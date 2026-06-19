"""明日方舟抽卡记录获取器

本模块实现了明日方舟（Arknights）游戏的抽卡记录获取功能。
支持以下三种Token获取方式：
1. 从游戏日志文件 HGWebview.log 中自动提取 u8_token
2. 通过鹰角账号 Token（hg_token）交换获取 u8_token
3. 用户手动粘贴包含 u8_token 的 URL

API基础地址: https://ak-webview.hypergryph.com/api
主要接口:
- /gacha/cate: 获取卡池列表
- /gacha/history: 获取抽卡历史记录（分页）

作者: gacha-analyzer 开发团队
"""

import os  # 操作系统接口模块，用于获取环境变量（如 SystemRoot）
import re  # 正则表达式模块，用于从日志文件中提取 token
import sys  # Python解释器相关变量和函数（备用导入）
import time  # 时间模块，用于时间戳转换和请求限流
import subprocess  # 子进程模块，用于执行系统命令（如 ipconfig /flushdns）
from pathlib import Path  # 路径处理模块，提供面向对象的文件路径操作
from typing import List, Optional  # 类型提示，List用于列表类型，Optional用于可选值
from urllib.parse import unquote  # URL解码函数，用于解码token中的特殊字符
from fetchers.base import BaseFetcher, FetcherError  # 基础获取器类和自定义异常类
from core.models import GachaRecord, ARKNIGHTS_POOL_MECHANIC_MAP, ARKNIGHTS_MECHANIC_TO_GROUP  # 数据模型和卡池映射表


import logging  # 日志模块，用于记录程序运行信息

# 创建当前模块的日志记录器
# __name__ 会被解析为 "fetchers.hypergryph.arknights"
# 这样可以在配置中统一控制日志级别
logger = logging.getLogger(__name__)


class ArknightsFetcher(BaseFetcher):
    """明日方舟抽卡记录获取器

    继承自 BaseFetcher 基类，实现了明日方舟特有的抽卡记录获取逻辑。
    主要功能：
    - 支持从日志文件自动提取 token
    - 支持通过鹰角账号 token 交换获取 u8_token
    - 支持从官方 API 获取卡池列表和抽卡历史
    - 自动处理分页，获取所有抽卡记录
    - 支持多种卡池类型识别（标准/中坚/限定）

    属性:
        API_BASE: 官方 API 基础地址
        _detected_uid: 通过账号交换检测到的用户UID（实例变量）
    """

    # 明日方舟官方 Webview API 基础地址
    # 所有 API 请求都会基于此地址发起
    # 例如: https://ak-webview.hypergryph.com/api/gacha/cate
    API_BASE = "https://ak-webview.hypergryph.com/api"

    def get_game_name(self) -> str:
        """获取游戏名称

        返回:
            str: 游戏的中文名称 "明日方舟"

        说明:
            此方法重写自 BaseFetcher 基类，用于在 UI 和日志中显示游戏名称。
            返回值会被用于构造文件名、数据库记录等场景。
        """
        return "明日方舟"

    def get_supported_pools(self) -> List[str]:
        """获取支持的卡池类型列表

        返回:
            List[str]: 支持的卡池类型标识符列表
                - "standard": 标准寻访（包括双UP、单UP、联合行动等）
                - "kernel": 中坚寻访（常驻池）
                - "limited": 限定寻访（限时池、联动池）

        说明:
            此方法定义了该获取器支持的卡池分类，用于：
            1. UI 层面显示可选的卡池过滤器
            2. 数据库查询时的卡池类型筛选
            3. 抽卡统计时的分组依据
        """
        return ["standard", "kernel", "limited"]

    @staticmethod
    def _cleanup_hosts():
        """清理 hosts 文件中可能残留的代理条目

        功能说明:
            在启动时调用，清理之前运行代理服务器时可能遗留的 hosts 修改。
            代理服务器会将 ak-webview.hypergryph.com 指向 127.0.0.1，
            如果程序异常退出，hosts 文件可能不会被还原，导致后续请求失败。

        实现逻辑:
            1. 读取系统 hosts 文件
            2. 查找包含特定标记 "# gacha-analyzer-arknights-proxy" 的行
            3. 如果找到，删除这些行并刷新 DNS 缓存

        异常处理:
            整个操作用 try-except 包裹，即使失败也不影响主流程。
            最常见的异常是权限不足（需要管理员权限修改 hosts 文件）。

        注意:
            - 此方法是静态方法，不需要实例即可调用
            - hosts 文件路径: C:\Windows\System32\drivers\etc\hosts
            - 修改 hosts 文件需要管理员权限
        """
        # 定义标记字符串，用于识别本程序添加的 hosts 条目
        # 使用唯一标记避免误删其他程序的 hosts 条目
        hosts_marker = "# gacha-analyzer-arknights-proxy"

        # 构造 hosts 文件的完整路径
        # 优先使用环境变量 SystemRoot（通常为 C:\Windows）
        # 如果环境变量不存在，使用默认值 C:\Windows
        # 路径拼接使用 Path 对象，自动处理路径分隔符
        hosts_path = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "drivers" / "etc" / "hosts"

        try:
            # 以 UTF-8 编码读取 hosts 文件内容
            # errors="ignore" 表示遇到无法解码的字节时忽略（避免编码错误）
            with open(hosts_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()

            # 检查是否包含本程序的标记
            # 如果不包含，说明 hosts 文件未被修改，无需清理
            if hosts_marker in content:
                # 过滤掉包含标记的行
                # split("\n") 按行分割，列表推导式过滤掉包含标记的行
                lines = [l for l in content.split("\n") if hosts_marker not in l]

                # 将清理后的内容写回 hosts 文件
                # newline="\n" 确保使用 Unix 换行符，避免 Windows 自动转换为 \r\n
                with open(hosts_path, "w", encoding="utf-8", newline="\n") as f:
                    f.write("\n".join(lines))

                # 刷新 DNS 缓存，使 hosts 修改立即生效
                # ipconfig /flushdns 是 Windows 系统命令
                # capture_output=True 捕获输出（避免打印到控制台）
                # timeout=10 设置超时10秒，防止命令卡住
                subprocess.run(["ipconfig", "/flushdns"], capture_output=True, timeout=10)

        except Exception:
            # 捕获所有异常，静默处理
            # 常见异常类型：
            # - FileNotFoundError: hosts 文件不存在（非 Windows 系统）
            # - PermissionError: 权限不足，无法修改 hosts 文件
            # - OSError: 其他操作系统错误
            pass

    def _get_u8_token_from_account(self, hg_token: str) -> str:
        """通过鹰角账号 token 获取 u8_token

        实现三步认证流程，将用户提供的鹰角账号 token 转换为抽卡 API 所需的 u8_token。

        参数:
            hg_token (str): 鹰角账号 token，从 user.hypergryph.com 获取
                格式: 约24位的字母数字字符串
                示例: "a1b2c3d4e5f6g7h8i9j0k1l2"

        返回:
            str: u8_token，用于调用抽卡记录 API
                格式: 约184位的长字符串
                示例: 包含大量字母数字和特殊字符

        流程说明:
            步骤1: hg_token -> app_token
                调用鹰角 OAuth2 接口，将账号 token 换取应用 token
                请求地址: https://as.hypergryph.com/user/oauth2/v2/grant
                请求体: {"type": 1, "appCode": "be36d44aa36bfb5b", "token": hg_token}
                appCode "be36d44aa36bfb5b" 是明日方舟的应用标识

            步骤2: app_token -> 绑定列表 -> 明日方舟 UID
                调用绑定列表接口，获取账号下绑定的所有游戏
                请求地址: https://binding-api-account-prod.hypergryph.com/account/binding/v1/binding_list
                遍历返回的 app 列表，找到 appCode 为 "arknights" 的条目
                从 bindingList 中提取 uid

            步骤3: UID + app_token -> u8_token
                调用 u8_token 生成接口，获取最终的抽卡凭证
                请求地址: https://binding-api-account-prod.hypergryph.com/account/binding/v1/u8_token_by_uid
                请求体: {"uid": uid, "token": app_token}

        异常处理:
            - FetcherError: 账号验证失败、未找到绑定角色、获取凭证失败
            - requests.RequestException: 网络请求失败（由 requests 库抛出）
            - json.JSONDecodeError: 响应数据格式错误（由 .json() 方法抛出）

        安全说明:
            - hg_token 和 app_token 是临时凭证，不应持久化存储
            - u8_token 有效期较长，可以缓存使用
            - 所有请求使用 HTTPS，数据传输加密
        """
        # 延迟导入 requests 库
        # 避免在模块加载时就导入，减少启动时间
        # 只在需要网络请求时才导入
        import requests as req

        # ========== 步骤 1: hg_token -> app_token ==========
        # 报告进度，通知 UI 层当前操作状态
        # 0.1 表示进度为 10%
        self._report_progress("正在验证账号...", 0.1)

        # 调用速率限制器，避免请求过快触发风控
        # BaseFetcher 基类实现了 _rate_limit 方法
        self._rate_limit()

        # 发送 POST 请求到鹰角 OAuth2 接口
        # json 参数会自动设置 Content-Type 为 application/json
        # timeout=15 设置请求超时为 15 秒
        grant_resp = req.post(
            "https://as.hypergryph.com/user/oauth2/v2/grant",  # OAuth2 授权接口
            json={
                "type": 1,  # token 类型，1 表示账号 token
                "appCode": "be36d44aa36bfb5b",  # 明日方舟的应用标识码
                "token": hg_token,  # 用户提供的鹰角账号 token
            },
            timeout=15,  # 请求超时时间（秒）
        )

        # 解析 JSON 响应
        # grant_resp.json() 会将响应体解析为 Python 字典
        grant_data = grant_resp.json()

        # 提取 app_token
        # 响应结构: {"code": 0, "data": {"token": "xxx"}}
        # 使用链式 get 方法安全地提取嵌套值
        app_token = grant_data.get("data", {}).get("token")

        # 检查 app_token 是否获取成功
        # 如果为空，说明 token 无效或已过期
        if not app_token:
            # 抛出自定义异常，携带错误信息
            raise FetcherError("账号验证失败，请检查 Token 是否正确。")

        # ========== 步骤 2: app_token -> 绑定列表 -> 明日方舟 UID ==========
        # 报告进度（20%）
        self._report_progress("正在获取账号信息...", 0.2)
        self._rate_limit()  # 再次限流

        # 发送 GET 请求获取账号绑定的游戏列表
        # params 参数会自动编码到 URL 查询字符串中
        # 实际请求: https://...binding_list?token=xxx&appCode=arknights
        binding_resp = req.get(
            "https://binding-api-account-prod.hypergryph.com/account/binding/v1/binding_list",
            params={
                "token": app_token,  # 步骤1获取的 app_token
                "appCode": "arknights",  # 指定查询明日方舟的绑定信息
            },
            timeout=15,
        )

        # 解析绑定列表响应
        binding_data = binding_resp.json()

        # 提取应用列表
        # 响应结构: {"code": 0, "data": {"list": [{"appCode": "arknights", "bindingList": [...]}]}}
        apps = binding_data.get("data", {}).get("list", [])

        # 遍历应用列表，查找明日方舟的绑定信息
        uid = None  # 初始化 UID 为 None
        for app in apps:
            # 检查当前 app 的 appCode 是否为 "arknights"
            if app.get("appCode") == "arknights":
                # 遍历该应用的绑定列表（一个账号可能绑定多个角色）
                for binding in app.get("bindingList", []):
                    # 提取 UID
                    uid = binding.get("uid", "")
                    if uid:  # 如果找到有效的 UID
                        break  # 跳出内层循环
                break  # 跳出外层循环

        # 如果未找到明日方舟的绑定角色
        if not uid:
            # 抛出详细错误信息，指导用户解决问题
            raise FetcherError(
                "未找到明日方舟绑定角色。\n\n"
                "请确保该账号已绑定明日方舟角色。"
            )

        # 将检测到的 UID 保存到实例变量
        # 后续可用于日志记录或调试
        self._detected_uid = uid

        # ========== 步骤 3: UID + app_token -> u8_token ==========
        # 报告进度（30%）
        self._report_progress("正在获取抽卡凭证...", 0.3)
        self._rate_limit()

        # 发送 POST 请求获取 u8_token
        # u8_token 是抽卡记录 API 的专用凭证
        u8_resp = req.post(
            "https://binding-api-account-prod.hypergryph.com/account/binding/v1/u8_token_by_uid",
            json={
                "uid": uid,  # 步骤2获取的明日方舟 UID
                "token": app_token,  # 步骤1获取的 app_token
            },
            timeout=15,
        )

        # 解析响应
        u8_data = u8_resp.json()

        # 提取 u8_token
        u8_token = u8_data.get("data", {}).get("token")

        # 检查 u8_token 是否获取成功
        if not u8_token:
            # 可能原因：触发了风控限制、账号异常、服务器繁忙
            raise FetcherError("获取抽卡凭证失败，可能触发了风控限制。请稍后再试。")

        # 报告最终进度（40%），并显示获取到的 UID
        self._report_progress(f"已获取明日方舟凭证 (UID: {uid})", 0.4)

        # 返回最终的 u8_token
        return u8_token

    def _find_token_from_log(self) -> Optional[str]:
        """从 HGWebview.log 中提取 token (u8_token)

        从明日方舟游戏客户端的日志文件中自动提取 u8_token。
        当玩家在游戏内打开抽卡记录页面时，游戏会向 ak-webview.hypergryph.com 发起请求，
        请求 URL 中会包含 u8_token 参数。

        返回:
            Optional[str]: 提取到的 u8_token，如果未找到则返回 None

        日志文件路径:
            %LOCALAPPDATA%Low/Hypergryph/Arknights/sdklogs/HGWebview.log

        提取策略:
            1. 优先从抽卡页面 URL 中提取（包含 "/gacha?" 路径）
            2. 备用：从任意包含 u8_token 参数的 URL 中提取
            3. 取最后一个匹配项（最新的 token）

        注意事项:
            - 返回的 token 可能已过期（通常有效期为几小时）
            - 如果游戏从未打开过抽卡记录页面，日志中不会有 token
            - 日志文件可能很大（几百MB），需要高效读取
        """
        # 构造日志文件的完整路径
        # Path.home() 返回用户主目录（如 C:\Users\username）
        # 使用 / 运算符拼接路径，Python 会自动处理分隔符
        log_path = Path.home() / "AppData/LocalLow/Hypergryph/Arknights/sdklogs/HGWebview.log"

        # 检查日志文件是否存在
        if not log_path.exists():
            # 文件不存在，可能游戏从未运行过或路径已改变
            return None

        try:
            # 读取日志文件内容
            # 使用 UTF-8 编码，errors="ignore" 忽略无法解码的字符
            # 日志文件可能包含各种编码的字符（如游戏内文本）
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            # 读取失败（文件被占用、权限不足等），返回 None
            return None

        # ========== 优先策略：从抽卡页面 URL 提取 ==========
        # 正则表达式说明：
        # - https?://ak-webview\.hypergryph\.com/gacha\? : 匹配抽卡页面的基础 URL
        #   - https? 表示 http 或 https
        #   - \. 表示转义的点号
        #   - \? 衹示转义的问号
        # - [^\s"]* : 匹配 URL 中的其他字符（非空白、非引号）
        # - u8_token= : 匹配 token 参数名
        # - ([^\s"&]+) : 捕获组，匹配 token 值（非空白、非引号、非&）
        gacha_pattern = r'https?://ak-webview\.hypergryph\.com/gacha\?[^\s"]*u8_token=([^\s"&]+)'

        # 使用 findall 查找所有匹配项
        # 返回列表，每个元素是捕获组的内容（即 token 值）
        gacha_matches = re.findall(gacha_pattern, content)

        # 如果找到匹配项，返回最后一个（最新的）
        if gacha_matches:
            # unquote 解码 URL 编码的字符（如 %2F -> /）
            return unquote(gacha_matches[-1])

        # ========== 备用策略：从任意 URL 提取 ==========
        # 更宽松的正则表达式，只匹配 u8_token 参数
        pattern = r'u8_token=([^\s"&]+)'
        matches = re.findall(pattern, content)

        # 如果没有找到任何匹配，返回 None
        if not matches:
            return None

        # 返回最后一个匹配项（最新的 token）
        # 注意：这里的 token 可能来自非抽卡页面，有效性较低
        return unquote(matches[-1])

    def _get_pool_categories(self, code: str) -> List[dict]:
        """获取卡池列表

        调用官方 API 获取当前可用的卡池列表。
        卡池列表包含池ID、池名称、池类型等信息。

        参数:
            code (str): u8_token，用于身份验证和请求签名

        返回:
            List[dict]: 卡池信息列表，每个元素是一个字典，包含：
                - poolId (str): 卡池唯一标识符
                    示例: "LIMITED_2024_SSR_01", "CLASSIC_STANDARD_POOL"
                - poolName (str): 卡池显示名称
                    示例: "限定寻访【深眠】", "中坚寻访"
                - 其他字段取决于 API 返回

        异常处理:
            - 网络请求失败: 返回空列表
            - API 返回错误码: 返回空列表
            - Token 无效/过期: 返回空列表
            - 响应格式异常: 返回空列表

        API 接口:
            GET https://ak-webview.hypergryph.com/api/gacha/cate
            参数:
                - code: u8_token
            响应:
                {
                    "code": 0,  // 0 表示成功
                    "data": [   // 卡池列表
                        {"poolId": "xxx", "poolName": "xxx", ...}
                    ]
                }
        """
        try:
            # 使用 self.session 发送 GET 请求
            # self.session 是 BaseFetcher 基类提供的 requests.Session 对象
            # Session 对象会自动管理 cookies、连接池等
            resp = self.session.get(
                f"{self.API_BASE}/gacha/cate",  # 拼接完整的 API URL
                params={"code": code},  # 查询参数：u8_token
                timeout=self.config.get_request_timeout()  # 从配置获取超时时间
            )

            # 检查 HTTP 状态码
            # raise_for_status() 在状态码为 4xx/5xx 时抛出异常
            resp.raise_for_status()

            # 解析 JSON 响应
            data = resp.json()

            # 检查业务逻辑错误码
            # code != 0 通常表示 token 无效或请求参数错误
            if data.get("code") != 0:
                return []

            # 提取 data 字段
            result = data.get("data")

            # ========== 处理不同的响应格式 ==========
            # 有效 token: data 是包含卡池对象的列表
            # 无效 token: data 是空列表
            if isinstance(result, list):
                # 检查列表是否非空且第一个元素是字典
                if result and isinstance(result[0], dict):
                    return result  # 有效卡池列表
                return []  # 空列表 = token 无效

            # 某些版本的 API 可能返回字典格式
            # 例如: {"code": 0, "data": {"list": [...]}}
            if isinstance(result, dict):
                return result.get("list", [])

        except Exception:
            # 捕获所有异常，静默处理
            # 常见异常：网络超时、连接拒绝、SSL 错误等
            pass

        # 默认返回空列表
        return []

    def _parse_pool_type(self, pool_name: str, pool_id: str = "") -> str:
        """根据卡池ID或名称判断保底分组

        明日方舟的卡池分为三种保底类型：
        1. standard（标准寻访）: 通用保底池，包括双UP、单UP、联合行动等
        2. kernel（中坚寻访）: 常驻池，与标准寻访共享保底计数
        3. limited（限定寻访）: 限时池，独立保底计数，通常有更高的出率

        参数:
            pool_name (str): 卡池显示名称
                示例: "限定寻访【深眠】", "中坚寻访", "标准寻访"
            pool_id (str): 卡池唯一标识符（可选）
                示例: "LIMITED_2024_SSR_01", "CLASSIC_STANDARD_POOL"

        返回:
            str: 卡池类型标识符
                - "standard": 标准寻访
                - "kernel": 中坚寻访
                - "limited": 限定寻访

        判断优先级:
            1. 优先使用 pool_id 前缀判断（最可靠）
            2. 其次使用卡池名称映射表（ARKNIGHTS_POOL_MECHANIC_MAP）
            3. 最后使用关键词匹配（兜底方案）
            4. 未识别的卡池默认为 limited（保守策略）

        映射表说明:
            - ARKNIGHTS_POOL_MECHANIC_MAP: 卡池名称 -> 机制类型
                例如: {"限定寻访【深眠】": "LIMITED", ...}
            - ARKNIGHTS_MECHANIC_TO_GROUP: 机制类型 -> 保底分组
                例如: {"LIMITED": "limited", "CLASSIC": "kernel", ...}
        """
        # ========== 策略1: 使用 pool_id 前缀判断 ==========
        # pool_id 的命名规则包含池类型信息，是最可靠的判断依据
        if pool_id:
            # 转换为大写，避免大小写不一致的问题
            pool_id_upper = pool_id.upper()

            # 限定池: 前缀为 "LIMITED_"
            # 示例: "LIMITED_2024_SSR_01", "LIMITED_GG_001"
            if pool_id_upper.startswith("LIMITED_"):
                return "limited"

            # 联动池: 前缀为 "LINKAGE_"
            # 联动池也属于限定池，独立保底计数
            elif pool_id_upper.startswith("LINKAGE_"):
                return "limited"

            # 中坚池: 前缀为 "CLASSIC_"
            # 示例: "CLASSIC_STANDARD_POOL", "CLASSIC_KERNEL_POOL"
            elif pool_id_upper.startswith("CLASSIC_"):
                return "kernel"

        # ========== 策略2: 使用卡池名称映射表 ==========
        # 从预定义的映射表中查找卡池名称对应的机制类型
        # ARKNIGHTS_POOL_MECHANIC_MAP 在 core.models 中定义
        mechanic = ARKNIGHTS_POOL_MECHANIC_MAP.get(pool_name, "")

        # 如果找到机制类型，再转换为保底分组
        if mechanic:
            # ARKNIGHTS_MECHANIC_TO_GROUP 将机制类型映射到分组
            # 默认值为 "standard"（安全兜底）
            return ARKNIGHTS_MECHANIC_TO_GROUP.get(mechanic, "standard")

        # ========== 策略3: 关键词匹配 ==========
        # 通过卡池名称中的关键词进行模糊匹配
        # 这是最后的兜底方案，处理未在映射表中定义的卡池

        # 中坚池关键词
        for keyword in ["中坚"]:
            if keyword in pool_name:
                return "kernel"

        # 标准池关键词
        for keyword in ["标准", "常驻"]:
            if keyword in pool_name:
                return "standard"

        # ========== 默认策略 ==========
        # 未识别的特定卡池默认为限定池（limited）
        # 原因：绝大多数特定角色卡池都是限时池
        # 这样设置即使误判，也不会影响保底计数的准确性
        return "limited"

    def fetch_records(self, url: str = None, account_id: int = None, **kwargs) -> List[GachaRecord]:
        """获取明日方舟抽卡记录

        主入口方法，负责协调整个抽卡记录获取流程。
        支持从多种来源获取 token，并遍历所有卡池获取完整的抽卡历史。

        参数:
            url (str, optional): Token 或 URL
                - 鹰角账号 Token（约24位）
                - u8_token（约184位）
                - 包含 u8_token 的完整 URL
                如果为 None，则尝试从日志文件自动提取
            account_id (int, optional): 账户ID，用于数据库记录
                如果为 None，则使用默认值 0
            **kwargs: 其他参数（保留接口兼容性）

        返回:
            List[GachaRecord]: 抽卡记录列表，每个 GachaRecord 包含：
                - account_id: 账户ID
                - game: 游戏标识 "arknights"
                - pool_type: 卡池类型 (standard/kernel/limited)
                - pool_name: 卡池名称
                - item_id: 唯一标识（角色名_时间）
                - item_name: 角色名称
                - item_type: 物品类型 "CHAR"
                - rarity: 稀有度（1-6）
                - is_featured: 是否为UP物品
                - count: 数量（始终为1）
                - time: 抽卡时间
                - gacha_id: 卡池ID
                - raw_data: 原始API响应数据

        流程说明:
            1. 清理可能残留的 hosts 修改（代理服务器遗留）
            2. 获取 token（从参数、日志或账号交换）
            3. 验证 token 有效性（获取卡池列表）
            4. 遍历所有卡池，分页获取抽卡记录
            5. 解析并转换记录格式
            6. 返回完整的抽卡记录列表

        异常处理:
            - FetcherError: 所有业务逻辑错误（token无效、网络失败等）
            - Exception: 未预期的异常（通常被捕获并转换为 FetcherError）
        """
        # ========== 步骤1: 清理 hosts 文件 ==========
        # 如果之前运行过代理服务器，hosts 文件可能被修改
        # 在启动时自动清理，确保网络请求正常
        self._cleanup_hosts()

        # ========== 步骤2: 获取 token ==========
        token = None  # 初始化 token 为 None

        if url:
            # 如果提供了 url 参数，直接使用
            # strip() 去除首尾空白字符
            token = url.strip()
        else:
            # 未提供 url，尝试从日志文件自动提取
            self._report_progress("正在从游戏日志读取 Token...", 0.05)
            token = self._find_token_from_log()

        # ========== 步骤3: 处理 token 类型 ==========
        if token:
            # 检查 token 长度，判断类型
            # 短 token（< 50字符）通常是鹰角账号 token，需要交换为 u8_token
            # 长 token（>= 50字符）通常是 u8_token，可以直接使用
            if len(token) < 50:
                # 检测到鹰角账号 token，执行交换流程
                self._report_progress("检测到鹰角账号 Token，正在交换...", 0.1)
                try:
                    token = self._get_u8_token_from_account(token)
                except FetcherError as e:
                    # 交换失败，包装错误信息并重新抛出
                    raise FetcherError(f"Token 交换失败：{e}")
            # 长 token 直接当作 u8_token 使用，无需额外处理

        # ========== 步骤4: 检查 token 是否存在 ==========
        if not token:
            # 未找到任何可用的 token
            # 提供详细的获取说明，帮助用户解决问题
            raise FetcherError(
                "未找到 Token。\n\n"
                "请通过以下方式之一提供：\n"
                "1. 登录获取：点击「登录获取」按钮登录鹰角账号\n"
                "2. 手动粘贴：从抓包工具中复制包含 u8_token 的 URL\n"
                "3. 账号 Token：粘贴从 user.hypergryph.com 获取的 Token"
            )

        # ========== 步骤5: 获取卡池列表 ==========
        self._report_progress("开始获取抽卡记录...", 0.1)

        # 调用 API 获取所有可用的卡池
        pools = self._get_pool_categories(token)

        # ========== 步骤6: 处理 token 无效的情况 ==========
        # 如果获取不到卡池，可能是以下原因：
        # 1. token 已过期
        # 2. token 无效
        # 3. 网络问题

        # 特殊情况：长 token（可能是日志中提取的）但获取不到卡池
        if not pools and len(token) > 50:
            self._report_progress("Token 可能已过期，尝试其他方式...", 0.1)
            # 无法自动恢复，提示用户手动操作
            raise FetcherError(
                "Token 已过期或无效。\n\n"
                "请通过以下方式重新获取：\n"
                "1. 点击「登录获取」按钮登录鹰角账号\n"
                "2. 或手动粘贴有效的 Token/URL"
            )

        # 通用情况：获取卡池失败
        if not pools:
            # 提供详细的错误信息和解决建议
            raise FetcherError(
                "获取卡池列表失败，Token 可能无效。\n\n"
                "请确认 Token 正确后重试，或点击「登录获取」重新登录。\n\n"
                "支持的 Token 格式：\n"
                "- 鹰角账号 Token（短，24字符）\n"
                "- u8_token（长，184字符）\n"
                "- 包含 u8_token 的完整 URL"
            )

        # ========== 步骤7: 遍历卡池获取记录 ==========
        all_records = []  # 存储所有抽卡记录

        # 遍历每个卡池
        for pool_info in pools:
            # 提取卡池信息
            # 兼容不同版本的 API 响应格式
            pool_id = pool_info.get("poolId") or pool_info.get("id", "")
            pool_name = pool_info.get("poolName") or pool_info.get("name", "未知卡池")

            # 解析卡池类型（standard/kernel/limited）
            pool_type = self._parse_pool_type(pool_name, pool_id)

            # 调试日志：打印卡池信息，便于排查问题
            print(f"[DEBUG] 卡池: {pool_name}, poolId: {pool_id}, 分类: {pool_type}")

            # 报告当前正在处理的卡池
            self._report_progress(f"正在获取卡池: {pool_name}...", 0.2)

            # ========== 分页获取抽卡记录 ==========
            page = 1  # 当前页码（用于调试日志）
            last_gacha_ts = ""  # 上一条记录的时间戳（用于分页）
            last_pos = ""  # 上一条记录的位置（用于分页）

            # 无限循环，直到获取完所有记录
            while True:
                # 限流，避免请求过快
                self._rate_limit()

                try:
                    # 构造请求参数
                    params = {
                        "code": token,  # u8_token
                        "category": pool_id,  # 卡池ID
                    }

                    # 如果不是第一页，添加分页参数
                    if last_gacha_ts:
                        params["gachaTs"] = last_gacha_ts
                    if last_pos:
                        params["pos"] = last_pos

                    # 发送 GET 请求获取抽卡历史
                    resp = self.session.get(
                        f"{self.API_BASE}/gacha/history",
                        params=params,
                        timeout=self.config.get_request_timeout()
                    )

                    # 检查 HTTP 状态码
                    resp.raise_for_status()

                    # 解析 JSON 响应
                    data = resp.json()

                    # 检查业务错误码
                    if data.get("code") != 0:
                        break  # token 无效或其他错误，跳出循环

                    # 提取记录列表
                    records = data.get("data", {}).get("list", [])

                    # 如果记录为空，说明已到达末尾
                    if not records:
                        break

                    # ========== 解析每条记录 ==========
                    for raw in records:
                        # 提取抽卡时间戳（毫秒）
                        gacha_ts = raw.get("gachaTs", 0)

                        # 转换时间戳为可读格式
                        try:
                            # 除以 1000 转换为秒级时间戳
                            ts = int(gacha_ts) / 1000
                            # 使用 strftime 格式化为 "YYYY-MM-DD HH:MM:SS"
                            # time.localtime 将 UTC 时间转换为本地时间
                            record_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts))
                        except (ValueError, TypeError, OSError):
                            # 转换失败，使用空字符串
                            record_time = ""

                        # 提取角色信息
                        # 每条记录就是一个角色，不是嵌套结构
                        char_name = raw.get("charName", "未知")

                        # 提取稀有度
                        rarity = raw.get("rarity", 0)

                        # 稀有度转换
                        # API 返回值: 0=1星, 1=2星, 2=3星, 3=4星, 4=5星, 5=6星
                        # 转换为标准星级: +1（1-6星）
                        rarity = rarity + 1

                        # 优先使用记录中的 poolName（具体卡池名）
                        # 如果记录中没有，使用池列表的名称
                        record_pool_name = raw.get("poolName", "") or pool_name

                        # 生成唯一 item_id
                        # 格式: 角色名_时间（与小黑盒导入格式一致）
                        # 这样设计可以避免重复记录（同一角色在不同时间抽到）
                        unique_id = f"{char_name}_{record_time}"

                        # 创建 GachaRecord 对象
                        record = GachaRecord(
                            account_id=account_id or 0,  # 账户ID，如果未提供则为0
                            game="arknights",  # 游戏标识
                            pool_type=pool_type,  # 卡池类型
                            pool_name=record_pool_name,  # 卡池名称
                            item_id=unique_id,  # 唯一标识
                            item_name=char_name,  # 角色名称
                            item_type="CHAR",  # 物品类型（角色）
                            rarity=rarity,  # 稀有度（1-6）
                            is_featured=False,  # 是否为UP物品（明日方舟API不提供此信息）
                            count=1,  # 数量（始终为1）
                            time=record_time,  # 抽卡时间
                            gacha_id=raw.get("poolId", pool_id),  # 卡池ID
                            raw_data=str(raw),  # 原始API响应（字符串形式）
                        )

                        # 将记录添加到列表
                        all_records.append(record)

                    # ========== 检查是否有更多记录 ==========
                    has_more = data.get("data", {}).get("hasMore", False)
                    if not has_more:
                        # 已获取所有记录，跳出循环
                        break

                    # ========== 更新分页参数 ==========
                    # 获取最后一条记录的信息，用于下一页查询
                    last_record = records[-1]
                    last_gacha_ts = str(last_record.get("gachaTs", ""))
                    last_pos = str(last_record.get("pos", ""))

                    # 页码计数（主要用于调试日志）
                    page += 1

                    # 限流：等待 0.5 秒
                    # 避免请求过快触发风控
                    time.sleep(0.5)

                except Exception as e:
                    # 捕获所有异常
                    if isinstance(e, FetcherError):
                        # FetcherError 是业务逻辑异常，需要重新抛出
                        raise
                    # 其他异常（网络错误、解析错误等），跳出循环
                    break

        # ========== 步骤8: 返回结果 ==========
        # 报告最终进度，显示获取的记录总数
        self._report_progress(f"获取完成，共 {len(all_records)} 条记录", 1.0)

        # 返回所有抽卡记录
        return all_records
