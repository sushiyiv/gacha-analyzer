"""星穹铁道抽卡记录获取器"""

from typing import List

from fetchers.mihoyo.base import MihoyoGachaFetcher
from core.models import GachaRecord


class StarRailFetcher(MihoyoGachaFetcher):
    """星穹铁道抽卡记录获取器"""

    game_key = "starrail"
    game_name = "崩坏：星穹铁道"
    supported_pools = ["character", "weapon", "standard", "beginner"]
    cache_game_key = "starrail"

    url_missing_tip = (
        "1. 打开崩坏：星穹铁道\n"
        "2. 进入跃迁记录页面\n"
        "3. 等待记录加载完成\n"
        "4. 切回本程序，重新点击获取"
    )
    expired_tip = "authkey已过期。\n\n请重新打开崩坏：星穹铁道，进入跃迁记录页面，然后切回本程序重试。"

    def fetch_records(self, url: str = None, account_id: int = None, latest_time: str = None) -> List[GachaRecord]:
        self._report_progress("正在获取星穹铁道抽卡记录...", 0.05)
        return super().fetch_records(url=url, account_id=account_id, latest_time=latest_time)
