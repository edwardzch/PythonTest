# test_modules/power.py
"""
此模块提供与程控电源交互的所有功能。
它包含用于设置电压/电流、开关通道以及进行测量等操作的函数。
"""

# --- 内部核心函数 ---

def set_power(psu, channel, voltage, current_limit, output_on):
    """(内部使用) 通用电源设置函数。"""
    psu.select_channel(channel)
    psu.set_voltage(voltage)
    psu.set_current(current_limit)
    if output_on:
        psu.turn_on()
        msg = f"通道 {channel} 已打开, 设置为 {voltage}V, {current_limit}A."
    else:
        psu.turn_off()
        msg = f"通道 {channel} 已关闭。"
    return True, msg

def measure_current(psu, channel):
    """(内部使用) 测量指定通道的电流。"""
    current = psu.measure_current(channel)
    return current, f"通道 {channel} 测得电流: {current:.4f} A"

def measure_voltage(psu, channel):
    """(内部使用) 测量指定通道的电压。"""
    voltage = psu.measure_voltage(channel)
    return voltage, f"通道 {channel} 测得电压: {voltage:.3f} V"

def _get_power_params(supply_type, **kwargs):
    """
    (内部使用) 辅助函数，根据电源模式从正确的配置中获取通道。
    
    :param supply_type: 供电类型 ("product", "battery", "daq")
    """
    power_supply_mode = kwargs.get('power_supply_mode', {})
    independent_power_config = kwargs.get('independent_power_config', {})
    power_control = kwargs.get('power_control', {})
    
    use_independent = power_supply_mode.get('use_independent_power', False) if power_supply_mode else False
    
    if use_independent and independent_power_config:
        # 独立模式：从 independent_power_config.mappings 读取通道
        mappings = independent_power_config.get('mappings', {})
        if supply_type not in mappings:
            raise ValueError(f"在独立电源配置的 mappings 中未找到 '{supply_type}' 的通道定义")
        channel = mappings[supply_type].get('channel')
        if channel is None:
            raise ValueError(f"独立电源配置中 '{supply_type}' 的通道未设置")
        # 独立模式下不需要 psu_id，因为电源已经是按工位绑定的
        return None, int(channel)
    else:
        # 共享模式：从 power_control 读取 psu_id 和通道
        if not power_control or supply_type not in power_control:
            raise ValueError(f"在 power_control 配置中未找到名为 '{supply_type}' 的电源定义")
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
    - 模块: power
    - 函数: set_power_product
    - 参数: {"voltage": 5.0, "current_limit": 3.0, "output_on": true}
    """
    voltage = float(voltage)
    current_limit = float(current_limit)
    output_on = str(output_on).lower() == 'true'
    
    get_psu_handle = kwargs.get('get_psu_handle')
    psu_id, channel = _get_power_params("product", **kwargs)
    psu = get_psu_handle(psu_id)
    return set_power(psu, channel, voltage, current_limit, output_on)

def measure_product_current(**kwargs):
    """
    测量"产品供电"电源的输出电流。
    此函数会根据电源模式读取正确配置的电源的当前实际输出电流。

    :return: (float, str) 返回值为测量到的电流值 (A)，可用于后续判断。

    用法示例:
    - 模块: power
    - 函数: measure_product_current
    - 变量: current_A
    - 比较: InRange
    - 最小值: 0.1
    - 最大值: 0.5
    """
    get_psu_handle = kwargs.get('get_psu_handle')
    psu_id, channel = _get_power_params("product", **kwargs)
    psu = get_psu_handle(psu_id)
    return measure_current(psu, channel)

def measure_product_voltage(**kwargs):
    """
    测量"产品供电"电源的输出电压。
    此函数会根据电源模式读取正确配置的电源的当前实际输出电压。

    :return: (float, str) 返回值为测量到的电压值 (V)，可用于后续判断。

    用法示例:
    - 模块: power
    - 函数: measure_product_voltage
    - 变量: voltage_V
    - 比较: InRange
    - 最小值: 4.9
    - 最大值: 5.1
    """
    get_psu_handle = kwargs.get('get_psu_handle')
    psu_id, channel = _get_power_params("product", **kwargs)
    psu = get_psu_handle(psu_id)
    return measure_voltage(psu, channel)

def set_power_battery(voltage, current_limit, output_on, **kwargs):
    """
    设置"电池供电"电源。

    :param voltage: (float) 要设置的电压值 (单位: V)。
    :param current_limit: (float) 要设置的电流上限 (单位: A)。
    :param output_on: (bool) 是否开启电源输出 (True 或 False)。
    :return: (bool, str) 执行结果。

    用法示例:
    - 模块: power
    - 函数: set_power_battery
    - 参数: {"voltage": 3.7, "current_limit": 1.0, "output_on": true}
    """
    voltage = float(voltage)
    current_limit = float(current_limit)
    output_on = str(output_on).lower() == 'true'
    
    get_psu_handle = kwargs.get('get_psu_handle')
    psu_id, channel = _get_power_params("battery", **kwargs)
    psu = get_psu_handle(psu_id)
    return set_power(psu, channel, voltage, current_limit, output_on)

def set_power_daq(voltage, current_limit, output_on, **kwargs):
    """
    设置"采集卡供电"电源。

    :param voltage: (float) 要设置的电压值 (单位: V)。
    :param current_limit: (float) 要设置的电流上限 (单位: A)。
    :param output_on: (bool) 是否开启电源输出 (True 或 False)。
    :return: (bool, str) 执行结果。

    用法示例:
    - 模块: power
    - 函数: set_power_daq
    - 参数: {"voltage": 5.0, "current_limit": 3.0, "output_on": true}
    """
    voltage = float(voltage)
    current_limit = float(current_limit)
    output_on = str(output_on).lower() == 'true'
    
    get_psu_handle = kwargs.get('get_psu_handle')
    psu_id, channel = _get_power_params("daq", **kwargs)
    psu = get_psu_handle(psu_id)
    return set_power(psu, channel, voltage, current_limit, output_on)

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