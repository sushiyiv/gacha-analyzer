"""自定义复选框 - 带可见勾选标记"""

from PySide6.QtWidgets import QCheckBox
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath


class StyledCheckBox(QCheckBox):
    """自定义复选框，带可见的勾选标记"""

    _SIZE = 18
    _BORDER = 2
    _RADIUS = 3

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setFixedSize(self._SIZE + 8 + self.fontMetrics().horizontalAdvance(text) + 4,
                          self._SIZE + 4)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("QCheckBox { spacing: 8px; }")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # indicator 区域
        size = self._SIZE
        x = 2
        y = (self.height() - size) / 2
        indicator = QRectF(x, y, size, size)

        # 背景
        if self.isChecked():
            painter.setBrush(QColor("#1a73e8"))
            painter.setPen(QPen(QColor("#1a73e8"), self._BORDER))
        else:
            painter.setBrush(QColor("white"))
            painter.setPen(QPen(QColor("#bbbbbb"), self._BORDER))

        painter.drawRoundedRect(indicator, self._RADIUS, self._RADIUS)

        # 勾选标记
        if self.isChecked():
            painter.setPen(QPen(QColor("white"), 2.2, Qt.PenStyle.SolidLine,
                                Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            path = QPainterPath()
            path.moveTo(x + 3.5, y + size / 2)
            path.lineTo(x + 7, y + size - 4)
            path.lineTo(x + size - 3.5, y + 4)
            painter.drawPath(path)

        # 文字
        painter.setPen(QColor("#333333"))
        painter.setFont(self.font())
        text_x = x + size + 8
        painter.drawText(text_x, 0, self.width() - text_x, self.height(),
                         Qt.AlignmentFlag.AlignVCenter, self.text())
        painter.end()
