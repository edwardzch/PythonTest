import sys
import time
import math
import pyvisa
import os

# =============================================================================
# 1. 导入 PySide6 模块 (替代 PyQt6)
# =============================================================================
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox,
    QLabel, QLineEdit, QPushButton, QComboBox, QTextEdit, QMessageBox
)
from PySide6.QtCore import (
    Qt, QObject, QThread, Signal, QPropertyAnimation, QPointF, Property, QEasingCurve
)
from PySide6.QtGui import (
    QIcon, QDoubleValidator, QFont, QPainter, QColor, QPen, QBrush
)


# =============================================================================
# 自定义的现代化UI控件
# =============================================================================
class ToggleSwitch(QWidget):
    # 2. 使用 Signal 替代 pyqtSignal
    toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(50, 28)
        self._checked = False
        self._bg_color = QColor("#555")
        self._handle_color = QColor("#f0f0f0")
        self._checked_color = QColor("#16a085")
        self._handle_position = 0
        self.animation = QPropertyAnimation(self, b"handle_position", self)
        self.animation.setDuration(200)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutCubic)

    def set_checked_color(self, color):
        self._checked_color = QColor(color)

    # 3. 使用 Property 替代 pyqtProperty
    @Property(float)
    def handle_position(self):
        return self._handle_position

    @handle_position.setter
    def handle_position(self, pos):
        self._handle_position = pos
        self.update()

    def setChecked(self, checked):
        if self._checked != checked:
            self._checked = checked
            self.animation.setEndValue(1 if self._checked else 0)
            self.animation.start()
            self.toggled.emit(self._checked)

    def isChecked(self):
        return self._checked

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        track_rect = self.rect().adjusted(1, 1, -1, -1)
        bg_color = self._checked_color if self._checked else self._bg_color
        painter.setBrush(QBrush(bg_color))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(track_rect, 14, 14)
        handle_radius, handle_y = 12, self.height() / 2
        start_x, end_x = handle_radius, self.width() - handle_radius
        handle_x = start_x + (end_x - start_x) * self._handle_position
        painter.setBrush(QBrush(self._handle_color))
        painter.drawEllipse(QPointF(handle_x, handle_y), handle_radius, handle_radius)

    def mousePressEvent(self, event):
        self.setChecked(not self.isChecked())


# =============================================================================
# 后端与线程通信部分
# =============================================================================
class RigolDP832:
    def __init__(self, rm, resource_name):
        try:
            self.instrument = rm.open_resource(resource_name)
            self.instrument.read_termination, self.instrument.write_termination = '\n', '\n'
            self.instrument.timeout = 5000
            self.idn = self.instrument.query('*IDN?').strip()
            if 'DP832' not in self.idn:
                raise ValueError(f"设备不是 Rigol DP832: {self.idn}")
        except Exception as e:
            self.instrument = None
            raise ConnectionError(f"连接到 {resource_name} 失败: {e}")

    def close(self):
        if self.instrument:
            self.instrument.close()
            self.instrument = None

    def _write(self, command):
        self.instrument.write(command)

    def _query(self, command):
        return self.instrument.query(command).strip()

    def set_voltage(self, channel, voltage):
        self._write(f':SOUR{channel}:VOLT {voltage}')

    def set_current(self, channel, current):
        self._write(f':SOUR{channel}:CURR {current}')

    def get_measurements(self, channel):
        volt = float(self._query(f':MEAS:VOLT? CH{channel}'))
        curr = float(self._query(f':MEAS:CURR? CH{channel}'))
        return volt, curr

    def set_output(self, channel, state):
        self._write(f':OUTP CH{channel},{"ON" if state else "OFF"}')

    def get_output_state(self, channel):
        return self._query(f':OUTP? CH{channel}').strip() == 'ON'


class WorkerSignals(QObject):
    # 使用 Signal 替代 pyqtSignal
    data_ready = Signal(dict)
    error = Signal(str)
    finished = Signal()


class PollingWorker(QObject):
    def __init__(self, instrument):
        super().__init__()
        self.instrument = instrument
        self.signals = WorkerSignals()
        self._is_running = True

    def run(self):
        while self._is_running:
            try:
                all_data = {}
                for ch in range(1, 4):
                    volt, curr = self.instrument.get_measurements(ch)
                    state = self.instrument.get_output_state(ch)
                    all_data[ch] = {'volt': volt, 'curr': curr, 'state': state}
                if self._is_running:
                    self.signals.data_ready.emit(all_data)
                    time.sleep(1)
            except Exception as e:
                if self._is_running:
                    self.signals.error.emit(str(e))
                    break
        self.signals.finished.emit()

    def stop(self):
        self._is_running = False


# =============================================================================
# 前端: 主应用程序 GUI
# =============================================================================
class PowerSupplyApp(QWidget):
    def __init__(self, theme_color):
        super().__init__()
        self.theme_color = theme_color
        self.instrument = None
        # 注意：如果你的电脑没有安装 pyvisa-py 后端，请去掉 '@py'，直接使用 rm = pyvisa.ResourceManager()
        self.rm = pyvisa.ResourceManager('@py')
        self.polling_thread, self.polling_worker = None, None
        self.voltage_entries, self.current_entries = {}, {}
        self.output_switches, self.voltage_readouts, self.current_readouts = {}, {}, {}
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("Rigol DP832 电源控制器")
        self.setGeometry(100, 100, 950, 500)
        main_layout = QVBoxLayout(self)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        icon_path = os.path.join(script_dir, "DP832.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        conn_group = QGroupBox("连接")
        conn_layout = QHBoxLayout()
        self.device_combo = QComboBox()
        self.device_combo.setEditable(True)
        conn_layout.addWidget(self.device_combo)
        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.clicked.connect(self.refresh_devices)
        conn_layout.addWidget(self.refresh_btn)
        self.connect_btn = QPushButton("连接")
        self.connect_btn.clicked.connect(self.toggle_connection)
        conn_layout.addWidget(self.connect_btn)
        conn_group.setLayout(conn_layout)
        main_layout.addWidget(conn_group)

        channels_layout = QHBoxLayout()
        main_layout.addLayout(channels_layout)
        for i in range(1, 4):
            channels_layout.addWidget(self.create_channel_ui(i))

        log_group = QGroupBox("日志")
        log_layout = QVBoxLayout()
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.clear_log_btn = QPushButton("清除日志")
        self.clear_log_btn.clicked.connect(self.log_text.clear)
        log_layout.addWidget(self.clear_log_btn, alignment=Qt.AlignmentFlag.AlignRight)
        log_layout.addWidget(self.log_text)
        log_group.setLayout(log_layout)
        main_layout.addWidget(log_group)
        self.refresh_devices()

    def create_channel_ui(self, channel):
        ch_group = QGroupBox(f"通道 {channel}")
        ch_layout = QGridLayout()

        # 设置区域
        ch_layout.addWidget(QLabel("电压 (V):"), 0, 0)
        v_entry = QLineEdit()
        v_validator = QDoubleValidator(0.0, 99.0, 3, self)
        v_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        v_entry.setValidator(v_validator)
        ch_layout.addWidget(v_entry, 0, 1)
        self.voltage_entries[channel] = v_entry

        ch_layout.addWidget(QLabel("电流 (A):"), 1, 0)
        c_entry = QLineEdit()
        c_validator = QDoubleValidator(0.0, 99.0, 3, self)
        c_validator.setNotation(QDoubleValidator.Notation.StandardNotation)
        c_entry.setValidator(c_validator)
        ch_layout.addWidget(c_entry, 1, 1)
        self.current_entries[channel] = c_entry

        set_btn = QPushButton("应用设置")
        set_btn.clicked.connect(lambda _, ch=channel: self.apply_settings(ch))
        ch_layout.addWidget(set_btn, 2, 0, 1, 2)

        output_switch = ToggleSwitch()
        output_switch.set_checked_color(self.theme_color)
        output_switch.toggled.connect(lambda state, ch=channel: self.toggle_output(ch, state))
        ch_layout.addWidget(QLabel("输出:"), 3, 0)
        ch_layout.addWidget(output_switch, 3, 1)
        self.output_switches[channel] = output_switch

        # 数值回读区域
        ch_layout.addWidget(QLabel("<b>实时回读:</b>"), 4, 0, 1, 2)

        # 创建电压回读标签
        v_readout_label = QLabel("0.000 V")
        v_readout_label.setObjectName("readoutLabel")
        v_readout_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ch_layout.addWidget(v_readout_label, 5, 0, 1, 2)
        self.voltage_readouts[channel] = v_readout_label

        # 创建电流回读标签
        a_readout_label = QLabel("0.000 A")
        a_readout_label.setObjectName("readoutLabel")
        a_readout_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        ch_layout.addWidget(a_readout_label, 6, 0, 1, 2)
        self.current_readouts[channel] = a_readout_label

        ch_group.setLayout(ch_layout)
        ch_layout.setRowStretch(7, 1)
        return ch_group

    def apply_settings(self, channel):
        if not self.instrument:
            QMessageBox.warning(self, "操作警告", "请先连接到设备！")
            return
        v_max, a_max = (30.0, 3.0) if channel in [1, 2] else (5.0, 3.0)
        voltage_str = self.voltage_entries[channel].text()
        current_str = self.current_entries[channel].text()

        if not voltage_str or not current_str:
            QMessageBox.critical(self, "输入错误", f"通道{channel}的电压和电流值不能为空。")
            return

        try:
            voltage, current = float(voltage_str), float(current_str)
        except ValueError:
            QMessageBox.critical(self, "输入错误", "请输入有效的数字。")
            return

        if not (0 <= voltage <= v_max):
            QMessageBox.warning(self, "范围警告", f"通道 {channel} 电压超出范围！\n\n允许范围: 0V - {v_max}V")
            return
        if not (0 <= current <= a_max):
            QMessageBox.warning(self, "范围警告", f"通道 {channel} 电流超出范围！\n\n允许范围: 0A - {a_max}A")
            return

        try:
            self.instrument.set_voltage(channel, voltage)
            self.instrument.set_current(channel, current)
            self.log(f"通道{channel}: 已设置为 {voltage:.3f} V, {current:.3f} A。")
        except Exception as e:
            QMessageBox.critical(self, "仪器错误", f"设置通道{channel}时发生未知错误：\n{e}")
            self.log(f"设置通道{channel}时发生未知错误：{e}")

    def update_ui_from_poll(self, data):
        for ch, values in data.items():
            volt, curr, state = values['volt'], values['curr'], values['state']

            self.voltage_readouts[ch].setText(f"{volt:.3f} V")
            self.current_readouts[ch].setText(f"{curr:.3f} A")

            switch = self.output_switches[ch]
            if switch.isChecked() != state:
                switch.blockSignals(True)
                switch.setChecked(state)
                switch.blockSignals(False)

    def log(self, message):
        timestamp = time.strftime('%H:%M:%S')
        self.log_text.append(f"[{timestamp}] {message}")

    def refresh_devices(self):
        try:
            resources = self.rm.list_resources()
            current_text = self.device_combo.currentText()
            self.device_combo.clear()
            self.device_combo.addItems(resources)
            if current_text in resources:
                self.device_combo.setCurrentText(current_text)
            self.log("刷新设备列表成功。")
        except Exception as e:
            self.log(f"刷新设备列表时出错: {e}")

    def toggle_connection(self):
        if self.instrument:
            self.stop_polling()
            self.instrument.close()
            self.instrument = None
            self.connect_btn.setText("连接")
            self.log("已断开设备连接。")
            self.setWindowTitle("Rigol DP832 电源控制器")
        else:
            resource_name = self.device_combo.currentText()
            if not resource_name:
                QMessageBox.warning(self, "连接错误", "请先在下拉框中选择或输入一个设备地址。")
                return
            try:
                self.instrument = RigolDP832(self.rm, resource_name)
                self.connect_btn.setText("断开")
                self.log(f"成功连接到: {self.instrument.idn}")
                self.setWindowTitle(f"已连接 - {self.instrument.idn}")
                self.start_polling()
            except Exception as e:
                self.log(f"连接失败: {e}")
                QMessageBox.critical(self, "连接失败", f"无法连接到设备：\n{e}")
                self.instrument = None

    def toggle_output(self, channel, state):
        if not self.instrument: return
        try:
            self.instrument.set_output(channel, state)
            self.log(f"通道{channel}: 输出已{'打开' if state else '关闭'}。")
        except Exception as e:
            self.log(f"切换通道{channel}输出时出错: {e}")

    def start_polling(self):
        self.polling_thread = QThread()
        self.polling_worker = PollingWorker(self.instrument)
        self.polling_worker.moveToThread(self.polling_thread)
        self.polling_worker.signals.data_ready.connect(self.update_ui_from_poll)
        self.polling_worker.signals.error.connect(self.handle_polling_error)
        self.polling_worker.signals.finished.connect(self.polling_thread.quit)
        self.polling_worker.signals.finished.connect(self.polling_worker.deleteLater)
        self.polling_thread.finished.connect(self.polling_thread.deleteLater)
        self.polling_thread.started.connect(self.polling_worker.run)
        self.polling_thread.start()

    def stop_polling(self):
        if self.polling_worker:
            self.polling_worker.stop()
        if self.polling_thread and self.polling_thread.isRunning():
            self.polling_thread.quit()
            self.polling_thread.wait()

    def handle_polling_error(self, error_msg):
        self.log(f"轮询错误: {error_msg}。正在断开连接...")
        QMessageBox.critical(self, "通信中断", f"与设备的通信中断：\n{error_msg}\n\n将断开连接。")
        if self.instrument: self.toggle_connection()

    def closeEvent(self, event):
        self.stop_polling()
        if self.instrument: self.instrument.close()
        event.accept()


if __name__ == "__main__":
    app = QApplication(sys.argv)
    THEME_COLOR = "#16a085"

    qss = f"""
        QWidget {{ background-color: #1e1e1e; color: #dcdcdc; font-family: 'Segoe UI', 'Microsoft YaHei', 'Sans-Serif'; font-size: 10pt; }}
        QGroupBox {{ font-weight: bold; border: 1px solid #3c3c3c; border-radius: 5px; margin-top: 1ex; font-size: 11pt; }}
        QGroupBox::title {{ subcontrol-origin: margin; subcontrol-position: top left; padding: 0 5px; }}
        QLineEdit, QComboBox, QTextEdit {{ background-color: #2a2a2a; border: 1px solid #4a4a4a; border-radius: 4px; padding: 5px; color: #dcdcdc; }}
        QLineEdit:focus, QComboBox:focus, QTextEdit:focus {{ border-color: {THEME_COLOR}; }}
        QPushButton {{ background-color: {THEME_COLOR}; color: white; border: none; padding: 8px 16px; border-radius: 4px; font-weight: bold; }}
        QPushButton:hover {{ background-color: #1abc9c; }}
        QPushButton:pressed {{ background-color: #138a72; }}
        QScrollBar:vertical {{ background: #2a2a2a; width: 12px; }}
        QScrollBar::handle:vertical {{ background: #4a4a4a; border-radius: 6px; }}
        QScrollBar:horizontal {{ background: #2a2a2a; height: 12px; }}
        QScrollBar::handle:horizontal {{ background: #4a4a4a; border-radius: 6px; }}
        QMessageBox {{ background-color: #2a2a2a; }}

        /* 新增的样式，用于回读数值 */
        QLabel#readoutLabel {{
            font-size: 22pt;
            font-weight: bold;
            color: #ffffff;
            background-color: #2a2a2a;
            border-radius: 5px;
            padding: 10px;
            margin-top: 5px;
        }}
    """
    app.setStyleSheet(qss)
    window = PowerSupplyApp(theme_color=THEME_COLOR)
    window.show()
    sys.exit(app.exec())