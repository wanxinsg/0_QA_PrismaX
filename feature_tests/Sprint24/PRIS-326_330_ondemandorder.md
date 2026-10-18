# PRIS-326 + PRIS-330：On-Demand Data Order、Job Assignment 与交付闭环

> 整合日期：2026-09-15｜来源：`PRIS-326` Upload Jobs + `PRIS-330` On-Demand Data + `PRIS-351` Admin All Jobs  
> 冲突时以较新业务规则为准；旧规则仅作负向回归。  
> 用例标记：`326/TC-*`、`330/TC-*`、`lanmanc/*`、`aparna/*`。  
> <span style="color:#2563eb">蓝色文字 = 2026-09-16 新增 / 变更（Jobs 上传 FE+BE+SDK 强耦合；Admin 移除 Organization 成员 FE+BE 成对）。</span>

**变更摘要**

| 日期 | 主题 | 详见 |
| --- | --- | --- |
| 09-04 | My Data 下载与 personal membership 解耦 | §4.3、E2E-MYD-05～09、附录 A |
| 09-04～06 | Additional Episodes、Job↔Order、Admin Episode Browser、Admin 可 Re-Approve | §3.4～3.5、§5.4～5.5、附录 B |
| 09-08 | Assign Episodes 选择/详情/批量 | §5.5、E2E-ADM-RD-02～10、附录 C |
| 09-09 | Order 绑定 Robot、custom task link、进度条、My Data RobotFilter | §5.1/5.3/5.4 |
| 09-10 | 坏数据可见性、Task 全选拉全量、上报格式、Team 邀请、Job Order 必填/支付/SDK 校验 | §5.1/5.4/5.6、附录 D |
| 09-11 | Customer accept/reject、hours_payable、Review timeline、工时 3 位、Operator 返回 robot、Admin 订单列表层级 | §3.2/3.3、§5.4/5.6/5.7、E2E-ADM-JOB-19～21、OP-UP-07～09、FLOW-08 |
| 09-10～12 | Customer accepted 时间补齐与 key 统一、Delivering Order 可建/关联 Job、Admin 全量 Jobs、Owner email 自动建档、MCAP 阈值更新 | §2、§3.2/3.5、§4.1、§5.6/5.9/5.10、§6.1、§7、E2E-ADM-JOB-22～25、E2E-ADM-ORG-01/04、E2E-MCAP-01～04 |
| 09-15 | 内部 PrismaX Owner 多 Organization、Invoice 年份编号、Order/Job 身份展示、Episode 按 JOB 搜索与分批指派、Job SDK 上传提示 | §1～3、§4.3～4.4、§5.1～5.5/5.7～5.9、§6～7、E2E-OWN-ORD-15、MYD-12、ADM-ORD-22、ADM-RD-12～13、OP-UP-10～11、ADM-INV-05、ADM-ORG-05～06、FLOW-09 |
| <span style="color:#2563eb">09-16</span> | <span style="color:#2563eb">Jobs 上传闭环：隐藏 task 可挂 Job、available-orders 补 `customer_name`、Order 下拉展示客户/主 task、SDK 在 `job_id` 作用域解析 task；Admin 可移除 Organization 成员（禁止删最后一位 owner）</span> | <span style="color:#2563eb">§1.1～1.2、§2、§3.5、§4.1/4.4、§5.6/5.7/5.9/5.10、§6.1～6.2、§7、E2E-ADM-JOB-26、OP-UP-10～11、SDK-UP-06、ADM-ORG-07、FLOW-10</span> |

---

## 1. Feature 完整描述

该 Feature 是一条从企业客户提出数据需求，到 PrismaX 分配采集任务、Operator 上传数据、客户验收交付、Admin 开票收款的完整 On-Demand Data 业务链路。

它由两个前后衔接的部分组成：

1. **Order Management（需求与交付管理）**：Organization Owner 创建订单并定义所需 task、工时和交付日期；Admin 审批客户报价并推进订单；客户在交付阶段查看进度、上报坏数据并验收；Admin 最终开票并收款。
2. **Upload Jobs（生产执行管理）**：Admin 将 Order 中的 catalog tasks 分配给 Operator，形成带工时、工资率和截止日期的 Job；Operator 查询 Job 并通过 SDK 将上传绑定到 Job；处理后的 Episode 累计 Job 工时，同时汇总到 Order 的交付进度。

这两个模块通过以下主链路连接：

```text
Organization
  → Order
    → Order Item (task_id + requested_hours)
      → Job (order_id + tasks_data)
        → Upload (job_id + task_id)
          → Episode (duration + processing/QC status)
            ├─ Job progress + Operator payment
            └─ Order delivery progress - reported bad episodes
              → Owner approve delivery
                → Invoice
                  → Mark paid
                    → Order complete
```

### 1.1 Feature 目标

- Owner 按 task/工时下单；Admin 管 Org、定价、生产与开票。
- PrismaX 内部 Owner 可隐藏地管理多个客户 Organization，并在 Orders 页面切换当前 Organization；普通客户成员仍保持单 Organization 约束。
- Job 仅能分配 Order catalog tasks；SDK 传 `job_id` 同时计入 Job 与 Order。
- <span style="color:#2563eb">Job 可包含对 Web/公开 catalog **不可见** 的隐藏 task；隐藏 task 只存在于 Job 作用域，须用 SDK 带 `job_id` 上传（FE 横幅引导 + BE 放开 Job task catalog + SDK 按 Job 解析 task，三端强耦合）。</span>
- Operator 可见 Job 进度/阶段；Owner 可见 delivered / reported / accepted / remaining。
- Admin 可在 VLA Operators 下跨 Operator 分页查看、精确搜索并维护全部未删除 Jobs。
- <span style="color:#2563eb">Admin 可在 Organizations 详情中移除客户 Owner/Member（FE+BE 成对）；最后一个 Owner 不可移除。</span>
- 验收 → `ready_for_invoice` → 开票 Mark paid → `complete`。
- My Data：≥`delivering` 可看 ORD；ORD 下载靠公司成员身份，Self-serve 仍要 personal membership。

### 1.2 不在自动闭环内的部分

- Order 进入 `production` 后不会自动创建 Job。
- Web 上传不传 `job_id`；计入 Job/Order 须用 SDK/CLI 显式传 `job_id`。
- Job Task 链接虽然会打开 Web 上传页，但仅用于定位 Task 并展示 SDK 提示；不能把 Web Upload 误认为已绑定当前 Job。
- <span style="color:#2563eb">隐藏/不可见 task 在 Web Upload catalog 中可能找不到（横幅 `not_found`）；即使打开 Modal，Web 上传仍不绑定 Job。</span>
- Order 客户报价与 Job 工资率、Order due date 与 Job due date 均不自动同步。
- Job 工时完成不自动推进 Order；仍需 Admin Mark Delivering + Owner Approve Delivery。

---

## 2. 角色与权限

| 角色 | 主要职责 | 主要页面 / 接口 |
| --- | --- | --- |
| Organization Owner | 管理订单、接受报价、查看交付、上报坏 Episode、验收、下载发票、管理 Team | Robotic Data Orders、Team、My Data |
| Internal PrismaX Owner | 以 `@prismax.ai` 身份拥有一个或多个 Organization 的 Owner 权限；对客户 Manage access/成员列表隐藏 | Robotic Data Orders（Organization switcher）、My Data、Admin 配置接口 |
| Organization Member | 查看组织订单和共享数据；不能创建/编辑订单、上报坏数据或验收 | Robotic Data Orders、My Data |
| Admin | 管理 Organization、Order、Job、Operator payment、Invoice 和状态推进；<span style="color:#2563eb">可移除 Organization 客户成员</span> | Admin Portal |
| Operator | 查看分配的 Job，选择正确 task 并上传采集数据 | Upload Dashboard、SDK/CLI |

关键权限原则：

- 一个用户只能属于一个 Organization。
- 上一条只约束 `data_organization_members` 中的客户身份；`data_organization_internal_owners` 允许同一 PrismaX 内部用户关联多个 Organization。
- Admin 创建 Organization 时，首个 Owner email 无现存 `users.email` 记录也可继续：后端先创建 email-only 用户记录再建立 Owner membership；这不代表用户已完成登录凭证注册。
- <span style="color:#2563eb">Admin 可 `DELETE /api/admin/organizations/&lt;id&gt;/members/&lt;user_id&gt;` 移除客户 Owner/Member，收回 Orders / My Data 访问；若目标是最后一位 `role=owner` → 409 `last_owner_required`（前端 Disable Remove + 二次确认）。此能力与 Internal Owner 移除接口独立。</span>
- Organization Owner 才能执行订单写操作、Team 管理、Report Bad 和 Approve Delivery。
- Admin Job 接口要求 Admin JWT；Operator Job 页面要求 gateway token；SDK Job/Upload 接口要求 `pxu_` Upload API Key。
- `pxa_` Download API Key 不能调用 Job 查询或上传接口。

---

## 3. 核心实体与数据关系

| 实体 | 关键字段 | 作用 |
| --- | --- | --- |
| `data_organizations` | `id`, `name`, `email_domain` | 企业客户主体 |
| `data_organization_members` | `org_id`, `user_id`, `role` | Owner/Member 关系；`user_id` 唯一 |
| `data_organization_internal_owners` | `organization_id`, `user_id`, `granted_by_admin_id`, `created_at` | 隐藏的 PrismaX 内部 Owner 关系；联合主键允许同一内部用户管理多个 Organization |
| `data_orders` | `status`, `hourly_rate_usd_cents`, `due_date`, `robot_type_id` | 客户订单；`robot_type_id` → `data_sample_machines`（migration `20260908_data_orders_robot_type_id.sql`） |
| `data_order_items` | `task_id`, `name`, `requested_hours`, `is_custom` | Order 的需求明细；catalog 行关联 `data_tasks` |
| `data_jobs` | `assigned_user_id`, `tasks_data`, `rate_usd_per_hour`, `due_date`, `order_id` | Admin 分配给 Operator 的生产 Job |
| `data_uploads` | `task_id`, `job_id`, `status` | 上传批次；`job_id` 是 Job 统计入口 |
| `data_episodes` | `task_id`, `video_duration_hours`, `status`, `qa_score` | 数据处理结果和工时来源 |
| `data_job_payments` | `total_hours`, `total_amount_usd`, `included_episode_ids`, `voided_at` | Operator 付款账本 |
| `data_order_reported_episodes` | `order_id`, `episode_id`, `reason`, `duration_seconds` | 客户永久上报的坏数据 |
| `data_invoices` | `order_ids`, `status`, `file_object_key`, `amount_usd_cents` | 客户发票，可合并同组织多个 Order；公开编号为 `INV-&lt;issued_year&gt;-&lt;numeric_id 至少 4 位&gt;`，例如 `INV-2026-0012` |
| `data_order_additional_episodes` | `order_id`, `episode_id`, `added_by_admin_id`, `added_at` | Admin 手动追加 Episode（主键 `(order_id, episode_id)`），不经 Job→Upload |

### 3.1 Order 状态机

```text
draft ── Owner Submit ──► submitted
                            │
                   Admin Approve
                    ├─ rate 不变 ──► production
                    └─ rate 变化 ──► pending_approval
                                        │
                          ┌─────────────┴─────────────────┐
                 Owner Approve Rate        Admin Re-Approve
                          └─────────────┬─────────────────┘
                                        ▼
                                   production
                                        │
                              Admin Mark Delivering
                                        ▼
                                   delivering
                    ┌───────────────────┴───────────────────┐
                    │ Owner Report Bad（可多次、不可撤销）    │
                    │ Owner Approve Delivery（需 ready）      │
                    └───────────────────┬───────────────────┘
                                        ▼
                               ready_for_invoice
                                        │
                              Admin Issue Invoice PDF
                                        │
                             Admin Mark Paid + Confirm
                                        ▼
                                    complete

draft / submitted / pending_approval ── Cancel ──► cancelled
```

补充：`pending_approval` 时 Admin 也可 Approve → `production`（不限 Owner）。

负向回归（旧路径已废）：

- `delivering` 旧 `/complete` → 404；开票对象须为未开票的 `ready_for_invoice`。
- Issue Invoice 不改 Order 状态；Mark Paid 才将关联 Orders → `complete`。
- My Data 数据源含 `delivering` / `ready_for_invoice` / `complete`（不限 complete）。

### 3.2 Job 与 Episode 阶段

互斥快照（按优先级，非累计漏斗）：

| 优先级 | 阶段 | 判定 |
| ---: | --- | --- |
| 1 | Customer rejected | 在关联 Order 的 `data_order_reported_episodes` 中（与 order 审批状态无关） |
| 2 | Customer accepted | `DERIVED_READY` 且 Order ∈ `{ready_for_invoice, complete}`；生产/交付中的 ready 回落 QC/Initial；API/timeline key 统一为 `customer_accepted`（不再使用 `customer`） |
| 3 | Initial rejected | `DERIVED_VALIDATION_FAILED` / `FAILED`（原「Rejected」文案） |
| 4 | QC accepted | 未落入以上，且 `qa_score ≥ 50` |
| 5 | Initial accepted | `DERIVED_READY` / `DERIVED_PARTIALLY_READY` |
| — | 不计入 | 仍在处理中 |

**Review timeline**：Drawer 展开下发 `timeline[]`（`key`/`label`/`at`/`reached`）。
- Initial rejected：单步，`at≈created_at`
- 其他：Initial → QC → Customer accepted **或** Customer rejected
- QC 的 `at` ≈ 同 Upload 末轮 QA session 最大时间；Customer accepted 的 `at` 取关联 Order 最新一条 `delivery_approved` history 的 `created_at`（`MAX(created_at)`），属于 Order 级时间并由该 Order 的 accepted Episodes 共享；Customer rejected 的 `at`/`reported_reason` 来自 reported 表
### 3.3 两套财务数据

| 财务对象 | 面向 | 计算依据 | 状态 / 行为 |
| --- | --- | --- | --- |
| Job Payment | Operator | `hours_logged`=非失败时长（含 customer-rejected）；`hours_payable`=再排除 reported。未付 outstanding=`min(hours_payable, hours_assigned)×rate`；工时 `round_hours`(3dp)，金额 `round2`。每 Job 仅 1 条活跃支付 | Mark paid / Void |
| Order Invoice | Organization | `Σ(requested_hours × customer order rate)`，不按 accepted hours 计价 | `issued → paid`；paid 时 Orders → complete |

两者不自动对账，Order rate 与 Job rate 可以不同。

### 3.4 Admin Additional Episodes

Admin 可绕过 Job→Upload，向 Order 追加/移除 Episode（表 `data_order_additional_episodes`）。

- 单次最多 500 个正整数 `episode_ids`（自动去重）；移除须 `confirmed: true`。
- History：`additional_episodes_added` / `additional_episode_removed`；**对 Owner/Member 隐藏**。
- Migration：`20260904_data_order_additional_episodes.sql`（含 episode / uploads 相关索引）。

### 3.5 Job ↔ Order Link/Unlink

Admin 变更 Job 的 `order_id`：

可选 Order 的唯一来源改为 `GET /data/admin/jobs/available-orders`，统一返回 `production` 与 `delivering`；旧的 `/data/admin/orders?status=production` 不再作为 Job 表单数据源。
<span style="color:#2563eb">09-16：该接口补充 `customer_name`（来自 `data_organizations.name`）；Job task catalog（`_jobs_get_task_catalog`）不再按 `is_visible_*` 过滤，隐藏 task 也可挂到 Job。前端 Order 下拉据此展示 `ORD-* · robot · 客户名 - 主 task - 小时`。</span>

| 条件 | 行为 |
| --- | --- |
| Job 当前 order_id == 目标 order_id | 无操作，直接返回 |
| Job 同时有 current 和 next order_id（跨 Order 直移） | 拒绝：必须先 unlink 再 link |
| 目标 Order 状态不在 `production` / `delivering` | 拒绝：仅允许生产/交付阶段操作 |
| Job 已有 delivered Episode 且未携带 `confirmed=true` | 拒绝并返回当前 Episode 数量，提示需确认 |
| 所有校验通过 | 写入 `data_order_history` 审计记录（当前事件名为 `job_attached` / `job_detached`），更新 `data_jobs.order_id` |

---

## 4. 端到端数据流

### 4.1 主业务流

```text
1. Organization Owner 创建并提交 Order
   POST /api/orders
   POST /api/orders/<ORD-ref>/submit
        │
        ▼
2. Admin 审批客户 rate
   POST /api/admin/orders/<ORD-ref>/approve
   rate 不变 → production
   rate 变化 → pending_approval → Owner approve → production
        │
        ▼
3. Admin 创建关联 Order 的 Job
   POST /data/admin/jobs
   body: operator + order_id + tasks + operator rate + due_date
   校验：Job tasks ⊆ Order catalog task_ids
   Order status ∈ {production, delivering}
        │
        ▼
4. Operator 查询 Job 并选择 task
   页面：GET /data/jobs
   SDK：GET /v1/data/jobs
        │
        ▼
5. Operator 用 SDK 上传并显式传 job_id
   POST /v1/data/upload-sessions
   校验：Job 属于当前 Operator，task_id 属于该 Job
   <span style="color:#2563eb">SDK 有 job_id 时：按 GET /v1/data/jobs 内该 Job 的 tasks 解析 scenario/task_name（含隐藏 task）；无 job_id 时仍走公开 /data/tasks</span>
   写入 data_uploads.job_id
        │
        ▼
6. Worker 生成 / 更新 Episodes
   status + duration + qa_score
        │
        ├─► Job Dashboard：hours_logged、stage_counts、payment
        │
        └─► Order Delivery：按 order_id → job → upload → episode 聚合
             delivered - reported_bad = accepted
        │
        ▼
7. Admin Mark Delivering
   production → delivering
        │
        ├─► Org 成员可在 My Data 选择 ORD-* 并下载
        ├─► Owner 可 Report Bad；accepted hours 立即下降
        └─► 每个 task accepted ≥ requested 时 delivery_ready=true
        │
        ▼
8. Owner Approve Delivery
   delivering → ready_for_invoice
        │
        ▼
9. Admin Issue Invoice；随后 Mark Paid
   Invoice issued → paid
   关联 Orders → complete
```

### 4.2 Job 工时与 Order 交付进度

```text
data_orders.id
  ← data_jobs.order_id
      ← data_uploads.job_id
          ← data_episodes.upload_id

Job hours_logged
  = 非失败 Episode 时长
Job hours_payable = hours_logged − reported episodes（仅此项参与 Mark Paid）
Order task delivered_seconds
  = 同 Order、同 task_id 下所有 Job/Upload/Episode 时长聚合

Order task accepted_seconds
  = max(delivered_seconds - reported_bad_seconds, 0)

Order delivery_ready
  = 每个 catalog item 的 accepted ≥ requested
    且不存在 task_id=NULL 的 item
```

同一 Order 可挂多个 Job；交付进度跨 Job 汇总（注意避免重复采集）。

### 4.3 My Data 数据流

```text
可访问 Episode
  = Personal Library ACTIVE
    ∪ Order → Jobs → Uploads → Episodes
      （用户为该 Organization 成员或 Internal PrismaX Owner；Order status 为
       delivering / ready_for_invoice / complete；排除失败 Episode）

OrderSourceFilter
  → GET /api/orders/data-sources
  → source_ids=self,ORD-<id>
  → GET My Data summary / episodes
  → POST /data/downloads/ui
       { access_context:"my_data", selected_episode_ids }
```

#### 4.3.1 下载鉴权

`access_context=my_data` 时：登录即可；按 episode 拆分 personal / ORD；含 personal 才查 membership；不占月配额、不强制 Browse 可见性。Org 访问实时解析，不进 Personal Library。

内部 Owner 的 Org 数据访问同样在每次请求中通过 `data_organization_internal_owners` 实时解析；移除内部 Owner 后，其对应 Organization 的 Orders、Additional Episodes 与下载权限应立即失效。

| 所选内容 | membership | 预期 |
| --- | --- | --- |
| 仅 `ORD-*` | inactive/无 | ✅ |
| 仅 Self-serve | inactive/无 | ❌ 403 |
| 仅 Self-serve | active | ✅ |
| ORD + Self-serve | inactive/无 | ❌ |
| ORD + Self-serve | active | ✅ |
| 越权/已失效 episode | — | ❌ 403 |

### 4.4 Operator Web 上传与 SDK 上传差异

| 上传方式 | 端点 | 支持 `job_id` | Job/task 校验 | 能否累计 Job/Order 进度 |
| --- | --- | ---: | --- | --- |
| Web Upload | `/data/upload-sessions` | ❌ | 不进行 Job 归属校验 | ❌ `data_uploads.job_id=NULL` |
| SDK / CLI | `/v1/data/upload-sessions` | ✅ 可选 | 校验 Job 属于 Operator 且 task 在 Job 中 | ✅，但调用方必须显式传 `job_id` |

从 Upload Dashboard 的 Job Task 点击进入时，链接为 `/data/upload?job=true#&lt;task_id&gt;`。`job=true` 只触发“请使用 SDK 在已分配 Job 下上传”的提示横幅，`#task_id` 仍负责定位 Web Task；该跳转不传 `job_id`，也不改变上表的上传归属规则。

<span style="color:#2563eb">**09-16 Jobs 上传三端耦合**：隐藏 task 对公开 Web catalog 可能不可见，但可挂在 Job 上。BE 放开 Job task catalog 可见性过滤；FE 用横幅把 Operator 导向 SDK；SDK 在传入 `job_id` 时改为从 `list_jobs()` 的 Job.tasks 解析 scenario（不再调用公开 `list_tasks()`）。无 `job_id` 的旧路径仍用公开 task catalog，保持兼容。</span>

---

## 5. 每个页面的功能

### 5.1 Organization Owner — Orders

入口：`/robotic-data?view=orders`

- 加载 Organization / Orders / Invoices；无 Org 时提示联系 PrismaX。Owner 可写，Member 只读。
- 先请求 `GET /api/organizations` 获取全部可访问 Organization；只有 1 个时直接进入，多个时显示 Organization switcher。切换后按 `organization_id` 重新加载 Organization、Orders、Invoices，并清除当前 Order/编辑状态。
- 列表/详情展示 Robot（`product_name`）；详情含状态、rate、hours、history、actions。
- **Delivery Progress**（`production` 起）：三段条（accepted / rejected / remaining），刻度 `max(required, accepted+rejected)`；`reported_episode_count>0` 时显示「N episode(s) rejected · replacements queued」（优先字段，否则累加 history）。
- **Report bad**（`delivering`）：toggle「Report bad episodes」；文本格式 `id, reason; id2`（逗号分字段，分号/换行分条目；支持 `EP-`、中文标点；reason 可选）；CSV 同为逗号分字段；可展开 API 示例；确认按钮「Report episodes」。
- `delivery_ready` 时可 Approve Delivery → `ready_for_invoice`；发票可下载 PDF。

### 5.2 Organization Owner — Team

入口：`/robotic-data?view=orders` → Team

- Owner 发 7 天邀请（域名须匹配 Org）；链接 `?invite=TOKEN`，须手动 Accept；登录邮箱须一致。
- 客户端校验：邮箱格式、域名、是否已有访问；失败内联错误（不 toast）；「Send invite」+ Enter 提交。
- 成员与待邀请合并同一卡片；成员「Active · Added {date}」；邀请「Invite sent {date}」。Owner 可撤邀请/移成员，不能移自己。
- 所有邀请、撤销邀请和移除成员请求携带当前 `organization_id`；内部 PrismaX Owners 不出现在客户 Team/Manage access 列表中。

### 5.3 My Data

- 数据源：Self-serve + `ORD-*`（Order ≥ `delivering`）；全选=不过滤。
- 下载：`access_context=my_data`；文件名用全局 `episode_id`。
- 门禁：active membership **或** 所选全为 `ORD-*` 才可下；纯 ORD 不要求 personal membership；混选 Self-serve 则需 membership。
- `RobotFilter`；深链 `?source=<orderId>`（离 My Data 清除）；task catalog 按 hostname。
- 测前确认前端是否含上述门禁（marketing / app 可能不同步）。
- Internal PrismaX Owner 可访问其所有已授权 Organization 的可交付数据；选择 Organization 后必须只出现该 Organization 的 ORD 数据源，不能混入其管理的其他客户数据。

### 5.4 Admin Portal — Orders

- 列表/过滤/详情；创建：有 rate→`pending_approval`，无 rate→`submitted`；Robot **必填**；task 可搜索 combobox。
- 操作：编辑、Approve（含 `pending_approval` 二次 Approve）、Mark Delivering、Cancel；无旧 Complete。
- catalog API 失败时 Orders 仍加载并提示；列表/详情先出，robot/task/invoice 并行，失败仅 toast。
- Additional Episodes 增删；Job link/unlink（跨 Order 须先 unlink）。
- Order 详情中的 Job 卡优先显示 `assigned_user_email`，其次显示 `assigned_user_solana_address`，均缺失时才显示 `Operator #&lt;user_id&gt;`；Create Linked Job 的 Operator 下拉使用同一身份优先级。
- 点击 Refresh 同时刷新列表、当前打开的 Order、关联 Jobs 和 Episodes，避免只刷新主列表而详情仍显示旧状态。
- Custom item：`link-task` 映射 catalog（生产前；生产后锁定）。
- 坏数据：列表 `BadDataBadge`；摘要 Bad data 行；「Bad data reported」面板 + Reported chip。
- 列表层级：主标题=客户名，次级=Order ID；meta 突出 hours；状态 badge 着色。
- **已知缺陷**：Create linked Job hours `step=0.25` vs Order `step=0.01`，填 `0.1` 会被浏览器拦截（E2E-ADM-JOB-15）。

### 5.5 Admin Portal — Robotic Data

入口：Admin Portal → Data Download（`RoboticDataAdmin`）；需 Admin token。子视图：Assign Episodes / Uploads（默认 Uploads）。

**Assign Episodes to Orders**

- 仅 `production`/`delivering` Order；未选则禁用搜索。
- 按 Order catalog task 拉可交付 Episode（分组接口 ≤48 样本）；标记已在 Order 的为 `In Order`（不可再选）。
- 卡片开详情、checkbox 才选择；详情 Admin token + `?admin=true`，无 Download。
- Task 全选：`listAllDownloadableTaskEpisodes` 拉全量再按搜索过滤；拉取中 checkbox disabled；切 Order 丢弃飞行中结果。精确输入 `JOB-&lt;id&gt;` 时改为按 `job_id` 服务端过滤；普通关键词仍匹配 scenario/environment/upload/episode/JOB 文本。
- 右侧按 Task 汇总；前 7 chips + `…N`；Add 需确认；成功合并 added/already-in-order 并清空选择。不改 Job/Upload/payment。
- Episode 默认按 `episode_id` 从新到旧；当前搜索下的 assigned/selected 计数、Task 全选与取消全选均只作用于过滤后的 Episode。
- Additional Episodes 超过 500 条时，前端自动拆成每批最多 500 条并合并 `added_episode_ids` / `already_in_order_episode_ids`；任一后续批失败不会回滚已成功批次。

**Uploads**

- 按 Upload 分组：筛选/排序/分页；展开加载更多；正常视图 preview，Failed only 显示拒绝原因。空/错/过期态须正确且不残留旧数据。

### 5.6 Admin Portal — Operator Dashboard / Jobs

- 选 Operator 看 Jobs；创建 Job：**Order 必填**（`production` / `delivering` 下拉）→ Task 限该 Order；切 Order 清理不匹配 task；展示 Robot 卡。
- <span style="color:#2563eb">Order 下拉选项展示更多信息：`ORD-{id} · {robot} · {customer_name} - {主 task 名} - {小时}h`（主 task = 该 Order 中 hours 最大的 task；依赖 `available-orders` 返回的 `customer_name` + tasks）。</span>
- <span style="color:#2563eb">可把对公开 catalog 不可见的隐藏 task 挂到 Job（BE 已去掉 Job catalog 的 visibility 过滤）；此类 task 的上传须走 SDK。</span>
- 编辑：已有 Upload 的 task 不可删。删除：软删并清 `job_id`；已挂 Order 则自动 `job_detached` 解绑（弹窗警告 ORD）。
- Drawer：Robot category；阶段含 Customer accepted/rejected、QC、Initial accepted/rejected；展开 Review timeline；Initial rejected 错误码；Customer rejected 反馈。Admin 另有 `order_status`。Customer accepted 的 key 为 `customer_accepted`，展开后显示 Order 级 `delivery_approved` 时间。
- 支付：每 Job 仅 1 条活跃支付；再 Mark→409，须先 Void。金额按 `hours_payable`；未审批「Pending — under review」，已审批「Earned — pending payment」，均可 Mark paid。
- Admin 见 `ORD-*`；Operator 无 `order_id`/`order_status`，但有 `robot`。Create linked Job hours 步长缺陷见 JOB-15。
- VLA Operators 增加独立 Jobs 子区：跨所有 Operator 展示未删除 Job，默认每页 15 条；可用 `JOB-&lt;id&gt;` / `ORD-&lt;id&gt;`（大小写不敏感）精确搜索，非法格式在前端直接提示。
- 全量表展示 Operator email；无 email 时展示 wallet 缩略值、复制按钮与 Solana/Base/Monad/Aptos/Ethereum chain badge；复用既有 Drawer、Edit、Delete、Mark paid、Unmark 逻辑。全量表不提供 New Job，创建仍从具体 Operator Dashboard 发起。

### 5.7 Operator — Upload Dashboard

入口：`/data/upload`

- Jobs 表：ID / task chips（`logged/assigned`）/ rate / hours（最多 3 位去尾 0） / amount / dates；支付态含 Pending under review（Operator 无 `order_status` 时未付常落此态）。
- 点击 Job 的 Task chip 跳转 `/data/upload?job=true#&lt;task_id&gt;`：Task 存在时照常打开对应 UploadInfoModal，同时在页面顶部显示琥珀色 SDK 提示横幅，并提供 `https://github.com/PrismaXAI/sdk-vla-foundry` 外链。
- <span style="color:#2563eb">SDK 外链旁增加外链图标；进度小时数 `white-space: nowrap` 防换行。</span>
- 横幅支持关闭；若 URL 对应状态在 `found` / `not_found` / `no_task_id` 之间变化则重新显示。Task 不存在时追加“This task isn't available to view on our web platform.”；无 hash 时只显示通用 SDK 提示；没有严格的 `job=true` 时不显示。
- <span style="color:#2563eb">隐藏 task 场景预期落在 `not_found`：横幅仍引导用 SDK，Web Modal 可能打不开对应 Task，但不得据此认为 Job 未分配。</span>
- 点行开 Drawer：阶段含 Customer rejected；展开 timeline / 错误码 / Customer feedback。
- Due date 色阶；`#task_id` 开上传 Modal。Web 上传不绑 Job。

### 5.8 Admin Portal — Invoices

- 仅展示 `ready_for_invoice` 且没有发票的 Order 供选择。
- 一张发票可合并同一 Organization 的多个 Orders。
- 上传文件必须为 PDF 签名且不超过 25MB。
- Issue 后 Invoice 为 `issued`，Orders 仍为 `ready_for_invoice`。
- Mark Paid 需要确认；Invoice → `paid`，关联 Orders → `complete`。
- Invoice 公开 ID 改为 `INV-YYYY-NNNN`：年份取 `issued_at`，数字部分至少 4 位；下载和 Mark Paid 会校验 URL 中完整编号与数据库返回值一致，旧 `INV-12` 格式无效。

### 5.9 Admin Portal — Organizations

- 创建 Organization 并指定 Owner。Owner email 不存在时自动插入规范化小写的 email-only `users` 记录，再创建 Owner membership；存在时直接复用。
- 查看成员 email、role、user_id、joined_at。
- <span style="color:#2563eb">Organization 详情成员表增加 Action「Remove」：二次确认后调用 `DELETE .../members/&lt;user_id&gt;`；成功刷新详情。文案说明将撤销 Orders / My Data 访问且不可撤销。最后一位 Owner 的 Remove 禁用并 tooltip「Add another owner before removing the last organization owner.」；后端同步返回 409 `last_owner_required`。</span>
- 为无 Organization 的用户添加 Owner 身份。
- 创建 Organization 时 Owner 查找只匹配规范化后的 `users.email`，不再回退 `user_profile_email` / `linked_email`；用户已属于其他 Organization 仍返回 409。
- Admin 可在独立表单中添加 `@prismax.ai` Internal Owner，也可在 Organization 详情中移除；不存在的内部 email 会创建 email-only 用户。Organization 卡片分别显示 client owners、client members、internal 数量。
- Admin Organization 详情可返回 `internal_owners`；Owner/Member 客户接口不返回该字段，客户成员查询也排除同时存在内部 Owner 关系的用户。

### 5.10 SDK / CLI

- `prismax.list_jobs()` / `prismax jobs` 查询当前 Operator Jobs。
- Python、CLI、JSON spec 均支持可选 `job_id`。
- 优先级：函数/CLI 参数 `job_id` > JSON spec `job_id` > 不传。
- `job_id` 必须为整数，`bool` 也会被拒绝。
- 不传 `job_id` 保持旧版兼容，但上传不会计入 Job。
- <span style="color:#2563eb">传入 `job_id` 时，`resolve_task_id` / `create_upload_session` / `upload` 从该 Job 的 `tasks`（`list_jobs()`）按 scenario/task_name 解析，**不**走公开 `list_tasks()`；因此 Job 上的隐藏/不可见 task 可用名称上传。未传 `job_id` 时行为不变。直接传 `task_id` 仍短路，不查 catalog。</span>
- Worker MCAP 强制校验更新：Camera average FPS 允许相对 15/25/30/60 目标值偏差 `±2.0 FPS`；Joint-to-camera 最大同步偏移允许 `≤42ms`。Camera-to-camera 仍为 `<34ms`，rolling FPS 仍为 informational，不要混用。
- 为兼容历史 validation payload 与现有 UI 映射，结果 key 暂仍使用 `camera_avg_fps_within_0.5_of_target` 和 `joint_camera_sync_below_34ms`；判断必须读取 payload 中的新 tolerance/threshold，不能按 key 名推断阈值。

---

## 6. 关键 API

### 6.1 Job 与 Upload

| 方法 | 路径 | 角色 | 功能 |
| --- | --- | --- | --- |
| `GET` | `/data/jobs` | Operator | 页面查询本人 Jobs + summary |
| `GET` | `/data/jobs/<id>/episodes` | Operator | Episode + 阶段；含 `timeline`/`reported_reason`；Initial rejected 才有 `processing_error` |
| `GET` | `/data/admin/jobs?user_id=` | Admin | 查询指定 Operator Jobs |
| `GET` | `/data/admin/jobs?order_id=` | Admin | 查询指定 Order 关联的 Jobs（`orderAdminApi.listOrderJobs`） |
| `GET` | `/data/admin/jobs/all?page=&page_size=&job_id=&order_id=` | Admin | 跨 Operator 分页查询全部未删除 Jobs；`job_id` / `order_id` 为可选整数精确过滤；`page_size` 范围 1～100；响应补充 user email/wallet/chain 与 pagination |
| `GET` | `/data/admin/jobs/<id>` | Admin | 查询单个 Job 详情（`orderAdminApi.getJob`） |
| `GET` | `/data/admin/jobs/available-orders` | Admin | Job 表单 Order 下拉；返回 `production` / `delivering` Orders 及其 tasks、robot，替代旧 `/data/admin/orders?status=production`；<span style="color:#2563eb">另返回 `customer_name`；挂 Job 用的 task catalog 含隐藏（非可见）task</span> |
| `GET/POST/PATCH/DELETE` | `/data/admin/jobs[/<id>]` | Admin | 创建、编辑、软删除 Job |
| `PATCH` | `/data/admin/jobs/<id>`（`order_id` 字段） | Admin | Link/Unlink Job 与 Order；目标 Order 须处于 `production`/`delivering`；跨 Order 直移须先 unlink；有 Episode 时需 `confirmed=true` |
| `GET` | `/data/admin/jobs/<id>/episodes` | Admin | 同 Operator episodes；Admin jobs 另有 `order_status` |
| `POST` | `/data/admin/jobs/<id>/payments` | Admin | Mark Paid（按 `hours_payable`，封顶 assigned） |
| `GET/POST` | `/data/admin/jobs/<id>/payments[/void]` | Admin | 查询付款 / Void |
| `GET` | `/data/admin/downloadable-task-groups?task_ids=&episode_limit=&search=` | Admin | 按 task_id 分组返回 Episode 样本（≤48 条），支持关键词搜索；SQL 用 `ROW_NUMBER() OVER (PARTITION BY task_id)` 分页；`search=JOB-&lt;id&gt;` 精确转为 `job_id` 过滤，响应 Episode 补充 `job_id`，并按 `episode_id DESC` 返回最新数据 |
| `GET` | `/data/admin/downloadable-task-episodes?task_id=``&job_id=` | Admin | Task 全量可交付 Episode（全选用；样本仍用 task-groups≤48）；`job_id` 为可选正整数，供 JOB 搜索后的全选使用 |
| `GET` | `/v1/data/jobs` | Upload API Key | SDK 查询 Jobs；<span style="color:#2563eb">含各 Job 的 tasks（不受公开 visibility 限制），供 SDK 在 `job_id` 作用域解析 scenario</span> |
| `POST` | `/v1/data/upload-sessions` | Upload API Key | SDK 上传（可选 `job_id`）；due 过期/已付→409；robot 不匹配→400（含 Resume） |
| `POST` | `/data/upload-sessions` | Operator Gateway | Web Upload；当前不支持 `job_id` |

### 6.2 Order、Organization、Invoice 与 My Data

| 页面 | 关键端点 |
| --- | --- |
| Owner Organizations / Orders | `GET /api/organizations`、`GET /api/organization?organization_id=`；`/api/orders`、`/<ORD-ref>/submit`、`/approve`、`/approve-delivery`、`/reported-episodes`、`/cancel`（多 Organization 用户的业务请求携带 `organization_id`） |
| Owner Team | `/api/organization`、`/invitations`、`/invitations/accept`、`/members/<id>`；邀请与成员变更按当前 `organization_id` 执行，客户成员列表不暴露 Internal Owner |
| My Data | `/api/orders/data-sources`、My Data summary/episodes/download endpoints |
| Admin Orders | `/api/admin/orders`、`/approve`、`/mark-delivering`、`/cancel`、`/api/admin/task-scenarios` |
| Admin Order Episodes | `GET .../episodes`（含 `reported_bad*`、`reported_episode_count`）；`POST/DELETE .../additional-episodes`（上限 500；删须 confirmed） |
| Admin Robot Types | `GET /api/admin/orders/robot-types` |
| Admin Custom Task Link | `POST .../items/<item_id>/link-task`（生产前） |
| Admin Approved Operators | `GET .../get-operator-applications?status=approved`（前端翻页拉全） |
| Admin Organizations | `/api/admin/organizations`、`/<id>/owners`；`POST /api/admin/organizations/&lt;id&gt;/internal-owners`、`DELETE /api/admin/organizations/&lt;id&gt;/internal-owners/&lt;user_id&gt;`；<span style="color:#2563eb">`DELETE /api/admin/organizations/&lt;id&gt;/members/&lt;user_id&gt;`（需 confirmation；最后一位 owner → 409 `last_owner_required`）</span> |
| Admin Invoices | `/api/admin/invoices`、`/<INV-ref>/mark-paid`；`INV-ref` 必须为与 `issued_at` 一致的规范编号 `INV-YYYY-NNNN` |
| Owner Invoice Download | `/api/invoices`、`/<INV-ref>/download`；同样校验完整规范编号 |

---

## 7. 关键业务规则与风险

| 优先级 | 规则 | 验证点 |
| --- | --- | --- |
| P0 | Migrations 已执行 | Order/Job/reported/additional/robot_type 等表结构齐全 |
| P0 | Web 上传无 `job_id` | 不计入 Job/Order；正向须 SDK 带 `job_id` |
| P0 | Job SDK 横幅只是引导，不是 Job 绑定 | `?job=true#task_id` 不携带具体 `job_id`；即使由 Job Task 链接进入并打开 Web Upload Modal，Web 上传仍写入 `job_id=NULL`，必须改用 SDK/CLI 并显式传 Job ID |
| <span style="color:#2563eb">P0</span> | <span style="color:#2563eb">隐藏 task 的 Jobs 上传须 FE+BE+SDK 对齐</span> | <span style="color:#2563eb">BE 允许隐藏 task 挂 Job；FE Order 下拉可读 `customer_name` 并展示主 task；SDK 有 `job_id` 时从 Job.tasks 解析，不得再依赖公开 `list_tasks()`；缺任一端会导致「能建 Job 却传不上去」或「能传但 Web 误导」</span> |
| <span style="color:#2563eb">P0</span> | <span style="color:#2563eb">Admin 移除 Organization 成员</span> | <span style="color:#2563eb">Remove 后立即失去 Orders/My Data；最后一位 owner 前后端均不可删（UI disable + 409）；与 Internal Owner 移除接口区分</span> |
| P0 | Order 完成路径 | `delivering → approve → ready_for_invoice → invoice paid → complete` |
| P0 | Bad Episode 不可撤销 | accepted 立即下降，可能使 delivery_ready=false |
| P0 | My Data 权限 | ≥delivering 可见；踢人立即失效；纯 ORD 不需 personal membership |
| P0 | 多 Organization 与 Internal Owner 租户隔离 | 每次请求都按显式 `organization_id` 校验 member/internal-owner 关系；切换 Organization 不得残留前一个组织的 Order、Invoice、Team 或 My Data；移除 Internal Owner 后权限立即失效 |
| P0 | Internal Owner 对客户隐藏 | 仅 Admin Organization 详情返回 `internal_owners`；客户 Team/Manage access、成员列表和 client owner/member 计数均不得暴露内部账号 |
| P0 | Job tasks ⊆ Order；创建 Job Order 必填 | 非法 task→400；未选 Order 不可建 |
| P0 | 支付：每 Job 一条活跃支付；SDK due/已付/robot 校验 | 再 Mark→409；上传/Resume 同步受限 |
| P0 | Customer accept/reject | accepted=`DERIVED_READY`+Order 已审批；rejected=reported 表；勿用 `job_customer_review_status` |
| P0 | hours_payable 排除 customer-rejected | 进度仍用 hours_logged；Mark Paid 用 payable |
| P0 | Job 阶段契约与验收时间 | 前后端均使用 `customer_accepted`；验收时间来自 Order 最新 `delivery_approved`，不是逐 Episode 审核时间 |
| P0 | Additional Episodes / Admin Re-Approve / history 对客户端隐藏 | 见 E2E-ADM-ORD-11～15 |
| P1 | Job link/unlink；Additional ≤500；Browser 样本 ≤48；全选走全量接口 | 跨 Order 须先 unlink；切 Order 取消飞行中全选 |
| P1 | JOB 精确筛选与 Additional 分批 | 仅完整 `JOB-n` 触发服务端 `job_id` 过滤；Task 全选、assigned/selected 计数均服从筛选；>500 按 500 分批，后批失败时前批已提交，UI 必须提示部分成功并重新加载真实结果 |
| P1 | Invoice 规范编号 | 年份来自 `issued_at`，数字 ID 至少补齐 4 位且不截断；旧 `INV-12`、年份不匹配和非规范 URL 均拒绝；不得恢复依赖固定起始值的 sequence 重置逻辑 |
| P1 | 全量 Jobs 分页/搜索 | 只返回 `deleted_at IS NULL`；搜索仅接受完整 `JOB-n` / `ORD-n`；空结果 pagination 可为 `total_pages=0` |
| P1 | Organization Owner 自动建档 | email trim+lower；并发创建依赖 `ON CONFLICT(email) DO NOTHING`；确认历史用户 email 已归一到 `users.email`，避免因旧 fallback 字段产生重复身份 |
| P1 | MCAP 新阈值与旧 key 共存 | 28/32 FPS 边界通过、低于 28 或高于 32 失败（以 30 FPS 为例）；42ms 通过、>42ms 失败；下游不得根据旧 key 文案硬编码 0.5/34 |
| P1 | Robot 必填；custom task 生产前 link；QC 需 `qa_score≥50` | |
| P1 | 上报格式 `id, reason; id2`；交付「rejected · replacements queued」 | 旧 `id;reason` 每行已失效 |
| P1 | 工时 3dp；Operator jobs 含 robot、无 order_id/status | |
| P1 | Create linked Job hours `step` 缺陷 | Order `0.01` vs Job `0.25`（JOB-15） |
| P1 | marketing / app My Data UI 可能不同步 | 确认被测含门禁逻辑 |

---

## 8. E2E 测试用例（按页面）

> 每条只测一个点：前置 → 步骤 → 预期；「边界」只写负向。按页面执行即可覆盖主链路，跨页闭环见 §8.11。

### 8.1 Organization Owner — Orders

| Unified ID | 来源 TC | 功能 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E2E-OWN-ORD-01 | 330/TC-URL-01、330/TC-AUTH-02 | 页面入口与认证 | Owner 已登录 | 访问 `/robotic-data?view=orders`；加载 `/api/orders` | 直接进入 Orders；订单正常加载 | `?view=invalid` → Browse；无组织 → `organization_required`；Member 仅只读 | |
| E2E-OWN-ORD-02 | 326/TC-O-20、330/TC-ORD-01 | 创建并提交订单 | 用户为 Organization Owner | New Order → 选择 Robot Type → 填 tasks/hours/due date → Submit | Order 为 `submitted`；allowed actions 含 edit/cancel；列表与详情显示 Robot `product_name` | due date 缺失或 hours≤0 → 阻止提交；未选 Robot → 400 `robot_type_required`；Member 无 New Order | |
| E2E-OWN-ORD-03 | 326/TC-O-20、330/TC-ORD-02、330/TC-ORD-03 | Draft 保存与提交 | Owner 可创建订单 | Save as draft → 打开详情 → Submit | `draft → submitted`；Draft allowed action 含 submit | — | |
| E2E-OWN-ORD-04 | 330/TC-ORD-04 | 编辑 Submitted | Order=`submitted` | 编辑 task 或字段 → Save | 仍为 `submitted`；history 新增 `order_updated` | Cancelled 无 Edit | |
| E2E-OWN-ORD-05 | 330/TC-ORD-05 | 编辑使报价失效 | Order=`pending_approval` | 编辑任意字段 → Save | 退回 `submitted`；旧 Approve 和 rate pending 提示消失 | — | |
| E2E-OWN-ORD-06 | 326/TC-O-21、330/TC-ORD-08 | 接受 Admin rate | Order=`pending_approval` 且 Admin 已设 rate | 点击 `Approve $X/hr` | Order=`production`；rate_pending=false | 无 rate → 409；Member 无按钮 | |
| E2E-OWN-ORD-07 | 330/TC-ORD-10 | Cancel | Order 为 draft/submitted/pending_approval | Cancel → 确认 | Order=`cancelled` | production 及以后无 Cancel；缺 confirmed → 409 | |
| E2E-OWN-ORD-08 | 330/TC-DEL-01 | 查看 Delivery Progress | Order 状态为 `production` / `delivering` / `ready_for_invoice` / `complete`；已有部分 Episode | 打开详情 | 展示 delivered/requested/reported bad/accepted/remaining 与 task breakdown；进度条三段（accepted=绿 / rejected=红 / remaining=灰）；刻度按 `max(required, accepted+rejected)` 动态缩放 | `production` 阶段即可见进度条（不再仅限 delivering 起）；未达标时 Approve Delivery disabled；custom `task_id=NULL` 不贡献 ready | |
| E2E-OWN-ORD-09 | 330/TC-BAD-01 | 文本上报坏 Episode | Order=`delivering` | toggle 上报 → 输入 `12523, camera blocked; 22072; EP-22073, issue` → Report episodes | reported↑、accepted↓；预览 ready/duplicate/invalid | 空/>5000/reason>500 拒绝；勿用旧每行 `id;reason` | |
| E2E-OWN-ORD-10 | 330/TC-BAD-02 | CSV 上报坏 Episode | Order=`delivering` | 上传 CSV → 确认 | 返回 reported/not_in_order/already_reported；仅有效且未报过的写入 | 非 delivering、Member、缺 confirmed 拒绝；已上报不可撤销 | |
| E2E-OWN-ORD-11 | 330/TC-DEL-02 | Approve Delivery | `delivering + delivery_ready` | Approve Delivery → 确认 | `ready_for_invoice`；history=`delivery_approved` | 未 ready 不可用；Member 无按钮；缺 confirmed → 409 | |
| E2E-OWN-ORD-12 | 326/TC-O-22、330/TC-INV-03 | 下载发票 | Invoice 已开具 | Order 详情 → PDF 下载 | 获取 signed URL 并在新标签打开 | 其他 Organization Invoice → 404 | |
| E2E-OWN-ORD-13 | 326/TC-ERR-06、326/TC-ERR-07、330/TC-ERR-01、330/TC-ERR-02 | Order 表单校验 | Owner/Admin 可编辑 Order | 输入非法 spec_link；hours=0 或负数 | 分别返回 URL 格式和 hours>0 错误 | spec_link 空值允许并转 null | |
| E2E-OWN-ORD-14 | lanmanc/a8ee326 | rejected · replacements 提示 | Order≥production 且 reported>0 | 看 Delivery Progress | 显示「N episode(s) rejected · replacements queued」；Task 无 per-task 坏数据时长行 | count=0 不显示 | |
| E2E-OWN-ORD-15 | Sep15/423ee00、4dd558b | 多 Organization 切换与订单隔离 | 当前用户可访问 A、B 两个 Organization，且两边各有 Order/Invoice | 进入 Orders → 在 Organization switcher 依次选择 A、B | 切换后重新加载当前 Organization、Orders 和 Invoices，并清空之前打开的 Order 详情/编辑态；每次只显示所选 Organization 数据 | 仅可访问一个 Organization 时不显示切换器；伪造无权限 `organization_id` 返回 403/404 且不泄漏数据 | |

### 8.2 Organization Owner — Team 页面

| Unified ID | 来源 TC | 功能 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E2E-OWN-TEAM-01 | 330/TC-ORG-04 | 创建邀请 | Owner | 输入 email → Send invite / Enter | 7 天 token 链接；成员与邀请同卡；Active / Invite sent | 格式/域名/已有访问 → 内联错误（不 toast）；API 409 同 | |
| E2E-OWN-TEAM-02 | 330/TC-ORG-05 | 接受邀请 | 用户无 Organization，持有效 token | 打开邀请链接 → 点击 Accept Invitation | 用户加入组织；URL 清除 invite；可见组织订单 | token 过期/已接受报错；登录 email 不匹配 → 403；不会自动 accept | |
| E2E-OWN-TEAM-03 | 330/TC-ORG-06 | 移除成员 | 组织存在 Member | Team → Remove → 确认 | Member 被移除并立即失去 ORD My Data | Owner 移除自己应被拒绝 | |

### 8.3 My Data 页面

| Unified ID | 来源 TC | 功能 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E2E-MYD-01 | 326/TC-O-23、330/TC-SRC-01、330/TC-SRC-03 | Order 数据源状态范围 | 用户为 Org 成员；Order 有 Episode | 分别将 Order 置为 production/delivering/ready_for_invoice/complete，加载 filter | delivering、ready_for_invoice、complete 返回 ORD 源；production 不返回 | 非成员不可见；这是对旧版“仅 complete”的更新 | |
| E2E-MYD-02 | 330/TC-SRC-01 | 单 Order 过滤 | ≥1 个可见 ORD 源 | 选择某个 `ORD-*` | 仅显示该 Order Episodes；请求含正确 `source_ids` | 无 ORD 源时 Filter 不渲染 | |
| E2E-MYD-03 | 330/TC-SRC-02 | 全选与 Self-serve | 多个 ORD + Personal Episodes | 全选；再只选 Self-serve | 全选等价无过滤；Self-serve 仅个人数据 | Order 与个人数据重复时只显示一次 | |
| E2E-MYD-04 | 330/TC-SRC-03、330/TC-DL-01 | 下载共享 Episode | Order≥delivering 且用户为成员 | 选择 ORD Episode → Download | `access_context=my_data`；不占个人月配额；文件用 `{episode_id}.mcap` 和 `{episode_id}/…` 命名 | 移除成员后立即失败；不能使用 uploader episode_key 导致覆盖 | |
| E2E-MYD-05 | lanmanc/774e80b、7608e84 | 无 membership 下载纯 ORD | Org 成员；membership inactive；Order≥delivering 有 Episode | 只选 `ORD-*` Episode → Download | UI 可点；API 成功；不查 / 不要求 personal membership | 文案提示 Self-serve 只读、公司 Order 不受影响 | |
| E2E-MYD-06 | lanmanc/774e80b、7608e84 | 无 membership 拦截 Self-serve | 同用户有 Self-serve Episode；membership inactive | 只选 Self-serve → Download | UI disabled 或 API 403，提示需 personal membership | 有 active membership 时应可下 | |
| E2E-MYD-07 | lanmanc/774e80b、7608e84 | 混合选择需 membership | inactive membership；同时选 `ORD-*` + Self-serve | 批量 Download | UI/API 拒绝；仅对 personal 行触发 membership 校验 | 开通 membership 后同选择应成功 | |
| E2E-MYD-08 | lanmanc/774e80b | 越权 / 失效访问 | 用户 A 选用户 B 的 episode，或踢出 Org 后重试原 ORD 下载 | 直接调 `POST /data/downloads/ui` `access_context=my_data` | 403 `one or more episodes are no longer accessible in My Data` | 列表侧也不应再出现该 ORD 源 | |
| E2E-MYD-09 | lanmanc/774e80b | 私有 Order task 可见性 | Order task 在 Browse 中不可见（非 public）；My Data 仍可访问该 Episode | My Data 下载该 Episode | 成功；`enforce_task_visibility` 对 my_data 为 false | Browse/公开 catalog 仍不可见该 task | |
| E2E-MYD-10 | lanmanc/69d8e57 | RobotFilter 过滤数据源 | My Data 中有来自不同 Robot 型号的 Episodes | 展开 RobotFilter → 选择某机器人型号 → 查看 Episode 列表 | 仅显示匹配该 Robot 的 Episodes；切换选项实时刷新；取消过滤恢复全量 | 无 Robot 数据时 Filter 不渲染或显示空状态 | |
| E2E-MYD-11 | lanmanc/69d8e57 | `?source=<orderId>` 深链接至 My Data | 用户已登录且为对应 Order 所属 Org 成员；Order≥delivering | 在 Orders 详情点击「View in My Data」→ 页面跳转到 My Data section；URL 含 `?source=<orderId>` | My Data 自动按该 `orderId` 过滤；URL 中 `?source=` 正确保留；切换至其他 section 时 `?source=` 从 URL 清除 | 手动构造非法 orderId 时 My Data 应显示「无数据」而非报错崩溃 | |
| E2E-MYD-12 | Sep15/423ee00、4dd558b | Internal Owner 跨 Organization 数据权限 | 同一 `@prismax.ai` 用户是 A、B 的 Internal Owner；两边均有 ≥delivering Order | 分别选择 A、B 并进入 My Data/下载；随后由 Admin 移除其 A 的 Internal Owner | 移除前可分别访问两边但无交叉数据；移除后 A 的列表、详情与下载立即拒绝，B 仍正常 | Internal Owner 不需要客户 membership；伪造第三个 Organization ID 不可访问 | |

### 8.4 Admin Portal — Orders 页面

| Unified ID | 来源 TC | 功能 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E2E-ADM-ORD-01 | 326/TC-ERR-02、330/TC-AUTH-01 | Admin 认证 | Admin Token | 打开 Orders 或调用 Admin API | 正常加载 | 无效/过期 → 401；非 Admin → 403；触发 session expired event | |
| E2E-ADM-ORD-02 | 330/TC-ADM-01 | Task catalog 容错 | `/api/admin/task-scenarios` 失败 | 打开 Orders Dashboard | Orders 仍加载；提示 scenarios unavailable；Create Order 仍可打开 | — | |
| E2E-ADM-ORD-03 | 326/TC-O-03 | Admin 创建 Order | Organization 已存在 | 选择 Robot Type → 创建 tasks/hours/due date；分别不填/填写 rate | 无 rate → `submitted`；有 rate → `pending_approval`；列表与详情显示 Robot `product_name` | 非法 Organization/task/spec 应报错；未选 Robot → 400 `robot_type_required`；Robot ID 不存在 → 400 `robot_type_not_found` | |
| E2E-ADM-ORD-04 | 326/TC-O-04、330/TC-ORD-06 | Approve 相同 rate | Submitted 且已有 rate | Approve → 输入相同 rate | `production` | — | |
| E2E-ADM-ORD-05 | 326/TC-O-05、330/TC-ORD-07 | Approve 不同 rate | Submitted | Approve → 输入不同 rate | `pending_approval`；Owner 看到新 rate 提示 | — | |
| E2E-ADM-ORD-06 | 326/TC-O-06、330/TC-ORD-09 | Mark Delivering | `production` | 点击 Mark Delivering | `delivering` | 非 production → 409 | |
| E2E-ADM-ORD-07 | 326/TC-O-06 | 废弃 Complete 路径回归 | `delivering` | 检查 UI；调用旧 `/api/admin/orders/<ref>/complete` | UI 无 Complete；旧端点 404；Order 保持 delivering | 只能由 Owner Approve Delivery 后经 Invoice Paid 完成 | |
| E2E-ADM-ORD-08 | 326/TC-O-07、330/TC-ORD-11 | Admin Cancel | draft/submitted/pending_approval | Cancel + Confirm | `cancelled` | production 及以后 → 409 | |
| E2E-ADM-ORD-09 | 330/TC-JOB-01 | Order catalog task 约束 | Order 有 catalog task IDs | 为该 Order 创建/更新 Job，分别选择合法和非法 task | 合法成功；非法 task_id → 400 | 省略 order_id 保留原关联；显式 null unlink；custom `task_id=NULL` 不可分配 | |
| E2E-ADM-ORD-10 | 330/TC-ERR-04 | Rate 校验 | 可 Approve Order | 输入 hourly_rate≤0 | 400 `hourly_rate must be greater than zero` | — | |
| E2E-ADM-ORD-11 | lanmanc/cdb10f7 | Admin 从 `pending_approval` 直接 Re-Approve | Order=`pending_approval`（Owner 尚未 Approve rate） | Admin 在 Order 详情点击 Approve → 输入 rate（相同或不同） | Order 直接进入 `production`；Owner 不需要操作；history 新增 `order_approved` | rate≤0 → 400；非 `pending_approval`/`submitted` → 错误 | |
| E2E-ADM-ORD-12 | lanmanc/9ad0709 | Admin 追加 Additional Episodes | Order 存在；已知 `episode_id` 列表 | `POST /api/admin/orders/<ref>/additional-episodes` body: `{episode_ids:[1,2,3]}` | 写入 `data_order_additional_episodes`；Order history 出现 `additional_episodes_added`；response 含追加结果 | 超过 500 条 → 业务错误；非整数/负数 episode_id → 400；重复 ID 自动去重 | |
| E2E-ADM-ORD-13 | lanmanc/9ad0709 | Admin 移除 Additional Episode | Order 已有 additional episodes | `DELETE /api/admin/orders/<ref>/additional-episodes/<episode_id>` body: `{confirmed:true}` | `data_order_additional_episodes` 对应行删除；history 出现 `additional_episode_removed` | 缺 `confirmed=true` → 409；不存在的 episode_id → 404 | |
| E2E-ADM-ORD-14 | lanmanc/9ad0709 | 查看 Order 关联 Episodes 列表 | Order 有 additional + job-linked episodes | `GET /api/admin/orders/<ref>/episodes` | 返回 `{order_id, episode_count, episodes:[...]}`；包含 additional 和 job-linked 两类 | 非 Admin 权限 → 403 | |
| E2E-ADM-ORD-15 | lanmanc/6398f7c | Additional Episodes history 对客户端隐藏 | Admin 已追加/移除 Additional Episodes | 以 Organization Owner/Member 身份查看 Order history | 不显示 `additional_episodes_added` / `additional_episode_removed` 类型事件；其余 history 事件正常可见 | Admin 后台查看时可见所有 history | |
| E2E-ADM-ORD-16 | lanmanc/3d15b97、1cd4225 | Robot Type 必填校验 | Admin 有效 Token；Robot Types 列表已加载 | ① 创建 Order 不选 Robot → 尝试提交；② 选择不存在的 robot_type_id 直接调 API | ① UI 提示「Select a Robot.」并阻止提交；② API 返回 400 `robot_type_required` / `robot_type_not_found` | Robot Types 加载失败时 Orders 仍可加载并弹出 toast 提示 Robots unavailable；编辑已有 Order 时 Robot 下拉回显当前值 | |
| E2E-ADM-ORD-17 | lanmanc/0701439、7133eea | Admin link custom task 到正式 catalog | Order 有 `is_custom=true, task_id=null` 的 item；Order 状态为 DRAFT/SUBMITTED/PENDING_APPROVAL | Admin 在 Order 详情找到 unresolved custom item → 搜索/选择 catalog task → 确认 link | item `task_id` 更新为选中值；`is_custom` 置 false；`name` 更新为 catalog `scenario`；Order history 新增 `order_task_mapped` 事件 | link 成功后该 item 不再显示 `Needs catalog task` 提示；custom task 在交付统计中开始被计入 | |
| E2E-ADM-ORD-18 | lanmanc/0701439 | link-task 负向校验 | 各种异常前提（见边界） | ① 对已 link 的 item 再次 link；② 对非 custom item 调用；③ 对 PRODUCTION 后的 Order 操作；④ 非法 task_id；⑤ 重复 link 同一 task_id | ① 409 `task_already_mapped`；② 409 `task_already_mapped`；③ 409 `order_locked`；④ 400（非正整数）；⑤ 409 `task_already_linked` | 非 Admin 角色调用返回 403；task_id 为 bool 时应返回 400（不允许 bool 转 int） | |
| E2E-ADM-ORD-19 | lanmanc/3aaaf4d | Admin Dashboard 加载体验 | Admin 正常打开 Orders 页面 | 观察 Orders 列表、taskTypes、robotTypes、invoices 四个资源加载时序 | Orders 列表/详情优先渲染（loading 消失）；taskTypes/robotTypes/invoices 后续独立加载；任一失败仅弹 toast，不阻塞已加载的订单列表；Orders → Invoices 「Add to Invoice」快捷按钮功能正常 | 慢网络下：先出 Orders、后出 Robot 下拉，不应页面空白或报错 | |
| E2E-ADM-ORD-20 | lanmanc/f68fb6a、0663368 | 坏数据角标与面板 | reported>0 | 列表 → 摘要 → Bad data 面板 | 角标「Bad data reported · N」；摘要 N EP·hrs；面板列 EP/reason/hrs/date；Reported chip+tooltip；cancelled 无 mapping 角标 | 无坏数据不渲染面板 | |
| E2E-ADM-ORD-21 | lanmanc/3573c69 | 订单列表层级 | 多状态订单 | 看列表主标题/ID/meta/badge | 主标题=客户名；次级=Order ID；hours 加粗；badge 着色 | 选中高亮；长名 ellipsis | |
| E2E-ADM-ORD-22 | Sep15/423ee00 | Job Operator 身份与 Refresh 一致性 | Order 关联三类 Job：有 email、仅 Solana address、两者均无 | 查看 Job 卡片和 Create linked Job 下拉；后台改变 Job/Episode 后点击 Refresh | Operator 依次优先显示 email、Solana address、user ID；Refresh 同步更新列表、当前 Order、Jobs 与 Episodes | 缺 email 不显示空白或错误用户；刷新后不得保留旧详情状态 | |

### 8.5 Admin Portal — Robotic Data / Assign Episodes to Orders 页面

| Unified ID | 来源 TC | 功能 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E2E-ADM-RD-01 | lanmanc/8640858、5da390c | Admin Episode Browser 按 task 分组展示 | Order 关联多个 task 的 Job；Episodes 已处理 | 打开 Admin Portal → Robotic Data → `Assign Episodes to Orders`；调用 `GET /data/admin/downloadable-task-groups?task_ids=…&episode_limit=48` | 按 scenario/task 分组显示；每组最多 48 条；支持折叠/展开；支持关键词搜索（upload_id、episode_id、scenario、environment） | `episode_limit` 超过 48 时截断到 48；`task_ids` 非正整数 → 400 | |
| E2E-ADM-RD-02 | lanmanc/251d4f7 | Episode 卡片与选择操作解耦 | 已选择 Production/Delivering Order，Browser 至少显示 1 个可用 Episode | 点击 Episode 卡片正文；关闭弹窗后再点击卡片左上角 checkbox | 点击卡片只打开详情，不改变 selected 数量；点击 checkbox 才选中 Episode，且不会误打开详情 | 用键盘聚焦卡片后按 Enter/Space 均可打开详情；checkbox 操作不应冒泡 | |
| E2E-ADM-RD-03 | lanmanc/251d4f7 | Admin Episode 详情与相机预览鉴权 | Admin token 有效；Episode 有多相机 preview | 打开 Episode 详情并检查网络请求、徽章、footer 和相机切换 | 请求 `GET /data/downloadable-episodes/&lt;episode_id&gt;/preview-videos?admin=true`，使用 Admin Bearer token；弹窗展示 Episode/Score/Duration/Robot、同 upload Episode 数、Task 平均质量/时长；Admin 模式隐藏 Download episode | 401/403 触发 Admin session expired（不是 User session expired）；无 token/无视频/接口失败时显示 preview unavailable/error 且页面不崩溃 | |
| E2E-ADM-RD-04 | lanmanc/251d4f7 | 已在 Order 的 Episode 禁止重复选择 | `GET /api/admin/orders/&lt;ref&gt;/episodes` 返回已关联 Episode | 查看对应卡片与详情弹窗，尝试点击 checkbox/Select 按钮 | 卡片显示 `In Order`、checkbox checked 且 disabled；Task 的 `in order` 数正确；详情显示 `In order` 徽章、说明文案和 disabled 的 `In order` 按钮 | 已关联 Episode 不进入单选或批量选择集合；全组都已关联时 Task checkbox disabled | |
| E2E-ADM-RD-05 | lanmanc/251d4f7、f68fb6a | Task 全选/取消 | Task 含 available/selected/in-order | Task checkbox 全选→再取消 | 全选走全量接口+搜索过滤；in-order 不选；mixed 态正确；拉取中 disabled | 拉取失败 toast 并保留选择；切 Order 丢弃飞行结果 | |
| E2E-ADM-RD-06 | lanmanc/251d4f7 | Task 与右侧 Selection 汇总准确 | 至少 2 个 Task；选择项包含不同时长，部分已在 Order | 跨 Task 单选/批量选择，并逐项取消 | 每个 Task 显示 `total episodes · N in order · M selected`；右侧总数和总小时为所有 selected Episodes 汇总；按 Task 分组显示名称、数量和各组小时（保留 2 位小数） | 缺失/非法 duration 按 0 计；已在 Order 数不计入 selected 总数/小时 | |
| E2E-ADM-RD-07 | lanmanc/251d4f7 | Selection chips、折叠摘要与清空 | 同一 Task 选择超过 7 个 Episodes，另一个 Task 也有选择 | 删除前 7 个可见 chip 中一项；点击 `… N episodes` 的 ×；点击 header 的 Clear × | 单个 × 仅移除对应 Episode；摘要 × 一次移除该组第 8 个起的隐藏项；Clear 清空全部 Task 的选择、详情缓存、计数和小时，Add 按钮恢复 disabled | 操作一个 Task 不影响其他 Task；选择为 0 时 Clear × 不显示 | |
| E2E-ADM-RD-08 | lanmanc/251d4f7 | 选择状态跨搜索/展开视图保留 | 已选择多个 Task/Episode | 修改搜索词使已选 Episode 暂时不可见；展开/折叠 Task、Load more 后恢复搜索 | 右侧仍保留完整 Episode 对象、Task 分组和小时；恢复搜索后 checkbox 状态一致；Load more 不清空既有选择 | 切换到另一个 Order 时必须清空 selected/assigned/confirmation 状态，并重新加载该 Order 已关联 Episodes，防止跨 Order 误加 | |
| E2E-ADM-RD-09 | lanmanc/251d4f7 | 批量 Add 确认与返回结果同步 | 已选择 available Episodes，其中服务端可能已存在部分 ID | 点击 `Add to ORD-*` → 确认；检查 `POST additional-episodes` 返回的 `added_episode_ids` / `already_in_order_episode_ids` | 提交期间按钮 disabled；added 与 already-in-order IDs 都合并进 assigned 集合且去重；可取得详情的项进入 assigned Episode 列表；成功后清空选择并关闭确认框，提示新增数量或全部已存在 | API 失败时显示错误、保留选择和确认框以便重试；401/403 触发 Admin session expired；重复点击不得并发提交 | |
| E2E-ADM-RD-10 | lanmanc/251d4f7 | 详情弹窗内选择状态联动 | 打开一个未关联且未选择的 Episode 详情 | 点击 `Select episode`，关闭并重开；再从卡片 checkbox 或右侧 chip 取消 | 详情按钮选择后文本变为 `Selected`，卡片 checkbox、Task selected 数及右侧汇总同步；外部取消后重开详情显示未选择 | 已在 Order 的详情只能显示 disabled `In order`，不得触发 toggle | |
| E2E-ADM-RD-11 | lanmanc/f68fb6a、0663368 | Admin Order Episodes 坏数据标记展示 | Admin 已选中含有 `reported_bad=true` Episode 的 Order | ① 查看 Episode chips 列表；② 悬停已标记 chip；③ 查看「Bad data reported」明细面板 | ① 已上报 Episode 的 chip 有红色高亮样式（`reportedEpisodeChip`）并在 chip 内显示「Reported」标记；② 悬停 tooltip 显示「Bad data reported: {reason}」（有 reason 时）或「Bad data reported」（无 reason 时）；③ 明细面板：每行含 `EP-{id}`、reason（无则「No reason provided」）、小时数和上报日期；`reported_bad=false` 的 Episode 不在面板中 | 需 backend `0663368` 及以上方有 `reported_bad` 字段；旧 backend 返回 `reported_bad=false`、面板不渲染；上报 Episode 数 = 0 时「Bad data reported」面板不渲染 | |
| E2E-ADM-RD-12 | Sep15/423ee00、4dd558b | 按 JOB 精确筛选与过滤内全选 | 同一 Task 下有多个 Job 的可交付 Episode，并含已加入当前 Order 的数据 | 搜索完整 `JOB-&lt;id&gt;` → 检查顺序和计数 → Task 全选/取消全选 | 仅返回该 `job_id`；按 `episode_id` 降序；assigned/selected 计数及全选只覆盖过滤结果，全量请求携带 `job_id` | 不存在 JOB 显示空态；普通关键词仍走文本搜索；`JOB-abc` 不得误作为有效 job_id | |
| E2E-ADM-RD-13 | Sep15/423ee00 | Additional Episodes 500 条分批与部分成功 | 准备 1001 条可选 Episode | 一次 Add 全部；再模拟第 2 批请求失败并重试 | 正常时发出 500/500/1 三批并合并 added/already IDs；失败时保留前面成功批次，提示错误并刷新真实 Order Episodes | 不得重复加入或把前批误报为回滚；重试只提交尚未加入的 Episode | |

### 8.6 Admin Portal — Operator Dashboard / Jobs 页面

| Unified ID | 来源 TC | 功能 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E2E-ADM-JOB-01 | 326/TC-J-10 | **Job 表单基础字段校验** | Admin 查看某 Operator Dashboard；已选一个 Production 或 Delivering Order | New Job → **选择 Order → 分别测试：过去日期、负 rate、无 task、重复 task → Save** | 每种非法输入各自提示对应错误，不发起创建请求 | **合法输入 → Job 创建成功并显示 ORD 徽章** | |
| E2E-ADM-JOB-02 | 326/TC-J-11、330/TC-JOB-01、aparna/70e71f1、d174c89 | 创建 Order-linked Job（正向） | Order 有 catalog tasks；状态分别为 `production` / `delivering` | **Order 下拉选择目标 Order → Task 列表自动切换为该 Order 的 tasks → 选择 task** | 创建成功；显示 `ORD-*` 徽章；**Order 卡片显示关联 Robot 型号**；Delivering Order 与 Production 行为一致 | Order 不存在、状态不在允许集合或 task 不属于 Order → 400/409（Order 必填校验及切换行为详见 JOB-16/17/18） | |
| E2E-ADM-JOB-03 | 326/TC-J-12 | 编辑 Job | Job 未删除 | 修改 rate/due date/tasks | 列表实时更新 | 移除已有 Upload 的 task → 409 | |
| E2E-ADM-JOB-04 | 326/TC-J-15 | 删除 Job | Job 存在 | Delete → 二次确认 | Job 软删除；关联 Upload `job_id` 清空；Episode/QA 数据保留 | **Job 已关联 Order → 弹窗显示「ORD-X」警告；删除成功后系统自动写入 `job_detached` 审计事件并将 `order_id` 置 NULL（不再需要先手动 Unlink）；**有 logged hours 时显示警告 | |
| E2E-ADM-JOB-05 | 326/TC-J-16 | Initial rejected 筛选 | 含失败 Episode | Drawer → Initial rejected | 仅失败条 + 错误码 | 切 filter 收起展开；无「Rejected」旧标签 | |
| E2E-ADM-JOB-06 | 326/TC-J-13、326/TC-ERR-03 | Mark Paid | 有 outstanding | Mark Paid | Paid；金额=`min(hours_payable, assigned)×rate` | 无 outstanding 无按钮；已付→409；Pending under review 仍可付 | |
| E2E-ADM-JOB-07 | 326/TC-J-14 | Void Payment | Job 有 active payment | Unmark → **单次确认（不再多选）** → Confirm | 对应工时恢复 outstanding；保留 void 审计字段 | **每个 Job 最多一条活跃支付，Void 弹窗仅展示该唯一支付的金额和日期；**无 active payment 显示空状态 | |
| E2E-ADM-JOB-08 | 326/TC-ERR-04 | 跨 Job Void | payment_id 属于其他 Job | 对当前 Job 调用 void 并传跨 Job ID | 跨 Job ID 不变；`voided_count=0` | 不得修改其他 Job 的 payment | |
| E2E-ADM-JOB-09 | 326/TC-ERR-05 | Operator 角色校验 | user_id 不是 Operator | 使用该用户创建 Job | 400 `user is not an operator` | — | |
| E2E-ADM-JOB-10 | 326/TC-LINK-05 | Rate 独立性 | Job 关联 Order | Job rate 填为不同于 Order rate | 两侧保留各自值；无自动同步 | UI/文档应避免把 Job 工资误认为客户报价 | |
| E2E-ADM-JOB-11 | 326/TC-LINK-06 | 一个 Order 多 Job | Order 已有关联 Job | 再创建另一个合法 Job | 两个 Job 均成功；交付进度跨 Job 汇总 | 验证无重复 Episode 计算 | |
| E2E-ADM-JOB-12 | lanmanc/7d9c47f、aparna/70e71f1 | Job Link 到 Order | Job 无 order_id（**UI 已强制 Order 必填，需通过 API 直接创建 order_id=NULL 的 Job 作为前置条件**）；目标 Order 状态为 `production` 或 `delivering` | PATCH `/data/admin/jobs/<id>` `{order_id: <X>}` | Job.order_id 更新；Order history 写入 `job_attached`；Admin Dashboard 显示 ORD 徽章 | Order 处于 `submitted`/`ready_for_invoice`/`complete` 等状态 → 拒绝；非 Admin → 403 | |
| E2E-ADM-JOB-13 | lanmanc/7d9c47f | Job Unlink from Order | Job 已关联 Order；Job 无已交付 Episode | PATCH 设 `order_id: null` | Job.order_id 清空；Order history 写入 `job_detached` | 有已交付 Episode 且未携带 `confirmed=true` → 返回 episode 数量并拒绝；携带后成功 | |
| E2E-ADM-JOB-14 | lanmanc/7d9c47f | 禁止 Job 跨 Order 直移 | Job 已关联 Order A | PATCH 直接设 `order_id: <Order B>` | 返回错误："A Job cannot move directly between Orders. Unlink it from its current Order first." | 须先 unlink（null）再 link 到新 Order | |
| E2E-ADM-JOB-15 | QA/2026-09-07 | Create linked Job hours 精度与 Order 对齐 | Order=`production`；catalog task requested hours=`0.1`（或任意非 `0.01+n×0.25` 的值） | Order 详情 → Create linked Job → 勾选该 task → hours 填 `0.1`（与 Order 一致）→ 选 Operator/rate/due date → Create Job | **当前缺陷**：浏览器原生校验拦截，提示 nearest valid values 为 `0.01` 和 `0.26`，无法提交。**修复后预期**：可成功创建 Job，`assigned_hours=0.1`，与 Order task hours 一致 | 根因：`OrderAdminDashboard.js` Create linked Job hours 为 `min="0.01" step="0.25"`，Order 创建 hours 为 `step="0.01"`；同时验证 `0.25`/`1` 等合法步长值仍可正常创建 | |
| E2E-ADM-JOB-16 | aparna/aee9de4 | Job 表单 — Order 必填校验 | Admin 打开 New Job 弹窗 | 不选 Order 直接点 Save | 表单内联错误「Pick the order this job belongs to.」，不发起创建请求；Task 下拉显示「Select an order first」并禁用 | 选择 Order 后 Task 列表切换为该 Order tasks；「Add task」按钮在未选 Order 时禁用 | |
| E2E-ADM-JOB-17 | aparna/aee9de4 | Job 表单 — 切换 Order 清理不匹配 task | 已选 Order A 并添加 task 行 | 将 Order 下拉切换到 Order B（task 集合不同） | 属于 Order A 但不在 Order B task 集合中的 task 行被移除；若全部行都被移除则保留一行空行 | 两个 Order 共有的 task 行保留；切换后 Robot Card 更新为 Order B 的 robot | |
| E2E-ADM-JOB-18 | aparna/aee9de4 | Job 表单 — Robot Card 显示 | Order 关联了 robot_type_id | 选择该 Order → 查看 Robot Card | 卡片展示 `product_name`、`manufacture · category · X-DoF`；点击「Spec ↗」跳转 `/data/fleet#<machine_id>` | Order 无 robot_type_id → 显示「No robot associated with this order.」；未选 Order → 显示「Pick an order to see the robot it runs on.」 | |
| E2E-ADM-JOB-19 | aparna/6b3c2a7、31b329c | Customer 分桶 | 含 ready/qa、reported、以及 Approve 后仍未拒收的 DERIVED_READY | Drawer 阶段计数；Approve 前后对比 | 未审批：ready→QC/Initial；reported→Customer rejected；审批后未拒收 DERIVED_READY→Customer accepted；两类 rejected 文案可区分 | PARTIALLY_READY 不进 Customer accepted | |
| E2E-ADM-JOB-20 | aparna/6b3c2a7、31b329c、685ae57 | Review timeline | 含 Initial rejected / QC / Customer rejected / Customer accepted | 逐条展开 | timeline 可见；Initial rejected→错误码；Customer rejected→reason；Customer accepted→Order 最新 `delivery_approved` 时间 | 未展开无 timeline；Order 无 approval history 时 accepted `at` 才允许为 null | |
| E2E-ADM-JOB-21 | aparna/6b3c2a7、fbd8854 | payable + 支付态 | 有 reported；Order=delivering | 看标签/outstanding → Approve → Mark Paid | delivering=Pending under review（已扣 reported）；审批后=Earned pending payment；金额=`min(payable,assigned)×rate`；小时≤3dp | 全拒无可付；已付→409 | |
| E2E-ADM-JOB-22 | aparna/0c69e07、8ebd8e1 | 全量 Jobs 初始加载与分页 | 多个 Operator 共至少 16 个未删除 Job，并准备 1 个软删除 Job | Admin Portal → VLA Operators → Jobs；翻到第 2 页再返回 | 调用 `/data/admin/jobs/all?page=1&page_size=15`；按 `created_at DESC, job_id DESC`；总数/页数/前后页状态正确；软删除 Job 不出现 | 无数据时显示 `No jobs found.`；`page_size>100` 按 100；非整数 page/page_size→400 | |
| E2E-ADM-JOB-23 | aparna/0c69e07、8ebd8e1 | 全量 Jobs 精确搜索 | 已知 Job 与 Order ID | 依次搜索 `JOB-123`、`job-123`、`ORD-45`，再 Clear | JOB/ORD 分别映射为后端 `job_id`/`order_id` 精确过滤；大小写均可；Clear 恢复第一页全量结果 | 纯数字、模糊文本、额外空格内文本显示格式错误且不请求；后端非整数 filter→400 | |
| E2E-ADM-JOB-24 | aparna/0c69e07、8ebd8e1 | 全量 Jobs 用户与复用操作 | 准备 email Operator、仅 wallet Operator，以及可编辑/可支付/已支付 Job | 检查 User 列；打开 Drawer；执行 Edit、Mark paid、Unmark、Delete | 优先展示 email+user ID；无 email 时展示 wallet 缩略、复制和 chain；操作复用既有 modal/drawer，成功后当前页与选中详情同步 | 全量表没有 New Job；删掉某页最后一行时自动退回前一页；Admin token 过期触发统一退出 | |
| E2E-ADM-JOB-25 | aparna/d41821e、685ae57 | Customer accepted key 与时间 | Order 有 DERIVED_READY Episodes，并产生一条或多条 `delivery_approved` history | 请求 Job episodes 并在 Drawer 展开 accepted Episode | stage/timeline key=`customer_accepted`；`reached=true`；`at` 等于该 Order 最新 `delivery_approved.created_at`；前端颜色/标签正确 | 未验收时不可进入 accepted；不得返回旧 key `customer`；同 Order Episodes 共享 Order 级时间 | |
| <span style="color:#2563eb">E2E-ADM-JOB-26</span> | <span style="color:#2563eb">Sep16/3d3c948、4a6260a</span> | <span style="color:#2563eb">Order 下拉客户/主 task 信息 + 隐藏 task 可挂 Job</span> | <span style="color:#2563eb">准备 `production`/`delivering` Order：有 organization 名、多 task（小时不同）、至少一个对公开 catalog 不可见的 catalog task</span> | <span style="color:#2563eb">打开 New Job → 检查 Order 下拉文案 → 选择该 Order → 勾选隐藏 task → Save</span> | <span style="color:#2563eb">下拉含 `ORD-* · robot · customer_name - 主 task - hours`；隐藏 task 可选且创建成功；`GET available-orders` 响应含 `customer_name`</span> | <span style="color:#2563eb">无 organization 时 customer 段可为空；主 task 取 hours 最大者；旧 backend 无 `customer_name` 时 UI 不得崩溃</span> | |

### 8.7 Operator — Upload Dashboard 页面

| Unified ID | 来源 TC | 功能 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E2E-OP-UP-01 | 326/TC-J-01 | Assigned Jobs 表格 | Operator 有 active Job | 登录 → `/data/upload` → Upload Dashboard | 展示 Job、tasks、rate、hours、amount、dates 和 summary；无 Admin Actions；**Task chip 显示 `Xh / Yh`（logged/assigned），如 `1.5h / 2.0h`** | 无 Job → `No jobs assigned yet.` | |
| E2E-OP-UP-02 | 326/TC-J-02 | Job Detail Drawer | Job 存在 | 点 Job 行 | Episode + 阶段条（含 Customer/Initial rejected） | 无 Episode 空态 | |
| E2E-OP-UP-03 | 326/TC-J-03 | Hash 打开上传 Modal | task_id=4 可用 | 访问 `/data/upload#4` | 自动打开 task 4 UploadInfoModal | `#999` 不报错；相同 hash 不重复打开 | |
| E2E-OP-UP-04 | 326/TC-J-04 | Due Date 显示 | Job 有/无 due date | 查看 Due Date 列 | 逾期红色；≤7 天橙色；Today；正常绿色 | null → `—` | |
| E2E-OP-UP-05 | 326/TC-ERR-01 | Operator Token 过期 | Gateway token 过期 | 请求 `/data/jobs` | 401 并跳转登录 | — | |
| E2E-OP-UP-06 | 326/TC-LINK-01、326/TC-LINK-04 | Web Upload 不绑定 Job | Operator 有 Job | 通过 Web 上传 Job task 或非 Job task | 上传本身成功；`data_uploads.job_id=NULL`；Job hours/Drawer 不变化 | 当前已知限制；不得误判为 Job 上传成功 | |
| E2E-OP-UP-07 | aparna/31b329c、6b3c2a7 | Operator rejected / timeline | 含 reported + Initial rejected | Drawer 筛选并展开 | timeline + feedback / 错误码 | 无 order_id；无 reported 则计数 0 | |
| E2E-OP-UP-08 | aparna/3547764 | Operator jobs 含 robot | Job 挂有 robot 的 Order | `GET /data/jobs` | 有 `robot`；无 `order_id`/`order_status` | 无 robot → null | |
| E2E-OP-UP-09 | aparna/fbd8854、31b329c | 工时展示 / 支付态 | 未付 Job，小时非 2 位整 | 看表格 | ≤3dp 去尾 0；未付多为 Pending under review | 已付显示日期 | |
| E2E-OP-UP-10 | aparna/e18ab46、<span style="color:#2563eb">4a6260a</span> | Job Task 跳转与 SDK 提示 | Operator 有包含有效 `task_id` 的 Job | 点击 Job Task chip | 进入 `/data/upload?job=true#&lt;task_id&gt;`；对应 UploadInfoModal 打开；顶部显示可关闭的琥珀色提示及可在新标签打开的 SDK 链接<span style="color:#2563eb">（含外链图标）</span> | 通过该页面执行 Web Upload 仍为 `job_id=NULL`，Job/Order 工时不累计 | |
| E2E-OP-UP-11 | aparna/e18ab46 | SDK 横幅 URL 分支与关闭状态 | 准备有效 Task ID、无效 Task ID，并可直接修改 URL | 依次访问 `?job=true#有效ID`、`?job=true#无效ID`、`?job=true`；关闭横幅；再改变 hash；最后访问无 `job=true` 的地址 | 分别得到 found、not_found、no_task_id 文案；无效 Task 追加 Web 不可用提示；关闭后隐藏，variant 改变后重新显示；无严格 `job=true` 时无横幅 | Task 尚在加载时不提前误判 not_found；SDK 链接含 `noopener noreferrer`；<span style="color:#2563eb">Job 上隐藏 task 的 hash 预期走 not_found，仍须引导 SDK 上传</span> | |

### 8.8 Admin Portal — Invoices 页面

| Unified ID | 来源 TC | 功能 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E2E-ADM-INV-01 | 326/TC-O-08、330/TC-INV-01 | Issue Invoice | 同 Organization 有 ready_for_invoice、无 Invoice Orders | 选择一个或多个 Order → 上传 PDF → Issue | Invoice=`issued`；Order 仍为 ready_for_invoice | complete/已有 Invoice 不在 picker；跨 Org 被过滤 | |
| E2E-ADM-INV-02 | 326/TC-O-09、330/TC-INV-02 | Mark Paid | Invoice=`issued` | Mark Paid & Complete → 确认 | Invoice=`paid`；paid_at 存在；关联 Orders=`complete` | 缺 confirmed → 409 | |
| E2E-ADM-INV-03 | 326/TC-ERR-08、330/TC-ERR-03 | PDF 格式与大小 | 可开票 | 上传无 `%PDF-` 签名文件；上传>25MB PDF | 分别返回 400、413 | 不创建 Invoice；不遗留可见孤立记录 | |
| E2E-ADM-INV-04 | 326/TC-ERR-09 | 重复开票保护 | Order 已有 Invoice | 打开 picker 并尝试通过 API 再开票 | UI 不显示该 Order；API 拒绝重复关联 | — | |
| E2E-ADM-INV-05 | Sep15/4dd558b | Invoice 规范编号与 URL 校验 | 准备本年签发、数字 ID&lt;10000 及 ID&gt;9999 的 Invoice | 检查列表编号，并分别用正确编号、旧 `INV-12`、错误年份执行下载/Mark Paid | 显示 `INV-&lt;issued_year&gt;-&lt;至少4位ID&gt;`；正确完整编号成功；大 ID 不截断 | 旧格式、错误年份、数字部分与记录不一致均返回 404/校验失败 | |

### 8.9 Admin Portal — Organizations 页面

| Unified ID | 来源 TC | 功能 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E2E-ADM-ORG-01 | 326/TC-O-01、330/TC-ORG-01、lanmanc/fb981c9、826e4ae | 创建 Organization | Owner email 可以存在或尚无用户记录 | 输入 name + owner email → Create | Organization 出现；用户成为 Owner；domain 正确；email 不存在时自动创建规范化小写的 email-only 用户，不再返回 404 | 用户已有 Org → 409；非法 email 拒绝；并发同 email 创建不得生成重复用户 | |
| E2E-ADM-ORG-02 | 326/TC-O-02、330/TC-ORG-02 | 查看成员 | Organization 已存在 | View Members | 显示 email、role、user_id、joined_at | 无成员显示空状态 | |
| E2E-ADM-ORG-03 | 330/TC-ORG-03 | 添加 Owner | 目标用户存在且无 Org | POST Owners / UI 添加 | 用户成为 Organization Owner | email 不存在 → 404；已有 Org → 409 | |
| E2E-ADM-ORG-04 | lanmanc/fb981c9 | Owner canonical email 查找 | 分别准备 `users.email` 已存在、仅 `user_profile_email`/`linked_email` 存在的用户 | 使用带前后空格和不同大小写的同一 email 创建 Organization | trim+lower 后只按 `users.email` 复用用户；不查询 profile/linked email | 仅旧 fallback 字段命中时会创建新的 email-only 用户；发布前须确认历史数据归一化与唯一约束 | |
| E2E-ADM-ORG-05 | Sep15/423ee00、4dd558b | 添加/移除 Internal Owner | Admin 登录；准备一个已存在和一个不存在的 `@prismax.ai` email | 向多个 Organization 添加同一 Internal Owner → 查看详情 → 移除其中一条关系 | 不存在用户时自动建 email-only 用户；同一内部用户可拥有多个 Organization；详情和 internal count 正确，移除只影响目标 Organization | 非 `@prismax.ai` 拒绝；重复添加不产生重复关系；无效 user/org 返回明确错误 | |
| E2E-ADM-ORG-06 | Sep15/423ee00、4dd558b | Internal Owner 客户侧隐藏 | Organization 同时有 client owner/member 和 Internal Owner | 对比 Admin Organization 详情、客户 Team/Manage access 与卡片计数 | Admin 详情含 `internal_owners`；客户接口和页面不返回/展示内部账号；client owner/member/internal 三类计数独立 | 同一用户存在内部关系时不得意外出现在客户成员列表 | |
| <span style="color:#2563eb">E2E-ADM-ORG-07</span> | <span style="color:#2563eb">Sep16/ac13865、b746d18</span> | <span style="color:#2563eb">Admin 移除 Organization 成员</span> | <span style="color:#2563eb">Org 有 ≥2 位 owner（或 1 owner + 1 member）；被移除用户可访问 Orders/My Data</span> | <span style="color:#2563eb">详情 → Remove member → 确认；再尝试移除最后一位 owner</span> | <span style="color:#2563eb">成员删除成功并刷新详情；被移除者立即失去 Orders/My Data；最后一位 owner 按钮 disabled，API 409 `last_owner_required`</span> | <span style="color:#2563eb">缺 confirmation → 409；非 Admin → 403；不存在的 member → 404；不得误调 Internal Owner 删除接口</span> | |

### 8.10 SDK / CLI 集成面

#### 8.10.1 Job 查询

| Unified ID | 来源 TC | 功能 | 操作步骤 | 预期结果 | Test Result |
| --- | --- | --- | --- | --- | --- |
| E2E-SDK-JOB-01 | 326/TC-SDK-01 | Python 查询 Jobs | `prismax.list_jobs()` | 返回 list，包含 job_id、due date、rate、tasks；无 Job 返回 `[]` | |
| E2E-SDK-JOB-02 | 326/TC-SDK-02 | CLI 文本查询 | `prismax jobs` | 每行输出 ID、due date、rate、task names；多 task 逗号分隔 | |
| E2E-SDK-JOB-03 | 326/TC-SDK-03 | CLI JSON 查询 | `prismax jobs --json` | 输出与 API 一致的完整 JSON 数组 | |
| E2E-SDK-JOB-04 | 326/TC-SDK-04 | Key 类型校验 | 用 `pxa_` 调用 list_jobs | 本地抛 `PrismaxAuthError`，不请求后端 | |
| E2E-SDK-JOB-05 | 326/TC-SDK-05 | 无效 Key | 用无效/过期 Upload Key 查询 | 后端 401/403；SDK 抛 `PrismaxAuthError` | |

#### 8.10.2 上传方式与优先级

| Unified ID | 来源 TC | 功能 | 操作步骤 | 预期结果 | Test Result |
| --- | --- | --- | --- | --- | --- |
| E2E-SDK-UP-01 | 326/TC-SDK-10 | Python 上传绑定 Job | `prismax.upload(..., job_id=<id>)` | Session 创建成功；`data_uploads.job_id` 正确 | |
| E2E-SDK-UP-02 | 326/TC-SDK-11 | CLI Upload | `prismax upload ... --job-id <id>` | 上传成功并写入 job_id | |
| E2E-SDK-UP-03 | 326/TC-SDK-12 | JSON Spec | spec 含 `"job_id":42` → `upload-data` | 请求 body 含 job_id=42；无字段则不发送 | |
| E2E-SDK-UP-04 | 326/TC-SDK-13 | 参数覆盖 Spec | spec job_id=42，CLI/Python 参数=7 | 实际使用 7 | |
| E2E-SDK-UP-05 | 326/TC-SDK-14、326/TC-LINK-02 | 不传 job_id | 使用新版 SDK 但省略 job_id | 上传成功；body 无 job_id；Job hours 不累计 | |
| <span style="color:#2563eb">E2E-SDK-UP-06</span> | <span style="color:#2563eb">Sep16/6cb1edc</span> | <span style="color:#2563eb">job_id 作用域解析隐藏 task</span> | <span style="color:#2563eb">Job 含公开 catalog 不可见的 task；用 scenario/task_name + `job_id` 上传（不传 task_id）</span> | <span style="color:#2563eb">SDK 调 `list_jobs` 而非 `list_tasks`；解析到正确 task_id；Session 写入该 `job_id`；Job/Order 工时可累计</span> | |

#### 8.10.3 校验、权限与回归

| Unified ID | 来源 TC | 功能 | 操作步骤 | 预期结果 | Test Result |
| --- | --- | --- | --- | --- | --- |
| E2E-SDK-VAL-01 | 326/TC-SDK-20 | job_id 类型 | spec 使用字符串或 bool | 本地 `PrismaxValidationError` | |
| E2E-SDK-VAL-02 | 326/TC-SDK-21 | Job 不存在 | 上传传 99999 | 后端 404/4xx | |
| E2E-SDK-VAL-03 | 326/TC-SDK-22 | Task 不属于 Job | Job 仅 task 4，上传其他 task | 后端 400；SDK 不预校验 | |
| <span style="color:#2563eb">E2E-SDK-VAL-08</span> | <span style="color:#2563eb">Sep16/6cb1edc</span> | <span style="color:#2563eb">job_id 作用域忽略 Job 外 task 名</span> | <span style="color:#2563eb">公开 catalog 有 scenario A，但当前 Job.tasks 不含 A；带该 Job 的 `job_id` + scenario A 解析</span> | <span style="color:#2563eb">本地 `PrismaxValidationError` 且文案含 `job_id`；不调用 `list_tasks`；job 不存在时提示 No job found</span> | |
| E2E-SDK-VAL-04 | 326/TC-SDK-23 | 跨 Operator Job | Operator B 使用 A 的 job_id | 403/404，不泄漏 Job | |
| E2E-SDK-REG-01 | 326/TC-SDK-40 | 旧上传脚本 | 新 SDK 运行不含 job_id 的旧脚本 | 上传成功，保持兼容 | |
| E2E-SDK-REG-02 | 326/TC-SDK-41 | Scenarios 回归 | `prismax scenarios` | Task catalog 正常 | |
| E2E-SDK-REG-03 | 326/TC-SDK-42 | Resume/Status 回归 | 对现有 Session 执行 resume/status（**前提：Job 未付、due_date 未过期**） | 功能正常，job_id 不破坏恢复；**Resume 返回 200（非 409）** | |
| E2E-SDK-REG-04 | 326/TC-SDK-43 | Download 回归 | 使用 Download Key 下载 | 下载流程不受 Job 功能影响 | |
| E2E-SDK-VAL-05 | aparna/7eb381e | Due date 已过 → 拒绝上传 | Job due_date 为昨天或更早 | SDK 上传带该 job_id | 返回 409；msg 含「due date (YYYY-MM-DD) has passed」；Resume 同一 Upload 也返回 409 | due_date 为今天（当天 23:59 UTC 前）→ 允许上传 | |
| E2E-SDK-VAL-06 | aparna/7eb381e | 已付 Job → 拒绝上传 | Job 已有活跃支付记录（`data_job_payments.voided_at IS NULL`） | SDK 上传或 Resume 带该 job_id | 返回 409；msg「This job has already been paid and can no longer accept new uploads.」 | Void 支付后上传恢复正常 | |
| E2E-SDK-VAL-07 | aparna/7eb381e | Robot 型号不匹配 → 拒绝上传 | Job 关联 Order 有 `robot_type_id=X`；上传用的机器 robot type ≠ X | SDK 上传带该 job_id + 错误型号机器的 serial_number | 返回 400；msg「{machine_name} doesn't match the robot type required for this job's order ({required_name})」 | 机器 serial_number 无法识别为任何 robot type → 400「machine isn't recognized as a supported robot type」；正确型号 → 200 | |

#### 8.10.4 Worker MCAP 校验

| Unified ID | 来源 TC | 功能 | 操作步骤 | 预期结果 | Test Result |
| --- | --- | --- | --- | --- | --- |
| E2E-MCAP-01 | lanmanc/82f2098 | Camera average FPS 新容差正边界 | 分别构造相对目标 FPS 偏差恰为 `-2.0` / `+2.0` 的 MCAP（如目标 30 FPS 时为 28/32）并执行 validation | 强制校验通过；结果 `tolerance=2.0` | |
| E2E-MCAP-02 | lanmanc/82f2098 | Camera average FPS 超界 | 构造相对目标偏差 `>2.0` 的 MCAP（如 27.99 FPS） | 强制校验失败；legacy key 仍为 `camera_avg_fps_within_0.5_of_target` | |
| E2E-MCAP-03 | lanmanc/82f2098 | Joint-camera sync 42ms 边界 | 使 camera frame 到最近 joint state 的最大偏移恰为 `42ms` | 强制校验通过；结果 `threshold_ms=42` | |
| E2E-MCAP-04 | lanmanc/82f2098 | Joint-camera sync 超界与兼容 key | 使最大偏移为 `42.001ms`；同时检查 UI 错误映射 | 强制校验失败；legacy key 仍为 `joint_camera_sync_below_34ms`，现有 E-005 映射保持可识别；Camera-to-camera `<34ms` 规则不变 | |

### 8.11 跨页面端到端闭环

| Unified ID | 来源 TC | 场景 | 操作步骤 | 预期结果 | Test Result |
| --- | --- | --- | --- | --- | --- |
| E2E-FLOW-01 | 326/TC-LINK-03、326/TC-SDK-30 | Job 上传正向闭环 | Admin 建 Job → Operator list_jobs → SDK 带 job_id/task 上传 → 等待处理 → 查看双方 Dashboard | Job hours 累计；Drawer 有 Episode；阶段分布正确 | |
| E2E-FLOW-02 | 326/TC-SDK-32 | Operator Payment | Flow-01 后 Mark Paid | 金额=`min(hours_payable, assigned)×rate`；Paid | |
| E2E-FLOW-03 | 326/TC-SDK-33 | Job 与 Order 关联可见性 | Job 关联 order_id 并完成 SDK 上传 | Admin Job 显示 ORD 徽章；Operator 接口不暴露 order_id；Order 不自动推进 | |
| E2E-FLOW-04 | 326/TC-LINK-05 | Rate 双轨 | Customer rate 与 Job rate 设置不同值 | Invoice 与 Payment 分别按各自 rate 计算，无串用 | |
| E2E-FLOW-05 | 326/TC-LINK-06 | 多 Job 汇总 | 同一 Order 建两个合法 Job并分别上传 | 两个 Job 独立统计；Order 按 task 聚合两者 Episode | |
| E2E-FLOW-06 | 330/TC-DEL-01、330/TC-DEL-02、330/TC-INV-01、330/TC-INV-02 | 完整交付与开票闭环 | Order → Job → SDK Upload → Mark Delivering → 达到 requested → Owner Approve → Issue Invoice → Mark Paid | 状态依次为 production/delivering/ready_for_invoice/complete；Invoice paid；My Data 全程权限符合状态 | |
| E2E-FLOW-07 | lanmanc/774e80b、7608e84 | 无 membership 的公司下载闭环 | 准备 inactive membership 的 Org Member → Mark Delivering 后进 My Data → 只下 ORD → 再尝试 Self-serve / 混合 → 移除成员再下 ORD | 纯 ORD 成功；Self-serve/混合失败；移除后 ORD 立即 403；全程不占个人月配额 | |
| E2E-FLOW-08 | aparna/6b3c2a7、31b329c | 拒收→扣应付→验收晋升 | 多条 ready → Delivering → 部分 report bad → Approve Delivery → Mark Paid | 上报后 rejected↑/payable↓；Approve 后未拒收→Customer accepted；支付不含拒收小时 | |
| E2E-FLOW-09 | Sep15/423ee00、4dd558b | Internal Owner 多 Organization 闭环 | Admin 将同一内部用户加入 A/B → 用户切换 A/B 查看 Orders、Invoices、My Data → Admin 移除 A 权限 → 用户重新访问 A/B | 添加后两边业务可分别操作且严格隔离，客户 Team 均不显示该用户；移除后 A 立即失权、B 不受影响 | |
| <span style="color:#2563eb">E2E-FLOW-10</span> | <span style="color:#2563eb">Sep16/3d3c948、4a6260a、e18ab46、6cb1edc</span> | <span style="color:#2563eb">隐藏 task Jobs 上传闭环</span> | <span style="color:#2563eb">Admin 建含隐藏 task 的 Job → Operator 点 Task 见 SDK 横幅（可 not_found）→ SDK 带 job_id + scenario 上传 → 查 Job/Order 进度</span> | <span style="color:#2563eb">Web 不累计；SDK 成功写入 job_id 且 hours 上涨；三端缺一则失败（下拉无客户信息/解析不到隐藏 task/误走 Web）</span> | |

---

## 9. 发布前检查清单

**环境**
- [ ] Migrations：`additional_episodes`、`robot_type_id` 等已执行
- [ ] Migration `20260914_data_organization_internal_owners.sql` 已执行，并验证同一 Internal Owner 可关联多个 Organization
- [ ] 四类账号就绪；被测前端含 My Data 门禁与 Assign Episodes 相关提交
- [ ] 确认历史 Owner email 已归一到 `users.email`，并验证 email 唯一约束/并发自动建档

**主链路**
- [ ] SDK 带 `job_id` 正向累计；Web 上传不绑 Job
- [ ] Order：`delivering → approve → ready_for_invoice → invoice paid → complete`；无旧 Complete
- [ ] Bad report 后 accepted/delivery_ready 变化；新上报格式（OWN-ORD-09）
- [ ] My Data：≥delivering 可见；纯 ORD 无 membership 可下；踢人立即失效（MYD-05～08、FLOW-07）
- [ ] 多 Organization 切换后 Orders/Invoices/My Data 严格隔离；Internal Owner 被移除后立即失权（OWN-ORD-15、MYD-12、FLOW-09）
- [ ] Invoice 使用 `INV-YYYY-NNNN` 规范编号，旧格式和错误年份不可下载/Mark Paid（ADM-INV-05）

**Admin Orders / Robotic Data**
- [ ] Robot 必填；custom task link；坏数据角标/面板（ADM-ORD-16～20）
- [ ] Additional Episodes + history 对客户端隐藏（ADM-ORD-12～15）
- [ ] Assign Episodes：选择/详情/全选全量/Add（ADM-RD-01～11）
- [ ] Order Job 身份按 email → Solana → user ID 展示，Refresh 同步刷新详情；Episode 按 JOB 精确搜索、最新优先、过滤内全选及 >500 分批/部分成功（ADM-ORD-22、ADM-RD-12～13）
- [ ] 订单列表层级与 badge（ADM-ORD-21）

**Organizations / Invoices**
- [ ] Internal Owner 仅允许 `@prismax.ai`，支持自动建档、跨 Organization 添加和单关系移除（ADM-ORG-05）
- [ ] Admin 可见 internal 列表/计数；客户 Team、Manage access 与成员接口完全隐藏内部账号（ADM-ORG-06）
- [ ] <span style="color:#2563eb">Admin 可移除客户 Owner/Member；最后一位 owner 不可删；移除后 Orders/My Data 立即失效（ADM-ORG-07）</span>
- [ ] Invoice 年份取 `issued_at`，数字 ID 至少补齐 4 位且大 ID 不截断；未恢复固定 sequence 起始值（ADM-INV-05）

**Jobs / Operator / SDK**
- [ ] Job Order 必填、Production/Delivering 均可选、删 Job 自动解绑、单次支付、QC≥50（JOB-02/04/06/16～18）
- [ ] Job Task 链接带 `?job=true#task_id`，SDK 横幅的 found/not_found/no_task_id、关闭/重显与外链均正确；Web Upload 仍不绑定 Job（OP-UP-10～11）
- [ ] <span style="color:#2563eb">Order 下拉含 customer_name/主 task；隐藏 task 可挂 Job；SDK 带 job_id 按 Job.tasks 解析隐藏 task（JOB-26、SDK-UP-06、SDK-VAL-08、FLOW-10）；FE/BE/SDK 须同版本联调</span>
- [ ] Link/Unlink 约束；Create linked Job hours 步长（JOB-12～15，已知缺陷）
- [ ] SDK due/已付/robot 校验（SDK-VAL-05～07）
- [ ] Customer 分桶 + timeline + payable/支付态（JOB-19～21、OP-UP-07～09、FLOW-08）
- [ ] Operator jobs 返回 robot、无 order_id/status
- [ ] 全量 Jobs 分页、JOB/ORD 精确搜索、用户 email/wallet、复用管理操作（JOB-22～24）
- [ ] `customer_accepted` key 与 Order 级 `delivery_approved` 时间（JOB-25）
- [ ] MCAP Camera FPS ±2.0、Joint-camera ≤42ms，以及 legacy result key 兼容（MCAP-01～04）

---

## 附录：历史改动索引

正文已吸收业务规则与用例。下列仅保留 commit 索引，细节以对应日期章节 / E2E 为准。

### A. 2026-09-03/04 — My Data 下载与 membership 解耦
| 仓库 | Commit | 要点 |
| --- | --- | --- |
| backend | `774e80b` | `access_context=my_data` 下载鉴权 |
| marketing | `7608e84` | `canDownloadEpisodeIds` 门禁 |
相关：§4.3、E2E-MYD-05～09、E2E-FLOW-07

### B. 2026-09-04～06 — Additional Episodes / Job↔Order / Browser / Re-Approve
| 仓库 | 代表 Commit | 要点 |
| --- | --- | --- |
| backend | `9ad0709` `7d9c47f` `5da390c` `cdb10f7` | additional 表+API；link/unlink；task-groups；Admin Re-Approve |
| app | `0813f86` `8640858` | OrderAdmin + Episode Browser |
| marketing | `6398f7c` | 隐藏 additional history |
相关：§3.4～3.5、E2E-ADM-ORD-11～15、ADM-JOB-12～14、ADM-RD-01

### C. 2026-09-08 — Assign Episodes UX（`251d4f7`）
卡片开详情 / checkbox 选择；Task 批量；Selection 汇总；Add 结果合并。相关：E2E-ADM-RD-02～10

### D. 2026-09-10 — 坏数据可见性 / 全选全量 / 上报与 Team
| 仓库 | Commit | 要点 |
| --- | --- | --- |
| app | `f68fb6a` | BadDataBadge、面板、Task 全量全选 |
| backend | `0663368` | `reported_episode_count`、reported 字段、列表批量查询 |
| marketing | `08ba694` `a8ee326` | 上报格式、Team 邀请、replacements 提示 |
相关：E2E-ADM-ORD-20、ADM-RD-05/11、OWN-ORD-09/14、OWN-TEAM-01

### E. 2026-09-11 — Customer accept/reject（data jobs v3）
| 仓库 | Commit | 要点 |
| --- | --- | --- |
| app | `b266a6d` `31b329c` `fbd8854` `3573c69` | Drawer timeline/分桶；工时展示；订单列表层级 |
| backend | `6904307` `6b3c2a7` `3547764` | stage/timeline/payable；Operator 返回 robot |
相关：§3.2/3.3、E2E-ADM-JOB-19～21、OP-UP-07～09、FLOW-08、ADM-ORD-21
