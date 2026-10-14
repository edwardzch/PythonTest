# test_modules/firmware.py
"""
此模块负责通过 J-Link 工具执行固件烧录操作。
"""

import subprocess
import os
import tempfile
import time
import logging

# 尝试导入 filelock，如果失败则使用一个虚拟的锁对象，以确保代码在缺少该库时也能运行。
# 在多工位场景下，filelock 是必需的。
try:
    from filelock import FileLock, Timeout
except ImportError:
    logging.warning("`filelock` 库未安装。在多工位并行测试中，J-Link 烧录可能因冲突而失败。")
    logging.warning("请运行 `pip install filelock` 来安装。")
    # 定义一个虚拟的锁对象，使其在没有 filelock 库时也能正常工作（但没有锁功能）。
    class DummyLock:
        def __enter__(self):
            pass
        def __exit__(self, exc_type, exc_val, exc_tb):
            pass
    class Timeout(Exception):
        pass
    FileLock = lambda path: DummyLock()


def burn_firmware(logger, jlink=None, jlink_sn=None, mcu_device=None, firmware_hex_path=None, timeout=20, **kwargs):
    """
    使用带互锁机制的 J-Link 烧录固件，确保多工位操作安全。

    此函数是 `_burn_firmware_internal` 的封装器，增加了文件锁，以防止多个进程同时访问 J-Link。
    等待锁的超时时间固定为 15 秒。烧录过程的超时由 `timeout` 参数指定。
    烧录完成后，会延时1秒再释放锁，为其他工位提供缓冲。

    :param logger: 日志记录器。
    :param jlink: J-Link 配置字典。
    :param jlink_sn: J-Link 序列号。
    :param mcu_device: 目标 MCU 型号。
    :param firmware_hex_path: 固件 .hex 文件路径。
    :param timeout: (int/float) 烧录过程的超时时间（秒）。
    :param kwargs: 其他参数。
    :return: (bool, str) 执行结果元组。
    """
    lock_timeout = 20  # 等待锁的超时时间固定为 20 秒
    try:
        burn_timeout = float(timeout)
    except (ValueError, TypeError):
        logger.warning(f"无效的烧录超时值 '{timeout}'，将使用默认值 20 秒。")
        burn_timeout = 20

    lock_path = os.path.join(tempfile.gettempdir(), "jlink_burn.lock")
    lock = FileLock(lock_path)

    logger.info(f"工位 (SN: {jlink_sn}) 请求烧录，等待 J-Link 锁 (超时: {lock_timeout}s)...")

    try:
        lock.acquire(timeout=lock_timeout)
        logger.info(f"工位 (SN: {jlink_sn}) 已获取 J-Link 锁。")

        return _burn_firmware_internal(
            logger=logger,
            jlink=jlink,
            jlink_sn=jlink_sn,
            mcu_device=mcu_device,
            firmware_hex_path=firmware_hex_path,
            timeout=burn_timeout,
            **kwargs
        )

    except Timeout:
        msg = f"工位 (SN: {jlink_sn}) 等待 J-Link 锁超时 (超过 {lock_timeout} 秒)。"
        logger.error(msg)
        return False, msg
    except Exception as e:
        msg = f"执行烧录时发生意外错误: {e}"
        logger.error(msg)
        return False, msg
    finally:
        if lock.is_locked:
            lock.release()
            logger.info(f"工位 (SN: {jlink_sn}) 已释放 J-Link 锁，延时 1 秒。")
            # time.sleep(1) #正常测试的时候是不可能4个工位同事进行的，所以这个延时就不加了，除非后续设备改制


def _burn_firmware_internal(logger, jlink=None, jlink_sn=None, mcu_device=None, firmware_hex_path=None, timeout=20, **kwargs):
    """
    使用带互锁机制的 J-Link 烧录固件，确保多工位操作安全。

    此函数是 `_burn_firmware_internal` 的封装器，增加了文件锁，以防止多个进程同时访问 J-Link。
    等待锁的超时时间固定为 15 秒。烧录过程的超时由 `timeout` 参数指定。
    烧录完成后，会延时1秒再释放锁，为其他工位提供缓冲。

    :param logger: 日志记录器。
    :param jlink: J-Link 配置字典。
    :param jlink_sn: J-Link 序列号。
    :param mcu_device: 目标 MCU 型号。
    :param firmware_hex_path: 固件 .hex 文件路径。
    :param timeout: (int/float) 烧录过程的超时时间（秒）。
    :param kwargs: 其他参数。
    :return: (bool, str) 执行结果元组。
    """
    # 获取 jlink_config（新结构）
    jlink_config = kwargs.get('jlink_config', {})
    
    # 优先从 jlink_config.jlink_path 获取（新结构），兼容旧的 jlink.jlink_exe_path
    jlink_exe_path = jlink_config.get('jlink_path') or (jlink.get('jlink_exe_path') if jlink else None)
    
    # 如果 jlink_sn 未提供，从 jlink_config.stations 中根据工位 ID 获取
    if not jlink_sn:
        station_id = kwargs.get('station_id', 'station_1')
        stations = jlink_config.get('stations', {})
        # 处理可能的嵌套结构
        if 'stations' in stations and isinstance(stations.get('stations'), dict):
            stations = stations.get('stations', {})
        station_config = stations.get(station_id, {})
        jlink_sn = station_config.get('jlink_sn', '')
    
    simulation_mode = jlink_config.get('simulation_mode', False)

    if simulation_mode:
        logger.info("[MOCK] J-Link 烧录模式为模拟状态。")
        time.sleep(1)
        return True, "J-Link 模拟烧录成功。"

    logger.info(f"开始真实 J-Link 烧录 (SN: {jlink_sn})...")

    for name, value in [('jlink_exe_path', jlink_exe_path), ('jlink_sn', jlink_sn), ('mcu_device', mcu_device),
                        ('firmware_hex_path', firmware_hex_path)]:
        if not value:
            msg = f"真实烧录失败：缺少必要参数或配置 '{name}'。"
            logger.error(msg)
            return False, msg

    if not os.path.isfile(firmware_hex_path):
        msg = f"固件文件未找到: {firmware_hex_path}"
        logger.error(msg)
        return False, msg

    safe_hex_path = firmware_hex_path.replace('\\', '/')
    # J-Link 脚本命令：
    # r     - 复位 (如果 reset 引脚未连接可能无效)
    # h     - 停止 CPU
    # loadfile - 加载固件
    # w4    - 写入 32 位值到寄存器（SFR 访问）
    #         0xE000ED0C = NVIC AIRCR 寄存器
    #         0x05FA0004 = VECTKEY (0x05FA) + SYSRESETREQ (bit 2)
    # 注意：SFR 复位后 MCU 会自动运行，不需要 g 命令
    # q     - 退出
    script_content = (
        f"r\n"              # 尝试硬件复位
        f"h\n"              # 停止 CPU
        f"loadfile \"{safe_hex_path}\"\n"  # 加载固件
        f"w4 0xE000ED0C 0x05FA0004\n"      # SFR 软复位：写入 AIRCR 寄存器触发系统复位
        f"sleep 100\n"      # 等待复位完成
        f"q\n"              # 退出（MCU 已自动运行）
    )
    script_file_path = None

    try:
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jlink', encoding='utf-8') as script_file:
            script_file.write(script_content)
            script_file_path = script_file.name

        command = [
            jlink_exe_path, "-SelectEmuBySN", str(jlink_sn),
            "-device", mcu_device, "-if", "SWD", "-speed", "4000",
            "-CommanderScript", script_file_path
        ]
        logger.info(f"执行真实烧录命令: {' '.join(command)}")

        # ------------------------------------------------------------------
        # 🔧 ★ EXE 修复补丁：确保 JLink.exe 能找到自己的 DLL（最关键）
        # ------------------------------------------------------------------
        env = os.environ.copy()
        jlink_dir = os.path.dirname(jlink_exe_path)
        env["PATH"] = jlink_dir + os.pathsep + env.get("PATH", "")
        # ------------------------------------------------------------------

        result = subprocess.run(
            command,
            timeout=timeout,
            capture_output=True,
            text=True,
            check=False,
            encoding='utf-8',
            errors='ignore',
            env=env  # ★ 必须指定，否则 EXE 环境会导致 USB 无法连接
        )

        full_output = result.stdout + result.stderr
        output_lower = full_output.lower()
        logger.debug(f"J-Link (SN: {jlink_sn}) 完整输出:\n{full_output}")

        error_indicators = [
            "error:", "failed to connect", "cannot connect",
            "could not establish a connection", "no emulators found",
            "unsupported", "failed"
        ]
        if any(error in output_lower for error in error_indicators):
            return False, f"J-Link 烧录失败：在输出中检测到错误。输出: {full_output.strip()}"

        success_indicators = [("flash download:", "o.k."), ("flash download:", "ok")]
        if any(all(ind in output_lower for ind in group) for group in success_indicators):
            if result.returncode == 0:
                return True, f"烧录成功 (J-Link SN: {jlink_sn}).\n\n完整输出:\n{full_output.strip()}"
            else:
                return False, f"J-Link 烧录失败：文本看似成功，但返回非零错误码 {result.returncode}。"

        if result.returncode != 0:
            return False, f"J-Link 烧录失败：进程返回非零错误码 {result.returncode}。"

        return False, f"J-Link 烧录失败：输出不明确。输出: {full_output.strip()}"

    except subprocess.TimeoutExpired:
        return False, f"J-Link 进程超时 (超过{timeout}秒)。"
    except Exception as e:
        return False, f"执行真实烧录时发生意外错误: {e}"
    finally:
        if script_file_path and os.path.exists(script_file_path):
            os.remove(script_file_path)


def burn_firmware_no_reset(logger, mcu_device=None, firmware_hex_path=None, timeout=20, **kwargs):
    """
    使用带互锁机制的 J-Link 烧录固件（只烧录，不重启 MCU）。

    与 burn_firmware 功能相同，但烧录完成后 **不会** 通过 SFR 写入 AIRCR 寄存器触发软复位。
    MCU 烧录完成后保持 Halt 状态，需要手动断电重新上电才会运行新固件。
    适用于探针/测试点连接不可靠的场景，避免 SFR 复位失败导致异常。

    jlink_exe_path 和 jlink_sn 从 kwargs['jlink_config'] 中自动获取。

    :param logger: 日志记录器。
    :param mcu_device: 目标 MCU 型号。
    :param firmware_hex_path: 固件 .hex 文件路径。
    :param timeout: (int/float) 烧录过程的超时时间（秒）。
    :param kwargs: 其他参数（需包含 jlink_config）。
    :return: (bool, str) 执行结果元组。
    """
    lock_timeout = 20
    try:
        burn_timeout = float(timeout)
    except (ValueError, TypeError):
        logger.warning(f"无效的烧录超时值 '{timeout}'，将使用默认值 20 秒。")
        burn_timeout = 20

    # 从 jlink_config 获取 jlink_sn 用于日志
    jlink_config = kwargs.get('jlink_config', {})
    station_id = kwargs.get('station_id', 'station_1')
    stations = jlink_config.get('stations', {})
    if 'stations' in stations and isinstance(stations.get('stations'), dict):
        stations = stations.get('stations', {})
    station_config = stations.get(station_id, {})
    jlink_sn = station_config.get('jlink_sn', '')

    lock_path = os.path.join(tempfile.gettempdir(), "jlink_burn.lock")
    lock = FileLock(lock_path)

    logger.info(f"工位 (SN: {jlink_sn}) 请求烧录(不重启)，等待 J-Link 锁 (超时: {lock_timeout}s)...")

    try:
        lock.acquire(timeout=lock_timeout)
        logger.info(f"工位 (SN: {jlink_sn}) 已获取 J-Link 锁。")

        return _burn_firmware_no_reset_internal(
            logger=logger,
            mcu_device=mcu_device,
            firmware_hex_path=firmware_hex_path,
            timeout=burn_timeout,
            **kwargs
        )

    except Timeout:
        msg = f"工位 (SN: {jlink_sn}) 等待 J-Link 锁超时 (超过 {lock_timeout} 秒)。"
        logger.error(msg)
        return False, msg
    except Exception as e:
        msg = f"执行烧录时发生意外错误: {e}"
        logger.error(msg)
        return False, msg
    finally:
        if lock.is_locked:
            lock.release()
            logger.info(f"工位 (SN: {jlink_sn}) 已释放 J-Link 锁。")


def _burn_firmware_no_reset_internal(logger, mcu_device=None, firmware_hex_path=None, timeout=20, **kwargs):
    """
    执行 J-Link 固件烧录（只烧录，不重启 MCU）。

    与 _burn_firmware_internal 的区别：
    - 不执行 SFR 软复位（不写入 AIRCR 寄存器）
    - 烧录完成后 MCU 保持 Halt 状态
    - 需要手动断电重新上电才会运行新固件

    jlink_exe_path 和 jlink_sn 从 kwargs['jlink_config'] 中自动获取。

    :param logger: 日志记录器。
    :param mcu_device: 目标 MCU 型号。
    :param firmware_hex_path: 固件 .hex 文件路径。
    :param timeout: (int/float) 烧录过程的超时时间（秒）。
    :param kwargs: 其他参数（需包含 jlink_config）。
    :return: (bool, str) 执行结果元组。
    """
    # 获取 jlink_config（新结构）
    jlink_config = kwargs.get('jlink_config', {})

    # 从 jlink_config.jlink_path 获取
    jlink_exe_path = jlink_config.get('jlink_path')

    # 从 jlink_config.stations 中根据工位 ID 获取 jlink_sn
    station_id = kwargs.get('station_id', 'station_1')
    stations = jlink_config.get('stations', {})
    if 'stations' in stations and isinstance(stations.get('stations'), dict):
        stations = stations.get('stations', {})
    station_config = stations.get(station_id, {})
    jlink_sn = station_config.get('jlink_sn', '')

    simulation_mode = jlink_config.get('simulation_mode', False)

    if simulation_mode:
        logger.info("[MOCK] J-Link 烧录模式为模拟状态（不重启）。")
        time.sleep(1)
        return True, "J-Link 模拟烧录成功（不重启）。"

    logger.info(f"开始真实 J-Link 烧录-不重启 (SN: {jlink_sn})...")

    for name, value in [('jlink_exe_path', jlink_exe_path), ('jlink_sn', jlink_sn), ('mcu_device', mcu_device),
                        ('firmware_hex_path', firmware_hex_path)]:
        if not value:
            msg = f"真实烧录失败：缺少必要参数或配置 '{name}'。"
            logger.error(msg)
            return False, msg

    if not os.path.isfile(firmware_hex_path):
        msg = f"固件文件未找到: {firmware_hex_path}"
        logger.error(msg)
        return False, msg

    safe_hex_path = firmware_hex_path.replace('\\', '/')
    # J-Link 脚本命令（不重启版本）：
    # r     - 复位 (如果 reset 引脚未连接可能无效)
    # h     - 停止 CPU
    # loadfile - 加载固件
    # q     - 退出（MCU 保持 Halt 状态，下次上电自动运行新固件）
    # 注意：此版本不执行 SFR 软复位，避免探针连接不可靠导致的重启问题
    script_content = (
        f"r\n"              # 尝试硬件复位
        f"h\n"              # 停止 CPU
        f"loadfile \"{safe_hex_path}\"\n"  # 加载固件
        f"q\n"              # 退出（MCU 保持 Halt 状态，下次上电自动运行新固件）
    )
    script_file_path = None

    try:
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jlink', encoding='utf-8') as script_file:
            script_file.write(script_content)
            script_file_path = script_file.name

        command = [
            jlink_exe_path, "-SelectEmuBySN", str(jlink_sn),
            "-device", mcu_device, "-if", "SWD", "-speed", "4000",
            "-CommanderScript", script_file_path
        ]
        logger.info(f"执行真实烧录命令(不重启): {' '.join(command)}")

        env = os.environ.copy()
        jlink_dir = os.path.dirname(jlink_exe_path)
        env["PATH"] = jlink_dir + os.pathsep + env.get("PATH", "")

        result = subprocess.run(
            command,
            timeout=timeout,
            capture_output=True,
            text=True,
            check=False,
            encoding='utf-8',
            errors='ignore',
            env=env
        )

        full_output = result.stdout + result.stderr
        output_lower = full_output.lower()
        logger.debug(f"J-Link (SN: {jlink_sn}) 完整输出(不重启):\n{full_output}")

        error_indicators = [
            "error:", "failed to connect", "cannot connect",
            "could not establish a connection", "no emulators found",
            "unsupported", "failed"
        ]
        if any(error in output_lower for error in error_indicators):
            return False, f"J-Link 烧录失败：在输出中检测到错误。输出: {full_output.strip()}"

        success_indicators = [("flash download:", "o.k."), ("flash download:", "ok")]
        if any(all(ind in output_lower for ind in group) for group in success_indicators):
            if result.returncode == 0:
                return True, f"烧录成功-不重启 (J-Link SN: {jlink_sn}).\n\n完整输出:\n{full_output.strip()}"
            else:
                return False, f"J-Link 烧录失败：文本看似成功，但返回非零错误码 {result.returncode}。"

        if result.returncode != 0:
            return False, f"J-Link 烧录失败：进程返回非零错误码 {result.returncode}。"

        return False, f"J-Link 烧录失败：输出不明确。输出: {full_output.strip()}"

    except subprocess.TimeoutExpired:
        return False, f"J-Link 进程超时 (超过{timeout}秒)。"
    except Exception as e:
        return False, f"执行真实烧录时发生意外错误: {e}"
    finally:
        if script_file_path and os.path.exists(script_file_path):
            os.remove(script_file_path)


def burn_firmware_nrst_reset(logger, mcu_device=None, firmware_hex_path=None, timeout=20, **kwargs):
    """
    使用带互锁机制的 J-Link 烧录固件，通过 NRST 引脚硬件复位重启 MCU。

    与 burn_firmware 功能相同，但烧录完成后使用 NRST 硬件复位引脚 + Go 命令来重启 MCU，
    而非通过 SFR 写入 AIRCR 寄存器。这是传统的 J-Link 重启方式。
    注意：需要探针正确连接到 MCU 的 NRST 引脚。

    jlink_exe_path 和 jlink_sn 从 kwargs['jlink_config'] 中自动获取。

    :param logger: 日志记录器。
    :param mcu_device: 目标 MCU 型号。
    :param firmware_hex_path: 固件 .hex 文件路径。
    :param timeout: (int/float) 烧录过程的超时时间（秒）。
    :param kwargs: 其他参数（需包含 jlink_config）。
    :return: (bool, str) 执行结果元组。
    """
    lock_timeout = 20
    try:
        burn_timeout = float(timeout)
    except (ValueError, TypeError):
        logger.warning(f"无效的烧录超时值 '{timeout}'，将使用默认值 20 秒。")
        burn_timeout = 20

    # 从 jlink_config 获取 jlink_sn 用于日志
    jlink_config = kwargs.get('jlink_config', {})
    station_id = kwargs.get('station_id', 'station_1')
    stations = jlink_config.get('stations', {})
    if 'stations' in stations and isinstance(stations.get('stations'), dict):
        stations = stations.get('stations', {})
    station_config = stations.get(station_id, {})
    jlink_sn = station_config.get('jlink_sn', '')

    lock_path = os.path.join(tempfile.gettempdir(), "jlink_burn.lock")
    lock = FileLock(lock_path)

    logger.info(f"工位 (SN: {jlink_sn}) 请求烧录(NRST复位)，等待 J-Link 锁 (超时: {lock_timeout}s)...")

    try:
        lock.acquire(timeout=lock_timeout)
        logger.info(f"工位 (SN: {jlink_sn}) 已获取 J-Link 锁。")

        return _burn_firmware_nrst_reset_internal(
            logger=logger,
            mcu_device=mcu_device,
            firmware_hex_path=firmware_hex_path,
            timeout=burn_timeout,
            **kwargs
        )

    except Timeout:
        msg = f"工位 (SN: {jlink_sn}) 等待 J-Link 锁超时 (超过 {lock_timeout} 秒)。"
        logger.error(msg)
        return False, msg
    except Exception as e:
        msg = f"执行烧录时发生意外错误: {e}"
        logger.error(msg)
        return False, msg
    finally:
        if lock.is_locked:
            lock.release()
            logger.info(f"工位 (SN: {jlink_sn}) 已释放 J-Link 锁。")


def _burn_firmware_nrst_reset_internal(logger, mcu_device=None, firmware_hex_path=None, timeout=20, **kwargs):
    """
    执行 J-Link 固件烧录，通过 NRST 引脚硬件复位重启 MCU。

    与 _burn_firmware_internal 的区别：
    - 不使用 SFR 写入 AIRCR 寄存器
    - 使用 Reset (NRST 硬件复位) + Go (启动运行) 的传统方式
    - 需要探针连接到 NRST 引脚

    jlink_exe_path 和 jlink_sn 从 kwargs['jlink_config'] 中自动获取。

    :param logger: 日志记录器。
    :param mcu_device: 目标 MCU 型号。
    :param firmware_hex_path: 固件 .hex 文件路径。
    :param timeout: (int/float) 烧录过程的超时时间（秒）。
    :param kwargs: 其他参数（需包含 jlink_config）。
    :return: (bool, str) 执行结果元组。
    """
    # 获取 jlink_config（新结构）
    jlink_config = kwargs.get('jlink_config', {})

    # 从 jlink_config.jlink_path 获取
    jlink_exe_path = jlink_config.get('jlink_path')

    # 从 jlink_config.stations 中根据工位 ID 获取 jlink_sn
    station_id = kwargs.get('station_id', 'station_1')
    stations = jlink_config.get('stations', {})
    if 'stations' in stations and isinstance(stations.get('stations'), dict):
        stations = stations.get('stations', {})
    station_config = stations.get(station_id, {})
    jlink_sn = station_config.get('jlink_sn', '')

    simulation_mode = jlink_config.get('simulation_mode', False)

    if simulation_mode:
        logger.info("[MOCK] J-Link 烧录模式为模拟状态（NRST复位）。")
        time.sleep(1)
        return True, "J-Link 模拟烧录成功（NRST复位）。"

    logger.info(f"开始真实 J-Link 烧录-NRST复位 (SN: {jlink_sn})...")

    for name, value in [('jlink_exe_path', jlink_exe_path), ('jlink_sn', jlink_sn), ('mcu_device', mcu_device),
                        ('firmware_hex_path', firmware_hex_path)]:
        if not value:
            msg = f"真实烧录失败：缺少必要参数或配置 '{name}'。"
            logger.error(msg)
            return False, msg

    if not os.path.isfile(firmware_hex_path):
        msg = f"固件文件未找到: {firmware_hex_path}"
        logger.error(msg)
        return False, msg

    safe_hex_path = firmware_hex_path.replace('\\', '/')
    # J-Link 脚本命令（NRST 硬件复位版本）：
    # r     - 复位 (通过 NRST 引脚)
    # h     - 停止 CPU
    # loadfile - 加载固件
    # r     - 烧录后通过 NRST 引脚硬件复位
    # go    - 启动 CPU 运行程序
    # q     - 退出
    script_content = (
        f"r\n"              # 尝试硬件复位
        f"h\n"              # 停止 CPU
        f"loadfile \"{safe_hex_path}\"\n"  # 加载固件
        f"r\n"              # 通过 NRST 引脚硬件复位
        f"go\n"             # 启动 CPU 运行程序
        f"q\n"              # 退出
    )
    script_file_path = None

    try:
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.jlink', encoding='utf-8') as script_file:
            script_file.write(script_content)
            script_file_path = script_file.name

        command = [
            jlink_exe_path, "-SelectEmuBySN", str(jlink_sn),
            "-device", mcu_device, "-if", "SWD", "-speed", "4000",
            "-CommanderScript", script_file_path
        ]
        logger.info(f"执行真实烧录命令(NRST复位): {' '.join(command)}")

        env = os.environ.copy()
        jlink_dir = os.path.dirname(jlink_exe_path)
        env["PATH"] = jlink_dir + os.pathsep + env.get("PATH", "")

        result = subprocess.run(
            command,
            timeout=timeout,
            capture_output=True,
            text=True,
            check=False,
            encoding='utf-8',
            errors='ignore',
            env=env
        )

        full_output = result.stdout + result.stderr
        output_lower = full_output.lower()
        logger.debug(f"J-Link (SN: {jlink_sn}) 完整输出(NRST复位):\n{full_output}")

        error_indicators = [
            "error:", "failed to connect", "cannot connect",
            "could not establish a connection", "no emulators found",
            "unsupported", "failed"
        ]
        if any(error in output_lower for error in error_indicators):
            return False, f"J-Link 烧录失败：在输出中检测到错误。输出: {full_output.strip()}"

        success_indicators = [("flash download:", "o.k."), ("flash download:", "ok")]
        if any(all(ind in output_lower for ind in group) for group in success_indicators):
            if result.returncode == 0:
                return True, f"烧录成功-NRST复位 (J-Link SN: {jlink_sn}).\n\n完整输出:\n{full_output.strip()}"
            else:
                return False, f"J-Link 烧录失败：文本看似成功，但返回非零错误码 {result.returncode}。"

        if result.returncode != 0:
            return False, f"J-Link 烧录失败：进程返回非零错误码 {result.returncode}。"

        return False, f"J-Link 烧录失败：输出不明确。输出: {full_output.strip()}"

    except subprocess.TimeoutExpired:
        return False, f"J-Link 进程超时 (超过{timeout}秒)。"
    except Exception as e:
        return False, f"执行真实烧录时发生意外错误: {e}"
    finally:
        if script_file_path and os.path.exists(script_file_path):
            os.remove(script_file_path)
