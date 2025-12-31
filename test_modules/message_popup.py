# test_modules/message_popup.py

"""
此模块提供消息弹框功能，类似 TestStand 的 Message Popup。
可以在测试序列中显示消息对话框，并获取用户的响应。

【重要】此模块现在通过 TestEngine 请求主线程显示 UI，是线程安全的。
"""

def show_message(test_engine_instance, message: str, title: str = "提示", buttons: str = "OK", icon: str = "Information"):
    """
    显示一个消息弹框，等待用户响应。
    
    :param test_engine_instance: (由引擎注入) TestEngine 实例
    :param message: 要显示的消息内容
    :param title: 对话框标题
    :param buttons: 按钮类型 (OK, OKCancel, YesNo, YesNoCancel, RetryCancel)
    :param icon: 图标类型 (Information, Warning, Critical, Question, NoIcon)
    :return: (str, str) 返回 (用户的选择, 描述信息)
    
    用法示例 1 - 简单提示：
    - 模块: message_popup
    - 函数: show_message
    - 参数: {"message": "请确认设备已正确连接"}
    - 依赖: test_engine_instance (自动注入)
    
    用法示例 2 - 询问用户：
    - 模块: message_popup
    - 函数: show_message
    - 参数: {"message": "测试失败，是否继续？", "title": "测试确认", "buttons": "YesNo", "icon": "Question"}
    - 变量: user_choice  (将用户的选择保存到变量)
    - 依赖: test_engine_instance (自动注入)
    
    用法示例 3 - 后续判断用户选择：
    - (前序步骤已将用户选择保存到 'user_choice')
    - 模块: control_flow
    - 函数: if_condition
    - 参数: {"condition": "user_choice == 'Yes'"}
    """
    if not test_engine_instance:
        return "FAIL", "TestEngine 实例未注入，无法显示弹框"
        
    try:
        # 通过引擎请求主线程显示弹框
        user_choice = test_engine_instance.request_user_interaction(
            'message_box',
            title=title,
            message=message,
            buttons=buttons,
            icon=icon
        )
        
        return user_choice, f"用户选择: {user_choice}"
    except Exception as e:
        return "FAIL", f"显示弹框失败: {e}"


def show_input(test_engine_instance, prompt: str, title: str = "输入", default_value: str = ""):
    """
    显示一个输入对话框，让用户输入文本。
    
    :param test_engine_instance: (由引擎注入) TestEngine 实例
    :param prompt: 提示信息
    :param title: 对话框标题
    :param default_value: 默认值
    :return: (str, str) 返回 (用户输入的文本, 描述信息)
    """
    if not test_engine_instance:
        return "FAIL", "TestEngine 实例未注入，无法显示弹框"
        
    try:
        # 通过引擎请求主线程显示输入框
        user_input = test_engine_instance.request_user_interaction(
            'input_box',
            title=title,
            prompt=prompt,
            default_value=default_value
        )
        
        if user_input is False or user_input is None:
            return False, "用户取消输入"
        else:
            return user_input, f"用户输入: {user_input}"
            
    except Exception as e:
        return "FAIL", f"显示输入框失败: {e}"


def confirm(test_engine_instance, message: str, title: str = "确认"):
    """
    显示一个确认对话框（是/否）。
    """
    choice, msg = show_message(test_engine_instance, message, title, buttons="YesNo", icon="Question")
    
    if choice == "Yes":
        return True, f"用户确认: {message}"
    else:
        return False, f"用户取消: {message}"


def alert(test_engine_instance, message: str, title: str = "警告"):
    """
    显示一个警告对话框。
    """
    show_message(test_engine_instance, message, title, buttons="OK", icon="Warning")
    return True, f"已显示警告: {message}"


def error(test_engine_instance, message: str, title: str = "错误"):
    """
    显示一个错误对话框。
    """
    show_message(test_engine_instance, message, title, buttons="OK", icon="Critical")
    return False, f"错误: {message}"
