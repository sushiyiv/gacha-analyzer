# ==============================================================================
# 文件: fetchers/mihoyo/api.py
# 说明: 米哈游通用抽卡记录API封装
#       封装了米哈游三款游戏(原神/星铁/绝区零)的抽卡记录API调用逻辑:
#       - 自动识别游戏类型并选择对应的API端点
#       - 自动遍历所有卡池类型并分页获取记录
#       - 提供通用的单条记录解析逻辑(稀有度转换、UP判断等)
#       - 提供常驻5星角色/武器列表用于UP判断
# ==============================================================================

"""米哈游通用 API 调用"""

# ---------- 标准库导入 ----------
import requests  # 用于发送HTTP GET/POST请求到米哈游API服务器
from typing import List, Dict, Optional  # 类型注解: List=列表, Dict=字典, Optional=可选类型
from urllib.parse import urlparse, parse_qs  # 用于URL解析: urlparse解析URL各部分, parse_qs解析查询参数

# ---------- 项目内部模块导入 ----------
from core.models import GachaRecord  # 统一的抽卡记录数据模型
from core.config import Config  # 应用全局配置(如日志级别、代理设置等)


class MihoyoAPI:
    """米哈游抽卡记录API封装类

    本类封装了米哈游系列游戏的抽卡记录查询API，主要功能:
    1. fetch_all(): 分页获取指定游戏所有卡池类型的全部抽卡记录
    2. parse_record(): 将单条API原始记录解析为标准GachaRecord对象
    3. 内置各游戏的API端点地址、卡池类型编码映射、常驻5星角色/武器列表

    使用方式:
        api = MihoyoAPI()
        records, uid = api.fetch_all("genshin", url, progress_callback)
    """

    # ==================== API 端点配置 ====================
    # 不同游戏使用不同的米哈游API服务器端点
    # 这些是公开可访问的抽卡记录查询接口(无需登录态)
    ENDPOINTS = {
        "genshin": "https://public-operation-hk4e.mihoyo.com/gacha_info/api/getGachaLog",
        # 原神: hk4e = HoYoverse Kaizen 4 Engine (原神引擎代号)
        # 该端点用于查询原神的祈愿记录

        "starrail": "https://public-operation-hkrpg.mihoyo.com/common/gacha_record/api/getGachaLog",
        # 崩坏：星穹铁道: hkrpg = Honkai: Star Rail
        # 该端点用于查询星铁的跃迁记录

        "zzz": "https://public-operation-nap.mihoyo.com/common/gacha_record/api/getGachaLog",
        # 绝区零: nap = Zenless Zone Zero (ZZZ)
        # 该端点用于查询绝区零的调频记录
    }

    # ==================== 卡池类型编码映射 ====================
    # 米哈游API使用数字编码来区分不同的卡池类型
    # 每个游戏的编码方案不同，这里统一管理映射关系
    GACHA_TYPES = {
        "genshin": {
            "character": "301",   # 角色活动祈愿(限定角色UP池)，编码301
            "weapon": "302",      # 武器活动祈愿(限定武器UP池)，编码302
            "chronicled": "400",  # 集录祈愿(往期UP角色复刻池)，编码400
            "standard": "200",    # 常驻祈愿(标准池)，编码200
            "beginner": "100",    # 初次相遇(新手池)，编码100
        },
        "starrail": {
            "character": "11",     # 角色活动跃迁(限定角色UP池)，编码11
            "weapon": "12",        # 光锥活动跃迁(限定武器UP池)，编码12
            "standard": "1",       # 常驻跃迁(标准池)，编码1
            "beginner": "2",       # 始发跃迁(新手池)，编码2
            "collab": "13",        # 联动角色跃迁，编码13
            "collab_weapon": "14", # 联动光锥跃迁，编码14
        },
        "zzz": {
            "character": "2001",       # 频调(角色UP池)，编码2001
            "weapon": "3001",          # 音擎调频(音擎UP池)，编码3001
            "special": "4001",         # 特殊频道(限定角色池)，编码4001
            "special_weapon": "5001",  # 特殊频道音擎(限定音擎池)，编码5001
            "bangboo": "6001",         # 邦布调频(邦布池)，编码6001
            "standard": "1001",        # 常驻调频(标准池)，编码1001
        },
        "wutheringwaves": {
            "character": "1",              # 角色活动唤取，编码1
            "weapon": "2",                 # 武器活动唤取，编码2
            "standard_character": "3",     # 角色常驻唤取，编码3
            "standard_weapon": "4",        # 武器常驻唤取，编码4
            "beginner": "5",               # 新手唤取，编码5
            "selector": "8",               # 角色新旅唤取，编码8
            "selector_weapon": "9",        # 武器新旅唤取，编码9
        },
    }

    # ==================== 构造方法 ====================

    def __init__(self):
        """初始化米哈游API客户端

        创建 Config 实例用于获取应用配置信息。
        Config 是全局单例，包含日志、代理等配置。
        """
        self.config = Config()  # 实例化全局配置，可能在后续请求中用于获取代理或超时设置

    # ==================== 核心获取方法 ====================

    def fetch_all(self, game: str, url: str, progress_callback=None, latest_time: str = None, cancel_check=None) -> List[Dict]:
        """获取指定游戏所有卡池类型的全部抽卡记录

        本方法是整个获取流程的核心，执行以下步骤:
        1. 解析输入URL，提取认证参数(authkey等)
        2. 根据游戏类型选择对应的API端点
        3. 遍历该游戏的所有卡池类型
        4. 对每个卡池类型，分页请求直到获取全部记录或达到页数限制
        5. 在每页请求中检测UID、处理取消操作、报告进度
        6. 返回所有记录的原始字典列表和检测到的UID

        参数:
            game (str): 游戏标识，必须是 ENDPOINTS 和 GACHA_TYPES 中已定义的key
                        可选值: "genshin", "starrail", "zzz"
            url (str): 包含authkey等认证参数的完整抽卡记录URL
                       格式示例: https://public-operation-hk4e.mihoyo.com/gacha_info/api/getGachaLog?authkey=xxx&...
            progress_callback (callable, 可选): 进度回调函数，签名为 (message: str, progress: float) -> None
                                               progress为0.0~1.0之间的浮点数，表示完成百分比
            latest_time (str, 可选): 增量获取的截止时间字符串，格式 "YYYY-MM-DD HH:MM:SS"
                                    注意: 当前实现中此参数未被使用，所有记录都会被获取
            cancel_check (callable, 可选): 取消检查回调，签名为 () -> bool
                                          返回True时中止获取并抛出APIError

        返回:
            tuple: (all_records, detected_uid)
                - all_records (List[Dict]): 所有卡池的原始记录列表，每条记录是一个字典
                  字典中会额外添加 "_pool_type" 字段标识所属卡池类型
                - detected_uid (str): 从记录中检测到的玩家UID字符串

        异常:
            APIError: 当网络请求失败、API返回错误、authkey过期或用户取消时抛出
        """
        # ---------- 第一步: 解析URL并提取基础参数 ----------
        parsed = urlparse(url)  # 将URL分解为: scheme(协议), hostname(主机), path(路径), query(查询)等部分

        base_params = parse_qs(parsed.query)
        # parse_qs将查询字符串解析为字典，每个key对应一个列表(因为同名参数可能有多个值)
        # 例如: "authkey=abc&lang=zh-cn" → {"authkey": ["abc"], "lang": ["zh-cn"]}

        # ---------- 第二步: 选择API端点 ----------
        endpoint = self.ENDPOINTS.get(game)
        # 从预定义端点字典中获取对应游戏的API地址
        if not endpoint:
            # 如果游戏中没有预定义端点(如第三方游戏)，从输入URL中推断端点
            # 保持原URL的 scheme + hostname + path 作为API端点
            endpoint = f"{parsed.scheme}://{parsed.hostname}{parsed.path}"

        # ---------- 第三步: 提取认证参数 ----------
        # 只保留API所需的认证和标识参数，丢弃其他无关参数
        # 这些参数是从用户URL中提取的，包含认证密钥和游戏标识信息
        auth_params = {}
        for key in ["authkey", "authkey_ver", "sign_type", "game_biz", "region", "auth_appid", "plat_type", "lang"]:
            if key in base_params:
                auth_params[key] = base_params[key][0]
                # base_params[key] 是一个列表，取第一个元素(通常是唯一的值)

        # ---------- 第四步: 初始化获取状态 ----------
        all_records = []       # 存储所有卡池的所有记录
        detected_uid = ""      # 从记录中检测到的玩家UID
        end_id = "0"           # 分页游标: 上一页最后一条记录的ID，用于下一页的end_id参数
        page = 1               # 当前页码，从1开始
        gacha_types = self.GACHA_TYPES.get(game, {})
        # 获取该游戏的卡池类型映射字典，如 genshin → {"character": "301", ...}
        total_pools = len(gacha_types)  # 该游戏的卡池类型总数，用于计算进度百分比
        current_pool_idx = 0  # 当前正在处理的卡池索引，用于进度计算

        # ---------- 第五步: 遍历所有卡池类型 ----------
        for pool_name, gacha_type_id in gacha_types.items():
            # pool_name: 卡池类型名称(如 "character", "weapon")
            # gacha_type_id: 对应的API编码(如 "301", "302")

            pool_progress = current_pool_idx / total_pools
            # 当前卡池的基础进度值，表示已完成的卡池占比
            # 例如3个卡池中的第2个: 1/3 ≈ 0.33

            page = 1        # 每个新卡池从第1页开始
            end_id = "0"    # 每个新卡池从ID "0" 开始(表示从最早记录开始)
            pool_total = 0  # 当前卡池已获取的记录总数
            pool_start_idx = len(all_records)  # 记录当前卡池在总列表中的起始位置

            if progress_callback:
                progress_callback(f"开始获取 {pool_name} 记录...", pool_progress)
                # 报告当前卡池的获取开始，进度为该卡池的基础进度值

            # ---------- 第六步: 分页获取当前卡池的所有记录 ----------
            while True:
                # ----- 取消检查 -----
                if cancel_check and cancel_check():
                    # 用户请求取消，抛出APIError中断整个获取流程
                    raise APIError("用户取消")

                # ----- 构建请求参数 -----
                params = {
                    **auth_params,           # 展开认证参数(authkey, game_biz, region等)
                    "lang": "zh-cn",         # 强制使用中文语言(确保返回中文名称)
                    "gacha_type": gacha_type_id,  # 当前卡池类型的API编码
                    "page": str(page),       # 页码(字符串类型)
                    "size": "20",            # 每页记录数，API最大支持20条
                    "end_id": end_id,        # 分页游标，返回ID > end_id 的记录
                }

                # ----- 调试日志 -----
                if page <= 3 or page % 10 == 0:
                    # 前3页和之后每10页打印一次调试信息，避免日志过多
                    print(f"[DEBUG] 获取 {pool_name} 第{page}页, end_id={end_id}")

                try:
                    # ----- 发送HTTP请求 -----
                    resp = requests.get(endpoint, params=params, timeout=30)
                    # 使用GET请求，参数会自动拼接到URL查询字符串中
                    # timeout=30 表示30秒超时，避免网络卡住时无限等待

                    # ----- 解析JSON响应 -----
                    try:
                        data = resp.json()  # 将响应体解析为Python字典
                    except Exception as e:
                        # JSON解析失败(可能是服务器返回了HTML错误页面)
                        raise APIError(f"解析响应失败: {str(e)}\n响应内容: {resp.text[:200]}")
                        # 截取响应内容前200字符作为错误信息的一部分，便于调试

                    # ----- 检查API业务状态码 -----
                    if data.get("retcode") != 0:
                        # retcode不为0表示业务层错误(如参数错误、认证失败等)
                        msg = data.get("message", "未知错误")  # 获取错误消息
                        msg_lower = msg.lower()  # 转小写用于不区分大小写的匹配
                        if "authkey" in msg_lower or "auth key" in msg_lower or "expired" in msg_lower or "time out" in msg_lower:
                            # authkey相关错误，通常是URL过期(一般有效期为几个小时)
                            raise APIError("authkey 已过期，请重新获取")
                        raise APIError(f"API 错误: {msg}")  # 其他业务错误

                    # ----- 提取记录列表 -----
                    records = data.get("data", {}).get("list", [])
                    # API响应结构: {"retcode": 0, "message": "OK", "data": {"list": [...], "size": 20}}
                    # 如果list为空，说明当前卡池的记录已全部获取完毕
                    if not records:
                        if progress_callback:
                            progress_callback(f"{pool_name} 获取完成，共 {pool_total} 条", pool_progress + 1.0 / total_pools)
                            # 报告当前卡池获取完成，进度推进一个完整卡池的份额
                        break  # 跳出内层while循环，开始处理下一个卡池

                    # ----- 从记录中提取UID -----
                    if not detected_uid:
                        # 只在首次检测到UID时进行，避免重复遍历
                        for r in records:
                            if r.get("uid"):
                                detected_uid = str(r["uid"])  # 记录中第一个出现的UID
                                break  # 找到后立即停止遍历

                    # ----- 标记卡池类型并追加到总列表 -----
                    for record in records:
                        record["_pool_type"] = pool_name
                        # 在每条原始记录字典中添加"_pool_type"字段
                        # 这是内部标记字段，后续 parse_record() 会读取它来确定卡池类型

                    all_records.extend(records)  # 将本页记录追加到总记录列表
                    pool_total += len(records)   # 累加当前卡池的记录计数
                    end_id = records[-1].get("id", "0")  # 取本页最后一条记录的ID作为下一页的游标
                    page += 1                     # 页码递增

                    # ----- 报告页级进度 -----
                    if progress_callback:
                        page_progress = min(page / 100, 1.0) / total_pools
                        # 页级进度: 假设每卡池最多约100页，取min防止超出1.0
                        # 再除以 total_pools 得到该页在整体进度中的份额
                        progress_callback(f"正在获取 {pool_name} 记录... 第{page-1}页 ({pool_total}条)", pool_progress + page_progress)

                    # ----- 安全限制: 最多100页 -----
                    if page > 100:
                        # 防止因异常情况(如API持续返回数据)导致无限循环
                        # 正常情况下每个卡池的记录不太可能超过100页(2000条)
                        if progress_callback:
                            progress_callback(f"{pool_name} 达到页数限制，共 {pool_total} 条", pool_progress + 1.0 / total_pools)
                        break  # 跳出内层while循环

                # ----- 网络异常处理 -----
                except requests.exceptions.Timeout:
                    # HTTP请求超时(30秒内未收到响应)
                    raise APIError("网络请求超时，请检查网络连接后重试")
                except requests.exceptions.ConnectionError:
                    # 无法建立网络连接(如DNS解析失败、服务器不可达)
                    raise APIError("网络连接失败，请检查网络连接后重试")
                except requests.exceptions.RequestException as e:
                    # 其他网络相关异常(如SSL证书错误、重定向过多等)
                    raise APIError(f"网络请求失败: {str(e)}")

            # ----- 当前卡池处理完毕，进入下一个 -----
            # API 返回记录是 newest-first，反转为 oldest-first
            # 这样插入数据库后 ID 顺序与实际抽卡顺序一致，
            # calculate_pity_counts 的 ORDER BY time ASC, id ASC 才能正确计算保底
            all_records[pool_start_idx:] = reversed(all_records[pool_start_idx:])
            current_pool_idx += 1

        # ---------- 返回最终结果 ----------
        return all_records, detected_uid
        # all_records: 所有卡池的所有原始记录字典列表
        # detected_uid: 从记录中检测到的玩家UID(可能为空字符串)

    # ==================== 常驻5星角色/武器列表 ====================
    # 用于判断抽到的5星角色/武器是否为UP(限定)物品
    # 逻辑: 如果5星物品不在常驻列表中，则判定为UP物品
    STANDARD_5STAR = {
        "genshin": {
            "character": [
                "梦见月瑞希",  # 常驻5星角色: Mualani (5.0新增)
                "迪希雅",     # 常驻5星角色: Dehya (3.5新增)
                "提纳里",     # 常驻5星角色: Tighnari (3.0新增，首位进入常驻的限定角色)
                "刻晴",       # 常驻5星角色: Keqing (开服常驻)
                "莫娜",       # 常驻5星角色: Mona (开服常驻)
                "七七",       # 常驻5星角色: Qiqi (开服常驻)
                "迪卢克",     # 常驻5星角色: Diluc (开服常驻)
                "琴",         # 常驻5星角色: Jean (开服常驻)
            ],
            "weapon": [
                "天空之刃",   # 常驻5星武器: Aquila Favonia (开服常驻)
                "风鹰剑",     # 常驻5星武器: Skyward Blade (开服常驻)
                "狼的末路",   # 常驻5星武器: Wolf's Gravestone (开服常驻)
                "天空之傲",   # 常驻5星武器: Skyward Pride (开服常驻)
                "和璞鸢",     # 常驻5星武器: Primordial Jade Winged-Spear (开服常驻)
                "天空之脊",   # 常驻5星武器: Skyward Spine (开服常驻)
                "四风原典",   # 常驻5星武器: Lost Prayer to the Sacred Winds (开服常驻)
                "天空之卷",   # 常驻5星武器: Skyward Atlas (开服常驻)
                "阿莫斯之弓", # 常驻5星武器: Amos' Bow (开服常驻)
                "天空之翼",   # 常驻5星武器: Skyward Harp (开服常驻)
            ],
        },
        "starrail": {
            "character": [
                "布洛妮娅",  # 常驻5星角色: Bronya
                "克拉拉",    # 常驻5星角色: Clara
                "杰帕德",    # 常驻5星角色: Gepard
                "白露",      # 常驻5星角色: Bailu
                "姬子",      # 常驻5星角色: Himeko
                "瓦尔特",    # 常驻5星角色: Welt
                "彦卿",      # 常驻5星角色: Yanqing
            ],
            "weapon": [
                "但战斗还未结束",  # 常驻5星光锥: But the Battle Isn't Over
                "时节不居",       # 常驻5星光锥: Time Waits for No One
                "无可取代的东西",  # 常驻5星光锥: Something Irreplaceable
                "银河铁道之夜",   # 常驻5星光锥: Night on the Galactic Railroad
                "制胜的瞬间",     # 常驻5星光锥: Moment of Victory
                "如泥酣眠",       # 常驻5星光锥: Sleep Like the Dead
                "以世界之名",     # 常驻5星光锥: In the Name of the World
            ],
        },
        "zzz": {
            "character": [
                "莱卡恩",  # 常驻5星角色: Lycaon
                "11号",    # 常驻5星角色: Soldier 11
                "珂蕾妲",  # 常驻5星角色: Koleda
                "丽娜",    # 常驻5星角色: Rina
                "格莉丝",  # 常驻5星角色: Grace
                "猫又",    # 常驻5星角色: Nekomata
            ],
            "weapon": [
                "硫磺石",       # 常驻5星音擎: Hellfire Demon
                "燃狱齿轮",     # 常驻5星音擎: The Brimstone
                "钢铁肉垫",     # 常驻5星音擎: Steel Cushion
                "啜泣摇篮",     # 常驻5星音擎: Weeping Cradle
                "嵌合编译器",   # 常驻5星音擎: Unfettered Game
                "拘缚者",       # 常驻5星音擎: The Restrainer
            ],
        },
        "wutheringwaves": {
            "character": [
                "维里奈",  # 常驻5星角色: Verina
                "安可",    # 常驻5星角色: Encore
                "鉴心",    # 常驻5星角色: Jianxin
                "卡卡罗",  # 常驻5星角色: Calcharo
                "凌阳",    # 常驻5星角色: Lingyang
            ],
            "weapon": [
                "浩境粼光",  # 常驻5星武器
                "千古洑流",  # 常驻5星武器
                "停驻之烟",  # 常驻5星武器
                "擎渊怒涛",  # 常驻5星武器
                "漪澜浮录",  # 常驻5星武器
                "源能机锋",  # 3.0版本新增常驻5星武器
                "镭射切变",  # 3.0版本新增常驻5星武器
                "相位涟漪",  # 3.0版本新增常驻5星武器
                "脉冲协臂",  # 3.0版本新增常驻5星武器
                "玻色星仪",  # 3.0版本新增常驻5星武器
            ],
        },
        "endfield": {
            # 明日方舟: 终末地 (Endfield) 的常驻5星角色和武器
            "character": [
                "骏卫",     # 常驻5星角色
                "余烬",     # 常驻5星角色
                "艾尔黛拉", # 常驻5星角色
                "别礼",     # 常驻5星角色
                "黎风",     # 常驻5星角色
            ],
            "weapon": [
                # 单手剑类常驻5星武器
                "热熔切割器", "不知归", "宏愿", "显赫声名", "扶摇", "白夜新星", "光荣记忆", "黯色火炬",
                # 双手剑类常驻5星武器
                "破碎君王", "大雷斑", "昔日精品", "赫拉芬格", "典范",
                # 长柄武器类常驻5星武器
                "负山", "骁勇", "J.E.T.",
                # 手铳类常驻5星武器
                "同类相食", "楔子", "望乡", "领航者",
                # 施术单元类常驻5星武器
                "爆破单元", "沧溟星梦", "骑士精神", "遗忘", "悼亡诗",
            ],
        },
    }

    # ==================== 可歪5星角色列表(含加入时间) ====================
    # 格式: { (game, pool_type): { "角色名": "加入可歪池的时间(YYYY-MM-DD)" } }
    # 用于判断某个5星角色在抽卡时间点是否为UP状态
    # 如果角色在抽卡时间之前就已经加入可歪池，则不算UP
    LOSEABLE_5STAR_WITH_DATE = {
        ("starrail", "character"): {
            # 星铁角色活动池的可歪角色及其加入时间
            # "星缘相邀" 机制: 限定角色在后续版本中加入常驻歪池

            "希儿": "2025-04-09",
            # 希儿 (Seele) 于2025年4月9日版本更新后加入可歪池
            # 在此日期之前的抽卡中抽到希儿算UP，之后算歪

            "刃": "2025-04-09",
            # 刃 (Blade) 于2025年4月9日版本更新后加入可歪池

            "符玄": "2025-04-09",
            # 符玄 (Fu Xuan) 于2025年4月9日版本更新后加入可歪池

            "云璃": "2026-04-22",
            # 云璃 (Yunli) 于2026年4月22日版本更新后加入可歪池

            "银枝": "2026-04-22",
            # 银枝 (Silver Wolf) 于2026年4月22日版本更新后加入可歪池

            "银狼": "2026-04-22",
            # 银狼 (Silver Wolf) 于2026年4月22日版本更新后加入可歪池
        },
    }

    # ==================== 明日方舟限定角色列表 ====================
    # 明日方舟的卡池机制: 限定角色只在限定池出现，非限定角色在常驻池也可获取
    # 用于判断抽到的6星干员是否为限定(UP)角色
    ARKNIGHTS_LIMITED = {
        # ---------- 限定干员 ----------
        "年",                  # 年 (Nian) - 联动限定
        "W",                   # W - 限定干员
        "迷迭香",              # 迷迭香 (Rosmontis) - 限定干员
        "夕",                  # 夕 (Dusk) - 限定干员
        "浊心斯卡蒂",          # 浊心斯卡蒂 (Skadi the Corrupting Heart) - 限定干员
        "假日威龙陈",          # 假日威龙陈 (Ch'en the Holungday) - 限定干员
        "耀骑士临光",          # 耀骑士临光 (Nearl the Radiant Knight) - 限定干员
        "令",                  # 令 (Ling) - 限定干员
        "归溟幽灵鲨",          # 归溟幽灵鲨 (Specter the Unchained) - 限定干员
        "百炼嘉维尔",          # 百炼嘉维尔 (Gavial the Invincible) - 限定干员
        "缄默德克萨斯",        # 缄默德克萨斯 (Texas the Omertosa) - 限定干员
        "重岳",                # 重岳 (Chongyue) - 限定干员
        "缪尔赛思",            # 缪尔赛思 (Muelsyse) - 限定干员
        "纯烬艾雅法拉",        # 纯烬 Eyjafjalla - 限定干员
        "塑心",                # 塑心 (Virtuosa) - 限定干员
        "黍",                  # 黍 (Shu) - 限定干员
        "维什戴尔",            # 维什戴尔 (Wis'adel) - 限定干员
        "佩佩",                # 佩佩 (Pepe) - 限定干员
        "荒芜拉普兰德",        # 荒芜拉普兰德 (Lappland the Darlington) - 限定干员
        "余",                  # 余 - 限定干员
        "新约能天使",          # 新约能天使 (Exusiai the New Covenant) - 限定干员
        "斩业星熊",            # 斩业星熊 (Hoshiguma the Progressive) - 限定干员
        "凛御银灰",            # 凛御银灰 (SilverAsh the Great Chief) - 限定干员
        "望",                  # 望 - 限定干员
        "凯尔希·思衡托",       # 凯尔希·思衡托 - 限定干员

        # ---------- 联动限定干员 ----------
        "灰烬",       # 彩虹六号联动: Ash (灰烬)
        "导火索",     # 彩虹六号联动: Blitz (导火索)
        "麒麟X夜刀",  # 怪物猎人联动: Kirin X Yato
        "焰狐龙梓兰", # 怪物猎人联动: Rathalos Zinogre
        "0",          # 联动干员
        "莱欧斯",     # 迷宫饭联动: Senshi (莱欧斯)
        "丰川祥子",   # BanG Dream联动: Toyokawa Sakiko
    }

    # ==================== 静态方法: 记录解析 ====================

    @staticmethod
    def parse_record(raw: dict, game: str, account_id: int) -> GachaRecord:
        """将API返回的单条原始记录字典解析为标准GachaRecord对象

        解析逻辑包括:
        1. 提取卡池类型(_pool_type由fetch_all添加)
        2. 转换稀有度编码(ZZZ的编码与其他游戏不同)
        3. 修正绝区零的卡池分类(邦布/音擎)
        4. 判断是否为UP物品(通过排除常驻列表和可歪列表)
        5. 组装GachaRecord对象

        参数:
            raw (dict): API返回的单条原始记录字典，包含以下字段:
                - id: 记录唯一ID
                - uid: 玩家UID
                - name: 物品名称
                - item_type: 物品类型(如"角色"、"武器")
                - rank_type: 稀有度编码
                - time: 抽卡时间
                - count: 数量(通常为1)
                - gacha_id: 卡池ID
                - _pool_type: 内部添加的卡池类型标识(由fetch_all添加)
            game (str): 游戏标识(如 "genshin")
            account_id (int): 账号ID，用于区分不同账号

        返回:
            GachaRecord: 解析后的标准抽卡记录对象
        """
        # ----- 第一步: 提取并修正卡池类型 -----
        pool_type = raw.get("_pool_type", "character")
        # _pool_type 是由 fetch_all() 方法在获取时附加的内部字段
        # 如果不存在则默认为 "character"

        # ----- 第二步: 提取并修正稀有度 -----
        rank_type = int(raw.get("rank_type", raw.get("rarity", "3")))
        # 大部分游戏: rank_type 直接对应稀有度 (3=三星, 4=四星, 5=五星)
        # ZZZ的rank_type编码不同: 2→3星, 3→4星, 4→5星 (需要+1修正)
        if game == "zzz":
            rarity = rank_type + 1  # ZZZ特殊处理: API的rank_type比实际稀有度少1
        else:
            rarity = rank_type  # 其他游戏直接使用rank_type

        # ----- 第三步: 提取物品名称 -----
        item_name = raw.get("name", "未知")
        # 如果API未返回name字段，则使用"未知"作为默认值

        # ----- 第四步: ZZZ卡池分类修正 -----
        if game == "zzz":
            item_type_raw = raw.get("item_type", "")
            # 绝区零的API可能将邦布错误地归入其他卡池
            # 需要根据item_type字段来修正pool_type
            if "邦布" in item_type_raw and pool_type != "bangboo":
                pool_type = "bangboo"
                # 如果物品类型包含"邦布"但卡池不是bangboo，则修正为bangboo
            elif "音擎" in item_type_raw and pool_type == "bangboo":
                pool_type = "special_weapon"
                # 如果物品类型是"音擎"但被错误归入bangboo池，修正为special_weapon

        # ----- 第五步: 提取物品类型和时间 -----
        item_type = raw.get("item_type", "")
        # 物品类型字符串，如 "角色"、"武器"、"音擎"、"邦布" 等

        record_time = raw.get("time", "")
        # 抽卡时间，格式: "2025-04-09 12:00:00"
        # 用于判断可歪角色是否在UP时间窗口内

        # ----- 第六步: 判断是否为UP物品 -----
        from core.models import get_max_rarity
        # 导入获取游戏最高稀有度的函数(如原神=5, 方舟=6)

        is_featured = False  # 是否为UP(限定)物品，默认为False(非UP)
        if rarity == get_max_rarity(game) and pool_type in ["character", "weapon"]:
            # 只有当抽到的是最高稀有度的 角色或武器 时才需要判断是否为UP
            # 低稀有度物品不存在UP的概念

            standard_items = MihoyoAPI.STANDARD_5STAR.get(game, {}).get(pool_type, [])
            # 获取该游戏该卡池类型的常驻5星物品列表

            limited_items = getattr(MihoyoAPI, 'ARKNIGHTS_LIMITED', set())
            # 获取明日方舟限定角色列表(其他游戏不使用)

            if game == "arknights":
                # ----- 明日方舟特殊逻辑 -----
                # 方舟的限定角色只在限定池出现，抽到即为UP
                # 通过检查是否在 ARKNIGHTS_LIMITED 集合中判断
                is_featured = item_name in limited_items
            else:
                # ----- 其他米哈游游戏通用逻辑 -----
                # 首先检查是否为可歪角色(有时间限制的往期UP角色)
                loseable_info = MihoyoAPI.LOSEABLE_5STAR_WITH_DATE.get((game, pool_type), {})
                if item_name in loseable_info:
                    # 该角色在可歪列表中，需要根据抽卡时间判断是否为UP
                    loseable_date = loseable_info[item_name]  # 加入可歪池的日期
                    if record_time and record_time >= loseable_date:
                        # 抽卡时间 >= 加入可歪池时间 → 该角色已不再是UP，属于歪到的
                        is_featured = False
                    else:
                        # 抽卡时间 < 加入可歪池时间 → 该角色在抽卡时还是UP状态
                        is_featured = True
                elif item_name not in standard_items:
                    # 不在常驻列表中，也不在可歪列表中 → 必定是UP角色/武器
                    is_featured = True
                # 注意: 如果在standard_items中，is_featured保持False(常驻非UP)

        # ----- 第七步: 组装并返回GachaRecord对象 -----
        return GachaRecord(
            account_id=account_id,        # 账号ID
            game=game,                    # 游戏标识
            pool_type=pool_type,          # 卡池类型(已修正)
            item_id=raw.get("id", ""),    # API返回的记录唯一ID
            item_name=item_name,          # 物品名称
            item_type=item_type,          # 物品类型
            rarity=rarity,                # 稀有度(已修正)
            is_featured=is_featured,      # 是否为UP物品
            count=int(raw.get("count", "1")),  # 数量，通常为1
            time=raw.get("time", ""),     # 抽卡时间
            gacha_id=raw.get("gacha_id", ""),  # 卡池ID
            pull_index=0,                 # 抽卡序号(预留字段，暂不使用)
            raw_data=str(raw),            # 原始记录字典的字符串形式(用于调试)
        )

    # ==================== 静态方法: UID提取 ====================

    @staticmethod
    def get_uid_from_records(records: list) -> str:
        """从记录列表中提取玩家UID

        遍历记录列表，找到第一条包含UID的记录并返回。
        支持两种记录格式: dict(原始API响应) 和 GachaRecord(已解析的对象)。

        参数:
            records (list): 记录列表，每条记录可以是dict或GachaRecord

        返回:
            str: 检测到的UID字符串，如果未找到则返回空字符串
        """
        for record in records:
            if isinstance(record, dict):
                # 原始字典格式: 使用 .get() 安全访问
                uid = record.get("uid")
            else:
                # GachaRecord对象格式: 使用 getattr 安全访问
                uid = getattr(record, "uid", None)
            if uid:
                return str(uid)  # 找到UID，转换为字符串并返回
        return ""  # 未找到UID，返回空字符串

    # ==================== 静态方法: 用户信息获取 ====================

    @staticmethod
    def get_user_info(game: str, uid: str, region: str) -> dict:
        """获取用户信息(如昵称)

        尝试通过米哈游API获取指定UID的用户信息。
        注意: 当前实现由于需要登录态(无法直接获取)，所以返回空字典。
        上层调用者会使用UID作为替代显示名。

        参数:
            game (str): 游戏标识
            uid (str): 玩家UID
            region (str): 服务器区域标识

        返回:
            dict: 用户信息字典(当前始终返回空字典{})
        """
        # 米哈游用户信息API需要登录态(cookie)，公开API无法直接获取
        # 这里保留了接口定义以便未来扩展
        if game in ["genshin", "starrail", "zzz"]:
            # 尝试从genAuthKey接口获取(实际上该接口用于生成认证密钥，不返回用户信息)
            # 以下URL为占位符，实际不会使用
            if game == "genshin":
                url = "https://api-takumi.mihoyo.com/binding/api/genAuthKey"
            elif game == "starrail":
                url = "https://api-takumi.mihoyo.com/binding/api/genAuthKey"
            else:
                url = "https://api-takumi.mihoyo.com/binding/api/genAuthKey"

            # 注意: 该API需要登录态的cookie，公开访问会返回错误
            # 当前策略是返回空字典，由上层使用UID作为显示名
            return {}

        return {}  # 未知游戏也返回空字典


# ==================== 自定义异常类 ====================

class APIError(Exception):
    """米哈游API调用错误异常

    在以下情况抛出:
    1. 网络请求超时或连接失败
    2. API返回非0的retcode(业务错误)
    3. JSON解析失败
    4. 用户主动取消操作

    该异常会被上层 MihoyoGachaFetcher.fetch_records() 捕获并转换为 FetcherError。
    """
    pass  # 继承Exception的所有功能，不需要额外实现
