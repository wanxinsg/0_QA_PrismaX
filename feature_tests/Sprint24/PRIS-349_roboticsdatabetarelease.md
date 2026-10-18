# PRIS-349 Robotics Data Beta Release

> 分析日期：2026-09-18  
> 范围：三仓联动。Robotics Data 意向收集、访问门禁、Admin Subscribers / Pending。  
> 日汇总见 [`Sep18.md`](./Sep18.md)。  
> **只测最终态。** 当天第一轮 lanmanc 提交曾挂过 Customers Tab 和审核/发信，第二轮已撤回，不要测 Approve/Deny 邮件路径。

| 仓库 | 最终 Commit | 说明 |
| --- | --- | --- |
| `prismax-marketing-rp` | `57d034d` 申请弹窗 + 门禁；`61be618` Membership **或** Organization 可进 My Data | 用户侧 |
| `app-prismax-rp-backend` | `dbcd68b` 建表；`053cb05` 只收集意向，去掉审核/发信，新增 Subscribers 列表 | user-management |
| `app-prismax-rp` | `46672b0` 首次挂 Beta Admin；`bafaacc` 收到 Data Subscribers：Subscribers’ Information / Pending Beta Access | Admin |

依赖：先执行 `20260915_create_robotics_data_beta_applications.sql`。

---

## 1. Feature 描述

Robotics Data 进入 limited beta：目录可预览；保存 / 下载 / My Data 受门禁。申请表只登记意向，**不发邮件、不授予会员、没有 Approve/Deny**。

| 项目 | 规则 |
| --- | --- |
| Browse 预览 | 未登录也可看目录 |
| 目录下载 / 保存 | 需要 **ACTIVE download membership** |
| My Data / Account | ACTIVE membership **或** 属于 ≥1 个 Organization |
| 申请 | 只 INSERT，不改 `user_data_download_membership` |
| Admin 审核 | 接口已删除，UI 无 Approve/Deny |

**不在本次范围：**

- 人工开通 membership 的后台流程（本 feature 不提供）

---

## 2. 最终产品规则（`053cb05` / `61be618` / `bafaacc`）

申请 **不等于** 开通。开通只看 download membership 是否在 `data_api_download_membership_plans` 且 `status=ACTIVE`。

```text
Browse Datasets
  → 任何人可预览目录（含未登录）
  → Banner：previewing beta；Apply / View application
  → 点下载 / 保存：
        未登录 → 登录
        已登录但无 active membership → 打开申请弹窗
        有 active membership → 走配额下载

My Data / Account
  → 未登录 → 登录
  → 有 active membership  ──┐
  → 或属于 ≥1 个 Organization ┼→ allowed
  → 否则 → 申请弹窗，并退回 Browse

申请表 POST /api/robotics-data/beta-applications
  → 只 INSERT robotics_data_beta_applications
  → 不发邮件、不改 membership、不提供 Admin 审核接口
```

---

## 3. 用户申请

`POST /api/robotics-data/beta-applications`

- 必须登录；email 取自账号，前端只读，后端忽略 payload 里的 email。
- 必填：`access_need` ∈ `{self_serve, custom}`；`selfserve` 归一成 `self_serve`。
- `robot_platforms` 可选多选，合法值：`yam` / `piper` / `tok2` / `realman` / `unitree_g1` / `other`。前端芯片没有 `other`，只能测 API。
- Organization / Role 选填，最长 255。
- 已有 active membership：200，`Robotics data access is already active.`，不写申请。
- 已有任意历史申请（含曾经 approved/denied 的遗留行）：200，`Your interest has already been registered.`，不再插入。
- 新申请：201，status=`pending`。
- 无登录：401；账号无 email：400。
- Rate limit：10/hour。

营销站组件：`RoboticsDataBetaApplicationModal.tsx`，由 `/robotic-data` Banner / My Data / 目录下载门禁打开。

---

## 4. 访问查询

`GET /api/robotics-data/beta-access`

- `has_access` **只**看 active membership，不看申请 status。
- 无 membership 时，只要库里有申请，接口 `status` 一律返回 `pending`（即使历史行是 approved/denied）。
- 无申请：`not_applied`。
- 有 membership：`approved`，且不再查申请行。

---

## 5. 前端门禁 `resolveRoboticsDataAccessGate`

| Token | Membership 已解析且有效 | Org 已解析且用户有组织 | 结果 |
| --- | --- | --- | --- |
| 无 | — | — | `sign_in` |
| 有 | 任一侧已确认授权 | — | `allowed` |
| 有 | 两侧都解析完且都未授权 | — | `apply` |
| 有 | 任一侧未解析完，且尚未授权 | — | `checking` |

注意：

- **Organization 只放开 My Data / Account，不放开目录下载。** 目录下载仍要求 `hasRoboticDataBetaAccess`（membership）。
- Banner 在 `sign_in` 或 `apply` 时显示，可 × 关闭（仅当前会话）。
- 无 membership 时 Banner CTA：未登录 `Apply →`；已申请 `View application →`。
- 切账号 / 登出后，未完成的 access 状态不能带到下一个 session。
- On-Demand Data（Orders）不受该 Beta 门禁；创建仍走原 org/owner 规则。

---

## 6. Admin

中间态 `Customers` 顶层 Tab 已被撤回，最终只在 **Data Subscribers** 内。

### 6.1 Pending Beta Access

- `GET /api/admin/robotics-data-beta-applications`，最多 500 条，按 `applied_at DESC`。
- 列：User（email + ID）/ Requested At / Company·Role / Robot Platforms / Access Need（Self-serve 或 Custom request）。
- **没有 Approve / Deny。** `POST /api/admin/robotics-data-beta-applications/<id>/review` 必须 404。
- 不展示 `user_name`。
- 该 GET **未**显式校验 `role=admin`（仅 JWT）。

### 6.2 Subscribers’ Information

- `GET /api/admin/robotics-data-subscribers?page=`
- **有** `role=admin` 检查；非 admin → 403。
- 条件：`user_data_download_membership` 去空格后非空。**不过滤 plan 是否 ACTIVE**，过期/无效 membership 字符串也会出现。
- 每页 25；非法 page 回落到 1。
- 列：User（优先 email，否则 Solana 地址 + ID）/ Download membership。有 email 时不展示钱包。
- 只读，无批准按钮。

---

## 7. 风险点

| 编号 | 风险 | 优先级 | 验证重点 |
| --- | --- | --- | --- |
| R-01 | 把申请当成开通 | 高 | 提交后 My Data 仍进不去；目录仍不能下载，除非另有 membership/org |
| R-02 | Org-only 用户能力混淆 | 高 | Org member 能进 My Data 看 order 数据；Browse 下载仍弹申请 |
| R-03 | 遗留 approved 申请 | 高 | 历史 approved/denied 行不得让 `has_access=true` |
| R-04 | 审核入口回潮 | 高 | UI 和 API 都没有 Approve/Deny/发信 |
| R-05 | 申请 email 被伪造 | 高 | DB email = 登录账号 email |
| R-06 | Banner 与 Account 门禁不一致 | 中 | 无权限点头像进 Account 应弹申请，不应进入付费/配额页 |
| R-07 | Subscribers 含非 ACTIVE plan | 中 | 无效 membership 字符串仍出现在表中 |
| R-08 | Beta Admin 列表无 role 校验 | 中 | 记录普通 JWT 是否能读 500 条申请 |
| R-09 | 登录后竞态 | 高 | 快速换号不能闪一下旧用户的 My Data |
| R-10 | 深链 `view=my-data` | 高 | 无权限打回 Browse，清掉 view/source/task_id |

---

## 8. 测试数据与环境

- 营销站、Admin、user-management 含上表最终 commit；Beta 申请表已建。
- 用户矩阵：
  - 未登录访客
  - 有 email、无 membership、无 org
  - ACTIVE download membership
  - 仅 Organization member / owner（无 membership）
  - 无 email 钱包号
  - Admin 白名单钱包
- 至少一个 delivering/后态 Order，供 Org-only 从 Order 进 My Data。
- 桌面 Chrome；可看 Network / Application / DB。

---

## 9. E2E 测试用例

### 9.1 申请与 Banner

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| PRIS-349-001 | P0 | 未登录可浏览 | 无 session | 打开 `/robotic-data` | 目录可预览；出现 beta Banner；My Data 触发登录 |
| PRIS-349-002 | P0 | 登录后无权限申请 | 有 email、无 membership、无 org | 点 Banner Apply 或 My Data | 打开 `Apply for beta access`；work email 只读且等于账号 |
| PRIS-349-003 | P0 | 缺 access_need | 弹窗已开 | 不选 What do you need，提交 | 前端错误 `Tell us what you need — it routes your application.`；不请求 |
| PRIS-349-004 | P0 | 提交 Self-serve | 新用户 | 选平台、Self-serve datasets，提交 | 201；成功态 `Application received`；Admin Pending 出现该行；membership 不变 |
| PRIS-349-005 | P0 | 提交 Custom | 新用户 | 选 Custom data production | `access_need=custom`；Admin 显示 `Custom request` |
| PRIS-349-006 | P0 | 重复申请 | 已有申请 | 再提交 | 200 already registered；不新增行；弹窗进入 received/pending 态 |
| PRIS-349-007 | P0 | 申请不授权 | 刚提交成功 | 关弹窗，点下载、点 My Data、刷新 | 仍无 membership；下载弹申请；My Data 不能进入（除非另有 org） |
| PRIS-349-008 | P1 | 已有 membership 再申请 | ACTIVE plan 用户 | 调 POST 或打开弹窗 | 接口 200 already active；前端走 approved 态 `Your data access is active` |
| PRIS-349-009 | P1 | 无 email 账号 | 钱包用户无 email | 尝试申请 | 400 `Your account needs an email address`；前端错误可见 |
| PRIS-349-010 | P1 | 伪造 email | 登录 A | payload 带 B 的 email | DB 仍写入 A 的 email |
| PRIS-349-011 | P1 | 非法 platform | — | API 传 `robot_platforms:["yam","hack","YAM"]` | 只保存 `yam`；大小写归一 |
| PRIS-349-012 | P2 | Banner 关闭 | apply/sign_in | 点 × | Banner 消失；刷新后可再出现（未持久化） |
| PRIS-349-013 | P1 | View application | pending 用户 | 点 Banner `View application` | 不显示空白表单，而是 Application received |

### 9.2 My Data / 下载门禁

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| PRIS-349-014 | P0 | Membership 用户 | ACTIVE download membership | 打开 My Data；从目录下载 | 两边都允许；不出现申请弹窗；Banner 不显示 |
| PRIS-349-015 | P0 | Org-only 用户 | 无 membership，但是某 Organization member | 进 My Data；再在 Browse 点下载 | My Data 允许；目录下载仍要求 membership/申请；Banner 因 gate=allowed 不显示 |
| PRIS-349-016 | P0 | 两无用户 | 无 membership 无 org | 点 My Data、点目录下载 | 都打开申请弹窗；停留在 Browse |
| PRIS-349-017 | P0 | 深链无权限 | 两无用户访问 `?view=my-data&source=ORD-1` | 打开 URL | 回到 Browse；清掉 view/source/task_id；打开申请或登录 |
| PRIS-349-018 | P0 | 深链有权限 | membership 或 org 用户同一 URL | 打开 URL | 进入 My Data 并按 source/task 过滤 |
| PRIS-349-019 | P1 | 登录后继续原动作 | 未登录点 My Data | 完成登录，用户有权限 | 自动进入 My Data；用户无权限则打开申请 |
| PRIS-349-020 | P1 | Account 入口 | 两无用户 | 点头像/Account | 不进 Account，打开申请；有权限才 `/account` |
| PRIS-349-021 | P0 | 切换账号隔离 | 先登录有权限用户，再换无权限用户 | 观察 My Data 和下载 | 必须重新检查；不得短暂展示上一个用户的 My Data/配额 |
| PRIS-349-022 | P1 | 检查中不误弹 | 慢网络 | 登录后立刻点 My Data | `checking` 期间等待，不闪申请弹窗；完成后按结果进入或申请 |
| PRIS-349-023 | P1 | Orders 不受 Beta 限制 | 两无用户但是可以登录 | 打开 On-Demand Data | Orders 可进（创建仍受原 org/owner 规则约束） |
| PRIS-349-024 | P0 | 从 Order 进 My Data | Org-only owner，order 已 delivering | 点 View in My Data | 因 org 授权进入 My Data；source+task 过滤仍有效 |

### 9.3 Admin Subscribers / Pending

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| PRIS-349-025 | P0 | Pending 列表 | 至少 1 条申请 | Data Subscribers → Pending Beta Access | 计数正确；email 在 ID 之上；平台 chip；无 Approve/Deny |
| PRIS-349-026 | P0 | 审核 API 已删除 | Admin token | `POST .../beta-applications/1/review` | 404；不改 status、不发邮件、不改 membership |
| PRIS-349-027 | P0 | Subscribers 列表 | 有 membership 用户 | Subscribers’ Information | 只显示 membership 非空用户；有 email 不展示钱包；分页 25 |
| PRIS-349-028 | P0 | Subscribers 需 admin | 普通用户 JWT | GET `/api/admin/robotics-data-subscribers` | 403；Admin 页不展示他人数据 |
| PRIS-349-029 | P1 | 空态 | 无申请 / 无 subscriber | 打开两张表 | Pending：`No interest registrations yet.`；Subscribers：`No subscribers found.` |
| PRIS-349-030 | P1 | Refresh | 另开窗口新增申请 | 点 Refresh | 列表更新 |
| PRIS-349-031 | P1 | 无 Customers 顶栏 | Admin Portal | 看顶层 Tab | 无独立 Customers Tab；入口只在 Data Subscribers |
| PRIS-349-032 | P2 | 非法 page | — | `page=0/-2/abc` | 当作 page=1，200 |
| PRIS-349-033 | P1 | Session 过期 | Admin token 失效 | 打开两张表 | 走 Admin session expired，不把 401 显示成空列表 |

### 9.4 跨功能

| ID | 优先级 | 场景 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- |
| PRIS-349-034 | P0 | Beta 申请不影响 Order | Org owner 无 download membership，创建/查看 Order，再申请 Beta | Order 流程不变；申请不改 membership；My Data 仍靠 org 打开 |
| PRIS-349-035 | P1 | Data Subscribers 不串台 | 从上到下点五个 sub-nav | Contact Sales、Discover/Researcher、Waitlist、Subscribers、Pending 各表独立 |
| PRIS-349-036 | P1 | Token 互不污染 | 同浏览器 Admin token + 营销站 gateway session | Subscribers 用 Admin token；Beta 申请用 gateway token |

---

## 10. 发布前检查清单

- [ ] 三仓含最终 commit（`bafaacc` / `053cb05` / `61be618`）；`robotics_data_beta_applications` 已建
- [ ] 营销站、Admin、user-management 一起发
- [ ] 所有 P0：申请不授权；My Data = membership **或** org；目录下载只要 membership；review API 404
- [ ] 无 Customers 顶栏；Pending / Subscribers 只读
- [ ] 单测（如环境允许）：
  - backend `test_robotics_data_interest.py`
  - marketing `tests/roboticDataRules.test.mjs`
  - frontend `SubscribersInformation.test.js`、`RoboticsDataBetaApplications.test.js`

---

## 11. 已知限制

1. 前端申请表无 `other` 平台芯片，后端允许 `other`。
2. Subscribers 列表不过滤 plan ACTIVE，只看 membership 字段非空。
3. Beta 申请历史 status 对用户接口一律显示 `pending`；Admin 列表未渲染 status 列。
4. Banner dismiss 不持久化。
5. Pending Admin GET 未校验 `role=admin`；Subscribers GET 有校验。
6. 开通仍依赖人工改 membership / 加 Organization，本 feature 不提供审核流。

---

## 12. 关联说明

- 与 PRIS-333 Waitlist 同挂 Data Subscribers，写入表不同，测时不要串台。
- `dbcd68b` 还带了 My Data `is_rejected`，逻辑独立，见 `Sep18.md` 第 5 节。
- 日汇总见 [`Sep18.md`](./Sep18.md)。
