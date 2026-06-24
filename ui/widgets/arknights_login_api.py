"""明日方舟登录窗口 - API直接登录（无需加载网页）"""

import requests
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QMessageBox, QComboBox
)
from PySide6.QtCore import Qt, QThread, Signal
from ui.widgets.styled_widgets import StyledCheckBox


class _LoginWorker(QThread):
    """后台线程执行登录 API 请求"""
    success = Signal(str)   # 登录成功，传递 token
    error = Signal(str)     # 登录失败，传递错误信息

    def __init__(self, account, password):
        super().__init__()
        self._account = account
        self._password = password

    def run(self):
        try:
            url = "https://as.hypergryph.com/user/auth/v1/token_by_phone_password"
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            data = {"phone": self._account, "password": self._password}
            resp = requests.post(url, json=data, headers=headers, timeout=15)
            result = resp.json()
            if result.get("status") == 0:
                token = result.get("data", {}).get("token", "")
                self.success.emit(token)
            else:
                msg = result.get("msg", "未知错误")
                self.error.emit(msg)
        except Exception as e:
            self.error.emit(str(e))


class ArknightsLoginApiDialog(QDialog):
    """明日方舟登录对话框 - API版"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("明日方舟 - 登录鹰角账号")
        self.setMinimumSize(420, 320)
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowContextHelpButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        self._token = None
        self._closing = False

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # 标题
        title = QLabel("登录鹰角账号")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # 账号选择/输入
        account_layout = QHBoxLayout()
        account_layout.addWidget(QLabel("账号:"))
        self.account_combo = QComboBox()
        self.account_combo.setEditable(True)
        self.account_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.account_combo.setMinimumWidth(250)
        self.account_combo.currentTextChanged.connect(self._on_account_selected)
        # 禁用自动补全，避免输入一个数字就匹配到已保存账号
        self.account_combo.setCompleter(None)
        account_layout.addWidget(self.account_combo)
        layout.addLayout(account_layout)

        # 密码输入
        password_layout = QHBoxLayout()
        password_layout.addWidget(QLabel("密码:"))
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("请输入密码")
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMinimumWidth(250)
        self.password_input.returnPressed.connect(self._on_login)
        password_layout.addWidget(self.password_input)
        layout.addLayout(password_layout)

        # 记住密码
        self.remember_cb = StyledCheckBox("记住密码")
        layout.addWidget(self.remember_cb)

        # 状态提示
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666; font-size: 12px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        self.login_btn = QPushButton("登录")
        self.login_btn.setFixedWidth(80)
        self.login_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8; color: white;
                font-weight: bold; border-radius: 4px;
                padding: 6px;
            }
            QPushButton:hover { background-color: #1557b0; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        self.login_btn.clicked.connect(self._on_login)
        btn_layout.addWidget(self.login_btn)

        layout.addLayout(btn_layout)

        # 加载保存的账号列表
        self._load_saved_accounts()

    def closeEvent(self, event):
        """点击右上角 × 关闭对话框"""
        self._closing = True
        # 停止后台线程
        if hasattr(self, '_worker') and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait()
        self.reject()
        event.accept()

    def _load_saved_accounts(self):
        """加载保存的账号列表（共享鹰角账号）"""
        from core.config import Config
        config = Config()
        # 共享鹰角账号列表（明日方舟和终末地通用）
        saved_accounts = config.get("hypergryph_saved_accounts", {})
        # 兼容旧配置：合并 arknights_saved_accounts
        old_arknights = config.get("arknights_saved_accounts", {})
        if old_arknights:
            saved_accounts.update(old_arknights)

        # 屏蔽信号，避免 addItem 期间反复触发 _on_account_selected
        self.account_combo.blockSignals(True)
        self.account_combo.clear()
        self.account_combo.addItem("添加账号")

        for account in saved_accounts.keys():
            self.account_combo.addItem(account)

        self.account_combo.blockSignals(False)

        if saved_accounts:
            self.account_combo.setCurrentIndex(1)
            self.remember_cb.setChecked(True)

    def _on_account_selected(self, account):
        """账号选择/输入变化"""
        if not account or account == "添加账号":
            self.password_input.clear()
            return

        import base64
        from core.config import Config
        config = Config()
        saved_accounts = config.get("hypergryph_saved_accounts", {})
        # 兼容旧配置
        old_arknights = config.get("arknights_saved_accounts", {})
        if old_arknights:
            saved_accounts.update(old_arknights)

        if account in saved_accounts:
            try:
                # 解码 base64 编码的密码
                encoded_password = saved_accounts[account]
                password = base64.b64decode(encoded_password.encode('utf-8')).decode('utf-8')
                self.password_input.setText(password)
                self.remember_cb.setChecked(True)
            except Exception:
                self.password_input.clear()

    def _save_account(self):
        """保存账号密码（密码使用base64编码）"""
        import base64
        from core.config import Config
        config = Config()

        account = self.account_combo.currentText().strip()
        password = self.password_input.text()

        if not account:
            return

        # 共享鹰角账号列表（明日方舟和终末地通用）
        saved_accounts = config.get("hypergryph_saved_accounts", {})

        if self.remember_cb.isChecked():
            # 使用 base64 编码密码（简单混淆，不是真正加密）
            encoded_password = base64.b64encode(password.encode('utf-8')).decode('utf-8')
            saved_accounts[account] = encoded_password
        else:
            # 如果取消记住，移除该账号
            if account in saved_accounts:
                del saved_accounts[account]

        config.set("hypergryph_saved_accounts", saved_accounts)
        config.save()

    def _on_login(self):
        """登录按钮点击"""
        account = self.account_combo.currentText().strip()
        password = self.password_input.text().strip()

        if not account:
            self.status_label.setText("请输入账号")
            self.account_combo.setFocus()
            return

        if not password:
            self.status_label.setText("请输入密码")
            self.password_input.setFocus()
            return

        self.login_btn.setEnabled(False)
        self.login_btn.setText("登录中...")
        self.status_label.setText("正在登录...")

        # 在后台线程执行网络请求，避免阻塞 UI
        self._worker = _LoginWorker(account, password)
        self._worker.success.connect(self._on_login_success)
        self._worker.error.connect(self._on_login_error)
        self._worker.start()

    def _on_login_success(self, token):
        """登录成功回调"""
        self._token = token
        self._save_account()
        self.status_label.setText("✓ 登录成功！")
        self.status_label.setStyleSheet("color: #4CAF50; font-size: 12px; font-weight: bold;")
        self.login_btn.setEnabled(True)
        self.login_btn.setText("登录")
        from PySide6.QtCore import QTimer
        QTimer.singleShot(500, self.accept)

    def _on_login_error(self, msg):
        """登录失败回调"""
        self.status_label.setText(f"登录出错: {msg}")
        self.status_label.setStyleSheet("color: #F44336; font-size: 12px;")
        self.login_btn.setEnabled(True)
        self.login_btn.setText("登录")

    def get_token(self) -> str:
        return self._token

    def get_error(self) -> str:
        return ""
