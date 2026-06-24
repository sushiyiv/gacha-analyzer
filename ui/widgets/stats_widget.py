"""统计分析页面"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QTableWidget, QTableWidgetItem, QHeaderView, QScrollArea,
    QComboBox, QGroupBox, QStackedWidget, QSlider, QProgressBar
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

from core.database import Database
from core.analyzer import PityAnalyzer, StatsAnalyzer
from core.models import BANNER_CONFIGS, GAME_COLORS, get_max_rarity, get_pool_names, get_endfield_pity_group, ENDFIELD_PITY_GROUP, ENDFIELD_PITY_RESETS_ON_NAME_CHANGE


class StatsWidget(QWidget):
    """统计分析页面"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.db = Database()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_widget = QWidget()
        main_layout = QVBoxLayout(scroll_widget)

        # 标题和选择
        header = QHBoxLayout()
        title = QLabel("统计分析")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        header.addWidget(title)
        header.addStretch()

        header.addWidget(QLabel("卡池:"))
        self.pool_combo = QComboBox()
        self.pool_combo.currentIndexChanged.connect(lambda: self.refresh())
        header.addWidget(self.pool_combo)
        main_layout.addLayout(header)

        # ===== 保底分析 =====
        pity_group = QGroupBox("保底分析")
        pity_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        pity_layout = QVBoxLayout(pity_group)

        self.pity_summary = QLabel("暂无数据")
        self.pity_summary.setStyleSheet("font-size: 13px;")
        pity_layout.addWidget(self.pity_summary)

        # 保底详情表格
        self.pity_table = QTableWidget()
        self.pity_table.setColumnCount(4)
        self.pity_table.setHorizontalHeaderLabels(["指标", "数值", "说明", "备注"])
        self.pity_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.pity_table.verticalHeader().setVisible(False)
        self.pity_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.pity_table.setMinimumHeight(200)
        pity_layout.addWidget(self.pity_table)
        main_layout.addWidget(pity_group)

        # ===== 50/50 统计 =====
        featured_group = QGroupBox("50/50 统计")
        featured_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        featured_layout = QVBoxLayout(featured_group)

        self.featured_summary = QLabel("暂无数据")
        self.featured_summary.setStyleSheet("font-size: 13px;")
        featured_layout.addWidget(self.featured_summary)

        self.featured_table = QTableWidget()
        self.featured_table.setColumnCount(3)
        self.featured_table.setHorizontalHeaderLabels(["指标", "数值", "说明"])
        self.featured_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.featured_table.verticalHeader().setVisible(False)
        self.featured_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.featured_table.setMinimumHeight(180)
        self.featured_table.verticalHeader().setDefaultSectionSize(40)
        featured_layout.addWidget(self.featured_table)
        main_layout.addWidget(featured_group)

        # ===== 出货记录 =====
        pull_group = QGroupBox("出货记录")
        pull_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        pull_layout = QVBoxLayout(pull_group)

        self.pull_table = QTableWidget()
        self.pull_table.setColumnCount(6)
        self.pull_table.setHorizontalHeaderLabels(
            ["序号", "名称", "星级", "是否UP", "保底计数", "时间"]
        )
        # 设置列宽模式：使用Interactive模式，让用户可以手动调整
        header = self.pull_table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        # 设置初始列宽
        self.pull_table.setColumnWidth(0, 60)   # 序号
        self.pull_table.setColumnWidth(1, 200)  # 名称
        self.pull_table.setColumnWidth(2, 110)  # 星级
        self.pull_table.setColumnWidth(3, 80)   # 是否UP
        self.pull_table.setColumnWidth(4, 100)  # 保底计数
        self.pull_table.setColumnWidth(5, 200)  # 时间
        # 设置表格属性
        self.pull_table.verticalHeader().setVisible(False)
        self.pull_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.pull_table.setMinimumHeight(300)
        self.pull_table.horizontalHeader().setStretchLastSection(True)  # 最后一列自动填充
        pull_layout.addWidget(self.pull_table)
        main_layout.addWidget(pull_group)

        # ===== 概率预测 =====
        prob_group = QGroupBox("概率预测")
        prob_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        prob_layout = QVBoxLayout(prob_group)

        # 开关式切换按钮 - 用固定容器实现滑动效果
        toggle_wrapper = QWidget()
        toggle_wrapper.setFixedSize(170, 32)
        toggle_wrapper.setCursor(Qt.CursorShape.PointingHandCursor)

        # 背景轨道
        toggle_bg = QFrame(toggle_wrapper)
        toggle_bg.setGeometry(0, 4, 170, 24)
        toggle_bg.setStyleSheet("background: #e0e0e0; border-radius: 12px;")

        # 滑动指示器
        self.toggle_indicator = QFrame(toggle_wrapper)
        self.toggle_indicator.setGeometry(0, 4, 85, 24)
        self.toggle_indicator.setStyleSheet("background: #1a73e8; border-radius: 12px;")

        # 左侧文字
        self.toggle_left_label = QLabel("表格", toggle_wrapper)
        self.toggle_left_label.setGeometry(0, 4, 85, 24)
        self.toggle_left_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toggle_left_label.setFont(QFont("Microsoft YaHei", 11, QFont.Weight.Bold))
        self.toggle_left_label.setStyleSheet("color: white; background: transparent;")

        # 右侧文字
        self.toggle_right_label = QLabel("进度条", toggle_wrapper)
        self.toggle_right_label.setGeometry(85, 4, 85, 24)
        self.toggle_right_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.toggle_right_label.setFont(QFont("Microsoft YaHei", 11))
        self.toggle_right_label.setStyleSheet("color: #666; background: transparent;")

        # 确保文字在指示器上方
        self.toggle_left_label.raise_()
        self.toggle_right_label.raise_()

        # 点击切换
        toggle_wrapper.mousePressEvent = lambda e: self._switch_prob_mode(
            1 - self.prob_stack.currentIndex()
        )

        toggle_bar = QHBoxLayout()
        toggle_bar.addStretch()
        toggle_bar.addWidget(toggle_wrapper)
        toggle_bar.addStretch()
        prob_layout.addLayout(toggle_bar)

        # 模式切换容器
        self.prob_stack = QStackedWidget()

        # --- 表格模式 ---
        self.prob_table = QTableWidget()
        self.prob_table.setColumnCount(3)
        self.prob_table.setHorizontalHeaderLabels(["抽数", "出货概率", "概率条"])
        self.prob_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.prob_table.verticalHeader().setVisible(False)
        self.prob_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.prob_table.setMinimumHeight(300)
        self.prob_stack.addWidget(self.prob_table)

        # --- 进度条模式 ---
        slider_page = QWidget()
        slider_layout = QVBoxLayout(slider_page)
        slider_layout.setContentsMargins(20, 20, 20, 20)
        slider_layout.setSpacing(15)

        # 当前状态提示
        self.slider_context_label = QLabel("当前已垫: 0抽")
        self.slider_context_label.setFont(QFont("Microsoft YaHei", 12))
        slider_layout.addWidget(self.slider_context_label)

        # 拖动滑块
        self.prob_slider = QSlider(Qt.Orientation.Horizontal)
        self.prob_slider.setMinimum(1)
        self.prob_slider.setMaximum(90)
        self.prob_slider.setValue(10)
        self.prob_slider.setTickPosition(QSlider.TickPosition.TicksBelow)
        self.prob_slider.setTickInterval(10)
        self.prob_slider.setFixedHeight(40)
        self.prob_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                border: none; height: 8px; border-radius: 4px;
                background: #ddd;
            }
            QSlider::handle:horizontal {
                background: #1a73e8; border: 3px solid #fff;
                width: 28px; height: 28px; margin: -13px 0;
                border-radius: 17px;
            }
            QSlider::handle:horizontal:hover {
                background: #1557b0;
            }
            QSlider::sub-page:horizontal {
                border-radius: 4px; background: #1a73e8;
            }
            QSlider::tick-mark:horizontal {
                width: 2px; height: 8px; background: #bbb; margin: 0;
            }
        """)
        self.prob_slider.valueChanged.connect(self._on_slider_changed)
        slider_layout.addWidget(self.prob_slider)

        # 滑块数值显示
        slider_val_row = QHBoxLayout()
        slider_val_row.addWidget(QLabel("1"))
        self.slider_pull_label = QLabel("10抽")
        self.slider_pull_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.slider_pull_label.setFont(QFont("Microsoft YaHei", 14, QFont.Weight.Bold))
        slider_val_row.addWidget(self.slider_pull_label)
        self.slider_max_label = QLabel("90")
        self.slider_max_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        slider_val_row.addWidget(self.slider_max_label)
        slider_layout.addLayout(slider_val_row)

        # 概率大字
        self.slider_prob_label = QLabel("出货概率: 6.0%")
        self.slider_prob_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.slider_prob_label.setFont(QFont("Microsoft YaHei", 20, QFont.Weight.Bold))
        self.slider_prob_label.setStyleSheet("color: #4CAF50;")
        slider_layout.addWidget(self.slider_prob_label)

        # 概率进度条
        self.slider_prob_bar = QProgressBar()
        self.slider_prob_bar.setFixedHeight(30)
        self.slider_prob_bar.setMaximum(10000)
        self.slider_prob_bar.setTextVisible(True)
        self.slider_prob_bar.setFormat("%p%")
        self.slider_prob_bar.setStyleSheet("""
            QProgressBar {
                border: none; border-radius: 15px; background-color: #e0e0e0;
                text-align: center; color: #333; font-size: 12px; font-weight: bold;
            }
            QProgressBar::chunk {
                border-radius: 15px; background-color: #4CAF50;
            }
        """)
        slider_layout.addWidget(self.slider_prob_bar)

        # 说明文字
        self.slider_desc_label = QLabel("拖动滑块查看不同抽数下的出货概率")
        self.slider_desc_label.setStyleSheet("color: #888; font-size: 11px;")
        self.slider_desc_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        slider_layout.addWidget(self.slider_desc_label)

        slider_layout.addStretch()
        self.prob_stack.addWidget(slider_page)

        prob_layout.addWidget(self.prob_stack)
        self._update_toggle_style()
        main_layout.addWidget(prob_group)

        main_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

    def _update_pool_combo(self, game):
        """根据游戏配置更新卡池下拉框"""
        self.pool_combo.blockSignals(True)
        current = self.pool_combo.currentData()
        self.pool_combo.clear()
        self.pool_combo.addItem("全部卡池", None)

        pools = get_pool_names(game)
        for pool_type, name in pools:
            self.pool_combo.addItem(name, pool_type)

        idx = self.pool_combo.findData(current)
        if idx >= 0:
            self.pool_combo.setCurrentIndex(idx)
        self.pool_combo.blockSignals(False)

    def refresh(self):
        account = self.main_window.get_current_account()
        if not account:
            return

        game = self.main_window.get_current_game()

        self._update_pool_combo(game)
        pool_type = self.pool_combo.currentData()

        if pool_type is None:
            records = self.db.get_records(account.id)
        elif game == "endfield" and pool_type:
            pity_group = get_endfield_pity_group(pool_type)
            if pity_group in ENDFIELD_PITY_RESETS_ON_NAME_CHANGE:
                # 武器池：不加载共享记录
                records = self.db.get_records(account.id, pool_type)
            else:
                # 其他池：加载同组所有记录（跨卡池轮换继承保底）
                shared_types = [pt for pt, g in ENDFIELD_PITY_GROUP.items() if g == pity_group]
                records = []
                for pt in shared_types:
                    records.extend(self.db.get_records(account.id, pt))
        else:
            records = self.db.get_records(account.id, pool_type)

        if not records:
            self.pity_summary.setText("暂无数据，请先导入抽卡记录")
            return

        # 保底分析（全部卡池时跳过）
        if pool_type:
            try:
                pool_name = records[0].pool_name if records else ""
                analyzer = PityAnalyzer(game, pool_type, pool_name)
                pity = analyzer.analyze(records)
                self._update_pity(pity, game)
            except Exception as e:
                self.pity_summary.setText(f"分析失败: {str(e)}")
        else:
            self.pity_summary.setText("全部卡池综合统计（保底分析请切换到具体卡池）")
            self.pity_table.setRowCount(0)

        # 统计分析
        stats = StatsAnalyzer(records, game)
        self._update_featured(stats, game)
        self._update_pulls(records, game)
        self._update_prob(game, pool_type, records)

        # 更新卡池抽数显示
        self._update_pool_pull_counts(account, game)

    def _update_pity(self, pity, game):
        """更新保底信息"""
        colors = GAME_COLORS.get(game, {})
        accent = colors.get("primary", "#1a73e8")

        guaranteed_text = "是（下次必出UP）" if pity["is_guaranteed"] else "否"
        self.pity_summary.setText(
            f"当前保底: {pity['current_pity']}/{pity['config'].hard_pity}  |  "
            f"当前概率: {pity['current_rate']*100:.2f}%  |  "
            f"大保底: {guaranteed_text}"
        )

        rows = [
            ("当前抽数", f"{pity['current_pity']}", "距离上次最高星", ""),
            ("距离保底", f"{pity['pulls_to_hard']}", "必出最高星", ""),
            ("当前概率", f"{pity['current_rate']*100:.2f}%", f"基础{pity['config'].base_rate_5star*100}%", ""),
            ("期望抽数(最高星)", f"{pity['expected_to_5star']}", "数学期望", ""),
            ("期望抽数(UP)", f"{pity['expected_to_featured']}", "含保底机制", ""),
            ("平均出货", f"{pity['avg_pity']}", f"最欧:{pity['min_pity']} 最非:{pity['max_pity']}", ""),
        ]

        # UP硬保底（终末地特许120抽、武器80抽，明日方舟单UP 150抽等）
        if pity.get("up_hard_pity", 0) > 0:
            rows.append((
                "UP大保底",
                f"{pity['up_hard_pity_remaining']}/{pity['up_hard_pity']}",
                "必出UP角色",
                "" if pity['config'].up_hard_pity_inherits else "不继承"
            ))

        # 十连保底（终末地每10抽保底5星）
        if pity.get("multi_pity_size", 0) > 0:
            rows.append((
                "十连保底",
                f"{pity['multi_pity_progress']}/{pity['multi_pity_size']}",
                f"每{pity['multi_pity_size']}抽保底{pity['multi_pity_rarity']}星",
                ""
            ))

        # 自选/兑换（终末地300抽自选、明日方舟限定300抽兑换）
        if pity.get("exchange_threshold", 0) > 0:
            rows.append((
                "自选/兑换",
                f"{pity['exchange_progress']}/{pity['exchange_threshold']}",
                "累计抽数",
                ""
            ))

        self.pity_table.setRowCount(len(rows))
        for i, (col1, col2, col3, col4) in enumerate(rows):
            self.pity_table.setItem(i, 0, QTableWidgetItem(col1))
            self.pity_table.setItem(i, 1, QTableWidgetItem(col2))
            self.pity_table.setItem(i, 2, QTableWidgetItem(col3))
            self.pity_table.setItem(i, 3, QTableWidgetItem(col4))

    def _update_featured(self, stats, game=""):
        # 明日方舟没有50/50机制，隐藏此区域
        if game == "arknights":
            self.featured_summary.setText("明日方舟无50/50机制")
            self.featured_table.setRowCount(0)
            return

        feat = stats.get_featured_stats()
        if feat["total"] == 0:
            self.featured_summary.setText("暂无5星记录")
            return

        self.featured_summary.setText(
            f"5星总数: {feat['total']}  |  "
            f"UP: {feat['wins']}  |  歪: {feat['losses']}  |  "
            f"UP胜率: {feat['win_rate']}%"
        )

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
        """更新出货记录表（最新在前）"""
        max_rarity = get_max_rarity(game) if game else 5
        five_stars = [r for r in sorted(records, key=lambda r: (r.time, r.id)) if r.rarity == max_rarity]
        five_stars.reverse()

        # 明日方舟隐藏"是否UP"列
        is_arknights = game == "arknights"
        if is_arknights:
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

        self.pull_table.setRowCount(len(five_stars))

        for i, r in enumerate(five_stars):
            self.pull_table.setItem(i, 0, QTableWidgetItem(str(i + 1)))
            self.pull_table.setItem(i, 1, QTableWidgetItem(r.item_name))

            star_item = QTableWidgetItem("★" * r.rarity)
            star_item.setForeground(QColor("#FF6B35"))
            self.pull_table.setItem(i, 2, star_item)

            if is_arknights:
                self.pull_table.setItem(i, 3, QTableWidgetItem(str(r.pity_count)))
                self.pull_table.setItem(i, 4, QTableWidgetItem(r.pool_name or ""))
            else:
                self.pull_table.setItem(i, 3, QTableWidgetItem("是" if r.is_featured else "否"))
                self.pull_table.setItem(i, 4, QTableWidgetItem(str(r.pity_count)))
                self.pull_table.setItem(i, 5, QTableWidgetItem(r.time[:16] if r.time else ""))

    def _update_pool_pull_counts(self, account, game):
        """更新卡池抽数显示（仅更新下拉框选项，不显示抽数）"""
        # 此方法保留供未来使用，当前不做额外更新
        pass

    def _update_toggle_style(self):
        """更新开关切换样式 - 移动指示器"""
        is_table = self.prob_stack.currentIndex() == 0
        # 移动指示器
        target_x = 0 if is_table else 85
        self.toggle_indicator.setGeometry(target_x, 4, 85, 24)
        # 文字颜色
        self.toggle_left_label.setStyleSheet(
            f"color: {'white' if is_table else '#666'}; background: transparent;"
        )
        self.toggle_right_label.setStyleSheet(
            f"color: {'#666' if is_table else 'white'}; background: transparent;"
        )

    def _switch_prob_mode(self, index):
        """切换概率预测模式"""
        self.prob_stack.setCurrentIndex(index)
        self._update_toggle_style()

    def _on_slider_changed(self, value):
        """滑块值变化"""
        from core.analyzer import get_pull_probability

        if not hasattr(self, '_prob_config') or not self._prob_config:
            return

        config = self._prob_config
        pity = self._prob_pity

        # 更新显示
        self.slider_pull_label.setText(f"{value}抽")
        self.slider_max_label.setText(str(config.hard_pity))

        prob = get_pull_probability(config, pity, value)
        self.slider_prob_label.setText(f"出货概率: {prob*100:.1f}%")

        # 进度条 (0~10000 对应 0%~100%)
        self.slider_prob_bar.setValue(int(prob * 10000))

        # 颜色: 绿(低概率) → 黄(中) → 红(高概率)
        color = self._get_prob_color(prob)
        self.slider_prob_label.setStyleSheet(f"color: {color};")
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
        """根据概率返回颜色: 绿→黄→红"""
        if prob <= 0.5:
            # 绿色区间 0~50%: #4CAF50
            return "#4CAF50"
        elif prob <= 0.8:
            # 黄色区间 50%~80%: #FFC107
            return "#FFC107"
        else:
            # 红色区间 80%~100%: #F44336
            return "#F44336"

    def _update_prob(self, game, pool_type, records):
        """更新概率预测"""
        from core.analyzer import get_pull_probability

        config = BANNER_CONFIGS.get((game, pool_type))
        if not config:
            # 全部卡池时显示提示
            self.prob_table.setRowCount(1)
            self.prob_table.setItem(0, 0, QTableWidgetItem(""))
            self.prob_table.setItem(0, 1, QTableWidgetItem(""))
            self.prob_table.setItem(0, 2, QTableWidgetItem("请切换到具体卡池查看概率预测"))
            self._prob_config = None
            self._prob_pity = 0
            self.slider_context_label.setText("请切换到具体卡池")
            self.slider_prob_label.setText("出货概率: -")
            self.slider_prob_bar.setValue(0)
            return

        pool_name = records[0].pool_name if records else ""
        pity = self.db.get_last_5star_pity(records[0].account_id, pool_type, game, pool_name=pool_name)

        # 保存供滑块使用
        self._prob_config = config
        self._prob_pity = pity

        # 更新滑块范围 - 上限为绝对保底数
        self.prob_slider.setMaximum(config.hard_pity)
        self.slider_max_label.setText(str(config.hard_pity))
        self.slider_context_label.setText(f"当前已垫: {pity}抽 / 保底{config.hard_pity}抽")
        self.slider_pull_label.setText(f"{self.prob_slider.value()}抽")

        # 表格模式
        rows = []
        for t in [1, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90]:
            if t > config.hard_pity:
                break
            prob = get_pull_probability(config, pity, t)
            bar_len = int(prob * 30)
            bar = "█" * bar_len + "░" * (30 - bar_len)
            rows.append((f"{t}抽", f"{prob*100:.1f}%", bar))

        self.prob_table.setRowCount(len(rows))
        for i, (c1, c2, c3) in enumerate(rows):
            self.prob_table.setItem(i, 0, QTableWidgetItem(c1))
            self.prob_table.setItem(i, 1, QTableWidgetItem(c2))
            self.prob_table.setItem(i, 2, QTableWidgetItem(c3))

        # 刷新滑块显示
        self._on_slider_changed(self.prob_slider.value())
