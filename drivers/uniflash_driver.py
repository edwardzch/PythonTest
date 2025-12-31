
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
        "mode": "shared",  # 共享模式（统一配置）
    }
    
    # ========== 配置表单定义 ==========
    CONFIG_SCHEMA = {
        "station_1_path": {
            "type": "directory",
            "label": "工位 1 UniFlash 目录",
            "default": "",
            "tooltip": "选择工位 1 对应的 UniFlash 根目录 (包含 .bat 文件的目录)"
        },
        "station_2_path": {
            "type": "directory",
            "label": "工位 2 UniFlash 目录",
            "default": "",
            "tooltip": "选择工位 2 对应的 UniFlash 根目录"
        },
        "station_3_path": {
            "type": "directory",
            "label": "工位 3 UniFlash 目录",
            "default": "",
            "tooltip": "选择工位 3 对应的 UniFlash 根目录"
        },
        "station_4_path": {
            "type": "directory",
            "label": "工位 4 UniFlash 目录",
            "default": "",
            "tooltip": "选择工位 4 对应的 UniFlash 根目录"
        }
    }

    def __init__(self, **kwargs):
        pass
