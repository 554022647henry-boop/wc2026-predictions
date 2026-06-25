"""
生成两张中文预测表格：
1. prediction_group_zh.html  — 按小组排列
2. prediction_schedule_zh.html — 按赛程（日期）排列
"""
import json, pathlib
from datetime import datetime, timezone, timedelta

# ── 数据加载 ──────────────────────────────────────────────
BASE = pathlib.Path('.')
fixtures = json.loads((BASE / 'data/fixtures.json').read_text(encoding='utf-8'))
results_raw = {}
rf = BASE / 'data/results/results.json'
if rf.exists():
    r = json.loads(rf.read_text(encoding='utf-8'))
    results_raw = {k: v for k, v in r.items() if isinstance(v, dict)}
pred_dir = BASE / 'data/predictions'

CST = timezone(timedelta(hours=8))

# ── 中文国家名映射 ────────────────────────────────────────
ZH = {
    'Algeria':                '阿尔及利亚',
    'Argentina':              '阿根廷',
    'Australia':              '澳大利亚',
    'Austria':                '奥地利',
    'Belgium':                '比利时',
    'Bosnia and Herzegovina': '波黑',
    'Brazil':                 '巴西',
    'Canada':                 '加拿大',
    'Cape Verde':             '佛得角',
    'Colombia':               '哥伦比亚',
    'Croatia':                '克罗地亚',
    'Curacao':                '库拉索',
    'Czechia':                '捷克',
    'DR Congo':               '刚果(金)',
    'Ecuador':                '厄瓜多尔',
    'Egypt':                  '埃及',
    'England':                '英格兰',
    'France':                 '法国',
    'Germany':                '德国',
    'Ghana':                  '加纳',
    'Haiti':                  '海地',
    'Iran':                   '伊朗',
    'Iraq':                   '伊拉克',
    'Ivory Coast':            '科特迪瓦',
    'Japan':                  '日本',
    'Jordan':                 '约旦',
    'Mexico':                 '墨西哥',
    'Morocco':                '摩洛哥',
    'Netherlands':            '荷兰',
    'New Zealand':            '新西兰',
    'Norway':                 '挪威',
    'Panama':                 '巴拿马',
    'Paraguay':               '巴拉圭',
    'Portugal':               '葡萄牙',
    'Qatar':                  '卡塔尔',
    'Saudi Arabia':           '沙特',
    'Scotland':               '苏格兰',
    'Senegal':                '塞内加尔',
    'South Africa':           '南非',
    'South Korea':            '韩国',
    'Spain':                  '西班牙',
    'Sweden':                 '瑞典',
    'Switzerland':            '瑞士',
    'Tunisia':                '突尼斯',
    'Turkiye':                '土耳其',
    'United States':          '美国',
    'Uruguay':                '乌拉圭',
    'Uzbekistan':             '乌兹别克',
}

def zh(name):
    return ZH.get(name, name)

# ── English short names ───────────────────────────────────
EN = {
    'Algeria':                'Algeria',
    'Argentina':              'Argentina',
    'Australia':              'Australia',
    'Austria':                'Austria',
    'Belgium':                'Belgium',
    'Bosnia and Herzegovina': 'Bosnia',
    'Brazil':                 'Brazil',
    'Canada':                 'Canada',
    'Cape Verde':             'C. Verde',
    'Colombia':               'Colombia',
    'Croatia':                'Croatia',
    'Curacao':                'Curacao',
    'Czechia':                'Czechia',
    'DR Congo':               'DR Congo',
    'Ecuador':                'Ecuador',
    'Egypt':                  'Egypt',
    'England':                'England',
    'France':                 'France',
    'Germany':                'Germany',
    'Ghana':                  'Ghana',
    'Haiti':                  'Haiti',
    'Iran':                   'Iran',
    'Iraq':                   'Iraq',
    'Ivory Coast':            'Ivory Coast',
    'Japan':                  'Japan',
    'Jordan':                 'Jordan',
    'Mexico':                 'Mexico',
    'Morocco':                'Morocco',
    'Netherlands':            'Netherlands',
    'New Zealand':            'New Zealand',
    'Norway':                 'Norway',
    'Panama':                 'Panama',
    'Paraguay':               'Paraguay',
    'Portugal':               'Portugal',
    'Qatar':                  'Qatar',
    'Saudi Arabia':           'Saudi Arabia',
    'Scotland':               'Scotland',
    'Senegal':                'Senegal',
    'South Africa':           'S. Africa',
    'South Korea':            'South Korea',
    'Spain':                  'Spain',
    'Sweden':                 'Sweden',
    'Switzerland':            'Switzerland',
    'Tunisia':                'Tunisia',
    'Turkiye':                'Turkiye',
    'United States':          'USA',
    'Uruguay':                'Uruguay',
    'Uzbekistan':             'Uzbekistan',
}

def name(n, lang='zh'):
    return EN.get(n, n) if lang == 'en' else ZH.get(n, n)

def get_kickoff_cst(match):
    ku = match.get('kickoff_utc', '')
    if ku:
        try:
            dt = datetime.fromisoformat(ku.replace('Z', '+00:00')).astimezone(CST)
            return dt.strftime('%m/%d %H:%M')
        except:
            pass
    return match.get('date', '')[5:] if match.get('date') else ''

def get_pred(mid):
    pf = pred_dir / mid / 'initial_prediction.json'
    if not pf.exists():
        return {}
    try:
        return json.loads(pf.read_text(encoding='utf-8')).get('output', {})
    except:
        return {}

def pred_result(pred, ta, tb):
    """返回 (箭头html, a_bold, b_bold, conf标签)"""
    p = pred.get('prediction', '')
    conf = pred.get('confidence', '')
    conf_cls = {'高': 'c-h', '中': 'c-m', '低': 'c-l'}.get(conf, 'c-m')
    conf_tag = f'<span class="conf {conf_cls}">{conf}</span>'

    if not p:
        return '<span class="arr-vs">vs</span>', False, False, ''
    if '平局' in p or 'draw' in p.lower():
        return '<span class="arr-draw">平</span>', False, False, conf_tag
    # 判断谁赢
    ta_zh, tb_zh = zh(ta), zh(tb)
    if ta in p or ta_zh in p:
        return '<span class="arr-l">◀</span>', True, False, conf_tag
    else:
        return '<span class="arr-r">▶</span>', False, True, conf_tag


# ════════════════════════════════════════════════════════
# 表1: 按小组
# ════════════════════════════════════════════════════════

def build_group_html():
    # 按小组收集比赛
    by_group = {}
    for m in fixtures['matches']:
        if m.get('stage') != 'group_stage': continue
        g = m.get('group', '?')
        by_group.setdefault(g, []).append(m)

    html_blocks = []
    for g in sorted(by_group.keys()):
        matches = sorted(by_group[g], key=lambda x: (x.get('matchday', 0), x.get('kickoff_utc', x.get('date', ''))))
        teams = list({m['team_a'] for m in matches} | {m['team_b'] for m in matches})
        teams_zh = ' · '.join(zh(t) for t in sorted(teams))

        rows = []
        for m in matches:
            mid = m['match_id']
            ta, tb = m['team_a'], m['team_b']
            md = m.get('matchday', '')
            time_str = get_kickoff_cst(m)
            actual = results_raw.get(mid, {})

            if actual:
                score = actual.get('score', '?')
                outcome = actual.get('outcome', '')
                ca = ' w' if outcome == 'A_WIN' else ''
                cb = ' w' if outcome == 'B_WIN' else ''
                # 同时显示预测
                pred = get_pred(mid)
                if pred:
                    arr, ba, bb, ctag = pred_result(pred, ta, tb)
                    correct = (
                        (outcome == 'A_WIN' and ba) or
                        (outcome == 'B_WIN' and bb) or
                        (outcome == 'DRAW' and '平' in arr)
                    )
                    verdict = '<span class="ok">✅</span>' if correct else '<span class="ng">❌</span>'
                    pred_tag = f'{arr}{verdict}'
                else:
                    pred_tag = ''
                rows.append(
                    f'<tr class="played">'
                    f'<td class="md">MD{md}</td>'
                    f'<td class="dt">{time_str}</td>'
                    f'<td class="ta{ca}">{zh(ta)}</td>'
                    f'<td class="sc"><span class="score">{score}</span><br><span class="pred-sm">{pred_tag}</span></td>'
                    f'<td class="tb{cb}">{zh(tb)}</td>'
                    f'<td class="cf"></td>'
                    f'</tr>'
                )
            else:
                pred = get_pred(mid)
                arr, ba, bb, ctag = pred_result(pred, ta, tb)
                ca = ' w' if ba else ''
                cb = ' w' if bb else ''
                row_cls = 'pred' if pred else 'upcoming'
                rows.append(
                    f'<tr class="{row_cls}">'
                    f'<td class="md">MD{md}</td>'
                    f'<td class="dt">{time_str}</td>'
                    f'<td class="ta{ca}">{zh(ta)}</td>'
                    f'<td class="sc">{arr}</td>'
                    f'<td class="tb{cb}">{zh(tb)}</td>'
                    f'<td class="cf">{ctag}</td>'
                    f'</tr>'
                )

        html_blocks.append(f'''
<div class="grp">
  <div class="grp-hd">第{g}组 <span class="grp-teams">{teams_zh}</span></div>
  <table>
    <tr class="hdr"><th>轮</th><th>北京时间</th><th>主场</th><th>比分/预测</th><th>客场</th><th></th></tr>
    {''.join(rows)}
  </table>
</div>''')

    return '\n'.join(html_blocks)


# ════════════════════════════════════════════════════════
# 表2: 按赛程（日期）
# ════════════════════════════════════════════════════════

def build_schedule_html():
    # 按北京日期分组
    all_matches = [m for m in fixtures['matches'] if m.get('stage') == 'group_stage' and m.get('team_a') not in ('', 'TBD')]

    by_date = {}
    for m in all_matches:
        ku = m.get('kickoff_utc', '')
        date_key = m.get('date', '9999-99-99')
        if ku:
            try:
                dt = datetime.fromisoformat(ku.replace('Z', '+00:00')).astimezone(CST)
                date_key = dt.strftime('%Y-%m-%d')
            except:
                pass
        by_date.setdefault(date_key, []).append(m)

    html_blocks = []
    for date_key in sorted(by_date.keys()):
        if date_key.startswith('9999'): continue
        try:
            dt = datetime.strptime(date_key, '%Y-%m-%d')
            weekdays = ['周一','周二','周三','周四','周五','周六','周日']
            date_label = dt.strftime('%m月%d日') + ' ' + weekdays[dt.weekday()]
        except:
            date_label = date_key

        matches = sorted(by_date[date_key], key=lambda x: x.get('kickoff_utc', x.get('date', '')))
        rows = []
        for m in matches:
            mid = m['match_id']
            ta, tb = m['team_a'], m['team_b']
            g = m.get('group', '?')
            md = m.get('matchday', '')
            time_str = get_kickoff_cst(m)
            # 只显示时间部分
            time_only = time_str[6:] if len(time_str) > 5 else time_str
            actual = results_raw.get(mid, {})

            if actual:
                score = actual.get('score', '?')
                outcome = actual.get('outcome', '')
                ca = ' w' if outcome == 'A_WIN' else ''
                cb = ' w' if outcome == 'B_WIN' else ''
                pred = get_pred(mid)
                if pred:
                    arr, ba, bb, ctag = pred_result(pred, ta, tb)
                    correct = (
                        (outcome == 'A_WIN' and ba) or
                        (outcome == 'B_WIN' and bb) or
                        (outcome == 'DRAW' and '平' in arr)
                    )
                    verdict = '<span class="ok">✅</span>' if correct else '<span class="ng">❌</span>'
                    pred_tag = f'{arr}{verdict}'
                else:
                    pred_tag = ''
                rows.append(
                    f'<tr class="played">'
                    f'<td class="tm">{time_only}</td>'
                    f'<td class="grpb">{g}组</td>'
                    f'<td class="ta{ca}">{zh(ta)}</td>'
                    f'<td class="sc"><span class="score">{score}</span><br><span class="pred-sm">{pred_tag}</span></td>'
                    f'<td class="tb{cb}">{zh(tb)}</td>'
                    f'<td class="cf"></td>'
                    f'</tr>'
                )
            else:
                pred = get_pred(mid)
                arr, ba, bb, ctag = pred_result(pred, ta, tb)
                ca = ' w' if ba else ''
                cb = ' w' if bb else ''
                row_cls = 'pred' if pred else 'upcoming'
                rows.append(
                    f'<tr class="{row_cls}">'
                    f'<td class="tm">{time_only}</td>'
                    f'<td class="grpb">{g}组</td>'
                    f'<td class="ta{ca}">{zh(ta)}</td>'
                    f'<td class="sc">{arr}</td>'
                    f'<td class="tb{cb}">{zh(tb)}</td>'
                    f'<td class="cf">{ctag}</td>'
                    f'</tr>'
                )

        html_blocks.append(f'''
<div class="day">
  <div class="day-hd">{date_label}</div>
  <table>
    <tr class="hdr"><th>时间</th><th>小组</th><th>主场</th><th></th><th>客场</th><th>置信</th></tr>
    {''.join(rows)}
  </table>
</div>''')

    return '\n'.join(html_blocks)


# ════════════════════════════════════════════════════════
# CSS 通用样式
# ════════════════════════════════════════════════════════

STYLE = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0a0f1a; color: #e8e8e8; font-family: 'PingFang SC', 'Microsoft YaHei', sans-serif; font-size: 13px; padding: 20px; }
h1 { font-size: 18px; color: #f0c040; text-align: center; margin-bottom: 6px; font-weight: 700; }
.sub { text-align: center; color: #888; font-size: 11px; margin-bottom: 20px; }
.legend { text-align: center; font-size: 11px; color: #aaa; margin-bottom: 16px; }
.legend span { margin: 0 10px; }
.leg-g { color: #4caf80; }
.leg-y { color: #f0c040; }

.grp, .day { margin-bottom: 18px; background: #111827; border-radius: 8px; overflow: hidden; border: 1px solid #1e2d3d; }
.grp-hd, .day-hd { background: #0d1f35; color: #f0c040; font-weight: 700; padding: 8px 12px; font-size: 14px; }
.grp-teams { color: #aaa; font-size: 11px; font-weight: 400; margin-left: 10px; }

table { width: 100%; border-collapse: collapse; }
th { background: #0a1520; color: #888; font-weight: 600; padding: 5px 8px; font-size: 11px; text-align: center; }
td { padding: 6px 8px; border-bottom: 1px solid #1a2535; text-align: center; }
.md, .tm, .grpb { color: #888; font-size: 11px; width: 48px; }
.dt { color: #888; font-size: 11px; width: 80px; }
.ta { text-align: right; font-weight: 500; }
.tb { text-align: left; font-weight: 500; }
.ta.w, .tb.w { color: #f0c040; font-weight: 700; }
.sc { width: 60px; font-weight: 700; }
.cf { width: 36px; }

tr.played td { background: #0d2218; }
tr.played .sc { color: #4caf80; }
tr.pred td { background: #1a1500; }
tr.upcoming td { opacity: 0.5; }

.arr-l { color: #f0c040; font-size: 14px; }
.arr-r { color: #f0c040; font-size: 14px; }
.arr-draw { color: #888; font-size: 13px; }
.arr-vs { color: #555; font-size: 11px; }
.score { font-size: 13px; font-weight: 700; color: #4caf80; }
.pred-sm { font-size: 11px; color: #aaa; display: inline-block; margin-top: 1px; }
.ok { color: #4caf80; font-size: 11px; }
.ng { color: #f44; font-size: 11px; }

.conf { font-size: 10px; padding: 1px 4px; border-radius: 3px; font-weight: 600; }
.c-h { background: #1a3a1a; color: #4caf80; }
.c-m { background: #2a2000; color: #f0c040; }
.c-l { background: #2a1a00; color: #ff9944; }

.grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
@media (max-width: 900px) { .grid { grid-template-columns: repeat(2, 1fr); } }
"""


def write_html(filename, title, content, lang='zh'):
    updated = datetime.now(CST).strftime('%Y-%m-%d %H:%M')
    if lang == 'en':
        sub = f'2026 FIFA World Cup · AI Predictions · Updated {updated} CST'
        leg1 = '■ Green = Played (actual score)'
        leg2 = '■ Yellow = AI Prediction (◀▶ = predicted winner, — = draw)'
        html_lang = 'en'
    else:
        sub = f'2026 FIFA 世界杯 · AI预测 · 更新于 {updated} 北京时间'
        leg1 = '■ 绿色 = 已完赛（实际比分）'
        leg2 = '■ 黄色 = AI预测（◀▶指向赢队，— = 平局）'
        html_lang = 'zh'
    html = f"""<!DOCTYPE html>
<html lang="{html_lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>{STYLE}</style>
</head>
<body>
<h1>{title}</h1>
<p class="sub">{sub}</p>
<div class="legend">
  <span class="leg-g">{leg1}</span>
  <span class="leg-y">{leg2}</span>
</div>
{content}
</body>
</html>"""
    out = BASE / 'web' / filename
    out.write_text(html, encoding='utf-8')
    print(f'  已生成: {out}')


def build_group_html_en():
    """English version of group table."""
    by_group = {}
    for m in fixtures['matches']:
        if m.get('stage') != 'group_stage': continue
        g = m.get('group', '?')
        by_group.setdefault(g, []).append(m)

    html_blocks = []
    for g in sorted(by_group.keys()):
        matches = sorted(by_group[g], key=lambda x: (x.get('matchday', 0), x.get('kickoff_utc', x.get('date', ''))))
        teams = list({m['team_a'] for m in matches} | {m['team_b'] for m in matches})
        teams_en = ' · '.join(EN.get(t, t) for t in sorted(teams))

        rows = []
        for m in matches:
            mid = m['match_id']
            ta, tb = m['team_a'], m['team_b']
            md = m.get('matchday', '')
            time_str = get_kickoff_cst(m)
            actual = results_raw.get(mid, {})

            if actual:
                score = actual.get('score', '?')
                outcome = actual.get('outcome', '')
                ca = ' w' if outcome == 'A_WIN' else ''
                cb = ' w' if outcome == 'B_WIN' else ''
                pred = get_pred(mid)
                if pred:
                    arr, ba, bb, ctag = pred_result(pred, ta, tb)
                    correct = (
                        (outcome == 'A_WIN' and ba) or
                        (outcome == 'B_WIN' and bb) or
                        (outcome == 'DRAW' and '平' in arr)
                    )
                    verdict = '<span class="ok">✅</span>' if correct else '<span class="ng">❌</span>'
                    pred_tag = f'{arr}{verdict}'
                else:
                    pred_tag = ''
                rows.append(
                    f'<tr class="played">'
                    f'<td class="md">MD{md}</td>'
                    f'<td class="dt">{time_str}</td>'
                    f'<td class="ta{ca}">{EN.get(ta,ta)}</td>'
                    f'<td class="sc"><span class="score">{score}</span><br><span class="pred-sm">{pred_tag}</span></td>'
                    f'<td class="tb{cb}">{EN.get(tb,tb)}</td>'
                    f'<td class="cf"></td>'
                    f'</tr>'
                )
            else:
                pred = get_pred(mid)
                arr, ba, bb, ctag = pred_result(pred, ta, tb)
                ca = ' w' if ba else ''
                cb = ' w' if bb else ''
                row_cls = 'pred' if pred else 'upcoming'
                rows.append(
                    f'<tr class="{row_cls}">'
                    f'<td class="md">MD{md}</td>'
                    f'<td class="dt">{time_str}</td>'
                    f'<td class="ta{ca}">{EN.get(ta,ta)}</td>'
                    f'<td class="sc">{arr}</td>'
                    f'<td class="tb{cb}">{EN.get(tb,tb)}</td>'
                    f'<td class="cf">{ctag}</td>'
                    f'</tr>'
                )

        html_blocks.append(f'''
<div class="grp">
  <div class="grp-hd">Group {g} <span class="grp-teams">{teams_en}</span></div>
  <table>
    <tr class="hdr"><th>MD</th><th>CST</th><th>Home</th><th>Score/Pred</th><th>Away</th><th></th></tr>
    {''.join(rows)}
  </table>
</div>''')

    return '\n'.join(html_blocks)


def build_schedule_html_en():
    """English version of schedule table."""
    all_matches = [m for m in fixtures['matches'] if m.get('stage') == 'group_stage' and m.get('team_a') not in ('', 'TBD')]
    by_date = {}
    for m in all_matches:
        ku = m.get('kickoff_utc', '')
        date_key = m.get('date', '9999-99-99')
        if ku:
            try:
                dt = datetime.fromisoformat(ku.replace('Z', '+00:00')).astimezone(CST)
                date_key = dt.strftime('%Y-%m-%d')
            except:
                pass
        by_date.setdefault(date_key, []).append(m)

    html_blocks = []
    for date_key in sorted(by_date.keys()):
        if date_key.startswith('9999'): continue
        try:
            dt = datetime.strptime(date_key, '%Y-%m-%d')
            weekdays = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun']
            date_label = dt.strftime('%b %d') + ' ' + weekdays[dt.weekday()]
        except:
            date_label = date_key

        matches = sorted(by_date[date_key], key=lambda x: x.get('kickoff_utc', x.get('date', '')))
        rows = []
        for m in matches:
            mid = m['match_id']
            ta, tb = m['team_a'], m['team_b']
            g = m.get('group', '?')
            time_str = get_kickoff_cst(m)
            time_only = time_str[6:] if len(time_str) > 5 else time_str
            actual = results_raw.get(mid, {})

            if actual:
                score = actual.get('score', '?')
                outcome = actual.get('outcome', '')
                ca = ' w' if outcome == 'A_WIN' else ''
                cb = ' w' if outcome == 'B_WIN' else ''
                pred = get_pred(mid)
                if pred:
                    arr, ba, bb, ctag = pred_result(pred, ta, tb)
                    correct = (
                        (outcome == 'A_WIN' and ba) or
                        (outcome == 'B_WIN' and bb) or
                        (outcome == 'DRAW' and '平' in arr)
                    )
                    verdict = '<span class="ok">✅</span>' if correct else '<span class="ng">❌</span>'
                    pred_tag = f'{arr}{verdict}'
                else:
                    pred_tag = ''
                rows.append(
                    f'<tr class="played">'
                    f'<td class="tm">{time_only}</td>'
                    f'<td class="grpb">Grp {g}</td>'
                    f'<td class="ta{ca}">{EN.get(ta,ta)}</td>'
                    f'<td class="sc"><span class="score">{score}</span><br><span class="pred-sm">{pred_tag}</span></td>'
                    f'<td class="tb{cb}">{EN.get(tb,tb)}</td>'
                    f'<td class="cf"></td>'
                    f'</tr>'
                )
            else:
                pred = get_pred(mid)
                arr, ba, bb, ctag = pred_result(pred, ta, tb)
                ca = ' w' if ba else ''
                cb = ' w' if bb else ''
                row_cls = 'pred' if pred else 'upcoming'
                rows.append(
                    f'<tr class="{row_cls}">'
                    f'<td class="tm">{time_only}</td>'
                    f'<td class="grpb">Grp {g}</td>'
                    f'<td class="ta{ca}">{EN.get(ta,ta)}</td>'
                    f'<td class="sc">{arr}</td>'
                    f'<td class="tb{cb}">{EN.get(tb,tb)}</td>'
                    f'<td class="cf">{ctag}</td>'
                    f'</tr>'
                )

        html_blocks.append(f'''
<div class="day">
  <div class="day-hd">{date_label}</div>
  <table>
    <tr class="hdr"><th>Time</th><th>Group</th><th>Home</th><th>Score/Pred</th><th>Away</th><th>Conf</th></tr>
    {''.join(rows)}
  </table>
</div>''')

    return '\n'.join(html_blocks)


# ════════════════════════════════════════════════════════
# 主程序
# ════════════════════════════════════════════════════════

if __name__ == '__main__':
    import sys
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')

    print('生成中文按小组预测表...')
    group_content = f'<div class="grid">{build_group_html()}</div>'
    write_html('prediction_group_zh.html', '2026世界杯 · 小组赛AI预测', group_content)

    print('生成中文按赛程预测表...')
    schedule_content = build_schedule_html()
    write_html('prediction_schedule_zh.html', '2026世界杯 · 赛程AI预测', schedule_content)

    print('生成英文按小组预测表...')
    group_content_en = f'<div class="grid">{build_group_html_en()}</div>'
    write_html('prediction_group_en.html', '2026 FIFA World Cup · Group Stage AI Predictions', group_content_en, lang='en')

    print('生成英文按赛程预测表...')
    schedule_content_en = build_schedule_html_en()
    write_html('prediction_schedule_en.html', '2026 FIFA World Cup · Schedule AI Predictions', schedule_content_en, lang='en')

    print('\n截图...')
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch()
            for fname, w in [
                ('prediction_group_zh.html', 1400),
                ('prediction_schedule_zh.html', 900),
                ('prediction_group_en.html', 1400),
                ('prediction_schedule_en.html', 900),
            ]:
                html_path = (BASE / 'web' / fname).resolve()
                out_path  = (BASE / 'web' / fname.replace('.html', '.png')).resolve()
                page = browser.new_page(viewport={'width': w, 'height': 900})
                page.goto(f'file:///{html_path}')
                page.wait_for_load_state('networkidle')
                page.screenshot(path=str(out_path), full_page=True)
                size = out_path.stat().st_size // 1024
                print(f'  {out_path.name}: {size} KB')
            browser.close()
        print('\n完成！')
    except Exception as e:
        print(f'截图失败: {e}')
        print('请手动用浏览器打开 web/ 目录下的 HTML 文件截图')
