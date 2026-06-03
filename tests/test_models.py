"""models 数据模型测试"""

import sys
import os
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.models import (
    GachaRecord, Account, BannerConfig, BANNER_CONFIGS,
    get_max_rarity, get_mechanic_type, GAME_NAMES,
)


class TestModels(unittest.TestCase):
    def test_gacha_record_defaults(self):
        r = GachaRecord(account_id=1, game="genshin", pool_type="character",
                        item_name="甘雨", rarity=5, time="2025-01-01 12:00:00")
        self.assertEqual(r.account_id, 1)
        self.assertEqual(r.pool_name, "")
        self.assertFalse(r.is_featured)

    def test_account_defaults(self):
        a = Account(game="genshin", uid="123", nickname="test")
        self.assertEqual(a.server, "")
        self.assertTrue(a.is_active)

    def test_max_rarity_by_game(self):
        self.assertEqual(get_max_rarity("genshin"), 5)
        self.assertEqual(get_max_rarity("starrail"), 5)
        self.assertEqual(get_max_rarity("zzz"), 5)
        self.assertEqual(get_max_rarity("arknights"), 6)
        self.assertEqual(get_max_rarity("endfield"), 6)
        self.assertEqual(get_max_rarity("wutheringwaves"), 5)

    def test_banner_configs_exist(self):
        self.assertIn(("genshin", "character"), BANNER_CONFIGS)
        self.assertIn(("starrail", "character"), BANNER_CONFIGS)
        self.assertIn(("zzz", "character"), BANNER_CONFIGS)

    def test_banner_config_fields(self):
        config = BANNER_CONFIGS[("genshin", "character")]
        self.assertGreater(config.hard_pity, 0)
        self.assertGreater(config.base_rate_5star, 0)
        self.assertGreater(config.soft_pity_start, 0)

    def test_game_names_complete(self):
        expected_games = {"genshin", "starrail", "zzz", "wutheringwaves", "endfield", "arknights"}
        self.assertEqual(set(GAME_NAMES.keys()), expected_games)

    def test_mechanic_type_mapping(self):
        self.assertEqual(get_mechanic_type("genshin", "character"), "character")
        self.assertEqual(get_mechanic_type("genshin", "weapon"), "weapon")


if __name__ == "__main__":
    unittest.main()
