# 文件路径: drivers/siglent_spd4323x.py
# Siglent SPD4323X 四通道程控电源驱动

import pyvisa
import threading
import logging
import time


class ConnectionError(Exception):
    """连接错误异常"""
    pass


class SiglentSPD4323X:
    """
    鼎阳 SPD4323X 四通道可编程线性直流电源驱动。
    支持 USB/LAN 通过 VISA 接口进行 SCPI 通信。
    """
    
    # ========== 驱动元数据（插件化架构） ==========
    DRIVER_META = {
        "name": "SiglentSPD4323X",
        "display_name": "鼎阳 SPD4323X 四通道电源",
        "category": "power_supply",
        "interface": "visa",
        "channels": 4,
        "supports_shared_mode": True,
        "supports_independent_mode": True,
    }
    
    # ========== 配置 Tab 定义 ==========
    CONFIG_TAB = {
        "tab_name": "SPD4323X 电源配置",
        "config_key": "spd4323x_power_config",
        "mode": "shared",  # 共享模式
    }
    
    # ========== 配置 Schema ==========
    CONFIG_SCHEMA = {
        "visa_address": {
            "type": "visa",
            "label": "VISA 地址",
            "default": "USB0::...",
            "tooltip": "例如: USB0::0xF4ED::0xEE3A::SPD4XIBQ5R2345::INSTR"
        },
        "auto_connect_on_startup": {
            "type": "bool",
            "label": "启动时连接",
            "default": False
        }
    }

    def __init__(self, visa_address, logger=None):
        """
        初始化驱动，只保存配置，不进行连接。
        
        :param visa_address: VISA 资源地址字符串
        :param logger: 可选的日志记录器
        """
        self.visa_address = visa_address
        self.instrument = None
        self.lock = threading.Lock()
        self._current_channel = 1

        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(f"SiglentSPD4323X_{self.visa_address}")
            if not self.logger.handlers:
                logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')

        self.logger.info(f"驱动 for SiglentSPD4323X '{self.visa_address}' 已创建但未连接。")

    @staticmethod
    def list_resources():
        """
        扫描系统中所有可用的 VISA 资源。
        
        :return: VISA 资源地址列表
        """
        try:
            rm = pyvisa.ResourceManager()
            resources = rm.list_resources()
            return list(resources)
        except Exception as e:
            logging.error(f"扫描 VISA 资源失败: {e}")
            return []

    def connect(self):
        """
        连接到仪器。如果已连接则跳过。
        
        :raises ConnectionError: 连接失败时抛出
        """
        if self.instrument:
            self.logger.info(f"设备 '{self.visa_address}' 已连接，跳过重复连接。")
            return
        try:
            rm = pyvisa.ResourceManager()
            self.instrument = rm.open_resource(self.visa_address)
            self.instrument.timeout = 5000  # 5 秒超时
            self.instrument.write_termination = '\n'
            self.instrument.read_termination = '\n'
            
            idn = self.instrument.query('*IDN?')
            self.logger.info(f"成功连接到 Siglent SPD4323X: {idn.strip()} at {self.visa_address}")
        except Exception as e:
            error_msg = f"连接到 Siglent SPD4323X ({self.visa_address}) 失败: {e}"
            self.logger.error(error_msg, exc_info=True)
            raise ConnectionError(error_msg) from e

    def is_connected(self):
        """检查设备是否已连接。"""
        return self.instrument is not None

    def _check_connection(self):
        """辅助函数，检查连接状态，如果未连接则抛出异常。"""
        if not self.is_connected():
            raise ConnectionError(f"操作失败: 设备 '{self.visa_address}' 未连接。")

    def _write(self, command):
        """发送命令到仪器（线程安全）。"""
        self._check_connection()
        with self.lock:
            self.instrument.write(command)
            time.sleep(0.05)  # 短暂延迟确保命令被处理

    def _query(self, command):
        """发送查询命令并返回结果（线程安全）。"""
        self._check_connection()
        with self.lock:
            return self.instrument.query(command)

    # ========== 通道控制 ==========
    
    def select_channel(self, channel):
        """
        选择要操作的通道。
        注意：SPD4323X 的大部分命令需要在命令中直接指定通道，
        此方法主要用于记录当前操作的通道。
        
        :param channel: 通道号 (1-4)
        """
        if channel < 1 or channel > 4:
            raise ValueError(f"通道号必须在 1-4 之间，当前: {channel}")
        self._current_channel = int(channel)
        self.logger.debug(f"已选择通道 {self._current_channel}")

    def set_voltage(self, voltage, channel=None):
        """
        设置指定通道的电压。
        
        :param voltage: 电压值 (V)
        :param channel: 通道号 (1-4)，如果为 None 则使用当前选中的通道
        """
        ch = channel if channel is not None else self._current_channel
        self._write(f"SOUR:VOLT:SET CH{ch},{voltage:.3f}")
        self.logger.info(f"通道 {ch} 电压已设置为 {voltage:.3f}V")

    def set_current(self, current, channel=None):
        """
        设置指定通道的电流限制。
        
        :param current: 电流值 (A)
        :param channel: 通道号 (1-4)，如果为 None 则使用当前选中的通道
        """
        ch = channel if channel is not None else self._current_channel
        self._write(f"SOUR:CURR:SET CH{ch},{current:.3f}")
        self.logger.info(f"通道 {ch} 电流已设置为 {current:.3f}A")

    def set_ovp(self, ovp_value, channel=None):
        """
        设置指定通道的过压保护值。
        
        :param ovp_value: OVP 电压值 (V)
        :param channel: 通道号 (1-4)
        """
        ch = channel if channel is not None else self._current_channel
        self._write(f"SOUR:OVP CH{ch},{ovp_value:.3f}")
        self.logger.info(f"通道 {ch} OVP 已设置为 {ovp_value:.3f}V")

    def set_ocp(self, ocp_value, channel=None):
        """
        设置指定通道的过流保护值。
        
        :param ocp_value: OCP 电流值 (A)
        :param channel: 通道号 (1-4)
        """
        ch = channel if channel is not None else self._current_channel
        self._write(f"SOUR:OCP CH{ch},{ocp_value:.3f}")
        self.logger.info(f"通道 {ch} OCP 已设置为 {ocp_value:.3f}A")

    def set_ocp_state(self, state, channel=None):
        """
        设置指定通道的 OCP 状态（是否启用过流切断）。
        
        :param state: True 启用 OCP 切断，False 禁用
        :param channel: 通道号 (1-4)
        """
        ch = channel if channel is not None else self._current_channel
        val = 1 if state else 0
        self._write(f"SOUR:OCP:STAT CH{ch},{val}")
        self.logger.info(f"通道 {ch} OCP 状态已设置为 {'启用' if state else '禁用'}")

    # ========== 输出控制 ==========
    
    def turn_on(self, channel=None):
        """
        打开指定通道的输出。
        
        :param channel: 通道号 (1-4)，如果为 None 则使用当前选中的通道
        """
        ch = channel if channel is not None else self._current_channel
        self._write(f"OUTP CH{ch},1")
        self.logger.info(f"通道 {ch} 输出已打开")

    def turn_off(self, channel=None):
        """
        关闭指定通道的输出。
        
        :param channel: 通道号 (1-4)，如果为 None 则使用当前选中的通道
        """
        ch = channel if channel is not None else self._current_channel
        self._write(f"OUTP CH{ch},0")
        self.logger.info(f"通道 {ch} 输出已关闭")

    def output_on(self, channel=None):
        """
        标准接口：打开输出。
        这是 HardwareManager 调用的方法。
        """
        self.logger.info(f"调用标准接口 output_on()")
        self.turn_on(channel)

    def output_off(self, channel=None):
        """
        标准接口：关闭输出。
        """
        self.logger.info(f"调用标准接口 output_off()")
        self.turn_off(channel)

    # ========== 测量功能 ==========
    
    def measure_voltage(self, channel=None):
        """
        测量指定通道的实际输出电压。
        
        :param channel: 通道号 (1-4)
        :return: 电压值 (V)
        """
        ch = channel if channel is not None else self._current_channel
        response = self._query(f"MEAS:VOLT? CH{ch}")
        voltage = float(response.strip())
        self.logger.debug(f"通道 {ch} 测得电压: {voltage:.3f}V")
        return voltage

    def measure_current(self, channel=None):
        """
        测量指定通道的实际输出电流。
        
        :param channel: 通道号 (1-4)
        :return: 电流值 (A)
        """
        ch = channel if channel is not None else self._current_channel
        response = self._query(f"MEAS:CURR? CH{ch}")
        current = float(response.strip())
        self.logger.debug(f"通道 {ch} 测得电流: {current:.4f}A")
        return current

    def get_run_mode(self, channel=None):
        """
        获取指定通道当前的运行模式 (CV/CC/UR)。
        
        :param channel: 通道号 (1-4)
        :return: 模式字符串 ("CV", "CC", "UR" 等)
        """
        ch = channel if channel is not None else self._current_channel
        try:
            response = self._query(f"MEAS:RUN:MODE? CH{ch}")
            return response.strip()
        except Exception:
            return "ERR"

    def get_status(self, channel=None):
        """
        获取指定通道的完整状态（电压、电流、模式）。
        
        :param channel: 通道号 (1-4)
        :return: (voltage, current, mode) 元组
        """
        ch = channel if channel is not None else self._current_channel
        try:
            voltage = self.measure_voltage(ch)
            current = self.measure_current(ch)
            mode = self.get_run_mode(ch)
            return voltage, current, mode
        except Exception as e:
            self.logger.error(f"获取通道 {ch} 状态失败: {e}")
            return 0.0, 0.0, "ERR"

    # ========== 关闭连接 ==========
    
    def close(self):
        """
        安全关闭设备连接。
        关闭前会尝试关闭所有通道的输出。
        """
        with self.lock:
            if not self.is_connected():
                return
            try:
                self.logger.info(f"正在安全关闭设备 '{self.visa_address}'...")
                
                # 关闭所有通道的输出
                for ch in [1, 2, 3, 4]:
                    try:
                        self.instrument.write(f"OUTP CH{ch},0")
                        time.sleep(0.05)
                    except Exception as e:
                        self.logger.warning(f"关闭通道 {ch} 时发生错误 (可忽略): {e}")

                # 尝试返回本地模式
                try:
                    self.instrument.write(":SYSTem:LOCal")
                except Exception:
                    pass

                self.instrument.close()
                self.logger.info(f"设备 '{self.visa_address}' 连接已安全关闭。")
            except Exception as e:
                self.logger.error(f"关闭设备 '{self.visa_address}' 时发生错误: {e}")
            finally:
                self.instrument = None
