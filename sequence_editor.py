# 文件路径: sequence_editor.py (信号风暴终极修复版 - 完整代码)

import sys
import json
import inspect
from collections import defaultdict
import copy

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QLineEdit, QTableWidget, QTableWidgetItem,
    QSplitter, QMenu, QHeaderView, QAbstractItemView, QMessageBox,
    QSizePolicy, QTextEdit, QStyledItemDelegate, QStyle, QFileDialog
)
from PySide6.QtGui import (
    QAction, QIcon, QColor, QKeySequence, QUndoStack, QUndoCommand, QFontMetrics, QPalette, QFont
)
from PySide6.QtCore import Qt, QEvent, QObject, QTimer, QMimeData


def resource_path(relative_path):
    import os
    base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


class SkippedStepDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        is_skipped = index.data(Qt.UserRole) == 'Skipped'
        
        # If skipped and NOT selected, draw custom background
        if is_skipped and not (option.state & QStyle.State_Selected):
            painter.save()
            
            # Fill background
            painter.fillRect(option.rect, QColor("#999999"))
            
            # Draw text manually to avoid background overwrite by stylesheet
            text = str(index.data(Qt.DisplayRole))
            if text:
                # Ensure font from option is used (which comes from the item)
                painter.setFont(option.font)
                
                # Use standard text formatting
                painter.setPen(QColor(Qt.white))
                
                # Get alignment
                alignment = index.data(Qt.TextAlignmentRole)
                if not alignment:
                    alignment = Qt.AlignLeft | Qt.AlignVCenter
                
                # For left-aligned text, add a small margin to match standard view
                if alignment & Qt.AlignLeft:
                    draw_rect = option.rect.adjusted(4, 0, 0, 0)
                else:
                    draw_rect = option.rect

                # Using drawItemText from style is safer for alignment/margins
                option.widget.style().drawItemText(
                    painter, draw_rect, alignment, option.palette, True, text, QPalette.Text
                )
                
            painter.restore()
        else:
            super().paint(painter, option, index)


class ChangeSequenceCommand(QUndoCommand):
    def __init__(self, editor, old_data, new_data, description, old_selection=None, new_selection=None):
        super().__init__(description)
        self.editor = editor
        self.old_data = copy.deepcopy(old_data)
        self.new_data = copy.deepcopy(new_data)
        self.old_selection = old_selection if old_selection is not None else []
        self.new_selection = new_selection if new_selection is not None else []

    def undo(self):
        self.editor.sequence_data = copy.deepcopy(self.old_data)
        self.editor.populate_table()
        self.editor._restore_selection(self.old_selection)

    def redo(self):
        self.editor.sequence_data = copy.deepcopy(self.new_data)
        self.editor.populate_table()
        self.editor._restore_selection(self.new_selection)


def _adjust_goto_steps(sequence_data, insert_position, count, is_insert=True):
    """
    调整所有 GotoStep 值以响应步骤的添加或删除。
    
    :param sequence_data: 序列数据列表
    :param insert_position: 插入或删除的位置（行索引，0-based）
    :param count: 添加或删除的步骤数量
    :param is_insert: True 表示插入，False 表示删除
    """
    # 计算步骤编号（跳过注释行）
    def row_to_step_number(row_idx, data):
        step_num = 0
        for i in range(len(data)):
            test_name = str(data[i].get('TestName', '')).strip()
            if not test_name.startswith(('*', '#')):
                step_num += 1
            if i == row_idx:
                return step_num if not test_name.startswith(('*', '#')) else None
        return None
    
    def step_number_to_row(step_num, data):
        current_step = 0
        for i, row in enumerate(data):
            test_name = str(row.get('TestName', '')).strip()
            if not test_name.startswith(('*', '#')):
                current_step += 1
                if current_step == step_num:
                    return i
        return None
    
    # 计算插入/删除位置对应的步骤编号
    affected_step_num = row_to_step_number(insert_position, sequence_data)
    if affected_step_num is None:
        # 如果是在注释行位置操作，找到之后的第一个有效步骤
        for i in range(insert_position, len(sequence_data)):
            affected_step_num = row_to_step_number(i, sequence_data)
            if affected_step_num:
                break
        if affected_step_num is None:
            return  # 没有可调整的步骤
    
    # 遍历所有步骤，调整 GotoStep 值
    for row_data in sequence_data:
        goto_step_str = str(row_data.get('GotoStep', '')).strip()
        step_action = row_data.get('StepAction', '')
        
        if goto_step_str and 'goto_step' in step_action:
            try:
                goto_step_num = int(goto_step_str)
                
                # 只调整那些指向受影响位置及之后步骤的 GotoStep
                if goto_step_num >= affected_step_num:
                    if is_insert:
                        row_data['GotoStep'] = str(goto_step_num + count)
                    else:
                        if goto_step_num >= affected_step_num + count:
                            row_data['GotoStep'] = str(goto_step_num - count)
                        else:
                            # GotoStep 指向被删除的步骤，清空它
                            row_data['GotoStep'] = ''
            except ValueError:
                pass  # GotoStep 不是有效数字，跳过


class DraggableTableWidget(QTableWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.sequence_editor = parent

    def dropEvent(self, event: QEvent):
        if not event.isAccepted() and event.source() == self:
            drop_row = self.rowAt(event.position().toPoint().y())
            if drop_row == -1: drop_row = self.rowCount()
            rows_to_move = self.sequence_editor._get_selected_rows_indices()
            if drop_row in rows_to_move: return
            old_data = copy.deepcopy(self.sequence_editor.sequence_data)
            new_data = copy.deepcopy(old_data)
            moved_items = [new_data[row] for row in rows_to_move]
            for row in reversed(rows_to_move): del new_data[row]
            offset = sum(1 for row in rows_to_move if row < drop_row)
            drop_row -= offset
            new_selection = []
            for i, item in enumerate(moved_items):
                new_data.insert(drop_row + i, item)
                new_selection.append(drop_row + i)
            command = ChangeSequenceCommand(self.sequence_editor, old_data, new_data, "拖动排序", rows_to_move,
                                            new_selection)
            self.sequence_editor.undo_stack.push(command)
            event.accept()
        super().dropEvent(event)


class SequenceEditor(QDialog):
    def __init__(self, parent, sequence_data, test_modules, save_callback):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.Window | Qt.WindowMinimizeButtonHint | Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.original_title = "序列编辑器"
        self.setWindowTitle(self.original_title)
        self.setWindowIcon(QIcon(resource_path('app_icon.ico')))
        self.sequence_data = [dict(row) for row in sequence_data]
        self.save_callback = save_callback
        self.module_map = test_modules
        self.module_functions = self._get_module_functions()
        self.headers_en = ['Step', 'TestName', 'Module', 'Function', 'Parameters', 'Variable', 'Compare', 'LowerLimit',
                           'UpperLimit', 'CPK', 'StepAction', 'GotoStep', 'Skip']
        self.headers_cn = ['步骤', '测试名称', '模块', '函数', '参数', '变量', '比较', '最小值', '最大值', 'CPK分析', '步骤处理',
                           '跳转步骤', '跳过']
        self.header_map_cn_to_en = dict(zip(self.headers_cn, self.headers_en))
        self.header_map_en_to_cn = {en: cn for cn, en in zip(self.headers_cn, self.headers_en)}
        self.column_map_en_to_idx = {name: i for i, name in enumerate(self.headers_en)}
        self._clipboard = []
        self._applying_data_to_editors = False
        self.editor_modified = False
        self._syncing_from_table = False  # 防止表格编辑和编辑器之间无限递归
        self.undo_stack = QUndoStack(self)
        self.undo_stack.setUndoLimit(50)
        self.undo_stack.cleanChanged.connect(self._on_stack_clean_changed)
        self._create_actions()
        self._create_widgets()
        self._connect_signals()
        self.populate_table()
        self._update_title()
        self._should_restore_maximized = False
        self._initialized = False

    def _create_actions(self):
        self.undo_action = self.undo_stack.createUndoAction(self, "撤销")
        self.redo_action = self.undo_stack.createRedoAction(self, "恢复")
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.cut_action = QAction("剪切", self, shortcut=QKeySequence.Cut, triggered=self.cut_step)
        self.copy_action = QAction("复制", self, shortcut=QKeySequence.Copy, triggered=self.copy_step)
        self.paste_action = QAction("粘贴", self, shortcut=QKeySequence.Paste, triggered=self.paste_step)
        self.add_step_action = QAction("添加步骤", self, triggered=self.add_step)
        self.del_step_action = QAction("删除步骤", self, shortcut=QKeySequence.Delete, triggered=self.delete_selected_steps)
        self.addAction(self.del_step_action)  # 注册到窗口以激活快捷键

        # 添加保存动作及 Ctrl+S 快捷键
        self.save_action = QAction("保存", self)
        self.save_action.setShortcut(QKeySequence.Save)  # QKeySequence.Save is typically Ctrl+S
        self.save_action.triggered.connect(self._save_and_apply)
        self.addAction(self.save_action)

    def _create_widgets(self):
        main_layout = QVBoxLayout(self)
        toolbar_widget = QWidget()
        toolbar = QHBoxLayout(toolbar_widget)
        main_layout.addWidget(toolbar_widget)
        self.add_btn = QPushButton("添加步骤")
        toolbar.addWidget(self.add_btn)
        self.del_btn = QPushButton("删除步骤")
        toolbar.addWidget(self.del_btn)
        self.up_btn = QPushButton("上移")
        toolbar.addWidget(self.up_btn)
        self.down_btn = QPushButton("下移")
        toolbar.addWidget(self.down_btn)
        self.undo_btn = QPushButton("撤销")
        toolbar.addWidget(self.undo_btn)
        self.redo_btn = QPushButton("恢复")
        toolbar.addWidget(self.redo_btn)
        toolbar.addStretch()
        self.save_apply_button = QPushButton("保存并应用")
        toolbar.addWidget(self.save_apply_button)
        self.close_button = QPushButton("关闭")
        toolbar.addWidget(self.close_button)
        splitter = QSplitter(Qt.Vertical)
        main_layout.addWidget(splitter, 1)
        self.table = DraggableTableWidget(self)
        self.table.setItemDelegate(SkippedStepDelegate(self.table))
        self._setup_table()
        splitter.addWidget(self.table)
        editor_area = QWidget()
        editor_area.setObjectName("EditorArea")
        editor_area.setStyleSheet("#EditorArea { border-top: 1px solid #555; padding: 5px; }")
        self.editor_layout = QGridLayout(editor_area)
        self.editors = {}
        self._create_editor_fields_new_layout()
        splitter.addWidget(editor_area)
        splitter.setSizes([800, 200])

    def _create_editor_fields_new_layout(self):
        layout_map = {
            'TestName': (0, 0), 'Module': (1, 0), 'Function': (2, 0),
            'Parameters': (0, 2), 'Variable': (2, 2),
            'Compare': (0, 4), 'LowerLimit': (1, 4), 'UpperLimit': (2, 4),
            'CPK': (0, 6),
            'StepAction': (0, 8), 'GotoStep': (1, 8), 'Skip': (2, 8)
        }
        self.editor_layout.setColumnStretch(1, 1);
        self.editor_layout.setColumnStretch(3, 1)
        self.editor_layout.setColumnStretch(5, 1);
        self.editor_layout.setColumnStretch(7, 1) # CPK column narrow
        self.editor_layout.setColumnStretch(9, 1)
        single_line_height = QLineEdit().sizeHint().height()
        params_box_height = single_line_height * 2 + 10
        for name, pos in layout_map.items():
            row, col = pos
            header_cn = self.header_map_en_to_cn.get(name, name)
            label = QLabel(header_cn + ":")
            label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            if name == 'Parameters':
                editor = QTextEdit();
                editor.setAcceptRichText(False)
                editor.setFixedHeight(params_box_height)
                editor.setContextMenuPolicy(Qt.CustomContextMenu)
                editor.customContextMenuRequested.connect(self._show_params_context_menu)
            elif name in ['Module', 'Function', 'StepAction', 'Skip', 'Compare', 'GotoStep', 'CPK']:
                editor = QComboBox()
                editor.setEditable(name in ['Module', 'Function'])
            else:
                editor = QLineEdit()
            self.editor_layout.addWidget(label, row, col)
            if name == 'Parameters':
                self.editor_layout.addWidget(editor, row, col + 1, 2, 1)
            else:
                self.editor_layout.addWidget(editor, row, col + 1)
            self.editors[name] = editor
            if name == 'Module': editor.addItems([''] + sorted(self.module_map.keys()))
            if name == 'StepAction':
                editor.addItems(['stop', 'continue', 'pass_goto_step', 'fail_goto_step'])
                editor.setToolTip(
                    "stop: 失败时停止(默认)\ncontinue: 失败时继续\npass_goto_step: 通过时跳转\nfail_goto_step: 失败时跳转")
            if name == 'Skip': editor.addItems(['No', 'Yes'])
            if name == 'CPK': editor.addItems(['False', 'True'])
            if name == 'Compare': editor.addItems(
                ['', 'InRange', 'NotInRange', '||', '==', '!=', '>', '>=', '<=', '<', 'Contains', 'NotContains'])
        self.editors['GotoStep'].setEnabled(False)

    # =========================================================
    #            【【【 Bug的最终根源与终极修复 】】】
    # =========================================================
    def _connect_signals(self):
        self.add_btn.clicked.connect(self.add_step)
        self.del_btn.clicked.connect(self.delete_selected_steps)
        self.up_btn.clicked.connect(self._move_steps_up)
        self.down_btn.clicked.connect(self._move_steps_down)
        self.undo_btn.clicked.connect(self.undo_stack.undo)
        self.redo_btn.clicked.connect(self.undo_stack.redo)
        self.undo_stack.canUndoChanged.connect(self.undo_btn.setEnabled)
        self.undo_stack.canRedoChanged.connect(self.redo_btn.setEnabled)
        self.undo_btn.setEnabled(self.undo_stack.canUndo())
        self.redo_btn.setEnabled(self.undo_stack.canRedo())
        self.table.itemSelectionChanged.connect(self.on_step_select)
        self.table.cellChanged.connect(self._on_table_cell_changed)
        self.save_apply_button.clicked.connect(self._save_and_apply)
        self.close_button.clicked.connect(self.close)

        # 1. 废除所有零散的信号，建立统一指挥
        for name, editor in self.editors.items():
            if isinstance(editor, QLineEdit):
                editor.editingFinished.connect(lambda field=name: self._on_field_editing_finished(field))
            elif isinstance(editor, QTextEdit):
                editor.installEventFilter(self)
            elif name not in ['Module', 'Function']:  # Module和Function有特殊逻辑，单独处理
                if isinstance(editor, QComboBox):
                    editor.activated.connect(lambda idx, field=name: self._on_field_editing_finished(field))

        # 2. 为 Module 设立唯一的总指挥信号
        self.editors['Module'].currentTextChanged.connect(self._on_module_changed)

        # 3. 为 Function 使用 activated 信号，只有用户实际从下拉列表选择时才触发
        #    而不是 currentIndexChanged（会在程序设置值时也触发）
        self.editors['Function'].activated.connect(self._on_function_activated)

        # 4. 其他下拉框的联动逻辑
        self.editors['Compare'].activated.connect(self._update_limit_editors_state)
        self.editors['StepAction'].activated.connect(self._update_goto_step_field_state)

    def _on_module_changed(self, module_name):
        """当模块文本改变时（无论是选择还是编辑），这是唯一的入口点"""
        if self._applying_data_to_editors: return

        # 1. 更新UI：重新填充函数列表，并清空当前函数
        function_combo = self.editors['Function']
        function_combo.blockSignals(True)  # 避免触发 _on_function_changed
        function_combo.clear()
        if module_name in self.module_functions:
            function_combo.addItems([''] + sorted(self.module_functions[module_name].keys()))
        function_combo.blockSignals(False)

        # 2. 提交数据更改
        self._on_field_editing_finished('Module')
        # 因为函数已经被清空了，所以也要提交这个更改
        if function_combo.currentText() != "":
            function_combo.setCurrentIndex(0)  # 确保UI显示空白
        self._on_field_editing_finished('Function')  # 提交空白函数

    def _on_function_changed(self, function_name):
        """当函数文本改变时，这是唯一的入口点"""
        if self._applying_data_to_editors: return

        # 1. 更新UI：如果选择了有效函数，则更新参数模板
        if function_name:
            self._update_parameter_template()

        # 2. 提交数据更改
        self._on_field_editing_finished('Function')

    def _on_function_activated(self, index: int):
        """当用户从函数下拉框中实际选择一个选项时触发（而非仅展开下拉框）。"""
        if self._applying_data_to_editors:
            return
        
        # 获取选中的函数名
        function_name = self.editors['Function'].currentText()
        
        # 获取当前步骤
        selected_rows = self._get_selected_rows_indices()
        if not selected_rows:
            return
        
        current_function = self.sequence_data[selected_rows[0]].get('Function', '')
        
        # 如果函数没有改变，不做任何操作
        if function_name == current_function:
            return
        
        # 保存旧数据用于 undo
        old_data = copy.deepcopy(self.sequence_data)
        
        # 更新函数值
        for row_idx in selected_rows:
            self.sequence_data[row_idx]['Function'] = function_name
        
        # 如果选择了有效函数，生成并更新参数模板
        if function_name:
            module_name = self.editors['Module'].currentText()
            if module_name in self.module_functions and function_name in self.module_functions[module_name]:
                params = self.module_functions[module_name][function_name]
                param_dict = {p: "null" for p in params}
                template_str = json.dumps(param_dict, ensure_ascii=False, separators=(',', ':'))
                # 同时更新 sequence_data 和 UI
                for row_idx in selected_rows:
                    self.sequence_data[row_idx]['Parameters'] = template_str
                self.editors['Parameters'].setPlainText(template_str)
        
        # 一次性提交 undo 命令
        new_data = copy.deepcopy(self.sequence_data)
        if old_data != new_data:
            command = ChangeSequenceCommand(self, old_data, new_data, "更改函数", selected_rows, selected_rows)
            self.undo_stack.push(command)

    def _on_field_editing_finished(self, field_key):
        if self._applying_data_to_editors: return
        selected_rows = self._get_selected_rows_indices()
        if not selected_rows: return
        old_data = copy.deepcopy(self.sequence_data)
        editor = self.editors[field_key]
        if isinstance(editor, QLineEdit):
            new_value = editor.text()
        elif isinstance(editor, QTextEdit):
            new_value = editor.toPlainText()
        elif isinstance(editor, QComboBox):
            if field_key == 'GotoStep':
                new_value = editor.currentText().split(' - ')[0]
            else:
                new_value = editor.currentText()
        else:
            return
        for row_idx in selected_rows:
            self.sequence_data[row_idx][field_key] = new_value
        new_data = copy.deepcopy(self.sequence_data)
        if old_data != new_data:
            command = ChangeSequenceCommand(self, old_data, new_data, "编辑步骤", selected_rows, selected_rows)
            self.undo_stack.push(command)
        # Note: populate_table() is called by undo command's redo(), which handles
        # indentation for TestName properly. For other fields, we don't need to 
        # manually update the table cell here since populate_table() handles it.
        # Skipping manual update to avoid overwriting indented TestName values.

    def eventFilter(self, obj, event):
        if obj == self.editors.get('Parameters') and event.type() == QEvent.FocusOut:
            self._on_field_editing_finished('Parameters')
        return super().eventFilter(obj, event)

    def _on_table_cell_changed(self, row, col):
        """当用户在表格中双击编辑单元格后，同步更改到 sequence_data 和下方编辑器"""
        # 防止 populate_table 触发、防止与编辑器同步造成递归
        if self._syncing_from_table or self._applying_data_to_editors:
            return
        
        # 步骤列为只读显示，不处理
        header_en = self.headers_en[col] if col < len(self.headers_en) else None
        if not header_en or header_en == 'Step':
            return
        
        if row < 0 or row >= len(self.sequence_data):
            return
        
        item = self.table.item(row, col)
        if not item:
            return
        
        new_value = item.text()
        
        # TestName 可能有缩进前缀（空格），去掉后再存
        if header_en == 'TestName':
            new_value = new_value.lstrip()
        
        old_value = str(self.sequence_data[row].get(header_en, ''))
        if new_value == old_value:
            return
        
        # 使用 undo 机制保存更改
        self._syncing_from_table = True
        try:
            old_data = copy.deepcopy(self.sequence_data)
            self.sequence_data[row][header_en] = new_value
            new_data = copy.deepcopy(self.sequence_data)
            command = ChangeSequenceCommand(self, old_data, new_data, "编辑单元格", [row], [row])
            self.undo_stack.push(command)
        finally:
            self._syncing_from_table = False

    def on_step_select(self):
        rows = self._get_selected_rows_indices()
        self.del_btn.setEnabled(bool(rows));
        self.up_btn.setEnabled(bool(rows) and rows[0] > 0)
        self.down_btn.setEnabled(bool(rows) and rows[-1] < self.table.rowCount() - 1)
        if not rows:
            self._clear_editors()
            return
        step_data = self.sequence_data[rows[0]]
        self._applying_data_to_editors = True
        try:
            if 'OnFail' in step_data and 'StepAction' not in step_data:
                step_data['StepAction'] = step_data.pop('OnFail')

            # --- 核心修复：现在这里的逻辑变得更健壮了 ---
            # 先设置模块
            module_name = step_data.get('Module', '')
            self.editors['Module'].setCurrentText(module_name)

            # 然后根据模块，准备好函数列表
            function_combo = self.editors['Function']
            function_combo.clear()
            if module_name in self.module_functions:
                function_combo.addItems([''] + sorted(self.module_functions[module_name].keys()))

            # 最后再设置函数和其他所有字段的值
            for header_en, editor in self.editors.items():
                if header_en == 'Module': continue  # 模块已经设置过了
                value = str(step_data.get(header_en, ""))
                if isinstance(editor, QComboBox):
                    if header_en == 'GotoStep':
                        handling_mode = step_data.get('StepAction', '')
                        goto_combo = self.editors['GotoStep']
                        goto_combo.clear()
                        if 'goto_step' in handling_mode:
                            display_items = self._get_subsequent_display_steps(rows[0])
                            goto_combo.addItems(display_items);
                            goto_combo.setEnabled(True)
                            for i, item_text in enumerate(display_items):
                                if item_text.startswith(value + ' - '):
                                    goto_combo.setCurrentIndex(i)
                                    break
                            else:
                                goto_combo.setCurrentText('')
                        else:
                            goto_combo.setEnabled(False)
                    else:
                        editor.setCurrentText(value)
                elif isinstance(editor, QTextEdit):
                    editor.setPlainText(value)
                else:
                    editor.setText(value)
            self._update_limit_editors_state()
        finally:
            self._applying_data_to_editors = False

    # =========================================================

    def _setup_table(self):
        self.table.setDragEnabled(True);
        self.table.setAcceptDrops(True)
        self.table.setDropIndicatorShown(True);
        self.table.setDragDropMode(QAbstractItemView.InternalMove)
        self.table.setColumnCount(len(self.headers_cn));
        self.table.setHorizontalHeaderLabels(self.headers_cn)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows);
        self.table.verticalHeader().setVisible(False)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu);
        self.table.customContextMenuRequested.connect(self.show_context_menu)
        self.table.addActions(
            [self.cut_action, self.copy_action, self.paste_action, self.undo_action, self.redo_action])
        header = self.table.horizontalHeader();
        header.setSectionResizeMode(QHeaderView.Interactive)
        col_configs = {'步骤': 60, '测试名称': 240, '模块': 120, '函数': 180, '参数': 340, '变量': 110, '比较': 80,
                       '最小值': 65, '最大值': 65, 'CPK分析': 80, '步骤处理': 80, '跳转步骤': 80, '跳过': 60}
        for i, h in enumerate(self.headers_cn):
            if h in col_configs: self.table.setColumnWidth(i, col_configs[h])
        param_col_index = self.headers_cn.index('参数')
        header.setSectionResizeMode(param_col_index, QHeaderView.Stretch)

    def _update_goto_step_field_state(self):
        if self._applying_data_to_editors: return
        self._on_field_editing_finished('StepAction')
        handling_mode = self.editors['StepAction'].currentText()
        goto_combo = self.editors['GotoStep']
        goto_combo.blockSignals(True)
        if 'goto_step' in handling_mode:
            goto_combo.clear()
            selected_rows = self._get_selected_rows_indices()
            if selected_rows: goto_combo.addItems(self._get_subsequent_display_steps(selected_rows[0]))
            goto_combo.setEnabled(True)
        else:
            goto_combo.clear();
            goto_combo.setEnabled(False)
            self._on_field_editing_finished('GotoStep')
        goto_combo.blockSignals(False)

    def _get_subsequent_display_steps(self, current_row_index):
        display_items = ['']
        fm = QFontMetrics(self.editors['GotoStep'].font())
        max_width = 200
        step_col_idx = self.headers_cn.index('步骤')
        for r in range(current_row_index + 1, len(self.sequence_data)):
            row_data = self.sequence_data[r]
            test_name = row_data.get('TestName', '')
            step_item = self.table.item(r, step_col_idx)
            if step_item and step_item.text():
                step_number = step_item.text()
                elided_name = fm.elidedText(test_name, Qt.ElideRight, max_width)
                display_items.append(f"{step_number} - {elided_name}")
        return display_items

    def _update_limit_editors_state(self):
        if self._applying_data_to_editors: return
        self._on_field_editing_finished('Compare')
        
        lower_editor = self.editors['LowerLimit']
        upper_editor = self.editors['UpperLimit']
        mode = self.editors['Compare'].currentText()

        # 根据不同的比较模式，决定启用哪个输入框
        # InRange/NotInRange/||: 上下限都用
        # ==, !=, >=, >: 只用下限 (最小值)
        # <=, <: 只用上限 (最大值)
        # 其他 (Contains等): 都不用
        enable_lower = mode in ['InRange', 'NotInRange', '||', '==', '!=', '>=', '>', 'Contains', 'NotContains']
        enable_upper = mode in ['InRange', 'NotInRange', '||', '<=', '<']

        lower_editor.setEnabled(enable_lower)
        upper_editor.setEnabled(enable_upper)

        # 如果输入框被禁用，则清空其内容
        if not enable_lower and lower_editor.text() != '':
            lower_editor.clear()
            self._on_field_editing_finished('LowerLimit')
        
        if not enable_upper and upper_editor.text() != '':
            upper_editor.clear()
            self._on_field_editing_finished('UpperLimit')

    def populate_table(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)
        self.table.setRowCount(len(self.sequence_data))
        
        step_number = 1

        # Calculate indentation for each row using a stack to properly track nested structures
        row_indents = []
        # Use a stack to properly track nested control flow structures
        indent_stack = []  # Stack of (type, level) tuples
        current_level = 0
        
        for row_data in self.sequence_data:
            func = row_data.get('Function', '')
            level_for_this_row = current_level
            
            # Opening statements: display at current level, then increase level
            if func in ['if_variable', 'for_loop', 'do_while_start']:
                level_for_this_row = current_level
                indent_stack.append((func, current_level))
                current_level += 1
            
            # Intermediate statements (else, elseif): display at parent level, level stays same for next
            elif func in ['else_block', 'elseif_variable']:
                # Find the matching if_variable on the stack
                if indent_stack:
                    level_for_this_row = indent_stack[-1][1]  # Display at same level as the IF
                else:
                    level_for_this_row = max(0, current_level - 1)
            
            # Closing statements: display at parent level, decrease level
            elif func == 'end_if':
                # Pop until we find the matching if_variable or elseif (handles nested structures)
                while indent_stack and indent_stack[-1][0] not in ['if_variable', 'elseif_variable']:
                    indent_stack.pop()
                    current_level = max(0, current_level - 1)
                if indent_stack:
                    level_for_this_row = indent_stack[-1][1]
                    indent_stack.pop()
                    current_level = max(0, current_level - 1)
                else:
                    level_for_this_row = 0
                    current_level = 0
            
            elif func == 'end_for':
                # Pop until we find the matching for_loop
                while indent_stack and indent_stack[-1][0] != 'for_loop':
                    indent_stack.pop()
                    current_level = max(0, current_level - 1)
                if indent_stack:
                    level_for_this_row = indent_stack[-1][1]
                    indent_stack.pop()
                    current_level = max(0, current_level - 1)
                else:
                    level_for_this_row = 0
                    current_level = 0
            
            elif func == 'end_do_while':
                # Pop until we find the matching do_while_start
                while indent_stack and indent_stack[-1][0] != 'do_while_start':
                    indent_stack.pop()
                    current_level = max(0, current_level - 1)
                if indent_stack:
                    level_for_this_row = indent_stack[-1][1]
                    indent_stack.pop()
                    current_level = max(0, current_level - 1)
                else:
                    level_for_this_row = 0
                    current_level = 0
            
            row_indents.append(level_for_this_row)

        for i, row_data in enumerate(self.sequence_data):
            if 'OnFail' in row_data and 'StepAction' not in row_data:
                row_data['StepAction'] = row_data.pop('OnFail')
                
            is_comment = str(row_data.get('TestName', '')).startswith(('*', '#'))
            is_skipped = str(row_data.get('Skip', 'No')) == 'Yes'
            
            for ui_col_idx, header_cn in enumerate(self.headers_cn):
                header_en = self.header_map_cn_to_en[header_cn]
                if header_en == 'Step':
                    value = str(step_number) if not is_comment else ''
                else:
                    value = str(row_data.get(header_en, ''))
                
                # Apply Indentation to TestName
                if header_en == 'TestName':
                    indent = row_indents[i]
                    if indent > 0:
                        # 使用全角空格或其他方式来模拟缩进，或者使用 setIndent (但 setIndent 只对左对齐有效且在某些样式下微调)
                        # 为了视觉明显，我们直接加空格前缀 (3 spaces per level)
                        # 注意：如果用户去编辑，可能会看到空格。但 QDoubleClicked -> Editor uses raw data (no indent).
                        # Populate table uses raw data + display mod.
                        # Wait, when we edit, we explicitly set editor text from sequence_data, which is clean.
                        # So adding spaces here strictly for display is fine.
                        prefix = "    " * indent # 4 spaces per level
                        value = prefix + value 

                item = QTableWidgetItem(value)
                
                # Apply Center Alignment for specific columns
                if header_en in ['Step', 'Skip', 'CPK', 'LowerLimit', 'UpperLimit']:
                    item.setTextAlignment(Qt.AlignCenter)
                
                if is_comment:
                    item.setBackground(QColor("#444"))
                    if header_en != 'TestName':
                        item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
                elif is_skipped:
                    item.setData(Qt.UserRole, 'Skipped')
                    item.setBackground(QColor("#999999"))
                    
                self.table.setItem(i, ui_col_idx, item)
            if not is_comment:
                step_number += 1
        self.table.blockSignals(False)
        self.table.itemSelectionChanged.emit()

    def _get_module_functions(self):
        functions = defaultdict(dict)
        for name, module in self.module_map.items():
            for func_name, func_obj in inspect.getmembers(module, inspect.isfunction):
                if not func_name.startswith('_'):
                    sig = inspect.signature(func_obj)
                    reserved = {'hardware_manager', 'test_engine_instance', 'modbus_slaves', 'uut_sn', 'logger',
                                'get_psu_handle', 'station_id', 'variables', 'last_result', 'power_control'}
                    user_params = [p.name for p in sig.parameters.values() if
                                   p.kind == inspect.Parameter.POSITIONAL_OR_KEYWORD and p.name not in reserved]

                    # 根据用户要求，为 burn_firmware 函数移除在配置中已有的参数
                    if func_name == 'burn_firmware':
                        params_to_remove = {'jlink', 'jlink_sn'}
                        user_params = [p for p in user_params if p not in params_to_remove]

                    functions[name][func_name] = user_params
        return functions

    def _get_selected_rows_indices(self):
        return sorted(list(set(item.row() for item in self.table.selectedItems())))

    def _restore_selection(self, rows_to_select):
        self.table.blockSignals(True);
        self.table.clearSelection()
        for row in rows_to_select:
            if 0 <= row < self.table.rowCount(): self.table.selectRow(row)
        self.table.blockSignals(False);
        self.table.itemSelectionChanged.emit()

    def _on_stack_clean_changed(self, is_clean):
        self.editor_modified = not is_clean
        self._update_title()

    def add_step(self):
        old_data = copy.deepcopy(self.sequence_data)
        selection = self._get_selected_rows_indices()
        new_step = {h: "" for h in self.headers_en if h != 'Step'}
        new_step.update({'StepAction': 'stop', 'Skip': 'No', 'CPK': 'False'})
        insert_row = selection[-1] + 1 if selection else self.table.rowCount()
        self.sequence_data.insert(insert_row, new_step)
        # 自动调整所有 GotoStep 值
        _adjust_goto_steps(self.sequence_data, insert_row, 1, is_insert=True)
        command = ChangeSequenceCommand(self, old_data, self.sequence_data, "添加步骤", selection, [insert_row])
        self.undo_stack.push(command)

    def delete_selected_steps(self):
        selection = self._get_selected_rows_indices()
        if not selection: return
        reply = QMessageBox.question(self, "确认删除", f"确定要删除选定的 {len(selection)} 个步骤吗？",
                                     QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.No: return
        old_data = copy.deepcopy(self.sequence_data)
        # 先调整 GotoStep（在删除前计算）
        first_deleted_row = selection[0]
        delete_count = len(selection)
        for row in reversed(selection): del self.sequence_data[row]
        # 删除后调整剩余步骤的 GotoStep
        _adjust_goto_steps(self.sequence_data, first_deleted_row, delete_count, is_insert=False)
        command = ChangeSequenceCommand(self, old_data, self.sequence_data, "删除步骤", selection, [])
        self.undo_stack.push(command)

    def copy_step(self):
        selection = self._get_selected_rows_indices()
        if not selection: return
        self._clipboard = [copy.deepcopy(self.sequence_data[i]) for i in selection]

    def cut_step(self):
        selection = self._get_selected_rows_indices()
        if not selection: return
        self.copy_step()
        old_data = copy.deepcopy(self.sequence_data)
        for row in reversed(selection): del self.sequence_data[row]
        command = ChangeSequenceCommand(self, old_data, self.sequence_data, "剪切步骤", selection, [])
        self.undo_stack.push(command)

    def paste_step(self):
        if not self._clipboard: return
        selection = self._get_selected_rows_indices()
        insert_row = selection[-1] + 1 if selection else self.table.rowCount()
        old_data = copy.deepcopy(self.sequence_data)
        new_selection = []
        for i, item in enumerate(self._clipboard):
            self.sequence_data.insert(insert_row + i, copy.deepcopy(item))
            new_selection.append(insert_row + i)
        # 自动调整所有 GotoStep 值
        _adjust_goto_steps(self.sequence_data, insert_row, len(self._clipboard), is_insert=True)
        command = ChangeSequenceCommand(self, old_data, self.sequence_data, "粘贴步骤", selection, new_selection)
        self.undo_stack.push(command)

    def _move_steps_up(self):
        selection = self._get_selected_rows_indices()
        if not selection or selection[0] == 0: return
        old_data = copy.deepcopy(self.sequence_data)
        moved_items = [self.sequence_data[i] for i in selection]
        for i in reversed(selection):
            del self.sequence_data[i]
        new_selection = []
        target_row = selection[0] - 1
        for i, item in enumerate(moved_items):
            self.sequence_data.insert(target_row + i, item)
            new_selection.append(target_row + i)
        command = ChangeSequenceCommand(self, old_data, self.sequence_data, "上移步骤", selection, new_selection)
        self.undo_stack.push(command)

    def _move_steps_down(self):
        selection = self._get_selected_rows_indices()
        if not selection or selection[-1] == len(self.sequence_data) - 1: return
        old_data = copy.deepcopy(self.sequence_data)
        moved_items = [self.sequence_data[i] for i in selection]
        for i in reversed(selection):
            del self.sequence_data[i]
        new_selection = []
        target_row = selection[0] + 1
        for i, item in enumerate(moved_items):
            self.sequence_data.insert(target_row + i, item)
            new_selection.append(target_row + i)
        command = ChangeSequenceCommand(self, old_data, self.sequence_data, "下移步骤", selection, new_selection)
        self.undo_stack.push(command)

    def closeEvent(self, event):
        if self.editor_modified:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("保存更改")
            msg_box.setText("当前测试程序有未保存的更改，是否保存？")
            msg_box.setIcon(QMessageBox.Question)
            save_button = msg_box.addButton("保存并应用", QMessageBox.AcceptRole)
            discard_button = msg_box.addButton("不保存", QMessageBox.DestructiveRole)
            cancel_button = msg_box.addButton("取消", QMessageBox.RejectRole)
            msg_box.exec()
            clicked_button = msg_box.clickedButton()
            if clicked_button == save_button:
                self._save_and_apply()
                event.accept()
            elif clicked_button == discard_button:
                event.accept()
            else:  # cancel_button
                event.ignore()
        else:
            event.accept()

    def _update_title(self):
        self.setWindowTitle(self.original_title + (" *" if self.editor_modified else ""))

    def _clear_editors(self):
        self._applying_data_to_editors = True
        try:
            for editor in self.editors.values():
                if isinstance(editor, QLineEdit):
                    editor.clear()
                elif isinstance(editor, (QComboBox, QTextEdit)):
                    if isinstance(editor, QComboBox):
                        editor.setCurrentIndex(-1)
                    else:
                        editor.clear()
        finally:
            self._applying_data_to_editors = False

    def show_context_menu(self, pos):
        menu = QMenu(self)
        menu.addAction(self.add_step_action);
        menu.addAction(self.del_step_action)
        menu.addSeparator();
        menu.addAction(self.copy_action);
        menu.addAction(self.cut_action);
        menu.addAction(self.paste_action)
        menu.addSeparator();
        menu.addAction(self.undo_action);
        menu.addAction(self.redo_action)
        menu.exec(self.table.mapToGlobal(pos))

    def _save_and_apply(self):
        self._assign_blocks()
        
        # 获取主窗口的当前序列文件路径
        main_window = self.parent()
        filepath = getattr(main_window, 'current_sequence_file_path', '')
        
        # 如果有文件路径，直接保存到文件
        if filepath:
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(self.sequence_data, f, indent=2, ensure_ascii=False)
                # 保存成功后，更新主窗口状态
                self.save_callback(copy.deepcopy(self.sequence_data))
                main_window.is_sequence_modified = False
                main_window.update_title()
                self.undo_stack.setClean()
                self._update_title()
                QMessageBox.information(self, "成功", "程序已保存并应用！")
            except Exception as e:
                QMessageBox.critical(self, "保存失败", f"无法保存文件: {e}")
        else:
            # 没有文件路径，弹出保存对话框
            from PySide6.QtWidgets import QFileDialog
            import os
            
            sequences_dir = os.path.join(os.path.abspath("."), 'sequences')
            if not os.path.exists(sequences_dir):
                os.makedirs(sequences_dir)
            
            filepath, _ = QFileDialog.getSaveFileName(self, "保存测试程序", sequences_dir, "JSON files (*.json)")
            
            if filepath:
                try:
                    with open(filepath, 'w', encoding='utf-8') as f:
                        json.dump(self.sequence_data, f, indent=2, ensure_ascii=False)
                    # 保存成功后，更新主窗口状态
                    main_window.current_sequence_file_path = filepath
                    self.save_callback(copy.deepcopy(self.sequence_data))
                    main_window.is_sequence_modified = False
                    main_window.update_title()
                    self.undo_stack.setClean()
                    self._update_title()
                    QMessageBox.information(self, "成功", f"程序已保存到: {os.path.basename(filepath)}")
                except Exception as e:
                    QMessageBox.critical(self, "保存失败", f"无法保存文件: {e}")

    def _update_parameter_template(self):
        module_name = self.editors['Module'].currentText()
        func_name = self.editors['Function'].currentText()
        if module_name in self.module_functions and func_name in self.module_functions[module_name]:
            params = self.module_functions[module_name][func_name]
            param_dict = {p: "null" for p in params}
            template_str = json.dumps(param_dict, ensure_ascii=False, separators=(',', ':'))
            self.editors['Parameters'].setPlainText(template_str)

    def _show_params_context_menu(self, pos):
        """为参数编辑框显示右键菜单，包含"浏览文件"选项"""
        editor = self.editors['Parameters']
        menu = editor.createStandardContextMenu()
        menu.addSeparator()
        
        # 解析当前参数 JSON，查找路径类的 key
        params_text = editor.toPlainText().strip()
        path_keys = []
        if params_text:
            try:
                params_dict = json.loads(params_text)
                if isinstance(params_dict, dict):
                    path_keywords = ('path', 'file', 'dir', 'folder')
                    path_keys = [k for k in params_dict.keys() 
                                 if any(kw in k.lower() for kw in path_keywords)]
            except (json.JSONDecodeError, ValueError):
                pass
        
        if path_keys:
            # 有路径类 key，显示针对性的浏览选项
            for key in path_keys:
                action = menu.addAction(f"📂 浏览文件 → {key}")
                action.triggered.connect(lambda checked=False, k=key: self._browse_file_for_param(k))
        else:
            # 通用浏览选项：在光标处插入路径
            action = menu.addAction("📂 浏览文件路径...")
            action.triggered.connect(lambda: self._browse_file_insert_at_cursor())
        
        menu.exec(editor.mapToGlobal(pos))

    def _browse_file_insert_at_cursor(self):
        """打开文件浏览对话框，在光标位置插入文件路径"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "选择文件", "",
            "所有文件 (*);;HEX 文件 (*.hex);;二进制文件 (*.bin)"
        )
        if not file_path:
            return
        editor = self.editors['Parameters']
        cursor = editor.textCursor()
        cursor.insertText(file_path)

    def _browse_file_for_param(self, param_key):
        """打开文件浏览对话框，将选中的文件路径填入参数 JSON 的指定 key"""
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"选择文件 - {param_key}", "",
            "所有文件 (*);;HEX 文件 (*.hex);;二进制文件 (*.bin)"
        )
        if not file_path:
            return
        
        # Qt 返回的路径已经是正斜杠格式，直接使用
        editor = self.editors['Parameters']
        params_text = editor.toPlainText().strip()
        
        try:
            params_dict = json.loads(params_text)
            if isinstance(params_dict, dict):
                params_dict[param_key] = file_path  # Qt 已使用正斜杠
                new_text = json.dumps(params_dict, ensure_ascii=False, separators=(',', ':'))
                editor.setPlainText(new_text)
                self._on_field_editing_finished('Parameters')
        except (json.JSONDecodeError, ValueError):
            QMessageBox.warning(self, "参数格式错误", "当前参数不是有效的 JSON 格式，无法插入文件路径。")

    def _assign_blocks(self):
        block = '';
        for row_data in self.sequence_data:
            name = str(row_data.get('TestName', '')).strip()
            if name.startswith('*') and '区块' in name:
                if 'Setup' in name:
                    block = 'Setup'
                elif 'Main' in name:
                    block = 'Main'
                elif 'Cleanup' in name:
                    block = 'Cleanup'
            row_data['Block'] = block
