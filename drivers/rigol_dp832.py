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
        "mode": "shared",
    }
    
    # ========== 配置 Schema（三模式切换：共享/独立/专用）==========
    CONFIG_SCHEMA = {
        "power_mode": {
            "type": "mode_switch",
            "label": "电源模式",
            "shared_label": "共享模式",
            "independent_label": "独立模式",
            "dedicated_label": "专用模式",
            "shared_config_key": "shared_config",
            "station_count": 4,
            
            # 共享模式的配置字段
            "shared_schema": {
                "visa_settings": {
                    "type": "visa_with_connect",
                    "label": "VISA 地址",
                    "default": "USB0::...",
                    "auto_connect_default": True
                },
                "channel_mappings": {
                    "type": "channel_config",
                    "label": "通道配置",
                    "channel_count": 3,
                    "max_voltage": 30,
                    "max_current": 3
                }
            },
            
            # 独立模式下每个工位的配置字段
            "independent_schema": {
                "visa_settings": {
                    "type": "visa_with_connect",
                    "label": "VISA 地址",
                    "default": "",
                    "auto_connect_default": True
                },
                "mappings": {
                    "type": "supply_channel_mapping",
                    "label": "供电通道映射",
                    "supply_types": {
                        "product": "产品供电",
                        "battery": "电池供电",
                        "daq": "采集卡供电"
                    },
                    "max_channels": 3
                },
                "channel_mappings": {
                    "type": "channel_config",
                    "label": "通道配置",
                    "channel_count": 3,
                    "max_voltage": 30,
                    "max_current": 3
                }
            },
            
            # 专用模式的配置字段（两台电源 + 映射）
            "dedicated_schema": {
                "psu_config": {
                    "type": "multi_psu_config",
                    "label": "专用电源配置",
                    "psu_ids": ["PSU_1", "PSU_2"],
                    "supply_types": {
                        "battery_supply": "电池供电",
                        "daq_supply": "采集卡供电"
                    },
                    "station_count": 4,
                    "max_channels": 3
                }
            }
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
        
        # 【关键修复】优先使用 NI-VISA 后端（车间电脑通常安装了 NI-VISA）
        # 只在 NI-VISA 不可用时才回退到 pyvisa-py
        backends_to_try = [
            ('', 'NI-VISA'),           # 默认后端（NI-VISA）
            ('@py', 'pyvisa-py'),      # 纯 Python 后端（需要 libusb）
        ]
        
        last_error = None
        for backend, backend_name in backends_to_try:
            try:
                if backend:
                    rm = pyvisa.ResourceManager(backend)
                else:
                    rm = pyvisa.ResourceManager()
                
                self.logger.info(f"尝试使用 {backend_name} 后端连接...")
                self.instrument = rm.open_resource(self.visa_address)
                self.instrument.timeout = 5000  # 5 seconds
                idn = self.instrument.query('*IDN?')
                self.logger.info(f"成功连接到 Rigol DP832: {idn.strip()} at {self.visa_address} (后端: {backend_name})")
                return  # 连接成功，直接返回
                
            except Exception as e:
                last_error = e
                self.logger.warning(f"{backend_name} 后端连接失败: {e}")
                self.instrument = None
                continue
        
        # 所有后端都失败
        error_msg = f"连接到 Rigol DP832 ({self.visa_address}) 失败: {last_error}"
        self.logger.error(error_msg, exc_info=True)
        raise ConnectionError(error_msg) from last_error

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

