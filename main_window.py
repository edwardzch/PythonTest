# 文件路径: main_windows.py (未保存提示终极修复版 - 完整代码)

import sys
import json
import threading
import time
import os
import subprocess
import webbrowser
import copy
import importlib.util


from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QGridLayout, QMessageBox, QFileDialog,
    QMenu, QInputDialog, QLineEdit, QDialog
)
from PySide6.QtCore import QTimer, QThreadPool, Qt, Slot
from PySide6.QtGui import QAction, QIcon, QPixmap, QColor, QActionGroup

# --- 原有模块 ---
from utils.app_utils import resource_path, get_app_base_path
from utils.permissions import require_permission, REGISTERED_PERMISSIONS
from test_station import TestStation
from hardware_manager import HardwareManager
from sequence_editor import SequenceEditor
from config_editor import ConfigEditor
from help_dialog import HelpDialog
from utils.splash_screen import SplashScreen
from cycle_test_dialog import CycleTestDialog, CycleTestControlDialog
from cycle_test_controller import CycleTestController
from report_generator import ReportGenerator
from permission_manager_dialog import PermissionManagerDialog
from login_dialog import LoginDialog
from login_settings_dialog import LoginSettingsDialog
from sniffer_dialog import SnifferDialog
import stats_app # Import the stats app module
import threading # Import threading module
from thimble_manager import ThimbleManager
from thimble_tracker_dialog import ThimbleTrackerDialog
from order_estimation_dialog import OrderEstimationDialog
from consumable_manager import get_consumable_manager
from cable_swap_dialog import CableSwapDialog
from cable_scan_dialog import CableScanDialog
import pogo_history_report

# --- 重构后新增的模块 ---
from constants import DEFAULT_SEQUENCE_DATA, STATUS_STYLES
from station_frame import StationFrame
from ui_components import COLOR_HIGHLIGHT_BG, show_scrollable_warning
from constants import APP_VERSION

# 导入全局结果存储
from test_engine import _INTERACTION_RESULTS


class TestApp(QMainWindow):
    def __init__(self, splash_screen=None, user_info=None, test_modules=None, drivers=None):
        super().__init__()
        self.user_info = user_info
        self.splash_screen = splash_screen
        self.test_modules = test_modules if test_modules is not None else {}
        self.drivers = drivers if drivers is not None else {}
        self.setWindowIcon(QIcon(resource_path('app_icon.ico')))
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.sequence_editor_instance, self.config_editor_instance, self.help_dialog_instance, self.permission_manager_instance, self.login_settings_instance = None, None, None, None, None
        self.sniffer_dialog_instances = {}  # 改为字典，管理每个工位的独立抓包窗口
        self.station_frames = {};
        self.global_config = {};
        self.stop_all_event = threading.Event()
        self.hardware_manager = None;
        self.ordered_station_ids = [];
        self.sequence_data = []
        self.current_sequence_file_path = "";
        self.is_sequence_modified = False
        self.stats_server_thread = None # Add this line
        self.stats_browser_opening = False  # Flag to prevent duplicate browser opening
        self.thimble_manager = ThimbleManager()
        self.thimble_tracker_dialog_instance = None
        self.current_work_order = ""  # 全局当前工单号
        self.current_work_order_qty = 0  # 【新增】全局工单目标数量
        
        # 【新增】跨工位全局SN追踪
        # 用于跨工位防重复计数和1分钟复测通过抵消
        self.global_sn_test_history = {}  # {sn: {'status': 'FAIL', 'time': timestamp, 'station_id': station_id, 'db_record_id': id}}
        self.global_counted_sns = set()   # 已计入统计的SN集合 (用于唯一SN跨工位去重)
        
        if not self.load_config(): QTimer.singleShot(0, self.close); return
        self._sync_permissions_config() # <-- Add this call
        if self.splash_screen:
            self.splash_screen.set_message("初始化硬件管理器...")
        self.hardware_manager = HardwareManager(self.global_config, self.drivers)
        if self.splash_screen:
            self.splash_screen.set_message("连接自动连接设备...")
        startup_errors = self.hardware_manager.load_and_connect_auto_devices()
        if startup_errors:
            error_details = "\n\n- " + "\n\n- ".join(startup_errors)
            show_scrollable_warning(self, "硬件连接警告", f"启动时以下硬件未能成功连接，相关功能可能受限:\n{error_details}")
        if self.splash_screen:
            self.splash_screen.set_message("初始化UI...")
        self._init_ui();
        self._create_menu();
        self.rebuild_ui_for_station_count();
        self.update_title()

        # Display logged-in user in status bar
        if self.user_info:
            user_display = f"{self.user_info.get('name', '')} {self.user_info['id']}" if self.user_info.get('name') else self.user_info['id']
            self.statusBar().showMessage(f"当前用户: {user_display}", 0)

    def _init_ui(self):
        self.central_widget = QWidget();
        self.main_layout = QGridLayout(self.central_widget);
        self.setCentralWidget(self.central_widget)

    def _create_menu(self):
        menu_bar = self.menuBar();
        
        # 增加菜单栏字体大小 (+12)
        font_size = menu_bar.font().pointSize()
        if font_size <= 0: font_size = 9
        new_size = font_size + 4
        
        menu_bar.setStyleSheet(f"""
            QMenuBar {{ font-size: {new_size}pt; }}
            QMenuBar::item {{ font-size: {new_size}pt; }}
            QMenu {{ font-size: {new_size}pt; }}
            QMenu::item {{ font-size: {new_size}pt; }}
        """)
        
        file_menu = menu_bar.addMenu("文件");
        edit_menu = menu_bar.addMenu("编辑");
        tools_menu = menu_bar.addMenu("工具")
        about_menu = menu_bar.addMenu("关于");

        # --- 文件菜单 ---
        new_action = file_menu.addAction("新建序列", self.new_sequence_file);
        new_action.setEnabled(self.has_permission('file_new'))

        file_menu.addAction("打开序列", self.load_sequence_from_file); # Opening is always allowed

        save_action = file_menu.addAction("保存", self.save_sequence);
        save_action.setShortcut("Ctrl+S");
        save_action.setEnabled(self.has_permission('file_save'))

        save_as_action = file_menu.addAction("另存为...", self.save_sequence_as);
        save_as_action.setEnabled(self.has_permission('file_save_as'))

        file_menu.addSeparator()
        file_menu.addAction("退出", self.close)

        # --- 编辑菜单 ---
        edit_sequence_action = edit_menu.addAction("编辑当前序列", self.open_sequence_editor);
        edit_sequence_action.setEnabled(self.has_permission('edit_test_sequence'))
        
        edit_config_action = edit_menu.addAction("编辑系统配置...", self.open_config_editor);
        edit_config_action.setEnabled(self.has_permission('access_config_editor'))
        
        edit_menu.addSeparator();
        station_count_menu = QMenu("工位数量", self);
        station_count_menu.setEnabled(self.has_permission('edit_station_count'))
        edit_menu.addMenu(station_count_menu);
        
        # 获取当前选中的工位列表
        selected_stations = self.global_config.get('selected_stations', ['station_1', 'station_2', 'station_3', 'station_4'])
        current_count = len(selected_stations)
        
        # 存储所有工位选择动作，用于更新状态
        self.station_combo_actions = {}
        
        # 工位数量 1 - 子菜单选择单个工位
        count1_menu = QMenu("1 个工位", self)
        for i in [1, 2, 3, 4]:
            combo = tuple([f'station_{i}'])
            action = QAction(f"工位 {i}", self, checkable=True)
            action.setChecked(tuple(sorted(selected_stations)) == combo)
            action.triggered.connect(lambda checked, c=list(combo): self._apply_station_selection(c) if checked else None)
            count1_menu.addAction(action)
            self.station_combo_actions[combo] = action
        station_count_menu.addMenu(count1_menu)
        
        # 工位数量 2 - 子菜单选择两个工位组合
        count2_menu = QMenu("2 个工位", self)
        pairs = [
            ([1, 2], "工位 1 + 2"), ([1, 3], "工位 1 + 3"), ([1, 4], "工位 1 + 4"),
            ([2, 3], "工位 2 + 3"), ([2, 4], "工位 2 + 4"), ([3, 4], "工位 3 + 4")
        ]
        for nums, label in pairs:
            combo = tuple([f'station_{n}' for n in nums])
            action = QAction(label, self, checkable=True)
            action.setChecked(tuple(sorted(selected_stations)) == combo)
            action.triggered.connect(lambda checked, c=list(combo): self._apply_station_selection(c) if checked else None)
            count2_menu.addAction(action)
            self.station_combo_actions[combo] = action
        station_count_menu.addMenu(count2_menu)
        
        # 工位数量 3 - 子菜单选择三个工位组合
        count3_menu = QMenu("3 个工位", self)
        triplets = [
            ([1, 2, 3], "工位 1 + 2 + 3"), ([1, 2, 4], "工位 1 + 2 + 4"),
            ([1, 3, 4], "工位 1 + 3 + 4"), ([2, 3, 4], "工位 2 + 3 + 4")
        ]
        for nums, label in triplets:
            combo = tuple([f'station_{n}' for n in nums])
            action = QAction(label, self, checkable=True)
            action.setChecked(tuple(sorted(selected_stations)) == combo)
            action.triggered.connect(lambda checked, c=list(combo): self._apply_station_selection(c) if checked else None)
            count3_menu.addAction(action)
            self.station_combo_actions[combo] = action
        station_count_menu.addMenu(count3_menu)
        
        # 工位数量 4 - 直接选择全部
        combo_all = ('station_1', 'station_2', 'station_3', 'station_4')
        action_all = QAction("4 个工位 (全部)", self, checkable=True)
        action_all.setChecked(current_count == 4)
        action_all.triggered.connect(lambda checked: self._apply_station_selection(list(combo_all)) if checked else None)
        station_count_menu.addAction(action_all)
        self.station_combo_actions[combo_all] = action_all

        # --- 工具菜单 ---
        tools_menu.addAction("重新启动配置", self._on_reconnect_hardware)
        
        cycle_test_action = tools_menu.addAction("循环压力测试", self.open_cycle_test_dialog)
        cycle_test_action.setEnabled(self.has_permission('allow_cycle_test'))
        tools_menu.addSeparator()
        tools_menu.addAction("查看历史记录...", self.open_stats_report) # Changed text from "历史数据分析" to "查看历史记录..."
        
        permission_action = tools_menu.addAction("权限管理...", self.open_permission_manager)
        permission_action.setEnabled(self.has_permission('manage_users'))
        
        tools_menu.addAction("登录设置...", self.open_login_settings)

        tools_menu.addSeparator()
        sniffer_action = tools_menu.addAction("通信抓包工具...", self.open_sniffer_dialog) # Changed text from "串口抓包工具..." to "通信抓包工具..."
        sniffer_action.setEnabled(self.has_permission('access_sniffer_tool'))

        tools_menu.addSeparator()
        # 顶针管理（原"顶针使用提醒"）
        thimble_tracker_action = tools_menu.addAction("顶针管理...", self.open_thimble_tracker_dialog)
        thimble_tracker_action.setEnabled(self.has_permission('manage_thimble_usage'))
        
        # 线缆管理
        cable_manage_action = tools_menu.addAction("线缆管理...", self.open_cable_management_dialog)
        cable_manage_action.setEnabled(self.has_permission('manage_cables'))

        # 配方绑定管理
        recipe_manage_action = tools_menu.addAction("配方绑定管理...", self.open_recipe_management_dialog)
        recipe_manage_action.setEnabled(self.has_permission('manage_recipes'))

        tools_menu.addSeparator()
        # 测试时间预测（原"工单预测"）
        order_estimation_action = tools_menu.addAction("测试时间预测...", self.open_order_estimation_dialog)
        order_estimation_action.setEnabled(True)

        # --- 关于菜单 ---
        # 主题子菜单
        theme_menu = QMenu("主题", self)
        about_menu.addMenu(theme_menu)
        self.theme_action_group = QActionGroup(self)
        current_theme = self.global_config.get('ui_theme', 'dark_teal.xml')
        
        # 可用主题列表
        available_themes = [
            ('深青色 (Dark Teal)', 'dark_teal.xml'),
            ('深蓝色 (Dark Blue)', 'dark_blue.xml'),
            ('深琥珀 (Dark Amber)', 'dark_amber.xml'),
            ('深青蓝 (Dark Cyan)', 'dark_cyan.xml'),
            ('深紫色 (Dark Purple)', 'dark_purple.xml'),
            ('深粉色 (Dark Pink)', 'dark_pink.xml'),
            ('浅青色 (Light Teal)', 'light_teal.xml'),
            ('浅蓝色 (Light Blue)', 'light_blue.xml'),
            ('浅青蓝 (Light Cyan)', 'light_cyan.xml'),
            ('浅粉色 (Light Pink)', 'light_pink.xml'),
        ]
        
        for display_name, theme_file in available_themes:
            action = QAction(display_name, self, checkable=True, checked=(theme_file == current_theme))
            action.triggered.connect(lambda checked, tf=theme_file: self._on_theme_change(tf) if checked else None)
            theme_menu.addAction(action)
            self.theme_action_group.addAction(action)
        
        about_menu.addSeparator()
        about_menu.addAction("帮助", self.show_help_dialog)
        about_menu.addAction("版本号", self.show_about_dialog)

    def show_about_dialog(self):
        """显示关于对话框，包含版本信息和更新日志。"""
        from PySide6.QtWidgets import QDialog, QVBoxLayout, QTextBrowser, QPushButton
        
        # 获取图标路径并处理为 URL 格式
        icon_path = resource_path('app_icon.ico').replace('\\', '/')
        
        changelog_html = f"""
        <style>
            body {{ color: white; font-family: "Microsoft YaHei", sans-serif; }}
            h3 {{ color: #4CAF50; margin-top: 0; }}
            ul {{ margin-top: 5px; }}
            li {{ margin-bottom: 5px; }}
        </style>
        <table border="0" cellpadding="10">
            <tr>
                <td valign="top"><img src="{icon_path}" width="64" height="64"></td>
                <td valign="top">
                    <h3>自动化测试平台</h3>
                    <p>版本: {APP_VERSION}</p>
                    <p>版权所有 © 2025</p>
                </td>
            </tr>
        </table>
        <hr>
        <h3>版本 2.3.0 更新说明 (2026-09-02):</h3>
        <ul>
            <li><b>【新增】自定义 Modbus 仪器设备与板卡支持 (Custom Modbus):</b>
                <ul>
                    <li><b>共享与独立双模式:</b> 支持 4 工位共用 1 个 Modbus 仪器/继电器板，内置线程互斥排队锁，彻底杜绝并发串口冲突；同时支持每工位独立串口模式。</li>
                    <li><b>自定义函数与工位地址映射:</b> 可以在配置编辑器中自定义函数名（如 <code>K_BOARD</code>）、描述、物理地址（十六进制/十进制）、True/False 写入值，测试序列中直接作为模块函数调用。</li>
                    <li><b>标准序列通信管理:</b> 测试序列 Setup 阶段通过 <code>open_serial_port</code> 动态配置波特率与超时，Cleanup 阶段通过 <code>close_serial_port</code> 安全释放。</li>
                </ul>
            </li>
            <li><b>【新增】USB 继电器板专用驱动与测试模块 (Relay Board):</b>
                <ul>
                    <li><b>专用 HEX/ASCII 协议深度适配:</b> 适配 USB Relay (TC, 4, Opto) / LCUS 系列继电器板专属协议（0xA0 指令头、累加和校验、ASCII 状态回显）。</li>
                    <li><b>4工位智能通道绑定:</b> 共享模式下无需配置繁琐表格，测试序列直接调用 <code>set_relay</code>、<code>get_relay</code>、<code>relay_on</code>、<code>relay_off</code>，各工位自动精准对应控制 CH1~CH4。</li>
                    <li><b>状态判断标准化:</b> 底层自动抹平不同工位返回文本差异，无论哪个工位吸合统一返回数值 <code>1</code>，断开统一返回 <code>0</code>，大幅简化序列判定逻辑。</li>
                </ul>
            </li>
            <li><b>【优化】配置器界面全面重构与美化:</b>
                <ul>
                    <li><b>自适应撑满与紧凑排版:</b> 彻底修复了之前表格被压缩显示过小及 Label 与控件之间的大段空白问题，规范标准表单尺寸。</li>
                    <li><b>科技风智能说明卡片:</b> 增加浅绿色信息引导卡片，直观展示共享模式下的工位通道绑定关系。</li>
                </ul>
            </li>
        </ul>
        <hr>
        <h3>版本 2.2.0 更新说明 (2026-07-31):</h3>
        <ul>
            <li><b>【新增】配方绑定管理功能 (Recipe & Cable Management):</b>
                <ul>
                    <li><b>配方与产品编码绑定:</b> 支持将测试脚本 (.json)、示例产品条码、提取的产品核心编码及转接线编码进行多维关联防错。选择脚本界面提供 <code>📁 浏览...</code> 选择窗口。</li>
                    <li><b>示例条码智能截取:</b> 增加 <code>⚡ 智能识别截取</code> 按钮，扫入完整示例条码后可自动智能提炼提取核心产品型号编码/前缀。</li>
                    <li><b>多工位精准置顶弹窗:</b> 在多工位产线中，转接线匹配弹窗自动精准浮现在<b>对应操作工位 Frame 正前方</b>，绝不遮挡其他工位。</li>
                    <li><b>无序/随机顺序扫码与自动高亮:</b> 支持任意顺序扫描多根转接线，扫错或取消测试时输入框自动全选高亮，扫码枪可直接无缝覆盖输入。</li>
                    <li><b>点击取消绝对终止拦截:</b> 点击 <b>❌ 取消测试</b> 时，程序在卡口处彻底终止拦截，工位显示 <code>取消测试</code>，零步骤执行、零 Cleanup 执行。</li>
                    <li><b>型号不匹配极速拦截:</b> 输入不匹配产品型号时，状态栏直接红底显示 <code>产品型号不匹配</code> 且 SN 框自动全选高亮，取消冗余 OK 确认框。</li>
                </ul>
            </li>
            <li><b>【新增】默认线缆寿命统计与报告融合:</b>
                <ul>
                    <li><b>自动寿命计数累加:</b> 只要配方绑定了转接线，每次测试完毕（PASS/FAIL）自动为该线缆在消耗品数据库中增加 +1 使用次数。</li>
                    <li><b>测试报告扩展:</b> 生成的 HTML/PDF 测试报告文件名及表头自动包含真实转接线编码与实时剩余寿命信息（如 <code>PASS_station_1_产品SN_线缆SN_时间.html</code>）。</li>
                </ul>
            </li>
        </ul>
        <hr>
        <h3>版本 2.1.1 更新说明 (2026-04-01):</h3>
        <ul>
            <li><b>序列编辑器功能增强:</b>
                <ul>
                    <li><b>Flag 书签标记:</b> 新增自定义 Flag 功能，可以在长序列中快速为关键步骤打上高亮标签，方便跳转与关注。</li>
                    <li><b>内容搜索:</b> 新增搜索栏，支持在庞大的测试序列中全文检索测试名称、参数或模块名称，提供便捷的定位能力。</li>
                </ul>
            </li>
            <li><b>CPK 数据保存修复:</b> 修复了在执行 Fluke8808A、DP832 等底层测量仪器的操作时，返回值因为类型错误导致无法进入 CPK 历史记录分析池的问题。</li>
        </ul>
        <hr>
        <h3>版本 2.1.0 更新说明 (2026-03-06):</h3>
        <ul>
            <li><b>以太网通信模块强化:</b>
                <ul>
                    <li><b>新增指令发送函数:</b> 增加了 <code>send_command</code> 直接发送简单指令不再强制要求填写 <code>extract_key</code>。</li>
                    <li><b>独立重连与初始化验证:</b> 增加了 <code>init_connection</code> 提供专属于复位上电流程的主动连接判断，防“假死连接”，并带有智能超时重试机制 (拦截 10065 错误)。</li>
                    <li><b>多网卡本地绑定:</b> 配合测试台多个 USB 转网口的需求，测试引擎现在可以在配置参数中指定发包专属的本地网卡 IP 进行硬件绑定，避免路由乱跳。</li>
                </ul>
            </li>
            <li><b>测试引擎比较逻辑优化:</b>
                <ul>
                    <li><b>多区间"或" (||) 判断:</b> 在 Sequence 检查中新增了 <code>||</code> 比较操作符。配合 <code>355, 0</code> (LowerLimits) 与 <code>360, 5</code> (UpperLimits) 可以实现对环形刻度或不相交多区间的范围探测。</li>
                    <li><b>严格符与多空白包容:</b> 对 <code>Contains</code> 系列判断增加了对多重制表符和换行符的兼容容错处理，以及对明确出现的 `\r\n` 元字符的转换匹配能力。</li>
                </ul>
            </li>
            <li><b>全局抓包工具功能增强:</b>
                <ul>
                    <li><b>由串口转为通信抓包:</b> 工具被更名为 <b>通信抓包工具</b>，并在以太网的底层 TX/RX 接口打入了数据钩子。</li>
                    <li><b>动态端口聚合:</b> 抓包工具现在能将以太网虚拟地址 (<code>IP:Port</code>) 和 COM口统一归入对应的工位，并同步保存到同一个分析日志文件中。</li>
                </ul>
            </li>
        </ul>
        <hr>
        <h3>版本 2.0.0 更新说明 (2025-12-31):</h3>
        <ul>
            <li><b>动态驱动配置系统:</b>
                <ul>
                    <li><b>全面迁移:</b> 所有驱动配置（电源、万用表、串口、JLink、UniFlash）现在都使用动态加载机制。</li>
                    <li><b>驱动开发指南:</b> 帮助文档新增「驱动开发指南」，详细说明如何编写 CONFIG_TAB 和 CONFIG_SCHEMA。</li>
                    <li><b>自动生成界面:</b> 在 drivers/ 目录下创建驱动文件后，配置编辑器自动生成对应的配置 Tab。</li>
                </ul>
            </li>
            <li><b>电源配置增强:</b>
                <ul>
                    <li><b>三模式切换:</b> DP832 支持共享/独立/专用三种模式切换。</li>
                    <li><b>多电源配置:</b> 专用模式支持配置两台电源，分别映射电池供电和采集卡供电。</li>
                    <li><b>通道配置:</b> 支持配置每个通道的电压、电流和启动时打开状态。</li>
                </ul>
            </li>
            <li><b>VISA/串口选择器优化:</b>
                <ul>
                    <li><b>点击刷新:</b> 移除刷新按钮，改为点击下拉框时自动扫描设备（与串口选择器一致）。</li>
                    <li><b>加载优化:</b> 配置编辑器打开时不再预扫描设备，大幅提升加载速度。</li>
                </ul>
            </li>
            <li><b>串口配置增强:</b>
                <ul>
                    <li><b>从站设备表格:</b> 恢复设备名称+从站地址的表格编辑功能，支持添加/删除设备行。</li>
                    <li><b>模式切换:</b> 支持共享/独立模式切换。</li>
                </ul>
            </li>
            <li><b>工位布局统一:</b>
                <ul>
                    <li><b>2x2 布局:</b> JLink、UniFlash、以太网等配置统一使用 2x2 工位布局（上12下34）。</li>
                    <li><b>固定4工位:</b> per_station 模式固定为4工位，不再依赖 config.json 中的 station_count。</li>
                </ul>
            </li>
            <li><b>界面优化:</b>
                <ul>
                    <li><b>布局优化:</b> 优化了专用模式电源配置的输入框间距和对齐。</li>
                    <li><b>移除帮助菜单:</b> 配置编辑器移除了左上角帮助菜单。</li>
                </ul>
            </li>
        </ul>
        <hr>
        <h3>版本 1.2.3 更新说明:</h3>
        <ul>
            <li><b>新增鼎阳SPD4323X四通道电源支持:</b>
                <ul>
                    <li>新增 <code>drivers/siglent_spd4323x.py</code> 驱动，支持电压/电流设置、输出控制、测量等功能。</li>
                    <li>新增 <code>test_modules/spd4323x.py</code> 测试模块，提供共享模式和独立模式两套函数。</li>
                    <li>配置编辑器新增"SPD4323X 电源"标签页，支持VISA地址扫描、模式切换、通道配置。</li>
                    <li>支持启动时自动连接和设置各通道初始电压/电流。</li>
                </ul>
            </li>
            <li><b>测试比较失败消息优化:</b>
                <ul>
                    <li>改进消息格式，从 "32 == 0" 改为 "实测值=32, 设定值=0 (要求: ==)"，更清晰易懂。</li>
                    <li>范围比较显示为 "实测值=0.012, 范围=[3.2, 3.4]"。</li>
                    <li>支持所有比较模式：==、!=、>、>=、<、<=、InRange、NotInRange、Contains、NotContains。</li>
                </ul>
            </li>
            <li><b>失败状态提示增强:</b> 失败时状态栏显示 "失败: xxx(步骤N)，具体内容请参考对应步骤的信息"，引导用户查看详情。</li>
        </ul>
        <hr>
        <h3>版本 1.2.2 更新说明:</h3>
        <ul>
            <li><b>修复Pass/Fail统计逻辑:</b>
                <ul>
                    <li>修复1分钟内复测通过时，数据库产生重复记录导致Total和Pass计数错误的问题。</li>
                    <li>优化跨工位复测逻辑：复测成功时，原工位取消Fail和Total计数，当前工位计入Pass和Total。</li>
                    <li>跨工位复测成功后，数据库记录的工位ID自动更新为复测成功的工位。</li>
                </ul>
            </li>
            <li><b>空SN提示优化:</b> 未输入SN时，不再弹出对话框，改为在状态栏显示 "⚠ 产品SN不能为空" 提示，减少操作干扰。</li>
            <li><b>简易SN判断优化:</b> SN长度≤3或纯数字≤999的视为简易SN，不进行重复检查（如1、2、test等用于无唯一SN的产品）。</li>
        </ul>
        <hr>
        <h3>版本 1.2.1 更新说明:</h3>
        <ul>
            <li><b>主题切换:</b> 在"关于"菜单中新增"主题"子菜单，支持 10 种主题（6 种暗色 + 4 种亮色），切换后立即生效。</li>
            <li><b>PASS 状态显示 SN:</b> 测试通过时，状态栏显示 "通过 | SN: xxx"，便于查看刚刚测试的产品。</li>
            <li><b>工位数量选择优化:</b> 重新设计工位选择菜单，采用分层结构：先选择工位数量（1-4），再选择具体哪些工位组合。</li>
        </ul>
        <hr>
        <h3>版本 1.2.0 更新说明:</h3>
        <ul>
            <li><b>耗材寿命管理模块:</b>
                <ul>
                    <li><b>线缆管理:</b> 新增流动线缆寿命追踪功能，自动记录每根线缆的使用次数。</li>
                    <li><b>扫码绑定:</b> 加载测试序列后自动弹出扫码对话框，要求扫描每个工位的线缆SN。</li>
                    <li><b>自动计数:</b> 每次测试完成（Pass/Fail）自动增加对应线缆的使用计数。</li>
                    <li><b>寿命警告:</b> 线缆达到使用上限时，扫码界面显示警告。</li>
                    <li><b>报废管理:</b> 支持将损坏或达到寿命的线缆标记为报废。</li>
                </ul>
            </li>
            <li><b>顶针管理增强:</b>
                <ul>
                    <li><b>默认参数:</b> 新增治具默认使用上限20,000次，预警天数90天。</li>
                    <li><b>历史记录:</b> 在对话框内直接查看顶针更换历史记录，支持搜索和CSV导出。</li>
                    <li><b>重置日志:</b> 每次重置使用次数时自动记录到历史。</li>
                </ul>
            </li>
            <li><b>菜单结构调整:</b>
                <ul>
                    <li><b>名称更新:</b> "顶针使用提醒"改为"顶针管理"。</li>
                    <li><b>名称更新:</b> "工单预测"改为"测试时间预测"。</li>
                    <li><b>新增菜单:</b> 添加"线缆管理"菜单项。</li>
                </ul>
            </li>
            <li><b>SN输入框优化:</b>
                <ul>
                    <li><b>智能焦点:</b> 测试成功后自动跳转到下一个空闲工位的输入框。</li>
                    <li><b>失败返回:</b> 测试失败时焦点自动返回当前工位，方便重测。</li>
                </ul>
            </li>
            <li><b>权限系统增强:</b>
                <ul>
                    <li><b>新权限:</b> 添加"顶针管理"、"线缆管理"、"测试时间预测"权限项。</li>
                    <li><b>自动授权:</b> 新增权限自动授予给工程师用户，无需手动配置。</li>
                </ul>
            </li>
        </ul>
        <hr>
        <h3>版本 1.1.4 更新说明:</h3>
        <ul>
            <li><b>会话统计系统:</b>
                <ul>
                    <li><b>按日期分割:</b> 每个测试序列每天自动创建一条会话记录，跨天自动分开。</li>
                    <li><b>历史数据准确:</b> 每条记录保存当时的吃饭时长设置，历史报告使用记录时的设置计算。</li>
                    <li><b>智能拿取耗时:</b> 用前10次间隔建立基准，超过3倍基准的间隔自动排除。</li>
                </ul>
            </li>
            <li><b>历史报告增强:</b>
                <ul>
                    <li><b>新增列:</b> 日期、工位数、操作员(姓名+工号)。</li>
                    <li><b>移除列:</b> 目标、进度（因为自动跟踪无需手动设置）。</li>
                    <li><b>午餐/晚餐:</b> 显示每条记录自己的设置值。</li>
                </ul>
            </li>
            <li><b>预测对话框优化:</b>
                <ul>
                    <li><b>简化输入:</b> 移除工单号输入框，改为自动使用序列名。</li>
                    <li><b>时间参数显示:</b> 实时显示平均测试时长和拿取耗时。</li>
                    <li><b>作息时间:</b> 简化为直接输入时长（分钟）。</li>
                </ul>
            </li>
        </ul>
        <hr>
        <h3>版本 1.1.3 更新说明:</h3>
        <ul>
            <li><b>顶针治具管理重构:</b>
                <ul>
                    <li><b>治具中心化:</b> 顶针使用追踪改为以治具为中心，每个治具可关联多个测试序列。</li>
                    <li><b>分层计数:</b> 同时追踪治具总使用次数和各序列单独使用次数。</li>
                    <li><b>首次关联提示:</b> 运行未关联的序列时，自动弹窗提示输入治具编码。</li>
                    <li><b>界面升级:</b> 采用合并单元格展示治具信息，支持直接编辑使用上限和预警天数。</li>
                </ul>
            </li>
            <li><b>电源独立模式支持:</b>
                <ul>
                    <li><b>模式切换:</b> 配置编辑器中可切换共享/独立电源模式。</li>
                    <li><b>工位电源:</b> 独立模式下，每个工位使用各自配置的电源VISA地址和通道映射。</li>
                    <li><b>通道映射:</b> 独立模式下产品、电池、采集卡可分别映射到不同通道。</li>
                </ul>
            </li>
            <li><b>新增电源函数:</b> <code>set_power_battery</code> 和 <code>set_power_daq</code>，用于控制电池和采集卡供电。</li>
        </ul>
        <hr>
        <h3>版本 1.1.2 更新说明:</h3>
        <ul>
            <li><b>智能工单预测增强:</b>
                <ul>
                    <li><b>界面重构:</b> 工单预测界面全面升级为网格布局，信息展示更直观，并新增2秒自动刷新机制。</li>
                    <li><b>作息避让:</b> 新增车间作息时间配置（午餐/晚餐），预估完成时刻自动跳过休息时段。</li>
                    <li><b>操作优化:</b> 移除了主界面冗余的工单输入框，统一在工具菜单中管理。</li>
                </ul>
            </li>
            <li><b>Modbus 通信升级:</b>
                <ul>
                    <li><b>32位数据支持:</b> 新增 <code>read_long</code> 函数，支持直接读取并解析32位整数（如版本号）。</li>
                    <li><b>有符号数支持:</b> <code>read_register</code> 系列函数现支持 <code>signed=True</code> 参数，可直接读取负数。</li>
                    <li><b>字节序控制:</b> 新增 <code>byteorder</code> 参数 (0-3)，灵活适配各种大小端设备。</li>
                </ul>
            </li>
            <li><b>帮助系统修复:</b> 修复了帮助文档无法正确显示多行参数说明和用法示例的问题。</li>
            <li><b>窗口状态修复:</b> 修复了最大化窗口切换应用后状态丢失的问题。</li>
        </ul>
        <hr>
        <h3>版本 1.1.1 更新说明:</h3>
        <ul>
            <li><b>UniFlash 固件烧录支持:</b>
                <ul>
                    <li>新增 UniFlash 配置界面，支持为每个工位独立指定固件烧录目录。</li>
                    <li>新增 <code>uniflash</code> 测试模块，提供 <code>run_uniflash_bat</code> 函数用于执行 .bat 文件。</li>
                    <li>新增 <code>process_utils</code> 模块，支持运行 .bat 脚本并捕获输出。</li>
                    <li>修复了路径中反斜杠导致的 Unicode 转义错误。</li>
                </ul>
            </li>
            <li><b>UI 优化:</b>
                <ul>
                    <li>优化了测试结果显示：结果列仅显示成功/失败状态，详细信息移至信息列。</li>
                    <li>改进了配置编辑器的文件/目录选择功能，新增"浏览"按钮。</li>
                </ul>
            </li>
            <li><b>配置持久化修复:</b> 修复了 UniFlash 配置无法正确保存和加载的问题。</li>
        </ul>
        <hr>
        <h3>版本 1.1.0 更新说明:</h3>
        <ul>
            <li><b>配置编辑器升级:</b>
                <ul>
                    <li>优化了 Modbus 从站配置界面，支持全局统一管理。</li>
                    <li>改进了串口端口选择，现在使用下拉框自动列出可用端口。</li>
                    <li>移除了不再需要的详细串口参数设置。</li>
                </ul>
            </li>
            <li><b>驱动支持:</b> 增强了对动态加载驱动的支持。</li>
            <li><b>UI 优化:</b> 调整了部分界面布局，提升用户体验。</li>
        </ul>
        <hr>
        <p>版本 1.0.0: 初始发布</p>
        """
        
        dialog = QDialog(self)
        dialog.setWindowTitle(f"关于 自动化测试平台 {APP_VERSION}")
        dialog.setWindowIcon(QIcon(resource_path('app_icon.ico')))
        
        layout = QVBoxLayout(dialog)
        
        text_browser = QTextBrowser()
        text_browser.setHtml(changelog_html)
        text_browser.setOpenExternalLinks(True)
        layout.addWidget(text_browser)
        
        close_button = QPushButton("关闭")
        close_button.clicked.connect(dialog.accept)
        layout.addWidget(close_button)
        
        dialog.show()
        dialog.setWindowState(Qt.WindowMaximized)

    @require_permission('manage_thimble_usage')
    def open_thimble_tracker_dialog(self):
        """打开顶针追踪对话框"""
        if self._is_window_active(self.thimble_tracker_dialog_instance):
            self.thimble_tracker_dialog_instance.activateWindow()
            self.thimble_tracker_dialog_instance.raise_()
        else:
            self.thimble_tracker_dialog_instance = ThimbleTrackerDialog(self.thimble_manager, self)
            self.thimble_tracker_dialog_instance.setAttribute(Qt.WA_DeleteOnClose)
            # 使用setWindowState设置最大化状态（与工单预测对话框一致的方式）
            self.thimble_tracker_dialog_instance.setWindowState(Qt.WindowMaximized)
            self.thimble_tracker_dialog_instance.show()  # 非模态，支持任务栏最小化

    def open_pogo_history_report(self):
        """打开顶针历史记录报告"""
        success, result = pogo_history_report.generate_and_open_pogo_history()
        if not success:
            QMessageBox.warning(self, "错误", f"生成报告失败: {result}")

    def open_cable_swap_dialog(self):
        """打开线缆更换对话框"""
        station_ids = [f"Station_{i+1}" for i in range(self.global_config.get('station_count', 4))]
        dialog = CableSwapDialog(self, station_ids)
        dialog.exec()

    @require_permission('manage_cables')
    def open_cable_management_dialog(self):
        """打开线缆管理对话框"""
        from cable_management_dialog import CableManagementDialog
        dialog = CableManagementDialog(self)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.setWindowState(Qt.WindowMaximized)
        dialog.show()  # 非模态，支持任务栏最小化

    @require_permission('manage_recipes')
    def open_recipe_management_dialog(self):
        """打开配方绑定管理对话框"""
        from recipe_management_dialog import RecipeManagementDialog
        dialog = RecipeManagementDialog(self)
        dialog.exec()

    def _show_cable_scan_dialog(self):
        """弹出线缆扫码对话框"""
        # 使用与 config.json 一致的 station_id 格式 (station_1 而不是 Station_1)
        station_ids = list(self.station_frames.keys())
        
        # 清空之前的绑定
        manager = get_consumable_manager()
        manager.clear_session()
        
        dialog = CableScanDialog(self, station_ids)
        result = dialog.exec()
        
        if result == QDialog.Accepted:
            # 获取绑定结果
            bindings = dialog.get_bindings()
            print(f"[CableScan] 线缆绑定完成: {bindings}")
        else:
            # 用户取消，清空绑定
            manager.clear_session()
            print("[CableScan] 用户取消扫码")

    def open_order_estimation_dialog(self):
        """打开工单预测对话框"""
        # 获取当前序列名称
        sequence_name = ""
        if self.current_sequence_file_path:
            sequence_name = os.path.basename(self.current_sequence_file_path)
        
        dialog = OrderEstimationDialog(
            parent=self,
            station_count=self.global_config.get('station_count', 1),
            sequence_name=sequence_name,
            sequence_data=self.sequence_data
        )
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        # 使用setWindowState设置最大化状态
        dialog.setWindowState(Qt.WindowMaximized)
        dialog.show()  # 非模态，支持任务栏最小化
        
        # 保存对话框引用以便后续访问
        self._order_estimation_dialog = dialog

    def open_login_settings(self):
        """打开登录设置对话框,允许所有用户修改默认登录角色"""
        if self._is_window_active(self.login_settings_instance):
            self.login_settings_instance.activateWindow()
            self.login_settings_instance.raise_()
        else:
            self.login_settings_instance = LoginSettingsDialog(self)
            self.login_settings_instance.setAttribute(Qt.WA_DeleteOnClose)
            self.login_settings_instance.exec()
    
    @require_permission('access_sniffer_tool')
    def open_sniffer_dialog(self):
        """打开串口抓包工具对话框，并确保只有一个实例。"""
        if not self._is_window_active(self.sniffer_dialog_instances):
            self.sniffer_dialog_instance = SnifferDialog(self, self)
            self.sniffer_dialog_instance.show()
        else:
            self.sniffer_dialog_instance.activateWindow()
            self.sniffer_dialog_instance.raise_()

    def open_stats_report(self):
        """启动后台Flask服务器（如果尚未运行）并打开浏览器。"""
        # Prevent duplicate browser opening
        if self.stats_browser_opening:
            self.statusBar().showMessage("正在打开浏览器，请稍候...", 1000)
            return
            
        try:
            self.stats_browser_opening = True
            
            if self.stats_server_thread is None or not self.stats_server_thread.is_alive():
                print("正在启动后台统计服务器...")
                # 创建一个线程来运行Flask应用
                self.stats_server_thread = threading.Thread(target=stats_app.run_app, daemon=True)
                self.stats_server_thread.start()
                self.statusBar().showMessage("正在启动统计服务器...", 3000)
                # 给服务器一点启动时间
                delay_ms = 1500
            else:
                print("统计服务器已在运行。")
                self.statusBar().showMessage("统计服务器已在运行。", 3000)
                delay_ms = 0

            # 在延迟后打开浏览器，并重置标志
            def open_and_reset():
                webbrowser.open('http://127.0.0.1:5678')
                # 延迟重置标志，确保浏览器已经启动
                QTimer.singleShot(500, lambda: setattr(self, 'stats_browser_opening', False))
            
            QTimer.singleShot(delay_ms, open_and_reset)

        except Exception as e:
            self.stats_browser_opening = False
            QMessageBox.critical(self, "错误", f"无法启动统计分析应用：\n{e}")
            print(f"启动 stats_app.py 失败: {e}")

    @require_permission('manage_users')
    def open_permission_manager(self):
        """打开权限管理对话框，并在关闭后刷新当前用户权限。"""
        if self._is_window_active(self.permission_manager_instance):
            self.permission_manager_instance.activateWindow()
            self.permission_manager_instance.raise_()
        else:
            self.permission_manager_instance = PermissionManagerDialog(self)
            self.permission_manager_instance.setAttribute(Qt.WA_DeleteOnClose)
            self.permission_manager_instance.exec()  # This is a blocking call

            # --- 【【【 核心修复：对话框关闭后，重新加载配置以刷新权限 】】】 ---
            print("权限管理器已关闭，正在重新加载配置以更新当前用户权限...")
            if self.load_config():  # load_config() reloads self.global_config
                if self.user_info and self.user_info.get('id'):
                    user_id = self.user_info['id']
                    new_access_control = self.global_config.get('access_control', {})
                    new_users = new_access_control.get('users', {})
                    new_user_data = new_users.get(user_id)

                    if new_user_data:
                        new_permissions = new_user_data.get('permissions', [])
                        # Check if permissions have actually changed
                        if set(self.user_info['permissions']) != set(new_permissions):
                            self.user_info['permissions'] = new_permissions
                            print(f"用户 '{user_id}' 的权限已在当前会话中更新。")
                            QMessageBox.information(self, "权限已更新", "当前用户的权限已刷新。")
            else:
                print("重新加载配置失败，权限可能未更新。")

    def _on_reconnect_hardware(self):
        """处理用户点击"重新启动配置"的动作。重新加载 config.json 并重新连接硬件。"""
        if any(frame.active_thread for frame in self.station_frames.values()):
            QMessageBox.warning(self, "操作无效", "无法在测试期间重新启动配置。")
            return

        self.statusBar().showMessage("正在重新启动配置...")
        QApplication.processEvents()

        try:
            # 1. 关闭所有现有硬件连接
            if self.hardware_manager:
                self.hardware_manager.close_all()
            
            # 2. 重新加载 config.json
            if not self.load_config():
                QMessageBox.critical(self, "错误", "重新加载配置文件失败。")
                return
            
            # 3. 重新创建 hardware_manager，需要传入 driver_plugins
            from hardware_manager import HardwareManager
            self.hardware_manager = HardwareManager(self.global_config, driver_plugins=self.drivers)
            
            # 4. 重新连接所有自动连接的硬件
            errors = self.hardware_manager.load_and_connect_auto_devices()
            
            # 5. 更新各工位的硬件管理器引用
            for station_id, frame in self.station_frames.items():
                station_cfg = self.global_config.get('stations', {}).get(station_id, {})
                station_cfg['id'] = station_id
                frame.station_config = station_cfg
            
            if not errors:
                self.statusBar().showMessage("配置重新启动成功。", 5000)
                QMessageBox.information(self, "成功", "配置已重新加载，所有硬件已重新连接。")
            else:
                error_details = "\n\n- " + "\n\n- ".join(errors)
                self.statusBar().showMessage("配置重新启动完成，部分硬件连接失败。", 5000)
                show_scrollable_warning(self, "部分硬件连接失败", f"配置已重新加载，但以下硬件未能成功连接：\n{error_details}")
        except Exception as e:
            self.statusBar().showMessage("配置重新启动失败。", 5000)
            QMessageBox.critical(self, "错误", f"重新启动配置时发生错误：\n{e}")

    # --- 辅助函数保持不变 ---
    def _is_window_active(self, window_instance):
        try:
            if window_instance and window_instance.isVisible(): return True
        except RuntimeError:
            return False
        return False

    def _prompt_save_before_action(self, title, text):
        if self.is_sequence_modified:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle(title)
            msg_box.setText(text)
            msg_box.setIcon(QMessageBox.Question)
            save_button = msg_box.addButton("保存", QMessageBox.AcceptRole)
            discard_button = msg_box.addButton("不保存", QMessageBox.DestructiveRole)
            cancel_button = msg_box.addButton("取消", QMessageBox.RejectRole)
            msg_box.exec()
            clicked_button = msg_box.clickedButton()

            if clicked_button == save_button:
                self.save_sequence_to_file()
                return not self.is_sequence_modified
            elif clicked_button == discard_button:
                return True
            else:  # cancel_button
                return False
        return True

    # =========================================================
    #            【【【 Bug修复核心修改区域 】】】
    # =========================================================
    @require_permission('edit_test_sequence')
    def open_sequence_editor(self):
        if any(frame.active_thread for frame in self.station_frames.values()):
            QMessageBox.warning(self, "操作无效", "无法在测试期间编辑测试程序。")
            return

        if not self.sequence_data:
            QMessageBox.information(self, "提示", "请先新建或打开一个测试程序文件。")
            return

        if self._is_window_active(self.sequence_editor_instance):
            self.sequence_editor_instance.activateWindow()
            self.sequence_editor_instance.raise_()
        else:
            # --- 【【【 核心修复：删除了对 deleteLater 的调用 】】】 ---
            # 既然我们已经依赖 WA_DeleteOnClose，这里就不应该再手动删除。
            # Python 的垃圾回收机制和 Qt 的父子关系会自动处理好内存。
            # self.sequence_editor_instance.deleteLater()  <-- 这行是导致崩溃的元凶，删掉它！

            self.sequence_editor_instance = SequenceEditor(
                self, 
                copy.deepcopy(self.sequence_data), 
                self.test_modules,
                self.on_sequence_saved, 
                self.current_sequence_file_path
            )
            self.sequence_editor_instance.setAttribute(Qt.WA_DeleteOnClose)
            self.sequence_editor_instance.show()
            self.sequence_editor_instance.setWindowState(Qt.WindowMaximized)

    # --- 后续所有方法保持和你上次的版本一样，完全不变 ---
    def on_sequence_saved(self, new_sequence_data):
        # 仅更新内存中的数据和刷新视图
        # 注意：is_sequence_modified 状态现在由编辑器的 _save_and_apply 负责管理
        if self.sequence_data != new_sequence_data:
            self.sequence_data = new_sequence_data
            self.refresh_all_station_views()

    @require_permission('access_config_editor')
    def open_config_editor(self):
        if self._is_window_active(self.config_editor_instance):
            self.config_editor_instance.activateWindow();
            self.config_editor_instance.raise_()
        else:
            # ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓ 【【【核心修改：传递完整的、正确的路径】】】 ↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓↓
            config_file_path = os.path.join(get_app_base_path(), 'config.json')
            self.config_editor_instance = ConfigEditor(self, config_file_path, self.on_config_saved_light)
            # ↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑↑
            self.config_editor_instance.setAttribute(Qt.WA_DeleteOnClose)
            self.config_editor_instance.show()
            self.config_editor_instance.setWindowState(Qt.WindowMaximized)

    def on_config_saved_light(self, new_config):
        self.global_config = new_config
        QMessageBox.information(self, "成功", "配置已保存。\n更改将在下次启动软件时完全生效。")

    def show_help_dialog(self):
        if self._is_window_active(self.help_dialog_instance):
            self.help_dialog_instance.activateWindow();
            self.help_dialog_instance.raise_()
        else:
            self.help_dialog_instance = HelpDialog(self, self.test_modules, self.drivers)
            self.help_dialog_instance.setAttribute(Qt.WA_DeleteOnClose)
            self.help_dialog_instance.show()
            self.help_dialog_instance.setWindowState(Qt.WindowMaximized)

    def closeEvent(self, event):
        if not self._prompt_save_before_action("退出", "当前测试程序有未保存的更改，是否在退出前保存？"):
            event.ignore()
            return

        if any(frame.active_thread for frame in self.station_frames.values()):
            if QMessageBox.question(self, '退出', '有测试正在进行，确定要强制退出吗？',
                                    QMessageBox.Yes | QMessageBox.No) == QMessageBox.No:
                event.ignore()
                return

        print("正在关闭所有硬件连接...")
        self.stop_all_event.set()
        if self.hardware_manager: self.hardware_manager.close_all()
        print("程序已退出。 সন")

        for window in [self.sequence_editor_instance, self.config_editor_instance, self.help_dialog_instance]:
            if self._is_window_active(window):
                window.close()

        event.accept()

    @require_permission('file_new')
    def new_sequence_file(self):
        if any(frame.active_thread for frame in self.station_frames.values()):
            QMessageBox.warning(self, "操作无效", "无法在测试期间新建测试程序。")
            return

        if not self._prompt_save_before_action("新建", "当前测试程序有未保存的更改，是否保存？"):
            return

        if self._is_window_active(self.sequence_editor_instance):
            self.sequence_editor_instance.close()

        self.sequence_data = copy.deepcopy(DEFAULT_SEQUENCE_DATA)
        self.current_sequence_file_path = ""
        self.is_sequence_modified = True
        self.update_title()
        self.refresh_all_station_views()

        self.open_sequence_editor()

    def load_sequence_from_file(self, filepath=None):
        if any(frame.active_thread for frame in self.station_frames.values()):
            QMessageBox.warning(self, "操作无效", "无法在测试期间加载测试程序。")
            return

        if not self._prompt_save_before_action("打开文件", "当前测试程序有未保存的更改，是否保存？"):
            return

        if self._is_window_active(self.sequence_editor_instance):
            self.sequence_editor_instance.close()

        if filepath is None:
            sequences_dir = os.path.join(get_app_base_path(), 'sequences')
            if not os.path.exists(sequences_dir):
                os.makedirs(sequences_dir)

            filepath, _ = QFileDialog.getOpenFileName(self, "打开序列", sequences_dir, "JSON files (*.json)")

        if not filepath:
            return

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                self.sequence_data = json.load(f)
            self.current_sequence_file_path = filepath
            self.is_sequence_modified = False
            self.update_title()
            self.refresh_all_station_views()
            QMessageBox.information(self, "加载成功", f"成功加载: {os.path.basename(filepath)}")

            # 自动聚焦到第一个工位
            if self.ordered_station_ids:
                first_station_id = self.ordered_station_ids[0]
                if first_station_id in self.station_frames:
                    self.station_frames[first_station_id].sn_entry.setFocus()
            
            # 【新增】弹出线缆扫码对话框（如果启用线缆追踪）
            cable_enabled = self.global_config.get('cable_tracking', {}).get('enabled', True)
            if cable_enabled:
                self._show_cable_scan_dialog()
            
            # 检查序列是否已关联治具（如果启用顶针追踪）
            thimble_enabled = self.global_config.get('thimble_tracking', {}).get('enabled', True)
            if thimble_enabled:
                self._check_and_prompt_fixture_binding(filepath)
        except Exception as e:
            QMessageBox.critical(self, "加载失败", f"无法加载或解析文件: {e}")

    def _check_and_prompt_fixture_binding(self, seq_path):
        """检查序列是否已关联治具，若未关联则弹窗提示用户输入治具编码"""
        if not seq_path or not hasattr(self, 'thimble_manager'):
            return
        
        # 使用第一个工位来检查（通常所有工位共用同一个治具配置）
        if not self.ordered_station_ids:
            return
        
        first_station_id = self.ordered_station_ids[0]
        fixture_code = self.thimble_manager.get_fixture_for_sequence(seq_path, first_station_id)
        
        if fixture_code is None:
            # 弹窗请求用户输入治具编码
            code, ok = QInputDialog.getText(
                self, "输入治具编码",
                f"此测试程序尚未关联治具。\n请输入所使用的治具编码（如 FIX_001）：",
                QLineEdit.Normal, ""
            )
            if ok and code.strip():
                # 为所有工位关联同一个治具
                for station_id in self.ordered_station_ids:
                    self.thimble_manager.associate_sequence(seq_path, code.strip(), station_id)

    def save_sequence_to_file(self, save_as=False):
        filepath = self.current_sequence_file_path
        if save_as or not filepath:
            sequences_dir = os.path.join(get_app_base_path(), 'sequences')
            if not os.path.exists(sequences_dir):
                os.makedirs(sequences_dir)

            filepath, _ = QFileDialog.getSaveFileName(self, "保存测试步骤", sequences_dir, "JSON files (*.json)")

        if not filepath:
            return

        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(self.sequence_data, f, indent=2, ensure_ascii=False)

            self.current_sequence_file_path = filepath
            self.is_sequence_modified = False
            self.update_title()
            QMessageBox.information(self, "保存成功", f"已保存到: {os.path.basename(filepath)}")
        except Exception as e:
            QMessageBox.critical(self, "保存失败", f"无法保存文件: {e}")

    @require_permission('file_save')
    def save_sequence(self):
        self.save_sequence_to_file(save_as=False)

    @require_permission('file_save_as')
    def save_sequence_as(self):
        self.save_sequence_to_file(save_as=True)

    def rebuild_ui_for_station_count(self):
        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            if widget := item.widget(): widget.deleteLater()
        self.station_frames.clear()
        
        # 使用 selected_stations 列表，向后兼容 station_count
        selected_stations = self.global_config.get('selected_stations', None)
        if selected_stations is None:
            # 向后兼容：如果没有 selected_stations，使用 station_count
            count = self.global_config.get('station_count', 4)
            selected_stations = [f"station_{i+1}" for i in range(count)]
        
        stations_config = self.global_config.get('stations', {})
        self.ordered_station_ids = sorted(selected_stations)  # 使用选中的工位
        
        frames_to_add = []
        for station_id in self.ordered_station_ids:
            station_cfg = stations_config.get(station_id, {})
            station_cfg['id'] = station_id
            frame = StationFrame(self, station_cfg, self.start_test, self, self.has_permission)
            self.station_frames[station_id] = frame
            frames_to_add.append(frame)
        
        count = len(frames_to_add)
        if count == 1 and frames_to_add:
            self.main_layout.addWidget(frames_to_add[0], 0, 0, 2, 2);
            self.main_layout.setRowStretch(0, 1);
            self.main_layout.setRowStretch(1, 0);
            self.main_layout.setColumnStretch(0, 1);
            self.main_layout.setColumnStretch(1, 0)
        elif count == 2 and len(frames_to_add) == 2:
            self.main_layout.addWidget(frames_to_add[0], 0, 0, 2, 1);
            self.main_layout.addWidget(frames_to_add[1], 0, 1, 2, 1);
            self.main_layout.setRowStretch(0, 1);
            self.main_layout.setRowStretch(1, 0);
            self.main_layout.setColumnStretch(0, 1);
            self.main_layout.setColumnStretch(1, 1)
        elif count == 3 and len(frames_to_add) == 3:
            self.main_layout.addWidget(frames_to_add[0], 0, 0);
            self.main_layout.addWidget(frames_to_add[1], 0, 1);
            self.main_layout.addWidget(frames_to_add[2], 1, 0, 1, 2);
            self.main_layout.setRowStretch(0, 1);
            self.main_layout.setRowStretch(1, 1);
            self.main_layout.setColumnStretch(0, 1);
            self.main_layout.setColumnStretch(1, 1)
        else:
            positions = [(0, 0), (0, 1), (1, 0), (1, 1)];
            for i, frame in enumerate(frames_to_add):
                if i < len(positions): self.main_layout.addWidget(frame, positions[i][0], positions[i][1])
            self.main_layout.setRowStretch(0, 1);
            self.main_layout.setRowStretch(1, 1);
            self.main_layout.setColumnStretch(0, 1);
            self.main_layout.setColumnStretch(1, 1)

        # 设置SN输入框之间的Tab顺序
        if len(frames_to_add) > 1:
            for i in range(len(frames_to_add) - 1):
                QWidget.setTabOrder(frames_to_add[i].sn_entry, frames_to_add[i+1].sn_entry)
            # 从最后一个跳回第一个，形成循环
        self.refresh_all_station_views()

        # 切换工位后，自动聚焦到第一个工位
        if self.ordered_station_ids:
            first_station_id = self.ordered_station_ids[0]
            if first_station_id in self.station_frames:
                self.station_frames[first_station_id].sn_entry.setFocus()

    @require_permission('edit_station_count')
    def _apply_station_selection(self, selected_stations):
        """应用工位选择配置并刷新界面"""
        if any(frame.active_thread for frame in self.station_frames.values()):
            QMessageBox.warning(self, "操作无效", "无法在测试期间更改工位选择。")
            return
        
        sorted_selection = sorted(selected_stations)
        self.global_config['selected_stations'] = sorted_selection
        self.global_config['station_count'] = len(selected_stations)
        self.save_global_config()
        
        # 更新所有复选框状态
        selection_tuple = tuple(sorted_selection)
        for combo, action in self.station_combo_actions.items():
            action.setChecked(combo == selection_tuple)
        
        self.rebuild_ui_for_station_count()

    def _on_theme_change(self, theme_file):
        """处理主题更改，立即应用新主题。"""
        self.global_config['ui_theme'] = theme_file
        self.save_global_config()
        
        # 立即应用新主题
        try:
            from qt_material import apply_stylesheet
            from PySide6.QtWidgets import QApplication
            from ui_components import COLOR_HIGHLIGHT_BG
            
            app = QApplication.instance()
            extra = {'density_scale': '-2'}
            apply_stylesheet(app, theme=theme_file, extra=extra)
            
            # 重新应用覆盖样式
            current_stylesheet = app.styleSheet()
            fixed_good_rule = f"selection-background-color: {COLOR_HIGHLIGHT_BG.name()};"
            fixed_stylesheet = current_stylesheet.replace("selection-background-color: #6effe8;", fixed_good_rule)
            
            override_stylesheet = f"""
                QTableView::item:selected, 
                QTableWidget::item:selected {{
                    background-color: {COLOR_HIGHLIGHT_BG.name()};
                }}
                QTableView::item:selected:focus, 
                QTableWidget::item:selected:focus {{
                     background-color: {COLOR_HIGHLIGHT_BG.name()};
                     color: white;
                }}
                QMenuBar::item:selected, 
                QMenuBar::item:pressed {{
                    background-color: {COLOR_HIGHLIGHT_BG.name()};
                    color: white;
                }}
                QMenu::item:selected {{
                    background-color: {COLOR_HIGHLIGHT_BG.name()};
                    color: white;
                }}
                QComboBox::item:selected {{
                    background-color: {COLOR_HIGHLIGHT_BG.name()};
                    color: white;
                }}
                QLineEdit#active_sn_input {{
                    background-color: #d9f7d9;
                    color: black;
                }}
            """
            app.setStyleSheet(fixed_stylesheet + override_stylesheet)
            QMessageBox.information(self, "主题已更改", f"主题已应用: {theme_file}")
        except Exception as e:
            QMessageBox.warning(self, "应用主题失败", f"无法应用主题，将在重启后生效。\n错误: {e}")

    def save_global_config(self):
        try:
            config_file_path = os.path.join(get_app_base_path(), 'config.json')
            with open(config_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.global_config, f, indent=4, ensure_ascii=False)
        except Exception as e:
            QMessageBox.critical(self, "错误", f"保存 config.json 失败: {e}");

    def has_permission(self, permission_id):
        """
        Checks if the current logged-in user has a specific permission.
        工程师(Engineer/Admin)角色自动拥有所有权限，新增任何权限均无需手动勾选。
        """
        if not self.user_info:
            return False

        # 工程师/管理员角色自动包含所有系统权限
        user_id = str(self.user_info.get('id', ''))
        user_name = str(self.user_info.get('name', ''))
        user_role = str(self.user_info.get('role', ''))

        if user_id in ['engineer', 'admin'] or '工程师' in user_name or '工程师' in user_role or 'admin' in user_role.lower():
            return True

        if not self.user_info.get('permissions'):
            return False

        return permission_id in self.user_info['permissions']

    def load_config(self):
        try:
            config_file_path = os.path.join(get_app_base_path(), 'config.json')
            if not os.path.exists(config_file_path):
                # 配置文件不存在，自动生成默认配置
                print(f"config.json 不存在，正在生成默认配置: {config_file_path}")
                default_config = TestApp._generate_default_config()
                with open(config_file_path, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=4, ensure_ascii=False)
                self.global_config = default_config
                QMessageBox.information(self, "提示", 
                    "未找到 config.json，已自动生成默认配置文件。\n请在「配置编辑器」中根据实际硬件进行配置。")
                return True
            with open(config_file_path, 'r', encoding='utf-8') as f:
                self.global_config = json.load(f)
            return True
        except Exception as e:
            QMessageBox.critical(self, "错误", f"加载 config.json 失败: {e}");
            return False

    @staticmethod
    def _generate_default_config():
        """生成默认的 config.json 配置"""
        stations = {}
        for i in range(1, 5):
            station_id = f"station_{i}"
            stations[station_id] = {
                "comm_port": "",
                "serial_params": {},
                "modbus_slaves": {
                    "daq_board": 5,
                    "servo_driver": 2,
                    "relay_board": 3,
                    "analog_board": 4
                },
                "dmm_visa_address": "",
                "dmm_auto_connect": False,
                "dmm_default_mode": "DCV",
                "power_control": {
                    "product": {"voltage": 0, "current": 0},
                    "battery": {"voltage": 0, "current": 0},
                    "daq": {"voltage": 0, "current": 0}
                }
            }
        
        return {
            "stations": stations,
            "station_count": 4,
            "selected_stations": ["station_1", "station_2", "station_3", "station_4"],
            "ui_theme": "dark_teal.xml",
            "serial_config": {
                "serial_mode": {
                    "mode": "independent",
                    "use_independent_mode": True,
                    "shared_config": {"port": "", "baudrate": 9600},
                    "independent_configs": {
                        f"station_{i}": {"port": "", "baudrate": 9600} for i in range(1, 5)
                    }
                }
            },
            "power_supply_mode": {
                "power_mode": {
                    "mode": "independent",
                    "use_independent_mode": True
                }
            },
            "jlink_config": {
                "jlink_path": "",
                "simulation_mode": False,
                "stations": {
                    f"station_{i}": {"jlink_sn": ""} for i in range(1, 5)
                }
            },
            "access_control": {
                "permissions_list": [
                    {"id": "file_new", "name": "新建文件"},
                    {"id": "file_save", "name": "保存文件"},
                    {"id": "file_save_as", "name": "另存为"},
                    {"id": "edit_test_sequence", "name": "编辑测试序列"},
                    {"id": "access_config_editor", "name": "访问配置编辑器"},
                    {"id": "edit_station_count", "name": "修改工位数量"},
                    {"id": "allow_cycle_test", "name": "循环压力测试"},
                    {"id": "manage_users", "name": "管理用户"},
                    {"id": "allow_debug", "name": "启用调试"}
                ],
                "users": {
                    "engineer": {
                        "name": "工程师",
                        "password": "dorna888",
                        "permissions": [
                            "file_new", "file_save", "file_save_as",
                            "edit_test_sequence", "access_config_editor",
                            "edit_station_count", "allow_cycle_test",
                            "manage_users", "allow_debug"
                        ]
                    },
                    "operator": {
                        "name": "操作员",
                        "password": "operator",
                        "permissions": ["file_save"]
                    }
                }
            }
        }

    def _sync_permissions_config(self):
        """
        Ensures that all permissions registered via decorators are present in the config file.
        New permissions are automatically granted to engineer role.
        """
        if not self.global_config.get('access_control'):
            return

        permissions_in_config = self.global_config['access_control'].get('permissions_list', [])
        permission_ids_in_config = {p['id'] for p in permissions_in_config}

        missing_permissions = REGISTERED_PERMISSIONS - permission_ids_in_config

        if not missing_permissions:
            return

        print(f"发现新的权限，正在自动添加到配置文件: {missing_permissions}")
        
        # 权限ID到中文名的映射
        permission_names = {
            'file_new': '新建文件',
            'file_save': '保存文件',
            'file_save_as': '另存为',
            'edit_test_sequence': '编辑测试序列',
            'access_config_editor': '访问配置编辑器',
            'edit_station_count': '修改工位数量',
            'allow_cycle_test': '循环压力测试',
            'manage_users': '管理用户',
            'access_sniffer_tool': '通信抓包工具', # Changed text from "串口抓包工具" to "通信抓包工具"
            'manage_thimble_usage': '顶针管理',
            'manage_cables': '线缆管理',
            'manage_recipes': '配方绑定管理',
            'access_time_prediction': '测试时间预测',
            'allow_debug': '启用调试'
        }

        for perm_id in missing_permissions:
            perm_name = permission_names.get(perm_id, perm_id)
            permissions_in_config.append({'id': perm_id, 'name': perm_name})
        
        # 自动授予全部已注册权限给工程师/管理员用户
        users = self.global_config['access_control'].get('users', {})
        all_permissions = set(REGISTERED_PERMISSIONS)
        for user_id, user_info in users.items():
            user_name = str(user_info.get('name', ''))
            user_role = str(user_info.get('role', ''))
            if user_id in ['engineer', 'admin'] or '工程师' in user_name or '工程师' in user_role or 'admin' in user_role.lower():
                user_permissions = set(user_info.get('permissions', []))
                user_permissions.update(all_permissions)
                user_info['permissions'] = sorted(list(user_permissions))
                print(f"已自动确保工程师/管理员用户 [{user_id}] 拥有全部系统权限 (共 {len(user_info['permissions'])} 项)")

        try:
            config_file_path = os.path.join(get_app_base_path(), 'config.json')
            with open(config_file_path, 'w', encoding='utf-8') as f:
                json.dump(self.global_config, f, indent=4, ensure_ascii=False)
            print("配置文件已更新，包含了新的权限。")
        except Exception as e:
            print(f"自动更新配置文件失败: {e}")

    def start_test(self, station_id, uut_sn, is_debugging, breakpoints, report_output_dir=None, work_order=None):
        frame = self.station_frames[station_id]
        operator_id = self.user_info['id'] if self.user_info else None
        operator_name = self.user_info['name'] if self.user_info else None  # 操作员姓名
        station_count = self.global_config.get('station_count', 4)  # 使用配置中的工位数
        
        # 【修复】如果没有传入工单号，使用全局工单号
        effective_work_order = work_order or self.current_work_order
        effective_target_qty = self.current_work_order_qty if effective_work_order else None
        
        adapter_cables = getattr(frame, 'current_adapter_cables', None)
        adapter_cable_life = getattr(frame, 'current_adapter_cable_life', None)

        thread = TestStation(station_id, uut_sn, self.global_config, self.hardware_manager, self.stop_all_event,
                             self.sequence_data, self.test_modules, is_debugging, breakpoints,
                             self.current_sequence_file_path, report_output_dir=report_output_dir,
                             operator_id=operator_id, operator_name=operator_name,
                             work_order=effective_work_order, target_qty=effective_target_qty,
                             station_count=station_count,
                             adapter_cables=adapter_cables,
                             adapter_cable_life=adapter_cable_life)
        thread.signals.step_update.connect(frame.update_step_in_view);
        thread.signals.final_status.connect(frame.on_test_finished);
        thread.signals.log.connect(frame.update_log);
        thread.signals.progress.connect(frame.progress_bar.setValue)
        if hasattr(thread.signals, 'paused_at'): thread.signals.paused_at.connect(frame.update_paused_at)
        # 连接用户交互信号
        if hasattr(thread.signals, 'user_interaction'):
            thread.signals.user_interaction.connect(self.on_user_interaction)
            
        frame.active_thread = thread;
        QThreadPool.globalInstance().start(thread)

    @Slot(dict)
    def on_user_interaction(self, data):
        """
        处理来自测试线程的用户交互请求（在主线程执行）。
        """
        station_id = data.get('station_id')
        interaction_type = data.get('type')
        kwargs = data.get('kwargs', {})
        event = data.get('event')
        request_id = data.get('request_id')
        
        # 获取父窗口（对应的工位Frame）
        parent_widget = self.station_frames.get(station_id, self)
        
        try:
            result = None
            
            # --- 辅助函数：居中弹框 ---
            def center_dialog(dialog, parent):
                if parent and parent != self:
                    # 获取父窗口中心
                    parent_center = parent.mapToGlobal(parent.rect().center())
                    # 获取对话框建议大小
                    size_hint = dialog.sizeHint()
                    # 计算左上角位置
                    x = parent_center.x() - size_hint.width() // 2
                    y = parent_center.y() - size_hint.height() // 2
                    dialog.move(x, y)
            
            if interaction_type == 'message_box':
                # --- new: 循环测试模式下自动处理 Warning ---
                if getattr(parent_widget, '_is_running_cycle_test', False) and \
                        kwargs.get('icon') == 'Warning' and \
                        kwargs.get('buttons') == 'OK':
                    print(f"[CycleTest] Auto-confirming alert on station {station_id}: {kwargs.get('message')}")
                    result = "OK"
                else: 
                    # --- original logic ---
                    title = kwargs.get('title', '提示')
                    message = kwargs.get('message', '')
                    buttons = kwargs.get('buttons', 'OK')
                    icon = kwargs.get('icon', 'Information')
                    
                    # 映射按钮
                    button_mapping = {
                        "OK": QMessageBox.Ok,
                        "OKCancel": QMessageBox.Ok | QMessageBox.Cancel,
                        "YesNo": QMessageBox.Yes | QMessageBox.No,
                        "YesNoCancel": QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                        "RetryCancel": QMessageBox.Retry | QMessageBox.Cancel,
                    }
                    
                    # 映射图标
                    icon_mapping = {
                        "Information": QMessageBox.Information,
                        "Warning": QMessageBox.Warning,
                        "Critical": QMessageBox.Critical,
                        "Question": QMessageBox.Question,
                        "NoIcon": QMessageBox.NoIcon,
                    }
                    
                    msg_box = QMessageBox(parent_widget)
                    msg_box.setWindowTitle(title)
                    msg_box.setText(message)
                    msg_box.setIcon(icon_mapping.get(icon, QMessageBox.Information))
                    msg_box.setStandardButtons(button_mapping.get(buttons, QMessageBox.Ok))
                    msg_box.setWindowModality(Qt.WindowModal)
                    
                    # 定位到工位中心
                    center_dialog(msg_box, parent_widget)
                    
                    # 执行并获取结果
                    ret = msg_box.exec()
                    
                    # 映射结果
                    # 直接使用 int 值进行比较，避免枚举类型不匹配的问题
                    response_mapping = {
                        int(QMessageBox.Ok): "OK",
                        int(QMessageBox.Cancel): "Cancel",
                        int(QMessageBox.Yes): "Yes",
                        int(QMessageBox.No): "No",
                        int(QMessageBox.Retry): "Retry",
                    }
                    
                    result = response_mapping.get(int(ret), "Unknown")

            elif interaction_type == 'input_box':
                title = kwargs.get('title', '输入')
                prompt = kwargs.get('prompt', '')
                default_value = kwargs.get('default_value', '')
                
                # 创建对话框实例
                input_dialog = QInputDialog(parent_widget)
                input_dialog.setWindowTitle(title)
                input_dialog.setLabelText(prompt)
                input_dialog.setTextValue(default_value)
                input_dialog.setWindowModality(Qt.WindowModal)
                # 【关键修复】设置输入模式为文本输入
                input_dialog.setInputMode(QInputDialog.TextInput)
                
                # 定位
                center_dialog(input_dialog, parent_widget)
                
                ok = input_dialog.exec()
                text = input_dialog.textValue()
                
                # QDialog.Accepted is 1
                if int(ok) == 1:
                    result = text
                else:
                    result = False

            _INTERACTION_RESULTS[request_id] = result
            
        except Exception as e:
            print(f"处理用户交互时出错: {e}")
            import traceback
            traceback.print_exc()
            if request_id:
                _INTERACTION_RESULTS[request_id] = None
        finally:
            # 必须设置事件，否则工作线程会永远阻塞
            if event:
                event.set()

    def refresh_all_station_views(self):
        for frame in self.station_frames.values():
            if hasattr(frame, 'load_sequence_to_view'): frame.load_sequence_to_view(self.sequence_data,
                                                                                    preserve_breakpoints=True)

    def update_title(self, modified=None):
        if modified is not None: self.is_sequence_modified = modified
        base_title = f"自动化测试平台 {APP_VERSION}"
        if self.user_info and self.user_info.get('id'):
            user_display = f"{self.user_info.get('name', '')} {self.user_info['id']}" if self.user_info.get('name') else self.user_info['id']
            base_title += f" - 用户: {user_display}"
        if self.current_sequence_file_path:
            title = f"{base_title} - 当前文件: {os.path.basename(self.current_sequence_file_path)}"
            if self.is_sequence_modified: title += " *"
        else:
            title = f"{base_title} - {'未命名步骤 *' if self.is_sequence_modified else '无测试步骤'}"
        self.setWindowTitle(title)

    @require_permission('allow_cycle_test')
    def open_cycle_test_dialog(self):
        """打开循环压力测试设置对话框"""
        if not self.sequence_data or not self.current_sequence_file_path:
            QMessageBox.warning(self, "无法开始", "请先打开一个测试程序，再进行循环压力测试。")
            return
        
        if any(frame.active_thread for frame in self.station_frames.values()):
            QMessageBox.warning(self, "操作无效", "无法在测试期间配置循环测试。")
            return

        # 获取当前激活的工位ID和测试序列
        active_station_ids = list(self.station_frames.keys())
        sequence_data = self.sequence_data
        
        dialog = CycleTestDialog(self, station_ids=active_station_ids, sequence_data=sequence_data)
        # 连接对话框的“开始”信号到主窗口的处理槽函数
        dialog.start_requested.connect(self.on_start_cycle_test)
        dialog.exec()

    def on_start_cycle_test(self, config):
        """
        接收到循环测试配置后，创建并启动后台控制器和前台控制窗口。
        """
        # 1. 将弹窗和控制器提升为实例属性
        self.cycle_control_dialog = CycleTestControlDialog(config['selected_stations'], self)
        self.cycle_test_controller = CycleTestController(main_app_instance=self, config=config)
        self.cyclic_test_config = config  # 保存配置，以便报告生成器使用

        # 2. 连接UI按钮和控制器方法
        self.cycle_control_dialog.abort_button.clicked.connect(self.cycle_test_controller.stop)

        # 3. 连接控制器的信号到主窗口的槽函数
        self.cycle_test_controller.signals.update_status_text.connect(self.cycle_control_dialog.update_status_text)
        self.cycle_test_controller.signals.update_running_time.connect(self.cycle_control_dialog.update_running_time)
        self.cycle_test_controller.signals.update_station_stats.connect(self.cycle_control_dialog.update_station_stats)
        self.cycle_test_controller.signals.finished.connect(self.on_cycle_finished)
        self.cycle_test_controller.signals.aborted.connect(self.on_cycle_aborted)

        # 4. 启动
        QThreadPool.globalInstance().start(self.cycle_test_controller)
        self.cycle_control_dialog.exec()  # 使用 exec() 以模态方式显示

    def on_cycle_finished(self, results):
        """
        循环测试正常完成的槽函数。
        【【【核心修改：独立的类方法，负责处理UI状态】】】
        """
        print("循环测试已完成。")

        # --- 新增: 收集报告所需的额外信息 (软件版本 / 顶针使用) ---
        if self.cyclic_test_config is None: self.cyclic_test_config = {}
        
        # 1. 软件版本
        self.cyclic_test_config['app_version'] = APP_VERSION
        
        # 2. 顶针使用情况 (遍历所有参与测试的工位)
        # 获取参与此次测试的工位列表 (result中的station_id)
        used_stations = sorted(list(set(r.get('station_id') for r in results if r.get('station_id'))))
        
        usage_lines = []
        for station_id in used_stations:
            info = self.thimble_manager.get_usage_info(self.current_sequence_file_path, station_id)
            usage_lines.append(f"[{station_id}] {info}")
            
        self.cyclic_test_config['thimble_usage_info'] = " | ".join(usage_lines)

        # 2. 生成并显示报告
        report_path = None
        if results:
            generator = ReportGenerator(results, self.cyclic_test_config)
            report_path = generator.generate_report()

        if report_path:
            self.cycle_control_dialog.show_completion_state(
                "循环测试已完成",
                "循环测试已完成。\n报告已生成。",
                report_path
            )
        else:
            self.cycle_control_dialog.show_completion_state(
                "循环测试已完成",
                "循环测试已完成，但生成报告失败。",
                None
            )

    def on_cycle_aborted(self, results):
        """
        循环测试被中止的槽函数。
        【【【核心修改：独立的类方法，逻辑与 on_cycle_finished 类似】】】
        """
        print("循环测试已被用户中止。")

        # 2. 如果有数据，则生成报告
        report_path = None
        if results:
            generator = ReportGenerator(results, self.cyclic_test_config)
            report_path = generator.generate_report()

        if report_path:
            self.cycle_control_dialog.show_completion_state(
                "循环测试已中止",
                "循环测试已中止。\n报告已生成。",
                report_path
            )
        else:
            self.cycle_control_dialog.show_completion_state(
                "循环测试已中止",
                "循环测试已中止，但生成报告失败。",
                None
            )

    def advance_focus_to_next_station(self, current_station_id):
        """将焦点移动到下一个空闲的工位，实现智能自动跳转。"""
        active_station_ids = sorted(self.station_frames.keys())
        if len(active_station_ids) <= 1:
            # 单工位模式，焦点回到当前工位
            frame = self.station_frames.get(current_station_id)
            if frame:
                frame.sn_entry.setFocus()
            return

        try:
            start_index = active_station_ids.index(current_station_id)
            # 遍历所有激活的工位，查找下一个没有正在运行测试的工位
            for i in range(len(active_station_ids)):
                next_index = (start_index + 1 + i) % len(active_station_ids)
                next_station_id = active_station_ids[next_index]
                
                next_frame = self.station_frames.get(next_station_id)
                # 检查工位是否空闲（没有正在运行的测试）
                if next_frame and next_frame.active_thread is None:
                    next_frame.sn_entry.setFocus()
                    return # 找到空闲工位，完成跳转并退出
        except (ValueError, IndexError) as e:
            print(f"无法跳转到下一个工位: {e}")

