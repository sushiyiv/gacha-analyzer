"""穷观阵 - 多游戏抽卡记录分析器"""

import sys
import os
import logging

# 确保项目根目录在 Python 路径中
if getattr(sys, 'frozen', False):
    _exe_dir = os.path.dirname(sys.executable)
    # 应用资源在 _internal；日志/用户数据放 exe 同级 data/
    if os.path.exists(os.path.join(_exe_dir, "_internal", "config.yaml")):
        _project_dir = os.path.join(_exe_dir, "_internal")
        _data_root = _exe_dir
    else:
        _project_dir = _exe_dir
        _data_root = _exe_dir
else:
    _project_dir = os.path.dirname(os.path.abspath(__file__))
    _data_root = _project_dir
sys.path.insert(0, _project_dir)
os.chdir(_project_dir)

from core.logging_config import setup_logging

# 初始化日志：控制台 + 文件
setup_logging(
    log_dir=os.path.join(_data_root, "data", "logs"),
    level=logging.INFO,
    app_name="qian",
)

logger = logging.getLogger(__name__)

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt, QTimer


def _global_excepthook(exc_type, exc_value, exc_tb):
    """全局异常钩子 - 捕获主线程未处理的异常"""
    logger.exception("未处理的异常")
    # 调用默认钩子（会弹出 Python 错误对话框）
    sys.__excepthook__(exc_type, exc_value, exc_tb)


def _qt_message_handler(msg_type, context, message):
    """Qt 消息处理器 - 捕获 Qt 内部的警告和错误"""
    if msg_type == 0:  # QtDebugMsg
        logger.debug("Qt: %s", message)
    elif msg_type == 1:  # QtInfoMsg
        logger.info("Qt: %s", message)
    elif msg_type == 2:  # QtWarningMsg
        logger.warning("Qt: %s", message)
    elif msg_type == 3:  # QtCriticalMsg
        logger.error("Qt: %s", message)
    elif msg_type == 4:  # QtFatalMsg
        logger.critical("Qt: %s", message)


from PySide6.QtGui import QFont, QIcon, QPalette, QColor


def _force_light_palette(app: QApplication):
    """强制使用浅色主题，不跟随系统深色模式"""
    palette = QPalette()
    light_colors = {
        QPalette.Window: "#f5f5f5",
        QPalette.WindowText: "#000000",
        QPalette.Base: "#ffffff",
        QPalette.AlternateBase: "#f5f5f5",
        QPalette.ToolTipBase: "#ffffff",
        QPalette.ToolTipText: "#000000",
        QPalette.Text: "#000000",
        QPalette.Button: "#e0e0e0",
        QPalette.ButtonText: "#000000",
        QPalette.BrightText: "#ffffff",
        QPalette.Link: "#1a73e8",
        QPalette.Highlight: "#1a73e8",
        QPalette.HighlightedText: "#ffffff",
        QPalette.PlaceholderText: "#999999",
        QPalette.Dark: "#c0c0c0",
        QPalette.Mid: "#c0c0c0",
        QPalette.Light: "#c0c0c0",
        QPalette.Midlight: "#c0c0c0",
        QPalette.Shadow: "#c0c0c0",
    }
    for group in (QPalette.Active, QPalette.Inactive, QPalette.Disabled):
        for role, color in light_colors.items():
            palette.setColor(group, role, QColor(color))
    app.setPalette(palette)


from ui.main_window import MainWindow


def main():
    logger.info("穷观阵启动中...")

    # 注册全局异常钩子
    sys.excepthook = _global_excepthook

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)

    # 安装 Qt 消息处理器
    from PySide6.QtCore import qInstallMessageHandler
    qInstallMessageHandler(_qt_message_handler)

    _force_light_palette(app)

    # 获取图标路径
    icon_path = os.path.join(_project_dir, "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    app.setApplicationName("穷观阵")
    app.setApplicationVersion("1.2.3")
    app.setOrganizationName("QianGuanZhen")

    window = MainWindow()
    window.show()

    logger.info("穷观阵已启动")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
