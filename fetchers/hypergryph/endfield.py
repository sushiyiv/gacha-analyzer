"""终末地抽卡记录获取器 - 支持日志提取、账号 Token 和第三方 API 三种方式

本模块实现了鹰角网络旗下游戏《明日方舟：终末地》（Arknights: Endfield）的抽卡记录获取功能。

支持的 Token 获取方式:
    1. 从游戏日志文件 HGWebview.log 中自动提取 u8_token（旧版游戏）
    2. 通过鹰角账号 Token（hg_token）交换获取 u8_token
    3. 用户手动粘贴包含 u8_token 的 URL

支持的卡池类型:
    - 特许寻访 (Special): 限定池，独立保底计数
    - 辉光庆典 (Joint): 联合寻访，独立保底计数
    - 基础寻访 (Standard): 常驻池
    - 启程寻访 (Beginner): 新手池
    - 武器池 (Weapon): 武器抽取

API 基础地址:
    - hypergryph: https://ef-webview.hypergryph.com/api
    - gryphline: https://ef-webview.gryphline.com/api

主要接口:
    - /api/record/char: 获取角色抽卡记录
    - /api/record/weapon: 获取武器抽卡记录
    - /api/record/weapon/pool: 获取武器池列表

增量同步机制:
    通过 seqId（序列ID）实现增量同步，只获取新增的记录。
    每次同步会记录各卡池的最大 seqId，下次同步时跳过已获取的记录。

作者: gacha-analyzer 开发团队
"""

import ast  # 抽象语法树模块，用于安全地解析字符串格式的 Python 数据结构
import os  # 操作系统接口（备用导入）
import re  # 正则表达式模块，用于从日志中提取 token
import time  # 时间模块，用于请求限流
from datetime import datetime  # 日期时间模块，用于时间戳转换
from pathlib import Path  # 路径处理模块
from urllib.parse import unquote  # URL 解码函数
from typing import List, Optional, Tuple  # 类型提示
from fetchers.base import BaseFetcher, FetcherError  # 基础获取器类和自定义异常
from core.models import GachaRecord, ENDFIELD_STANDARD_6STAR  # 数据模型和常驻6星列表

# ========== 终末地角色池类型常量 ==========
# 这些常量对应 API 返回的 pool_type 字段值
# 使用枚举风格命名（E_ 前缀），与游戏内部命名一致
CHAR_POOL_TYPES = [
    "E_CharacterGachaPoolType_Special",  # 特许寻访（限定池）
    "E_CharacterGachaPoolType_Joint",  # 辉光庆典（联合寻访）
    "E_CharacterGachaPoolType_Standard",  # 基础寻访（常驻池）
    "E_CharacterGachaPoolType_Beginner",  # 启程寻访（新手池）
]

# ========== API pool_type → 项目内部 pool_type 映射 ==========
# API 返回的 pool_type 是枚举风格字符串
# 需要转换为项目内部使用的简化标识符
# 这样便于数据库存储、UI 显示和统计分析
_POOL_TYPE_MAP = {
    "E_CharacterGachaPoolType_Special": "limited",     # 特许寻访 → 限定池
    "E_CharacterGachaPoolType_Joint": "joint",         # 辉光庆典 → 联合寻访
    "E_CharacterGachaPoolType_Standard": "character",  # 基础寻访 → 角色池
    "E_CharacterGachaPoolType_Beginner": "beginner",   # 启程寻访 → 新手池
}


def _parse_gacha_ts(ts) -> str:
    """将 gachaTs（毫秒时间戳）转换为 datetime 字符串（含毫秒）

    参数:
        ts: 时间戳，可以是整数、浮点数或字符串
            - 毫秒时间戳: 1000000000000 (13位)
            - 秒级时间戳: 1000000000 (10位)

    返回:
        str: 格式化的时间字符串
            - 毫秒时间戳: "2024-01-01 12:00:00.123"
            - 秒级时间戳: "2024-01-01 12:00:00"
            - 转换失败: ""

    实现逻辑:
        1. 将输入转换为整数
        2. 判断时间戳位数（>1e12 为毫秒级）
        3. 转换为 datetime 对象
        4. 格式化为字符串

    异常处理:
        - ValueError: 无法转换为整数
        - OSError: 时间戳超出系统支持范围
        - TypeError: 输入类型不支持
    """
    # 检查输入是否为空
    if not ts:
        return ""

    try:
        # 尝试转换为整数
        ts_int = int(ts)

        # 判断是否为毫秒时间戳
        # 毫秒时间戳通常大于 1e12（约 2001 年）
        # 秒级时间戳通常小于 1e12
        if ts_int > 1e12:  # 毫秒时间戳
            # 除以 1000 转换为秒级时间戳
            # datetime.fromtimestamp 将时间戳转换为本地时间
            dt = datetime.fromtimestamp(ts_int / 1000)

            # 格式化为 "YYYY-MM-DD HH:MM:SS.mmm"
            # 使用 f-string 手动拼接毫秒部分
            # ts_int % 1000 提取毫秒部分
            # :03d 格式化为 3 位数字（补零）
            return dt.strftime("%Y-%m-%d %H:%M:%S.") + f"{ts_int % 1000:03d}"
        else:
            # 秒级时间戳，直接转换
            return datetime.fromtimestamp(ts_int).strftime("%Y-%m-%d %H:%M:%S")

    except (ValueError, OSError, TypeError):
        # 转换失败，返回空字符串
        return ""


def _compare_seq_id(a: str, b: str) -> int:
    """比较两个 seq_id 的大小

    seq_id 是抽卡记录的序列标识符，用于增量同步。
    此函数实现了 seq_id 的比较逻辑，支持纯数字和混合字符串。

    参数:
        a (str): 第一个 seq_id
        b (str): 第二个 seq_id

    返回:
        int: 比较结果
            - 1: a > b
            - 0: a == b
            - -1: a < b

    比较规则:
        1. 如果相等，返回 0
        2. 如果都是纯数字:
            - 先比较长度（位数多的更大）
            - 长度相同则按字符串比较
        3. 如果一个纯数字一个非数字:
            - 纯数字更大
        4. 如果都是非纯数字:
            - 按字符串字典序比较

    示例:
        _compare_seq_id("123", "45") -> 1 (123 > 45)
        _compare_seq_id("abc", "123") -> -1 (非数字 < 数字)
        _compare_seq_id("abc", "abd") -> -1 (abc < abd)
    """
    # 如果相等，直接返回 0
    if a == b:
        return 0

    # 检查是否为纯数字
    a_digit = a.isdigit()
    b_digit = b.isdigit()

    # 情况1: 都是纯数字
    if a_digit and b_digit:
        # 先比较长度（位数多的更大）
        if len(a) != len(b):
            return 1 if len(a) > len(b) else -1
        # 长度相同，按字符串比较
        return 1 if a > b else -1

    # 情况2: 一个纯数字，一个非纯数字
    # 纯数字更大（数字 ID 通常比字符串 ID 更新）
    if a_digit != b_digit:
        return 1 if a_digit else -1

    # 情况3: 都是非纯数字
    # 按字符串字典序比较
    return 1 if a > b else -1


def _get_max_seq_id(records: List[GachaRecord]) -> str:
    """从记录列表中获取最大 seq_id

    遍历所有记录，找到最大的 seq_id。
    用于确定增量同步的起点。

    参数:
        records (List[GachaRecord]): 抽卡记录列表

    返回:
        str: 最大的 seq_id，如果列表为空则返回 ""

    实现逻辑:
        1. 遍历每条记录
        2. 从 raw_data 中解析 seqId
        3. 使用 _compare_seq_id 比较大小
        4. 返回最大的 seq_id

    注意:
        - raw_data 是字符串格式的 Python 字典
        - 使用 ast.literal_eval 安全解析（避免代码注入）
        - 解析失败的记录会被跳过
    """
    # 初始化最大 ID 为空字符串
    max_id = ""

    # 遍历所有记录
    for r in records:
        try:
            # 解析 raw_data
            # raw_data 是字符串格式的 Python 字典
            # 例如: "{'seqId': '123', 'charName': 'xxx'}"
            raw = ast.literal_eval(r.raw_data) if r.raw_data else {}

            # 提取 seqId
            sid = str(raw.get("seqId", ""))

            # 如果 seqId 非空且比当前最大值大
            if sid and _compare_seq_id(sid, max_id) > 0:
                max_id = sid

        except Exception:
            # 解析失败，跳过此记录
            pass

    # 返回最大的 seq_id
    return max_id


class EndfieldFetcher(BaseFetcher):
    """终末地抽卡记录获取器

    继承自 BaseFetcher 基类，实现了终末地特有的抽卡记录获取逻辑。

    主要功能:
        - 支持从日志文件自动提取 u8_token（旧版游戏）
        - 支持通过鹰角账号 token 交换获取 u8_token
        - 支持从官方 API 获取角色和武器抽卡记录
        - 支持增量同步，避免重复获取已存在的记录
        - 自动处理分页，获取所有抽卡记录
        - 支持多种卡池类型识别

    属性:
        _detected_uid: 通过账号交换检测到的用户UID

    数据流:
        1. 获取 u8_token（从日志、URL 或账号交换）
        2. 获取角色池记录（遍历所有角色池类型）
        3. 获取武器池记录（遍历所有武器池）
        4. 合并并返回所有记录
    """

    def get_game_name(self) -> str:
        """获取游戏名称

        返回:
            str: 游戏的中文名称 "终末地"

        说明:
            此方法重写自 BaseFetcher 基类。
            返回值用于 UI 显示、日志记录和文件命名。
        """
        return "终末地"

    def get_supported_pools(self) -> List[str]:
        """获取支持的卡池类型列表

        返回:
            List[str]: 支持的卡池类型标识符列表
                - "limited": 限定池（特许寻访）
                - "joint": 联合寻访（辉光庆典）
                - "character": 角色池（基础寻访）
                - "weapon": 武器池
                - "beginner": 新手池（启程寻访）

        说明:
            此方法定义了该获取器支持的卡池分类，用于:
            1. UI 层面显示可选的卡池过滤器
            2. 数据库查询时的卡池类型筛选
            3. 抽卡统计时的分组依据
        """
        return ["limited", "joint", "character", "weapon", "beginner"]

    def _find_u8_token_from_log(self) -> Optional[Tuple[str, str]]:
        """从 HGWebview.log 中提取 u8_token（旧版游戏）

        从终末地游戏客户端的日志文件中自动提取 u8_token。
        当玩家在游戏内打开抽卡记录页面时，游戏会向 ef-webview 服务器发起请求，
        请求 URL 中会包含 u8_token 参数。

        返回:
            Optional[Tuple[str, str]]: 元组 (u8_token, provider)
                - u8_token: 提取到的抽卡凭证
                - provider: 服务提供商标识
                    - "hypergryph": 鹰角国际服
                    - "gryphline": 鹰角国际服（Gryphline 品牌）
                如果未找到则返回 None

        日志文件路径:
            %LOCALAPPDATA%Low/Hypergryph/Endfield/sdklogs/HGWebview.log

        提取策略:
            1. 使用正则表达式匹配 ef-webview 域名的 URL
            2. 从 URL 参数中提取 u8_token
            3. 返回最后一个匹配项（最新的 token）
            4. 同时识别服务提供商（hypergryph 或 gryphline）

        注意事项:
            - 返回的 token 可能已过期（通常有效期为几小时）
            - 如果游戏从未打开过抽卡记录页面，日志中不会有 token
            - 旧版游戏才会写入日志，新版游戏可能已移除此机制
        """
        # 构造日志文件路径
        log_path = Path.home() / "AppData/LocalLow/Hypergryph/Endfield/sdklogs/HGWebview.log"

        # 检查文件是否存在
        if not log_path.exists():
            return None

        try:
            # 读取日志文件内容
            # 使用 UTF-8 编码，忽略无法解码的字符
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
        except Exception:
            # 读取失败，返回 None
            return None

        # 正则表达式匹配 ef-webview 域名的 URL
        # 模式说明:
        # - https://ef-webview\. : 匹配 URL 开头
        # - (hypergryph|gryphline) : 捕获组，匹配服务提供商
        # - \.com/[^\s"]* : 匹配路径和查询参数
        # - u8_token= : 匹配 token 参数名
        # - ([^\s"&]+) : 捕获组，匹配 token 值
        pattern = r'https://ef-webview\.(hypergryph|gryphline)\.com/[^\s"]*u8_token=([^\s"&]+)'

        # 查找所有匹配项
        matches = re.findall(pattern, content)

        # 如果没有匹配，返回 None
        if not matches:
            return None

        # 取最后一个匹配项（最新的 token）
        # matches[-1] 返回 (provider, token_encoded) 元组
        provider, token_encoded = matches[-1]

        # unquote 解码 URL 编码的 token
        # 返回 (u8_token, provider) 元组
        return unquote(token_encoded), provider

    def _get_u8_token_from_account(self, hg_token: str) -> Tuple[str, str]:
        """通过鹰角账号 token 获取 u8_token

        实现三步认证流程，将用户提供的鹰角账号 token 转换为抽卡 API 所需的 u8_token。

        参数:
            hg_token (str): 鹰角账号 token，从 user.hypergryph.com 获取
                格式: 约24位的字母数字字符串

        返回:
            Tuple[str, str]: 元组 (u8_token, provider)
                - u8_token: 用于调用抽卡记录 API 的凭证
                - provider: 服务提供商标识，固定为 "hypergryph"

        流程说明:
            步骤1: hg_token -> app_token
                调用鹰角 OAuth2 接口，将账号 token 换取应用 token
                请求地址: https://as.hypergryph.com/user/oauth2/v2/grant
                appCode: "be36d44aa36bfb5b"（终末地的应用标识）

            步骤2: app_token -> 绑定列表 -> 终末地 UID
                调用绑定列表接口，获取账号下绑定的所有游戏
                请求地址: https://binding-api-account-prod.hypergryph.com/account/binding/v1/binding_list
                appCode: "endfield"（查询终末地的绑定信息）

            步骤3: UID + app_token -> u8_token
                调用 u8_token 生成接口，获取最终的抽卡凭证
                请求地址: https://binding-api-account-prod.hypergryph.com/account/binding/v1/u8_token_by_uid

        异常处理:
            - FetcherError: 账号验证失败、未找到绑定角色、获取凭证失败

        安全说明:
            - 所有请求使用 HTTPS，数据传输加密
            - token 是临时凭证，不应持久化存储
        """
        # 延迟导入 requests 库
        import requests as req

        # ========== 步骤 1: hg_token -> app_token ==========
        # 报告进度（10%）
        self._report_progress("正在验证账号...", 0.1)

        # 限流
        self._rate_limit()

        # 发送 POST 请求到 OAuth2 接口
        grant_resp = req.post(
            "https://as.hypergryph.com/user/oauth2/v2/grant",
            json={
                "type": 1,  # token 类型
                "appCode": "be36d44aa36bfb5b",  # 终末地应用标识
                "token": hg_token,  # 用户提供的账号 token
            },
            timeout=15,
        )

        # 解析响应
        grant_data = grant_resp.json()

        # 提取 app_token
        app_token = grant_data.get("data", {}).get("token")

        # 检查是否获取成功
        if not app_token:
            # 获取错误信息
            msg = grant_data.get("msg", "未知错误")
            raise FetcherError(f"账号验证失败: {msg}")

        # ========== 步骤 2: app_token -> 绑定列表 -> UID ==========
        # 报告进度（20%）
        self._report_progress("正在获取账号信息...", 0.2)
        self._rate_limit()

        # 发送 GET 请求获取绑定列表
        binding_resp = req.get(
            "https://binding-api-account-prod.hypergryph.com/account/binding/v1/binding_list",
            params={
                "token": app_token,
                "appCode": "endfield",  # 查询终末地
            },
            headers={
                # 模拟浏览器请求头（某些接口可能检查 User-Agent）
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            },
            timeout=15,
        )

        # 解析响应
        binding_data = binding_resp.json()

        # 提取应用列表
        apps = binding_data.get("data", {}).get("list", [])

        # 查找终末地的 UID
        uid = None
        for app in apps:
            # 检查 appCode 是否为 "endfield"
            if app.get("appCode") == "endfield":
                # 遍历绑定列表（一个账号可能绑定多个角色）
                for binding in app.get("bindingList", []):
                    uid = binding.get("uid", "")
                    if uid:
                        break  # 找到有效 UID，跳出内层循环
                break  # 跳出外层循环

        # 检查是否找到 UID
        if not uid:
            raise FetcherError("未找到终末地绑定角色。请确保该账号已绑定终末地。")

        # 保存 UID 到实例变量
        self._detected_uid = uid

        # ========== 步骤 3: UID + app_token -> u8_token ==========
        # 报告进度（30%）
        self._report_progress("正在获取抽卡凭证...", 0.3)
        self._rate_limit()

        # 发送 POST 请求获取 u8_token
        u8_resp = req.post(
            "https://binding-api-account-prod.hypergryph.com/account/binding/v1/u8_token_by_uid",
            json={
                "uid": uid,
                "token": app_token,
            },
            timeout=15,
        )

        # 解析响应
        u8_data = u8_resp.json()

        # 提取 u8_token
        u8_token = u8_data.get("data", {}).get("token")

        # 检查是否获取成功
        if not u8_token:
            raise FetcherError("获取抽卡凭证失败，可能触发了风控限制。请稍后再试。")

        # 返回 u8_token 和 provider
        # provider 固定为 "hypergryph"（账号交换只支持国际服）
        return u8_token, "hypergryph"

    def _get_u8_token(self, url: str = None) -> Tuple[str, str]:
        """获取 u8_token，优先从日志提取，其次从 URL 参数提取

        这是 token 获取的统一入口，按照优先级尝试不同的获取方式。

        参数:
            url (str, optional): 用户提供的 URL 或 token

        返回:
            Tuple[str, str]: 元组 (u8_token, provider)

        获取优先级:
            1. 从日志文件自动提取（最方便）
            2. 从 URL 参数提取（用户粘贴的抽卡链接）
            3. 通过账号 token 交换（需要网络请求）

        异常处理:
            - FetcherError: 所有获取方式都失败

        注意:
            - 日志提取只适用于旧版游戏
            - URL 必须包含 "ef-webview" 和 "u8_token=" 才能识别
            - 长 token（>50字符）会被当作账号 token 尝试交换
        """
        # ========== 方式1: 从日志提取 ==========
        # 最方便的方式，无需用户手动操作
        result = self._find_u8_token_from_log()
        if result:
            return result

        # ========== 方式2: 从 URL 参数提取 ==========
        if url:
            # 检查 URL 是否包含抽卡链接特征
            if "ef-webview" in url and "u8_token=" in url:
                # 直接从 URL 中提取 u8_token
                match = re.search(r'u8_token=([^&]+)', url)
                if match:
                    # 识别服务提供商
                    # 包含 "gryphline" 则为国际服，否则为国服
                    provider = "gryphline" if "gryphline" in url else "hypergryph"
                    return unquote(match.group(1)), provider

            elif len(url) > 50:
                # 长 token，当作鹰角账号 token 尝试交换
                return self._get_u8_token_from_account(url.strip())

            else:
                # 短 token（<50字符），可能是 framework_token
                # framework_token 用于第三方 API，但该方式已弃用
                raise FetcherError("凭证格式不正确，请重新登录获取")

        # ========== 所有方式都失败 ==========
        # 提供详细的获取说明
        raise FetcherError(
            "未找到抽卡凭证。\n\n"
            "请通过以下方式之一获取：\n"
            "1. 在游戏内打开抽卡记录页面（旧版游戏会写入日志）\n"
            "2. 登录 https://user.hypergryph.com/ 获取 Token 并粘贴"
        )

    def _check_token_error(self, resp: dict) -> None:
        """检查 API 响应中的 token 错误

        某些 API 在 token 无效或过期时会返回特定错误码。
        此方法检查这些错误码并抛出相应的异常。

        参数:
            resp (dict): API 响应数据

        错误码说明:
            - 40100: Token 已过期或无效

        异常处理:
            - FetcherError: token 过期或无效

        注意:
            - 此方法只检查 token 相关错误
            - 其他错误码由调用方处理
        """
        # 提取错误码
        code = resp.get("code", 0)

        # 检查 token 过期错误码
        if code == 40100:
            raise FetcherError(
                "Token 已过期。\n\n"
                "请在游戏内重新打开一次抽卡记录页面，或重新登录获取新 Token。"
            )

    def _fetch_char_records(self, u8_token: str, provider: str, server_id: str = "1", stop_seq_ids: dict = None) -> List[GachaRecord]:
        """获取角色池记录（支持增量同步）

        遍历所有角色池类型，分页获取抽卡记录。
        支持增量同步，只获取新增的记录。

        参数:
            u8_token (str): 抽卡 API 凭证
            provider (str): 服务提供商（"hypergryph" 或 "gryphline"）
            server_id (str): 服务器ID，默认 "1"（国服）
            stop_seq_ids (dict, optional): 增量同步的停止点
                格式: {"pool_type": "max_seq_id"}
                例如: {"character": "12345", "limited": "67890"}

        返回:
            List[GachaRecord]: 角色抽卡记录列表

        API 接口:
            GET https://ef-webview.{provider}.com/api/record/char
            参数:
                - lang: 语言（zh-cn）
                - token: u8_token
                - server_id: 服务器ID
                - pool_type: 池类型
                - seq_id: 分页游标（可选）

        增量同步逻辑:
            1. 获取 stop_seq_id（该池类型已同步的最大 seq_id）
            2. 请求新记录
            3. 过滤掉 seq_id <= stop_seq_id 的记录
            4. 如果遇到旧记录，停止分页（后续页面更旧）

        异常处理:
            - FetcherError: 网络请求失败、token 无效
        """
        # 存储所有记录
        all_records = []

        # 语言设置
        lang = "zh-cn"

        # 遍历所有角色池类型
        for api_pool_type in CHAR_POOL_TYPES:
            # 将 API 池类型转换为内部池类型
            internal_pool_type = _POOL_TYPE_MAP.get(api_pool_type, "character")

            # 获取该池类型的停止点（用于增量同步）
            stop_seq_id = (stop_seq_ids or {}).get(internal_pool_type, "")

            # 报告进度
            self._report_progress(f"正在获取角色池: {api_pool_type}...", 0.4)

            # 分页参数
            seq_id = ""  # 当前页游标
            has_more = True  # 是否还有更多记录

            # 分页循环
            while has_more:
                # 构造请求参数
                params = {
                    "lang": lang,
                    "token": u8_token,
                    "server_id": server_id,
                    "pool_type": api_pool_type,
                }

                # 如果有游标，添加到参数
                if seq_id:
                    params["seq_id"] = seq_id

                # 构造请求 URL
                url = f"https://ef-webview.{provider}.com/api/record/char"

                try:
                    # 发送请求
                    resp = self._request(url, params=params)
                except FetcherError:
                    # 请求失败，停止分页
                    has_more = False
                    break

                # 检查 token 错误
                self._check_token_error(resp)

                # 检查业务错误码
                if resp.get("code") != 0:
                    has_more = False
                    break

                # 提取数据
                data = resp.get("data", {})
                records_list = data.get("list", [])
                has_more_flag = data.get("hasMore", False)

                # 调试日志：写入文件便于排查问题
                with open("debug_endfield.log", "a", encoding="utf-8") as f:
                    f.write(f"{api_pool_type}: 本页{len(records_list)}条, hasMore={has_more_flag}, stop_seq_id='{stop_seq_id}', seq_id='{seq_id}'\n")
                    if records_list:
                        f.write(f"  首条: seqId={records_list[0].get('seqId')}, 尾条: seqId={records_list[-1].get('seqId')}\n")

                # ========== 增量同步：过滤旧记录 ==========
                if stop_seq_id:
                    # 过滤出 seq_id 大于停止点的记录
                    new_only = [r for r in records_list
                                if _compare_seq_id(str(r.get("seqId", "")), stop_seq_id) > 0]

                    # 写入调试日志
                    with open("debug_endfield.log", "a", encoding="utf-8") as f:
                        f.write(f"  增量过滤: {len(records_list)} -> {len(new_only)}\n")

                    # 如果过滤后记录减少，说明遇到了旧记录
                    if len(new_only) < len(records_list):
                        records_list = new_only
                        has_more = False  # 后续页面更旧，停止分页

                # ========== 解析每条记录 ==========
                for raw in records_list:
                    # 提取角色名称
                    item_name = raw.get("charName", "未知")

                    # 提取稀有度（1-6星）
                    rarity = int(raw.get("rarity", 3))

                    # 判断是否为 UP 物品
                    # 6星角色不在常驻列表中 = UP 物品
                    is_featured = (rarity == 6 and item_name not in ENDFIELD_STANDARD_6STAR)

                    # 创建 GachaRecord 对象
                    record = GachaRecord(
                        account_id=0,  # 稍后设置
                        game="endfield",
                        pool_type=internal_pool_type,
                        pool_name=raw.get("poolName", ""),
                        item_id=str(raw.get("seqId", "")),  # 使用 seqId 作为唯一标识
                        item_name=item_name,
                        item_type="角色",
                        rarity=rarity,
                        is_featured=is_featured,
                        count=1,
                        time=_parse_gacha_ts(raw.get("gachaTs", "")),
                        gacha_id=raw.get("poolId", ""),
                        raw_data=str(raw),
                    )

                    # 添加到结果列表
                    all_records.append(record)

                # 更新分页状态
                has_more = bool(data.get("hasMore", False))

                # 更新游标（使用最后一条记录的 seqId）
                if records_list:
                    seq_id = records_list[-1].get("seqId", "")

        # 返回所有记录
        return all_records

    def _fetch_weapon_records(self, u8_token: str, provider: str, server_id: str = "1", stop_seq_ids: dict = None) -> List[GachaRecord]:
        """获取武器池记录（支持增量同步）

        先获取武器池列表，然后逐个池子获取抽卡记录。

        参数:
            u8_token (str): 抽卡 API 凭证
            provider (str): 服务提供商
            server_id (str): 服务器ID，默认 "1"
            stop_seq_ids (dict, optional): 增量同步的停止点

        返回:
            List[GachaRecord]: 武器抽卡记录列表

        API 接口:
            1. 获取武器池列表:
               GET https://ef-webview.{provider}.com/api/record/weapon/pool
            2. 获取武器池记录:
               GET https://ef-webview.{provider}.com/api/record/weapon
               参数:
                   - pool_id: 武器池ID

        增量同步逻辑:
            与角色池类似，使用 seq_id 实现增量同步。

        异常处理:
            - FetcherError: 网络请求失败、token 无效
        """
        # 存储所有记录
        all_records = []

        # 语言设置
        lang = "zh-cn"

        # 报告进度
        self._report_progress("正在获取武器池列表...", 0.7)

        # ========== 步骤1: 获取武器池列表 ==========
        pool_url = f"https://ef-webview.{provider}.com/api/record/weapon/pool"

        try:
            # 发送请求获取武器池列表
            pool_resp = self._request(pool_url, params={
                "lang": lang,
                "token": u8_token,
                "server_id": server_id,
            })
        except FetcherError:
            # 请求失败，返回空列表
            return all_records

        # 检查 token 错误
        self._check_token_error(pool_resp)

        # 检查业务错误码
        if pool_resp.get("code") != 0:
            return all_records

        # 提取武器池列表
        pools = pool_resp.get("data", [])

        # ========== 步骤2: 遍历每个武器池获取记录 ==========
        for pool in pools:
            # 提取池信息
            pool_id = pool.get("poolId", "")
            pool_name = pool.get("poolName", pool_id)

            # 报告进度
            self._report_progress(f"正在获取武器池: {pool_name}...", 0.8)

            # 获取该池的停止点
            stop_seq_id = (stop_seq_ids or {}).get("weapon", "")

            # 分页参数
            seq_id = ""
            has_more = True

            # 分页循环
            while has_more:
                # 构造请求参数
                params = {
                    "lang": lang,
                    "token": u8_token,
                    "server_id": server_id,
                    "pool_id": pool_id,  # 武器池ID
                }

                # 添加分页游标
                if seq_id:
                    params["seq_id"] = seq_id

                # 构造请求 URL
                url = f"https://ef-webview.{provider}.com/api/record/weapon"

                try:
                    # 发送请求
                    resp = self._request(url, params=params)
                except FetcherError:
                    # 请求失败，停止分页
                    has_more = False
                    break

                # 检查 token 错误
                self._check_token_error(resp)

                # 检查业务错误码
                if resp.get("code") != 0:
                    has_more = False
                    break

                # 提取数据
                data = resp.get("data", {})
                records_list = data.get("list", [])

                # ========== 增量同步 ==========
                if stop_seq_id:
                    # 过滤旧记录
                    new_only = [r for r in records_list
                                if _compare_seq_id(str(r.get("seqId", "")), stop_seq_id) > 0]

                    # 如果遇到旧记录，停止分页
                    if len(new_only) < len(records_list):
                        records_list = new_only
                        has_more = False

                # ========== 解析每条记录 ==========
                for raw in records_list:
                    # 提取武器名称
                    item_name = raw.get("weaponName", "未知")

                    # 提取稀有度
                    rarity = int(raw.get("rarity", 3))

                    # 判断是否为 UP 物品
                    is_featured = (rarity == 6 and item_name not in ENDFIELD_STANDARD_6STAR)

                    # 创建 GachaRecord 对象
                    record = GachaRecord(
                        account_id=0,
                        game="endfield",
                        pool_type="weapon",  # 固定为武器类型
                        pool_name=raw.get("poolName", ""),
                        item_id=str(raw.get("seqId", "")),
                        item_name=item_name,
                        item_type="武器",  # 物品类型为武器
                        rarity=rarity,
                        is_featured=is_featured,
                        count=1,
                        time=_parse_gacha_ts(raw.get("gachaTs", "")),
                        gacha_id=pool_id,
                        raw_data=str(raw),
                    )

                    # 添加到结果列表
                    all_records.append(record)

                # 更新分页状态
                has_more = bool(data.get("hasMore", False))

                # 更新游标
                if records_list:
                    seq_id = records_list[-1].get("seqId", "")

                # 如果还有更多记录，等待 0.5 秒再请求
                # 避免请求过快触发风控
                if has_more:
                    time.sleep(0.5)

        # 返回所有记录
        return all_records

    def _fetch_from_third_party(self, framework_token: str) -> List[GachaRecord]:
        """通过第三方 API 获取抽卡记录（已弃用）

        此方法原本用于通过第三方 API 获取抽卡记录，但该方式已弃用。

        参数:
            framework_token (str): 框架 token（UUID 格式）

        返回:
            List[GachaRecord]: 永远不会返回（总是抛出异常）

        异常:
            FetcherError: 始终抛出，提示用户使用官方方式

        弃用原因:
            - 第三方 API 不稳定
            - 安全性考虑
            - 官方 API 已足够完善
        """
        raise FetcherError(
            "第三方 API 方式已弃用。\n\n"
            "请使用「登录获取」按钮，通过鹰角官网登录获取 Token。"
        )

    def fetch_records(self, url: str = None, account_id: int = None, **kwargs) -> List[GachaRecord]:
        """获取终末地抽卡记录（支持增量同步）

        主入口方法，负责协调整个抽卡记录获取流程。

        参数:
            url (str, optional): Token 或 URL
                - 鹰角账号 Token（约24位）
                - u8_token（100+位）
                - 包含 u8_token 的完整 URL
                - framework_token（36位 UUID，已弃用）
                如果为 None，则尝试从日志文件自动提取
            account_id (int, optional): 账户ID，用于增量同步和数据库记录
            **kwargs: 其他参数（保留接口兼容性）

        返回:
            List[GachaRecord]: 抽卡记录列表，每个 GachaRecord 包含:
                - account_id: 账户ID
                - game: 游戏标识 "endfield"
                - pool_type: 卡池类型 (limited/joint/character/weapon/beginner)
                - pool_name: 卡池名称
                - item_id: 唯一标识（seqId）
                - item_name: 物品名称（角色名或武器名）
                - item_type: 物品类型 ("角色" 或 "武器")
                - rarity: 稀有度（1-6）
                - is_featured: 是否为 UP 物品
                - count: 数量（始终为1）
                - time: 抽卡时间
                - gacha_id: 卡池ID
                - raw_data: 原始API响应数据

        流程说明:
            1. 报告初始进度
            2. 获取已有记录的最大 seq_id（用于增量同步）
            3. 判断 token 类型并获取 u8_token
            4. 获取角色池记录
            5. 获取武器池记录
            6. 设置 account_id
            7. 返回所有记录

        Token 类型判断:
            - HTTP URL: 包含 "ef-webview" 的 URL
            - 短 token (<50字符): 鹰角账号 token，需要交换
            - UUID 格式 (36字符): framework_token，已弃用
            - 长 token (50+字符): u8_token，直接使用

        增量同步机制:
            - 从数据库查询已有记录的最大 seq_id
            - 按卡池类型分别记录停止点
            - 只获取 seq_id 大于停止点的新记录
            - 遇到旧记录时停止分页

        异常处理:
            - FetcherError: 所有业务逻辑错误
        """
        # ========== 步骤1: 报告初始进度 ==========
        self._report_progress("正在获取抽卡凭证...", 0.05)

        # ========== 步骤2: 获取增量同步的停止点 ==========
        # stop_seq_ids 格式: {"pool_type": "max_seq_id"}
        # 例如: {"character": "12345", "limited": "67890", "weapon": "11111"}
        stop_seq_ids = {}

        # 如果提供了 account_id，从数据库查询已有记录
        if account_id:
            import sqlite3  # SQLite 数据库模块
            from core.config import Config  # 配置类

            # 获取数据库配置
            cfg = Config()

            try:
                # 连接数据库
                conn = sqlite3.connect(cfg.db_path)

                # 设置行工厂，返回字典格式的行
                conn.row_factory = sqlite3.Row

                # 查询该账户的所有终末地记录
                # 只需要 pool_type 和 raw_data 字段
                rows = conn.execute(
                    "SELECT pool_type, raw_data FROM gacha_records WHERE account_id=? AND game='endfield'",
                    (account_id,)
                ).fetchall()

                # 关闭数据库连接
                conn.close()

                # 遍历每条记录，找到各池类型的最大 seq_id
                for row in rows:
                    d = dict(row)  # 将 Row 对象转换为字典
                    pool_type = d.get("pool_type", "")
                    raw_str = d.get("raw_data", "")

                    # 跳过无效数据
                    if not pool_type or not raw_str:
                        continue

                    try:
                        # 安全解析 raw_data
                        raw = ast.literal_eval(raw_str)

                        # 提取 seqId
                        sid = str(raw.get("seqId", ""))

                        # 更新该池类型的最大 seq_id
                        if sid:
                            if pool_type not in stop_seq_ids or _compare_seq_id(sid, stop_seq_ids[pool_type]) > 0:
                                stop_seq_ids[pool_type] = sid

                    except Exception:
                        # 解析失败，跳过此记录
                        pass

                # 如果有停止点，报告增量同步信息
                if stop_seq_ids:
                    self._report_progress(f"增量同步，各池最大ID: {stop_seq_ids}", 0.05)

            except Exception:
                # 数据库查询失败，继续全量同步
                pass

        # ========== 步骤3: 判断 token 类型并获取 u8_token ==========
        # Token 类型判断逻辑:
        # - HTTP URL: 包含 "ef-webview" 的完整 URL
        # - 非 HTTP 字符串: 可能是 token
        if url and not url.startswith("http"):
            token = url.strip()

            # 检查是否为 UUID 格式（framework_token）
            # UUID 格式: 36字符，包含4个连字符
            if len(token) == 36 and token.count('-') == 4:
                # framework_token，使用第三方 API（已弃用）
                self._report_progress("使用扫码登录凭证获取记录...", 0.1)
                all_records = self._fetch_from_third_party(token)
            else:
                # 其他短 token，当作鹰角账号 token
                self._report_progress("检测到账号 Token，正在交换...", 0.1)
                try:
                    # 交换获取 u8_token
                    u8_token, provider = self._get_u8_token_from_account(token)

                    # 报告进度
                    self._report_progress("已获取凭证，开始获取记录...", 0.2)

                    # 获取角色池记录
                    all_records = []
                    char_records = self._fetch_char_records(u8_token, provider, stop_seq_ids=stop_seq_ids)
                    all_records.extend(char_records)

                    # 获取武器池记录
                    weapon_records = self._fetch_weapon_records(u8_token, provider, stop_seq_ids=stop_seq_ids)
                    all_records.extend(weapon_records)

                except FetcherError:
                    # 业务逻辑异常，重新抛出
                    raise
                except Exception as e:
                    # 其他异常，包装后抛出
                    raise FetcherError(f"Token 交换失败: {e}")

        elif url and "ef-webview" in url:
            # 包含 "ef-webview" 的 URL，从中提取 u8_token
            u8_token, provider = self._get_u8_token(url)

            # 获取角色池记录
            all_records = []
            char_records = self._fetch_char_records(u8_token, provider, stop_seq_ids=stop_seq_ids)
            all_records.extend(char_records)

            # 获取武器池记录
            weapon_records = self._fetch_weapon_records(u8_token, provider, stop_seq_ids=stop_seq_ids)
            all_records.extend(weapon_records)

        else:
            # 尝试从日志提取
            result = self._find_u8_token_from_log()
            if result:
                u8_token, provider = result

                # 获取角色池记录
                all_records = []
                char_records = self._fetch_char_records(u8_token, provider, stop_seq_ids=stop_seq_ids)
                all_records.extend(char_records)

                # 获取武器池记录
                weapon_records = self._fetch_weapon_records(u8_token, provider, stop_seq_ids=stop_seq_ids)
                all_records.extend(weapon_records)
            else:
                # 所有方式都失败，提示用户
                raise FetcherError(
                    "未找到抽卡凭证。\n\n"
                    "请通过以下方式之一获取：\n"
                    "1. 点击「登录获取」按钮扫码登录\n"
                    "2. 在游戏内打开抽卡记录页面\n"
                    "3. 粘贴鹰角账号 Token"
                )

        # ========== 步骤4: 设置 account_id ==========
        if account_id:
            for r in all_records:
                r.account_id = account_id

        # ========== 步骤5: 报告最终进度 ==========
        # 判断同步类型
        sync_type = "增量" if stop_seq_ids else "全量"

        # 报告完成信息
        self._report_progress(f"{sync_type}同步完成，获取 {len(all_records)} 条新记录", 1.0)

        # 返回所有记录
        return all_records
