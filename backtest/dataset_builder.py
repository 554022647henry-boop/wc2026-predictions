"""
数据集构建 Agent
职责：为每场历史比赛搜集"赛前"信息（不含比赛结果），
      模拟预测系统在比赛开始前能获取到的信息。
"""
import json
import sys
import time
from pathlib import Path

import anthropic
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

client = config.make_client()

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

DATASET_BUILDER_SYSTEM = """你是一个专门为回测系统构建历史赛前数据集的Agent。

你的任务是：为指定的历史世界杯比赛，重建"赛前"状态——即如果你是在比赛开球前收集信息，你会知道什么。

【严格禁止】
- 不得提及这场比赛的实际比分或结果
- 不得透露谁赢了这场比赛
- 不得使用任何"赛后"视角的描述（例如："该球队在此役后..."）

【应当提供的信息】
1. 两队的FIFA世界排名（比赛时的排名）
2. 两队进入世界杯前/本届赛事前的近期状态（最近5场竞赛场结果）
3. 已知的伤停/停赛球员
4. 两队的战术风格和主要打法
5. 关键球员信息（当时状态，非赛后评价）
6. 历史交锋记录
7. 赛前主流媒体的分析和预测倾向
8. 当时的赔率（如能找到）
9. 赛事背景（阶段重要性、双方晋级压力等）

你将使用搜索结果来补充信息。搜索时请重点寻找：
- "预测"类文章（match preview, prediction, preview）
- 赛前分析（pre-match analysis）
- 两队在比赛前的状态报道

输出格式：结构化JSON，字段见示例。"""


def bing_search(query: str, num: int = 3) -> list[dict]:
    url = f"https://www.bing.com/search?q={requests.utils.quote(query)}&count={num}"
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for li in soup.select("li.b_algo")[:num]:
            h = li.select_one("h2 a")
            p = li.select_one("p")
            if h:
                results.append({
                    "title": h.get_text(strip=True),
                    "url": h.get("href", ""),
                    "snippet": p.get_text(strip=True) if p else ""
                })
        return results
    except Exception:
        return []


def fetch_text(url: str, max_chars: int = 3000) -> str:
    try:
        r = requests.get(url, headers=HEADERS, timeout=8)
        soup = BeautifulSoup(r.text, "html.parser")
        for t in soup(["script", "style", "nav", "footer"]):
            t.decompose()
        return soup.get_text(" ", strip=True)[:max_chars]
    except Exception:
        return ""


def build_prematch_context(match: dict) -> dict:
    """
    为一场历史比赛构建赛前上下文。
    搜索策略：专找preview/预测类文章，避免结果报道。
    """
    team_a = match["team_a"]
    team_b = match["team_b"]
    year = match["date"][:4]
    stage = match["stage"]
    date = match["date"]

    stage_label = {
        "group_stage": "group stage",
        "round_of_16": "round of 16",
        "quarterfinal": "quarter-final",
        "semifinal": "semi-final",
        "final": "final"
    }.get(stage, stage)

    print(f"  搜索赛前信息: {team_a} vs {team_b} ({year} WC {stage_label})")

    # 多角度搜索，专找赛前分析
    queries = [
        f"{team_a} {team_b} {year} World Cup {stage_label} preview prediction",
        f"{team_a} vs {team_b} {year} FIFA World Cup team news lineup",
        f"{team_a} {year} World Cup squad injuries form",
        f"{team_b} {year} World Cup squad injuries form",
        f"{team_a} {team_b} head to head history",
    ]

    raw_snippets = []
    for q in queries:
        results = bing_search(q, num=2)
        for r in results:
            # 过滤掉明显是赛后报道的标题
            title_lower = r["title"].lower()
            if any(w in title_lower for w in ["result", "highlights", "recap", "report", "reaction", "review"]):
                continue
            raw_snippets.append(f"[{r['title']}]\n{r['snippet']}")
        time.sleep(0.3)

    search_text = "\n\n".join(raw_snippets[:10])

    # 用 Claude 整理成结构化赛前信息
    prompt = f"""请根据以下搜索摘要，为这场比赛重建赛前信息。

比赛：{team_a} vs {team_b}
赛事：{year} FIFA 世界杯 {stage_label}
时间：{date}

搜索到的内容：
{search_text}

请以JSON格式输出赛前信息，格式如下：
{{
  "match_id": "{match['id']}",
  "team_a": "{team_a}",
  "team_b": "{team_b}",
  "stage": "{stage}",
  "date": "{date}",
  "context_a": {{
    "fifa_ranking_approx": "大约第X位（{year}年）",
    "recent_form": ["最近几场竞赛场结果，如W/L/D"],
    "key_players": "关键球员信息",
    "injuries_suspensions": "已知伤停",
    "tactical_style": "战术风格描述",
    "tournament_form": "本届赛事表现（如适用）"
  }},
  "context_b": {{
    "fifa_ranking_approx": "...",
    "recent_form": ["..."],
    "key_players": "...",
    "injuries_suspensions": "...",
    "tactical_style": "...",
    "tournament_form": "..."
  }},
  "head_to_head": "历史交锋简述",
  "pre_match_narrative": "赛前主流分析和预期",
  "estimated_odds_favorite": "{team_a}还是{team_b}，或势均力敌",
  "context_quality": "高/中/低（信息完整程度）"
}}

【重要】不要写这场比赛的实际结果或比分。"""

    resp = client.messages.create(
        model=config.MODEL,
        max_tokens=1500,
        system=DATASET_BUILDER_SYSTEM,
        messages=[{"role": "user", "content": prompt}]
    )

    text = resp.content[0].text

    # 尝试解析JSON
    import re
    json_match = re.search(r"\{.*\}", text, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group())
        except Exception:
            pass

    # 兜底
    return {
        "match_id": match["id"],
        "team_a": team_a,
        "team_b": team_b,
        "stage": stage,
        "date": date,
        "raw_context": text,
        "context_quality": "低（解析失败，使用原始文本）"
    }


def build_dataset(year: int, save_dir: str = None) -> list[dict]:
    """构建某年世界杯的完整赛前数据集。"""
    matches_file = Path(__file__).parent / "data" / f"matches_{year}.json"
    data = json.loads(matches_file.read_text(encoding="utf-8"))
    matches = data["matches"]

    save_dir = Path(save_dir or (Path(__file__).parent / "data"))
    output_file = save_dir / f"prematch_context_{year}.json"

    # 如果已有部分数据，接着跑
    existing = {}
    if output_file.exists():
        existing_list = json.loads(output_file.read_text(encoding="utf-8"))
        existing = {m["match_id"]: m for m in existing_list}
        print(f"  已有 {len(existing)} 场比赛的数据，继续补充...")

    results = list(existing.values())

    for i, match in enumerate(matches):
        if match["id"] in existing:
            print(f"  [{i+1}/{len(matches)}] 跳过（已有）: {match['team_a']} vs {match['team_b']}")
            continue

        print(f"\n[{i+1}/{len(matches)}] 构建: {match['team_a']} vs {match['team_b']} ({match['stage']})")
        try:
            ctx = build_prematch_context(match)
            results.append(ctx)
            # 每次追加保存
            output_file.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception as e:
            print(f"  失败: {e}")
            results.append({"match_id": match["id"], "team_a": match["team_a"],
                           "team_b": match["team_b"], "error": str(e)})

        time.sleep(1)

    print(f"\n数据集已保存: {output_file}")
    return results


if __name__ == "__main__":
    year = int(sys.argv[1]) if len(sys.argv) > 1 else 2022
    build_dataset(year)
