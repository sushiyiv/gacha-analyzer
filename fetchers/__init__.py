# ==============================================================================
# 文件: fetchers/__init__.py
# 说明: 数据获取模块的包初始化文件
#       负责导入所有游戏的获取器类并构建获取器注册表(FETCHER_MAP)
#       上层模块通过 get_fetcher(game) 函数获取指定游戏的获取器实例
#       支持的游戏: genshin(原神), starrail(星铁), zzz(绝区零),
#                  wutheringwaves(鸣潮), arknights(明日方舟), endfield(终末地)
# ==============================================================================

"""数据获取模块 - 获取器注册表"""

# ==================== 获取器类导入 ====================

from fetchers.mihoyo.genshin import GenshinFetcher
# 导入原神获取器类: 继承自 MihoyoGachaFetcher
# 负责通过米哈游API获取原神的祈愿记录

from fetchers.mihoyo.starrail import StarRailFetcher
# 导入崩坏：星穹铁道获取器类: 继承自 MihoyoGachaFetcher
# 负责通过米哈游API获取星铁的跃迁记录

from fetchers.mihoyo.zzz import ZZZFetcher
# 导入绝区零获取器类: 继承自 MihoyoGachaFetcher
# 负责通过米哈游API获取绝区零的调频记录

from fetchers.kuro.wutheringwaves import WutheringWavesFetcher
# 导入鸣潮获取器类: 直接继承自 BaseFetcher (库洛游戏使用独立API)
# 负责通过库洛API获取鸣潮的唤取记录

from fetchers.hypergryph.arknights import ArknightsFetcher
# 导入明日方舟获取器类: 继承自 HypergryphFetcher (鹰角网络的游戏)
# 负责通过鹰角API获取明日方舟的寻访记录

from fetchers.hypergryph.endfield import EndfieldFetcher
# 导入明日方舟：终末地获取器类: 继承自 HypergryphFetcher
# 负责通过鹰角API获取终末地的抽卡记录

# ==================== 获取器注册表 ====================
# 游戏标识字符串 → 获取器类 的映射字典
# 上层模块通过游戏标识查找对应的获取器类并实例化

FETCHER_MAP = {
    "genshin": GenshinFetcher,
    # "genshin" → 原神获取器: 使用米哈游API端点

    "starrail": StarRailFetcher,
    # "starrail" → 崩坏：星穹铁道获取器: 使用米哈游API端点

    "zzz": ZZZFetcher,
    # "zzz" → 绝区零获取器: 使用米哈游API端点

    "wutheringwaves": WutheringWavesFetcher,
    # "wutheringwaves" → 鸣潮获取器: 使用库洛API端点

    "arknights": ArknightsFetcher,
    # "arknights" → 明日方舟获取器: 使用鹰角API端点

    "endfield": EndfieldFetcher,
    # "endfield" → 明日方舟：终末地获取器: 使用鹰角API端点
}

# ==================== 获取器工厂函数 ====================


def get_fetcher(game: str):
    """根据游戏标识获取对应的获取器实例

    本函数是获取器的工厂方法，接收游戏标识字符串，返回对应的获取器实例。
    每次调用都会创建新的实例(非单例模式)。

    使用示例:
        fetcher = get_fetcher("genshin")  # 返回 GenshinFetcher 实例
        fetcher = get_fetcher("starrail")  # 返回 StarRailFetcher 实例

    参数:
        game (str): 游戏标识字符串，必须是 FETCHER_MAP 中已定义的key
                    可选值: "genshin", "starrail", "zzz", "wutheringwaves",
                            "arknights", "endfield"

    返回:
        BaseFetcher子类的实例: 对应游戏的获取器实例，可调用其 fetch_records() 方法

    异常:
        ValueError: 当传入的游戏标识不在 FETCHER_MAP 中时抛出
    """
    cls = FETCHER_MAP.get(game)
    # 从注册表中查找对应游戏的获取器类
    # 如果游戏标识不存在，返回None

    if not cls:
        raise ValueError(f"不支持的游戏: {game}")
        # 抛出ValueError，告知调用者该游戏不受支持

    return cls()  # 创建并返回获取器类的实例(无参构造)
