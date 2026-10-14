# -*- coding: utf-8 -*-
"""
工位转接线编码扫码校验弹窗 (Station Adapter Cable Dialog)
在测试开始前提示操作员扫描/输入配方绑定的转接线编码，支持任意随机顺序扫码校验。
"""

import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton,
    QGroupBox, QFormLayout, QMessageBox, QFrame
)
from PySide6.QtCore import Qt
from utils.consumable_db import check_cable_sn

class StationAdapterCableDialog(QDialog):
    def __init__(self, parent, station_id: str, recipe: dict, current_sn: str):
        super().__init__(parent)
        self.station_id = station_id
        self.recipe = recipe
        self.current_sn = current_sn
        self.expected_cables = recipe.get('adapter_cables', [])
        self.enable_life_management = recipe.get('enable_life_management', True)
        
        self.scanned_cables = []
        self.cable_life_info = ""
        self.inputs = []

        self.init_ui()

    def showEvent(self, event):
        super().showEvent(event)
        if self.parent():
            try:
                parent = self.parent()
                parent_center = parent.mapToGlobal(parent.rect().center())
                size_hint = self.sizeHint()
                w = size_hint.width() if size_hint.width() > 0 else 540
                h = size_hint.height() if size_hint.height() > 0 else 400
                x = parent_center.x() - w // 2
                y = parent_center.y() - h // 2
                self.move(x, y)
            except Exception as e:
                print(f"转接线弹窗居中定位异常: {e}")

    def init_ui(self):
        self.setWindowTitle(f"【{self.station_id}】转接线编码匹配校验")
        self.setFixedWidth(540)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowSystemMenuHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowMinimizeButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        # 1. 顶部提示信息卡片
        info_group = QGroupBox("1. 配方绑定校验信息")
        info_layout = QFormLayout(info_group)
        info_layout.setSpacing(8)

        recipe_name = self.recipe.get('recipe_name', '未命名配方')
        seq_path = self.recipe.get('sequence_path', '')
        seq_name = seq_path.split('/')[-1].split('\\')[-1] if seq_path else '默认脚本'

        lbl_station = QLabel(f"<b style='color:#3498db; font-size:14px;'>{self.station_id}</b>")
        lbl_recipe = QLabel(f"<b>{recipe_name}</b>")
        lbl_seq = QLabel(seq_name)
        lbl_sn = QLabel(self.current_sn if self.current_sn else "通用/未指定")
        lbl_count = QLabel(f"<b style='color:#e67e22;'>{len(self.expected_cables)} 根 (支持随机顺序扫码)</b>")

        info_layout.addRow("当前工位:", lbl_station)
        info_layout.addRow("匹配配方:", lbl_recipe)
        info_layout.addRow("测试脚本:", lbl_seq)
        info_layout.addRow("产品 SN:", lbl_sn)
        info_layout.addRow("所需转接线:", lbl_count)

        layout.addWidget(info_group)

        # 2. 扫码输入区域
        scan_group = QGroupBox(f"2. 请扫码/输入转接线编码 (共 {len(self.expected_cables)} 根，可任意顺序)")
        scan_layout = QFormLayout(scan_group)
        scan_layout.setSpacing(10)

        for i in range(1, len(self.expected_cables) + 1):
            line_edit = QLineEdit()
            line_edit.setPlaceholderText(f"扫描第 {i} 根转接线编码...")
            line_edit.setStyleSheet("font-size: 14px; padding: 5px;")
            
            # 回车自动跳下一个输入框或提交
            next_idx = i
            line_edit.returnPressed.connect(lambda idx=next_idx: self._on_input_return(idx))
            
            scan_layout.addRow(f"转接线 {i}:", line_edit)
            self.inputs.append(line_edit)

        layout.addWidget(scan_group)

        # 3. 错误提示 Label
        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 13px;")
        self.error_label.setAlignment(Qt.AlignCenter)
        self.error_label.setWordWrap(True)
        layout.addWidget(self.error_label)

        # 4. 底部按钮
        btn_layout = QHBoxLayout()
        self.btn_confirm = QPushButton("✅ 确认并开始测试")
        self.btn_confirm.setFixedHeight(38)
        self.btn_confirm.setStyleSheet("font-weight: bold; font-size: 14px; background-color: #27ae60; color: white;")
        self.btn_confirm.clicked.connect(self._verify_and_accept)

        self.btn_cancel = QPushButton("❌ 取消测试")
        self.btn_cancel.setFixedHeight(38)
        self.btn_cancel.clicked.connect(self._on_cancel_clicked)

        btn_layout.addWidget(self.btn_confirm)
        btn_layout.addWidget(self.btn_cancel)
        layout.addLayout(btn_layout)

        # 默认聚焦到第一个输入框
        if self.inputs:
            self.inputs[0].setFocus()

    def _on_cancel_clicked(self):
        self.reject()

    def _on_input_return(self, current_1_index: int):
        """当按回车时跳到下一个 LineEdit，最后一个回车自动提交"""
        if current_1_index < len(self.inputs):
            self.inputs[current_1_index].setFocus()
            self.inputs[current_1_index].selectAll()
        else:
            self._verify_and_accept()

    def _verify_and_accept(self):
        """无序/随机顺序匹配校验输入的转接线编码"""
        if getattr(self, '_is_verifying', False):
            return
        self._is_verifying = True
        try:
            scanned_list = [inp.text().strip() for inp in self.inputs]
            
            # 1. 检查空字段
            for i, val in enumerate(scanned_list, start=1):
                if not val:
                    self.error_label.setText(f"⚠ 转接线 {i} 编码不能为空，请扫描/输入！")
                    self.inputs[i-1].setFocus()
                    return

            # 2. 无序集/多项比对 (支持配方为型号/前缀如 26011101498，实际扫码为独有SN如 26011101498-01)
            expected_upper = [e.upper().strip() for e in self.expected_cables]
            scanned_upper = [s.upper().strip() for s in scanned_list]

            unmatched_scanned = []
            matched_expected_indices = set()

            for scanned_val in scanned_upper:
                found = False
                # 提取截取主型号前缀 (按 - / _ / # 分隔)
                scanned_main = scanned_val.split('-')[0].split('_')[0].split('#')[0]
                for idx, expected_val in enumerate(expected_upper):
                    if idx not in matched_expected_indices:
                        # 核心比对：全相同 / 前缀匹配 / 主型号相同 / 双向包含
                        if (scanned_val == expected_val or
                            scanned_val.startswith(expected_val) or
                            scanned_main == expected_val or
                            expected_val in scanned_val or
                            scanned_val in expected_val):
                            matched_expected_indices.add(idx)
                            found = True
                            break
                if not found:
                    unmatched_scanned.append(scanned_val)

            if unmatched_scanned or len(matched_expected_indices) < len(expected_upper):
                err_details = ""
                if unmatched_scanned:
                    err_details = f"包含未授权/非配方转接线: [{', '.join(unmatched_scanned)}]"
                else:
                    missing = [self.expected_cables[i] for i in range(len(expected_upper)) if i not in matched_expected_indices]
                    err_details = f"缺失转接线: [{', '.join(missing)}]"

                msg = f"❌ 转接线匹配错误！{err_details}\n配方要求包含: [{', '.join(self.expected_cables)}]"
                self.error_label.setText(msg)

                # 保持错误提示文字，全选高亮错误文本并重新聚焦，扫码时可直接覆盖
                for inp in self.inputs:
                    inp.selectAll()
                if self.inputs:
                    self.inputs[0].setFocus()
                return

            # 3. 校验通过，汇总寿命及生成信息
            life_info_parts = []
            if self.enable_life_management:
                life_warnings = []
                for cable_sn in scanned_list:
                    cable_info = check_cable_sn(cable_sn)
                    if cable_info:
                        status = cable_info.get('status', 'active')
                        used = cable_info.get('total_count', 0)
                        limit = cable_info.get('max_limit', 10000)
                        life_info_parts.append(f"{cable_sn} ({used}/{limit})")
                        if status == 'retired' or used >= limit:
                            life_warnings.append(f"转接线 [{cable_sn}] 寿命已超限 ({used}/{limit} 次)！")
                    else:
                        life_info_parts.append(f"{cable_sn} (0/10000)")
                
                if life_warnings:
                    warn_msg = "\n".join(life_warnings) + "\n\n请在【线缆管理】中维护寿命或更换线缆。"
                    QMessageBox.warning(self, "线缆寿命预警", warn_msg)
            else:
                life_info_parts = [f"{sn} (未启用寿命管理)" for sn in scanned_list]

            self.scanned_cables = scanned_list
            self.cable_life_info = ", ".join(life_info_parts)
            self.accept()
        finally:
            self._is_verifying = False
