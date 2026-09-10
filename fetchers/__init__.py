
"""数据获取模块 - 获取器注册表"""


from fetchers.mihoyo.genshin import GenshinFetcher
from fetchers.mihoyo.starrail import StarRailFetcher
from fetchers.mihoyo.zzz import ZZZFetcher
from fetchers.kuro.wutheringwaves import WutheringWavesFetcher


FETCHER_MAP = {
    "genshin": GenshinFetcher,
    "starrail": StarRailFetcher,
    "zzz": ZZZFetcher,
    "wutheringwaves": WutheringWavesFetcher,
}



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

    if not cls:
        raise ValueError(f"不支持的游戏: {game}")

    return cls()
