"""
回测报告生成器
读取回测结果，生成完整分析报告，写入 backtest_report.md
"""
import json
from pathlib import Path

BACKTEST_DIR = Path(__file__).parent


def load_results(year: int) -> list[dict]:
    f = BACKTEST_DIR / f"backtest_results_{year}.json"
    if not f.exists():
        return []
    return json.loads(f.read_text(encoding="utf-8"))


def generate_report():
    results_2022 = load_results(2022)
    results_2018 = load_results(2018)
    all_results = results_2022 + results_2018

    if not all_results:
        print("未找到回测结果，请先运行 run_backtest.py")
        return

    def acc(lst):
        if not lst:
            return 0, 0, 0
        c = sum(1 for r in lst if r["correct"])
        return c, len(lst), c/len(lst)*100

    # 汇总统计
    correct_all, total_all, acc_all = acc(all_results)

    upsets = [r for r in all_results if r["is_upset"]]
    non_upsets = [r for r in all_results if not r["is_upset"]]
    uc, ut, uacc = acc(upsets)
    nc, nt, nacc = acc(non_upsets)

    # 置信度分析
    high_conf = [r for r in all_results if r.get("confidence") == "高"]
    mid_conf = [r for r in all_results if r.get("confidence") == "中"]
    low_conf = [r for r in all_results if r.get("confidence") == "低"]
    hc, ht, hacc = acc(high_conf)
    mc, mt, macc = acc(mid_conf)
    lc, lt, lacc = acc(low_conf)

    # 按赛段
    stages = {}
    for r in all_results:
        s = r["stage"]
        if s not in stages:
            stages[s] = []
        stages[s].append(r)

    # 错误案例
    wrong = [r for r in all_results if not r["correct"]]
    # 错得最离谱的：爆冷但预测了热门
    missed_upsets = [r for r in wrong if r["is_upset"]]
    # 预测了爆冷但实际是热门赢
    false_upsets = [r for r in wrong if not r["is_upset"] and r.get("predicted") != r.get("actual")]

    # 生成报告
    lines = []
    lines.append("# 世界杯预测系统回测报告")
    lines.append(f"\n测试数据集：2018年世界杯 + 2022年世界杯（共{total_all}场代表性比赛）\n")

    lines.append("---\n")
    lines.append("## 一、总体准确率\n")
    lines.append(f"| 指标 | 数值 |")
    lines.append(f"|------|------|")
    lines.append(f"| **总预测场次** | {total_all} |")
    lines.append(f"| **预测正确** | {correct_all} |")
    lines.append(f"| **整体准确率** | **{acc_all:.1f}%** |")
    lines.append(f"| 世界顶级模型参考上限 | ~55-58% |")
    lines.append(f"| 随机猜测基准 | ~33% |")
    lines.append(f"| 跟随热门基准 | ~45-50% |")

    lines.append("\n---\n")
    lines.append("## 二、按年份\n")
    lines.append(f"| 年份 | 正确/总计 | 准确率 |")
    lines.append(f"|------|-----------|--------|")
    c22, t22, a22 = acc(results_2022)
    c18, t18, a18 = acc(results_2018)
    lines.append(f"| 2022卡塔尔 | {c22}/{t22} | {a22:.1f}% |")
    lines.append(f"| 2018俄罗斯 | {c18}/{t18} | {a18:.1f}% |")

    lines.append("\n---\n")
    lines.append("## 三、按赛程阶段\n")
    lines.append(f"| 阶段 | 正确/总计 | 准确率 |")
    lines.append(f"|------|-----------|--------|")
    stage_order = ["group_stage", "round_of_16", "quarterfinal", "semifinal", "final"]
    stage_labels = {"group_stage": "小组赛", "round_of_16": "16强", "quarterfinal": "四分之一决赛",
                    "semifinal": "半决赛", "final": "决赛"}
    for s in stage_order:
        if s in stages:
            sc, st, sa = acc(stages[s])
            lines.append(f"| {stage_labels.get(s, s)} | {sc}/{st} | {sa:.1f}% |")

    lines.append("\n---\n")
    lines.append("## 四、爆冷识别能力\n")
    lines.append(f"| 类型 | 正确/总计 | 准确率 |")
    lines.append(f"|------|-----------|--------|")
    lines.append(f"| 爆冷场次（冷门队赢） | {uc}/{ut} | {uacc:.1f}% |")
    lines.append(f"| 正常场次（热门队赢或平） | {nc}/{nt} | {nacc:.1f}% |")

    lines.append("\n**被错过的爆冷（预测热门但冷门赢了）：**\n")
    for r in missed_upsets:
        lines.append(f"- {r['year']} | {r['team_a']} vs {r['team_b']} ({r['stage']}) — {r['note']}")
        lines.append(f"  预测：{r['predicted_str']} | 实际：{r['actual']}\n")

    lines.append("\n---\n")
    lines.append("## 五、置信度校准\n")
    lines.append(f"| 置信度 | 实际准确率 | 场次 | 校准状态 |")
    lines.append(f"|--------|-----------|------|----------|")
    if ht > 0:
        cal_h = "✓ 良好" if hacc >= 65 else ("△ 偏高" if hacc >= 55 else "✗ 过高估计")
        lines.append(f"| 高置信度 | {hacc:.1f}% | {ht}场 | {cal_h} |")
    if mt > 0:
        cal_m = "✓ 良好" if 45 <= macc <= 65 else ("△ 偏低" if macc < 45 else "△ 偏高")
        lines.append(f"| 中置信度 | {macc:.1f}% | {mt}场 | {cal_m} |")
    if lt > 0:
        cal_l = "✓ 良好" if lacc <= 55 else "✗ 低置信度不够低"
        lines.append(f"| 低置信度 | {lacc:.1f}% | {lt}场 | {cal_l} |")

    lines.append("\n---\n")
    lines.append("## 六、典型错误案例分析\n")
    for r in wrong[:10]:
        lines.append(f"**{r['year']} | {r['team_a']} vs {r['team_b']}** ({stage_labels.get(r['stage'], r['stage'])})")
        lines.append(f"- 预测：{r['predicted_str']} | 实际结果：{r['actual']} | {r['note']}")
        lines.append("")

    lines.append("\n---\n")
    lines.append("## 七、系统评估与改进建议\n")

    # 动态评估
    assessment = []
    if acc_all >= 60:
        assessment.append("✅ **总体准确率良好**（超过世界顶级模型参考线55-58%），系统表现出色。")
    elif acc_all >= 50:
        assessment.append("△ **总体准确率中等**（高于随机和跟随热门基准，但未超过顶级模型参考线）。")
    else:
        assessment.append("❌ **总体准确率偏低**（低于跟随热门基准），系统存在明显问题。")

    if uacc < 20:
        assessment.append("❌ **爆冷识别极弱**：系统几乎无法识别冷门，过度依赖热门队优势判断。")
        assessment.append("  → 建议：加强魔鬼代言人Agent的权重，降低裁判对历史声誉的依赖。")
    elif uacc < 35:
        assessment.append("△ **爆冷识别偏弱**：对于冷门场次表现不稳定。")
        assessment.append("  → 建议：增加对赔率信号的利用，市场对冷门有时比纯分析更准。")
    else:
        assessment.append("✅ **爆冷识别能力合格**：系统能识别相当比例的冷门。")

    if hacc < 60:
        assessment.append("⚠️ **高置信度校准问题**：声称高把握的预测实际准确率不够高，存在过度自信。")
        assessment.append("  → 建议：在裁判Prompt中增加置信度保守化规则，减少高置信度输出。")

    if a22 < a18:
        assessment.append("⚠️ **2022年准确率低于2018年**：可能因为2022年爆冷更多（沙特胜阿根廷等），系统应对高不确定性场次能力不足。")

    assessment.append("\n**核心改进方向：**")
    assessment.append("1. **引入历史赔率数据**：赛前赔率是最强预测信号，2018/2022的历史赔率如能获取，会显著提升准确率")
    assessment.append("2. **强化赛前关键信息搜集**：当前赛前数据集质量直接影响预测精度")
    assessment.append("3. **爆冷概率建模**：为每场比赛计算一个爆冷概率分数，而非二元判断")
    assessment.append("4. **淘汰赛专项模型**：淘汰赛比小组赛预测难度更高（任何队都可以在一场定胜负中赢），需要单独校准")

    lines.extend(assessment)

    lines.append("\n---\n")
    lines.append("## 八、完整预测记录\n")
    lines.append("| 年份 | 比赛 | 阶段 | 预测 | 实际 | 结果 |")
    lines.append("|------|------|------|------|------|------|")
    for r in all_results:
        icon = "✓" if r["correct"] else "✗"
        upset_tag = " 🎯" if r["is_upset"] and r["correct"] else (" ❌爆冷" if r["is_upset"] else "")
        lines.append(f"| {r['year']} | {r['team_a']} vs {r['team_b']} | {stage_labels.get(r['stage'], r['stage'])} | {r['predicted_str']} | {r['actual']} | {icon}{upset_tag} |")

    report = "\n".join(lines)
    report_file = BACKTEST_DIR / "backtest_report.md"
    report_file.write_text(report, encoding="utf-8")
    print(f"\n报告已保存: {report_file}")
    print(f"\n综合准确率: {acc_all:.1f}% ({correct_all}/{total_all})")
    print(f"爆冷识别率: {uacc:.1f}% ({uc}/{ut})")
    return report_file


if __name__ == "__main__":
    generate_report()
