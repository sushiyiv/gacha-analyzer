"""图表展示页面"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QComboBox, QScrollArea, QPushButton, QApplication
)
from PySide6.QtCore import Qt, QEvent
from PySide6.QtGui import QFont

import matplotlib
matplotlib.use('QtAgg')
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False

from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

from core.database import Database
from core.analyzer import StatsAnalyzer, PityAnalyzer, get_rate_at_pull
from core.models import BANNER_CONFIGS, GAME_COLORS, get_max_rarity, get_pool_names


class ChartWidget(QWidget):
    """图表展示页面"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.db = Database()
        self._init_ui()

    def eventFilter(self, obj, event):
        """让 matplotlib 画布的滚轮事件传递给父级滚动区域"""
        from PySide6.QtCore import QEvent
        if event.type() == QEvent.Type.Wheel:
            # 找到最近的 QScrollArea 并转发事件
            widget = self
            while widget:
                scroll = widget.findChild(QScrollArea)
                if scroll:
                    # 让滚动区域处理事件
                    new_event = event.clone()
                    QApplication.sendEvent(scroll.viewport(), new_event)
                    return True
                widget = widget.parent()
            return False
        return super().eventFilter(obj, event)

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题和选择
        header = QHBoxLayout()
        title = QLabel("图表展示")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        header.addWidget(title)
        header.addStretch()

        header.addWidget(QLabel("卡池:"))
        self.pool_combo = QComboBox()
        self.pool_combo.currentIndexChanged.connect(lambda: self.refresh())
        header.addWidget(self.pool_combo)
        self._last_game = None
        layout.addLayout(header)

        # 图表滚动区
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll_widget = QWidget()
        self.chart_layout = QVBoxLayout(self.scroll_widget)
        self.chart_layout.setSpacing(16)

        scroll.setWidget(self.scroll_widget)
        layout.addWidget(scroll)

    def refresh(self):
        account = self.main_window.get_current_account()
        if not account:
            return

        game = self.main_window.get_current_game()

        # 游戏切换时更新卡池下拉框
        if game != self._last_game:
            self._last_game = game
            self.pool_combo.blockSignals(True)
            current = self.pool_combo.currentData()
            self.pool_combo.clear()
            self.pool_combo.addItem("全部卡池", None)
            for pt, name in get_pool_names(game):
                self.pool_combo.addItem(name, pt)
            idx = self.pool_combo.findData(current)
            self.pool_combo.setCurrentIndex(idx if idx >= 0 else 0)
            self.pool_combo.blockSignals(False)

        pool_type = self.pool_combo.currentData()
        records = self.db.get_records(account.id, pool_type)

        # 清除旧图表
        while self.chart_layout.count():
            child = self.chart_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if not records:
            no_data = QLabel("暂无数据，请先导入抽卡记录")
            no_data.setAlignment(Qt.AlignmentFlag.AlignCenter)
            no_data.setStyleSheet("color: #888; font-size: 14px; padding: 40px;")
            self.chart_layout.addWidget(no_data)
            return

        colors = GAME_COLORS.get(game, {})
        accent = colors.get("primary", "#1a73e8")

        stats = StatsAnalyzer(records)

        # 1. 出货抽数分布直方图
        self._add_pull_distribution_chart(records, accent)

        # 2. 保底概率曲线
        self._add_rate_curve_chart(game, pool_type, records, accent)

        # 3. 各星级统计
        self._add_rarity_chart(stats, accent)

        # 4. 卡池投入占比
        self._add_pool_distribution_chart(records, accent)

        # 5. 月度趋势
        self._add_monthly_trend_chart(records, accent)

        # 6. 50/50统计
        self._add_featured_chart(records, accent, game)

        self.chart_layout.addStretch()

    def _create_canvas(self, title_text, figsize=(10, 4)):
        """创建图表画布"""
        frame = QFrame()
        frame.setObjectName("card")
        frame.setStyleSheet(
            "QFrame { background-color: white; border-radius: 12px; border: 1px solid #e8e8e8; }"
        )
        layout = QVBoxLayout(frame)

        title = QLabel(title_text)
        title.setFont(QFont("Microsoft YaHei", 13, QFont.Weight.Bold))
        layout.addWidget(title)

        fig = Figure(figsize=figsize, dpi=100)
        fig.set_facecolor('white')
        canvas = FigureCanvas(fig)
        canvas.setMinimumHeight(300)

        # 让滚轮事件传递给父级滚动区域
        canvas.installEventFilter(self)

        layout.addWidget(canvas)

        self.chart_layout.addWidget(frame)
        return fig, canvas

    def _add_pull_distribution_chart(self, records, color):
        """出货抽数分布直方图"""
        stats = StatsAnalyzer(records)
        game = records[0].game if records else ""
        max_rarity = get_max_rarity(game) if game else 5
        distribution = stats.get_pull_distribution(max_rarity)

        if not distribution:
            return

        fig, canvas = self._create_canvas("出货抽数分布（每次5星在第几抽出）")
        ax = fig.add_subplot(111)

        bins = range(1, max(distribution) + 2)
        ax.hist(distribution, bins=bins, color=color, alpha=0.8, edgecolor='white')

        avg = sum(distribution) / len(distribution)
        ax.axvline(avg, color='red', linestyle='--', linewidth=1.5, label=f'平均: {avg:.1f}')
        ax.set_xlabel('抽数')
        ax.set_ylabel('次数')
        ax.legend()
        ax.grid(axis='y', alpha=0.3)

        fig.tight_layout()
        canvas.draw()

    def _add_rate_curve_chart(self, game, pool_type, records, color):
        """保底概率曲线"""
        from core.models import get_mechanic_type
        pool_name = records[0].pool_name if records else ""
        mechanic_type = get_mechanic_type(game, pool_type, pool_name)
        config = BANNER_CONFIGS.get((game, mechanic_type))
        if not config:
            config = BANNER_CONFIGS.get((game, pool_type))
        if not config:
            return

        pool_name = records[0].pool_name if records else ""
        pity = self.db.get_last_5star_pity(records[0].account_id, pool_type, game, pool_name=pool_name)

        fig, canvas = self._create_canvas("逐抽出5星概率曲线")
        ax = fig.add_subplot(111)

        pulls = list(range(pity, config.hard_pity + 1))
        rates = [get_rate_at_pull(config, p) * 100 for p in pulls]

        ax.plot([p - pity for p in pulls], rates, color=color, linewidth=2)
        ax.fill_between([p - pity for p in pulls], rates, alpha=0.2, color=color)

        if pity >= config.soft_pity_start:
            ax.axvline(0, color='orange', linestyle='--', alpha=0.7, label='当前位置(软保底中)')
        else:
            ax.axvline(0, color='green', linestyle='--', alpha=0.7, label='当前位置')

        ax.axvline(config.hard_pity - pity, color='red', linestyle='--', alpha=0.5, label='硬保底')
        ax.set_xlabel('距今抽数')
        ax.set_ylabel('5星概率 (%)')
        ax.legend()
        ax.grid(alpha=0.3)

        fig.tight_layout()
        canvas.draw()

    def _add_rarity_chart(self, stats, color):
        """各星级统计"""
        summary = stats.get_summary()
        if summary["total"] == 0:
            return

        fig, canvas = self._create_canvas("各星级数量统计", figsize=(6, 4))
        ax = fig.add_subplot(111)

        # 动态获取星级列表
        game = stats.game if hasattr(stats, 'game') else ""
        max_rarity = get_max_rarity(game) if game else 5

        labels = []
        values = []
        colors = ['#FF6B35', '#9B7ED8', '#90CAF9', '#A5D6A7']
        for r in range(max_rarity, 2, -1):
            labels.append(f'{r}星')
            values.append(summary.get(f"star_{r}", 0))

        bars = ax.bar(labels, values, color=colors[:len(values)], width=0.5, edgecolor='white')
        for bar, val in zip(bars, values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 1,
                    str(val), ha='center', fontweight='bold')

        ax.set_ylabel('数量')
        ax.grid(axis='y', alpha=0.3)

        fig.tight_layout()
        canvas.draw()

    def _add_pool_distribution_chart(self, records, color):
        """卡池投入占比"""
        from collections import Counter
        from core.models import get_pool_names

        pool_counts = Counter(r.pool_type for r in records)
        if not pool_counts:
            return

        fig, canvas = self._create_canvas("卡池投入占比", figsize=(6, 4))
        ax = fig.add_subplot(111)

        # 从游戏配置获取卡池显示名称
        game = records[0].game if records else ""
        pool_config = dict(get_pool_names(game))
        labels = [pool_config.get(k, k) for k in pool_counts.keys()]
        values = list(pool_counts.values())
        colors = ['#FF6B35', '#9B7ED8', '#90CAF9', '#A5D6A7', '#FFD54F', '#80CBC4', '#FFAB91']

        wedges, texts, autotexts = ax.pie(
            values, labels=labels, autopct='%1.1f%%',
            colors=colors[:len(values)], startangle=90
        )
        ax.axis('equal')

        fig.tight_layout()
        canvas.draw()

    def _add_monthly_trend_chart(self, records, color):
        """月度趋势"""
        stats = StatsAnalyzer(records)
        monthly = stats.get_monthly_trend()
        if not monthly:
            return

        fig, canvas = self._create_canvas("月度抽卡趋势")
        ax = fig.add_subplot(111)

        months = list(monthly.keys())[-12:]  # 最近12个月
        values = [monthly[m] for m in months]
        display_months = [m[5:] for m in months]  # 只显示月份

        ax.bar(display_months, values, color=color, alpha=0.8, edgecolor='white')
        ax.plot(display_months, values, color='red', marker='o', markersize=4, linewidth=1)

        ax.set_xlabel('月份')
        ax.set_ylabel('抽数')
        ax.grid(axis='y', alpha=0.3)

        fig.tight_layout()
        canvas.draw()

    def _add_featured_chart(self, records, color, game=""):
        """50/50统计饼图"""
        # 明日方舟没有50/50机制，不显示此图表
        if game == "arknights":
            return

        max_rarity = get_max_rarity(game) if game else 5
        five_stars = [r for r in records if r.rarity == max_rarity]
        if not five_stars:
            return

        wins = sum(1 for r in five_stars if r.is_featured)
        losses = len(five_stars) - wins

        fig, canvas = self._create_canvas("50/50 统计", figsize=(6, 4))
        ax = fig.add_subplot(111)

        if wins + losses > 0:
            labels = [f'UP ({wins}次)', f'歪 ({losses}次)']
            values = [wins, losses]
            colors = ['#4CAF50', '#FF5252']

            wedges, texts, autotexts = ax.pie(
                values, labels=labels, autopct='%1.1f%%',
                colors=colors, startangle=90
            )
        ax.axis('equal')

        fig.tight_layout()
        canvas.draw()
