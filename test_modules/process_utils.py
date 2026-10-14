import subprocess
import os
import logging

def run_bat_script(script_path: str, timeout: int = 60):
    """
    执行指定的 .bat 脚本。

    :param script_path: .bat 文件的绝对路径。
    :param timeout: 执行超时时间（秒），默认 60 秒。
    :return: (bool, str) 执行结果元组。 (True, "Output...") or (False, "Error...")

    用法示例:
    - 模块: process_utils
    - 函数: run_bat_script
    - 参数: {"script_path": "C:\\Scripts\\test.bat", "timeout": 30}
    """
    if not os.path.exists(script_path):
        return False, f"脚本文件不存在: {script_path}"

    try:
        process = subprocess.Popen(
            [script_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            shell=True,
            cwd=os.path.dirname(script_path)
        )

        try:
            stdout, stderr = process.communicate(timeout=float(timeout))
            output_msg = f"Stdout:\n{stdout}\nStderr:\n{stderr}"

            if process.returncode == 0:
                return True, f"脚本执行成功。\n{output_msg}"
            else:
                return False, f"脚本执行失败 (返回码 {process.returncode})。\n{output_msg}"
                
        except subprocess.TimeoutExpired:
            # 解决Windows下的subprocess超时卡死问题：使用taskkill强制结束进程树，防止未结束的子进程（如烧录工具）卡住管道
            subprocess.run(['taskkill', '/F', '/T', '/PID', str(process.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            process.kill()
            process.stdout.close()
            process.stderr.close()
            return False, f"脚本执行超时 ({timeout}s)。"
    except Exception as e:
        logging.error(f"执行 .bat 脚本出错: {e}", exc_info=True)
        return False, f"执行脚本时发生异常: {e}"
