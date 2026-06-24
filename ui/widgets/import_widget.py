"""数据导入页面"""

import json
import os
import csv
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QLineEdit, QTextEdit, QFileDialog, QMessageBox,
    QProgressBar, QGroupBox, QGridLayout, QComboBox, QDialog
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont

from core.database import Database
from core.models import Account, GachaRecord, GAME_NAMES
from fetchers import get_fetcher
from fetchers.url_parser import URLParser
from ui.widgets.style_constants import GROUPBOX_STYLE


class FetchThread(QThread):
    """后台获取线程"""
    progress = Signal(str, float)
    finished = Signal(list)
    error = Signal(str)

    def __init__(self, game, url=None, account_id=None, latest_time=None):
        super().__init__()
        self.game = game
        self.url = url
        self.account_id = account_id
        self.latest_time = latest_time
        self._cancelled = False
        self.detected_uid = ""

    def cancel(self):
        self._cancelled = True

    def is_cancelled(self):
        return self._cancelled

    def run(self):
        try:
            fetcher = get_fetcher(self.game)
            self._fetcher_instance = fetcher  # 保存引用供取消时使用
            fetcher.set_progress_callback(lambda msg, p: self.progress.emit(msg, p))
            fetcher._cancel_check = self.is_cancelled
            records = fetcher.fetch_records(url=self.url, account_id=self.account_id, latest_time=self.latest_time)
            self.detected_uid = getattr(fetcher, '_detected_uid', '')
            if self._cancelled:
                self.error.emit("用户已取消获取")
            else:
                self.finished.emit(records)
        except Exception as e:
            if self._cancelled:
                self.error.emit("用户已取消获取")
            else:
                self.error.emit(str(e))


class ImportWidget(QWidget):
    """数据导入页面"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.db = Database()
        self.fetch_thread = None
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # 标题
        title = QLabel("获取数据")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        layout.addWidget(title)

        subtitle = QLabel("选择一种方式导入抽卡记录")
        subtitle.setStyleSheet("color: #888; font-size: 13px;")
        layout.addWidget(subtitle)

        # 方式一：自动获取
        auto_group = QGroupBox("方式一：自动获取（推荐）")
        auto_group.setStyleSheet(GROUPBOX_STYLE)
        auto_layout = QVBoxLayout(auto_group)

        # 游戏选择 + 按钮 同一行
        select_layout = QHBoxLayout()
        select_layout.addWidget(QLabel("游戏:"))
        self.auto_game_combo = QComboBox()
        self._auto_game_options = [
            ("all", "全部游戏"),
            ("genshin", "原神"),
            ("starrail", "星穹铁道"),
            ("zzz", "绝区零"),
            ("wutheringwaves", "鸣潮"),
            ("endfield", "终末地"),
            ("arknights", "明日方舟"),
        ]
        for gid, gname in self._auto_game_options:
            self.auto_game_combo.addItem(gname, gid)
        select_layout.addWidget(self.auto_game_combo)

        self.auto_fetch_btn = QPushButton("开始获取")
        self.auto_fetch_btn.setObjectName("primary_button")
        self.auto_fetch_btn.setFixedSize(100, 32)
        self.auto_fetch_btn.clicked.connect(self._auto_fetch)
        select_layout.addWidget(self.auto_fetch_btn)
        select_layout.addStretch()
        auto_layout.addLayout(select_layout)

        # 说明
        auto_desc = QLabel("请确保已打开对应游戏并进入抽卡记录页面")
        auto_desc.setStyleSheet("color: #666;")
        auto_layout.addWidget(auto_desc)

        layout.addWidget(auto_group)

        # 方式二：手动粘贴URL
        url_group = QGroupBox("方式二：手动粘贴URL")
        url_group.setStyleSheet(auto_group.styleSheet())
        url_layout = QVBoxLayout(url_group)

        url_desc = QLabel(
            "通过抓包工具获取抽卡记录API的完整URL，粘贴到下方输入框。"
        )
        url_desc.setStyleSheet("color: #666;")
        url_layout.addWidget(url_desc)

        self._endfield_hint = QLabel(
            "终末地：粘贴鹰角账号Token（点击下方登录获取按钮进行获取）"
        )
        self._endfield_hint.setStyleSheet("color: #666;")
        url_layout.addWidget(self._endfield_hint)

        self._arknights_hint = QLabel(
            "明日方舟：粘贴鹰角账号Token（点击下方登录获取按钮进行获取）"
        )
        self._arknights_hint.setStyleSheet("color: #666;")
        url_layout.addWidget(self._arknights_hint)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText("粘贴抽卡记录URL")
        url_layout.addWidget(self.url_input)

        url_btn_layout = QHBoxLayout()
        self.url_fetch_btn = QPushButton("解析获取")
        self.url_fetch_btn.setObjectName("primary_button")
        self.url_fetch_btn.setFixedSize(120, 36)
        self.url_fetch_btn.clicked.connect(self._url_fetch)
        url_btn_layout.addWidget(self.url_fetch_btn)

        paste_btn = QPushButton("从剪贴板粘贴")
        paste_btn.setFixedSize(120, 36)
        paste_btn.setStyleSheet("background-color: #666;")
        paste_btn.clicked.connect(self._paste_from_clipboard)
        url_btn_layout.addWidget(paste_btn)

        self.login_btn = QPushButton("登录获取")
        self.login_btn.setFixedSize(120, 36)
        self.login_btn.setStyleSheet("background-color: #E65100;")
        self.login_btn.setToolTip("登录鹰角账号获取Token（仅终末地和明日方舟）")
        self.login_btn.clicked.connect(self._login_fetch)
        url_btn_layout.addWidget(self.login_btn)

        # 连接游戏选择下拉框信号，控制登录按钮显示
        self.auto_game_combo.currentIndexChanged.connect(self._update_login_btn_visibility)
        # 初始化登录按钮显示状态
        self._update_login_btn_visibility()

        url_btn_layout.addStretch()
        url_layout.addLayout(url_btn_layout)

        layout.addWidget(url_group)

        # 方式三：文件导入
        file_group = QGroupBox("方式三：文件导入")
        file_group.setStyleSheet(auto_group.styleSheet())
        file_layout = QVBoxLayout(file_group)

        file_desc = QLabel("支持 JSON、Excel (.xlsx)、CSV 格式")
        file_desc.setStyleSheet("color: #666;")
        file_layout.addWidget(file_desc)

        file_btn_layout = QHBoxLayout()
        json_btn = QPushButton("导入 JSON")
        json_btn.setObjectName("primary_button")
        json_btn.clicked.connect(lambda: self._import_file("json"))
        excel_btn = QPushButton("导入 Excel")
        excel_btn.setObjectName("primary_button")
        excel_btn.clicked.connect(lambda: self._import_file("excel"))
        csv_btn = QPushButton("导入 CSV")
        csv_btn.setObjectName("primary_button")
        csv_btn.clicked.connect(lambda: self._import_file("csv"))

        file_btn_layout.addWidget(json_btn)
        file_btn_layout.addWidget(excel_btn)
        file_btn_layout.addWidget(csv_btn)
        file_btn_layout.addStretch()
        file_layout.addLayout(file_btn_layout)

        layout.addWidget(file_group)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # 状态和取消按钮
        status_layout = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

        self.cancel_btn = QPushButton("取消获取")
        self.cancel_btn.setFixedSize(80, 28)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.setStyleSheet("background-color: #F44336; color: white; border: none; border-radius: 4px;")
        self.cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.cancel_btn.clicked.connect(self._cancel_fetch)
        status_layout.addWidget(self.cancel_btn)

        layout.addLayout(status_layout)

        # 日志输出
        log_label = QLabel("操作日志")
        log_label.setFont(QFont("Microsoft YaHei", 12, QFont.Weight.Bold))
        layout.addWidget(log_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(150)
        self.log_text.setStyleSheet(
            "background-color: #ffffff; color: #000000; font-family: Consolas; font-size: 12px;"
        )
        layout.addWidget(self.log_text)

        layout.addStretch()

    def _log(self, message):
        self.log_text.append(message)

    def _auto_fetch(self):
        """自动获取 - 自动检测选中的游戏"""
        from fetchers.cache_reader import CacheReader
        from fetchers.url_parser import URLParser

        selected_id = self.auto_game_combo.currentData()
        if selected_id == "all":
            selected = ["genshin", "starrail", "zzz", "wutheringwaves", "endfield", "arknights"]
        else:
            selected = [selected_id]

        # 检查是否选择了不支持自动获取的游戏
        unsupported_games = []
        supported_games = []
        for game_id in selected:
            if game_id in ["endfield", "arknights"]:
                unsupported_games.append(GAME_NAMES.get(game_id, game_id))
            else:
                supported_games.append(game_id)

        # 如果有不支持的游戏，弹窗提示
        if unsupported_games:
            game_names = "、".join(unsupported_games)
            QMessageBox.warning(
                self, "提示",
                f"{game_names}暂时不支持自动获取，\n请使用方法二登录获取。"
            )
            # 如果只有不支持的游戏，则返回
            if not supported_games:
                return
            # 如果混合了支持和不支持的游戏，只继续获取支持的游戏
            selected = supported_games

        self._set_fetching(True)
        game_label = self.auto_game_combo.currentText()
        self._log(f"开始自动检测: {game_label}...")

        cache = CacheReader()
        detected_games = []

        # 只扫描选中的游戏
        for game_id in selected:
            try:
                url = cache.extract_url(game_id)
                if url:
                    detected_games.append((game_id, url))
            except Exception as e:
                self._log(f"  ✗ 扫描 {GAME_NAMES.get(game_id, game_id)} 失败: {str(e)}")

        if not detected_games:
            self._log("\n未找到任何游戏记录！")
            self._log("请确保：")
            self._log("1. 已打开游戏")
            self._log("2. 进入抽卡/跃迁记录页面")
            self._log("3. 等待记录加载完成")
            self._log("4. 切回本程序重试")
            self._set_fetching(False)
            QMessageBox.information(self, "提示",
                "未找到任何游戏记录。\n\n"
                "请确保：\n"
                "1. 已打开游戏\n"
                "2. 进入抽卡/跃迁记录页面\n"
                "3. 等待记录加载完成\n"
                "4. 切回本程序重试\n\n"
                "如果还是找不到，请尝试手动粘贴URL。")
            return

        self._log(f"\n共检测到 {len(detected_games)} 个游戏，开始获取记录...")

        # 依次获取每个游戏的记录
        self._detected_games = detected_games
        self._current_fetch_index = 0
        self._fetch_next_game()

    def _fetch_next_game(self):
        """获取下一个游戏的记录"""
        if self._current_fetch_index >= len(self._detected_games):
            self._set_fetching(False)
            self._log("\n所有游戏获取完成！")
            self.main_window.refresh_all()
            QMessageBox.information(self, "完成", "所有游戏记录获取完成！")
            return

        game, url = self._detected_games[self._current_fetch_index]
        self._log(f"\n正在获取 {GAME_NAMES.get(game, game)}...")

        # 自动创建或获取账号
        account = self._auto_detect_account(game, url)
        if not account:
            self._log(f"  跳过 {GAME_NAMES.get(game, game)}")
            self._current_fetch_index += 1
            self._fetch_next_game()
            return

        # 切换到当前游戏
        self.main_window._on_game_changed(game)
        self.main_window.set_account(account)

        # 获取最新记录时间，用于增量获取
        latest_time = None
        records = self.db.get_records(account.id)
        if records:
            latest_time = max(r.time for r in records if r.time)
            self._log(f"  已有记录，从 {latest_time} 开始增量获取")

        self.fetch_thread = FetchThread(game, url=url, account_id=account.id, latest_time=latest_time)
        self.fetch_thread.progress.connect(self._on_progress)
        self.fetch_thread.finished.connect(self._on_game_fetch_done)
        self.fetch_thread.error.connect(self._on_game_fetch_error)
        self.fetch_thread.start()

    def _generate_nickname(self, game, uid):
        """生成唯一昵称：游戏称呼+UID后三位，重复则加位数"""
        game_titles = {
            "genshin": "旅行者", "starrail": "开拓者", "zzz": "绳匠",
            "wutheringwaves": "漂泊者", "endfield": "管理员", "arknights": "博士",
        }
        title = game_titles.get(game, "玩家")
        existing = {a.nickname for a in self.db.get_accounts(game)}

        # 从后3位开始，逐步增加位数直到唯一
        for digits in range(3, min(len(uid), 8) + 1):
            nickname = f"{title}{uid[-digits:]}"
            if nickname not in existing:
                return nickname

        # 极端情况：加序号
        for i in range(2, 100):
            nickname = f"{title}{uid[-3:]}({i})"
            if nickname not in existing:
                return nickname

        return f"{title}{uid[-3:]}"

    def _auto_detect_account(self, game, url, detected_uid=None):
        """自动检测并创建账号"""
        from fetchers.url_parser import URLParser
        from fetchers.cache_reader import CacheReader
        from PySide6.QtWidgets import QInputDialog

        parsed = URLParser.parse(url)
        region = parsed.get("region", "cn")

        # 尝试从URL中提取uid
        uid = None
        params = parsed.get("params", {})
        uid = params.get("uid") or params.get("user_id") or params.get("player_id")

        # 使用预先检测到的UID（明日方舟/终末地）
        if not uid and detected_uid:
            uid = detected_uid

        # 如果URL中没有uid，尝试从UidInfo.txt读取
        if not uid:
            cache = CacheReader()
            uid = cache.extract_uid(game, region)
            if uid:
                self._log(f"  从游戏文件读取到UID: {uid}")

        # 尝试获取昵称
        nickname = ""
        cache = CacheReader()
        nickname = cache.extract_nickname(game, region)
        if nickname:
            self._log(f"  检测到昵称: {nickname}")

        # 检查是否已存在账号
        accounts = self.db.get_accounts(game)
        for acc in accounts:
            if uid and acc.uid == uid:
                self._log(f"  使用已有账号: {acc.nickname or acc.uid}")
                return acc

        # 如果没有UID，且是明日方舟/终末地，让用户手动输入
        if not uid and game in ["arknights", "endfield"]:
            if accounts:
                # 询问用户是使用已有账号还是输入新UID
                reply = QMessageBox.question(
                    self, "选择账号",
                    f"检测到已有{GAME_NAMES.get(game, game)}账号：\n"
                    f"  {accounts[0].nickname or accounts[0].uid}\n\n"
                    "是否使用该账号？\n"
                    "（选择\"否\"可以输入新的账号UID）",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply == QMessageBox.StandardButton.Yes:
                    self._log(f"  使用已有账号: {accounts[0].nickname or accounts[0].uid}")
                    return accounts[0]

            # 让用户输入UID
            uid, ok = QInputDialog.getText(
                self, "输入账号UID",
                f"请输入{GAME_NAMES.get(game, game)}的账号UID："
            )
            if not ok or not uid.strip():
                return None
            uid = uid.strip()

        # 如果还是没有UID，复用该游戏的第一个已有账号
        if not uid and accounts:
            self._log(f"  复用已有账号: {accounts[0].nickname or accounts[0].uid}")
            return accounts[0]

        # 创建新账号
        account = Account(
            game=game,
            uid=uid or "",
            nickname=nickname or "",
            server=region,
        )
        account.id = self.db.add_account(account)
        self._log(f"  自动创建账号: {uid or '(待确认)'} ({region})")
        return account

    def _on_game_fetch_done(self, records):
        """单个游戏获取完成"""
        try:
            if not records:
                self._log("  未获取到记录")
            else:
                account = self.main_window.get_current_account()
                if account:
                    # 从fetcher获取检测到的UID
                    detected_uid = getattr(self.fetch_thread, 'detected_uid', '')
                    if detected_uid and detected_uid != account.uid:
                        self._log(f"  检测到UID: {detected_uid}")
                        account.uid = detected_uid

                    # 如果还是没有UID，尝试从记录中提取
                    if not account.uid:
                        from fetchers.mihoyo.api import MihoyoAPI
                        uid = MihoyoAPI.get_uid_from_records(records)
                        if uid:
                            account.uid = uid
                            self._log(f"  从记录中提取UID: {uid}")

                    # 生成默认昵称
                    if not account.nickname and account.uid:
                        account.nickname = self._generate_nickname(account.game, account.uid)

                    self.db.update_account(account)
                    self.main_window.set_account(account)

                    # 转换为GachaRecord对象
                    gacha_records = []
                    for raw in records:
                        if isinstance(raw, dict):
                            record = MihoyoAPI.parse_record(raw, account.game, account.id)
                            gacha_records.append(record)
                        else:
                            gacha_records.append(raw)

                    new_count = self.db.add_records(gacha_records)
                    skipped_count = len(records) - new_count

                    if new_count > 0:
                        self._log(f"  成功导入 {new_count} 条新记录")
                        # 计算保底数
                        self._log("  正在计算保底数...")
                        self.db.calculate_pity_counts(account.id)
                        self._log("  保底数计算完成")
                        # 明日方舟自动更新卡池分类
                        if account.game == "arknights":
                            updated = self.main_window.settings_page._do_update_arknights_pool_types()
                            if updated > 0:
                                self._log(f"  已自动更新 {updated} 条卡池分类")
                    if skipped_count > 0:
                        self._log(f"  跳过 {skipped_count} 条重复记录")
        except Exception as e:
            self._log(f"  ✗ 处理记录时出错: {e}")

        # 继续获取下一个游戏
        self._current_fetch_index += 1
        self._fetch_next_game()

    def _on_game_fetch_error(self, error_msg):
        """单个游戏获取失败"""
        self._log(f"  ✗ 获取失败: {error_msg}")
        if "取消" in error_msg:
            self._set_fetching(False)
            self._log("已取消获取")
            return
        if "authkey" in error_msg.lower() or "expired" in error_msg.lower() or "过期" in error_msg:
            self._log("  提示: authkey已过期，请重新打开游戏进入抽卡记录页面")
        elif "网络" in error_msg or "timeout" in error_msg.lower():
            self._log("  提示: 网络请求失败，请检查网络连接")
        # 跳过当前游戏，继续获取下一个
        self._current_fetch_index += 1
        self._fetch_next_game()

    def _url_fetch(self):
        """URL获取 - 自动检测游戏"""
        url = self.url_input.text().strip()
        if not url:
            QMessageBox.warning(self, "提示", "请输入URL或Token")
            return

        # 自动检测游戏类型
        from fetchers.url_parser import URLParser
        parsed = URLParser.parse(url)
        game = parsed.get("game", "")

        # 终末地/明日方舟特殊处理：如果不是URL，且当前游戏是endfield/arknights，当作账号token
        if not game and not url.startswith("http"):
            current = self.main_window.get_current_game()
            if current in ["endfield", "arknights"]:
                game = current

        if not game:
            game = self.main_window.get_current_game()
            self._log(f"无法自动识别游戏，使用当前游戏: {GAME_NAMES.get(game, game)}")
        else:
            self._log(f"自动识别游戏: {GAME_NAMES.get(game, game)}")

        # 对于明日方舟和终末地，先通过token获取UID
        uid = None
        if game in ["arknights", "endfield"] and not url.startswith("http"):
            uid = self._get_uid_from_token(game, url)
            if uid:
                self._log(f"  从Token检测到UID: {uid}")

        # 自动创建或获取账号
        account = self._auto_detect_account(game, url, uid)
        if not account:
            return

        # 切换到对应游戏
        self.main_window._on_game_changed(game)
        self.main_window.set_account(account)

        self._set_fetching(True)
        self._log(f"开始从URL获取 {GAME_NAMES.get(game, game)} 抽卡记录...")

        # 获取最新记录时间，用于增量获取
        latest_time = None
        records = self.db.get_records(account.id)
        if records:
            latest_time = max(r.time for r in records if r.time)
            self._log(f"已有记录，从 {latest_time} 开始增量获取")

        self.fetch_thread = FetchThread(game, url=url, account_id=account.id, latest_time=latest_time)
        self.fetch_thread.progress.connect(self._on_progress)
        self.fetch_thread.finished.connect(self._on_fetch_done)
        self.fetch_thread.error.connect(self._on_fetch_error)
        self.fetch_thread.start()

    def _on_progress(self, message, progress):
        self.status_label.setText(message)
        if progress > 0:
            self.progress_bar.setValue(int(progress * 100))
        self._log(message)

    def _on_fetch_done(self, records):
        """获取完成"""
        self._set_fetching(False)

        if not records:
            self._log("未获取到任何记录")
            QMessageBox.information(self, "提示", "未获取到任何记录")
            return

        account = self.main_window.get_current_account()
        if account:
            # 从fetcher获取检测到的UID
            detected_uid = getattr(self.fetch_thread, 'detected_uid', '')
            if detected_uid and detected_uid != account.uid:
                self._log(f"检测到UID: {detected_uid}")
                account.uid = detected_uid

            if not account.uid:
                from fetchers.mihoyo.api import MihoyoAPI
                uid = MihoyoAPI.get_uid_from_records(records)
                if uid:
                    account.uid = uid
                    self._log(f"从记录中提取UID: {uid}")

            # 生成默认昵称
            if not account.nickname and account.uid:
                account.nickname = self._generate_nickname(account.game, account.uid)

            self.db.update_account(account)
            self.main_window.set_account(account)

            # 转换为GachaRecord对象
            gacha_records = []
            for raw in records:
                if isinstance(raw, dict):
                    record = MihoyoAPI.parse_record(raw, account.game, account.id)
                    gacha_records.append(record)
                else:
                    gacha_records.append(raw)

            new_count = self.db.add_records(gacha_records)
            skipped_count = len(records) - new_count

            if new_count > 0:
                self._log(f"成功导入 {new_count} 条新记录")
                # 计算保底数
                self._log("正在计算保底数...")
                self.db.calculate_pity_counts(account.id)
                self._log("保底数计算完成")
                # 明日方舟自动更新卡池分类
                if account.game == "arknights":
                    updated = self.main_window.settings_page._do_update_arknights_pool_types()
                    if updated > 0:
                        self._log(f"已自动更新 {updated} 条卡池分类")
            if skipped_count > 0:
                self._log(f"跳过 {skipped_count} 条重复记录")

            QMessageBox.information(
                self, "导入完成",
                f"新记录: {new_count} 条\n重复记录: {skipped_count} 条\n总计获取: {len(records)} 条"
            )
            self.main_window.refresh_all()
        else:
            self._log("错误：未找到账号")

    def _on_fetch_error(self, error_msg):
        self._set_fetching(False)
        if "取消" in error_msg:
            self._log("已取消获取")
            return
        self._log(f"错误：{error_msg}")
        if "authkey" in error_msg.lower() or "expired" in error_msg.lower():
            self._log("提示: authkey已过期，请重新打开游戏进入抽卡记录页面")
            QMessageBox.critical(self, "获取失败", f"{error_msg}\n\nauthkey已过期，请重新打开游戏进入抽卡记录页面，然后切回本程序重试。")
        elif "网络" in error_msg or "timeout" in error_msg.lower():
            self._log("提示: 网络请求失败，请检查网络连接")
            QMessageBox.critical(self, "获取失败", f"{error_msg}\n\n请检查网络连接后重试。")
        else:
            QMessageBox.critical(self, "获取失败", error_msg)

    def _cancel_fetch(self):
        """取消当前获取"""
        if self.fetch_thread and self.fetch_thread.isRunning():
            self.fetch_thread.cancel()
            # 杀掉代理子进程（如果有）
            try:
                fetcher = getattr(self.fetch_thread, '_fetcher_instance', None)
                if fetcher:
                    proc = getattr(fetcher, '_proxy_proc', None)
                    if proc and proc.poll() is None:
                        proc.kill()
            except Exception:
                pass
            self.cancel_btn.setEnabled(False)
            self.cancel_btn.setText("取消中...")
            self._log("正在取消获取...")

    def _get_uid_from_token(self, game: str, token: str) -> str:
        """通过token获取UID（仅明日方舟和终末地）"""
        try:
            import requests as req

            self._log(f"  正在从Token获取UID... (Token长度: {len(token)})")

            # 短 token（< 50字符）是鹰角账号 token，需要交换
            if len(token) < 50:
                self._log(f"  检测到鹰角账号Token，正在交换...")
                # 1. hg_token -> app_token
                grant_resp = req.post(
                    "https://as.hypergryph.com/user/oauth2/v2/grant",
                    json={"type": 1, "appCode": "be36d44aa36bfb5b", "token": token},
                    timeout=15,
                )
                grant_data = grant_resp.json()
                app_token = grant_data.get("data", {}).get("token")
                if not app_token:
                    self._log(f"  ✗ 获取app_token失败: {grant_data.get('msg', '未知错误')}")
                    return None

                # 2. app_token -> 绑定列表 -> UID
                binding_resp = req.get(
                    "https://binding-api-account-prod.hypergryph.com/account/binding/v1/binding_list",
                    params={"token": app_token, "appCode": game},
                    timeout=15,
                )
                binding_data = binding_resp.json()
                apps = binding_data.get("data", {}).get("list", [])

                for app in apps:
                    if app.get("appCode") == game:
                        for binding in app.get("bindingList", []):
                            uid = binding.get("uid", "")
                            if uid:
                                self._log(f"  ✓ 获取到UID: {uid}")
                                return str(uid)
                self._log(f"  ✗ 未找到{game}的绑定角色")
            else:
                self._log(f"  Token是u8_token（长token），无法直接获取UID")
        except Exception as e:
            self._log(f"  ✗ 获取UID失败: {str(e)}")
        return None

    def _set_fetching(self, fetching):
        self.auto_fetch_btn.setEnabled(not fetching)
        self.url_fetch_btn.setEnabled(not fetching)
        self.progress_bar.setVisible(fetching)
        self.cancel_btn.setVisible(fetching)
        self.cancel_btn.setEnabled(fetching)
        self.cancel_btn.setText("取消获取")
        if fetching:
            self.progress_bar.setRange(0, 0)  # 不确定进度
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)

    def _update_login_btn_visibility(self):
        """根据选择的游戏更新登录按钮的显示状态"""
        selected_id = self.auto_game_combo.currentData()
        # 只有选择终末地、明日方舟或全部游戏时才显示登录按钮
        show_login = selected_id in ["all", "endfield", "arknights"]
        self.login_btn.setVisible(show_login)
        # 终末地/明日方舟专用说明仅在对应游戏时显示
        self._endfield_hint.setVisible(selected_id == "endfield")
        self._arknights_hint.setVisible(selected_id == "arknights")
        # 输入框占位文字跟随游戏切换
        if selected_id in ("endfield", "arknights"):
            self.url_input.setPlaceholderText("粘贴鹰角账号Token")
        else:
            self.url_input.setPlaceholderText("粘贴抽卡记录URL")

    def _paste_from_clipboard(self):
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        self.url_input.setText(clipboard.text())

    def _login_fetch(self):
        """登录获取 - 根据当前游戏打开对应登录窗口"""
        game = self.main_window.get_current_game()

        if game == "endfield":
            self._login_endfield()
        elif game == "arknights":
            self._login_arknights()
        else:
            QMessageBox.information(self, "提示", "登录获取仅支持终末地和明日方舟。")

    def _login_endfield(self):
        """终末地登录 - API版"""
        try:
            from ui.widgets.login_dialog_api import LoginApiDialog

            dialog = LoginApiDialog(self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                token = dialog.get_framework_token()
                if token:
                    self.url_input.setText(token)
                    self._log(f"✓ 终末地登录成功，Token: {token[:20]}...")
                    QTimer.singleShot(100, self._url_fetch)
                else:
                    self._log("✗ 未获取到凭证")
                    QMessageBox.warning(self, "提示", "未获取到凭证")
            else:
                self._log("登录已取消")
        except Exception as e:
            self._log(f"✗ 登录出错: {type(e).__name__}: {str(e)}")

    def _login_arknights(self):
        """明日方舟登录 - API版"""
        try:
            from ui.widgets.arknights_login_api import ArknightsLoginApiDialog

            dialog = ArknightsLoginApiDialog(self)
            if dialog.exec() == QDialog.DialogCode.Accepted:
                token = dialog.get_token()
                if token:
                    self.url_input.setText(token)
                    self._log(f"✓ 明日方舟登录成功，Token: {token[:20]}...")
                    QTimer.singleShot(100, self._url_fetch)
                else:
                    self._log("✗ 未获取到 Token")
                    QMessageBox.warning(self, "提示", "未获取到 Token，请重试。")
            else:
                self._log("登录已取消")
        except Exception as e:
            self._log(f"✗ 登录出错: {type(e).__name__}: {str(e)}")

    def _import_file(self, file_type):
        """文件导入"""
        filters = {
            "json": "JSON 文件 (*.json)",
            "excel": "Excel 文件 (*.xlsx *.xls)",
            "csv": "CSV 文件 (*.csv)",
        }
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择文件", "", filters.get(file_type, "")
        )
        if not filepath:
            return

        game = self.main_window.get_current_game()
        account = self.main_window.get_current_account()

        if not account:
            account = self._ensure_account(game)
            if not account:
                return

        try:
            records = self._parse_file(filepath, file_type, game, account.id)
            if records:
                count = self.db.add_records(records)
                self._log(f"从文件导入 {count} 条新记录")
                QMessageBox.information(self, "导入成功", f"成功导入 {count} 条新记录！")
                self.main_window.refresh_all()
            else:
                QMessageBox.warning(self, "提示", "文件中没有找到有效记录")
        except Exception as e:
            self._log(f"导入失败：{str(e)}")
            QMessageBox.critical(self, "导入失败", f"解析文件失败：\n{str(e)}")

    def _parse_file(self, filepath, file_type, game, account_id):
        """解析导入文件"""
        records = []

        if file_type == "json":
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

            # 检测小黑盒格式: {"info": {...}, "data": {"id": {"c": [...], "p": "..."}, ...}}
            if isinstance(data, dict) and "info" in data and "data" in data and isinstance(data["data"], dict):
                records = self._parse_xiaoheihe(data, game, account_id)
            # 检测 UIGF 格式: {"info": {...}, "list": [...]}
            elif isinstance(data, dict) and "info" in data and "list" in data:
                records = self._parse_uigf(data, game, account_id)
            else:
                # 兼容多种格式
                if isinstance(data, dict):
                    if "list" in data:
                        data = data["list"]
                    elif "records" in data:
                        data = data["records"]
                    else:
                        data = data.get("list", data.get("records", data.get("data", [])))

                for item in data:
                    records.append(GachaRecord(
                        account_id=account_id,
                        game=item.get("game", game),
                        pool_type=item.get("pool_type", item.get("gacha_type", "character")),
                        item_name=item.get("item_name", item.get("name", "未知")),
                        item_type=item.get("item_type", item.get("type", "")),
                        rarity=int(item.get("rarity", item.get("rank_type", 3))),
                        is_featured=bool(item.get("is_featured", item.get("is_up", False))),
                        time=item.get("time", ""),
                        pity_count=int(item.get("pity_count", 0)),
                    ))

        elif file_type == "csv":
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    records.append(GachaRecord(
                        account_id=account_id,
                        game=row.get("game", game),
                        pool_type=row.get("pool_type", "character"),
                        item_name=row.get("item_name", row.get("name", "未知")),
                        item_type=row.get("item_type", ""),
                        rarity=int(row.get("rarity", 3)),
                        is_featured=row.get("is_featured", "").lower() in ("true", "1", "是"),
                        time=row.get("time", ""),
                    ))

        elif file_type == "excel":
            try:
                import openpyxl
                wb = openpyxl.load_workbook(filepath, read_only=True)
                ws = wb.active
                headers = [cell.value for cell in next(ws.iter_rows(max_row=1))]
                for row in ws.iter_rows(min_row=2, values_only=True):
                    item = dict(zip(headers, row))
                    records.append(GachaRecord(
                        account_id=account_id,
                        game=str(item.get("game", game)),
                        pool_type=str(item.get("pool_type", "character")),
                        item_name=str(item.get("item_name", item.get("name", "未知"))),
                        item_type=str(item.get("item_type", "")),
                        rarity=int(item.get("rarity", 3)),
                        is_featured=bool(item.get("is_featured", False)),
                        time=str(item.get("time", "")),
                    ))
            except ImportError:
                raise RuntimeError("需要安装 openpyxl 才能导入 Excel 文件")

        return records

    def _parse_xiaoheihe(self, data: dict, game: str, account_id: int) -> list:
        """解析小黑盒导出格式

        格式: {"info": {...}, "data": {"timestamp": {"c": [[name, rarity, is_featured], ...], "p": "卡池名"}, ...}}
        """
        from datetime import datetime
        from core.models import get_max_rarity

        records = []
        uid = str(data.get("info", {}).get("uid", ""))

        # 小黑盒的星级和API一致（0-5），明日方舟需要+1转成1-6
        rarity_offset = 1 if game == "arknights" else 0

        for ts_str, entry in data.get("data", {}).items():
            # 解析时间戳
            try:
                ts = int(ts_str)
                time_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, OSError):
                time_str = ""

            pool_name = entry.get("p", "")
            chars = entry.get("c", [])

            # 根据游戏确定 pool_type
            if game == "arknights":
                pool_type = self._get_arknights_pool_type(pool_name)
            else:
                pool_type = "character"

            for idx, char in enumerate(chars):
                if len(char) < 2:
                    continue
                char_name = char[0]
                rarity = int(char[1]) + rarity_offset
                is_featured = bool(char[2]) if len(char) > 2 else False

                # 生成唯一 item_id: 角色名_时间（与游戏API获取格式一致，避免重复）
                item_id = f"{char_name}_{time_str}"

                records.append(GachaRecord(
                    account_id=account_id,
                    game=game,
                    pool_type=pool_type,
                    pool_name=pool_name,
                    item_id=item_id,
                    item_name=char_name,
                    item_type="CHAR",
                    rarity=rarity,
                    is_featured=is_featured,
                    count=1,
                    time=time_str,
                ))

        return records

    def _parse_uigf(self, data: dict, game: str, account_id: int) -> list:
        """解析 UIGF (Unified Interchangeable GachaLog Format) 标准格式

        格式: {"info": {...}, "list": [{"uid", "gacha_type", "time", "name", "item_type", "rank_type", "id", ...}, ...]}
        """
        from fetchers.mihoyo.api import MihoyoAPI

        # UIGF gacha_type 到 pool_type 的映射
        UIGF_TYPE_MAP = {
            "genshin": {
                "100": "beginner",
                "200": "standard",
                "301": "character",
                "302": "weapon",
                "400": "character",
                "500": "chronicled",
            },
            "starrail": {
                "1": "standard",
                "2": "beginner",
                "11": "character",
                "12": "weapon",
                "13": "collab",
                "14": "collab_weapon",
            },
            "zzz": {
                "1001": "standard",
                "2001": "character",
                "3001": "weapon",
                "4001": "special",
                "5001": "special_weapon",
                "6001": "bangboo",
                # 兼容 API 新短格式
                "1": "standard",
                "2": "character",
                "3": "weapon",
                "4": "special",
                "5": "special_weapon",
                "6": "bangboo",
            },
        }

        type_map = UIGF_TYPE_MAP.get(game, {})
        records = []

        for item in data.get("list", []):
            gacha_type = str(item.get("gacha_type", item.get("uigf_gacha_type", "")))
            pool_type = type_map.get(gacha_type, "character")

            # 添加 _pool_type 供 MihoyoAPI.parse_record 使用
            item["_pool_type"] = pool_type
            record = MihoyoAPI.parse_record(item, game, account_id)
            records.append(record)

        return records

    def _get_arknights_pool_type(self, pool_name: str) -> str:
        """根据明日方舟卡池名返回保底分组"""
        from core.models import ARKNIGHTS_POOL_MECHANIC_MAP, ARKNIGHTS_MECHANIC_TO_GROUP

        # 精确匹配
        mechanic = ARKNIGHTS_POOL_MECHANIC_MAP.get(pool_name, "")
        if mechanic:
            return ARKNIGHTS_MECHANIC_TO_GROUP.get(mechanic, "standard")

        # 关键词匹配
        limited_keywords = ["限定", "联动", "跨年", "归航", "启程", "承诺"]
        kernel_keywords = ["中坚"]
        standard_keywords = ["标准", "常驻", "定向", "甄选"]

        for kw in limited_keywords:
            if kw in pool_name:
                return "limited"
        for kw in kernel_keywords:
            if kw in pool_name:
                return "kernel"
        for kw in standard_keywords:
            if kw in pool_name:
                return "standard"

        # 未识别的限时卡池默认为独立寻访（limited）
        # 因为大多数特定角色卡池都是限定池
        return "limited"

    def _ensure_account(self, game):
        """确保有账号，没有则创建"""
        from PySide6.QtWidgets import QInputDialog
        uid, ok = QInputDialog.getText(self, "创建账号", "请输入游戏UID:")
        if not ok or not uid.strip():
            return None

        nickname, _ = QInputDialog.getText(self, "设置昵称", "请输入昵称（可选）:")

        account = Account(
            game=game,
            uid=uid.strip(),
            nickname=nickname.strip() if nickname else "",
            server="cn",
        )
        account.id = self.db.add_account(account)
        self.main_window.set_account(account)
        return account

    def refresh(self):
        # 同步左侧游戏列表（显示/隐藏 + 顺序）
        visible = getattr(self.main_window, '_visible_games', [])
        order = getattr(self.main_window, '_game_order', [])
        all_games = [
            ("genshin", "原神"), ("starrail", "星穹铁道"), ("zzz", "绝区零"),
            ("wutheringwaves", "鸣潮"), ("endfield", "终末地"), ("arknights", "明日方舟"),
        ]

        # 按左侧顺序筛选可见游戏
        ordered_visible = [g for g in order if g in visible]
        game_map = dict(all_games)

        self.auto_game_combo.blockSignals(True)
        self.auto_game_combo.clear()
        self._auto_game_options = [("all", "全部游戏")]
        self.auto_game_combo.addItem("全部游戏", "all")
        for gid in ordered_visible:
            gname = game_map.get(gid, gid)
            self._auto_game_options.append((gid, gname))
            self.auto_game_combo.addItem(gname, gid)
        self.auto_game_combo.blockSignals(False)

        # 同步当前游戏选择
        current_game = self.main_window.get_current_game()
        for i, (gid, _) in enumerate(self._auto_game_options):
            if gid == current_game:
                self.auto_game_combo.setCurrentIndex(i)
                break

