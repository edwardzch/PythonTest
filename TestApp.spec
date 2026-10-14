# main.spec
# -*- mode: python ; coding: utf-8 -*-

import os
import glob

block_cipher = None

# 【【【重要】】】 我们不再需要 project_dir 变量了，以避免路径混淆

# -------------------------
# libusb-1.0.dll 的搜索 (保持原样，这个影响不大)
# -------------------------
libusb_paths = glob.glob(
    os.path.join(
        os.getcwd(),
        ".venv",
        "Lib",
        "site-packages",
        "libusb_package",
        "**",
        "libusb-1.0.dll"
    ),
    recursive=True
)
binaries = []
if libusb_paths:
    binaries.append((libusb_paths[0], '.'))
else:
    print("WARNING: libusb-1.0.dll 未找到，将无法使用 USB-TMC (DP832)。")


# -------------------------------------------------------------
# 【【【核心修正】】】 使用函数动态、明确地收集所有需要的文件
# -------------------------------------------------------------
def collect_files(folder):
    """
    递归地收集一个文件夹下的所有文件，并为 PyInstaller 的 'datas' 生成元组列表。
    返回的元组格式为 (源文件路径, 在打包文件中的目标文件夹路径)。
    """
    file_list = []
    for root, _, files in os.walk(folder):
        for file in files:
            full_path = os.path.join(root, file)
            # 'dest_path' 是相对于应用根目录的路径
            # 例如, 'static/js/chart.js' -> 'static/js'
            dest_path = os.path.relpath(root, '.')
            file_list.append((full_path, dest_path))
    return file_list

datas = [
    ('app_icon.ico', '.'),
    ('visa.conf', '.'),
]

# 添加 templates 和 static 目录下的所有文件
datas.extend(collect_files('templates'))
datas.extend(collect_files('static'))


# -------------------------
# hiddenimports 保持不变
# -------------------------
hiddenimports = [
    'PySide6', 'PySide6.QtWidgets', 'PySide6.QtGui', 'PySide6.QtCore', 'PySide6.QtWebEngineWidgets',
    'qt_material', 'pandas', 'numpy', 'matplotlib', 'pyserial', 'pyvisa', 'pyvisa_py',
    'pyvisa_py.highlevel', 'pyvisa_py.usb', 'pyvisa_py.usb.usbtmc', 'pyvisa_py.usb.usb_backend',
    'pyvisa_py.protocols', 'pyvisa_py.protocols.usb', 'minimalmodbus', 'pyusb', 'libusb-package',
    'flask', 'werkzeug', 'jinja2', 'markupsafe', 'itsdangerous', 'click', 'colorama', 'filelock',
]


a = Analysis(
    ['main.py'],
    # 【【【核心修正】】】 删除硬编码的 pathex，让PyInstaller自动处理
    pathex=[], # <-- 直接留空或删除此行
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],  # 改为空列表，不再将所有文件打包到 exe 中
    exclude_binaries=True,  # 排除二进制文件，这些会在 COLLECT 中处理
    name='TestApp_V2.3.0',  # 更新版本号为 2.3.0
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # 不显示控制台窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='app_icon.ico',
    version='version_info.txt' if os.path.exists('version_info.txt') else None,
)

# COLLECT 用于生成 --onedir 模式的输出文件夹
coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='TestApp_V2.3.0',
)
