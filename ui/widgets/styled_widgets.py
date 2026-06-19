"""自定义复选框 - 带可见勾选标记

本模块定义了 StyledCheckBox 类，一个完全自绘的复选框控件。
与 Qt 内置的 QCheckBox 不同，它通过重写 paintEvent 实现完全自定义绘制，
确保在不同操作系统和主题下都能获得一致的视觉效果。

技术要点：
- 继承自 QCheckBox，复用其三态（checked/unchecked/partiallyChecked）逻辑
- 通过 QPainterPath 绘制勾选标记（✓），使用抗锯齿渲染
- 使用 setFixedSize 固定控件尺寸，确保布局稳定
- 鼠标悬停时显示手型光标（PointingHandCursor）
"""

# =============================================================================
# 导入部分
# =============================================================================

# QCheckBox：Qt 内置的复选框控件，提供三态切换和信号（stateChanged、clicked 等）
from PySide6.QtWidgets import QCheckBox

# Qt：Qt 核心枚举类型集合，包含对齐方式、光标形状、键盘修饰键等
# QRectF：浮点精度的矩形类，用于精确的绘图区域计算
from PySide6.QtCore import Qt, QRectF

# QPainter：Qt 2D 绘图引擎，提供在 widget 表面绘制图形的能力
# QColor：颜色类，支持 RGB/RGBA/HSL 等多种颜色表示
# QPen：画笔类，控制线条的颜色、宽度、样式等
# QPainterPath：矢量路径类，可定义任意形状的绘制路径（直线、曲线等）
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath


# =============================================================================
# StyledCheckBox 类定义
# =============================================================================

class StyledCheckBox(QCheckBox):
    """自定义复选框，带可见的勾选标记。

    继承自 QCheckBox，通过重写 paintEvent 实现完全自定义绘制。
    选中时绘制蓝色圆角矩形 + 白色对勾，未选中时绘制灰色边框的白色矩形。

    内部状态说明：
    - self.isChecked()：继承自 QCheckBox 的方法，返回当前复选框的选中状态（bool）
    - self.text()：继承自 QCheckBox 的方法，返回关联的文本字符串
    - self.font()：继承自 QWidget 的方法，返回当前控件使用的 QFont 字体对象
    - self.fontMetrics()：继承自 QWidget 的方法，返回 QFontMetrics 对象，
      用于测量文本的像素宽度、高度等信息
    - self.width() / self.height()：继承自 QWidget，返回当前控件的实际像素尺寸

    Qt Widget 生命周期：
    - __init__：创建控件实例，设置初始属性（尺寸、光标、样式）
    - paintEvent：每次控件需要重绘时被 Qt 框架自动调用（如窗口遮挡后恢复、
      切换窗口、调用 update() 等场景）
    - 用户点击时，QCheckBox 基类自动处理状态切换并触发 paintEvent 重绘
    """

    # ---------------------------------------------------------------------------
    # 类级别常量 - 定义复选框方块的外观参数
    # ---------------------------------------------------------------------------
    _SIZE = 18    # 复选框方块的边长（像素），即勾选区域是一个 18x18 的正方形
    _BORDER = 2   # 复选框方块边框的线条宽度（像素），较粗的边框确保视觉清晰
    _RADIUS = 3   # 圆角半径（像素），为方块的四个角提供微小的圆角效果

    # ---------------------------------------------------------------------------
    # 构造方法
    # ---------------------------------------------------------------------------

    def __init__(self, text="", parent=None):
        """初始化自定义复选框。

        参数说明：
            text (str): 复选框旁边的显示文本，默认为空字符串
            parent (QWidget | None): 父级 Qt 控件，由 Qt 对象树管理生命周期。
                当 parent 被销毁时，该控件也会被自动销毁（避免内存泄漏）。
                传 None 表示该控件为顶层控件。

        内部工作原理：
        1. 调用 QCheckBox.__init__ 完成基类初始化，建立 Qt 对象树关系
        2. 使用 fontMetrics().horizontalAdvance(text) 精确计算文本像素宽度
           - fontMetrics() 返回当前字体的度量信息
           - horizontalAdvance(text) 返回文本在当前字体下占用的水平像素数
           - 这比 QFontMetrics.boundingRect() 更高效，适合单行文本宽度测量
        3. 固定控件尺寸为：宽度 = 方块(18) + 间距(8) + 文本宽度 + 右边距(4)
                              高度 = 方块(18) + 上下边距(2*2)
        4. 设置光标为手型，提升可交互性的视觉反馈
        5. 通过 setStyleSheet 设置 QCheckBox 的 spacing 属性为 8px
           （此属性影响内置 indicator 与文字的间距，但在自绘模式下不直接使用）
        """
        super().__init__(text, parent)  # 调用 QCheckBox 的构造函数，传入文本和父控件

        # 计算并设置固定尺寸：
        # _SIZE(18) = 复选框方块边长
        # 8 = 方块与文字之间的间距
        # horizontalAdvance(text) = 文本在当前字体下的像素宽度
        # 4 = 文字右侧的额外边距
        # _SIZE + 4 = 方块上下各 2px 的边距
        self.setFixedSize(
            self._SIZE + 8 + self.fontMetrics().horizontalAdvance(text) + 4,
            self._SIZE + 4
        )

        # 设置鼠标光标为手型（指向手），这是可点击控件的标准交互提示
        self.setCursor(Qt.CursorShape.PointingHandCursor)

        # 通过样式表设置 QCheckBox 内部 spacing 属性为 8px
        # 注意：在自绘模式下，这个 spacing 主要用于 accessibility（辅助功能）
        # 实际的文字位置由 paintEvent 中的代码控制
        self.setStyleSheet("QCheckBox { spacing: 8px; }")

    # ---------------------------------------------------------------------------
    # 绘图事件重写
    # ---------------------------------------------------------------------------

    def paintEvent(self, event):
        """重写 QCheckBox 的绘制事件，实现完全自定义的视觉外观。

        参数说明：
            event (QPaintEvent): Qt 框架传入的绘制事件对象。
                - event.rect() 返回需要重绘的矩形区域（脏区域）
                - Qt 通常只会重绘需要更新的区域，但在此实现中我们绘制整个控件

        绘制流程（三个阶段）：
        1. 绘制背景方块（圆角矩形），颜色根据选中状态变化
        2. 如果处于选中状态，绘制白色对勾（✓）路径
        3. 在方块右侧绘制关联文本

        QPainter 绑定生命周期：
        - QPainter(self)：构造时自动绑定到当前 widget 的绘图设备
        - painter.end()：显式释放绘图设备的绑定
        - 使用 painter.save() / painter.restore() 也可以保存/恢复绘图状态，
          但此处选择手动 end()，效果等价

        Qt Widget 绘制机制：
        - paintEvent 在 Qt 事件循环中被调度，通常在窗口首次显示、
          从最小化恢复、窗口大小改变、调用 update()/repaint() 时触发
        - QPainter 只能在 paintEvent 内部使用（否则未定义行为）
        """
        # 创建 QPainter 实例并绑定到当前控件的绘图设备
        painter = QPainter(self)

        # 启用抗锯齿渲染（Antiialiasing），
        # 使圆角矩形和对勾路径的边缘更平滑，减少锯齿感
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # =========================================================================
        # 第一阶段：绘制复选框方块（背景）
        # =========================================================================

        # 复选框方块的边长（像素）
        size = self._SIZE

        # x 坐标：方块左边距为 2px，紧贴控件左边缘
        x = 2

        # y 坐标：垂直居中计算
        # (self.height() - size) / 2 得到方块顶部的 y 坐标
        # 例如控件高度 22px，方块 18px，则 y = 2，上下各留 2px
        y = (self.height() - size) / 2

        # 创建浮点精度的矩形 QRectF，用于精确绘图
        # QRectF(x, y, width, height) - 这里宽高均为 size（正方形）
        indicator = QRectF(x, y, size, size)

        # 根据选中状态设置画刷（填充色）和画笔（边框色）
        if self.isChecked():
            # 选中状态：蓝色背景 + 蓝色边框
            # #1a73e8 是 Google Material Design 的蓝色主色调
            painter.setBrush(QColor("#1a73e8"))
            painter.setPen(QPen(QColor("#1a73e8"), self._BORDER))
        else:
            # 未选中状态：白色背景 + 浅灰色边框
            # #bbbbbb 是中灰色，表示非激活状态
            painter.setBrush(QColor("white"))
            painter.setPen(QPen(QColor("#bbbbbb"), self._BORDER))

        # 绘制圆角矩形
        # drawRoundedRect(rect, xRadius, yRadius)
        # _RADIUS = 3 表示水平和垂直方向的圆角半径均为 3px
        painter.drawRoundedRect(indicator, self._RADIUS, self._RADIUS)

        # =========================================================================
        # 第二阶段：绘制勾选标记（✓）
        # =========================================================================

        if self.isChecked():
            # 创建白色画笔，用于绘制对勾
            # QPen(color, width, style, cap, join) 参数说明：
            #   - QColor("white")：白色线条
            #   - 2.2：线条宽度 2.2 像素，略粗以确保可见性
            #   - SolidLine：实线样式
            #   - RoundCap：线端点为圆形（更自然的视觉效果）
            #   - RoundJoin：线连接处为圆形（避免尖锐转角）
            painter.setPen(QPen(
                QColor("white"),         # 线条颜色：白色（与蓝色背景形成对比）
                2.2,                     # 线条宽度：2.2 像素
                Qt.PenStyle.SolidLine,   # 线条样式：实线
                Qt.PenCapStyle.RoundCap, # 线端点样式：圆形（使对勾末端更圆润）
                Qt.PenJoinStyle.RoundJoin # 线连接样式：圆形（使对勾转角处更平滑）
            ))

            # 创建 QPainterPath 来定义对勾的路径
            # QPainterPath 是一个矢量路径对象，可以添加直线、曲线、弧线等元素
            # 对勾由三段直线组成，形成经典的 "V" 形勾选标记
            path = QPainterPath()

            # 对勾第一笔：从左中到右下（对勾的长笔画）
            # (x + 3.5, y + size/2) = 方块内左中偏下位置（起笔点）
            # (x + 7, y + size - 4) = 方块内下方中间偏右位置（转折点）
            path.moveTo(x + 3.5, y + size / 2)     # 移动到起笔点
            path.lineTo(x + 7, y + size - 4)       # 画线到转折点

            # 对勾第二笔：从转折点到右上（对勾的短笔画）
            # (x + size - 3.5, y + 4) = 方块内右上角位置（收笔点）
            path.lineTo(x + size - 3.5, y + 4)     # 画线到收笔点

            # 使用 QPainter 绘制路径
            painter.drawPath(path)

        # =========================================================================
        # 第三阶段：绘制关联文本
        # =========================================================================

        # 设置文本颜色为深灰色 #333333，与浅色背景形成良好对比
        painter.setPen(QColor("#333333"))

        # 使用控件当前的字体绘制文本
        # self.font() 返回 QFont 对象，包含字体族、大小、粗细等信息
        painter.setFont(self.font())

        # 计算文本的绘制区域
        # text_x = 方块右边 + 间距 8px
        text_x = x + size + 8

        # drawText 的参数说明：
        #   (x, y, width, height, flags, text)
        #   - x, y：文本区域左上角坐标
        #   - width, height：文本区域的宽高
        #   - AlignVCenter：垂直居中对齐
        #   - text：要绘制的文本字符串
        painter.drawText(
            text_x,                    # 文本区域左 x 坐标
            0,                         # 文本区域顶部 y 坐标
            self.width() - text_x,    # 文本区域宽度（控件总宽 - 文本起始 x）
            self.height(),            # 文本区域高度 = 控件高度
            Qt.AlignmentFlag.AlignVCenter,  # 垂直居中对齐标志
            self.text()               # 要绘制的文本（继承自 QCheckBox）
        )

        # 显式结束绘图，释放绑定到绘图设备的 QPainter 资源
        # 这是良好的资源管理实践，虽然析构函数也会自动释放
        painter.end()
