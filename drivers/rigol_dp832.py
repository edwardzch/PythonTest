# 文件路径: drivers/real/rigol_dp832.py
# (已添加标准接口方法)

import pyvisa
import threading
import logging
import time


# 定义一个我们自己的 ConnectionError 类，以便上层可以捕获
class ConnectionError(Exception):
    pass


class RigolDP832:
    # ========== 驱动元数据（插件化架构） ==========
    DRIVER_META = {
        "name": "RigolDP832",
        "display_name": "普源 DP832 三通道电源",
        "category": "power_supply",
        "interface": "visa",
        "channels": 3,
        "supports_shared_mode": True,
        "supports_independent_mode": True,
    }
    
    # ========== 配置 Tab 定义 ==========
    CONFIG_TAB = {
        "tab_name": "DP832 电源配置",
        "config_key": "dp832_config",
        "mode": "shared",  # 共享模式（多工位共用）
    }
    
    # ========== 配置 Schema ==========
    CONFIG_SCHEMA = {
        "visa_address": {
            "type": "visa",
            "label": "VISA 地址",
            "default": "USB0::...",
            "tooltip": "例如: USB0::0x1AB1::0x0E11::..."
        },
        "auto_connect_on_startup": {
            "type": "bool",
            "label": "启动时连接",
            "default": True
        }
    }

    def __init__(self, visa_address, logger=None):
        """
        初始化驱动，只保存配置，不进行连接。
        """
        self.visa_address = visa_address
        self.instrument = None
        self.lock = threading.Lock()

        if logger:
            self.logger = logger
        else:
            self.logger = logging.getLogger(f"RigolDP832_{self.visa_address}")
            if not self.logger.handlers:
                logging.basicConfig(level=logging.INFO, format='%(asctime)s - [%(name)s] - %(levelname)s - %(message)s')

        self.logger.info(f"驱动 for RigolDP832 '{self.visa_address}' 已创建但未连接。")

    def connect(self):
        if self.instrument:
            self.logger.info(f"设备 '{self.visa_address}' 已连接，跳过重复连接。")
            return
        try:
            rm = pyvisa.ResourceManager()  # 使用默认后端
            self.instrument = rm.open_resource(self.visa_address)
            self.instrument.timeout = 5000  # 5 seconds
            idn = self.instrument.query('*IDN?')
            self.logger.info(f"成功连接到 Rigol DP832: {idn.strip()} at {self.visa_address}")
        except Exception as e:
            error_msg = f"连接到 Rigol DP832 ({self.visa_address}) 失败: {e}"
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
        self._check_connection()
        with self.lock:
            self.instrument.write(command)

    def _query(self, command):
        self._check_connection()
        with self.lock:
            return self.instrument.query(command)

    def select_channel(self, channel):
        """
        选择要操作的通道。这是 Rigol DP832 的关键命令。
        后续的 set_voltage, set_current, turn_on/off 都将作用于此通道。
        """
        self._write(f":INSTrument:NSELect {channel}")

    def set_voltage(self, voltage):
        """为当前选定的通道设置电压。"""
        self._write(f":SOURce:VOLTage {voltage:.3f}")

    def set_current(self, current):
        """为当前选定的通道设置电流。"""
        self._write(f":SOURce:CURRent {current:.3f}")

    def turn_on(self):
        """打开当前选定通道的输出。这是您原来的方法。"""
        self._write(":OUTPut:STATe ON")

    def turn_off(self):
        """关闭当前选定通道的输出。这是您原来的方法。"""
        self._write(":OUTPut:STATe OFF")

    # --- 【【【本次修改的核心】】】 ---
    # 添加标准接口方法，它们只是调用您已有的方法。

    def output_on(self):
        """
        标准接口：打开输出。
        这是 HardwareManager 调用的方法。它内部调用 turn_on()。
        """
        self.logger.info("调用标准接口 output_on(), 实际执行 turn_on()")
        self.turn_on()

    def output_off(self):
        """
        标准接口：关闭输出。
        它内部调用 turn_off()。
        """
        self.logger.info("调用标准接口 output_off(), 实际执行 turn_off()")
        self.turn_off()

    # --- -------------------------- ---

    def measure_voltage(self, channel):
        """
        测量指定通道的电压。
        注意: DP832的:MEAS?命令可以直接指定通道，无需预先select_channel。
        """
        return float(self._query(f":MEASure:VOLTage? CH{channel}"))

    def measure_current(self, channel):
        """测量指定通道的电流。"""
        return float(self._query(f":MEASure:CURRent? CH{channel}"))

    def close(self):
        with self.lock:
            if not self.is_connected():
                return
            try:
                self.logger.info(f"正在安全关闭设备 '{self.visa_address}'...")
                # 关闭前关闭所有通道的输出
                for ch in [1, 2, 3]:
                    try:
                        self.instrument.write(f":OUTPut CH{ch},OFF")
                        time.sleep(0.05)
                    except Exception as e:
                        self.logger.warning(f"关闭通道 {ch} 时发生错误 (可忽略): {e}")

                # 尝试返回本地模式，让前面板可操作
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

