"""
批量重新预测：对所有未完赛比赛重新用 7-Agent 系统预测。
- 已有实际结果的比赛跳过
- 已有预测文件的比赛跳过（断点续跑）
"""
import json, pathlib, time, sys, os
from datetime import datetime

# 强制 stdout utf-8，避免 Windows GBK 崩溃
if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import config
from agents.predictor import run_prediction_v2  # 新版：KB v2 + ESPN实时，无DeepSeek补充

FIXTURES_FILE = pathlib.Path(config.FIXTURES_FILE)
RESULTS_FILE  = pathlib.Path(config.RESULTS_FILE)
PRED_DIR      = pathlib.Path(config.PREDICTIONS_DIR)
ROUND_KEY     = 'initial'
ROUND_LABEL   = '初始预测'

# ── 加载数据 ──────────────────────────────────────────────────────
fixtures = json.loads(FIXTURES_FILE.read_text(encoding='utf-8'))
results  = {}
if RESULTS_FILE.exists():
    r = json.loads(RESULTS_FILE.read_text(encoding='utf-8'))
    results = {k: v for k, v in r.items() if not k.startswith('_')}

# ── 筛选需要预测的比赛（无结果 且 无预测文件）───────────────────────
to_predict = []
skip_done  = 0
skip_result = 0

for match in fixtures['matches']:
    if match.get('stage') != 'group_stage':
        continue
    mid = match['match_id']
    if mid in results:
        skip_result += 1
        continue
    pred_file = PRED_DIR / mid / f'{ROUND_KEY}_prediction.json'
    if pred_file.exists():
        skip_done += 1   # 已预测过（断点续跑）
        continue
    to_predict.append(match)

total = len(to_predict)
print(f'\n{"="*60}')
print(f'批量重新预测  {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
print(f'需要预测: {total} 场')
print(f'跳过(已完赛): {skip_result} 场  |  跳过(已预测): {skip_done} 场')
print(f'{"="*60}\n')

if total == 0:
    print('全部已完成，无需预测。')
    sys.exit(0)

errors = []

for i, match in enumerate(to_predict, 1):
    mid = match['match_id']
    ta  = match['team_a']
    tb  = match['team_b']
    print(f'\n[{i}/{total}] {ta} vs {tb}  ({mid})')
    try:
        run_prediction_v2(match, ROUND_KEY, ROUND_LABEL)
        print(f'  [OK] 完成')
    except Exception as e:
        print(f'  [FAIL] 失败: {e}')
        import traceback; traceback.print_exc()
        errors.append((mid, str(e)))
    time.sleep(0.5)

# ── 汇报 ─────────────────────────────────────────────────────────
print(f'\n{"="*60}')
print(f'预测完成: {total - len(errors)}/{total} 成功')
if errors:
    print(f'失败 {len(errors)} 场:')
    for mid, err in errors:
        print(f'  {mid}: {err}')
print(f'{"="*60}')

# ── Git 批量存档（不可篡改时间戳）────────────────────────────────────
print('\n[Step 1] Git 存档预测文件...')
import subprocess
try:
    # 把所有新预测文件一次性 commit
    subprocess.run(['git', 'add', 'data/predictions/'], check=True, capture_output=True)
    commit_msg = f'[批量预测存档] 7-Agent 初始预测 {total - len(errors)}/{total} 场 {datetime.now().strftime("%Y-%m-%d %H:%M")}'
    result_git = subprocess.run(
        ['git', 'commit', '-m', commit_msg, '--no-verify'],
        capture_output=True, text=True, encoding='utf-8', errors='replace'
    )
    if result_git.returncode == 0:
        token_file_git = pathlib.Path('C:/Projects/github/.github_token')
        if token_file_git.exists():
            token_git = token_file_git.read_text(encoding='utf-8').strip()
            remote_url = f'https://{token_git}@github.com/554022647henry-boop/wc2026-predictions.git'
            push_result = subprocess.run(
                ['git', 'push', remote_url, 'main'],
                capture_output=True, text=True, encoding='utf-8', errors='replace'
            )
            if push_result.returncode == 0:
                print('[Git] 存档推送成功 - GitHub 时间戳已锁定')
            else:
                print(f'[Git] commit 成功但 push 失败: {push_result.stderr[:100]}')
        else:
            print('[Git] commit 成功，未 push（无 token）')
    else:
        print(f'[Git] commit 失败: {result_git.stderr[:100]}')
except Exception as e:
    print(f'[Git] 存档失败（不影响主流程）: {e}')

# ── 更新 HTML ─────────────────────────────────────────────────────
print('\n[Step 2] 更新 HTML...')
from agents.html_updater import update_html
update_html()

# ── 推送 GitHub Pages ─────────────────────────────────────────────
print('[Step 3] 推送 GitHub Pages...')
import requests, base64
from pathlib import Path

token_file = Path('C:/Projects/github/.github_token')
if token_file.exists():
    token = token_file.read_text(encoding='utf-8').strip()
    if token.startswith('ghp_'):
        username = '554022647henry-boop'
        repo     = 'wc2026-predictions'
        H = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}
        html_bytes = Path(config.HTML_FILE).read_bytes()
        encoded    = base64.b64encode(html_bytes).decode()
        r2  = requests.get(
            f'https://api.github.com/repos/{username}/{repo}/contents/index.html',
            headers=H, timeout=10)
        sha = r2.json().get('sha', '') if r2.status_code == 200 else ''
        r3  = requests.put(
            f'https://api.github.com/repos/{username}/{repo}/contents/index.html',
            headers=H,
            json={'message': f'7-Agent 全量重新预测 {datetime.now().strftime("%Y-%m-%d %H:%M")}',
                  'content': encoded, **({'sha': sha} if sha else {})},
            timeout=30
        )
        if r3.status_code in (200, 201):
            print(f'[推送成功] https://{username}.github.io/{repo}/')
        else:
            print(f'[推送失败] {r3.status_code}')

print('\n[全部完成]')
