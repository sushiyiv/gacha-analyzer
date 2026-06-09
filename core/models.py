"""数据模型定义 - 所有游戏共用的数据结构"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class Game(Enum):
    """支持的游戏"""
    GENSHIN = "genshin"
    STARRAIL = "starrail"
    ZZZ = "zzz"
    WUTHERINGWAVES = "wutheringwaves"
    ENDFIELD = "endfield"
    ARKNIGHTS = "arknights"


class GachaPoolType(Enum):
    """卡池类型"""
    CHARACTER = "character"     # 角色/限定池
    WEAPON = "weapon"           # 武器/光锥池
    STANDARD = "standard"       # 常驻池
    BEGINNER = "beginner"       # 新手池
    LIMITED = "limited"         # 限定池（明日方舟等）


class Rarity(Enum):
    """星级"""
    STAR_3 = 3
    STAR_4 = 4
    STAR_5 = 5


@dataclass
class Account:
    """账号信息"""
    id: Optional[int] = None
    game: str = ""               # Game enum value
    uid: str = ""
    nickname: str = ""
    server: str = ""             # cn, os_asia, os_usa, os_euro, etc.
    is_active: bool = True
    created_at: str = ""
    updated_at: str = ""


@dataclass
class GachaRecord:
    """抽卡记录"""
    id: Optional[int] = None
    account_id: int = 0
    game: str = ""               # Game enum value
    pool_type: str = ""          # 保底机制类型（用于分组和保底计算）
    pool_name: str = ""          # 卡池原始名称（用于显示和筛选）
    item_id: str = ""            # 物品内部ID
    item_name: str = ""          # 物品名称
    item_type: str = ""          # 物品类型（角色/武器/光锥等）
    rarity: int = 5              # 星级
    is_featured: bool = False    # 是否为UP物品
    count: int = 1               # 抽取数量（单抽1，十连中每个为1）
    time: str = ""               # 抽卡时间
    pity_count: int = 0          # 距离上次出该星级的抽数
    gacha_id: str = ""           # 卡池ID
    pull_index: int = 0          # 在该卡池中的总抽数序号
    raw_data: str = ""           # 原始API返回数据
    created_at: str = ""


@dataclass
class BannerConfig:
    """卡池保底配置"""
    game: str = ""
    pool_type: str = ""
    name: str = ""
    base_rate_5star: float = 0.006
    base_rate_4star: float = 0.051
    soft_pity_start: int = 74
    hard_pity: int = 90
    soft_pity_increment: float = 0.06
    featured_guarantee_rate: float = 0.5  # 50/50
    has_guarantee: bool = True

    # === 扩展字段（明日方舟/终末地专用）===
    up_hard_pity: int = 0               # UP硬保底抽数，0=无此机制
    up_hard_pity_inherits: bool = False  # UP硬保底是否跨池继承
    multi_pity_size: int = 0            # 十连保底间隔，0=无
    multi_pity_rarity: int = 0          # 保底的星级
    exchange_threshold: int = 0         # 自选/兑换所需抽数，0=无
    description: str = ""               # 卡池规则简要说明


# 各游戏保底配置
BANNER_CONFIGS = {
    # ===== 原神 =====
    ("genshin", "beginner"): BannerConfig(
        game="genshin", pool_type="beginner", name="新手祈愿",
        base_rate_5star=0.006, base_rate_4star=0.051,
        soft_pity_start=74, hard_pity=20, soft_pity_increment=0.06,
        featured_guarantee_rate=0.0, has_guarantee=False,
        description="8折优惠，限20抽，首10连必出诺艾尔，不计入常规保底",
    ),
    ("genshin", "character"): BannerConfig(
        game="genshin", pool_type="character", name="限定角色祈愿",
        base_rate_5star=0.006, base_rate_4star=0.051,
        soft_pity_start=74, hard_pity=90, soft_pity_increment=0.06,
        featured_guarantee_rate=0.5, has_guarantee=True,
        description="50/50小保底，歪了下次必出UP，保底继承",
    ),
    ("genshin", "weapon"): BannerConfig(
        game="genshin", pool_type="weapon", name="限定武器祈愿",
        base_rate_5star=0.007, base_rate_4star=0.060,
        soft_pity_start=63, hard_pity=80, soft_pity_increment=0.07,
        featured_guarantee_rate=0.75, has_guarantee=True,
        description="定轨机制，最多歪两次后必出定轨武器，保底继承但定轨值清零",
    ),
    ("genshin", "chronicled"): BannerConfig(
        game="genshin", pool_type="chronicled", name="集录祈愿",
        base_rate_5star=0.006, base_rate_4star=0.051,
        soft_pity_start=74, hard_pity=90, soft_pity_increment=0.06,
        featured_guarantee_rate=0.5, has_guarantee=True,
        description="混合池，可定轨角色或武器，歪一次后必中，保底继承但定轨不继承",
    ),
    ("genshin", "standard"): BannerConfig(
        game="genshin", pool_type="standard", name="常驻祈愿",
        base_rate_5star=0.006, base_rate_4star=0.051,
        soft_pity_start=74, hard_pity=90, soft_pity_increment=0.06,
        featured_guarantee_rate=0.0, has_guarantee=False,
    ),
    # ===== 星穹铁道 =====
    ("starrail", "beginner"): BannerConfig(
        game="starrail", pool_type="beginner", name="新手跃迁",
        base_rate_5star=0.006, base_rate_4star=0.051,
        soft_pity_start=74, hard_pity=50, soft_pity_increment=0.06,
        featured_guarantee_rate=0.0, has_guarantee=False,
        description="新手池，限50抽，十连8折，首五星必出角色，不计入常规保底",
    ),
    ("starrail", "character"): BannerConfig(
        game="starrail", pool_type="character", name="限定角色跃迁",
        base_rate_5star=0.006, base_rate_4star=0.051,
        soft_pity_start=74, hard_pity=90, soft_pity_increment=0.06,
        featured_guarantee_rate=0.5, has_guarantee=True,
        description="50/50小保底，歪了下次必出UP，保底继承",
    ),
    ("starrail", "weapon"): BannerConfig(
        game="starrail", pool_type="weapon", name="限定光锥跃迁",
        base_rate_5star=0.008, base_rate_4star=0.066,
        soft_pity_start=64, hard_pity=80, soft_pity_increment=0.07,
        featured_guarantee_rate=0.75, has_guarantee=True,
        description="75%UP概率，无定轨，歪了下次必中，保底继承",
    ),
    ("starrail", "standard"): BannerConfig(
        game="starrail", pool_type="standard", name="常驻跃迁",
        base_rate_5star=0.006, base_rate_4star=0.051,
        soft_pity_start=74, hard_pity=90, soft_pity_increment=0.06,
        featured_guarantee_rate=0.0, has_guarantee=False,
        exchange_threshold=300,
        description="角色光锥混合，无大保底，累计300抽可自选一位常驻五星",
    ),
    ("starrail", "collab"): BannerConfig(
        game="starrail", pool_type="collab", name="联动角色跃迁",
        base_rate_5star=0.006, base_rate_4star=0.051,
        soft_pity_start=74, hard_pity=90, soft_pity_increment=0.06,
        featured_guarantee_rate=0.5, has_guarantee=True,
        description="联动角色池，保底仅联动池之间互通，不与其他池共享",
    ),
    ("starrail", "collab_weapon"): BannerConfig(
        game="starrail", pool_type="collab_weapon", name="联动光锥跃迁",
        base_rate_5star=0.008, base_rate_4star=0.066,
        soft_pity_start=64, hard_pity=80, soft_pity_increment=0.07,
        featured_guarantee_rate=0.75, has_guarantee=True,
        description="联动光锥池，保底仅联动池之间互通，不与其他池共享",
    ),
    # ===== 绝区零 =====
    ("zzz", "character"): BannerConfig(
        game="zzz", pool_type="character", name="独家频段",
        base_rate_5star=0.006, base_rate_4star=0.051,
        soft_pity_start=74, hard_pity=90, soft_pity_increment=0.06,
        featured_guarantee_rate=0.5, has_guarantee=True,
        description="限定角色池，50/50小保底，歪了下次必出UP，保底继承",
    ),
    ("zzz", "weapon"): BannerConfig(
        game="zzz", pool_type="weapon", name="音擎频段",
        base_rate_5star=0.007, base_rate_4star=0.060,
        soft_pity_start=63, hard_pity=80, soft_pity_increment=0.07,
        featured_guarantee_rate=0.75, has_guarantee=True,
        description="限定武器池，75%UP概率，保底继承",
    ),
    ("zzz", "bangboo"): BannerConfig(
        game="zzz", pool_type="bangboo", name="邦布频段",
        base_rate_5star=0.006, base_rate_4star=0.051,
        soft_pity_start=64, hard_pity=80, soft_pity_increment=0.07,
        featured_guarantee_rate=1.0, has_guarantee=True,
        description="邦布池，可自选S级邦布定向抽取，保底和定轨可继承",
    ),
    ("zzz", "standard"): BannerConfig(
        game="zzz", pool_type="standard", name="常驻频段",
        base_rate_5star=0.006, base_rate_4star=0.051,
        soft_pity_start=74, hard_pity=90, soft_pity_increment=0.06,
        featured_guarantee_rate=0.0, has_guarantee=False,
        exchange_threshold=300,
        description="前50抽8折，首S级必出角色，累计300抽可自选常驻S级",
    ),
    ("zzz", "special"): BannerConfig(
        game="zzz", pool_type="special", name="独家重映",
        base_rate_5star=0.006, base_rate_4star=0.051,
        soft_pity_start=74, hard_pity=90, soft_pity_increment=0.06,
        featured_guarantee_rate=0.5, has_guarantee=True,
        description="限时特殊角色池，每期首个五星必UP（仅一次），之后50/50，硬保底继承",
    ),
    ("zzz", "special_weapon"): BannerConfig(
        game="zzz", pool_type="special_weapon", name="音擎回响",
        base_rate_5star=0.007, base_rate_4star=0.060,
        soft_pity_start=63, hard_pity=80, soft_pity_increment=0.07,
        featured_guarantee_rate=0.75, has_guarantee=True,
        description="限时特殊武器池，每期首个五星必UP（仅一次），之后75%，硬保底继承",
    ),
    # ===== 鸣潮 =====
    ("wutheringwaves", "beginner"): BannerConfig(
        game="wutheringwaves", pool_type="beginner", name="新手唤取",
        base_rate_5star=0.008, base_rate_4star=0.060,
        soft_pity_start=65, hard_pity=50, soft_pity_increment=0.08,
        featured_guarantee_rate=0.0, has_guarantee=False,
        description="新手池，8折优惠，50抽内必出五星，出后消失",
    ),
    ("wutheringwaves", "character"): BannerConfig(
        game="wutheringwaves", pool_type="character", name="限定角色唤取",
        base_rate_5star=0.008, base_rate_4star=0.060,
        soft_pity_start=65, hard_pity=80, soft_pity_increment=0.08,
        featured_guarantee_rate=0.5, has_guarantee=True,
        description="50/50小保底，歪了下次必出UP，保底继承",
    ),
    ("wutheringwaves", "weapon"): BannerConfig(
        game="wutheringwaves", pool_type="weapon", name="限定武器唤取",
        base_rate_5star=0.008, base_rate_4star=0.060,
        soft_pity_start=65, hard_pity=80, soft_pity_increment=0.08,
        featured_guarantee_rate=1.0, has_guarantee=True,
        description="100%UP武器，不会歪，保底继承",
    ),
    ("wutheringwaves", "collab"): BannerConfig(
        game="wutheringwaves", pool_type="collab", name="联动角色唤取",
        base_rate_5star=0.008, base_rate_4star=0.060,
        soft_pity_start=65, hard_pity=80, soft_pity_increment=0.08,
        featured_guarantee_rate=0.5, has_guarantee=True,
        description="联动角色池，规则同限定角色唤取，保底仅联动池互通",
    ),
    ("wutheringwaves", "collab_weapon"): BannerConfig(
        game="wutheringwaves", pool_type="collab_weapon", name="联动武器唤取",
        base_rate_5star=0.008, base_rate_4star=0.060,
        soft_pity_start=65, hard_pity=80, soft_pity_increment=0.08,
        featured_guarantee_rate=1.0, has_guarantee=True,
        description="联动武器池，规则同限定武器唤取，保底仅联动池互通",
    ),
    ("wutheringwaves", "selector"): BannerConfig(
        game="wutheringwaves", pool_type="selector", name="新旅角色唤取",
        base_rate_5star=0.008, base_rate_4star=0.060,
        soft_pity_start=65, hard_pity=80, soft_pity_increment=0.08,
        featured_guarantee_rate=0.5, has_guarantee=True,
        description="定向角色池，50/50会歪，歪了下次必出，出后消失，保底不继承",
    ),
    ("wutheringwaves", "selector_weapon"): BannerConfig(
        game="wutheringwaves", pool_type="selector_weapon", name="新旅武器唤取",
        base_rate_5star=0.008, base_rate_4star=0.060,
        soft_pity_start=65, hard_pity=80, soft_pity_increment=0.08,
        featured_guarantee_rate=0.5, has_guarantee=True,
        description="定向武器池，50/50会歪，歪了下次必出，出后消失，保底不继承",
    ),
    ("wutheringwaves", "standard_character"): BannerConfig(
        game="wutheringwaves", pool_type="standard_character", name="常驻角色唤取",
        base_rate_5star=0.008, base_rate_4star=0.060,
        soft_pity_start=65, hard_pity=80, soft_pity_increment=0.08,
        featured_guarantee_rate=0.0, has_guarantee=False,
        description="常驻角色唤取，无UP",
    ),
    ("wutheringwaves", "standard_weapon"): BannerConfig(
        game="wutheringwaves", pool_type="standard_weapon", name="常驻武器唤取",
        base_rate_5star=0.008, base_rate_4star=0.060,
        soft_pity_start=65, hard_pity=80, soft_pity_increment=0.08,
        featured_guarantee_rate=1.0, has_guarantee=True,
        description="可定向选择五星武器，抽到必为所选武器，不会歪",
    ),
    # ===== 终末地 =====
    ("endfield", "beginner"): BannerConfig(
        game="endfield", pool_type="beginner", name="启程寻访",
        base_rate_5star=0.008, base_rate_4star=0.080,
        soft_pity_start=66, hard_pity=40, soft_pity_increment=0.05,
        featured_guarantee_rate=0.0, has_guarantee=False,
        multi_pity_size=10, multi_pity_rarity=5,
        description="新手池，40抽内必出6星，限次数",
    ),
    ("endfield", "character"): BannerConfig(
        game="endfield", pool_type="character", name="基础寻访",
        base_rate_5star=0.008, base_rate_4star=0.080,
        soft_pity_start=66, hard_pity=80, soft_pity_increment=0.05,
        featured_guarantee_rate=0.0, has_guarantee=False,
        multi_pity_size=10, multi_pity_rarity=5,
        exchange_threshold=300,
        description="常驻池，80抽小保底，300抽可自选常驻6星",
    ),
    ("endfield", "limited"): BannerConfig(
        game="endfield", pool_type="limited", name="特许寻访",
        base_rate_5star=0.008, base_rate_4star=0.080,
        soft_pity_start=66, hard_pity=80, soft_pity_increment=0.05,
        featured_guarantee_rate=0.5, has_guarantee=True,
        multi_pity_size=10, multi_pity_rarity=5,
        up_hard_pity=120, up_hard_pity_inherits=False,
        description="限定池，50/50小保底跨卡池继承，120抽大保底不继承",
    ),
    ("endfield", "joint"): BannerConfig(
        game="endfield", pool_type="joint", name="辉光庆典",
        base_rate_5star=0.008, base_rate_4star=0.080,
        soft_pity_start=66, hard_pity=80, soft_pity_increment=0.05,
        featured_guarantee_rate=0.5, has_guarantee=True,
        multi_pity_size=10, multi_pity_rarity=5,
        description="联合寻访，多UP池，保底独立计算",
    ),
    ("endfield", "weapon"): BannerConfig(
        game="endfield", pool_type="weapon", name="武库申领",
        base_rate_5star=0.040, base_rate_4star=0.080,
        soft_pity_start=30, hard_pity=40, soft_pity_increment=0.05,
        featured_guarantee_rate=0.25, has_guarantee=True,
        up_hard_pity=80, up_hard_pity_inherits=False,
        multi_pity_size=10, multi_pity_rarity=5,
        description="武器池，40抽小保底(25%UP)换卡池名清空，80抽大保底不继承",
    ),
    # ===== 明日方舟（按保底机制分 4 组）=====
    ("arknights", "standard"): BannerConfig(
        game="arknights", pool_type="standard", name="标准寻访",
        base_rate_5star=0.020, base_rate_4star=0.100,
        soft_pity_start=50, hard_pity=100, soft_pity_increment=0.02,
        featured_guarantee_rate=0.5, has_guarantee=True,
        description="常驻标准/单UP/联合行动/前路回响/定向甄选，水位互通",
    ),
    ("arknights", "kernel"): BannerConfig(
        game="arknights", pool_type="kernel", name="中坚寻访",
        base_rate_5star=0.020, base_rate_4star=0.100,
        soft_pity_start=50, hard_pity=100, soft_pity_increment=0.02,
        featured_guarantee_rate=0.5, has_guarantee=True,
        description="中坚寻访/中坚甄选，水位仅中坚之间互通",
    ),
    ("arknights", "limited"): BannerConfig(
        game="arknights", pool_type="limited", name="独立寻访",
        base_rate_5star=0.020, base_rate_4star=0.100,
        soft_pity_start=50, hard_pity=100, soft_pity_increment=0.02,
        featured_guarantee_rate=0.7, has_guarantee=True,
        up_hard_pity=120, up_hard_pity_inherits=False,
        exchange_threshold=300,
        description="新手/限定/联动/跨年/归航，水位独立不继承，池结束清空",
    ),
}

# 各游戏最高星级
MAX_RARITY = {
    "genshin": 5,
    "starrail": 5,
    "zzz": 5,
    "wutheringwaves": 5,
    "endfield": 6,
    "arknights": 6,
}


def get_max_rarity(game: str) -> int:
    """获取游戏的最高星级"""
    return MAX_RARITY.get(game, 5)


# 终末地常驻6星（不在列表中的6星 = UP/限定物品）
ENDFIELD_STANDARD_6STAR = {
    # 常驻角色
    "艾尔黛拉", "骏卫", "余烬", "黎风", "别礼",
    # 常驻武器 - 单手剑
    "黯色火炬", "不知归", "热熔切割器", "宏愿", "扶摇",
    "白夜新星", "显赫声名", "五号遗产", "忘机", "湍流", "幽蓝回唱",
    # 常驻武器 - 双手剑
    "赫拉芬格", "破碎君王", "大雷斑", "昔日精品", "典范", "阿布拉克萨斯",
    # 常驻武器 - 长枪
    "负山", "骁勇", "J.E.T", "塔罗斯旋涡",
    # 常驻武器 - 手铳
    "楔子", "领航者", "同类相食", "望乡",
    # 常驻武器 - 施术单元
    "作品：蚀象", "沧溟星梦", "骑士精神", "爆破单元", "遗忘", "镀红祝福",
}


def get_pity_rarity(game: str, pool_type: str = None) -> int:
    """获取十连保底所依据的星级（用于 multi_pity 显示，非主保底计数）"""
    if pool_type is not None:
        config = BANNER_CONFIGS.get((game, pool_type))
        if config and config.multi_pity_rarity > 0:
            return config.multi_pity_rarity
    else:
        for (g, pt), config in BANNER_CONFIGS.items():
            if g == game and config.multi_pity_rarity > 0:
                return config.multi_pity_rarity
    return get_max_rarity(game)


# 各游戏卡池配置: [(pool_type, 显示名称)]
POOL_CONFIGS = {
    "genshin": [
        ("character", "限定角色祈愿"),
        ("weapon", "限定武器祈愿"),
        ("chronicled", "集录祈愿"),
        ("standard", "常驻祈愿"),
        ("beginner", "新手祈愿"),
    ],
    "starrail": [
        ("character", "限定角色跃迁"),
        ("weapon", "限定光锥跃迁"),
        ("collab", "联动角色跃迁"),
        ("collab_weapon", "联动光锥跃迁"),
        ("standard", "常驻跃迁"),
        ("beginner", "新手跃迁"),
    ],
    "zzz": [
        ("character", "独家频段"),
        ("weapon", "音擎频段"),
        ("special", "独家重映"),
        ("special_weapon", "音擎回响"),
        ("bangboo", "邦布频段"),
        ("standard", "常驻频段"),
    ],
    "wutheringwaves": [
        ("character", "限定角色唤取"),
        ("weapon", "限定武器唤取"),
        ("collab", "联动角色唤取"),
        ("collab_weapon", "联动武器唤取"),
        ("selector", "新旅角色唤取"),
        ("selector_weapon", "新旅武器唤取"),
        ("standard_character", "常驻角色唤取"),
        ("standard_weapon", "常驻武器唤取"),
        ("beginner", "新手唤取"),
    ],
    "endfield": [
        ("limited", "特许寻访"),
        ("joint", "辉光庆典"),
        ("character", "基础寻访"),
        ("weapon", "武库申领"),
        ("beginner", "启程寻访"),
    ],
    "arknights": [
        ("standard", "标准寻访"),
        ("kernel", "中坚寻访"),
        ("limited", "独立寻访"),
    ],
}


def get_pool_names(game: str) -> list:
    """获取游戏的卡池列表 [(pool_type, 显示名称)]"""
    return POOL_CONFIGS.get(game, POOL_CONFIGS.get("genshin", []))


# 终末地：保底分组
# limited/joint/character/beginner 跨卡池轮换继承保底（不按 pool_name 分组）
# 武器池换名字清空保底（按 pool_name 分组）
ENDFIELD_PITY_GROUP = {
    "limited": "limited",
    "joint": "joint",         # 辉光庆典与限定池分开计算
    "character": "character",
    "weapon": "weapon",
    "beginner": "beginner",
}


def get_endfield_pity_group(pool_type: str) -> str:
    """获取终末地卡池的保底分组"""
    return ENDFIELD_PITY_GROUP.get(pool_type, pool_type)


# 终末地：换卡池名字时保底会重置的池类型（武器池）
ENDFIELD_PITY_RESETS_ON_NAME_CHANGE = {"weapon"}


# 明日方舟：具体卡池名 → 机制类型
# 根据保底是否互通来分组
ARKNIGHTS_POOL_MECHANIC_MAP = {
    # 标准寻访（水位互通）
    "常驻标准寻访": "standard",
    "标准寻访": "standard",
    "单角色UP": "standard",
    "单UP": "standard",
    "联合行动": "standard",
    "前路回响": "standard",
    "定向甄选": "standard",
    # 中坚寻访（水位独立，仅中坚之间互通）
    "中坚寻访": "kernel",
    "常驻中坚寻访": "kernel",
    "中坚甄选": "kernel",
    # 独立池（水位不继承或用完即止）
    "限定寻访": "limited",
    "限时寻访": "limited",
    "联动限定寻访": "limited",
    "联动寻访": "limited",
    "跨年欢庆寻访": "limited",
    "跨年欢庆·寻访": "limited",
    "跨年欢庆·展望": "limited",
    "归航寻访": "limited",
    # 限定卡池（具体名称）
    "承诺": "limited",            # 限定卡池（凯尔希·思衡托、可露希尔）
    # 联动卡池（具体名称）
    "幽境狩人": "limited",        # 怪物猎人联动（焰狐龙梓兰）
    # 新手池
    "启程寻访": "beginner",
}

# 明日方舟：机制类型 → 保底分组（用于 BANNER_CONFIGS 的 key）
ARKNIGHTS_MECHANIC_TO_GROUP = {
    "standard": "standard",
    "kernel": "kernel",
    "limited": "limited",
    "beginner": "limited",  # 新手池也是独立寻访
}


def get_arknights_mechanic_group(pool_name: str) -> str:
    """根据明日方舟卡池名返回保底分组（standard/limited/beginner）"""
    mechanic = ARKNIGHTS_POOL_MECHANIC_MAP.get(pool_name, "")
    return ARKNIGHTS_MECHANIC_TO_GROUP.get(mechanic, "standard")


def get_mechanic_type(game: str, pool_type: str, pool_name: str = "") -> str:
    """获取卡池的保底机制类型（用于 BANNER_CONFIGS 查询）"""
    if game == "arknights":
        return get_arknights_mechanic_group(pool_name)
    # 其他游戏直接用 pool_type
    return pool_type


# 游戏显示名称
GAME_NAMES = {
    "genshin": "原神",
    "starrail": "崩坏：星穹铁道",
    "zzz": "绝区零",
    "wutheringwaves": "鸣潮",
    "endfield": "终末地",
    "arknights": "明日方舟",
}

# 游戏主题色
GAME_COLORS = {
    "genshin": {"primary": "#8B6914", "accent": "#D4A843", "bg": "#FFF8E1"},
    "starrail": {"primary": "#4A2E8C", "accent": "#9B7ED8", "bg": "#F3E5F5"},
    "zzz": {"primary": "#F5C842", "accent": "#1A1A1A", "bg": "#FFFDE7"},
    "wutheringwaves": {"primary": "#1E3A5F", "accent": "#00D4AA", "bg": "#E0F7FA"},
    "endfield": {"primary": "#3D5A1E", "accent": "#E87E04", "bg": "#F1F8E9"},
    "arknights": {"primary": "#2B2B2B", "accent": "#FF6B35", "bg": "#FBE9E7"},
}
