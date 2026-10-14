# 文件路径: test_modules/relay_board.py
"""
测试模块: relay_board (USB / 串口继电器板控制模块)
适用于：USB Relay (TC, 4, Opto) / LCUS 系列继电器板 (专用 HEX/ASCII 协议)

函数设计：
1. 串口生命周期：
   - open_serial_port(baudrate, bytesize, parity, stopbits, timeout)
   - close_serial_port()

2. 【共享模式常用函数】（无需指定通道，通道由当前工位ID自动确定：工位1->CH1, 工位2->CH2...）：
   - set_relay(state=True): 控制当前工位对应继电器（state: true / false）
   - get_relay(): 查询当前工位对应继电器状态（返回 1 或 0）
   - relay_on(): 打开当前工位继电器
   - relay_off(): 关闭当前工位继电器
   - set_all_relays(state=True): 一键全开/全关所有通道

3. 【独立模式/指定通道函数】（用于需要显式指定通道的场景）：
   - set_relay_by_channel(channel, state=True): 指定通道控制开关
   - get_relay_by_channel(channel): 指定通道查询状态
   - relay_on_by_channel(channel): 打开指定通道
   - relay_off_by_channel(channel): 关闭指定通道
"""

import os as _os
import json as _json
import logging as _logging


def _get_relay_board_driver(hardware_manager, test_engine_instance):
    if not hardware_manager:
        raise ValueError("硬件管理器 (hardware_manager) 未提供。")
    station_id = getattr(test_engine_instance, 'station_id', 'station_1') if test_engine_instance else 'station_1'
    return hardware_manager.get_relay_board_driver(station_id), station_id


def _get_shared_channel(test_engine_instance):
    """根据当前工位ID自动解析通道号 (station_1 -> 1, station_2 -> 2, station_3 -> 3, station_4 -> 4)"""
    station_id = getattr(test_engine_instance, 'station_id', 'station_1') if test_engine_instance else 'station_1'
    if str(station_id).startswith("station_"):
        try:
            return int(str(station_id).split("_")[-1])
        except Exception:
            return 1
    return 1


# ==============================================================================
# 1. 串口连接管理函数
# ==============================================================================

def open_serial_port(baudrate=9600, bytesize=8, parity='N', stopbits=1, timeout=1.0,
                     hardware_manager=None, test_engine_instance=None, **kwargs):
    """
    打开并配置继电器板的通信串口。
    建议在测试序列的 Setup 区块中调用。

    :param baudrate: (int) 波特率, 通常为 9600。
    :param bytesize: (int) 数据位, 默认 8。
    :param parity: (str) 校验位, 'N' (无), 'E' (偶), 'O' (奇)。
    :param stopbits: (int) 停止位, 默认 1。
    :param timeout: (float) 超时时间（秒）, 默认 1.0。
    :return: (bool, str) 执行结果。
    """
    try:
        driver, station_id = _get_relay_board_driver(hardware_manager, test_engine_instance)
        driver.open_serial(
            baudrate=baudrate,
            bytesize=bytesize,
            parity=parity,
            stopbits=stopbits,
            timeout=timeout
        )
        return True, f"继电器板串口 {driver.port} 成功打开 (波特率: {baudrate}, 8-{parity}-{stopbits})。"
    except Exception as e:
        err = f"打开继电器板串口失败: {e}"
        _logging.error(err, exc_info=True)
        return False, err


def close_serial_port(hardware_manager=None, test_engine_instance=None, **kwargs):
    """
    关闭继电器板通信串口。
    建议在测试序列的 Cleanup 区块中调用。

    :return: (bool, str) 执行结果。
    """
    try:
        driver, station_id = _get_relay_board_driver(hardware_manager, test_engine_instance)
        driver.close()
        return True, f"继电器板串口 {driver.port} 已成功关闭。"
    except Exception as e:
        err = f"关闭继电器板串口异常: {e}"
        _logging.warning(err)
        return True, f"关闭继电器板串口遇到问题，但测试继续: {e}"


# ==============================================================================
# 2. 【共享模式常用函数】（通道由当前工位自动确定，无需输入 channel）
# ==============================================================================

def set_relay(state=True, hardware_manager=None, test_engine_instance=None, **kwargs):
    """
    [共享模式] 控制当前工位对应的继电器开关（工位1控CH1，工位2控CH2，工位3控CH3，工位4控CH4）。

    :param state: (bool/str/int) True (打开/吸合), False (关闭/断开)
    :return: (bool, str) 执行结果
    """
    try:
        driver, station_id = _get_relay_board_driver(hardware_manager, test_engine_instance)
        channel = _get_shared_channel(test_engine_instance)
        return driver.set_relay(channel=channel, state=state)
    except Exception as e:
        err = f"控制工位 {station_id} 继电器失败: {e}"
        _logging.error(err, exc_info=True)
        return False, err


def get_relay(hardware_manager=None, test_engine_instance=None, **kwargs):
    """
    [共享模式] 查询当前工位对应的继电器状态（工位1查CH1，工位2查CH2...）。

    :return: (int, str) 1 (吸合/ON) 或 0 (断开/OFF)，以及日志信息
    """
    try:
        driver, station_id = _get_relay_board_driver(hardware_manager, test_engine_instance)
        channel = _get_shared_channel(test_engine_instance)
        return driver.query_relay(channel=channel)
    except Exception as e:
        err = f"查询工位 {station_id} 继电器状态失败: {e}"
        _logging.error(err, exc_info=True)
        return False, err


def relay_on(hardware_manager=None, test_engine_instance=None, **kwargs):
    """
    [共享模式] 打开当前工位对应的继电器（无需参数）。

    :return: (bool, str) 执行结果
    """
    return set_relay(state=True, hardware_manager=hardware_manager,
                     test_engine_instance=test_engine_instance, **kwargs)


def relay_off(hardware_manager=None, test_engine_instance=None, **kwargs):
    """
    [共享模式] 关闭当前工位对应的继电器（无需参数）。

    :return: (bool, str) 执行结果
    """
    return set_relay(state=False, hardware_manager=hardware_manager,
                     test_engine_instance=test_engine_instance, **kwargs)


def set_all_relays(state=True, hardware_manager=None, test_engine_instance=None, **kwargs):
    """
    控制所有继电器通道同时打开或关闭。

    :param state: (bool/str/int) True 打开所有, False 关闭所有
    :return: (bool, str) 执行结果
    """
    try:
        driver, station_id = _get_relay_board_driver(hardware_manager, test_engine_instance)
        return driver.set_relay(channel="all", state=state)
    except Exception as e:
        err = f"控制所有继电器失败: {e}"
        _logging.error(err, exc_info=True)
        return False, err


# ==============================================================================
# 3. 【独立模式 / 指定通道函数】（显式指定 channel 控制）
# ==============================================================================

def set_relay_by_channel(channel, state=True, hardware_manager=None, test_engine_instance=None, **kwargs):
    """
    [指定通道模式] 控制指定编号的继电器开关。

    :param channel: (int/str) 通道号 1~8 或 "all"
    :param state: (bool/str/int) True (打开/吸合), False (关闭/断开)
    :return: (bool, str) 执行结果
    """
    try:
        driver, station_id = _get_relay_board_driver(hardware_manager, test_engine_instance)
        return driver.set_relay(channel=channel, state=state)
    except Exception as e:
        err = f"控制继电器通道 {channel} 失败: {e}"
        _logging.error(err, exc_info=True)
        return False, err


def get_relay_by_channel(channel, hardware_manager=None, test_engine_instance=None, **kwargs):
    """
    [指定通道模式] 查询指定编号的继电器状态。

    :param channel: (int/str) 通道号 1~8
    :return: (int, str) 1 (吸合/ON) 或 0 (断开/OFF)，以及日志信息
    """
    try:
        driver, station_id = _get_relay_board_driver(hardware_manager, test_engine_instance)
        return driver.query_relay(channel=channel)
    except Exception as e:
        err = f"查询继电器通道 {channel} 状态失败: {e}"
        _logging.error(err, exc_info=True)
        return False, err


def relay_on_by_channel(channel, hardware_manager=None, test_engine_instance=None, **kwargs):
    """
    [指定通道模式] 打开指定编号的继电器通道。

    :param channel: (int/str) 通道号 1~8
    :return: (bool, str) 执行结果
    """
    return set_relay_by_channel(channel=channel, state=True, hardware_manager=hardware_manager,
                                test_engine_instance=test_engine_instance, **kwargs)


def relay_off_by_channel(channel, hardware_manager=None, test_engine_instance=None, **kwargs):
    """
    [指定通道模式] 关闭指定编号的继电器通道。

    :param channel: (int/str) 通道号 1~8
    :return: (bool, str) 执行结果
    """
    return set_relay_by_channel(channel=channel, state=False, hardware_manager=hardware_manager,
                                test_engine_instance=test_engine_instance, **kwargs)
