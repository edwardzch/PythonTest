# 文件路径: test_modules/custom_modbus.py
"""
测试模块: custom_modbus (自定义 Modbus 仪器与设备)
功能说明：
1. 串口生命周期管理：
   - open_serial_port(baudrate, bytesize, parity, stopbits, timeout): 在测试 Setup 中打开并配置串口
   - close_serial_port(): 在测试 Cleanup 中关闭串口
2. 自定义函数调用：
   - 在配置编辑器中配置的函数（如 K_BOARD）会自动生成为测试函数，参数为 state: true/false。
"""

import os as _os
import json as _json
import logging as _logging


def _get_app_base_path():
    """获取应用程序根目录路径"""
    try:
        from utils.app_utils import get_app_base_path as _base_path
        return _base_path()
    except Exception:
        return _os.path.abspath('.')


def _get_custom_modbus_driver(hardware_manager, test_engine_instance):
    """内部辅助函数：获取自定义 Modbus 驱动句柄"""
    if not hardware_manager:
        raise ValueError("硬件管理器 (hardware_manager) 未提供。")
    station_id = getattr(test_engine_instance, 'station_id', 'station_1') if test_engine_instance else 'station_1'
    return hardware_manager.get_custom_modbus_driver(station_id), station_id


def _execute_custom_modbus(func_name, state=True, hardware_manager=None, test_engine_instance=None, **kwargs):
    """内部函数：执行自定义 Modbus 写入"""
    try:
        driver, station_id = _get_custom_modbus_driver(hardware_manager, test_engine_instance)
        return driver.execute_function(func_name=func_name, state=state, station_id=station_id)
    except Exception as e:
        err = f"执行自定义 Modbus 功能 '{func_name}' 失败: {e}"
        logging.error(err, exc_info=True)
        return False, err


def _read_custom_modbus(func_name, hardware_manager=None, test_engine_instance=None, **kwargs):
    """内部函数：读取自定义 Modbus 状态"""
    try:
        driver, station_id = _get_custom_modbus_driver(hardware_manager, test_engine_instance)
        return driver.read_function(func_name=func_name, station_id=station_id)
    except Exception as e:
        err = f"读取自定义 Modbus 功能 '{func_name}' 失败: {e}"
        logging.error(err, exc_info=True)
        return False, err


# ==========================================
# 公开导出函数 1: 打开并配置串口
# ==========================================
def open_serial_port(baudrate, bytesize, parity, stopbits, timeout, hardware_manager=None, test_engine_instance=None, **kwargs):
    """
    打开并配置自定义 Modbus 仪器的通信串口。
    建议在测试序列的 Setup 区块中调用。

    :param baudrate: (int) 波特率, 例如 9600, 19200, 57600, 115200。
    :param bytesize: (int) 数据位, 通常是 8。
    :param parity: (str) 校验位, 'N' (无), 'E' (偶), 'O' (奇)。
    :param stopbits: (int) 停止位, 通常是 1 或 2。
    :param timeout: (float) 超时时间（秒），例如 1.0。
    :return: (bool, str) 执行结果。
    """
    try:
        driver, station_id = _get_custom_modbus_driver(hardware_manager, test_engine_instance)
        driver.open_serial(
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            timeout=timeout
        )
        return True, f"Modbus 仪器串口 {driver.port} 成功打开 (波特率: {baudrate}, 8-{parity}-{stopbits}, 超时: {timeout}s)。"
    except Exception as e:
        err = f"打开 Modbus 串口失败: {e}"
        logging.error(err, exc_info=True)
        return False, err


# ==========================================
# 公开导出函数 2: 关闭串口
# ==========================================
def close_serial_port(hardware_manager=None, test_engine_instance=None, **kwargs):
    """
    关闭自定义 Modbus 仪器的通信串口。
    建议在测试序列的 Cleanup 区块中调用，以确保串口资源被正确释放。

    :return: (bool, str) 执行结果。
    """
    try:
        driver, station_id = _get_custom_modbus_driver(hardware_manager, test_engine_instance)
        driver.close()
        return True, f"Modbus 仪器串口 {driver.port} 已成功关闭。"
    except Exception as e:
        err = f"关闭 Modbus 串口时发生异常: {e}"
        logging.warning(err)
        return True, f"关闭 Modbus 串口遇到问题，但测试继续: {e}"


# ==========================================
# 动态注册在配置器中定义的功能函数（如 K_BOARD）
# ==========================================
def _create_dynamic_function(name):
    """动态生成具体功能函数闭包（供序列编辑器直接作为函数下拉选项）"""
    def _func(state=True, hardware_manager=None, test_engine_instance=None, **kwargs):
        return _execute_custom_modbus(name, state=state, hardware_manager=hardware_manager,
                                      test_engine_instance=test_engine_instance, **kwargs)
    _func.__name__ = name
    _func.__doc__ = f"控制自定义 Modbus 功能 '{name}'。\n参数 state 为 True 写入配置的 true值，False 写入配置的 false值。"
    return _func


def _load_and_register_configured_functions():
    """从 config.json 动态加载所有已配置的功能名称，并注册为模块可调用的函数"""
    try:
        config_path = _os.path.join(_get_app_base_path(), 'config.json')
        if not _os.path.exists(config_path):
            config_path = _os.path.join(_os.path.abspath('.'), 'config.json')

        if _os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                cfg = _json.load(f)

            root_cfg = cfg.get('custom_modbus_config') or cfg.get('relay_config') or {}
            mode_cfg = root_cfg.get('device_mode') or root_cfg.get('relay_mode') or root_cfg
            shared_cfg = mode_cfg.get('shared_config', {})
            channel_mappings = shared_cfg.get('channel_mappings', [])

            reserved_names = {'open_serial_port', 'close_serial_port'}
            for item in channel_mappings:
                if isinstance(item, dict) and 'alias' in item:
                    alias = item['alias'].strip()
                    if alias and alias.isidentifier() and alias not in reserved_names:
                        globals()[alias] = _create_dynamic_function(alias)
    except Exception as e:
        print(f"[custom_modbus] 动态加载配置函数失败: {e}")


# 初始化时动态注册在配置器中定义的所有函数
_load_and_register_configured_functions()
