"""缓存文件读取 - 从游戏缓存中提取 API URL"""

import os
import re
from pathlib import Path
from typing import Optional, Tuple
from core.config import Config


class CacheReader:
    """游戏缓存文件读取器"""

    def __init__(self):
        self.config = Config()

    def find_game_path(self, game: str, region: str = "cn") -> str:
        """从日志文件中找到游戏安装路径"""
        log_path = self.config.get_cache_path(game, region)
        if not log_path or not os.path.exists(log_path):
            # 尝试其他可能的日志文件
            alt_paths = self._get_alternative_log_paths(game, region)
            for alt_path in alt_paths:
                if os.path.exists(alt_path):
                    log_path = alt_path
                    break
            else:
                return ""

        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(8192)  # 读取更多内容
        except Exception:
            return ""

        if game == "genshin":
            # 尝试从日志中提取游戏安装路径
            # 匹配类似 E:/path/to/Genshin Impact Game/YuanShen_Data 的路径
            # 路径可能包含空格，所以用更宽松的匹配
            match = re.search(r'([A-Z]:/(?:[^:*?"<>|\n])+?)/(YuanShen_Data|GenshinImpact_Data)', content)
            if match:
                base = match.group(1).strip()
                data_dir = match.group(2)
                return base + "/" + data_dir

            # 备用模式
            patterns = [
                r'Warmup file \w+:(.+?)(YuanShen_Data|GenshinImpact_Data)',
                r'Loading player data from (.+?)(?:/|$)',
            ]
            for pattern in patterns:
                match = re.search(pattern, content)
                if match:
                    base = match.group(1).strip()
                    if "YuanShen_Data" in content:
                        return base + "YuanShen_Data"
                    elif "GenshinImpact_Data" in content:
                        return base + "GenshinImpact_Data"
                    else:
                        return base + "YuanShen_Data"

        elif game == "starrail":
            match = re.search(r'Loading player data from (.+?)/Game/StarRail_Data', content)
            if match:
                return match.group(1) + "/Game/StarRail_Data"

        elif game == "zzz":
            # 从 reportPath 提取游戏数据目录
            match = re.search(r'reportPath":"(.+?ZenlessZoneZero_Data)', content)
            if match:
                return match.group(1).replace("\\\\", "/").replace("\\", "/")
            match = re.search(r'Discovering subsystems at path (.+?)(?:/|$)', content)
            if match:
                return match.group(1).strip()

        elif game == "wutheringwaves":
            # 鸣潮从日志文件位置推断游戏路径
            # 日志在 Client/Saved/Logs/Client.log，游戏数据在 Client/Saved/
            log_dir = Path(log_path).parent  # Logs/
            saved_dir = log_dir.parent  # Saved/
            if saved_dir.exists():
                return str(saved_dir)

        return ""

    def _get_alternative_log_paths(self, game: str, region: str) -> list:
        """获取其他可能的日志文件路径"""
        paths = []
        if game == "genshin":
            if region == "cn":
                paths = [
                    str(Path.home() / "AppData/LocalLow/miHoYo/原神/LocalLog.log"),
                    str(Path.home() / "AppData/LocalLow/miHoYo/原神/output_log.txt"),
                ]
            else:
                paths = [
                    str(Path.home() / "AppData/LocalLow/Cognosphere/Genshin Impact/LocalLog.log"),
                    str(Path.home() / "AppData/LocalLow/Cognosphere/Genshin Impact/output_log.txt"),
                ]
        elif game == "wutheringwaves":
            # 鸣潮日志在游戏安装目录 Client/Saved/Logs/Client.log
            # 1. 先查注册表
            try:
                import winreg
                for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                    for subkey in [
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
                    ]:
                        try:
                            key = winreg.OpenKey(hive, subkey)
                            i = 0
                            while True:
                                try:
                                    sub = winreg.EnumKey(key, i)
                                    sub_k = winreg.OpenKey(key, sub)
                                    try:
                                        name = winreg.QueryValueEx(sub_k, "DisplayName")[0]
                                        if "wuthering" in name.lower() or name == "\u9e23\u6f6e":
                                            loc = ""
                                            try:
                                                loc = winreg.QueryValueEx(sub_k, "InstallLocation")[0]
                                            except Exception:
                                                pass
                                            if loc and os.path.isdir(loc):
                                                log = Path(loc) / "Wuthering Waves Game" / "Client" / "Saved" / "Logs" / "Client.log"
                                                if log.exists():
                                                    paths.append(str(log))
                                                    return paths
                                                # 尝试直接在安装目录下找
                                                log2 = Path(loc) / "Client" / "Saved" / "Logs" / "Client.log"
                                                if log2.exists():
                                                    paths.append(str(log2))
                                                    return paths
                                    finally:
                                        winreg.CloseKey(sub_k)
                                    i += 1
                                except OSError:
                                    break
                            winreg.CloseKey(key)
                        except Exception:
                            pass
            except Exception:
                pass

            # 2. 注册表没找到，搜索所有磁盘
            import string as _string
            search_dirs = []
            for letter in _string.ascii_uppercase:
                drive = Path(f"{letter}:/")
                if not drive.exists():
                    continue
                # 常见游戏安装目录
                for subdir in ["Program Files", "Program File", "Program Files (x86)",
                               "Games", "Game", ""]:
                    try:
                        base = drive / subdir if subdir else drive
                        if not base.exists() or not base.is_dir():
                            continue
                        for p in base.iterdir():
                            if not p.is_dir():
                                continue
                            name_lower = p.name.lower()
                            if "wuthering" in name_lower or "鸣潮" in name_lower:
                                search_dirs.append(p)
                    except (PermissionError, OSError):
                        continue

            for base in search_dirs:
                log = base / "Wuthering Waves Game" / "Client" / "Saved" / "Logs" / "Client.log"
                if log.exists():
                    paths.append(str(log))
                    return paths
        return paths

    def extract_url(self, game: str, region: str = "cn") -> Optional[str]:
        """从缓存文件中提取抽卡 API URL"""
        # 所有米哈游游戏：优先从日志文件读取 URL
        if game in ("genshin", "starrail", "zzz"):
            log_path = self.config.get_cache_path(game, region)
            if log_path and os.path.exists(log_path):
                url = self._parse_cache_file(log_path, game)
                if url:
                    return url

        game_path = self.find_game_path(game, region)
        if not game_path:
            # 尝试直接从游戏数据目录查找
            game_path = self._find_game_data_dir(game, region)
            if not game_path:
                return None

        # 尝试不同的缓存路径
        cache_paths = self._get_cache_data_paths(game)
        for cache_rel in cache_paths:
            cache_file = os.path.join(game_path, cache_rel)
            if os.path.exists(cache_file):
                url = self._parse_cache_file(cache_file, game)
                if url:
                    return url

        # 如果没找到，尝试搜索所有可能的缓存文件
        return self._search_cache_files(game_path, game)

    def _find_game_data_dir(self, game: str, region: str) -> str:
        """直接查找游戏数据目录"""
        if game == "genshin":
            if region == "cn":
                # 常见的原神安装路径
                possible_paths = [
                    "E:/miHoYo Launcher/games/Genshin Impact Game",
                    "D:/miHoYo Launcher/games/Genshin Impact Game",
                    "C:/Program Files/Genshin Impact",
                    str(Path.home() / "miHoYo Launcher/games/Genshin Impact Game"),
                ]
            else:
                possible_paths = [
                    "E:/miHoYo Launcher/games/Genshin Impact Game",
                    "D:/miHoYo Launcher/games/Genshin Impact Game",
                    "C:/Program Files/Genshin Impact",
                ]

            for path in possible_paths:
                data_dir = os.path.join(path, "YuanShen_Data")
                if os.path.exists(data_dir):
                    return data_dir
                data_dir = os.path.join(path, "GenshinImpact_Data")
                if os.path.exists(data_dir):
                    return data_dir

        elif game == "starrail":
            possible_paths = [
                "E:/miHoYo Launcher/games/Star Rail Game",
                "D:/miHoYo Launcher/games/Star Rail Game",
                str(Path.home() / "miHoYo Launcher/games/Star Rail Game"),
            ]
            for path in possible_paths:
                data_dir = os.path.join(path, "StarRail_Data")
                if os.path.exists(data_dir):
                    return data_dir

        elif game == "zzz":
            possible_paths = [
                "E:/miHoYo Launcher/games/ZenlessZoneZero Game",
                "D:/miHoYo Launcher/games/ZenlessZoneZero Game",
                str(Path.home() / "miHoYo Launcher/games/ZenlessZoneZero Game"),
            ]
            for path in possible_paths:
                data_dir = os.path.join(path, "ZenlessZoneZero_Data")
                if os.path.exists(data_dir):
                    return data_dir

        return ""

    def _search_cache_files(self, game_path: str, game: str) -> Optional[str]:
        """搜索所有可能的缓存文件"""
        # 查找webCaches目录
        web_cache_dir = os.path.join(game_path, "webCaches")
        if not os.path.exists(web_cache_dir):
            return None

        # 遍历所有版本的缓存
        for version_dir in sorted(os.listdir(web_cache_dir), reverse=True):
            cache_file = os.path.join(web_cache_dir, version_dir, "Cache", "Cache_Data", "data_2")
            if os.path.exists(cache_file):
                url = self._parse_cache_file(cache_file, game)
                if url:
                    return url

        return None

    def _get_cache_data_paths(self, game: str) -> list:
        """获取各游戏的缓存文件相对路径"""
        if game == "wutheringwaves":
            # 鸣潮的URL存在Client.log中
            return ["Logs/Client.log"]
        paths = [
            "../webCaches/2.49.0.0/Cache/Cache_Data/data_2",
            "../webCaches/2.47.0.0/Cache/Cache_Data/data_2",
            "../webCaches/2.45.1.0/Cache/Cache_Data/data_2",
            "../webCaches/2.43.0.0/Cache/Cache_Data/data_2",
            "../webCaches/2.24.0.0/Cache/Cache_Data/data_2",
            "../webCaches/2.22.0.0/Cache/Cache_Data/data_2",
            "../webCaches/2.20.0.0/Cache/Cache_Data/data_2",
            "../webCaches/2.18.0.0/Cache/Cache_Data/data_2",
        ]
        return paths

    def _parse_cache_file(self, filepath: str, game: str) -> Optional[str]:
        """解析缓存文件，提取URL"""
        try:
            with open(filepath, "rb") as f:
                data = f.read()
            content = data.decode("utf-8", errors="ignore")
        except Exception:
            return None

        # 鸣潮：日志是二进制编码，使用专用解码器
        if game == "wutheringwaves":
            from fetchers.kuro.log_decoder import extract_gacha_urls_from_log
            urls = extract_gacha_urls_from_log(filepath)
            if urls:
                return urls[-1]
            return None

        # 查找包含 getGachaLog 或类似API的URL
        patterns = [
            r'https?://[^\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f]+getGachaLog[^\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f]*',
            r'https?://[^\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f]+getGacha[^\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f]*',
            r'https?://[^\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f]+gacha[^\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f]*authkey=[^\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f]*',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content)
            if matches:
                # 取最后一个（最新的）
                url = matches[-1]
                # 清理URL中的控制字符
                url = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', url)
                return url

        return None

    def extract_authkey(self, url: str) -> Optional[str]:
        """从URL中提取authkey"""
        match = re.search(r'authkey=([^&]+)', url)
        if match:
            return match.group(1)
        return None

    def extract_uid(self, game: str, region: str = "cn") -> Optional[str]:
        """从游戏文件中提取UID"""
        # 首先尝试从UidInfo.txt读取
        if game == "genshin":
            if region == "cn":
                uid_file = Path.home() / "AppData/LocalLow/miHoYo/原神/UidInfo.txt"
            else:
                uid_file = Path.home() / "AppData/LocalLow/Cognosphere/Genshin Impact/UidInfo.txt"
        elif game == "starrail":
            if region == "cn":
                uid_file = Path.home() / "AppData/LocalLow/miHoYo/崩坏：星穹铁道/UidInfo.txt"
            else:
                uid_file = Path.home() / "AppData/LocalLow/Cognosphere/Star Rail/UidInfo.txt"
        elif game == "zzz":
            if region == "cn":
                uid_file = Path.home() / "AppData/LocalLow/miHoYo/绝区零/UidInfo.txt"
            else:
                uid_file = Path.home() / "AppData/LocalLow/Cognosphere/ZZZ/UidInfo.txt"
        else:
            return None

        if uid_file.exists():
            try:
                with open(uid_file, "r", encoding="utf-8") as f:
                    uid = f.read().strip()
                    if uid and uid.isdigit():
                        return uid
            except Exception:
                pass

        return None

    def extract_nickname(self, game: str, region: str = "cn") -> Optional[str]:
        """从游戏文件中提取昵称"""
        # 尝试从日志文件中提取昵称
        log_path = self.config.get_cache_path(game, region)
        if not log_path or not os.path.exists(log_path):
            return None

        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(8192)

            # 尝试查找昵称（不同游戏格式不同）
            if game == "genshin":
                # 原神日志中可能包含昵称
                import re
                match = re.search(r'Player\s+(\w+)\s+login', content)
                if match:
                    return match.group(1)

            elif game == "starrail":
                # 星穹铁道日志中可能包含昵称
                import re
                match = re.search(r'Player\s+(\w+)\s+login', content)
                if match:
                    return match.group(1)

        except Exception:
            pass

        return None

    def is_url_expired(self, url: str) -> bool:
        """检查URL是否过期（简单检测）"""
        # 米哈游的authkey大约24小时过期
        # 这里做一个简单的检测：尝试发一个请求
        try:
            import requests
            resp = requests.get(url, params={"page": 1, "size": 1}, timeout=10)
            data = resp.json()
            return data.get("retcode") != 0
        except Exception:
            return True
