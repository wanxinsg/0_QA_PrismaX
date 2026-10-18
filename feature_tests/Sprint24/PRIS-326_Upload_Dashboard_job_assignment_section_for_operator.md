# PRIS-326：Upload Dashboard Job Assignment Section for Operator

> 分析日期：2026-08-31  
> 分析范围：  
> - `app-prismax-rp`：commit `ea440c148df11f3161b92c07ed14f15ff8115bff`（含）→ 最新  
> - `app-prismax-rp-backend`：commit `87aa49f30ff565e212bd1ea9caaddd9f3641b1c0`（含）→ 最新  
> - `sdk-vla-foundry`：commit `d1c65bc`（含）→ `testing` 分支最新（`8aaa744`）  
> 分析人：AI（基于代码 diff，不参考其他 MD 文档）

---

## 1. Commit 清单

### 1.1 前端 `app-prismax-rp`（共 6 commits）

| Commit | 日期 | 说明 |
|--------|------|------|
| `ea440c1` | 2026-08-25 | PRIS-326: implement first version of data jobs |
| `b9615b9` | — | PRIS-326: improve misc ui styling |
| `c2ab2dc` | 2026-08-28 | PRIS-326: add task id hash url for /data/upload |
| `d38793c` | 2026-08-28 | PRIS-326: add unmark payment support; order id support |
| `4f24b59` | — | PRIS-326: misc styling improvement |
| `e7b97c7` | — | Merge pull request #80 from PrismaXAI/PRIS-326-data-jobs |

### 1.2 后端 `app-prismax-rp-backend`（共 8 commits）

| Commit | 日期 | 说明 |
|--------|------|------|
| `87aa49f` | 2026-08-25 | PRIS-326: implement first version of data jobs |
| `43b08cc` | 2026-08-26 | PRIS-326: refactor db schema to put tasks_data in the same data_jobs table |
| `d1b4ab7` | — | PRIS-326: update apis for upload sdk |
| `e84470b` | — | PRIS-326: support unmark/void data job payments |
| `e1d0ba0` | — | Merge branch 'testing' into PRIS-326-data-jobs |
| `d5b1acb` | — | PRIS-326: add order_id to the data_jobs table |
| `cba5720` | — | PRIS-326: exclude failed status from hours logged |
| `294e426` | — | PRIS-326: clean up helper func used by upload sdk |
| `e97fab2` | — | Merge pull request #67 from PrismaXAI/PRIS-326-data-jobs |

### 1.3 <span style="color:#1a73e8">SDK `sdk-vla-foundry`（共 2 commits）</span>

| Commit | 日期 | 说明 |
|--------|------|------|
| <span style="color:#1a73e8">`d1c65bc`</span> | <span style="color:#1a73e8">2026-08-28</span> | <span style="color:#1a73e8">feat: add optional jobs integration for uploads</span> |
| <span style="color:#1a73e8">`8aaa744`</span> | <span style="color:#1a73e8">2026-08-31</span> | <span style="color:#1a73e8">Merge pull request #2 from PrismaXAI/feature/upload-jobs</span> |

> <span style="color:#1a73e8">`8aaa744` 为 merge commit，实际代码改动均在 `d1c65bc` 中，无额外 diff。</span>  
> <span style="color:#1a73e8">统计：9 个文件，+313 / -8 行。</span>

---

## 2. 业务逻辑

本次变更实现了两个相互独立、通过 `order_id` 关联的功能模块：

### 2.1 Upload Jobs（数据采集任务管理）

面向 **Admin** 管理 operator 的数据采集作业，面向 **Operator** 查看自己的任务进度。

#### 核心概念

- **Job（作业）**：Admin 为某 operator 分配的一批任务，包含一个或多个 task（如 Cable insertion、Table setting），每个 task 设置分配工时（`assigned_hours`）。
- **Task（任务类型）**：来自后端的 task catalog（`data_tasks` 表），operator 上传视频时选择对应 task，视频 episode 归属到该 job。
- **Episode（集）**：一次上传产生的视频片段；其处理状态映射到 job 的进度阶段。
- **Payment（付款记录）**：Admin 手动 mark paid，记录已付工时和金额；支持 void（撤销）。

#### Job 进度阶段

Episode 经过处理后归入以下阶段（用于 Job Detail Drawer 中的分布展示）：

| 阶段 key | 含义 | 触发条件 |
|----------|------|----------|
| `customer` | Customer accepted | `job_customer_review_status = 'accepted'`（当前不会触发，功能预留） |
| `qc` | QC accepted | episode 有 `qa_score`（已过 QC 审核） |
| `initial` | Initial accepted | status 为 `DERIVED_READY` / `DERIVED_PARTIALLY_READY` |
| `rejected` | Rejected | status 为 `DERIVED_VALIDATION_FAILED` / `FAILED` |

处于处理中（非 ready/failed）的 episode 不计入任何阶段。

这四项并不是 Episode 数据库中的一组独立状态，而是后端根据 Episode 的 `status`、QA 分数和客户审核状态实时计算出的互斥分类。同一个 Episode 在同一时刻只会计入一个阶段，后端的实际判定优先级如下：

| 优先级 | Dashboard 阶段 | 判定规则 |
|------:|-------------------|----------|
| 1 | Rejected | `status` 为 `DERIVED_VALIDATION_FAILED` 或 `FAILED` |
| 2 | Customer accepted | 未失败，且 `job_customer_review_status = 'accepted'` |
| 3 | QC accepted | 未失败、未被客户接收，且 `qa_score IS NOT NULL` |
| 4 | Initial accepted | 无上述条件，且 `status` 为 `DERIVED_READY` 或 `DERIVED_PARTIALLY_READY` |
| — | 不计入阶段统计 | Episode 仍在上传或处理中，尚未 ready，也未失败 |

典型状态转换：

```text
上传或处理中
   ├─ 初步处理成功 ──────────────> Initial accepted
   └─ 处理或校验失败 ────────────> Rejected

Initial accepted
   ├─ 完成 QC 并产生 qa_score ───> QC accepted
   └─ 后续被判定失败 ────────────> Rejected

QC accepted
   ├─ 客户审核通过 ──────────────> Customer accepted
   └─ 后续被判定失败 ────────────> Rejected
```

转换规则说明：

- 四个阶段的数字是当前快照，不是累计漏斗。例如一个 Episode 从 Initial accepted 转为 QC accepted 后，Initial 数量减 1，QC 数量加 1。
- Rejected 的优先级最高。只要底层 `status` 是失败状态，即使已经存在 `qa_score` 或客户审核结果，仍然显示为 Rejected。
- QC accepted 当前只判断是否存在 `qa_score`，不判断分数是否达到某个阈值。
- Customer accepted 是预留阶段；当前尚未提供实际客户审核写入流程，因此该数字通常保持为 0。
- Rejected Episode 如果被修复并恢复为 ready，阶段会根据现有字段重新计算：存在 `qa_score` 时进入 QC accepted，否则进入 Initial accepted；客户审核功能启用后，已被客户接收的 Episode 会进入 Customer accepted。

示例：

```text
Customer accepted   0
QC accepted         0
Initial accepted   18
Rejected            0
```

以上表示 18 个 Episode 已通过初步处理，但尚未产生 QA 分数；没有 Episode 处理失败，也没有 Episode 进入客户接收阶段。

#### 付款计算逻辑

`compute_payment_breakdown(hours_logged, rate, prior_payments)`：
- 已付工时 = 所有未 void 的 payment 的 `total_hours` 之和
- 待付工时 = max(0, hours_logged − 已付工时)
- 本次应付金额 = 待付工时 × 当前 rate（历史付款金额不受 rate 修改影响）
- `amount_earned_total` = 历史已付金额 + 当前待付金额

#### Payment Void（撤销付款）

- void 不删除记录，仅写 `voided_at` + `voided_by_admin_id`
- 被 void 的记录退出所有聚合计算，对应的 hours/episodes 重新变为"待支付"状态
- 用于审计追踪完整保留

#### Order ID 关联

`data_jobs.order_id` 字段关联 `data_orders.id`，纯用于内部追踪，对 operator 不可见（仅 admin mode 返回）。

#### <span style="color:#1a73e8">SDK 集成（`sdk-vla-foundry`，commit `d1c65bc`）</span>

<span style="color:#1a73e8">SDK 同步新增了对 job 的查询与绑定能力，统计：9 个文件，+313 / -8 行。</span>

<span style="color:#1a73e8">**核心能力：**</span>
<span style="color:#1a73e8">1. `prismax.list_jobs()` / CLI `prismax jobs` — 查询已分配给本账号的 jobs（需 `pxu_` upload API key）</span>
<span style="color:#1a73e8">2. 上传时可选传入 `job_id` — 创建 upload session 时告知后端本次上传属于哪个 Job</span>
<span style="color:#1a73e8">3. **向后兼容** — `job_id` 完全可选，不传时行为与改动前一致</span>

<span style="color:#1a73e8">**分层改动：**</span>

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| <span style="color:#1a73e8">`prismax/jobs.py`</span> | <span style="color:#1a73e8">新增</span> | <span style="color:#1a73e8">`list_jobs()` 公开 API</span> |
| <span style="color:#1a73e8">`prismax/client.py`</span> | <span style="color:#1a73e8">修改</span> | <span style="color:#1a73e8">`create_upload_session` 支持 `job_id`；新增 `list_jobs()` 调用 `GET /v1/data/jobs`</span> |
| <span style="color:#1a73e8">`prismax/upload.py`</span> | <span style="color:#1a73e8">修改</span> | <span style="color:#1a73e8">`upload()` / `create_upload_session()` 透传 `job_id`</span> |
| <span style="color:#1a73e8">`prismax/data_upload.py`</span> | <span style="color:#1a73e8">修改</span> | <span style="color:#1a73e8">JSON spec 可选字段 `"job_id"` 解析、整数校验、`DataUpload.job_id` 只读属性</span> |
| <span style="color:#1a73e8">`prismax/cli.py`</span> | <span style="color:#1a73e8">修改</span> | <span style="color:#1a73e8">新增 `jobs` 子命令（输出格式：`id \| due_date \| rate \| tasks`）；`upload` / `upload-data` 增加 `--job-id`</span> |
| <span style="color:#1a73e8">`prismax/__init__.py`</span> | <span style="color:#1a73e8">修改</span> | <span style="color:#1a73e8">导出 `list_jobs`</span> |
| <span style="color:#1a73e8">`README.md`</span> | <span style="color:#1a73e8">修改</span> | <span style="color:#1a73e8">补充 job_id 获取方式、JSON/Python/CLI 示例</span> |

<span style="color:#1a73e8">**`job_id` 传入方式与优先级：** Python 函数参数 `job_id=` > JSON spec 中 `"job_id"` > 不传（NULL）；CLI `--job-id` 可覆盖 spec 值；类型须为整数，`bool` 会被拒绝。</span>

> <span style="color:#1a73e8">⚠️ `list_jobs()` 要求 `pxu_` 前缀 upload key，download key 本地即拒；仅 SDK 上传可写 `job_id`，Web 端上传不支持（见联动问题 L-01）。</span>

---

### 2.2 Order Management（生产订单管理）

面向 **企业客户（Organization Owner）** 下单并追踪执行进度，面向 **Admin** 审批定价、推进状态、开具发票。

#### 实体层级

```
data_organizations (企业组织)
  └─ data_organization_members (成员，owner/member 角色)
  └─ data_organization_invitations (邀请 token)
  └─ data_orders (生产订单)
       └─ data_order_items (任务类型 + 工时需求)
       └─ data_order_history (状态变更事件日志)
  └─ data_invoices (发票，跨多个 order 合并开具)
```

#### 订单状态机

```
draft ──[submit by owner]──► submitted
                                 │
                    [admin approve, rate unchanged]──► production
                                 │
                    [admin approve, rate changed / admin create with rate]
                                 ▼
                          pending_approval
                                 │
                    [owner approve]──► production
                                            │
                               [admin mark-delivering]──► delivering
                                                               │
                                              [admin complete]──► complete

任意 {draft, submitted, pending_approval} ──[cancel]──► cancelled
```

#### 各角色可执行的操作

| 状态 | Owner 可执行 | Admin 可执行 |
|------|-------------|-------------|
| draft | edit, submit, cancel | — |
| submitted | edit, cancel | edit, approve, cancel |
| pending_approval | approve, edit, cancel | edit, cancel |
| production | — | mark_delivering |
| delivering | — | complete |
| complete | — | — |
| cancelled | — | — |

#### 发票逻辑

- 仅 status=`complete` 且无发票的订单可被开票
- 同一张发票可合并多个 order（必须同一 organization）
- Admin 上传 PDF 附件（最大 25MB，验证文件签名 `%PDF-`），关联 order_ids，写 `data_invoices`
- 发票状态：`issued` → `paid`（admin mark-paid 后）
- Organization owner 可下载发票 PDF（通过 signed URL）

---

## 3. Data Flow

### 3.1 Upload Jobs 数据流

```
[Operator 前端 /data/upload]
    │
    │ 1. hashchange 监听 #<task_id>，自动打开 UploadInfoModal
    │
    │ 2. 上传视频 episode，upload 行携带 job_id（SDK 通过 /v1/data/jobs 获取）
    │
    ▼
[data_uploads] ──job_id──► [data_jobs]
    │
    │ 3. worker 处理 MCAP，写 data_episodes（status, video_duration_hours, qa_score）
    ▼
[data_episodes]
    │
    │ 4. Admin 查看 job 详情 → GET /data/admin/jobs/<id>/episodes
    │    → jobs_helper.stage_for_episode() 分桶聚合
    │
    │ 5. Admin mark paid → POST /data/admin/jobs/<id>/payments
    │    → compute_payment_breakdown() 计算 outstanding
    │    → 写 data_job_payments
    │
    │ 6. Admin void → POST /data/admin/jobs/<id>/payments/void
    │    → 写 voided_at，重新开放对应 hours
    ▼
[data_job_payments]
```

**前端 AssignedJobsSection 数据流：**

```
mount / isAdminMode
  │
  ├─ fetchJobs()          GET /data/jobs (operator)
  │                       GET /data/admin/jobs?user_id=X (admin)
  │                       → jobs[] + summary{}
  │
  ├─ fetchTaskCatalog()   GET /data/tasks  (admin only，供 job 表单下拉)
  │
  ├─ handleRowClick()     → JobDetailDrawer
  │                           GET /data/[admin/]jobs/<id>/episodes
  │
  ├─ setFormJob(null)     → JobFormModal (create)   POST /data/admin/jobs
  ├─ setFormJob(job)      → JobFormModal (edit)     PATCH /data/admin/jobs/<id>
  ├─ setDeletingJob()     → JobDeleteModal          DELETE /data/admin/jobs/<id>
  ├─ markPaid()           → POST /data/admin/jobs/<id>/payments
  └─ setUnmarkingJob()    → UnmarkPaymentsModal
                              GET /data/admin/jobs/<id>/payments
                              POST /data/admin/jobs/<id>/payments/void
```

**<span style="color:#1a73e8">SDK 上传路径数据流（`sdk-vla-foundry`）：</span>**

```
[Operator / 自动化脚本]
    │
    │ 1. prismax.list_jobs()  或  prismax jobs
    │    GET /v1/data/jobs（需 pxu_ upload API key）
    │    返回：[{job_id, due_date, rate_usd_per_hour, tasks[{task_id, task_name, assigned_hours}]}]
    │
    │ 2. 选择 job_id 及该 job 下对应的 task
    │
    │ 3. 上传时传入 job_id（三选一，优先级：参数 > JSON spec > 不传）：
    │    - prismax.upload(..., job_id=42)
    │    - prismax_upload.json 中 "job_id": 42
    │    - prismax upload ./data --job-id 42
    │
    ▼
POST /v1/data/upload-sessions
  body: {task_id, serial_number, files, job_id?}  ← job_id 为 None 时不含该字段
    │
    ▼
[data_uploads.job_id] ──► [data_jobs]
    │
    │ 4. episode 处理完成后，hours_logged 在 Job 上累计
    ▼
[Operator Dashboard Jobs 表格 / Admin Job Detail Drawer]
```

### 3.2 Order Management 数据流

```
[Admin 前端 AdminPortal → Orders Tab → OrderAdminDashboard]
    │
    ├─ 加载    GET /api/admin/organizations
    │          GET /api/admin/orders?organization_id=&status=
    │          GET /api/admin/invoices?organization_id=
    │
    ├─ 创建订单  POST /api/admin/organizations/<id>/orders
    │            → status: submitted (无 rate) / pending_approval (有 rate)
    │
    ├─ 审批    POST /api/admin/orders/<ref>/approve {hourly_rate}
    │          → rate 不变: production；rate 变: pending_approval
    │
    ├─ 推进    POST /api/admin/orders/<ref>/mark-delivering
    │          POST /api/admin/orders/<ref>/complete
    │
    ├─ 开票    POST /api/admin/invoices (multipart PDF + order_ids)
    │          POST /api/admin/invoices/<ref>/mark-paid
    │
    └─ 取消    POST /api/admin/orders/<ref>/cancel {confirmed: true}

[Organization Owner 前端]
    │
    ├─ GET /api/orders
    ├─ POST /api/orders (draft)
    ├─ POST /api/orders/<ref>/submit
    ├─ POST /api/orders/<ref>/approve  (accept rate proposed by admin)
    ├─ POST /api/orders/<ref>/cancel
    └─ GET /api/invoices / GET /api/invoices/<ref>/download
```

---

## 4. API 端点列表

### 4.1 Upload Jobs API（`app_prismax_data_pipeline`）

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| `GET` | `/data/tasks` | gateway token | 获取 task catalog（任务类型列表，供 job 表单下拉） |
| `GET` | `/data/jobs` | gateway token (operator) | 获取当前 operator 的所有 jobs + summary |
| `GET` | `/data/admin/jobs?user_id=X` | admin JWT | 获取指定 operator 的所有 jobs（含 order_id） |
| `POST` | `/data/admin/jobs` | admin JWT | 创建 job，body: `{user_id, tasks[], rate_usd_per_hour, due_date, order_id?}` |
| `PATCH` | `/data/admin/jobs/<job_id>` | admin JWT | 编辑 job（tasks、rate、due_date、order_id）；不允许删除有上传记录的 task |
| `DELETE` | `/data/admin/jobs/<job_id>` | admin JWT | 软删除 job（清空关联 uploads 的 job_id） |
| `GET` | `/data/jobs/<job_id>/episodes` | gateway token (operator) | 获取本人 job 的 episode 明细 + stage_counts |
| `GET` | `/data/admin/jobs/<job_id>/episodes` | admin JWT | 获取任意 job 的 episode 明细 + stage_counts |
| `POST` | `/data/admin/jobs/<job_id>/payments` | admin JWT | 将当前 outstanding 标记为已付 |
| `GET` | `/data/admin/jobs/<job_id>/payments` | admin JWT | 列出 job 的所有有效（未 void）付款记录 |
| `POST` | `/data/admin/jobs/<job_id>/payments/void` | admin JWT | 撤销指定 payment，body: `{payment_ids: []}` |
| `GET` | `/v1/data/jobs` | Upload SDK API Key | SDK 获取 operator 的 jobs（仅含 job_id/due_date/rate/tasks_data） |

**关键请求/响应字段：**

`POST /data/admin/jobs` body：
```json
{
  "user_id": 123,
  "tasks": [{"task_id": 4, "assigned_hours": 8.0}],
  "rate_usd_per_hour": 18.50,
  "due_date": "2026-09-15",
  "order_id": 1044
}
```

`GET /data/jobs` response：
```json
{
  "success": true,
  "data": [{
    "job_id": 1,
    "assigned_user_id": 123,
    "created_at": "2026-08-25T...",
    "due_date": "2026-09-15",
    "rate_usd_per_hour": 18.5,
    "tasks": [{"task_id": 4, "task_name": "Cable insertion", "assigned_hours": 8.0}],
    "hours_assigned": 8.0,
    "hours_logged": 3.25,
    "amount_paid_total": 0.0,
    "amount_outstanding": 60.12,
    "amount_earned_total": 60.12,
    "last_payment_at": null
  }],
  "summary": {
    "job_count": 1,
    "hours_logged_total": 3.25,
    "hours_assigned_total": 8.0,
    "amount_earned_total": 60.12,
    "amount_outstanding_total": 60.12
  }
}
```

### 4.2 Order Management API（`app_prismax_user_management`）

#### Admin 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/admin/organizations` | 列出所有组织 |
| `GET` | `/api/admin/organizations/<id>` | 获取组织详情（含成员列表） |
| `POST` | `/api/admin/organizations` | 创建组织，body: `{name, owner_email}` |
| `POST` | `/api/admin/organizations/<id>/owners` | 添加 owner，body: `{owner_email}` |
| `GET` | `/api/admin/orders?organization_id=&status=` | 列出订单（支持过滤） |
| `GET` | `/api/admin/orders/<ORD-ref>` | 获取订单详情 |
| `POST` | `/api/admin/organizations/<id>/orders` | 创建订单 |
| `PATCH` | `/api/admin/orders/<ORD-ref>` | 编辑订单（draft/submitted/pending_approval） |
| `POST` | `/api/admin/orders/<ORD-ref>/approve` | 审批定价，body: `{hourly_rate}` |
| `POST` | `/api/admin/orders/<ORD-ref>/mark-delivering` | 标记为 Delivering |
| `POST` | `/api/admin/orders/<ORD-ref>/cancel` | 取消订单，body: `{confirmed: true}` |
| `POST` | `/api/admin/orders/<ORD-ref>/complete` | 标记完成，body: `{confirmed: true}` |
| `GET` | `/api/admin/invoices?organization_id=` | 列出发票 |
| `POST` | `/api/admin/invoices` | 开具发票（multipart: order_ids + PDF file） |
| `POST` | `/api/admin/invoices/<INV-ref>/mark-paid` | 标记发票已付，body: `{confirmed: true}` |

#### Organization Owner 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/api/organization` | 获取本组织信息 |
| `POST` | `/api/organization/invitations` | 创建邀请，body: `{email}` |
| `DELETE` | `/api/organization/invitations/<id>` | 撤销邀请 |
| `POST` | `/api/organization/invitations/accept` | 接受邀请，body: `{token}` |
| `DELETE` | `/api/organization/members/<user_id>` | 移除成员 |
| `GET` | `/api/orders?status=` | 列出本组织订单 |
| `GET` | `/api/orders/data-sources` | 获取 complete 订单作为 My Data 数据源 |
| `GET` | `/api/orders/<ORD-ref>` | 获取订单详情 |
| `POST` | `/api/orders` | 创建 draft 订单 |
| `PATCH` | `/api/orders/<ORD-ref>` | 编辑 draft/submitted 订单 |
| `POST` | `/api/orders/<ORD-ref>/submit` | 提交订单（draft → submitted） |
| `POST` | `/api/orders/<ORD-ref>/approve` | 接受 admin 定价（pending_approval → production） |
| `POST` | `/api/orders/<ORD-ref>/cancel` | 取消订单 |
| `GET` | `/api/invoices` | 列出本组织发票 |
| `GET` | `/api/invoices/<INV-ref>/download` | 获取发票 PDF 下载链接（signed URL） |


---

## 5. 数据库变更

### 5.1 Upload Jobs（`app_prismax_data_pipeline/sql/`）

**`20260824_data_jobs_v1.sql`**（主 schema）：
```sql
data_jobs              -- job 主表
  job_id, assigned_user_id, created_by_admin_id, rate_usd_per_hour, due_date
  tasks_data JSONB     -- [{task_id, assigned_hours}, ...]（从单独表重构合并入此）
  order_id             -- 关联 data_orders.id（可选）
  deleted_at           -- 软删除

data_job_payments      -- 付款记录（追加型账本）
  job_payment_id, job_id, rate_usd_per_hour_snapshot
  total_hours, total_amount_usd
  included_episode_ids JSONB   -- GIN 索引
  marked_by_admin_id, paid_at

data_uploads           -- 新增 job_id 外键列
data_episodes          -- 新增 job_customer_review_status 列（预留）
```

**`20260827_data_job_payments_void.sql`**（void 支持）：
```sql
ALTER TABLE data_job_payments
  ADD COLUMN voided_at TIMESTAMPTZ,
  ADD COLUMN voided_by_admin_id BIGINT;
-- 活跃付款部分索引：WHERE voided_at IS NULL
```

### 5.2 Order Management（`app_prismax_user_management/order_management/sql/`）

**`20260825_data_order_management_v1.sql`**（手动执行，Cloud Build 不自动运行）：
```sql
data_organizations           -- 企业组织
data_organization_members    -- 成员（owner/member 角色）
data_organization_invitations -- 邀请（token_hash，带 expires_at）
data_orders                  -- 生产订单（status 状态机，hourly_rate_usd_cents）
                             -- id 序列从 1044 起始
data_order_items             -- 订单任务条目（name, requested_hours, is_custom）
data_order_history           -- 事件日志（event_type, actor_type, actor_id, details）
data_invoices                -- 发票（order_ids[], file_object_key, amount_usd_cents）
                             -- id 序列从 2208 起始
```

---

## 6. 前端组件变更

### 6.1 新增组件

| 组件/文件 | 位置 | 功能 |
|----------|------|------|
| `AssignedJobsSection` | `src/components/Data/UploadDashboard/` | Operator 查看己方 jobs；Admin 管理 jobs |
| `JobDetailDrawer` | 同上（inline） | 滑出抽屉显示 job 的 episode 明细 + 阶段分布 |
| `JobFormModal` | 同上（inline） | 创建/编辑 job 表单 |
| `JobDeleteModal` | 同上（inline） | 软删除确认（有日志数据时显示警告） |
| `UnmarkPaymentsModal` | 同上（inline） | 列出活跃付款，选择性 void |
| `OrderAdminDashboard` | `src/components/Admin/Orders/` | Admin 订单管理界面（Orders/Organizations/Invoices 三 Tab） |
| `orderAdminApi.js` | 同上 | Admin 端订单 API 客户端（含 OrderAdminApiError 错误类） |

### 6.2 修改组件

| 组件/文件 | 修改说明 |
|----------|----------|
| `UploadDashboard.js` | 移至 `UploadDashboard/` 子目录，集成 `AssignedJobsSection` |
| `DataHub.js` | 更新 `UploadDashboard` 的 import 路径 |
| `Upload.js` | 新增 hash URL 支持：`/data/upload#<task_id>` 自动打开对应 task 的上传弹窗 |
| `AdminPortal.js` | 新增 `Orders` Tab，渲染 `OrderAdminDashboard` |

---

## 7. 测试分析

### 7.1 已有单元测试

**前端（`app-prismax-rp`）：**
- `OrderAdminDashboard.test.js`：仅覆盖 Organizations Tab 打开成员卡片场景（1 case）
- `orderAdminApi.test.js`：API 客户端方法测试（mock fetch）

**后端（`app-prismax-rp-backend`）：**
- `jobs_helper.py` 的 helper 函数（`compute_payment_breakdown`、`stage_for_episode` 等）**无专项单元测试**
- `order_management/tests/`：routes / domain / auth / schema_contract 四类测试已覆盖 Order Management 状态机

<span style="color:#1a73e8">**SDK（`sdk-vla-foundry`，commit `d1c65bc`，+200 行）：**</span>
<span style="color:#1a73e8">- `test_data_upload.py`：`job_id` spec 解析、校验、session 传参</span>
<span style="color:#1a73e8">- `test_upload_helpers.py`：client body、`list_jobs` 端点、CLI、upload 透传</span>
<span style="color:#1a73e8">- 缺失：与真实后端的集成测试；`job_id` 业务校验（task 归属、跨 operator）需 E2E 手工验证</span>

### 7.2 测试空白（高风险）

| 模块 | 缺失的测试 |
|------|-----------|
| `jobs_helper.compute_payment_breakdown` | void 后重新计算；rate 变更后历史不重算 |
| `admin_create_job` | order_id 存在性校验；operator 角色校验 |
| `admin_update_job` | 移除有上传记录的 task（应返回 409） |
| `admin_void_job_payments` | 跨 job 的 payment_ids 不允许 void |
| `AssignedJobsSection` | 前端组件无任何自动化测试 |
| `Upload.js hash URL` | hash 变更触发 modal 无测试 |
| Invoice PDF 上传 | 文件签名验证、大小限制 |

---

## 8. E2E 测试用例

| TC ID | 模块 | 角色 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
|-------|------|------|----------|----------|----------|-------------|-------------|
| TC-J-01 | Upload Jobs | Operator | 账号已被 admin 分配 ≥1 个 active job | 登录 → 进入 `/data/upload` → 切换到 UploadDashboard | Jobs 表格展示：Job ID、Task chips、Rate、Hours logged（进度条）、Amount（金额+支付状态）、Assigned date、Due date；Summary 行展示汇总；无 Actions 列 | 无 job 时显示 "No jobs assigned yet." | |
| TC-J-02 | Upload Jobs | Operator | 至少 1 个 job 存在 | 点击任意 job 行 | 右侧弹出 JobDetailDrawer，展示 episode 列表、阶段分布（Customer/QC/Initial/Rejected 数量）和堆积进度条 | 无 episode 时显示 "No episodes recorded against this job yet." | |
| TC-J-03 | Upload Jobs | Operator | task_id=4 在 operator 可用 tasks 中 | 直接访问 `/data/upload#4` | 页面加载后自动打开 task_id=4 的 UploadInfoModal | `#999`（不存在）→ 无弹窗无报错；同一 hash 重复触发 → 不重复打开 | |
| TC-J-04 | Upload Jobs | Operator | job 有 due_date | 查看 Jobs 表格的 Due date 列 | 超期 → 红色 "Overdue by X days"；≤7天 → 橙色 "X days left"；今天 → "Due today"；正常 → 绿色 "X days left" | due_date 为空 → 显示 "—" | |
| TC-J-10 | Upload Jobs | Admin | 在 admin mode 查看某 operator 的 dashboard | 点击 "+ New job" → 选择 task、填写 assigned_hours > 0、rate ≥ 0、due_date ≥ 今天 → Save | job 出现在列表，显示实际 job_id；`order_id` 留空时 job 行无 ORD 徽章 | due_date < 今天 → "Due date falls before the assigned date."；rate 负数 → 报错；未选 task → "Pick a task and give it hours above zero."；同一 task 重复添加 → 下拉 disabled | |
| TC-J-11 | Upload Jobs | Admin | 已存在有效 order_id | 创建 job 时填写已存在的 Order ID | 创建成功，job 行显示 "ORD-XXXX" 徽章 | 填写不存在的 order_id → 后端 400，前端显示错误 | |
| TC-J-12 | Upload Jobs | Admin | job 存在且未删除 | 点击 "Edit" → 修改 rate / due_date → Save | 列表实时更新新值 | 移除有上传记录的 task → 后端 409 "Can't remove a task that already has uploads under this job." | |
| TC-J-13 | Upload Jobs | Admin | job 有 outstanding amount（pay = unpaid / partial） | 点击 "Mark paid" | Amount 状态变为 "Paid <日期>"，outstanding = 0 | outstanding = 0 → "Mark paid" 按钮不显示；连续两次 mark paid → 后端 400 "Nothing outstanding to pay on this job." | |
| TC-J-14 | Upload Jobs | Admin | job 已有付款（pay = paid / partial） | 点击 "Unmark" → UnmarkPaymentsModal → 全选 → 确认 | outstanding 恢复全额，pay 状态回到 "Earned — not paid" | 仅 void 部分 → 仅该部分重新变为 outstanding；无活跃 payment → "No active payments to unmark." | |
| TC-J-15 | Upload Jobs | Admin | job 存在 | 点击 "Delete" → 确认弹窗 | job 从列表消失；关联 uploads 的 job_id 清空（QA 数据保留） | job 有 logged hours → 弹窗显示 "X logged hours are attached…" 警告，需二次确认 | |
| TC-J-16 | Upload Jobs | Admin | job 含多个 episode，包含 rejected | 点击 job 行 → Drawer → 切换阶段过滤器为 "Rejected" | 仅展示 rejected episodes；显示 `processing_error.error_message` | 切换过滤器 → expandedId 重置（展开详情收起） | |
| TC-O-01 | Order Mgmt | Admin | 目标 owner email 存在于 users 表 | Organizations Tab → 输入名称、owner email → 创建 | 列表出现新 Organization；owner 用户获得 owner 角色 | email 不存在 → 后端报错 | |
| TC-O-02 | Order Mgmt | Admin | 组织已存在 | 点击组织 → View members | 弹出 Modal 展示 email、角色（Owner/Member）、user_id、joined_at | 无成员 → 显示 "No organization members." | |
| TC-O-03 | Order Mgmt | Admin | 组织已存在 | 创建订单：选组织 + tasks + hours + due_date，**不填** hourly_rate → 创建 | status = `submitted` | **填写** hourly_rate → status = `pending_approval`（等 owner 确认） | |
| TC-O-04 | Order Mgmt | Admin | 订单 status = submitted，已有 rate | 点击 Approve，rate 字段填入与订单**相同**的值 | status 变为 `production`，allowed_actions 含 `mark_delivering` | rate 不同 → status 变为 `pending_approval` | |
| TC-O-05 | Order Mgmt | Admin | 订单 status = submitted | Approve 时填入**不同** rate | status 变为 `pending_approval`，等待 owner 接受新 rate | — | |
| TC-O-06 | Order Mgmt | Admin | 订单 status = production | mark-delivering → status = delivering → complete（含 confirmed=true） | status 依次正确变更；complete 后 allowed_actions 为空 | delivering 状态下调用 complete 缺少 confirmed → 后端 409 | |
| TC-O-07 | Order Mgmt | Admin | 订单处于 draft / submitted / pending_approval | 点击 Cancel → 确认对话框 | status 变为 `cancelled` | production / delivering / complete → "This order can no longer be cancelled" | |
| TC-O-08 | Order Mgmt | Admin | ≥1 个 status=complete 且无发票的订单 | Invoices Tab → 勾选 order → 上传 PDF → Attach PDF & issue | 发票列表出现新行，status = `issued` | 跨 organization 选 order → UI 限制同组织；上传非 PDF → 400；PDF > 25MB → 413 | |
| TC-O-09 | Order Mgmt | Admin | 发票 status = issued | 点击 Mark paid | status 变为 `paid`，显示 paid_at 日期 | — | |
| TC-O-20 | Order Mgmt | Owner | 已属于某 organization | My Data / Orders → New order → 填写 tasks/hours/due_date → Save → Submit | status 从 `draft` 变为 `submitted` | due_date 为空 → 保存报错 | |
| TC-O-21 | Order Mgmt | Owner | Admin 更改 rate 后订单变为 pending_approval | Owner 点击 Approve | status 变为 `production` | admin 未设置 rate → 后端 409 "the admin must set a rate before owner approval" | |
| TC-O-22 | Order Mgmt | Owner | 组织有已开票的发票 | Invoices → 点击下载 | 获取 signed URL，跳转或触发 PDF 下载 | 下载其他组织发票 → 404 | |
| TC-O-23 | Order Mgmt | Owner | 订单 status = complete | 进入 My Data → 数据源下拉 | `GET /api/orders/data-sources` 返回该订单作为可选数据源 | status ≠ complete → 不出现在数据源列表 | |
| TC-ERR-01 | Upload Jobs | — | gateway token 已过期 | 访问 `/data/jobs` | 返回 401，前端跳转登录 | — | |
| TC-ERR-02 | Upload Jobs | — | admin token 已过期 | 调用任意 jobs admin API | 返回 401，前端触发 `ADMIN_SESSION_EXPIRED_EVENT` | — | |
| TC-ERR-03 | Upload Jobs | Admin | job logged hours = 0 | 点击 "Mark paid" | 后端返回 400 "Nothing outstanding to pay" | — | |
| TC-ERR-04 | Upload Jobs | Admin | payment_id 属于其他 job | POST `/data/admin/jobs/<id>/payments/void` 含跨 job 的 id | 跨 job 的 id 静默跳过（voided_count=0），job 数据不变 | — | |
| TC-ERR-05 | Upload Jobs | Admin | user_id 对应非 operator 角色 | 创建 job 时使用该 user_id | 后端返回 400 "user is not an operator" | — | |
| TC-ERR-06 | Order Mgmt | Admin | — | 创建订单时 spec_link 填写非 http/https URL | 后端返回 400 "spec_link must be a valid http or https URL" | — | |
| TC-ERR-07 | Order Mgmt | Admin | — | 创建订单时 task hours = 0 | 后端返回 400 "task hours must be greater than zero" | — | |
| TC-ERR-08 | Order Mgmt | Admin | — | 上传发票时文件无 `%PDF-` 签名 | 后端返回 400 "the uploaded file is not a valid PDF" | — | |
| TC-ERR-09 | Order Mgmt | Admin | order 已有发票 | 在 Invoices Tab 尝试再次选取该 order | UI 过滤（`!order.invoice`），已有发票的 order 不出现在选择列表 | — | |

<span style="color:#1a73e8">**SDK 上传集成测试（`sdk-vla-foundry` 新增，前置：Operator 持 `pxu_` upload API key，Admin 已创建至少 1 个 active job）**</span>

| TC ID | 模块 | 角色 | 前提条件 | 操作步骤 | 预期结果 | 边界 / 异常 | Test Result |
|-------|------|------|----------|----------|----------|-------------|-------------|
| <span style="color:#1a73e8">TC-SDK-01</span> | SDK / list_jobs | Operator | 已被分配 ≥1 个 job，使用 `pxu_` upload API key | Python: `prismax.list_jobs()` | 返回 list，每项含 `job_id`、`due_date`、`rate_usd_per_hour`、`tasks`（含 `task_id`、`task_name`、`assigned_hours`） | 无 job 时返回空 list `[]` | |
| <span style="color:#1a73e8">TC-SDK-02</span> | SDK / list_jobs | Operator | 同上 | CLI: `prismax jobs` | 每行输出 `job_id \| due_date \| rate \| task_names` | 多 task 时 task_names 以逗号分隔 | |
| <span style="color:#1a73e8">TC-SDK-03</span> | SDK / list_jobs | Operator | 同上 | CLI: `prismax jobs --json` | 输出完整 JSON 数组，与 API 原始响应一致 | — | |
| <span style="color:#1a73e8">TC-SDK-04</span> | SDK / list_jobs | Operator | 使用 download API key（`pxa_` 前缀） | `prismax.list_jobs(api_key="pxa_...")` | SDK 本地抛出 `PrismaxAuthError`，未到达后端 | — | |
| <span style="color:#1a73e8">TC-SDK-05</span> | SDK / list_jobs | Operator | API key 无效或过期 | 调用 `list_jobs()` | 后端返回 401/403，SDK 抛出 `PrismaxAuthError` | — | |
| <span style="color:#1a73e8">TC-SDK-10</span> | SDK / upload | Operator | job 含已知 `task_id`，使用匹配 `scenario` | `prismax.upload(folder, scenario="...", serial_number="...", job_id=<id>)` | upload session 创建成功；后端 `data_uploads.job_id` = 传入值 | 不传 `job_id` → `data_uploads.job_id` 为 NULL | |
| <span style="color:#1a73e8">TC-SDK-11</span> | SDK / upload | Operator | 同上 | CLI: `prismax upload ./data --scenario "..." --serial-number "..." --job-id <id>` | 上传成功，`job_id` 写入 DB | — | |
| <span style="color:#1a73e8">TC-SDK-12</span> | SDK / upload-data | Operator | `prismax_upload.json` 含 `"job_id": 42` | `prismax upload-data ./prismax_upload.json` | 请求 body 含 `job_id: 42` | spec 无 `job_id` 字段 → body 不含该字段 | |
| <span style="color:#1a73e8">TC-SDK-13</span> | SDK / upload-data | Operator | JSON spec 含 `"job_id": 42` | `prismax upload-data spec.json --job-id 7` | 实际使用 `job_id=7`（CLI 参数覆盖 spec） | Python `create_upload_session(data_upload, job_id=7)` 同理 | |
| <span style="color:#1a73e8">TC-SDK-14</span> | SDK / upload | Operator | 任意有效上传数据 | `prismax.upload(...)` 不传 `job_id` | 上传成功；请求 body **不含** `job_id` 字段；行为与旧版 SDK 一致 | — | |
| <span style="color:#1a73e8">TC-SDK-20</span> | SDK / validation | — | — | JSON spec 中 `"job_id": "not-a-number"` | SDK 本地抛出 `PrismaxValidationError: job_id must be an integer` | `"job_id": true`（bool）→ 同样拒绝 | |
| <span style="color:#1a73e8">TC-SDK-21</span> | SDK / validation | Operator | — | 上传时传入不存在的 `job_id`（如 99999） | 后端返回 4xx | — | |
| <span style="color:#1a73e8">TC-SDK-22</span> | SDK / validation | Operator | job 仅含 task_id=4 | `job_id` 正确但 `scenario` 不属于该 job 的 tasks | 后端返回 4xx（task 不在 job 范围内）；SDK 不预校验 | — | |
| <span style="color:#1a73e8">TC-SDK-23</span> | SDK / validation | Operator B | job 属于 Operator A | 用 B 的 API key 上传并传入 A 的 `job_id` | 后端返回 403/404 | — | |
| <span style="color:#1a73e8">TC-SDK-30</span> | SDK / E2E | Operator | Admin 已创建 job（含 task + rate + due_date） | 1. `prismax.list_jobs()` 获取 `job_id` 和 tasks<br>2. SDK 上传传入 `job_id` + 匹配 `task_id`<br>3. 等 episode 处理完成<br>4. 查看 Dashboard Jobs 表格 | `hours_logged` 累计；JobDetailDrawer 显示 episode 明细和阶段分布 | — | |
| <span style="color:#1a73e8">TC-SDK-32</span> | SDK / E2E | Operator | job 有 outstanding amount，hours 已累计 | Admin 点击 "Mark paid" | payment 金额 = outstanding hours × rate；Dashboard 状态更新 | — | |
| <span style="color:#1a73e8">TC-SDK-33</span> | SDK / E2E | Operator | job 已关联 `order_id` | SDK 上传完成后 Admin 查看 job 行 | ORD 徽章显示；`data_orders.status` 不自动推进（见 L-08） | — | |
| <span style="color:#1a73e8">TC-SDK-40</span> | SDK / regression | Operator | 旧版上传脚本，不含 `job_id` 参数 | 使用新版 SDK 直接运行，不修改脚本 | 上传成功，行为与旧版一致 | — | |
| <span style="color:#1a73e8">TC-SDK-41</span> | SDK / regression | Operator | — | `prismax scenarios` | 返回 task catalog，不受 jobs 改动影响 | — | |
| <span style="color:#1a73e8">TC-SDK-42</span> | SDK / regression | Operator | 已有进行中的 upload session | `prismax resume` / `prismax status` | 功能正常，不受 `job_id` 改动影响 | — | |
| <span style="color:#1a73e8">TC-SDK-43</span> | SDK / regression | Operator | download API key | `prismax download` | download 流程不受影响 | — | |

---

## 9. 已知局限与注意事项

1. **Customer Review 阶段预留**：`data_episodes.job_customer_review_status` 列已创建，`JOB_STAGE_CUSTOMER` 已接入前端显示，但实际不会有 episode 进入该阶段，直至 customer-review 功能上线。
2. **tasks_data DB 重构**：初始版本使用 `data_job_tasks` 独立表，后续重构为 `data_jobs.tasks_data JSONB`。如果部署顺序不当，需先跑 SQL migration，否则 UPDATE 会失败。
3. **admin mode 的 hours_logged 截断**：summary 中 `hours_logged_total` 对每个 job 取 `min(hours_logged, hours_assigned)`，防止超额采集影响汇总；但单 job 行仍展示真实值。
4. **发票 PDF 存储**：使用 `invoice_storage.upload_pdf(pdf)`，如果对象存储写入成功但 DB 插入失败，会尝试清理 orphaned object，但清理失败时仅记录 warning，不 rollback 存储。
5. **Order Management 部署手动**：`20260825_data_order_management_v1.sql` 备注"手动执行"，Cloud Build 不自动运行，需 DBA 或 ops 手动触发。
6. **Order Task 与 Operator Task 互不相通**：Owner 在 Order 中定义的 task 进入 production 后，不会自动出现在 Operator 上传界面，也不会自动出现在 Admin 创建 Job 的 task 下拉中。Admin 须手动在 `data_tasks` 中创建对应条目，再创建 Job 并关联 order_id。

---

## 10. Upload Jobs × Order Management 联动问题分析

### 10.1 Episode → Job 进度映射的实现现状

映射逻辑（`jobs_helper.stage_for_episode()`）代码已写，但**能否生效取决于上传路径**。

两条上传路径对 `job_id` 的处理完全不同：

| 上传路径 | 端点 | 传 `job_id`？ | `data_uploads.job_id` |
|----------|------|:---:|:---:|
| **Web 浏览器上传**（operator 在网页端操作） | `POST /data/upload-sessions` | ❌ 不支持 | ❌ 永远 NULL |
| **SDK 上传**（API Key，程序调用） | `POST /v1/data/upload-sessions` | ✅ 可选字段，有校验 | ✅ 写入（需主动传） |

**后果**：operator 通过网页端上传的所有视频，`data_uploads.job_id = NULL`，导致：
- `hours_logged` 永远为 0
- JobDetailDrawer 的 episode 列表永远为空，阶段分布全为 0
- `amount_earned_total = 0`，Mark paid 按钮无法产生实际意义

**SDK 路径的额外限制**：SDK 不强制要求传 `job_id`（可选），需要 SDK 调用方主动查 `GET /v1/data/jobs` 并在每次上传时带上正确的 `job_id`，否则同样是 NULL。

---

### 10.2 联动问题汇总

| 编号 | 问题 | 影响范围 | 风险 |
|------|------|----------|------|
| **L-01** | **Web 上传不写 `job_id`**：`POST /data/upload-sessions` 的 INSERT 没有 `job_id` 字段；网页端上传的 episode 永远不归入任何 job | `hours_logged`、episode 明细、payment 全部失效 | 🔴 高 |
| **L-02** | **SDK 上传的 `job_id` 需手动传入**：`/v1/data/upload-sessions` 中 `job_id` 是可选字段，SDK 调用方若不主动传，结果与 Web 上传相同 | 同 L-01 | 🔴 高 |
| **L-03** | **task_id 归属校验仅在 SDK 路径**：Web 路径上传时不校验所选 task 是否属于该 job，operator 可上传任意 task 的视频而不被约束到 job 范围 | 数据归属混乱 | 🟡 中 |
| **L-04** | **Order 进入 `production` 不自动创建 Job**：两套系统完全独立，Admin 必须手动进入 Operator Dashboard → 创建 Job → 关联 order_id | 操作依赖人工，易遗漏 | 🔴 高 |
| **L-05** | **Task Catalog 与 Order Items 不同步**：`data_order_items`（Order 里的 task 名称）与 `data_tasks`（Job 表单的 task 下拉）是两张独立的表，Admin 还需手动在 `data_tasks` 新增条目，custom task 更无法自动映射 | 操作步骤多，易出错 | 🟡 中 |
| **L-06** | **Rate 双轨独立**：`data_orders.hourly_rate_usd_cents`（客户侧定价）和 `data_jobs.rate_usd_per_hour`（operator 工资）各填各的，无任何同步或校验，两者可以完全不一致 | 财务对账困难 | 🟡 中 |
| **L-07** | **Due date 双轨独立**：同上，`data_orders.due_date` 和 `data_jobs.due_date` 互不关联 | 进度追踪断层 | 🟡 中 |
| **L-08** | **Job 完成不推进 Order 状态**：`hours_logged >= hours_assigned` 时前端显示"Complete"，但 `data_orders.status` 不会自动变为 `delivering` 或 `complete` | 交付流程需 Admin 手动推进 | 🟡 中 |
| **L-09** | **多个 Job 可关联同一 Order**：`data_jobs.order_id` 无 UNIQUE 约束，同一个 order 可被多个 job 关联，无防重机制 | 数据一致性风险 | 🟡 中 |
| **L-10** | **Operator 付款与客户发票完全隔离**：`data_job_payments`（operator 工资）和 `data_invoices`（客户开票金额）无任何字段关联，无法自动对比成本与收入 | 财务分析需手动 | 🟢 低（当前版本设计如此） |

---

### 10.3 当前正确的操作 SOP（全靠 Admin 手动桥接）

```
1. Order 进入 production（Admin 在 Admin Portal → Orders Tab 操作）
       ↓
2. Admin 手动去 data_tasks 确认 task catalog 中有对应条目
   （若 Order 含 custom task，需先插入 data_tasks）
       ↓
3. Admin Portal → Operators Tab → 找到目标 operator → "View Dashboard"
   → "+ New job" → 选 task → 填 rate（与 Order rate 保持一致）
   → 填 due_date（与 Order due_date 保持一致）
   → Order ID 字段填入 order id → "Create job"
       ↓
4. Operator 须通过 SDK（API Key）上传，且上传时主动传入 job_id
   （网页端上传无法建立 episode ↔ job 关联）
       ↓
5. Episode 处理完成后，hours_logged 才会累计，job 进度才会更新
       ↓
6. Admin 手动 mark paid → 手动推进 Order 状态至 delivering / complete
```

---

### 10.4 测试建议（针对联动问题）

| TC ID | 验证目标 | 操作 | 预期 / 当前实际 |
|-------|----------|------|-----------------|
| TC-LINK-01 | L-01：Web 上传后 job hours 不累计 | operator 通过网页端上传视频，episode 处理完成后查看 job | `hours_logged = 0`，episode 列表为空（当前实际行为） |
| TC-LINK-02 | L-02：SDK 上传不传 job_id，结果同 L-01 | SDK 调用 `/v1/data/upload-sessions` 不传 `job_id` | `hours_logged = 0` |
| TC-LINK-03 | L-02：SDK 上传传入 job_id，hours 正确累计 | SDK 调用时传入有效 `job_id` + 匹配的 `task_id`，episode 处理完成 | `hours_logged` 等于 episode 时长之和，Drawer 显示 episode 明细 |
| TC-LINK-04 | L-03：Web 上传不校验 task 归属 | operator 网页端选择不属于任何 job 的 task 上传 | 上传成功，无报错（设计如此，但 episode 不归入 job） |
| TC-LINK-05 | L-06：rate 不同步 | Admin 创建 job 时填入与 order 不同的 rate | 两侧各显示各自的值，无警告 |
| TC-LINK-06 | L-09：同一 order 关联多个 job | Admin 为同一 order_id 创建两个不同 job | 两个 job 均创建成功，`data_jobs` 中两行 `order_id` 相同 |

> <span style="color:#1a73e8">SDK 上传正向 E2E 及 mark paid / order 联动测试见 §8 TC-SDK-30 / TC-SDK-32 / TC-SDK-33。</span>
