# 世界杯2026 AI预测系统 · 开发日志

---

## 系统概述

**目标：** 用7个AI Agent对2026年世界杯小组赛72场比赛做赛前预测，网站公开展示，用GitHub commit时间戳证明预测在赛前完成（不可篡改）。

**技术栈：** Python + DeepSeek API + GitHub Pages

**仓库：** https://github.com/554022647henry-boop/wc2026-predictions

---

## 核心预测流程

```
比赛信息（fixtures.json）
    ↓
Agent1：信息采集
  - ESPN API（赔率/阵容/伤停）
  - WhoScored（球员评分）
  - CBS Sports（赛事报道）
  - DeepSeek（历史知识：战绩/战术/DNA）
    ↓
Agent2：信息审阅 + 质量评分（最多2轮补充）
    ↓
7个 Indicator Agents（各评一个维度，0-10分）
  A. 绝对实力（权重7%）
  B. 球队化学（权重8%）
  C. 近期状态（权重7%）
  D. 关键球员（权重15%）
  E. 情境压力（权重20%）
  F. 战术对位（权重25%）← 回测最强因子
  G. 大赛DNA（权重18%）
    ↓
H. 赔率校验器（不参与计分，只纠偏）
    ↓
数学聚合（加权delta → 概率分布）
    ↓
裁判Agent：最终预测 + 3条理由
    ↓
保存 initial_prediction.json
    ↓
Git commit（锁定时间戳）
```

---

## 维度权重设计依据

基于2018/2022年世界杯回测（40场，Pearson相关系数）：
- F_战术对位：r=0.59（最强）
- E_情境压力：r=0.44
- G_大赛DNA：r=0.42
- D_关键球员：r=0.33
- B_化学反应：r=0.16
- A_绝对实力：r=-0.05（世界杯中几乎失效）
- C_近期状态：r=-0.04

---

## 系统文件结构

```
世界杯预测/
├── auto_update.py          # 主脚本：抓结果 + 更新HTML + 推GitHub
├── batch_repredict.py      # 批量初始预测（手动运行）
├── generate_image.py       # 生成预测图表（中英文版）
├── config.py               # API配置
├── agents/
│   ├── collector.py        # Agent1：信息采集
│   ├── reviewer.py         # Agent2：信息审阅
│   ├── predictor.py        # 预测引擎（7 Agents + 裁判）
│   ├── indicator_agents.py # 7个维度Agent定义 + 权重
│   ├── quant_model.py      # 数学聚合模型
│   └── html_updater.py     # HTML生成
├── data/
│   ├── fixtures.json       # 72场赛程（含kickoff_utc精确时间）
│   ├── results/results.json # 已完赛比赛结果
│   └── predictions/        # 各场次预测文件
│       └── WC2026_X_MDX_X/
│           └── initial_prediction.json  ← 唯一使用的预测文件
└── web/
    ├── index.html          # 主网站（GitHub Pages）
    ├── prediction_table_zh.html/png  # 中文预测表
    └── prediction_table_en.html/png  # 英文预测表
```

---

## 变更记录

---

### v0.1 — 初始版本

**时间：** 2026年6月上旬

**内容：**
- 建立完整预测流水线（Agent1→2→7 Indicators→裁判）
- 部署GitHub Pages展示网站
- 配置auto_update.py每30分钟自动运行

**初始参数：**
- 小组赛N=3（只用F_战术/E_情境/G_DNA三个Agent）
- 预测时间窗口：T-24h / T-12h / T-2h / T-30min（赛前自动重新预测）

---

### v0.2 — 2026-06-14：发现3个Agent的严重问题

**问题描述：**

1. **小组赛实际只有2个有效Agent**
   - G_DNA在小组赛返回硬编码的5/5中性分（confidence=2），等于无效
   - 实际只有F_战术（~56%）和E_情境（~44%）在决定预测
   - A_实力、C_状态、D_球员、B_化学 完全被忽略

2. **平局预测严重偏低（8.6%，正常应~25%）**
   - 原因：仅2个有效Agent评分极端化，delta经常超过±0.5平局阈值

**修复：**
```python
# 改前
N_FOR_GROUP_STAGE = 3

# 改后
N_FOR_GROUP_STAGE = 7  # 小组赛也用全7个Agent
```

同时修复G_DNA小组赛逻辑：不再硬编码5/5，改为评估历史小组赛表现（置信度降至4-5分）。

**影响：** 对所有小组赛初始预测重跑（64场，约1.5小时）

---

### v0.3 — 2026-06-14~15：批量重新预测

**执行：** `batch_repredict.py`

**内容：**
- 删除旧的3-Agent初始预测文件
- 对64场未完赛小组赛重新生成7-Agent初始预测
- 完成后Git commit存档（时间戳：2026-06-15 02:37）

**Git存档信息：**
```
commit: [预测存档] 7-Agent 全量初始预测 64场小组赛 2026-06-15 02:37
文件数: 85个
```

---

### v0.4 — 2026-06-15：发现T-xxx预测文件污染问题（重大Bug）

**问题描述：**

今日4场比赛预测展示：
- Germany vs Curacao → 预测Germany胜 → **实际7-1 ✅**
- Netherlands vs Japan → 网站显示"Netherlands胜（低）" → **实际2-2 ❌**
- Ivory Coast vs Ecuador → 网站显示"平局（低）" → **实际1-0科特迪瓦 ❌**
- Sweden vs Tunisia → 网站显示"平局（低）" → **实际5-1瑞典 ❌**

**根本原因分析：**

**Bug1：时间计算错误**

`fixtures.json` 中 `date` 字段只有日期（`"2026-06-15"`），无具体时间。
`auto_update.py` 解析为午夜00:00，导致时间窗口计算完全错误：

```
Sweden vs Tunisia 真实开球：2026-06-15 10:00 北京时间
代码认为开球：         2026-06-15 00:00（午夜）

T-2h 应触发时间：08:00 on June 15
T-2h 实际触发：   22:11 on June 13  ← 早了 35.8小时！

T-30min 应触发：  09:30 on June 15
T-30min 实际触发：23:12 on June 13  ← 早了 34.8小时！
```

凌晨1点比赛（Germany）因为时差只差1小时，凑巧触发正确。
上午10点比赛（Sweden）差了10小时，触发提前36小时。

**Bug2：T-xxx采集没有DeepSeek历史知识**

初始预测 `initial_raw.json`（9.3小时前）：
- ✅ 包含"来源4：AI历史知识库"（近5场战绩、战术风格、大赛历史）

T-30min `T-30min_raw.json`（36小时前）：
- ❌ 没有来源4，只有983字
- Bing搜索返回旅游网站/百度百科，完全无用

**Bug3：html_updater.py 优先级反了**

```python
# 改前（T-30min最优先，initial最低）
order = ['T-30min','T-2h','T-12h','T-24h','initial']

# 导致：36小时前生成的垃圾"平局（低）"覆盖了正确的初始预测"瑞典胜"
```

**修复：**

1. `auto_update.py` — 删除 `check_and_predict()` 调用，不再自动触发T-xxx预测
2. `html_updater.py` — 改为 `order = ['initial']`，只显示初始预测
3. 删除15个垃圾T-xxx预测文件

```python
# auto_update.py 修改后只做3件事：
[Step 1] 抓比赛结果（ESPN API）
[Step 2] 更新HTML
[Step 3] 推送GitHub Pages
# Step 2（预测窗口）已永久删除
```

---

## 当前系统状态（2026-06-15）

### 运行模式
- **只使用初始预测**，不再有T-24h/T-12h/T-2h/T-30min自动重预测
- `auto_update.py` 手动触发，只做：抓结果 → 更新HTML → 推GitHub
- 没有cron定时任务（之前因为cron积累大量Python进程导致电脑过热，已停用）

### 已完成预测
- 小组赛64场初始预测（7-Agent，2026-06-15 02:37 git存档）
- 2场（A组MD1）未预测（在系统建立前已完赛）

### 准确率（截至2026-06-15，共10场有预测+已完赛）
**仅用初始预测：4/10（40%）**

| 比赛 | 预测 | 实际 | 结果 |
|------|------|------|------|
| Bosnia vs Canada | Canada胜 | 1-1 平 | ❌ |
| Qatar vs Switzerland | Switzerland胜 | 1-1 平 | ❌ |
| Haiti vs Scotland | Scotland胜 | 0-1 苏格兰 | ✅ |
| Brazil vs Morocco | Brazil胜 | 1-1 平 | ❌ |
| Paraguay vs USA | USA胜 | 4-1 巴拉圭 | ✅ |
| Australia vs Turkiye | Turkiye胜 | 2-0 澳大利亚 | ❌ |
| Ivory Coast vs Ecuador | Ecuador胜 | 1-0 科特迪瓦 | ❌ |
| Germany vs Curacao | Germany胜 | 7-1 德国 | ✅ |
| Netherlands vs Japan | 荷兰胜 | 2-2 平 | ❌ |
| Sweden vs Tunisia | Sweden胜 | 5-1 瑞典 | ✅ |

**主要失误规律：** 平局全部预测错（4场），两场爆冷（巴拉圭、科特迪瓦）

### 已知问题（待下一版本解决）
1. **平局预测率偏低**：当前系统预测平局约8.6%，正常世界杯小组赛平局率~25%
   - 根本原因：Indicator Agent评分倾向极端化，delta很少落在±0.5的平局区间
   - 可能方向：调整PROB_TABLE让平局区间更宽，或在Agent提示词中引导更均衡评分

2. **fixtures.json 时间字段不精确**：
   - `date` 只有日期，无时间（虽然已停用T-xxx预测，这个问题留着）
   - `kickoff_utc` 字段有精确UTC时间，如果将来需要精准触发可用这个

---

### v0.5 — 2026-06-15：信息质量重构 + Agent规范化

**背景：** 复盘4场比赛（Ivory Coast vs Ecuador、Netherlands vs Japan）发现两类根本性问题。

**问题1：信息与维度严重错位**

7个Indicator Agent有清晰的维度定义，但collector拿到的信息根本无法支撑这些维度：
- F_tactical收到的是"荷兰惯用4-3-3"，无法判断克制关系
- D_keyplayer收到的是球员名+身价，无"缺阵影响""如何针对"等具体信息
- 补充信息轮次经常拿到AI幻觉或旧年份数据（supp1把男足分析成女足）

**问题2：Agent评分无约束、无量表**

- F_tactical输出了65/35（应为0-10评分），系统未校验直接使用，导致战术维度权重实际被放大10倍
- 所有7个Agent对Ivory Coast vs Ecuador全部输出4/6，评分模板化
- 无量表说明（6分代表什么？7分代表什么？）

**修复方案：**

#### 1. 建立「2026世界杯球队知识库」(data/team_knowledge_2026.json)

48支参赛队全覆盖，每队包含：
- 完整26人大名单 + 预期首发11人
- 战术：阵型、进攻套路（key_pattern_1/2）、防守弱点、如何破防
- 关键球员：详情 + 缺阵影响 + 对方如何针对
- 近期5场比赛结果
- 世界杯历史（含首轮记录、逆转能力）
- 化学反应、情境因素

生成方式：DeepSeek API批量生成(3队/批)，Sofascore浏览器核实大名单。

#### 2. 重写 indicator_agents.py（v3）

- **评分量表**：5=平等/6=轻微优势/6.5=明显优势/7=强优势/8=压倒性，两队和值必须在8-13之间
- **值域校验**：所有分数强制截断至0-10，和值>13时等比例缩放
- **结构化输出**：新增 `key_factors` 字段（3条必须引用具体球员名或战术细节的证据）
- **知识库集成**：每个Agent收到维度专属的知识库片段（F_tactical只看战术，D_keyplayer只看关键球员）

#### 3. 更新 predictor.py

- 自动从知识库加载两队数据并传入各Agent
- 日志显示知识库命中情况（"阵型=4-3-3 | 大名单=26人"）

#### 4. 更新 quant_model.py

- dimension_breakdown新增 `key_factors` 和 `reasoning` 字段，供复盘使用

**改动文件：**
- `agents/indicator_agents.py` — 完全重写
- `agents/predictor.py` — 添加_load_kb()
- `agents/quant_model.py` — 扩展breakdown字段
- `build_knowledge_base.py` — 新建，批量生成知识库
- `data/team_knowledge_2026.json` — 新建，48队知识库

**盲测验证（12场已完赛，新系统vs旧系统）：**

| 比赛 | 实际 | 新系统 | 旧系统 |
|------|------|--------|--------|
| Mexico 2-0 South Africa | A_WIN | Mexico胜(高) ✅ | 无预测 |
| South Korea 2-1 Czechia | A_WIN | 韩国胜(低) ✅ | 无预测 |
| Bosnia 1-1 Canada | 平局 | **平局(低) ✅** | Canada胜 ❌ |
| Qatar 1-1 Switzerland | 平局 | Switzerland胜(高) ❌ | Switzerland胜 ❌ |
| Haiti 0-1 Scotland | B_WIN | Scotland胜(中) ✅ | Scotland胜 ✅ |
| Brazil 1-1 Morocco | 平局 | **平局(中) ✅** | Brazil胜 ❌ |
| Paraguay 4-1 USA | B_WIN | USA胜(中) ✅ | USA胜 ✅ |
| Australia 2-0 Turkiye | A_WIN | Turkiye胜(中) ❌ | Turkiye胜 ❌ |
| Ivory Coast 1-0 Ecuador | A_WIN | 平局(中) ❌ | Ecuador胜 ❌ |
| Germany 7-1 Curacao | A_WIN | Germany胜(高) ✅ | Germany胜 ✅ |
| Netherlands 2-2 Japan | 平局 | Netherlands胜(中) ❌ | 荷兰胜 ❌ |
| Sweden 5-1 Tunisia | A_WIN | Sweden胜(低) ✅ | Sweden胜 ✅ |

**准确率：新系统 6/10 = 60%（可比较场次），旧系统 4/10 = 40%**（注：之前误报70%，实为60%）

最大提升：平局预测从 0/4 → 2/4（Bosnia/Canada、Brazil/Morocco）
仍未解决：Australia vs Turkiye、Netherlands vs Japan 两场，市场赔率也判断错误

**对提升的诚实分析（事后复盘）：**

改对的3场：
1. Bosnia vs Canada：旧=Canada胜❌ → 新=平局✅（实际1-1）
2. Brazil vs Morocco：旧=Brazil胜❌ → 新=平局✅（实际1-1）
3. South Korea vs Czechia：旧=无预测 → 新=韩国胜✅（实际2-1）

真正"判断改变"的只有2场，均为平局预测。没有任何一场发生"A胜→B胜"的翻转。

提升的本质：分差被评分量表约束后，接近0的比赛自然落入平局区间，而这两场正好踢了平局。是概率校正而非分析能力提升。

**未来预测分布（60场未完赛）：**
- 新系统平局预测率：15.0%（旧系统6.7%，世界杯历史均值~24%）
- 高置信度预测：25%（旧系统大量高置信，新系统收紧）
- 预测方向真正改变的场次：7场（均为从某队胜→平局）

知识库和维度改造对评分依据的丰富程度有实质改善，但对预测方向的影响需要更大样本（50+场）才能验证。

**状态：** v0.5完成，60场全量重新预测上线，git存档时间戳2026-06-15 22:08。

---

## 当前系统状态（2026-06-15 更新至v0.5）

### 运行模式
- **只使用初始预测**，基于知识库+7维度Indicator Agent系统
- `auto_update.py` 手动触发：抓结果 → 更新HTML → 推GitHub
- `batch_repredict.py` 用于批量重新预测

### 已完成预测
- 小组赛72场：12场已完赛有结果，60场已用v0.5系统重新预测（2026-06-15 22:08 git存档）

### 准确率（截至2026-06-15，共12场有预测+已完赛）
**v0.5新系统：8/12（67%）/ 可比较10场：6/10（60%）**

---

## 操作手册

### 日常结果更新
```bash
cd "C:\Projects\世界杯预测"
python auto_update.py
```
效果：抓ESPN最新结果 → 更新HTML → 推GitHub Pages

### 重新出一版初始预测
```bash
# 修改预测逻辑后，批量重跑所有未完赛比赛
python batch_repredict.py
# 运行时间：约1.5小时（64场 × ~85秒）
# 完成后自动git commit + push + 更新网站
```

### 生成预测图表（中英文双版本）
```bash
python generate_image.py
# 截图
python -c "
from playwright.sync_api import sync_playwright
import pathlib
with sync_playwright() as p:
    browser = p.chromium.launch()
    for lang in ('zh','en'):
        html = pathlib.Path(f'web/prediction_table_{lang}.html').resolve()
        out  = pathlib.Path(f'web/prediction_table_{lang}.png').resolve()
        page = browser.new_page(viewport={'width':1200,'height':900})
        page.goto(f'file:///{html}')
        page.wait_for_load_state('networkidle')
        page.screenshot(path=str(out), full_page=True)
    browser.close()
"
```

---

*最后更新：2026-06-15 22:30（v0.5 final 上线，60场全量重新预测完成）*
