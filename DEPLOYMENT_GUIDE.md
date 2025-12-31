# TestApp V1.1.0 部署指南（--onedir 模式）

## 改进说明

已将打包模式从 `--onefile`（单文件）改为 `--onedir`（文件夹），**启动速度将提升 5-10 倍**。

### 优势对比

| 模式 | 启动时间 | 体积 | 部署复杂度 |
|------|---------|------|-----------|
| --onefile | ~42秒 | 240MB (单文件) | 简单 |
| --onedir | ~5-8秒 | ~250MB (文件夹) | 稍复杂 |

## 打包步骤

### 1. 打包主程序

在项目根目录运行：

```bash
pyinstaller main.spec
```

这将在 `dist\` 目录下生成 `TestApp_V1.1.0\` 文件夹，包含：
- `TestApp_V1.1.0.exe` - 主程序可执行文件
- 各种 `.dll`、`.pyd` 文件 - 依赖库
- `_internal\` 文件夹 - Python 运行时和其他资源

### 2. 准备部署包

创建最终部署结构：

```
TestApp_Deployment/
├── drivers/
│   ├── fluke_8808a.cpython-312.pyc
│   ├── modbus_communication.cpython-312.pyc
│   └── rigol_dp832.cpython-312.pyc
├── test_modules/
│   ├── communication.cpython-312.pyc
│   ├── control_flow.cpython-312.pyc
│   └── ... (其他测试模块)
└── TestApp_V1.1.0/              ← 整个文件夹复制过来
    ├── TestApp_V1.1.0.exe       ← 用户双击这个启动
    ├── _internal/
    │   └── ... (所有依赖文件)
    ├── config.json
    ├── test_history.db
    ├── sequences/
    ├── reports/
    └── ... (其他运行时文件)
```

### 3. 复制运行时文件

将以下文件/文件夹复制到 `TestApp_V1.1.0\` 文件夹内：
- `config.json`
- `sequences/` 目录
- `docs/` 目录（如果需要）
- 其他配置文件

## 使用说明

### 直接启动

用户双击 `TestApp_V1.1.0\TestApp_V1.1.0.exe` 即可启动（约5-8秒）。

### 创建桌面快捷方式（推荐）

为方便用户使用，建议创建桌面快捷方式：

1. 右键 `TestApp_V1.1.0.exe`
2. 选择"创建快捷方式"
3. 将快捷方式移到桌面或其他位置
4. 重命名为 `测试平台 V1.1.0`

## 优化建议

### 1. 首次启动优化

首次启动时，Windows Defender 可能会扫描文件，导致启动稍慢。建议：
- 将 `TestApp_V1.1.0\` 文件夹添加到 Windows Defender 排除列表

### 2. 网络驱动器问题

如果从网络驱动器运行，启动会更慢。建议：
- 复制到本地硬盘（如 `C:\Program Files\TestApp\`）

### 3. SSD vs HDD

- SSD：启动时间 ~5秒
- HDD：启动时间 ~8-10秒

## 与 --onefile 模式的区别

### --onefile（旧方式）
- ✅ 单个 exe 文件，便于分发
- ❌ 启动极慢（~42秒）
- ❌ 每次运行都解压临时文件

### --onedir（新方式）
- ✅ 启动快速（~5-8秒）
- ✅ 不需要解压，直接运行
- ❌ 文件较多，需要整个文件夹

### 4. 消息弹框模块 (message_popup.py)

新增了类似 TestStand 的消息弹框模块，支持在测试序列中与用户交互。

**主要功能：**
- `show_message`: 显示消息框（支持多种按钮和图标）
- `show_input`: 显示输入框
- `confirm`: 简单的确认框（是/否）
- `alert`: 简单的警告框
- `error`: 简单的错误框

**使用注意：**
- 该模块通过线程安全的方式调用主线程 UI，不会导致程序崩溃。
- 弹框会自动显示在对应工位的界面上，支持多工位并发测试。
- 必须确保 `TestEngine` 实例被正确注入（系统会自动处理）。

## 故障排除

### Q: 弹框位置不对或被遮挡
A: 弹框现在会自动定位到对应工位的中心。如果仍然出现位置偏移，请检查是否使用了多显示器且缩放比例不一致。

### Q: 输入框总是提示"用户取消输入"
A: 请确保在输入完成后点击"OK"按钮或按回车键。直接关闭窗口会被视为取消。
A: 确保 `drivers\` 和 `test_modules\` 文件夹与 `TestApp_V1.1.0\` 在同一父目录下。

### Q: 启动还是很慢
A: 
1. 检查是否在网络驱动器上运行
2. 检查 Windows Defender 是否在扫描
3. 确认使用的是 SSD 而非 HDD

### Q: 双击没反应
A: 
1. 检查是否有杀毒软件拦截
2. 尝试右键"以管理员身份运行"
3. 查看 Windows 事件查看器的错误日志

## 回退到 --onefile（如果需要）

如果因为某些原因需要回退到单文件模式，修改 `main.spec`：

```python
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,  # 恢复
    a.datas,     # 恢复
    [],
    exclude_binaries=False,  # 改为 False
    name='TestApp_V1.1.0',
    # ... 其他参数
)

# 删除或注释掉 COLLECT 部分
# coll = COLLECT(...)
```

然后重新运行 `pyinstaller main.spec`。
