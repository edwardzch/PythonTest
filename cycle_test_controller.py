# 文件路径: cycle_test_controller.py (报告路径修复版)
# -*- coding: utf-8 -*-

import os
import re
import time
import threading
import datetime
import traceback
from functools import partial
from PySide6.QtCore import QObject, Signal, QRunnable, Slot, Qt


class CycleTestControllerSignals(QObject):
    update_status_text = Signal(str)
    update_running_time = Signal(float)
    update_station_stats = Signal(str, int, int)
    finished = Signal(list)
    aborted = Signal(list)


class CycleTestController(QRunnable):
    def __init__(self, main_app_instance, config):
        super().__init__()
        self.app = main_app_instance
        self.config = config
        self.signals = CycleTestControllerSignals()
        self.is_running = True
        self.is_paused = False
        self.results = []
        self.sn_base = self.config.get("start_sn", "SN-001")
        self.sn_increment = self.config.get("sn_increment", False)
        self._lock = threading.Lock()
        self._cycle_finish_condition = threading.Condition(self._lock)
        self._stations_finished_count = 0
        # 初始化每个工位的统计数据
        self.station_stats = {
            station_id: {'passed': 0, 'failed': 0}
            for station_id in self.config.get("selected_stations", [])
        }

    def _generate_base_sn_for_cycle(self, cycle_index):
        if not self.sn_increment:
            return self.sn_base
        increment = cycle_index
        match = re.match(r'^(.*?)(\d+)$', self.sn_base)
        if match:
            prefix, num_str = match.groups()
            num = int(num_str)
            padding = len(num_str)
            return f"{prefix}{num + increment:{'0' + str(padding)}d}"
        else:
            return f"{self.sn_base}-{cycle_index + 1}"

    @Slot()
    def run(self):
        try:
            selected_stations = self.config.get("selected_stations", [])
            total_cycles = self.config.get("cycle_count", 0)

            if not selected_stations or total_cycles == 0:
                self.signals.finished.emit([]);
                return

            start_time = datetime.datetime.now()
            controller_start_time = time.time() # 计时器开始时间
            base_dir = "CycleTestReports"
            date_dir = os.path.join(base_dir, start_time.strftime('%Y-%m-%d'))
            report_folder = f"Report_{start_time.strftime('%Y%m%d_%H%M%S')}"
            main_report_path = os.path.join(date_dir, report_folder)
            individual_reports_dir = os.path.join(main_report_path, "individual_reports")
            os.makedirs(individual_reports_dir, exist_ok=True)
            self.config['main_report_path'] = main_report_path

            stagger_delay = self.config.get("stagger_delay", 1.0)

            for i in range(total_cycles):
                if not self.is_running: break

                while self.is_paused:
                    # 暂停时也要更新时间
                    elapsed_time = time.time() - controller_start_time
                    self.signals.update_running_time.emit(elapsed_time)
                    time.sleep(0.1)
                    if not self.is_running: break
                if not self.is_running: break

                # 更新时间和状态
                elapsed_time = time.time() - controller_start_time
                self.signals.update_running_time.emit(elapsed_time)
                cycle_num = i + 1
                self.signals.update_status_text.emit(f"第 {cycle_num}/{total_cycles} 轮测试进行中...")

                with self._lock:
                    self._stations_finished_count = 0

                base_sn_for_this_cycle = self._generate_base_sn_for_cycle(i)

                for idx, station_id in enumerate(selected_stations):
                    if not self.is_running: break

                    # 从第二个工位开始，应用启动延迟
                    if idx > 0 and stagger_delay > 0:
                        time.sleep(stagger_delay)
                    
                    # 休眠后再次检查停止标志
                    if not self.is_running: break

                    frame = self.app.station_frames.get(station_id)
                    if not frame: continue

                    callback_slot = partial(self.on_station_test_finished, station_id=station_id, cycle_num=cycle_num)

                    frame.cycle_test_finished.connect(callback_slot, Qt.SingleShotConnection)
                    frame.start_cycle_test(base_sn_for_this_cycle, report_output_dir=individual_reports_dir)

                if not self.is_running: break

                with self._lock:
                    self._cycle_finish_condition.wait_for(
                        lambda: self._stations_finished_count >= len(selected_stations) or not self.is_running,
                        timeout=300
                    )
                    if self._stations_finished_count < len(selected_stations):
                        print(f"警告：第 {cycle_num} 轮测试超时或被中断。")

                time.sleep(0.5)

            time.sleep(0.5)
            if self.is_running:
                self.signals.finished.emit(self.results)
            else:
                self.signals.aborted.emit(self.results)

        except Exception as e:
            print(f"循环测试控制器发生严重错误: {e}");
            traceback.print_exc()
            self.signals.aborted.emit(self.results)

    def on_station_test_finished(self, result_data, station_id, cycle_num):
        content = result_data.get('content', {})
        fail_info_for_report = None
        message_content = content.get('message')
        if isinstance(message_content, dict):
            fail_details_raw = message_content.get('fail_details')
            if isinstance(fail_details_raw, dict):
                step_index = fail_details_raw.get('step_index', -1)
                step_name = 'N/A'
                if step_index != -1:
                    for step in content.get('all_steps_results', []):
                        if step.get('original_index') == step_index:
                            step_name = step.get('TestName', 'N/A');
                            break
                fail_info_for_report = {'step_name': step_name, 'message': fail_details_raw.get('message', ''),
                                        'result': fail_details_raw.get('result', '')}
        cpk_values = {}
        cpk_steps_to_check = self.config.get('cpk_steps', [])
        all_steps_results = content.get('all_steps_results', [])
        # 【修复】跟踪同名步骤出现次数，避免后面覆盖前面
        cpk_name_counter = {}
        for step_result in all_steps_results:
            test_name = step_result.get('TestName', '').strip()
            # 生成唯一key：同名步骤加 #2, #3 后缀
            if test_name in cpk_steps_to_check:
                cpk_name_counter[test_name] = cpk_name_counter.get(test_name, 0) + 1
                occurrence = cpk_name_counter[test_name]
                unique_key = test_name if occurrence == 1 else f"{test_name} #{occurrence}"
                if test_name in cpk_steps_to_check or unique_key in cpk_steps_to_check:
                    try:
                        # 【核心修复】使用 raw_result 获取原始测量值，而不是 result（可能是 "Done" 等显示值）
                        result_val = step_result.get('raw_result', step_result.get('result'))
                        # Handle tuple format: (bool, numeric_value) or (numeric_value, message_string)
                        if isinstance(result_val, (list, tuple)) and len(result_val) >= 2:
                            if isinstance(result_val[0], bool):
                                value_for_cpk = result_val[1]
                            else:
                                value_for_cpk = result_val[0]
                        elif isinstance(result_val, (list, tuple)) and len(result_val) == 1:
                            value_for_cpk = result_val[0]
                        else:
                            value_for_cpk = result_val

                        cpk_values[unique_key] = {'value': float(value_for_cpk),
                                                 'usl': float(step_result['UpperLimit']) if step_result.get(
                                                     'UpperLimit') not in [None, ''] else None,
                                                 'lsl': float(step_result['LowerLimit']) if step_result.get(
                                                     'LowerLimit') not in [None, ''] else None}
                    except (ValueError, TypeError, KeyError) as e:
                        cpk_values[unique_key] = {'value': 'N/A', 'usl': 'N/A', 'lsl': 'N/A'}
        
        
        with self._lock:
            status = content.get('status', 'UNKNOWN').upper()
            if status == 'PASS':
                self.station_stats[station_id]['passed'] += 1
            elif status == 'FAIL':
                self.station_stats[station_id]['failed'] += 1
            
            passed_count = self.station_stats[station_id]['passed']
            failed_count = self.station_stats[station_id]['failed']
            self.signals.update_station_stats.emit(station_id, passed_count, failed_count)

            self.results.append({
                "cycle": cycle_num,
                "station_id": station_id,
                "sn": content.get('uut_sn', 'N/A'),
                "status": content.get('status', 'UNKNOWN'),
                "duration": float(content.get('duration_raw', 0.0)),
                "fail_details": fail_info_for_report,
                "start_time": datetime.datetime.now() - datetime.timedelta(
                    seconds=float(content.get('duration_raw', 0.0))),
                "cpk_values": cpk_values
            })
            self._stations_finished_count += 1
            self._cycle_finish_condition.notify_all()

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        if self.is_paused:
            print("循环测试已暂停")
        else:
            print("循环测试已恢复")

    def stop(self):
        print("循环测试中止指令已接收...")
        self.is_running = False
        for frame in self.app.station_frames.values():
            if frame.active_thread:
                frame.active_thread.stop()
        with self._lock:
            self._cycle_finish_condition.notify_all()
