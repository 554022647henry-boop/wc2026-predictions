"""
HTML 更新器 — 双 Tab 设计
Tab 1: 按小组（Groups）
Tab 2: 按日期（Schedule，体育 APP 风格）
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

# ─────────────────────────────────────────
# 数据加载
# ─────────────────────────────────────────

FLAGS = {
    'Mexico':'🇲🇽','South Africa':'🇿🇦','South Korea':'🇰🇷','Czechia':'🇨🇿',
    'Canada':'🇨🇦','Bosnia and Herzegovina':'🇧🇦','Qatar':'🇶🇦','Switzerland':'🇨🇭',
    'Brazil':'🇧🇷','Morocco':'🇲🇦','Haiti':'🇭🇹','Scotland':'🏴󠁧󠁢󠁳󠁣󠁴󠁿',
    'United States':'🇺🇸','Paraguay':'🇵🇾','Australia':'🇦🇺','Turkiye':'🇹🇷',
    'Germany':'🇩🇪','Curacao':'🇨🇼','Ivory Coast':'🇨🇮','Ecuador':'🇪🇨',
    'Netherlands':'🇳🇱','Japan':'🇯🇵','Sweden':'🇸🇪','Tunisia':'🇹🇳',
    'Belgium':'🇧🇪','Egypt':'🇪🇬','Iran':'🇮🇷','New Zealand':'🇳🇿',
    'Spain':'🇪🇸','Cape Verde':'🇨🇻','Saudi Arabia':'🇸🇦','Uruguay':'🇺🇾',
    'France':'🇫🇷','Senegal':'🇸🇳','Iraq':'🇮🇶','Norway':'🇳🇴',
    'Argentina':'🇦🇷','Algeria':'🇩🇿','Austria':'🇦🇹','Jordan':'🇯🇴',
    'Portugal':'🇵🇹','DR Congo':'🇨🇩','Uzbekistan':'🇺🇿','Colombia':'🇨🇴',
    'England':'🏴󠁧󠁢󠁥󠁮󠁧󠁿','Croatia':'🇭🇷','Ghana':'🇬🇭','Panama':'🇵🇦',
    'TBD':'⚽',
}

def f(t): return FLAGS.get(t, '⚽')

def load_fixtures():
    fp = Path(config.FIXTURES_FILE)
    if not fp.exists(): return {'matches': [], 'groups': {}}
    data = json.loads(fp.read_text(encoding='utf-8'))
    # 自动从 kickoff_utc 计算北京时间（UTC+8）的日期和时间
    CST = timezone(timedelta(hours=8))
    for m in data.get('matches', []):
        if m.get('kickoff_utc'):
            try:
                dt = datetime.fromisoformat(m['kickoff_utc'].replace('Z', '+00:00'))
                dt_cst = dt.astimezone(CST)
                m['kickoff_cst']  = dt_cst.strftime('%H:%M')
                m['date_cst']     = dt_cst.strftime('%Y-%m-%d')   # 正确的北京日期
            except Exception:
                pass
    return data

def load_latest_prediction(match_id):
    order = ['initial']
    d = Path(config.PREDICTIONS_DIR) / match_id
    if not d.exists(): return None
    for rk in order:
        f = d / f'{rk}_prediction.json'
        if f.exists():
            return json.loads(f.read_text(encoding='utf-8'))
    return None

def load_all_predictions(match_id):
    order = ['initial']
    d = Path(config.PREDICTIONS_DIR) / match_id
    if not d.exists(): return []
    result = []
    for rk in order:
        fp = d / f'{rk}_prediction.json'
        if fp.exists():
            result.append(json.loads(fp.read_text(encoding='utf-8')))
    return result

def load_results():
    fp = Path(config.RESULTS_FILE)
    if not fp.exists(): return {}
    data = json.loads(fp.read_text(encoding='utf-8'))
    return {k: v for k, v in data.items() if not k.startswith('_')}

def calc_stats(matches, results):
    total = correct = 0
    for m in matches:
        mid = m['match_id']
        if mid not in results: continue
        pred = load_latest_prediction(mid)
        if not pred: continue
        actual = results[mid]['outcome']
        predicted = _normalize_pred(pred.get('output',{}).get('prediction',''), m['team_a'], m['team_b'])
        total += 1
        if predicted == actual: correct += 1
    acc = f'{correct/total*100:.1f}%' if total > 0 else '—'
    return total, correct, acc


# ─────────────────────────────────────────
# 双语工具
# ─────────────────────────────────────────

def _bi(zh: str, en: str) -> str:
    """双语包裹：中文显示时用zh，英文时用en"""
    return f'<span class="zh">{zh}</span><span class="en">{en}</span>'

def _pred_en(prediction: str, ta: str, tb: str) -> str:
    """把中文预测文字转成英文"""
    if not prediction: return ''
    if ta in prediction and '胜' in prediction: return f'{ta} Win'
    if tb in prediction and '胜' in prediction: return f'{tb} Win'
    if '平' in prediction or 'Draw' in prediction.lower(): return 'Draw'
    return prediction

# ─────────────────────────────────────────
# 渲染工具
# ─────────────────────────────────────────

def _normalize_pred(pred_str, ta, tb):
    if not pred_str: return 'UNKNOWN'
    p = pred_str
    if ta in p and '胜' in p: return 'A_WIN'
    if tb in p and '胜' in p: return 'B_WIN'
    if '平' in p or 'draw' in p.lower(): return 'DRAW'
    return 'UNKNOWN'

def _conf_badge(conf):
    cls = {'高':'high','中':'mid','低':'low'}.get(conf,'mid')
    conf_en = {'高':'High','中':'Mid','低':'Low'}.get(conf,'Mid')
    return f'<span class="badge-conf {cls}">{_bi(conf+"置信", conf_en)}</span>'

def _upset_tag(risk):
    if risk == '高': return f'<span class="badge-risk high">⚡{_bi("爆冷","Upset")}</span>'
    if risk == '中': return f'<span class="badge-risk mid">△{_bi("变数","Variable")}</span>'
    return ''

def _match_card(match, results, compact=False):
    mid = match['match_id']
    ta, tb = match['team_a'], match['team_b']
    # 优先用北京时间的日期（date_cst），避免UTC日期跨天显示错误
    date = match.get('date_cst') or match.get('date','')
    venue = match.get('venue','').split(',')[0]
    md = match.get('matchday', '')
    md_tag = f'MD{md} · ' if md else ''

    pred = load_latest_prediction(mid)
    result = results.get(mid)
    all_preds = load_all_predictions(mid)

    # 预测区
    pred_html = ''
    correct_cls = ''
    if pred:
        out = pred.get('output', {})
        prediction = out.get('prediction', '')
        confidence = out.get('confidence', '')
        reasons_zh = out.get('reasons_zh', out.get('reasons', []))
        reasons_en = out.get('reasons_en', out.get('reasons', []))
        risk = pred.get('_internal', {}).get('upset_risk', '低')
        normalized = _normalize_pred(prediction, ta, tb)
        pred_en = _pred_en(prediction, ta, tb)

        a_cls = 'winner' if normalized == 'A_WIN' else ''
        b_cls = 'winner' if normalized == 'B_WIN' else ''

        # 双语理由
        reasons_html = ''
        for rzh, ren in zip(reasons_zh[:3], reasons_en[:3] if reasons_en else reasons_zh[:3]):
            reasons_html += f'<li>{_bi(rzh, ren)}</li>'

        history_html = ''
        if len(all_preds) > 1:
            items = ''.join(
                f'<li><span class="hl">{p.get("round_label","")}</span>'
                f'{p.get("output",{}).get("prediction","—")} ({p.get("output",{}).get("confidence","?")})</li>'
                for p in all_preds
            )
            history_html = f'<details class="hist"><summary>{_bi("预测历史","History")}</summary><ul>{items}</ul></details>'

        pred_html = f'''
        <div class="pred-box">
          <div class="pred-row">
            <span class="pred-str">{_bi(prediction, pred_en)}</span>
            {_conf_badge(confidence)}{_upset_tag(risk)}
          </div>
          <ul class="reasons">{reasons_html}</ul>
          {history_html}
        </div>'''

        if result:
            actual = result.get('outcome','')
            is_correct = (normalized == actual)
            correct_cls = 'correct' if is_correct else 'incorrect'

    # 实际结果 + 预测对比（增强版）
    result_html = ''
    verdict_html = ''
    if result:
        score = result.get('score', '')
        actual_outcome = result.get('outcome', '')
        icon = '✓' if correct_cls == 'correct' else '✗'

        # 实际结果标签（双语）
        outcome_label_zh = {'A_WIN': f'{ta}胜', 'B_WIN': f'{tb}胜', 'DRAW': '平局'}.get(actual_outcome, actual_outcome)
        outcome_label_en = {'A_WIN': f'{ta} Win', 'B_WIN': f'{tb} Win', 'DRAW': 'Draw'}.get(actual_outcome, actual_outcome)
        outcome_label = _bi(outcome_label_zh, outcome_label_en)

        # 赛果栏
        result_html = f'''
        <div class="result-bar {correct_cls}">
          <span class="result-icon">{icon}</span>
          <div class="result-detail">
            <span class="result-score">{score}</span>
            <span class="result-outcome">{_bi("实际：","Result:")} {outcome_label}</span>
          </div>
        </div>'''

        # 预测对比行
        if pred:
            prediction_str = pred.get('output', {}).get('prediction', '')
            conf_str = pred.get('output', {}).get('confidence', '')
            pred_str_en = _pred_en(prediction_str, ta, tb)
            conf_en = {'高':'High','中':'Mid','低':'Low'}.get(conf_str, conf_str)
            match_txt = _bi('预测正确 ✓','Correct ✓') if correct_cls == 'correct' else _bi('预测有误 ✗','Wrong ✗')
            verdict_html = f'''
            <div class="verdict {correct_cls}">
              <span class="verdict-pred">{_bi(f"预测：{prediction_str}（{conf_str}置信）", f"Pred: {pred_str_en} ({conf_en})")}</span>
              <span class="verdict-sep">→</span>
              <span class="verdict-actual">{_bi(f"实际：{outcome_label_zh} {score}", f"Result: {outcome_label_en} {score}")}</span>
              <span class="verdict-badge">{match_txt}</span>
            </div>'''

    # 显示中国时间
    kickoff = match.get('kickoff_cst', '')
    time_str = f' {kickoff}' if kickoff else ''
    date_display = f'{date[5:]}{time_str} 北京时间' if date else ''

    return f'''
    <div class="match-card {correct_cls}" id="{mid}">
      <div class="match-meta">{md_tag}{date_display} · {venue}</div>
      <div class="teams">
        <span class="team-name {a_cls if pred else ""}">{f(ta)}<br><b>{ta}</b></span>
        <span class="vs">VS</span>
        <span class="team-name right {b_cls if pred else ""}">{f(tb)}<br><b>{tb}</b></span>
      </div>
      {result_html}
      {verdict_html}
      {pred_html}
    </div>'''


# ─────────────────────────────────────────
# Tab 1: 按小组
# ─────────────────────────────────────────

GROUP_TEAMS = {
    'A':['Mexico','South Africa','South Korea','Czechia'],
    'B':['Canada','Bosnia and Herzegovina','Qatar','Switzerland'],
    'C':['Brazil','Morocco','Haiti','Scotland'],
    'D':['United States','Paraguay','Australia','Turkiye'],
    'E':['Germany','Curacao','Ivory Coast','Ecuador'],
    'F':['Netherlands','Japan','Sweden','Tunisia'],
    'G':['Belgium','Egypt','Iran','New Zealand'],
    'H':['Spain','Cape Verde','Saudi Arabia','Uruguay'],
    'I':['France','Senegal','Iraq','Norway'],
    'J':['Argentina','Algeria','Austria','Jordan'],
    'K':['Portugal','DR Congo','Uzbekistan','Colombia'],
    'L':['England','Croatia','Ghana','Panama'],
}

def render_groups_tab(matches, results):
    from collections import defaultdict
    by_group = defaultdict(list)
    for m in matches:
        if m.get('stage') == 'group_stage' and m.get('group'):
            by_group[m['group']].append(m)

    html = '<div class="groups-grid">'
    for g in sorted(by_group.keys()):
        teams = GROUP_TEAMS.get(g, [])
        chips = ''.join(f'<span class="chip">{f(t)} {t}</span>' for t in teams)
        ms = sorted(by_group[g], key=lambda x: (x.get('matchday',0), x.get('date','')))
        cards = ''.join(_match_card(m, results) for m in ms)
        html += f'''
        <div class="group-wrap">
          <div class="group-hd">
            <span class="group-lbl">第 {g} 组</span>
            <div class="group-chips">{chips}</div>
          </div>
          <div class="group-matches">{cards}</div>
        </div>'''
    html += '</div>'
    return html


# ─────────────────────────────────────────
# Tab 2: 按日期（赛程表）
# ─────────────────────────────────────────

def render_schedule_tab(matches, results):
    from collections import defaultdict

    # 按精确时间排序（北京日期 + kickoff_cst），没有时间的排后面
    def sort_key(m):
        date = m.get('date_cst') or m.get('date', '9999-99-99')
        time = m.get('kickoff_cst', '99:99')
        return f'{date} {time}'

    sorted_matches = sorted(matches, key=sort_key)

    # 按日期分组（用北京时间日期，保持时间排序）
    by_date = defaultdict(list)
    for m in sorted_matches:
        date = m.get('date_cst') or m.get('date', '')
        if date:
            by_date[date].append(m)

    html = '<div class="schedule-list">'
    for date in sorted(by_date.keys()):
        ms = by_date[date]  # 已按时间排序
        try:
            dt = datetime.strptime(date, '%Y-%m-%d')
            date_label = dt.strftime('%m月%d日') + ' ' + ['周一','周二','周三','周四','周五','周六','周日'][dt.weekday()]
        except Exception:
            date_label = date

        day_matches = ''
        for m in ms:  # 直接用已排序的列表
            mid = m['match_id']
            ta, tb = m['team_a'], m['team_b']
            stage = m.get('stage','')
            grp = m.get('group','?')
            mday = m.get('matchday','')
            stage_label_zh = {
                'group_stage': f"第{grp}组 MD{mday}",
                'round_of_32':'32强','round_of_16':'16强',
                'quarterfinal':'四分之一决赛','semifinal':'半决赛','final':'决赛',
            }.get(stage, stage)
            stage_label_en = {
                'group_stage': f"Group {grp} MD{mday}",
                'round_of_32':'Round of 32','round_of_16':'Round of 16',
                'quarterfinal':'Quarter-Final','semifinal':'Semi-Final','final':'Final',
            }.get(stage, stage)
            stage_label = _bi(stage_label_zh, stage_label_en)
            venue = m.get('venue','').split(',')[0]
            kickoff = m.get('kickoff_cst', '')
            time_tag = f'<span class="time-tag">{kickoff} {_bi("北京时间","CST")}</span>' if kickoff else ''

            pred = load_latest_prediction(mid)
            result = results.get(mid)

            # 状态标签（双语）
            status_cls = 'upcoming'
            status_txt = _bi('待赛','Upcoming')
            if result:
                status_cls = 'finished'
                status_txt = _bi('完赛','Final')
            elif pred:
                status_cls = 'predicted'
                status_txt = _bi('已预测','Predicted')

            # 比分或预测
            score_block = ''
            verdict_sched = ''
            sched_correct_cls = ''

            if result:
                score = result.get('score', '?')
                actual_outcome = result.get('outcome', '')
                outcome_label_zh = {'A_WIN': f'{ta}胜', 'B_WIN': f'{tb}胜', 'DRAW': '平局'}.get(actual_outcome, actual_outcome)
                outcome_label = _bi(outcome_label_zh, {'A_WIN': f'{ta} Win', 'B_WIN': f'{tb} Win', 'DRAW': 'Draw'}.get(actual_outcome, actual_outcome))

                is_correct = False
                correct_icon = ''
                if pred:
                    normalized = _normalize_pred(pred.get('output', {}).get('prediction', ''), ta, tb)
                    is_correct = normalized == actual_outcome
                    correct_icon = '✓' if is_correct else '✗'
                    sched_correct_cls = 'correct' if is_correct else 'incorrect'

                score_block = f'''<div class="score-block finished {sched_correct_cls}">
                  <span class="sched-result-icon">{correct_icon}</span>
                  <span class="score">{score}</span>
                </div>'''

                # 预测对比（赛程表版）
                if pred:
                    prediction_str = pred.get('output', {}).get('prediction', '')
                    confidence = pred.get('output', {}).get('confidence', '')
                    conf_en2 = {'高':'High','中':'Mid','低':'Low'}.get(confidence, confidence)
                    pred_en2 = _pred_en(prediction_str, ta, tb)
                    badge = _bi('预测正确 ✓','Correct ✓') if is_correct else _bi('预测有误 ✗','Wrong ✗')
                    badge_cls = 'correct' if is_correct else 'incorrect'
                    outcome_en2 = {'A_WIN': f'{ta} Win', 'B_WIN': f'{tb} Win', 'DRAW': 'Draw'}.get(actual_outcome, actual_outcome)
                    verdict_sched = f'''
                    <div class="sched-verdict {badge_cls}">
                      <span>{_bi(f"预测：{prediction_str}（{confidence}）", f"Pred: {pred_en2} ({conf_en2})")}</span>
                      <span class="sv-arrow">→</span>
                      <span>{_bi(f"实际：{outcome_label_zh} {score}", f"Result: {outcome_en2} {score}")}</span>
                      <span class="sv-badge {badge_cls}">{badge}</span>
                    </div>'''

            elif pred:
                out = pred.get('output', {})
                prediction = out.get('prediction', '')
                confidence = out.get('confidence', '')
                risk = pred.get('_internal', {}).get('upset_risk', '低')
                conf_cls = {'高': 'high', '中': 'mid', '低': 'low'}.get(confidence, 'mid')
                conf_en = {'高':'High','中':'Mid','低':'Low'}.get(confidence, confidence)
                risk_icon = '⚡' if risk == '高' else ('△' if risk == '中' else '')
                pred_en_str = _pred_en(prediction, ta, tb)
                score_block = f'''<div class="score-block predicted">
                  <div class="pred-label">{_bi(prediction, pred_en_str)}</div>
                  <div class="pred-meta"><span class="conf-dot {conf_cls}"></span>{_bi(confidence, conf_en)} {risk_icon}</div>
                </div>'''
            else:
                score_block = '<div class="score-block upcoming"><span class="vs-dash">-</span></div>'

            # 3条理由（双语，点击展开）
            reasons_detail = ''
            if pred:
                out2 = pred.get('output', {})
                rzh_list = out2.get('reasons_zh', out2.get('reasons', []))
                ren_list = out2.get('reasons_en', out2.get('reasons', []))
                if rzh_list:
                    items = ''
                    for rzh, ren in zip(rzh_list[:3], ren_list[:3] if ren_list else rzh_list[:3]):
                        items += f'<li>{_bi(rzh, ren)}</li>'
                    reasons_detail = f'<div class="reasons-detail"><ul>{items}</ul></div>'

            day_matches += f'''
            <div class="sched-card {status_cls} {sched_correct_cls}" onclick="this.classList.toggle('expanded')">
              <div class="sched-row">
                <div class="sched-teams">
                  <div class="sched-team">{f(ta)} {ta}</div>
                  {score_block}
                  <div class="sched-team right">{f(tb)} {tb}</div>
                </div>
                <div class="sched-meta">
                  {time_tag}
                  <span class="stage-tag">{stage_label}</span>
                  <span class="venue-tag">{venue}</span>
                  <span class="status-tag {status_cls}">{status_txt}</span>
                </div>
              </div>
              {verdict_sched}
              {reasons_detail}
            </div>'''

        html += f'''
        <div class="date-group">
          <div class="date-hd">{date_label}</div>
          <div class="date-matches">{day_matches}</div>
        </div>'''

    html += '</div>'
    return html


# ─────────────────────────────────────────
# 完整 HTML 生成
# ─────────────────────────────────────────

def generate_html():
    fixtures = load_fixtures()
    matches = fixtures.get('matches', [])
    results = load_results()
    total, correct, acc = calc_stats(matches, results)
    completed = len(results)
    predicted = sum(1 for m in matches if load_latest_prediction(m['match_id']))
    high_risk = 0
    for m in matches:
        p = load_latest_prediction(m['match_id'])
        if p and p.get('_internal',{}).get('upset_risk') == '高':
            high_risk += 1

    groups_html = render_groups_tab(matches, results)
    schedule_html = render_schedule_tab(matches, results)

    now_str = datetime.now().strftime('%Y-%m-%d %H:%M')
    return f'''<!DOCTYPE html>
<html lang="zh-CN" data-lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>🏆 FIFA World Cup 2026 · AI Predictions</title>
<style>
{_css()}
</style>
</head>
<body>
<header>
  <div class="hdr-inner">
    <div class="hdr-top-bar">
      <div class="hdr-badge">{_bi("AI 预测系统 · 实时更新","AI Prediction · Live")}</div>
      <button class="lang-btn" onclick="toggleLang()" title="Switch Language">
        <span class="zh">🇬🇧 EN</span><span class="en">🇨🇳 中文</span>
      </button>
    </div>
    <h1>🏆 {_bi("FIFA 世界杯 2026","FIFA World Cup 2026")}</h1>
    <p class="hdr-sub">{_bi("美国 · 加拿大 · 墨西哥","USA · Canada · Mexico")} &nbsp;|&nbsp; 2026.6.11 — 7.19</p>
    <div class="stats">
      <div class="stat"><b>{predicted}</b><small>{_bi("已预测","Predicted")}</small></div>
      <div class="stat"><b>{completed}</b><small>{_bi("已完赛","Completed")}</small></div>
      <div class="stat hi"><b>{acc}</b><small>{_bi("预测准确率","Accuracy")}</small></div>
      <div class="stat"><b>{high_risk}</b><small>{_bi("高爆冷风险","Upset Risk")}</small></div>
    </div>
  </div>
</header>

<div class="tabs">
  <button class="tab-btn active" onclick="switchTab('groups',this)">⚽ {_bi("按小组","Groups")}</button>
  <button class="tab-btn" onclick="switchTab('schedule',this)">📅 {_bi("赛程表","Schedule")}</button>
  <button class="tab-btn" onclick="switchTab('knockout',this)">🏆 {_bi("淘汰赛","Knockout")}</button>
</div>

<main>
  <div id="tab-groups" class="tab-content active">
    <div class="sec-title">{_bi("小组赛 — 12组 × 6场","Group Stage — 12 Groups × 6 Matches")}</div>
    {groups_html}
  </div>

  <div id="tab-schedule" class="tab-content">
    <div class="sec-title">{_bi("全部赛程 · 按日期","Full Schedule · By Date")}</div>
    {schedule_html}
  </div>

  <div id="tab-knockout" class="tab-content">
    <div class="sec-title" style="margin-bottom:12px">🏆 {_bi("淘汰赛对阵图 · AI 预测","Knockout Bracket · AI Predictions")}</div>
    <iframe src="knockout_bracket.html" style="width:100%;height:900px;border:none;border-radius:12px;background:transparent;overflow:hidden;" onload="this.style.height=this.contentDocument.body.scrollHeight+'px'"></iframe>
  </div>
</main>

<footer>
  {_bi("数据来源：FIFA官网 · ESPN API · DeepSeek AI 分析","Data: FIFA · ESPN API · DeepSeek AI")} &nbsp;·&nbsp;
  {_bi("最后更新","Updated")}: {now_str}
</footer>

<script>{_js()}</script>
</body>
</html>'''


def _css():
    return '''
:root{--bg:#080d17;--s1:#111827;--s2:#1a2234;--s3:#232f45;
  --gold:#f5b731;--gold2:#d4981e;--green:#34d399;--red:#f87171;
  --text:#f1f5f9;--muted:#64748b;--border:#1e293b;--r:12px}
*{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif}

/* ── 语言切换核心规则 ───────────────── */
[data-lang="zh"] .en{display:none}
[data-lang="en"] .zh{display:none}

/* Header */
header{background:linear-gradient(160deg,#0c1525,#1a2740);border-bottom:1px solid var(--border);padding:36px 20px 30px;text-align:center}
.hdr-top-bar{display:flex;align-items:center;justify-content:center;gap:16px;margin-bottom:12px}
.hdr-badge{display:inline-block;border:1px solid var(--gold2);color:var(--gold);background:rgba(245,183,49,.08);padding:3px 14px;border-radius:20px;font-size:11px;letter-spacing:1.5px;text-transform:uppercase}
.lang-btn{background:rgba(255,255,255,.08);border:1px solid var(--border);color:var(--text);padding:4px 12px;border-radius:16px;font-size:12px;cursor:pointer;transition:.2s}
.lang-btn:hover{background:rgba(245,183,49,.15);border-color:var(--gold2)}
h1{font-size:clamp(1.8rem,5vw,3rem);font-weight:900;background:linear-gradient(135deg,var(--gold) 20%,#fff 55%,var(--gold) 90%);-webkit-background-clip:text;-webkit-text-fill-color:transparent;line-height:1.1;margin-bottom:8px}
.hdr-sub{color:var(--muted);font-size:.9rem;margin-bottom:28px}
.stats{display:flex;justify-content:center;gap:40px;flex-wrap:wrap;padding-top:24px;border-top:1px solid var(--border)}
.stat{text-align:center}
.stat b{display:block;font-size:1.8rem;font-weight:800;color:var(--text)}
.stat.hi b{background:linear-gradient(135deg,var(--gold),#fff);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.stat small{font-size:.68rem;color:var(--muted);text-transform:uppercase;letter-spacing:.5px}

/* Tabs */
.tabs{display:flex;gap:0;padding:0 20px;border-bottom:1px solid var(--border);background:var(--s1);position:sticky;top:0;z-index:100}
.tab-btn{flex:1;max-width:200px;padding:14px 20px;background:none;border:none;border-bottom:2px solid transparent;color:var(--muted);font-size:.9rem;font-weight:600;cursor:pointer;transition:.2s}
.tab-btn:hover{color:var(--text)}
.tab-btn.active{color:var(--gold);border-bottom-color:var(--gold)}

/* Content */
main{max-width:1680px;margin:0 auto;padding:28px 20px 60px}
.tab-content{display:none}
.tab-content.active{display:block}
.sec-title{font-size:1.1rem;font-weight:700;color:var(--gold);margin-bottom:20px;padding-bottom:8px;border-bottom:2px solid var(--gold2)}

/* ── Groups Tab ── */
.groups-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(360px,1fr));gap:18px}
.group-wrap{background:var(--s1);border:1px solid var(--border);border-radius:var(--r);overflow:hidden}
.group-hd{background:linear-gradient(135deg,var(--s2),var(--s3));padding:12px 16px;border-bottom:1px solid var(--border)}
.group-lbl{font-size:.72rem;font-weight:700;color:var(--gold);text-transform:uppercase;letter-spacing:1px;display:block;margin-bottom:6px}
.group-chips{display:flex;flex-wrap:wrap;gap:4px}
.chip{background:rgba(255,255,255,.05);border:1px solid var(--border);border-radius:10px;padding:2px 8px;font-size:10px;color:var(--muted)}
.group-matches{padding:8px;display:flex;flex-direction:column;gap:6px}

/* Match card */
.match-card{background:var(--s2);border:1px solid var(--border);border-radius:10px;padding:11px;transition:border-color .2s}
.match-card:hover{border-color:rgba(245,183,49,.3)}
.match-card.correct{border-left:3px solid var(--green)}
.match-card.incorrect{border-left:3px solid var(--red)}
.match-meta{font-size:9px;color:var(--muted);margin-bottom:7px}
.teams{display:grid;grid-template-columns:1fr auto 1fr;gap:6px;align-items:center;margin-bottom:8px}
.team-name{font-size:11px;font-weight:500;line-height:1.3;text-align:center}
.team-name.right{text-align:center}
.team-name.winner{color:var(--gold);font-weight:700}
.vs{font-size:10px;color:var(--muted);font-weight:700;text-align:center}
.pred-box{background:rgba(0,0,0,.2);border-radius:7px;padding:7px 9px}
.pred-row{display:flex;align-items:center;gap:5px;flex-wrap:wrap;margin-bottom:5px}
.pred-str{font-weight:700;font-size:12px;color:var(--gold);flex:1}
.badge-conf{padding:1px 7px;border-radius:9px;font-size:9px;font-weight:600}
.badge-conf.high{background:rgba(52,211,153,.12);color:var(--green)}
.badge-conf.mid{background:rgba(245,183,49,.12);color:var(--gold)}
.badge-conf.low{background:rgba(100,116,139,.12);color:var(--muted)}
.badge-risk{font-size:9px;white-space:nowrap}
.badge-risk.high{color:var(--red)}
.badge-risk.mid{color:var(--gold)}
.reasons{list-style:none;padding:0}
.reasons li{font-size:10px;color:var(--muted);padding:1px 0 1px 12px;position:relative;line-height:1.4}
.reasons li::before{content:"•";position:absolute;left:3px;color:var(--gold2)}
.result-bar{display:flex;align-items:center;gap:8px;padding:6px 10px;border-radius:8px;margin-bottom:6px}
.result-bar.correct{background:rgba(52,211,153,.1);border:1px solid rgba(52,211,153,.25)}
.result-bar.incorrect{background:rgba(248,113,113,.1);border:1px solid rgba(248,113,113,.25)}
.result-icon{font-size:1rem;font-weight:800;flex-shrink:0}
.result-bar.correct .result-icon{color:var(--green)}
.result-bar.incorrect .result-icon{color:var(--red)}
.result-detail{display:flex;flex-direction:column;gap:1px}
.result-score{font-size:13px;font-weight:800;color:var(--text)}
.result-outcome{font-size:10px;color:var(--muted)}
.verdict{display:flex;flex-wrap:wrap;align-items:center;gap:5px;padding:5px 8px;border-radius:6px;margin-bottom:6px;font-size:10px}
.verdict.correct{background:rgba(52,211,153,.07)}
.verdict.incorrect{background:rgba(248,113,113,.07)}
.verdict-pred{color:var(--muted)}
.verdict-sep{color:var(--muted)}
.verdict-actual{color:var(--text);font-weight:600}
.verdict-badge{margin-left:auto;padding:1px 7px;border-radius:8px;font-weight:700;font-size:9px}
.verdict.correct .verdict-badge{background:rgba(52,211,153,.2);color:var(--green)}
.verdict.incorrect .verdict-badge{background:rgba(248,113,113,.2);color:var(--red)}
.hist{margin-top:5px}
.hist summary{font-size:9px;color:var(--muted);cursor:pointer}
.hist ul{list-style:none;padding:4px 0 0 0}
.hist li{font-size:9px;color:var(--muted);display:flex;justify-content:space-between;padding:1px 0}
.hl{color:var(--text);margin-right:8px}

/* ── Schedule Tab ── */
.schedule-list{display:flex;flex-direction:column;gap:20px}
.date-group{}
.date-hd{font-size:1rem;font-weight:700;color:var(--gold);padding:10px 0 8px;border-bottom:1px solid var(--border);margin-bottom:10px}
.date-matches{display:flex;flex-direction:column;gap:8px}
.sched-card{background:var(--s1);border:1px solid var(--border);border-radius:10px;padding:14px 16px;cursor:pointer;transition:border-color .2s}
.sched-card:hover{border-color:rgba(245,183,49,.3)}
.sched-card.finished{border-left:3px solid var(--border)}
.sched-card.finished.correct{border-left:3px solid var(--green)}
.sched-card.finished.incorrect{border-left:3px solid var(--red)}
.sched-row{}
.sched-teams{display:grid;grid-template-columns:1fr auto 1fr;gap:8px;align-items:center;margin-bottom:8px}
.sched-team{font-size:13px;font-weight:600}
.sched-team.right{text-align:right}
.sched-meta{display:flex;flex-wrap:wrap;gap:8px;align-items:center}
.time-tag{font-size:11px;font-weight:700;color:var(--gold);min-width:70px}
.stage-tag{font-size:10px;background:rgba(255,255,255,.06);padding:2px 8px;border-radius:8px;color:var(--muted)}
.venue-tag{font-size:10px;color:var(--muted)}
.status-tag{font-size:10px;padding:2px 8px;border-radius:8px;font-weight:600}
.status-tag.finished{background:rgba(52,211,153,.1);color:var(--green)}
.status-tag.predicted{background:rgba(245,183,49,.1);color:var(--gold)}
.status-tag.upcoming{background:rgba(100,116,139,.1);color:var(--muted)}
.score-block{display:flex;flex-direction:column;align-items:center;min-width:80px}
.score-block.finished .score{font-size:1.2rem;font-weight:800;color:var(--text)}
.score-block.predicted .pred-label{font-size:11px;font-weight:700;color:var(--gold);text-align:center}
.score-block.predicted .pred-meta{font-size:10px;color:var(--muted);display:flex;align-items:center;gap:4px}
.score-block.upcoming .vs-dash{font-size:1.2rem;color:var(--muted);font-weight:300}
.conf-dot{width:6px;height:6px;border-radius:50%;display:inline-block}
.conf-dot.high{background:var(--green)}
.conf-dot.mid{background:var(--gold)}
.conf-dot.low{background:var(--muted)}
.res-icon{font-size:.8rem;font-weight:700;margin-right:4px}
.res-icon.correct{color:var(--green)}
.res-icon.wrong{color:var(--red)}
/* 赛程表结果图标 */
.sched-result-icon{font-size:.85rem;font-weight:800;margin-right:3px}
.score-block.correct .sched-result-icon{color:var(--green)}
.score-block.incorrect .sched-result-icon{color:var(--red)}
.sched-card.correct{border-left:3px solid var(--green)}
.sched-card.incorrect{border-left:3px solid var(--red)}
/* 赛程表预测对比行 */
.sched-verdict{display:flex;flex-wrap:wrap;align-items:center;gap:4px;
  padding:5px 10px;font-size:10px;border-top:1px solid var(--border)}
.sched-verdict.correct{background:rgba(52,211,153,.06)}
.sched-verdict.incorrect{background:rgba(248,113,113,.06)}
.sv-arrow{color:var(--muted)}
.sv-badge{margin-left:auto;padding:1px 7px;border-radius:8px;font-weight:700;font-size:9px}
.sv-badge.correct{background:rgba(52,211,153,.2);color:var(--green)}
.sv-badge.incorrect{background:rgba(248,113,113,.2);color:var(--red)}
.reasons-detail{display:none;padding-top:10px;border-top:1px solid var(--border);margin-top:10px}
.sched-card.expanded .reasons-detail{display:block}
.reasons-detail ul{list-style:none;padding:0}
.reasons-detail li{font-size:11px;color:var(--muted);padding:2px 0 2px 14px;position:relative;line-height:1.4}
.reasons-detail li::before{content:"•";position:absolute;left:4px;color:var(--gold2)}

/* Footer */
footer{text-align:center;padding:24px;color:var(--muted);font-size:.72rem;border-top:1px solid var(--border)}

@media(max-width:640px){
  .groups-grid{grid-template-columns:1fr}
  .stats{gap:20px}
  .sched-teams{grid-template-columns:1fr 70px 1fr}
}
'''

def _js():
    return '''
// ── Tab 切换 ──────────────────────────────
function switchTab(name, btn) {
  document.querySelectorAll('.tab-content').forEach(t => t.classList.remove('active'))
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'))
  document.getElementById('tab-' + name).classList.add('active')
  btn.classList.add('active')
}

// ── 语言切换 ──────────────────────────────
function toggleLang() {
  const html = document.documentElement
  const current = html.getAttribute('data-lang') || 'zh'
  const next = current === 'zh' ? 'en' : 'zh'
  html.setAttribute('data-lang', next)
  localStorage.setItem('wc2026_lang', next)
}

// 页面加载时恢复语言设置
(function() {
  const saved = localStorage.getItem('wc2026_lang')
  if (saved) document.documentElement.setAttribute('data-lang', saved)
})()
'''


# ─────────────────────────────────────────
# KO 预测数据 JS（供 knockout_bracket.html 加载）
# ─────────────────────────────────────────

def generate_ko_prediction_js():
    """生成 web/ko_predictions.js，包含所有淘汰赛的 AI 预测数据。"""
    fixtures = load_fixtures()
    predictions = {}
    for match in fixtures.get('matches', []):
        stage = match.get('stage', '')
        if stage in ('group_stage', ''):
            continue
        mid = match['match_id']
        pred = load_latest_prediction(mid)
        if pred and pred.get('output'):
            out = pred['output']
            internal = pred.get('_internal', {})
            predictions[mid] = {
                'prediction': out.get('prediction', ''),
                'confidence': out.get('confidence', ''),
                'p_a_win': internal.get('p_a_win'),
                'p_b_win': internal.get('p_b_win'),
            }

    js_content = 'window.KO_PREDICTIONS = ' + json.dumps(
        predictions, ensure_ascii=False, indent=2) + ';'
    js_path = Path(config.HTML_FILE).parent / 'ko_predictions.js'
    js_path.write_text(js_content, encoding='utf-8')
    print(f'  [KO预测JS] 已生成: {js_path.name} ({len(predictions)} 场)')


# ─────────────────────────────────────────
# 入口
# ─────────────────────────────────────────

def update_html():
    print('[HTML] 生成 index.html...')
    html = generate_html()
    out = Path(config.HTML_FILE)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding='utf-8')
    size_kb = len(html) // 1024
    print(f'[HTML] 已保存: {out} ({size_kb}KB)')
    generate_ko_prediction_js()
    return str(out)


if __name__ == '__main__':
    update_html()
