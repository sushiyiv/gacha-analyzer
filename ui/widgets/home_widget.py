"""首页/总览页面 - 统计与卡池标签页合并"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView,
    QComboBox, QScrollArea, QTabWidget, QTabBar, QProgressBar,
    QPushButton, QDialog, QDialogButtonBox, QListWidget, QListWidgetItem
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFont, QColor

from ui.widgets.game_list import GameListDelegate, GameListWidget, CheckListDelegate
import shiboken6

from core.database import Database
from core.config import Config
from core.models import BANNER_CONFIGS, get_max_rarity, get_pity_rarity, get_pool_names, get_mechanic_type


class HomeWidget(QWidget):
    """首页"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.db = Database()
        self.config = Config()
        self._tabs = []
        self._current_game = None
        self._tab_connected = False
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 账号选择区
        account_bar = QHBoxLayout()
        account_bar.addWidget(QLabel("账号:"))
        self.account_combo = QComboBox()
        self.account_combo.setMinimumWidth(200)
        self.account_combo.currentIndexChanged.connect(self._on_account_changed)
        account_bar.addWidget(self.account_combo)

        self._show_uid = True
        self._uid_btn = QPushButton("隐藏UID")
        self._uid_btn.setFixedHeight(28)
        self._uid_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._uid_btn.setStyleSheet("font-size: 11px; color: #888;")
        self._uid_btn.clicked.connect(self._toggle_uid)
        account_bar.addWidget(self._uid_btn)

        self._pool_plus_btn = QPushButton("卡池管理")
        self._pool_plus_btn.setFixedHeight(28)
        self._pool_plus_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._pool_plus_btn.setStyleSheet("""
            QPushButton {
                font-size: 11px; font-weight: bold; color: #1a73e8;
                border: 1px solid #1a73e8; border-radius: 6px;
                padding: 0 10px;
            }
            QPushButton:hover { background: #e8f0fe; }
        """)
        self._pool_plus_btn.clicked.connect(self._on_pool_plus_clicked)
        account_bar.addWidget(self._pool_plus_btn)

        # 星级筛选按钮
        self._star_filter_btn = QPushButton("星级筛选")
        self._star_filter_btn.setFixedHeight(28)
        self._star_filter_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._star_filter_btn.setStyleSheet("""
            QPushButton {
                font-size: 11px; font-weight: bold; color: #1a73e8;
                border: 1px solid #1a73e8; border-radius: 6px;
                padding: 0 10px;
            }
            QPushButton:hover { background: #e8f0fe; }
        """)
        self._star_filter_btn.clicked.connect(self._on_star_filter_clicked)
        account_bar.addWidget(self._star_filter_btn)

        account_bar.addStretch()
        layout.addLayout(account_bar)

        # 滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)
        scroll_layout.setSpacing(12)

        # ===== 卡池标签页 =====

        self.pool_tabs = QTabWidget()
        self.pool_tabs.setTabPosition(QTabWidget.TabPosition.North)
        self.pool_tabs.setStyleSheet("""
            QTabWidget::pane { border: 1px solid #e0e0e0; border-radius: 8px; background: white; }
            QTabBar::tab { padding: 8px 16px; margin-right: 2px; border: 1px solid #e0e0e0;
                          border-bottom: none; border-radius: 8px 8px 0 0; background: #f5f5f5;
                          color: #333333; }
            QTabBar::tab:selected { background: white; font-weight: bold; color: #1a73e8; }
        """)

        # 统计项模板
        self._stat_full = [("total", "总抽数", "#333"), ("star5", "最高星数", "#FF6B35"),
                           ("up_ratio", "UP/总金数", "#E91E63"), ("win_rate", "小保底不歪率", "#4CAF50"),
                           ("avg_pity", "平均出金", "#FF9800"), ("avg_featured", "每UP需", "#1a73e8")]
        self._stat_simple = [("total", "总抽数", "#333"), ("star5", "最高星数", "#FF6B35"),
                             ("avg_pity", "平均出金", "#FF9800")]

        scroll_layout.addWidget(self.pool_tabs)

        # 初始化默认标签页
        self._rebuild_tabs("genshin")

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

    def _create_stat_item(self, title, value, color):
        """创建单个统计项"""
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(0, 0, 0, 0)

        value_label = QLabel(value)
        value_label.setObjectName("stat_number")
        value_label.setStyleSheet(f"color: {color}; font-size: 24px; font-weight: bold;")
        value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(value_label)

        title_label = QLabel(title)
        title_label.setObjectName("stat_label")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)

        frame._value_label = value_label
        return frame

    def _create_pool_tab(self, name, pool_type, stat_keys, pity_pools, pool_name_map=None, pool_name_filter=None, pool_names_by_type=None):
        """创建卡池标签页内容（统计行 + 表格 + 保底进度）"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        # 统计行
        stats_frame = QFrame()
        stats_frame.setObjectName("card")
        stats_layout = QHBoxLayout(stats_frame)
        stats_layout.setContentsMargins(20, 10, 20, 10)
        stats_layout.setSpacing(40)

        stat_items = {}
        for key, title, color in stat_keys:
            item = self._create_stat_item(title, "-", color)
            stats_layout.addWidget(item)
            stat_items[key] = item

        stats_layout.addStretch()
        layout.addWidget(stats_frame)

        # 只有终末地武器池和明日方舟独立寻访使用卡片模式（按具体卡池名分区块）
        has_multiple_pools = False
        cards_container = None
        current_game = self.main_window.get_current_game()
        use_card_mode = (current_game == "endfield" and pool_type == "weapon") or \
                        (current_game == "arknights" and pool_type == "limited")
        if use_card_mode and pool_names_by_type and pool_type in pool_names_by_type:
            pool_names = pool_names_by_type[pool_type]
            if len(pool_names) >= 1:
                has_multiple_pools = True
                cards_scroll = QScrollArea()
                cards_scroll.setWidgetResizable(True)
                cards_scroll.setFrameShape(QFrame.Shape.NoFrame)
                cards_container = QWidget()
                cards_layout = QVBoxLayout(cards_container)
                cards_layout.setContentsMargins(0, 0, 0, 0)
                cards_layout.setSpacing(12)
                cards_scroll.setWidget(cards_container)
                layout.addWidget(cards_scroll, 1)

        # 出货记录表格（单 pool_name 时使用）
        table = QTableWidget()
        current_game = self.main_window.get_current_game()
        if current_game == "arknights":
            table.setColumnCount(5)
            table.setHorizontalHeaderLabels(["序号", "名称", "星级", "保底计数", "卡池"])
            header = table.horizontalHeader()
            header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
            header.setSectionResizeMode(2, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
            header.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
            table.setColumnWidth(0, 50)
            table.setColumnWidth(2, 110)
            table.setColumnWidth(3, 80)
        else:
            table.setColumnCount(6)
            table.setHorizontalHeaderLabels(["序号", "名称", "星级", "是否UP", "保底计数", "时间"])
            header = table.horizontalHeader()
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

        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)
        table.setMinimumHeight(200)
        table.horizontalHeader().setStretchLastSection(True)

        # 只有非卡片模式才添加表格和保底条
        pity_frames = []
        if not has_multiple_pools:
            layout.addWidget(table)

            fallback_names = {"character": "角色池", "weapon": "武器池", "standard": "常驻池",
                              "standard_character": "常驻角色", "standard_weapon": "常驻武器", "collab": "联动池"}
            name_map = pool_name_map or fallback_names
            if pity_pools is not None:
                pools_to_show = pity_pools if pity_pools else ["character", "weapon", "standard"]
                for p_type in pools_to_show:
                    pf = self._create_pity_bar(name_map.get(p_type, p_type))
                    layout.addWidget(pf)
                    pity_frames.append((p_type, pf))

        # 保存引用
        widget._table = table
        widget._stat_items = stat_items
        widget._pity_frames = pity_frames
        widget._pool_type = pool_type
        widget._pool_name_filter = pool_name_filter
        widget._cards_container = cards_container
        widget._active_sub_filter = None

        return widget

    def _create_pool_card(self, pool_name, pool_type, game, records, account, star_filter, max_rarity):
        """为单个具体卡池创建卡片区块"""
        card = QFrame()
        card.setObjectName("card")
        card.setStyleSheet("""
            QFrame#card {
                background: white; border: 1px solid #e0e0e0;
                border-radius: 8px; padding: 0px;
            }
        """)
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(16, 12, 16, 12)
        card_layout.setSpacing(8)

        # 卡池名称
        name_label = QLabel(pool_name)
        name_label.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        name_label.setStyleSheet("color: #333; border: none;")
        card_layout.addWidget(name_label)

        # 统计行（最高星数、不歪率、平均出金）
        sorted_records = sorted(records, key=lambda r: (r.time, r.id))
        total = len(records)
        five_stars = [r for r in sorted_records if r.rarity == max_rarity]
        star5_count = len(five_stars)

        stats_row = QHBoxLayout()
        stats_row.setSpacing(24)

        def _add_stat(label, value, color="#333"):
            frame = QFrame()
            frame.setStyleSheet("border: none;")
            fl = QVBoxLayout(frame)
            fl.setContentsMargins(0, 0, 0, 0)
            fl.setSpacing(2)
            val = QLabel(value)
            val.setStyleSheet(f"color: {color}; font-size: 20px; font-weight: bold;")
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl = QLabel(label)
            lbl.setStyleSheet("color: #666666; font-size: 11px;")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            fl.addWidget(val)
            fl.addWidget(lbl)
            stats_row.addWidget(frame)
            return val

        star_label = "★" * max_rarity
        val_star = _add_stat(star_label, str(star5_count), "#FF6B35")

        if star5_count > 0:
            avg_pity = f"{round(total / star5_count, 1)}抽"
        else:
            avg_pity = "-"

        val_avg = _add_stat("平均出金", avg_pity, "#FF9800")

        # 已垫抽数
        mechanic_type = get_mechanic_type(game, pool_type, pool_name)
        config = BANNER_CONFIGS.get((game, mechanic_type))
        if not config:
            config = BANNER_CONFIGS.get((game, pool_type))
        if config:
            pity = self.db.get_last_5star_pity(account.id, pool_type, game, pool_name=pool_name)
            _add_stat("已垫", f"{pity}抽", "#1a73e8")

        stats_row.addStretch()
        card_layout.addLayout(stats_row)

        # 记录表格
        table = QTableWidget()
        if game == "arknights":
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
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.verticalHeader().setVisible(False)

        filtered = [r for r in sorted_records if r.rarity in star_filter]
        filtered.reverse()
        table.setRowCount(len(filtered))

        # 自动高度：最多显示5行，少于5行按实际高度
        row_height = 28
        header_height = 32
        visible_rows = min(len(filtered), 5)
        if visible_rows > 0:
            table.setFixedHeight(header_height + row_height * visible_rows)
        else:
            table.setFixedHeight(header_height + row_height)

        star_colors = {3: "#888", 4: "#9B59B6", 5: "#FFD700", 6: "#FF6B35"}
        for i, r in enumerate(filtered):
            idx_item = QTableWidgetItem(str(i + 1))
            idx_item.setForeground(QColor("#333333"))
            table.setItem(i, 0, idx_item)

            name_item = QTableWidgetItem(r.item_name)
            name_item.setForeground(QColor("#333333"))
            table.setItem(i, 1, name_item)

            si = QTableWidgetItem("★" * r.rarity)
            si.setForeground(QColor(star_colors.get(r.rarity, "#FF6B35")))
            table.setItem(i, 2, si)
            if game == "arknights":
                time_item = QTableWidgetItem(r.time[:16] if r.time else "")
                time_item.setForeground(QColor("#333333"))
                table.setItem(i, 3, time_item)
            else:
                ui = QTableWidgetItem("是" if r.is_featured else "否")
                ui.setForeground(QColor("#FF6B35" if r.is_featured else "#4CAF50"))
                table.setItem(i, 3, ui)
                time_item = QTableWidgetItem(r.time[:16] if r.time else "")
                time_item.setForeground(QColor("#333333"))
                table.setItem(i, 4, time_item)

        card_layout.addWidget(table)

        return card, {"star": val_star, "avg": val_avg}

    def _create_pity_bar(self, pool_name):
        """创建保底进度条"""
        frame = QFrame()
        frame.setObjectName("card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(15, 10, 15, 10)

        # 标题行
        title_layout = QHBoxLayout()
        title_label = QLabel(pool_name)
        title_label.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        title_label.setStyleSheet("color: #333333;")
        title_layout.addWidget(title_label)

        pity_text = QLabel("0/90")
        pity_text.setFont(QFont("Microsoft YaHei", 11))
        pity_text.setStyleSheet("color: #333333;")
        title_layout.addWidget(pity_text)

        title_layout.addStretch()
        layout.addLayout(title_layout)

        # 进度条
        progress = QProgressBar()
        progress.setFixedHeight(20)
        progress.setTextVisible(True)
        progress.setFormat("%v/%m")
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

        frame._pity_text = pity_text
        frame._progress = progress
        return frame

    def _toggle_uid(self):
        self._show_uid = not self._show_uid
        self._uid_btn.setText("隐藏UID" if self._show_uid else "显示UID")
        self.refresh()

    def _on_account_changed(self, index):
        account_id = self.account_combo.currentData()
        if account_id:
            account = self.db.get_account_by_id(account_id)
            self.main_window.set_account(account)
            self.refresh()

    def _rebuild_tabs(self, game, account=None):
        """根据游戏重建标签页"""
        self.pool_tabs.blockSignals(True)
        old_tabs = list(self._tabs)
        self._tabs.clear()
        self.pool_tabs.clear()

        # 强制释放旧标签页
        for tab in old_tabs:
            tab._stat_items.clear()
            tab._pity_frames.clear()
            tab._table = None
            tab.setParent(None)
            shiboken6.delete(tab)

        # 读取用户的卡池显示/顺序配置
        all_pools = get_pool_names(game)
        visible_pools = self.config.get(f"pool_visible.{game}", [pt for pt, _ in all_pools])
        pool_order = self.config.get(f"pool_order.{game}", [pt for pt, _ in all_pools])
        pool_name_map = dict(all_pools)

        # 按用户顺序筛选可见卡池
        ordered_pools = []
        for pt in pool_order:
            if pt in visible_pools and pt in pool_name_map:
                ordered_pools.append((pt, pool_name_map[pt]))
        for pt, name in all_pools:
            if pt not in [p for p, _ in ordered_pools] and pt in visible_pools:
                ordered_pools.append((pt, name))

        # 获取已有记录，按 pool_type 分组收集 pool_name
        pool_names_by_type = {}  # {pool_type: set(pool_name)}
        if account:
            existing = self.db.get_records(account.id)
            for r in existing:
                if r.pool_name:
                    pool_names_by_type.setdefault(r.pool_type, set()).add(r.pool_name)

        # "全部"标签页
        all_pool_types = [pt for pt, _ in ordered_pools]
        # 明日方舟不显示UP/总金数、小保底不歪率、每UP需
        if game == "arknights":
            stat_keys = self._stat_simple
        else:
            stat_keys = self._stat_full
        tab = self._create_pool_tab("全部", None, stat_keys, all_pool_types, pool_name_map, pool_names_by_type=pool_names_by_type)
        self._tabs.append(tab)
        self.pool_tabs.addTab(tab, "全部")

        # 各卡池标签页
        for pool_type, name in ordered_pools:
            # 明日方舟不显示UP/总金数、小保底不歪率、每UP需
            if game == "arknights":
                stat_keys = self._stat_simple
            else:
                stat_keys = self._stat_full if pool_type in ("character", "weapon") else self._stat_simple
            pool_names = pool_names_by_type.get(pool_type, set())
            tab = self._create_pool_tab(name, pool_type, stat_keys, None, pool_name_map, pool_names_by_type=pool_names_by_type)
            self._tabs.append(tab)
            self.pool_tabs.addTab(tab, name)

        self.pool_tabs.blockSignals(False)

        # 只连接一次信号，避免重复连接
        if not self._tab_connected:
            self.pool_tabs.currentChanged.connect(self._on_tab_changed)
            self._tab_connected = True

    def _on_pool_plus_clicked(self):
        """点击"+"按钮，弹出卡池管理"""
        game = self.main_window.get_current_game()
        current_tab = self.pool_tabs.currentIndex()
        current_pool_type = self._tabs[current_tab]._pool_type if current_tab < len(self._tabs) else None

        old_visible = self.config.get(f"pool_visible.{game}", [])
        old_order = self.config.get(f"pool_order.{game}", [])

        self._show_pool_manager(game)

        new_visible = self.config.get(f"pool_visible.{game}", [])
        new_order = self.config.get(f"pool_order.{game}", [])
        if old_visible == new_visible and old_order == new_order:
            return  # 没改动

        # 有改动，重建标签页（暂停刷新避免闪烁）
        self.setUpdatesEnabled(False)
        self._current_game = None
        self.refresh()

        # 只有当前卡池被隐藏才跳"全部"，否则留在当前卡池
        if current_pool_type is not None and current_pool_type not in new_visible:
            self.pool_tabs.setCurrentIndex(0)
        elif current_pool_type is not None:
            for i, tab in enumerate(self._tabs):
                if tab._pool_type == current_pool_type:
                    self.pool_tabs.setCurrentIndex(i)
                    break

        self.setUpdatesEnabled(True)

    def _on_tab_changed(self, index):
        """标签页切换事件"""
        if 0 <= index < self.pool_tabs.count():
            self.refresh()

    def _show_pool_manager(self, game):
        """显示卡池管理对话框"""
        all_pools = get_pool_names(game)
        # 确保配置中包含所有卡池
        default_visible = [pt for pt, _ in all_pools]
        default_order = [pt for pt, _ in all_pools]
        current_visible = self.config.get(f"pool_visible.{game}", default_visible)
        current_order = self.config.get(f"pool_order.{game}", default_order)
        pool_name_map = dict(all_pools)

        # 确保所有卡池都在顺序列表中（但不强制加回可见列表）
        for pt, _ in all_pools:
            if pt not in current_order:
                current_order.append(pt)

        dialog = QDialog(self)
        dialog.setWindowTitle("卡池管理")
        dialog.setMinimumWidth(300)
        dialog.setMinimumHeight(350)
        layout = QVBoxLayout(dialog)

        header = QLabel("点击选择/取消，长按拖动排序:")
        header.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px;")
        layout.addWidget(header)

        list_widget = GameListWidget()
        list_widget.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        list_widget.setDefaultDropAction(Qt.DropAction.MoveAction)
        list_widget.setItemDelegate(CheckListDelegate(list_widget))
        list_widget.setStyleSheet("QListWidget { background-color: #ffffff; border: 1px solid #e0e0e0; }")

        # 按当前顺序填充
        for pt in current_order:
            if pt in pool_name_map:
                item = QListWidgetItem(pool_name_map[pt])
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
                item.setData(Qt.ItemDataRole.UserRole, pt)
                item.setData(Qt.ItemDataRole.UserRole + 1, pt in current_visible)
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
                pt = item.data(Qt.ItemDataRole.UserRole)
                new_order.append(pt)
                if item.data(Qt.ItemDataRole.UserRole + 1):
                    new_visible.append(pt)
            self.config.set(f"pool_order.{game}", new_order)
            self.config.set(f"pool_visible.{game}", new_visible if new_visible else [new_order[0]])
            self.config.save()

    def _refresh_cards(self, tab, records, account, game, max_rarity, star_filter):
        """刷新卡片模式的内容"""
        cards_container = tab._cards_container
        if not cards_container:
            return

        # 清空旧卡片
        layout = cards_container.layout()
        while layout.count():
            child = layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        # 按 pool_name 分组
        groups = {}
        for r in records:
            pn = r.pool_name or "未知卡池"
            groups.setdefault(pn, []).append(r)

        if not groups:
            no_data = QLabel("暂无数据")
            no_data.setStyleSheet("color: #999; font-size: 13px; padding: 40px;")
            no_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
            layout.addWidget(no_data)
            return

        pool_type = tab._pool_type

        # 按最新记录时间倒序排列（最新的在上面）
        def _latest_time(recs):
            times = [r.time for r in recs if r.time]
            return max(times) if times else ""
        sorted_groups = sorted(groups.items(), key=lambda x: _latest_time(x[1]), reverse=True)

        for pn, pool_records in sorted_groups:
            card, stat_refs = self._create_pool_card(
                pn, pool_type, game, pool_records, account, star_filter, max_rarity
            )
            layout.addWidget(card)

        layout.addStretch()

    def _refresh_tab(self, tab):
        """刷新单个标签页的数据"""
        account = self.main_window.get_current_account()
        if not account:
            return
        game = self.main_window.get_current_game()
        all_records = self.db.get_records(account.id)
        max_rarity = get_max_rarity(game)
        star_filter = self._get_star_filter(game)

        pool_type = tab._pool_type
        pool_name_filter = getattr(tab, '_pool_name_filter', None)
        active_sub_filter = getattr(tab, '_active_sub_filter', None)

        if pool_type is None:
            records = all_records
        elif active_sub_filter:
            records = [r for r in all_records if r.pool_type == pool_type and r.pool_name == active_sub_filter]
        elif pool_name_filter:
            records = [r for r in all_records if r.pool_type == pool_type and r.pool_name == pool_name_filter]
        else:
            records = [r for r in all_records if r.pool_type == pool_type]

        # 检查是否有卡片容器
        cards_container = getattr(tab, '_cards_container', None)
        if cards_container:
            # 卡片模式：为每个 pool_name 创建独立卡片
            self._refresh_cards(tab, records, account, game, max_rarity, star_filter)
        else:
            # 普通模式：单表格
            self._update_tab_stats(tab, records, account, game)

    def _get_star_filter(self, game: str) -> list:
        """获取当前游戏的星级筛选设置"""
        max_rarity = get_max_rarity(game)
        # 默认值：终末地/明日方舟显示5-6星，其他游戏显示4-5星
        if game in ("endfield", "arknights"):
            default = [r for r in range(5, max_rarity + 1)]
        else:
            default = [r for r in range(4, max_rarity + 1)]
        return self.config.get(f"star_filter.{game}", default)

    def _on_star_filter_clicked(self):
        """打开星级筛选对话框"""
        game = self.main_window.get_current_game()
        max_rarity = get_max_rarity(game)
        current_filter = self._get_star_filter(game)

        dialog = QDialog(self)
        dialog.setWindowTitle("星级筛选")
        dialog.setMinimumWidth(260)
        dialog.setMinimumHeight(300)
        layout = QVBoxLayout(dialog)

        header = QLabel("点击选择/取消显示的星级:")
        header.setStyleSheet("font-size: 13px; font-weight: bold; padding: 4px;")
        layout.addWidget(header)

        list_widget = GameListWidget()
        list_widget.setItemDelegate(CheckListDelegate(list_widget))
        list_widget.setStyleSheet("QListWidget { background-color: #ffffff; border: 1px solid #e0e0e0; }")

        star_labels = {3: "三星", 4: "四星", 5: "五星", 6: "六星"}
        for star in range(max_rarity, 0, -1):
            label = f"{'★' * star}  {star_labels.get(star, f'{star}星')}"
            item = QListWidgetItem(label)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsUserCheckable)
            item.setData(Qt.ItemDataRole.UserRole, star)
            item.setData(Qt.ItemDataRole.UserRole + 1, star in current_filter)
            list_widget.addItem(item)

        layout.addWidget(list_widget)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        if dialog.exec() == QDialog.DialogCode.Accepted:
            selected = []
            for i in range(list_widget.count()):
                item = list_widget.item(i)
                if item.data(Qt.ItemDataRole.UserRole + 1):
                    selected.append(item.data(Qt.ItemDataRole.UserRole))
            if not selected:
                selected = [max_rarity]
            self.config.set(f"star_filter.{game}", selected)
            self.config.save()
            self.refresh()

    def refresh(self):
        """刷新页面"""
        game = self.main_window.get_current_game()

        # 游戏切换时才重建标签页
        need_rebuild = game != self._current_game
        if need_rebuild:
            self.setUpdatesEnabled(False)

        try:
            # 先获取账号（重建标签页时需要知道有哪些独立寻访）
            accounts = self.db.get_accounts(game)
            account = self.main_window.get_current_account()
            if not account and accounts:
                self.main_window.set_account(accounts[0])
                account = accounts[0]

            if need_rebuild:
                self._current_game = game
                self._rebuild_tabs(game, account)

            # 刷新账号列表
            self.account_combo.blockSignals(True)
            self.account_combo.clear()
            accounts = self.db.get_accounts(game)
            current_account = self.main_window.get_current_account()
            current_index = 0
            for i, acc in enumerate(accounts):
                display = acc.nickname if acc.nickname else acc.uid
                if self._show_uid and acc.uid:
                    self.account_combo.addItem(f"{display} ({acc.uid})", acc.id)
                else:
                    self.account_combo.addItem(display, acc.id)
                if current_account and acc.id == current_account.id:
                    current_index = i
            if accounts:
                self.account_combo.setCurrentIndex(current_index)
            self.account_combo.blockSignals(False)

            if not accounts:
                self._clear_stats()
                return

            account = self.main_window.get_current_account()
            if not account:
                self.main_window.set_account(accounts[0])
                account = accounts[0]

            # 获取所有记录
            all_records = self.db.get_records(account.id)
            if not all_records:
                self._clear_stats()
                return

            # 更新各标签页
            max_rarity = get_max_rarity(game)
            star_filter = self._get_star_filter(game)
            for tab in self._tabs:
                pool_type = tab._pool_type
                pool_name_filter = getattr(tab, '_pool_name_filter', None)
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
            if need_rebuild:
                self.setUpdatesEnabled(True)

    def _update_tab_stats(self, tab, records, account, game):
        """更新单个标签页的统计和表格"""
        stat_items = tab._stat_items
        pool_type = tab._pool_type
        max_rarity = get_pity_rarity(game, pool_type)

        sorted_records = sorted(records, key=lambda r: (r.time, r.id))
        total = len(records)
        five_stars = [r for r in sorted_records if r.rarity == max_rarity]
        star5_count = len(five_stars)

        # 总抽数
        if "total" in stat_items:
            stat_items["total"]._value_label.setText(str(total))

        # 五星数
        if "star5" in stat_items:
            stat_items["star5"]._value_label.setText(str(star5_count))

        # UP/总金数
        if "up_ratio" in stat_items:
            up_count = sum(1 for r in five_stars if r.is_featured)
            if star5_count > 0:
                stat_items["up_ratio"]._value_label.setText(f"{up_count}/{star5_count}")
            else:
                stat_items["up_ratio"]._value_label.setText("-")

        # 小保底不歪率
        if "win_rate" in stat_items:
            if star5_count > 0:
                up_count = sum(1 for r in five_stars if r.is_featured)
                win_rate = round(up_count / star5_count * 100, 1)
                stat_items["win_rate"]._value_label.setText(f"{win_rate}%")
            else:
                stat_items["win_rate"]._value_label.setText("-")

        # 平均出金
        if "avg_pity" in stat_items:
            if star5_count > 0:
                avg = round(total / star5_count, 1)
                stat_items["avg_pity"]._value_label.setText(f"{avg}抽")
            else:
                stat_items["avg_pity"]._value_label.setText("-")

        # 每UP需抽数
        if "avg_featured" in stat_items:
            if five_stars:
                avg = sum(r.pity_count for r in five_stars) / len(five_stars)
                stat_items["avg_featured"]._value_label.setText(f"{avg:.1f}抽")
            else:
                stat_items["avg_featured"]._value_label.setText("-")

        # 保底进度条
        pool_name_filter = getattr(tab, '_pool_name_filter', None)
        for p_type, pity_frame in tab._pity_frames:
            config = BANNER_CONFIGS.get((game, p_type))
            if not config:
                pity_frame.setVisible(False)
                continue
            pity_frame.setVisible(True)

            # 独立寻访：池之间不互通不继承，不计算保底
            if p_type == "limited":
                pity_frame._pity_text.setText("卡池之间不互通不继承，故不计算保底")
                pity_frame._progress.setFormat("0/0")
                pity_frame._progress.setMaximum(1)
                pity_frame._progress.setValue(0)
                pity_frame._progress.setStyleSheet("""
                    QProgressBar {
                        border: none; border-radius: 10px; background-color: #e0e0e0;
                        text-align: center; color: #999; font-size: 11px; font-weight: bold;
                    }
                    QProgressBar::chunk { border-radius: 10px; background-color: #e0e0e0; }
                """)
                continue

            pity = self.db.get_last_5star_pity(account.id, p_type, game, pool_name=pool_name_filter or "")
            hard_pity = config.hard_pity
            pity_frame._pity_text.setText(f"已垫{pity}抽 / 保底{hard_pity}抽")
            pity_frame._progress.setMaximum(hard_pity)
            pity_frame._progress.setValue(pity)

            # 绿→黄→红
            ratio = pity / hard_pity if hard_pity > 0 else 0
            if ratio < 0.5:
                color = "#4CAF50"
            elif ratio < 0.8:
                color = "#FFC107"
            else:
                color = "#F44336"
            pity_frame._progress.setStyleSheet(f"""
                QProgressBar {{
                    border: none; border-radius: 10px; background-color: #e0e0e0;
                    text-align: center; color: #333; font-size: 11px; font-weight: bold;
                }}
                QProgressBar::chunk {{
                    border-radius: 10px; background-color: {color};
                }}
            """)

        # 更新表格
        star_filter = self._get_star_filter(game)
        self._update_pool_table(tab._table, sorted_records, max_rarity, star_filter)

    def _update_pool_table(self, table, records, max_rarity=5, star_filter=None):
        """更新卡池表格（最新在前）"""
        if star_filter is None:
            star_filter = [max_rarity]
        filtered = [r for r in records if r.rarity in star_filter]
        filtered.reverse()
        table.setRowCount(len(filtered))

        # 星级颜色映射
        star_colors = {3: "#888", 4: "#9B59B6", 5: "#FFD700", 6: "#FF6B35"}
        col_count = table.columnCount()

        for i, r in enumerate(filtered):
            table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            table.setItem(i, 1, QTableWidgetItem(r.item_name))

            star_item = QTableWidgetItem("★" * r.rarity)
            star_item.setForeground(QColor(star_colors.get(r.rarity, "#FF6B35")))
            table.setItem(i, 2, star_item)

            if col_count == 5:
                # 明日方舟：序号, 名称, 星级, 保底计数, 卡池
                table.setItem(i, 3, QTableWidgetItem(str(r.pity_count)))
                table.setItem(i, 4, QTableWidgetItem(r.pool_name or ""))
            else:
                # 其他游戏：序号, 名称, 星级, 是否UP, 保底计数, 时间
                up_item = QTableWidgetItem("是" if r.is_featured else "否")
                if r.is_featured:
                    up_item.setForeground(QColor("#FF6B35"))
                else:
                    up_item.setForeground(QColor("#4CAF50"))
                table.setItem(i, 3, up_item)
                table.setItem(i, 4, QTableWidgetItem(str(r.pity_count)))
                table.setItem(i, 5, QTableWidgetItem(r.time[:16] if r.time else ""))

    def _clear_stats(self):
        for tab in self._tabs:
            for key, item in tab._stat_items.items():
                item._value_label.setText("-")
            tab._table.setRowCount(0)
            for _, pf in tab._pity_frames:
                pf._pity_text.setText("0/0")
                pf._progress.setValue(0)
            # 清空卡片容器
            cards_container = getattr(tab, '_cards_container', None)
            if cards_container:
                layout = cards_container.layout()
                if layout:
                    while layout.count():
                        child = layout.takeAt(0)
                        if child.widget():
                            child.widget().deleteLater()
