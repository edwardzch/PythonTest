# test_modules/math_utils.py
"""
此模块提供通用的数学计算功能。
"""

import re

def calculate(expression: str, variables: dict):
    """
    评估一个包含变量的数学表达式。
    此函数直接计算表达式字符串，并能在给定的变量字典中查找变量的值。
    变量名不需要使用花括号。

    :param expression: 数学表达式字符串。例如: "voltage / 4096 * 5"
    :param variables: (由引擎注入) 包含了当前作用域内所有可用变量的字典。
    :return: 如果计算成功，返回计算结果 (一个数字)。如果失败，返回 (False, 错误信息)。

    用法示例:
    - (前序步骤已将值存入变量 'voltage')
    - 模块: math_utils
    - 函数: calculate
    - 参数: {"expression": "voltage / 4096 * 5"}
    - 变量: actual_voltage
    """
    try:
        # 提供一个受限的 globals 环境，只允许安全的内建函数，增强安全性。
        # 这里允许了 'abs', 'round', 'min', 'max' 等常用数学函数。
        safe_globals = {
            "__builtins__": {
                "abs": abs,
                "round": round,
                "min": min,
                "max": max,
                "pow": pow,
            }
        }

        # 创建一个新的字典，用于eval，处理变量值为元组的情况
        eval_locals = {}
        # 正则表达式查找所有可能的变量名
        variable_names = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', expression)
        for name in variable_names:
            if name in variables:
                value = variables[name]
                if isinstance(value, tuple) and len(value) > 0:
                    eval_locals[name] = value[0]
                else:
                    eval_locals[name] = value

        # 直接使用 eval, 将处理过的变量字典作为局部变量上下文传入。
        result = eval(expression, safe_globals, eval_locals)
        
        return result

    except NameError as e:
        # 捕获因为找不到变量而产生的 NameError
        return False, f"计算错误: {e}. 请确保表达式中使用的变量名正确，并且在该步骤之前已被赋值。"
    except Exception as e:
        # 捕获其他所有可能的计算异常
        return False, f"计算表达式时发生错误: {e}"