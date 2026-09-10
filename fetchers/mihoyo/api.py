"""米哈游通用抽卡记录 API"""

import logging
import requests
from typing import List
from urllib.parse import urlparse, parse_qs

from core.models import GachaRecord
from core.config import Config

logger = logging.getLogger(__name__)


class APIError(Exception):
    pass


class MihoyoAPI:
    ENDPOINTS = {
        "genshin": "https://public-operation-hk4e.mihoyo.com/gacha_info/api/getGachaLog",
        "starrail": "https://public-operation-hkrpg.mihoyo.com/common/gacha_record/api/getGachaLog",
        "zzz": "https://public-operation-nap.mihoyo.com/common/gacha_record/api/getGachaLog",
    }

    COLLAB_ENDPOINTS = {
        "starrail": "https://public-operation-hkrpg.mihoyo.com/common/gacha_record/api/getLdGachaLog",
    }

    GACHA_TYPES = {
        "genshin": {
            "character": "301",
            "weapon": "302",
            "chronicled": "400",
            "standard": "200",
            "beginner": "100",
        },
        "starrail": {
            "character": "11",
            "weapon": "12",
            "standard": "1",
            "beginner": "2",
            "collab": "21",
            "collab_weapon": "22",
        },
        "zzz": {
            "character": "2",
            "weapon": "3",
            "special": "102",
            "special_weapon": "103",
            "bangboo": "5",
            "standard": "1",
        },
        "wutheringwaves": {
            "character": "1",
            "weapon": "2",
            "standard_character": "3",
            "standard_weapon": "4",
            "beginner": "5",
            "selector": "8",
            "selector_weapon": "9",
        },
    }

    STANDARD_5STAR = {
        "genshin": {
            "character": ["迪希雅", "提纳里", "梦见月瑞希", "刻晴", "莫娜", "七七", "迪卢克", "琴"],
            "weapon": [
                "天空之刃", "风鹰剑", "狼的末路", "天空之傲", "和璞鸢",
                "天空之脊", "四风原典", "天空之卷", "阿莫斯之弓", "天空之翼",
            ],
        },
        "starrail": {
            "character": ["布洛妮娅", "克拉拉", "杰帕德", "白露", "姬子", "瓦尔特", "彦卿"],
            "weapon": [
                "但战斗还未结束", "时节不居", "无可取代的东西", "银河铁道之夜",
                "制胜的瞬间", "如泥酣眠", "以世界之名",
            ],
        },
        "zzz": {
            "character": ["莱卡恩", "11号", "珂蕾妲", "丽娜", "格莉丝", "猫又"],
            "weapon": [
                "硫磺石", "燃狱齿轮", "钢铁肉垫", "啜泣摇篮", "嵌合编译器", "拘缚者",
            ],
        },
        "wutheringwaves": {
            "character": ["维里奈", "安可", "鉴心", "卡卡罗", "凌阳"],
            "weapon": [
                "浩境粼光", "千古洑流", "停驻之烟", "擎渊怒涛", "漪澜浮录",
                "源能机锋", "镭射切变", "相位涟漪", "脉冲协臂", "玻色星仪",
            ],
        },
    }

    # 往期限定进入可歪池后，按抽卡时间判断是否仍算 UP
    LOSEABLE_5STAR_WITH_DATE = {
        ("genshin", "character"): {
            "提纳里": "2022-09-28",
            "迪希雅": "2023-04-12",
        },
        ("starrail", "character"): {
            "希儿": "2025-04-09",
            "刃": "2025-04-09",
            "符玄": "2025-04-09",
            "云璃": "2026-04-22",
            "银枝": "2026-04-22",
            "银狼": "2026-04-22",
        },
    }

    def __init__(self):
        self.config = Config()

    def fetch_all(self, game: str, url: str, progress_callback=None,
                  latest_time: str = None, cancel_check=None, session=None) -> tuple:
        """分页拉取全部卡池记录，返回 (raw_records, detected_uid)。"""
        http = session if session is not None else requests
        parsed = urlparse(url)
        base_params = parse_qs(parsed.query)

        endpoint = self.ENDPOINTS.get(game)
        if not endpoint:
            endpoint = f"{parsed.scheme}://{parsed.hostname}{parsed.path}"

        auth_params = {}
        for key in ["authkey", "authkey_ver", "sign_type", "game_biz",
                    "region", "auth_appid", "plat_type", "lang"]:
            if key in base_params:
                auth_params[key] = base_params[key][0]

        zzz_params = {}
        if game == "zzz":
            for key in ["real_gacha_type", "init_log_gacha_base_type"]:
                if key in base_params:
                    zzz_params[key] = base_params[key][0]

        collab_extra_params = {}
        for key in ["gacha_id", "decide_item_id_list", "timestamp"]:
            if key in base_params:
                val = base_params[key][0]
                if key == "decide_item_id_list":
                    from urllib.parse import unquote
                    val = unquote(val)
                collab_extra_params[key] = val

        all_records = []
        detected_uid = ""
        gacha_types = self.GACHA_TYPES.get(game, {})
        total_pools = len(gacha_types)
        current_pool_idx = 0
        max_pages = 500  # 纯安全阀，正常全量也远到不了

        for pool_name, gacha_type_id in gacha_types.items():
            if pool_name in ("collab", "collab_weapon") and game in self.COLLAB_ENDPOINTS:
                pool_endpoint = self.COLLAB_ENDPOINTS[game]
            else:
                pool_endpoint = endpoint

            pool_progress = current_pool_idx / max(total_pools, 1)
            page = 1
            end_id = "0"
            pool_total = 0
            pool_start_idx = len(all_records)
            reached_known_history = False

            if progress_callback:
                progress_callback(f"开始获取 {pool_name} 记录...", pool_progress)

            while True:
                if cancel_check and cancel_check():
                    raise APIError("用户取消")

                params = {
                    **auth_params,
                    "lang": "zh-cn",
                    "page": str(page),
                    "size": "20",
                    "end_id": end_id,
                }
                if game == "zzz":
                    params.update(zzz_params)
                    params["real_gacha_type"] = gacha_type_id
                else:
                    params["gacha_type"] = gacha_type_id
                if pool_name in ("collab", "collab_weapon"):
                    params.update(collab_extra_params)

                try:
                    resp = http.get(pool_endpoint, params=params, timeout=(5, 30))
                    try:
                        data = resp.json()
                    except Exception as e:
                        raise APIError(f"解析响应失败: {str(e)}\n响应内容: {resp.text[:200]}")

                    if data.get("retcode") != 0:
                        msg = data.get("message", "未知错误")
                        msg_lower = msg.lower()
                        if any(k in msg_lower for k in ["authkey", "auth key", "expired", "time out"]):
                            raise APIError("authkey 已过期，请重新获取")
                        if "frequently" in msg_lower or "频繁" in msg:
                            import time as _time
                            if progress_callback:
                                progress_callback(
                                    f"{pool_name} 请求过快，稍候重试...",
                                    pool_progress,
                                )
                            _time.sleep(2.5)
                            continue
                        if progress_callback:
                            progress_callback(
                                f"{pool_name} 获取失败: {msg}，跳过",
                                pool_progress + 1.0 / max(total_pools, 1),
                            )
                        break

                    records = data.get("data", {}).get("list", [])
                    if not records:
                        records = data.get("data", {}).get("list_v2", [])
                    if not records:
                        resp_info = (
                            f"retcode={data.get('retcode')}, "
                            f"data_keys={list(data.get('data', {}).keys()) if data.get('data') else 'None'}, "
                            f"list_len={len(data.get('data', {}).get('list', [])) if data.get('data') else 0}"
                        )
                        if progress_callback:
                            progress_callback(
                                f"{pool_name} 返回0条，{resp_info}",
                                pool_progress + 1.0 / max(total_pools, 1),
                            )
                        break

                    if not detected_uid:
                        for r in records:
                            if r.get("uid"):
                                detected_uid = str(r["uid"])
                                break

                    # API newest-first；有 latest_time 时只保留更新的记录并尽早停
                    page_records = records
                    if latest_time:
                        page_records = [
                            r for r in records
                            if (r.get("time") or "") > latest_time
                        ]
                        oldest_on_page = records[-1].get("time") or ""
                        if oldest_on_page and oldest_on_page <= latest_time:
                            reached_known_history = True

                    for record in page_records:
                        record["_pool_type"] = pool_name

                    all_records.extend(page_records)
                    pool_total += len(page_records)
                    end_id = records[-1].get("id", "0")
                    page += 1

                    if progress_callback:
                        page_progress = min(page / 50, 1.0) / max(total_pools, 1)
                        progress_callback(
                            f"正在获取 {pool_name} 记录... 第{page-1}页 ({pool_total}条)",
                            pool_progress + page_progress,
                        )

                    if reached_known_history:
                        break

                    if page > max_pages:
                        logger.warning("%s 超过 %d 页安全上限，共 %d 条", pool_name, max_pages, pool_total)
                        if progress_callback:
                            progress_callback(
                                f"{pool_name} 达到安全页数上限，共 {pool_total} 条（历史可能不全）",
                                pool_progress + 1.0 / max(total_pools, 1),
                            )
                        break

                except requests.exceptions.Timeout:
                    logger.error("米哈游API请求超时")
                    raise APIError("网络请求超时，请检查网络连接后重试")
                except requests.exceptions.ConnectionError:
                    if cancel_check and cancel_check():
                        raise APIError("用户取消")
                    logger.error("米哈游API连接失败")
                    raise APIError("网络连接失败，请检查网络连接后重试")
                except requests.exceptions.RequestException as e:
                    if cancel_check and cancel_check():
                        raise APIError("用户取消")
                    logger.error("米哈游API请求失败: %s", e)
                    raise APIError(f"网络请求失败: {str(e)}")

            # API 返回 newest-first，反转为 oldest-first 以便保底按 id 顺序算
            all_records[pool_start_idx:] = reversed(all_records[pool_start_idx:])
            current_pool_idx += 1

        return all_records, detected_uid

    @staticmethod
    def parse_record(raw: dict, game: str, account_id: int) -> GachaRecord:
        pool_type = raw.get("_pool_type", "character")

        rank_type = int(raw.get("rank_type", raw.get("rarity", "3")))
        # ZZZ 的 rank_type 比实际星级少 1
        rarity = rank_type + 1 if game == "zzz" else rank_type

        item_name = raw.get("name", "未知")

        if game == "zzz":
            raw_gacha_type = str(raw.get("gacha_type", ""))
            if raw_gacha_type == "5":
                pool_type = "bangboo"
            elif raw_gacha_type == "1":
                pool_type = "standard"
            elif raw_gacha_type == "2":
                pool_type = "special" if pool_type == "special" else "character"
            elif raw_gacha_type == "3":
                pool_type = "special_weapon" if pool_type == "special_weapon" else "weapon"
            elif raw_gacha_type == "102":
                pool_type = "special"
            elif raw_gacha_type == "103":
                pool_type = "special_weapon"

        item_type = raw.get("item_type", "")
        record_time = raw.get("time", "")

        from core.models import get_max_rarity
        is_featured = False
        if rarity == get_max_rarity(game):
            if pool_type in ["standard", "beginner"]:
                is_featured = False
            else:
                lookup_type = pool_type
                if pool_type == "collab":
                    lookup_type = "character"
                elif pool_type == "collab_weapon":
                    lookup_type = "weapon"
                standard_items = MihoyoAPI.STANDARD_5STAR.get(game, {}).get(lookup_type, [])
                loseable_info = MihoyoAPI.LOSEABLE_5STAR_WITH_DATE.get((game, lookup_type), {})
                if item_name in loseable_info:
                    loseable_date = loseable_info[item_name]
                    is_featured = not (record_time and record_time >= loseable_date)
                elif item_name not in standard_items:
                    is_featured = True

        return GachaRecord(
            account_id=account_id,
            game=game,
            pool_type=pool_type,
            item_id=raw.get("id", ""),
            item_name=item_name,
            item_type=item_type,
            rarity=rarity,
            is_featured=is_featured,
            count=int(raw.get("count", "1")),
            time=raw.get("time", ""),
            gacha_id=raw.get("gacha_id", ""),
            pull_index=0,
            raw_data=str(raw),
        )

    @staticmethod
    def get_uid_from_records(records: list) -> str:
        for record in records:
            if isinstance(record, dict):
                uid = record.get("uid")
            else:
                uid = getattr(record, "uid", None)
            if uid:
                return str(uid)
        return ""

    @staticmethod
    def get_user_info(game: str, uid: str, region: str) -> dict:
        # 公开 API 无登录态，拿不到昵称，上层用 UID 显示
        return {}
