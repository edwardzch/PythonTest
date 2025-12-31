import os
import json
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QLabel, QSpinBox,
    QPushButton, QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QWidget, QAbstractItemView, QInputDialog, QLineEdit, QCheckBox
)
from PySide6.QtCore import Qt, Slot, QTimer
from PySide6.QtGui import QColor
from thimble_manager import ThimbleManager
from consumable_manager import get_consumable_manager
from utils.app_utils import get_app_base_path

class ThimbleTrackerDialog(QDialog):
    def __init__(self, thimble_manager: ThimbleManager, parent=None):
        super().__init__(parent)
        self.thimble_manager = thimble_manager
        self.parent_app = parent
        self.station_ids = []
        
        # 获取工位列表
        if hasattr(parent, 'global_config'):
            self.station_ids = sorted(parent.global_config.get('stations', {}).keys())
        else:
            self.station_ids = ["Station_1", "Station_2", "Station_3", "Station_4"]
        
        # 确定"工位1"的ID（用于复制配置）
        self.station_1_id = self.station_ids[0] if self.station_ids else "Station_1"

        self.setWindowTitle("顶针治具管理")
        self.resize(1200, 700)
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinMaxButtonsHint)

        self.sequence_files = self.thimble_manager.get_all_sequence_files()

        self._init_ui()
        self.load_station_data()

    def _init_ui(self):
        layout = QVBoxLayout(self)

        # 1. 顶部栏：工位选择 + 启用开关
        top_layout = QHBoxLayout()
        
        # 启用追踪开关
        self.enable_checkbox = QCheckBox("启用顶针追踪")
        self.enable_checkbox.setChecked(self._get_enabled_from_config())
        self.enable_checkbox.stateChanged.connect(self._on_enable_changed)
        top_layout.addWidget(self.enable_checkbox)
        
        top_layout.addSpacing(30)
        
        top_layout.addWidget(QLabel("当前工位:"))
        self.station_combo = QComboBox()
        self.station_combo.addItems(self.station_ids)
        self.station_combo.setMinimumWidth(200)
        self.station_combo.setSizeAdjustPolicy(QComboBox.AdjustToContents)
        self.station_combo.currentTextChanged.connect(self.load_station_data)
        top_layout.addWidget(self.station_combo)
        top_layout.addStretch()
        layout.addLayout(top_layout)

        # 2. 表格区域
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "序号", "治具编码", "使用总数", "使用上限", "预警天数", 
            "对应测试程序", "单序列使用次数"
        ])
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(0, QHeaderView.ResizeToContents)  # 序号
        header.setSectionResizeMode(5, QHeaderView.Stretch)  # 序列名称 - main stretch
        
        # 治具编码 - 固定宽度，缩小
        header.setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 400)
        
        # 使用总数、使用上限、预警天数、单序列使用次数 - 较大固定宽度
        for col_idx in [2, 3, 4, 6]:
            header.setSectionResizeMode(col_idx, QHeaderView.Fixed)
            self.table.setColumnWidth(col_idx, 130)
            
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        layout.addWidget(self.table)
        
        # 3. 操作按钮
        action_layout = QHBoxLayout()
        self.add_fixture_btn = QPushButton("添加治具 (+)")
        self.add_fixture_btn.clicked.connect(self.add_fixture)
        self.remove_fixture_btn = QPushButton("删除治具 (-)")
        self.remove_fixture_btn.clicked.connect(self.remove_selected_fixture)
        self.add_seq_btn = QPushButton("为选中治具添加序列")
        self.add_seq_btn.clicked.connect(self.add_sequence_to_fixture)
        self.remove_seq_btn = QPushButton("移除选中序列")
        self.remove_seq_btn.clicked.connect(self.remove_selected_sequence)
        self.reset_btn = QPushButton("重置选中治具计数")
        self.reset_btn.clicked.connect(self.reset_selected_fixture)
        
        action_layout.addWidget(self.add_fixture_btn)
        action_layout.addWidget(self.remove_fixture_btn)
        action_layout.addWidget(self.add_seq_btn)
        action_layout.addWidget(self.remove_seq_btn)
        action_layout.addWidget(self.reset_btn)
        action_layout.addStretch()
        layout.addLayout(action_layout)
        
        layout.addWidget(QLabel("提示: 治具相关属性会自动保存。一个治具可以关联多个测试程序。"))

        # 4. 底部按钮
        btn_layout = QHBoxLayout()
        self.copy_btn = QPushButton("从工位1复制配置")
        self.copy_btn.clicked.connect(self.copy_from_station_1)
        
        self.history_btn = QPushButton("📋 历史记录")
        self.history_btn.clicked.connect(self.open_pogo_history)
        
        self.close_btn = QPushButton("关闭")
        self.close_btn.clicked.connect(self.accept)
        
        btn_layout.addWidget(self.copy_btn)
        btn_layout.addWidget(self.history_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.close_btn)
        layout.addLayout(btn_layout)

    def load_station_data(self):
        station_id = self.station_combo.currentText()
        if not station_id: return
        
        self.table.clearSpans()  # Clear old spans
        self.table.setRowCount(0)
        
        fixtures = self.thimble_manager.get_fixtures(station_id)
        
        fixture_index = 0
        for fix_code, fix_info in fixtures.items():
            fixture_index += 1
            sequences = fix_info.get("sequences", {})
            row_count_for_fixture = max(len(sequences), 1)  # At least one row for a fixture
            
            start_row = self.table.rowCount()
            
            for seq_idx, (seq_name, seq_count) in enumerate(sequences.items() if sequences else [("", 0)]):
                row = self.table.rowCount()
                self.table.insertRow(row)
                
                if seq_idx == 0:
                    # First row of fixture - add fixture-level data
                    # 序号
                    item_index = QTableWidgetItem(str(fixture_index))
                    item_index.setTextAlignment(Qt.AlignCenter)
                    item_index.setFlags(item_index.flags() ^ Qt.ItemIsEditable)
                    self.table.setItem(row, 0, item_index)
                    
                    # 治具编码
                    item_code = QTableWidgetItem(fix_code)
                    item_code.setData(Qt.UserRole, fix_code)  # Store original code
                    self.table.setItem(row, 1, item_code)
                    
                    # 使用总数
                    item_total = QTableWidgetItem(str(fix_info.get("total_usage", 0)))
                    item_total.setTextAlignment(Qt.AlignCenter)
                    item_total.setFlags(item_total.flags() ^ Qt.ItemIsEditable)
                    item_total.setBackground(QColor("#555555"))
                    self.table.setItem(row, 2, item_total)
                    
                    # 使用上限 (SpinBox)
                    sb_limit = QSpinBox()
                    sb_limit.setRange(0, 9999999)
                    sb_limit.setValue(fix_info.get("limit", 0))
                    sb_limit.editingFinished.connect(lambda fc=fix_code, sb=sb_limit: self._on_limit_changed(fc, sb))
                    self.table.setCellWidget(row, 3, sb_limit)
                    
                    # 预警天数 (SpinBox)
                    sb_days = QSpinBox()
                    sb_days.setRange(0, 3650)
                    sb_days.setValue(fix_info.get("warning_days", 0))
                    sb_days.editingFinished.connect(lambda fc=fix_code, sb=sb_days: self._on_days_changed(fc, sb))
                    self.table.setCellWidget(row, 4, sb_days)
                else:
                    # Subsequent rows for merged cells - leave empty (will be spanned)
                    for col in range(5):
                        item = QTableWidgetItem("")
                        item.setFlags(item.flags() ^ Qt.ItemIsEditable ^ Qt.ItemIsSelectable)
                        self.table.setItem(row, col, item)
                
                # 对应序列
                item_seq = QTableWidgetItem(seq_name if seq_name else "(无关联序列)")
                item_seq.setData(Qt.UserRole, fix_code)  # Store parent fixture
                item_seq.setData(Qt.UserRole + 1, seq_name)  # Store sequence name
                self.table.setItem(row, 5, item_seq)
                
                # 单序列使用次数
                item_seq_count = QTableWidgetItem(str(seq_count) if seq_name else "-")
                item_seq_count.setTextAlignment(Qt.AlignCenter)
                item_seq_count.setFlags(item_seq_count.flags() ^ Qt.ItemIsEditable)
                self.table.setItem(row, 6, item_seq_count)
            
            # Apply row spans for fixture-level columns if multiple sequences
            if row_count_for_fixture > 1:
                for col in range(5):  # Columns 0-4 are fixture-level
                    self.table.setSpan(start_row, col, row_count_for_fixture, 1)

        # 确保合并单元格后行高正确
        self.table.resizeRowsToContents()
        
        # 更新复制按钮状态 - 当选中第一个工位时禁用
        self.copy_btn.setEnabled(station_id != self.station_1_id)

    def _on_limit_changed(self, fix_code, spinbox):
        station_id = self.station_combo.currentText()
        fixtures = self.thimble_manager.get_fixtures(station_id)
        if fix_code in fixtures:
            current_days = fixtures[fix_code].get("warning_days", 0)
            self.thimble_manager.update_fixture(station_id, fix_code, spinbox.value(), current_days)

    def _on_days_changed(self, fix_code, spinbox):
        station_id = self.station_combo.currentText()
        fixtures = self.thimble_manager.get_fixtures(station_id)
        if fix_code in fixtures:
            current_limit = fixtures[fix_code].get("limit", 0)
            self.thimble_manager.update_fixture(station_id, fix_code, current_limit, spinbox.value())

    @Slot()
    def add_fixture(self):
        code, ok = QInputDialog.getText(self, "添加治具", "请输入新治具编码:", QLineEdit.Normal)
        if ok and code.strip():
            station_id = self.station_combo.currentText()
            self.thimble_manager.add_fixture(station_id, code.strip())
            self.load_station_data()

    @Slot()
    def remove_selected_fixture(self):
        selected_rows = set(index.row() for index in self.table.selectedIndexes())
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要删除的治具。")
            return
        
        # Get unique fixture codes from selected rows
        fixture_codes = set()
        for row in selected_rows:
            item = self.table.item(row, 1)  # 治具编码 column
            if item and item.data(Qt.UserRole):
                fixture_codes.add(item.data(Qt.UserRole))
            # Also check column 5 which stores the parent fixture code
            item_seq = self.table.item(row, 5)
            if item_seq and item_seq.data(Qt.UserRole):
                fixture_codes.add(item_seq.data(Qt.UserRole))
        
        if not fixture_codes:
            return
            
        reply = QMessageBox.question(
            self, "确认删除", 
            f"确定要删除以下治具吗？\n{', '.join(fixture_codes)}\n\n此操作将删除治具及其所有关联的序列记录。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            station_id = self.station_combo.currentText()
            for code in fixture_codes:
                self.thimble_manager.remove_fixture(station_id, code)
            self.load_station_data()

    @Slot()
    def add_sequence_to_fixture(self):
        # Find the selected fixture
        selected_rows = set(index.row() for index in self.table.selectedIndexes())
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择一个治具。")
            return
        
        fix_code = None
        for row in selected_rows:
            item = self.table.item(row, 1)
            if item and item.data(Qt.UserRole):
                fix_code = item.data(Qt.UserRole)
                break
            item_seq = self.table.item(row, 5)
            if item_seq and item_seq.data(Qt.UserRole):
                fix_code = item_seq.data(Qt.UserRole)
                break
        
        if not fix_code:
            QMessageBox.warning(self, "提示", "无法确定所选行的治具。")
            return
        
        # Show sequence selection dialog
        seq_name, ok = QInputDialog.getItem(
            self, "添加序列", 
            f"为治具 '{fix_code}' 选择要关联的测试程序:",
            [""] + self.sequence_files, 0, False
        )
        if ok and seq_name:
            station_id = self.station_combo.currentText()
            self.thimble_manager.associate_sequence(
                os.path.join(get_app_base_path(), 'sequences', seq_name),
                fix_code,
                station_id
            )
            self.load_station_data()

    @Slot()
    def remove_selected_sequence(self):
        selected_rows = set(index.row() for index in self.table.selectedIndexes())
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要移除的序列。")
            return
        
        to_remove = []  # List of (fix_code, seq_name)
        for row in selected_rows:
            item_seq = self.table.item(row, 5)
            if item_seq:
                fix_code = item_seq.data(Qt.UserRole)
                seq_name = item_seq.data(Qt.UserRole + 1)
                if fix_code and seq_name:
                    to_remove.append((fix_code, seq_name))
        
        if not to_remove:
            QMessageBox.warning(self, "提示", "所选行没有可移除的序列。")
            return
        
        reply = QMessageBox.question(
            self, "确认移除", 
            f"确定要移除 {len(to_remove)} 个序列关联吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            station_id = self.station_combo.currentText()
            for fix_code, seq_name in to_remove:
                self.thimble_manager.remove_sequence_from_fixture(station_id, fix_code, seq_name)
            self.load_station_data()

    @Slot()
    def reset_selected_fixture(self):
        selected_rows = set(index.row() for index in self.table.selectedIndexes())
        if not selected_rows:
            QMessageBox.warning(self, "提示", "请先选择要重置的治具。")
            return
        
        fixture_codes = set()
        for row in selected_rows:
            item = self.table.item(row, 1)
            if item and item.data(Qt.UserRole):
                fixture_codes.add(item.data(Qt.UserRole))
            item_seq = self.table.item(row, 5)
            if item_seq and item_seq.data(Qt.UserRole):
                fixture_codes.add(item_seq.data(Qt.UserRole))
        
        if not fixture_codes:
            return
            
        reply = QMessageBox.question(
            self, "确认重置", 
            f"确定要重置以下治具的所有计数吗？\n{', '.join(fixture_codes)}",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            station_id = self.station_combo.currentText()
            consumable_mgr = get_consumable_manager()
            
            for code in fixture_codes:
                # 获取重置前的使用次数和首次使用时间
                fixtures = self.thimble_manager.get_fixtures(station_id)
                if code in fixtures:
                    count_before = fixtures[code].get('total_usage', 0)
                    first_use = fixtures[code].get('first_use_timestamp', 0)
                    first_use_time = None
                    if first_use > 0:
                        from datetime import datetime
                        first_use_time = datetime.fromtimestamp(first_use).isoformat()
                    
                    # 记录到顶针历史
                    operator_id = None
                    if hasattr(self.parent(), 'user_info') and self.parent().user_info:
                        operator_id = self.parent().user_info.get('id')
                    
                    consumable_mgr.log_pogo_reset(
                        station_id=station_id,
                        fixture_code=code,
                        count_before=count_before,
                        first_use_time=first_use_time,
                        operator_id=operator_id,
                        notes="通过顶针管理界面手动重置"
                    )
                
                # 执行重置
                self.thimble_manager.reset_fixture_usage(station_id, code)
            
            self.load_station_data()
            QMessageBox.information(self, "成功", f"已重置 {len(fixture_codes)} 个治具并记录历史")

    @Slot()
    def copy_from_station_1(self):
        target_station = self.station_combo.currentText()
        if target_station == self.station_1_id: return
        
        reply = QMessageBox.question(
            self, "确认复制", 
            f"确定要从 {self.station_1_id} 覆盖当前工位的所有配置吗？\n当前工位的数据将丢失。",
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if self.thimble_manager.copy_station_data(self.station_1_id, target_station):
                self.load_station_data()
                QMessageBox.information(self, "成功", "复制完成。")
            else:
                QMessageBox.warning(self, "失败", "源工位没有数据。")

    @Slot()
    def open_pogo_history(self):
        """打开顶针历史记录报告"""
        import pogo_history_report
        success, result = pogo_history_report.generate_and_open_pogo_history()
        if not success:
            QMessageBox.warning(self, "错误", f"生成报告失败: {result}")
    
    def _get_enabled_from_config(self):
        """从配置文件读取启用状态"""
        if self.parent_app and hasattr(self.parent_app, 'global_config'):
            tracking_config = self.parent_app.global_config.get('thimble_tracking', {})
            return tracking_config.get('enabled', True)
        return True
    
    def _on_enable_changed(self, state):
        """保存启用状态到配置文件"""
        enabled = bool(state)  # state > 0 means checked
        if self.parent_app and hasattr(self.parent_app, 'global_config'):
            if 'thimble_tracking' not in self.parent_app.global_config:
                self.parent_app.global_config['thimble_tracking'] = {}
            self.parent_app.global_config['thimble_tracking']['enabled'] = enabled
            
            # 保存到文件
            try:
                config_path = os.path.join(get_app_base_path(), 'config.json')
                with open(config_path, 'w', encoding='utf-8') as f:
                    json.dump(self.parent_app.global_config, f, indent=4, ensure_ascii=False)
            except Exception as e:
                print(f"保存配置失败: {e}")

if __name__ == '__main__':
    from PySide6.QtWidgets import QApplication
    import sys
    app = QApplication(sys.argv)
    manager = ThimbleManager()
    dialog = ThimbleTrackerDialog(manager)
    dialog.exec()
    sys.exit(app.exec())
