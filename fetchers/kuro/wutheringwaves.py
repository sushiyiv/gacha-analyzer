# ==============================================================================
# 文件: fetchers/kuro/wutheringwaves.py
# 说明: 鸣潮(Wuthering Waves)抽卡记录获取器
#       鸣潮由库洛游戏(Kuro Games)开发，使用独立于米哈游的API体系
#       主要特点:
#       - API端点: gmserver-api.aki-game2.com (使用POST请求)
#       - 参数格式: 驼峰命名法JSON (如 playerId, cardPoolType)
#       - 支持7种卡池类型(包括新旅唤取等鸣潮特有卡池)
#       - 需要从网页URL中解析hash fragment中的参数
# ==============================================================================

"""鸣潮抽卡记录获取器"""

# ---------- 标准库/第三方库导入 ----------
import requests  # 用于发送HTTP POST请求到鸣潮API服务器
from urllib.parse import parse_qs  # 用于解析URL查询字符串参数

# ---------- 类型注解导入 ----------
from typing import List  # 用于声明返回值类型为列表

# ---------- 项目内部模块导入 ----------
from fetchers.base import BaseFetcher, FetcherError  # 所有获取器的抽象基类及统一错误类型
from fetchers.cache_reader import CacheReader  # 从本地游戏缓存文件中提取抽卡URL的工具
from fetchers.url_parser import URLParser  # URL清洗与校验工具
from core.models import GachaRecord  # 统一的抽卡记录数据模型

# ==================== 卡池类型映射 ====================
# 鸣潮API使用数字编码的 cardPoolType 参数来区分不同卡池
# 本字典将数字编码映射为内部统一的卡池类型名称字符串

CARD_POOL_TYPE_MAP = {
    1: "character",           # 角色活动唤取(限定角色UP池)，编码1
    2: "weapon",              # 武器活动唤取(限定武器UP池)，编码2
    3: "standard_character",  # 角色常驻唤取(标准角色池)，编码3
    4: "standard_weapon",     # 武器常驻唤取(标准武器池)，编码4
    5: "beginner",            # 新手唤取(新手池)，编码5
    8: "selector",            # 角色新旅唤取(可自选角色的特殊池)，编码8
    9: "selector_weapon",     # 武器新旅唤取(可自选武器的特殊池)，编码9
}

# ==================== API返回的中文卡池名映射 ====================
# 鸣潮API有时会返回中文卡池名称(而非数字编码)
# 本字典作为备用映射，当中文名称出现在API响应中时用于确定卡池类型

POOL_NAME_MAP = {
    "角色精准调谐": "character",      # 早期版本的卡池名称
    "角色活动唤取": "character",      # 当前版本的角色活动池名称
    "武器精准调谐": "weapon",        # 早期版本的卡池名称
    "武器活动唤取": "weapon",        # 当前版本的武器活动池名称
    "角色常驻唤取": "standard_character",  # 角色常驻池
    "武器常驻唤取": "standard_weapon",     # 武器常驻池
    "新手唤取": "beginner",               # 新手池
    "新手自选唤取": "beginner",           # 新手自选池(归为新手池)
    "角色新旅唤取": "selector",           # 角色新旅唤取(可自选角色)
    "武器新旅唤取": "selector_weapon",    # 武器新旅唤取(可自选武器)
}

# ==================== 鸣潮常驻5星角色列表 ====================
# 用于判断抽到的5星角色是否为UP(限定)物品
# 不在此列表中的5星角色即为限定/UP角色

STANDARD_5STAR_CHARACTERS = {
    "维里奈",  # 常驻5星角色: Verina (开服常驻)
    "安可",    # 常驻5星角色: Encore (开服常驻)
    "鉴心",    # 常驻5星角色: Jianxin (开服常驻)
    "卡卡罗",  # 常驻5星角色: Calcharo (开服常驻)
    "凌阳",    # 常驻5星角色: Lingyang (开服常驻)
}

# ==================== 鸣潮常驻5星武器列表 ====================
# 用于判断抽到的5星武器是否为UP(限定)物品
# 包含开服5把和3.0版本新增的5把

STANDARD_5STAR_WEAPONS = {
    # ---------- 开服常驻5星武器(5把) ----------
    "浩境粼光",  # 常驻5星武器
    "千古洑流",  # 常驻5星武器
    "停驻之烟",  # 常驻5星武器
    "擎渊怒涛",  # 常驻5星武器
    "漪澜浮录",  # 常驻5星武器

    # ---------- 3.0版本新增常驻5星武器(5把) ----------
    "源能机锋",  # 3.0版本新增常驻5星武器
    "镭射切变",  # 3.0版本新增常驻5星武器
    "相位涟漪",  # 3.0版本新增常驻5星武器
    "脉冲协臂",  # 3.0版本新增常驻5星武器
    "玻色星仪",  # 3.0版本新增常驻5星武器
}

# ==================== 日志模块 ====================

import logging  # 导入Python标准日志模块

logger = logging.getLogger(__name__)
# 创建以当前模块名命名的日志记录器
# __name__ = "fetchers.kuro.wutheringwaves"
# 用于在代码中输出警告/错误级别的日志信息

# ==================== 鸣潮获取器类 ====================


class WutheringWavesFetcher(BaseFetcher):
    """鸣潮抽卡记录获取器

    直接继承 BaseFetcher (而非 MihoyoGachaFetcher)，因为鸣潮使用独立的API体系:
    - API端点: gmserver-api.aki-game2.com (POST请求，JSON格式)
    - URL格式: 鸣潮的URL使用hash fragment传递参数(而非标准query string)
    - 认证方式: 使用 playerId + serverId 等参数，不使用authkey

    获取流程:
    1. 从缓存或用户输入获取鸣潮抽卡记录URL
    2. 解析URL hash fragment中的参数
    3. 遍历7种卡池类型，使用POST请求获取每种卡池的记录
    4. 将原始记录转换为标准GachaRecord对象
    """

    # ==================== API配置 ====================

    API_URL = "https://gmserver-api.aki-game2.com/gacha/record/query"
    # 鸣潮抽卡记录查询API端点
    # aki-game2.com 是库洛游戏的服务器域名
    # 该端点接受POST请求，请求体为JSON格式

    # ==================== 构造方法 ====================

    def __init__(self):
        """初始化鸣潮获取器

        调用父类 BaseFetcher.__init__() 进行基础初始化。
        创建 CacheReader 实例用于从本地缓存中提取抽卡URL。
        初始化 _detected_uid 属性用于存储检测到的玩家ID。
        """
        super().__init__()  # 调用 BaseFetcher 的构造方法
        self.cache = CacheReader()  # 创建缓存读取器，用于从鸣潮本地缓存中提取URL
        self._detected_uid = ""  # 检测到的玩家UID(从URL参数中提取)

    # ==================== 接口实现方法 ====================

    def get_game_name(self) -> str:
        """获取游戏的中文显示名称

        返回:
            str: "鸣潮"，用于进度提示消息中
        """
        return "鸣潮"

    def get_supported_pools(self) -> List[str]:
        """获取鸣潮支持的所有卡池类型

        返回:
            List[str]: 鸣潮支持的7种卡池类型列表:
                - "character":          角色活动唤取
                - "weapon":             武器活动唤取
                - "selector":           角色新旅唤取
                - "selector_weapon":    武器新旅唤取
                - "standard_character": 角色常驻唤取
                - "standard_weapon":    武器常驻唤取
                - "beginner":           新手唤取
        """
        return ["character", "weapon", "selector", "selector_weapon",
                "standard_character", "standard_weapon", "beginner"]

    # ==================== 内部辅助方法 ====================

    def _parse_webview_url(self, url: str) -> dict:
        """从鸣潮网页URL中提取查询参数

        鸣潮的抽卡记录网页URL格式比较特殊，参数不在标准查询字符串中，
        而是在URL的hash fragment部分(即 # 后面)。
        URL格式示例:
            https://...#/record?svr_id=xxx&player_id=xxx&resources_id=xxx&...

        参数:
            url (str): 鸣潮抽卡记录网页的完整URL

        返回:
            dict: 解析后的参数字典，包含:
                - player_id:    玩家ID
                - svr_id:       服务器ID
                - resources_id: 资源ID
                - lang:         语言代码
                - record_id:    记录ID
                如果URL格式不正确则返回空字典
        """
        # 尝试解析hash fragment格式的URL
        if '#' in url:
            # URL中存在 # 分隔符，参数在 # 后面
            hash_part = url.split('#', 1)[1]
            # split('#', 1) 只分割一次，避免URL中多个#号的干扰
            # hash_part 现在是 "#/record?svr_id=xxx&player_id=xxx" 中 "?..." 的部分

            if '?' in hash_part:
                # hash部分中包含 ? ，表示有查询参数
                query = hash_part.split('?', 1)[1]
                # query = "svr_id=xxx&player_id=xxx&resources_id=xxx&..."

                params = parse_qs(query)
                # parse_qs 将查询字符串解析为字典
                # 例如: {"svr_id": ["xxx"], "player_id": ["xxx"]}

                return {k: v[0] for k, v in params.items()}
                # 将每个值从列表中取出第一个元素(因为每个参数只有一个值)

        # 尝试解析标准查询字符串格式的URL(兼容普通URL)
        if '?' in url:
            params = parse_qs(url.split('?', 1)[1])
            return {k: v[0] for k, v in params.items()}

        return {}  # URL格式无法识别，返回空字典

    # ==================== 核心获取方法 ====================

    def fetch_records(self, url: str = None, account_id: int = None,
                      latest_time: str = None) -> List[GachaRecord]:
        """获取鸣潮抽卡记录的主流程方法

        整体流程:
        1. 如果未提供url，从本地游戏缓存中提取
        2. 清洗URL并解析hash fragment中的参数
        3. 逐个卡池类型发送POST请求获取记录
        4. 将原始记录转换为GachaRecord对象并判断是否为UP
        5. 返回完整的抽卡记录列表

        参数:
            url (str, 可选): 鸣潮抽卡记录URL。为None则尝试自动从缓存获取。
            account_id (int, 可选): 账号ID，用于区分不同账号。默认为0。
            latest_time (str, 可选): 增量获取时间参数(预留)。

        返回:
            List[GachaRecord]: 鸣潮抽卡记录列表。

        异常:
            FetcherError: 当URL获取失败、参数缺失、网络错误或用户取消时抛出。
        """
        # ----- 第一步: 获取抽卡URL -----
        if not url:
            # 未提供URL，尝试从本地游戏缓存中自动提取
            self._report_progress("正在从缓存中提取URL...", 0.1)  # 报告进度: 10%
            url = self.cache.extract_url("wutheringwaves")
            # 从缓存中提取鸣潮的抽卡记录URL
            if not url:
                # 缓存中找不到URL，抛出错误并给出操作指引
                raise FetcherError(
                    "无法自动获取鸣潮URL。\n\n"  # 错误标题
                    "请打开鸣潮，进入唤取记录页面，然后切回本程序重试。\n"  # 操作指引
                    "或者手动粘贴唤取记录页面的URL。"  # 备选方案
                )

        # ----- 第二步: 清洗URL并解析参数 -----
        url = URLParser.clean_url(url)  # 清除URL中的转义字符(如 \\u0026 → &)
        params = self._parse_webview_url(url)  # 从URL的hash fragment中提取参数

        if not params.get("player_id"):
            # URL中缺少必要的玩家ID参数，无法发起API请求
            raise FetcherError("URL中缺少必要参数，请重新获取")

        self._detected_uid = params.get("player_id", "")  # 保存检测到的玩家ID

        # ----- 第三步: 定义要获取的卡池类型 -----
        pool_types = [1, 2, 3, 4, 5, 8, 9]
        # 鸣潮支持的7种卡池类型编码:
        # 1=角色活动唤取, 2=武器活动唤取, 3=角色常驻唤取
        # 4=武器常驻唤取, 5=新手唤取, 8=角色新旅唤取, 9=武器新旅唤取

        all_records = []  # 存储所有卡池的原始记录
        total_pools = len(pool_types)  # 卡池类型总数(7)，用于进度计算

        # ----- 第四步: 遍历所有卡池类型，逐个请求 -----
        for pool_idx, card_pool_type in enumerate(pool_types):
            # pool_idx: 当前卡池索引(0-6)
            # card_pool_type: 卡池类型编码(1/2/3/4/5/8/9)

            # ----- 取消检查 -----
            if self._cancel_check and self._cancel_check():
                raise FetcherError("用户取消")
                # 如果用户在获取过程中点击了取消按钮，中断整个流程

            # ----- 确定卡池名称并报告进度 -----
            pool_name = CARD_POOL_TYPE_MAP.get(card_pool_type, "character")
            # 通过编码映射获取卡池名称，未找到则默认为 "character"
            self._report_progress(
                f"正在获取 {pool_name} 记录... ({pool_idx + 1}/{total_pools})",
                (pool_idx + 0.5) / total_pools
                # 进度计算: 当前卡池索引+0.5(表示正在处理中) 除以 总卡池数
                # 使用 +0.5 表示当前卡池处理了一半，使进度更平滑
            )

            try:
                # ----- 发送POST请求到鸣潮API -----
                # 鸣潮API使用POST请求，请求体为JSON格式
                # 注意: 鸣潮API的参数使用驼峰命名法(而非蛇形命名法)
                resp = requests.post(
                    self.API_URL,  # API端点: gmserver-api.aki-game2.com/gacha/record/query
                    json={  # JSON格式的请求体
                        "playerId": params["player_id"],          # 玩家ID(必填)
                        "serverId": params.get("svr_id", ""),     # 服务器ID
                        "cardPoolId": params.get("resources_id", ""),  # 卡池资源ID
                        "cardPoolType": card_pool_type,           # 卡池类型编码(1-9)
                        "languageCode": params.get("lang", "zh-Hans"),  # 语言代码，默认简体中文
                        "recordId": params.get("record_id", ""),  # 记录ID(用于增量获取)
                    },
                    headers={"Content-Type": "application/json"},  # 指定Content-Type为JSON
                    timeout=15,  # 15秒超时(比米哈游的30秒短，因为鸣潮API通常响应更快)
                )
                data = resp.json()  # 将响应体解析为Python字典

            except requests.exceptions.Timeout:
                # HTTP请求超时(15秒内未收到响应)
                raise FetcherError("网络请求超时")
            except requests.exceptions.ConnectionError:
                # 无法建立网络连接(如DNS解析失败、服务器不可达)
                raise FetcherError("网络连接失败")
            except Exception as e:
                # 其他异常(JSON解析错误、未知网络错误等)
                raise FetcherError(f"请求失败: {str(e)}")

            # ----- 检查API业务状态码 -----
            code = data.get("code")
            # 鸣潮API成功状态码是 0 (不同于米哈游的 retcode=0)
            if code != 0:
                msg = data.get("message", data.get("msg", "未知错误"))
                # 鸣潮API的错误消息可能在 "message" 或 "msg" 字段中
                logger.warning(f" {pool_name} (type={card_pool_type}) 获取失败: {msg}")
                # 记录警告日志但不中断，跳过该卡池继续获取其他卡池
                # 某些卡池可能已被移除或当前不可用(如新手池在完成新手任务后)
                continue  # 跳过当前卡池，继续下一个

            # ----- 提取记录并标记卡池类型 -----
            records = data.get("data", [])
            # 鸣潮API直接返回列表(不同于米哈游的 data.list)
            for r in records:
                r["_pool_type"] = pool_name  # 添加内部卡池类型标记
                r["_card_pool_type"] = card_pool_type  # 保存原始数字编码

            all_records.extend(records)  # 将当前卡池的记录追加到总列表

        # ----- 第五步: 将原始记录转换为GachaRecord对象 -----
        result = []  # 存储转换后的GachaRecord列表
        for raw in all_records:
            # ----- 确定卡池类型 -----
            pool_type = raw.get("_pool_type", "character")  # 使用内部标记的卡池类型
            card_pool_name = raw.get("cardPoolType", "")
            # 尝试从API返回的中文卡池名获取(备用映射)
            if card_pool_name in POOL_NAME_MAP:
                pool_type = POOL_NAME_MAP[card_pool_name]
                # 如果中文名在映射表中，使用映射后的类型名(可能覆盖内部标记)

            # ----- 判断是否为UP/限定物品 -----
            rarity = int(raw.get("qualityLevel", 3))
            # qualityLevel: 鸣潮API返回的稀有度等级(3=3星, 4=4星, 5=5星)

            item_name = raw.get("name", "")  # 物品名称

            is_permanent_pool = "常驻" in card_pool_name or "新手" in card_pool_name
            # 判断当前卡池是否为常驻池或新手池
            # 常驻池和新手池中抽到的5星都不算UP

            is_standard_item = (item_name in STANDARD_5STAR_CHARACTERS or
                                item_name in STANDARD_5STAR_WEAPONS)
            # 判断该物品是否在常驻5星列表中(角色或武器)

            # UP判断逻辑: 非常驻池 + 5星稀有度 + 不在常驻列表中 = UP物品
            is_featured = (not is_permanent_pool) and rarity >= 5 and (not is_standard_item)

            # ----- 生成唯一标识ID -----
            unique_id = f"{raw.get('resourceId', '')}_{raw.get('time', '')}_{raw.get('_card_pool_type', '')}"
            # 使用 资源ID + 时间 + 卡池类型编码 组合作为唯一标识
            # 鸣潮API没有返回像米哈游那样的唯一记录ID

            # ----- 组装GachaRecord对象 -----
            record = GachaRecord(
                account_id=account_id or 0,  # 账号ID，默认为0
                game="wutheringwaves",       # 游戏标识固定为 "wutheringwaves"
                pool_type=pool_type,         # 卡池类型(已修正)
                item_id=unique_id,           # 生成的唯一标识
                item_name=raw.get("name", "未知"),  # 物品名称
                item_type=raw.get("resourceType", ""),  # 物品类型(如"角色"、"武器")
                rarity=rarity,               # 稀有度
                is_featured=is_featured,     # 是否为UP物品
                count=int(raw.get("count", 1)),  # 数量，通常为1
                time=raw.get("time", ""),    # 抽卡时间
            )
            result.append(record)  # 追加到结果列表

        # ----- 第六步: 完成并返回结果 -----
        self._report_progress(f"获取完成，共 {len(result)} 条记录", 1.0)
        # 报告进度100%，显示总记录数
        return result  # 返回完整的抽卡记录列表
