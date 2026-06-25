"""
build_knowledge_base.py
为2026世界杯全部48支参赛队建立知识库
每队包含：阵型/战术/大名单/关键球员/历史/化学等信息
供7个Indicator Agent使用
"""
import json
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, str(Path(__file__).parent))
import config

client = config.make_client()

TEAMS = [
    "Algeria", "Argentina", "Australia", "Austria", "Belgium",
    "Bosnia and Herzegovina", "Brazil", "Canada", "Cape Verde",
    "Colombia", "Croatia", "Curacao", "Czechia", "DR Congo",
    "Ecuador", "Egypt", "England", "France", "Germany", "Ghana",
    "Haiti", "Iran", "Iraq", "Ivory Coast", "Japan", "Jordan",
    "Mexico", "Morocco", "Netherlands", "New Zealand", "Norway",
    "Panama", "Paraguay", "Portugal", "Qatar", "Saudi Arabia",
    "Scotland", "Senegal", "South Africa", "South Korea",
    "Spain", "Sweden", "Switzerland", "Tunisia", "Turkiye",
    "United States", "Uruguay", "Uzbekistan"
]

SCHEMA_EXAMPLE = """{
  "TeamName": {
    "basics": {
      "fifa_ranking": <整数>,
      "squad_market_value_eur": <整数，欧元>,
      "confederation": "<UEFA/CONMEBOL/CAF/AFC/CONCACAF/OFC>",
      "coach": "<全名>",
      "coach_tenure_since": "<YYYY-MM>",
      "coach_wc_experience": "<描述>",
      "coach_style_summary": "<2-3句，核心战术哲学>"
    },
    "squad": {
      "squad_26": [
        {"name": "<全名>", "pos": "<GK/CB/RB/LB/CDM/CM/CAM/RW/LW/CF>", "club": "<俱乐部>", "age": <整数>}
        // 列出全部26名球员
      ],
      "expected_xi": ["<11名球员姓名，按4-3-3或实际阵型顺序>"],
      "formation_xi": "<如4-3-3>",
      "captain": "<队长姓名>"
    },
    "tactical": {
      "formation_primary": "<如4-3-3>",
      "formation_alternative": "<备用阵型>",
      "attack": {
        "build_up_style": "<出球风格，2-3句>",
        "width": "<宽度利用方式>",
        "main_creation_zone": "<主要进攻区域>",
        "key_pattern_1": "<核心进攻套路1>",
        "key_pattern_2": "<核心进攻套路2>",
        "set_piece_offense": "<定位球进攻习惯>",
        "avg_goals_per_game_recent": <数字>,
        "attack_weakness": "<进攻短板>"
      },
      "defense": {
        "defensive_block": "<防守阵型/站位>",
        "press_trigger": "<逼抢触发条件>",
        "defensive_line_height": "<高/中/低位>",
        "key_weakness": "<防守核心弱点>",
        "aerial_strength": "<制空能力>",
        "set_piece_defense": "<定位球防守方式>",
        "how_to_beat": "<如何有效攻破此防线>"
      },
      "physical_profile": {
        "avg_height_cm": <整数>,
        "pace_rating": "<快/中/慢 + 说明>",
        "physicality": "<对抗能力描述>"
      },
      "press_resistance": {
        "can_play_under_press": "<能力描述>",
        "weakness": "<在压迫下的弱点>"
      }
    },
    "key_players": [
      {
        "name": "<全名>",
        "pos": "<位置>",
        "club": "<俱乐部>",
        "age": <整数>,
        "role": "<在球队体系中的具体作用>",
        "form_2026": "<备战期状态>",
        "injury_risk": "<高/中/低>",
        "absence_impact": "<若缺阵对球队的影响>",
        "neutralize_with": "<对方如何针对此球员>"
      }
      // 列出3-5名关键球员
    ],
    "chemistry": {
      "core_combination_years": <整数，核心阵容稳定年数>,
      "club_clusters": "<是否有同一俱乐部的多人组合>",
      "system_stability": "<体系稳定程度>",
      "locker_room": "<更衣室气氛，是否有已知矛盾>",
      "youth_vs_exp_balance": "<老中青结构描述>"
    },
    "form_recent": [
      {"date": "YYYY-MM-DD", "opponent": "<对手>", "result": "<如2-1>", "type": "<Friendly/WCQ/Nations/etc>", "note": "<简短备注>"}
      // 近5场
    ],
    "wc_history": {
      "2022": {"result": "<结果>", "detail": "<简述>", "group": "<小组及排名>"},
      "2018": {"result": "<结果>", "detail": "<简述>"},
      "2014": {"result": "<结果>", "detail": "<简述>"},
      "opening_game_record": "<近几届世界杯首轮成绩规律>",
      "from_behind_record": "<落后追分/逆转能力>",
      "big_game_dna_note": "<大赛关键场次表现特点>"
    },
    "context_factors": {
      "group": "<A-L>",
      "tournament_expectation": "<夺冠热门/出线目标/黑马/陪跑>",
      "media_pressure": "<高/中/低>",
      "coach_big_game_record": "<主帅在大赛中的表现记录>"
    }
  }
}"""

BATCH_SIZE = 3

def build_prompt(teams_batch: list[str]) -> str:
    teams_str = "、".join(teams_batch)
    return f"""你是资深足球分析师，熟悉2026年世界杯（2026年6月在美国/加拿大/墨西哥举行）所有参赛队。

请为以下 {len(teams_batch)} 支球队生成详细的球队知识库数据：
{teams_str}

请严格按照以下JSON Schema格式输出，每队包含完整信息：

Schema格式说明：
{SCHEMA_EXAMPLE}

要求：
1. squad_26 必须列出所有26名球员（姓名/位置/俱乐部/年龄）
2. expected_xi 必须是具体的11名球员姓名
3. key_players 必须包含3-5名关键球员，每人都要有 neutralize_with（对方如何针对）
4. form_recent 必须有近5场比赛结果（2026年的友谊赛/预选赛）
5. 所有文字字段用中文，球员姓名写英文全名
6. tactical 部分必须具体，不能写"高位压迫"这类空话，要写清楚触发条件、执行方式、具体弱点
7. 如某字段数据不确定，标注"（推测）"但仍要给出合理估值

只输出JSON，不要任何解释文字。格式：
{{
  "TeamA": {{...}},
  "TeamB": {{...}},
  ...
}}"""


def call_deepseek(prompt: str, batch_label: str) -> dict:
    print(f"  [API] 调用DeepSeek: {batch_label} ...")
    try:
        resp = client.messages.create(
            model=config.MODEL,
            max_tokens=16000,
            messages=[{"role": "user", "content": prompt}]
        )
        text = resp.content[0].text.strip()

        # 提取JSON
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

        # 找到第一个{到最后一个}
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            print(f"  [错误] 未找到JSON内容")
            return {}

        data = json.loads(text[start:end])
        print(f"  [OK] 获取到 {len(data)} 支队数据")
        return data
    except json.JSONDecodeError as e:
        print(f"  [错误] JSON解析失败: {e}")
        # 保存原始输出用于调试
        Path(f"data/debug_batch_{batch_label}.txt").write_text(text, encoding='utf-8')
        return {}
    except Exception as e:
        print(f"  [错误] API调用失败: {e}")
        return {}


def main():
    output_file = Path("data/team_knowledge_2026.json")

    # 加载已有数据（断点续跑）
    existing = {}
    if output_file.exists():
        existing = json.loads(output_file.read_text(encoding='utf-8'))
        print(f"[续跑] 已有 {len(existing)} 支队数据")

    # 过滤掉已有的队
    teams_todo = [t for t in TEAMS if t not in existing]
    print(f"[任务] 需要生成 {len(teams_todo)} 支队（共{len(TEAMS)}支）")

    if not teams_todo:
        print("[完成] 所有队已生成！")
        return existing

    # 分批处理
    batches = [teams_todo[i:i+BATCH_SIZE] for i in range(0, len(teams_todo), BATCH_SIZE)]
    print(f"[计划] {len(batches)} 批，每批{BATCH_SIZE}队\n")

    for i, batch in enumerate(batches, 1):
        label = f"批次{i}({'+'.join(batch[:2])}...)"
        print(f"\n{'='*50}")
        print(f"[批次 {i}/{len(batches)}] {', '.join(batch)}")

        prompt = build_prompt(batch)
        result = call_deepseek(prompt, label)

        if result:
            existing.update(result)
            # 每批保存一次（防止中途失败丢数据）
            output_file.parent.mkdir(parents=True, exist_ok=True)
            output_file.write_text(
                json.dumps(existing, ensure_ascii=False, indent=2),
                encoding='utf-8'
            )
            print(f"  [保存] 累计 {len(existing)} 支队 → {output_file}")
        else:
            print(f"  [跳过] 批次{i}失败，可重新运行续跑")

        if i < len(batches):
            time.sleep(2)  # 避免API限速

    # 最终统计
    print(f"\n{'='*50}")
    print(f"[完成] 知识库已生成: {len(existing)}/{len(TEAMS)} 支队")
    missing = [t for t in TEAMS if t not in existing]
    if missing:
        print(f"[缺失] {missing}")

    return existing


if __name__ == "__main__":
    kb = main()

    # 打印一支队作为样本检验
    if "Netherlands" in kb:
        ned = kb["Netherlands"]
        print(f"\n--- 荷兰样本检验 ---")
        print(f"教练: {ned.get('basics',{}).get('coach')}")
        print(f"阵型: {ned.get('tactical',{}).get('formation_primary')}")
        xi = ned.get('squad',{}).get('expected_xi',[])
        print(f"首发: {', '.join(xi[:5])}...")
        kp = ned.get('key_players',[])
        print(f"关键球员: {', '.join(p['name'] for p in kp[:3])}")
