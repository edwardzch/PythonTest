# 文件路径: drivers/ethernet_driver.py
# 示例驱动 - 演示如何定义动态配置 Tab
# 将此文件放入 drivers/ 目录，config_editor 会自动生成配置界面

"""
以太网通信驱动示例

这个文件演示了如何使用 CONFIG_TAB 和 CONFIG_SCHEMA 来定义
一个自动在配置编辑器中显示的配置界面。

使用方法：
1. 将此文件放入 drivers/ 目录
2. 打开配置编辑器
3. 你会看到一个新的 "以太网配置" Tab 自动出现
4. 修改配置后保存，配置会写入 config.json
"""


class EthernetDriver:
    """以太网通信驱动"""
    
    # ========== 驱动元数据 ==========
    DRIVER_META = {
        "name": "EthernetDriver",
        "display_name": "以太网通信",
        "category": "communication",
        "interface": "ethernet",
    }
    
    # ========== 配置 Tab 定义（关键！）==========
    CONFIG_TAB = {
        "tab_name": "以太网配置",           # Tab 标签名称
        "config_key": "ethernet_config",    # 在 config.json 中的 key
        "mode": "per_station",              # "shared" 或 "per_station"
        # shared: 所有工位共用一个配置
        # per_station: 每个工位独立配置
    }
    
    # ========== 配置表单定义 ==========
    CONFIG_SCHEMA = {
        "ip_address": {
            "type": "string",
            "label": "IP 地址",
            "default": "192.168.1.100",
            "tooltip": "设备的 IP 地址"
        },
        "port": {
            "type": "int",
            "label": "端口号",
            "default": 5000,
            "tooltip": "通信端口号"
        },
        "protocol": {
            "type": "select",
            "label": "通信协议",
            "options": ["TCP", "UDP"],
            "default": "TCP"
        },
        "timeout": {
            "type": "float",
            "label": "超时时间(秒)",
            "default": 5.0
        },
        "auto_connect": {
            "type": "bool",
            "label": "启动时自动连接",
            "default": False
        }
    }

    def __init__(self, ip_address, port=5000, protocol="TCP", timeout=5.0, auto_connect=False):
        """初始化以太网驱动"""
        self.ip_address = ip_address
        self.port = port
        self.protocol = protocol
        self.timeout = timeout
        self.auto_connect = auto_connect
        self.socket = None
    
    def connect(self):
        """连接到设备"""
        import socket
        try:
            if self.protocol == "TCP":
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            else:
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            
            self.socket.settimeout(self.timeout)
            self.socket.connect((self.ip_address, self.port))
            print(f"已连接到 {self.ip_address}:{self.port} ({self.protocol})")
        except Exception as e:
            raise ConnectionError(f"连接失败: {e}")
    
    def close(self):
        """关闭连接"""
        if self.socket:
            self.socket.close()
            self.socket = None
