# PRIS-325 Admin Portal — Operator Details Page

## 变更概述

### 前端（app-prismax-rp）

涉及文件：
- `src/components/Admin/VLAAdminOperatorApplications.js`（修改）
- `src/components/Admin/VLAAdminOperatorDetail.js`（新增）
- 对应 CSS Module 文件

#### 核心变更逻辑

**1. 已审批 Operator 行可点击 → 打开详情 Modal**
- `ApplicationsTable` 新增 `onOpenDetail` prop
- Approved 状态的行绑定 `onClick → openDetail(app)`，行样式添加 `rowClickable`，并渲染 `›` 指示符
- 按钮（Dashboard / Approve / Deny）均添加 `e.stopPropagation()`，防止触发行级点击

**2. Deny 操作返回值**
- `handleDeny` 从无返回值改为明确返回 `true`（成功）/ `false`（取消 / 异常），支持被 Detail Modal 感知操作结果

**3. VLAAdminOperatorDetail（新组件）**
- 接收 `userId / email / app / onClose / onDeny / onOpenDashboard`
- **Header 区**：邮箱、User ID、Approved pill、user_class pill、total_points
- **Stats 卡片**：Approved on、Episodes uploaded、Last upload、Active upload keys 数量
- **Registered robots 区**：展示机器人 manufacturer/model/serial_number，每条带 `Paired` pill
- **Upload API Keys 区**：
  - 列表：label、key（前缀 + 掩码）、创建时间、最近使用时间、状态（ACTIVE / REVOKED）
  - 对 ACTIVE key 显示 Delete 按钮 → 二次确认 Modal → 调用 DELETE API 吊销
  - "Create upload key" 按钮 → 填写 Label → 调用 POST API → 成功后显示一次性密钥 Modal（含 Copy 按钮）
- **顶部操作**：`Open dashboard`（跳至 UploadDashboard 并关闭 Detail）、`Deny operator`（调用 onDeny callback，成功后自动关闭 Modal）
- 所有嵌套 Modal 均有独立 overlay，点击空白区域可关闭（创建/吊销进行中时不可关闭）

### 后端（app-prismax-rp-backend）

#### app_prismax_data_pipeline/app.py — 新增 Admin Upload API Key 管理接口

| 接口 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 列举 Upload Keys | GET | `/data/admin/upload-api-keys?user_id=X` | 返回该用户所有 Upload Key（含 REVOKED） |
| 创建 Upload Key | POST | `/data/admin/upload-api-keys` | body: `{user_id, label}`；验证用户存在且为 Operator；返回完整 api_key（仅此一次） |
| 吊销 Upload Key | DELETE | `/data/admin/upload-api-keys/<id>?user_id=X` | 仅对 ACTIVE 状态的 key 操作；双重校验 key 属于该 user_id |
| Operator 统计 | GET | `/data/admin/operator-detail/stats?user_id=X` | 返回 total_episodes、last_upload_at |

#### app_prismax_user_management/app.py — 审批状态过滤逻辑修复

**问题**：原逻辑仅依赖 `data_operator_applications.admin_review_status` 过滤，当用户 role 在流程外被修改时会出现在错误 Tab。

**修复**：
- Approved Tab：JOIN users，要求 `users.user_role = 'operator'`（Live 状态）
- Pending / Denied Tab：JOIN users，要求 `users.user_role != 'operator'`（Live 状态）
- 计数逻辑同步修正

**Deny 时自动吊销 Upload Keys**：
- 在 `review_operator_application` 事务中，deny（含 approved→deny）时 UPDATE 该用户所有 ACTIVE upload keys 为 REVOKED

---

## 测试分析

### 风险点

| 编号 | 风险描述 | 优先级 |
|------|---------|--------|
| R-01 | Approved 行点击与行内按钮点击的事件传播隔离是否生效 | 高 |
| R-02 | Deny 回调的 boolean 返回值驱动 Detail Modal 关闭行为 | 高 |
| R-03 | 创建 Upload Key 后密钥仅显示一次，刷新后不可再次获取 | 高 |
| R-04 | 吊销 Key 后立即在列表反映为 REVOKED，Delete 按钮消失 | 高 |
| R-05 | Deny 操作（含 approved→deny）自动吊销该用户所有 ACTIVE Upload Keys | 高 |
| R-06 | Approved Tab 过滤以 live user_role 为准，不被历史 review_status 误导 | 高 |
| R-07 | 非 Operator 用户不可为其创建 Upload Key（后端校验） | 高 |
| R-08 | Detail 内 Open dashboard 会关闭 Detail 再打开 Dashboard | 中 |
| R-09 | Stats 加载中显示 `—`，加载失败不崩溃 | 中 |
| R-10 | 注册 Robots 为空时显示空状态文案 | 低 |
| R-11 | 创建 Key 时 Label 为空也允许（label nullable） | 低 |
| R-12 | Upload Key 列表按 created_at DESC 排序 | 低 |

### 接口边界测试点

- `user_id` 缺失或非整数 → 400
- `user_id` 不存在 → 404（Create 接口）
- 目标用户不是 Operator → 400（Create 接口）
- 对 REVOKED key 再次调用 DELETE → 404
- 管理员未登录（无 JWT）→ 401 / 403
- 跨用户吊销：DELETE key 时 user_id 与 key 实际归属不符 → 404

---

## E2E 测试用例

### 环境准备

- 管理员账号已登录 Admin Portal
- 至少存在一名已审批的 Operator（approved 状态，user_role = 'operator'）
- 至少存在一名 Pending 申请人
- 测试 Operator 已注册至少 1 台机器人（可选，用于 robots 区验证）

---

### 功能模块一：Approved 行点击与 Detail Modal 入口

| TC | 测试目标 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|----|---------|---------|---------|---------|--------|
| TC-01 | Approved 行点击打开 Detail Modal | Approved Tab 有至少一条记录 | 1. 进入 Admin Portal → Operator Applications → Approved Tab<br>2. 点击某条 Approved Operator 行（避开按钮区域） | 1. 弹出 Operator Detail Modal<br>2. Header 显示该 Operator 邮箱<br>3. Header 显示 User ID（格式 `ID XXXXX`）<br>4. 显示 `Approved` 状态 pill<br>5. 每条 Approved 行末尾可见 `›` 指示符 | 高 |
| TC-02 | Pending / Denied 行不可点击打开 Modal | Pending Tab 有记录 | 1. 切换到 Pending Tab<br>2. 点击任意 Pending 行（非按钮区域） | 无 Modal 弹出，无任何路由跳转 | 高 |
| TC-03 | 行内按钮点击不触发 Detail Modal（事件传播隔离） | Approved Tab 有至少一条记录 | 1. 点击某 Approved 行的 **Dashboard** 按钮<br>2. 关闭 Dashboard 返回<br>3. 再次点击同一行的 **Deny** 按钮并在 confirm 对话框选 Cancel | 1. Dashboard 按钮：跳转 UploadDashboard，不打开 Detail Modal<br>2. Deny + Cancel：不打开 Detail Modal，该行仍在 Approved Tab | 高 |

---

### 功能模块二：Operator Detail Modal — 信息展示

| TC | 测试目标 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|----|---------|---------|---------|---------|--------|
| TC-04 | Stats 卡片数据正确加载 | 已打开任意 Approved Operator 的 Detail Modal | 打开 Detail Modal，观察 Stats 区域 | 1. `Approved on`：显示格式化时间（如 `Aug 20, 2026, 10:30 AM`）<br>2. `Episodes uploaded`：显示非负整数<br>3. `Last upload`：有上传则显示时间，否则显示 `—`<br>4. `Active upload keys`：与下方 Keys 区 ACTIVE 数量一致<br>5. 加载中四个 stat 均显示 `—` | 高 |
| TC-05 | Registered Robots 区 — 有机器人 | 该 Operator 已注册至少 1 台机器人 | 打开该 Operator 的 Detail Modal，查看 Registered robots 区 | 每条机器人显示 `{manufacturer} {model}`、`{serial_number}`，状态 `Paired` pill | 中 |
| TC-06 | Registered Robots 区 — 无机器人 | 该 Operator 未注册任何机器人 | 打开该 Operator 的 Detail Modal，查看 Registered robots 区 | 显示 `No registered robots.` 空状态文案 | 低 |

---

### 功能模块三：Upload API Keys — 列表展示

| TC | 测试目标 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|----|---------|---------|---------|---------|--------|
| TC-07 | Keys 列表正常展示（有 Keys） | 该 Operator 至少有 1 条 Upload Key | 打开 Detail Modal，滚动到 Upload API keys 区域 | 1. 表头：Label / Key / Created / Last used / Status<br>2. Key 列显示 `{key_prefix}••••••••••••••••••`<br>3. ACTIVE：绿色 `Active` pill + `Delete` 按钮<br>4. REVOKED：灰色 `Revoked` pill，无 Delete 按钮<br>5. 列表按创建时间降序排列 | 高 |
| TC-08 | Keys 列表空状态 | 该 Operator 无任何 Upload Key | 打开 Detail Modal，查看 Upload API keys 区域 | 显示 `No upload keys yet` + `This operator can't push episodes until you create one.` | 中 |
| TC-09 | 多 Key 共存展示 | — | 1. 为某 Operator 创建 3 条 Upload Key<br>2. 吊销其中 1 条<br>3. 重新打开 Detail Modal | 1. 显示 3 条 Key<br>2. 已吊销 Key 显示 REVOKED pill，无 Delete 按钮<br>3. 2 条 ACTIVE Key 各显示 Delete 按钮<br>4. Stats 中 `Active upload keys` 为 `2`<br>5. 列表按创建时间降序排列（最新在最前） | 中 |

---

### 功能模块四：Upload API Keys — 创建

| TC | 测试目标 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|----|---------|---------|---------|---------|--------|
| TC-10 | 创建 Upload Key 完整流程（有 Label） | 已打开 Operator Detail Modal | 1. 点击 `Create upload key`<br>2. 填写 Label `Bench Station A`<br>3. 点击 `Create key`<br>4. 查看 Key created Modal<br>5. 点击 `Done` | 1. 弹出创建 Modal，含 Label 输入框<br>2. 创建成功后创建 Modal 关闭<br>3. 弹出 Key created Modal，显示完整 api_key<br>4. 提示 `Copy it now — you won't be able to see it again.`<br>5. 提供 Copy 按钮（点后变 ✓，~1.8s 恢复）<br>6. 显示安全提示文案<br>7. Done 后 Modal 关闭，列表新增 `Bench Station A` ACTIVE 条目<br>8. Stats `Active upload keys` 计数 +1 | 高 |
| TC-11 | 创建 Upload Key — Label 为空 | 已打开创建 Key Modal | 1. 不填写 Label<br>2. 直接点击 `Create key` | 成功创建，列表新增条目，Label 列显示 `—` | 低 |
| TC-12 | 创建 Modal — 取消 | 已打开创建 Key Modal | 1. 填写 Label<br>2. 点击 `Cancel` | 创建 Modal 关闭，Keys 列表无新增，Detail Modal 仍打开 | 中 |
| TC-13 | 创建 Key 进行中 UI 防重复 | 已点击 `Create key`（网络慢/throttle） | 点击 `Create key` 后立即观察 Modal | 1. 按钮显示 `Creating…` 且置灰（disabled）<br>2. Cancel 按钮置灰不可点<br>3. 点击 Overlay 不关闭 Modal | 中 |

---

### 功能模块五：Upload API Keys — 吊销

| TC | 测试目标 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|----|---------|---------|---------|---------|--------|
| TC-14 | 吊销 ACTIVE Key 完整流程 | 该 Operator 至少有 1 条 ACTIVE Key | 1. 找到目标 ACTIVE Key，点击 `Delete`<br>2. 查看确认 Modal<br>3. 点击 `Delete key` | 1. 确认 Modal 显示标题 `Delete "{label 或 prefix}"?`<br>2. 显示警告：`Uploads using this key start failing immediately. Episodes already uploaded are not affected. This can't be undone.`<br>3. 吊销成功后确认 Modal 关闭<br>4. 列表该 Key 状态变为 `Revoked`，`Delete` 按钮消失<br>5. Stats `Active upload keys` 计数 -1 | 高 |
| TC-15 | 吊销 Modal — 取消 | 已点击某 ACTIVE Key 的 `Delete` | 在确认 Modal 点击 `Keep key` | 确认 Modal 关闭，该 Key 仍为 ACTIVE 状态 | 中 |
| TC-16 | 吊销进行中 UI 防重复 | 已点击 `Delete key`（网络慢/throttle） | 点击 `Delete key` 后立即观察 Modal | 1. 按钮显示 `Deleting…` 且置灰<br>2. `Keep key` 按钮置灰<br>3. 点击 Overlay 不关闭 Modal | 中 |

---

### 功能模块六：Copy 按钮

| TC | 测试目标 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|----|---------|---------|---------|---------|--------|
| TC-17 | Key created Modal 的 Copy 按钮 | 已成功创建 Upload Key，Key created Modal 已弹出 | 点击 Copy 按钮 | 1. Copy 图标变为 ✓（Check 图标）<br>2. 约 1.8 秒后恢复为 Copy 图标<br>3. 粘贴板内容与 Modal 中展示的完整 api_key 一致 | 中 |

---

### 功能模块七：Detail Modal — 顶部操作

| TC | 测试目标 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|----|---------|---------|---------|---------|--------|
| TC-18 | Open dashboard — Detail 自动关闭 | 已打开某 Operator 的 Detail Modal | 点击顶部 `Open dashboard` 按钮 | 1. Detail Modal 关闭<br>2. UploadDashboard 视图打开，显示该 Operator 数据<br>3. 关闭 Dashboard 后可返回 Approved 列表 | 中 |
| TC-19 | Deny operator — 成功（从 Detail 内发起） | 已打开某 APPROVED Operator 的 Detail Modal | 1. 点击 `Deny operator`<br>2. 在浏览器 confirm 对话框点击 `OK` | 1. Detail Modal 自动关闭<br>2. Approved Tab 该 Operator 消失<br>3. 该 Operator 出现在 Denied Tab<br>4. 该 Operator 所有 ACTIVE Upload Keys 已被自动吊销（API 验证） | 高 |
| TC-20 | Deny operator — 取消（从 Detail 内发起） | 已打开某 APPROVED Operator 的 Detail Modal | 1. 点击 `Deny operator`<br>2. 在浏览器 confirm 对话框点击 `Cancel` | 1. Detail Modal 保持打开<br>2. Approved Tab 该 Operator 记录保留<br>3. `Deny operator` 按钮状态恢复（不显示 Denying…） | 高 |
| TC-21 | 点击 Overlay 关闭 Detail Modal | 已打开 Operator Detail Modal | 点击 Modal 外部暗色 Overlay 区域 | Detail Modal 关闭，回到 Operator Applications 列表 | 中 |
| TC-22 | Back 按钮关闭 Detail Modal | 已打开 Operator Detail Modal | 点击左上角 `← Back to approved operators` | Detail Modal 关闭，回到列表 | 中 |

---

### 功能模块八：后端过滤逻辑修复验证

| TC | 测试目标 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|----|---------|---------|---------|---------|--------|
| TC-23 | Approved Tab 过滤以 Live user_role 为准 | DB 中存在某用户：`admin_review_status = 'approved'`，`user_role != 'operator'`（role 在流程外被清除） | 刷新 Admin Portal，进入 Operator Applications | 1. Approved Tab 不显示该用户<br>2. Denied 或 Pending Tab 正确显示该用户（取决于 `admin_review_status`） | 高 |
| TC-24 | Deny 时自动吊销 Upload Keys（API 层验证） | 目标 Operator 已有多条 ACTIVE Upload Keys | 1. 通过 Admin Portal Deny 该 Operator（Approved → Deny 路径）<br>2. 调用 `GET /data/admin/upload-api-keys?user_id=X` 验证 | 1. 所有 keys 的 `status` 均为 `REVOKED`<br>2. `revoked_at` 字段为 Deny 操作时的时间 | 高 |

---

### 功能模块九：后端接口边界与鉴权

| TC | 测试目标 | 操作步骤 | 预期结果 | 优先级 |
|----|---------|---------|---------|--------|
| TC-25 | `user_id` 缺失 | `GET /data/admin/upload-api-keys`（不传 user_id） | HTTP 400，body: `user_id is required` | 高 |
| TC-26 | `user_id` 非整数 | `GET /data/admin/upload-api-keys?user_id=abc` | HTTP 400 | 高 |
| TC-27 | `user_id` 不存在 | `POST /data/admin/upload-api-keys`，body: `{"user_id": 999999}` | HTTP 404，body: `user not found` | 高 |
| TC-28 | 目标用户非 Operator | `POST /data/admin/upload-api-keys`，body: `{"user_id": <普通用户 ID>}` | HTTP 400，body: `user is not an operator` | 高 |
| TC-29 | 吊销不属于该 user_id 的 Key | `DELETE /data/admin/upload-api-keys/<id>?user_id=<他人ID>` | HTTP 404 | 高 |
| TC-30 | 吊销已 REVOKED 的 Key | `DELETE /data/admin/upload-api-keys/<revoked_id>?user_id=X` | HTTP 404 | 高 |
| TC-31 | 未授权访问 — 无 JWT | 不带 Authorization header 依次请求 4 个 Admin 接口：<br>- `GET /data/admin/upload-api-keys?user_id=1`<br>- `POST /data/admin/upload-api-keys`<br>- `DELETE /data/admin/upload-api-keys/1?user_id=1`<br>- `GET /data/admin/operator-detail/stats?user_id=1` | 所有接口返回 401 或 403 | 高 |

---

## 注意事项

- Upload Key 的完整密钥（api_key）**仅在创建成功响应中返回一次**，后续接口和页面仅展示前缀（key_prefix），测试时注意在 Key created Modal 中验证并记录
- Deny 操作同时触发两个后端改动：修改 `data_operator_applications.admin_review_status` + 吊销 `data_api_keys_upload` 中所有 ACTIVE 记录，测试时需验证两者均生效
- Approved Tab 的过滤逻辑变更是 bug fix，测试时可配合 DB 直接修改 user_role 来构造脏数据场景进行验证
