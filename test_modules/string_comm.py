# test_modules/string_comm.py
"""
此模块提供基于字符串的请求-响应式通信功能。
主要用于向串口发送文本命令，并接收文本回复。
"""

import logging

TERMINATOR = '\r\n'  # 命令结束符：回车+换行 (CRLF)

def send_sn(variables: dict, hardware_manager=None, test_engine_instance=None, **kwargs):
    """
    通过串口发送当前产品的SN码。
    此函数会自动从测试流程的变量中获取 `uut_sn` 并发送，通常用于通知下位机测试开始。
    发送的SN码会自动附加一个回车换行符 (CRLF) 作为结束标志。

    :param variables: (由引擎注入) 包含 `uut_sn` 的变量字典。
    :return: (bool, str) 执行结果。

    用法示例:
    - 模块: string_comm
    - 函数: send_sn
    - 参数: (留空)
    """
    logger = kwargs.get("logger", logging.getLogger())
    try:
        station_id = test_engine_instance.station_id
        comm_port = test_engine_instance.global_config['stations'][station_id]['comm_port']
    except KeyError:
        return False, "配置错误: 未能从测试引擎配置中找到当前工位的 comm_port"

    uut_sn = variables.get('uut_sn')
    if not uut_sn: return False, "未能从变量中获取SN码 (uut_sn)"
    
    try:
        data_to_send = uut_sn + TERMINATOR
        logger.info(f"正在向端口 {comm_port} 写入原始SN: {repr(data_to_send)}")
        hardware_manager.write_raw_string(comm_port, data_to_send)
        return True, f"SN '{uut_sn}' 发送成功"
    except Exception as e:
        logger.error(f"发送原始SN时发生错误: {e}", exc_info=True)
        return False, f"发送SN失败: {e}"

def request_and_get_string(cmd: str, hardware_manager=None, test_engine_instance=None, **kwargs):
    """
    通过串口发送一个自定义命令，并等待接收一行字符串作为返回。
    发送的命令会自动附加回车换行符 (CRLF)。
    函数会等待并读取设备返回的一行字符串（以换行符为结束）。

    :param cmd: 要发送的字符串命令。
    :return: (str, str) 或 (False, str)。成功时返回 (读取到的字符串, 成功信息)，失败时返回 (False, 错误信息)。

    用法示例:
    - 模块: string_comm
    - 函数: request_and_get_string
    - 参数: {"cmd": "GET_VERSION"}
    - 变量: fw_version
    - 比较: Contains
    - 最小值: "V1.2"
    """
    logger = kwargs.get("logger", logging.getLogger())
    try:
        station_id = test_engine_instance.station_id
        comm_port = test_engine_instance.global_config['stations'][station_id]['comm_port']
    except KeyError:
        return False, "配置错误: 未能从测试引擎配置中找到当前工位的 comm_port"

    if not cmd:
        return False, '参数错误: 请在Parameters列中设置 "cmd": "YourCommand"'

    try:
        data_to_send = cmd + TERMINATOR
        logger.info(f"正在向端口 {comm_port} 发送请求: {repr(data_to_send)}")
        response_string = hardware_manager.write_then_read_raw_string(comm_port, data_to_send)
        if response_string == "":
            return False, f"请求 '{cmd}' 后无响应或超时"
        return response_string, f"接收到: {response_string}"
    except Exception as e:
        logger.error(f"请求/获取字符串时发生错误: {e}", exc_info=True)
        return False, f"请求/获取字符串失败: {e}"
