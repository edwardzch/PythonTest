import sys
import socket
import datetime
import re
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QLabel, QLineEdit, QPushButton,
                               QTextBrowser, QGroupBox, QMessageBox, QPlainTextEdit,
                               QSpinBox, QCheckBox, QFrame)
from PySide6.QtGui import QTextCursor, QColor

# -------------------------------------------------------------------------
#  样式表 (CSS)
# -------------------------------------------------------------------------
QSS_STYLE = """
QMainWindow { background-color: #1e1e2e; }
QWidget { font-family: "Segoe UI", "Microsoft YaHei", sans-serif; font-size: 14px; color: #cdd6f4; }
QGroupBox { border: 2px solid #313244; border-radius: 8px; margin-top: 20px; font-weight: bold; color: #89b4fa; }
QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 5px; }
QLineEdit, QPlainTextEdit, QSpinBox { background-color: #313244; border: 1px solid #45475a; border-radius: 4px; padding: 5px; color: #ffffff; }
QLineEdit:focus, QPlainTextEdit:focus, QSpinBox:focus { border: 1px solid #89b4fa; }
QPushButton { background-color: #45475a; border: none; border-radius: 4px; padding: 6px 12px; font-weight: bold; color: #ffffff; }
QPushButton:hover { background-color: #585b70; }
QPushButton:pressed { background-color: #313244; }
QPushButton#btn_connect { background-color: #a6e3a1; color: #1e1e2e; }
QPushButton#btn_disconnect { background-color: #f38ba8; color: #1e1e2e; }
QPushButton#btn_send { background-color: #89b4fa; color: #1e1e2e; }
QPushButton#btn_clear { background-color: #fab387; color: #1e1e2e; font-size: 12px; padding: 4px 8px;}
QPushButton#btn_start_loop { background-color: #a6e3a1; color: #1e1e2e; }
QPushButton#btn_stop_loop { background-color: #f38ba8; color: #1e1e2e; }
QTextBrowser { background-color: #181825; border: 1px solid #313244; border-radius: 6px; padding: 10px; }
"""


# -------------------------------------------------------------------------
#  后台通讯线程 - 修复了断开时的崩溃问题
# -------------------------------------------------------------------------
class TcpReceiver(QThread):
    signal_data_received = Signal(str)
    signal_error = Signal(str)
    signal_disconnected = Signal()

    def __init__(self, socket_obj):
        super().__init__()
        self.sock = socket_obj
        self.is_running = True

    def run(self):
        buffer_size = 4096
        while self.is_running:
            try:
                # 阻塞接收
                data = self.sock.recv(buffer_size)

                if not data:
                    # 收到空字节，通常意味着服务器断开，或者是本地close导致的
                    if self.is_running:
                        self.signal_disconnected.emit()
                    break

                # 解码
                try:
                    text = data.decode('utf-8', errors='ignore')
                except:
                    text = data.decode('ascii', errors='ignore')

                if self.is_running:
                    self.signal_data_received.emit(text)

            except (OSError, ConnectionAbortedError, ConnectionResetError) as e:
                # 关键修复：如果是因为用户点击了断开(is_running=False)，则忽略这个错误
                if not self.is_running:
                    break
                else:
                    self.signal_error.emit(f"连接异常: {str(e)}")
                    break
            except Exception as e:
                if self.is_running:
                    self.signal_error.emit(f"未知错误: {str(e)}")
                break

    def stop(self):
        """安全停止线程"""
        self.is_running = False
        # 注意：实际 socket 关闭操作由主线程完成，这里只改标志位
        # 线程会在 recv 抛出异常或返回空时退出


# -------------------------------------------------------------------------
#  主窗口逻辑
# -------------------------------------------------------------------------
class DriverController(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TCP 上位机助手 (脚本版)")
        self.resize(950, 800)
        self.setStyleSheet(QSS_STYLE)

        # TCP 变量
        self.tcp_socket = None
        self.recv_thread = None
        self.is_connected = False

        # 脚本执行引擎变量
        self.script_timer = QTimer()
        self.script_timer.setSingleShot(True)  # 设为单次触发，因为每次延时时间可能不同
        self.script_timer.timeout.connect(self.execute_next_step)

        self.parsed_tasks = []  # 解析后的任务列表 [{'type':'CMD', 'val':'...'}, {'type':'DELAY', 'val':5000}]
        self.current_step_index = 0
        self.current_loop_count = 0
        self.target_loop_count = 0
        self.loop_interval_ms = 1000

        self.init_ui()

    def init_ui(self):
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)

        # --- 1. 顶部设置 ---
        settings_group = QGroupBox("通讯设置")
        settings_layout = QHBoxLayout()
        self.ip_input = QLineEdit("192.168.57.10")
        self.port_input = QLineEdit("9006")
        self.port_input.setFixedWidth(80)
        self.btn_connect = QPushButton("连接")
        self.btn_connect.setObjectName("btn_connect")
        self.btn_connect.clicked.connect(self.toggle_connection)

        settings_layout.addWidget(QLabel("IP:"))
        settings_layout.addWidget(self.ip_input)
        settings_layout.addWidget(QLabel("Port:"))
        settings_layout.addWidget(self.port_input)
        settings_layout.addWidget(self.btn_connect)
        settings_group.setLayout(settings_layout)

        # --- 2. 日志区 ---
        log_group = QGroupBox("通讯日志")
        log_main_layout = QVBoxLayout()
        log_tool_layout = QHBoxLayout()
        log_tool_layout.addStretch()
        self.btn_clear_log = QPushButton("清除日志")
        self.btn_clear_log.setObjectName("btn_clear")
        self.btn_clear_log.clicked.connect(lambda: self.log_browser.clear())
        log_tool_layout.addWidget(self.btn_clear_log)

        self.log_browser = QTextBrowser()
        self.log_browser.setOpenExternalLinks(False)
        log_main_layout.addLayout(log_tool_layout)
        log_main_layout.addWidget(self.log_browser)
        log_group.setLayout(log_main_layout)

        # --- 3. 单条发送 ---
        single_cmd_layout = QHBoxLayout()
        self.cmd_input = QLineEdit()
        self.cmd_input.setPlaceholderText("单条指令...")
        self.cmd_input.returnPressed.connect(self.send_single_command)
        self.btn_send = QPushButton("发送 ➤")
        self.btn_send.setObjectName("btn_send")
        self.btn_send.clicked.connect(self.send_single_command)
        self.btn_toggle_extend = QPushButton("脚本模式 ▼")
        self.btn_toggle_extend.setCheckable(True)
        self.btn_toggle_extend.clicked.connect(self.toggle_extended_panel)

        single_cmd_layout.addWidget(self.cmd_input)
        single_cmd_layout.addWidget(self.btn_send)
        single_cmd_layout.addWidget(self.btn_toggle_extend)

        # --- 4. 扩展：脚本发送区 ---
        self.extended_widget = QWidget()
        self.extended_widget.setVisible(False)
        ext_layout = QVBoxLayout(self.extended_widget)
        ext_layout.setContentsMargins(0, 0, 0, 0)

        ext_group = QGroupBox("脚本循环任务 (Script Batch)")
        ext_group_layout = QHBoxLayout()

        # --- 修改部分：在这里设置新的默认文本 ---
        example_text = """flt
mtturnreset
#Delay 1000
flt
commode 0
opmode 0
paen 0
izero 2
zero 1
en
#Delay 8000
zerost
k
zero 0
#Delay 1000
en
#Delay 1000
active
j 60"""

        self.multi_cmd_input = QPlainTextEdit()
        self.multi_cmd_input.setPlaceholderText("输入指令...\n支持指令: #Delay 毫秒数")
        self.multi_cmd_input.setPlainText(example_text)  # 设置默认内容

        ctrl_panel = QVBoxLayout()

        # 循环间隔 (Loop Interval)
        row1 = QHBoxLayout()
        row1.addWidget(QLabel("循环间隔(ms):"))
        self.spin_interval = QSpinBox()
        self.spin_interval.setRange(0, 3600000)
        self.spin_interval.setValue(1000)
        self.spin_interval.setToolTip("每一轮指令全部发送完后，等待多久开始下一轮")
        row1.addWidget(self.spin_interval)
        ctrl_panel.addLayout(row1)

        # 循环次数
        row2 = QHBoxLayout()
        row2.addWidget(QLabel("循环次数:"))
        self.spin_count = QSpinBox()
        self.spin_count.setRange(0, 9999)
        self.spin_count.setValue(1)
        row2.addWidget(self.spin_count)
        ctrl_panel.addLayout(row2)
        ctrl_panel.addWidget(QLabel("(0 = 无限循环)"))

        # 进度显示
        self.lbl_status = QLabel("就绪")
        self.lbl_status.setStyleSheet("color: #fab387; font-size: 12px;")
        ctrl_panel.addWidget(self.lbl_status)
        ctrl_panel.addStretch()

        self.btn_start_loop = QPushButton("开始运行")
        self.btn_start_loop.setObjectName("btn_start_loop")
        self.btn_start_loop.clicked.connect(self.start_script)

        self.btn_stop_loop = QPushButton("停止运行")
        self.btn_stop_loop.setObjectName("btn_stop_loop")
        self.btn_stop_loop.setEnabled(False)
        self.btn_stop_loop.clicked.connect(self.stop_script)

        ctrl_panel.addWidget(self.btn_start_loop)
        ctrl_panel.addWidget(self.btn_stop_loop)

        ext_group_layout.addWidget(self.multi_cmd_input, stretch=3)
        ext_group_layout.addLayout(ctrl_panel, stretch=1)
        ext_group.setLayout(ext_group_layout)
        ext_layout.addWidget(ext_group)

        main_layout.addWidget(settings_group)
        main_layout.addWidget(log_group)
        main_layout.addLayout(single_cmd_layout)
        main_layout.addWidget(self.extended_widget)
        main_layout.setStretch(1, 10)

    # ------------------ UI 交互 ------------------
    def toggle_extended_panel(self):
        is_visible = self.btn_toggle_extend.isChecked()
        self.extended_widget.setVisible(is_visible)
        self.btn_toggle_extend.setText("脚本模式 ▲" if is_visible else "脚本模式 ▼")

    # ------------------ TCP 连接管理 (修复崩溃) ------------------
    def toggle_connection(self):
        if not self.is_connected:
            self.connect_tcp()
        else:
            self.disconnect_tcp()

    def connect_tcp(self):
        ip = self.ip_input.text().strip()
        try:
            port = int(self.port_input.text().strip())
        except:
            QMessageBox.warning(self, "错误", "端口号错误")
            return

        try:
            self.log_msg(f"正在连接到 {ip}:{port} ...", "system")
            self.tcp_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.tcp_socket.settimeout(2.0)
            self.tcp_socket.connect((ip, port))
            self.tcp_socket.settimeout(None)  # 恢复阻塞

            self.recv_thread = TcpReceiver(self.tcp_socket)
            self.recv_thread.signal_data_received.connect(self.handle_rx_data)
            self.recv_thread.signal_error.connect(self.handle_error)
            self.recv_thread.signal_disconnected.connect(self.handle_remote_disconnect)
            self.recv_thread.start()

            self.is_connected = True
            self.btn_connect.setText("断开")
            self.btn_connect.setObjectName("btn_disconnect")
            self.btn_connect.setStyle(self.btn_connect.style())
            self.ip_input.setEnabled(False)
            self.port_input.setEnabled(False)
            self.log_msg("连接成功！", "success")

        except Exception as e:
            self.log_msg(f"连接失败: {str(e)}", "error")
            if self.tcp_socket:
                self.tcp_socket.close()

    def disconnect_tcp(self):
        """
        优雅断开连接，防止崩溃
        """
        self.stop_script()  # 先停止脚本

        # 1. 标记线程停止
        if self.recv_thread:
            self.recv_thread.stop()

        # 2. 关闭 Socket
        if self.tcp_socket:
            try:
                # shutdown 能够强制打破 recv 的阻塞
                self.tcp_socket.shutdown(socket.SHUT_RDWR)
            except:
                pass
            try:
                self.tcp_socket.close()
            except:
                pass
            self.tcp_socket = None

        # 3. 等待线程结束（可选，PySide会自动清理）
        if self.recv_thread:
            self.recv_thread.wait(500)  # 等待最多500ms
            self.recv_thread = None

        self.is_connected = False
        self.btn_connect.setText("连接")
        self.btn_connect.setObjectName("btn_connect")
        self.btn_connect.setStyle(self.btn_connect.style())
        self.ip_input.setEnabled(True)
        self.port_input.setEnabled(True)
        self.log_msg("连接已断开", "system")

    def handle_remote_disconnect(self):
        self.log_msg("服务器主动断开连接", "error")
        self.disconnect_tcp()

    def handle_error(self, err_msg):
        self.log_msg(f"通讯错误: {err_msg}", "error")

    # ------------------ 发送逻辑 ------------------
    def send_raw_command(self, cmd_str):
        if not self.is_connected or not self.tcp_socket:
            return False

        full_cmd = cmd_str + "\r\n"
        try:
            self.tcp_socket.sendall(full_cmd.encode('utf-8'))
            self.log_msg(f"TX: {cmd_str}", "tx")
            return True
        except Exception as e:
            self.log_msg(f"发送失败: {str(e)}", "error")
            self.disconnect_tcp()
            return False

    def send_single_command(self):
        if not self.is_connected:
            QMessageBox.warning(self, "警告", "请先连接")
            return
        cmd = self.cmd_input.text()
        if cmd:
            self.send_raw_command(cmd)

    def handle_rx_data(self, text):
        clean_text = text.strip()
        if clean_text:
            self.log_msg(f"RX: {clean_text}", "rx")

    def log_msg(self, text, tag):
        timestamp = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        colors = {"tx": "#a6e3a1", "rx": "#89b4fa", "error": "#f38ba8", "success": "#a6e3a1", "system": "#fab387"}
        color = colors.get(tag, "#cdd6f4")
        self.log_browser.append(
            f'<span style="color:#6c7086;">[{timestamp}]</span> <span style="color:{color};">{text}</span>')
        self.log_browser.moveCursor(QTextCursor.End)

    # ------------------ 脚本执行引擎 (核心升级) ------------------

    def parse_script(self):
        """解析文本框内容为任务列表"""
        raw_text = self.multi_cmd_input.toPlainText()
        lines = [line.strip() for line in raw_text.split('\n') if line.strip()]
        tasks = []

        for line in lines:
            # 检查是否是 #Delay 指令 (不区分大小写)
            if line.lower().startswith("#delay"):
                try:
                    # 获取 #Delay 后面的数字
                    parts = line.split()
                    if len(parts) >= 2:
                        delay_val = int(parts[1])
                        tasks.append({'type': 'DELAY', 'val': delay_val, 'raw': line})
                    else:
                        self.log_msg(f"语法警告: {line} 缺少时间参数，默认忽略", "error")
                except ValueError:
                    self.log_msg(f"语法错误: {line} 时间必须是整数", "error")
            else:
                # 普通指令
                tasks.append({'type': 'CMD', 'val': line})
        return tasks

    def start_script(self):
        if not self.is_connected:
            QMessageBox.warning(self, "错误", "请先连接设备")
            return

        self.parsed_tasks = self.parse_script()
        if not self.parsed_tasks:
            QMessageBox.warning(self, "提示", "脚本内容为空")
            return

        # 初始化状态
        self.current_step_index = 0
        self.current_loop_count = 0
        self.target_loop_count = self.spin_count.value()
        self.loop_interval_ms = self.spin_interval.value()

        # UI 锁定
        self.btn_start_loop.setEnabled(False)
        self.btn_stop_loop.setEnabled(True)
        self.multi_cmd_input.setEnabled(False)
        self.spin_interval.setEnabled(False)
        self.spin_count.setEnabled(False)

        self.log_msg("--- 脚本任务开始 ---", "system")
        self.update_status()

        # 立即执行第一步
        self.execute_next_step()

    def stop_script(self):
        self.script_timer.stop()
        self.log_msg("--- 脚本任务停止 ---", "system")

        # UI 恢复
        self.btn_start_loop.setEnabled(True)
        self.btn_stop_loop.setEnabled(False)
        self.multi_cmd_input.setEnabled(True)
        self.spin_interval.setEnabled(True)
        self.spin_count.setEnabled(True)
        self.lbl_status.setText("就绪")

    def execute_next_step(self):
        """执行引擎的核心函数"""
        if not self.is_connected:
            self.stop_script()
            return

        # 1. 检查是否当前轮次已执行完所有指令
        if self.current_step_index >= len(self.parsed_tasks):
            # 本轮结束
            self.current_loop_count += 1

            # 检查总循环次数
            if self.target_loop_count > 0 and self.current_loop_count >= self.target_loop_count:
                self.log_msg("--- 所有循环已完成 ---", "success")
                self.stop_script()
                return
            else:
                # 还有下一轮，等待“循环间隔”
                self.current_step_index = 0
                self.log_msg(f"--- 第 {self.current_loop_count} 轮完成，等待 {self.loop_interval_ms}ms ---", "system")
                self.update_status()
                self.script_timer.start(self.loop_interval_ms)
                return

        # 2. 获取当前要执行的任务
        task = self.parsed_tasks[self.current_step_index]

        # 3. 根据任务类型执行
        if task['type'] == 'CMD':
            # 发送指令
            self.send_raw_command(task['val'])
            # 指向下一步
            self.current_step_index += 1
            self.update_status()
            # 普通指令之间给一个极短的缓冲(比如50ms)，防止粘包或发太快
            self.script_timer.start(50)

        elif task['type'] == 'DELAY':
            # 延时指令
            delay_ms = task['val']
            self.log_msg(f"等待 {delay_ms} ms...", "system")
            # 指向下一步
            self.current_step_index += 1
            self.update_status()
            # 启动定时器，时间到了再去执行下一条
            self.script_timer.start(delay_ms)

    def update_status(self):
        target_str = "∞" if self.target_loop_count == 0 else str(self.target_loop_count)
        self.lbl_status.setText(
            f"进度: 循环 {self.current_loop_count}/{target_str} | 步骤 {self.current_step_index}/{len(self.parsed_tasks)}")

    def closeEvent(self, event):
        self.disconnect_tcp()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = DriverController()
    window.show()
    sys.exit(app.exec())
