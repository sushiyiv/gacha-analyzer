"""保底分析模块 - 追踪保底进度，计算逐抽概率"""

from banner_config import ALL_BANNERS


def get_rate_at_pull(config, pull_number):
    """计算第N抽出5星的概率"""
    base = config["base_rate_5star"]
    soft_start = config["soft_pity_start"]
    hard = config["hard_pity"]
    increment = config["soft_pity_increment"]

    if pull_number >= hard:
        return 1.0
    if pull_number >= soft_start:
        extra = (pull_number - soft_start + 1) * increment
        return min(base + extra, 1.0)
    return base


def analyze_pity(banner_config, current_pity, is_guaranteed=False):
    """分析当前保底状态，返回详细信息"""
    config = banner_config
    hard = config["hard_pity"]
    soft_start = config["soft_pity_start"]
    pulls_to_hard = hard - current_pity

    # 当前抽数的概率
    current_rate = get_rate_at_pull(config, current_pity)

    # 逐抽概率表
    rate_table = []
    for i in range(current_pity, hard + 1):
        rate = get_rate_at_pull(config, i)
        rate_table.append({
            "pull": i,
            "pulls_from_now": i - current_pity,
            "rate": rate,
            "rate_pct": f"{rate * 100:.2f}%",
        })

    # 计算期望抽数（到下一个5星）
    expected_pulls = 0
    cumulative_no_5star = 1.0
    for i in range(current_pity, hard + 1):
        rate = get_rate_at_pull(config, i)
        pulls_from_now = i - current_pity + 1
        prob_this_pull = cumulative_no_5star * rate
        expected_pulls += pulls_from_now * prob_this_pull
        cumulative_no_5star *= (1 - rate)
    # 硬保底兜底
    expected_pulls += pulls_to_hard * cumulative_no_5star

    # 计算限定角色期望
    if config["has_guarantee"]:
        if is_guaranteed:
            featured_expected = expected_pulls
        else:
            # 50% 概率歪，歪了还要再抽一轮
            featured_expected = expected_pulls + 0.5 * expected_pulls
    else:
        featured_expected = expected_pulls

    result = {
        "banner_name": config["name"],
        "current_pity": current_pity,
        "is_guaranteed": is_guaranteed,
        "pulls_to_hard_pity": pulls_to_hard,
        "current_rate": current_rate,
        "current_rate_pct": f"{current_rate * 100:.2f}%",
        "expected_pulls_to_5star": round(expected_pulls, 2),
        "expected_pulls_to_featured": round(featured_expected, 2),
        "soft_pity_start": soft_start,
        "hard_pity": hard,
        "rate_table": rate_table,
    }

    # 武器池定轨信息
    if config.get("has_epitomized_path"):
        result["epitomized_path_count"] = config["epitomized_path_count"]

    return result


def format_pity_report(analysis):
    """格式化保底分析报告"""
    lines = []
    lines.append(f"\n{'='*50}")
    lines.append(f"  {analysis['banner_name']} - 保底分析")
    lines.append(f"{'='*50}")
    lines.append(f"  当前已垫: {analysis['current_pity']} 抽")
    lines.append(f"  大保底状态: {'是 (下次必出限定)' if analysis['is_guaranteed'] else '否 (可能歪)'}")
    lines.append(f"  距离硬保底: {analysis['pulls_to_hard_pity']} 抽")
    lines.append(f"  当前5星概率: {analysis['current_rate_pct']}")
    lines.append(f"  期望抽数(任意5星): {analysis['expected_pulls_to_5star']} 抽")
    lines.append(f"  期望抽数(限定5星): {analysis['expected_pulls_to_featured']} 抽")
    lines.append(f"  软保底起始: 第 {analysis['soft_pity_start']} 抽")
    lines.append(f"  硬保底: 第 {analysis['hard_pity']} 抽")
    lines.append(f"{'='*50}")

    # 显示接下来几抽的概率
    lines.append(f"\n  接下来的概率变化:")
    lines.append(f"  {'抽数':>6} {'概率':>10} {'概率条'}")
    lines.append(f"  {'-'*40}")

    table = analysis["rate_table"]
    # 显示最多15抽或到硬保底
    display_count = min(len(table), 15)
    for entry in table[:display_count]:
        bar_len = int(entry["rate"] * 50)
        bar = "█" * bar_len + "░" * (50 - bar_len)
        lines.append(f"  +{entry['pulls_from_now']:>3}抽  {entry['rate_pct']:>8}  {bar}")

    if len(table) > display_count:
        lines.append(f"  ... (省略 {len(table) - display_count} 抽)")
    # 硬保底
    last = table[-1]
    bar_len = int(last["rate"] * 50)
    bar = "█" * bar_len + "░" * (50 - bar_len)
    lines.append(f"  +{last['pulls_from_now']:>3}抽  {last['rate_pct']:>8}  {bar} ← 硬保底")

    lines.append("")
    return "\n".join(lines)
