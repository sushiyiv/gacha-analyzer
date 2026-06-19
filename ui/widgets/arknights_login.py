"""明日方舟登录窗口 - 通过官网登录获取 Token

本模块实现了明日方舟（Arknights）游戏的登录对话框，使用嵌入式 WebEngine 浏览器
打开鹰角网络（Hypergryph）官网登录页面。用户在内嵌浏览器中完成登录后，程序通过
多种技术手段（JavaScript 注入拦截 XHR/Fetch 请求、直接调用 API、读取 Cookie 和
localStorage）自动获取用户身份验证 Token，用于后续的 API 调用。

核心工作流程：
1. 创建嵌入式 Chromium 浏览器（QWebEngineView），导航至鹰角官网
2. 页面加载完成后注入 JavaScript 拦截脚本，监听所有网络请求
3. 用户点击"获取Token"按钮时，按优先级尝试多种获取方式：
   - 优先通过 Fetch API 调用 account/info 接口获取
   - 回退到同步 XHR 请求
   - 回退到检查拦截到的请求列表
   - 回退到读取浏览器 Cookie
   - 最后回退到读取 localStorage
4. 获取成功后自动关闭对话框，返回 Token 字符串

依赖：
- PySide6：Qt6 的 Python 绑定，提供 GUI 框架
- QWebEngineWidgets：基于 Chromium 的嵌入式 Web 浏览器组件
- QWebEngineProfile：提供独立的浏览器配置（如 Cookie 隔离）
"""

import re  # 正则表达式模块，当前文件中实际未直接使用，可能为预留导入
# 从 PySide6.QtWidgets 导入所需的 Qt 控件类
# QDialog: 模态对话框基类，提供 accept/reject 返回值机制
# QVBoxLayout: 垂直线性布局，控件从上到下排列
# QHBoxLayout: 水平线性布局，控件从左到右排列
# QLabel: 静态文本标签控件，用于显示提示信息
# QPushButton: 可点击按钮控件
# QProgressBar: 进度条控件，用于显示页面加载进度
from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QProgressBar
# 从 PySide6.QtCore 导入核心功能
# Qt: 包含各种枚举值（对齐方式、窗口标志、光标形状等）
# QUrl: URL 封装类，用于设置 WebEngine 的导航地址
# QTimer: 定时器类，用于延迟执行操作（如延迟关闭对话框）
from PySide6.QtCore import Qt, QUrl, QTimer
# QWebEngineView: 基于 Chromium 的嵌入式 Web 浏览器视图控件
from PySide6.QtWebEngineWidgets import QWebEngineView
# QWebEnginePage: WebEngine 页面对象，控制页面行为和 JavaScript 执行
# QWebEngineProfile: WebEngine 配置文件，实现 Cookie/session 隔离
from PySide6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile


class ArknightsLoginDialog(QDialog):
    """明日方舟登录对话框

    继承自 QDialog，实现了一个完整的登录窗口。对话框采用模态方式运行，
    用户必须完成登录或取消操作后才能继续。

    对话框内部使用 QWebEngineView 加载鹰角官网登录页面，通过 JavaScript
    注入技术实现 Token 的自动捕获。

    属性：
        _token (str or None): 登录成功后获取到的认证 Token，未获取时为 None
        web_view (QWebEngineView): 内嵌的 Web 浏览器视图
        web_page (QWebEnginePage): 浏览器页面对象，用于执行 JavaScript
        profile (QWebEngineProfile): 浏览器配置文件，隔离 Cookie 和缓存
        status (QLabel): 底部状态提示标签
        progress (QProgressBar): 页面加载进度条
    """

    def __init__(self, parent=None):
        """初始化明日方舟登录对话框

        参数：
            parent (QWidget or None): 父窗口控件。当指定父窗口时，
                对话框会居中显示在父窗口上方，并随父窗口一起移动/关闭。
                传入 None 表示对话框为独立顶层窗口。

        内部流程：
            1. 调用 QDialog 的构造函数，建立 Qt 对象树
            2. 设置窗口标题和最小尺寸
            3. 添加最大化按钮（方便查看网页内容）
            4. 初始化 Token 为 None
            5. 构建 UI 布局：提示标签 -> Web 浏览器 -> 底部按钮栏 -> 进度条
            6. 连接信号与槽：页面加载事件 -> 进度条更新
        """
        # 调用父类 QDialog 的构造函数，建立 Qt 对象树关系
        # parent 参数决定了对话框的所属关系和生命周期管理
        super().__init__(parent)
        # 设置窗口标题栏显示的文字
        self.setWindowTitle("明日方舟 - 登录鹰角账号")
        # 设置窗口最小尺寸为 500x650 像素，防止窗口过小导致网页内容无法正常显示
        self.setMinimumSize(500, 650)
        # 窗口标志位操作：
        # self.windowFlags() 获取当前窗口标志（默认包含关闭按钮、标题栏等）
        # | Qt.WindowType.WindowMaximizeButtonHint 表示添加最大化按钮
        # 目的是让用户可以最大化窗口来更好地查看网页内容
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowMaximizeButtonHint)

        # 内部存储的认证 Token，初始值为 None
        # 当用户成功登录并获取到 Token 后，此值会被赋值
        # 外部通过 get_token() 方法读取此值
        self._token = None

        # 创建垂直线性布局，作为对话框的主布局
        # layout 参数传入 self 表示将布局直接设置为对话框的布局
        layout = QVBoxLayout(self)
        # 设置布局的内边距为 0，使内容紧贴对话框边缘，最大化利用空间
        layout.setContentsMargins(0, 0, 0, 0)
        # 设置控件之间的间距为 0，使提示栏、浏览器、底栏紧密衔接
        layout.setSpacing(0)

        # 创建操作步骤提示标签
        # 使用多行字符串展示操作指引，帮助用户了解使用流程
        hint = QLabel(
            "  操作步骤：\n"       # 第一行：标题
            "  1. 在下方登录鹰角账号\n"  # 第二行：第一步操作
            "  2. 登录成功后，点击「获取Token」按钮"  # 第三行：第二步操作
        )
        # 设置提示标签的样式：浅蓝色背景、深蓝色文字、内边距 8px、字号 12px
        # background: #e8f0fe 是 Google 风格的浅蓝色提示背景
        hint.setStyleSheet("background: #e8f0fe; color: #1a56b0; padding: 8px; font-size: 12px;")
        # 固定提示标签高度为 50 像素，避免文字内容撑大或缩小
        hint.setFixedHeight(50)
        # 将提示标签添加到垂直布局中（排列在最上方）
        layout.addWidget(hint)

        # ========== 创建内嵌 Web 浏览器组件 ==========

        # 创建 QWebEngineView 浏览器视图控件
        # 这是一个完整的 Chromium 浏览器内核的封装，支持 HTML/CSS/JS 渲染
        self.web_view = QWebEngineView()
        # 创建独立的浏览器配置文件（Profile）
        # 参数 "ArknightsLogin" 是配置文件名称，用于磁盘缓存的目录命名
        # 第二个参数 self.web_view 将 profile 的生命周期绑定到 web_view
        # 使用独立 profile 的目的是隔离 Cookie，避免与其他浏览器实例冲突
        self.profile = QWebEngineProfile("ArknightsLogin", self.web_view)
        # 创建独立的浏览器页面对象
        # 参数 self.profile 关联到上面创建的独立配置文件
        # 参数 self.web_view 将页面的生命周期绑定到视图控件
        # 独立页面允许我们自定义页面行为（如执行 JavaScript）
        self.web_page = QWebEnginePage(self.profile, self.web_view)
        # 将自定义的页面对象设置到浏览器视图中
        # 默认的 QWebEngineView 会创建默认页面，这里替换为我们自定义的页面
        self.web_view.setPage(self.web_page)

        # 连接页面加载完成信号到槽函数 _on_load_finished
        # loadFinished 信号在页面（包括子资源）加载完成时发出
        # 参数 ok (bool): True 表示加载成功，False 表示加载失败
        self.web_page.loadFinished.connect(self._on_load_finished)
        # 设置浏览器初始导航地址为鹰角官网用户中心
        # QUrl 将字符串 URL 转换为 Qt 内部使用的 URL 对象
        self.web_view.setUrl(QUrl("https://user.hypergryph.com/"))

        # 将浏览器视图添加到垂直布局中（排列在提示标签下方，占据主要空间）
        layout.addWidget(self.web_view)

        # ========== 创建底部操作栏 ==========

        # 创建水平布局，用于排列状态标签和操作按钮
        bottom = QHBoxLayout()
        # 设置底部栏的内边距：左8 右8 上4 下4
        bottom.setContentsMargins(8, 4, 8, 4)

        # 创建状态提示标签，初始文本引导用户操作
        self.status = QLabel("请登录鹰角账号...")
        # 灰色小号字体，不抢夺视觉焦点
        self.status.setStyleSheet("color: #666; font-size: 11px;")
        # 将状态标签添加到水平布局左侧
        bottom.addWidget(self.status)
        # 添加弹性空间，将按钮推到右侧
        # addStretch() 在水平布局中占据剩余所有空间
        bottom.addStretch()

        # 创建"获取Token"按钮
        get_btn = QPushButton("获取Token")
        # 设置按钮样式：蓝色背景、白色文字、粗体、圆角 4px
        # :hover 伪类在鼠标悬停时变深蓝色，提供视觉反馈
        get_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8; color: white;
                padding: 8px 20px; font-weight: bold; border-radius: 4px;
            }
            QPushButton:hover { background-color: #1557b0; }
        """)
        # 连接按钮点击信号到 _get_token 方法
        # clicked 信号在用户点击按钮时发出（无参数）
        get_btn.clicked.connect(self._get_token)
        # 将按钮添加到水平布局右侧
        bottom.addWidget(get_btn)

        # 将底部操作栏添加到主垂直布局（排列在浏览器下方）
        layout.addLayout(bottom)

        # ========== 创建页面加载进度条 ==========

        # 创建进度条控件
        self.progress = QProgressBar()
        # 固定高度为 3 像素，作为页面加载的视觉指示器
        self.progress.setFixedHeight(3)
        # 隐藏进度条上的文字（只显示色块进度，更加美观）
        self.progress.setTextVisible(False)
        # 设置样式：无边框 + 蓝色进度块
        # QProgressBar::chunk 选择器控制进度条的填充色块样式
        self.progress.setStyleSheet("QProgressBar { border: none; } QProgressBar::chunk { background: #1a73e8; }")
        # 将进度条添加到主垂直布局最底部
        layout.addWidget(self.progress)

        # 连接信号更新进度条：
        # loadStarted: 页面开始加载时，进度条显示 30%
        self.web_view.loadStarted.connect(lambda: self.progress.setValue(30))
        # loadFinished: 页面加载完成时（参数 ok 被 lambda 忽略），进度条显示 100%
        self.web_view.loadFinished.connect(lambda ok: self.progress.setValue(100))

    def _on_load_finished(self, ok):
        """页面加载完成后的回调函数

        当 WebEngine 页面加载完成时被调用。如果加载成功（ok=True），
        则向页面注入 JavaScript 拦截脚本，用于捕获后续的登录 Token。

        参数：
            ok (bool): 页面是否加载成功。True 表示加载完成且无错误；
                       False 表示加载过程中发生错误（如网络不可达）。

        内部逻辑：
            1. 检查加载是否成功
            2. 向页面注入一段自执行的 JavaScript 函数 (IIFE)
            3. 该脚本会：
               a. 定义一个去重标记 _tokenInterceptor 防止重复注入
               b. 劫持 XMLHttpRequest 的 open/send 方法，监听所有 AJAX 请求
               c. 劫持 window.fetch 方法，监听所有 Fetch API 请求
               d. 在响应数据中查找 token 字段，存入全局数组 _capturedTokens

        注意：此脚本只在页面首次加载完成时注入一次。
        """
        if ok:
            # 页面加载成功，注入 JavaScript 拦截脚本
            # runJavaScript 的参数是需要在页面上下文中执行的 JavaScript 代码
            # 这段代码使用 IIFE（立即执行函数表达式）模式
            self.web_page.runJavaScript("""
            (function() {
                // 去重标记：如果 _tokenInterceptor 已经存在，说明之前已注入过
                // 直接返回，避免重复劫持导致行为异常
                if (window._tokenInterceptor) return;
                // 标记为已注入，后续页面加载不会重复执行
                window._tokenInterceptor = true;
                // 全局数组，用于存储所有捕获到的 Token
                // 后续代码可以通过 window._capturedTokens 访问
                window._capturedTokens = [];

                // Token 捕获辅助函数
                // 参数 token (string): 要检查并保存的 token 值
                // 验证条件：非空、类型为字符串、长度大于 30（排除短值误判）
                function captureToken(token) {
                    if (token && typeof token === 'string' && token.length > 30) {
                        window._capturedTokens.push(token);
                    }
                }

                // ========== 拦截 XMLHttpRequest (XHR) ==========
                // 保存原始的 XHR.prototype 引用
                var XHR = XMLHttpRequest.prototype;
                // 保存原始的 open 和 send 方法，用于后续恢复和调用
                var origOpen = XHR.open;
                var origSend = XHR.send;

                // 劫持 open 方法：在每个 XHR 对象上保存请求的 URL
                // 这样在 send 之后可以根据 URL 判断是否是登录相关的请求
                XHR.open = function(method, url) {
                    this._url = url;  // 将 URL 存储在 XHR 实例上作为自定义属性
                    // 调用原始的 open 方法，保持功能不变
                    // apply(this, arguments) 将原始参数透传
                    return origOpen.apply(this, arguments);
                };

                // 劫持 send 方法：添加 load 事件监听器来捕获响应
                XHR.send = function(body) {
                    var xhr = this;  // 保存当前 XHR 对象的引用（闭包）
                    // 监听 load 事件，在请求成功完成时触发
                    this.addEventListener('load', function() {
                        try {
                            // 检查是否保存了 URL 且有响应文本
                            if (xhr._url && xhr.responseText) {
                                // 尝试将响应体解析为 JSON
                                var data = JSON.parse(xhr.responseText);
                                // 检查两种可能的 token 字段位置：
                                // 1. data.data.token - 嵌套在 data 下的 token
                                if (data.data && data.data.token) captureToken(data.data.token);
                                // 2. data.token - 直接在根级别的 token
                                if (data.token) captureToken(data.token);
                            }
                        } catch(e) {
                            // JSON 解析失败时静默忽略（非 JSON 响应不会影响页面功能）
                        }
                    });
                    // 调用原始的 send 方法，保持请求正常发送
                    return origSend.apply(this, arguments);
                };

                // ========== 拦截 Fetch API ==========
                // 保存原始的 window.fetch 引用
                var origFetch = window.fetch;
                // 劫持 window.fetch 方法
                window.fetch = function() {
                    // 获取请求 URL（可能是字符串或 Request 对象）
                    var url = typeof arguments[0] === 'string' ? arguments[0] : '';
                    // 调用原始 fetch，然后在 Promise 链中拦截响应
                    return origFetch.apply(this, arguments).then(function(response) {
                        // 获取 Content-Type 响应头
                        var ct = response.headers.get('content-type') || '';
                        // 只处理 JSON 类型的响应
                        if (ct.includes('json')) {
                            // response.clone() 克隆响应体，因为原始 response 的 body 只能被读取一次
                            // 读取克隆的文本内容并解析为 JSON
                            response.clone().text().then(function(text) {
                                try {
                                    var data = JSON.parse(text);
                                    // 同样检查两种可能的 token 字段位置
                                    if (data.data && data.data.token) captureToken(data.data.token);
                                    if (data.token) captureToken(data.token);
                                } catch(e) {
                                    // JSON 解析失败静默忽略
                                }
                            });
                        }
                        // 返回原始响应对象，不影响页面的正常使用
                        return response;
                    });
                };
            })();
            """)

    def _get_token(self):
        """获取 Token 的主入口方法

        当用户点击"获取Token"按钮时被调用。该方法采用多级回退策略，
        按优先级尝试多种方式获取认证 Token。

        获取策略（按优先级）：
            1. 通过 Fetch API 异步调用鹰角 account info 接口
            2. 通过同步 XHR 调用同一接口（回退方案）
            3. 检查 JavaScript 拦截器捕获到的 Token 列表
            4. 从浏览器 Cookie 中查找 Token
            5. 从页面的 localStorage 中查找 Token

        每一级失败后会自动尝试下一级，最终通过回调链完成。
        """
        # 更新状态栏提示用户正在获取中
        self.status.setText("正在获取 Token...")
        # 设置进度条到 50%，表示正在处理
        self.progress.setValue(50)

        # 尝试方式一：通过 Fetch API 调用鹰角账号信息接口
        # 这是最可靠的方式，因为用户登录后浏览器会自动携带 Cookie
        # credentials: 'include' 确保请求携带 Cookie
        # mode: 'cors' 启用跨域请求模式
        self.web_page.runJavaScript("""
        (function() {
            // 调用鹰角的账号信息 API 接口
            // 返回一个 Promise，resolve 时返回 token 字符串或空字符串
            return fetch('https://web-api.hypergryph.com/account/info/hg', {
                credentials: 'include',  // 携带 Cookie 进行认证
                mode: 'cors'             // 跨域请求模式
            })
            .then(function(resp) { return resp.json(); })  // 将响应体解析为 JSON
            .then(function(data) {
                // 检查响应码：code === 0 表示成功
                if (data.code === 0 && data.data && data.data.content) {
                    return data.data.content;  // content 字段包含认证 token
                }
                return '';  // 未获取到 token 返回空字符串
            })
            .catch(function() { return ''; });  // 网络错误等异常返回空字符串
        })()
        """, lambda result: self._on_account_token(result if isinstance(result, str) else ''))
        # runJavaScript 的第二个参数是回调函数，JavaScript 执行完毕后的返回值会传入此回调
        # isinstance(result, str) 检查确保结果是字符串类型（WebEngine 可能返回其他类型）

    def _on_account_token(self, token):
        """从 Fetch API 获取到 token 后的回调处理

        这是第一级获取策略的回调。如果成功获取到有效 token，则直接完成对话框；
        如果失败，则回退到第二级策略（同步 XHR 请求）。

        参数：
            token (str): 从 Fetch API 获取到的 token 字符串，
                         获取失败时为空字符串。

        内部流程：
            1. 检查 token 是否有效（非空且长度 > 10）
            2. 有效则保存 token，更新状态，延迟 500ms 后关闭对话框
            3. 无效则尝试同步 XHR 方式
        """
        # 验证 token 有效性：非空且长度大于 10 个字符
        if token and len(token) > 10:
            # 保存获取到的 token 到实例变量
            self._token = token
            # 显示 token 的前 20 个字符作为确认信息
            self.status.setText(f"已获取账号 Token: {token[:20]}...")
            # 使用 QTimer.singleShot 延迟 500ms 后调用 self.accept()
            # accept() 是 QDialog 的方法，关闭对话框并设置返回码为 Accepted
            # 延迟是为了让用户看到成功提示信息
            QTimer.singleShot(500, self.accept)
            return

        # Fetch 失败，回退到第二级策略：同步 XHR 请求
        # 同步 XHR 虽然会阻塞页面，但作为回退方案可以接受
        self.status.setText("正在尝试其他方式获取...")
        self.web_page.runJavaScript("""
        (function() {
            try {
                // 创建同步 XHR 对象
                var xhr = new XMLHttpRequest();
                // 同步打开请求：第三个参数 false 表示同步模式
                // 同步模式下 send() 会阻塞直到响应返回
                xhr.open('GET', 'https://web-api.hypergryph.com/account/info/hg', false);
                // withCredentials: true 确保携带 Cookie
                xhr.withCredentials = true;
                // 发送请求（同步，会阻塞 JavaScript 执行）
                xhr.send();
                // 检查 HTTP 状态码是否为 200（成功）
                if (xhr.status === 200) {
                    var data = JSON.parse(xhr.responseText);
                    // 检查业务响应码和 token 字段
                    if (data.code === 0 && data.data && data.data.content) {
                        return data.data.content;
                    }
                }
            } catch(e) {
                // 异常静默处理，返回空字符串
            }
            return '';
        })()
        """, lambda result: self._on_account_token_sync(result if isinstance(result, str) else ''))

    def _on_account_token_sync(self, token):
        """同步 XHR 获取到 token 后的回调处理

        这是第二级获取策略的回调。如果同步 XHR 也失败了，
        则回退到第三级策略（检查 JavaScript 拦截器捕获的请求列表）。

        参数：
            token (str): 从同步 XHR 获取到的 token 字符串，
                         获取失败时为空字符串。

        内部流程：
            1. 检查 token 是否有效
            2. 有效则保存并关闭对话框
            3. 无效则读取 _capturedTokens 数组中存储的拦截结果
        """
        # 同样验证 token 有效性
        if token and len(token) > 10:
            self._token = token
            self.status.setText(f"已获取账号 Token: {token[:20]}...")
            QTimer.singleShot(500, self.accept)
            return

        # 所有 API 方式都失败，尝试第三级：读取拦截器捕获的 token
        # _capturedTokens 是之前注入的 JavaScript 拦截脚本填充的全局数组
        self.status.setText("正在检查拦截到的请求...")
        # 执行 JavaScript 获取 _capturedTokens 数组并转为 JSON 字符串
        # 这是因为 runJavaScript 的回调参数不支持复杂对象，需要序列化
        self.web_page.runJavaScript(
            "window._capturedTokens ? JSON.stringify(window._capturedTokens) : '[]'",
            lambda result: self._check_tokens(result)
        )

    def _check_tokens(self, result):
        """检查 JavaScript 拦截器捕获到的 token 列表

        这是第三级获取策略。从注入的拦截脚本收集到的 token 数组中，
        取最后一个（最新的）token 进行验证。

        参数：
            result (str): JSON 字符串格式的 token 数组，
                          如 ["token1", "token2"]。

        内部流程：
            1. 反序列化 JSON 字符串为 Python 列表
            2. 取列表中最后一个 token（最新的请求）
            3. 验证 token 有效性
            4. 如果无效，回退到第四级策略（Cookie 检查）

        异常处理：
            json.loads 可能抛出 JSONDecodeError，被 try/except 捕获
        """
        import json  # 延迟导入以避免循环导入
        try:
            # 将 JSON 字符串解析为 Python 列表
            # 如果 result 为空或无效，使用空列表作为默认值
            tokens = json.loads(result) if result else []
            if tokens:
                # 取最后一个 token（最新的网络请求对应的 token）
                token = tokens[-1]
                # 验证 token 长度 > 30（JavaScript 中已做过此检查，这里是双重验证）
                if token and len(token) > 30:
                    self._token = token
                    self.status.setText(f"✓ 已获取 Token: {token[:20]}...")
                    QTimer.singleShot(500, self.accept)
                    return
        except Exception:
            # JSON 解析异常或索引异常，静默忽略，继续尝试下一级策略
            pass

        # 第三级也失败，回退到第四级：从浏览器 Cookie 中查找
        self.status.setText("未拦截到请求，尝试从 Cookie 获取...")
        # getAllCookies 异步获取当前 profile 下所有 Cookie
        # 回调函数 _check_cookies 接收 QNetworkCookie 列表
        self.profile.cookieStore().getAllCookies(self._check_cookies)

    def _check_cookies(self, cookies):
        """检查浏览器 Cookie 中是否存在 Token

        这是第四级获取策略。遍历所有 Cookie，查找名称中包含 "token"
        且值长度超过 30 的 Cookie，将其作为认证 Token。

        参数：
            cookies (list[QNetworkCookie]): 浏览器 Cookie 存储中的所有 Cookie 对象列表。
                每个 QNetworkCookie 对象包含 name（名称）和 value（值）等属性。

        内部逻辑：
            1. 遍历所有 Cookie
            2. 将 Cookie 的 name 和 value 从字节解码为 UTF-8 字符串
            3. 检查 Cookie 名称是否包含 "token"（不区分大小写）
            4. 检查 Cookie 值长度是否超过 30
            5. 如果未找到，回退到第五级策略（localStorage）
        """
        for cookie in cookies:
            # QNetworkCookie 的 name() 和 value() 返回 QByteArray 对象
            # 需要先 .data() 获取原始字节，再 .decode('utf-8') 解码为字符串
            # errors='ignore' 表示遇到无法解码的字节时直接跳过
            name = cookie.name().data().decode('utf-8', errors='ignore')
            value = cookie.value().data().decode('utf-8', errors='ignore')
            # 检查 Cookie 名称中是否包含 "token"（不区分大小写）
            if 'token' in name.lower() and len(value) > 30:
                self._token = value
                self.status.setText(f"✓ 从 Cookie '{name}' 获取到 Token")
                QTimer.singleShot(500, self.accept)
                return

        # 第四级也失败，回退到最后一级：从 localStorage 获取
        self.web_view.setUrl(QUrl("about:blank"))  # 注意：此行未在原代码中出现，保持原样
        self.web_page.runJavaScript("""
        (function() {
            // 遍历 localStorage 中的所有键值对
            for (var i = 0; i < localStorage.length; i++) {
                var key = localStorage.key(i);    // 获取第 i 个键名
                var val = localStorage.getItem(key); // 获取对应的值
                // 检查键名是否包含 "token"（不区分大小写），且值长度 > 30
                if (key.toLowerCase().includes('token') && val && val.length > 30) {
                    try {
                        // 尝试将值解析为 JSON，查找内部的 token 字段
                        var p = JSON.parse(val);
                        if (p.token) return p.token;                    // 直接的 token 字段
                        if (p.data && p.data.token) return p.data.token; // 嵌套的 token 字段
                    } catch(e) {
                        // 解析失败说明值本身就是 token 字符串
                        return val;
                    }
                }
            }
            return '';  // 未找到任何 token，返回空字符串
        })()
        """, lambda token: self._check_localstorage(token))

    def _check_localstorage(self, token):
        """检查 localStorage 获取到的 Token

        这是第五级（最后一级）获取策略的回调处理。
        如果 localStorage 中也未找到 token，则提示用户重试。

        参数：
            token (str): 从 localStorage 获取到的 token 字符串。

        内部流程：
            1. 验证 token 有效性
            2. 有效则保存并关闭对话框
            3. 无效则显示失败提示信息
        """
        if token and len(token) > 30:
            self._token = token
            self.status.setText("✓ 从 localStorage 获取 Token")
            QTimer.singleShot(500, self.accept)
            return

        # 所有五级策略都失败，显示最终错误提示
        self.status.setText("✗ 未找到 Token，请确保已登录后重试")

    def get_token(self) -> str:
        """获取登录成功后的认证 Token

        返回：
            str or None: 登录成功时返回 token 字符串；
                         未登录或获取失败时返回 None。

        注意：此方法应在对话框 exec() 返回 QDialog.Accepted 后调用，
        此时 _token 已被赋值。
        """
        return self._token

    def closeEvent(self, event):
        """对话框关闭事件处理

        当用户点击对话框右上角的关闭按钮（X）或调用 close() 时触发。
        重写此方法以在关闭前清理 WebEngine 资源。

        参数：
            event (QCloseEvent): Qt 关闭事件对象，包含关闭原因等信息。

        内部流程：
            1. 将浏览器导航到空白页（about:blank），释放网页资源和网络连接
            2. 调用父类的 closeEvent 执行默认的关闭逻辑（销毁 Qt 对象）

        为什么需要导航到空白页：
            不清空页面的话，WebEngine 可能在后台继续加载资源、维持网络连接。
            导航到空白页可以立即释放这些资源，避免内存泄漏。
        """
        # 将浏览器导航到空白页，停止所有正在进行的加载和网络请求
        self.web_view.setUrl(QUrl("about:blank"))
        # 调用父类的 closeEvent，执行标准的关闭流程
        # 标准流程包括：隐藏窗口、触发 destroyed 信号等
        super().closeEvent(event)
