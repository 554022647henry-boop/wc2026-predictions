"""
Agent 1 — 信息搜集（重构版）

数据来源（已实测可用，不走Bing）：
  1. ESPN API    — 赔率 / 首发阵容 / 伤停 / 本届WC已完赛结果（结构化JSON，最可靠）
  2. WhoScored   — 球员质量数据 / 当前赛程 / 首发阵容（实时验证）
  3. CBS Sports  — WC赛事报道（各队表现、赛前分析）

DeepSeek 知识补充（不依赖实时抓取）：
  - 赛前5场竞赛成绩（训练数据中有）
  - 历史战术风格、大赛DNA

7个维度目标：
  1.实力基础   → ESPN赔率隐含 + WhoScored球员评分
  2.近期状态   → CBS报道 + ESPN本届结果 + DeepSeek历史知识
  3.战术对位   → WhoScored统计 + DeepSeek战术知识
  4.大赛DNA    → DeepSeek历史知识 + CBS背景文章
  5.赔率信号   → ESPN API DraftKings赔率（最核心！）
  6.本届动能   → ESPN WC Scoreboard（本届已打比赛）
  7.动机情境   → CBS文章 + DeepSeek分析
"""
import json
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

client = config.make_client()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# ─── 已确认可访问的域名白名单 ──────────────────────────────────────
ACCESSIBLE_DOMAINS = [
    "espn.com", "cbssports.com", "sportingnews.com",
    "whoscored.com", "goal.com", "skysports.com",
    "si.com", "90min.com",
]


# ═══════════════════════════════════════════════════════
# 来源1: ESPN API（结构化JSON，最优先）
# ═══════════════════════════════════════════════════════

def espn_fetch_event_detail(event_id: str) -> dict:
    """获取单场比赛详情：赔率、阵容、伤停、统计。"""
    url = config.ESPN_API["match_summary"].format(event_id=event_id)
    try:
        r = requests.get(url, headers=HEADERS, timeout=12)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        return {"error": str(e)}


def espn_find_event_id(team_a: str, team_b: str, match_date: str) -> Optional[str]:
    """从WC赛程中找到比赛的event_id。"""
    base_dt = datetime.strptime(match_date, "%Y-%m-%d")
    for delta in range(-1, 3):
        date_key = (base_dt + timedelta(days=delta)).strftime("%Y%m%d")
        try:
            r = requests.get(
                config.ESPN_API["scoreboard"].format(date=date_key),
                headers=HEADERS, timeout=10
            )
            for evt in r.json().get("events", []):
                name = evt.get("name", "").lower()
                ta_words = [w.lower() for w in team_a.split() if len(w) > 3]
                tb_words = [w.lower() for w in team_b.split() if len(w) > 3]
                # 去除特殊字符做模糊匹配（处理 Curaçao/Türkiye 等）
                import unicodedata
                def norm(s): return unicodedata.normalize('NFD', s.lower()).encode('ascii','ignore').decode()
                name_norm = norm(name)
                if any(norm(w) in name_norm for w in ta_words + [team_a]) and \
                   any(norm(w) in name_norm for w in tb_words + [team_b]):
                    return evt.get("id")
        except Exception:
            continue
    return None


def espn_get_wc_results(team_a: str, team_b: str) -> list[dict]:
    """获取两队在本届世界杯中的已完赛结果。"""
    results = []
    try:
        r = requests.get(
            f"{config.ESPN_API['scoreboard'].replace('?dates={date}', '')}?dates=20260601-20260714",
            headers=HEADERS, timeout=10
        )
        # 用日期范围格式
        r2 = requests.get(
            "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard?dates=20260601-20260714",
            headers=HEADERS, timeout=10
        )
        events = r2.json().get("events", [])
        for evt in events:
            status = evt.get("status", {}).get("type", {}).get("description", "")
            if status not in ("Full Time", "Final", "FT"):
                continue
            comps = evt.get("competitions", [{}])[0]
            competitors = comps.get("competitors", [])
            teams_in_match = [c.get("team", {}).get("displayName", "") for c in competitors]
            if team_a in teams_in_match or team_b in teams_in_match:
                scores = []
                for c in competitors:
                    t = c.get("team", {}).get("displayName", "")
                    s = c.get("score", "?")
                    w = " ✓" if c.get("winner") else ""
                    scores.append(f"{t} {s}{w}")
                results.append({
                    "match": " vs ".join(t.get("team", {}).get("displayName", "") for t in competitors),
                    "score": " - ".join(scores),
                    "date": evt.get("date", "")[:10],
                })
    except Exception:
        pass
    return results


def espn_build_prematch_data(team_a: str, team_b: str, match_date: str) -> dict:
    """
    综合ESPN API：赔率、阵容、伤停、本届WC结果。
    """
    data = {
        "event_id": None,
        "odds": {},
        "lineups": {},
        "injuries": [],
        "wc_results": [],
        "source": "ESPN API",
    }

    # 找 event_id
    event_id = espn_find_event_id(team_a, team_b, match_date)
    if event_id:
        data["event_id"] = event_id
        detail = espn_fetch_event_detail(event_id)

        # 赔率
        odds_list = detail.get("odds", [])
        if odds_list:
            o = odds_list[0]
            prov = o.get("provider", {}).get("name", "")
            ho = o.get("homeTeamOdds", {})
            ao = o.get("awayTeamOdds", {})
            draw_raw = o.get("drawOdds", {})
            draw_ml = draw_raw.get("moneyLine") if isinstance(draw_raw, dict) else draw_raw
            data["odds"] = {
                "provider": prov,
                "home_team": team_a,
                "home_moneyline": ho.get("moneyLine"),
                "away_team": team_b,
                "away_moneyline": ao.get("moneyLine"),
                "draw_moneyline": draw_ml,
                "note": f"{prov}: {team_a} {ho.get('moneyLine','?')} / Draw {draw_ml} / {team_b} {ao.get('moneyLine','?')}",
            }

        # 阵容（开球前1小时公布）
        for roster in detail.get("rosters", []):
            tname = roster.get("team", {}).get("displayName", "")
            starters = [a for a in roster.get("athletes", []) if a.get("starter")]
            if starters:
                names = [
                    a.get("athlete", {}).get("displayName", "") or a.get("displayName", "")
                    for a in starters[:11]
                ]
                data["lineups"][tname] = names

        # 伤停
        for inj in detail.get("injuries", []):
            p = inj.get("athlete", {}).get("displayName", "")
            t = inj.get("team", {}).get("displayName", "")
            s = inj.get("type", {}).get("description", "")
            if p and t:
                data["injuries"].append(f"{t} | {p}: {s}")

    # 本届WC结果
    data["wc_results"] = espn_get_wc_results(team_a, team_b)

    return data


# ═══════════════════════════════════════════════════════
# 来源2: WhoScored（球员质量 + 当前赛程 + 阵容）
# ═══════════════════════════════════════════════════════

def whoscored_fetch(team_a: str, team_b: str) -> dict:
    """
    从WhoScored主页提取：当前WC赛程、阵容、球员质量数据。
    """
    data = {"fixture_found": False, "lineup_confirmed": False,
            "top_players": [], "raw_text": "", "source": "WhoScored"}
    try:
        r = requests.get("https://www.whoscored.com", headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return data
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(" ", strip=True)
        data["raw_text"] = text[:3000]

        # 检查比赛是否在WhoScored赛程中
        if team_a in text and team_b in text:
            data["fixture_found"] = True

        # 检查是否有确认首发
        if "Confirmed Lineups" in text or "Confirmed" in text:
            data["lineup_confirmed"] = True
            # 尝试找 team_a 或 team_b 的阵容
            for t in [team_a, team_b]:
                idx = text.find(t)
                if idx >= 0:
                    snippet = text[idx:idx+500]
                    if "Confirmed" in snippet:
                        data[f"lineup_{t.lower().replace(' ','_')}"] = snippet[:300]

        # 提取顶级球员数据（相关球员）
        team_keywords = [team_a.lower(), team_b.lower()]
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        for line in lines:
            if any(k in line.lower() for k in team_keywords) and len(line) < 200:
                data["top_players"].append(line)

    except Exception as e:
        data["error"] = str(e)
    return data


# ═══════════════════════════════════════════════════════
# 来源3: CBS Sports（WC赛事报道 + 分析）
# ═══════════════════════════════════════════════════════

def cbssports_fetch(team_a: str, team_b: str) -> dict:
    """
    从CBS Sports WC板块提取：赛事报道、球队分析、赛前预测文章。
    """
    data = {"articles": [], "relevant_content": "", "source": "CBS Sports"}
    try:
        r = requests.get("https://www.cbssports.com/soccer/world-cup/", headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return data
        soup = BeautifulSoup(r.text, "html.parser")

        # 找相关文章链接
        for a in soup.find_all("a", href=True):
            title = a.get_text(strip=True)
            href = a.get("href", "")
            if len(title) < 15 or len(title) > 200:
                continue
            is_relevant = any(
                k.lower() in title.lower()
                for k in [team_a, team_b, "World Cup", "Germany", "France", "Brazil",
                          "England", "Argentina", "preview", "analysis", "score", "result"]
            )
            if is_relevant:
                url = href if href.startswith("http") else f"https://www.cbssports.com{href}"
                data["articles"].append({"title": title, "url": url})

        # 抓前2篇相关文章的内容
        fetched = 0
        for art in data["articles"][:5]:
            if fetched >= 2:
                break
            try:
                r2 = requests.get(art["url"], headers=HEADERS, timeout=8)
                if r2.status_code == 200 and len(r2.text) > 1000:
                    soup2 = BeautifulSoup(r2.text, "html.parser")
                    text2 = soup2.get_text(" ", strip=True)
                    # 找和两队相关的段落
                    for team in [team_a, team_b]:
                        idx = text2.find(team)
                        if idx >= 0:
                            snippet = text2[max(0, idx-100):idx+600]
                            data["relevant_content"] += f"\n[{art['title'][:60]}]\n{snippet}\n"
                            fetched += 1
                            break
            except Exception:
                continue
            time.sleep(0.3)

    except Exception as e:
        data["error"] = str(e)
    return data


# ═══════════════════════════════════════════════════════
# 整合：完整赛前信息包
# ═══════════════════════════════════════════════════════

def collect_prematch_info(match_info: dict, round_label: str,
                          supplement_queries: list[str] | None = None) -> str:
    """
    整合3个来源的数据，用 DeepSeek 补充历史知识，
    返回结构化赛前信息文本供 Agent2 审阅。
    """
    team_a = match_info["team_a"]
    team_b = match_info["team_b"]
    match_date = match_info.get("date", "")
    stage = match_info.get("stage", "")
    venue = match_info.get("venue", "")

    print(f"  [ESPN API] 获取赔率/阵容/伤停...")
    espn = espn_build_prematch_data(team_a, team_b, match_date)

    print(f"  [WhoScored] 获取球员质量/赛程...")
    ws = whoscored_fetch(team_a, team_b)

    print(f"  [CBS Sports] 获取WC赛事报道...")
    cbs = cbssports_fetch(team_a, team_b)

    # ── 从 v2 知识库注入真实数据 ────────────────────────────────
    kb_v2_text_a = ""
    kb_v2_text_b = ""
    try:
        kb_v2_file = Path(config.BASE_DIR) / "data" / "team_knowledge_v2.json"
        if kb_v2_file.exists():
            kb_v2 = json.loads(kb_v2_file.read_text(encoding="utf-8"))
            for team, out_var in [(team_a, "a"), (team_b, "b")]:
                t = kb_v2.get(team, {})
                sq = t.get("squad", {}).get("data", [])
                form = t.get("recent_form", {}).get("data", [])
                hist = t.get("historical", {})
                lines = []
                if sq:
                    lines.append(f"【{team} 官方注册大名单（ESPN✅ 真实可信）】")
                    pos_groups = {}
                    for p in sq:
                        pos = p.get("pos", "?")
                        pos_groups.setdefault(pos, []).append(p["name"])
                    for pos, names in pos_groups.items():
                        lines.append(f"  {pos}: {', '.join(names)}")
                if form:
                    lines.append(f"【{team} 近期战绩（ESPN✅ 真实比赛结果）】")
                    for m in form[:6]:
                        h, a = m.get("home","?"), m.get("away","?")
                        hs, as_ = m.get("home_score","?"), m.get("away_score","?")
                        lines.append(f"  {m.get('date','?')} {h} {hs}-{as_} {a} [{m.get('type','?')}]")
                if hist.get("formation"):
                    lines.append(f"【{team} 战术（AI历史⚠️ 仅供参考）】")
                    lines.append(f"  阵型: {hist.get('formation','?')} | 教练: {hist.get('coach','?')}")
                    if hist.get("attack_style"):
                        lines.append(f"  进攻: {hist['attack_style']}")
                    if hist.get("defensive_weakness"):
                        lines.append(f"  防守弱点: {hist['defensive_weakness']}")
                if out_var == "a":
                    kb_v2_text_a = "\n".join(lines)
                else:
                    kb_v2_text_b = "\n".join(lines)
    except Exception as e:
        print(f"  [KB v2] 加载失败: {e}")

    # ── 用 DeepSeek 补充【仅限历史/DNA，禁止生成球员名或近期战绩】────
    print(f"  [DeepSeek] 补充历史DNA（WC历史/交锋记录）...")
    knowledge_prompt = f"""为以下世界杯比赛提供历史背景信息。

比赛：{team_a} vs {team_b}
阶段：{stage}

【严格禁止】：
- 禁止生成球员名字列表（大名单已从ESPN官方获取，你的名单可能过时）
- 禁止生成近期比赛结果（近期战绩已从ESPN真实数据获取，你的结果可能是错的）
- 禁止提及格列兹曼、卡马文加、吉鲁、洛里斯等已退役/未入选球员

【只需提供以下历史信息】：
1. 两队历史交锋记录（近10年，最多3场，只写你有把握的）
2. {team_a} 世界杯历史表现（2014/2018/2022三届结果）
3. {team_b} 世界杯历史表现（2014/2018/2022三届结果）
4. 哪支队在小组赛首战表现更稳定（历史规律）
5. 大赛DNA：哪支队在逆境中表现更好

格式：简洁直接，不要废话。如果某项你不确定，直接写"不确定"，不要猜测或编造。"""

    try:
        resp = client.messages.create(
            model=config.MODEL,
            max_tokens=800,
            messages=[{"role": "user", "content": knowledge_prompt}]
        )
        historical_knowledge = resp.content[0].text
    except Exception as e:
        historical_knowledge = f"历史知识获取失败: {e}"

    # ── 组装最终输出 ────────────────────────────────────────────
    sections = []

    sections.append("=" * 60)
    sections.append(f"赛前信息报告: {team_a} vs {team_b}")
    sections.append(f"轮次: {round_label} | 日期: {match_date} | 场地: {venue}")
    sections.append("=" * 60)

    # ESPN API
    sections.append("\n【来源1: ESPN API - 实时数据】")
    if espn.get("odds") and espn["odds"].get("note"):
        sections.append(f"赔率 {espn['odds']['note']}")
    else:
        sections.append("赔率: 暂未获取")

    if espn.get("lineups"):
        sections.append("确认首发阵容:")
        for team, players in espn["lineups"].items():
            sections.append(f"  {team}: {', '.join(players[:11])}")
    else:
        sections.append("首发阵容: 尚未公布（开球前1小时公布）")

    if espn.get("injuries"):
        sections.append("伤停/停赛:")
        for inj in espn["injuries"]:
            sections.append(f"  {inj}")
    else:
        sections.append("伤停: ESPN无伤停记录")

    if espn.get("wc_results"):
        sections.append("本届WC相关队伍已完赛:")
        for r_info in espn["wc_results"][:6]:
            sections.append(f"  {r_info['date']} {r_info['score']}")
    else:
        sections.append("本届WC: 两队尚未在本届有完赛记录")

    # WhoScored
    sections.append("\n【来源2: WhoScored - 球员质量/赛程】")
    sections.append(f"赛程确认: {'已在WhoScored赛程中找到' if ws.get('fixture_found') else '未找到'}")
    sections.append(f"首发确认: {'已确认首发' if ws.get('lineup_confirmed') else '首发未确认'}")
    if ws.get("raw_text"):
        # 提取和两队相关的文本段落
        text = ws["raw_text"]
        for team in [team_a, team_b]:
            idx = text.find(team)
            if idx >= 0:
                snippet = text[max(0,idx-50):idx+300]
                sections.append(f"WhoScored相关内容[{team}]: {snippet[:200]}")

    # CBS Sports
    sections.append("\n【来源3: CBS Sports - WC报道】")
    if cbs.get("articles"):
        sections.append(f"找到 {len(cbs['articles'])} 篇相关文章:")
        for art in cbs["articles"][:4]:
            sections.append(f"  - {art['title'][:80]}")
    if cbs.get("relevant_content"):
        sections.append("文章内容摘录:")
        sections.append(cbs["relevant_content"][:1000])
    else:
        sections.append("CBS报道: 暂无直接相关赛前文章")

    # ── 来源4a: KB v2 官方真实数据（ESPN，最可信）────────────────
    sections.append("\n【来源4a: ESPN官方知识库 - 大名单+近期战绩（真实数据✅）】")
    sections.append("⚠️ 以下大名单和战绩来自ESPN官方API，是本届真实注册球员和真实比赛结果，请以此为准，忽略其他来源中的球员名字或战绩。")
    if kb_v2_text_a:
        sections.append(kb_v2_text_a)
    else:
        sections.append(f"{team_a}: KB v2数据未找到")
    if kb_v2_text_b:
        sections.append(kb_v2_text_b)
    else:
        sections.append(f"{team_b}: KB v2数据未找到")

    # ── 来源4b: DeepSeek历史DNA（仅WC历史，不含球员名/近期战绩）────
    sections.append("\n【来源4b: AI历史DNA（仅WC历史和交锋记录，⚠️禁止用于球员名或近期战绩）】")
    sections.append(historical_knowledge)

    return "\n".join(sections)


# ═══════════════════════════════════════════════════════
# 主函数：执行搜集并保存
# ═══════════════════════════════════════════════════════

def run_collection(
    match_info: dict,
    round_key: str,
    round_label: str,
    supplement_queries: list[str] | None = None,
    supp_index: int | None = None,
) -> str:
    """执行完整搜集，保存原始文件，返回文件路径。"""
    match_id = match_info["match_id"]
    team_a = match_info["team_a"]
    team_b = match_info["team_b"]

    if supp_index:
        print(f"\n[Agent1] 补充搜集 #{supp_index}: {team_a} vs {team_b} | {round_label}")
        # 补充轮：用 DeepSeek 针对缺失信息补充
        supplement_prompt = "\n".join(supplement_queries or [])
        try:
            resp = client.messages.create(
                model=config.MODEL,
                max_tokens=800,
                messages=[{"role": "user", "content": f"""针对以下信息缺口，请提供补充信息：

比赛：{team_a} vs {team_b}

缺失信息：
{supplement_prompt}

请尽量提供具体数据，不确定的内容请说明。"""}]
            )
            raw_content = f"【补充信息 第{supp_index}轮】\n{resp.content[0].text}"
        except Exception as e:
            raw_content = f"补充搜集失败: {e}"
    else:
        print(f"\n[Agent1] 开始搜集: {team_a} vs {team_b} | {round_label}")
        raw_content = collect_prematch_info(match_info, round_label)

    # 保存
    filename = f"{round_key}_supp{supp_index}_raw.json" if supp_index else f"{round_key}_raw.json"
    save_dir = Path(config.COLLECTED_DIR) / match_id
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / filename

    payload = {
        "match_id": match_id,
        "round": round_key,
        "round_label": round_label,
        "supplement_index": supp_index,
        "timestamp": datetime.now().isoformat(),
        "team_a": team_a,
        "team_b": team_b,
        "raw_content": raw_content,
    }
    save_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Agent1] 已保存: {save_path.name}")
    return str(save_path)
