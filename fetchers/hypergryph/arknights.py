"""明日方舟抽卡记录获取器"""

import os
import re
import sys
import time
import subprocess
from pathlib import Path
from typing import List, Optional
from urllib.parse import unquote
from fetchers.base import BaseFetcher, FetcherError
from core.models import GachaRecord, ARKNIGHTS_POOL_MECHANIC_MAP, ARKNIGHTS_MECHANIC_TO_GROUP


import logging

logger = logging.getLogger(__name__)


class ArknightsFetcher(BaseFetcher):
    """明日方舟抽卡记录获取器"""

    API_BASE = "https://ak-webview.hypergryph.com/api"

    def get_game_name(self) -> str:
        return "明日方舟"

    def get_supported_pools(self) -> List[str]:
        return ["standard", "kernel", "limited"]

    @staticmethod
    def _cleanup_hosts():
        """清理 hosts 文件中可能残留的代理条目"""
        hosts_marker = "# gacha-analyzer-arknights-proxy"
        hosts_path = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"
        try:
            with open(hosts_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
            if hosts_marker in content:
                lines = [l for l in content.split("\n") if hosts_marker not in l]
                with open(hosts_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write("\n".join(lines))
                # 刷新 DNS
                subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=10)
        except Exception:
            pass

    def _get_u8_token_from_account(self, hg_token: str) -> str:
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
            raise FetcherError("账号验证失败，请检查 Token 是否正确。")

        # 2. app_token -> 绑定列表 -> 明日方舟 UID
        self._report_progress("正在获取账号信息...", 0.2)
        self._rate_limit()
        binding_resp = req.get(
            "https://binding-api-account-prod.hypergryph.com/account/binding/v1/binding_list",
            params={"token": app_token, "appCode": "arknights"},
            timeout=15,
        )
        binding_data = binding_resp.json()
        apps = binding_data.get("data", {}).get("list", [])

        # 找明日方舟的 UID
        uid = None
        for app in apps:
            if app.get("appCode") == "arknights":
                for binding in app.get("bindingList", []):
                    uid = binding.get("uid", "")
                    if uid:
                        break
                break

        if not uid:
            raise FetcherError(
                "未找到明日方舟绑定角色。\n\n"
                "请确保该账号已绑定明日方舟角色。"
            )

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

        self._report_progress(f"已获取明日方舟凭证 (UID: {uid})", 0.4)
        return u8_token

    def _find_token_from_log(self) -> Optional[str]:
        """从 HGWebview.log 中提取 token (u8_token)"""
        log_path = Path.home() / "AppData/LocalLow/Hypergryph/Arknights/sdklogs/HGWebview.log"
        if not log_path.exists():
            return None

        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            return None

        # 优先从 gacha URL 中提取（抽卡记录页面的 token 更有效）
        gacha_pattern = r'https?://ak-webview\.hypergryph\.com/gacha\?[^\s"]*u8_token=([^\s"&]+)'
        gacha_matches = re.findall(gacha_pattern, content)
        if gacha_matches:
            return unquote(gacha_matches[-1])

        # 备用：从任意 URL 中提取
        pattern = r'u8_token=([^\s"&]+)'
        matches = re.findall(pattern, content)
        if not matches:
            return None

        # 取最后一个（最新的），但需要验证是否过期
        return unquote(matches[-1])

    def _get_pool_categories(self, code: str) -> List[dict]:
        """获取卡池列表，返回空列表表示 token 无效或已过期"""
        try:
            resp = self.session.get(
                f"{self.API_BASE}/gacha/cate",
                params={"code": code},
                timeout=self.config.get_request_timeout()
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("code") != 0:
                return []
            result = data.get("data")
            # 有效 token: data 是包含卡池对象的列表
            # 无效 token: data 是空列表
            if isinstance(result, list):
                if result and isinstance(result[0], dict):
                    return result  # 有效卡池列表
                return []  # 空列表 = token 无效
            if isinstance(result, dict):
                return result.get("list", [])
        except Exception:
            pass
        return []

    def _parse_pool_type(self, pool_name: str, pool_id: str = "") -> str:
        """根据卡池ID或名称判断保底分组（standard/kernel/limited）

        poolId 前缀判断：
        - LIMITED_: 限定卡池
        - LINKAGE_: 联动卡池
        - CLASSIC_: 中坚卡池
        - 其他所有: 标准寻访（包括双UP、单UP、联合行动等）
        """
        # 使用 poolId 前缀判断
        if pool_id:
            pool_id_upper = pool_id.upper()
            if pool_id_upper.startswith("LIMITED_"):
                return "limited"
            elif pool_id_upper.startswith("LINKAGE_"):
                return "limited"
            elif pool_id_upper.startswith("CLASSIC_"):
                return "kernel"

        # 备用：使用卡池名称映射
        mechanic = ARKNIGHTS_POOL_MECHANIC_MAP.get(pool_name, "")
        if mechanic:
            return ARKNIGHTS_MECHANIC_TO_GROUP.get(mechanic, "standard")

        # 关键词判断
        for keyword in ["中坚"]:
            if keyword in pool_name:
                return "kernel"
        for keyword in ["标准", "常驻"]:
            if keyword in pool_name:
                return "standard"

        # 未识别的特定卡池默认为独立寻访（limited）
        # 因为绝大多数特定角色卡池都是限时池
        return "limited"

    def fetch_records(self, url: str = None, account_id: int = None, **kwargs) -> List[GachaRecord]:
        """获取明日方舟抽卡记录"""
        # 清理可能残留的 hosts 修改
        self._cleanup_hosts()

        # 获取 token
        token = None
        if url:
            token = url.strip()
        else:
            # 尝试从日志读取
            self._report_progress("正在从游戏日志读取 Token...", 0.05)
            token = self._find_token_from_log()

        # 判断 token 类型并处理
        if token:
            # 短 token（< 50字符）是鹰角账号 token，需要交换
            if len(token) < 50:
                self._report_progress("检测到鹰角账号 Token，正在交换...", 0.1)
                try:
                    token = self._get_u8_token_from_account(token)
                except FetcherError as e:
                    raise FetcherError(f"Token 交换失败：{e}")
            # 长 token 直接当 u8_token 使用

        if not token:
            raise FetcherError(
                "未找到 Token。\n\n"
                "请通过以下方式之一提供：\n"
                "1. 登录获取：点击「登录获取」按钮登录鹰角账号\n"
                "2. 手动粘贴：从抓包工具中复制包含 u8_token 的 URL\n"
                "3. 账号 Token：粘贴从 user.hypergryph.com 获取的 Token"
            )

        self._report_progress("开始获取抽卡记录...", 0.1)

        # 获取卡池列表
        pools = self._get_pool_categories(token)

        # 如果获取不到卡池，可能是日志里的旧 token，尝试当作账号 token 交换
        if not pools and len(token) > 50:
            self._report_progress("Token 可能已过期，尝试其他方式...", 0.1)
            # 无法恢复，提示用户
            raise FetcherError(
                "Token 已过期或无效。\n\n"
                "请通过以下方式重新获取：\n"
                "1. 点击「登录获取」按钮登录鹰角账号\n"
                "2. 或手动粘贴有效的 Token/URL"
            )

        if not pools:
            raise FetcherError(
                "获取卡池列表失败，Token 可能无效。\n\n"
                "请确认 Token 正确后重试，或点击「登录获取」重新登录。\n\n"
                "支持的 Token 格式：\n"
                "- 鹰角账号 Token（短，24字符）\n"
                "- u8_token（长，184字符）\n"
                "- 包含 u8_token 的完整 URL"
            )

        all_records = []

        for pool_info in pools:
            pool_id = pool_info.get("poolId") or pool_info.get("id", "")
            pool_name = pool_info.get("poolName") or pool_info.get("name", "未知卡池")
            pool_type = self._parse_pool_type(pool_name, pool_id)

            # 调试日志：打印卡池信息
            print(f"[DEBUG] 卡池: {pool_name}, poolId: {pool_id}, 分类: {pool_type}")

            self._report_progress(f"正在获取卡池: {pool_name}...", 0.2)

            page = 1
            last_gacha_ts = ""
            last_pos = ""

            while True:
                self._rate_limit()
                try:
                    params = {
                        "code": token,
                        "category": pool_id,
                    }
                    if last_gacha_ts:
                        params["gachaTs"] = last_gacha_ts
                    if last_pos:
                        params["pos"] = last_pos

                    resp = self.session.get(
                        f"{self.API_BASE}/gacha/history",
                        params=params,
                        timeout=self.config.get_request_timeout()
                    )
                    resp.raise_for_status()
                    data = resp.json()

                    if data.get("code") != 0:
                        break

                    records = data.get("data", {}).get("list", [])
                    if not records:
                        break

                    for raw in records:
                        gacha_ts = raw.get("gachaTs", 0)

                        # gachaTs 是毫秒时间戳字符串
                        try:
                            ts = int(gacha_ts) / 1000
                            record_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
                        except (ValueError, TypeError, OSError):
                            record_time = ""

                        # 每条记录就是一个角色（不是嵌套结构）
                        char_name = raw.get("charName", "未知")
                        rarity = raw.get("rarity", 0)
                        # 方舟 rarity: 0=1星, 1=2星, 2=3星, 3=4星, 4=5星, 5=6星
                        # 转换为标准星级: +1
                        rarity = rarity + 1

                        # 优先用记录里的 poolName（具体卡池名），其次用池列表的名称
                        record_pool_name = raw.get("poolName", "") or pool_name

                        # 生成唯一 item_id: 角色名_时间（与小黑盒导入格式一致）
                        unique_id = f"{char_name}_{record_time}"

                        record = GachaRecord(
                            account_id=account_id or 0,
                            game="arknights",
                            pool_type=pool_type,
                            pool_name=record_pool_name,
                            item_id=unique_id,
                            item_name=char_name,
                            item_type="CHAR",
                            rarity=rarity,
                            is_featured=False,
                            count=1,
                            time=record_time,
                            gacha_id=raw.get("poolId", pool_id),
                            raw_data=str(raw),
                        )
                        all_records.append(record)

                    # 检查是否还有更多
                    has_more = data.get("data", {}).get("hasMore", False)
                    if not has_more:
                        break

                    # 更新分页参数
                    last_record = records[-1]
                    last_gacha_ts = str(last_record.get("gachaTs", ""))
                    last_pos = str(last_record.get("pos", ""))

                    page += 1
                    time.sleep(0.5)

                except Exception as e:
                    if isinstance(e, FetcherError):
                        raise
                    break

        self._report_progress(f"获取完成，共 {len(all_records)} 条记录", 1.0)
        return all_records
