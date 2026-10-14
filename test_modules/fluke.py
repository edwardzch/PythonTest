# test_modules/fluke.py
"""
此模块提供了与 Fluke 8808A 数字万用表交互的测试函数。
新版本将仪器模式设置和数值读取分离，并支持单位转换。
"""

# 单位转换字典: Key = 用户输入的单位, Value = 从基础单位转换的乘数
UNIT_MULTIPLIERS = {
    # Voltage
    'V': 1,
    'mV': 1000,
    'uV': 1_000_000,
    # Current
    'A': 1,
    'mA': 1000,
    'uA': 1_000_000,
    # Resistance
    'Ohm': 1,
    'kOhm': 1 / 1000,
    'MOhm': 1 / 1_000_000,
}

def set_measurement_mode(logger, hardware_manager, station_id, mode, **kwargs):
    """
    设置万用表的测量模式，不读取数值。这是一个耗时操作（约2-3秒），建议在测试序列的准备阶段调用。

    用法示例:
    - 模块: fluke
    - 函数: set_measurement_mode
    - 参数: {"mode": "DCI"}  # 设置为直流电流模式

    :param station_id: (str) 当前工位的ID, 由测试引擎注入。
    :param mode: (str) 要设置的模式。可用模式包括: 'DCV', 'ACV', 'DCI', 'ACI', 'RES', 'DIODE', 'FREQ', 'CONT'。
    """
    try:
        dmm = hardware_manager.get_station_instrument(instrument_type='dmm', station_id=station_id)
        if dmm is None:
            return False, f"未能找到工位 {station_id} 对应的万用表。"

        logger.info(f"工位 {station_id}: 设置万用表模式为 '{mode}'...")
        dmm.set_mode(mode)
        logger.info(f"工位 {station_id}: 万用表模式已设置为 '{mode}'。")
        return True, f"模式已设置为 {mode}"

    except Exception as e:
        logger.error(f"设置万用表模式 '{mode}' 时发生异常: {e}", exc_info=True)
        return False, f"异常: {e}"

def read_measurement(logger, hardware_manager, station_id, unit=None, **kwargs):
    """
    从万用表读取当前数值，并根据需要进行单位转换。此函数应在调用 set_measurement_mode 之后使用。

    用法示例:
    - 模块: fluke
    - 函数: read_measurement
    - 参数: {"unit": "mA"}  # 读取数值，并期望以毫安(mA)为单位返回

    :param station_id: (str) 当前工位的ID, 由测试引擎注入。
    :param unit: (str, optional) 期望返回值的单位。如果提供，将自动转换。
        - 电压单位: 'V', 'mV', 'uV'
        - 电流单位: 'A', 'mA', 'uA'
        - 电阻单位: 'Ohm', 'kOhm', 'MOhm'
    :return: (bool, str) 测量结果元组。
    """
    try:
        dmm = hardware_manager.get_station_instrument(instrument_type='dmm', station_id=station_id)
        if dmm is None:
            return False, f"未能找到工位 {station_id} 对应的万用表。"

        value = dmm.read_value()

        if value is not None:
            if unit and unit in UNIT_MULTIPLIERS:
                converted_value = value * UNIT_MULTIPLIERS[unit]
                logger.info(f"工位 {station_id} 读数: {value:.6f} -> {converted_value:.6f} {unit}")
                return True, f"{converted_value:.6f}"
            elif unit:
                logger.warning(f"未知的单位: '{unit}'。将返回原始值。")
                return True, str(value)
            else:
                logger.info(f"工位 {station_id} 读数: {value}")
                return True, str(value)
        else:
            return False, f"从工位 {station_id} 的万用表读取值失败。"

    except Exception as e:
        logger.error(f"读取万用表数值时发生异常: {e}", exc_info=True)
        return False, f"异常: {e}"

def measure_value(logger, hardware_manager, station_id, mode, unit=None, **kwargs):
    """
    [推荐：多工位共享模式下安全] 
    原子性操作：设置模式并立刻读取数值，期间锁定设备防止其他工位插队串台。
    
    用法示例:
    - 模块: fluke
    - 函数: measure_value
    - 参数: {"mode": "DCV", "unit": "V"}
    """
    try:
        dmm = hardware_manager.get_station_instrument(instrument_type='dmm', station_id=station_id)
        if dmm is None:
            return False, f"未能找到工位 {station_id} 对应的万用表。"

        logger.info(f"工位 {station_id}: 正在原子地将万用表模式设置为 '{mode}' 并读取数值...")
        
        # 使用底层驱动的新方法获得原子性的带锁保护
        if hasattr(dmm, 'measure_atomic'):
            value = dmm.measure_atomic(mode)
        else:
            # 兼容非 fluke8808a 或老版本驱动
            dmm.set_mode(mode)
            value = dmm.read_value()

        if value is not None:
            if unit and unit in UNIT_MULTIPLIERS:
                converted_value = value * UNIT_MULTIPLIERS[unit]
                logger.info(f"工位 {station_id} 读数: {value:.6f} -> {converted_value:.6f} {unit}")
                return True, f"{converted_value:.6f}"
            elif unit:
                logger.warning(f"未知的单位: '{unit}'。将返回原始值。")
                return True, str(value)
            else:
                logger.info(f"工位 {station_id} 读数: {value}")
                return True, str(value)
        else:
            return False, f"从工位 {station_id} 的万用表读取值失败。"

    except Exception as e:
        logger.error(f"原子读取万用表数值时发生异常: {e}", exc_info=True)
        return False, f"异常: {e}"
