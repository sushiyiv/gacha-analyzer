"""数据获取模块 - 获取器注册表"""

from fetchers.mihoyo.genshin import GenshinFetcher
from fetchers.mihoyo.starrail import StarRailFetcher
from fetchers.mihoyo.zzz import ZZZFetcher
from fetchers.kuro.wutheringwaves import WutheringWavesFetcher
from fetchers.hypergryph.arknights import ArknightsFetcher
from fetchers.hypergryph.endfield import EndfieldFetcher


FETCHER_MAP = {
    "genshin": GenshinFetcher,
    "starrail": StarRailFetcher,
    "zzz": ZZZFetcher,
    "wutheringwaves": WutheringWavesFetcher,
    "arknights": ArknightsFetcher,
    "endfield": EndfieldFetcher,
}


def get_fetcher(game: str):
    """获取指定游戏的获取器实例"""
    cls = FETCHER_MAP.get(game)
    if not cls:
        raise ValueError(f"不支持的游戏: {game}")
    return cls()
