# -*- coding: utf-8 -*-
"""
自动化部署构建脚本
"""

import os
import shutil
import subprocess
import sys
import py_compile
from pathlib import Path


def print_step(msg):
    """打印步骤信息"""
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print(f"{'='*60}\n")


def compile_py_to_pyc(source_dir, target_dir):
    """
    将Python源文件编译为.pyc文件
    
    Args:
        source_dir: 源代码目录
        target_dir: 目标.pyc文件目录
    """
    source_path = Path(source_dir)
    target_path = Path(target_dir)
    
    # 创建目标目录
    target_path.mkdir(parents=True, exist_ok=True)
    
    # 遍历源目录中的所有Python文件
    for py_file in source_path.rglob('*.py'):
        # 跳过__pycache__目录
        if '__pycache__' in str(py_file):
            continue
            
        # 计算相对路径
        rel_path = py_file.relative_to(source_path)
        
        # 创建目标子目录
        target_subdir = target_path / rel_path.parent
        target_subdir.mkdir(parents=True, exist_ok=True)
        
        # 编译为.pyc
        pyc_file = target_subdir / f"{py_file.stem}.cpython-{sys.version_info.major}{sys.version_info.minor}.pyc"
        
        try:
            py_compile.compile(str(py_file), str(pyc_file), doraise=True)
            print(f"  ✓ 编译: {rel_path} -> {pyc_file.name}")
        except Exception as e:
            print(f"  ✗ 编译失败: {rel_path} - {e}")


def main():
    """主构建流程"""
    # 获取项目根目录
    project_root = Path(__file__).parent.absolute()
    os.chdir(project_root)
    
    print_step("步骤 1/6: 构建 TestApp.exe")
    result = subprocess.run([sys.executable, '-m', 'PyInstaller', 'main.spec', '--clean'], 
                          capture_output=False)
    if result.returncode != 0:
        print("✗ TestApp.exe 构建失败！")
        return 1
    print("✓ TestApp.exe 构建成功")
    
    print_step("步骤 2/6: 构建 launcher.exe")
    result = subprocess.run([sys.executable, '-m', 'PyInstaller', 'launcher.spec', '--clean'], 
                          capture_output=False)
    if result.returncode != 0:
        print("✗ launcher.exe 构建失败！")
        return 1
    print("✓ launcher.exe 构建成功")
    
    print_step("步骤 3/6: 创建 TestApp_Deployment 目录结构")
    deployment_root = project_root / 'TestApp_Deployment'
    
    # 清理旧的部署目录
    if deployment_root.exists():
        shutil.rmtree(deployment_root)
    
    # 创建目录结构
    drivers_dir = deployment_root / 'drivers'
    test_modules_dir = deployment_root / 'test_modules'
    testapp_dir = deployment_root / 'TestApp'
    
    (drivers_dir / 'real').mkdir(parents=True, exist_ok=True)
    (drivers_dir / 'simulation').mkdir(parents=True, exist_ok=True)
    test_modules_dir.mkdir(parents=True, exist_ok=True)
    testapp_dir.mkdir(parents=True, exist_ok=True)
    print("✓ 目录结构创建成功")
    
    print_step("步骤 4/6: 编译 Python 模块为 .pyc")
    # 编译 drivers
    print("编译 drivers/real...")
    compile_py_to_pyc(project_root / 'drivers' / 'real', drivers_dir / 'real')
    
    print("\n编译 drivers/simulation...")
    compile_py_to_pyc(project_root / 'drivers' / 'simulation', drivers_dir / 'simulation')
    
    print("\n编译 test_modules...")
    compile_py_to_pyc(project_root / 'test_modules', test_modules_dir)
    
    print("✓ 所有模块编译完成")
    
    print_step("步骤 5/6: 复制可执行文件和配置")
    # 复制 TestApp.exe
    testapp_exe = project_root / 'dist' / 'TestApp_V1.0.exe'
    if testapp_exe.exists():
        shutil.copy2(testapp_exe, testapp_dir / 'TestApp_V1.0.exe')
        print(f"✓ 复制 TestApp_V1.0.exe")
    else:
        print(f"✗ 找不到 {testapp_exe}")
        return 1
    
    # 复制 launcher.exe
    launcher_exe = project_root / 'dist' / 'launcher.exe'
    if launcher_exe.exists():
        shutil.copy2(launcher_exe, testapp_dir / 'launcher.exe')
        print(f"✓ 复制 launcher.exe")
    else:
        print(f"✗ 找不到 {launcher_exe}")
        return 1
    
    # 复制 config.json
    config_file = project_root / 'config.json'
    if config_file.exists():
        shutil.copy2(config_file, testapp_dir / 'config.json')
        print(f"✓ 复制 config.json")
    else:
        print(f"✗ 找不到 config.json")
        return 1
    
    # 如果 app_config.json 存在，也复制过去
    app_config_file = project_root / 'app_config.json'
    if app_config_file.exists():
        shutil.copy2(app_config_file, testapp_dir / 'app_config.json')
        print(f"✓ 复制 app_config.json")
    
    # 创建其他必要的目录
    (testapp_dir / 'sequences').mkdir(exist_ok=True)
    (testapp_dir / 'CycleTestReports').mkdir(exist_ok=True)
    (testapp_dir / 'SnifferReports').mkdir(exist_ok=True)
    print("✓ 创建运行时目录")
    
    # 复制templates目录
    templates_src = project_root / 'templates'
    if templates_src.exists():
        shutil.copytree(templates_src, testapp_dir / 'templates', dirs_exist_ok=True)
        print("✓ 复制 templates 目录")
    
    print_step("步骤 6/6: 创建部署指南")
    guide_content = """TestApp 部署指南
================

1. 目录结构：
   TestApp_Deployment/
   ├── drivers/               # 驱动模块（.pyc）
   ├── test_modules/          # 测试模块（.pyc）
   └── TestApp/              # 主应用程序
       ├── launcher.exe      # 启动器（双击运行此文件）
       ├── TestApp_V1.0.exe  # 主程序
       ├── config.json       # 配置文件
       ├── sequences/        # 测试序列目录
       ├── CycleTestReports/ # 循环测试报告
       └── SnifferReports/   # 串口抓包报告

2. 运行方式：
   双击 launcher.exe 启动应用程序

3. 配置修改：
   编辑 config.json 文件修改硬件配置

4. 更新程序：
   - 替换 TestApp_V1.0.exe 为新版本
   - 如需更新测试模块或驱动，替换对应的 .pyc 文件
   - 修改配置后重启程序生效

构建时间: """ + subprocess.check_output(['powershell', 'Get-Date'], text=True).strip() + "\n"
    
    (deployment_root / 'DeploymentGuide.txt').write_text(guide_content, encoding='utf-8')
    print("✓ 部署指南创建成功")
    
    print_step("✅ 部署构建完成！")
    print(f"部署目录: {deployment_root.absolute()}")
    print(f"\n启动方式: 运行 {testapp_dir / 'launcher.exe'}")
    
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except Exception as e:
        print(f"\n❌ 构建过程出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
