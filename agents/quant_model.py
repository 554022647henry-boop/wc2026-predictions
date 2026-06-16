"""
数学汇总模型 v2
输入：N个 Indicator Agent 评分 + 赔率校验器
输出：A胜/平局/B胜 概率分布 + 最终预测

加权 delta 公式：
  δ = Σ(weight_i × conf_i × (a_i - b_i)) / Σ(weight_i × conf_i)

赔率校验：
  若预测概率与赔率隐含概率差距 >20% → 触发警告，降低置信度
  H 不改变预测方向，只影响置信度标签

平局建模（关键改进）：
  |δ| 越小 → P(Draw) 越高
  国际比赛平均平局率约 24-27%，此表经过校准
"""
import math
from typing import Optional


# ── 概率映射表（基于 δ 范围，已针对国际赛校准）────────────────────
# (delta_low, delta_high, P_A_win, P_draw, P_B_win)
PROB_TABLE = [
    (3.5,  math.inf, 0.68, 0.18, 0.14),
    (2.5,  3.5,      0.58, 0.23, 0.19),
    (1.8,  2.5,      0.50, 0.28, 0.22),
    (1.1,  1.8,      0.43, 0.33, 0.24),
    (0.5,  1.1,      0.38, 0.36, 0.26),
    (0.1,  0.5,      0.34, 0.38, 0.28),
    (-0.1, 0.1,      0.32, 0.39, 0.29),   # 极度平衡
    (-0.5, -0.1,     0.28, 0.38, 0.34),
    (-1.1, -0.5,     0.26, 0.36, 0.38),
    (-1.8, -1.1,     0.24, 0.33, 0.43),
    (-2.5, -1.8,     0.22, 0.28, 0.50),
    (-3.5, -2.5,     0.19, 0.23, 0.58),
    (-math.inf, -3.5, 0.14, 0.18, 0.68),
]


def delta_to_probs(delta: float) -> tuple[float, float, float]:
    for lo, hi, pa, pd, pb in PROB_TABLE:
        if lo <= delta < hi:
            return pa, pd, pb
    return 0.32, 0.39, 0.29


def moneyline_to_prob(ml: float) -> float:
    """美式赔率 → 原始概率（未去vig）"""
    if ml is None:
        return 0.0
    ml = float(ml)
    if ml > 0:
        return 100 / (ml + 100)
    else:
        return abs(ml) / (abs(ml) + 100)


def aggregate_scores(agent_scores: list[dict],
                     odds_calibrator: dict | None = None,
                     is_knockout: bool = False) -> dict:
    """
    汇总 N 个 Indicator Agent 评分，返回完整预测结果。

    Parameters
    ----------
    agent_scores    : 来自 run_n_agents() 的评分列表
    odds_calibrator : 来自 run_odds_calibrator() 的赔率校验结果（可选）
    is_knockout     : 淘汰赛时无平局选项
    """
    if not agent_scores:
        return {"prediction": "DRAW", "p_a_win": 0.33, "p_draw": 0.34,
                "p_b_win": 0.33, "weighted_delta": 0.0, "confidence_level": "低"}

    # ── 加权分差（权重 × 置信度 × 分差）───────────────────────────
    total_w = 0.0
    weighted_sum = 0.0
    dim_breakdown = []

    for s in agent_scores:
        w = float(s.get("weight", 1.0 / len(agent_scores)))
        conf = max(0.1, float(s.get("confidence", 5)))
        a = float(s.get("team_a_score", 5))
        b = float(s.get("team_b_score", 5))
        effective_w = w * conf
        weighted_sum += effective_w * (a - b)
        total_w += effective_w
        dim_breakdown.append({
            "dimension": s.get("dimension", "?"),
            "label": s.get("label", "?"),
            "a_score": a, "b_score": b,
            "delta": round(a - b, 1),
            "confidence": round(conf, 1),
            "weight": round(w, 3),
            "key_factors": s.get("key_factors", []),
            "reasoning": s.get("reasoning", ""),
        })

    delta = weighted_sum / total_w if total_w > 0 else 0.0

    # ── 基础概率 ─────────────────────────────────────────────────
    p_a, p_d, p_b = delta_to_probs(delta)

    # ── 淘汰赛：平局概率分摊 ──────────────────────────────────────
    prediction = max({"A_WIN": p_a, "DRAW": p_d, "B_WIN": p_b},
                     key=lambda k: {"A_WIN": p_a, "DRAW": p_d, "B_WIN": p_b}[k])
    if is_knockout:
        if prediction == "DRAW":
            prediction = "A_WIN" if delta >= 0 else "B_WIN"
        # 重新计算（去平局）
        if delta >= 0:
            p_a += p_d * 0.55; p_b += p_d * 0.45
        else:
            p_b += p_d * 0.55; p_a += p_d * 0.45
        p_d = 0.0

    # ── 置信度判断 ────────────────────────────────────────────────
    abs_delta = abs(delta)
    avg_conf = total_w / max(len(agent_scores), 1)

    if abs_delta >= 2.0 and avg_conf >= 6.0:
        confidence = "高"
    elif abs_delta >= 1.0 or avg_conf >= 5.0:
        confidence = "中"
    else:
        confidence = "低"

    # ── 赔率校验（H维度）─────────────────────────────────────────
    calibration_note = ""
    calibration_warning = False
    if odds_calibrator and odds_calibrator.get("confidence", 0) >= 3:
        # 从赔率 agent 的评分推算市场隐含概率
        # team_a_score=10时意味着 P(A)~0.95, score=5时~0.5
        odds_a = odds_calibrator.get("team_a_score", 5) / 10.0
        odds_b = odds_calibrator.get("team_b_score", 5) / 10.0
        odds_d = 1 - odds_a - odds_b
        odds_d = max(0.1, odds_d)
        total_odds = odds_a + odds_d + odds_b
        mkt_a = odds_a / total_odds
        mkt_d = odds_d / total_odds
        mkt_b = odds_b / total_odds

        # 比较市场概率与模型概率
        model_p = {"A_WIN": p_a, "DRAW": p_d, "B_WIN": p_b}
        mkt_p = {"A_WIN": mkt_a, "DRAW": mkt_d, "B_WIN": mkt_b}

        max_divergence = max(abs(model_p[k] - mkt_p[k]) for k in model_p)
        if max_divergence > 0.20:
            calibration_warning = True
            calibration_note = (
                f"⚠️ 赔率偏差 {max_divergence:.0%}：模型 {prediction} "
                f"P(A)={p_a:.0%}/P(D)={p_d:.0%}/P(B)={p_b:.0%} vs "
                f"市场 P(A)={mkt_a:.0%}/P(D)={mkt_d:.0%}/P(B)={mkt_b:.0%}"
            )
            if confidence == "高":
                confidence = "中"  # 降级

    return {
        "weighted_delta":     round(delta, 2),
        "p_a_win":            round(p_a, 3),
        "p_draw":             round(p_d, 3),
        "p_b_win":            round(p_b, 3),
        "prediction":         prediction,
        "confidence_level":   confidence,
        "calibration_warning": calibration_warning,
        "calibration_note":   calibration_note,
        "n_agents":           len(agent_scores),
        "dimension_breakdown": dim_breakdown,
    }


def predict_with_n_agents(n: int, team_a: str, team_b: str,
                          context: str, stage: str = "",
                          is_knockout: bool = False,
                          use_calibrator: bool = True) -> dict:
    """
    用 N 个 Indicator Agent 完成一场比赛的量化预测。
    顺序：实力→状态→战术→球员→化学→情境→DNA（按权重从高到低）
    """
    from agents.indicator_agents import run_n_agents, run_odds_calibrator

    print(f"  [量化模型] N={n} | {team_a} vs {team_b}")
    scores = run_n_agents(n, team_a, team_b, context, stage)

    calibrator = None
    if use_calibrator:
        calibrator = run_odds_calibrator(team_a, team_b, context)

    result = aggregate_scores(scores, calibrator, is_knockout)
    result["n_agents"] = n
    result["team_a"] = team_a
    result["team_b"] = team_b
    result["stage"] = stage
    result["odds_calibrator"] = calibrator

    print(f"  → δ={result['weighted_delta']:+.2f} | "
          f"P(A)={result['p_a_win']:.0%} P(D)={result['p_draw']:.0%} P(B)={result['p_b_win']:.0%} "
          f"| 预测:{result['prediction']} ({result['confidence_level']})"
          + (" ⚠️" if result.get("calibration_warning") else ""))

    return result
