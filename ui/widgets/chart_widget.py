"""图表展示页面

本模块使用Matplotlib + Qt后端实现抽卡数据的可视化图表，包括：
1. 出货抽数分布直方图 - 展示每次出5星时的抽数分布
2. 保底概率曲线 - 展示逐抽概率的变化趋势
3. 各星级统计柱状图 - 展示各星级物品的数量对比
4. 卡池投入占比饼图 - 展示各卡池的抽数投入比例
5. 月度抽卡趋势 - 展示按月统计的抽卡数量变化
6. 50/50统计饼图 - 展示UP/歪的比例

Matplotlib通过QtAgg后端将图表渲染为Qt原生组件，
可以无缝嵌入PySide6的窗口部件体系中。
"""

# ========== 导入语句 ==========

# 导入PySide6的窗口部件模块
# QWidget: 窗口部件基类
# QVBoxLayout: 垂直布局
# QHBoxLayout: 水平布局
# QLabel: 文本标签
# QFrame: 带边框容器
# QComboBox: 下拉选择框
# QScrollArea: 滚动区域
# QPushButton: 按钮（虽然本文件未直接使用，但保留导入以备扩展）
# QApplication: Qt应用程序实例，用于事件发送
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QComboBox, QScrollArea, QPushButton, QApplication
)

# Qt: 核心模块
# QEvent: Qt事件类，用于事件过滤和处理
from PySide6.QtCore import Qt, QEvent

# QFont: 字体类
from PySide6.QtGui import QFont

# ========== Matplotlib配置 ==========

# 导入matplotlib绘图库
import matplotlib
# 设置matplotlib的后端为QtAgg
# QtAgg是基于Qt的Agg(Antigrain Geometry)渲染器后端
# 它将matplotlib的图形渲染为Qt可以显示的像素数据
matplotlib.use('QtAgg')

# 设置全局字体配置，确保中文正确显示
# font.sans-serif 是无衬线字体的首选列表
# SimHei(黑体)是最常见的中文无衬线字体
# Microsoft YaHei(微软雅黑)是Windows系统的优质中文字体
# DejaVu Sans 是matplotlib默认的英文字体，作为最终兜底
matplotlib.rcParams['font.sans-serif'] = [
    'SimHei', 'Microsoft YaHei', 'DejaVu Sans'
]
# axes.unicode_minus = False 解决负号"-"显示为方块的问题
# 当使用中文字体时，matplotlib可能无法正确渲染Unicode负号
# 设置此选项后会使用matplotlib内置的负号渲染方式
matplotlib.rcParams['axes.unicode_minus'] = False

# FigureCanvasQTAgg: matplotlib的Qt画布类
# 它将matplotlib的Figure渲染为Qt的QWidget，可以嵌入到任何Qt布局中
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
# Figure: matplotlib的图形对象，是所有绑图元素的顶层容器
from matplotlib.figure import Figure

# Database: 数据库操作封装
from core.database import Database

# StatsAnalyzer: 统计分析器，提供各种统计方法
# PityAnalyzer: 保底分析器（本文件未直接使用但保留导入）
# get_rate_at_pull: 获取指定抽数处的基础概率（考虑软保底提升）
from core.analyzer import StatsAnalyzer, PityAnalyzer, get_rate_at_pull

# BANNER_CONFIGS: 卡池保底配置字典
# GAME_COLORS: 游戏主题色配置
# get_max_rarity: 获取游戏最高星级
# get_pool_names: 获取游戏卡池列表
from core.models import BANNER_CONFIGS, GAME_COLORS, get_max_rarity, get_pool_names


class ChartWidget(QWidget):
    """图表展示页面组件

    使用Matplotlib在Qt窗口中渲染各种统计图表。
    支持滚轮事件传递给父级滚动区域，确保在嵌套滚动场景下
    用户可以正常滚动查看所有图表。

    属性:
        main_window: 主窗口引用
        db: Database实例
        pool_combo: 卡池选择下拉框
        _last_game: 上一次刷新时的游戏（用于检测游戏切换）
        scroll_widget: 图表区域的滚动内容widget
        chart_layout: 图表的垂直布局容器
    """

    def __init__(self, main_window):
        """构造函数

        参数:
            main_window: 主窗口实例引用，用于获取当前账号和游戏信息
        """
        # 调用父类QWidget构造函数
        super().__init__()

        # 保存主窗口引用
        self.main_window = main_window

        # 创建数据库实例
        self.db = Database()

        # 初始化UI
        self._init_ui()

    def eventFilter(self, obj, event):
        """事件过滤器：让Matplotlib画布的滚轮事件传递给父级滚动区域

        Qt的事件传播机制：当一个组件接收到事件时，如果它不处理（不消费），
        事件会传递给其父组件。但Matplotlib的FigureCanvas会自己处理滚轮
        事件用于缩放图形，这会阻止事件传递到外层的QScrollArea。

        本方法通过Qt的事件过滤器机制，在滚轮事件到达FigureCanvas之前
        将其转发给最近的QScrollArea，实现正常的滚动体验。

        参数:
            obj (QObject): 接收到事件的对象（这里是某个FigureCanvas）
            event (QEvent): Qt事件对象

        返回:
            bool: True表示事件已被处理（不再继续传递），
                  False表示事件继续正常传递
        """
        # 导入QEvent（虽然文件顶部已导入，这里再次导入确保作用域可用）
        from PySide6.QtCore import QEvent

        # 检查事件类型是否为滚轮事件
        if event.type() == QEvent.Type.Wheel:
            # 从当前组件开始向上遍历组件树，寻找最近的QScrollArea
            widget = self
            while widget:
                # findChild()在当前widget的子组件树中查找指定类型的第一个组件
                # 这种向上查找的方式可以找到嵌套在任意深度的滚动区域
                scroll = widget.findChild(QScrollArea)
                if scroll:
                    # 找到滚动区域后，创建滚轮事件的副本
                    # event.clone()创建事件的深拷贝，避免原事件被修改
                    new_event = event.clone()
                    # QApplication.sendEvent()将事件发送给指定的目标组件
                    # scroll.viewport()是滚动区域的可视区域（实际接收滚轮事件的组件）
                    QApplication.sendEvent(scroll.viewport(), new_event)
                    # 返回True表示事件已处理，FigureCanvas不会再收到这个事件
                    return True
                # 向上一级父组件继续查找
                widget = widget.parent()
            # 没有找到QScrollArea，事件继续正常传递
            return False
        # 非滚轮事件不做特殊处理，调用父类默认实现
        return super().eventFilter(obj, event)

    def _init_ui(self):
        """初始化图表页面的UI布局

        页面结构：
        1. 顶部：标题 + 卡池选择下拉框
        2. 中部：图表滚动区域，包含所有生成的图表

        图表会在refresh()方法中动态生成并添加到chart_layout中。
        """
        # 页面根布局（垂直排列）
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ===== 顶部标题和卡池选择 =====
        header = QHBoxLayout()
        title = QLabel("图表展示")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        header.addWidget(title)
        # 弹性空间将标题推到左侧
        header.addStretch()

        header.addWidget(QLabel("卡池:"))
        # 卡池选择下拉框
        self.pool_combo = QComboBox()
        # 切换卡池时刷新图表
        self.pool_combo.currentIndexChanged.connect(lambda: self.refresh())
        header.addWidget(self.pool_combo)

        # 记录上一次刷新时的游戏，用于检测游戏是否切换
        # 当游戏切换时需要重新填充下拉框选项
        self._last_game = None

        # 将标题栏添加到根布局
        layout.addLayout(header)

        # ===== 图表滚动区域 =====
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        # 图表内容widget（在refresh()中会被动态填充图表）
        self.scroll_widget = QWidget()
        # 图表垂直布局：所有图表从上到下排列
        self.chart_layout = QVBoxLayout(self.scroll_widget)
        # 图表之间的垂直间距为16px
        self.chart_layout.setSpacing(16)

        # 将内容widget设置为滚动区域的内容
        scroll.setWidget(self.scroll_widget)
        # 将滚动区域添加到根布局
        layout.addWidget(scroll)

    def refresh(self):
        """刷新整个图表页面

        这是图表页面的核心刷新方法，在以下情况下被调用：
        1. 用户切换卡池下拉框时
        2. 主窗口调用refresh_all()时
        3. 数据导入后

        方法流程：
        1. 获取当前账号和游戏
        2. 在游戏切换时更新卡池下拉框选项
        3. 加载指定卡池的抽卡记录
        4. 清除旧图表
        5. 依次生成6种图表
        """
        # 获取当前选中的账号
        account = self.main_window.get_current_account()
        if not account:
            return

        game = self.main_window.get_current_game()

        # 检测游戏是否切换
        # 游戏切换时需要重新填充卡池下拉框（不同游戏的卡池不同）
        if game != self._last_game:
            self._last_game = game
            # 屏蔽信号，防止clear/addItem触发不必要的刷新
            self.pool_combo.blockSignals(True)
            # 保存当前选中的pool_type，刷新后尝试恢复
            current = self.pool_combo.currentData()
            self.pool_combo.clear()
            # 添加"全部卡池"默认选项
            self.pool_combo.addItem("全部卡池", None)
            # 获取当前游戏的所有卡池并添加到下拉框
            for pt, name in get_pool_names(game):
                self.pool_combo.addItem(name, pt)
            # 尝试恢复之前选中的卡池
            idx = self.pool_combo.findData(current)
            self.pool_combo.setCurrentIndex(idx if idx >= 0 else 0)
            # 重新启用信号
            self.pool_combo.blockSignals(False)

        # 获取当前选中的卡池类型（None表示全部）
        pool_type = self.pool_combo.currentData()
        # 加载该账号指定卡池的抽卡记录
        records = self.db.get_records(account.id, pool_type)

        # 清除旧图表
        # QLayout.count()返回布局中的子项数量
        while self.chart_layout.count():
            # takeAt(0)取出第一个子项并从布局中移除
            # 返回QLayoutItem对象
            child = self.chart_layout.takeAt(0)
            # 检查子项是否是widget（而不是spacer或嵌套布局）
            if child.widget():
                # deleteLater()请求Qt在事件循环的下一次迭代中删除该组件
                # 不立即删除是因为当前可能正在遍历组件树，立即删除会导致崩溃
                child.widget().deleteLater()

        # 无数据时显示提示信息
        if not records:
            no_data = QLabel("暂无数据，请先导入抽卡记录")
            no_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_data.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
            self.chart_layout.addWidget(no_data)
            return

        # 获取当前游戏的主题色
        colors = GAME_COLORS.get(game, {})
        accent = colors.get("primary", "#1a73e8")

        # 创建统计分析器实例
        stats = StatsAnalyzer(records)

        # ===== 依次生成6种图表 =====

        # 1. 出货抽数分布直方图：展示每次出5星时的抽数分布情况
        self._add_pull_distribution_chart(records, accent)

        # 2. 保底概率曲线：展示从当前位置到硬保底的概率变化曲线
        self._add_rate_curve_chart(game, pool_type, records, accent)

        # 3. 各星级统计柱状图：展示3/4/5星（或4/5/6星）的数量对比
        self._add_rarity_chart(stats, accent)

        # 4. 卡池投入占比饼图：展示各卡池的抽数投入比例
        self._add_pool_distribution_chart(records, accent)

        # 5. 月度抽卡趋势柱状图：展示最近12个月的抽卡数量变化
        self._add_monthly_trend_chart(records, accent)

        # 6. 50/50统计饼图：展示UP/歪的比例
        self._add_featured_chart(records, accent, game)

        # 在底部添加弹性空间，让图表紧靠顶部
        self.chart_layout.addStretch()

    def _create_canvas(self, title_text, figsize=(10, 4)):
        """创建图表画布的通用方法

        为每个图表创建统一的容器结构：
        QFrame(卡片容器) -> QVBoxLayout -> QLabel(标题) + FigureCanvas(图表)

        参数:
            title_text (str): 图表标题文字
            figsize (tuple): 图表尺寸(宽度, 高度)，单位为英寸
                            默认(10, 4)即10英寸宽、4英寸高
                            在100 DPI下约为1000x400像素

        返回:
            tuple: (Figure, FigureCanvas)
                   Figure是matplotlib的图形对象，用于绑图
                   FigureCanvas是Qt组件，用于在界面中显示图表
        """
        # 创建卡片容器QFrame
        frame = QFrame()
        # 设置对象名为"card"（便于CSS选择器定位）
        frame.setObjectName("card")
        # 白色背景 + 12px圆角 + 浅灰色边框，形成卡片式外观
        frame.setStyleSheet(
            "QFrame { background-color: white; border-radius: 12px; "
            "border: 1px solid #e8e8e8; }"
        )
        # 卡片内部垂直布局
        layout = QVBoxLayout(frame)

        # 图表标题
        title = QLabel(title_text)
        title.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        layout.addWidget(title)

        # 创建matplotlib Figure对象
        # figsize指定图表尺寸（英寸），dpi指定每英寸像素数
        fig = Figure(figsize=figsize, dpi=100)
        # 设置图形背景为白色
        fig.set_facecolor('white')

        # 将Figure渲染为Qt画布组件
        canvas = FigureCanvas(fig)
        # 设置最小高度300px，确保图表不会太小
        canvas.setMinimumHeight(300)

        # 安装事件过滤器，让画布的滚轮事件可以传递给父级滚动区域
        # eventFilter方法在本类中已重写
        canvas.installEventFilter(self)

        # 将画布添加到卡片布局
        layout.addWidget(canvas)

        # 将卡片添加到图表滚动区域的布局
        self.chart_layout.addWidget(frame)

        # 返回Figure和Canvas，调用者在Figure上绑图，最后调用canvas.draw()渲染
        return fig, canvas

    def _add_pull_distribution_chart(self, records, color):
        """绘制出货抽数分布直方图

        该图表展示每次出最高星时是在第几抽出的，
        帮助用户了解自己的出货运气分布：
        - 大量集中在1-10抽：运气好（欧皇）
        - 大量集中在70-80抽：运气一般
        - 有超过90抽的：可能是统计错误或特殊卡池

        参数:
            records (list): 抽卡记录列表
            color (str): 图表主色调（十六进制颜色代码）
        """
        # 创建统计分析器
        stats = StatsAnalyzer(records)
        # 从第一条记录获取游戏类型
        game = records[0].game if records else ""
        # 获取该游戏的最高星级
        max_rarity = get_max_rarity(game) if game else 5
        # 获取出货抽数分布数据（列表，每个元素是一次出5星时的抽数）
        distribution = stats.get_pull_distribution(max_rarity)

        # 无数据时不绘制
        if not distribution:
            return

        # 创建画布
        fig, canvas = self._create_canvas("出货抽数分布（每次5星在第几抽出）")
        # 创建子图（111表示1行1列第1个图）
        ax = fig.add_subplot(111)

        # 创建柱状图的分箱范围
        # range(1, max(distribution)+2) 确保覆盖所有数据点
        # +2是因为range的上界是不包含的，且hist需要一个额外的边界
        bins = range(1, max(distribution) + 2)
        # 绘制直方图
        # alpha=0.8 设置透明度（0完全透明，1完全不透明）
        # edgecolor='white' 给每个柱子添加白色边框，使其更容易区分
        ax.hist(distribution, bins=bins, color=color, alpha=0.8, edgecolor='white')

        # 计算平均值
        avg = sum(distribution) / len(distribution)
        # 绘制平均值的红色虚线
        # linestyle='--' 表示虚线，linewidth=1.5 设置线宽
        ax.axvline(
            avg, color='red', linestyle='--',
            linewidth=1.5, label=f'平均: {avg:.1f}'
        )
        # 设置X轴标签
        ax.set_xlabel('抽数')
        # 设置Y轴标签
        ax.set_ylabel('次数')
        # 显示图例（label参数定义的文本）
        ax.legend()
        # 添加Y轴网格线，alpha=0.3设置透明度
        ax.grid(axis='y', alpha=0.3)

        # tight_layout()自动调整子图参数，使之填充整个图形区域
        fig.tight_layout()
        # 将图形渲染到画布上（必须在所有绑图操作完成后调用）
        canvas.draw()

    def _add_rate_curve_chart(self, game, pool_type, records, color):
        """绘制保底概率曲线图

        该图表展示从当前位置到硬保底之间，每一抽的5星概率。
        曲线会呈现出明显的两段式特征：
        - 软保底前：概率保持基础值（如原神0.6%）
        - 软保底后：概率急剧上升直到硬保底100%

        参数:
            game (str): 游戏标识符
            pool_type (str): 卡池类型
            records (list): 抽卡记录列表
            color (str): 图表主色调
        """
        # 懒导入get_mechanic_type函数
        from core.models import get_mechanic_type

        # 获取卡池名称和机制类型
        pool_name = records[0].pool_name if records else ""
        # get_mechanic_type根据游戏、卡池类型和名称判断使用哪套保底机制
        mechanic_type = get_mechanic_type(game, pool_type, pool_name)

        # 尝试查找机制类型的配置，如果找不到则用pool_type查找
        # 这是一种降级策略：先用精确类型查找，找不到就用通用类型
        config = BANNER_CONFIGS.get((game, mechanic_type))
        if not config:
            config = BANNER_CONFIGS.get((game, pool_type))
        if not config:
            return

        # 获取当前保底计数
        pool_name = records[0].pool_name if records else ""
        pity = self.db.get_last_5star_pity(
            records[0].account_id, pool_type, game, pool_name=pool_name
        )

        # 创建画布
        fig, canvas = self._create_canvas("逐抽出5星概率曲线")
        ax = fig.add_subplot(111)

        # 生成从当前保底计数到硬保底的每抽位置
        pulls = list(range(pity, config.hard_pity + 1))
        # 计算每个位置的概率（百分比）
        rates = [get_rate_at_pull(config, p) * 100 for p in pulls]

        # 绘制概率曲线
        # X轴是"距今抽数"（从0开始），Y轴是概率百分比
        ax.plot(
            [p - pity for p in pulls], rates,
            color=color, linewidth=2  # 2px线宽
        )
        # fill_between()在曲线下方填充半透明颜色，增加视觉效果
        ax.fill_between(
            [p - pity for p in pulls], rates,
            alpha=0.2, color=color  # 20%透明度
        )

        # 绘制当前位置指示线
        if pity >= config.soft_pity_start:
            # 已进入软保底区间，用橙色虚线标记
            ax.axvline(
                0, color='orange', linestyle='--',
                alpha=0.7, label='当前位置(软保底中)'
            )
        else:
            # 还在基础概率区间，用绿色虚线标记
            ax.axvline(
                0, color='green', linestyle='--',
                alpha=0.7, label='当前位置'
            )

        # 绘制硬保底位置的红色虚线
        ax.axvline(
            config.hard_pity - pity, color='red',
            linestyle='--', alpha=0.5, label='硬保底'
        )
        ax.set_xlabel('距今抽数')
        ax.set_ylabel('5星概率 (%)')
        ax.legend()
        ax.grid(alpha=0.3)

        fig.tight_layout()
        canvas.draw()

    def _add_rarity_chart(self, stats, color):
        """绘制各星级数量统计柱状图

        该图表以柱状图形式展示各星级物品的数量，
        使用不同颜色区分星级，柱子上方标注具体数值。

        参数:
            stats (StatsAnalyzer): 统计分析器实例
            color (str): 主色调（实际中各星级使用独立颜色）
        """
        # 获取汇总统计数据
        summary = stats.get_summary()
        # 无数据时不绘制
        if summary["total"] == 0:
            return

        # 创建画布（较窄的尺寸适合柱状图）
        fig, canvas = self._create_canvas("各星级数量统计", figsize=(6, 4))
        ax = fig.add_subplot(111)

        # 动态获取游戏和最高星级
        game = stats.game if hasattr(stats, 'game') else ""
        max_rarity = get_max_rarity(game) if game else 5

        # 构建柱状图数据
        labels = []  # X轴标签（如"5星"、"4星"、"3星"）
        values = []  # 柱子高度（各星级的数量）
        # 各星级的颜色：橙色(最高星)、紫色、蓝色、绿色
        colors = ['#FF6B35', '#9B7ED8', '#90CAF9', '#A5D6A7']

        # 从最高星级向下遍历到3星
        for r in range(max_rarity, 2, -1):
            labels.append(f'{r}星')
            # summary.get(f"star_{r}", 0) 获取该星级的数量，不存在则默认为0
            values.append(summary.get(f"star_{r}", 0))

        # 绘制柱状图
        # width=0.5 设置柱子宽度为分类宽度的50%
        bars = ax.bar(labels, values, color=colors[:len(values)],
                       width=0.5, edgecolor='white')

        # 在每根柱子上方标注具体数值
        for bar, val in zip(bars, values):
            # text()在指定位置添加文本
            # x: 柱子中心的x坐标
            # y: 柱子顶部上方5个单位
            # ha='center': 水平居中对齐
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 1,
                str(val), ha='center', fontweight='bold'
            )

        ax.set_ylabel('数量')
        ax.grid(axis='y', alpha=0.3)

        fig.tight_layout()
        canvas.draw()

    def _add_pool_distribution_chart(self, records, color):
        """绘制卡池投入占比饼图

        该图表以饼图形式展示用户在各卡池上的抽数投入比例，
        帮助用户了解自己的资源分配情况。

        参数:
            records (list): 抽卡记录列表
            color (str): 主色调（实际中饼图使用独立的颜色列表）
        """
        # 懒导入Counter和get_pool_names
        from collections import Counter
        from core.models import get_pool_names

        # 统计每个卡池类型的记录数（即抽数）
        pool_counts = Counter(r.pool_type for r in records)
        if not pool_counts:
            return

        fig, canvas = self._create_canvas("卡池投入占比", figsize=(6, 4))
        ax = fig.add_subplot(111)

        # 获取游戏ID和卡池配置映射
        game = records[0].game if records else ""
        # get_pool_names返回[(pool_type, name), ...]，转换为字典方便查找
        pool_config = dict(get_pool_names(game))
        # 将内部pool_type转换为用户可见的卡池名称
        labels = [pool_config.get(k, k) for k in pool_counts.keys()]
        values = list(pool_counts.values())
        # 饼图使用多种颜色，足够7种卡池
        colors = [
            '#FF6B35', '#9B7ED8', '#90CAF9', '#A5D6A7',
            '#FFD54F', '#80CBC4', '#FFAB91'
        ]

        # 绘制饼图
        # autopct='%1.1f%%' 显示百分比，保留1位小数
        # startangle=90 让第一个扇形从12点钟方向开始
        wedges, texts, autotexts = ax.pie(
            values, labels=labels, autopct='%1.1f%%',
            colors=colors[:len(values)], startangle=90
        )
        # axis('equal') 确保饼图是正圆形（不被坐标轴比例拉伸）

        fig.tight_layout()
        canvas.draw()

    def _add_monthly_trend_chart(self, records, color):
        """绘制月度抽卡趋势图

        该图表以柱状图+折线图的组合形式，展示最近12个月的抽卡数量变化。
        柱状图表示每月抽数，红色折线连接各月数据点以突出趋势。

        参数:
            records (list): 抽卡记录列表
            color (str): 柱状图主色调
        """
        # 创建统计分析器
        stats = StatsAnalyzer(records)
        # 获取月度趋势数据 {月份字符串: 抽数}
        # 如 {"2024-01": 150, "2024-02": 80, ...}
        monthly = stats.get_monthly_trend()
        if not monthly:
            return

        fig, canvas = self._create_canvas("月度抽卡趋势")
        ax = fig.add_subplot(111)

        # 取最近12个月的数据（避免图表过长）
        # list(monthly.keys())[-12:] 取最后12个key
        months = list(monthly.keys())[-12:]
        values = [monthly[m] for m in months]
        # 从"2024-01"中提取"01"，只显示月份不显示年份
        display_months = [m[5:] for m in months]

        # 绘制柱状图
        ax.bar(display_months, values, color=color, alpha=0.8, edgecolor='white')
        # 在柱状图上方叠加折线图，突出趋势变化
        # marker='o' 在数据点处画圆点，markersize=4 设置圆点大小
        ax.plot(
            display_months, values, color='red',
            marker='o', markersize=4, linewidth=1
        )

        ax.set_xlabel('月份')
        ax.set_ylabel('抽数')
        ax.grid(axis='y', alpha=0.3)

        fig.tight_layout()
        canvas.draw()

    def _add_featured_chart(self, records, color, game=""):
        """绘制50/50统计饼图

        该图表展示最高星中UP角色/武器的比例（"赢"）和歪的比例（"输"）。
        理论上UP率是50%，但实际数据可能偏离。

        参数:
            records (list): 抽卡记录列表
            color (str): 主色调（实际中UP/歪使用绿/红色）
            game (str): 当前游戏标识符，默认空字符串

        特殊处理:
            明日方舟没有50/50机制，直接返回不绘制此图表。
        """
        # 明日方舟没有50/50机制（不是50%概率出UP角色）
        if game == "arknights":
            return

        # 获取最高星级
        max_rarity = get_max_rarity(game) if game else 5
        # 筛选出所有最高星级的记录
        five_stars = [r for r in records if r.rarity == max_rarity]
        # 无最高星记录时不绘制
        if not five_stars:
            return

        # 统计UP次数（"赢"）和歪次数（"输"）
        # sum(1 for r in five_stars if r.is_featured) 统计is_featured为True的记录数
        # 这种写法等价于len([r for r in five_stars if r.is_featured])
        # 但更节省内存（生成器表达式vs列表推导式）
        wins = sum(1 for r in five_stars if r.is_featured)
        losses = len(five_stars) - wins

        fig, canvas = self._create_canvas("50/50 统计", figsize=(6, 4))
        ax = fig.add_subplot(111)

        # 只有当有数据时才绘制饼图
        if wins + losses > 0:
            # 标签中包含次数信息，如 "UP (15次)" "歪 (10次)"
            labels = [f'UP ({wins}次)', f'歪 ({losses}次)']
            values = [wins, losses]
            # 绿色代表UP（胜利），红色代表歪（失败）
            colors = ['#4CAF50', '#FF5252']

            # 绘制饼图
            wedges, texts, autotexts = ax.pie(
                values, labels=labels, autopct='%1.1f%%',
                colors=colors, startangle=90
            )
        # 确保饼图是正圆形
        ax.axis('equal')

        fig.tight_layout()
        canvas.draw()
