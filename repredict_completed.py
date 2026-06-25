"""
对已完赛比赛用新系统重新预测（盲预测，不传入赛果）
用于验证v0.5系统的准确率提升效果
"""
import json, sys, time
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, str(Path(__file__).parent))
import config
from agents.collector import run_collection
from agents.reviewer import review
from agents.predictor import run_prediction

results   = json.loads(Path(config.RESULTS_FILE).read_text(encoding='utf-8'))
fixtures  = json.loads(Path(config.FIXTURES_FILE).read_text(encoding='utf-8'))
match_lkp = {m['match_id']: m for m in fixtures['matches']}

# 只处理有结果但没有(新)初始预测的比赛
todo = []
for mid in results:
    pred = Path(config.PREDICTIONS_DIR) / mid / 'initial_prediction.json'
    if not pred.exists():
        m = match_lkp.get(mid)
        if m and m.get('team_a') != 'TBD':
            todo.append(m)

print(f'\n{"="*60}')
print(f'盲预测验证  共 {len(todo)} 场')
print(f'{"="*60}\n')

errors, ok = [], 0
for i, match in enumerate(todo, 1):
    mid = match['match_id']
    ta, tb = match['team_a'], match['team_b']
    r = results[mid]
    print(f'\n[{i}/{len(todo)}] {ta} vs {tb}')
    print(f'  实际结果: {r["score"]} ({r["outcome"]}) — 预测系统不可见')
    try:
        raw  = run_collection(match, 'initial', '初始预测')
        rev  = review(match, 'initial', '初始预测', raw)
        pred = run_prediction(match, rev, 'initial', '初始预测')
        ok  += 1
        print(f'  → 预测: {pred["output"]["prediction"]} ({pred["output"]["confidence"]})')
    except Exception as e:
        print(f'  [FAIL] {e}')
        errors.append((mid, str(e)))
    time.sleep(1)

# ── 汇总准确率 ──────────────────────────────────────────────
print(f'\n{"="*60}')
print(f'新系统预测完成: {ok}/{len(todo)}')
print(f'\n{"="*60}')
print('准确率对比:')
print(f'{"比赛":<35} {"实际":<12} {"新预测":<15} {"旧预测":<15} {"新":<4} {"旧":<4}')
print('-'*85)

new_correct = old_correct = 0
for mid, r in sorted(results.items()):
    ta, tb = r['team_a'], r['team_b']
    actual = r['outcome']
    score  = r['score']

    new_file = Path(config.PREDICTIONS_DIR) / mid / 'initial_prediction.json'
    old_file = Path(config.PREDICTIONS_DIR) / mid / 'initial_prediction.json.v1bak'

    new_pred = old_pred = '(无)'
    new_ok   = old_ok   = '—'

    def chk(pred_str, outcome, a, b):
        return (outcome=='A_WIN' and a in pred_str) or \
               (outcome=='B_WIN' and b in pred_str) or \
               (outcome=='DRAW' and '平局' in pred_str)

    if new_file.exists():
        p = json.loads(new_file.read_text(encoding='utf-8'))
        new_pred = f"{p['output']['prediction']}({p['output']['confidence']})"
        new_ok   = '✅' if chk(new_pred, actual, ta, tb) else '❌'
        if new_ok == '✅': new_correct += 1

    if old_file.exists():
        p = json.loads(old_file.read_text(encoding='utf-8'))
        old_pred = f"{p['output']['prediction']}({p['output']['confidence']})"
        old_ok   = '✅' if chk(old_pred, actual, ta, tb) else '❌'
        if old_ok == '✅': old_correct += 1

    label = f'{ta} {score} {tb}'
    print(f'{label:<35} {actual:<12} {new_pred:<15} {old_pred:<15} {new_ok:<4} {old_ok:<4}')

total = sum(1 for mid in results if (Path(config.PREDICTIONS_DIR)/mid/'initial_prediction.json.v1bak').exists())
print(f'\n新系统: {new_correct}/{total} = {new_correct/total*100:.1f}%')
print(f'旧系统: {old_correct}/{total} = {old_correct/total*100:.1f}%')
print(f'变化:   {"+" if new_correct>=old_correct else ""}{new_correct-old_correct} 场')
