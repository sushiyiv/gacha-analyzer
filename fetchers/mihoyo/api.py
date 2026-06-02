"""米哈游通用 API 调用"""

import requests
from typing import List, Dict, Optional
from core.models import GachaRecord
from core.config import Config


class MihoyoAPI:
    """米哈游抽卡记录 API"""

    # API 端点
    ENDPOINTS = {
        "genshin": "https://public-operation-hk4e.mihoyo.com/gacha_info/api/getGachaLog",
        "starrail": "https://public-operation-hkrpg.mihoyo.com/common/gacha_record/api/getGachaLog",
        "zzz": "https://public-operation-nap.mihoyo.com/common/gacha_record/api/getGachaLog",
    }

    # 卡池类型映射
    GACHA_TYPES = {
        "genshin": {
            "character": "301",
            "weapon": "302",
            "chronicled": "400",
            "standard": "200",
            "beginner": "100",
        },
        "starrail": {
            "character": "11",
            "weapon": "12",
            "standard": "1",
            "beginner": "2",
            "collab": "13",
            "collab_weapon": "14",
        },
        "zzz": {
            "character": "2001",
            "weapon": "3001",
            "special": "4001",
            "special_weapon": "5001",
            "bangboo": "6001",
            "standard": "1001",
        },
        "wutheringwaves": {
            "character": "1",
            "weapon": "2",
            "standard_character": "3",
            "standard_weapon": "4",
            "beginner": "5",
            "selector": "8",
            "selector_weapon": "9",
        },
    }

    def __init__(self):
        self.config = Config()

    def fetch_all(self, game: str, url: str, progress_callback=None, latest_time: str = None, cancel_check=None) -> List[Dict]:
        """获取所有抽卡记录"""
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url)

        # 从URL中提取基础参数
        base_params = parse_qs(parsed.query)

        # 使用正确的 API 端点（不是网页 URL）
        endpoint = self.ENDPOINTS.get(game)
        if not endpoint:
            # 如果没有预定义的端点，尝试从 URL 推断
            endpoint = f"{parsed.scheme}://{parsed.hostname}{parsed.path}"

        # 只保留必要的认证参数
        auth_params = {}
        for key in ["authkey", "authkey_ver", "sign_type", "game_biz", "region", "auth_appid", "plat_type", "lang"]:
            if key in base_params:
                auth_params[key] = base_params[key][0]

        all_records = []
        detected_uid = ""
        end_id = "0"
        page = 1
        gacha_types = self.GACHA_TYPES.get(game, {})
        total_pools = len(gacha_types)
        current_pool_idx = 0

        # 遍历所有卡池类型
        for pool_name, gacha_type_id in gacha_types.items():
            pool_progress = current_pool_idx / total_pools
            page = 1
            end_id = "0"
            pool_total = 0

            if progress_callback:
                progress_callback(f"开始获取 {pool_name} 记录...", pool_progress)

            while True:
                if cancel_check and cancel_check():
                    raise APIError("用户取消")

                params = {
                    **auth_params,
                    "lang": "zh-cn",
                    "gacha_type": gacha_type_id,
                    "page": str(page),
                    "size": "20",  # API最大支持20，但实际可能支持更大值
                    "end_id": end_id,
                }

                # 调试日志
                if page <= 3 or page % 10 == 0:
                    print(f"[DEBUG] 获取 {pool_name} 第{page}页, end_id={end_id}")

                try:
                    resp = requests.get(endpoint, params=params, timeout=30)

                    # 检查响应内容
                    try:
                        data = resp.json()
                    except Exception as e:
                        raise APIError(f"解析响应失败: {str(e)}\n响应内容: {resp.text[:200]}")

                    if data.get("retcode") != 0:
                        msg = data.get("message", "未知错误")
                        msg_lower = msg.lower()
                        if "authkey" in msg_lower or "auth key" in msg_lower or "expired" in msg_lower or "time out" in msg_lower:
                            raise APIError("authkey 已过期，请重新获取")
                        raise APIError(f"API 错误: {msg}")

                    records = data.get("data", {}).get("list", [])
                    if not records:
                        if progress_callback:
                            progress_callback(f"{pool_name} 获取完成，共 {pool_total} 条", pool_progress + 1.0 / total_pools)
                        break

                    # 从记录中提取UID
                    if not detected_uid:
                        for r in records:
                            if r.get("uid"):
                                detected_uid = str(r["uid"])
                                break

                    # 不论是否增量获取，都继续获取所有记录
                    # 增量过滤将在入库时通过UNIQUE约束处理
                    for record in records:
                        record["_pool_type"] = pool_name

                    all_records.extend(records)
                    pool_total += len(records)
                    end_id = records[-1].get("id", "0")
                    page += 1

                    if progress_callback:
                        page_progress = min(page / 100, 1.0) / total_pools
                        progress_callback(f"正在获取 {pool_name} 记录... 第{page-1}页 ({pool_total}条)", pool_progress + page_progress)

                    # 安全限制
                    if page > 100:
                        if progress_callback:
                            progress_callback(f"{pool_name} 达到页数限制，共 {pool_total} 条", pool_progress + 1.0 / total_pools)
                        break

                except requests.exceptions.Timeout:
                    raise APIError("网络请求超时，请检查网络连接后重试")
                except requests.exceptions.ConnectionError:
                    raise APIError("网络连接失败，请检查网络连接后重试")
                except requests.exceptions.RequestException as e:
                    raise APIError(f"网络请求失败: {str(e)}")

            current_pool_idx += 1

        return all_records, detected_uid

    # 常驻五星角色/武器列表（用于判断是否UP）
    STANDARD_5STAR = {
        "genshin": {
            "character": ["梦见月瑞希", "迪希雅", "提纳里", "刻晴", "莫娜", "七七", "迪卢克", "琴"],
            "weapon": ["天空之刃", "风鹰剑", "狼的末路", "天空之傲", "和璞鸢",
                       "天空之脊", "四风原典", "天空之卷", "阿莫斯之弓", "天空之翼"],
        },
        "starrail": {
            "character": ["布洛妮娅", "克拉拉", "杰帕德", "白露", "姬子", "瓦尔特", "彦卿"],
            "weapon": ["但战斗还未结束", "时节不居", "无可取代的东西", "银河铁道之夜",
                       "制胜的瞬间", "如泥酣眠", "以世界之名"],
        },
        "zzz": {
            "character": ["莱卡恩", "11号", "珂蕾妲", "丽娜", "格莉丝", "猫又"],
            "weapon": ["硫磺石", "燃狱齿轮", "钢铁肉垫", "啜泣摇篮", "嵌合编译器", "拘缚者"],
        },
        "wutheringwaves": {
            "character": ["维里奈", "安可", "鉴心", "卡卡罗", "凌阳"],
            "weapon": ["浩境粼光", "千古洑流", "停驻之烟", "擎渊怒涛", "漪澜浮录",
                       "源能机锋", "镭射切变", "相位涟漪", "脉冲协臂", "玻色星仪"],
        },
        "endfield": {
            "character": ["骏卫", "余烬", "艾尔黛拉", "别礼", "黎风"],
            "weapon": [
                # 单手剑
                "热熔切割器", "不知归", "宏愿", "显赫声名", "扶摇", "白夜新星", "光荣记忆", "黯色火炬",
                # 双手剑
                "破碎君王", "大雷斑", "昔日精品", "赫拉芬格", "典范",
                # 长柄武器
                "负山", "骁勇", "J.E.T.",
                # 手铳
                "同类相食", "楔子", "望乡", "领航者",
                # 施术单元
                "爆破单元", "沧溟星梦", "骑士精神", "遗忘", "悼亡诗",
            ],
        },
    }

    # 可歪角色列表：角色加入可歪池的时间（用于判断历史UP）
    # 格式: { (game, pool_type): { "角色名": "加入可歪池的时间(YYYY-MM-DD)" } }
    LOSEABLE_5STAR_WITH_DATE = {
        ("starrail", "character"): {
            # 2025.4.9 版本更新后加入可歪池（星缘相邀）
            "希儿": "2025-04-09",
            "刃": "2025-04-09",
            "符玄": "2025-04-09",
            # 2026.4.22 版本更新后加入可歪池（星缘相邀）
            "云璃": "2026-04-22",
            "银枝": "2026-04-22",
            "银狼": "2026-04-22",
        },
    }

    # 明日方舟限定角色（非限定即为常驻）
    ARKNIGHTS_LIMITED = {
        "年", "W", "迷迭香", "夕", "浊心斯卡蒂", "假日威龙陈", "耀骑士临光",
        "令", "归溟幽灵鲨", "百炼嘉维尔", "缄默德克萨斯", "重岳", "缪尔赛思",
        "纯烬艾雅法拉", "塑心", "黍", "维什戴尔", "佩佩", "荒芜拉普兰德",
        "余", "新约能天使", "斩业星熊", "凛御银灰", "望", "凯尔希·思衡托",
        # 联动限定
        "灰烬", "导火索", "麒麟X夜刀", "焰狐龙梓兰", "0", "莱欧斯", "丰川祥子",
    }

    @staticmethod
    def parse_record(raw: dict, game: str, account_id: int) -> GachaRecord:
        """解析API返回的单条记录"""
        pool_type = raw.get("_pool_type", "character")
        rank_type = int(raw.get("rank_type", raw.get("rarity", "3")))
        # ZZZ的rank_type编码不同: 2→3星, 3→4星, 4→5星
        if game == "zzz":
            rarity = rank_type + 1
        else:
            rarity = rank_type
        item_name = raw.get("name", "未知")
        # ZZZ: 根据 item_type 修正卡池分类（API 可能把邦布归入错误的卡池）
        if game == "zzz":
            item_type_raw = raw.get("item_type", "")
            if "邦布" in item_type_raw and pool_type != "bangboo":
                pool_type = "bangboo"
            elif "音擎" in item_type_raw and pool_type == "bangboo":
                pool_type = "special_weapon"
        item_type = raw.get("item_type", "")
        record_time = raw.get("time", "")  # 抽卡时间，格式: "2025-04-09 12:00:00"

        # 判断是否为UP
        from core.models import get_max_rarity
        is_featured = False
        if rarity == get_max_rarity(game) and pool_type in ["character", "weapon"]:
            standard_items = MihoyoAPI.STANDARD_5STAR.get(game, {}).get(pool_type, [])
            limited_items = getattr(MihoyoAPI, 'ARKNIGHTS_LIMITED', set())
            if game == "arknights":
                # 明日方舟：限定角色出现即为UP（只在限定池出现）
                is_featured = item_name in limited_items
            else:
                # 其他游戏：检查是否为可歪角色（需要考虑时间）
                loseable_info = MihoyoAPI.LOSEABLE_5STAR_WITH_DATE.get((game, pool_type), {})
                if item_name in loseable_info:
                    # 这个角色有可歪时间限制，需要判断抽卡时间
                    loseable_date = loseable_info[item_name]  # 加入可歪池的时间
                    if record_time and record_time >= loseable_date:
                        # 抽卡时间 >= 加入可歪池时间，说明是歪到的（非UP）
                        is_featured = False
                    else:
                        # 抽卡时间 < 加入可歪池时间，说明当时还是UP
                        is_featured = True
                elif item_name not in standard_items:
                    # 不在常驻列表中，也不是可歪角色 = UP
                    is_featured = True

        return GachaRecord(
            account_id=account_id,
            game=game,
            pool_type=pool_type,
            item_id=raw.get("id", ""),  # 使用API返回的唯一ID
            item_name=item_name,
            item_type=item_type,
            rarity=rarity,
            is_featured=is_featured,
            count=int(raw.get("count", "1")),
            time=raw.get("time", ""),
            gacha_id=raw.get("gacha_id", ""),
            pull_index=0,
            raw_data=str(raw),
        )

    @staticmethod
    def get_uid_from_records(records: list) -> str:
        """从记录中提取UID"""
        for record in records:
            if isinstance(record, dict):
                uid = record.get("uid")
            else:
                uid = getattr(record, "uid", None)
            if uid:
                return str(uid)
        return ""

    @staticmethod
    def get_user_info(game: str, uid: str, region: str) -> dict:
        """获取用户信息（昵称等）"""
        # 米哈游用户信息API
        if game in ["genshin", "starrail", "zzz"]:
            # 尝试从角色信息API获取昵称
            if game == "genshin":
                url = "https://api-takumi.mihoyo.com/binding/api/genAuthKey"
            elif game == "starrail":
                url = "https://api-takumi.mihoyo.com/binding/api/genAuthKey"
            else:
                url = "https://api-takumi.mihoyo.com/binding/api/genAuthKey"

            # 注意：这个API需要登录态，暂时无法直接获取
            # 返回空字典，使用UID作为显示名
            return {}

        return {}


class APIError(Exception):
    pass
