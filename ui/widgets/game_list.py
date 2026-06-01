"""游戏/卡池列表组件 - 双击选择 + 长按拖动"""

from PySide6.QtWidgets import QListWidget, QStyledItemDelegate
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen


class GameListDelegate(QStyledItemDelegate):
    """列表代理 - 模拟游戏按钮风格：圆角卡片 + 蓝色边框选中"""

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        selected = index.data(Qt.ItemDataRole.UserRole + 1)
        rect = QRectF(option.rect).adjusted(6, 3, -6, -3)

        if selected:
            # 选中：蓝色边框 + 浅蓝背景
            painter.setBrush(QColor("#d2e3fc"))
            painter.setPen(QPen(QColor("#1a73e8"), 2))
            text_color = QColor("#1a56b0")
        else:
            # 未选中：灰色边框 + 白色背景
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(QColor("#e0e0e0"), 1.5))
            text_color = QColor("#333333")

        painter.drawRoundedRect(rect, 10, 10)

        # 文字
        text_rect = rect.adjusted(14, 0, -14, 0)
        painter.setPen(text_color)
        painter.setFont(option.font)
        if selected:
            font = option.font
            font.setBold(True)
            painter.setFont(font)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, index.data())

        painter.restore()

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        hint.setHeight(max(hint.height(), 46))
        return hint


class GameListWidget(QListWidget):
    """列表 - 双击选择，长按拖动排序"""

    def mouseDoubleClickEvent(self, event):
        item = self.itemAt(event.pos())
        if item:
            selected = item.data(Qt.ItemDataRole.UserRole + 1)
            item.setData(Qt.ItemDataRole.UserRole + 1, not selected)
            self.viewport().update()
        super().mouseDoubleClickEvent(event)
