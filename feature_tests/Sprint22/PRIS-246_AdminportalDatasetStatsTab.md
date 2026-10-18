# PRIS-246 Admin Portal Dataset Stats Tab 测试分析

> 文档状态：基于前后端仓库全量 Dataset Stats 逻辑 Review 的测试设计（不以某段 Commit Range 为边界）  
> 分析日期：2026-07-16  
> 前端分支/HEAD：`app-prismax-rp/testing@b3b78039ed7f41943cac175483589e4cb52bbb45`  
> 后端分支/HEAD：`app-prismax-rp-backend/testing@e273846a3d92839de34e8412bd3738a9796e316f`  
> 前端入口：Admin Portal → Dataset Stats  
> 相关 API：`GET /data/admin/dataset-stats`、`GET /data/admin/dataset-stats/export`

## 1. 功能范围

PRIS-246 在 Admin Portal 中新增 Dataset Stats Tab，用于按 Task、Robot、Operator 和时间范围查看 Data Episode 统计，并导出与当前筛选条件一致的 CSV。

页面包含：

- Robot Type 下拉框。
- Operator ID 输入框。
- Time Span：`1W`、`1M`、`1Y`、`All`、`Custom`。
- Custom From/To 日期。
- 默认选中的 `Hide test data (task_id 12)`。
- Task 列表及每个 Task 的 Episode Count。
- 5 个 Summary 指标：Episodes、With Duration、Failure Rate、Mean Duration、Total Duration。
- Duration Distribution Histogram。
- Review Status：PASS/FAIL Count 和 Percentage。
- Failure Comments：失败标签、Count、占全部 Failure Label 的 Percentage。
- 使用当前筛选条件的 CSV Download。

不在本测试范围：

- 修改 Episode、Task、Upload 或 QA 结果。
- 重复视频审核操作本身。
- 非 Dataset Stats 的其他 Admin Portal Tab。

### 1.1 全量 Review 范围

本次从当前仓库 HEAD 重新检查 Dataset Stats 的完整调用链，而不是只检查最近 Commit 中的 Diff：

| 层级 | 已 Review 的实现 |
| --- | --- |
| Admin 入口与 Token | `AdminPortal.js`、`ConnectWalletHeader.js`、`authErrors.js` |
| Dataset Stats 页面 | `DatasetStatsAdmin.js`、`DatasetStatsAdmin.module.css`、现有 Jest Test |
| 前端 API 封装 | `datasetStatsAdmin.js` 的 Query Builder、JSON 读取、错误处理和 CSV 下载 |
| 后端路由 | `/data/admin/dataset-stats`、`/data/admin/dataset-stats/export` |
| 后端公共逻辑 | Query Parser、Episode Query、Payload、Failure Label、Histogram、Percentage、Admin JWT |
| 数据依赖 | `data_episodes`、`data_uploads`、`data_tasks`、`data_machines` 的 Join 和字段使用 |
| 上游联动 | Upload 创建及时间字段、Duplicate Review 对 Episode Status/`processing_error` 的改写 |

仓库内没有独立的后端 Dataset Stats 自动化测试；前端现有测试只覆盖 Percentage Normalization 的两个场景，因此下文用例同时覆盖缺失的 Unit、API Integration 和 E2E 层。

## 2. 代码实现与统计口径

### 2.1 数据来源和基础过滤

主查询关联：

```text
data_episodes e
  INNER JOIN data_uploads u       ON u.upload_id = e.upload_id
  LEFT JOIN data_tasks t          ON t.task_id = e.task_id
  LEFT JOIN data_machines m       ON m.machine_id = u.machine_id
```

只统计以下 Episode Status：

- `DERIVED_READY`
- `DERIVED_VALIDATION_FAILED`
- `FAILED`

其他状态，例如 `UPLOADED`、`DERIVING`，不会进入 Summary、Task Count、Robot Option 或 CSV。

注意：因为 `data_uploads` 使用 INNER JOIN，不存在对应 Upload 的孤立 Episode 不会进入统计。

### 2.2 Review Status 映射

| Episode Status | Dataset Stats Review Status |
| --- | --- |
| `DERIVED_READY` | `PASS` |
| `DERIVED_VALIDATION_FAILED` | `FAIL` |
| `FAILED` | `FAIL` |

因此当前页面的 PASS/FAIL 是 Pipeline Episode Status 映射，不是直接读取人工 QA Vote。

### 2.3 Summary 计算

| 字段 | 计算规则 |
| --- | --- |
| `episode_count` | 当前筛选结果的 Episode 行数 |
| `with_duration_count` | `video_duration_hours` 可转换为数字的 Episode 数 |
| `pass_fail_count` | PASS Count + FAIL Count；当前基础状态过滤下通常等于 `episode_count` |
| `failure_rate` | FAIL Count ÷ `pass_fail_count`；无数据时为 0，API 返回 Ratio，例如 `0.1` 表示 10% |
| `total_duration_s` | 所有有效 Duration 秒数求和后保留 1 位小数 |
| `mean_duration_s` | `total_duration_s` ÷ `with_duration_count`，保留 1 位小数 |

单个 Duration 的转换规则：

```text
duration_s = round(float(video_duration_hours) × 3600, 4)
```

无效或 Null Duration 不进入时长统计分母，但 Episode 仍进入 Episode Count 和 PASS/FAIL。

### 2.4 Duration Histogram

- 无有效 Duration：返回空 `histogram` 和 `['0','0','0']`。
- 所有 Duration 相等：返回 1 个 Bin，Count 为全部有效 Duration 数。
- Duration 不同：使用 18 个等宽 Bin。
- 最大值强制进入最后一个 Bin，避免数组越界。
- 每个 Bin 返回 `bin_start_s`、`bin_end_s`、`count`。
- X Axis 返回 Min、Mid、Max 三个四舍五入后的文本值。

### 2.5 Failure Label 优先级

只有 FAIL Episode 生成 Failure Label。解析 `processing_error` 的优先级：

1. `details.duplicate_review_id` 或 `details.matched_episode_id` → `Duplicate video`。
2. `details.failure_label`。
3. `details.reason`。
4. `details.validation_error_code`。
5. `details.error_code`。
6. `details.failed_checks[0]`。
7. 顶层 `error`。
8. 顶层 `error_message`。
9. 顶层 `step`。
10. 无法解析或无有效字段 → `Failed processing`。

Humanize 会将 `_` 和 `-` 替换为空格并首字母大写，同时去除 `schema schema` 及其后面的内容。

Failure Comments 的 Percentage 分母是所有 Failure Label Count 之和，不是全部 Episode Count。前端会根据显示的 Count 重新计算 Percentage，不直接信任 API Percentage。

### 2.6 Task 和 Robot Option 口径

- Task 列表和 Robot Option 会应用 Status、Task 12、Robot、Operator 和 Time 筛选。
- 生成 Task 列表时会忽略当前选中的 `task/task_id`，以便用户仍可切换其他 Task。
- Robot Option 查询同样忽略当前 Task，但会保留当前 `robot_type` 条件；选择某个 Robot 后，接口通常只返回 `All robots + 当前 Robot`，不能直接切换到另一 Robot，必须先切回 All。
- `All tasks` Count 是 Task Query 返回的所有分组 Count 之和。
- SQL 的 Task 表达式是 `COALESCE(t.scenario, CONCAT('Task ', e.task_id::text), 'Unknown task')`。PostgreSQL `CONCAT` 会忽略 Null，因此 Null Task ID 的实际 SQL 值是 `Task `，而不是 `Unknown task`；空 Scenario 也会产生空字符串。Payload 只会把空字符串改为 `Unknown task`。
- SQL 的 Robot 表达式同理：Null Machine ID 的实际值是 `Machine `，空 Product Name 会在 Payload 阶段变成 `Unknown robot`。
- Task Sidebar 使用 Task Name 作为 React `key` 和 API Filter，而不是 Task ID；同名 Scenario 会被 SQL Group 合并，且不能区分点击。
- Task Filter 是大小写敏感的精确匹配；Robot Filter 是大小写不敏感的精确匹配。

### 2.7 前端交互实现

- 页面打开后默认自动请求数据。
- 任何 Filter、Task 或日期变化都会立即触发新请求。
- 前端通过 `AbortController` 取消上一请求，通常可避免旧响应覆盖新 Filter；但旧请求的 `finally` 仍可能在新请求期间执行 `setIsLoading(false)`，存在 Loading 状态提前结束的竞态，需要单独验证。
- Operator ID 输入没有 Debounce，每次按键都会触发请求。
- 切换 Hide Task 12 会自动将 Active Task 重置为 `All tasks`。
- API Session Expired 会广播 `ADMIN_SESSION_EXPIRED_EVENT`。
- CSV 下载期间按钮变为 `Downloading...` 并 Disable，避免重复点击。
- API 普通加载失败时，当前实现会清空 Stats，但不显示明确的 Error Message；页面继续显示 Loading Placeholder。这是需要验证并建议修复的 UX 问题。
- Stats API 对 HTTP 2xx 空 Body/非预期 Schema 没有严格 Contract 校验：空 Body 会被当作空对象并渲染为全 0；字段类型异常会由 Normalize 层尽量转换或回退。
- Normalize 会根据 Review 行重新计算 `pass_fail_count`/`failure_rate`，根据 Failure 行重新计算百分比；当 Histogram 非空时，`with_duration_count` 使用 Histogram Count 之和覆盖 Summary 值。
- 当前 Robot 选项或 Active Task 因其他筛选消失时，组件不会自动重置对应 State，需验证 Select/Sidebar 与数据是否出现不一致。

### 2.8 上游数据变化对统计的影响

Dataset Stats 是只读页面，但仓库内以下写操作会改变它的结果：

- Upload Session 创建时，Upload 和 Episode 初始状态为 `UPLOADING`，不会进入 Dataset Stats。
- Stats 时间使用 Upload 的 `COALESCE(uploaded_at, created_at)`，不是 Episode 自身时间，也不是视频采集时间。
- 当同一 Upload 的 `uploaded_at` 从 Null 变为非 Null 时，统计时间会从 `created_at` 切换到 `uploaded_at`；同一 Episode 可能因此进入或离开 Rolling/Custom 时间窗口。
- Duplicate Review 判定为 `DUPLICATED/APPROVED` 时，Source Episode 被改为 `DERIVED_VALIDATION_FAILED`，并写入带 `duplicate_review_id`、`matched_episode_id`、`validation_error_code=duplicate_files` 的 `processing_error`；Stats 应显示 FAIL / Duplicate video。
- Duplicate Review 判定为 `NOT_DUPLICATED/REJECTED` 时，只有当前 Episode 正好是该 Review 产生的 Duplicate Failure，才恢复成 `DERIVED_READY` 并清空 `processing_error`；Stats 应从 FAIL / Duplicate video 变回 PASS。
- Duplicate Review 同时会同步 Upload Status；Dataset Stats 的 PASS/FAIL 仍只读取 Episode Status，Upload Status 仅通过时间字段和 Join 间接参与。

## 3. Admin 鉴权

两个 API 都使用 `_require_admin_jwt()`，必须同时满足：

1. Bearer JWT 有效。
2. JWT Claim `role`（大小写不敏感）等于 `admin`。
3. JWT Identity 对应的 Wallet 存在于 `admin_whitelist`。

预期状态：

| 情况 | HTTP |
| --- | --- |
| Missing、Malformed、Expired JWT | 401，`invalid token` |
| JWT 有效但 Role 非 Admin | 403，`admin access required` |
| Admin Role 但 Wallet 不在 Whitelist | 403，`admin access required` |
| Role 和 Whitelist 均有效 | 200 |

## 4. API Contract

### 4.1 GET `/data/admin/dataset-stats`

#### Query Parameters

| 参数 | 必填 | 默认值 | 后端实现规则 |
| --- | --- | --- | --- |
| `task` | 否 | `All tasks` | 非 `all/all tasks` 时按最终 Task Display Name 精确匹配 |
| `task_id` | 否 | 空 | 必须可转换为整数；存在时优先于 `task`。当前前端不发送此参数 |
| `robot_type` | 否 | `all` | 对请求值 Lowercase 后，与最终 Robot Display Name 的 Lowercase 精确匹配 |
| `operator_id` | 否 | 空 | 与 `CAST(u.user_id AS TEXT)` 精确匹配 |
| `time_span` | 否 | `all` | 允许 `1w`、`1m`、`1y`、`all`、`custom` 或空字符串 |
| `date_from` | 否 | 空 | 仅 `custom` 使用；格式 `YYYY-MM-DD`；当天 00:00 起包含 |
| `date_to` | 否 | 空 | 仅 `custom` 使用；格式 `YYYY-MM-DD`；通过 `< 次日 00:00` 实现结束日期当天包含 |
| `hide_task_12` | 否 | `true` | `false/0/no/off` 表示不隐藏；其他任意值均按隐藏处理，不返回 400 |

补充边界：

- `custom` 允许只传 From、只传 To，或两者都不传。
- `date_from > date_to` 没有显式校验，当前会返回 200 和空结果。
- `1m` 实际定义为过去 30 天，`1y` 为过去 365 天，不是 Calendar Month/Year。
- 时间基准为 `COALESCE(uploaded_at, created_at)`。
- `task_id` 和 `task` 同时存在时只使用 `task_id`。

#### Success Response

```json
{
  "success": true,
  "data": {
    "robot_types": [
      {"value": "all", "label": "All robots"}
    ],
    "tasks": [
      {"name": "All tasks", "count": 100}
    ],
    "summary": {
      "episode_count": 100,
      "with_duration_count": 98,
      "failure_rate": 0.1,
      "pass_fail_count": 100,
      "mean_duration_s": 12.5,
      "total_duration_s": 1225.0
    },
    "histogram": [
      {"bin_start_s": 0.0, "bin_end_s": 2.0, "count": 5}
    ],
    "histogram_x_labels": ["0", "18", "36"],
    "review_status": [
      {"label": "PASS", "count": 90, "percentage": 90.0},
      {"label": "FAIL", "count": 10, "percentage": 10.0}
    ],
    "failure_comments": [
      {"label": "Duplicate video", "count": 5, "percentage": 50.0}
    ]
  }
}
```

### 4.2 GET `/data/admin/dataset-stats/export`

- 使用与 Stats API 相同的 Episode Query 和全部 Filter。
- Response `Content-Type` 为 `text/csv`。
- `Content-Disposition` 为 `attachment; filename=<safe_task>_YYYY-MM-DD.csv`，日期使用 UTC。
- `safe_task` 最长 80 字符；除字母数字、`-`、`_` 外的字符替换为 `_`。
- CSV 按 `recorded_at DESC NULLS LAST, episode_id DESC` 排序。

CSV Header：

```text
episode_id,task,robot_type,operator_id,duration_s,review_status,failure_label,recorded_at
```

字段规则：

- Null/Invalid Duration 输出空字符串。
- PASS 的 `failure_label` 输出空字符串。
- `recorded_at` 输出 ISO Format。
- CSV 当前没有针对以 `= + - @` 开头的 Spreadsheet Formula 做显式 Neutralization，需要作为安全测试重点。

## 5. 测试数据设计

建议创建以下可精确计算的 Fixture：

| 数据 | Task | Robot | Operator | Status | Duration | Processing Error | Recorded At |
| --- | --- | --- | --- | --- | --- | --- | --- |
| E1 | 1 / Pick | YAM | 101 | `DERIVED_READY` | 10s | 空 | 今天 |
| E2 | 1 / Pick | YAM | 101 | `DERIVED_VALIDATION_FAILED` | 20s | Duplicate Review ID | 今天 |
| E3 | 2 / Place | RoArm | 102 | `FAILED` | Null | `validation_error_code=low_fps` | 8 天前 |
| E4 | 12 / Test | YAM | 101 | `DERIVED_READY` | 30s | 空 | 今天 |
| E5 | 2 / Place | RoArm | 102 | `DERIVING` | 40s | 空 | 今天 |
| E6 | Null Task | Null Machine | 103 | `FAILED` | Invalid/Null | 无法解析 JSON | 31 天前 |
| E7 | 同名 Scenario | YAM | 104 | `DERIVED_READY` | 10s | 空 | 366 天前 |
| E8 | 无对应 Upload | — | — | `FAILED` | 10s | Generic Error | 今天 |

默认隐藏 Task 12 时，预期：

- E4 被排除。
- E5 因 Status 被排除。
- E8 因 INNER JOIN Upload 被排除。
- E1、E2、E3、E6、E7 进入 All-time 统计。
- Episode Count = 5。
- PASS = 2，FAIL = 3，Failure Rate = 60%。
- Valid Duration Count = 3，Total = 40s，Mean = 13.3s。

## 6. API 与 E2E 测试用例总表

以下用例基于当前前后端仓库的完整 Dataset Stats 调用链整理。API 和 E2E 用例统一放在一张表中，便于筛选、执行和维护。

| ID | 类型 | 优先级 | 场景 | 测试条件或步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| PRIS246-API-001 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P0 | Missing Token | 不传 Authorization | 401；`success=false`；不返回统计或 CSV |
| PRIS246-API-002 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P0 | Malformed/Expired Token | 无效或过期 Bearer JWT | 401 `invalid token` |
| PRIS246-API-003 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P0 | 非 Admin Role | 有效 JWT，Role=operator | 403 `admin access required` |
| PRIS246-API-004 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P0 | Admin Role 但不在 Whitelist | 有效 Admin Claim，未知 Wallet | 403；不泄露 Admin 数据 |
| PRIS246-API-005 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P0 | 合法 Admin | Admin Claim + Whitelisted Wallet | 200，Schema/CSV 正确 |
| PRIS246-API-006 | `GET /data/admin/dataset-stats/export` | P1 | Spreadsheet Formula Injection | Task/Robot/Error 值以 `= + - @` 开头 | 文件不得在 Spreadsheet 中执行公式；当前代码可能失败，应记录安全缺陷 |
| PRIS246-API-007 | `GET /data/admin/dataset-stats` | P0 | 默认统计 | 无 Query，使用标准 Fixture | 只统计三个允许 Status，默认排除 Task 12；Summary 与预计算一致 |
| PRIS246-API-008 | `GET /data/admin/dataset-stats` | P0 | Status 映射 | Ready、Validation Failed、Failed、Deriving | PASS/FAIL 映射正确；Deriving 不出现 |
| PRIS246-API-009 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P1 | Orphan Episode | Episode 无对应 Upload | 因 INNER JOIN 不进入任何 Count/Option/CSV |
| PRIS246-API-010 | `GET /data/admin/dataset-stats` | P1 | 空结果 | Filter 无匹配数据 | 200；Episode/Duration/Failure 为 0；Histogram=[]；X Label 为 0；无 NaN |
| PRIS246-API-011 | `GET /data/admin/dataset-stats` | P1 | 全 Null Duration | 所有匹配 Episode Duration Null | Episode Count 正常；With Duration=0；Mean/Total=0；Histogram Empty |
| PRIS246-API-012 | `GET /data/admin/dataset-stats` | P1 | 相同 Duration | 三个 Episode 均 10s | Histogram 只有一个 Bin，Count=3，三个 X Label 相同 |
| PRIS246-API-013 | `GET /data/admin/dataset-stats` | P1 | 18 Bin 边界 | Min、Max 和多个边界值 | 共 18 Bin；所有 Count 之和等于 With Duration；Max 进入最后 Bin |
| PRIS246-API-014 | `GET /data/admin/dataset-stats` | P1 | Duration 精度 | 小数 Hour 和不可转换值 | 单项保留 4 位秒精度；Aggregate 按实现保留 1 位；Invalid 不进分母 |
| PRIS246-API-015 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P0 | 默认隐藏 Task 12 | 无或 `hide_task_12=true` | Task 12 不进入 Summary、Task Count、Robot Option、CSV |
| PRIS246-API-016 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P0 | 显示 Task 12 | `hide_task_12=false/0/no/off` 分别执行 | Task 12 进入结果，四个 False Alias 行为一致 |
| PRIS246-API-017 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P1 | 非法 Boolean 实际行为 | `hide_task_12=abc/yes/true/空` | 均按 Hide=True，不应预期 400 |
| PRIS246-API-018 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P0 | Task ID 优先 | 同时传 `task_id=1&task=Place` | 只按 Task ID 1，忽略 Task 文本 |
| PRIS246-API-019 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P1 | 非法 Task ID | `task_id=abc` | 400，`task_id must be an integer` |
| PRIS246-API-020 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P0 | Task Name | `task=Pick` | Summary/Histogram/Status/CSV 只含 Pick；Task Sidebar 仍提供其他可选 Task |
| PRIS246-API-021 | `GET /data/admin/dataset-stats` | P1 | 同名 Scenario | 两个 Task ID 使用同一 Scenario | 使用 `task` 会合并两个 Task；记录当前实现并确认产品预期 |
| PRIS246-API-022 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P0 | Robot Filter | `robot_type=yam` 和不同大小写 | 大小写不敏感精确匹配；其他 Robot 被排除 |
| PRIS246-API-023 | `GET /data/admin/dataset-stats` | P1 | Robot Fallback | Machine 无 Product Name、Machine ID Null、Product Name 空字符串 | 无 Product Name 且有 ID 时为 `Machine <id>`；Null ID 的当前 SQL 实际值为 `Machine `；空 Product Name 在 Payload 中为 `Unknown robot`，同时核对 Option 与 Episode 是否一致 |
| PRIS246-API-024 | `GET /data/admin/dataset-stats` | P0 | Operator Filter | `operator_id=101` | 只统计 User 101；Task/Robot Option 同步缩小 |
| PRIS246-API-025 | `GET /data/admin/dataset-stats` | P1 | Operator 精确匹配和 Trim | `operator_id=0101`、`101 `、`abc` | 请求值会去除首尾空格，因此 `101 ` 匹配 101；`0101` 和 `abc` 不匹配并返回空数据 |
| PRIS246-API-026 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P0 | 1W/1M/1Y | 分别请求 `1w/1m/1y` | 使用过去 7/30/365 天；边界前后数据正确 |
| PRIS246-API-027 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P1 | Uploaded At 优先 | Upload 同时有 Uploaded/Created At | 使用 Uploaded At；仅 Uploaded At Null 时使用 Created At |
| PRIS246-API-028 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P0 | Custom 双边界 | `date_from=2026-07-01&date_to=2026-07-01` | 包含当天 00:00 至 23:59:59，排除 7 月 2 日 00:00 |
| PRIS246-API-029 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P1 | Custom 单边界 | 只传 From，再只传 To | 分别应用下界和上界，不返回参数错误 |
| PRIS246-API-030 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P1 | Custom 无日期 | `time_span=custom` 不传 Date | 200，等价于无时间限制的当前其他 Filter |
| PRIS246-API-031 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P1 | From 晚于 To | From > To | 当前实现返回 200 Empty；建议产品确认是否应改为 400 |
| PRIS246-API-032 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P0 | 非法 Date | `2026/07/01`、无效日期 | 400，Message 指明 `YYYY-MM-DD` |
| PRIS246-API-033 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P0 | 非法 Time Span | `time_span=week` | 400，列出允许值 |
| PRIS246-API-034 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P1 | Case 和空值 | `1W`、`ALL`、空字符串 | Lowercase 后行为正确；空值按 All |
| PRIS246-API-035 | `GET /data/admin/dataset-stats` | P0 | Duplicate 优先 | 有 Duplicate Review ID，同时有其他 Reason | Label=`Duplicate video` |
| PRIS246-API-036 | `GET /data/admin/dataset-stats` | P1 | Detail 优先级 | 同时包含 Failure Label、Reason、Validation Code | 使用 `failure_label` |
| PRIS246-API-037 | `GET /data/admin/dataset-stats` | P1 | Failed Checks | `failed_checks` 有多个元素 | 只使用第一个并 Humanize |
| PRIS246-API-038 | `GET /data/admin/dataset-stats` | P1 | 顶层 Fallback | 分别只有 Error、Error Message、Step | 按优先级产生对应 Label |
| PRIS246-API-039 | `GET /data/admin/dataset-stats` | P1 | 无效 JSON/空对象 | Invalid String、空 JSON、非 Dict | Label=`Failed processing`，API 不报 500 |
| PRIS246-API-040 | `GET /data/admin/dataset-stats` | P1 | Schema Schema 清理 | Label 含 `schema schema` 后缀 | 后缀被清除，前后端显示一致 |
| PRIS246-API-041 | `GET /data/admin/dataset-stats` | P0 | Review Percentage | PASS=90、FAIL=10 | API 为 90%/10%，Failure Rate Ratio=0.1 |
| PRIS246-API-042 | `GET /data/admin/dataset-stats` | P0 | Failure Percentage 分母 | 10 个 Fail：A=6、B=4；另有 90 Pass | Failure A/B 为 60%/40%，不是 6%/4% |
| PRIS246-API-043 | `GET /data/admin/dataset-stats` | P1 | Failure 排序和并列 | 多 Label Count 相同 | Count 降序；相同 Count 按 Label 升序 |
| PRIS246-API-044 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P0 | Stats/CSV 一致 | 两个 API 使用相同 Filter | CSV Episode ID 集合和行数等于 Stats 当前筛选的 Episode 集合 |
| PRIS246-API-045 | `GET /data/admin/dataset-stats/export` | P0 | CSV Header/类型 | 合法 Export | `text/csv`、Attachment Header、8 个 Header 名和顺序正确 |
| PRIS246-API-046 | `GET /data/admin/dataset-stats/export` | P1 | CSV 排序 | 不同 Recorded At 和同时间不同 ID | Recorded At DESC；同时间 Episode ID DESC；Null 最后 |
| PRIS246-API-047 | `GET /data/admin/dataset-stats/export` | P1 | CSV Null 字段 | Null Duration、Task、Robot、Operator | Duration/Operator 空；Task/Robot 按当前 SQL/Payload Fallback（包括 `Task `/`Machine `）输出；CSV 列数不漂移 |
| PRIS246-API-048 | `GET /data/admin/dataset-stats/export` | P1 | Filename 清洗 | Task 含空格、`/`、引号、超 80 字符 | 特殊字符替换，Task 部分最长 80，日期为 UTC Today |
| PRIS246-API-049 | `GET /data/admin/dataset-stats/export` | P1 | CSV 特殊字符 | Scenario/Error 含逗号、引号、换行、Unicode | CSV Writer 正确 Quote，重新读取后字段不破坏 |
| PRIS246-API-050 | `GET /data/admin/dataset-stats/export` | P0 | Export 鉴权和 Filter Error | 无 Token、非法 Date/Task ID | 与 Stats 相同的 401/403/400，不返回伪 CSV |
| PRIS246-API-051 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P0 | Task Fallback 一致性 | Null Task ID、无 Task Row、Scenario 空字符串 | 分别验证 SQL/JSON/Sidebar/CSV 的实际值；Null ID 当前为 `Task `，空 Scenario 在 Payload 为 `Unknown task`，记录 Option 与 Filter 不一致缺陷 |
| PRIS246-API-052 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P1 | Task 大小写和精确匹配 | `Pick`、`pick`、`Pick `、部分字符串 | Query 会 Trim，但匹配大小写敏感且不支持部分匹配 |
| PRIS246-API-053 | `GET /data/admin/dataset-stats` | P1 | Robot Option 自过滤 | 先 All 获取 YAM/RoArm，再请求 `robot_type=YAM` | 数据和 Task 只含 YAM；Robot Option 当前只剩 All + YAM，确认不能直接选择 RoArm 的实现行为 |
| PRIS246-API-054 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P1 | 参数化防注入 | Task/Robot/Operator 传引号、SQL Comment、Unicode | 作为绑定参数处理，不改变 WHERE，不返回额外数据或 500 |
| PRIS246-API-055 | `GET /data/admin/dataset-stats` | P1 | Humanize 后 Label 合并 | `low_fps`、`low-fps` 和大小写变体 | 检查 Humanize 后相同文本是否按最终 Label 合并；Percentage 总和约为 100% |
| PRIS246-API-056 | `POST /data/admin/video-duplicate-reviews/{review_id}/decision`<br>`GET /data/admin/dataset-stats` | P0 | Duplicate Review → FAIL | Source 原为 Ready，执行 DUPLICATED 后请求 Stats | Episode 进入 FAIL，Failure Label=`Duplicate video`，Failure Rate/Count 立即更新 |
| PRIS246-API-057 | `POST /data/admin/video-duplicate-reviews/{review_id}/decision`<br>`GET /data/admin/dataset-stats` | P0 | Reject Duplicate → PASS | 对同一 Duplicate Review 执行 NOT_DUPLICATED | 仅匹配该 Review 的 Duplicate Failure 恢复 Ready/PASS、错误清空；其他 Validation Failure 不得被误恢复 |
| PRIS246-API-058 | `GET /data/admin/dataset-stats` | P0 | Response Schema 完整性 | 正常 Stats | `success=true`；所有固定字段存在且类型正确；Count 非负；Rate/Percentage 范围正确 |
| PRIS246-API-059 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P1 | DB 查询异常 | 模拟连接失败、Timeout、SQL Error | 返回受控 5xx 且不泄露 SQL/凭据；前端不崩溃。当前 Route 无局部异常包装，需记录实际全局错误格式 |
| PRIS246-API-060 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P1 | 大结果集资源占用 | 逐步扩大到生产级 Episode 数 | Stats/Export 当前均 `fetchall()`；记录响应时间、进程内存、CSV 大小和超时点 |
| PRIS246-API-061 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P1 | 时间边界与 DB 时区 | NOW 边界、UTC 午夜、DST/Session Timezone | Rolling Window 与 Custom Date 使用数据库时间语义；确认与产品展示时区一致，无漏一天/多一天 |
| PRIS246-API-062 | `GET /data/admin/dataset-stats` | P1 | 重复 Join 防重 | Task/Machine 主键正常及异常重复 Fixture | 每个 Episode 只计一次；若关联数据异常导致放大，应能通过 Episode ID 集合识别 |
| PRIS246-API-063 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P1 | Wallet 大小写 | JWT Identity 与 Whitelist 地址仅大小写不同 | 当前 SQL 是精确 `=`；记录真实 403 行为并确认 Wallet 是否应 Normalize |
| PRIS246-API-064 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P1 | HTTP Method | POST/PUT/DELETE/OPTIONS | 非允许 Method 不执行统计；CORS Preflight 按环境配置通过，敏感数据不泄露 |
| PRIS246-API-065 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P1 | Recorded Time 切换 | 初始 `uploaded_at=NULL` 后再写入与 `created_at` 不同的时间 | 首次使用 Created At，更新后改用 Uploaded At；Stats 与 Export 在窗口边界同步进入/移出 |
| PRIS246-API-066 | `GET /data/admin/dataset-stats`<br>`GET /data/admin/dataset-stats/export` | P1 | 非法 Duration Domain | 负数、NaN、Infinity、极大值 | 不应产生负时长、NaN/Infinity JSON 或 500；当前代码只检查能否 `float()`，需记录负数/非有限值的实际缺陷 |
| PRIS246-E2E-001 | E2E | P0 | Admin 访问入口 | Admin 登录 → Admin Portal → Dataset Stats | Tab 可见并进入页面；默认发起一次 Stats 请求 |
| PRIS246-E2E-002 | E2E | P0 | 非 Admin 访问 | 普通用户尝试进入 Admin Portal 或直接构造请求 | 无 Dataset Stats 数据；API 403；页面不能绕过权限 |
| PRIS246-E2E-003 | E2E | P0 | Session Expired | 打开页面后使 Admin Token 过期，再切 Filter | 广播 Session Expired，触发现有 Admin 登出/重新认证流程 |
| PRIS246-E2E-004 | E2E | P1 | 默认 UI | 首次打开 | Robot=All、Operator 空、Time=All、Hide Task 12 Checked、Active Task=All tasks |
| PRIS246-E2E-005 | E2E | P1 | Loading | 模拟慢响应 | Sidebar 和 Content 显示 Loading；Download Disabled；无旧数据闪烁 |
| PRIS246-E2E-006 | E2E | P1 | Empty Result | 筛选到无数据 | Summary 为 0，图表/表格安全显示空状态，无 NaN/Infinity |
| PRIS246-E2E-007 | E2E | P1 | API 普通失败 | Stats API 返回 500/Network Error | 记录当前页面只显示 Loading Placeholder、无明确错误的 UX 缺陷；页面不崩溃 |
| PRIS246-E2E-008 | E2E | P0 | Hide Task 12 默认值 | 使用包含 Task 12 数据打开页面 | Task 12 不在列表和 Summary 中，Checkbox 默认选中 |
| PRIS246-E2E-009 | E2E | P0 | 显示 Task 12 | Uncheck Hide Test Data | Active Task 重置 All tasks；Task 12 出现；Summary 和图表更新 |
| PRIS246-E2E-010 | E2E | P0 | Task 切换 | 点击某 Task，再点 All tasks | 标题、Active Style、Summary、Histogram、Review/Failure 同步变化 |
| PRIS246-E2E-011 | E2E | P0 | Robot Filter | 从 All 选择 YAM/RoArm | Task Count 和所有统计只反映所选 Robot；Dropdown Option 正确 |
| PRIS246-E2E-012 | E2E | P0 | Operator ID | 输入合法 Operator ID | 所有内容缩小到该用户；清空恢复 All Operators |
| PRIS246-E2E-013 | E2E | P1 | Operator 高频输入 | 快速输入/删除多个字符 | 旧请求被 Abort，最终页面只显示最后输入对应结果；记录无 Debounce 的请求量 |
| PRIS246-E2E-014 | E2E | P0 | Time Chip | 依次点击 1W、1M、1Y、All | Active Chip 正确；请求参数和数据范围正确 |
| PRIS246-E2E-015 | E2E | P0 | Custom Date | 选择 Custom 并设置 From/To | Date Input 出现；请求携带日期；结果包含结束当天 |
| PRIS246-E2E-016 | E2E | P1 | Filter 组合 | Robot + Operator + Time + Task | 页面所有模块都使用同一 Filter 交集，无某个模块沿用旧条件 |
| PRIS246-E2E-017 | E2E | P1 | 请求竞态 | 连续快速切换 Task/Robot/Time | 被取消的旧响应不能覆盖最后选择；无 React Warning |
| PRIS246-E2E-018 | E2E | P0 | Summary 显示 | 使用预计算 Fixture | 5 个指标与 API/DB 一致；Failure Rate 将 Ratio 正确乘 100 |
| PRIS246-E2E-019 | E2E | P1 | Duration 格式 | Total <1h 和 ≥1h 两组数据 | Mean 固定显示秒；Total <1h 显示秒，≥1h 显示小时 |
| PRIS246-E2E-020 | E2E | P1 | Histogram | 有 18 Bin 和 Equal Duration 两组数据 | Bar 高度/Tooltip/Axis 正确；非零 Count 的 Bar 至少可见 |
| PRIS246-E2E-021 | E2E | P0 | Review Status | PASS/FAIL 比例极端值和普通值 | Count、Bar、Percentage 正确；0.1% 不被错误显示为 10% |
| PRIS246-E2E-022 | E2E | P0 | Failure Comments | 多种 Failure Label | Label 清洗正确；Count 和 `% of labels` 使用 Failure Total 作分母 |
| PRIS246-E2E-023 | E2E | P1 | 无 Failure | 全部 PASS | 显示 `No failure comments.`，页面布局正常 |
| PRIS246-E2E-024 | E2E | P1 | 大数据和长文本 | 大 Count、长 Label、长 Task、多个 Robot | 数字本地化；文本不破坏布局；表格可读且可滚动 |
| PRIS246-E2E-025 | E2E | P0 | 默认 CSV | All Tasks/All Time 点击 Download CSV | 下载成功；文件名/Headers/行数正确；默认不含 Task 12 |
| PRIS246-E2E-026 | E2E | P0 | Filtered CSV | 应用 Robot、Operator、Custom Date、Task 后下载 | CSV 只含当前 Filter 结果，与页面 Episode Count 一致 |
| PRIS246-E2E-027 | E2E | P1 | 防重复下载 | 网络慢时快速多次点击 Download | 第一次后按钮 Disabled 且显示 Downloading；只触发一个有效下载 |
| PRIS246-E2E-028 | E2E | P0 | Export Session Expired | 下载时返回 401 | 触发 Admin Session Expired，不保存错误文件 |
| PRIS246-E2E-029 | E2E | P1 | Export 失败 | 返回 400/500/Network Error | 显示 `Failed to download dataset stats CSV.`；按钮恢复可点击 |
| PRIS246-E2E-030 | E2E | P1 | CSV 内容打开验证 | 用 Spreadsheet 和标准 CSV Parser 打开 | 逗号/引号/Unicode 不错列；日期/Duration/Label 正确；无公式执行 |
| PRIS246-E2E-031 | E2E | P1 | Desktop | 1366×768、1920×1080 | Sidebar、Summary、Histogram、两张表无重叠，Download 可见 |
| PRIS246-E2E-032 | E2E | P1 | Tablet/Mobile | 768×1024、375×667 | 页面可用，Filter/Task/表格可访问，无水平内容丢失或不可达 Action |
| PRIS246-E2E-033 | E2E | P1 | Keyboard | 仅键盘操作所有 Filter、Task 和 Download | Focus 可见、Tab 顺序合理、Enter/Space 可用、Date 有 Label |
| PRIS246-E2E-034 | E2E | P1 | Screen Reader 基础 | 检查 Select、Operator、Date、Checkbox、Button | Accessible Name 正确；状态变化可理解；纯装饰 SVG 不干扰 |
| PRIS246-E2E-035 | E2E | P1 | 大数据性能 | 使用接近 Production 规模数据打开和组合筛选 | 达到约定 API/UI SLA；页面不冻结；内存可接受 |
| PRIS246-E2E-036 | E2E | P1 | 浏览器兼容 | Chrome、Safari、Firefox | Date Input、Blob Download、图表和 Abort 行为一致 |
| PRIS246-E2E-037 | E2E | P1 | Abort Loading 竞态 | 请求 A 很慢，切 Filter 发起 B；让 A 的 Abort/Finally 先完成 | B 完成前 Loading 不应提前消失；若提前消失，记录当前共享 Boolean Loading 的竞态缺陷 |
| PRIS246-E2E-038 | E2E | P1 | Robot 候选收窄 | All 下选择 YAM，再尝试直接选择 RoArm | 当前接口只返回 All + YAM；验证必须先选 All 才能看到 RoArm，并作为可用性问题记录 |
| PRIS246-E2E-039 | E2E | P1 | Active Task 消失 | 选 Task A 后设置不包含 A 的 Operator/Robot | Heading/请求仍是 A，但 Sidebar 无 Active Item；页面不应误显示其他 Task 数据，记录 State 未重置问题 |
| PRIS246-E2E-040 | E2E | P1 | Selected Robot 无结果 | 选 Robot 后组合无匹配 Operator/Date | Select State 与 API 返回 Option 不一致时页面不崩溃；恢复 Filter 后可回到 All |
| PRIS246-E2E-041 | E2E | P1 | 容错 Normalize | Stub 旧字段名、数字字符串、错误 Percentage、缺失字段 | 前端按 Count 重新计算比例并安全回退；不显示 NaN/Infinity |
| PRIS246-E2E-042 | E2E | P1 | 2xx 空/错误 Schema | API 返回 204、空对象、`success=true` 但 Data 缺失 | 记录当前被 Normalize 成全 0 的行为；产品若要求 Contract Error，应创建缺陷 |
| PRIS246-E2E-043 | E2E | P0 | Duplicate Review 联动 | 在 Video Duplicates 将目标 Episode 判为 Duplicate，再返回 Dataset Stats | 无需刷新登录；重新进入/刷新 Stats 后 PASS→FAIL，出现 Duplicate video；Reject 后反向恢复 |
| PRIS246-E2E-044 | E2E | P1 | Admin Role 被撤销 | 页面已打开时从 Whitelist 移除 Admin，再切 Filter | API 403；不得继续显示旧数据；当前不会触发 Session Expired Event，应记录实际 UX |

## 7. 数据库校验 SQL

以下 SQL 用于手工抽查，实际 Schema/时间条件应与测试环境调整：

```sql
-- 默认状态且隐藏 Task 12 的 Episode 总数
SELECT COUNT(*)
FROM data_episodes e
JOIN data_uploads u ON u.upload_id = e.upload_id
WHERE UPPER(COALESCE(e.status, '')) IN (
  'DERIVED_READY', 'DERIVED_VALIDATION_FAILED', 'FAILED'
)
AND COALESCE(e.task_id, -1) <> 12;

-- PASS / FAIL
SELECT
  COUNT(*) FILTER (WHERE e.status = 'DERIVED_READY') AS pass_count,
  COUNT(*) FILTER (
    WHERE e.status IN ('DERIVED_VALIDATION_FAILED', 'FAILED')
  ) AS fail_count
FROM data_episodes e
JOIN data_uploads u ON u.upload_id = e.upload_id
WHERE UPPER(COALESCE(e.status, '')) IN (
  'DERIVED_READY', 'DERIVED_VALIDATION_FAILED', 'FAILED'
)
AND COALESCE(e.task_id, -1) <> 12;

-- Duration 基础值
SELECT
  COUNT(e.video_duration_hours) AS with_duration_count,
  SUM(e.video_duration_hours * 3600) AS total_duration_s,
  AVG(e.video_duration_hours * 3600) AS mean_duration_s
FROM data_episodes e
JOIN data_uploads u ON u.upload_id = e.upload_id
WHERE UPPER(COALESCE(e.status, '')) IN (
  'DERIVED_READY', 'DERIVED_VALIDATION_FAILED', 'FAILED'
)
AND COALESCE(e.task_id, -1) <> 12;
```

## 8. 自动化建议

后端建议使用 Pytest + Flask Test Client：

- `_dataset_stats_parse_query`：参数矩阵和 SQL 条件。
- `_dataset_stats_failure_label`：完整优先级 Parameterized Test。
- `_dataset_stats_histogram`：Empty、Equal、18 Bin、Max Boundary。
- `_dataset_stats_episode_payload`：Duration、Status、Datetime 和 Invalid Value。
- 两个 Route：Admin Auth、Response Schema、CSV、DB Fixture 集成。
- Duplicate Review Decision → Episode Status/Failure Label → Stats 的跨路由集成测试。
- 使用真实 PostgreSQL Test DB 验证 `CONCAT + NULL`、`::text`、Timezone、`NULLS LAST` 等数据库方言行为，不能只 Mock SQLAlchemy Result。

前端建议使用 Jest + React Testing Library：

- 保留现有 Percentage Normalization Test。
- 增加 Query Builder 全参数和 Custom Date Test。
- 增加 Filter Change、Abort Race、Task 12 Reset、Empty/Error State Test。
- 增加 CSV Header Filename、Blob Download、Duplicate Click、Session Expired Test。
- 增加 Summary/Histogram/Failure Table Rendering Test。
- 增加 2xx 空响应/错误 Schema、Robot Option 自过滤、Active Task 消失和 Abort/Loading 竞态测试。
- 现有 Jest 文件实际包含 3 条 Percentage Test，但没有渲染组件或测试 API Query Builder；不应将其视为页面回归覆盖。

建议将以下用例设为 CI P0 Gate：

- `PRIS246-API-001–005`：Admin 鉴权。
- `PRIS246-API-007`：默认统计。
- `PRIS246-API-015–016`：Task 12。
- `PRIS246-API-018`：Task ID 优先。
- `PRIS246-API-028`：Custom Date 当天包含。
- `PRIS246-API-041–042`：Percentage 口径。
- `PRIS246-API-044–045`：CSV 一致性和 Contract。
- `PRIS246-API-056–058`：Duplicate Review 联动和 Response Contract。
- `PRIS246-E2E-001`、`008–010`、`018`、`021–022`、`025–026`、`043`。

## 9. 代码审查发现与待确认问题

### 9.1 建议修复

1. Stats API 普通失败时页面没有明确 Error State，会持续显示 Loading Placeholder。
2. Operator ID 每次输入都会请求 API，建议增加 Debounce。
3. `date_from > date_to` 当前返回 200 Empty，建议前后端增加校验和用户提示。
4. CSV 未显式防止 Spreadsheet Formula Injection，建议对 `= + - @` 开头的文本加安全前缀。
5. 后端支持 `task_id`，前端只传 Task Name；Scenario 重名时会合并多个 Task。
6. Stats Query 当前把全部匹配 Episode 加载到应用内存后计算，大数据量下需要性能评估或数据库聚合优化。
7. Null Task/Machine 的 SQL Fallback 因 PostgreSQL `CONCAT` 语义实际产生 `Task `/`Machine `，与代码声明的 `Unknown task/robot` 不一致；空字符串又会在 Payload 层变成 Unknown，造成 Option、Filter、JSON 和 CSV 可能不一致。
8. Robot Option Query 保留当前 Robot Filter，选择后候选列表收窄为 All + 当前 Robot，无法一步切换到其他 Robot。
9. 切换 Operator/Robot/Time 后，若 Active Task 已无数据，前端不会自动回到 All Tasks；Active Heading 可能在 Sidebar 找不到对应项。
10. Abort 的旧请求仍会在 `finally` 中清除全局 `isLoading`，快速筛选时可能提前隐藏新请求的 Loading 状态。
11. 前端对 2xx 空 Body/错误 Schema 没有强校验，可能把接口异常静默渲染为 0 数据。
12. Screen Reader 可访问性不足：Robot Select 和 Operator Input 的可见文字不是关联的 `<label>`/`aria-label`，Loading/Error 没有 `aria-live`，Histogram 没有等价的文本数据描述。
13. 当前移动端 CSS 仅把 Lower Grid 改为单列，仍保留 280px 固定 Sidebar 和横向 Flex 布局；375px 等窄屏可能压缩或裁切主内容。
14. Admin Whitelist 被撤销会返回 403 `admin access required`，但前端 Session Expired 判断不识别该信息，页面会停在无明确错误的 Loading Placeholder。
15. Duration 只做 `float()` 转换，没有非负及 `isfinite` 校验；脏数据中的负数、NaN 或 Infinity 可能污染 Summary/Histogram，甚至触发 500。

### 9.2 Product/Dev 待确认

1. `1M`/`1Y` 是否确认代表过去 30/365 天，而不是 Calendar Month/Year？
2. PASS/FAIL 是否确认按 Pipeline Episode Status，而不是人工 QA Vote？
3. Scenario 重名时应合并，还是必须按 Task ID 区分？
4. Custom Date 是否允许单边界和空日期？
5. Task/Robot Option 是否应随当前 Task Filter 缩小，还是保留可切换全集？
6. Dataset Stats 和 CSV 在 Production 数据规模下的响应时间 SLA 是多少？
7. Null/Empty Task、Machine、Scenario、Product Name 在产品上应该显示什么统一名称？
8. Robot 下拉是否应该始终返回其他可选 Robot，而不是被当前 Robot 条件自过滤？
9. Duplicate Review 修改状态后，Dataset Stats 是否要求自动刷新，还是重新进入/手动触发请求即可？
10. 日期筛选的业务时区是 UTC、数据库 Session Timezone，还是用户本地时区？

在以上问题确认前，测试结果应同时记录“当前代码行为”和“最终产品预期”，避免把实现现状误当成已确认需求。
