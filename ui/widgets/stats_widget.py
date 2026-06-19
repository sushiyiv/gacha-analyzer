"""统计分析页面

本模块实现了抽卡统计分析的完整UI界面，包括：
- 保底（硬保底/软保底）进度跟踪与分析
- 50/50（UP/歪）概率统计
- 高星出货记录展示
- 概率预测（表格模式和滑动条模式两种展示方式）

所有数据从数据库实时读取，用户切换卡池时自动刷新。
"""

# ========== 导入语句 ==========

# 导入PySide6（Qt for Python）的窗口部件模块
# QWidget: 所有UI组件的基类
# QVBoxLayout: 垂直布局管理器，从上到下排列子组件
# QHBoxLayout: 水平布局管理器，从左到右排列子组件
# QLabel: 文本标签，用于显示静态文字信息
# QFrame: 带边框的容器组件，可用作分隔或装饰
# QTableWidget: 表格组件，用于以行列形式展示数据
# QTableWidgetItem: 表格中的单个单元格项
# QHeaderView: 表头视图，控制表格列的显示和调整模式
# QScrollArea: 滚动区域，当内容超出可视范围时提供滚动条
# QComboBox: 下拉选择框，用户可从预定义列表中选择一项
# QGroupBox: 带标题边框的分组容器，用于将相关控件视觉上归为一组
# QStackedWidget: 堆叠容器，一次只显示一个子组件，用于实现多页面切换
# QSlider: 滑动条，允许用户通过拖动滑块在一个范围内选择数值
# QProgressBar: 进度条，以图形化方式显示进度百分比
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea,
    QComboBox, QGroupBox, QStackedWidget, QSlider, QProgressBar
)

# Qt: PySide6核心模块，包含各种枚举值和基础类型
# AlignmentFlag: 对齐标志（如居中、左对齐等）
# CursorShape: 鼠标光标形状（如手形、箭头等）
# Orientation: 方向标志（水平/垂直）
# TickPosition: 滑动条刻度线位置
from PySide6.QtCore import Qt

# QFont: 字体类，用于设置文字的字体族、大小、粗细等属性
# QColor: 颜色类，用于表示和处理颜色值
from PySide6.QtGui import QFont, QColor

# Database: 数据库封装类，提供抽卡记录的增删改查接口
from core.database import Database

# PityAnalyzer: 保底分析器，负责计算当前保底进度、期望抽数等
# StatsAnalyzer: 统计分析器，负责计算50/50胜率、各星级分布等统计数据
from core.analyzer import PityAnalyzer, StatsAnalyzer

# BANNER_CONFIGS: 卡池配置字典，key为(game, pool_type)元组，value为包含保底参数的配置对象
# GAME_COLORS: 游戏主题色配置字典，key为游戏ID，value为包含颜色信息的字典
# get_max_rarity: 获取指定游戏最高星级的函数（如原神为5，明日方舟为6）
# get_pool_names: 获取指定游戏所有卡池名称列表的函数，返回[(pool_type, name), ...]
# get_endfield_pity_group: 获取终末地卡池保底分组的函数
# ENDFIELD_PITY_GROUP: 终末地保底分组映射字典
# ENDFIELD_PITY_RESETS_ON_NAME_CHANGE: 在卡池名称变更时重置保底的终末地分组列表
from core.models import (
    BANNER_CONFIGS, GAME_COLORS, get_max_rarity, get_pool_names,
    get_endfield_pity_group, ENDFIELD_PITY_GROUP,
    ENDFIELD_PITY_RESETS_ON_NAME_CHANGE
)


class StatsWidget(QWidget):
    """统计分析页面组件

    继承自QWidget，作为Qt窗口部件树中的一个节点。
    该类负责：
    1. 构建包含保底分析、50/50统计、出货记录、概率预测四大模块的完整UI
    2. 从数据库读取抽卡记录并计算统计数据
    3. 响应用户操作（切换卡池、切换显示模式、拖动滑块）并实时更新显示

    属性:
        main_window: 主窗口引用，用于获取当前选中的账号和游戏信息
        db: Database实例，用于数据库查询操作
        pool_combo: 卡池选择下拉框
        pity_summary: 保底分析摘要文本标签
        pity_table: 保底分析详情表格
        featured_summary: 50/50统计摘要文本标签
        featured_table: 50/50统计详情表格
        pull_table: 出货记录表格
        toggle_indicator: 概率预测模式切换的滑动指示器
        toggle_left_label: 切换按钮左侧"表格"文字标签
        toggle_right_label: 切换按钮右侧"进度条"文字标签
        prob_stack: 概率预测的堆叠容器（表格模式/滑动条模式）
        prob_table: 概率预测的表格模式组件
        prob_slider: 概率预测的滑动条
        slider_pull_label: 滑动条当前抽数显示
        slider_max_label: 滑动条最大值显示
        slider_prob_label: 滑动条当前概率大字显示
        slider_prob_bar: 概率进度条
        slider_context_label: 滑动条上下文提示
        slider_desc_label: 滑动条说明文字
    """

    def __init__(self, main_window):
        """构造函数

        参数:
            main_window: 主窗口实例的引用。通过该引用可调用
                         get_current_account()获取当前账号，
                         get_current_game()获取当前游戏，
                         refresh_all()刷新所有页面等方法。
                         这是一种典型的"依赖注入"模式，子组件不自己创建依赖，
                         而是由父组件传入。
        """
        # 调用父类QWidget的构造函数，完成Qt对象的基础初始化
        # 这包括：设置Qt对象指针、元对象系统注册等底层操作
        super().__init__()

        # 保存主窗口引用，供后续调用主窗口的方法（如获取当前账号/游戏）
        self.main_window = main_window

        # 创建Database实例，用于后续的数据库查询操作
        # Database类封装了SQLite数据库的所有操作，采用单例模式
        self.db = Database()

        # 调用UI初始化方法，构建整个页面的界面布局和组件
        # 将UI初始化独立为方法可以保持构造函数的简洁性
        self._init_ui()

    def _init_ui(self):
        """初始化整个页面的UI布局

        该方法构建了统计分析页面的完整界面，包含以下模块：
        1. 顶部标题栏 + 卡池选择下拉框
        2. 保底分析区块（摘要 + 详情表格）
        3. 50/50统计区块（摘要 + 详情表格）
        4. 出货记录区块（完整记录表格）
        5. 概率预测区块（表格模式 + 滑动条模式，可切换）

        所有区块都包裹在QScrollArea中，当内容超出窗口高度时自动出现滚动条。
        Qt的布局系统会自动计算各组件的大小和位置，开发者只需指定排列方式和间距。
        """

        # 创建垂直布局管理器作为页面根布局
        # setContentsMargins(0,0,0,0) 移除布局四周的默认边距(默认是11px)
        # 这样可以让内容紧贴窗口边缘，最大化利用空间
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建滚动区域，作为整个页面内容的容器
        # 当内容高度超过可视区域时，QScrollArea会自动显示垂直滚动条
        scroll = QScrollArea()
        # setWidgetResizable(True) 让滚动区域内的内容组件自动调整大小以填满可用空间
        # 否则内容组件会保持固定大小，可能导致滚动区域内出现不必要的空白
        scroll.setWidgetResizable(True)
        # 设置滚动区域无边框外观（NoFrame），使其与背景融为一体
        # QFrame.Shape.NoFrame 是一个枚举值，表示不绘制任何边框
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        # 创建滚动区域内的内容组件
        # QScrollArea只能包含一个子widget，这个widget是所有内容的根容器
        scroll_widget = QWidget()

        # 在scroll_widget上创建垂直布局，用于从上到下排列所有子模块
        main_layout = QVBoxLayout(scroll_widget)

        # ===== 顶部标题和卡池选择区域 =====
        # 创建水平布局，左侧放标题，右侧放卡池选择器
        header = QHBoxLayout()

        # 创建标题标签
        title = QLabel("统计分析")
        # 设置字体：Microsoft YaHei(微软雅黑)字号18粗体
        # QFont.Weight.Bold 是Qt6中表示粗体的枚举值
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        # 将标题添加到水平布局的左侧
        header.addWidget(title)
        # addStretch()在标题和下拉框之间添加弹性空间
        # 弹性空间会占据所有剩余宽度，从而将标题推到左侧、下拉框推到右侧
        header.addStretch()

        # 创建"卡池:"文字标签
        header.addWidget(QLabel("卡池:"))
        # 创建卡池选择下拉框
        self.pool_combo = QComboBox()
        # 当用户切换下拉框选项时，触发currentIndexChanged信号
        # 该信号连接到lambda回调，lambda内部调用self.refresh()刷新整个页面
        # currentIndexChanged信号在索引变化时发出，参数为新的索引值（这里lambda忽略了它）
        self.pool_combo.currentIndexChanged.connect(lambda: self.refresh())
        # 将下拉框添加到水平布局
        header.addWidget(self.pool_combo)
        # 将整个header水平布局添加到主垂直布局中
        main_layout.addLayout(header)

        # ===== 保底分析区块 =====
        # QGroupBox提供带标题的分组框外观，视觉上将保底相关内容归为一组
        pity_group = QGroupBox("保底分析")
        # 使用QSS(QT Style Sheet)设置样式，类似于网页的CSS
        # { font-weight: bold; font-size: 14px; } 让标题文字加粗、14px字号
        pity_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        # 在分组框内部创建垂直布局来排列保底相关的子组件
        pity_layout = QVBoxLayout(pity_group)

        # 创建保底摘要标签，显示当前保底进度的概要信息
        # 初始化文本为"暂无数据"，等有数据时会被替换
        self.pity_summary = QLabel("暂无数据")
        # 设置摘要标签字体大小为13px
        self.pity_summary.setStyleSheet("font-size: 13px;")
        # 将摘要标签添加到保底分组的垂直布局中
        pity_layout.addWidget(self.pity_summary)

        # 创建保底详情表格
        # QTableWidget是基于项的表格组件，每个单元格是一个QTableWidgetItem
        self.pity_table = QTableWidget()
        # 设置表格有4列
        self.pity_table.setColumnCount(4)
        # 设置4列的表头文字：指标名称、具体数值、说明文字、备注
        self.pity_table.setHorizontalHeaderLabels(["指标", "数值", "说明", "备注"])
        # setSectionResizeMode(Stretch) 让所有列平均分配表格宽度
        # 这样无论窗口大小如何变化，各列都会等宽显示
        self.pity_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        # 隐藏行号列（最左侧的1,2,3...编号），因为保底数据不需要行号
        self.pity_table.verticalHeader().setVisible(False)
        # 禁用表格的编辑功能，防止用户点击单元格时触发编辑
        # NoEditTriggers 表示没有任何编辑触发条件
        self.pity_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # 设置表格最小高度为200px，确保即使数据很少也能有足够的显示空间
        self.pity_table.setMinimumHeight(200)
        # 将表格添加到保底分组的布局中
        pity_layout.addWidget(self.pity_table)
        # 将整个保底分组框添加到主布局
        main_layout.addWidget(pity_group)

        # ===== 50/50 统计区块 =====
        # 50/50是指抽到最高星时，有50%概率获得UP角色/武器，50%概率歪（获得非UP角色/武器）
        featured_group = QGroupBox("50/50 统计")
        featured_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        # 在分组框内创建垂直布局
        featured_layout = QVBoxLayout(featured_group)

        # 50/50统计的摘要标签
        self.featured_summary = QLabel("暂无数据")
        self.featured_summary.setStyleSheet("font-size: 13px;")
        featured_layout.addWidget(self.featured_summary)

        # 50/50统计详情表格，3列：指标、数值、说明
        self.featured_table = QTableWidget()
        self.featured_table.setColumnCount(3)
        self.featured_table.setHorizontalHeaderLabels(["指标", "数值", "说明"])
        # 列宽自动拉伸填满表格宽度
        self.featured_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        # 隐藏行号
        self.featured_table.verticalHeader().setVisible(False)
        # 禁止编辑
        self.featured_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # 最小高度180px
        self.featured_table.setMinimumHeight(180)
        # 设置默认行高为40px，让每行有更舒适的阅读间距
        self.featured_table.verticalHeader().setDefaultSectionSize(40)
        featured_layout.addWidget(self.featured_table)
        main_layout.addWidget(featured_group)

        # ===== 出货记录区块 =====
        # 展示所有最高星级物品的获取记录
        pull_group = QGroupBox("出货记录")
        pull_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        pull_layout = QVBoxLayout(pull_group)

        # 创建出货记录表格，6列
        self.pull_table = QTableWidget()
        self.pull_table.setColumnCount(6)
        # 设置6列表头：序号、物品名称、星级、是否为UP角色、保底计数、获取时间
        self.pull_table.setHorizontalHeaderLabels(
            ["序号", "名称", "星级", "是否UP", "保底计数", "时间"]
        )
        # 获取水平表头对象，用于设置列宽调整模式
        # 注意：这里的变量名header与前面的header(布局)同名，但作用域不同，不会冲突
        header = self.pull_table.horizontalHeader()
        # Interactive模式允许用户手动拖动列边框调整列宽
        # 与Stretch模式不同，Interactive不会自动平均分配宽度
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # 手动设置每列的初始宽度（像素值），根据内容预期长度来分配
        self.pull_table.setColumnWidth(0, 60)   # 序号列：只需显示较小的数字
        self.pull_table.setColumnWidth(1, 200)  # 名称列：角色/武器名通常较长
        self.pull_table.setColumnWidth(2, 110)  # 星级列：显示"★★★★★"等星号
        self.pull_table.setColumnWidth(3, 80)   # 是否UP列：只显示"是"或"否"
        self.pull_table.setColumnWidth(4, 100)  # 保底计数列：显示数字
        self.pull_table.setColumnWidth(5, 200)  # 时间列：显示完整的日期时间字符串
        # 隐藏行号
        self.pull_table.verticalHeader().setVisible(False)
        # 禁止编辑
        self.pull_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # 最小高度300px，出货记录通常较多需要较大空间
        self.pull_table.setMinimumHeight(300)
        # stretchLastSection让最后一列自动填充剩余空间
        # 当窗口变宽时，时间列会自动变宽而非留出空白
        self.pull_table.horizontalHeader().setStretchLastSection(True)
        pull_layout.addWidget(self.pull_table)
        main_layout.addWidget(pull_group)

        # ===== 概率预测区块 =====
        # 概率预测展示在不同抽数下的出货概率，支持表格和进度条两种查看模式
        prob_group = QGroupBox("概率预测")
        prob_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        prob_layout = QVBoxLayout(prob_group)

        # --- 自定义开关式切换按钮 ---
        # 使用固定大小的QWidget作为切换按钮的容器
        # 整体宽度170px，高度32px
        toggle_wrapper = QWidget()
        toggle_wrapper.setFixedSize(170, 32)
        # 设置鼠标悬停时显示手形光标，提示用户可以点击
        toggle_wrapper.setCursor(Qt.CursorShape.PointingHandCursor)

        # 背景轨道：灰色的底色条，模拟滑动开关的轨道
        toggle_bg = QFrame(toggle_wrapper)
        # setGeometry(x, y, width, height) 设置子组件在父组件中的位置和大小
        # 这里x=0(左边缘对齐), y=4(距顶部4px留出边距), 宽170, 高24
        toggle_bg.setGeometry(0, 4, 170, 24)
        # 设置背景色为浅灰色，border-radius:12px让圆角等于高度一半，形成胶囊形状
        toggle_bg.setStyleSheet("background: #e0e0e0; border-radius: 12px;")

        # 滑动指示器：蓝色的可移动滑块，表示当前选中的模式
        self.toggle_indicator = QFrame(toggle_wrapper)
        # 初始位置在左侧(0,4)，宽85(总宽的一半)，高24
        self.toggle_indicator.setGeometry(0, 4, 85, 24)
        # 蓝色背景 + 圆角，形成蓝色胶囊形状
        self.toggle_indicator.setStyleSheet(
            "background: #1a73e8; border-radius: 12px;"
        )

        # 左侧文字标签："表格"模式
        self.toggle_left_label = QLabel("表格", toggle_wrapper)
        # 位置与指示器相同(0,4)，宽85，高24，文字居中显示
        self.toggle_left_label.setGeometry(0, 4, 85, 24)
        # AlignCenter让文字在标签内水平和垂直居中
        self.toggle_left_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 粗体11号微软雅黑字体
        self.toggle_left_label.setFont(
            QFont("Microsoft YaHei", 11, QFont.Weight.Bold)
        )
        # 白色文字，透明背景（不遮挡下方的指示器）
        self.toggle_left_label.setStyleSheet("color: white; background: transparent;")

        # 右侧文字标签："进度条"模式
        self.toggle_right_label = QLabel("进度条", toggle_wrapper)
        # 位置在右半边(x=85, y=4)
        self.toggle_right_label.setGeometry(85, 4, 85, 24)
        self.toggle_right_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 非粗体11号字，因为未被选中所以用普通字重
        self.toggle_right_label.setFont(QFont("Microsoft YaHei", 11))
        # 灰色文字，表示未选中状态
        self.toggle_right_label.setStyleSheet("color: #666; background: transparent;")

        # raise_()将标签提升到Z序的最上层，确保文字显示在指示器上方
        # Qt中后添加的组件默认在上层，但这里文字和指示器是通过不同方式添加的
        # 手动提升Z序可以确保文字始终可见
        self.toggle_left_label.raise_()
        self.toggle_right_label.raise_()

        # 重写toggle_wrapper的mousePressEvent事件处理函数
        # 当用户点击切换按钮区域时，翻转当前显示模式
        # lambda中的e是鼠标事件参数(QMouseEvent)，被忽略因为不需要使用
        # 1 - currentIndex() 实现0和1之间的切换：如果是0则变为1，如果是1则变为0
        toggle_wrapper.mousePressEvent = lambda e: self._switch_prob_mode(
            1 - self.prob_stack.currentIndex()
        )

        # 创建水平布局，让切换按钮居中显示
        toggle_bar = QHBoxLayout()
        # addStretch()在左侧添加弹性空间
        toggle_bar.addStretch()
        # 将切换按钮添加到中间
        toggle_bar.addWidget(toggle_wrapper)
        # addStretch()在右侧添加弹性空间，两个弹性空间使按钮居中
        toggle_bar.addStretch()
        # 将水平布局添加到概率预测分组的垂直布局中
        prob_layout.addLayout(toggle_bar)

        # --- QStackedWidget：模式切换容器 ---
        # QStackedWidget管理多个子页面，同一时间只显示一个
        # 通过setCurrentIndex()切换显示的页面
        self.prob_stack = QStackedWidget()

        # --- 页面0：表格模式 ---
        # 创建概率预测表格，3列：抽数、出货概率、概率条(ASCII图形)
        self.prob_table = QTableWidget()
        self.prob_table.setColumnCount(3)
        self.prob_table.setHorizontalHeaderLabels(["抽数", "出货概率", "概率条"])
        self.prob_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.prob_table.verticalHeader().setVisible(False)
        self.prob_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.prob_table.setMinimumHeight(300)
        # 将表格添加到堆叠容器中，索引为0
        self.prob_stack.addWidget(self.prob_table)

        # --- 页面1：进度条模式（滑动条交互） ---
        # 创建一个QWidget作为进度条模式的页面容器
        slider_page = QWidget()
        # 在该页面内创建垂直布局
        slider_layout = QVBoxLayout(slider_page)
        # 设置布局的内边距为20px（上下左右各20px）
        slider_layout.setContentsMargins(20, 20, 20, 20)
        # 设置子组件之间的垂直间距为15px
        slider_layout.setSpacing(15)

        # 上下文提示标签：显示当前保底进度（如"当前已垫: 30抽"）
        self.slider_context_label = QLabel("当前已垫: 0抽")
        # 12号微软雅黑字体
        self.slider_context_label.setFont(QFont("Microsoft YaHei", 12))
        slider_layout.addWidget(self.slider_context_label)

        # 创建水平方向的滑动条，允许用户选择抽数来查看对应概率
        self.prob_slider = QSlider(Qt.Orientation.Horizontal)
        # 滑动条最小值为1（最少1抽）
        self.prob_slider.setMinimum(1)
        # 最大值初始为90（后续会根据卡池配置动态更新）
        self.prob_slider.setMaximum(90)
        # 初始值为10，表示默认显示"第10抽"的概率
        self.prob_slider.setValue(10)
        # 设置刻度线显示在滑块下方
        self.prob_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        # 每隔10个单位显示一个刻度线
        self.prob_slider.setTickInterval(10)
        # 固定滑动条高度为40px，确保有足够空间显示滑块和刻度
        self.prob_slider.setFixedHeight(40)
        # 使用QSS详细样式化滑动条的各个部分
        self.prob_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                /* groove是滑动条的背景轨道 */
                border: none; height: 8px; border-radius: 4px;
                background: #ddd;  /* 浅灰色轨道 */
            }
            QSlider::handle:horizontal {
                /* handle是可拖动的滑块 */
                background: #1a73e8; border: 3px solid #fff;
                width: 28px; height: 28px; margin: -13px 0;
                /* margin负值让滑块超出轨道上下边界，形成更大的触控区域 */
                border-radius: 17px;  /* 圆形滑块 */
            }
            QSlider::handle:horizontal:hover {
                /* 悬停时颜色加深 */
                background: #1557b0;
            }
            QSlider::sub-page:horizontal {
                /* sub-page是滑块左侧已滑过的区域 */
                border-radius: 4px; background: #1a73e8;
            }
            QSlider::tick-mark:horizontal {
                /* tick-mark是刻度线 */
                width: 2px; height: 8px; background: #bbb; margin: 0;
            }
        """)
        # 将滑动条的valueChanged信号连接到_on_slider_changed方法
        # valueChanged信号在用户拖动滑块或通过程序设置值时发出
        # 参数为新的整数值
        self.prob_slider.valueChanged.connect(self._on_slider_changed)
        slider_layout.addWidget(self.prob_slider)

        # 滑块数值显示行：显示范围 "1  ---[10抽]---  90"
        slider_val_row = QHBoxLayout()
        # 最小值标签"1"
        slider_val_row.addWidget(QLabel("1"))
        # 当前值标签"10抽"，居中显示
        self.slider_pull_label = QLabel("10抽")
        self.slider_pull_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 14号粗体字，突出显示当前选择的抽数
        self.slider_pull_label.setFont(
            QFont("Microsoft YaHei", 14, QFont.Weight.Bold)
        )
        slider_val_row.addWidget(self.slider_pull_label)
        # 最大值标签，右对齐
        self.slider_max_label = QLabel("90")
        self.slider_max_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        slider_val_row.addWidget(self.slider_max_label)
        # 将水平行添加到垂直布局
        slider_layout.addLayout(slider_val_row)

        # 概率大字显示：以大号绿色字体显示当前概率百分比
        self.slider_prob_label = QLabel("出货概率: 6.0%")
        self.slider_prob_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 20号粗体字，非常醒目
        self.slider_prob_label.setFont(
            QFont("Microsoft YaHei", 20, QFont.Weight.Bold)
        )
        # 绿色文字(#4CAF50是Material Design绿色)
        self.slider_prob_label.setStyleSheet("color: #4CAF50;")
        slider_layout.addWidget(self.slider_prob_label)

        # 概率进度条：以图形化方式显示概率大小
        self.slider_prob_bar = QProgressBar()
        self.slider_prob_bar.setFixedHeight(30)
        # 设置最大值为10000，用于精确表示百分比（如5.67%对应567）
        self.slider_prob_bar.setMaximum(10000)
        # 在进度条上显示文字
        self.slider_prob_bar.setTextVisible(True)
        # "%p%"格式中%p会被替换为当前百分比值
        self.slider_prob_bar.setFormat("%p%")
        # QSS样式：圆角胶囊形状，绿色进度块
        self.slider_prob_bar.setStyleSheet("""
            QProgressBar {
                border: none; border-radius: 15px; background-color: #e0e0e0;
                text-align: center; color: #333; font-size: 12px; font-weight: bold;
            }
            QProgressBar::chunk {
                /* chunk是已填充的部分 */
                border-radius: 15px; background-color: #4CAF50;
            }
        """)
        slider_layout.addWidget(self.slider_prob_bar)

        # 说明提示文字
        self.slider_desc_label = QLabel("拖动滑块查看不同抽数下的出货概率")
        # 灰色小字，起辅助说明作用
        self.slider_desc_label.setStyleSheet("color: #888; font-size: 11px;")
        self.slider_desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        slider_layout.addWidget(self.slider_desc_label)

        # 在布局底部添加弹性空间，让上面的组件紧靠顶部
        slider_layout.addStretch()
        # 将进度条页面添加到堆叠容器，索引为1
        self.prob_stack.addWidget(slider_page)

        # 将堆叠容器添加到概率预测分组的布局
        prob_layout.addWidget(self.prob_stack)
        # 初始化切换按钮的视觉状态（表格模式）
        self._update_toggle_style()
        # 将概率预测分组添加到主布局
        main_layout.addWidget(prob_group)

        # 在主布局底部添加弹性空间，让所有内容紧靠顶部
        main_layout.addStretch()
        # 将scroll_widget设置为滚动区域的内容组件
        # 这是QScrollArea的必要步骤，必须通过setWidget()关联内容
        scroll.setWidget(scroll_widget)
        # 将滚动区域添加到页面根布局
        layout.addWidget(scroll)

    def _update_pool_combo(self, game):
        """根据当前游戏更新卡池下拉框的选项列表

        该方法在每次刷新时被调用，确保下拉框的选项与当前游戏匹配。
        切换游戏时会清空并重新填充所有卡池选项。

        参数:
            game (str): 游戏标识符，如 "genshin"(原神), "starrail"(星穹铁道),
                        "zzz"(绝区零), "wutheringwaves"(鸣潮),
                        "endfield"(终末地), "arknights"(明日方舟)

        信号处理:
            更新过程中使用blockSignals(True/False)临时屏蔽信号，
            防止clear()和addItem()操作触发不必要的currentIndexChanged信号，
            避免引起连锁刷新。这是Qt开发中的常见模式。
        """
        # 屏蔽信号，防止在清空和重新填充过程中触发refresh()导致的无限递归
        self.pool_combo.blockSignals(True)

        # 保存当前选中的卡池数据（pool_type或None），用于刷新后恢复选择
        current = self.pool_combo.currentData()

        # 清空下拉框中的所有选项
        self.pool_combo.clear()

        # 添加"全部卡池"选项，data为None表示不筛选特定卡池
        # QComboBox的addItem(text, userData)中userData可以存储任意Python对象
        self.pool_combo.addItem("全部卡池", None)

        # get_pool_names(game)返回该游戏所有可用卡池的列表
        # 返回格式: [(pool_type, pool_name), ...]
        # pool_type是内部标识符，pool_name是显示给用户的名称
        pools = get_pool_names(game)
        for pool_type, name in pools:
            # 每个选项的显示文字是卡池名称，关联数据是pool_type
            self.pool_combo.addItem(name, pool_type)

        # 尝试恢复之前选中的选项
        # findData()在所有选项中查找匹配data值的索引
        # 如果之前选中的卡池在新列表中仍然存在，则恢复选择
        idx = self.pool_combo.findData(current)
        if idx >= 0:
            self.pool_combo.setCurrentIndex(idx)

        # 重新启用信号，后续的用户操作可以正常触发信号
        self.pool_combo.blockSignals(False)

    def refresh(self):
        """刷新整个统计分析页面的数据

        这是核心的刷新方法，在以下情况下被调用：
        1. 用户切换卡池下拉框时
        2. 主窗口调用refresh_all()时
        3. 账号切换时

        方法执行流程：
        1. 获取当前账号和游戏
        2. 更新卡池下拉框选项
        3. 根据当前卡池从数据库加载记录
        4. 分别执行保底分析、50/50统计、出货记录、概率预测的更新
        5. 更新卡池抽数显示

        异常处理：
        - 保底分析用try/except包裹，即使分析失败也不影响其他模块的显示
        """
        # 获取当前选中的账号，如果未选择账号则直接返回
        account = self.main_window.get_current_account()
        if not account:
            return

        # 获取当前选中的游戏标识符
        game = self.main_window.get_current_game()

        # 根据当前游戏更新卡池下拉框选项
        self._update_pool_combo(game)
        # 获取当前选中的卡池类型（pool_type或None表示全部）
        pool_type = self.pool_combo.currentData()

        # 根据卡池选择加载对应的抽卡记录
        if pool_type is None:
            # 全部卡池模式：加载该账号所有游戏的所有记录
            records = self.db.get_records(account.id)
        elif game == "endfield" and pool_type:
            # 终末地的特殊处理：部分卡池共享保底计数
            # 获取当前卡池的保底分组
            pity_group = get_endfield_pity_group(pool_type)
            if pity_group in ENDFIELD_PITY_RESETS_ON_NAME_CHANGE:
                # 武器池等独立保底池：只加载当前卡池的记录
                # 因为这些池的保底不与其他池共享
                records = self.db.get_records(account.id, pool_type)
            else:
                # 标准池/限定池等共享保底池：加载同组所有卡池的记录
                # 例如轮换的限定池之间保底计数是继承的
                shared_types = [
                    pt for pt, g in ENDFIELD_PITY_GROUP.items()
                    if g == pity_group
                ]
                records = []
                for pt in shared_types:
                    records.extend(self.db.get_records(account.id, pt))
        else:
            # 其他游戏：直接按卡池类型筛选记录
            records = self.db.get_records(account.id, pool_type)

        # 如果没有记录，显示提示信息并返回
        if not records:
            self.pity_summary.setText("暂无数据，请先导入抽卡记录")
            return

        # ===== 保底分析（仅在选择了具体卡池时执行） =====
        if pool_type:
            try:
                # 从第一条记录获取卡池名称（同批次记录的卡池名称相同）
                pool_name = records[0].pool_name if records else ""
                # 创建保底分析器，传入游戏、卡池类型和卡池名称
                # PityAnalyzer需要这三个参数来确定使用哪套保底规则
                analyzer = PityAnalyzer(game, pool_type, pool_name)
                # 执行分析，返回包含各种保底统计数据的字典
                # 返回的字典包含: current_pity, hard_pity, current_rate,
                # pulls_to_hard, expected_to_5star, expected_to_featured,
                # avg_pity, min_pity, max_pity, is_guaranteed 等字段
                pity = analyzer.analyze(records)
                # 用分析结果更新保底显示
                self._update_pity(pity, game)
            except Exception as e:
                # 分析失败时显示错误信息，但不中断整个刷新流程
                self.pity_summary.setText(f"分析失败: {str(e)}")
        else:
            # 全部卡池模式下不执行保底分析（因为不同卡池的保底规则不同）
            self.pity_summary.setText("全部卡池综合统计（保底分析请切换到具体卡池）")
            self.pity_table.setRowCount(0)

        # ===== 统计分析 =====
        # 创建统计分析器，计算50/50等统计数据
        stats = StatsAnalyzer(records, game)
        # 更新50/50统计显示
        self._update_featured(stats, game)
        # 更新出货记录表格
        self._update_pulls(records, game)
        # 更新概率预测（表格模式和进度条模式都会更新）
        self._update_prob(game, pool_type, records)

        # 更新卡池抽数显示（预留接口，当前为空操作）
        self._update_pool_pull_counts(account, game)

    def _update_pity(self, pity, game):
        """更新保底分析的显示内容

        参数:
            pity (dict): PityAnalyzer.analyze()返回的保底分析结果字典，包含以下字段:
                - current_pity (int): 当前保底计数（距离上次最高星的抽数）
                - config: 保底配置对象，包含hard_pity(硬保底数)、base_rate_5star(基础概率)等
                - current_rate (float): 当前出货概率（0~1之间的小数）
                - pulls_to_hard (int): 距离硬保底还需的抽数
                - expected_to_5star (float): 出5星的数学期望抽数
                - expected_to_featured (float): 出UP角色的数学期望抽数（含保底机制）
                - avg_pity (float): 平均出货抽数
                - min_pity (int): 最少出货抽数（最欧记录）
                - max_pity (int): 最多出货抽数（最非记录）
                - is_guaranteed (bool): 是否处于大保底状态（下次必出UP）
                - up_hard_pity (int, 可选): UP角色的硬保底数
                - up_hard_pity_remaining (int, 可选): 距离UP硬保底还剩的抽数
                - up_hard_pity_inherits (bool, 可选): UP硬保底是否跨卡池继承
                - multi_pity_size (int, 可选): 十连保底的间隔抽数
                - multi_pity_progress (int, 可选): 十连保底的当前进度
                - multi_pity_rarity (int, 可选): 十连保底保证的最低星级
                - exchange_threshold (int, 可选): 自选/兑换所需的累计抽数
                - exchange_progress (int, 可选): 自选/兑换的当前进度
            game (str): 当前游戏标识符
        """
        # 获取当前游戏的主题色配置
        # GAME_COLORS的结构如: {"genshin": {"primary": "#e8a852", ...}}
        colors = GAME_COLORS.get(game, {})
        # 获取主色调，用于后续UI着色（默认蓝色）
        accent = colors.get("primary", "#1a73e8")

        # 格式化大保底状态文字
        guaranteed_text = "是（下次必出UP）" if pity["is_guaranteed"] else "否"

        # 设置保底摘要标签的文本
        # 使用f-string格式化，:.2f表示保留2位小数
        # *100将小数百分比转换为百分比显示（如0.06 -> 6.00%）
        self.pity_summary.setText(
            f"当前保底: {pity['current_pity']}/{pity['config'].hard_pity}  |  "
            f"当前概率: {pity['current_rate']*100:.2f}%  |  "
            f"大保底: {guaranteed_text}"
        )

        # 构建保底详情表格的行数据
        # 每行是一个四元组：(指标名称, 数值, 说明, 备注)
        rows = [
            ("当前抽数", f"{pity['current_pity']}",
             "距离上次最高星", ""),
            ("距离保底", f"{pity['pulls_to_hard']}",
             "必出最高星", ""),
            ("当前概率", f"{pity['current_rate']*100:.2f}%",
             f"基础{pity['config'].base_rate_5star*100}%", ""),
            ("期望抽数(最高星)", f"{pity['expected_to_5star']}",
             "数学期望", ""),
            ("期望抽数(UP)", f"{pity['expected_to_featured']}",
             "含保底机制", ""),
            ("平均出货", f"{pity['avg_pity']}",
             f"最欧:{pity['min_pity']} 最非:{pity['max_pity']}", ""),
        ]

        # 条件行：UP硬保底（仅当配置中存在UP硬保底时显示）
        # 终末地限定池120抽、武器池80抽；明日方舟单UP 150抽等
        # get()方法在字典中查找键，不存在则返回默认值0
        if pity.get("up_hard_pity", 0) > 0:
            rows.append((
                "UP大保底",
                f"{pity['up_hard_pity_remaining']}/{pity['up_hard_pity']}",
                "必出UP角色",
                # 如果UP硬保底不跨卡池继承，则在备注列显示"不继承"
                "" if pity['config'].up_hard_pity_inherits else "不继承"
            ))

        # 条件行：十连保底（如终末地每10抽保底5星）
        if pity.get("multi_pity_size", 0) > 0:
            rows.append((
                "十连保底",
                f"{pity['multi_pity_progress']}/{pity['multi_pity_size']}",
                f"每{pity['multi_pity_size']}抽保底{pity['multi_pity_rarity']}星",
                ""
            ))

        # 条件行：自选/兑换机制（如终末地300抽自选、明日方舟限定300抽兑换）
        if pity.get("exchange_threshold", 0) > 0:
            rows.append((
                "自选/兑换",
                f"{pity['exchange_progress']}/{pity['exchange_threshold']}",
                "累计抽数",
                ""
            ))

        # 设置表格行数（必须先设置行数，才能填充数据）
        self.pity_table.setRowCount(len(rows))
        # 遍历每一行，为每个单元格创建QTableWidgetItem并设置到表格中
        for i, (col1, col2, col3, col4) in enumerate(rows):
            # QTableWidgetItem()构造函数接受字符串参数
            # 即使是数字也需要先转换为字符串
            self.pity_table.setItem(i, 0, QTableWidgetItem(col1))
            self.pity_table.setItem(i, 1, QTableWidgetItem(col2))
            self.pity_table.setItem(i, 2, QTableWidgetItem(col3))
            self.pity_table.setItem(i, 3, QTableWidgetItem(col4))

    def _update_featured(self, stats, game=""):
        """更新50/50统计区域的显示

        参数:
            stats (StatsAnalyzer): 统计分析器实例，提供了get_featured_stats()方法
            game (str): 当前游戏标识符，默认为空字符串

        逻辑说明:
            明日方舟没有50/50机制（不是50%概率出UP角色），因此对明日方舟
            特殊处理，直接显示"无50/50机制"并清空表格。
        """
        # 明日方舟的抽卡机制不包含50/50，隐藏此区域的详细数据
        if game == "arknights":
            self.featured_summary.setText("明日方舟无50/50机制")
            # setRowCount(0)清空表格所有行
            self.featured_table.setRowCount(0)
            return

        # 获取50/50统计数据
        # 返回字典包含: total(总5星数), wins(UP次数), losses(歪次数), win_rate(胜率百分比)
        feat = stats.get_featured_stats()
        # 如果没有5星记录，显示提示信息
        if feat["total"] == 0:
            self.featured_summary.setText("暂无5星记录")
            return

        # 格式化摘要文字，包含总数、UP数、歪数、胜率
        self.featured_summary.setText(
            f"5星总数: {feat['total']}  |  "
            f"UP: {feat['wins']}  |  歪: {feat['losses']}  |  "
            f"UP胜率: {feat['win_rate']}%"
        )

        # 构建50/50统计详情表格行数据
        rows = [
            ("5星总数", str(feat["total"]), ""),
            ("UP次数", str(feat["wins"]), "获得UP角色/武器"),
            ("歪的次数", str(feat["losses"]), "获得非UP"),
            ("UP胜率", f"{feat['win_rate']}%", "理论50%"),
        ]
        self.featured_table.setRowCount(len(rows))
        for i, (c1, c2, c3) in enumerate(rows):
            self.featured_table.setItem(i, 0, QTableWidgetItem(c1))
            self.featured_table.setItem(i, 1, QTableWidgetItem(c2))
            self.featured_table.setItem(i, 2, QTableWidgetItem(c3))

    def _update_pulls(self, records, game=""):
        """更新出货记录表格

        该方法筛选出所有最高星级的获取记录，按时间倒序排列（最新的在最上面），
        并根据游戏类型调整表格列（明日方舟没有UP概念，所以隐藏"是否UP"列）。

        参数:
            records (list): 当前卡池的所有抽卡记录列表，每个元素是一个Record对象，
                          包含 game, pool_type, pool_name, item_name, item_type,
                          rarity, is_featured, time, pity_count, account_id, id 等属性
            game (str): 当前游戏标识符
        """
        # 获取当前游戏的最高星级（原神/星铁/ZZZ/鸣潮=5，明日方舟=6）
        max_rarity = get_max_rarity(game) if game else 5

        # 筛选出最高星级的记录
        # sorted()先按时间排序，相同时间按id排序以保证稳定排序
        # lambda r: (r.time, r.id) 创建元组作为排序键，元组比较是逐元素进行的
        # 列表推导式 [r for r in ... if r.rarity == max_rarity] 筛选最高星级
        five_stars = [
            r for r in sorted(records, key=lambda r: (r.time, r.id))
            if r.rarity == max_rarity
        ]
        # reverse()原地反转列表，使最新获取的记录排在最前面
        five_stars.reverse()

        # 根据游戏类型调整表格列配置
        # 明日方舟没有"是否UP"概念（没有50/50机制），需要调整列
        is_arknights = game == "arknights"
        if is_arknights:
            # 明日方舟：5列（序号、名称、星级、保底计数、卡池名称）
            self.pull_table.setColumnCount(5)
            self.pull_table.setHorizontalHeaderLabels(
                ["序号", "名称", "星级", "保底计数", "卡池"]
            )
            self.pull_table.setColumnWidth(0, 60)
            self.pull_table.setColumnWidth(1, 200)
            self.pull_table.setColumnWidth(2, 110)
            self.pull_table.setColumnWidth(3, 100)
            self.pull_table.setColumnWidth(4, 200)
        else:
            # 其他游戏：6列（序号、名称、星级、是否UP、保底计数、时间）
            self.pull_table.setColumnCount(6)
            self.pull_table.setHorizontalHeaderLabels(
                ["序号", "名称", "星级", "是否UP", "保底计数", "时间"]
            )
            self.pull_table.setColumnWidth(0, 60)
            self.pull_table.setColumnWidth(1, 200)
            self.pull_table.setColumnWidth(2, 110)
            self.pull_table.setColumnWidth(3, 80)
            self.pull_table.setColumnWidth(4, 100)
            self.pull_table.setColumnWidth(5, 200)

        # 设置表格总行数
        self.pull_table.setRowCount(len(five_stars))

        # 逐行填充出货记录
        for i, r in enumerate(five_stars):
            # 第0列：序号（从1开始）
            self.pull_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            # 第1列：物品名称
            self.pull_table.setItem(i, 1, QTableWidgetItem(r.item_name))

            # 第2列：星级，用★符号可视化表示
            # ★ * r.rarity 会生成对应数量的星号，如5星="★★★★★"
            star_item = QTableWidgetItem("★" * r.rarity)
            # 设置星号颜色为橙色(#FF6B35)，使其更醒目
            star_item.setForeground(QColor("#FF6B35"))
            self.pull_table.setItem(i, 2, star_item)

            if is_arknights:
                # 明日方舟的列布局：保底计数 + 卡池名称
                self.pull_table.setItem(
                    i, 3, QTableWidgetItem(str(r.pity_count))
                )
                self.pull_table.setItem(
                    i, 4, QTableWidgetItem(r.pool_name or "")
                )
            else:
                # 其他游戏的列布局：是否UP + 保底计数 + 时间
                # 三元表达式: "是" if r.is_featured else "否"
                self.pull_table.setItem(
                    i, 3, QTableWidgetItem("是" if r.is_featured else "否")
                )
                self.pull_table.setItem(
                    i, 4, QTableWidgetItem(str(r.pity_count))
                )
                # time[:16]截取前16个字符，去掉秒部分（如"2024-01-15 14:30"）
                # 如果time为空则显示空字符串
                self.pull_table.setItem(
                    i, 5, QTableWidgetItem(r.time[:16] if r.time else "")
                )

    def _update_pool_pull_counts(self, account, game):
        """更新卡池抽数显示（预留扩展接口）

        当前实现为空操作(pass)，保留此方法供未来功能扩展使用。
        计划功能：在下拉框选项旁显示每个卡池的总抽数。

        参数:
            account: 当前选中的账号对象
            game (str): 当前游戏标识符
        """
        # pass语句是Python的空操作，方法体不能为空所以需要至少一个语句
        pass

    def _update_toggle_style(self):
        """更新模式切换按钮的视觉样式

        根据当前prob_stack显示的页面索引来更新：
        1. 滑动指示器的位置（左/右）
        2. 两个文字标签的颜色（选中为白色，未选中为灰色）

        该方法在页面初始化和模式切换时被调用。
        """
        # 检查当前堆叠容器显示的是哪个页面
        # currentIndex()返回当前页面的索引，0=表格，1=进度条
        is_table = self.prob_stack.currentIndex() == 0

        # 移动滑动指示器到对应位置
        # 表格模式(0): x=0（左半边），进度条模式(1): x=85（右半边）
        target_x = 0 if is_table else 85
        # setGeometry(x, y, width, height) 移动指示器位置
        self.toggle_indicator.setGeometry(target_x, 4, 85, 24)

        # 更新左侧"表格"标签颜色：选中时白色，未选中时灰色(#666)
        self.toggle_left_label.setStyleSheet(
            f"color: {'white' if is_table else '#666'}; background: transparent;"
        )
        # 更新右侧"进度条"标签颜色：与左侧相反
        self.toggle_right_label.setStyleSheet(
            f"color: {'#666' if is_table else 'white'}; background: transparent;"
        )

    def _switch_prob_mode(self, index):
        """切换概率预测的显示模式

        参数:
            index (int): 目标页面索引，0=表格模式，1=进度条模式
        """
        # setCurrentIndex让堆叠容器显示指定索引的页面
        self.prob_stack.setCurrentIndex(index)
        # 更新切换按钮的视觉样式以匹配新状态
        self._update_toggle_style()

    def _on_slider_changed(self, value):
        """滑动条值变化时的回调函数

        当用户拖动滑块时，该方法被调用以：
        1. 更新当前抽数显示
        2. 计算并显示对应的出货概率
        3. 更新进度条的填充量和颜色

        参数:
            value (int): 滑块当前值（1~90之间的整数，表示第几抽）

        注意：
            该方法在初始化时也会被调用一次（在_update_prob末尾），
            此时self._prob_config可能尚未设置，需要用hasattr检查。
        """
        # 懒导入：在方法内部导入避免循环依赖
        from core.analyzer import get_pull_probability

        # 安全检查：如果保底配置尚未初始化则直接返回
        # hasattr()检查对象是否具有指定属性
        if not hasattr(self, '_prob_config') or not self._prob_config:
            return

        # 获取保存的保底配置和当前保底计数
        config = self._prob_config
        pity = self._prob_pity

        # 更新滑块旁的抽数显示标签
        self.slider_pull_label.setText(f"{value}抽")
        # 更新最大值标签（会随卡池变化）
        self.slider_max_label.setText(str(config.hard_pity))

        # 计算在当前保底基础上再抽value次的累计出货概率
        # get_pull_probability考虑了基础概率、软保底提升、硬保底等因素
        prob = get_pull_probability(config, pity, value)
        # 格式化显示概率百分比，保留1位小数
        self.slider_prob_label.setText(f"出货概率: {prob*100:.1f}%")

        # 更新进度条数值
        # 进度条范围是0~10000，prob是0~1的小数
        # 乘以10000转换为整数（如0.065 -> 650）
        self.slider_prob_bar.setValue(int(prob * 10000))

        # 根据概率值获取对应颜色
        color = self._get_prob_color(prob)
        # 更新概率文字颜色
        self.slider_prob_label.setStyleSheet(f"color: {color};")
        # 更新进度条颜色（需要同时更新轨道和进度块的样式）
        self.slider_prob_bar.setStyleSheet(f"""
            QProgressBar {{
                border: none; border-radius: 15px; background-color: #e0e0e0;
                text-align: center; color: #333; font-size: 12px; font-weight: bold;
            }}
            QProgressBar::chunk {{
                border-radius: 15px; background-color: {color};
            }}
        """)

    def _get_prob_color(self, prob):
        """根据概率值返回对应的颜色代码

        使用交通灯配色方案：
        - 绿色(#4CAF50): 概率较低(0%~50%)，表示"安全"
        - 黄色(#FFC107): 概率中等(50%~80%)，表示"注意"
        - 红色(#F44336): 概率很高(80%~100%)，表示"即将触发"

        参数:
            prob (float): 出货概率，范围0~1

        返回:
            str: 十六进制颜色代码字符串
        """
        if prob <= 0.5:
            # 绿色区间：概率不超过50%
            return "#4CAF50"  # Material Design Green 500
        elif prob <= 0.8:
            # 黄色区间：概率在50%~80%之间
            return "#FFC107"  # Material Design Amber 500
        else:
            # 红色区间：概率超过80%，接近硬保底
            return "#F44336"  # Material Design Red 500

    def _update_prob(self, game, pool_type, records):
        """更新概率预测区域（表格模式和进度条模式）

        该方法根据当前卡池的保底配置，计算并展示不同抽数下的出货概率。
        支持两种展示模式：
        1. 表格模式：以行列形式展示1抽、5抽、10抽...的概率
        2. 进度条模式：通过滑动条交互查看任意抽数的概率

        参数:
            game (str): 当前游戏标识符
            pool_type (str): 当前卡池类型标识符
            records (list): 当前卡池的抽卡记录列表
        """
        # 懒导入避免循环依赖
        from core.analyzer import get_pull_probability

        # 通过游戏和卡池类型查找保底配置
        # BANNER_CONFIGS的key是(game, pool_type)元组
        config = BANNER_CONFIGS.get((game, pool_type))

        if not config:
            # 未找到配置（如全部卡池模式），显示提示信息
            self.prob_table.setRowCount(1)
            self.prob_table.setItem(0, 0, QTableWidgetItem(""))
            self.prob_table.setItem(0, 1, QTableWidgetItem(""))
            self.prob_table.setItem(
                0, 2, QTableWidgetItem("请切换到具体卡池查看概率预测")
            )
            # 清除保存的配置，防止滑块操作出错
            self._prob_config = None
            self._prob_pity = 0
            # 更新滑块区域的提示
            self.slider_context_label.setText("请切换到具体卡池")
            self.slider_prob_label.setText("出货概率: -")
            self.slider_prob_bar.setValue(0)
            return

        # 获取当前卡池名称和保底计数
        pool_name = records[0].pool_name if records else ""
        # get_last_5star_pity()查询数据库获取距离上次出5星已经垫了多少抽
        pity = self.db.get_last_5star_pity(
            records[0].account_id, pool_type, game, pool_name=pool_name
        )

        # 保存配置和保底计数供滑块回调使用
        self._prob_config = config
        self._prob_pity = pity

        # 更新滑动条的范围：最大值设为硬保底数（如原神90抽）
        self.prob_slider.setMaximum(config.hard_pity)
        # 更新最大值标签
        self.slider_max_label.setText(str(config.hard_pity))
        # 更新上下文提示："当前已垫: 30抽 / 保底90抽"
        self.slider_context_label.setText(
            f"当前已垫: {pity}抽 / 保底{config.hard_pity}抽"
        )
        # 更新当前抽数显示
        self.slider_pull_label.setText(f"{self.prob_slider.value()}抽")

        # --- 构建表格模式的数据 ---
        rows = []
        # 遍历常见的抽数节点：1、5、10、20...90
        for t in [1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90]:
            # 如果该抽数超过硬保底数则不显示（如硬保底80抽时跳过90抽）
            if t > config.hard_pity:
                break
            # 计算从当前保底计数再抽t次的累计出货概率
            prob = get_pull_probability(config, pity, t)
            # bar_len是概率条的"填充"长度（总共30个字符宽）
            bar_len = int(prob * 30)
            # 使用█表示已填充部分，░表示未填充部分，形成ASCII概率条
            bar = "█" * bar_len + "░" * (30 - bar_len)
            # 将行数据添加到列表
            rows.append((f"{t}抽", f"{prob*100:.1f}%", bar))

        # 填充表格
        self.prob_table.setRowCount(len(rows))
        for i, (c1, c2, c3) in enumerate(rows):
            self.prob_table.setItem(i, 0, QTableWidgetItem(c1))
            self.prob_table.setItem(i, 1, QTableWidgetItem(c2))
            self.prob_table.setItem(i, 2, QTableWidgetItem(c3))

        # 初始化滑动条的显示（使用当前滑块值触发一次更新）
        self._on_slider_changed(self.prob_slider.value())
