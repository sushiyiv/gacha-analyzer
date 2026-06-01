"""URL 解析器 - 解析用户粘贴的抽卡记录 API URL"""

import re
from urllib.parse import urlparse, parse_qs, unquote
from typing import Dict, Optional


class URLParser:
    """抽卡记录 URL 解析器"""

    @staticmethod
    def parse(url: str) -> Dict:
        """解析URL，提取关键信息"""
        url = unquote(url.strip())
        parsed = urlparse(url)
        params = parse_qs(parsed.query)

        # 鸣潮URL的参数在hash fragment中
        if not params and parsed.fragment and '?' in parsed.fragment:
            frag_query = parsed.fragment.split('?', 1)[1]
            params = parse_qs(frag_query)

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

        # 判断游戏类型
        result["game"] = URLParser._detect_game(url, result)
        result["pool_type"] = URLParser._detect_pool_type(url, result)

        return result

    @staticmethod
    def _detect_game(url: str, info: Dict) -> str:
        """根据URL判断游戏"""
        biz = info.get("game_biz", "") or ""
        host = info.get("host", "") or ""

        if "hk4e" in url or "genshin" in biz.lower():
            return "genshin"
        elif "hkrpg" in url or "starrail" in biz.lower():
            return "starrail"
        elif "nap" in url or "zzz" in biz.lower():
            return "zzz"
        elif "kuro" in host.lower() or "aki-game" in host.lower() or "wutheringwaves" in url.lower():
            return "wutheringwaves"
        elif "ef-webview" in url or "endfield" in url.lower():
            return "endfield"
        elif "hypergryph" in url.lower() and "endfield" not in url.lower():
            # 可能是终末地的账号 token
            return ""
        return ""

    @staticmethod
    def _detect_pool_type(url: str, info: Dict) -> str:
        """根据URL判断卡池类型"""
        params = info.get("params", {})
        gacha_type = params.get("gacha_type", "")

        # 米哈游系列的gacha_type通常是数字
        if isinstance(gacha_type, str) and gacha_type.isdigit():
            # 原神: 1=常驻, 2=角色, 3=武器, 11=新手
            # 星铁: 1=常驻, 2=角色, 3=武器, 11=新手
            type_map = {
                "1": "standard", "2": "character", "3": "weapon",
                "11": "beginner", "12": "character",
            }
            return type_map.get(gacha_type, "character")

        return "character"

    @staticmethod
    def validate_url(url: str) -> bool:
        """验证URL是否是有效的抽卡记录URL"""
        url = url.strip()
        if not url.startswith("http"):
            return False
        # 检查是否包含关键参数
        has_authkey = "authkey=" in url
        has_gacha = "gacha" in url.lower() or "GachaLog" in url
        return has_authkey or has_gacha

    @staticmethod
    def clean_url(url: str) -> str:
        """清理URL，去除多余的转义字符"""
        url = url.strip()
        url = url.replace("\\u0026", "&")
        url = url.replace("%26", "&")
        url = re.sub(r'\s+', '', url)
        return url
