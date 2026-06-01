"""抽卡分析引擎 - 保底分析、统计分析、运势评分"""

import math
from collections import Counter, defaultdict
from datetime import datetime
from typing import List, Dict, Optional
from core.models import GachaRecord, BannerConfig, BANNER_CONFIGS, Rarity, get_max_rarity, get_mechanic_type


def get_rate_at_pull(config: BannerConfig, pull_number: int) -> float:
    """计算第N抽出5星的概率"""
    if pull_number >= config.hard_pity:
        return 1.0
    if pull_number >= config.soft_pity_start:
        extra = (pull_number - config.soft_pity_start + 1) * config.soft_pity_increment
        return min(config.base_rate_5star + extra, 1.0)
    return config.base_rate_5star


def get_expected_pulls(config: BannerConfig, current_pity: int) -> float:
    """计算期望抽数（到下一个5星）"""
    expected = 0.0
    cumulative_no_5star = 1.0
    for i in range(current_pity, config.hard_pity + 1):
        rate = get_rate_at_pull(config, i)
        pulls_from_now = i - current_pity + 1
        prob_this_pull = cumulative_no_5star * rate
        expected += pulls_from_now * prob_this_pull
        cumulative_no_5star *= (1 - rate)
    remaining = config.hard_pity - current_pity
    expected += (remaining + 1) * cumulative_no_5star
    return expected


def get_featured_expected(config: BannerConfig, current_pity: int,
                          is_guaranteed: bool) -> float:
    """计算抽到限定5星的期望抽数"""
    expected_5star = get_expected_pulls(config, current_pity)
    if not config.has_guarantee:
        return expected_5star
    if is_guaranteed:
        return expected_5star
    if config.featured_guarantee_rate >= 1.0:
        return expected_5star  # 100% UP，不会歪
    # 50/50: 概率歪，歪了要再抽一轮
    # 期望 = expected * (1 / featured_rate)
    return expected_5star / config.featured_guarantee_rate


def get_pull_probability(config: BannerConfig, current_pity: int,
                         target_pulls: int) -> float:
    """计算N抽内出5星的概率"""
    cumulative = 1.0
    no_5star = 1.0
    for i in range(current_pity, current_pity + target_pulls):
        if i > config.hard_pity:
            return 1.0
        rate = get_rate_at_pull(config, i)
        no_5star *= (1 - rate)
    return 1 - no_5star


class PityAnalyzer:
    """保底分析器"""

    def __init__(self, game: str, pool_type: str, pool_name: str = ""):
        self.game = game
        # 根据游戏和卡池名获取实际的保底机制类型
        mechanic_type = get_mechanic_type(game, pool_type, pool_name)
        self.config = BANNER_CONFIGS.get((game, mechanic_type))
        if not self.config:
            # 回退到 pool_type 直接查找
            self.config = BANNER_CONFIGS.get((game, pool_type))
        if not self.config:
            raise ValueError(f"未知的卡池配置: {game} / {pool_type}")

    def analyze(self, records: List[GachaRecord]) -> Dict:
        """分析保底状态"""
        if not records:
            return self._empty_result()

        max_rarity = get_max_rarity(self.game)

        # 按时间排序
        sorted_records = sorted(records, key=lambda r: (r.time, r.id))

        # 计算当前保底进度
        last_5star_idx = -1
        for i, r in enumerate(sorted_records):
            if r.rarity == max_rarity:
                last_5star_idx = i
        current_pity = len(sorted_records) - 1 - last_5star_idx if last_5star_idx >= 0 else len(sorted_records)

        # 判断是否大保底
        is_guaranteed = False
        if self.config.has_guarantee:
            for r in reversed(sorted_records):
                if r.rarity == max_rarity:
                    is_guaranteed = not r.is_featured
                    break

        # 最高星记录
        five_stars = [r for r in sorted_records if r.rarity == max_rarity]
        pity_counts = []
        last_idx = -1
        for i, r in enumerate(sorted_records):
            if r.rarity == max_rarity:
                pity_counts.append(i - last_idx)
                last_idx = i

        # 50/50 统计
        featured_wins = sum(1 for r in five_stars if r.is_featured)
        featured_losses = len(five_stars) - featured_wins

        # 期望计算
        expected_to_5star = get_expected_pulls(self.config, current_pity)
        expected_to_featured = get_featured_expected(self.config, current_pity, is_guaranteed)

        # 各抽数阈值概率
        prob_table = {}
        for t in [10, 20, 30, 50, 70, 80, 90, 100, 120, 150]:
            if t <= self.config.hard_pity or (self.config.up_hard_pity and t <= self.config.up_hard_pity):
                prob_table[t] = get_pull_probability(self.config, current_pity, t)

        # UP硬保底进度
        up_hard_pity_remaining = 0
        if self.config.up_hard_pity > 0:
            # 统计当前垫了多少抽（从上次出6星算起，或从上次歪6星后的大保底重置点算起）
            up_hard_pity_remaining = max(0, self.config.up_hard_pity - current_pity)

        # 十连保底进度
        multi_pity_progress = 0
        if self.config.multi_pity_size > 0:
            multi_pity_progress = current_pity % self.config.multi_pity_size

        # 自选/兑换进度
        exchange_progress = 0
        if self.config.exchange_threshold > 0:
            exchange_progress = min(len(sorted_records), self.config.exchange_threshold)

        return {
            "config": self.config,
            "current_pity": current_pity,
            "is_guaranteed": is_guaranteed,
            "pulls_to_hard": self.config.hard_pity - current_pity,
            "current_rate": get_rate_at_pull(self.config, current_pity),
            "expected_to_5star": round(expected_to_5star, 2),
            "expected_to_featured": round(expected_to_featured, 2),
            "prob_table": prob_table,
            "total_5star": len(five_stars),
            "total_4star": sum(1 for r in sorted_records if r.rarity == 4),
            "total_pulls": len(sorted_records),
            "pity_counts": pity_counts,
            "avg_pity": round(sum(pity_counts) / len(pity_counts), 2) if pity_counts else 0,
            "min_pity": min(pity_counts) if pity_counts else 0,
            "max_pity": max(pity_counts) if pity_counts else 0,
            "featured_wins": featured_wins,
            "featured_losses": featured_losses,
            "featured_rate": round(featured_wins / len(five_stars) * 100, 1) if five_stars else 0,
            "five_stars": five_stars,
            "rate_curve": self._get_rate_curve(current_pity),
            # 扩展字段
            "up_hard_pity": self.config.up_hard_pity,
            "up_hard_pity_remaining": up_hard_pity_remaining,
            "multi_pity_size": self.config.multi_pity_size,
            "multi_pity_progress": multi_pity_progress,
            "exchange_threshold": self.config.exchange_threshold,
            "exchange_progress": exchange_progress,
            "description": self.config.description,
        }

    def _get_rate_curve(self, current_pity: int) -> List[Dict]:
        """获取从当前抽数到硬保底的概率曲线"""
        curve = []
        for i in range(current_pity, self.config.hard_pity + 1):
            rate = get_rate_at_pull(self.config, i)
            curve.append({"pull": i, "pulls_from_now": i - current_pity, "rate": rate})
        return curve

    def _empty_result(self):
        return {
            "config": self.config,
            "current_pity": 0, "is_guaranteed": False,
            "pulls_to_hard": self.config.hard_pity,
            "current_rate": self.config.base_rate_5star,
            "expected_to_5star": 0, "expected_to_featured": 0,
            "prob_table": {}, "total_5star": 0, "total_4star": 0, "total_pulls": 0,
            "pity_counts": [], "avg_pity": 0, "min_pity": 0, "max_pity": 0,
            "featured_wins": 0, "featured_losses": 0, "featured_rate": 0,
            "five_stars": [], "rate_curve": [],
            "up_hard_pity": self.config.up_hard_pity,
            "up_hard_pity_remaining": self.config.up_hard_pity,
            "multi_pity_size": self.config.multi_pity_size,
            "multi_pity_progress": 0,
            "exchange_threshold": self.config.exchange_threshold,
            "exchange_progress": 0,
            "description": self.config.description,
        }


class StatsAnalyzer:
    """统计分析器"""

    def __init__(self, records: List[GachaRecord], game: str = ""):
        self.records = records
        self.game = game

    def get_summary(self) -> Dict:
        """获取总览统计"""
        if not self.records:
            return {"total": 0}

        max_rarity = get_max_rarity(self.game) if self.game else 5
        rarity_count = Counter(r.rarity for r in self.records)
        total = len(self.records)

        return {
            "total": total,
            "star_5": rarity_count.get(max_rarity, 0),
            "star_4": rarity_count.get(4, 0),
            "star_3": rarity_count.get(3, 0),
            "rate_max": round(rarity_count.get(max_rarity, 0) / total * 100, 2) if total else 0,
            "rate_4": round(rarity_count.get(4, 0) / total * 100, 2) if total else 0,
            "rate_3": round(rarity_count.get(3, 0) / total * 100, 2) if total else 0,
        }

    def get_pool_distribution(self) -> Dict:
        """获取卡池分布"""
        pool_counts = Counter(r.pool_type for r in self.records)
        return dict(pool_counts)

    def get_monthly_trend(self) -> Dict:
        """获取月度趋势"""
        monthly = defaultdict(int)
        for r in self.records:
            if r.time:
                month = r.time[:7]  # YYYY-MM
                monthly[month] += 1
        return dict(sorted(monthly.items()))

    def get_pull_distribution(self, rarity: int = 5) -> List[int]:
        """获取出货抽数分布"""
        sorted_records = sorted(self.records, key=lambda r: (r.time, r.id))
        distribution = []
        last_idx = -1
        for i, r in enumerate(sorted_records):
            if r.rarity == rarity:
                distribution.append(i - last_idx)
                last_idx = i
        return distribution

    def get_luck_rating(self) -> Dict:
        """运势评分"""
        max_rarity = get_max_rarity(self.game) if self.game else 5
        distribution = self.get_pull_distribution(max_rarity)
        if not distribution:
            return {"rating": "无数据", "score": 0, "description": "暂无5星记录"}

        avg = sum(distribution) / len(distribution)
        config = BANNER_CONFIGS.get((self.records[0].game, "character"))
        theoretical_avg = 62.5 if not config else 1 / config.base_rate_5star

        if avg <= theoretical_avg * 0.6:
            rating, desc = "SSR 欧皇", "你的运气简直逆天！"
        elif avg <= theoretical_avg * 0.8:
            rating, desc = "SR 比较欧", "运气不错，继续保持！"
        elif avg <= theoretical_avg * 1.0:
            rating, desc = "R 正常", "运气在正常范围内。"
        elif avg <= theoretical_avg * 1.2:
            rating, desc = "N 有点非", "运气稍微差了一点。"
        elif avg <= theoretical_avg * 1.5:
            rating, desc = "N 非酋", "建议洗手后再抽。"
        else:
            rating, desc = "NN 究极非酋", "你是天选之人（负面意义上）。"

        # 计算0-100分
        score = max(0, min(100, int(100 - (avg - theoretical_avg * 0.5) / theoretical_avg * 100)))

        return {"rating": rating, "score": score, "description": desc, "avg_pulls": round(avg, 1)}

    def get_time_distribution(self) -> Dict:
        """按小时分布"""
        hourly = defaultdict(int)
        for r in self.records:
            if r.time and len(r.time) >= 13:
                hour = r.time[11:13]
                hourly[hour] += 1
        return dict(sorted(hourly.items()))

    def get_featured_stats(self) -> Dict:
        """50/50 统计"""
        max_rarity = get_max_rarity(self.game) if self.game else 5
        five_stars = [r for r in self.records if r.rarity == max_rarity]
        if not five_stars:
            return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0}

        wins = sum(1 for r in five_stars if r.is_featured)
        losses = len(five_stars) - wins
        return {
            "total": len(five_stars),
            "wins": wins,
            "losses": losses,
            "win_rate": round(wins / len(five_stars) * 100, 1),
        }
