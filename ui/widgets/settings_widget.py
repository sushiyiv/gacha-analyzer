"""设置页面"""

import os
import json
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QPushButton, QLineEdit, QFileDialog, QMessageBox,
    QGroupBox, QFormLayout, QComboBox, QScrollArea,
    QTableWidget, QTableWidgetItem, QHeaderView, QInputDialog
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from core.database import Database
from core.config import Config
from core.models import Account, GAME_NAMES
from ui.widgets.style_constants import GROUPBOX_STYLE


class SettingsWidget(QWidget):
    """设置页面"""

    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        self.db = Database()
        self.config = Config()
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll_widget = QWidget()
        main_layout = QVBoxLayout(scroll_widget)

        title = QLabel("设置")
        title.setFont(QFont("Microsoft YaHei", 18, QFont.Weight.Bold))
        main_layout.addWidget(title)

        # ===== 账号管理 =====
        account_group = QGroupBox("账号管理")
        account_group.setStyleSheet(GROUPBOX_STYLE)
        account_layout = QVBoxLayout(account_group)

        self.account_table = QTableWidget()
        self.account_table.setColumnCount(4)
        self.account_table.setHorizontalHeaderLabels(["游戏", "UID", "昵称", "操作"])
        self.account_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.account_table.verticalHeader().setVisible(False)
        self.account_table.verticalHeader().setDefaultSectionSize(40)
        self.account_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.account_table.setMinimumHeight(300)
        account_layout.addWidget(self.account_table)

        account_btn_layout = QHBoxLayout()
        add_account_btn = QPushButton("添加账号")
        add_account_btn.clicked.connect(self._add_account)
        account_btn_layout.addWidget(add_account_btn)
        refresh_btn = QPushButton("刷新列表")
        refresh_btn.setStyleSheet("background-color: #666;")
        refresh_btn.clicked.connect(self._refresh_accounts)
        account_btn_layout.addWidget(refresh_btn)
        account_btn_layout.addStretch()
        account_layout.addLayout(account_btn_layout)

        main_layout.addWidget(account_group)

        # ===== 数据管理 =====
        data_group = QGroupBox("数据管理")
        data_group.setStyleSheet(GROUPBOX_STYLE)
        data_layout = QVBoxLayout(data_group)

        btn_row1 = QHBoxLayout()
        backup_btn = QPushButton("备份数据库")
        backup_btn.clicked.connect(self._backup)
        btn_row1.addWidget(backup_btn)

        restore_btn = QPushButton("恢复备份")
        restore_btn.clicked.connect(self._restore)
        btn_row1.addWidget(restore_btn)

        clear_btn = QPushButton("清空当前账号数据")
        clear_btn.setStyleSheet("background-color: #d32f2f;")
        clear_btn.clicked.connect(self._clear_data)
        btn_row1.addWidget(clear_btn)
        btn_row1.addStretch()
        data_layout.addLayout(btn_row1)

        btn_row2 = QHBoxLayout()
        export_json_btn = QPushButton("导出 JSON")
        export_json_btn.clicked.connect(lambda: self._export("json"))
        btn_row2.addWidget(export_json_btn)

        export_excel_btn = QPushButton("导出 Excel")
        export_excel_btn.clicked.connect(lambda: self._export("excel"))
        btn_row2.addWidget(export_excel_btn)

        export_csv_btn = QPushButton("导出 CSV")
        export_csv_btn.clicked.connect(lambda: self._export("csv"))
        btn_row2.addWidget(export_csv_btn)

        recalc_btn = QPushButton("重新计算保底数")
        recalc_btn.setStyleSheet("background-color: #666;")
        recalc_btn.clicked.connect(self._recalculate_pity)
        btn_row2.addWidget(recalc_btn)

        update_pool_btn = QPushButton("更新卡池分类")
        update_pool_btn.setStyleSheet("background-color: #666;")
        update_pool_btn.setToolTip("更新明日方舟卡池分类（修复联动卡池被错误分类的问题）")
        update_pool_btn.clicked.connect(self._update_arknights_pool_types)
        btn_row2.addWidget(update_pool_btn)

        btn_row2.addStretch()
        data_layout.addLayout(btn_row2)

        main_layout.addWidget(data_group)

        # ===== 缓存路径配置 =====
        path_group = QGroupBox("缓存路径配置")
        path_group.setStyleSheet(GROUPBOX_STYLE)
        path_layout = QFormLayout(path_group)

        self.path_inputs = {}
        # 不使用缓存路径的游戏（使用日志文件获取 token）
        no_cache_games = ["endfield", "arknights"]
        for game_id, name in GAME_NAMES.items():
            if game_id in no_cache_games:
                # 终末地和明日方舟显示提示信息
                hint_label = QLabel("该游戏使用登录方式获取，无需配置缓存路径")
                hint_label.setStyleSheet("color: #888; font-style: italic;")
                path_layout.addRow(f"{name}:", hint_label)
            else:
                path_input = QLineEdit()
                path_input.setPlaceholderText(f"默认路径（留空使用默认）")
                path_input.setMinimumWidth(400)
                current = self.config.get(f"cache_paths.{game_id}.cn", "")
                path_input.setText(current)
                self.path_inputs[game_id] = path_input
                path_layout.addRow(f"{name}:", path_input)

        save_path_btn = QPushButton("保存路径配置")
        save_path_btn.setFixedSize(140, 32)
        save_path_btn.clicked.connect(self._save_paths)
        path_layout.addRow("", save_path_btn)

        main_layout.addWidget(path_group)

        # ===== 关于 =====
        about_group = QGroupBox("关于")
        about_group.setStyleSheet(GROUPBOX_STYLE)
        about_layout = QVBoxLayout(about_group)
        about_layout.addWidget(QLabel("穷观阵 v1.1.0"))
        about_layout.addWidget(QLabel("支持游戏: 原神、星穹铁道、绝区零、鸣潮、终末地、明日方舟"))
        about_layout.addWidget(QLabel("数据完全离线存储，不会上传到任何服务器"))
        main_layout.addWidget(about_group)

        main_layout.addStretch()
        scroll.setWidget(scroll_widget)
        layout.addWidget(scroll)

    def refresh(self):
        self._refresh_accounts()

    def _refresh_accounts(self):
        accounts = self.db.get_accounts()
        self.account_table.setRowCount(len(accounts))
        for i, acc in enumerate(accounts):
            self.account_table.setItem(i, 0, QTableWidgetItem(GAME_NAMES.get(acc.game, acc.game)))
            self.account_table.setItem(i, 1, QTableWidgetItem(acc.uid))
            self.account_table.setItem(i, 2, QTableWidgetItem(acc.nickname))

            del_btn = QPushButton("删除")
            del_btn.setFixedSize(60, 28)
            del_btn.setStyleSheet("background-color: #d32f2f; font-size: 12px;")
            del_btn.clicked.connect(lambda checked, aid=acc.id: self._delete_account(aid))
            self.account_table.setCellWidget(i, 3, del_btn)

    def _add_account(self):
        game = self.main_window.get_current_game()
        uid, ok = QInputDialog.getText(self, "添加账号", "请输入游戏UID:")
        if not ok or not uid.strip():
            return

        nickname, _ = QInputDialog.getText(self, "设置昵称", "请输入昵称（可选）:")

        account = Account(
            game=game, uid=uid.strip(),
            nickname=nickname.strip() if nickname else "",
            server="cn",
        )
        self.db.add_account(account)
        self._refresh_accounts()
        self.main_window.refresh_all()
        QMessageBox.information(self, "成功", f"已添加账号: {uid}")

    def _delete_account(self, account_id):
        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除此账号及其所有抽卡记录吗？此操作不可恢复。",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.delete_account(account_id)
            self._refresh_accounts()
            self.main_window.refresh_all()

    def _backup(self):
        try:
            path = self.db.backup()
            QMessageBox.information(self, "备份成功", f"数据库已备份到:\n{path}")
        except Exception as e:
            QMessageBox.critical(self, "备份失败", str(e))

    def _restore(self):
        filepath, _ = QFileDialog.getOpenFileName(
            self, "选择备份文件", self.config.backup_dir,
            "数据库文件 (*.db)"
        )
        if not filepath:
            return

        reply = QMessageBox.question(
            self, "确认恢复",
            "恢复备份将覆盖当前所有数据，确定继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            try:
                self.db.restore(filepath)
                QMessageBox.information(self, "恢复成功", "数据已恢复")
                self.main_window.refresh_all()
            except Exception as e:
                QMessageBox.critical(self, "恢复失败", str(e))

    def _clear_data(self):
        account = self.main_window.get_current_account()
        if not account:
            QMessageBox.warning(self, "提示", "请先选择账号")
            return

        reply = QMessageBox.question(
            self, "确认清空",
            f"确定要清空账号 {account.uid} 的所有抽卡记录吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.db.clear_records(account.id)
            QMessageBox.information(self, "完成", "数据已清空")
            self.main_window.refresh_all()

    def _export(self, fmt):
        account = self.main_window.get_current_account()
        if not account:
            QMessageBox.warning(self, "提示", "请先选择账号")
            return

        records = self.db.get_records(account.id)
        if not records:
            QMessageBox.warning(self, "提示", "没有可导出的数据")
            return

        if fmt == "json":
            filepath, _ = QFileDialog.getSaveFileName(
                self, "导出JSON", self.config.export_dir, "JSON (*.json)"
            )
            if filepath:
                data = self.db.export_json(account.id)
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(data)
                QMessageBox.information(self, "导出成功", f"已导出到: {filepath}")

        elif fmt == "csv":
            filepath, _ = QFileDialog.getSaveFileName(
                self, "导出CSV", self.config.export_dir, "CSV (*.csv)"
            )
            if filepath:
                import csv
                with open(filepath, "w", encoding="utf-8-sig", newline="") as f:
                    writer = csv.writer(f)
                    writer.writerow(["游戏", "卡池类型", "卡池名称", "名称", "类型", "星级", "UP", "时间", "保底"])
                    for r in records:
                        writer.writerow([
                            r.game, r.pool_type, r.pool_name, r.item_name, r.item_type,
                            r.rarity, "是" if r.is_featured else "否", r.time, r.pity_count
                        ])
                QMessageBox.information(self, "导出成功", f"已导出到: {filepath}")

        elif fmt == "excel":
            filepath, _ = QFileDialog.getSaveFileName(
                self, "导出Excel", self.config.export_dir, "Excel (*.xlsx)"
            )
            if filepath:
                try:
                    import openpyxl
                    wb = openpyxl.Workbook()
                    ws = wb.active
                    ws.title = "抽卡记录"
                    ws.append(["游戏", "卡池类型", "卡池名称", "名称", "类型", "星级", "UP", "时间", "保底"])
                    for r in records:
                        ws.append([
                            r.game, r.pool_type, r.pool_name, r.item_name, r.item_type,
                            r.rarity, "是" if r.is_featured else "否", r.time, r.pity_count
                        ])
                    wb.save(filepath)
                    QMessageBox.information(self, "导出成功", f"已导出到: {filepath}")
                except ImportError:
                    QMessageBox.warning(self, "提示", "需要安装 openpyxl")

    def _save_paths(self):
        for game_id, input_widget in self.path_inputs.items():
            path = input_widget.text().strip()
            if path:
                self.config.set(f"cache_paths.{game_id}.cn", path)
        self.config.save()
        QMessageBox.information(self, "保存成功", "路径配置已保存")

    def _recalculate_pity(self):
        """重新计算所有账号的保底数"""
        accounts = self.db.get_accounts()
        if not accounts:
            QMessageBox.information(self, "提示", "没有账号需要处理")
            return

        reply = QMessageBox.question(
            self, "确认重新计算",
            f"确定要重新计算 {len(accounts)} 个账号的保底数吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        for account in accounts:
            self.db.calculate_pity_counts(account.id)

        QMessageBox.information(self, "完成", f"已重新计算 {len(accounts)} 个账号的保底数")
        self.main_window.refresh_all()

    def _update_arknights_pool_types(self):
        """更新明日方舟卡池分类（修复联动卡池被错误分类的问题）"""
        import ast

        reply = QMessageBox.question(
            self, "确认更新",
            "这将根据 poolId 更新明日方舟的卡池分类。\n"
            "主要修复联动卡池（如幽境狩人）被错误分类为标准寻访的问题。\n\n"
            "确定继续吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )
        if reply != QMessageBox.StandardButton.Yes:
            return

        updated = self._do_update_arknights_pool_types()

        QMessageBox.information(self, "完成", f"已更新 {updated} 条记录的卡池分类")
        self.main_window.refresh_all()

    def _do_update_arknights_pool_types(self):
        """执行更新明日方舟卡池分类"""
        import ast

        conn = self.db._ensure_conn()
        rows = conn.execute(
            "SELECT id, pool_name, raw_data FROM gacha_records WHERE game='arknights'"
        ).fetchall()

        updated = 0
        for row in rows:
            record_id = row["id"]
            pool_name = row["pool_name"]
            raw_data = row["raw_data"]

            if not raw_data:
                continue

            try:
                raw = ast.literal_eval(raw_data)
                pool_id = raw.get("poolId", "")
            except Exception:
                continue

            # 根据 poolId 前缀判断卡池类型
            new_pool_type = None
            if pool_id:
                pool_id_upper = pool_id.upper()
                if pool_id_upper.startswith("LIMITED_"):
                    new_pool_type = "limited"
                elif pool_id_upper.startswith("LINKAGE_"):
                    new_pool_type = "limited"
                elif pool_id_upper.startswith("CLASSIC_"):
                    new_pool_type = "kernel"
                else:
                    new_pool_type = "standard"

            if new_pool_type:
                conn.execute(
                    "UPDATE gacha_records SET pool_type=? WHERE id=?",
                    (new_pool_type, record_id)
                )
                updated += 1

        conn.commit()

        # 重新计算保底数
        for account in self.db.get_accounts("arknights"):
            self.db.calculate_pity_counts(account.id)

        return updated
