# test_modules/datetime_utils.py
"""
此模块提供获取当前日期和时间各个部分的函数。
"""

from datetime import datetime

def get_year():
    """
    获取当前年份的后两位。
    例如，如果是2025年，则返回整数 25。

    :return: (int) 当前年份的后两位。

    用法示例:
    - 模块: datetime_utils
    - 函数: get_year
    - 变量: YEAR
    """
    return datetime.now().year % 100

def get_month():
    """
    获取当前月份。

    :return: (int) 当前月份 (1-12)。

    用法示例:
    - 模块: datetime_utils
    - 函数: get_month
    - 变量: MONTH
    """
    return datetime.now().month

def get_day():
    """
    获取当前是月份中的第几天。

    :return: (int) 当前日期 (1-31)。

    用法示例:
    - 模块: datetime_utils
    - 函数: get_day
    - 变量: DAY
    """
    return datetime.now().day

def get_hour():
    """
    获取当前小时 (24小时制)。

    :return: (int) 当前小时 (0-23)。

    用法示例:
    - 模块: datetime_utils
    - 函数: get_hour
    - 变量: HOUR
    """
    return datetime.now().hour

def get_minute():
    """
    获取当前分钟。

    :return: (int) 当前分钟 (0-59)。

    用法示例:
    - 模块: datetime_utils
    - 函数: get_minute
    - 变量: MINUTE
    """
    return datetime.now().minute

def get_second():
    """
    获取当前秒数。

    :return: (int) 当前秒数 (0-59)。

    用法示例:
    - 模块: datetime_utils
    - 函数: get_second
    - 变量: SECOND
    """
    return datetime.now().second