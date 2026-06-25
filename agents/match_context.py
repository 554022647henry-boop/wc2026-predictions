"""
match_context.py — 比赛上下文构建器（新架构）

只从真实来源获取数据，不调用DeepSeek生成内容：

  静态数据（KB v2）:
    - 大名单26人（ESPN官方）
    - 近期6场战绩（ESPN官方）
    - 教练/阵型/历史（AI历史，标注来源）

  实时数据（ESPN API，每场必取）:
    - 赔率（DraftKings）
    - 小组积分榜（从已完赛结果计算）
    - 休息天数（从kickoff_utc计算）
    - 确认首发（开球前1小时）
    - 伤停记录

输出：结构化的比赛上下文字典，直接传给7个Indicator Agent。
"""
import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
import config

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


# ════════════════════════════════════════════════════════
# 1. 从KB v2加载静态数据
# ════════════════════════════════════════════════════════

def load_team_static(team_name: str) -> dict:
    """从KB v2加载球队静态数据（大名单+战绩+历史）。"""
    kb_file = Path(config.BASE_DIR) / "data" / "team_knowledge_v2.json"
    if not kb_file.exists():
        return {"_error": "KB v2不存在"}
    kb = json.loads(kb_file.read_text(encoding="utf-8"))
    t = kb.get(team_name, {})
    if not t:
        return {"_error": f"{team_name}不在KB v2中"}

    sq = t.get("squad", {}).get("data", [])
    form = t.get("recent_form", {}).get("data", [])
    hist = t.get("historical", {})

    # 按位置分组大名单
    pos_groups = {}
    for p in sq:
        pos = p.get("pos", "?")
        pos_groups.setdefault(pos, []).append(p["name"])

    squad_by_pos = {pos: names for pos, names in pos_groups.items()}

    # 格式化近期战绩
    form_lines = []
    for m in form[:6]:
        h, a = m.get("home", "?"), m.get("away", "?")
        hs, as_ = m.get("home_score", "?"), m.get("away_score", "?")
        t_type = m.get("type", "?").replace("fifa.", "").replace("worldq.", "WCQ-")
        form_lines.append(f"{m.get('date', '?')} {h} {hs}-{as_} {a} [{t_type}]")

    return {
        "squad_count": len(sq),
        "squad_by_pos": squad_by_pos,
        "squad_list": [p["name"] for p in sq],
        "squad_source": "ESPN_ROSTER✅",
        "recent_form": form_lines,
        "form_source": "ESPN_API✅",
        "coach": hist.get("coach"),
        "formation": hist.get("formation"),
        "attack_style": hist.get("attack_style"),
        "defensive_weakness": hist.get("defensive_weakness"),
        "how_to_beat": hist.get("how_to_beat") or hist.get("defensive_how_to_beat"),
        "wc_2022": hist.get("wc_2022"),
        "wc_2018": hist.get("wc_2018"),
        "wc_2014": hist.get("wc_2014"),
        "opening_game_pattern": hist.get("opening_game_pattern"),
        "big_game_dna": hist.get("big_game_dna"),
        "hist_source": "DEEPSEEK_HISTORICAL⚠️",
    }


# ════════════════════════════════════════════════════════
# 2. 实时数据：赔率 + 首发 + 伤停
# ════════════════════════════════════════════════════════

def fetch_match_realtime(match_info: dict) -> dict:
    """从ESPN API获取赔率/首发/伤停（每场比赛实时获取）。"""
    from agents.collector import espn_find_event_id, espn_fetch_event_detail

    result = {
        "odds": None,
        "lineup_a": None,
        "lineup_b": None,
        "injuries": [],
        "odds_source": None,
        "lineup_source": None,
    }

    team_a = match_info["team_a"]
    team_b = match_info["team_b"]
    date_str = match_info.get("date", "2026-06-15")

    try:
        event_id = espn_find_event_id(team_a, team_b, date_str)
        if not event_id:
            return result

        detail = espn_fetch_event_detail(event_id)

        # 赔率
        odds_list = detail.get("odds", [])
        if odds_list:
            o = odds_list[0]
            prov = o.get("provider", {}).get("name", "")
            ho = o.get("homeTeamOdds", {})
            ao = o.get("awayTeamOdds", {})
            draw = o.get("drawOdds", {})
            draw_ml = draw.get("moneyLine") if isinstance(draw, dict) else draw
            result["odds"] = {
                "provider": prov,
                "team_a_ml": ho.get("moneyLine"),
                "draw_ml": draw_ml,
                "team_b_ml": ao.get("moneyLine"),
                "display": f"{prov}: {team_a} {ho.get('moneyLine','?')} / Draw {draw_ml} / {team_b} {ao.get('moneyLine','?')}",
            }
            result["odds_source"] = f"ESPN_API✅ (event={event_id})"

        # 首发
        for roster in detail.get("rosters", []):
            tname = roster.get("team", {}).get("displayName", "")
            starters = [
                a.get("athlete", {}).get("displayName", "") or a.get("displayName", "")
                for a in roster.get("athletes", [])
                if a.get("starter")
            ][:11]
            if starters:
                if team_a in tname or any(w in tname for w in team_a.split()):
                    result["lineup_a"] = starters
                else:
                    result["lineup_b"] = starters
                result["lineup_source"] = "ESPN_API✅"

        # 伤停
        for inj in detail.get("injuries", []):
            p = inj.get("athlete", {}).get("displayName", "")
            t = inj.get("team", {}).get("displayName", "")
            s = inj.get("type", {}).get("description", "")
            if p and t:
                result["injuries"].append(f"{t} | {p}: {s}")

    except Exception as e:
        result["_error"] = str(e)

    return result


# ════════════════════════════════════════════════════════
# 3. 实时数据：小组积分榜
# ════════════════════════════════════════════════════════

def build_group_standings(match_info: dict) -> dict:
    """从已有比赛结果计算小组积分榜，判断晋级形势。"""
    group = match_info.get("group", "")
    team_a = match_info["team_a"]
    team_b = match_info["team_b"]

    results_file = Path(config.RESULTS_FILE)
    fixtures_file = Path(config.FIXTURES_FILE)

    if not results_file.exists() or not fixtures_file.exists():
        return {}

    results = {k: v for k, v in json.loads(results_file.read_text(encoding="utf-8")).items()
               if isinstance(v, dict)}
    fixtures = json.loads(fixtures_file.read_text(encoding="utf-8"))

    # 找同组所有比赛
    group_matches = [
        m for m in fixtures["matches"]
        if m.get("group") == group and m.get("stage") == "group_stage"
    ]

    if not group_matches:
        return {}

    # 计算积分
    teams_in_group = set()
    for m in group_matches:
        teams_in_group.add(m["team_a"])
        teams_in_group.add(m["team_b"])

    standings = {t: {"pts": 0, "w": 0, "d": 0, "l": 0, "gf": 0, "ga": 0, "played": 0}
                 for t in teams_in_group}

    completed = []
    for m in group_matches:
        mid = m["match_id"]
        if mid not in results:
            continue
        r = results[mid]
        ta, tb = r["team_a"], r["team_b"]
        score = r.get("score", "0-0")
        try:
            gf, ga = map(int, score.split("-"))
        except Exception:
            gf, ga = 0, 0

        outcome = r["outcome"]
        standings[ta]["played"] += 1
        standings[tb]["played"] += 1
        standings[ta]["gf"] += gf
        standings[ta]["ga"] += ga
        standings[tb]["gf"] += ga
        standings[tb]["ga"] += gf

        if outcome == "A_WIN":
            standings[ta]["pts"] += 3
            standings[ta]["w"] += 1
            standings[tb]["l"] += 1
        elif outcome == "B_WIN":
            standings[tb]["pts"] += 3
            standings[tb]["w"] += 1
            standings[ta]["l"] += 1
        else:
            standings[ta]["pts"] += 1
            standings[tb]["pts"] += 1
            standings[ta]["d"] += 1
            standings[tb]["d"] += 1

        completed.append(f"MD{m.get('matchday','?')}: {ta} {gf}-{ga} {tb}")

    # 排序
    sorted_teams = sorted(standings.keys(),
                          key=lambda t: (-standings[t]["pts"],
                                        -(standings[t]["gf"] - standings[t]["ga"])))

    table_lines = []
    for i, t in enumerate(sorted_teams, 1):
        s = standings[t]
        gd = s["gf"] - s["ga"]
        flag = " ← 本场参与" if t in (team_a, team_b) else ""
        table_lines.append(
            f"  {i}. {t}: {s['pts']}分 ({s['w']}胜{s['d']}平{s['l']}负) 净胜球{gd:+d}{flag}"
        )

    # 判断本场意义
    remaining = len([m for m in group_matches if m["match_id"] not in results])
    stakes = _assess_stakes(team_a, team_b, standings, remaining, sorted_teams)

    return {
        "group": group,
        "table": table_lines,
        "completed": completed,
        "remaining_matches": remaining,
        "stakes_a": stakes.get(team_a, "积分尚不明确"),
        "stakes_b": stakes.get(team_b, "积分尚不明确"),
        "_source": "ESPN_RESULTS✅（从已完赛结果计算）",
    }


def _assess_stakes(team_a, team_b, standings, remaining, sorted_teams):
    """判断双方在此战的利益关系（必须赢/可以平/已出线等）。"""
    stakes = {}
    for team in (team_a, team_b):
        s = standings.get(team, {})
        pts = s.get("pts", 0)
        played = s.get("played", 0)
        pos = sorted_teams.index(team) + 1 if team in sorted_teams else 4

        if pts >= 7:
            stakes[team] = "已锁定出线，此战可保守"
        elif pts >= 4 and pos <= 2:
            stakes[team] = "出线形势较好，需避免大败"
        elif pts == 0 and played == 2:
            stakes[team] = "两连败，此战必须赢球否则出局"
        elif pts <= 1 and played >= 1:
            stakes[team] = "积分落后，需要赢球保持出线希望"
        else:
            stakes[team] = f"当前{pts}分，出线形势待定"
    return stakes


# ════════════════════════════════════════════════════════
# 4. 计算休息天数
# ════════════════════════════════════════════════════════

def get_rest_days(team_name: str, current_kickoff_utc: str) -> dict:
    """计算该队距上一场比赛的休息天数。"""
    results_file = Path(config.RESULTS_FILE)
    fixtures_file = Path(config.FIXTURES_FILE)
    if not results_file.exists():
        return {"rest_days": None, "_source": "无数据"}

    results = {k: v for k, v in json.loads(results_file.read_text(encoding="utf-8")).items()
               if isinstance(v, dict)}
    fixtures = json.loads(fixtures_file.read_text(encoding="utf-8"))

    try:
        current_dt = datetime.fromisoformat(current_kickoff_utc.replace("Z", "+00:00"))
    except Exception:
        return {"rest_days": None}

    last_match_dt = None
    for m in fixtures["matches"]:
        if team_name not in (m.get("team_a"), m.get("team_b")):
            continue
        if m["match_id"] not in results:
            continue
        ku = m.get("kickoff_utc", "")
        if not ku:
            continue
        try:
            dt = datetime.fromisoformat(ku.replace("Z", "+00:00"))
            if dt < current_dt:
                if last_match_dt is None or dt > last_match_dt:
                    last_match_dt = dt
        except Exception:
            pass

    if last_match_dt:
        rest = (current_dt - last_match_dt).days
        return {"rest_days": rest, "last_match": last_match_dt.strftime("%Y-%m-%d"),
                "_source": "kickoff_utc✅"}
    return {"rest_days": None, "_note": "未找到上一场比赛"}


# ════════════════════════════════════════════════════════
# 5. 组装完整比赛上下文
# ════════════════════════════════════════════════════════

def build_match_context(match_info: dict) -> dict:
    """
    主函数：组装一场比赛所有需要的上下文数据。
    返回结构化字典，直接传给predictor的7个agents。
    """
    team_a = match_info["team_a"]
    team_b = match_info["team_b"]
    ku = match_info.get("kickoff_utc", "")

    print(f"  [上下文构建] {team_a} vs {team_b}")

    # 1. 静态数据（KB v2）
    print("    [KB v2] 加载大名单+战绩+历史...")
    static_a = load_team_static(team_a)
    static_b = load_team_static(team_b)
    print(f"    {team_a}: {static_a.get('squad_count', 0)}人大名单, {len(static_a.get('recent_form', []))}场战绩")
    print(f"    {team_b}: {static_b.get('squad_count', 0)}人大名单, {len(static_b.get('recent_form', []))}场战绩")

    # 2. 实时数据（ESPN）
    print("    [ESPN] 赔率/首发/伤停...")
    realtime = fetch_match_realtime(match_info)
    if realtime.get("odds"):
        print(f"    赔率: {realtime['odds']['display']}")
    else:
        print("    赔率: 未获取")

    # 3. 小组积分
    print("    [积分榜] 计算小组形势...")
    standings = build_group_standings(match_info)

    # 4. 休息天数
    rest_a = get_rest_days(team_a, ku) if ku else {}
    rest_b = get_rest_days(team_b, ku) if ku else {}

    ctx = {
        "match_id":  match_info["match_id"],
        "team_a":    team_a,
        "team_b":    team_b,
        "stage":     match_info.get("stage", "group_stage"),
        "kickoff":   ku,
        "venue":     match_info.get("venue", ""),

        # 实时：赔率
        "odds":      realtime.get("odds"),
        "odds_source": realtime.get("odds_source"),

        # 实时：首发
        "lineup_a":  realtime.get("lineup_a"),
        "lineup_b":  realtime.get("lineup_b"),
        "lineup_source": realtime.get("lineup_source"),

        # 实时：伤停
        "injuries":  realtime.get("injuries", []),

        # 实时：积分/形势
        "standings": standings,
        "rest_days_a": rest_a,
        "rest_days_b": rest_b,

        # 静态（KB v2）
        "team_a_data": static_a,
        "team_b_data": static_b,
    }

    return ctx


def context_to_text(ctx: dict) -> str:
    """把上下文字典转成供Agent使用的文本格式。"""
    ta = ctx["team_a"]
    tb = ctx["team_b"]
    lines = []

    lines.append(f"{'='*60}")
    lines.append(f"比赛: {ta} vs {tb} | {ctx.get('stage','')} | {ctx.get('kickoff','')[:10]}")
    lines.append(f"场地: {ctx.get('venue','')}")
    lines.append(f"{'='*60}")

    # 赔率
    if ctx.get("odds"):
        lines.append(f"\n【赔率 {ctx['odds_source']}】")
        lines.append(f"  {ctx['odds']['display']}")
    else:
        lines.append("\n【赔率】未获取")

    # 首发
    if ctx.get("lineup_a") or ctx.get("lineup_b"):
        lines.append(f"\n【确认首发 {ctx.get('lineup_source','')}】")
        if ctx.get("lineup_a"):
            lines.append(f"  {ta}: {', '.join(ctx['lineup_a'][:11])}")
        if ctx.get("lineup_b"):
            lines.append(f"  {tb}: {', '.join(ctx['lineup_b'][:11])}")
    else:
        lines.append("\n【首发】开球前1小时公布")

    # 伤停
    if ctx.get("injuries"):
        lines.append("\n【伤停 ESPN✅】")
        for inj in ctx["injuries"]:
            lines.append(f"  {inj}")

    # 积分/形势
    st = ctx.get("standings", {})
    if st.get("table"):
        lines.append(f"\n【{st['group']}组积分榜 ESPN✅】")
        for row in st["table"]:
            lines.append(row)
        if st.get("stakes_a"):
            lines.append(f"\n  本场意义:")
            lines.append(f"    {ta}: {st['stakes_a']}")
            lines.append(f"    {tb}: {st['stakes_b']}")

    # 休息天数
    ra = ctx.get("rest_days_a", {})
    rb = ctx.get("rest_days_b", {})
    if ra.get("rest_days") is not None or rb.get("rest_days") is not None:
        lines.append("\n【休息天数 ESPN✅】")
        if ra.get("rest_days") is not None:
            lines.append(f"  {ta}: {ra['rest_days']}天（上场 {ra.get('last_match', '?')}）")
        if rb.get("rest_days") is not None:
            lines.append(f"  {tb}: {rb['rest_days']}天（上场 {rb.get('last_match', '?')}）")

    # A队完整数据
    for team, data_key in [(ta, "team_a_data"), (tb, "team_b_data")]:
        d = ctx.get(data_key, {})
        if not d or d.get("_error"):
            lines.append(f"\n【{team}】KB v2数据缺失")
            continue

        lines.append(f"\n{'─'*50}")
        lines.append(f"【{team} 大名单 {d['squad_source']}】（{d['squad_count']}人）")
        for pos, names in d.get("squad_by_pos", {}).items():
            lines.append(f"  {pos}: {', '.join(names)}")

        lines.append(f"\n【{team} 近期{len(d.get('recent_form',[]))}场战绩 {d['form_source']}】")
        for row in d.get("recent_form", []):
            lines.append(f"  {row}")

        lines.append(f"\n【{team} 战术 {d['hist_source']}】")
        lines.append(f"  教练: {d.get('coach','?')} | 阵型: {d.get('formation','?')}")
        if d.get("attack_style"):
            lines.append(f"  进攻: {d['attack_style']}")
        if d.get("defensive_weakness"):
            lines.append(f"  防守弱点: {d['defensive_weakness']}")
        if d.get("how_to_beat"):
            lines.append(f"  如何破防: {d['how_to_beat']}")

        lines.append(f"\n【{team} 世界杯历史 {d['hist_source']}】")
        for yr in ("wc_2022", "wc_2018", "wc_2014"):
            val = d.get(yr)
            if val:
                lines.append(f"  {yr.replace('wc_', '')}: {val}")
        if d.get("opening_game_pattern"):
            lines.append(f"  首轮规律: {d['opening_game_pattern']}")
        if d.get("big_game_dna"):
            lines.append(f"  大赛DNA: {d['big_game_dna']}")

    return "\n".join(lines)
