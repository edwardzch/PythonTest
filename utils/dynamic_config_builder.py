from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, 
    QLineEdit, QCheckBox, QComboBox, QPushButton, QFileDialog, QSizePolicy
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
        # 【修复】保存之前选择的端口值（UserData 或手动输入的文本）
        current_data = self.currentData()  # 如果是下拉选择的，这是 COMx
        current_text = self.currentText()  # 显示文本或手动输入
        
        # 提取纯端口名：如果是 "COM5 - Description" 格式，提取 "COM5"
        if current_data:
            port_to_restore = current_data
        elif " - " in current_text:
            port_to_restore = current_text.split(" - ")[0]
        else:
            port_to_restore = current_text
        
        self.clear()
        ports = sorted(serial.tools.list_ports.comports())
        for port in ports:
            # port.device 是 COMx, port.description 是描述
            display_text = f"{port.device} - {port.description}"
            self.addItem(display_text, port.device) # UserData 存储纯 COMx
        
        # 恢复之前的选择（使用端口名匹配）
        index = self.findData(port_to_restore)
        if index >= 0:
            self.setCurrentIndex(index)
        elif port_to_restore:
            self.setEditText(port_to_restore)

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

        from PySide6.QtWidgets import QSizePolicy
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

            elif field_type in ('serial_port', 'serial', 'port'):
                widget = SerialPortComboBox()
                if current_val:
                    idx = widget.findData(str(current_val))
                    if idx >= 0:
                        widget.setCurrentIndex(idx)
                    else:
                        widget.setEditText(str(current_val))

            elif field_type in ('select', 'choice', 'combo'):
                widget = QComboBox()
                options = field_def.get('choices', field_def.get('options', []))
                for opt in options:
                    widget.addItem(str(opt))
                if current_val is not None:
                    widget.setCurrentText(str(current_val))

            elif field_type in ('info_box', 'banner', 'label_card'):
                from PySide6.QtWidgets import QFrame
                card = QFrame()
                card.setObjectName("infoCard")
                card.setStyleSheet("""
                    QFrame#infoCard {
                        background-color: rgba(0, 200, 150, 0.08);
                        border: 1px solid rgba(0, 200, 150, 0.35);
                        border-radius: 6px;
                    }
                """)
                card_layout = QVBoxLayout(card)
                card_layout.setContentsMargins(12, 10, 12, 10)
                info_lbl = QLabel(field_def.get('text', label_text))
                info_lbl.setStyleSheet("color: #00E6A0; font-size: 13px; font-weight: 500;")
                info_lbl.setWordWrap(True)
                card_layout.addWidget(info_lbl)
                widget = card
                label = None

            elif field_type == 'local_ip_button':
                line_edit = QLineEdit()
                line_edit.setText(str(current_val) if current_val is not None else "")
                
                ip_btn = QPushButton("显示本机 IP")
                # ip_btn.setFixedWidth(90)
                
                def show_local_ips():
                    import socket
                    import subprocess
                    import re
                    from PySide6.QtWidgets import QMessageBox
                    try:
                        hostname = socket.gethostname()
                        
                        # Use ipconfig to get both descriptions and IP addresses
                        result = subprocess.run(['ipconfig', '/all'], capture_output=True, text=True, encoding='gbk', errors='ignore')
                        output = result.stdout
                        
                        # Simple parser for ipconfig output
                        adapters = []
                        current_adapter = ""
                        current_ip = ""
                        
                        for line in output.split('\n'):
                            line = line.strip()
                            if line.endswith(':'):  # Adapter name/description section header
                                if current_adapter and current_ip:
                                    adapters.append(f"{current_adapter}\n  -> {current_ip}")
                                current_adapter = line[:-1]
                                current_ip = ""
                            elif "描述" in line or "Description" in line:
                                desc = line.split(':', 1)[-1].strip()
                                current_adapter = f"[{desc}]"
                            elif "IPv4 地址" in line or "IPv4 Address" in line:
                                ip_match = re.search(r'(\d+\.\d+\.\d+\.\d+)', line)
                                if ip_match:
                                    current_ip = ip_match.group(1)
                                    
                        # add the last one
                        if current_adapter and current_ip:
                             adapters.append(f"{current_adapter}\n  -> {current_ip}")

                        if adapters:
                             ip_list_str = "\n\n".join(adapters)
                        else:
                             # Fallback if ipconfig fails to parse
                             _, _, ip_addresses = socket.gethostbyname_ex(hostname)
                             valid_ips = [ip for ip in ip_addresses if not ip.startswith("127.")]
                             ip_list_str = "\n".join(valid_ips)

                        QMessageBox.information(
                            self.parent, 
                            "本机 IP 地址", 
                            f"主机名: {hostname}\n\n检测到的适配器和IP:\n\n{ip_list_str}"
                        )
                    except Exception as e:
                        QMessageBox.warning(self.parent, "错误", f"获取 IP 地址失败: {e}")
                        
                ip_btn.clicked.connect(lambda checked=False: show_local_ips())
                
                container = QWidget()
                h_layout = QHBoxLayout(container)
                h_layout.addWidget(line_edit)
                h_layout.addWidget(ip_btn)
                h_layout.setContentsMargins(0,0,0,0)
                
                widget = container
                self.widgets[key] = line_edit


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
                # VISA 地址选择器（点击下拉框时自动刷新）
                # 自定义 VISA ComboBox，点击时自动刷新
                class VisaComboBox(QComboBox):
                    def __init__(self, parent=None):
                        super().__init__(parent)
                        self.setEditable(True)
                        
                    def showPopup(self):
                        self._refresh_visa()
                        super().showPopup()
                        
                    def _refresh_visa(self):
                        try:
                            import pyvisa
                            # 优先尝试 @py 后端（支持 USB 设备），失败则回退到默认后端
                            try:
                                rm = pyvisa.ResourceManager('@py')
                            except ValueError:
                                rm = pyvisa.ResourceManager()  # 回退到 NI-VISA
                            
                            resources = list(rm.list_resources('?*'))
                            print(f"[VISA] pyvisa 检测到: {resources}")
                            
                            # 【关键修复】手动检测 USB INSTR 设备（pyvisa-py 有时无法枚举）
                            try:
                                import libusb_package
                                libusb_package.get_libusb1_backend()
                                import usb.core
                                
                                # 常见仪器厂商的 USB Vendor ID
                                usb_instrument_vendors = {
                                    0x1ab1: "Rigol",       # Rigol (DP832, DS1000Z, etc.)
                                    0xf4ed: "Siglent",     # Siglent
                                    0x5345: "Keysight",    # Keysight/Agilent
                                    0x0957: "Agilent",     # Agilent
                                    0x0699: "Tektronix",   # Tektronix
                                    0x164e: "GW Instek",   # GW Instek
                                }
                                
                                for vendor_id, vendor_name in usb_instrument_vendors.items():
                                    devices = usb.core.find(find_all=True, idVendor=vendor_id)
                                    for dev in devices:
                                        try:
                                            serial = dev.serial_number or "???"
                                            product_id = dev.idProduct
                                            # 构建 VISA 资源名称
                                            visa_addr = f"USB0::{vendor_id}::{product_id}::{serial}::0::INSTR"
                                            print(f"[VISA] 检测到 USB 设备: {visa_addr}")
                                            if visa_addr not in resources:
                                                resources.append(visa_addr)
                                        except Exception as e:
                                            print(f"[VISA] 读取 USB 设备信息失败: {e}")
                            except ImportError as e:
                                print(f"[VISA] libusb 导入失败: {e}")
                            except Exception as e:
                                print(f"[VISA] 手动 USB 检测失败: {e}")
                            
                            print(f"[VISA] 最终列表: {resources}")
                            current_text = self.currentText()
                            self.clear()
                            for res in resources:
                                self.addItem(res)
                            if current_text:
                                idx = self.findText(current_text)
                                if idx >= 0:
                                    self.setCurrentIndex(idx)
                                else:
                                    self.setEditText(current_text)
                        except Exception as e:
                            print(f"[VISA] 扫描失败: {e}")
                
                combo = VisaComboBox()
                combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                
                # 设置当前值
                if current_val:
                    combo.setEditText(str(current_val))
                
                widget = combo
                self.widgets[key] = combo

            elif field_type == 'visa_with_connect':
                # VISA 地址选择器（点击刷新）+ 启动时连接
                from PySide6.QtWidgets import QSizePolicy
                
                # 自定义 VISA ComboBox，点击时自动刷新
                class VisaComboBox(QComboBox):
                    def __init__(self, parent=None):
                        super().__init__(parent)
                        self.setEditable(True)
                        
                    def showPopup(self):
                        self._refresh_visa()
                        super().showPopup()
                        
                    def _refresh_visa(self):
                        try:
                            import pyvisa
                            # 优先尝试 @py 后端（支持 USB 设备），失败则回退到默认后端
                            try:
                                rm = pyvisa.ResourceManager('@py')
                            except ValueError:
                                rm = pyvisa.ResourceManager()  # 回退到 NI-VISA
                            
                            resources = list(rm.list_resources('?*'))
                            
                            # 【关键修复】手动检测 USB INSTR 设备
                            try:
                                import libusb_package
                                libusb_package.get_libusb1_backend()
                                import usb.core
                                usb_vendors = {0x1ab1: "Rigol", 0xf4ed: "Siglent", 0x5345: "Keysight", 0x0957: "Agilent", 0x0699: "Tektronix", 0x164e: "GW Instek"}
                                for vid, _ in usb_vendors.items():
                                    for dev in usb.core.find(find_all=True, idVendor=vid):
                                        try:
                                            visa_addr = f"USB0::{vid}::{dev.idProduct}::{dev.serial_number or '???'}::0::INSTR"
                                            if visa_addr not in resources: resources.append(visa_addr)
                                        except: pass
                            except: pass
                            
                            current_text = self.currentText()
                            self.clear()
                            for res in resources:
                                self.addItem(res)
                            if current_text:
                                idx = self.findText(current_text)
                                if idx >= 0:
                                    self.setCurrentIndex(idx)
                                else:
                                    self.setEditText(current_text)
                        except Exception as e:
                            print(f"扫描 VISA 资源失败: {e}")
                
                combo = VisaComboBox()
                combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                
                auto_connect_check = QCheckBox("启动时连接")
                
                # 【关键修复】current_val 可能是字典 {visa_address: "...", auto_connect_on_startup: bool}
                if isinstance(current_val, dict):
                    visa_address = current_val.get('visa_address', field_def.get('default', ''))
                    connect_config = current_val.get('auto_connect_on_startup', field_def.get('auto_connect_default', False))
                else:
                    # 兼容旧格式：current_val 直接是地址字符串
                    visa_address = current_val if current_val else field_def.get('default', '')
                    connect_config = config_data.get('auto_connect_on_startup', field_def.get('auto_connect_default', False))
                
                auto_connect_check.setChecked(bool(connect_config))
                
                if visa_address:
                    combo.setEditText(str(visa_address))

                
                # 容器：VISA下拉 + 启动时连接（无刷新按钮）
                container = QWidget()
                h_layout = QHBoxLayout(container)
                h_layout.addWidget(combo, 1)
                h_layout.addWidget(auto_connect_check)
                h_layout.setContentsMargins(0,0,0,0)
                
                widget = container
                self.widgets[key] = {
                    'type': 'visa_with_connect',
                    'combo': combo,
                    'auto_connect': auto_connect_check
                }
            
            elif field_type == 'channel_config':
                # 通道配置表格（电压、电流、启动时打开）
                from PySide6.QtWidgets import QGroupBox, QDoubleSpinBox
                
                channel_count = field_def.get('channel_count', 4)
                channel_configs = config_data.get(key, {})
                
                channel_container = QWidget()
                channel_layout = QGridLayout(channel_container)
                channel_layout.setSpacing(6)
                channel_layout.setContentsMargins(0, 0, 0, 0)
                
                # 设置列拉伸（让输入框列拉伸，标签列固定）
                channel_layout.setColumnStretch(1, 1)  # 电压输入列拉伸
                channel_layout.setColumnStretch(3, 1)  # 电流输入列拉伸
                
                channel_widgets = {}
                for ch in range(1, channel_count + 1):
                    ch_key = f"CH{ch}"
                    ch_config = channel_configs.get(ch_key, {})
                    row = ch - 1  # 从第0行开始
                    
                    # 通道标签 + 电压
                    ch_label = QLabel(f"通道 {ch} 电压:")
                    channel_layout.addWidget(ch_label, row, 0)
                    
                    voltage_spin = QDoubleSpinBox()
                    voltage_spin.setRange(0, field_def.get('max_voltage', 32))
                    voltage_spin.setDecimals(2)
                    voltage_spin.setSuffix(" V")
                    voltage_spin.setValue(ch_config.get('voltage', 5.0))
                    channel_layout.addWidget(voltage_spin, row, 1)
                    
                    # 电流
                    current_label = QLabel("电流:")
                    channel_layout.addWidget(current_label, row, 2)
                    
                    current_spin = QDoubleSpinBox()
                    current_spin.setRange(0, field_def.get('max_current', 3.2))
                    current_spin.setDecimals(3)
                    current_spin.setSuffix(" A")
                    current_spin.setValue(ch_config.get('current', 1.0))
                    channel_layout.addWidget(current_spin, row, 3)
                    
                    # 启动时打开
                    enable_check = QCheckBox("启动时打开")
                    enable_check.setChecked(ch_config.get('enable_on_startup', False))
                    channel_layout.addWidget(enable_check, row, 4)
                    
                    channel_widgets[ch_key] = {
                        'voltage': voltage_spin,
                        'current': current_spin,
                        'enable_on_startup': enable_check
                    }
                
                self.widgets[key] = {
                    'type': 'channel_config',
                    'channels': channel_widgets
                }
                
                widget = channel_container
                label = None

                widget = channel_container
                label = None

            elif field_type == 'supply_channel_mapping':
                # 供电通道映射（用于 DP832 独立模式，将功能映射到通道）
                from PySide6.QtWidgets import QSpinBox
                
                mapping_container = QWidget()
                mapping_layout = QGridLayout(mapping_container)
                mapping_layout.setSpacing(6)
                mapping_layout.setContentsMargins(0, 0, 0, 0)
                
                supply_types = field_def.get('supply_types', {
                    'product': "产品供电",
                    'battery': "电池供电",
                    'daq': "采集卡供电"
                })
                
                # 当前配置: {'product': {'channel': 1}, ...}
                current_mappings = config_data.get(key, {})
                # 兼容旧格式或空值
                if not isinstance(current_mappings, dict):
                    current_mappings = {}

                mapping_widgets = {}
                row = 0
                
                # 默认通道分配
                default_channels = {'product': 1, 'daq': 2, 'battery': 3}
                
                for supply_key, supply_label in supply_types.items():
                    mapping_layout.addWidget(QLabel(f"{supply_label}:"), row, 0)
                    
                    ch_spin = QSpinBox()
                    ch_spin.setRange(1, field_def.get('max_channels', 3))
                    ch_spin.setPrefix("CH ")
                    
                    # 获取当前值
                    supply_cfg = current_mappings.get(supply_key, {})
                    current_ch = supply_cfg.get('channel', default_channels.get(supply_key, 1))
                    ch_spin.setValue(int(current_ch))
                    
                    mapping_layout.addWidget(ch_spin, row, 1)
                    
                    mapping_widgets[supply_key] = {'channel': ch_spin}
                    row += 1
                
                self.widgets[key] = {
                    'type': 'supply_channel_mapping',
                    'mappings': mapping_widgets
                }
                
                widget = mapping_container
                label = None

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
            
            elif field_type == 'jlink_sn':
                # J-Link SN 选择器，支持自动检测已连接的 J-Link
                class JLinkSNComboBox(QComboBox):
                    def __init__(self, parent=None):
                        super().__init__(parent)
                        self.setEditable(True)
                        # 不在初始化时自动刷新，只在点击下拉框时刷新
                        
                    def showPopup(self):
                        self._refresh_jlinks()
                        super().showPopup()
                        
                    def _refresh_jlinks(self):
                        import subprocess
                        import os
                        import re
                        
                        current_text = self.currentText()
                        self.clear()
                        
                        # 下拉框只显示当前连接的设备，不显示已保存的值
                        
                        try:
                            # 使用 J-Link Commander 获取已连接的设备
                            jlink_path = None
                            for path in [
                                r'C:\Program Files\SEGGER\JLink\JLink.exe',
                                r'C:\Program Files (x86)\SEGGER\JLink\JLink.exe',
                            ]:
                                if os.path.exists(path):
                                    jlink_path = path
                                    break
                            
                            if jlink_path and os.path.exists(jlink_path):
                                # 创建临时脚本让 J-Link 列出设备后退出
                                import tempfile
                                with tempfile.NamedTemporaryFile(mode='w', suffix='.jlink', delete=False) as f:
                                    f.write('ShowEmuList\nq\n')
                                    script_path = f.name
                                
                                try:
                                    result = subprocess.run(
                                        [jlink_path, '-CommanderScript', script_path],
                                        capture_output=True, text=True, timeout=5,
                                        creationflags=subprocess.CREATE_NO_WINDOW
                                    )
                                    
                                    # 解析输出中的 S/N 信息
                                    # 格式: "J-Link[0]: Connection: USB, Serial number: 601025137"
                                    for line in result.stdout.split('\n'):
                                        match = re.search(r'Serial number[:\s]+(\d+)', line, re.IGNORECASE)
                                        if match:
                                            sn = match.group(1)
                                            # 只添加连接的设备
                                            if sn not in [self.itemText(i) for i in range(self.count())]:
                                                self.addItem(sn)
                                finally:
                                    os.unlink(script_path)
                        except Exception as e:
                            print(f"扫描 J-Link 设备失败: {e}")
                        
                        # 恢复输入框中已保存的值（即使它不在下拉列表中）
                        if current_text:
                            self.setEditText(current_text)
                
                widget = JLinkSNComboBox()
                from PySide6.QtWidgets import QSizePolicy
                widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                
                if current_val:
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
            
            elif field_type == 'multi_psu_config':
                # 多电源专用配置（多台电源 + 电源类型映射 + 工位映射）
                from PySide6.QtWidgets import QGroupBox, QDoubleSpinBox, QSpinBox, QSizePolicy
                
                psu_ids = field_def.get('psu_ids', ['PSU_1', 'PSU_2'])
                supply_types = field_def.get('supply_types', {
                    'battery_supply': '电池供电',
                    'daq_supply': '采集卡供电'
                })
                station_count = field_def.get('station_count', 4)
                max_channels = field_def.get('max_channels', 3)
                
                psu_config = config_data.get(key, {})
                
                # 主容器
                main_container = QWidget()
                main_layout = QVBoxLayout(main_container)
                main_layout.setSpacing(15)  # 增加组间间距
                main_layout.setContentsMargins(0, 0, 0, 0)
                
                # ===== 电源设备配置区域 =====
                psu_group = QGroupBox("电源设备配置")
                psu_layout = QVBoxLayout(psu_group)
                psu_layout.setSpacing(8)
                psu_widgets = {}
                
                # 自定义 VISA ComboBox，点击时自动刷新
                class VisaComboBox(QComboBox):
                    def __init__(self, parent=None):
                        super().__init__(parent)
                        self.setEditable(True)
                        
                    def showPopup(self):
                        self._refresh_visa()
                        super().showPopup()
                        
                    def _refresh_visa(self):
                        try:
                            import pyvisa
                            try:
                                rm = pyvisa.ResourceManager('@py')
                            except ValueError:
                                rm = pyvisa.ResourceManager()
                            
                            resources = list(rm.list_resources('?*'))
                            
                            # 手动检测 USB INSTR 设备
                            try:
                                import libusb_package; libusb_package.get_libusb1_backend()
                                import usb.core
                                usb_vendors = {0x1ab1: "Rigol", 0xf4ed: "Siglent", 0x5345: "Keysight", 0x0957: "Agilent"}
                                for vid, _ in usb_vendors.items():
                                    for dev in usb.core.find(find_all=True, idVendor=vid):
                                        try:
                                            visa_addr = f"USB0::{vid}::{dev.idProduct}::{dev.serial_number or '???'}::0::INSTR"
                                            if visa_addr not in resources: resources.append(visa_addr)
                                        except: pass
                            except: pass
                            
                            current_text = self.currentText()
                            self.clear()
                            for res in resources:
                                self.addItem(res)
                            if current_text:
                                idx = self.findText(current_text)
                                if idx >= 0:
                                    self.setCurrentIndex(idx)
                                else:
                                    self.setEditText(current_text)
                        except Exception as e:
                            print(f"扫描 VISA 资源失败: {e}")
                
                for psu_id in psu_ids:
                    psu_item_layout = QHBoxLayout()
                    psu_item_layout.addWidget(QLabel(f"{psu_id} VISA 地址:"))
                    
                    visa_combo = VisaComboBox()
                    visa_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                    psu_data = psu_config.get('power_supplies', {}).get(psu_id, {})
                    visa_val = psu_data.get('visa_address', '')
                    if visa_val:
                        visa_combo.setEditText(str(visa_val))
                    
                    auto_connect = QCheckBox("启动时连接")
                    auto_connect.setChecked(psu_data.get('auto_connect_on_startup', True))
                    
                    psu_item_layout.addWidget(visa_combo, 1)
                    psu_item_layout.addWidget(auto_connect)
                    psu_layout.addLayout(psu_item_layout)
                    
                    psu_widgets[psu_id] = {
                        'visa_combo': visa_combo,
                        'auto_connect': auto_connect
                    }
                
                main_layout.addWidget(psu_group)
                
                # ===== 电源基础配置（电池供电/采集卡供电）=====
                startup_group = QGroupBox("电源基础配置 (启动时设置)")
                startup_layout = QGridLayout(startup_group)
                startup_layout.setSpacing(10)  # 增加间距
                startup_layout.setContentsMargins(10, 15, 10, 10)
                
                # 设置列拉伸（输入框列均分）
                startup_layout.setColumnStretch(1, 1)  # 电源型号
                startup_layout.setColumnStretch(3, 1)  # 通道
                startup_layout.setColumnStretch(5, 1)  # 电压
                startup_layout.setColumnStretch(7, 1)  # 电流
                
                startup_settings = psu_config.get('power_startup_settings', {})
                startup_widgets = {}
                
                for row, (type_key, type_name) in enumerate(supply_types.items()):
                    type_cfg = startup_settings.get(type_key, {})
                    
                    # 供电类型 + 电源型号
                    startup_layout.addWidget(QLabel(f"{type_name} 电源:"), row, 0)
                    psu_combo = QComboBox()
                    psu_combo.addItems(psu_ids)
                    psu_combo.setCurrentText(type_cfg.get('psu_id', psu_ids[0]))
                    startup_layout.addWidget(psu_combo, row, 1)
                    
                    # 通道
                    startup_layout.addWidget(QLabel("通道:"), row, 2)
                    ch_spin = QSpinBox()
                    ch_spin.setRange(1, max_channels)
                    ch_spin.setValue(type_cfg.get('channel', 1))
                    startup_layout.addWidget(ch_spin, row, 3)
                    
                    # 电压
                    startup_layout.addWidget(QLabel("电压:"), row, 4)
                    volt_spin = QDoubleSpinBox()
                    volt_spin.setRange(0, 30)
                    volt_spin.setDecimals(2)
                    volt_spin.setSuffix(" V")
                    volt_spin.setValue(type_cfg.get('voltage', 5.0))
                    startup_layout.addWidget(volt_spin, row, 5)
                    
                    # 电流
                    startup_layout.addWidget(QLabel("电流:"), row, 6)
                    curr_spin = QDoubleSpinBox()
                    curr_spin.setRange(0, 3)
                    curr_spin.setDecimals(3)
                    curr_spin.setSuffix(" A")
                    curr_spin.setValue(type_cfg.get('current', 1.0))
                    startup_layout.addWidget(curr_spin, row, 7)
                    
                    # 启动时启用
                    enable_check = QCheckBox("启动时启用")
                    enable_check.setChecked(type_cfg.get('enabled', False))
                    startup_layout.addWidget(enable_check, row, 8)
                    
                    startup_widgets[type_key] = {
                        'psu_id': psu_combo,
                        'channel': ch_spin,
                        'voltage': volt_spin,
                        'current': curr_spin,
                        'enabled': enable_check
                    }
                
                main_layout.addWidget(startup_group)
                
                # ===== 工位产品供电映射 =====
                mapping_group = QGroupBox("工位产品供电映射")
                mapping_layout = QGridLayout(mapping_group)
                mapping_layout.setSpacing(10)  # 增加间距
                mapping_layout.setContentsMargins(10, 15, 10, 10)
                
                # 设置列拉伸
                mapping_layout.setColumnStretch(1, 1)
                mapping_layout.setColumnStretch(3, 1)
                
                power_control = psu_config.get('power_control', {})
                mapping_widgets = {}
                
                for i in range(1, station_count + 1):
                    station_id = f"station_{i}"
                    station_cfg = power_control.get(station_id, {}).get('product', {})
                    row = i - 1
                    
                    # 工位 + 电源型号
                    mapping_layout.addWidget(QLabel(f"工位 {i} 电源:"), row, 0)
                    psu_combo = QComboBox()
                    psu_combo.addItems(psu_ids)
                    psu_combo.setCurrentText(station_cfg.get('psu_id', psu_ids[0]))
                    mapping_layout.addWidget(psu_combo, row, 1)
                    
                    # 通道
                    mapping_layout.addWidget(QLabel("通道:"), row, 2)
                    ch_spin = QSpinBox()
                    ch_spin.setRange(1, max_channels)
                    ch_spin.setValue(station_cfg.get('channel', 1))
                    mapping_layout.addWidget(ch_spin, row, 3)
                    
                    mapping_widgets[station_id] = {
                        'psu_id': psu_combo,
                        'channel': ch_spin
                    }
                
                main_layout.addWidget(mapping_group)
                main_layout.addStretch()
                
                self.widgets[key] = {
                    'type': 'multi_psu_config',
                    'psu_widgets': psu_widgets,
                    'startup_widgets': startup_widgets,
                    'mapping_widgets': mapping_widgets,
                    'psu_ids': psu_ids
                }
                
                widget = main_container
                label = None
            
            elif field_type == 'mode_switch':
                # 模式切换组件（共享/独立/专用模式）
                from PySide6.QtWidgets import QGroupBox, QRadioButton, QButtonGroup, QStackedWidget, QSizePolicy
                
                mode_group = QGroupBox(label_text)
                mode_layout = QVBoxLayout(mode_group)
                mode_layout.setSpacing(5)
                mode_layout.setContentsMargins(10, 10, 10, 10)
                
                # 创建单选按钮（水平排列）
                radio_container = QWidget()
                radio_layout = QHBoxLayout(radio_container)
                radio_layout.setContentsMargins(0, 0, 0, 0)
                radio_layout.setSpacing(20)
                
                shared_radio = QRadioButton(field_def.get('shared_label', '共享模式'))
                independent_radio = QRadioButton(field_def.get('independent_label', '独立模式'))
                dedicated_radio = None
                
                button_group = QButtonGroup(mode_group)
                button_group.addButton(shared_radio, 0)
                button_group.addButton(independent_radio, 1)
                
                radio_layout.addWidget(shared_radio)
                radio_layout.addWidget(independent_radio)
                
                # 检查是否有专用模式配置
                dedicated_schema = field_def.get('dedicated_schema')
                if dedicated_schema is not None:
                    dedicated_radio = QRadioButton(field_def.get('dedicated_label', '专用模式'))
                    button_group.addButton(dedicated_radio, 2)
                    radio_layout.addWidget(dedicated_radio)
                
                radio_layout.addStretch()  # 左对齐
                mode_layout.addWidget(radio_container)
                
                # 设置默认值
                # 【关键修复】从 current_val 读取 mode，而不是 config_data
                mode_config = current_val if isinstance(current_val, dict) else {}
                current_mode = mode_config.get('mode', 'shared')
                if current_mode == 'independent' or mode_config.get('use_independent_mode', False):
                    independent_radio.setChecked(True)
                elif current_mode == 'dedicated' and dedicated_radio:
                    dedicated_radio.setChecked(True)
                else:
                    shared_radio.setChecked(True)
                
                # 创建堆叠容器用于切换显示
                stacked = QStackedWidget()
                stacked.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                
                # === 共享模式子配置 ===
                shared_widget = QWidget()
                shared_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                shared_layout_inner = QVBoxLayout(shared_widget)
                shared_layout_inner.setSpacing(10)
                shared_layout_inner.setContentsMargins(0, 0, 0, 0)
                shared_layout_inner.setAlignment(Qt.AlignTop)
                
                shared_schema = field_def.get('shared_schema', {})
                # 【关键修复】从 mode_config 读取共享配置
                shared_config = mode_config.get(field_def.get('shared_config_key', 'shared_config'), {})
                shared_builder = DynamicConfigBuilder(self.parent)
                
                shared_grid = QGridLayout()
                shared_grid.setSpacing(10)
                shared_builder.build_ui(shared_schema, shared_grid, shared_config)
                shared_layout_inner.addLayout(shared_grid)
                shared_layout_inner.addStretch()
                
                stacked.addWidget(shared_widget)
                
                # === 独立模式子配置（按工位 2x2）===
                independent_widget = QWidget()
                independent_layout = QGridLayout(independent_widget)
                independent_layout.setSpacing(10)
                independent_layout.setContentsMargins(0, 0, 0, 0)
                independent_schema = field_def.get('independent_schema', {})
                station_count = field_def.get('station_count', 4)
                
                station_builders = {}
                for i in range(1, station_count + 1):
                    station_id = f"station_{i}"
                    station_group = QGroupBox(f"工位 {i}")
                    station_layout_inner = QGridLayout(station_group)
                    station_layout_inner.setSpacing(6)
                    
                    # 【关键修复】从 mode_config 读取独立配置
                    station_config = mode_config.get('independent_configs', {}).get(station_id, {})
                    station_builder = DynamicConfigBuilder(self.parent)
                    station_builder.build_ui(independent_schema, station_layout_inner, station_config)
                    station_builders[station_id] = station_builder
                    
                    row_pos = (i - 1) // 2
                    col_pos = (i - 1) % 2
                    independent_layout.addWidget(station_group, row_pos, col_pos)
                
                stacked.addWidget(independent_widget)
                
                # === 专用模式子配置 ===
                dedicated_builder = None
                if dedicated_schema is not None:
                    dedicated_widget = QWidget()
                    dedicated_layout = QVBoxLayout(dedicated_widget)
                    dedicated_layout.setSpacing(15)  # 与共享模式一致的间距
                    dedicated_layout.setContentsMargins(0, 0, 0, 0)
                    # 不设置对齐，让内容自然拉伸
                    
                    # 【关键修复】从 mode_config 读取专用配置
                    dedicated_config = mode_config.get('dedicated_config', {})
                    dedicated_builder = DynamicConfigBuilder(self.parent)
                    
                    # 直接使用 VBoxLayout 构建，不用 grid
                    dedicated_builder.build_ui(dedicated_schema, dedicated_layout, dedicated_config)
                    dedicated_layout.addStretch()
                    
                    stacked.addWidget(dedicated_widget)
                
                mode_layout.addWidget(stacked)
                
                # 连接信号
                def on_mode_changed(button_id):
                    stacked.setCurrentIndex(button_id)
                button_group.idClicked.connect(on_mode_changed)
                
                # 设置初始显示
                if independent_radio.isChecked():
                    stacked.setCurrentIndex(1)
                elif dedicated_radio and dedicated_radio.isChecked():
                    stacked.setCurrentIndex(2)
                else:
                    stacked.setCurrentIndex(0)
                
                # 存储复合组件
                self.widgets[key] = {
                    'type': 'mode_switch',
                    'button_group': button_group,
                    'shared_builder': shared_builder,
                    'station_builders': station_builders,
                    'dedicated_builder': dedicated_builder,
                    'shared_config_key': field_def.get('shared_config_key', 'shared_config'),
                    'has_dedicated': dedicated_schema is not None,
                }
                
                widget = mode_group
                label = None
            
            elif field_type == 'group':
                # 嵌套配置组
                from PySide6.QtWidgets import QGroupBox
                
                group_box = QGroupBox(label_text)
                group_layout = QGridLayout(group_box)
                
                sub_schema = field_def.get('schema', {})
                sub_config = config_data.get(key, {}) if isinstance(config_data.get(key), dict) else {}
                
                sub_builder = DynamicConfigBuilder(self.parent)
                sub_builder.build_ui(sub_schema, group_layout, sub_config)
                
                self.widgets[key] = {
                    'type': 'group',
                    'builder': sub_builder
                }
                
                widget = group_box
                label = None
            
            elif field_type == 'station_group':
                # 按工位配置组（2x2 布局）
                from PySide6.QtWidgets import QGroupBox
                
                station_container = QWidget()
                station_layout_outer = QGridLayout(station_container)
                station_layout_outer.setSpacing(10)
                
                sub_schema = field_def.get('schema', {})
                station_count = field_def.get('station_count', 4)
                config_key = field_def.get('config_key', key)
                
                station_builders = {}
                for i in range(1, station_count + 1):
                    station_id = f"station_{i}"
                    station_box = QGroupBox(f"工位 {i}")
                    station_inner_layout = QGridLayout(station_box)
                    
                    # 【修复】从 config_data 中当前 key 获取配置
                    # 支持两种结构：
                    # 1. 扁平结构: config_data[key].station_X
                    # 2. 嵌套结构: config_data[key].stations.station_X (由旧版 station_group 保存时产生)
                    stations_data = config_data.get(key, {})
                    
                    # 处理嵌套结构：如果 stations_data 包含 'stations' 键
                    if 'stations' in stations_data:
                        stations_data = stations_data.get('stations', {})
                    
                    station_data = stations_data.get(station_id, {})
                    station_config = station_data
                    
                    builder = DynamicConfigBuilder(self.parent)
                    builder.build_ui(sub_schema, station_inner_layout, station_config)
                    station_builders[station_id] = builder
                    
                    # 2x2 布局：上面12，下面34
                    row_pos = (i - 1) // 2
                    col_pos = (i - 1) % 2
                    station_layout_outer.addWidget(station_box, row_pos, col_pos)
                
                self.widgets[key] = {
                    'type': 'station_group',
                    'builders': station_builders,
                    'config_key': config_key
                }
                
                widget = station_container
                label = QLabel(f"{label_text}:") if field_def.get('show_label', False) else None
            
            elif field_type == 'modbus_slave_editor':
                # Modbus 从站设备编辑器（设备名称 + 从站地址表格）
                from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView
                
                slave_container = QWidget()
                slave_layout = QVBoxLayout(slave_container)
                slave_layout.setContentsMargins(0, 0, 0, 0)
                slave_layout.setSpacing(5)
                
                # 获取当前配置
                slaves_data = current_val if isinstance(current_val, dict) else {}
                
                # 表格
                table = QTableWidget(0, 2)
                table.setHorizontalHeaderLabels(["设备名称 (英文)", "从站地址"])
                table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
                table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
                table.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                table.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                
                # 填充表格
                for name, addr in slaves_data.items():
                    row = table.rowCount()
                    table.insertRow(row)
                    table.setItem(row, 0, QTableWidgetItem(str(name)))
                    table.setItem(row, 1, QTableWidgetItem(str(addr)))
                
                # 自适应高度
                def update_table_height():
                    row_count = table.rowCount()
                    header_height = table.horizontalHeader().height()
                    row_height = table.verticalHeader().defaultSectionSize()
                    total_height = header_height + (row_height * max(row_count, 1)) + 4
                    table.setMinimumHeight(total_height)
                    table.setMaximumHeight(total_height)
                update_table_height()
                
                slave_layout.addWidget(table)
                
                # 按钮
                btn_layout = QHBoxLayout()
                add_btn = QPushButton("添加设备")
                del_btn = QPushButton("删除选中")
                
                def add_row():
                    row = table.rowCount()
                    table.insertRow(row)
                    table.setItem(row, 0, QTableWidgetItem("new_device"))
                    table.setItem(row, 1, QTableWidgetItem("1"))
                    update_table_height()
                
                def del_row():
                    current_row = table.currentRow()
                    if current_row >= 0:
                        table.removeRow(current_row)
                        update_table_height()
                
                add_btn.clicked.connect(add_row)
                del_btn.clicked.connect(del_row)
                btn_layout.addWidget(add_btn)
                btn_layout.addWidget(del_btn)
                btn_layout.addStretch()
                slave_layout.addLayout(btn_layout)
                
                self.widgets[key] = {
                    'type': 'modbus_slave_editor',
                    'table': table
                }
                
                widget = slave_container
                label = QLabel(f"{label_text}:") if label_text else None

            elif field_type in ('relay_channel_editor', 'single_channel_editor'):
                # 自定义Modbus功能/函数映射编辑器
                # 共享模式: 8列 (包含工位1~4地址)
                # 独立模式: 5列 (单工位物理地址)
                from PySide6.QtWidgets import QTableWidget, QTableWidgetItem, QHeaderView, QGroupBox
                
                is_single = (field_type == 'single_channel_editor') or (field_def.get('mode') == 'single')
                
                relay_group = QGroupBox(label_text if label_text else ("自定义功能与物理地址配置" if is_single else "自定义函数与工位地址配置 (序列中可直接调用)"))
                relay_group.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
                relay_layout = QVBoxLayout(relay_group)
                relay_layout.setContentsMargins(8, 12, 8, 8)
                relay_layout.setSpacing(6)
                
                # 获取当前配置列表
                channels_data = current_val if isinstance(current_val, list) else []
                
                if is_single:
                    headers = ["函数名称 (序列调用)", "功能描述", "物理地址", "true值", "false值"]
                else:
                    headers = [
                        "函数名称 (序列调用)", "功能描述", "工位1物理地址", 
                        "工位2物理地址", "工位3物理地址", "工位4物理地址", 
                        "true值", "false值"
                    ]
                
                table = QTableWidget(0, len(headers))
                table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
                table.setHorizontalHeaderLabels(headers)
                table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
                table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
                for c in range(2, len(headers)):
                    table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeToContents)
                
                # 填充表格
                for item in channels_data:
                    if not isinstance(item, dict):
                        continue
                    tbl_row = table.rowCount()
                    table.insertRow(tbl_row)
                    alias = item.get('alias', '')
                    desc = item.get('desc', '')
                    st_addrs = item.get('station_addresses', {})
                    addr1 = st_addrs.get('station_1', item.get('address', ''))
                    addr2 = st_addrs.get('station_2', '')
                    addr3 = st_addrs.get('station_3', '')
                    addr4 = st_addrs.get('station_4', '')
                    on_val = str(item.get('on_value', item.get('true_value', 1)))
                    off_val = str(item.get('off_value', item.get('false_value', 0)))
                    
                    if is_single:
                        table.setItem(tbl_row, 0, QTableWidgetItem(str(alias)))
                        table.setItem(tbl_row, 1, QTableWidgetItem(str(desc)))
                        table.setItem(tbl_row, 2, QTableWidgetItem(str(item.get('address', addr1))))
                        table.setItem(tbl_row, 3, QTableWidgetItem(on_val))
                        table.setItem(tbl_row, 4, QTableWidgetItem(off_val))
                    else:
                        table.setItem(tbl_row, 0, QTableWidgetItem(str(alias)))
                        table.setItem(tbl_row, 1, QTableWidgetItem(str(desc)))
                        table.setItem(tbl_row, 2, QTableWidgetItem(str(addr1)))
                        table.setItem(tbl_row, 3, QTableWidgetItem(str(addr2)))
                        table.setItem(tbl_row, 4, QTableWidgetItem(str(addr3)))
                        table.setItem(tbl_row, 5, QTableWidgetItem(str(addr4)))
                        table.setItem(tbl_row, 6, QTableWidgetItem(on_val))
                        table.setItem(tbl_row, 7, QTableWidgetItem(off_val))
                
                # 表格自适应高度
                def update_relay_table_height():
                    row_count = table.rowCount()
                    header_height = table.horizontalHeader().height()
                    row_height = table.verticalHeader().defaultSectionSize()
                    total_height = header_height + (row_height * max(row_count, 1)) + 8
                    table.setMinimumHeight(min(max(total_height, 100), 300))
                update_relay_table_height()
                
                relay_layout.addWidget(table)
                
                # 操作按钮
                btn_layout = QHBoxLayout()
                add_btn = QPushButton("➕ 添加项")
                del_btn = QPushButton("➖ 删除项")
                
                def add_relay_row():
                    r_idx = table.rowCount()
                    table.insertRow(r_idx)
                    idx = r_idx + 1
                    alias_name = f"K_BOARD" if r_idx == 0 else f"K{idx}"
                    desc_name = f"控制项" if r_idx == 0 else f"功能项 {idx}"
                    base_hex = f"0xA0{idx:02X}"
                    
                    if is_single:
                        table.setItem(r_idx, 0, QTableWidgetItem(alias_name))
                        table.setItem(r_idx, 1, QTableWidgetItem(desc_name))
                        table.setItem(r_idx, 2, QTableWidgetItem(base_hex))
                        table.setItem(r_idx, 3, QTableWidgetItem("1"))
                        table.setItem(r_idx, 4, QTableWidgetItem("0"))
                    else:
                        table.setItem(r_idx, 0, QTableWidgetItem(alias_name))
                        table.setItem(r_idx, 1, QTableWidgetItem(desc_name))
                        table.setItem(r_idx, 2, QTableWidgetItem(base_hex))
                        table.setItem(r_idx, 3, QTableWidgetItem(""))
                        table.setItem(r_idx, 4, QTableWidgetItem(""))
                        table.setItem(r_idx, 5, QTableWidgetItem(""))
                        table.setItem(r_idx, 6, QTableWidgetItem("1"))
                        table.setItem(r_idx, 7, QTableWidgetItem("0"))
                    update_relay_table_height()
                
                def del_relay_row():
                    current_row = table.currentRow()
                    if current_row >= 0:
                        table.removeRow(current_row)
                        update_relay_table_height()
                
                add_btn.clicked.connect(add_relay_row)
                del_btn.clicked.connect(del_relay_row)
                btn_layout.addWidget(add_btn)
                btn_layout.addWidget(del_btn)
                
                if not is_single:
                    auto_fill_btn = QPushButton("⚡ 工位地址快速递增 (+1)")
                    auto_fill_btn.setToolTip("选中某一行，以工位1地址为基准，自动将+1、+2、+3依次填充到工位2、3、4")
                    def auto_fill_addresses():
                        current_row = table.currentRow()
                        if current_row < 0:
                            return
                        base_addr_item = table.item(current_row, 2)
                        if not base_addr_item or not base_addr_item.text().strip():
                            return
                        base_text = base_addr_item.text().strip()
                        try:
                            if base_text.lower().startswith('0x'):
                                val = int(base_text, 16)
                                for col, st_idx in [(3, 1), (4, 2), (5, 3)]:
                                    table.setItem(current_row, col, QTableWidgetItem(f"0x{val + st_idx:04X}"))
                            else:
                                val = int(base_text)
                                for col, st_idx in [(3, 1), (4, 2), (5, 3)]:
                                    table.setItem(current_row, col, QTableWidgetItem(str(val + st_idx)))
                        except Exception:
                            pass
                    auto_fill_btn.clicked.connect(auto_fill_addresses)
                    btn_layout.addWidget(auto_fill_btn)
                
                btn_layout.addStretch()
                relay_layout.addLayout(btn_layout)
                
                self.widgets[key] = {
                    'type': 'single_channel_editor' if is_single else 'relay_channel_editor',
                    'table': table,
                    'is_single': is_single
                }
                
                widget = relay_group
                label = None
            
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
                        label.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Preferred)
                        if isinstance(widget, (QLineEdit, QComboBox, SerialPortComboBox)):
                            widget.setMaximumWidth(280)
                            widget.setMinimumWidth(200)
                        layout.addWidget(label, row, 0, Qt.AlignLeft | Qt.AlignVCenter)
                        layout.addWidget(widget, row, 1, Qt.AlignLeft | Qt.AlignVCenter)
                        layout.setColumnStretch(0, 0)
                        layout.setColumnStretch(1, 0)
                        layout.setColumnStretch(2, 1)
                    else:
                        layout.addWidget(widget, row, 0, 1, 3) # 跨满整行3列
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
                text = widget.currentText().strip()
                cur_idx = widget.currentIndex()
                if cur_idx >= 0 and widget.itemText(cur_idx) == text:
                    # 匹配了下拉项，取 UserData
                    data = widget.itemData(cur_idx)
                    value = data if data else (text.split(" - ")[0] if " - " in text else text)
                else:
                    # 用户手动输入或设置了自定义端口
                    value = text.split(" - ")[0] if " - " in text else text

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
            
            # 处理复杂类型
            elif isinstance(widget, dict):
                widget_type = widget.get('type')
                
                if widget_type == 'mode_switch':
                    # 模式切换：返回模式值和所有子配置
                    button_group = widget.get('button_group')
                    checked_id = button_group.checkedId()
                    
                    # 模式值：0=shared, 1=independent, 2=dedicated
                    mode_map = {0: 'shared', 1: 'independent', 2: 'dedicated'}
                    result = {'mode': mode_map.get(checked_id, 'shared')}
                    
                    # 保留旧字段兼容性
                    result['use_independent_mode'] = (checked_id == 1)
                    
                    # 获取共享模式配置
                    shared_builder = widget.get('shared_builder')
                    if shared_builder:
                        shared_key = widget.get('shared_config_key', 'shared_config')
                        result[shared_key] = shared_builder.get_config()
                    
                    # 获取独立模式配置
                    station_builders = widget.get('station_builders', {})
                    if station_builders:
                        ind_configs = {}
                        for station_id, builder in station_builders.items():
                            ind_configs[station_id] = builder.get_config()
                        result['independent_configs'] = ind_configs
                    
                    # 获取专用模式配置
                    dedicated_builder = widget.get('dedicated_builder')
                    if dedicated_builder:
                        result['dedicated_config'] = dedicated_builder.get_config()
                    
                    value = result
                
                elif widget_type == 'group':
                    # 嵌套配置组
                    builder = widget.get('builder')
                    value = builder.get_config() if builder else {}
                
                elif widget_type == 'station_group':
                    # 按工位配置组 - 直接保存为扁平结构，不再额外嵌套 'stations'
                    builders = widget.get('builders', {})
                    value = {
                        station_id: builder.get_config()
                        for station_id, builder in builders.items()
                    }
                
                elif widget_type == 'visa_with_connect':
                    # VISA + 启动时连接
                    combo = widget.get('combo')
                    auto_connect = widget.get('auto_connect')
                    value = {
                        'visa_address': combo.currentText() if combo else '',
                        'auto_connect_on_startup': auto_connect.isChecked() if auto_connect else False
                    }
                
                elif widget_type == 'channel_config':
                    # 通道配置
                    channels = widget.get('channels', {})
                    value = {}
                    for ch_key, ch_widgets in channels.items():
                        value[ch_key] = {
                            'voltage': ch_widgets['voltage'].value(),
                            'current': ch_widgets['current'].value(),
                            'enable_on_startup': ch_widgets['enable_on_startup'].isChecked()
                        }
                
                elif widget_type == 'supply_channel_mapping':
                    # 供电通道映射 (product/battery/daq -> channel)
                    mapping_widgets = widget.get('mappings', {})
                    value = {}
                    for supply_key, supply_widgets in mapping_widgets.items():
                        ch_spin = supply_widgets.get('channel')
                        if ch_spin:
                            value[supply_key] = {'channel': ch_spin.value()}
                
                elif widget_type == 'multi_psu_config':
                    # 多电源配置
                    psu_widgets = widget.get('psu_widgets', {})
                    startup_widgets = widget.get('startup_widgets', {})
                    mapping_widgets = widget.get('mapping_widgets', {})
                    
                    # 电源设备配置
                    power_supplies = {}
                    for psu_id, psu_w in psu_widgets.items():
                        power_supplies[psu_id] = {
                            'visa_address': psu_w['visa_combo'].currentText(),
                            'auto_connect_on_startup': psu_w['auto_connect'].isChecked()
                        }
                    
                    # 启动设置
                    power_startup_settings = {}
                    for type_key, type_w in startup_widgets.items():
                        power_startup_settings[type_key] = {
                            'psu_id': type_w['psu_id'].currentText(),
                            'channel': type_w['channel'].value(),
                            'voltage': type_w['voltage'].value(),
                            'current': type_w['current'].value(),
                            'enabled': type_w['enabled'].isChecked()
                        }
                    
                    # 工位映射
                    power_control = {}
                    for station_id, station_w in mapping_widgets.items():
                        power_control[station_id] = {
                            'product': {
                                'psu_id': station_w['psu_id'].currentText(),
                                'channel': station_w['channel'].value()
                            }
                        }
                    
                    value = {
                        'power_supplies': power_supplies,
                        'power_startup_settings': power_startup_settings,
                        'power_control': power_control
                    }
                
                elif widget_type == 'modbus_slave_editor':
                    # Modbus 从站设备表格
                    table = widget.get('table')
                    if table:
                        slaves = {}
                        for row in range(table.rowCount()):
                            name_item = table.item(row, 0)
                            addr_item = table.item(row, 1)
                            if name_item and addr_item:
                                name = name_item.text().strip()
                                try:
                                    addr = int(addr_item.text())
                                except ValueError:
                                    addr = 1
                                if name:
                                    slaves[name] = addr
                        value = slaves

                elif widget_type in ('relay_channel_editor', 'single_channel_editor'):
                    table = widget.get('table')
                    is_single = widget.get('is_single', False)
                    if table:
                        channels = []
                        for row in range(table.rowCount()):
                            alias_item = table.item(row, 0)
                            desc_item = table.item(row, 1)
                            alias = alias_item.text().strip() if alias_item else ''
                            if not alias:
                                continue
                            desc = desc_item.text().strip() if desc_item else ''

                            if is_single:
                                addr_item = table.item(row, 2)
                                on_item = table.item(row, 3)
                                off_item = table.item(row, 4)
                                addr = addr_item.text().strip() if addr_item else ''
                                try: on_val = int(on_item.text().strip()) if on_item else 1
                                except ValueError: on_val = 1
                                try: off_val = int(off_item.text().strip()) if off_item else 0
                                except ValueError: off_val = 0

                                channels.append({
                                    'alias': alias,
                                    'desc': desc,
                                    'address': addr,
                                    'station_addresses': {'station_1': addr},
                                    'true_value': on_val,
                                    'false_value': off_val,
                                    'on_value': on_val,
                                    'off_value': off_val
                                })
                            else:
                                addr1_item = table.item(row, 2)
                                addr2_item = table.item(row, 3)
                                addr3_item = table.item(row, 4)
                                addr4_item = table.item(row, 5)
                                on_item = table.item(row, 6)
                                off_item = table.item(row, 7)
                                addr1 = addr1_item.text().strip() if addr1_item else ''
                                addr2 = addr2_item.text().strip() if addr2_item else ''
                                addr3 = addr3_item.text().strip() if addr3_item else ''
                                addr4 = addr4_item.text().strip() if addr4_item else ''
                                try: on_val = int(on_item.text().strip()) if on_item else 1
                                except ValueError: on_val = 1
                                try: off_val = int(off_item.text().strip()) if off_item else 0
                                except ValueError: off_val = 0

                                channels.append({
                                    'alias': alias,
                                    'desc': desc,
                                    'address': addr1,
                                    'station_addresses': {
                                        'station_1': addr1,
                                        'station_2': addr2 or addr1,
                                        'station_3': addr3 or addr1,
                                        'station_4': addr4 or addr1,
                                    },
                                    'true_value': on_val,
                                    'false_value': off_val,
                                    'on_value': on_val,
                                    'off_value': off_val
                                })
                        value = channels
            
            if value is not None:
                config[key] = value
        
        return config
