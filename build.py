"""穷观阵打包脚本"""

import shutil
import tempfile
from pathlib import Path

import PyInstaller.__main__

BASE_DIR = Path(__file__).resolve().parent
DIST_APP = BASE_DIR / "dist" / "穷观阵"
USER_DATA = DIST_APP / "data"

# 重建会删掉整个 dist/穷观阵，先暂存用户数据
stash = None
if USER_DATA.exists():
    stash = Path(tempfile.mkdtemp(prefix="qian_data_"))
    shutil.copytree(USER_DATA, stash / "data", dirs_exist_ok=True)
    print(f"stashed user data -> {stash / 'data'}")

try:
    PyInstaller.__main__.run([
        str(BASE_DIR / "main.py"),
        "--name=穷观阵",
        "--windowed",
        f"--icon={BASE_DIR / 'icon.ico'}",
        "--onedir",
        f"--add-data={BASE_DIR / 'data' / 'game_data'};data/game_data",
        f"--add-data={BASE_DIR / 'config.yaml'};.",
        f"--add-data={BASE_DIR / 'ui' / 'resources'};ui/resources",
        "--hidden-import=PySide6.QtWidgets",
        "--hidden-import=PySide6.QtCore",
        "--hidden-import=PySide6.QtGui",
        "--hidden-import=matplotlib",
        "--hidden-import=matplotlib.backends.backend_qtagg",
        "--noconfirm",
        f"--distpath={BASE_DIR / 'dist'}",
        f"--workpath={BASE_DIR / 'build'}",
    ])
finally:
    if stash and (stash / "data").exists():
        USER_DATA.parent.mkdir(parents=True, exist_ok=True)
        if USER_DATA.exists():
            shutil.rmtree(USER_DATA)
        shutil.copytree(stash / "data", USER_DATA)
        print(f"restored user data -> {USER_DATA}")
    if stash:
        shutil.rmtree(stash, ignore_errors=True)
