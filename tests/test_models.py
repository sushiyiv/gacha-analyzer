"""数据模型辅助函数测试"""

from core.models import make_item_id


class TestMakeItemId:
    def test_stable_for_same_input(self):
        a = make_item_id("genshin", "character", "2024-01-01 12:00:00", "纳西妲", 0)
        b = make_item_id("genshin", "character", "2024-01-01 12:00:00", "纳西妲", 0)
        assert a == b

    def test_seq_distinguishes_same_second(self):
        a = make_item_id("genshin", "character", "2024-01-01 12:00:00", "纳西妲", 0)
        b = make_item_id("genshin", "character", "2024-01-01 12:00:00", "纳西妲", 1)
        assert a != b

    def test_name_distinguishes(self):
        a = make_item_id("genshin", "character", "2024-01-01 12:00:00", "纳西妲")
        b = make_item_id("genshin", "character", "2024-01-01 12:00:00", "钟离")
        assert a != b

    def test_not_empty(self):
        assert make_item_id("genshin", "character", "t", "n")
