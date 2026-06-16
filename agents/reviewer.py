"""
Agent 2 — 信息审阅 + 缺口补充
读取 Agent1 的原始搜集内容，过滤整理，检查缺口，
必要时指派 Agent1 补充（最多2轮）。
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import anthropic

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from agents.collector import run_collection
from agents.odds_analyzer import append_odds_snapshot

client = config.make_client()


# ─────────────────────────────────────────
# 审阅核心
# ─────────────────────────────────────────

def review(match_info: dict, round_key: str, round_label: str, raw_file_path: str) -> dict:
    """
    审阅原始搜集内容，执行最多2轮补充，返回最终结构化信息。

    Returns
    -------
    dict: 结构化的审阅结果（含 _supplement_history 内部字段）
    """
    match_id = match_info["match_id"]
    team_a = match_info["team_a"]
    team_b = match_info["team_b"]
    is_close_to_kickoff = _is_close_to_kickoff(match_info)

    # 读取原始内容
    raw_data = json.loads(Path(raw_file_path).read_text(encoding="utf-8"))
    raw_content = raw_data["raw_content"]

    supplement_history = []

    for attempt in range(config.MAX_SUPPLEMENT_ROUNDS + 1):  # 0=初审, 1=第1轮补充后审, 2=第2轮补充后审
        print(f"\n[Agent2] 审阅 {match_id} | {round_label} | 轮次 {attempt}")

        reviewed, supplement_needed, supplement_queries = _do_review(
            match_info=match_info,
            raw_content=raw_content,
            round_key=round_key,
            round_label=round_label,
            is_close_to_kickoff=is_close_to_kickoff,
        )

        if not supplement_needed or attempt >= config.MAX_SUPPLEMENT_ROUNDS:
            # 不需要补充，或已达到最大补充轮次 → 结束
            if attempt >= config.MAX_SUPPLEMENT_ROUNDS and supplement_needed:
                print(f"[Agent2] 已达最大补充轮次({config.MAX_SUPPLEMENT_ROUNDS})，强制结束，使用现有信息")
            break

        # 需要补充 → 调用 Agent1
        supp_index = attempt + 1
        print(f"[Agent2] 发现信息缺口，指派 Agent1 补充（第{supp_index}轮）")
        print(f"  补充搜索词: {supplement_queries}")

        supp_file = run_collection(
            match_info=match_info,
            round_key=round_key,
            round_label=round_label,
            supplement_queries=supplement_queries,
            supp_index=supp_index,
        )
        supp_data = json.loads(Path(supp_file).read_text(encoding="utf-8"))

        # 合并补充内容到 raw_content
        raw_content += f"\n\n===== 补充内容 第{supp_index}轮 =====\n{supp_data['raw_content']}"
        supplement_history.append({
            "round": supp_index,
            "queries": supplement_queries,
            "file": supp_file,
        })

    # 注入内部字段
    reviewed["_supplement_history"] = supplement_history
    reviewed["_review_timestamp"] = datetime.now().isoformat()

    # 保存审阅结果
    _save_reviewed(match_id, round_key, reviewed)

    return reviewed


def _do_review(
    match_info: dict,
    raw_content: str,
    round_key: str,
    round_label: str,
    is_close_to_kickoff: bool,
) -> tuple[dict, bool, list[str]]:
    """
    调用 DeepSeek 执行一次审阅。
    Returns: (reviewed_dict, supplement_needed, supplement_queries)
    """
    team_a = match_info["team_a"]
    team_b = match_info["team_b"]
    match_id = match_info["match_id"]

    lineup_check = (
        f"距开球 < 1小时：必须检查首发阵容是否已公布"
        if is_close_to_kickoff
        else "距开球 > 1小时：首发阵容不作强制要求"
    )

    hours_before = _get_hours_before(match_info)

    prompt_template = Path(config.PROMPTS_DIR) / "reviewer_prompt.txt"
    user_prompt = prompt_template.read_text(encoding="utf-8").format(
        raw_collected=raw_content,
        team_a=team_a,
        team_b=team_b,
        match_id=match_id,
        round=round_key,
        round_label=round_label,
        hours_before=hours_before,
    )

    # T-30min 附加首发要求
    if is_close_to_kickoff:
        user_prompt += f"\n\n【额外要求】距开球<1小时，首发阵容若未确认评1分，已确认评满分。"

    response = client.messages.create(
        model=config.MODEL,
        max_tokens=3500,
        system=(
            "你是世界杯预测系统的信息质量审阅官（Agent2）。"
            "严格执行7维度评分，确保JSON格式正确，"
            "当信息不足时必须输出 SUPPLEMENT_NEEDED: true。"
            "不允许因为'信息有限'就直接通过低质量数据。"
        ),
        messages=[{"role": "user", "content": user_prompt}],
    )

    text = response.content[0].text

    # 解析 JSON
    reviewed = _parse_reviewed_json(text, match_id, round_key, team_a, team_b)

    # 检查维度评分，判断是否需要补充
    dim_scores = reviewed.get("dimension_scores", {})
    weighted = reviewed.get("weighted_score", 0)

    # 新维度key（v3）兼容旧key
    f_score   = dim_scores.get("F_tactical", dim_scores.get("tactics", 5))
    e_score   = dim_scores.get("E_context",  dim_scores.get("motivation", 5))
    odds_score = dim_scores.get("odds", 5)
    form_score = dim_scores.get("C_form", dim_scores.get("form", 5))
    recent_form_empty = not reviewed.get("team_a", {}).get("recent_form") and \
                        not reviewed.get("team_b", {}).get("recent_form")

    # 补充触发条件（v3：战术和情境缺口优先级最高）
    needs_supplement = (
        "SUPPLEMENT_NEEDED: true" in text
        or (weighted > 0 and weighted < 15)
        or f_score <= 2          # 战术对位（25%）信息严重不足
        or odds_score < 3        # 赔率缺失
        or (form_score < 3 and recent_form_empty)  # 无任何近期战绩
    )

    supplement_queries = []
    if needs_supplement:
        # 优先从响应中提取SEARCH_QUERIES
        matches = re.findall(r'^\d+\.\s*"?(.+?)"?\s*(?:→|->)', text, re.MULTILINE)
        if not matches:
            matches = re.findall(r"^\d+\.\s*(.+?)(?:\s*→|\s*->|\s*$)", text, re.MULTILINE)
        supplement_queries = [m.strip() for m in matches if m.strip() and len(m.strip()) > 5]

        if not supplement_queries:
            # 自动生成针对缺口维度的补充查询
            if f_score <= 2:
                supplement_queries.append(f"{team_a} 2026 World Cup formation tactics coach style")
                supplement_queries.append(f"{team_b} 2026 World Cup formation tactics defensive weakness")
            if odds_score < 3:
                supplement_queries.append(f"{team_a} vs {team_b} 世界杯赔率 DraftKings Pinnacle")
            if form_score < 3:
                supplement_queries.append(f"{team_a} recent matches results June 2026")
                supplement_queries.append(f"{team_b} recent matches results June 2026")

    print(f"[Agent2] 维度评分: {dim_scores} | 加权分: {weighted} | 补充: {needs_supplement}")
    return reviewed, needs_supplement, supplement_queries


def _parse_reviewed_json(text: str, match_id: str, round_key: str, team_a: str, team_b: str) -> dict:
    """从响应中提取 JSON 块，支持新格式（含 dimension_scores）。"""
    # 尝试提取 ```json 块
    for pattern in [r"```json\s*(.*?)\s*```", r"```\s*(.*?)\s*```"]:
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                d = json.loads(m.group(1))
                _ensure_defaults(d, match_id, round_key, team_a, team_b)
                return d
            except json.JSONDecodeError:
                pass

    # 尝试解析整段
    try:
        d = json.loads(text)
        _ensure_defaults(d, match_id, round_key, team_a, team_b)
        return d
    except json.JSONDecodeError:
        pass

    # 尝试找最大的 { } 块
    m2 = re.search(r'\{[^{}]{200,}\}', text, re.DOTALL)
    if m2:
        try:
            d = json.loads(m2.group())
            _ensure_defaults(d, match_id, round_key, team_a, team_b)
            return d
        except Exception:
            pass

    # 兜底：返回包含原始文本的最小结构
    fallback = {
        "match_id": match_id,
        "collection_round": round_key,
        "team_a": {"name": team_a, "confirmed_absences": [], "doubtful": [],
                   "confirmed_lineup": None, "recent_form": [],
                   "key_player_notes": "", "coach_statement": "", "latest_news": ""},
        "team_b": {"name": team_b, "confirmed_absences": [], "doubtful": [],
                   "confirmed_lineup": None, "recent_form": [],
                   "key_player_notes": "", "coach_statement": "", "latest_news": ""},
        "odds": {"pinnacle": {"a": None, "draw": None, "b": None},
                 "draftkings": {"a": None, "draw": None, "b": None},
                 "implied_prob": {"a": None, "draw": None, "b": None},
                 "line_movement": ""},
        "dimension_scores": {"F_tactical":1,"E_context":1,"G_dna":1,"D_keyplayer":1,"A_strength":1,"B_chemistry":1,"C_form":1},
        "weighted_score": 7,
        "notable_info": text[:800],
        "info_completeness": "不足（JSON解析失败）",
    }
    return fallback


def _ensure_defaults(d: dict, match_id: str, round_key: str, team_a: str, team_b: str):
    """确保必要字段存在，补充缺失的默认值。"""
    d.setdefault("match_id", match_id)
    d.setdefault("collection_round", round_key)
    d.setdefault("dimension_scores", {
        "F_tactical":3,"E_context":3,"G_dna":3,"D_keyplayer":3,
        "A_strength":3,"B_chemistry":3,"C_form":3
    })
    d.setdefault("weighted_score", 21)
    d.setdefault("info_completeness", "基本充分")
    # team_a/team_b 字段
    for key, tname in [("team_a", team_a), ("team_b", team_b)]:
        if key not in d or not isinstance(d[key], dict):
            d[key] = {"name": tname}
        d[key].setdefault("name", tname)
        d[key].setdefault("recent_form", [])
        d[key].setdefault("confirmed_absences", [])
        d[key].setdefault("doubtful", [])
        d[key].setdefault("confirmed_lineup", None)


def _save_reviewed(match_id: str, round_key: str, reviewed: dict):
    """保存审阅结果到 data/reviewed/{match_id}/，并追加赔率历史快照。"""
    save_dir = Path(config.REVIEWED_DIR) / match_id
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"{round_key}_reviewed.json"
    save_path.write_text(json.dumps(reviewed, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[Agent2] 审阅结果已保存: {save_path}")

    # ── 追加赔率快照到历史文件 ──────────────────────────────────
    odds = reviewed.get("odds", {})
    if odds.get("pinnacle") or odds.get("bet365"):
        append_odds_snapshot(match_id, round_key, {
            "pinnacle": odds.get("pinnacle", {}),
            "bet365": odds.get("bet365", {}),
        })
        print(f"[Agent2] 赔率快照已追加: {match_id} / {round_key}")


def _is_close_to_kickoff(match_info: dict) -> bool:
    """判断是否距比赛不足1小时。"""
    match_date = match_info.get("date", "")
    if not match_date:
        return False
    try:
        match_dt = datetime.fromisoformat(match_date)
        delta = (match_dt - datetime.now()).total_seconds() / 3600
        return delta < 1.0
    except Exception:
        return False


def _get_hours_before(match_info: dict) -> str:
    """返回距比赛时间的可读描述。"""
    match_date = match_info.get("date", "")
    if not match_date:
        return "时间未知"
    try:
        match_dt = datetime.fromisoformat(match_date)
        delta = (match_dt - datetime.now()).total_seconds() / 3600
        if delta > 24:
            return f"约 {delta/24:.1f} 天后开赛"
        return f"约 {delta:.1f} 小时后开赛"
    except Exception:
        return match_date
