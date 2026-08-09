# ==============================================================================
# 文件: fetchers/__init__.py
# 说明: 数据获取模块的包初始化文件
#       负责导入所有游戏的获取器类并构建获取器注册表(FETCHER_MAP)
#       上层模块通过 get_fetcher(game) 函数获取指定游戏的获取器实例
#       支持的游戏: genshin(原神), starrail(星铁), zzz(绝区零),
#                  wutheringwaves(鸣潮)
# ==============================================================================

"""数据获取模块 - 获取器注册表"""

# ==================== 获取器类导入 ====================

from fetchers.mihoyo.genshin import GenshinFetcher
from fetchers.mihoyo.starrail import StarRailFetcher
from fetchers.mihoyo.zzz import ZZZFetcher
from fetchers.kuro.wutheringwaves import WutheringWavesFetcher

# ==================== 获取器注册表 ====================

FETCHER_MAP = {
    "genshin": GenshinFetcher,
    "starrail": StarRailFetcher,
    "zzz": ZZZFetcher,
    "wutheringwaves": WutheringWavesFetcher,
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
                    可选值: "genshin", "starrail", "zzz", "wutheringwaves"

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
