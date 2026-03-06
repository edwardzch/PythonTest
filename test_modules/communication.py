# test_modules/communication.py
"""
此模块提供底层的Modbus通信能力，用于与其他硬件设备（如DAQ板、伺服驱动器等）进行交互。
它通过一个函数工厂，为在 `config.json` 中定义的每个设备动态生成了独立的读写函数。
"""

import logging

# --- 内部辅助函数 ---

def _get_comm_for_station(hardware_manager, test_engine_instance):
    """一个内部辅助函数，在每次需要时动态获取Modbus通信句柄。"""
    comm_port = test_engine_instance.station_config.get('comm_port')
    if not comm_port:
        raise ValueError("当前工位未配置通信串口 (comm_port)。")
    return hardware_manager.get_modbus_communicator(comm_port)

def _to_int(value_str):
    """将值（特别是十六进制字符串）转换为整数。"""
    if isinstance(value_str, int): return value_str
    if value_str is None or str(value_str).strip() == '' or str(value_str).lower() == 'null': return None
    value_str = str(value_str).strip().lower()
    if value_str.startswith('0x'):
        return int(value_str, 16)
    else:
        return int(value_str)

def _read_long(comm, slave_address, register, signed=False, byteorder=0):
    """内部函数：读取32位整数。"""
    try:
        register_int = _to_int(register)
        byteorder_int = int(byteorder)
        result = comm.read_long(slave_address, register_int, signed=signed, byteorder=byteorder_int)
        if isinstance(result, int):
            hex_str = f"0x{result & 0xFFFFFFFF:08X}" if result >= 0 else f"-0x{(-result) & 0xFFFFFFFF:08X}"
            msg = f"从地址 {slave_address}:0x{register_int:04X} 读取到32位值: {result}({hex_str})"
        else:
            msg = f"从地址 {slave_address}:0x{register_int:04X} 读取到32位值: {result}"
        return result, msg
    except Exception as e:
        return False, f"读取地址 {slave_address}:{register} 失败: {e}"

def _read_registers(comm, slave_address, register, count=1, signed=False):
    """内部函数:读取保持寄存器。"""
    try:
        register_int = _to_int(register)
        count_int = _to_int(count) or 1
        values = comm.read_holding_registers(slave_address, register_int, count_int)
        
        # 处理有符号转换 (如果需要)
        # read_holding_registers 返回的是无符号列表
        if signed:
            if isinstance(values, list):
                # 转换列表中的每个元素
                values = [v if v < 32768 else v - 65536 for v in values]
            elif isinstance(values, int):
                # 如果返回单个值（虽然API通常返回列表，但作为防守性编程）
                values = values if values < 32768 else values - 65536

        result = values[0] if count_int == 1 and isinstance(values, list) else values
        # 格式化返回消息：包含从站地址和十六进制显示
        if isinstance(result, int):
            hex_str = f"0x{result & 0xFFFF:04X}" if result >= 0 else f"-0x{(-result) & 0xFFFF:04X}"
            msg = f"从地址 {slave_address}: 0x{register_int:04X} 读取到值 {result}({hex_str})"
        else:
            msg = f"从地址 {slave_address}: 0x{register_int:04X} 读取到值 {result}"
        return result, msg
    except Exception as e:
        return False, f"从地址 {slave_address}: 0x{_to_int(register) or 0:04X} 读取失败: {e}"

def _read_input_registers(comm, slave_address, register, count=1, signed=False):
    """内部函数：读取输入寄存器 (04H)。"""
    try:
        register_int = _to_int(register)
        count_int = _to_int(count) or 1
        values = comm.read_input_registers(slave_address, register_int, count_int)
        
        # 处理有符号转换
        if signed:
            if isinstance(values, list):
                values = [v if v < 32768 else v - 65536 for v in values]
            elif isinstance(values, int):
                values = values if values < 32768 else values - 65536

        result = values[0] if count_int == 1 and isinstance(values, list) else values
        # 格式化返回消息：包含从站地址和十六进制显示
        if isinstance(result, int):
            hex_str = f"0x{result & 0xFFFF:04X}" if result >= 0 else f"-0x{(-result) & 0xFFFF:04X}"
            msg = f"从地址 {slave_address}: 0x{register_int:04X} 读取到值 {result}({hex_str})"
        else:
            msg = f"从地址 {slave_address}: 0x{register_int:04X} 读取到值 {result}"
        return result, msg
    except Exception as e:
        return False, f"从地址 {slave_address}: 0x{_to_int(register) or 0:04X} 读取失败: {e}"

def _write_register(comm, slave_address, register, value):
    """内部函数：写入单个寄存器。"""
    try:
        register_int = _to_int(register)
        value_int = _to_int(value)
        comm.write_single_register(slave_address, register_int, value_int)
        return True, f"向地址 {slave_address}:{register} 写入值 {value} 成功。"
    except Exception as e:
        return False, f"写入地址 {slave_address}:{register} 失败: {e}"

def _write_registers_multiple(comm, slave_address, register, values):
    """内部函数：写入多个寄存器。"""
    try:
        register_int = _to_int(register)
        if not isinstance(values, list): return False, "参数错误: values 期望是一个列表。"
        values_int = [_to_int(v) for v in values]
        if any(v is None for v in values_int): return False, "参数错误: values 列表包含无效或空的数字字符串。"
        comm.write_multiple_registers(slave_address, register_int, values_int)
        return True, f"向地址 {slave_address}:{register} 写入 {len(values_int)} 个值成功。"
    except Exception as e:
        return False, f"写入地址 {slave_address}:{register} 失败: {e}"

# --- 函数工厂 ---

def _create_device_functions(device_name, read_only=False, is_input_register=False):
    """为指定设备动态创建一套完整的读写函数及它们的文档。"""
    
    def specific_read(register, count=1, signed=False, hardware_manager=None, test_engine_instance=None, modbus_slaves=None, **kwargs):
        try:
            # 兼容旧版本调用，确保 signed 是 bool
            if isinstance(signed, str):
                signed = signed.lower() == 'true'

            # 【调试】打印 modbus_slaves 内容
            logging.debug(f"[{device_name}] modbus_slaves received: {modbus_slaves}")
            
            comm = _get_comm_for_station(hardware_manager, test_engine_instance)
            slave_address = modbus_slaves.get(device_name) if modbus_slaves else None
            if slave_address is None:
                logging.error(f"[{device_name}] 从站地址查找失败: modbus_slaves={modbus_slaves}, key={device_name}")
                return False, f"配置错误: 未找到设备'{device_name}'的从站地址"
            if is_input_register:
                return _read_input_registers(comm, slave_address, register, count, signed)
            else:
                return _read_registers(comm, slave_address, register, count, signed)
        except Exception as e:
            return False, f"执行 {device_name} 读取失败: {e}"

    def specific_read_long(register, signed=False, byteorder=0, hardware_manager=None, test_engine_instance=None, modbus_slaves=None, **kwargs):
        try:
            if isinstance(signed, str): signed = signed.lower() == 'true'
            
            comm = _get_comm_for_station(hardware_manager, test_engine_instance)
            slave_address = modbus_slaves.get(device_name)
            if slave_address is None: return False, f"配置错误: 未找到设备'{device_name}'的从站地址"
            return _read_long(comm, slave_address, register, signed, byteorder)
        except Exception as e:
            return False, f"执行 {device_name} 32位读取失败: {e}"

    if read_only:
        specific_read.__doc__ = f"""读取设备 '{device_name}' 的一个或多个输入寄存器 (04H)。

:param register: (int/str) 起始寄存器地址。支持十六进制字符串 (如 '0x10')。
:param count: (int) 要读取的寄存器数量，默认为1。
:param signed: (bool) 是否作为有符号数读取，默认为 False (无符号)。
:return: (int/list, str) 如果读取单个值，返回该值；如果读取多个值，返回一个列表。

用法示例:
- 模块: communication
- 函数: read_{device_name.replace('_board','').replace('_driver','')}_register
- 参数: {{"register": "0x02", "count": 1, "signed": "true"}}
- 变量: daq_value
"""
        return specific_read

    def specific_write_single(register, value, hardware_manager=None, test_engine_instance=None, modbus_slaves=None, **kwargs):
        try:
            # 【调试】打印 modbus_slaves 内容
            logging.debug(f"[{device_name}] write_single modbus_slaves: {modbus_slaves}")
            
            comm = _get_comm_for_station(hardware_manager, test_engine_instance)
            slave_address = modbus_slaves.get(device_name) if modbus_slaves else None
            if slave_address is None:
                logging.error(f"[{device_name}] 写入时从站地址查找失败: modbus_slaves={modbus_slaves}, key={device_name}")
                return False, f"配置错误: 未找到设备'{device_name}'的从站地址"
            return _write_register(comm, slave_address, register, value)
        except Exception as e:
            return False, f"执行 {device_name} 写入失败: {e}"

    def specific_write_multiple(register, values, hardware_manager=None, test_engine_instance=None, modbus_slaves=None, **kwargs):
        try:
            comm = _get_comm_for_station(hardware_manager, test_engine_instance)
            slave_address = modbus_slaves.get(device_name) if modbus_slaves else None
            if slave_address is None:
                logging.error(f"[{device_name}] 写入多个时从站地址查找失败: modbus_slaves={modbus_slaves}, key={device_name}")
                return False, f"配置错误: 未找到设备'{device_name}'的从站地址"
            return _write_registers_multiple(comm, slave_address, register, values)
        except Exception as e:
            return False, f"执行 {device_name} 写入失败: {e}"

    # --- 动态生成文档字符串 ---
    specific_read.__doc__ = f"""读取设备 '{device_name}' 的一个或多个保持寄存器。

:param register: (int/str) 起始寄存器地址。支持十六进制字符串 (如 '0x10')。
:param count: (int) 要读取的寄存器数量，默认为1。
:param signed: (bool) 是否作为有符号数读取，默认为 False。
:return: (int/list, str) 如果读取单个值，返回该值；如果读取多个值，返回一个列表。

用法示例:
- 模块: communication
- 函数: read_{device_name.replace('_board','').replace('_driver','')}_register
- 参数: {{"register": "0x02", "count": 1}}
- 变量: daq_value
"""
    specific_write_single.__doc__ = f"""向设备 '{device_name}' 写入一个单字到保持寄存器。

:param register: (int/str) 寄存器地址。支持十六进制字符串。
:param value: (int/str) 要写入的值。支持十六进制字符串。
:return: (bool, str) 执行结果。

用法示例:
- 模块: communication
- 函数: write_{device_name.replace('_board','').replace('_driver','')}_register
- 参数: {{"register": "0x00", "value": "0x10"}}
"""
    specific_write_multiple.__doc__ = f"""向设备 '{device_name}' 连续写入多个值到保持寄存器。

:param register: (int/str) 起始寄存器地址。支持十六进制字符串。
:param values: (list) 要写入的值的列表。列表中的每个值都可以是十六进制字符串。
:return: (bool, str) 执行结果。

用法示例:
- 模块: communication
- 函数: write_{device_name.replace('_board','').replace('_driver','')}_registers_multiple
- 参数: {{"register": "0x02", "values": ["0x03", "0x04"]}}
"""

    specific_read_long.__doc__ = f"""读取设备 '{device_name}' 的一个32位整数 (跨越2个寄存器)。

:param register: (int/str) 起始寄存器地址。
:param signed: (bool) 是否有符号，默认 False。
:param byteorder: (int) 字节序。
    0：高字在前，大端序（标准）
    1：低字在前，大端序
    2：高字在前，小端序
    3：低字在前，小端序
:return: (int, str) 读取到的32位整数值。

用法示例:
- 模块: communication
- 函数: read_{device_name.replace('_board','').replace('_driver','')}_long
- 参数: {{"register": "0x0407", "signed": "true", "byteorder": 1}}
"""

    return specific_read, specific_write_single, specific_write_multiple, specific_read_long

# --- 动态创建并导出所有设备函数 ---

import json
import os

def _load_modbus_devices():
    """
    从 config.json 中读取 Modbus 从站设备配置。
    优先从 serial_config.modbus_slaves（新格式）读取，
    如果不存在则回退到 stations.station_X.modbus_slaves（旧格式）以保持兼容。
    """
    devices = set()
    try:
        # 尝试获取 config.json 路径
        # 【调试增强】使用 get_app_base_path 确保在打包后也能正确找到配置文件
        try:
            from utils.app_utils import get_app_base_path
            base_dir = get_app_base_path()
        except ImportError:
            # 备选方案：从 __file__ 推断
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        config_path = os.path.join(base_dir, 'config.json')
        print(f"[communication] 尝试加载配置文件: {config_path}")
        print(f"[communication] 配置文件存在: {os.path.exists(config_path)}")
        
        if os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                
                # 新格式：从 serial_config.modbus_slaves 读取（共享配置）
                serial_config = config.get('serial_config', {})
                shared_slaves = serial_config.get('modbus_slaves', {})
                if shared_slaves:
                    devices.update(shared_slaves.keys())
                    print(f"[communication] 从 serial_config.modbus_slaves 加载设备: {list(shared_slaves.keys())}")
                
                # 兼容旧格式：从 stations.station_X.modbus_slaves 读取
                if not devices:
                    stations = config.get('stations', {})
                    for s_id, s_data in stations.items():
                        slaves = s_data.get('modbus_slaves', {})
                        if slaves:
                            devices.update(slaves.keys())
                            print(f"[communication] 从 stations.{s_id}.modbus_slaves 加载设备: {list(slaves.keys())}")
                        
    except Exception as e:
        logging.warning(f"无法从配置文件加载 Modbus 设备列表: {e}")
        import traceback
        traceback.print_exc()
    
    # 如果没找到任何设备，提供默认集合
    if not devices:
        devices = {"daq_board", "servo_driver", "relay_board", "analog_board"}
        print(f"[communication] 未找到设备配置，使用默认设备集: {devices}")
    
    return devices

_devices = _load_modbus_devices()
print(f"动态加载 Modbus 设备函数: {_devices}")

for device_name in _devices:
    # 生成标准读写函数
    r_func, w_func, wm_func, r_long_func = _create_device_functions(device_name)
    
    # 动态注入到当前模块的全局命名空间
    # 命名规则: read_{name}_register
    # 如果 name 包含 _board 或 _driver 后缀，可以考虑去除以简化函数名，或者保留
    # 用户之前的代码是: read_daq_register (对应 daq_board)
    # 所以逻辑是: replace('_board', '').replace('_driver', '')
    
    short_name = device_name.replace('_board', '').replace('_driver', '')
    
    globals()[f"read_{short_name}_register"] = r_func
    globals()[f"read_{short_name}_long"] = r_long_func
    globals()[f"write_{short_name}_register"] = w_func
    globals()[f"write_{short_name}_registers_multiple"] = wm_func
    
    # 为所有设备生成 input register 读取函数（04H 功能码）
    r_in_func = _create_device_functions(device_name, read_only=True, is_input_register=True)
    globals()[f"read_{short_name}_input_register"] = r_in_func

# 清理临时变量
if 'r_in_func' in locals(): del r_in_func
del _devices, device_name, r_func, w_func, wm_func, r_long_func, short_name


# --- 独立的串口控制函数 ---

def open_serial_port(baudrate, bytesize, parity, stopbits, timeout, hardware_manager=None, test_engine_instance=None, **kwargs):
    """
    【独立模式专用】打开并配置当前工位的通信串口。
    此函数用于在测试序列的Setup区块中，根据给定参数初始化物理串口。
    注意：在共享串口模式下，此步骤会自动跳过。

    :param baudrate: (int) 波特率, 例如 9600, 57600, 115200。
    :param bytesize: (int) 数据位, 通常是 8。
    :param parity: (str) 校验位, 'N' (无), 'E' (偶), 'O' (奇)。
    :param stopbits: (int) 停止位, 通常是 1 或 2。
    :param timeout: (float) 读取超时时间（秒）。
    :return: (bool, str) 执行结果。
    """
    try:
        station_id = test_engine_instance.station_id
        config = test_engine_instance.global_config
        serial_mode_cfg = config.get('serial_port_mode', {})
        if serial_mode_cfg.get('use_shared_port', False):
            return True, "共享串口模式，自动跳过手动打开。"
        comm_port = config['stations'][station_id]['comm_port']
        if not comm_port: return False, f"工位 {station_id} 未配置串口 (comm_port)。"
        is_simulated = serial_mode_cfg.get('shared_port_config', {}).get('simulation_mode', False)
        serial_params = {'baudrate': int(baudrate), 'bytesize': int(bytesize), 'parity': parity, 'stopbits': int(stopbits), 'timeout': float(timeout)}
        success = hardware_manager.initialize_and_connect_serial(comm_port, serial_params, is_simulated)
        return (True, f"串口 {comm_port} 成功打开并连接。") if success else (False, f"打开串口 {comm_port} 失败。")
    except KeyError as e:
        return False, f"配置错误: 缺少键 {e}。"
    except Exception as e:
        return False, f"发生意外错误: {str(e)}"

def close_serial_port(hardware_manager=None, test_engine_instance=None, **kwargs):
    """
    【独立模式专用】关闭当前工位之前打开的通信串口。
    建议在测试序列的Cleanup区块中调用，以确保资源被正确释放。
    注意：在共享串口模式下，此步骤会自动跳过。

    :return: (bool, str) 执行结果。
    """
    try:
        station_id = test_engine_instance.station_id
        config = test_engine_instance.global_config
        serial_mode_cfg = config.get('serial_port_mode', {})
        if serial_mode_cfg.get('use_shared_port', False):
            return True, "共享串口模式，自动跳过手动关闭。"
        comm_port = config['stations'][station_id].get('comm_port')
        if not comm_port: return True, "未配置串口，跳过关闭。"
        success = hardware_manager.disconnect_device(comm_port, cleanup_instance=False)
        return (True, f"串口 {comm_port} 已成功关闭。") if success else (True, f"关闭串口 {comm_port} 时遇到问题，但测试继续。")
    except Exception as e:
        return True, f"关闭串口时发生意外错误，但测试继续: {str(e)}"
