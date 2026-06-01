"""打包脚本 - 使用 PyInstaller 打包成 exe"""

import os
import subprocess
import sys


def build():
    """打包成 exe"""
    print("开始打包...")

    # 确保 PyInstaller 已安装
    try:
        import PyInstaller
    except ImportError:
        print("正在安装 PyInstaller...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 项目根目录
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # PyInstaller 参数
    args = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",                    # 单文件
        "--windowed",                   # 无控制台窗口
        "--name=穷观阵",                  # exe名称
        f"--icon={os.path.join(base_dir, 'icon.ico')}" if os.path.exists(
            os.path.join(base_dir, 'icon.ico')
        ) else "",
        f"--add-data={os.path.join(base_dir, 'config.yaml')};.",
        f"--add-data={os.path.join(base_dir, 'ui', 'resources')};ui/resources",
        f"--add-data={os.path.join(base_dir, 'data', 'game_data')};data/game_data",
        f"--add-data={os.path.join(base_dir, 'fetchers', 'hypergryph', 'arknights_proxy.py')};fetchers/hypergryph",
        "--hidden-import=PySide6",
        "--hidden-import=matplotlib",
        "--hidden-import=sqlite3",
        "--hidden-import=yaml",
        "--hidden-import=openpyxl",
        "--hidden-import=requests",
        "--collect-all=matplotlib",
        os.path.join(base_dir, "main.py"),
    ]

    # 过滤空参数
    args = [a for a in args if a]

    print("执行命令:", " ".join(args))
    result = subprocess.run(args, cwd=base_dir)

    if result.returncode == 0:
        print("\n打包成功！")
        print(f"输出目录: {os.path.join(base_dir, 'dist')}")
    else:
        print("\n打包失败，请检查错误信息")


if __name__ == "__main__":
    build()
