"""保底分析公式与统计测试"""

import pytest

from core.analyzer import (
    get_rate_at_pull,
    get_expected_pulls,
    get_featured_expected,
    get_pull_probability,
    PityAnalyzer,
)
from core.models import GachaRecord, BANNER_CONFIGS


@pytest.fixture
def genshin_character():
    return BANNER_CONFIGS[("genshin", "character")]


@pytest.fixture
def genshin_weapon():
    return BANNER_CONFIGS[("genshin", "weapon")]


class TestRateAtPull:
    def test_base_rate_before_soft_pity(self, genshin_character):
        assert get_rate_at_pull(genshin_character, 1) == pytest.approx(0.006)
        assert get_rate_at_pull(genshin_character, 73) == pytest.approx(0.006)

    def test_soft_pity_start(self, genshin_character):
        # 第 74 抽进入软保底，额外 +0.06
        assert get_rate_at_pull(genshin_character, 74) == pytest.approx(0.066)

    def test_soft_pity_ramp(self, genshin_character):
        # 第 75 抽：0.006 + 2*0.06 = 0.126
        assert get_rate_at_pull(genshin_character, 75) == pytest.approx(0.126)

    def test_hard_pity_is_certain(self, genshin_character):
        assert get_rate_at_pull(genshin_character, 90) == 1.0
        assert get_rate_at_pull(genshin_character, 91) == 1.0


class TestExpectedPulls:
    def test_fresh_pity_reasonable(self, genshin_character):
        # 原神角色池从 0 抽起，期望约 62 抽（含软保底）
        e = get_expected_pulls(genshin_character, 0)
        assert 55 < e < 70

    def test_at_soft_pity_boundary(self, genshin_character):
        # 已抽 73，下一抽是 74（软保底起点）
        # 若 off-by-one 传成第 73 抽的概率，期望会明显偏大
        e = get_expected_pulls(genshin_character, 73)
        assert e < 12

    def test_near_hard_pity(self, genshin_character):
        # 已抽 89，下一抽必出
        assert get_expected_pulls(genshin_character, 89) == pytest.approx(1.0)

    def test_at_hard_pity(self, genshin_character):
        # 已抽 90，仍应再抽 1 次（rate=1）
        assert get_expected_pulls(genshin_character, 90) == pytest.approx(1.0)

    def test_decreases_with_pity(self, genshin_character):
        assert get_expected_pulls(genshin_character, 10) < get_expected_pulls(genshin_character, 0)


class TestFeaturedExpected:
    def test_5050_formula(self, genshin_character):
        e = get_expected_pulls(genshin_character, 0)
        featured = get_featured_expected(genshin_character, 0, is_guaranteed=False)
        assert featured == pytest.approx(e * (2.0 - 0.5))

    def test_guaranteed_equals_base(self, genshin_character):
        e = get_expected_pulls(genshin_character, 0)
        assert get_featured_expected(genshin_character, 0, True) == pytest.approx(e)

    def test_weapon_7525(self, genshin_weapon):
        e = get_expected_pulls(genshin_weapon, 0)
        featured = get_featured_expected(genshin_weapon, 0, False)
        assert featured == pytest.approx(e * (2.0 - 0.75))
        # 旧公式 E/p 会给出 E/0.75 ≈ 1.333E，应明显大于正确值 1.25E
        assert featured < e / 0.75


class TestPullProbability:
    def test_zero_target(self, genshin_character):
        assert get_pull_probability(genshin_character, 0, 0) == pytest.approx(0.0)

    def test_certain_at_hard_pity(self, genshin_character):
        assert get_pull_probability(genshin_character, 0, 90) == pytest.approx(1.0)

    def test_single_pull_is_base(self, genshin_character):
        assert get_pull_probability(genshin_character, 0, 1) == pytest.approx(0.006)


def _rec(i, rarity=3, featured=False, time=None, game="genshin"):
    return GachaRecord(
        id=i, account_id=1, game=game, pool_type="character",
        item_id=f"id{i}", item_name=f"item{i}", rarity=rarity,
        is_featured=featured, time=time or f"2024-01-01 00:00:{i:02d}",
    )


class TestPityAnalyzer:
    def test_empty(self):
        result = PityAnalyzer("genshin", "character").analyze([])
        assert result["total_pulls"] == 0
        assert result["current_pity"] == 0

    def test_no_5star_all_counted(self):
        records = [_rec(i) for i in range(1, 21)]
        result = PityAnalyzer("genshin", "character").analyze(records)
        assert result["current_pity"] == 20
        assert result["total_5star"] == 0

    def test_pity_after_5star(self):
        records = [_rec(1, rarity=5, featured=True)] + [_rec(i) for i in range(2, 11)]
        result = PityAnalyzer("genshin", "character").analyze(records)
        assert result["current_pity"] == 9
        assert result["is_guaranteed"] is False

    def test_guaranteed_after_loss(self):
        records = [_rec(1, rarity=5, featured=False)]
        result = PityAnalyzer("genshin", "character").analyze(records)
        assert result["is_guaranteed"] is True

    def test_current_rate_uses_next_pull(self):
        # 已抽 73 → 下一抽编号 74，应命中软保底 0.066
        records = [_rec(i) for i in range(1, 74)]
        result = PityAnalyzer("genshin", "character").analyze(records)
        assert result["current_pity"] == 73
        assert result["current_rate"] == pytest.approx(0.066)

    def test_rate_curve_starts_at_next_pull(self):
        records = [_rec(i) for i in range(1, 74)]
        result = PityAnalyzer("genshin", "character").analyze(records)
        curve = result["rate_curve"]
        assert curve[0]["pull"] == 74
        assert curve[0]["pulls_from_now"] == 1
        assert curve[-1]["pull"] == 90
