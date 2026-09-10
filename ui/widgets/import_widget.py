"""数据导入页面"""

import json
import logging
import os
import csv

logger = logging.getLogger(__name__)
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QLineEdit, QTextEdit, QFileDialog, QMessageBox,
    QProgressBar, QGroupBox, QGridLayout, QComboBox, QDialog
)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from PySide6.QtGui import QFont

from core.database import Database
from core.models import Account, GachaRecord, GAME_NAMES, make_item_id
from ui.widgets.style_constants import GROUPBOX_STYLE


class FetchThread(QThread):
    """后台获取线程：拉取 + 入库，支持可中断取消"""
    progress = Signal(str, float)
    finished = Signal(dict)
    error = Signal(str)

    def __init__(self, game, url=None, account_id=None, latest_time=None, account=None):
        super().__init__()
        self.game = game
        self.url = url
        self.account_id = account_id
        self.latest_time = latest_time
        self.account = account
        self._cancelled = False
        self.detected_uid = ""

    def cancel(self):
        self._cancelled = True
        fetcher = getattr(self, "_fetcher_instance", None)
        if fetcher is not None:
            try:
                fetcher.abort()
            except Exception:
                pass

    def is_cancelled(self):
        return self._cancelled

    def run(self):
        try:
            from fetchers import get_fetcher
            from fetchers.mihoyo.api import MihoyoAPI
            from core.database import Database

            fetcher = get_fetcher(self.game)
            self._fetcher_instance = fetcher
            fetcher.set_progress_callback(lambda msg, p: self.progress.emit(msg, p))
            fetcher._cancel_check = self.is_cancelled

            records = fetcher.fetch_records(
                url=self.url, account_id=self.account_id, latest_time=self.latest_time
            )
            self.detected_uid = getattr(fetcher, "_detected_uid", "")
            if self._cancelled:
                self.error.emit("用户已取消获取")
                return

            # 入库放到工作线程，避免主线程卡死
            self.progress.emit("正在写入数据库...", 0.92)
            db = Database()
            account = self.account
            if account is not None:
                if self.detected_uid and self.detected_uid != account.uid:
                    account.uid = self.detected_uid
                if not account.uid:
                    uid = MihoyoAPI.get_uid_from_records(records)
                    if uid:
                        account.uid = uid
                if not account.nickname and account.uid:
                    # 昵称生成放在 UI 层，这里只保证 uid
                    pass
                db.update_account(account)

                gacha_records = []
                for raw in records:
                    if isinstance(raw, dict):
                        gacha_records.append(
                            MihoyoAPI.parse_record(raw, account.game, account.id)
                        )
                    else:
                        gacha_records.append(raw)

                new_count = db.add_records(gacha_records)
                if self._cancelled:
                    self.error.emit("用户已取消获取")
                    return
                if new_count > 0:
                    self.progress.emit("正在计算保底数...", 0.96)
                    db.calculate_pity_counts(account.id)

                self.finished.emit({
                    "total": len(records),
                    "new_count": new_count,
                    "skipped_count": len(records) - new_count,
                    "detected_uid": self.detected_uid,
                    "account_id": account.id,
                    "game": account.game,
                })
            else:
                self.finished.emit({
                    "total": len(records),
                    "new_count": 0,
                    "skipped_count": 0,
                    "detected_uid": self.detected_uid,
                    "account_id": self.account_id,
                    "game": self.game,
                })
        except Exception as e:
            if self._cancelled or "取消" in str(e):
                self.error.emit("用户已取消获取")
            else:
                logger.exception("获取抽卡记录失败")
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
        ]
        for gid, gname in self._auto_game_options:
            self.auto_game_combo.addItem(gname, gid)
        select_layout.addWidget(self.auto_game_combo)

        self.auto_fetch_btn = QPushButton("开始获取")
        self.auto_fetch_btn.setObjectName("primary_button")
        self.auto_fetch_btn.setFixedSize(100, 32)
        self.auto_fetch_btn.clicked.connect(self._auto_fetch)
        select_layout.addWidget(self.auto_fetch_btn)

        self.auto_url_btn = QPushButton("获取URL")
        self.auto_url_btn.setObjectName("primary_button")
        self.auto_url_btn.setFixedSize(100, 32)
        self.auto_url_btn.clicked.connect(self._extract_url)
        select_layout.addWidget(self.auto_url_btn)

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

        # 导出URL按钮（初始隐藏，获取完成后显示）
        self.copy_url_btn = QPushButton("复制URL")
        self.copy_url_btn.setFixedSize(80, 28)
        self.copy_url_btn.setVisible(False)
        self.copy_url_btn.setStyleSheet("background-color: #1976D2; color: white; border: none; border-radius: 4px;")
        self.copy_url_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.copy_url_btn.clicked.connect(self._copy_urls)
        status_layout.addWidget(self.copy_url_btn)

        self.export_url_btn = QPushButton("导出URL")
        self.export_url_btn.setFixedSize(80, 28)
        self.export_url_btn.setVisible(False)
        self.export_url_btn.setStyleSheet("background-color: #1976D2; color: white; border: none; border-radius: 4px;")
        self.export_url_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.export_url_btn.clicked.connect(self._export_urls)
        status_layout.addWidget(self.export_url_btn)

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

    def _extract_url(self):
        """从缓存中提取抽卡URL并显示"""
        game_id = self.auto_game_combo.currentData()
        if game_id == "all":
            QMessageBox.information(self, "提示", "请先选择一个具体的游戏")
            return

        self._log(f"正在提取 {GAME_NAMES.get(game_id, game_id)} 的URL...")
        try:
            # 鸣潮需要专用的日志解密
            if game_id == "wutheringwaves":
                from fetchers.kuro.wutheringwaves import WutheringWavesFetcher
                fetcher = WutheringWavesFetcher()
                url = fetcher._get_url_from_log()
            else:
                from fetchers.cache_reader import CacheReader
                cache = CacheReader()
                url = cache.extract_url(game_id)
        except Exception as e:
            logger.error("提取URL失败: %s", e)
            self._log(f"提取失败: {e}")
            QMessageBox.warning(self, "错误", f"提取URL失败:\n{e}")
            return

        if not url:
            logger.warning("提取URL失败，未找到抽卡记录URL")
            self._log("未找到URL")
            QMessageBox.information(self, "提示",
                "未找到抽卡记录URL。\n\n"
                "请确保：\n"
                "1. 已打开游戏\n"
                "2. 进入抽卡/跃迁记录页面\n"
                "3. 等待记录加载完成\n"
                "4. 切回本程序重试")
            return

        from PySide6.QtWidgets import QApplication
        QApplication.clipboard().setText(url)
        self._log(f"URL已复制到剪贴板 ({len(url)} 字符)")
        QMessageBox.information(self, "完成",
            f"URL已复制到剪贴板！\n\n"
            f"长度: {len(url)} 字符\n\n"
            f"可粘贴到浏览器或其他工具中使用。")

    def _auto_fetch(self):
        """自动获取：URL 提取与拉取都在工作线程，主线程不扫缓存"""
        selected_id = self.auto_game_combo.currentData()
        if selected_id == "all":
            selected = ["genshin", "starrail", "zzz", "wutheringwaves"]
        else:
            selected = [selected_id]

        self._set_fetching(True)
        self._log(f"开始自动检测: {self.auto_game_combo.currentText()}...")
        self._log("（后台提取 URL 并获取，可随时取消）")
        self._detected_urls = []
        self._detected_games = [(gid, None) for gid in selected]
        self._current_fetch_index = 0
        self._auto_mode = True
        self._fetch_next_game()

    def _fetch_next_game(self):
        if self._current_fetch_index >= len(self._detected_games):
            self._set_fetching(False)
            self._auto_mode = False
            self._log("\n所有游戏获取完成！")
            if getattr(self, "_detected_urls", None):
                self._log("\n=== 检测到的URL ===")
                for game_id, url in self._detected_urls:
                    if url:
                        self._log(f"  [{GAME_NAMES.get(game_id, game_id)}] {url}")
                self._log("====================")
            self.main_window.refresh_all()
            QMessageBox.information(self, "完成", "所有游戏记录获取完成！")
            return

        game, url = self._detected_games[self._current_fetch_index]
        self._log(f"\n正在获取 {GAME_NAMES.get(game, game)}...")

        account = self._auto_detect_account(game, url or "")
        if not account:
            self._log(f"  跳过 {GAME_NAMES.get(game, game)}")
            self._current_fetch_index += 1
            self._fetch_next_game()
            return

        if not account.nickname and account.uid:
            account.nickname = self._generate_nickname(account.game, account.uid)
            self.db.update_account(account)

        self.main_window._on_game_changed(game)
        self.main_window.set_account(account)

        latest_time = None
        existing = self.db.get_records(account.id)
        if existing:
            latest_time = max(r.time for r in existing if r.time)
            self._log(f"  已有记录，从 {latest_time} 开始增量获取")

        self.fetch_thread = FetchThread(
            game, url=url, account_id=account.id,
            latest_time=latest_time, account=account,
        )
        self.fetch_thread.progress.connect(self._on_progress)
        self.fetch_thread.finished.connect(self._on_game_fetch_done)
        self.fetch_thread.error.connect(self._on_game_fetch_error)
        self.fetch_thread.start()

    def _generate_nickname(self, game, uid):
        """生成唯一昵称：游戏称呼+UID后三位，重复则加位数"""
        game_titles = {
            "genshin": "旅行者", "starrail": "开拓者", "zzz": "绳匠",
            "wutheringwaves": "漂泊者",
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

        # 使用预先检测到的UID
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

        # 如果没有UID，复用该游戏的第一个已有账号
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

    def _on_game_fetch_done(self, result):
        """单个游戏获取+入库完成"""
        try:
            if not isinstance(result, dict):
                result = {"total": 0, "new_count": 0, "skipped_count": 0}
            if result.get("total", 0) == 0:
                self._log("  未获取到记录")
            else:
                self._log(
                    f"  新记录 {result.get('new_count', 0)} 条，"
                    f"重复 {result.get('skipped_count', 0)} 条"
                )
                if result.get("detected_uid"):
                    self._log(f"  UID: {result['detected_uid']}")
        except Exception as e:
            logger.error("处理记录时出错: %s", e)
            self._log(f"  ✗ 处理记录时出错: {e}")

        self._current_fetch_index += 1
        self._fetch_next_game()

    def _on_game_fetch_error(self, error_msg):
        """单个游戏获取失败"""
        logger.error("获取失败: %s", error_msg)
        self._log(f"  ✗ 获取失败: {error_msg}")
        if "取消" in error_msg:
            self._auto_mode = False
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

        if not game:
            game = self.main_window.get_current_game()
            self._log(f"无法自动识别游戏，使用当前游戏: {GAME_NAMES.get(game, game)}")
        else:
            self._log(f"自动识别游戏: {GAME_NAMES.get(game, game)}")

        # 自动创建或获取账号
        account = self._auto_detect_account(game, url)
        if not account:
            return

        # 切换到对应游戏
        self.main_window._on_game_changed(game)
        self.main_window.set_account(account)

        self._set_fetching(True)
        self._log(f"开始从URL获取 {GAME_NAMES.get(game, game)} 抽卡记录...")

        # 保存URL供导出使用
        self._detected_urls = [(game, url)]

        # 获取最新记录时间，用于增量获取
        latest_time = None
        records = self.db.get_records(account.id)
        if records:
            latest_time = max(r.time for r in records if r.time)
            self._log(f"已有记录，从 {latest_time} 开始增量获取")

        self.fetch_thread = FetchThread(
            game, url=url, account_id=account.id,
            latest_time=latest_time, account=account,
        )
        self.fetch_thread.progress.connect(self._on_progress)
        self.fetch_thread.finished.connect(self._on_fetch_done)
        self.fetch_thread.error.connect(self._on_fetch_error)
        self.fetch_thread.start()

    def _on_fetch_done(self, result):
        """URL 获取完成"""
        self._set_fetching(False)
        if not isinstance(result, dict):
            result = {}
        total = result.get("total", 0)
        if total == 0:
            self._log("未获取到任何记录")
            QMessageBox.information(self, "提示", "未获取到任何记录")
            return

        self._log(
            f"导入完成：新记录 {result.get('new_count', 0)} 条，"
            f"重复 {result.get('skipped_count', 0)} 条"
        )
        if result.get("detected_uid"):
            self._log(f"UID: {result['detected_uid']}")

        account = self.main_window.get_current_account()
        if account and not account.nickname and account.uid:
            account.nickname = self._generate_nickname(account.game, account.uid)
            self.db.update_account(account)

        QMessageBox.information(
            self, "导入完成",
            f"新记录: {result.get('new_count', 0)} 条\n"
            f"重复记录: {result.get('skipped_count', 0)} 条\n"
            f"总计获取: {total} 条"
        )
        self.main_window.refresh_all()

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
        """取消当前获取：置标志并关闭 HTTP Session 打断阻塞请求"""
        self._auto_mode = False
        if self.fetch_thread and self.fetch_thread.isRunning():
            self.fetch_thread.cancel()
            self.cancel_btn.setEnabled(False)
            self.cancel_btn.setText("取消中...")
            self._log("正在取消获取...")
            # 给线程一点时间退出；不阻塞 UI
            QTimer.singleShot(8000, self._on_cancel_timeout)

    def _on_cancel_timeout(self):
        if self.fetch_thread and self.fetch_thread.isRunning():
            self._log("取消超时，线程仍在退出中…")
            self.cancel_btn.setEnabled(True)
            self.cancel_btn.setText("取消获取")

    def _on_progress(self, message, progress):
        self.status_label.setText(message)
        if progress > 0:
            self.progress_bar.setValue(int(progress * 100))
        # 降低日志刷屏，避免 QTextEdit 过多导致卡顿
        if progress <= 0 or progress >= 0.9 or "完成" in message or "失败" in message or "取消" in message:
            self._log(message)

    def _set_fetching(self, fetching):
        self.auto_fetch_btn.setEnabled(not fetching)
        self.url_fetch_btn.setEnabled(not fetching)
        self.progress_bar.setVisible(fetching)
        self.cancel_btn.setVisible(fetching)
        self.cancel_btn.setEnabled(fetching)
        self.cancel_btn.setText("取消获取")
        # 获取完成后显示导出URL按钮
        has_urls = hasattr(self, '_detected_urls') and self._detected_urls
        self.copy_url_btn.setVisible(not fetching and has_urls)
        self.export_url_btn.setVisible(not fetching and has_urls)
        if fetching:
            self.progress_bar.setRange(0, 0)  # 不确定进度
        else:
            self.progress_bar.setRange(0, 100)
            self.progress_bar.setValue(0)

    def _get_urls_text(self) -> str:
        """获取所有检测到的URL文本"""
        if not hasattr(self, '_detected_urls') or not self._detected_urls:
            return ""
        lines = []
        for game_id, url in self._detected_urls:
            lines.append(f"[{GAME_NAMES.get(game_id, game_id)}] {url}")
        return "\n".join(lines)

    def _copy_urls(self):
        """复制所有检测到的URL到剪贴板"""
        text = self._get_urls_text()
        if not text:
            QMessageBox.information(self, "提示", "没有可复制的URL")
            return
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        clipboard.setText(text)
        self._log("✓ URL已复制到剪贴板")
        QMessageBox.information(self, "复制成功", "URL已复制到剪贴板！")

    def _export_urls(self):
        """导出所有检测到的URL到文件"""
        text = self._get_urls_text()
        if not text:
            QMessageBox.information(self, "提示", "没有可导出的URL")
            return
        filepath, _ = QFileDialog.getSaveFileName(
            self, "导出URL", "gacha_urls.txt", "文本文件 (*.txt)"
        )
        if not filepath:
            return
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            self._log(f"✓ URL已导出到: {filepath}")
            QMessageBox.information(self, "导出成功", f"URL已导出到:\n{filepath}")
        except Exception as e:
            logger.error("导出URL失败: %s", e)
            self._log(f"✗ 导出失败: {str(e)}")
            QMessageBox.critical(self, "导出失败", f"导出失败:\n{str(e)}")

    def _paste_from_clipboard(self):
        from PySide6.QtWidgets import QApplication
        clipboard = QApplication.clipboard()
        self.url_input.setText(clipboard.text())

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
                # 导入后计算保底数
                self._log("正在计算保底数...")
                self.db.calculate_pity_counts(account.id)
                self._log("保底数计算完成")
                QMessageBox.information(self, "导入成功", f"成功导入 {count} 条新记录！")
                self.main_window.refresh_all()
            else:
                QMessageBox.warning(self, "提示", "文件中没有找到有效记录")
        except Exception as e:
            logger.exception("导入文件失败")
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

                for idx, item in enumerate(data):
                    g = item.get("game", game)
                    pt = item.get("pool_type", item.get("gacha_type", "character"))
                    t = item.get("time", "")
                    name = item.get("item_name", item.get("name", "未知"))
                    records.append(GachaRecord(
                        account_id=account_id,
                        game=g,
                        pool_type=pt,
                        pool_name=item.get("pool_name", ""),
                        item_id=item.get("item_id") or item.get("id")
                                  or make_item_id(g, pt, t, name, idx),
                        item_name=name,
                        item_type=item.get("item_type", item.get("type", "")),
                        rarity=int(item.get("rarity", item.get("rank_type", 3))),
                        is_featured=bool(item.get("is_featured", item.get("is_up", False))),
                        time=t,
                        pity_count=int(item.get("pity_count", 0)),
                    ))

        elif file_type == "csv":
            with open(filepath, "r", encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                for idx, row in enumerate(reader):
                    g = row.get("game", game)
                    pt = row.get("pool_type", "character")
                    t = row.get("time", "")
                    name = row.get("item_name", row.get("name", "未知"))
                    records.append(GachaRecord(
                        account_id=account_id,
                        game=g,
                        pool_type=pt,
                        item_id=row.get("item_id") or make_item_id(g, pt, t, name, idx),
                        item_name=name,
                        item_type=row.get("item_type", ""),
                        rarity=int(row.get("rarity", 3)),
                        is_featured=row.get("is_featured", "").lower() in ("true", "1", "是"),
                        time=t,
                    ))

        elif file_type == "excel":
            try:
                import openpyxl
                wb = openpyxl.load_workbook(filepath, read_only=True)
                ws = wb.active
                headers = [cell.value for cell in next(ws.iter_rows(max_row=1))]
                for idx, row in enumerate(ws.iter_rows(min_row=2, values_only=True)):
                    item = dict(zip(headers, row))
                    g = str(item.get("game", game))
                    pt = str(item.get("pool_type", "character"))
                    t = str(item.get("time", ""))
                    name = str(item.get("item_name", item.get("name", "未知")))
                    records.append(GachaRecord(
                        account_id=account_id,
                        game=g,
                        pool_type=pt,
                        item_id=str(item.get("item_id") or make_item_id(g, pt, t, name, idx)),
                        item_name=name,
                        item_type=str(item.get("item_type", "")),
                        rarity=int(item.get("rarity", 3)),
                        is_featured=bool(item.get("is_featured", False)),
                        time=t,
                    ))
            except ImportError:
                raise RuntimeError("需要安装 openpyxl 才能导入 Excel 文件")

        return records

    def _parse_xiaoheihe(self, data: dict, game: str, account_id: int) -> list:
        """解析小黑盒导出格式

        格式: {"info": {...}, "data": {"timestamp": {"c": [[name, rarity, is_featured], ...], "p": "卡池名"}, ...}}
        """
        from datetime import datetime
        from core.models import get_pool_names

        pool_name_map = {
            display: pool_type
            for pool_type, display in get_pool_names(game)
        }

        records = []
        seq_counter = {}

        for ts_str, entry in data.get("data", {}).items():
            try:
                ts = int(ts_str)
                time_str = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, OSError):
                time_str = ""

            pool_name = entry.get("p", "")
            chars = entry.get("c", [])
            pool_type = pool_name_map.get(pool_name, "character")

            for char in chars:
                if len(char) < 2:
                    continue
                char_name = char[0]
                rarity = int(char[1])
                is_featured = bool(char[2]) if len(char) > 2 else False

                key = f"{pool_type}|{time_str}"
                seq = seq_counter.get(key, 0)
                seq_counter[key] = seq + 1
                item_id = make_item_id(game, pool_type, time_str, char_name, seq, pool_name)

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
                "21": "collab",
                "22": "collab_weapon",
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

        # UIGF 文件通常是最新在前，反转为从旧到新，
        # 保证导入后数据库 id 顺序与时间顺序一致
        items = list(reversed(data.get("list", [])))

        for item in items:
            gacha_type = str(item.get("gacha_type", item.get("uigf_gacha_type", "")))
            pool_type = type_map.get(gacha_type, "character")

            # 添加 _pool_type 供 MihoyoAPI.parse_record 使用
            item["_pool_type"] = pool_type
            record = MihoyoAPI.parse_record(item, game, account_id)
            records.append(record)

        return records

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
            ("wutheringwaves", "鸣潮"),
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

