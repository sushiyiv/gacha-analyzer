"""设置页面

本模块实现了应用程序的设置界面，提供以下功能：
- 账号管理（添加、删除、查看账号列表）
- 数据管理（备份、恢复、清空、导出JSON/CSV/Excel、重新计算保底数、更新卡池分类）
- 缓存路径配置（各游戏缓存文件的路径设置）
- 关于信息展示

所有操作通过Database和Config类与后端交互，使用QMessageBox进行用户反馈。
"""

# ========== 导入语句 ==========

# os模块：提供操作系统级别的功能
# 这里主要用于文件路径处理等（虽然当前代码中os的直接使用不多，
# 但QFileDialog返回的路径是操作系统相关的）
import os

# json模块：用于JSON数据的序列化和反序列化
# 在导出功能中可能间接使用
import json

# 导入PySide6的窗口部件模块
# QWidget: 窗口部件基类
# QVBoxLayout: 垂直布局
# QHBoxLayout: 水平布局
# QLabel: 文本标签
# QFrame: 带边框容器
# QPushButton: 可点击按钮
# QLineEdit: 单行文本输入框
# QFileDialog: 文件选择对话框（打开/保存文件时弹出）
# QMessageBox: 消息对话框（提示、警告、确认等）
# QGroupBox: 带标题的分组框
# QFormLayout: 表单布局，自动对齐标签和输入框（左标签右输入）
# QComboBox: 下拉选择框
# QScrollArea: 滚动区域
# QTableWidget: 表格组件
# QTableWidgetItem: 表格单元格项
# QHeaderView: 表格表头
# QInputDialog: 输入对话框，弹出一个小窗口让用户输入文本
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QLineEdit, QFileDialog, QMessageBox,
    QGroupBox, QFormLayout, QComboBox, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QInputDialog
)

# Qt: PySide6核心模块，包含枚举值和基础类型
from PySide6.QtCore import Qt

# QFont: 字体类
from PySide6.QtGui import QFont

# Database: 数据库操作封装类
from core.database import Database

# Config: 应用配置管理类，提供get/set/save等方法
# 用于读写用户设置（如缓存路径、备份目录等）
from core.config import Config

# Account: 账号数据模型类，包含game、uid、nickname、server等字段
# GAME_NAMES: 游戏ID到显示名称的映射字典
# 如 {"genshin": "原神", "starrail": "星穹铁道", ...}
from core.models import Account, GAME_NAMES


class SettingsWidget(QWidget):
    """设置页面组件

    提供应用程序的配置管理界面，包括账号管理、数据备份恢复、
    导出功能和缓存路径配置。

    属性:
        main_window: 主窗口引用
        db: Database实例
        config: Config实例
        account_table: 账号列表表格
        path_inputs: 缓存路径输入框字典 {game_id: QLineEdit}
    """

    def __init__(self, main_window):
        """构造函数

        参数:
            main_window: 主窗口实例引用，用于：
                        - get_current_game(): 获取当前选择的游戏
                        - get_current_account(): 获取当前选中的账号
                        - refresh_all(): 刷新所有页面的数据
        """
        # 调用父类QWidget构造函数，完成Qt对象的基础初始化
        super().__init__()

        # 保存主窗口引用，供后续调用主窗口方法使用
        self.main_window = main_window

        # 创建数据库操作实例
        self.db = Database()

        # 创建配置管理实例
        # Config类封装了用户配置的读写操作，通常使用JSON文件或INI文件存储
        self.config = Config()

        # 初始化UI界面
        self._init_ui()

    def _init_ui(self):
        """初始化设置页面的完整UI布局

        页面从上到下包含以下区块：
        1. 标题 "设置"
        2. 账号管理区块（表格 + 操作按钮）
        3. 数据管理区块（备份/恢复/清空/导出按钮）
        4. 缓存路径配置区块（各游戏路径输入）
        5. 关于区块（版本信息和隐私说明）

        所有内容包裹在QScrollArea中，支持滚动查看。
        """

        # 创建页面根布局（垂直排列）
        layout = QVBoxLayout(self)
        # 移除默认的四边内边距，让内容贴边显示
        layout.setContentsMargins(0, 0, 0, 0)

        # 创建滚动区域作为页面内容的容器
        scroll = QScrollArea()
        # 内容组件自动调整大小以填满滚动区域
        scroll.setWidgetResizable(True)
        # 无边框外观
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        # 滚动区域内的内容widget
        scroll_widget = QWidget()
        # 内容垂直布局
        main_layout = QVBoxLayout(scroll_widget)

        # ===== 页面标题 =====
        title = QLabel("设置")
        # 18号粗体微软雅黑
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        main_layout.addWidget(title)

        # ===== 账号管理区块 =====
        # QGroupBox提供带标题的边框容器
        account_group = QGroupBox("账号管理")
        account_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 14px; }"
        )
        # 分组框内部使用垂直布局
        account_layout = QVBoxLayout(account_group)

        # 创建账号列表表格，4列：游戏、UID、昵称、操作
        self.account_table = QTableWidget()
        self.account_table.setColumnCount(4)
        self.account_table.setHorizontalHeaderLabels(
            ["游戏", "UID", "昵称", "操作"]
        )
        # 列宽自动拉伸填满
        self.account_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        # 隐藏行号
        self.account_table.verticalHeader().setVisible(False)
        # 禁止编辑
        self.account_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        # 最小高度300px
        self.account_table.setMinimumHeight(300)
        account_layout.addWidget(self.account_table)

        # 按钮行：添加账号 + 刷新列表
        account_btn_layout = QHBoxLayout()

        # "添加账号"按钮
        add_account_btn = QPushButton("添加账号")
        # clicked信号连接到_add_account方法
        # clicked信号在用户点击按钮时发出，参数为checked布尔值（普通按钮始终为False）
        add_account_btn.clicked.connect(self._add_account)
        account_btn_layout.addWidget(add_account_btn)

        # "刷新列表"按钮
        refresh_btn = QPushButton("刷新列表")
        # 设置灰色背景样式
        refresh_btn.setStyleSheet("background-color: #666;")
        # 连接到_refresh_accounts方法
        refresh_btn.clicked.connect(self._refresh_accounts)
        account_btn_layout.addWidget(refresh_btn)

        # 在按钮行右侧添加弹性空间，让按钮靠左排列
        account_btn_layout.addStretch()
        account_layout.addLayout(account_btn_layout)

        # 将账号管理分组添加到主布局
        main_layout.addWidget(account_group)

        # ===== 数据管理区块 =====
        data_group = QGroupBox("数据管理")
        data_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 14px; }"
        )
        data_layout = QVBoxLayout(data_group)

        # --- 第一行按钮：备份、恢复、清空 ---
        btn_row1 = QHBoxLayout()

        # "备份数据库"按钮
        backup_btn = QPushButton("备份数据库")
        backup_btn.clicked.connect(self._backup)
        btn_row1.addWidget(backup_btn)

        # "恢复备份"按钮
        restore_btn = QPushButton("恢复备份")
        restore_btn.clicked.connect(self._restore)
        btn_row1.addWidget(restore_btn)

        # "清空当前账号数据"按钮（红色背景警示危险操作）
        clear_btn = QPushButton("清空当前账号数据")
        # #d32f2f是Material Design Red 700，用于危险/破坏性操作
        clear_btn.setStyleSheet("background-color: #d32f2f;")
        clear_btn.clicked.connect(self._clear_data)
        btn_row1.addWidget(clear_btn)

        # 右侧弹性空间
        btn_row1.addStretch()
        data_layout.addLayout(btn_row1)

        # --- 第二行按钮：导出 + 工具 ---
        btn_row2 = QHBoxLayout()

        # "导出 JSON"按钮
        export_json_btn = QPushButton("导出 JSON")
        # lambda: self._export("json") 创建一个匿名函数，点击时调用导出方法并传入格式参数
        # 这种模式避免了为每种格式单独写一个方法
        export_json_btn.clicked.connect(lambda: self._export("json"))
        btn_row2.addWidget(export_json_btn)

        # "导出 Excel"按钮
        export_excel_btn = QPushButton("导出 Excel")
        export_excel_btn.clicked.connect(lambda: self._export("excel"))
        btn_row2.addWidget(export_excel_btn)

        # "导出 CSV"按钮
        export_csv_btn = QPushButton("导出 CSV")
        export_csv_btn.clicked.connect(lambda: self._export("csv"))
        btn_row2.addWidget(export_csv_btn)

        # "重新计算保底数"按钮（灰色背景，表示次要操作）
        recalc_btn = QPushButton("重新计算保底数")
        recalc_btn.setStyleSheet("background-color: #666;")
        # 连接到保底重算方法
        recalc_btn.clicked.connect(self._recalculate_pity)
        btn_row2.addWidget(recalc_btn)

        # "更新卡池分类"按钮（用于修复明日方舟联动卡池分类错误）
        update_pool_btn = QPushButton("更新卡池分类")
        update_pool_btn.setStyleSheet("background-color: #666;")
        # setToolTip设置鼠标悬停时显示的提示文字
        update_pool_btn.setToolTip(
            "更新明日方舟卡池分类（修复联动卡池被错误分类的问题）"
        )
        update_pool_btn.clicked.connect(self._update_arknights_pool_types)
        btn_row2.addWidget(update_pool_btn)

        btn_row2.addStretch()
        data_layout.addLayout(btn_row2)

        # 将数据管理分组添加到主布局
        main_layout.addWidget(data_group)

        # ===== 缓存路径配置区块 =====
        path_group = QGroupBox("缓存路径配置")
        path_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 14px; }"
        )
        # 使用QFormLayout，它自动将标签放左侧、输入框放右侧，形成表单式布局
        path_layout = QFormLayout(path_group)

        # 存储各游戏的路径输入框引用，key为game_id
        self.path_inputs = {}

        # 不需要缓存路径的游戏列表
        # 终末地和明日方舟使用日志文件获取token，不需要配置缓存路径
        no_cache_games = ["endfield", "arknights"]

        # 遍历所有支持的游戏
        # GAME_NAMES是字典，items()返回(key, value)对
        for game_id, name in GAME_NAMES.items():
            if game_id in no_cache_games:
                # 不需要缓存路径的游戏：显示灰色斜体提示文字
                hint_label = QLabel("该游戏使用登录方式获取，无需配置缓存路径")
                hint_label.setStyleSheet("color: #888; font-style: italic;")
                # addRow(标签, 控件)是QFormLayout的方法，自动排列表单行
                path_layout.addRow(f"{name}:", hint_label)
            else:
                # 需要缓存路径的游戏：显示文本输入框
                path_input = QLineEdit()
                # setPlaceholderText设置输入框为空时的灰色占位文字
                path_input.setPlaceholderText(f"默认路径（留空使用默认）")
                # 最小宽度400px，确保路径输入框有足够空间显示长路径
                path_input.setMinimumWidth(400)
                # 从配置中读取当前保存的路径，config.get()支持点号分隔的嵌套key
                # 如 "cache_paths.genshin.cn" 读取原神国服的缓存路径
                current = self.config.get(f"cache_paths.{game_id}.cn", "")
                # 将已保存的路径填入输入框
                path_input.setText(current)
                # 保存输入框引用，后续保存时需要读取其内容
                self.path_inputs[game_id] = path_input
                # 添加到表单行
                path_layout.addRow(f"{name}:", path_input)

        # "保存路径配置"按钮
        save_path_btn = QPushButton("保存路径配置")
        # 固定按钮大小
        save_path_btn.setFixedSize(140, 32)
        save_path_btn.clicked.connect(self._save_paths)
        # 第一个参数为空字符串表示不显示标签（按钮独占一行）
        path_layout.addRow("", save_path_btn)

        main_layout.addWidget(path_group)

        # ===== 关于区块 =====
        about_group = QGroupBox("关于")
        about_group.setStyleSheet(
            "QGroupBox { font-weight: bold; font-size: 14px; }"
        )
        about_layout = QVBoxLayout(about_group)
        # 添加三行关于信息
        about_layout.addWidget(QLabel("穷观阵 v1.0.0"))
        about_layout.addWidget(
            QLabel("支持游戏: 原神、星穹铁道、绝区零、鸣潮、终末地、明日方舟")
        )
        about_layout.addWidget(
            QLabel("数据完全离线存储，不会上传到任何服务器")
        )
        main_layout.addWidget(about_group)

        # 底部弹性空间，让所有内容紧靠顶部
        main_layout.addStretch()
        # 关联滚动区域的内容widget
        scroll.setWidget(scroll_widget)
        # 将滚动区域添加到页面根布局
        layout.addWidget(scroll)

    def refresh(self):
        """外部调用的刷新入口

        当主窗口需要刷新设置页面时（如账号切换后），
        会调用此方法。目前仅刷新账号列表。
        """
        self._refresh_accounts()

    def _refresh_accounts(self):
        """刷新账号列表表格

        从数据库读取所有账号信息，重新填充表格。
        每次刷新都会完全重建表格内容（先清空再填充），
        这种方式简单可靠，适合数据量不大的场景。

        表格中"操作"列使用setCellWidget()嵌入实际的QPushButton，
        而不是使用QTableWidgetItem，这样按钮可以正常响应点击事件。
        """
        # 从数据库获取所有账号列表
        accounts = self.db.get_accounts()

        # 设置表格行数
        self.account_table.setRowCount(len(accounts))

        # 逐行填充账号信息
        for i, acc in enumerate(accounts):
            # 第0列：游戏名称
            # GAME_NAMES.get(acc.game, acc.game) 如果游戏ID在映射表中则返回中文名，
            # 否则返回原始game ID作为兜底
            self.account_table.setItem(
                i, 0, QTableWidgetItem(GAME_NAMES.get(acc.game, acc.game))
            )
            # 第1列：UID
            self.account_table.setItem(i, 1, QTableWidgetItem(acc.uid))
            # 第2列：昵称
            self.account_table.setItem(i, 2, QTableWidgetItem(acc.nickname))

            # 第3列：删除按钮（使用setCellWidget嵌入实际按钮组件）
            del_btn = QPushButton("删除")
            # 固定按钮尺寸
            del_btn.setFixedSize(60, 28)
            # 红色背景 + 小字号
            del_btn.setStyleSheet(
                "background-color: #d32f2f; font-size: 12px;"
            )
            # lambda中的默认参数aid=acc.id是关键技巧：
            # Python的lambda在循环中会捕获变量的引用而非值，
            # 如果不用默认参数，所有lambda都会引用同一个acc.id（最后一个账号的ID）
            # 使用默认参数aid=acc.id可以在lambda创建时立即绑定当前值
            del_btn.clicked.connect(
                lambda checked, aid=acc.id: self._delete_account(aid)
            )
            # 将按钮嵌入表格单元格
            self.account_table.setCellWidget(i, 3, del_btn)

    def _add_account(self):
        """添加新账号

        弹出两个输入对话框让用户输入：
        1. 游戏UID（必填）
        2. 昵称（可选）

        创建Account对象并保存到数据库，然后刷新账号列表和所有页面。

        QInputDialog.getText()返回一个元组(text, ok)：
        - text: 用户输入的文本
        - ok: True表示用户点击了"确定"，False表示点击了"取消"
        """
        # 获取当前选择的游戏类型
        game = self.main_window.get_current_game()

        # 弹出输入对话框获取UID
        # 参数: parent, title, label, default_text, ok, flags
        uid, ok = QInputDialog.getText(self, "添加账号", "请输入游戏UID:")
        # 用户取消或输入为空时直接返回
        if not ok or not uid.strip():
            return

        # 弹出第二个对话框获取昵称（可选）
        nickname, _ = QInputDialog.getText(
            self, "设置昵称", "请输入昵称（可选）:"
        )
        # _ 是Python惯例，表示我们不关心第二个返回值(ok标志)

        # 创建Account数据模型实例
        account = Account(
            game=game,
            uid=uid.strip(),  # strip()去除首尾空白字符
            nickname=nickname.strip() if nickname else "",
            server="cn",  # 默认国服
        )
        # 将账号写入数据库
        self.db.add_account(account)
        # 刷新账号列表表格
        self._refresh_accounts()
        # 刷新所有页面（因为新账号可能影响统计、图表等页面的显示）
        self.main_window.refresh_all()
        # 弹出成功提示消息框
        QMessageBox.information(self, "成功", f"已添加账号: {uid}")

    def _delete_account(self, account_id):
        """删除账号及其所有抽卡记录

        参数:
            account_id (int): 要删除的账号ID（数据库主键）

        该操作不可恢复，因此会弹出确认对话框让用户二次确认。
        QMessageBox.question()创建一个带有Yes/No按钮的对话框。
        """
        # 弹出确认对话框
        reply = QMessageBox.question(
            self,                    # parent: 父组件（设置对话框的所属窗口）
            "确认删除",              # title: 对话框标题
            "确定要删除此账号及其所有抽卡记录吗？此操作不可恢复。",  # 文本
            # 按钮组合：Yes和No两个标准按钮
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        # 用户确认删除
        if reply == QMessageBox.StandardButton.Yes:
            # 从数据库删除账号（级联删除关联的抽卡记录）
            self.db.delete_account(account_id)
            # 刷新账号列表
            self._refresh_accounts()
            # 刷新所有页面
            self.main_window.refresh_all()

    def _backup(self):
        """备份数据库

        调用Database.backup()方法执行备份操作。
        backup()方法内部会将SQLite数据库文件复制到备份目录，
        文件名通常包含时间戳以便区分不同版本。

        异常处理:
            使用try/except捕获所有异常，向用户显示错误信息。
            常见异常：磁盘空间不足、权限不足、文件被占用等。
        """
        try:
            # 执行备份，返回备份文件的完整路径
            path = self.db.backup()
            # 成功后弹出提示，显示备份文件路径
            QMessageBox.information(
                self, "备份成功", f"数据库已备份到:\n{path}"
            )
        except Exception as e:
            # 备份失败时显示错误信息
            # QMessageBox.critical()显示错误级别（红色图标）的对话框
            QMessageBox.critical(self, "备份失败", str(e))

    def _restore(self):
        """从备份文件恢复数据库

        操作流程：
        1. 打开文件选择对话框让用户选择备份文件
        2. 弹出确认对话框警告数据覆盖风险
        3. 用户确认后执行恢复操作
        4. 刷新所有页面

        QFileDialog.getOpenFileName()返回元组(filepath, filter)：
        - filepath: 选择的文件完整路径，用户取消时为空字符串
        - filter: 应用的文件过滤器字符串
        """
        # 打开文件选择对话框，初始目录为配置中的备份目录
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择备份文件", self.config.backup_dir,
            "数据库文件 (*.db)"  # 文件过滤器，只显示.db文件
        )
        # 用户取消选择
        if not filepath:
            return

        # 弹出确认对话框，警告恢复操作会覆盖当前数据
        reply = QMessageBox.question(
            self, "确认恢复",
            "恢复备份将覆盖当前所有数据，确定继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                # 执行数据库恢复：将备份文件的内容覆盖当前数据库
                self.db.restore(filepath)
                QMessageBox.information(self, "恢复成功", "数据已恢复")
                # 恢复成功后刷新所有页面以显示新数据
                self.main_window.refresh_all()
            except Exception as e:
                # 恢复失败（如文件损坏、格式不兼容等）
                QMessageBox.critical(self, "恢复失败", str(e))

    def _clear_data(self):
        """清空当前选中账号的所有抽卡记录

        仅清空抽卡记录，账号信息本身保留。
        操作不可恢复，会弹出确认对话框。

        注意：该操作不会删除账号条目，只删除关联的抽卡记录。
        """
        # 获取当前选中的账号
        account = self.main_window.get_current_account()
        # 未选择账号时提示用户
        if not account:
            QMessageBox.warning(self, "提示", "请先选择账号")
            return

        # 确认对话框，显示将要清空的账号UID
        reply = QMessageBox.question(
            self, "确认清空",
            f"确定要清空账号 {account.uid} 的所有抽卡记录吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            # 调用数据库方法清空该账号的所有抽卡记录
            self.db.clear_records(account.id)
            QMessageBox.information(self, "完成", "数据已清空")
            self.main_window.refresh_all()

    def _export(self, fmt):
        """导出抽卡记录为指定格式

        参数:
            fmt (str): 导出格式，支持以下值：
                      - "json": JSON格式，保留完整的数据结构
                      - "csv": CSV格式，兼容Excel等电子表格软件
                      - "excel": Excel格式(.xlsx)，需要openpyxl库

        操作流程：
        1. 检查是否有选中的账号和可导出的数据
        2. 弹出文件保存对话框让用户选择保存位置
        3. 根据格式执行对应的导出逻辑
        4. 显示成功/失败提示

        异常处理:
            - CSV导出：使用utf-8-sig编码（带BOM），确保Excel正确识别中文
            - Excel导出：需要openpyxl库，缺失时给出安装提示
        """
        # 获取当前选中的账号
        account = self.main_window.get_current_account()
        if not account:
            QMessageBox.warning(self, "提示", "请先选择账号")
            return

        # 获取该账号的所有抽卡记录
        records = self.db.get_records(account.id)
        if not records:
            QMessageBox.warning(self, "提示", "没有可导出的数据")
            return

        # ===== JSON格式导出 =====
        if fmt == "json":
            # 弹出文件保存对话框
            # getSaveFileName返回(filepath, filter)元组
            filepath, _ = QFileDialog.getSaveFileName(
                self, "导出JSON", self.config.export_dir,
                "JSON (*.json)"  # 默认文件过滤器
            )
            if filepath:
                # 使用Database的export_json方法生成JSON字符串
                data = self.db.export_json(account.id)
                # 以UTF-8编码写入文件（with语句确保文件正确关闭）
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(data)
                QMessageBox.information(
                    self, "导出成功", f"已导出到: {filepath}"
                )

        # ===== CSV格式导出 =====
        elif fmt == "csv":
            filepath, _ = QFileDialog.getSaveFileName(
                self, "导出CSV", self.config.export_dir,
                "CSV (*.csv)"
            )
            if filepath:
                # 懒导入csv模块（只在需要时导入，减少启动时间）
                import csv
                # utf-8-sig编码：写入BOM(Byte Order Mark)字节序标记
                # 这样Excel打开CSV文件时能正确识别UTF-8编码的中文
                # newline=""防止Windows下CSV写入时出现多余的空行
                with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.writer(f)
                    # 写入表头行
                    writer.writerow([
                        "游戏", "卡池类型", "卡池名称", "名称",
                        "类型", "星级", "UP", "时间", "保底"
                    ])
                    # 逐行写入数据
                    for r in records:
                        writer.writerow([
                            r.game,          # 游戏标识
                            r.pool_type,     # 卡池类型（如standard, limited）
                            r.pool_name,     # 卡池显示名称
                            r.item_name,     # 抽到的物品名称
                            r.item_type,     # 物品类型（角色/武器）
                            r.rarity,        # 星级数字
                            "是" if r.is_featured else "否",  # 是否为UP物品
                            r.time,          # 获取时间
                            r.pity_count     # 当时的保底计数
                        ])
                QMessageBox.information(
                    self, "导出成功", f"已导出到: {filepath}"
                )

        # ===== Excel格式导出 =====
        elif fmt == "excel":
            filepath, _ = QFileDialog.getSaveFileName(
                self, "导出Excel", self.config.export_dir,
                "Excel (*.xlsx)"
            )
            if filepath:
                try:
                    # 懒导入openpyxl（第三方库，可能未安装）
                    import openpyxl
                    # 创建新的工作簿（Excel文件）
                    wb = openpyxl.Workbook()
                    # 获取默认活动工作表
                    ws = wb.active
                    # 设置工作表标签名
                    ws.title = "抽卡记录"
                    # append()方法可以添加一行数据（接受列表）
                    ws.append([
                        "游戏", "卡池类型", "卡池名称", "名称",
                        "类型", "星级", "UP", "时间", "保底"
                    ])
                    # 逐行追加数据
                    for r in records:
                        ws.append([
                            r.game, r.pool_type, r.pool_name,
                            r.item_name, r.item_type, r.rarity,
                            "是" if r.is_featured else "否",
                            r.time, r.pity_count
                        ])
                    # 保存工作簿到指定路径
                    wb.save(filepath)
                    QMessageBox.information(
                        self, "导出成功", f"已导出到: {filepath}"
                    )
                except ImportError:
                    # openpyxl未安装时的友好提示
                    QMessageBox.warning(self, "提示", "需要安装 openpyxl")

    def _save_paths(self):
        """保存缓存路径配置

        遍历所有游戏的路径输入框，将非空的路径保存到配置文件。
        空路径不保存，这样应用会继续使用默认路径。
        """
        # 遍历path_inputs字典中的每个游戏路径输入框
        for game_id, input_widget in self.path_inputs.items():
            # 获取输入框中的文本并去除首尾空白
            path = input_widget.text().strip()
            # 只保存非空路径
            if path:
                # config.set()支持嵌套key，用点号分隔层级
                # 如 "cache_paths.genshin.cn" 会被存储为嵌套结构
                self.config.set(f"cache_paths.{game_id}.cn", path)
        # 将配置写入磁盘（持久化保存）
        self.config.save()
        QMessageBox.information(self, "保存成功", "路径配置已保存")

    def _recalculate_pity(self):
        """重新计算所有账号的保底数

        该功能用于修复保底计数不准确的情况，如：
        - 手动修改了数据库
        - 导入了外部数据后保底计数未同步
        - 升级了保底计算逻辑

        操作流程：
        1. 从数据库获取所有账号
        2. 弹出确认对话框
        3. 逐个账号重新计算保底数
        4. 刷新所有页面
        """
        # 获取所有账号
        accounts = self.db.get_accounts()
        if not accounts:
            QMessageBox.information(self, "提示", "没有账号需要处理")
            return

        # 确认对话框
        reply = QMessageBox.question(
            self, "确认重新计算",
            f"确定要重新计算 {len(accounts)} 个账号的保底数吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        # 用户取消
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 遍历每个账号，调用数据库方法重新计算保底数
        # calculate_pity_counts()会重新遍历该账号的所有抽卡记录，
        # 按时间顺序重新计算每条记录的pity_count字段
        for account in accounts:
            self.db.calculate_pity_counts(account.id)

        QMessageBox.information(
            self, "完成",
            f"已重新计算 {len(accounts)} 个账号的保底数"
        )
        self.main_window.refresh_all()

    def _update_arknights_pool_types(self):
        """更新明日方舟卡池分类

        修复联动卡池（如幽境狩人）被错误分类为标准寻访的问题。
        该方法通过poolId前缀来判断正确的卡池类型：
        - LIMITED_*: 限定池 -> "limited"
        - LINKAGE_*: 联动池 -> "limited"
        - CLASSIC_*: 经典寻访 -> "kernel"
        - 其他: 标准寻访 -> "standard"

        会弹出确认对话框说明操作内容。
        """
        # 懒导入ast模块（用于安全地解析raw_data字符串）
        import ast

        # 确认对话框，详细说明操作目的和影响
        reply = QMessageBox.question(
            self, "确认更新",
            "这将根据 poolId 更新明日方舟的卡池分类。\n"
            "主要修复联动卡池（如幽境狩人）被错误分类为标准寻访的问题。\n\n"
            "确定继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        # 执行实际的更新操作
        updated = self._do_update_arknights_pool_types()

        # 显示更新结果
        QMessageBox.information(
            self, "完成", f"已更新 {updated} 条记录的卡池分类"
        )
        self.main_window.refresh_all()

    def _do_update_arknights_pool_types(self):
        """执行明日方舟卡池分类更新的具体逻辑

        该方法直接操作数据库，流程：
        1. 查询所有明日方舟的抽卡记录
        2. 从每条记录的raw_data中提取poolId
        3. 根据poolId前缀判断正确的卡池类型
        4. 更新数据库中的pool_type字段
        5. 重新计算保底数

        返回:
            int: 更新的记录条数

        注意:
            - 使用ast.literal_eval()安全解析raw_data字符串
            - raw_data可能为None或格式不正确，需要异常处理
            - poolId比较时统一转为大写以避免大小写敏感问题
        """
        # ast模块用于安全地解析Python字面量表达式
        import ast

        # 获取数据库连接对象（确保连接存在）
        conn = self.db._ensure_conn()

        # 查询所有明日方舟的抽卡记录
        # 使用row_factory(cursor)返回的行对象支持通过列名访问数据
        rows = conn.execute(
            "SELECT id, pool_name, raw_data FROM gacha_records "
            "WHERE game='arknights'"
        ).fetchall()

        updated = 0  # 计数器：记录更新了多少条

        # 逐条处理记录
        for row in rows:
            record_id = row["id"]        # 记录的数据库主键
            pool_name = row["pool_name"]  # 卡池名称
            raw_data = row["raw_data"]    # 原始数据字符串（JSON格式或dict字面量）

            # 跳过没有原始数据的记录
            if not raw_data:
                continue

            try:
                # ast.literal_eval()安全地将字符串解析为Python对象
                # 比eval()更安全，只解析字面量（字符串、数字、字典、列表等）
                # 不会执行任意代码，防止注入攻击
                raw = ast.literal_eval(raw_data)
                # 从解析后的字典中获取poolId
                pool_id = raw.get("poolId", "")
            except Exception:
                # 解析失败（格式不正确）则跳过该记录
                continue

            # 根据poolId前缀判断正确的卡池类型
            new_pool_type = None
            if pool_id:
                # 统一转为大写进行比较，避免大小写敏感问题
                pool_id_upper = pool_id.upper()
                if pool_id_upper.startswith("LIMITED_"):
                    new_pool_type = "limited"  # 限定池
                elif pool_id_upper.startswith("LINKAGE_"):
                    new_pool_type = "limited"  # 联动池归类为限定池
                elif pool_id_upper.startswith("CLASSIC_"):
                    new_pool_type = "kernel"   # 经典寻访（中坚寻访）
                else:
                    new_pool_type = "standard"  # 标准寻访（默认）

            # 如果成功确定了新类型，执行数据库更新
            if new_pool_type:
                conn.execute(
                    "UPDATE gacha_records SET pool_type=? WHERE id=?",
                    (new_pool_type, record_id)
                )
                updated += 1

        # 提交事务，将所有更新写入数据库
        # SQLite默认每条SQL自动提交，但这里批量操作后统一提交更高效
        conn.commit()

        # 重新计算所有明日方舟账号的保底数
        # 因为卡池分类变化会影响保底计算（不同类型的池保底不共享）
        for account in self.db.get_accounts("arknights"):
            self.db.calculate_pity_counts(account.id)

        return updated
