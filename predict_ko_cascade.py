"""
淘汰赛链式预测（R32 → 冠军）
根据本轮 AI 预测结果决定晋级队伍，逐轮推进。
"""
import json, sys, pathlib, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, str(pathlib.Path(__file__).parent))

import config
from agents.predictor import run_prediction_v2

PRED_DIR = pathlib.Path(config.PREDICTIONS_DIR)
FIXTURES_FILE = pathlib.Path(config.FIXTURES_FILE)
RESULTS_FILE = pathlib.Path(config.RESULTS_FILE)
ROUND_KEY = 'initial'
ROUND_LABEL = '初始预测'

# ── 淘汰赛对阵树 ──────────────────────────────────────────
# 每场比赛晋级后 feed 到下一轮的哪个比赛、哪个 side (A/B)
BRACKET_TREE = {
    # ============================================================
    # ★ 以下对阵树已按 fixtures.json 的 note 字段逐场校对 ★
    #   R32→R16, R16→QF, QF→SF 三步校验通过，确保与 FIFA 一致。
    #   修改前请先确认 fixtures.json 对应 note 未改。
    # ============================================================
    # R32 → R16  (fixtures.json notes: M89~M96)
    'WC2026_R32_01': {'feeds': 'WC2026_R16_02', 'side': 'A'},  # 已完赛 Canada 1-0
    'WC2026_R32_02': {'feeds': 'WC2026_R16_03', 'side': 'A'},
    'WC2026_R32_03': {'feeds': 'WC2026_R16_02', 'side': 'B'},
    'WC2026_R32_04': {'feeds': 'WC2026_R16_01', 'side': 'A'},
    'WC2026_R32_05': {'feeds': 'WC2026_R16_03', 'side': 'B'},
    'WC2026_R32_06': {'feeds': 'WC2026_R16_04', 'side': 'A'},
    'WC2026_R32_07': {'feeds': 'WC2026_R16_01', 'side': 'B'},
    'WC2026_R32_08': {'feeds': 'WC2026_R16_06', 'side': 'B'},
    'WC2026_R32_09': {'feeds': 'WC2026_R16_06', 'side': 'A'},
    'WC2026_R32_10': {'feeds': 'WC2026_R16_04', 'side': 'B'},
    'WC2026_R32_11': {'feeds': 'WC2026_R16_05', 'side': 'B'},
    'WC2026_R32_12': {'feeds': 'WC2026_R16_05', 'side': 'A'},
    'WC2026_R32_13': {'feeds': 'WC2026_R16_08', 'side': 'A'},
    'WC2026_R32_14': {'feeds': 'WC2026_R16_07', 'side': 'B'},
    'WC2026_R32_15': {'feeds': 'WC2026_R16_07', 'side': 'A'},
    'WC2026_R32_16': {'feeds': 'WC2026_R16_08', 'side': 'B'},
    # R16 → QF  (fixtures.json notes: M97 Foxborough, M99 Miami,
    #             M98 Inglewood, M100 Kansas City)
    'WC2026_R16_01': {'feeds': 'WC2026_QF_01', 'side': 'A'},
    'WC2026_R16_02': {'feeds': 'WC2026_QF_01', 'side': 'B'},
    'WC2026_R16_03': {'feeds': 'WC2026_QF_03', 'side': 'A'},
    'WC2026_R16_04': {'feeds': 'WC2026_QF_03', 'side': 'B'},
    'WC2026_R16_05': {'feeds': 'WC2026_QF_02', 'side': 'A'},
    'WC2026_R16_06': {'feeds': 'WC2026_QF_02', 'side': 'B'},
    'WC2026_R16_07': {'feeds': 'WC2026_QF_04', 'side': 'A'},
    'WC2026_R16_08': {'feeds': 'WC2026_QF_04', 'side': 'B'},
    # QF → SF  (fixtures.json notes: M101 Dallas, M102 Atlanta)
    'WC2026_QF_01': {'feeds': 'WC2026_SF_01', 'side': 'A'},
    'WC2026_QF_02': {'feeds': 'WC2026_SF_01', 'side': 'B'},
    'WC2026_QF_03': {'feeds': 'WC2026_SF_02', 'side': 'A'},
    'WC2026_QF_04': {'feeds': 'WC2026_SF_02', 'side': 'B'},
    # SF → Final
    'WC2026_SF_01': {'feeds': 'WC2026_FINAL', 'side': 'A'},
    'WC2026_SF_02': {'feeds': 'WC2026_FINAL', 'side': 'B'},
}

# 轮次排序
ROUND_ORDER = ['round_of_32', 'round_of_16', 'quarterfinal', 'semifinal', 'third_place', 'final']
STAGE_LABEL = {
    'round_of_32': '32强', 'round_of_16': '16强',
    'quarterfinal': '8强', 'semifinal': '4强',
    'third_place': '季军赛', 'final': '决赛',
}


def load_prediction(mid):
    """读取某场比赛的预测。"""
    f = PRED_DIR / mid / f'{ROUND_KEY}_prediction.json'
    if f.exists():
        return json.loads(f.read_text(encoding='utf-8'))
    return None


def get_winner(mid, pred):
    """从预测结果中提取胜者队名。"""
    if not pred:
        return None
    out = pred.get('output', {})
    pred_str = out.get('prediction', '')
    # 预测格式: "Brazil胜" 或 "Netherlands胜"
    if pred_str.endswith('胜'):
        name = pred_str[:-1]
        return name
    return None


def load_fixtures():
    data = json.loads(FIXTURES_FILE.read_text(encoding='utf-8'))
    return {m['match_id']: m for m in data['matches']}


def run_predict(mid, team_a, team_b, stage):
    """预测一场比赛，返回预测结果。"""
    match_info = {
        'match_id': mid,
        'team_a': team_a,
        'team_b': team_b,
        'stage': stage,
    }
    pred = run_prediction_v2(match_info, ROUND_KEY, ROUND_LABEL)
    time.sleep(0.5)
    return pred


def main():
    fixtures = load_fixtures()
    results = {}
    if RESULTS_FILE.exists():
        r = json.loads(RESULTS_FILE.read_text(encoding='utf-8'))
        results = {k: v for k, v in r.items() if not k.startswith('_')}

    # ── 从 results.json + fixtures 自动确定实际胜者 ──
    actual_winners = {}
    for mid, res in results.items():
        match = fixtures.get(mid)
        if not match:
            continue
        stage = match.get('stage', '')
        if stage not in ('round_of_32',):
            continue
        outcome = res.get('outcome', '')
        if outcome == 'A_WIN':
            actual_winners[mid] = match['team_a']
        elif outcome == 'B_WIN':
            actual_winners[mid] = match['team_b']
    # 硬编码在 fixture 里的结果
    for mid, m in fixtures.items():
        if m.get('result') and m.get('stage') == 'round_of_32':
            if mid not in actual_winners:
                # e.g. Canada 1-0 South Africa
                actual_winners[mid] = m['team_a']

    # ── 收集所有预测结果（包括之前跑过的） ──
    predicted_winners = {}  # mid → winner team name

    # ── 按轮次顺序推进 ──
    # 只需预测的场次（按对阵树自动确定）
    to_predict = set()

    # 先确定 R32 哪些需要预测
    for mid, info in BRACKET_TREE.items():
        if not info:  # 3RD, FINAL 没有 feeds
            continue
        stage = fixtures.get(mid, {}).get('stage', '')
        if stage != 'round_of_32':
            continue
        match = fixtures.get(mid)
        if not match:
            continue
        ta, tb = match['team_a'], match['team_b']
        if 'TBD' in (ta, tb):
            continue
        if match.get('result'):  # 已有内联结果
            continue
        if mid in results:  # 已完赛
            continue
        if mid in predicted_winners:
            continue
        if load_prediction(mid):
            continue
        to_predict.add(mid)

    # ── 如果有要预测的 R32，先跑 ──
    if to_predict:
        print(f'\n{"="*60}')
        print(f'【第1轮】32强赛：{len(to_predict)} 场')
        print(f'{"="*60}')
        for mid in sorted(to_predict):
            match = fixtures[mid]
            ta, tb = match['team_a'], match['team_b']
            print(f'\n  {ta} vs {tb} ({mid})')
            try:
                pred = run_predict(mid, ta, tb, 'round_of_32')
                winner = get_winner(mid, pred)
                if winner:
                    predicted_winners[mid] = winner
                    print(f'  → {winner} 晋级')
            except Exception as e:
                print(f'  ✗ 失败: {e}')
                import traceback; traceback.print_exc()

    # ── 重新加载所有已有预测 ──
    for mid in BRACKET_TREE:
        if mid not in predicted_winners:
            pred = load_prediction(mid)
            w = get_winner(mid, pred)
            if w:
                predicted_winners[mid] = w
        if mid in actual_winners:
            predicted_winners[mid] = actual_winners[mid]

    # 确认 R32 全部有预测结果
    all_r32_done = True
    for mid in BRACKET_TREE:
        match = fixtures.get(mid)
        if not match or match.get('stage') != 'round_of_32':
            continue
        if match.get('result') or mid in results:
            continue  # 已完赛
        if 'TBD' in (match.get('team_a',''), match.get('team_b','')):
            continue
        if mid not in predicted_winners:
            pred = load_prediction(mid)
            w = get_winner(mid, pred)
            if w:
                predicted_winners[mid] = w
            else:
                print(f'  ⚠️ {match["team_a"]} vs {match["team_b"]} ({mid}) 还没有预测结果')
                all_r32_done = False

    if not all_r32_done:
        print('\n⚠️ 部分 R32 比赛还没有预测，无法继续推进。请先完成 R32 预测。')
        return

    # ── 打印 R32 预测结果 ──
    print(f'\n{"="*60}')
    print(f'【32强赛预测结果】')
    print(f'{"="*60}')
    for mid in sorted(BRACKET_TREE):
        match = fixtures.get(mid)
        if not match or match.get('stage') != 'round_of_32':
            continue
        ta, tb = match['team_a'], match['team_b']
        w = predicted_winners.get(mid, '?')
        print(f'  {ta} vs {tb} → {w} 晋级')

    # ── 逐轮推进：R16 → QF → SF → Final ──
    prediction_path = {}  # mid → {winner, pred}
    prediction_path.update({mid: {'winner': predicted_winners[mid]} for mid in predicted_winners})

    # 为 R16_02 固定 team_a (Canada)
    canada_won = predicted_winners.get('WC2026_R32_01', 'Canada')  # Canada 已确定

    for stage_key in ['round_of_16', 'quarterfinal', 'semifinal']:
        stage_matches = [mid for mid, info in BRACKET_TREE.items()
                         if fixtures.get(mid, {}).get('stage') == stage_key]

        if not stage_matches:
            continue

        print(f'\n{"="*60}')
        print(f'【{STAGE_LABEL[stage_key]}】{len(stage_matches)} 场')
        print(f'{"="*60}')

        has_all_feeds = True
        for mid in stage_matches:
            match = fixtures.get(mid, {})
            info = BRACKET_TREE.get(mid, {})

            # 找到 feeder 比赛的 winner
            # 需要从 BRACKET_TREE 反向查找哪些比赛的 feeds=mid
            feeders = [fm for fm, fi in BRACKET_TREE.items()
                       if fi.get('feeds') == mid]

            winner_a = None
            winner_b = None
            for fm in feeders:
                fi = BRACKET_TREE.get(fm, {})
                f_winner = prediction_path.get(fm, {}).get('winner')
                if f_winner:
                    if fi.get('side') == 'A':
                        winner_a = f_winner
                    elif fi.get('side') == 'B':
                        winner_b = f_winner

            # 特例处理：已有实际结果的队伍
            if mid == 'WC2026_R16_02':
                # team_a = Canada (固定), team_b = R32-03 winner
                winner_a = canada_won if not winner_a else winner_a

            if not winner_a or not winner_b:
                feeders_str = '、'.join(fm for fm in feeders)
                print(f'  ⏳ {mid}: 等待对阵确定 ({feeders_str})')
                has_all_feeds = False
                continue

            # 检查是否已有预测文件
            existing = load_prediction(mid)
            if existing:
                w = get_winner(mid, existing)
                prediction_path[mid] = {'winner': w, 'pred': existing}
                print(f'  ✅ {mid}: {winner_a} vs {winner_b} (已有预测 → {w})')
                continue

            # 预测
            print(f'  🔮 {mid}: {winner_a} vs {winner_b}')
            try:
                pred = run_predict(mid, winner_a, winner_b, stage_key)
                winner = get_winner(mid, pred)
                prediction_path[mid] = {'winner': winner, 'pred': pred}
                print(f'  → {winner} 晋级')
            except Exception as e:
                print(f'  ✗ 失败: {e}')

    # ── 季军赛（SF 败者 vs SF 败者）──
    print(f'\n{"="*60}')
    print(f'【季军赛】')
    print(f'{"="*60}')
    sf1_winner = prediction_path.get('WC2026_SF_01', {}).get('winner')
    sf2_winner = prediction_path.get('WC2026_SF_02', {}).get('winner')

    # 季军赛是 SF 的败者（目前我们没存败者，但可以从 fixtures.json 的 TBD TBD 结构来看）
    # 暂不预测季军赛，因为需要知道 SF 败者

    # ── 决赛 ──
    print(f'\n{"="*60}')
    print(f'【决赛】')
    print(f'{"="*60}')

    if sf1_winner and sf2_winner:
        existing = load_prediction('WC2026_FINAL')
        if existing:
            w = get_winner('WC2026_FINAL', existing)
            prediction_path['WC2026_FINAL'] = {'winner': w, 'pred': existing}
        else:
            print(f'  🔮 {sf1_winner} vs {sf2_winner}')
            try:
                pred = run_predict('WC2026_FINAL', sf1_winner, sf2_winner, 'final')
                winner = get_winner('WC2026_FINAL', pred)
                prediction_path['WC2026_FINAL'] = {'winner': winner, 'pred': pred}
                print(f'  🏆 冠军: {winner}')
            except Exception as e:
                print(f'  ✗ 失败: {e}')

    # ── 打印完整冠军路径 ──
    print(f'\n{"="*60}')
    print(f'🏆 【完整冠军预测路径】')
    print(f'{"="*60}')

    for stage_key in ['round_of_32', 'round_of_16', 'quarterfinal', 'semifinal', 'final']:
        matches_in_stage = [mid for mid in sorted(BRACKET_TREE)
                            if fixtures.get(mid, {}).get('stage') == stage_key]
        if not matches_in_stage:
            continue
        print(f'\n--- {STAGE_LABEL[stage_key]} ---')
        for mid in matches_in_stage:
            match = fixtures.get(mid, {})
            p = prediction_path.get(mid, {})
            w = p.get('winner', '?')
            ta = match.get('team_a', 'TBD')
            tb = match.get('team_b', 'TBD')
            if 'TBD' not in (ta, tb) or w != '?':
                print(f'  {ta} vs {tb} → {w}')

    # ── 更新 HTML ──
    print(f'\n{"="*60}')
    print('更新 HTML...')
    from agents.html_updater import update_html
    update_html()

    print(f'\n{"="*60}')
    print(f'全部完成！完整预测路径如上。')
    print(f'{"="*60}')


if __name__ == '__main__':
    main()
