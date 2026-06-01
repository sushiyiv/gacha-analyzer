"""抽卡核心引擎 - 精确模拟原神/星铁保底机制"""

import random
from banner_config import CHARACTER_BANNER, WEAPON_BANNER_GI, WEAPON_BANNER_SR, STANDARD_BANNER


class PityState:
    """保底状态追踪"""

    def __init__(self, banner_config, current_pity=0, is_guaranteed=False, epitomized_count=0):
        self.config = banner_config
        self.current_pity = current_pity        # 距离上次出5星已垫的抽数
        self.is_guaranteed = is_guaranteed       # 是否处于大保底（上次歪了）
        self.epitomized_count = epitomized_count  # 定轨计数（武器池）
        self.pull_history = []

    def get_5star_rate(self):
        """计算当前抽数下的5星概率"""
        base = self.config["base_rate_5star"]
        soft_start = self.config["soft_pity_start"]
        hard = self.config["hard_pity"]
        increment = self.config["soft_pity_increment"]

        if self.current_pity >= hard:
            return 1.0
        if self.current_pity >= soft_start:
            extra = (self.current_pity - soft_start + 1) * increment
            return min(base + extra, 1.0)
        return base

    def pull_once(self):
        """执行一次抽卡，返回 (是否出5星, 是否限定5星, 是否出4星)"""
        self.current_pity += 1
        rate = self.get_5star_rate()

        if random.random() < rate:
            # 出5星了
            self.current_pity = 0
            is_featured = self._resolve_featured()
            self.pull_history.append(5)
            return True, is_featured, False

        # 检查4星保底
        if self._check_4star():
            self.pull_history.append(4)
            return False, False, True

        self.pull_history.append(3)
        return False, False, False

    def _resolve_featured(self):
        """决定出的5星是否为限定角色/武器"""
        config = self.config

        if not config["has_guarantee"]:
            # 常驻池，随机出
            return False

        # 有定轨机制的武器池
        if config.get("has_epitomized_path"):
            if self.is_guaranteed:
                self.is_guaranteed = False
                self.epitomized_count = 0
                return True
            if random.random() < config["featured_guarantee"]:
                self.epitomized_count = 0
                return True
            else:
                self.epitomized_count += 1
                if self.epitomized_count >= config["epitomized_path_count"]:
                    self.epitomized_count = 0
                    self.is_guaranteed = False
                    return True
                self.is_guaranteed = True
                return False

        # 角色池 50/50 + 大保底
        if self.is_guaranteed:
            self.is_guaranteed = False
            return True

        if random.random() < config["featured_guarantee"]:
            return True
        else:
            self.is_guaranteed = True
            return False

    def _check_4star(self):
        """检查4星保底（简化处理）"""
        pity_4star = sum(1 for p in self.pull_history[-9:] if p >= 4)
        if pity_4star == 0 and len(self.pull_history) >= 10:
            return True
        return random.random() < self.config["base_rate_4star"]


def simulate_pulls(banner_config, num_pulls, current_pity=0, is_guaranteed=False):
    """模拟N次抽卡，返回详细结果"""
    state = PityState(banner_config, current_pity, is_guaranteed)
    results = {
        "total_pulls": num_pulls,
        "five_stars": [],
        "four_stars": 0,
        "featured_count": 0,
        "off_featured_count": 0,
        "pulls_per_5star": [],
    }

    last_5star_pull = 0
    for i in range(num_pulls):
        is_5star, is_featured, is_4star = state.pull_once()
        if is_5star:
            pull_num = i + 1
            results["five_stars"].append({
                "pull": pull_num,
                "is_featured": is_featured,
                "pity_count": pull_num - last_5star_pull,
            })
            results["pulls_per_5star"].append(pull_num - last_5star_pull)
            if is_featured:
                results["featured_count"] += 1
            else:
                results["off_featured_count"] += 1
            last_5star_pull = pull_num
        elif is_4star:
            results["four_stars"] += 1

    return results, state


def pulls_until_featured(banner_config, current_pity=0, is_guaranteed=False, max_pulls=1000):
    """模拟抽到限定5星需要多少抽"""
    state = PityState(banner_config, current_pity, is_guaranteed)
    for i in range(1, max_pulls + 1):
        is_5star, is_featured, _ = state.pull_once()
        if is_5star and is_featured:
            return i
    return max_pulls
