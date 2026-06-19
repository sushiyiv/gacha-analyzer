"""明日方舟登录窗口 - 轻量版（使用系统浏览器）

本模块实现了明日方舟（Arknights）登录对话框的轻量版本，不使用 WebEngine
也不使用 API 直接登录，而是打开系统默认浏览器让用户手动完成登录，
然后手动复制 token 粘贴到应用中。

设计理念：
- 最轻量的实现方式，不依赖 WebEngine 或 requests 库
- 适用于 WebEngine 不可用的环境（如缺少 Chromium 依赖）
- 完全依赖用户手动操作，流程相对简单但需要用户配合

使用流程：
1. 用户点击"打开鹰角官网登录"按钮
2. 系统浏览器打开鹰角官网登录页面
3. 用户在浏览器中登录账号
4. 用户按 F12 打开开发者工具，在 Console 中执行 JavaScript 获取 token
5. 用户将获取到的 token 粘贴到应用的输入框中
6. 点击"确定"按钮完成

依赖：
- webbrowser: Python 标准库，用于打开系统默认浏览器
- PySide6: Qt6 的 Python 绑定，提供 GUI 框架
"""

import webbrowser  # Python 标准库，提供跨平台的浏览器打开功能
# 从 PySide6.QtWidgets 导入所需的 Qt 控件类
# QDialog: 模态对话框基类
# QVBoxLayout/HBoxLayout: 垂直/水平线性布局
# QLabel: 静态文本标签
# QPushButton: 可点击按钮
# QLineEdit: 单行文本输入框（用于粘贴 token）
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit
)
# Qt: 核心枚举和工具类（包含窗口标志、光标形状等）
from PySide6.QtCore import Qt


class ArknightsLoginLightDialog(QDialog):
    """明日方舟登录对话框 - 轻量版

    不使用任何嵌入式浏览器或 API 调用，完全依赖用户手动操作获取 token。

    UI 结构：
        标题标签
        操作步骤说明
        打开浏览器按钮
        Token 输入区 [标签 | 输入框]
        按钮区 [弹性空间 | 取消 | 确定]
        底部提示标签

    属性：
        _token (str or None): 用户输入的 token，初始为 None
        token_input (QLineEdit): token 输入框
        hint_label (QLabel): 底部操作提示标签
    """

    def __init__(self, parent=None):
        """初始化轻量版登录对话框

        参数：
            parent (QWidget or None): 父窗口控件，传入 None 表示独立顶层窗口。

        与 WebEngine 版的区别：
            - 不创建 QWebEngineView，内存占用极小
            - 不需要 Chromium 内核，启动速度快
            - 用户需要手动操作获取 token
        """
        super().__init__(parent)  # 调用 QDialog 父类构造函数
        # 设置窗口标题
        self.setWindowTitle("明日方舟 - 登录获取Token")
        # 设置最小尺寸
        self.setMinimumSize(450, 300)
        # 移除标题栏的帮助按钮（问号图标），只保留关闭按钮
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        # Token 存储变量
        self._token = None

        # 创建主垂直布局，间距 12px，内边距 16px
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(16, 16, 16, 16)

        # ========== 标题标签 ==========
        title = QLabel("获取鹰角账号Token")
        # 16px 粗体字号
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        # ========== 操作步骤说明 ==========
        # 多行文本标签，详细说明获取 token 的步骤
        # 使用 \n\n 分隔段落，增加可读性
        steps = QLabel(
            "操作步骤：\n\n"                                    # 标题行
            "1. 点击下方按钮打开鹰角官网\n"                       # 第一步
            "2. 在网页中登录您的鹰角账号\n"                       # 第二步
            "3. 登录成功后，按 F12 打开开发者工具\n"              # 第三步
            "4. 在 Console 中输入以下代码并回车：\n"             # 第四步
            "   document.cookie.match(/token=([^;]+)/)?.[1]\n"  # 第四步的 JS 代码
            "5. 复制输出的token，粘贴到下方输入框"               # 第五步
        )
        # 灰色文字，12px 字号，行高 1.5 倍
        steps.setStyleSheet("color: #333; font-size: 12px; line-height: 1.5;")
        # 启用自动换行，当文字超出控件宽度时自动换行
        steps.setWordWrap(True)
        layout.addWidget(steps)

        # ========== 打开浏览器按钮 ==========
        open_btn = QPushButton("打开鹰角官网登录")
        # 蓝色背景样式，与鹰角品牌色调一致
        open_btn.setStyleSheet("""
            QPushButton {
                background-color: #1a73e8; color: white;
                padding: 10px; font-size: 14px; font-weight: bold;
                border-radius: 6px;
            }
            QPushButton:hover { background-color: #1557b0; }
        """)
        # 设置鼠标悬停时的光标为手型，提示用户这是可点击的按钮
        open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        # 连接点击信号到 _open_browser 方法
        open_btn.clicked.connect(self._open_browser)
        layout.addWidget(open_btn)

        # ========== Token 输入区 ==========
        # 水平布局，标签和输入框在同一行
        input_layout = QHBoxLayout()
        input_layout.addWidget(QLabel("Token:"))
        # 创建 token 输入框
        self.token_input = QLineEdit()
        # 占位提示文字
        self.token_input.setPlaceholderText("粘贴获取到的token...")
        # 最小宽度 300px，确保有足够的输入空间
        self.token_input.setMinimumWidth(300)
        input_layout.addWidget(self.token_input)
        layout.addLayout(input_layout)

        # ========== 底部按钮区 ==========
        btn_layout = QHBoxLayout()
        # 弹性空间将按钮推到右侧
        btn_layout.addStretch()

        # 取消按钮
        cancel_btn = QPushButton("取消")
        cancel_btn.setFixedWidth(80)
        # reject() 关闭对话框，返回 QDialog.Rejected
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        # 确定按钮：绿色背景，表示确认操作
        ok_btn = QPushButton("确定")
        ok_btn.setFixedWidth(80)
        # 绿色主题样式（与登录按钮的蓝色主题区分）
        ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50; color: white;
                font-weight: bold; border-radius: 4px;
            }
            QPushButton:hover { background-color: #388E3C; }
        """)
        # 连接点击信号到 _on_ok 方法
        ok_btn.clicked.connect(self._on_ok)
        btn_layout.addWidget(ok_btn)

        layout.addLayout(btn_layout)

        # ========== 底部提示标签 ==========
        # 初始为空，后续根据用户操作显示提示信息
        self.hint_label = QLabel("")
        # 浅灰色小号字体
        self.hint_label.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(self.hint_label)

    def _open_browser(self):
        """打开系统默认浏览器访问鹰角官网

        使用 Python 标准库 webbrowser 模块打开系统默认浏览器，
        导航到鹰角账号登录页面。

        注意：
            webbrowser.open() 在不同操作系统上的行为：
            - Windows: 打开默认浏览器（如 Chrome、Edge 等）
            - macOS: 打开默认浏览器
            - Linux: 使用 xdg-open 或默认浏览器

        打开后用户需要手动在浏览器中完成登录操作。
        """
        # 鹰角官网用户中心 URL
        url = "https://user.hypergryph.com/"
        # 使用系统默认浏览器打开 URL
        webbrowser.open(url)
        # 更新底部提示标签，告知用户浏览器已打开
        self.hint_label.setText("已在浏览器中打开，请登录后复制token")

    def _on_ok(self):
        """确定按钮点击处理

        验证用户输入的 token 是否有效，然后关闭对话框。

        验证规则：
            1. token 不能为空
            2. token 长度必须 >= 20 个字符（过短说明不是有效的 token）

        内部流程：
            1. 获取输入框内容并去除首尾空白
            2. 验证非空和长度
            3. 验证通过则保存 token 并关闭对话框
            4. 验证失败则显示错误提示
        """
        # 获取输入的 token 并去除首尾空白字符
        token = self.token_input.text().strip()
        # 空 token 验证
        if not token:
            self.hint_label.setText("请输入token")
            return

        # token 长度验证：有效的鹰角 token 通常长度远大于 20
        if len(token) < 20:
            self.hint_label.setText("token长度不正确，请重新获取")
            return

        # 保存 token
        self._token = token
        # 关闭对话框，返回 QDialog.Accepted
        self.accept()

    def get_token(self) -> str:
        """获取用户输入的认证 Token

        返回：
            str or None: 用户成功输入并验证通过的 token 字符串；
                         未输入或验证失败时返回 None。

        使用方式：
            dialog = ArknightsLoginLightDialog()
            if dialog.exec() == QDialog.Accepted:
                token = dialog.get_token()
        """
        return self._token

    def get_error(self) -> str:
        """获取最近的错误信息

        返回：
            str: 始终返回空字符串，因为错误通过 hint_label 直接显示在 UI 上。

        注意：此方法是为了与 WebEngine 版保持统一的接口。
        """
        return ""
