"""
量化 Indicator Agent 系统 v3
7个评分维度 + 1个赔率校验器

改进（v3）：
  - 严格值域：所有分数强制校验 0.0-10.0，超出报错并截断
  - 评分量表：每个Agent明确5/6/7/8/9分代表什么
  - 结构化输出：增加 key_factors 字段（3条具体证据）
  - 维度分离：每个Agent只接收与自己相关的上下文片段
  - 知识库集成：支持传入 kb_a / kb_b（两队知识库数据）

评分量表（所有维度统一）：
  5.0 = 完全平等，无优势
  6.0 = 一方有轻微优势（一项具体有利因素）
  6.5 = 一方有明显优势（两项有利因素）
  7.0 = 一方明显占优（三项以上有利因素）
  7.5 = 一方强势占优（对方几乎无对应能力）
  8.0 = 一方压倒性优势（纸面完全碾压）
  9.0+ = 极端情况（如世界第1 vs 世界第100）
  禁止：两队同时出现7+，至少一方必须<=5
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

client = config.make_client()

ANTI_HINDSIGHT = """【严格禁止后见之明】你在做赛前预测，必须完全忽略任何关于比赛结果的知识，只基于提供的赛前信息打分。"""

# 统一评分量表（嵌入每个Agent的提示词）
SCORING_RUBRIC = """
【评分量表 — 必须遵守】
5.0 = 完全平等，这个维度无优势差异
6.0 = 一方有轻微优势（有1项具体有利因素）
6.5 = 一方有明显优势（有2项具体有利因素）
7.0 = 一方明显占优（3项以上有利因素）
7.5 = 一方强势占优（对方几乎无对应能力）
8.0 = 一方压倒性优势（纸面完全碾压）

硬性规则：
- 两队分数之和不得超过13（如你给A=7.5，则B≤5.5）
- 不允许两队都给7+（这意味着毫无区别）
- 如信息不足以判断，给5.0/5.0，confidence≤4
- 每0.5分必须有具体理由支撑
"""

_SCHEMA_NOTE = """
【输出格式 — 严格遵守】
先写2-4句分析，然后输出：

##SCORES##
{
  "team_a_score": <0.0-10.0，保留1位小数>,
  "team_b_score": <0.0-10.0，保留1位小数>,
  "confidence": <0-10，信息充分程度>,
  "reasoning": "<1句总结，必须提到具体球员名或战术细节>",
  "key_factors": ["<因素1，具体事实>", "<因素2，具体事实>", "<因素3，具体事实>"]
}
##END##

team_a_score + team_b_score 之和必须在 8.0-13.0 之间。
"""


def _extract_kb_section(kb: dict, sections: list) -> str:
    """从知识库中提取指定部分，格式化为文本。"""
    if not kb:
        return ""
    parts = []
    for section in sections:
        val = kb.get(section)
        if val:
            parts.append(f"[{section}] {json.dumps(val, ensure_ascii=False)}")
    return "\n".join(parts)


def _call(system: str, user: str) -> dict:
    """
    调用 DeepSeek，解析评分 JSON。
    解析 ##SCORES## 块，做值域校验后返回。
    """
    try:
        resp = client.messages.create(
            model=config.MODEL,
            max_tokens=600,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = resp.content[0].text

        # 优先：找 ##SCORES## 标记块
        m = re.search(r'##SCORES##\s*(\{.*?\})\s*##END##', text, re.DOTALL)
        if m:
            result = json.loads(m.group(1))
        else:
            # 退路1：找包含 team_a_score 的 JSON
            m2 = re.search(r'\{[^{}]*"team_a_score"[^{}]*\}', text, re.DOTALL)
            if m2:
                result = json.loads(m2.group())
            else:
                # 退路2：正则提取数字
                nums = re.findall(r'"(?:team_a_score|team_b_score|confidence)"\s*:\s*([\d.]+)', text)
                if len(nums) >= 3:
                    result = {"team_a_score": float(nums[0]), "team_b_score": float(nums[1]),
                              "confidence": float(nums[2]), "reasoning": text[-150:],
                              "key_factors": []}
                else:
                    raise ValueError("无法解析评分")

        result["full_analysis"] = text

        # ── 值域校验（核心改进）─────────────────────────────────
        for field in ("team_a_score", "team_b_score", "confidence"):
            val = float(result.get(field, 5.0))
            if val < 0 or val > 10:
                print(f"  [⚠️ 值域异常] {field}={val}，已截断至[0,10]")
                val = max(0.0, min(10.0, val))
            result[field] = round(val, 1)

        # 确保 key_factors 是列表
        if not isinstance(result.get("key_factors"), list):
            result["key_factors"] = []

        # 和值检查
        s = result["team_a_score"] + result["team_b_score"]
        if s > 13.0:
            print(f"  [⚠️ 和值异常] a={result['team_a_score']}+b={result['team_b_score']}={s}>13，等比例缩放")
            result["team_a_score"] = round(result["team_a_score"] * 13.0 / s, 1)
            result["team_b_score"] = round(result["team_b_score"] * 13.0 / s, 1)

        return result

    except Exception as e:
        print(f"  [Agent解析失败] {e}")
    return {"team_a_score": 5.0, "team_b_score": 5.0, "confidence": 3.0,
            "reasoning": "数据不足，中性评分", "key_factors": [], "full_analysis": ""}


# ─── A：绝对实力 ──────────────────────────────────────────────────
def agent_A_strength(ta: str, tb: str, ctx: str,
                     kb_a: dict = None, kb_b: dict = None) -> dict:
    kb_text = ""
    for name, kb in [(ta, kb_a), (tb, kb_b)]:
        if kb:
            b = kb.get("basics", {})
            s = kb.get("squad", {})
            ranking = b.get("fifa_ranking")
            value   = b.get("squad_market_value_eur")
            squad26 = s.get("squad_26", [])
            ranking_str = str(ranking) if ranking else "未知（需从赛前信息判断）"
            value_str   = f"{value:,}€" if value else "未知（需从赛前信息判断）"
            kb_text += f"\n[{name}大名单 来源=ESPN✅] FIFA排名:{ranking_str} | 身价:{value_str}"
            kb_text += f" | {len(squad26)}人名单: {', '.join(p['name'] for p in squad26[:8])}..."

    return _call(
        f"""你是绝对实力评估员。{ANTI_HINDSIGHT}
评估维度：
1. FIFA排名/ELO差距（排名差30名以上才有实质影响，排名未知则根据赛前信息推断）
2. 阵容整体档次（五大联赛主力 vs 中下游联赛；球员名单来自ESPN官方，可信）
3. 是否有能单场改变比赛走向的超级球员（梅西/姆巴佩级别，不是泛泛的"核心"）
注意：大名单来自ESPN官方WC注册名单（真实可信），身价/排名如无数据请基于球员俱乐部档次判断。
{SCORING_RUBRIC}{_SCHEMA_NOTE}""",
        f"比赛：{ta} vs {tb}\n{kb_text}\n赛前信息：{ctx[:500]}"
    )


# ─── B：球队化学反应 ──────────────────────────────────────────────
def agent_B_chemistry(ta: str, tb: str, ctx: str,
                      kb_a: dict = None, kb_b: dict = None) -> dict:
    kb_text = ""
    for name, kb in [(ta, kb_a), (tb, kb_b)]:
        if kb:
            chem = kb.get("chemistry", {})
            kb_text += f"\n[{name}化学反应] {json.dumps(chem, ensure_ascii=False)}"

    return _call(
        f"""你是球队化学反应评估员。{ANTI_HINDSIGHT}
评估维度：
1. 核心组合稳定性：主力阵容在一起打了多少年？同俱乐部球员有几人？
2. 更衣室氛围：教练执教多久？有无内部矛盾公开报道？
3. 体系成熟度：这套战术系统磨合多久？临阵换人会不会打乱节奏？
注意：世界杯集训仅约14天，化学反应差距会被放大。
{SCORING_RUBRIC}{_SCHEMA_NOTE}""",
        f"比赛：{ta} vs {tb}\n{kb_text}\n赛前信息：{ctx[:500]}"
    )


# ─── C：近期竞技状态 ──────────────────────────────────────────────
def agent_C_form(ta: str, tb: str, ctx: str,
                 kb_a: dict = None, kb_b: dict = None) -> dict:
    kb_text = ""
    for name, kb in [(ta, kb_a), (tb, kb_b)]:
        if kb:
            form = kb.get("form_recent", [])
            if form:
                parts = []
                for r in form[:6]:
                    # 兼容v1格式（opponent+result）和v2格式（home+away+scores）
                    if "opponent" in r:
                        parts.append(f"{r['date']} vs {r['opponent']} {r['result']}({r.get('type','')})")
                    elif "home" in r and "away" in r:
                        src = f"[ESPN✅]" if r.get("_verified") else "[AI⚠️]"
                        parts.append(f"{r['date']} {r['home']} {r.get('h_score','?')}-{r.get('a_score','?')} {r['away']} ({r.get('type','?')}) {src}")
                    else:
                        parts.append(str(r))
                kb_text += f"\n[{name}近期战绩-来源ESPN✅] " + " | ".join(parts)

    return _call(
        f"""你是近期状态评估员。{ANTI_HINDSIGHT}
评估维度：
1. 近5场竞赛场成绩（友谊赛权重30%，预选赛/正赛权重100%）
2. 进失球趋势（近3场进球是增加还是减少？）
3. 上一场是否留下体力消耗（加时、高强度比赛）？
4. 状态上升/下滑信号（是否3连胜/3连败？）
{SCORING_RUBRIC}{_SCHEMA_NOTE}""",
        f"比赛：{ta} vs {tb}\n{kb_text}\n赛前信息：{ctx[:500]}"
    )


# ─── D：关键球员 ─────────────────────────────────────────────────
def agent_D_keyplayer(ta: str, tb: str, ctx: str,
                      kb_a: dict = None, kb_b: dict = None) -> dict:
    kb_text = ""
    for name, kb in [(ta, kb_a), (tb, kb_b)]:
        if kb:
            kp = kb.get("key_players", [])
            if kp:
                kp_str = " | ".join(
                    f"{p['name']}({p.get('pos','?')},{p.get('club','?')}) "
                    f"状态:{p.get('form_2026','?')} 缺阵影响:{p.get('absence_impact','?')}"
                    for p in kp[:3]
                )
                kb_text += f"\n[{name}关键球员] {kp_str}"

    return _call(
        f"""你是关键球员状态评估员。{ANTI_HINDSIGHT}
评估维度：
1. 核心1-2名球员当前状态是否处于本赛季/本备战期高位？
2. 是否有确认伤停或存疑的隐患？
3. 对方有没有针对性的限制方案（已知能克制对方核心的防守球员或战术）？
4. 如果核心球员缺阵/状态不佳，球队备用方案是否充分？
必须引用具体球员名字，不能只说"核心球员"。
{SCORING_RUBRIC}{_SCHEMA_NOTE}""",
        f"比赛：{ta} vs {tb}\n{kb_text}\n赛前信息：{ctx[:500]}"
    )


# ─── E：情境/压力 ────────────────────────────────────────────────
def agent_E_context(ta: str, tb: str, ctx: str, stage: str = "",
                    kb_a: dict = None, kb_b: dict = None) -> dict:
    kb_text = ""
    for name, kb in [(ta, kb_a), (tb, kb_b)]:
        if kb:
            cf = kb.get("context_factors", {})
            kb_text += f"\n[{name}情境] 期望:{cf.get('tournament_expectation','?')} | 媒体压力:{cf.get('media_pressure','?')}"

    return _call(
        f"""你是赛前情境评估员。{ANTI_HINDSIGHT}
评估维度：
1. 必须赢/可平/可输的动机强度差异（小组赛MD1双方都想赢，差异小；MD3差异大）
2. 休息天数差距（≥2天差距才有影响）
3. 心理包袱：历史失败的阴影（如德国卫冕冠军小组赛出局的包袱）
4. 主场/中立场/敌对环境（比如墨西哥队在美国踢）
5. 教练赛前发布会中的异常表态（自信/紧张信号）
{SCORING_RUBRIC}{_SCHEMA_NOTE}""",
        f"比赛：{ta} vs {tb}（{stage}）\n{kb_text}\n赛前信息：{ctx[:500]}"
    )


# ─── F：战术对位 ─────────────────────────────────────────────────
def agent_F_tactical(ta: str, tb: str, ctx: str,
                     kb_a: dict = None, kb_b: dict = None) -> dict:
    kb_text = ""
    for name, kb in [(ta, kb_a), (tb, kb_b)]:
        if kb:
            tac = kb.get("tactical", {})
            att = tac.get("attack", {})
            dfn = tac.get("defense", {})
            kb_text += f"\n[{name}战术]"
            kb_text += f" 阵型:{tac.get('formation_primary','?')}"
            kb_text += f" | 进攻:{att.get('main_creation_zone','?')} / 核心套路:{att.get('key_pattern_1','?')}"
            kb_text += f" | 防守弱点:{dfn.get('key_weakness','?')}"
            kb_text += f" | 如何破防:{dfn.get('how_to_beat','?')}"
            pr = tac.get("press_resistance", {})
            kb_text += f" | 抗压球能力:{pr.get('can_play_under_press','?')}"

    return _call(
        f"""你是战术对位评估员。{ANTI_HINDSIGHT}
核心问题：这两套打法放在一起，谁的风格在这个具体对阵中占便宜？

必须分析：
1. A队进攻 vs B队防守：A的主要进攻手段能否有效攻破B的防守薄弱点？
2. B队进攻 vs A队防守：B的主要进攻手段是否能利用A的防守漏洞？
3. 阵型/节奏匹配：高位压迫 vs 低位反击哪方更有利？节奏控制谁更占优？
4. 定位球：哪队定位球进攻更威胁？对方定位球防守是否有漏洞？

不是评价谁的战术"先进"，而是谁的具体打法在这个配对中更有利。
{SCORING_RUBRIC}{_SCHEMA_NOTE}""",
        f"比赛：{ta} vs {tb}\n{kb_text}\n赛前信息：{ctx[:500]}"
    )


# ─── G：大赛DNA ──────────────────────────────────────────────────
def agent_G_dna(ta: str, tb: str, ctx: str, stage: str = "",
                kb_a: dict = None, kb_b: dict = None) -> dict:
    kb_text = ""
    for name, kb in [(ta, kb_a), (tb, kb_b)]:
        if kb:
            wch = kb.get("wc_history", {})
            kb_text += f"\n[{name}历史] 2022:{wch.get('2022',{}).get('result','?')} | 2018:{wch.get('2018',{}).get('result','?')}"
            kb_text += f" | 首轮记录:{wch.get('opening_game_record','?')}"
            kb_text += f" | 逆转能力:{wch.get('from_behind_record','?')}"

    is_knockout = stage.lower() not in ("group_stage", "小组赛", "group", "")

    if not is_knockout:
        return _call(
            f"""你是大赛基因评估员（小组赛版本）。{ANTI_HINDSIGHT}
评估维度（小组赛阶段）：
1. 近3届世界杯小组赛出线率（是否经常首轮失常？）
2. 世界杯首战历史表现规律（慢热 vs 开门红型）
3. 对阵实力相当对手时的历史心理状态

注意：小组赛DNA信号弱，confidence 主动设低（不超过6分）。
{SCORING_RUBRIC}{_SCHEMA_NOTE}""",
            f"比赛：{ta} vs {tb}（{stage}）\n{kb_text}\n赛前信息：{ctx[:400]}"
        )
    return _call(
        f"""你是大赛DNA评估员（淘汰赛版本）。{ANTI_HINDSIGHT}
评估维度：
1. 近3届世界杯淘汰赛成绩（克罗地亚式DNA vs 纸老虎型）
2. 落后时的历史翻盘记录（逆境中会不会崩？）
3. 点球大战记录（如有相关历史）
4. 关键战役中个人英雄主义是否出现过？
{SCORING_RUBRIC}{_SCHEMA_NOTE}""",
        f"比赛：{ta} vs {tb}（{stage}）\n{kb_text}\n赛前信息：{ctx[:400]}"
    )


# ─── H：市场赔率校验器（不参与计分）────────────────────────────────
def agent_H_odds(ta: str, tb: str, ctx: str) -> dict:
    result = _call(
        f"""你是赔率信号评估员。{ANTI_HINDSIGHT}
任务：从信息中提取赔率，计算隐含概率，作为校验信号。
赔率格式：美式(+150/-120) → 隐含概率 = 100/(赔率+100) 或 |赔率|/(|赔率|+100)
欧式(2.50) → 隐含概率 = 1/赔率

team_a_score / team_b_score 直接填写 A队胜/B队胜的隐含概率×10
（例：A胜概率55% → team_a_score=5.5，B胜概率30% → team_b_score=3.0，平局=1.5）
若无赔率数据，confidence=2，给5.0/5.0。
{_SCHEMA_NOTE}""",
        f"比赛：{ta} vs {tb}\n赛前信息（含赔率）：{ctx[:600]}"
    )
    result["is_calibrator"] = True
    return result


# ─── 权重配置 ─────────────────────────────────────────────────────
DIMENSION_WEIGHTS = {
    "F_tactical":   0.25,
    "E_context":    0.20,
    "G_dna":        0.18,
    "D_keyplayer":  0.15,
    "B_chemistry":  0.08,
    "A_strength":   0.07,
    "C_form":       0.07,
}

N_FOR_GROUP_STAGE = 7
N_FOR_KNOCKOUT = 7

AGENTS_IN_ORDER = [
    ("F_tactical",  agent_F_tactical),
    ("E_context",   agent_E_context),
    ("G_dna",       agent_G_dna),
    ("D_keyplayer", agent_D_keyplayer),
    ("B_chemistry", agent_B_chemistry),
    ("A_strength",  agent_A_strength),
    ("C_form",      agent_C_form),
]

DIMENSION_LABELS = {
    "A_strength":  "绝对实力",
    "B_chemistry": "球队化学",
    "C_form":      "近期状态",
    "D_keyplayer": "关键球员",
    "E_context":   "情境压力",
    "F_tactical":  "战术对位",
    "G_dna":       "大赛DNA",
}


def run_n_agents(n: int, ta: str, tb: str, ctx: str, stage: str = "",
                 kb_a: dict = None, kb_b: dict = None) -> list[dict]:
    """
    按重要性顺序运行前 n 个维度的 Agent。
    kb_a / kb_b: 两队的知识库数据（来自 team_knowledge_2026.json）
    """
    ordered = sorted(AGENTS_IN_ORDER, key=lambda x: -DIMENSION_WEIGHTS[x[0]])
    results = []
    for key, fn in ordered[:n]:
        try:
            kwargs = {"kb_a": kb_a, "kb_b": kb_b}
            if key in ("E_context", "G_dna"):
                score = fn(ta, tb, ctx, stage, **kwargs)
            else:
                score = fn(ta, tb, ctx, **kwargs)

            score["dimension"] = key
            score["label"] = DIMENSION_LABELS[key]
            score["weight"] = DIMENSION_WEIGHTS[key]
            results.append(score)
        except Exception as e:
            results.append({
                "dimension": key, "label": DIMENSION_LABELS.get(key, key),
                "weight": DIMENSION_WEIGHTS[key],
                "team_a_score": 5.0, "team_b_score": 5.0,
                "confidence": 2.0, "reasoning": f"Error: {e}",
                "key_factors": []
            })
    return results


def run_odds_calibrator(ta: str, tb: str, ctx: str) -> dict:
    return agent_H_odds(ta, tb, ctx)
