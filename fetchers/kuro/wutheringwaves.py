# -*- coding: utf-8 -*-
"""鸣潮抽卡记录获取器"""

import os
import requests
from urllib.parse import parse_qs
from typing import List
from fetchers.base import BaseFetcher, FetcherError
from fetchers.cache_reader import CacheReader
from fetchers.url_parser import URLParser
from fetchers.kuro.log_decoder import extract_gacha_urls_from_log
from core.models import GachaRecord

import logging

logger = logging.getLogger(__name__)

CARD_POOL_TYPE_MAP = {
    1: "character", 2: "weapon", 3: "standard_character",
    4: "standard_weapon", 5: "beginner", 8: "selector", 9: "selector_weapon", 10: "collab",
}

POOL_NAME_MAP = {
    "角色精准调谐": "character", "角色活动唤取": "character",
    "武器精准调谐": "weapon", "武器活动唤取": "weapon",
    "角色常驻唤取": "standard_character", "武器常驻唤取": "standard_weapon",
    "新手唤取": "beginner", "新手自选唤取": "beginner",
    "角色新旅唤取": "selector", "武器新旅唤取": "selector_weapon",
    "角色联动唤取": "collab", "武器联动唤取": "collab_weapon",
    "联动角色唤取": "collab", "联动武器唤取": "collab_weapon",
}

STANDARD_5STAR_CHARACTERS = {"维里奈", "安可", "鉴心", "卡卡罗", "凌阳"}
STANDARD_5STAR_WEAPONS = {
    "浩境粼光", "千古洑流", "停驻之烟", "擎渊怒涛", "漪澜浮录",
    "源能机锋", "镭射切变", "相位涟漪", "脉冲协臂", "玻色星仪",
}


class WutheringWavesFetcher(BaseFetcher):
    API_URL = "https://gmserver-api.aki-game2.com/gacha/record/query"

    def __init__(self):
        super().__init__()
        self.cache = CacheReader()
        self._detected_uid = ""

    def get_game_name(self):
        return "鸣潮"

    def get_supported_pools(self):
        return ["character", "weapon", "selector", "selector_weapon",
                "standard_character", "standard_weapon", "beginner", "collab"]

    def _find_game_exe(self):
        try:
            import winreg
            for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                for subkey in [r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                               r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"]:
                    try:
                        key = winreg.OpenKey(hive, subkey)
                        i = 0
                        while True:
                            try:
                                sk = winreg.EnumKey(key, i)
                                sp = winreg.OpenKey(key, sk)
                                try:
                                    name = winreg.QueryValueEx(sp, "DisplayName")[0]
                                    if "鸣潮" in name or "Wuthering" in name:
                                        loc = winreg.QueryValueEx(sp, "InstallLocation")[0]
                                        exe = os.path.join(loc, "Wuthering Waves Game", "Wuthering Waves.exe")
                                        if os.path.exists(exe):
                                            return exe
                                except FileNotFoundError:
                                    pass
                                winreg.CloseKey(sp)
                                i += 1
                            except OSError:
                                break
                        winreg.CloseKey(key)
                    except FileNotFoundError:
                        pass
        except Exception:
            pass
        for p in ["E:/Program File/Wuthering Waves/Wuthering Waves Game/Wuthering Waves.exe",
                   "D:/Program Files/Wuthering Waves/Wuthering Waves Game/Wuthering Waves.exe",
                   "C:/Program Files/Wuthering Waves/Wuthering Waves Game/Wuthering Waves.exe"]:
            if os.path.exists(p):
                return p
        return ""

    def _find_client_log(self):
        exe = self._find_game_exe()
        if exe:
            d = os.path.dirname(exe)
            log = os.path.join(d, "Client", "Saved", "Logs", "Client.log")
            if os.path.exists(log):
                return log
        for p in ["E:/Program File/Wuthering Waves/Wuthering Waves Game/Client/Saved/Logs/Client.log",
                   "D:/Program Files/Wuthering Waves/Wuthering Waves Game/Client/Saved/Logs/Client.log"]:
            if os.path.exists(p):
                return p
        return ""

    def _get_url_from_log(self):
        """从游戏日志中解密获取抽卡URL（纯Python实现）"""
        log = self._find_client_log()
        if not log:
            return ""
        try:
            self._report_progress("解密游戏日志...", 0.08)
            urls = extract_gacha_urls_from_log(log)
            if urls:
                return urls[-1]  # 取最新的URL
        except Exception as e:
            logger.warning("日志解密失败: %s", str(e))
        return ""

    def _parse_webview_url(self, url):
        if "#" in url:
            h = url.split("#", 1)[1]
            if "?" in h:
                q = h.split("?", 1)[1]
                return {k: v[0] for k, v in parse_qs(q).items()}
        if "?" in url:
            return {k: v[0] for k, v in parse_qs(url.split("?", 1)[1]).items()}
        return {}

    def fetch_records(self, url=None, account_id=None, latest_time=None):
        if not url:
            self._report_progress("获取抽卡URL...", 0.05)
            url = self._get_url_from_log()
            if not url:
                self._report_progress("从缓存提取...", 0.1)
                url = self.cache.extract_url("wutheringwaves")
        if not url:
            raise FetcherError("无法获取鸣潮抽卡URL。请确保已打开游戏并进入抽卡记录页面。")
        url = URLParser.clean_url(url)
        params = self._parse_webview_url(url)
        if not params.get("player_id"):
            raise FetcherError("URL中缺少必要参数")
        self._detected_uid = params["player_id"]
        pool_types = [1, 2, 3, 4, 5, 8, 9, 10]
        all_records = []
        for idx, pt in enumerate(pool_types):
            if self._cancel_check and self._cancel_check():
                raise FetcherError("用户取消")
            pn = CARD_POOL_TYPE_MAP.get(pt, "character")
            self._report_progress("获取 %s (%d/%d)..." % (pn, idx+1, len(pool_types)), (idx+0.5)/len(pool_types))
            try:
                resp = requests.post(self.API_URL, json={
                    "playerId": params["player_id"], "serverId": params.get("svr_id", ""),
                    "cardPoolId": params.get("resources_id", ""), "cardPoolType": pt,
                    "languageCode": params.get("lang", "zh-Hans"), "recordId": params.get("record_id", ""),
                }, headers={"Content-Type": "application/json"}, timeout=15)
                data = resp.json()
            except Exception as e:
                raise FetcherError("请求失败: %s" % str(e))
            if data.get("code") != 0:
                logger.warning("%s 获取失败: %s" % (pn, data.get("message", "")))
                continue
            for r in data.get("data", []):
                r["_pool_type"] = pn
                r["_card_pool_type"] = pt
            all_records.extend(data.get("data", []))
        result = []
        seen_ids = {}
        for raw in all_records:
            pt_name = raw.get("_pool_type", "character")
            cpn = raw.get("cardPoolType", "")
            if cpn in POOL_NAME_MAP:
                pt_name = POOL_NAME_MAP[cpn]
            rarity = int(raw.get("qualityLevel", 3))
            name = raw.get("name", "")
            is_perm = "常驻" in cpn or "新手" in cpn
            is_std = name in STANDARD_5STAR_CHARACTERS or name in STANDARD_5STAR_WEAPONS
            is_up = (not is_perm) and rarity >= 5 and (not is_std)
            base_id = "%s_%s_%s" % (raw.get("resourceId", ""), raw.get("time", ""), raw.get("_card_pool_type", ""))
            if base_id in seen_ids:
                seen_ids[base_id] += 1
                uid = "%s_%d" % (base_id, seen_ids[base_id])
            else:
                seen_ids[base_id] = 0
                uid = base_id
            result.append(GachaRecord(
                account_id=account_id or 0, game="wutheringwaves", pool_type=pt_name,
                item_id=uid, item_name=name, item_type=raw.get("resourceType", ""),
                rarity=rarity, is_featured=is_up, count=int(raw.get("count", 1)), time=raw.get("time", ""),
            ))
        self._report_progress("完成: %d 条记录" % len(result), 1.0)
        return result