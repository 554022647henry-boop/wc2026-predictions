"""
build_kb_v2.py — 知识库重建（v2，带来源验证）

架构：
  Agent 1 (collect_team): 按数据来源逐个抓取，每个字段标注来源URL
  Agent 2 (review_team):  审核来源真实性，AI生成 → 标 _verified:false，找不到 → null
  结果存入 data/team_knowledge_v2.json

数据来源优先级：
  1. ESPN Roster API   → 大名单26人（姓名/位置/年龄）
  2. ESPN Friendly API → 近期热身赛（最近8场）
  3. ESPN WCQ API      → 近期预选赛（最近8场）
  4. Sofascore 浏览器  → 球员俱乐部、全部近期比赛
  5. DeepSeek 历史     → 战术风格、WC历史（必须标注历史来源）
"""
import json
import sys
import time
import requests
from pathlib import Path
from datetime import datetime

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, str(Path(__file__).parent))
import config

client = config.make_client()
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# ── ESPN team_id 映射（名称标准化）────────────────────
ESPN_NAME_MAP = {
    "Bosnia and Herzegovina": "Bosnia-Herzegovina",
    "DR Congo": "Congo DR",
    "Curacao": "Curaçao",
    "Turkiye": "Türkiye",
}

def get_espn_team_ids() -> dict:
    """获取ESPN WC球队ID（fixture名称 → ESPN ID）。"""
    r = requests.get(
        'https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams',
        headers=HEADERS, timeout=10
    )
    espn_teams = r.json().get('sports',[{}])[0].get('leagues',[{}])[0].get('teams',[])
    espn_map = {t['team']['displayName']: t['team']['id'] for t in espn_teams}

    # 从fixtures加载我们的队名
    fixtures = json.loads(Path(config.FIXTURES_FILE).read_text(encoding='utf-8'))
    our_teams = set()
    for m in fixtures['matches']:
        if m.get('team_a') not in ('TBD', ''): our_teams.add(m['team_a'])
        if m.get('team_b') not in ('TBD', ''): our_teams.add(m['team_b'])

    result = {}
    for our_name in our_teams:
        espn_name = ESPN_NAME_MAP.get(our_name, our_name)
        if espn_name in espn_map:
            result[our_name] = espn_map[espn_name]
        else:
            result[our_name] = None
    return result


def _parse_score(score_raw) -> str:
    """ESPN score字段可能是字符串或嵌套对象，统一提取显示值。"""
    if isinstance(score_raw, dict):
        return score_raw.get('displayValue', score_raw.get('value', '?'))
    return str(score_raw) if score_raw is not None else '?'


# ════════════════════════════════════════════════════
# AGENT 1: 数据采集
# ════════════════════════════════════════════════════

def collect_squad(team_name: str, espn_id: str) -> dict:
    """从ESPN Roster API采集大名单。"""
    if not espn_id:
        return {"data": [], "_source": "ESPN_ROSTER:no_id", "_verified": False, "_count": 0}
    url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams/{espn_id}/roster"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        athletes = r.json().get('athletes', [])
        players = []
        for a in athletes:
            pos_raw = a.get('position', {})
            pos = pos_raw.get('abbreviation', '?') if isinstance(pos_raw, dict) else str(pos_raw)
            inj = a.get('injuries', [])
            players.append({
                "name": a.get('displayName', '?'),
                "pos": pos,
                "age": a.get('age'),
                "jersey": a.get('jersey', ''),
                "club": None,          # ESPN不提供俱乐部，Sofascore补充
                "injury": inj[0].get('status', {}).get('description') if inj else None,
                "_source": f"ESPN_ROSTER:{url}",
                "_verified": True,
            })
        return {"data": players, "_source": f"ESPN_ROSTER:{url}", "_verified": True, "_count": len(players)}
    except Exception as e:
        return {"data": [], "_source": f"ESPN_ROSTER:failed:{e}", "_verified": False, "_count": 0}


def collect_recent_form(team_name: str, espn_id: str) -> dict:
    """从ESPN Friendly + WCQ API采集近期战绩。"""
    if not espn_id:
        return {"data": [], "_sources": [], "_verified": False}

    # 每个洲的WCQ联赛
    CONF_MAP = {
        **dict.fromkeys(["France","Spain","Germany","England","Belgium","Netherlands","Portugal",
                         "Croatia","Switzerland","Austria","Norway","Sweden","Scotland","Czechia",
                         "Bosnia and Herzegovina","Turkiye"], "fifa.worldq.uefa"),
        **dict.fromkeys(["Argentina","Brazil","Colombia","Ecuador","Uruguay","Paraguay"], "fifa.worldq.conmebol"),
        **dict.fromkeys(["Mexico","United States","Canada","Panama","Curacao","Haiti"], "concacaf.wcq"),
        **dict.fromkeys(["Algeria","Morocco","Senegal","Ivory Coast","Egypt","Ghana",
                         "Tunisia","DR Congo","South Africa","Cape Verde"], "caf.wcq"),
        **dict.fromkeys(["Japan","South Korea","Saudi Arabia","Iran","Australia",
                         "Qatar","Iraq","Jordan","Uzbekistan"], "afc.wcq"),
        "New Zealand": "ofc.wcq",
    }

    all_matches = []
    sources = []

    for league_key in ["fifa.friendly", CONF_MAP.get(team_name, ""), "fifa.worldq.uefa"]:
        if not league_key or league_key in sources:
            continue
        url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_key}/teams/{espn_id}/schedule?limit=8"
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code != 200:
                continue
            events = r.json().get('events', [])
            for evt in events:
                status = evt.get('status', {}).get('type', {}).get('description', '')
                if status not in ('Final', 'Full Time', 'FT', 'Finished', 'Completed', ''):
                    continue
                comps = evt.get('competitions', [{}])[0]
                competitors = comps.get('competitors', [])
                if len(competitors) < 2:
                    continue
                home_c = next((c for c in competitors if c.get('homeAway') == 'home'), competitors[0])
                away_c = next((c for c in competitors if c.get('homeAway') == 'away'), competitors[1])
                all_matches.append({
                    "date": evt.get('date', '')[:10],
                    "home": home_c.get('team', {}).get('displayName', '?'),
                    "away": away_c.get('team', {}).get('displayName', '?'),
                    "home_score": _parse_score(home_c.get('score')),
                    "away_score": _parse_score(away_c.get('score')),
                    "home_win": home_c.get('winner', False) if isinstance(home_c.get('winner'), bool) else None,
                    "type": league_key,
                    "_source": f"ESPN:{url}",
                    "_verified": True,
                })
            sources.append(league_key)
            if len(all_matches) >= 5:
                break
        except Exception as e:
            sources.append(f"{league_key}:failed:{e}")

    all_matches.sort(key=lambda x: x['date'], reverse=True)
    return {
        "data": all_matches[:6],
        "_sources": sources,
        "_verified": True,
        "_count": len(all_matches),
    }


def collect_historical(team_name: str) -> dict:
    """从DeepSeek获取历史知识（战术+WC历史）。必须标注为历史来源。"""
    prompt = f"""你是足球历史分析师。请提供{team_name}国家队的以下信息，所有内容必须基于2025年12月之前的已知历史事实，不允许猜测或编造。

1. 教练（截至2026年初）：全名
2. 惯用阵型（近2年）：如4-3-3
3. 进攻风格（2-3句，基于已知事实）
4. 防守弱点（基于已知事实）
5. 世界杯历史（2014/2018/2022各届结果，如未参加写"未参赛"）
6. 世界杯小组赛首轮历史规律（近几届）
7. 大赛逆转/DNA特点（基于历史）

格式（JSON）：
{{
  "coach": "<全名 或 null>",
  "formation": "<如4-3-3 或 null>",
  "attack_style": "<基于事实的描述>",
  "defensive_weakness": "<基于事实的描述>",
  "wc_2022": "<结果>", "wc_2018": "<结果>", "wc_2014": "<结果>",
  "opening_game_pattern": "<近几届首轮规律>",
  "big_game_dna": "<大赛特点>"
}}

如果某项你没有把握，请写null，不要猜测。"""

    try:
        resp = client.messages.create(
            model=config.MODEL,
            max_tokens=600,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text
        import re
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            data = json.loads(m.group())
            # 强制标注所有字段为历史来源
            for k in list(data.keys()):
                if not k.startswith('_'):
                    data[f"_{k}_source"] = "DEEPSEEK_HISTORICAL"
            data["_verified"] = False
            data["_method"] = "DEEPSEEK_HISTORICAL"
            data["_note"] = "AI历史知识，截至2026年初，未经实时验证"
            return data
    except Exception as e:
        pass
    return {"_verified": False, "_method": "DEEPSEEK_HISTORICAL", "_error": "failed"}


# ════════════════════════════════════════════════════
# AGENT 2: 审核
# ════════════════════════════════════════════════════

def review_team_data(raw: dict) -> dict:
    """审核采集数据，标注可信度。"""
    squad = raw.get("squad", {})
    form = raw.get("recent_form", {})
    historical = raw.get("historical", {})

    issues = []

    # 1. 大名单审核
    if not squad.get("_verified"):
        issues.append("SQUAD: 无法从ESPN获取，数据不可信")
    elif squad.get("_count", 0) < 20:
        issues.append(f"SQUAD: 只有{squad['_count']}人，可能不完整")

    # 2. 近期战绩审核
    if not form.get("_verified"):
        issues.append("FORM: 无法获取真实战绩")
    elif form.get("_count", 0) == 0:
        issues.append("FORM: 找不到任何近期比赛记录")

    # 3. 历史数据审核（始终标注为未验证）
    if historical.get("_method") == "DEEPSEEK_HISTORICAL":
        issues.append("HISTORICAL: AI生成，需人工核实关键数据")

    raw["_review"] = {
        "issues": issues,
        "squad_reliable": squad.get("_verified", False) and squad.get("_count", 0) >= 22,
        "form_reliable": form.get("_verified", False) and form.get("_count", 0) >= 3,
        "historical_source": "AI_HISTORICAL",
        "overall_quality": "HIGH" if not issues else ("MEDIUM" if len(issues) == 1 else "LOW"),
        "reviewed_at": datetime.now().isoformat(),
    }
    return raw


# ════════════════════════════════════════════════════
# 主流程
# ════════════════════════════════════════════════════

def build_team_knowledge(team_name: str, espn_id: str) -> dict:
    """完整流程：Agent1采集 → Agent2审核 → 返回可信知识库条目。"""
    print(f"\n  [A1采集] {team_name} (ESPN:{espn_id})")

    # Agent 1: 采集
    squad_data = collect_squad(team_name, espn_id)
    print(f"    大名单: {squad_data['_count']}人 ({'✅' if squad_data['_verified'] else '❌'})")

    form_data = collect_recent_form(team_name, espn_id)
    print(f"    近期战绩: {form_data['_count']}场 来源={form_data['_sources'][:2]}")

    historical_data = collect_historical(team_name)
    coach = historical_data.get("coach", "?")
    formation = historical_data.get("formation", "?")
    print(f"    历史: 教练={coach} 阵型={formation} [AI历史，未验证]")

    # 组装原始数据
    raw = {
        "team": team_name,
        "espn_id": espn_id,
        "squad": squad_data,
        "recent_form": form_data,
        "historical": historical_data,
        "_collected_at": datetime.now().isoformat(),
    }

    # Agent 2: 审核
    reviewed = review_team_data(raw)
    quality = reviewed["_review"]["overall_quality"]
    issues = reviewed["_review"]["issues"]
    print(f"  [A2审核] 质量={quality} 问题={len(issues)}")
    for iss in issues:
        print(f"    ⚠️ {iss}")

    return reviewed


def main():
    output_file = Path("data/team_knowledge_v2.json")
    output_file.parent.mkdir(parents=True, exist_ok=True)

    # 加载已有数据（断点续跑）
    existing = {}
    if output_file.exists():
        existing = json.loads(output_file.read_text(encoding='utf-8'))
        print(f"[续跑] 已有 {len(existing)} 支队")

    # 获取ESPN ID映射
    print("获取ESPN team_id映射...")
    espn_ids = get_espn_team_ids()
    no_id = [t for t, i in espn_ids.items() if i is None]
    if no_id:
        print(f"⚠️ 以下队没有ESPN ID: {no_id}")
    print(f"成功映射: {len(espn_ids) - len(no_id)}/48 支队\n")

    # 筛选需要处理的队
    todo = [t for t in espn_ids if t not in existing]
    print(f"需要处理: {len(todo)} 支队")

    errors = []
    for i, team_name in enumerate(todo, 1):
        espn_id = espn_ids.get(team_name)
        print(f"\n[{i}/{len(todo)}] {team_name}")
        try:
            result = build_team_knowledge(team_name, espn_id)
            existing[team_name] = result
            output_file.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8'
            )
        except Exception as e:
            print(f"  [FAIL] {e}")
            errors.append((team_name, str(e)))
        time.sleep(0.5)

    print(f"\n{'='*60}")
    print(f"完成: {len(todo)-len(errors)}/{len(todo)}")
    if errors:
        print(f"失败: {[t for t,_ in errors]}")
    print(f"已保存: {output_file}")


if __name__ == '__main__':
    main()
