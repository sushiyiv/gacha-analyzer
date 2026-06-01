"""终末地登录窗口 - 通过鹰角官网登录自动获取 Token"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton
)
from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtWebEngineWidgets import QWebEngineView
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile


class LoginDialog(QDialog):
    """终末地登录对话框 - 打开鹰角官网登录，自动捕获 Token"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("终末地 - 登录获取")
        self.setMinimumSize(500, 650)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        self._framework_token = None
        self._last_error = ""

        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        layout.setContentsMargins(8, 8, 8, 8)

        self.status_label = QLabel("请在下方网页中登录鹰角账号")
        self.status_label.setStyleSheet("color: #1a73e8; font-size: 12px; padding: 4px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # 内嵌浏览器
        self.web_view = QWebEngineView()
        self.profile = QWebEngineProfile("EndfieldLogin", self.web_view)
        self.page = QWebEnginePage(self.profile, self.web_view)
        self.web_view.setPage(self.page)

        self.page.loadFinished.connect(self._on_page_loaded)
        self.page.titleChanged.connect(self._on_title_changed)
        self.web_view.setUrl(QUrl("https://user.hypergryph.com/"))

        layout.addWidget(self.web_view)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setFixedHeight(32)
        self.cancel_btn.clicked.connect(self.reject)
        layout.addWidget(self.cancel_btn)

    def _on_page_loaded(self, ok):
        """页面加载完成，注入 token 拦截脚本"""
        if not ok:
            return

        self.page.runJavaScript("""
        (function() {
            if (window._tokenInterceptor) return;
            window._tokenInterceptor = true;
            function sendToken(token) {
                if (!token || window._tokenSent) return;
                window._tokenSent = true;
                document.title = 'LOGIN_TOKEN:' + token;
            }
            // 拦截 XHR
            var XHR = XMLHttpRequest.prototype;
            var origOpen = XHR.open;
            var origSend = XHR.send;
            XHR.open = function(method, url) { this._url = url; return origOpen.apply(this, arguments); };
            XHR.send = function(body) {
                var xhr = this;
                this.addEventListener('load', function() {
                    try {
                        if (xhr._url && xhr._url.includes('as.hypergryph.com/user/auth')) {
                            var data = JSON.parse(xhr.responseText);
                            if (data.status === 0 && data.data && data.data.token) {
                                sendToken(data.data.token);
                            }
                        }
                    } catch(e) {}
                });
                return origSend.apply(this, arguments);
            };
            // 拦截 Fetch
            var origFetch = window.fetch;
            window.fetch = async function() {
                var resp = await origFetch.apply(this, arguments);
                try {
                    if (resp.url && resp.url.includes('as.hypergryph.com/user/auth')) {
                        var clone = resp.clone();
                        clone.json().then(function(data) {
                            if (data.status === 0 && data.data && data.data.token) {
                                sendToken(data.data.token);
                            }
                        });
                    }
                } catch(e) {}
                return resp;
            };
            // 轮询 Cookie 兜底
            var timer = setInterval(function() {
                if (window._tokenSent) { clearInterval(timer); return; }
                fetch('https://web-api.hypergryph.com/account/info/hg', {
                    method: 'GET', credentials: 'include'
                }).then(function(r) { return r.json(); }).then(function(d) {
                    if (d.code === 0 && d.data && d.data.content) {
                        sendToken(d.data.content);
                        clearInterval(timer);
                    }
                }).catch(function(){});
            }, 2000);
        })();
        """)

    def _on_title_changed(self, title: str):
        """监听页面标题变化，捕获 token"""
        if title and title.startswith("LOGIN_TOKEN:"):
            token = title[len("LOGIN_TOKEN:"):]
            if token and len(token) > 10:
                self._framework_token = token
                self.status_label.setText(f"✓ 登录成功！Token: {token[:20]}...")
                self.status_label.setStyleSheet("color: #4CAF50; font-size: 12px; font-weight: bold; padding: 4px;")
                QTimer.singleShot(500, self.accept)

    def get_framework_token(self) -> str:
        return self._framework_token

    def get_error(self) -> str:
        return self._last_error

    def closeEvent(self, event):
        super().closeEvent(event)
