# JLink 编程器配置驱动

class JLinkDriver:
    """
    JLink 编程器配置驱动。
    用于在配置编辑器中生成 JLink 工位配置界面（2x2 布局）。
    """
    
    # ========== 驱动元数据 ==========
    DRIVER_META = {
        "name": "JLinkDriver",
        "display_name": "JLink 编程器",
        "category": "programmer",
        "interface": "usb",
    }
    
    # ========== 配置 Tab 定义 ==========
    CONFIG_TAB = {
        "tab_name": "JLink 配置",
        "config_key": "jlink_config",
        "mode": "shared",
    }
    
    # ========== 配置表单定义（全局路径 + 工位 SN）==========
    CONFIG_SCHEMA = {
        "jlink_path": {
            "type": "file",
            "label": "JLink.exe 路径",
            "default": ""
        },
        "stations": {
            "type": "station_group",
            "label": "工位 JLink SN 配置",
            "station_count": 4,
            "schema": {
                "jlink_sn": {
                    "type": "jlink_sn",
                    "label": "JLink SN",
                    "default": ""
                }
            }
        }
    }

    def __init__(self, **kwargs):
        pass
