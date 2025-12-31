import os
import sys

def get_app_base_path():
    """
    可靠地获取应用程序的根目录。
    这是所有需要与EXE文件在同一目录下的文件的基础路径（如 config.json, test_history.db）。

    - 在打包的EXE中，这是EXE文件所在的目录。
    - 在开发环境中，这是项目的主目录（通常是包含 main.py 的目录）。
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # 如果程序被PyInstaller打包，sys.executable指向EXE文件
        return os.path.dirname(sys.executable)
    else:
        # 在开发环境中运行.py文件
        # os.path.abspath(".") 返回当前工作目录，通常是项目根目录
        return os.path.abspath(".")

def resource_path(relative_path):
    """
    获取内部资源的绝对路径，这是诊断的核心函数。
    """
    try:
        # PyInstaller创建一个临时文件夹并将路径存储在_MEIPASS中
        base_path = sys._MEIPASS
    except Exception:
        # 在开发环境中
        base_path = get_app_base_path()

    final_path = os.path.join(base_path, relative_path)
    return final_path


def plugin_path(relative_path):
    """
    获取外部插件目录的绝对路径。
    此函数保留了您独特的逻辑：在打包后，插件目录位于EXE的上级目录。
    """
    if getattr(sys, 'frozen', False) and hasattr(sys, '_MEIPASS'):
        # 作为打包后的EXE运行
        # 1. 获取EXE所在的目录
        exe_dir = get_app_base_path()
        # 2. 从EXE目录上移一级，到达您期望的插件根目录
        plugin_root = os.path.abspath(os.path.join(exe_dir, os.pardir))
        return os.path.join(plugin_root, relative_path)
    else:
        # 在开发环境中运行
        # 插件目录位于项目根目录下
        return os.path.join(get_app_base_path(), relative_path)

