# test_modules/system.py

"""
此模块包含与测试流程控制和系统级操作相关的函数。
"""

import time

def wait(seconds: float):
    """
    暂停程序执行指定的秒数。

    :param seconds: 需要等待的秒数，可以是小数。
    :return: (bool, str) 执行结果元组。

    用法示例:
    - 模块: system
    - 函数: wait
    - 参数: {"seconds": 0.5}
    """
    try:
        float_seconds = float(seconds)
        time.sleep(float_seconds)
        return True, f"成功等待 {float_seconds} 秒。"
    except (ValueError, TypeError) as e:
        return False, f"等待失败：提供的秒数 '{seconds}' 不是一个有效的数字。错误: {e}"


def set_variable(variables: dict, name: str, value: any):
    """
    在测试流程中设置或创建一个变量。

    :param variables: (由引擎注入) 变量字典。
    :param name: 要设置的变量名。
    :param value: 要设置的变量值。
    :return: (bool, str) 执行结果元组。

    用法示例:
    - 模块: system
    - 函数: set_variable
    - 参数: {"name": "my_var", "value": 10}
    """
    variables[name] = value
    value_str = f'"{value}"' if isinstance(value, str) else str(value)
    return True, f"变量 '{name}' 已被设置为: {value_str}"


def get_variable(variables: dict, name: str):
    """
    获取一个已经存在的变量的值。
    主要作用是将其值作为本步骤的返回值，以便后续步骤可以使用“比较”功能来判断它。

    :param variables: (由引擎注入) 变量字典。
    :param name: 要获取的变量名。
    :return: (any, str) (获取到的值, 描述信息) 或 (False, 错误信息)。

    用法示例:
    - (前序步骤已将值存入变量 'my_var')
    - 模块: system
    - 函数: get_variable
    - 参数: {"name": "my_var"}
    - 比较: ==
    - 最小值: 10
    """
    value = variables.get(name)
    if value is not None:
        return value, f"成功获取到变量 '{name}'"
    else:
        return False, f"获取变量失败: 未找到名为 '{name}' 的变量"


def dummy_pass():
    """
    一个空操作函数，本身什么也不做，总是返回成功。
    主要用途是提供一个“空步骤”，以便利用测试引擎的内置功能，例如对某个变量进行“比较”判断。

    :return: (bool, str) 总是返回成功。

    用法示例 (判断变量值是否在范围内):
    - (前序步骤已将结果存入变量 'my_voltage')
    - 模块: system
    - 函数: dummy_pass
    - 变量: my_voltage  (让引擎将 my_voltage 的值作为本步骤的“结果”)
    - 比较: InRange
    - 最小值: 4.8
    - 最大值: 5.2
    """
    return True, "此步骤仅用于触发引擎的内置变量判断功能。"

def dummy_fail(message: str = "用户主动标记失败"):
    """
    一个空操作函数，它本身什么也不做，总是返回失败。
    主要用于 IF-ELSE 块中，明确地标记出一条不符合预期的测试路径。

    :param message: 您希望在报告中显示的失败信息。
    :return: (bool, str) 总是返回失败。

    用法示例:
    - ...
    - else_block
    - 模块: system
    - 函数: dummy_fail
    - 参数: {"message": "电压不在预期范围内，测试失败"}
    - end_if
    """
    return False, message