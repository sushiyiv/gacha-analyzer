"""穷观阵打包脚本"""

import PyInstaller.__main__
import os

# 获取项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PyInstaller.__main__.run([
    os.path.join(BASE_DIR, "main.py"),
    "--name=穷观阵",
    "--windowed",  # 无控制台窗口
    f"--icon={os.path.join(BASE_DIR, 'icon.ico')}",
    "--onedir",  # 目录模式，包含 _internal
    f"--add-data={os.path.join(BASE_DIR, 'data', 'game_data')};data/game_data",
    f"--add-data={os.path.join(BASE_DIR, 'config.yaml')};.",
    "--hidden-import=PySide6.QtWidgets",
    "--hidden-import=PySide6.QtCore",
    "--hidden-import=PySide6.QtGui",
    "--hidden-import=matplotlib",
    "--hidden-import=matplotlib.backends.backend_qtagg",
    "--noconfirm",  # 覆盖已有输出
    f"--distpath={os.path.join(BASE_DIR, 'dist')}",
    f"--workpath={os.path.join(BASE_DIR, 'build')}",
])
