# -*- coding: utf-8 -*-
import json
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, 
    QComboBox, QPushButton, QMessageBox, QGroupBox
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt
from utils.app_utils import resource_path

CONFIG_FILE = "config.json"

class LoginSettingsDialog(QDialog):
    """登录设置对话框 - 允许用户修改默认登录角色"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("登录设置")
        self.setWindowIcon(QIcon(resource_path('app_icon.ico')))
        self.setMinimumWidth(350)
        self.setModal(True)
        
        self._load_config()
        self._init_ui()
    
    def _load_config(self):
        """加载配置文件"""
        try:
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                self.config = json.load(f)
            self.access_control = self.config.get("access_control", {})
            self.default_login_role = self.access_control.get("default_login_role", "工程师")
        except FileNotFoundError:
            QMessageBox.critical(self, "错误", f"配置文件 '{CONFIG_FILE}' 未找到。")
            self.close()
        except json.JSONDecodeError:
            QMessageBox.critical(self, "错误", f"配置文件 '{CONFIG_FILE}' 格式错误。")
            self.close()
    
    def _save_config(self):
        """保存配置文件"""
        try:
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            return True
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"保存配置时发生错误: {e}")
            return False
    
    def _init_ui(self):
        """初始化UI"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(15)
        
        # 设置组
        settings_group = QGroupBox("默认登录角色设置")
        settings_layout = QVBoxLayout(settings_group)
        
        # 说明文字
        description_label = QLabel(
            "选择下次启动程序时默认使用的登录角色。\n"
            "修改后将在下次打开登录窗口时生效。"
        )
        description_label.setWordWrap(True)
        description_label.setStyleSheet("color: #888; font-size: 11px;")
        settings_layout.addWidget(description_label)
        
        # 角色选择
        role_layout = QHBoxLayout()
        role_layout.addWidget(QLabel("默认登录角色:"))
        
        self.role_combo = QComboBox()
        self.role_combo.addItems(["工程师", "操作员"])
        self.role_combo.setCurrentText(self.default_login_role)
        role_layout.addWidget(self.role_combo, 1)
        
        settings_layout.addLayout(role_layout)
        main_layout.addWidget(settings_group)
        
        # 按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()
        
        self.save_button = QPushButton("保存")
        self.save_button.setProperty("class", "primary")
        self.save_button.clicked.connect(self._on_save)
        button_layout.addWidget(self.save_button)
        
        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.reject)
        button_layout.addWidget(self.cancel_button)
        
        main_layout.addLayout(button_layout)
    
    def _on_save(self):
        """保存设置"""
        new_role = self.role_combo.currentText()
        
        # 更新配置
        if "access_control" not in self.config:
            self.config["access_control"] = {}
        
        self.config["access_control"]["default_login_role"] = new_role
        
        # 保存到文件
        if self._save_config():
            QMessageBox.information(
                self, 
                "保存成功", 
                f"默认登录角色已设置为: {new_role}\n下次打开登录窗口时将自动选择此角色。"
            )
            self.accept()
