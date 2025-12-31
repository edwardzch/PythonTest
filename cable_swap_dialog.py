# -*- coding: utf-8 -*-
"""
线缆更换对话框
用于测试中途更换损坏的线缆
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QComboBox, QGroupBox, QFormLayout, QMessageBox
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from consumable_manager import get_consumable_manager


class CableSwapDialog(QDialog):
    """
    线缆更换对话框
    用于测试中途更换损坏的线缆
    """
    
    def __init__(self, parent, station_ids):
        """
        :param parent: 父窗口
        :param station_ids: 工位ID列表
        """
        super().__init__(parent)
        self.station_ids = station_ids
        self.manager = get_consumable_manager()
        
        self._init_ui()
        self.setWindowTitle("更换线缆")
        self.setMinimumWidth(400)
        
    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        
        # 标题
        title = QLabel("更换损坏的线缆")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #2c3e50;")
        main_layout.addWidget(title)
        
        # 表单区域
        form_group = QGroupBox("更换信息")
        form_layout = QFormLayout(form_group)
        
        # 工位选择
        self.station_combo = QComboBox()
        for sid in self.station_ids:
            self.station_combo.addItem(sid.replace("_", " "), sid)
        self.station_combo.currentIndexChanged.connect(self._on_station_changed)
        form_layout.addRow("选择工位:", self.station_combo)
        
        # 当前线缆
        self.current_sn_label = QLabel("-")
        self.current_sn_label.setStyleSheet("font-weight: bold; color: #3498db;")
        form_layout.addRow("当前线缆:", self.current_sn_label)
        
        # 新线缆SN
        self.new_sn_input = QLineEdit()
        self.new_sn_input.setPlaceholderText("扫描或输入新线缆SN")
        self.new_sn_input.returnPressed.connect(self._on_confirm)
        form_layout.addRow("新线缆SN:", self.new_sn_input)
        
        # 状态显示
        self.status_label = QLabel("")
        form_layout.addRow("", self.status_label)
        
        main_layout.addWidget(form_group)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        confirm_btn = QPushButton("确认更换")
        confirm_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 8px 20px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #1e8449; }
        """)
        confirm_btn.clicked.connect(self._on_confirm)
        btn_layout.addWidget(confirm_btn)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #95a5a6;
                color: white;
                padding: 8px 20px;
                border: none;
                border-radius: 4px;
            }
            QPushButton:hover { background-color: #7f8c8d; }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        main_layout.addLayout(btn_layout)
        
        # 初始化显示
        self._on_station_changed()
    
    def _on_station_changed(self):
        """工位选择变化时更新当前线缆显示"""
        station_id = self.station_combo.currentData()
        current_sn = self.manager.get_cable_for_station(station_id)
        
        if current_sn:
            info = self.manager.get_cable_info(current_sn)
            usage = info.get('total_count', 0) if info else 0
            limit = info.get('max_limit', 10000) if info else 10000
            self.current_sn_label.setText(f"{current_sn} ({usage}/{limit})")
        else:
            self.current_sn_label.setText("未绑定")
        
        self.new_sn_input.clear()
        self.status_label.clear()
    
    def _on_confirm(self):
        """确认更换"""
        station_id = self.station_combo.currentData()
        new_sn = self.new_sn_input.text().strip()
        
        if not new_sn:
            self.status_label.setText("请输入新线缆SN")
            self.status_label.setStyleSheet("color: #e74c3c;")
            return
        
        # 获取旧线缆信息
        old_sn = self.manager.get_cable_for_station(station_id)
        
        # 尝试绑定新线缆
        success, msg = self.manager.bind_cable_to_station(station_id, new_sn)
        
        if success:
            info = self.manager.get_cable_info(new_sn)
            usage = info.get('total_count', 0) if info else 0
            limit = info.get('max_limit', 10000) if info else 10000
            
            QMessageBox.information(
                self, "更换成功",
                f"工位 {station_id} 线缆已更换\n"
                f"旧: {old_sn or '无'}\n"
                f"新: {new_sn} (寿命: {usage}/{limit})"
            )
            self.accept()
        else:
            self.status_label.setText(f"✗ {msg}")
            self.status_label.setStyleSheet("color: #e74c3c;")
            self.new_sn_input.selectAll()
            self.new_sn_input.setFocus()
