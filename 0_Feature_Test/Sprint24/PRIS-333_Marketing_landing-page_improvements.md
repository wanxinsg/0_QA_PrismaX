# PRIS-333 Marketing Landing Page Improvements

> 分析日期：2026-08-27（v1）/ 2026-09-02（v3 补充更新）  
> 数据来源：git log / diff、源码；未执行远端部署验证。

---

## 1. 范围与 Commit 清单

### v1（2026-08-26，仅 `prismax-marketing-rp`，PR [#9](https://github.com/PrismaXAI/prismax-marketing-rp/pull/9)）

| Commit | 日期 | 说明 |
| --- | --- | --- |
| `9e679a9` | 2026-08-26 | Events：替换末尾 3 条活动 + 图片 rename |
| `1aa58a5` | 2026-08-26 | Network：中心从 SVG 轨道换成 GIF + 金色叠色 |
| `475450b` | 2026-08-26 | NetworkOrbit 加废弃注释（未删除文件） |

**基线：** `1bfd970`（PR [#8](https://github.com/PrismaXAI/prismax-marketing-rp/pull/8)，2026-08-21）已实现 Events 自动分桶 + hover 预览图 + 外链 CTA。

### <span style="color:#2563eb">v3（2026-09-01，三仓库联动，PR #12 / #68 / #81）</span>

<span style="color:#2563eb">

| 仓库 | Commit 范围 | PR |
| --- | --- | --- |
| `prismax-marketing-rp` | `bcc6ad7`（含）→ `f963626`，已合入 `main` | [#12](https://github.com/PrismaXAI/prismax-marketing-rp/pull/12) |
| `app-prismax-rp-backend` | `05a6224`（含）→ `e616402` | [#68](https://github.com/PrismaXAI/app-prismax-rp-backend/pull/68) |
| `app-prismax-rp`（Admin） | `a80c6b4`（含）→ `96e0a40` | [#81](https://github.com/PrismaXAI/app-prismax-rp/pull/81) |

| Commit | 仓库 | 说明 |
| --- | --- | --- |
| `bcc6ad7` | marketing | Events 整表重构：条目/CTA 动词/年份显示/预览图 |
| `fc705ab` | marketing | 全站链接更新（Blog 域名、Robotics Data 新开标签等） |
| `55ef405` | marketing | FieldNotes → Latest 重命名；文案/字体微调 |
| `ea12d35` | marketing | Latest 改为动态拉取 blog articles.js + fallback + 单测 |
| `9f2a50e` | marketing | Request Access 弹窗 + Plans/Network 接入 limited release |
| `bc24d7c` | marketing | Modal / BrandKit / Plans 样式微调 |
| `05a6224` | backend | 新增 `POST /api/marketing/request-access` + Admin 列表 API |
| `81be54a` | backend | Contact Sales 表名统一为 `marketing_contact_sales_submissions` |
| `a80c6b4` | admin app | Admin Portal 新增 Marketing Interest Access Requests 表格 |

> 注：`34407a5`（lanmanc）改 `/robotic-data` 页随 PR #12 合入，不在 Aparna 范围，需单独回归。

</span>

---

## 2. 首页区块顺序（最终状态）

```text
Landing page（app/(marketing)/page.tsx）
  Hero → HeroShowcase → BackedBy → DataSection
  → Plans     ← Limited release badge + Request access 弹窗（v3）
  → Network   ← 中心 GIF（v1）；左栏「Join the waitlist」弹窗（v3）
  → Latest    ← 原 FieldNotes，动态 blog 卡片（v3）
  → Events    ← 自动分桶（PR#8）；v1 替换末尾 3 条；v3 整表重写
  → FinalCta
```

---

## 3. 改动逻辑

### 3.1 Events 区块

**分桶逻辑（PR #8 建立，v1/v3 未改）：**

```text
EVENTS[]  →  isPast(endDate T23:59:59 < now)?
  否 → Upcoming，按 endDate 升序；CTA 用 ctaVerb
  是 → Past，按 endDate 降序；CTA 强制 View
每行 <li data-preview=...>  供 EventsPreview hover 跟随图使用
```

**v1 变更（`9e679a9`）：** 替换末尾 3 条（第 5–7 条），前 4 条（Decasonic / BASS SBC / IROS / Robots & Rollups）不动；同步 rename 3 张预览图为 kebab-case。

<span style="color:#2563eb">

**v3 变更（`bcc6ad7`）：整表重写**（不是增量）

| 条目 | v1 | v3 |
| --- | --- | --- |
| Upcoming | IROS 2026 · IEEE/RSJ · **View** | **IROS · Pittsburgh · `follow`→「Follow for details」** |
| Past 1 | BASS SBC 2026 | **BASS SBC · Stanford** |
| Past 2 | Decasonic Web3 Investor Day | ~~移除~~ |
| Past 3 | Robots & Rollups · NY Tech Week | **Robots & Rollups · New York** |
| Past 4 | Physical AI & Robotics Salon | 同 |
| Past 5 | RoboCon @ ETHDenver | **RoboCon SF**（Aug 5 2025，SF，`events-robocon-sf.jpg` ~10 MB） |
| Past 6 | RoboCon @ SmartCon | **RoboCon NYC**（Nov 4 2025，NY，`events-robocon-nyc.jpg`） |

逻辑增强：`ctaVerb` 扩展为 `"register" | "view" | "follow"`；日期列拆成月日 + 年份（`dateDay` / `dateYear`）两行显示。

**以 2026-09-02 为准的分桶期望：**

| 分组 | 条目（顺序） | CTA |
| --- | --- | --- |
| Upcoming | IROS（Sep 27 2026） | **Follow for details** |
| Past（新→旧） | BASS SBC → Robots & Rollups → Physical AI Salon → RoboCon NYC → RoboCon SF | 全部 **View** |

</span>

---

### 3.2 Network 区块

**v1 变更（`1aa58a5`）：** 中心从 `<NetworkOrbit>`（CSS SVG 轨道）替换为 `<picture>` GIF + 金色 tint：

```text
<picture class=coreMedia>
  <source media="(prefers-reduced-motion: reduce)" → 静态 JPG（33 KB）
  <img src=network-core-strands.gif>              → 默认播 GIF（~2 MB，lazy/async）
</picture>
<span class=coreTint>  金色 mix-blend-mode: color, opacity 0.4
$1M+ 叠在最上层（z-index: 1）
```

`NetworkOrbit.tsx` 仍留 repo，已加废弃注释，页面不再渲染。

<span style="color:#2563eb">

**v3 变更（`9f2a50e`）：** 左栏 Egocentric CTA 从外链改为弹窗：

- 旧：`<a href="https://app.prismax.ai/data">Start contributing</a>`
- 新：`<button onClick={() => openRequestAccess("egocentric_waitlist")}>Join the waitlist</button>`

右栏「Apply as an operator」仍指向 `https://app.prismax.ai/data`（未改）。

</span>

---

### <span style="color:#2563eb">3.3 Latest 区块（原 FieldNotes）</span>

<span style="color:#2563eb">

**v3 `55ef405`：** 组件/文件从 `FieldNotes` 重命名为 `Latest`，`id="field-notes"` → `id="latest"`，标题文案更新。

**v3 `ea12d35`：** Latest 改为 Server Component（async），动态拉取 blog 数据：

```text
Latest() [async Server Component]
  → fetchLatestCards()
      GET https://blog.prismax.ai/articles.js  (revalidate: 3600s)
      → parseArticlesJs()：切片 `window.PRISMAX_ARTICLES=[...]` 的 JSON
      → selectLatest(posts, 3)：按 date 降序取最新 3 篇
      → toCard()：href = blog.prismax.ai/article.html?slug=...
  失败/非 2xx/空 → FALLBACK_CARDS（2026-05-14 快照 3 篇）
```

卡片 UI：inline SVG mini-thumb → **真实 cover 图**（`<img loading="lazy">`）+ category 标签。  
「See all」链接从 `www.prismax.ai/blog` 改为 `blog.prismax.ai`。  
单测：`tests/latestPosts.test.mjs`（parse / select / fetch fallback）。

</span>

---

### <span style="color:#2563eb">3.4 Request Access 全流程（三仓库联动）</span>

<span style="color:#2563eb">

**Marketing 前端（`9f2a50e`）：**

```text
RequestAccessProvider（app/layout.tsx 全局包裹）
  ├─ Plans：Discover / Researcher → openRequestAccess("discover" | "researcher")
  │     CTA 文案改「Request access」；Plans 区加「Limited release」badge
  ├─ Network 左栏 → openRequestAccess("egocentric_waitlist")
  └─ RequestAccessModal
        POST {USER_API}/api/marketing/request-access
        必填：email、role
        可选：name、organization
        discover/researcher 额外：use_case、data_interest（waitlist 不显示）
        成功 →「You're on the list.」
```

`Button.tsx` 同步增强：`onClick` 现可拦截 http(s) 链接（`preventDefault` + 回调），Plans CTA 不再跳 console signup。Enterprise「Talk to sales」仍走 Contact Sales 弹窗（`mailto:` 不受影响）。

**Backend API（`05a6224`）：**

| 端点 | 关键规则 |
| --- | --- |
| `POST /api/marketing/request-access` | 公开；`request_type` ∈ `discover / researcher / egocentric_waitlist` |
| | email 必填（`email_validator` 校验）；role 必填 |
| | 同 email + 同 type 重复提交 → **429** + 友好 msg |
| | Rate limit：**4/min · 7/hour · 15/day**（按 IP） |
| | 写入 `marketing_interest_access_requests` 表 |
| `GET /api/admin/get-marketing-interest-access-requests` | JWT；分页；按 `created_at DESC` |

**附带 refactor（`81be54a`）：** Contact Sales 所有读写从 `contact_sales_submissions` 改为 `marketing_contact_sales_submissions`（需确认 DB 迁移已执行）。

**Admin 前端（`a80c6b4`）：** AdminPortal General 区新增「Marketing Interest Access Requests」表格，列含 Request Type / Email / Role / Name / Organization / Use Case / Data Interest / Created At，分页 10 条/页。

</span>

---

### <span style="color:#2563eb">3.5 全站链接与文案（`fc705ab` + `55ef405`）</span>

<span style="color:#2563eb">

| 位置 | 旧 | 新 |
| --- | --- | --- |
| Footer / Latest / Header Blog | `www.prismax.ai/blog` | `blog.prismax.ai` |
| Footer Product | Robotics Data（内链） | 标记 `external: true`（新开标签） |
| Footer Product | 含「PrismaX Toolkits」 | 已移除 |
| Footer Earn | 含「Become an owner-operator」 | 已移除；其余标签大小写统一 |
| LoginMenu / MobileNav | Robotics Data 不开新标签 | 同样新开标签 |
| `HomeRoot.module.css` | `--font-serif: Georgia` | 恢复 `var(--font-editorial-new), Georgia` |

</span>

---

### <span style="color:#2563eb">3.6 样式微调（`bc24d7c`）</span>

<span style="color:#2563eb">

- ContactSales / RequestAccess Modal：`--font-serif` 改为 Editorial New。
- Plans：`Limited release` badge 移到 eyebrow 上方（block 排列）。
- Brand Kit：typeface 卡片字重调整，usage list `<li>` 内容补 `<span>` 包裹。

</span>

---

## 4. 风险点

| 编号 | 风险描述 | 优先级 |
| --- | --- | --- |
| R-01 | Network 中心是金色 GIF，非 SVG 轨道；`$1M+` / chip 仍清晰可读 | 高 |
| R-02 | `prefers-reduced-motion: reduce` 时中心为静态 JPG，不播 GIF | 中 |
| R-03 | GIF ~2 MB：首屏以下 lazy load；弱网下 `$1M+` 不被遮挡 | 中 |
| R-04 | 移动端（≤940px）Network 三列变单列，中心 `order: -1` 排在文案上方 | 中 |
| <span style="color:#2563eb">R-05</span> | <span style="color:#2563eb">Events：IROS 在 Upcoming，CTA **Follow for details**；Decasonic 不再出现</span> | <span style="color:#2563eb">高</span> |
| <span style="color:#2563eb">R-06</span> | <span style="color:#2563eb">Events：Past 5 条顺序正确；RoboCon SF/NYC 替换 ETHDenver/SmartCon</span> | <span style="color:#2563eb">高</span> |
| <span style="color:#2563eb">R-07</span> | <span style="color:#2563eb">Events：日期列显示月日 + 年份两行</span> | <span style="color:#2563eb">中</span> |
| <span style="color:#2563eb">R-08</span> | <span style="color:#2563eb">IROS 过了 2026-10-01 23:59 后进 Past 顶部，CTA 变 View</span> | <span style="color:#2563eb">高</span> |
| <span style="color:#2563eb">R-09</span> | <span style="color:#2563eb">RoboCon SF 预览图 ~10 MB：弱网 hover 预览延迟明显</span> | <span style="color:#2563eb">中</span> |
| <span style="color:#2563eb">R-10</span> | <span style="color:#2563eb">Latest 展示 blog 最新 3 篇（或 fallback）；链接到 `blog.prismax.ai/article.html?slug=...`</span> | <span style="color:#2563eb">高</span> |
| <span style="color:#2563eb">R-11</span> | <span style="color:#2563eb">`#latest` anchor 有效；原 `#field-notes` 不再存在</span> | <span style="color:#2563eb">中</span> |
| <span style="color:#2563eb">R-12</span> | <span style="color:#2563eb">Plans Discover/Researcher 点「Request access」打开弹窗，**不跳** console signup</span> | <span style="color:#2563eb">高</span> |
| <span style="color:#2563eb">R-13</span> | <span style="color:#2563eb">Network 左栏「Join the waitlist」打开弹窗（egocentric_waitlist），不跳外链</span> | <span style="color:#2563eb">高</span> |
| <span style="color:#2563eb">R-14</span> | <span style="color:#2563eb">弹窗：email/role 必填校验；discover/researcher 有 use_case/data_interest；waitlist 无</span> | <span style="color:#2563eb">高</span> |
| <span style="color:#2563eb">R-15</span> | <span style="color:#2563eb">提交成功后 Admin 表格可见新记录（三种 request_type 各测一条）</span> | <span style="color:#2563eb">高</span> |
| <span style="color:#2563eb">R-16</span> | <span style="color:#2563eb">同 email + 同 type 重复提交 → 429 + 友好错误文案</span> | <span style="color:#2563eb">高</span> |
| <span style="color:#2563eb">R-17</span> | <span style="color:#2563eb">Contact Sales 仍正常写入 `marketing_contact_sales_submissions`（新表名）</span> | <span style="color:#2563eb">高</span> |
| <span style="color:#2563eb">R-18</span> | <span style="color:#2563eb">DB 表 `marketing_interest_access_requests` 已部署；未迁移则提交 API 500</span> | <span style="color:#2563eb">高</span> |
| <span style="color:#2563eb">R-19</span> | <span style="color:#2563eb">Blog 链接全站指向 `blog.prismax.ai`；Robotics Data 新开标签</span> | <span style="color:#2563eb">中</span> |

---

## 5. E2E 测试用例

### 环境准备

- **Marketing**：`main`（含 `f963626`）
- **Backend**：`testing`（含 `e616402`），且 DB 已有 `marketing_interest_access_requests` 表
- **Admin app**：`testing`（含 `96e0a40`），可用 Admin JWT
- 桌面 Chrome（细指针）+ 移动宽度（触控或 DevTools iPhone）
- DevTools Rendering 可切 `prefers-reduced-motion`

---

### 模块一：Network 区块

| TC | 测试目标 | 前置 | 操作 | 预期结果 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| TC-01 | GIF 替换 SVG 轨道 | 桌面、未开 reduced-motion | 滚到 `#network` | 中心是金色丝线动图；无旋转 SVG 圆圈；`$1M+` 清晰叠在上层 | 高 |
| TC-02 | reduced-motion 用静态图 | DevTools 开启 prefers-reduced-motion | 刷新看 Network 中心 | 静态 JPG，不循环播放；文案仍在 | 中 |
| TC-03 | 移动端单列布局 | 视口 ≤ 940px | 看 Network 区块 | 中心 `$1M+` 排在两段文案上方 | 中 |
| <span style="color:#2563eb">TC-04</span> | <span style="color:#2563eb">左栏 Join the waitlist 开弹窗</span> | <span style="color:#2563eb">桌面</span> | <span style="color:#2563eb">点「Join the waitlist」</span> | <span style="color:#2563eb">打开 Request Access 弹窗（egocentric_waitlist），不跳外链</span> | <span style="color:#2563eb">高</span> |
| <span style="color:#2563eb">TC-05</span> | <span style="color:#2563eb">右栏 Apply as an operator 仍为外链</span> | <span style="color:#2563eb">同上</span> | <span style="color:#2563eb">点「Apply as an operator」</span> | <span style="color:#2563eb">新开标签到 `https://app.prismax.ai/data`</span> | <span style="color:#2563eb">中</span> |

---

### <span style="color:#2563eb">模块二：Events v3</span>

<span style="color:#2563eb">

| TC | 测试目标 | 前置 | 操作 | 预期结果 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| TC-06 | v3 内容与分桶 | 日期 2026-09-02 | 滚到 `#events` | Upcoming 仅 IROS + Follow for details；Past 5 条：BASS SBC→Robots&Rollups→Salon→RoboCon NYC→RoboCon SF；无 Decasonic / ETHDenver / SmartCon | 高 |
| TC-07 | 日期年份分列 | 桌面 | 看日期列 | 月日、年份上下两行 | 中 |
| TC-08 | 新预览图 | 桌面、细指针 | hover RoboCon NYC / SF | 对应 jpg 预览；非旧 robocon-ethdenver/smartcon 图 | 高 |
| TC-09 | 触控无预览 | 手机或 coarse pointer | 点/滑活动行 | 无浮动预览；点 CTA 仍跳外链 | 中 |
| TC-10 | IROS 分桶时间切换 | 可修改系统时间至 2026-10-02 | 查看 Events | IROS 进 Past 顶部；CTA 变 View | 高 |

</span>

---

### <span style="color:#2563eb">模块三：Latest 动态 Blog</span>

<span style="color:#2563eb">

| TC | 测试目标 | 前置 | 操作 | 预期结果 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| TC-11 | 动态 3 张卡片 | 可访问 blog.prismax.ai | 滚到 `#latest` | 3 张带 cover 图的卡片；内容与 blog 最新文一致（或 fallback 3 篇） | 高 |
| TC-12 | 卡片外链 | 同上 | 点任一卡片 | 新标签打开 `blog.prismax.ai/article.html?slug=...` | 高 |
| TC-13 | See all | 同上 | 点「See all →」 | 打开 `https://blog.prismax.ai` | 中 |
| TC-14 | Fallback | 阻断 articles.js 请求 | 刷新首页 | 显示 3 张 fallback 卡片，页面不报错 | 中 |
| TC-15 | `#latest` anchor | — | 访问 `/#latest` | 正常滚至该区块；`#field-notes` 无效 | 中 |

</span>

---

### <span style="color:#2563eb">模块四：Request Access（E2E 跨三仓库）</span>

<span style="color:#2563eb">

| TC | 测试目标 | 前置 | 操作 | 预期结果 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| TC-16 | Discover 弹窗 | Marketing 已部署 | Plans → Discover「Request access」 | 弹窗副标题含 Discover plan；有 use_case、data_interest 字段 | 高 |
| TC-17 | Researcher 弹窗 | 同上 | Plans → Researcher「Request access」 | 副标题含 Researcher plan | 高 |
| TC-18 | Egocentric waitlist 弹窗 | 同上 | Network 左栏「Join the waitlist」 | 弹窗无 plan 副标题；**无** use_case/data_interest 字段 | 高 |
| TC-19 | 必填校验 | 弹窗打开 | 不填 email/role 直接提交 | 字段高亮 +「Please add a valid email and your role.」 | 高 |
| TC-20 | 成功提交 + Admin 回写 | 新 email + Admin 已登录 | 填必填项提交 → 查 Admin 表 |「You're on the list.」；Admin 表出现新行，字段与提交一致；分页正常 | 高 |
| TC-21 | 重复提交 | 同 email 同 type 已提交 | 再次提交 discover | 错误文案含 already submitted；HTTP 429 | 高 |
| TC-22 | Enterprise 不受影响 | 同上 | Plans → Enterprise「Talk to sales」 | 仍开 Contact Sales 弹窗 | 中 |
| TC-23 | Contact Sales 回归 | — | 通过 Contact Sales 提交 | Admin 端 Contact Sales 表（新名 `marketing_contact_sales_submissions`）有新数据 | 高 |

</span>

---

### <span style="color:#2563eb">模块五：链接与文案回归</span>

<span style="color:#2563eb">

| TC | 测试目标 | 操作 | 预期结果 | 优先级 |
| --- | --- | --- | --- | --- |
| TC-24 | Blog 链接 | Footer / Latest「See all」 | 新开 `blog.prismax.ai` | 中 |
| TC-25 | Robotics Data 新开标签 | Header Login → Robotics Data | 新开标签 | 中 |
| TC-26 | Limited release 文案 | 看 Plans 顶区 | 显示「Limited release」badge + 正文含 limited release | 中 |
| TC-27 | Plans CTA 不再跳 console | Plans → Discover/Researcher | 打开弹窗而非跳转 `console.prismax.ai/signup` | 高 |

</span>

---

## 6. 不在本次范围

- Events 自动分桶引擎、hover 预览 portal/tilt 算法 — PR #8 内容，v1/v3 未改逻辑。
- `NetworkOrbit.tsx` 文件仍在 repo 属预期，确认页面不渲染 `.orbit` / `.spin` 即可。
- <span style="color:#2563eb">`34407a5`（robotic-data 页）随 PR #12 合入，不在 Aparna commit 范围，需单独回归。</span>
- <span style="color:#2563eb">Rate limit 压测（TC 可选，4+/min 触发限流验证）。</span>

---

## 附：名词解释

**分桶（Bucketing）**：把一个平铺列表里的条目，按某个条件自动归类到不同的"桶"（分组）里。

具体到 Events 区块：所有活动维护在同一份 `EVENTS[]` 数组中，渲染时用当天时间与每条活动的 `endDate` 比较，自动分进两组：

```
所有 Events（一份平铺数组）
         ↓  按 endDate 判断
  ┌────────────┐    ┌────────────┐
  │  Upcoming  │    │    Past    │
  │（还没结束）│    │（已经结束）│
  └────────────┘    └────────────┘
```

不需要人工维护两个独立列表，日期到了自动换组。平时也可以理解为"自动分组"或"自动归类"。
