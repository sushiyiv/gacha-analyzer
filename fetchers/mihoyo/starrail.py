
"""星穹铁道抽卡记录获取器"""

from typing import List

from fetchers.mihoyo.base import MihoyoGachaFetcher
from core.models import GachaRecord


class StarRailFetcher(MihoyoGachaFetcher):
    """崩坏：星穹铁道抽卡记录获取器

    继承自 MihoyoGachaFetcher，通过设置类属性来适配星铁游戏:
    - game_key "starrail" 会被传递给 MihoyoAPI.fetch_all() 选择正确的API端点
    - supported_pools 定义了星铁的4种卡池类型
    - cache_game_key 用于从本地缓存中定位星铁的跃迁记录URL
    """


    game_key = "starrail"

    game_name = "崩坏：星穹铁道"

    supported_pools = ["character", "weapon", "standard", "beginner", "collab", "collab_weapon"]

    cache_game_key = "starrail"


    url_missing_tip = (
        "1. 打开崩坏：星穹铁道\n"
        "2. 进入跃迁记录页面\n"
        "3. 等待记录加载完成\n"
        "4. 切回本程序，重新点击获取"
    )

    expired_tip = "authkey已过期。\n\n请重新打开崩坏：星穹铁道，进入跃迁记录页面，然后切回本程序重试。"


    def fetch_records(self, url: str = None, account_id: int = None, latest_time: str = None) -> List[GachaRecord]:
        """获取崩坏：星穹铁道抽卡记录

        在父类的 fetch_records() 方法基础上，添加星铁特有的初始进度提示。
        实际获取逻辑全部由父类 MihoyoGachaFetcher.fetch_records() 完成。

        参数:
            url (str, 可选): 跃迁记录的API URL。为None时自动从缓存获取。
            account_id (int, 可选): 米哈游账号ID，用于区分不同账号的记录。
            latest_time (str, 可选): 增量获取的截止时间参数。

        返回:
            List[GachaRecord]: 星铁跃迁记录列表，每条记录包含:
                - 物品名称、稀有度、类型
                - 所属卡池类型
                - 是否为UP角色/光锥
                - 抽卡时间
                - 原始API数据
        """
        self._report_progress("正在获取星穹铁道抽卡记录...", 0.05)

        return super().fetch_records(url=url, account_id=account_id, latest_time=latest_time)
