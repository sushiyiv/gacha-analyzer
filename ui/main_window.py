"""主窗口 - 左侧导航 + 右侧内容区"""

import os
from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
    QPushButton, QLabel, QFrame, QFileDialog, QMessageBox,
    QMenu, QCheckBox, QDialog, QDialogButtonBox, QListWidget, QListWidgetItem,
    QScrollArea
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon, QAction

from ui.widgets.game_list import GameListDelegate, GameListWidget, CheckListDelegate

from core.database import Database
from core.config import Config
from core.models import GAME_NAMES, GAME_COLORS
from ui.widgets.home_widget import HomeWidget
from ui.widgets.import_widget import ImportWidget
from ui.widgets.manual_add_widget import ManualAddWidget
from ui.widgets.stats_widget import StatsWidget
from ui.widgets.chart_widget import ChartWidget
from ui.widgets.settings_widget import SettingsWidget


class MainWindow(QMainWindow):
    """主窗口"""

    def __init__(self):
        super().__init__()
        self.db = Database()
        self.config = Config()
        self.current_account = None
        self.current_game = "genshin"  # 默认值，后面会更新

        self._init_ui()
        self._load_style()

        # 启动时自动更新明日方舟卡池分类
        self._auto_update_arknights_pools()

        # 启动时恢复上次选择的游戏，没有则用第一个可见游戏
        last_game = self.config.get("last_game", "")
        if last_game and last_game in self._visible_games:
            self._on_game_changed(last_game)
        else:
            first = self._visible_games[0] if self._visible_games else "genshin"
            self._on_game_changed(first)

    def _auto_update_arknights_pools(self):
        """启动时自动更新明日方舟卡池分类"""
        from PySide6.QtCore import QTimer

        def do_update():
            try:
                from ui.widgets.settings_widget import SettingsWidget
                # 创建临时实例来调用更新方法
                settings = SettingsWidget(self)
                updated = settings._do_update_arknights_pool_types()
                if updated > 0:
                    print(f"自动更新明日方舟卡池分类: {updated} 条记录")
            except Exception as e:
                print(f"自动更新卡池分类失败: {e}")

        # 使用 QTimer 延迟执行，避免阻塞启动
        QTimer.singleShot(1000, do_update)

    def _init_ui(self):
        self.setWindowTitle("穷观阵 -- 乾坤清策，否极泰来")
        self.setMinimumSize(1100, 700)
        self.resize(1200, 750)

        icon_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # ===== 左侧导航 =====
        nav_widget = QWidget()
        nav_widget.setObjectName("nav_widget")
        nav_widget.setFixedWidth(200)
        nav_layout = QVBoxLayout(nav_widget)
        nav_layout.setContentsMargins(0, 0, 0, 0)
        nav_layout.setSpacing(0)

        # 游戏选择区
        game_frame = QFrame()
        game_layout = QVBoxLayout(game_frame)
        game_layout.setContentsMargins(12, 8, 12, 8)
        game_layout.setSpacing(2)

        game_label = QLabel("选择游戏")
        game_label.setStyleSheet("color: #888; font-size: 11px; padding-left: 4px;")
        game_layout.addWidget(game_label)

        self._game_order = self.config.get("game_order", list(GAME_NAMES.keys()))
        self._game_order = [g for g in self._game_order if g in GAME_NAMES]
        for g in GAME_NAMES:
            if g not in self._game_order:
                self._game_order.append(g)
        self._visible_games = self.config.get("visible_games", list(GAME_NAMES.keys()))
        self._visible_games = [g for g in self._visible_games if g in GAME_NAMES]

        # 游戏按钮滚动区域
        self._game_scroll = QScrollArea()
        self._game_scroll.setWidgetResizable(True)
        self._game_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._game_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        self._game_layout = QVBoxLayout(scroll_content)
        self._game_layout.setContentsMargins(0, 0, 0, 0)
        self._game_layout.setSpacing(2)

        self.game_buttons = {}
        self._rebuild_game_buttons()
        self._game_layout.addStretch()

        self._game_scroll.setWidget(scroll_content)
        self._game_scroll.setMinimumHeight(220)
        game_layout.addWidget(self._game_scroll)

        # 更多游戏按钮（常驻）
        more_btn = QPushButton("游戏管理")
        more_btn.setObjectName("game_button")
        more_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        more_btn.setStyleSheet("""
            QPushButton {
                color: #1a73e8; font-size: 12px; font-weight: bold;
                border: 1px solid #1a73e8; border-radius: 6px;
                padding: 10px 4px; text-align: center; min-height: 20px;
            }
            QPushButton:hover { background-color: #e8f0fe; }
        """)
        more_btn.clicked.connect(self._show_game_manager)
        game_layout.addWidget(more_btn)

        nav_layout.addWidget(game_frame)

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("color: #e0e0e0; margin: 8px 16px;")
        nav_layout.addWidget(line)

        # 导航按钮
        self.nav_buttons = {}
        nav_items = [
            ("home", "总览"), ("import", "获取数据"), ("manual", "手动添加"),
            ("stats", "统计分析"), ("chart", "图表展示"), ("settings", "设置"),
        ]
        for key, text in nav_items:
            btn = QPushButton(text)
            btn.setObjectName("nav_button")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda checked, k=key: self._on_nav_changed(k))
            nav_layout.addWidget(btn)
            self.nav_buttons[key] = btn

        nav_layout.addStretch()

        version = QLabel("v1.0.0")
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setStyleSheet("color: #bbb; font-size: 11px; padding: 8px;")
        nav_layout.addWidget(version)

        main_layout.addWidget(nav_widget)

        # ===== 右侧内容区 =====
        content_widget = QWidget()
        content_widget.setStyleSheet("background-color: #f5f5f5;")
        content_layout = QVBoxLayout(content_widget)
        content_layout.setContentsMargins(16, 16, 16, 16)

        top_bar = QHBoxLayout()
        top_bar.addStretch()

        self.game_indicator = QLabel()
        self.game_indicator.setStyleSheet(
            "background-color: #1a73e8; color: #000000; border-radius: 10px; "
            "padding: 4px 12px; font-size: 12px; font-weight: bold;"
        )
        top_bar.addWidget(self.game_indicator)
        content_layout.addLayout(top_bar)

        self.page_stack = QStackedWidget()
        content_layout.addWidget(self.page_stack)

        self.home_page = HomeWidget(self)
        self.import_page = ImportWidget(self)
        self.manual_page = ManualAddWidget(self)
        self.stats_page = StatsWidget(self)
        self.chart_page = ChartWidget(self)
        self.settings_page = SettingsWidget(self)

        for page in [self.home_page, self.import_page, self.manual_page,
                     self.stats_page, self.chart_page, self.settings_page]:
            self.page_stack.addWidget(page)

        main_layout.addWidget(content_widget)

        self.nav_buttons["home"].setChecked(True)
        if self.game_buttons:
            # 选中第一个可见游戏（不是 _game_order 第一个，可能被隐藏了）
            first_visible = next((g for g in self._game_order if g in self.game_buttons), None)
            if first_visible:
                self.game_buttons[first_visible].setChecked(True)

    def _rebuild_game_buttons(self):
        """重建游戏按钮列表"""
        for btn in self.game_buttons.values():
            btn.setParent(None)
            btn.deleteLater()
        self.game_buttons.clear()

        # 清除布局中的所有项（包括旧的 stretch）
        while self._game_layout.count():
            item = self._game_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        for game_id in self._game_order:
            if game_id not in self._visible_games:
                continue
            btn = self._create_game_button(game_id)
            self._game_layout.addWidget(btn)
            self.game_buttons[game_id] = btn

        self._game_layout.addStretch()

    def _create_game_button(self, game_id):
        btn = QPushButton(GAME_NAMES.get(game_id, game_id))
        btn.setObjectName("game_button")
        btn.setCheckable(True)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda checked, g=game_id: self._on_game_changed(g))
        return btn

    def _show_game_manager(self):
        """显示游戏管理对话框 - 双击选择，长按拖动"""
        dialog = QDialog(self)
        dialog.setWindowTitle("管理游戏")
        dialog.setMinimumWidth(300)
        dialog.setMinimumHeight(350)
        layout = QVBoxLayout(dialog)

        header = QLabel("点击选择/取消，长按拖动排序:")
        header.setStyleSheet("font-size: 12px; font-weight: bold; padding: 4px;")
        layout.addWidget(header)

        list_widget = GameListWidget()
        list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        list_widget.setItemDelegate(CheckListDelegate(list_widget))
        list_widget.setStyleSheet("QListWidget { background-color: #ffffff; border: 1px solid #e0e0e0; }")

        for gid in self._game_order:
            item = QListWidgetItem(GAME_NAMES.get(gid, gid))
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(Qt.ItemDataRole.UserRole, gid)
            item.setData(Qt.ItemDataRole.UserRole + 1, gid in self._visible_games)
            list_widget.addItem(item)

        layout.addWidget(list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            new_order = []
            new_visible = []
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                gid = item.data(Qt.ItemDataRole.UserRole)
                new_order.append(gid)
                if item.data(Qt.ItemDataRole.UserRole + 1):
                    new_visible.append(gid)
            self._game_order = new_order
            self._visible_games = new_visible if new_visible else [new_order[0]]
            self.config.set("game_order", self._game_order)
            self.config.set("visible_games", self._visible_games)
            self.config.save()
            self._rebuild_game_buttons()
            # 当前游戏被隐藏时，跳到第一个可见游戏
            if self.current_game not in self._visible_games:
                self._on_game_changed(self._visible_games[0])
            else:
                self.game_buttons[self.current_game].setChecked(True)


    def _load_style(self):
        qss_path = os.path.join(os.path.dirname(__file__), "resources", "styles", "default.qss")
        if os.path.exists(qss_path):
            with open(qss_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())

    def _on_game_changed(self, game: str):
        self.current_game = game
        self.config.set("last_game", game)
        self.config.save()
        for gid, btn in self.game_buttons.items():
            btn.setChecked(gid == game)

        colors = GAME_COLORS.get(game, {})
        accent = colors.get("primary", "#1a73e8")
        self.game_indicator.setText(f"  {GAME_NAMES.get(game, game)}  ")
        self.game_indicator.setStyleSheet(
            f"background-color: {accent}; color: #000000; border-radius: 10px; "
            f"padding: 4px 12px; font-size: 12px; font-weight: bold;"
        )

        accounts = self.db.get_accounts(game)
        self.current_account = accounts[0] if accounts else None
        self._refresh_current_page()

    def _on_nav_changed(self, page: str):
        pages = {"home": 0, "import": 1, "manual": 2, "stats": 3, "chart": 4, "settings": 5}
        self.page_stack.setCurrentIndex(pages.get(page, 0))
        for key, btn in self.nav_buttons.items():
            btn.setChecked(key == page)
        self._refresh_current_page()

    def _refresh_current_page(self):
        page = self.page_stack.widget(self.page_stack.currentIndex())
        if hasattr(page, 'refresh'):
            page.refresh()

    def get_current_game(self) -> str:
        return self.current_game

    def get_current_account(self):
        return self.current_account

    def set_account(self, account):
        self.current_account = account
        self._refresh_current_page()

    def refresh_all(self):
        self._on_game_changed(self.current_game)




