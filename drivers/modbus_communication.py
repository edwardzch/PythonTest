# 文件路径: drivers/real/modbus_communication.py (最终修正版)

import minimalmodbus
import serial
import logging
import re
from sniffer import sniffer_instance


class ConnectionError(Exception): pass


class SerialWrapper(serial.Serial):
    """
    一个 serial.Serial 的包装器，用于在读写操作前后进行日志记录。
    """
    def write(self, data):
        sniffer_instance.log_communication('TX', self.port, data)
        return super().write(data)

    def read(self, size=1):
        data = super().read(size)
        # 记录所有接收到的数据，真实反映设备返回的内容
        if data:
            sniffer_instance.log_communication('RX', self.port, data)
        return data



MODBUS_ERROR_CODES = {
    0x01: "功能码无法识别", 0x31: "功能码无法识别",
    0x02: "数据地址不存在", 0x32: "数据地址不存在",
    0x03: "数据值不允许/超限", 0x33: "数据值不允许/超限",
    0x04: "执行请求失败", 0x34: "执行请求失败",
    0x05: "编码器通讯超时", 0x51: "编码器通讯超时",
    0x06: "编码器CRC错误", 0x52: "编码器CRC错误",
    0x07: "数据地址不存在(采集板)", 0x53: "数据地址不存在(采集板)",
    0x08: "Modbus CRC错误", 0x54: "Modbus CRC错误",
    0x09: "未设置编码器类型", 0x55: "未设置编码器类型",
    0x0A: "SN位数错误", 0x56: "SN位数错误",
}


class ModbusCommunicator:
    """
    一个基于 minimalmodbus 的、非线程安全的Modbus通信驱动。
    它遵循了良好的设计实践，解决了生命周期管理问题。
    1. __init__ 只保存配置，不执行任何I/O。
    2. connect() 方法负责创建和打开连接。
    3. close() 方法负责关闭和清理连接。
    """

    # ========== 驱动元数据 ==========
    DRIVER_META = {
        "name": "ModbusCommunicator",
        "display_name": "Modbus 串口通信",
        "category": "communication",
        "interface": "serial",
    }
    
    # ========== 配置 Tab 定义 ==========
    CONFIG_TAB = {
        "tab_name": "串口配置",
        "config_key": "serial_config",
        "mode": "shared",  # 共享串口模式
    }
    
    # ========== 配置表单定义 ==========
    CONFIG_SCHEMA = {
        "port": {
            "type": "serial_port",
            "label": "端口号",
            "default": "COM1",
            "tooltip": "选择串口"
        },
        "baudrate": {
            "type": "baudrate",
            "label": "波特率",
            "default": 9600
        },
        "timeout": {
            "type": "float",
            "label": "超时时间(秒)",
            "default": 1.0
        }
    }


    def __init__(self, port, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=1.0, **kwargs):
        """
        初始化驱动，只存储配置参数，不打开连接。
        """
        # --- 【【【核心修复 1: 明确存储所有配置参数】】】 ---
        self.port = port
        self.baudrate = int(baudrate)
        self.bytesize = int(bytesize)
        self.parity = parity  # 保持为 'N', 'E', 'O' 字符串, minimalmodbus 会处理
        self.stopbits = int(stopbits)
        self.timeout = float(timeout)

        self.instrument = None  # 连接句柄，在 connect() 之前始终为 None

        self.logger = logging.getLogger(f"ModbusDrv.{self.port}")
        self.logger.info(f"驱动已初始化，配置: {self.get_config_dict()}")

    def get_config_dict(self):
        """返回当前配置的字典，方便调试。"""
        return {
            "port": self.port, "baudrate": self.baudrate, "bytesize": self.bytesize,
            "parity": self.parity, "stopbits": self.stopbits, "timeout": self.timeout
        }

    # --- 【【【核心修复 2: 移除 reconfigure 方法】】】 ---
    # reconfigure 是导致警告和状态混乱的根源，已被移除。

    def connect(self):
        if self.is_connected():
            return
        try:
            logging.info(f"ModbusDrv.{self.port}: 正在打开并配置 Modbus 端口...")
            
            # 创建自定义的串口包装器实例
            ser = SerialWrapper(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self.timeout
            )
            
            # 将包装器实例传递给 minimalmodbus
            self.instrument = minimalmodbus.Instrument(
                port=ser,  # 传递的是对象而不是端口字符串
                slaveaddress=1,
                mode=minimalmodbus.MODE_RTU
            )
            self.instrument.clear_buffers_before_each_transaction = True
            logging.info(f"ModbusDrv.{self.port}: 端口 {self.port} 成功打开。")
        except Exception as e:
            # 捕获所有底层异常，包装成我们自己的 ConnectionError
            error_msg = f"无法打开或配置 Modbus 端口 {self.port}: {e}"
            logging.error(f"ERROR:ModbusDrv.{self.port}:{error_msg}", exc_info=True)
            raise ConnectionError(error_msg) from e

    def close(self):
        """
        安全地关闭串口连接。
        """
        if self.instrument and hasattr(self.instrument.serial, 'close'):
            if self.instrument.serial.is_open:
                self.instrument.serial.close()
                self.logger.info(f"端口 {self.port} 已关闭。")
        self.instrument = None

    def is_connected(self):
        """
        检查 minimalmodbus 实例是否存在且其内部串口是打开的。
        """
        return self.instrument is not None and hasattr(self.instrument, 'serial') and self.instrument.serial.is_open

    def _ensure_connected(self):
        """内部辅助函数，确保在执行操作前已连接。"""
        if not self.is_connected():
            raise ConnectionError(f"操作失败: 串口 {self.port} 未连接。")

    def _set_slave(self, slave_address):
        """设置当前操作的目标从站地址。"""
        self._ensure_connected()
        self.instrument.address = int(slave_address)

    def _handle_modbus_exception(self, e, slave_address):
        """统一处理Modbus异常，提供更友好的错误信息。"""
        if isinstance(e, minimalmodbus.NoResponseError):
            raise IOError(f"Modbus设备(地址:{slave_address})无响应")

        elif isinstance(e, minimalmodbus.ModbusException):
            code = None
            # First, try to get the code from standard attributes
            if hasattr(e, 'slave_exception_code'):
                code = e.slave_exception_code
            elif hasattr(e, 'exceptioncode'):
                code = e.exceptioncode
            elif hasattr(e, 'exception_code'):
                code = e.exception_code
            
            # If standard attributes fail, try parsing the error message string as a fallback
            if code is None:
                try:
                    error_string = str(e)
                    # Look for "Slave reported error code XX"
                    match = re.search(r'Slave reported error code (\d+)', error_string)
                    if match:
                        code = int(match.group(1))
                except (ValueError, TypeError):
                    pass  # Ignore parsing errors

            if code is not None:
                message = MODBUS_ERROR_CODES.get(code, f"未知的Modbus错误码: {hex(code)}")
                raise IOError(f"Modbus设备(地址:{slave_address})返回错误: {message} (原始码: {hex(code)})")
            else:
                # If we still can't find the code, log everything we know about the exception
                self.logger.error(f"无法解析Modbus异常。类型: {type(e)}, 属性: {dir(e)}")
                raise IOError(f"Modbus设备(地址:{slave_address})返回了一个无法解析的错误: {e}")
        else:
            # Re-raise any other unexpected exceptions
            raise e

    # --- 以下是您原有的、现在可以正常工作的Modbus读写功能 ---
    def read_holding_registers(self, slave_address, register_address, num_of_registers):
        self._ensure_connected()
        try:
            self._set_slave(slave_address)
            # minimalmodbus v2.0+ 推荐使用 read_registers
            return self.instrument.read_registers(registeraddress=register_address,
                                                  number_of_registers=num_of_registers)
        except Exception as e:
            self._handle_modbus_exception(e, slave_address)

    def read_input_registers(self, slave_address, register_address, num_of_registers):
        self._ensure_connected()
        try:
            self._set_slave(slave_address)
            return self.instrument.read_registers(registeraddress=register_address,
                                                  number_of_registers=num_of_registers, functioncode=4)
        except Exception as e:
            self._handle_modbus_exception(e, slave_address)

    def write_single_register(self, slave_address, register_address, value):
        self._ensure_connected()
        try:
            self._set_slave(slave_address)
            # 明确指定功能码6
            self.instrument.write_register(registeraddress=register_address, value=value, functioncode=6)
        except Exception as e:
            self._handle_modbus_exception(e, slave_address)

    def write_multiple_registers(self, slave_address, register_address, values):
        self._ensure_connected()
        try:
            self._set_slave(slave_address)
            self.instrument.write_registers(registeraddress=register_address, values=values)
        except Exception as e:
            self._handle_modbus_exception(e, slave_address)

    def write_string(self, slave_address, register_address, text_string):
        self._ensure_connected()
        try:
            self._set_slave(slave_address)
            self.instrument.write_string(registeraddress=register_address, textstring=text_string)
        except Exception as e:
            self._handle_modbus_exception(e, slave_address)

    def read_string(self, slave_address, register_address, number_of_registers):
        self._ensure_connected()
        try:
            self._set_slave(slave_address)
            return self.instrument.read_string(registeraddress=register_address,
                                               number_of_registers=number_of_registers)
        except Exception as e:
            self._handle_modbus_exception(e, slave_address)

    def read_long(self, slave_address, register_address, signed=False, byteorder=0):
        """
        读取32位整数。
        :param byteorder: 0=HighWordFirst(BigEndian), 1=LowWordFirst, 2=LittleEndian, 3=LowWordFirst LittleEndian
        """
        self._ensure_connected()
        try:
            self._set_slave(slave_address)
            return self.instrument.read_long(registeraddress=register_address, signed=signed, byteorder=byteorder)
        except Exception as e:
            self._handle_modbus_exception(e, slave_address)