# 文件路径: cycle_test_dialog.py (UnboundLocalError 终极修复版)
# -*- coding: utf-8 -*-

# --- 【【【核心修复1：将 import 移到文件顶部】】】 ---
import os
import sys
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, QLabel,
    QLineEdit, QCheckBox, QDialogButtonBox, QSpinBox, QFormLayout,
    QListWidget, QAbstractItemView, QPushButton, QMessageBox, QStackedLayout, QDoubleSpinBox
)
from PySide6.QtCore import Qt, Signal


class CycleTestControlDialog(QDialog):
    """
    一个总在最前端的小窗口，用于显示循环测试状态并提供控制。
    """
    abort_clicked = Signal()

    def __init__(self, station_ids, parent=None):
        super().__init__(parent)
        self.setWindowTitle("循环测试控制")
        self.setWindowFlags(Qt.WindowStaysOnTopHint | Qt.Dialog | Qt.WindowMinimizeButtonHint)
        self.setMinimumWidth(400)
        self.report_path = None
        self.station_ids = station_ids

        main_layout = QVBoxLayout(self)

        # 总体状态和运行时间 (始终显示)
        top_info_layout = QFormLayout()
        self.status_label = QLabel("正在准备开始循环测试...")
        self.running_time_label = QLabel("00:00:00")
        top_info_layout.addRow("当前状态:", self.status_label)
        top_info_layout.addRow("运行时间:", self.running_time_label)
        main_layout.addLayout(top_info_layout)

        # 各工位统计 (始终显示)
        stats_group = QGroupBox("各工位统计 (通过 / 失败)")
        stats_layout = QFormLayout(stats_group)
        self.station_stats_labels = {}
        for station_id in self.station_ids:
            station_num = station_id.split('_')[-1]
            stat_label = QLabel("<span style='color:#27ae60;'>0</span> / <span style='color:#c0392b;'>0</span>")
            self.station_stats_labels[station_id] = stat_label
            stats_layout.addRow(f"工位 {station_num}:", stat_label)
        main_layout.addWidget(stats_group)

        # --- 使用 QStackedLayout 管理动态UI状态 ---
        self.stacked_layout = QStackedLayout()

        # 状态0: 测试进行中 (只包含控制按钮)
        running_widget = QWidget()
        running_layout = QVBoxLayout(running_widget)
        running_buttons = QHBoxLayout()
        self.abort_button = QPushButton("中止测试")
        running_buttons.addStretch()
        running_buttons.addWidget(self.abort_button)
        running_buttons.addStretch()
        running_layout.addLayout(running_buttons)
        running_layout.setContentsMargins(0,0,0,0) # 移除内边距

        # 状态1: 测试已完成 (只包含完成消息和按钮)
        completed_widget = QWidget()
        completed_layout = QVBoxLayout(completed_widget)
        self.completion_message_label = QLabel("")
        self.completion_message_label.setAlignment(Qt.AlignCenter)
        completed_buttons = QHBoxLayout()
        self.report_button = QPushButton("打开文件夹")
        self.close_button = QPushButton("关闭")
        completed_buttons.addWidget(self.report_button)
        completed_buttons.addWidget(self.close_button)
        completed_layout.addWidget(self.completion_message_label)
        completed_layout.addLayout(completed_buttons)
        completed_layout.setContentsMargins(0,0,0,0) # 移除内边距

        self.stacked_layout.addWidget(running_widget)
        self.stacked_layout.addWidget(completed_widget)
        main_layout.addLayout(self.stacked_layout)

        # 连接信号
        self.abort_button.clicked.connect(self.abort_clicked)
        self.report_button.clicked.connect(self._on_report_button_clicked)
        self.close_button.clicked.connect(self.accept)

    def update_running_time(self, elapsed_seconds):
        """更新运行时间显示"""
        hours, remainder = divmod(int(elapsed_seconds), 3600)
        minutes, seconds = divmod(remainder, 60)
        self.running_time_label.setText(f"{hours:02}:{minutes:02}:{seconds:02}")

    def update_station_stats(self, station_id, passed_count, failed_count):
        """更新指定工位的通过/失败统计"""
        if station_id in self.station_stats_labels:
            rich_text = f"<span style='color:#27ae60;'>{passed_count}</span> / <span style='color:#c0392b;'>{failed_count}</span>"
            self.station_stats_labels[station_id].setText(rich_text)

    def update_status_text(self, text):
        self.status_label.setText(text)

    def _on_report_button_clicked(self):
        """处理打开报告文件夹按钮点击事件"""
        if self.report_path and os.path.exists(os.path.dirname(self.report_path)):
            try:
                report_dir = os.path.dirname(os.path.abspath(self.report_path))
                os.startfile(report_dir)
            except Exception as e:
                QMessageBox.critical(self, "无法打开", f"无法自动打开文件夹: {e}")
        else:
            QMessageBox.warning(self, "提示", "报告路径无效或文件夹不存在。")

    def show_completion_state(self, title, message, report_path=None):
        """
        将对话框切换到完成状态，显示最终消息和报告按钮。
        """
        self.setWindowTitle(title)
        self.report_path = report_path
        self.completion_message_label.setText(message)
        self.report_button.setVisible(bool(report_path))
        self.stacked_layout.setCurrentIndex(1)

    def closeEvent(self, event):
        if self.stacked_layout.currentIndex() == 1:
            event.accept()
        else:
            event.ignore()
            QMessageBox.information(self, "提示", '请使用"中止测试"按钮来结束循环测试。')


# =========================================================================
#  CycleTestDialog (设置窗口) 的代码你写的很完美，保持不变
# =========================================================================
class CycleTestDialog(QDialog):
    start_requested = Signal(dict)

    def __init__(self, parent=None, station_ids=None, sequence_data=None):
        super().__init__(parent)
        self.setWindowTitle("循环压力测试设置")
        self.setMinimumSize(450, 400)

        self.station_ids = station_ids if station_ids else []
        self.sequence_data = sequence_data if sequence_data else []

        main_layout = QVBoxLayout(self)
        params_group = QGroupBox("测试参数")
        form_layout = QFormLayout(params_group)
        form_layout.setRowWrapPolicy(QFormLayout.RowWrapPolicy.WrapAllRows)
        
        self.cycle_count_spinbox = QSpinBox()
        self.cycle_count_spinbox.setRange(1, 1000000)
        self.cycle_count_spinbox.setValue(10)
        form_layout.addRow("循环次数:", self.cycle_count_spinbox)
        
        self.stagger_delay_spinbox = QDoubleSpinBox()
        self.stagger_delay_spinbox.setRange(0, 60)
        self.stagger_delay_spinbox.setValue(1.0)
        self.stagger_delay_spinbox.setSuffix(" s")
        form_layout.addRow("工位启动延迟:", self.stagger_delay_spinbox)

        self.start_sn_edit = QLineEdit("SN:DL1L2511030001")
        form_layout.addRow("起始产品SN:", self.start_sn_edit)
        
        self.sn_increment_check = QCheckBox("SN自动递增")
        self.sn_increment_check.setChecked(True)
        form_layout.addRow(self.sn_increment_check)
        
        main_layout.addWidget(params_group)

        stations_group = QGroupBox("选择测试工位")
        stations_layout = QHBoxLayout(stations_group)
        self.station_checkboxes = {}
        if not self.station_ids:
            stations_layout.addWidget(QLabel("未找到可用工位"))
        else:
            for station_id in self.station_ids:
                station_num = station_id.split('_')[-1]
                checkbox = QCheckBox(f"工位 {station_num}")
                checkbox.setChecked(True)
                self.station_checkboxes[station_id] = checkbox
                stations_layout.addWidget(checkbox)
        main_layout.addWidget(stations_group)

        cpk_group = QGroupBox("CPK 分析 (可选，按住Ctrl可多选)")
        cpk_layout = QVBoxLayout(cpk_group)
        self.cpk_step_list = QListWidget()
        self.cpk_step_list.setSelectionMode(QAbstractItemView.ExtendedSelection)
        for step in self.sequence_data:
            test_name = step.get("TestName", "").strip()
            if test_name and not test_name.startswith(('*', '#')):
                self.cpk_step_list.addItem(test_name)
        cpk_layout.addWidget(self.cpk_step_list)
        main_layout.addWidget(cpk_group)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.button(QDialogButtonBox.Ok).setText("开始循环测试")
        self.button_box.button(QDialogButtonBox.Cancel).setText("取消")
        self.button_box.accepted.connect(self.on_start)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)

    def on_start(self):
        selected_stations = [
            station_id for station_id, checkbox in self.station_checkboxes.items()
            if checkbox.isChecked()
        ]
        if not selected_stations:
            QMessageBox.warning(self, "选择错误", "请至少选择一个测试工位。")
            return
        selected_cpk_items = self.cpk_step_list.selectedItems()
        cpk_steps = [item.text() for item in selected_cpk_items]
        config = {
            "cycle_count": self.cycle_count_spinbox.value(),
            "start_sn": self.start_sn_edit.text().strip(),
            "sn_increment": self.sn_increment_check.isChecked(),
            "selected_stations": selected_stations,
            "stagger_delay": self.stagger_delay_spinbox.value(),
            "cpk_steps": cpk_steps
        }
        self.accept()
        self.start_requested.emit(config)


if __name__ == '__main__':
    app = QApplication(sys.argv)
    mock_station_ids = [f"station_{i}" for i in range(1, 5)]
    dialog = CycleTestDialog(station_ids=mock_station_ids)
    dialog.show()
    sys.exit(app.exec())
