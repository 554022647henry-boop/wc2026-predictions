# Ligo哥 · 视频 HTML 展示风格规范

> 来源：飞书脑库 → 文章草稿 → 视频 → HTML展示风格 → `Ligo哥_视频HTML展示风格规范`

---

## 设计系统

### 字体三件套（必须通过 Google Fonts 引入）

| 用途 | 字体 | 变量 | 常用字重 |
|------|------|------|---------|
| 大标题 / 展示文字 | **Syne** | `--f-display` | 700 / 800 |
| 正文 / 说明文字 | **Figtree** | `--f-body` | 400 / 500 / 600 |
| 标签 / 数据 / 代码 | **Space Mono** | `--f-mono` | 400 / 700 |

```html
<link href="https://fonts.googleapis.com/css2?family=Syne:wght@600;700;800&family=Figtree:ital,wght@0,400;0,500;0,600;1,400&family=Space+Mono:wght@400;700&display=swap" rel="stylesheet">
```

### 颜色令牌

```css
:root {
  /* 文字 */
  --ink:       #0a0a0a;   /* 主文字 */
  --ink-2:     #3f3f46;   /* 次级文字 */
  --ink-3:     #71717a;   /* 辅助/标签 */

  /* 背景 */
  --bg:        #ffffff;
  --surface:   #f4f4f5;   /* 卡片底色 */
  --border:    #e4e4e7;   /* 分割线 */

  /* 品牌蓝 */
  --blue:      #1d4ed8;
  --blue-dark: #1e3a8a;   /* Hero 背景 */
  --blue-bg:   #eff6ff;   /* 浅蓝块 */
  --blue-mid:  #dbeafe;   /* 蓝色边框 */
}
```

**扩展色（在日报 HTML 中使用）：**

```css
/* 正确/命中 */
--green:     #15803d;
--green-bg:  #f0fdf4;
--green-mid: #bbf7d0;

/* 错误/失败 */
--red:       #b91c1c;
--red-bg:    #fef2f2;
--red-mid:   #fecaca;

/* 警告/风险 */
--amber:     #b45309;
--amber-bg:  #fffbeb;
--amber-mid: #fde68a;
```

---

## 布局规则

- **外层背景**：`#0d1117`（深夜色）
- **舞台宽度**：`width: 100%; max-width: 640px`，白底，`border-radius: 0`（贴边无圆角）
- **阴影**：`none`（全宽贴边时不需要阴影）
- **body padding**：`padding: 0`（无横向 padding，stage 紧贴窗口边缘）
- **内容区 padding**：水平 `40px`
- **入场动画**：`.stage` 有 `rise` 关键帧（`translateY(32px) → 0`，0.7s）
- **录制说明**：浏览器窗口设为 640×1138（9:16）或 640×852（iPhone 比例），stage 自动贴满，可直接录屏

---

## 核心组件

### Hero 区
- 背景：`--blue-dark`（深海军蓝）+ 横向细线纹理 + 右上角圆形装饰
- 标题：Syne 800，`clamp(30px, 5.5vw, 42px)`，`color:#fff`
- 强调词：`<em>` → `color: #93c5fd`（亮蓝）
- 元数据行：Space Mono 11px，`rgba(255,255,255,.5)`，左侧有 24px 短横线装饰
- 副标题：Figtree 15px，`rgba(255,255,255,.65)`

### 要点列表（.point）
- 两列网格：`48px 1fr`，序号列用 Space Mono 蓝色（视频模板）；**日报失败复盘中序号用红色 `var(--red)`**（更直观，见日报制作说明）
- 每项上方有 1px border 分割，第一项无 border
- 标题：Syne 700 16px；正文：Figtree 14px `--ink-2`

### 洞察引语（.insight）
- 负 margin 拉满宽度（`margin: 0 -40px`）
- 浅蓝背景 + 上下 2px 蓝色边框
- blockquote：Syne 700 **22px**，`--blue-dark`（日报 HTML 中 font-size 必须为 22px）

### 对比行（.compare-row）
- 三列：`1fr auto 1fr`，中间箭头用 Space Mono
- 左侧：删除线文字（灰色）；右侧：加粗，`<span>` 用蓝色强调

### 工具标签（.tool-tag）
- Space Mono 12px，`border-radius: 2px`
- 内含 5 格竖条熟练度 bar
- Hover：border + bg 变蓝

### Footer
- `background: var(--ink)`（黑色）
- 左侧品牌名，右侧期号，均用 Space Mono 低透明度白色

---

## Scroll Reveal 系统

```css
.r { opacity: 0; transform: translateY(16px); transition: opacity 0.55s, transform 0.55s; }
.r.on { opacity: 1; transform: none; }
.r-d1 ~ .r-d5 { transition-delay: .06s ~ .30s; }
```

```js
const io = new IntersectionObserver(entries => {
  entries.forEach(e => { if (e.isIntersecting) { e.target.classList.add('on'); io.unobserve(e.target); } });
}, { threshold: 0.12 });  // 统一 0.12，不用 0.1
document.querySelectorAll('.r').forEach(el => io.observe(el));
// Hero 首屏立即触发
setTimeout(() => document.querySelectorAll('.hero .r').forEach(el => el.classList.add('on')), 200);
```

---

## 日报派生组件（daily_report_*.html 专用）

### 比赛结果卡（.match-card）
- `.hit`：绿色边框 + 绿色 badge + **左侧4px绿色实心条**（`::before`）
- `.miss`：红色边框 + 红色 badge + **左侧4px红色实心条**
- 三列网格展示队徽 + 比分 + 队名
- 比分字号：**52px**（Syne 800）
- 命中/失误展示：`.verdict-tag` 带 emoji 的圆角标签（`✅ 命中` / `❌ 失误`），取代旧版纯文字
- 底部显示预测值

### 预测卡（.pred-card）
- Header：组别 + 时间 + 置信度 badge（高/中/低）
  - 置信度 badge：**渐变色徽章**（白色文字），高→绿渐变、中→琥珀渐变、低→红渐变
- 概率条（.prob-bar-track）：三段 **14px** 加粗圆角条，概率值直接标注在预测方向条上（`.prob-bar-val`）
- **信心对比条（`.confidence-gap`）**：在概率分布下方新增"模型信心 vs 不确定性"双色条，对比"支持率 X%"（预测方向概率）与"反对率 Y%"（其余两个结果概率之和），一眼看出模型的确定程度
- 理由列表：`28px 1fr` 两列，bullet 替换为 **emoji 分类图标**（`.reason-icon`），各类别见日报制作说明中的 emoji 对照表
- 风险块：amber 色左 border，橙色文字

---

## 命名约定

- 日报文件：`daily_report_MMDD.html`
- 模板文件：`ligo_video_style_template.html`（本文件）
- 所有 HTML 存放于 `web/` 或 `web/templates/`
