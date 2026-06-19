"""UI 工具函数 - 共享的组件创建和样式辅助"""

from PySide6.QtWidgets import (
    QGroupBox, QLabel, QTableWidget, QHeaderView,
    QPushButton, QFrame, QHBoxLayout
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont


def make_page_title(text: str) -> QLabel:
    """创建页面标题（18px 粗体 Microsoft YaHei）"""
    title = QLabel(text)
    title.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
    return title


def make_section_group(title: str) -> QGroupBox:
    """创建分组框（14px 粗体标题 + 标准边框样式）"""
    group = QGroupBox(title)
    group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
    return group


def make_stat_table(columns: list, min_height: int = 200) -> QTableWidget:
    """创建标准统计表格（无编辑、自动列宽、隐藏行号）

    Args:
        columns: 列标题列表，如 ["指标", "数值", "说明"]
        min_height: 最小高度
    """
    table = QTableWidget()
    table.setColumnCount(len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
    table.verticalHeader().setVisible(False)
    table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
    table.setMinimumHeight(min_height)
    return table


def make_hint_label(text: str, color: str = "#666") -> QLabel:
    """创建提示文字（灰色小字）"""
    label = QLabel(text)
    label.setStyleSheet(f"color: {color};")
    return label


def make_accent_button(text: str, color: str = "#1a73e8",
                       width: int = None, height: int = None) -> QPushButton:
    """创建带自定义颜色的按钮"""
    btn = QPushButton(text)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if width and height:
        btn.setFixedSize(width, height)
    return btn


def make_hseparator() -> QFrame:
    """创建水平分割线"""
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setFrameShadow(QFrame.Shadow.Sunken)
    return line


def make_button_row(*buttons: QPushButton) -> QHBoxLayout:
    """将按钮排列在一行，末尾加 stretch"""
    layout = QHBoxLayout()
    for btn in buttons:
        layout.addWidget(btn)
    layout.addStretch()
    return layout
