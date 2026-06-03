"""日志配置模块 - 统一日志格式与输出"""

import logging
import logging.handlers
import sys
from pathlib import Path


def setup_logging(log_dir: str = None, level: int = logging.INFO, app_name: str = "qian"):
    """配置全局日志

    Args:
        log_dir: 日志文件目录，None 则只输出到控制台
        level: 日志级别
        app_name: 应用名称，用于日志文件名
    """
    root = logging.getLogger()
    root.setLevel(level)

    # 避免重复添加 handler
    if root.handlers:
        return

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # 控制台 handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(level)
    console.setFormatter(formatter)
    root.addHandler(console)

    # 文件 handler（可选）
    if log_dir:
        log_path = Path(log_dir)
        log_path.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_path / f"{app_name}.log",
            maxBytes=2 * 1024 * 1024,  # 2MB
            backupCount=3,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
