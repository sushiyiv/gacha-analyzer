"""SQLite 数据库操作模块（稳定性与可维护性优化版）"""

import logging
import sqlite3
import json
import shutil
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import List, Optional
from core.models import Account, GachaRecord
from core.config import Config


logger = logging.getLogger(__name__)


class Database:
    """SQLite 数据库管理"""

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if not hasattr(self, '_initialized'):
            self.config = Config()
            self.db_path = self.config.db_path
            self._conn = None
            self._initialized = True
            self._init_db()

    def _ensure_conn(self):
        if self._conn is None:
            self._conn = sqlite3.connect(self.db_path)
            self._conn.row_factory = sqlite3.Row
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
        return self._conn

    @contextmanager
    def connect(self):
        conn = self._ensure_conn()
        try:
            yield conn
        finally:
            pass

    def _init_db(self):
        with self.connect() as conn:
            conn.executescript("""
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

                CREATE INDEX IF NOT EXISTS idx_records_account ON gacha_records(account_id);
                CREATE INDEX IF NOT EXISTS idx_records_game ON gacha_records(game);
                CREATE INDEX IF NOT EXISTS idx_records_pool ON gacha_records(pool_type);
                CREATE INDEX IF NOT EXISTS idx_records_rarity ON gacha_records(rarity);
                CREATE INDEX IF NOT EXISTS idx_records_time ON gacha_records(time);
            """)
            conn.commit()

            try:
                conn.execute("SELECT pool_name FROM gacha_records LIMIT 1")
            except sqlite3.OperationalError:
                conn.execute("ALTER TABLE gacha_records ADD COLUMN pool_name TEXT DEFAULT ''")
                conn.commit()

            self._migrate_unique_constraint(conn)

    def _migrate_unique_constraint(self, conn):
        try:
            cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='gacha_records'")
            row = cursor.fetchone()
            table_sql = row[0] if row else ""
            if "UNIQUE(account_id, item_id)" in table_sql:
                return

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

            before_count = conn.execute("SELECT COUNT(*) FROM gacha_records").fetchone()[0]
            after_count = conn.execute("SELECT COUNT(*) FROM gacha_records_new").fetchone()[0]
            logger.info("migration dedupe check: before=%d after=%d", before_count, after_count)

            conn.execute("DROP TABLE gacha_records")
            conn.execute("ALTER TABLE gacha_records_new RENAME TO gacha_records")
            conn.commit()

            self._rebuild_pity_counts(conn)
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

    def add_account(self, account: Account) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """INSERT INTO accounts (game, uid, nickname, server)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(game, uid) DO UPDATE SET
                   nickname=excluded.nickname, server=excluded.server,
                   updated_at=datetime('now','localtime')""",
                (account.game, account.uid, account.nickname, account.server)
            )
            conn.commit()
            return cursor.lastrowid

    def get_accounts(self, game: str = None) -> List[Account]:
        with self.connect() as conn:
            if game:
                rows = conn.execute(
                    "SELECT * FROM accounts WHERE game=? AND is_active=1 ORDER BY updated_at DESC",
                    (game,)
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
                """UPDATE accounts SET uid=?, nickname=?, server=?, updated_at=datetime('now','localtime')
                   WHERE id=?""",
                (account.uid, account.nickname, account.server, account.id)
            )
            conn.commit()

    def delete_account(self, account_id: int):
        with self.connect() as conn:
            conn.execute("DELETE FROM gacha_records WHERE account_id=?", (account_id,))
            conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
            conn.commit()

    def add_records(self, records: List[GachaRecord]) -> int:
        with self.connect() as conn:
            count = 0
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
                         record.pull_index, record.raw_data)
                    )
                    count += 1
                except sqlite3.IntegrityError:
                    pass
            conn.commit()
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
                query += f" LIMIT {limit}"
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
                (account_id, pool_type)
            ).fetchone()
            return row["max_time"] if row else None

    def _rebuild_pity_counts(self, conn):
        from core.models import get_max_rarity
        rows = conn.execute(
            "SELECT id, game, pool_type, pool_name, rarity FROM gacha_records ORDER BY account_id, pool_type, time ASC, id ASC"
        ).fetchall()

        pity_counts = {}
        for row in rows:
            record_id = row["id"]
            game = row["game"]
            pool_type = row["pool_type"]
            pool_name = row["pool_name"] if "pool_name" in row.keys() else ""
            rarity = row["rarity"]
            max_rarity = get_max_rarity(game)

            group_key = (pool_type, pool_name) if pool_name else (pool_type, "")
            if group_key not in pity_counts:
                pity_counts[group_key] = 0

            pity_counts[group_key] += 1

            if rarity == max_rarity:
                conn.execute(
                    "UPDATE gacha_records SET pity_count=? WHERE id=?",
                    (pity_counts[group_key], record_id)
                )
                pity_counts[group_key] = 0

        conn.commit()

    def get_total_records(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) as cnt FROM gacha_records").fetchone()
            return row["cnt"]

    def backup(self) -> str:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = Path(self.config.backup_dir) / f"gacha_backup_{timestamp}.db"
        shutil.copy2(self.db_path, backup_path)
        self._cleanup_old_backups()
        return str(backup_path)

    def restore(self, backup_path: str):
        if not Path(backup_path).exists():
            raise FileNotFoundError(f"备份文件不存在: {backup_path}")
        self.close()
        shutil.copy2(backup_path, self.db_path)
        self._initialized = False
        self.__init__()

    def _cleanup_old_backups(self):
        max_backups = self.config.get_int("max_backups", 10)
        backup_dir = Path(self.config.backup_dir)
        backups = sorted(backup_dir.glob("gacha_backup_*.db"), reverse=True)
        for old in backups[max_backups:]:
            old.unlink()

    def export_json(self, account_id: int = None) -> str:
        if account_id:
            records = self.get_records(account_id)
        else:
            with self.connect() as conn:
                rows = conn.execute("SELECT * FROM gacha_records ORDER BY time ASC").fetchall()
                records = [self._row_to_record(r) for r in rows]

        data = []
        for r in records:
            data.append({
                "game": r.game, "pool_type": r.pool_type, "pool_name": r.pool_name,
                "item_name": r.item_name, "item_type": r.item_type,
                "rarity": r.rarity, "is_featured": r.is_featured,
                "time": r.time, "pity_count": r.pity_count,
            })
        return json.dumps(data, ensure_ascii=False, indent=2)

    def import_json(self, json_str: str, account_id: int) -> int:
        data = json.loads(json_str)
        if isinstance(data, dict):
            data = data.get("list", data.get("records", []))
        records = []
        for item in data:
            records.append(GachaRecord(
                account_id=account_id,
                game=item.get("game", ""),
                pool_type=item.get("pool_type", ""),
                pool_name=item.get("pool_name", ""),
                item_name=item.get("item_name", ""),
                item_type=item.get("item_type", ""),
                rarity=item.get("rarity", 5),
                is_featured=bool(item.get("is_featured", False)),
                time=item.get("time", ""),
                pity_count=item.get("pity_count", 0),
            ))
        return self.add_records(records)

    def _row_to_account(self, row) -> Account:
        return Account(
            id=row["id"], game=row["game"], uid=row["uid"],
            nickname=row["nickname"], server=row["server"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )

    def _row_to_record(self, row) -> GachaRecord:
        return GachaRecord(
            id=row["id"], account_id=row["account_id"], game=row["game"],
            pool_type=row["pool_type"],
            pool_name=row["pool_name"] if "pool_name" in row.keys() else "",
            item_id=row["item_id"],
            item_name=row["item_name"], item_type=row["item_type"],
            rarity=row["rarity"], is_featured=bool(row["is_featured"]),
            count=row["count"], time=row["time"],
            pity_count=row["pity_count"], gacha_id=row["gacha_id"],
            pull_index=row["pull_index"], raw_data=row["raw_data"],
            created_at=row["created_at"],
        )

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None
