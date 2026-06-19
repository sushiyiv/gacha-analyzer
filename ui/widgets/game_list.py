"""游戏/卡池列表组件 - 双击选择 + 长按拖动"""

from PySide6.QtWidgets import QListWidget, QStyledItemDelegate
from PySide6.QtCore import Qt, QRectF, QSize
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath


class CheckListDelegate(QStyledItemDelegate):
    """列表代理 - 左侧复选框 + 文字"""

    _BOX = 16
    _RADIUS = 3

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        selected = index.data(Qt.ItemDataRole.UserRole + 1)
        rect = QRectF(option.rect).adjusted(4, 3, -4, -3)

        # 整行背景 + 圆角边框
        painter.setPen(QPen(QColor("#dadce0"), 1.5))
        painter.setBrush(QColor("#ffffff"))
        painter.drawRoundedRect(rect, 10, 10)

        # 复选框（垂直居中）
        box_size = self._BOX
        box_x = rect.left() + 14
        box_y = rect.center().y() - box_size / 2.0
        box = QRectF(box_x, box_y, box_size, box_size)

        if selected:
            painter.setBrush(QColor("#1a73e8"))
            painter.setPen(QPen(QColor("#1a73e8"), 1.5))
        else:
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(QColor("#bbbbbb"), 1.5))
        painter.drawRoundedRect(box, self._RADIUS, self._RADIUS)

        # 勾选标记 ✓
        if selected:
            pen = QPen(QColor("white"), 2.2, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            path = QPainterPath()
            path.moveTo(box_x + 3, box_y + box_size / 2.0)
            path.lineTo(box_x + 6.5, box_y + box_size - 3)
            path.lineTo(box_x + box_size - 3, box_y + 3)
            painter.drawPath(path)

        # 文字
        painter.setPen(QColor("#333333"))
        painter.setFont(option.font)
        text_x = box_x + box_size + 10
        text_rect = QRectF(text_x, rect.top(),
                           rect.width() - text_x - 8, rect.height())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter, index.data() or "")

        painter.restore()

    def sizeHint(self, option, index):
        return QSize(200, 38)


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
    """列表 - 点击复选框区域切换，其余区域正常拖动"""

    _BOX_LEFT = 14          # 复选框左边距
    _BOX_RIGHT = 14 + 16    # 复选框左边距 + 复选框宽度

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.pos())
            if item:
                # 判断点击是否在复选框区域内
                x = event.pos().x()
                if self._BOX_LEFT <= x <= self._BOX_RIGHT:
                    selected = item.data(Qt.ItemDataRole.UserRole + 1)
                    item.setData(Qt.ItemDataRole.UserRole + 1, not selected)
                    self.viewport().update()
                    return  # 不调用 super，阻止拖动启动
        super().mousePressEvent(event)
