"""
本届赛事动能 Agent
分析两队在「当前世界杯」中的实际表现，
识别「越打越强」或「越打越差」的趋势。

核心价值：
  - 摩洛哥在本届赢了比利时→西班牙→葡萄牙，这是硬数据，
    比「历史上摩洛哥从未进过世界杯4强」更有预测价值
  - 某队连续失球，防线已暴露，这比赛季初的技术统计更相关
"""
import json
from pathlib import Path
from typing import Optional

import anthropic
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

client = config.make_client()

TOURNAMENT_LOG_FILE = Path(config.DATA_DIR) / "tournament_log.json"

MOMENTUM_SYSTEM = """你是世界杯预测系统的【本届赛事动能分析师】。

你的职责：分析两队在「本届世界杯」的实际交战记录，
评估当前赛事状态——而非历史声誉或长期统计。

判断维度：
1. 进攻动能：场均进球趋势（在上升/稳定/下降）
2. 防守稳定性：场均失球趋势，有无暴露明显漏洞
3. 已证明的大赛战绩：本届赛事中已击败了哪些强队
4. 战术进化迹象：打法是否在适应和改进
5. 体能与轮换：连续作战是否有疲劳迹象

重要原则：
- 本届赛事数据权重 > 历史数据
- 如果某队本届已经赢过比当前对手更强的队伍，这是第一级证据
- 连败/连胜趋势本身就是信号
- 点球/加时获胜 vs 正常时间获胜在评估时要区分"""

MOMENTUM_PROMPT = """分析以下两队在本届世界杯中的表现动能。

比赛：{team_a} vs {team_b}
阶段：{stage}

{team_a} 本届赛事记录：
{log_a}

{team_b} 本届赛事记录：
{log_b}

请分析：
1. 两队各自的进攻/防守趋势（上升/稳定/下滑）
2. 本届已击败的对手质量对比
3. 有没有「越打越强」的信号
4. 有没有「被摸透了/疲态」的信号
5. 体能状态：上一场是否打了加时/点球，休息天数影响

输出格式（严格遵守）：
FAVOR: [{team_a} / {team_b} / 势均力敌]
CONFIDENCE: [高/中/低]
MOMENTUM_A: [上升/稳定/下滑]
MOMENTUM_B: [上升/稳定/下滑]
ANALYSIS: [2-4句核心分析，必须引用具体比赛数据]
KEY_EVIDENCE: [最关键的一条本届赛事证据]"""


# ─────────────────────────────────────────
# 数据管理
# ─────────────────────────────────────────

def load_tournament_log() -> dict:
    """加载全局赛事记录。"""
    if not TOURNAMENT_LOG_FILE.exists():
        return {}
    return json.loads(TOURNAMENT_LOG_FILE.read_text(encoding="utf-8"))


def save_tournament_log(log: dict):
    TOURNAMENT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOURNAMENT_LOG_FILE.write_text(
        json.dumps(log, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def add_match_result(team_a: str, team_b: str, stage: str,
                     result_a: str, score: str,
                     xg_a: Optional[float] = None, xg_b: Optional[float] = None):
    """
    比赛结束后录入结果到赛事日志。
    result_a: 'W'（A赢）/ 'D'（平）/ 'L'（A负）
    """
    log = load_tournament_log()

    def add_entry(team: str, vs: str, result: str, own_score: str, opp_score: str,
                  own_xg: Optional[float], opp_xg: Optional[float]):
        if team not in log:
            log[team] = []
        entry = {
            "stage": stage,
            "vs": vs,
            "result": result,
            "score": f"{own_score}-{opp_score}",
        }
        if own_xg is not None:
            entry["xg_for"] = round(own_xg, 2)
        if opp_xg is not None:
            entry["xg_against"] = round(opp_xg, 2)
        log[team].append(entry)

    # 解析比分
    parts = score.replace(" ", "").split("-")
    score_a, score_b = parts[0], parts[1] if len(parts) > 1 else "?"

    # 录入 A 队
    add_entry(team_a, team_b, result_a, score_a, score_b, xg_a, xg_b)

    # 录入 B 队（镜像）
    result_b = {"W": "L", "L": "W", "D": "D"}[result_a]
    add_entry(team_b, team_a, result_b, score_b, score_a, xg_b, xg_a)

    save_tournament_log(log)
    print(f"[赛事日志] 已录入: {team_a} {score} {team_b} ({stage})")


def get_team_log(team: str) -> list[dict]:
    """获取某队本届赛事记录。"""
    log = load_tournament_log()
    return log.get(team, [])


def format_team_log(team: str) -> str:
    """格式化某队赛事记录供 Agent 阅读。"""
    entries = get_team_log(team)
    if not entries:
        return f"{team}：本届赛事暂无已完成比赛记录（首场比赛）"

    lines = [f"{team} 本届赛事表现（共{len(entries)}场）："]
    total_goals_for = 0
    total_goals_against = 0

    for e in entries:
        result_emoji = {"W": "✓胜", "D": "△平", "L": "✗负"}.get(e["result"], e["result"])
        xg_info = ""
        if "xg_for" in e and "xg_against" in e:
            xg_info = f" | xG {e['xg_for']:.1f}-{e['xg_against']:.1f}"

        stage_label = {
            "group_stage": "小组赛", "round_of_16": "16强",
            "quarterfinal": "8强", "semifinal": "半决赛", "final": "决赛"
        }.get(e["stage"], e["stage"])

        lines.append(f"  {stage_label} vs {e['vs']}: {result_emoji} {e['score']}{xg_info}")

        try:
            g_for, g_against = e["score"].split("-")
            # 处理加时/点球格式如 "1-1 (PKs 3-0)"
            g_for = int(g_for.strip().split()[0])
            g_against = int(g_against.strip().split()[0])
            total_goals_for += g_for
            total_goals_against += g_against
        except Exception:
            pass

    n = len(entries)
    if n > 0:
        wins = sum(1 for e in entries if e["result"] == "W")
        draws = sum(1 for e in entries if e["result"] == "D")
        losses = sum(1 for e in entries if e["result"] == "L")
        lines.append(f"  汇总: {wins}胜{draws}平{losses}负 | 进{total_goals_for}球失{total_goals_against}球")

        # 趋势分析
        if n >= 2:
            recent = entries[-2:]
            recent_wins = sum(1 for e in recent if e["result"] == "W")
            early = entries[:max(1, n-2)]
            early_wins = sum(1 for e in early if e["result"] == "W")
            if recent_wins > early_wins / len(early) * len(recent):
                lines.append(f"  趋势: ↑ 近期状态上升")
            elif recent_wins < early_wins / len(early) * len(recent):
                lines.append(f"  趋势: ↓ 近期状态下滑")

    return "\n".join(lines)


# ─────────────────────────────────────────
# Agent 调用
# ─────────────────────────────────────────

def run_momentum_agent(match_info: dict) -> dict:
    """
    运行本届赛事动能分析。
    返回结构化结果供 predictor.py 使用。
    """
    import re
    team_a = match_info["team_a"]
    team_b = match_info["team_b"]
    stage = match_info.get("stage", "")

    log_a = format_team_log(team_a)
    log_b = format_team_log(team_b)

    # 如果两队都没有赛事记录（首场），给低权重提示
    has_data_a = bool(get_team_log(team_a))
    has_data_b = bool(get_team_log(team_b))

    if not has_data_a and not has_data_b:
        return {
            "favor": "势均力敌",
            "confidence": "低",
            "momentum_a": "未知",
            "momentum_b": "未知",
            "analysis": "本届赛事均无已完成比赛记录，动能分析不适用（首场比赛）",
            "key_evidence": "无本届数据",
            "raw": "",
            "has_data": False,
        }

    prompt = MOMENTUM_PROMPT.format(
        team_a=team_a,
        team_b=team_b,
        stage=stage,
        log_a=log_a,
        log_b=log_b,
    )

    resp = client.messages.create(
        model=config.MODEL,
        max_tokens=800,
        system=MOMENTUM_SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text

    def extract(field):
        m = re.search(rf"^{field}:\s*(.+)", text, re.MULTILINE)
        return m.group(1).strip() if m else ""

    result = {
        "favor": extract("FAVOR"),
        "confidence": extract("CONFIDENCE"),
        "momentum_a": extract("MOMENTUM_A"),
        "momentum_b": extract("MOMENTUM_B"),
        "analysis": extract("ANALYSIS"),
        "key_evidence": extract("KEY_EVIDENCE"),
        "raw": text,
        "has_data": True,
    }

    print(f"  [动能Agent] 倾向: {result['favor']} ({result['confidence']}) | "
          f"{team_a}:{result['momentum_a']} / {team_b}:{result['momentum_b']}")
    return result
