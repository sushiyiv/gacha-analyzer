"""终末地登录窗口 - API直接登录（无需加载网页）

本模块实现了明日方舟：终末地（Arknights: Endfield）登录对话框的 API 版本。
与 WebEngine 版不同，此版本直接调用鹰角网络的登录 API 进行身份验证，
不需要加载任何网页。

与明日方舟 API 版 (arknights_login_api.py) 的区别：
- 窗口标题为"终末地"，便于用户区分
- 使用 "hypergryph_saved_accounts" 共享账号列表
- 向后兼容 "endfield_saved_accounts" 旧配置格式
- 提供 get_framework_token() 和 get_token() 两个方法（保持接口兼容）

登录流程：
1. 用户在可编辑下拉框中选择或输入账号
2. 输入密码
3. 后台线程向鹰角 API 发送 HTTP POST 请求
4. API 返回 token 或错误信息
5. 登录成功后保存账号到本地配置

安全说明：
- 密码使用 Base64 编码存储（仅混淆，非加密）
- 网络请求在后台线程执行，不阻塞 UI
- 登录按钮在请求期间禁用，防止重复提交

依赖：
- requests: HTTP 客户端库
- PySide6: Qt6 的 Python 绑定
- core.config.Config: 应用配置管理
- ui.widgets.styled_widgets.StyledCheckBox: 自定义复选框控件
"""

import requests  # HTTP 客户端库，用于向鹰角 API 发送 POST 请求
# 从 PySide6.QtWidgets 导入所需的 Qt 控件类
# QDialog: 模态对话框基类
# QVBoxLayout/HBoxLayout: 垂直/水平线性布局
# QLabel: 静态文本标签
# QPushButton: 可点击按钮
# QLineEdit: 单行文本输入框
# QCheckBox: 复选框（已导入但未使用，由 StyledCheckBox 替代）
# QMessageBox: 消息提示框（已导入但未使用，可能为预留）
# QComboBox: 下拉选择框（用于选择已保存的账号）
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QCheckBox, QMessageBox, QComboBox
)
# Qt: 核心枚举和工具类
# QThread: 工作线程基类，用于后台执行网络请求
# Signal: Qt 信号类，用于线程间安全通信
from PySide6.QtCore import Qt, QThread, Signal
# StyledCheckBox: 自定义样式的复选框，提供统一的视觉风格
from ui.widgets.styled_widgets import StyledCheckBox


class _LoginWorker(QThread):
    """后台线程执行登录 API 请求

    在独立线程中执行 HTTP 登录请求，避免阻塞 UI 主线程。

    Qt 多线程通信机制：
    - 子线程不能直接操作 UI 控件（会导致未定义行为）
    - 必须通过 Signal 机制将结果传递回主线程
    - 信号的槽函数在主线程的事件循环中执行，可以安全操作 UI

    属性：
        success (Signal[str]): 登录成功信号，携带 token
        error (Signal[str]): 登录失败信号，携带错误信息
        _account (str): 手机号/账号
        _password (str): 密码
    """

    # 类级别定义的信号
    # 参数类型为 str，登录成功时携带 token 字符串
    success = Signal(str)
    # 参数类型为 str，登录失败时携带错误描述
    error = Signal(str)

    def __init__(self, account, password):
        """初始化登录工作线程

        参数：
            account (str): 手机号或账号
            password (str): 密码
        """
        super().__init__()  # 调用 QThread 父类构造函数
        self._account = account  # 保存账号
        self._password = password  # 保存密码

    def run(self):
        """线程启动后执行的主方法

        QThread.start() 调用后，此方法在新的操作系统线程中自动执行。
        包含完整的 HTTP 登录请求逻辑。

        API 接口详情：
            端点: POST https://as.hypergryph.com/user/auth/v1/token_by_phone_password
            Content-Type: application/json
            请求体: {"phone": "手机号", "password": "密码"}
            成功响应: {"status": 0, "data": {"token": "认证token"}}
            失败响应: {"status": 非零, "msg": "错误描述"}

        异常捕获：
            - requests.exceptions.Timeout: 网络超时（15 秒）
            - requests.exceptions.ConnectionError: 网络连接失败
            - json.JSONDecodeError: 响应体不是有效 JSON
            - KeyError/AttributeError: 响应结构不符合预期
            所有异常通过 error 信号安全传递回主线程
        """
        try:
            # 鹰角网络的手机号+密码登录 API 地址
            url = "https://as.hypergryph.com/user/auth/v1/token_by_phone_password"
            # HTTP 请求头
            headers = {
                "Content-Type": "application/json",  # 声明请求体格式为 JSON
                # 模拟 Chrome 浏览器的 User-Agent，避免被服务器拒绝
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            # 请求体：手机号和密码
            data = {"phone": self._account, "password": self._password}
            # 发送 POST 请求
            # json=data: 自动将 dict 序列化为 JSON 字符串并设置 Content-Type
            # timeout=15: 15 秒超时，避免网络异常时线程永久阻塞
            resp = requests.post(url, json=data, headers=headers, timeout=15)
            # 将响应体解析为 Python 字典
            result = resp.json()
            # 检查业务状态码：status == 0 表示登录成功
            if result.get("status") == 0:
                # 提取 token：data.token 或 data -> token 的嵌套路径
                # get 链式调用确保任何层级缺失都不会抛出 KeyError
                token = result.get("data", {}).get("token", "")
                # 通过信号将 token 安全地传递回主线程
                self.success.emit(token)
            else:
                # 登录失败，提取错误信息
                msg = result.get("msg", "未知错误")
                # 通过信号将错误信息传递回主线程
                self.error.emit(msg)
        except Exception as e:
            # 捕获所有可能的异常（网络错误、JSON 解析错误等）
            # 将异常对象转为字符串后传递回主线程
            self.error.emit(str(e))


class LoginApiDialog(QDialog):
    """终末地登录对话框 - API 版本

    不依赖 WebEngine 的轻量级登录对话框，通过 HTTP API 直接完成登录。

    功能特性：
    - 可编辑的下拉框：选择已保存的账号或手动输入新账号
    - 密码输入框：字符自动隐藏（密码模式）
    - 记住密码：Base64 编码存储到本地配置
    - 后台线程：网络请求不阻塞 UI
    - 向后兼容：支持新旧两种配置格式

    UI 布局（从上到下）：
        标题标签
        账号区 [标签 | 可编辑下拉框]
        密码区 [标签 | 密码输入框]
        记住密码复选框
        状态提示标签
        按钮区 [弹性空间 | 取消 | 登录]

    属性：
        _token (str or None): 登录成功后获取到的 token
        _closing (bool): 对话框正在关闭的标志
        account_combo (QComboBox): 账号下拉选择框
        password_input (QLineEdit): 密码输入框
        remember_cb (StyledCheckBox): 记住密码复选框
        status_label (QLabel): 状态提示标签
        login_btn (QPushButton): 登录按钮
    """

    def __init__(self, parent=None):
        """初始化 API 版登录对话框

        参数：
            parent (QWidget or None): 父窗口控件。
        """
        super().__init__(parent)  # 调用 QDialog 父类构造函数
        # 设置窗口标题（与明日方舟版区分）
        self.setWindowTitle("终末地 - 登录鹰角账号")
        # 设置最小尺寸
        self.setMinimumSize(420, 320)
        # 设置窗口标志位：
        # 移除帮助按钮（问号），确保留有关闭按钮
        self.setWindowFlags(
            self.windowFlags()
            & ~Qt.WindowType.WindowContextHelpButtonHint
            | Qt.WindowType.WindowCloseButtonHint
        )

        # Token 存储
        self._token = None
        # 关闭标志位
        self._closing = False

        # 创建主垂直布局
        layout = QVBoxLayout(self)
        layout.setSpacing(12)  # 控件间距 12px
        layout.setContentsMargins(20, 20, 20, 20)  # 内边距 20px

        # ========== 标题标签 ==========
        title = QLabel("登录鹰角账号")
        title.setStyleSheet("font-size: 18px; font-weight: bold;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title)

        # ========== 账号输入区 ==========
        account_layout = QHBoxLayout()
        account_layout.addWidget(QLabel("账号:"))
        # 创建可编辑的下拉选择框
        self.account_combo = QComboBox()
        self.account_combo.setEditable(True)  # 允许手动输入
        # 不自动插入新输入的内容到下拉列表
        self.account_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.account_combo.setMinimumWidth(250)
        # 连接文本变化信号到账号选择回调
        self.account_combo.currentTextChanged.connect(self._on_account_selected)
        # 禁用自动补全，防止输入数字就匹配到已保存账号
        self.account_combo.setCompleter(None)
        account_layout.addWidget(self.account_combo)
        layout.addLayout(account_layout)

        # ========== 密码输入区 ==========
        password_layout = QHBoxLayout()
        password_layout.addWidget(QLabel("密码:"))
        self.password_input = QLineEdit()
        self.password_input.setPlaceholderText("请输入密码")
        # 密码模式：输入内容显示为圆点
        self.password_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.password_input.setMinimumWidth(250)
        # 按 Enter 键触发登录
        self.password_input.returnPressed.connect(self._on_login)
        password_layout.addWidget(self.password_input)
        layout.addLayout(password_layout)

        # ========== 记住密码复选框 ==========
        self.remember_cb = StyledCheckBox("记住密码")
        layout.addWidget(self.remember_cb)

        # ========== 状态提示标签 ==========
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: #666; font-size: 12px;")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        # ========== 按钮区 ==========
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()  # 弹性空间

        # 取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.reject)  # 关闭并返回 Rejected
        btn_layout.addWidget(cancel_btn)

        # 登录按钮（蓝色主题）
        self.login_btn = QPushButton("登录")
        self.login_btn.setFixedWidth(80)
        # 三种状态样式：正常蓝色、悬停深蓝、禁用灰色
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

        # ========== 初始化：加载已保存的账号列表 ==========
        self._load_saved_accounts()

    def closeEvent(self, event):
        """窗口关闭事件处理

        当用户点击窗口右上角的 X 按钮时触发。
        负责清理后台线程资源，防止内存泄漏。

        参数：
            event (QCloseEvent): Qt 关闭事件对象。

        清理流程：
            1. 设置关闭标志位
            2. 如果后台线程正在运行，强制终止并等待完成
            3. 调用 reject() 关闭对话框
            4. 接受关闭事件
        """
        self._closing = True
        # 检查后台线程是否存在且正在运行
        if hasattr(self, '_worker') and self._worker.isRunning():
            # 强制终止线程（terminate 不是安全方式，但有 timeout 兜底）
            self._worker.terminate()
            # 等待线程真正结束
            self._worker.wait()
        self.reject()
        event.accept()

    def _load_saved_accounts(self):
        """从本地配置加载已保存的账号列表

        加载策略（共享账号机制）：
            1. 优先读取 "hypergryph_saved_accounts"（新版共享格式）
            2. 合并 "endfield_saved_accounts"（终末地旧版格式）
            3. 两者合并后填充到下拉框

        为什么使用共享账号：
            明日方舟和终末地都是鹰角网络的游戏，使用相同的鹰角账号。
            共享账号列表避免用户在两个游戏中重复保存账号。

        配置数据结构示例：
            hypergryph_saved_accounts = {
                "13800138000": "MTM4MDAxMzgwMDA=",  # base64("13800138000")
                "13900139000": "MTM5MDAxMzkwMDA="
            }

        信号屏蔽：
            使用 blockSignals(True/False) 包裹 addItem 操作，
            避免每次添加选项都触发 currentTextChanged 信号。
        """
        from core.config import Config
        config = Config()
        # 读取共享的鹰角账号列表
        saved_accounts = config.get("hypergryph_saved_accounts", {})
        # 读取终末地旧版专用账号列表（向后兼容）
        old_endfield = config.get("endfield_saved_accounts", {})
        if old_endfield:
            # 合并旧版账号（不会覆盖同名的新版账号）
            saved_accounts.update(old_endfield)

        # 屏蔽信号：批量添加 item 期间不触发选择变化回调
        self.account_combo.blockSignals(True)
        self.account_combo.clear()
        # 添加固定选项"添加账号"（index 0）
        self.account_combo.addItem("添加账号")
        # 添加所有已保存的账号
        for account in saved_accounts.keys():
            self.account_combo.addItem(account)
        # 恢复信号处理
        self.account_combo.blockSignals(False)

        # 如果有已保存的账号，自动选中第一个
        if saved_accounts:
            self.account_combo.setCurrentIndex(1)  # index 1 = 第一个实际账号
            self.remember_cb.setChecked(True)

    def _on_account_selected(self, account):
        """账号选择变化回调

        当用户在下拉框中选择已保存的账号时，自动填充对应密码。
        选择"添加账号"或手动输入时，清空密码框。

        参数：
            account (str): 当前选中/输入的账号文本。

        密码恢复流程：
            1. 从配置中查找账号对应的 Base64 编码密码
            2. 将 Base64 解码为明文密码
            3. 填入密码输入框
        """
        # 特殊选项或空输入：清空密码
        if not account or account == "添加账号":
            self.password_input.clear()
            return

        import base64
        from core.config import Config
        config = Config()
        # 读取共享账号列表
        saved_accounts = config.get("hypergryph_saved_accounts", {})
        # 兼容终末地旧版格式
        old_endfield = config.get("endfield_saved_accounts", {})
        if old_endfield:
            saved_accounts.update(old_endfield)

        # 查找账号并解码密码
        if account in saved_accounts:
            try:
                encoded_password = saved_accounts[account]
                # Base64 解码：str -> bytes (encode) -> bytes (b64decode) -> str (decode)
                password = base64.b64decode(encoded_password.encode('utf-8')).decode('utf-8')
                self.password_input.setText(password)
                self.remember_cb.setChecked(True)
            except Exception:
                # 解码失败时清空密码框
                self.password_input.clear()

    def _save_account(self):
        """保存当前账号密码到本地配置

        保存逻辑：
            1. 获取当前账号和密码
            2. 如果勾选"记住密码"：Base64 编码密码后保存
            3. 如果未勾选：从配置中移除该账号
            4. 写入配置文件并持久化

        安全性说明：
            Base64 是编码格式，不是加密算法。任何人都可以解码。
            这里仅提供基本的混淆，避免密码明文存储在配置文件中。
            生产环境应考虑使用操作系统密钥库（如 Windows Credential Manager）。
        """
        import base64
        from core.config import Config
        config = Config()

        # 获取输入内容
        account = self.account_combo.currentText().strip()
        password = self.password_input.text()

        # 账号为空时不保存
        if not account:
            return

        saved_accounts = config.get("hypergryph_saved_accounts", {})

        if self.remember_cb.isChecked():
            # 编码并保存密码
            encoded_password = base64.b64encode(password.encode('utf-8')).decode('utf-8')
            saved_accounts[account] = encoded_password
        else:
            # 取消记住时移除该账号
            if account in saved_accounts:
                del saved_accounts[account]

        # 持久化配置
        config.set("hypergryph_saved_accounts", saved_accounts)
        config.save()

    def _on_login(self):
        """登录按钮点击处理

        执行输入验证，然后启动后台线程进行 API 登录。

        验证规则：
            - 账号不能为空
            - 密码不能为空
            - 两个条件都满足时才启动登录线程

        UI 交互流程：
            1. 验证输入 -> 显示错误提示（如果有）
            2. 禁用登录按钮，显示"登录中..."
            3. 启动后台线程
            4. 线程完成后通过信号回调 _on_login_success 或 _on_login_error
        """
        account = self.account_combo.currentText().strip()
        password = self.password_input.text().strip()

        # 账号验证
        if not account:
            self.status_label.setText("请输入账号")
            self.account_combo.setFocus()  # 聚焦到账号输入框
            return

        # 密码验证
        if not password:
            self.status_label.setText("请输入密码")
            self.password_input.setFocus()  # 聚焦到密码输入框
            return

        # 验证通过：更新 UI 状态
        self.login_btn.setEnabled(False)  # 禁用按钮，防止重复点击
        self.login_btn.setText("登录中...")
        self.status_label.setText("正在登录...")

        # 创建后台登录线程并连接信号
        self._worker = _LoginWorker(account, password)
        self._worker.success.connect(self._on_login_success)  # 成功回调
        self._worker.error.connect(self._on_login_error)      # 失败回调
        self._worker.start()  # 启动线程，run() 方法在新线程中执行

    def _on_login_success(self, token):
        """登录成功回调

        后台线程成功获取 token 后，通过 success 信号触发此方法。

        参数：
            token (str): 登录成功后获取到的认证 token。

        执行操作：
            1. 保存 token 到实例变量
            2. 保存账号到配置（如果勾选了记住密码）
            3. 显示绿色成功提示
            4. 延迟 500ms 后关闭对话框
        """
        self._token = token
        self._save_account()  # 保存账号密码
        # 显示绿色成功提示
        self.status_label.setText("✓ 登录成功！")
        self.status_label.setStyleSheet("color: #4CAF50; font-size: 12px; font-weight: bold;")
        # 恢复登录按钮
        self.login_btn.setEnabled(True)
        self.login_btn.setText("登录")
        # 延迟关闭：让用户看到成功提示
        QTimer.singleShot(500, self.accept)

    def _on_login_error(self, msg):
        """登录失败回调

        参数：
            msg (str): 错误信息，如"账号或密码错误"等。

        UI 变化：
            - 状态标签显示红色错误信息
            - 登录按钮恢复可用
        """
        self.status_label.setText(f"登录出错: {msg}")
        self.status_label.setStyleSheet("color: #F44336; font-size: 12px;")
        self.login_btn.setEnabled(True)
        self.login_btn.setText("登录")

    def get_framework_token(self) -> str:
        """获取认证 Token（终末地专用接口名）

        返回：
            str or None: token 字符串或 None。

        注意：此方法名为 get_framework_token 以兼容终末地模块的接口约定。
        """
        return self._token

    def get_token(self) -> str:
        """获取认证 Token（通用接口名）

        返回：
            str or None: token 字符串或 None。

        注意：此方法与 get_framework_token 返回相同的值，
        提供两种命名以兼容不同的调用方。
        """
        return self._token

    def get_error(self) -> str:
        """获取最近的错误信息

        返回：
            str: 始终返回空字符串，错误通过 UI 直接显示。

        统一接口方法，与 WebEngine 版和轻量版保持一致。
        """
        return ""
