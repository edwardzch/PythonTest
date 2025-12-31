# 文件路径: test_station.py (透明转发版)

import threading
from PySide6.QtCore import QObject, Signal, QRunnable, Slot

from test_engine import TestEngine
from sniffer import sniffer_instance



class WorkerSignals(QObject):
    step_update = Signal(dict)
    final_status = Signal(dict)
    log = Signal(tuple)
    progress = Signal(int)
    paused_at = Signal(int)
    user_interaction = Signal(dict)  # 新增信号：用于请求主线程处理用户交互


class TestStation(QRunnable):
    def __init__(self, station_id, uut_sn, global_config, hardware_manager,
                 stop_all_event, sequence_data, available_modules,
                 is_debugging, breakpoints,
                 sequence_file_path, report_output_dir=None, 
                 operator_id=None, operator_name=None, work_order=None, target_qty=None, station_count=1):
        super().__init__()
        self.station_id = station_id
        self.uut_sn = uut_sn
        self.global_config = global_config
        self.hardware_manager = hardware_manager
        self.stop_all_event = stop_all_event
        self.sequence_data = sequence_data
        self.available_modules = available_modules
        self.is_debugging = is_debugging
        self.breakpoints = breakpoints
        self.sequence_file_path = sequence_file_path
        self.report_output_dir = report_output_dir
        self.report_output_dir = report_output_dir
        self.operator_id = operator_id
        self.operator_name = operator_name  # 【新增】操作员姓名
        self.work_order = work_order
        self.target_qty = target_qty
        self.station_count = station_count  # 【新增】工位数

        self.signals = WorkerSignals()

        self.local_stop_event = threading.Event()
        self.pause_event = threading.Event()
        self.step_event = threading.Event()
        self.resume_event = threading.Event()
        self.pause_event.set()

    def run(self):
        # --- Sniffer 上下文管理 ---
        station_comm_port = None
        try:
            # 1. 从配置中找到该工位关联的通信端口
            station_config = self.global_config.get('stations', {}).get(self.station_id, {})
            station_comm_port = station_config.get('comm_port')

            # 2. 注册上下文
            if station_comm_port:
                sniffer_instance.register_station_context(
                    port=station_comm_port,
                    station_id=self.station_id,
                    sn=self.uut_sn
                )

            # 3. 运行测试引擎
            engine = TestEngine(
                station_id=self.station_id, uut_sn=self.uut_sn,
                global_config=self.global_config, hardware_manager=self.hardware_manager,
                sequence_data=self.sequence_data, available_modules=self.available_modules,
                signals=self.signals,
                is_debugging=self.is_debugging,
                breakpoints=self.breakpoints, local_stop_event=self.local_stop_event,
                stop_all_event=self.stop_all_event, pause_event=self.pause_event,
                step_event=self.step_event, resume_event=self.resume_event,
                sequence_file_path=self.sequence_file_path,
                report_output_dir=self.report_output_dir,
                operator_id=self.operator_id,
                operator_name=self.operator_name,
                work_order=self.work_order,
                target_qty=self.target_qty,
                station_count=self.station_count
            )
            engine.run_sequence()

        finally:
            # 4. 确保测试结束后注销上下文
            if station_comm_port:
                sniffer_instance.unregister_station_context(station_comm_port)

    def stop(self):
        self.local_stop_event.set();
        self.pause_event.set();
        self.step_event.set();
        self.resume_event.set()

    def pause(self):
        self.pause_event.clear()
        self.signals.paused_at.emit(-1)  # 立刻通知GUI，它已经暂停了

    def resume(self):
        self.pause_event.set();
        self.resume_event.set();
        self.step_event.set()

    def step(self):
        self.pause_event.set();
        self.step_event.set()

    def update_breakpoints(self, new_breakpoints):
        self.breakpoints.clear();
        self.breakpoints.update(new_breakpoints)
