"""数据库唯一约束、导入、备份、data_version、保底计数测试"""

import sqlite3

import pytest

from core.database import Database
from core.models import Account, GachaRecord, make_item_id


@pytest.fixture
def db(tmp_path, monkeypatch):
    """隔离的临时数据库实例"""
    from core.config import Config

    db_file = tmp_path / "test.db"
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()

    Database._instance = None
    Config._instance = None
    Config._config = None

    instance = Database.__new__(Database)
    instance._initialized = False
    instance.config = None
    instance._conn = None
    instance._lock = __import__("threading").RLock()

    class FakeConfig:
        db_path = str(db_file)

        @property
        def backup_dir(self):
            return str(backup_dir)

        def get_int(self, key, default=None):
            return default if default is not None else 10

    instance.config = FakeConfig()
    instance.db_path = str(db_file)
    instance._conn = None
    instance._initialized = True
    instance._init_db()
    Database._instance = instance
    yield instance
    instance.close()
    Database._instance = None
    Config._instance = None
    Config._config = None


def _account(db, game="genshin", uid="100000001"):
    acc = Account(game=game, uid=uid, nickname="t", server="cn")
    acc.id = db.add_account(acc)
    return acc


def _rec(account_id, name, time, item_id="", rarity=5, featured=True, pool_type="character"):
    return GachaRecord(
        account_id=account_id, game="genshin", pool_type=pool_type,
        item_id=item_id, item_name=name, rarity=rarity, is_featured=featured, time=time,
    )


class TestAddRecords:
    def test_empty_item_id_only_first(self, db):
        acc = _account(db)
        recs = [
            _rec(acc.id, "A", "2024-01-01 10:00:00", ""),
            _rec(acc.id, "B", "2024-01-01 10:00:01", ""),
            _rec(acc.id, "C", "2024-01-01 10:00:02", ""),
        ]
        count = db.add_records(recs)
        assert count == 1

    def test_generated_item_id_all_inserted(self, db):
        acc = _account(db)
        recs = [
            _rec(acc.id, n, t, make_item_id("genshin", "character", t, n, i))
            for i, (n, t) in enumerate([
                ("A", "2024-01-01 10:00:00"),
                ("A", "2024-01-01 10:00:00"),
                ("B", "2024-01-01 10:00:01"),
            ])
        ]
        count = db.add_records(recs)
        assert count == 3

    def test_duplicate_item_id_skipped(self, db):
        acc = _account(db)
        rec = _rec(acc.id, "A", "2024-01-01 10:00:00", "fixed-id")
        assert db.add_records([rec]) == 1
        assert db.add_records([rec]) == 0

    def test_import_json_generates_ids(self, db):
        acc = _account(db, uid="100000002")
        payload = (
            '[{"game":"genshin","pool_type":"character","item_name":"A",'
            '"rarity":5,"time":"2024-01-01 10:00:00"},'
            '{"game":"genshin","pool_type":"character","item_name":"B",'
            '"rarity":5,"time":"2024-01-01 10:00:01"}]'
        )
        count = db.import_json(payload, acc.id)
        assert count == 2


class TestExportRoundTrip:
    def test_export_includes_item_id(self, db):
        acc = _account(db, uid="100000003")
        db.add_records([_rec(acc.id, "A", "2024-01-01 10:00:00", "abc123")])
        data = db.export_json(acc.id)
        assert '"item_id": "abc123"' in data


class TestBackupRestore:
    def test_backup_creates_file(self, db):
        acc = _account(db, uid="100000004")
        db.add_records([_rec(acc.id, "A", "2024-01-01 10:00:00", "id1")])
        path = db.backup()
        assert path.endswith(".db")
        conn = sqlite3.connect(path)
        try:
            n = conn.execute("SELECT COUNT(*) FROM gacha_records").fetchone()[0]
            assert n == 1
        finally:
            conn.close()

    def test_wal_data_included(self, db):
        acc = _account(db, uid="100000005")
        db.add_records([_rec(acc.id, "A", "2024-01-01 10:00:00", "wal-id")])
        path = db.backup()
        conn = sqlite3.connect(path)
        try:
            names = {r[0] for r in conn.execute("SELECT item_name FROM gacha_records")}
            assert "A" in names
        finally:
            conn.close()


class TestDataVersion:
    def test_increases_on_add(self, db):
        acc = _account(db, uid="100000010")
        v0 = db.data_version
        db.add_records([_rec(acc.id, "A", "2024-01-01 10:00:00", "id-v1")])
        assert db.data_version > v0

    def test_unchanged_when_all_duplicates(self, db):
        acc = _account(db, uid="100000011")
        rec = _rec(acc.id, "A", "2024-01-01 10:00:00", "id-v2")
        db.add_records([rec])
        v1 = db.data_version
        db.add_records([rec])
        assert db.data_version == v1

    def test_increases_on_delete_account(self, db):
        acc = _account(db, uid="100000012")
        db.add_records([_rec(acc.id, "A", "2024-01-01 10:00:00", "id-v3")])
        v1 = db.data_version
        db.delete_account(acc.id)
        assert db.data_version > v1

    def test_increases_on_calculate_pity(self, db):
        acc = _account(db, uid="100000013")
        recs = [
            _rec(acc.id, "A", "2024-01-01 10:00:00", "p1", rarity=3, featured=False),
            _rec(acc.id, "B", "2024-01-01 10:00:01", "p2", rarity=5, featured=True),
            _rec(acc.id, "C", "2024-01-01 10:00:02", "p3", rarity=3, featured=False),
        ]
        db.add_records(recs)
        v1 = db.data_version
        db.calculate_pity_counts(acc.id)
        assert db.data_version > v1


class TestPityCounts:
    def test_pity_count_after_5star(self, db):
        acc = _account(db, uid="100000020")
        recs = [
            _rec(acc.id, "s1", "2024-01-01 10:00:00", "a1", rarity=3, featured=False),
            _rec(acc.id, "s2", "2024-01-01 10:00:01", "a2", rarity=3, featured=False),
            _rec(acc.id, "s3", "2024-01-01 10:00:02", "a3", rarity=3, featured=False),
            _rec(acc.id, "gold", "2024-01-01 10:00:03", "a4", rarity=5, featured=True),
            _rec(acc.id, "s4", "2024-01-01 10:00:04", "a5", rarity=3, featured=False),
        ]
        db.add_records(recs)
        db.calculate_pity_counts(acc.id)

        rows = db.get_records(acc.id)
        by_name = {r.item_name: r for r in rows}
        assert by_name["gold"].pity_count == 4
        # 出金后的下一条不写 pity_count（未到下一次五星）
        assert by_name["s4"].pity_count == 0

    def test_pity_resets_each_5star(self, db):
        acc = _account(db, uid="100000021")
        recs = [
            _rec(acc.id, "g1", "2024-01-01 10:00:00", "b1", rarity=5, featured=True),
            _rec(acc.id, "x1", "2024-01-01 10:00:01", "b2", rarity=3, featured=False),
            _rec(acc.id, "g2", "2024-01-01 10:00:02", "b3", rarity=5, featured=False),
        ]
        db.add_records(recs)
        db.calculate_pity_counts(acc.id)
        rows = {r.item_name: r for r in db.get_records(acc.id)}
        assert rows["g1"].pity_count == 1
        assert rows["g2"].pity_count == 2

    def test_pools_counted_independently(self, db):
        acc = _account(db, uid="100000022")
        recs = [
            GachaRecord(
                account_id=acc.id, game="genshin", pool_type="character",
                item_id="c1", item_name="c_a", rarity=3, is_featured=False,
                time="2024-01-01 10:00:00",
            ),
            GachaRecord(
                account_id=acc.id, game="genshin", pool_type="weapon",
                item_id="w1", item_name="w_a", rarity=3, is_featured=False,
                time="2024-01-01 10:00:00",
            ),
            GachaRecord(
                account_id=acc.id, game="genshin", pool_type="character",
                item_id="c2", item_name="c_gold", rarity=5, is_featured=True,
                time="2024-01-01 10:00:01",
            ),
            GachaRecord(
                account_id=acc.id, game="genshin", pool_type="weapon",
                item_id="w2", item_name="w_gold", rarity=5, is_featured=True,
                time="2024-01-01 10:00:01",
            ),
        ]
        db.add_records(recs)
        db.calculate_pity_counts(acc.id)
        rows = {r.item_name: r for r in db.get_records(acc.id)}
        assert rows["c_gold"].pity_count == 2
        assert rows["w_gold"].pity_count == 2

    def test_import_json_recalculates_pity(self, db):
        acc = _account(db, uid="100000023")
        payload = (
            '[{"game":"genshin","pool_type":"character","item_name":"s1",'
            '"rarity":3,"time":"2024-01-01 10:00:00"},'
            '{"game":"genshin","pool_type":"character","item_name":"g1",'
            '"rarity":5,"time":"2024-01-01 10:00:01"}]'
        )
        db.import_json(payload, acc.id)
        rows = {r.item_name: r for r in db.get_records(acc.id)}
        assert rows["g1"].pity_count == 2
