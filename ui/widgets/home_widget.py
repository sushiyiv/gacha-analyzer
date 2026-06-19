"""首页/总览页面 - 统计与卡池标签页合并

本模块实现抽卡分析器的主首页界面，包含以下核心功能：
- 账号选择与切换
- 按卡池类型分组的统计标签页（全部、角色池、武器池等）
- 每个标签页展示：总抽数、五星数、UP比率、小保底不歪率、平均出金、每UP需抽数
- 出货记录表格（按时间倒序显示抽卡记录）
- 保底进度条（显示距保底所需的抽数）
- 卡池管理对话框（控制卡池的显示/隐藏/排序）
- 星级筛选对话框（控制显示哪些星级的记录）
- 卡片模式（终末地武器池、明日方舟独立寻访按具体卡池名分区块展示）

Qt控件层级关系：
  HomeWidget (QWidget)
  └── QVBoxLayout (主布局)
      ├── QHBoxLayout (账号栏：账号选择 + UID按钮 + 卡池管理 + 星级筛选)
      └── QScrollArea (可滚动区域)
          └── QWidget
              └── QVBoxLayout
                  └── QTabWidget (pool_tabs) - 卡池标签页
                      ├── Tab "全部" → QWidget (统计行 + 表格 + 保底条)
                      ├── Tab "角色池" → QWidget
                      ├── Tab "武器池" → QWidget
                      └── ...

信号/槽连接说明：
  - account_combo.currentIndexChanged → _on_account_changed：切换账号时刷新数据
  - _uid_btn.clicked → _toggle_uid：切换UID的显示/隐藏
  - _pool_plus_btn.clicked → _on_pool_plus_clicked：打开卡池管理对话框
  - _star_filter_btn.clicked → _on_star_filter_clicked：打开星级筛选对话框
  - pool_tabs.currentChanged → _on_tab_changed：标签页切换时刷新数据
"""

# ========== 导入语句 ==========

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QScrollArea, QTabWidget, QTabBar, QProgressBar,
    QPushButton, QDialog, QDialogButtonBox, QListWidget, QListWidgetItem
)
# QWidget: 所有Qt界面组件的基类
# QVBoxLayout: 垂直方向布局管理器，控件从上到下排列
# QHBoxLayout: 水平方向布局管理器，控件从左到右排列
# QLabel: 文本标签控件，用于显示不可编辑的文字
# QFrame: 带边框的容器控件，常用于分组显示
# QTableWidget: 表格控件，支持行列数据展示
# QTableWidgetItem: 表格中的单个单元格项
# QHeaderView: 表格的表头视图，控制列宽调整模式
# QComboBox: 下拉选择框控件
# QScrollArea: 可滚动区域控件，内容超出时自动显示滚动条
# QTabWidget: 标签页容器控件，支持多标签页切换
# QTabBar: 标签页的标签栏
# QProgressBar: 进度条控件
# QPushButton: 按钮控件
# QDialog: 模态对话框基类
# QDialogButtonBox: 标准按钮框（确定/取消）
# QListWidget: 列表控件
# QListWidgetItem: 列表中的单个项

from PySide6.QtCore import Qt, QSize
# Qt: Qt核心常量命名空间（对齐方式、光标形状、数据角色等）
# QSize: 尺寸类，包含宽和高

from PySide6.QtGui import QFont, QColor
# QFont: 字体类，用于设置字体族、大小、粗细等
# QColor: 颜色类，支持多种颜色格式（十六进制、RGB等）

from ui.widgets.game_list import GameListDelegate, GameListWidget, CheckListDelegate
# GameListDelegate: 自定义列表项绘制代理（可能用于带图标等特殊渲染）
# GameListWidget: 自定义列表控件（支持拖拽排序等特殊功能）
# CheckListDelegate: 带复选框的列表项绘制代理，用于在列表项左侧显示勾选状态

import shiboken6
# shiboken6: PySide6的C++/Python绑定库，提供对象生命周期管理
# shiboken6.delete(): 手动删除Qt对象（比Python的del更彻底地释放C++资源）

from core.database import Database
# Database: 数据库访问层，封装了SQLite数据库的增删改查操作

from core.config import Config
# Config: 配置管理类，封装了用户配置的读取和保存（键值对形式）

from core.models import BANNER_CONFIGS, get_max_rarity, get_pity_rarity, get_pool_names, get_mechanic_type
# BANNER_CONFIGS: 卡池配置字典，键为(game, mechanic_type)元组，值包含保底次数等配置
# get_max_rarity(game): 获取指定游戏的最高星级（如原神5星、明日方舟6星）
# get_pity_rarity(game, pool_type): 获取指定游戏/卡池类型触发保底的星级
# get_pool_names(game): 获取指定游戏所有卡池名称列表，返回[(pool_type, display_name), ...]
# get_mechanic_type(game, pool_type, pool_name): 获取指定卡池的保底机制类型


class HomeWidget(QWidget):
    """首页主控件

    作为应用的主页面，聚合了统计概览、卡池数据和记录表格。
    通过 main_window 与父窗口通信，获取当前账号和游戏信息。
    所有数据从 Database 实时查询，每次 refresh() 调用都会重新加载。

    属性说明：
        main_window: 主窗口引用，用于获取当前账号/游戏状态
        db: 数据库实例，用于查询抽卡记录和账号信息
        config: 配置管理实例，用于读写用户偏好设置（卡池可见性、排序、星级筛选等）
        _tabs: list[QWidget] - 所有标签页的widget引用列表
        _current_game: str|None - 当前显示的游戏ID，用于检测游戏切换
        _tab_connected: bool - 标签页变化信号是否已连接（避免重复连接）
        pool_tabs: QTabWidget - 卡池标签页容器
    """

    def __init__(self, main_window):
        """构造函数

        参数：
            main_window: MainWindow实例，是本控件的父窗口，
                        提供 get_current_game()、get_current_account()、
                        set_account()、refresh_all() 等方法
        """
        # 调用QWidget的构造函数，完成C++端的Qt控件初始化
        super().__init__()
        # 保存主窗口引用，后续通过它获取当前游戏/账号状态
        self.main_window = main_window
        # 初始化数据库访问对象，所有数据查询通过此对象完成
        self.db = Database()
        # 初始化配置管理对象，读写用户偏好（卡池显示、排序、星级筛选）
        self.config = Config()
        # 标签页widget引用列表，按顺序存储所有已创建的标签页widget
        self._tabs = []
        # 当前游戏ID，用于检测游戏是否发生了切换（切换时需要重建标签页）
        self._current_game = None
        # 标签页变化信号是否已连接的标志，防止重复连接导致多次刷新
        self._tab_connected = False
        # 调用UI初始化方法，构建所有界面组件
        self._init_ui()

    def _init_ui(self):
        """初始化界面布局

        构建整个首页的界面结构：
        1. 顶部账号栏（账号选择 + UID按钮 + 卡池管理 + 星级筛选）
        2. 可滚动区域内的卡池标签页

        布局结构：
        QVBoxLayout (self)
        ├── QHBoxLayout (account_bar)
        │   ├── QLabel("账号:")
        │   ├── QComboBox (account_combo)
        │   ├── QPushButton (UID按钮)
        │   ├── QPushButton (卡池管理按钮)
        │   ├── QPushButton (星级筛选按钮)
        │   └── addStretch() 弹性空间
        └── QScrollArea
            └── QWidget
                └── QVBoxLayout
                    ├── QTabWidget (pool_tabs)
                    └── addStretch() 底部弹性空间
        """
        # 创建垂直方向的主布局，并绑定到self（HomeWidget）
        # layout.setContentsMargins(0, 0, 0, 0) 设置布局的外边距为0，使内容紧贴窗口边缘
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # ===== 账号选择区域 =====
        # 创建水平布局，用于横向排列账号选择相关控件
        account_bar = QHBoxLayout()
        # "账号:" 标签，提示用户后面的下拉框功能
        account_bar.addWidget(QLabel("账号:"))
        # 账号下拉选择框，用户可在此切换不同账号
        self.account_combo = QComboBox()
        # 设置最小宽度200像素，防止账号名较短时下拉框过窄
        self.account_combo.setMinimumWidth(200)
        # 连接下拉框的 indexChanged 信号到 _on_account_changed 槽函数
        # 当用户选择不同账号时触发，参数 index 是新选中项的索引
        self.account_combo.currentIndexChanged.connect(self._on_account_changed)
        # 将账号下拉框添加到水平布局中
        account_bar.addWidget(self.account_combo)

        # UID显示/隐藏按钮的初始状态：默认显示UID
        self._show_uid = True
        # 创建"隐藏UID"按钮，点击可在显示/隐藏UID之间切换
        self._uid_btn = QPushButton("隐藏UID")
        # 固定按钮高度28像素
        self._uid_btn.setFixedHeight(28)
        # 设置鼠标悬停时显示手型光标，提示可点击
        self._uid_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # 设置按钮样式：小字号灰色文字，无边框
        self._uid_btn.setStyleSheet("font-size: 11px; color: #888;")
        # 连接点击信号到 _toggle_uid 槽函数
        self._uid_btn.clicked.connect(self._toggle_uid)
        # 将UID按钮添加到水平布局
        account_bar.addWidget(self._uid_btn)

        # "卡池管理"按钮，点击后弹出卡池管理对话框
        self._pool_plus_btn = QPushButton("卡池管理")
        # 固定高度28像素
        self._pool_plus_btn.setFixedHeight(28)
        # 设置手型光标
        self._pool_plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # 设置按钮样式：蓝色边框和文字，圆角6px，hover时浅蓝色背景
        self._pool_plus_btn.setStyleSheet("""
            QPushButton {
                font-size: 11px; font-weight: bold; color: #1a73e8;
                border: 1px solid #1a73e8; border-radius: 6px;
                padding: 0 10px;
            }
            QPushButton:hover { background: #e8f0fe; }
        """)
        # 连接点击信号到 _on_pool_plus_clicked 槽函数
        self._pool_plus_btn.clicked.connect(self._on_pool_plus_clicked)
        # 将卡池管理按钮添加到水平布局
        account_bar.addWidget(self._pool_plus_btn)

        # "星级筛选"按钮，点击后弹出星级筛选对话框
        self._star_filter_btn = QPushButton("星级筛选")
        # 固定高度28像素
        self._star_filter_btn.setFixedHeight(28)
        # 设置手型光标
        self._star_filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # 设置按钮样式：与卡池管理按钮相同的蓝色主题
        self._star_filter_btn.setStyleSheet("""
            QPushButton {
                font-size: 11px; font-weight: bold; color: #1a73e8;
                border: 1px solid #1a73e8; border-radius: 6px;
                padding: 0 10px;
            }
            QPushButton:hover { background: #e8f0fe; }
        """)
        # 连接点击信号到 _on_star_filter_clicked 槽函数
        self._star_filter_btn.clicked.connect(self._on_star_filter_clicked)
        # 将星级筛选按钮添加到水平布局
        account_bar.addWidget(self._star_filter_btn)

        # 在水平布局右侧添加弹性空间，使控件靠左对齐
        account_bar.addStretch()
        # 将账号栏水平布局添加到主垂直布局中
        layout.addLayout(account_bar)

        # ===== 滚动区域 =====
        # 创建可滚动区域，当内容超出可视区域时自动显示滚动条
        scroll = QScrollArea()
        # 设置内部widget可自动调整大小以适应滚动区域
        scroll.setWidgetResizable(True)
        # 设置无边框，使滚动区域与周围布局无缝融合
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # 创建滚动区域内部的widget容器
        scroll_widget = QWidget()
        # 在内部widget上创建垂直布局
        scroll_layout = QVBoxLayout(scroll_widget)
        # 设置布局中控件之间的间距为12像素
        scroll_layout.setSpacing(12)

        # ===== 卡池标签页 =====

        # 创建标签页容器控件
        self.pool_tabs = QTabWidget()
        # 设置标签页位于顶部（North）
        self.pool_tabs.setTabPosition(QTabWidget.TabPosition.North)
        # 设置标签页的样式：面板边框、标签样式、选中状态
        self.pool_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #e0e0e0; border-radius: 8px; background: white; }
            QTabBar::tab { padding: 8px 16px; margin-right: 2px; border: 1px solid #e0e0e0;
                          border-bottom: none; border-radius: 8px 8px 0 0; background: #f5f5f5; }
            QTabBar::tab:selected { background: white; font-weight: bold; }
        """)

        # ===== 统计项模板 =====
        # _stat_full: 完整统计项列表，包含所有统计指标
        # 每个元组格式: (key, display_title, color)
        # key: 用于在 _stat_items 字典中查找对应widget的键名
        # display_title: 显示在统计项下方的标题文字
        # color: 统计数值的颜色（十六进制）
        self._stat_full = [("total", "总抽数", "#333"), ("star5", "最高星数", "#FF6B35"),
                           ("up_ratio", "UP/总金数", "#E91E63"), ("win_rate", "小保底不歪率", "#4CAF50"),
                           ("avg_pity", "平均出金", "#FF9800"), ("avg_featured", "每UP需", "#1a73e8")]
        # _stat_simple: 简化统计项列表，只包含基础指标（用于明日方舟等无需显示UP相关统计的游戏）
        self._stat_simple = [("total", "总抽数", "#333"), ("star5", "最高星数", "#FF6B35"),
                             ("avg_pity", "平均出金", "#FF9800")]

        # 将标签页容器添加到滚动区域的布局中
        scroll_layout.addWidget(self.pool_tabs)

        # 以"genshin"（原神）为默认游戏，初始化标签页
        self._rebuild_tabs("genshin")

        # 在底部添加弹性空间，使标签页内容靠上
        scroll_layout.addStretch()
        # 将内部widget设置为滚动区域的内容
        scroll.setWidget(scroll_widget)
        # 将滚动区域添加到主布局
        layout.addWidget(scroll)

    def _create_stat_item(self, title, value, color):
        """创建单个统计项widget

        创建一个包含数值和标题的统计展示项，结构如下：
        ┌─────────┐
        │  value  │  ← 大号加粗彩色数字
        │  title  │  ← 小号灰色标题
        └─────────┘

        参数：
            title (str): 统计项标题文字，如"总抽数"、"平均出金"
            value (str): 初始显示的数值，默认显示"-"表示无数据
            color (str): 数值的颜色，十六进制字符串如"#FF6B35"

        返回：
            QFrame: 包含统计项的frame控件，frame._value_label 属性
                    引用数值label，供后续更新数值时使用

        数据结构：
            frame._value_label = value_label (QLabel)
            通过 frame._value_label.setText() 可以更新显示的数值
        """
        # 创建QFrame作为统计项的容器
        frame = QFrame()
        # 在frame内创建垂直布局
        layout = QVBoxLayout(frame)
        # 设置外边距为0，使内容紧贴frame边界
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建数值显示label
        value_label = QLabel(value)
        # 设置对象名称，便于通过样式表或findChild定位
        value_label.setObjectName("stat_number")
        # 设置样式：颜色、24px字号、加粗
        value_label.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold;")
        # 设置文字居中对齐
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 将数值label添加到布局
        layout.addWidget(value_label)

        # 创建标题显示label
        title_label = QLabel(title)
        # 设置对象名称
        title_label.setObjectName("stat_label")
        # 设置文字居中对齐
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        # 将标题label添加到布局
        layout.addWidget(title_label)

        # 在frame上附加_value_label属性，供外部更新数值使用
        # 这是自定义属性绑定到Qt对象上的模式，Python的动态属性机制
        frame._value_label = value_label
        return frame

    def _create_pool_tab(self, name, pool_type, stat_keys, pity_pools, pool_name_map=None, pool_name_filter=None, pool_names_by_type=None):
        """创建卡池标签页内容（统计行 + 表格 + 保底进度条）

        根据传入参数创建一个完整的标签页widget，包含：
        1. 顶部统计行（总抽数、五星数等统计卡片）
        2. 中间出货记录表格（或卡片模式的scroll区域）
        3. 底部保底进度条

        参数：
            name (str): 标签页显示名称，如"全部"、"角色池"、"武器池"
            pool_type (str|None): 卡池类型标识，如"character"、"weapon"、"standard"
                                  None表示"全部"标签页，包含所有类型的记录
            stat_keys (list[tuple]): 统计项配置列表，每个元组为(key, title, color)
            pity_pools (list[str]|None): 需要显示保底进度条的卡池类型列表
                                         None表示非"全部"标签页，不显示保底条
            pool_name_map (dict|None): 卡池类型到显示名称的映射
                                        如{"character": "角色池", "weapon": "武器池"}
            pool_name_filter (str|None): 卡池名称过滤器，仅在特定pool_name的记录上使用
            pool_names_by_type (dict|None): {pool_type: set(pool_name)} 按类型分组的卡池名集合
                                             用于判断是否启用卡片模式

        返回：
            QWidget: 包含所有子控件的标签页widget，附加以下自定义属性：
                _table: QTableWidget - 记录表格引用
                _stat_items: dict[str, QFrame] - 统计项字典，键为统计项key
                _pity_frames: list[(str, QFrame)] - 保底进度条列表，每项为(pool_type, frame)
                _pool_type: str|None - 本标签页对应的卡池类型
                _pool_name_filter: str|None - 卡池名称过滤器
                _cards_container: QWidget|None - 卡片模式的容器widget
                _active_sub_filter: str|None - 当前激活的子筛选（卡片模式下某个具体卡池名）

        特殊逻辑：
            终末地武器池和明日方舟独立寻访使用卡片模式（按具体卡池名分区块展示）
            其他情况使用普通模式（单表格 + 底部保底进度条）
        """
        # 创建标签页的根widget
        widget = QWidget()
        # 创建垂直布局
        layout = QVBoxLayout(widget)
        # 设置内边距10像素
        layout.setContentsMargins(10, 10, 10, 10)
        # 设置控件间距10像素
        layout.setSpacing(10)

        # ===== 统计行 =====
        # 创建统计行容器frame
        stats_frame = QFrame()
        # 设置对象名为"card"，配合CSS样式表
        stats_frame.setObjectName("card")
        # 在frame内创建水平布局，统计项横向排列
        stats_layout = QHBoxLayout(stats_frame)
        # 设置内边距：左20 上10 右20 下10
        stats_layout.setContentsMargins(20, 10, 20, 10)
        # 设置统计项之间的间距为40像素
        stats_layout.setSpacing(40)

        # 遍历统计项配置，为每项创建widget
        stat_items = {}
        for key, title, color in stat_keys:
            # 调用 _create_stat_item 创建统计项，初始值为"-"
            item = self._create_stat_item(title, "-", color)
            # 将统计项添加到水平布局
            stats_layout.addWidget(item)
            # 将统计项存入字典，键为统计项key，方便后续通过key更新数值
            stat_items[key] = item

        # 在统计行右侧添加弹性空间，使统计项靠左排列
        stats_layout.addStretch()
        # 将统计行添加到标签页布局
        layout.addWidget(stats_frame)

        # ===== 卡片模式判断 =====
        # 只有终末地武器池和明日方舟独立寻访使用卡片模式（按具体卡池名分区块）
        # has_multiple_pools 标记是否使用卡片模式
        has_multiple_pools = False
        # cards_container 是卡片模式的滚动容器，非卡片模式时为None
        cards_container = None
        # 获取当前选中的游戏
        current_game = self.main_window.get_current_game()
        # 判断是否需要使用卡片模式：
        # 终末地的武器池 或 明日方舟的限定池（独立寻访）
        use_card_mode = (current_game == "endfield" and pool_type == "weapon") or \
                        (current_game == "arknights" and pool_type == "limited")
        # 如果需要卡片模式，且该类型下有具体的pool_name
        if use_card_mode and pool_names_by_type and pool_type in pool_names_by_type:
            pool_names = pool_names_by_type[pool_type]
            # 至少有1个具体的pool_name才启用卡片模式
            if len(pool_names) >= 1:
                has_multiple_pools = True
                # 创建卡片区域的滚动容器
                cards_scroll = QScrollArea()
                cards_scroll.setWidgetResizable(True)
                cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
                # 创建卡片容器widget
                cards_container = QWidget()
                # 卡片容器内的垂直布局，每个卡片占一行
                cards_layout = QVBoxLayout(cards_container)
                cards_layout.setContentsMargins(0, 0, 0, 0)
                cards_layout.setSpacing(12)
                # 将卡片容器设置为滚动区域的内容
                cards_scroll.setWidget(cards_container)
                # 将滚动区域添加到标签页布局，stretch=1表示占据剩余空间
                layout.addWidget(cards_scroll, 1)

        # ===== 出货记录表格（仅非卡片模式使用） =====
        # 创建表格控件
        table = QTableWidget()
        # 根据游戏设置表格列数和列标题
        current_game = self.main_window.get_current_game()
        if current_game == "arknights":
            # 明日方舟的表格有5列：序号、名称、星级、保底计数、卡池
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(["序号", "名称", "星级", "保底计数", "卡池"])
            header = table.horizontalHeader()
            # 固定宽度：序号列50px，星级列110px，保底计数列80px
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
            table.setColumnWidth(0, 50)
            table.setColumnWidth(2, 110)
            table.setColumnWidth(3, 80)
        else:
            # 其他游戏的表格有6列：序号、名称、星级、是否UP、保底计数、时间
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(["序号", "名称", "星级", "是否UP", "保底计数", "时间"])
            header = table.horizontalHeader()
            # 固定宽度设置
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
            table.setColumnWidth(0, 50)
            table.setColumnWidth(2, 110)
            table.setColumnWidth(3, 70)
            table.setColumnWidth(4, 80)

        # 禁止编辑表格内容（只读模式）
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        # 设置点击行为：选中整行而非单个单元格
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        # 隐藏行号列（左侧的数字列），因为我们已在第一列显示序号
        table.verticalHeader().setVisible(False)
        # 设置表格最小高度200像素，防止无数据时表格过小
        table.setMinimumHeight(200)
        # 设置最后一列自动拉伸填满剩余宽度
        table.horizontalHeader().setStretchLastSection(True)

        # ===== 保底进度条（仅非卡片模式） =====
        # 保底进度条列表，每项为(pool_type, frame)元组
        pity_frames = []
        # 只有非卡片模式才添加表格和保底条
        if not has_multiple_pools:
            # 将表格添加到标签页布局
            layout.addWidget(table)

            # 卡池类型到默认显示名称的映射（当 pool_name_map 未提供时使用）
            fallback_names = {"character": "角色池", "weapon": "武器池", "standard": "常驻池",
                              "standard_character": "常驻角色", "standard_weapon": "常驻武器", "collab": "联动池"}
            # 优先使用传入的pool_name_map，否则用默认映射
            name_map = pool_name_map or fallback_names
            # pity_pools不为None时才创建保底条
            # pity_pools为None表示非"全部"标签页，该标签页对应单一卡池类型，不需要保底条
            if pity_pools is not None:
                # 确定需要显示的卡池类型列表
                pools_to_show = pity_pools if pity_pools else ["character", "weapon", "standard"]
                # 为每个需要显示保底进度的卡池类型创建进度条
                for p_type in pools_to_show:
                    # 调用 _create_pity_bar 创建保底进度条widget
                    pf = self._create_pity_bar(name_map.get(p_type, p_type))
                    # 将进度条添加到标签页布局
                    layout.addWidget(pf)
                    # 保存(pool_type, frame)引用对，方便后续更新
                    pity_frames.append((p_type, pf))

        # ===== 保存引用到widget的自定义属性 =====
        # 这些属性在后续 refresh() 时会被读取和更新
        widget._table = table  # 记录表格引用
        widget._stat_items = stat_items  # 统计项字典 {key: frame}
        widget._pity_frames = pity_frames  # 保底进度条列表 [(pool_type, frame)]
        widget._pool_type = pool_type  # 本标签页对应的卡池类型（None=全部）
        widget._pool_name_filter = pool_name_filter  # 卡池名称过滤器
        widget._cards_container = cards_container  # 卡片模式容器（非卡片模式为None）
        widget._active_sub_filter = None  # 当前激活的子筛选（卡片模式下某个具体卡池名）

        return widget

    def _create_pool_card(self, pool_name, pool_type, game, records, account, star_filter, max_rarity):
        """为单个具体卡池创建卡片区块（卡片模式专用）

        在卡片模式下，每个具体的pool_name（如"限定寻访-XXX"）会生成一个独立的卡片，
        卡片内包含：卡池名称、统计行（最高星数、平均出金、已垫抽数）和记录表格。

        参数：
            pool_name (str): 具体的卡池名称，如"限定寻访-深眠"
            pool_type (str): 卡池类型，如"weapon"、"limited"
            game (str): 游戏ID，如"endfield"、"arknights"
            records (list[GachaRecord]): 该卡池的所有抽卡记录
            account (Account): 当前账号对象
            star_filter (list[int]): 星级筛选列表，如[5, 6]，控制表格显示哪些星级
            max_rarity (int): 游戏最高星级

        返回：
            tuple: (card_frame, stat_refs)
                card_frame (QFrame): 卡片容器frame
                stat_refs (dict): 统计值引用 {"star": val_star_label, "avg": val_avg_label}

        内部逻辑：
            1. 创建卡片容器和布局
            2. 添加卡池名称标题
            3. 计算并展示统计行（五星数、平均出金、已垫抽数）
            4. 创建并填充记录表格（按星级筛选过滤）
            5. 自动计算表格高度（最多5行）
        """
        # 创建卡片容器frame
        card = QFrame()
        # 设置对象名为"card"，用于CSS样式匹配
        card.setObjectName("card")
        # 设置卡片样式：白背景、灰色边框、圆角8px
        card.setStyleSheet("""
            QFrame#card {
                background: white; border: 1px solid #e0e0e0;
                border-radius: 8px; padding: 0px;
            }
        """)
        # 创建卡片内的垂直布局
        card_layout = QVBoxLayout(card)
        # 设置内边距：左16 上12 右16 下12
        card_layout.setContentsMargins(16, 12, 16, 12)
        # 设置控件间距8像素
        card_layout.setSpacing(8)

        # ===== 卡池名称标题 =====
        name_label = QLabel(pool_name)
        # 设置字体：微软雅黑，14号，加粗
        name_label.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        # 设置样式：深灰色文字，无边框（覆盖卡片的border样式）
        name_label.setStyleSheet("color: #333; border: none;")
        # 将标题添加到卡片布局
        card_layout.addWidget(name_label)

        # ===== 统计行 =====
        # 按时间和ID排序记录（确保时间顺序一致）
        sorted_records = sorted(records, key=lambda r: (r.time, r.id))
        # 计算总记录数
        total = len(records)
        # 筛选出最高星级的记录（五星或六星，取决于游戏）
        five_stars = [r for r in sorted_records if r.rarity == max_rarity]
        # 计算最高星数记录的总数
        star5_count = len(five_stars)

        # 创建统计行的水平布局
        stats_row = QHBoxLayout()
        stats_row.setSpacing(24)

        # 内部辅助函数：在统计行中添加一个统计项
        def _add_stat(label, value, color="#333"):
            """在统计行中添加一个统计项（数值 + 标题）

            参数：
                label (str): 标题文字，如"★"、"平均出金"
                value (str): 显示的数值，如"12"、"68.5抽"
                color (str): 数值颜色，默认深灰色

            返回：
                QLabel: 数值label引用，可后续更新
            """
            frame = QFrame()
            frame.setStyleSheet("border: none;")
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(0, 0, 0, 0)
            fl.setSpacing(2)
            # 数值label
            val = QLabel(value)
            val.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: bold;")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            # 标题label
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #888; font-size: 11px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fl.addWidget(val)
            fl.addWidget(lbl)
            stats_row.addWidget(frame)
            return val

        # 添加最高星数统计项（如"★★★★★★"对应6星，显示个数）
        star_label = "★" * max_rarity
        val_star = _add_stat(star_label, str(star5_count), "#FF6B35")

        # 计算平均出金抽数（总抽数 / 最高星数记录数）
        if star5_count > 0:
            avg_pity = f"{round(total / star5_count, 1)}抽"
        else:
            avg_pity = "-"

        # 添加平均出金统计项
        val_avg = _add_stat("平均出金", avg_pity, "#FF9800")

        # ===== 已垫抽数（距上次出金的抽数） =====
        # 获取当前卡池的保底机制类型
        mechanic_type = get_mechanic_type(game, pool_type, pool_name)
        # 先尝试用机制类型查找配置
        config = BANNER_CONFIGS.get((game, mechanic_type))
        # 如果找不到，回退到用pool_type查找
        if not config:
            config = BANNER_CONFIGS.get((game, pool_type))
        # 只有在有配置的情况下才显示已垫抽数
        if config:
            # 查询数据库获取距上次出金的抽数
            pity = self.db.get_last_5star_pity(account.id, pool_type, game, pool_name=pool_name)
            _add_stat("已垫", f"{pity}抽", "#1a73e8")

        # 在统计行右侧添加弹性空间
        stats_row.addStretch()
        # 将统计行添加到卡片布局
        card_layout.addLayout(stats_row)

        # ===== 记录表格 =====
        table = QTableWidget()
        if game == "arknights":
            # 明日方舟：4列（序号、名称、星级、时间）
            table.setColumnCount(4)
            table.setHorizontalHeaderLabels(["序号", "名称", "星级", "时间"])
            h = table.horizontalHeader()
            h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            h.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            h.setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
            table.setColumnWidth(0, 50)
            table.setColumnWidth(2, 110)
        else:
            # 其他游戏：5列（序号、名称、星级、是否UP、时间）
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(["序号", "名称", "星级", "是否UP", "时间"])
            h = table.horizontalHeader()
            h.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            h.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            h.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            h.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
            h.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
            table.setColumnWidth(0, 50)
            table.setColumnWidth(2, 110)
            table.setColumnWidth(3, 70)
        # 禁止编辑、选中整行、隐藏行号
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)

        # 根据星级筛选过滤记录
        filtered = [r for r in sorted_records if r.rarity in star_filter]
        # 反转顺序，最新的记录显示在最上面
        filtered.reverse()
        # 设置表格行数
        table.setRowCount(len(filtered))

        # ===== 自动计算表格高度 =====
        row_height = 28  # 每行高度28像素
        header_height = 32  # 表头高度32像素
        # 最多显示5行，少于5行按实际高度
        visible_rows = min(len(filtered), 5)
        if visible_rows > 0:
            table.setFixedHeight(header_height + row_height * visible_rows)
        else:
            # 无数据时也保留一行的高度（显示空表头）
            table.setFixedHeight(header_height + row_height)

        # 星级颜色映射：3星灰色、4星紫色、5星金色、6星橙色
        star_colors = {3: "#888", 4: "#9B59B6", 5: "#FFD700", 6: "#FF6B35"}
        # 填充表格数据
        for i, r in enumerate(filtered):
            # 第0列：序号（从1开始）
            table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            # 第1列：物品名称
            table.setItem(i, 1, QTableWidgetItem(r.item_name))
            # 第2列：星级（用★符号表示）
            si = QTableWidgetItem("★" * r.rarity)
            # 设置星级颜色
            si.setForeground(QColor(star_colors.get(r.rarity, "#FF6B35")))
            table.setItem(i, 2, si)
            if game == "arknights":
                # 明日方舟：第3列是时间（截取到分钟，忽略秒）
                table.setItem(i, 3, QTableWidgetItem(r.time[:16] if r.time else ""))
            else:
                # 其他游戏：第3列是是否UP
                ui = QTableWidgetItem("是" if r.is_featured else "否")
                ui.setForeground(QColor("#FF6B35" if r.is_featured else "#4CAF50"))
                table.setItem(i, 3, ui)
                # 第4列是时间
                table.setItem(i, 4, QTableWidgetItem(r.time[:16] if r.time else ""))

        # 将表格添加到卡片布局
        card_layout.addWidget(table)

        # 返回卡片frame和统计值引用字典
        return card, {"star": val_star, "avg": val_avg}

    def _create_pity_bar(self, pool_name):
        """创建保底进度条widget

        为指定卡池创建一个包含标题和进度条的保底展示区域，结构如下：
        ┌─────────────────────────────────────┐
        │ 角色池              0/90             │  ← 标题行
        │ ████████░░░░░░░░░░░░  45/90         │  ← 进度条
        └─────────────────────────────────────┘

        参数：
            pool_name (str): 卡池显示名称，如"角色池"、"武器池"

        返回：
            QFrame: 包含保底信息的frame，附加以下自定义属性：
                _pity_text (QLabel): 保底文字标签，显示"已垫X抽 / 保底Y抽"
                _progress (QProgressBar): 进度条控件，显示当前保底进度
        """
        # 创建容器frame
        frame = QFrame()
        frame.setObjectName("card")
        # 创建垂直布局
        layout = QVBoxLayout(frame)
        # 设置内边距
        layout.setContentsMargins(15, 10, 15, 10)

        # ===== 标题行 =====
        title_layout = QHBoxLayout()
        # 卡池名称标签
        title_label = QLabel(pool_name)
        title_label.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        title_layout.addWidget(title_label)

        # 保底进度文字标签，初始显示"0/90"
        pity_text = QLabel("0/90")
        pity_text.setFont(QFont("Microsoft YaHei", 11))
        title_layout.addWidget(pity_text)

        # 右侧弹性空间，使标题和进度文字分布在两端
        title_layout.addStretch()
        layout.addLayout(title_layout)

        # ===== 进度条 =====
        progress = QProgressBar()
        # 固定高度20像素
        progress.setFixedHeight(20)
        # 启用进度条上的文字显示
        progress.setTextVisible(True)
        # 设置文字格式：显示当前值/最大值（如"45/90"）
        progress.setFormat("%v/%m")
        # 设置进度条样式：无边框、圆角、灰色背景、蓝色填充
        progress.setStyleSheet("""
            QProgressBar {
                border: none;
                border-radius: 10px;
                background-color: #e0e0e0;
                text-align: center;
                color: #333;
                font-size: 11px;
                font-weight: bold;
            }
            QProgressBar::chunk {
                border-radius: 10px;
                background-color: #1a73e8;
            }
        """)
        layout.addWidget(progress)

        # 在frame上附加引用属性，方便外部更新保底数据
        frame._pity_text = pity_text  # 保底文字标签
        frame._progress = progress  # 进度条控件
        return frame

    def _toggle_uid(self):
        """切换UID显示/隐藏状态

        每次点击按钮时切换 _show_uid 的布尔值，
        然后更新按钮文字，并调用 refresh() 刷新整个页面
        （刷新时会根据 _show_uid 决定账号列表中是否显示UID）。
        """
        # 切换显示状态（True ↔ False）
        self._show_uid = not self._show_uid
        # 根据新状态更新按钮文字
        self._uid_btn.setText("隐藏UID" if self._show_uid else "显示UID")
        # 刷新页面，使账号列表中的UID显示/隐藏生效
        self.refresh()

    def _on_account_changed(self, index):
        """账号下拉框选择变化的槽函数

        当用户从下拉框中选择不同账号时被调用。

        参数：
            index (int): 新选中项的索引（未使用，通过currentData获取账号ID）
        """
        # 获取当前选中项关联的账号ID（通过addItem的data参数设置）
        account_id = self.account_combo.currentData()
        # 如果有有效的账号ID
        if account_id:
            # 从数据库查询完整的账号对象
            account = self.db.get_account_by_id(account_id)
            # 通知主窗口切换当前账号
            self.main_window.set_account(account)
            # 刷新页面数据
            self.refresh()

    def _rebuild_tabs(self, game, account=None):
        """根据游戏重建标签页

        当切换游戏时，需要销毁所有旧标签页并根据新游戏的卡池配置重新创建。
        这是最重的UI操作，会阻塞信号避免中间状态的闪烁。

        参数：
            game (str): 目标游戏ID，如"genshin"、"starrail"
            account (Account|None): 当前账号，用于查询已有记录的pool_name信息

        内部流程：
            1. 阻塞标签页信号，防止重建过程中触发不必要的刷新
            2. 保存旧标签页引用，清空标签页容器
            3. 逐个销毁旧标签页（shiboken6.delete释放C++资源）
            4. 读取用户的卡池显示/排序配置
            5. 按用户配置顺序筛选可见卡池
            6. 查询已有记录，收集各pool_type下出现过的pool_name
            7. 创建"全部"标签页
            8. 为每个可见的卡池类型创建独立标签页
            9. 恢复信号，连接标签页切换信号（仅首次）

        数据结构：
            pool_names_by_type: dict[str, set[str]]
                键为pool_type（如"character"），值为该类型下出现过的所有pool_name集合
                用于判断是否需要使用卡片模式
        """
        # 阻塞QTabWidget的信号，避免clear()和addTab()过程中触发currentChanged
        self.pool_tabs.blockSignals(True)
        # 保存旧标签页列表的副本（用于后续销毁）
        old_tabs = list(self._tabs)
        # 清空标签页引用列表
        self._tabs.clear()
        # 清空QTabWidget中的所有标签页（这会从UI移除但不删除widget）
        self.pool_tabs.clear()

        # ===== 强制释放旧标签页 =====
        # 遍历旧标签页，手动清理并释放
        for tab in old_tabs:
            # 清空统计项引用
            tab._stat_items.clear()
            # 清空保底进度条引用
            tab._pity_frames.clear()
            # 断开表格引用
            tab._table = None
            # 移除父子关系（从widget树中断开）
            tab.setParent(None)
            # 使用shiboken6.delete()手动释放C++端的Qt对象内存
            # Python的gc不会自动调用delete，必须显式释放
            shiboken6.delete(tab)

        # ===== 读取用户的卡池显示/排序配置 =====
        # 获取当前游戏所有卡池名称，返回[(pool_type, display_name), ...]
        all_pools = get_pool_names(game)
        # 从配置中读取用户设置的可见卡池列表
        # 默认值为所有卡池都可见
        visible_pools = self.config.get(f"pool_visible.{game}", [pt for pt, _ in all_pools])
        # 从配置中读取用户设置的卡池排序顺序
        # 默认值为所有卡池按原始顺序排列
        pool_order = self.config.get(f"pool_order.{game}", [pt for pt, _ in all_pools])
        # 将卡池列表转为字典：{pool_type: display_name}
        pool_name_map = dict(all_pools)

        # ===== 按用户顺序筛选可见卡池 =====
        ordered_pools = []
        # 先按用户自定义顺序添加可见的卡池
        for pt in pool_order:
            if pt in visible_pools and pt in pool_name_map:
                ordered_pools.append((pt, pool_name_map[pt]))
        # 再补充不在用户顺序中但可见的卡池（兜底）
        for pt, name in all_pools:
            if pt not in [p for p, _ in ordered_pools] and pt in visible_pools:
                ordered_pools.append((pt, name))

        # ===== 查询已有记录，按 pool_type 分组收集 pool_name =====
        pool_names_by_type = {}  # {pool_type: set(pool_name)}
        if account:
            # 获取该账号的所有抽卡记录
            existing = self.db.get_records(account.id)
            for r in existing:
                # 如果记录有pool_name字段（独立寻访等场景）
                if r.pool_name:
                    # 将pool_name添加到对应pool_type的集合中
                    pool_names_by_type.setdefault(r.pool_type, set()).add(r.pool_name)

        # ===== "全部"标签页 =====
        all_pool_types = [pt for pt, _ in ordered_pools]
        # 明日方舟使用简化统计（不显示UP/总金数、小保底不歪率、每UP需）
        if game == "arknights":
            stat_keys = self._stat_simple
        else:
            stat_keys = self._stat_full
        # 创建"全部"标签页：pool_type=None表示包含所有类型的记录
        tab = self._create_pool_tab("全部", None, stat_keys, all_pool_types, pool_name_map, pool_names_by_type=pool_names_by_type)
        self._tabs.append(tab)
        # 将标签页添加到QTabWidget，标签标题为"全部"
        self.pool_tabs.addTab(tab, "全部")

        # ===== 各卡池独立标签页 =====
        for pool_type, name in ordered_pools:
            # 明日方舟全部使用简化统计
            if game == "arknights":
                stat_keys = self._stat_simple
            else:
                # 角色池和武器池使用完整统计，其他卡池使用简化统计
                stat_keys = self._stat_full if pool_type in ("character", "weapon") else self._stat_simple
            # 获取该pool_type下出现过的所有pool_name
            pool_names = pool_names_by_type.get(pool_type, set())
            # 创建卡池标签页：pity_pools=None表示非"全部"标签页，不创建保底条
            tab = self._create_pool_tab(name, pool_type, stat_keys, None, pool_name_map, pool_names_by_type=pool_names_by_type)
            self._tabs.append(tab)
            self.pool_tabs.addTab(tab, name)

        # 恢复标签页信号
        self.pool_tabs.blockSignals(False)

        # 只连接一次信号，避免多次调用 _rebuild_tabs 导致重复连接
        # 重复连接会导致一次tab切换触发多次 _on_tab_changed 调用
        if not self._tab_connected:
            # currentChanged 信号在标签页切换时发射，参数为新标签页索引
            self.pool_tabs.currentChanged.connect(self._on_tab_changed)
            self._tab_connected = True

    def _on_pool_plus_clicked(self):
        """点击"卡池管理"按钮，弹出卡池管理对话框

        流程：
            1. 记录当前可见卡池和排序配置（用于比较是否发生了变化）
            2. 弹出对话框让用户修改
            3. 对话框关闭后比较新旧配置
            4. 如果有变化，暂停UI更新→重建标签页→恢复UI→定位到之前的标签页
        """
        # 获取当前游戏ID
        game = self.main_window.get_current_game()
        # 记录当前选中的标签页索引
        current_tab = self.pool_tabs.currentIndex()
        # 获取当前标签页对应的pool_type（用于对话框关闭后恢复位置）
        current_pool_type = self._tabs[current_tab]._pool_type if current_tab < len(self._tabs) else None

        # 保存修改前的配置快照
        old_visible = self.config.get(f"pool_visible.{game}", [])
        old_order = self.config.get(f"pool_order.{game}", [])

        # 弹出卡池管理对话框（模态，阻塞直到关闭）
        self._show_pool_manager(game)

        # 读取修改后的配置
        new_visible = self.config.get(f"pool_visible.{game}", [])
        new_order = self.config.get(f"pool_order.{game}", [])
        # 如果配置没有变化，直接返回
        if old_visible == new_visible and old_order == old_order:
            return  # 没改动

        # ===== 有改动，重建标签页 =====
        # 暂停UI更新，避免重建过程中的视觉闪烁
        self.setUpdatesEnabled(False)
        # 重置当前游戏标记，强制 _rebuild_tabs 执行重建
        self._current_game = None
        # 调用refresh()，内部会检测到游戏变化并调用 _rebuild_tabs
        self.refresh()

        # ===== 恢复标签页位置 =====
        # 如果之前的卡池被隐藏了，跳到"全部"标签页
        if current_pool_type is not None and current_pool_type not in new_visible:
            self.pool_tabs.setCurrentIndex(0)
        # 如果之前的卡池仍然可见，定位到对应的标签页
        elif current_pool_type is not None:
            for i, tab in enumerate(self._tabs):
                if tab._pool_type == current_pool_type:
                    self.pool_tabs.setCurrentIndex(i)
                    break

        # 恢复UI更新
        self.setUpdatesEnabled(True)

    def _on_tab_changed(self, index):
        """标签页切换事件的槽函数

        当用户点击不同标签页时触发，刷新当前标签页的数据。

        参数：
            index (int): 新选中的标签页索引
        """
        # 检查索引在有效范围内
        if 0 <= index < self.pool_tabs.count():
            # 刷新所有标签页数据（refresh内部会更新所有标签页）
            self.refresh()

    def _show_pool_manager(self, game):
        """显示卡池管理对话框

        弹出一个模态对话框，允许用户：
            - 通过勾选/取消勾选控制每个卡池的显示/隐藏
            - 通过拖拽调整卡池标签页的排序顺序

        参数：
            game (str): 当前游戏ID

        对话框结构：
            QDialog
            ├── QLabel (提示文字)
            ├── GameListWidget (带勾选框和拖拽排序的列表)
            │   ├── QListWidgetItem "角色池" (可勾选、可拖拽)
            │   ├── QListWidgetItem "武器池"
            │   └── ...
            └── QDialogButtonBox (确定/取消)

        数据结构：
            每个QListWidgetItem的UserRole存储pool_type标识
            UserRole + 1 存储布尔值，表示该卡池是否可见
        """
        # 获取游戏所有卡池配置
        all_pools = get_pool_names(game)
        # 设置默认值：所有卡池可见，按原始顺序排列
        default_visible = [pt for pt, _ in all_pools]
        default_order = [pt for pt, _ in all_pools]
        # 读取用户配置
        current_visible = self.config.get(f"pool_visible.{game}", default_visible)
        current_order = self.config.get(f"pool_order.{game}", default_order)
        pool_name_map = dict(all_pools)

        # 确保所有卡池都在顺序列表中（可能有新增卡池）
        for pt, _ in all_pools:
            if pt not in current_order:
                current_order.append(pt)

        # 创建模态对话框，parent=self 确保对话框居中于首页
        dialog = QDialog(self)
        dialog.setWindowTitle("卡池管理")
        dialog.setMinimumWidth(300)
        dialog.setMinimumHeight(350)
        layout = QVBoxLayout(dialog)

        # 提示文字
        header = QLabel("点击选择/取消，长按拖动排序:")
        header.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px;")
        layout.addWidget(header)

        # 创建带勾选框和拖拽排序功能的自定义列表控件
        list_widget = GameListWidget()
        # 设置拖拽模式为内部移动（列表项之间拖拽排序）
        list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        # 设置默认拖拽动作为移动（而非复制）
        list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        # 设置自定义的列表项代理，用于绘制勾选框
        list_widget.setItemDelegate(CheckListDelegate(list_widget))
        # 设置列表样式
        list_widget.setStyleSheet("QListWidget { background-color: #ffffff; border: 1px solid #e0e0e0; }")

        # 按当前顺序填充列表项
        for pt in current_order:
            if pt in pool_name_map:
                # 创建列表项，显示卡池名称
                item = QListWidgetItem(pool_name_map[pt])
                # 禁用Qt自带的checkable标记（使用自定义delegate绘制勾选框）
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                # UserRole存储pool_type标识，用于保存时识别
                item.setData(Qt.ItemDataRole.UserRole, pt)
                # UserRole + 1 存储可见性状态（布尔值）
                item.setData(Qt.ItemDataRole.UserRole + 1, pt in current_visible)
                list_widget.addItem(item)

        # 将列表控件添加到对话框布局
        layout.addWidget(list_widget)

        # 添加确定/取消按钮
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        # accepted信号连接到dialog.accept()，关闭对话框并返回Accepted
        buttons.accepted.connect(dialog.accept)
        # rejected信号连接到dialog.reject()，关闭对话框并返回Rejected
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        # 执行模态对话框，等待用户操作
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 用户点击了确定，保存新的配置
            new_order = []
            new_visible = []
            # 遍历列表中的所有项，获取新的顺序和可见性
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                # 获取pool_type标识
                pt = item.data(Qt.ItemDataRole.UserRole)
                new_order.append(pt)
                # 获取可见性状态
                if item.data(Qt.ItemDataRole.UserRole + 1):
                    new_visible.append(pt)
            # 保存新的排序顺序
            self.config.set(f"pool_order.{game}", new_order)
            # 保存新的可见性列表；如果全部隐藏则至少保留第一个
            self.config.set(f"pool_visible.{game}", new_visible if new_visible else [new_order[0]])
            # 持久化配置到文件
            self.config.save()

    def _refresh_cards(self, tab, records, account, game, max_rarity, star_filter):
        """刷新卡片模式的内容

        在卡片模式下，按 pool_name 分组记录，为每个具体卡池创建独立的卡片widget。
        卡片按最新记录时间倒序排列（最近有记录的卡池在最上面）。

        参数：
            tab (QWidget): 当前标签页widget，需要包含 _cards_container 属性
            records (list[GachaRecord]): 当前标签页的所有记录（已按pool_type筛选）
            account (Account): 当前账号对象
            game (str): 游戏ID
            max_rarity (int): 最高星级
            star_filter (list[int]): 星级筛选列表

        内部逻辑：
            1. 清空卡片容器中的所有旧卡片
            2. 按 pool_name 分组记录
            3. 按最新记录时间倒序排列各组
            4. 为每个组调用 _create_pool_card 创建卡片widget
        """
        # 获取卡片容器引用
        cards_container = tab._cards_container
        if not cards_container:
            return

        # ===== 清空旧卡片 =====
        layout = cards_container.layout()
        # 循环取出布局中的所有子项并删除
        while layout.count():
            child = layout.takeAt(0)
            # takeAt返回QLayoutItem，需要检查是否是widget
            if child.widget():
                # 使用deleteLater()安全删除（在事件循环结束时删除，避免崩溃）
                child.widget().deleteLater()

        # ===== 按 pool_name 分组 =====
        groups = {}
        for r in records:
            # 如果记录没有pool_name，使用"未知卡池"作为默认分组名
            pn = r.pool_name or "未知卡池"
            # 使用setdefault方法，首次遇到某pool_name时创建空列表
            groups.setdefault(pn, []).append(r)

        # 没有数据时显示占位文字
        if not groups:
            no_data = QLabel("暂无数据")
            no_data.setStyleSheet("color: #999; font-size: 13px; padding: 40px;")
            no_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(no_data)
            return

        pool_type = tab._pool_type

        # ===== 按最新记录时间倒序排列 =====
        def _latest_time(recs):
            """获取一组记录中最新的时间戳字符串"""
            times = [r.time for r in recs if r.time]
            return max(times) if times else ""

        # 按最新时间倒序排列，最近有记录的卡池排在最上面
        sorted_groups = sorted(groups.items(), key=lambda x: _latest_time(x[1]), reverse=True)

        # 为每个卡池创建卡片widget
        for pn, pool_records in sorted_groups:
            card, stat_refs = self._create_pool_card(
                pn, pool_type, game, pool_records, account, star_filter, max_rarity
            )
            layout.addWidget(card)

        # 底部添加弹性空间
        layout.addStretch()

    def _refresh_tab(self, tab):
        """刷新单个标签页的数据

        这是刷新单个标签页的入口方法，负责：
            1. 获取当前账号和游戏
            2. 查询数据库获取所有记录
            3. 根据标签页的pool_type和pool_name_filter筛选记录
            4. 根据是否为卡片模式调用不同的刷新方法

        参数：
            tab (QWidget): 要刷新的标签页widget

        数据筛选逻辑：
            - pool_type is None → 使用所有记录（"全部"标签页）
            - active_sub_filter 存在 → 按pool_type和pool_name精确筛选（卡片模式子筛选）
            - pool_name_filter 存在 → 按pool_type和pool_name筛选
            - 否则 → 仅按pool_type筛选
        """
        # 获取当前账号
        account = self.main_window.get_current_account()
        if not account:
            return
        # 获取当前游戏
        game = self.main_window.get_current_game()
        # 查询该账号的所有抽卡记录
        all_records = self.db.get_records(account.id)
        # 获取最高星级
        max_rarity = get_max_rarity(game)
        # 获取星级筛选配置
        star_filter = self._get_star_filter(game)

        # 获取标签页的筛选参数
        pool_type = tab._pool_type
        pool_name_filter = getattr(tab, '_pool_name_filter', None)
        active_sub_filter = getattr(tab, '_active_sub_filter', None)

        # 根据筛选参数过滤记录
        if pool_type is None:
            # "全部"标签页：使用所有记录
            records = all_records
        elif active_sub_filter:
            # 有子筛选：同时按pool_type和pool_name精确匹配
            records = [r for r in all_records if r.pool_type == pool_type and r.pool_name == active_sub_filter]
        elif pool_name_filter:
            # 有pool_name过滤器：按pool_type和pool_name匹配
            records = [r for r in all_records if r.pool_type == pool_type and r.pool_name == pool_name_filter]
        else:
            # 仅按pool_type筛选
            records = [r for r in all_records if r.pool_type == pool_type]

        # 检查是否为卡片模式（有cards_container属性）
        cards_container = getattr(tab, '_cards_container', None)
        if cards_container:
            # 卡片模式：为每个pool_name创建独立卡片
            self._refresh_cards(tab, records, account, game, max_rarity, star_filter)
        else:
            # 普通模式：更新统计和单表格
            self._update_tab_stats(tab, records, account, game)

    def _get_star_filter(self, game: str) -> list:
        """获取当前游戏的星级筛选设置

        从配置中读取星级筛选列表，如果未配置则使用默认值：
            - 终末地/明日方舟：默认显示5-6星
            - 其他游戏：默认显示4-5星

        参数：
            game (str): 游戏ID

        返回：
            list[int]: 星级列表，如[5, 6] 或 [4, 5]

        数据结构：
            配置键格式: "star_filter.{game}"
            值格式: [int, int, ...] 如 [5, 6]
        """
        # 获取游戏的最高星级（如原神=5，明日方舟=6）
        max_rarity = get_max_rarity(game)
        # 根据游戏设置默认的星级筛选范围
        if game in ("endfield", "arknights"):
            # 终末地/明日方舟：只显示高星级（5星和6星）
            default = [r for r in range(5, max_rarity + 1)]
        else:
            # 其他游戏：显示4星和5星
            default = [r for r in range(4, max_rarity + 1)]
        # 从配置中读取，未配置则使用默认值
        return self.config.get(f"star_filter.{game}", default)

    def _on_star_filter_clicked(self):
        """打开星级筛选对话框

        弹出模态对话框，允许用户选择显示哪些星级的记录。
        对话框中的列表项从高星级到低星级排列，每项前有勾选框。

        数据结构：
            每个QListWidgetItem的UserRole存储星级数值（如5或6）
            UserRole + 1 存储布尔值，表示该星级是否被选中
        """
        # 获取当前游戏
        game = self.main_window.get_current_game()
        # 获取最高星级
        max_rarity = get_max_rarity(game)
        # 获取当前的星级筛选配置
        current_filter = self._get_star_filter(game)

        # 创建模态对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("星级筛选")
        dialog.setMinimumWidth(260)
        dialog.setMinimumHeight(300)
        layout = QVBoxLayout(dialog)

        # 提示文字
        header = QLabel("点击选择/取消显示的星级:")
        header.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px;")
        layout.addWidget(header)

        # 创建带勾选框的列表
        list_widget = GameListWidget()
        list_widget.setItemDelegate(CheckListDelegate(list_widget))
        list_widget.setStyleSheet("QListWidget { background-color: #ffffff; border: 1px solid #e0e0e0; }")

        # 星级到中文名称的映射
        star_labels = {3: "三星", 4: "四星", 5: "五星", 6: "六星"}
        # 从最高星级到1星，逐个添加列表项
        for star in range(max_rarity, 0, -1):
            # 构建显示文字，如"★★★★★★  六星"
            label = f"{'★' * star}  {star_labels.get(star, f'{star}星')}"
            item = QListWidgetItem(label)
            # 禁用Qt自带的checkable标记
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            # UserRole存储星级数值
            item.setData(Qt.ItemDataRole.UserRole, star)
            # UserRole + 1 存储当前是否选中
            item.setData(Qt.ItemDataRole.UserRole + 1, star in current_filter)
            list_widget.addItem(item)

        layout.addWidget(list_widget)

        # 添加确定/取消按钮
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        # 执行模态对话框
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 收集用户选中的星级
            selected = []
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if item.data(Qt.ItemDataRole.UserRole + 1):
                    selected.append(item.data(Qt.ItemDataRole.UserRole))
            # 如果没有选中任何星级，默认至少选中最高星级
            if not selected:
                selected = [max_rarity]
            # 保存配置
            self.config.set(f"star_filter.{game}", selected)
            self.config.save()
            # 刷新页面使筛选生效
            self.refresh()

    def refresh(self):
        """刷新整个首页页面

        这是首页的主刷新入口，在以下场景被调用：
            - 账号切换
            - 标签页切换
            - UID显示/隐藏切换
            - 卡池管理修改后
            - 星级筛选修改后
            - 外部数据变化后（通过 main_window.refresh_all() 间接调用）

        内部流程：
            1. 检测游戏是否发生变化（需要重建标签页）
            2. 获取账号列表，更新账号下拉框
            3. 如果需要重建，调用 _rebuild_tabs()
            4. 遍历所有标签页，根据筛选条件更新数据
            5. 使用 try/finally 确保 setUpmentsEnabled 恢复
        """
        # 获取当前游戏
        game = self.main_window.get_current_game()

        # 检测游戏是否发生了变化
        need_rebuild = game != self._current_game
        if need_rebuild:
            # 游戏切换时暂停UI更新，避免重建过程中的闪烁
            self.setUpdatesEnabled(False)

        try:
            # 先获取账号（重建标签页时需要知道有哪些独立寻访）
            accounts = self.db.get_accounts(game)
            account = self.main_window.get_current_account()
            # 如果主窗口没有当前账号但数据库中有，使用第一个账号
            if not account and accounts:
                self.main_window.set_account(accounts[0])
                account = accounts[0]

            # 如果游戏发生变化，重建所有标签页
            if need_rebuild:
                self._current_game = game
                self._rebuild_tabs(game, account)

            # ===== 刷新账号下拉框 =====
            # 阻塞信号，避免clear()触发_account_changed
            self.account_combo.blockSignals(True)
            self.account_combo.clear()
            # 重新查询账号列表（可能在重建标签页时有变化）
            accounts = self.db.get_accounts(game)
            current_account = self.main_window.get_current_account()
            current_index = 0
            # 遍历所有账号，添加到下拉框
            for i, acc in enumerate(accounts):
                # 显示名称：优先用昵称，没有则用UID
                display = acc.nickname if acc.nickname else acc.uid
                # 如果显示UID，在名称后附加UID
                if self._show_uid and acc.uid:
                    self.account_combo.addItem(f"{display} ({acc.uid})", acc.id)
                else:
                    self.account_combo.addItem(display, acc.id)
                # 记录当前账号在下拉框中的索引
                if current_account and acc.id == current_account.id:
                    current_index = i
            # 设置下拉框选中项为当前账号
            if accounts:
                self.account_combo.setCurrentIndex(current_index)
            # 恢复信号
            self.account_combo.blockSignals(False)

            # 如果没有账号，清空统计并返回
            if not accounts:
                self._clear_stats()
                return

            # 确保有当前账号
            account = self.main_window.get_current_account()
            if not account:
                self.main_window.set_account(accounts[0])
                account = accounts[0]

            # ===== 获取所有记录 =====
            all_records = self.db.get_records(account.id)
            if not all_records:
                self._clear_stats()
                return

            # ===== 更新各标签页 =====
            max_rarity = get_max_rarity(game)
            star_filter = self._get_star_filter(game)
            for tab in self._tabs:
                pool_type = tab._pool_type
                pool_name_filter = getattr(tab, '_pool_name_filter', None)
                # 根据pool_type筛选记录
                if pool_type is None:
                    records = all_records
                elif pool_name_filter:
                    records = [r for r in all_records if r.pool_type == pool_type and r.pool_name == pool_name_filter]
                else:
                    records = [r for r in all_records if r.pool_type == pool_type]

                # 检查是否为卡片模式
                cards_container = getattr(tab, '_cards_container', None)
                if cards_container:
                    self._refresh_cards(tab, records, account, game, max_rarity, star_filter)
                else:
                    self._update_tab_stats(tab, records, account, game)

        finally:
            # 无论是否发生异常，都恢复UI更新
            if need_rebuild:
                self.setUpdatesEnabled(True)

    def _update_tab_stats(self, tab, records, account, game):
        """更新单个标签页的统计数值、保底进度条和表格

        这是普通模式下标签页数据刷新的核心方法，负责：
            1. 计算各项统计指标并更新stat_items中的数值
            2. 更新保底进度条的进度和颜色
            3. 更新记录表格的数据

        参数：
            tab (QWidget): 标签页widget
            records (list[GachaRecord]): 该标签页的所有记录
            account (Account): 当前账号对象
            game (str): 游戏ID

        统计指标计算方法：
            - 总抽数: len(records)
            - 最高星数: 等于max_rarity的记录数
            - UP/总金数: UP记录数 / 最高星数记录数
            - 小保底不歪率: UP记录数 / 最高星数记录数 * 100%
            - 平均出金: 总抽数 / 最高星数记录数
            - 每UP需抽数: 所有最高星数记录的pity_count之和 / 最高星数记录数
        """
        # 获取统计项引用字典
        stat_items = tab._stat_items
        pool_type = tab._pool_type
        # 获取触发保底的星级（如原神角色池为5星）
        max_rarity = get_pity_rarity(game, pool_type)

        # 按时间排序记录（先按时间，再按ID保证确定性）
        sorted_records = sorted(records, key=lambda r: (r.time, r.id))
        total = len(records)
        # 筛选出触发保底的星级记录
        five_stars = [r for r in sorted_records if r.rarity == max_rarity]
        star5_count = len(five_stars)

        # ===== 更新各项统计数值 =====
        # 总抽数
        if "total" in stat_items:
            stat_items["total"]._value_label.setText(str(total))

        # 最高星数（触发保底的星级的记录数）
        if "star5" in stat_items:
            stat_items["star5"]._value_label.setText(str(star5_count))

        # UP/总金数（如"5/8"表示8个金中5个是UP）
        if "up_ratio" in stat_items:
            up_count = sum(1 for r in five_stars if r.is_featured)
            if star5_count > 0:
                stat_items["up_ratio"]._value_label.setText(f"{up_count}/{star5_count}")
            else:
                stat_items["up_ratio"]._value_label.setText("-")

        # 小保底不歪率（UP记录数 / 总金数 * 100%）
        if "win_rate" in stat_items:
            if star5_count > 0:
                up_count = sum(1 for r in five_stars if r.is_featured)
                win_rate = round(up_count / star5_count * 100, 1)
                stat_items["win_rate"]._value_label.setText(f"{win_rate}%")
            else:
                stat_items["win_rate"]._value_label.setText("-")

        # 平均出金（总抽数 / 金数）
        if "avg_pity" in stat_items:
            if star5_count > 0:
                avg = round(total / star5_count, 1)
                stat_items["avg_pity"]._value_label.setText(f"{avg}抽")
            else:
                stat_items["avg_pity"]._value_label.setText("-")

        # 每UP需抽数（所有金的pity_count之和 / 金数）
        if "avg_featured" in stat_items:
            if five_stars:
                # pity_count是每条记录出金时距上次出金的抽数
                avg = sum(r.pity_count for r in five_stars) / len(five_stars)
                stat_items["avg_featured"]._value_label.setText(f"{avg:.1f}抽")
            else:
                stat_items["avg_featured"]._value_label.setText("-")

        # ===== 更新保底进度条 =====
        pool_name_filter = getattr(tab, '_pool_name_filter', None)
        for p_type, pity_frame in tab._pity_frames:
            # 获取卡池的保底配置
            config = BANNER_CONFIGS.get((game, p_type))
            if not config:
                # 没有配置则隐藏该保底条
                pity_frame.setVisible(False)
                continue
            pity_frame.setVisible(True)

            # 独立寻访（limited）：池之间不互通不继承，不计算保底
            if p_type == "limited":
                pity_frame._pity_text.setText("卡池之间不互通不继承，故不计算保底")
                pity_frame._progress.setFormat("0/0")
                pity_frame._progress.setMaximum(1)
                pity_frame._progress.setValue(0)
                # 设置灰色进度条样式（表示不活跃）
                pity_frame._progress.setStyleSheet("""
                    QProgressBar {
                        border: none; border-radius: 10px; background-color: #e0e0e0;
                        text-align: center; color: #999; font-size: 11px; font-weight: bold;
                    }
                    QProgressBar::chunk { border-radius: 10px; background-color: #e0e0e0; }
                """)
                continue

            # 查询数据库获取距上次出金的抽数
            pity = self.db.get_last_5star_pity(account.id, p_type, game, pool_name=pool_name_filter or "")
            # 获取硬保底次数（如90抽必出）
            hard_pity = config.hard_pity
            # 更新保底文字
            pity_frame._pity_text.setText(f"已垫{pity}抽 / 保底{hard_pity}抽")
            # 更新进度条范围和当前值
            pity_frame._progress.setMaximum(hard_pity)
            pity_frame._progress.setValue(pity)

            # 根据进度比例设置进度条颜色：
            # < 50% 绿色（安全区）
            # 50%-80% 黄色（接近保底）
            # > 80% 红色（即将触发保底）
            ratio = pity / hard_pity if hard_pity > 0 else 0
            if ratio < 0.5:
                color = "#4CAF50"  # 绿色
            elif ratio < 0.8:
                color = "#FFC107"  # 黄色
            else:
                color = "#F44336"  # 红色
            # 动态设置进度条颜色（通过内联样式表）
            pity_frame._progress.setStyleSheet(f"""
                QProgressBar {{
                    border: none; border-radius: 10px; background-color: #e0e0e0;
                    text-align: center; color: #333; font-size: 11px; font-weight: bold;
                }}
                QProgressBar::chunk {{
                    border-radius: 10px; background-color: {color};
                }}
            """)

        # ===== 更新表格 =====
        star_filter = self._get_star_filter(game)
        self._update_pool_table(tab._table, sorted_records, max_rarity, star_filter)

    def _update_pool_table(self, table, records, max_rarity=5, star_filter=None):
        """更新卡池表格数据（最新在前）

        将记录按星级筛选后倒序填入表格。表格结构因游戏而异：
            - 明日方舟：5列（序号、名称、星级、保底计数、卡池）
            - 其他游戏：6列（序号、名称、星级、是否UP、保底计数、时间）

        参数：
            table (QTableWidget): 要更新的表格控件
            records (list[GachaRecord]): 已按时间排序的所有记录
            max_rarity (int): 触发保底的星级，默认5
            star_filter (list[int]|None): 星级筛选列表，为None时只显示max_rarity
        """
        # 如果没有传入星级筛选，默认只显示触发保底的星级
        if star_filter is None:
            star_filter = [max_rarity]
        # 按星级筛选记录
        filtered = [r for r in records if r.rarity in star_filter]
        # 反转顺序，使最新的记录显示在最上面
        filtered.reverse()
        # 设置表格行数
        table.setRowCount(len(filtered))

        # 星级颜色映射
        star_colors = {3: "#888", 4: "#9B59B6", 5: "#FFD700", 6: "#FF6B35"}
        # 获取当前列数以区分游戏
        col_count = table.columnCount()

        # 逐行填充表格数据
        for i, r in enumerate(filtered):
            # 第0列：序号（从1开始）
            table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            # 第1列：物品名称
            table.setItem(i, 1, QTableWidgetItem(r.item_name))

            # 第2列：星级（★符号 + 颜色）
            star_item = QTableWidgetItem("★" * r.rarity)
            star_item.setForeground(QColor(star_colors.get(r.rarity, "#FF6B35")))
            table.setItem(i, 2, star_item)

            if col_count == 5:
                # 明日方舟：5列
                # 第3列：保底计数（距上次出金的抽数）
                table.setItem(i, 3, QTableWidgetItem(str(r.pity_count)))
                # 第4列：卡池名称
                table.setItem(i, 4, QTableWidgetItem(r.pool_name or ""))
            else:
                # 其他游戏：6列
                # 第3列：是否UP（橙色=是，绿色=否）
                up_item = QTableWidgetItem("是" if r.is_featured else "否")
                if r.is_featured:
                    up_item.setForeground(QColor("#FF6B35"))
                else:
                    up_item.setForeground(QColor("#4CAF50"))
                table.setItem(i, 3, up_item)
                # 第4列：保底计数
                table.setItem(i, 4, QTableWidgetItem(str(r.pity_count)))
                # 第5列：时间（截取到分钟，忽略秒）
                table.setItem(i, 5, QTableWidgetItem(r.time[:16] if r.time else ""))

    def _clear_stats(self):
        """清空所有标签页的统计数据

        当没有账号或没有记录时调用，将所有统计项重置为"-"，
        清空表格，并重置保底进度条。
        同时清空卡片模式容器中的卡片。
        """
        # 遍历所有标签页
        for tab in self._tabs:
            # 重置所有统计项的数值为"-"
            for key, item in tab._stat_items.items():
                item._value_label.setText("-")
            # 清空表格（设置行数为0）
            tab._table.setRowCount(0)
            # 重置所有保底进度条
            for _, pf in tab._pity_frames:
                pf._pity_text.setText("0/0")
                pf._progress.setValue(0)
            # 清空卡片容器（卡片模式）
            cards_container = getattr(tab, '_cards_container', None)
            if cards_container:
                layout = cards_container.layout()
                if layout:
                    # 循环取出并删除所有卡片widget
                    while layout.count():
                        child = layout.takeAt(0)
                        if child.widget():
                            child.widget().deleteLater()
