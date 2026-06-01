"""明日方舟登录窗口 - 轻量版（使用系统浏览器）"""

import webbrowser
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit
)
from PySide6.QtCore import Qt, QTimer


class ArknightsLoginLightDialog(QDialog):
    """明日方舟登录对话框 - 轻量版"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("明日方舟 - 登录获取Token")
        self.setMinimumSize(450, 300)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._token = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # 标题
        title = QLabel("获取鹰角账号Token")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # 步骤说明
        steps = QLabel(
            "操作步骤：\n\n"
            "1. 点击下方按钮打开鹰角官网\n"
            "2. 在网页中登录您的鹰角账号\n"
            "3. 登录成功后，按 F12 打开开发者工具\n"
            "4. 在 Console 中输入以下代码并回车：\n"
            "   document.cookie.match(/token=([^;]+)/)?.[1]\n"
            "5. 复制输出的token，粘贴到下方输入框"
        )
        steps.setStyleSheet("color: #333; font-size: 12px; line-height: 1.5;")
        steps.setWordWrap(True)
        layout.addWidget(steps)

        # 打开浏览器按钮
        open_btn = QPushButton("打开鹰角官网登录")
        open_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8; color: white;
                padding: 10px; font-size: 14px; font-weight: bold;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #1557b0; }
        """)
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        open_btn.clicked.connect(self._open_browser)
        layout.addWidget(open_btn)

        # Token 输入框
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Token:"))
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("粘贴获取到的token...")
        self.token_input.setMinimumWidth(300)
        input_layout.addWidget(self.token_input)
        layout.addLayout(input_layout)

        # 按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("确定")
        ok_btn.setFixedWidth(80)
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50; color: white;
                font-weight: bold; border-radius: 4px;
            }
            QPushButton:hover { background-color: #388E3C; }
        """)
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

        # 提示
        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.hint_label)

    def _open_browser(self):
        """打开系统浏览器"""
        url = "https://user.hypergryph.com/"
        webbrowser.open(url)
        self.hint_label.setText("已在浏览器中打开，请登录后复制token")

    def _on_ok(self):
        """确定按钮点击"""
        token = self.token_input.text().strip()
        if not token:
            self.hint_label.setText("请输入token")
            return

        if len(token) < 20:
            self.hint_label.setText("token长度不正确，请重新获取")
            return

        self._token = token
        self.accept()

    def get_token(self) -> str:
        return self._token

    def get_error(self) -> str:
        return ""
