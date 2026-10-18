# Sprint 22 Commit 逻辑改动与 E2E 测试分析

> 分析日期：2026-07-16  
> 前端仓库：`app-prismax-rp`（`testing`）  
> 前端范围：`06640339ae60a9af1d0d2925b9fc16c8383ce5a4`（含）→ `b3b78039ed7f41943cac175483589e4cb52bbb45`  
> 后端仓库：`app-prismax-rp-backend`（`testing`）  
> 后端范围：`c3557869d15d10304dc30467b385a7021e6dad9f`（含）→ `e273846a3d92839de34e8412bd3738a9796e316f`  
> 数据来源：本地 clean worktree；分析期间未执行远端拉取。

## 1. Commit 范围说明

两个指定的起始 SHA 都是 merge commit。本文使用以下范围规则：

1. 包含指定的起始 merge commit，并分析其相对第一父提交引入的逻辑。
2. 包含从起始 commit 到当前本地 `testing` HEAD 之间引入的全部提交，包括后续 merge 带入的功能提交。

这样既不会漏掉隐藏在 merge commit 中的功能改动，也不会把起始点以前无关的历史提交误算进 Sprint 22。

## 2. 总体结论

Sprint 22 涉及多个相互关联的产品模块，而不是单一功能：

- 新增 Data QA 个人进度页，包含个人统计、审核历史、积分和公开排行榜。
- 新增 Admin Dataset Stats 数据面板，支持筛选、隐藏 Task 12、图表、失败原因统计和 CSV 导出。
- 重构重复视频审核流程，按 Upload 分组，支持视频对比、审核决定、分页和用户排名。
- 改进上传失败恢复逻辑，创建 session 后立即保存 Upload ID，并提示用户可以续传。
- 重构 Robotic Data Episode 详情弹窗，支持多相机预览、同步播放、元数据、标签、响应式布局和加载性能优化。
- UI 和 Manifest 下载统一接入会员月度额度；Hex 根据额外视频数量更准确地估算文件数。

最高风险集中在：重复视频决定的数据事务一致性、下载额度并发超卖或重复扣减、排行榜缓存过期、媒体 URL 权限，以及筛选和分页边界。

## 3. Commit List

### 3.1 前端：8 个 Commit

| # | Commit | 日期 | 原始说明 | 主要功能域 |
| --- | --- | --- | --- | --- |
| 1 | `06640339ae60a9af1d0d2925b9fc16c8383ce5a4` | 2026-07-14 | Merge `testing` into PRIS-277 branch | Dataset Stats、Data QA、上传布局 |
| 2 | `0890585b6107750beded0067464ca05439116c9d` | 2026-07-14 | fixing upload bug + added video duplication admin new ui | 上传续传状态、重复视频审核 UI |
| 3 | `428b9408206d6a04c0357cae164770dda27db5b2` | 2026-07-14 | PRIS-277: clean up data review routes | Review 路由和组件迁移、旧 History 删除 |
| 4 | `a60511d956fa95a6e0a04b83a5880cd180b5d1ba` | 2026-07-14 | Merge pull request #65 | QA Progress 和排行榜 UI |
| 5 | `9286d6e5c5896d80cbd60fade2ae1fc7fa1f42d4` | 2026-07-15 | YAM robotic-data view update | YAM 预览显示规则 |
| 6 | `f1607b77a103b784ded0fe9458e63eda4ba52f63` | 2026-07-15 | robotic-data detail modal and speed | Episode 详情、多相机预览、性能优化 |
| 7 | `a8e7fce1aee5f72f18c63fdcd82eaa4c616470c6` | 2026-07-15 | updated ui | Episode 详情 UI 调整 |
| 8 | `b3b78039ed7f41943cac175483589e4cb52bbb45` | 2026-07-15 | added scroll bar | 弹窗内容溢出和滚动 |

### 3.2 后端：8 个 Commit

| # | Commit | 日期 | 原始说明 | 主要功能域 |
| --- | --- | --- | --- | --- |
| 1 | `c3557869d15d10304dc30467b385a7021e6dad9f` | 2026-07-14 | Merge `testing` into PRIS-277 branch | QA 排行榜、Dataset Stats、下载逻辑 |
| 2 | `3898b732b2edb8309ba0a1b925457e08a2833824` | 2026-07-14 | upload bug + video duplication admin | 重复审核分组、决定、用户统计 |
| 3 | `8d5908356c0b1830fc65bfecb9b3c8bd35d7b21a` | 2026-07-14 | Merge remote `testing` | Hex 下载文件数估算 |
| 4 | `0d6961fad35079f1d76884b45e326432ecbd600f` | 2026-07-14 | clean up qa leaderboard code | QA 常量、Helper 和接口清理 |
| 5 | `3366184584248902bcf1b7e902a1445179b514e9` | 2026-07-14 | Merge pull request #53 | QA 进度、历史、排行榜、奖励 |
| 6 | `a922ee021cfa5101ad17bb68176ad1468e53cb06` | 2026-07-15 | restricting the download for all methods | 下载共享月度额度 |
| 7 | `a9e7ba29ac76bf3f50df868ff60e410119af970a` | 2026-07-15 | Merge remote `testing` | 合入 QA 和下载改动 |
| 8 | `e273846a3d92839de34e8412bd3738a9796e316f` | 2026-07-15 | robotic-data speed + detail modal | Preview Video 接口、元数据性能优化 |

## 4. 详细逻辑改动

### 4.1 Data QA 进度、奖励、历史和排行榜

前端改动：

- 在 **Data → Verify Quality → My Progress** 下新增 `ReviewUserProgress` 页面，实际路由为 `/data/review/progress`。
- 展示 Prisma Earned、已审核 Upload 数量、Acceptance Rate、近 7 天积分、排名、会员 Badge 和 Validator 角色。
- 展示排行榜：用户脱敏标识、会员 Badge、审核 Upload 数和 QA 积分。
- 当前用户不在排行榜返回列表中时，将其单独追加为高亮行。
- 审核历史每页 5 条，展示 Quality Score、积分状态和积分值。
- 删除旧 `ReviewHistory`，调整 Review Home 组件目录和路由。

后端改动：

- 新增交易类型 `data_qa_episode_review`，每个符合条件的 Episode 奖励 100 积分。
- 新增内部接口 `POST /data/qa/leaderboard/update`，通过内部 Token 重建 `data_qa_leaderboard`。
- 排序规则：QA 积分降序 → 不重复 Upload 数降序 → User ID。
- 新增 `GET /data/qa/leaderboard`，返回 Top 100 和当前用户 fallback。
- 新增鉴权的个人进度和分页历史接口。
- 零审核用户也可以返回 `you`，其 rank/uploads 为空，但仍可显示已有 QA 积分。
- 公开返回前对 Email 和钱包地址进行截断脱敏。

风险：

- 排行榜依赖定时刷新，可能与实时统计不一致。
- 个人 rank 来自缓存表，而其他统计实时计算，短时间内可能出现数据不一致。
- Review 重试不得重复发放奖励。
- Acceptance Rate 依赖 Upload 终态和 Point Transaction 关联，需验证口径。

### 4.2 Admin Dataset Stats

前端改动：

- Admin Portal 新增 **Dataset Stats** Tab。
- 支持 Robot Type、Operator ID、Task、`1w/1m/1y/all/custom` 时间范围和 Task 12 显隐筛选。
- 默认隐藏 Task 12 测试数据。
- 展示 Episode 数、失败率、平均时长、总时长、时长 Histogram、Review Status 和失败原因分布。
- CSV 导出使用当前筛选条件。
- 支持 Loading、Abort、Empty、Token 失效、API Error 和 Download 状态。

后端改动：

- 新增 Admin-only `GET /data/admin/dataset-stats`。
- 新增 Admin-only `GET /data/admin/dataset-stats/export`。
- 只统计 `DERIVED_READY`、`DERIVED_VALIDATION_FAILED`、`FAILED`。
- `DERIVED_READY` 映射为 PASS，两个失败状态映射为 FAIL。
- 从 Duplicate Detail、Failure Label、Validation/Error Code、Failed Check 或 Processing Error 中生成失败标签。
- 将 `video_duration_hours` 转换为秒，并生成最多 18 个 Histogram Bin。
- 时间筛选使用 `uploaded_at`，为空时使用 `created_at`；自定义结束日期按次日零点排除实现当天包含。
- 导出 Episode 级明细并清洗文件名。

风险：

- Dashboard 和 CSV 必须使用完全相同的筛选结果。
- Robot 筛选使用 Product Name 字符串，大小写或命名变化可能导致不匹配。
- 使用 Scenario 文本筛选 Task，在同名 Scenario 情况下可能混合数据。
- 空时长不能进入平均值分母。
- 当前查询未分页，大数据量下有响应时间和内存风险。

### 4.3 重复视频 Admin Review

前端改动：

- 重构 Duplicate Review 页面，按 Source Upload 分组。
- 增加 Pending 和 All Reviews 筛选。
- Review 列表和 User Stats 分别拥有 Task 12 隐藏开关。
- 每页按 10 个 Upload 分页，而不是按 10 条 Match 分页。
- Upload 可展开/折叠，并展示该 Upload 的所有 Match。
- 展示 Source/Matched 视频、Slot、Score、Task、Machine、Upload ID、状态和时间。
- 支持 **Mark duplicate** 和 **Not a duplicate**。
- 新增用户排名：Detection、Affected Upload、Confirmed Duplicate、Pending Review 和脱敏身份。

后端改动：

- `GET /data/admin/video-duplicate-reviews` 支持 `group_by=review|upload`、status、limit、offset、`hide_task_12`。
- Upload 分页先选择 Source Upload ID，再返回这些 Upload 下的全部 Review。
- Task 12 判断基于 Source Episode/Upload，不受 Matched Episode 影响。
- Source 和 Matched Video 分别生成签名 URL。
- 新增 `GET /data/admin/video-duplicate-review-user-stats`，最大 limit 100。
- Duplicate/Approved 映射为 `APPROVED`；Not Duplicate/Rejected 映射为 `REJECTED`。
- Mark Duplicate 会将 Source Episode 设为 `DERIVED_VALIDATION_FAILED`，并写入结构化 `duplicate_files` 错误。
- Not Duplicate 仅在当前失败由同一个 Review 产生时，将 Episode 恢复为 `DERIVED_READY`。
- 每次决定后重新计算 Source Upload Status。
- Data Worker 只将 `DERIVED_READY` Episode 作为重复检测候选。

风险：

- Review、Episode Status、Processing Error 和 Upload Status 必须在一个事务内一致提交。
- 反转决定不能清除其他原因造成的失败。
- Review Count 和 Upload Count 是不同的分页口径。
- 页面停留时间过长时 Signed URL 可能过期。
- 一个 Episode 多个 Match 产生相反决定时，最终状态可能存在冲突。

### 4.4 上传失败恢复

- Session 创建成功后，前端立即保存 `upload_id`、Task ID 和 Machine ID。
- 后续文件上传或 Finalize 失败时，提示具体 Upload ID 和可续传信息。
- 续传根据 Existing Files 和 Missing Signed URLs 跳过已完成文件。

风险：

- Session 创建前失败时不能提示可续传或虚假的 Upload ID。
- 续传不能创建第二个 Upload 或重复上传已有文件。
- Task/Machine 必须保持为原 Session 的选择。

### 4.5 Robotic Data Workspace 和 Episode Detail

前端改动：

- 新增 Episode Detail，展示 Episode/Task/Robot、数据集 Episode 数、Quality、Duration、文件数、Tags 和选择操作。
- 通过新 Preview API 加载多相机视频。
- 分类并排序 `env`、`left`、`right` 和 Additional Video。
- 当时间差超过约 0.35 秒时，让其他视频跟随主视频同步。
- 增加统一 Play/Pause、Camera Dot、横向滚动、Skeleton、Fallback Image/Video 和 Error State。
- YAM 使用特殊 Crop/展示规则。
- 弹窗使用响应式布局和内部 Scroll，避免内容超出 Viewport。
- Workspace 并发请求 Episode、Task 和 Machine，减少重复媒体发现操作。

后端改动：

- 新增 `GET /data/downloadable-episodes/<episode_id>/preview-videos`。
- 普通用户必须有 Robotic Data 权限；Admin 请求必须使用 Admin JWT。
- 只返回可见 Task 下状态为 `DERIVED_READY` 的 Episode。
- 返回排序后的 Primary Video 和独立的 Additional Video；优先 CDN，否则使用 Signed URL。
- 优先使用 Episode File Metadata，提高加载速度；旧数据保留 GCS List fallback。

风险：

- 未授权用户不能取得媒体 URL。
- 隐藏 Task 和非 Ready Episode 必须返回 404。
- Metadata 不完整时必须正确 fallback。
- 单个 Camera 失败不能导致整个弹窗失败。
- 不同浏览器和移动端的 Autoplay 行为不同。

### 4.6 下载会员额度和文件数估算 (Done)

后端改动：

- UI 和 Manifest Download 与 API Package 共用月度 Episode 额度池。
- 使用 PostgreSQL Advisory Transaction Lock 按 User 防止并发超卖额度。
- UI/Manifest Download 只记录一次会员、Billing Month、授权 Episode 数和授权时间。
- Admin Download 绕过会员额度。
- 无有效 Plan 返回 403；超额度返回 402 和详细 Usage。
- UI 直接下载仍限制 10 个 Episode。
- Manifest 默认限制 800 个文件；特定会员可 Unlimited Manifest。
- 下载 Payload 包含全部 Additional Video，而不仅是三个 Primary Video。

Hex 改动：

- 文件估算改为 `1 个 MCAP + 实际 video_count`，包括 Additional MP4。
- Metadata 缺失但路径存在时，仍 fallback 为每个 Episode 4 个文件。
- 返回总估算文件数、平均文件数、Fallback 基础、各下载方式可用性和月度额度。
- Agent Prompt 明确禁止固定假设每个 Episode 只有 4 个文件。

风险：

- 同一个 Episode 重复下载是否重复消耗额度需要产品确认。
- 下载准备失败不得错误消耗额度。
- UI、Manifest、API Package 和 Hex 的 Used/Remaining 必须一致。
- Metadata 缺失时，Fallback 可能低估包含额外视频的 Episode。

## 5. 新增或改动的 API

### 5.1 API 变更总览

> 下表只列出当前文档保留的 `4.1–4.6` 功能范围。已删除功能域中的 Teleop、OAuth/Payment 和 Hex Capability Request API 不在此处重复列举。

| # | Method | Endpoint | 类型 | 鉴权 | 主要新增或改动 |
| --- | --- | --- | --- | --- | --- |
| 1 | GET | `/data/downloadable-uploads` | 修改 | Robotic Data User | Episode 列表增加实际视频数量等 Metadata，用于详情和文件估算 |
| 2 | POST | `/data/downloadable-uploads/previews` | 修改 | Robotic Data User/Admin | 优先按 File Metadata 定位 Preview，增加 `preview_video_url_type`，旧数据保留 GCS fallback |
| 3 | GET | `/data/downloadable-episodes/<episode_id>/preview-videos` | 新增 | Robotic Data User/Admin | 返回按 Slot 排序的 Primary 和 Additional Video；只允许可见且 `DERIVED_READY` 的 Episode |
| 4 | GET | `/data/admin/video-duplicate-reviews` | 修改 | Admin JWT | 新增 `group_by`、`hide_task_12`，支持按 Upload 分页并返回 Source/Matched Video 详情和 Signed URL |
| 5 | GET | `/data/admin/video-duplicate-review-user-stats` | 新增 | Admin JWT | 返回用户 Duplicate Detection、Affected Upload、Confirmed/Pending 和身份统计 |
| 6 | POST | `/data/admin/video-duplicate-reviews/<review_id>/decision` | 修改 | Admin JWT | Duplicate/Not Duplicate 决定联动 Review、Episode Error/Status 和 Upload Status |
| 7 | GET | `/data/admin/dataset-stats` | 新增 | Admin JWT | 按 Task、Robot、Operator、时间和 Task 12 过滤，返回 Summary、Histogram、Review/Failure 分布 |
| 8 | GET | `/data/admin/dataset-stats/export` | 新增 | Admin JWT | 使用相同过滤条件导出 Episode 级 CSV |
| 9 | GET | `/data/downloads/limits` | 逻辑修改 | Robotic Data User | Usage 口径包含 API Package 与已授权 UI/Manifest Download 的共享月度额度 |
| 10 | POST | `/data/downloads/ui` | 修改 | Operator/符合条件用户；Admin 可绕过额度 | 新增月度 Quota Authorization；超额 402，无 Plan 403；成功响应增加 `quota` |
| 11 | POST | `/data/downloads/manifest` | 修改 | Operator/符合条件用户；Admin 可绕过额度 | 同一共享 Quota；继续检查 Manifest File Cap；Manifest 包含 Additional Video |
| 12 | POST | `/data/qa/uploads/<upload_id>/review` | 修改 | QA Eligible User | Review Final Decision 按有效 Episode 发放 `data_qa_episode_review` 积分，并保证重复处理幂等 |
| 13 | POST | `/data/qa/leaderboard/update` | 修改/启用鉴权 | Internal API Token | 强制校验内部 Token，重建 QA Leaderboard Cache |
| 14 | GET | `/data/qa/leaderboard` | 修改 | Public；可选 `userId` | 返回 Top 100、脱敏身份和当前用户 fallback，包括零 Review 用户 |
| 15 | GET | `/data/qa/progress-stats` | 修改 | QA Eligible User | 返回 QA 积分、Upload 数、Acceptance Rate、近 7 天积分、Rank 和 Validator 信息 |
| 16 | GET | `/data/qa/progress-history` | 修改 | QA Eligible User | 返回分页审核历史、Quality Score、Episode Count、Point 和 `pending/earned/failed` 状态 |
| 17 | GET | `/data/review-history` | 移除 | — | 旧接口删除，由 `/data/qa/progress-history` 替代 |

### 5.2 关键 API Contract

#### Dataset Stats Query

`GET /data/admin/dataset-stats` 和 `/export` 共用以下参数：

| 参数 | 规则 |
| --- | --- |
| `task` | 默认 `All tasks`；非 All 时按 Scenario 文本过滤 |
| `task_id` | 可选整数；存在时优先于 `task` |
| `robot_type` | 默认 `all`，按 Robot Product Name 大小写不敏感匹配 |
| `operator_id` | 可选，按 Upload User ID 文本匹配 |
| `time_span` | `1w`、`1m`、`1y`、`all` 或 `custom` |
| `date_from` / `date_to` | `custom` 时使用，格式 `YYYY-MM-DD`；`date_to` 包含当天 |
| `hide_task_12` | 默认 `true`；`false/0/no/off` 表示不隐藏 |

#### Duplicate Review Query/Decision

- `status`：`PENDING`、`APPROVED`、`REJECTED`、`IGNORED`、`ALL`。
- `group_by`：`review` 或 `upload`；默认 `review`。
- `limit`：1–100；`offset`：非负整数。
- `hide_task_12`：Boolean Query，过滤依据为 Source Episode。
- Decision Body：`{"decision":"DUPLICATED"}` 或 `{"decision":"NOT_DUPLICATED"}`，可附加最长 2000 字符的 `note`。

#### Download Request/Response

- Request 支持 `selected_upload_ids`、`selected_upload_id`、`selected_episode_ids` 或 `selected_episode_id`，具体组合由现有 Download Request Helper 校验。
- UI Download 最多 10 个 Episode。
- Manifest 默认最多 800 个实际 Asset File，除非 Membership 支持 Unlimited Manifest。
- 普通用户成功授权后返回/记录 `membership`、`billing_month`、`monthly_episode_limit`、`used_episodes`、`new_episodes`、`projected_episodes` 和 `remaining_episodes`。
- 超月度额度返回 402；无有效下载会员返回 403；非法选择或超平台 Cap 返回 400。

### 5.3 API Test 用例

#### A. Robotic Data 和 Preview API

| ID | Priority | API | 测试场景 | 请求/数据 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| S22-API-001 | P0 | GET `/data/downloadable-uploads` | 合法用户获取 Catalog | Robotic Data User Token | 200；仅返回允许展示的数据；Episode、Task、Machine、`video_count` 等字段正确 |
| S22-API-002 | P0 | GET `/data/downloadable-uploads` | 未授权访问 | 无 Token、无权限用户 | 返回对应 401/403；不返回 Catalog 数据 |
| S22-API-003 | P1 | POST `/data/downloadable-uploads/previews` | Metadata 快速路径 | Episode 有完整 File Metadata | 200；返回 Preview Video/Image、URL Type；不依赖全目录扫描 |
| S22-API-004 | P1 | POST `/data/downloadable-uploads/previews` | Legacy fallback | Episode 无 Metadata 但 GCS 有 Derived Media | 200；仍能通过 GCS fallback 返回 Preview |
| S22-API-005 | P0 | GET `/data/downloadable-episodes/<id>/preview-videos` | Ready/Visible Episode | 有 Env/Left/Right/Additional Video | 200；Primary 按 Slot 排序；Additional 独立返回；每项包含有效 URL/类型 |
| S22-API-006 | P0 | GET `/data/downloadable-episodes/<id>/preview-videos` | 权限和可见性 | 无权限、Hidden Task、Non-ready、未知 ID | 无权限返回 401/403；其余返回 404；不泄露 Signed URL |
| S22-API-007 | P1 | GET `/data/downloadable-episodes/<id>/preview-videos` | 部分 Camera 缺失 | 只有 Left 或无 Primary 但有 Additional | 200；只返回存在的媒体，结构有效且不报 500 |

#### B. Duplicate Review API

| ID | Priority | API | 测试场景 | 请求/数据 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| S22-API-008 | P0 | GET `/data/admin/video-duplicate-reviews` | Admin 鉴权 | Valid/Expired/Missing Admin JWT | Valid 为 200；Expired/Missing 被拒绝且不返回 Review Data |
| S22-API-009 | P0 | GET `/data/admin/video-duplicate-reviews` | 按 Upload 分页 | `group_by=upload&limit=10&offset=0`，每个 Upload 多个 Match | 返回 10 个 Upload Group 对应的全部 Review；`total_upload_count`、`total_review_count`、`has_more` 正确 |
| S22-API-010 | P1 | GET `/data/admin/video-duplicate-reviews` | Review 分页兼容 | `group_by=review&status=PENDING` | Limit/Offset 按 Review 生效；Pagination Count 口径正确 |
| S22-API-011 | P1 | GET `/data/admin/video-duplicate-reviews` | Task 12 Source 过滤 | `hide_task_12=true`，准备 Source/Matched Task 交叉数据 | 只过滤 Source 为 Task 12 的 Review，Matched Task 不影响结果 |
| S22-API-012 | P1 | GET `/data/admin/video-duplicate-reviews` | 参数边界 | 非法 status/group_by/limit/offset/Boolean | 返回 400 和明确 Message；无 500 |
| S22-API-013 | P1 | GET `/data/admin/video-duplicate-review-user-stats` | 统计与排序 | 多用户、多个 Upload、不同 Review Status | Detection、Distinct Upload、Confirmed、Pending、Total 和排序与 DB 一致 |
| S22-API-014 | P1 | GET `/data/admin/video-duplicate-review-user-stats` | Limit 和 Task 12 | `limit=1/100/101`，切换 `hide_task_12` | Limit 被限制在 1–100；Task 12 过滤口径正确；身份字段正确 |
| S22-API-015 | P0 | POST `/data/admin/video-duplicate-reviews/<id>/decision` | Mark Duplicate | `{"decision":"DUPLICATED","note":"..."}` | 200；Review=`APPROVED`；Source Episode 失败并写入当前 Review ID；Upload Status 同步 |
| S22-API-016 | P0 | POST `/data/admin/video-duplicate-reviews/<id>/decision` | Not Duplicate 并恢复 | 对同 Review 发送 `NOT_DUPLICATED` | 200；Review=`REJECTED`；仅当该 Review 导致失败时恢复 Ready 和清空对应 Error |
| S22-API-017 | P0 | POST `/data/admin/video-duplicate-reviews/<id>/decision` | 不清除无关失败 | Episode 的 Processing Error 来自其他 Review/Validation | Review 更新，但无关 Episode Failure/Error 保留 |
| S22-API-018 | P1 | POST `/data/admin/video-duplicate-reviews/<id>/decision` | 非法和不存在数据 | 非法 Decision、未知 Review ID、超长 Note | 非法为 400；未知为 404；Note 按 2000 字符规则处理 |
| S22-API-019 | P0 | POST Decision | 并发相反决定 | 同时提交 Duplicate 和 Not Duplicate | 无部分事务；最终 Review、Episode、Upload 状态组合一致，可追溯最后成功请求 |

#### C. Dataset Stats API

| ID | Priority | API | 测试场景 | 请求/数据 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| S22-API-020 | P0 | GET `/data/admin/dataset-stats` | Admin 鉴权 | Valid/Invalid/Missing Admin JWT | Valid 为 200；其他请求被拒绝且不泄露统计 |
| S22-API-021 | P0 | GET `/data/admin/dataset-stats` | 默认统计口径 | 不传 Query，含 Task 12 和多状态数据 | 只含三个目标 Episode Status；默认隐藏 Task 12；Summary 与 DB 一致 |
| S22-API-022 | P1 | GET `/data/admin/dataset-stats` | 组合筛选 | Task ID、Robot、Operator、1m/custom 日期 | 返回筛选交集；Task/Robot Option 与筛选范围一致 |
| S22-API-023 | P1 | GET `/data/admin/dataset-stats` | Custom Date 边界 | `date_from=date_to=某天`，含当天 00:00/23:59 和次日 00:00 | 包含指定当天，排除次日零点及以后 |
| S22-API-024 | P1 | GET `/data/admin/dataset-stats` | Duration 和 Failure | Null/相同时长、Duplicate/Error Code/Failed Check | Mean/Total/Histogram 无 NaN；Failure Label 和 Count 正确 |
| S22-API-025 | P1 | GET `/data/admin/dataset-stats` | 非法参数 | 非整数 Task ID、非法 Date/Time Span | 返回 400 和明确错误信息 |
| S22-API-026 | P0 | GET `/data/admin/dataset-stats/export` | CSV 与 JSON 一致 | 对两个接口传完全相同 Query | 200；CSV Episode 集合/行数与 JSON 筛选结果一致；Header 正确 |
| S22-API-027 | P1 | GET `/data/admin/dataset-stats/export` | CSV 文件安全 | Task 名含空格、特殊字符和公式前缀数据 | Filename 被清洗；CSV 结构不破坏；需确认并验证 Spreadsheet Formula Injection 防护 |

#### D. Download API (Done)

| ID | Priority | API | 测试场景 | 请求/数据 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| S22-API-028 | P0 | GET `/data/downloads/limits` | 共享 Usage | 用户同时存在 API Package 和 UI/Manifest 授权记录 | 200；Used 等于两个来源之和；Limit/Remaining 正确 |
| S22-API-029 | P0 | POST `/data/downloads/ui` | 额度内下载 | Active Plan、≤10 个 Ready Episode | 200；Files 完整；响应含 Quota；DB 只写一次授权 Count |
| S22-API-030 | P0 | POST `/data/downloads/ui` | 超月度额度 | Projected > Limit | 402；Data 包含 Limit/Used/New/Projected/Remaining；Download 不为 Ready |
| S22-API-031 | P0 | POST `/data/downloads/ui` | 无 Plan 和平台上限 | 无 Active Plan；或选择 11 个 Episode | 无 Plan 403；超 10 个为 400；均不消耗 Quota |
| S22-API-032 | P0 | POST `/data/downloads/manifest` | 额度和 File Cap 内 | 选择含 Additional Video 且总 Asset ≤800 | 200 JSON Manifest 下载响应；Manifest 包含全部 Asset；Quota 正确记录 |
| S22-API-033 | P0 | POST `/data/downloads/manifest` | File Cap 超限 | 实际 Metadata Asset >800 | 400；不生成 Ready Manifest；不错误占用月度 Quota |
| S22-API-034 | P0 | POST UI/Manifest | 并发额度竞争 | 剩余额度只够一个请求，同时发起两个 | Advisory Lock 生效；一个成功、一个 402；总 Used 不超 Limit |
| S22-API-035 | P1 | POST UI/Manifest | Admin Bypass | Admin 在普通用户额度已满时请求 | 成功；不执行普通用户 Quota Authorization |
| S22-API-036 | P1 | POST UI/Manifest | 无效或不可下载选择 | Missing ID、Non-ready Episode、无完整 Asset | 返回 400；Failed Download 有原因；Quota 未授权 |

#### E. Data QA API

| ID | Priority | API | 测试场景 | 请求/数据 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| S22-API-037 | P0 | POST `/data/qa/uploads/<id>/review` | 完成有效 Review | QA Eligible User，N 个可奖励 Episode | Review 成功；每个 Episode 100 Point；Transaction Type 正确；总计 `N×100` |
| S22-API-038 | P0 | POST Review | 重试和并发幂等 | 相同 Final Decision 重试/并发提交 | 不重复创建 Episode Activity/Point Transaction，不重复加分 |
| S22-API-039 | P0 | POST `/data/qa/leaderboard/update` | Internal Token | Missing/Invalid/Valid Token | 前两者 401；Valid 为 200 并返回准确 Updated Count |
| S22-API-040 | P1 | GET `/data/qa/leaderboard` | Top 100 与脱敏 | 超过 100 个用户，含 Email/Wallet | 只返回 Top 100；排序正确；身份脱敏；无完整敏感值 |
| S22-API-041 | P1 | GET `/data/qa/leaderboard` | Current User fallback | `userId` 不在 Cache、零 Review、未知 User | 有实时数据则返回 `you`；零 Review 返回空 Rank/Upload；未知用户不产生错误 Self |
| S22-API-042 | P0 | GET `/data/qa/progress-stats` | 鉴权和统计 | QA User、非 QA User、无 Token | QA User 200 且各指标与 DB 一致；其他请求按 Role/Auth 拒绝 |
| S22-API-043 | P1 | GET `/data/qa/progress-stats` | Acceptance Rate 边界 | Accepted/Failed/Pending 组合、无终态数据 | 只以终态计算；无分母时返回 Null，不出现除零错误 |
| S22-API-044 | P0 | GET `/data/qa/progress-history` | 分页和 State | `page=1&page_size=5`，准备 Pending/Earned/Failed | 200；总数、顺序、页大小正确；State、Score、Points 正确 |
| S22-API-045 | P1 | GET `/data/qa/progress-history` | Pagination 边界 | Page/Page Size 非数字、0、负数、>100、超末页 | 非法参数按实现返回 400；Size 最大 100；超末页为空且 Total 不变 |
| S22-API-046 | P0 | GET `/data/review-history` | 旧接口下线 | 调用旧路径 | 返回 404；前端和其他调用方不再依赖旧接口，统一使用 Progress History |

### 5.4 建议的 API 自动化实现

- 使用 Pytest + Flask Test Client 覆盖参数、鉴权、状态码和 Response Schema。
- 对 Dataset Stats、Leaderboard、Progress 和 User Stats 使用可控 Fixture，直接核对 SQL 统计结果。
- 对 Duplicate Decision 和 Download Quota 使用真实 PostgreSQL Test Transaction，验证事务、Advisory Lock 和并发行为；仅 Mock SQL 无法覆盖核心风险。
- Mock GCS/CDN URL 生成用于 Contract Test；另保留至少一组集成环境测试验证真实 Signed URL。
- 为所有 401/403/404/400/402 响应增加“不包含敏感业务数据”的断言。
- 将 `S22-API-019`、`S22-API-034`、`S22-API-038` 作为并发/幂等性 P0 Gate。

## 6. 测试策略

### 6.1 测试层级

| 层级 | 范围 | 目标 |
| --- | --- | --- |
| API Contract | 新增/修改接口、鉴权、校验、状态码和 Schema | 尽早发现接口兼容和权限问题 |
| Data Integrity | 奖励、排名、重复决定、Upload Status、Quota Record | 验证跨表一致性和幂等性 |
| Component/Integration | Filter、Normalization、Route、恢复状态和媒体控制 | 验证前端状态与 API 集成 |
| E2E | 基于真实角色的前后端及 Storage 流程 | 验证用户可见的完整流程 |
| Non-functional | 性能、并发、响应式、Signed URL Expiry | 覆盖普通 Happy Path 无法发现的风险 |

### 6.2 测试账号和数据准备

- 有效 Admin Portal Token 的 Admin。
- 有效 Robotic Data Download Membership 的 Operator。
- 接近和达到月度 Quota 的 Operator。
- 无有效 Download Plan 的 Operator。
- 拥有 Completed、Pending、Accepted、Failed Review 的 QA Validator。
- 零 QA Review 用户和排名在 Top 100 之外的用户。
- `DERIVED_READY`、`DERIVED_VALIDATION_FAILED`、`FAILED`、Processing Episode。
- Task 12 和非 Task 12 Upload。
- 三个 Primary Video、Additional Video、Metadata 缺失、Camera 缺失和 Hidden Task Episode。
- 一个 Source Upload 多个 Match、相反/反转决定的 Duplicate Review 数据。

## 7. E2E 测试用例

### E2E 进度跟踪

进度状态：`notstart` | `inprogress` | `pendingfix` | `done`

| 模块 | Case 范围 | 用例数 | 进度 | 备注 |
| --- | --- | --- | --- | --- |
| 7.1 Data QA Progress 和排行榜 | S22-E2E-001 ~ 007 | 7 | notstart | |
| 7.2 Dataset Stats Admin | S22-E2E-008 ~ 014 | 7 | pendingfix | |
| 7.3 Duplicate Review Admin | S22-E2E-015 ~ 022 | 8 | inprogress | |
| 7.4 Upload Resume | S22-E2E-023 ~ 025 | 3 | notstart | |
| 7.5 Robotic Data 和 Episode Modal | S22-E2E-026 ~ 032 | 7 | notstart | |
| 7.6 Download Quota 和 Hex Estimate | S22-E2E-033 ~ 041 | 9 | done | |

### 7.1 Data QA Progress 和排行榜

| ID | 优先级 | 场景 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- |
| S22-E2E-001 | P0 | QA 用户打开 My Progress | Validator 登录 → Data → Verify Quality → My Progress | 个人统计、排行榜、第一页 History 正常加载 |
| S22-E2E-002 | P0 | Review 只奖励一次 | 完成含 N 个有效 Episode 的 QA Review → 刷新 | Prisma 增加 `N × 100`；Upload 只计一次；重试不重复奖励 |
| S22-E2E-003 | P1 | History 分页 | 准备超过 5 条 Review → Next/Previous | 每个完整页 5 条；总数和页码正确；无重复/漏项 |
| S22-E2E-004 | P1 | 当前用户不在 Top List | 使用 Top 100 之外用户打开 My Progress | 返回排行榜，并在末尾追加高亮的当前用户正确排名 |
| S22-E2E-005 | P1 | 零 Review 用户 | 新 QA 用户打开 My Progress | Rank/Uploads/Acceptance 显示 `—` 或空状态，页面不报错 |
| S22-E2E-006 | P0 | 刷新接口鉴权 | 无 Token、错误 Token、正确 Token 调用 Update | 前两者 401；正确 Token 重建并返回 Updated Count |
| S22-E2E-007 | P1 | 公开身份脱敏 | 加载 Email 和 Wallet 用户排行榜 | 不返回完整 Email/Wallet，仅显示截断值 |

### 7.2 Dataset Stats Admin

| ID | 优先级 | 场景 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- |
| S22-E2E-008 | P0 | Admin-only | Admin、普通用户、匿名用户分别访问 | 仅 Admin 可查看；其他用户不泄露数据 |
| S22-E2E-009 | P0 | 默认隐藏 Task 12 | 准备 Task 12 和正常 Episode → 打开页面 | 默认总数不含 Task 12，与 DB 一致 |
| S22-E2E-010 | P1 | 组合筛选 | 选择 Robot、Task、Operator、时间范围 | 所有 Metric/Chart/Task Count 反映筛选交集 |
| S22-E2E-011 | P0 | CSV 与 Dashboard 一致 | 应用筛选 → 记录 Total → 导出 CSV | CSV 行数和记录与页面一致；Header 和文件名正确 |
| S22-E2E-012 | P1 | 失败分类 | 准备 Duplicate、Validation Code、Failed Check、Generic Error | 失败标签和数量正确且可读 |
| S22-E2E-013 | P1 | 空数据和空 Duration | 分别筛选到无记录和无 Duration 记录 | 正确 Empty State；无 NaN 或除零错误 |
| S22-E2E-014 | P1 | 非法 Query | 发送错误 `task_id`、Date、Time Span | 返回 400 和明确 Message，UI 不崩溃 |

### 7.3 Duplicate Review Admin

| ID | 优先级 | 场景 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- |
| S22-E2E-015 | P0 | Upload Group 分页 | 准备 11+ 个 Upload 且每个多个 Match | 第一页 10 个 Upload 且包含其全部 Match；下一页从第 11 个开始 |
| S22-E2E-016 | P1 | 按 Source 隐藏 Task 12 | Task 12 Source 匹配正常 Task，反向再准备一组 | 仅 Source 为 Task 12 的 Group 被隐藏 |
| S22-E2E-017 | P0 | Confirm Duplicate | Pending Match → Mark Duplicate | Review Approved；Episode 失败；结构化 Error 和 Upload Status 原子更新 |
| S22-E2E-018 | P0 | Reject 并恢复 | 先 Mark Duplicate，再对同一 Review 选 Not Duplicate | Review Rejected；仅当该 Review 造成失败时恢复 `DERIVED_READY` |
| S22-E2E-019 | P0 | 保留其他失败 | Episode 已有其他 Validation Failure → Reject Duplicate | 不清除无关 Failure 和 Processing Error |
| S22-E2E-020 | P1 | User Ranking | 准备多用户和多状态 → 切换 Task 12 | Detection、Distinct Upload、Confirmed、Pending、排序和身份正确 |
| S22-E2E-021 | P1 | Signed URL 过期 | 打开两视频 → 模拟 URL 过期/缺失 | 可用视频正常；单个失败不影响页面；刷新可重新取 URL |
| S22-E2E-022 | P0 | 并发相反决定 | 对同一个 Review 几乎同时提交相反决定 | Review、Episode、Upload 最终保持一致，无部分更新 |

### 7.4 Upload Resume

| ID | 优先级 | 场景 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- |
| S22-E2E-023 | P0 | Session 后上传失败 | 创建 Session 后强制一个文件失败 | Error 包含 Upload ID 和续传提示，并保存 Resume Session |
| S22-E2E-024 | P0 | 续传部分上传 | 重试上一失败 Upload | 复用同一 Upload ID；跳过已有文件；补传并 Finalize |
| S22-E2E-025 | P1 | Session 创建前失败 | 强制 Create Session API 失败 | 不提示 Upload ID/续传，不保存无效 Session |

### 7.5 Robotic Data 和 Episode Modal

| ID | 优先级 | 场景 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- |
| S22-E2E-026 | P0 | 多相机详情 | 打开含 Env/Left/Right/Additional 的 Ready Episode | 元数据和相机顺序正确，Files/Tags/Counts 正确 |
| S22-E2E-027 | P1 | 播放同步 | 播放、Seek、Pause、Resume 主视频 | 其他视频在容差内跟随，统一控制有效 |
| S22-E2E-028 | P0 | 权限和可见性 | 授权、未授权、Hidden Task、Non-ready 分别请求 | 授权 Ready 正常；未授权拒绝；Hidden/Non-ready 为 404 |
| S22-E2E-029 | P1 | Legacy Fallback | 打开无完整 Metadata 的旧 Episode | GCS Fallback 成功加载已有媒体 |
| S22-E2E-030 | P1 | YAM 显示 | 分别打开 YAM 和非 YAM | YAM 使用指定 Crop/Left View，其他 Robot 不受影响 |
| S22-E2E-031 | P1 | 响应式和滚动 | Desktop/Tablet/Mobile 打开长内容详情 | 内容可读、内部滚动有效、Action 可访问、背景不误滚 |
| S22-E2E-032 | P1 | 性能基线 | 加载代表性 Catalog，反复打开详情 | 达到约定 SLA；有 Metadata 时不重复全量 Bucket Scan |

### 7.6 Download Quota 和 Hex Estimate (Done)

| ID | 优先级 | 场景 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- |
| S22-E2E-033 | P0 | UI Download 未超额度 | Active Member 下载 ≤10 个且额度足够 | 成功；记录 Membership/Month/Count；Remaining 正确减少 |
| S22-E2E-034 | P0 | Manifest 未超 File Cap | 选择实际 Asset ≤800 的 Episode | Manifest 包含 MCAP、Primary 和全部 Additional Video |
| S22-E2E-035 | P0 | 超月度额度 | 选择使 Projected Usage 超限的数据 | 返回 402 和 Limit/Used/New/Projected/Remaining；不生成 Ready Download |
| S22-E2E-036 | P0 | 无有效 Plan | 分别请求 UI 和 Manifest | 均返回 403，额度不变化 |
| S22-E2E-037 | P0 | Quota 并发竞争 | 剩余额度只够一个请求，同时发起两个 | 仅一个成功；另一个失败；Used 不超限 |
| S22-E2E-038 | P1 | Admin Bypass | 普通用户已满额度后，Admin 下载同一数据 | Admin 成功且不改变普通用户 Usage |
| S22-E2E-039 | P1 | 准备失败不扣额度 | 无可下载 Asset 或强制 Prepare Failure | Download Failed，Authorized Usage 不增加 |
| S22-E2E-040 | P0 | Hex 实际文件估算 | 选择 3 视频、4+ 视频、Metadata 缺失 Episode | 估算等于 MCAP + 实际视频；只在缺失时 Fallback；推荐方式正确 |
| S22-E2E-041 | P1 | 跨方式共享 Usage | 先用 API Package 消耗额度，再请求 UI/Manifest | Projected Usage 包含 Package 使用量，正确限制 |

## 8. API 和数据一致性检查

E2E 执行时需要同时验证：

1. 一个 QA Episode Reward 只产生一个 `point_transactions`，并正确关联 QA Episode Activity。
2. 刷新时 `data_qa_leaderboard.total_points` 等于用户 `data_qa_episode_review` Transaction 之和。
3. Duplicate Approval 在同一事务更新 Review、Source Episode、Processing Error 和 Source Upload。
4. Duplicate Rejection 只清除引用同一 Review ID 的 `duplicate_files` Error。
5. 每个成功授权的 Download 只写一次 `quota_authorized_episode_count`。
6. Monthly Usage 等于已授权 API Package Episode 加已授权 `data_downloads` Episode 数。
7. 并发请求不能超过会员 Plan Limit。
8. 相同筛选条件下 Dataset Stats JSON 和 CSV 的 Episode ID 集合一致。

## 9. 非功能和兼容性测试

- 浏览器：当前支持版本的 Chrome、Safari、Firefox。
- 移动端：iOS Safari、Android Chrome，覆盖 Autoplay 被禁止场景。
- Viewport：375×667、768×1024、1366×768、1920×1080。
- 并发：Duplicate Decision、Quota Authorization、Upload Resume、Reward Callback。
- 性能：大 Dataset Stats、100 行榜单、大量 Duplicate Match、多 Additional Video Episode。
- 容错：GCS Metadata 缺失、CDN 不可用、Signed URL 过期和部分 API 失败。
- 安全：Role、Admin JWT 过期、Internal Token、Episode Preview/Download IDOR 和 CSV Injection。

## 10. 建议执行顺序

1. P0 API 鉴权和 Contract 检查。
2. P0 Reward、Duplicate 和 Quota 数据一致性。
3. P0 QA、Duplicate、Upload、Download 和 Robotic Data Happy Path。
4. P0 并发和边界测试。
5. P1 Filter、Pagination、Fallback、响应式、浏览器和性能测试。
6. 发版后执行 Production Smoke 子集。

## 11. Production Smoke 建议

- Admin 打开 Dataset Stats，并导出一个小范围筛选 CSV。
- Admin 打开一个 Pending Duplicate Group，确认两个视频可播放；除非使用专用 Smoke 数据，否则不提交决定。
- Validator 进入 Data → Verify Quality → My Progress，确认 Stats、Leaderboard、History 加载。
- 授权用户打开一个 Robotic Data Episode 并播放 Camera Preview。
- Active Member 创建一个 Episode 的 UI Download，并检查 Quota Response。
- 全程监控 4xx/5xx、Cloud Run Error、DB Transaction Failure、Signed URL Failure 和异常延迟。

## 12. 需要 Product/Dev 确认的问题

1. 同一个 Episode 在同一个月重复下载，是否应该重复消耗 Quota？
2. QA 缓存排行榜多久刷新一次，可接受的数据延迟 SLA 是多少？
3. 一个 Episode 存在多个 Duplicate Review 且 Admin 做出相反决定时，哪个决定优先？
4. 当 Scenario 重名时，Dataset Stats 是否应使用 Task ID 而不是 Scenario 文本筛选？
5. Production 数据规模下 Dataset Stats 和 Robotic Data Detail 的性能 SLA 是多少？

在这些问题确认前，测试应记录当前实现行为，并将其与最终产品要求不一致的地方标记出来。
