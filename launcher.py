# -*- coding: utf-8 -*-
"""
轻量级启动器 - 显示启动画面并启动主应用
"""

import sys
import os
import subprocess
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QPixmap
from PySide6.QtCore import QTimer

from utils.app_utils import resource_path
from utils.splash_screen import SplashScreen


# 【重要】添加外部插件目录到Python路径
# 即使在launcher中也需要添加，确保启动的TestApp能找到插件
if getattr(sys, 'frozen', False):
    # 打包后的exe环境
    exe_dir = os.path.dirname(sys.executable)
    parent_dir = os.path.abspath(os.path.join(exe_dir, os.pardir))
    
    # 添加 drivers 和 test_modules 目录到 sys.path
    drivers_path = os.path.join(parent_dir, 'drivers')
    test_modules_path = os.path.join(parent_dir, 'test_modules')
    
    if drivers_path not in sys.path:
        sys.path.insert(0, drivers_path)
    
    if test_modules_path not in sys.path:
        sys.path.insert(0, test_modules_path)


def main():
    """启动器主函数"""
    app = QApplication(sys.argv)
    
    # 显示启动画面
    pixmap = QPixmap(resource_path('app_icon.ico'))
    splash = SplashScreen(pixmap)
    splash.show()
    splash.set_message("正在启动测试平台...")
    
    app.processEvents()
    
    # 获取 TestApp.exe 的路径
    if getattr(sys, 'frozen', False):
        # 如果是打包后的exe
        launcher_dir = os.path.dirname(sys.executable)
        
        # 优先查找 TestApp_V1.1.0.exe，否则查找任何 TestApp*.exe
        testapp_exe = os.path.join(launcher_dir, 'TestApp_V1.1.0.exe')
        
        if not os.path.exists(testapp_exe):
            # 尝试查找任何 TestApp 开头的 exe
            import glob
            pattern = os.path.join(launcher_dir, 'TestApp*.exe')
            matches = glob.glob(pattern)
            if matches:
                testapp_exe = matches[0]
                print(f"找到 TestApp: {os.path.basename(testapp_exe)}")
    else:
        # 开发环境
        testapp_exe = os.path.join(os.path.dirname(__file__), 'main.py')
    
    # 检查 TestApp 是否存在
    if not os.path.exists(testapp_exe):
        splash.set_message(f"错误: 找不到 TestApp 可执行文件")
        QTimer.singleShot(3000, app.quit)
        return app.exec()
    
    # 延迟启动主应用（给用户看到启动画面）
    def launch_testapp():
        splash.set_message("正在加载主程序...")
        app.processEvents()
        
        # 启动 TestApp，传递参数表明由 launcher 启动
        if testapp_exe.endswith('.py'):
            # 开发环境
            subprocess.Popen([sys.executable, testapp_exe, '--launched-by-launcher'])
        else:
            # 生产环境
            subprocess.Popen([testapp_exe, '--launched-by-launcher'])
        
        # 关闭启动画面和launcher
        splash.close()
        app.quit()
    
    # 1秒后启动主应用
    QTimer.singleShot(1000, launch_testapp)
    
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
