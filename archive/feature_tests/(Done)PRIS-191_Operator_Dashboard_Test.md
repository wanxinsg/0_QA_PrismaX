# PRIS-191 Operator Dashboard — 完整测试文档

**Feature:** Operator Dashboard  
**Ticket:** PRIS-191  
**最后更新：** 2026-05-14  
**仓库：** `app-prismax-rp`（前端）、`app-prismax-rp-backend / app_prismax_user_management`（后端）  
**测试基准版本：** 前端 `41a5f44`（PR #39 已合并至 `testing`）；后端 `c822a57`（PR #34 已合并至 `testing`）

---

## 目录

1. [功能概述](#1-功能概述)
2. [信息架构与路由](#2-信息架构与路由)
3. [前端组件结构](#3-前端组件结构)
4. [API 设计](#4-api-设计)
5. [数据计算规则](#5-数据计算规则)
6. [测试环境要求](#6-测试环境要求)
7. [测试用例 — API 层](#7-测试用例--api-层)
8. [测试用例 — 前端 E2E（Operator 视角）](#8-测试用例--前端-e2eoperator-视角)
9. [测试用例 — 前端 E2E（Admin 视角）](#9-测试用例--前端-e2eadmin-视角)
10. [测试用例 — 边界与异常](#10-测试用例--边界与异常)
11. [测试用例 — 导航与路由回归](#11-测试用例--导航与路由回归)
12. [数据核对 SQL 参考](#12-数据核对-sql-参考)

---

## 1. 功能概述

### 1.1 背景

Operator Dashboard 是面向机器人数据贡献者（Operator 角色）的**数据上传看板**，替代了原有的独立 History 页面，整合至 `/data/upload/dashboard` 路由下。

### 1.2 核心目标

- 为 Operator 提供所有历史上传的聚合指标（QA 分、总 Episode 数、平均每日时长）。
- 通过趋势图直观展示数据质量与产出变化。
- 分页展示每次上传的详情（任务、时长、通过/失败统计）。
- 允许筛选机器人、按时间范围切换；支持下钻查看每次 upload 的 episode 详情。
- Admin 可用相同界面查看指定 Operator 的 Dashboard。

### 1.3 涉及角色

| 角色 | 说明 | 访问方式 |
|------|------|----------|
| Operator | 机器人数据上传者 | 普通接口（bearer token via `hash_code`） |
| Admin | 平台管理员 | Admin 接口（JWT + `role=admin` claim） |
| 非 Operator / 非 Admin | 其他用户（如 QA） | 导航未展示 Dashboard，不能访问 |

---

## 2. 信息架构与路由

### 2.1 导航变更

**变更前：** Upload Data → 子导航（Upload / **History** / Dashboard）

**变更后：** Upload Data → 子导航（Upload / **Dashboard**）

原 `UploadHistory.js` 组件及其路由已删除。

### 2.2 路由映射

| URL | 渲染组件 | 说明 |
|-----|---------|------|
| `/data/upload` | `DataUpload` | 上传任务主页（默认） |
| `/data/upload/dashboard` | `UploadDashboard` | 本功能所在页面 |
| `/data/upload/history` | `Navigate → /data/upload/history`（顶层重定向） | 旧链路；子工作区不再渲染 History，会落到上传页 |
| `/data/history` | `Navigate → /data/upload/history` | 顶层旧重定向 |

### 2.3 访问权限

`DataHub` 限制 `userRole` 为以下之一方可进入：`operator`、`qa`、`senior qa`、`expert qa`。`UploadDashboard` 本身没有角色二次校验，依赖导航前置过滤。Admin 模式通过 `adminUserId` 属性开启。

---

## 3. 前端组件结构

```
DataHub
└── UploadWorkspace (路由 /data/upload/*)
    ├── 子导航: Upload | Dashboard
    └── isDashboardRoute
        ├── true  → UploadDashboard
        └── false → DataUpload

UploadDashboard
├── 时间范围 pills（7d / 30d / 90d / 1y / all）
├── MetricCard × 3
│   ├── Avg QA Score（颜色编码 + delta）
│   ├── Total Episodes（+ delta %）
│   └── Avg Hrs / Day
├── 图表行
│   ├── QA score trend（折线图，Y 轴 70–100）
│   └── Episode hrs / day（折线图）
├── 上传历史表
│   ├── 机器筛选 MachineDropdown
│   ├── 分页（page_size = 5）
│   └── 表行点击 → EpisodeDrawer
└── EpisodeDrawer（侧边抽屉）
    ├── 头部：upload_id · task_name，元信息 4 格（Upload ID / 时间 / Episodes / QA score）
    ├── 汇总行：accepted + rejected + 进度条
    ├── 筛选栏：All / Accepted / Rejected
    └── Episode 列表（可展开 → 失败原因）
```

### 3.1 QualityScore 颜色规则

| 分值范围 | 颜色 |
|----------|------|
| ≥ 80 | 绿色 `#4caf7d` |
| 60 – 79 | 琥珀色 `#d4a84b` |
| < 60 | 红色 `#e05c5c` |
| null / undefined | 灰色；显示 "Scoring in progress" |

### 3.2 Episode 状态映射

| DB 状态 | `is_derived_ready` | `is_failed` | 前端显示 | Badge 颜色 |
|---------|--------------------|-------------|---------|-----------|
| `DERIVED_READY` | true | false | Accepted | 绿 |
| `DERIVED_VALIDATION_FAILED` / `FAILED` | false | true | Rejected | 红 |
| 其余（`UPLOADING`、`PROCESSING` 等） | false | false | Pending | 灰 |

### 3.3 Episode 失败原因展示规则（`getEpisodeFailureReason`）

优先级：
1. `processing_error.details.failed_checks` → 映射为可读标签，分号连接
2. `processing_error.error_message`（不等于 `'mcap validation failed'`）→ 直接显示
3. `processing_error.step === 'mcap_validation'` → `'MCAP validation failed'`
4. 兜底：`processing_error.error_message` 或 `'Episode failed processing'`

**Check key → 前端文案：**

| check key | 显示文案 |
|-----------|---------|
| `camera_avg_fps_within_0.5_of_target` | Camera avg FPS outside allowed range |
| `camera_max_gap_below_69ms` | Camera frame gap too large |
| `camera_resolution_min_640x480` | Camera resolution below 640x480 |
| `camera_sync_below_34ms` | Camera streams not synchronized |
| `joint_camera_sync_below_34ms` | Joint data not synced with camera frames |
| `joint_avg_freq_above_45hz` | Joint avg frequency too low |

### 3.4 时长展示规则（Upload 表中 Total hrs）

```js
row.total_hrs > 0
  ? (row.total_hrs.toFixed(1) > 0 ? `${row.total_hrs.toFixed(1)} h` : `${row.total_hrs.toFixed(2)} h`)
  : '—'
```

即：保留 1 位小数；若 1 位精度结果 > 0 则用 1 位，否则用 2 位（适用于极小值如 0.005）。

---

## 4. API 设计

### 4.1 接口一览

| 接口 | 方法 | 路径 | 鉴权 |
|------|------|------|------|
| Operator Summary | GET | `/vla/operator-dashboard/summary` | Bearer `gatewayToken`（或 `?token=`） |
| Operator Uploads | GET | `/vla/operator-dashboard/uploads` | 同上 |
| Admin Summary | GET | `/vla/admin/operator-dashboard/summary` | JWT Bearer + `role=admin` |
| Admin Uploads | GET | `/vla/admin/operator-dashboard/uploads` | JWT Bearer + `role=admin` |

### 4.2 鉴权说明

**Operator 接口：** token 从 `Authorization: Bearer <token>` 或 `?token=<token>` 获取，在 `users.hash_code` 列查找对应 `userid`。  
**Admin 接口：** 使用 JWT，`get_jwt()` 中 `role` 字段须为 `admin`（大小写不敏感）。

### 4.3 GET /vla/operator-dashboard/summary

**请求参数：**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| duration | string | 否 | `30d` | 枚举：`7d` / `30d` / `90d` / `1y` / `all`；非法值回退 `30d` |

**成功响应（200）：**

```json
{
  "success": true,
  "data": {
    "duration": "30d",
    "duration_label": "Last 30 days",
    "avg_qa_score": 85.2,
    "avg_qa_score_delta": 3.1,
    "total_episodes": 240,
    "total_episodes_delta_pct": 12.5,
    "avg_hrs_per_day": 0.83,
    "qa_score_trend": [
      { "label": "13 may", "score": 82.0 },
      { "label": "14 may", "score": 88.5 }
    ],
    "episode_hrs_trend": [
      { "label": "13 may", "hrs": 0.50 },
      { "label": "14 may", "hrs": 1.20 }
    ]
  }
}
```

**字段说明：**

| 字段 | 类型 | 为 null 条件 |
|------|------|-------------|
| `avg_qa_score` | float \| null | 无任何 `REVIEW_*_ROUND_SUCCEEDED` upload |
| `avg_qa_score_delta` | float \| null | 当期或上期任一无 QA 数据 |
| `total_episodes` | int | — |
| `total_episodes_delta_pct` | float \| null | 上期 episode 数为 0 |
| `avg_hrs_per_day` | float \| null | `all` 且无有效时长数据时 |
| `qa_score_trend` | array | 空数组表示无 QA 数据 |
| `episode_hrs_trend` | array | 可包含 hrs=0 的桶 |

**错误响应：**

| 场景 | HTTP 状态 | msg |
|------|----------|-----|
| 无 token | 400 | `"token is required"` |
| 非法 token | 401 | `"invalid token"` |

### 4.4 GET /vla/operator-dashboard/uploads

**请求参数：**

| 参数 | 类型 | 必填 | 默认 | 说明 |
|------|------|------|------|------|
| duration | string | 否 | `30d` | 同 summary |
| machine_id | string | 否 | — | 筛选机器；不传或空串表示不筛选 |
| page | int | 否 | `1` | 最小 1 |
| page_size | int | 否 | `10` | 范围 1–50；前端固定传 5 |

**成功响应（200）：**

```json
{
  "success": true,
  "data": [
    {
      "upload_id": 1001,
      "task_id": 42,
      "machine_id": "M001",
      "status": "REVIEW_FIRST_ROUND_SUCCEEDED",
      "created_at": "2026-05-13T03:41:28Z",
      "uploaded_at": "...",
      "task_name": "Pick-and-place task A",
      "product_name": "Airbot Gen2",
      "qa_score": 87,
      "total_hrs": 0.83,
      "episode_summary": {
        "total": 5,
        "derived_ready": 4,
        "failed": 1,
        "pending": 0
      },
      "episodes": [
        {
          "episode_id": 2001,
          "episode_key": "abc123",
          "status": "DERIVED_READY",
          "mcap_size_bytes": 204800,
          "video_size_bytes": 1048576,
          "video_duration_seconds": 597.6,
          "processing_error": {},
          "is_derived_ready": true,
          "is_failed": false
        }
      ]
    }
  ],
  "machines": [
    { "machine_id": "M001", "product_name": "Airbot Gen2" },
    { "machine_id": "M002", "product_name": "Airbot Gen3" }
  ],
  "pagination": {
    "page": 1,
    "page_size": 5,
    "total": 23,
    "total_pages": 5
  }
}
```

**字段说明：**

| 字段 | 说明 |
|------|------|
| `qa_score` | 仅 `REVIEW_*_ROUND_SUCCEEDED` 状态时有值，为最高轮次所有 reviewer 的 `AVG(qa_score)::int`；否则 `null` |
| `total_hrs` | 该 upload 所有 episode 的 `video_duration_seconds / 3600` 之和，保留 2 位小数 |
| `task_name` | 来自 `data_tasks.scenario`；无则 `Task {task_id}`；无 task 则 `'-'` |
| `episode_summary` | `total` / `derived_ready` / `failed` / `pending` |
| `machines` | 该 user 所有 upload 关联机器的去重列表（不受 duration/machine_id 过滤） |

**错误响应：**

| 场景 | HTTP 状态 | msg |
|------|----------|-----|
| 无 token | 400 | `"token is required"` |
| 非法 token | 401 | `"invalid token"` |
| page / page_size 非整数 | 400 | `"invalid pagination params"` |

### 4.5 GET /vla/admin/operator-dashboard/summary

**在 Operator Summary 基础上新增：**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| user_id | int | 是 | 目标 Operator 的 userid；缺失或非整数返回 400 |

**鉴权错误：**

| 场景 | HTTP 状态 | msg |
|------|----------|-----|
| 无有效 JWT | 401 | `"invalid or missing token"` |
| JWT 有效但非 admin | 403 | `"admin access required"` |
| 缺 `user_id` / 非整数 | 400 | `"user_id is required"` |

### 4.6 GET /vla/admin/operator-dashboard/uploads

同 Admin Summary 鉴权；除 `user_id` 外，其余参数与 Operator Uploads 相同。

---

## 5. 数据计算规则

### 5.1 时间范围（duration）

| duration | 当期 SQL | 上期 SQL（用于 delta） |
|----------|---------|----------------------|
| `7d` | `created_at >= NOW() - 7 days` | 前 7–14 天 |
| `30d` | `>= NOW() - 30 days` | 前 30–60 天 |
| `90d` | `>= NOW() - 90 days` | 前 90–180 天 |
| `1y` | `>= NOW() - 365 days` | 前 365–730 天 |
| `all` | 无时间过滤 | 前 days×2 至前 days（使用 30d 的 prior） |

### 5.2 趋势 X 轴分组

| duration | SQL 表达式 | 示例 label |
|----------|-----------|-----------|
| `7d` | `TO_CHAR(created_at, 'Dy')` | `Mon`、`Tue` |
| `30d` / `90d` | `LOWER(TO_CHAR(created_at, 'DD Mon'))` | `13 may` |
| `1y` / `all` | `LOWER(TO_CHAR(created_at, 'YYYY Mon'))` | `2026 may` |

### 5.3 QA 分数来源

```sql
LEFT JOIN LATERAL (
    SELECT AVG(q.qa_score)::int AS qa_score
    FROM data_qa_sessions q
    WHERE q.upload_id = u.upload_id
      AND u.status IN ('REVIEW_FIRST_ROUND_SUCCEEDED',
                       'REVIEW_SECOND_ROUND_SUCCEEDED',
                       'REVIEW_THIRD_ROUND_SUCCEEDED')
      AND q.qa_round = (
          SELECT MAX(q2.qa_round) FROM data_qa_sessions q2
          WHERE q2.upload_id = u.upload_id
      )
) qs ON TRUE
```

- 仅 upload 达到成功态才计分；在途 / 失败 / 未审核的 upload QA score 为 `null`。
- 取最高完成轮次的所有 reviewer 均值（取整）。

### 5.4 时长统计

| 字段 | 公式 | 说明 |
|------|------|------|
| `episode.video_duration_seconds` | `round(video_duration_hours × 3600, 1)` | 来自 DB `data_episodes.video_duration_hours`；0 → `null` |
| `upload.total_hrs` | `sum(video_duration_seconds / 3600)` for all episodes，保留 2 位小数 | 前端 EpisodeDrawer 按秒展示 |
| Summary `avg_hrs_per_day`（固定窗口） | `total_hrs / days_in_window`，保留 2 位小数 | 7d → /7，30d → /30，90d → /90，1y → /365 |
| Summary `avg_hrs_per_day`（`all`） | `total_hrs / max((now - first_upload_date).days, 1)` | 无数据 → `null` |
| `episode_hrs_trend[*].hrs` | 每时间桶 `SUM(video_duration_hours)` | 来自 `data_episodes` JOIN `data_uploads` |

### 5.5 avg_qa_score_delta 详解

`avg_qa_score_delta` = **当前期均值** − **上一个等长周期均值**，用于衡量 QA 分数相比上个周期是否提升或下降。

"上一个等长周期"由后端 `_dashboard_prior_clause` 定义：

| duration | 当前期 | 对比的上期 |
|----------|--------|-----------|
| `7d` | 最近 7 天 | 前 7–14 天 |
| `30d` | 最近 30 天 | 前 30–60 天 |
| `90d` | 最近 90 天 | 前 90–180 天 |
| `1y` | 最近 365 天 | 前 365–730 天 |
| `all` | 全部 | 使用 30d 的对比区间（前 30–60 天） |

#### 举例（duration = 30d，今天 2026-05-14）

**当前期（2026-04-14 ~ 2026-05-14）**

| Upload | 状态 | 最高轮次 reviewer 均值（qa_score） |
|--------|------|---------------------------------|
| Upload A | REVIEW_FIRST_ROUND_SUCCEEDED | 90 |
| Upload B | REVIEW_FIRST_ROUND_SUCCEEDED | 80 |
| Upload C | REVIEW_FIRST_ROUND_SUCCEEDED | 85 |
| Upload D | UPLOADING | null（不参与计算） |

> `avg_qa_score` = (90 + 80 + 85) / 3 = **85.0**

**上期（2026-03-15 ~ 2026-04-14）**

| Upload | 状态 | 最高轮次 reviewer 均值（qa_score） |
|--------|------|---------------------------------|
| Upload E | REVIEW_FIRST_ROUND_SUCCEEDED | 75 |
| Upload F | REVIEW_FIRST_ROUND_SUCCEEDED | 80 |

> `prior_qa` = (75 + 80) / 2 = **77.5**

**结果**

```
avg_qa_score_delta = 85.0 - 77.5 = +7.5
```

前端显示：**↑ 7.5 pts vs prior period**（绿色）

**下降示例：** 当前期均值 72.0，上期均值 80.0 → `delta = -8.0` → 前端显示 **↓ 8.0 pts vs prior period**（红色）

#### delta 为 null 的条件

| 场景 | 原因 |
|------|------|
| 当前期无任何 `REVIEW_*_ROUND_SUCCEEDED` upload | `avg_qa_score` 本身为 null |
| 上期无任何 `REVIEW_*_ROUND_SUCCEEDED` upload | `prior_qa` 为 null |
| 任一为 null | `qa_delta` 不计算，返回 null，前端不显示 delta |

#### 注意：按 episode 数量加权

后端 SQL 是 `data_uploads JOIN data_episodes` 后再做均值，同一个 upload 有多少个 episode，其 QA 分就被计算多少次。例如 Upload A 有 5 个 episode（QA=90）、Upload B 有 1 个 episode（QA=60），实际均值为 (90×5 + 60×1) / 6 = **85.0**，而非简单的 (90+60)/2 = 75.0。测试时核对数值需注意此加权行为，可使用 12 节 SQL 进行验证。

---

## 6. 测试环境要求

### 6.1 账号

| 账号类型 | 用途 |
|----------|------|
| Operator A | 有多次上传记录，含已完成 QA、进行中、UPLOADING 状态 |
| Operator B | 无历史上传（0 数据空态验证） |
| Operator A（多机器）| 名下至少 2 台机器（machine_id 不同） |
| Admin | 有效 JWT token，`role=admin` |
| QA 用户 | 仅有 QA 权限，无 Dashboard 入口 |

### 6.2 数据准备

| 数据类型 | 最小要求 |
|----------|---------|
| 有 QA 分的 upload | 至少 3 条，状态 `REVIEW_FIRST_ROUND_SUCCEEDED`，不同分段（≥80 / 60–79 / <60） |
| 无 QA 分的 upload | 至少 2 条，状态 `UPLOADING` 或 `PROCESSING` |
| 失败 episode | 至少 1 条含 `processing_error.details.failed_checks` 的 episode |
| 含时长的 episode | `video_duration_hours` 有值（非 0 非 null）的 episode ≥ 5 条 |
| 时长为 0/null | 至少 1 条 episode `video_duration_hours` 为 null |
| 多页数据 | Operator A 在某时间范围内 upload 数 ≥ 6（覆盖 page_size=5 的翻页） |
| 不同时间段 | upload 跨越 7d / 30d / 90d 范围分布，验证时间过滤 |
| 状态 `UPLOADING` | 1 条，验证 Continue 按钮出现 |

---

## 7. 测试用例 — API 层

### 7.1 Summary API — Operator 版

| 用例编号 | 用例标题 | 请求 | 预期结果 |
|----------|---------|------|---------|
| API-S-01 | 合法 token + 默认 duration | `GET /vla/operator-dashboard/summary?token=<valid>` | 200；`success:true`；`data.duration="30d"` |
| API-S-02 | Authorization header | `Authorization: Bearer <token>` | 200；与 query param 等价 |
| API-S-03 | duration=7d | `?duration=7d&token=<valid>` | `data.duration_label="Last 7 days"` |
| API-S-04 | duration=90d | `?duration=90d` | `data.duration_label="Last 90 days"` |
| API-S-05 | duration=1y | `?duration=1y` | `data.duration_label="This year"` |
| API-S-06 | duration=all | `?duration=all` | `data.duration_label="All time"` |
| API-S-07 | 非法 duration | `?duration=abc` | 回退 `30d`；200 正常响应 |
| API-S-08 | avg_qa_score 计算 | 有 3 个 SUCCEEDED upload，qa_score 分别 80/90/100（同轮次各 1 个 reviewer） | `avg_qa_score = 90.0`（(80+90+100)/3） |
| API-S-09 | QA delta 正向 | 当期均值 > 上期均值 | `avg_qa_score_delta > 0` |
| API-S-10 | QA delta 负向 | 当期均值 < 上期均值 | `avg_qa_score_delta < 0` |
| API-S-11 | 无 QA 数据 | 无 SUCCEEDED upload | `avg_qa_score: null`；`avg_qa_score_delta: null` |
| API-S-12 | total_episodes 计数 | DB 有 10 个 episode（含所有状态） | `total_episodes = 10` |
| API-S-13 | avg_hrs_per_day 固定窗口 | 30d 内总时长 60h | `avg_hrs_per_day = 2.0`（60/30） |
| API-S-14 | avg_hrs_per_day = all | 首条上传距今 10 天，总时长 5h | `avg_hrs_per_day = 0.5`（5/10） |
| API-S-15 | qa_score_trend 分组 | duration=7d；有周一至周日数据 | label 格式为 `Mon/Tue/...` |
| API-S-16 | qa_score_trend 分组 | duration=30d | label 格式为 `dd mon`，如 `13 may` |
| API-S-17 | qa_score_trend 分组 | duration=1y | label 格式为 `yyyy mon`，如 `2026 may` |
| API-S-18 | episode_hrs_trend | 有时长数据 | 每桶 hrs ≥ 0；与 `SUM(video_duration_hours)` 一致 |
| API-S-19 | 无 token | 无 token header 且无 query param | 400；`msg: "token is required"` |
| API-S-20 | 非法 token | `?token=invalid_hash` | 401；`msg: "invalid token"` |

### 7.2 Uploads API — Operator 版

| 用例编号 | 用例标题 | 请求 | 预期结果 |
|----------|---------|------|---------|
| API-U-01 | 基本请求 | `GET /vla/operator-dashboard/uploads?token=<valid>` | 200；`success:true`；`data` 为数组；含 `pagination`、`machines` |
| API-U-02 | 分页默认 page=1 | — | 返回最多 10 条（默认 `page_size=10`） |
| API-U-03 | page_size=5 | `?page_size=5` | 返回最多 5 条 |
| API-U-04 | page=2 | `?page=2&page_size=5` | 返回第 6–10 条（按 `created_at` 倒序） |
| API-U-05 | page_size 上限 | `?page_size=100` | 实际返回 ≤ 50（后端 `min(50, page_size)`） |
| API-U-06 | page_size 非整数 | `?page_size=abc` | 400；`msg: "invalid pagination params"` |
| API-U-07 | 机器筛选 | `?machine_id=M001` | data 中所有 upload 的 `machine_id = "M001"` |
| API-U-08 | 机器筛选空串 | `?machine_id=` | 返回所有机器的 upload |
| API-U-09 | machines 字段 | 无论是否传 machine_id | `machines` 返回该 user 全部去重机器列表 |
| API-U-10 | pagination 结构 | 有 23 条，page_size=5 | `total=23`；`total_pages=5` |
| API-U-11 | qa_score 有值 | upload status 为 `REVIEW_FIRST_ROUND_SUCCEEDED`，两个 reviewer 分别 80/90 | `qa_score = 85`（AVG 取整） |
| API-U-12 | qa_score 为 null | upload status 为 `UPLOADING` | `qa_score: null` |
| API-U-13 | total_hrs 计算 | 2 个 episode 时长各 0.5h | `total_hrs = 1.0` |
| API-U-14 | video_duration_seconds | `video_duration_hours = 0.1660278` | `video_duration_seconds = 597.7`（0.1660278 × 3600 = 597.7，保留 1 位） |
| API-U-15 | episode_summary 统计 | 5 episodes：DERIVED_READY×3，FAILED×1，UPLOADING×1 | `total=5, derived_ready=3, failed=1, pending=1` |
| API-U-16 | task_name 来源 | task 有 scenario | `task_name = scenario 值` |
| API-U-17 | task_name 无 scenario | task 无 scenario | `task_name = "Task {task_id}"` |
| API-U-18 | task_name 无 task | upload 无关联 task | `task_name = "-"` |
| API-U-19 | 排序 | 多条 upload | 按 `created_at` 倒序（最新在前） |
| API-U-20 | duration 过滤 | `?duration=7d` | 仅返回 7 天内的 upload |
| API-U-21 | 无 token | — | 400 |
| API-U-22 | 非法 token | — | 401 |

### 7.3 Admin API

| 用例编号 | 用例标题 | 预期结果 |
|----------|---------|---------|
| API-A-01 | Admin token + user_id | 200；返回目标 Operator 数据 |
| API-A-02 | 无 JWT | 401；`"invalid or missing token"` |
| API-A-03 | JWT 有效但 role 非 admin（如 role=operator） | 403；`"admin access required"` |
| API-A-04 | 缺 user_id | 400；`"user_id is required"` |
| API-A-05 | user_id 为字符串 | 400；`"user_id is required"` |
| API-A-06 | user_id 不存在 | 200；所有指标为 null/0（无该 user 数据） |
| API-A-07 | 数据一致 | Admin 与 Operator 自查同一账号，同 duration | 两接口返回数据相同 |

---

## 8. 测试用例 — 前端 E2E（Operator 视角）

### 8.1 页面入口与导航

| 用例编号 | 用例标题 | 操作步骤 | 预期结果 |
|----------|---------|---------|---------|
| E2E-NAV-01 | 进入 Dashboard | 登录 Operator 账号 → 点击 Upload Data → 子导航点 Dashboard | 导航至 `/data/upload/dashboard`；页面加载 |
| E2E-NAV-02 | 子导航只有两项 | 进入 Upload Data 区域 | 子导航仅显示 **Upload**、**Dashboard**；无 History |
| E2E-NAV-03 | Upload 子导航跳转 | 在 Dashboard 点 Upload | 跳至上传主页 |
| E2E-NAV-04 | 直接输入 URL | 浏览器输入 `/data/upload/dashboard` | 正常加载 Dashboard |
| E2E-NAV-05 | QA 角色 | 使用 QA 账号登录 | Data Hub 可访问；子导航无 Dashboard 或访问报错（确认产品期望） |

### 8.2 时间范围 Pills

| 用例编号 | 用例标题 | 操作步骤 | 预期结果 |
|----------|---------|---------|---------|
| E2E-DUR-01 | 默认范围 | 首次打开 Dashboard | `Last 30 days` 按钮高亮；指标与图表按 30 天数据加载 |
| E2E-DUR-02 | 切换 7d | 点击 Last 7 days | 按钮高亮切换；summary 与 uploads 发起新请求（`duration=7d`）；分页重置到第 1 页 |
| E2E-DUR-03 | 切换 90d | 点击 Last 90 days | 同上，`duration=90d` |
| E2E-DUR-04 | 切换 This year | 点击 This year | summary duration_label 显示 "This year" |
| E2E-DUR-05 | 切换 All time | 点击 All time | Avg Hrs / Day 副标题显示 "All-time avg" |
| E2E-DUR-06 | 切换时关闭 Drawer | 已打开 EpisodeDrawer 时切换时间范围 | Drawer 关闭（`setSelectedUpload(null)`） |

### 8.3 指标卡（Metric Cards）

| 用例编号 | 用例标题 | 操作步骤 / 数据条件 | 预期结果 |
|----------|---------|-------------------|---------|
| E2E-MET-01 | Avg QA Score 绿色 | 均值 ≥ 80 | 数值显示绿色 |
| E2E-MET-02 | Avg QA Score 琥珀色 | 均值 60–79 | 数值显示琥珀色 |
| E2E-MET-03 | Avg QA Score 红色 | 均值 < 60 | 数值显示红色 |
| E2E-MET-04 | Avg QA Score 正 delta | 当期高于上期 | 显示 `↑ X.X pts vs prior period`（绿色） |
| E2E-MET-05 | Avg QA Score 负 delta | 当期低于上期 | 显示 `↓ X.X pts vs prior period`（红色） |
| E2E-MET-06 | Avg QA Score 无数据 | 无 SUCCEEDED upload | 显示 `—`；无 delta |
| E2E-MET-07 | Total Episodes 计数 | 30d 内有 50 个 episode | 显示 `50` |
| E2E-MET-08 | Total Episodes delta | 上期 40 个，当期 50 个 | 显示 `↑ 25.0% vs prior period` |
| E2E-MET-09 | Avg Hrs / Day 固定窗口 | 30d 总时长 30h | 显示 `1.0 h`；副标题 "Rolling last 30 days avg" |
| E2E-MET-10 | Avg Hrs / Day All time | `all` duration，有时长数据 | 显示计算值；副标题 "All-time avg" |
| E2E-MET-11 | Avg Hrs / Day 无时长 | 所有 episode `video_duration_hours` 为 null | 显示 `—` |
| E2E-MET-12 | 加载态 | 网络延迟期间 | 指标卡显示骨架屏 |
| E2E-MET-13 | 加载失败 | summary API 返回 500 | 指标显示 `—`；不崩溃 |

### 8.4 图表

| 用例编号 | 用例标题 | 操作步骤 / 数据条件 | 预期结果 |
|----------|---------|-------------------|---------|
| E2E-CHT-01 | QA trend 有数据 | 有多个时间桶的 QA 数据 | 折线图正常渲染；hover tooltip 显示具体分值 |
| E2E-CHT-02 | QA trend Y 轴范围 | 任意数据 | Y 轴固定 70–100 |
| E2E-CHT-03 | QA trend 空态 | 无 SUCCEEDED upload | 显示 "No QA data for this period" |
| E2E-CHT-04 | Hrs trend 有数据 | 有多个时间桶的时长数据 | 折线图正常渲染；tooltip 含 `h` 单位 |
| E2E-CHT-05 | Hrs trend 空态 | 所有时长为 0 | 显示 "No data for this period" |
| E2E-CHT-06 | 7d X 轴格式 | duration=7d | X 轴 label 为星期缩写（Mon, Tue...） |
| E2E-CHT-07 | 30d X 轴格式 | duration=30d | X 轴 label 为 `dd mon` 格式 |
| E2E-CHT-08 | 1y X 轴格式 | duration=1y | X 轴 label 为 `yyyy mon` 格式 |
| E2E-CHT-09 | 无动画 | 切换 duration | 图表切换时无过渡动画（`isAnimationActive=false`） |

### 8.5 上传历史表

| 用例编号 | 用例标题 | 操作步骤 / 数据条件 | 预期结果 |
|----------|---------|-------------------|---------|
| E2E-TBL-01 | 列头 | 打开 Dashboard | 表头：Upload ID / Task name / Upload time / Episodes / Total hrs / Quality score / Pass / Fail（共 8 列含 action 列） |
| E2E-TBL-02 | Upload ID 展示 | — | 显示 `upload_id` 数值 |
| E2E-TBL-03 | Task name 来源 | task 有 scenario | 显示 scenario 名称 |
| E2E-TBL-04 | Upload time 格式 | — | 格式：`M/D/YYYY, HH:MM`（24h） |
| E2E-TBL-05 | Episodes 计数 | 5 个 episode | 显示 `5` |
| E2E-TBL-06 | Total hrs — 正常值 | total_hrs=1.5 | 显示 `1.5 h` |
| E2E-TBL-07 | Total hrs — 小值 | total_hrs=0.005 | 显示 `0.01 h`（2 位精度） |
| E2E-TBL-08 | Total hrs — 0 | total_hrs=0 | 显示 `—` |
| E2E-TBL-09 | Quality score — 绿色 | qa_score=90 | 绿点 + 绿色数字 90 |
| E2E-TBL-10 | Quality score — 无分 | qa_score=null | 显示 "Scoring in progress"（灰色） |
| E2E-TBL-11 | Pass/Fail — 有 accepted+rejected | derived_ready=3, failed=1 | 显示 "3 accepted 1 rejected" + 占比色条 |
| E2E-TBL-12 | Pass/Fail — 全 pending | 所有 episode pending | 显示 "Pending review" |
| E2E-TBL-13 | Continue 按钮显示 | upload.status="UPLOADING" | 最右列出现 Continue 按钮 |
| E2E-TBL-14 | Continue 按钮跳转 | 点击 Continue | 跳至 `/data/upload`，携带 `resumeUpload` state（upload_id/task_id/machine_id/status） |
| E2E-TBL-15 | Continue 按钮不显示 | upload.status="DERIVED_READY" | 无 Continue 按钮 |
| E2E-TBL-16 | 空态 | 选中时间范围内无 upload | 显示 "No uploads for this period." |
| E2E-TBL-17 | 加载失败 | uploads API 返回 500 | 表格显示错误文案；不崩溃 |

### 8.6 分页

| 用例编号 | 用例标题 | 操作步骤 | 预期结果 |
|----------|---------|---------|---------|
| E2E-PAG-01 | 每页 5 条 | 有 8 条 upload | 第 1 页显示 5 条；底部 `Showing 5 of 8` |
| E2E-PAG-02 | 翻到第 2 页 | 点击页码 2 | 加载第 6–8 条；`Showing 3 of 8` |
| E2E-PAG-03 | → 按钮 | 当前页 < total_pages | 点击 → 跳到下一页 |
| E2E-PAG-04 | 切换 duration 重置分页 | 在第 2 页切换时间范围 | 回到第 1 页 |
| E2E-PAG-05 | 切换机器重置分页 | 在第 2 页切换机器 | 回到第 1 页 |
| E2E-PAG-06 | 总页数 1 | 只有 3 条 upload | 底部无 → 按钮；仅显示页码 1 |

### 8.7 机器筛选（MachineDropdown）

| 用例编号 | 用例标题 | 操作步骤 | 预期结果 |
|----------|---------|---------|---------|
| E2E-MAC-01 | 默认显示 | 打开 Dashboard | 下拉显示 "All machines" |
| E2E-MAC-02 | 打开下拉 | 点击触发按钮 | 展开机器列表；当前选中项高亮 |
| E2E-MAC-03 | 选择特定机器 | 点击机器名 | 下拉关闭；按钮文本变为机器名；表格重新加载，仅显示该机器 upload |
| E2E-MAC-04 | 选 All machines | 下拉中点 All machines | 不传 `machine_id`；恢复全部 |
| E2E-MAC-05 | 点击外部关闭 | 打开下拉后点外部区域 | 下拉关闭 |
| E2E-MAC-06 | 机器名长截断 | 机器名超过 200px | 以 ellipsis 截断显示 |
| E2E-MAC-07 | 无机器数据 | 该 Operator 无关联机器 | 仅 "All machines" 选项 |

### 8.8 Episode Drawer

| 用例编号 | 用例标题 | 操作步骤 | 预期结果 |
|----------|---------|---------|---------|
| E2E-DRW-01 | 打开 Drawer | 点击表格行 | 右侧弹出 EpisodeDrawer |
| E2E-DRW-02 | Drawer 头部信息 | — | 标题：`{upload_id} · {task_name}`；4 格元信息（Upload ID / Upload time / Episodes / QA score） |
| E2E-DRW-03 | Drawer QA score 颜色 | qa_score=85 | 颜色符合 3.1 节规则 |
| E2E-DRW-04 | Drawer QA score null | qa_score=null | 显示 `—`（灰色） |
| E2E-DRW-05 | 汇总行 accepted | derived_ready=4 | `✓ 4 accepted` |
| E2E-DRW-06 | 汇总行 rejected | failed=1 | `✕ 1 rejected` |
| E2E-DRW-07 | 汇总行 0 rejected | failed=0 | 无 rejected pill |
| E2E-DRW-08 | 进度条 | accepted=4, failed=1 | 填充比例 = 4/5 = 80% |
| E2E-DRW-09 | 筛选 All | 默认或点 All | 所有 episode 显示 |
| E2E-DRW-10 | 筛选 Accepted | 点 Accepted | 仅 `is_derived_ready=true` 的 episode |
| E2E-DRW-11 | 筛选 Rejected | 点 Rejected | 仅 `is_failed=true` 的 episode |
| E2E-DRW-12 | 筛选空结果 | 筛 Rejected 但无失败 episode | 显示 "No episodes to show." |
| E2E-DRW-13 | Episode 编号格式 | episode_key="abc" | 显示 `#abc`（padStart 2 位）；若 episode_key 为空用 episode_id |
| E2E-DRW-14 | Episode 时长 | video_duration_seconds=597.6 | 显示 `597.6s · 3 cams` |
| E2E-DRW-15 | Episode 无时长 | video_duration_seconds=null | 显示 `— · 3 cams` |
| E2E-DRW-16 | Episode badge Accepted | is_derived_ready=true | 绿色 Accepted badge |
| E2E-DRW-17 | Episode badge Rejected | is_failed=true | 红色 Rejected badge |
| E2E-DRW-18 | Episode badge Pending | 两者均 false | 灰色 Pending badge |
| E2E-DRW-19 | 展开失败原因 | 点击 Rejected episode 行 | 展开 "Failure reason" 区域 |
| E2E-DRW-20 | 收起失败原因 | 再次点击 | 收起 |
| E2E-DRW-21 | 失败原因 — failed_checks | check key 存在映射 | 显示对应可读文案，多条分号连接 |
| E2E-DRW-22 | 失败原因 — 未知 check key | check key 无映射 | 原始 key 直接显示 |
| E2E-DRW-23 | 失败原因 — error_message | 无 failed_checks，有 error_message（非 mcap validation failed） | 直接显示 error_message |
| E2E-DRW-24 | 失败原因 — mcap 步骤 | step=mcap_validation | 显示 `MCAP validation failed` |
| E2E-DRW-25 | Accepted episode 不展开失败原因 | 点击 Accepted episode 行 | 点击无展开内容 |
| E2E-DRW-26 | 切换筛选重置展开 | 展开一个 Rejected，切换到 All | 展开状态重置（`setExpandedId(null)`） |
| E2E-DRW-27 | Escape 关闭 | Drawer 打开时按 Escape | Drawer 关闭 |
| E2E-DRW-28 | 点击遮罩关闭 | 点击 Drawer 外部遮罩 | Drawer 关闭 |
| E2E-DRW-29 | 点击 Drawer 内部不关闭 | 点击 Drawer 内部任意位置 | Drawer 不关闭（`stopPropagation`） |
| E2E-DRW-30 | 点击 × 按钮关闭 | 点 Drawer 右上角 × | Drawer 关闭 |
| E2E-DRW-31 | 切换 upload 重置状态 | 关闭再点另一行 | 筛选器回到 All，展开态重置 |
| E2E-DRW-32 | 同行再次点击 | 点击已选中行 | Drawer 关闭（toggle） |

---

## 9. 测试用例 — 前端 E2E（Admin 视角）

| 用例编号 | 用例标题 | 操作步骤 | 预期结果 |
|----------|---------|---------|---------|
| E2E-ADM-01 | Admin 页面加载 | Admin 界面打开 Operator 的 Dashboard（传 `adminUserId`） | 请求走 `/vla/admin/operator-dashboard/*`；`user_id` 附在请求中 |
| E2E-ADM-02 | 数据一致 | Admin 查看 Operator A 与 Operator A 自查 | 同时间范围下数据相同 |
| E2E-ADM-03 | Continue 按钮隐藏 | Admin 模式下 UPLOADING upload | 无 Continue 按钮（`!isAdminMode` 条件） |
| E2E-ADM-04 | 切换 duration | Admin 模式切换时间范围 | `user_id` 始终附带；数据刷新 |
| E2E-ADM-05 | 机器筛选 | Admin 模式筛选机器 | `machine_id` + `user_id` 同时发送 |
| E2E-ADM-06 | Admin token 过期 | JWT 过期 | 请求 401；前端展示错误态 |

---

## 10. 测试用例 — 边界与异常

| 用例编号 | 用例标题 | 操作步骤 / 数据条件 | 预期结果 |
|----------|---------|-------------------|---------|
| E2E-ERR-01 | Summary 请求失败 | 断网或 summary API 500 | 指标卡全部显示 `—`；`summaryError` 状态；不崩溃 |
| E2E-ERR-02 | Uploads 请求失败 | uploads API 500 | 表格显示错误文案；不崩溃 |
| E2E-ERR-03 | 零上传账号 | Operator B（无历史上传） | 指标全 `—` 或 0；图表空态文案；表格 "No uploads for this period." |
| E2E-ERR-04 | 全 null 时长 | 所有 episode `video_duration_hours=null` | avg_hrs_per_day=null（`—`）；total_hrs=0（`—`） |
| E2E-ERR-05 | processing_error 格式异常 | `processing_error` 为损坏 JSON 字符串 | 后端安全解析为 `{}`；前端显示兜底文案 "Episode failed processing" |
| E2E-ERR-06 | total_hrs 极小值 | total_hrs=0.003 | 显示 `0.00 h`（精度兜底）；不显示 `—`（因为 > 0） |
| E2E-ERR-07 | 大量 episode | 单次 upload 有 50 个 episode | Drawer 正常滚动渲染，无性能卡顿 |
| E2E-ERR-08 | 长机器名 | machine_name 超 30 字符 | MachineDropdown 截断显示，下拉选项完整显示 |
| E2E-ERR-09 | 并发翻页 | 快速连续点多个页码 | 以最后一次点击的结果为准；无数据乱序 |
| E2E-ERR-10 | 无 Operator 权限 | 普通用户（非 operator/qa 角色）直接访问 `/data/upload/dashboard` | 不显示 Dashboard；提示无权限或重定向 |

---

## 11. 测试用例 — 导航与路由回归

| 用例编号 | 用例标题 | 操作步骤 | 预期结果 | 优先级 |
|----------|---------|---------|---------|-------|
| E2E-ROT-01 | 旧 History URL | Operator 浏览器输入 `/data/upload/history` | 验证实际落点：Upload 页或 Dashboard（与产品确认期望行为） | P1 |
| E2E-ROT-02 | 旧书签 `/data/history` | 直接访问 | Navigate 重定向链路不报 404 | P1 |
| E2E-ROT-03 | 刷新 Dashboard | 在 `/data/upload/dashboard` 刷新 | 页面正常加载，不跳回首页 | P1 |
| E2E-ROT-04 | 浏览器前进/后退 | 在 Upload 和 Dashboard 之间跳转后 back/forward | 路由状态正确恢复 | P2 |
| E2E-ROT-05 | 上传页子导航 Upload | 在 Dashboard 点子导航 Upload | 跳回上传主页，展示任务列表 | P0 |

---

## 12. 数据核对 SQL 参考

以下 SQL 可用于在测试时直接核对前端展示值与 DB 数据是否一致。

### 12.1 核对指定 user 在 30d 内的 avg_qa_score

```sql
SELECT AVG(qs.qa_score)::float AS avg_qa_score
FROM data_uploads u
LEFT JOIN LATERAL (
    SELECT AVG(q.qa_score)::int AS qa_score
    FROM data_qa_sessions q
    WHERE q.upload_id = u.upload_id
      AND u.status IN (
          'REVIEW_FIRST_ROUND_SUCCEEDED',
          'REVIEW_SECOND_ROUND_SUCCEEDED',
          'REVIEW_THIRD_ROUND_SUCCEEDED'
      )
      AND q.qa_round = (
          SELECT MAX(q2.qa_round) FROM data_qa_sessions q2
          WHERE q2.upload_id = u.upload_id
      )
) qs ON TRUE
JOIN data_episodes e ON e.upload_id = u.upload_id
WHERE u.user_id = :user_id
  AND u.created_at >= NOW() - INTERVAL '30 days';
```

### 12.2 核对 avg_hrs_per_day（30d）

```sql
SELECT SUM(COALESCE(e.video_duration_hours, 0)) / 30 AS avg_hrs_per_day
FROM data_uploads u
JOIN data_episodes e ON e.upload_id = u.upload_id
WHERE u.user_id = :user_id
  AND u.created_at >= NOW() - INTERVAL '30 days';
```

### 12.3 核对单个 upload 的 total_hrs

```sql
SELECT
    u.upload_id,
    ROUND(SUM(
        CASE WHEN e.video_duration_hours > 0
             THEN e.video_duration_hours * 3600
             ELSE 0
        END
    )::numeric / 3600, 2) AS total_hrs
FROM data_uploads u
JOIN data_episodes e ON e.upload_id = u.upload_id
WHERE u.upload_id = :upload_id
GROUP BY u.upload_id;
```

### 12.4 核对 episode_summary

```sql
SELECT
    COUNT(*) AS total,
    COUNT(*) FILTER (WHERE e.status = 'DERIVED_READY') AS derived_ready,
    COUNT(*) FILTER (WHERE e.status IN ('DERIVED_VALIDATION_FAILED', 'FAILED')) AS failed
FROM data_episodes e
WHERE e.upload_id = :upload_id;
```

### 12.5 核对 QA score（最高轮次均值）

```sql
SELECT AVG(q.qa_score)::int AS qa_score
FROM data_qa_sessions q
WHERE q.upload_id = :upload_id
  AND q.qa_round = (
      SELECT MAX(q2.qa_round) FROM data_qa_sessions q2
      WHERE q2.upload_id = :upload_id
  );
```

---

*文档基于源码 `app-prismax-rp@41a5f44` 与 `app-prismax-rp-backend@c822a57` 编写，如后续代码有变更请同步更新。*
