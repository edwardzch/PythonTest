# test_modules/spd4323x.py
"""
此模块提供与 Siglent SPD4323X 四通道程控电源交互的所有功能。
包含两种模式：
- 共享模式（非独立模式）：一台电源的4个通道分别对应4个工位，函数无需指定通道
- 独立模式：每个工位有独立的SPD4323X，函数需要指定通道参数
"""

# ========== 内部核心函数 ==========

def _get_spd4323x_handle(**kwargs):
    """
    (内部使用) 获取 SPD4323X 电源句柄。
    根据配置的模式（共享/独立）选择正确的句柄。
    """
    hardware_manager = kwargs.get('hardware_manager')
    station_id = kwargs.get('station_id')
    
    # 使用 hardware_manager 的 get_spd4323x 方法
    psu = hardware_manager.get_spd4323x(station_id)
    return psu



def _get_shared_channel(**kwargs):
    """
    (内部使用) 在共享模式下，根据工位ID获取对应的通道号。
    默认映射: station_1 -> CH1, station_2 -> CH2, station_3 -> CH3, station_4 -> CH4
    """
    station_id = kwargs.get('station_id')
    spd_config = kwargs.get('spd4323x_config', {})
    shared_config = spd_config.get('shared_config', {})
    channel_mappings = shared_config.get('channel_mappings', {})
    
    station_mapping = channel_mappings.get(station_id, {})
    channel = station_mapping.get('channel')
    
    if channel is None:
        # 默认映射：station_1 -> 1, station_2 -> 2, ...
        try:
            station_num = int(station_id.split('_')[1])
            channel = station_num
        except (IndexError, ValueError):
            channel = 1
    
    return int(channel)


# ========== 共享模式函数（非独立模式，通道与工位绑定）==========

def set_power(voltage, current_limit, output_on, **kwargs):
    """
    [共享模式] 设置电源输出，通道由工位ID自动确定。
    
    :param voltage: (float) 电压值 (V)
    :param current_limit: (float) 电流限制 (A)
    :param output_on: (bool) 是否打开输出
    :return: (bool, str) 执行结果
    
    用法示例 (在测试序列编辑器中):
    - 模块: spd4323x
    - 函数: set_power
    - 参数: {"voltage": 5.0, "current_limit": 3.0, "output_on": true}
    """
    voltage = float(voltage)
    current_limit = float(current_limit)
    output_on = str(output_on).lower() == 'true' if isinstance(output_on, str) else bool(output_on)
    
    psu = _get_spd4323x_handle(**kwargs)
    channel = _get_shared_channel(**kwargs)
    
    psu.set_voltage(voltage, channel)
    psu.set_current(current_limit, channel)
    
    if output_on:
        psu.turn_on(channel)
        msg = f"SPD4323X CH{channel} 已打开, 设置为 {voltage}V, {current_limit}A."
    else:
        psu.turn_off(channel)
        msg = f"SPD4323X CH{channel} 已关闭."
    
    return True, msg


def measure_voltage(**kwargs):
    """
    [共享模式] 测量电源输出电压，通道由工位ID自动确定。
    
    :return: (float, str) 测量到的电压值 (V)
    
    用法示例:
    - 模块: spd4323x
    - 函数: measure_voltage
    - 变量: voltage_V
    - 比较: InRange
    - 最小值: 4.9
    - 最大值: 5.1
    """
    psu = _get_spd4323x_handle(**kwargs)
    channel = _get_shared_channel(**kwargs)
    
    voltage = psu.measure_voltage(channel)
    return voltage, f"SPD4323X CH{channel} 测得电压: {voltage:.3f}V"


def measure_current(**kwargs):
    """
    [共享模式] 测量电源输出电流，通道由工位ID自动确定。
    
    :return: (float, str) 测量到的电流值 (A)
    
    用法示例:
    - 模块: spd4323x
    - 函数: measure_current
    - 变量: current_A
    - 比较: InRange
    - 最小值: 0.1
    - 最大值: 0.5
    """
    psu = _get_spd4323x_handle(**kwargs)
    channel = _get_shared_channel(**kwargs)
    
    current = psu.measure_current(channel)
    return current, f"SPD4323X CH{channel} 测得电流: {current:.4f}A"


def output_on(**kwargs):
    """
    [共享模式] 打开电源输出，通道由工位ID自动确定。
    
    :return: (bool, str) 执行结果
    
    用法示例:
    - 模块: spd4323x
    - 函数: output_on
    """
    psu = _get_spd4323x_handle(**kwargs)
    channel = _get_shared_channel(**kwargs)
    
    psu.turn_on(channel)
    return True, f"SPD4323X CH{channel} 输出已打开."


def output_off(**kwargs):
    """
    [共享模式] 关闭电源输出，通道由工位ID自动确定。
    
    :return: (bool, str) 执行结果
    
    用法示例:
    - 模块: spd4323x
    - 函数: output_off
    """
    psu = _get_spd4323x_handle(**kwargs)
    channel = _get_shared_channel(**kwargs)
    
    psu.turn_off(channel)
    return True, f"SPD4323X CH{channel} 输出已关闭."


# ========== 独立模式函数（需指定通道参数）==========

def set_power_channel(channel, voltage, current_limit, output_on, **kwargs):
    """
    [独立模式] 设置指定通道的电源输出。
    
    :param channel: (int) 通道号 (1-4)
    :param voltage: (float) 电压值 (V)
    :param current_limit: (float) 电流限制 (A)
    :param output_on: (bool) 是否打开输出
    :return: (bool, str) 执行结果
    
    用法示例:
    - 模块: spd4323x
    - 函数: set_power_channel
    - 参数: {"channel": 1, "voltage": 5.0, "current_limit": 3.0, "output_on": true}
    """
    channel = int(channel)
    voltage = float(voltage)
    current_limit = float(current_limit)
    output_on = str(output_on).lower() == 'true' if isinstance(output_on, str) else bool(output_on)
    
    psu = _get_spd4323x_handle(**kwargs)
    
    psu.set_voltage(voltage, channel)
    psu.set_current(current_limit, channel)
    
    if output_on:
        psu.turn_on(channel)
        msg = f"SPD4323X CH{channel} 已打开, 设置为 {voltage}V, {current_limit}A."
    else:
        psu.turn_off(channel)
        msg = f"SPD4323X CH{channel} 已关闭."
    
    return True, msg


def measure_voltage_channel(channel, **kwargs):
    """
    [独立模式] 测量指定通道的电源输出电压。
    
    :param channel: (int) 通道号 (1-4)
    :return: (float, str) 测量到的电压值 (V)
    
    用法示例:
    - 模块: spd4323x
    - 函数: measure_voltage_channel
    - 参数: {"channel": 1}
    - 变量: voltage_V
    """
    channel = int(channel)
    psu = _get_spd4323x_handle(**kwargs)
    
    voltage = psu.measure_voltage(channel)
    return voltage, f"SPD4323X CH{channel} 测得电压: {voltage:.3f}V"


def measure_current_channel(channel, **kwargs):
    """
    [独立模式] 测量指定通道的电源输出电流。
    
    :param channel: (int) 通道号 (1-4)
    :return: (float, str) 测量到的电流值 (A)
    
    用法示例:
    - 模块: spd4323x
    - 函数: measure_current_channel
    - 参数: {"channel": 2}
    - 变量: current_A
    """
    channel = int(channel)
    psu = _get_spd4323x_handle(**kwargs)
    
    current = psu.measure_current(channel)
    return current, f"SPD4323X CH{channel} 测得电流: {current:.4f}A"


def output_on_channel(channel, **kwargs):
    """
    [独立模式] 打开指定通道的电源输出。
    
    :param channel: (int) 通道号 (1-4)
    :return: (bool, str) 执行结果
    
    用法示例:
    - 模块: spd4323x
    - 函数: output_on_channel
    - 参数: {"channel": 1}
    """
    channel = int(channel)
    psu = _get_spd4323x_handle(**kwargs)
    
    psu.turn_on(channel)
    return True, f"SPD4323X CH{channel} 输出已打开."


def output_off_channel(channel, **kwargs):
    """
    [独立模式] 关闭指定通道的电源输出。
    
    :param channel: (int) 通道号 (1-4)
    :return: (bool, str) 执行结果
    
    用法示例:
    - 模块: spd4323x
    - 函数: output_off_channel
    - 参数: {"channel": 1}
    """
    channel = int(channel)
    psu = _get_spd4323x_handle(**kwargs)
    
    psu.turn_off(channel)
    return True, f"SPD4323X CH{channel} 输出已关闭."


# ========== 连接管理函数 ==========

def connect_spd4323x(**kwargs):
    """
    连接 SPD4323X 电源。适合放在 Setup 区块中。
    
    :return: (bool, str) 执行结果
    
    用法示例:
    - 模块: spd4323x
    - 函数: connect_spd4323x
    """
    try:
        psu = _get_spd4323x_handle(**kwargs)
        if not psu.is_connected():
            psu.connect()
        return True, "SPD4323X 连接成功."
    except Exception as e:
        return False, f"SPD4323X 连接失败: {e}"


def disconnect_spd4323x(**kwargs):
    """
    断开 SPD4323X 电源连接。适合放在 Cleanup 区块中。
    
    :return: (bool, str) 执行结果
    
    用法示例:
    - 模块: spd4323x
    - 函数: disconnect_spd4323x
    """
    try:
        psu = _get_spd4323x_handle(**kwargs)
        if psu.is_connected():
            psu.close()
        return True, "SPD4323X 已断开连接."
    except Exception as e:
        return False, f"SPD4323X 断开连接失败: {e}"


# ========== 辅助函数 ==========

def get_channel_status(channel, **kwargs):
    """
    获取指定通道的完整状态（电压、电流、运行模式）。
    
    :param channel: (int) 通道号 (1-4)
    :return: (dict, str) 状态字典和信息
    
    用法示例:
    - 模块: spd4323x
    - 函数: get_channel_status
    - 参数: {"channel": 1}
    """
    channel = int(channel)
    psu = _get_spd4323x_handle(**kwargs)
    
    voltage, current, mode = psu.get_status(channel)
    
    status = {
        'voltage': voltage,
        'current': current,
        'mode': mode
    }
    
    msg = f"SPD4323X CH{channel}: {voltage:.3f}V, {current:.4f}A, 模式: {mode}"
    return status, msg


def set_all_channels_off(**kwargs):
    """
    关闭所有通道的输出。适合用于紧急停止或测试清理。
    
    :return: (bool, str) 执行结果
    
    用法示例:
    - 模块: spd4323x
    - 函数: set_all_channels_off
    """
    psu = _get_spd4323x_handle(**kwargs)
    
    for ch in [1, 2, 3, 4]:
        try:
            psu.turn_off(ch)
        except Exception:
            pass
    
    return True, "SPD4323X 所有通道输出已关闭."
