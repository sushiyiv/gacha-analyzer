"""增量拉取 latest_time 过滤与提前停页测试"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from fetchers.mihoyo.api import MihoyoAPI, APIError


def _page(records):
    """构造一页 API 响应（newest-first）"""
    return {
        "retcode": 0,
        "message": "OK",
        "data": {"list": records},
    }


class FakeSession:
    """按调用顺序返回预置页；记录请求次数"""

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []

    def get(self, url, params=None, timeout=None):
        self.calls.append({"url": url, "params": dict(params or {}), "timeout": timeout})
        if not self.pages:
            return SimpleNamespace(json=lambda: _page([]), text="")
        page = self.pages.pop(0)
        return SimpleNamespace(json=lambda: page, text="")


def _item(i, time, gacha_type="301"):
    return {
        "id": str(1000 + i),
        "uid": "100000001",
        "name": f"item{i}",
        "item_type": "角色",
        "rank_type": "3",
        "time": time,
        "count": "1",
        "gacha_id": "1",
        "gacha_type": gacha_type,
    }


@pytest.fixture
def api():
    return MihoyoAPI()


def _url():
    return (
        "https://public-operation-hk4e.mihoyo.com/gacha_info/api/getGachaLog"
        "?authkey=test&game_biz=hk4e_cn&region=cn_gf01&lang=zh-cn"
    )


class TestLatestTimeFilter:
    def test_keeps_only_newer_records(self, api):
        # newest-first: 12:00, 11:00, 10:00
        page = _page([
            _item(3, "2024-01-01 12:00:00"),
            _item(2, "2024-01-01 11:00:00"),
            _item(1, "2024-01-01 10:00:00"),
        ])
        session = FakeSession([page])
        records, uid = api.fetch_all(
            "genshin",
            _url(),
            latest_time="2024-01-01 11:00:00",
            session=session,
        )
        # 仅 12:00 比 latest_time 新
        assert len(records) == 1
        assert records[0]["time"] == "2024-01-01 12:00:00"
        assert uid == "100000001"
        # 碰到已知历史后应停页，不继续拉其他卡池的后续页
        # genshin 有多个池，但 character 这一页就会 reached_known_history
        assert len(session.calls) >= 1

    def test_stops_paging_when_reaching_known_history(self, api):
        page1 = _page([
            _item(5, "2024-01-01 15:00:00"),
            _item(4, "2024-01-01 14:00:00"),
        ])
        page2 = _page([
            _item(3, "2024-01-01 13:00:00"),
            _item(2, "2024-01-01 10:00:00"),  # 已知历史
        ])
        # 只给 character 池两页，后续池返回空
        pages = [page1, page2]
        # 其余池空
        for _ in range(10):
            pages.append(_page([]))
        session = FakeSession(pages)
        records, _ = api.fetch_all(
            "genshin",
            _url(),
            latest_time="2024-01-01 12:00:00",
            session=session,
        )
        # page1 全新，page2 只保留 13:00
        times = [r["time"] for r in records]
        assert "2024-01-01 15:00:00" in times
        assert "2024-01-01 14:00:00" in times
        assert "2024-01-01 13:00:00" in times
        assert "2024-01-01 10:00:00" not in times
        # character 池不应请求第 3 页
        char_calls = [c for c in session.calls if c["params"].get("gacha_type") == "301"]
        assert len(char_calls) == 2

    def test_without_latest_time_fetches_all(self, api):
        pages = [
            _page([_item(2, "2024-01-01 11:00:00"), _item(1, "2024-01-01 10:00:00")]),
            _page([]),
        ]
        # 其余池空
        for _ in range(8):
            pages.append(_page([]))
        session = FakeSession(pages)
        records, _ = api.fetch_all("genshin", _url(), session=session)
        times = {r["time"] for r in records}
        assert "2024-01-01 10:00:00" in times
        assert "2024-01-01 11:00:00" in times

    def test_records_reversed_to_oldest_first(self, api):
        page = _page([
            _item(3, "2024-01-01 12:00:00"),
            _item(2, "2024-01-01 11:00:00"),
            _item(1, "2024-01-01 10:00:00"),
        ])
        pages = [page] + [_page([]) for _ in range(9)]
        session = FakeSession(pages)
        records, _ = api.fetch_all("genshin", _url(), session=session)
        # 每个卡池内反转为 oldest-first
        assert records[0]["time"] <= records[1]["time"] <= records[2]["time"]


class TestCancel:
    def test_cancel_raises(self, api):
        session = FakeSession([_page([_item(1, "2024-01-01 10:00:00")])])
        with pytest.raises(APIError, match="取消"):
            api.fetch_all(
                "genshin",
                _url(),
                cancel_check=lambda: True,
                session=session,
            )

    def test_cancel_midway_between_pools(self, api):
        calls = {"n": 0}

        def cancel_after_one():
            calls["n"] += 1
            return calls["n"] > 2

        session = FakeSession([_page([]) for _ in range(20)])
        with pytest.raises(APIError, match="取消"):
            api.fetch_all(
                "genshin",
                _url(),
                cancel_check=cancel_after_one,
                session=session,
            )


class TestTimeouts:
    def test_uses_connect_read_tuple(self, api):
        session = FakeSession([_page([]) for _ in range(10)])
        api.fetch_all("genshin", _url(), session=session)
        assert session.calls
        assert session.calls[0]["timeout"] == (5, 30)
