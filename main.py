"""穷观阵 - 多游戏抽卡记录分析器"""

import sys
import os
import logging

# 确保项目根目录在 Python 路径中，并切换工作目录
if getattr(sys, 'frozen', False):
    # PyInstaller exe 模式
    _exe_dir = os.path.dirname(sys.executable)
    # onedir 模式下数据文件在 _internal 子目录中
    if os.path.exists(os.path.join(_exe_dir, "_internal", "config.yaml")):
        _project_dir = os.path.join(_exe_dir, "_internal")
    else:
        _project_dir = _exe_dir
else:
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

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    _force_light_palette(app)

    # 获取图标路径
    icon_path = os.path.join(_project_dir, "icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    font = QFont("Microsoft YaHei", 10)
    app.setFont(font)

    app.setApplicationName("穷观阵")
    app.setApplicationVersion("1.1.1")
    app.setOrganizationName("QianGuanZhen")

    window = MainWindow()
    window.show()

    logger.info("穷观阵已启动")
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
