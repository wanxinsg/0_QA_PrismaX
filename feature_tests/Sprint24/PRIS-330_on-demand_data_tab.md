# PRIS-330：On-Demand Data Tab — Order Management 功能分析

> 分析日期：2026-08-31（v1）/ <span style="color:#2563eb">2026-09-03（v2 补充：交付审批、开票闭环、Bad episode、下载命名）</span>  
> 分析人：AI（基于代码 diff）；未执行远端部署验证。  
> <span style="color:#2563eb">蓝色文字 = 新增 / 变更内容。</span>
>
> 分析范围（Chris / lanmanc，order 相关改动）：
>
> - `app-prismax-rp` `67c8157`（含）→ 最新（v2 重点：`c176c76`→`7ec491a`）
> - `app-prismax-rp-backend` `676b173`（含）→ 最新（v2 重点：`fe777d9`→`03eb170`）
> - `prismax-marketing-rp` `53ef26b`（含）→ 最新（v2 重点：`4bf92eb`→`d01ab88`，**仅 `origin/testing`**）
> - <span style="color:#2563eb">`sdk-vla-foundry` `002a29c`（下载命名文档/单测对齐，仅 `origin/testing`）</span>

---

## 1. 业务逻辑

### 1.1 核心概念


| 概念                    | 说明                                                                              |
| --------------------- | ------------------------------------------------------------------------------- |
| **Organization**      | 企业客户主体；一个用户只能属于一个组织；Organization Owner 管理订单和成员，Member 只读                                     |
| **Order（生产订单）**       | 企业向 PrismaX 下单，含若干 task items（名称 + 工时）和 due date                                |
| **Hourly Rate**       | Admin 定价，`null` 表示待定；rate 与 owner 确认一致 → production，Admin 改价 → pending_approval |
| <span style="color:#2563eb">**Order Item `task_id`**</span> | <span style="color:#2563eb">catalog 行可空链接 `data_tasks.task_id`；custom 行 `task_id = NULL`；`name` 仍为历史 scenario 快照。进入 production 前 catalog 行必须有有效 `task_id`。</span> |
| <span style="color:#2563eb">**Delivery Progress**</span> | <span style="color:#2563eb">按 Order item 的 `task_id` 聚合 Job→Upload→Episode 时长；`accepted = delivered − reported_bad`；全部 task `accepted ≥ requested` 才 `delivery_ready`。</span> |
| <span style="color:#2563eb">**Bad Episode Report**</span> | <span style="color:#2563eb">Organization Owner 仅在 `delivering` 可永久上报坏 episode；立即从 accepted hours 扣除，不可撤销。</span> |
| **Invoice（发票）**       | <span style="color:#2563eb">Admin 对 **`ready_for_invoice`**（非 complete）订单开具 PDF，可跨 order 合并；`Mark paid` 将关联 Orders 一并 `complete`。</span> |
| **OrderSourceFilter** | <span style="color:#2563eb">My Data 按 Order 过滤；数据源含 **`delivering` / `ready_for_invoice` / `complete`** 的 `ORD-*`（v1 仅 complete）。</span> |


---

### 1.2 订单状态机

```
draft ──[owner submit]──► submitted
  │                           │
  │                  [admin approve]
  │                    ┌──────┴──────────────────┐
  │              rate 不变                   rate 变
  │                    ↓                         ↓
  │               production              pending_approval
  │                    │                         │
  │         [mark-delivering]           [owner approve]
  │                    ↓                         │
  │               delivering ◄──────────────────┘
  │                    │
  │     ┌──────────────┴──────────────┐
  │     │  [owner report bad episodes] │  （可选，可多次；不可撤销）
  │     │  [owner approve-delivery]    │  需 delivery_ready + confirmed
  │                    ↓
  │           ready_for_invoice
  │                    │
  │     [admin issue invoice PDF]
  │     [admin mark-paid + confirmed]
  │                    ↓
  │                complete
  │
  └──[cancel]──► cancelled   （可从 draft / submitted / pending_approval 取消）
```

<span style="color:#2563eb">

> 去掉 Admin 在 `delivering` 上直接 `complete`。  
> 新路径：`delivering` →（Organization Owner `approve-delivery`）→ `ready_for_invoice` →（Admin 开票 + `mark-paid`）→ `complete`。

</span>

#### 各状态可执行操作


| 状态                 | Organization Owner                     | Admin                      |
| ------------------ | ------------------------- | -------------------------- |
| `draft`            | edit, submit, cancel      | edit, cancel               |
| `submitted`        | edit, cancel              | edit, approve, cancel      |
| `pending_approval` | **approve**, edit, cancel | edit, cancel               |
| `production`       | —                         | mark_delivering            |
| `delivering`       | <span style="color:#2563eb">**approve_delivery**（需 delivery_ready；见 `allowed_actions`）；**report bad episodes**（前端硬编码，不在 `allowed_actions`）</span> | <span style="color:#2563eb">—（不再 complete；`/complete` 已 404）</span> |
| <span style="color:#2563eb">`ready_for_invoice`</span> | <span style="color:#2563eb">查看交付进度 / 发票（开票后）</span> | <span style="color:#2563eb">开具发票；Mark paid → 关联 Orders complete</span> |
| `complete`         | 查看/下载发票                   | <span style="color:#2563eb">（已付发票只读；不再从 complete 开票）</span> |
| `cancelled`        | —                         | —                          |

#### 关键动作（最终路径）

| 动作 | 执行方 | 说明 |
|---|---|---|
| `approve_delivery` | Organization Owner | `delivering` → `ready_for_invoice`；需 delivery_ready |
| `reported-episodes` | Organization Owner | 仅 `delivering`；不可撤销；accepted hours 立即扣除 |
| `issue invoice` | Admin | 仅对 `ready_for_invoice` 且未开票的订单 |
| `mark-paid` | Admin | 发票付款，同步将关联 Orders 标为 `complete` |

---

### 1.3 关键业务规则


| 规则                   | 逻辑                                                                                            |
| -------------------- | --------------------------------------------------------------------------------------------- |
| **Admin Approve**    | 只允许 `submitted` → approve；rate 与原值相同 → `production`；rate 变化 → `pending_approval`              |
| **Organization Owner Edit 退状态**   | 在 `pending_approval` 时编辑 → 强制退回 `submitted`（作废现有报价）                                           |
| **Admin Edit 退状态**   | 编辑 `draft` 时状态永远保持 draft；编辑 `submitted`/`pending_approval` 且 rate 有变 → `pending_approval`     |
| **确认机制**      | `body.confirmed=true` 或 Header `X-Action-Confirmed: true` 必须存在，否则 409 `confirmation_required`（cancel / <span style="color:#2563eb">approve-delivery / report bad /</span> mark-paid 等） |
| **Organization Owner Approve 前置** | admin 必须先设 rate（`hourly_rate_usd_cents IS NOT NULL`），否则 409                                   |
| **Cancel 限制**        | 只允许从 `draft`/`submitted`/`pending_approval` 取消；`production` 及以后返回 409                         |
| <span style="color:#2563eb">**Approve Delivery**</span> | <span style="color:#2563eb">仅 `delivering` + `delivery_ready`；成功 → `ready_for_invoice`；不可撤销。</span> |
| <span style="color:#2563eb">**Bad Episode Report**</span> | <span style="color:#2563eb">仅 Organization Owner + `delivering`；单次 ≤5000；reason ≤500 字符；episode 必须属于该 Order 的 Job 链路；已上报跳过；不在订单返回 `not_in_order_episode_ids`。</span> |
| <span style="color:#2563eb">**Accepted Hours**</span> | <span style="color:#2563eb">`accepted_seconds = max(delivered_seconds − reported_bad_seconds, 0)`；`delivery_ready` 要求**每个**有 `task_id` 的 item `accepted ≥ requested`；任一 `task_id=NULL` 的 item 会使 `delivery_ready=false`。</span> |
| <span style="color:#2563eb">**Invoice 开票对象**</span> | <span style="color:#2563eb">后端 + Admin UI：仅 `ready_for_invoice` 且未开票的同 org Orders；开票**不改**订单状态，仍停留 `ready_for_invoice`；`Mark paid` 才将关联 Orders → `complete`。金额按 `Σ(requested_hours × rate)`，非 accepted hours。</span> |
| <span style="color:#2563eb">**Job ↔ Order Tasks**</span> | <span style="color:#2563eb">创建/更新带 `order_id` 的 Job 时，每个 task_id 必须属于该 Order 的 catalog items；省略 `order_id` 保留原链接，显式 `null` 才 unlink。Admin UI 仅有自由文本 Order ID，任务合法性靠后端校验。</span> |
| <span style="color:#2563eb">**Admin 创建订单**</span> | <span style="color:#2563eb">Admin 创建跳过 `draft`：有 rate → `pending_approval`，无 rate → `submitted`。</span> |
| <span style="color:#2563eb">**My Data 下载配额**</span> | <span style="color:#2563eb">`access_context: "my_data"` 时 `enforce_monthly_quota=False`，不走个人月配额；共享 episode 不复制进 personal library。</span> |


---

### 1.4 Organization 管理

- **创建组织**（Admin）：传 `owner_email`，后端 COALESCE 匹配 `email`/`user_profile_email`/`linked_email` 三字段查用户；已属于其他组织返回 409；组织 `email_domain` 取自 owner email 的 `@` 后缀。
- **邀请成员**（Organization Owner）：生成 7 天（168h）有效的 token（SHA-256 hash 存库），v1 不发邮件，token 直接返回由前端构造链接；**邀请 email 域名必须匹配**组织 `email_domain`，否则拒绝。
- **接受邀请**：URL `?invite=TOKEN` 传入 `OrderWorkspace`；无组织时展示 **Accept invitation** 按钮，需用户点击后才调用 `acceptInvitation`（非页面加载自动 accept）。成功后清除 URL 参数。登录用户 email 必须与邀请 email 一致，否则 403。
- **Owner 不可通过 members API 移除**；Admin 可通过 `POST …/owners` 添加多个 Organization Owner。

---

### 1.5 My Data 订单数据源过滤

<span style="color:#2563eb">

`GET /api/orders/data-sources` 返回状态为 **`delivering` / `ready_for_invoice` / `complete`** 的订单作为数据源（`{type:"order", id:"ORD-X"}`）。

My Data 列表/汇总通过 CTE 解析可访问 episode：

```
self（个人 library ACTIVE）
  ∪
Order → Jobs(order_id) → Uploads → Episodes
  （org 成员；order status ∈ delivering|ready_for_invoice|complete；
   episode 排除 DERIVED_VALIDATION_FAILED / FAILED）
```

- `source_ids` 支持 `self` 与 `ORD-<id>`；仅选某 ORD 时不泄漏 personal library。
- Marketing 下载请求增加 `access_context: "my_data"`，后端用 `_accessible_my_data_episode_ids` 再鉴权，并跳过月配额。
- 组织成员被移除后，下一次请求即失去共享 Order 数据。
- `OrderSourceFilter` 本身不按 status 过滤；可见 ORD 源完全依赖后端 `data-sources` 返回。

</span>

`OrderSourceFilter` 渲染为多选下拉，全选等于无过滤（`null`），变更后将 `source_ids` 追加到 `GET /data/my-data/episodes`。

---

## 2. Data Flow

### 2.1 Admin 端

```
AdminPortal → Orders Tab → OrderAdminDashboard(adminToken)
  │
  ├─ 初始化：GET /api/admin/organizations + /admin/orders + /admin/invoices
  │          + GET /api/admin/task-scenarios（失败仅告警，不阻断）
  │
  ├─ Orders Tab：查看 / Create / Edit / Approve / Mark-Delivering / Cancel
  │              （详情展示 delivered_hours / delivery_ready；**不**展示 reported_bad/accepted；无 Complete 按钮）
  ├─ Organizations Tab：查看成员（GET /api/admin/organizations/<id>）/ 创建组织
  └─ Invoices Tab：勾选 ready_for_invoice 订单 + 上传 PDF → issue（订单状态不变）
                   → Mark paid & complete（同步 complete 关联 Orders）
```

### 2.2 Organization Owner 端

```
RoboticDataPageClient → ?view=orders → OrderWorkspace(gatewayToken, invitationToken)
  │
  ├─ 初始化：GET /api/organization + /orders + /invoices
  │          （无组织 → organization_required 错误 → 显示"联系 PrismaX"）
  │
  ├─ 邀请 token + 无组织 → 显示 Accept invitation → POST accept → 重新加载
  │
  ├─ 订单操作（Organization Owner only）：创建 / 编辑 / 提交 / 批价 / 取消
  │   delivering / ready_for_invoice：Delivery progress 卡片（含 delivered / reported_bad / accepted）
  │   delivering + owner：Approve delivery（看 allowed_actions）/ Report bad（UI 硬编码）
  ├─ 发票下载：GET /api/invoices/<ref>/download → signed URL → window.open
  └─ Team 管理：创建邀请 / 撤销邀请 / 移除成员
```

### 2.3 My Data + OrderSourceFilter

```
MyDataWorkspace
  ├─ OrderSourceFilter → GET /api/orders/data-sources
  │     （delivering | ready_for_invoice | complete）
  ├─ 过滤变更 → source_ids 追加到 loadSummary() + loadEpisodes()
  └─ 下载 → POST … { selected_episode_ids, access_context: "my_data", … }
            落盘文件名优先 episode_id（{id}.mcap / {id}_video.mp4）
```

<span style="color:#2563eb">

### 2.4 Job ↔ Order ↔ My Data

```
Admin 创建/更新 Job（order_id 必填时）
  → 校验 tasks ⊆ Order catalog task_ids
  → Operator 按 Job 上传
  → Episodes 进入 Order 交付进度（按 task_id 聚合）
  → Organization Owner 可 Report bad / Approve delivery
  → ready_for_invoice 后 Admin 开票 → Mark paid → complete
  → Org 成员在 My Data 看见 ORD-* 源（delivering 起即可）
```

</span>

---

## 3. API 端点列表

### 3.1 Admin 端点（Bearer Admin JWT）


| 方法      | 路径                                            | 说明            | Body / 参数                                            |
| ------- | --------------------------------------------- | ------------- | ---------------------------------------------------- |
| `GET`   | `/api/admin/organizations`                    | 列出所有组织        | —                                                    |
| `POST`  | `/api/admin/organizations`                    | 创建组织          | `{name, owner_email}`                                |
| `GET`   | `/api/admin/organizations/<id>`               | 获取组织详情（含成员）   | —                                                    |
| `POST`  | `/api/admin/organizations/<id>/owners`        | 添加 Organization Owner      | `{owner_email}`                                      |
| <span style="color:#2563eb">`GET`</span> | <span style="color:#2563eb">`/api/admin/task-scenarios`</span> | <span style="color:#2563eb">列出 `data_tasks` catalog（scenario 非空）</span> | <span style="color:#2563eb">—</span> |
| `GET`   | `/api/admin/orders`                           | 列出订单          | `?organization_id=&status=`                          |
| `GET`   | `/api/admin/orders/<ORD-ref>`                 | 订单详情          | —                                                    |
| `POST`  | `/api/admin/organizations/<id>/orders`        | 创建订单          | `{tasks[{task_id,name,hours,is_custom}], due_date, …}` |
| `PATCH` | `/api/admin/orders/<ORD-ref>`                 | 编辑订单          | 同上                                                   |
| `POST`  | `/api/admin/orders/<ORD-ref>/approve`         | 审批定价          | `{hourly_rate}`                                      |
| `POST`  | `/api/admin/orders/<ORD-ref>/mark-delivering` | 进入 delivering | —                                                    |
| ~~`POST` `/api/admin/orders/<ORD-ref>/complete`~~ | <span style="color:#2563eb">**v2 产品路径废弃**</span> | <span style="color:#2563eb">改由 Invoice `mark-paid` 完成 Orders</span> | — |
| `POST`  | `/api/admin/orders/<ORD-ref>/cancel`          | 取消订单          | `{confirmed: true}`                                  |
| `GET`   | `/api/admin/invoices`                         | 列出发票          | `?organization_id=`                                  |
| `POST`  | `/api/admin/invoices`                         | 开具发票          | FormData: `order_ids[]`（<span style="color:#2563eb">ready_for_invoice</span>）+ PDF |
| `POST`  | `/api/admin/invoices/<INV-ref>/mark-paid`     | <span style="color:#2563eb">标记已付并 complete 关联 Orders</span> | `{confirmed: true}` |


### 3.2 Organization Owner 端点（Bearer Gateway Token）


| 方法       | 路径                                     | 说明                        | Body / 参数                                                       |
| -------- | -------------------------------------- | ------------------------- | --------------------------------------------------------------- |
| `GET`    | `/api/organization`                    | 获取组织信息（含成员、邀请）            | —                                                               |
| `POST`   | `/api/organization/invitations`        | 创建邀请                      | `{email}` → 返回 `invitation_token`                               |
| `DELETE` | `/api/organization/invitations/<id>`   | 撤销邀请                      | `{confirmed: true}`                                             |
| `POST`   | `/api/organization/invitations/accept` | 接受邀请                      | `{token}`                                                       |
| `DELETE` | `/api/organization/members/<user_id>`  | 移除成员                      | `{confirmed: true}`                                             |
| `GET`    | `/api/orders`                          | 列出订单（含 allowed_actions）   | `?status=`                                                      |
| `GET`    | `/api/orders/<ORD-ref>`                | 订单详情                      | —                                                               |
| `POST`   | `/api/orders`                          | 创建订单                      | `{tasks[{task_id,name,hours,is_custom}], due_date, …, as_draft?}` |
| `PATCH`  | `/api/orders/<ORD-ref>`                | 编辑订单                      | 同上                                                              |
| `POST`   | `/api/orders/<ORD-ref>/submit`         | 提交 draft                  | `{}`                                                            |
| `POST`   | `/api/orders/<ORD-ref>/approve`        | 接受 Admin 定价               | `{}`                                                            |
| <span style="color:#2563eb">`POST`</span> | <span style="color:#2563eb">`/api/orders/<ORD-ref>/approve-delivery`</span> | <span style="color:#2563eb">验收交付 → ready_for_invoice</span> | <span style="color:#2563eb">`{confirmed: true}`</span> |
| <span style="color:#2563eb">`POST`</span> | <span style="color:#2563eb">`/api/orders/<ORD-ref>/reported-episodes`</span> | <span style="color:#2563eb">上报坏 episode</span> | <span style="color:#2563eb">`{confirmed:true, episodes:[{episode_id, reason?}]}`</span> |
| `POST`   | `/api/orders/<ORD-ref>/cancel`         | 取消订单                      | `{confirmed: true}`                                             |
| `GET`    | `/api/invoices`                        | 列出发票                      | —                                                               |
| `GET`    | `/api/invoices/<INV-ref>/download`     | 发票 PDF 下载链接               | —                                                               |
| `GET`    | `/api/orders/data-sources`             | <span style="color:#2563eb">delivering / ready_for_invoice / complete</span> 订单作为 My Data 数据源 | — |


### 3.3 响应结构示例

`GET /api/orders/<ref>` 返回 `allowed_actions` 驱动前端按钮显示：

```json
{
  "id": "ORD-1044",
  "status": "delivering",
  "hourly_rate": 25.0,
  "rate_pending": false,
  "total_hours": 48.0,
  "delivered_hours": 50.2,
  "reported_bad_hours": 2.1,
  "accepted_hours": 48.1,
  "remaining_hours": 0,
  "delivery_ready": true,
  "total_value_usd_cents": 120000,
  "tasks": [{
    "id": 1,
    "task_id": 17,
    "name": "Cable insertion",
    "hours": 40.0,
    "is_custom": false,
    "delivered_hours": 42.0,
    "reported_bad_hours": 1.5,
    "accepted_hours": 40.5,
    "delivery_ready": true
  }],
  "history": [{"id": 1, "type": "delivery_started", "actor_type": "admin", "...": "..."}],
  "invoice": null,
  "allowed_actions": ["approve_delivery"]
}
```

<span style="color:#2563eb">

`POST …/reported-episodes` 成功响应要点：

```json
{
  "reported_count": 3,
  "reported_duration_seconds": 7200,
  "not_in_order_episode_ids": [999],
  "already_reported_episode_ids": [101],
  "order": { "...": "更新后的 order（含 progress）" }
}
```

</span>

---

## 4. 数据库 Schema

> SQL 均标注**手动执行**，Cloud Build 不自动运行。

```sql
data_organizations          -- id（BIGSERIAL）, name, email_domain, created_at
data_organization_members   -- PK(org_id, user_id)；user_id UNIQUE（一人只能属于一个组织）
                            -- role CHECK('owner','member')
data_organization_invitations -- token_hash UNIQUE, expires_at
                              -- UNIQUE(org_id, lower(email))
data_orders                 -- id 序列从 1044 起始
                            -- status CHECK(含 ready_for_invoice), hourly_rate_usd_cents
                            -- due_date DATE, spec_link, notes
data_order_items            -- name TEXT, requested_hours NUMERIC(10,2)>0, is_custom BOOLEAN
                            -- task_id BIGINT NULL → data_tasks（20260831）
data_order_history          -- event_type, actor_type, actor_id, details JSONB
data_invoices               -- id 序列从 2208 起始
                            -- order_ids BIGINT[], status CHECK('issued','paid')
                            -- file_object_key（GCS）, amount_usd_cents
data_jobs.order_id          -- BIGINT NULL → data_orders（20260901）
data_order_reported_episodes -- PK(order_id, episode_id)；reason；duration_seconds（20260902）
```

<span style="color:#2563eb">


</span>

---

## 5. 测试分析

### 5.1 测试空白（高风险）


| 模块                                | 缺失内容                                  | 风险  |
| --------------------------------- | ------------------------------------- | --- |
| `domain.py admin_edit_result`     | rate 变/不变时状态分叉                        | 高   |
| `domain.py owner_edit_result`     | pending_approval → submitted 强制退回     | 高   |
| `repository.py accept_invitation` | token 过期、已接受的 token、跨组织               | 高   |
| `routes.py owner_approve`         | admin 未设 rate 时 409；非 owner member 操作 | 高   |
| Invoice PDF                       | 非 PDF 签名、>25MB                        | 高   |
| <span style="color:#2563eb">E2E：delivering → approve-delivery → invoice → mark-paid</span> | <span style="color:#2563eb">全链路人工/自动化尚未覆盖</span> | <span style="color:#2563eb">高</span> |
| <span style="color:#2563eb">Bad report 边界</span> | <span style="color:#2563eb">上报后 blocking approve；非 delivering 拒绝；成员非 owner</span> | <span style="color:#2563eb">高</span> |
| <span style="color:#2563eb">My Data ORD @ delivering</span> | <span style="color:#2563eb">过早可见 / 移除成员立即失效 / 与 self 去重</span> | <span style="color:#2563eb">高</span> |
| `OrderWorkspace.tsx`              | invitationToken 自动 accept 流程          |     |
| `repository.py _user_by_email`    | email 大小写；三字段 fallback 顺序             | 中   |
| `OrderSourceFilter.tsx`           | 全选/取消全选；无 ORD 源时隐藏                    | 中   |

### 5.2 建议测试矩阵（快速索引）

| 场景 | 角色 | 检查点 |
|---|---|---|
| Order 状态机 | Admin + Organization Owner | `draft→submitted→approve→production→delivering→approve delivery→ready_for_invoice→issue invoice→mark paid→complete` |
| 交付进度 | Organization Owner / Orders | 各 task `delivered / accepted / reported_bad / remaining`；未达标时 Approve delivery disabled |
| Bad data report | Organization Owner + `delivering` | 文本与 CSV；确认弹窗；返回 `reported / not_in_order / already_reported` |
| My Data sources | Org member | `self` + `ORD-*`；`delivering` 即可见；移除成员后立即失效 |
| Download 命名 | My Data / SDK | 文件落盘为 `{episode_id}.mcap` 与 `{episode_id}/video.mp4` |
| Admin Job×Order | Admin Jobs | 只能选 Order catalog tasks；非法 `task_id` → 400 |
| Admin Invoice | Admin Invoices | 仅 `ready_for_invoice` 可开票；Mark paid 同步 complete 关联 Orders |
| Migration 兼容 | Backend | 未建 reported 表时 list/detail 不 500；上报 API 在 migration 前应失败 |

---

## 6. E2E 测试用例（按页面组织）

### 6.1 页面覆盖索引

| 页面 / 入口 | 主要覆盖 | 用例 |
| --- | --- | --- |
| Organization Owner — Orders | 入口、订单创建/编辑/提交/批价/取消、交付验收、坏数据、发票下载 | TC-URL-01、TC-AUTH-02、TC-ORD-01～05、TC-ORD-08、TC-ORD-10、TC-DEL-01～02、TC-BAD-01～02、TC-INV-03 |
| Organization Owner — Team | 邀请、接受邀请、移除成员 | TC-ORG-04～06 |
| My Data | Order 数据源过滤、共享数据权限、下载命名 | TC-SRC-01～03、TC-DL-01 |
| Admin Portal — Orders | Admin 认证、审批、开始交付、取消、catalog 容错 | TC-AUTH-01、TC-ORD-06～07、TC-ORD-09、TC-ORD-11、TC-ADM-01 |
| Admin Portal — Jobs | Job 与 Order task 绑定 | TC-JOB-01 |
| Admin Portal — Invoices | 开票、付款、PDF 校验 | TC-INV-01～02、TC-ERR-03 |
| Admin Portal — Organizations | 创建组织、查看成员、添加 Owner | TC-ORG-01～03 |
| Orders 通用表单 / API | Owner 与 Admin 共用字段校验 | TC-ERR-01～02、TC-ERR-04 |

### 6.2 Organization Owner — Orders 页面

入口：`/robotic-data?view=orders`

#### 6.2.1 页面入口与订单生命周期

| TC ID | 功能 | 角色 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **TC-URL-01** | URL 路由 | Organization Owner | 已登录 | 直接访问 `/robotic-data?view=orders` | 直接进入 Orders Tab | `?view=invalid` → 默认进入 browse Tab | |
| **TC-AUTH-02** | Organization Owner 认证 | Organization Owner | — | 调用 `/api/orders` | 正常返回 | 无组织 → `organization_required`，前端显示“联系 PrismaX” | |
| **TC-ORD-01** | 创建订单 | Organization Owner | 已属于某 Organization（Organization Owner 角色） | `+ New order` → 填 task + due_date，不填 rate → Submit | 状态 `submitted`；allowed_actions = [edit, cancel] | task hours=0 → 表单报错；member（非 owner）看不到 `+ New order` | |
| **TC-ORD-02** | 保存草稿 | Organization Owner | — | 创建订单时点击 “Save as draft” | 状态 `draft`；allowed_actions 含 submit | — | |
| **TC-ORD-03** | 提交草稿 | Organization Owner | status = draft | 订单详情 → Submit order | 状态 `submitted` | — | |
| **TC-ORD-04** | Organization Owner 编辑 | Organization Owner | status = submitted | 编辑任务 → Save | 状态仍 `submitted`；history 新增 `order_updated` | status = cancelled → 无 Edit 按钮 | |
| **TC-ORD-05** | Organization Owner 编辑作废报价 | Organization Owner | status = pending_approval | 编辑任意字段 → Save | 状态退回 `submitted`；Approve 按钮消失；pending_approval 提示消失 | — | |
| **TC-ORD-08** | Organization Owner 批价 | Organization Owner | status = pending_approval，admin 已设 rate | 点击 `Approve $X/hr` | 状态 `production`；rate_pending = false | admin 未设 rate → 409（前端此时不显示 Approve 按钮） | |
| **TC-ORD-10** | Organization Owner Cancel | Organization Owner | status = draft / submitted / pending_approval | Cancel → 确认 | 状态 `cancelled` | production 及以后 → Cancel 按钮不显示 | |

#### 6.2.2 交付进度、坏数据与验收

| TC ID | 功能 | 角色 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| <span style="color:#2563eb">**TC-DEL-01**</span> | <span style="color:#2563eb">交付进度展示</span> | <span style="color:#2563eb">Organization Owner</span> | <span style="color:#2563eb">delivering；Job 已上传部分 episode</span> | <span style="color:#2563eb">打开订单详情</span> | <span style="color:#2563eb">显示 delivered / requested；task breakdown；未达标时 Approve delivery disabled/tooltip</span> | <span style="color:#2563eb">custom task（task_id null）不贡献 ready</span> | |
| <span style="color:#2563eb">**TC-BAD-01**</span> | <span style="color:#2563eb">上报坏 episode（文本）</span> | <span style="color:#2563eb">Organization Owner</span> | <span style="color:#2563eb">delivering</span> | <span style="color:#2563eb">Report bad data → 输入 `episode_id;reason` → 确认</span> | <span style="color:#2563eb">reported_count↑；accepted hours 下降；可能失去 delivery_ready</span> | <span style="color:#2563eb">非法行提示；空列表拒绝；>5000 拒绝</span> | |
| <span style="color:#2563eb">**TC-BAD-02**</span> | <span style="color:#2563eb">上报坏 episode（CSV）</span> | <span style="color:#2563eb">Organization Owner</span> | <span style="color:#2563eb">delivering</span> | <span style="color:#2563eb">上传 CSV → 确认</span> | <span style="color:#2563eb">同 TC-BAD-01；返回 not_in_order / already_reported 计数</span> | <span style="color:#2563eb">非 delivering → API 拒绝；不可撤销</span> | |
| <span style="color:#2563eb">**TC-DEL-02**</span> | <span style="color:#2563eb">Approve Delivery</span> | <span style="color:#2563eb">Organization Owner</span> | <span style="color:#2563eb">delivering + delivery_ready</span> | <span style="color:#2563eb">Approve delivery → 确认</span> | <span style="color:#2563eb">状态 `ready_for_invoice`；history `delivery_approved`</span> | <span style="color:#2563eb">未 ready → 按钮不可用；缺 confirmed → 409；member 无按钮</span> | |

#### 6.2.3 发票查看与下载

| TC ID | 功能 | 角色 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **TC-INV-03** | Organization Owner 下载发票 | Organization Owner | 发票已开具 | 订单详情 → PDF ↓ | 获取 signed URL，新标签打开 | 下载其他 org 发票 → 404 | |

### 6.3 Organization Owner — Team 页面

入口：`/robotic-data?view=orders` → Team

| TC ID | 功能 | 角色 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **TC-ORG-04** | 邀请成员 | Organization Owner | 已属于组织（Organization Owner） | Team → 输入 email → Create invitation | 返回 `invitation_token`，链接含 `?invite=TOKEN` | 同组织同 email 重复 → 409；**非 org email_domain → 拒绝** | |
| **TC-ORG-05** | 接受邀请 | 任意已登录用户 | 收到 `?invite=TOKEN` 链接；用户尚无组织 | 打开 `/robotic-data?view=orders&invite=TOKEN` → 点击 **Accept invitation** | 调用 acceptInvitation；成功后 URL 清除 invite；用户加入组织可见订单 | token 过期（>7天）→ 报错；登录 email ≠ 邀请 email → 403 | |
| **TC-ORG-06** | 移除成员 | Organization Owner | 组织内有 member | Team → Remove → 确认 | 成员移除；<span style="color:#2563eb">被移除者立即失去 ORD My Data</span> | 移除自己（owner）→ 后端应拒绝 | |

### 6.4 My Data 页面

| TC ID | 功能 | 角色 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **TC-SRC-01** | My Data 数据源过滤 | Organization Owner | <span style="color:#2563eb">≥1 个 delivering/ready/complete 订单</span> | My Data → OrderSourceFilter → 选择某订单 | 仅显示该订单的 episodes；`source_ids` 正确传入 | <span style="color:#2563eb">无 ORD 源 → Filter 不渲染</span> | |
| **TC-SRC-02** | My Data 数据源全选 | Organization Owner | 多个订单 + self-serve episodes | 全选所有数据源 | 等价于无过滤，所有 episodes 显示 | 仅选 “Self-serve” → 仅显示无 order 共享的 episodes | |
| <span style="color:#2563eb">**TC-SRC-03**</span> | <span style="color:#2563eb">delivering 即可见</span> | <span style="color:#2563eb">Org member</span> | <span style="color:#2563eb">Order=delivering + Job 有 episode</span> | <span style="color:#2563eb">My Data 选 ORD-*</span> | <span style="color:#2563eb">可见共享 episodes；可下载（access_context=my_data）</span> | <span style="color:#2563eb">非成员 404/空</span> | |
| <span style="color:#2563eb">**TC-DL-01**</span> | <span style="color:#2563eb">下载命名 episode_id</span> | <span style="color:#2563eb">Organization Owner</span> | <span style="color:#2563eb">My Data 可选 episode</span> | <span style="color:#2563eb">下载一包</span> | <span style="color:#2563eb">文件为 `{episode_id}.mcap`、`{episode_id}/…` 或 `{id}_video.mp4`，非 uploader key</span> | <span style="color:#2563eb">SDK CLI 同路径约定</span> | |

### 6.5 Admin Portal — Orders 页面

#### 6.5.1 页面访问与容错

| TC ID | 功能 | 角色 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **TC-AUTH-01** | Admin 认证 | Admin | — | 调用任意 `/api/admin/`* | 正常返回 | 过期/无效 → 401；role ≠ admin → 403；前端触发 `ADMIN_SESSION_EXPIRED_EVENT` | |
| <span style="color:#2563eb">**TC-ADM-01**</span> | <span style="color:#2563eb">Admin catalog 容错</span> | <span style="color:#2563eb">Admin</span> | <span style="color:#2563eb">task-scenarios API 失败</span> | <span style="color:#2563eb">打开 Orders Dashboard</span> | <span style="color:#2563eb">Orders 仍加载；提示 scenarios unavailable；Create order 仍可用</span> | — | |

#### 6.5.2 审批与状态流转

| TC ID | 功能 | 角色 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **TC-ORD-06** | Admin Approve（rate 一致） | Admin | status = submitted，已有 rate | Orders Tab → Approve → 填入**相同** rate | 状态 `production` | — | |
| **TC-ORD-07** | Admin Approve（rate 变更） | Admin | status = submitted | Approve → 填入**不同** rate | 状态 `pending_approval`；Organization Owner 端出现“PrismaX confirmed a rate of $X/hr”提示 | — | |
| **TC-ORD-09** | Admin Mark Delivering | Admin | status = production | mark-delivering | 状态 `delivering` | 非 production → 409 invalid_transition | |
| **TC-ORD-11** | Admin Cancel | Admin | status = submitted | Cancel + confirmed:true | 状态 `cancelled` | status = production → 409 | |

### 6.6 Admin Portal — Jobs 页面

| TC ID | 功能 | 角色 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| <span style="color:#2563eb">**TC-JOB-01**</span> | <span style="color:#2563eb">Job 绑定 Order tasks</span> | <span style="color:#2563eb">Admin</span> | <span style="color:#2563eb">Order 有 catalog task_ids</span> | <span style="color:#2563eb">创建 Job 带 order_id + 合法/非法 task</span> | <span style="color:#2563eb">合法成功；非法 task_id → 400</span> | <span style="color:#2563eb">更新时省略 order_id 保留链接；显式 null unlink</span> | |

### 6.7 Admin Portal — Invoices 页面

| TC ID | 功能 | 角色 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **TC-INV-01** | Admin 开票 | Admin | <span style="color:#2563eb">≥1 个 ready_for_invoice 且无发票的订单</span> | Invoices Tab → 勾选订单（同 org）→ 上传 PDF → issue | 新发票行 `INV-XXXX`，status = `issued` | 跨 org 订单 → UI 过滤；非 PDF → 400；>25MB → 413；<span style="color:#2563eb">complete 订单不应出现在开票 picker</span> | |
| **TC-INV-02** | Admin Mark Paid | Admin | 发票 status = issued | <span style="color:#2563eb">Mark paid & complete → 确认（文案含 order ids）</span> | <span style="color:#2563eb">发票 `paid`；关联 Orders 全部 `complete`</span> | — | |
| **TC-ERR-03** | Invoice PDF 格式 | Admin | — | 上传非 PDF 文件 | 400（`%PDF-` 签名校验失败） | >25MB → 413 | |

### 6.8 Admin Portal — Organizations 页面

| TC ID | 功能 | 角色 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **TC-ORG-01** | Admin 创建组织 | Admin | owner email 在 users 表中存在 | Organizations Tab → name + owner_email → Create | 列表出现新组织 | email 不存在 → 404；已属于其他组织 → 409 | |
| **TC-ORG-02** | Admin 查看成员 | Admin | 组织已创建 | 点击组织行 → View members | Modal 展示 email、role、user_id、joined_at | 无成员 → “No organization members.” | |
| **TC-ORG-03** | Admin 添加 Organization Owner | Admin | 目标 email 存在且无组织 | POST owners {owner_email} | 该用户成为 Organization Owner | email 不存在 → 404；已有组织 → 409 | |

### 6.9 Orders 页面通用表单 / API 校验

适用页面：Organization Owner — Orders、Admin Portal — Orders。

| TC ID | 功能 | 角色 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **TC-ERR-01** | spec_link 格式 | Organization Owner/Admin | — | spec_link 填非 http/https URL | 400 “spec_link must be a valid http or https URL” | 空值 → 允许（转 null） | |
| **TC-ERR-02** | task hours 格式 | Organization Owner/Admin | — | task hours = 0 或负数 | 400 “task hours must be greater than zero” | — | |
| **TC-ERR-04** | Rate 格式 | Admin | — | approve 时 hourly_rate ≤ 0 | 400 “hourly_rate must be greater than zero” | — | |


---

## 7. 风险、局限与待改进

### 7.0 风险等级汇总

| Level | Topic | 影响 | 验证要点 |
|---|---|---|---|
| **P0** | Manual SQL migrations | 未执行 `20260901` / `20260902` 时，`ready_for_invoice` 约束与 bad-report 表缺失 | 部署前在 Cloud SQL 手工跑两份 SQL；`03eb170` 仅降低读路径炸库风险 |
| **P0** | Order → Complete 语义变化 | Admin 不再直接 Complete；Owner Approve delivery → `ready_for_invoice` → Invoice paid → complete | 全链路 E2E：`draft→…→delivering→approve→issue PDF→mark paid` |
| **P0** | My Data Order 源提前可见 | `1509dcd` 起 delivering 订单 episode 即可进 My Data / 下载 | 验证 ORD-* 过滤、组织成员权限、非成员不可见、与 self 去重 |
| **P0** | Bad episode 不可撤销 | 上报后立即从 accepted hours 扣除，可能阻断 approve_delivery | 测无效 ID / 已上报 / 不在订单 / 上限 5000；确认 UI 二次确认 |
| **P1** | 下载命名 breaking change | 相对路径从 uploader `episode_key` 变为 `{episode_id}.mcap` / `{episode_id}/…` | Browser、CDN package、SDK download 三端对照；旧脚本若依赖 key 需改 |
| **P1** | Job 任务必须属于 Order | 创建/更新带 `order_id` 的 Job 时校验 `task_id ⊆ order items` | 合法/非法 task；省略 `order_id` 保留链接；显式 `null` unlink |
| **P2** | Admin task catalog 依赖 | `c176c76` 曾直连 data pipeline；`7ec491a` 改 admin API 并容错 | tasks API 失败时 Dashboard 仍可用；Create order 下拉可为空 |

---

### 7.1 部署注意


| 项目                      | 说明                                                                                              |
| ----------------------- | ----------------------------------------------------------------------------------------------- |
| SQL 手动执行                | <span style="color:#2563eb">须按序执行 v1 → 20260831 → **20260901** → **20260902**</span>；Cloud Build 不自动运行 |
| <span style="color:#2563eb">Marketing / SDK 分支</span> | <span style="color:#2563eb">v2 Organization Owner UI / SDK 文档在 `origin/testing`，**未进 main**；回归环境必须对准 testing</span> |
| Admin JWT 依赖 Flask 全局配置 | `verify_jwt_in_request()` 依赖 `JWT_SECRET_KEY`，order_management Blueprint 必须注册到同一 Flask 实例       |
| Invoice PDF 孤立对象        | `upload_pdf()` 成功但 DB 写入失败时尝试清理 GCS，清理失败仅记 warning，可能留下孤立 PDF                                   |
| Next.js 代理路径            | `orderApi.ts` 的 `ORDER_API_BASE="/prismax-user"` 依赖 Next.js rewrite 正确配置，否则所有 Organization Owner 端 API 均 404 |


### 7.2 设计断层：Order Task 与 Operator Task

Order item 已通过 `task_id` 与 `data_tasks` catalog 链接，带 `order_id` 的 Job 任务亦须属于该 Order catalog items。Admin 仍需手动创建 Job 并绑定 `order_id`：

```
Order 进入 production
  → Admin 创建 Job 并设置 order_id（tasks ⊆ Order catalog）
  → Operator 按 Job 上传
  → Episode 自动计入 Order delivery progress / My Data ORD 源
```

剩余风险：

| 场景 | 风险 |
| --- | --- |
| Order 含 custom task / `task_id=NULL` | 进入 production 前 `require_catalog_task_mapping` 会拦截；若异常进入 delivering，该行使 `delivery_ready` 永不成立 |
| Job 未设 `order_id` | My Data ORD 源与交付进度均看不到对应 uploads |
| catalog `task_id` 在 production 后被删/改名 | 历史 `name` 快照仍在；Job 校验可能失败 |
| Admin Job UI | 仅自由文本 Order ID + 全量 task 下拉；**不**按 Order catalog 过滤，非法组合靠后端 400 |
| production 后无法取消、无 Admin complete 逃生口 | 若 Owner 永不 approve-delivery，订单会卡在 delivering / ready_for_invoice |



### 7.3 Production / Delivering / Ready for invoice

| | `production` | `delivering` | <span style="color:#2563eb">`ready_for_invoice`</span> |
|--|--|--|--|
| **含义** | 数据采集进行中 | 采集交付中；Organization Owner 可验货/报坏 | <span style="color:#2563eb">Organization Owner 已验收，等待 Admin 开票</span> |
| **进入方式** | Admin/Organization Owner 批价通过 | Admin `mark-delivering` | <span style="color:#2563eb">Organization Owner `approve-delivery`</span> |
| **Organization Owner 可操作** | — | <span style="color:#2563eb">Approve delivery、Report bad</span> | 查看进度 / 发票（开票后） |
| **Admin 下一步** | mark_delivering | — | <span style="color:#2563eb">Issue invoice → Mark paid → Orders complete</span> |
| **My Data ORD 源** | ❌ | <span style="color:#2563eb">✅</span> | <span style="color:#2563eb">✅</span>（`complete` 亦 ✅） |
| **可取消** | ❌ | ❌ | ❌ |


---

### 7.4 其他设计注意点

- **一用户只能属于一个组织**：`data_organization_members.user_id UNIQUE`，接受第二个邀请会触发 DB 约束报错
- **Admin 编辑 draft 不触发 pending_approval**：符合设计（draft 未提交，rate 变化无需 owner 确认）
- **OrderSourceFilter 客户端二次过滤**：前端按 `episode.order_id | orderId | source_order_id` 过滤，若字段名不一致可能导致 "Self-serve" 过滤失效
- <span style="color:#2563eb">**Bad episode 不可撤销**：误报只能靠补传更多 accepted hours 再达 `delivery_ready`；全部 miss（已上报/不在订单）仍返回 200 且 `reported_count:0`</span>
- <span style="color:#2563eb">**下载命名 breaking change**：依赖 uploader `episode_key` 的外部脚本需改用 `episode_id`；回归须用 Marketing / SDK 的 `origin/testing`，当前 `main` 仍是旧命名</span>
- <span style="color:#2563eb">**缺 migration 时**：status check / reported 表缺失会导致写路径失败；读进度有 `TO_REGCLASS` 降级但不能上报</span>
- <span style="color:#2563eb">**`allowed_actions` 不含 report-bad**：Owner 端报坏按钮由前端在 `delivering` 硬编码，Member 无按钮</span>
- **邀请域名锁定**：仅同 `email_domain` 可被邀请；接受时登录 email 必须匹配邀请 email
