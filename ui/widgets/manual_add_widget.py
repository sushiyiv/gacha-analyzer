"""手动添加记录页面"""

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QLineEdit, QComboBox, QDateTimeEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QGroupBox, QCheckBox, QSpinBox, QScrollArea, QGridLayout
)
from PySide6.QtCore import Qt, QDateTime
from PySide6.QtGui import QFont

from core.database import Database
from core.models import GachaRecord, GAME_NAMES, POOL_CONFIGS, MAX_RARITY
from ui.widgets.styled_widgets import StyledCheckBox


class ManualAddWidget(QWidget):
    """手动添加记录"""

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

        # 标题
        title = QLabel("手动添加记录")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        main_layout.addWidget(title)

        # ===== 单条添加 =====
        single_group = QGroupBox("单条添加")
        single_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        form = QGridLayout(single_group)
        form.setSpacing(10)

        # 卡池
        form.addWidget(QLabel("卡池:"), 0, 0)
        self.pool_combo = QComboBox()
        form.addWidget(self.pool_combo, 0, 1)

        # 物品名称
        form.addWidget(QLabel("物品名称:"), 0, 2)
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("输入角色/武器名称")
        form.addWidget(self.name_input, 0, 3)

        # 物品类型
        form.addWidget(QLabel("物品类型:"), 1, 0)
        self.type_combo = QComboBox()
        form.addWidget(self.type_combo, 1, 1)

        # 星级
        form.addWidget(QLabel("星级:"), 1, 2)
        self.rarity_combo = QComboBox()
        form.addWidget(self.rarity_combo, 1, 3)

        # 是否UP
        form.addWidget(QLabel("是否UP:"), 2, 0)
        self.featured_check = StyledCheckBox("UP物品")
        form.addWidget(self.featured_check, 2, 1)

        # 时间
        form.addWidget(QLabel("抽卡时间:"), 2, 2)
        self.time_edit = QDateTimeEdit(QDateTime.currentDateTime())
        self.time_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        form.addWidget(self.time_edit, 2, 3)

        # 添加按钮
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("添加记录")
        add_btn.setFixedSize(120, 36)
        add_btn.clicked.connect(self._add_single)
        btn_layout.addWidget(add_btn)
        btn_layout.addStretch()
        form.addLayout(btn_layout, 3, 0, 1, 4)

        main_layout.addWidget(single_group)

        # ===== 批量添加 =====
        batch_group = QGroupBox("批量添加")
        batch_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        batch_layout = QVBoxLayout(batch_group)

        batch_desc = QLabel("在表格中连续输入记录，完成后点击「批量保存」")
        batch_desc.setStyleSheet("color: #666;")
        batch_layout.addWidget(batch_desc)

        self.batch_table = QTableWidget(20, 5)
        self.batch_table.setHorizontalHeaderLabels(["名称", "类型", "星级", "是否UP", "时间"])
        self.batch_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # 设置默认值
        for row in range(20):
            type_combo = QComboBox()
            type_combo.addItems(["角色", "武器", "光锥", "音擎"])
            self.batch_table.setCellWidget(row, 1, type_combo)

            rarity_combo = QComboBox()
            rarity_combo.addItems(["5", "4", "3"])
            self.batch_table.setCellWidget(row, 2, rarity_combo)

            featured_combo = QComboBox()
            featured_combo.addItems(["否", "是"])
            self.batch_table.setCellWidget(row, 3, featured_combo)

        batch_layout.addWidget(self.batch_table)

        batch_btn_layout = QHBoxLayout()
        save_batch_btn = QPushButton("批量保存")
        save_batch_btn.setFixedSize(120, 36)
        save_batch_btn.clicked.connect(self._add_batch)
        batch_btn_layout.addWidget(save_batch_btn)

        clear_btn = QPushButton("清空表格")
        clear_btn.setFixedSize(100, 36)
        clear_btn.setStyleSheet("background-color: #666;")
        clear_btn.clicked.connect(self._clear_batch)
        batch_btn_layout.addWidget(clear_btn)
        batch_btn_layout.addStretch()
        batch_layout.addLayout(batch_btn_layout)

        main_layout.addWidget(batch_group)
        main_layout.addStretch()

        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

        # 保存批量表格的下拉框引用
        self._batch_type_combos = []
        self._batch_rarity_combos = []
        for row in range(20):
            self._batch_type_combos.append(self.batch_table.cellWidget(row, 1))
            self._batch_rarity_combos.append(self.batch_table.cellWidget(row, 2))

    def _add_single(self):
        """添加单条记录"""
        account = self.main_window.get_current_account()
        if not account:
            QMessageBox.warning(self, "提示", "请先选择或创建账号")
            return

        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入物品名称")
            return

        game = self.main_window.get_current_game()
        pool = self.pool_combo.currentData()
        item_type = self.type_combo.currentText()
        rarity = self.rarity_combo.currentData() or 5
        featured = self.featured_check.isChecked()
        time_str = self.time_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")

        record = GachaRecord(
            account_id=account.id,
            game=game,
            pool_type=pool,
            item_name=name,
            item_type=item_type,
            rarity=rarity,
            is_featured=featured,
            time=time_str,
        )

        count = self.db.add_records([record])
        if count > 0:
            QMessageBox.information(self, "成功", f"已添加记录: {name}")
            self.name_input.clear()
            self.main_window.refresh_all()
        else:
            QMessageBox.warning(self, "提示", "记录可能已存在")

    def _add_batch(self):
        """批量添加"""
        account = self.main_window.get_current_account()
        if not account:
            QMessageBox.warning(self, "提示", "请先选择或创建账号")
            return

        game = self.main_window.get_current_game()
        records = []

        for row in range(self.batch_table.rowCount()):
            name_item = self.batch_table.item(row, 0)
            if not name_item or not name_item.text().strip():
                continue

            name = name_item.text().strip()
            item_type = self.batch_table.cellWidget(row, 1).currentText()
            rarity = int(self.batch_table.cellWidget(row, 2).currentText())
            featured = self.batch_table.cellWidget(row, 3).currentText() == "是"
            time_item = self.batch_table.item(row, 4)
            time_str = time_item.text().strip() if time_item else ""

            if not time_str:
                time_str = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")

            # 使用第一个卡池类型作为默认值
            pools = POOL_CONFIGS.get(game, [])
            default_pool = pools[0][0] if pools else "character"

            records.append(GachaRecord(
                account_id=account.id,
                game=game,
                pool_type=default_pool,
                item_name=name,
                item_type=item_type,
                rarity=rarity,
                is_featured=featured,
                time=time_str,
            ))

        if not records:
            QMessageBox.warning(self, "提示", "没有有效的记录可保存")
            return

        count = self.db.add_records(records)
        QMessageBox.information(self, "成功", f"已批量添加 {count} 条记录")
        self._clear_batch()
        self.main_window.refresh_all()

    def _clear_batch(self):
        for row in range(self.batch_table.rowCount()):
            self.batch_table.setItem(row, 0, None)
            self.batch_table.setItem(row, 4, None)

    def refresh(self):
        """根据当前游戏更新下拉框选项"""
        game = self.main_window.get_current_game()
        if not game:
            return

        # 更新卡池下拉框
        self.pool_combo.blockSignals(True)
        self.pool_combo.clear()
        pools = POOL_CONFIGS.get(game, [])
        for pool_type, display_name in pools:
            self.pool_combo.addItem(display_name, pool_type)
        self.pool_combo.blockSignals(False)

        # 更新物品类型下拉框
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        item_types = self._get_item_types(game)
        self.type_combo.addItems(item_types)
        self.type_combo.blockSignals(False)

        # 更新星级下拉框
        self.rarity_combo.blockSignals(True)
        self.rarity_combo.clear()
        max_rarity = MAX_RARITY.get(game, 5)
        for r in range(max_rarity, 2, -1):
            stars = "★" * r
            self.rarity_combo.addItem(f"{stars} ({r}星)", r)
        self.rarity_combo.blockSignals(False)

        # 更新批量表格的下拉框
        item_types = self._get_item_types(game)
        for row in range(20):
            type_combo = self.batch_table.cellWidget(row, 1)
            if type_combo:
                type_combo.blockSignals(True)
                type_combo.clear()
                type_combo.addItems(item_types)
                type_combo.blockSignals(False)

            rarity_combo = self.batch_table.cellWidget(row, 2)
            if rarity_combo:
                rarity_combo.blockSignals(True)
                rarity_combo.clear()
                for r in range(max_rarity, 2, -1):
                    rarity_combo.addItem(str(r), r)
                rarity_combo.blockSignals(False)

    def _get_item_types(self, game):
        """根据游戏返回物品类型列表"""
        type_map = {
            "genshin": ["角色", "武器"],
            "starrail": ["角色", "光锥"],
            "zzz": ["角色", "音擎"],
            "wutheringwaves": ["角色", "武器"],
            "endfield": ["角色", "武器"],
            "arknights": ["角色"],
        }
        return type_map.get(game, ["角色", "武器"])
