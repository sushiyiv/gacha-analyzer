"""从游戏缓存/日志提取抽卡 API URL、UID、昵称"""

import os
import logging
import re
from pathlib import Path
from typing import Optional

from core.config import Config

logger = logging.getLogger(__name__)


class CacheReader:
    def __init__(self):
        self.config = Config()

    def find_game_path(self, game: str, region: str = "cn") -> str:
        log_path = self.config.get_cache_path(game, region)
        if not log_path or not os.path.exists(log_path):
            for alt_path in self._get_alternative_log_paths(game, region):
                if os.path.exists(alt_path):
                    log_path = alt_path
                    break
            else:
                return ""

        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(8192)
        except Exception:
            return ""

        if game == "genshin":
            match = re.search(
                r'([A-Z]:/(?:[^:*?"<>|\n])+?)/(YuanShen_Data|GenshinImpact_Data)',
                content,
            )
            if match:
                return match.group(1).strip() + "/" + match.group(2)

            for pattern in [
                r'Warmup file \w+:(.+?)(YuanShen_Data|GenshinImpact_Data)',
                r'Loading player data from (.+?)(?:/|$)',
            ]:
                match = re.search(pattern, content)
                if match:
                    base = match.group(1).strip()
                    if "GenshinImpact_Data" in content:
                        return base + "GenshinImpact_Data"
                    return base + "YuanShen_Data"

        elif game == "starrail":
            match = re.search(r'reportPath":"(.+?StarRail_Data)', content)
            if match:
                return match.group(1).replace("\\\\", "/").replace("\\", "/")
            match = re.search(r'Loading player data from (.+?)/Game/StarRail_Data', content)
            if match:
                return match.group(1) + "/Game/StarRail_Data"

        elif game == "zzz":
            match = re.search(r'reportPath":"(.+?ZenlessZoneZero_Data)', content)
            if match:
                return match.group(1).replace("\\\\", "/").replace("\\", "/")
            match = re.search(r'Discovering subsystems at path (.+?)(?:/|$)', content)
            if match:
                return match.group(1).strip()

        elif game == "wutheringwaves":
            saved_dir = Path(log_path).parent.parent
            if saved_dir.exists():
                return str(saved_dir)

        return ""

    def _get_alternative_log_paths(self, game: str, region: str) -> list:
        paths = []
        home = Path.home()

        if game == "genshin":
            if region == "cn":
                paths = [
                    str(home / "AppData/LocalLow/miHoYo/原神/LocalLog.log"),
                    str(home / "AppData/LocalLow/miHoYo/原神/output_log.txt"),
                ]
            else:
                paths = [
                    str(home / "AppData/LocalLow/Cognosphere/Genshin Impact/LocalLog.log"),
                    str(home / "AppData/LocalLow/Cognosphere/Genshin Impact/output_log.txt"),
                ]
        elif game == "starrail":
            if region == "cn":
                paths = [
                    str(home / "AppData/LocalLow/miHoYo/崩坏：星穹铁道/output_log.txt"),
                    str(home / "AppData/LocalLow/miHoYo/崩坏：星穹铁道/Player.log"),
                ]
            else:
                paths = [
                    str(home / "AppData/LocalLow/Cognosphere/Star Rail/output_log.txt"),
                    str(home / "AppData/LocalLow/Cognosphere/Star Rail/Player.log"),
                ]
        elif game == "zzz":
            if region == "cn":
                paths = [str(home / "AppData/LocalLow/miHoYo/绝区零/output_log.txt")]
            else:
                paths = [str(home / "AppData/LocalLow/Cognosphere/ZZZ/output_log.txt")]
        elif game == "wutheringwaves":
            try:
                import winreg
                for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                    for subkey in [
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
                    ]:
                        try:
                            key = winreg.OpenKey(hive, subkey)
                        except OSError:
                            continue
                        i = 0
                        while True:
                            try:
                                sub = winreg.EnumKey(key, i)
                            except OSError:
                                break
                            i += 1
                            try:
                                sub_k = winreg.OpenKey(key, sub)
                            except OSError:
                                continue
                            try:
                                name = winreg.QueryValueEx(sub_k, "DisplayName")[0]
                                if "wuthering" in str(name).lower() or name == "鸣潮":
                                    loc = ""
                                    try:
                                        loc = winreg.QueryValueEx(sub_k, "InstallLocation")[0]
                                    except OSError:
                                        pass
                                    if loc and os.path.isdir(loc):
                                        for suffix in (
                                            "Wuthering Waves Game/Client/Saved/Logs/Client.log",
                                            "Client/Saved/Logs/Client.log",
                                        ):
                                            p = os.path.join(loc, suffix)
                                            if os.path.exists(p):
                                                paths.append(p)
                            except OSError:
                                pass
                            finally:
                                winreg.CloseKey(sub_k)
                        winreg.CloseKey(key)
            except Exception:
                pass

            for p in [
                r"E:/Program Files/Wuthering Waves/Wuthering Waves Game/Client/Saved/Logs/Client.log",
                r"D:/Program Files/Wuthering Waves/Wuthering Waves Game/Client/Saved/Logs/Client.log",
                r"C:/Program Files/Wuthering Waves/Wuthering Waves Game/Client/Saved/Logs/Client.log",
            ]:
                if os.path.exists(p):
                    paths.append(p)

        return paths

    def extract_url(self, game: str, region: str = "cn") -> Optional[str]:
        if game in ("genshin", "starrail", "zzz"):
            log_path = self.config.get_cache_path(game, region)
            if log_path and os.path.exists(log_path):
                url = self._parse_cache_file(log_path, game)
                if url:
                    return url

        game_path = self.find_game_path(game, region)
        if not game_path:
            game_path = self._find_game_data_dir(game, region)
            if not game_path:
                return None

        for cache_rel in self._get_cache_data_paths(game):
            cache_file = os.path.join(game_path, cache_rel)
            if os.path.exists(cache_file):
                url = self._parse_cache_file(cache_file, game)
                if url:
                    return url

        return self._search_cache_files(game_path, game)

    def _find_game_data_dir(self, game: str, region: str) -> str:
        if game == "genshin":
            possible_paths = [
                "E:/miHoYo Launcher/games/Genshin Impact Game",
                "D:/miHoYo Launcher/games/Genshin Impact Game",
                "C:/Program Files/Genshin Impact",
                str(Path.home() / "miHoYo Launcher/games/Genshin Impact Game"),
            ]
            for path in possible_paths:
                for name in ("YuanShen_Data", "GenshinImpact_Data"):
                    data_dir = os.path.join(path, name)
                    if os.path.exists(data_dir):
                        return data_dir
        elif game == "starrail":
            for path in [
                "E:/miHoYo Launcher/games/Star Rail Game",
                "D:/miHoYo Launcher/games/Star Rail Game",
                str(Path.home() / "miHoYo Launcher/games/Star Rail Game"),
            ]:
                data_dir = os.path.join(path, "StarRail_Data")
                if os.path.exists(data_dir):
                    return data_dir
        elif game == "zzz":
            for path in [
                "E:/miHoYo Launcher/games/ZenlessZoneZero Game",
                "D:/miHoYo Launcher/games/ZenlessZoneZero Game",
                str(Path.home() / "miHoYo Launcher/games/ZenlessZoneZero Game"),
            ]:
                data_dir = os.path.join(path, "ZenlessZoneZero_Data")
                if os.path.exists(data_dir):
                    return data_dir
        return ""

    def _search_cache_files(self, game_path: str, game: str) -> Optional[str]:
        web_cache_dir = os.path.join(game_path, "webCaches")
        if not os.path.exists(web_cache_dir):
            return None
        for version_dir in sorted(os.listdir(web_cache_dir), reverse=True):
            cache_file = os.path.join(
                web_cache_dir, version_dir, "Cache", "Cache_Data", "data_2"
            )
            if os.path.exists(cache_file):
                url = self._parse_cache_file(cache_file, game)
                if url:
                    return url
        return None

    def _get_cache_data_paths(self, game: str) -> list:
        if game == "wutheringwaves":
            return ["Logs/Client.log"]
        return [
            "../webCaches/2.49.0.0/Cache/Cache_Data/data_2",
            "../webCaches/2.47.0.0/Cache/Cache_Data/data_2",
            "../webCaches/2.45.1.0/Cache/Cache_Data/data_2",
            "../webCaches/2.43.0.0/Cache/Cache_Data/data_2",
            "../webCaches/2.24.0.0/Cache/Cache_Data/data_2",
            "../webCaches/2.22.0.0/Cache/Cache_Data/data_2",
            "../webCaches/2.20.0.0/Cache/Cache_Data/data_2",
            "../webCaches/2.18.0.0/Cache/Cache_Data/data_2",
        ]

    def _parse_cache_file(self, filepath: str, game: str) -> Optional[str]:
        try:
            with open(filepath, "rb") as f:
                content = f.read().decode("utf-8", errors="ignore")
        except Exception:
            logger.debug("缓存文件读取失败: %s", filepath)
            return None

        if game == "wutheringwaves":
            matches = re.findall(
                r'"url":"(https://aki-gm-resources\.aki-game\.com/aki/gacha/index\.html#/record\?[^"]+)"',
                content,
            )
            if matches:
                return matches[-1].replace("\\u0026", "&")
            return None

        ctrl = r"\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f"
        patterns = [
            rf'https?://[^{ctrl}]+getGachaLog[^{ctrl}]*',
            rf'https?://[^{ctrl}]+getGacha[^{ctrl}]*',
            rf'https?://[^{ctrl}]+gacha[^{ctrl}]*authkey=[^{ctrl}]*',
        ]
        for pattern in patterns:
            matches = re.findall(pattern, content)
            if matches:
                return re.sub(r"[\x00-\x1f\x7f-\x9f]", "", matches[-1])
        return None

    def extract_authkey(self, url: str) -> Optional[str]:
        match = re.search(r"authkey=([^&]+)", url)
        return match.group(1) if match else None

    def extract_uid(self, game: str, region: str = "cn") -> Optional[str]:
        home = Path.home()
        if game == "genshin":
            uid_file = (
                home / "AppData/LocalLow/miHoYo/原神/UidInfo.txt"
                if region == "cn"
                else home / "AppData/LocalLow/Cognosphere/Genshin Impact/UidInfo.txt"
            )
        elif game == "starrail":
            uid_file = (
                home / "AppData/LocalLow/miHoYo/崩坏：星穹铁道/UidInfo.txt"
                if region == "cn"
                else home / "AppData/LocalLow/Cognosphere/Star Rail/UidInfo.txt"
            )
        elif game == "zzz":
            uid_file = (
                home / "AppData/LocalLow/miHoYo/绝区零/UidInfo.txt"
                if region == "cn"
                else home / "AppData/LocalLow/Cognosphere/ZZZ/UidInfo.txt"
            )
        else:
            return None

        if uid_file.exists():
            try:
                uid = uid_file.read_text(encoding="utf-8").strip()
                if uid and uid.isdigit():
                    return uid
            except Exception:
                logger.debug("UID文件读取失败: %s", uid_file)
        return None

    def extract_nickname(self, game: str, region: str = "cn") -> Optional[str]:
        log_path = self.config.get_cache_path(game, region)
        if not log_path or not os.path.exists(log_path):
            return None
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read(8192)
            if game in ("genshin", "starrail"):
                match = re.search(r"Player\s+(\w+)\s+login", content)
                if match:
                    return match.group(1)
        except Exception:
            logger.debug("昵称文件读取失败")
        return None

    def is_url_expired(self, url: str) -> bool:
        try:
            import requests
            resp = requests.get(url, params={"page": 1, "size": 1}, timeout=10)
            return resp.json().get("retcode") != 0
        except Exception:
            return True
