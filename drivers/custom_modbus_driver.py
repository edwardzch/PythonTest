# 文件路径: drivers/custom_modbus.py
"""
自定义 Modbus 仪器/板卡驱动模块 (Custom Modbus Instrument Driver)
特性：
1. 支持“共享模式”（4工位共用一块仪器/板卡，通信自动排队互斥）与“独立模式”（每工位独立仪器/板卡串口）。
2. 配置编辑器中只需配置：串口号、从站地址、协议类型、自定义函数与工位映射表。
3. 波特率、数据位、校验位、超时时间由测试序列中的 open_serial_port 统一配置和打开。
"""

import threading
import time
import logging
import serial

try:
    import minimalmodbus
    MINIMALMODBUS_AVAILABLE = True
except ImportError:
    MINIMALMODBUS_AVAILABLE = False


def _to_int(val):
    """将十进制或十六进制字符串/整数转为 int"""
    if val is None or val == "":
        return 0
    if isinstance(val, int):
        return val
    s = str(val).strip()
    if s.lower().startswith("0x"):
        return int(s, 16)
    return int(s)


class CustomModbusDriver:
    """
    自定义 Modbus 仪器设备与多工位板卡驱动
    """

    DRIVER_META = {
        "name": "CustomModbusDriver",
        "display_name": "自定义Modbus仪器设备",
        "category": "custom_modbus",
        "interface": "serial",
        "supports_shared_mode": True,
        "supports_independent_mode": True,
    }

    CONFIG_TAB = {
        "tab_name": "自定义modbus仪器配置",
        "config_key": "custom_modbus_config",
        "mode": "shared",
    }

    # 配置 Schema（精简版：串口号 + 从站地址 + 协议类型 + 映射表）
    CONFIG_SCHEMA = {
        "device_mode": {
            "type": "mode_switch",
            "label": "工作模式",
            "shared_label": "共享模式（多工位共用一块仪器/板卡，通信自动互斥排队）",
            "independent_label": "独立模式（每工位独立仪器/板卡串口）",
            "shared_config_key": "shared_config",
            "station_count": 4,

            # 共享模式配置
            "shared_schema": {
                "port": {
                    "type": "serial_port",
                    "label": "串口号",
                    "default": "COM3"
                },
                "slave_id": {
                    "type": "int",
                    "label": "从站地址 (Slave ID)",
                    "default": 3
                },
                "protocol_type": {
                    "type": "choice",
                    "label": "协议类型",
                    "choices": ["holding_register (03H/06H 寄存器)", "coil (01H/05H 线圈)"],
                    "default": "holding_register (03H/06H 寄存器)"
                },
                "channel_mappings": {
                    "type": "relay_channel_editor",
                    "label": "自定义函数与工位地址配置 (配置后可在序列编辑器中直接调用)",
                    "default": []
                }
            },

            # 独立模式配置 (每工位)
            "independent_schema": {
                "port": {
                    "type": "serial_port",
                    "label": "串口号",
                    "default": "COM1"
                },
                "slave_id": {
                    "type": "int",
                    "label": "从站地址 (Slave ID)",
                    "default": 1
                },
                "protocol_type": {
                    "type": "choice",
                    "label": "协议类型",
                    "choices": ["holding_register (03H/06H 寄存器)", "coil (01H/05H 线圈)"],
                    "default": "holding_register (03H/06H 寄存器)"
                },
                "channel_mappings": {
                    "type": "single_channel_editor",
                    "label": "自定义功能与物理地址配置",
                    "default": []
                }
            }
        }
    }

    def __init__(self, port="COM3", slave_id=3, protocol_type="holding_register",
                 channel_mappings=None, logger=None, **kwargs):
        self.port = port
        self.slave_id = _to_int(slave_id) or 3
        self.protocol_type = "coil" if "coil" in str(protocol_type).lower() else "holding_register"
        self.channel_mappings = channel_mappings or []
        self.logger = logger or logging.getLogger(f"CustomModbus_{self.port}")

        # 串口参数由 open_serial_port 配置
        self.baudrate = 9600
        self.bytesize = 8
        self.parity = 'N'
        self.stopbits = 1
        self.timeout = 1.0

        self.instrument = None
        # 多工位共用串口互斥锁（工位1通讯时，其他工位自动排队等待）
        self.lock = threading.Lock()
        
        # 记录各通道当前状态缓存：{(station_id, physical_address): state_val}
        self._state_cache = {}
        # 函数名称速查表
        self._channel_map = {}
        self._reload_channel_map()

    def _reload_channel_map(self):
        """重新索引功能映射表"""
        self._channel_map = {}
        for item in self.channel_mappings:
            if isinstance(item, dict) and "alias" in item:
                alias = item["alias"].strip()
                if alias:
                    self._channel_map[alias] = item

    def update_config(self, port, slave_id, protocol_type, channel_mappings):
        """动态更新配置"""
        with self.lock:
            self.port = port
            self.slave_id = _to_int(slave_id) or 3
            self.protocol_type = "coil" if "coil" in str(protocol_type).lower() else "holding_register"
            self.channel_mappings = channel_mappings or []
            self._reload_channel_map()
            if self.instrument:
                try:
                    self.close()
                except Exception:
                    pass

    def open_serial(self, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=1.0):
        """
        根据测试序列 open_serial_port 传入的参数初始化并打开串口。
        """
        if not MINIMALMODBUS_AVAILABLE:
            raise RuntimeError("minimalmodbus 库未安装，无法使用 Modbus 仪器驱动。")

        with self.lock:
            try:
                self.baudrate = _to_int(baudrate) or 9600
                self.bytesize = _to_int(bytesize) or 8
                self.stopbits = _to_int(stopbits) or 1
                self.timeout = float(timeout) if timeout else 1.0
                
                # 校验位映射
                parity_str = str(parity).strip().upper()
                if parity_str == 'E' or parity_str == 'EVEN':
                    serial_parity = serial.PARITY_EVEN
                elif parity_str == 'O' or parity_str == 'ODD':
                    serial_parity = serial.PARITY_ODD
                else:
                    serial_parity = serial.PARITY_NONE
                self.parity = serial_parity

                # 如果已有打开的连接且串口一致，则更新参数或重连
                if self.instrument and hasattr(self.instrument, 'serial') and self.instrument.serial and self.instrument.serial.is_open:
                    self.instrument.serial.baudrate = self.baudrate
                    self.instrument.serial.bytesize = self.bytesize
                    self.instrument.serial.parity = self.parity
                    self.instrument.serial.stopbits = self.stopbits
                    self.instrument.serial.timeout = self.timeout
                    self.logger.info(f"串口 {self.port} 参数已更新: {self.baudrate}, {self.bytesize}, {self.parity}, {self.stopbits}, {self.timeout}s")
                    return True

                self.logger.info(f"正在打开 Modbus 串口 {self.port}: {self.baudrate}bps, 8-{parity_str}-{self.stopbits}, 从站: {self.slave_id}")
                instrument = minimalmodbus.Instrument(self.port, self.slave_id)
                instrument.serial.baudrate = self.baudrate
                instrument.serial.bytesize = self.bytesize
                instrument.serial.parity = self.parity
                instrument.serial.stopbits = self.stopbits
                instrument.serial.timeout = self.timeout
                instrument.mode = minimalmodbus.MODE_RTU
                instrument.close_port_after_each_call = False
                instrument.clear_buffers_before_each_transaction = True

                self.instrument = instrument
                self.logger.info(f"Modbus 串口 {self.port} 打开成功！")
                return True
            except Exception as e:
                self.logger.error(f"打开 Modbus 串口 {self.port} 失败: {e}")
                self.instrument = None
                raise

    def connect(self):
        """按需连接（使用当前参数）"""
        return self.open_serial(self.baudrate, self.bytesize, self.parity, self.stopbits, self.timeout)

    def is_connected(self):
        with self.lock:
            return bool(self.instrument and hasattr(self.instrument, 'serial') and self.instrument.serial and self.instrument.serial.is_open)

    def close(self):
        """关闭串口"""
        with self.lock:
            if self.instrument and hasattr(self.instrument, 'serial') and self.instrument.serial:
                try:
                    self.instrument.serial.close()
                    self.logger.info(f"Modbus 串口 {self.port} 已关闭。")
                except Exception as e:
                    self.logger.warning(f"关闭串口 {self.port} 时发生异常: {e}")
            self.instrument = None

    def get_physical_address(self, func_name, station_id="station_1"):
        """
        根据函数名称和当前工位，解析出物理寄存器/线圈地址与配置。
        返回: (address_int, item_info)
        """
        item_info = self._channel_map.get(func_name)
        if not item_info:
            try:
                addr = _to_int(func_name)
                return addr, {"alias": func_name, "on_value": 1, "off_value": 0}
            except Exception:
                raise ValueError(f"未找到自定义 Modbus 函数/项目 '{func_name}' 的配置。请在配置编辑器的'自定义modbus仪器配置'中添加。")

        station_addrs = item_info.get("station_addresses", {})
        if isinstance(station_addrs, dict) and station_id in station_addrs:
            addr_raw = station_addrs[station_id]
        else:
            addr_raw = item_info.get("address", "0")

        addr = _to_int(addr_raw)
        return addr, item_info

    def execute_function(self, func_name, state=True, station_id="station_1"):
        """
        执行自定义功能写入：
        state 为 True 时写入 true值，state 为 False 时写入 false值。
        通信期间使用 self.lock 保证 485 总线排队互斥，其他工位自动等待。
        """
        if not self.is_connected():
            self.connect()

        # 解析布尔状态
        target_is_true = True if str(state).strip().upper() in ["TRUE", "1", "ON", "OPEN", "HIGH", "吸合", "开", "YES"] else False
        addr, item_info = self.get_physical_address(func_name, station_id)

        # 获取 true值 / false值
        true_val = _to_int(item_info.get("on_value", item_info.get("true_value", 1)))
        false_val = _to_int(item_info.get("off_value", item_info.get("false_value", 0)))
        value_to_write = true_val if target_is_true else false_val

        # 485 总线排队互斥执行写入
        try:
            self._raw_write(addr, value_to_write)
            self._state_cache[(station_id, addr)] = target_is_true
            state_text = f"True (写入值: {value_to_write})" if target_is_true else f"False (写入值: {value_to_write})"
            msg = f"工位 {station_id} 执行 '{func_name}' (0x{addr:04X}) -> {state_text}"
            self.logger.info(msg)
            return True, msg
        except Exception as e:
            err = f"工位 {station_id} 执行 '{func_name}' (0x{addr:04X}) 失败: {e}"
            self.logger.error(err)
            return False, err

    def read_function(self, func_name, station_id="station_1"):
        """
        读取状态
        """
        if not self.is_connected():
            self.connect()

        addr, item_info = self.get_physical_address(func_name, station_id)
        true_val = _to_int(item_info.get("on_value", item_info.get("true_value", 1)))

        try:
            val = self._raw_read(addr)
            is_true = (val == true_val) if self.protocol_type != "coil" else bool(val)
            self._state_cache[(station_id, addr)] = is_true
            msg = f"工位 {station_id} 读取 '{func_name}' (0x{addr:04X}) -> {is_true} (原始值: {val})"
            return (1 if is_true else 0), msg
        except Exception as e:
            err = f"工位 {station_id} 读取 '{func_name}' (0x{addr:04X}) 失败: {e}"
            self.logger.error(err)
            return False, err

    def _raw_write(self, register_or_coil, value):
        with self.lock:
            if not self.instrument:
                raise RuntimeError("串口通信未建立，请先调用 open_serial_port。")
            if self.protocol_type == "coil":
                self.instrument.write_bit(register_or_coil, 1 if value else 0, functioncode=5)
            else:
                self.instrument.write_register(register_or_coil, value, functioncode=6)

    def _raw_read(self, register_or_coil):
        with self.lock:
            if not self.instrument:
                raise RuntimeError("串口通信未建立，请先调用 open_serial_port。")
            if self.protocol_type == "coil":
                return self.instrument.read_bit(register_or_coil, functioncode=1)
            else:
                return self.instrument.read_register(register_or_coil, functioncode=3)
