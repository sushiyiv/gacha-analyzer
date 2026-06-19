# ==============================================================================
# 文件: fetchers/url_parser.py
# 说明: 抽卡记录URL解析器
#       负责解析用户粘贴的各种格式的抽卡记录API URL
#       支持的URL格式:
#       1. 米哈游系列: 标准query string格式 (authkey=xxx&gacha_type=xxx&...)
#       2. 鸣潮: hash fragment格式 (https://...#/record?player_id=xxx&...)
#       功能:
#       - parse(): 解析URL提取关键信息并判断游戏类型
#       - validate_url(): 验证URL是否为有效的抽卡记录URL
#       - clean_url(): 清洗URL去除转义字符和多余空白
# ==============================================================================

"""URL 解析器 - 解析用户粘贴的抽卡记录 API URL"""

# ---------- 标准库导入 ----------
import re  # 正则表达式模块，用于URL清洗中的空白字符移除
from urllib.parse import urlparse, parse_qs, unquote
# urlparse: 将URL分解为各组成部分(scheme, hostname, path, query等)
# parse_qs: 将查询字符串解析为字典(如 "a=1&b=2" → {"a": ["1"], "b": ["2"]})
# unquote:  将URL编码的字符串解码(如 "%E5%8E%9F%E7%A5%9E" → "原神")

from typing import Dict, Optional  # 类型注解: Dict=字典, Optional=可选类型


class URLParser:
    """抽卡记录 URL 解析器

    提供静态方法用于解析、验证和清洗抽卡记录URL。
    支持米哈游系列(原神/星铁/绝区零)和鸣潮的URL格式。
    不需要实例化，所有方法都是 @staticmethod。
    """

    # ==================== URL解析方法 ====================

    @staticmethod
    def parse(url: str) -> Dict:
        """解析URL，提取关键信息

        本方法是URL解析的核心入口，执行以下步骤:
        1. 解码URL(处理URL编码的中文字符等)
        2. 使用urlparse分解URL各部分
        3. 解析查询字符串参数
        4. 兼容鸣潮的hash fragment格式
        5. 从URL特征推断游戏类型和卡池类型

        参数:
            url (str): 用户粘贴的抽卡记录URL字符串
                       支持包含多余空白、转义字符等不规范格式

        返回:
            Dict: 解析结果字典，包含以下字段:
                - url (str): 清洗后的完整URL
                - host (str): 主机名(如 "public-operation-hk4e.mihoyo.com")
                - path (str): 路径(如 "/gacha_info/api/getGachaLog")
                - params (dict): 所有查询参数的字典
                - authkey (str|None): 认证密钥(米哈游URL中才有)
                - game_biz (str|None): 游戏业务标识(米哈游URL中才有)
                - lang (str|None): 语言代码(如 "zh-cn")
                - region (str|None): 服务器区域标识
                - game (str): 自动检测的游戏标识(可能为空字符串)
                - pool_type (str): 自动检测的卡池类型
        """
        url = unquote(url.strip())
        # 第一步: strip()去除首尾空白字符
        # unquote()解码URL编码的字符(如 %20 → 空格, %E5%8E%9F → "原")

        parsed = urlparse(url)
        # 第二步: 将URL分解为6个部分:
        # - scheme:   协议(如 "https")
        # - netloc:   网络位置(如 "public-operation-hk4e.mihoyo.com")
        # - path:     路径(如 "/gacha_info/api/getGachaLog")
        # - params:   路径参数(通常为空)
        # - query:    查询字符串(如 "authkey=xxx&lang=zh-cn")
        # - fragment: 片段标识(如 "#/record?player_id=xxx")

        params = parse_qs(parsed.query)
        # 第三步: 解析URL的查询字符串部分
        # 返回格式: {"authkey": ["abc123"], "lang": ["zh-cn"]}
        # 每个key对应一个列表，因为同名参数可能有多个值

        # ----- 第四步: 兼容鸣潮URL格式 -----
        # 鸣潮的URL参数不在标准query string中，而是在hash fragment中
        # 例如: https://...#/record?svr_id=xxx&player_id=xxx
        if not params and parsed.fragment and '?' in parsed.fragment:
            # 条件: 标准query为空 + fragment存在 + fragment中包含?
            frag_query = parsed.fragment.split('?', 1)[1]
            # 从fragment中提取?后面的部分作为查询字符串
            params = parse_qs(frag_query)
            # 解析fragment中的查询参数

        # ----- 第五步: 组装解析结果字典 -----
        result = {
            "url": url,           # 清洗后的完整URL
            "host": parsed.hostname,  # 主机名(不含端口)
            "path": parsed.path,      # URL路径
            "params": {k: v[0] if len(v) == 1 else v for k, v in params.items()},
            # 将参数值从列表转换为单个值(如果只有一个元素)
            # 例如: {"lang": ["zh-cn"]} → {"lang": "zh-cn"}
            # 如果有多个同名参数，则保留列表形式

            "authkey": params.get("authkey", [None])[0],
            # 提取authkey参数(米哈游认证密钥)，不存在则为None
            # authkey是米哈游URL中最重要的参数，用于身份验证

            "game_biz": params.get("game_biz", [None])[0],
            # 提取game_biz参数(游戏业务标识)
            # 例如: "hk4e_cn" = 原神国服, "hkrpg_cn" = 星铁国服

            "lang": params.get("lang", [None])[0],
            # 提取lang参数(语言代码)，例如 "zh-cn" = 简体中文

            "region": params.get("region", [None])[0],
            # 提取region参数(服务器区域)，例如 "cn_gf01" = 官服, "cn_e01" = B服
        }

        # ----- 第六步: 自动检测游戏类型和卡池类型 -----
        result["game"] = URLParser._detect_game(url, result)
        # 根据URL特征和参数推断游戏类型

        result["pool_type"] = URLParser._detect_pool_type(url, result)
        # 根据gacha_type参数推断卡池类型

        return result  # 返回完整的解析结果字典

    # ==================== 内部辅助方法: 游戏检测 ====================

    @staticmethod
    def _detect_game(url: str, info: Dict) -> str:
        """根据URL特征自动检测游戏类型

        检测逻辑基于以下URL特征:
        - 原神: URL包含 "hk4e" 或 game_biz 包含 "genshin"
        - 星铁: URL包含 "hkrpg" 或 game_biz 包含 "starrail"
        - 绝区零: URL包含 "nap" 或 game_biz 包含 "zzz"
        - 鸣潮: 主机名包含 "kuro" 或 "aki-game" 或URL包含 "wutheringwaves"
        - 终末地: URL包含 "ef-webview" 或 "endfield"

        参数:
            url (str): 完整URL字符串
            info (Dict): parse()方法已解析的信息字典

        返回:
            str: 游戏标识字符串，无法识别时返回空字符串 ""
        """
        biz = info.get("game_biz", "") or ""
        # 从解析结果中获取game_biz参数，如果为None则使用空字符串
        # 或运算符 "" 用于处理 None 的情况(避免 None in url 出错)

        host = info.get("host", "") or ""
        # 从解析结果中获取主机名

        # ----- 逐个游戏匹配 -----
        if "hk4e" in url or "genshin" in biz.lower():
            # hk4e 是原神的引擎代号(HoYoverse Kaizen 4 Engine)
            # genshin 是原神的英文名，在 game_biz 中出现
            return "genshin"

        elif "hkrpg" in url or "starrail" in biz.lower():
            # hkrpg 是星铁的代号(Honkai: Star Rail)
            # starrail 是星铁的英文标识
            return "starrail"

        elif "nap" in url or "zzz" in biz.lower():
            # nap 是绝区零的代号(Zenless Zone Zero)
            # zzz 是绝区零的简称
            return "zzz"

        elif "kuro" in host.lower() or "aki-game" in host.lower() or "wutheringwaves" in url.lower():
            # kuro = 库洛游戏(Kuro Games，鸣潮开发商)
            # aki-game = 库洛游戏的服务器域名
            # wutheringwaves = 鸣潮的英文名
            return "wutheringwaves"

        elif "ef-webview" in url or "endfield" in url.lower():
            # ef-webview = 终末地的WebView标识
            # endfield = 终末地的英文名
            return "endfield"

        elif "hypergryph" in url.lower() and "endfield" not in url.lower():
            # hypergryph = 鹰角网络(明日方舟开发商)
            # 如果包含hypergryph但不包含endfield，可能是明日方舟
            # 但明日方舟的获取器可能不使用URL方式，暂返回空字符串
            return ""

        return ""  # 无法识别游戏类型

    # ==================== 内部辅助方法: 卡池类型检测 ====================

    @staticmethod
    def _detect_pool_type(url: str, info: Dict) -> str:
        """根据URL参数自动检测卡池类型

        主要通过URL中的 gacha_type 参数来判断卡池类型。
        不同游戏的 gacha_type 编码含义不同，目前仅支持米哈游系列的映射。

        参数:
            url (str): 完整URL字符串(未直接使用，保留接口一致性)
            info (Dict): parse()方法已解析的信息字典

        返回:
            str: 卡池类型字符串，默认返回 "character"
        """
        params = info.get("params", {})
        # 获取URL中解析出的所有参数

        gacha_type = params.get("gacha_type", "")
        # 获取gacha_type参数值(米哈游系列URL中表示卡池类型的数字编码)

        # ----- 米哈游系列gacha_type数字编码映射 -----
        if isinstance(gacha_type, str) and gacha_type.isdigit():
            # 确保gacha_type是数字字符串(如 "1", "2", "301")
            # 注意: 原神和星铁的编码不同:
            # 原神: 1=常驻, 2=角色, 3=武器, 11=新手
            # 星铁: 1=常驻, 2=角色, 3=武器, 11=新手
            # 以下是合并后的通用映射
            type_map = {
                "1": "standard",    # gacha_type=1 → 常驻池
                "2": "character",   # gacha_type=2 → 角色池
                "3": "weapon",      # gacha_type=3 → 武器池
                "11": "beginner",   # gacha_type=11 → 新手池
                "12": "character",  # gacha_type=12 → 角色池(星铁特定)
            }
            return type_map.get(gacha_type, "character")
            # 使用get方法安全查找，未找到则默认返回 "character"

        return "character"
        # gacha_type不存在或非数字时，默认返回 "character"(角色池)

    # ==================== URL验证方法 ====================

    @staticmethod
    def validate_url(url: str) -> bool:
        """验证URL是否是有效的抽卡记录URL

        验证规则:
        1. URL必须以 "http" 开头(支持http和https)
        2. URL必须包含 "authkey=" 参数 或 包含 "gacha"/"GachaLog" 关键词

        参数:
            url (str): 待验证的URL字符串

        返回:
            bool: URL有效返回True，否则返回False
        """
        url = url.strip()  # 去除首尾空白

        if not url.startswith("http"):
            # 必须是http或https协议的URL
            return False

        # 检查是否包含关键特征
        has_authkey = "authkey=" in url
        # 米哈游URL的核心认证参数

        has_gacha = "gacha" in url.lower() or "GachaLog" in url
        # "gacha" 是抽卡的英文，出现在URL路径或参数中
        # "GachaLog" 是部分游戏中使用的URL路径标识

        return has_authkey or has_gacha
        # 满足任一条件即认为是有效的抽卡记录URL

    # ==================== URL清洗方法 ====================

    @staticmethod
    def clean_url(url: str) -> str:
        """清洗URL，去除多余的转义字符和空白

        用户从游戏日志或网页复制的URL可能包含:
        1. Python字符串转义: \\u0026 (应为 &)
        2. URL编码: %26 (应为 &)
        3. 中间插入的空白字符(换行、制表符等)

        参数:
            url (str): 原始URL字符串(可能包含不规范字符)

        返回:
            str: 清洗后的规范URL字符串
        """
        url = url.strip()  # 去除首尾空白字符(包括换行符、制表符等)

        url = url.replace("\\u0026", "&")
        # 将Python的unicode转义序列 \\u0026 替换为实际的 & 字符
        # 这通常发生在从日志文件中复制URL时

        url = url.replace("%26", "&")
        # 将URL编码的 & (%26) 替换为实际的 & 字符
        # 某些场景下 & 会被错误地URL编码

        url = re.sub(r'\s+', '', url)
        # 使用正则表达式移除URL中所有的空白字符(空格、换行、制表符等)
        # \s 匹配任何空白字符, + 表示匹配一个或多个
        # 替换为空字符串，等效于删除所有空白

        return url  # 返回清洗后的URL
