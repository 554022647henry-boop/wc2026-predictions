# 日报制作说明

## 数据来源

- **今日结果**：`data/results/results.json`（按 `recorded_at` 过滤日期）
- **比赛预测**：`data/predictions/{match_id}/initial_prediction.json`
  - 用 `output.prediction` / `output.confidence` / `output.reasons` / `output.key_risk`
  - 胜平负概率用 `_internal.p_a_win` / `p_draw` / `p_b_win`
- **赛程时间**：`data/fixtures.json` → `kickoff_cst`（北京时间，按此升序排列）

## 结构（固定顺序）

1. **Hero**：日期 + 今日命中率 X/N
2. **今日结果**：按北京时间升序，命中绿框 / 失败红框
3. **Insight 引语**：今日核心教训一句话
4. **失败复盘**：编号分析，结尾加琥珀色教训标签
5. **明日预测**：置信度 badge + 概率条 + 依据 + 风险块
6. **Footer**：`@Ligo哥 · AI预测系统`

## 视觉风格

参考 `ligo_video_style_template.html`，详见 `STYLE_GUIDE.md`。

## 文件命名 & 推送

```
web/daily_report_MMDD.html
```

推送：直接跑 `auto_update.py`，或用 GitHub API 单独推文件（token 在 `C:/Projects/github/.github_token`）。
