"""配置管理模块"""

import os
import yaml
from pathlib import Path


class Config:
    """应用配置管理"""

    _instance = None
    _config = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if self._config is None:
            self._base_dir = Path(__file__).parent.parent
            self._config_path = self._base_dir / "config.yaml"
            self._user_config_path = self._base_dir / "data" / "user_config.yaml"
            self._config = {}
            self._load()

    def _load(self):
        """加载配置"""
        # 加载默认配置
        if self._config_path.exists():
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._config = yaml.safe_load(f) or {}

        # 加载用户配置覆盖
        if self._user_config_path.exists():
            with open(self._user_config_path, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
                self._deep_merge(self._config, user_config)

    def _deep_merge(self, base, override):
        """深度合并字典"""
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def get(self, key, default=None):
        """获取配置值，支持点号分隔的路径"""
        keys = key.split(".")
        value = self._config
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
            else:
                return default
            if value is None:
                return default
        return value

    def set(self, key, value):
        """设置配置值"""
        keys = key.split(".")
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def save(self):
        """保存用户配置"""
        self._user_config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._user_config_path, "w", encoding="utf-8") as f:
            yaml.dump(self._config, f, allow_unicode=True, default_flow_style=False)

    @property
    def base_dir(self):
        return self._base_dir

    @property
    def db_path(self):
        path = self._base_dir / self.get("database_path", "data/gacha_records.db")
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    @property
    def backup_dir(self):
        path = self._base_dir / self.get("backup_dir", "data/backups")
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    @property
    def export_dir(self):
        path = self._base_dir / self.get("export_dir", "data/exports")
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def get_cache_path(self, game, region="cn"):
        """获取游戏缓存文件路径"""
        rel_path = self.get(f"cache_paths.{game}.{region}", "")
        if not rel_path:
            return ""
        return str(Path.home() / rel_path)

    def get_request_interval(self):
        return self.get("request_interval", 1.0)

    def get_request_timeout(self):
        return self.get("request_timeout", 15)
