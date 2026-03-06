# 文件路径: help_dialog.py (最大化问题修复版)

import sys
import inspect
import html

from PySide6.QtWidgets import (
    QDialog, QSplitter, QTreeWidget, QTreeWidgetItem, QTextEdit, QVBoxLayout, QApplication
)
from PySide6.QtGui import QIcon
from PySide6.QtCore import Qt, QTimer

from constants import APP_VERSION


def resource_path(relative_path):
    import os
    base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class HelpDialog(QDialog):
    def __init__(self, parent, test_modules):
        # 修复父对象和窗口标志，使其成为独立窗口并避免内存问题
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)

        self.setWindowTitle("帮助文档")
        self.setWindowIcon(QIcon(resource_path('app_icon.ico')))
        self.resize(1024, 768)
        self.setMinimumSize(800, 600)

        self._is_first_show = True  # 添加标志位
        self.test_modules = test_modules
        self._init_ui()
        self._populate_content_map()
        self._populate_tree()

        self.tree.currentItemChanged.connect(self.on_topic_select)
        QTimer.singleShot(0, self._initial_select)

    def showEvent(self, event):
        super().showEvent(event)
        # 【【【优化：使用QTimer解决首次最大化问题】】】
        if self._is_first_show:
            self._is_first_show = False
            QTimer.singleShot(0, self.showMaximized)

    # --- 后续所有函数保持不变，无需修改 ---

    def _initial_select(self):
        if self.tree.topLevelItemCount() > 0:
            first_item = self.tree.topLevelItem(0)
            self.tree.setCurrentItem(first_item)
            self.tree.expandItem(first_item)
            for i in range(self.tree.topLevelItemCount()):
                self.tree.expandItem(self.tree.topLevelItem(i))

    def _init_ui(self):
        main_layout = QVBoxLayout(self)
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        splitter.addWidget(self.tree)
        self.text_area = QTextEdit()
        self.text_area.setReadOnly(True)
        splitter.addWidget(self.text_area)
        splitter.setSizes([300, 724])

    def _populate_tree(self):
        self.tree.clear()
        intro_item = QTreeWidgetItem(self.tree, ["欢迎"])
        intro_item.setData(0, Qt.UserRole, "intro")

        # --- 全面重构功能指南 ---
        guide_node = QTreeWidgetItem(self.tree, ["功能指南"])
        guide_node.setData(0, Qt.UserRole, "guide_overview")
        
        main_ui_item = QTreeWidgetItem(guide_node, ["主界面与工位"])
        main_ui_item.setData(0, Qt.UserRole, "main_ui_guide")

        file_ops_item = QTreeWidgetItem(guide_node, ["文件操作"])
        file_ops_item.setData(0, Qt.UserRole, "file_ops_guide")

        editor_item = QTreeWidgetItem(guide_node, ["序列编辑器"])
        editor_item.setData(0, Qt.UserRole, "sequence_editor_guide")

        config_item = QTreeWidgetItem(guide_node, ["系统配置"])
        config_item.setData(0, Qt.UserRole, "config_editor_guide")

        # 创建 "工具" 子目录
        tools_node = QTreeWidgetItem(guide_node, ["工具"])
        
        cycle_test_item = QTreeWidgetItem(tools_node, ["循环压力测试"])
        cycle_test_item.setData(0, Qt.UserRole, "cycle_test_guide")

        sniffer_item = QTreeWidgetItem(tools_node, ["通信抓包工具"])
        sniffer_item.setData(0, Qt.UserRole, "sniffer_tool_guide")

        analysis_item = QTreeWidgetItem(tools_node, ["历史数据分析"])
        analysis_item.setData(0, Qt.UserRole, "analysis_guide")
        
        hardware_item = QTreeWidgetItem(tools_node, ["硬件工具"])
        hardware_item.setData(0, Qt.UserRole, "hardware_tools_guide")
        
        # 新增功能（v1.2.0）
        thimble_item = QTreeWidgetItem(tools_node, ["顶针管理"])
        thimble_item.setData(0, Qt.UserRole, "thimble_guide")
        
        cable_item = QTreeWidgetItem(tools_node, ["线缆管理"])
        cable_item.setData(0, Qt.UserRole, "cable_guide")
        
        order_est_item = QTreeWidgetItem(tools_node, ["测试时间预测"])
        order_est_item.setData(0, Qt.UserRole, "order_estimation_guide")

        permission_item = QTreeWidgetItem(guide_node, ["权限管理"])
        permission_item.setData(0, Qt.UserRole, "permission_guide")
        
        # 驱动开发指南（v2.1.0）
        driver_dev_item = QTreeWidgetItem(guide_node, ["驱动开发指南"])
        driver_dev_item.setData(0, Qt.UserRole, "driver_dev_guide")
        # --- 重构结束 ---

        mod_node = QTreeWidgetItem(self.tree, ["模块函数参考"])
        mod_node.setData(0, Qt.UserRole, "mod_ref_overview")
        for module_name in sorted(self.test_modules.keys()):
            module = self.test_modules[module_name]
            module_item = QTreeWidgetItem(mod_node, [module_name.replace("_", " ").title()])
            module_item.setData(0, Qt.UserRole, f"mod_{module_name}")
            functions = []
            for func_name, func_obj in inspect.getmembers(module, inspect.isfunction):
                if not func_name.startswith('_'): functions.append((func_name, func_obj))
            for func_name, func_obj in sorted(functions):
                func_item = QTreeWidgetItem(module_item, [func_name])
                func_item.setData(0, Qt.UserRole, f"func_{module_name}_{func_name}")

    def _populate_content_map(self):
        self.content_map = {
            "intro": self._get_intro_content,
            "main_ui_guide": self._get_main_ui_content,
            "file_ops_guide": self._get_file_ops_content,
            "sequence_editor_guide": self._get_sequence_editor_content,
            "config_editor_guide": self._get_config_editor_content,
            "cycle_test_guide": self._get_cycle_test_content,
            "sniffer_tool_guide": self._get_sniffer_tool_content,
            "analysis_guide": self._get_analysis_content,
            "hardware_tools_guide": self._get_hardware_tools_content,
            "permission_guide": self._get_permission_guide_content,
            "order_estimation_guide": self._get_order_estimation_content,
            "thimble_guide": self._get_thimble_guide_content,
            "cable_guide": self._get_cable_guide_content,
            "guide_overview": self._get_guide_overview_content,
            "mod_ref_overview": self._get_mod_ref_overview_content,
            "driver_dev_guide": self._get_driver_dev_guide_content,
        }
        for module_name, module in self.test_modules.items():
            self.content_map[f"mod_{module_name}"] = lambda m=module: self._get_module_content(m)
            for func_name, func_obj in inspect.getmembers(module, inspect.isfunction):
                if not func_name.startswith('_'):
                    self.content_map[f"func_{module_name}_{func_name}"] = \
                        lambda fn=func_name, fo=func_obj, mn=module_name: self._get_function_content(mn, fn, fo)

    def on_topic_select(self, current, previous):
        if not current: return
        item_id = current.data(0, Qt.UserRole)
        content_func = self.content_map.get(item_id)
        if content_func:
            self.text_area.setHtml(content_func())
            self.text_area.verticalScrollBar().setValue(0)

    def _get_intro_content(self):
        return f"""
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h1>欢迎使用自动化测试平台</h1>
            <h2>版本 (Version): {APP_VERSION}</h2>
            <hr>
            <h3>中文说明</h3>
            <p>本帮助系统旨在为您提供关于平台所有功能的详细指导。请使用左侧的目录树来导航不同的帮助主题。</p>
            <ul>
                <li><b>功能指南</b>: 包含主界面、文件操作、序列编辑器、系统配置、各种工具等的详细说明。</li>
                <li><b>模块函数参考</b>: 列出所有可用的测试模块及其函数的详细参数说明。</li>
            </ul>
            <h3>English Description</h3>
            <p>This help system provides detailed guidance on all platform features. Use the directory tree on the left to navigate through different topics.</p>
            
            <hr>
            <h3>版本更新日志</h3>
            <p>详细的版本更新日志请查看主菜单 <b>"关于" -> "版本号"</b>。</p>
            </body>
        """

    def _get_sequence_editor_content(self):
        return """
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h1>序列编辑器指南</h1>
            <p>序列编辑器是创建和修改测试序列的核心工具。</p>
            
            <h2>界面概览</h2>
            <ul>
                <li><b>主表格</b>: 显示测试序列的每一步。您可以拖动行来进行排序，使用右键菜单进行剪切、复制、粘贴、删除等操作。</li>
                <li><b>编辑区</b>: 位于主表格下方，用于详细编辑当前选中步骤的各项参数。</li>
                <li><b>工具栏</b>: 提供添加/删除步骤、上/下移、撤销/恢复以及保存等快捷操作。</li>
            </ul>

            <h2>核心字段说明</h2>
            <p>每个测试步骤都包含以下关键字段：</p>
            <ul>
                <li><b>测试名称</b>: 对该步骤的可读描述。以 `*` 或 `#` 开头的步骤被视为注释或区块标题。</li>
                <li><b>模块 / 函数</b>: 定义此步骤要执行的具体操作。</li>
                <li><b>参数</b>: 调用上述函数时需要传入的参数，为JSON格式。我们实现的变量替换功能 <b>{变量名}</b> 在此可用。</li>
                <li><b>变量</b>: 用于接收当前步骤的执行结果。引擎会自动将结果存入此处指定的变量名中。</li>
                <li><b>比较</b>: 定义如何判断当前步骤的结果是否通过。详见下方"比较模式详解"。</li>
                <li><b>最小值 / 最大值</b>: 与"比较"字段配合使用，定义判断的边界。支持十六进制 (以`0x`开头)。</li>
                <li><b>步骤处理 (StepAction)</b>: 定义当步骤失败或成功时的行为，例如 `stop` (停止), `continue` (继续), `pass_goto_step` (成功时跳转), `fail_goto_step` (失败时跳转)。</li>
                <li><b>跳转步骤 (GotoStep)</b>: 与 `StepAction` 配合，指定要跳转到的目标步骤编号。</li>
                <li><b>跳过 (Skip)</b>: 设置为 `Yes` 可以让测试引擎在执行时忽略此步骤。</li>
                <li><b>CPK</b>: 设置为 `True` 可以将该步骤的测量结果记录到数据库用于CPK统计分析（详见下文）。</li>
            </ul>
            
            <h2>比较模式详解</h2>
            <p>比较模式用于判断测试步骤的返回值是否符合预期。系统支持以下比较模式：</p>
            
            <h3>数值范围比较</h3>
            <table border='1' cellpadding='8' style='border-collapse: collapse; width: 100%;'>
                <tr style='background-color: #3a3a3a;'>
                    <th>比较模式</th><th>含义</th><th>判断逻辑</th><th>需要的字段</th>
                </tr>
                <tr>
                    <td><code>InRange</code></td>
                    <td>在范围内</td>
                    <td>最小值 ≤ 结果 ≤ 最大值 → PASS</td>
                    <td>最小值 + 最大值</td>
                </tr>
                <tr>
                    <td><code>NotInRange</code></td>
                    <td>不在范围内</td>
                    <td>结果 &lt; 最小值 或 结果 &gt; 最大值 → PASS</td>
                    <td>最小值 + 最大值</td>
                </tr>
            </table>
            
            <h3>数值比较运算符</h3>
            <table border='1' cellpadding='8' style='border-collapse: collapse; width: 100%;'>
                <tr style='background-color: #3a3a3a;'>
                    <th>比较模式</th><th>含义</th><th>判断逻辑</th><th>需要的字段</th>
                </tr>
                <tr><td><code>==</code></td><td>等于</td><td>结果 == 最小值 → PASS</td><td>最小值</td></tr>
                <tr><td><code>!=</code></td><td>不等于</td><td>结果 != 最小值 → PASS</td><td>最小值</td></tr>
                <tr><td><code>></code></td><td>大于</td><td>结果 > 最小值 → PASS</td><td>最小值</td></tr>
                <tr><td><code>>=</code></td><td>大于等于</td><td>结果 >= 最小值 → PASS</td><td>最小值</td></tr>
                <tr><td><code>&lt;</code></td><td>小于</td><td>结果 &lt; 最大值 → PASS</td><td>最大值</td></tr>
                <tr><td><code>&lt;=</code></td><td>小于等于</td><td>结果 &lt;= 最大值 → PASS</td><td>最大值</td></tr>
            </table>
            
            <h3>字符串比较</h3>
            <table border='1' cellpadding='8' style='border-collapse: collapse; width: 100%;'>
                <tr style='background-color: #3a3a3a;'>
                    <th>比较模式</th><th>含义</th><th>判断逻辑</th><th>需要的字段</th>
                </tr>
                <tr>
                    <td><code>Contains</code></td>
                    <td>包含子串</td>
                    <td>结果字符串包含"最小值"字段指定的子串 → PASS</td>
                    <td>最小值（子串）</td>
                </tr>
                <tr>
                    <td><code>NotContains</code></td>
                    <td>不包含子串</td>
                    <td>结果字符串不包含"最小值"字段指定的子串 → PASS</td>
                    <td>最小值（子串）</td>
                </tr>
            </table>
            
            <h3 style='color: #00BFFF;'>💡 实用技巧：编码器零位判断</h3>
            <p>对于绝对式编码器（如17位编码器，范围0~131072），判断是否在零位附近时，由于零位可能"环绕"（接近最大值或接近0），可使用 <code>NotInRange</code> 模式：</p>
            <div style='background-color: #2E2E2E; padding: 15px; border-radius: 5px;'>
                <p><b>场景</b>: 判断17位编码器是否在零位±72范围内</p>
                <p><b>分析</b>: 零位附近的有效范围是 0~72 或 131000~131072</p>
                <p><b>设置方法</b>:</p>
                <ul>
                    <li><b>比较模式</b>: <code>NotInRange</code></li>
                    <li><b>最小值</b>: <code>73</code></li>
                    <li><b>最大值</b>: <code>130999</code></li>
                </ul>
                <p><b>判断逻辑</b>: 结果 &lt; 73 或 结果 &gt; 130999 → PASS（即值在0~72或131000~131072之间）</p>
            </div>
            
            <h2>CPK统计功能</h2>
            <p>CPK（过程能力指数）用于评估生产过程的稳定性和一致性。系统支持自动采集测试数据用于CPK分析。</p>
            <h3>如何启用</h3>
            <ul>
                <li>在编辑区将 <b>CPK</b> 字段设置为 <code>True</code>。</li>
            </ul>
            <h3>前提条件</h3>
            <p>该步骤必须满足以下条件才能正确记录CPK数据：</p>
            <ul>
                <li>有效的<b>数值测量结果</b>（非布尔值或纯字符串）</li>
                <li>有效的<b>上限值</b>（UpperLimit）和<b>下限值</b>（LowerLimit）</li>
            </ul>
            <h3>数据存储</h3>
            <p>测试完成后，符合条件的步骤数据会自动记录到数据库的 <code>test_step_results</code> 表中，包含步骤名称、测量值、上下限等信息。</p>
            <h3>数据分析</h3>
            <p>可通过主菜单 <b>"工具" -> "历史数据分析"</b> 查看CPK分析报告，包括CPK值、直方图、趋势图等。</p>
            
            <h2>高级流程控制</h2>
            <p>我们已经实现了强大的 `IF-ELSE-ENDIF` 块状流程控制。您可以使用 `control_flow` 模块下的 `if_variable`, `else_block`, `end_if` 函数来构建复杂的逻辑分支。</p>
            </body>
        """

    def _get_config_editor_content(self):
        return """
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h1>系统配置指南</h1>
            <p>系统配置 (`config.json`) 定义了测试平台运行所需的所有硬件和全局设置。</p>
            <p>您可以通过主菜单的“编辑” -> “编辑系统配置...”来打开它。</p>
            
            <h2>主要配置项</h2>
            <ul>
                <li><b>report_base_path</b>: 定义测试报告的根目录。</li>
                <li><b>devices</b>: 定义所有可用的硬件设备，例如电源、串口、J-Link等。每个设备都有其类型、地址和别名。</li>
                <li><b>stations</b>: 定义所有的测试工位。每个工位可以绑定 `devices` 中定义的不同硬件设备，实现差异化配置。</li>
            </ul>
            <p><b>重要提示</b>: 修改系统配置后，通常需要重启软件才能使所有更改完全生效。</p>
            </body>
        """

    def _get_main_ui_content(self):
        return """
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h1>主界面与工位指南</h1>
            <p>主界面是测试执行的控制中心，它以工位为单位显示测试状态。</p>
            
            <h2>工位面板</h2>
            <p>每个工位面板都包含以下元素：</p>
            <ul>
                <li><b>状态显示</b>: 显示当前工位的状态，如“空闲”、“测试中”、“通过”、“失败”等。</li>
                <li><b>控制按钮</b>: 提供“开始测试”、“开始调试”、“暂停”、“中止”等操作。</li>
                <li><b>产品SN输入框</b>: 在此输入产品SN后按回车，或点击“开始测试”按钮，即可启动测试。</li>
                <li><b>测试步骤视图</b>: 实时显示当前测试序列的执行进度和每一步的结果。</li>
                <li><b>日志区域</b>: 可通过“日志”复选框打开，显示详细的执行日志，便于调试。</li>
            </ul>

            <h2>工位数量设置</h2>
            <p>您可以根据实际需要，动态调整主界面上显示的工位数量。</p>
            <ul>
                <li><b>如何设置</b>: 通过主菜单的“编辑” -> “工位数量”，然后选择您想要的数量 (1-4)。</li>
                <li><b>注意</b>: 更改工位数量会重置主界面布局。此操作不能在测试正在进行时执行。</li>
            </ul>
            </body>
        """

    def _get_file_ops_content(self):
        return """
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h1>文件操作指南</h1>
            <p>文件菜单提供了管理测试序列文件的基本操作。</p>
            
            <h2>操作说明</h2>
            <ul>
                <li><b>新建序列...</b>: 创建一个新的、空白的测试序列。会自动打开序列编辑器。</li>
                <li><b>打开序列...</b>: 从硬盘加载一个现有的 `.json` 格式的测试序列文件。</li>
                <li><b>保存 (Ctrl+S)</b>: 将当前对测试序列的修改保存到原文件中。</li>
                <li><b>另存为...</b>: 将当前测试序列保存到一个新的 `.json` 文件中。</li>
            </ul>
            <p><b>提示</b>: 在执行新建、打开或退出操作时，如果当前程序有未保存的修改，系统会提示您保存，防止数据丢失。</p>
            </body>
        """

    def _get_cycle_test_content(self):
        return """
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h1>循环压力测试指南</h1>
            <p>此功能用于对产品进行长时间、重复性的压力测试。</p>
            
            <h2>如何使用</h2>
            <ol>
                <li>首先，加载一个您想要用于循环测试的测试序列。</li>
                <li>通过主菜单“工具” -> “循环压力测试”打开设置对话框。</li>
                <li><b>配置测试</b>:
                    <ul>
                        <li>选择要参与测试的一个或多个工位。</li>
                        <li>设置测试的总次数或总时长。</li>
                        <li>配置SN码规则（如固定SN、递增SN或随机SN）。</li>
                        <li>设置失败停止条件（如连续失败N次或累计失败N次后停止）。</li>
                    </ul>
                </li>
                <li>点击“开始”按钮，循环测试将开始在后台运行。</li>
            </ol>
            
            <h2>监控与报告</h2>
            <p>测试开始后，会弹出一个监控窗口，实时显示每个工位的测试次数、通过率和运行时间。测试结束后，会自动生成一份详细的总结报告，保存在 <b>CycleTestReports</b> 文件夹中。</p>
            </body>
        """

    def _get_analysis_content(self):
        return """
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h1>历史数据分析指南</h1>
            <p>本平台会将每一次的测试结果记录到本地数据库中，此功能提供了一个网页界面来查询和分析这些历史数据。</p>
            
            <h2>如何访问</h2>
            <p>通过主菜单“工具” -> “历史数据分析”。</p>
            
            <h2>功能说明</h2>
            <p>点击后，程序会自动在后台启动一个本地Web服务器，并用您的默认浏览器打开数据分析页面。您可以在该页面上：</p>
            <ul>
                <li>按日期、SN号、测试结果等条件筛选测试记录。</li>
                <li>查看测试数据的统计图表，如通过率趋势等。</li>
                <li>导出查询结果。</li>
            </ul>
            </body>
        """

    def _get_hardware_tools_content(self):
        return """
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h1>硬件工具指南</h1>
            <p>此菜单下包含与硬件直接交互的便捷工具。</p>
            
            <h2>功能说明</h2>
            <ul>
                <li><b>重新启动配置</b>:
                    <p>此功能允许您在不重启软件的情况下重新加载 config.json 配置文件并重新连接所有硬件。在配置编辑器中修改了配置后，点击此菜单即可立即生效。</p>
                    <p><b>注意</b>: 此操作不能在测试正在进行时执行。</p>
                </li>
            </ul>
            </body>
        """

    def _get_sniffer_tool_content(self):
        return """
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h1>通信抓包工具指南</h1>
            <p>通信抓包工具是一个强大的诊断功能，用于监控和记录应用程序与硬件之间的所有串口和以太网通信。</p>
            
            <h2>如何访问</h2>
            <p>通过主菜单的“工具” -> “通信抓包工具...”来打开它。请注意，此功能受权限管理控制。</p>

            <h2>主要功能</h2>
            <ul>
                <li><b>实时监控 (Live Watch)</b>: 打开窗口后，所有工位的通信数据（发送TX/接收RX）都会实时显示在主文本区域。</li>
                <li><b>后台记录</b>:
                    <ol>
                        <li>通过复选框选择您想记录的一个或多个工位。</li>
                        <li>点击“开始后台记录”按钮。</li>
                        <li>工具会自动捕获所选工位在测试时使用的产品SN，并将所有通信数据保存到一个CSV文件中。</li>
                    </ol>
                </li>
                <li><b>报告位置</b>: 所有记录的报告都保存在项目根目录下的 <b>SnifferReports</b> 文件夹内。</li>
                <li><b>自动上下文关联</b>: 工具能自动识别出每一条数据来自哪个工位、哪个串口，以及对应哪个SN，使分析变得简单清晰。</li>
            </ul>
            </body>
        """

    def _get_permission_guide_content(self):
        return """
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h1>权限管理指南</h1>
            <p>本平台包含一个灵活的权限管理系统，用于控制不同用户对各项功能的访问权限。系统没有密码，仅通过用户ID进行区分。</p>
            
            <h2>如何访问</h2>
            <p>通过主菜单的“工具” -> “权限管理...”来打开（通常需要工程师权限）。</p>

            <h2>核心概念</h2>
            <ul>
                <li><b>角色</b>: 系统预设了两种角色：<b>工程师</b>和<b>操作工</b>。工程师通常拥有所有权限，而操作工的权限则可以被精确配置。</li>
                <li><b>用户 (Users)</b>: 系统中的操作员账户。您可以创建新的操作工账户并为其分配权限。</li>
                <li><b>权限 (Permissions)</b>: 对某个特定操作的许可，例如 `access_sniffer_tool` (访问抓包工具) 或 `edit_test_sequence` (编辑测试程序)。</li>
            </ul>

            <h2>操作指南</h2>
            <p>在权限管理窗口中，工程师可以：</p>
            <ul>
                <li><b>新增操作工</b>: 点击“添加用户”按钮，输入新操作工的ID。</li>
                <li><b>删除操作工</b>: 选中一个用户后，点击“删除用户”按钮。</li>
                <li><b>配置权限</b>: 在左侧列表中选择一个用户后，在右侧的权限列表中，勾选或取消勾选该用户应当拥有的权限。</li>
            </ul>
            <p><b>自动发现新权限</b>: 当开发者在代码中定义了一个新的权限后，程序会在下次启动时自动将其添加到权限列表中，工程师可以直接在界面中进行分配。</p>
            </body>
        """

    def _get_order_estimation_content(self):
        return """
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h1>测试时间预测</h1>
            <p>此工具用于预估完成指定数量产品测试所需的时间，帮助生产计划安排。</p>
            
            <h2>如何访问</h2>
            <p>通过主菜单"工具" -> "测试时间预测"打开。</p>

            <h2>主要功能</h2>
            <ul>
                <li><b>自动数据采集</b>: 系统根据当前加载的测试序列自动统计测试数据，无需手动输入。</li>
                <li><b>当前已完成总数</b>: 显示今日该序列的Pass和Fail数量及良率。</li>
                <li><b>时间参数显示</b>: 实时显示"平均测试时长"和"平均拿取耗时"。</li>
                <li><b>预计完成时间</b>: 输入目标数量后，自动计算预计完成时间。</li>
                <li><b>车间作息配置</b>: 设置工作时间和午餐/晚餐时长，预估时间会自动排除休息时段。</li>
                <li><b>按日期分割</b>: 每个序列每天自动创建一条会话记录，跨天自动分开统计。</li>
            </ul>
            
            <h2>智能算法</h2>
            <ul>
                <li><b>智能拿取耗时</b>: 用前10次间隔建立基准，超过3倍基准的异常间隔（如休息、离开）自动排除。</li>
                <li><b>午餐晚餐扣除</b>: 仅当会话实际跨过用餐时段时才扣除相应时长。</li>
            </ul>
            
            <h2>历史报告</h2>
            <p>点击"查看历史详情"按钮，会生成包含以下信息的HTML报告：</p>
            <ul>
                <li>日期、测试序列、工位数、操作员</li>
                <li>Pass/Fail数、良率、平均测试时长、拿取耗时</li>
                <li>总耗时(实际)、午餐/晚餐时长、总耗时(工作)</li>
            </ul>
            </body>
        """

    def _get_thimble_guide_content(self):
        return """
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h1>顶针管理</h1>
            <p>此功能用于追踪顶针治具的使用次数，及时提醒更换，确保测试质量。</p>
            
            <h2>如何访问</h2>
            <p>通过主菜单"工具" -> "顶针管理"打开。</p>

            <h2>核心概念</h2>
            <ul>
                <li><b>治具编码</b>: 每个物理治具的唯一标识（如贴在治具上的条码）。</li>
                <li><b>关联序列</b>: 一个治具可以被多个测试序列使用，系统分别统计。</li>
                <li><b>使用次数</b>: 分为治具总使用次数和各序列单独使用次数。</li>
                <li><b>使用上限</b>: 默认20,000次，达到上限时发出警告。</li>
                <li><b>预警天数</b>: 默认90天，超过此天数也会发出提醒。</li>
            </ul>

            <h2>操作指南</h2>
            <ul>
                <li><b>添加治具</b>: 点击"添加治具"按钮，输入新治具的编码。</li>
                <li><b>关联序列</b>: 选中治具后，点击"添加序列"，选择要关联的测试序列。</li>
                <li><b>设置上限</b>: 双击"使用上限"或"预警天数"单元格直接编辑。</li>
                <li><b>重置计数</b>: 更换新治具后，使用"重置使用次数"按钮清零（会记录到历史）。</li>
                <li><b>历史记录</b>: 点击"历史记录"按钮查看顶针更换历史报告。</li>
                <li><b>首次关联</b>: 运行未关联的序列时，会自动弹窗提示输入治具编码。</li>
            </ul>
            
            <h2>历史记录</h2>
            <p>每次重置使用次数时，系统会记录：工位、治具编码、重置时间、重置前使用次数、首次使用时间、操作员等信息。</p>
            </body>
        """

    def _get_cable_guide_content(self):
        return """
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h1>线缆管理</h1>
            <p>此功能用于追踪和管理流动线缆的使用寿命，确保线缆在达到使用上限前及时更换。</p>
            
            <h2>如何访问</h2>
            <p>通过主菜单"工具" -> "线缆管理"打开。</p>

            <h2>工作流程</h2>
            <ol>
                <li><b>加载序列后扫码</b>: 每次加载测试序列后，会弹出扫码对话框要求扫描每个工位的线缆SN。</li>
                <li><b>自动计数</b>: 每次测试完成（无论Pass或Fail），对应工位绑定的线缆使用次数自动+1。</li>
                <li><b>寿命监控</b>: 当线缆使用次数接近或达到上限时，扫码时会显示警告。</li>
            </ol>

            <h2>主要功能</h2>
            <ul>
                <li><b>线缆列表</b>: 显示所有已登记的线缆及其使用状态。</li>
                <li><b>添加线缆</b>: 手动添加新线缆到系统。</li>
                <li><b>标记报废</b>: 将损坏或达到寿命的线缆标记为报废。</li>
                <li><b>修改上限</b>: 针对不同规格的线缆可设置不同的使用上限（默认10,000次）。</li>
                <li><b>绑定线缆到工位</b>: 中途更换线缆时，可手动将新线缆绑定到指定工位。</li>
                <li><b>查看报告</b>: 生成HTML格式的线缆使用报告，支持搜索和CSV导出。</li>
            </ul>
            
            <h2>注意事项</h2>
            <ul>
                <li>线缆绑定在加载序列后通过扫码完成，关闭程序后绑定关系会清空。</li>
                <li>线缆使用记录持久保存在数据库中。</li>
                <li>已报废的线缆无法再绑定到工位。</li>
            </ul>
            </body>
        """

    def _get_guide_overview_content(self):
        return """
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h1>功能指南</h1>
            <p>功能指南包含了本测试平台所有主要功能的详细说明。请点击左侧子项查看具体内容。</p>
            
            <h2>内容概览</h2>
            <ul>
                <li><b>主界面与工位</b>: 测试执行的主控制中心，包括工位面板、状态显示、控制按钮等。</li>
                <li><b>文件操作</b>: 新建、打开、保存测试序列文件的操作说明。</li>
                <li><b>序列编辑器</b>: 创建和修改测试序列的核心工具，包括字段说明、CPK统计、流程控制等。</li>
                <li><b>系统配置</b>: 硬件设备配置、工位绑定、全局设置等。</li>
                <li><b>工具</b>: 包含循环压力测试、串口抓包、历史分析、顶针管理、线缆管理等实用工具。</li>
                <li><b>权限管理</b>: 用户角色和权限的配置说明。</li>
            </ul>
            </body>
        """

    def _get_mod_ref_overview_content(self):
        return """
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h1>模块函数参考</h1>
            <p>此部分列出了所有可用于测试序列的模块及其函数。请点击左侧的模块名展开查看其包含的函数列表。</p>
            
            <h2>如何使用</h2>
            <ol>
                <li>在序列编辑器中，选择要编辑的测试步骤。</li>
                <li>在<b>模块</b>字段中选择需要的模块名。</li>
                <li>在<b>函数</b>字段中选择要调用的函数。</li>
                <li>根据函数文档，在<b>参数</b>字段中填写所需的参数。</li>
            </ol>
            
            <h2>模块列表</h2>
            <p>展开左侧的模块项即可查看每个模块的详细文档和函数列表。每个函数文档包含：</p>
            <ul>
                <li>函数签名（参数名称、类型、默认值）</li>
                <li>功能描述</li>
                <li>参数详细说明</li>
                <li>返回值说明</li>
                <li>使用示例（如有）</li>
            </ul>
            </body>
        """

    def _get_driver_dev_guide_content(self):
        return """
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h1>驱动开发指南 (v2.1.0)</h1>
            <p>本系统支持动态加载驱动配置界面。只需在 <code>drivers/</code> 目录下创建符合规范的驱动文件，系统会自动在配置编辑器中生成对应的配置 Tab。</p>
            
            <h2>快速开始</h2>
            <p>在 <code>drivers/</code> 目录下创建一个 Python 文件，定义一个包含 <code>CONFIG_TAB</code> 和 <code>CONFIG_SCHEMA</code> 的类：</p>
            
            <div style='background-color: #2E2E2E; padding: 15px; border-radius: 5px; font-family: monospace;'>
<pre style='margin: 0; color: #DCDCDC;'>
class MyDriver:
    # ========== 驱动元数据 ==========
    DRIVER_META = {
        "name": "MyDriver",
        "display_name": "我的设备",
        "category": "custom",
        "interface": "usb",
    }
    
    # ========== 配置 Tab 定义 ==========
    CONFIG_TAB = {
        "tab_name": "我的设备配置",    # Tab 标签名称
        "config_key": "my_config",      # 在 config.json 中的 key
        "mode": "shared",               # "shared" 或 "per_station"
    }
    
    # ========== 配置表单定义 ==========
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
        }
    }
</pre>
            </div>
            
            <h2>CONFIG_TAB 字段说明</h2>
            <table border='1' cellpadding='8' style='border-collapse: collapse; width: 100%;'>
                <tr style='background-color: #3a3a3a;'>
                    <th>字段</th><th>类型</th><th>说明</th>
                </tr>
                <tr><td><b>tab_name</b></td><td>string</td><td>Tab 标签显示名称</td></tr>
                <tr><td><b>config_key</b></td><td>string</td><td>配置在 config.json 中的键名</td></tr>
                <tr><td><b>mode</b></td><td>string</td><td><code>shared</code> = 所有工位共用一个配置<br><code>per_station</code> = 每工位独立配置（固定4工位，2x2布局）</td></tr>
            </table>
            
            <h2>CONFIG_SCHEMA 支持的字段类型</h2>
            <table border='1' cellpadding='8' style='border-collapse: collapse; width: 100%;'>
                <tr style='background-color: #3a3a3a;'>
                    <th>类型</th><th>说明</th><th>示例</th>
                </tr>
                <tr><td><code>string</code></td><td>文本输入框</td><td><code>"default": "hello"</code></td></tr>
                <tr><td><code>int</code></td><td>整数输入框</td><td><code>"default": 100</code></td></tr>
                <tr><td><code>float</code></td><td>浮点数输入框</td><td><code>"default": 3.14</code></td></tr>
                <tr><td><code>bool</code></td><td>复选框</td><td><code>"default": True</code></td></tr>
                <tr><td><code>select</code></td><td>下拉选择框</td><td><code>"options": ["TCP", "UDP"]</code></td></tr>
                <tr><td><code>file</code></td><td>文件选择器</td><td>带浏览按钮的文件路径</td></tr>
                <tr><td><code>directory</code></td><td>目录选择器</td><td>带浏览按钮的目录路径</td></tr>
                <tr><td><code>visa</code></td><td>VISA 地址选择器</td><td>点击下拉框自动扫描</td></tr>
                <tr><td><code>visa_with_connect</code></td><td>VISA + 启动时连接</td><td>VISA选择 + 复选框</td></tr>
                <tr><td><code>serial_port</code></td><td>串口选择器</td><td>点击下拉框自动扫描</td></tr>
                <tr><td><code>baudrate</code></td><td>波特率选择器</td><td>常用波特率下拉框</td></tr>
            </table>
            
            <h2>高级类型</h2>
            
            <h3>mode_switch（模式切换）</h3>
            <p>支持共享/独立/专用三种模式切换：</p>
            <div style='background-color: #2E2E2E; padding: 15px; border-radius: 5px; font-family: monospace;'>
<pre style='margin: 0; color: #DCDCDC;'>
"power_mode": {
    "type": "mode_switch",
    "label": "电源模式",
    "shared_label": "共享模式",
    "independent_label": "独立模式",
    "dedicated_label": "专用模式",  # 可选
    "station_count": 4,
    "shared_schema": { ... },
    "independent_schema": { ... },
    "dedicated_schema": { ... }  # 可选
}
</pre>
            </div>
            
            <h3>station_group（工位分组，2x2布局）</h3>
            <p>用于每工位独立配置的2x2网格布局：</p>
            <div style='background-color: #2E2E2E; padding: 15px; border-radius: 5px; font-family: monospace;'>
<pre style='margin: 0; color: #DCDCDC;'>
"stations": {
    "type": "station_group",
    "label": "工位配置",
    "station_count": 4,
    "schema": {
        "device_sn": {"type": "string", "label": "设备SN"}
    }
}
</pre>
            </div>
            
            <h3>channel_config（通道配置）</h3>
            <p>用于电源等多通道设备：</p>
            <div style='background-color: #2E2E2E; padding: 15px; border-radius: 5px; font-family: monospace;'>
<pre style='margin: 0; color: #DCDCDC;'>
"channel_mappings": {
    "type": "channel_config",
    "label": "通道配置",
    "channel_count": 3,
    "max_voltage": 30,
    "max_current": 3
}
</pre>
            </div>
            
            <h3>multi_psu_config（多电源配置）</h3>
            <p>用于多台电源的专用配置（如两台DP832）：</p>
            <div style='background-color: #2E2E2E; padding: 15px; border-radius: 5px; font-family: monospace;'>
<pre style='margin: 0; color: #DCDCDC;'>
"psu_config": {
    "type": "multi_psu_config",
    "label": "电源配置",
    "psu_ids": ["PSU_1", "PSU_2"],
    "supply_types": {
        "battery_supply": "电池供电",
        "daq_supply": "采集卡供电"
    },
    "station_count": 4,
    "max_channels": 3
}
</pre>
            </div>
            
            <h2>示例：完整的电源驱动</h2>
            <div style='background-color: #2E2E2E; padding: 15px; border-radius: 5px; font-family: monospace;'>
<pre style='margin: 0; color: #DCDCDC;'>
class MyPowerSupply:
    DRIVER_META = {
        "name": "MyPowerSupply",
        "display_name": "我的电源",
        "category": "power",
        "interface": "visa",
    }
    
    CONFIG_TAB = {
        "tab_name": "我的电源配置",
        "config_key": "my_psu_config",
        "mode": "shared",
    }
    
    CONFIG_SCHEMA = {
        "power_mode": {
            "type": "mode_switch",
            "label": "电源模式",
            "shared_label": "共享模式",
            "independent_label": "独立模式",
            "station_count": 4,
            "shared_schema": {
                "visa_settings": {
                    "type": "visa_with_connect",
                    "label": "VISA 地址",
                    "auto_connect_default": True
                },
                "channel_mappings": {
                    "type": "channel_config",
                    "channel_count": 4,
                    "max_voltage": 32,
                    "max_current": 3.2
                }
            },
            "independent_schema": {
                "visa_settings": {
                    "type": "visa_with_connect",
                    "label": "VISA 地址"
                }
            }
        }
    }
</pre>
            </div>
            
            <h2>注意事项</h2>
            <ul>
                <li>驱动文件必须放在 <code>drivers/</code> 目录下</li>
                <li>类名可以任意，系统会自动扫描包含 <code>CONFIG_TAB</code> 的类</li>
                <li>配置会自动保存到 <code>config.json</code> 中对应的 <code>config_key</code></li>
                <li>修改驱动文件后需要重启软件才能看到变化</li>
            </ul>
            </body>
        """

    def _get_module_content(self, module):
        module_name = module.__name__.split('.')[-1]
        doc = inspect.getdoc(module) or "没有提供模块文档。"
        escaped_doc = html.escape(doc).replace('\n', '<br>')
        return f"""
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h1>模块: {module_name}</h1>
            <p style='background-color: #333; padding: 10px; border-radius: 5px;'>{escaped_doc}</p>
            <p>请从左侧展开此模块查看其包含的函数列表。</p>
            </body>
        """

    def _get_function_content(self, module_name, func_name, func):
        doc = inspect.getdoc(func) or "此函数没有提供文档字符串。"
        try:
            sig = inspect.signature(func)
            params = []
            for param in sig.parameters.values():
                p_str = param.name
                if param.annotation != inspect.Parameter.empty:
                    type_name = param.annotation.__name__ if hasattr(param.annotation, '__name__') else str(
                        param.annotation)
                    p_str += f": <span style='color: #87CEEB;'>{type_name}</span>"
                if param.default != inspect.Parameter.empty:
                    p_str += f" = <span style='color: #90EE90;'>{repr(param.default)}</span>"
                params.append(p_str)
            signature_html = f"<b>{func_name}</b>({', '.join(params)})"
        except (ValueError, TypeError):
            signature_html = f"<b>{func_name}</b>(...)"

        # --- 新的解析逻辑 ---
        lines = doc.split('\n')
        
        description_lines = []
        params_list = [] # List of (name, [desc_lines])
        return_lines = []
        other_sections = [] # List of lines
        
        # 状态机: 0=Description, 1=Params, 2=Return, 3=Others
        current_state = 0
        
        for line in lines:
            stripped = line.strip()
            
            # 检测状态切换
            if stripped.startswith(':param'):
                current_state = 1
                parts = stripped.split(':', 2)
                if len(parts) > 2:
                    p_name = parts[1].split(' ')[1]
                    p_desc = parts[2].strip()
                    params_list.append([p_name, [p_desc]])
                continue
            elif stripped.startswith(':return'):
                current_state = 2
                parts = stripped.split(':', 2)
                if len(parts) > 2:
                    return_lines.append(parts[2].strip())
                continue
            elif stripped.startswith('用法示例') or stripped.startswith('Usage Example'):
                current_state = 3
                other_sections.append(f"<h4>{html.escape(stripped)}</h4>")
                continue
                
            # 根据状态处理内容
            if current_state == 0:
                # 初始描述
                if stripped:
                    description_lines.append(html.escape(line))
            elif current_state == 1:
                # 参数详情 (支持多行缩进)
                if params_list:
                    # 如果这行有内容，即便是缩进的，也作为从属描述
                    # 我们保留原有的格式（比如换行）
                    # 简单起见，如果非空行，就追加到最后一个参数的描述里
                    if stripped:
                        # 尝试检测是否是列表项
                        prefix = "<br>&nbsp;&nbsp;&nbsp;&nbsp;"
                        params_list[-1][1].append(f"{prefix}{html.escape(stripped)}")
            elif current_state == 2:
                if stripped:
                    return_lines.append(html.escape(stripped))
            elif current_state == 3:
                # 其他部分 (原样保留格式，比如代码块)
                # 简单的处理：如果看起来像代码，用等宽字体
                if stripped.startswith('-') or stripped.startswith('{'):
                     other_sections.append(f"<div style='font-family: monospace; margin-left: 20px;'>{html.escape(line)}</div>")
                else:
                    other_sections.append(html.escape(line) + "<br>")

        # 构建HTML
        description_html = "<br>".join(description_lines)
        
        params_html = ""
        if params_list:
            items = []
            for name, desc_lines in params_list:
                full_desc = "".join(desc_lines)
                items.append(f"<li><b>{name}</b>: {full_desc}</li>")
            params_html = f"<h4>参数:</h4><ul>{''.join(items)}</ul>"
            
        return_html = ""
        if return_lines:
            return_html = f"<p><b>返回:</b> {' '.join(return_lines)}</p>"
            
        others_html = "".join(other_sections)

        return f"""
            <body style='font-family: sans-serif; font-size: 16px; line-height: 1.6;'>
            <h2>函数: <span style='font-family: "Courier New", monospace; color: #DAA520;'>{module_name}.{func_name}</span></h2>
            <div style='background-color: #2E2E2E; padding: 15px; border-radius: 5px; font-family: "Courier New", monospace; color: #DCDCDC;'>
                {signature_html}
            </div>
            <h4>描述:</h4>
            <p>{description_html}</p>
            {params_html}
            {return_html}
            {others_html}
            </body>
        """


if __name__ == '__main__':
    app = QApplication(sys.argv)
    try:
        from qt_material import apply_stylesheet

        apply_stylesheet(app, theme='dark_teal.xml')
    except ImportError:
        print("qt_material not found, using default style.")


    def mock_power_on(voltage: int, current: float = 1.0):
        pass


    def mock_read_voltage():
        pass


    mock_power_module = type(sys)('power')
    mock_power_module.__doc__ = "这是一个模拟的电源控制模块..."
    mock_power_module.power_on = mock_power_on;
    mock_power_module.read_voltage = mock_read_voltage
    mock_comm_module = type(sys)('communication')
    mock_comm_module.__doc__ = "这是一个模拟的通信模块。"
    mock_modules = {"power": mock_power_module, "communication": mock_comm_module}

    dialog = HelpDialog(None, mock_modules)
    dialog.show()
    sys.exit(app.exec())
