"""config 配置管理测试"""

import sys
import os
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config import Config


class TestConfigDefaults(unittest.TestCase):
    def test_default_values(self):
        cfg = Config()
        self.assertIsInstance(cfg.get_request_interval(), float)
        self.assertGreater(cfg.get_request_interval(), 0)
        self.assertIsInstance(cfg.get_request_timeout(), int)
        self.assertGreater(cfg.get_request_timeout(), 0)

    def test_dot_notation_get(self):
        cfg = Config()
        # cache_paths.genshin.cn should exist from config.yaml
        val = cfg.get("cache_paths.genshin.cn")
        self.assertIsNotNone(val)

    def test_missing_key_returns_default(self):
        cfg = Config()
        self.assertIsNone(cfg.get("nonexistent.key"))
        self.assertEqual(cfg.get("nonexistent.key", "fallback"), "fallback")

    def test_set_and_get(self):
        cfg = Config()
        cfg.set("test.key", "value")
        self.assertEqual(cfg.get("test.key"), "value")

    def test_get_int_float(self):
        cfg = Config()
        cfg.set("test.num", 42)
        self.assertEqual(cfg.get_int("test.num"), 42)
        self.assertIsInstance(cfg.get_int("test.num"), int)

        cfg.set("test.flt", 3.14)
        self.assertAlmostEqual(cfg.get_float("test.flt"), 3.14)


if __name__ == "__main__":
    unittest.main()
