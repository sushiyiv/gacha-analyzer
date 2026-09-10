"""SQLite 数据库：账号 / 抽卡记录 CRUD、保底计数、备份导入导出"""

import logging
import sqlite3
import json
import shutil
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from core.models import Account, GachaRecord, make_item_id
from core.config import Config

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    game TEXT NOT NULL,
    uid TEXT NOT NULL,
    nickname TEXT DEFAULT '',
    server TEXT DEFAULT 'cn',
    is_active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now','localtime')),
    updated_at TEXT DEFAULT (datetime('now','localtime')),
    UNIQUE(game, uid)
);

CREATE TABLE IF NOT EXISTS gacha_records (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    account_id INTEGER NOT NULL,
    game TEXT NOT NULL,
    pool_type TEXT NOT NULL,
    pool_name TEXT DEFAULT '',
    item_id TEXT DEFAULT '',
    item_name TEXT NOT NULL,
    item_type TEXT DEFAULT '',
    rarity INTEGER NOT NULL,
    is_featured INTEGER DEFAULT 0,
    count INTEGER DEFAULT 1,
    time TEXT NOT NULL,
    pity_count INTEGER DEFAULT 0,
    gacha_id TEXT DEFAULT '',
    pull_index INTEGER DEFAULT 0,
    raw_data TEXT DEFAULT '',
    created_at TEXT DEFAULT (datetime('now','localtime')),
    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
    UNIQUE(account_id, item_id)
);

CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE INDEX IF NOT EXISTS idx_records_account ON gacha_records(account_id);
CREATE INDEX IF NOT EXISTS idx_records_game ON gacha_records(game);
CREATE INDEX IF NOT EXISTS idx_records_pool ON gacha_records(pool_type);
CREATE INDEX IF NOT EXISTS idx_records_rarity ON gacha_records(rarity);
CREATE INDEX IF NOT EXISTS idx_records_time ON gacha_records(time);
"""


class Database:
    """单例 SQLite 管理器"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, "_initialized"):
            self.config = Config()
            self.db_path = self.config.db_path
            self._conn = None
            # 单例连接会被工作线程（获取入库）共用，需串行化
            self._lock = threading.RLock()
            self._data_version = 0
            self._initialized = True
            self._init_db()

    def _ensure_conn(self):
        if self._conn is None:
            # check_same_thread=False：获取线程写库时使用同一连接
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    @contextmanager
    def connect(self):
        lock = getattr(self, "_lock", None)
        if lock is None:
            lock = self._lock = threading.RLock()
        with lock:
            yield self._ensure_conn()

    def bump_data_version(self):
        self._data_version = getattr(self, "_data_version", 0) + 1

    @property
    def data_version(self) -> int:
        return getattr(self, "_data_version", 0)

    def _init_db(self):
        with self.connect() as conn:
            conn.executescript(_SCHEMA)
            conn.commit()

            try:
                conn.execute("SELECT pool_name FROM gacha_records LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE gacha_records ADD COLUMN pool_name TEXT DEFAULT ''")
                conn.commit()

            schema_changed = self._migrate_unique_constraint(conn)
            self.fix_zzz_bangboo_batches(conn)

            # 仅在 schema 升级或首次建库时全量重算，避免每次启动扫全表
            ver_row = conn.execute(
                "SELECT value FROM app_meta WHERE key='schema_version'"
            ).fetchone()
            stored_ver = int(ver_row[0]) if ver_row else 0
            if schema_changed or stored_ver < SCHEMA_VERSION:
                logger.info("rebuild pity counts (schema %s -> %s)", stored_ver, SCHEMA_VERSION)
                self._rebuild_pity_counts(conn)
                conn.execute(
                    "INSERT OR REPLACE INTO app_meta (key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
                conn.commit()

    def _migrate_unique_constraint(self, conn) -> bool:
        """旧库 UNIQUE 约束可能不同，必要时整表重建。返回是否发生迁移。"""
        try:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='gacha_records'"
            ).fetchone()
            table_sql = row[0] if row else ""
            if "UNIQUE(account_id, item_id)" in table_sql:
                return False

            conn.execute("""
                CREATE TABLE IF NOT EXISTS gacha_records_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    account_id INTEGER NOT NULL,
                    game TEXT NOT NULL,
                    pool_type TEXT NOT NULL,
                    pool_name TEXT DEFAULT '',
                    item_id TEXT DEFAULT '',
                    item_name TEXT NOT NULL,
                    item_type TEXT DEFAULT '',
                    rarity INTEGER NOT NULL,
                    is_featured INTEGER DEFAULT 0,
                    count INTEGER DEFAULT 1,
                    time TEXT NOT NULL,
                    pity_count INTEGER DEFAULT 0,
                    gacha_id TEXT DEFAULT '',
                    pull_index INTEGER DEFAULT 0,
                    raw_data TEXT DEFAULT '',
                    created_at TEXT DEFAULT (datetime('now','localtime')),
                    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
                    UNIQUE(account_id, item_id)
                )
            """)
            conn.execute("""
                INSERT OR IGNORE INTO gacha_records_new
                SELECT * FROM gacha_records
            """)
            before = conn.execute("SELECT COUNT(*) FROM gacha_records").fetchone()[0]
            after = conn.execute("SELECT COUNT(*) FROM gacha_records_new").fetchone()[0]
            logger.info("migration dedupe check: before=%d after=%d", before, after)
            conn.execute("DROP TABLE gacha_records")
            conn.execute("ALTER TABLE gacha_records_new RENAME TO gacha_records")
            conn.commit()
            self._rebuild_pity_counts(conn)
            return True
        except Exception as e:
            logger.warning("migration failed, keeping existing schema: %s", e)
            try:
                conn.rollback()
            except Exception:
                pass
            try:
                conn.execute("DROP TABLE IF EXISTS gacha_records_new")
                conn.commit()
            except Exception:
                pass
            return False

    # ---- 账号 ----

    def add_account(self, account: Account) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """INSERT INTO accounts (game, uid, nickname, server)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(game, uid) DO UPDATE SET
                   nickname=excluded.nickname, server=excluded.server,
                   updated_at=datetime('now','localtime')""",
                (account.game, account.uid, account.nickname, account.server),
            )
            conn.commit()
            return cursor.lastrowid

    def get_accounts(self, game: str = None) -> List[Account]:
        with self.connect() as conn:
            if game:
                rows = conn.execute(
                    "SELECT * FROM accounts WHERE game=? AND is_active=1 ORDER BY updated_at DESC",
                    (game,),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM accounts WHERE is_active=1 ORDER BY game, updated_at DESC"
                ).fetchall()
            return [self._row_to_account(r) for r in rows]

    def get_account_by_id(self, account_id: int) -> Optional[Account]:
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
            return self._row_to_account(row) if row else None

    def update_account(self, account: Account):
        with self.connect() as conn:
            conn.execute(
                """UPDATE accounts SET uid=?, nickname=?, server=?,
                   updated_at=datetime('now','localtime') WHERE id=?""",
                (account.uid, account.nickname, account.server, account.id),
            )
            conn.commit()

    def delete_account(self, account_id: int):
        with self.connect() as conn:
            conn.execute("DELETE FROM gacha_records WHERE account_id=?", (account_id,))
            conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
            conn.commit()
        self.bump_data_version()

    # ---- 抽卡记录 ----

    def add_records(self, records: List[GachaRecord]) -> int:
        count = 0
        with self.connect() as conn:
            for record in records:
                try:
                    conn.execute(
                        """INSERT INTO gacha_records
                           (account_id, game, pool_type, pool_name, item_id, item_name, item_type,
                            rarity, is_featured, count, time, pity_count, gacha_id,
                            pull_index, raw_data)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (record.account_id, record.game, record.pool_type,
                         record.pool_name, record.item_id, record.item_name, record.item_type,
                         record.rarity, int(record.is_featured), record.count,
                         record.time, record.pity_count, record.gacha_id,
                         record.pull_index, record.raw_data),
                    )
                    count += 1
                except sqlite3.IntegrityError as e:
                    if "unique" in str(e).lower():
                        continue
                    logger.warning(
                        "插入记录失败: %s | name=%s time=%s",
                        e, record.item_name, record.time,
                    )
            conn.commit()
        if count:
            self.bump_data_version()
        return count

    def get_records(self, account_id: int, pool_type: str = None,
                    rarity: int = None, limit: int = None) -> List[GachaRecord]:
        with self.connect() as conn:
            query = "SELECT * FROM gacha_records WHERE account_id=?"
            params = [account_id]
            if pool_type:
                query += " AND pool_type=?"
                params.append(pool_type)
            if rarity:
                query += " AND rarity=?"
                params.append(rarity)
            query += " ORDER BY time DESC, id DESC"
            if limit:
                query += f" LIMIT {int(limit)}"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_record(r) for r in rows]

    def get_records_by_game(self, game: str, pool_type: str = None) -> List[GachaRecord]:
        with self.connect() as conn:
            query = "SELECT * FROM gacha_records WHERE game=?"
            params = [game]
            if pool_type:
                query += " AND pool_type=?"
                params.append(pool_type)
            query += " ORDER BY time ASC, id ASC"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_record(r) for r in rows]

    def get_record_count(self, account_id: int, pool_type: str = None) -> dict:
        with self.connect() as conn:
            query = "SELECT rarity, COUNT(*) as cnt FROM gacha_records WHERE account_id=?"
            params = [account_id]
            if pool_type:
                query += " AND pool_type=?"
                params.append(pool_type)
            query += " GROUP BY rarity"
            rows = conn.execute(query, params).fetchall()
            return {row["rarity"]: row["cnt"] for row in rows}

    def get_latest_time(self, account_id: int, pool_type: str) -> Optional[str]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT MAX(time) as max_time FROM gacha_records WHERE account_id=? AND pool_type=?",
                (account_id, pool_type),
            ).fetchone()
            return row["max_time"] if row else None

    def get_last_5star_pity(self, account_id: int, pool_type: str,
                            game: str = "", pool_name: str = "") -> int:
        from core.models import get_max_rarity
        max_rarity = get_max_rarity(game) if game else 5
        with self._lock:
            conn = self._ensure_conn()

            if not pool_name:
                latest = conn.execute(
                    """SELECT pool_name FROM gacha_records
                       WHERE account_id=? AND pool_type=?
                       ORDER BY time DESC, id DESC LIMIT 1""",
                    (account_id, pool_type),
                ).fetchone()
                if not latest:
                    return 0
                pool_name = latest["pool_name"]

            # 鸣潮接口同秒最新在前，导入后较小 id 反而更新
            wuthering = game == "wutheringwaves"
            order_clause = "time DESC, id ASC" if wuthering else "time DESC, id DESC"
            after_clause = (
                "(time > ? OR (time = ? AND id < ?))"
                if wuthering
                else "(time > ? OR (time = ? AND id > ?))"
            )

            row = conn.execute(
                f"""SELECT time, id FROM gacha_records
                   WHERE account_id=? AND pool_type=? AND pool_name=? AND rarity>=?
                   ORDER BY {order_clause} LIMIT 1""",
                (account_id, pool_type, pool_name, max_rarity),
            ).fetchone()

            if row is None:
                total = conn.execute(
                    "SELECT COUNT(*) as cnt FROM gacha_records "
                    "WHERE account_id=? AND pool_type=? AND pool_name=?",
                    (account_id, pool_type, pool_name),
                ).fetchone()
                return total["cnt"] if total else 0

            count = conn.execute(
                f"""SELECT COUNT(*) as cnt FROM gacha_records
                   WHERE account_id=? AND pool_type=? AND pool_name=? AND {after_clause}""",
                (account_id, pool_type, pool_name, row["time"], row["time"], row["id"]),
            ).fetchone()
            return count["cnt"] if count else 0

    def fix_zzz_bangboo_batches(self, conn=None, account_id: int = None):
        if conn is None:
            conn = self._ensure_conn()
        where_clause = "WHERE game='zzz' AND item_type LIKE '%邦布%' AND pool_type != 'bangboo'"
        params = []
        if account_id:
            where_clause += " AND account_id=?"
            params.append(account_id)
        conn.execute(f"UPDATE gacha_records SET pool_type='bangboo' {where_clause}", params)
        conn.commit()

    def calculate_pity_counts(self, account_id: int):
        self.fix_zzz_bangboo_batches(account_id=account_id)
        from core.models import get_max_rarity
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, game, pool_type, pool_name, rarity FROM gacha_records "
                "WHERE account_id=? ORDER BY pool_type, time ASC, "
                "CASE WHEN game='wutheringwaves' THEN -id ELSE id END ASC",
                (account_id,),
            ).fetchall()
            pity_counts = {}
            for row in rows:
                game = row["game"]
                pool_type = row["pool_type"]
                pool_name = row["pool_name"] if "pool_name" in row.keys() else ""
                group_key = (game, pool_type, pool_name)
                pity_counts.setdefault(group_key, 0)
                pity_counts[group_key] += 1
                if row["rarity"] >= get_max_rarity(game):
                    conn.execute(
                        "UPDATE gacha_records SET pity_count=? WHERE id=?",
                        (pity_counts[group_key], row["id"]),
                    )
                    pity_counts[group_key] = 0
            conn.commit()
        self.bump_data_version()

    def _rebuild_pity_counts(self, conn):
        self.fix_zzz_bangboo_batches(conn=conn)
        from core.models import get_max_rarity
        rows = conn.execute(
            "SELECT id, game, pool_type, pool_name, rarity FROM gacha_records "
            "ORDER BY account_id, pool_type, time ASC, "
            "CASE WHEN game='wutheringwaves' THEN -id ELSE id END ASC"
        ).fetchall()
        pity_counts = {}
        for row in rows:
            game = row["game"]
            pool_type = row["pool_type"]
            pool_name = row["pool_name"] if "pool_name" in row.keys() else ""
            group_key = (game, pool_type, pool_name)
            pity_counts.setdefault(group_key, 0)
            pity_counts[group_key] += 1
            if row["rarity"] >= get_max_rarity(game):
                conn.execute(
                    "UPDATE gacha_records SET pity_count=? WHERE id=?",
                    (pity_counts[group_key], row["id"]),
                )
                pity_counts[group_key] = 0
        conn.commit()

    @staticmethod
    def _determine_is_featured(game: str, pool_type: str, item_name: str,
                               rarity: int, record_time: str) -> bool:
        """第三方导入后重算 UP 标记。联动池映射到角色/武器池再查表。"""
        from core.models import get_max_rarity

        if rarity != get_max_rarity(game):
            return False
        if pool_type in ("standard", "beginner"):
            return False

        if game == "wutheringwaves":
            from fetchers.kuro.wutheringwaves import (
                STANDARD_5STAR_CHARACTERS, STANDARD_5STAR_WEAPONS,
            )
            is_std = (
                item_name in STANDARD_5STAR_CHARACTERS
                or item_name in STANDARD_5STAR_WEAPONS
            )
            return not is_std

        from fetchers.mihoyo.api import MihoyoAPI

        lookup_type = pool_type
        if pool_type == "collab":
            lookup_type = "character"
        elif pool_type == "collab_weapon":
            lookup_type = "weapon"

        standard_items = MihoyoAPI.STANDARD_5STAR.get(game, {}).get(lookup_type, [])
        loseable_info = MihoyoAPI.LOSEABLE_5STAR_WITH_DATE.get((game, lookup_type), {})

        if item_name in loseable_info:
            loseable_date = loseable_info[item_name]
            return not (record_time and record_time >= loseable_date)
        if item_name not in standard_items:
            return True
        return False

    def recalculate_is_featured(self, account_id: int):
        from core.models import get_max_rarity
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT id, game, pool_type, item_name, rarity, time "
                "FROM gacha_records WHERE account_id=? ORDER BY time ASC, id ASC",
                (account_id,),
            ).fetchall()
            for row in rows:
                if row["rarity"] != get_max_rarity(row["game"]):
                    continue
                new_featured = self._determine_is_featured(
                    game=row["game"],
                    pool_type=row["pool_type"],
                    item_name=row["item_name"],
                    rarity=row["rarity"],
                    record_time=row["time"] if "time" in row.keys() else "",
                )
                conn.execute(
                    "UPDATE gacha_records SET is_featured=? WHERE id=?",
                    (int(new_featured), row["id"]),
                )
            conn.commit()

    def get_total_records(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM gacha_records").fetchone()
            return row["cnt"]

    # ---- 备份 ----

    def backup(self) -> str:
        """sqlite backup API，WAL 下也能拿到完整库。"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = Path(self.config.backup_dir) / f"gacha_backup_{timestamp}.db"
        src = self._ensure_conn()
        dest = sqlite3.connect(str(backup_path))
        try:
            src.backup(dest)
        finally:
            dest.close()
        self._cleanup_old_backups()
        return str(backup_path)

    def restore(self, backup_path: str):
        if not Path(backup_path).exists():
            raise FileNotFoundError(f"备份文件不存在: {backup_path}")
        self.close()
        shutil.copy2(backup_path, self.db_path)
        for suffix in ("-wal", "-shm"):
            stale = Path(self.db_path + suffix)
            if stale.exists():
                try:
                    stale.unlink()
                except OSError:
                    logger.warning("清理残留文件失败: %s", stale)
        self._initialized = False
        self.__init__()

    def _cleanup_old_backups(self):
        max_backups = self.config.get_int("max_backups", 10)
        backup_dir = Path(self.config.backup_dir)
        backups = sorted(backup_dir.glob("gacha_backup_*.db"), reverse=True)
        for old in backups[max_backups:]:
            old.unlink()

    # ---- 导入导出 ----

    def export_json(self, account_id: int = None) -> str:
        if account_id:
            records = self.get_records(account_id)
        else:
            with self.connect() as conn:
                rows = conn.execute("SELECT * FROM gacha_records ORDER BY time ASC").fetchall()
                records = [self._row_to_record(r) for r in rows]

        data = [{
            "game": r.game,
            "pool_type": r.pool_type,
            "pool_name": r.pool_name,
            "item_id": r.item_id,
            "item_name": r.item_name,
            "item_type": r.item_type,
            "rarity": r.rarity,
            "is_featured": r.is_featured,
            "time": r.time,
            "pity_count": r.pity_count,
        } for r in records]
        return json.dumps(data, ensure_ascii=False, indent=2)

    def import_json(self, json_str: str, account_id: int) -> int:
        data = json.loads(json_str)
        if isinstance(data, dict):
            data = data.get("list", data.get("records", []))
        records = []
        for idx, item in enumerate(data):
            g = item.get("game", "")
            pt = item.get("pool_type", "")
            t = item.get("time", "")
            name = item.get("item_name", "")
            records.append(GachaRecord(
                account_id=account_id,
                game=g,
                pool_type=pt,
                pool_name=item.get("pool_name", ""),
                item_id=item.get("item_id") or item.get("id")
                          or make_item_id(g, pt, t, name, idx),
                item_name=name,
                item_type=item.get("item_type", ""),
                rarity=item.get("rarity", 5),
                is_featured=bool(item.get("is_featured", False)),
                time=t,
                pity_count=item.get("pity_count", 0),
            ))
        count = self.add_records(records)
        if count > 0:
            self.recalculate_is_featured(account_id)
            self.calculate_pity_counts(account_id)
            self.bump_data_version()
        return count

    def _row_to_account(self, row) -> Account:
        return Account(
            id=row["id"],
            game=row["game"],
            uid=row["uid"],
            nickname=row["nickname"],
            server=row["server"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def _row_to_record(self, row) -> GachaRecord:
        return GachaRecord(
            id=row["id"],
            account_id=row["account_id"],
            game=row["game"],
            pool_type=row["pool_type"],
            pool_name=row["pool_name"] if "pool_name" in row.keys() else "",
            item_id=row["item_id"],
            item_name=row["item_name"],
            item_type=row["item_type"],
            rarity=row["rarity"],
            is_featured=bool(row["is_featured"]),
            count=row["count"],
            time=row["time"],
            pity_count=row["pity_count"],
            gacha_id=row["gacha_id"],
            pull_index=row["pull_index"],
            raw_data=row["raw_data"],
            created_at=row["created_at"],
        )

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
