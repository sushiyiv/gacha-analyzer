# =============================================================================
# 主窗口模块 - 应用程序的顶层窗口
# =============================================================================
# 本模块定义了 MainWindow 类，它是"穷观阵"抽卡分析工具的主窗口。
# MainWindow 继承自 QMainWindow，是整个应用的顶层容器，负责：
#   - 管理左侧导航栏（游戏选择 + 功能模块切换）
#   - 管理右侧内容区（通过 QStackedWidget 切换不同页面）
#   - 协调游戏切换、账号切换、页面刷新等全局状态
#   - 加载 QSS 样式表
#   - 自动更新明日方舟卡池数据
#
# 架构设计：
#   - 采用经典的"侧边导航 + 内容区"布局
#   - 左侧导航栏包含两部分：游戏选择区 + 功能导航区
#   - 右侧内容区使用 QStackedWidget 实现页面切换（类似 Tab 页但无 Tab 栏）
#   - 各页面（HomeWidget、ImportWidget 等）都接收 MainWindow 实例作为参数
#     以便访问全局状态（当前游戏、当前账号等）
# =============================================================================

# =============================================================================
# 标准库导入
# =============================================================================

# logging：Python 标准日志模块，提供分级日志记录（DEBUG/INFO/WARNING/ERROR/CRITICAL）
import logging

# os：Python 标准操作系统接口模块，提供文件路径操作、环境变量访问等功能
import os

# =============================================================================
# PySide6 QtWidgets 导入 - Qt 窗口部件类
# =============================================================================
# PySide6 是 Qt 6 的官方 Python 绑定，提供对 Qt C++ 库的完整访问
# QtWidgets 模块包含所有经典的桌面 UI 控件

from PySide6.QtWidgets import (
    QMainWindow,           # 主窗口基类，提供菜单栏、工具栏、状态栏、中心部件等框架
    QWidget,               # 所有 UI 对象的基类，不绘制任何内容，仅作为容器
    QVBoxLayout,           # 垂直布局管理器，将子控件从上到下排列
    QHBoxLayout,           # 水平布局管理器，将子控件从左到右排列
    QStackedWidget,        # 堆叠部件，一次只显示一个子部件（类似 Tab 页无 Tab 栏）
    QPushButton,           # 按钮控件，支持点击、可选中、可自定义样式
    QLabel,                # 标签控件，用于显示文本或图片
    QFrame,                # 框架控件，可添加边框和分割线，常用于分组和视觉分隔
    QFileDialog,           # 文件选择对话框（虽然导入但当前未使用）
    QMessageBox,           # 消息框对话框（虽然导入但当前未使用）
    QMenu,                 # 弹出菜单控件（虽然导入但当前未使用）
    QCheckBox,             # 复选框控件（虽然导入但当前未使用）
    QDialog,               # 对话框基类，模态或非模态显示
    QDialogButtonBox,      # 对话框按钮盒，自动根据平台排列 OK/Cancel 等标准按钮
    QListWidget,           # 列表控件，用于显示和管理有序列表
    QListWidgetItem,       # 列表项对象，存储在 QListWidget 中
    QScrollArea            # 滚动区域控件，为内容提供滚动条
)

# =============================================================================
# PySide6 QtCore 导入 - Qt 核心非 GUI 类
# =============================================================================

from PySide6.QtCore import Qt  # Qt 核心枚举集合（对齐方式、光标形状、键盘修饰键等）

# =============================================================================
# PySide6 QtGui 导入 - Qt GUI 类
# =============================================================================

from PySide6.QtGui import (
    QFont,    # 字体类，包含字体族、大小、粗细、样式等信息
    QIcon,    # 图标类，支持从文件、资源、像素图等创建图标
    QAction   # 动作类，可附加到菜单栏、工具栏、快捷键等
)

# =============================================================================
# 项目内部模块导入
# =============================================================================

# 游戏列表组件：提供自定义的列表委托和列表控件
from ui.widgets.game_list import GameListDelegate, GameListWidget, CheckListDelegate

# 数据库管理器：提供 SQLite 数据库的 CRUD 操作封装
from core.database import Database

# 配置管理器：提供 JSON 配置文件的读写操作
from core.config import Config

# 数据模型常量：GAME_NAMES（游戏ID到中文名映射）和 GAME_COLORS（游戏主题色）
from core.models import GAME_NAMES, GAME_COLORS

# 各页面控件（每个页面对应一个功能模块）
from ui.widgets.home_widget import HomeWidget          # 总览首页
from ui.widgets.import_widget import ImportWidget      # 数据导入页面
from ui.widgets.manual_add_widget import ManualAddWidget  # 手动添加页面
from ui.widgets.stats_widget import StatsWidget        # 统计分析页面
from ui.widgets.chart_widget import ChartWidget        # 图表展示页面
from ui.widgets.settings_widget import SettingsWidget  # 设置页面

# =============================================================================
# 日志记录器初始化
# =============================================================================

# 创建以当前模块名命名的日志记录器
# __name__ 在此文件中为 "ui.main_window"
# 日志记录器的层级结构：root -> ui -> main_window
logger = logging.getLogger(__name__)


# =============================================================================
# MainWindow 类定义
# =============================================================================

class MainWindow(QMainWindow):
    """应用程序主窗口。

    继承自 QMainWindow，管理整个应用的 UI 布局和全局状态。

    QMainWindow 提供的标准框架：
    - setCentralWidget()：设置中心部件（本应用使用自定义的 QWidget 作为中心部件）
    - menuBar()：菜单栏（本应用未使用）
    - statusBar()：状态栏（本应用未使用）
    - toolBar()：工具栏（本应用未使用）

    全局状态属性：
        self.db (Database)：数据库实例，所有页面共享同一个数据库连接
        self.config (Config)：配置管理器实例，管理 JSON 配置文件的读写
        self.current_account (str | None)：当前选中的账号 UID
        self.current_game (str)：当前选中的游戏 ID（如 "genshin"）
        self.game_buttons (dict)：游戏 ID -> QPushButton 的映射字典
        self.nav_buttons (dict)：导航键名 -> QPushButton 的映射字典
        self._game_order (list)：游戏的显示顺序列表
        self._visible_games (list)：可见游戏的 ID 列表
        self.page_stack (QStackedWidget)：页面堆叠部件
    """

    # ---------------------------------------------------------------------------
    # 构造方法
    # ---------------------------------------------------------------------------

    def __init__(self):
        """初始化主窗口。

        初始化流程：
        1. 调用 QMainWindow.__init__() 完成基类初始化
        2. 创建数据库和配置管理器的全局实例
        3. 初始化 UI 布局（_init_ui）
        4. 加载 QSS 样式表（_load_style）
        5. 延迟自动更新明日方舟卡池数据（_auto_update_arknights_pools）
        6. 恢复上次选择的游戏（从配置文件读取）
        """
        super().__init__()  # 调用 QMainWindow 的构造函数

        # 创建全局数据库实例
        # Database 类封装了 SQLite 数据库操作，采用单例模式确保所有页面共享同一连接
        self.db = Database()

        # 创建全局配置管理器实例
        # Config 类管理 JSON 配置文件的读写，支持 get/set/save 操作
        self.config = Config()

        # 当前选中的账号 UID（初始为 None，切换游戏时自动设置）
        # 账号数据结构：数据库中存储的 UID 字符串
        self.current_account = None

        # 当前选中的游戏 ID（初始为 "genshin"，即原神）
        # 游戏 ID 是 GAME_NAMES 字典的键（如 "genshin"、"star_rail"、"arknights" 等）
        self.current_game = "genshin"

        # 初始化 UI 布局（构建整个窗口的控件树）
        self._init_ui()

        # 加载 QSS 样式表（覆盖默认的 Qt 控件样式）
        self._load_style()

        # 延迟 1 秒后自动更新明日方舟的卡池类型数据
        # 使用 QTimer.singleShot 确保在 UI 完全显示后才执行
        self._auto_update_arknights_pools()

        # =========================================================================
        # 恢复上次选择的游戏
        # =========================================================================
        # 从配置文件读取上次最后选择的游戏 ID
        # config.get(key, default) 方法：如果 key 存在则返回对应值，否则返回 default
        last_game = self.config.get("last_game", "")

        # 如果上次选择的游戏存在且在当前可见游戏中，则切换到该游戏
        if last_game and last_game in self._visible_games:
            self._on_game_changed(last_game)
        else:
            # 否则切换到第一个可见游戏，如果没有可见游戏则回退到 "genshin"
            # 三元表达式：_visible_games[0] 如果列表不为空，否则 "genshin"
            first = self._visible_games[0] if self._visible_games else "genshin"
            self._on_game_changed(first)

    # ---------------------------------------------------------------------------
    # 明日方舟卡池自动更新
    # ---------------------------------------------------------------------------

    def _auto_update_arknights_pools(self):
        """延迟 1 秒后自动更新明日方舟的卡池类型数据。

        为什么要延迟 1 秒：
        - 确保 UI 已经完全初始化和显示
        - 避免在构造期间执行耗时操作导致界面卡顿
        - QTimer.singleShot 是一次性定时器，到期后自动销毁

        内部实现：
        - 定义一个局部函数 do_update()，封装实际的更新逻辑
        - 通过 QTimer.singleShot(1000, do_update) 在 1000ms 后执行

        异常处理：
        - 使用 try/except 捕获所有异常，避免自动更新失败影响应用启动
        - logger.exception() 记录完整的异常堆栈信息，便于调试
        """
        from PySide6.QtCore import QTimer  # 延迟导入 QTimer，避免循环依赖

        def do_update():
            """执行明日方舟卡池类型的实际更新操作。

            内部工作原理：
            1. 调用 settings_page._do_update_arknights_pool_types() 方法
            2. 该方法会从外部数据源获取最新的卡池类型信息
            3. 返回更新的记录数（int），如果更新成功且有新数据则 > 0
            4. 记录日志信息

            异常处理：
            - 捕获所有 Exception 异常，记录日志但不中断应用运行
            - 这是合理的策略，因为卡池更新是后台辅助功能，不应影响主程序
            """
            try:
                # 调用设置页面的明日方舟卡池类型更新方法
                # updated 返回更新的记录数
                updated = self.settings_page._do_update_arknights_pool_types()

                # 如果有记录被更新，记录 info 级别日志
                # %d 是 Python logging 的格式化占位符，对应 updated 的整数值
                if updated > 0:
                    logger.info("auto-update arknights pool types: %d records", updated)
            except Exception:
                # 捕获所有异常并记录完整的异常堆栈（包含行号、调用链等）
                logger.exception("auto-update arknights pool types failed")

        # 使用 QTimer.singleShot 在 1000 毫秒（1 秒）后执行 do_update
        # singleShot 创建一个一次性的 QTimer，到期触发信号后自动销毁
        QTimer.singleShot(1000, do_update)

    # ---------------------------------------------------------------------------
    # UI 初始化方法
    # ---------------------------------------------------------------------------

    def _init_ui(self):
        """初始化整个窗口的 UI 布局。

        布局结构（树状）：
        MainWindow (QMainWindow)
        └── central (QWidget)                    -- 中心部件
            └── main_layout (QHBoxLayout)         -- 水平主布局（无边距、无间距）
                ├── nav_widget (QWidget, 固定宽 200px)  -- 左侧导航栏
                │   └── nav_layout (QVBoxLayout)          -- 垂直导航布局
                │       ├── game_frame (QFrame)            -- 游戏选择区域
                │       │   └── game_layout (QVBoxLayout)
                │       │       ├── "选择游戏" 标签
                │       │       ├── _game_scroll (QScrollArea)  -- 游戏列表滚动区
                │       │       │   └── scroll_content (QWidget)
                │       │       │       └── _game_layout (QVBoxLayout)  -- 游戏按钮布局
                │       │       └── "游戏管理" 按钮
                │       ├── 分割线 (QFrame HLine)
                │       ├── 功能导航按钮 x6
                │       ├── 弹簧 (addStretch)
                │       └── 版本号标签
                └── content_widget (QWidget)       -- 右侧内容区
                    └── content_layout (QVBoxLayout)
                        ├── top_bar (QHBoxLayout)   -- 顶部信息栏
                        │   ├── 弹簧
                        │   └── game_indicator (QLabel)  -- 当前游戏指示器
                        └── page_stack (QStackedWidget)  -- 页面堆叠部件
                            ├── home_page (HomeWidget)
                            ├── import_page (ImportWidget)
                            ├── manual_page (ManualAddWidget)
                            ├── stats_page (StatsWidget)
                            ├── chart_page (ChartWidget)
                            └── settings_page (SettingsWidget)
        """
        # 设置窗口标题（使用中文古风标题："穷观阵"是游戏内道具名，副标题为诗意文案）
        self.setWindowTitle("穷观阵 -- 乾坤清策，否极泰来")

        # 设置窗口最小尺寸（宽度 1100px，高度 700px）
        # 用户不能将窗口缩小到此尺寸以下
        self.setMinimumSize(1100, 700)

        # 设置窗口初始大小（宽度 1200px，高度 750px）
        self.resize(1200, 750)

        # =========================================================================
        # 设置窗口图标
        # =========================================================================
        # 构建图标文件的绝对路径
        # __file__ 是当前文件路径，dirname 两次得到项目根目录
        # 例如：D:/gacha-analyzer/ui/main_window.py
        #       -> D:/gacha-analyzer/ui/ (dirname 1次)
        #       -> D:/gacha-analyzer/ (dirname 2次)
        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icon.ico")

        # 如果图标文件存在，则设置窗口图标
        # QIcon 支持从 ICO/PNG/JPG 等多种格式加载
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # =========================================================================
        # 创建中心部件和主布局
        # =========================================================================
        # QMainWindow 要求设置一个中心部件（central widget），
        # 所有内容都放置在中心部件内
        central = QWidget()
        self.setCentralWidget(central)  # 将 central 设置为中心部件

        # 创建水平布局作为主布局
        # 布局管理器会自动管理子控件的位置和大小
        main_layout = QHBoxLayout(central)

        # 设置主布局的边距和间距为 0
        # 这样导航栏和内容区可以无缝紧贴窗口边缘
        main_layout.setContentsMargins(0, 0, 0, 0)  # 左、上、右、下
        main_layout.setSpacing(0)  # 子控件之间的间距

        # =========================================================================
        # 左侧导航栏
        # =========================================================================
        # 创建导航栏的容器 widget
        nav_widget = QWidget()
        nav_widget.setObjectName("nav_widget")  # 设置 Qt 对象名，用于 QSS 样式选择
        nav_widget.setFixedWidth(200)  # 固定导航栏宽度为 200 像素

        # 创建垂直布局管理导航栏内容
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(0, 0, 0, 0)  # 无边距
        nav_layout.setSpacing(0)  # 无间距

        # =========================================================================
        # 游戏选择区域
        # =========================================================================
        # 创建一个带边框的框架容器，用于包裹游戏选择相关内容
        game_frame = QFrame()
        game_layout = QVBoxLayout(game_frame)  # 框架内的垂直布局

        # 设置游戏区域的内边距：左12、上8、右12、下8
        game_layout.setContentsMargins(12, 8, 12, 8)
        # 子控件之间的间距为 2px（紧凑布局）
        game_layout.setSpacing(2)

        # 创建"选择游戏"标题标签
        game_label = QLabel("选择游戏")
        # 通过内联样式表设置灰色小字体，左侧留 4px 内边距
        game_label.setStyleSheet("color: #888; font-size: 11px; padding-left: 4;")
        game_layout.addWidget(game_label)  # 将标签添加到游戏区域布局

        # =========================================================================
        # 初始化游戏排序和可见性列表
        # =========================================================================

        # 从配置文件读取游戏显示顺序
        # 如果配置文件中没有 game_order，则使用 GAME_NAMES 的默认键顺序
        # GAME_NAMES 是一个字典，键为游戏 ID（如 "genshin"、"star_rail"）
        self._game_order = self.config.get("game_order", list(GAME_NAMES.keys()))

        # 过滤掉不在 GAME_NAMES 中的无效游戏 ID（防止配置文件中残留已删除的游戏）
        self._game_order = [g for g in self._game_order if g in GAME_NAMES]

        # 确保所有游戏都在 _game_order 中（即使配置文件中遗漏了某些游戏）
        # 如果 GAME_NAMES 中有新游戏但 _game_order 中没有，追加到末尾
        for g in GAME_NAMES:
            if g not in self._game_order:
                self._game_order.append(g)

        # 从配置文件读取可见游戏列表
        # visible_games 控制哪些游戏在导航栏中显示（用户可以隐藏不需要的游戏）
        self._visible_games = self.config.get("visible_games", list(GAME_NAMES.keys()))

        # 过滤掉不在 GAME_NAMES 中的无效游戏 ID
        self._visible_games = [g for g in self._visible_games if g in GAME_NAMES]

        # =========================================================================
        # 创建游戏列表滚动区域
        # =========================================================================

        # QScrollArea：为内容提供滚动条
        # 当游戏数量较多时，可以垂直滚动查看所有游戏
        self._game_scroll = QScrollArea()

        # setWidgetResizable(True)：使内部 widget 自动调整大小以填充滚动区域
        # 这确保了当窗口大小改变时，内部内容也能正确适应
        self._game_scroll.setWidgetResizable(True)

        # 隐藏滚动区域的边框（NoFrame = 无边框）
        # 这样滚动区域与周围的 UI 元素无缝融合
        self._game_scroll.setFrameShape(QFrame.Shape.NoFrame)

        # 禁用水平滚动条（我们只需要垂直滚动）
        # ScrollBarAlwaysOff = 始终隐藏水平滚动条
        self._game_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        # 创建滚动区域的内容容器
        # QScrollArea 内部需要一个 QWidget 作为滚动内容的载体
        scroll_content = QWidget()

        # 创建垂直布局用于排列游戏按钮
        self._game_layout = QVBoxLayout(scroll_content)
        self._game_layout.setContentsMargins(0, 0, 0, 0)
        self._game_layout.setSpacing(2)  # 游戏按钮之间的间距为 2px

        # 游戏按钮字典：{game_id: QPushButton}
        # 用于在切换游戏时快速更新按钮的选中状态
        self.game_buttons = {}

        # 构建游戏按钮（从 _game_order 和 _visible_games 生成）
        self._rebuild_game_buttons()

        # 将内容容器设置为滚动区域的 widget
        self._game_scroll.setWidget(scroll_content)

        # 设置滚动区域的最小高度为 220px
        # 确保即使游戏较少，游戏选择区域也占据足够的垂直空间
        self._game_scroll.setMinimumHeight(220)

        # 将滚动区域添加到游戏区域布局
        game_layout.addWidget(self._game_scroll)

        # =========================================================================
        # "游戏管理" 按钮
        # =========================================================================
        # 创建按钮，点击后打开游戏管理对话框
        more_btn = QPushButton("游戏管理")
        more_btn.setObjectName("game_button")  # 设置对象名，用于 QSS 样式选择
        more_btn.setCursor(Qt.CursorShape.PointingHandCursor)  # 鼠标悬停时显示手型光标

        # 通过内联样式表自定义按钮外观：
        # - 蓝色文字 + 蓝色边框（与应用主色调一致）
        # - 圆角 6px
        # - 悬停时背景变为浅蓝色
        more_btn.setStyleSheet("""
            QPushButton {
                color: #1a73e8; font-size: 12px; font-weight: bold;
                border: 1px solid #1a73e8; border-radius: 6px;
                padding: 10px 4px; text-align: center; min-height: 20px;
            }
            QPushButton:hover { background-color: #e8f0fe; }
        """)

        # 信号-槽连接：点击按钮时调用 _show_game_manager 方法
        # clicked 是 QPushButton 的内置信号，发射时携带一个 bool 参数（checked）
        # 但我们不需要这个参数，所以 lambda 中忽略它
        more_btn.clicked.connect(self._show_game_manager)

        # 将按钮添加到游戏区域布局
        game_layout.addWidget(more_btn)

        # 将游戏框架添加到导航栏布局
        nav_layout.addWidget(game_frame)

        # =========================================================================
        # 分割线
        # =========================================================================
        # 创建水平分割线，视觉上分隔游戏选择区和功能导航区
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)  # 水平线
        # 内联样式：灰色线条，上下各有 8px 的外边距，左右 16px
        line.setStyleSheet("color: #e0e0e0; margin: 8px 16px;")
        nav_layout.addWidget(line)

        # =========================================================================
        # 功能导航按钮
        # =========================================================================

        # 导航按钮字典：{键名: QPushButton}
        # 键名用于标识当前选中的页面
        self.nav_buttons = {}

        # 导航项定义：(键名, 显示文本)
        # 键名对应 page_stack 中的页面索引
        nav_items = [
            ("home", "总览"),       # 首页总览
            ("import", "获取数据"),  # 数据导入
            ("manual", "手动添加"),  # 手动添加抽卡记录
            ("stats", "统计分析"),  # 数据统计分析
            ("chart", "图表展示"),  # 图表可视化
            ("settings", "设置"),    # 应用设置
        ]

        for key, text in nav_items:
            # 创建导航按钮
            btn = QPushButton(text)
            btn.setObjectName("nav_button")  # 对象名，用于 QSS 样式选择

            # setCheckable(True)：使按钮具有"可选中"状态
            # 选中按钮显示为高亮（类似 RadioButton 的互斥选择效果）
            btn.setCheckable(True)

            btn.setCursor(Qt.CursorShape.PointingHandCursor)  # 手型光标

            # 信号-槽连接：点击按钮时调用 _on_nav_changed 方法
            # 使用 lambda 并通过默认参数 k=key 捕获当前循环变量
            # 这是 Python 闭包的经典陷阱：如果不使用默认参数，
            # lambda 中的 k 会引用循环结束后的最后一个值
            btn.clicked.connect(lambda checked, k=key: self._on_nav_changed(k))

            nav_layout.addWidget(btn)  # 将按钮添加到导航布局
            self.nav_buttons[key] = btn  # 存入字典以便后续访问

        # =========================================================================
        # 弹簧和版本号标签
        # =========================================================================

        # addStretch()：在导航按钮下方添加弹性空间
        # 弹簧会占据所有剩余的垂直空间，将版本号标签推到底部
        nav_layout.addStretch()

        # 版本号标签
        version = QLabel("v1.0.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)  # 水平和垂直居中
        version.setStyleSheet("color: #bbb; font-size: 11px; padding: 8px;")  # 浅灰色小字
        nav_layout.addWidget(version)

        # 将导航栏添加到主布局（位于左侧）
        main_layout.addWidget(nav_widget)

        # =========================================================================
        # 右侧内容区
        # =========================================================================

        # 创建内容区的容器 widget
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #f5f5f5;")  # 浅灰色背景

        # 创建垂直布局
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(16, 16, 16, 16)  # 四周各留 16px 内边距

        # =========================================================================
        # 顶部信息栏
        # =========================================================================

        # 创建水平布局，内容居中显示
        top_bar = QHBoxLayout()
        top_bar.addStretch()  # 左侧弹簧，将内容推向右方

        # 游戏指示器标签：显示当前选中的游戏名称
        self.game_indicator = QLabel()
        # 内联样式：蓝色背景、黑色文字、圆角胶囊形状
        self.game_indicator.setStyleSheet(
            "background-color: #1a73e8; color: #000000; border-radius: 10px; "
            "padding: 4px 12px; font-size: 12px; font-weight: bold;"
        )
        top_bar.addWidget(self.game_indicator)  # 将指示器添加到顶部栏

        # 将顶部栏添加到内容布局
        content_layout.addLayout(top_bar)

        # =========================================================================
        # 页面堆叠部件
        # =========================================================================

        # QStackedWidget：一次只显示一个子部件，通过索引切换
        # 类似 Tab 页，但没有 Tab 栏（切换由左侧导航栏控制）
        self.page_stack = QStackedWidget()
        content_layout.addWidget(self.page_stack)

        # =========================================================================
        # 创建各页面控件
        # =========================================================================

        # 每个页面都接收 self（MainWindow 实例）作为参数
        # 这样各页面可以访问主窗口的全局状态（如 get_current_game()）
        self.home_page = HomeWidget(self)        # 总览首页
        self.import_page = ImportWidget(self)    # 数据导入页面
        self.manual_page = ManualAddWidget(self)  # 手动添加页面
        self.stats_page = StatsWidget(self)      # 统计分析页面
        self.chart_page = ChartWidget(self)      # 图表展示页面
        self.settings_page = SettingsWidget(self)  # 设置页面

        # 将所有页面添加到 QStackedWidget
        # addWidget 返回该页面的索引（从 0 开始）
        # 页面索引对应关系：
        #   0 = home_page
        #   1 = import_page
        #   2 = manual_page
        #   3 = stats_page
        #   4 = chart_page
        #   5 = settings_page
        for page in [self.home_page, self.import_page, self.manual_page,
                     self.stats_page, self.chart_page, self.settings_page]:
            self.page_stack.addWidget(page)

        # 将内容区添加到主布局（位于导航栏右侧）
        main_layout.addWidget(content_widget)

        # =========================================================================
        # 初始化选中状态
        # =========================================================================

        # 默认选中"总览"导航按钮
        self.nav_buttons["home"].setChecked(True)

        # 如果有可见的游戏，选中第一个可见游戏
        if self.game_buttons:
            # first_visible：找到 _game_order 中第一个存在于 game_buttons 中的游戏
            # next() 从生成器中获取第一个匹配项，如果没有则返回 None
            first_visible = next(
                (g for g in self._game_order if g in self.game_buttons),
                None
            )
            if first_visible:
                self.game_buttons[first_visible].setChecked(True)

    # ---------------------------------------------------------------------------
    # 游戏按钮重建方法
    # ---------------------------------------------------------------------------

    def _rebuild_game_buttons(self):
        """重建游戏选择区域的所有按钮。

        当用户通过"游戏管理"对话框修改游戏顺序或可见性后调用此方法。

        重建流程：
        1. 清除 _game_layout 中的所有现有子控件
           - takeAt(0)：从布局中取出第一个子项
           - item.widget()：获取子项对应的 widget
           - w.deleteLater()：延迟删除 widget（在 Qt 事件循环安全时执行）
        2. 清空 game_buttons 字典
        3. 遍历 _game_order，为每个可见游戏创建按钮
        4. 在布局末尾添加弹性空间

        为什么使用 deleteLater() 而非直接 delete：
        - deleteLater() 将删除操作放入 Qt 事件队列，在安全的时机执行
        - 直接删除正在使用的 widget 可能导致未定义行为
        - 这是 Qt 推荐的安全删除方式
        """
        # 第一步：清除布局中的所有现有 widget
        while self._game_layout.count():
            # takeAt(0)：取出布局中的第一个子项（QLayoutItem）
            # 每次取出第一个，直到布局为空
            item = self._game_layout.takeAt(0)

            # 获取子项对应的 widget
            # 注意：布局项可能是 widget、子布局或弹簧（spacer）
            # 只有 widget 需要手动删除
            w = item.widget()
            if w:
                w.deleteLater()  # 延迟删除，确保在 Qt 事件循环安全时执行

        # 清空游戏按钮字典
        self.game_buttons.clear()

        # 第二步：为每个可见游戏创建按钮
        for game_id in self._game_order:
            # 跳过不在可见列表中的游戏
            if game_id not in self._visible_games:
                continue

            # 创建游戏按钮（设置文本、样式、点击事件）
            btn = self._create_game_button(game_id)

            # 将按钮添加到游戏布局（从上到下排列）
            self._game_layout.addWidget(btn)

            # 存入字典，便于后续通过游戏 ID 快速访问按钮
            self.game_buttons[game_id] = btn

        # 在布局末尾添加弹性空间
        # 这使游戏按钮靠顶部排列，底部留出空白
        self._game_layout.addStretch()

    # ---------------------------------------------------------------------------
    # 创建单个游戏按钮
    # ---------------------------------------------------------------------------

    def _create_game_button(self, game_id):
        """创建一个游戏选择按钮。

        参数说明：
            game_id (str): 游戏 ID，如 "genshin"、"star_rail"、"arknights"
                          用于从 GAME_NAMES 字典获取显示名称

        返回值：
            QPushButton：配置好的游戏按钮实例

        按钮属性：
        - 文本：GAME_NAMES[game_id] 的中文名称（如 "原神"、"崩坏：星穹铁道"）
        - 可选中（checkable）：点击后按钮保持选中状态
        - 点击信号连接到 _on_game_changed 方法
        """
        # 创建按钮，使用 GAME_NAMES 字典将 game_id 转换为中文名称
        # 如果 game_id 不在 GAME_NAMES 中，则直接使用 game_id 作为文本
        btn = QPushButton(GAME_NAMES.get(game_id, game_id))
        btn.setObjectName("game_button")  # 对象名，用于 QSS 样式选择
        btn.setCheckable(True)  # 可选中状态
        btn.setCursor(Qt.CursorShape.PointingHandCursor)  # 手型光标

        # 信号-槽连接：点击时调用 _on_game_changed，传入对应的游戏 ID
        # 使用默认参数 g=game_id 捕获当前的 game_id 值
        btn.clicked.connect(lambda checked, g=game_id: self._on_game_changed(g))

        return btn

    # ---------------------------------------------------------------------------
    # 游戏管理对话框
    # ---------------------------------------------------------------------------

    def _show_game_manager(self):
        """显示游戏管理对话框。

        功能：
        - 显示所有游戏的列表，每个游戏前有复选框
        - 用户可以点击复选框控制游戏的可见性
        - 用户可以通过拖拽调整游戏的显示顺序
        - 点击"确定"保存修改并更新导航栏

        对话框结构：
        QDialog
        └── layout (QVBoxLayout)
            ├── header (QLabel)             -- 提示信息
            ├── list_widget (GameListWidget) -- 可拖拽的复选列表
            └── buttons (QDialogButtonBox)  -- 确定/取消按钮

        Qt 对话框生命周期：
        - dialog = QDialog(self)：创建对话框，parent=self（主窗口）
          - 设置 parent 确保对话框随主窗口一起销毁（对象树机制）
          - 模态对话框会阻塞父窗口的交互
        - dialog.exec()：以模态方式显示对话框，阻塞直到用户关闭
          - 返回 QDialog.DialogCode.Accepted（确定）或 QDialog.DialogCode.Rejected（取消）
        - dialog.accept()：关闭对话框并返回 Accepted
        - dialog.reject()：关闭对话框并返回 Rejected
        """
        # 创建模态对话框，parent 为 self（主窗口）
        # 这确保对话框在主窗口之上显示，且随主窗口一起销毁
        dialog = QDialog(self)
        dialog.setWindowTitle("管理游戏")  # 设置对话框标题
        dialog.setMinimumWidth(300)   # 最小宽度
        dialog.setMinimumHeight(350)  # 最小高度

        # 创建垂直布局
        layout = QVBoxLayout(dialog)

        # 创建提示信息标签
        header = QLabel("点击选择/取消，长按拖动排序")
        header.setStyleSheet("font-size: 12px; font-weight: bold; padding: 4px;")
        layout.addWidget(header)

        # =========================================================================
        # 创建可拖拽的复选列表
        # =========================================================================
        list_widget = GameListWidget()  # 使用自定义的 GameListWidget

        # 设置拖拽模式为 InternalMove（内部移动）
        # 这允许在同一个列表内拖拽排序，但不能拖到列表外部
        list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)

        # 设置默认拖拽操作为 MoveAction（移动而非复制）
        list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)

        # 设置自定义委托（CheckListDelegate）来绘制列表项
        # 这样每个列表项都会显示"复选框 + 文字"的样式
        list_widget.setItemDelegate(CheckListDelegate(list_widget))

        # 设置列表的样式表（白色背景 + 浅灰色边框）
        list_widget.setStyleSheet(
            "QListWidget { background-color: #ffffff; border: 1px solid #e0e0e0; }"
        )

        # =========================================================================
        # 填充列表项
        # =========================================================================
        # 遍历游戏排序列表，为每个游戏创建一个列表项
        for gid in self._game_order:
            # 创建列表项，文本为游戏的中文名称
            item = QListWidgetItem(GAME_NAMES.get(gid, gid))

            # 禁用 Qt 内置的复选框功能
            # ItemIsUserCheckable 标志控制是否显示 Qt 自带的复选框
            # 我们使用自定义委托绘制复选框，所以需要禁用内置的
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)

            # 存储游戏 ID 到 UserRole（自定义数据角色，从 256 开始）
            item.setData(Qt.ItemDataRole.UserRole, gid)

            # 存储可见性状态到 UserRole + 1（布尔值）
            # 使用 in 运算符判断该游戏是否在可见列表中
            item.setData(Qt.ItemDataRole.UserRole + 1, gid in self._visible_games)

            list_widget.addItem(item)  # 将列表项添加到列表控件

        layout.addWidget(list_widget)

        # =========================================================================
        # 对话框按钮
        # =========================================================================

        # 创建对话框按钮盒，包含"确定"和"取消"两个按钮
        # StandardButton.Ok 和 StandardButton.Cancel 是 Qt 预定义的标准按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )

        # 信号-槽连接：
        # accepted 信号 -> dialog.accept()：关闭对话框并返回 Accepted
        # rejected 信号 -> dialog.reject()：关闭对话框并返回 Rejected
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        # =========================================================================
        # 处理对话框结果
        # =========================================================================

        # exec() 以模态方式显示对话框，返回用户操作的结果码
        # Accepted 表示用户点击了"确定"，Rejected 表示点击了"取消"
        if dialog.exec() == QDialog.DialogCode.Accepted:
            # 用户点击了"确定"，收集列表中的新顺序和可见性设置
            new_order = []     # 新的游戏显示顺序
            new_visible = []   # 新的可见游戏列表

            # 遍历列表中的所有项（注意：拖拽排序后顺序可能已改变）
            for i in range(list_widget.count()):
                item = list_widget.item(i)  # 获取第 i 个列表项

                # 从 UserRole 获取游戏 ID
                gid = item.data(Qt.ItemDataRole.UserRole)
                new_order.append(gid)  # 添加到新顺序列表

                # 从 UserRole + 1 获取可见性状态
                if item.data(Qt.ItemDataRole.UserRole + 1):
                    new_visible.append(gid)

            # 更新游戏顺序和可见性列表
            self._game_order = new_order

            # 确保至少有一个可见游戏（如果用户取消了所有游戏的勾选，
            # 则默认显示排序列表中的第一个游戏）
            self._visible_games = new_visible if new_visible else [new_order[0]]

            # 将新设置保存到配置文件
            self.config.set("game_order", self._game_order)
            self.config.set("visible_games", self._visible_games)

            # config.save() 将内存中的配置持久化到 JSON 文件
            self.config.save()

            # 重建导航栏中的游戏按钮
            self._rebuild_game_buttons()

            # 检查当前选中的游戏是否仍然可见
            if self.current_game not in self._visible_games:
                # 如果当前游戏已被隐藏，切换到第一个可见游戏
                self._on_game_changed(self._visible_games[0])
            else:
                # 当前游戏仍然可见，更新按钮的选中状态
                self.game_buttons[self.current_game].setChecked(True)

    # ---------------------------------------------------------------------------
    # 加载 QSS 样式表
    # ---------------------------------------------------------------------------

    def _load_style(self):
        """加载 QSS（Qt Style Sheets）样式表。

        QSS 是 Qt 的样式表语言，语法类似 CSS，用于自定义 Qt 控件的外观。

        文件路径：
        ui/resources/styles/default.qss

        工作原理：
        - 读取 QSS 文件的全部内容
        - 调用 self.setStyleSheet() 将样式应用到整个窗口
        - QSS 会向下级联到所有子控件
        - 如果文件不存在，则不加载任何样式，使用 Qt 默认外观

        QSS 加载时机：
        - 在 _init_ui() 之后调用，确保所有控件已创建
        - 样式表会在控件创建后立即生效
        """
        # 构建 QSS 文件的绝对路径
        # __file__ = ui/main_window.py
        # dirname 1次 = ui/
        # dirname 2次 = 项目根目录/
        # join("resources", "styles", "default.qss") = resources/styles/default.qss
        qss_path = os.path.join(
            os.path.dirname(__file__),
            "resources",
            "styles",
            "default.qss"
        )

        # 检查 QSS 文件是否存在，如果存在则读取并应用
        if os.path.exists(qss_path):
            # 使用 with 语句确保文件正确关闭（上下文管理器）
            # encoding="utf-8" 确保正确读取中文注释和字符串
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())  # 读取全部内容并应用为样式表

    # ---------------------------------------------------------------------------
    # 游戏切换处理
    # ---------------------------------------------------------------------------

    def _on_game_changed(self, game: str):
        """处理游戏切换事件。

        当用户点击左侧导航栏的游戏按钮时调用此方法。

        参数说明：
            game (str): 新选中的游戏 ID（如 "genshin"、"star_rail"）

        处理流程：
        1. 更新当前游戏状态
        2. 将游戏选择保存到配置文件（下次启动时恢复）
        3. 更新所有游戏按钮的选中状态（只高亮当前选中的）
        4. 更新右上角的游戏指示器标签（颜色和文字）
        5. 加载该游戏的第一个账号
        6. 刷新当前显示的页面

        数据流：
        - 用户点击游戏按钮 -> _on_game_changed(game) 被调用
        - 该方法更新全局状态 -> 各页面通过 get_current_game() 获取新状态
        - 各页面根据新状态刷新数据显示
        """
        # 更新全局游戏状态
        self.current_game = game

        # 保存到配置文件，以便下次启动时恢复
        self.config.set("last_game", game)
        self.config.save()  # 持久化到 JSON 文件

        # 更新所有游戏按钮的选中状态
        # 只有当前选中的游戏按钮高亮，其他按钮取消选中
        # setChecked(True/False) 触发按钮的重绘，显示选中/未选中外观
        for gid, btn in self.game_buttons.items():
            btn.setChecked(gid == game)  # 只有 gid == game 时为 True

        # =========================================================================
        # 更新右上角的游戏指示器标签
        # =========================================================================

        # 获取游戏主题色（从 GAME_COLORS 字典）
        # GAME_COLORS 结构示例：{"genshin": {"primary": "#e8a838"}, ...}
        colors = GAME_COLORS.get(game, {})

        # 获取主色调，如果找不到则回退到默认蓝色 #1a73e8
        accent = colors.get("primary", "#1a73e8")

        # 设置指示器文本（前后各加两个空格作为内边距）
        self.game_indicator.setText(f"  {GAME_NAMES.get(game, game)}  ")

        # 更新指示器样式（使用游戏的主色调作为背景色）
        self.game_indicator.setStyleSheet(
            f"background-color: {accent}; color: #000000; border-radius: 10px; "
            f"padding: 4px 12px; font-size: 12px; font-weight: bold;"
        )

        # =========================================================================
        # 加载该游戏的第一个账号
        # =========================================================================

        # 从数据库获取该游戏的所有账号列表
        # get_accounts(game) 返回 UID 字符串列表（如 ["100000001", "100000002"]）
        accounts = self.db.get_accounts(game)

        # 如果有账号，选择第一个；如果没有账号，设为 None
        # 使用列表推导的简写形式（条件表达式）
        self.current_account = accounts[0] if accounts else None

        # 刷新当前显示的页面，使页面内容与新游戏/账号状态同步
        self._refresh_current_page()

    # ---------------------------------------------------------------------------
    # 导航切换处理
    # ---------------------------------------------------------------------------

    def _on_nav_changed(self, page: str):
        """处理导航按钮切换事件。

        当用户点击左侧导航栏的功能按钮时调用此方法。

        参数说明：
            page (str): 页面键名（"home"/"import"/"manual"/"stats"/"chart"/"settings"）

        处理流程：
        1. 将页面键名转换为 QStackedWidget 的索引
        2. 切换 QStackedWidget 显示对应的页面
        3. 更新所有导航按钮的选中状态（只高亮当前选中的）
        4. 刷新当前页面的数据
        """
        # 页面键名到 QStackedWidget 索引的映射表
        # 索引顺序与 _init_ui() 中 addWidget 的顺序一致
        pages = {
            "home": 0,     # 总览首页
            "import": 1,   # 数据导入
            "manual": 2,   # 手动添加
            "stats": 3,    # 统计分析
            "chart": 4,    # 图表展示
            "settings": 5  # 设置
        }

        # 切换页面堆叠部件的当前显示页面
        # setCurrentIndex() 会自动隐藏当前页面并显示目标页面
        # 如果索引无效（超出范围），则不做任何操作
        self.page_stack.setCurrentIndex(pages.get(page, 0))

        # 更新导航按钮的选中状态
        # 只有当前选中的按钮高亮，其他按钮取消选中
        for key, btn in self.nav_buttons.items():
            btn.setChecked(key == page)

        # 刷新当前页面的数据（确保显示最新内容）
        self._refresh_current_page()

    # ---------------------------------------------------------------------------
    # 页面刷新
    # ---------------------------------------------------------------------------

    def _refresh_current_page(self):
        """刷新当前显示的页面。

        工作原理：
        1. 获取当前显示的页面 widget（通过 page_stack 的当前索引）
        2. 使用 hasattr 检查该页面是否有 refresh() 方法
        3. 如果有，则调用 refresh() 刷新页面数据

        设计模式：
        - 这是一个简化版的"访问者模式"
        - 各页面控件如果需要响应全局状态变化，
          应当实现 refresh() 方法
        - hasattr 检查确保即使某个页面没有 refresh() 方法也不会报错

        调用时机：
        - 游戏切换后（_on_game_changed）
        - 导航页面切换后（_on_nav_changed）
        - 账号切换后（set_account）
        - 全局刷新时（refresh_all）
        """
        # 获取当前显示的页面 widget
        # currentIndex() 返回当前页的索引（int）
        # widget(index) 返回索引对应的 QWidget
        page = self.page_stack.widget(self.page_stack.currentIndex())

        # 使用 hasattr 检查页面是否有 refresh() 方法
        # 这是 Python 的鸭子类型（Duck Typing）检查
        # 如果页面实现了 refresh()，则调用它；否则静默跳过
        if hasattr(page, 'refresh'):
            page.refresh()

    # ---------------------------------------------------------------------------
    # 公共访问方法
    # ---------------------------------------------------------------------------

    def get_current_game(self) -> str:
        """获取当前选中的游戏 ID。

        返回值：
            str: 游戏 ID，如 "genshin"、"star_rail"、"arknights"

        使用场景：
            各页面控件通过 self.parent().get_current_game() 调用此方法
            获取当前游戏信息，用于数据库查询和数据显示。
        """
        return self.current_game

    def get_current_account(self):
        """获取当前选中的账号 UID。

        返回值：
            str | None: 账号 UID 字符串，如果没有选中账号则返回 None

        使用场景：
            各页面控件通过 self.parent().get_current_account() 调用此方法
            获取当前账号信息，用于过滤抽卡记录。
        """
        return self.current_account

    def set_account(self, account):
        """设置当前账号并刷新页面。

        参数说明：
            account (str | None): 账号 UID 字符串

        使用场景：
            各页面（如导入页面）在获取/创建新账号后调用此方法，
            通知主窗口切换到该账号并刷新显示。

        注意：此方法只更新内存中的状态，不写入配置文件。
        账号的选择不持久化，因为不同游戏可能有不同账号。
        """
        self.current_account = account
        self._refresh_current_page()  # 刷新当前页面以显示新账号的数据

    def refresh_all(self):
        """全局刷新 - 重新触发游戏切换流程。

        这相当于模拟一次游戏切换，使所有状态和 UI 重新同步。

        使用场景：
            外部模块（如数据库导入完成后）调用此方法，
            确保主窗口和所有页面都反映最新的数据状态。

        内部实现：
            调用 _on_game_changed 并传入当前游戏 ID，
            这会触发完整的状态更新、按钮刷新、页面刷新流程。
        """
        self._on_game_changed(self.current_game)
