"""终末地登录窗口 - 轻量版（使用系统浏览器）

本模块实现了明日方舟：终末地（Arknights: Endfield）登录对话框的轻量版本。
不使用 WebEngine 也不使用 API 直接登录，而是打开系统默认浏览器让用户手动
完成登录，然后手动复制 token 粘贴到应用中。

与明日方舟轻量版 (arknights_login_light.py) 的区别：
- 窗口标题为"终末地"
- 提供 get_framework_token() 和 get_token() 两个方法（兼容终末地接口）
- 布局和样式完全相同

设计理念：
- 最轻量的实现方式，不依赖 WebEngine 或 requests 库
- 适用于 WebEngine 不可用的环境
- 用户需要手动操作获取 token

使用流程：
1. 点击"打开鹰角官网登录"按钮
2. 在系统浏览器中登录鹰角账号
3. 按 F12 打开开发者工具
4. 在 Console 中执行: document.cookie.match(/token=([^;]+)/)?.[1]
5. 复制输出的 token，粘贴到应用输入框
6. 点击"确定"

依赖：
- webbrowser: Python 标准库，打开系统默认浏览器
- PySide6: Qt6 的 Python 绑定
"""

import webbrowser  # Python 标准库，跨平台打开默认浏览器
# 从 PySide6.QtWidgets 导入所需的 Qt 控件类
# QDialog: 模态对话框基类
# QVBoxLayout/HBoxLayout: 垂直/水平线性布局
# QLabel: 静态文本标签
# QPushButton: 可点击按钮
# QLineEdit: 单行文本输入框（用于粘贴 token）
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit
)
# Qt: 核心枚举类（包含窗口标志、光标形状等枚举值）
from PySide6.QtCore import Qt


class LoginLightDialog(QDialog):
    """终末地登录对话框 - 轻量版

    不使用任何嵌入式浏览器或 API 调用，完全依赖用户手动操作获取 token。

    UI 结构（从上到下）：
        标题标签（"获取鹰角账号Token"）
        操作步骤说明（5 步操作指南）
        打开浏览器按钮（蓝色主题）
        Token 输入区 [标签 | 输入框]
        按钮区 [弹性空间 | 取消 | 确定]
        底部提示标签（动态显示操作反馈）

    属性：
        _token (str or None): 用户输入的 token
        token_input (QLineEdit): token 输入框
        hint_label (QLabel): 底部提示标签
    """

    def __init__(self, parent=None):
        """初始化终末地轻量版登录对话框

        参数：
            parent (QWidget or None): 父窗口控件。

        与 API 版的区别：
            - 不需要输入账号密码
            - 不需要网络请求线程
            - 用户手动获取 token 后粘贴
            - 更轻量，启动更快
        """
        super().__init__(parent)  # 调用 QDialog 父类构造函数
        # 设置窗口标题
        self.setWindowTitle("终末地 - 登录获取Token")
        # 设置最小尺寸
        self.setMinimumSize(450, 300)
        # 移除标题栏的帮助按钮
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        # Token 存储
        self._token = None

        # 创建主垂直布局
        layout = QVBoxLayout(self)
        layout.setSpacing(12)  # 控件间距 12px
        layout.setContentsMargins(16, 16, 16, 16)  # 内边距 16px

        # ========== 标题标签 ==========
        title = QLabel("获取鹰角账号Token")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # ========== 操作步骤说明 ==========
        # 详细的 5 步操作指引，帮助用户了解如何获取 token
        steps = QLabel(
            "操作步骤：\n\n"                                    # 步骤标题
            "1. 点击下方按钮打开鹰角官网\n"                       # 第一步
            "2. 在网页中登录您的鹰角账号\n"                       # 第二步
            "3. 登录成功后，按 F12 打开开发者工具\n"              # 第三步
            "4. 在 Console 中输入以下代码并回车：\n"             # 第四步
            "   document.cookie.match(/token=([^;]+)/)?.[1]\n"  # JS 代码
            "5. 复制输出的token，粘贴到下方输入框"               # 第五步
        )
        steps.setStyleSheet("color: #333; font-size: 12px; line-height: 1.5;")
        # 启用自动换行
        steps.setWordWrap(True)
        layout.addWidget(steps)

        # ========== 打开浏览器按钮 ==========
        open_btn = QPushButton("打开鹰角官网登录")
        # 蓝色主题样式
        open_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8; color: white;
                padding: 10px; font-size: 14px; font-weight: bold;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #1557b0; }
        """)
        # 鼠标悬停时显示手型光标
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # 连接点击信号到浏览器打开方法
        open_btn.clicked.connect(self._open_browser)
        layout.addWidget(open_btn)

        # ========== Token 输入区 ==========
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Token:"))
        # 创建 token 输入框
        self.token_input = QLineEdit()
        self.token_input.setPlaceholderText("粘贴获取到的token...")
        self.token_input.setMinimumWidth(300)
        input_layout.addWidget(self.token_input)
        layout.addLayout(input_layout)

        # ========== 按钮区 ==========
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()  # 弹性空间

        # 取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedWidth(80)
        cancel_btn.clicked.connect(self.reject)  # 关闭对话框
        btn_layout.addWidget(cancel_btn)

        # 确定按钮（绿色主题）
        ok_btn = QPushButton("确定")
        ok_btn.setFixedWidth(80)
        # 绿色样式与蓝色的打开浏览器按钮区分
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

        # ========== 底部提示标签 ==========
        # 初始为空，后续显示操作反馈信息
        self.hint_label = QLabel("")
        self.hint_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.hint_label)

    def _open_browser(self):
        """打开系统默认浏览器访问鹰角官网

        使用 webbrowser 标准库打开系统默认浏览器。
        webbrowser.open() 在不同平台上的行为：
        - Windows: 使用 os.startfile 或注册的默认浏览器
        - macOS: 使用 open 命令
        - Linux: 使用 xdg-open 命令

        打开后用户需要手动在浏览器中完成登录，
        然后通过开发者工具获取 token。
        """
        # 鹰角官网用户中心 URL
        url = "https://user.hypergryph.com/"
        # 打开系统默认浏览器
        webbrowser.open(url)
        # 更新提示标签
        self.hint_label.setText("已在浏览器中打开，请登录后复制token")

    def _on_ok(self):
        """确定按钮点击处理

        验证用户输入的 token 有效性，通过后关闭对话框。

        验证规则：
            1. token 不能为空
            2. token 长度必须 >= 20 个字符（排除过短的无效输入）

        注意：验证通过后调用 self.accept() 关闭对话框，
        返回 QDialog.Accepted。调用方通过 exec() 的返回值判断是否成功。
        """
        # 获取并清理输入内容
        token = self.token_input.text().strip()
        # 空 token 验证
        if not token:
            self.hint_label.setText("请输入token")
            return

        # 长度验证：有效 token 通常长度远大于 20
        if len(token) < 20:
            self.hint_label.setText("token长度不正确，请重新获取")
            return

        # 验证通过：保存 token 并关闭对话框
        self._token = token
        self.accept()

    def get_framework_token(self) -> str:
        """获取用户输入的认证 Token（终末地专用接口名）

        返回：
            str or None: token 字符串或 None。

        使用方式：
            dialog = LoginLightDialog()
            if dialog.exec() == QDialog.Accepted:
                token = dialog.get_framework_token()
        """
        return self._token

    def get_token(self) -> str:
        """获取用户输入的认证 Token（通用接口名）

        返回：
            str or None: token 字符串或 None。

        注意：与 get_framework_token 返回相同的值，
        提供两种命名以兼容不同的调用方。
        """
        return self._token

    def get_error(self) -> str:
        """获取最近的错误信息

        返回：
            str: 始终返回空字符串，错误通过 hint_label 直接显示。

        统一接口方法，与 WebEngine 版和 API 版保持一致。
        """
        return ""
