# ==============================================================================
# 文件: fetchers/mihoyo/zzz.py
# 说明: 绝区零(Zenless Zone Zero)抽卡记录获取器
#       继承自 MihoyoGachaFetcher 基类，只需配置ZZZ特有的参数:
#       - 游戏标识: "zzz"
#       - 游戏名称: "绝区零"
#       - 支持的卡池: 角色/武器/常驻(不含新手池)
#       - 缓存key: "zzz"
#       - 用户操作提示: 如何在游戏中打开调频记录页面
# ==============================================================================

"""绝区零抽卡记录获取器"""

# ---------- 类型注解导入 ----------
from typing import List  # 用于声明返回值类型为列表

# ---------- 项目内部模块导入 ----------
from fetchers.mihoyo.base import MihoyoGachaFetcher  # 米哈游系列游戏的通用获取器基类
from core.models import GachaRecord  # 统一的抽卡记录数据模型


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

    # ==================== 游戏配置属性 ====================

    game_key = "zzz"
    # 绝区零在米哈游API系统中的内部标识字符串
    # 该值用于: 1) 选择API端点(public-operation-nap.mihoyo.com)
    #          2) 选择卡池类型编码映射(2001/3001/4001/5001/6001/1001)

    game_name = "绝区零"
    # 绝区零的中文显示名称，用于进度提示消息中
    # 例如: "正在获取绝区零抽卡记录..."

    supported_pools = ["character", "weapon", "standard"]
    # 绝区零支持的卡池类型列表:
    # - "character": 频调(限定角色UP池，编码2001)
    # - "weapon":    音擎调频(限定音擎UP池，编码3001)
    # - "standard":  常驻调频(标准池，编码1001)
    # 注意: 绝区零没有新手池，所以 supported_pools 不包含 "beginner"
    # 另有特殊池(special=4001, special_weapon=5001, bangboo=6001)在GACHA_TYPES中定义但未列入

    cache_game_key = "zzz"
    # CacheReader使用的缓存目录标识key
    # CacheReader会根据此key在绝区零的缓存目录中查找包含调频记录URL的文件

    # ==================== 用户提示信息 ====================

    url_missing_tip = (
        "1. 打开绝区零\n"                        # 步骤1: 启动绝区零游戏客户端
        "2. 进入调频记录页面\n"                   # 步骤2: 在游戏中打开调频记录界面
        "3. 等待记录加载完成\n"                   # 步骤3: 等待页面加载(使URL包含完整参数)
        "4. 切回本程序，重新点击获取"              # 步骤4: 切换回分析器并重试
    )
    # 当程序无法自动从缓存中提取URL时显示给用户的操作指引
    # 绝区零中"抽卡"被称为"调频"，所以记录页面叫做"调频记录"

    expired_tip = "authkey已过期。\n\n请重新打开绝区零，进入调频记录页面，然后切回本程序重试。"
    # 当API返回authkey过期错误时显示的提示
    # 指导用户重新打开绝区零并进入调频记录页面以获取新的authkey

    # ==================== 核心方法 ====================

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
        # 报告初始进度5%，表示已经开始获取绝区零的记录

        return super().fetch_records(url=url, account_id=account_id, latest_time=latest_time)
        # 调用父类 MihoyoGachaFetcher.fetch_records() 执行实际获取流程
        # 参数透传: URL获取 → API调用 → 记录解析(含ZZZ特殊修正) → 返回结果
