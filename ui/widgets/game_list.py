"""游戏/卡池列表组件 - 双击选择 + 长按拖动

本模块提供了用于游戏管理和卡池管理的自定义列表控件，主要包含三个类：

1. CheckListDelegate：列表项委托，绘制"复选框 + 文字"风格的列表项。
   - 左侧绘制一个可点击切换的复选框（圆角矩形 + 对勾标记）
   - 右侧绘制对应的文本标签
   - 通过 Qt 的 Model/View 架构，将绘制逻辑与数据模型分离

2. GameListDelegate：列表项委托，绘制"卡片式游戏按钮"风格的列表项。
   - 选中状态：浅蓝色背景 + 蓝色边框 + 加粗文字
   - 未选中状态：白色背景 + 灰色边框 + 普通文字
   - 通过圆角矩形模拟按钮外观

3. GameListWidget：自定义的 QListWidget，支持点击复选框区域切换可见性，
   以及长按拖动排序。
   - 重写 mousePressEvent 来区分"点击复选框"和"拖动排序"两种操作
   - 复选框区域（左侧 14~30px）点击时切换复选框状态
   - 其余区域的点击/拖动行为由 QListWidget 基类处理（InternalMove 模式）

技术架构：
- 使用 Qt 的 Model/View 框架：QListWidget 内部维护一个 QStandardItemModel
- QStyledItemDelegate 负责列表项的自定义绘制，替代默认的绘制方式
- 数据通过 Qt.ItemDataRole.UserRole 系列角色（UserRole + 0, +1）存储在每个列表项中
  - UserRole + 0：存储游戏 ID 字符串（如 "genshin"、"star_rail"）
  - UserRole + 1：存储可见性状态（bool），控制该游戏是否在导航栏中显示
"""

# =============================================================================
# 导入部分
# =============================================================================

# QListWidget：Qt 内置的列表控件，内部维护一个模型（QStandardItemModel），
# 提供添加、删除、拖拽、排序等列表操作功能
# QStyledItemDelegate：Qt 的列表项委托基类，允许开发者完全自定义列表项的绘制和交互
from PySide6.QtWidgets import QListWidget, QStyledItemDelegate

# Qt：核心枚举（鼠标按钮、键盘修饰键、角色数据等）
# QRectF：浮点精度的矩形类，用于精确的绘图区域计算
# QSize：尺寸类（整数精度），用于 sizeHint 返回建议尺寸
from PySide6.QtCore import Qt, QRectF, QSize

# QPainter：2D 绘图引擎
# QColor：颜色表示类
# QPen：画笔（控制线条外观）
# QPainterPath：矢量路径（用于绘制对勾等自定义形状）
from PySide6.QtGui import QPainter, QColor, QPen, QPainterPath


# =============================================================================
# CheckListDelegate 类定义
# =============================================================================

class CheckListDelegate(QStyledItemDelegate):
    """列表代理 - 左侧复选框 + 文字。

    用于游戏管理对话框（_show_game_manager）中的列表项绘制。
    每个列表项的布局：
        [  复选框(16x16)  ]  [  文字标签  ]

    继承说明：
    - 继承自 QStyledItemDelegate（而非 QItemDelegate），
      后者在使用 Qt 样式代理（QStyle）时表现更好，且对现代 Qt 主题支持更佳
    - 必须重写 paint() 和 sizeHint() 方法来自定义绘制和尺寸计算

    Qt Model/View 交互机制：
    - 当 QListWidget 需要绘制某个列表项时，会调用 delegate 的 paint() 方法
    - paint() 通过 index 参数访问底层模型数据（QStandardItemModel）
    - index.data(role) 从模型中获取指定角色的数据：
      - Qt.ItemDataRole.DisplayRole（默认）：显示文本
      - Qt.ItemDataRole.UserRole + 1：自定义角色，存储可见性状态（bool）
    """

    # ---------------------------------------------------------------------------
    # 类级别常量 - 复选框方块的外观参数
    # ---------------------------------------------------------------------------
    _BOX = 16    # 复选框方块的边长（像素）
    _RADIUS = 3  # 圆角半径（像素）

    # ---------------------------------------------------------------------------
    # paint 方法 - 自定义绘制列表项
    # ---------------------------------------------------------------------------

    def paint(self, painter: QPainter, option, index):
        """自定义绘制一个列表项。

        参数说明：
            painter (QPainter): Qt 传入的绘图引擎，已绑定到列表的 viewport（视口）
            option (QStyleOptionViewItem): 包含列表项的样式选项：
                - option.rect：列表项在 viewport 中的矩形区域（QRect，整数精度）
                - option.font：当前使用的字体
                - option.state：列表项的状态标志（是否选中、是否激活等）
            index (QModelIndex): 模型索引，用于从底层数据模型中获取数据：
                - index.data(role)：获取指定角色的数据
                - index.row()：获取行号
                - index.column()：获取列号

        绘制流程：
        1. 保存 painter 状态（save/restore 配对使用）
        2. 绘制白色背景（覆盖 Qt 默认的选中高亮）
        3. 计算并绘制复选框区域（垂直居中）
        4. 如果选中，绘制白色对勾
        5. 在复选框右侧绘制文字标签
        6. 恢复 painter 状态

        注意：painter.save() 和 painter.restore() 配对使用，
        确保绘制操作不会影响到其他列表项的绘制。
        save() 保存当前的变换矩阵、画笔、画刷等状态，
        restore() 恢复到 save() 时的状态。
        """
        painter.save()  # 保存 painter 的当前状态（变换矩阵、画笔、画刷等）
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)  # 启用抗锯齿

        # 从模型索引获取可见性状态（UserRole + 1 存储的布尔值）
        # 这个值决定了复选框是选中还是未选中状态
        selected = index.data(Qt.ItemDataRole.UserRole + 1)

        # 将 option.rect（QRect 整数精度）转换为 QRectF（浮点精度）
        # 这样可以进行更精确的亚像素级绘图
        rect = QRectF(option.rect)

        # =========================================================================
        # 第一阶段：绘制白色背景
        # =========================================================================
        # 先用白色填充整个列表项区域，覆盖 Qt 默认的选中高亮效果
        # NoPen 表示不绘制边框（只填充背景色）
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor("#ffffff"))
        painter.drawRect(rect)  # 填充整个列表项矩形区域

        # =========================================================================
        # 第二阶段：绘制复选框方块（垂直居中）
        # =========================================================================
        box_size = self._BOX  # 复选框方块边长 = 16 像素

        # 复选框的水平位置：距列表项左边缘 14px
        box_x = rect.left() + 14

        # 复选框的垂直位置：在列表项中垂直居中
        # rect.center().y() 返回列表项中心的 y 坐标
        # 减去 box_size / 2.0 使方块顶部对齐到正确位置
        box_y = rect.center().y() - box_size / 2.0

        # 创建复选框的浮点矩形（用于后续绘制）
        box = QRectF(box_x, box_y, box_size, box_size)

        # 根据选中状态设置画刷和画笔
        if selected:
            # 选中：蓝色背景 + 蓝色边框（#1a73e8 = Google Material Blue）
            painter.setBrush(QColor("#1a73e8"))
            painter.setPen(QPen(QColor("#1a73e8"), 1.5))
        else:
            # 未选中：白色背景 + 浅灰色边框
            painter.setBrush(QColor("#ffffff"))
            painter.setPen(QPen(QColor("#bbbbbb"), 1.5))

        # 绘制圆角矩形复选框
        # drawRoundedRect(rect, xRadius, yRadius)
        painter.drawRoundedRect(box, self._RADIUS, self._RADIUS)

        # =========================================================================
        # 第三阶段：绘制勾选标记（✓）- 仅在选中状态时绘制
        # =========================================================================
        if selected:
            # 创建白色画笔，用于绘制对勾
            # QPen(color, width, style, cap, join) 的各参数含义：
            #   color="white"：白色线条，与蓝色背景形成高对比度
            #   width=2.2：线条宽度 2.2 像素，确保在 16x16 的方块内清晰可见
            #   style=SolidLine：实线（不使用虚线）
            #   cap=RoundCap：线段端点为圆形（使对勾起止点更圆润自然）
            #   join=RoundJoin：线段连接处为圆形（使对勾转折点更平滑）
            pen = QPen(
                QColor("white"),         # 线条颜色
                2.2,                     # 线条宽度
                Qt.PenStyle.SolidLine,   # 实线样式
                Qt.PenCapStyle.RoundCap, # 圆形线端
                Qt.PenJoinStyle.RoundJoin # 圆形线连接
            )
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)  # 不填充路径内部（只绘制轮廓）

            # 创建 QPainterPath 定义对勾的三段直线路径
            path = QPainterPath()

            # 对勾第一笔：从左中偏下到下方中间（长笔画的下半段）
            # (box_x + 3, box_y + box_size/2)：方块内左侧中偏下
            path.moveTo(box_x + 3, box_y + box_size / 2.0)

            # 转折点：下方中间偏右
            # (box_x + 6.5, box_y + box_size - 3)：方块内下方
            path.lineTo(box_x + 6.5, box_y + box_size - 3)

            # 对勾第二笔：从转折点到右上角（短笔画）
            # (box_x + box_size - 3, box_y + 3)：方块内右上方
            path.lineTo(box_x + box_size - 3, box_y + 3)

            # 绘制对勾路径
            painter.drawPath(path)

        # =========================================================================
        # 第四阶段：绘制文字标签
        # =========================================================================

        # 设置文本颜色为深灰色 #333333（与白色背景形成良好对比）
        painter.setPen(QColor("#333333"))

        # 使用列表项的字体（option.font 包含当前列表项应使用的字体信息）
        painter.setFont(option.font)

        # 计算文本绘制区域的起始 x 坐标
        # box_x + box_size + 10 = 复选框右边缘 + 10px 间距
        text_x = box_x + box_size + 10

        # 创建文本绘制区域的浮点矩形
        # 宽度 = 列表项总宽度 - 文本起始x - 右边距8px
        text_rect = QRectF(
            text_x,                     # 左边界
            rect.top(),                 # 上边界
            rect.width() - text_x - 8, # 宽度（留出右边距）
            rect.height()               # 高度
        )

        # 绘制文本
        # AlignVCenter：垂直居中对齐
        # index.data() 获取 DisplayRole 的数据（即 QListWidgetItem 的文本）
        # 或运算符 "or" 提供空字符串的后备值，防止 None 被传入
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter,
            index.data() or ""  # 获取列表项的显示文本，如果为 None 则使用空字符串
        )

        # 恢复 painter 到 save() 时的状态，确保不影响其他列表项的绘制
        painter.restore()

    # ---------------------------------------------------------------------------
    # sizeHint 方法 - 返回列表项的建议尺寸
    # ---------------------------------------------------------------------------

    def sizeHint(self, option, index):
        """返回列表项的建议尺寸。

        参数说明：
            option (QStyleOptionViewItem): 样式选项（包含字体、状态等）
            index (QModelIndex): 模型索引

        返回值：
            QSize(200, 38)：宽度 200px，高度 38px
            - 宽度 200：足以显示大部分游戏名称
            - 高度 38：为复选框(16px) + 上下间距提供足够空间

        注意：QListWidget 在布局时会调用此方法确定每个列表项的尺寸。
        """
        return QSize(200, 38)


# =============================================================================
# GameListDelegate 类定义
# =============================================================================

class GameListDelegate(QStyledItemDelegate):
    """列表代理 - 模拟游戏按钮风格：圆角卡片 + 蓝色边框选中。

    用于主窗口左侧导航栏的游戏列表绘制。
    选中状态：浅蓝色背景（#d2e3fc）+ 蓝色边框（#1a73e8, 2px）+ 加粗文字
    未选中状态：白色背景（#ffffff）+ 灰色边框（#e0e0e0, 1.5px）+ 普通文字

    与 CheckListDelegate 的区别：
    - CheckListDelegate：复选框 + 文字（用于游戏管理对话框的多选列表）
    - GameListDelegate：卡片式按钮风格（用于导航栏的单选游戏切换列表）
    """

    # ---------------------------------------------------------------------------
    # paint 方法 - 自定义绘制列表项
    # ---------------------------------------------------------------------------

    def paint(self, painter: QPainter, option, index):
        """自定义绘制游戏列表项，模拟按钮卡片风格。

        参数说明：
            painter (QPainter): 绘图引擎
            option (QStyleOptionViewItem): 列表项样式选项
            index (QModelIndex): 模型索引

        绘制流程：
        1. 保存 painter 状态
        2. 启用抗锯齿
        3. 根据选中状态设置背景色、边框色、文字颜色
        4. 绘制圆角矩形卡片
        5. 绘制文字标签（选中时加粗）
        6. 恢复 painter 状态
        """
        painter.save()  # 保存绘图状态
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)  # 启用抗锯齿

        # 从模型数据获取选中状态（UserRole + 1）
        selected = index.data(Qt.ItemDataRole.UserRole + 1)

        # 创建列表项的浮点矩形，并向内收缩：
        # adjusted(6, 3, -6, -3) 表示：
        #   左边界 +6px，上边界 +3px，右边界 -6px，下边界 -3px
        # 这样在卡片之间留出了间距，形成分隔效果
        rect = QRectF(option.rect).adjusted(6, 3, -6, -3)

        if selected:
            # =========================================
            # 选中状态：蓝色主题
            # =========================================
            painter.setBrush(QColor("#d2e3fc"))  # 浅蓝色背景填充
            painter.setPen(QPen(QColor("#1a73e8"), 2))  # 蓝色边框，2px 宽
            text_color = QColor("#1a56b0")  # 深蓝色文字
        else:
            # =========================================
            # 未选中状态：灰色主题
            # =========================================
            painter.setBrush(QColor("#ffffff"))  # 白色背景填充
            painter.setPen(QPen(QColor("#e0e0e0"), 1.5))  # 浅灰色边框，1.5px 宽
            text_color = QColor("#333333")  # 深灰色文字

        # 绘制圆角矩形卡片
        # 圆角半径 10px，使卡片呈现圆润的现代 UI 风格
        painter.drawRoundedRect(rect, 10, 10)

        # =========================================================================
        # 绘制文字标签
        # =========================================================================

        # 创建文字绘制区域，左右各内缩 14px（为圆角留出空间）
        text_rect = rect.adjusted(14, 0, -14, 0)

        # 设置文字颜色
        painter.setPen(text_color)

        # 设置字体（option.font 包含当前项的字体信息）
        painter.setFont(option.font)

        # 选中状态时将文字加粗，增强视觉反馈
        if selected:
            # 注意：不能直接修改 option.font（它是 const 引用）
            # 需要创建一个字体副本并修改
            font = option.font     # 创建字体副本
            font.setBold(True)     # 设置为加粗
            painter.setFont(font)  # 将加粗字体应用到 painter

        # 绘制文字，垂直居中对齐
        # index.data() 获取 DisplayRole 的文本数据
        painter.drawText(
            text_rect,
            Qt.AlignmentFlag.AlignVCenter,
            index.data()
        )

        painter.restore()  # 恢复绘图状态

    # ---------------------------------------------------------------------------
    # sizeHint 方法 - 返回列表项的建议尺寸
    # ---------------------------------------------------------------------------

    def sizeHint(self, option, index):
        """返回列表项的建议尺寸。

        高度取父类建议高度和 46px 中的较大值，
        确保卡片有足够的垂直空间呈现按钮外观。
        宽度继承父类的默认值。

        参数说明：
            option (QStyleOptionViewItem): 样式选项
            index (QModelIndex): 模型索引

        返回值：
            QSize：建议尺寸，高度 >= 46px
        """
        hint = super().sizeHint(option, index)  # 获取父类的默认建议尺寸
        hint.setHeight(max(hint.height(), 46))  # 高度至少 46px
        return hint


# =============================================================================
# GameListWidget 类定义
# =============================================================================

class GameListWidget(QListWidget):
    """自定义列表控件 - 点击复选框区域切换，其余区域正常拖动。

    通过重写 mousePressEvent 来实现区域化的点击行为：
    - 复选框区域（x ∈ [14, 30]）：切换复选框状态，不启动拖动
    - 其余区域：正常的 QListWidget 行为（可触发拖动排序）

    这种设计巧妙地解决了同一个列表需要同时支持"点击切换"和"拖拽排序"的需求。

    Qt 鼠标事件传递机制：
    - 当用户按下鼠标时，Qt 事件循环调用 mousePressEvent
    - 如果不调用 super().mousePressEvent()，事件不会传递到基类，
      基类的默认行为（如启动拖动）不会被触发
    - 通过条件性地调用 super()，可以选择性地阻止某些行为

    数据结构说明：
    - 每个 QListWidgetItem 通过 setData() 存储两个自定义数据：
      - UserRole + 0：游戏 ID（如 "genshin"）
      - UserRole + 1：可见性状态（bool）
    - 这些数据通过 index.data(role) 在 delegate 的 paint() 方法中读取
    """

    # ---------------------------------------------------------------------------
    # 类级别常量 - 定义复选框的可点击区域
    # ---------------------------------------------------------------------------
    _BOX_LEFT = 14          # 复选框左边距（像素），复选框区域的左边界
    _BOX_RIGHT = 14 + 16    # 复选框右边距（像素），复选框区域的右边界
                            # _BOX_LEFT + 复选框宽度(16) = 30
                            # 即 x ∈ [14, 30] 的区域被识别为复选框点击区域

    # ---------------------------------------------------------------------------
    # mousePressEvent 方法 - 重写鼠标按下事件
    # ---------------------------------------------------------------------------

    def mousePressEvent(self, event):
        """处理鼠标按下事件。

        参数说明：
            event (QMouseEvent): Qt 传入的鼠标事件对象，包含：
                - event.button()：按下的鼠标按键（左键、右键、中键等）
                - event.pos()：鼠标按下时在控件内的坐标（QPoint）
                - event.x() / event.y()：坐标的 x/y 分量（已弃用，推荐 pos()）

        处理逻辑：
        1. 仅处理左键点击（event.button() == LeftButton）
        2. 获取点击位置下方的列表项（self.itemAt(pos)）
        3. 判断点击位置是否在复选框区域内（x ∈ [14, 30]）
        4. 如果在复选框区域内：切换可见性状态并重绘，然后 return（不调用 super）
        5. 如果不在复选框区域内：调用 super().mousePressEvent() 处理默认行为
           （包括列表项选中、拖动排序启动等）

        itemAt(pos) 方法说明：
        - 返回 pos 坐标下方的 QListWidgetItem，如果没有任何项则返回 None
        - 坐标是相对于控件 viewport 的，而非全局坐标

        item.data(role) 方法说明：
        - 从列表项获取指定角色的数据
        - Qt.ItemDataRole.UserRole + 1 是自定义角色，存储可见性状态
        - 返回值取决于之前 setData() 时存储的数据类型（此处为 bool）

        item.setData(role, value) 方法说明：
        - 向列表项存储指定角色的数据
        - UserRole 是自定义角色的起始编号（从 256 开始）
        - UserRole + 1 表示第二个自定义数据槽位

        viewport().update() 方法说明：
        - 触发列表视口的重绘，这会调用所有可见列表项的 delegate.paint()
        - 与 repaint() 不同，update() 是异步的，会合并多次更新请求
        """
        # 仅处理鼠标左键点击（不处理右键、中键等）
        if event.button() == Qt.MouseButton.LeftButton:

            # 获取鼠标点击位置下方的列表项
            # itemAt() 返回 QListWidgetItem 或 None
            item = self.itemAt(event.pos())

            if item:
                # 获取鼠标点击的 x 坐标
                x = event.pos().x()

                # 判断点击是否在复选框区域内（x ∈ [14, 30]）
                if self._BOX_LEFT <= x <= self._BOX_RIGHT:
                    # 从列表项的 UserRole + 1 获取当前可见性状态
                    selected = item.data(Qt.ItemDataRole.UserRole + 1)

                    # 切换可见性状态（布尔取反）
                    item.setData(Qt.ItemDataRole.UserRole + 1, not selected)

                    # 触发列表视口重绘，使 delegate 重新绘制所有可见项
                    # 这样复选框的选中/未选中状态会被立即更新到视觉上
                    self.viewport().update()

                    # 直接返回，不调用 super().mousePressEvent()
                    # 这样可以阻止 QListWidget 基类启动拖动操作
                    # 因为在复选框区域的点击应该是"切换"而非"拖动"
                    return  # 不调用 super，阻止拖动启动

        # 如果不是在复选框区域的点击（或者不是左键），
        # 调用 QListWidget 基类的 mousePressEvent 处理默认行为：
        # - 选中被点击的列表项
        # - 可能启动拖动操作（如果启用了 DragDropMode）
        super().mousePressEvent(event)
