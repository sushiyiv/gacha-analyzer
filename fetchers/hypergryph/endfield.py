"""终末地抽卡记录获取器 - 支持日志提取、账号 Token 和第三方 API 三种方式"""

import ast
import os
import re
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote
from typing import List, Optional, Tuple
from fetchers.base import BaseFetcher, FetcherError
from core.models import GachaRecord, ENDFIELD_STANDARD_6STAR

# 终末地角色池类型
CHAR_POOL_TYPES = [
    "E_CharacterGachaPoolType_Special",
    "E_CharacterGachaPoolType_Joint",
    "E_CharacterGachaPoolType_Standard",
    "E_CharacterGachaPoolType_Beginner",
]

# API 返回的 pool_type → 项目内部 pool_type 映射
_POOL_TYPE_MAP = {
    "E_CharacterGachaPoolType_Special": "limited",     # 特许寻访（限定池）
    "E_CharacterGachaPoolType_Joint": "joint",         # 辉光庆典（联合寻访）
    "E_CharacterGachaPoolType_Standard": "character",  # 基础寻访
    "E_CharacterGachaPoolType_Beginner": "beginner",   # 启程寻访
}

def _parse_gacha_ts(ts) -> str:
    """将 gachaTs（毫秒时间戳）转换为 datetime 字符串（含毫秒）"""
    if not ts:
        return ""
    try:
        ts_int = int(ts)
        if ts_int > 1e12:  # 毫秒时间戳
            dt = datetime.fromtimestamp(ts_int / 1000)
            return dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{ts_int % 1000:03d}"
        return datetime.fromtimestamp(ts_int).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError, TypeError):
        return ""


def _compare_seq_id(a: str, b: str) -> int:
    """比较两个 seq_id，返回 1(a>b), 0(a==b), -1(a<b)"""
    if a == b:
        return 0
    a_digit = a.isdigit()
    b_digit = b.isdigit()
    if a_digit and b_digit:
        if len(a) != len(b):
            return 1 if len(a) > len(b) else -1
        return 1 if a > b else -1
    if a_digit != b_digit:
        return 1 if a_digit else -1
    return 1 if a > b else -1


def _get_max_seq_id(records: List[GachaRecord]) -> str:
    """从记录列表中获取最大 seq_id"""
    max_id = ""
    for r in records:
        try:
            raw = ast.literal_eval(r.raw_data) if r.raw_data else {}
            sid = str(raw.get("seqId", ""))
            if sid and _compare_seq_id(sid, max_id) > 0:
                max_id = sid
        except Exception:
            pass
    return max_id


class EndfieldFetcher(BaseFetcher):
    """终末地抽卡记录获取器"""

    def get_game_name(self) -> str:
        return "终末地"

    def get_supported_pools(self) -> List[str]:
        return ["limited", "joint", "character", "weapon", "beginner"]

    def _find_u8_token_from_log(self) -> Optional[Tuple[str, str]]:
        """从 HGWebview.log 中提取 u8_token（旧版游戏）"""
        log_path = Path.home() / "AppData/LocalLow/Hypergryph/Endfield/sdklogs/HGWebview.log"
        if not log_path.exists():
            return None

        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            return None

        pattern = r'https://ef-webview\.(hypergryph|gryphline)\.com/[^\s"]*u8_token=([^\s"&]+)'
        matches = re.findall(pattern, content)
        if not matches:
            return None

        provider, token_encoded = matches[-1]
        return unquote(token_encoded), provider

    def _get_u8_token_from_account(self, hg_token: str) -> Tuple[str, str]:
        """通过鹰角账号 token 获取 u8_token"""
        import requests as req

        # 1. hg_token -> app_token
        self._report_progress("正在验证账号...", 0.1)
        self._rate_limit()
        grant_resp = req.post(
            "https://as.hypergryph.com/user/oauth2/v2/grant",
            json={"type": 1, "appCode": "be36d44aa36bfb5b", "token": hg_token},
            timeout=15,
        )
        grant_data = grant_resp.json()
        app_token = grant_data.get("data", {}).get("token")
        if not app_token:
            msg = grant_data.get("msg", "未知错误")
            raise FetcherError(f"账号验证失败: {msg}")

        # 2. app_token -> binding list -> UID
        self._report_progress("正在获取账号信息...", 0.2)
        self._rate_limit()
        binding_resp = req.get(
            "https://binding-api-account-prod.hypergryph.com/account/binding/v1/binding_list",
            params={"token": app_token, "appCode": "endfield"},
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"},
            timeout=15,
        )
        binding_data = binding_resp.json()
        apps = binding_data.get("data", {}).get("list", [])

        # 找终末地的 UID（嵌套结构：app.bindingList[].uid）
        uid = None
        for app in apps:
            if app.get("appCode") == "endfield":
                for binding in app.get("bindingList", []):
                    uid = binding.get("uid", "")
                    if uid:
                        break
                break

        if not uid:
            raise FetcherError("未找到终末地绑定角色。请确保该账号已绑定终末地。")

        # 保存检测到的 UID
        self._detected_uid = uid

        # 3. UID + app_token -> u8_token
        self._report_progress("正在获取抽卡凭证...", 0.3)
        self._rate_limit()
        u8_resp = req.post(
            "https://binding-api-account-prod.hypergryph.com/account/binding/v1/u8_token_by_uid",
            json={"uid": uid, "token": app_token},
            timeout=15,
        )
        u8_data = u8_resp.json()
        u8_token = u8_data.get("data", {}).get("token")
        if not u8_token:
            raise FetcherError("获取抽卡凭证失败，可能触发了风控限制。请稍后再试。")

        return u8_token, "hypergryph"

    def _get_u8_token(self, url: str = None) -> Tuple[str, str]:
        """获取 u8_token，优先从日志提取，其次从 URL 参数提取"""
        # 方式1：从日志提取
        result = self._find_u8_token_from_log()
        if result:
            return result

        # 方式2：从 URL 参数提取（用户手动粘贴的 token）
        if url:
            # URL 可能是直接的 u8_token，也可能是鹰角账号 token
            if "ef-webview" in url and "u8_token=" in url:
                # 直接是抽卡链接
                match = re.search(r'u8_token=([^&]+)', url)
                if match:
                    provider = "gryphline" if "gryphline" in url else "hypergryph"
                    return unquote(match.group(1)), provider
            elif len(url) > 50:
                # 长 token，当作鹰角账号 token
                return self._get_u8_token_from_account(url.strip())
            else:
                # 短 token，可能是 framework_token，不应该到这里
                raise FetcherError("凭证格式不正确，请重新登录获取")

        raise FetcherError(
            "未找到抽卡凭证。\n\n"
            "请通过以下方式之一获取：\n"
            "1. 在游戏内打开抽卡记录页面（旧版游戏会写入日志）\n"
            "2. 登录 https://user.hypergryph.com/ 获取 Token 并粘贴"
        )

    def _check_token_error(self, resp: dict) -> None:
        """检查 token 错误"""
        code = resp.get("code", 0)
        if code == 40100:
            raise FetcherError(
                "Token 已过期。\n\n"
                "请在游戏内重新打开一次抽卡记录页面，或重新登录获取新 Token。"
            )

    def _fetch_char_records(self, u8_token: str, provider: str, server_id: str = "1", stop_seq_ids: dict = None) -> List[GachaRecord]:
        """获取角色池记录（支持增量同步）"""
        all_records = []
        lang = "zh-cn"

        for api_pool_type in CHAR_POOL_TYPES:
            internal_pool_type = _POOL_TYPE_MAP.get(api_pool_type, "character")
            # 按池类型获取对应的 stop_seq_id
            stop_seq_id = (stop_seq_ids or {}).get(internal_pool_type, "")
            self._report_progress(f"正在获取角色池: {api_pool_type}...", 0.4)
            seq_id = ""
            has_more = True

            while has_more:
                params = {
                    "lang": lang,
                    "token": u8_token,
                    "server_id": server_id,
                    "pool_type": api_pool_type,
                }
                if seq_id:
                    params["seq_id"] = seq_id

                url = f"https://ef-webview.{provider}.com/api/record/char"
                try:
                    resp = self._request(url, params=params)
                except FetcherError:
                    has_more = False
                    break

                self._check_token_error(resp)
                if resp.get("code") != 0:
                    has_more = False
                    break

                data = resp.get("data", {})
                records_list = data.get("list", [])
                has_more_flag = data.get("hasMore", False)

                # 调试日志写入文件
                with open("debug_endfield.log", "a", encoding="utf-8") as f:
                    f.write(f"{api_pool_type}: 本页{len(records_list)}条, hasMore={has_more_flag}, stop_seq_id='{stop_seq_id}', seq_id='{seq_id}'\n")
                    if records_list:
                        f.write(f"  首条: seqId={records_list[0].get('seqId')}, 尾条: seqId={records_list[-1].get('seqId')}\n")

                # 增量同步：过滤掉已有的旧记录
                if stop_seq_id:
                    new_only = [r for r in records_list
                                if _compare_seq_id(str(r.get("seqId", "")), stop_seq_id) > 0]
                    with open("debug_endfield.log", "a", encoding="utf-8") as f:
                        f.write(f"  增量过滤: {len(records_list)} -> {len(new_only)}\n")
                    if len(new_only) < len(records_list):
                        records_list = new_only
                        has_more = False  # 遇到旧记录，后续页面更旧，停止

                for raw in records_list:
                    item_name = raw.get("charName", "未知")
                    rarity = int(raw.get("rarity", 3))
                    # 6星：不在常驻列表中 = UP物品
                    is_featured = (rarity == 6 and item_name not in ENDFIELD_STANDARD_6STAR)
                    record = GachaRecord(
                        account_id=0,
                        game="endfield",
                        pool_type=internal_pool_type,
                        pool_name=raw.get("poolName", ""),
                        item_id=str(raw.get("seqId", "")),
                        item_name=item_name,
                        item_type="角色",
                        rarity=rarity,
                        is_featured=is_featured,
                        count=1,
                        time=_parse_gacha_ts(raw.get("gachaTs", "")),
                        gacha_id=raw.get("poolId", ""),
                        raw_data=str(raw),
                    )
                    all_records.append(record)

                has_more = bool(data.get("hasMore", False))
                if records_list:
                    seq_id = records_list[-1].get("seqId", "")

        return all_records

    def _fetch_weapon_records(self, u8_token: str, provider: str, server_id: str = "1", stop_seq_ids: dict = None) -> List[GachaRecord]:
        """获取武器池记录（支持增量同步）"""
        all_records = []
        lang = "zh-cn"

        self._report_progress("正在获取武器池列表...", 0.7)

        pool_url = f"https://ef-webview.{provider}.com/api/record/weapon/pool"
        try:
            pool_resp = self._request(pool_url, params={
                "lang": lang,
                "token": u8_token,
                "server_id": server_id,
            })
        except FetcherError:
            return all_records

        self._check_token_error(pool_resp)
        if pool_resp.get("code") != 0:
            return all_records

        pools = pool_resp.get("data", [])

        for pool in pools:
            pool_id = pool.get("poolId", "")
            pool_name = pool.get("poolName", pool_id)
            self._report_progress(f"正在获取武器池: {pool_name}...", 0.8)

            # 按池类型获取对应的 stop_seq_id
            stop_seq_id = (stop_seq_ids or {}).get("weapon", "")
            seq_id = ""
            has_more = True

            while has_more:
                params = {
                    "lang": lang,
                    "token": u8_token,
                    "server_id": server_id,
                    "pool_id": pool_id,
                }
                if seq_id:
                    params["seq_id"] = seq_id

                url = f"https://ef-webview.{provider}.com/api/record/weapon"
                try:
                    resp = self._request(url, params=params)
                except FetcherError:
                    has_more = False
                    break

                self._check_token_error(resp)
                if resp.get("code") != 0:
                    has_more = False
                    break

                data = resp.get("data", {})
                records_list = data.get("list", [])

                # 增量同步：过滤掉已有的旧记录
                if stop_seq_id:
                    new_only = [r for r in records_list
                                if _compare_seq_id(str(r.get("seqId", "")), stop_seq_id) > 0]
                    if len(new_only) < len(records_list):
                        records_list = new_only
                        has_more = False

                for raw in records_list:
                    item_name = raw.get("weaponName", "未知")
                    rarity = int(raw.get("rarity", 3))
                    # 6星：不在常驻列表中 = UP物品
                    is_featured = (rarity == 6 and item_name not in ENDFIELD_STANDARD_6STAR)
                    record = GachaRecord(
                        account_id=0,
                        game="endfield",
                        pool_type="weapon",
                        pool_name=raw.get("poolName", ""),
                        item_id=str(raw.get("seqId", "")),
                        item_name=item_name,
                        item_type="武器",
                        rarity=rarity,
                        is_featured=is_featured,
                        count=1,
                        time=_parse_gacha_ts(raw.get("gachaTs", "")),
                        gacha_id=pool_id,
                        raw_data=str(raw),
                    )
                    all_records.append(record)

                has_more = bool(data.get("hasMore", False))
                if records_list:
                    seq_id = records_list[-1].get("seqId", "")

                if has_more:
                    time.sleep(0.5)

        return all_records

    def _fetch_from_third_party(self, framework_token: str) -> List[GachaRecord]:
        """通过第三方 API 获取抽卡记录（已弃用）"""
        raise FetcherError(
            "第三方 API 方式已弃用。\n\n"
            "请使用「登录获取」按钮，通过鹰角官网登录获取 Token。"
        )

    def fetch_records(self, url: str = None, account_id: int = None, **kwargs) -> List[GachaRecord]:
        """获取终末地抽卡记录（支持增量同步）"""
        self._report_progress("正在获取抽卡凭证...", 0.05)

        # 获取已有记录的最大 seq_id，用于增量同步（独立连接，按卡池类型分别记录）
        stop_seq_ids = {}  # {pool_type: max_seq_id}
        if account_id:
            import sqlite3
            from core.config import Config
            cfg = Config()
            try:
                conn = sqlite3.connect(cfg.db_path)
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT pool_type, raw_data FROM gacha_records WHERE account_id=? AND game='endfield'",
                    (account_id,)
                ).fetchall()
                conn.close()
                for row in rows:
                    d = dict(row)
                    pool_type = d.get("pool_type", "")
                    raw_str = d.get("raw_data", "")
                    if not pool_type or not raw_str:
                        continue
                    try:
                        raw = ast.literal_eval(raw_str)
                        sid = str(raw.get("seqId", ""))
                        if sid:
                            if pool_type not in stop_seq_ids or _compare_seq_id(sid, stop_seq_ids[pool_type]) > 0:
                                stop_seq_ids[pool_type] = sid
                    except Exception:
                        pass
                if stop_seq_ids:
                    self._report_progress(f"增量同步，各池最大ID: {stop_seq_ids}", 0.05)
            except Exception:
                pass

        # 判断 token 类型
        # hg_token: ~24位，从官网获取，需要交换为 u8_token
        # framework_token: 36位 UUID 格式，用于第三方 API
        # u8_token: 100+位，用于官方 API
        if url and not url.startswith("http"):
            token = url.strip()
            # UUID 格式（含 '-'，36位）是 framework_token
            if len(token) == 36 and token.count('-') == 4:
                self._report_progress("使用扫码登录凭证获取记录...", 0.1)
                all_records = self._fetch_from_third_party(token)
            else:
                # 其他短 token 当作 hg_token，交换为 u8_token
                self._report_progress("检测到账号 Token，正在交换...", 0.1)
                try:
                    u8_token, provider = self._get_u8_token_from_account(token)
                    self._report_progress("已获取凭证，开始获取记录...", 0.2)
                    all_records = []
                    char_records = self._fetch_char_records(u8_token, provider, stop_seq_ids=stop_seq_ids)
                    all_records.extend(char_records)
                    weapon_records = self._fetch_weapon_records(u8_token, provider, stop_seq_ids=stop_seq_ids)
                    all_records.extend(weapon_records)
                except FetcherError:
                    raise
                except Exception as e:
                    raise FetcherError(f"Token 交换失败: {e}")
        elif url and "ef-webview" in url:
            u8_token, provider = self._get_u8_token(url)
            all_records = []
            char_records = self._fetch_char_records(u8_token, provider, stop_seq_ids=stop_seq_ids)
            all_records.extend(char_records)
            weapon_records = self._fetch_weapon_records(u8_token, provider, stop_seq_ids=stop_seq_ids)
            all_records.extend(weapon_records)
        else:
            result = self._find_u8_token_from_log()
            if result:
                u8_token, provider = result
                all_records = []
                char_records = self._fetch_char_records(u8_token, provider, stop_seq_ids=stop_seq_ids)
                all_records.extend(char_records)
                weapon_records = self._fetch_weapon_records(u8_token, provider, stop_seq_ids=stop_seq_ids)
                all_records.extend(weapon_records)
            else:
                raise FetcherError(
                    "未找到抽卡凭证。\n\n"
                    "请通过以下方式之一获取：\n"
                    "1. 点击「登录获取」按钮扫码登录\n"
                    "2. 在游戏内打开抽卡记录页面\n"
                    "3. 粘贴鹰角账号 Token"
                )

        # 设置 account_id
        if account_id:
            for r in all_records:
                r.account_id = account_id

        sync_type = "增量" if stop_seq_ids else "全量"
        self._report_progress(f"{sync_type}同步完成，获取 {len(all_records)} 条新记录", 1.0)
        return all_records
