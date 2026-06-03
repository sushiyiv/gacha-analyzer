"""原神抽卡记录获取器"""

from typing import List

from fetchers.mihoyo.base import MihoyoGachaFetcher
from core.models import GachaRecord


class GenshinFetcher(MihoyoGachaFetcher):
    """原神抽卡记录获取器"""

    game_key = "genshin"
    game_name = "原神"
    supported_pools = ["character", "weapon", "standard", "beginner"]
    cache_game_key = "genshin"

    url_missing_tip = (
        "1. 打开原神\n"
        "2. 进入抽卡记录页面\n"
        "3. 等待记录加载完成\n"
        "4. 切回本程序，重新点击获取"
    )
    expired_tip = "authkey已过期。\n\n请重新打开原神，进入抽卡记录页面，然后切回本程序重试。"

    def fetch_records(self, url: str = None, account_id: int = None, latest_time: str = None) -> List[GachaRecord]:
        self._report_progress("正在获取原神抽卡记录...", 0.05)
        return super().fetch_records(url=url, account_id=account_id, latest_time=latest_time)
