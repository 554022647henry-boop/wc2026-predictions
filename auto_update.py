"""
自动更新脚本 — 由 CronCreate 每30分钟调用
1. 从 ESPN API 获取今日比赛结果 → 录入 results.json + tournament_log
2. 检查赛前时间窗口 → 触发 T-24h/12h/2h/30min 完整预测
3. 重新生成 HTML
"""
import json
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 设置 API key
os.environ.setdefault('DEEPSEEK_API_KEY', 'sk-118341cebbbb44858b2b9c19c27fd2b4')

sys.path.insert(0, str(Path(__file__).parent))
import config

import requests
HEADERS = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}

# ─────────────────────────────────────────
# Step 1: 从 ESPN API 抓取最新比赛结果
# ─────────────────────────────────────────

def fetch_and_record_results():
    """获取今日及近3天的比赛结果，自动录入系统。"""
    results_file = Path(config.RESULTS_FILE)
    results_file.parent.mkdir(parents=True, exist_ok=True)
    existing = json.loads(results_file.read_text(encoding='utf-8')) if results_file.exists() else {}

    fixtures = json.loads(Path(config.FIXTURES_FILE).read_text(encoding='utf-8'))
    match_lookup = {m['match_id']: m for m in fixtures.get('matches', [])}

    # 查近3天
    updated = 0
    for delta in range(-1, 3):
        date = (datetime.now() + timedelta(days=delta)).strftime('%Y%m%d')
        url = config.ESPN_API['scoreboard'].format(date=date)
        try:
            r = requests.get(url, headers=HEADERS, timeout=10)
            events = r.json().get('events', [])
        except Exception:
            continue

        for evt in events:
            status = evt.get('status', {}).get('type', {}).get('description', '')
            if status not in ('Full Time', 'Final', 'FT'):
                continue

            comps = evt.get('competitions', [{}])[0]
            competitors = comps.get('competitors', [])
            if len(competitors) < 2:
                continue

            # 识别 team_a / team_b（home 通常是 team_b in our away-at-home format）
            scores = {}
            for c in competitors:
                name = c.get('team', {}).get('displayName', '')
                score = c.get('score', '0')
                ha = c.get('homeAway', 'away')
                scores[name] = {'score': score, 'homeAway': ha}

            # 找到对应的 match_id
            teams = list(scores.keys())
            if len(teams) < 2:
                continue

            # 规范化队名（去除重音/特殊字符，解决 Türkiye→Turkiye, Curaçao→Curacao）
            import unicodedata
            def norm(s):
                return unicodedata.normalize('NFD', s).encode('ascii', 'ignore').decode().lower().strip()

            match_id = None
            team_a_name = team_b_name = None
            for mid, m in match_lookup.items():
                ma, mb = norm(m['team_a']), norm(m['team_b'])
                t0, t1 = norm(teams[0]), norm(teams[1])
                # 双向匹配（含包含关系）
                def fuzzy_match(a, b):
                    return a == b or a in b or b in a
                if fuzzy_match(ma, t0) and fuzzy_match(mb, t1):
                    match_id = mid; team_a_name = m['team_a']; team_b_name = m['team_b']; break
                if fuzzy_match(ma, t1) and fuzzy_match(mb, t0):
                    match_id = mid; team_a_name = m['team_a']; team_b_name = m['team_b']; break

            if not match_id or match_id in existing:
                continue

            # 取比分
            a_score_str = scores.get(teams[0], {}).get('score', '0')
            b_score_str = scores.get(teams[1], {}).get('score', '0')
            try:
                a_goals = int(a_score_str)
                b_goals = int(b_score_str)
            except ValueError:
                continue

            if team_a_name == teams[0]:
                outcome = 'A_WIN' if a_goals > b_goals else ('B_WIN' if b_goals > a_goals else 'DRAW')
                score_str = f'{a_goals}-{b_goals}'
                result_a = 'W' if outcome == 'A_WIN' else ('L' if outcome == 'B_WIN' else 'D')
            else:
                outcome = 'A_WIN' if b_goals > a_goals else ('B_WIN' if a_goals > b_goals else 'DRAW')
                score_str = f'{b_goals}-{a_goals}'
                result_a = 'W' if outcome == 'A_WIN' else ('L' if outcome == 'B_WIN' else 'D')

            existing[match_id] = {
                'outcome': outcome,
                'score': score_str,
                'team_a': team_a_name,
                'team_b': team_b_name,
                'recorded_at': datetime.now().isoformat(),
            }
            updated += 1
            print(f'  [结果] {team_a_name} {score_str} {team_b_name} → {outcome}')

            # 同步更新 tournament_log
            from agents.momentum_agent import add_match_result
            m = match_lookup[match_id]
            add_match_result(team_a_name, team_b_name, m.get('stage','group_stage'),
                             result_a, score_str)

    if updated:
        results_file.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f'[结果] 录入 {updated} 场新结果')
    else:
        print('[结果] 无新结果')

    return updated


# ─────────────────────────────────────────
# Step 2: 检查是否需要触发预测
# ─────────────────────────────────────────

PREDICTION_WINDOWS = {
    24:   'T-24h',
    12:   'T-12h',
    2:    'T-2h',
    0.5:  'T-30min',
}
WINDOW_TOLERANCE_MINUTES = 35  # ±35分钟内触发

def check_and_predict():
    """检查赛程，对进入时间窗口的比赛触发预测。"""
    fixtures = json.loads(Path(config.FIXTURES_FILE).read_text(encoding='utf-8'))
    now = datetime.now()
    triggered = 0

    from agents.collector import run_collection
    from agents.reviewer import review
    from agents.predictor import run_prediction

    for match in fixtures.get('matches', []):
        date_str = match.get('date', '')
        if not date_str or match.get('team_a') == 'TBD':
            continue
        try:
            match_dt = datetime.fromisoformat(date_str)
        except Exception:
            continue

        hours_to_match = (match_dt - now).total_seconds() / 3600

        # 封盘：比赛前10分钟停止
        if hours_to_match < config.CUTOFF_MINUTES_BEFORE_KICKOFF / 60:
            continue

        for hours_before, round_key in PREDICTION_WINDOWS.items():
            tolerance = WINDOW_TOLERANCE_MINUTES / 60
            if abs(hours_to_match - hours_before) > tolerance:
                continue

            pred_file = Path(config.PREDICTIONS_DIR) / match['match_id'] / f'{round_key}_prediction.json'
            if pred_file.exists():
                continue

            label = {
                'T-24h': '赛前24小时', 'T-12h': '赛前12小时',
                'T-2h': '赛前2小时', 'T-30min': '赛前30分钟（封盘）'
            }[round_key]

            print(f'\n[预测] 触发: {match["team_a"]} vs {match["team_b"]} | {label}')
            try:
                raw_file = run_collection(match, round_key, label)
                reviewed = review(match, round_key, label, raw_file)
                run_prediction(match, reviewed, round_key, label)
                triggered += 1
            except Exception as e:
                print(f'  [预测] 失败: {e}')

    if triggered == 0:
        print('[预测] 当前无比赛进入预测窗口')
    return triggered


# ─────────────────────────────────────────
# Step 3: 更新 HTML
# ─────────────────────────────────────────

def update_html():
    from agents.html_updater import update_html as _update
    _update()


# ─────────────────────────────────────────
# 主流程
# ─────────────────────────────────────────

# ─────────────────────────────────────────
# Step 4: 推送到 GitHub Pages（如果有有效 token）
# ─────────────────────────────────────────

def push_to_github_pages():
    """
    把最新的 index.html 推送到 GitHub Pages。
    token 存在 C:/Projects/github/.github_token
    """
    token_file = Path('C:/Projects/github/.github_token')
    if not token_file.exists():
        return False

    token = token_file.read_text(encoding='utf-8').strip()
    if not token or not token.startswith('ghp_'):
        return False

    username = '554022647henry-boop'
    repo = 'wc2026-predictions'
    H = {'Authorization': f'token {token}', 'Accept': 'application/vnd.github.v3+json'}

    import base64, requests as req

    # 验证 token
    r = req.get('https://api.github.com/user', headers=H, timeout=10)
    if r.status_code != 200:
        print(f'[GitHub] token 无效 ({r.status_code})，跳过推送')
        return False

    # 读 HTML
    html_bytes = Path(config.HTML_FILE).read_bytes()
    encoded = base64.b64encode(html_bytes).decode()

    # 获取当前文件 SHA
    r2 = req.get(f'https://api.github.com/repos/{username}/{repo}/contents/index.html',
                 headers=H, timeout=10)
    sha = r2.json().get('sha', '') if r2.status_code == 200 else ''

    # 推送
    r3 = req.put(
        f'https://api.github.com/repos/{username}/{repo}/contents/index.html',
        headers=H,
        json={'message': f'⚽ Auto-update {datetime.now().strftime("%Y-%m-%d %H:%M")}',
              'content': encoded, **({'sha': sha} if sha else {})},
        timeout=30
    )

    if r3.status_code in (200, 201):
        print(f'[GitHub] 推送成功 → https://{username}.github.io/{repo}/')
        return True
    else:
        print(f'[GitHub] 推送失败: {r3.status_code} {r3.text[:80]}')
        return False


if __name__ == '__main__':
    print(f'\n{"="*50}')
    print(f'自动更新 {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}')
    print(f'{"="*50}')

    print('\n[Step 1] 获取最新比赛结果...')
    fetch_and_record_results()

    # [Step 2] 预测窗口（T-24h/T-12h/T-2h/T-30min）已停用
    # 现在只使用初始预测，不再自动触发赛前更新预测

    print('\n[Step 2] 更新 HTML...')
    update_html()

    print('\n[Step 3] 推送到 GitHub Pages...')
    push_to_github_pages()

    print('\n[完成]')
