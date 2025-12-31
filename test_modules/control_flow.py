# test_modules/control_flow.py
import math
import re

"""
此模块中的函数作为“标记”被测试引擎特殊处理，以实现高级流程控制，
如条件判断 (`IF-ELSE`) 和循环 (`WHILE`)。
"""

def if_variable(condition: str, variables: dict = None):
    """
    IF 条件判断的开始。标志着一个条件块的开始。
    引擎会执行 condition 表达式，如果结果为 True，则继续执行后续步骤；
    如果为 False，则跳转到对应的 else_block 或 end_if。

    :param condition: 一个可被Python `eval()` 函数执行的判断表达式字符串。
                      表达式中的变量名不需要使用花括号。
    :param variables: (由引擎注入) 变量字典。
    :return: (bool, str) 返回条件判断的结果。

    用法示例:
    - 模块: control_flow
    - 函数: if_variable
    - 参数: {"condition": "SF == 48 or SF == 30"}
    """
    variables = variables or {}
    try:
        # 将表达式中的十六进制数字转换为十进制
        condition = re.sub(r'0x[0-9a-fA-F]+', lambda m: str(int(m.group(0), 16)), condition)

        # 创建一个新的字典，用于eval，处理变量值为元组的情况
        eval_locals = {}
        # 正则表达式查找所有可能的变量名
        variable_names = re.findall(r'[a-zA-Z_][a-zA-Z0-9_]*', condition)
        for name in variable_names:
            if name in variables:
                value = variables[name]
                if isinstance(value, tuple) and len(value) > 0:
                    eval_locals[name] = value[0]
                else:
                    eval_locals[name] = value

        # 对于无法解析的复杂表达式或非浮点数比较，回退到标准 eval
        result = eval(condition, {"__builtins__": {}}, eval_locals)
        return result, f"IF 条件 '{condition}' 的结果是 {result}"
    except Exception as e:
        return False, str(e)

def elseif_variable(condition: str, variables: dict = None):
    """
    ELSE IF 条件判断。标志着一个条件块的延续。
    仅当之前的 IF 或 ELSE IF 条件为 False 时，引擎才会执行此步骤的 condition 表达式。
    如果结果为 True，则继续执行后续步骤；
    如果为 False，则跳转到下一个 else_block / elseif_variable 或 end_if。

    :param condition: 一个可被Python `eval()` 函数执行的判断表达式字符串。
    :param variables: (由引擎注入) 变量字典。
    :return: (bool, str) 返回条件判断的结果。
    """
    # The logic is identical to if_variable; the distinction is handled by the TestEngine.
    return if_variable(condition, variables)

def else_block():
    """
    标记 ELSE 块的开始。
    如果之前的 IF 条件为 True，引擎会自动跳过 ELSE 块内的所有内容，直接跳转到 END_IF。
    如果 IF 条件为 False，引擎则会进入此块执行。

    :return: (bool, str) 总是返回成功。

    用法示例:
    - ... (if_variable 及其代码块)
    - 模块: control_flow
    - 函数: else_block
    - ... (else 块内的代码)
    """
    return True, "进入 ELSE 块。"

def end_if():
    """
    标记 IF-ELSE 块的结束。
    这是一个必需的闭合标记，用于界定流程控制块的范围。

    :return: (bool, str) 总是返回成功。
    """
    return True, "结束 IF-ELSE 块。"


def for_loop(count: int = 1):
    """
    FOR 循环的开始。标志着一个循环块的开始。
    引擎会根据 count 的值，重复执行 `for_loop` 和 `end_for` 之间的步骤。

    :param count: 循环的总次数。
    :return: (bool, str) 总是返回成功。

    用法示例:
    - 模块: control_flow
    - 函数: for_loop
    - 参数: {"count": 5}
    """
    return True, f"开始 FOR 循环，共 {count} 次。"


def end_for():
    """
    标记 FOR 循环的结束。
    这是一个必需的闭合标记。当引擎执行到这里，会检查循环次数，
    如果未完成，则跳转回 for_loop 之后，否则继续往下执行。

    :return: (bool, str) 总是返回成功。
    """
    return True, "结束 FOR 循环迭代。"


def break_loop():
    """
    跳出当前循环。
    当引擎执行到此函数，会立即停止当前循环，并跳转到 `end_for` 标记之后。
    此函数必须在 `for_loop` 和 `end_for` 块内部使用。

    :return: (bool, str) 总是返回成功。
    """
    return True, "跳出循环。"