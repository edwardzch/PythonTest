# -*- coding: utf-8 -*-
"""
线缆扫码对话框
在加载序列后弹出，要求每个工位扫描线缆SN
"""
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, 
    QPushButton, QGroupBox, QGridLayout, QMessageBox
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from consumable_manager import get_consumable_manager


class CableScanDialog(QDialog):
    """
    线缆扫码对话框
    根据工位数量动态生成扫码输入框
    """
    
    def __init__(self, parent, station_ids):
        """
        :param parent: 父窗口
        :param station_ids: 需要扫码的工位ID列表, e.g. ['Station_1', 'Station_2']
        """
        super().__init__(parent)
        self.station_ids = station_ids
        self.manager = get_consumable_manager()
        self.scan_entries = {}  # station_id -> QLineEdit
        self.status_labels = {}  # station_id -> QLabel
        self.confirmed = {}  # station_id -> bool
        
        self._init_ui()
        self.setWindowTitle("线缆扫码确认")
        self.setModal(True)
        self.setMinimumWidth(500)
        
    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        
        # 标题
        title = QLabel("请为每个工位扫描线缆SN")
        title.setFont(QFont("Microsoft YaHei", 14, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet("color: #2c3e50; margin-bottom: 10px;")
        main_layout.addWidget(title)
        
        # 提示
        hint = QLabel("扫描完成后，系统将显示线缆当前寿命状态。所有工位扫码完成后才能开始测试。")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: #7f8c8d; font-size: 11px;")
        main_layout.addWidget(hint)
        
        # 工位输入区域
        for station_id in self.station_ids:
            group = QGroupBox(station_id.replace("_", " "))
            group.setStyleSheet("""
                QGroupBox { 
                    font-weight: bold; 
                    border: 2px solid #3498db; 
                    border-radius: 8px; 
                    margin-top: 10px; 
                    padding-top: 10px; 
                }
                QGroupBox::title { 
                    subcontrol-origin: margin; 
                    subcontrol-position: top center; 
                    padding: 0 10px; 
                    background-color: #3498db; 
                    color: white; 
                    border-radius: 4px; 
                }
            """)
            
            layout = QGridLayout(group)
            
            # SN输入
            sn_label = QLabel("线缆SN:")
            sn_input = QLineEdit()
            sn_input.setPlaceholderText("扫描或输入线缆SN后按回车")
            sn_input.returnPressed.connect(lambda sid=station_id: self._on_scan(sid))
            self.scan_entries[station_id] = sn_input
            layout.addWidget(sn_label, 0, 0)
            layout.addWidget(sn_input, 0, 1)
            
            # 确认按钮
            confirm_btn = QPushButton("确认")
            confirm_btn.clicked.connect(lambda checked, sid=station_id: self._on_scan(sid))
            confirm_btn.setStyleSheet("""
                QPushButton {
                    background-color: #3498db;
                    color: white;
                    padding: 6px 15px;
                    border: none;
                    border-radius: 4px;
                }
                QPushButton:hover { background-color: #2980b9; }
            """)
            layout.addWidget(confirm_btn, 0, 2)
            
            # 状态显示
            status_label = QLabel("等待扫码...")
            status_label.setStyleSheet("color: #7f8c8d; font-style: italic;")
            self.status_labels[station_id] = status_label
            layout.addWidget(status_label, 1, 0, 1, 3)
            
            main_layout.addWidget(group)
            self.confirmed[station_id] = False
        
        # 底部按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        
        self.start_btn = QPushButton("开始测试")
        self.start_btn.setEnabled(False)
        self.start_btn.setStyleSheet("""
            QPushButton {
                background-color: #27ae60;
                color: white;
                padding: 10px 30px;
                font-size: 14px;
                font-weight: bold;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #1e8449; }
            QPushButton:disabled { background-color: #bdc3c7; }
        """)
        self.start_btn.clicked.connect(self.accept)
        btn_layout.addWidget(self.start_btn)
        
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #e74c3c;
                color: white;
                padding: 10px 20px;
                border: none;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #c0392b; }
        """)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)
        
        main_layout.addLayout(btn_layout)
        
        # 自动聚焦第一个输入框
        if self.station_ids:
            self.scan_entries[self.station_ids[0]].setFocus()
    
    def _on_scan(self, station_id):
        """处理扫码/输入"""
        sn_input = self.scan_entries[station_id]
        status_label = self.status_labels[station_id]
        sn = sn_input.text().strip()
        
        if not sn:
            status_label.setText("请输入线缆SN")
            status_label.setStyleSheet("color: #e74c3c;")
            return
        
        # 尝试绑定
        success, msg = self.manager.bind_cable_to_station(station_id, sn)
        
        if success:
            # 获取详细信息
            info = self.manager.get_cable_info(sn)
            usage = info.get('total_count', 0) if info else 0
            limit = info.get('max_limit', 10000) if info else 10000
            
            status_label.setText(f"✓ {sn} - 寿命: {usage}/{limit}")
            status_label.setStyleSheet("color: #27ae60; font-weight: bold;")
            sn_input.setEnabled(False)
            self.confirmed[station_id] = True
            
            # 检查是否全部完成
            self._check_all_confirmed()
            
            # 自动跳转到下一个未确认的工位
            self._focus_next_unconfirmed(station_id)
        else:
            status_label.setText(f"✗ {msg}")
            status_label.setStyleSheet("color: #e74c3c;")
            sn_input.selectAll()
            sn_input.setFocus()
    
    def _check_all_confirmed(self):
        """检查是否所有工位都已确认"""
        all_done = all(self.confirmed.values())
        self.start_btn.setEnabled(all_done)
        if all_done:
            self.start_btn.setFocus()
    
    def _focus_next_unconfirmed(self, current_station_id):
        """聚焦下一个未确认的工位"""
        current_idx = self.station_ids.index(current_station_id)
        for i in range(current_idx + 1, len(self.station_ids)):
            sid = self.station_ids[i]
            if not self.confirmed[sid]:
                self.scan_entries[sid].setFocus()
                return
    
    def get_bindings(self):
        """获取最终的工位-线缆绑定"""
        return self.manager.current_session_cables.copy()
