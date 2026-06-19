"""明日方舟登录窗口 - API直接登录（无需加载网页）

本模块实现了明日方舟（Arknights）登录对话框的 API 版本，与 WebEngine 版不同，
此版本不需要加载网页，而是直接调用鹰角网络的登录 API 进行身份验证。

核心优势：
- 不依赖 WebEngine（Chromium 内核），启动速度快，内存占用低
- 直接通过 HTTP POST 请求完成登录，流程简洁
- 支持记住密码功能（使用 Base64 编码存储，简单混淆）

登录流程：
1. 用户输入手机号（账号）和密码
2. 后台线程向鹰角 API 发送 POST 请求
3. API 返回成功时携带 token，返回失败时携带错误信息
4. 登录成功后保存账号信息到本地配置

依赖：
- requests: HTTP 客户端库，用于发送网络请求
- PySide6: Qt6 的 Python 绑定，提供 GUI 框架
- core.config.Config: 应用配置管理类，用于存储/读取保存的账号
- ui.widgets.styled_widgets.StyledCheckBox: 自定义样式的复选框控件
"""

import requests  # HTTP 客户端库，用于向鹰角 API 发送 POST 请求
# 从 PySide6.QtWidgets 导入所需的 Qt 控件类
# QDialog: 模态对话框基类
# QVBoxLayout/HBoxLayout: 垂直/水平线性布局
# QLabel: 静态文本标签
# QPushButton: 可点击按钮
# QLineEdit: 单行文本输入框（用于输入账号和密码）
# QCheckBox: 复选框（用于"记住密码"选项）
# QMessageBox: 消息提示框（已导入但未使用，可能为预留）
# QComboBox: 下拉选择框（用于选择已保存的账号）
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QMessageBox, QComboBox
)
# Qt: 核心枚举和工具类
# QThread: 工作线程基类，用于在后台执行耗时的网络请求
# Signal: Qt 信号类，用于线程间安全通信
from PySide6.QtCore import Qt, QThread, Signal
# StyledCheckBox: 自定义样式的复选框，提供统一的视觉风格
from ui.widgets.styled_widgets import StyledCheckBox


class _LoginWorker(QThread):
    """后台线程执行登录 API 请求

    继承自 QThread，在独立线程中执行 HTTP 登录请求。
    这样做是为了避免网络请求阻塞 UI 主线程，保持界面响应性。

    Qt 的线程安全规则：
    - 不能在子线程中直接操作 UI 控件
    - 必须通过信号（Signal）机制与主线程通信
    - 子线程发出的信号会被自动排队到主线程的事件循环中处理

    属性：
        success (Signal[str]): 登录成功信号，携带获取到的 token 字符串
        error (Signal[str]): 登录失败信号，携带错误信息字符串
        _account (str): 用户输入的手机号/账号
        _password (str): 用户输入的密码
    """

    # 类级别定义的信号：
    # success 信号：参数类型为 str，登录成功时发出，携带 token
    success = Signal(str)
    # error 信号：参数类型为 str，登录失败时发出，携带错误消息
    error = Signal(str)

    def __init__(self, account, password):
        """初始化登录工作线程

        参数：
            account (str): 用户的手机号或账号
            password (str): 用户的密码

        注意：QThread 的构造函数中不执行网络请求，
        实际的网络操作在 run() 方法中执行。
        """
        super().__init__()  # 调用 QThread 父类构造函数
        self._account = account  # 保存账号到实例变量
        self._password = password  # 保存密码到实例变量

    def run(self):
        """线程启动后执行的主方法

        QThread.start() 调用后，此方法在新线程中自动执行。
        包含完整的登录 API 调用逻辑。

        API 接口说明：
            URL: https://as.hypergryph.com/user/auth/v1/token_by_phone_password
            方法: POST
            Content-Type: application/json
            请求体: {"phone": "手机号", "password": "密码"}
            响应体: {
                "status": 0,           // 0=成功, 其他=失败
                "data": {"token": "..."},  // 成功时返回 token
                "msg": "错误信息"        // 失败时返回错误描述
            }

        异常处理：
            - 网络超时、DNS 解析失败等网络异常会被 try/except 捕获
            - HTTP 非 200 状态码、JSON 解析失败等也会被捕获
            - 所有异常通过 error 信号安全地传递回主线程
        """
        try:
            # 鹰角网络的手机号+密码登录 API 地址
            url = "https://as.hypergryph.com/user/auth/v1/token_by_phone_password"
            # HTTP 请求头
            headers = {
                "Content-Type": "application/json",  # 告诉服务器请求体是 JSON 格式
                # 模拟浏览器的 User-Agent，避免被服务器拒绝
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            # 请求体数据：手机号和密码
            data = {"phone": self._account, "password": self._password}
            # 发送 POST 请求
            # json=data 自动将字典序列化为 JSON 并设置 Content-Type
            # timeout=15 设置 15 秒超时，避免无限等待
            resp = requests.post(url, json=data, headers=headers, timeout=15)
            # 将响应体解析为 JSON 字典
            result = resp.json()
            # 检查业务响应码：status == 0 表示登录成功
            if result.get("status") == 0:
                # 从嵌套的 data 字典中提取 token
                # get 链式调用确保任何层级缺失都不会抛出 KeyError
                token = result.get("data", {}).get("token", "")
                # 通过信号将 token 发送回主线程
                self.success.emit(token)
            else:
                # 登录失败，提取错误信息
                # msg 字段包含服务器返回的可读错误描述
                msg = result.get("msg", "未知错误")
                # 通过信号将错误信息发送回主线程
                self.error.emit(msg)
        except Exception as e:
            # 捕获所有异常（网络错误、JSON 解析错误、KeyError 等）
            # 将异常信息转为字符串后通过 error 信号发送回主线程
            self.error.emit(str(e))


class ArknightsLoginApiDialog(QDialog):
    """明日方舟登录对话框 - API 版本

    不依赖 WebEngine 的轻量级登录对话框，通过 HTTP API 直接完成登录。

    特性：
    - 可编辑的下拉框选择已保存的账号，或手动输入新账号
    - 密码输入时自动隐藏字符（密码模式）
    - 支持记住密码（Base64 编码存储）
    - 后台线程执行网络请求，不阻塞 UI

    属性：
        _token (str or None): 登录成功后获取到的 token
        _closing (bool): 标记对话框是否正在关闭
        account_combo (QComboBox): 可编辑的账号下拉选择框
        password_input (QLineEdit): 密码输入框
        remember_cb (StyledCheckBox): "记住密码"复选框
        status_label (QLabel): 底部状态提示标签
        login_btn (QPushButton): 登录按钮
        _worker (_LoginWorker): 后台登录线程实例
    """

    def __init__(self, parent=None):
        """初始化 API 版登录对话框

        参数：
            parent (QWidget or None): 父窗口控件，传入 None 表示独立顶层窗口。

        UI 结构：
            标题标签
            账号输入区 [标签 | 下拉选择框]
            密码输入区 [标签 | 密码框]
            记住密码复选框
            状态提示标签
            按钮区 [弹性空间 | 取消 | 登录]
        """
        super().__init__(parent)  # 调用 QDialog 父类构造函数
        # 设置窗口标题
        self.setWindowTitle("明日方舟 - 登录鹰角账号")
        # 设置窗口最小尺寸，确保所有 UI 元素可见
        self.setMinimumSize(420, 320)
        # 设置窗口标志位：
        # 先获取当前标志位
        # & ~Qt.WindowType.WindowContextHelpButtonHint: 移除标题栏的帮助按钮（问号图标）
        # | Qt.WindowType.WindowCloseButtonHint: 确保留有关闭按钮
        # 组合后的效果：标准窗口，有标题栏和关闭按钮，但没有帮助按钮
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowContextHelpButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        # Token 存储，初始为 None
        self._token = None
        # 关闭标志位，用于在 closeEvent 中判断是否需要清理资源
        self._closing = False

        # 创建主垂直布局，间距 12px，内边距 20px
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(20, 20, 20, 20)

        # ========== 标题标签 ==========
        title = QLabel("登录鹰角账号")
        # 18px 粗体字号，突出显示
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        # 居中对齐
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # ========== 账号输入区 ==========
        # 创建水平布局，将标签和下拉框排列在同一行
        account_layout = QHBoxLayout()
        account_layout.addWidget(QLabel("账号:"))
        # 创建可编辑的下拉选择框
        self.account_combo = QComboBox()
        self.account_combo.setEditable(True)  # 允许用户手动输入新账号
        # 设置插入策略为 NoInsert：用户输入内容不会自动添加到下拉列表
        # 避免误输入的内容被永久保存到列表中
        self.account_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        # 最小宽度 250px，确保有足够的输入空间
        self.account_combo.setMinimumWidth(250)
        # 连接信号：当用户选择或输入新账号时触发回调
        # currentTextChanged 在文本变化时发出，包括手动输入和下拉选择
        self.account_combo.currentTextChanged.connect(self._on_account_selected)
        # 禁用自动补全功能：如果不禁用，输入一个数字可能就匹配到已保存的账号
        # 传入 None 表示移除默认的 Completer
        self.account_combo.setCompleter(None)
        account_layout.addWidget(self.account_combo)
        layout.addLayout(account_layout)

        # ========== 密码输入区 ==========
        password_layout = QHBoxLayout()
        password_layout.addWidget(QLabel("密码:"))
        # 创建密码输入框
        self.password_input = QLineEdit()
        # 占位提示文字，在输入框为空时显示
        self.password_input.setPlaceholderText("请输入密码")
        # 设置回显模式为 Password：输入的字符显示为圆点（●）而非明文
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        # 最小宽度 250px，与账号输入框保持一致
        self.password_input.setMinimumWidth(250)
        # 连接回车键信号：用户在密码框中按 Enter 键时触发登录
        self.password_input.returnPressed.connect(self._on_login)
        password_layout.addWidget(self.password_input)
        layout.addLayout(password_layout)

        # ========== 记住密码复选框 ==========
        # StyledCheckBox 是自定义的复选框控件，提供统一的视觉风格
        self.remember_cb = StyledCheckBox("记住密码")
        layout.addWidget(self.remember_cb)

        # ========== 状态提示标签 ==========
        self.status_label = QLabel("")  # 初始为空
        # 灰色小号字体
        self.status_label.setStyleSheet("color: #666; font-size: 12px;")
        # 居中对齐
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # ========== 底部按钮区 ==========
        btn_layout = QHBoxLayout()
        # 添加弹性空间，将按钮推到右侧
        btn_layout.addStretch()

        # 取消按钮：点击后关闭对话框并返回 Rejected
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedWidth(80)
        # reject() 是 QDialog 内置方法，关闭对话框并设置返回码为 QDialog.Rejected
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        # 登录按钮：蓝色背景、白色文字、粗体
        self.login_btn = QPushButton("登录")
        self.login_btn.setFixedWidth(80)
        # 三种状态的样式：
        # Normal: 蓝色背景
        # Hover: 深蓝色背景
        # Disabled: 灰色背景（登录中时禁用，防止重复点击）
        self.login_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8; color: white;
                font-weight: bold; border-radius: 4px;
                padding: 6px;
            }
            QPushButton:hover { background-color: #1557b0; }
            QPushButton:disabled { background-color: #ccc; }
        """)
        # 连接登录按钮点击信号到登录处理方法
        self.login_btn.clicked.connect(self._on_login)
        btn_layout.addWidget(self.login_btn)

        layout.addLayout(btn_layout)

        # ========== 初始化：加载已保存的账号列表 ==========
        self._load_saved_accounts()

    def closeEvent(self, event):
        """窗口关闭事件处理

        当用户点击窗口右上角的 X 关闭按钮时触发。
        需要清理后台线程资源，避免线程在对话框关闭后继续运行。

        参数：
            event (QCloseEvent): Qt 关闭事件对象。

        内部流程：
            1. 设置关闭标志位
            2. 检查后台线程是否在运行，如果是则终止并等待
            3. 调用 reject() 关闭对话框
            4. 接受关闭事件
        """
        # 标记对话框正在关闭
        self._closing = True
        # 检查后台线程是否存在且正在运行
        if hasattr(self, '_worker') and self._worker.isRunning():
            # terminate() 强制终止线程（注意：这不是安全的终止方式，
            # 但 requests 的 timeout 机制可以限制最长等待时间）
            self._worker.terminate()
            # wait() 阻塞主线程直到子线程真正结束，防止资源泄漏
            self._worker.wait()
        # 调用 reject() 关闭对话框，返回 QDialog.Rejected
        self.reject()
        # 接受关闭事件，允许窗口正常关闭
        event.accept()

    def _load_saved_accounts(self):
        """从本地配置中加载已保存的账号列表

        加载逻辑：
            1. 读取 "hypergryph_saved_accounts" 配置项（新版共享账号格式）
            2. 向后兼容读取 "arknights_saved_accounts"（旧版明日方舟专用格式）
            3. 将两个字典合并（旧版作为补充）
            4. 将账号列表填充到下拉选择框

        配置数据结构：
            hypergryph_saved_accounts = {
                "手机号1": "base64编码的密码",
                "手机号2": "base64编码的密码",
                ...
            }

        注意：
            使用 blockSignals(True/False) 包裹填充操作，
            避免每次 addItem 时都触发 _on_account_selected 信号。
        """
        from core.config import Config  # 延迟导入配置管理类
        config = Config()  # 创建配置实例
        # 读取共享的鹰角账号列表（明日方舟和终末地共用）
        saved_accounts = config.get("hypergryph_saved_accounts", {})
        # 兼容旧配置：读取明日方舟专用的旧格式账号列表
        old_arknights = config.get("arknights_saved_accounts", {})
        if old_arknights:
            # 将旧格式账号合并到共享列表中（旧账号不会覆盖同名的新账号）
            saved_accounts.update(old_arknights)

        # 屏蔽信号：在批量添加 item 期间，阻止 currentTextChanged 信号
        # 避免每次 addItem 都触发 _on_account_selected 导致不必要的密码加载
        self.account_combo.blockSignals(True)
        # 清空下拉框中的所有选项
        self.account_combo.clear()
        # 添加固定的"添加账号"选项（列表第一项）
        self.account_combo.addItem("添加账号")
        # 遍历所有已保存的账号，添加到下拉框
        for account in saved_accounts.keys():
            self.account_combo.addItem(account)
        # 恢复信号处理
        self.account_combo.blockSignals(False)

        # 如果有已保存的账号，自动选中第一个账号并勾选"记住密码"
        if saved_accounts:
            # setCurrentIndex(1) 选中第一个实际账号（index 0 是"添加账号"）
            self.account_combo.setCurrentIndex(1)
            # 自动勾选记住密码
            self.remember_cb.setChecked(True)

    def _on_account_selected(self, account):
        """账号选择变化时的回调处理

        当用户在下拉框中选择一个已保存的账号时，自动填充对应的密码。
        当用户选择"添加账号"或手动输入新账号时，清空密码框。

        参数：
            account (str): 当前选中/输入的账号文本。

        内部流程：
            1. 如果选中的是"添加账号"或为空，清空密码框
            2. 否则从配置中查找该账号对应的密码
            3. 密码是 Base64 编码的，需要解码后填入输入框
        """
        # 特殊选项检查：空字符串或"添加账号"时清空密码
        if not account or account == "添加账号":
            self.password_input.clear()
            return

        import base64  # 导入 Base64 编解码模块
        from core.config import Config
        config = Config()
        # 读取共享账号列表
        saved_accounts = config.get("hypergryph_saved_accounts", {})
        # 兼容旧格式
        old_arknights = config.get("arknights_saved_accounts", {})
        if old_arknights:
            saved_accounts.update(old_arknights)

        # 检查选中的账号是否在已保存列表中
        if account in saved_accounts:
            try:
                # 获取 Base64 编码的密码
                encoded_password = saved_accounts[account]
                # 解码流程：str -> bytes (encode UTF-8) -> bytes (base64 decode) -> str (decode UTF-8)
                password = base64.b64decode(encoded_password.encode('utf-8')).decode('utf-8')
                # 将解码后的明文密码填入输入框
                self.password_input.setText(password)
                # 自动勾选"记住密码"
                self.remember_cb.setChecked(True)
            except Exception:
                # 解码失败时清空密码框（可能是旧数据格式不兼容）
                self.password_input.clear()

    def _save_account(self):
        """保存当前账号和密码到本地配置

        密码使用 Base64 编码存储，提供基本的混淆（注意：不是真正的加密）。

        保存逻辑：
            1. 获取当前输入的账号和密码
            2. 如果勾选了"记住密码"，将密码 Base64 编码后保存
            3. 如果取消勾选，从配置中移除该账号
            4. 将更新后的账号列表写入配置文件

        安全注意：
            Base64 是编码不是加密，任何人都可以解码。
            这里只是为了避免明文存储密码，提供最基本的安全性。
        """
        import base64
        from core.config import Config
        config = Config()

        # 获取当前输入的账号（去除首尾空白字符）
        account = self.account_combo.currentText().strip()
        # 获取密码（不去除空白，密码可能包含前后空格）
        password = self.password_input.text()

        # 账号为空时不保存
        if not account:
            return

        # 读取当前已保存的账号列表
        saved_accounts = config.get("hypergryph_saved_accounts", {})

        if self.remember_cb.isChecked():
            # 勾选了"记住密码"：编码并保存
            # encode UTF-8: 字符串 -> 字节
            # b64encode: 字节 -> Base64 编码的字节
            # decode UTF-8: Base64 字节 -> 字符串（方便存储为 JSON）
            encoded_password = base64.b64encode(password.encode('utf-8')).decode('utf-8')
            saved_accounts[account] = encoded_password
        else:
            # 未勾选"记住密码"：如果该账号已保存则移除
            if account in saved_accounts:
                del saved_accounts[account]

        # 将更新后的账号列表写入配置
        config.set("hypergryph_saved_accounts", saved_accounts)
        # 持久化到磁盘
        config.save()

    def _on_login(self):
        """登录按钮点击处理

        执行登录前的输入验证，然后启动后台线程执行 API 请求。

        验证规则：
            1. 账号不能为空
            2. 密码不能为空
            3. 验证通过后禁用登录按钮（防止重复点击），启动后台线程

        UI 状态变化：
            - 登录前：按钮正常，显示"登录"
            - 登录中：按钮禁用，显示"登录中..."
            - 登录后：按钮恢复，根据结果显示状态信息
        """
        # 获取并清理输入内容
        account = self.account_combo.currentText().strip()
        password = self.password_input.text().strip()

        # 账号为空验证
        if not account:
            self.status_label.setText("请输入账号")
            # 将焦点设置到账号输入框，方便用户输入
            self.account_combo.setFocus()
            return

        # 密码为空验证
        if not password:
            self.status_label.setText("请输入密码")
            self.password_input.setFocus()
            return

        # 禁用登录按钮，防止重复点击
        self.login_btn.setEnabled(False)
        # 更新按钮文字，表示正在处理中
        self.login_btn.setText("登录中...")
        self.status_label.setText("正在登录...")

        # 创建后台登录线程
        self._worker = _LoginWorker(account, password)
        # 连接信号到槽函数：
        # success 信号 -> _on_login_success: 处理登录成功
        # error 信号 -> _on_login_error: 处理登录失败
        self._worker.success.connect(self._on_login_success)
        self._worker.error.connect(self._on_login_error)
        # 启动线程：start() 后 _LoginWorker.run() 会在新线程中执行
        self._worker.start()

    def _on_login_success(self, token):
        """登录成功回调

        当后台线程成功获取到 token 后，通过 success 信号触发此方法。

        参数：
            token (str): 登录成功后获取到的认证 token。

        内部流程：
            1. 保存 token 到实例变量
            2. 保存账号到本地配置
            3. 更新 UI 显示成功状态
            4. 延迟 500ms 后自动关闭对话框
        """
        # 保存 token 供外部通过 get_token() 方法获取
        self._token = token
        # 保存账号和密码到配置（如果勾选了"记住密码"）
        self._save_account()
        # 更新状态标签为绿色成功提示
        self.status_label.setText("✓ 登录成功！")
        self.status_label.setStyleSheet("color: #4CAF50; font-size: 12px; font-weight: bold;")
        # 恢复登录按钮状态
        self.login_btn.setEnabled(True)
        self.login_btn.setText("登录")
        # 延迟 500ms 后调用 self.accept() 关闭对话框
        # accept() 设置返回码为 QDialog.Accepted
        # 延迟是为了让用户看到成功提示信息
        QTimer.singleShot(500, self.accept)

    def _on_login_error(self, msg):
        """登录失败回调

        当后台线程登录失败时，通过 error 信号触发此方法。

        参数：
            msg (str): 错误信息，如"账号或密码错误"、网络超时等。

        UI 变化：
            - 状态标签显示红色错误信息
            - 登录按钮恢复可用状态
        """
        # 显示红色错误信息
        self.status_label.setText(f"登录出错: {msg}")
        self.status_label.setStyleSheet("color: #F44336; font-size: 12px;")
        # 恢复登录按钮
        self.login_btn.setEnabled(True)
        self.login_btn.setText("登录")

    def get_token(self) -> str:
        """获取登录成功后的认证 Token

        返回：
            str or None: 登录成功时返回 token 字符串；
                         未登录或获取失败时返回 None。

        使用方式：
            dialog = ArknightsLoginApiDialog()
            if dialog.exec() == QDialog.Accepted:
                token = dialog.get_token()
        """
        return self._token

    def get_error(self) -> str:
        """获取最近的错误信息

        返回：
            str: 错误信息字符串。此 API 版本始终返回空字符串，
                  因为错误信息通过状态标签直接显示在 UI 上。

        注意：此方法是为了与 WebEngine 版保持统一的接口。
        """
        return ""
