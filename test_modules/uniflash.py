import os
from test_modules.process_utils import run_bat_script

def run_uniflash_bat(bat_filename, timeout=60, **kwargs):
    """
    根据当前工位配置的 UniFlash 目录，运行指定的 .bat 文件。
    
    :param bat_filename: .bat 文件名 (例如 "dslite-C28xx_CPU1.bat")
    :param timeout: 超时时间 (秒)
    :param kwargs: 包含全局配置和上下文信息，由测试引擎自动传入
    :return: (bool, str) 执行结果
    """
    # 1. 获取当前工位 ID (例如 "station_1")
    station_id = kwargs.get('station_id')
    if not station_id:
        return False, "无法获取当前工位 ID (station_id)"

    # 2. 获取全局配置
    global_config = kwargs.get('global_config', {})
    if not global_config:
        # 尝试从 kwargs 直接获取 (TestEngine 可能会把 global_config 拆散传进来，也可能作为整体)
        # 在 TestEngine._parse_and_execute 中，dependencies 包含了 global_config 的内容
        # 但通常我们建议 TestEngine 显式传递 global_config 对象，或者我们从 dependencies 里找 uniflash_config
        # 让我们看看 TestEngine 的实现...
        # dependencies = {**self.global_config, ...} -> global_config 的键值对被展开了
        # 所以我们可以直接从 kwargs 里获取 'uniflash_config'
        pass

    uniflash_config = kwargs.get('uniflash_config', {})
    
    # 3. 获取当前工位的路径配置
    # 键名对应 drivers/uniflash_driver.py 中的 CONFIG_SCHEMA
    # station_1 -> station_1_path
    path_key = f"{station_id}_path"
    base_path = uniflash_config.get(path_key)

    if not base_path:
        return False, f"未配置工位 {station_id} 的 UniFlash 目录。请在配置编辑器中设置 'UniFlash 配置'。"

    if not os.path.exists(base_path):
        return False, f"配置的 UniFlash 目录不存在: {base_path}"

    # 4. 拼接完整路径
    full_bat_path = os.path.join(base_path, bat_filename)
    
    if not os.path.exists(full_bat_path):
        return False, f"在配置的目录下找不到脚本文件: {full_bat_path}"

    # 5. 调用 process_utils 运行脚本
    # 注意：process_utils.run_bat_script 已经修复，会自动切换 CWD 到脚本所在目录
    return run_bat_script(full_bat_path, timeout)
