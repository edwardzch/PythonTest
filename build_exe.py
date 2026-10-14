# -*- coding: utf-8 -*-
"""
自动化测试平台 - 智能一键打包脚本 (build_exe.py)

功能特性：
1. 自动从 constants.py 读取最新的 APP_VERSION (例如 2.3.0)。
2. 自动生成 Windows PE 格式的版本信息文件 (file_version_info.txt)，注入 exe 属性。
3. 自动同步更新 TestApp.spec 中的打包输出名称 (TestApp_V{version})。
4. 调用 PyInstaller 自动化构建，并清理临时构建缓存。
5. 打包完成后输出最终产物路径与大小。
"""

import os
import sys
import re
import shutil
import subprocess
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def get_current_version():
    """从 constants.py 解析当前版本号"""
    constants_file = os.path.join(BASE_DIR, "constants.py")
    if os.path.exists(constants_file):
        with open(constants_file, "r", encoding="utf-8") as f:
            content = f.read()
            match = re.search(r'APP_VERSION\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1).strip()
    return "2.3.0"


def parse_version_tuple(version_str):
    """将类似 '2.3.0' 或 '2.3.0.1' 转换为 4 位整数元组 (2, 3, 0, 0)"""
    parts = re.findall(r'\d+', version_str)
    while len(parts) < 4:
        parts.append('0')
    return tuple(int(p) for p in parts[:4])


def generate_version_info_file(version_str, target_path):
    """生成适用于 PyInstaller 的 Windows 版本信息文件"""
    v_tuple = parse_version_tuple(version_str)
    v_str = f"{v_tuple[0]}.{v_tuple[1]}.{v_tuple[2]}.{v_tuple[3]}"
    
    content = f"""# UTF-8
#
# Windows PE 可执行文件属性版本信息
# 自动生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}
#

VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={v_tuple},
    prodvers={v_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        '080404b0',
        [StringStruct('CompanyName', '自动化测试平台'),
        StringStruct('FileDescription', '多工位自动化测试与测控集成系统'),
        StringStruct('FileVersion', '{version_str}'),
        StringStruct('InternalName', 'TestApp'),
        StringStruct('LegalCopyright', 'Copyright © 2026'),
        StringStruct('OriginalFilename', 'TestApp_V{version_str}.exe'),
        StringStruct('ProductName', '自动化测试平台'),
        StringStruct('ProductVersion', '{version_str}')])
      ]
    ),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[1/4] 成功生成 Windows 版本属性信息文件: {os.path.basename(target_path)} (版本: {version_str})")


def sync_spec_file(version_str):
    """同步更新 TestApp.spec 中的版本号名称"""
    spec_path = os.path.join(BASE_DIR, "TestApp.spec")
    if not os.path.exists(spec_path):
        print(f"[警告] 未找到 {spec_path} 文件！")
        return

    with open(spec_path, "r", encoding="utf-8") as f:
        spec_content = f.read()

    # 替换 name='TestApp_V...'
    new_name = f"TestApp_V{version_str}"
    updated_content = re.sub(
        r"name\s*=\s*['\"]TestApp_V[^'\"]*['\"]",
        f"name='{new_name}'",
        spec_content
    )

    # 确保加入 version 属性
    if "version='version_info.txt'" not in updated_content and "version=" not in updated_content:
        updated_content = re.sub(
            r"(icon\s*=\s*['\"][^'\"]*['\"],?)",
            r"\1\n    version='version_info.txt',",
            updated_content
        )

    with open(spec_path, "w", encoding="utf-8") as f:
        f.write(updated_content)

    print(f"[2/4] 成功同步 TestApp.spec 打包配置 -> 输出名称: {new_name}")


def clean_build_cache():
    """清理历史构建缓存目录"""
    build_dir = os.path.join(BASE_DIR, "build")
    if os.path.exists(build_dir):
        try:
            shutil.rmtree(build_dir)
            print(f"[3/4] 已清理旧的构建缓存: {build_dir}")
        except Exception as e:
            print(f"[3/4] 清理构建缓存提示: {e}")
    else:
        print("[3/4] 构建缓存已为就绪状态。")


def run_pyinstaller():
    """执行 PyInstaller 打包流程"""
    spec_path = os.path.join(BASE_DIR, "TestApp.spec")
    print(f"[4/4] 正在启动 PyInstaller 打包构建...")
    print(f"      命令: {sys.executable} -m PyInstaller {spec_path} --noconfirm")
    print("=" * 70)
    
    cmd = [sys.executable, "-m", "PyInstaller", spec_path, "--noconfirm"]
    start_time = time.time()
    
    process = subprocess.Popen(
        cmd,
        cwd=BASE_DIR,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace"
    )

    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        if line:
            # 过滤打印关键进度
            clean_line = line.rstrip()
            if any(k in clean_line for k in ("INFO:", "WARNING:", "Building", "checking", "Appended", "COLLECT")):
                print(f"  {clean_line}")
            elif "ERROR:" in clean_line:
                print(f"  \033[91m{clean_line}\033[0m")

    ret_code = process.poll()
    elapsed = time.time() - start_time
    print("=" * 70)

    if ret_code == 0:
        version = get_current_version()
        dist_dir = os.path.join(BASE_DIR, "dist", f"TestApp_V{version}")
        exe_file = os.path.join(dist_dir, f"TestApp_V{version}.exe")
        
        print("\n" + "★" * 70)
        print(f"  🎉 打包大获成功！(总耗时: {elapsed:.1f} 秒)")
        print(f"  📦 软件版本: V{version}")
        print(f"  📁 输出目录: {dist_dir}")
        if os.path.exists(exe_file):
            size_mb = os.path.getsize(exe_file) / (1024 * 1024)
            print(f"  🚀 主程序文件: {exe_file} ({size_mb:.2f} MB)")
        print("★" * 70 + "\n")
        return True
    else:
        print(f"\n❌ 打包失败，退出码: {ret_code}，请检查上方日志。")
        return False


def main():
    print("=" * 70)
    print("   自动化测试平台 - 智能打包构建工具 (Auto Build System)")
    print("=" * 70)

    version = get_current_version()
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        version = sys.argv[1].strip()

    print(f"-> 目标打包版本号: {version}")

    # 1. 生成版本信息文件
    version_info_path = os.path.join(BASE_DIR, "version_info.txt")
    generate_version_info_file(version, version_info_path)

    # 2. 同步 spec 配置
    sync_spec_file(version)

    # 3. 清理旧缓存
    clean_build_cache()

    # 4. 询问或直接打包
    print("\n准备就绪，即将开始执行 PyInstaller 打包...")
    run_pyinstaller()


if __name__ == "__main__":
    main()
