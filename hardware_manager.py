# 文件路径: hardware_manager.py (在您的版本上添加了启动设置)

import logging
import threading
import importlib
import serial
from sniffer import sniffer_instance



class HardwareError(Exception): pass


class ConnectionError(Exception): pass


class SynchronizedModbusCommunicator:
    def __init__(self, real_communicator, lock, port_name):
        self._communicator = real_communicator
        self._lock = lock
        self._port_name = port_name

    def __getattr__(self, name):
        attr = getattr(self._communicator, name)
        if callable(attr):
            def locked_method(*args, **kwargs):
                with self._lock:
                    return attr(*args, **kwargs)

            return locked_method
        else:
            return attr


class HardwareManager:
    def __init__(self, global_config, driver_plugins={}):
        self.config = global_config
        self.driver_plugins = driver_plugins
        self.devices = {}
        self.comm_port_locks = {}
        self.raw_serial_handles = {}
        self.device_registry = {}  # 设备注册表
        self._load_device_registry()  # 加载设备注册表
        logging.info("硬件管理器已创建。")

    def _load_device_registry(self):
        """
        从 device_registry.json 加载设备注册表。
        这使得用户可以在不修改主程序的情况下添加新设备。
        """
        import os
        import json
        from utils.app_utils import get_app_base_path
        
        registry_path = os.path.join(get_app_base_path(), 'device_registry.json')
        if os.path.exists(registry_path):
            try:
                with open(registry_path, 'r', encoding='utf-8') as f:
                    self.device_registry = json.load(f)
                logging.info(f"已加载设备注册表: {len(self.device_registry.get('devices', {}))} 个设备")
            except Exception as e:
                logging.error(f"加载设备注册表失败: {e}")
                self.device_registry = {"devices": {}}
        else:
            logging.info("设备注册表不存在，使用空注册表")
            self.device_registry = {"devices": {}}

    def _get_driver_class(self, driver_name):
        """
        动态反射获取驱动类，完全无需硬编码。
        支持:
        1. 纯类名: 如 'ElectronicLoadDriver', 'SiglentSPD4323X'
        2. 模块+类名: 如 'electronic_load.ElectronicLoadDriver'
        3. 遍历 driver_plugins 反射匹配
        """
        target_class_name = driver_name.split('.')[-1]
        target_mod_name = driver_name.split('.')[0] if '.' in driver_name else None

        # 1. 优先在已加载的驱动插件中查找
        for mod_name, plugin in self.driver_plugins.items():
            if target_mod_name and mod_name != target_mod_name:
                continue
            if hasattr(plugin, target_class_name):
                attr = getattr(plugin, target_class_name)
                if isinstance(attr, type):
                    return attr

        # 2. 如果指定了纯类名，遍历所有插件模块中的类（支持大小写不敏感容错）
        for mod_name, plugin in self.driver_plugins.items():
            for attr_name in dir(plugin):
                if attr_name.lower() == target_class_name.lower():
                    attr = getattr(plugin, attr_name)
                    if isinstance(attr, type):
                        return attr

        # 3. 兼容旧驱动显式导入
        if driver_name == 'CustomModbusDriver':
            from drivers.custom_modbus_driver import CustomModbusDriver
            return CustomModbusDriver
        if driver_name == 'RelayBoardDriver':
            from drivers.relay_board_driver import RelayBoardDriver
            return RelayBoardDriver

        # 4. Fallback: 尝试动态导入
        try:
            import importlib
            # 尝试作为 drivers.<driver_name> 或 drivers.<mod>.<Class>
            if '.' in driver_name:
                mod_part, cls_part = driver_name.rsplit('.', 1)
                mod = importlib.import_module(f"drivers.{mod_part}")
                if hasattr(mod, cls_part):
                    return getattr(mod, cls_part)
            else:
                mod = importlib.import_module(f"drivers.{driver_name}")
                if hasattr(mod, driver_name):
                    return getattr(mod, driver_name)
        except Exception:
            pass

        raise HardwareError(f"无法从任何插件中加载驱动: {driver_name}")

    def _create_device_from_registry(self, device_id):
        """
        根据设备注册表创建设备实例。
        
        :param device_id: 设备ID
        :return: 设备实例，如果创建失败则返回 None
        """
        device_def = self.device_registry.get('devices', {}).get(device_id)
        if not device_def:
            logging.warning(f"设备注册表中未找到设备: {device_id}")
            return None
        
        if not device_def.get('enabled', True):
            logging.info(f"设备 {device_id} 已禁用，跳过创建")
            return None
        
        driver_name = device_def.get('driver')
        if not driver_name:
            logging.error(f"设备 {device_id} 未指定驱动类名")
            return None
        
        try:
            DriverClass = self._get_driver_class(driver_name)
            config = device_def.get('config', {})
            
            # 根据驱动接口类型创建实例
            meta = getattr(DriverClass, 'DRIVER_META', {})
            interface_type = meta.get('interface', 'visa')
            
            if interface_type == 'visa':
                visa_address = config.get('visa_address', '')
                instance = DriverClass(visa_address=visa_address)
            elif interface_type == 'serial':
                port = config.get('port', '')
                instance = DriverClass(port=port, **config)
            else:
                # 通用方式创建
                instance = DriverClass(**config)
            
            self.devices[device_id] = instance
            logging.info(f"已从注册表创建设备: {device_id} (驱动: {driver_name})")
            return instance
            
        except Exception as e:
            logging.error(f"从注册表创建设备 {device_id} 失败: {e}")
            return None

    def get_registered_device(self, device_id, auto_connect=True):
        """
        获取注册表中的设备，如果未创建则自动创建并连接。
        
        :param device_id: 设备ID
        :param auto_connect: 是否自动连接
        :return: 设备实例
        """
        if device_id in self.devices:
            return self.devices[device_id]
        
        device = self._create_device_from_registry(device_id)
        if device and auto_connect:
            try:
                if hasattr(device, 'connect'):
                    device.connect()
            except Exception as e:
                logging.error(f"连接设备 {device_id} 失败: {e}")
        
        return device

    def load_and_connect_auto_devices(self):
        """
        加载并连接配置为“自动启动”的设备，并应用启动设置。
        """
        logging.info("========== 开始自动加载并连接硬件 ==========")
        error_messages = []

        serial_mode_cfg = self.config.get('serial_port_mode', {})
        if serial_mode_cfg.get('use_shared_port', False):
            logging.info("--- 检测到共享串口模式，正在自动连接... ---")
            shared_cfg = serial_mode_cfg.get('shared_port_config', {})
            port_name = shared_cfg.get('port')
            if port_name:
                is_simulated = shared_cfg.get('simulation_mode', False)
                params = shared_cfg.get('serial_params', {})
                try:
                    self.initialize_and_connect_serial(port_name, params, is_simulated)
                except Exception as e:
                    msg = f"共享串口 {port_name}: 连接失败 - {e}"
                    logging.error(msg)
                    error_messages.append(msg)
            else:
                logging.warning("配置为共享串口模式，但未在共享配置中指定串口号。")
        else:
            logging.info("--- 检测到独立串口模式，启动时不自动连接串口。---")

        psu_configs = self.config.get('power_supplies', {})
        for psu_id, psu_info in psu_configs.items():
            if psu_id == "simulation_mode" or not isinstance(psu_info, dict):
                continue
            if psu_info.get('auto_connect_on_startup', False):
                try:
                    self.get_psu(psu_id)
                except Exception as e:
                    visa_address = psu_info.get('visa_address', '未知地址')
                    msg = f"程控电源 {psu_id} ({visa_address}): 连接失败 - {e}"
                    logging.error(msg)
                    error_messages.append(msg)

        # --- 【【【本次修改的核心】】】 ---
        # 在所有设备都尝试连接后，应用电源启动设置
        startup_errors = self._apply_power_startup_settings()
        error_messages.extend(startup_errors)

        # 自动连接各工位的万用表（从 dmm_config 读取，与 DP832 模式一致）
        dmm_errors = self._load_and_connect_dmm()
        error_messages.extend(dmm_errors)

        # --- 从设备注册表加载设备（插件化架构）---
        registry_devices = self.device_registry.get('devices', {})
        if registry_devices:
            logging.info(f"--- 正在从设备注册表加载 {len(registry_devices)} 个设备... ---")
            for device_id, device_def in registry_devices.items():
                if not device_def.get('enabled', True):
                    continue
                config = device_def.get('config', {})
                if config.get('auto_connect_on_startup', False):
                    try:
                        device = self.get_registered_device(device_id, auto_connect=True)
                        if device:
                            # 应用注册表中的启动设置（电压/电流等）
                            self._apply_registry_device_startup_settings(device_id, device, device_def)
                    except Exception as e:
                        driver_name = device_def.get('driver', '未知驱动')
                        msg = f"注册表设备 {device_id} ({driver_name}): 连接失败 - {e}"
                        logging.error(msg)
                        error_messages.append(msg)

        # --- DP832 电源自动连接（独立模式）---
        dp832_errors = self._load_and_connect_dp832()
        error_messages.extend(dp832_errors)

        # --- SPD4323X 电源自动连接 ---
        spd_errors = self._load_and_connect_spd4323x()
        error_messages.extend(spd_errors)

        # --- Modbus 自定义仪器/板卡自动连接 ---
        custom_modbus_errors = self._load_and_connect_custom_modbus()
        error_messages.extend(custom_modbus_errors)

        # --- USB 继电器板自动连接 ---
        relay_board_errors = self._load_and_connect_relay_board()
        error_messages.extend(relay_board_errors)

        logging.info("========== 自动加载和连接完成 ==========")
        return error_messages

    def _apply_registry_device_startup_settings(self, device_id, device, device_def):
        """
        应用注册表中设备的启动设置（电压、电流、输出等）。
        
        :param device_id: 设备ID
        :param device: 设备实例
        :param device_def: 设备定义（来自注册表）
        """
        channel_mappings = device_def.get('channel_mappings', {})
        if not channel_mappings:
            return
        
        logging.info(f"正在应用设备 {device_id} 的启动设置...")
        
        for mapping_key, settings in channel_mappings.items():
            channel = settings.get('channel')
            if channel is None:
                continue
            
            try:
                # 设置电压
                voltage = settings.get('voltage')
                if voltage is not None and hasattr(device, 'set_voltage'):
                    device.set_voltage(voltage, channel)
                
                # 设置电流
                current = settings.get('current')
                if current is not None and hasattr(device, 'set_current'):
                    device.set_current(current, channel)
                
                # 输出控制
                enable_on_startup = settings.get('enable_on_startup', False)
                if enable_on_startup:
                    if hasattr(device, 'output_on'):
                        device.output_on(channel)
                    elif hasattr(device, 'turn_on'):
                        device.turn_on(channel)
                        
                logging.info(f"  通道 {channel}: V={voltage}, I={current}, 输出={'开启' if enable_on_startup else '关闭'}")
                
            except Exception as e:
                logging.warning(f"应用设备 {device_id} 通道 {channel} 设置失败: {e}")

    def _load_and_connect_dp832(self):
        """
        加载并连接 DP832 电源，根据配置的模式（共享/独立/专用）。
        - 共享模式：由 power_supplies 顶层配置处理
        - 独立模式：从 dp832_config.power_mode.independent_configs 读取各工位配置
        - 专用模式：从 dp832_config.power_mode.dedicated_config 读取多台电源配置
        """
        error_messages = []
        dp832_config_root = self.config.get('dp832_config', {})
        
        if not dp832_config_root:
            logging.info("未找到 DP832 配置 (dp832_config)，跳过。")
            return error_messages
        
        dp832_config = dp832_config_root.get('power_mode', dp832_config_root)
        mode = dp832_config.get('mode', 'shared')
        use_independent = dp832_config.get('use_independent_mode', False)
        
        # 兼容：如果没有 mode 字段，通过 use_independent_mode 判断
        if mode == 'shared' and use_independent:
            mode = 'independent'
        
        logging.info(f"DP832 电源模式: {mode}")
        
        if mode == 'independent':
            logging.info("--- DP832: 独立模式 ---")
            independent_cfgs = dp832_config.get('independent_configs', {})
            
            for station_id, ind_cfg in independent_cfgs.items():
                visa_settings = ind_cfg.get('visa_settings', {})
                if isinstance(visa_settings, dict):
                    visa_address = visa_settings.get('visa_address', '')
                    auto_connect = visa_settings.get('auto_connect_on_startup', False)
                else:
                    visa_address = ind_cfg.get('visa_address', '')
                    auto_connect = ind_cfg.get('auto_connect_on_startup', False)
                
                if not visa_address:
                    continue
                    
                if auto_connect:
                    device_id = f"psu_{station_id}"
                    try:
                        self._create_and_connect_dp832(device_id, visa_address)
                        
                        # 应用 channel_mappings 通道启动设置
                        channel_mappings = ind_cfg.get('channel_mappings', {})
                        self._apply_dp832_channel_startup(device_id, channel_mappings)
                        
                    except Exception as e:
                        msg = f"DP832 {station_id} ({visa_address}): 连接失败 - {e}"
                        logging.error(msg)
                        error_messages.append(msg)
        
        elif mode == 'dedicated':
            # 专用模式：从 dedicated_config.psu_config 读取多台电源配置
            logging.info("--- DP832: 专用模式 ---")
            
            dedicated_cfg = dp832_config.get('dedicated_config', {})
            psu_config = dedicated_cfg.get('psu_config', {})
            power_supplies = psu_config.get('power_supplies', {})
            
            # 1. 连接各电源设备
            for psu_id, psu_info in power_supplies.items():
                visa_address = psu_info.get('visa_address', '')
                auto_connect = psu_info.get('auto_connect_on_startup', False)
                
                if not visa_address or visa_address == 'USB0::...':
                    continue
                
                if auto_connect:
                    device_id = f"dedicated_{psu_id}"
                    try:
                        self._create_and_connect_dp832(device_id, visa_address)
                        print(f"[DP832] ✅ {device_id} 连接成功")
                    except Exception as e:
                        msg = f"专用电源 {psu_id} ({visa_address}): 连接失败 - {e}"
                        print(f"[DP832] ❌ {msg}")
                        logging.error(msg)
                        error_messages.append(msg)
            
            # 2. 应用电源启动设置（电池供电、采集卡供电等）
            power_startup_settings = psu_config.get('power_startup_settings', {})
            for supply_name, settings in power_startup_settings.items():
                if not settings.get('enabled', False):
                    continue
                
                psu_id = settings.get('psu_id')
                channel = settings.get('channel')
                voltage = settings.get('voltage')
                current = settings.get('current')
                
                if not all([psu_id, channel is not None]):
                    continue
                
                device_id = f"dedicated_{psu_id}"
                psu = self.devices.get(device_id)
                if not psu:
                    logging.warning(f"{supply_name}: 电源 {psu_id} 未连接，跳过")
                    continue
                
                try:
                    psu.select_channel(channel)
                    if voltage is not None:
                        psu.set_voltage(voltage)
                    if current is not None:
                        psu.set_current(current)
                    psu.output_on()
                    print(f"[DP832] ✅ {supply_name}: {psu_id} CH{channel} -> {voltage}V, {current}A, 已打开")
                    logging.info(f"专用模式 {supply_name}: {psu_id} CH{channel} -> {voltage}V, {current}A, 已打开")
                except Exception as e:
                    msg = f"专用模式启动设置 {supply_name} 失败: {e}"
                    print(f"[DP832] ❌ {msg}")
                    logging.warning(msg)
        
        else:
            # 共享模式
            logging.info("--- DP832: 共享模式 ---")
            
            shared_cfg = dp832_config.get('shared_config', {})
            visa_settings = shared_cfg.get('visa_settings', {})
            if isinstance(visa_settings, dict):
                visa_address = visa_settings.get('visa_address', '')
                auto_connect = visa_settings.get('auto_connect_on_startup', False)
            else:
                visa_address = ''
                auto_connect = False
            
            if visa_address and visa_address != 'USB0::...' and auto_connect:
                psu_configs = self.config.get('power_supplies', {})
                if not psu_configs:
                    device_id = "dp832_shared"
                    try:
                        self._create_and_connect_dp832(device_id, visa_address)
                        print(f"[DP832] ✅ 共享模式 {device_id} 连接成功")
                        
                        # 应用 channel_mappings 通道启动设置
                        channel_mappings = shared_cfg.get('channel_mappings', {})
                        self._apply_dp832_channel_startup(device_id, channel_mappings)
                    except Exception as e:
                        msg = f"DP832 共享模式 ({visa_address}): 连接失败 - {e}"
                        print(f"[DP832] ❌ {msg}")
                        logging.error(msg)
                        error_messages.append(msg)
        
        return error_messages

    def _create_and_connect_dp832(self, device_id, visa_address):
        """
        创建并连接 DP832 设备实例。
        """
        if device_id in self.devices:
            self.connect_device(device_id)
            return self.devices[device_id]
        
        logging.info(f"正在创建 DP832 设备: {device_id} ({visa_address})")
        driver_name = 'RigolDP832'
        DriverClass = self._get_driver_class(driver_name)
        
        instance = DriverClass(visa_address=visa_address)
        self.devices[device_id] = instance
        self.connect_device(device_id)
        return instance

    def _apply_dp832_channel_startup(self, device_id, channel_mappings):
        """
        应用 DP832 通道启动设置（电压、电流、打开输出）。
        channel_mappings 格式: {"CH1": {"voltage": 5.0, "current": 1.0, "enable_on_startup": true}, ...}
        """
        psu = self.devices.get(device_id)
        if not psu or not channel_mappings:
            return
        
        for ch_key, ch_cfg in channel_mappings.items():
            # 从 "CH1" / "CH2" / "CH3" 提取通道号
            try:
                ch_num = int(ch_key.replace('CH', '').replace('ch', ''))
            except (ValueError, AttributeError):
                continue
            
            voltage = ch_cfg.get('voltage', 5.0)
            current = ch_cfg.get('current', 1.0)
            enable = ch_cfg.get('enable_on_startup', False)
            
            try:
                psu.select_channel(ch_num)
                psu.set_voltage(voltage)
                psu.set_current(current)
                if enable:
                    psu.output_on()
                    print(f"[DP832-HW]   ✅ {device_id} {ch_key}: {voltage}V, {current}A, 已打开")
                    logging.info(f"DP832 {device_id} {ch_key}: 启动设置 {voltage}V, {current}A, 已打开")
                else:
                    logging.info(f"DP832 {device_id} {ch_key}: 设置 {voltage}V, {current}A (未启用输出)")
            except Exception as e:
                print(f"[DP832-HW]   ❌ {device_id} {ch_key} 启动设置失败: {e}")
                logging.warning(f"DP832 {device_id} {ch_key} 启动设置失败: {e}")

    def _load_and_connect_dmm(self):
        """
        加载并连接万用表，根据配置的模式（共享/独立）。
        配置结构与 DP832 一致：dmm_config.dmm_mode.{shared_config/independent_configs}
        """
        error_messages = []
        dmm_config_root = self.config.get('dmm_config', {})
        
        if not dmm_config_root:
            logging.info("未找到 dmm_config 配置，跳过万用表自动连接。")
            return error_messages
        
        dmm_mode_config = dmm_config_root.get('dmm_mode', {})
        use_independent = dmm_mode_config.get('use_independent_mode', False)
        
        if use_independent:
            logging.info("--- 万用表: 独立模式 ---")
            ind_cfgs = dmm_mode_config.get('independent_configs', {})
            
            for station_id, ind_cfg in ind_cfgs.items():
                visa_settings = ind_cfg.get('visa_settings', {})
                if isinstance(visa_settings, dict):
                    visa_address = visa_settings.get('visa_address', '')
                    auto_connect = visa_settings.get('auto_connect_on_startup', False)
                else:
                    visa_address = ind_cfg.get('visa_address', '')
                    auto_connect = ind_cfg.get('auto_connect_on_startup', False)
                
                if not visa_address:
                    continue
                
                if auto_connect:
                    try:
                        self.get_station_instrument('dmm', station_id)
                    except Exception as e:
                        msg = f"万用表 {station_id} ({visa_address}): 连接失败 - {e}"
                        logging.error(msg)
                        error_messages.append(msg)
        else:
            logging.info("--- 万用表: 共享模式 ---")
            shared_cfg = dmm_mode_config.get('shared_config', {})
            visa_settings = shared_cfg.get('visa_settings', {})
            if isinstance(visa_settings, dict):
                visa_address = visa_settings.get('visa_address', '')
                auto_connect = visa_settings.get('auto_connect_on_startup', False)
            else:
                visa_address = shared_cfg.get('visa_address', '')
                auto_connect = shared_cfg.get('auto_connect_on_startup', False)
            
            if visa_address and auto_connect:
                # 共享模式下，为所有启用的工位创建同一个连接
                # 使用 station_1 作为共享实例的 station_id
                try:
                    self.get_station_instrument('dmm', 'station_1')
                    logging.info(f"共享万用表 ({visa_address}): 连接成功")
                except Exception as e:
                    msg = f"共享万用表 ({visa_address}): 连接失败 - {e}"
                    logging.error(msg)
                    error_messages.append(msg)
        
        return error_messages

    def _load_and_connect_spd4323x(self):
        """
        加载并连接 SPD4323X 电源，根据配置的模式（共享/独立）。
        """
        error_messages = []
        spd_config_root = self.config.get('spd4323x_config', {})
        
        if not spd_config_root:
            logging.info("未找到 SPD4323X 配置，跳过。")
            return error_messages
        
        # 【关键修复】配置结构是 spd4323x_config.power_mode.xxx，需要读取 power_mode 嵌套层
        spd_config = spd_config_root.get('power_mode', spd_config_root)  # 兼容旧格式
        
        use_independent = spd_config.get('use_independent_mode', False)
        
        if use_independent:
            # 独立模式：每个工位有自己的 SPD4323X
            logging.info("--- SPD4323X: 独立模式 ---")
            independent_cfgs = spd_config.get('independent_configs', {})
            
            for station_id, ind_cfg in independent_cfgs.items():
                # 【关键修复】从 visa_settings 嵌套字典中读取 VISA 地址和自动连接设置
                visa_settings = ind_cfg.get('visa_settings', {})
                if isinstance(visa_settings, dict):
                    visa_address = visa_settings.get('visa_address', '')
                    auto_connect = visa_settings.get('auto_connect_on_startup', False)
                else:
                    # 兼容旧格式
                    visa_address = ind_cfg.get('visa_address', '')
                    auto_connect = ind_cfg.get('auto_connect_on_startup', False)
                
                if not visa_address:
                    continue
                    
                if auto_connect:
                    device_id = f"spd4323x_{station_id}"
                    try:
                        self._create_and_connect_spd4323x(device_id, visa_address)
                        # 应用通道启动设置
                        channels_cfg = ind_cfg.get('channels', {})
                        psu = self.devices.get(device_id)
                        if psu:
                            for ch, ch_cfg in channels_cfg.items():
                                if ch_cfg.get('enable_on_startup', False):
                                    voltage = ch_cfg.get('voltage', 5.0)
                                    current = ch_cfg.get('current', 1.0)
                                    psu.set_voltage(voltage, int(ch))
                                    psu.set_current(current, int(ch))
                                    psu.turn_on(int(ch))
                                    logging.info(f"SPD4323X {device_id} CH{ch}: 启动设置 {voltage}V, {current}A, 已打开")
                    except Exception as e:
                        msg = f"SPD4323X {device_id} ({visa_address}): 连接失败 - {e}"
                        logging.error(msg)
                        error_messages.append(msg)
        else:
            # 共享模式：一台 SPD4323X 给所有工位用
            logging.info("--- SPD4323X: 共享模式 ---")
            shared_cfg = spd_config.get('shared_config', {})
            
            # 【关键修复】从 visa_settings 嵌套字典中读取 VISA 地址和自动连接设置
            visa_settings = shared_cfg.get('visa_settings', {})
            if isinstance(visa_settings, dict):
                visa_address = visa_settings.get('visa_address', '')
                auto_connect = visa_settings.get('auto_connect_on_startup', False)
            else:
                # 兼容旧格式
                visa_address = shared_cfg.get('visa_address', '')
                auto_connect = shared_cfg.get('auto_connect_on_startup', False)
            
            if visa_address and auto_connect:
                device_id = "spd4323x_shared"
                try:
                    self._create_and_connect_spd4323x(device_id, visa_address)
                    # 应用通道-工位映射的启动设置
                    channel_mappings = shared_cfg.get('channel_mappings', {})
                    psu = self.devices.get(device_id)
                    if psu:
                        for station_id, mapping in channel_mappings.items():
                            if mapping.get('enable_on_startup', False):
                                channel = mapping.get('channel', 1)
                                voltage = mapping.get('voltage', 5.0)
                                current = mapping.get('current', 1.0)
                                psu.set_voltage(voltage, channel)
                                psu.set_current(current, channel)
                                psu.turn_on(channel)
                                logging.info(f"SPD4323X 共享 CH{channel} ({station_id}): 启动设置 {voltage}V, {current}A, 已打开")
                except Exception as e:
                    msg = f"SPD4323X 共享 ({visa_address}): 连接失败 - {e}"
                    logging.error(msg)
                    error_messages.append(msg)
        
        return error_messages

    def _create_and_connect_spd4323x(self, device_id, visa_address):
        """
        创建并连接 SPD4323X 设备实例。
        """
        if device_id in self.devices:
            self.connect_device(device_id)
            return self.devices[device_id]
        
        logging.info(f"正在创建 SPD4323X 设备: {device_id} ({visa_address})")
        driver_name = 'SiglentSPD4323X'
        DriverClass = self._get_driver_class(driver_name)
        
        instance = DriverClass(visa_address=visa_address)
        self.devices[device_id] = instance
        self.connect_device(device_id)
        return instance

    def get_spd4323x(self, station_id=None):
        """
        获取 SPD4323X 电源句柄。
        
        :param station_id: 工位ID（仅在独立模式下需要）
        :return: SPD4323X 驱动实例
        """
        spd_config_root = self.config.get('spd4323x_config', {})
        # 【关键修复】读取 power_mode 嵌套层
        spd_config = spd_config_root.get('power_mode', spd_config_root)
        use_independent = spd_config.get('use_independent_mode', False)
        
        if use_independent:
            if not station_id:
                raise HardwareError("独立模式下必须指定 station_id 参数")
            device_id = f"spd4323x_{station_id}"
            ind_cfgs = spd_config.get('independent_configs', {})
            ind_cfg = ind_cfgs.get(station_id, {})
            # 【关键修复】从 visa_settings 嵌套字典读取 VISA 地址
            visa_settings = ind_cfg.get('visa_settings', {})
            if isinstance(visa_settings, dict):
                visa_address = visa_settings.get('visa_address', '')
            else:
                visa_address = ind_cfg.get('visa_address', '')
        else:
            device_id = "spd4323x_shared"
            shared_cfg = spd_config.get('shared_config', {})
            # 【关键修复】从 visa_settings 嵌套字典读取 VISA 地址
            visa_settings = shared_cfg.get('visa_settings', {})
            if isinstance(visa_settings, dict):
                visa_address = visa_settings.get('visa_address', '')
            else:
                visa_address = shared_cfg.get('visa_address', '')
        
        if device_id in self.devices:
            self.connect_device(device_id)
            return self.devices[device_id]
        
        if not visa_address:
            raise HardwareError(f"SPD4323X ({device_id}) 未配置 VISA 地址")
        
        return self._create_and_connect_spd4323x(device_id, visa_address)

    def _load_and_connect_custom_modbus(self):
        """
        加载并连接自定义 Modbus 仪器/板卡，根据配置的模式（共享/独立）。
        """
        error_messages = []
        custom_modbus_cfg_root = self.config.get('custom_modbus_config') or self.config.get('relay_config') or {}
        if not custom_modbus_cfg_root:
            logging.info("未找到自定义 Modbus 配置 (custom_modbus_config)，跳过。")
            return error_messages

        mode_cfg = custom_modbus_cfg_root.get('device_mode') or custom_modbus_cfg_root.get('relay_mode') or custom_modbus_cfg_root
        mode = mode_cfg.get('mode', 'shared')
        use_independent = mode_cfg.get('use_independent_mode', False)
        if mode == 'shared' and use_independent:
            mode = 'independent'

        logging.info(f"自定义 Modbus 仪器模式: {mode}")

        try:
            DriverClass = self._get_driver_class('CustomModbusDriver')
        except Exception as e:
            logging.warning(f"未能加载 CustomModbusDriver: {e}")
            return error_messages

        if mode == 'independent':
            ind_cfgs = mode_cfg.get('independent_configs', {})
            for station_id, ind_cfg in ind_cfgs.items():
                port = ind_cfg.get('port')
                if not port:
                    continue
                device_id = f"custom_modbus_{station_id}"
                try:
                    driver_inst = DriverClass(**ind_cfg)
                    self.devices[device_id] = driver_inst
                    logging.info(f"独立 Modbus 仪器配置已就绪 ({device_id}, {port})")
                except Exception as e:
                    logging.warning(f"独立 Modbus 仪器 ({device_id}, {port}) 初始化异常: {e}")
        else:
            shared_cfg = mode_cfg.get('shared_config', {})
            port = shared_cfg.get('port')
            if port:
                device_id = "custom_modbus_shared"
                try:
                    driver_inst = DriverClass(**shared_cfg)
                    self.devices[device_id] = driver_inst
                    logging.info(f"共享 Modbus 仪器配置已就绪 ({port})")
                except Exception as e:
                    logging.warning(f"共享 Modbus 仪器 ({port}) 初始化异常: {e}")

        return error_messages

    def get_custom_modbus_driver(self, station_id="station_1"):
        """
        获取指定工位的自定义 Modbus 驱动句柄。
        共享模式下返回全局单例（内部自带线程互斥锁），独立模式下返回工位专属实例。
        """
        custom_modbus_cfg_root = self.config.get('custom_modbus_config') or self.config.get('relay_config') or {}
        mode_cfg = custom_modbus_cfg_root.get('device_mode') or custom_modbus_cfg_root.get('relay_mode') or custom_modbus_cfg_root
        mode = mode_cfg.get('mode', 'shared')
        use_independent = mode_cfg.get('use_independent_mode', False)
        if mode == 'shared' and use_independent:
            mode = 'independent'

        device_id = f"custom_modbus_{station_id}" if mode == 'independent' else "custom_modbus_shared"

        if device_id in self.devices:
            return self.devices[device_id]

        # 未初始化则按需创建
        DriverClass = self._get_driver_class('CustomModbusDriver')

        if mode == 'independent':
            ind_cfgs = mode_cfg.get('independent_configs', {})
            ind_cfg = ind_cfgs.get(station_id, {})
            port = ind_cfg.get('port')
            if not port:
                raise HardwareError(f"工位 '{station_id}' 未配置独立 Modbus 仪器串口。")
            driver_inst = DriverClass(**ind_cfg)
        else:
            shared_cfg = mode_cfg.get('shared_config', {})
            port = shared_cfg.get('port')
            if not port:
                raise HardwareError("共享 Modbus 仪器未配置串口号。请在配置编辑器中设置。")
            driver_inst = DriverClass(**shared_cfg)

        self.devices[device_id] = driver_inst
        return driver_inst

    def _load_and_connect_relay_board(self):
        """
        加载并初始化 USB 继电器板（非 Modbus 协议），根据配置的模式（共享/独立）。
        """
        error_messages = []
        relay_board_cfg_root = self.config.get('relay_board_config', {})
        if not relay_board_cfg_root:
            return error_messages

        mode_cfg = relay_board_cfg_root.get('device_mode', relay_board_cfg_root)
        mode = mode_cfg.get('mode', 'shared')
        use_independent = mode_cfg.get('use_independent_mode', False)
        if mode == 'shared' and use_independent:
            mode = 'independent'

        try:
            DriverClass = self._get_driver_class('RelayBoardDriver')
        except Exception as e:
            logging.warning(f"未能加载 RelayBoardDriver: {e}")
            return error_messages

        if mode == 'independent':
            ind_cfgs = mode_cfg.get('independent_configs', {})
            for station_id, ind_cfg in ind_cfgs.items():
                port = ind_cfg.get('port')
                if not port:
                    continue
                device_id = f"relay_board_{station_id}"
                try:
                    driver_inst = DriverClass(**ind_cfg)
                    self.devices[device_id] = driver_inst
                    logging.info(f"独立继电器板配置就绪 ({device_id}, {port})")
                except Exception as e:
                    logging.warning(f"独立继电器板 ({device_id}, {port}) 初始化异常: {e}")
        else:
            shared_cfg = mode_cfg.get('shared_config', {})
            port = shared_cfg.get('port')
            if port:
                device_id = "relay_board_shared"
                try:
                    driver_inst = DriverClass(**shared_cfg)
                    self.devices[device_id] = driver_inst
                    logging.info(f"共享继电器板配置就绪 ({port})")
                except Exception as e:
                    logging.warning(f"共享继电器板 ({port}) 初始化异常: {e}")

        return error_messages

    def get_relay_board_driver(self, station_id="station_1"):
        """
        获取指定工位的 USB 继电器板驱动句柄。
        共享模式下返回全局单例，独立模式下返回工位专属实例。
        """
        relay_board_cfg_root = self.config.get('relay_board_config', {})
        mode_cfg = relay_board_cfg_root.get('device_mode', relay_board_cfg_root)
        mode = mode_cfg.get('mode', 'shared')
        use_independent = mode_cfg.get('use_independent_mode', False)
        if mode == 'shared' and use_independent:
            mode = 'independent'

        device_id = f"relay_board_{station_id}" if mode == 'independent' else "relay_board_shared"

        if device_id in self.devices:
            dev = self.devices[device_id]
            return dev

        DriverClass = self._get_driver_class('RelayBoardDriver')

        if mode == 'independent':
            ind_cfgs = mode_cfg.get('independent_configs', {})
            ind_cfg = ind_cfgs.get(station_id, {})
            port = ind_cfg.get('port')
            if not port:
                raise HardwareError(f"工位 '{station_id}' 未配置独立继电器板串口。")
            driver_inst = DriverClass(**ind_cfg)
        else:
            shared_cfg = mode_cfg.get('shared_config', {})
            port = shared_cfg.get('port')
            if not port:
                raise HardwareError("共享继电器板未配置串口号。请在配置编辑器中设置。")
            driver_inst = DriverClass(**shared_cfg)

        self.devices[device_id] = driver_inst
        return driver_inst

    # 兼容别名
    def get_relay_driver(self, station_id="station_1"):
        return self.get_custom_modbus_driver(station_id)

    # --- 【【【新增的辅助方法】】】 ---
    def _apply_power_startup_settings(self):
        """
        读取 config.json 中的 power_startup_settings 并应用它们。
        这是一个私有方法，由 load_and_connect_auto_devices 调用。
        """
        startup_settings = self.config.get('power_startup_settings', {})
        error_messages = []
        if not startup_settings:
            logging.info("未找到 'power_startup_settings'，跳过电源启动设置。")
            return error_messages

        logging.info("========== 开始应用电源启动设置 ==========")
        # 获取电源的顶层定义，用于后续检查
        power_supplies_def = self.config.get('power_supplies', {})

        for supply_name, settings in startup_settings.items():
            if not settings.get('enabled'):
                # logging.info(f"'{supply_name}' 未启用，跳过。") # 这条日志太啰嗦，可以注释掉
                continue

            psu_id = settings.get('psu_id')
            channel = settings.get('channel')
            voltage = settings.get('voltage')
            current = settings.get('current')

            # 【【【核心BUG修复逻辑】】】
            # 在尝试操作硬件之前，先检查其上游电源是否配置为“启动时连接”
            psu_def = power_supplies_def.get(psu_id, {})
            if not psu_def.get('auto_connect_on_startup', False):
                logging.warning(
                    f"跳过启动项 '{supply_name}'，因为它关联的电源 '{psu_id}' 没有勾选 '启动时连接'。"
                )
                continue
            # --- 修复结束 ---

            if not all([psu_id, channel is not None, voltage is not None, current is not None]):
                msg = f"电源启动设置 '{supply_name}' 配置不完整，跳过。"
                logging.error(msg)
                error_messages.append(msg)
                continue

            try:
                # 获取电源句柄，如果未连接会在这里报错
                psu_handle = self.get_psu(psu_id)
                if not psu_handle:
                    raise HardwareError(f"未能获取到电源 {psu_id} 的句柄。")

                logging.info(f"正在应用 '{supply_name}': {psu_id} Ch{channel} -> {voltage}V, {current}A")

                # 假设您的电源驱动有以下标准方法
                # 如果是多通道电源，先选择通道
                if hasattr(psu_handle, 'select_channel'):
                    psu_handle.select_channel(channel)

                # 设置电压和电流
                psu_handle.set_voltage(voltage)
                psu_handle.set_current(current)

                # 打开输出
                psu_handle.output_on()

                logging.info(f"成功: '{supply_name}' 已设置并打开。")

            except Exception as e:
                msg = f"应用 '{supply_name}' 设置时出错: {e}"
                logging.error(msg, exc_info=True)
                error_messages.append(msg)

        logging.info("========== 电源启动设置应用完成 ==========")
        return error_messages

    # --- -------------------------- ---

    def initialize_and_connect_serial(self, port_name, serial_params, is_simulated):
        with self.comm_port_locks.setdefault(port_name, threading.Lock()):
            if port_name in self.devices:
                logging.info(f"串口 {port_name} 已初始化，正在尝试重新连接...")
                self.connect_device(port_name)
                return True

            logging.info(f"--- 正在按需初始化并连接串口: {port_name} ---")
            try:
                # 移除 Mock 判断，直接使用 ModbusCommunicator
                # 如果 is_simulated 为 True，这里仍然加载真实驱动，但由于没有 Mock 驱动了，
                # 可能会连接失败。这是符合预期的，因为用户删除了 simulation 目录。
                modbus_driver_name = "ModbusCommunicator"
                ModbusDriverClass = self._get_driver_class(modbus_driver_name)
                modbus_instance = ModbusDriverClass(port=port_name, **serial_params)
                self.devices[port_name] = modbus_instance
                self.connect_device(port_name)
                return True
            except Exception as e:
                logging.error(f"按需初始化串口 {port_name} 失败: {e}", exc_info=True)
                raise HardwareError(f"初始化串口 {port_name} 失败: {e}") from e

    def connect_device(self, device_id):
        device = self.devices.get(device_id)
        if not device:
            raise HardwareError(f"尝试连接未知设备: {device_id}")

        try:
            # 检查is_connected方法是否存在且返回True
            if hasattr(device, 'is_connected') and device.is_connected():
                return True
            if not hasattr(device, 'connect'):
                logging.warning(f"设备 {device_id} 不支持 'connect' 方法。")
                return True

            logging.info(f"正在连接设备: {device_id}...")
            device.connect()

            if 'modbus' in str(type(device)).lower() and (instrument := getattr(device, 'instrument', None)):
                if (raw_handle := getattr(instrument, 'serial', None)) and isinstance(raw_handle,
                                                                                      serial.Serial) and raw_handle.is_open:
                    self.raw_serial_handles[device_id] = raw_handle
                    logging.info(f"成功为 {device_id} 提取了原始串口句柄。")

            logging.info(f"设备 {device_id} 连接成功。")
            return True
        except Exception as e:
            logging.error(f"连接设备 {device_id} 失败: {e}", exc_info=True)
            raise HardwareError(f"连接设备 {device_id} 失败: {e}") from e

    def disconnect_device(self, device_id, cleanup_instance=False):
        device = self.devices.get(device_id)
        if not device:
            logging.warning(f"请求断开不存在的设备: {device_id}")
            return True

        try:
            if hasattr(device, 'is_connected') and device.is_connected():
                if hasattr(device, 'close'):
                    logging.info(f"正在物理断开设备: {device_id}...")
                    device.close()
                    logging.info(f"设备 {device_id} 已物理断开。")
            else:
                logging.info(f"设备 {device_id} 已经是断开状态。")

            if device_id in self.raw_serial_handles:
                del self.raw_serial_handles[device_id]

            if cleanup_instance:
                del self.devices[device_id]
                logging.info(f"已从管理器中彻底移除设备实例: {device_id}")

            return True
        except Exception as e:
            logging.error(f"断开设备 {device_id} 时失败: {e}", exc_info=True)
            return False

    def close_all(self):
        logging.info("========== 开始彻底关闭所有硬件连接 ==========")
        for device_id in list(self.devices.keys()):
            self.disconnect_device(device_id, cleanup_instance=True)
        logging.info("========== 所有硬件已彻底关闭并清理完毕 ==========")

    def reconnect_all_auto_devices(self):
        """关闭所有连接，然后重新连接所有配置为自动启动的设备。"""
        self.close_all()
        # close_all会清空devices字典，所以下次调用get_psu等函数时会重新创建实例
        error_messages = self.load_and_connect_auto_devices()
        return error_messages

    def get_psu(self, psu_id):
        if psu_id in self.devices:
            self.connect_device(psu_id)
            return self.devices[psu_id]

        psu_configs = self.config.get('power_supplies', {})
        if not (psu_info := psu_configs.get(psu_id)):
            raise HardwareError(f"配置中找不到电源: {psu_id}")

        # 移除 simulation_mode 判断
        driver_name = psu_info.get('driver', 'RigolDP832')
        PsuDriverClass = self._get_driver_class(driver_name)

        # 兼容旧格式(字符串)和新格式(visa_settings字典)
        visa_val = psu_info.get('visa_address')
        if isinstance(visa_val, dict):
            visa_addr = visa_val.get('visa_address')
        else:
            visa_addr = visa_val
            # 如果没找到，尝试从 visa_settings 子项找
            if not visa_addr:
                 visa_settings = psu_info.get('visa_settings')
                 if isinstance(visa_settings, dict):
                     visa_addr = visa_settings.get('visa_address')

        psu_instance = PsuDriverClass(visa_address=visa_addr)
        self.devices[psu_id] = psu_instance
        self.connect_device(psu_id)
        return psu_instance

    def get_station_psu(self, station_id):
        """
        获取工位的电源句柄，根据电源模式（独立/共享/专用）选择正确的配置。
        """
        # 【读取 dp832_config 配置】
        dp832_config = self.config.get('dp832_config', {})
        dp832_power_mode = dp832_config.get('power_mode', {})
        mode = dp832_power_mode.get('mode', 'shared')
        use_independent = dp832_power_mode.get('use_independent_mode', False)
        
        # 兼容：如果没有 mode 字段，通过 use_independent_mode 判断
        if mode == 'shared' and use_independent:
            mode = 'independent'
        
        # 【后备：旧的 power_supply_mode 配置】
        if not dp832_config:
            power_mode_cfg = self.config.get('power_supply_mode', {})
            if power_mode_cfg.get('use_independent_power', False):
                mode = 'independent'
        
        station_config = self.config.get('stations', {}).get(station_id, {})
        
        if mode == 'independent':
            # 独立模式：为每个工位创建独立的电源实例
            logical_id = f"psu_{station_id}"
            
            if logical_id in self.devices:
                self.connect_device(logical_id)
                return self.devices[logical_id]
            
            visa_address = None
            auto_connect = True
            driver_name = 'RigolDP832'
            
            # 从 dp832_config 读取
            if dp832_config:
                independent_cfgs = dp832_power_mode.get('independent_configs', {})
                ind_cfg = independent_cfgs.get(station_id, {})
                visa_settings = ind_cfg.get('visa_settings', {})
                if isinstance(visa_settings, dict):
                    visa_address = visa_settings.get('visa_address', '')
                    auto_connect = visa_settings.get('auto_connect_on_startup', True)
                else:
                    visa_address = ind_cfg.get('visa_address', '')
                    auto_connect = ind_cfg.get('auto_connect_on_startup', True)
            
            # 【后备：从旧的 independent_power_config 读取】
            if not visa_address:
                ind_power_cfg = station_config.get('independent_power_config', {})
                visa_address = ind_power_cfg.get('visa_address')
                auto_connect = ind_power_cfg.get('auto_connect_on_startup', True)
                driver_name = ind_power_cfg.get('driver', 'RigolDP832')
            
            if not visa_address:
                raise HardwareError(f"工位 '{station_id}' 的独立电源模式下未配置 VISA 地址。请在配置编辑器的 'DP832 电源配置' 中设置。")
            
            PsuDriverClass = self._get_driver_class(driver_name)
            
            psu_instance = PsuDriverClass(visa_address=visa_address)
            self.devices[logical_id] = psu_instance
            
            if auto_connect:
                self.connect_device(logical_id)
            
            logging.info(f"独立电源模式: 工位 {station_id} 使用 VISA={visa_address}")
            return psu_instance
        
        elif mode == 'dedicated':
            # 专用模式：根据 power_control 找到工位对应的 PSU
            dedicated_cfg = dp832_power_mode.get('dedicated_config', {})
            psu_config = dedicated_cfg.get('psu_config', {})
            station_mappings = psu_config.get('power_control', {})
            
            station_mapping = station_mappings.get(station_id, {})
            product_mapping = station_mapping.get('product', {})
            psu_id = product_mapping.get('psu_id')
            
            if not psu_id:
                raise HardwareError(f"工位 '{station_id}' 的专用电源模式下未配置产品供电映射。请在配置编辑器的 'DP832 电源配置' 中设置。")
            
            device_id = f"dedicated_{psu_id}"
            
            if device_id not in self.devices:
                # 如果设备尚未连接，尝试现在连接
                power_supplies = psu_config.get('power_supplies', {})
                psu_info = power_supplies.get(psu_id, {})
                visa_address = psu_info.get('visa_address', '')
                if not visa_address:
                    raise HardwareError(f"专用电源 '{psu_id}' 未配置 VISA 地址。")
                self._create_and_connect_dp832(device_id, visa_address)
            
            logging.info(f"专用电源模式: 工位 {station_id} 使用电源 {psu_id}")
            return self.devices[device_id]
        
        else:
            # 共享模式：使用 power_control 映射到全局电源
            pc_cfg = station_config.get('power_control', {}).get('product', {})
            psu_id = pc_cfg.get('psu_id')
            
            if not psu_id:
                # 尝试从 dp832_config 的共享模式读取
                shared_cfg = dp832_power_mode.get('shared_config', {})
                visa_settings = shared_cfg.get('visa_settings', {})
                if isinstance(visa_settings, dict):
                    visa_address = visa_settings.get('visa_address', '')
                else:
                    visa_address = ''
                
                if visa_address and visa_address != 'USB0::...':
                    device_id = "dp832_shared"
                    if device_id not in self.devices:
                        self._create_and_connect_dp832(device_id, visa_address)
                    return self.devices[device_id]
                
                raise HardwareError(f"工位 '{station_id}' 的共享电源模式下未配置电源映射。")
            
            logging.info(f"共享电源模式: 工位 {station_id} 使用电源 {psu_id}")
            return self.get_psu(psu_id)

    def get_station_instrument(self, instrument_type, station_id):
        """
        获取或创建一个绑定到特定工位的仪器实例。
        例如: get_station_instrument('dmm', 'station_1')
        """
        logical_id = f"{instrument_type}_{station_id}"  # e.g., "dmm_station_1"

        if logical_id in self.devices:
            self.connect_device(logical_id)
            return self.devices[logical_id]

        station_config = self.config.get('stations', {}).get(station_id)
        if not station_config:
            raise HardwareError(f"在配置中未找到工位 '{station_id}' 的配置。")

        if instrument_type == 'dmm':
            visa_address = None
            default_mode = None
            
            # 从 dmm_config 读取（与 DP832 配置结构一致）
            dmm_config_root = self.config.get('dmm_config', {})
            dmm_mode_config = dmm_config_root.get('dmm_mode', {})
            use_independent = dmm_mode_config.get('use_independent_mode', False)
            
            if use_independent:
                ind_cfgs = dmm_mode_config.get('independent_configs', {})
                ind_cfg = ind_cfgs.get(station_id, {})
                visa_settings = ind_cfg.get('visa_settings', {})
                if isinstance(visa_settings, dict):
                    visa_address = visa_settings.get('visa_address', '')
                else:
                    visa_address = ind_cfg.get('visa_address', '')
                default_mode = ind_cfg.get('default_mode', 'DCV')
            else:
                shared_cfg = dmm_mode_config.get('shared_config', {})
                visa_settings = shared_cfg.get('visa_settings', {})
                if isinstance(visa_settings, dict):
                    visa_address = visa_settings.get('visa_address', '')
                else:
                    visa_address = shared_cfg.get('visa_address', '')
                default_mode = shared_cfg.get('default_mode', 'DCV')
            
            driver_name = 'Fluke8808A'
        else:
            raise HardwareError(f"未知的工位仪器类型: '{instrument_type}'")

        if not visa_address:
            raise HardwareError(f"在工位 '{station_id}' 的配置中找不到 '{instrument_type}' 的VISA地址。请在配置编辑器的 'Fluke8808A 配置' 中设置。")

        DriverClass = self._get_driver_class(driver_name)

        instance = DriverClass(visa_address=visa_address)
        self.devices[logical_id] = instance
        self.connect_device(logical_id)

        # 连接后，设置默认模式
        try:
            if default_mode:
                logging.info(f"为 {logical_id} 设置默认模式为: {default_mode}")
                instance.set_mode(default_mode)
        except Exception as e:
            logging.error(f"为 {logical_id} 设置默认模式失败: {e}")

        return instance

    def get_modbus_communicator(self, comm_port):
        device = self.devices.get(comm_port)
        if not device:
            raise HardwareError(f"Modbus句柄 '{comm_port}' 尚未初始化。请先在测试步骤中使用'open_serial_port'。")

        self.connect_device(comm_port)
        port_lock = self.comm_port_locks.get(comm_port)
        if not port_lock:
            port_lock = self.comm_port_locks.setdefault(comm_port, threading.Lock())

        return SynchronizedModbusCommunicator(device, port_lock, comm_port)

    def get_device(self, device_id):
        device = self.devices.get(device_id)
        if not device:
            raise HardwareError(f"请求的设备句柄不存在: {device_id}")
        return device

    def _get_locked_serial_port(self, port_name):
        port_lock = self.comm_port_locks.get(port_name)
        if not port_lock:
            raise HardwareError(f"内部错误：端口 '{port_name}' 的锁不存在。")
        raw_serial = self.raw_serial_handles.get(port_name)
        if not raw_serial:
            raise HardwareError(f"请求对端口 {port_name} 操作，但未找到其串口句柄（可能未连接）。")
        return raw_serial, port_lock

    def write_raw_string(self, port_name, data):
        # 1. 准备好要发送的 bytes 数据
        data_to_send = data.encode('utf-8') if isinstance(data, str) else data

        # 2. 用完全相同的 bytes 数据去发送
        raw_serial, port_lock = self._get_locked_serial_port(port_name)
        with port_lock:
            raw_serial.write(data_to_send)

    def write_then_read_raw_string(self, port_name, data_to_write):
        """
        直接通过串口发送原始字符串/字节，并读取一行返回。
        日志记录由底层的 SerialWrapper 自动完成。
        """
        data_to_send = data_to_write.encode('utf-8') if isinstance(data_to_write, str) else data_to_write

        raw_serial, port_lock = self._get_locked_serial_port(port_name)
        with port_lock:
            # SerialWrapper.write 会自动记录 TX
            raw_serial.write(data_to_send)

            # SerialWrapper.read 会在 readline 的循环中被调用，自动记录 RX
            received_data = raw_serial.readline()
            sniffer_instance.log_communication('RX', port_name, received_data)
            return received_data.decode('utf-8', errors='ignore').strip()

    def write_then_read_multiline(self, port_name, data_to_write, end_marker="END", timeout_s=10):
        """
        发送命令后循环读取多行响应，直到遇到 end_marker 或超时。
        用于黑匣子 GetTestContent 等返回多行数据的命令。
        
        :param port_name: 串口名称
        :param data_to_write: 要发送的命令字符串
        :param end_marker: 结束标记（默认 "END"）
        :param timeout_s: 总超时时间（秒）
        :return: (lines, overflow) - 所有读取到的行列表, 是否溢出
        """
        import time
        data_to_send = data_to_write.encode('utf-8') if isinstance(data_to_write, str) else data_to_write
        
        raw_serial, port_lock = self._get_locked_serial_port(port_name)
        lines = []
        overflow = False
        
        with port_lock:
            # 保存原始超时，设置较短的 readline 超时
            original_timeout = raw_serial.timeout
            raw_serial.timeout = 1.0  # 每次 readline 最多等1秒
            
            try:
                raw_serial.write(data_to_send)
                start_time = time.time()
                
                while (time.time() - start_time) < timeout_s:
                    line_bytes = raw_serial.readline()
                    if not line_bytes:
                        continue  # 超时空行，继续等待
                    
                    line_str = line_bytes.decode('utf-8', errors='ignore').strip()
                    if not line_str:
                        continue
                    
                    if line_str == end_marker:
                        break
                    elif line_str == "OVERFLOW":
                        overflow = True
                    elif line_str == "EMPTY":
                        break
                    else:
                        lines.append(line_str)
            finally:
                raw_serial.timeout = original_timeout
        
        return lines, overflow

    def write_then_read_cdhd_response(self, port_name, data_to_write, prompt="-->", timeout_s=5.0):
        """
        发送 CDHD 驱动器指令，清空发送前接收缓冲脏数据，循环读取多行响应直到遇到 prompt (默认 "-->") 或超时。
        
        :param port_name: 串口名称
        :param data_to_write: 要发送的命令字符串 (例如 "DICONT 8.485\r\n")
        :param prompt: CDHD 响应结束提示符（默认 "-->"）
        :param timeout_s: 最大超时时间 (单位秒，默认 5.0)
        :return: (lines, response_str) 读取到的响应行列表与合并后的字符串
        """
        import time
        data_to_send = data_to_write.encode('utf-8') if isinstance(data_to_write, str) else data_to_write
        
        raw_serial, port_lock = self._get_locked_serial_port(port_name)
        lines = []
        
        with port_lock:
            # 1. 清空串口接收缓冲区中遗留的脏数据，防止累计错误
            try:
                if hasattr(raw_serial, 'reset_input_buffer'):
                    raw_serial.reset_input_buffer()
                elif hasattr(raw_serial, 'flushInput'):
                    raw_serial.flushInput()
            except Exception:
                pass

            # 2. 临时缩短读取超时时间，提高轮询灵敏度
            original_timeout = raw_serial.timeout
            raw_serial.timeout = 0.5  # 每次 readline 最长等待 0.5 秒
            
            try:
                raw_serial.write(data_to_send)
                start_time = time.time()
                
                while (time.time() - start_time) < timeout_s:
                    line_bytes = raw_serial.readline()
                    if not line_bytes:
                        continue
                    
                    sniffer_instance.log_communication('RX', port_name, line_bytes)
                    line_str = line_bytes.decode('utf-8', errors='ignore').strip()
                    if not line_str:
                        continue
                    
                    if line_str == prompt or line_str.endswith(prompt):
                        break
                    
                    lines.append(line_str)
            finally:
                raw_serial.timeout = original_timeout
                
        response_str = "\n".join(lines).strip()
        return lines, response_str
