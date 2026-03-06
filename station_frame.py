import time
import os
from collections import deque

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QComboBox, QTableWidget,
    QTableWidgetItem, QSplitter, QTextEdit, QProgressBar, QMessageBox, QHeaderView,
    QAbstractItemView, QCheckBox, QSizePolicy, QStackedLayout, QApplication, QLineEdit
)
from PySide6.QtCore import Qt, Signal, Slot, QTimer, QEvent
from PySide6.QtGui import QFontMetrics, QColor, QPen, QFont

# 从我们新建的模块中导入
from constants import STATUS_STYLES, LOG_LEVEL_COLORS
from ui_components import RowColorDelegate, STEP_STATUS_ROLE
from utils.database_logger import check_sn_exists, update_test_result_to_pass, get_recent_fail_record


class StationFrame(QWidget):
    # 新增信号，专门给循环测试控制器使用
    cycle_test_finished = Signal(dict)

    def __init__(self, parent, station_config, start_callback, app_instance, has_permission_func):  # <--- Modified here
        super().__init__(parent)
        self.app = app_instance;
        self.station_config = station_config;
        self.start_callback = start_callback
        self.id = station_config['id'];
        self.active_thread = None;
        self.breakpoints = set()
        self.is_in_debug_mode = False;
        self.user_stopped_in_debug = False;
        self.current_highlighted_row = -1
        self.sn_history = deque(maxlen=10);
        self.pass_count, self.fail_count, self.total_count = 0, 0, 0
        # 智能统计追踪
        self.sn_test_history = {}  # {sn: {'status': 'FAIL', 'time': timestamp, 'retry_count': 0}}
        self.counted_sns = set()   # 已计入统计的SN集合 (用于唯一SN场景)
        # 全局连续失败追踪（与SN无关，但SN改变会重置）
        self.consecutive_fail_count = 0  # 连续失败次数
        self.last_tested_sn = None  # 最后测试的SN，SN改变时重置连续失败计数
        self.has_permission = has_permission_func  # <--- New instance variable
        self._is_running_cycle_test = False  # 标记当前是否正在运行循环测试

        self.control_stack = QStackedLayout();
        self.stop_click_timer = QTimer(self);
        self.stop_click_timer.setInterval(250)
        self.stop_click_timer.setSingleShot(True);
        self._create_widgets();
        self._connect_signals_and_slots()
        self.update_button_states('idle');
        self.toggle_log_visibility(False);
        self.update_status('IDLE')
        self.timer = QTimer(self);
        self.timer.timeout.connect(self.update_test_time)

    def _create_widgets(self):
        main_layout = QVBoxLayout(self);
        main_layout.setContentsMargins(10, 5, 10, 5);
        self.setObjectName("StationFrame");
        self.setStyleSheet("#StationFrame { border: 1px solid #444; border-radius: 5px; }");
        top_bar = QWidget()
        top_bar_layout = QHBoxLayout(top_bar)
        top_bar_layout.setContentsMargins(0, 0, 0, 0)
        station_name_label = QLabel(f"工位 {self.id.split('_')[-1]}")
        station_name_label.setStyleSheet("font-size: 16px; font-weight: bold;")

        self.status_label = QLabel("空闲");
        self.status_label.setAlignment(Qt.AlignCenter);

        # 增加字体大小 (+12)
        font_size = self.font().pointSize()
        if font_size <= 0: font_size = 9
        new_size = font_size + 2

        self.status_label.setStyleSheet(
            f"font-size: {new_size}pt; font-weight: bold; padding: 5px; border-radius: 3px;");
        self.status_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred);
        self.status_label.setFixedHeight(38);
        self.status_label.setToolTip("当前工位状态");

        control_container = QWidget();
        control_container.setLayout(self.control_stack);
        self.control_stack.setSizeConstraint(QStackedLayout.SetFixedSize);
        self.control_stack.setContentsMargins(0, 0, 0, 0);

        idle_widget = QWidget();
        idle_layout = QHBoxLayout(idle_widget);
        idle_layout.setContentsMargins(0, 0, 0, 0);
        idle_layout.setSpacing(5);
        self.idle_start_button = QPushButton("▶");
        self.idle_debug_button = QPushButton("🐞");
        self.idle_debug_button.setEnabled(self.has_permission('allow_debug'))
        self.idle_reset_button = QPushButton("⟳");
        idle_layout.addWidget(self.idle_start_button);
        idle_layout.addWidget(self.idle_debug_button);
        idle_layout.addWidget(self.idle_reset_button);
        self.control_stack.addWidget(idle_widget);

        testing_widget = QWidget();
        testing_layout = QHBoxLayout(testing_widget);
        testing_layout.setContentsMargins(0, 0, 0, 0);
        testing_layout.setSpacing(5);
        self.test_pause_button = QPushButton("⏸");
        self.test_abort_button = QPushButton("■");
        self.test_resume_button = QPushButton("▶");
        testing_layout.addWidget(self.test_pause_button);
        testing_layout.addWidget(self.test_abort_button);
        testing_layout.addWidget(self.test_resume_button);
        self.control_stack.addWidget(testing_widget);
        debugging_widget = QWidget();
        debugging_layout = QHBoxLayout(debugging_widget);
        debugging_layout.setContentsMargins(0, 0, 0, 0);
        debugging_layout.setSpacing(5);
        self.debug_abort_button = QPushButton("■");
        self.debug_step_button = QPushButton("→");
        self.debug_resume_button = QPushButton("▶");
        debugging_layout.addWidget(self.debug_abort_button);
        debugging_layout.addWidget(self.debug_step_button);
        debugging_layout.addWidget(self.debug_resume_button);
        self.control_stack.addWidget(debugging_widget);
        button_style = "font-size: 18px; font-weight: bold;";
        for btn, tooltip in [(self.idle_start_button, "开始测试"), (self.idle_debug_button, "开始调试"),
                             (self.idle_reset_button, "重置统计"), (self.test_pause_button, "暂停"),
                             (self.test_abort_button, "中止测试"), (self.test_resume_button, "继续"),
                             (self.debug_abort_button, "中止调试"), (self.debug_step_button, "单步执行"),
                             (self.debug_resume_button, "继续运行")]: btn.setFixedSize(38, 38); btn.setToolTip(
            tooltip); btn.setStyleSheet(button_style)
        self.log_toggle = QCheckBox("日志");
        self.log_toggle.setChecked(False);

        top_bar_layout.addWidget(station_name_label);
        top_bar_layout.addWidget(self.status_label, 1);
        top_bar_layout.addWidget(control_container);
        top_bar_layout.addWidget(self.log_toggle);
        sn_stats_bar = QWidget();
        sn_stats_layout = QHBoxLayout(sn_stats_bar);
        sn_stats_layout.setContentsMargins(0, 0, 0, 0);
        sn_stats_layout.setSpacing(10);
        sn_stats_layout.addWidget(QLabel("产品SN:"));
        self.sn_entry = QComboBox();
        self.sn_entry.setEditable(True);
        self.sn_entry.lineEdit().setPlaceholderText("扫描或输入SN后按回车开始...");
        self.sn_entry.lineEdit().installEventFilter(self);  # 为双击事件监听
        self.sn_entry.installEventFilter(self);  # 为焦点事件监听

        stats_widget = QWidget();
        stats_layout = QHBoxLayout(stats_widget);
        stats_layout.setContentsMargins(0, 0, 0, 0);
        stats_layout.setSpacing(10);
        self.test_time_label = QLabel("时间: 0.00s");
        self.pass_label = QLabel("通过: 0");
        self.fail_label = QLabel("失败: 0");
        self.total_label = QLabel("总数: 0");
        self.rate_label = QLabel("合格率: 0.00%");
        fm = QFontMetrics(self.test_time_label.font());
        time_width = fm.horizontalAdvance("时间: 999.99s");
        pass_width = fm.horizontalAdvance("通过: 9999");
        fail_width = fm.horizontalAdvance("失败: 999");
        total_width = fm.horizontalAdvance("总数: 9999");
        self.test_time_label.setMinimumWidth(time_width);
        self.pass_label.setMinimumWidth(pass_width);
        self.fail_label.setMinimumWidth(fail_width);
        self.total_label.setMinimumWidth(total_width);
        for label in [self.test_time_label, self.pass_label, self.fail_label, self.total_label,
                      self.rate_label]: stats_layout.addWidget(label)
        sn_stats_layout.addWidget(self.sn_entry, 1);
        sn_stats_layout.addWidget(stats_widget);
        self.steps_view = QTableWidget();
        self._setup_steps_view();
        self.steps_view.setItemDelegate(RowColorDelegate(self.steps_view));
        self.log_area = QTextEdit();
        self.log_area.setReadOnly(True);
        self.splitter = QSplitter(Qt.Vertical);
        self.splitter.addWidget(self.steps_view);
        self.splitter.addWidget(self.log_area);
        self.splitter.setStretchFactor(0, 3);
        self.splitter.setStretchFactor(1, 1);
        self.progress_bar = QProgressBar();
        self.progress_bar.setTextVisible(False);
        self.progress_bar.setVisible(False);
        main_layout.addWidget(top_bar);
        main_layout.addWidget(sn_stats_bar);
        main_layout.addWidget(self.splitter);
        main_layout.addWidget(self.progress_bar);
        main_layout.setStretch(0, 0);
        main_layout.setStretch(1, 0);
        main_layout.setStretch(2, 1);
        main_layout.setStretch(3, 0)

        # 将除SN输入框外的所有控件的焦点策略设为NoFocus，以控制Tab键行为
        widgets_to_disable_focus = [
            self.idle_start_button, self.idle_debug_button, self.idle_reset_button,
            self.test_pause_button, self.test_abort_button, self.test_resume_button,
            self.debug_abort_button, self.debug_step_button, self.debug_resume_button,
            self.log_toggle, self.steps_view
        ]
        for widget in widgets_to_disable_focus:
            widget.setFocusPolicy(Qt.NoFocus)

    def _setup_steps_view(self):
        self.steps_view.setColumnCount(6)
        self.steps_view.setHorizontalHeaderLabels(['●', '步骤', '测试名称', '范围', '结果', '信息'])
        self.steps_view.verticalHeader().setVisible(False)
        self.steps_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.steps_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        
        # 启用自动换行
        self.steps_view.setWordWrap(True)
        self.steps_view.setTextElideMode(Qt.ElideNone)

        # 设置表头字体 (+12) - 使用setStyleSheet以确保覆盖主题
        base_font = self.steps_view.font()
        font_size = base_font.pointSize()
        if font_size <= 0: font_size = 9
        new_size = font_size + 2

        self.steps_view.horizontalHeader().setStyleSheet(f"font-size: {new_size}pt; font-weight: bold;")
        # header_font = QFont(base_font)
        # header_font.setPointSize(base_font.pointSize() + 12)
        # header_font.setBold(True)
        # self.steps_view.horizontalHeader().setFont(header_font)

        header = self.steps_view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        self.steps_view.setColumnWidth(0, 30)
        self.steps_view.setColumnWidth(1, 100)  # 增加宽度以适应3位数步骤 (原60)
        self.steps_view.setColumnWidth(2, 200)
        self.steps_view.setColumnWidth(3, 120)
        self.steps_view.setColumnWidth(4, 100)
        header.setStretchLastSection(True)

    def _connect_signals_and_slots(self):
        self.log_toggle.toggled.connect(self.toggle_log_visibility);
        self.sn_entry.lineEdit().returnPressed.connect(self.on_start_test_normal_click);
        self.idle_start_button.clicked.connect(self.on_start_test_normal_click);
        self.idle_debug_button.clicked.connect(lambda: self._start_test_flow(is_debugging=True));
        self.idle_reset_button.clicked.connect(self.reset_stats_manual);
        self.test_pause_button.clicked.connect(self.on_test_pause);
        self.test_abort_button.clicked.connect(self.on_abort_clicked);
        self.test_resume_button.clicked.connect(self.on_test_resume);
        self.debug_abort_button.clicked.connect(self.on_abort_clicked);
        self.debug_step_button.clicked.connect(self.on_debug_step);
        self.debug_resume_button.clicked.connect(self.on_debug_resume);
        self.steps_view.cellClicked.connect(self._on_breakpoint_click)

    def update_button_states(self, state, is_paused=False):
        if state == 'idle':
            self.control_stack.setCurrentIndex(0)
        elif self.is_in_debug_mode:
            self.control_stack.setCurrentIndex(2);
            self.debug_resume_button.setEnabled(
                is_paused);
            self.debug_step_button.setEnabled(is_paused);
            self.debug_abort_button.setEnabled(True)
        else:
            self.control_stack.setCurrentIndex(1);
            self.test_pause_button.setEnabled(
                not is_paused);
            self.test_resume_button.setEnabled(is_paused);
            self.test_abort_button.setEnabled(True)
        self.sn_entry.setEnabled(state == 'idle')

    def on_test_pause(self):
        if self.active_thread: self.active_thread.pause()

    def on_test_resume(self):
        if self.active_thread: 
            self.update_status('RUNNING')
            # 强制立即更新按钮状态，防止逻辑延迟
            self.test_resume_button.setEnabled(False)
            self.test_pause_button.setEnabled(True)
            self.update_button_states('running', is_paused=False)
            QApplication.processEvents()
            self.active_thread.resume()

    def on_debug_resume(self):
        if self.active_thread: self.update_status('DEBUG_RUNNING'); self.update_button_states('running',
                                                                                              is_paused=False); self.active_thread.resume()

    def on_debug_step(self):
        if self.active_thread: self.active_thread.step()

    def on_abort_clicked(self):
        if self.active_thread: self.user_stopped_in_debug = self.is_in_debug_mode; self.active_thread.stop()

    def _start_test_flow(self, is_debugging, report_output_dir=None):
        if is_debugging and (
                not self.app.sequence_data or not self.app.current_sequence_file_path): QMessageBox.warning(self,
                                                                                                            "提示",
                                                                                                            "请先打开一个测试程序才能开始调试。"); return
        current_sn = self.sn_entry.currentText().strip()
        if not current_sn: QMessageBox.critical(self, "错误", "产品SN不能为空！"); return
        if self.app.is_sequence_modified:
            reply = QMessageBox.question(self, '未保存的更改', '当前测试程序有未保存的更改。是否要在测试前保存？',
                                         QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if reply == QMessageBox.Save: self.app.save_sequence_to_file()
            if self.app.is_sequence_modified or reply == QMessageBox.Cancel: return
        self._add_sn_to_history(current_sn);
        self.is_in_debug_mode = is_debugging;
        self.reset_ui_for_new_run(preserve_breakpoints=True, show_breakpoints=is_debugging)
        self.test_start_time = time.time();
        self.timer.start(100);
        # 最终投递！将包裹交给 self.start_callback
        self.start_callback(self.id, current_sn, is_debugging, self.breakpoints.copy(),
                            report_output_dir=report_output_dir)
        QTimer.singleShot(0, lambda: self.app.advance_focus_to_next_station(self.id))
        self.update_button_states('running', is_paused=is_debugging)
        if is_debugging:
            self.update_status('DEBUG_PAUSED')
        else:
            self.update_status('RUNNING')

    def _set_row_status(self, row, status):
        if 0 <= row < self.steps_view.rowCount():
            for col in range(self.steps_view.columnCount()):
                item = self.steps_view.item(row, col)
                if item: item.setData(STEP_STATUS_ROLE, status)
            self.steps_view.viewport().update(self.steps_view.visualRect(self.steps_view.model().index(row, 0)))

    def _ensure_row_is_visible(self, row_index):
        if 0 <= row_index < self.steps_view.rowCount():
            item = self.steps_view.item(row_index, 0)
            if item: QTimer.singleShot(0,
                                       lambda: self.steps_view.scrollToItem(item, QAbstractItemView.PositionAtCenter))

    @Slot(int)
    def update_paused_at(self, step_index):
        if self.is_in_debug_mode:
            self.update_status('DEBUG_PAUSED')
            if step_index != -1:
                row_to_update = step_index
                if self.current_highlighted_row != -1 and self.current_highlighted_row != row_to_update: self._set_row_status(
                    self.current_highlighted_row, None)
                self._set_row_status(row_to_update, 'PAUSED');
                self.current_highlighted_row = row_to_update
                self._ensure_row_is_visible(row_to_update)
        else:
            self.update_status('PAUSED')
        self.update_button_states('paused', is_paused=True)

    @Slot(dict)
    def update_step_in_view(self, data: dict):
        content = data['content']
        row_to_update = content['step_index']
        status = content['status'].upper()
        if not (0 <= row_to_update < self.steps_view.rowCount()): return
        if self.current_highlighted_row != -1 and self.current_highlighted_row != row_to_update:
            last_status_item = self.steps_view.item(self.current_highlighted_row, 0)
            if last_status_item and last_status_item.data(STEP_STATUS_ROLE) in ['RUNNING', 'PAUSED']:
                self._set_row_status(self.current_highlighted_row, None)
        self._set_row_status(row_to_update, status)
        if status in ['RUNNING', 'PAUSED']:
            self.current_highlighted_row = row_to_update
            self._ensure_row_is_visible(row_to_update)
            if status == 'RUNNING' and not self.is_in_debug_mode: self.update_button_states('running', is_paused=False)
        else:
            if row_to_update == self.current_highlighted_row: self.current_highlighted_row = -1
        result_text = content.get('result', '')
        message_text = content.get('message', '')
        result_item = self.steps_view.item(row_to_update, 4)
        if result_item is None:
            result_item = QTableWidgetItem()
            self.steps_view.setItem(row_to_update, 4, result_item)
        message_item = self.steps_view.item(row_to_update, 5)
        if message_item is None:
            message_item = QTableWidgetItem()
            self.steps_view.setItem(row_to_update, 5, message_item)
        result_item.setText(result_text)
        result_item.setToolTip(result_text)
        message_item.setText(message_text)
        message_item.setToolTip(message_text)




    def load_sequence_to_view(self, sequence_data, preserve_breakpoints=False, show_breakpoints=True):
        self.steps_view.setRowCount(0)
        if not preserve_breakpoints: self.breakpoints.clear()

        # Create special font for TestName
        base_font = self.steps_view.font()
        test_name_font = QFont(base_font)
        test_name_font.setBold(False)
        test_name_font.setPointSize(base_font.pointSize() + 12)

        actual_step_count = 0
        for original_index, row_data in enumerate(sequence_data):
            self.steps_view.insertRow(original_index)
            test_name_full = str(row_data.get('TestName', '')).strip()
            row_type = 'normal'
            if test_name_full.startswith('*'):
                row_type = 'block'
            elif test_name_full.startswith('#'):
                row_type = 'comment'
            for col in range(self.steps_view.columnCount()):
                item = QTableWidgetItem()
                item.setData(Qt.UserRole, row_type)
                item.setData(STEP_STATUS_ROLE, None)
                self.steps_view.setItem(original_index, col, item)
            if row_type == 'block':
                text = test_name_full[1:].strip()
                self.steps_view.item(original_index, 2).setText(text)
                self.steps_view.item(original_index, 2).setToolTip(text)
                self.steps_view.item(original_index, 2).setFont(test_name_font)  # 区块标题字体
            elif row_type == 'comment':
                self.steps_view.item(original_index, 2).setText(test_name_full)
                self.steps_view.item(original_index, 2).setToolTip(test_name_full)
                self.steps_view.item(original_index, 2).setFont(test_name_font)  # 注释字体
            else:
                actual_step_count += 1
                bp_char = "●" if show_breakpoints and original_index in self.breakpoints else ""
                limits_text = f"[{row_data.get('LowerLimit', '')}, {row_data.get('UpperLimit', '')}]" if row_data.get(
                    'LowerLimit', '') or row_data.get('UpperLimit', '') else ""
                self.steps_view.item(original_index, 0).setText(bp_char)
                self.steps_view.item(original_index, 1).setText(str(actual_step_count))
                self.steps_view.item(original_index, 2).setText(test_name_full)
                self.steps_view.item(original_index, 2).setToolTip(test_name_full)
                self.steps_view.item(original_index, 3).setText(limits_text)
                self.steps_view.item(original_index, 3).setToolTip(limits_text)
                self.steps_view.item(original_index, 0).setTextAlignment(Qt.AlignCenter)
                self.steps_view.item(original_index, 1).setTextAlignment(Qt.AlignCenter)

                # 为所有列设置大字体
                for c in range(6):
                    if self.steps_view.item(original_index, c):
                        self.steps_view.item(original_index, c).setFont(test_name_font)
        self.steps_view.resizeRowsToContents()

    def update_button_states(self, state, is_paused=False):
        if state == 'idle':
            self.control_stack.setCurrentIndex(0)
        elif self.is_in_debug_mode:
            self.control_stack.setCurrentIndex(2);
            self.debug_resume_button.setEnabled(
                is_paused);
            self.debug_step_button.setEnabled(is_paused);
            self.debug_abort_button.setEnabled(True)
        else:
            self.control_stack.setCurrentIndex(1);
            self.test_pause_button.setEnabled(
                not is_paused);
            self.test_resume_button.setEnabled(is_paused);
            self.test_abort_button.setEnabled(True)
        self.sn_entry.setEnabled(state == 'idle')

    def on_test_pause(self):
        if self.active_thread: self.active_thread.pause()

    def on_test_resume(self):
        if self.active_thread: self.update_status('RUNNING'); self.active_thread.resume()

    def on_debug_resume(self):
        if self.active_thread: self.update_status('DEBUG_RUNNING'); self.update_button_states('running',
                                                                                              is_paused=False); self.active_thread.resume()

    def on_debug_step(self):
        if self.active_thread: self.active_thread.step()

    def on_abort_clicked(self):
        if self.active_thread: self.user_stopped_in_debug = self.is_in_debug_mode; self.active_thread.stop()

    def _start_test_flow(self, is_debugging, report_output_dir=None):
        if is_debugging and (
                not self.app.sequence_data or not self.app.current_sequence_file_path): QMessageBox.warning(self,
                                                                                                            "提示",
                                                                                                            "请先打开一个测试程序才能开始调试。"); return
        current_sn = self.sn_entry.currentText().strip()
        if not current_sn:
            # 在状态标签显示空SN提示，避免弹框
            self.status_label.setText("⚠ 产品SN不能为空")
            font_size = self.font().pointSize()
            if font_size <= 0: font_size = 9
            new_size = font_size + 12
            self.status_label.setStyleSheet(
                f"font-size: {new_size}pt; font-weight: bold; padding: 5px; border-radius: 3px; background-color: #f39c12; color: white;")
            return

        if self.app.is_sequence_modified:
            reply = QMessageBox.question(self, '未保存的更改', '当前测试程序有未保存的更改。是否要在测试前保存？',
                                         QMessageBox.Save | QMessageBox.Discard | QMessageBox.Cancel)
            if reply == QMessageBox.Save: self.app.save_sequence_to_file()
            if self.app.is_sequence_modified or reply == QMessageBox.Cancel: return
        self._add_sn_to_history(current_sn);
        self.is_in_debug_mode = is_debugging;
        self.reset_ui_for_new_run(preserve_breakpoints=True, show_breakpoints=is_debugging)
        self.test_start_time = time.time();
        self.timer.start(100);
        # 最终投递！将包裹交给 self.start_callback
        self.start_callback(self.id, current_sn, is_debugging, self.breakpoints.copy(),
                            report_output_dir=report_output_dir)
        QTimer.singleShot(0, lambda: self.app.advance_focus_to_next_station(self.id))
        self.update_button_states('running', is_paused=is_debugging)
        if is_debugging:
            self.update_status('DEBUG_PAUSED')
        else:
            self.update_status('RUNNING')

    def _set_row_status(self, row, status):
        if 0 <= row < self.steps_view.rowCount():
            for col in range(self.steps_view.columnCount()):
                item = self.steps_view.item(row, col)
                if item: item.setData(STEP_STATUS_ROLE, status)
            self.steps_view.viewport().update(self.steps_view.visualRect(self.steps_view.model().index(row, 0)))

    def _ensure_row_is_visible(self, row_index):
        if 0 <= row_index < self.steps_view.rowCount():
            item = self.steps_view.item(row_index, 0)
            if item: QTimer.singleShot(0,
                                       lambda: self.steps_view.scrollToItem(item, QAbstractItemView.PositionAtCenter))

    @Slot(int)
    def update_paused_at(self, step_index):
        if self.is_in_debug_mode:
            self.update_status('DEBUG_PAUSED')
            if step_index != -1:
                row_to_update = step_index
                if self.current_highlighted_row != -1 and self.current_highlighted_row != row_to_update: self._set_row_status(
                    self.current_highlighted_row, None)
                self._set_row_status(row_to_update, 'RUNNING');
                self.current_highlighted_row = row_to_update
                self._ensure_row_is_visible(row_to_update)
        else:
            self.update_status('PAUSED')
        self.update_button_states('paused', is_paused=True)

    @Slot(dict)
    def update_step_in_view(self, data: dict):
        content = data['content']
        row_to_update = content['step_index']
        status = content['status'].upper()
        if not (0 <= row_to_update < self.steps_view.rowCount()): return
        if self.current_highlighted_row != -1 and self.current_highlighted_row != row_to_update:
            last_status_item = self.steps_view.item(self.current_highlighted_row, 0)
            if last_status_item and last_status_item.data(STEP_STATUS_ROLE) in ['RUNNING', 'PAUSED']:
                self._set_row_status(self.current_highlighted_row, None)
        self._set_row_status(row_to_update, status)
        if status in ['RUNNING', 'PAUSED']:
            self.current_highlighted_row = row_to_update
            self._ensure_row_is_visible(row_to_update)
            if status == 'RUNNING' and not self.is_in_debug_mode: self.update_button_states('running', is_paused=False)
        else:
            if row_to_update == self.current_highlighted_row: self.current_highlighted_row = -1
        result_text = content.get('result', '')
        message_text = content.get('message', '')
        result_item = self.steps_view.item(row_to_update, 4)
        if result_item is None:
            result_item = QTableWidgetItem()
            self.steps_view.setItem(row_to_update, 4, result_item)
        message_item = self.steps_view.item(row_to_update, 5)
        if message_item is None:
            message_item = QTableWidgetItem()
            self.steps_view.setItem(row_to_update, 5, message_item)
        # 结果列只显示 PASS/FAIL 状态
        if status in ['PASS', 'FAIL']:
            result_item.setText(status)
            result_item.setToolTip(f"{status}: {result_text}")
        else:
            result_item.setText(result_text)
            result_item.setToolTip(result_text)
        message_item.setText(message_text)
        message_item.setToolTip(message_text)

    @Slot(dict)
    def on_test_finished(self, final_status_data):
        was_in_debug_mode = self.is_in_debug_mode
        self.timer.stop()
        content = final_status_data['content']
        status = content.get('status', 'FAIL').upper()
        if status == "USER_STOPPED" and was_in_debug_mode:
            status = 'DEBUG_STOP'
        if self.current_highlighted_row != -1:
            self._set_row_status(self.current_highlighted_row, None)
            self.current_highlighted_row = -1
        self.active_thread = None
        self.is_in_debug_mode = False
        self.update_button_states('idle')
        # 保存当前测试的SN用于状态显示
        last_sn = content.get('uut_sn', self.sn_entry.currentText().strip())
        self.update_status(status, content, sn=last_sn)
        self.sn_entry.setCurrentText('')
        if was_in_debug_mode:
            self._toggle_breakpoints_visibility(False)
        # 使用智能统计
        if status in ['PASS', 'FAIL']:
            db_record_id = content.get('db_record_id')  # 获取数据库记录ID
            show_repair_warning, repair_message, skip_db_record = self._update_smart_statistics(last_sn, status, db_record_id)
            
            # 如果是复测成功，删除本次测试创建的重复数据库记录
            if skip_db_record and db_record_id:
                from utils.database_logger import delete_test_record
                delete_test_record(db_record_id)
            
            self.update_stats_display()
            if show_repair_warning and repair_message:
                # 在状态标签显示维修提示
                self.status_label.setText(f"{repair_message} | 失败")
                self.status_label.setToolTip(repair_message)

        # 智能焦点管理
        # 统一逻辑：无论是通过还是失败，都自动跳转到下一个空闲工位，维持连续作业流。
        if status in ['PASS', 'FAIL']:
             QTimer.singleShot(100, lambda: self.app.advance_focus_to_next_station(self.id))
        # USER_STOPPED 等其他状态不自动跳转

        # 发射专用于循环测试的信号
        self.cycle_test_finished.emit(final_status_data)

        # 检查顶针使用情况
        self._check_thimble_usage(status)

    def _toggle_breakpoints_visibility(self, visible):
        for r in range(self.steps_view.rowCount()):
            if r in self.breakpoints:
                bp_item = self.steps_view.item(r, 0)
                if bp_item: bp_item.setText("●" if visible else "")

    def _on_breakpoint_click(self, row, column):
        if column != 0: return
        step_item = self.steps_view.item(row, 1)
        if not step_item or not step_item.text(): return
        original_index = row
        bp_item = self.steps_view.item(row, 0)
        if original_index in self.breakpoints:
            self.breakpoints.remove(original_index);
            bp_item.setText("")
        else:
            self.breakpoints.add(original_index);
            bp_item.setText("●");
            bp_item.setForeground(QColor("red"))
        if self.active_thread: self.active_thread.update_breakpoints(self.breakpoints.copy())

    def reset_ui_for_new_run(self, preserve_breakpoints=False, show_breakpoints=True):
        self.user_stopped_in_debug = False
        self.log_area.clear()
        self.progress_bar.setValue(0)
        self.test_time_label.setText("时间: 0.00s")
        self.current_highlighted_row = -1
        self.load_sequence_to_view(self.app.sequence_data, preserve_breakpoints, show_breakpoints)

    def on_start_test_normal_click(self):
        current_sn = self.sn_entry.currentText().strip()
        if not current_sn:
            # 在状态标签显示空SN提示，避免弹框
            self.status_label.setText("⚠ 产品SN不能为空")
            font_size = self.font().pointSize()
            if font_size <= 0: font_size = 9
            new_size = font_size + 12
            self.status_label.setStyleSheet(
                f"font-size: {new_size}pt; font-weight: bold; padding: 5px; border-radius: 3px; background-color: #f39c12; color: white;")
            return
        if not self.app.sequence_data or not self.app.current_sequence_file_path:
            QMessageBox.warning(self, "提示", "请先打开一个测试程序。")
            return

        # SN重复检查（仅启用时生效，仅限正常测试，且只对唯一SN生效）
        sn_check_config = self.app.global_config.get('sn_duplicate_check', {})
        if sn_check_config.get('enabled', False):
            # 简单SN不进行重复检查
            if not self._is_simple_sn(current_sn):
                # 获取sequence_name并去掉.json后缀（与数据库存储格式保持一致）
                sequence_name = None
                if self.app.current_sequence_file_path:
                    sequence_name = os.path.basename(self.app.current_sequence_file_path)
                    if sequence_name.endswith('.json'):
                        sequence_name = sequence_name[:-5]  # 去掉 ".json"
                if check_sn_exists(current_sn, sequence_name):
                    self.sn_entry.setCurrentText('')
                    # 在状态标签显示重复提示，避免弹框
                    self.status_label.setText("⚠ SN已重复")
                    # 使用与update_status一致的字体大小
                    font_size = self.font().pointSize()
                    if font_size <= 0: font_size = 9
                    new_size = font_size + 12
                    self.status_label.setStyleSheet(
                        f"font-size: {new_size}pt; font-weight: bold; padding: 5px; border-radius: 3px; background-color: #f39c12; color: white;")
                    return

        # 正常点击开始，肯定不是循环测试
        self._is_running_cycle_test = False
        self._start_test_flow(is_debugging=False)

    def start_cycle_test(self, sn, report_output_dir=None):
        """
        专用于循环测试的启动方法。
        """
        self._is_running_cycle_test = True  # 标记为循环测试
        self.sn_entry.setCurrentText(sn)
        self._start_test_flow(is_debugging=False, report_output_dir=report_output_dir)

    def eventFilter(self, watched, event):
        # 恢复到“上一个版本”的方案：通过动态更改对象名称来触发全局ID样式
        if watched == self.sn_entry:
            if event.type() == QEvent.FocusIn:
                self.sn_entry.lineEdit().setObjectName("active_sn_input")
                self.sn_entry.style().unpolish(self.sn_entry)
                self.sn_entry.style().polish(self.sn_entry)
            elif event.type() == QEvent.FocusOut:
                self.sn_entry.lineEdit().setObjectName("")
                self.sn_entry.style().unpolish(self.sn_entry)
                self.sn_entry.style().polish(self.sn_entry)

        # 保留原有的双击和回车事件处理
        if watched == self.sn_entry.lineEdit():
            if event.type() == QEvent.MouseButtonDblClick:
                QTimer.singleShot(0, self.sn_entry.showPopup)
                return True
            if event.type() == QEvent.KeyPress and event.key() == Qt.Key_Return:
                self.on_start_test_normal_click()
                return True

        return super().eventFilter(watched, event)

    @Slot(bool)
    def toggle_log_visibility(self, checked):
        self.splitter.widget(1).setVisible(checked)

    @Slot(str)
    def _add_sn_to_history(self, sn):
        if sn in self.sn_history: self.sn_history.remove(sn)
        self.sn_history.appendleft(sn)
        self.sn_entry.blockSignals(True)
        self.sn_entry.clear()
        self.sn_entry.addItems(self.sn_history)
        self.sn_entry.setCurrentText(self.sn_entry.itemText(0))
        self.sn_entry.blockSignals(False)

    def update_status(self, status_key, message="", sn=""):
        text, color = STATUS_STYLES.get(status_key.upper(), ('未知', '#6c757d'))
        full_text = text
        # PASS状态显示SN
        if status_key.upper() == 'PASS' and sn:
            full_text = f"通过 | SN: {sn}"
        elif status_key.upper() == 'FAIL' and isinstance(message, dict) and 'fail_details' in message.get('message',
                                                                                                          {}):
            details = message['message']['fail_details']
            step_index = details.get('step_index', -1)
            ui_step_number = ""
            test_name = ""
            if 0 <= step_index < self.steps_view.rowCount():
                step_num_item = self.steps_view.item(step_index, 1)
                if step_num_item: ui_step_number = step_num_item.text()
                # 获取测试名称
                name_item = self.steps_view.item(step_index, 2)
                if name_item: test_name = name_item.text()
            result_val = details.get('result', '')
            # 在失败信息中显示测试名称，并提示用户查看步骤详情
            if test_name:
                full_text = f"失败: {test_name} (步骤 {ui_step_number})，具体内容请参考对应步骤的信息"
            else:
                full_text = f"失败: 步骤 {ui_step_number}，具体内容请参考对应步骤的信息"
        elif isinstance(message, dict) and isinstance(message.get('message'), str):
            msg_str = message.get('message')
            full_text = f"{text}: {msg_str}" if msg_str and msg_str != text else text
        elif isinstance(message, str):
            full_text = f"{text}: {message}" if message else text
        
        elif status_key.upper() == 'USER_STOPPED':
             if isinstance(message, dict) and 'fail_details' in message.get('message', {}):
                details = message['message']['fail_details']
                step_index = details.get('step_index', -1)
                ui_step_number = ""
                test_name = ""
                if 0 <= step_index < self.steps_view.rowCount():
                    step_num_item = self.steps_view.item(step_index, 1)
                    if step_num_item: ui_step_number = step_num_item.text()
                    # 获取测试名称
                    name_item = self.steps_view.item(step_index, 2)
                    if name_item: test_name = name_item.text()
                
                if test_name:
                    full_text = f"测试中止: {test_name} (步骤 {ui_step_number})"
                else:
                    full_text = f"测试中止: 步骤 {ui_step_number}"
             else:
                 full_text = f"测试中止"
             
             # 设置特定颜色给中止状态 (橙色)
             color = "#e67e22"
        fm = QFontMetrics(self.status_label.font())
        elided_text = fm.elidedText(full_text, Qt.ElideRight, self.status_label.width())
        self.status_label.setText(elided_text)
        self.status_label.setToolTip(full_text)

        # 保持大字体
        font_size = self.font().pointSize()
        if font_size <= 0: font_size = 9
        new_size = font_size + 12

        self.status_label.setStyleSheet(
            f"background-color: {color}; color: white; font-size: {new_size}pt; font-weight: bold; padding: 5px; border-radius: 3px;"
        )

    @Slot()
    def update_test_time(self):
        if hasattr(self, 'test_start_time'): self.test_time_label.setText(
            f"时间: {time.time() - self.test_start_time:.2f}s")

    def update_stats_display(self):
        self.pass_label.setText(f"通过: {self.pass_count}")
        self.pass_label.setStyleSheet("color: #2ecc71; font-weight: bold;") # Green
        self.fail_label.setText(f"失败: {self.fail_count}")
        self.fail_label.setStyleSheet("color: #e74c3c; font-weight: bold;") # Red
        self.total_label.setText(f"总数: {self.total_count}")
        pass_rate = (self.pass_count / self.total_count * 100) if self.total_count > 0 else 0.0;
        self.rate_label.setText(f"合格率: {pass_rate:.2f}%")

    def reset_stats_manual(self):
        reply = QMessageBox.question(self, '确认', '确定要手动重置此工位的统计数据吗？',
                                     QMessageBox.Ok | QMessageBox.Cancel)
        if reply == QMessageBox.Ok:
            self.pass_count = 0
            self.fail_count = 0
            self.total_count = 0
            # 清空SN追踪历史
            self.sn_test_history.clear()
            self.counted_sns.clear()
            # 重置连续失败追踪
            self.consecutive_fail_count = 0
            self.last_tested_sn = None
            self.update_stats_display()

    def _is_simple_sn(self, sn):
        """判断是否为简单SN（如 1, 2, test 等，用于没有唯一SN的产品）"""
        # 简单SN：长度<=3 或 纯数字且<=999
        if len(sn) <= 3:
            return True
        if sn.isdigit() and int(sn) <= 999:
            return True
        return False

    def _update_smart_statistics(self, sn, status, db_record_id=None):
        """智能统计: 区分唯一SN和简单SN，支持跨工位追踪
        
        Args:
            sn: 产品序列号
            status: 测试状态 'PASS' 或 'FAIL'
            db_record_id: 数据库记录ID（由test_engine传入）
        
        返回: (show_warning, warning_message, skip_db_record)
               skip_db_record: True表示复测成功，应删除新创建的数据库记录
        """
        current_time = time.time()
        is_simple = self._is_simple_sn(sn)
        
        # === 全局连续失败检测逻辑 ===
        # 规则：同一个SN连续失败3次提醒，中途测试其他SN则重置计数
        show_consecutive_fail_warning = False
        
        if self.last_tested_sn is not None and self.last_tested_sn != sn:
            # SN改变了，重置连续失败计数
            self.consecutive_fail_count = 0
        
        if status == 'PASS':
            # 测试通过，重置连续失败计数
            self.consecutive_fail_count = 0
        elif status == 'FAIL':
            # 测试失败，增加连续失败计数
            self.consecutive_fail_count += 1
            if self.consecutive_fail_count >= 3:
                show_consecutive_fail_warning = True
                # 触发后重置，避免持续报警
                self.consecutive_fail_count = 0
        
        # 更新最后测试的SN
        self.last_tested_sn = sn
        
        # 使用全局SN追踪（跨工位共享）
        global_history = self.app.global_sn_test_history
        global_counted = self.app.global_counted_sns
        
        # 获取当前序列名称用于数据库查询
        sequence_name = None
        if self.app.current_sequence_file_path:
            sequence_name = os.path.basename(self.app.current_sequence_file_path)
            if sequence_name.endswith('.json'):
                sequence_name = sequence_name[:-5]
        
        if is_simple:
            # === 简单SN场景：支持复测逻辑（本工位内） ===
            if sn in self.sn_test_history:
                history = self.sn_test_history[sn]
                time_diff = current_time - history['time']
                
                if history['status'] == 'FAIL' and status == 'PASS' and time_diff <= 60:
                    # 1分钟内复测通过：取消fail，计入pass，total不变
                    self.fail_count -= 1
                    self.pass_count += 1
                    
                    # 更新数据库原记录为PASS
                    if history.get('db_record_id'):
                        update_test_result_to_pass(history['db_record_id'])
                    
                    del self.sn_test_history[sn]
                    # 返回skip_db_record=True，通知删除本次测试创建的重复记录
                    return show_consecutive_fail_warning, "已连续测试失败3次，请维修产品" if show_consecutive_fail_warning else None, True
            
            # 首次测试此简单SN 或者非复测通过情况
            if sn not in self.sn_test_history or status != 'PASS':
                if sn not in self.sn_test_history:
                    self.total_count += 1
                    if status == 'PASS':
                        self.pass_count += 1
                    else:
                        self.fail_count += 1
                        self.sn_test_history[sn] = {
                            'status': 'FAIL', 
                            'time': current_time, 
                            'retry_count': 0,
                            'db_record_id': db_record_id
                        }
                else:
                    # 已有记录的简单SN，更新失败时间戳和数据库ID
                    if status == 'FAIL':
                        self.sn_test_history[sn]['time'] = current_time
                        self.sn_test_history[sn]['db_record_id'] = db_record_id
        else:
            # === 唯一SN场景：支持1分钟内跨工位复测通过取消fail ===
            
            # 检查全局历史（跨工位）
            if sn in global_history:
                history = global_history[sn]
                time_diff = current_time - history['time']
                
                if history['status'] == 'FAIL' and status == 'PASS' and time_diff <= 60:
                    # 1分钟内复测通过（可能是跨工位）
                    original_station_id = history.get('station_id')
                    
                    # 【修改】原工位：取消fail和total计数
                    if original_station_id and original_station_id in self.app.station_frames:
                        original_frame = self.app.station_frames[original_station_id]
                        original_frame.fail_count -= 1
                        original_frame.total_count -= 1  # 也取消total
                        original_frame.update_stats_display()
                    
                    # 【修改】当前工位：计入pass和total
                    self.total_count += 1
                    self.pass_count += 1
                    
                    # 更新数据库原记录为PASS，并更新工位为当前工位
                    if history.get('db_record_id'):
                        update_test_result_to_pass(history['db_record_id'], self.id)
                    
                    del global_history[sn]
                    # 返回skip_db_record=True，通知删除本次测试创建的重复记录
                    return show_consecutive_fail_warning, "已连续测试失败3次，请维修产品" if show_consecutive_fail_warning else None, True
            
            # 唯一SN：跨工位只计数一次
            if sn in global_counted:
                # 已在其他工位计过数，不再重复计数
                # 但如果是FAIL，需要记录到全局历史以便后续复测判断
                if status == 'FAIL':
                    global_history[sn] = {
                        'status': 'FAIL',
                        'time': current_time,
                        'station_id': self.id,
                        'db_record_id': db_record_id
                    }
                return show_consecutive_fail_warning, "已连续测试失败3次，请维修产品" if show_consecutive_fail_warning else None, False
            
            global_counted.add(sn)
            self.total_count += 1
            if status == 'PASS':
                self.pass_count += 1
            else:
                self.fail_count += 1
                # 记录失败信息到全局历史，用于跨工位1分钟内复测通过判断
                global_history[sn] = {
                    'status': 'FAIL',
                    'time': current_time,
                    'station_id': self.id,
                    'db_record_id': db_record_id
                }
        
        return show_consecutive_fail_warning, "已连续测试失败3次，请维修产品" if show_consecutive_fail_warning else None, False

    @Slot(tuple)
    def update_log(self, log_content):
        msg, level = log_content
        color = LOG_LEVEL_COLORS.get(level.upper(), "#FFFFFF");
        self.log_area.append(f'<span style="color:{color};">{msg}</span>')

    def _check_thimble_usage(self, test_status):
        """Helper method to check and act on thimble usage."""
        # 仅在测试结束（非用户中止）时才计数
        # 【新增】如果是循环测试，则不计入顶针使用次数
        if not self.app.current_sequence_file_path or test_status in ['USER_STOPPED', 'DEBUG_STOP']:
            return

        if self._is_running_cycle_test:
            return

        # 顶针追踪（检查是否启用）
        thimble_enabled = self.app.global_config.get('thimble_tracking', {}).get('enabled', True)
        if thimble_enabled:
            try:
                duration = time.time() - self.test_start_time
                seq_path = self.app.current_sequence_file_path

                # 使用主应用的 thimble_manager 实例
                manager = self.app.thimble_manager
                # 【修改】传入 station_id
                manager.increment_usage(seq_path, duration, self.id)

                # 检查是否需要提醒
                # 【修改】传入 station_id
                needed, message = manager.check_reminder(seq_path, self.id)

                if needed:
                    # 使用QTimer.singleShot确保弹窗不会阻塞当前完成流程
                    QTimer.singleShot(0, lambda: self.show_thimble_reminder_dialog(self.app.current_sequence_file_path,
                                                                                   message))
            except Exception as e:
                print(f"检查顶针使用情况时发生错误: {e}")

        # 线缆计数（检查是否启用）
        cable_enabled = self.app.global_config.get('cable_tracking', {}).get('enabled', True)
        if cable_enabled:
            try:
                from consumable_manager import get_consumable_manager
                consumable_mgr = get_consumable_manager()
                consumable_mgr.on_test_complete(self.id)
            except Exception as e:
                print(f"线缆计数时发生错误: {e}")

    def show_thimble_reminder_dialog(self, seq_path, message):
        """显示顶针使用提醒对话框。"""
        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("顶针使用提醒")
        msg_box.setIcon(QMessageBox.Warning)
        msg_box.setText(message)

        snooze_7_days_btn = msg_box.addButton("一周后提醒", QMessageBox.AcceptRole)
        snooze_1_day_btn = msg_box.addButton("一天后提醒", QMessageBox.AcceptRole)
        ok_btn = msg_box.addButton("好的", QMessageBox.RejectRole)

        msg_box.exec()

        clicked_button = msg_box.clickedButton()
        manager = self.app.thimble_manager

        if clicked_button == snooze_7_days_btn:
            manager.set_snooze(seq_path, 7, self.id)
        elif clicked_button == snooze_1_day_btn:
            manager.set_snooze(seq_path, 1, self.id)