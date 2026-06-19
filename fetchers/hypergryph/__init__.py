"""鹰角网络（Hypergryph）游戏抽卡记录获取器模块

此模块包含鹰角网络旗下游戏的抽卡记录获取器：
- ArknightsFetcher: 明日方舟抽卡记录获取器
- EndfieldFetcher: 终末地抽卡记录获取器
- arknights_proxy: 明日方舟本地代理服务器（用于捕获u8_token）
"""

# 明确导出模块中的公开类，便于外部导入
# 当其他模块使用 from fetchers.hypergryph import ArknightsFetcher 时
# Python 会从 __init__.py 中查找该类的定义
# 由于 ArknightsFetcher 定义在 arknights.py 子模块中
# 这里需要显式导入才能在包级别使用

from fetchers.hypergryph.arknights import ArknightsFetcher
from fetchers.hypergryph.endfield import EndfieldFetcher

# 定义此包的公开接口列表
# 当使用 from fetchers.hypergryph import * 时
# 只会导出 __all__ 中列出的名称
# 这样可以避免意外导出内部模块或变量
__all__ = [
    "ArknightsFetcher",
    "EndfieldFetcher",
]

# 版本信息，用于调试和兼容性检查
__version__ = "1.0.0"