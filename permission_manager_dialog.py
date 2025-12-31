# -*- coding: utf-8 -*-
import sys
import json
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QListWidget, QListWidgetItem,
    QCheckBox, QGroupBox, QGridLayout, QMessageBox, QInputDialog, QWidget, QComboBox
)
from PySide6.QtCore import Qt

CONFIG_FILE = "config.json"

class PermissionManagerDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("权限管理")
        self.setMinimumSize(800, 600)

        self._load_config()
        self._init_ui()
        self._load_users_to_list()

    def _load_config(self):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self.access_control = self.config.get("access_control", {})
            self.users = self.access_control.get("users", {})
            self.permissions_list = self.access_control.get("permissions_list", [])
        except FileNotFoundError:
            QMessageBox.critical(self, "错误", f"配置文件 '{CONFIG_FILE}' 未找到。")
            self.close()
        except json.JSONDecodeError:
            QMessageBox.critical(self, "错误", f"配置文件 '{CONFIG_FILE}' 格式错误。")
            self.close()

    def _save_config(self):
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            QMessageBox.information(self, "保存成功", "权限配置已保存。")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存配置时发生错误: {e}")

    def _init_ui(self):
        # 主布局：左侧用户列表，右侧详情和权限
        main_layout = QHBoxLayout(self)
        main_layout.setStretch(0, 1) # 左侧比例
        main_layout.setStretch(1, 2) # 右侧比例

        # --- 左侧 ---
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.addWidget(QLabel("用户列表:"))
        
        self.user_list_widget = QListWidget()
        self.user_list_widget.currentItemChanged.connect(self._display_user_details)
        left_layout.addWidget(self.user_list_widget)

        user_buttons_layout = QHBoxLayout()
        self.add_user_button = QPushButton("新增用户")
        self.add_user_button.clicked.connect(self._add_user)
        self.delete_user_button = QPushButton("删除用户")
        self.delete_user_button.clicked.connect(self._delete_user)
        user_buttons_layout.addWidget(self.add_user_button)
        user_buttons_layout.addWidget(self.delete_user_button)
        left_layout.addLayout(user_buttons_layout)
        
        main_layout.addWidget(left_widget)

        # --- 右侧 ---
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)

        # 权限组
        self.permissions_group_box = QGroupBox("权限设置")
        self.permissions_grid_layout = QGridLayout(self.permissions_group_box)
        self.permission_checkboxes = {} 

        max_cols = 3
        for i, perm in enumerate(self.permissions_list):
            checkbox = QCheckBox(perm["name"])
            self.permissions_grid_layout.addWidget(checkbox, i // max_cols, i % max_cols)
            self.permission_checkboxes[perm["id"]] = checkbox
        
        right_layout.addWidget(self.permissions_group_box)

        # 用户详情组
        details_group_box = QGroupBox("用户详情")
        form_layout = QGridLayout(details_group_box)
        form_layout.addWidget(QLabel("工号:"), 0, 0)
        self.id_input = QLineEdit()
        self.id_input.setReadOnly(True)
        form_layout.addWidget(self.id_input, 0, 1)

        form_layout.addWidget(QLabel("姓名:"), 1, 0)
        self.name_input = QLineEdit()
        form_layout.addWidget(self.name_input, 1, 1)
        
        right_layout.addWidget(details_group_box)
        
        right_layout.addStretch() # 添加伸缩，将保存按钮推到底部

        self.save_button = QPushButton("保存更改")
        self.save_button.clicked.connect(self._on_save_changes)
        right_layout.addWidget(self.save_button)

        main_layout.addWidget(right_widget)

    def _load_users_to_list(self):
        self.user_list_widget.clear()
        # 工程师账户不在此处管理
        for user_id, user_data in self.users.items():
            if user_id != "engineer":
                item = QListWidgetItem(f"{user_data.get('name', 'N/A')} ({user_id})")
                item.setData(Qt.UserRole, user_id)
                self.user_list_widget.addItem(item)
        
        if self.user_list_widget.count() > 0:
            self.user_list_widget.setCurrentRow(0)
        else:
            self._clear_user_details()

    def _display_user_details(self, current_item, previous_item):
        if not current_item:
            self._clear_user_details()
            return

        user_id = current_item.data(Qt.UserRole)
        user_data = self.users.get(user_id, {})

        self.id_input.setText(user_id)
        self.name_input.setText(user_data.get("name", ""))

        current_permissions = user_data.get("permissions", [])
        for perm_id, checkbox in self.permission_checkboxes.items():
            checkbox.setChecked(perm_id in current_permissions)

    def _clear_user_details(self):
        self.id_input.clear()
        self.name_input.clear()
        for checkbox in self.permission_checkboxes.values():
            checkbox.setChecked(False)

    def _add_user(self):
        new_id, ok1 = QInputDialog.getText(self, "新增用户", "请输入新用户的工号:")
        if not ok1 or not new_id: return
        if new_id in self.users:
            QMessageBox.warning(self, "警告", f"工号 '{new_id}' 已存在。")
            return
        
        new_name, ok2 = QInputDialog.getText(self, "新增用户", "请输入新用户的姓名:", text=new_id)
        if not ok2 or not new_name: return

        # 新用户默认密码为工号，或您可以设定一个固定的初始密码
        default_password = new_id 
        
        self.users[new_id] = {
            "name": new_name,
            "password": default_password,
            "permissions": []
        }
        self._load_users_to_list()
        
        found_items = self.user_list_widget.findItems(f"{new_name} ({new_id})", Qt.MatchExactly)
        if found_items:
            self.user_list_widget.setCurrentItem(found_items[0])
        
        self._save_config()
        QMessageBox.information(self, "成功", f"用户 '{new_name}' 已添加。\n初始密码为工号: {default_password}")

    def _delete_user(self):
        current_item = self.user_list_widget.currentItem()
        if not current_item:
            QMessageBox.warning(self, "删除用户", "请先选择一个要删除的用户。")
            return

        user_id = current_item.data(Qt.UserRole)
        if user_id == "engineer":
            QMessageBox.warning(self, "删除用户", "不能删除工程师账户。")
            return

        reply = QMessageBox.question(self, "确认删除", f"确定要删除用户 '{user_id}' 吗？",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            del self.users[user_id]
            self._load_users_to_list()
            self._save_config()

    def _on_save_changes(self):
        current_item = self.user_list_widget.currentItem()
        if not current_item:
            QMessageBox.warning(self, "保存更改", "请选择一个用户以保存更改。")
            return

        user_id = current_item.data(Qt.UserRole)
        user_data = self.users.get(user_id)

        new_name_on_form = self.name_input.text()
        if user_data.get("name") != new_name_on_form:
             user_data["name"] = new_name_on_form
             current_item.setText(f"{new_name_on_form} ({user_id})")
        
        selected_permissions = []
        for perm_id, checkbox in self.permission_checkboxes.items():
            if checkbox.isChecked():
                selected_permissions.append(perm_id)
        user_data["permissions"] = selected_permissions
        
        self._save_config()

if __name__ == '__main__':
    app = QApplication(sys.argv)
    dialog = PermissionManagerDialog()
    dialog.exec()
    sys.exit(0)