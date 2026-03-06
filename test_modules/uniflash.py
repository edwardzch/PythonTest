import os
from test_modules.process_utils import run_bat_script

def run_uniflash_bat(bat_filename, firmware_path=None, timeout=60, **kwargs):
    """
    根据固件文件夹路径和当前工位，自动匹配对应的 station 子文件夹，运行指定的 .bat 文件。
    
    目录结构示例:
        BD3E_V2.5.00/
        ├── station1/      # 工位1 (对应 station_1)
        │   ├── dslite-C28xx_CPU1.bat
        │   ├── dslite-C28xx_CPU2.bat
        │   └── dslite-Cortex_M4_0.bat
        ├── station2/      # 工位2 (对应 station_2)
        ├── station3/      # 工位3 (对应 station_3)
        └── station4/      # 工位4 (对应 station_4)
    
    :param bat_filename: .bat 文件名 (例如 "dslite-C28xx_CPU1.bat")
    :param firmware_path: 固件文件夹的绝对路径 (例如 "D:/firmware/BD3E_V2.5.00")
    :param timeout: 超时时间 (秒)
    :param kwargs: 包含上下文信息，由测试引擎自动传入
    :return: (bool, str) 执行结果
    """
    # 1. 获取当前工位 ID (例如 "station_1")
    station_id = kwargs.get('station_id')
    if not station_id:
        return False, "无法获取当前工位 ID (station_id)"

    # 2. 检查 firmware_path 参数
    if not firmware_path:
        return False, "未指定固件文件夹路径 (firmware_path)。请在测试序列中设置此参数。"
    
    if not os.path.exists(firmware_path):
        return False, f"固件文件夹不存在: {firmware_path}"

    # 3. 根据工位ID映射到station子文件夹
    # station_1 -> station1, station_2 -> station2, ...
    station_num = station_id.replace("station_", "")
    station_folder = f"station{station_num}"
    
    # 4. 构建完整的工位目录路径
    station_path = os.path.join(firmware_path, station_folder)
    
    if not os.path.exists(station_path):
        return False, f"固件文件夹中找不到工位子目录: {station_path}"

    # 5. 拼接完整的 .bat 文件路径
    full_bat_path = os.path.join(station_path, bat_filename)
    
    if not os.path.exists(full_bat_path):
        return False, f"在工位目录下找不到脚本文件: {full_bat_path}"

    # 6. 调用 process_utils 运行脚本
    # 注意：process_utils.run_bat_script 已经修复，会自动切换 CWD 到脚本所在目录
    return run_bat_script(full_bat_path, timeout)
