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
        # capture_output=True 捕获 stdout 和 stderr
        # text=True 将输出作为字符串处理
        # check=True 如果返回码非 0 则抛出 CalledProcessError (这里我们手动处理返回码，所以设为 False 或默认)
        result = subprocess.run(
            [script_path],
            capture_output=True,
            text=True,
            timeout=float(timeout),
            shell=True, # .bat 需要 shell=True 或者直接调用 cmd /c
            cwd=os.path.dirname(script_path) # 设置工作目录为脚本所在目录，确保脚本内的相对路径正确
        )

        output_msg = f"Stdout:\n{result.stdout}\nStderr:\n{result.stderr}"

        if result.returncode == 0:
            return True, f"脚本执行成功。\n{output_msg}"
        else:
            return False, f"脚本执行失败 (返回码 {result.returncode})。\n{output_msg}"

    except subprocess.TimeoutExpired:
        return False, f"脚本执行超时 ({timeout}s)。"
    except Exception as e:
        logging.error(f"执行 .bat 脚本出错: {e}", exc_info=True)
        return False, f"执行脚本时发生异常: {e}"
