# ==============================================================================
# 文件: fetchers/mihoyo/starrail.py
# 说明: 崩坏：星穹铁道(Honkai: Star Rail)抽卡记录获取器
#       继承自 MihoyoGachaFetcher 基类，只需配置星铁特有的参数:
#       - 游戏标识: "starrail"
#       - 游戏名称: "崩坏：星穹铁道"
#       - 支持的卡池: 角色/武器/常驻/新手
#       - 缓存key: "starrail"
#       - 用户操作提示: 如何在游戏中打开跃迁记录页面
# ==============================================================================

"""星穹铁道抽卡记录获取器"""

# ---------- 类型注解导入 ----------
from typing import List  # 用于声明返回值类型为列表

# ---------- 项目内部模块导入 ----------
from fetchers.mihoyo.base import MihoyoGachaFetcher  # 米哈游系列游戏的通用获取器基类
from core.models import GachaRecord  # 统一的抽卡记录数据模型


class StarRailFetcher(MihoyoGachaFetcher):
    """崩坏：星穹铁道抽卡记录获取器

    继承自 MihoyoGachaFetcher，通过设置类属性来适配星铁游戏:
    - game_key "starrail" 会被传递给 MihoyoAPI.fetch_all() 选择正确的API端点
    - supported_pools 定义了星铁的4种卡池类型
    - cache_game_key 用于从本地缓存中定位星铁的跃迁记录URL
    """

    # ==================== 游戏配置属性 ====================

    game_key = "starrail"
    # 星铁在米哈游API系统中的内部标识字符串
    # 该值用于: 1) 选择API端点(public-operation-hkrpg.mihoyo.com)
    #          2) 选择卡池类型编码映射(11/12/1/2)

    game_name = "崩坏：星穹铁道"
    # 星铁的中文显示名称，用于进度提示消息中
    # 例如: "正在获取崩坏：星穹铁道抽卡记录..."

    supported_pools = ["character", "weapon", "standard", "beginner"]
    # 星铁支持的卡池类型列表:
    # - "character": 角色活动跃迁(限定角色UP池，编码11)
    # - "weapon":    光锥活动跃迁(限定光锥UP池，编码12)
    # - "standard":  常驻跃迁(标准池，编码1)
    # - "beginner":  始发跃迁(新手池，编码2)
    # 注意: 联动卡池(collab=13, collab_weapon=14)在GACHA_TYPES中定义但未列入supported_pools

    cache_game_key = "starrail"
    # CacheReader使用的缓存目录标识key
    # CacheReader会根据此key在星铁的缓存目录中查找包含跃迁记录URL的文件

    # ==================== 用户提示信息 ====================

    url_missing_tip = (
        "1. 打开崩坏：星穹铁道\n"                # 步骤1: 启动星铁游戏客户端
        "2. 进入跃迁记录页面\n"                   # 步骤2: 在游戏中打开跃迁记录界面
        "3. 等待记录加载完成\n"                   # 步骤3: 等待页面加载(使URL包含完整参数)
        "4. 切回本程序，重新点击获取"              # 步骤4: 切换回分析器并重试
    )
    # 当程序无法自动从缓存中提取URL时显示给用户的操作指引
    # 星铁中"抽卡"被称为"跃迁"，所以记录页面叫做"跃迁记录"

    expired_tip = "authkey已过期。\n\n请重新打开崩坏：星穹铁道，进入跃迁记录页面，然后切回本程序重试。"
    # 当API返回authkey过期错误时显示的提示
    # 指导用户重新打开星铁并进入跃迁记录页面以获取新的authkey

    # ==================== 核心方法 ====================

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
        # 报告初始进度5%，表示已经开始获取星铁的记录

        return super().fetch_records(url=url, account_id=account_id, latest_time=latest_time)
        # 调用父类 MihoyoGachaFetcher.fetch_records() 执行实际获取流程
        # 参数透传: URL获取 → API调用 → 记录解析 → 返回结果
