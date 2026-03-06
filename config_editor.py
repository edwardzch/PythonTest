# 文件路径: config_editor.py (已彻底修复回车键问题)

import sys
import json
import os
from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QScrollArea,
    QLabel, QPushButton, QLineEdit, QComboBox, QCheckBox, QTabWidget,
    QGroupBox, QDialogButtonBox, QMessageBox, QFileDialog, QTableWidget,
    QTableWidgetItem, QHeaderView, QSpinBox, QDoubleSpinBox, QSplitter,
    QListWidget, QListWidgetItem, QInputDialog
)

from PySide6.QtGui import QIcon, QAction, QKeySequence
from PySide6.QtCore import Qt, QTimer

from utils.app_utils import resource_path
from utils.app_utils import get_app_base_path
from utils.dynamic_config_builder import DynamicConfigBuilder
from utils.plugin_loader import find_driver_class, load_plugins_from_dir
import importlib

try:
    import pyvisa
    PYVISA_AVAILABLE = True
except ImportError:
    PYVISA_AVAILABLE = False

class ModbusSlaveEditor(QWidget):
    def __init__(self, initial_slaves=None):
        super().__init__()
        self.slaves = initial_slaves or {}
        self._init_ui()

    def _init_ui(self):
        # 主布局改为垂直
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        # 表格
        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(["设备名称 (英文)", "从站地址"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        # 移除滚动条，高度自适应
        self.table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        main_layout.addWidget(self.table)

        # 按钮布局 (水平)
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("添加设备")
        add_btn.clicked.connect(self._add_row)
        del_btn = QPushButton("删除选中")
        del_btn.clicked.connect(self._del_row)
        
        btn_layout.addWidget(add_btn)
        btn_layout.addWidget(del_btn)
        btn_layout.addStretch() 
        
        main_layout.addLayout(btn_layout)

        self._load_data()

    def _update_table_height(self):
        """根据行数自动调整表格高度"""
        row_count = self.table.rowCount()
        # 获取表头高度
        header_height = self.table.horizontalHeader().height()
        # 获取行高总和 (假设默认行高)
        row_height = self.table.verticalHeader().defaultSectionSize()
        total_height = header_height + (row_height * row_count) + 2 # +2 for borders
        
        # 设置最小高度和固定高度
        self.table.setMinimumHeight(total_height)
        self.table.setMaximumHeight(total_height)
        self.setMinimumHeight(total_height)

    def _load_data(self):
        self.table.setRowCount(0)
        for name, addr in self.slaves.items():
            self._add_row_item(name, addr)
        self._update_table_height()

    def _add_row(self):
        self._add_row_item("new_device", 1)
        self._update_table_height()

    def _add_row_item(self, name, addr):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(str(name)))
        self.table.setItem(row, 1, QTableWidgetItem(str(addr)))

    def _del_row(self):
        current_row = self.table.currentRow()
        if current_row >= 0:
            self.table.removeRow(current_row)
            self._update_table_height()

    def get_slaves(self):
        slaves = {}
        for row in range(self.table.rowCount()):
            name_item = self.table.item(row, 0)
            addr_item = self.table.item(row, 1)
            if name_item and addr_item:
                name = name_item.text().strip()
                try:
                    addr = int(addr_item.text().strip())
                    if name:
                        slaves[name] = addr
                except ValueError:
                    pass # Ignore invalid address
        return slaves

class ConfigEditor(QDialog):

    def __init__(self, parent, config_path, config_update_callback):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        self.setWindowTitle("配置编辑器")
        self.setWindowIcon(QIcon(resource_path('app_icon.ico')))
        self.setMinimumSize(800, 600)

        self.config_path = config_path
        self.config_update_callback = config_update_callback

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                self.config_data = json.load(f)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载配置文件失败: {e}")
            QTimer.singleShot(0, self.close)
            return

        self.psu_ids = ["PSU_A", "PSU_B"]
        self.editor_modified = False
        self.dynamic_builders = {} # Store builders to retrieve data later
        self.config_file_path = config_path  # 保存配置文件路径用于设备管理
        
        # 从父窗口获取 driver_plugins 用于设备管理
        if hasattr(parent, 'drivers'):
            self.driver_plugins = parent.drivers
        else:
            self.driver_plugins = {}
        
        self._init_widgets()
        # 已移除帮助菜单（self._create_menu_bar()）
        self._load_config_to_ui()
        self._add_save_shortcut()
        self._should_restore_maximized = False

    def closeEvent(self, event):
        if self.editor_modified:
            reply = QMessageBox.question(self, "关闭", "配置已修改，是否放弃更改并关闭？",
                                         QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
            if reply == QMessageBox.No: event.ignore(); return
        event.accept()

    def _init_widgets(self):
        main_layout = QVBoxLayout(self)
        # Menu bar is added via setMenuBar in _create_menu_bar
        
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)

        # 原有的硬编码 Tab（保留复杂功能）
        # self.tabs.addTab(self._create_power_tab(), "电源配置")  # 已迁移到动态 Tab
        # SPD4323X 已迁移到动态 Tab（使用 mode_switch 类型）
        # self.tabs.addTab(self._create_jlink_tab(), "JLink 设置")  # 已迁移到动态 Tab
        # self.tabs.addTab(self._create_multimeter_tab(), "万用表配置")  # 已迁移到动态 Tab
        # self.tabs.addTab(self._create_serial_tab(), "串口设置")  # 已迁移到动态 Tab
        self.tabs.addTab(self._create_database_tab(), "基础配置")
        # self.tabs.addTab(self._create_uniflash_tab(), "UniFlash 配置")  # 已迁移到动态 Tab
        
        # 动态加载驱动定义的配置 Tab（仅新增驱动）
        self._load_dynamic_driver_tabs()
        
        # self.tabs.addTab(self._create_path_tab(), "路径设置")

        self.button_box = QDialogButtonBox()

        # --- 【【【核心修复】】】 ---
        # 将 "保存" 按钮的角色从 AcceptRole 改为 ActionRole
        # AcceptRole 会导致按钮被回车键触发，ActionRole 则不会。
        self.save_button = self.button_box.addButton("保存", QDialogButtonBox.ActionRole)
        # --- --------------------- ---

        self.close_button = self.button_box.addButton("关闭", QDialogButtonBox.RejectRole)

        # 之前的 setDefault 和 setAutoDefault 都不再需要了，因为角色已经改变

        self.save_button.clicked.connect(self._save_config)
        self.close_button.clicked.connect(self.close)

        main_layout.addWidget(self.button_box)
        self._connect_all_widgets_to_mark_modified(self)

    def _add_save_shortcut(self):
        save_action = QAction(self)
        save_action.setShortcut(QKeySequence.Save)  # Ctrl+S
        save_action.triggered.connect(self._save_config)
        self.addAction(save_action)

    def _save_config(self):
        """只将UI内容保存到 config.json 文件，并更新主程序的内存变量。"""
        try:
            # 获取旧的数据库名称
            old_db_name = self.config_data.get('database_name', 'test_history')
            
            # 保存UI到配置
            self._save_ui_to_config()
            
            # 获取新的数据库名称
            new_db_name = self.config_data.get('database_name', 'test_history')
            
            # 如果数据库名称发生变化，则重命名数据库文件
            if old_db_name != new_db_name:
                old_db_path = os.path.join(get_app_base_path(), f'{old_db_name}.db')
                new_db_path = os.path.join(get_app_base_path(), f'{new_db_name}.db')
                
                # 检查新文件名是否已存在
                if os.path.exists(new_db_path):
                    reply = QMessageBox.question(
                        self, "数据库文件已存在", 
                        f"数据库文件 '{new_db_name}.db' 已存在。\n是否覆盖？",
                        QMessageBox.Yes | QMessageBox.No,
                        QMessageBox.No
                    )
                    if reply == QMessageBox.No:
                        return
                
                # 如果旧数据库文件存在，则重命名
                if os.path.exists(old_db_path):
                    try:
                        # 如果新文件存在且用户选择覆盖，先删除新文件
                        if os.path.exists(new_db_path):
                            os.remove(new_db_path)
                        
                        os.rename(old_db_path, new_db_path)
                        print(f"数据库文件已重命名: {old_db_name}.db -> {new_db_name}.db")
                        QMessageBox.information(
                            self, "数据库重命名成功", 
                            f"数据库文件已从 '{old_db_name}.db' 重命名为 '{new_db_name}.db'"
                        )
                    except Exception as e:
                        QMessageBox.warning(
                            self, "数据库重命名失败", 
                            f"无法重命名数据库文件: {e}\n配置仍将保存。"
                        )
            
            # 保存配置文件
            with open(self.config_path, 'w', encoding='utf-8') as f:
                json.dump(self.config_data, f, indent=4, ensure_ascii=False)

            if self.config_update_callback:
                self.config_update_callback(self.config_data)

            self.editor_modified = False
            self.setWindowTitle("配置编辑器")
            
            # 更新当前数据库信息显示
            self.current_db_info_label.setText(f"数据库文件: {new_db_name}.db")
            
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法保存配置文件: {e}")

    def _get_driver_schema(self, driver_name):
        """获取驱动类的配置 Schema"""
        # 首先尝试当前目录的 drivers
        app_base = get_app_base_path()
        drivers_dir = os.path.join(app_base, 'drivers')
        
        # 如果不存在，尝试上一级目录的 drivers（适配打包后的部署结构）
        if not os.path.exists(drivers_dir):
            parent_dir = os.path.dirname(app_base)
            drivers_dir = os.path.join(parent_dir, 'drivers')
        
        driver_class = find_driver_class(driver_name, drivers_dir)
        if driver_class and hasattr(driver_class, 'CONFIG_SCHEMA'):
            return driver_class.CONFIG_SCHEMA
        return {}

    # ... 以下所有 _create_... 和其他辅助方法保持不变 ...
    # (此处省略了您已有的、无需改动的代码)
    def _create_scrollable_area(self):
        scroll_area = QScrollArea();
        scroll_area.setWidgetResizable(True);
        content_container = QWidget()
        scroll_area.setWidget(content_container);
        content_layout = QVBoxLayout(content_container)
        content_layout.setAlignment(Qt.AlignTop);
        return scroll_area, content_layout

    def _create_path_tab(self):
        scroll_widget, content_layout = self._create_scrollable_area()
        path_group = QGroupBox("路径配置")
        path_layout = QGridLayout(path_group)

        path_layout.addWidget(QLabel("测试报告根路径:"), 0, 0)
        self.report_path_edit = QLineEdit()
        self.report_path_edit.setPlaceholderText("可填相对路径(如 'reports')或绝对路径")
        browse_button = QPushButton("浏览...")
        # 连接到新的、智能的浏览函数
        browse_button.clicked.connect(
            lambda: self._browse_and_set_path(self.report_path_edit, "选择测试报告根目录")
        )
        path_layout.addWidget(self.report_path_edit, 0, 1)
        path_layout.addWidget(browse_button, 0, 2)

        path_layout.setColumnStretch(1, 1)
        content_layout.addWidget(path_group)
        return scroll_widget

    def _browse_and_set_path(self, line_edit_widget, dialog_title, file_filter=None):
        """
        通用的、智能的路径浏览和设置函数。
        - 如果选择的路径在程序根目录下，则保存为相对路径。
        - 否则，保存为绝对路径。
        """
        # 决定是浏览文件还是文件夹
        if file_filter:
            path, _ = QFileDialog.getOpenFileName(self, dialog_title, get_app_base_path(), file_filter)
        else:
            path = QFileDialog.getExistingDirectory(self, dialog_title, get_app_base_path())

        if path:
            # 统一路径分隔符
            path = os.path.normpath(path)
            app_base = os.path.normpath(get_app_base_path())

            try:
                # 检查路径是否在应用根目录下
                relative_path = os.path.relpath(path, app_base)
                # 如果relpath的结果不包含 '..'，说明是子目录
                if not relative_path.startswith('..'):
                    final_path = relative_path
                    print(f"路径在程序目录下，已设置为相对路径: '{final_path}'")
                else:
                    final_path = path  # 是外部路径，使用绝对路径
                    print(f"路径在程序目录外，已设置为绝对路径: '{final_path}'")
            except ValueError:
                # 在Windows上，如果路径在不同驱动器，relpath会抛出ValueError
                final_path = path
                print(f"路径在不同驱动器，已设置为绝对路径: '{final_path}'")

            line_edit_widget.setText(final_path.replace("\\", "/"))

    def _create_database_tab(self):
        """创建数据库配置标签页"""
        scroll_widget, content_layout = self._create_scrollable_area()
        
        db_group = QGroupBox("数据库配置")
        db_layout = QVBoxLayout(db_group)
        
        # 说明文本
        info_label = QLabel(
            "数据库名称配置：\n"
            "• 每个测试设备可以使用独立的数据库文件\n"
            "• 修改名称后，原数据库文件将被重命名\n"
            "• 所有历史数据将保留不变\n"
            "• 数据库文件位于程序根目录下"
        )
        info_label.setStyleSheet("color: #888; padding: 10px; background-color: #2a2a2a; border-radius: 5px;")
        db_layout.addWidget(info_label)
        
        # 数据库名称输入
        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("数据库名称:"))
        self.database_name_edit = QLineEdit()
        self.database_name_edit.setPlaceholderText("test_history")
        self.database_name_edit.setToolTip("只输入文件名，不要包含 .db 扩展名")
        name_layout.addWidget(self.database_name_edit, 1)
        name_layout.addWidget(QLabel(".db"))
        db_layout.addLayout(name_layout)
        
        # 当前数据库信息
        current_info_group = QGroupBox("当前数据库信息")
        current_info_layout = QVBoxLayout(current_info_group)
        self.current_db_info_label = QLabel("数据库文件: test_history.db")
        self.current_db_info_label.setStyleSheet("padding: 5px;")
        current_info_layout.addWidget(self.current_db_info_label)
        db_layout.addWidget(current_info_group)
        
        content_layout.addWidget(db_group)
        
        # SN重复检查配置
        sn_check_group = QGroupBox("SN重复检查")
        sn_check_layout = QVBoxLayout(sn_check_group)
        
        sn_check_info = QLabel(
            '启用后，正常测试前会检查产品SN是否已在数据库中存在。\n'
            '如果SN已存在，将清空输入并提示"SN已重复"。\n'
            '注意：循环测试不受此设置影响。'
        )
        sn_check_info.setStyleSheet("color: #888; padding: 5px;")
        sn_check_layout.addWidget(sn_check_info)
        
        self.sn_duplicate_check_enabled = QCheckBox("启用SN重复检查")
        self.sn_duplicate_check_enabled.setToolTip("开启后，正常测试将拒绝已测试过的产品SN")
        sn_check_layout.addWidget(self.sn_duplicate_check_enabled)
        
        content_layout.addWidget(sn_check_group)
        
        # 黑匣子功能配置
        blackbox_group = QGroupBox("黑匣子功能")
        blackbox_layout = QVBoxLayout(blackbox_group)
        
        blackbox_info = QLabel(
            '启用后，每次测试结束时将自动获取测试板黑匣子记录，\n'
            '并生成独立的通讯日志报告（HTML格式）。\n'
            '需要在测试序列中添加 get_blackbox_content 步骤。'
        )
        blackbox_info.setStyleSheet("color: #888; padding: 5px;")
        blackbox_layout.addWidget(blackbox_info)
        
        self.blackbox_enabled_check = QCheckBox("启用黑匣子记录报告")
        self.blackbox_enabled_check.setToolTip("开启后，测试完成时自动获取并生成黑匣子通讯日志报告")
        blackbox_layout.addWidget(self.blackbox_enabled_check)
        
        content_layout.addWidget(blackbox_group)
        
        content_layout.addStretch()
        
        return scroll_widget

    def _create_jlink_tab(self):
        scroll_widget, content_layout = self._create_scrollable_area();
        global_group = QGroupBox("全局设置")
        global_layout = QGridLayout(global_group);
        global_layout.addWidget(QLabel("JLink.exe 路径:"), 0, 0)
        self.jlink_path_edit = QLineEdit();
        global_layout.addWidget(self.jlink_path_edit, 0, 1)

        browse_btn = QPushButton("浏览...")
        browse_btn.clicked.connect(lambda: self._browse_and_set_path(
            self.jlink_path_edit, "选择 JLink.exe", "Executable (*.exe);;All Files (*)"
        ))
        global_layout.addWidget(browse_btn, 0, 2)

        content_layout.addWidget(global_group);
        sn_group = QGroupBox("工位 JLink SN")
        sn_layout = QGridLayout(sn_group);
        self.jlink_station_edits = {}
        for i in range(1, 5):
            sn_layout.addWidget(QLabel(f"工位 {i}:"), i - 1, 0);
            edit = QLineEdit()
            sn_layout.addWidget(edit, i - 1, 1);
            self.jlink_station_edits[f"station_{i}"] = edit
        content_layout.addWidget(sn_group);
        return scroll_widget

    def _create_multimeter_tab(self):
        scroll_widget, content_layout = self._create_scrollable_area()
        dmm_group = QGroupBox("各工位万用表配置 (Per-Station DMM Configuration)")
        dmm_layout = QVBoxLayout(dmm_group)
        
        stations_cfg = self.config_data.get('stations', {})
        
        for i in range(1, 5):
            station_id = f"station_{i}"
            station_dmm_group = QGroupBox(f"工位 {i} 万用表")
            station_dmm_layout = QGridLayout(station_dmm_group)
            
            # 获取该工位的 DMM 配置
            # 注意：在旧配置中，DMM配置是直接散落在 station_X 下的 dmm_visa_address 等字段
            # 为了支持通用化，我们需要将它们聚合，或者 DynamicConfigBuilder 支持扁平化字典？
            # DynamicConfigBuilder 接收一个 config_data 字典。
            # 我们可以把 station_cfg 传进去，它会读取 schema 中定义的 key。
            # 这样是兼容的，因为 schema 中的 key (visa_address) 在 station_cfg 中可能不存在（旧的是 dmm_visa_address）
            # 等等，旧代码是 dmm_visa_address。
            # 但 Fluke8808A 的 Schema 定义的是 visa_address。
            # 这意味着我们需要做一层映射，或者迁移配置。
            # 为了简单起见，我们假设新的通用配置将使用嵌套字典 'dmm_config'，或者我们修改 Schema 里的 key 名字？
            # 修改 Schema key 名字不通用。
            # 最好是在 config.json 中，station_X 下面有一个 "dmm" 字段，里面存放 visa_address 等。
            # 为了保持兼容性，我们可以在加载时，把 dmm_visa_address 转换成 dmm_config['visa_address']
            # 保存时，再转回去？或者直接拥抱新结构。
            # 鉴于这是重构，我们拥抱新结构： stations -> station_X -> dmm -> { visa_address, ... }
            # 但为了兼容旧数据，我们需要在加载时处理一下。
            
            s_data = stations_cfg.get(station_id, {})
            dmm_config = s_data.get('dmm', {})
            
            # 兼容旧配置: 如果 dmm 为空，尝试从扁平字段读取
            if not dmm_config:
                if 'dmm_visa_address' in s_data:
                    dmm_config['visa_address'] = s_data['dmm_visa_address']
                if 'dmm_auto_connect' in s_data:
                    dmm_config['auto_connect_on_startup'] = s_data['dmm_auto_connect']
                if 'dmm_default_mode' in s_data:
                    dmm_config['default_mode'] = s_data['dmm_default_mode']

            driver_name = dmm_config.get('driver', 'Fluke8808A')
            schema = self._get_driver_schema(driver_name)
            
            if schema:
                builder = DynamicConfigBuilder(self)
                builder.build_ui(schema, station_dmm_layout, dmm_config)
                # Store builder with a unique key
                self.dynamic_builders[f"{station_id}_dmm"] = builder
            else:
                station_dmm_layout.addWidget(QLabel(f"未找到驱动 '{driver_name}' 的配置定义"))
                
            dmm_layout.addWidget(station_dmm_group)
            
        content_layout.addWidget(dmm_group)
        return scroll_widget

    def _create_serial_tab(self):
        scroll_widget, content_layout = self._create_scrollable_area();
        global_group = QGroupBox("全局串口模式")
        global_layout = QVBoxLayout(global_group);
        self.use_shared_port_check = QCheckBox("使用共享串口 (所有工位共用一个物理端口)")
        global_layout.addWidget(self.use_shared_port_check)
        content_layout.addWidget(global_group);
        
        # --- Shared Port ---
        self.shared_port_group = QGroupBox("共享串口配置 (Shared Port)")
        shared_layout = QGridLayout(self.shared_port_group);
        shared_layout.setColumnStretch(0, 0) # Label 列不拉伸
        shared_layout.setColumnStretch(1, 1) # Widget 列拉伸
        
        serial_cfg = self.config_data.get('serial_port_mode', {})
        shared_port_cfg = serial_cfg.get('shared_port_config', {})
        
        # 映射旧配置到新 Schema (ModbusCommunicator)
        # 旧: port, serial_params: {baudrate, ...}
        # 新: port, baudrate, ... (扁平化)
        # 我们需要构造一个扁平化的 config 字典给 builder
        shared_flat_config = shared_port_cfg.get('serial_params', {}).copy()
        shared_flat_config['port'] = shared_port_cfg.get('port', 'COM1')
        
        driver_name = shared_port_cfg.get('driver', 'ModbusCommunicator')
        schema = self._get_driver_schema(driver_name)

        
        if schema:
            builder = DynamicConfigBuilder(self)
            builder.build_ui(schema, shared_layout, shared_flat_config)
            self.dynamic_builders['shared_serial'] = builder
        else:
            shared_layout.addWidget(QLabel(f"未找到驱动 '{driver_name}' 的配置定义"))

        content_layout.addWidget(self.shared_port_group);
        
        # --- Global Modbus Configuration ---
        # 用户要求 Modbus 从站配置从工位配置里出来，作为全局配置
        modbus_group = QGroupBox("Modbus 从站设备配置 (全局)")
        modbus_layout = QVBoxLayout(modbus_group)
        
        # 加载初始数据：尝试从第一个工位读取，或者从全局读取（如果已迁移）
        # 这里我们读取 station_1 的配置作为默认显示
        stations_cfg = self.config_data.get('stations', {})
        initial_slaves = {}
        if 'station_1' in stations_cfg:
            initial_slaves = stations_cfg['station_1'].get('modbus_slaves', {})
        
        if not initial_slaves:
             initial_slaves = {
                "daq_board": 5, "servo_driver": 2, 
                "relay_board": 3, "analog_board": 4
            }
            
        self.global_modbus_editor = ModbusSlaveEditor(initial_slaves)
        modbus_layout.addWidget(self.global_modbus_editor)
        content_layout.addWidget(modbus_group)
        
        # --- Independent Ports ---
        
        # --- Independent Ports ---
        self.independent_ports_group = QGroupBox("独立工位串口配置 (Independent Ports)")
        ind_layout = QGridLayout(self.independent_ports_group);
        self.serial_station_widgets = {} # Still needed for modbus slaves? Yes.
        
        stations_cfg = self.config_data.get('stations', {})

        for i in range(1, 5):
            station_id = f"station_{i}"
            station_group = QGroupBox(f"工位 {i} (station_{i})");
            station_layout = QVBoxLayout(station_group)
            
            # 动态串口配置
            s_data = stations_cfg.get(station_id, {})
            # 同样需要扁平化
            s_flat_config = s_data.get('serial_params', {}).copy()
            s_flat_config['port'] = s_data.get('comm_port', f'COM{i+10}')
            
            driver_name = s_data.get('serial_driver', 'ModbusCommunicator')
            schema = self._get_driver_schema(driver_name)
            
            if schema:
                # 使用 QGridLayout 以便 builder 正常工作
                s_param_layout = QGridLayout()
                builder = DynamicConfigBuilder(self)
                builder.build_ui(schema, s_param_layout, s_flat_config)
                self.dynamic_builders[f"{station_id}_serial"] = builder
                station_layout.addLayout(s_param_layout)
            
            # Modbus Slaves 已移至全局，此处不再显示
            
            ind_layout.addWidget(station_group, (i - 1) % 2, (i - 1) // 2)
            
        content_layout.addWidget(self.independent_ports_group);
        self.use_shared_port_check.toggled.connect(self._toggle_serial_ui)
        self._toggle_serial_ui(False);
        return scroll_widget

    # _create_serial_param_widgets 已不再需要，删除


    def _create_power_tab(self):
        scroll_widget, content_layout = self._create_scrollable_area();
        global_group = QGroupBox("全局电源模式")
        global_layout = QVBoxLayout(global_group);
        global_layout.setContentsMargins(10, 10, 10, 10)
        # self.psu_sim_mode_check = QCheckBox("全局模拟模式 (Simulation Mode)") # 已移除
        self.use_independent_power_check = QCheckBox("电源独立模式")
        # global_layout.addWidget(self.psu_sim_mode_check) # 已移除
        global_layout.addWidget(self.use_independent_power_check)
        content_layout.addWidget(global_group)

        # 共享电源配置组
        self.shared_power_group = QWidget()
        shared_power_layout = QVBoxLayout(self.shared_power_group)
        shared_power_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(self.shared_power_group)

        # --- 动态生成 PSU 定义 ---
        psu_cfg = self.config_data.get('power_supplies', {})
        
        for psu_id in self.psu_ids:
            psu_group = QGroupBox(f"{psu_id} 配置")
            psu_layout = QGridLayout(psu_group)
            
            # 获取该 PSU 的驱动名称，默认为 RigolDP832
            current_psu_config = psu_cfg.get(psu_id, {})
            driver_name = current_psu_config.get('driver', 'RigolDP832')
            
            # 获取 Schema
            schema = self._get_driver_schema(driver_name)
            
            if schema:
                builder = DynamicConfigBuilder(self)
                builder.build_ui(schema, psu_layout, current_psu_config)
                self.dynamic_builders[psu_id] = builder
            else:
                psu_layout.addWidget(QLabel(f"未找到驱动 '{driver_name}' 的配置定义 (Schema)"))
            
            shared_power_layout.addWidget(psu_group)

        align_layout = QVBoxLayout();
        align_layout.setSpacing(15)
        startup_group = QGroupBox("电源基础配置 (启动时设置)");
        startup_layout = QGridLayout(startup_group)
        startup_headers = ["供电类型", "电源型号", "通道", "电压(V)", "电流(A)", "启动时启用"]
        for col, h in enumerate(startup_headers): startup_layout.addWidget(QLabel(h), 0, col, Qt.AlignCenter)
        self.power_startup_widgets = {};
        supply_types = {"battery_supply": "电池供电", "daq_supply": "采集卡供电"}
        for row, (key, name) in enumerate(supply_types.items(), 1):
            startup_layout.addWidget(QLabel(name), row, 0);
            psu_combo = QComboBox();
            psu_combo.addItems(self.psu_ids)
            ch_edit = QLineEdit();
            volt_edit = QLineEdit();
            curr_edit = QLineEdit();
            enable_check = QCheckBox()
            startup_layout.addWidget(psu_combo, row, 1);
            startup_layout.addWidget(ch_edit, row, 2)
            startup_layout.addWidget(volt_edit, row, 3);
            startup_layout.addWidget(curr_edit, row, 4)
            startup_layout.addWidget(enable_check, row, 5, Qt.AlignCenter);
            self.power_startup_widgets[key] = {'psu_id': psu_combo, 'channel': ch_edit, 'voltage': volt_edit,
                                               'current': curr_edit, 'enabled': enable_check}
        startup_layout.setColumnStretch(1, 1);
        startup_layout.setColumnStretch(2, 1);
        startup_layout.setColumnStretch(3, 1);
        startup_layout.setColumnStretch(4, 1)
        align_layout.addWidget(startup_group);
        mapping_group = QGroupBox("工位产品供电映射");
        mapping_layout = QGridLayout(mapping_group)
        mapping_headers = ["工位", "电源型号", "通道"];
        [mapping_layout.addWidget(QLabel(h), 0, col, Qt.AlignCenter) for col, h in enumerate(mapping_headers)]
        self.power_control_widgets = {}
        for i in range(1, 5):
            station_id = f"station_{i}";
            mapping_layout.addWidget(QLabel(f"工位 {i}"), i, 0)
            prod_psu = QComboBox();
            prod_psu.addItems(self.psu_ids);
            prod_ch = QLineEdit()
            mapping_layout.addWidget(prod_psu, i, 1);
            mapping_layout.addWidget(prod_ch, i, 2)
            self.power_control_widgets[station_id] = {'product': {'psu_id': prod_psu, 'channel': prod_ch}}
        mapping_layout.setColumnStretch(1, 1);
        mapping_layout.setColumnStretch(2, 1)
        align_layout.addWidget(mapping_group)
        shared_power_layout.addLayout(align_layout)

        # 独立工位电源配置组
        self.independent_power_group = QGroupBox("独立工位电源配置")
        ind_power_layout = QGridLayout(self.independent_power_group)
        self.independent_power_widgets = {}

        for i in range(1, 5):
            station_id = f"station_{i}"
            station_group = QGroupBox(f"工位 {i} (station_{i})")
            station_layout = QVBoxLayout(station_group)

            # VISA and Connection
            visa_layout = QHBoxLayout()
            visa_layout.addWidget(QLabel("VISA 地址:"))
            visa_edit = QLineEdit()
            visa_layout.addWidget(visa_edit, 1)
            auto_conn_check = QCheckBox("启动时连接")
            visa_layout.addWidget(auto_conn_check)
            station_layout.addLayout(visa_layout)

            # Channel Mapping
            mapping_group = QGroupBox("通道映射")
            mapping_layout = QGridLayout(mapping_group)
            mapping_layout.addWidget(QLabel("供电类型"), 0, 0)
            mapping_layout.addWidget(QLabel("通道"), 0, 1)

            supply_types = {
                'product': "产品供电",
                'battery': "电池供电",
                'daq': "采集卡供电"
            }
            
            station_mapping_widgets = {}
            for row, (key, name) in enumerate(supply_types.items(), 1):
                mapping_layout.addWidget(QLabel(name), row, 0)
                ch_edit = QLineEdit()
                ch_edit.setFixedWidth(80)
                mapping_layout.addWidget(ch_edit, row, 1)
                station_mapping_widgets[key] = {'channel': ch_edit}
            
            station_layout.addWidget(mapping_group)
            ind_power_layout.addWidget(station_group, (i - 1) % 2, (i - 1) // 2)

            self.independent_power_widgets[station_id] = {
                'visa_address': visa_edit,
                'auto_connect_on_startup': auto_conn_check,
                'mappings': station_mapping_widgets
            }

        content_layout.addWidget(self.independent_power_group)

        self.use_independent_power_check.toggled.connect(self._toggle_power_ui)
        self._toggle_power_ui(False)  # 【修复】初始状态设置

        # 【BUG修复】当电源的PSU ID变化时，也需要更新启动启用按钮的状态
        for key, widgets in self.power_startup_widgets.items():
            widgets['psu_id'].currentTextChanged.connect(self._initial_ui_state_update)

        return scroll_widget

    def _create_uniflash_tab(self):
        scroll_widget, content_layout = self._create_scrollable_area()
        group = QGroupBox("UniFlash 路径配置")
        layout = QGridLayout(group)
        
        # 获取 UniFlash 驱动的 Schema
        schema = self._get_driver_schema('UniFlashDriver')
        if schema:
            # 获取当前的 uniflash 配置
            uniflash_config = self.config_data.get('uniflash_config', {})
            
            builder = DynamicConfigBuilder(self)
            builder.build_ui(schema, layout, uniflash_config)
            self.dynamic_builders['uniflash'] = builder
        else:
            layout.addWidget(QLabel("未找到 UniFlashDriver，请检查 drivers 目录。"))
            
        content_layout.addWidget(group)
        return scroll_widget

    def _create_device_management_tab(self):
        """创建设备管理标签页 - 用于插件化设备管理"""
        scroll_widget, content_layout = self._create_scrollable_area()
        
        # 说明文字
        info_label = QLabel(
            "设备管理：在此添加、配置和管理硬件设备。\n"
            "新添加的设备会保存到 device_registry.json，无需修改主程序。"
        )
        info_label.setStyleSheet("color: #6c757d; font-style: italic; padding: 5px;")
        content_layout.addWidget(info_label)
        
        # 主布局：左侧设备列表 + 右侧配置面板
        main_splitter = QSplitter(Qt.Horizontal)
        
        # ========== 左侧：驱动列表和已注册设备 ==========
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        # 可用驱动列表
        driver_group = QGroupBox("可用驱动")
        driver_layout = QVBoxLayout(driver_group)
        self.driver_list = QListWidget()
        self._populate_driver_list()
        driver_layout.addWidget(self.driver_list)
        
        add_btn = QPushButton("添加选中驱动为新设备 →")
        add_btn.clicked.connect(self._on_add_device_from_driver)
        driver_layout.addWidget(add_btn)
        left_layout.addWidget(driver_group)
        
        # 已注册设备列表
        registered_group = QGroupBox("已注册设备")
        registered_layout = QVBoxLayout(registered_group)
        self.registered_device_list = QListWidget()
        self.registered_device_list.currentItemChanged.connect(self._on_device_selected)
        registered_layout.addWidget(self.registered_device_list)
        
        btn_layout = QHBoxLayout()
        remove_btn = QPushButton("删除")
        remove_btn.clicked.connect(self._on_remove_device)
        btn_layout.addWidget(remove_btn)
        registered_layout.addLayout(btn_layout)
        left_layout.addWidget(registered_group)
        
        main_splitter.addWidget(left_widget)
        
        # ========== 右侧：设备配置面板 ==========
        self.device_config_scroll = QScrollArea()
        self.device_config_scroll.setWidgetResizable(True)
        self.device_config_container = QWidget()
        self.device_config_layout = QVBoxLayout(self.device_config_container)
        self.device_config_layout.addWidget(QLabel("选择左侧设备查看配置"))
        self.device_config_layout.addStretch()
        self.device_config_scroll.setWidget(self.device_config_container)
        
        main_splitter.addWidget(self.device_config_scroll)
        main_splitter.setSizes([300, 500])
        
        content_layout.addWidget(main_splitter)
        
        # 加载已注册设备
        self._load_registered_devices()
        
        return scroll_widget

    def _populate_driver_list(self):
        """填充可用驱动列表（从 driver_plugins 获取有 DRIVER_META 的驱动）"""
        self.driver_list.clear()
        
        for plugin_name, plugin_module in self.driver_plugins.items():
            for attr_name in dir(plugin_module):
                if attr_name.startswith('_'):
                    continue
                attr = getattr(plugin_module, attr_name)
                if isinstance(attr, type) and hasattr(attr, 'DRIVER_META'):
                    meta = attr.DRIVER_META
                    display_name = meta.get('display_name', attr_name)
                    category = meta.get('category', '未分类')
                    
                    item = QListWidgetItem(f"{display_name} [{category}]")
                    item.setData(Qt.UserRole, attr_name)  # 保存类名
                    item.setData(Qt.UserRole + 1, meta)   # 保存元数据
                    self.driver_list.addItem(item)

    def _load_registered_devices(self):
        """加载已注册设备到列表"""
        self.registered_device_list.clear()
        
        # 从 device_registry.json 加载
        import os
        import json
        registry_path = os.path.join(os.path.dirname(self.config_file_path), 'device_registry.json')
        
        if os.path.exists(registry_path):
            try:
                with open(registry_path, 'r', encoding='utf-8') as f:
                    self.device_registry = json.load(f)
            except Exception as e:
                print(f"加载设备注册表失败: {e}")
                self.device_registry = {"devices": {}}
        else:
            self.device_registry = {"devices": {}}
        
        # 填充列表
        for device_id, device_def in self.device_registry.get('devices', {}).items():
            driver_name = device_def.get('driver', '未知驱动')
            enabled = device_def.get('enabled', True)
            status = "✓" if enabled else "✗"
            
            item = QListWidgetItem(f"{status} {device_id} ({driver_name})")
            item.setData(Qt.UserRole, device_id)
            self.registered_device_list.addItem(item)

    def _on_add_device_from_driver(self):
        """从选中的驱动创建新设备"""
        current_item = self.driver_list.currentItem()
        if not current_item:
            QMessageBox.warning(self, "提示", "请先选择一个驱动。")
            return
        
        driver_class_name = current_item.data(Qt.UserRole)
        meta = current_item.data(Qt.UserRole + 1)
        
        # 获取设备ID
        device_id, ok = QInputDialog.getText(
            self, "添加设备", 
            f"请输入设备ID（用于标识此设备）：\n驱动: {meta.get('display_name', driver_class_name)}",
            text=f"{driver_class_name.lower()}_1"
        )
        
        if not ok or not device_id.strip():
            return
        
        device_id = device_id.strip()
        
        # 检查ID是否已存在
        if device_id in self.device_registry.get('devices', {}):
            QMessageBox.warning(self, "错误", f"设备ID '{device_id}' 已存在。")
            return
        
        # 创建设备配置
        new_device = {
            "driver": driver_class_name,
            "enabled": True,
            "config": {
                "auto_connect_on_startup": False
            }
        }
        
        # 如果是多通道设备，添加通道映射
        channels = meta.get('channels', 0)
        if channels > 0:
            new_device['channel_mappings'] = {}
        
        # 保存到注册表
        if 'devices' not in self.device_registry:
            self.device_registry['devices'] = {}
        self.device_registry['devices'][device_id] = new_device
        
        self._save_device_registry()
        self._load_registered_devices()
        
        # 选中新添加的设备
        for i in range(self.registered_device_list.count()):
            item = self.registered_device_list.item(i)
            if item.data(Qt.UserRole) == device_id:
                self.registered_device_list.setCurrentItem(item)
                break
        
        self.editor_modified = True

    def _on_remove_device(self):
        """删除选中的设备"""
        current_item = self.registered_device_list.currentItem()
        if not current_item:
            return
        
        device_id = current_item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "确认删除", 
            f"确定要删除设备 '{device_id}' 吗？",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            if device_id in self.device_registry.get('devices', {}):
                del self.device_registry['devices'][device_id]
                self._save_device_registry()
                self._load_registered_devices()
                self._clear_device_config_panel()
                self.editor_modified = True

    def _on_device_selected(self, current, previous):
        """当选中设备时，显示其配置"""
        if not current:
            return
        
        device_id = current.data(Qt.UserRole)
        device_def = self.device_registry.get('devices', {}).get(device_id, {})
        
        if not device_def:
            return
        
        self._show_device_config(device_id, device_def)

    def _show_device_config(self, device_id, device_def):
        """显示设备配置面板"""
        # 清空现有内容
        self._clear_device_config_panel()
        
        driver_name = device_def.get('driver', '')
        config = device_def.get('config', {})
        
        # 标题
        title = QLabel(f"设备配置: {device_id}")
        title.setStyleSheet("font-weight: bold; font-size: 14px;")
        self.device_config_layout.addWidget(title)
        
        # 启用/禁用
        enabled_check = QCheckBox("启用此设备")
        enabled_check.setChecked(device_def.get('enabled', True))
        enabled_check.stateChanged.connect(
            lambda state, did=device_id: self._update_device_enabled(did, state == Qt.Checked)
        )
        self.device_config_layout.addWidget(enabled_check)
        
        # 获取驱动的 CONFIG_SCHEMA
        schema = self._get_driver_schema(driver_name)
        if schema:
            config_group = QGroupBox("连接配置")
            config_layout = QGridLayout(config_group)
            
            builder = DynamicConfigBuilder(self)
            builder.build_ui(schema, config_layout, config)
            
            # 保存 builder 引用用于保存配置
            self.current_device_builder = builder
            self.current_device_id = device_id
            
            self.device_config_layout.addWidget(config_group)
            
            # 保存按钮
            save_btn = QPushButton("保存设备配置")
            save_btn.clicked.connect(lambda: self._save_device_config(device_id))
            self.device_config_layout.addWidget(save_btn)
        
        self.device_config_layout.addStretch()

    def _clear_device_config_panel(self):
        """清空设备配置面板"""
        while self.device_config_layout.count():
            child = self.device_config_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()
        self.current_device_builder = None
        self.current_device_id = None

    def _update_device_enabled(self, device_id, enabled):
        """更新设备启用状态"""
        if device_id in self.device_registry.get('devices', {}):
            self.device_registry['devices'][device_id]['enabled'] = enabled
            self._save_device_registry()
            self._load_registered_devices()
            self.editor_modified = True

    def _save_device_config(self, device_id):
        """保存当前设备配置"""
        if not hasattr(self, 'current_device_builder') or not self.current_device_builder:
            return
        
        new_config = self.current_device_builder.get_config()
        
        if device_id in self.device_registry.get('devices', {}):
            self.device_registry['devices'][device_id]['config'] = new_config
            self._save_device_registry()
            QMessageBox.information(self, "成功", f"设备 '{device_id}' 配置已保存。")
            self.editor_modified = True

    def _save_device_registry(self):
        """保存设备注册表到 JSON 文件"""
        import os
        import json
        registry_path = os.path.join(os.path.dirname(self.config_file_path), 'device_registry.json')
        
        try:
            with open(registry_path, 'w', encoding='utf-8') as f:
                json.dump(self.device_registry, f, ensure_ascii=False, indent=2)
            print(f"设备注册表已保存: {registry_path}")
        except Exception as e:
            QMessageBox.warning(self, "保存失败", f"保存设备注册表失败: {e}")

    def _load_dynamic_driver_tabs(self):
        """从 drivers 目录动态加载驱动定义的配置 Tab"""
        # 存储动态 Tab 的 builders，用于保存配置
        if not hasattr(self, 'dynamic_tab_builders'):
            self.dynamic_tab_builders = {}
        
        # 优先使用主程序启动时已预加载的驱动模块（避免重复加载导致延迟）
        if self.driver_plugins:
            loaded_drivers = self.driver_plugins
            print(f"使用预加载的驱动模块 ({len(loaded_drivers)} 个)")
        else:
            # 降级：如果没有预加载，则动态加载
            app_base = get_app_base_path()
            drivers_dir = os.path.join(app_base, 'drivers')
            
            if not os.path.exists(drivers_dir):
                parent_dir = os.path.dirname(app_base)
                drivers_dir = os.path.join(parent_dir, 'drivers')
            
            if not os.path.exists(drivers_dir):
                print("drivers 目录不存在，跳过动态 Tab 加载")
                return
            
            loaded_drivers = load_plugins_from_dir(drivers_dir)
            print(f"动态加载驱动模块 ({len(loaded_drivers)} 个)")
        
        for module_name, module in loaded_drivers.items():
            # 遍历模块中的所有类
            for attr_name in dir(module):
                if attr_name.startswith('_'):
                    continue
                attr = getattr(module, attr_name)
                if not isinstance(attr, type):
                    continue
                
                # 检查是否有 CONFIG_TAB 定义
                if not hasattr(attr, 'CONFIG_TAB') or not hasattr(attr, 'CONFIG_SCHEMA'):
                    continue
                
                config_tab = attr.CONFIG_TAB
                config_schema = attr.CONFIG_SCHEMA
                
                tab_name = config_tab.get('tab_name', attr_name)
                config_key = config_tab.get('config_key', attr_name.lower() + '_config')
                
                # 跳过已有硬编码 Tab 的驱动（避免重复）
                skip_drivers = [
                    # 所有驱动已迁移到动态 Tab
                ]
                if attr_name in skip_drivers:
                    print(f"跳过已有硬编码 Tab 的驱动: {attr_name}")
                    continue
                mode = config_tab.get('mode', 'shared')  # 'shared' 或 'per_station'
                
                print(f"加载动态 Tab: {tab_name} (key={config_key}, mode={mode})")
                
                # 创建 Tab
                tab_widget = self._create_dynamic_tab(
                    tab_name, config_key, config_schema, mode
                )
                self.tabs.addTab(tab_widget, tab_name)
    
    def _create_dynamic_tab(self, tab_name, config_key, schema, mode):
        """创建一个动态配置 Tab"""
        scroll_widget, content_layout = self._create_scrollable_area()
        
        if mode == 'shared':
            # 共享模式：所有工位共用一个配置
            group = QGroupBox(f"{tab_name} 配置")
            layout = QGridLayout(group)
            
            # 获取当前配置
            current_config = self.config_data.get(config_key, {})
            
            builder = DynamicConfigBuilder(self)
            builder.build_ui(schema, layout, current_config)
            
            self.dynamic_tab_builders[config_key] = {
                'mode': 'shared',
                'builder': builder
            }
            
            content_layout.addWidget(group)
            
        elif mode == 'per_station':
            # 独立模式：每个工位独立配置（固定 4 工位）
            station_count = 4  # 固定为 4 工位
            
            # 添加说明
            info_label = QLabel(f"每个工位独立配置 {tab_name}")
            info_label.setStyleSheet("color: #6c757d; font-style: italic;")
            content_layout.addWidget(info_label)
            
            # 存储每个工位的 builder
            station_builders = {}
            
            # 使用 2x2 网格布局（上面12，下面34）
            grid_container = QWidget()
            grid_layout = QGridLayout(grid_container)
            grid_layout.setSpacing(10)
            
            for i in range(1, station_count + 1):
                station_id = f"station_{i}"
                station_group = QGroupBox(f"工位 {i}")
                station_layout = QGridLayout(station_group)
                
                # 从 stations -> station_X -> config_key 获取配置
                stations_cfg = self.config_data.get('stations', {})
                station_cfg = stations_cfg.get(station_id, {})
                current_config = station_cfg.get(config_key, {})
                
                builder = DynamicConfigBuilder(self)
                builder.build_ui(schema, station_layout, current_config)
                station_builders[station_id] = builder
                
                # 2x2 布局：行 = (i-1)//2, 列 = (i-1)%2
                row = (i - 1) // 2
                col = (i - 1) % 2
                grid_layout.addWidget(station_group, row, col)
            
            content_layout.addWidget(grid_container)
            self.dynamic_tab_builders[config_key] = {
                'mode': 'per_station',
                'builders': station_builders
            }
        
        content_layout.addStretch()
        return scroll_widget


    def _create_spd4323x_tab(self):
        """创建 SPD4323X 四通道程控电源配置标签页"""
        scroll_widget, content_layout = self._create_scrollable_area()
        
        # 初始化 SPD4323X 相关的widgets存储
        self.spd4323x_widgets = {}
        
        # ========== 全局模式选择 ==========
        mode_group = QGroupBox("SPD4323X 电源模式")
        mode_layout = QVBoxLayout(mode_group)
        
        self.spd4323x_independent_mode = QCheckBox("独立模式（每个工位独立的 SPD4323X）")
        self.spd4323x_independent_mode.setToolTip(
            "勾选：每个工位配置一台独立的 SPD4323X\n"
            "不勾选：所有工位共用一台 SPD4323X，4个通道分别对应4个工位"
        )
        mode_layout.addWidget(self.spd4323x_independent_mode)
        content_layout.addWidget(mode_group)
        
        # ========== 共享模式配置 (一台电源，4通道对应4工位) ==========
        self.spd4323x_shared_group = QGroupBox("共享模式配置 (一台 SPD4323X)")
        shared_layout = QVBoxLayout(self.spd4323x_shared_group)
        
        # VISA 地址选择
        visa_layout = QHBoxLayout()
        visa_layout.addWidget(QLabel("VISA 地址:"))
        self.spd4323x_shared_visa_combo = QComboBox()
        self.spd4323x_shared_visa_combo.setEditable(True)
        self.spd4323x_shared_visa_combo.setMinimumWidth(350)
        visa_layout.addWidget(self.spd4323x_shared_visa_combo, 1)
        
        refresh_btn = QPushButton("刷新")
        refresh_btn.setFixedWidth(60)
        refresh_btn.clicked.connect(lambda: self._refresh_visa_resources(self.spd4323x_shared_visa_combo))
        visa_layout.addWidget(refresh_btn)
        
        self.spd4323x_shared_auto_connect = QCheckBox("启动时连接")
        visa_layout.addWidget(self.spd4323x_shared_auto_connect)
        shared_layout.addLayout(visa_layout)
        
        # 通道-工位映射表格
        mapping_group = QGroupBox("通道-工位映射")
        mapping_layout = QGridLayout(mapping_group)
        
        # 表头
        headers = ["工位", "对应通道", "设置电压(V)", "设置电流(A)", "启动时打开"]
        for col, header in enumerate(headers):
            lbl = QLabel(header)
            lbl.setStyleSheet("font-weight: bold;")
            mapping_layout.addWidget(lbl, 0, col, Qt.AlignCenter)
        
        self.spd4323x_shared_channel_widgets = {}
        for i in range(1, 5):
            station_id = f"station_{i}"
            row = i
            
            # 工位标签
            mapping_layout.addWidget(QLabel(f"工位 {i}"), row, 0)
            
            # 通道选择
            ch_combo = QComboBox()
            ch_combo.addItems(["CH1", "CH2", "CH3", "CH4"])
            ch_combo.setCurrentIndex(i - 1)  # 默认 station_1 -> CH1
            mapping_layout.addWidget(ch_combo, row, 1)
            
            # 电压设置
            volt_spin = QDoubleSpinBox()
            volt_spin.setRange(0, 32)
            volt_spin.setDecimals(2)
            volt_spin.setValue(5.0)
            volt_spin.setSuffix(" V")
            mapping_layout.addWidget(volt_spin, row, 2)
            
            # 电流设置
            curr_spin = QDoubleSpinBox()
            curr_spin.setRange(0, 3.2)
            curr_spin.setDecimals(3)
            curr_spin.setValue(1.0)
            curr_spin.setSuffix(" A")
            mapping_layout.addWidget(curr_spin, row, 3)
            
            # 启动时打开
            enable_check = QCheckBox()
            mapping_layout.addWidget(enable_check, row, 4, Qt.AlignCenter)
            
            self.spd4323x_shared_channel_widgets[station_id] = {
                'channel': ch_combo,
                'voltage': volt_spin,
                'current': curr_spin,
                'enable_on_startup': enable_check
            }
        
        shared_layout.addWidget(mapping_group)
        content_layout.addWidget(self.spd4323x_shared_group)
        
        # ========== 独立模式配置 (每工位一台电源) ==========
        self.spd4323x_independent_group = QGroupBox("独立模式配置 (每工位独立 SPD4323X)")
        ind_layout = QGridLayout(self.spd4323x_independent_group)
        
        self.spd4323x_independent_widgets = {}
        
        for i in range(1, 5):
            station_id = f"station_{i}"
            
            # 工位组
            station_group = QGroupBox(f"工位 {i}")
            station_layout = QVBoxLayout(station_group)
            
            # VISA 地址行
            visa_row = QHBoxLayout()
            visa_row.addWidget(QLabel("VISA:"))
            visa_combo = QComboBox()
            visa_combo.setEditable(True)
            visa_combo.setMinimumWidth(280)
            visa_row.addWidget(visa_combo, 1)
            
            refresh_btn = QPushButton("刷新")
            refresh_btn.setFixedWidth(50)
            refresh_btn.clicked.connect(lambda checked, combo=visa_combo: self._refresh_visa_resources(combo))
            visa_row.addWidget(refresh_btn)
            
            auto_conn = QCheckBox("启动时连接")
            visa_row.addWidget(auto_conn)
            station_layout.addLayout(visa_row)
            
            # 4通道配置
            ch_group = QGroupBox("通道配置")
            ch_grid = QGridLayout(ch_group)
            
            # 表头
            ch_grid.addWidget(QLabel("通道"), 0, 0)
            ch_grid.addWidget(QLabel("电压(V)"), 0, 1)
            ch_grid.addWidget(QLabel("电流(A)"), 0, 2)
            ch_grid.addWidget(QLabel("启动打开"), 0, 3)
            
            channel_widgets = {}
            for ch in range(1, 5):
                ch_row = ch
                ch_grid.addWidget(QLabel(f"CH{ch}"), ch_row, 0)
                
                volt = QDoubleSpinBox()
                volt.setRange(0, 32)
                volt.setDecimals(2)
                volt.setValue(5.0)
                ch_grid.addWidget(volt, ch_row, 1)
                
                curr = QDoubleSpinBox()
                curr.setRange(0, 3.2)
                curr.setDecimals(3)
                curr.setValue(1.0)
                ch_grid.addWidget(curr, ch_row, 2)
                
                enable = QCheckBox()
                ch_grid.addWidget(enable, ch_row, 3, Qt.AlignCenter)
                
                channel_widgets[str(ch)] = {
                    'voltage': volt,
                    'current': curr,
                    'enable_on_startup': enable
                }
            
            station_layout.addWidget(ch_group)
            
            # 放入网格 (2x2布局)
            row_pos = (i - 1) // 2
            col_pos = (i - 1) % 2
            ind_layout.addWidget(station_group, row_pos, col_pos)
            
            self.spd4323x_independent_widgets[station_id] = {
                'visa_combo': visa_combo,
                'auto_connect': auto_conn,
                'channels': channel_widgets
            }
        
        content_layout.addWidget(self.spd4323x_independent_group)
        
        # 连接模式切换信号
        self.spd4323x_independent_mode.toggled.connect(self._toggle_spd4323x_mode)
        self._toggle_spd4323x_mode(False)  # 默认共享模式
        
        # 初次刷新 VISA 资源
        QTimer.singleShot(100, lambda: self._refresh_visa_resources(self.spd4323x_shared_visa_combo))
        
        return scroll_widget

    def _refresh_visa_resources(self, combo_box):
        """刷新指定 ComboBox 的 VISA 资源列表"""
        if not PYVISA_AVAILABLE:
            QMessageBox.warning(self, "警告", "pyvisa 未安装，无法扫描 VISA 资源。")
            return
        
        try:
            rm = pyvisa.ResourceManager()
            resources = rm.list_resources()
            
            current_text = combo_box.currentText()
            combo_box.clear()
            combo_box.addItems(list(resources))
            
            # 尝试恢复之前选中的项
            if current_text:
                index = combo_box.findText(current_text)
                if index >= 0:
                    combo_box.setCurrentIndex(index)
                else:
                    combo_box.setEditText(current_text)
            
            if not resources:
                QMessageBox.information(self, "扫描结果", "未找到任何 VISA 资源。")
        except Exception as e:
            QMessageBox.warning(self, "扫描失败", f"扫描 VISA 资源时出错: {e}")

    def _toggle_spd4323x_mode(self, use_independent):
        """切换 SPD4323X 共享/独立模式的UI显示"""
        self.spd4323x_shared_group.setVisible(not use_independent)
        self.spd4323x_independent_group.setVisible(use_independent)


    def _update_startup_enable_state(self, psu_id, is_checked):
        """ 根据“启动时连接”的状态，更新“启动时启用”复选框的可用性。 """
        for key, widgets in self.power_startup_widgets.items():
            if widgets['psu_id'].currentText() == psu_id:
                widgets['enabled'].setEnabled(is_checked)
                if not is_checked:
                    widgets['enabled'].setChecked(False)

    def _toggle_serial_ui(self, use_shared):
        """已弃用 - 串口配置现在由动态 Tab 处理"""
        pass

    def _toggle_power_ui(self, use_independent):
        """已弃用 - 电源配置现在由动态 Tab 处理"""
        pass

    def _initial_ui_state_update(self):
        """在UI加载后，根据当前配置初始化所有依赖控件的状态。"""
        # 1. 更新电源启动按钮的状态
        # 注意：由于现在是动态生成，我们可能需要从 builder 中获取 auto_connect_on_startup 的状态
        # 但 builder 的 get_config() 返回的是值。
        # 为了简化，这里暂时不自动联动“启动时启用”按钮的状态，或者需要更复杂的逻辑来查找 CheckBox。
        pass

    def _mark_modified(self, *args):
        if not self.editor_modified: self.editor_modified = True; self.setWindowTitle(self.windowTitle() + " *")

    def _connect_all_widgets_to_mark_modified(self, parent_widget):
        for widget in parent_widget.findChildren(QLineEdit): widget.textChanged.connect(self._mark_modified)
        for widget in parent_widget.findChildren(QComboBox): widget.currentTextChanged.connect(self._mark_modified)
        for widget in parent_widget.findChildren(QCheckBox): widget.toggled.connect(self._mark_modified)

    def _load_config_to_ui(self):
        """加载配置到 UI - 简化版（只处理非动态 Tab）"""
        for widget in self.findChildren(QWidget):
            try:
                widget.blockSignals(True)
            except RuntimeError:
                pass
        
        # 加载数据库配置
        database_name = self.config_data.get('database_name', 'test_history')
        self.database_name_edit.setText(database_name)
        self.current_db_info_label.setText(f"数据库文件: {database_name}.db")
        
        # 加载 SN 重复检查配置
        sn_check_cfg = self.config_data.get('sn_duplicate_check', {})
        self.sn_duplicate_check_enabled.setChecked(sn_check_cfg.get('enabled', False))
        
        # 加载黑匣子配置
        blackbox_cfg = self.config_data.get('blackbox_config', {})
        self.blackbox_enabled_check.setChecked(blackbox_cfg.get('enabled', False))
        
        # JLink 配置已迁移到动态 Tab，由 DynamicConfigBuilder 自动加载
        
        # 动态 Tab 的配置已由 DynamicConfigBuilder 在 build_ui 时自动加载
        
        QTimer.singleShot(0, self._restore_signals_and_update_ui)

    def _restore_signals_and_update_ui(self):
        for widget in self.findChildren(QWidget):
            try:
                widget.blockSignals(False)
            except RuntimeError:
                pass
        
        self._initial_ui_state_update() # 【BUG修复】加载配置后，立即更新一次UI状态

        self.editor_modified = False;
        self.setWindowTitle("配置编辑器")

    def _save_ui_to_config(self):
        """保存 UI 配置到 config_data - 简化版（只处理非动态 Tab + 动态 Tab）"""
        
        # Helper to ensure nested dictionaries exist before setting a value
        def set_nested(keys, value):
            d = self.config_data
            for key in keys[:-1]:
                d = d.setdefault(key, {})
            d[keys[-1]] = value

        # 保存数据库名称
        database_name = self.database_name_edit.text().strip()
        if not database_name:
            database_name = 'test_history'
        self.config_data['database_name'] = database_name

        # 保存 SN 重复检查配置
        set_nested(['sn_duplicate_check', 'enabled'], self.sn_duplicate_check_enabled.isChecked())
        
        # 保存黑匣子配置
        set_nested(['blackbox_config', 'enabled'], self.blackbox_enabled_check.isChecked())

        # JLink 配置已迁移到动态 Tab，由 dynamic_tab_builders 统一保存
        
        # 保存动态加载的驱动 Tab 配置（核心）
        if hasattr(self, 'dynamic_tab_builders'):
            for config_key, tab_info in self.dynamic_tab_builders.items():
                mode = tab_info.get('mode', 'shared')
                
                if mode == 'shared':
                    # 共享模式：直接保存到顶层 config_key
                    builder = tab_info.get('builder')
                    if builder:
                        set_nested([config_key], builder.get_config())
                
                elif mode == 'per_station':
                    # 独立模式：保存到 stations -> station_X -> config_key
                    builders = tab_info.get('builders', {})
                    for station_id, builder in builders.items():
                        if builder:
                            set_nested(['stations', station_id, config_key], builder.get_config())
        
        # 【关键修复】同步串口配置到 stations.station_X.comm_port（测试引擎实际读取的位置）
        serial_config = self.config_data.get('serial_config', {})
        serial_mode_config = serial_config.get('serial_mode', {})
        mode = serial_mode_config.get('mode', 'shared')
        
        if mode == 'independent' or serial_mode_config.get('use_independent_mode', False):
            # 独立模式：从 independent_configs 读取每个工位的串口
            independent_configs = serial_mode_config.get('independent_configs', {})
            for station_id, station_serial_config in independent_configs.items():
                port = station_serial_config.get('port', '')
                if port:
                    set_nested(['stations', station_id, 'comm_port'], port)
        else:
            # 共享模式：所有工位使用相同的串口
            shared_config = serial_mode_config.get('shared_config', {})
            shared_port = shared_config.get('port', '')
            if shared_port:
                for i in range(1, 5):  # 假设最多4个工位
                    station_id = f"station_{i}"
                    set_nested(['stations', station_id, 'comm_port'], shared_port)

        # 【关键修复】同步 DMM 配置到 stations.station_X 的旧字段
        dmm_config = self.config_data.get('dmm_config', {})
        dmm_mode_config = dmm_config.get('dmm_mode', {})
        dmm_mode = dmm_mode_config.get('mode', 'shared')

        if dmm_mode == 'independent' or dmm_mode_config.get('use_independent_mode', False):
            ind_cfgs = dmm_mode_config.get('independent_configs', {})
            for station_id, ind_cfg in ind_cfgs.items():
                visa_settings = ind_cfg.get('visa_settings', {})
                if isinstance(visa_settings, dict):
                    set_nested(['stations', station_id, 'dmm_visa_address'],
                               visa_settings.get('visa_address', ''))
                    set_nested(['stations', station_id, 'dmm_auto_connect'],
                               visa_settings.get('auto_connect_on_startup', False))
                set_nested(['stations', station_id, 'dmm_default_mode'],
                           ind_cfg.get('default_mode', 'DCV'))
        else:
            shared_cfg = dmm_mode_config.get('shared_config', {})
            visa_settings = shared_cfg.get('visa_settings', {})
            if isinstance(visa_settings, dict):
                visa_addr = visa_settings.get('visa_address', '')
                auto_conn = visa_settings.get('auto_connect_on_startup', False)
                default_mode = shared_cfg.get('default_mode', 'DCV')
                for i in range(1, 5):
                    station_id = f"station_{i}"
                    set_nested(['stations', station_id, 'dmm_visa_address'], visa_addr)
                    set_nested(['stations', station_id, 'dmm_auto_connect'], auto_conn)
                    set_nested(['stations', station_id, 'dmm_default_mode'], default_mode)

    def _convert_params_to_types(self, params_dict):
        converted = {};
        for key, value in params_dict.items():
            try:
                if key in ['baudrate', 'bytesize', 'stopbits']:
                    converted[key] = int(value)
                elif key == 'timeout':
                    converted[key] = float(value)
                else:
                    converted[key] = value
            except (ValueError, TypeError):
                defaults = {'baudrate': 9600, 'bytesize': 8, 'stopbits': 1, 'timeout': 0.2};
                converted[key] = defaults.get(key, value)
        return converted
