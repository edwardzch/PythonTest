# 文件路径: order_estimation_dialog.py
# 智能工单预测对话框 - 根据工单数量和测试参数预估完成时间
# -*- coding: utf-8 -*-

import os
import sqlite3
from datetime import datetime, timedelta
from math import ceil

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QLineEdit, QDialogButtonBox, QSpinBox, QFormLayout,
    QPushButton, QDoubleSpinBox, QFrame, QTimeEdit, QGridLayout,
    QAbstractSpinBox, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox
)
from PySide6.QtCore import Qt, Signal, QTimer, QTime, QSettings
from PySide6.QtGui import QFont

from utils.database_logger import get_db_path
from utils import work_order_db
import work_order_history_report


class OrderEstimationDialog(QDialog):
    """
    智能工单预测对话框。
    根据工单数量、测试工位数、测试时间等因素预估完成测试所需时间。
    """

    def __init__(self, parent=None, station_count=1, sequence_name="", sequence_data=None):
        super().__init__(parent)
        self.setWindowTitle("工单测试时间预测")
        self.setMinimumWidth(500)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint)

        self.station_count = station_count
        self.sequence_name = sequence_name
        self.sequence_data = sequence_data or []
        
        # 历史数据缓存
        self.historical_avg_duration = None
        self.historical_pass_rate = None
        self.historical_handling_time = None
        
        # 当前实际数据缓存
        self.current_pass = 0
        self.current_fail = 0
        
        # Load settings
        self.settings = QSettings("MyCompany", "PythonTestPlatform")
        
        self._init_ui()
        self._load_persisted_values() # Restore settings
        
        # 初始加载一次数据并计算
        QTimer.singleShot(100, self._trigger_recalc)
        
        # 连接UI信号
        self._connect_signals()

    def _init_ui(self):
        """初始化用户界面"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)

        # ========== 测试配置组 ==========
        config_group = QGroupBox("测试配置")
        config_layout = QGridLayout(config_group)

        # Row 0: 序列
        seq_title = QLabel("当前测试序列:")
        self.sequence_label = QLabel(self.sequence_name if self.sequence_name else "未加载序列")
        self.sequence_label.setStyleSheet("font-weight: bold; color: #2980b9;")
        config_layout.addWidget(seq_title, 0, 0)
        config_layout.addWidget(self.sequence_label, 0, 1, 1, 3)  # 跨3列

        # Row 1: 工位数 & 数量
        st_title = QLabel("测试工位数:")
        self.station_spinbox = QSpinBox()
        self.station_spinbox.setRange(1, 6)
        self.station_spinbox.setValue(self.station_count)
        self.station_spinbox.setSuffix(" 工位")
        config_layout.addWidget(st_title, 1, 0)
        config_layout.addWidget(self.station_spinbox, 1, 1)

        qty_title = QLabel("目标数量:")
        self.order_count_spinbox = QSpinBox()
        self.order_count_spinbox.setRange(1, 100000)
        self.order_count_spinbox.setValue(1000)
        self.order_count_spinbox.setSuffix(" 个")
        config_layout.addWidget(qty_title, 1, 2)
        config_layout.addWidget(self.order_count_spinbox, 1, 3)
        
        config_layout.setColumnStretch(1, 1)
        config_layout.setColumnStretch(3, 1)

        main_layout.addWidget(config_group)

        # ========== 自动计算参数 (只读) ==========
        time_group = QGroupBox("时间参数 (自动获取)")
        time_layout = QFormLayout(time_group)

        # 单次测试时间
        test_time_layout = QHBoxLayout()
        self.test_time_spinbox = QDoubleSpinBox()
        self.test_time_spinbox.setRange(0, 3600)
        self.test_time_spinbox.setSuffix(" 秒")
        self.test_time_spinbox.setDecimals(1)
        self.test_time_spinbox.setReadOnly(True) # ReadOnly
        self.test_time_spinbox.setButtonSymbols(QAbstractSpinBox.NoButtons)
        test_time_layout.addWidget(self.test_time_spinbox)
        
        self.test_time_source_label = QLabel("")
        self.test_time_source_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        test_time_layout.addWidget(self.test_time_source_label)
        test_time_layout.addStretch()
        time_layout.addRow("单次测试时间:", test_time_layout)

        # 拿取耗时 (Handling Time) - Replaces Install/Remove
        handling_layout = QHBoxLayout()
        self.handling_time_spinbox = QDoubleSpinBox()
        self.handling_time_spinbox.setRange(0, 300)
        self.handling_time_spinbox.setSuffix(" 秒")
        self.handling_time_spinbox.setDecimals(1)
        self.handling_time_spinbox.setReadOnly(True) # ReadOnly
        self.handling_time_spinbox.setButtonSymbols(QAbstractSpinBox.NoButtons)
        handling_layout.addWidget(self.handling_time_spinbox)
        
        handling_note = QLabel("(相邻两次测试间隔)")
        handling_note.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        handling_layout.addWidget(handling_note)
        handling_layout.addStretch()
        time_layout.addRow("拿取耗时:", handling_layout)

        # 预估测试通过率
        pass_rate_layout = QHBoxLayout()
        self.pass_rate_spinbox = QDoubleSpinBox()
        self.pass_rate_spinbox.setRange(0.0, 100.0)
        self.pass_rate_spinbox.setSuffix(" %")
        self.pass_rate_spinbox.setDecimals(1)
        self.pass_rate_spinbox.setReadOnly(True) # ReadOnly
        self.pass_rate_spinbox.setButtonSymbols(QAbstractSpinBox.NoButtons)
        pass_rate_layout.addWidget(self.pass_rate_spinbox)
        
        self.pass_rate_source_label = QLabel("")
        self.pass_rate_source_label.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        pass_rate_layout.addWidget(self.pass_rate_source_label)
        pass_rate_layout.addStretch()
        time_layout.addRow("实测通过率:", pass_rate_layout)

        main_layout.addWidget(time_group)

        # ========== 车间作息时间组 (保持不变) ==========
        schedule_group = QGroupBox("车间作息时间")
        schedule_layout = QFormLayout(schedule_group)
        
        schedule_info = QLabel("设置工作时间和休息时长，用于计算有效工作耗时")
        schedule_info.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        schedule_layout.addRow(schedule_info)

        # 工作时间：简单的区间输入
        work_layout = QHBoxLayout()
        self.work_start = QTimeEdit(QTime(8, 0))
        self.work_start.setDisplayFormat("HH:mm")
        work_layout.addWidget(self.work_start)
        work_layout.addWidget(QLabel(" - "))
        self.work_end = QTimeEdit(QTime(18, 0))
        self.work_end.setDisplayFormat("HH:mm")
        work_layout.addWidget(self.work_end)
        work_layout.addStretch()
        schedule_layout.addRow("工作时间:", work_layout)

        # 午饭时长：改为分钟数输入
        lunch_layout = QHBoxLayout()
        self.lunch_duration = QSpinBox()
        self.lunch_duration.setRange(0, 180)
        self.lunch_duration.setValue(60)
        self.lunch_duration.setSuffix(" 分钟")
        lunch_layout.addWidget(self.lunch_duration)
        lunch_layout.addStretch()
        schedule_layout.addRow("午餐时长:", lunch_layout)

        # 晚饭时长：改为分钟数输入
        dinner_layout = QHBoxLayout()
        self.dinner_duration = QSpinBox()
        self.dinner_duration.setRange(0, 180)
        self.dinner_duration.setValue(40)
        self.dinner_duration.setSuffix(" 分钟")
        dinner_layout.addWidget(self.dinner_duration)
        dinner_layout.addStretch()
        schedule_layout.addRow("晚餐时长:", dinner_layout)

        main_layout.addWidget(schedule_group)
        
        # ========== 预估结果组 (Same) ==========
        result_group = QGroupBox("预估结果")
        result_group.setStyleSheet("QGroupBox { font-weight: bold; border: 2px solid #3498db; border-radius: 8px; margin-top: 12px; padding-top: 10px; } QGroupBox::title { subcontrol-origin: margin; subcontrol-position: top center; padding: 0 10px; background-color: #3498db; color: white; border-radius: 4px; }")
        result_layout = QVBoxLayout(result_group)

        self.total_tests_label = QLabel("当前已完成总数: -")
        self.total_tests_label.setStyleSheet("font-size: 13px;")
        result_layout.addWidget(self.total_tests_label)

        self.duration_label = QLabel("预计完成总时间: -")
        self.duration_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #27ae60;")
        result_layout.addWidget(self.duration_label)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("background-color: #bdc3c7;")
        result_layout.addWidget(line)

        self.finish_time_label = QLabel("预计完成时刻: -")
        self.finish_time_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #2980b9;")
        result_layout.addWidget(self.finish_time_label)

        main_layout.addWidget(result_group)

        # ========== 按钮区 ==========
        button_layout = QHBoxLayout()
        
        button_layout.addStretch()
        
        self.close_button = QPushButton("关闭")
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)

        # History Button
        self.history_button = QPushButton("查看历史详情")
        self.history_button.setStyleSheet("""
            QPushButton { background-color: #9b59b6; color: white; border: none; padding: 8px 15px; border-radius: 4px; }
            QPushButton:hover { background-color: #8e44ad; }
        """)
        self.history_button.clicked.connect(self._show_history_details)
        button_layout.addWidget(self.history_button)

        main_layout.addLayout(button_layout)

    def _load_persisted_values(self):
        """Restore values from settings."""
        # 加载序列相关设置
        if self.sequence_name:
            key_prefix = f"OrderEstimation/{self.sequence_name}"
            saved_qty = self.settings.value(f"{key_prefix}/quantity", 1000)
            self.order_count_spinbox.setValue(int(saved_qty))
        
        # 加载车间作息时间（全局设置）
        work_start = self.settings.value("Workshop/work_start", "08:00")
        work_end = self.settings.value("Workshop/work_end", "18:00")
        lunch_duration = self.settings.value("Workshop/lunch_duration", 60)
        dinner_duration = self.settings.value("Workshop/dinner_duration", 40)
        
        self.work_start.setTime(QTime.fromString(work_start, "HH:mm"))
        self.work_end.setTime(QTime.fromString(work_end, "HH:mm"))
        self.lunch_duration.setValue(int(lunch_duration))
        self.dinner_duration.setValue(int(dinner_duration))

    def _save_settings(self):
        """保存当前设置到持久化存储。"""
        # 保存序列相关设置
        if self.sequence_name:
            key_prefix = f"OrderEstimation/{self.sequence_name}"
            self.settings.setValue(f"{key_prefix}/quantity", self.order_count_spinbox.value())
        
        # 保存车间作息时间（全局设置）
        self.settings.setValue("Workshop/work_start", self.work_start.time().toString("HH:mm"))
        self.settings.setValue("Workshop/work_end", self.work_end.time().toString("HH:mm"))
        self.settings.setValue("Workshop/lunch_duration", self.lunch_duration.value())
        self.settings.setValue("Workshop/dinner_duration", self.dinner_duration.value())
        
        self.settings.sync()  # 强制立即同步到存储
    
    def accept(self):
        """关闭对话框时保存设置。"""
        self._save_settings()
        super().accept()
    
    def reject(self):
        """取消对话框时也保存设置。"""
        self._save_settings()
        super().reject()
    
    def closeEvent(self, event):
        """Save values on close."""
        self._save_settings()
        super().closeEvent(event)

    def _connect_signals(self):
        """连接信号和槽"""
        # 参数变化重新计算
        self.station_spinbox.valueChanged.connect(self._trigger_recalc)
        self.order_count_spinbox.valueChanged.connect(self._trigger_recalc)
        self.lunch_duration.valueChanged.connect(self._trigger_recalc)
        self.dinner_duration.valueChanged.connect(self._trigger_recalc)

    def _trigger_recalc(self):
        self._load_historical_data()
        self._calculate_estimation()

    def _load_historical_data(self):
        """
        Smart Data Loading:
        - If current sequence has >= 10 samples: Use its REAL stats.
        - Else: Use Sequence Historical Stats.
        """
        sequence_name = self.sequence_name
        
        # Defaults
        avg_time = 0.0
        pass_rate = 95.0
        handling_time = 5.0
        source_desc = "(无数据)"
        
        use_historical = True

        if sequence_name:
            # 使用序列名作为标识查询数据
            wo_info = work_order_db.get_work_order_info(sequence_name)
            if wo_info:
                sample_count = wo_info.get('pass_qty', 0) + wo_info.get('fail_qty', 0)
                if sample_count >= 10:
                    # Adequate samples, use real data
                    use_historical = False
                    avg_time = wo_info.get('avg_duration', 0.0)
                    pass_rate = wo_info.get('pass_rate', 95.0)
                    # Get Handling Time
                    handling_time = work_order_db.get_avg_handling_time(sequence_name)
                    source_desc = f"(数据源: 序列统计, 样本: {sample_count})"
                
                # Update current counts regardless of sample size
                self.current_pass = wo_info.get('pass_qty', 0)
                self.current_fail = wo_info.get('fail_qty', 0)
            else:
                self.current_pass = 0
                self.current_fail = 0
        else:
            self.current_pass = 0
            self.current_fail = 0

        if use_historical:
             # Fallback to general history
             hist_avg = work_order_db.get_historical_avg_for_sequence(sequence_name)
             if hist_avg:
                 avg_time = hist_avg
             
             # Approx handling time for sequence
             if sequence_name:
                 handling_time = work_order_db.get_sequence_handling_time_avg(sequence_name)
             source_desc = "(数据源: 历史记录)"

        # Update UI
        if avg_time > 0:
            self.test_time_spinbox.setValue(avg_time)
        self.pass_rate_spinbox.setValue(pass_rate)
        self.handling_time_spinbox.setValue(handling_time)
        
        self.test_time_source_label.setText(source_desc)
        self.pass_rate_source_label.setText(source_desc)

    def _calculate_estimation(self):
        """计算预估时间"""
        # 获取输入参数
        target_pass_count = self.order_count_spinbox.value()
        station_count = self.station_spinbox.value()
        single_test_time = self.test_time_spinbox.value()
        handling_time = self.handling_time_spinbox.value() # 拿取耗时 (Interval)
        pass_rate = self.pass_rate_spinbox.value() / 100.0

        if pass_rate <= 0:
            pass_rate = 0.01

        # ========== 核心计算逻辑 ==========
        
        # 1. 单个产品的平均测试周期 (CT)
        # 理想情况: 所有工位并行。
        # 当 PassRate < 100% 时，意味着有些产品测试了多次。
        # 
        # 预期测试次数 / Pass产出 = 1 / PassRate
        # 例如 90% 良率，产出 100 个良品，大约需要测试 100 / 0.9 = 111.1 次
        # 
        # 总需要的测试次数 = Target_Pass_Qty / PassRate
        total_tests_needed = ceil(target_pass_count / pass_rate)
        
        # 2. 单次测试耗时 = 测试时间 + 拿取(间隔)时间
        cycle_time_per_test = single_test_time + handling_time
        
        # 3. 总工作时间 (人时/机时) = 总测试次数 * 单次耗时
        total_man_machine_seconds = total_tests_needed * cycle_time_per_test
        
        # 4. 考虑多工位并行
        # 实际耗时 = 总工作时间 / 工位数
        actual_duration_seconds = total_man_machine_seconds / station_count
        
        # 6. 计算完成时刻（考虑休息时间）
        finish_datetime = self._calculate_finish_time_with_breaks(actual_duration_seconds)

        # ========== 更新显示 ==========
        
        # 当前已完成总数
        current_total = self.current_pass + self.current_fail
        self.total_tests_label.setText(
            f"当前已完成总数: {current_total:,} 次 "
            f"(Pass: {self.current_pass}, Fail: {self.current_fail})"
        )

        # 更新时间参数组里的显示(spinbox)
        self.test_time_spinbox.setValue(single_test_time)
        self.handling_time_spinbox.setValue(handling_time)
        self.pass_rate_spinbox.setValue(pass_rate * 100)

        # 预计完成时间
        hours, remainder = divmod(int(actual_duration_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        
        if hours > 0:
            duration_str = f"{hours} 小时 {minutes} 分钟 {seconds} 秒"
        elif minutes > 0:
            duration_str = f"{minutes} 分钟 {seconds} 秒"
        else:
            duration_str = f"{seconds} 秒"
        
        self.duration_label.setText(f"预计工作时间: {duration_str}")

        # 预计完成时刻
        finish_str = finish_datetime.strftime("%Y-%m-%d %H:%M:%S")
        self.finish_time_label.setText(f"预计完成时刻: {finish_str}")

    def _calculate_finish_time_with_breaks(self, work_seconds):
        """
        计算考虑休息时间后的实际完成时刻。
        使用工作时间和吃饭时长来计算。
        
        Args:
            work_seconds: 需要的纯工作时间（秒）
            
        Returns:
            datetime: 预计完成的日期时间
        """
        # 获取工作时间设置
        work_start_time = self.work_start.time()
        work_end_time = self.work_end.time()
        lunch_mins = self.lunch_duration.value()
        dinner_mins = self.dinner_duration.value()
        
        # 将QTime转换为秒数
        work_start_sec = work_start_time.hour() * 3600 + work_start_time.minute() * 60
        work_end_sec = work_end_time.hour() * 3600 + work_end_time.minute() * 60
        
        # 假设午餐在工作时间的中间（如12:00），晚餐在17:00左右
        lunch_start_sec = 12 * 3600  # 12:00
        dinner_start_sec = 17 * 3600  # 17:00
        
        # 每天有效工作时间 = 总工作时间 - 午餐 - 晚餐
        total_work_per_day = (work_end_sec - work_start_sec) - (lunch_mins + dinner_mins) * 60
        if total_work_per_day <= 0:
            total_work_per_day = 8 * 3600  # 默认8小时
        
        current_datetime = datetime.now()
        remaining_work = work_seconds
        
        # 最多模拟30天
        max_days = 30
        day_count = 0
        
        while remaining_work > 0 and day_count < max_days:
            day_count += 1
            
            # 今天还剩多少工作时间
            current_time_sec = current_datetime.hour * 3600 + current_datetime.minute * 60 + current_datetime.second
            
            # 如果当前时间已过下班时间，跳到第二天
            if current_time_sec >= work_end_sec:
                next_day = current_datetime.replace(hour=work_start_time.hour(), minute=work_start_time.minute(), 
                                                    second=0, microsecond=0) + timedelta(days=1)
                current_datetime = next_day
                continue
            
            # 如果还没上班，跳到上班时间
            if current_time_sec < work_start_sec:
                current_datetime = current_datetime.replace(hour=work_start_time.hour(), 
                                                           minute=work_start_time.minute(), 
                                                           second=0, microsecond=0)
                current_time_sec = work_start_sec
            
            # 计算今天剩余可用工作时间
            time_until_end = work_end_sec - current_time_sec
            
            # 减去今天剩余的吃饭时间
            breaks_remaining = 0
            if current_time_sec < lunch_start_sec:
                breaks_remaining += lunch_mins * 60
            if current_time_sec < dinner_start_sec:
                breaks_remaining += dinner_mins * 60
            
            available_today = max(0, time_until_end - breaks_remaining)
            
            if remaining_work <= available_today:
                # 今天能完成
                current_datetime = current_datetime + timedelta(seconds=remaining_work)
                remaining_work = 0
            else:
                # 用完今天的时间，跳到第二天
                remaining_work -= available_today
                next_day = current_datetime.replace(hour=work_start_time.hour(), minute=work_start_time.minute(), 
                                                    second=0, microsecond=0) + timedelta(days=1)
                current_datetime = next_day
        
        return current_datetime

    def _show_history_details(self):
        """Show history HTML report for ALL work orders."""
        try:
            success, msg = work_order_history_report.generate_and_open_history_report()
            if not success:
                QMessageBox.warning(self, "错误", f"无法生成报告: {msg}")
        except Exception as e:
            QMessageBox.critical(self, "错误", str(e))



class RealTimeOrderTracker:
    """
    实时工单进度追踪器。
    在测试过程中根据实际测试数据更新预测。
    """

    def __init__(self, target_pass_count, station_count):
        self.target_pass_count = target_pass_count
        self.station_count = station_count
        self.start_time = None
        
        # 统计数据
        self.total_tests = 0
        self.pass_count = 0
        self.fail_count = 0
        self.test_durations = []  # 记录每次测试时长
        
    def start(self):
        """开始追踪"""
        self.start_time = datetime.now()
        
    def record_test(self, is_pass, duration):
        """记录一次测试结果"""
        self.total_tests += 1
        self.test_durations.append(duration)
        
        if is_pass:
            self.pass_count += 1
        else:
            self.fail_count += 1
    
    def get_current_pass_rate(self):
        """获取当前通过率"""
        if self.total_tests == 0:
            return 0.0
        return self.pass_count / self.total_tests
    
    def get_average_duration(self):
        """获取平均测试时长"""
        if not self.test_durations:
            return 0.0
        return sum(self.test_durations) / len(self.test_durations)
    
    def get_remaining_count(self):
        """获取剩余需要PASS的数量"""
        return max(0, self.target_pass_count - self.pass_count)
    
    def estimate_remaining_time(self):
        """
        根据当前数据估算剩余时间。
        Returns: 剩余秒数，如果数据不足返回None
        """
        if self.total_tests < 3:  # 至少需要3组数据才能估算
            return None
        
        remaining_pass = self.get_remaining_count()
        if remaining_pass <= 0:
            return 0
        
        current_pass_rate = self.get_current_pass_rate()
        if current_pass_rate <= 0:
            return None  # 无法估算
        
        avg_duration = self.get_average_duration()
        
        # 估算需要的测试次数
        remaining_tests = ceil(remaining_pass / current_pass_rate)
        
        # 考虑多工位并行
        tests_per_station = ceil(remaining_tests / self.station_count)
        
        return tests_per_station * avg_duration
    
    def get_estimated_finish_time(self):
        """获取预计完成时刻"""
        remaining = self.estimate_remaining_time()
        if remaining is None:
            return None
        return datetime.now() + timedelta(seconds=remaining)
    
    def get_progress_summary(self):
        """获取进度摘要"""
        remaining_pass = self.get_remaining_count()
        progress = (self.pass_count / self.target_pass_count * 100) if self.target_pass_count > 0 else 0
        
        summary = {
            'total_tests': self.total_tests,
            'pass_count': self.pass_count,
            'fail_count': self.fail_count,
            'remaining_pass': remaining_pass,
            'progress_percent': min(100.0, progress),
            'current_pass_rate': self.get_current_pass_rate() * 100,
            'avg_duration': self.get_average_duration(),
        }
        
        est_finish = self.get_estimated_finish_time()
        if est_finish:
            summary['estimated_finish_time'] = est_finish.strftime("%Y-%m-%d %H:%M:%S")
            remaining_time = self.estimate_remaining_time()
            if remaining_time:
                hours, remainder = divmod(int(remaining_time), 3600)
                minutes, seconds = divmod(remainder, 60)
                summary['remaining_time_str'] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
        
        return summary


if __name__ == '__main__':
    import sys
    from PySide6.QtWidgets import QApplication
    
    app = QApplication(sys.argv)
    dialog = OrderEstimationDialog(
        station_count=3,
        sequence_name="TestSequence_V1.0"
    )
    dialog.show()
    sys.exit(app.exec())
