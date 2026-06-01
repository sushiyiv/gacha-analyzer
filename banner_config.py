"""卡池配置数据"""

# 限定角色池（原神/星铁通用）
CHARACTER_BANNER = {
    "name": "限定角色池",
    "base_rate_5star": 0.006,       # 0.6%
    "base_rate_4star": 0.051,       # 5.1%
    "soft_pity_start": 74,          # 软保底从第74抽开始
    "hard_pity": 90,                # 硬保底90抽
    "soft_pity_increment": 0.06,    # 软保底每抽增加6%
    "featured_guarantee": 0.5,      # 50/50 概率
    "has_guarantee": True,          # 有大小保底机制
    "4star_hard_pity": 10,          # 4星硬保底10抽
}

# 限定武器池（原神）
WEAPON_BANNER_GI = {
    "name": "限定武器池(原神)",
    "base_rate_5star": 0.007,       # 0.7%
    "base_rate_4star": 0.060,       # 6.0%
    "soft_pity_start": 63,          # 软保底从第63抽开始
    "hard_pity": 80,                # 硬保底80抽
    "soft_pity_increment": 0.07,    # 软保底每抽增加7%
    "featured_guarantee": 0.75,     # 75/25
    "has_guarantee": True,
    "has_epitomized_path": True,    # 定轨机制
    "epitomized_path_count": 2,     # 定轨2次必出
    "4star_hard_pity": 10,
}

# 限定光锥池（星铁）
WEAPON_BANNER_SR = {
    "name": "限定光锥池(星铁)",
    "base_rate_5star": 0.008,       # 0.8%
    "base_rate_4star": 0.066,       # 6.6%
    "soft_pity_start": 64,          # 软保底从第64抽开始
    "hard_pity": 80,                # 硬保底80抽
    "soft_pity_increment": 0.07,    # 软保底每抽增加7%
    "featured_guarantee": 0.75,     # 75/25
    "has_guarantee": True,
    "has_epitomized_path": True,
    "epitomized_path_count": 1,     # 星铁定轨1次必出
    "4star_hard_pity": 10,
}

# 常驻池
STANDARD_BANNER = {
    "name": "常驻池",
    "base_rate_5star": 0.006,
    "base_rate_4star": 0.051,
    "soft_pity_start": 74,
    "hard_pity": 90,
    "soft_pity_increment": 0.06,
    "featured_guarantee": 0.0,      # 常驻池无限定概念
    "has_guarantee": False,
    "4star_hard_pity": 10,
}

ALL_BANNERS = {
    "1": ("限定角色池", CHARACTER_BANNER),
    "2": ("限定武器池(原神)", WEAPON_BANNER_GI),
    "3": ("限定光锥池(星铁)", WEAPON_BANNER_SR),
    "4": ("常驻池", STANDARD_BANNER),
}
