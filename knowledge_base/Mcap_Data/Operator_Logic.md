# Operator 功能逻辑与数据流分析

---

## 一、功能背景与目标

**Operator** 是 Prisma 平台的机器人数据贡献者角色。用户需要主动申请，经管理员审核通过后，才能上传机器人轨迹数据并获得收益。

**功能目标：**

- 用户提交 Operator 申请（含机器人信息）
- 管理员在后台完成审核（批准 / 拒绝）
- 审核结果实时同步到用户前端
- 审批通过后发送邮件通知用户，同时通知系统管理员

**涉及的核心角色与实体：**


| 角色/实体                     | 说明                    |
| ------------------------- | --------------------- |
| User（用户）                  | 机器人持有者，发起 Operator 申请 |
| Admin（管理员）                | 负责审核申请，可批准或拒绝         |
| Robot（机器人）                | 用户名下已注册的机器人，通过序列号唯一标识 |
| OperatorApplication（申请记录） | 记录每次申请的详情与审核状态        |


---

## 二、申请状态流转

Operator 申请从创建到最终态，有三个状态：

```
用户提交申请
     │
     ▼
  PENDING  ──── Admin 批准 ───▶  APPROVED
     │
     └────── Admin 拒绝 ───▶  REJECTED  ──── 用户重新申请 ───▶  PENDING
```


| 状态         | 触发条件          | 后续动作                             |
| ---------- | ------------- | -------------------------------- |
| `PENDING`  | 用户提交申请        | 等待管理员审核                          |
| `APPROVED` | 管理员点击批准       | 更新用户 Operator 权限；发送通知邮件给用户和系统管理员 |
| `REJECTED` | 管理员点击拒绝（填写原因） | 记录拒绝原因；前端展示原因；用户可重新申请            |


---

## 三、序列号规则（Serial Number Rules）

序列号由各厂商定义，后端负责统一校验。前端通过 debounce 触发，用户停止输入后才发起一次校验请求。


| 厂商            | 总长度 | 前缀   | 其余字符                 | 示例                        |
| ------------- | --- | ---- | -------------------- | ------------------------- |
| Airbot        | 16  | `PZ` | 字母 + 数字（含字母需与供应商确认）  | `PZ51C02543000816`        |
| AGILEX        | 23  | `MD` | 大写字母 + 数字 `[0-9A-Z]` | `MD100101000019205Z00083` |
| I2rt Robotics | 11  | `JG` | 纯数字                  | `JG260103027`             |
| Realman       | 16  | `RM` | 纯数字                  | `RM11010325010301`        |


**后端校验规则（通用逻辑）：**

1. 长度必须符合对应厂商规定
2. 前缀（`PZ` / `MD` / `JG` / `RM`）必须匹配
3. 其余字符满足厂商字符集约束
4. 全部大写（不接受小写）
5. 序列号不能为空

---

## 四、核心 API 一览


| 接口                                              | 调用方      | 说明                            |
| ----------------------------------------------- | -------- | ----------------------------- |
| `GET /get-user-data`                            | 前端（用户）   | 聚合返回用户信息、机器人列表、当前 Operator 状态 |
| `POST /validate-serial-number`                  | 前端（实时校验） | 校验序列号格式与归属，支持 debounce 调用     |
| `POST /submit-operator-application`             | 前端（用户提交） | 创建 PENDING 申请记录               |
| `GET /admin/operator-applications`              | Admin 前端 | 获取申请列表，支持按状态筛选                |
| `POST /admin/operator-applications/:id/approve` | Admin 前端 | 批准申请，触发权限更新和邮件通知              |
| `POST /admin/operator-applications/:id/reject`  | Admin 前端 | 拒绝申请，记录拒绝原因                   |


### `/get-user-data` 返回结构（示意）

```json
{
  "user": { "name": "Alice", "email": "alice@example.com" },
  "robots": [
    { "name": "Robot A", "serial_number": "JG260103027", "status": "active" }
  ],
  "operator_status": "PENDING"
}
```

> `operator_status` 枚举值：`NONE`（未申请）/ `PENDING` / `APPROVED` / `REJECTED`

---

## 五、端到端数据流

### 5.1 用户申请流程

```
用户进入账号页
      │
      ▼
GET /get-user-data  ──▶  operator_status = NONE
      │
      ▼
打开 Operator Application Modal
      │
      ├─ 邮箱验证（通过后解锁后续步骤）
      │
      ├─ 输入序列号（停止输入后 debounce 触发）
      │       └──▶  POST /validate-serial-number  ──▶  有效 / 无效
      │
      └─ 所有校验通过，点击提交
              └──▶  POST /submit-operator-application
                          │
                          ▼
                    DB 写入 PENDING 申请记录
                          │
                          ▼
              前端刷新视图为「待审核」状态
```

### 5.2 管理员审核流程

```
Admin 打开 Operator Applications Review
      │
      ▼
GET /admin/operator-applications  ──▶  返回 PENDING 申请列表
      │
      ├─ 查看申请详情（用户信息 / 机器人信息 / 序列号）
      │
      ├─ 点击「批准」
      │       └──▶  POST /approve
      │                   │
      │                   ├── DB: 申请状态 → APPROVED
      │                   ├── DB: 用户 Operator 权限更新
      │                   ├── Email → 用户（审批通过通知）
      │                   └── Email → 系统管理员（新增 Operator 通知）
      │
      └─ 点击「拒绝」+ 填写原因
              └──▶  POST /reject
                          │
                          ├── DB: 申请状态 → REJECTED
                          └── DB: 记录拒绝原因
```

### 5.3 用户查看审核结果

用户刷新账号页，前端调用 `GET /get-user-data`，根据返回的 `operator_status` 值渲染不同视图：


| operator_status | 前端展示                                |
| --------------- | ----------------------------------- |
| `NONE`          | 展示「申请成为 Operator」入口                 |
| `PENDING`       | 展示「审核中」提示，禁用重复提交                    |
| `APPROVED`      | 展示 Operator 已激活状态，开放 VLA Foundry 入口 |
| `REJECTED`      | 展示拒绝原因，提供「重新申请」入口                   |


---

## 六、邮件通知

审批通过后，后端发送以下邮件：

**收件人：申请用户**

> **Subject：** Operator Status Approved: Start Earning at the VLA Foundry
>
> Hi [Name],
>
> Congratulations! Your application has been approved. You are now officially a Prisma Operator.
>
> Since your hardware is already registered, you are ready to begin. You can now access the VLA Foundry to upload your robot trajectory data and start earning USD.
>
> **How to get started:**
>
> 1. Log in to the Prisma platform.
> 2. Navigate to the VLA Foundry section.
> 3. Upload your VLA data from your registered humanoid.
>
> Your contributions are essential to building the next generation of robotics. We're excited to have you on board.
>
> Best,
> The Prisma Team

**收件人：系统管理员**（用于运维侧感知新 Operator 的产生，便于人工复核）

> 邮件内容包含：新 Operator 的用户信息、机器人信息、审核操作人、时间戳。

**异常处理原则：** 邮件发送失败不影响状态落库，需记录 error log 并支持重发机制。

---

## 七、测试策略与测试用例

### 7.1 测试策略概述

Operator 功能涉及序列号校验、用户申请、管理员审核、状态同步、邮件通知五个核心环节，采用「分层覆盖」策略：


| 测试层级   | 覆盖目标                         | 工具/方式                        |
| ------ | ---------------------------- | ---------------------------- |
| 后端单元测试 | 序列号校验逻辑、状态流转规则、各 handler 返回值 | pytest / mock DB             |
| 后端接口测试 | API 参数完整性、HTTP 状态码、数据库写入正确性  | pytest + test DB             |
| 前端组件测试 | UI 状态渲染、表单校验、debounce 触发行为   | Jest / React Testing Library |
| E2E 测试 | 完整业务流程闭环（含跨角色操作）             | Playwright / Cypress         |


**测试优先级：** 序列号校验 > 申请状态流转 > 审核接口权限 > 邮件通知 > UI 展示细节

---

### 7.2 序列号校验测试用例

> 对应 `POST /api/operator/register-robot/validate-serial-number` 接口，**只校验格式**，不查 DB 归属。

**7.2.1 格式校验**


| ID    | 厂商      | 输入                         | 期望结果 | 失败原因                                        |
| ----- | ------- | -------------------------- | ---- | ------------------------------------------- |
| SN-01 | Airbot  | `PZ51C02543000816`         | 通过   | 官方示例                                        |
| SN-02 | Airbot  | `PZ12345678901234`         | 通过   | 16位，PZ 开头，最后 9 位为纯数字（`\d{9}$`）              |
| SN-03 | Airbot  | `PZ1234567890123`          | 失败   | 只有 15 位，长度不足                                |
| SN-04 | Airbot  | `PZ123456789012345`        | 失败   | 17 位，超出长度                                   |
| SN-05 | Airbot  | `AB51C02543000816`         | 失败   | 前缀非 `PZ`                                    |
| SN-06 | Airbot  | `pz51c02543000816`         | 失败   | 小写不合规                                       |
| SN-07 | Airbot  | `PZ51-02543000815`         | 失败   | 含特殊字符 `-`                                   |
| SN-08 | AGILEX  | `MD100101000019205Z00083`  | 通过   | 官方示例                                        |
| SN-09 | AGILEX  | `MD100000000000000000001`  | 通过   | 23位，MD 开头，后21位为纯数字（`[0-9]` 是 `[0-9A-Z]` 子集） |
| SN-10 | AGILEX  | `MD1001010000192050000830` | 失败   | 24 位，超出长度                                   |
| SN-11 | AGILEX  | `MD10010100001920500008`   | 失败   | 22 位，长度不足                                   |
| SN-12 | AGILEX  | `XX100101000019205Z00083`  | 失败   | 前缀非 `MD`                                    |
| SN-13 | AGILEX  | `MD100101000019205z00083`  | 失败   | 含小写字母（实际代码仅校验长度+前缀，此用例验证大小写敏感性，需确认实现是否拦截）  |
| SN-14 | I2rt    | `JG260103027`              | 通过   | 官方示例                                        |
| SN-15 | I2rt    | `JG26010302`               | 失败   | 只有 10 位，长度不足                                |
| SN-16 | I2rt    | `JG2601030270`             | 失败   | 12 位，超出长度                                   |
| SN-17 | I2rt    | `JG26010302A`              | ⚠️ 待确认 | 实际代码只校验「长度11 + JG前缀」，不校验后缀字符集，此输入长度为11可能通过  |
| SN-18 | I2rt    | `AG260103027`              | 失败   | 前缀非 `JG`                                    |
| SN-19 | Realman | `RM11010325010301`         | 通过   | 官方示例                                        |
| SN-20 | Realman | `RM1101032501030`          | 失败   | 15 位，长度不足                                   |
| SN-21 | Realman | `RM110103250103011`        | 失败   | 17 位，超出长度                                   |
| SN-22 | Realman | `RM1101032501030A`         | ⚠️ 待确认 | 实际代码只校验「长度16 + RM前缀」，不校验后缀字符集，此输入长度为16可能通过  |
| SN-23 | Realman | `rm11010325010301`         | ⚠️ 待确认 | 实际代码不做大小写校验，此输入可能通过，需确认 startswith 是否区分大小写 |
| SN-24 | 通用      | `（空字符串）`                   | 失败   | 空值不接受                                       |
| SN-25 | 通用      | `JG260103027`（首部有空格）       | 失败   | 首尾空格不合规                                     |
| SN-26 | 跨厂商     | `JG51C02543000816`         | 失败   | JG 前缀但长度为 16，不符合 I2rt 的 11 位规则              |


**7.2.2 注册机器人接口校验说明**

> ⚠️ **实际代码确认：`/api/operator/register-robot/validate-serial-number` 只做格式校验，不查 DB，不校验归属。**
>
> 注册机器人时（`POST /api/operator/register-robot`）的 duplicate 查询带有 `user_id`，
> **只防止当前用户重复注册同一台机器人，不校验序列号是否已被其他用户注册。**
> 即同一序列号可以被多个不同用户同时注册，当前代码不拦截。

| ID        | 场景                         | 接口                                  | 前置数据                            | 期望结果（当前实现）                                   |
| --------- | -------------------------- | ----------------------------------- | ------------------------------- | -------------------------------------------- |
| SN-OWN-01 | 注册机器人，序列号未被当前用户注册过         | `POST /api/operator/register-robot` | DB 中当前用户无此机器人记录                  | 注册成功；写入 `data_machines`                      |
| SN-OWN-02 | 注册机器人，当前用户重复注册同一序列号        | `POST /api/operator/register-robot` | 当前用户已有相同 manufacturer+model+serial 记录 | 失败，返回 409：「You have already registered this robot」 |
| SN-OWN-03 | 注册机器人，序列号已被其他用户注册（⚠️ 功能缺口） | `POST /api/operator/register-robot` | 同序列号已属于另一用户                     | ⚠️ **当前代码不拦截，注册成功**（跨用户归属校验未实现，建议后续补充唯一性约束） |


---

### 7.3 用户申请流程测试用例

> 覆盖前端表单交互 + `POST /api/operator/submit-membership-application` 接口。


| ID     | 场景                    | 前置条件                     | 操作步骤                                        | 期望结果                                            |
| ------ | --------------------- | ------------------------ | ------------------------------------------- | ----------------------------------------------- |
| APP-01 | 正常提交申请（账号已有邮箱）        | 用户已登录，账号已绑定邮箱，名下有至少一个机器人  | 点击「Apply」按钮                                   | 直接调用 submit 接口（无需 Modal）；DB 写入 `pending` 申请；前端显示「Membership pending」badge；通知弹窗提示「We'll email you at {email}」 |
| APP-02 | 正常提交申请（账号无邮箱，需先添加）    | 用户已登录，账号无任何邮箱，名下有机器人      | 点击「Apply」按钮                                   | 打开 OperatorApplicationNewEmailModal，要求用户填写并验证邮箱后才提交 |
| APP-03 | 无机器人时 Apply 按钮禁用       | 用户已登录，名下无任何机器人            | 进入账号页                                       | Apply 按钮 disabled；Tooltip 提示「Register a robot in order to be eligible」 |
| APP-04 | 已有 pending 申请时不再显示 Apply | 该用户已有一条 pending 申请        | 进入账号页                                       | 显示「Membership pending」badge；Apply 按钮消失       |
| APP-05 | 已 approved 时显示已激活状态    | 用户 operator_status 为 approved | 进入账号页                                       | 显示「Current membership」blue badge；Operator 标题变为蓝色；无 Apply 按钮 |
| APP-06 | denied 状态展示固定提示，无重新申请入口 | 用户上次申请被拒绝（operator_status = denied） | 进入账号页                                    | 显示「Membership denied」badge；hover 出现 Tooltip：「Your application was declined. Please contact support@prismax.ai...」；**Apply 按钮不渲染；用户无法从 UI 重新申请** |
| APP-08 | 提交接口返回错误（账号已有 pending）  | 后端检测到已有 pending 申请         | 点击 Apply                                    | showNotification error：「There is already a pending application...」；状态不变 |
| APP-09 | 提交接口返回错误（无机器人）         | 后端检测到用户无已注册机器人            | 点击 Apply                                    | showNotification error：「You must register at least one robot...」 |
| APP-10 | 提交接口网络异常               | 网络中断                       | 点击 Apply                                    | showNotification error；Apply 按钮恢复可点击；DB 无脏记录  |
| APP-11 | 未登录用户点击 Apply           | 用户未登录                      | 点击 Apply 按钮                                 | showNotification warning：「Please log in first before requesting operator membership.」 |


---

### 7.4 管理员审核流程测试用例

> 覆盖 Admin Operator Applications Review 组件（`VLAAdminOperatorApplications.js`）+ `POST /api/admin/review-operator-application` 接口。
>
> ⚠️ **实际确认：Deny 操作无需填写原因，直接一键 Deny；前端不弹窗，不记录拒绝原因。**

| ID     | 场景                     | 前置条件                          | 操作步骤                       | 期望结果                                                                 |
| ------ | ---------------------- | ----------------------------- | -------------------------- | -------------------------------------------------------------------- |
| ADM-01 | 批准申请                   | Admin 已登录，有一条 pending 申请      | 打开 Review 页 → 点击「Approve」  | DB：`users.user_role = 'operator'`；`data_operator_applications.admin_review_status = 'approved'`；该行从列表移除；用户收到审批通过邮件 |
| ADM-02 | 拒绝申请                   | Admin 已登录，有一条 pending 申请      | 打开 Review 页 → 点击「Deny」    | DB：`users.user_role = NULL`；`admin_review_status = 'denied'`；该行从列表移除；**不记录拒绝原因；不发送邮件给用户** |
| ADM-03 | 列表展示字段完整性              | 有多条 pending 申请                | 打开 Review 页查看列表            | 每行展示：用户邮箱/钱包地址、申请时间、状态 badge、会员等级/积分、机器人列表（含 manufacturer+model+serial） |
| ADM-04 | 空列表展示                  | 无任何 pending 申请                | 打开 Review 页 Pending 区域     | 显示「No pending applications.」，不报错                                     |
| ADM-05 | Approved / Denied 区块折叠 | 页面加载                          | 默认状态                       | Approved 和 Denied 区块默认折叠（collapsible=true）；Pending 区块默认展开            |
| ADM-06 | 分页功能                   | Pending 申请超过 20 条（PAGE_SIZE）   | 查看列表底部                     | 显示分页控件；点击下一页正确加载第二页数据                                                |
| ADM-07 | Approved 申请可被 Deny     | 申请状态为 approved                | 在 Approved 区块点击「Deny」     | `admin_review_status → 'denied'`；`user_role → NULL`；记录从 Approved 列表移除 |
| ADM-08 | Pending 状态下 Approve 可显示 Deny | 申请状态为 pending            | 查看 Actions 列              | 同时显示「Approve」和「Deny」按钮（`showApprove = !isApproved; showDeny = isPending \|\| isApproved`） |
| ADM-09 | 非 Admin token 调用审核接口   | 普通用户 token                    | 直接请求 review-operator-application | 返回 401（JWT 校验失败）                                                  |
| ADM-10 | 审核不存在的 application_id  | Admin 已登录                     | 请求不存在的 application_id      | 返回错误或无行受影响（取决于后端实现，建议返回 404）                                        |
| ADM-11 | 审核过程中点击另一条申请           | 有多条 pending 申请，正在处理第一条        | 第一条 processing 期间点击第二条操作按钮 | 其他申请操作按钮 disabled（`disabled={!!processingId}`）；防止并发操作               |


---

### 7.5 /get-user-data 接口测试用例

> 覆盖数据聚合接口，验证 operator_status 与 robots 字段的正确性。


| ID     | 场景                        | 前置数据                               | 期望响应                                              |
| ------ | ------------------------- | ---------------------------------- | ------------------------------------------------- |
| GUD-01 | 未申请的普通用户（有机器人）           | 用户有机器人，无申请记录                    | `robots` 列表非空；`operator_status: null`                              |
| GUD-02 | 未申请的普通用户（无机器人）           | 用户名下无任何机器人                      | `robots: []`（空数组）；`operator_status: null`                          |
| GUD-03 | 有 pending 申请              | 存在一条 pending 申请                  | `operator_status: "pending"`                                         |
| GUD-04 | 已 approved               | `users.user_role = 'operator'`  | `operator_status: "approved"`（优先读 user_role，不读申请表）                  |
| GUD-05 | 已 denied                 | 最近一条申请状态为 denied                 | `operator_status: "denied"`                                          |
| GUD-06 | 历史 denied + 当前新 pending  | 旧 denied 记录 + 新 pending 申请（需通过 API 直接构造，UI 不支持 denied 后重新申请） | `operator_status: "pending"`（取最新一条 ORDER BY created_at DESC LIMIT 1） |
| GUD-07 | denied 重新申请后被 approved   | 申请经历 denied → pending → approved | `operator_status: "approved"`（user_role 更新为 'operator'）              |
| GUD-08 | 机器人信息字段完整性               | 用户有多个机器人                        | 每个机器人包含 `machine_id`、`manufacturer`、`model`、`serial_number`、`is_default_producer` |
| GUD-09 | 未登录用户访问                  | 无 token 或 token 无效              | 返回 `{"success": false, "msg": "Authorization token is required"}`（401） |


---

### 7.6 邮件通知测试用例

> ⚠️ **实际确认：系统管理员邮件在用户「提交申请时」触发（不是批准时）；用户邮件仅在「批准时」触发；拒绝时不发任何邮件。**

| ID      | 场景                        | 触发动作                          | 期望结果                                                                                    |
| ------- | ------------------------- | ----------------------------- | --------------------------------------------------------------------------------------- |
| MAIL-01 | 用户提交申请 → 系统管理员收到通知        | 用户点击 Apply 提交成功               | `wanxin@solidcap.io` 和 `support@prismax.ai` 收到邮件；Subject：「New Operator Membership Application Submitted」；内容含当前 pending 总数 |
| MAIL-02 | 审批通过 → 用户收到通知邮件           | Admin 点击 Approve              | 申请邮箱收到邮件；Subject：「Operator Status Approved: Start Earning at the VLA Foundry」；正文含用户姓名（占位符已替换） |
| MAIL-03 | 拒绝申请 → 不触发任何邮件            | Admin 点击 Deny                 | 用户不收到任何邮件；系统管理员不收到额外通知                                                                  |
| MAIL-04 | 邮件发送失败不影响核心状态落库           | mock 邮件服务抛出异常                 | DB 状态正常更新；错误被 log 记录；用户权限正常生效（邮件发送在 DB commit 之后执行）                                      |
| MAIL-05 | 批准时找不到申请邮箱，跳过发送但 log 告警  | approved=true 但 app_row.email 为空 | 不抛出异常；log warning：「Operator approved but unable to send an email」；DB 状态仍为 approved    |


---

### 7.7 E2E 主流程测试用例


| ID     | 场景                        | 步骤摘要                                                             | 关键断言                                                                                  |
| ------ | ------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| E2E-01 | 申请 → 批准 完整链路             | 用户登录（账号已绑定邮箱，名下有机器人）→ 点击 Apply → 提交成功 → 切换 Admin 账号批准 → 切回用户刷新页面 | ① DB：`admin_review_status = 'approved'`，`user_role = 'operator'` ② 用户页显示「Current membership」blue badge ③ 系统管理员在提交时收到通知邮件 ④ 用户在批准时收到通过邮件 |
| E2E-02 | 申请 → 拒绝 完整链路             | 用户登录 → 提交申请 → 切换 Admin → 点击 Deny → 切回用户刷新页面                    | ① DB：`admin_review_status = 'denied'`，`user_role = NULL` ② 用户页显示「Membership denied」badge，hover 提示联系 support ③ **不展示拒绝原因文字** ④ 不发送邮件给用户 |
| E2E-03 | denied 状态下 UI 无重新申请入口（⚠️ 功能缺口） | 在 E2E-02 基础上，用户刷新账号页 | ⚠️ Apply 按钮不存在；只显示「Membership denied」badge 和联系 support 的 Tooltip；**当前版本不支持用户从 UI 自助重新申请，需联系 support 人工处理** |
| E2E-04 | 移动端申请流程                  | 使用移动端视口（375px）完成 E2E-01 全流程                                     | 所有页面布局正常；Apply 按钮可点击；通知弹窗完整展示；无内容截断或遮挡 |


