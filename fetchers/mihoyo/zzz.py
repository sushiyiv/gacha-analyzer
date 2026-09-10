
"""绝区零抽卡记录获取器"""

from typing import List

from fetchers.mihoyo.base import MihoyoGachaFetcher
from core.models import GachaRecord


class ZZZFetcher(MihoyoGachaFetcher):
    """绝区零抽卡记录获取器

    继承自 MihoyoGachaFetcher，通过设置类属性来适配绝区零游戏:
    - game_key "zzz" 会被传递给 MihoyoAPI.fetch_all() 选择正确的API端点
    - supported_pools 定义了绝区零的3种卡池类型(无新手池)
    - cache_game_key 用于从本地缓存中定位绝区零的调频记录URL

    注意: 绝区零的稀有度编码与其他米哈游游戏不同:
    - API返回的 rank_type: 2=3星, 3=4星, 4=5星 (需要在parse_record中+1修正)
    - 绝区零的抽卡被称为"调频"
    """


    game_key = "zzz"

    game_name = "绝区零"

    supported_pools = ["character", "weapon", "special", "special_weapon", "bangboo", "standard"]

    cache_game_key = "zzz"


    url_missing_tip = (
        "1. 打开绝区零\n"
        "2. 进入调频记录页面\n"
        "3. 等待记录加载完成\n"
        "4. 切回本程序，重新点击获取"
    )

    expired_tip = "authkey已过期。\n\n请重新打开绝区零，进入调频记录页面，然后切回本程序重试。"


    def fetch_records(self, url: str = None, account_id: int = None, latest_time: str = None) -> List[GachaRecord]:
        """获取绝区零抽卡记录

        在父类的 fetch_records() 方法基础上，添加绝区零特有的初始进度提示。
        实际获取逻辑全部由父类 MihoyoGachaFetcher.fetch_records() 完成。

        特殊注意: 父类会调用 MihoyoAPI.fetch_all()，在该方法中:
        - API端点使用 "zzz" 对应的 public-operation-nap.mihoyo.com
        - 解析记录时会自动修正稀有度(rank_type + 1)
        - 会根据item_type修正邦布/音擎的卡池归属

        参数:
            url (str, 可选): 调频记录的API URL。为None时自动从缓存获取。
            account_id (int, 可选): 米哈游账号ID，用于区分不同账号的记录。
            latest_time (str, 可选): 增量获取的截止时间参数。

        返回:
            List[GachaRecord]: 绝区零调频记录列表，每条记录包含:
                - 物品名称、稀有度、类型
                - 所属卡池类型(已修正邦布/音擎归属)
                - 是否为UP角色/音擎/邦布
                - 抽卡时间
                - 原始API数据
        """
        self._report_progress("正在获取绝区零抽卡记录...", 0.05)

        return super().fetch_records(url=url, account_id=account_id, latest_time=latest_time)
