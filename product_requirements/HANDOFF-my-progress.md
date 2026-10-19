# Handoff — Verify Quality: "My Progress" tab

Single self-contained file: `verify-quality-progress.html` (inline CSS + JS, no build step, no dependencies except Google Fonts). All data is mock and flagged below for API replacement.

## What this is
The **My Progress** tab inside Verify Quality — merges the old History tab with a validator leaderboard. Tab order in the page: `Review & Earn | My Progress`.

## Layout
- **Top (full width):** validator identity + stat strip.
  - Badges: **Validator** (green, hero) and **Amplifier** (grey, secondary). A user can hold both; render whichever apply.
  - Stat strip: Prisma earned, Uploads reviewed, Acceptance rate, This week.
  - "Your rank #N" sits inline on the right.
- **Bottom (two equal cards, `520px` fixed height):**
  - **Left — Leaderboard:** ranks validators by uploads/Prisma. Top 3 get medal icons + a divider. List scrolls internally. The current user's row is highlighted (green) and appended at the bottom of the list — it scrolls with the list, not pinned.
  - **Right — Review history:** table of the user's past reviews with pagination.

## Data to wire (all mock — replace with API)
Three JS arrays near the bottom `<script>`:

1. **`topBoard`** — leaderboard rows, pre-sorted by rank (index order = rank).
   `{ name, uploads: <int>, prisma: <int> }`
2. **`you`** — the current user's leaderboard row (rendered highlighted at list bottom).
   `{ name, uploads, prisma, rank: <int>, me: true }`
3. **`history`** — review history rows.
   `{ id, task, time, score: <0–100>, points: <int>, state: "pending"|"earned"|"failed" }`

The stat strip values (Prisma earned, Uploads reviewed, Acceptance rate, This week) and the "Your rank #N" are currently **hardcoded in the HTML** — bind these to the user object too.

Render targets: leaderboard rows inject into `#lb-scroll`, history rows into `#hist-body`.

## Prisma Points column (history) — 3 states
- **pending** — amount shown, "PENDING" label (grey). Potential points, review in progress.
- **earned** — amount shown, "EARNED" label (green). Credited.
- **failed** — amount shown as `—`, "FAILED" label (grey). No points earned.

Value stacks above the state label (vertical).

## Quality Score
`score` (0–100) shows a small dot: green if ≥85, grey otherwise. Number stays white. Threshold in `scoreColor()`.

## Design tokens / palette
Dark theme, page bg `#2a2a2a`, cards `#232323`. Fonts: Newsreader (headings), Outfit (body).
Intentionally restrained to **two accents**:
- `--gold: #c9bca8` (warm greige) → Prisma values only.
- `--green: #60c87a` → validator identity + positive status.
Blue/amber/red exist as tokens but are **not** used as text colors (kept only for muted medal icons). Keep new UI on this two-accent scheme.

## Known stubs / notes
- Pagination (`1 / 1`) is visual only — no paging logic.
- Leaderboard is display-only (no sort/filter; time-range chips were removed).
- Both bottom cards are locked to equal height; if real history is short its card will have empty space below the pager (intended, for balance).
- Nav, rail, tabs are static — hook up routing as per the rest of the app.

---

---

# 交接文档 — Verify Quality："My Progress" 标签页

单一独立文件：`verify-quality-progress.html`（内联 CSS + JS，无需构建步骤，除 Google Fonts 外无其他依赖）。所有数据均为 mock 数据，待替换项已在下方标注。

## 功能说明
**My Progress** 标签页位于 Verify Quality 模块内 — 将原有的 History 标签页与验证者排行榜合并为一个页面。页面标签顺序：`Review & Earn | My Progress`。

## 布局
- **顶部（全宽）：** 验证者身份信息 + 数据统计栏。
  - 徽章：**Validator**（绿色，主徽章）和 **Amplifier**（灰色，次要徽章）。用户可同时持有两个徽章；根据实际情况渲染对应徽章。
  - 数据统计栏：已获得 Prisma、已审核上传量、通过率、本周数据。
  - "您的排名 #N" 内联显示在右侧。
- **底部（两张等宽卡片，固定高度 `520px`）：**
  - **左侧 — 排行榜：** 按上传量/Prisma 对验证者进行排名。前 3 名显示奖牌图标 + 分割线。列表支持内部滚动。当前用户行高亮显示（绿色），追加在列表底部 — 随列表滚动，不固定置顶。
  - **右侧 — 审核历史：** 显示用户历史审核记录的表格，支持分页。

## 需接入的数据（均为 mock — 替换为 API）
`<script>` 底部附近有三个 JS 数组：

1. **`topBoard`** — 排行榜数据行，已按排名预排序（数组索引顺序即排名）。
   `{ name, uploads: <int>, prisma: <int> }`
2. **`you`** — 当前用户的排行榜数据行（在列表底部高亮显示）。
   `{ name, uploads, prisma, rank: <int>, me: true }`
3. **`history`** — 审核历史数据行。
   `{ id, task, time, score: <0–100>, points: <int>, state: "pending"|"earned"|"failed" }`

数据统计栏中的数值（已获得 Prisma、已审核上传量、通过率、本周数据）以及"您的排名 #N"当前**硬编码在 HTML 中** — 请将这些数据也绑定到用户对象。

渲染目标：排行榜行注入 `#lb-scroll`，历史记录行注入 `#hist-body`。

## Prisma 积分列（历史记录）— 3 种状态
- **pending（待定）** — 显示积分数量，附带"PENDING"标签（灰色）。表示潜在积分，审核进行中。
- **earned（已获得）** — 显示积分数量，附带"EARNED"标签（绿色）。已入账。
- **failed（失败）** — 积分显示为 `—`，附带"FAILED"标签（灰色）。未获得任何积分。

数值显示在状态标签上方（纵向排列）。

## 质量评分
`score`（0–100）显示一个小圆点：≥85 时为绿色，否则为灰色。数字保持白色。阈值逻辑在 `scoreColor()` 函数中。

## 设计 Token / 色板
深色主题，页面背景 `#2a2a2a`，卡片背景 `#232323`。字体：Newsreader（标题）、Outfit（正文）。
强调色刻意精简为**两种**：
- `--gold: #c9bca8`（暖灰褐色）→ 仅用于 Prisma 数值。
- `--green: #60c87a` → 验证者身份标识 + 正面状态。
蓝色/琥珀色/红色作为 Token 存在，但**不作为文字颜色使用**（仅用于奖牌图标的低饱和度效果）。新 UI 开发请遵循此双强调色方案。

## 已知存根 / 注意事项
- 分页（`1 / 1`）仅为视觉展示 — 暂无分页逻辑。
- 排行榜仅展示（无排序/筛选功能；时间范围切换已移除）。
- 两张底部卡片高度锁定相等；若真实历史记录较少，其卡片底部会留有空白（设计预期，保持视觉平衡）。
- 导航栏、侧边栏、标签页均为静态 — 请按应用整体路由规范接入。
