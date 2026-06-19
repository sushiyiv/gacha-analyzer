"""手动添加记录页面

本模块实现抽卡分析器的手动数据录入功能界面，支持两种录入方式：
1. 单条添加 - 逐条输入抽卡记录，包含卡池、名称、类型、星级、UP状态和时间
2. 批量添加 - 在表格中连续输入多条记录，一次性保存

Qt控件层级结构：
    ManualAddWidget (QWidget)
    └── QVBoxLayout
        └── QScrollArea (可滚动区域)
            └── QWidget
                └── QVBoxLayout
                    ├── QLabel "手动添加记录" (标题)
                    ├── QGroupBox "单条添加"
                    │   ├── QGridLayout (表单)
                    │   │   ├── QLabel + QComboBox (卡池选择)
                    │   │   ├── QLabel + QLineEdit (物品名称)
                    │   │   ├── QLabel + QComboBox (物品类型)
                    │   │   ├── QLabel + QComboBox (星级)
                    │   │   ├── QLabel + StyledCheckBox (是否UP)
                    │   │   ├── QLabel + QDateTimeEdit (抽卡时间)
                    │   │   └── QPushButton "添加记录"
                    │   └── ...
                    ├── QGroupBox "批量添加"
                    │   ├── QLabel (说明文字)
                    │   ├── QTableWidget (批量输入表格)
                    │   └── QHBoxLayout (批量保存 + 清空表格)
                    └── addStretch()

信号/槽连接：
    - add_btn.clicked → _add_single：单条添加按钮
    - save_batch_btn.clicked → _add_batch：批量保存按钮
    - clear_btn.clicked → _clear_batch：清空表格按钮

数据流：
    用户输入 → 构造GachaRecord对象 → db.add_records() → refresh_all()
"""

# ========== PySide6/Qt导入 ==========

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QLineEdit, QComboBox, QDateTimeEdit,
    QTableWidget, QTableWidgetItem, QHeaderView, QMessageBox,
    QGroupBox, QCheckBox, QSpinBox, QScrollArea, QGridLayout
)
# QWidget: 控件基类
# QVBoxLayout: 垂直布局
# QHBoxLayout: 水平布局
# QLabel: 文本标签
# QFrame: 带边框容器
# QPushButton: 按钮
# QLineEdit: 单行文本输入框
# QComboBox: 下拉选择框
# QDateTimeEdit: 日期时间选择器
# QTableWidget: 表格控件（用于批量输入）
# QTableWidgetItem: 表格单元格项
# QHeaderView: 表头视图
# QMessageBox: 消息提示框
# QGroupBox: 分组框
# QCheckBox: 复选框（本文件中未直接使用，由StyledCheckBox替代）
# QSpinBox: 数字微调框（本文件中未直接使用）
# QScrollArea: 可滚动区域
# QGridLayout: 网格布局（用于单条添加的表单）

from PySide6.QtCore import Qt, QDateTime
# Qt: 核心常量（对齐方式、数据角色等）
# QDateTime: 日期时间类，用于初始化时间选择器的默认值

from PySide6.QtGui import QFont
# QFont: 字体类

# ========== 业务模块导入 ==========

from core.database import Database
# Database: 数据库访问层

from core.models import GachaRecord, GAME_NAMES, POOL_CONFIGS, MAX_RARITY
# GachaRecord: 抽卡记录数据模型
#     字段：account_id, game, pool_type, item_name, item_type, rarity, is_featured, time
# GAME_NAMES: 游戏ID到中文名称的映射
# POOL_CONFIGS: 卡池配置，格式为 {game_id: [(pool_type, display_name), ...]}
# MAX_RARITY: 最大星级映射，格式为 {game_id: max_rarity}

from ui.widgets.styled_widgets import StyledCheckBox
# StyledCheckBox: 带自定义样式的复选框控件（可能有勾选框的特殊视觉效果）


class ManualAddWidget(QWidget):
    """手动添加记录页面主控件

    提供两种抽卡记录录入方式：
    1. 单条添加：适合补录少量记录，需要填写所有字段
    2. 批量添加：适合补录大量记录，表格形式连续输入

    注意：
        - 本页面需要先选择账号才能添加记录
        - 卡池类型根据当前游戏动态更新（调用 refresh()）
        - 记录去重依赖数据库的唯一约束
    """

    def __init__(self, main_window):
        """构造函数

        参数：
            main_window: 主窗口实例，提供 get_current_game()、get_current_account()、
                        refresh_all() 等方法
        """
        super().__init__()
        # 保存主窗口引用
        self.main_window = main_window
        # 初始化数据库访问对象
        self.db = Database()
        # 调用UI初始化方法
        self._init_ui()

    def _init_ui(self):
        """初始化界面布局

        构建整个手动添加页面的界面结构：
        1. 可滚动区域包裹所有内容（防止小窗口时内容被截断）
        2. 标题
        3. 单条添加区域（QGroupBox + QGridLayout表单）
        4. 批量添加区域（QGroupBox + QTableWidget + 按钮）
        """
        # 创建主垂直布局
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建可滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        # 滚动区域的内部widget
        scroll_widget = QWidget()
        main_layout = QVBoxLayout(scroll_widget)

        # ===== 标题 =====
        title = QLabel("手动添加记录")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        main_layout.addWidget(title)

        # ===== 单条添加区域 =====
        # QGroupBox 创建带标题的分组框，视觉上将相关控件归组
        single_group = QGroupBox("单条添加")
        single_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        # 使用QGridLayout创建表单布局（4列网格）
        # 行0: [卡池标签] [卡池下拉框] [物品名称标签] [名称输入框]
        # 行1: [物品类型标签] [类型下拉框] [星级标签] [星级下拉框]
        # 行2: [是否UP标签] [UP复选框]     [抽卡时间标签] [时间选择器]
        # 行3: [添加按钮（跨4列）]
        form = QGridLayout(single_group)
        # 设置网格内控件间距为10像素
        form.setSpacing(10)

        # ----- 行0：卡池选择 -----
        form.addWidget(QLabel("卡池:"), 0, 0)  # 第0行第0列：标签
        self.pool_combo = QComboBox()  # 卡池下拉选择框
        form.addWidget(self.pool_combo, 0, 1)  # 第0行第1列：下拉框

        # ----- 行0右侧：物品名称输入 -----
        form.addWidget(QLabel("物品名称:"), 0, 2)  # 第0行第2列：标签
        self.name_input = QLineEdit()  # 单行文本输入框
        self.name_input.setPlaceholderText("输入角色/武器名称")  # 占位提示
        form.addWidget(self.name_input, 0, 3)  # 第0行第3列：输入框

        # ----- 行1：物品类型 -----
        form.addWidget(QLabel("物品类型:"), 1, 0)
        self.type_combo = QComboBox()  # 物品类型下拉框（角色/武器/光锥等）
        form.addWidget(self.type_combo, 1, 1)

        # ----- 行1右侧：星级选择 -----
        form.addWidget(QLabel("星级:"), 1, 2)
        self.rarity_combo = QComboBox()  # 星级下拉框（5星/4星/3星）
        form.addWidget(self.rarity_combo, 1, 3)

        # ----- 行2：是否UP -----
        form.addWidget(QLabel("是否UP:"), 2, 0)
        # StyledCheckBox 是自定义的复选框，显示"UP物品"文字
        self.featured_check = StyledCheckBox("UP物品")
        form.addWidget(self.featured_check, 2, 1)

        # ----- 行2右侧：抽卡时间 -----
        form.addWidget(QLabel("抽卡时间:"), 2, 2)
        # QDateTimeEdit 初始化为当前时间
        self.time_edit = QDateTimeEdit(QDateTime.currentDateTime())
        # 设置显示格式：年-月-日 时:分:秒
        self.time_edit.setDisplayFormat("yyyy-MM-dd HH:mm:ss")
        form.addWidget(self.time_edit, 2, 3)

        # ----- 行3：添加按钮 -----
        btn_layout = QHBoxLayout()
        add_btn = QPushButton("添加记录")
        add_btn.setFixedSize(120, 36)
        # 连接点击信号到 _add_single 槽函数
        add_btn.clicked.connect(self._add_single)
        btn_layout.addWidget(add_btn)
        # 右侧弹性空间，使按钮靠左
        btn_layout.addStretch()
        # 将按钮行添加到表单布局，span参数表示跨4列（row=3, col=0, rowSpan=1, colSpan=4）
        form.addLayout(btn_layout, 3, 0, 1, 4)

        # 将单条添加分组框添加到主布局
        main_layout.addWidget(single_group)

        # ===== 批量添加区域 =====
        batch_group = QGroupBox("批量添加")
        batch_group.setStyleSheet("QGroupBox { font-weight: bold; font-size: 14px; }")
        batch_layout = QVBoxLayout(batch_group)

        # 说明文字
        batch_desc = QLabel("在表格中连续输入记录，完成后点击「批量保存」")
        batch_desc.setStyleSheet("color: #666;")
        batch_layout.addWidget(batch_desc)

        # 创建20行5列的批量输入表格
        # 列：名称、类型、星级、是否UP、时间
        self.batch_table = QTableWidget(20, 5)
        self.batch_table.setHorizontalHeaderLabels(["名称", "类型", "星级", "是否UP", "时间"])
        # 所有列均匀拉伸
        self.batch_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)

        # ===== 为每行设置默认的下拉框控件 =====
        for row in range(20):
            # 第1列（类型）：设置为QComboBox
            type_combo = QComboBox()
            type_combo.addItems(["角色", "武器", "光锥", "音擎"])
            # setCellWidget 将QComboBox嵌入到表格单元格中
            self.batch_table.setCellWidget(row, 1, type_combo)

            # 第2列（星级）：设置为QComboBox
            rarity_combo = QComboBox()
            rarity_combo.addItems(["5", "4", "3"])
            self.batch_table.setCellWidget(row, 2, rarity_combo)

            # 第3列（是否UP）：设置为QComboBox
            featured_combo = QComboBox()
            featured_combo.addItems(["否", "是"])
            self.batch_table.setCellWidget(row, 3, featured_combo)

        # 将批量表格添加到批量添加区域
        batch_layout.addWidget(self.batch_table)

        # ===== 批量操作按钮 =====
        batch_btn_layout = QHBoxLayout()
        # "批量保存"按钮
        save_batch_btn = QPushButton("批量保存")
        save_batch_btn.setFixedSize(120, 36)
        save_batch_btn.clicked.connect(self._add_batch)
        batch_btn_layout.addWidget(save_batch_btn)

        # "清空表格"按钮
        clear_btn = QPushButton("清空表格")
        clear_btn.setFixedSize(100, 36)
        # 灰色背景，视觉上次要操作
        clear_btn.setStyleSheet("background-color: #666;")
        clear_btn.clicked.connect(self._clear_batch)
        batch_btn_layout.addWidget(clear_btn)
        # 右侧弹性空间
        batch_btn_layout.addStretch()
        batch_layout.addLayout(batch_btn_layout)

        # 将批量添加分组框添加到主布局
        main_layout.addWidget(batch_group)
        # 底部弹性空间，使内容靠上
        main_layout.addStretch()

        # 将内部widget设置为滚动区域的内容
        scroll.setWidget(scroll_widget)
        # 将滚动区域添加到主布局
        layout.addWidget(scroll)

        # ===== 保存批量表格下拉框的引用 =====
        # 这些引用方便后续在 refresh() 时更新下拉框选项
        self._batch_type_combos = []
        self._batch_rarity_combos = []
        for row in range(20):
            # 获取每行的类型下拉框引用
            self._batch_type_combos.append(self.batch_table.cellWidget(row, 1))
            # 获取每行的星级下拉框引用
            self._batch_rarity_combos.append(self.batch_table.cellWidget(row, 2))

    def _add_single(self):
        """添加单条抽卡记录

        流程：
            1. 检查是否有选中的账号
            2. 验证物品名称不为空
            3. 从表单控件中读取所有字段值
            4. 构造GachaRecord对象
            5. 写入数据库
            6. 清空输入框并刷新主窗口

        异常处理：
            - 无账号 → 警告提示
            - 名称为空 → 警告提示
            - 记录重复 → 提示可能已存在（数据库去重）
        """
        # 检查是否有当前账号
        account = self.main_window.get_current_account()
        if not account:
            QMessageBox.warning(self, "提示", "请先选择或创建账号")
            return

        # 获取并验证物品名称
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请输入物品名称")
            return

        # 从各控件读取表单数据
        game = self.main_window.get_current_game()  # 当前游戏
        pool = self.pool_combo.currentData()  # 卡池类型（通过currentData获取关联的数据）
        item_type = self.type_combo.currentText()  # 物品类型（显示文字）
        rarity = self.rarity_combo.currentData() or 5  # 星级（数据值，默认5）
        featured = self.featured_check.isChecked()  # 是否UP
        # 将QDateTime转换为字符串格式
        time_str = self.time_edit.dateTime().toString("yyyy-MM-dd HH:mm:ss")

        # 构造GachaRecord对象
        record = GachaRecord(
            account_id=account.id,  # 账号ID（关联到特定账号）
            game=game,  # 游戏ID
            pool_type=pool,  # 卡池类型
            item_name=name,  # 物品名称
            item_type=item_type,  # 物品类型
            rarity=rarity,  # 星级
            is_featured=featured,  # 是否UP
            time=time_str,  # 抽卡时间
        )

        # 写入数据库，返回新增记录数
        count = self.db.add_records([record])
        if count > 0:
            QMessageBox.information(self, "成功", f"已添加记录: {name}")
            # 清空名称输入框（方便连续添加）
            self.name_input.clear()
            # 刷新主窗口所有页面数据
            self.main_window.refresh_all()
        else:
            # count为0表示记录已存在（被去重）
            QMessageBox.warning(self, "提示", "记录可能已存在")

    def _add_batch(self):
        """批量添加抽卡记录

        遍历批量表格中的所有行，提取有名称的行，构造GachaRecord列表，
        一次性写入数据库。

        流程：
            1. 检查是否有当前账号
            2. 遍历表格的20行
            3. 跳过名称为空的行
            4. 从每行的控件中读取字段值
            5. 为所有有效行构造GachaRecord列表
            6. 批量写入数据库
            7. 清空表格并刷新主窗口

        注意：
            - 卡池类型统一使用当前游戏的第一个卡池类型作为默认值
            - 时间字段为空时自动使用当前时间
        """
        # 检查账号
        account = self.main_window.get_current_account()
        if not account:
            QMessageBox.warning(self, "提示", "请先选择或创建账号")
            return

        game = self.main_window.get_current_game()
        records = []

        # 遍历所有行（20行）
        for row in range(self.batch_table.rowCount()):
            # 获取名称单元格的item
            name_item = self.batch_table.item(row, 0)
            # 跳过名称为空的行
            if not name_item or not name_item.text().strip():
                continue

            # 读取各字段值
            name = name_item.text().strip()
            # cellWidget获取嵌入单元格的QComboBox，currentText获取显示文字
            item_type = self.batch_table.cellWidget(row, 1).currentText()
            rarity = int(self.batch_table.cellWidget(row, 2).currentText())
            featured = self.batch_table.cellWidget(row, 3).currentText() == "是"
            # 时间字段可能没有item（用户未输入）
            time_item = self.batch_table.item(row, 4)
            time_str = time_item.text().strip() if time_item else ""

            # 如果未输入时间，使用当前时间作为默认值
            if not time_str:
                time_str = QDateTime.currentDateTime().toString("yyyy-MM-dd HH:mm:ss")

            # 使用当前游戏的第一个卡池类型作为默认值
            pools = POOL_CONFIGS.get(game, [])
            default_pool = pools[0][0] if pools else "character"

            # 构造GachaRecord对象
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

        # 没有有效记录
        if not records:
            QMessageBox.warning(self, "提示", "没有有效的记录可保存")
            return

        # 批量写入数据库
        count = self.db.add_records(records)
        QMessageBox.information(self, "成功", f"已批量添加 {count} 条记录")
        # 清空表格
        self._clear_batch()
        # 刷新主窗口
        self.main_window.refresh_all()

    def _clear_batch(self):
        """清空批量输入表格

        清除所有行的名称（第0列）和时间（第4列）文本内容。
        类型、星级、是否UP列的下拉框保持默认值不变。
        """
        for row in range(self.batch_table.rowCount()):
            # 将名称和时间列设为None（清除单元格内容）
            # 注意：setCellWidget 的下拉框不受此影响
            self.batch_table.setItem(row, 0, None)  # 清空名称列
            self.batch_table.setItem(row, 4, None)  # 清空时间列

    def refresh(self):
        """根据当前游戏更新所有下拉框选项

        当切换游戏时调用此方法，更新：
            1. 卡池类型下拉框（pool_combo）- 根据游戏更新可用卡池
            2. 物品类型下拉框（type_combo）- 不同游戏有不同的物品类型
            3. 星级下拉框（rarity_combo）- 不同游戏的最高星级不同
            4. 批量表格中的所有下拉框

        使用 blockSignals(True/False) 包裹操作，防止多次触发信号导致意外行为。

        数据来源：
            - POOL_CONFIGS: 卡池配置 {game: [(pool_type, display_name), ...]}
            - MAX_RARITY: 最大星级 {game: max_rarity}
            - _get_item_types(): 物品类型列表
        """
        game = self.main_window.get_current_game()
        if not game:
            return

        # ===== 更新卡池下拉框 =====
        # 阻塞信号，避免clear()触发currentIndexChanged
        self.pool_combo.blockSignals(True)
        self.pool_combo.clear()
        # 从POOL_CONFIGS获取当前游戏的卡池配置
        pools = POOL_CONFIGS.get(game, [])
        for pool_type, display_name in pools:
            # addItem(display_text, data): data通过currentData()获取
            self.pool_combo.addItem(display_name, pool_type)
        self.pool_combo.blockSignals(False)

        # ===== 更新物品类型下拉框 =====
        self.type_combo.blockSignals(True)
        self.type_combo.clear()
        # 获取当前游戏对应的物品类型列表
        item_types = self._get_item_types(game)
        self.type_combo.addItems(item_types)
        self.type_combo.blockSignals(False)

        # ===== 更新星级下拉框 =====
        self.rarity_combo.blockSignals(True)
        self.rarity_combo.clear()
        # 获取当前游戏的最大星级
        max_rarity = MAX_RARITY.get(game, 5)
        # 从最高星级到3星，逐个添加（如"★★★★★ (5星)"）
        for r in range(max_rarity, 2, -1):
            stars = "★" * r
            self.rarity_combo.addItem(f"{stars} ({r}星)", r)
        self.rarity_combo.blockSignals(False)

        # ===== 更新批量表格的下拉框 =====
        item_types = self._get_item_types(game)
        for row in range(20):
            # 更新类型下拉框
            type_combo = self.batch_table.cellWidget(row, 1)
            if type_combo:
                type_combo.blockSignals(True)
                type_combo.clear()
                type_combo.addItems(item_types)
                type_combo.blockSignals(False)

            # 更新星级下拉框
            rarity_combo = self.batch_table.cellWidget(row, 2)
            if rarity_combo:
                rarity_combo.blockSignals(True)
                rarity_combo.clear()
                for r in range(max_rarity, 2, -1):
                    rarity_combo.addItem(str(r), r)
                rarity_combo.blockSignals(False)

    def _get_item_types(self, game):
        """根据游戏返回物品类型列表

        不同游戏的物品类型命名不同：
            - 原神/鸣潮/终末地：角色、武器
            - 星穹铁道：角色、光锥
            - 绝区零：角色、音擎
            - 明日方舟：只有角色

        参数：
            game (str): 游戏ID

        返回：
            list[str]: 物品类型字符串列表，如["角色", "武器"]

        数据结构：
            type_map: dict[str, list[str]]
                键为游戏ID，值为该游戏的物品类型列表
        """
        # 游戏到物品类型的映射
        type_map = {
            "genshin": ["角色", "武器"],
            "starrail": ["角色", "光锥"],
            "zzz": ["角色", "音擎"],
            "wutheringwaves": ["角色", "武器"],
            "endfield": ["角色", "武器"],
            "arknights": ["角色"],
        }
        # 未识别的游戏使用默认值
        return type_map.get(game, ["角色", "武器"])
