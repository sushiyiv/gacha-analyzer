"""鸣潮抽卡记录获取器"""

import requests
from urllib.parse import parse_qs
from typing import List
from fetchers.base import BaseFetcher, FetcherError
from fetchers.cache_reader import CacheReader
from fetchers.url_parser import URLParser
from core.models import GachaRecord

# cardPoolType (API参数) -> pool_name 映射
CARD_POOL_TYPE_MAP = {
    1: "character",           # 角色活动唤取
    2: "weapon",              # 武器活动唤取
    3: "standard_character",  # 角色常驻唤取
    4: "standard_weapon",     # 武器常驻唤取
    5: "beginner",            # 新手唤取
    8: "selector",            # 角色新旅唤取
    9: "selector_weapon",     # 武器新旅唤取
}

# API返回的中文卡池名 -> pool_name 映射（备用）
POOL_NAME_MAP = {
    "角色精准调谐": "character",
    "角色活动唤取": "character",
    "武器精准调谐": "weapon",
    "武器活动唤取": "weapon",
    "角色常驻唤取": "standard_character",
    "武器常驻唤取": "standard_weapon",
    "新手唤取": "beginner",
    "新手自选唤取": "beginner",
    "角色新旅唤取": "selector",
    "武器新旅唤取": "selector_weapon",
}

# 鸣潮常驻5星角色（非限定）
STANDARD_5STAR_CHARACTERS = {
    "维里奈", "安可", "鉴心", "卡卡罗", "凌阳",
}

# 鸣潮常驻5星武器（非限定，共10把）
STANDARD_5STAR_WEAPONS = {
    # 开服5把
    "浩境粼光", "千古洑流", "停驻之烟", "擎渊怒涛", "漪澜浮录",
    # 3.0版本新增5把
    "源能机锋", "镭射切变", "相位涟漪", "脉冲协臂", "玻色星仪",
}


import logging

logger = logging.getLogger(__name__)


class WutheringWavesFetcher(BaseFetcher):
    """鸣潮抽卡记录获取器"""

    API_URL = "https://gmserver-api.aki-game2.com/gacha/record/query"

    def __init__(self):
        super().__init__()
        self.cache = CacheReader()
        self._detected_uid = ""

    def get_game_name(self) -> str:
        return "鸣潮"

    def get_supported_pools(self) -> List[str]:
        return ["character", "weapon", "selector", "selector_weapon",
                "standard_character", "standard_weapon", "beginner"]

    def _parse_webview_url(self, url: str) -> dict:
        """从鸣潮网页URL中提取参数"""
        # URL格式: https://...#/record?svr_id=xxx&player_id=xxx&...
        if '#' in url:
            hash_part = url.split('#', 1)[1]
            if '?' in hash_part:
                query = hash_part.split('?', 1)[1]
                params = parse_qs(query)
                return {k: v[0] for k, v in params.items()}
        if '?' in url:
            params = parse_qs(url.split('?', 1)[1])
            return {k: v[0] for k, v in params.items()}
        return {}

    def fetch_records(self, url: str = None, account_id: int = None,
                      latest_time: str = None) -> List[GachaRecord]:
        """获取鸣潮抽卡记录"""
        if not url:
            self._report_progress("正在从缓存中提取URL...", 0.1)
            url = self.cache.extract_url("wutheringwaves")
            if not url:
                raise FetcherError(
                    "无法自动获取鸣潮URL。\n\n"
                    "请打开鸣潮，进入唤取记录页面，然后切回本程序重试。\n"
                    "或者手动粘贴唤取记录页面的URL。"
                )

        url = URLParser.clean_url(url)
        params = self._parse_webview_url(url)

        if not params.get("player_id"):
            raise FetcherError("URL中缺少必要参数，请重新获取")

        self._detected_uid = params.get("player_id", "")

        # 要获取的卡池类型 (cardPoolType: 1-9)
        pool_types = [1, 2, 3, 4, 5, 8, 9]
        all_records = []
        total_pools = len(pool_types)

        for pool_idx, card_pool_type in enumerate(pool_types):
            if self._cancel_check and self._cancel_check():
                raise FetcherError("用户取消")

            pool_name = CARD_POOL_TYPE_MAP.get(card_pool_type, "character")
            self._report_progress(
                f"正在获取 {pool_name} 记录... ({pool_idx + 1}/{total_pools})",
                (pool_idx + 0.5) / total_pools
            )

            try:
                # API要求驼峰命名参数
                resp = requests.post(
                    self.API_URL,
                    json={
                        "playerId": params["player_id"],
                        "serverId": params.get("svr_id", ""),
                        "cardPoolId": params.get("resources_id", ""),
                        "cardPoolType": card_pool_type,
                        "languageCode": params.get("lang", "zh-Hans"),
                        "recordId": params.get("record_id", ""),
                    },
                    headers={"Content-Type": "application/json"},
                    timeout=15,
                )
                data = resp.json()
            except requests.exceptions.Timeout:
                raise FetcherError("网络请求超时")
            except requests.exceptions.ConnectionError:
                raise FetcherError("网络连接失败")
            except Exception as e:
                raise FetcherError(f"请求失败: {str(e)}")

            # API成功状态码是 0
            code = data.get("code")
            if code != 0:
                msg = data.get("message", data.get("msg", "未知错误"))
                # 某些卡池可能已被移除，跳过继续获取
                logger.warning(f" {pool_name} (type={card_pool_type}) 获取失败: {msg}")
                continue

            # API直接返回列表
            records = data.get("data", [])
            for r in records:
                r["_pool_type"] = pool_name
                r["_card_pool_type"] = card_pool_type

            all_records.extend(records)

        # 转换为GachaRecord
        result = []
        for raw in all_records:
            pool_type = raw.get("_pool_type", "character")
            card_pool_name = raw.get("cardPoolType", "")
            if card_pool_name in POOL_NAME_MAP:
                pool_type = POOL_NAME_MAP[card_pool_name]

            # 判断是否为UP/限定
            rarity = int(raw.get("qualityLevel", 3))
            item_name = raw.get("name", "")
            is_permanent_pool = "常驻" in card_pool_name or "新手" in card_pool_name
            is_standard_item = (item_name in STANDARD_5STAR_CHARACTERS or
                                item_name in STANDARD_5STAR_WEAPONS)
            # UP = 限时池 + 5星 + 不是常驻角色/武器
            is_featured = (not is_permanent_pool) and rarity >= 5 and (not is_standard_item)

            # 用 resourceId + time + cardPoolType 组合作为唯一标识
            unique_id = f"{raw.get('resourceId', '')}_{raw.get('time', '')}_{raw.get('_card_pool_type', '')}"

            record = GachaRecord(
                account_id=account_id or 0,
                game="wutheringwaves",
                pool_type=pool_type,
                item_id=unique_id,
                item_name=raw.get("name", "未知"),
                item_type=raw.get("resourceType", ""),
                rarity=rarity,
                is_featured=is_featured,
                count=int(raw.get("count", 1)),
                time=raw.get("time", ""),
            )
            result.append(record)

        self._report_progress(f"获取完成，共 {len(result)} 条记录", 1.0)
        return result
