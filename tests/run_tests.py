"""无 pytest 时的最小测试运行器（覆盖核心断言）"""
import sys
import os
import tempfile
import traceback
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

PASSED = []
FAILED = []


def approx(a, b, rel=1e-6):
    return abs(a - b) <= rel * max(1.0, abs(b))


def run(name, fn):
    try:
        fn()
        PASSED.append(name)
        print(f"  PASS {name}")
    except Exception:
        FAILED.append(name)
        print(f"  FAIL {name}")
        traceback.print_exc()


# ---- analyzer ----
from core.analyzer import (
    get_rate_at_pull, get_expected_pulls, get_featured_expected,
    get_pull_probability, PityAnalyzer,
)
from core.models import BANNER_CONFIGS, GachaRecord, make_item_id

c = BANNER_CONFIGS[("genshin", "character")]
w = BANNER_CONFIGS[("genshin", "weapon")]


def t_rates():
    assert approx(get_rate_at_pull(c, 1), 0.006)
    assert approx(get_rate_at_pull(c, 73), 0.006)
    assert approx(get_rate_at_pull(c, 74), 0.066)
    assert approx(get_rate_at_pull(c, 75), 0.126)
    assert get_rate_at_pull(c, 90) == 1.0


def t_expected():
    e0 = get_expected_pulls(c, 0)
    assert 55 < e0 < 70, e0
    e73 = get_expected_pulls(c, 73)
    assert e73 < 12, e73
    assert approx(get_expected_pulls(c, 89), 1.0)
    assert approx(get_expected_pulls(c, 90), 1.0)
    assert get_expected_pulls(c, 10) < e0


def t_featured():
    e0 = get_expected_pulls(c, 0)
    assert approx(get_featured_expected(c, 0, False), e0 * 1.5)
    assert approx(get_featured_expected(c, 0, True), e0)
    ew = get_expected_pulls(w, 0)
    fw = get_featured_expected(w, 0, False)
    assert approx(fw, ew * 1.25)
    assert fw < ew / 0.75


def t_prob():
    assert approx(get_pull_probability(c, 0, 0), 0.0)
    assert approx(get_pull_probability(c, 0, 90), 1.0)
    assert approx(get_pull_probability(c, 0, 1), 0.006)


def t_analyzer():
    def rec(i, rarity=3, featured=False):
        return GachaRecord(
            id=i, account_id=1, game="genshin", pool_type="character",
            item_id=f"id{i}", item_name=f"item{i}", rarity=rarity,
            is_featured=featured, time=f"2024-01-01 00:00:{i:02d}",
        )
    r = PityAnalyzer("genshin", "character").analyze([])
    assert r["total_pulls"] == 0
    r = PityAnalyzer("genshin", "character").analyze([rec(i) for i in range(1, 21)])
    assert r["current_pity"] == 20
    r = PityAnalyzer("genshin", "character").analyze(
        [rec(1, 5, True)] + [rec(i) for i in range(2, 11)]
    )
    assert r["current_pity"] == 9
    assert r["is_guaranteed"] is False
    r = PityAnalyzer("genshin", "character").analyze([rec(1, 5, False)])
    assert r["is_guaranteed"] is True
    r = PityAnalyzer("genshin", "character").analyze([rec(i) for i in range(1, 74)])
    assert r["current_pity"] == 73
    assert approx(r["current_rate"], 0.066)
    assert r["rate_curve"][0]["pull"] == 74
    assert r["rate_curve"][0]["pulls_from_now"] == 1
    assert r["rate_curve"][-1]["pull"] == 90


def t_item_id():
    a = make_item_id("g", "c", "t", "n", 0)
    b = make_item_id("g", "c", "t", "n", 0)
    d = make_item_id("g", "c", "t", "n", 1)
    assert a == b and a != d and a


# ---- database ----
from core.database import Database
from core.models import Account


def _fresh_db(tmp):
    Database._instance = None
    inst = Database.__new__(Database)
    inst._initialized = False
    inst._conn = None

    class FakeConfig:
        db_path = str(Path(tmp) / "t.db")

        @property
        def backup_dir(self):
            p = Path(tmp) / "bk"
            p.mkdir(exist_ok=True)
            return str(p)

        def get_int(self, key, default=None):
            return default if default is not None else 10

    inst.config = FakeConfig()
    inst.db_path = inst.config.db_path
    inst._init_db()
    Database._instance = inst
    return inst


def t_db():
    import sqlite3
    with tempfile.TemporaryDirectory() as tmp:
        db = _fresh_db(tmp)
        acc = Account(game="genshin", uid="1", nickname="t", server="cn")
        acc.id = db.add_account(acc)

        def rec(name, time, item_id=""):
            return GachaRecord(
                account_id=acc.id, game="genshin", pool_type="character",
                item_id=item_id, item_name=name, rarity=5, is_featured=True, time=time,
            )

        # empty item_id → only 1
        n = db.add_records([
            rec("A", "2024-01-01 10:00:00", ""),
            rec("B", "2024-01-01 10:00:01", ""),
        ])
        assert n == 1, n

        # generated ids → all inserted
        n = db.add_records([
            rec("A", "t0", make_item_id("g", "c", "t0", "A", 0)),
            rec("A", "t0", make_item_id("g", "c", "t0", "A", 1)),
            rec("B", "t1", make_item_id("g", "c", "t1", "B", 0)),
        ])
        assert n == 3, n

        # import_json generates ids
        payload = (
            '[{"game":"genshin","pool_type":"character","item_name":"X",'
            '"rarity":5,"time":"2024-02-01 10:00:00"},'
            '{"game":"genshin","pool_type":"character","item_name":"Y",'
            '"rarity":5,"time":"2024-02-01 10:00:01"}]'
        )
        n = db.import_json(payload, acc.id)
        assert n == 2, n

        # export includes item_id
        exported = db.export_json(acc.id)
        assert "item_id" in exported

        # backup has data
        path = db.backup()
        conn = sqlite3.connect(path)
        try:
            cnt = conn.execute("SELECT COUNT(*) FROM gacha_records").fetchone()[0]
            assert cnt >= 3, cnt
        finally:
            conn.close()
        db.close()
        Database._instance = None


print("Running core tests...")
run("rate_at_pull", t_rates)
run("expected_pulls", t_expected)
run("featured_expected", t_featured)
run("pull_probability", t_prob)
run("pity_analyzer", t_analyzer)
run("make_item_id", t_item_id)
run("database", t_db)

print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
sys.exit(1 if FAILED else 0)
