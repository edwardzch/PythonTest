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
import utils.visa_timeout  # 取巧：让 PyInstaller 能扫描并打包这个依赖
from login_dialog import LoginDialog
from main_window import TestApp
from ui_components import COLOR_HIGHLIGHT_BG


def load_plugins(plugin_dir, splash_screen=None):
    """
    从指定目录及其子目录加载插件模块。
    支持从 __pycache__ 目录加载 .pyc 文件。
    修复：正确注册到 sys.modules 以支持模块间导入。
    增强：自动选择与当前 Python 版本匹配的 .pyc 文件。
    """
    loaded_plugins = {}
    target_plugin_path = plugin_path(plugin_dir)
    
    # 获取当前 Python 版本标识（如 "cpython-312"）
    python_version_tag = f"cpython-{sys.version_info.major}{sys.version_info.minor}"
    print(f"当前 Python 版本标识: {python_version_tag}")

    print(f"尝试加载插件目录: {target_plugin_path}")

    if not os.path.exists(target_plugin_path):
        print(f"插件目录 '{target_plugin_path}' 不存在，已自动创建。")
        os.makedirs(target_plugin_path, exist_ok=True)
        return loaded_plugins

    if splash_screen:
        splash_screen.set_message(f"正在从 '{plugin_dir}' 加载插件...")

    print(f"正在从 '{target_plugin_path}' 及其子目录加载插件...")

    # 【关键修复】将项目根目录添加到 sys.path
    project_root = os.path.dirname(os.path.abspath(__file__))
    if project_root not in sys.path:
        sys.path.insert(0, project_root)
        print(f"已添加到 sys.path: {project_root}")
        
    plugin_parent_dir = os.path.dirname(target_plugin_path)
    if plugin_parent_dir not in sys.path:
        sys.path.insert(0, plugin_parent_dir)
        print(f"已添加到 sys.path: {plugin_parent_dir}")

    # 【新增】支持外部第三方库目录 ext_packages，免打包补充 pip 依赖
    ext_packages_dir = os.path.join(plugin_parent_dir, 'ext_packages')
    if os.path.exists(ext_packages_dir) and ext_packages_dir not in sys.path:
        sys.path.insert(0, ext_packages_dir)
        print(f"已挂载外部第三方库目录: {ext_packages_dir}")

    # 【关键修复】注册包本身到 sys.modules
    import types
    if plugin_dir not in sys.modules:
        package_module = types.ModuleType(plugin_dir)
        package_module.__path__ = [target_plugin_path]
        package_module.__package__ = plugin_dir
        sys.modules[plugin_dir] = package_module
        print(f"已注册包: {plugin_dir}")

    # 【新增】收集所有候选文件，然后按优先级选择
    # 优先级：.py > 版本匹配的 .pyc > .pyd > 其他 .pyc
    module_candidates = {}  # {module_name: [(priority, full_path, filename), ...]}
    
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
                    # 判断是否为当前 Python 版本
                    if python_version_tag in filename:
                        priority = 2  # 版本匹配的 .pyc，优先级较高
                    else:
                        priority = 4  # 版本不匹配的 .pyc，优先级最低
                        print(f"  [跳过] {filename} - Python 版本不匹配，当前需要 {python_version_tag}")
                        continue  # 直接跳过版本不匹配的 .pyc
                else:
                    module_name = os.path.splitext(filename)[0]
                    priority = 4
            elif filename.endswith('.pyd'):
                module_name = os.path.splitext(filename)[0]
                priority = 3  # .pyd 优先级中等
            else:  # .py
                module_name = os.path.splitext(filename)[0]
                priority = 1  # .py 优先级最高
            
            if module_name not in module_candidates:
                module_candidates[module_name] = []
            module_candidates[module_name].append((priority, full_path, filename))
    
    # 对每个模块选择优先级最高的文件
    for module_name, candidates in module_candidates.items():
        # 按优先级排序（数字小的优先）
        candidates.sort(key=lambda x: x[0])
        priority, full_path, filename = candidates[0]
        
        # 【关键修复】构建完整的模块路径 (例如 'test_modules.uniflash')
        full_module_name = f"{plugin_dir}.{module_name}"

        try:
            if splash_screen:
                splash_screen.set_message(f"正在加载: {module_name}")

            if filename.endswith('.pyc'):
                # 加载 .pyc 文件
                import marshal

                with open(full_path, 'rb') as f:
                    # 【关键修复】根据 Python 版本动态确定头部大小
                    # Python 3.7+ 的 pyc 头部是 16 字节
                    # Python 3.3-3.6 的 pyc 头部是 12 字节
                    if sys.version_info >= (3, 7):
                        f.read(16)
                    else:
                        f.read(12)
                    code = marshal.load(f)

                module = types.ModuleType(module_name)
                module.__file__ = full_path
                module.__package__ = plugin_dir
                
                # 【关键修复】先注册到 sys.modules，再执行代码
                # 这样模块内的相对/绝对导入才能正确解析
                sys.modules[full_module_name] = module
                sys.modules[module_name] = module  # 也用短名注册，兼容旧代码
                
                exec(code, module.__dict__)
            else:
                # 加载 .py 或 .pyd 文件
                spec = importlib.util.spec_from_file_location(full_module_name, full_path)
                module = importlib.util.module_from_spec(spec)
                
                # 【关键修复】先注册到 sys.modules
                sys.modules[full_module_name] = module
                sys.modules[module_name] = module
                
                spec.loader.exec_module(module)

            loaded_plugins[module_name] = module
            print(f"  - 成功加载插件: {module_name} (注册为 {full_module_name}, 来源: {filename})")

        except Exception as e:
            print(f"加载插件 {filename} 失败: {e}")
            import traceback
            traceback.print_exc()

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
        config_auto_generated = False
        try:
            from utils.app_utils import get_app_base_path
            config_path = os.path.join(get_app_base_path(), 'config.json')
            
            if not os.path.exists(config_path):
                from main_window import TestApp
                print(f"config.json 不存在，正在入口处生成默认配置: {config_path}")
                default_config = TestApp._generate_default_config()
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=4, ensure_ascii=False)
                config_auto_generated = True

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
        
        if getattr(locals(), 'config_auto_generated', False) or 'config_auto_generated' in locals() and config_auto_generated:
            from PySide6.QtWidgets import QMessageBox
            # 现在样式表已经加载完毕，弹窗会继承大字体和深色主题
            QMessageBox.information(None, "提示", 
                "首次运行未找到 config.json，已自动生成默认配置文件。\n\n"
                "初始管理员账号: 工程师\n"
                "初始管理员密码: dorna888\n\n"
                "请在登录后使用左上角「编辑」->「编辑系统配置」\n"
                "根据您的实际硬件地址进行修改验证。")

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
