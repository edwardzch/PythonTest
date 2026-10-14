# sniffer.py

import logging
import os
from datetime import datetime
from PySide6.QtCore import QObject, Signal

class Sniffer(QObject):
    """
    一个用于捕获和记录通信数据的单例工具。
    """
    # 信号定义：发送捕获到的数据包
    # 参数: 时间戳 (str), 方向 (str 'TX'/'RX'), 端口 (str), 数据 (str), 工位ID (str)
    data_captured = Signal(str, str, str, str, str)

    _instance = None

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super(Sniffer, cls).__new__(cls, *args, **kwargs)
        return cls._instance

    def __init__(self):
        # 防止重复初始化
        if hasattr(self, '_initialized'):
            return
        super().__init__()
        self._initialized = True
        
        self.log_directory = "SnifferReports"
        os.makedirs(self.log_directory, exist_ok=True)

        self.logging_sessions = {}  # {station_id: file_handler}
        self.logging_station_sns = {} # {station_id: sn}
        
        self.port_context = {}  # e.g., {'COM1': {'station_id': 'station_1', 'sn': 'SN123'}}
        self.port_to_station_map = {}  # e.g., {'COM27': 'station_1'} - from config

    def register_station_context(self, port, station_id, sn):
        """测试开始或设备调用时，注册一个端口/地址和工位/SN的关联"""
        if port:
            print(f"[Sniffer] 注册上下文: Port {port} -> Station {station_id} (SN: {sn})")
            self.port_context[port] = {'station_id': station_id, 'sn': sn}

    def unregister_station_context(self, port):
        """测试结束或设备调用结束时，注销端口/地址的关联"""
        if port and port in self.port_context:
            print(f"[Sniffer] 注销上下文: Port {port}")
            del self.port_context[port]

    def start_station_logging(self, station_id, sn="N/A", main_window=None):
        """
        开始为指定工位（或全局）记录抓包数据。
        :param station_id: 工位ID (如 'station_1', 或 'station_all')
        :param sn: 产品SN
        :param main_window: 主窗口实例，用于获取端口配置
        """
        if station_id in self.logging_sessions:
            self.stop_station_logging(station_id)

        # 更新端口映射
        if main_window:
            try:
                stations_cfg = main_window.global_config.get('stations', {})
                for st_id, st_cfg in stations_cfg.items():
                    # 串口
                    comm_port = st_cfg.get('comm_port')
                    if comm_port:
                        self.port_to_station_map[comm_port] = st_id
                    # 万用表 VISA 地址
                    dmm_addr = st_cfg.get('dmm_visa_address')
                    if dmm_addr:
                        self.port_to_station_map[dmm_addr] = st_id
                    # 以太网虚拟端口
                    eth = st_cfg.get('ethernet_config', {})
                    if eth and eth.get('ip_address') and eth.get('port'):
                        self.port_to_station_map[f"{eth['ip_address']}:{eth['port']}"] = st_id
            except Exception as e:
                print(f"[Sniffer] 无法获取端口配置: {e}")
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if station_id == "station_all":
            filename = f"{self.log_directory}/capture_all_{timestamp}.txt"
            title_name = "全局/共享设备"
        else:
            filename = f"{self.log_directory}/capture_{station_id}_{timestamp}.txt"
            title_name = f"工位 {station_id}"

        try:
            file_handler = open(filename, 'w', encoding='utf-8')
            file_handler.write(f"=== 抓包日志记录 ({title_name}) ===\n")
            file_handler.write(f"开始时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            file_handler.write(f"记录目标: {title_name} (SN: {sn})\n")
            file_handler.write("=" * 50 + "\n\n")
            
            self.logging_sessions[station_id] = file_handler
            self.logging_station_sns[station_id] = sn
            
            print(f"抓包日志已启动，目标: {station_id}, 文件: {filename}")
            return True, filename
        except Exception as e:
            print(f"启动抓包日志失败: {e}")
            if 'file_handler' in locals() and file_handler:
                file_handler.close()
            return False, str(e)

    def stop_station_logging(self, station_id):
        """
        停止指定工位的日志记录。
        """
        if station_id in self.logging_sessions:
            try:
                file_handler = self.logging_sessions.pop(station_id)
                file_handler.close()
                self.logging_station_sns.pop(station_id, None)
                print(f"工位 {station_id} 的抓包日志已停止。")
            except Exception as e:
                print(f"停止抓包日志时出错 ({station_id}): {e}")

    def stop_all_logging(self):
        """停止所有正在进行的日志记录"""
        for station_id in list(self.logging_sessions.keys()):
            self.stop_station_logging(station_id)

    def log_communication(self, direction, port, data, station_id=None, sn=None):
        """
        记录一次通信事件。
        它会发出信号用于实时显示，如果文件记录开启，则同时写入文件。
        
        :param direction: 'TX' (发送) or 'RX' (接收)
        :param port: 通信端口或设备地址 (e.g., 'COM1', 'ASRL29::INSTR', '192.168.1.100:5000')
        :param data: 通信数据 (bytes, bytearray or str)
        :param station_id: (可选) 显式指定的工位ID (e.g., 'station_1')
        :param sn: (可选) 显式指定的产品SN
        """
        # --- 从多个来源获取工位和SN ---
        if not station_id:
            # 优先级: port_to_station_map (from config) > port_context (runtime registered)
            station_id = self.port_to_station_map.get(port)
            if not station_id:
                context = self.port_context.get(port, {})
                station_id = context.get('station_id', 'UnknownStation')
        
        if not sn:
            context = self.port_context.get(port, {})
            dynamic_sn = context.get('sn')
            if dynamic_sn and dynamic_sn != 'N/A':
                sn = dynamic_sn
            else:
                sn = self.logging_station_sns.get(station_id, 'N/A')

        timestamp = datetime.now().strftime('%H:%M:%S.%f')[:-3]
        
        if isinstance(data, str):
            data_str = data.strip()
        elif isinstance(data, (bytes, bytearray)):
            data_str = data.hex(' ').upper()
        else:
            data_str = str(data)

        # 发送信号给Live Watch窗口 (带上 station_id)
        self.data_captured.emit(timestamp, direction, port, data_str, station_id or "")

        # 如果该工位正在记录日志，则写入对应的文件
        if station_id in self.logging_sessions:
            file_handler = self.logging_sessions[station_id]
            try:
                log_line = f"[{timestamp}] {station_id}(SN:{sn}) {direction} {port}: {data_str}\n"
                file_handler.write(log_line)
                file_handler.flush()
            except Exception as e:
                print(f"写入抓包日志时出错 ({station_id}): {e}")

        # 如果开启了全局抓包记录 ("station_all")，同时写入全局抓包文件
        if "station_all" in self.logging_sessions and station_id != "station_all":
            file_handler = self.logging_sessions["station_all"]
            try:
                log_line = f"[{timestamp}] {station_id}(SN:{sn}) {direction} {port}: {data_str}\n"
                file_handler.write(log_line)
                file_handler.flush()
            except Exception as e:
                print(f"写入全局抓包日志时出错: {e}")

# 创建一个全局单例
sniffer_instance = Sniffer()
