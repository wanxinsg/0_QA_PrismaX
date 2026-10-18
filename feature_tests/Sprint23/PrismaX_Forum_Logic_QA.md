# PrismaX Forum 逻辑分析与测试用例

> 分析日期：2026-08-12  
> **复审日期：2026-08-12**（已 `git pull` 最新 `testing`）  
> 前端：`prismax-marketing-rp` `testing` @ `cf910e8`（Forum 相关：`47ddc53` / `e2eb98e` / `7bf2e1d`）  
> 后端：`app-prismax-rp-backend` `testing` @ `e9ced43`（Forum 最新 `5a65706`）  
> 说明：Forum UI **不在** `app-prismax-rp`；在 Marketing `/forum/*`  
> 关联：`Sprint22_FE_0122539_BE_470ab3d_Commit_Range_QA.md` §3.5；`QA_PrismaX/PM_PRD/prismax-forum/`

---

## 1. 总体结论

PrismaX Forum 是独立论坛微服务 + Marketing 站内嵌页面：

| 层 | 仓库 / 路径 | 职责 |
| --- | --- | --- |
| FE | `prismax-marketing-rp` → `/forum` | 列表、详情、发帖、草稿、收藏、作者删帖、登录门控 |
| BE | `app-prismax-rp-backend/app_prismax_forum` | Threads / Comments / Categories / Media |
| Auth | PrismaX User Service + `users.hash_code` | Forum **不自管登录**；只认 `Authorization: Bearer <hash_code>` |
| DB | 与主站共用 `users`；Forum 表 `forum_*` | Cloud SQL Postgres（生产）；本地可 SQLite |

`app-prismax-rp` **无 Forum 功能代码**。测 Forum 必须用 Marketing 前端（或直调 Forum API）。

**发布前重点（`testing` 复审后）：**

1. Gateway Bearer 与 User Service 登录态打通（demo auth 已删除）。
2. 草稿仅作者可见；他人访问返回 404（不是 403）。
3. 图片走 GCS `/api/media/images`，非 base64 内嵌。
4. **BUG-01 在 `testing`/beta 已关闭**：Edit → `forumDraftPath` → `/forum/compose?id=`（有单测）。合 `main`/prod 时防回退。
5. 作者可在帖子详情 **Delete**（`47ddc53`）；API 错误会透出 `detail`（`e2eb98e`）。
6. Beta 营销站有 **BetaAccessGate**（`cf910e8`）：浏览器冒烟前需能过门禁。

---

## 2. 架构与数据流

```text
Browser (prismax-marketing-rp)
  ├─ LoginModal → User API (/auth/save, /verify_token, OAuth)
  │                 └─ localStorage.gatewayToken = users.hash_code
  ├─ /forum/* UI
  └─ fetch /api/*  (+ Authorization: Bearer <gatewayToken>)
        │
        ▼ Next.js rewrite (next.config.ts)
  BACKEND_ORIGIN
    beta:  app-prismax-forum-beta-*.run.app
    prod:  forum.prismaxserver.com
        │
        ▼ FastAPI app_prismax_forum
  optional_user / current_user
    → SELECT users WHERE hash_code = token
  forum_threads / forum_comments / forum_likes / forum_saves
```

### 2.1 页面与路由

| 路径 | 需登录 | 行为 |
| --- | --- | --- |
| `/forum` | 否（浏览）；Like/Save/发帖要登录 | 分类 Tab、Latest/Most Discussed、搜索 `?q=`、分页 Load More（12/页） |
| `/forum/thread/[id]` | 否（读）；评论/赞/收藏要登录 | 正文 Block 渲染、一层回复、Share 复制链接 |
| `/forum/compose` | 是 | Block 编辑器；Save Draft / Publish；`?id=` 编辑已有稿 |
| `/forum/drafts` | 是 | 我的草稿：Edit / Publish / Delete |
| `/forum/saved` | 是 | 已收藏已发布帖；取消收藏后从列表移除 |

Header：搜索、New Post、Account（My Drafts / Saved）、Sign In。

### 2.2 API 一览

| Method | Path | Auth | 说明 |
| --- | --- | --- | --- |
| GET | `/api/health` | 否 | DB 连通性；`authorization: prismax_gateway_token` |
| GET | `/api/categories` | 否 | 仅 `published`；首项 `All` + 各分类 count |
| GET | `/api/threads` | 可选 | `category` / `sort=latest\|discussed` / `q` / `limit` / `offset`；仅 published |
| GET | `/api/threads/{id}` | 可选 | draft 仅作者；他人/未登录 → **404** |
| POST | `/api/threads` | 必 | `status=draft\|published`；bleach 清洗 |
| PATCH | `/api/threads/{id}` | 必 | 仅作者；可改 status / content |
| POST | `/api/threads/{id}/publish` | 必 | 仅作者；置 published + `published_at` |
| DELETE | `/api/threads/{id}` | 必 | 仅作者 |
| POST | `/api/threads/{id}/like` | 必 | Toggle；count = 真赞 + `seed_likes` |
| POST | `/api/threads/{id}/save` | 必 | Toggle；`count` 恒为 0 |
| GET | `/api/me/drafts` | 必 | 当前用户 draft，按 `updated_at` desc |
| GET | `/api/me/saved` | 必 | 已收藏且仍为 published |
| GET | `/api/threads/{id}/comments` | 可选 | 树：顶层最新在前；回复挂在顶层下 |
| POST | `/api/threads/{id}/comments` | 必 | `parent_id` 可选；回复的回复折回顶层 parent |
| POST | `/api/comments/{id}/like` | 必 | Toggle |
| POST | `/api/media/images` | 必 | jpeg/png/webp/gif；默认 ≤10MB；需配置 GCS |

### 2.3 鉴权规则

- **读公开内容**：可无 Token。
- **写操作**：`current_user`；无/无效 Bearer → **401** `Authentication required.`
- Token = `users.hash_code`（明文比对，非 JWT 验签）。
- 前端 401 触发 `prismax:session-expired` → 清 session + 打开 LoginModal。
- 已删除 demo `/api/auth`、cookie session adapter（BE `b49ade4`）。

### 2.4 内容与互动规则

- **正文**：JSON blocks：`p` / `h2` / `quote` / `bullet` / `code` / `divider` / `image`。
- **清洗**：`bleach` — text 去全部标签；html 仅允许 `a,b,br,code,em,i,strong,u`。
- **Excerpt**：显式 excerpt，否则取首段 text，默认文案 `"A new monograph awaiting peer review."`；最长 200。
- **分类（FE 固定）**：Discourse / Case Study / Editorial / Protocol；默认 Discourse。
- **评论嵌套**：最多一层；对回复再回复时 BE 把 `parent_id` 改成顶层评论 id。
- **计数**：`like_count` / `comment_count` = 真实行数 + `seed_*`（导入基线）。
- **删除帖**：级联删 comments / saves（schema FK）；likes 按 target 存，帖删后可能残留孤儿 like（注意回归）。

### 2.5 Media

- 需 `FORUM_GCS_BUCKET`；未配置 → **503**.
- 对象路径：`{prefix}/{user_id}/{YYYY}/{MM}/{uuid}{ext}`。
- 返回公开 URL（`FORUM_GCS_PUBLIC_BASE_URL` 或 GCS 默认 URL）。

---

## 3. 核心业务流（测前对照）

### 3.1 浏览

1. 打开 `/forum` → `GET /api/categories` + `GET /api/threads?limit=12`.
2. 切分类 / Latest|Most Discussed / Header 搜索 `q` → 重新拉列表。
3. Load More → `offset = 已加载数`；`threads.length >= total` 时提示已全部加载。
4. 点卡片 → `/forum/thread/{id}` → thread + comments。

### 3.2 登录门控

未登录点 New Post / Like / Save / Post Reply → `requireAuth()` 打开 LoginModal；登录成功后 `gatewayToken` 写入 localStorage，后续 `/api` 自动带 Bearer。

### 3.3 发帖 / 草稿

1. `/forum/compose`：标题必填才可 Publish；Draft 可无标题吗？——BE `title` min_length=1 且 clean 后空则 400；FE Publish 要求 `title.trim()`，Save Draft 也走同一 payload，空标题会失败。
2. Cover / Image block → `POST /api/media/images` → 存 URL。
3. Publish → `POST /api/threads` `status=published` → 回 `/forum`。
4. Draft → `status=draft` → 回 `/forum/drafts`。
5. Drafts 页 Publish → `PATCH ... { status: "published" }`（未用 `/publish` 专用接口，行为应等价）。

### 3.4 评论

- 顶层评论 prepend 到列表。
- Reply 只在顶层评论上；嵌套回复 UI 无 Like/Reply 按钮。
- 会话内 `added` 本地加到 contributions 展示，刷新后以服务端 `comment_count`（含 seed）为准。

---

## 4. 测试用例

### 4.1 P0 — 鉴权与身份（Auth）

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| AUTH-01 | P0 | 有效 Gateway Token 发帖 | Marketing 邮箱/OAuth 登录后 Publish | 201；作者为当前用户（name 来自 email 前缀） |
| AUTH-02 | P0 | 无 Token 写接口 | 直调 `POST /api/threads` 无 Authorization | **401** Authentication required. |
| AUTH-03 | P0 | 错误 / 过期 Token | Bearer 伪造或已 logout 的 hash | **401**；UI 弹出登录 |
| AUTH-04 | P0 | Demo / Cookie 旧链路 | 访问旧 `/api/auth/login` 或仅依赖 forum cookie | 不可用 / 404 |
| AUTH-05 | P0 | 跨环境 Token | beta 登录 token 打 prod Forum（或反向） | 失败（users 库不一致） |
| AUTH-06 | P0 | 登出后再写 | Logout → Like / 发帖 | 要求重新登录；不串号 |
| AUTH-07 | P0 | 双 Tab 登出 | A Tab 登出，B Tab 发帖 | 401 或 session-expired 处理合理 |

### 4.2 P0 — 浏览列表与筛选（Browse）

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| BRW-01 | P0 | 首页默认 | 打开 `/forum` | 仅 published；Latest；显示 total；骨架屏后出卡片 |
| BRW-02 | P0 | 分类过滤 | 点非 All 分类 | 列表与 count 一致；仅该 category |
| BRW-03 | P0 | All 汇总 | 对比 All.count 与各分类之和 | 相等 |
| BRW-04 | P0 | Most Discussed | 切 sort | 评论多的在前；同评论数时较新在前 |
| BRW-05 | P0 | 搜索 title/excerpt | Header 输入命中词 | `q` 写入 URL；结果正确；空结果有 Empty UI |
| BRW-06 | P1 | 搜索大小写 | 大小写混合 | ilike，不区分大小写 |
| BRW-07 | P0 | Load More | 造 >12 帖后分页 | 追加不丢页；到底提示 caught up |
| BRW-08 | P1 | 草稿不进列表 | 发 draft 后回首页 | 列表不可见该帖 |
| BRW-09 | P1 | Health | `GET /api/health` | status ok；database.ok true（环境 DB 正常时） |

### 4.3 P0 — 帖子读写与权限（Thread）

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| THR-01 | P0 | 读 published | 打开详情 | 标题/作者/日期/blocks/赞藏状态正确 |
| THR-02 | P0 | 读他人 draft | 未登录或另一用户 `GET /threads/{draftId}` | **404** Thread not found. |
| THR-03 | P0 | 作者读自己 draft | 作者带 Token 打开 | 200，可编辑 |
| THR-04 | P0 | 创建 published | 填标题+正文 Publish | 进首页；`published_at` 有值 |
| THR-05 | P0 | 创建 draft | Save Draft | 仅 drafts 可见；首页无 |
| THR-06 | P0 | 空标题 | title 空白 Publish / API | FE 拦住；API **400** Title is required. |
| THR-07 | P0 | 改他人帖 | 用户 B PATCH 用户 A 的帖 | **403** Not your thread. |
| THR-08 | P0 | 删他人帖 | 用户 B DELETE | **403** |
| THR-09 | P0 | 作者删帖 | 详情页 Delete（作者可见）确认后删除；或 Drafts Delete | 回列表；详情 404；评论不可见 |
| THR-09b | P0 | 非作者无删帖入口 | 他人打开已发布帖 | 无 Delete 按钮；直调 DELETE → **403** |
| THR-10 | P0 | Draft → Publish | Drafts 点 Publish 或 compose 发布 | 进首页；drafts 移除；`published_at` 更新 |
| THR-11 | P1 | 再 Publish 已发布 | `POST .../publish` 重复 | 幂等成功，不异常 |
| THR-12 | P1 | Excerpt 自动生成 | 无 excerpt 发帖 | excerpt 来自首段 text，≤200 |
| THR-13 | P1 | 分类默认 | 不选分类 | Discourse |
| THR-14 | P1 | 不存在 id | `/forum/thread/999999` | Thread not found UI |

### 4.4 P0 — 评论（Comment）

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| CMT-01 | P0 | 顶层评论 | 登录后 Post Reply | 201；列表顶部出现；author 正确 |
| CMT-02 | P0 | 未登录评论 | 点 Post Reply | 打开登录；不发请求或失败后引导登录 |
| CMT-03 | P0 | 空正文 | body 空白 / 仅空白 | FE 不发；API **400** |
| CMT-04 | P0 | 一层回复 | Reply 某顶层评论 | 嵌套在该评论下；`parent_id` = 顶层 id |
| CMT-05 | P0 | 回复的回复（API） | `parent_id` 指向已是 reply 的评论 | BE 折回顶层 parent；仍一层嵌套 |
| CMT-06 | P1 | 非法 parent | parent 属其他 thread | **400** Invalid parent comment. |
| CMT-07 | P1 | 帖不存在 | 对不存在 thread 评论 | **404** |
| CMT-08 | P1 | contributions 计数 | 发评论后刷新 | comment_count（+seed）与列表一致 |

### 4.5 P0 — 点赞 / 收藏（Engage）

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| ENG-01 | P0 | 帖子点赞 Toggle | 连点两次 Like | 先 active+count+1，再取消；刷新保持 |
| ENG-02 | P0 | 评论点赞 | 顶层评论 Like | Toggle；count 含 seed_likes |
| ENG-03 | P0 | 收藏 | Save → `/forum/saved` | 列表出现；再 Save 移除 |
| ENG-04 | P0 | 未登录赞/藏 | 未登录点图标 | 登录弹窗 |
| ENG-05 | P1 | 重复赞唯一约束 | 并发双请求 like | 最终一态；无 500 |
| ENG-06 | P1 | 收藏仅 published | 收藏 draft（若直调 API） | 可写 Save 行，但 `/me/saved` 只回 published |
| ENG-07 | P1 | Share | 点 Share | 复制当前 URL；toast 成功 |

### 4.6 P0 — 图片上传（Media）

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| MED-01 | P0 | 合法图片 | 上传 jpg/png/webp/gif cover | 返回 url；封面展示；发布后详情可见 |
| MED-02 | P0 | 正文 Image block | + Image | 插入 block，src 为 GCS URL |
| MED-03 | P0 | 未登录上传 | 无 Token POST media | **401** |
| MED-04 | P1 | 超大图 | > `FORUM_MAX_IMAGE_BYTES`（默认 10MB） | **413** |
| MED-05 | P1 | 非法类型 | pdf / svg / txt | **400** Unsupported image type. |
| MED-06 | P1 | 空文件 | 0 byte | **400** Image is empty. |
| MED-07 | P1 | Bucket 未配 | 本地未配 GCS | **503**；UI 提示上传失败 |

### 4.7 P1 — 编辑器 / XSS / SEO

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| EDT-01 | P1 | 多 Block 类型 | 依次加 h2/quote/bullet/code/divider/image | 发布后渲染正确 |
| EDT-02 | P1 | 拖拽排序 | 拖 block 重排后发布 | 顺序保持 |
| EDT-03 | P0 | XSS html | 正文塞入 `<script>` / `onerror=` | 入库被 bleach 剥掉；详情不执行脚本 |
| EDT-04 | P1 | 链接白名单 | `<a href="javascript:...">` | 被清洗；http(s)/mailto 可保留 |
| EDT-05 | P1 | SEO / robots | `/forum/compose|drafts|saved` | robots disallow；thread 有 canonical/OG |
| EDT-06 | P1 | Sitemap | 已发布帖 | sitemap 含 `/forum/thread/{id}`；草稿不含 |

### 4.8 P1 — 前端已知问题 / 回归缺陷

| ID | 优先级 | 场景 | 步骤 | 预期 / 现状 |
| --- | --- | --- | --- | --- |
| BUG-01 | 已关闭（testing/beta） | Drafts → Edit | `/forum/drafts` 点 Edit | 跳转 `/forum/compose?id=`。修复：`7bf2e1d` + `lib/forumRules.mjs` `forumDraftPath`；单测 `tests/forumRules.test.mjs`。合 main/prod 防回退。 |
| BUG-02 | P2 | 嵌套回复 Like | UI 无二级 Like | 与 BE 能力不一致；确认是否产品故意 |
| BUG-03 | N/A | `.env.example` AUTH_PROVIDER | testing 树中已无该过时示例 | 原 demo auth 文档漂移项作废 |
| BUG-04 | P2 | 列表 N+1 | 大量帖子列表 | 每帖多次 count 查询；关注 beta 延迟 |
| BUG-05 | P2 | cover/`src` 未 bleach | 直调 API 塞恶意 cover URL；卡片 `url('${cover}')` | 文本已洗，图片 URL 未校验；关注 CSS/内容注入 |
| BUG-06 | P2 | Sitemap 上限 | 发 >100 帖 | sitemap `limit=100`，多出的已发布帖可能不进 sitemap |

### 4.9 P1 — 环境 / CORS / 代理

| ID | 优先级 | 场景 | 步骤 | 预期 |
| --- | --- | --- | --- | --- |
| ENV-01 | P0 | Beta rewrite | beta-www / `testing` 部署 | `/api` → `app-prismax-forum-beta-1053158761087.us-west1.run.app`（`lib/forumBackend.mjs`） |
| ENV-02 | P0 | Prod rewrite | 生产 Marketing | `/api` → `app-prismax-forum-1053158761087.us-west1.run.app`（**非**旧文档里的 `forum.prismaxserver.com`，除非 `BACKEND_ORIGIN` 覆盖） |
| ENV-03 | P1 | CORS 直连 API | 浏览器跨域直打 Forum origin | 仅允许配置 origins |
| ENV-04 | P1 | User API 环境 | localhost / beta / prod hostname | `getUserApiBase()` 指向对应 user 服务 |
| ENV-05 | P0 | Beta 门禁 | 打开 beta-www `/forum` | 需过 `BetaAccessGate` 后再测 Forum |

---

## 5. 建议回归矩阵（最小集）

```text
[Auth]  登录 → Bearer 发帖成功；无 Token 401；demo 登录不可用
[Browse] 分类 / Latest / Discussed / 搜索 / Load More
[Draft]  存草稿 → 他人 404 → 自己可见 → Publish 上首页
[Thread] 作者可改删；他人 403
[Comment] 顶层 + 一层回复；空正文拒绝
[Engage] Like / Save Toggle + Saved 页
[Media]  jpg 上传成功；非法类型 / 超大失败
[XSS]    script 标签入库被洗
[BUG]    Drafts Edit → /forum/compose?id=（beta 已通过；回归防回退）
```

---

## 6. API 快速冒烟（curl）

将 `$TOKEN` 换成登录后 `localStorage.gatewayToken`，`$HOST` 换成 Forum 后端或同源 `/api`：

```bash
# Health
curl -s "$HOST/api/health"

# 公开列表
curl -s "$HOST/api/threads?limit=5&sort=latest"

# 需登录发帖
curl -s -X POST "$HOST/api/threads" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"QA smoke","category":"Discourse","content":[{"type":"p","html":"hi","text":"hi"}],"status":"published"}'

# 无 Token 应 401
curl -s -o /dev/null -w "%{http_code}\n" -X POST "$HOST/api/threads" \
  -H "Content-Type: application/json" \
  -d '{"title":"x","content":[],"status":"draft"}'
```

后端单测：

```bash
cd app-prismax-rp-backend
python -m unittest app_prismax_forum.test_auth
python -m unittest app_prismax_forum.test_migrations
```

---

## 7. 风险与待确认

1. **FE 不在 `app-prismax-rp`**：排期/用例勿只回归主 App。
2. **Token 明文 hash_code**：与主站一致；Forum 无二次 JWT 校验，依赖 User 库行存在且 hash 有效。
3. **seed_likes / seed_comments**：导入数据会使 UI 计数 > 真实互动行数，验收勿强行相等。
4. **删除帖后 likes**：`forum_likes` 无 FK cascade 到 thread，可能留孤儿；一般不影响 UI。
5. **BUG-01 Draft Edit 路径**：beta/`testing` 已修复；若本地仍见旧路径，先对齐 `testing` 再测。
6. **Media 依赖 GCS + 公钥读**：beta/prod bucket 策略、CDN base URL 需运维确认。

---

## 8. 建议测试顺序

1. Health + Auth（AUTH-01~04）  
2. Browse 冒烟（BRW-01~05, 07）  
3. 发帖 / 草稿 / 权限（THR-01~10）+ BUG-01 回归（Edit 仍进 `/forum/compose`）  
4. 评论与互动（CMT / ENG）  
5. Media + XSS  
6. Beta/Prod 环境 rewrite 与登录联调  

完成以上后再做移动端 Header / 搜索 / Account 菜单走查。

---

## 补充说明：Design 草稿 vs 代码实现差异

> 对照：`QA_PrismaX/PM_PRD/prismax-forum/`（design / 原型草稿）  
> 实现：BE `app-prismax-rp-backend/app_prismax_forum` + FE `prismax-marketing-rp` `/forum/*`  
> 用途：用例与验收以**当前实现**为准；design 仅作产品意图参考，下列差异勿按草稿反向卡实现。

### 1. 结构性差异（产品形态变了）

| # | 主题 | Design 草稿 | 当前实现 | 影响 |
| --- | --- | --- | --- | --- |
| D1 | 应用形态 | 独立 Next 应用，路由在根：`/`、`/compose`、`/thread/[id]`、`/drafts`、`/saved` | 嵌在 Marketing 站，统一加前缀：`/forum`、`/forum/compose`、… | 所有内链、SEO、sitemap 需 `/forum` |
| D2 | 部署 | 本机 systemd；API **仅 loopback**；FE `:3001` 公网 | Forum API 独立 Cloud Run（beta/prod URL）；Marketing FE rewrite `/api` | CORS、公网 API、环境分流 |
| D3 | 用户表 | Forum 自建 `users`（`external_id` / `name` / `avatar_color`），adapter upsert | **复用主站** `users`（`userid` / `hash_code` / `email`…）；展示名由 email 推导 | 无独立 forum 用户；无 demo persona |
| D4 | 业务表名 | `threads` / `comments` / `likes` / `saves` | `forum_threads` / `forum_comments` / `forum_likes` / `forum_saves` | 同库隔离命名 |
| D5 | 数据库 | 默认 SQLite + `create_all` | 生产 Cloud SQL Postgres + SQL schema + FK migration；本地仍可 SQLite | 运维与迁移不同 |

### 2. 认证（最大差异）

| # | Design 草稿 | 当前实现 |
| --- | --- | --- |
| A1 | `AUTH_PROVIDER` + AuthAdapter（`demo` / `prismax`） | **已删除** adapter / demo；只解析 Bearer |
| A2 | Cookie session（`credentials: "include"`） | `localStorage.gatewayToken` + `Authorization: Bearer` |
| A3 | API：`/api/auth/me`、`/provider`、`/logout`、`/demo/*` | **无** Forum auth 路由 |
| A4 | 登录：Demo 预设身份 / 任意名字 | 真实 PrismaX 登录：邮箱验证码 / Google / Apple + reCAPTCHA |
| A5 | 会话：启动调 `/api/auth/me` | 读 localStorage；401 发 `prismax:session-expired` |
| A6 | Design 规划的 PrismaX 路径是 **验 JWT claim** | 实现是 **hash_code 查表**（与主站 gateway 一致，非 JWT 验签） |
| A7 | Health 返回 `auth_provider` | Health 返回 `authorization: prismax_gateway_token` + DB 状态 |

### 3. Design 列为 follow-up、实现已落地

| # | Design 原文风险 / 后续 | 当前实现 |
| --- | --- | --- |
| F1 | HTML 需 bleach sanitization | 已有 `sanitize.py`（bleach）写入时清洗 |
| F2 | 图片用 base64 data URL，建议对象存储 | 已有 `POST /api/media/images` → GCS，存 URL |
| F3 | 列表/文章纯 CSR，SEO 后续做 | Thread 页已 SSR metadata / OG / JSON-LD；sitemap、robots 已配 |
| F4 | 无迁移系统 | 有 `sql/20260630_forum_schema.sql` + `migrations.py`（userid FK） |

### 4. API / 业务行为差异

| # | 项 | Design | 实现 |
| --- | --- | --- | --- |
| B1 | Media API | 无 | 新增 `/api/media/images` |
| B2 | Auth API | 有完整 `/api/auth/*` | 已移除 |
| B3 | 空标题 | `title.strip()` 写入，未显式 400 | `clean_text` 后空 → **400** |
| B4 | content 写入 | 原样 `model_dump()` | 经 `clean_blocks` |
| B5 | 帖/评/赞/藏/分类核心接口 | 有 | **路径与语义基本一致**（业务主路径对齐） |
| B6 | 评论一层嵌套 / seed 计数 | 有 | 同设计 |

### 5. 前端 UX / 组件差异

| # | 项 | Design | 实现 |
| --- | --- | --- | --- |
| U1 | Header | 独立 `Header.tsx` | `ForumHeader`；账户用共享 `EmailAccountMenu` |
| U2 | Footer | Forum 专用 “Digital Monograph · © 2026”，Privacy/Terms/Contact 为 `#` | 共享 `SiteFooter`（Marketing 链接含 Forum） |
| U3 | Toast | 单字符串 `Toast` | `Notification`（success/error/info） |
| U4 | 登录弹窗 | Demo Sign In | 正式 LoginModal（与站点共用） |
| U5 | 作者展示 | `User.name` / `initials` / `avatar_color` 入库 | name/initials/avatar_color **运行时由 email/userid 计算** |
| U6 | Drafts → Edit | `/compose?id=`（相对根路径，正确） | **`testing` 已修**：`forumDraftPath` → `/forum/compose?id=`（`7bf2e1d` + 单测） |
| U7 | 移动端账户 | 抽屉里主要 Sign In/Out + 发帖；Drafts/Saved 仅桌面用户菜单 | 移动端 Account 菜单也带 My Drafts / Saved |
| U8 | 搜索占位文案 | “Search threads, authors, topics…” | 相同文案；**两边 API 都不搜 author**（仅 title/excerpt） |
| U9 | 删帖 UI | 仅 Drafts 有 Delete | 详情页作者可见 Delete + 确认（`47ddc53`） |
| U10 | 错误提示 | 多为泛化 toast | 部分流程透出 API `detail`（`e2eb98e`） |

### 6. 对齐、可视为未变的部分

- 浏览：分类 Tab、Latest / Most Discussed、`q` 搜索、分页 12、Load More  
- 详情：BlockRenderer、Like / Save / Share、一层评论与回复  
- 编辑器：categories（Discourse / Case Study / Editorial / Protocol）、block 类型集合、草稿/发布流  
- 权限：draft 仅作者可见（404）、改删仅作者（403）

### 7. 差异结论（给测试 / 产品）

1. **不要按 design README 测 demo 登录 / `/api/auth/*` / cookie session** —— 已废弃。  
2. **按 Marketing `/forum` + Gateway Bearer + 真登录测**。  
3. Design 里标成后续的 **bleach / GCS / SEO**，实现侧大多已做，应按实现验收。  
4. BUG-01 在 `testing`/beta 已关闭；合 main/prod 防回退。  
5. 作者身份与头像逻辑从「可配置 persona」变成「email 派生」，验收展示勿拿 demo 种子用户名对比。

---

## 补充说明：`testing` 分支复审结论（2026-08-12）

> FE `prismax-marketing-rp` @ `cf910e8` · BE `app-prismax-rp-backend` @ `e9ced43`（forum `5a65706`）  
> 已对两仓执行 `git fetch` + `git pull --ff-only origin testing`。

### 已确认（可按通过项回归）

| 项 | 结论 | 证据 |
| --- | --- | --- |
| BUG-01 Draft Edit | **已修** | `forumDraftPath`；Drafts Edit 用该 helper；`tests/forumRules.test.mjs` 断言 `/forum/compose?id=42`；beta 实测一致 |
| Auth | Bearer `hash_code` only | 无 `/api/auth`；`deps.optional_user` 查 `users.hash_code` |
| Media | GCS 上传 | `POST /api/media/images`；未配 bucket → 503 |
| HTML 清洗 | bleach 写入时清洗 | `sanitize.clean_blocks` |
| SEO | robots / sitemap / thread metadata | compose/drafts/saved disallow；sitemap 拉 published |
| 作者删帖 UI | 新增 | Thread 详情 Delete + confirm（`47ddc53`） |
| API 错误展示 | 改善 | `ApiError` 透出 `detail`（`e2eb98e`） |
| Forum origin 解析 | 统一 helper | `lib/forumBackend.mjs`：dev `8085`；beta/testing → beta Cloud Run；else → prod Cloud Run |

### 仍建议关注

| ID | 级别 | 说明 |
| --- | --- | --- |
| BUG-05 | P2 | `cover_image` / block `src` **未** bleach；卡片 CSS `url('${cover}')` 有注入面 |
| BUG-02 | P2 | 嵌套回复无 Like UI |
| BUG-04 | P2 | 列表序列化 N+1 |
| BUG-06 | P2 | sitemap `limit=100` |
| ENV-05 | P0 环境 | `BetaAccessGate` 可能挡住未授权浏览器冒烟 |
| 覆盖缺口 | — | BE 无 threads/comments/media 集成测；仅有 `test_auth` + `test_migrations` |

### 文档订正（相对初版）

1. **Prod Forum 默认 origin** 以 `app-prismax-forum-1053158761087.us-west1.run.app` 为准，不以旧 `forum.prismaxserver.com` 为代码默认（可用 `BACKEND_ORIGIN` 覆盖）。  
2. **BUG-01** 从「P0 打开」改为「testing/beta 已关闭，防回退」。  
3. 增补 **THR-09b / 作者详情删帖**、**ENV-05 Beta 门禁**。  
4. 用例与验收 **以当前 `testing` 为准**；勿用未含 `7bf2e1d` 的旧 `main` 工作区复测 Draft Edit。
