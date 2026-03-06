# test_modules/ethernet_module.py

import logging
import time
import socket
import re
from sniffer import sniffer_instance

TERMINATOR = '\r\n'

# 全局的连接管理器，避免每次都重新建立连接
_connection_pool = {}

def _get_or_create_connection(ip, port, timeout, logger, local_ip=""):
    """获取现有连接或创建新连接"""
    # 包含了 local_ip 的连接键，确保绑定不同网卡的连接不会混用
    conn_key = f"{local_ip}=>{ip}:{port}" if local_ip else f"{ip}:{port}"
    sock = _connection_pool.get(conn_key)
    
    # 测试连接是否还活着
    is_alive = False
    if sock is not None:
        try:
            # 使用非阻塞看一眼有没有对方断开的信号
            sock.settimeout(0.0)
            data = sock.recv(16, socket.MSG_PEEK)
            if data == b'':
                is_alive = False # 对方优雅关闭了连接
            else:
                is_alive = True
        except socket.timeout:
             pass # 这是非阻塞正常预期
        except BlockingIOError:
            is_alive = True # 没有数据可读，说明连接还在
        except Exception:
            is_alive = False # 其他异常，认为连接坏了
            
        sock.settimeout(timeout) # 恢复超时设置
        
    if is_alive:
        return sock
        
    # 如果没连上，或者连接断开了，重新连接
    if sock:
        try:
            sock.close()
        except:
            pass
            
    logger.info(f"正在建立新的以太网连接 {conn_key} ...")
    new_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    new_sock.settimeout(timeout)
    
    # 【新增】强制绑定指定的本机网卡发出通信
    if local_ip:
        try:
            # 端口为 0 表示由操作系统随机分配一个本地端口
            new_sock.bind((local_ip, 0))
            logger.info(f"已绑定本机网卡 IP: {local_ip}")
        except Exception as e:
            logger.error(f"无法绑定本机网卡 IP {local_ip}: {e}")
            raise RuntimeError(f"网卡绑定失败: {local_ip}")
            
    try:
        new_sock.connect((ip, int(port)))
    except socket.timeout:
        raise socket.timeout(f"连接超时: {conn_key}")
    except Exception as e:
        raise ConnectionError(f"连接失败: {e}")

    _connection_pool[conn_key] = new_sock
    return new_sock

def init_connection(test_engine_instance=None, **kwargs):
    """
    手动初始化/重新初始化以太网连接。
    在驱动器断电上电后使用，连接参数完全遵从配置编辑器的配置。
    """
    logger = kwargs.get("logger", logging.getLogger())
    try:
        # 获取基础配置
        station_id = test_engine_instance.station_id
        eth_config = test_engine_instance.global_config['stations'][station_id].get('ethernet_config', {})
        
        # 参数覆盖
        final_ip = eth_config.get('ip_address')
        final_port = eth_config.get('port')
        final_timeout = float(eth_config.get('timeout', 5.0))
        local_ip = eth_config.get('local_ip', "")
        
        if not final_ip or not final_port:
            return False, "无法初始化连接: 缺少目标 IP 地址或端口配置"
            
        conn_key = f"{local_ip}=>{final_ip}:{final_port}" if local_ip else f"{final_ip}:{final_port}"
        logger.info(f"正在初始化以太网连接 {conn_key} ...")
        
        # 强制断开旧连接
        old_sock = _connection_pool.pop(conn_key, None)
        if old_sock:
            try:
                old_sock.shutdown(socket.SHUT_RDWR)
                old_sock.close()
            except:
                pass
                
        # 加入重试机制来处理 WinError 10065 (WSAEHOSTUNREACH: 无法连接的主机)
        # 这种情况通常发生在网卡刚刚物理连接上，但操作系统的路由表还没完全准备好的瞬间
        max_retries = 3
        retry_delay = 1.0
        
        for attempt in range(max_retries):
            # 建立新连接并放入池中
            new_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            new_sock.settimeout(final_timeout)
            
            if local_ip:
                try:
                    new_sock.bind((local_ip, 0))
                except Exception as e:
                    return False, f"网卡硬件绑定失败 [IP: {local_ip}]: {e}"
                    
            try:
                new_sock.connect((final_ip, int(final_port)))
                
                # 为了防止虽然 TCP 层面连接上了，但驱动器的应用层（比如已经被别的上位机占用）没有响应
                try:
                    new_sock.sendall(TERMINATOR.encode('utf-8'))
                    new_sock.settimeout(2.0)
                    verify_data = new_sock.recv(1024)
                    if not verify_data:
                        raise ConnectionError("驱动器未返回任何握手数据，通讯超时")
                except socket.timeout:
                    raise ConnectionError("驱动器连接后响应超时，处于异常状态")
                except Exception as e:
                    raise ConnectionError(f"验证通信时失败: {e}")
                    
                new_sock.settimeout(final_timeout)
                _connection_pool[conn_key] = new_sock
                return True, f"成功建立与 {conn_key} 的连接"
                
            except socket.error as e:
                # 检查是否是 10065 错误 (WSAEHOSTUNREACH)
                if hasattr(e, 'winerror') and e.winerror == 10065:
                    if attempt < max_retries - 1:
                        logger.warning(f"OS路由未准备好 (WinError 10065)，第 {attempt+1} 次重试中，等待 {retry_delay}s...")
                        time.sleep(retry_delay)
                        continue
                    else:
                        raise e # 重试用尽，抛出原始错误
                else:
                    raise e # 其他 socket 错误，直接抛出，交给外层抓取
        
    except socket.timeout:
         return False, f"初始化连接超时 ({final_timeout}s)"
    except Exception as e:
        logger.error(f"初始化以太网连接时发生错误: {e}")
        return False, f"初始化连接失败: {e}"

def disconnect(test_engine_instance=None, **kwargs):
    """
    手动断开以太网连接。
    如果需要切换设备或在测试序列结束时彻底释放资源，可以调用此函数。
    
    用法示例:
    - 模块: ethernet_module
    - 函数: disconnect
    """
    logger = kwargs.get("logger", logging.getLogger())
    try:
        station_id = test_engine_instance.station_id
        eth_config = test_engine_instance.global_config['stations'][station_id].get('ethernet_config', {})
        ip_address = eth_config.get('ip_address')
        port = eth_config.get('port')
        
        if not ip_address or not port:
            return True, "没找到配置，跳过断开。"
            
        local_ip = eth_config.get('local_ip', "")
        conn_key = f"{local_ip}=>{ip_address}:{port}" if local_ip else f"{ip_address}:{port}"
        sock = _connection_pool.pop(conn_key, None)
        if sock:
            try:
                sock.shutdown(socket.SHUT_RDWR)
                sock.close()
            except:
                pass
            logger.info(f"以太网连接 {conn_key} 已断开。")
            return True, f"成功断开 {conn_key}"
        else:
            return True, f"未发现已建立的连接 {conn_key}"
            
    except Exception as e:
        logger.error(f"断开以太网连接时发生错误: {e}")
        return False, f"断开失败: {e}"

def request_and_get_string(cmd: str, extract_key: str = "", regex_pattern: str = "", test_engine_instance=None, **kwargs):
    """
    通过以太网 (TCP) 发送一个自定义命令，并等待接收返回。
    支持长连接复用，避免每次耗时重连。
    
    :param cmd: 要发送的字符串命令。
    :param extract_key: (新增简化提取) 自动提取类似 "MPHASE = 1" 或 "v 2994.01" 这种格式的键值对。
                        例如：传入 "MPHASE"，会自动查找并提取其后的数字；
                        传入 "v"，会自动查找 "v " 后面的数字。
    :param regex_pattern: (高级功能) 自定义正则提取。如果 extract_key 无法满足，可手写正则。
    :return: (返回值, 消息)

    用法示例:
    - 获取 MPHASE 变量: {"cmd": "zerost", "extract_key": "MPHASE"}
    - 获取 转速 v: {"cmd": "v", "extract_key": "v"}
    """
    logger = kwargs.get("logger", logging.getLogger())
    
    # 1. 获取以太网配置
    try:
        station_id = test_engine_instance.station_id
        eth_config = test_engine_instance.global_config['stations'][station_id].get('ethernet_config', {})
        ip_address = eth_config.get('ip_address')
        port = eth_config.get('port')
        timeout_s = float(eth_config.get('timeout', 5.0))
        local_ip = eth_config.get('local_ip', "")
        
        if not ip_address or not port:
            return False, "配置错误: 当前工位的 ethernet_config 缺少 ip_address 或 port"
    except Exception as e:
        return False, f"尝试获取以太网配置异常: {e}"

    if not cmd:
        return False, '参数错误: 请在Parameters列中设置 "cmd": "你的命令"'

    sock = None
    try:
        # 2. 复用TCP连接
        sock = _get_or_create_connection(ip_address, port, timeout_s, logger, local_ip)
        
        # 注册抓包上下文（告诉 Sniffer 该“端口”属于哪个工位，这里把 IP:Port 作为虚拟端口名字）
        virtual_port = f"{ip_address}:{port}"
        sn = test_engine_instance.uut_sn if hasattr(test_engine_instance, 'uut_sn') else "Unknown"
        sniffer_instance.register_station_context(virtual_port, station_id, sn)
        
        # 为了防止重连/长连接带来的缓冲区脏数据，发送前清空一下缓冲区
        try:
            sock.settimeout(0.0)
            while True:
                junk = sock.recv(4096)
                if not junk: break
        except:
            pass
        sock.settimeout(timeout_s)

        # 3. 发送数据
        data_to_send = cmd + TERMINATOR
        logger.info(f"TX (Ethernet): {repr(data_to_send)}")
        sniffer_instance.log_communication('TX', virtual_port, data_to_send)
        sock.sendall(data_to_send.encode('utf-8'))
        
        # 4. 接收数据块 (类似串口读取直到超时)
        buf_size = 4096
        response_bytes = b""
        
        first_chunk = sock.recv(buf_size)
        if not first_chunk:
            # 可能是对方断开了，我们把被污染的连接踢出池子
            conn_key = f"{local_ip}=>{ip_address}:{port}" if local_ip else f"{ip_address}:{port}"
            _connection_pool.pop(conn_key, None)
            return False, "服务器已断开连接，未能读取到数据。"
            
        response_bytes += first_chunk
        
        sock.settimeout(0.1) 
        while True:
            try:
                chunk = sock.recv(buf_size)
                if not chunk:
                    break
                response_bytes += chunk
            except socket.timeout:
                break
            except Exception as e:
                logger.warning(f"接收后续数据块时出现异常: {e}")
                break

        # 恢复默认的超时时间以供下次使用
        sock.settimeout(timeout_s)
        
        # 解码
        try:
            response_string = response_bytes.decode('utf-8', errors='ignore').strip()
        except:
            response_string = response_bytes.decode('ascii', errors='ignore').strip()
            
        logger.info(f"RX (Ethernet): {response_string}")
        sniffer_instance.log_communication('RX', virtual_port, response_string)
        
        if not response_string:
             return False, f"请求 '{cmd}' 后无响应数据"
             
        # 5. 【新增特新】简化的快捷提取功能 (优先级高于自定义正则)
        if extract_key:
            # 构建一个通用的、能应对空格和等号的数字提取正则
            # 解释: 匹配 extract_key，紧跟着可能的等号或冒号和空格，然后提取纯数字序列（包括负号和小数点）
            # 例如: "MPHASE = 1", "v  2994.0", "Key: -1.5"
            escaped_key = re.escape(extract_key)
            # 这个正则表示： 匹配键名 + \s* (可能有的空格) + [=:]? (可选的等号或冒号) + \s* (可能有的空格) + ([-\d\.]+) (提取数字)
            auto_regex = escaped_key + r"\s*[=:]?\s*([-\d\.]+)"
            
            try:
                match = re.search(auto_regex, response_string, re.IGNORECASE)
                if match:
                    extracted_text = match.group(1)
                    try:
                        extracted_value = float(extracted_text)
                        logger.info(f"自动提取键 '{extract_key}' 数值成功: {extracted_value}")
                        return extracted_value, f"原始回复: {response_string} | 提取值: {extracted_value}"
                    except ValueError:
                         return False, f"找到了键 '{extract_key}' 的值 '{extracted_text}'，但无法转为浮点数。"
                else:
                    return False, f"未能从回复 ({response_string}) 中自动提取到键 '{extract_key}' 的数值。"
            except Exception as e:
                 return False, f"自动提取报错: {e}"

        # 6. 正则表达式提取处理
        elif regex_pattern:
            try:
                match = re.search(regex_pattern, response_string)
                if match:
                    extracted_text = match.group(1) # 获取提取组内容
                    try:
                        extracted_value = float(extracted_text)
                        logger.info(f"正则提取数值成功: {extracted_value}")
                        return extracted_value, f"原始回复: {response_string} | 提取值: {extracted_value}"
                    except ValueError:
                        return False, f"正则匹配到了 '{extracted_text}'，但它无法被转换为浮点数。"
                else:
                    return False, f"未能从回复 ({response_string}) 中匹配到正则 '{regex_pattern}'。"
            except re.error as e:
                return False, f"正则表达式 '{regex_pattern}' 语法错误: {e}"

        # 7. 没有提取参数，直接返回完整字符串
        return response_string, f"接收到: {response_string}"

    except socket.timeout:
         return False, f"网络通信超时 ({timeout_s}s)"
    except Exception as e:
        logger.error(f"以太网通信时发生错误: {e}", exc_info=True)
        # 如果出错，把死掉的连接清理掉
        conn_key = f"{local_ip}=>{ip_address}:{port}" if local_ip else f"{ip_address}:{port}"
        _connection_pool.pop(conn_key, None)
        return False, f"以太网通信失败: {e}"

def send_command(cmd: str, test_engine_instance=None, **kwargs):
    """
    通过以太网 (TCP) 发送命令，直接返回收到的完整字符串。
    比 request_and_get_string 少了提取参数，用起来更简单。
    
    :param cmd: 要发送的字符串命令。
    :return: (返回完整字符串内容, 消息)

    用法示例:
    - 只需要在参数里填: {"cmd": "flt"}
    - 配置比较模式: Contains
    """
    return request_and_get_string(cmd=cmd, test_engine_instance=test_engine_instance, **kwargs)
