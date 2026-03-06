# -*- coding: utf-8 -*-
"""
通用UI组件和UI相关常量
"""

from PySide6.QtWidgets import (
    QStyledItemDelegate, QStyleOptionViewItem, QStyle,
    QDialog, QVBoxLayout, QTextEdit, QPushButton, QApplication, QLabel
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen, QPalette, QIcon

from constants import STATUS_STYLES

# --- UI 颜色常量 ---
COLOR_HIGHLIGHT_BG = QColor("#3a6381")
COLOR_HIGHLIGHT_TEXT = QColor(Qt.white)
ROW_COLOR_BLOCK = QColor("#24282C")
ROW_COLOR_COMMENT = QColor("#3D444A")
COLOR_PASS_TEXT = QColor("#28a745")
COLOR_FAIL_TEXT = QColor("#dc3545")
COLOR_RUNNING_BG = QColor(STATUS_STYLES['RUNNING'][1])
COLOR_PAUSED_BG = QColor(STATUS_STYLES['PAUSED'][1])

# --- 自定义数据角色 ---
STEP_STATUS_ROLE = Qt.UserRole + 1


def show_scrollable_warning(parent, title, message, icon_path=None):
    """
    显示一个可滚动的警告对话框，适用于内容较长的消息。
    确保 OK 按钮始终可见，不会被内容遮挡。
    
    :param parent: 父窗口
    :param title: 对话框标题
    :param message: 消息内容
    :param icon_path: 可选的图标路径
    """
    dialog = QDialog(parent)
    dialog.setWindowTitle(title)
    if icon_path:
        dialog.setWindowIcon(QIcon(icon_path))
    dialog.setMinimumSize(500, 300)
    dialog.setMaximumSize(800, 600)
    
    layout = QVBoxLayout(dialog)
    
    # 警告图标和标题
    title_label = QLabel(f"⚠️ {title}")
    title_label.setStyleSheet("font-size: 16pt; font-weight: bold; color: #f0ad4e;")
    layout.addWidget(title_label)
    
    # 可滚动的文本区域
    text_edit = QTextEdit()
    text_edit.setPlainText(message)
    text_edit.setReadOnly(True)
    text_edit.setStyleSheet("font-size: 12pt;")
    layout.addWidget(text_edit)
    
    # OK 按钮
    ok_button = QPushButton("确定")
    ok_button.setMinimumHeight(40)
    ok_button.setStyleSheet("font-size: 14pt;")
    ok_button.clicked.connect(dialog.accept)
    ok_button.setDefault(True)
    layout.addWidget(ok_button)
    
    # 调整对话框大小以适应内容，但不超过屏幕大小
    dialog.adjustSize()
    
    # 居中显示
    # 居中显示在屏幕中间
    screen = QApplication.primaryScreen()
    if screen:
        screen_geo = screen.availableGeometry()
        dialog.move(
            screen_geo.x() + (screen_geo.width() - dialog.width()) // 2,
            screen_geo.y() + (screen_geo.height() - dialog.height()) // 2
        )
    elif parent:
        parent_geo = parent.geometry()
        dialog.move(
            parent_geo.x() + (parent_geo.width() - dialog.width()) // 2,
            parent_geo.y() + (parent_geo.height() - dialog.height()) // 2
        )
    
    dialog.exec()


class RowColorDelegate(QStyledItemDelegate):
    """
    一个用于QTableWidget的委托，根据单元格的数据和状态来自定义行背景色和文本颜色。
    - 高亮显示选中行。
    - 根据测试步骤的运行状态（RUNNING, PAUSED）显示特定背景色。
    - 区分显示区块（block）和注释（comment）行。
    - 根据测试结果（PASS, FAIL）显示特定文本颜色。
    """
    def paint(self, painter, option, index):
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)

        painter.save()

        step_status = index.data(STEP_STATUS_ROLE)
        row_type = index.data(Qt.UserRole)

        # 1. 决定背景色
        if opt.state & QStyle.State_Selected:
            painter.fillRect(opt.rect, COLOR_HIGHLIGHT_BG)
        elif step_status == 'RUNNING':
            painter.fillRect(opt.rect, COLOR_RUNNING_BG)
        elif step_status == 'PAUSED':
            painter.fillRect(opt.rect, COLOR_PAUSED_BG)
        elif row_type == 'block':
            painter.fillRect(opt.rect, ROW_COLOR_BLOCK)
        elif row_type == 'comment':
            painter.fillRect(opt.rect, ROW_COLOR_COMMENT)
        else:
            # 默认背景
            painter.fillRect(opt.rect, opt.palette.color(QPalette.Base))

        # 2. 决定文本颜色
        text_color = opt.palette.color(QPalette.Text)
        if opt.state & QStyle.State_Selected:
            text_color = COLOR_HIGHLIGHT_TEXT
        elif step_status == 'PASS':
            text_color = COLOR_PASS_TEXT
        elif step_status == 'FAIL':
            text_color = COLOR_FAIL_TEXT
        elif row_type == 'block':
            text_color = QColor("#DDDDDD")
        elif row_type == 'comment':
            text_color = QColor("#999999")

        painter.setPen(QPen(text_color))

        # 3. 绘制文本
        text = index.data(Qt.DisplayRole)
        if text:
            # Ensure the custom font set on the item is used
            painter.setFont(opt.font)
            
            alignment = index.data(Qt.TextAlignmentRole)
            if not alignment:
                alignment = Qt.AlignLeft | Qt.AlignVCenter
            # 增加一些内边距
            text_rect = opt.rect.adjusted(5, 0, -5, 0)
            
            # 必须包含 Qt.TextWordWrap 才能支持自动换行
            draw_flags = alignment | Qt.TextWordWrap
            painter.drawText(text_rect, draw_flags, text)

        painter.restore()
