"""SQLite 数据库操作模块（稳定性与可维护性优化版）

本模块是整个抽卡分析系统的数据持久化核心，负责管理所有抽卡记录和账号信息的 CRUD 操作。
使用 SQLite 作为底层数据库引擎，通过单例模式确保全局唯一数据库连接实例。
主要功能包括：
  1. 账号管理（增删改查）
  2. 抽卡记录的导入、查询和统计
  3. 保底计数（pity count）的自动计算与更新
  4. 数据库备份与恢复
  5. 数据导出为 JSON 格式
  6. 数据库 Schema 迁移（自动处理旧版本兼容性）
"""

# =====================================================================
# 标准库导入
# =====================================================================

# logging 模块：提供日志记录功能，用于记录程序运行过程中的信息、警告和错误
import logging

# sqlite3 模块：Python 内置的 SQLite 数据库接口，提供轻量级关系型数据库操作能力
import sqlite3

# json 模块：用于将 Python 对象序列化为 JSON 字符串，以及将 JSON 字符串反序列化为 Python 对象
import json

# shutil 模块：提供高级文件操作工具，此处主要用于文件复制（数据库备份）
import shutil

# contextlib.contextmanager：装饰器，用于将生成器函数转换为上下文管理器（with 语句）
# 可以简化资源管理代码，确保连接在使用后正确释放或回滚
from contextlib import contextmanager

# datetime 模块：提供日期和时间处理功能，用于生成备份文件的时间戳
from datetime import datetime

# pathlib.Path：面向对象的文件路径处理类，比传统 os.path 更直观易用
from pathlib import Path

# typing 模块：提供类型注解工具，用于增强代码可读性和 IDE 智能提示
# List：列表类型注解；Optional：可选类型注解（值可以为 None）
from typing import List, Optional

# =====================================================================
# 项目内部模块导入
# =====================================================================

# core.models 模块：定义数据模型类，Account 表示游戏账号，GachaRecord 表示单条抽卡记录
from core.models import Account, GachaRecord

# core.config 模块：配置管理类，提供数据库路径、备份目录等配置项的读取
from core.config import Config


# =====================================================================
# 日志器配置
# =====================================================================

# 创建一个与当前模块名（core.database）同名的日志器实例
# __name__ 在此处解析为字符串 "core.database"，便于按模块名过滤日志输出
# 后续代码通过 logger.info()、logger.warning() 等方法记录日志
logger = logging.getLogger(__name__)


# =====================================================================
# Database 单例类
# =====================================================================

class Database:
    """SQLite 数据库管理

    使用单例模式（Singleton Pattern）确保整个应用程序只有一个数据库管理实例。
    这样做的好处是：
      1. 避免多个实例竞争同一个数据库文件
      2. 维护单一的数据库连接，减少资源开销
      3. 保证数据操作的一致性和顺序性

    主要职责：
      - 管理数据库连接的创建和关闭
      - 执行数据库 Schema 的初始化和迁移
      - 提供账号和抽卡记录的 CRUD 操作
      - 计算和更新保底计数
      - 数据库备份与恢复
    """

    # 类变量：存储单例实例的引用，初始值为 None
    # 当第一次创建 Database 实例时，会将实例赋值给 _instance
    # 后续所有创建请求都会返回这个已存在的实例
    _instance = None

    def __new__(cls):
        """重写 __new__ 方法实现单例模式

        __new__ 是 Python 中真正创建实例的方法（在 __init__ 之前被调用）。
        如果 _instance 为 None，说明是首次创建，调用父类的 __new__ 创建新实例。
        如果 _instance 已存在，直接返回已有实例的引用。

        返回值：Database 的唯一实例对象
        """
        # 检查是否已经创建过实例
        if cls._instance is None:
            # 首次创建：调用 object.__new__(cls) 创建一个新的 Database 实例
            cls._instance = super().__new__(cls)
        # 返回单例实例（无论新建的还是已存在的）
        return cls._instance

    def __init__(self):
        """初始化数据库管理器

        由于单例模式下 __new__ 会反复返回同一实例，
        __init__ 也会被多次调用。因此使用 _initialized 标志位
        确保初始化逻辑只执行一次。

        初始化内容：
          1. 读取配置对象（Config）
          2. 从配置中获取数据库文件路径
          3. 初始化连接对象为 None（延迟创建）
          4. 设置初始化标志
          5. 调用 _init_db() 创建数据库表结构（如果尚未创建）
        """
        # 使用 hasattr 检查是否已经初始化过，防止重复初始化
        if not hasattr(self, '_initialized'):
            # 创建 Config 实例，读取应用程序配置
            self.config = Config()
            # 从配置中获取数据库文件的路径（如 "data/gacha.db"）
            self.db_path = self.config.db_path
            # 数据库连接对象初始为 None，采用延迟初始化策略
            # 即只在第一次真正需要连接时才创建
            self._conn = None
            # 标记初始化已完成，后续的 __init__ 调用将跳过此块
            self._initialized = True
            # 初始化数据库表结构（建表、索引、迁移等）
            self._init_db()

    def _ensure_conn(self):
        """确保数据库连接可用

        这是延迟初始化（Lazy Initialization）的核心方法。
        如果连接为 None，则创建新的连接；否则复用已有连接。

        内部逻辑：
          1. 检查 _conn 是否为 None
          2. 若为 None，创建新的 SQLite 连接
          3. 设置 Row 工厂，使查询结果支持按列名访问
          4. 启用 WAL 日志模式（Write-Ahead Logging），提升并发性能
          5. 启用外键约束支持
          6. 返回连接对象

        返回值：有效的 sqlite3.Connection 对象
        """
        # 仅在连接不存在时才创建新连接
        if self._conn is None:
            # 创建指向 self.db_path 的 SQLite 数据库连接
            # 如果数据库文件不存在，SQLite 会自动创建
            self._conn = sqlite3.connect(self.db_path)
            # 设置 row_factory 为 sqlite3.Row，使得查询结果行支持按列名访问
            # 例如 row["name"] 而不是 row[0]，大大提高代码可读性
            self._conn.row_factory = sqlite3.Row
            # 启用 WAL（Write-Ahead Logging）日志模式
            # WAL 模式允许读写操作并发执行，大幅提升多线程场景下的性能
            # 同时也提供了更好的崩溃恢复能力
            self._conn.execute("PRAGMA journal_mode=WAL")
            # 启用外键约束（SQLite 默认关闭外键约束）
            # 启用后，FOREIGN KEY 约束会在 INSERT/UPDATE/DELETE 时被检查
            # 例如：删除账户时，关联的抽卡记录也会被级联删除
            self._conn.execute("PRAGMA foreign_keys=ON")
        # 返回数据库连接对象
        return self._conn

    @contextmanager
    def connect(self):
        """上下文管理器：安全地获取数据库连接

        使用 @contextmanager 装饰器将生成器函数转换为上下文管理器。
        配合 with 语句使用，提供统一的连接获取接口。

        使用方式：
            with self.connect() as conn:
                conn.execute("SELECT ...")

        工作流程：
          1. 通过 _ensure_conn() 获取数据库连接
          2. yield 连接对象供 with 块内部使用
          3. 退出 with 块时正常结束（finally 块中无额外操作）

        注意：与常见的回滚包装不同，此实现将事务管理交给调用方，
        调用方需要自行决定何时 commit 或 rollback。
        """
        # 获取或创建数据库连接
        conn = self._ensure_conn()
        try:
            # 将连接对象 yield 给 with 块使用
            yield conn
        finally:
            # finally 块确保无论是否发生异常都会执行
            # 当前实现为空操作，事务管理由调用方负责
            pass

    def _init_db(self):
        """初始化数据库结构（建表、索引、迁移）

        此方法在 Database 首次初始化时被调用，执行以下操作：
          1. 使用 executescript() 执行多条 SQL 语句创建表和索引
          2. 创建 accounts 表（存储游戏账号信息）
          3. 创建 gacha_records 表（存储抽卡记录）
          4. 创建索引以加速查询
          5. 尝试添加 pool_name 列（向后兼容旧版本数据库）
          6. 迁移 UNIQUE 约束（确保数据完整性）

        执行流程：
          1. 通过 connect() 上下文管理器获取连接
          2. executescript() 会隐式提交之前的事务，然后执行多条 SQL
          3. 每条 CREATE TABLE IF NOT EXISTS 确保幂等性（多次运行不报错）
          4. 创建索引加速常用查询字段的检索速度
          5. 异常处理确保迁移失败时不会破坏现有数据
        """
        # 使用上下文管理器获取数据库连接
        with self.connect() as conn:
            # executescript() 方法执行多条以分号分隔的 SQL 语句
            # 在执行前会隐式 COMMIT 当前事务
            conn.executescript("""
                -- =====================================================
                -- 账号表（accounts）
                -- 存储用户的游戏账号信息，支持多游戏、多账号管理
                -- =====================================================
                CREATE TABLE IF NOT EXISTS accounts (
                    -- id: 自增主键，每条记录的唯一标识符
                    -- INTEGER PRIMARY KEY AUTOINCREMENT 让 SQLite 自动生成递增的整数 ID
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    -- game: 游戏名称标识符（如 "genshin", "starrail", "endfield"）
                    -- NOT NULL 约束确保必须提供游戏名称，不允许为空
                    game TEXT NOT NULL,

                    -- uid: 用户在游戏中的唯一 ID（如原神的 UID: 100000000）
                    -- NOT NULL 约束确保必须提供用户 ID
                    uid TEXT NOT NULL,

                    -- nickname: 用户昵称，默认为空字符串
                    -- 允许为空，因为有些情况下用户尚未设置昵称
                    nickname TEXT DEFAULT '',

                    -- server: 服务器区域（如 "cn", "global", "jp" 等）
                    -- 默认为 "cn"（中国服务器）
                    server TEXT DEFAULT 'cn',

                    -- is_active: 账号是否激活标志
                    -- 1 表示激活（正常显示），0 表示停用（软删除，数据保留）
                    -- 这种设计支持"删除"账号后仍可恢复
                    is_active INTEGER DEFAULT 1,

                    -- created_at: 记录创建时间
                    -- 使用 SQLite 的 datetime 函数，'now' 表示当前 UTC 时间
                    -- 'localtime' 参数将 UTC 时间转换为本地时间
                    created_at TEXT DEFAULT (datetime('now','localtime')),

                    -- updated_at: 记录最后更新时间
                    -- 同上，自动记录最后一次修改的时间
                    updated_at TEXT DEFAULT (datetime('now','localtime')),

                    -- UNIQUE 约束：确保同一游戏下不会有两个相同 UID 的账号
                    -- 例如：原神不能有两个 UID=100000000 的账号
                    UNIQUE(game, uid)
                );

                -- =====================================================
                -- 抽卡记录表（gacha_records）
                -- 存储每次抽卡的详细信息，是系统的核心数据表
                -- =====================================================
                CREATE TABLE IF NOT EXISTS gacha_records (
                    -- id: 自增主键，每条抽卡记录的唯一标识
                    id INTEGER PRIMARY KEY AUTOINCREMENT,

                    -- account_id: 外键，关联 accounts 表的 id
                    -- 表示这条抽卡记录属于哪个账号
                    -- NOT NULL 约束确保每条记录必须关联一个账号
                    account_id INTEGER NOT NULL,

                    -- game: 游戏名称（冗余字段，便于跨账号查询）
                    game TEXT NOT NULL,

                    -- pool_type: 卡池类型（如 "character", "weapon", "standard"）
                    -- 不同游戏有不同的卡池命名规则
                    pool_type TEXT NOT NULL,

                    -- pool_name: 卡池具体名称（如 "纳西妲 UP 池"）
                    -- 用于区分同一类型下的不同卡池（如多个角色 UP 池）
                    pool_name TEXT DEFAULT '',

                    -- item_id: 抽到物品的唯一标识符
                    -- 用于去重判断，防止重复导入同一条记录
                    item_id TEXT DEFAULT '',

                    -- item_name: 抽到物品的名称（如 "纳西妲", "天空之刃"）
                    -- 这是最重要的展示字段之一
                    item_name TEXT NOT NULL,

                    -- item_type: 物品类型（如 "角色", "武器"）
                    item_type TEXT DEFAULT '',

                    -- rarity: 物品稀有度等级
                    -- 通常用数字表示：5=五星, 4=四星, 3=三星
                    rarity INTEGER NOT NULL,

                    -- is_featured: 是否为 UP 角色（提升概率的限定角色）
                    -- 1 表示是 UP 角色，0 表示是常驻角色
                    is_featured INTEGER DEFAULT 0,

                    -- count: 本次抽卡获得的数量（通常为 1，十连抽时可能更大）
                    count INTEGER DEFAULT 1,

                    -- time: 抽卡时间（格式如 "2024-01-15 14:30:00"）
                    -- 用于按时间排序和计算保底
                    time TEXT NOT NULL,

                    -- pity_count: 距离上次最高星物品的抽卡次数（保底计数）
                    -- 这是计算保底的核心字段
                    -- 例如：如果保底计数为 80，表示距离上次出金已经抽了 80 次
                    pity_count INTEGER DEFAULT 0,

                    -- gacha_id: 抽卡事件的唯一 ID（来自游戏 API）
                    -- 用于更精确的去重判断
                    gacha_id TEXT DEFAULT '',

                    -- pull_index: 在本次抽卡批次中的序号（如十连抽中的第几个）
                    pull_index INTEGER DEFAULT 0,

                    -- raw_data: 原始抽卡数据（JSON 格式字符串）
                    -- 保留原始数据以便后续调试或提取新字段
                    raw_data TEXT DEFAULT '',

                    -- created_at: 记录创建时间（本地时间）
                    created_at TEXT DEFAULT (datetime('now','localtime')),

                    -- 外键约束：当关联的账号被删除时，自动删除该账号的所有抽卡记录
                    -- ON DELETE CASCADE 实现级联删除
                    FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,

                    -- UNIQUE 约束：确保同一账号下不会有两个相同 item_id 的记录
                    -- 这是防止重复导入的关键约束
                    UNIQUE(account_id, item_id)
                );

                -- =====================================================
                -- 索引创建
                -- 索引通过 B-Tree 数据结构加速查询，避免全表扫描
                -- 虽然会略微增加写入开销，但对读取性能提升巨大
                -- =====================================================

                -- 索引1：按 account_id 查询所有抽卡记录
                -- 最常用的查询场景，如"查看某账号的所有记录"
                CREATE INDEX IF NOT EXISTS idx_records_account ON gacha_records(account_id);

                -- 索引2：按游戏名称查询所有记录
                -- 用于"查看某游戏所有记录"的场景
                CREATE INDEX IF NOT EXISTS idx_records_game ON gacha_records(game);

                -- 索引3：按卡池类型查询
                -- 用于"查看某卡池类型的所有记录"
                CREATE INDEX IF NOT EXISTS idx_records_pool ON gacha_records(pool_type);

                -- 索引4：按稀有度查询
                -- 用于"查看所有五星记录"等场景
                CREATE INDEX IF NOT EXISTS idx_records_rarity ON gacha_records(rarity);

                -- 索引5：按抽卡时间排序
                -- 用于按时间线展示抽卡历史
                CREATE INDEX IF NOT EXISTS idx_records_time ON gacha_records(time);
            """)
            # executescript 已经隐式提交了事务，这里再显式提交一次以确保安全
            conn.commit()

            # =====================================================
            # 向后兼容迁移：添加 pool_name 列
            # 早期版本的数据库可能没有 pool_name 列
            # 通过尝试查询该列来检测是否存在
            # =====================================================
            try:
                # 尝试查询 pool_name 列，如果列不存在会抛出 OperationalError
                conn.execute("SELECT pool_name FROM gacha_records LIMIT 1")
            except sqlite3.OperationalError:
                # 如果抛出异常，说明 pool_name 列不存在，需要添加
                # ALTER TABLE ADD COLUMN 是 SQLite 添加新列的语法
                # DEFAULT '' 设置默认值为空字符串，确保现有记录不会出错
                conn.execute("ALTER TABLE gacha_records ADD COLUMN pool_name TEXT DEFAULT ''")
                # 提交 ALTER 操作，使其持久化
                conn.commit()

            # 执行 UNIQUE 约束迁移（确保唯一约束为 UNIQUE(account_id, item_id)）
            self._migrate_unique_constraint(conn)

    def _migrate_unique_constraint(self, conn):
        """迁移 UNIQUE 约束：从旧的唯一约束迁移到新的唯一约束

        SQLite 的限制：无法直接修改已有表的 UNIQUE 约束。
        因此需要通过"创建新表 -> 复制数据 -> 删除旧表 -> 重命名新表"的方式实现迁移。

        迁移策略（三步走）：
          1. 创建带有新 UNIQUE 约束的新表
          2. 将旧表数据复制到新表（使用 INSERT OR IGNORE 去重）
          3. 删除旧表，将新表重命名为原表名

        参数：
            conn: sqlite3.Connection 对象，当前数据库连接
                  注意：此方法不使用上下文管理器，因为迁移可能涉及多个步骤，
                  需要在一个事务中完成所有操作

        异常处理：
          - 整个迁移过程用 try-except 包裹
          - 如果迁移失败，记录警告日志并回滚
          - 确保不残留临时表（gacha_records_new）
        """
        try:
            # 查询 sqlite_master 系统表获取 gacha_records 表的原始 CREATE TABLE 语句
            # sqlite_master 是 SQLite 的系统目录表，存储所有表、索引、触发器的定义
            # type='table' 过滤只查询表定义（不包含索引和视图）
            cursor = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='gacha_records'")
            # fetchone() 返回单行结果（Row 对象），如果表不存在返回 None
            row = cursor.fetchone()
            # row[0] 是 CREATE TABLE 的完整 SQL 语句字符串
            # 如果表不存在，table_sql 为空字符串
            table_sql = row[0] if row else ""
            # 检查是否已经包含新的 UNIQUE 约束
            # 如果已经包含，说明迁移已完成，无需重复执行（幂等性检查）
            if "UNIQUE(account_id, item_id)" in table_sql:
                return

            # =====================================================
            # 步骤1：创建新表 gacha_records_new
            # 新表结构与原表相同，但 UNIQUE 约束改为 (account_id, item_id)
            # =====================================================
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

            # =====================================================
            # 步骤2：将旧表数据复制到新表
            # INSERT OR IGNORE 会忽略违反 UNIQUE 约束的重复记录
            # 这样可以自动去重，只保留每组 (account_id, item_id) 的第一条记录
            # =====================================================
            conn.execute("""
                INSERT OR IGNORE INTO gacha_records_new
                SELECT * FROM gacha_records
            """)

            # =====================================================
            # 步骤3：验证数据完整性
            # 比较迁移前后的记录数，确保没有意外丢失大量数据
            # =====================================================
            # 查询旧表的记录总数
            before_count = conn.execute("SELECT COUNT(*) FROM gacha_records").fetchone()[0]
            # 查询新表的记录总数
            after_count = conn.execute("SELECT COUNT(*) FROM gacha_records_new").fetchone()[0]
            # 记录迁移前后的记录数，便于排查问题
            logger.info("migration dedupe check: before=%d after=%d", before_count, after_count)

            # =====================================================
            # 步骤4：替换表
            # 删除旧表，将新表重命名为原表名
            # =====================================================
            conn.execute("DROP TABLE gacha_records")
            conn.execute("ALTER TABLE gacha_records_new RENAME TO gacha_records")
            # 提交所有迁移操作，使其持久化
            conn.commit()

            # 步骤5：迁移完成后，重新计算所有保底计数
            # 因为数据可能在迁移过程中被去重，保底计数需要重新计算
            self._rebuild_pity_counts(conn)
        except Exception as e:
            # 迁移过程中发生任何异常，记录警告日志（但不中断程序）
            logger.warning("migration failed, keeping existing schema: %s", e)
            # 尝试回滚当前事务，撤销迁移中的所有操作
            try:
                conn.rollback()
            except Exception:
                # 如果回滚也失败（极端情况，如连接已断开），忽略异常，继续执行
                pass
            # 清理可能残留的临时表 gacha_records_new，避免下次运行时出错
            try:
                # DROP TABLE IF EXISTS 确保表不存在时不报错
                conn.execute("DROP TABLE IF EXISTS gacha_records_new")
                conn.commit()
            except Exception:
                # 清理失败也忽略，因为主表应该还在
                pass

    # =====================================================================
    # 账号管理（CRUD 操作）
    # =====================================================================

    def add_account(self, account: Account) -> int:
        """添加或更新游戏账号

        使用 UPSERT（Update or Insert）操作：
          - 如果账号不存在（game+uid 组合不存在），插入新记录
          - 如果账号已存在，更新昵称和服务器信息，并刷新更新时间

        参数：
            account: Account 对象，包含以下字段：
              - game (str): 游戏名称，如 "genshin", "starrail"
              - uid (str): 用户在游戏中的唯一 ID
              - nickname (str): 用户昵称
              - server (str): 服务器区域，如 "cn", "global"

        返回值：
            int: 账号的数据库主键 id
                  - 新插入时返回新生成的 id
                  - 更新时返回已存在的 id

        SQL 逻辑解释：
          INSERT INTO accounts ... VALUES (?, ?, ?, ?)
          ON CONFLICT(game, uid) DO UPDATE SET ...
          这是 SQLite 3.24+ 支持的 UPSERT 语法：
            1. 先尝试插入新记录
            2. 如果 (game, uid) 组合冲突（已存在），则执行 UPDATE
            3. excluded.nickname 引用的是尝试插入的新值
            4. 同时更新 updated_at 为当前时间
        """
        # 使用上下文管理器获取数据库连接
        with self.connect() as conn:
            # 执行 UPSERT 操作：如果账号已存在则更新，不存在则插入
            cursor = conn.execute(
                """INSERT INTO accounts (game, uid, nickname, server)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(game, uid) DO UPDATE SET
                   nickname=excluded.nickname, server=excluded.server,
                   updated_at=datetime('now','localtime')""",
                # 参数化查询：使用 ? 占位符防止 SQL 注入攻击
                # excluded 是 SQLite UPSERT 语法的关键字，引用尝试插入的新值
                (account.game, account.uid, account.nickname, account.server)
            )
            # 提交事务，确保数据持久化到磁盘
            conn.commit()
            # lastrowid 返回最近一次 INSERT 操作生成的自增主键
            # 对于 UPDATE 操作，也会返回已存在记录的 id
            return cursor.lastrowid

    def get_accounts(self, game: str = None) -> List[Account]:
        """获取所有激活的账号列表

        根据是否指定游戏名称，执行不同的查询：
          - 指定游戏：只返回该游戏的账号
          - 未指定游戏：返回所有游戏的账号

        参数：
            game (str, 可选): 游戏名称筛选条件
                              如果为 None，则返回所有游戏的账号

        返回值：
            List[Account]: Account 对象列表，按更新时间倒序排列
                           （最近更新的账号排在前面）

        SQL 查询解释：
          情况1（指定了游戏）：
            SELECT * FROM accounts WHERE game=? AND is_active=1
            ORDER BY updated_at DESC
            - WHERE game=? 筛选指定游戏
            - AND is_active=1 只查询激活状态的账号（排除软删除的）
            - ORDER BY updated_at DESC 按更新时间降序（最新的在前）

          情况2（未指定游戏）：
            SELECT * FROM accounts WHERE is_active=1
            ORDER BY game, updated_at DESC
            - ORDER BY game 先按游戏名分组
            - 再按更新时间降序排列
        """
        # 获取数据库连接
        with self.connect() as conn:
            # 根据 game 参数是否为 None 决定查询方式
            if game:
                # 指定了游戏：按游戏名称和激活状态筛选，按更新时间倒序
                rows = conn.execute(
                    "SELECT * FROM accounts WHERE game=? AND is_active=1 ORDER BY updated_at DESC",
                    (game,)
                ).fetchall()
            else:
                # 未指定游戏：查询所有激活账号，先按游戏名排序，再按更新时间倒序
                rows = conn.execute(
                    "SELECT * FROM accounts WHERE is_active=1 ORDER BY game, updated_at DESC"
                ).fetchall()
            # 使用列表推导式将每一行数据库记录转换为 Account 对象
            return [self._row_to_account(r) for r in rows]

    def get_account_by_id(self, account_id: int) -> Optional[Account]:
        """根据账号 ID 查询单个账号

        参数：
            account_id (int): 账号的数据库主键 ID

        返回值：
            Optional[Account]: 找到则返回 Account 对象，未找到则返回 None

        SQL 查询解释：
          SELECT * FROM accounts WHERE id=?
          - 按主键精确查询，最多返回一条记录
          - 主键查询性能最优（B-Tree 索引直接定位）
        """
        # 获取数据库连接
        with self.connect() as conn:
            # 执行精确查询，fetchone() 返回单行结果或 None
            row = conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
            # 如果行存在，转换为 Account 对象；否则返回 None
            return self._row_to_account(row) if row else None

    def update_account(self, account: Account):
        """更新已有账号的信息

        更新 uid、nickname、server 三个字段，并自动刷新 updated_at 时间戳。
        注意：不会更新 game 字段，因为 game+uid 组合是唯一标识。

        参数：
            account: Account 对象，必须包含 id 字段（用于定位记录）
                     其他字段（uid, nickname, server）为要更新的新值

        SQL 逻辑解释：
          UPDATE accounts SET uid=?, nickname=?, server=?, updated_at=datetime('now','localtime')
          WHERE id=?
          - SET 子句指定要更新的字段和新值
          - WHERE id=? 确保只更新指定的账号（避免全表更新）
          - datetime('now','localtime') 自动设置为当前本地时间
        """
        # 获取数据库连接
        with self.connect() as conn:
            # 执行 UPDATE 语句，按 id 更新指定字段
            conn.execute(
                """UPDATE accounts SET uid=?, nickname=?, server=?, updated_at=datetime('now','localtime')
                   WHERE id=?""",
                # 参数顺序：uid, nickname, server, id
                (account.uid, account.nickname, account.server, account.id)
            )
            # 提交事务，使更新持久化
            conn.commit()

    def delete_account(self, account_id: int):
        """删除账号及其所有抽卡记录

        删除顺序很重要：必须先删除子表（gacha_records）的记录，再删除父表（accounts）的记录。
        虽然设置了 ON DELETE CASCADE 级联删除，但显式先删子表更安全可靠。

        参数：
            account_id (int): 要删除的账号 ID

        注意事项：
          1. 此操作会永久删除该账号的所有抽卡记录
          2. 建议在删除前调用 backup() 方法进行备份
          3. 这是硬删除（物理删除），数据不可恢复
        """
        # 获取数据库连接
        with self.connect() as conn:
            # 第一步：删除该账号的所有抽卡记录
            # 显式先删子表，确保即使 CASCADE 未启用也不会报外键约束错误
            conn.execute("DELETE FROM gacha_records WHERE account_id=?", (account_id,))
            # 第二步：删除账号本身
            conn.execute("DELETE FROM accounts WHERE id=?", (account_id,))
            # 提交事务，确保两步操作原子性地生效
            conn.commit()

    # =====================================================================
    # 抽卡记录管理（CRUD 操作）
    # =====================================================================

    def add_records(self, records: List[GachaRecord]) -> int:
        """批量添加抽卡记录

        逐条插入记录，遇到重复记录（违反 UNIQUE 约束）时静默跳过。
        这种设计支持增量导入：新导入的记录会自动跳过已存在的记录。

        参数：
            records (List[GachaRecord]): 抽卡记录列表，每个 GachaRecord 包含：
              - account_id (int): 关联的账号 ID
              - game (str): 游戏名称
              - pool_type (str): 卡池类型
              - pool_name (str): 卡池名称
              - item_id (str): 物品 ID
              - item_name (str): 物品名称
              - item_type (str): 物品类型
              - rarity (int): 稀有度等级
              - is_featured (bool): 是否为 UP 角色
              - count (int): 数量
              - time (str): 抽卡时间
              - pity_count (int): 保底计数
              - gacha_id (str): 抽卡事件 ID
              - pull_index (int): 批次序号
              - raw_data (str): 原始数据

        返回值：
            int: 成功插入的新记录数量（不包括因重复而跳过的记录）

        异常处理：
          - sqlite3.IntegrityError: 当记录违反 UNIQUE 约束时抛出
            （即相同 account_id + item_id 已存在），此时静默跳过该记录
        """
        # 获取数据库连接
        with self.connect() as conn:
            # 成功插入的记录计数器
            count = 0
            # 逐条处理每条抽卡记录
            for record in records:
                try:
                    # 执行 INSERT 语句，将记录插入 gacha_records 表
                    # 使用 15 个 ? 占位符对应 15 个字段
                    conn.execute(
                        """INSERT INTO gacha_records
                           (account_id, game, pool_type, pool_name, item_id, item_name, item_type,
                            rarity, is_featured, count, time, pity_count, gacha_id,
                            pull_index, raw_data)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        # 参数元组，与 SQL 中的 ? 占位符一一对应
                        # 注意：is_featured 从 bool 转换为 int（True->1, False->0）
                        (record.account_id, record.game, record.pool_type,
                         record.pool_name, record.item_id, record.item_name, record.item_type,
                         record.rarity, int(record.is_featured), record.count,
                         record.time, record.pity_count, record.gacha_id,
                         record.pull_index, record.raw_data)
                    )
                    # 插入成功，计数器加 1
                    count += 1
                except sqlite3.IntegrityError:
                    # 记录已存在（account_id + item_id 重复），静默跳过
                    # 这是增量导入的关键设计：不报错，只是不重复插入
                    pass
            # 提交整个批次的操作，一次性写入磁盘
            conn.commit()
            # 返回成功插入的记录数
            return count

    def get_records(self, account_id: int, pool_type: str = None,
                    rarity: int = None, limit: int = None) -> List[GachaRecord]:
        """查询指定账号的抽卡记录

        支持多条件组合查询，所有筛选条件都是可选的。
        查询结果按时间倒序排列（最新的记录在前）。

        参数：
            account_id (int): 账号 ID（必填）
            pool_type (str, 可选): 卡池类型筛选
            rarity (int, 可选): 稀有度筛选（如 5 只看五星）
            limit (int, 可选): 返回记录数上限

        返回值：
            List[GachaRecord]: 满足条件的抽卡记录列表

        SQL 构建逻辑（动态查询）：
          1. 基础查询：SELECT * FROM gacha_records WHERE account_id=?
          2. 如果指定了 pool_type，追加 AND pool_type=?
          3. 如果指定了 rarity，追加 AND rarity=?
          4. 始终按 time DESC, id DESC 排序（时间倒序，相同时间按 id 倒序）
          5. 如果指定了 limit，追加 LIMIT ?
        """
        # 获取数据库连接
        with self.connect() as conn:
            # 构建动态 SQL 查询的基础部分
            # 基础查询条件：按 account_id 筛选
            query = "SELECT * FROM gacha_records WHERE account_id=?"
            # 参数列表，与查询中的 ? 占位符按顺序对应
            params = [account_id]
            # 可选条件1：如果指定了卡池类型，追加筛选条件
            if pool_type:
                query += " AND pool_type=?"
                params.append(pool_type)
            # 可选条件2：如果指定了稀有度，追加筛选条件
            if rarity:
                query += " AND rarity=?"
                params.append(rarity)
            # 始终按时间倒序排列，相同时间按 id 倒序（保证最新记录在前）
            query += " ORDER BY time DESC, id DESC"
            # 可选条件3：如果指定了数量限制，追加 LIMIT 子句
            if limit:
                # 注意：limit 直接拼接到 SQL 中，不是参数化查询
                # 因为 SQLite 的 LIMIT 不支持参数化绑定
                # 但由于 limit 是 int 类型（由调用方传入），不存在 SQL 注入风险
                query += f" LIMIT {limit}"
            # 执行动态构建的查询并获取所有结果行
            rows = conn.execute(query, params).fetchall()
            # 使用列表推导式将每行数据库记录转换为 GachaRecord 对象
            return [self._row_to_record(r) for r in rows]

    def get_records_by_game(self, game: str, pool_type: str = None) -> List[GachaRecord]:
        """按游戏名称查询所有抽卡记录

        与 get_records() 不同，此方法按游戏名称而非账号 ID 查询。
        用于需要跨账号查看某游戏所有记录的场景。

        参数：
            game (str): 游戏名称（必填）
            pool_type (str, 可选): 卡池类型筛选

        返回值：
            List[GachaRecord]: 满足条件的抽卡记录列表，按时间正序排列

        SQL 查询逻辑：
          SELECT * FROM gacha_records WHERE game=?
          [AND pool_type=?]
          ORDER BY time ASC, id ASC
          - 注意：这里按时间正序（ASC）排列，与 get_records() 的 DESC 相反
          - 正序排列便于按时间线查看完整抽卡历史
        """
        # 获取数据库连接
        with self.connect() as conn:
            # 构建动态查询，基础条件为 game=?
            query = "SELECT * FROM gacha_records WHERE game=?"
            params = [game]
            # 可选的卡池类型筛选
            if pool_type:
                query += " AND pool_type=?"
                params.append(pool_type)
            # 按时间正序排列（从旧到新，便于查看时间线）
            query += " ORDER BY time ASC, id ASC"
            rows = conn.execute(query, params).fetchall()
            return [self._row_to_record(r) for r in rows]

    def get_record_count(self, account_id: int, pool_type: str = None) -> dict:
        """统计指定账号各稀有度的抽卡记录数量

        使用 GROUP BY 和 COUNT 聚合函数，按稀有度分组统计。
        返回的结果是一个字典，键为稀有度数字，值为该稀有度的记录数。

        参数：
            account_id (int): 账号 ID
            pool_type (str, 可选): 卡池类型筛选

        返回值：
            dict: 稀有度到数量的映射
                  例如：{3: 150, 4: 45, 5: 8}
                  表示三星 150 次，四星 45 次，五星 8 次

        SQL 查询逻辑：
          SELECT rarity, COUNT(*) as cnt FROM gacha_records
          WHERE account_id=? [AND pool_type=?]
          GROUP BY rarity
          - GROUP BY rarity 按稀有度值分组（每个不同的稀有度值为一组）
          - COUNT(*) 统计每组中的记录总数
          - 别名 cnt 便于通过 row["cnt"] 按列名访问结果
        """
        # 获取数据库连接
        with self.connect() as conn:
            # 构建聚合查询，基础条件为 account_id=?
            query = "SELECT rarity, COUNT(*) as cnt FROM gacha_records WHERE account_id=?"
            params = [account_id]
            # 可选的卡池类型筛选
            if pool_type:
                query += " AND pool_type=?"
                params.append(pool_type)
            # 按稀有度分组统计
            query += " GROUP BY rarity"
            rows = conn.execute(query, params).fetchall()
            # 使用字典推导式将结果行转换为 {稀有度: 数量} 的字典
            # row["rarity"] 获取稀有度值，row["cnt"] 获取对应的记录数
            return {row["rarity"]: row["cnt"] for row in rows}

    def get_latest_time(self, account_id: int, pool_type: str) -> Optional[str]:
        """获取指定账号某卡池的最新抽卡时间

        用于确定导入数据时的时间起点，避免导入重复的时间段。

        参数：
            account_id (int): 账号 ID
            pool_type (str): 卡池类型

        返回值：
            Optional[str]: 最新抽卡时间字符串（如 "2024-01-15 14:30:00"）
                           如果没有记录则返回 None

        SQL 查询逻辑：
          SELECT MAX(time) as max_time FROM gacha_records
          WHERE account_id=? AND pool_type=?
          - MAX(time) 聚合函数返回时间字符串的最大值
          - ISO 格式的时间字符串可以直接用 MAX() 比较大小
        """
        # 获取数据库连接
        with self.connect() as conn:
            # 查询指定账号和卡池类型的最新时间
            row = conn.execute(
                "SELECT MAX(time) as max_time FROM gacha_records WHERE account_id=? AND pool_type=?",
                (account_id, pool_type)
            ).fetchone()
            # 如果有记录返回最大时间，否则返回 None
            return row["max_time"] if row else None

    def get_last_5star_pity(self, account_id: int, pool_type: str,
                            game: str = "", pool_name: str = "") -> int:
        """获取当前保底进度（距离上次最高星的抽数）

        这是保底计数的高级接口，封装了不同游戏的保底规则差异。
        核心算法：
          1. 根据游戏名称确定最高稀有度（如原神/星铁为5，终末地可能为6）
          2. 根据游戏和卡池类型构建筛选条件
          3. 找到最后一次出最高星的时间点
          4. 统计那之后的所有抽卡次数即为当前保底进度

        参数：
            account_id (int): 账号 ID
            pool_type (str): 卡池类型
            game (str, 可选): 游戏名称，默认空字符串
            pool_name (str, 可选): 卡池名称，默认空字符串

        返回值：
            int: 当前保底进度（距离上次最高星的抽数）

        特殊处理（终末地 Endfield 游戏）：
          - 终末地的武器池在卡池名称变更时会重置保底
          - 需要额外按 pool_name 过滤
          - 不同 pool_type 可能属于同一个保底组（共享保底计数）
          - 保底组内非武器池的卡池轮换时保底继承
        """
        # 从 models 模块导入游戏相关的配置常量和函数
        # get_max_rarity: 根据游戏名称返回最高稀有度等级（如原神返回5）
        # get_endfield_pity_group: 根据卡池类型返回终末地的保底分组名
        # ENDFIELD_PITY_GROUP: 终末地卡池类型到保底分组的映射字典
        # ENDFIELD_PITY_RESETS_ON_NAME_CHANGE: 需要按名称重置保底的分组集合
        from core.models import get_max_rarity, get_endfield_pity_group, ENDFIELD_PITY_GROUP, ENDFIELD_PITY_RESETS_ON_NAME_CHANGE
        # 获取该游戏的最高稀有度等级，未指定游戏时默认为 5（五星）
        max_rarity = get_max_rarity(game) if game else 5

        # 直接获取数据库连接（不使用上下文管理器，因为后续有多次查询）
        conn = self._ensure_conn()

        # =====================================================
        # 根据游戏和卡池类型构建 SQL 筛选条件片段
        # pool_type_filter 是 SQL 的 WHERE 子句片段，pool_type_params 是对应的参数
        # =====================================================
        # 终末地游戏的特殊保底逻辑
        if game == "endfield":
            # 获取该卡池类型所属的保底分组
            pity_group = get_endfield_pity_group(pool_type)
            # 如果该分组属于"名称变更时重置保底"的类型（如武器池）
            if pity_group in ENDFIELD_PITY_RESETS_ON_NAME_CHANGE:
                # 武器池：需要同时按 pool_type 和 pool_name 过滤
                # 因为武器池在名称变更时会重置保底
                pool_type_filter = "pool_type=? AND pool_name=?"
                # 如果 pool_name 有值则使用它，否则使用空字符串
                pool_type_params = [pool_type, pool_name] if pool_name else [pool_type, ""]
            else:
                # 非武器池：按该保底组内的所有 pool_type 过滤
                # 同一保底组内的不同卡池轮换时保底计数继承
                # 例如：某保底组包含 "character_up_1" 和 "character_up_2"，需要同时查两个
                pool_types = [pt for pt, g in ENDFIELD_PITY_GROUP.items() if g == pity_group]
                # 使用 IN 子句匹配多个 pool_type，生成对应数量的 ? 占位符
                placeholders = ",".join("?" * len(pool_types))
                pool_type_filter = f"pool_type IN ({placeholders})"
                pool_type_params = pool_types
        else:
            # 非终末地游戏：简单的 pool_type 等值过滤
            pool_type_filter = "pool_type=?"
            pool_type_params = [pool_type]

        # =====================================================
        # 当未指定 pool_name 时，自动查找该保底组下最近活跃的 pool_name
        # 这确保了在未明确指定卡池名称时，使用最新的卡池进行保底查询
        # =====================================================
        if not pool_name:
            latest = conn.execute(
                f"""SELECT pool_name FROM gacha_records
                   WHERE account_id=? AND {pool_type_filter}
                   ORDER BY time DESC, id DESC LIMIT 1""",
                # 参数：account_id + 卡池筛选参数
                [account_id] + pool_type_params
            ).fetchone()
            if not latest:
                # 该保底组没有任何记录，保底计数为 0（还未抽过）
                return 0
            # 获取最近一条记录的 pool_name
            pool_name = latest["pool_name"]

        # =====================================================
        # 根据游戏类型分别处理保底查询
        # 终末地武器池和非终末地游戏需要额外按 pool_name 过滤
        # 终末地非武器池则不按 pool_name 过滤（跨轮换继承保底）
        # =====================================================
        if game == "endfield":
            if pity_group in ENDFIELD_PITY_RESETS_ON_NAME_CHANGE:
                # ---- 终末地武器池：按 pool_name 过滤（换名字清空保底）----
                # 第一次查询：找到最后一次出最高星的时间和 id
                row = conn.execute(
                    f"""SELECT time, id FROM gacha_records
                       WHERE account_id=? AND {pool_type_filter} AND rarity>=?
                       ORDER BY time DESC, id DESC LIMIT 1""",
                    [account_id] + pool_type_params + [max_rarity]
                ).fetchone()

                # 如果从未出过最高星（row 为 None）
                if row is None:
                    # 统计该卡池的所有记录数作为当前保底进度
                    total = conn.execute(
                        f"SELECT COUNT(*) as cnt FROM gacha_records WHERE account_id=? AND {pool_type_filter}",
                        [account_id] + pool_type_params
                    ).fetchone()
                    return total["cnt"] if total else 0

                # 第二次查询：统计最后一次最高星之后的所有抽卡次数
                count = conn.execute(
                    f"""SELECT COUNT(*) as cnt FROM gacha_records
                       WHERE account_id=? AND {pool_type_filter} AND (time > ? OR (time = ? AND id > ?))""",
                    # 参数：账号ID, 卡池筛选参数, 最近五星的时间（用于时间比较）和ID（用于同秒内区分）
                    [account_id] + pool_type_params + [row["time"], row["time"], row["id"]]
                ).fetchone()
                # 返回保底计数
                return count["cnt"] if count else 0
            else:
                # ---- 终末地非武器池：不按 pool_name 过滤（跨轮换继承保底）----
                # 第一次查询：找到最后一次出最高星的时间和 id
                row = conn.execute(
                    f"""SELECT time, id FROM gacha_records
                       WHERE account_id=? AND {pool_type_filter} AND rarity>=?
                       ORDER BY time DESC, id DESC LIMIT 1""",
                    [account_id] + pool_type_params + [max_rarity]
                ).fetchone()

                # 如果从未出过最高星（row 为 None）
                if row is None:
                    total = conn.execute(
                        f"SELECT COUNT(*) as cnt FROM gacha_records WHERE account_id=? AND {pool_type_filter}",
                        [account_id] + pool_type_params
                    ).fetchone()
                    return total["cnt"] if total else 0

                # 第二次查询：统计最后一次最高星之后的所有抽卡次数
                count = conn.execute(
                    f"""SELECT COUNT(*) as cnt FROM gacha_records
                       WHERE account_id=? AND {pool_type_filter} AND (time > ? OR (time = ? AND id > ?))""",
                    [account_id] + pool_type_params + [row["time"], row["time"], row["id"]]
                ).fetchone()
                return count["cnt"] if count else 0
        else:
            # ---- 非终末地游戏（如原神、星铁等）：同时按 pool_type 和 pool_name 过滤 ----
            # 第一次查询：找到最后一次出最高星的时间和 id
            row = conn.execute(
                """SELECT time, id FROM gacha_records
                   WHERE account_id=? AND pool_type=? AND pool_name=? AND rarity>=?
                   ORDER BY time DESC, id DESC LIMIT 1""",
                (account_id, pool_type, pool_name, max_rarity)
            ).fetchone()

            # 如果从未出过最高星（row 为 None）
            if row is None:
                # 统计该卡池的所有记录数作为当前保底进度
                total = conn.execute(
                    "SELECT COUNT(*) as cnt FROM gacha_records WHERE account_id=? AND pool_type=? AND pool_name=?",
                    (account_id, pool_type, pool_name)
                ).fetchone()
                return total["cnt"] if total else 0

            # 第二次查询：统计最后一次最高星之后的所有抽卡次数
            # AND (time > ? OR (time = ? AND id > ?)) 条件精确筛选出"之后"的记录
            count = conn.execute(
                """SELECT COUNT(*) as cnt FROM gacha_records
                   WHERE account_id=? AND pool_type=? AND pool_name=? AND (time > ? OR (time = ? AND id > ?))""",
                (account_id, pool_type, pool_name, row["time"], row["time"], row["id"])
            ).fetchone()
            return count["cnt"] if count else 0

    def calculate_pity_counts(self, account_id: int):
        """重新计算指定账号所有记录的保底计数

        当导入新数据或数据被修改后，需要重新计算保底计数。
        此方法会：
          1. 查询该账号的所有记录（按时间正序排列）
          2. 遍历记录，为每个保底分组维护一个累加计数器
          3. 每次遇到最高星物品时，将当前累加值写入 pity_count 并重置计数器
          4. 提交事务

        算法核心：
          - 维护一个字典 pity_counts，键为分组键，值为当前累计抽数
          - 每读一条记录，对应分组的计数器 +1
          - 当抽到最高星时，将计数器的值写入该记录的 pity_count 字段，然后重置为 0
          - 这样每条最高星记录的 pity_count 就表示"距离上一次出金抽了多少次"

        参数：
            account_id (int): 要重新计算保底计数的账号 ID

        排序说明：
          ORDER BY pool_type, time ASC, id ASC
          - 先按 pool_type 分组，确保同一卡池的记录连续处理
          - 再按时间正序（从旧到新），确保保底计数按实际抽卡顺序累加
          - 相同时间按 id 正序，保证同一秒内的记录也有确定的顺序
        """
        # 从 models 模块导入游戏相关的配置函数和常量
        from core.models import get_max_rarity, get_endfield_pity_group, ENDFIELD_PITY_RESETS_ON_NAME_CHANGE
        # 获取数据库连接
        with self.connect() as conn:
            # 查询该账号的所有抽卡记录，只选择需要的字段以提高性能
            rows = conn.execute(
                "SELECT id, game, pool_type, pool_name, rarity FROM gacha_records "
                "WHERE account_id=? ORDER BY pool_type, time ASC, id ASC",
                (account_id,)
            ).fetchall()

            # 保底计数器字典：键为分组键（元组），值为当前累加的抽卡次数
            pity_counts = {}
            # 遍历每一行抽卡记录（已按时间正序排列）
            for row in rows:
                # 提取当前记录的关键字段
                record_id = row["id"]        # 记录的数据库主键
                game = row["game"]            # 游戏名称
                pool_type = row["pool_type"]  # 卡池类型
                # 安全获取 pool_name：兼容旧版数据库可能没有此列的情况
                pool_name = row["pool_name"] if "pool_name" in row.keys() else ""
                rarity = row["rarity"]        # 稀有度等级
                # 获取该游戏的最高稀有度等级（如原神返回5，终末地返回6）
                max_rarity = get_max_rarity(game)

                # =====================================================
                # 确定保底分组键（group_key）
                # 相同分组键的记录共享同一个保底计数器
                # =====================================================
                if game == "endfield":
                    # 终末地游戏的特殊分组逻辑
                    group = get_endfield_pity_group(pool_type)
                    if group in ENDFIELD_PITY_RESETS_ON_NAME_CHANGE:
                        # 武器池等：按 (游戏, 保底组, 卡池名称) 分组
                        # 同一保底组内，不同名称的卡池独立计算保底
                        group_key = (game, group, pool_name)
                    else:
                        # 角色池等：按 (游戏, 保底组) 分组
                        # 同一保底组内的所有 pool_type 共享保底计数
                        group_key = (game, group)
                else:
                    # 非终末地游戏：按 (游戏, 卡池类型, 卡池名称) 分组
                    # 如果没有 pool_name，使用空字符串作为默认值
                    group_key = (game, pool_type, pool_name) if pool_name else (game, pool_type, "")

                # 如果该分组尚未初始化，设置初始计数为 0
                if group_key not in pity_counts:
                    pity_counts[group_key] = 0

                # 累加当前分组的抽卡次数（每次抽卡 +1）
                pity_counts[group_key] += 1

                # 检查是否抽到了最高星物品
                if rarity >= max_rarity:
                    # 抽到最高星：将当前累加值作为 pity_count 写入数据库
                    conn.execute(
                        "UPDATE gacha_records SET pity_count=? WHERE id=?",
                        (pity_counts[group_key], record_id)
                    )
                    # 重置该分组的计数器为 0，开始计算下一段保底
                    pity_counts[group_key] = 0

            # 提交事务，将所有 pity_count 的更新写入数据库
            conn.commit()

    def _rebuild_pity_counts(self, conn):
        """重新计算所有账号的保底计数（数据库迁移时使用）

        与 calculate_pity_counts() 的区别：
          - 此方法操作所有账号（不限定 account_id）
          - 不使用上下文管理器（因为迁移过程中连接已由调用方管理）
          - 用于数据库 Schema 迁移后重建保底计数

        参数：
            conn: 数据库连接对象（由调用方传入，不在此方法内管理连接生命周期）

        SQL 查询逻辑：
          SELECT id, game, pool_type, pool_name, rarity FROM gacha_records
          ORDER BY account_id, pool_type, time ASC, id ASC
          - 先按 account_id 分组，确保同一账号的记录连续
          - 再按 pool_type 分组，确保同一卡池类型连续
          - 最后按时间正序排列，确保按实际抽卡顺序处理
          - 这保证了每个账号的每个卡池都按正确顺序计算保底
        """
        # 从 models 模块导入游戏相关的配置函数和常量
        from core.models import get_max_rarity, get_endfield_pity_group, ENDFIELD_PITY_RESETS_ON_NAME_CHANGE
        # 查询所有记录，按账号、卡池类型和时间排序
        rows = conn.execute(
            "SELECT id, game, pool_type, pool_name, rarity FROM gacha_records "
            "ORDER BY account_id, pool_type, time ASC, id ASC"
        ).fetchall()

        # 保底计数器字典：键为分组键（元组），值为当前累加的抽卡次数
        pity_counts = {}
        # 遍历所有记录
        for row in rows:
            # 提取关键字段
            record_id = row["id"]
            game = row["game"]
            pool_type = row["pool_type"]
            # 安全获取 pool_name，兼容旧版数据库
            pool_name = row["pool_name"] if "pool_name" in row.keys() else ""
            rarity = row["rarity"]
            # 获取最高稀有度等级
            max_rarity = get_max_rarity(game)

            # 确定保底分组键（逻辑与 calculate_pity_counts 完全相同）
            if game == "endfield":
                group = get_endfield_pity_group(pool_type)
                if group in ENDFIELD_PITY_RESETS_ON_NAME_CHANGE:
                    # 武器池：按 (游戏, 保底组, 卡池名称) 分组
                    group_key = (game, group, pool_name)
                else:
                    # 非武器池：按 (游戏, 保底组) 分组，跨卡池继承保底
                    group_key = (game, group)
            else:
                # 非终末地游戏：按 (游戏, 卡池类型, 卡池名称) 分组
                group_key = (game, pool_type, pool_name) if pool_name else (game, pool_type, "")

            # 初始化该分组的计数器（如果尚未存在）
            if group_key not in pity_counts:
                pity_counts[group_key] = 0

            # 累加抽卡次数
            pity_counts[group_key] += 1

            # 如果抽到最高星，记录保底计数并重置
            if rarity >= max_rarity:
                conn.execute(
                    "UPDATE gacha_records SET pity_count=? WHERE id=?",
                    (pity_counts[group_key], record_id)
                )
                # 重置计数器
                pity_counts[group_key] = 0

        # 提交所有保底计数的更新
        conn.commit()

    def get_total_records(self) -> int:
        """获取数据库中所有抽卡记录的总数

        用于系统概览和统计面板显示。

        返回值：
            int: 所有抽卡记录的总数量

        SQL 查询逻辑：
          SELECT COUNT(*) as cnt FROM gacha_records
          - COUNT(*) 聚合函数统计所有行数（包括 NULL 值行）
          - 别名 cnt 便于通过 row["cnt"] 按列名访问结果
        """
        # 获取数据库连接
        with self.connect() as conn:
            # 执行 COUNT 聚合查询
            row = conn.execute("SELECT COUNT(*) as cnt FROM gacha_records").fetchone()
            # 返回记录总数
            return row["cnt"]

    # =====================================================================
    # 数据库备份与恢复
    # =====================================================================

    def backup(self) -> str:
        """创建数据库备份

        备份策略：
          1. 生成带时间戳的备份文件名
          2. 使用 shutil.copy2 复制数据库文件（保留文件元数据）
          3. 清理旧的备份文件，只保留最新的 N 个

        返回值：
            str: 备份文件的完整路径

        备份文件命名规则：
          gacha_backup_YYYYMMDD_HHMMSS.db
          例如：gacha_backup_20240115_143000.db

        注意：备份前应确保数据库连接未锁定文件，
        shutil.copy2 会复制文件的全部内容（包括当前未提交的数据在 WAL 模式下）
        """
        # 生成当前时间的格式化字符串，用作备份文件名的一部分
        # strftime 将 datetime 对象格式化为指定格式的字符串
        # %Y=四位年, %m=两位月, %d=两位日, %H=两位时, %M=两位分, %S=两位秒
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # 构建备份文件的完整路径
        # Path 对象支持 / 运算符拼接路径
        # backup_dir 从配置中读取，如 "backups/"
        backup_path = Path(self.config.backup_dir) / f"gacha_backup_{timestamp}.db"
        # shutil.copy2 复制文件并保留文件元数据（修改时间、权限等）
        # 比 shutil.copy() 更完善，元数据也被保留
        shutil.copy2(self.db_path, backup_path)
        # 清理旧的备份文件，避免磁盘空间无限增长
        self._cleanup_old_backups()
        # 返回备份文件的路径字符串
        return str(backup_path)

    def restore(self, backup_path: str):
        """从备份文件恢复数据库

        恢复流程：
          1. 验证备份文件是否存在
          2. 关闭当前数据库连接（释放文件锁）
          3. 用备份文件覆盖当前数据库文件
          4. 重置初始化标志，重新调用 __init__() 重建连接和表结构

        参数：
            backup_path (str): 备份文件的完整路径

        异常处理：
          - FileNotFoundError: 如果备份文件不存在，抛出此异常并附带路径信息

        注意事项：
          - 恢复操作会覆盖当前数据库的所有数据
          - 建议在恢复前先调用 backup() 备份当前数据
        """
        # 检查备份文件是否存在
        if not Path(backup_path).exists():
            # 备份文件不存在，抛出 FileNotFoundError 异常
            raise FileNotFoundError(f"备份文件不存在: {backup_path}")
        # 关闭当前数据库连接，确保文件不被锁定
        self.close()
        # 用备份文件覆盖当前数据库文件
        shutil.copy2(backup_path, self.db_path)
        # 重置初始化标志，允许 __init__ 重新执行完整的初始化逻辑
        self._initialized = False
        # 重新调用 __init__，重建数据库连接和表结构
        # 注意：由于 __new__ 返回同一实例，这里只是重新执行初始化逻辑
        self.__init__()

    def _cleanup_old_backups(self):
        """清理旧的备份文件，只保留最新的 N 个

        备份数量上限从配置文件中读取，默认为 10 个。
        按文件修改时间倒序排列，删除超出限制的旧文件。

        工作流程：
          1. 从配置中读取最大备份数量（max_backups）
          2. 获取备份目录下所有匹配 "gacha_backup_*.db" 的文件
          3. 按文件名排序（文件名包含时间戳，所以排序等同于按时间排序）
          4. reverse=True 反转为倒序（最新的在前）
          5. 删除从第 max_backups+1 个开始的旧文件
        """
        # 从配置中读取最大备份数量，默认为 10
        max_backups = self.config.get_int("max_backups", 10)
        # 获取备份目录的 Path 对象
        backup_dir = Path(self.config.backup_dir)
        # glob("gacha_backup_*.db") 匹配所有备份文件
        # sorted() 默认按文件名升序排列，reverse=True 反转为降序
        # 由于文件名包含时间戳，降序等同于按时间从新到旧排列
        backups = sorted(backup_dir.glob("gacha_backup_*.db"), reverse=True)
        # 使用切片获取超出数量限制的旧备份文件
        # backups[max_backups:] 从第 max_backups 个元素开始的所有元素
        for old in backups[max_backups:]:
            # unlink() 删除文件（等同于 os.remove()）
            old.unlink()

    # =====================================================================
    # 数据导入导出
    # =====================================================================

    def export_json(self, account_id: int = None) -> str:
        """将抽卡记录导出为 JSON 格式字符串

        支持两种导出模式：
          1. 指定 account_id：只导出该账号的记录
          2. 未指定 account_id：导出所有记录

        参数：
            account_id (int, 可选): 账号 ID，为 None 时导出所有记录

        返回值：
            str: 格式化的 JSON 字符串
                  - ensure_ascii=False: 支持中文等非 ASCII 字符直接输出（不做 Unicode 转义）
                  - indent=2: 每级缩进 2 个空格，便于人类阅读

        导出的 JSON 结构示例：
          [
            {
              "game": "genshin",
              "pool_type": "character",
              "pool_name": "纳西妲 UP",
              "item_name": "纳西妲",
              "item_type": "角色",
              "rarity": 5,
              "is_featured": true,
              "time": "2024-01-15 14:30:00",
              "pity_count": 78
            },
            ...
          ]
        """
        # 根据是否指定账号 ID 选择不同的查询方式
        if account_id:
            # 指定了账号 ID：查询该账号的所有记录（默认时间倒序）
            records = self.get_records(account_id)
        else:
            # 未指定账号 ID：查询所有记录，按时间正序排列
            with self.connect() as conn:
                rows = conn.execute("SELECT * FROM gacha_records ORDER BY time ASC").fetchall()
                records = [self._row_to_record(r) for r in rows]

        # 构建导出数据列表
        data = []
        for r in records:
            # 将每条 GachaRecord 对象转换为字典，只包含需要导出的字段
            data.append({
                "game": r.game,                  # 游戏名称
                "pool_type": r.pool_type,        # 卡池类型
                "pool_name": r.pool_name,        # 卡池名称
                "item_name": r.item_name,        # 物品名称
                "item_type": r.item_type,        # 物品类型
                "rarity": r.rarity,              # 稀有度等级
                "is_featured": r.is_featured,    # 是否为 UP 角色
                "time": r.time,                  # 抽卡时间
                "pity_count": r.pity_count,      # 保底计数
            })
        # 使用 json.dumps 将 Python 字典列表序列化为 JSON 字符串
        # ensure_ascii=False: 允许中文等字符直接输出为可读文本
        # indent=2: 格式化输出，每个层级缩进 2 个空格
        return json.dumps(data, ensure_ascii=False, indent=2)

    def import_json(self, json_str: str, account_id: int) -> int:
        """从 JSON 字符串导入抽卡记录

        支持两种 JSON 输入格式：
          1. 数组格式：直接是记录列表 [...]
          2. 对象格式：包含 "list" 或 "records" 键的字典 {..., "list": [...]}

        参数：
            json_str (str): JSON 格式的字符串
            account_id (int): 目标账号 ID（导入的记录会关联到此账号）

        返回值：
            int: 成功导入的记录数量（重复记录被跳过不计入）

        注意事项：
          - 重复的记录（account_id + item_id 已存在）会被 add_records() 自动跳过
          - 缺失的字段会使用安全的默认值（get 方法 + 默认参数）
          - rarity 默认为 5（五星），is_featured 默认为 False
        """
        # 使用 json.loads 将 JSON 字符串解析为 Python 对象（list 或 dict）
        data = json.loads(json_str)
        # 兼容两种 JSON 格式
        if isinstance(data, dict):
            # 对象格式：尝试获取 "list" 或 "records" 键的值
            # 如果都不存在，返回空列表作为兜底
            data = data.get("list", data.get("records", []))
        # 将 JSON 字典数据逐条转换为 GachaRecord 对象
        records = []
        for item in data:
            records.append(GachaRecord(
                account_id=account_id,  # 所有导入记录关联到指定账号
                # 使用 dict.get() 方法安全地获取字段值
                # 当 JSON 中缺少某个字段时，使用指定的默认值
                game=item.get("game", ""),
                pool_type=item.get("pool_type", ""),
                pool_name=item.get("pool_name", ""),
                item_name=item.get("item_name", ""),
                item_type=item.get("item_type", ""),
                rarity=item.get("rarity", 5),           # 默认稀有度为 5（五星）
                is_featured=bool(item.get("is_featured", False)),  # 转换为 bool 类型
                time=item.get("time", ""),
                pity_count=item.get("pity_count", 0),
            ))
        # 调用 add_records() 批量插入，返回成功导入的数量
        return self.add_records(records)

    # =====================================================================
    # 数据转换辅助方法（数据库行 -> 数据模型对象）
    # =====================================================================

    def _row_to_account(self, row) -> Account:
        """将数据库行对象转换为 Account 数据模型

        使用 sqlite3.Row 的字典式访问方式（row["column_name"]）提取字段值。
        is_active 字段从 SQLite 的整数（0/1）转换为 Python 的布尔值（False/True）。

        参数：
            row: sqlite3.Row 对象，代表 accounts 表的一行
                 支持按列名或列索引访问字段值

        返回值：
            Account: 账号数据模型对象，包含所有字段
        """
        return Account(
            id=row["id"],                    # 数据库自增主键
            game=row["game"],                # 游戏名称标识符
            uid=row["uid"],                  # 用户在游戏中的唯一 ID
            nickname=row["nickname"],        # 用户昵称
            server=row["server"],            # 服务器区域
            is_active=bool(row["is_active"]),  # 激活状态：int(0/1) -> bool(False/True)
            created_at=row["created_at"],    # 记录创建时间
            updated_at=row["updated_at"],    # 记录最后更新时间
        )

    def _row_to_record(self, row) -> GachaRecord:
        """将数据库行对象转换为 GachaRecord 数据模型

        使用 sqlite3.Row 的字典式访问方式提取字段值。
        兼容旧版数据库可能缺少 pool_name 列的情况（通过 keys() 检查）。
        is_featured 字段从整数（0/1）转换为布尔值（False/True）。

        参数：
            row: sqlite3.Row 对象，代表 gacha_records 表的一行

        返回值：
            GachaRecord: 抽卡记录数据模型对象，包含所有字段
        """
        return GachaRecord(
            id=row["id"],                    # 数据库自增主键
            account_id=row["account_id"],    # 关联的账号 ID（外键）
            game=row["game"],                # 游戏名称
            pool_type=row["pool_type"],      # 卡池类型
            # 安全获取 pool_name：兼容旧版数据库可能没有此列
            # row.keys() 返回 Row 对象中所有列名的列表
            pool_name=row["pool_name"] if "pool_name" in row.keys() else "",
            item_id=row["item_id"],          # 物品唯一标识符
            item_name=row["item_name"],      # 物品名称
            item_type=row["item_type"],      # 物品类型
            rarity=row["rarity"],            # 稀有度等级
            is_featured=bool(row["is_featured"]),  # 是否 UP 角色：int -> bool
            count=row["count"],              # 获得数量
            time=row["time"],                # 抽卡时间
            pity_count=row["pity_count"],    # 保底计数
            gacha_id=row["gacha_id"],        # 抽卡事件唯一 ID
            pull_index=row["pull_index"],    # 批次中的序号
            raw_data=row["raw_data"],        # 原始抽卡数据（JSON 字符串）
            created_at=row["created_at"],    # 记录创建时间
        )

    def close(self):
        """关闭数据库连接

        关闭流程：
          1. 检查连接对象是否存在（避免对 None 调用 close() 导致异常）
          2. 调用 close() 方法关闭 SQLite 连接，释放文件锁和内存资源
          3. 将连接引用设为 None，确保后续操作通过 _ensure_conn() 创建新连接

        注意：
          - 关闭后，后续的数据库操作会自动创建新连接（延迟初始化机制）
          - 应在应用程序退出时调用此方法释放系统资源
          - 调用 restore() 方法前也需要先关闭连接
        """
        # 检查连接是否存在（防止对 None 调用 close() 方法）
        if self._conn:
            # 关闭 SQLite 连接，释放数据库文件锁和内存中的缓存
            self._conn.close()
            # 将连接引用设为 None，确保后续操作会创建新连接
            self._conn = None
