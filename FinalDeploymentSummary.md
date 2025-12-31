# 最终部署步骤总结

为了将您的应用程序部署到车间，您需要按照以下顺序执行操作，并最终将所有组件组合到一个部署文件夹中：

1.  **生成核心应用程序 (`TestApp` 文件夹)**：
    *   打开命令行（例如 `cmd` 或 PowerShell），导航到您的项目根目录 `C:\Users\edwar\Desktop\PythonTest`。
    *   运行 PyInstaller 命令：
        ```bash
        pyinstaller main.spec
        ```
    *   这将在项目根目录下生成一个 `dist` 文件夹，其中包含 `TestApp` 文件夹（即您的核心应用程序）。

2.  **编译插件 (`test_modules` 和 `drivers` 目录)**：
    *   在您的项目根目录 `C:\Users\edwar\Desktop\PythonTest` 下，找到并**双击运行 `compile_plugins.bat` 脚本**。
    *   该脚本会自动将 `test_modules/` 和 `drivers/` 目录下的所有 `.py` 文件编译成 `.pyc` 文件，并存放在各自目录下的 `__pycache__` 子目录中。

3.  **组装最终部署文件夹**：
    *   在车间电脑上创建一个新的部署目录，例如 `D:\TestApp_Deployment`。
    *   将您在步骤1中生成的 `dist/TestApp` 文件夹完整地复制到 `D:\TestApp_Deployment` 目录下。
    *   将项目根目录下的 `config.json` 文件复制到 `D:\TestApp_Deployment` 目录下。
    *   将您在步骤2中编译好的 `test_modules/` 和 `drivers/` 文件夹（包含 `__pycache__` 子目录和 `.pyc` 文件）完整地复制到 `D:\TestApp_Deployment` 目录下。
    *   根据需要，复制或创建 `sequences/`、`reports/`、`CycleTestReports/`、`SnifferReports/` 文件夹，以及 `test_history.db` 文件到 `D:\TestApp_Deployment` 目录下。
    *   将更新后的 `DeploymentGuide.txt` 文件也复制到 `D:\TestApp_Deployment` 目录下。

完成以上步骤后，您的部署文件夹 `D:\TestApp_Deployment` 就准备好了，可以按照 `DeploymentGuide.txt` 中的说明进行配置和使用了。
