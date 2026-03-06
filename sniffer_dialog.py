# sniffer_dialog.py

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QTextEdit, QPushButton, QHBoxLayout,
    QMessageBox, QLabel, QCheckBox, QTabWidget, QWidget
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from sniffer import sniffer_instance

class SnifferDialog(QDialog):
    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.setWindowTitle("通信抓包工具")
        self.setWindowFlags(self.windowFlags() | Qt.WindowMinimizeButtonHint)
        self.setMinimumSize(900, 700)
        self.setAttribute(Qt.WA_DeleteOnClose)

        # 存储每个工位的UI组件
        self.station_widgets = {}
        self.station_count = main_window.global_config.get('station_count', 4)
        
        self._init_ui()
        
        # 连接到sniffer的全局实例
        sniffer_instance.data_captured.connect(self.on_data_captured)

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        
        # 创建Tab Widget
        self.tab_widget = QTabWidget()
        
        # 为每个工位创建一个Tab
        for i in range(1, self.station_count + 1):
            station_id = f"station_{i}"
            tab = self._create_station_tab(station_id, i)
            self.tab_widget.addTab(tab, f"工位 {i}")
            
        main_layout.addWidget(self.tab_widget)

    def _create_station_tab(self, station_id, station_num):
        """为单个工位创建Tab页内容"""
        tab_widget = QWidget()
        layout = QVBoxLayout(tab_widget)
        
        # 显示区域
        display = QTextEdit()
        display.setReadOnly(True)
        display.setFont(QFont("Courier New", 10))
        
        # 控制按钮区域
        control_layout = QHBoxLayout()
        
        start_log_button = QPushButton("开始后台记录")
        stop_log_button = QPushButton("停止后台记录")
        stop_log_button.setEnabled(False)
        clear_button = QPushButton("清空显示")
        autoscroll_checkbox = QCheckBox("自动滚动")
        autoscroll_checkbox.setChecked(True)
        
        control_layout.addWidget(start_log_button)
        control_layout.addWidget(stop_log_button)
        control_layout.addStretch()
        control_layout.addWidget(clear_button)
        control_layout.addWidget(autoscroll_checkbox)
        
        # 状态标签
        status_label = QLabel(f"状态: 空闲")
        
        # 组装布局
        layout.addLayout(control_layout)
        layout.addWidget(display)
        layout.addWidget(status_label)
        
        # 保存组件引用
        self.station_widgets[station_id] = {
            'display': display,
            'start_button': start_log_button,
            'stop_button': stop_log_button,
            'clear_button': clear_button,
            'autoscroll': autoscroll_checkbox,
            'status_label': status_label,
            'logging': False
        }
        
        # 连接信号
        start_log_button.clicked.connect(lambda: self.start_logging(station_id))
        stop_log_button.clicked.connect(lambda: self.stop_logging(station_id))
        clear_button.clicked.connect(display.clear)
        
        return tab_widget

    def on_data_captured(self, timestamp, direction, port, data):
        """处理从sniffer实例接收到的数据的槽函数"""
        # 从port确定station_id
        station_id = sniffer_instance.port_to_station_map.get(port)
        if not station_id:
            context = sniffer_instance.port_context.get(port, {})
            station_id = context.get('station_id')
            
        if not station_id or station_id not in self.station_widgets:
            # 如果无法确定工位，则不显示（或显示在所有工位？）
            return
        
        widgets = self.station_widgets[station_id]
        display = widgets['display']
        
        # 添加彩色文本
        color = "blue" if direction == 'TX' else "green"
        html_line = f'<font color="{color}"><b>[{timestamp}] [{direction}] [{port}]</b></font> {data}'
        display.append(html_line)

        # 自动滚动
        if widgets['autoscroll'].isChecked():
            display.verticalScrollBar().setValue(display.verticalScrollBar().maximum())

    def start_logging(self, station_id):
        """为指定工位开始后台记录"""
        widgets = self.station_widgets[station_id]
        
        # 获取SN
        station_frame = self.main_window.station_frames.get(station_id)
        if station_frame:
            sn = station_frame.sn_entry.currentText() or "SN_Not_Available"
        else:
            sn = "SN_Frame_Error"
        
        # 启动文件记录（只记录这一个工位）
        success, message = sniffer_instance.start_station_logging(station_id, sn, self.main_window)
        
        if success:
            widgets['status_label'].setText(f"状态: 正在记录到 {message}")
            widgets['start_button'].setEnabled(False)
            widgets['stop_button'].setEnabled(True)
            widgets['logging'] = True
        else:
            QMessageBox.critical(self, "错误", f"无法开始记录日志: {message}")

    def stop_logging(self, station_id):
        """为指定工位停止后台记录"""
        widgets = self.station_widgets[station_id]
        
        sniffer_instance.stop_station_logging(station_id)
        
        widgets['status_label'].setText("状态: 空闲")
        widgets['start_button'].setEnabled(True)
        widgets['stop_button'].setEnabled(False)
        widgets['logging'] = False

    def closeEvent(self, event):
        """窗口关闭事件"""
        # 确保在关闭窗口时，如果仍在记录，则停止记录
        # 确保在关闭窗口时，如果仍在记录，则停止记录
        sniffer_instance.stop_all_logging()
        
        # 断开信号连接，防止内存泄漏
        try:
            sniffer_instance.data_captured.disconnect(self.on_data_captured)
        except (TypeError, RuntimeError) as e:
            # 如果信号已经断开，会抛出TypeError或RuntimeError，可以安全地忽略
            print(f"断开信号时出现预期中的错误: {e}")
            
        super().closeEvent(event)
