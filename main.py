"""穷观阵 - 多游戏抽卡记录分析器"""

import sys
import os

# 确保项目根目录在 Python 路径中，并切换工作目录
_project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _project_dir)
os.chdir(_project_dir)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon

from ui.main_window import MainWindow


def preload_webengine():
    """预加载 WebEngine 组件，避免登录时卡顿"""
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import QWebEngineProfile
        # 创建一个临时的 WebEngineView 来预加载
        # 这会触发 Chromium 引擎的初始化
        view = QWebEngineView()
        profile = QWebEngineProfile("Preload", view)
        view.setPage(profile.createPage(view))
        # 加载一个空白页面来完成初始化
        view.setUrl("about:blank")
        return view  # 返回引用防止被垃圾回收
    except Exception:
        return None


def main():
    # 高DPI支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)

    # 设置应用图标
    icon_path = os.path.join(os.path.dirname(__file__), "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    # 设置全局字体
    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    # 设置应用信息
    app.setApplicationName("穷观阵")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("QianGuanZhen")

    # 预加载 WebEngine（在后台完成初始化）
    app._preload_view = preload_webengine()

    # 创建并显示主窗口
    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
