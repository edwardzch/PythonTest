
class UniFlashDriver:
    """
    UniFlash 编程器配置驱动。
    用于在配置编辑器中生成 4 个工位的路径选择界面。
    """
    
    # ========== 驱动元数据 ==========
    DRIVER_META = {
        "name": "UniFlashDriver",
        "display_name": "UniFlash 编程器",
        "category": "programmer",
        "interface": "executable",
    }
    
    # ========== 配置 Tab 定义 ==========
    CONFIG_TAB = {
        "tab_name": "UniFlash 配置",
        "config_key": "uniflash_config",
        "mode": "shared",
    }
    
    # ========== 配置表单定义（使用 station_group 实现 2x2 布局）==========
    CONFIG_SCHEMA = {
        "stations": {
            "type": "station_group",
            "label": "工位 UniFlash 目录配置",
            "station_count": 4,
            "schema": {
                "uniflash_path": {
                    "type": "directory",
                    "label": "UniFlash 目录",
                    "default": ""
                }
            }
        }
    }

    def __init__(self, **kwargs):
        pass
