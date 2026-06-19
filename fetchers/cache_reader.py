"""缓存文件读取 - 从游戏缓存中提取 API URL

本模块负责从游戏客户端的本地缓存文件和日志文件中读取抽卡记录的 API URL。
支持的米哈游游戏包括原神(Genshin)、崩坏：星穹铁道(Star Rail)、绝区零(ZZZ)。
也支持库洛游戏的鸣潮(Wuthering Waves)。

工作原理：
1. 游戏运行时会将 HTTP 请求日志写入本地缓存文件（通常是 Chromium 风格的 webCaches）。
2. 本模块扫描这些缓存文件，用正则表达式匹配包含 getGachaLog 等关键字的 URL。
3. 同时也从游戏的 output_log.txt 等日志文件中尝试提取信息。

主要类 CacheReader 提供以下功能：
- 查找游戏安装路径（通过日志文件分析）
- 从缓存文件中提取抽卡 API URL
- 从 URL 中解析 authkey
- 从游戏文件中提取用户 UID 和昵称
- 检查 URL 是否过期
"""

# ==================== 标准库导入 ====================

import os  # 操作系统接口模块，用于文件路径操作、文件存在性检查、环境变量读取等
import re  # 正则表达式模块，用于从缓存文本中匹配和提取 URL 及关键信息
from pathlib import Path  # 面向对象的文件系统路径模块，提供跨平台的路径操作方法

# ==================== 类型标注导入 ====================

from typing import Optional, Tuple  # 类型提示：Optional 表示值可以是类型本身或 None；Tuple 表示元组

# ==================== 项目内部模块导入 ====================

from core.config import Config  # 项目核心配置类，负责管理配置文件路径、各游戏的缓存路径等


class CacheReader:
    """游戏缓存文件读取器

    该类封装了所有与缓存文件读取相关的逻辑，包括：
    - 从日志文件中定位游戏安装路径
    - 从 Chromium 风格的 web 缓存中提取抽卡 API URL
    - 解析 URL 参数（authkey、uid）
    - 从游戏本地文件中读取用户信息（UID、昵称）

    Attributes:
        self.config (Config): 配置管理实例，用于获取各游戏的日志/缓存文件路径。
    """

    def __init__(self):
        """初始化 CacheReader 实例

        创建一个 Config 实例并存储在 self.config 中。
        Config 类负责管理项目配置，包括各游戏在不同地区（国服/国际服）
        的日志文件路径、缓存文件路径等信息。
        """
        self.config = Config()  # 实例化 Config 类，后续方法通过 self.config 访问配置

    def find_game_path(self, game: str, region: str = "cn") -> str:
        """从日志文件中找到游戏安装路径

        通过分析游戏客户端输出的日志文件内容，使用正则表达式匹配
        游戏数据目录的路径。不同游戏的日志格式和路径模式各不相同。

        Args:
            game (str): 游戏标识符，可选值为 "genshin"（原神）、
                       "starrail"（星穹铁道）、"zzz"（绝区零）、
                       "wutheringwaves"（鸣潮）。
            region (str): 游戏地区，默认 "cn"（国服），
                         "os" 或其他值表示国际服。

        Returns:
            str: 游戏数据目录的完整路径（如 "E:/Games/YuanShen_Data"），
                 如果找不到则返回空字符串 ""。

        工作流程：
        1. 先通过 Config 获取默认的日志文件路径
        2. 如果路径不存在，尝试备选日志路径
        3. 读取日志文件内容（最多读取 8192 字节）
        4. 根据游戏类型使用不同的正则模式匹配路径
        """
        # 第一步：从配置中获取该游戏对应的日志文件路径
        # get_cache_path 返回一个文件系统路径字符串，指向游戏的日志文件
        log_path = self.config.get_cache_path(game, region)

        # 第二步：验证日志路径是否存在；如果不存在，尝试备选路径
        # os.path.exists() 检查文件或目录是否存在，不存在时返回 False
        if not log_path or not os.path.exists(log_path):
            # 调用私有方法获取备选日志文件路径列表
            # 备选路径通常包括 AppData 目录下的其他日志文件位置
            alt_paths = self._get_alternative_log_paths(game, region)

            # 遍历所有备选路径，找到第一个实际存在的文件
            for alt_path in alt_paths:
                if os.path.exists(alt_path):  # 检查备选路径是否存在
                    log_path = alt_path  # 找到有效路径，更新 log_path
                    break  # 找到后立即退出循环
            else:
                # for-else 结构：当 for 循环正常结束（未被 break）时执行
                # 即所有备选路径都不存在，无法找到日志文件
                return ""  # 返回空字符串表示未找到日志文件

        # 第三步：读取日志文件内容
        # 使用 try-except 包裹文件读取操作，防止文件权限、编码等问题导致崩溃
        try:
            # 以 UTF-8 编码打开文件，errors="ignore" 表示遇到无法解码的字节直接忽略
            # 这种方式可以容忍日志文件中偶尔出现的非 UTF-8 字节
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                # 读取前 8192 字节（8KB）的内容
                # 日志文件通常很大，但游戏路径信息一般出现在文件开头部分
                # 只读取一部分可以提高性能并减少内存占用
                content = f.read(8192)
        except Exception:
            # 捕获所有异常（文件被锁定、权限不足、磁盘故障等）
            # 读取失败时返回空字符串，不向上层抛出异常
            return ""

        # 第四步：根据游戏类型，使用对应的正则表达式从日志内容中提取路径

        if game == "genshin":
            # ---- 原神 (Genshin Impact) 的日志路径解析 ----

            # 主正则模式：匹配形如 "E:/path/to/Genshin Impact Game/YuanShen_Data" 的路径
            # 正则解析：
            #   ([A-Z]:/(?:[^:*?"<>|\n])+?)  - 捕获组1：匹配盘符+路径（如 E:/xxx）
            #     [A-Z]:  匹配盘符（A-Z 加冒号）
            #     /  匹配正斜杠（路径分隔符）
            #     (?:[^:*?"<>|\n])+?  非贪婪匹配路径中除非法字符外的所有字符
            #       这些非法字符是 Windows 文件名中不允许出现的字符
            #       +? 表示非贪婪模式，尽可能少地匹配，以便后续的 / 能正确匹配
            #   /(YuanShen_Data|GenshinImpact_Data)  - 捕获组2：匹配游戏数据目录名
            #     中文客户端使用 YuanShen_Data，国际服使用 GenshinImpact_Data
            match = re.search(
                r'([A-Z]:/(?:[^:*?"<>|\n])+?)/(YuanShen_Data|GenshinImpact_Data)',
                content
            )
            if match:
                # match.group(1) 返回第一个捕获组（基础安装路径）
                # .strip() 去除路径两端可能存在的空白字符
                base = match.group(1).strip()
                # match.group(2) 返回第二个捕获组（数据目录名，如 YuanShen_Data）
                data_dir = match.group(2)
                # 拼接完整路径并返回，例如 "E:/Games/Genshin Impact Game/YuanShen_Data"
                return base + "/" + data_dir

            # ---- 备用正则模式 ----
            # 当主模式匹配失败时，使用以下备选模式
            # 备选模式列表，按优先级从高到低排列
            patterns = [
                # 备选模式1：匹配 "Warmup file" 日志行中的路径
                # "Warmup file E:/path/YuanShen_Data" 格式
                r'Warmup file \w+:(.+?)(YuanShen_Data|GenshinImpact_Data)',
                # 备选模式2：匹配 "Loading player data from" 日志行中的路径
                r'Loading player data from (.+?)(?:/|$)',
            ]

            # 依次尝试每个备选模式
            for pattern in patterns:
                match = re.search(pattern, content)
                if match:
                    base = match.group(1).strip()  # 提取基础路径
                    # 根据日志中实际出现的数据目录名来确定使用哪个
                    if "YuanShen_Data" in content:
                        return base + "YuanShen_Data"  # 国服
                    elif "GenshinImpact_Data" in content:
                        return base + "GenshinImpact_Data"  # 国际服
                    else:
                        # 默认使用国服路径名（更常见的使用场景）
                        return base + "YuanShen_Data"

        elif game == "starrail":
            # ---- 崩坏：星穹铁道 (Honkai: Star Rail) 的日志路径解析 ----

            # 匹配日志中 "Loading player data from" 行中的路径
            # 正则解析：
            #   Loading player data from  - 固定的前缀文本
            #   (.+?)  - 非贪婪捕获：匹配到 /Game/StarRail_Data 之前的所有字符
            #   /Game/StarRail_Data  - 星穹铁道特有的数据目录路径结构
            match = re.search(
                r'Loading player data from (.+?)/Game/StarRail_Data',
                content
            )
            if match:
                # 提取基础路径并拼接完整路径返回
                # 例如返回 "E:/Games/Star Rail Game/Game/StarRail_Data"
                return match.group(1) + "/Game/StarRail_Data"

        elif game == "zzz":
            # ---- 绝区零 (Zenless Zone Zero) 的日志路径解析 ----

            # 模式1：从 JSON 格式的 reportPath 字段中提取路径
            # 绝区零日志中包含 reportPath 字段，存储游戏数据目录路径
            # 正则解析：
            #   reportPath":"  - 匹配 JSON 字段名和冒号引号
            #   (.+?ZenlessZoneZero_Data)  - 捕获到以 ZenlessZoneZero_Data 结尾的路径
            #   "  - 结尾的引号
            match = re.search(
                r'reportPath":"(.+?ZenlessZoneZero_Data)',
                content
            )
            if match:
                # 日志中的路径可能使用反斜杠（Windows风格），需要转换为正斜杠
                # replace("\\\\", "/") 将双重转义的反斜杠替换为正斜杠
                # replace("\\", "/") 将单个反斜杠替换为正斜杠
                # 这样可以确保路径在所有平台上都能正确使用
                return match.group(1).replace("\\\\", "/").replace("\\", "/")

            # 模式2：从 "Discovering subsystems at path" 日志行中提取路径
            match = re.search(
                r'Discovering subsystems at path (.+?)(?:/|$)',
                content
            )
            if match:
                # .strip() 去除路径末尾的空白字符
                return match.group(1).strip()

        elif game == "wutheringwaves":
            # ---- 鸣潮 (Wuthering Waves) 的路径解析 ----
            # 鸣潮的日志文件位于游戏安装目录的 Client/Saved/Logs/Client.log
            # 通过日志文件的位置反推游戏数据目录

            # Path(log_path).parent 获取日志文件的父目录（即 Logs/ 目录）
            log_dir = Path(log_path).parent  # Logs/ 目录
            # 再取父目录得到 Saved/ 目录（游戏数据通常存储在这里）
            saved_dir = log_dir.parent  # Saved/ 目录

            # 检查 Saved/ 目录是否存在
            if saved_dir.exists():
                # 将 Path 对象转换为字符串并返回
                return str(saved_dir)

        # 所有匹配模式都未成功，返回空字符串
        return ""

    def _get_alternative_log_paths(self, game: str, region: str) -> list:
        """获取其他可能的日志文件路径

        当通过 Config 获取的默认日志路径不存在时，本方法提供
        各游戏在不同地区的备选日志文件路径列表。

        Args:
            game (str): 游戏标识符
            region (str): 游戏地区（"cn" 国服 或其他国际服标识）

        Returns:
            list: 备选日志文件路径的字符串列表（可能为空列表）。

        说明：
        - 原神的日志存放在 AppData/LocalLow 目录下
        - 鸣潮的日志在游戏安装目录中，需要通过注册表或磁盘搜索来定位
        """
        paths = []  # 初始化空列表，用于存储找到的备选路径

        if game == "genshin":
            # ---- 原神的备选日志路径 ----
            if region == "cn":
                # 国服原神的日志文件位置（miHoYo 发行）
                paths = [
                    # 原神国服主日志文件
                    str(Path.home() / "AppData/LocalLow/miHoYo/原神/LocalLog.log"),
                    # 原神国服输出日志文件
                    str(Path.home() / "AppData/LocalLow/miHoYo/原神/output_log.txt"),
                ]
            else:
                # 国际服原神的日志文件位置（Cognosphere/天空之琴发行）
                paths = [
                    # 原神国际服主日志文件
                    str(Path.home() / "AppData/LocalLow/Cognosphere/Genshin Impact/LocalLog.log"),
                    # 原神国际服输出日志文件
                    str(Path.home() / "AppData/LocalLow/Cognosphere/Genshin Impact/output_log.txt"),
                ]
        elif game == "wutheringwaves":
            # ---- 鸣潮的备选日志路径 ----
            # 鸣潮的日志文件不在 AppData 中，而是在游戏安装目录的
            # Client/Saved/Logs/Client.log
            # 需要通过多种方式查找游戏安装位置

            # 策略1：通过 Windows 注册表查找已安装程序的安装路径
            try:
                # 导入 Windows 注册表操作模块
                # winreg 只能在 Windows 系统上使用
                import winreg

                # 遍历两个注册表根键：HKEY_LOCAL_MACHINE（所有用户）和 HKEY_CURRENT_USER（当前用户）
                for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
                    # 遍历两个卸载信息子键路径
                    # 一个是原生路径，另一个是 WOW6432Node（32位程序在64位系统上的映射）
                    for subkey in [
                        r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                        r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
                    ]:
                        try:
                            # 打开注册表子键
                            key = winreg.OpenKey(hive, subkey)
                            i = 0  # 枚举索引，从 0 开始

                            # 无限循环枚举注册表子键下的所有条目
                            while True:
                                try:
                                    # EnumKey 枚举指定索引处的子键名称
                                    sub = winreg.EnumKey(key, i)
                                    # 打开枚举到的子键，获取其详细信息
                                    sub_k = winreg.OpenKey(key, sub)

                                    try:
                                        # 读取 DisplayName（显示名称）值
                                        # QueryValueEx 返回一个元组 (value, type)
                                        name = winreg.QueryValueEx(sub_k, "DisplayName")[0]

                                        # 检查是否是鸣潮（通过英文名或中文名匹配）
                                        if "wuthering" in name.lower() or name == "鸣潮":
                                            loc = ""  # 安装位置变量

                                            try:
                                                # 尝试读取 InstallLocation（安装位置）值
                                                loc = winreg.QueryValueEx(sub_k, "InstallLocation")[0]
                                            except Exception:
                                                # 如果没有 InstallLocation 值，保持为空
                                                pass

                                            # 验证安装位置是否有效（目录存在）
                                            if loc and os.path.isdir(loc):
                                                # 尝试路径1：安装在 "Wuthering Waves Game" 子目录下
                                                log = Path(loc) / "Wuthering Waves Game" / "Client" / "Saved" / "Logs" / "Client.log"
                                                if log.exists():
                                                    paths.append(str(log))
                                                    return paths  # 找到后立即返回

                                                # 尝试路径2：直接在安装目录下
                                                log2 = Path(loc) / "Client" / "Saved" / "Logs" / "Client.log"
                                                if log2.exists():
                                                    paths.append(str(log2))
                                                    return paths  # 找到后立即返回
                                    finally:
                                        # 无论 sub_k 操作是否成功，都关闭注册表键
                                        # 这是良好的资源管理实践，防止注册表句柄泄漏
                                        winreg.CloseKey(sub_k)

                                    i += 1  # 移动到下一个条目

                                except OSError:
                                    # OSError 表示没有更多子键可枚举（索引越界）
                                    # 正常退出循环
                                    break

                            # 遍历完所有子键后，关闭当前注册表键
                            winreg.CloseKey(key)
                        except Exception:
                            # 捕获打开或操作注册表键时的所有异常
                            # 继续尝试下一个子键路径
                            pass
            except Exception:
                # 捕获导入 winreg 或注册表操作的整体异常
                # 非 Windows 系统或注册表访问受限时会触发
                pass

            # ---- 策略2：注册表中未找到，遍历所有磁盘搜索游戏安装目录 ----
            import string as _string  # 导入字符串模块，用于获取字母表（A-Z）

            search_dirs = []  # 存储搜索到的可能的游戏安装目录

            # 遍历所有可能的磁盘盘符（A-Z）
            for letter in _string.ascii_uppercase:
                # 构造磁盘根路径，如 "C:/"、"D:/" 等
                drive = Path(f"{letter}:/")

                # 检查磁盘是否存在（有些盘符可能没有对应的物理磁盘）
                if not drive.exists():
                    continue  # 跳过不存在的磁盘

                # 在每个磁盘上搜索常见的游戏安装子目录
                for subdir in ["Program Files", "Program File", "Program Files (x86)",
                               "Games", "Game", ""]:
                    try:
                        # 构造搜索基础路径
                        # subdir 为空字符串时表示在磁盘根目录搜索
                        base = drive / subdir if subdir else drive

                        # 验证路径是否存在且是目录
                        if not base.exists() or not base.is_dir():
                            continue  # 跳过不存在的路径或非目录

                        # 遍历基础目录下的所有条目
                        for p in base.iterdir():
                            if not p.is_dir():
                                continue  # 跳过文件，只处理目录

                            # 将目录名转为小写进行不区分大小写的匹配
                            name_lower = p.name.lower()
                            if "wuthering" in name_lower or "鸣潮" in name_lower:
                                # 匹配到游戏安装目录，添加到搜索列表
                                search_dirs.append(p)
                    except (PermissionError, OSError):
                        # 捕获权限不足或系统错误（如某些受保护的系统目录）
                        continue  # 跳过，继续搜索其他目录

            # 对搜索到的每个候选目录，尝试查找日志文件
            for base in search_dirs:
                # 构造日志文件路径
                log = base / "Wuthering Waves Game" / "Client" / "Saved" / "Logs" / "Client.log"
                if log.exists():
                    paths.append(str(log))
                    return paths  # 找到后立即返回

        # 返回找到的备选路径列表（可能为空）
        return paths

    def extract_url(self, game: str, region: str = "cn") -> Optional[str]:
        """从缓存文件中提取抽卡 API URL

        这是提取抽卡 URL 的主入口方法。它会按优先级尝试多种策略：
        1. 对米哈游游戏，先尝试从日志文件直接读取 URL
        2. 通过日志文件找到游戏安装路径
        3. 在安装路径下按预定义的缓存文件相对路径逐一查找
        4. 如果预定义路径都找不到，进行全目录搜索

        Args:
            game (str): 游戏标识符。
            region (str): 游戏地区，默认 "cn"。

        Returns:
            Optional[str]: 找到的抽卡 API URL，找不到则返回 None。
                          URL 通常形如：
                          "https://webstatic.mihoyo.com/hk4e_global/e20210928calculate..."
        """
        # ---- 第一步：对米哈游游戏，优先从日志文件直接读取 URL ----
        # 米哈游游戏包括原神、星穹铁道、绝区零
        if game in ("genshin", "starrail", "zzz"):
            # 获取该游戏的日志文件路径
            log_path = self.config.get_cache_path(game, region)

            # 验证路径有效且文件存在
            if log_path and os.path.exists(log_path):
                # 调用 _parse_cache_file 解析日志文件，提取 URL
                # 这种方式比查找 webCaches 更快更直接
                url = self._parse_cache_file(log_path, game)
                if url:  # 如果成功提取到 URL
                    return url  # 直接返回，不需要继续查找缓存文件

        # ---- 第二步：尝试通过日志文件找到游戏安装路径 ----
        game_path = self.find_game_path(game, region)

        if not game_path:
            # 日志文件中未找到路径，尝试使用硬编码的常见安装路径
            game_path = self._find_game_data_dir(game, region)
            if not game_path:
                # 所有方式都失败，返回 None
                return None

        # ---- 第三步：按预定义的缓存文件相对路径逐一查找 ----
        # 获取该游戏所有可能的缓存文件相对路径列表
        cache_paths = self._get_cache_data_paths(game)

        for cache_rel in cache_paths:
            # 拼接完整的缓存文件路径
            cache_file = os.path.join(game_path, cache_rel)
            if os.path.exists(cache_file):  # 检查文件是否存在
                # 尝试解析该缓存文件提取 URL
                url = self._parse_cache_file(cache_file, game)
                if url:
                    return url  # 成功提取到 URL

        # ---- 第四步：预定义路径都未找到，进行全目录搜索 ----
        # 递归搜索 webCaches 目录下的所有缓存文件
        return self._search_cache_files(game_path, game)

    def _find_game_data_dir(self, game: str, region: str) -> str:
        """直接查找游戏数据目录（硬编码的常见安装路径）

        当无法从日志文件中解析出路径时，使用预定义的常见安装路径列表
        进行暴力搜索。这些路径覆盖了大多数用户的默认安装位置。

        Args:
            game (str): 游戏标识符。
            region (str): 游戏地区。

        Returns:
            str: 游戏数据目录路径，找不到则返回空字符串 ""。

        说明：
        - 路径中包含 miHoYo Launcher/games/ 结构，这是米哈游启动器的默认安装方式
        - 不同盘符（C/D/E）和用户目录（~）都被覆盖
        """
        if game == "genshin":
            # ---- 原神的常见安装路径 ----
            if region == "cn":
                # 国服原神常见安装路径列表
                possible_paths = [
                    "E:/miHoYo Launcher/games/Genshin Impact Game",  # E盘（常见）
                    "D:/miHoYo Launcher/games/Genshin Impact Game",  # D盘
                    "C:/Program Files/Genshin Impact",  # C盘Program Files
                    str(Path.home() / "miHoYo Launcher/games/Genshin Impact Game"),  # 用户主目录
                ]
            else:
                # 国际服原神常见安装路径列表
                possible_paths = [
                    "E:/miHoYo Launcher/games/Genshin Impact Game",
                    "D:/miHoYo Launcher/games/Genshin Impact Game",
                    "C:/Program Files/Genshin Impact",
                ]

            # 遍历所有可能的路径
            for path in possible_paths:
                # 检查国服数据目录 YuanShen_Data 是否存在
                data_dir = os.path.join(path, "YuanShen_Data")
                if os.path.exists(data_dir):
                    return data_dir  # 国服数据目录存在，返回

                # 检查国际服数据目录 GenshinImpact_Data 是否存在
                data_dir = os.path.join(path, "GenshinImpact_Data")
                if os.path.exists(data_dir):
                    return data_dir  # 国际服数据目录存在，返回

        elif game == "starrail":
            # ---- 星穹铁道的常见安装路径 ----
            possible_paths = [
                "E:/miHoYo Launcher/games/Star Rail Game",
                "D:/miHoYo Launcher/games/Star Rail Game",
                str(Path.home() / "miHoYo Launcher/games/Star Rail Game"),
            ]
            for path in possible_paths:
                # 星穹铁道只有 StarRail_Data 这一个数据目录名
                data_dir = os.path.join(path, "StarRail_Data")
                if os.path.exists(data_dir):
                    return data_dir

        elif game == "zzz":
            # ---- 绝区零的常见安装路径 ----
            possible_paths = [
                "E:/miHoYo Launcher/games/ZenlessZoneZero Game",
                "D:/miHoYo Launcher/games/ZenlessZoneZero Game",
                str(Path.home() / "miHoYo Launcher/games/ZenlessZoneZero Game"),
            ]
            for path in possible_paths:
                # 绝区零数据目录名为 ZenlessZoneZero_Data
                data_dir = os.path.join(path, "ZenlessZoneZero_Data")
                if os.path.exists(data_dir):
                    return data_dir

        # 所有路径都未找到
        return ""

    def _search_cache_files(self, game_path: str, game: str) -> Optional[str]:
        """搜索所有可能的缓存文件

        当预定义的缓存路径都不存在时，递归遍历 webCaches 目录下的
        所有版本目录，查找可用的缓存数据文件。

        Args:
            game_path (str): 游戏数据目录的完整路径。
            game (str): 游戏标识符。

        Returns:
            Optional[str]: 提取到的抽卡 API URL，找不到则返回 None。

        文件结构说明：
        webCaches/
        ├── 2.49.0.0/        # Chromium 缓存版本号
        │   └── Cache/
        │       └── Cache_Data/
        │           └── data_2  # 实际的缓存数据文件
        ├── 2.47.0.0/
        └── ...
        """
        # 构造 webCaches 目录的完整路径
        web_cache_dir = os.path.join(game_path, "webCaches")

        # 检查 webCaches 目录是否存在
        if not os.path.exists(web_cache_dir):
            return None  # 目录不存在，无法继续搜索

        # os.listdir() 列出目录下的所有条目名称
        # sorted(..., reverse=True) 按版本号降序排列（最新的版本优先）
        # 因为版本号是字符串，降序排列时 "2.49.0.0" > "2.47.0.0" 正好是我们需要的顺序
        for version_dir in sorted(os.listdir(web_cache_dir), reverse=True):
            # 构造具体的缓存数据文件路径
            # 结构：webCaches/{版本号}/Cache/Cache_Data/data_2
            cache_file = os.path.join(
                web_cache_dir, version_dir, "Cache", "Cache_Data", "data_2"
            )

            if os.path.exists(cache_file):
                # 尝试解析该缓存文件提取 URL
                url = self._parse_cache_file(cache_file, game)
                if url:
                    return url  # 成功提取到 URL

        # 所有版本的缓存文件都未能提取到有效的 URL
        return None

    def _get_cache_data_paths(self, game: str) -> list:
        """获取各游戏的缓存文件相对路径列表

        返回游戏数据目录下的缓存文件相对路径，按照从新到旧的顺序排列。
        这些路径对应 Chromium 引擎不同版本的缓存格式。

        Args:
            game (str): 游戏标识符。

        Returns:
            list: 缓存文件相对路径的字符串列表。

        说明：
        - 米哈游游戏使用 Chromium 内嵌浏览器，缓存文件在 webCaches 目录下
        - 鸣潮不使用 Chromium，其 URL 存储在日志文件中
        - 不同版本号对应不同的 Chromium 缓存版本，新版本通常包含最新的请求记录
        """
        if game == "wutheringwaves":
            # 鸣潮的 URL 存储在游戏日志文件中，不在 Chromium 缓存中
            # 返回日志文件的相对路径
            return ["Logs/Client.log"]

        # 米哈游游戏的 Chromium 缓存文件路径列表
        # 按版本号从新到旧排列，优先检查较新的版本
        paths = [
            "../webCaches/2.49.0.0/Cache/Cache_Data/data_2",  # 最新版本
            "../webCaches/2.47.0.0/Cache/Cache_Data/data_2",
            "../webCaches/2.45.1.0/Cache/Cache_Data/data_2",
            "../webCaches/2.43.0.0/Cache/Cache_Data/data_2",
            "../webCaches/2.24.0.0/Cache/Cache_Data/data_2",
            "../webCaches/2.22.0.0/Cache/Cache_Data/data_2",
            "../webCaches/2.20.0.0/Cache/Cache_Data/data_2",
            "../webCaches/2.18.0.0/Cache/Cache_Data/data_2",  # 较旧版本
        ]
        return paths

    def _parse_cache_file(self, filepath: str, game: str) -> Optional[str]:
        """解析缓存文件，提取抽卡 API URL

        这是核心的 URL 提取方法。它读取缓存文件（二进制格式），
        将其解码为文本，然后用正则表达式搜索包含抽卡 API 关键字的 URL。

        Args:
            filepath (str): 缓存文件的完整路径。
            game (str): 游戏标识符，用于选择合适的正则匹配策略。

        Returns:
            Optional[str]: 提取到的完整 URL 字符串，找不到则返回 None。

        文件格式说明：
        - Chromium 缓存文件（data_2）是二进制格式，混合了数据和元数据
        - 但 HTTP URL 通常以纯文本形式嵌入在二进制数据中
        - 所以可以直接以二进制读取后解码为 UTF-8 文本来搜索
        """
        # ---- 第一步：读取并解码缓存文件 ----
        try:
            # 以二进制模式（"rb"）打开文件
            # 使用二进制模式是因为缓存文件包含非文本数据
            with open(filepath, "rb") as f:
                data = f.read()  # 读取整个文件内容为 bytes 对象

            # 将二进制数据解码为 UTF-8 文本
            # errors="ignore" 遇到无法解码的字节直接跳过（缓存文件中常有非 UTF-8 数据）
            content = data.decode("utf-8", errors="ignore")
        except Exception:
            # 文件读取或解码失败（文件损坏、权限问题等）
            return None

        # ---- 第二步：根据游戏类型选择匹配策略 ----

        if game == "wutheringwaves":
            # ---- 鸣潮的 URL 提取 ----
            # 鸣潮的 URL 存储在日志的 OpenWebView 操作中
            # 格式为 JSON: {"url":"https://aki-gm-resources.aki-game.com/..."}
            # 正则解析：
            #   "url":"  - JSON 字段名
            #   (https://aki-gm-resources\.aki-game\.com/aki/gacha/index\.html#/record\?[^"]+)
            #     - 捕获完整的鸣潮抽卡记录页面 URL
            #     \?  匹配问号（URL 参数的开始）
            #     [^"]+  匹配非引号的所有字符（URL 参数部分）
            matches = re.findall(
                r'"url":"(https://aki-gm-resources\.aki-game\.com/aki/gacha/index\.html#/record\?[^"]+)"',
                content
            )
            if matches:
                # 取最后一个匹配（最新的一条记录）
                # 将 JSON 转义的 & 符号还原：& → &
                return matches[-1].replace("\\u0026", "&")
            return None  # 未找到匹配

        # ---- 米哈游游戏的 URL 提取 ----
        # 使用多个正则模式，从宽到窄匹配，确保覆盖不同版本的日志格式

        # 正则模式列表，按匹配精度从高到低排列
        patterns = [
            # 模式1：精确匹配包含 getGachaLog 的 URL
            # 这是最精确的匹配，直接对应抽卡记录查询 API
            # 正则解析：
            #   https?://  匹配 http:// 或 https://
            #   [^\x00-\x1f]+  匹配 URL 主体（排除控制字符）
            #   getGachaLog  精确匹配 API 端点名称
            #   [^\x00-\x1f]*  匹配 URL 剩余部分（查询参数等）
            r'https?://[^\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f]+getGachaLog[^\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f]*',
            # 模式2：匹配包含 getGacha 的 URL（比模式1更宽松）
            # 覆盖 API 名称可能变化的情况
            r'https?://[^\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f]+getGacha[^\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f]*',
            # 模式3：最宽松的匹配，只要 URL 包含 gacha 和 authkey 参数
            # 覆盖各种抽卡相关的 API 端点
            r'https?://[^\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f]+gacha[^\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f]*authkey=[^\x00\x01\x02\x03\x04\x05\x06\x07\x08\x09\x0a\x0b\x0c\x0d\x0e\x0f]*',
        ]

        # 依次尝试每个正则模式
        for pattern in patterns:
            # findall 返回所有匹配结果的列表
            matches = re.findall(pattern, content)
            if matches:
                # 取最后一个匹配（最新/最后的请求通常是用户最近的抽卡记录）
                url = matches[-1]

                # 清理 URL 中可能残留的控制字符
                # [\x00-\x1f\x7f-\x9f] 匹配所有 ASCII 控制字符和扩展控制字符
                # 这些字符是二进制数据中的噪声，不是有效 URL 的一部分
                url = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', url)

                return url  # 返回清理后的 URL

        # 所有正则模式都未匹配到有效的 URL
        return None

    def extract_authkey(self, url: str) -> Optional[str]:
        """从 URL 中提取 authkey（认证密钥）

        authkey 是米哈游抽卡 API 的认证参数，用于验证请求的合法性。
        它通常作为 URL 查询参数出现，格式为 authkey=xxxxxxxxxxxxx。

        Args:
            url (str): 完整的抽卡 API URL 字符串。

        Returns:
            Optional[str]: authkey 的值，提取失败则返回 None。

        示例：
        输入: "https://webstatic.mihoyo.com/hk4e/...?authkey=abc123&game_biz=..."
        输出: "abc123"
        """
        # 正则匹配 authkey 参数的值
        # authkey=  匹配参数名
        # ([^&]+)  捕获组：匹配所有非 & 字符（即参数值，直到遇到下一个参数）
        match = re.search(r'authkey=([^&]+)', url)
        if match:
            # 返回 authkey 的值
            return match.group(1)
        return None  # URL 中不包含 authkey 参数

    def extract_uid(self, game: str, region: str = "cn") -> Optional[str]:
        """从游戏文件中提取用户 UID

        UID（用户唯一标识符）存储在游戏本地的 UidInfo.txt 文件中。
        不同游戏和地区的 UidInfo.txt 文件位置各不相同。

        Args:
            game (str): 游戏标识符。
            region (str): 游戏地区，默认 "cn"。

        Returns:
            Optional[str]: 用户的数字 UID 字符串，提取失败则返回 None。

        UID 文件位置规则：
        - 路径格式：~/AppData/LocalLow/{发行商}/{游戏名}/UidInfo.txt
        - 国服发行商为 miHoYo，国际服为 Cognosphere
        """
        # 根据游戏和地区确定 UidInfo.txt 文件的位置
        if game == "genshin":
            if region == "cn":
                # 原神国服 UID 文件路径
                uid_file = Path.home() / "AppData/LocalLow/miHoYo/原神/UidInfo.txt"
            else:
                # 原神国际服 UID 文件路径
                uid_file = Path.home() / "AppData/LocalLow/Cognosphere/Genshin Impact/UidInfo.txt"
        elif game == "starrail":
            if region == "cn":
                # 星穹铁道国服 UID 文件路径（注意游戏名称包含冒号）
                uid_file = Path.home() / "AppData/LocalLow/miHoYo/崩坏：星穹铁道/UidInfo.txt"
            else:
                # 星穹铁道国际服 UID 文件路径
                uid_file = Path.home() / "AppData/LocalLow/Cognosphere/Star Rail/UidInfo.txt"
        elif game == "zzz":
            if region == "cn":
                # 绝区零国服 UID 文件路径
                uid_file = Path.home() / "AppData/LocalLow/miHoYo/绝区零/UidInfo.txt"
            else:
                # 绝区零国际服 UID 文件路径
                uid_file = Path.home() / "AppData/LocalLow/Cognosphere/ZZZ/UidInfo.txt"
        else:
            # 不支持的游戏类型（如鸣潮），返回 None
            return None

        # 检查 UID 文件是否存在
        if uid_file.exists():
            try:
                # 以 UTF-8 编码读取 UID 文件
                with open(uid_file, "r", encoding="utf-8") as f:
                    # 读取全部内容并去除首尾空白字符
                    uid = f.read().strip()

                    # 验证 UID 是否有效：
                    # - 非空字符串
                    # - 纯数字（UID 应该只包含数字）
                    if uid and uid.isdigit():
                        return uid  # 返回有效的 UID
            except Exception:
                # 文件读取失败（权限不足、文件损坏等）
                pass  # 静默失败，继续执行

        # 文件不存在或读取失败
        return None

    def extract_nickname(self, game: str, region: str = "cn") -> Optional[str]:
        """从游戏日志文件中提取用户昵称

        通过分析游戏日志文件内容，使用正则表达式匹配玩家登录时
        记录的昵称信息。

        Args:
            game (str): 游戏标识符。
            region (str): 游戏地区，默认 "cn"。

        Returns:
            Optional[str]: 用户昵称字符串，提取失败则返回 None。

        注意：
        - 目前仅支持原神和星穹铁道的昵称提取
        - 鸣潮和绝区零的日志中可能没有明确的昵称记录
        """
        # 获取该游戏的日志文件路径
        log_path = self.config.get_cache_path(game, region)

        # 验证日志路径有效且文件存在
        if not log_path or not os.path.exists(log_path):
            return None  # 日志文件不存在

        try:
            # 以 UTF-8 编码读取日志文件，忽略无法解码的字符
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                # 只读取前 8192 字节（昵称信息通常在日志文件开头）
                content = f.read(8192)

            # 根据游戏类型使用不同的昵称匹配模式
            if game == "genshin":
                # ---- 原神昵称提取 ----
                # 原神日志中玩家登录时会记录 "Player xxx login" 格式的行
                # 正则解析：
                #   Player  - 固定前缀
                #   \s+     - 一个或多个空白字符
                #   (\w+)   - 捕获组：一个或多个字母数字下划线字符（即昵称）
                #   \s+     - 一个或多个空白字符
                #   login   - 固定后缀
                import re  # 正则模块（此处重复导入，但不影响功能）
                match = re.search(r'Player\s+(\w+)\s+login', content)
                if match:
                    return match.group(1)  # 返回捕获的昵称

            elif game == "starrail":
                # ---- 星穹铁道昵称提取 ----
                # 使用与原神相同的正则模式
                import re
                match = re.search(r'Player\s+(\w+)\s+login', content)
                if match:
                    return match.group(1)  # 返回捕获的昵称

        except Exception:
            # 捕获所有异常，静默失败
            pass

        # 未找到昵称信息
        return None

    def is_url_expired(self, url: str) -> bool:
        """检查抽卡 URL 是否已过期

        米哈游的 authkey 大约 24 小时后会过期。本方法通过发送一个
        最小化的 HTTP 请求来验证 URL 是否仍然有效。

        Args:
            url (str): 要检查的抽卡 API URL。

        Returns:
            bool: 如果 URL 已过期或请求失败返回 True；有效返回 False。

        检测原理：
        - 发送一个只请求 1 条记录的最小化请求
        - 如果返回的 retcode（返回码）不为 0，说明 URL 已失效
        - 正常情况下 retcode 为 0 表示请求成功
        """
        try:
            # 导入 requests HTTP 客户端库
            import requests

            # 发送 GET 请求，只请求 1 条记录以最小化数据传输
            # params 会自动拼接到 URL 末尾：?page=1&size=1
            resp = requests.get(url, params={"page": 1, "size": 1}, timeout=10)

            # 将响应内容解析为 JSON 格式
            data = resp.json()

            # 检查返回码：
            # retcode == 0 表示请求成功（URL 有效）
            # retcode != 0 表示请求失败（URL 过期或无效）
            # data.get("retcode") 安全地获取 "retcode" 字段，不存在时返回 None
            return data.get("retcode") != 0

        except Exception:
            # 捕获所有异常：
            # - 网络连接失败（DNS 解析失败、网络断开等）
            # - 请求超时
            # - 响应内容不是有效的 JSON
            # - requests 库未安装
            # 异常情况下保守地认为 URL 已过期
            return True
