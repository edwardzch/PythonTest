# 文件路径: drivers/relay_board_driver.py
"""
USB/串口继电器板驱动 (USB Relay Driver - TC/LCUS 4/8路光耦继电器协议)
协议格式 (HEX 4字节):
  - 帧头: 0xA0
  - 通道号: 0x01 ~ 0x08 (0x0F 为所有通道)
  - 操作码: 0x01 (打开/ON), 0x00 (关闭/OFF), 0x02 (查询状态)
  - 校验和: (0xA0 + 通道号 + 操作码) & 0xFF
  - 板卡响应: ASCII 字符串，如 "CH1:ON", "CH1:OFF"
"""

import threading
import time
import logging
import serial


def _to_int(val):
    if val is None or val == "":
        return 0
    if isinstance(val, int):
        return val
    s = str(val).strip()
    if s.lower().startswith("0x"):
        return int(s, 16)
    return int(s)


class RelayBoardDriver:
    """
    USB / 串口继电器板驱动 (非 Modbus 协议，专用 HEX/ASCII 协议)
    """

    DRIVER_META = {
        "name": "RelayBoardDriver",
        "display_name": "USB继电器板 (4/8路)",
        "category": "relay_board",
        "interface": "serial",
        "supports_shared_mode": True,
        "supports_independent_mode": True,
    }

    CONFIG_TAB = {
        "tab_name": "USB继电器板配置",
        "config_key": "relay_board_config",
        "mode": "shared",
    }

    CONFIG_SCHEMA = {
        "device_mode": {
            "type": "mode_switch",
            "label": "工作模式",
            "shared_label": "共享模式（多工位共用一块继电器板，通信自动互斥排队）",
            "independent_label": "独立模式（每工位独立继电器板串口）",
            "shared_config_key": "shared_config",
            "station_count": 4,

            # 共享模式配置
            "shared_schema": {
                "port": {
                    "type": "serial_port",
                    "label": "串口号",
                    "default": "COM4"
                },
                "mapping_info": {
                    "type": "info_box",
                    "label": "工位通道映射说明",
                    "text": "💡 共享模式通道映射说明：\n • 工位 1 执行测试时自动控制 CH1 (第1路继电器)\n • 工位 2 执行测试时自动控制 CH2 (第2路继电器)\n • 工位 3 执行测试时自动控制 CH3 (第3路继电器)\n • 工位 4 执行测试时自动控制 CH4 (第4路继电器)\n • 多工位并发测试时底层自动互斥排队，无需担心指令冲突。"
                }
            },

            # 独立模式配置 (每工位独立继电器板串口)
            "independent_schema": {
                "port": {
                    "type": "serial_port",
                    "label": "串口号",
                    "default": "COM1"
                }
            }
        }
    }

    def __init__(self, port="COM4", channel_mappings=None, logger=None, **kwargs):
        self.port = port
        self.channel_mappings = channel_mappings or []
        self.logger = logger or logging.getLogger(f"RelayBoard_{self.port}")

        # 默认串口参数
        self.baudrate = 9600
        self.bytesize = 8
        self.parity = serial.PARITY_NONE
        self.stopbits = 1
        self.timeout = 1.0

        self.serial_inst = None
        self.lock = threading.Lock()
        self._channel_map = {}
        self._reload_channel_map()

    def _reload_channel_map(self):
        self._channel_map = {}
        for item in self.channel_mappings:
            if isinstance(item, dict) and "alias" in item:
                alias = item["alias"].strip()
                if alias:
                    self._channel_map[alias] = item

    def open_serial(self, baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=1.0):
        """打开串口"""
        with self.lock:
            try:
                self.baudrate = _to_int(baudrate) or 9600
                self.bytesize = _to_int(bytesize) or 8
                self.stopbits = _to_int(stopbits) or 1
                self.timeout = float(timeout) if timeout else 1.0

                parity_str = str(parity).strip().upper()
                if parity_str in ('E', 'EVEN'):
                    self.parity = serial.PARITY_EVEN
                elif parity_str in ('O', 'ODD'):
                    self.parity = serial.PARITY_ODD
                else:
                    self.parity = serial.PARITY_NONE

                if self.serial_inst and self.serial_inst.is_open:
                    self.serial_inst.baudrate = self.baudrate
                    self.serial_inst.bytesize = self.bytesize
                    self.serial_inst.parity = self.parity
                    self.serial_inst.stopbits = self.stopbits
                    self.serial_inst.timeout = self.timeout
                    self.logger.info(f"继电器板串口 {self.port} 参数已更新")
                    return True

                self.logger.info(f"正在打开继电器板串口 {self.port}: {self.baudrate}bps, 8-{parity_str}-{self.stopbits}")
                self.serial_inst = serial.Serial(
                    port=self.port,
                    baudrate=self.baudrate,
                    bytesize=self.bytesize,
                    parity=self.parity,
                    stopbits=self.stopbits,
                    timeout=self.timeout
                )
                self.logger.info(f"继电器板串口 {self.port} 打开成功！")
                return True
            except Exception as e:
                self.logger.error(f"打开继电器板串口 {self.port} 失败: {e}")
                self.serial_inst = None
                raise

    def connect(self):
        return self.open_serial(self.baudrate, self.bytesize, self.parity, self.stopbits, self.timeout)

    def is_connected(self):
        with self.lock:
            return bool(self.serial_inst and self.serial_inst.is_open)

    def close(self):
        with self.lock:
            if self.serial_inst:
                try:
                    self.serial_inst.close()
                    self.logger.info(f"继电器板串口 {self.port} 已关闭。")
                except Exception as e:
                    self.logger.warning(f"关闭继电器板串口异常: {e}")
            self.serial_inst = None

    def _send_cmd(self, channel_int, op_code):
        """
        发送继电器指令并接收响应
        :param channel_int: 通道号 1~8 或 0x0F (全部)
        :param op_code: 0x01 (ON), 0x00 (OFF), 0x02 (QUERY)
        :return: (bool, str) 响应结果
        """
        with self.lock:
            if not self.serial_inst or not self.serial_inst.is_open:
                raise RuntimeError(f"继电器板串口 {self.port} 未打开，请先调用 open_serial_port。")

            # 计算校验和 (0xA0 + channel + op_code) & 0xFF
            checksum = (0xA0 + channel_int + op_code) & 0xFF
            tx_data = bytes([0xA0, channel_int, op_code, checksum])

            # 清空缓存
            self.serial_inst.reset_input_buffer()
            self.serial_inst.reset_output_buffer()

            # 发送 HEX 报文
            self.serial_inst.write(tx_data)
            self.serial_inst.flush()
            time.sleep(0.05)

            # 读取板卡返回的 ASCII 响应
            rx_data = b""
            start_time = time.time()
            while time.time() - start_time < (self.timeout or 1.0):
                if self.serial_inst.in_waiting > 0:
                    rx_data += self.serial_inst.read(self.serial_inst.in_waiting)
                    if b"\n" in rx_data or len(rx_data) >= 6:
                        break
                time.sleep(0.02)

            rx_str = rx_data.decode("ascii", errors="ignore").strip()
            self.logger.debug(f"[RelayBoard] TX: {tx_data.hex(' ').upper()} -> RX: '{rx_str}'")
            return True, rx_str

    def get_channel_by_name(self, func_name=None, station_id="station_1"):
        """根据配置或工位号解析对应的通道号 (1~8 或 0x0F)"""
        # 如果未指定或指定通用名称，默认工位 1->CH1, 工位 2->CH2, 工位 3->CH3, 工位 4->CH4
        station_num = 1
        if str(station_id).startswith("station_"):
            try:
                station_num = int(str(station_id).split("_")[-1])
            except Exception:
                station_num = 1

        if not func_name or str(func_name).strip() in ("", "None", "K_BOARD", "RELAY", "relay", "default"):
            return min(max(station_num, 1), 8)

        if str(func_name).lower() in ("all", "0x0f", "15"):
            return 0x0F

        try:
            return int(func_name)
        except Exception:
            pass

        item_info = self._channel_map.get(func_name)
        if item_info:
            st_addrs = item_info.get("station_addresses", {})
            ch_raw = st_addrs.get(station_id, item_info.get("address", str(station_num)))
            if str(ch_raw).lower() in ("all", "0x0f", "15"):
                return 0x0F
            return _to_int(ch_raw) or station_num

        return min(max(station_num, 1), 8)

    def set_relay(self, channel=1, state=True):
        """
        直接设置指定通道的继电器开关
        :param channel: 1~8 或 0x0F/'all'
        :param state: True (开), False (关)
        """
        if not self.is_connected():
            self.connect()

        ch_int = 0x0F if str(channel).lower() in ('all', '0x0f', '15') else int(channel)
        op_code = 0x01 if state else 0x00
        ok, resp = self._send_cmd(ch_int, op_code)
        ch_desc = "所有通道" if ch_int == 0x0F else f"第 {ch_int} 路"
        action_desc = "打开(ON)" if state else "关闭(OFF)"
        msg = f"继电器板 {ch_desc} {action_desc} -> 返回: {resp}"
        self.logger.info(msg)
        return True, msg

    def query_relay(self, channel=1):
        """
        查询指定通道的继电器状态
        :param channel: 1~8 或 0x0F
        :return: (1 if ON else 0), resp_str
        """
        if not self.is_connected():
            self.connect()

        ch_int = 0x0F if str(channel).lower() in ('all', '0x0f', '15') else int(channel)
        ok, resp = self._send_cmd(ch_int, 0x02)
        
        # 精准匹配目标通道状态
        import re
        match = re.search(rf"CH{ch_int}\s*:\s*(ON|OFF)", resp.upper())
        if match:
            is_on = (match.group(1) == "ON")
        else:
            is_on = ("ON" in resp.upper()) and ("OFF" not in resp.upper())
            
        status_str = "ON (吸合)" if is_on else "OFF (断开)"
        msg = f"继电器板 第 {ch_int} 路状态: {status_str} (原始响应: {resp})"
        self.logger.info(msg)
        return (1 if is_on else 0), msg

    def execute_function(self, func_name, state=True, station_id="station_1"):
        """
        序列调用入口：支持工位自动映射通道
        """
        ch_int = self.get_channel_by_name(func_name, station_id)
        target_state = True if str(state).strip().upper() in ["TRUE", "1", "ON", "OPEN", "HIGH", "吸合", "开", "YES"] else False
        return self.set_relay(ch_int, target_state)
