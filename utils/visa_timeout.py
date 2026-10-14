"""
VISA 通信超时保护工具。

当 pyvisa-py 底层 libusb 卡死时，VISA timeout 可能不会生效。
此模块提供 Python 级别的超时保护，使用 daemon 线程确保即使底层卡死也能超时返回。
"""

import threading
import logging

logger = logging.getLogger(__name__)

# 默认 VISA I/O 超时（秒）
DEFAULT_VISA_IO_TIMEOUT = 8


def visa_call_with_timeout(func, args=(), kwargs=None, timeout=DEFAULT_VISA_IO_TIMEOUT):
    """
    在子线程中执行 VISA 调用，主线程等待指定超时。
    
    - 如果调用在 timeout 内完成，返回结果
    - 如果超时未返回，抛出 TimeoutError
    - 如果调用抛出异常，重新抛出原始异常
    
    :param func: 要执行的函数
    :param args: 函数参数
    :param kwargs: 函数关键字参数
    :param timeout: 超时时间（秒）
    :return: func 的返回值
    :raises TimeoutError: 超时时抛出
    """
    result = [None]
    exception = [None]

    def wrapper():
        try:
            result[0] = func(*args, **(kwargs or {}))
        except Exception as e:
            exception[0] = e

    t = threading.Thread(target=wrapper, daemon=True)
    t.start()
    t.join(timeout=timeout)

    if t.is_alive():
        func_name = getattr(func, '__name__', str(func))
        raise TimeoutError(f"VISA 调用 '{func_name}' 超时 ({timeout}s)，设备可能无响应。")
    if exception[0]:
        raise exception[0]
    return result[0]
