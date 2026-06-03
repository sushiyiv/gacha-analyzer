"""配置管理模块（稳定性优化版）"""

import os
import yaml
from pathlib import Path


class Config:
    """应用配置管理"""

    _instance = None
    _config = None

    DEFAULTS = {
        "database_path": "data/gacha_records.db",
        "backup_dir": "data/backups",
        "export_dir": "data/exports",
        "request_interval": 1.0,
        "request_timeout": 15,
        "max_backups": 10,
        "backup_interval_hours": 24,
        "auto_backup": True,
    }

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
        self._config = dict(self.DEFAULTS)

        if self._config_path.exists():
            with open(self._config_path, "r", encoding="utf-8") as f:
                default_config = yaml.safe_load(f) or {}
                self._deep_merge(self._config, default_config)

        if self._user_config_path.exists():
            with open(self._user_config_path, "r", encoding="utf-8") as f:
                user_config = yaml.safe_load(f) or {}
                self._deep_merge(self._config, user_config)

    def _deep_merge(self, base, override):
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def get(self, key, default=None):
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

    def get_int(self, key, default=None):
        value = self.get(key, default)
        try:
            return int(value)
        except Exception:
            return default

    def get_float(self, key, default=None):
        value = self.get(key, default)
        try:
            return float(value)
        except Exception:
            return default

    def set(self, key, value):
        keys = key.split(".")
        config = self._config
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        config[keys[-1]] = value

    def save(self):
        self._user_config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._user_config_path, "w", encoding="utf-8") as f:
            yaml.dump(self._config, f, allow_unicode=True, default_flow_style=False)

    @property
    def base_dir(self):
        return self._base_dir

    @property
    def db_path(self):
        path = self._base_dir / str(self.get("database_path", self.DEFAULTS["database_path"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    @property
    def backup_dir(self):
        path = self._base_dir / str(self.get("backup_dir", self.DEFAULTS["backup_dir"]))
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    @property
    def export_dir(self):
        path = self._base_dir / str(self.get("export_dir", self.DEFAULTS["export_dir"]))
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    def get_cache_path(self, game, region="cn"):
        rel_path = self.get(f"cache_paths.{game}.{region}", "")
        if not rel_path:
            return ""
        return str(Path.home() / rel_path)

    def get_request_interval(self):
        return self.get_float("request_interval", self.DEFAULTS["request_interval"])

    def get_request_timeout(self):
        return self.get_int("request_timeout", self.DEFAULTS["request_timeout"])
