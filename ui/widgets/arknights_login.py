"""明日方舟登录窗口 - 通过官网登录获取 Token"""

import re
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar
from PySide6.QtCore import Qt, QUrl, QTimer
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile


class ArknightsLoginDialog(QDialog):
    """明日方舟登录对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("明日方舟 - 登录鹰角账号")
        self.setMinimumSize(500, 650)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)

        self._token = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 提示
        hint = QLabel(
            "  操作步骤：\n"
            "  1. 在下方登录鹰角账号\n"
            "  2. 登录成功后，点击「获取Token」按钮"
        )
        hint.setStyleSheet("background: #e8f0fe; color: #1a56b0; padding: 8px; font-size: 12px;")
        hint.setFixedHeight(50)
        layout.addWidget(hint)

        # WebEngine
        self.web_view = QWebEngineView()
        self.profile = QWebEngineProfile("ArknightsLogin", self.web_view)
        self.web_page = QWebEnginePage(self.profile, self.web_view)
        self.web_view.setPage(self.web_page)

        self.web_page.loadFinished.connect(self._on_load_finished)
        self.web_view.setUrl(QUrl("https://user.hypergryph.com/"))

        layout.addWidget(self.web_view)

        # 底部
        bottom = QHBoxLayout()
        bottom.setContentsMargins(8, 4, 8, 4)

        self.status = QLabel("请登录鹰角账号...")
        self.status.setStyleSheet("color: #666; font-size: 11px;")
        bottom.addWidget(self.status)
        bottom.addStretch()

        get_btn = QPushButton("获取Token")
        get_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8; color: white;
                padding: 8px 20px; font-weight: bold; border-radius: 4px;
            }
            QPushButton:hover { background-color: #1557b0; }
        """)
        get_btn.clicked.connect(self._get_token)
        bottom.addWidget(get_btn)

        layout.addLayout(bottom)

        # 进度条
        self.progress = QProgressBar()
        self.progress.setFixedHeight(3)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet("QProgressBar { border: none; } QProgressBar::chunk { background: #1a73e8; }")
        layout.addWidget(self.progress)

        self.web_view.loadStarted.connect(lambda: self.progress.setValue(30))
        self.web_view.loadFinished.connect(lambda ok: self.progress.setValue(100))

    def _on_load_finished(self, ok):
        """页面加载完成"""
        if ok:
            # 注入拦截脚本
            self.web_page.runJavaScript("""
            (function() {
                if (window._tokenInterceptor) return;
                window._tokenInterceptor = true;
                window._capturedTokens = [];

                function captureToken(token) {
                    if (token && typeof token === 'string' && token.length > 30) {
                        window._capturedTokens.push(token);
                    }
                }

                // 拦截 XHR
                var XHR = XMLHttpRequest.prototype;
                var origOpen = XHR.open;
                var origSend = XHR.send;

                XHR.open = function(method, url) {
                    this._url = url;
                    return origOpen.apply(this, arguments);
                };

                XHR.send = function(body) {
                    var xhr = this;
                    this.addEventListener('load', function() {
                        try {
                            if (xhr._url && xhr.responseText) {
                                var data = JSON.parse(xhr.responseText);
                                if (data.data && data.data.token) captureToken(data.data.token);
                                if (data.token) captureToken(data.token);
                            }
                        } catch(e) {}
                    });
                    return origSend.apply(this, arguments);
                };

                // 拦截 fetch
                var origFetch = window.fetch;
                window.fetch = function() {
                    var url = typeof arguments[0] === 'string' ? arguments[0] : '';
                    return origFetch.apply(this, arguments).then(function(response) {
                        var ct = response.headers.get('content-type') || '';
                        if (ct.includes('json')) {
                            response.clone().text().then(function(text) {
                                try {
                                    var data = JSON.parse(text);
                                    if (data.data && data.data.token) captureToken(data.data.token);
                                    if (data.token) captureToken(data.token);
                                } catch(e) {}
                            });
                        }
                        return response;
                    });
                };
            })();
            """)

    def _get_token(self):
        """获取 Token"""
        self.status.setText("正在获取 Token...")
        self.progress.setValue(50)

        # 尝试从 account info API 获取 hg_token
        # 先检查当前页面是否已登录
        self.web_page.runJavaScript("""
        (function() {
            // 尝试 fetch API
            return fetch('https://web-api.hypergryph.com/account/info/hg', {
                credentials: 'include',
                mode: 'cors'
            })
            .then(function(resp) { return resp.json(); })
            .then(function(data) {
                if (data.code === 0 && data.data && data.data.content) {
                    return data.data.content;
                }
                return '';
            })
            .catch(function() { return ''; });
        })()
        """, lambda result: self._on_account_token(result if isinstance(result, str) else ''))

    def _on_account_token(self, token):
        """从 account info API 获取到的 token"""
        if token and len(token) > 10:
            self._token = token
            self.status.setText(f"已获取账号 Token: {token[:20]}...")
            QTimer.singleShot(500, self.accept)
            return

        # fetch 失败，尝试用注入的 XHR 拦截器获取
        self.status.setText("正在尝试其他方式获取...")
        self.web_page.runJavaScript("""
        (function() {
            // 尝试直接 XHR 请求
            try {
                var xhr = new XMLHttpRequest();
                xhr.open('GET', 'https://web-api.hypergryph.com/account/info/hg', false);
                xhr.withCredentials = true;
                xhr.send();
                if (xhr.status === 200) {
                    var data = JSON.parse(xhr.responseText);
                    if (data.code === 0 && data.data && data.data.content) {
                        return data.data.content;
                    }
                }
            } catch(e) {}
            return '';
        })()
        """, lambda result: self._on_account_token_sync(result if isinstance(result, str) else ''))

    def _on_account_token_sync(self, token):
        """同步 XHR 获取到的 token"""
        if token and len(token) > 10:
            self._token = token
            self.status.setText(f"已获取账号 Token: {token[:20]}...")
            QTimer.singleShot(500, self.accept)
            return

        # 所有方式都失败，回退到拦截方式
        self.status.setText("正在检查拦截到的请求...")
        self.web_page.runJavaScript(
            "window._capturedTokens ? JSON.stringify(window._capturedTokens) : '[]'",
            lambda result: self._check_tokens(result)
        )

    def _check_tokens(self, result):
        """检查拦截到的 token"""
        import json
        try:
            tokens = json.loads(result) if result else []
            if tokens:
                token = tokens[-1]
                if token and len(token) > 30:
                    self._token = token
                    self.status.setText(f"✓ 已获取 Token: {token[:20]}...")
                    QTimer.singleShot(500, self.accept)
                    return
        except Exception:
            pass

        # 从 cookie 获取
        self.status.setText("未拦截到请求，尝试从 Cookie 获取...")
        self.profile.cookieStore().getAllCookies(self._check_cookies)

    def _check_cookies(self, cookies):
        """检查 cookie"""
        for cookie in cookies:
            name = cookie.name().data().decode('utf-8', errors='ignore')
            value = cookie.value().data().decode('utf-8', errors='ignore')
            if 'token' in name.lower() and len(value) > 30:
                self._token = value
                self.status.setText(f"✓ 从 Cookie '{name}' 获取到 Token")
                QTimer.singleShot(500, self.accept)
                return

        # 从 localStorage 获取
        self.web_page.runJavaScript("""
        (function() {
            for (var i = 0; i < localStorage.length; i++) {
                var key = localStorage.key(i);
                var val = localStorage.getItem(key);
                if (key.toLowerCase().includes('token') && val && val.length > 30) {
                    try {
                        var p = JSON.parse(val);
                        if (p.token) return p.token;
                        if (p.data && p.data.token) return p.data.token;
                    } catch(e) {
                        return val;
                    }
                }
            }
            return '';
        })()
        """, lambda token: self._check_localstorage(token))

    def _check_localstorage(self, token):
        """检查 localStorage"""
        if token and len(token) > 30:
            self._token = token
            self.status.setText("✓ 从 localStorage 获取 Token")
            QTimer.singleShot(500, self.accept)
            return

        self.status.setText("✗ 未找到 Token，请确保已登录后重试")

    def get_token(self) -> str:
        """获取 Token"""
        return self._token

    def closeEvent(self, event):
        self.web_view.setUrl(QUrl("about:blank"))
        super().closeEvent(event)
