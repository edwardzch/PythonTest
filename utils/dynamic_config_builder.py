from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
    QLineEdit, QCheckBox, QComboBox, QPushButton, QFileDialog
)
from PySide6.QtCore import Qt
import os
import serial.tools.list_ports

class SerialPortComboBox(QComboBox):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setEditable(True) # 允许手动输入，以防未检测到
        self._refresh_ports()

    def showPopup(self):
        self._refresh_ports()
        super().showPopup()

    def _refresh_ports(self):
        current_text = self.currentText()
        self.clear()
        ports = sorted(serial.tools.list_ports.comports())
        for port in ports:
            # port.device 是 COMx, port.description 是描述
            display_text = f"{port.device} - {port.description}"
            self.addItem(display_text, port.device) # UserData 存储纯 COMx
        
        # 恢复之前的选择（如果还在列表中）
        index = self.findData(current_text)
        if index >= 0:
            self.setCurrentIndex(index)
        else:
            self.setEditText(current_text)

class DynamicConfigBuilder:

    def __init__(self, parent_widget):
        self.parent = parent_widget
        self.widgets = {}  # key: widget
        self.schema = {}

    def build_ui(self, schema, layout, config_data=None):
        """
        根据 Schema 构建 UI。
        schema: dict, e.g. {"visa_address": {"type": "string", ...}}
        layout: QLayout, 控件将被添加到此布局中
        config_data: dict, 初始值
        """
        self.schema = schema
        self.widgets = {} # Reset widgets
        
        if config_data is None:
            config_data = {}

        row = 0
        # 使用 QGridLayout 如果传入的是 grid，否则使用 addWidget
        is_grid = isinstance(layout, QGridLayout)

        for key, field_def in schema.items():
            field_type = field_def.get('type', 'string')
            label_text = field_def.get('label', key)
            default_val = field_def.get('default')
            tooltip = field_def.get('tooltip', '')
            
            current_val = config_data.get(key, default_val)

            # 创建 Label
            label = QLabel(f"{label_text}:")
            if tooltip:
                label.setToolTip(tooltip)
            
            widget = None

            if field_type == 'string':
                widget = QLineEdit()
                widget.setText(str(current_val) if current_val is not None else "")
            
            elif field_type == 'int':
                widget = QLineEdit()
                widget.setText(str(current_val) if current_val is not None else "0")
                # TODO: Add IntValidator
            
            elif field_type == 'float':
                widget = QLineEdit()
                widget.setText(str(current_val) if current_val is not None else "0.0")
                # TODO: Add DoubleValidator

            elif field_type == 'bool':
                # 对于布尔值，Label 可以省略，或者放在 Checkbox 旁边
                widget = QCheckBox(label_text) # Checkbox 自带 Label
                widget.setChecked(bool(current_val))
                label = None # 不再需要单独的 Label

            elif field_type == 'select':
                widget = QComboBox()
                options = field_def.get('options', [])
                for opt in options:
                    widget.addItem(str(opt))
                widget.setCurrentText(str(current_val))

            elif field_type == 'file':
                line_edit = QLineEdit()
                line_edit.setText(str(current_val) if current_val is not None else "")
                browse_btn = QPushButton("...")
                browse_btn.setFixedWidth(30)
                # Fix: clicked emits (checked), so we need to accept it to avoid overriding w
                browse_btn.clicked.connect(lambda checked=False, w=line_edit: self._browse_file(w))
                
                # 使用容器包裹
                container = QWidget()
                h_layout = QHBoxLayout(container)
                h_layout.addWidget(line_edit)
                h_layout.addWidget(browse_btn)
                h_layout.setContentsMargins(0,0,0,0)
                
                widget = container # 用于添加到界面布局
                self.widgets[key] = line_edit # 用于获取值

            elif field_type == 'directory':
                line_edit = QLineEdit()
                line_edit.setText(str(current_val) if current_val is not None else "")
                browse_btn = QPushButton("...")
                browse_btn.setFixedWidth(30)
                # Fix: clicked emits (checked), so we need to accept it to avoid overriding w
                browse_btn.clicked.connect(lambda checked=False, w=line_edit: self._browse_directory(w))
                
                # 使用容器包裹
                container = QWidget()
                h_layout = QHBoxLayout(container)
                h_layout.addWidget(line_edit)
                h_layout.addWidget(browse_btn)
                h_layout.setContentsMargins(0,0,0,0)
                
                widget = container # 用于添加到界面布局
                self.widgets[key] = line_edit # 用于获取值

            elif field_type == 'visa':
                # VISA 地址选择器（下拉框 + 刷新按钮）
                from PySide6.QtWidgets import QSizePolicy
                
                combo = QComboBox()
                combo.setEditable(True)  # 允许手动输入
                combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                
                refresh_btn = QPushButton("刷新")
                refresh_btn.setFixedWidth(50)
                
                def refresh_visa_resources(cb=combo):
                    try:
                        import pyvisa
                        rm = pyvisa.ResourceManager()
                        resources = rm.list_resources()
                        current_text = cb.currentText()
                        cb.clear()
                        for res in resources:
                            cb.addItem(res)
                        # 恢复之前的选择
                        if current_text:
                            idx = cb.findText(current_text)
                            if idx >= 0:
                                cb.setCurrentIndex(idx)
                            else:
                                cb.setEditText(current_text)
                    except Exception as e:
                        print(f"扫描 VISA 资源失败: {e}")
                
                refresh_btn.clicked.connect(lambda checked=False, cb=combo: refresh_visa_resources(cb))
                
                # 初始加载 VISA 资源
                refresh_visa_resources(combo)
                
                # 设置当前值
                if current_val:
                    idx = combo.findText(str(current_val))
                    if idx >= 0:
                        combo.setCurrentIndex(idx)
                    else:
                        combo.setEditText(str(current_val))
                
                # 容器
                container = QWidget()
                h_layout = QHBoxLayout(container)
                h_layout.addWidget(combo)
                h_layout.addWidget(refresh_btn)
                h_layout.setContentsMargins(0,0,0,0)
                
                widget = container
                self.widgets[key] = combo  # 保存 combo 用于获取值

            elif field_type == 'serial_port':
                widget = SerialPortComboBox()
                # 设置 SizePolicy 为 Expanding，确保在 Grid 中拉伸
                from PySide6.QtWidgets import QSizePolicy
                widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                
                # 如果有当前值，尝试设置
                if current_val:
                    # 尝试找到匹配的 COM 口
                    index = widget.findData(str(current_val))
                    if index >= 0:
                        widget.setCurrentIndex(index)
                    else:
                        widget.setEditText(str(current_val))
            
            elif field_type == 'channel':
                # 通道选择器（1-4 通道或自定义范围）
                from PySide6.QtWidgets import QSpinBox
                widget = QSpinBox()
                min_ch = field_def.get('min', 1)
                max_ch = field_def.get('max', 4)
                widget.setRange(min_ch, max_ch)
                widget.setValue(int(current_val) if current_val else min_ch)
            
            elif field_type == 'baudrate':
                # 波特率选择器（常用波特率列表）
                widget = QComboBox()
                baudrates = field_def.get('options', [9600, 19200, 38400, 57600, 115200, 230400, 460800, 921600])
                for br in baudrates:
                    widget.addItem(str(br))
                widget.setEditable(True)  # 允许手动输入
                widget.setCurrentText(str(current_val) if current_val else "115200")
            
            elif field_type == 'voltage':
                # 电压输入（带单位和范围）
                from PySide6.QtWidgets import QDoubleSpinBox
                widget = QDoubleSpinBox()
                widget.setRange(field_def.get('min', 0), field_def.get('max', 32))
                widget.setDecimals(field_def.get('decimals', 2))
                widget.setSuffix(" V")
                widget.setValue(float(current_val) if current_val else field_def.get('default', 5.0))
            
            elif field_type == 'current':
                # 电流输入（带单位和范围）
                from PySide6.QtWidgets import QDoubleSpinBox
                widget = QDoubleSpinBox()
                widget.setRange(field_def.get('min', 0), field_def.get('max', 10))
                widget.setDecimals(field_def.get('decimals', 3))
                widget.setSuffix(" A")
                widget.setValue(float(current_val) if current_val else field_def.get('default', 1.0))
            
            else:
                # 默认情况，或者未知类型，不操作 widget (保持为 None)
                pass
            
            if widget:
                if tooltip:
                    widget.setToolTip(tooltip)
                
                # 如果不是特殊处理的控件（如 file），则直接保存引用
                if key not in self.widgets:
                    self.widgets[key] = widget

                if is_grid:
                    if label:
                        layout.addWidget(label, row, 0)
                        layout.addWidget(widget, row, 1)
                    else:
                        layout.addWidget(widget, row, 0, 1, 2) # 跨两列
                else:
                    # 使用 QHBoxLayout 时，默认会左右拉伸。
                    # 为了让 Label 和 Widget 紧凑，我们可以不使用嵌套 Layout，而是直接 addWidget 到父 Layout (如果是 VBox)
                    # 但 DynamicConfigBuilder 无法确定父 Layout 是 VBox 还是 HBox。
                    # 假设父 Layout 是 VBox (通常是这样)，我们希望每一行是一个 Label + Widget
                    
                    row_layout = QHBoxLayout()
                    if label:
                        row_layout.addWidget(label)
                        # 设置 Label 的固定宽度或策略，防止它占用过多空间? 
                        # 不，用户抱怨的是间隔远，说明中间有 Stretch。
                        # 默认 QHBoxLayout 没有 Stretch，除非 Widget 自己有。
                        
                    row_layout.addWidget(widget)
                    # 添加 Stretch 可能会把它们推到左边，或者推开？
                    # 如果父 Layout 很宽，Widget 会被拉伸。
                    # 如果用户觉得间隔远，可能是 Label 占位太宽？
                    # 或者是因为之前的实现没有对齐。
                    
                    # 尝试：不加 Stretch，让 Widget 自动填充剩余空间。
                    # 关键是：如果这是在一个很宽的 GroupBox 里，Widget 应该拉伸。
                    
                    layout.addLayout(row_layout)
                
                row += 1

    def _browse_file(self, line_edit):
        path, _ = QFileDialog.getOpenFileName(self.parent, "选择文件")
        if path:
            line_edit.setText(path)

    def _browse_directory(self, line_edit):
        path = QFileDialog.getExistingDirectory(self.parent, "选择文件夹")
        if path:
            line_edit.setText(path)

    def get_config(self):
        """从控件中获取当前配置值，并根据 Schema 转换类型。"""
        config = {}
        for key, field_def in self.schema.items():
            widget = self.widgets.get(key)
            if not widget:
                continue
            
            value = None
            field_type = field_def.get('type', 'string')

            if isinstance(widget, QLineEdit):
                text = widget.text()
                if field_type == 'int':
                    try: value = int(text)
                    except: value = 0
                elif field_type == 'float':
                    try: value = float(text)
                    except: value = 0.0
                else:
                    value = text
            
            elif isinstance(widget, QCheckBox):
                value = widget.isChecked()
            
            elif isinstance(widget, SerialPortComboBox):
                # 优先取 UserData (COMx)，如果为空（手动输入），取 Text
                data = widget.currentData()
                if data:
                    value = data
                else:
                    # 如果是 "COM1 - Description" 这种格式（用户没选下拉，直接默认显示的），
                    # 或者用户手动输入了 "COM1"
                    text = widget.currentText()
                    if " - " in text:
                        value = text.split(" - ")[0]
                    else:
                        value = text

            elif isinstance(widget, QComboBox):
                text = widget.currentText()
                if field_type == 'int' or field_type == 'baudrate':
                    try: value = int(text)
                    except: value = text
                else:
                    value = text
            
            # 处理 QSpinBox (channel 类型)
            from PySide6.QtWidgets import QSpinBox, QDoubleSpinBox
            if isinstance(widget, QSpinBox):
                value = widget.value()
            elif isinstance(widget, QDoubleSpinBox):
                value = widget.value()
            
            config[key] = value
        
        return config
