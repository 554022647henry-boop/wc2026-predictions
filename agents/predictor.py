"""
预测引擎 v3 — 7个量化 Indicator Agent + 赔率校验 + 裁判

流程：
  collected data (ESPN/WhoScored/CBS/DeepSeek)
      ↓
  reviewed_to_context()  — 格式化为富文本
      ↓
  7个独立 Indicator Agent（每个只管一个维度，输出0-10分）
      ↓
  aggregate_scores()  — 加权分差 → 概率分布
      ↓
  H赔率校验  — 纠偏（不参与计分）
      ↓
  裁判 Agent  — 概率 → 预测结论 + 3条理由
"""
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from agents.indicator_agents import (
    AGENTS_IN_ORDER, DIMENSION_WEIGHTS,
    N_FOR_GROUP_STAGE, N_FOR_KNOCKOUT,
    run_n_agents, run_odds_calibrator
)
from agents.quant_model import aggregate_scores

client = config.make_client()


# ─────────────────────────────────────────
# reviewed → 富文本上下文
# ─────────────────────────────────────────

def reviewed_to_context(reviewed: dict) -> str:
    """
    把 reviewer 结构化 JSON 转成供7个 Indicator Agent 使用的富文本。
    确保每个维度都能找到需要的信息。
    """
    ta = reviewed.get("team_a", {})
    tb = reviewed.get("team_b", {})
    odds = reviewed.get("odds", {})
    dk = odds.get("draftkings", {})
    notable = reviewed.get("notable_info", "")

    sections = []

    # 赔率（维度H/E）
    if dk.get("a") or dk.get("b"):
        sections.append(f"【赔率 - DraftKings】"
                        f"{ta.get('name','A')} {dk.get('a','?')} / "
                        f"Draw {dk.get('draw','?')} / "
                        f"{tb.get('name','B')} {dk.get('b','?')}")
    else:
        pinnacle = odds.get("pinnacle", {})
        if any(pinnacle.values()):
            sections.append(f"【赔率 - Pinnacle】{pinnacle}")
        else:
            sections.append("【赔率】暂无数据")

    # A队信息
    sections.append(f"\n【{ta.get('name','A队')} 信息】")
    if ta.get("confirmed_absences"):
        sections.append(f"确认缺阵: {', '.join(ta['confirmed_absences'])}")
    if ta.get("doubtful"):
        sections.append(f"疑似伤停: {', '.join(ta['doubtful'])}")
    if ta.get("confirmed_lineup"):
        sections.append(f"确认首发: {ta['confirmed_lineup']}")
    if ta.get("recent_form"):
        sections.append(f"近期战绩: {' | '.join(ta['recent_form'][:5])}")
    if ta.get("key_player_notes"):
        sections.append(f"关键球员: {ta['key_player_notes']}")
    if ta.get("coach_statement"):
        sections.append(f"教练表态: {ta['coach_statement']}")
    if ta.get("latest_news"):
        sections.append(f"最新消息: {ta['latest_news'][:200]}")

    # B队信息
    sections.append(f"\n【{tb.get('name','B队')} 信息】")
    if tb.get("confirmed_absences"):
        sections.append(f"确认缺阵: {', '.join(tb['confirmed_absences'])}")
    if tb.get("doubtful"):
        sections.append(f"疑似伤停: {', '.join(tb['doubtful'])}")
    if tb.get("confirmed_lineup"):
        sections.append(f"确认首发: {tb['confirmed_lineup']}")
    if tb.get("recent_form"):
        sections.append(f"近期战绩: {' | '.join(tb['recent_form'][:5])}")
    if tb.get("key_player_notes"):
        sections.append(f"关键球员: {tb['key_player_notes']}")
    if tb.get("coach_statement"):
        sections.append(f"教练表态: {tb['coach_statement']}")
    if tb.get("latest_news"):
        sections.append(f"最新消息: {tb['latest_news'][:200]}")

    # 维度评分参考（给Agent看质量）
    dim_scores = reviewed.get("dimension_scores", {})
    if dim_scores:
        sections.append(f"\n【信息质量（审阅官评分）】{dim_scores}")

    # 额外补充信息
    if notable:
        sections.append(f"\n【补充背景】{notable[:600]}")

    return "\n".join(sections)


# ─────────────────────────────────────────
# 裁判 Agent：概率 → 文字预测 + 3条理由
# ─────────────────────────────────────────

JUDGE_SYSTEM = """你是世界杯比赛预测的最终裁判。
你已收到量化模型的计算结果，现在需要：
1. 确认或微调预测方向（基于你对比赛的整体判断）
2. 写3条面向普通球迷的预测理由（具体、有画面感，提到球员名或战术细节）
3. 指出最主要的爆冷风险

【关于球员名字的严格要求】：
- 只能提及「来源4a ESPN官方知识库」中出现的球员
- 禁止提及：格列兹曼(Griezmann)、卡马文加(Camavinga)、吉鲁(Giroud)、洛里斯(Lloris) 等未入选球员
- 禁止编造比赛结果（如"4-1大胜阿根廷"这类可能不真实的结果）
- 如果不确定球员是否入选，只写"核心球员"而不写具体名字

只输出 JSON，格式：
{"prediction": "A队名胜/平局/B队名胜", "confidence": "高/中/低",
 "reasons": ["...", "...", "..."], "key_risk": "..."}
"""


def run_judge(team_a: str, team_b: str, stage: str,
              quant_result: dict, context: str) -> dict:
    """裁判：把量化结果转成可读预测。"""
    is_knockout = stage not in ("group_stage", "小组赛")

    pred = quant_result.get("prediction", "DRAW")
    pa = quant_result.get("p_a_win", 0.33)
    pd = quant_result.get("p_draw", 0.34)
    pb = quant_result.get("p_b_win", 0.33)
    delta = quant_result.get("weighted_delta", 0)
    conf = quant_result.get("confidence_level", "低")
    calib = quant_result.get("calibration_note", "")

    pred_label = (
        f"{team_a}胜" if pred == "A_WIN"
        else ("平局" if pred == "DRAW" else f"{team_b}胜")
    )

    breakdown = quant_result.get("dimension_breakdown", [])
    breakdown_text = "\n".join(
        f"  {d['label']}(w={d['weight']:.2f}): "
        f"{team_a}={d['a_score']:.1f} {team_b}={d['b_score']:.1f} "
        f"δ={d['delta']:+.1f} conf={d['confidence']:.1f}"
        for d in breakdown
    )

    user_msg = f"""比赛：{team_a} vs {team_b}（{stage}）
{'淘汰赛：无平局选项' if is_knockout else '小组赛：平局可选'}

【量化模型结果】
加权分差 δ = {delta:+.2f}（正=A占优，负=B占优）
概率：{team_a}胜 {pa:.0%} / 平局 {pd:.0%} / {team_b}胜 {pb:.0%}
建议预测：{pred_label}（{conf}置信）
{('校验警告：' + calib) if calib else ''}

【各维度评分明细】
{breakdown_text}

【赛前信息摘要】
{context[:800]}

请确认预测方向，并写3条球迷可读的理由。"""

    try:
        resp = client.messages.create(
            model=config.MODEL,
            max_tokens=600,
            system=JUDGE_SYSTEM,
            messages=[{"role": "user", "content": user_msg}],
        )
        text = resp.content[0].text
        m = re.search(r'\{.*\}', text, re.DOTALL)
        if m:
            return json.loads(m.group())
    except Exception as e:
        pass

    # 兜底
    return {
        "prediction": pred_label,
        "confidence": conf,
        "reasons": [
            f"量化模型综合{len(breakdown)}个维度，{team_a if delta>0 else team_b}占优",
            f"分差 δ={delta:+.2f}，{'强势胜出' if abs(delta)>2 else '小幅占优'}",
            "详见维度评分明细",
        ],
        "key_risk": quant_result.get("calibration_note", "")[:80] or "势均力敌，存在变数",
    }


# ─────────────────────────────────────────
# 主函数
# ─────────────────────────────────────────

def _normalize_kb_v2(raw: dict, team_name: str) -> dict:
    """
    把 v2 知识库格式（带_source标注）转换为 indicator_agents 可用的格式。
    v2 结构: {squad:{data:[...]}, recent_form:{data:[...]}, historical:{...}}
    v1 结构: {squad:{squad_26:[...]}, tactical:{...}, key_players:[...], form_recent:[...]}
    """
    hist = raw.get("historical", {})
    squad_data = raw.get("squad", {}).get("data", [])
    form_data  = raw.get("recent_form", {}).get("data", [])

    # 转换大名单格式
    squad_26 = []
    for p in squad_data:
        squad_26.append({
            "name": p.get("name", "?"),
            "pos":  p.get("pos", "?"),
            "age":  p.get("age"),
            "club": p.get("club"),   # ESPN不提供，通常为null
            "_source": p.get("_source", "ESPN_ROSTER"),
            "_verified": p.get("_verified", True),
        })

    # 转换近期战绩格式
    form_recent = []
    for m in form_data[:6]:
        home, away = m.get("home", "?"), m.get("away", "?")
        hs, as_ = m.get("home_score", "?"), m.get("away_score", "?")
        result = f'{home} {hs}-{as_} {away}'
        form_recent.append({
            "date":   m.get("date", "?"),
            "match":  result,
            "home":   home,
            "away":   away,
            "h_score": hs,
            "a_score": as_,
            "type":   m.get("type", "?"),
            "_source": m.get("_source", "ESPN"),
            "_verified": m.get("_verified", True),
        })

    # 从大名单提取关键球员（前场+中场中最知名的）
    # v2不含key_players，从squad里提取FW/MF位置的球员作为潜在关键球员
    key_pos = {"FW","F","MF","M","CF","CAM","AM","RW","LW"}
    key_players_raw = [p for p in squad_26 if p.get("pos","").upper() in key_pos][:6]

    return {
        # ── 大名单（ESPN真实数据）
        "squad": {
            "squad_26": squad_26,
            "_count": len(squad_26),
            "_source": "ESPN_ROSTER",
            "_verified": True,
        },

        # ── 近期战绩（ESPN真实数据）
        "form_recent": form_recent,

        # ── 战术（AI历史，标注不可信）
        "tactical": {
            "formation_primary": hist.get("formation"),
            "formation_alternative": None,
            "attack": {
                "build_up_style": hist.get("attack_style"),
                "main_creation_zone": None,
                "key_pattern_1": None,
                "attack_weakness": None,
            },
            "defense": {
                "key_weakness": hist.get("defensive_weakness"),
                "how_to_beat": hist.get("how_to_beat"),
                "defensive_block": None,
            },
            "press_resistance": {"can_play_under_press": None},
            "_source": "DEEPSEEK_HISTORICAL",
            "_verified": False,
            "_note": "战术数据来自AI历史知识，需比对实际观察",
        },

        # ── 世界杯历史（AI历史，相对稳定可靠）
        "wc_history": {
            "2022": hist.get("wc_2022"),
            "2018": hist.get("wc_2018"),
            "2014": hist.get("wc_2014"),
            "opening_game_pattern": hist.get("opening_game_pattern"),
            "big_game_dna_note":    hist.get("big_game_dna"),
            "from_behind_record": None,
            "_source": "DEEPSEEK_HISTORICAL",
            "_note": "历史赛事记录，一般可信",
        },

        # ── 基础信息（v2无此数据，设为null）
        "basics": {
            "coach": hist.get("coach"),
            "fifa_ranking": None,          # v2无此数据
            "squad_market_value_eur": None, # v2无此数据
            "_source": "DEEPSEEK_HISTORICAL_partial",
            "_note": "FIFA排名/身价v2暂无，教练来自AI历史",
        },

        # ── 关键球员（从squad提取，无详细信息）
        "key_players": [
            {
                "name": p["name"],
                "pos": p.get("pos"),
                "club": p.get("club"),     # ESPN不提供，通常null
                "role": None,
                "form_2026": None,
                "absence_impact": None,
                "neutralize_with": None,
                "_source": "ESPN_ROSTER",
                "_note": "来自ESPN大名单，无详细球员信息",
            }
            for p in key_players_raw
        ],

        # ── 球队化学（v2无此数据）
        "chemistry": {
            "core_combination_years": None,
            "system_stability": hist.get("coach") and "教练已确认" or None,
            "_source": "NOT_AVAILABLE",
        },

        # ── 情境因素（v2无此数据）
        "context_factors": {
            "tournament_expectation": None,
            "media_pressure": None,
            "_source": "NOT_AVAILABLE",
        },

        "coach":   {"name": hist.get("coach"), "_source": "DEEPSEEK_HISTORICAL"},
        "_meta":   raw.get("_meta", {}),
        "_v2_raw": raw,
    }


def _load_kb(team_a: str, team_b: str) -> tuple[dict, dict]:
    """
    加载两队的知识库数据。
    优先使用 v2（真实数据源），回退到 v1（AI生成）。
    """
    base = Path(config.BASE_DIR) / "data"
    v2_file = base / "team_knowledge_v2.json"
    v1_file = base / "team_knowledge_2026.json"

    # 优先 v2
    if v2_file.exists():
        try:
            kb = json.loads(v2_file.read_text(encoding="utf-8"))
            raw_a = kb.get(team_a, {})
            raw_b = kb.get(team_b, {})
            if raw_a:
                kb_a = _normalize_kb_v2(raw_a, team_a)
                sq_a = kb_a["squad"]["_count"]
                fm_a = len(kb_a["form_recent"])
                print(f"  [知识库v2] {team_a}: {sq_a}人 | {fm_a}场战绩 | 阵型={kb_a['tactical'].get('formation_primary','?')} ✅")
            else:
                kb_a = {}
                print(f"  [知识库v2] {team_a}: 暂无数据")
            if raw_b:
                kb_b = _normalize_kb_v2(raw_b, team_b)
                sq_b = kb_b["squad"]["_count"]
                fm_b = len(kb_b["form_recent"])
                print(f"  [知识库v2] {team_b}: {sq_b}人 | {fm_b}场战绩 | 阵型={kb_b['tactical'].get('formation_primary','?')} ✅")
            else:
                kb_b = {}
                print(f"  [知识库v2] {team_b}: 暂无数据")
            return kb_a, kb_b
        except Exception as e:
            print(f"  [知识库v2] 加载失败，回退v1: {e}")

    # 回退 v1
    if v1_file.exists():
        try:
            kb = json.loads(v1_file.read_text(encoding="utf-8"))
            kb_a = kb.get(team_a, {})
            kb_b = kb.get(team_b, {})
            print(f"  [知识库v1⚠️] {team_a}/{team_b}: 使用旧版AI生成数据")
            return kb_a, kb_b
        except Exception as e:
            print(f"  [知识库] 加载失败: {e}")
    return {}, {}


def run_prediction(match_info: dict, reviewed: dict,
                   round_key: str, round_label: str,
                   n_agents: int = None) -> dict:
    """
    完整预测流水线：
      知识库(team_knowledge_2026.json) + reviewed data
        → 7 Indicator Agents（每个收到维度专属上下文）
        → aggregate → 赔率校验 → 裁判
    """
    if n_agents is None:
        stage_key = match_info.get("stage", "group_stage")
        is_ko = stage_key not in ("group_stage", "小组赛")
        n_agents = N_FOR_KNOCKOUT if is_ko else N_FOR_GROUP_STAGE

    match_id = match_info["match_id"]
    team_a = match_info["team_a"]
    team_b = match_info["team_b"]
    stage = match_info.get("stage", "group_stage")
    is_knockout = stage not in ("group_stage", "小组赛")

    print(f"\n[预测引擎] {team_a} vs {team_b} | {round_label} | N={n_agents}")
    print("=" * 60)

    # 0. 加载知识库
    kb_a, kb_b = _load_kb(team_a, team_b)

    # 1. 把 reviewed 转成富文本上下文
    context = reviewed_to_context(reviewed)

    # 2. 运行 N 个 Indicator Agents（每个独立评一个维度，含知识库数据）
    print(f"  [运行{n_agents}个Indicator Agents]")
    scores = run_n_agents(n_agents, team_a, team_b, context, stage,
                          kb_a=kb_a, kb_b=kb_b)

    # 3. 赔率校验器（H维度，独立运行）
    print(f"  [赔率校验器]")
    calibrator = run_odds_calibrator(team_a, team_b, context)

    # 4. 数学聚合
    quant_result = aggregate_scores(scores, calibrator, is_knockout)
    quant_result["n_agents"] = n_agents

    # 5. 裁判输出可读预测
    print(f"  [裁判] 生成预测结论...")
    judge = run_judge(team_a, team_b, stage, quant_result, context)

    # 6. 组装完整预测文件
    prediction = {
        "match_id": match_id,
        "round": round_key,
        "round_label": round_label,
        "timestamp": datetime.now().isoformat(),

        "_internal": {
            "说明": "内部留痕，供追溯复盘",
            "n_agents": n_agents,
            "weighted_delta": quant_result["weighted_delta"],
            "p_a_win": quant_result["p_a_win"],
            "p_draw": quant_result["p_draw"],
            "p_b_win": quant_result["p_b_win"],
            "dimension_breakdown": quant_result["dimension_breakdown"],
            "calibration_warning": quant_result.get("calibration_warning", False),
            "calibration_note": quant_result.get("calibration_note", ""),
            "judge_reasoning": judge.get("prediction", ""),
        },

        "output": {
            "说明": "对外展示到HTML",
            "prediction": judge.get("prediction", ""),
            "confidence": judge.get("confidence", "中"),
            "reasons": judge.get("reasons", [])[:3],
            "key_risk": judge.get("key_risk", ""),
        },

        "actual_result": None,
    }

    # 保存
    save_dir = Path(config.PREDICTIONS_DIR) / match_id
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"{round_key}_prediction.json"
    save_path.write_text(
        json.dumps(prediction, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n[预测引擎] 完成: {prediction['output']['prediction']} ({prediction['output']['confidence']})")
    for i, r in enumerate(prediction["output"]["reasons"], 1):
        print(f"  理由{i}: {r}")

    # Git 存档（不可篡改的时间戳证明）
    _git_archive(save_path, team_a, team_b, round_label,
                 prediction['output']['prediction'])

    return prediction


def run_prediction_v2(match_info: dict, round_key: str = "initial",
                      round_label: str = "初始预测",
                      n_agents: int = None) -> dict:
    """
    新版预测流水线（v2）：
      KB v2（静态真实数据）+ ESPN实时数据
        → 直接给7个Indicator Agents
        → aggregate → 赔率校验 → 裁判

    与旧版的区别：
      - 不再运行collector/reviewer（省去10+次DeepSeek API调用）
      - 大名单/战绩直接从KB v2读（ESPN官方数据）
      - 实时数据（赔率/积分/首发）直接从ESPN API读
      - 信息质量更高，速度更快（约3-4次API调用 vs 15次）
    """
    from agents.match_context import build_match_context, context_to_text

    if n_agents is None:
        stage_key = match_info.get("stage", "group_stage")
        is_ko = stage_key not in ("group_stage", "小组赛")
        n_agents = N_FOR_KNOCKOUT if is_ko else N_FOR_GROUP_STAGE

    match_id = match_info["match_id"]
    team_a   = match_info["team_a"]
    team_b   = match_info["team_b"]
    stage    = match_info.get("stage", "group_stage")
    is_knockout = stage not in ("group_stage", "小组赛")

    print(f"\n[预测引擎v2] {team_a} vs {team_b} | {round_label} | N={n_agents}")
    print("=" * 60)

    # 1. 构建比赛上下文（KB v2 + ESPN实时）
    ctx_dict = build_match_context(match_info)
    context  = context_to_text(ctx_dict)

    # 2. 加载KB数据供各Agent使用（从match_context里提取格式化好的kb_a/kb_b）
    kb_a, kb_b = _load_kb(team_a, team_b)

    # 3. 把积分/赔率等实时数据补充到kb的context_factors里
    st = ctx_dict.get("standings", {})
    if kb_a:
        kb_a.setdefault("context_factors", {})
        kb_a["context_factors"]["stakes"] = st.get("stakes_a", "")
        kb_a["context_factors"]["rest_days"] = ctx_dict.get("rest_days_a", {}).get("rest_days")
    if kb_b:
        kb_b.setdefault("context_factors", {})
        kb_b["context_factors"]["stakes"] = st.get("stakes_b", "")
        kb_b["context_factors"]["rest_days"] = ctx_dict.get("rest_days_b", {}).get("rest_days")

    # 4. 运行7个Indicator Agents
    print(f"  [运行{n_agents}个Indicator Agents]")
    scores = run_n_agents(n_agents, team_a, team_b, context, stage,
                          kb_a=kb_a, kb_b=kb_b)

    # 5. 赔率校验器
    print("  [赔率校验器]")
    calibrator = run_odds_calibrator(team_a, team_b, context)

    # 6. 数学聚合
    quant_result = aggregate_scores(scores, calibrator, is_knockout)
    quant_result["n_agents"] = n_agents

    # 7. 裁判
    print("  [裁判] 生成预测结论...")
    judge = run_judge(team_a, team_b, stage, quant_result, context)

    # 8. 组装并保存
    prediction = {
        "match_id":    match_id,
        "round":       round_key,
        "round_label": round_label,
        "timestamp":   datetime.now().isoformat(),
        "pipeline":    "v2_match_context",

        "_internal": {
            "说明": "v2流水线：KB v2 + ESPN实时，无DeepSeek数据补充",
            "n_agents": n_agents,
            "weighted_delta": quant_result["weighted_delta"],
            "p_a_win":  quant_result["p_a_win"],
            "p_draw":   quant_result["p_draw"],
            "p_b_win":  quant_result["p_b_win"],
            "dimension_breakdown": quant_result["dimension_breakdown"],
            "calibration_warning": quant_result.get("calibration_warning", False),
            "calibration_note":    quant_result.get("calibration_note", ""),
            "judge_reasoning":     judge.get("prediction", ""),
            "data_sources": {
                "squad":      "ESPN_ROSTER✅",
                "form":       "ESPN_API✅",
                "odds":       ctx_dict.get("odds_source", "未获取"),
                "standings":  ctx_dict.get("standings", {}).get("_source", "无"),
                "lineup":     ctx_dict.get("lineup_source", "未获取"),
                "tactics":    "DEEPSEEK_HISTORICAL⚠️",
                "wc_history": "DEEPSEEK_HISTORICAL⚠️",
            },
        },

        "output": {
            "说明": "对外展示到HTML",
            "prediction": judge.get("prediction", ""),
            "confidence": judge.get("confidence", "中"),
            "reasons":    judge.get("reasons", [])[:3],
            "key_risk":   judge.get("key_risk", ""),
        },

        "actual_result": None,
    }

    save_dir  = Path(config.PREDICTIONS_DIR) / match_id
    save_dir.mkdir(parents=True, exist_ok=True)
    save_path = save_dir / f"{round_key}_prediction.json"
    save_path.write_text(
        json.dumps(prediction, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n[预测引擎v2] 完成: {prediction['output']['prediction']} ({prediction['output']['confidence']})")
    for i, r in enumerate(prediction["output"]["reasons"], 1):
        print(f"  理由{i}: {r}")

    _git_archive(save_path, team_a, team_b, round_label,
                 prediction['output']['prediction'])

    return prediction


def _git_archive(pred_file: Path, team_a: str, team_b: str,
                 round_label: str, result: str):
    """
    将预测文件 git commit + push，利用 GitHub 时间戳作为可信存档。
    失败不影响主流程。
    """
    import subprocess
    try:
        repo_root = Path(__file__).parent.parent
        rel_path  = pred_file.relative_to(repo_root)

        msg = (f"[预测存档] {team_a} vs {team_b} | "
               f"{round_label} | {result} | "
               f"{datetime.now().strftime('%Y-%m-%d %H:%M')}")

        subprocess.run(["git", "add", str(rel_path)],
                       cwd=repo_root, check=True,
                       capture_output=True)
        subprocess.run(["git", "commit", "-m", msg, "--no-verify"],
                       cwd=repo_root, check=True,
                       capture_output=True)

        # push（用 token 写入远端 URL，避免交互式密码）
        token_file = repo_root.parent / "github" / ".github_token"
        if token_file.exists():
            token = token_file.read_text(encoding="utf-8").strip()
            remote_url = (f"https://{token}@github.com/"
                          "554022647henry-boop/wc2026-predictions.git")
            subprocess.run(["git", "push", remote_url, "main"],
                           cwd=repo_root, check=True,
                           capture_output=True)
            print(f"  [Git] 存档推送成功: {msg[:60]}...")
        else:
            print(f"  [Git] 已 commit，未 push（无 token）")

    except Exception as e:
        print(f"  [Git] 存档失败（不影响预测）: {e}")
