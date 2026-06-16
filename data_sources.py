"""
data_sources.py — 可靠数据来源定义 + 测试

所有数据来源必须在此注册。Agent 1 只能使用这里定义的来源。
Agent 2 审核时会验证来源是否在此列表中。

来源类型：
  API       — 直接 HTTP 请求，结构化 JSON，最可靠
  BROWSER   — 需要浏览器渲染，可靠但慢
  HISTORICAL — DeepSeek/AI 历史知识，必须标注，不可用于球员名单/赛果

每个来源字段说明：
  type:        API | BROWSER | HISTORICAL
  base_url:    基础URL模板
  provides:    能提供什么数据
  reliability: HIGH | MEDIUM | LOW
  note:        使用说明
"""

SOURCES = {

    # ═══════════════════════════════════════
    # A: ESPN API（实时，最可靠）
    # ═══════════════════════════════════════
    "ESPN_TEAMS": {
        "type": "API",
        "base_url": "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams",
        "provides": ["team_id_mapping", "team_list"],
        "reliability": "HIGH",
        "note": "获取所有48支参赛队的ESPN team_id，用于后续查询",
    },

    "ESPN_ROSTER": {
        "type": "API",
        "base_url": "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/teams/{espn_id}/roster",
        "provides": ["squad_26", "player_name", "player_position", "player_age", "jersey_number", "injury_status"],
        "reliability": "HIGH",
        "note": "官方WC注册名单，26人，含位置/年龄/伤情",
    },

    "ESPN_SCOREBOARD": {
        "type": "API",
        "base_url": "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates={date}",
        "provides": ["wc_match_results", "wc_match_odds", "match_status"],
        "reliability": "HIGH",
        "note": "本届WC比赛结果和赔率，date格式YYYYMMDD",
    },

    "ESPN_MATCH_SUMMARY": {
        "type": "API",
        "base_url": "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/summary?event={event_id}",
        "provides": ["match_odds", "match_lineups", "match_injuries", "match_stats"],
        "reliability": "HIGH",
        "note": "单场比赛详情，赔率/首发/伤停",
    },

    "ESPN_WCQ_UEFA": {
        "type": "API",
        "base_url": "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.worldq.uefa/teams/{espn_id}/schedule",
        "provides": ["recent_form_2025_wc_qualifier"],
        "reliability": "HIGH",
        "note": "欧洲区WCQ2025战绩，对欧洲队有效",
    },

    "ESPN_WCQ_CONCACAF": {
        "type": "API",
        "base_url": "https://site.api.espn.com/apis/site/v2/sports/soccer/concacaf.wcq/teams/{espn_id}/schedule",
        "provides": ["recent_form_2025_wc_qualifier"],
        "reliability": "HIGH",
        "note": "北中美洲WCQ战绩",
    },

    "ESPN_WCQ_CONMEBOL": {
        "type": "API",
        "base_url": "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.worldq.conmebol/teams/{espn_id}/schedule",
        "provides": ["recent_form_2025_wc_qualifier"],
        "reliability": "HIGH",
        "note": "南美WCQ战绩",
    },

    "ESPN_WCQ_CAF": {
        "type": "API",
        "base_url": "https://site.api.espn.com/apis/site/v2/sports/soccer/caf.wcq/teams/{espn_id}/schedule",
        "provides": ["recent_form_2025_wc_qualifier"],
        "reliability": "HIGH",
        "note": "非洲WCQ战绩",
    },

    "ESPN_WCQ_AFC": {
        "type": "API",
        "base_url": "https://site.api.espn.com/apis/site/v2/sports/soccer/afc.wcq/teams/{espn_id}/schedule",
        "provides": ["recent_form_2025_wc_qualifier"],
        "reliability": "HIGH",
        "note": "亚洲WCQ战绩",
    },

    # ═══════════════════════════════════════
    # B: Sofascore 浏览器（实时，需浏览器）
    # ═══════════════════════════════════════
    "SOFASCORE_TEAM": {
        "type": "BROWSER",
        "base_url": "https://www.sofascore.com/football/team/{slug}/{sofascore_id}",
        "provides": ["squad_with_clubs", "recent_form_all_competitions", "injury_list", "coach_name"],
        "reliability": "HIGH",
        "note": "最全面的实时数据：球员俱乐部、近期所有比赛、伤情列表",
    },

    "SOFASCORE_MATCH": {
        "type": "BROWSER",
        "base_url": "https://www.sofascore.com/football/match/{slug}#{id}",
        "provides": ["match_lineups", "match_odds", "match_result"],
        "reliability": "HIGH",
        "note": "单场比赛详情",
    },

    # ═══════════════════════════════════════
    # C: 历史/AI知识（必须标注，不得用于名单/赛果）
    # ═══════════════════════════════════════
    "DEEPSEEK_HISTORICAL": {
        "type": "HISTORICAL",
        "base_url": None,
        "provides": ["wc_history_2014_2022", "tactical_style_general", "coach_philosophy", "team_dna_patterns"],
        "reliability": "MEDIUM",
        "note": "AI历史知识库，截至2026年初。只能用于历史记录和战术风格描述。禁止用于球员名单、近期赛果",
        "forbidden_for": ["squad_26", "recent_form", "injuries", "confirmed_lineup"],
    },
}


# ═══════════════════════════════════════
# ESPN team_id 映射（48支WC2026参赛队）
# ═══════════════════════════════════════
# 运行 fetch_espn_team_ids() 自动填充
ESPN_TEAM_IDS = {}

# WCQ竞赛联赛与洲际区的对应（用于查近期战绩）
CONFEDERATION_WCQ = {
    # 欧洲
    "Albania": "fifa.worldq.uefa", "Austria": "fifa.worldq.uefa", "Belgium": "fifa.worldq.uefa",
    "Bosnia and Herzegovina": "fifa.worldq.uefa", "Croatia": "fifa.worldq.uefa",
    "Czechia": "fifa.worldq.uefa", "England": "fifa.worldq.uefa", "France": "fifa.worldq.uefa",
    "Germany": "fifa.worldq.uefa", "Netherlands": "fifa.worldq.uefa", "Norway": "fifa.worldq.uefa",
    "Portugal": "fifa.worldq.uefa", "Scotland": "fifa.worldq.uefa", "Spain": "fifa.worldq.uefa",
    "Sweden": "fifa.worldq.uefa", "Switzerland": "fifa.worldq.uefa", "Turkiye": "fifa.worldq.uefa",
    # 南美
    "Argentina": "fifa.worldq.conmebol", "Brazil": "fifa.worldq.conmebol",
    "Colombia": "fifa.worldq.conmebol", "Ecuador": "fifa.worldq.conmebol",
    "Paraguay": "fifa.worldq.conmebol", "Uruguay": "fifa.worldq.conmebol",
    # 北中美
    "Canada": "concacaf.wcq", "Mexico": "concacaf.wcq", "United States": "concacaf.wcq",
    "Panama": "concacaf.wcq",
    # 非洲
    "Algeria": "caf.wcq", "Ivory Coast": "caf.wcq", "DR Congo": "caf.wcq",
    "Egypt": "caf.wcq", "Ghana": "caf.wcq", "Morocco": "caf.wcq",
    "Senegal": "caf.wcq", "South Africa": "caf.wcq", "Tunisia": "caf.wcq",
    # 亚洲
    "Australia": "afc.wcq", "Iran": "afc.wcq", "Iraq": "afc.wcq",
    "Japan": "afc.wcq", "Jordan": "afc.wcq", "Qatar": "afc.wcq",
    "Saudi Arabia": "afc.wcq", "South Korea": "afc.wcq", "Uzbekistan": "afc.wcq",
    # 其他/加勒比
    "Cape Verde": "caf.wcq", "Curacao": "concacaf.wcq", "Haiti": "concacaf.wcq",
    "New Zealand": "ofc.wcq",
    "Bosnia and Herzegovina": "fifa.worldq.uefa",
}


import requests
import json

HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}


def fetch_espn_team_ids() -> dict:
    """从ESPN API获取所有48支队的ESPN team_id。"""
    r = requests.get(SOURCES["ESPN_TEAMS"]["base_url"], headers=HEADERS, timeout=10)
    teams = r.json().get('sports', [{}])[0].get('leagues', [{}])[0].get('teams', [])
    return {t['team']['displayName']: t['team']['id'] for t in teams}


def fetch_espn_roster(team_name: str, espn_id: str) -> dict:
    """从ESPN拿官方WC大名单。返回带来源标注的数据。"""
    url = SOURCES["ESPN_ROSTER"]["base_url"].format(espn_id=espn_id)
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        athletes = r.json().get('athletes', [])
        players = []
        for a in athletes:
            pos_raw = a.get('position', {})
            pos = pos_raw.get('abbreviation', '?') if isinstance(pos_raw, dict) else '?'
            players.append({
                "name": a.get('displayName', '?'),
                "pos": pos,
                "age": a.get('age'),
                "jersey": a.get('jersey'),
                "_source": f"ESPN_ROSTER:{url}",
                "_verified": True,
            })
        return {
            "squad_26": players,
            "_source": f"ESPN_ROSTER:{url}",
            "_count": len(players),
        }
    except Exception as e:
        return {"squad_26": [], "_source": "ESPN_ROSTER:failed", "_error": str(e), "_verified": False}


def fetch_espn_recent_form(team_name: str, espn_id: str) -> dict:
    """从ESPN拿WCQ+WC近期战绩（含比赛结果）。"""
    league = CONFEDERATION_WCQ.get(team_name, "fifa.worldq.uefa")
    results = []
    sources_used = []

    # 先查本届WC（从scoreboard批量查）
    import sys
    sys.path.insert(0, '.')

    # 查WCQ
    for league_try in [league, "fifa.worldq.uefa"]:
        url = SOURCES.get(f"ESPN_WCQ_{league_try.upper().replace('.','_').replace('FIFA_WORLDQ_','')}", {}).get("base_url")
        if not url:
            # 直接构建URL
            url = f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_try}/teams/{espn_id}/schedule"

        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                events = r.json().get('events', [])
                for evt in events[-8:]:  # 最近8场
                    comps = evt.get('competitions', [{}])[0]
                    competitors = comps.get('competitors', [])
                    if len(competitors) < 2: continue
                    home = next((c for c in competitors if c.get('homeAway') == 'home'), competitors[0])
                    away = next((c for c in competitors if c.get('homeAway') == 'away'), competitors[1])
                    status = evt.get('status', {}).get('type', {}).get('description', '')
                    results.append({
                        "date": evt.get('date', '')[:10],
                        "home": home.get('team', {}).get('displayName', '?'),
                        "away": away.get('team', {}).get('displayName', '?'),
                        "home_score": home.get('score', '?'),
                        "away_score": away.get('score', '?'),
                        "status": status,
                        "_source": f"ESPN:{url}",
                        "_verified": True,
                    })
                sources_used.append(f"ESPN:{url}({len(events)}场)")
            if results: break
        except Exception as e:
            sources_used.append(f"ESPN:{league_try}:failed:{e}")

    return {
        "recent_form_wcq": sorted(results, key=lambda x: x['date'], reverse=True)[:5],
        "_sources": sources_used,
    }


def test_all_sources():
    """测试所有API来源是否可用。"""
    print("=== 数据来源可用性测试 ===\n")

    # 1. ESPN Teams
    try:
        ids = fetch_espn_team_ids()
        print(f"✅ ESPN_TEAMS: {len(ids)} 支队")
        print(f"   样本: France={ids.get('France')}, Spain={ids.get('Spain')}, Japan={ids.get('Japan')}")
    except Exception as e:
        print(f"❌ ESPN_TEAMS: {e}")

    # 2. ESPN Roster
    try:
        ids = fetch_espn_team_ids()
        roster = fetch_espn_roster("France", ids["France"])
        print(f"\n✅ ESPN_ROSTER: France {roster['_count']}人")
        print(f"   首3人: {[p['name'] for p in roster['squad_26'][:3]]}")
    except Exception as e:
        print(f"\n❌ ESPN_ROSTER: {e}")

    # 3. ESPN Scoreboard
    try:
        r = requests.get("https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=20260616", headers=HEADERS, timeout=10)
        events = r.json().get('events', [])
        print(f"\n✅ ESPN_SCOREBOARD: {len(events)} 场今日比赛")
    except Exception as e:
        print(f"\n❌ ESPN_SCOREBOARD: {e}")

    # 4. ESPN WCQ form
    try:
        ids = fetch_espn_team_ids()
        form = fetch_espn_recent_form("France", ids["France"])
        print(f"\n✅ ESPN_WCQ: France {len(form['recent_form_wcq'])} 场近期WCQ")
        for m in form['recent_form_wcq'][:2]:
            print(f"   {m['date']} {m['home']} {m['home_score']}-{m['away_score']} {m['away']}")
    except Exception as e:
        print(f"\n❌ ESPN_WCQ: {e}")

    # 5. Sofascore（需浏览器，这里只验证URL格式）
    print(f"\n⚠️  SOFASCORE_BROWSER: 需要浏览器（mcp__browser-use），URL格式：")
    print(f"   https://www.sofascore.com/football/team/france/4481")
    print(f"   提供：球员俱乐部、近期全部比赛（含热身赛）、伤情")

    print("\n=== 测试完成 ===")


if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    test_all_sources()
