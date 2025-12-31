# 驱动开发指南 (Driver Development Guide)

本指南旨在帮助开发者为 PythonTest 平台开发新的硬件驱动程序，并将其集成到配置编辑器中。

## 1. 驱动位置
所有驱动程序应放置在 `drivers/` 目录下。

## 2. 驱动类结构
一个标准的驱动类应包含以下部分：

### 2.1 初始化方法 `__init__`
*   接收配置参数（通常是 `visa_address` 或 `port` 等）。
*   **不要**在 `__init__` 中进行硬件连接。初始化应只保存配置。

### 2.2 连接方法 `connect`
*   执行实际的硬件连接逻辑（如 `pyvisa.open_resource` 或 `serial.Serial`）。
*   如果连接失败，应抛出异常。

### 2.3 断开方法 `close`
*   安全地关闭连接并释放资源。

---

## 3. 自动生成配置界面（核心功能）

### 3.1 CONFIG_TAB - 定义配置 Tab（新功能！）

通过 `CONFIG_TAB` 定义，可以让驱动**自动在配置编辑器中生成一个配置 Tab**，无需修改任何代码！

```python
class MyDriver:
    CONFIG_TAB = {
        "tab_name": "我的设备配置",      # Tab 标签名称
        "config_key": "my_device_config", # 在 config.json 中的 key
        "mode": "shared",                 # "shared" (共享) 或 "per_station" (每工位独立)
    }
```

**mode 说明：**
*   `shared`: 所有工位共用一个配置
*   `per_station`: 每个工位独立配置（会自动显示 4 个工位配置组）

### 3.2 CONFIG_SCHEMA - 定义表单字段

```python
class MyDriver:
    CONFIG_SCHEMA = {
        "field_name": {
            "type": "string",       # 字段类型
            "label": "显示名称",      # 在界面上显示的标签
            "default": "默认值",      # 默认值
            "tooltip": "提示信息",    # 鼠标悬停时的提示
        },
        # ... 更多字段
    }
```

### 3.3 支持的字段类型

| 类型 | 控件 | 用途 | 额外参数 |
|------|------|------|----------|
| `string` | 文本框 | 普通文本、IP地址等 | - |
| `int` | 文本框 | 整数 | - |
| `float` | 文本框 | 小数 | - |
| `bool` | 复选框 | 开关选项 | - |
| `select` | 下拉框 | 固定选项 | `options: [...]` |
| `serial_port` | 串口下拉框 | 自动列出 COM 口 | - |
| `visa` | VISA 选择器 | 自动扫描设备 | - |
| `file` | 文件选择框 | 选择文件 | - |
| `directory` | 文件夹选择框 | 选择目录 | - |
| `channel` | 通道选择器 | 电源通道等 | `min`, `max` |
| `baudrate` | 波特率选择 | 常用波特率 | `options` |
| `voltage` | 电压输入 | 带单位 | `min`, `max`, `decimals` |
| `current` | 电流输入 | 带单位 | `min`, `max`, `decimals` |

---

## 4. 完整示例

参见 `drivers/ethernet_driver.py`：

```python
class EthernetDriver:
    DRIVER_META = {
        "name": "EthernetDriver",
        "display_name": "以太网通信",
        "category": "communication",
    }
    
    # 定义 Tab - 自动在配置编辑器中显示
    CONFIG_TAB = {
        "tab_name": "以太网配置",
        "config_key": "ethernet_config",
        "mode": "per_station",
    }
    
    # 定义表单
    CONFIG_SCHEMA = {
        "ip_address": {
            "type": "string",
            "label": "IP 地址",
            "default": "192.168.1.100"
        },
        "port": {
            "type": "int",
            "label": "端口号",
            "default": 5000
        },
        "auto_connect": {
            "type": "bool",
            "label": "启动时连接",
            "default": False
        }
    }
    
    def __init__(self, ip_address, port=5000, ...):
        self.ip_address = ip_address
        # ...
```

---

## 5. 集成到系统

1.  将编写好的 `.py` 文件放入 `drivers/` 目录
2.  重启软件或打开配置编辑器
3.  **自动**出现对应的配置 Tab！
4.  配置保存到 `config.json`

**无需修改任何代码，无需重新打包 exe！**
