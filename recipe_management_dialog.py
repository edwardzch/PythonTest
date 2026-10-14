# -*- coding: utf-8 -*-
"""
配方绑定管理对话框 (Recipe Management Dialog)
提供测试脚本、产品编码、转接线编码绑定的增删改查界面，支持浏览选择脚本及多转接线自定义添加。
"""

import os
import logging
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QCheckBox, QMessageBox, QGroupBox,
    QFormLayout, QFileDialog, QHeaderView, QAbstractItemView, QListWidget,
    QListWidgetItem
)
from PySide6.QtCore import Qt
from recipe_manager import get_recipe_manager, RecipeManager
from utils.consumable_db import check_cable_sn


class RecipeEditDialog(QDialog):
    """新增/编辑配方对话框"""
    def __init__(self, parent=None, recipe_data: dict = None):
        super().__init__(parent)
        self.recipe_data = recipe_data or {}
        self.init_ui()

    def init_ui(self):
        is_edit = bool(self.recipe_data.get('id'))
        self.setWindowTitle("编辑配方" if is_edit else "新增配方绑定")
        self.resize(550, 480)
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

        # 1. 基础信息配置
        base_group = QGroupBox("配方基础信息")
        form_layout = QFormLayout(base_group)
        form_layout.setSpacing(10)

        self.edit_name = QLineEdit(self.recipe_data.get('recipe_name', ''))
        self.edit_name.setPlaceholderText("例如: BD3E-寻相测试配方")
        form_layout.addRow("配方名称:", self.edit_name)

        # 测试脚本 + 浏览按钮
        seq_layout = QHBoxLayout()
        self.edit_seq_path = QLineEdit(self.recipe_data.get('sequence_path', ''))
        self.edit_seq_path.setPlaceholderText("请选择或输入测试脚本 .json 相对/绝对路径...")
        
        self.btn_browse_seq = QPushButton("📁 浏览...")
        self.btn_browse_seq.setFixedWidth(85)
        self.btn_browse_seq.clicked.connect(self._browse_sequence_file)
        
        seq_layout.addWidget(self.edit_seq_path)
        seq_layout.addWidget(self.btn_browse_seq)
        form_layout.addRow("测试脚本:", seq_layout)

        # 示例产品条码 + 智能识别截取按钮
        sample_layout = QHBoxLayout()
        self.edit_sample_sn = QLineEdit(self.recipe_data.get('sample_sn', ''))
        self.edit_sample_sn.setPlaceholderText("扫入/录入产品示例完整条码 (如 SEA20202607310001)...")
        self.edit_sample_sn.textChanged.connect(self._on_sample_or_code_changed)

        self.btn_smart_extract = QPushButton("⚡ 智能识别截取")
        self.btn_smart_extract.setFixedWidth(120)
        self.btn_smart_extract.setStyleSheet("font-weight: bold; background-color: #2980b9; color: white;")
        self.btn_smart_extract.clicked.connect(self._smart_recognize_product_code)

        sample_layout.addWidget(self.edit_sample_sn)
        sample_layout.addWidget(self.btn_smart_extract)
        form_layout.addRow("示例产品条码:", sample_layout)

        # 提取的核心产品编码
        self.edit_product_code = QLineEdit(self.recipe_data.get('product_code', ''))
        self.edit_product_code.setPlaceholderText("例如: SEA20 (自动截取的关键识别编码/前缀)")
        self.edit_product_code.textChanged.connect(self._on_sample_or_code_changed)
        form_layout.addRow("提取的产品编码:", self.edit_product_code)

        # 识别比对状态指示
        self.lbl_extract_status = QLabel("💡 提示: 扫入示例条码后点击「⚡ 智能识别截取」，系统将自动判定/提取核心编码。")
        self.lbl_extract_status.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        self.lbl_extract_status.setWordWrap(True)
        form_layout.addRow("识别比对状态:", self.lbl_extract_status)

        # 是否启用寿命管理
        self.chk_life_mgr = QCheckBox("启用转接线寿命管理 (自动同步至线缆管理数据库，默认 10,000 次)")
        self.chk_life_mgr.setChecked(self.recipe_data.get('enable_life_management', True))
        form_layout.addRow("寿命管理:", self.chk_life_mgr)

        layout.addWidget(base_group)

        # 2. 转接线编码配置
        cables_group = QGroupBox("绑定的转接线编码列表 (可配置多根)")
        cables_layout = QVBoxLayout(cables_group)

        self.cable_list = QListWidget()
        self.cable_list.setSelectionMode(QAbstractItemView.SingleSelection)

        # 初始化已有转接线列表
        existing_cables = self.recipe_data.get('adapter_cables', [])
        for cable_sn in existing_cables:
            self._add_cable_item(cable_sn)

        btn_cable_layout = QHBoxLayout()
        self.btn_add_cable = QPushButton("➕ 添加转接线编码")
        self.btn_add_cable.clicked.connect(self._on_add_cable_clicked)

        self.btn_del_cable = QPushButton("➖ 删除选中的转接线")
        self.btn_del_cable.clicked.connect(self._on_del_cable_clicked)

        btn_cable_layout.addWidget(self.btn_add_cable)
        btn_cable_layout.addWidget(self.btn_del_cable)

        cables_layout.addWidget(self.cable_list)
        cables_layout.addLayout(btn_cable_layout)

        layout.addWidget(cables_group)

        # 3. 底部确定/取消
        bottom_layout = QHBoxLayout()
        self.btn_save = QPushButton("💾 保存配方")
        self.btn_save.setFixedHeight(36)
        self.btn_save.setStyleSheet("font-weight: bold; background-color: #27ae60; color: white;")
        self.btn_save.clicked.connect(self._save_recipe)

        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setFixedHeight(36)
        self.btn_cancel.clicked.connect(self.reject)

        bottom_layout.addWidget(self.btn_save)
        bottom_layout.addWidget(self.btn_cancel)

        layout.addLayout(bottom_layout)

    def _browse_sequence_file(self):
        """浏览选择测试脚本 JSON 文件"""
        initial_dir = os.path.join(os.getcwd(), "sequences")
        if not os.path.exists(initial_dir):
            initial_dir = os.getcwd()

        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "选择测试脚本文件",
            initial_dir,
            "JSON 测试脚本 (*.json);;所有文件 (*.*)"
        )
        if file_path:
            # 优先使用相对路径（相对当前工作目录）
            try:
                rel_path = os.path.relpath(file_path, os.getcwd()).replace('\\', '/')
                self.edit_seq_path.setText(rel_path)
            except Exception:
                self.edit_seq_path.setText(file_path.replace('\\', '/'))

    def _add_cable_item(self, cable_sn: str = ""):
        """往 ListWidget 添加一条可编辑的转接线列表项"""
        item = QListWidgetItem(self.cable_list)
        item.setFlags(item.flags() | Qt.ItemIsEditable)
        item.setText(cable_sn if cable_sn else "双击输入转接线编码...")
        self.cable_list.addItem(item)
        if not cable_sn:
            self.cable_list.editItem(item)

    def _on_add_cable_clicked(self):
        self._add_cable_item("")

    def _on_del_cable_clicked(self):
        row = self.cable_list.currentRow()
        if row >= 0:
            self.cable_list.takeItem(row)
        else:
            QMessageBox.information(self, "提示", "请先在列表中选中要删除的转接线编码。")

    def _on_sample_or_code_changed(self):
        """当示例条码或提取编码变动时实时尝试校验"""
        sample_sn = self.edit_sample_sn.text().strip()
        prod_code = self.edit_product_code.text().strip()
        if sample_sn and prod_code:
            sample_upper = sample_sn.upper()
            code_upper = prod_code.upper()
            if code_upper in sample_upper or sample_upper.startswith(code_upper):
                self.lbl_extract_status.setText(f"✅ 匹配校验成功！示例条码 [{sample_sn}] 包含核心产品编码 [{prod_code}]。")
                self.lbl_extract_status.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 12px;")
            else:
                self.lbl_extract_status.setText(f"⚠ 示例条码 [{sample_sn}] 中未找到产品编码 [{prod_code}]，请确认前缀/关键字！")
                self.lbl_extract_status.setStyleSheet("color: #e74c3c; font-weight: bold; font-size: 12px;")

    def _smart_recognize_product_code(self):
        """智能识别与截取测试工具函数"""
        sample_sn = self.edit_sample_sn.text().strip()
        prod_code = self.edit_product_code.text().strip()

        if not sample_sn:
            self.lbl_extract_status.setText("⚠ 请先在「示例产品条码」中扫描或输入一个真实条码！")
            self.lbl_extract_status.setStyleSheet("color: #e67e22; font-weight: bold; font-size: 12px;")
            self.edit_sample_sn.setFocus()
            return

        import re
        extracted = ""
        # 1. 拆分连字符/下划线 (如 PN-SEA20-20260731)
        parts = re.split(r'[-_/\s]+', sample_sn)
        if len(parts) > 1:
            for p in parts:
                if any(c.isalpha() for c in p):
                    extracted = p
                    break

        # 2. 如果没拆出来，正则匹配前缀字母+数字组合 (如 SEA20202607310001 -> SEA20)
        if not extracted:
            m = re.match(r'^([a-zA-Z]+[0-9]{1,3})', sample_sn)
            if m:
                extracted = m.group(1)
            else:
                extracted = sample_sn[:5]

        # 填入提取的产品编码
        if extracted:
            self.edit_product_code.setText(extracted)
            prod_code = extracted

        # 验证比对结果
        if prod_code and (prod_code.upper() in sample_sn.upper() or sample_sn.upper().startswith(prod_code.upper())):
            msg = f"⚡ 智能截取完成！核心编码 [{prod_code}] 成功从示例条码 [{sample_sn}] 中识别提取并验证一致。"
            self.lbl_extract_status.setText(msg)
            self.lbl_extract_status.setStyleSheet("color: #27ae60; font-weight: bold; font-size: 12px;")
        else:
            msg = f"⚠ 已自动识别可能编码为 [{prod_code}]，请人工确认是否有误。"
            self.lbl_extract_status.setText(msg)
            self.lbl_extract_status.setStyleSheet("color: #f39c12; font-weight: bold; font-size: 12px;")

    def _save_recipe(self):
        """保存配方数据"""
        name = self.edit_name.text().strip()
        seq_path = self.edit_seq_path.text().strip()
        sample_sn = self.edit_sample_sn.text().strip()
        prod_code = self.edit_product_code.text().strip()
        enable_life = self.chk_life_mgr.isChecked()

        if not name:
            QMessageBox.warning(self, "警告", "配方名称不能为空！")
            self.edit_name.setFocus()
            return

        if not seq_path:
            QMessageBox.warning(self, "警告", "测试脚本不能为空！请点击“浏览...”选择脚本。")
            self.edit_seq_path.setFocus()
            return

        # 收集转接线列表
        cables = []
        for i in range(self.cable_list.count()):
            text = self.cable_list.item(i).text().strip()
            if text and text != "双击输入转接线编码...":
                cables.append(text)

        if not cables:
            QMessageBox.warning(self, "警告", "请至少添加一根绑定的转接线编码！")
            return

        # 如果启用了寿命管理，自动在耗材数据库初始化/注册线缆
        if enable_life:
            for c_sn in cables:
                check_cable_sn(c_sn)

        result_data = {
            'id': self.recipe_data.get('id', ''),
            'recipe_name': name,
            'sequence_path': seq_path,
            'sample_sn': sample_sn,
            'product_code': prod_code,
            'adapter_cables': cables,
            'enable_life_management': enable_life
        }

        mgr = get_recipe_manager()
        if result_data['id']:
            success = mgr.update_recipe(result_data['id'], result_data)
        else:
            success = mgr.add_recipe(result_data)

        if success:
            QMessageBox.information(self, "成功", "配方保存成功！")
            self.accept()
        else:
            QMessageBox.critical(self, "错误", "保存配方到文件失败！")

    def closeEvent(self, event):
        """点击右上角 X 关闭窗口"""
        self.reject()
        event.accept()


class RecipeManagementDialog(QDialog):
    """配方绑定管理主对话框"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.mgr = get_recipe_manager()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("配方绑定管理 (脚本 - 产品 - 转接线)")
        self.resize(850, 500)
        self.setWindowFlags(
            Qt.Window |
            Qt.WindowSystemMenuHint |
            Qt.WindowTitleHint |
            Qt.WindowCloseButtonHint |
            Qt.WindowMaximizeButtonHint |
            Qt.WindowMinimizeButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setSpacing(10)

        # 顶部说明
        lbl_tip = QLabel("提示：配置测试脚本、产品编码与转接线编码的绑定配方。扫码开始测试时，将自动校验转接线。")
        lbl_tip.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        layout.addWidget(lbl_tip)

        # 配方表格
        self.table = QTableWidget()
        self.table.setColumnCount(5)
        self.table.setHorizontalHeaderLabels([
            "配方名称", "测试脚本", "产品编码", "转接线编码列表", "寿命管理"
        ])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.doubleClicked.connect(self._edit_selected_recipe)

        layout.addWidget(self.table)

        # 按钮控制栏
        btn_layout = QHBoxLayout()

        self.btn_add = QPushButton("➕ 新增配方")
        self.btn_add.setFixedHeight(36)
        self.btn_add.setStyleSheet("font-weight: bold; background-color: #27ae60; color: white;")
        self.btn_add.clicked.connect(self._add_recipe)

        self.btn_edit = QPushButton("✏️ 编辑配方")
        self.btn_edit.setFixedHeight(36)
        self.btn_edit.clicked.connect(self._edit_selected_recipe)

        self.btn_delete = QPushButton("🗑️ 删除配方")
        self.btn_delete.setFixedHeight(36)
        self.btn_delete.setStyleSheet("color: #e74c3c;")
        self.btn_delete.clicked.connect(self._delete_recipe)

        self.btn_refresh = QPushButton("🔄 刷新")
        self.btn_refresh.setFixedHeight(36)
        self.btn_refresh.clicked.connect(self.load_recipes_to_table)

        btn_layout.addWidget(self.btn_add)
        btn_layout.addWidget(self.btn_edit)
        btn_layout.addWidget(self.btn_delete)
        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addStretch()

        self.btn_close = QPushButton("关闭")
        self.btn_close.setFixedHeight(36)
        self.btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(self.btn_close)

        layout.addLayout(btn_layout)

        # 初始加载
        self.load_recipes_to_table()

    def load_recipes_to_table(self):
        """填充表格"""
        recipes = self.mgr.get_all_recipes()
        self.table.setRowCount(len(recipes))

        for row, rec in enumerate(recipes):
            cables_str = ", ".join(rec.get('adapter_cables', []))
            life_str = "已启用" if rec.get('enable_life_management', True) else "未启用"
            prod_code = rec.get('product_code', '')
            sample_sn = rec.get('sample_sn', '')
            prod_disp = f"{prod_code} [示例: {sample_sn}]" if sample_sn else prod_code

            item_name = QTableWidgetItem(rec.get('recipe_name', ''))
            item_seq = QTableWidgetItem(rec.get('sequence_path', ''))
            item_prod = QTableWidgetItem(prod_disp)
            item_cables = QTableWidgetItem(cables_str)
            item_life = QTableWidgetItem(life_str)

            item_name.setData(Qt.UserRole, rec.get('id'))

            self.table.setItem(row, 0, item_name)
            self.table.setItem(row, 1, item_seq)
            self.table.setItem(row, 2, item_prod)
            self.table.setItem(row, 3, item_cables)
            self.table.setItem(row, 4, item_life)

    def _add_recipe(self):
        dlg = RecipeEditDialog(self)
        if dlg.exec() == QDialog.Accepted:
            self.load_recipes_to_table()

    def _edit_selected_recipe(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在列表中选中要编辑的配方。")
            return

        item = self.table.item(row, 0)
        recipe_id = item.data(Qt.UserRole)
        
        recipes = self.mgr.get_all_recipes()
        recipe_data = next((r for r in recipes if r.get('id') == recipe_id), None)

        if recipe_data:
            dlg = RecipeEditDialog(self, recipe_data)
            if dlg.exec() == QDialog.Accepted:
                self.load_recipes_to_table()

    def _delete_recipe(self):
        row = self.table.currentRow()
        if row < 0:
            QMessageBox.information(self, "提示", "请先在列表中选中要删除的配方。")
            return

        item = self.table.item(row, 0)
        recipe_id = item.data(Qt.UserRole)
        recipe_name = item.text()

        reply = QMessageBox.question(
            self,
            "确认删除",
            f"确定要删除配方【{recipe_name}】吗？删除后不可恢复。",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            if self.mgr.delete_recipe(recipe_id):
                QMessageBox.information(self, "成功", "配方已删除。")
                self.load_recipes_to_table()
            else:
                QMessageBox.critical(self, "错误", "删除配方失败！")

    def closeEvent(self, event):
        """点击右上角 X 关闭窗口"""
        self.accept()
        event.accept()
