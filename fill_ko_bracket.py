"""填充淘汰赛对阵图：添加预测徽标 + 更新对阵队名 + 冠军高亮"""
import json, re, sys
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

predictions = json.loads(
    Path('web/ko_predictions.js').read_text(encoding='utf-8')
    .split('=', 1)[1].strip().rstrip(';')
)

CN = {
    'Canada':'加拿大','South Africa':'南非','Brazil':'巴西','Japan':'日本',
    'Netherlands':'荷兰','Morocco':'摩洛哥','Germany':'德国','Paraguay':'巴拉圭',
    'Ivory Coast':'科特迪瓦','Norway':'挪威','Mexico':'墨西哥','Ecuador':'厄瓜多尔',
    'France':'法国','Sweden':'瑞典','Belgium':'比利时','Senegal':'塞内加尔',
    'United States':'美国','Bosnia':'波黑','England':'英格兰','DR Congo':'刚果',
    'Spain':'西班牙','Austria':'奥地利','Portugal':'葡萄牙','Croatia':'克罗地亚',
    'Switzerland':'瑞士','Algeria':'阿尔及利亚','Australia':'澳大利亚','Egypt':'埃及',
    'Argentina':'阿根廷','Cape Verde':'佛得角','Colombia':'哥伦比亚','Ghana':'加纳',
    'Bosnia and Herzegovina':'波黑',
}

FLAGS = {
    'Argentina':'🇦🇷','Australia':'🇦🇺','Austria':'🇦🇹',
    'Belgium':'🇧🇪','Brazil':'🇧🇷','Canada':'🇨🇦',
    'Cape Verde':'🇨🇻','Colombia':'🇨🇴','Croatia':'🇭🇷',
    'DR Congo':'🇨🇩','Ecuador':'🇪🇨','Egypt':'🇪🇬',
    'England':'🏴󠁧󠁢󠁥󠁮󠁧󠁿','France':'🇫🇷','Germany':'🇩🇪',
    'Ghana':'🇬🇭','Ivory Coast':'🇨🇮','Japan':'🇯🇵',
    'Mexico':'🇲🇽','Morocco':'🇲🇦','Netherlands':'🇳🇱',
    'Norway':'🇳🇴','Paraguay':'🇵🇾','Portugal':'🇵🇹',
    'Senegal':'🇸🇳','South Africa':'🇿🇦','Spain':'🇪🇸',
    'Sweden':'🇸🇪','Switzerland':'🇨🇭','United States':'🇺🇸',
    'Algeria':'🇩🇿','Bosnia':'🇧🇦','Bosnia and Herzegovina':'🇧🇦',
}

# ── 预加载实际结果（results.json + fixtures 内联结果）────────
ACTUAL_WINNERS = {}  # mid → winner team name
RESULT_SCORES = {}   # mid → {'score': '2-1', 'outcome': 'A_WIN', 'team_a': ..., 'team_b': ...}
_res_file = Path('data/results/results.json')
_fix_file = Path('data/fixtures.json')
if _res_file.exists():
    _r = json.loads(_res_file.read_text(encoding='utf-8'))
    _fix = json.loads(_fix_file.read_text(encoding='utf-8'))
    _fix_lookup = {m['match_id']: m for m in _fix.get('matches', [])}
    for _mid, _res in _r.items():
        if _mid.startswith('_'):
            continue
        _m = _fix_lookup.get(_mid)
        if not _m:
            continue
        _outcome = _res.get('outcome', '')
        RESULT_SCORES[_mid] = {
            'score': _res.get('score', ''),
            'outcome': _outcome,
            'team_a': _m['team_a'],
            'team_b': _m['team_b'],
        }
        if _outcome == 'A_WIN':
            ACTUAL_WINNERS[_mid] = _m['team_a']
        elif _outcome == 'B_WIN':
            ACTUAL_WINNERS[_mid] = _m['team_b']
    # 也检查 fixtures 中的内联结果
    for _mid, _m in _fix_lookup.items():
        if _m.get('result') and _mid not in ACTUAL_WINNERS:
            ACTUAL_WINNERS[_mid] = _m['team_a']
            RESULT_SCORES[_mid] = {
                'score': _m['result'],
                'outcome': 'A_WIN',
                'team_a': _m['team_a'],
                'team_b': _m['team_b'],
            }

# ── 淘汰赛对阵树（与 predict_ko_cascade.py 一致）────────────────
BRACKET_TREE = {
    'WC2026_R32_01': {'feeds': 'WC2026_R16_02', 'side': 'A'},
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
    'WC2026_R16_01': {'feeds': 'WC2026_QF_01', 'side': 'A'},
    'WC2026_R16_02': {'feeds': 'WC2026_QF_01', 'side': 'B'},
    'WC2026_R16_03': {'feeds': 'WC2026_QF_03', 'side': 'A'},
    'WC2026_R16_04': {'feeds': 'WC2026_QF_03', 'side': 'B'},
    'WC2026_R16_05': {'feeds': 'WC2026_QF_02', 'side': 'A'},
    'WC2026_R16_06': {'feeds': 'WC2026_QF_02', 'side': 'B'},
    'WC2026_R16_07': {'feeds': 'WC2026_QF_04', 'side': 'A'},
    'WC2026_R16_08': {'feeds': 'WC2026_QF_04', 'side': 'B'},
    'WC2026_QF_01': {'feeds': 'WC2026_SF_01', 'side': 'A'},
    'WC2026_QF_02': {'feeds': 'WC2026_SF_01', 'side': 'B'},
    'WC2026_QF_03': {'feeds': 'WC2026_SF_02', 'side': 'A'},
    'WC2026_QF_04': {'feeds': 'WC2026_SF_02', 'side': 'B'},
    'WC2026_SF_01': {'feeds': 'WC2026_FINAL', 'side': 'A'},
    'WC2026_SF_02': {'feeds': 'WC2026_FINAL', 'side': 'B'},
}


def get_predicted_winner(mid):
    """从 ko_predictions.js 获取某场比赛的预测胜者。
    如果比赛已有实际结果，返回实际胜者。"""
    # 先检查 actual_winners（预加载了 results.json + fixtures 内联结果）
    if mid in ACTUAL_WINNERS:
        return ACTUAL_WINNERS[mid]
    p = predictions.get(mid)
    if not p:
        return None
    pred_str = p.get('prediction', '')
    if pred_str.endswith('胜'):
        return pred_str[:-1]
    return None


def get_ko_teams(mid):
    """
    根据 BRACKET_TREE 递归确定某场淘汰赛的预测对阵双方。
    返回 (team_a_name, team_b_name) 英文名。
    """
    feeders = [fm for fm, fi in BRACKET_TREE.items() if fi.get('feeds') == mid]
    teams = {}
    for fm in feeders:
        side = BRACKET_TREE[fm].get('side', 'A')
        winner = get_predicted_winner(fm)
        if winner:
            teams[side] = winner
    return teams.get('A'), teams.get('B')


def pred_badge_html(mid):
    p = predictions.get(mid)
    if not p: return ''
    pred_str = p.get('prediction', '')
    conf = p.get('confidence', '')
    if not pred_str: return ''
    for en, cn_name in CN.items():
        pred_str = pred_str.replace(en, cn_name)
    cls = {'高':'high','中':'mid','低':'low'}.get(conf, 'mid')
    return f'<div class="pred-badge show {cls}" data-match="{mid}">{pred_str} · {conf}</div>'


def find_card_boundary(html, class_name, start_from=0):
    """在 HTML 中找到 class 匹配的卡片，返回 (start, end) 位置。"""
    pattern = f'<div class="m {class_name}'
    pos = html.find(pattern, start_from)
    if pos == -1:
        return None
    tag_end = html.find('>', pos)
    if tag_end == -1:
        return None
    i = tag_end + 1
    depth = 1
    while depth > 0 and i < len(html):
        next_open = html.find('<div', i)
        next_close = html.find('</div>', i)
        if next_close == -1:
            break
        if next_open != -1 and next_open < next_close:
            depth += 1
            gt = html.find('>', next_open)
            if gt == -1: break
            i = gt + 1
        else:
            depth -= 1
            if depth == 0:
                return (pos, next_close + 6)
            i = next_close + 6
    return None


html = Path('web/knockout_bracket.html').read_text(encoding='utf-8')

# ═══════════════════════════════════════════════════════════════
# 1. R32 卡片：添加预测徽标（15 场，R32_01 已完赛跳过）
# ═══════════════════════════════════════════════════════════════
R32_BADGE_CARDS = [
    ('l-r32-04', 'WC2026_R32_04'),
    ('l-r32-07', 'WC2026_R32_07'),
    ('l-r32-03', 'WC2026_R32_03'),
    ('l-r32-12', 'WC2026_R32_12'),
    ('l-r32-11', 'WC2026_R32_11'),
    ('l-r32-09', 'WC2026_R32_09'),
    ('l-r32-08', 'WC2026_R32_08'),
    ('r-r32-02', 'WC2026_R32_02'),
    ('r-r32-05', 'WC2026_R32_05'),
    ('r-r32-06', 'WC2026_R32_06'),
    ('r-r32-10', 'WC2026_R32_10'),
    ('r-r32-15', 'WC2026_R32_15'),
    ('r-r32-14', 'WC2026_R32_14'),
    ('r-r32-13', 'WC2026_R32_13'),
    ('r-r32-16', 'WC2026_R32_16'),
]

for cls_name, mid in reversed(R32_BADGE_CARDS):
    badge = pred_badge_html(mid)
    if not badge:
        print(f'  ⏭️ {cls_name} ({mid}): 无预测')
        continue
    boundary = find_card_boundary(html, cls_name)
    if not boundary:
        print(f'  ⚠️ {cls_name}: 未找到')
        continue
    start, end = boundary
    card_content = html[start:end]
    cleaned = re.sub(r'<div class="pred-badge[^>]*>.*?</div>', '', card_content, flags=re.DOTALL)
    insert_pos = cleaned.rfind('</div>')
    if insert_pos == -1:
        print(f'  ⚠️ {cls_name}: 无闭合标签')
        continue
    new_card = cleaned[:insert_pos] + badge + cleaned[insert_pos:]
    html = html[:start] + new_card + html[end:]
    print(f'  ✅ {cls_name} ({mid}): 已添加 R32 徽标')

# ═══════════════════════════════════════════════════════════════
# 2. R16/QF/SF 卡片：添加预测徽标（原有逻辑）
# ═══════════════════════════════════════════════════════════════
BADGE_CARDS = [
    ('l-r16-1', 'WC2026_R16_01'),
    ('l-r16-2', 'WC2026_R16_02'),
    ('l-r16-5', 'WC2026_R16_05'),
    ('l-r16-6', 'WC2026_R16_06'),
    ('r-r16-3', 'WC2026_R16_03'),
    ('r-r16-4', 'WC2026_R16_04'),
    ('r-r16-7', 'WC2026_R16_07'),
    ('r-r16-8', 'WC2026_R16_08'),
    ('l-qf-1', 'WC2026_QF_01'),
    ('l-qf-2', 'WC2026_QF_02'),
    ('r-qf-3', 'WC2026_QF_03'),
    ('r-qf-4', 'WC2026_QF_04'),
    ('l-sf', 'WC2026_SF_01'),
    ('r-sf', 'WC2026_SF_02'),
]

for cls_name, mid in reversed(BADGE_CARDS):
    badge = pred_badge_html(mid)
    if not badge:
        print(f'  ⏭️ {cls_name} ({mid}): 无预测')
        continue
    boundary = find_card_boundary(html, cls_name)
    if not boundary:
        print(f'  ⚠️ {cls_name}: 未找到')
        continue
    start, end = boundary
    card_content = html[start:end]
    cleaned = re.sub(r'<div class="pred-badge[^>]*>.*?</div>', '', card_content, flags=re.DOTALL)
    insert_pos = cleaned.rfind('</div>')
    if insert_pos == -1:
        print(f'  ⚠️ {cls_name}: 无闭合标签')
        continue
    new_card = cleaned[:insert_pos] + badge + cleaned[insert_pos:]
    html = html[:start] + new_card + html[end:]
    print(f'  ✅ {cls_name} ({mid}): 已添加徽标')

# ═══════════════════════════════════════════════════════════════
# 3. R16/QF/SF 卡片：TBD 队名 → 预测晋级队伍
# ═══════════════════════════════════════════════════════════════
row_re = re.compile(r'<div class="row[^"]*">.*?</div>', re.DOTALL)

for cls_name, mid in BADGE_CARDS:
    boundary = find_card_boundary(html, cls_name)
    if not boundary:
        continue
    start, end = boundary
    card = html[start:end]

    team_a, team_b = get_ko_teams(mid)
    if not team_a or not team_b:
        print(f'  ⏭️ {cls_name} ({mid}): 无法确定对阵')
        continue

    predicted_winner = get_predicted_winner(mid)
    team_rows_list = [team_a, team_b]

    all_rows = row_re.findall(card)
    for row_idx, row_html in enumerate(all_rows):
        if row_idx >= len(team_rows_list):
            break
        team = team_rows_list[row_idx]
        # 跳过 meta 行（class="meta" 不匹配 row 正则）
        flag = FLAGS.get(team, '🏳️')
        cn_name = CN.get(team, team)
        is_win = (team == predicted_winner)
        # 只替换含有 <span class="flag"> 的队名行
        if '<span class="flag">' not in row_html:
            continue
        new_row = f'<div class="row{" win" if is_win else ""}"><span class="flag">{flag}</span><span class="nm">{cn_name}</span></div>'
        card = card.replace(row_html, new_row, 1)
        print(f'  ✅ {cls_name} ({mid}): 行{row_idx+1} → {cn_name}')

    html = html[:start] + card + html[end:]

# ═══════════════════════════════════════════════════════════════
# 3b. 已完赛 R32 卡片：更新 tag（去掉"进行中"）和比分
# ═══════════════════════════════════════════════════════════════
for cls_name, mid in R32_BADGE_CARDS:
    res = RESULT_SCORES.get(mid)
    if not res:
        continue
    # 跳过 R32_01（已在 HTML 中硬编码完成）
    boundary = find_card_boundary(html, cls_name)
    if not boundary:
        continue
    start, end = boundary
    card = html[start:end]

    # 替换 tag: tag-live / tag-future → tag-done
    card = re.sub(
        r'<span class="tag tag-live">[^<]*</span>',
        '<span class="tag tag-done">✅ 完赛</span>',
        card
    )
    card = re.sub(
        r'<span class="tag tag-future">[^<]*</span>',
        '<span class="tag tag-done">✅ 完赛</span>',
        card
    )

    # 解析比分
    score_str = res.get('score', '')
    outcome = res.get('outcome', '')
    m = re.match(r'(\d+)-(\d+)', score_str)
    if m:
        a_score, b_score = m.group(1), m.group(2)
        team_a_name = res.get('team_a', '')
        team_b_name = res.get('team_b', '')
        # 更新比分: 第一行是 team_a, 第二行是 team_b
        rows = re.findall(r'<div class="row[^"]*">.*?</div>', card, re.DOTALL)
        for row_idx, row_html in enumerate(rows):
            this_score = a_score if row_idx == 0 else b_score
            # 已有 <span class="sc"> 则替换内容，否则插入
            if '<span class="sc">' in row_html:
                new_row = re.sub(
                    r'<span class="sc">[^<]*</span>',
                    f'<span class="sc">{this_score}</span>',
                    row_html
                )
            else:
                # 在 </div> 前插入
                new_row = row_html.rstrip()
                if new_row.endswith('</div>'):
                    new_row = new_row[:-6] + f'<span class="sc">{this_score}</span></div>'
            card = card.replace(row_html, new_row, 1)

    html = html[:start] + card + html[end:]
    print(f'  ✅ {cls_name} ({mid}): 更新赛果 tag + 比分')

# ═══════════════════════════════════════════════════════════════
# 4. 决赛卡片：更新队名（final-card 不是 m 类，单独处理）
# ═══════════════════════════════════════════════════════════════
final_teams = get_ko_teams('WC2026_FINAL')
if final_teams and final_teams[0] and final_teams[1]:
    sf1_winner, sf2_winner = final_teams
    final_predicted_winner = get_predicted_winner('WC2026_FINAL')

    fc_marker = '<div class="final-card">'
    fc_pos = html.find(fc_marker)
    if fc_pos != -1:
        fc_tag_end = html.find('>', fc_pos)
        i = fc_tag_end + 1
        depth = 1
        fc_end = len(html)
        while depth > 0 and i < len(html):
            next_open = html.find('<div', i)
            next_close = html.find('</div>', i)
            if next_close == -1:
                break
            if next_open != -1 and next_open < next_close:
                depth += 1
                gt = html.find('>', next_open)
                if gt == -1: break
                i = gt + 1
            else:
                depth -= 1
                if depth == 0:
                    fc_end = next_close + 6
                    break
                i = next_close + 6

        fc_html = html[fc_pos:fc_end]
        tbd_rows_fc = re.findall(r'<div class="row tbd">.*?</div>', fc_html, re.DOTALL)
        for i, team in enumerate([sf1_winner, sf2_winner]):
            if i >= len(tbd_rows_fc):
                break
            flag = FLAGS.get(team, '🏳️')
            cn_name = CN.get(team, team)
            is_win = (team == final_predicted_winner)
            new_row = f'<div class="row{" win" if is_win else ""}"><span class="flag">{flag}</span><span class="nm">{cn_name}</span></div>'
            fc_html = fc_html.replace(tbd_rows_fc[i], new_row, 1)

        html = html[:fc_pos] + fc_html + html[fc_end:]
        print(f'  ✅ 决赛: 更新对阵 → {CN.get(sf1_winner, sf1_winner)} vs {CN.get(sf2_winner, sf2_winner)}')

# ═══════════════════════════════════════════════════════════════
# 5. 决赛冠军预测 + 去重
# ═══════════════════════════════════════════════════════════════
final_pred = predictions.get('WC2026_FINAL')
if final_pred:
    p = final_pred.get('prediction', '')
    c = final_pred.get('confidence', '')
    for en, cn_name in CN.items():
        p = p.replace(en, cn_name)

    champ_div = (f'<div class="final-pred" style="margin-top:6px;padding:4px 8px;'
                 f'background:rgba(255,215,0,0.12);border-radius:6px;'
                 f'font-family:var(--f-display);font-size:11px;font-weight:700;'
                 f'color:#ffd700;text-align:center;letter-spacing:0.05em;">'
                 f'🏆 {p} · {c}</div>')

    # 去重
    html = re.sub(r'<div class="final-pred[^>]*>.*?</div>\s*', '', html, flags=re.DOTALL)

    third_pos = html.find('<div class="third">')
    if third_pos != -1:
        html = html[:third_pos] + champ_div + '\n  ' + html[third_pos:]

    print(f'  ✅ 决赛冠军预测已添加')

    # 顶部横幅
    winner_cn = p.replace('胜', '').strip() if p.endswith('胜') else ''
    if winner_cn:
        banner = (f'<div style="text-align:center;margin:-20px auto 20px;padding:6px 16px;'
                  f'background:rgba(255,215,0,0.08);border:1px solid rgba(255,215,0,0.15);'
                  f'border-radius:8px;display:inline-block;font-family:var(--f-display);'
                  f'font-size:14px;font-weight:700;color:#ffd700;letter-spacing:0.08em;'
                  f'max-width:600px;">'
                  f'🏆 AI 预测冠军：{winner_cn} <span style="font-weight:400;opacity:0.6;">({c}置信)</span>'
                  f'</div>')
        html = re.sub(
            r'<div style="text-align:center;margin:-20px auto 20px;padding:6px 16px;background:rgba\(255,215,0,0\.08\).*?</div>',
            '', html, flags=re.DOTALL
        )
        html = html.replace('</h1>', f'</h1>\n  {banner}')
        print(f'  ✅ 冠军横幅：{winner_cn}')

print(f'\n写入 web/knockout_bracket.html...')
Path('web/knockout_bracket.html').write_text(html, encoding='utf-8')
print('完成！')
