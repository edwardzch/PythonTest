# Launcher 使用说明

## 为什么使用 Launcher？

由于主程序 `TestApp_V1.1.0.exe` 体积较大（约240MB），启动时需要10多秒。使用轻量级的 `Launcher.exe` 可以提供更好的用户体验：
- `Launcher.exe` 体积小（约10-20MB），秒启动
- 立即显示启动画面，给用户即时反馈
- 后台启动主程序，避免用户等待

## 打包 Launcher

使用 PyInstaller 打包 launcher.py：

```bash
pyinstaller --name="Launcher" ^
            --onefile ^
            --windowed ^
            --icon=app_icon.ico ^
            --add-data "app_icon.ico;." ^
            launcher.py
```

### 打包参数说明：
- `--name="Launcher"`: 输出文件名为 Launcher.exe
- `--onefile`: 打包为单个 exe 文件
- `--windowed`: 无控制台窗口（GUI 应用）
- `--icon=app_icon.ico`: 设置图标
- `--add-data`: 打包图标文件

## 部署结构

将打包后的文件按以下结构部署：

```
TestApp_Deployment/
├── Launcher.exe              ← 用户双击这个启动
├── drivers/
│   ├── fluke_8808a.cpython-312.pyc
│   ├── modbus_communication.cpython-312.pyc
│   └── rigol_dp832.cpython-312.pyc
├── test_modules/
│   ├── communication.cpython-312.pyc
│   ├── ...
└── TestApp/
    ├── TestApp_V1.1.0.exe    ← 主程序（由 Launcher 启动）
    ├── config.json
    ├── test_history.db
    └── ...其他运行时文件
```

## 使用方法

1. 用户双击 `Launcher.exe`
2. 立即显示启动画面
3. Launcher 在后台启动 `TestApp_V1.1.0.exe`
4. 主程序启动完成后，Launcher 自动关闭

## 注意事项

- Launcher 会自动查找 `TestApp_V1.1.0.exe`，如果找不到，会尝试查找任何 `TestApp*.exe`
- 确保 Launcher.exe 和 TestApp/ 目录在同一级
- 测试时可以使用 `console=True` 查看调试信息

## 开发环境测试

在开发环境中，可以直接运行 `launcher.py`：

```bash
python launcher.py
```

它会自动启动 `main.py`。
