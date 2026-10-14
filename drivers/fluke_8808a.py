# drivers/real/fluke_8808a.py
# Based on the user-provided, debugged testfluke.py

import pyvisa
import time
import threading

from utils.visa_timeout import visa_call_with_timeout, DEFAULT_VISA_IO_TIMEOUT

# Python 级 VISA 超时（秒）
VISA_IO_TIMEOUT = DEFAULT_VISA_IO_TIMEOUT
VISA_CONNECT_TIMEOUT = 15

class Fluke8808A:
    """Driver for Fluke 8808A Multimeter, using a two-step command protocol."""

    # ========== 驱动元数据 ==========
    DRIVER_META = {
        "name": "Fluke8808A",
        "display_name": "福禄克 8808A 万用表",
        "category": "multimeter",
        "interface": "visa",
    }
    
    # ========== 配置 Tab 定义（动态生成 Tab）==========
    CONFIG_TAB = {
        "tab_name": "Fluke8808A 配置",
        "config_key": "dmm_config",
        "mode": "shared",
    }
    
    # ========== 配置表单定义（支持共享/独立模式）==========
    CONFIG_SCHEMA = {
        "dmm_mode": {
            "type": "mode_switch",
            "label": "万用表模式",
            "shared_label": "共享模式（多工位共用一台万用表）",
            "independent_label": "独立模式（每工位独立万用表）",
            "shared_config_key": "shared_config",
            "station_count": 4,
            
            # 共享模式配置
            "shared_schema": {
                "visa_settings": {
                    "type": "visa_with_connect",
                    "label": "VISA 地址",
                    "default": "ASRL1::INSTR",
                    "auto_connect_default": True
                },
                "default_mode": {
                    "type": "select",
                    "label": "默认模式",
                    "options": ["DCV", "ACV", "DCI", "ACI", "RES", "DIODE", "FREQ", "CONT"],
                    "default": "DCV"
                }
            },
            
            # 独立模式配置
            "independent_schema": {
                "visa_settings": {
                    "type": "visa_with_connect",
                    "label": "VISA 地址",
                    "default": "",
                    "auto_connect_default": True
                },
                "default_mode": {
                    "type": "select",
                    "label": "默认模式",
                    "options": ["DCV", "ACV", "DCI", "ACI", "RES", "DIODE", "FREQ", "CONT"],
                    "default": "DCV"
                }
            }
        }
    }


    CONFIG_COMMANDS = {
        "DCV": "VDC",
        "ACV": "VAC",
        "DCI": "ADC",
        "ACI": "AAC",
        "RES": "OHMS",
        "DIODE": "DIOD",
        "FREQ": "HZ",
        "CONT": "CONT"
    }
    FETCH_COMMAND = "VAL1?"

    def __init__(self, visa_address):
        self.visa_address = visa_address
        self.instrument = None
        self.lock = threading.Lock()

    def _robust_query_unlocked(self, query_string):
        """无锁的查询，必须在获取锁之后使用。"""
        try:
            visa_call_with_timeout(self.instrument.write, args=(query_string,), timeout=VISA_IO_TIMEOUT)
            data = visa_call_with_timeout(self.instrument.read, timeout=VISA_IO_TIMEOUT).strip()
            prompt = visa_call_with_timeout(self.instrument.read, timeout=VISA_IO_TIMEOUT).strip()
        except TimeoutError:
            self._force_close()
            raise ConnectionError(f"设备 '{self.visa_address}' 通信超时 (query: {query_string})")
        if prompt in ["?>", "!>"]:
            raise Exception(f"Query command '{query_string}' failed with prompt: {prompt}")
        return data

    def _robust_query(self, query_string):
        """发送查询并读取数据和后续提示符。"""
        self._check_connection()
        with self.lock:
            return self._robust_query_unlocked(query_string)

    def connect(self):
        if self.is_connected():
            return
        
        # 优先使用 pyvisa-py 后端（与扫描器一致）
        backends_to_try = [
            ('@py', 'pyvisa-py'),
            ('', 'NI-VISA'),
        ]
        
        last_error = None
        for backend, backend_name in backends_to_try:
            try:
                if backend:
                    rm = pyvisa.ResourceManager(backend)
                else:
                    rm = pyvisa.ResourceManager()
                
                self.instrument = rm.open_resource(
                    self.visa_address,
                    read_termination='\r\n',
                    write_termination='\r',
                    baud_rate=9600,
                    timeout=5000
                )
                # Enter remote mode
                self._write_config_command("REMS")
                
                idn = self._robust_query("*IDN?")
                print(f"[Fluke] ✅ 成功连接: {idn} (后端: {backend_name})")
                return
                
            except Exception as e:
                last_error = e
                self.instrument = None
                continue
        
        error_msg = f"连接到 Fluke 8808A ({self.visa_address}) 失败: {last_error}"
        raise ConnectionError(error_msg) from last_error

    def is_connected(self):
        """Checks if the instrument is currently connected."""
        # A simple check is to see if the instrument object exists.
        # A more robust check might involve a quick query.
        return self.instrument is not None

    def _check_connection(self):
        """辅助函数，检查连接状态，如果未连接则抛出异常。"""
        if not self.is_connected():
            raise ConnectionError(f"操作失败: 设备 '{self.visa_address}' 未连接。")

    def _write_config_command_unlocked(self, command):
        """无锁的写操作，必须在获取锁之后使用。"""
        try:
            visa_call_with_timeout(self.instrument.write, args=(command,), timeout=VISA_IO_TIMEOUT)
            prompt = visa_call_with_timeout(self.instrument.read, timeout=VISA_IO_TIMEOUT).strip()
        except TimeoutError:
            self._force_close()
            raise ConnectionError(f"设备 '{self.visa_address}' 通信超时 (write: {command})")
        if prompt in ["?", "!>"]:
            # Note: For REMS command, we might not get a prompt. This depends on Fluke's firmware.
            # But according to testfluke.py it does, unless it's REMS? testfluke.py ignored prompt for REMS.
            raise Exception(f"Configuration command '{command}' failed with prompt: {prompt}")

    def _write_config_command(self, command):
        """发送配置命令并清除返回的提示符。"""
        self._check_connection()
        with self.lock:
            self._write_config_command_unlocked(command)
        """发送配置命令并清除返回的提示符。"""
        try:
            visa_call_with_timeout(self.instrument.write, args=(command,), timeout=VISA_IO_TIMEOUT)
            prompt = visa_call_with_timeout(self.instrument.read, timeout=VISA_IO_TIMEOUT).strip()
        except TimeoutError:
            self._force_close()
            raise ConnectionError(f"设备 '{self.visa_address}' 通信超时 (write: {command})")
        if prompt in ["?", "!>"]:
            raise Exception(f"Configuration command '{command}' failed with prompt: {prompt}")

    def _force_close(self):
        """通信超时后的紧急断开，不再尝试与设备通信。"""
        self.instrument = None
        print(f"[Fluke] ⚠️ 设备 '{self.visa_address}' 已被强制断开（通信超时）")

    def _query_value(self):
        """Queries the instrument for its value using the robust query method."""
        data = self._robust_query(self.FETCH_COMMAND)
        try:
            value_str = data.split()[0]
            return float(value_str)
        except (ValueError, IndexError):
            print(f"Warning: Could not parse DMM value from response: '{data}'")
            return None

    # 为了兼容旧版本的 read_value 别名
    read_value = _query_value

    def measure_atomic(self, mode_key=None):
        """
        [推荐的多工位并发测量方式]
        线程安全的原子级测量方法。
        获取线程锁 -> 切换模式 -> 等待稳定 -> 触发测量 -> 释放锁。
        防止不同工位多线程状态下交叉干扰万用表的测量状态。
        """
        self._check_connection()
        with self.lock:
            # 如果提供了新模式，进行切换
            if mode_key:
                config_cmd = self.CONFIG_COMMANDS.get(mode_key.upper())
                if config_cmd:
                    try:
                        # 对于部分模式切换需要一定时间切延迟
                        self._write_config_command_unlocked(config_cmd)
                        time.sleep(0.5) 
                    except Exception as e:
                        print(f"Warning: Mode set via atomic measure failed: {e}")
            
            # 读取数值
            data = self._robust_query_unlocked(self.FETCH_COMMAND)
            try:
                value_str = data.split()[0]
                return float(value_str)
            except (ValueError, IndexError):
                print(f"Warning: Could not parse DMM value from response: '{data}'")
                return None

    def set_mode(self, mode_key):
        """Sets the measurement function of the multimeter."""
        config_cmd = self.CONFIG_COMMANDS.get(mode_key.upper())
        if not config_cmd:
            raise ValueError(f"Invalid measurement mode key: {mode_key}")
        self._write_config_command(config_cmd)
        # A short delay after setting the mode is good practice
        time.sleep(0.2)

    def read_value(self):
        """Reads the currently displayed value from the multimeter."""
        return self._query_value()

    def close(self):
        """Return instrument to local mode and close connection."""
        if self.instrument:
            try:
                visa_call_with_timeout(
                    self.instrument.write, args=("LOCS",), timeout=3
                )
            except Exception:
                pass
            try:
                visa_call_with_timeout(self.instrument.close, timeout=3)
            except Exception:
                pass
            self.instrument = None