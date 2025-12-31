# -*- coding: utf-8 -*-
"""
应用程序主入口。
"""

import sys
import os
import importlib.util

from PySide6.QtWidgets import QApplication, QDialog
from PySide6.QtGui import QPixmap

from utils.app_utils import resource_path, plugin_path
from utils.splash_screen import SplashScreen
from login_dialog import LoginDialog
from main_window import TestApp
from ui_components import COLOR_HIGHLIGHT_BG


def load_plugins(plugin_dir, splash_screen=None):
    """
    从指定目录及其子目录加载插件模块。
    支持从 __pycache__ 目录加载 .pyc 文件。
    """
    loaded_plugins = {}
    target_plugin_path = plugin_path(plugin_dir)

    print(f"尝试加载插件目录: {target_plugin_path}")

    if not os.path.exists(target_plugin_path):
        print(f"插件目录 '{target_plugin_path}' 不存在，已自动创建。")
        os.makedirs(target_plugin_path, exist_ok=True)
        return loaded_plugins

    if splash_screen:
        splash_screen.set_message(f"正在从 '{plugin_dir}' 加载插件...")

    print(f"正在从 '{target_plugin_path}' 及其子目录加载插件...")

    for root, dirs, files in os.walk(target_plugin_path):
        # 只跳过以 __ 开头的目录（如 __pycache__）
        dirs[:] = [d for d in dirs if not d.startswith('__')]
        
        for filename in files:
            # 支持 .py, .pyc 和 .pyd 文件
            if not (filename.endswith('.py') or filename.endswith('.pyc') or filename.endswith('.pyd')):
                continue
            if filename.startswith('__'):
                continue

            full_path = os.path.join(root, filename)
            
            # 提取模块名
            if filename.endswith('.pyc'):
                # 处理 .cpython-312.pyc 这种格式
                if '.cpython-' in filename:
                    module_name = filename.split('.')[0]
                else:
                    module_name = os.path.splitext(filename)[0]
            elif filename.endswith('.pyd'):
                module_name = os.path.splitext(filename)[0]
            else:  # .py
                module_name = os.path.splitext(filename)[0]

            try:
                if splash_screen:
                    splash_screen.set_message(f"正在加载: {module_name}")

                if filename.endswith('.pyc'):
                    # 加载 .pyc 文件
                    import marshal
                    import types

                    with open(full_path, 'rb') as f:
                        f.read(16)  # 跳过头部
                        code = marshal.load(f)

                    module = types.ModuleType(module_name)
                    exec(code, module.__dict__)
                else:
                    # 加载 .py 或 .pyd 文件
                    spec = importlib.util.spec_from_file_location(module_name, full_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

                loaded_plugins[module_name] = module
                print(f"  - 成功加载插件: {module_name}")

            except Exception as e:
                print(f"加载插件 {filename} 失败: {e}")

    return loaded_plugins


if __name__ == "__main__":
    app = QApplication(sys.argv)

    pixmap = QPixmap(resource_path('app_icon.ico'))
    splash = SplashScreen(pixmap)
    splash.show()

    app.processEvents()

    # 1. 首先应用所有样式
    try:
        from qt_material import apply_stylesheet
        
        # 从配置文件读取主题设置
        import json
        config_theme = 'dark_teal.xml'  # 默认主题
        try:
            from utils.app_utils import get_app_base_path
            config_path = os.path.join(get_app_base_path(), 'config.json')
            with open(config_path, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
                config_theme = config_data.get('ui_theme', 'dark_teal.xml')
        except Exception as cfg_err:
            print(f"读取主题配置失败，使用默认主题: {cfg_err}")
        
        extra = {'density_scale': '-2'}
        apply_stylesheet(app, theme=config_theme, extra=extra)
        
        current_stylesheet = app.styleSheet()
        
        # 修复并覆盖颜色
        fixed_good_rule = f"selection-background-color: {COLOR_HIGHLIGHT_BG.name()};"
        fixed_stylesheet = current_stylesheet.replace("selection-background-color: #6effe8;", fixed_good_rule)

        # 计算大字体大小 (+12)
        base_pt = app.font().pointSize()
        if base_pt <= 0: base_pt = 9
        dialog_font_size = base_pt + 12
        
        override_stylesheet = f"""
            QMessageBox, QInputDialog {{
                font-size: {dialog_font_size}pt;
            }}
            QMessageBox QLabel, QInputDialog QLabel, 
            QMessageBox QPushButton, QInputDialog QPushButton,
            QMessageBox QLineEdit, QInputDialog QLineEdit,
            QMessageBox QComboBox, QInputDialog QComboBox {{
                font-size: {dialog_font_size}pt;
            }}
            QTableView::item:selected, 
            QTableWidget::item:selected {{
                background-color: {COLOR_HIGHLIGHT_BG.name()};
            }}
            QTableView::item:selected:focus, 
            QTableWidget::item:selected:focus {{
                 background-color: {COLOR_HIGHLIGHT_BG.name()};
                 color: white;
            }}
            QMenuBar::item:selected, 
            QMenuBar::item:pressed {{
                background-color: {COLOR_HIGHLIGHT_BG.name()};
                color: white;
            }}
            QMenu::item:selected {{
                background-color: {COLOR_HIGHLIGHT_BG.name()};
                color: white;
            }}
            QComboBox::item:selected {{
                background-color: {COLOR_HIGHLIGHT_BG.name()};
                color: white;
            }}
            QLineEdit#active_sn_input {{
                background-color: #d9f7d9;
                color: black;
            }}
        """
        app.setStyleSheet(fixed_stylesheet + override_stylesheet)

    except ImportError:
        print("qt_material 未找到。使用默认的应用样式。" )

    # 2. 然后加载插件
    splash.set_message("加载测试模块...")
    test_modules = load_plugins('test_modules', splash)
    splash.set_message("加载驱动程序...")
    drivers = load_plugins('drivers', splash)

    # 3. 最后显示登录对话框
    login_dialog = LoginDialog()
    if login_dialog.exec() == QDialog.Accepted:
        user_info = login_dialog.get_user_info()
        splash.set_message(f"用户 '{user_info['id']}' 登录成功...")
    else:
        # 如果登录被取消或失败，则退出应用
        splash.hide()
        sys.exit(0)

    # 创建并显示主窗口
    window = TestApp(splash, user_info, test_modules=test_modules, drivers=drivers)
    window.showMaximized()
    splash.finish(window)
    sys.exit(app.exec())
