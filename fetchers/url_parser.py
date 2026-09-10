"""抽卡记录 URL 解析 / 校验 / 清洗"""

import re
from urllib.parse import urlparse, parse_qs, unquote
from typing import Dict


class URLParser:
    @staticmethod
    def parse(url: str) -> Dict:
        url = unquote(url.strip())
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        # 鸣潮参数在 hash fragment 里
        if not params and parsed.fragment and "?" in parsed.fragment:
            params = parse_qs(parsed.fragment.split("?", 1)[1])

        result = {
            "url": url,
            "host": parsed.hostname,
            "path": parsed.path,
            "params": {k: v[0] if len(v) == 1 else v for k, v in params.items()},
            "authkey": params.get("authkey", [None])[0],
            "game_biz": params.get("game_biz", [None])[0],
            "lang": params.get("lang", [None])[0],
            "region": params.get("region", [None])[0],
        }
        result["game"] = URLParser._detect_game(url, result)
        result["pool_type"] = URLParser._detect_pool_type(url, result)
        return result

    @staticmethod
    def _detect_game(url: str, info: Dict) -> str:
        biz = info.get("game_biz", "") or ""
        host = info.get("host", "") or ""
        if "hk4e" in url or "genshin" in biz.lower():
            return "genshin"
        if "hkrpg" in url or "starrail" in biz.lower():
            return "starrail"
        if "nap" in url or "zzz" in biz.lower():
            return "zzz"
        if "kuro" in host.lower() or "aki-game" in host.lower() or "wutheringwaves" in url.lower():
            return "wutheringwaves"
        return ""

    @staticmethod
    def _detect_pool_type(url: str, info: Dict) -> str:
        params = info.get("params", {})
        game = info.get("game", "")
        gacha_type = params.get(
            "real_gacha_type" if game == "zzz" else "gacha_type", ""
        )
        if isinstance(gacha_type, str) and gacha_type.isdigit():
            type_map = {
                "1": "standard",
                "2": "character",
                "3": "weapon",
                "5": "bangboo",
                "11": "beginner",
                "12": "character",
                "102": "special",
                "103": "special_weapon",
            }
            return type_map.get(gacha_type, "character")
        return "character"

    @staticmethod
    def validate_url(url: str) -> bool:
        url = url.strip()
        if not url.startswith("http"):
            return False
        has_authkey = "authkey=" in url
        has_gacha = "gacha" in url.lower() or "GachaLog" in url
        return has_authkey or has_gacha

    @staticmethod
    def clean_url(url: str) -> str:
        url = url.strip()
        url = url.replace("\\u0026", "&")
        url = url.replace("%26", "&")
        return re.sub(r"\s+", "", url)
