"""穷观阵 - 多游戏抽卡记录分析器"""

import sys
import os
import logging

# 确保项目根目录在 Python 路径中，并切换工作目录
_project_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _project_dir)
os.chdir(_project_dir)

from core.logging_config import setup_logging

# 初始化日志：控制台 + 文件
setup_logging(
    log_dir=os.path.join(_project_dir, "data", "logs"),
    level=logging.INFO,
    app_name="qian",
)

logger = logging.getLogger(__name__)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon

from ui.main_window import MainWindow


def preload_webengine():
    """预加载 WebEngine 组件，避免登录时卡顿"""
    try:
        from PySide6.QtWebEngineWidgets import QWebEngineView
        from PySide6.QtWebEngineCore import QWebEngineProfile
        view = QWebEngineView()
        profile = QWebEngineProfile("Preload", view)
        view.setPage(profile.createPage(view))
        view.setUrl("about:blank")
        return view
    except Exception:
        logger.debug("WebEngine preload skipped (not installed or unavailable)")
        return None


def main():
    logger.info("穷观阵启动中...")

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)

    icon_path = os.path.join(os.path.dirname(__file__), "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    app.setApplicationName("穷观阵")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("QianGuanZhen")

    app._preload_view = preload_webengine()

    window = MainWindow()
    window.show()

    logger.info("穷观阵已启动")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
