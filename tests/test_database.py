"""database 核心逻辑测试（使用内存数据库）"""

import sys
import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.models import Account, GachaRecord


class TestDatabaseBasic(unittest.TestCase):
    """使用临时数据库文件测试"""

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.tmpdir, "test.db")
        # 直接用 sqlite3 测试核心 SQL，绕过 Config 单例
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.executescript("""
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
        """)
        self.conn.commit()

    def tearDown(self):
        self.conn.close()

    def test_insert_and_query_account(self):
        self.conn.execute(
            "INSERT INTO accounts (game, uid, nickname) VALUES (?, ?, ?)",
            ("genshin", "123456789", "测试号")
        )
        self.conn.commit()
        row = self.conn.execute("SELECT * FROM accounts WHERE uid=?", ("123456789",)).fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["game"], "genshin")
        self.assertEqual(row["nickname"], "测试号")

    def test_unique_account_constraint(self):
        self.conn.execute(
            "INSERT INTO accounts (game, uid, nickname) VALUES (?, ?, ?)",
            ("genshin", "123", "A")
        )
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO accounts (game, uid, nickname) VALUES (?, ?, ?)",
                ("genshin", "123", "B")
            )

    def test_insert_and_query_record(self):
        self.conn.execute(
            "INSERT INTO accounts (game, uid) VALUES (?, ?)", ("genshin", "1")
        )
        self.conn.commit()
        account_id = self.conn.execute("SELECT id FROM accounts").fetchone()["id"]

        self.conn.execute(
            """INSERT INTO gacha_records
               (account_id, game, pool_type, item_id, item_name, rarity, time)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (account_id, "genshin", "character", "item_1", "甘雨", 5, "2025-01-01 12:00:00")
        )
        self.conn.commit()

        rows = self.conn.execute(
            "SELECT * FROM gacha_records WHERE account_id=?", (account_id,)
        ).fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["item_name"], "甘雨")
        self.assertEqual(rows[0]["rarity"], 5)

    def test_cascade_delete(self):
        self.conn.execute("INSERT INTO accounts (game, uid) VALUES (?, ?)", ("genshin", "1"))
        self.conn.commit()
        aid = self.conn.execute("SELECT id FROM accounts").fetchone()["id"]
        self.conn.execute(
            "INSERT INTO gacha_records (account_id, game, pool_type, item_id, item_name, rarity, time) VALUES (?,?,?,?,?,?,?)",
            (aid, "genshin", "character", "i1", "A", 3, "2025-01-01")
        )
        self.conn.commit()
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("DELETE FROM accounts WHERE id=?", (aid,))
        self.conn.commit()
        rows = self.conn.execute("SELECT * FROM gacha_records").fetchall()
        self.assertEqual(len(rows), 0)

    def test_unique_record_constraint(self):
        self.conn.execute("INSERT INTO accounts (game, uid) VALUES (?, ?)", ("genshin", "1"))
        self.conn.commit()
        aid = self.conn.execute("SELECT id FROM accounts").fetchone()["id"]
        self.conn.execute(
            "INSERT INTO gacha_records (account_id, game, pool_type, item_id, item_name, rarity, time) VALUES (?,?,?,?,?,?,?)",
            (aid, "genshin", "character", "item_1", "A", 5, "2025-01-01")
        )
        self.conn.commit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO gacha_records (account_id, game, pool_type, item_id, item_name, rarity, time) VALUES (?,?,?,?,?,?,?)",
                (aid, "genshin", "character", "item_1", "B", 3, "2025-01-02")
            )


if __name__ == "__main__":
    unittest.main()
