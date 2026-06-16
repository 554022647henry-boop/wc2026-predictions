"""
赔率变动分析器
读取每场比赛各轮次的赔率历史，计算变动方向和幅度，
生成给裁判 Agent 使用的信号文本。

核心逻辑：
  - 赔率变短（odds decrease）= 该队获得市场资金 = 聪明钱押注
  - 变动幅度 >20%: 重要信号（与确认伤停同等权重）
  - 变动幅度 10-20%: 中等信号
  - 变动幅度 <10%: 正常波动，忽略
"""
import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

ODDS_DIR = Path(config.DATA_DIR) / "odds_history"


# ─────────────────────────────────────────
# 存储：每轮追加赔率快照
# ─────────────────────────────────────────

def append_odds_snapshot(match_id: str, round_key: str, odds: dict):
    """
    将本轮赔率快照追加到历史文件。
    odds 格式: {"pinnacle": {"a": 1.85, "draw": 3.60, "b": 4.20}, "bet365": {...}}
    """
    ODDS_DIR.mkdir(parents=True, exist_ok=True)
    file_path = ODDS_DIR / f"{match_id}.json"

    history = []
    if file_path.exists():
        history = json.loads(file_path.read_text(encoding="utf-8"))

    # 避免重复记录同一轮次
    if any(r["round"] == round_key for r in history):
        return

    snapshot = {"round": round_key, **odds}
    history.append(snapshot)
    file_path.write_text(json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8")


def load_odds_history(match_id: str) -> list[dict]:
    file_path = ODDS_DIR / f"{match_id}.json"
    if not file_path.exists():
        return []
    return json.loads(file_path.read_text(encoding="utf-8"))


# ─────────────────────────────────────────
# 分析：计算变动信号
# ─────────────────────────────────────────

ROUND_ORDER = ["initial", "T-24h", "T-12h", "T-2h", "T-30min"]


def _odds_to_prob(odds: float) -> float:
    """赔率转隐含概率（去掉 vig 前的原始值）。"""
    if not odds or odds <= 0:
        return 0.0
    return 1.0 / odds


def _pct_change(old: float, new: float) -> float:
    """计算赔率变化百分比（正值=变长/变贵，负值=变短/变便宜）。"""
    if not old or old == 0:
        return 0.0
    return (new - old) / old * 100


def analyze_odds_movement(match_id: str, team_a: str, team_b: str) -> dict:
    """
    分析赔率从开盘到封盘的变动。
    返回结构化分析结果，供裁判 Agent 使用。
    """
    history = load_odds_history(match_id)
    if len(history) < 2:
        return {
            "available": False,
            "signal": "无足够历史赔率数据（需至少2轮）",
            "weight": "无信号",
        }

    # 按轮次排序
    def round_idx(r):
        key = r.get("round", "")
        return ROUND_ORDER.index(key) if key in ROUND_ORDER else 99

    history_sorted = sorted(history, key=round_idx)
    first = history_sorted[0]
    last = history_sorted[-1]

    # 提取 Pinnacle 赔率（优先，最准）
    def get_odds(snap, side):
        pinnacle = snap.get("pinnacle", {})
        if not pinnacle:
            pinnacle = snap  # 兼容直接存在顶层的格式
        return pinnacle.get(side) or snap.get(f"pinnacle_{side}")

    open_a = get_odds(first, "a")
    open_draw = get_odds(first, "draw")
    open_b = get_odds(first, "b")
    close_a = get_odds(last, "a")
    close_draw = get_odds(last, "draw")
    close_b = get_odds(last, "b")

    if not (open_a and close_a):
        return {
            "available": False,
            "signal": "赔率数据不完整",
            "weight": "无信号",
        }

    change_a = _pct_change(open_a, close_a)
    change_b = _pct_change(open_b, close_b) if (open_b and close_b) else 0

    # 解读变动方向
    # 赔率变短（负变化）= 该队更被看好 = 有钱进来
    # 赔率变长（正变化）= 该队被抛售 = 资金撤离
    lines = []
    signal_level = "无显著信号"
    weight = "背景参考"
    favored_by_market = None

    lines.append(f"开盘: {team_a} {open_a:.2f} / 平局 {open_draw:.2f} / {team_b} {open_b:.2f}")
    lines.append(f"封盘: {team_a} {close_a:.2f} / 平局 {close_draw:.2f} / {team_b} {close_b:.2f}")
    lines.append("")

    # 分析 A 队变动
    if abs(change_a) >= 20:
        direction = "缩短" if change_a < 0 else "变长"
        lines.append(f"⚡ {team_a} 赔率{direction} {abs(change_a):.0f}%（{'市场大量买入' if change_a < 0 else '市场大量撤资'}）")
        signal_level = "强信号"
        weight = "第一级（与确认伤停同等权重）"
        favored_by_market = team_a if change_a < 0 else team_b
    elif abs(change_a) >= 10:
        direction = "缩短" if change_a < 0 else "变长"
        lines.append(f"△ {team_a} 赔率{direction} {abs(change_a):.0f}%（中等波动）")
        signal_level = "中等信号"
        weight = "第二级（与战术分析同等权重）"
        favored_by_market = team_a if change_a < 0 else team_b

    # 分析 B 队变动
    if abs(change_b) >= 20:
        direction = "缩短" if change_b < 0 else "变长"
        lines.append(f"⚡ {team_b} 赔率{direction} {abs(change_b):.0f}%（{'市场大量买入' if change_b < 0 else '市场大量撤资'}）")
        if signal_level != "强信号":
            signal_level = "强信号"
            weight = "第一级（与确认伤停同等权重）"
        favored_by_market = team_b if change_b < 0 else team_a
    elif abs(change_b) >= 10:
        direction = "缩短" if change_b < 0 else "变长"
        lines.append(f"△ {team_b} 赔率{direction} {abs(change_b):.0f}%（中等波动）")

    # 补充解读
    if signal_level == "无显著信号":
        lines.append(f"赔率变化 {team_a}: {change_a:+.1f}% / {team_b}: {change_b:+.1f}%（正常波动范围内）")
        lines.append("结论: 市场对开盘赔率判断无明显修正，无额外信号。")
    else:
        if favored_by_market:
            lines.append(f"结论: 市场聪明钱明显倾向 {favored_by_market}，")
            lines.append("      可能原因：已知伤停/首发变化/内部消息/赛前训练观察。")
            lines.append(f"      裁判应将此作为{weight}。")

    # 计算封盘隐含概率
    raw_a = _odds_to_prob(close_a)
    raw_draw = _odds_to_prob(close_draw) if close_draw else 0
    raw_b = _odds_to_prob(close_b)
    total = raw_a + raw_draw + raw_b
    if total > 0:
        prob_a = raw_a / total
        prob_draw = raw_draw / total
        prob_b = raw_b / total
        lines.append("")
        lines.append(f"封盘隐含概率（去vig）: {team_a} {prob_a*100:.0f}% / 平局 {prob_draw*100:.0f}% / {team_b} {prob_b*100:.0f}%")

    return {
        "available": True,
        "signal_level": signal_level,
        "weight": weight,
        "favored_by_market": favored_by_market,
        "change_a_pct": round(change_a, 1),
        "change_b_pct": round(change_b, 1),
        "analysis_text": "\n".join(lines),
        "rounds_captured": len(history),
    }


def get_odds_signal_for_judge(match_id: str, team_a: str, team_b: str) -> str:
    """
    返回给裁判 Agent 使用的赔率信号文字块。
    """
    result = analyze_odds_movement(match_id, team_a, team_b)
    if not result["available"]:
        return f"赔率历史：{result['signal']}"

    header = f"【赔率变动分析 — {result['signal_level']}】"
    return f"{header}\n{result['analysis_text']}"
