# ==============================================================================
# 文件: fetchers/mihoyo/base.py
# 说明: 米哈游系列游戏抽卡记录获取器的通用基类
#       提供了所有米哈游游戏共用的抽卡记录获取逻辑，包括:
#       - 自动从缓存中提取抽卡URL
#       - URL校验与清洗
#       - 调用通用API获取所有卡池的抽卡记录
#       - 将原始API响应解析为统一的GachaRecord数据模型
#       子类(原神/星铁/绝区零)只需提供游戏标识、显示名等配置即可。
# ==============================================================================

"""米哈游系列游戏抽卡记录通用获取器"""

# ---------- 类型注解导入 ----------
from typing import List  # 用于声明返回值类型为列表

# ---------- 项目内部模块导入 ----------
from fetchers.base import BaseFetcher, FetcherError  # 所有获取器的抽象基类及统一错误类型
from fetchers.mihoyo.api import MihoyoAPI, APIError  # 米哈游通用API封装类及API错误类型
from fetchers.cache_reader import CacheReader  # 从本地游戏缓存文件中提取抽卡URL的工具
from fetchers.url_parser import URLParser  # URL清洗与校验工具
from core.models import GachaRecord  # 统一的抽卡记录数据模型


class MihoyoGachaFetcher(BaseFetcher):
    """米哈游系列抽卡记录获取器基类

    本类封装了米哈游所有游戏(原神、星铁、绝区零)共用的抽卡记录获取流程。
    子类只需设置以下类属性即可适配不同游戏:
      - game_key:       游戏标识字符串(如 "genshin")，用于API端点和数据区分
      - game_name:      游戏中文显示名(如 "原神")，用于进度提示
      - supported_pools: 该支持的卡池类型列表
      - cache_game_key:  本地缓存文件中的游戏标识key
      - url_missing_tip:  当无法自动获取URL时给用户的操作提示
      - expired_tip:     当authkey过期时给用户的操作提示
    """

    # ---------- 类属性声明(子类必须覆盖) ----------

    game_key: str = ""
    # 游戏在米哈游内部的标识字符串，例如 "genshin"、"starrail"、"zzz"
    # 该值会传递给 MihoyoAPI.fetch_all() 用于确定API端点和卡池类型映射

    game_name: str = ""
    # 游戏的中文显示名称，用于进度回调消息中向用户展示当前正在获取哪款游戏的数据

    supported_pools: List[str] = []
    # 当前游戏支持的卡池类型列表，例如 ["character", "weapon", "standard", "beginner"]
    # 该列表会被 get_supported_pools() 方法返回给上层调用者

    cache_game_key: str = ""
    # 用于在 CacheReader 中定位本地缓存文件的游戏标识key
    # CacheReader 会根据此key在对应的缓存目录下查找包含抽卡URL的文件

    url_missing_tip: str = ""
    # 当自动获取URL失败时，向用户展示的操作提示文本(多行字符串)
    # 指导用户如何在游戏中打开抽卡记录页面以便程序抓取URL

    expired_tip: str = ""
    # 当API返回authkey过期错误时，向用户展示的提示文本(多行字符串)
    # 指导用户如何重新获取有效的抽卡URL

    # ---------- 构造方法 ----------

    def __init__(self):
        """初始化获取器实例

        调用父类 BaseFetcher.__init__() 进行基础初始化，
        然后创建米哈游通用API客户端(MihoyoAPI)和缓存读取器(CacheReader)实例。
        这两个工具对象会在后续的 fetch_records() 方法中被使用。
        """
        super().__init__()  # 调用 BaseFetcher 的构造方法，初始化进度回调等基础设施
        self.api = MihoyoAPI()  # 创建米哈游API封装实例，负责实际的HTTP请求和数据解析
        self.cache = CacheReader()  # 创建缓存读取器实例，用于从本地游戏缓存中提取抽卡URL

    # ---------- 公开接口方法 ----------

    def get_game_name(self) -> str:
        """获取当前游戏的中文显示名称

        返回:
            str: 游戏中文名，例如 "原神"、"崩坏：星穹铁道"、"绝区零"
        """
        return self.game_name  # 返回子类设置的游戏名

    def get_supported_pools(self) -> List[str]:
        """获取当前游戏支持的所有卡池类型

        返回:
            List[str]: 卡池类型字符串列表，例如 ["character", "weapon", "standard", "beginner"]
                       注意: 返回的是副本(safe copy)，外部修改不会影响内部数据
        """
        return list(self.supported_pools)  # 使用 list() 创建副本返回，防止外部意外修改

    def fetch_records(self, url: str = None, account_id: int = None, latest_time: str = None) -> List[GachaRecord]:
        """获取抽卡记录的主流程方法

        整体流程:
        1. 如果未提供url，则尝试从本地游戏缓存中自动提取抽卡URL
        2. 对URL进行清洗(去除转义字符等)和有效性校验
        3. 调用 MihoyoAPI.fetch_all() 分页获取所有卡池的抽卡记录
        4. 将每条原始API响应记录解析为GachaRecord对象
        5. 返回完整的抽卡记录列表

        参数:
            url (str, 可选): 抽卡记录的API URL。如果为None则尝试自动从缓存获取。
            account_id (int, 可选): 账号ID，用于区分不同账号的记录。默认为0。
            latest_time (str, 可选): 增量获取的截止时间，仅获取该时间之后的新记录。
                                     注意: 当前实现中此参数主要用于未来扩展。

        返回:
            List[GachaRecord]: 解析后的抽卡记录列表，按时间顺序排列。

        异常:
            FetcherError: 当URL获取失败、URL无效、API调用出错或用户取消操作时抛出。
        """
        # ----- 第一步: 获取抽卡URL -----
        if not url:
            # 未提供URL，尝试从本地游戏缓存文件中自动提取
            self._report_progress("正在从缓存中提取URL...", 0.1)  # 报告进度: 10%
            url = self.cache.extract_url(self.cache_game_key)  # 从缓存中提取对应游戏的抽卡URL
            if not url:
                # 缓存中也找不到URL，抛出错误并给出用户操作指引
                raise FetcherError(
                    "无法自动获取URL。\n\n"  # 错误标题
                    "请按以下步骤操作：\n"   # 操作指引标题
                    f"{self.url_missing_tip}\n\n"  # 子类提供的具体操作步骤
                    "或者手动粘贴抽卡记录URL。"  # 备选方案: 手动粘贴URL
                )

        # ----- 第二步: 清洗和校验URL -----
        url = URLParser.clean_url(url)  # 清除URL中的转义字符(如 \\u0026 → &)和多余空白
        if not URLParser.validate_url(url):
            # URL不合法(不是http开头或缺少关键参数)，抛出错误
            raise FetcherError("无效的URL，请检查后重试")

        # ----- 第三步: 调用API获取原始记录 -----
        self._report_progress("正在获取抽卡记录...", 0.3)  # 报告进度: 30%

        try:
            # 调用MihoyoAPI.fetch_all()，它会自动遍历所有卡池类型并分页获取
            # 参数说明:
            #   self.game_key: 游戏标识(如 "genshin")，决定使用哪个API端点和卡池映射
            #   url: 已清洗的抽卡URL，包含authkey等认证参数
            #   self._report_progress: 进度回调函数，API内部会在每个关键步骤调用它
            #   latest_time: 增量获取时间参数
            #   cancel_check: 取消检查回调，用户点击取消时返回True
            # 返回值: (原始记录列表, 检测到的UID) 元组
            raw_records, detected_uid = self.api.fetch_all(
                self.game_key,
                url,
                self._report_progress,
                latest_time,
                cancel_check=self._cancel_check,
            )
        except APIError as e:
            # API调用出错，需要判断错误类型并给出相应提示
            error_msg = str(e)
            if any(keyword in error_msg.lower() for keyword in ["authkey", "expired", "过期"]):
                # authkey过期错误: 提供用户友好的过期提示
                raise FetcherError(self.expired_tip or f"authkey 已过期，请重新获取。\n原始信息：{error_msg}")
            # 其他API错误: 直接传递原始错误信息
            raise FetcherError(error_msg)

        # ----- 第四步: 解析原始记录为GachaRecord对象 -----
        self._report_progress("正在解析记录...", 0.8)  # 报告进度: 80%

        records = []  # 存储解析后的GachaRecord对象列表
        for raw in raw_records:
            # MihoyoAPI.parse_record() 是一个静态方法，负责:
            # 1. 提取并修正稀有度(rarity)
            # 2. 判断是否为UP角色/武器(is_featured)
            # 3. 确定卡池类型(pool_type)
            # 4. 将原始字典转换为GachaRecord数据对象
            record = MihoyoAPI.parse_record(raw, self.game_key, account_id or 0)
            records.append(record)

        # ----- 第五步: 完成并返回结果 -----
        self._detected_uid = detected_uid  # 保存检测到的UID，供上层使用
        self._report_progress(f"获取完成，共 {len(records)} 条记录", 1.0)  # 报告进度: 100%
        return records  # 返回完整的解析后记录列表
