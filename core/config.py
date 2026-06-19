"""配置管理模块（稳定性优化版）"""
# 该模块是整个应用程序的配置管理中心，负责加载、合并、读取、写入和持久化配置。
# 采用单例模式（Singleton Pattern），确保整个应用运行期间只有一个 Config 实例。
# 支持多层配置覆盖：默认值 -> 全局配置文件(config.yaml) -> 用户配置文件(user_config.yaml)。
# 支持点号分隔的层级键（如 "cache_paths.genshin.cn"），用于访问嵌套的字典结构。

import os  # 导入 os 模块，提供操作系统相关的功能，如文件路径操作、环境变量访问等
import yaml  # 导入 PyYAML 库，用于读取和写入 YAML 格式的配置文件。YAML 是一种人类可读的数据序列化格式，常用于配置文件
from pathlib import Path  # 导入 pathlib.Path 类，提供面向对象的文件系统路径操作方式，比 os.path 更加简洁和直观


class Config:
    """应用配置管理"""
    # Config 类是整个配置系统的核心，采用单例模式设计。
    # 内部使用字典存储所有配置项，支持通过点号路径访问嵌套配置。
    # 配置加载优先级：代码默认值 < config.yaml < user_config.yaml。
    # 所有路径配置都相对于项目根目录（即 config.py 所在目录的父目录）。

    _instance = None  # 类变量，用于存储单例实例。初始值为 None，首次创建 Config 实例时被赋值，后续所有调用都返回此实例
    _config = None  # 类变量，用于存储合并后的最终配置字典。初始值为 None，首次 __init__ 调用时加载。使用类变量配合单例模式

    DEFAULTS = {
        # DEFAULTS 字典定义了所有配置项的默认值。当配置文件中不存在某个配置项时，会使用此处的值。
        # 这是配置系统的最低优先级层，任何配置文件中的值都可以覆盖这些默认值。
        "database_path": "data/gacha_records.db",  # 数据库文件的相对路径（相对于项目根目录），使用 SQLite 存储抽卡记录
        "backup_dir": "data/backups",  # 备份文件的存储目录相对路径。自动备份功能会将数据库备份到此目录
        "export_dir": "data/exports",  # 导出文件的存储目录相对路径。用户导出的 CSV/Excel 等文件会保存到此目录
        "request_interval": 1.0,  # HTTP 请求之间的最小间隔时间（单位：秒），用于避免对 API 服务器发送过快的请求而被限流或封禁
        "request_timeout": 15,  # HTTP 请求的超时时间（单位：秒），超过此时间未收到响应则认为请求失败
        "max_backups": 10,  # 备份目录中最多保留的备份文件数量，超出此数量时最旧的备份会被自动删除
        "backup_interval_hours": 24,  # 自动备份的间隔时间（单位：小时），每隔此时间自动执行一次数据库备份
        "auto_backup": True,  # 是否启用自动备份功能，为 True 时程序启动后会定期自动备份数据库
    }

    def __new__(cls):
        # __new__ 方法是 Python 的静态方法，在 __init__ 之前被调用，负责创建并返回新的实例对象。
        # 这里通过重写 __new__ 实现单例模式：检查 _instance 是否为 None。
        if cls._instance is None:  # 如果 _instance 为 None，说明这是第一次创建 Config 实例
            cls._instance = super().__new__(cls)
            # 调用父类（object）的 __new__ 方法创建实例，并将新实例赋值给类变量 _instance
        return cls._instance
        # 无论是否是第一次创建，都返回同一个 _instance 实例。这保证了 Config 全局唯一

    def __init__(self):
        # __init__ 方法在实例创建后被调用，负责初始化实例的属性和加载配置。
        # 由于 __new__ 的单例模式，__init__ 可能会被多次调用（每次调用 Config() 时）。
        # 通过检查 self._config 是否为 None 来确保初始化逻辑只执行一次。
        if self._config is None:  # 检查配置字典是否已初始化，只有首次调用时 _config 才为 None
            self._base_dir = Path(__file__).parent.parent
            # Path(__file__) 获取当前文件 config.py 的绝对路径
            # .parent 获取其父目录（即 core/ 目录）
            # .parent.parent 再获取上一级目录，即项目根目录（gacha-analyzer/）
            # 结果是一个 Path 对象，后续所有相对路径都基于此目录进行拼接

            self._config_path = self._base_dir / "config.yaml"
            # 拼接全局配置文件的完整路径。"/" 运算符在 Path 对象中用于路径拼接
            # 该文件包含用户自定义的全局配置，优先级高于代码默认值

            self._user_config_path = self._base_dir / "data" / "user_config.yaml"
            # 拼接用户配置文件的完整路径。该文件位于 data/ 目录下，是用户级别的配置
            # 优先级最高，可以覆盖全局配置中的任何配置项

            self._config = {}  # 初始化配置字典为空字典，后续由 _load() 方法填充实际配置内容

            self._load()  # 调用 _load() 方法加载所有配置：默认值 -> 全局配置 -> 用户配置，按优先级逐层合并

    def _load(self):
        # _load() 方法负责加载并合并所有配置层。加载顺序决定了配置的优先级：后加载的会覆盖先加载的。
        # 加载流程：
        #   1. 先将 DEFAULTS（代码默认值）复制到 self._config
        #   2. 加载 config.yaml（全局配置）并与 self._config 深度合并
        #   3. 加载 user_config.yaml（用户配置）并与 self._config 深度合并
        # 最终 self._config 中包含合并后的完整配置，用户配置优先级最高

        self._config = dict(self.DEFAULTS)
        # 使用 dict() 构造函数创建 DEFAULTS 的浅拷贝。使用浅拷贝而非直接赋值
        # 是为了防止后续对 self._config 的修改意外影响到 DEFAULTS 类变量

        if self._config_path.exists():
            # 检查全局配置文件 config.yaml 是否存在于文件系统中
            # 如果文件不存在则跳过此步骤，仅使用默认配置
            with open(self._config_path, "r", encoding="utf-8") as f:
                # 以只读模式（"r"）打开全局配置文件，使用 UTF-8 编码以支持中文等非 ASCII 字符
                # with 语句确保文件在读取完成后自动关闭，即使发生异常也不会泄漏文件句柄
                default_config = yaml.safe_load(f) or {}
                # yaml.safe_load() 将 YAML 文件内容解析为 Python 字典。使用 safe_load 而非 load 是为了防止
                # YAML 中的恶意代码执行（安全性考虑）。如果文件为空或解析结果为 None，则使用空字典 {} 代替
                self._deep_merge(self._config, default_config)
                # 将全局配置深度合并到 self._config 中。合并规则：
                # - 如果两边的值都是字典，则递归合并
                # - 否则，全局配置的值覆盖默认值

        if self._user_config_path.exists():
            # 检查用户配置文件 data/user_config.yaml 是否存在
            # 用户配置文件是可选的，如果不存在则仅使用默认值和全局配置
            with open(self._user_config_path, "r", encoding="utf-8") as f:
                # 以 UTF-8 编码只读模式打开用户配置文件
                user_config = yaml.safe_load(f) or {}
                # 解析 YAML 用户配置文件，如果文件为空则使用空字典
                self._deep_merge(self._config, user_config)
                # 将用户配置深度合并到 self._config 中。由于这是最后一步合并，
                # 用户配置中的任何值都会覆盖全局配置和默认值中的同名配置项

    def _deep_merge(self, base, override):
        # _deep_merge() 方法实现字典的深度合并（Deep Merge）。
        # 与简单的 dict.update() 不同，深度合并会递归处理嵌套字典：
        # - 如果 base 和 override 中同一个 key 对应的值都是字典，则递归合并这两个字典
        # - 否则，override 中的值直接覆盖 base 中的值
        # 此方法会直接修改 base 字典（原地修改），不会创建新字典。
        #
        # 参数：
        #   base: 目标字典（被合并的基础字典）。合并后的结果会存储在此字典中。
        #   override: 覆盖字典（提供新值的字典）。其中的值会覆盖 base 中的同名值。
        #
        # 示例：
        #   base = {"a": 1, "b": {"c": 2, "d": 3}}
        #   override = {"b": {"c": 99}, "e": 5}
        #   结果: base = {"a": 1, "b": {"c": 99, "d": 3}, "e": 5}

        for key, value in override.items():
            # 遍历 override 字典中的每一个键值对。items() 返回 (key, value) 的迭代器
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                # 条件判断：1) key 已存在于 base 中；2) base[key] 的值是字典；3) override 中该 key 的值也是字典
                # 三个条件同时满足时，说明两边都是嵌套字典，需要递归合并
                self._deep_merge(base[key], value)
                # 递归调用 _deep_merge()，将 override 的子字典合并到 base 的子字典中
            else:
                # 以下三种情况之一：
                #   a) key 在 base 中不存在（新增配置项）
                #   b) base[key] 不是字典（简单值被字典覆盖，或字典被简单值覆盖）
                #   c) override 中该 key 的值不是字典（简单值覆盖）
                base[key] = value
                # 直接用 override 的值替换 base 中的值，实现配置覆盖

    def get(self, key, default=None):
        # get() 方法根据点号分隔的键路径获取配置值。
        # 支持嵌套访问，如 "cache_paths.genshin.cn" 会依次查找 _config["cache_paths"]["genshin"]["cn"]。
        # 如果路径中任何一层不存在或值为 None，则返回 default 参数指定的默认值。
        #
        # 参数：
        #   key: 配置键名，支持点号分隔的层级路径（字符串类型）。例如 "database_path" 或 "cache_paths.genshin.cn"
        #   default: 当配置项不存在时返回的默认值。默认为 None
        #
        # 返回值：
        #   找到的配置值（可以是任意类型），或 default 参数指定的默认值
        #
        # 示例：
        #   config.get("database_path") -> "data/gacha_records.db"
        #   config.get("cache_paths.genshin.cn", "") -> "miHoYo/..." 或 ""

        keys = key.split(".")
        # 使用 "." 作为分隔符将键路径拆分为列表。例如 "cache_paths.genshin.cn" -> ["cache_paths", "genshin", "cn"]
        # 如果键名不含点号（如 "database_path"），则列表只有一个元素 ["database_path"]

        value = self._config
        # 将 value 初始化为整个配置字典，作为逐层查找的起点

        for k in keys:
            # 逐层遍历拆分后的键列表，每次向下查找一层
            if isinstance(value, dict):
                # 检查当前层的值是否为字典（只有字典类型才能继续用键访问）
                value = value.get(k)
                # 使用字典的 get() 方法获取当前键对应的值。如果键不存在，返回 None 而非抛出异常
            else:
                # 如果当前层的值不是字典（可能是字符串、数字、列表等基本类型），
                # 则无法继续向下查找，说明路径无效，返回默认值
                return default
            if value is None:
                # 如果当前层获取到的值为 None（表示该键不存在），则返回默认值
                return default
        return value
        # 所有层级都查找成功，返回最终找到的配置值

    def get_int(self, key, default=None):
        # get_int() 方法获取指定键的整数值。
        # 内部先调用 get() 获取原始值，然后尝试将其转换为 int 类型。
        # 如果转换失败（如值为字符串 "abc" 或 None），则返回默认值。
        #
        # 参数：
        #   key: 配置键名（字符串类型），支持点号分隔的层级路径
        #   default: 转换失败或配置不存在时返回的默认值，默认为 None
        #
        # 返回值：
        #   整数类型的配置值，或 default 参数指定的默认值

        value = self.get(key, default)
        # 调用 get() 方法获取配置值。如果配置项不存在，会返回 default 作为默认值

        try:
            return int(value)
            # 尝试将获取到的值转换为整数类型。int() 可以处理：
            # - 整数（直接返回）
            # - 浮点数（截断小数部分，如 3.9 -> 3）
            # - 数字字符串（如 "15" -> 15）
            # 如果值为 None 或无法转换的字符串，会抛出 ValueError 异常
        except Exception:
            # 捕获所有异常（包括 ValueError、TypeError 等），确保方法不会因类型转换错误而崩溃
            return default
            # 转换失败时返回默认值，保证调用方始终能获得一个可用的返回值

    def get_float(self, key, default=None):
        # get_float() 方法获取指定键的浮点数值。
        # 与 get_int() 类似，但转换目标类型为 float。
        # 用于获取如 request_interval（请求间隔）等需要小数精度的配置项。
        #
        # 参数：
        #   key: 配置键名（字符串类型），支持点号分隔的层级路径
        #   default: 转换失败或配置不存在时返回的默认值，默认为 None
        #
        # 返回值：
        #   浮点数类型的配置值，或 default 参数指定的默认值

        value = self.get(key, default)
        # 调用 get() 方法获取配置值

        try:
            return float(value)
            # 尝试将获取到的值转换为浮点数。float() 可以处理：
            # - 浮点数（直接返回）
            # - 整数（自动转换为浮点数，如 15 -> 15.0）
            # - 数字字符串（如 "0.3" -> 0.3）
            # - 科学记数法字符串（如 "1e-3" -> 0.001）
        except Exception:
            # 捕获所有异常，确保方法的健壮性
            return default
            # 转换失败时返回默认值

    def set(self, key, value):
        # set() 方法设置指定键的配置值，支持点号分隔的层级路径。
        # 如果路径中的中间层级不存在，会自动创建嵌套的字典结构。
        # 注意：set() 方法只修改内存中的配置字典，不会立即持久化到文件。
        # 调用方需要在设置完成后显式调用 save() 方法来保存更改。
        #
        # 参数：
        #   key: 配置键名（字符串类型），支持点号分隔的层级路径。例如 "database_path" 或 "cache_paths.genshin.cn"
        #   value: 要设置的配置值，可以是任意类型（字符串、数字、布尔值、字典等）
        #
        # 示例：
        #   config.set("request_interval", 0.5)  -> 设置顶层配置
        #   config.set("cache_paths.genshin.cn", "miHoYo/...")  -> 设置嵌套配置，自动创建中间层字典

        keys = key.split(".")
        # 使用 "." 分隔符将键路径拆分为列表。例如 "cache_paths.genshin.cn" -> ["cache_paths", "genshin", "cn"]

        config = self._config
        # 将 config 引用指向配置字典，后续操作会在此字典上进行

        for k in keys[:-1]:
            # 遍历除最后一个键以外的所有键（即中间层级的键）
            # keys[:-1] 使用切片操作去掉列表最后一个元素
            # 例如 ["cache_paths", "genshin", "cn"] -> ["cache_paths", "genshin"]
            if k not in config:
                # 如果当前层级的键不存在于字典中，则创建一个空字典
                # 这样就自动构建了嵌套的字典结构，无需手动创建中间层
                config[k] = {}
            config = config[k]
            # 将 config 引用移动到下一层级的字典，继续向下遍历
            # 这是一个逐层深入的过程：从最外层字典逐步导航到目标层级

        config[keys[-1]] = value
        # 获取最后一个键（目标键），并将值设置到该键上
        # 此时 config 引用指向目标键所在的父字典，直接赋值即可完成设置
        # 例如，对于 "cache_paths.genshin.cn"，此时 keys[-1] = "cn"，
        # config 指向 _config["cache_paths"]["genshin"] 字典，设置其 "cn" 键的值

    def save(self):
        # save() 方法将当前内存中的配置字典持久化保存到用户配置文件（user_config.yaml）。
        # 保存前会自动确保 data/ 目录存在。
        # 注意：此方法会将整个配置字典（包括默认值和全局配置）写入文件，
        # 因此 user_config.yaml 中会包含所有配置项，而不仅仅是用户修改过的配置。
        #
        # 异常处理：
        # - 如果 data/ 目录无法创建（权限不足等），mkdir 会抛出 OSError 异常
        # - 如果文件写入失败（磁盘已满、权限不足等），open() 或 yaml.dump() 会抛出异常

        self._user_config_path.parent.mkdir(parents=True, exist_ok=True)
        # 确保用户配置文件的父目录（data/）存在
        # parents=True 递归创建不存在的父目录
        # exist_ok=True 如果目录已存在则不抛出异常
        # 这是为了防止首次保存时 data/ 目录尚未创建的情况

        with open(self._user_config_path, "w", encoding="utf-8") as f:
            # 以写入模式（"w"）打开用户配置文件，使用 UTF-8 编码
            # 如果文件已存在则覆盖（"w" 模式），如果不存在则创建新文件
            # with 语句确保文件在写入完成后自动关闭
            yaml.dump(self._config, f, allow_unicode=True, default_flow_style=False)
            # yaml.dump() 将 Python 字典序列化为 YAML 格式并写入文件
            # 参数说明：
            #   self._config: 要序列化的配置字典（包含所有合并后的配置）
            #   f: 文件对象，yaml.dump 会将内容写入此文件
            #   allow_unicode=True: 允许输出非 ASCII 字符（如中文），否则会被转义为 \uXXXX 格式
            #   default_flow_style=False: 使用块状格式（block style）而非流式格式（flow style）输出 YAML
            #     块状格式更易读，例如：
            #     database_path: data/gacha_records.db
            #     而非流式格式：{database_path: data/gacha_records.db}

    @property
    def base_dir(self):
        # base_dir 是一个只读属性，返回项目根目录的 Path 对象。
        # 使用 @property 装饰器将方法伪装为属性，调用时无需加括号：config.base_dir
        # 项目根目录是所有相对路径配置的基准目录。
        #
        # 返回值：
        #   Path 类型的项目根目录路径对象。例如 Path("D:/gacha-analyzer")
        return self._base_dir
        # 直接返回在 __init__ 中计算好的 _base_dir 属性

    @property
    def db_path(self):
        # db_path 是一个只读属性，返回数据库文件的绝对路径（字符串类型）。
        # 路径由项目根目录 + 配置中的 database_path 拼接而成。
        # 如果配置中不存在 database_path，则使用 DEFAULTS 中的默认值。
        # 访问此属性时会自动确保数据库文件的父目录存在。
        #
        # 返回值：
        #   字符串类型的数据库文件绝对路径。例如 "D:/gacha-analyzer/data/gacha_records.db"
        path = self._base_dir / str(self.get("database_path", self.DEFAULTS["database_path"]))
        # 拼接路径：
        #   1. self.get("database_path", self.DEFAULTS["database_path"]) 获取配置值，如果不存在则使用默认值 "data/gacha_records.db"
        #   2. str() 确保值为字符串类型（虽然通常已经是字符串，但为了类型安全）
        #   3. self._base_dir / ... 使用 Path 的 / 运算符拼接绝对路径
        # 结果为 Path 对象，如 Path("D:/gacha-analyzer/data/gacha_records.db")
        path.parent.mkdir(parents=True, exist_ok=True)
        # 获取数据库文件路径的父目录并确保其存在
        # parents=True 递归创建不存在的父目录（如 data/ 不存在时也会创建）
        # exist_ok=True 如果目录已存在则不抛出异常
        # 数据库文件本身不会被创建，只是确保其所在目录已就绪
        return str(path)
        # 将 Path 对象转换为字符串返回。调用方通常需要字符串路径来执行文件操作

    @property
    def backup_dir(self):
        # backup_dir 是一个只读属性，返回备份目录的绝对路径（字符串类型）。
        # 用于自动备份和手动备份功能，存储数据库的备份文件。
        # 访问此属性时会自动确保备份目录存在。
        #
        # 返回值：
        #   字符串类型的备份目录绝对路径。例如 "D:/gacha-analyzer/data/backups"
        path = self._base_dir / str(self.get("backup_dir", self.DEFAULTS["backup_dir"]))
        # 拼接路径，逻辑与 db_path 相同：
        #   1. 获取配置值，不存在则使用默认值 "data/backups"
        #   2. 与项目根目录拼接成完整路径
        path.mkdir(parents=True, exist_ok=True)
        # 确保备份目录本身存在。与 db_path 的 .parent.mkdir 不同，
        # 这里是对 path 本身调用 mkdir，因为 backup_dir 就是一个目录路径而非文件路径
        # parents=True 和 exist_ok=True 的作用与上述相同
        return str(path)
        # 返回字符串格式的绝对路径

    @property
    def export_dir(self):
        # export_dir 是一个只读属性，返回导出目录的绝对路径（字符串类型）。
        # 用户导出的抽卡数据（CSV、Excel 等格式）会保存到此目录中。
        # 访问此属性时会自动确保导出目录存在。
        #
        # 返回值：
        #   字符串类型的导出目录绝对路径。例如 "D:/gacha-analyzer/data/exports"
        path = self._base_dir / str(self.get("export_dir", self.DEFAULTS["export_dir"]))
        # 拼接路径，逻辑与 db_path、backup_dir 相同：
        #   1. 获取配置值，不存在则使用默认值 "data/exports"
        #   2. 与项目根目录拼接成完整路径
        path.mkdir(parents=True, exist_ok=True)
        # 确保导出目录存在。与 backup_dir 相同，直接对路径本身创建目录
        return str(path)
        # 返回字符串格式的绝对路径

    def get_cache_path(self, game, region="cn"):
        # get_cache_path() 方法获取指定游戏和区服的缓存文件路径。
        # 缓存路径存储在配置字典的 cache_paths.{game}.{region} 层级中。
        # 该路径是相对于用户主目录（Home Directory）的相对路径，方法会自动拼接为绝对路径。
        #
        # 参数：
        #   game: 游戏标识符（字符串类型），例如 "genshin"（原神）、"sr"（崩坏：星穹铁道）、"zzz"（绝区零）
        #   region: 区服标识符（字符串类型），默认值为 "cn"（国服）。其他可能的值如 "os"（国际服）等
        #
        # 返回值：
        #   字符串类型的缓存文件绝对路径（基于用户主目录拼接）
        #   如果配置中不存在该路径，返回空字符串 ""
        #
        # 示例：
        #   config.get_cache_path("genshin", "cn") -> "C:/Users/username/miHoYo/原神"
        #   config.get_cache_path("genshin", "os") -> "C:/Users/username/AppData/LocalLow/..."
        #   config.get_cache_path("unknown_game") -> ""

        rel_path = self.get(f"cache_paths.{game}.{region}", "")
        # 使用 f-string 构建点号分隔的配置键，如 "cache_paths.genshin.cn"
        # 调用 get() 方法获取值，如果不存在则返回空字符串 ""
        # 注意：即使默认配置中没有 cache_paths 相关配置，也不会报错，只会返回空字符串

        if not rel_path:
            # 检查获取到的路径是否为空字符串（falsy 值）
            # 如果为空，说明配置中没有设置该游戏/区服的缓存路径
            return ""
            # 返回空字符串，表示未配置此游戏/区服的缓存路径

        return str(Path.home() / rel_path)
        # Path.home() 返回当前用户的主目录路径（如 "C:/Users/30982"）
        # / rel_path 使用 Path 的 / 运算符拼接相对路径，得到完整的绝对路径
        # str() 将 Path 对象转换为字符串返回
        # 最终结果如 "C:/Users/30982/miHoYo/原神"

    def get_request_interval(self):
        # get_request_interval() 方法获取 HTTP 请求之间的间隔时间（秒）。
        # 该值用于控制爬取抽卡记录时的请求频率，避免过于频繁的请求导致被 API 服务器限流。
        #
        # 返回值：
        #   浮点数类型的请求间隔（秒）。默认值为 1.0 秒。
        #   如果配置值无效（如非数字字符串），返回 DEFAULTS 中的默认值
        return self.get_float("request_interval", self.DEFAULTS["request_interval"])
        # 调用 get_float() 获取浮点数值：
        #   1. 尝试从配置中读取 "request_interval" 的值
        #   2. 如果配置不存在或值无法转换为浮点数，返回 DEFAULTS["request_interval"]（即 1.0）

    def get_request_timeout(self):
        # get_request_timeout() 方法获取 HTTP 请求的超时时间（秒）。
        # 如果服务器在指定时间内没有响应，请求会被视为超时失败并触发重试机制。
        #
        # 返回值：
        #   整数类型的超时时间（秒）。默认值为 15 秒。
        #   如果配置值无效（如非数字字符串），返回 DEFAULTS 中的默认值
        return self.get_int("request_timeout", self.DEFAULTS["request_timeout"])
        # 调用 get_int() 获取整数值：
        #   1. 尝试从配置中读取 "request_timeout" 的值
        #   2. 如果配置不存在或值无法转换为整数，返回 DEFAULTS["request_timeout"]（即 15）
