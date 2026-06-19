"""数据获取器基类

本模块定义了抽卡记录获取器的基础抽象类 BaseFetcher 和统一错误类 FetcherError。
所有游戏特定的获取器（如原神、崩坏星穹铁道等）都应继承 BaseFetcher，
并实现其中定义的抽象方法，从而获得统一的请求限流、进度回调、异常处理等能力。
"""

# ========================= 标准库导入 =========================

# time 模块提供时间相关函数，本文件主要用于:
#   - time.time()  获取当前 Unix 时间戳（浮点数，单位: 秒）
#   - time.sleep() 暂停线程执行指定秒数，用于请求限流
import time

# requests 是 Python 最常用的 HTTP 客户端库，提供:
#   - requests.Session  会话对象，可复用 TCP 连接、统一管理请求头和 Cookie
#   - requests.exceptions.Timeout          请求超时异常
#   - requests.exceptions.ConnectionError  网络连接失败异常
#   - requests.exceptions.HTTPError        HTTP 状态码非 2xx 异常
import requests

# ABC (Abstract Base Class) 提供抽象基类支持;
# abstractmethod 装饰器标记方法为必须由子类实现的抽象方法，
# 如果子类没有实现，实例化时会抛出 TypeError。
from abc import ABC, abstractmethod

# typing 模块提供类型注解（Type Hints），用于静态分析和 IDE 提示:
#   - List[X]      表示列表，元素类型为 X
#   - Dict[K, V]   表示字典，键类型为 K，值类型为 V
#   - Optional[X]  等价于 X | None，表示可选值
#   - Callable     表示可调用对象（函数、lambda 等），签名可标注参数和返回值
from typing import List, Dict, Optional, Callable

# GachaRecord 是抽卡记录的数据模型（通常是 dataclass 或 Pydantic model），
# 包含字段如: uid, gacha_type, item_id, count, time, name, lang 等，
# 代表从游戏 API 获取的一条原始抽卡记录。
from core.models import GachaRecord

# Config 是全局配置管理器，负责:
#   - 读取/写入配置文件（如 YAML/JSON）
#   - 提供请求间隔、超时时间等网络参数
#   - 管理 API 基础 URL、语言设置等
from core.config import Config


# ========================= 统一错误类 =========================

class FetcherError(Exception):
    """获取器错误 —— 所有由获取器引发的业务异常的统一类型。

    使用统一异常类的好处:
      1. 调用方只需捕获 FetcherError 即可处理所有获取器相关的错误
      2. 错误消息面向用户，可直接展示在 UI 上
      3. 便于在上层做统一的错误分类和重试逻辑

    继承自 Exception，无额外属性。
    实例化时传入 message 字符串即可:
        raise FetcherError("请求超时")
    """
    pass


# ========================= 抽象基类 =========================

class BaseFetcher(ABC):
    """抽卡记录获取器基类。

    设计思路:
      - 所有游戏特定的 Fetcher（如 GenshinFetcher、StarRailFetcher）继承本类
      - 本类提供通用的 HTTP 请求、限流、进度回调等基础设施
      - 子类只需关注"如何构造 URL"和"如何解析响应"两个核心问题
      - 通过 ABC 强制子类实现三个抽象方法，保证接口一致性

    生命周期:
      1. 子类构造函数调用 super().__init__()
      2. 通过 set_progress_callback() 注册进度回调（可选）
      3. 调用 fetch_records() 开始获取数据
      4. 内部自动处理限流、异常、进度汇报
    """

    def __init__(self):
        """初始化获取器的通用状态。

        执行的操作:
          1. 创建 Config 实例，加载配置文件
          2. 创建 requests.Session，复用底层 TCP 连接（连接池），
             避免每次请求都重新建立连接，提高效率
          3. 设置默认 User-Agent 请求头，模拟浏览器访问，
             防止被服务端识别为爬虫而拒绝
          4. 初始化 _last_request_time 为 0，表示"从未请求过"，
             确保首次请求不会被限流
          5. 初始化三个可选回调/状态属性为 None/空字符串

        注意:
          - Config() 每次调用都会读取配置文件并创建新实例
          - User-Agent 只是基础模拟，某些游戏可能还需要其他请求头
        """
        # 加载全局配置，获取请求间隔、超时时间等参数
        self.config = Config()

        # 创建会话对象。Session 内部维护一个连接池（默认 10 个连接），
        # 复用 TCP 连接可显著减少 DNS 解析和 TLS 握手的开销。
        self.session = requests.Session()

        # 设置默认请求头。User-Agent 是服务端判断客户端类型的首要依据。
        # 此处使用 Chrome 浏览器的 UA 字符串，模拟正常浏览器访问。
        # 注意: 实际的游戏 API 可能需要更完整的 UA 或其他头部字段。
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        })

        # 记录上一次请求完成的时间戳（Unix 时间戳，秒）。
        # 初始化为 0，使得 time.time() - 0 永远大于请求间隔，
        # 从而首次调用 _rate_limit() 时不会等待。
        self._last_request_time = 0

        # 进度回调函数，类型为 Callable[[str, float], None]。
        # 签名: callback(message: str, progress: float)
        #   - message: 当前状态描述，如 "已获取 100 条记录"
        #   - progress: 进度百分比 0.0~1.0，或 0~100（取决于具体实现）
        # 未设置时为 None，此时 _report_progress() 不执行任何操作。
        self._progress_callback: Optional[Callable] = None

        # 取消检查函数，类型为 Callable[[], bool]。
        # 每次循环迭代时调用，返回 True 表示用户请求取消。
        # 本基类中未直接使用，但子类可在循环中检查此回调。
        self._cancel_check: Optional[Callable] = None

        # 从响应中自动检测到的用户 UID。
        # 某些游戏的 API 响应中会包含 UID，获取器会将其提取并存储在此，
        # 供后续保存记录时使用。
        # 初始化为空字符串，表示尚未检测到。
        self._detected_uid: str = ""

    def set_progress_callback(self, callback: Callable):
        """设置进度回调函数。

        参数:
            callback: 可调用对象，签名为 (message: str, progress: float) -> None
                      - message: 描述当前进度的文字信息
                      - progress: 数值型进度值，调用方可据此更新进度条

        使用方式:
            fetcher = SomeFetcher()
            fetcher.set_progress_callback(my_ui.update_progress)
            fetcher.fetch_records(...)

        内部行为:
            将 callback 函数引用直接赋值给实例属性 _progress_callback。
            后续每次调用 _report_progress() 时都会检查该属性，
            若不为 None 则执行回调。
        """
        # 将外部传入的回调函数保存到实例属性中
        self._progress_callback = callback

    def _report_progress(self, message: str, progress: float = 0):
        """向已注册的进度回调汇报当前进度。

        参数:
            message:  状态描述字符串，例如 "正在获取第 2 页..."
            progress: 进度值（浮点数），默认为 0。
                      具体含义由调用方约定，可以是 0.0~1.0 或 0~100。

        内部行为:
            1. 检查 _progress_callback 是否已注册（不为 None）
            2. 若已注册，调用 callback(message, progress) 通知 UI 层
            3. 若未注册（为 None），此方法静默返回，不做任何操作

        这种"空对象模式"避免了在每个调用点都做 None 检查，
        使主流程代码更加简洁。
        """
        # 仅在回调已注册时才执行，否则跳过
        if self._progress_callback:
            # 调用回调函数，将进度信息传递给 UI 层
            self._progress_callback(message, progress)

    def _rate_limit(self):
        """请求限流 —— 确保两次请求之间至少间隔 config 指定的时间。

        工作原理（令牌桶 / 固定间隔限流的简化版）:
          1. 从配置中读取最小请求间隔 interval（秒）
          2. 计算距上次请求已经过去的时间 elapsed
          3. 若 elapsed < interval，说明请求过于频繁，
             则 sleep(interval - elapsed) 补齐差额
          4. 更新 _last_request_time 为当前时间

        为什么需要限流:
          - 游戏 API 通常有频率限制（如每秒最多 10 次请求）
          - 过快请求可能触发服务端反爬机制（返回 429 或封 IP）
          - 限流还能降低对服务端的负载，是一种网络礼仪

        注意:
          - time.time() 返回的是单调递增的系统时钟时间（非高精度），
            在 Windows 上精度约为 15.6ms，但对限流场景足够
          - 如果系统时钟被手动调快，elapsed 可能为负，
            此时不会 sleep，直接放行
        """
        # 从配置中获取最小请求间隔（秒）
        interval = self.config.get_request_interval()

        # 计算距上次请求的经过时间
        elapsed = time.time() - self._last_request_time

        # 如果经过时间小于最小间隔，则暂停差额时间
        if elapsed < interval:
            time.sleep(interval - elapsed)

        # 更新上次请求时间为当前时间
        # 注意: 这行在 sleep 之后执行，所以实际间隔会略大于 interval（多出 sleep 精度误差）
        self._last_request_time = time.time()

    def _request(self, url: str, params: dict = None, headers: dict = None) -> dict:
        """发送 HTTP GET 请求并返回解析后的 JSON 响应。

        这是所有网络请求的核心方法，封装了:
          - 限流（自动调用 _rate_limit）
          - 超时控制（从配置中读取）
          - 异常捕获与转换（将 requests 异常转为 FetcherError）

        参数:
            url:     请求的完整 URL 地址，例如
                     "https://webstatic.mihoyo.com/..."
            params:  URL 查询参数字典，例如
                     {"page": 1, "size": 20, "gacha_type": "11"}
                     会被 requests 自动编码为 ?page=1&size=20&...
                     若为 None 则不附加查询参数
            headers: 额外的请求头字典，会与 Session 默认头合并（覆盖同名键）
                     例如 {"Referer": "https://webstatic.mihoyo.com"}
                     若为 None 则仅使用 Session 默认头

        返回值:
            dict —— 解析后的 JSON 响应体。
            成功时通常包含 "data" 和 "retcode" 等字段，例如:
            {
                "retcode": 0,
                "message": "OK",
                "data": {
                    "list": [...],
                    "page": "1",
                    "size": "20",
                    "total": "500"
                }
            }

        异常处理:
            所有 requests 异常都被捕获并转换为 FetcherError，
            对外暴露统一的错误类型，便于调用方处理:

            | 原始异常                      | 转换后的 FetcherError 消息             |
            |-------------------------------|---------------------------------------|
            | requests.exceptions.Timeout   | "请求超时，请检查网络连接"              |
            | requests.exceptions.HTTPError | "HTTP错误: {status_code}"              |
            | requests.exceptions.ConnectionError | "网络连接失败，请检查网络"       |
            | 其他 Exception                | "请求失败: {error_message}"            |

        调用流程:
          1. 调用 _rate_limit() 确保不超过频率限制
          2. 从配置读取超时时间
          3. 发起 GET 请求
          4. 调用 raise_for_status() 检查 HTTP 状态码是否为 2xx
          5. 若状态码正常，解析响应体为 JSON 并返回
          6. 若任何步骤出错，捕获异常并转为 FetcherError 抛出
        """
        # 执行限流，确保两次请求间隔足够
        self._rate_limit()

        # 从配置中获取请求超时时间（秒），通常为 10~30 秒
        # 超时包含"连接超时"和"读取超时"两部分（requests 默认同时适用于两者）
        timeout = self.config.get_request_timeout()

        try:
            # 发起 HTTP GET 请求
            # - url:     目标地址
            # - params:  查询参数，requests 会自动 URL 编码
            # - headers: 额外请求头，与 session 默认头合并
            # - timeout: 超时秒数，超时后抛出 Timeout 异常
            resp = self.session.get(url, params=params, headers=headers, timeout=timeout)

            # 检查 HTTP 状态码。若状态码不在 200~299 范围内，
            # raise_for_status() 会抛出 HTTPError 异常。
            # 例如 403 Forbidden、500 Internal Server Error 都会触发。
            resp.raise_for_status()

            # 将响应体解析为 Python 字典（JSON 反序列化）。
            # 若响应体不是合法 JSON，会抛出 JSONDecodeError
            # （继承自 ValueError，被下方的兜底 except 捕获）。
            return resp.json()

        except requests.exceptions.Timeout:
            # 请求超时 —— 可能原因: 网络慢、服务端无响应、DNS 解析慢
            # 将原始异常信息丢弃，抛出面向用户的中文提示
            raise FetcherError("请求超时，请检查网络连接")

        except requests.exceptions.HTTPError as e:
            # HTTP 状态码错误 —— e.response 是完整的 Response 对象，
            # e.response.status_code 是具体的错误码（如 403、500、429）
            # 将状态码嵌入错误消息，便于排查
            raise FetcherError(f"HTTP错误: {e.response.status_code}")

        except requests.exceptions.ConnectionError:
            # 网络连接失败 —— 可能原因: DNS 解析失败、目标主机不可达、
            # 本地无网络连接、防火墙拦截
            raise FetcherError("网络连接失败，请检查网络")

        except Exception as e:
            # 兜底异常处理 —— 捕获所有其他未预期的异常，
            # 包括但不限于:
            #   - JSONDecodeError（响应体非 JSON）
            #   - UnicodeDecodeError（编码问题）
            #   - ValueError / TypeError（数据解析异常）
            # 将异常信息转为字符串后嵌入 FetcherError 消息中
            raise FetcherError(f"请求失败: {str(e)}")

    # ========================= 抽象方法 =========================
    # 以下三个方法由 @abstractmethod 装饰，子类必须全部实现。
    # 若子类遗漏任何一个，实例化时 Python 会抛出:
    #   TypeError: Can't instantiate abstract class XXX with abstract methods ...
    # 这确保了所有获取器都暴露统一的接口。

    @abstractmethod
    def fetch_records(self, url: str = None, account_id: int = None) -> List[GachaRecord]:
        """获取抽卡记录 —— 这是获取器的核心方法。

        子类必须实现此方法，负责:
          1. 根据 url 和 account_id 构造完整的 API 请求地址
          2. 循环分页请求（通常每页 20 条），直到获取全部记录
          3. 将 API 原始响应解析为 GachaRecord 对象列表
          4. 通过 _report_progress() 汇报获取进度
          5. 检查 _cancel_check 支持用户中途取消
          6. 处理分页参数（page / end_id 等），翻页直到无更多数据

        参数:
            url:        API 基础地址，通常从配置中获取或由调用方传入。
                        例如 "https://webstatic.mihoyo.com/..."
                        若为 None，子类应从配置中读取默认值。
            account_id: 账号 ID（数字类型），用于区分不同账号的记录。
                        某些游戏 API 需要此参数作为查询条件。
                        若为 None，子类应从配置中读取。

        返回值:
            List[GachaRecord] —— 按时间正序排列的抽卡记录列表。
            每个 GachaRecord 包含单次抽卡的完整信息。

        异常:
            可能抛出 FetcherError（通过 self._request() 或手动 raise）。

        注意:
            这是一个抽象方法（pass 仅为语法占位），实际逻辑在子类中实现。
        """
        # 抽象方法无需实现，由子类提供具体逻辑
        pass

    @abstractmethod
    def get_game_name(self) -> str:
        """返回当前获取器对应的游戏名称。

        用于:
          - 在 UI 中显示当前正在处理的游戏
          - 构建存储路径（如 ./data/{game_name}/...）
          - 日志记录和错误提示中标识游戏来源

        子类实现示例:
            def get_game_name(self) -> str:
                return "原神"

        返回值:
            str —— 游戏名称，如 "原神"、"崩坏：星穹铁道"、"绝区零" 等。

        注意:
            抽象方法，子类必须实现。
        """
        pass

    @abstractmethod
    def get_supported_pools(self) -> List[str]:
        """返回当前游戏支持的卡池类型列表。

        卡池类型通常用数字或字符串标识，例如:
          - 原神: ["11", "12", "100"]  （角色池、武器池、常驻池）
          - 崩坏星穹铁道: ["11", "12", "1"]

        用途:
          - 在 UI 中列出可选的卡池供用户选择
          - 验证用户指定的卡池类型是否有效
          - 决定哪些卡池需要获取记录

        返回值:
            List[str] —— 卡池类型标识符列表，每个元素是一个卡池 ID 字符串。

        注意:
            抽象方法，子类必须实现。
        """
        pass
