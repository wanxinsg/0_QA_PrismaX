# Sep 18 改动：业务逻辑、测试分析与 E2E 用例

> 日期：2026-09-18（UTC+8）  
> 范围：`app-prismax-rp`、`app-prismax-rp-backend`、`prismax-marketing-rp` 当日合入 `testing` 的全部 commit。  
> 分析基线：三仓 `git fetch` 后 `origin/testing`。  
> 最终 HEAD：frontend `bafaacc` / backend `053cb05` / marketing `61be618`。  
> 当天有两轮 lanmanc 提交（先落地、后重构）。**本文只测最终态**，不测被撤回的 Approve/Deny 邮件路径。

## 1. 范围与 Commit

### 1.1 app-prismax-rp

| Hash | 时间 (+08) | 作者 | 说明 |
| --- | --- | --- | --- |
| `46672b0` | 00:34 | lanmanc | Order Admin Remove 按钮布局；首次挂上 Robotics Data Beta Admin |
| `4b560d9` | 06:14 | Aparna | PRIS-333：Admin 展示 Egocentric Waitlist；Data Subscribers 表重命名 |
| `f3f3003` | 06:44 | aparna-prismax | Merge PR #87 `PRIS-333-landing-page-new-form-v7` |
| `bafaacc` | 06:52 | lanmanc | Data Subscribers 增加 Subscribers’ Information / Pending Beta Access |

### 1.2 app-prismax-rp-backend

| Hash | 时间 (+08) | 作者 | 说明 |
| --- | --- | --- | --- |
| `dbcd68b` | 00:33 | lanmanc | Robotics Data Beta 申请表 + My Data `is_rejected` / `rejected_episodes` |
| `0cc98f5` | 00:33 | lanmanc | Merge `testing` |
| `8aa3666` | 04:05 | Aparna | PRIS-335：`data_uploads.qa_score` 列；QA helper 迁到 `qa/` |
| `de8e83f` | 04:14 | aparna-prismax | Merge PR #77 `PRIS-335-refactor-qa-final-score-db` |
| `d1c496e` | 06:29 | Aparna | PRIS-333：Egocentric Waitlist 独立 API + Admin 列表 |
| `47d4e83` | 06:43 | aparna-prismax | Merge PR #78 `PRIS-333-landing-page-new-form-v7` |
| `053cb05` | 07:25 | lanmanc | Beta 申请改为只收集意向；去掉审核/发信；新增 Subscribers 只读列表 |

### 1.3 prismax-marketing-rp

| Hash | 时间 (+08) | 作者 | 说明 |
| --- | --- | --- | --- |
| `57d034d` | 00:32 | lanmanc | Robotics Data Beta 申请弹窗；My Data 入口门禁；Rejected 标记 |
| `cd9a05d` | 06:25 | Aparna | PRIS-333：独立 Egocentric Waitlist 弹窗；Footer 微调 |
| `694b0fe` | 06:45 | aparna-prismax | Merge PR #15 `PRIS-333-landing-page-new-form-v7` |
| `61be618` | 07:25 | lanmanc | 访问门禁：Membership **或** Organization 即可进 My Data |

### 1.4 主题与依赖

| 主题 | Frontend | Backend | Marketing | 依赖 |
| --- | --- | --- | --- | --- |
| PRIS-333 Egocentric Waitlist | Admin 新表 | 新提交 API + Admin 列表；从 Request Access 拆出 | 首页 Network 独立弹窗 | 需先跑 `20260917_create_marketing_egocentric_waitlist_requests.sql`。完整说明见 [`PRIS-333_egocentric_waitlist.md`](./PRIS-333_egocentric_waitlist.md) |
| PRIS-349 Robotics Data Beta | Data Subscribers 两张新分区 | Beta 申请/查询；Subscribers 分页；**审核接口已删除** | 申请弹窗 + Banner + My Data 门禁 | 需先跑 `20260915_create_robotics_data_beta_applications.sql`。完整说明见 [`PRIS-349_roboticsdatabetarelease.md`](./PRIS-349_roboticsdatabetarelease.md) |
| My Data Rejected 标记 | — | Summary / Episode 列表返回拒绝计数和 `is_rejected` | 行样式 + Rejected badge | 依赖 `data_order_reported_episodes` |
| PRIS-335 `qa_score` 列 | 无 UI 改动，读路径行为应变快/一致 | 写入 `data_uploads.qa_score`；Dashboard / QA Review / Jobs 改为读列 | — | 先 ALTER，再跑 backfill，再发代码。完整说明见 [`PRIS-335_data_uploads_qa_score.md`](./PRIS-335_data_uploads_qa_score.md) |
| Order Admin Remove 按钮 | Organization 成员 Remove 布局 | — | — | 无后端依赖 |

---

## 2. 总体业务影响

1. 首页 Network「Join the waitlist」不再走 Discover/Researcher 的 Request Access 表单，改为独立 Egocentric Waitlist；Admin Data Subscribers 可查看提交。
2. Robotics Data 目录仍可预览；**保存 / 下载 / My Data** 需要有效 download membership，或（仅 My Data）用户属于至少一个 Organization。申请表只登记意向，**不发邮件、不授予会员、没有 Approve/Deny**。
3. My Data 对客户拒绝的 episode 显示 Rejected 标记，并在侧栏给出 rejected 计数。
4. QA 终审分数写入 `data_uploads.qa_score`。Operator Dashboard、QA Review 列表、Jobs episode 阶段不再每次做 median 子查询。
5. Order Admin 移除组织 Owner 时，最后一位 Owner 的禁用提示改到按钮外层，避免 disabled 按钮吞掉 tooltip。

---

## 3. PRIS-333：Egocentric Waitlist

完整逻辑、风险与 E2E 已拆到 [`PRIS-333_egocentric_waitlist.md`](./PRIS-333_egocentric_waitlist.md)。

要点：Network「Join the waitlist」改为独立弹窗，写入 `marketing_egocentric_waitlist_requests`；Discover/Researcher 仍走 Request Access。Admin Data Subscribers 新增 Egocentric Waitlist 表。需先建表再发三仓。

---

## 4. PRIS-349：Robotics Data 意向收集、访问门禁与 Subscribers

完整逻辑、风险与 E2E 已拆到 [`PRIS-349_roboticsdatabetarelease.md`](./PRIS-349_roboticsdatabetarelease.md)。

要点：申请只登记、不授权。My Data = active membership **或** 属于某个 Organization；目录下载仍只要 membership。Admin 新增 Subscribers / Pending，无审核按钮。需先建表再发三仓。

---

## 5. My Data：客户拒绝 Episode 标记

### 5.1 业务逻辑

后端在 My Data 可访问集合上判断：该 episode 是否出现在 `data_order_reported_episodes`，且 source 为同一 `ORD-<order_id>`。

- `GET /data/my-data/summary` 增加 `rejected_episodes`
- `GET /data/my-data/episodes` 每行增加 `is_rejected`
- 计数是当前用户可见范围内的拒绝数，不是全局 QA reject

前端：

- `rejected_episodes > 0` 时侧栏标题显示 `· N rejected`
- `isEpisodeRejected(episode)` 以 `is_rejected` 为主，同时兼容 `REJECTED` / `CUSTOMER_REJECTED` 等历史字段
- 拒绝行增加样式和 `Rejected` badge，tooltip：`Rejected by customer · replacement queued`

拒绝标记 **不阻止** 查看详情；是否仍可下载取决于原 My Data 下载规则，本次未改下载权限。

### 5.2 测试分析与风险

| 风险 | 分析 | 验证重点 |
| --- | --- | --- |
| 跨 Order 误标 | JOIN 要求 `ORD-` + 同一 order_id | 只在对应 Order source 下标记；别的 source 同一 episode 不误伤 |
| QA reject 与客户 reject 混淆 | 本次只看 `data_order_reported_episodes` | QA 失败但客户未 report 的 episode 不应出 Rejected badge |
| 计数与列表不一致 | summary 与 list 应用同一 EXISTS | 侧栏数字 = 当前可见 rejected 行数（注意过滤条件） |
| 过滤后计数 | summary 的 rejected 未随 task/robot 过滤 | 记录实际：总数旁的 rejected 是否随筛选变化 |
| 无拒绝数据回归 | — | 不显示 `· 0 rejected`，无 badge |

### 5.3 完整 E2E 测试用例

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| SEP18-REJ-001 | P0 | 拒绝行标记 | Order A 中 episode 101 已被客户 report | 该用户打开 My Data，必要时按 Order A 过滤 | 101 行有 Rejected badge 和拒绝样式；`is_rejected=true` |
| SEP18-REJ-002 | P0 | 侧栏计数 | 可见范围内 3 条被拒 | 打开 My Data | 标题含 `· 3 rejected` |
| SEP18-REJ-003 | P0 | 无拒绝 | 用户数据全未 report | 打开 My Data | 无 rejected 文案，无 badge |
| SEP18-REJ-004 | P0 | 不跨 Order 污染 | 101 只在 Order A 被拒，也出现在别的 source | 分别按 A 和其他 source 看 | 仅 A 下标记；其他 source 不显示 Rejected |
| SEP18-REJ-005 | P1 | QA 失败不是客户拒绝 | episode QA fail 但未 report | 打开 My Data | 无 Rejected badge |
| SEP18-REJ-006 | P1 | 仍可打开详情 | 被拒 episode | 点击该行 | 详情打开，不崩溃 |
| SEP18-REJ-007 | P2 | 深链到被拒 episode | ` /robotic-data/<id>?view=my-data` | 有权限用户打开 | 详情打开且列表中该行标记 Rejected |

---

## 6. PRIS-335：`data_uploads.qa_score`

完整逻辑、风险、部署顺序与 E2E 已拆到 [`PRIS-335_data_uploads_qa_score.md`](./PRIS-335_data_uploads_qa_score.md)。

要点：终审分写入 `data_uploads.qa_score`；Dashboard / QA Review / Jobs 改读列。必须先 ALTER → backfill `--apply` → 再发 data-pipeline。未迁列就发代码会 500。

---

## 7. Order Admin：Remove Owner 按钮

### 7.1 业务逻辑

Organization Detail 里，客户 Owner 与 Internal Owner 的 Remove 按钮外包一层 `span.removeOwnerAction`。

- 最后一位客户 Owner：按钮 disabled，**外层 span** 承担 title：`Please add another owner before removing this one.`
- 非最后 Owner / Internal Owner：仍可点 Remove，后续确认流不变。

没有新 API。目的是让 disabled 按钮的 tooltip 在浏览器里能显示。

### 7.2 测试分析与风险

| 风险 | 分析 | 验证重点 |
| --- | --- | --- |
| 仍可删最后 Owner | 只改 DOM | disabled + 原 API 保护都在 |
| Tooltip 仍不出现 | 某些浏览器对包裹层也有限制 | hover 外层能看到提示 |
| Internal Owner 被误禁用 | 只有 last customer owner 禁用 | Internal Remove 始终可点（权限允许时） |
| 移动端 | hover tooltip 弱 | 至少按钮不可点，不出现误删 |

### 7.3 完整 E2E 测试用例

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| SEP18-ORD-001 | P0 | 最后一位 Owner | Org 仅 1 个客户 Owner | 打开 Organization Detail，hover Remove | 按钮 disabled；提示 `Please add another owner before removing this one.`；请求不发出 |
| SEP18-ORD-002 | P0 | 多名 Owner | ≥2 客户 Owner | Remove 其中一位并确认 | 成功移除；另一位仍在 |
| SEP18-ORD-003 | P1 | Internal Owner | 存在 internal owner | Remove internal | 不因 last-owner 规则被禁用；移除成功 |
| SEP18-ORD-004 | P1 | 添加 Owner 后解锁 | 先只有 1 个 Owner | 加成 2 个后再看原按钮 | 原 Owner 的 Remove 可点 |
| SEP18-ORD-005 | P2 | 布局 | 桌面 + 窄屏 | 看成员行 | Remove 不把行高撑乱，不遮挡 email/ID |

---

## 8. 跨功能回归

| ID | 优先级 | 场景 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- |
| SEP18-CROSS-001 | P0 | 两套获客表单互不写入 | 同一 email 先 Discover Request Access，再 Egocentric Waitlist | 分别进 interest 表和 waitlist 表；Admin 两张表都能看到 |
| SEP18-CROSS-002 | P0 | Beta 申请不影响 Order | Org owner 无 download membership，创建/查看 Order，再申请 Beta | Order 流程不变；申请不改 membership；My Data 仍靠 org 打开 |
| SEP18-CROSS-003 | P0 | 拒绝标记 + Task 过滤 | 从 Order Task 进 My Data，该 Task 含被拒 episode | source+task 过滤仍准；被拒行有 badge；计数不为负 |
| SEP18-CROSS-004 | P1 | QA 分数与 Jobs / Dashboard 一致 | 终审一个 upload，看 Dashboard、QA Review、Job QC | 三处分数/阶段都读同一 `data_uploads.qa_score` |
| SEP18-CROSS-005 | P1 | Admin Data Subscribers 五区 | 从上到下点五个 sub-nav | Contact Sales、Discover/Researcher、Waitlist、Subscribers、Pending 无串台 |
| SEP18-CROSS-006 | P1 | 登录态互不污染 | 同浏览器 Admin token + 营销站 gateway session | Waitlist/Subscribers 用 Admin token；Beta 申请用 gateway token |
| SEP18-CROSS-007 | P2 | Footer 与首页 CTA | 从首页 Network 提交 waitlist，再从 Footer 进 Brand Kit | Waitlist 成功；Brand Kit 新标签，不影响弹窗状态 |

---

## 9. 测试数据与环境准备

- 营销站、Admin Portal、data-pipeline 均指向含当日 commit 的 `testing`。
- 已执行：
  - `20260917_create_marketing_egocentric_waitlist_requests.sql`
  - `20260915_create_robotics_data_beta_applications.sql`
  - `20260916_data_uploads_qa_score_column.sql` + backfill（QA 分数相关用例）
- Email：未用过的 waitlist 邮箱；已在 waitlist 的邮箱；Discover 与 Waitlist 可共用对比邮箱。
- 用户矩阵：
  - 未登录访客
  - 有 email、无 membership、无 org
  - ACTIVE download membership
  - 仅 Organization member / owner（无 membership）
  - 无 email 钱包号
  - Admin 白名单钱包
- Order：至少一个 delivering/后态 Order，其中 1 条 episode 已写入 `data_order_reported_episodes`，并另有未拒绝 episode。
- QA：至少一个已终审 upload、一个进行中 upload；一个 job 含不同 `qa_score`。
- Organization：至少 1-owner 和 2-owner 各一个，便于 Remove 用例。
- 桌面 Chrome；Network / Application / DB 可查。

---

## 10. 发布准入

- [ ] 三仓 `testing` 含第 1 节全部最终 commit；营销站、Admin、user-management、data-pipeline 一起发，避免 Waitlist/Beta 表单打到旧 API。
- [ ] Waitlist 表、Beta 申请表已建。`qa_score` 列已加且历史 backfill 已 apply（若本次发 data-pipeline）。
- [ ] PRIS-333 所有 P0：见 [`PRIS-333_egocentric_waitlist.md`](./PRIS-333_egocentric_waitlist.md)；独立 Waitlist 提交、去重、Admin 可见；Discover/Researcher 未回退。
- [ ] PRIS-349 所有 P0：见 [`PRIS-349_roboticsdatabetarelease.md`](./PRIS-349_roboticsdatabetarelease.md)；申请不授权；My Data = membership **或** org；目录下载只要 membership；review API 404。
- [ ] 第 5 节所有 P0：客户拒绝标记准确，不把 QA reject 显示成客户拒绝。
- [ ] PRIS-335 所有 P0：见 [`PRIS-335_data_uploads_qa_score.md`](./PRIS-335_data_uploads_qa_score.md)；新终审写入列；Dashboard / QA Review / Jobs 读列且无 500。
- [ ] 第 7 节 P0：最后 Owner 不能删，tooltip 可见。
- [ ] 跨功能 P0 通过。
- [ ] 单测（如环境允许）：
  - backend `test_robotics_data_interest.py`
  - backend `test_data_membership_downloads.py` 中 rejection 断言
  - marketing `tests/roboticDataRules.test.mjs`、`tests/myDataEpisodeStatus.test.mjs`
  - frontend `SubscribersInformation.test.js`、`RoboticsDataBetaApplications.test.js`

---

## 11. 已知限制（记到测试报告即可，不挡 P0 除非产品要求修）

1. Waitlist `email` 无 DB UNIQUE，极端并发可能双插。
2. Waitlist Admin GET、Beta 申请 Admin GET 未校验 `role=admin`；Subscribers GET 有校验。
3. 前端申请表无 `other` 平台芯片，后端允许 `other`。
4. Subscribers 列表不过滤 plan ACTIVE，只看 membership 字段非空。
5. Beta 申请历史 status 对用户接口一律显示 `pending`，Admin 列表仍可能露出库内原始 status 字段（UI 未渲染 status 列）。
6. Banner dismiss 不持久化。
7. `qa_score` 未迁移就发 data-pipeline 会让 Dashboard/Jobs/QA Review 失败。
