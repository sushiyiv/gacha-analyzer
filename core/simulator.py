"""蒙特卡洛抽卡模拟模块

基于 core.models.BannerConfig 的精确保底机制模拟，替代遗留的 gacha_engine.py + simulator.py。
"""

import random
from typing import List, Dict, Optional
from core.models import BannerConfig, BANNER_CONFIGS


class PityState:
    """保底状态追踪（基于 BannerConfig dataclass）"""

    def __init__(self, config: BannerConfig, current_pity: int = 0,
                 is_guaranteed: bool = False, epitomized_count: int = 0):
        self.config = config
        self.current_pity = current_pity
        self.is_guaranteed = is_guaranteed
        self.epitomized_count = epitomized_count
        self.pull_history: List[int] = []

    def get_5star_rate(self) -> float:
        """计算当前抽数下的5星概率"""
        if self.current_pity >= self.config.hard_pity:
            return 1.0
        if self.current_pity >= self.config.soft_pity_start:
            extra = (self.current_pity - self.config.soft_pity_start + 1) * self.config.soft_pity_increment
            return min(self.config.base_rate_5star + extra, 1.0)
        return self.config.base_rate_5star

    def pull_once(self):
        """执行一次抽卡，返回 (是否出5星, 是否限定5星, 是否出4星)"""
        self.current_pity += 1
        rate = self.get_5star_rate()

        if random.random() < rate:
            self.current_pity = 0
            is_featured = self._resolve_featured()
            self.pull_history.append(5)
            return True, is_featured, False

        if self._check_4star():
            self.pull_history.append(4)
            return False, False, True

        self.pull_history.append(3)
        return False, False, False

    def _resolve_featured(self) -> bool:
        """决定出的5星是否为限定"""
        config = self.config

        if not config.has_guarantee:
            return False

        # 有大小保底机制
        if self.is_guaranteed:
            self.is_guaranteed = False
            return True

        if random.random() < config.featured_guarantee_rate:
            return True
        else:
            self.is_guaranteed = True
            return False

    def _check_4star(self) -> bool:
        """检查4星保底（简化处理）"""
        pity_4star = sum(1 for p in self.pull_history[-9:] if p >= 4)
        if pity_4star == 0 and len(self.pull_history) >= 10:
            return True
        return random.random() < self.config.base_rate_4star


def simulate_pulls(config: BannerConfig, num_pulls: int,
                   current_pity: int = 0, is_guaranteed: bool = False):
    """模拟N次抽卡，返回详细结果"""
    state = PityState(config, current_pity, is_guaranteed)
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


def pulls_until_featured(config: BannerConfig, current_pity: int = 0,
                         is_guaranteed: bool = False, max_pulls: int = 1000) -> int:
    """模拟抽到限定5星需要多少抽"""
    state = PityState(config, current_pity, is_guaranteed)
    for i in range(1, max_pulls + 1):
        is_5star, is_featured, _ = state.pull_once()
        if is_5star and is_featured:
            return i
    return max_pulls


def monte_carlo_simulate(config: BannerConfig, current_pity: int = 0,
                         is_guaranteed: bool = False, target_featured: int = 1,
                         simulations: int = 10000) -> List[int]:
    """Monte Carlo 模拟抽到目标数量限定5星需要的抽数"""
    results = []
    for _ in range(simulations):
        total_pulls = 0
        featured_count = 0
        state_pity = current_pity
        state_guaranteed = is_guaranteed

        while featured_count < target_featured:
            pulls = pulls_until_featured(config, state_pity, state_guaranteed)
            total_pulls += pulls
            featured_count += 1
            state_pity = 0
            state_guaranteed = False

        results.append(total_pulls)
    return results


def analyze_simulation_results(results: List[int], target_featured: int = 1) -> Dict:
    """分析模拟结果"""
    results_sorted = sorted(results)
    n = len(results_sorted)

    avg = sum(results) / n
    median = results_sorted[n // 2]
    min_val = results_sorted[0]
    max_val = results_sorted[-1]

    # 各抽数阈值的概率
    thresholds = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 120, 150, 180, 200]
    prob_table = {}
    for t in thresholds:
        count = sum(1 for r in results if r <= t)
        prob_table[t] = count / n

    # 欧皇/非酋分布
    percentiles = {
        "欧皇 (前10%)": results_sorted[int(n * 0.1)],
        "偏欧 (前25%)": results_sorted[int(n * 0.25)],
        "正常 (50%)": median,
        "偏非 (前75%)": results_sorted[int(n * 0.75)],
        "非酋 (前90%)": results_sorted[int(n * 0.9)],
        "究极非酋 (前99%)": results_sorted[int(n * 0.99)],
    }

    return {
        "simulations": n,
        "target_featured": target_featured,
        "average": round(avg, 2),
        "median": median,
        "min": min_val,
        "max": max_val,
        "prob_table": prob_table,
        "percentiles": percentiles,
        "raw_results": results,
    }
