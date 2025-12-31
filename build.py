# build.py
import os
import shutil
import sys
import time


def run_command(command):
    """运行系统命令，如果失败则退出"""
    print(f"\n[Build] 正在执行: {command} ...")
    ret = os.system(command)
    if ret != 0:
        print(f"[Build] 错误: 命令执行失败 -> {command}")
        sys.exit(1)


def main():
    print("=" * 50)
    print("开始自动化打包流程")
    print("=" * 50)

    # 1. 清理旧的构建文件 (可选，防止缓存问题)
    if os.path.exists('build'):
        print("[Build] 清理 build 文件夹...")
        try:
            shutil.rmtree('build')
        except Exception as e:
            print(f"清理失败 (可能被占用): {e}")

    # 2. 打包主程序 (文件夹模式)
    # 这会生成 dist/TestApp_V1.0 文件夹
    print("\n>>> 阶段 1/3: 打包主程序 (TestApp)...")
    run_command('pyinstaller main.spec')

    # 3. 打包启动器 (单文件模式)
    # 这会生成 dist/Launcher.exe
    print("\n>>> 阶段 2/3: 打包启动器 (Launcher)...")
    run_command('pyinstaller launcher.spec')

    # 4. 移动文件
    print("\n>>> 阶段 3/3: 整合文件...")

    # 定义路径
    dist_dir = 'dist'
    main_app_folder = os.path.join(dist_dir, 'TestApp_V1.0')  # main.spec 里定义的文件夹名
    launcher_exe_src = os.path.join(dist_dir, 'Launcher.exe')
    launcher_exe_dst = os.path.join(main_app_folder, 'Launcher.exe')

    # 检查文件是否存在
    if not os.path.exists(main_app_folder):
        print(f"[Error] 主程序文件夹未找到: {main_app_folder}")
        sys.exit(1)

    if not os.path.exists(launcher_exe_src):
        print(f"[Error] 启动器 EXE 未找到: {launcher_exe_src}")
        sys.exit(1)

    # 移动 Launcher.exe 到 TestApp_V1.0 文件夹内
    try:
        # 如果目标文件夹里已经有 Launcher.exe，先删除
        if os.path.exists(launcher_exe_dst):
            os.remove(launcher_exe_dst)

        shutil.move(launcher_exe_src, launcher_exe_dst)
        print(f"[Success] Launcher.exe 已移动到: {main_app_folder}")
    except Exception as e:
        print(f"[Error] 移动文件失败: {e}")
        sys.exit(1)

    # 5. 重命名主程序 (确保 launcher.py 代码里叫 TestApp.exe)
    # main.spec 默认生成的是 TestApp_V1.0.exe (根据 name 字段)
    # 我们需要确保它和 launcher.py 代码里的 target_exe="TestApp.exe" 一致

    # 假设 main.spec 里的 name='TestApp_V1.0'
    original_main_exe = os.path.join(main_app_folder, 'TestApp_V1.0.exe')
    target_main_exe = os.path.join(main_app_folder, 'TestApp.exe')

    if os.path.exists(original_main_exe):
        if os.path.exists(target_main_exe):
            os.remove(target_main_exe)
        os.rename(original_main_exe, target_main_exe)
        print(f"[Success] 主程序已重命名为: TestApp.exe")
    else:
        # 如果找不到，可能是 spec 里的 name 已经是 TestApp.exe 了，或者路径不对
        # 这一步做个宽容处理
        print(f"[Info] 未找到 {original_main_exe}，跳过重命名 (请确认 spec name 配置)")

    print("\n" + "=" * 50)
    print(f"打包完成！")
    print(f"最终产物位置: {os.path.abspath(main_app_folder)}")
    print("请进入该文件夹，运行 Launcher.exe 测试。")
    print("=" * 50)


if __name__ == "__main__":
    main()