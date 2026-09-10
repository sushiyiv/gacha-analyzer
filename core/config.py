"""配置管理：默认值 < config.yaml < user_config.yaml

save() 只写入相对 base（默认值+config.yaml）有差异的键，避免用户配置文件膨胀并盖住后续默认值升级。
"""

import copy
import sys
import yaml
from pathlib import Path


class Config:
    """单例配置。支持点号路径，如 cache_paths.genshin.cn"""

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
            if getattr(sys, "frozen", False):
                exe_dir = Path(sys.executable).parent
                # 应用资源在 _internal；用户数据在 exe 同级，重打包不会被清
                self._base_dir = (
                    exe_dir / "_internal"
                    if (exe_dir / "_internal" / "config.yaml").exists()
                    else exe_dir
                )
                self._data_root = exe_dir
            else:
                self._base_dir = Path(__file__).parent.parent
                self._data_root = self._base_dir

            self._data_dir = self._data_root / "data"
            self._data_dir.mkdir(parents=True, exist_ok=True)
            self._config_path = self._base_dir / "config.yaml"
            self._user_config_path = self._data_dir / "user_config.yaml"
            self._config = {}
            self._base = {}
            self._load()

    def _load(self):
        self._config = dict(self.DEFAULTS)

        if self._config_path.exists():
            with open(self._config_path, "r", encoding="utf-8") as f:
                self._deep_merge(self._config, yaml.safe_load(f) or {})

        self._base = copy.deepcopy(self._config)

        if self._user_config_path.exists():
            with open(self._user_config_path, "r", encoding="utf-8") as f:
                self._deep_merge(self._config, yaml.safe_load(f) or {})

    def _deep_merge(self, base, override):
        for key, value in override.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

    def get(self, key, default=None):
        value = self._config
        for k in key.split("."):
            if not isinstance(value, dict):
                return default
            value = value.get(k)
            if value is None:
                return default
        return value

    def get_int(self, key, default=None):
        try:
            return int(self.get(key, default))
        except Exception:
            return default

    def get_float(self, key, default=None):
        try:
            return float(self.get(key, default))
        except Exception:
            return default

    def set(self, key, value):
        """只改内存，需再调 save() 落盘。"""
        config = self._config
        keys = key.split(".")
        for k in keys[:-1]:
            config = config.setdefault(k, {})
        config[keys[-1]] = value

    def save(self):
        """只持久化相对 base 有差异的用户配置。"""
        user_only = self._diff(self._config, getattr(self, "_base", {}))
        self._user_config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._user_config_path, "w", encoding="utf-8") as f:
            yaml.dump(user_only, f, allow_unicode=True, default_flow_style=False)

    @classmethod
    def _diff(cls, current, base):
        if not isinstance(current, dict) or not isinstance(base, dict):
            return current if current != base else None
        out = {}
        for key, value in current.items():
            if key not in base:
                out[key] = value
            elif isinstance(value, dict) and isinstance(base.get(key), dict):
                nested = cls._diff(value, base[key])
                if nested:
                    out[key] = nested
            elif value != base[key]:
                out[key] = value
        return out

    @property
    def base_dir(self):
        return self._base_dir

    @property
    def db_path(self):
        path = self._data_root / str(self.get("database_path", self.DEFAULTS["database_path"]))
        path.parent.mkdir(parents=True, exist_ok=True)
        return str(path)

    @property
    def backup_dir(self):
        path = self._data_root / str(self.get("backup_dir", self.DEFAULTS["backup_dir"]))
        path.mkdir(parents=True, exist_ok=True)
        return str(path)

    @property
    def export_dir(self):
        path = self._data_root / str(self.get("export_dir", self.DEFAULTS["export_dir"]))
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
