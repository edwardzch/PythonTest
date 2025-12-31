# -*- coding: utf-8 -*-
"""
通用UI组件和UI相关常量
"""

from PySide6.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QStyle
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPen, QPalette

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
