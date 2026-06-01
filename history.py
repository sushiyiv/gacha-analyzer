"""历史记录分析模块 - API导入 + 手动导入 + 数据分析"""

import json
import os
from datetime import datetime

# 米哈游抽卡记录 API（原神）
GENSHIN_API_URL = "https://hk4e-api.mihoyo.com/event/gacha_info/api/getGachaLog"
# 星铁抽卡记录 API
STARRAIL_API_URL = "https://api-takumi.mihoyo.com/common/gacha_record/api/getGachaLog"

# 原神卡池 ID
GENSHIN_BANNER_IDS = {
    "character": "a8f1c4a2947f22852c1fb84e48316e57e0b4264",
    "weapon": "a8f1c4a2947f22852c1fb84e48316e57e0b4264",
    "standard": "a8f1c4a2947f22852c1fb84e48316e57e0b4264",
}


def fetch_history_from_api(authkey, banner_type="character", game="genshin", page_size=20):
    """从米哈游 API 获取抽卡历史记录"""
    import requests
    from urllib.parse import quote

    if game == "genshin":
        base_url = GENSHIN_API_URL
        banner_id = GENSHIN_BANNER_IDS.get(banner_type, "")
    else:
        base_url = STARRAIL_API_URL
        banner_id = ""

    all_records = []
    end_id = ""
    page = 1

    while True:
        params = {
            "authkey": authkey,
            "authkey_ver": "1",
            "sign_type": "2",
            "lang": "zh-cn",
            "gacha_type": banner_id,
            "page": page,
            "size": page_size,
            "end_id": end_id,
        }

        try:
            resp = requests.get(base_url, params=params, timeout=10)
            data = resp.json()

            if data.get("retcode") != 0:
                print(f"  API 错误: {data.get('message', '未知错误')}")
                return []

            records = data.get("data", {}).get("list", [])
            if not records:
                break

            all_records.extend(records)
            end_id = records[-1].get("id", "")
            page += 1

            # 限制最多获取 50 页，防止无限循环
            if page > 50:
                break

        except Exception as e:
            print(f"  请求失败: {e}")
            return []

    return all_records


def load_history_from_file(filepath):
    """从 JSON 文件加载抽卡历史记录"""
    if not os.path.exists(filepath):
        print(f"  文件不存在: {filepath}")
        return []

    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and "records" in data:
        return data["records"]
    else:
        print("  文件格式不正确，需要 JSON 数组或 {records: [...]} 格式")
        return []


def save_history_to_file(records, filepath):
    """保存抽卡历史记录到 JSON 文件"""
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)
    print(f"  记录已保存到: {filepath}")


def analyze_history(records):
    """分析抽卡历史记录"""
    if not records:
        return None

    total = len(records)
    five_stars = []
    four_stars = []
    last_5star_idx = -1

    for i, record in enumerate(records):
        rarity = record.get("rank_type") or record.get("rarity", "")
        if str(rarity) == "5":
            pity_count = i - last_5star_idx
            five_stars.append({
                "name": record.get("name", "未知"),
                "pull_index": i + 1,
                "pity_count": pity_count,
                "time": record.get("time", ""),
                "is_featured": None,  # 需要外部判断
            })
            last_5star_idx = i
        elif str(rarity) == "4":
            four_stars.append(record)

    # 计算统计数据
    pity_counts = [s["pity_count"] for s in five_stars]
    avg_pity = sum(pity_counts) / len(pity_counts) if pity_counts else 0

    # 出货时间线
    timeline = []
    for s in five_stars:
        timeline.append(f"  第 {s['pull_index']:>5} 抽 | {s['name']:<15} | 保底计数: {s['pity_count']}")

    # 欧非评级
    rating = ""
    if avg_pity <= 40:
        rating = "★★★★★ 欧皇附体！"
    elif avg_pity <= 55:
        rating = "★★★★ 比较欧"
    elif avg_pity <= 65:
        rating = "★★★ 正常水平"
    elif avg_pity <= 75:
        rating = "★★ 有点非"
    else:
        rating = "★ 非酋本酋"

    # 软保底命中率
    soft_pity_hits = sum(1 for c in pity_counts if c >= 74)
    hard_pity_hits = sum(1 for c in pity_counts if c >= 85)

    return {
        "total_pulls": total,
        "five_star_count": len(five_stars),
        "four_star_count": len(four_stars),
        "five_stars": five_stars,
        "avg_pity": round(avg_pity, 2),
        "min_pity": min(pity_counts) if pity_counts else 0,
        "max_pity": max(pity_counts) if pity_counts else 0,
        "rating": rating,
        "soft_pity_hits": soft_pity_hits,
        "hard_pity_hits": hard_pity_hits,
        "timeline": timeline,
    }


def format_history_report(analysis):
    """格式化历史记录分析报告"""
    if not analysis:
        return "  没有可分析的记录。"

    lines = []
    lines.append(f"\n{'='*55}")
    lines.append(f"  抽卡历史分析报告")
    lines.append(f"{'='*55}")
    lines.append(f"  总抽数: {analysis['total_pulls']}")
    lines.append(f"  5星数量: {analysis['five_star_count']}")
    lines.append(f"  4星数量: {analysis['four_star_count']}")
    lines.append(f"  平均保底计数: {analysis['avg_pity']}")
    lines.append(f"  最少: {analysis['min_pity']} 抽出货")
    lines.append(f"  最多: {analysis['max_pity']} 抽出货")
    lines.append(f"  软保底命中: {analysis['soft_pity_hits']} 次")
    lines.append(f"  接近硬保底(85+): {analysis['hard_pity_hits']} 次")
    lines.append(f"  欧非评级: {analysis['rating']}")

    if analysis["timeline"]:
        lines.append(f"\n  5星出货时间线:")
        lines.append(f"  {'抽数':>8} | {'名称':<15} | 保底计数")
        lines.append(f"  {'-'*45}")
        for entry in analysis["timeline"]:
            lines.append(entry)

    lines.append("")
    return "\n".join(lines)
