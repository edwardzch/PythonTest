# -*- coding: utf-8 -*-
import sys
import json
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QGridLayout,
    QLabel, QLineEdit, QPushButton, QComboBox, QMessageBox, QWidget
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt
from utils.app_utils import resource_path

CONFIG_FILE = "config.json"


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("用户登录")
        self.setWindowIcon(QIcon(resource_path('app_icon.ico')))  # 设置窗口图标

        # 增加字体大小 (+12) - 使用setStyleSheet以覆盖qt-material的主题设置
        # 假设基础字体约为9-10pt，直接设置一个较大的值，例如22pt
        # 为了更准确，我们可以获取当前字体大小并增加
        current_font_size = self.font().pointSize()
        if current_font_size <= 0: current_font_size = 9  # 默认值
        new_size = current_font_size + 10

        # 应用到对话框及其所有子控件
        # QComboBox和QLineEdit高度增加约20% (假设大字体下默认约40px -> 设置为48px)
        self.setStyleSheet(f"""
            QDialog, QLabel, QPushButton {{ font-size: {new_size}pt; }}
            QComboBox, QLineEdit {{
                font-size: {new_size}pt;
                min-height: 28px;
                padding: 5px;
            }}
        """)

        self.setMinimumWidth(400)  # 稍微增加宽度以适应大字体

        self.user_info = {}

        self._load_config()
        self._init_ui()

    def _load_config(self):
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.users = config.get("access_control", {}).get("users", {})
            self.default_role = config.get("access_control", {}).get("default_login_role", "工程师")
        except (FileNotFoundError, json.JSONDecodeError) as e:
            QMessageBox.critical(self, "配置错误", f"加载配置文件 '{CONFIG_FILE}' 失败: {e}")
            # Don't exit, just close the dialog
            QApplication.instance().quit()

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)

        form_grid_layout = QGridLayout()
        form_grid_layout.setSpacing(10)

        # --- 角色选择 ---
        form_grid_layout.addWidget(QLabel("登录角色:"), 0, 0)
        self.role_combo = QComboBox()
        self.role_combo.addItem("工程师")
        self.role_combo.addItem("操作员")

        form_grid_layout.addWidget(self.role_combo, 0, 1)

        # --- 动态输入区域 ---
        # 使用 QStackedWidget 来切换工程师和操作员的输入界面
        self.stacked_widget = QWidget()
        self.stacked_layout = QGridLayout(self.stacked_widget)
        self.stacked_layout.setContentsMargins(0, 0, 0, 0)

        # 工程师视图
        self.password_label = QLabel("密码:")
        self.password_input = QLineEdit()
        self.password_input.setEchoMode(QLineEdit.Password)
        self.stacked_layout.addWidget(self.password_label, 0, 0)
        self.stacked_layout.addWidget(self.password_input, 0, 1)

        # 操作员视图
        self.id_label = QLabel("工号:")
        self.id_input = QLineEdit()
        self.stacked_layout.addWidget(self.id_label, 1, 0)
        self.stacked_layout.addWidget(self.id_input, 1, 1)

        # --- 登录按钮和状态标签 ---
        self.login_button = QPushButton("登录")
        self.login_button.clicked.connect(self._attempt_login)
        # 让登录按钮自动应用主题的强调色
        self.login_button.setProperty("class", "primary")

        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #dc3545;")  # 错误信息用红色

        main_layout.addLayout(form_grid_layout)
        main_layout.addWidget(self.stacked_widget)
        main_layout.addStretch()
        main_layout.addWidget(self.login_button)
        main_layout.addWidget(self.status_label, 0, Qt.AlignCenter)

        # 连接回车键
        self.password_input.returnPressed.connect(self.login_button.click)
        self.id_input.returnPressed.connect(self.login_button.click)

        # --- Initialize State (Moved to end to ensure all widgets exist) ---
        self.role_combo.currentIndexChanged.connect(self._update_ui_for_role)

        # Set the default role based on loaded config
        default_index = 1 if self.default_role == "操作员" else 0
        self.role_combo.setCurrentIndex(default_index)
        # Manually call the update function for the initial state
        self._update_ui_for_role(default_index)

    def _update_ui_for_role(self, index):
        if index == 0:  # 工程师
            self.id_label.hide()
            self.id_input.hide()
            self.password_label.show()
            self.password_input.show()
            self.password_input.clear()
            self.password_input.setFocus()
        else:  # 操作员
            self.password_label.hide()
            self.password_input.hide()
            self.id_label.show()
            self.id_input.show()
            self.id_input.clear()
            self.id_input.setFocus()

    def _attempt_login(self):
        role = self.role_combo.currentText()

        if role == "工程师":
            user_id = "engineer"
            password = self.password_input.text()
            if not password:
                self.status_label.setText("密码不能为空。")
                return

            user_data = self.users.get(user_id)
            if user_data and user_data.get("password") == password:
                self.user_info = {
                    "id": user_id,
                    "name": user_data.get("name", ""),
                    "permissions": user_data.get("permissions", [])
                }
                self.accept()
            else:
                self.status_label.setText("密码错误。")

        elif role == "操作员":
            user_id = self.id_input.text().strip()
            if not user_id:
                self.status_label.setText("工号不能为空。")
                return

            user_data = self.users.get(user_id)
            if user_data:
                self.user_info = {
                    "id": user_id,
                    "name": user_data.get("name", ""),
                    "permissions": user_data.get("permissions", [])
                }
                self.accept()
            else:
                self.status_label.setText("操作员工号不存在。")

    def get_user_info(self):
        return self.user_info


if __name__ == '__main__':
    app = QApplication(sys.argv)
    # 在主入口应用样式，这里只是为了独立测试
    try:
        from qt_material import apply_stylesheet

        apply_stylesheet(app, theme='dark_teal.xml')
    except ImportError:
        pass

    dialog = LoginDialog()
    dialog.exec()

    if dialog.result() == QDialog.Accepted:
        print(f"登录成功: {dialog.get_user_info()}")
    else:
        print("登录取消。")

    sys.exit(0)