"""analyzer 核心逻辑测试"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.analyzer import PityAnalyzer, StatsAnalyzer, get_rate_at_pull, get_expected_pulls
from core.models import GachaRecord, BANNER_CONFIGS


def _make_records(game, pool_type, pity_sequence):
    """根据保底出金序列生成测试记录

    pity_sequence: list of (pity_count, is_featured) 表示第几抽出金、是否UP
    """
    records = []
    pull_idx = 0
    for pity_count, is_featured in pity_sequence:
        for j in range(pity_count - 1):
            pull_idx += 1
            records.append(GachaRecord(
                account_id=1, game=game, pool_type=pool_type,
                item_name=f"3star_{pull_idx}", rarity=3, is_featured=False,
                time=f"2025-01-01 00:{pull_idx:02d}:00",
            ))
        pull_idx += 1
        records.append(GachaRecord(
            account_id=1, game=game, pool_type=pool_type,
            item_name=f"5star_{pull_idx}", rarity=5, is_featured=is_featured,
            time=f"2025-01-01 00:{pull_idx:02d}:00",
        ))
    return records


class TestRateAtPull(unittest.TestCase):
    def test_base_rate_before_soft_pity(self):
        config = BANNER_CONFIGS.get(("genshin", "character"))
        self.assertIsNotNone(config)
        rate = get_rate_at_pull(config, 1)
        self.assertAlmostEqual(rate, config.base_rate_5star, places=5)

    def test_rate_increases_during_soft_pity(self):
        config = BANNER_CONFIGS.get(("genshin", "character"))
        rate_start = get_rate_at_pull(config, config.soft_pity_start)
        rate_mid = get_rate_at_pull(config, config.soft_pity_start + 10)
        self.assertGreater(rate_mid, rate_start)

    def test_hard_pity_is_100_percent(self):
        config = BANNER_CONFIGS.get(("genshin", "character"))
        rate = get_rate_at_pull(config, config.hard_pity)
        self.assertEqual(rate, 1.0)


class TestExpectedPulls(unittest.TestCase):
    def test_expected_pulls_positive(self):
        config = BANNER_CONFIGS.get(("genshin", "character"))
        expected = get_expected_pulls(config, 0)
        self.assertGreater(expected, 0)
        self.assertLess(expected, config.hard_pity + 1)

    def test_expected_pulls_near_hard_pity(self):
        config = BANNER_CONFIGS.get(("genshin", "character"))
        expected = get_expected_pulls(config, config.hard_pity - 1)
        self.assertLessEqual(expected, 2.0)


class TestPityAnalyzer(unittest.TestCase):
    def test_empty_records(self):
        analyzer = PityAnalyzer("genshin", "character")
        result = analyzer.analyze([])
        self.assertEqual(result["current_pity"], 0)
        self.assertEqual(result["total_5star"], 0)

    def test_current_pity_counting(self):
        analyzer = PityAnalyzer("genshin", "character")
        records = _make_records("genshin", "character", [(30, True)])
        # 30抽出金后又抽了5发
        for i in range(5):
            records.append(GachaRecord(
                account_id=1, game="genshin", pool_type="character",
                item_name=f"3star_extra_{i}", rarity=3, is_featured=False,
                time=f"2025-01-01 01:{i:02d}:00",
            ))
        result = analyzer.analyze(records)
        self.assertEqual(result["current_pity"], 5)
        self.assertEqual(result["total_5star"], 1)

    def test_guaranteed_after_losing_5050(self):
        analyzer = PityAnalyzer("genshin", "character")
        records = _make_records("genshin", "character", [(60, False)])
        result = analyzer.analyze(records)
        self.assertTrue(result["is_guaranteed"])

    def test_not_guaranteed_after_winning_5050(self):
        analyzer = PityAnalyzer("genshin", "character")
        records = _make_records("genshin", "character", [(60, True)])
        result = analyzer.analyze(records)
        self.assertFalse(result["is_guaranteed"])


class TestStatsAnalyzer(unittest.TestCase):
    def test_empty_records(self):
        stats = StatsAnalyzer([], "genshin")
        summary = stats.get_summary()
        self.assertEqual(summary["total"], 0)

    def test_summary_counts(self):
        records = _make_records("genshin", "character", [(60, True), (70, False)])
        stats = StatsAnalyzer(records, "genshin")
        summary = stats.get_summary()
        self.assertEqual(summary["total"], 60 + 70)
        self.assertEqual(summary["star_5"], 2)

    def test_monthly_trend(self):
        records = [
            GachaRecord(account_id=1, game="genshin", pool_type="character",
                        item_name="a", rarity=3, time="2025-01-15 12:00:00"),
            GachaRecord(account_id=1, game="genshin", pool_type="character",
                        item_name="b", rarity=3, time="2025-02-15 12:00:00"),
        ]
        stats = StatsAnalyzer(records, "genshin")
        trend = stats.get_monthly_trend()
        self.assertEqual(trend["2025-01"], 1)
        self.assertEqual(trend["2025-02"], 1)


if __name__ == "__main__":
    unittest.main()
