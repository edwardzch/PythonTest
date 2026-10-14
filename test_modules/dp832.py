# test_modules/dp832.py
"""
此模块提供与程控电源交互的所有功能。
它包含用于设置电压/电流、开关通道以及进行测量等操作的函数。
"""

# --- 内部核心函数 ---

def set_power(psu, channel, voltage, current_limit, output_on, station_id=None):
    """(内部使用) 通用电源设置函数。"""
    psu.set_voltage(voltage, channel=channel, station_id=station_id)
    psu.set_current(current_limit, channel=channel, station_id=station_id)
    if output_on:
        psu.turn_on(channel=channel, station_id=station_id)
        msg = f"通道 {channel} 已打开, 设置为 {voltage}V, {current_limit}A."
    else:
        psu.turn_off(channel=channel, station_id=station_id)
        msg = f"通道 {channel} 已关闭。"
    return True, msg

def measure_current(psu, channel, station_id=None):
    """(内部使用) 测量指定通道的电流。"""
    current = psu.measure_current(channel, station_id=station_id)
    return current, f"通道 {channel} 测得电流: {current:.4f} A"

def measure_voltage(psu, channel, station_id=None):
    """(内部使用) 测量指定通道的电压。"""
    voltage = psu.measure_voltage(channel, station_id=station_id)
    return voltage, f"通道 {channel} 测得电压: {voltage:.3f} V"

def _get_power_params(supply_type, **kwargs):
    """
    (内部使用) 辅助函数，根据电源模式从正确的配置中获取通道。
    
    :param supply_type: 供电类型 ("product", "battery", "daq")
    
    配置读取优先级（独立模式）：
    1. dp832_config.power_mode.independent_configs.{station_id}.mappings（新格式）
    2. independent_power_config.mappings（旧格式，向后兼容）
    3. 默认通道映射（product=1, daq=2, battery=3）
    """
    station_id = kwargs.get('station_id')
    power_control = kwargs.get('power_control', {})
    
    # 【新配置】从 dp832_config 读取
    dp832_config = kwargs.get('dp832_config', {})
    dp832_power_mode = dp832_config.get('power_mode', {})
    use_independent_new = dp832_power_mode.get('use_independent_mode', False)
    
    # 【旧配置】从 power_supply_mode 和 independent_power_config 读取
    power_supply_mode = kwargs.get('power_supply_mode', {})
    independent_power_config = kwargs.get('independent_power_config', {})
    use_independent_old = power_supply_mode.get('use_independent_power', False) if power_supply_mode else False
    
    # 确定是否使用独立模式
    mode = dp832_power_mode.get('mode', 'shared') if dp832_config else 'shared'
    if not dp832_config and use_independent_old:
        mode = 'independent'

    if mode == 'dedicated':
        # 专用模式：从 dedicated_config -> psu_config -> power_control -> station_id 读取
        dedicated_cfg = dp832_power_mode.get('dedicated_config', {})
        psu_config = dedicated_cfg.get('psu_config', {})
        power_control_cfg = psu_config.get('power_control', {})
        station_pc = power_control_cfg.get(station_id, {})
        
        if supply_type not in station_pc:
            raise ValueError(f"在专用电源配置中未找到工位 '{station_id}' 的 '{supply_type}' 映射")
        
        channel = station_pc[supply_type].get('channel')
        psu_id = station_pc[supply_type].get('psu_id')
        if channel is None or psu_id is None:
            raise ValueError(f"专用电源模式工位 '{station_id}' 的 '{supply_type}' 未配置完整 (psu_id或channel)")
            
        return f"dedicated_{psu_id}", int(channel)

    elif mode == 'independent':
        # 独立模式：尝试从新配置读取 mappings
        mappings = None
        
        # 1. 优先从新配置 dp832_config 读取
        if dp832_config and station_id:
            ind_configs = dp832_power_mode.get('independent_configs', {})
            station_cfg = ind_configs.get(station_id, {})
            mappings = station_cfg.get('mappings', {})
        
        # 2. 如果新配置没有，回退到旧配置 independent_power_config
        if not mappings and independent_power_config:
            mappings = independent_power_config.get('mappings', {})
        
        # 默认通道映射
        default_channels = {'product': 1, 'daq': 2, 'battery': 3}
        
        if mappings:
            channel_config = mappings.get(supply_type, {})
            channel = channel_config.get('channel')
        else:
            channel = None
        
        if channel is None:
            if supply_type in default_channels:
                channel = default_channels[supply_type]
            else:
                raise ValueError(f"在独立电源配置中未找到 '{supply_type}' 的通道定义")

        # 独立模式下不需要 psu_id，因为电源已经是按工位绑定的
        return None, int(channel)
    else:
        # 共享模式：从 power_control 读取 psu_id 和通道
        if not power_control or supply_type not in power_control:
            raise ValueError(f"在 power_control 配置（共享模式）中未找到名为 '{supply_type}' 的电源定义")
        return power_control[supply_type].get('psu_id'), power_control[supply_type].get('channel')

# --- 用户可用函数 ---

def set_power_product(voltage, current_limit, output_on, **kwargs):
    """
    设置"产品供电"电源。
    此函数用于控制产品供电电源，根据电源模式（独立/共享）自动选择正确的配置。

    :param voltage: (float) 要设置的电压值 (单位: V)。
    :param current_limit: (float) 要设置的电流上限 (单位: A)。
    :param output_on: (bool) 是否开启电源输出 (True 或 False)。
    :return: (bool, str) 执行结果。

    用法示例:
    - 模块: dp832
    - 函数: set_power_product
    - 参数: {"voltage": 5.0, "current_limit": 3.0, "output_on": true}
    """
    voltage = float(voltage)
    current_limit = float(current_limit)
    output_on = str(output_on).lower() == 'true'
    
    get_psu_handle = kwargs.get('get_psu_handle')
    station_id = kwargs.get('station_id')
    psu_id, channel = _get_power_params("product", **kwargs)
    psu = get_psu_handle(psu_id)
    return set_power(psu, channel, voltage, current_limit, output_on, station_id=station_id)

def measure_product_current(**kwargs):
    """
    测量"产品供电"电源的输出电流。
    此函数会根据电源模式读取正确配置的电源的当前实际输出电流。

    :return: (float, str) 返回值为测量到的电流值 (A)，可用于后续判断。

    用法示例:
    - 模块: dp832
    - 函数: measure_product_current
    - 变量: current_A
    - 比较: InRange
    - 最小值: 0.1
    - 最大值: 0.5
    """
    get_psu_handle = kwargs.get('get_psu_handle')
    station_id = kwargs.get('station_id')
    psu_id, channel = _get_power_params("product", **kwargs)
    psu = get_psu_handle(psu_id)
    return measure_current(psu, channel, station_id=station_id)

def measure_product_voltage(**kwargs):
    """
    测量"产品供电"电源的输出电压。
    此函数会根据电源模式读取正确配置的电源的当前实际输出电压。

    :return: (float, str) 返回值为测量到的电压值 (V)，可用于后续判断。

    用法示例:
    - 模块: dp832
    - 函数: measure_product_voltage
    - 变量: voltage_V
    - 比较: InRange
    - 最小值: 4.9
    - 最大值: 5.1
    """
    get_psu_handle = kwargs.get('get_psu_handle')
    station_id = kwargs.get('station_id')
    psu_id, channel = _get_power_params("product", **kwargs)
    psu = get_psu_handle(psu_id)
    return measure_voltage(psu, channel, station_id=station_id)

def set_power_battery(voltage, current_limit, output_on, **kwargs):
    """
    设置"电池供电"电源。

    :param voltage: (float) 要设置的电压值 (单位: V)。
    :param current_limit: (float) 要设置的电流上限 (单位: A)。
    :param output_on: (bool) 是否开启电源输出 (True 或 False)。
    :return: (bool, str) 执行结果。

    用法示例:
    - 模块: dp832
    - 函数: set_power_battery
    - 参数: {"voltage": 3.7, "current_limit": 1.0, "output_on": true}
    """
    voltage = float(voltage)
    current_limit = float(current_limit)
    output_on = str(output_on).lower() == 'true'
    
    get_psu_handle = kwargs.get('get_psu_handle')
    station_id = kwargs.get('station_id')
    psu_id, channel = _get_power_params("battery", **kwargs)
    psu = get_psu_handle(psu_id)
    return set_power(psu, channel, voltage, current_limit, output_on, station_id=station_id)

def set_power_daq(voltage, current_limit, output_on, **kwargs):
    """
    设置"采集卡供电"电源。

    :param voltage: (float) 要设置的电压值 (单位: V)。
    :param current_limit: (float) 要设置的电流上限 (单位: A)。
    :param output_on: (bool) 是否开启电源输出 (True 或 False)。
    :return: (bool, str) 执行结果。

    用法示例:
    - 模块: dp832
    - 函数: set_power_daq
    - 参数: {"voltage": 5.0, "current_limit": 3.0, "output_on": true}
    """
    voltage = float(voltage)
    current_limit = float(current_limit)
    output_on = str(output_on).lower() == 'true'
    
    get_psu_handle = kwargs.get('get_psu_handle')
    station_id = kwargs.get('station_id')
    psu_id, channel = _get_power_params("daq", **kwargs)
    psu = get_psu_handle(psu_id)
    return set_power(psu, channel, voltage, current_limit, output_on, station_id=station_id)

def connect_instrument(device_id, **kwargs):
    """
    连接一个在 config.json 中定义的硬件设备。
    适合放在 Setup 区块中，用于显式地初始化硬件（如程控电源）。如果设备已连接，则不会重复连接。

    :param device_id: (str) 要连接的设备的ID，必须与 config.json 中的定义匹配 (例如 "PSU_A")。
    :return: (bool, str) 执行结果。
    """
    if not device_id:
        return False, "参数错误: device_id 不能为空。"
    hardware_manager = kwargs.get('hardware_manager')
    success = hardware_manager.connect_device(device_id)
    return (True, f"设备 {device_id} 连接成功或已连接。") if success else (False, f"设备 {device_id} 连接失败。")

def disconnect_instrument(device_id, **kwargs):
    """
    断开一个硬件设备的连接。
    适合放在 Cleanup 区块中，用于安全地释放硬件资源。

    :param device_id: (str) 要断开的设备的ID (例如 "PSU_A")。
    :return: (bool, str) 执行结果。
    """
    if not device_id:
        return False, "参数错误: device_id 不能为空。"
    hardware_manager = kwargs.get('hardware_manager')
    success = hardware_manager.disconnect_device(device_id)
    return (True, f"设备 {device_id} 已断开。") if success else (False, f"设备 {device_id} 断开失败。")