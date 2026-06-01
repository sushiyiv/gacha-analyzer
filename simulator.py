"""概率模拟模块 - Monte Carlo 模拟 + 可视化"""

import random
import matplotlib.pyplot as plt
import matplotlib
from gacha_engine import pulls_until_featured, simulate_pulls
from banner_config import ALL_BANNERS

# 支持中文显示
matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'DejaVu Sans']
matplotlib.rcParams['axes.unicode_minus'] = False


def monte_carlo_simulate(banner_config, current_pity=0, is_guaranteed=False,
                         target_featured=1, simulations=10000):
    """Monte Carlo 模拟抽到目标数量限定5星需要的抽数"""
    results = []
    for _ in range(simulations):
        total_pulls = 0
        featured_count = 0
        state_pity = current_pity
        state_guaranteed = is_guaranteed

        while featured_count < target_featured:
            pulls = pulls_until_featured(banner_config, state_pity, state_guaranteed)
            total_pulls += pulls
            featured_count += 1
            state_pity = 0
            state_guaranteed = False

        results.append(total_pulls)
    return results


def analyze_simulation_results(results, target_featured=1):
    """分析模拟结果"""
    results_sorted = sorted(results)
    n = len(results_sorted)

    avg = sum(results) / n
    median = results_sorted[n // 2]
    min_val = results_sorted[0]
    max_val = results_sorted[-1]

    # 各抽数阈值的概率
    thresholds = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100, 120, 150, 180, 200]
    prob_table = {}
    for t in thresholds:
        count = sum(1 for r in results if r <= t)
        prob_table[t] = count / n

    # 欧皇/非酋分布
    percentiles = {
        "欧皇 (前10%)": results_sorted[int(n * 0.1)],
        "偏欧 (前25%)": results_sorted[int(n * 0.25)],
        "正常 (50%)": median,
        "偏非 (前75%)": results_sorted[int(n * 0.75)],
        "非酋 (前90%)": results_sorted[int(n * 0.9)],
        "究极非酋 (前99%)": results_sorted[int(n * 0.99)],
    }

    return {
        "simulations": n,
        "target_featured": target_featured,
        "average": round(avg, 2),
        "median": median,
        "min": min_val,
        "max": max_val,
        "prob_table": prob_table,
        "percentiles": percentiles,
        "raw_results": results,
    }


def format_simulation_report(analysis):
    """格式化模拟报告"""
    lines = []
    lines.append(f"\n{'='*50}")
    lines.append(f"  Monte Carlo 模拟结果 (抽到 {analysis['target_featured']} 个限定5星)")
    lines.append(f"{'='*50}")
    lines.append(f"  模拟次数: {analysis['simulations']:,}")
    lines.append(f"  平均抽数: {analysis['average']}")
    lines.append(f"  中位数: {analysis['median']}")
    lines.append(f"  最少: {analysis['min']} 抽")
    lines.append(f"  最多: {analysis['max']} 抽")

    lines.append(f"\n  欧非分布:")
    for label, val in analysis["percentiles"].items():
        lines.append(f"    {label}: {val} 抽")

    lines.append(f"\n  各抽数阈值内出货概率:")
    for pulls, prob in analysis["prob_table"].items():
        bar_len = int(prob * 30)
        bar = "█" * bar_len + "░" * (30 - bar_len)
        lines.append(f"    {pulls:>4} 抽: {prob*100:>6.2f}% {bar}")

    lines.append("")
    return "\n".join(lines)


def plot_simulation(analysis, save_path=None):
    """绘制模拟结果图表"""
    results = analysis["raw_results"]

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # 左图：抽数分布直方图
    ax1 = axes[0]
    ax1.hist(results, bins=range(min(results), max(results) + 2), edgecolor='black',
             alpha=0.7, color='#4CAF50', density=True)
    ax1.axvline(analysis["average"], color='red', linestyle='--', linewidth=1.5,
                label=f'平均值: {analysis["average"]}')
    ax1.axvline(analysis["median"], color='blue', linestyle='--', linewidth=1.5,
                label=f'中位数: {analysis["median"]}')
    ax1.set_xlabel('抽数')
    ax1.set_ylabel('概率密度')
    ax1.set_title(f'抽到 {analysis["target_featured"]} 个限定5星的抽数分布')
    ax1.legend()
    ax1.grid(axis='y', alpha=0.3)

    # 右图：累积概率曲线
    ax2 = axes[1]
    results_sorted = sorted(results)
    n = len(results_sorted)
    cumulative = [i / n for i in range(1, n + 1)]

    # 降采样以提高性能
    step = max(1, n // 500)
    sampled_x = results_sorted[::step]
    sampled_y = cumulative[::step]

    ax2.plot(sampled_x, sampled_y, color='#2196F3', linewidth=2)
    ax2.axhline(0.5, color='gray', linestyle=':', alpha=0.5)
    ax2.axhline(0.9, color='gray', linestyle=':', alpha=0.5)
    ax2.set_xlabel('抽数')
    ax2.set_ylabel('累积概率')
    ax2.set_title('累积概率曲线 (多少抽内能出货)')
    ax2.set_ylim(0, 1.05)
    ax2.grid(alpha=0.3)

    # 标注关键概率点
    for prob_label, prob_val in [("50%", 0.5), ("90%", 0.9)]:
        idx = next(i for i, v in enumerate(cumulative) if v >= prob_val)
        x_val = results_sorted[idx]
        ax2.annotate(f'{prob_label}概率: {x_val}抽',
                     xy=(x_val, prob_val), fontsize=9,
                     arrowprops=dict(arrowstyle='->', color='gray'),
                     xytext=(x_val + 10, prob_val - 0.1))

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path, dpi=150, bbox_inches='tight')
        print(f"  图表已保存到: {save_path}")
    else:
        plt.show()
    plt.close()
