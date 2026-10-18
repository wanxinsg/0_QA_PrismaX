# Prismax Pre-Release — 2026-06-22~23 Commit 分析与测试策略

**涉及仓库：** `app-prismax-rp`（前端）、`app-prismax-rp-backend`（后端）  
**日期跨度：** 2026-06-22 ~ 2026-06-23  
**提交作者：** lanmanc、Aparna Rangamani  
**分析范围：**
- 后端：`985020e`（含）→ `bcff8bd`
- 前端：`89f91b1`（含）→ `bdee463`（HEAD）

| 仓库 | Commit 范围 | 改动规模 |
|------|------------|---------|
| app-prismax-rp-backend | `985020e` → `bcff8bd`（2 commits） | 4 文件，+82 / -53 |
| app-prismax-rp | `89f91b1` → `bdee463`（5 commits） | 8 文件，+199 / -141 |

---

## 一、Commit 清单

### 1.1 后端（app-prismax-rp-backend）

| # | Hash | 时间 | 作者 | 说明 |
|---|------|------|------|------|
| 1 | `985020e` | 06-22 19:47 PDT | Aparna | pre-release: account for already awarded qa review points pre launch date |
| 2 | `bcff8bd` | 06-23 00:26 EDT | lanmanc | updated backend logic |

### 1.2 前端（app-prismax-rp）

| # | Hash | 时间 | 作者 | 说明 |
|---|------|------|------|------|
| 1 | `89f91b1` | 06-22 13:51 EDT | lanmanc | changed access control |
| 2 | `7d994d0` | 06-22 14:18 PDT | Aparna | PRIS-136: update qa review access control |
| 3 | `5e46c7a` | 06-22 15:48 EDT | lanmanc | improved speed |
| 4 | `1b83d0a` | 06-22 19:44 PDT | Aparna | pre-release: make qa enhancements with review count by launch date; show explorer no access message sooner |
| 5 | `bdee463` | 06-22 22:06 EDT | lanmanc | trying to improve speed |

---

## 二、后端改动详细分析

### 2.1 `985020e` — QA Review 上线日期机制 & 积分幂等保护

**文件：** `app_prismax_data_pipeline/qa_helper.py`、`app_prismax_data_pipeline/app.py`

#### 2.1.1 引入 `QA_LAUNCH_DATE`

```python
QA_LAUNCH_DATE = datetime(2026, 6, 23, 16, 0, 0, tzinfo=timezone.utc)
```

所有统计"用户已完成 review 数"的 `COUNT(*)` SQL 查询均增加过滤条件：

```sql
AND created_at >= :qa_launch_date
```

涉及两处：
- `_require_qa_eligible_user`：检查用户是否超过 review 上限
- `get_qa_validator_access_data`：返回用户已完成 review 数给前端

**意图：** 上线日期之前的历史 review 不计入新的上限配额，避免历史数据导致用户在上线第一天就被误判为超额。

#### 2.1.2 `get_qa_validator_access_data` 返回值新增字段

API 响应新增：
```json
{
  "qa_launch_date": "2026-06-23T16:00:00+00:00"
}
```

前端用此字段展示"自 X 日起完成了 N 次 review"的文案。

#### 2.1.3 `get_episode_earnings` 积分展示修复

移除了 `is_succeeded` 的判断（原代码：`if has_transaction and points_change is not None and is_succeeded`），改为：

```python
if has_transaction and points_change is not None:
```

**意图：** 上线前已发放的积分（对应 episode 可能不是成功状态）也正常展示，不因 status 问题被前端隐藏。

#### 2.1.4 `_reward_final_decision_qa_points` — 发放积分幂等保护

发放积分前查询 `data_qa_episode_activity` 中已有 `point_transaction_id` 的 `(user_id, episode_id)` 对，过滤后只处理尚未发放的记录：

```python
already_rewarded = {(user_id, episode_id) for r in existing_rows}
reward_pairs = [pair for pair in reward_pairs if pair not in already_rewarded]
```

**意图：** 防止因系统重跑（re-run）同一个 upload 时重复给用户发放积分。

---

### 2.2 `bcff8bd` — MCAP 校验策略调整（TOK2 产品）

**文件：** `app_prismax_data_worker/scale_validate_mcap_v01.py`、`app_prismax_data_worker/worker.py`

#### 2.2.1 参数重命名

| 旧参数 | 新参数 | 含义变化 |
|--------|--------|---------|
| `skip_joint_hz_checks` | `skip_camera_fps_check` | TOK2 跳过的检查从关节频率改为摄像头 FPS |

#### 2.2.2 TOK2 校验策略变更

| 校验项 | 旧行为（TOK2） | 新行为（TOK2） |
|--------|--------------|--------------|
| camera FPS check | 正常执行 | **跳过**（标记 `skipped: True`） |
| joint avg freq check | **跳过** | **正常执行** |
| joint rolling freq check | **跳过** | **正常执行** |

**意图：** TOK2 硬件无摄像头或摄像头数据不可靠，但关节频率数据有效，故调换跳过策略。

#### 2.2.3 重复文件检测精化

`_find_existing_duplicate_files` 中 status 过滤条件从：

```sql
AND UPPER(COALESCE(e.status, '')) NOT IN :ignored_statuses
```

改为：

```sql
AND UPPER(COALESCE(e.status, '')) = 'DERIVED_READY'
```

**意图：** 只有真正成功导出的 episode 才被认定为重复文件，避免处于中间状态的记录误判为重复。同时去掉了 SQLAlchemy `expanding` bindparam，简化查询。

---

## 三、前端改动详细分析

### 3.1 `89f91b1` — 正式开放 VLA Foundry / QA Review 入口

**文件：** `Dashboard.js`、`DataHub.js`、`LeftPanel.js`、`MobileMenu.js`、`OperatorSection.js`、`Upload.js`

#### 3.1.1 Dashboard — 移除上线时间门禁

删除 `VALIDATION_LAUNCH_TIME` 时间判断，`handleBeginValidating` 直接跳转 `/data/review`。

#### 3.1.2 DataHub — 移除 `canAccessDataHub` 角色限制

删除：
```js
const canAccessDataHub = ['operator', 'qa', 'senior qa', 'expert qa'].includes(normalizedUserRole);
```
及对应的"Coming soon"全屏提示页，DataHub 现对所有用户开放。

#### 3.1.3 LeftPanel & MobileMenu — 移除"Coming Soon"标注

- 删除 `canAccessVlaFoundry` 逻辑，VLA Foundry 链接从 `/data` 改为 `/data/upload`
- 删除 hover 时显示的"(Coming Soon)"标注
- 删除 `vlaFoundryIsHovered` state

#### 3.1.4 OperatorSection — 阻止 QA 用户申请 Operator

```js
const isQaRole = normalizedUserRole.endsWith('qa');
if (isQaRole) {
    showNotification('warning', 'QA users cannot apply for Operator membership.');
    return;
}
```

#### 3.1.5 Upload.js — 未登录用户提示

```js
{isLoggedIn ? 'No tasks in this scenario.' : 'Please log in to view upload tasks.'}
```

---

### 3.2 `7d994d0` — PRIS-136: QA Review 访问权限放开

**文件：** `DataHub.js`

#### 3.2.1 `canAccessQAReview` 逻辑变更

| 旧逻辑 | 新逻辑 |
|--------|--------|
| 仅 `qa / senior qa / expert qa` 角色 | `isLoggedIn && !isOperator`（任意登录用户，Operator 除外） |

#### 3.2.2 `ReviewWorkspace` 无权限提示细化

| 场景 | 提示文案 |
|------|---------|
| 未登录 | Please log in to access Review Datasets. |
| Operator | This area is not available to Operators. |
| 其他 | Unable to access Review Datasets. |

#### 3.2.3 导航栏 Review 标签样式

`navItemDisabled` 只在 `isOperator` 时应用（不再对所有非 QA 用户 disable）。

---

### 3.3 `5e46c7a` — DataHub 加载性能优化

**文件：** `DataHub.js`

#### 3.3.1 task list 与 machine list 解耦

原流程：`Promise.all([fetchTaskList, fetchMachineList])` 串行等待两者。

新流程：
- `loadMachineData`：独立 `useCallback`，仅在 `isUploadRoute` 时执行，支持 `isCancelled` 回调
- `loadReferenceData`：只负责 task list，`void loadMachineData()` 异步触发但不等待

#### 3.3.2 `ensureQaUploads` 触发条件放宽

原：仅在 `isReviewRoute` 时触发  
新：无条件触发（函数内部已有 `canAccessQAReview` 检查）

**意图：** 进入 DataHub 即预加载 QA uploads，不再等到用户切换至 review 路由。

#### 3.3.3 未登录状态立即清空

```js
if (!gatewayToken) {
    setDataTasks([]);
    setDataMachines([]);
    setIsDataLoading(false);
    return;
}
```

---

### 3.4 `1b83d0a` — 前端展示上线日期计数 & Explorer 提前拦截

**文件：** `DataQAReview.js`

#### 3.4.1 `formatLaunchDateShort` 工具函数

将 ISO 日期格式化为 `"June 23"` 短格式，用于展示文案。

#### 3.4.2 review 计数文案更新

```
"X reviews completed since June 23"
```

从后端 `qa_launch_date` 字段动态获取日期。

#### 3.4.3 Explorer Member 提前拦截

在提交评审流程最开头增加：
```js
if (userClass === 'Explorer Member') {
    setShowValidatorAccessModal(true);
    return;
}
```

**意图：** Explorer 无需发出 API 请求，直接弹出升级提示弹窗。

---

### 3.5 `bdee463` — Upload 任务卡片渲染优化

**文件：** `Upload.js`

#### 3.5.1 场景 Filter 默认值

`scenarioFilter` 为空时，自动 fallback 到 `tasks[0]` 的 environment，避免空列表。

#### 3.5.2 清除过期视频元数据

过滤条件变化时清空 `previewDurations` 和 `previewVideoRefs`，防止旧时长标签残留。

#### 3.5.3 渲染提取局部变量

将 `getTaskPreviewVideoUrl(task)` 和 `String(task.task_id)` 提取为 `taskPreviewUrl` / `taskKey`，避免 JSX 内重复调用。

---

## 四、测试策略

### 4.1 总体原则

| 维度 | 说明 |
|------|------|
| **重点** | 访问控制变更（Operator/Explorer/QA/未登录）、QA Review 上线配额计数、积分展示 |
| **风险等级高** | `canAccessQAReview` 逻辑变更影响所有用户角色；`QA_LAUNCH_DATE` 计数过滤影响配额限制 |
| **环境** | 需覆盖 staging 环境，各角色账号：未登录、Explorer、Innovator、Amplifier、Operator、QA、Senior QA |
| **回归** | 原有 Upload、DataHub 导航、积分展示功能不能退化 |

### 4.2 测试分类

```
E2E（用户流程）
├── 访问控制
│   ├── VLA Foundry 入口
│   ├── QA Review 入口
│   └── Operator 申请门禁
├── QA Review 核心流程
│   ├── Review 计数展示（上线日期过滤）
│   ├── Explorer 拦截弹窗
│   └── 积分展示
├── MCAP 校验（TOK2 vs 非 TOK2）
└── Upload 页面
    ├── 场景 filter
    └── 任务卡片渲染
```

---

## 五、E2E 测试条目

| ID | 分类 | 用例名称 | 角色 / 前提 | 操作步骤 | 预期结果 | 优先级 |
|----|------|---------|------------|---------|---------|--------|
| TC-01 | 🔐 访问控制 | 未登录用户访问 VLA Foundry | 未登录 | 点击左侧导航栏"VLA Foundry" | 跳转至 `/data/upload`；任务列表显示"Please log in to view upload tasks." | P1 |
| TC-02 | 🔐 访问控制 | 未登录用户访问 QA Review | 未登录 | 直接访问 `/data/review` | Review 区域显示"Please log in to access Review Datasets."；Review 导航标签**不**为 disabled | P1 |
| TC-03 | 🔐 访问控制 | Explorer 用户访问 QA Review | Explorer Member | 导航至 `/data/review` | 可正常进入 review 页面；进度条展示；文案含"since June 23" | P1 |
| TC-04 | 🔐 访问控制 | Explorer 用户提交评审立即弹升级提示 | Explorer Member，已打开某 episode 评审页 | 点击"Submit"提交按钮 | 立即弹出 `ValidatorAccessModal`；**不**发出 review 提交 API 请求 | P1 |
| TC-05 | 🔐 访问控制 | Operator 用户访问 QA Review | Operator | 点击导航栏 Review 标签 | Review 标签显示为 disabled；弹出通知"Operators are not able to access Review Datasets."；页面显示"This area is not available to Operators." | P0 |
| TC-06 | 🔐 访问控制 | Operator Account 页面无副作用 | Operator，进入 Account 页面 | 浏览 Account 页面 | 页面功能正常，无异常弹窗（回归验证） | P2 |
| TC-07 | 🔐 访问控制 | QA 用户尝试申请 Operator 资格 | QA / Senior QA / Expert QA，进入 Account 页面 | 点击申请 Operator Membership 按钮 | 弹出 warning"QA users cannot apply for Operator membership."；不进入申请流程 | P1 |
| TC-08 | 🔐 访问控制 | Innovator/Amplifier 用户访问 QA Review | Innovator 或 Amplifier | 导航至 `/data/review` | 可正常进入 review 页面；Review 导航标签不为 disabled | P2 |
| TC-09 | 🔐 访问控制 | Dashboard "Begin Validating" 直接跳转 | 任意登录用户 | 点击 Dashboard 上的"Begin Validating"按钮 | 直接跳转 `/data/review`；不显示"Coming soon"提示 | P0 |
| TC-10 | 📊 QA Review | Review 计数只统计上线日后 | QA 用户，上线前后均有 review 记录 | 进入 `/data/review`，查看 Validator Status 区域 | `reviewsDone` 只统计 `2026-06-23 16:00 UTC` 之后的 review；文案显示"X reviews completed since June 23" | P0 |
| TC-11 | 📊 QA Review | QA 配额限制只计上线后 review | QA 用户，上线前已提交超过配额上限的 review | 上线后尝试提交新的 review | 系统不因历史数据拦截；用户可正常提交新 review（直到新计数达上限） | P0 |
| TC-12 | 📊 QA Review | 历史积分展示不受 episode 状态影响 | 用户在上线前已获 QA 积分，对应 episode 状态非 SUCCEEDED | 进入 Episode Earnings 页面 | 上线前已发放积分正常显示（`status: "granted"`）；`total_points` 正确累计 | P2 |
| TC-13 | 📊 QA Review | QA 积分发放幂等性 | 同一 upload 已完成 final decision 并发放过积分（需构造并发或手动二次触发场景） | 直接在 DB 层验证：对已发放过积分的 upload_id 调用函数后，`data_qa_episode_activity` 中 `point_transaction_id` 无新增重复记录；积分总额不变 | `(user_id, episode_id)` 不重复发放积分；`point_transaction_id` 无新增重复记录 ⚠️ 无独立重跑入口，建议写单元测试覆盖 | P2 |
| TC-14 | 🤖 MCAP 校验 | TOK2 — camera FPS 跳过，joint freq 正常执行 | 上传 `product_name = "TOK2"` 的 MCAP 文件 | 等待 worker 完成 MCAP 校验 | `camera_fps_check.skipped = true`，reason = "Skipped for TOK2"；`joint_avg_freq_above_45hz` 与 joint rolling check 正常执行 | P0 |
| TC-15 | 🤖 MCAP 校验 | 非 TOK2 — 所有校验项全执行 | 上传 `product_name` 非"TOK2"的 MCAP 文件 | 等待 worker 完成 MCAP 校验 | camera FPS check 正常执行（不 skip）；joint freq check 正常执行 | P1 |
| TC-16 | 🤖 MCAP 校验 | 重复文件检测 — DERIVED_READY 正确识别重复 | 数据库存在 `status = 'DERIVED_READY'` 的 episode，文件大小与待上传一致 | 上传相同大小的新文件 | 系统识别为重复文件，返回重复提示 | P1 |
| TC-17 | 🤖 MCAP 校验 | 重复文件检测 — 非 DERIVED_READY 不误判 | 数据库存在 `status` 为 `FAILED`/`PROCESSING` 的 episode，文件大小一致 | 上传相同大小的新文件 | 系统**不**识别为重复文件，允许正常上传 | P2 |
| TC-18 | ⚡ 性能优化 | DataHub — task list 与 machine list 并发加载 | Operator，Network 面板已打开 | 导航至 `/data/upload` | task list 与 machine list 请求**并发**发出；task list 完成后 skeleton 消失，machine list 可稍后到达 | P2 |
| TC-19 | ⚡ 性能优化 | DataHub — 未登录时立即显示空态 | 未登录 | 导航至 `/data/upload` | 无 loading spinner；立即显示"Please log in to view upload tasks." | P2 |
| TC-20 | ⚡ 性能优化 | DataHub — 进入时预加载 QA Uploads | QA 用户，Network 面板已打开 | 直接导航至 `/data/upload` | 进入 DataHub 即发出 QA uploads 预加载请求；切换至 `/data/review` 时无额外延迟 | P3 |
| TC-21 | ⚡ 性能优化 | Upload 页面 — 场景 Filter 默认值回退 | Operator，Upload 有任务，`scenarioFilter` 为空 | 进入 Upload 页面 | 默认展示 `tasks[0]` 所属 environment 的任务，不显示空列表 | P3 |
| TC-22 | ⚡ 性能优化 | Upload 页面 — 过滤切换不残留视频时长标签 | Operator，任务卡片已加载视频预览及时长标签 | 切换 `scenarioFilter` 或 `formatFilter` | 新过滤结果卡片无旧时长数据残留；视频正常重新加载 | P3 |

---

## 六、测试优先级矩阵

| 优先级 | 测试条目 | 原因 |
|--------|---------|------|
| **P0（阻塞发布）** | TC-05、TC-09、TC-10、TC-11、TC-14 | 访问控制核心路径；QA 上线日期计数直接影响用户配额；TOK2 校验策略切换 |
| **P1（高）** | TC-01、TC-02、TC-03、TC-04、TC-07、TC-15、TC-16 | 用户角色权限全面变更；MCAP 校验回归 |
| **P2（中）** | TC-06、TC-08、TC-12、TC-13、TC-17、TC-18、TC-19 | 边界场景；幂等性保护；性能改进 |
| **P3（低）** | TC-20、TC-21、TC-22 | 纯性能优化验证，不影响功能正确性 |
