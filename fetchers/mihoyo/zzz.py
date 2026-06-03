"""绝区零抽卡记录获取器"""

from typing import List

from fetchers.mihoyo.base import MihoyoGachaFetcher
from core.models import GachaRecord


class ZZZFetcher(MihoyoGachaFetcher):
    """绝区零抽卡记录获取器"""

    game_key = "zzz"
    game_name = "绝区零"
    supported_pools = ["character", "weapon", "standard"]
    cache_game_key = "zzz"

    url_missing_tip = (
        "1. 打开绝区零\n"
        "2. 进入调频记录页面\n"
        "3. 等待记录加载完成\n"
        "4. 切回本程序，重新点击获取"
    )
    expired_tip = "authkey已过期。\n\n请重新打开绝区零，进入调频记录页面，然后切回本程序重试。"

    def fetch_records(self, url: str = None, account_id: int = None, latest_time: str = None) -> List[GachaRecord]:
        self._report_progress("正在获取绝区零抽卡记录...", 0.05)
        return super().fetch_records(url=url, account_id=account_id, latest_time=latest_time)
