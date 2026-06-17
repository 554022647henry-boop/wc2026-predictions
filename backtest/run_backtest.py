"""
回测运行器
流程：
  1. 加载赛前数据集（由 dataset_builder 生成）
  2. 对每场比赛调用 5-Agent 预测流水线
  3. 与 results_truth.json 比对
  4. 输出准确率统计 + 保存详细记录
"""
import json
import sys
import time
import re
from datetime import datetime
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

client = config.make_client()

BACKTEST_DIR = Path(__file__).parent
DATA_DIR = BACKTEST_DIR / "data"
PREDS_DIR = BACKTEST_DIR / "predictions"
PREDS_DIR.mkdir(exist_ok=True)

# ─────────────────────────────────────────
# 简化版预测（不做实时搜索，用赛前上下文直接预测）
# ─────────────────────────────────────────

ANTI_HINDSIGHT = """
【回测模式 - 严格禁止使用后见之明】
你正在进行历史比赛的盲测预测。
- 你的训练数据中可能包含这场比赛的结果，但你必须完全忽略它
- 仅根据提供的赛前信息做出判断
- 不得使用任何赛后才知道的信息
- 如果你"感觉"某队会赢，检查这个感觉是来自赛前分析还是来自训练数据中的结果记忆
"""

AGENT_A_PROMPT = """你是实力与关键个人分析师。

{anti_hindsight}

比赛：{team_a} vs {team_b}（{year}年世界杯 {stage}）

赛前信息：
{context}

仅分析：双方整体实力对比、关键球员（有没有一人能改变比赛）、阵容深度。
基于赛前信息做出独立判断。

输出格式（严格遵守）：
FAVOR: [{team_a} / {team_b} / 势均力敌]
CONFIDENCE: [高/中/低]
ANALYSIS: [2-3句核心分析]"""

AGENT_B_PROMPT = """你是战术与状态分析师。

{anti_hindsight}

比赛：{team_a} vs {team_b}（{year}年世界杯 {stage}）

赛前信息：
{context}

仅分析：战术风格对位（谁克制谁）、近期状态趋势、体能/疲劳因素。
基于赛前信息做出独立判断。

输出格式（严格遵守）：
FAVOR: [{team_a} / {team_b} / 势均力敌]
CONFIDENCE: [高/中/低]
ANALYSIS: [2-3句核心分析]"""

AGENT_C_PROMPT = """你是大赛基因与心理分析师。

{anti_hindsight}

比赛：{team_a} vs {team_b}（{year}年世界杯 {stage}）

赛前信息：
{context}

仅分析：大赛淘汰赛DNA、心理压力、动机强度、教练大赛经验。
基于赛前信息做出独立判断。

输出格式（严格遵守）：
FAVOR: [{team_a} / {team_b} / 势均力敌]
CONFIDENCE: [高/中/低]
ANALYSIS: [2-3句核心分析]"""

DEVILS_PROMPT = """你是魔鬼代言人。

{anti_hindsight}

比赛：{team_a} vs {team_b}（{year}年世界杯 {stage}）
热门队（赔率更低的一方）：{favorite}

赛前信息：
{context}

专找热门队败因，至少2条具体理由。

RISK_1: [理由]
RISK_2: [理由]
OVERALL_UPSET_RISK: [高/中/低]"""

JUDGE_PROMPT = """你是最终裁判。

{anti_hindsight}

比赛：{team_a} vs {team_b}（{year}年世界杯 {stage}）
是否淘汰赛（无平局）：{is_knockout}

专家分析汇总：
实力分析：{analysis_a}
战术分析：{analysis_b}
心理分析：{analysis_c}
魔鬼代言人：{devils}

按证据强度判决（不数票）。
证据优先级：硬事实（伤停/停赛/客观数据）> 战术分析 > 软因素（历史/心理）

输出格式（严格遵守，不得省略）：
PREDICTION: [{team_a}胜 / 平局 / {team_b}胜]（淘汰赛无平局）
CONFIDENCE: [高/中/低]
JUDGE_REASONING: [3-4句推理，体现证据优先级]
REASONS:
1. [球迷可读理由，提到具体球员或战术]
2. [同上]
3. [同上]"""


def call_agent(prompt: str, max_tokens: int = 800) -> str:
    resp = client.messages.create(
        model=config.MODEL,
        max_tokens=max_tokens,
        messages=[{"role": "user", "content": prompt}]
    )
    return resp.content[0].text


def extract_field(text: str, field: str) -> str:
    m = re.search(rf"^{field}:\s*(.+)", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def predict_match(ctx: dict, year: int, is_knockout: bool) -> dict:
    """运行5个Agent对一场历史比赛进行盲预测。"""
    team_a = ctx["team_a"]
    team_b = ctx["team_b"]
    stage = ctx.get("stage", "")
    context_str = json.dumps(ctx, ensure_ascii=False, indent=2)
    anti = ANTI_HINDSIGHT

    # 确定热门队（用赛前主观判断）
    favorite = ctx.get("estimated_odds_favorite", team_a)
    if favorite not in [team_a, team_b]:
        favorite = team_a

    # Agent A
    a_out = call_agent(AGENT_A_PROMPT.format(
        anti_hindsight=anti, team_a=team_a, team_b=team_b,
        year=year, stage=stage, context=context_str))

    # Agent B
    b_out = call_agent(AGENT_B_PROMPT.format(
        anti_hindsight=anti, team_a=team_a, team_b=team_b,
        year=year, stage=stage, context=context_str))

    # Agent C
    c_out = call_agent(AGENT_C_PROMPT.format(
        anti_hindsight=anti, team_a=team_a, team_b=team_b,
        year=year, stage=stage, context=context_str))

    # 魔鬼代言人
    d_out = call_agent(DEVILS_PROMPT.format(
        anti_hindsight=anti, team_a=team_a, team_b=team_b,
        year=year, stage=stage, favorite=favorite, context=context_str))

    # 裁判
    j_out = call_agent(JUDGE_PROMPT.format(
        anti_hindsight=anti, team_a=team_a, team_b=team_b,
        year=year, stage=stage,
        is_knockout="是" if is_knockout else "否",
        analysis_a=extract_field(a_out, "ANALYSIS"),
        analysis_b=extract_field(b_out, "ANALYSIS"),
        analysis_c=extract_field(c_out, "ANALYSIS"),
        devils=d_out[:300]
    ), max_tokens=1000)

    prediction = extract_field(j_out, "PREDICTION")
    confidence = extract_field(j_out, "CONFIDENCE")

    # 解析reasons
    reasons = re.findall(r"^\d+\.\s*(.+)", j_out, re.MULTILINE)

    return {
        "match_id": ctx["match_id"],
        "team_a": team_a,
        "team_b": team_b,
        "stage": stage,
        "_internal": {
            "agent_a": extract_field(a_out, "FAVOR"),
            "agent_b": extract_field(b_out, "FAVOR"),
            "agent_c": extract_field(c_out, "FAVOR"),
            "upset_risk": extract_field(d_out, "OVERALL_UPSET_RISK"),
            "judge_reasoning": extract_field(j_out, "JUDGE_REASONING"),
        },
        "output": {
            "prediction": prediction,
            "confidence": confidence,
            "reasons": reasons[:3]
        }
    }


def normalize_prediction(pred_str: str, team_a: str, team_b: str) -> str:
    """把预测字符串标准化为 A_WIN / DRAW / B_WIN。"""
    p = pred_str.strip()
    if team_a in p and "胜" in p:
        return "A_WIN"
    if team_b in p and "胜" in p:
        return "B_WIN"
    if "平" in p or "draw" in p.lower():
        return "DRAW"
    # 模糊匹配
    if team_a.lower() in p.lower():
        return "A_WIN"
    if team_b.lower() in p.lower():
        return "B_WIN"
    return "UNKNOWN"


def run_backtest(year: int):
    """对某年世界杯进行完整回测。"""
    print(f"\n{'='*60}")
    print(f"开始回测: {year} 世界杯")
    print(f"{'='*60}")

    # 加载数据
    context_file = DATA_DIR / f"prematch_context_{year}.json"
    if not context_file.exists():
        print(f"未找到赛前数据集: {context_file}")
        print("请先运行 dataset_builder.py 构建数据集")
        return

    contexts = {c["match_id"]: c for c in json.loads(context_file.read_text(encoding="utf-8"))}
    truth = json.loads((DATA_DIR / "results_truth.json").read_text(encoding="utf-8"))

    matches_file = DATA_DIR / f"matches_{year}.json"
    matches = json.loads(matches_file.read_text(encoding="utf-8"))["matches"]

    results = []
    correct = 0
    total = 0
    by_stage = {}
    upset_correct = 0
    upset_total = 0

    for i, match in enumerate(matches):
        mid = match["id"]
        if mid not in contexts:
            print(f"[{i+1}] 跳过（无赛前数据）: {mid}")
            continue
        if mid not in truth:
            print(f"[{i+1}] 跳过（无实际结果）: {mid}")
            continue

        # 检查是否已预测
        pred_file = PREDS_DIR / f"{mid}.json"
        if pred_file.exists():
            pred = json.loads(pred_file.read_text(encoding="utf-8"))
            print(f"[{i+1}/{len(matches)}] 已有预测: {match['team_a']} vs {match['team_b']} → {pred['output']['prediction']}")
        else:
            print(f"\n[{i+1}/{len(matches)}] 预测中: {match['team_a']} vs {match['team_b']}...")
            is_knockout = match["stage"] != "group_stage"
            try:
                pred = predict_match(contexts[mid], year, is_knockout)
                pred_file.write_text(json.dumps(pred, ensure_ascii=False, indent=2), encoding="utf-8")
                time.sleep(1)
            except Exception as e:
                print(f"  预测失败: {e}")
                continue

        # 评分
        actual = truth[mid]["outcome"]
        predicted_norm = normalize_prediction(
            pred["output"].get("prediction", ""),
            match["team_a"], match["team_b"]
        )

        is_correct = (predicted_norm == actual)
        is_upset = truth[mid].get("note", "").startswith("爆冷")

        stage = match["stage"]
        if stage not in by_stage:
            by_stage[stage] = {"total": 0, "correct": 0}
        by_stage[stage]["total"] += 1
        total += 1

        if is_correct:
            correct += 1
            by_stage[stage]["correct"] += 1
            if is_upset:
                upset_correct += 1

        if is_upset:
            upset_total += 1

        status = "✓" if is_correct else "✗"
        print(f"  {status} 预测:{predicted_norm} 实际:{actual} {'[爆冷]' if is_upset else ''} | {pred['output'].get('prediction','?')}")

        results.append({
            "match_id": mid,
            "year": year,
            "team_a": match["team_a"],
            "team_b": match["team_b"],
            "stage": stage,
            "predicted": predicted_norm,
            "predicted_str": pred["output"].get("prediction", ""),
            "actual": actual,
            "correct": is_correct,
            "is_upset": is_upset,
            "confidence": pred["output"].get("confidence", ""),
            "note": truth[mid].get("note", "")
        })

    # 保存结果
    result_file = BACKTEST_DIR / f"backtest_results_{year}.json"
    result_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    acc = correct / total * 100 if total > 0 else 0
    upset_acc = upset_correct / upset_total * 100 if upset_total > 0 else 0

    print(f"\n{'='*60}")
    print(f"{year}世界杯回测结果")
    print(f"{'='*60}")
    print(f"总计: {correct}/{total} = {acc:.1f}%")
    print(f"爆冷识别: {upset_correct}/{upset_total} = {upset_acc:.1f}%")
    print(f"\n按阶段:")
    for s, v in by_stage.items():
        sacc = v['correct'] / v['total'] * 100 if v['total'] > 0 else 0
        print(f"  {s}: {v['correct']}/{v['total']} = {sacc:.1f}%")

    return {
        "year": year,
        "total": total,
        "correct": correct,
        "accuracy": acc,
        "upset_correct": upset_correct,
        "upset_total": upset_total,
        "upset_accuracy": upset_acc,
        "by_stage": by_stage,
        "details": results
    }


if __name__ == "__main__":
    years = [2022, 2018]
    all_results = {}
    for y in years:
        r = run_backtest(y)
        if r:
            all_results[y] = r

    # 合计
    if all_results:
        t = sum(v["total"] for v in all_results.values())
        c = sum(v["correct"] for v in all_results.values())
        print(f"\n{'='*60}")
        print(f"综合准确率 (2018+2022): {c}/{t} = {c/t*100:.1f}%")
