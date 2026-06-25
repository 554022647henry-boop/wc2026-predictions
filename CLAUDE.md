# 世界杯2026 AI预测系统 · 项目指引

## 这是什么

一个用 **10 个协作 AI Agent** 对 2026 年世界杯每场比赛做赛前结构化预测的系统。7 个维度 Agent 各自独立打分（战术对位、情境压力、大赛 DNA 等），数学公式加权聚合，输出预测方向 + 置信度 + 3 条可解释理由。预测结果发布在 [GitHub Pages 网站](https://554022647henry-boop.github.io/wc2026-predictions/) 上，Git 提交时间戳证明预测不可篡改。

**技术栈：** Python + DeepSeek API（兼容 Anthropic SDK 接口）+ GitHub Pages

---

## 目录结构速览

```
世界杯预测_v2/
├── main.py               ← CLI 总入口（预测/结果录入/启动服务）
├── auto_update.py         ← 定时任务（抓 ESPN 结果 → 录入 → 更新 HTML → 推送）
├── batch_repredict.py     ← 批量重预测所有未完赛比赛
├── scheduler.py           ← 自动调度器（按时间窗口触发预测）
├── build_kb_v2.py         ← 知识库构建（ESPN API 拉取 48 队数据）
├── config.py              ← 全局配置（API 密钥、路径、预测轮次、权重）
│
├── agents/                ← 10 个 AI Agent 模块
│   ├── collector.py       ← Agent 1：信息搜集（ESPN API + Bing 搜索 + AI 知识）
│   ├── reviewer.py        ← Agent 2：信息审阅 + 质量评分（最多 2 轮补充）
│   ├── indicator_agents.py← Agent 3-9：7 个维度评分 Agent
│   ├── predictor.py       ← 数学聚合模型 + 裁判 Agent（最终预测输出）
│   ├── html_updater.py    ← HTML 生成器（预测 → index.html）
│   ├── momentum_agent.py  ← 赛事动能追踪（胜/平/负 + 比分 + xG）
│   ├── match_context.py   ← 比赛上下文信息（读取知识库 v2）
│   ├── odds_analyzer.py   ← 赔率分析校验
│   └── quant_model.py     ← 量化模型（概率分布计算）
│
├── prompts/               ← 7 个 Agent 提示词模板
│   ├── collector_prompt.txt
│   ├── reviewer_prompt.txt
│   ├── judge_prompt.txt
│   ├── strength_agent.txt / tactical_agent.txt / dna_agent.txt
│   ├── momentum_agent.txt / devils_advocate.txt
│
├── data/                  ← 所有运行时数据
│   ├── fixtures.json      ← 104 场比赛赛程（球队、时间、场地）
│   ├── predictions/       ← 72 个子目录，每个含 initial_prediction.json
│   ├── results/           ← 实际比赛结果（results.json）
│   ├── tournament_log.json← 每队赛事动能记录
│   ├── team_knowledge_v2.json ← 48 队知识库（ESPN 真实数据）
│   ├── collected/         ← Agent 1 搜集原始数据（gitignored）
│   ├── reviewed/          ← Agent 2 审阅后结构化数据（gitignored）
│   ├── odds_history/      ← 赔率历史（gitignored）
│   ├── pred_summary.json  ← 预测汇总（生成文件，gitignored）
│   └── pred_tmr.json      ← 明日预测摘要（生成文件，gitignored）
│
├── web/                   ← GitHub Pages 发布根目录
│   ├── index.html         ← 主网站（预测 vs 赛果对比，中英文，分组/日期切换）
│   ├── model_intro.html   ← 模型介绍页
│   ├── daily_report_*.html← 每日日报（gitignored，手工或 Agent 制作）
│   ├── templates/         ← 日报/视频设计规范
│   │   ├── STYLE_GUIDE.md
│   │   ├── 日报制作说明.md
│   │   └── ligo_video_style_template.html
│   └── prediction_*.html/png ← 旧版展示页（保留但不再更新）
│
├── backtest/              ← 回测系统（2018/2022 世界杯数据验证）
│   ├── run_backtest.py / run_all.py
│   ├── dataset_builder.py / report.py / gen_report.py
│   └── data/              ← 历史比赛真实数据
│
├── .github/workflows/deploy.yml ← 自动部署到 GitHub Pages
├── README.md              ← 项目对外介绍
├── DEVLOG.md              ← 开发日志
├── 方案设计.md             ← 中文方案设计文档
└── requirements.txt       ← Python 依赖
```

---

## 核心预测流水线

```
赛程信息 (fixtures.json)
    ↓
Agent 1：信息搜集  ← ESPN API + Bing 搜索 + AI 历史知识
    ↓
Agent 2：信息审阅  ← 给每类信息打质量分，不足触发补充（最多 2 轮）
    ↓
7 个维度 Agent 各自独立评分（0-10 分）
  A. 绝对实力 (7%)    B. 球队化学 (8%)    C. 近期状态 (7%)
  D. 关键球员 (15%)   E. 情境压力 (20%)   F. 战术对位 (25%) ← 最强因子
  G. 大赛 DNA (18%)   H. 赔率校验器（不参与计分，只纠偏）
    ↓
数学聚合：加权分差 → 概率分布 (quant_model.py)
    ↓
裁判 Agent：概率 → 预测方向 + 置信度 + 3 条理由
    ↓
保存 initial_prediction.json + 更新 web/index.html
    ↓
GitHub Pages 自动部署
```

---

## 常见操作命令

### 日常结果更新（比赛踢完后必做）

```bash
# 1. 抓取 ESPN 最新赛果 + 自动录入（推荐）
python auto_update.py

# 2. 手动录入单场结果
python main.py result --match WC2026_A_MD1_1 --outcome "A胜" --score "2-1"

# 3. 手动录入动能日志（按队名）
python main.py log-result --team-a "France" --team-b "Brazil" --result W --score "3-1"

# 4. 查看某队赛事动能
python main.py show-momentum --team "France"

# 5. 重新生成 HTML
python main.py html
```

### 预测相关

```bash
# 初始预测全部 72 场小组赛
python main.py predict-all

# 预测单场
python main.py predict --match WC2026_A_MD1_1

# 批量重预测（跳过已有结果的比赛）
python batch_repredict.py
```

### 本地调试

```bash
# 启动本地 HTTP 服务器预览网站
python main.py serve --port 8080

# 启动自动调度器（按比赛时间触发预测窗口）
python main.py schedule
```

### 知识库

```bash
# 重建 48 队知识库（ESPN API 拉取真实数据）
python build_kb_v2.py
```

---

## 自动化流程（auto_update.py 做了什么）

`auto_update.py` 是核心自动化脚本，由 CronCreate 每 30 分钟调用一次：

1. **抓取赛果** — 从 ESPN API 拉近 3 天比赛结果，自动录入 `data/results/results.json` + `data/tournament_log.json`
2. **检查预测窗口** — 看是否有比赛进入 T-24h / T-12h / T-2h / T-30min 窗口，触发对应轮次的预测（目前预测窗口部分已注释）
3. **重新生成 HTML** — 更新 `web/index.html`
4. **推送日报** — 如果当天 `web/daily_report_MMDD.html` 存在，一并推送到 GitHub Pages
5. **Git 提交 + 推送** — 自动 commit 变更，触发 GitHub Actions 部署

注意：`auto_update.py` 第 14 行有硬编码的 `DEEPSEEK_API_KEY`（已在原仓库 Git 历史中，此处为副本）。

---

## 日报制作流程

### 自动获取今日结果

运行 `python auto_update.py` → 自动从 ESPN 抓取并录入赛果。

### 制作日报 HTML

日报是手工（或由 AI Agent 协助）制作的 HTML 文件，遵循 `web/templates/日报制作说明.md` 的规范：

1. **数据来源**：
   - 今日结果 → `data/results/results.json`（按 `recorded_at` 过滤）
   - 预测内容 → `data/predictions/{match_id}/initial_prediction.json`
   - 赛程时间 → `data/fixtures.json` → `kickoff_cst`

2. **固定结构**：Hero → 明日预测 (SECTION 01) → 今日复盘 (SECTION 02) → 失败复盘 (SECTION 03) → Footer

3. **文件命名**：`web/daily_report_MMDD.html`

4. **推送**：放到 `web/` 目录下，`auto_update.py` 会自动检测并推送

---

## 关键约定

### API 密钥
- `DEEPSEEK_API_KEY` 环境变量 → 使用 DeepSeek（便宜快速，推荐）
- `ANTHROPIC_API_KEY` 环境变量 → 使用原生 Anthropic SDK
- `config.py` 中的 `make_client()` 函数自动选择

### 路径
- `config.py` 中的路径是硬编码的 `D:\Projects\世界杯预测`，在新副本中可能需要调整
- `HTML_FILE` 指向 `web/index.html`（不是根目录的 index.html）

### 比赛 ID 格式
- 格式：`WC2026_{组}_{轮次}_{场次}`，如 `WC2026_A_MD1_1`（A 组第 1 轮第 1 场）
- 48 队 12 组 × 每轮 2 场 × 3 轮 = 72 场小组赛

### 预测 JSON 结构
每个 `initial_prediction.json` 包含：
- `output`：`prediction`（预测方向）、`confidence`（高/中/低）、`reasons`（3 条理由）、`key_risk`
- `_internal`：7 个维度的评分详情、权重、推理过程
- `actual_result`：赛后填入（初始为 null）

### Git 工作流
- 预测结果 commit 到仓库 → GitHub Actions 自动部署 `web/` 到 Pages
- `data/collected/`、`data/reviewed/`、`data/odds_history/` 已 gitignored（运行时数据）
- `web/daily_report_*.html` 已 gitignored（生成的日报）

---

## 注意事项

1. **不要用 AI 生成球队名单/近期战绩** — 必须从 ESPN API 获取真实数据（有 `_source` + `_verified` 字段区分）
2. **config.py 在 .gitignore 中** — 新环境克隆后需要手动创建
3. **`data/predictions/` 是核心数据** — 72 场比赛的预测都在里面，不要误删
4. **根目录曾经有一个 `index.html`** — 是旧版本残留，网站实际用的是 `web/index.html`
5. **`auto_update.py` 中的预测窗口部分已被注释** — 目前只做结果抓取 + HTML 更新，不触发新的赛前预测
