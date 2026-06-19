"""终末地登录窗口 - 通过鹰角官网登录自动获取 Token

本模块实现了明日方舟：终末地（Arknights: Endfield）的登录对话框。
使用嵌入式 WebEngine 浏览器打开鹰角官网，用户登录后自动捕获认证 Token。

与明日方舟版 (arknights_login.py) 的区别：
- 使用独立的浏览器 Profile 名称 "EndfieldLogin"（终末地专用隔离空间）
- 通过监听浏览器标题变化（titleChanged 信号）来接收 Token
- 包含定时轮询 Cookie 的兜底方案
- 使用 document.title 作为 JavaScript 到 Python 的通信通道

Token 捕获策略：
1. 拦截 XHR 请求中的登录响应
2. 拦截 Fetch API 请求中的登录响应
3. 定时轮询 account/info API 接口（每 2 秒）
4. 所有方式都通过修改 document.title 传递 Token

通信机制说明：
JavaScript 和 Python 之间不能直接调用函数。此模块使用了一个巧妙的方案：
JavaScript 捕获到 Token 后，将页面标题设置为 "LOGIN_TOKEN:xxx"，
Python 端通过 QWebEnginePage 的 titleChanged 信号监听标题变化，
从而实现从 JavaScript 到 Python 的数据传递。

依赖：
- PySide6: Qt6 的 Python 绑定
- QWebEngineWidgets: 嵌入式 Web 浏览器组件
- QWebEngineCore: WebEngine 核心组件（Page、Profile）
"""

# 从 PySide6.QtWidgets 导入所需的 Qt 控件类
# QDialog: 模态对话框基类
# QVBoxLayout: 垂直线性布局
# QLabel: 静态文本标签
# QPushButton: 可点击按钮
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QPushButton
)
# Qt: 核心枚举（窗口标志、对齐方式等）
# QTimer: 定时器（用于延迟关闭对话框）
# QUrl: URL 封装类（用于设置浏览器导航地址）
from PySide6.QtCore import Qt, QTimer, QUrl
# QWebEngineView: 基于 Chromium 的嵌入式 Web 浏览器视图
from PySide6.QtWebEngineWidgets import QWebEngineView
# QWebEnginePage: WebEngine 页面对象，控制 JavaScript 执行和页面事件
# QWebEngineProfile: 浏览器配置文件，隔离 Cookie 和缓存
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile


class LoginDialog(QDialog):
    """终末地登录对话框 - 打开鹰角官网登录，自动捕获 Token

    通过嵌入式浏览器打开鹰角官网，用户在浏览器中完成登录后，
    程序通过 JavaScript 注入和标题监听机制自动获取认证 Token。

    与 ArknightsLoginDialog 的关键区别：
    - 使用 document.title 通信而非 runJavaScript 回调
    - 包含定时轮询的兜底方案
    - 专注于单一 token 获取路径（不尝试多种回退策略）

    属性：
        _framework_token (str or None): 获取到的认证 Token
        _last_error (str): 最近一次错误信息
        web_view (QWebEngineView): 嵌入式浏览器视图
        profile (QWebEngineProfile): 浏览器配置文件（隔离 Cookie）
        page (QWebEnginePage): 浏览器页面对象
        status_label (QLabel): 顶部状态提示标签
        cancel_btn (QPushButton): 取消按钮
    """

    def __init__(self, parent=None):
        """初始化终末地登录对话框

        参数：
            parent (QWidget or None): 父窗口控件。

        UI 结构（从上到下）：
            状态提示标签
            嵌入式 Web 浏览器（占据主要空间）
            取消按钮
        """
        super().__init__(parent)  # 调用 QDialog 父类构造函数
        # 设置窗口标题
        self.setWindowTitle("终末地 - 登录获取")
        # 设置最小尺寸，确保浏览器内容有足够显示空间
        self.setMinimumSize(500, 650)
        # 移除标题栏的帮助按钮（问号图标）
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        # 认证 Token 存储，初始为 None
        self._framework_token = None
        # 错误信息存储，初始为空字符串
        self._last_error = ""

        # 创建主垂直布局
        layout = QVBoxLayout(self)
        layout.setSpacing(8)  # 控件间距 8px
        layout.setContentsMargins(8, 8, 8, 8)  # 内边距 8px

        # ========== 顶部状态提示标签 ==========
        self.status_label = QLabel("请在下方网页中登录鹰角账号")
        # 蓝色文字，12px 字号，内边距 4px
        self.status_label.setStyleSheet("color: #1a73e8; font-size: 12px; padding: 4px;")
        # 水平和垂直居中对齐
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # ========== 创建嵌入式 Web 浏览器 ==========
        self.web_view = QWebEngineView()
        # 创建终末地专用的浏览器配置文件
        # "EndfieldLogin" 是 Profile 名称，用于磁盘缓存目录命名
        # 独立的 Profile 确保与其他登录窗口的 Cookie 互不干扰
        self.profile = QWebEngineProfile("EndfieldLogin", self.web_view)
        # 创建独立的页面对象，关联到终末地 Profile
        self.page = QWebEnginePage(self.profile, self.web_view)
        # 将页面设置到视图中
        self.web_view.setPage(self.page)

        # 连接页面加载完成信号到 JavaScript 注入方法
        self.page.loadFinished.connect(self._on_page_loaded)
        # 连接标题变化信号到 Token 捕获方法
        # 这是 JavaScript -> Python 的通信通道
        self.page.titleChanged.connect(self._on_title_changed)
        # 导航到鹰角官网用户中心
        self.web_view.setUrl(QUrl("https://user.hypergryph.com/"))

        # 将浏览器视图添加到布局中（占据主要空间）
        layout.addWidget(self.web_view)

        # ========== 底部取消按钮 ==========
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setFixedHeight(32)  # 固定高度 32px
        # reject() 关闭对话框，返回 QDialog.Rejected
        self.cancel_btn.clicked.connect(self.reject)
        layout.addWidget(self.cancel_btn)

    def _on_page_loaded(self, ok):
        """页面加载完成后注入 JavaScript Token 拦截脚本

        每当页面加载完成（包括页面跳转）时都会调用此方法。
        注入的脚本会拦截网络请求并捕获登录 Token。

        参数：
            ok (bool): 页面是否加载成功。False 表示加载失败（如网络错误）。

        注入脚本的工作原理：
            1. 拦截 XMLHttpRequest 的 open/send 方法
            2. 拦截 window.fetch 方法
            3. 在请求响应中查找 token 字段
            4. 找到后通过修改 document.title 传递给 Python 端
            5. 同时启动定时轮询作为兜底方案

        为什么使用 document.title 通信：
            QWebEngineView 不支持直接从 JavaScript 调用 Python 函数。
            但 titleChanged 信号可以监听标题变化，因此将标题设置为
            "LOGIN_TOKEN:xxx" 格式，Python 端解析标题即可获取 Token。
        """
        if not ok:
            return  # 页面加载失败，不注入脚本

        # 向页面注入 JavaScript 拦截脚本
        # 使用 IIFE（立即执行函数表达式）避免污染全局作用域
        self.page.runJavaScript("""
        (function() {
            // 去重标记：防止重复注入导致多次劫持
            if (window._tokenInterceptor) return;
            window._tokenInterceptor = true;

            // Token 发送函数：通过修改页面标题将 Token 传递给 Python
            // 参数 token (string): 要发送的认证 token
            // 条件：非空且未发送过（防止重复发送）
            function sendToken(token) {
                if (!token || window._tokenSent) return;
                // 标记已发送，防止后续的定时轮询重复发送
                window._tokenSent = true;
                // 将页面标题设置为特殊格式：LOGIN_TOKEN: + token 值
                // Python 端的 _on_title_changed 会解析这个标题
                document.title = 'LOGIN_TOKEN:' + token;
            }

            // ========== 拦截 XMLHttpRequest (XHR) ==========
            var XHR = XMLHttpRequest.prototype;
            // 保存原始方法的引用
            var origOpen = XHR.open;
            var origSend = XHR.send;

            // 劫持 open 方法：在 XHR 实例上保存请求 URL
            XHR.open = function(method, url) {
                this._url = url;  // 保存 URL 到实例属性
                return origOpen.apply(this, arguments);  // 调用原始方法
            };

            // 劫持 send 方法：在请求完成后检查响应中的 token
            XHR.send = function(body) {
                var xhr = this;
                // 添加 load 事件监听器
                this.addEventListener('load', function() {
                    try {
                        // 检查 URL 是否是登录认证接口
                        if (xhr._url && xhr._url.includes('as.hypergryph.com/user/auth')) {
                            // 解析 JSON 响应
                            var data = JSON.parse(xhr.responseText);
                            // 检查 status === 0 表示登录成功
                            // data.data.token 是 token 字段
                            if (data.status === 0 && data.data && data.data.token) {
                                sendToken(data.data.token);
                            }
                        }
                    } catch(e) {
                        // JSON 解析失败等异常静默忽略
                    }
                });
                return origSend.apply(this, arguments);
            };

            // ========== 拦截 Fetch API ==========
            var origFetch = window.fetch;
            // 劫持 fetch 方法（async 函数）
            window.fetch = async function() {
                // 调用原始 fetch 并 await 结果
                var resp = await origFetch.apply(this, arguments);
                try {
                    // 检查响应 URL 是否是登录认证接口
                    if (resp.url && resp.url.includes('as.hypergryph.com/user/auth')) {
                        // 克隆响应体（因为原始 response 的 body 只能读取一次）
                        var clone = resp.clone();
                        // 异步解析 JSON 并检查 token
                        clone.json().then(function(data) {
                            if (data.status === 0 && data.data && data.data.token) {
                                sendToken(data.data.token);
                            }
                        });
                    }
                } catch(e) {}
                // 返回原始响应，不影响页面正常功能
                return resp;
            };

            // ========== 定时轮询兜底方案 ==========
            // 如果 XHR/Fetch 拦截都未捕获到 token，
            // 则定时调用 account/info 接口检查是否已登录
            var timer = setInterval(function() {
                // 如果已经发送过 token，停止定时器
                if (window._tokenSent) { clearInterval(timer); return; }
                // 调用鹰角账号信息 API
                fetch('https://web-api.hypergryph.com/account/info/hg', {
                    method: 'GET',
                    credentials: 'include'  // 携带 Cookie 认证
                }).then(function(r) { return r.json(); }).then(function(d) {
                    // code === 0 表示已登录，content 字段包含 token
                    if (d.code === 0 && d.data && d.data.content) {
                        sendToken(d.data.content);
                        clearInterval(timer);  // 获取成功后停止轮询
                    }
                }).catch(function(){
                    // 网络错误等异常：不处理，等待下次轮询
                });
            }, 2000);  // 每 2 秒轮询一次
        })();
        """)

    def _on_title_changed(self, title: str):
        """监听浏览器页面标题变化，捕获 Token

        这是 JavaScript -> Python 通信通道的接收端。
        当 JavaScript 设置 document.title 为 "LOGIN_TOKEN:xxx" 格式时，
        此方法会被触发，解析出 Token。

        参数：
            title (str): 页面标题的新值。

        通信协议：
            - 格式: "LOGIN_TOKEN:" + token_value
            - token 长度 > 10 时才视为有效
            - 获取成功后自动关闭对话框
        """
        # 检查标题是否以 "LOGIN_TOKEN:" 前缀开头
        if title and title.startswith("LOGIN_TOKEN:"):
            # 截取前缀之后的部分作为 Token
            token = title[len("LOGIN_TOKEN:"):]
            # 验证 Token 有效性：非空且长度 > 10
            if token and len(token) > 10:
                # 保存 Token
                self._framework_token = token
                # 更新状态标签为绿色成功提示，显示 Token 前 20 个字符
                self.status_label.setText(f"✓ 登录成功！Token: {token[:20]}...")
                self.status_label.setStyleSheet(
                    "color: #4CAF50; font-size: 12px; font-weight: bold; padding: 4px;"
                )
                # 延迟 500ms 后关闭对话框
                # accept() 设置返回码为 QDialog.Accepted
                QTimer.singleShot(500, self.accept)

    def get_framework_token(self) -> str:
        """获取登录成功后的认证 Token

        返回：
            str or None: 登录成功时返回 token 字符串；
                         未登录或获取失败时返回 None。

        使用方式：
            dialog = LoginDialog()
            if dialog.exec() == QDialog.Accepted:
                token = dialog.get_framework_token()
        """
        return self._framework_token

    def get_error(self) -> str:
        """获取最近的错误信息

        返回：
            str: 错误信息字符串。此版本始终返回空字符串，
                  因为错误通过 status_label 直接显示。

        注意：此方法是为了与 API 版和轻量版保持统一的接口。
        """
        return self._last_error

    def closeEvent(self, event):
        """对话框关闭事件处理

        默认的关闭处理：调用父类的 closeEvent 执行标准关闭流程。

        参数：
            event (QCloseEvent): Qt 关闭事件对象。

        注意：此版本没有显式导航到空白页（与 arknights_login.py 不同），
        因为终末地版本的对话框关闭后不需要保留浏览器状态。
        """
        super().closeEvent(event)
