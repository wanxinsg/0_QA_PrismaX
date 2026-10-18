# Uploading 逻辑（前后端联动梳理，MCAP + MP4）

本文基于前端 `Prismax/app-prismax-rp` 与后端 `Prismax/app-prismax-rp-backend` 代码，梳理“数据上传（uploading）”的端到端链路，供 QA/联调定位使用。

---

## 1. 总览：端到端时序

### 1.1 一句话

**前端先向 Data Pipeline 创建 Upload Session 拿到每个文件的 Signed PUT URL → 浏览器并发 PUT 直传到 GCS Raw Bucket → 再上传每个 Episode 的 `_MANIFEST.json` → 触发后端 worker 校验 MCAP、加水印转存视频到 Derived Bucket，并在 DB 推进 upload/episode 状态。**

### 1.2 关键参与方

- **前端 Web**：`Prismax/app-prismax-rp/src/components/Data/Upload.js`
- **Data Pipeline API（Flask）**：`app_prismax_data_pipeline/app.py`
  - 提供任务/机器列表、创建 upload session、查询 upload history、QA Review API 等
- **Data Worker（Flask，事件触发）**：`app_prismax_data_worker/worker.py`
  - 监听 Raw Bucket 中 `_MANIFEST.json` 对象创建事件，驱动校验/派生数据生成
- **存储**：Google Cloud Storage
  - Raw：默认 `prismax-data-raw-prod`（ENV: `DATA_RAW_BUCKET`）
  - Derived：默认 `prismax-data-derived-prod`（ENV: `DATA_DERIVED_BUCKET`）
- **数据库**：Cloud SQL Postgres（表：`data_uploads`, `data_episodes`, `data_qa_sessions`）

---

## 2. 前端逻辑（Upload 页面）

### 2.1 入口与权限

- 入口页面：`/data/upload`（见 `DataHub.js`）
- 上传按钮在任务卡片上，点击触发 `startUploadFlow(task_id)`
- **权限硬限制**：前端仅允许 `userRole === operator` 时启用上传（否则按钮禁用并提示）

### 2.2 文件选择方式

前端支持两种方式（最终都走同一套 normalize/校验/上传）：

- **目录选择**：`<input type="file" webkitdirectory directory multiple />`
- **拖拽文件**：`onDrop` 读取 `event.dataTransfer.files`

### 2.3 路径归一化与去重

前端对每个 `File` 计算 `relative_path`：

- 优先：`file.webkitRelativePath`
- 否则：`file.name`
- 归一化规则（`normalizeRelativePath`）：
  - `\` → `/`
  - 去掉空段
  - **如果路径包含多级目录，会去掉第一级目录**（`parts.slice(1).join('/')`）
    - 目的：用户选择目录时，浏览器会带上“顶层目录名”，前端统一剥掉，避免上传到 `raw/{upload_id}/{topDir}/...`
- 忽略：`.DS_Store`（根或子目录）
- 去重：同 `relative_path` 只保留第一份

### 2.4 文件结构与格式校验（MCAP+MP4）

以当前实现的 `mcap+mp4` 规则为例（`FileFormatCheck/mcapMp4.js`）：

- Root 下只允许 `.mcap`：
  - `{episode_key}.mcap`
- Episode 目录下只允许 `.mp4` 且**必须正好 3 个**：
  - `{episode_key}/xxx.mp4`（要求目录层级只能 1 层：`folder/file`，禁止嵌套）
- 禁止：episode 文件夹名以 `.mcap` 结尾

前端会从文件集合推导：

- `episodeKeys`：用于后续生成 `_MANIFEST.json`（每个 episode 一个）
- `errors`：存在则阻止上传

### 2.5 创建 Upload Session（拿 Signed PUT URLs）

前端点击 `Start Upload` 后：

- 取 token：`gatewayToken` 或 `localStorage.gatewayToken`
- POST：`{PRISMAX_DATA_PIPELINE_URL}/data/upload-sessions`
- 请求体（JSON）：

```json
{
  "token": "<gatewayToken>",
  "task_id": 123,
  "machine_id": "machine_xxx",
  "files": [
    {"relative_path": "A.mcap", "size_bytes": 123, "content_type": "application/octet-stream"},
    {"relative_path": "A/cam1.mp4", "size_bytes": 456, "content_type": "video/mp4"},
    {"relative_path": "A/cam2.mp4", "size_bytes": 456, "content_type": "video/mp4"},
    {"relative_path": "A/cam3.mp4", "size_bytes": 456, "content_type": "video/mp4"},

    // 重要：前端会额外“占位”每个 episode 的 manifest
    {"relative_path": "A/_MANIFEST.json", "size_bytes": null, "content_type": "application/json"}
  ]
}
```

### 2.6 并发直传 Raw Bucket（浏览器 PUT）

后端返回 `signed_urls[]` 后，前端做：

- 将 `signed_urls` 构建为 `Map(relative_path -> signed_url)`
- 用固定并发数上传：`UPLOAD_CONCURRENCY = 5`
- 对每个文件执行：
  - `fetch(signed_url, { method: 'PUT', body: file, headers: { 'Content-Type': content_type } })`
  - 任意失败会 throw，整体标记上传失败
- 上传进度：`uploadedCount/files.length`（仅统计“原始 files”，manifest 另算）

### 2.7 上传 `_MANIFEST.json`（触发后端处理）

原始文件上传完成后，前端对每个 `episodeKey` 生成 manifest JSON 并 PUT：

- 路径：`{episodeKey}/_MANIFEST.json`
- 内容来自 `buildManifestPayload`，核心字段：

```json
{
  "manifest_version": 1,
  "upload_id": 10001,
  "episode_key": "A",
  "machine_id": "machine_xxx",
  "task_id": 123,
  "created_at_utc": "2026-03-11T00:00:00.000Z",
  "files": [
    {"relative_path": "A.mcap", "size_bytes": 123, "content_type": "..."},
    {"relative_path": "A/cam1.mp4", "size_bytes": 456, "content_type": "..."}
  ]
}
```

**注意**：前端 manifest 中的 `files[]` 会过滤，仅包含与该 episodeKey 相关的文件（`A.mcap` + `A/...`）。

---

## 3. 后端逻辑（Data Pipeline API）

### 3.1 服务地址（前端配置）

前端 `configs/config.js`：

- 本地：`PRISMAX_DATA_PIPELINE_URL = http://127.0.0.1:8082`
- Beta / Prod：使用 Cloud Run / `https://data.prismaxserver.com`

### 3.2 认证与角色

`/data/upload-sessions` 的认证方式：

- token 从 payload `token` 或 `Authorization: Bearer ...` 或 query 参数读取（实现 `_extract_token`）
- DB 校验：`users.hash_code = token`
- **要求 role=operator**（否则 403）

### 3.3 创建 Upload Session（核心：DB + Signed PUT URLs）

接口：`POST /data/upload-sessions`（见 `app_prismax_data_pipeline/app.py`）

主要逻辑：

- 解析/校验 `files[]`
  - 最大数量：`MAX_FILES_PER_UPLOAD`（默认 2000）
  - 规范化 `relative_path`：
    - 禁止空、`..`、以 `/` 结尾等
- 推导 `episode_keys`
  - root 的 `{episode}.mcap` 以及 `{episode}/...mp4` 都会计入
- **强制每个 episode 必须有 `_MANIFEST.json`**
  - 后端会比对 `expected_episode_keys` vs `manifest_keys`（缺失/多余都会 400）
- 写入 DB：
  - `data_uploads`：插入 status=`UPLOADING`，并记录 `expected_episode_keys`
  - `data_episodes`：为每个 episode 插入一行 status=`UPLOADING`
    - `raw_mcap_path = raw/{upload_id}/{episode}.mcap`
    - `raw_video_folder_path = raw/{upload_id}/{episode}/`
- 生成 Signed URL（GCS V4）：
  - bucket：`DATA_RAW_BUCKET`
  - 对每个 `relative_path` 生成：
    - `object_name = raw/{upload_id}/{relative_path}`
    - `method = PUT`
    - `content_type` 会参与签名（前端 PUT 时必须一致）

返回：

- `upload_id`
- `bucket`（raw bucket）
- `upload_prefix`（`raw/{upload_id}/`）
- `signed_urls[]`（每个 relative_path 一个）
- `expires_at`（默认 TTL：`DATA_SIGNED_URL_TTL_SECONDS`，缺省 900s）

---

## 4. 后端逻辑（Data Worker：manifest 事件驱动）

### 4.1 触发条件

worker 入口：`POST /`（`app_prismax_data_worker/worker.py`），支持两种事件格式：

- Eventarc CloudEvent：payload 直接含 `{bucket, name}`
- Pub/Sub push：`message.data` base64 解码后 JSON 含 `{bucket, name}`

worker 只处理：

- bucket == `DATA_RAW_BUCKET`
- object_name 以 `/_MANIFEST.json` 结尾
- 路径满足：`raw/{upload_id}/{episode_key}/_MANIFEST.json`

### 4.2 manifest 内容校验（防串单）

worker 下载 manifest 并检查：

- `manifest.upload_id == upload_id`
- `manifest.episode_key == episode_key`
- `files[]` 非空

### 4.3 逐文件存在性与 size 校验

对 manifest 的 `files[]`：

- 检查每个 `raw/{upload_id}/{relative_path}` 在 GCS 是否存在
- 若 manifest 中 `size_bytes` 非空，会对比 blob.size
- 统计：
  - `mcap_size`（第一个 `.mcap` 的 size）
  - `total_video_size`（所有 `.mp4` 的 size 总和）

如果 **missing / size_mismatch**：

- `data_episodes.status = FAILED`（仅该 episode）
- 返回响应里带 missing/size_mismatch（但不会自动重试/补偿）

### 4.4 推进状态：UPLOADED / DERIVING / DERIVED_READY

当该 episode 的文件齐全后：

- `data_episodes.status = UPLOADED`
- `data_episodes.mcap_size_bytes / video_size_bytes` 写入
- 调用 `_update_upload_status` 尝试推进 `data_uploads.status`

`_update_upload_status`（简化规则）：

- 只要有任意 episode = `DERIVED_VALIDATION_FAILED` → upload 也标记该失败
- 所有 episode 都是 `DERIVED_READY` → upload=`DERIVED_READY`
- 所有 episode 都在 `UPLOADED/DERIVING/DERIVED_READY` → upload=`UPLOADED` 且 `uploaded_at` 补写

### 4.5 MCAP 校验（失败会写回 upload 级别原因）

worker 会下载该 episode 的 `.mcap` 到本地临时目录并运行校验：

- 校验实现：`scale_validate_mcap_v01.py`
- 产出：`validation_results`
  - `output_mcap_passed: bool`
  - `failed_checks: [...]`
  - `mandatory_checks` 明细等

若校验抛异常或 `output_mcap_passed=false`：

- `data_episodes.status = DERIVED_VALIDATION_FAILED`（该 episode）
- `data_uploads.status = DERIVED_VALIDATION_FAILED`
- `data_uploads.mcap_validation_result` 写入结构化失败原因（含 failed_episode_key/id、failed_checks、error 等）

该字段来自迁移：`20260310_data_upload_mcap_validation_v1.sql`

### 4.6 视频加水印并写入 Derived

校验通过后：

- `data_episodes.status = DERIVING`
- 对该 episode 的每个 `.mp4`：
  - 下载 raw mp4
  - ffmpeg `drawtext` 加水印（ENV：`WATERMARK_TEXT`，默认 `PrismaX`）
  - 上传到 Derived：
    - `derived/{upload_id}/{episode_key}/{output_rel}`
- 结束后：
  - `data_episodes.status = DERIVED_READY`
  - `derived_bucket / derived_video_folder_path` 更新
  - 再次 `_update_upload_status` 推进 `data_uploads.status`

---

## 5. Upload History（用户侧查看上传结果）

前端页面：`UploadHistory.js`

- GET：`/data/uploading-history`
- 认证：`Authorization: Bearer <token>`
- 返回字段（DB：`data_uploads`）：
  - `upload_id, task_id, machine_id, status, mcap_validation_result, created_at, uploaded_at`

前端会把 `mcap_validation_result` 解析为“Reason”：

- 优先：`failed_episode_key / failed_episode_id`
- 展示：`failed_checks[]` 或 `error`

---

## 6. QA Review 与 uploading 状态的关系（从 DERIVED_READY 开始）

QA 入口与授权：

- 前端只对 `qa / senior qa / expert qa` 展示 Review（`DataHub.js`）
- 后端 `_require_qa_user` 校验 token 并将 role 归一化后限定在 `QA_ALLOWED_ROLES`

QA Queue 获取：

- GET：`/data/qa/uploads`
- 后端按 role 对 status 进行优先级队列：
  - `qa`：`DERIVED_READY`（round=1）
  - `senior qa`：优先 `REVIEW_FIRST_ROUND_FAILED`（round=2），其次 `DERIVED_READY`
  - `expert qa`：优先 `REVIEW_SECOND_ROUND_FAILED`（round=3）…

QA 拉取 episode（只看 `DERIVED_READY` 的 episodes + derived mp4 signed GET URL）：

- GET：`/data/qa/uploads/{upload_id}/episodes?offset=&limit=`
- 返回 `derived_videos[]`，每个元素含 `signed_url`

QA 提交 upload-level review：

- POST：`/data/qa/uploads/{upload_id}/review`
- 会写入 `data_qa_sessions(upload_id, qa_round, qa_score, review_result, ...)`
- 根据 round 收集人数与是否分歧，推进 `data_uploads.status` 到：
  - `REVIEW_FIRST_ROUND_SUCCEEDED / FAILED`
  - `REVIEW_SECOND_ROUND_SUCCEEDED / FAILED`
  - `REVIEW_THIRD_ROUND_SUCCEEDED`

迁移参考：`20260305_data_qa_sessions_upload_level_v1.sql`

---

## 7. QA 视角：关键状态机（建议关注）

### 7.1 episode 级（`data_episodes.status`）

- `UPLOADING`：创建 upload session 后即插入
- `FAILED`：manifest 校验时发现缺文件/size mismatch（文件没齐/不一致）
- `UPLOADED`：manifest 校验通过并写入 size_bytes
- `DERIVING`：开始派生处理（MCAP 校验通过后）
- `DERIVED_READY`：派生视频已写入 derived bucket，可进入 QA
- `DERIVED_VALIDATION_FAILED`：MCAP 校验失败（upload 会同时失败）

### 7.2 upload 级（`data_uploads.status`）

- `UPLOADING`：创建 upload session 后立即写入
- `UPLOADED`：当所有 episode 至少都到 `UPLOADED/DERIVING/DERIVED_READY` 会推进，且写 `uploaded_at`
- `DERIVED_READY`：所有 episode 都 `DERIVED_READY`
- `DERIVED_VALIDATION_FAILED`：任意 episode 校验失败（并在 `mcap_validation_result` 给原因）
- QA review 推进：`REVIEW_*`

---

## 8. 常见失败场景与定位抓手

### 8.1 创建 upload session 失败（前端 POST 400/401/403）

- **token 缺失/失效**：前端会提示 “Missing gateway token / invalid token”
- **非 operator**：后端强制 403（前端也会禁用）
- **manifest 不匹配**（最常见）：
  - 后端要求每个 episode 都有 `_MANIFEST.json` 的 signed url 占位
  - 如果前端/调用方没把 `{episode}/_MANIFEST.json` 加到 `files[]` 会直接 400

### 8.2 PUT 上传失败（signed url 403/400）

- **Content-Type 不一致**：
  - 后端签名时把 `content_type` 加入签名，前端 PUT 必须用同一个值
  - 某些浏览器对未知类型可能 `file.type==""`，前端会回退 `application/octet-stream`
- **URL 过期**：默认 900s，超时需重新创建 session

### 8.3 worker 处理后 episode=FAILED（missing/size mismatch）

原因：

- 某些文件没传上去（上传过程中失败但前端未感知，或用户中断）
- manifest 中 `size_bytes` 与实际 blob.size 不一致

定位：

- 看 worker 响应（若有日志/监控）
- DB 中 `data_episodes.status=FAILED`，且 upload 可能仍停留在 `UPLOADING/UPLOADED`（视其它 episodes 状态）

### 8.4 MCAP 校验失败（upload=DERIVED_VALIDATION_FAILED）

定位入口：

- 前端 Upload History 的 Reason 列（解析 `mcap_validation_result`）
- `mcap_validation_result.failed_checks[]` / `.error`

校验项来源：`scale_validate_mcap_v01.py`（mandatory 6 项）

### 8.5 QA 侧看不到 upload

只有当 upload/episodes 到 `DERIVED_READY` 后，才会进入 QA queue（至少对 base QA）。

---

## 9. 代码索引（快速跳转）

- 前端上传：`app-prismax-rp/src/components/Data/Upload.js`
- 前端 upload history：`app-prismax-rp/src/components/Data/UploadHistory.js`
- 前端格式校验：`app-prismax-rp/src/components/Data/FileFormatCheck/mcapMp4.js`
- Pipeline API：`app-prismax-rp-backend/app_prismax_data_pipeline/app.py`
  - `POST /data/upload-sessions`
  - `GET /data/uploading-history`
- Worker：`app-prismax-rp-backend/app_prismax_data_worker/worker.py`
- MCAP 校验：`app-prismax-rp-backend/app_prismax_data_worker/scale_validate_mcap_v01.py`
- SQL 迁移：
  - `20260310_data_upload_mcap_validation_v1.sql`
  - `20260305_data_qa_sessions_upload_level_v1.sql`

---

## 10. 测试策略（QA / 联调）

### 10.1 测试目标与范围

- **目标**：验证上传从 UI → Signed URL 直传 → worker 派生 → DB 状态推进 → History/QA Review 可见的全链路正确性与可观测性。
- **范围**：
  - Upload Data：文件结构校验、创建 session、并发 PUT、manifest 上传
  - Worker：manifest 触发、missing/size mismatch、MCAP validation、视频派生（加水印）
  - Upload History：状态与失败原因（`mcap_validation_result`）展示
  - QA Review：`DERIVED_READY` 进入队列、拉取 episodes、提交 review 影响 status
- **不在范围（本轮不强测）**：任务/机器的业务正确性、钱包/登录体系本身、非 data pipeline 的其它后端服务。

### 10.2 分层测试金字塔（建议）

- **前端单测/组件测**：
  - 文件路径归一化/去重
  - `FileFormatCheck`（episode_key 推导与错误提示）
  - manifest payload 构造（每个 episode 只包含对应文件）
- **API 集成测试（Data Pipeline）**：
  - `/data/upload-sessions` 的鉴权、manifest keys 校验、signed url 返回结构
  - `/data/uploading-history` 返回字段与排序
  - QA API：`/data/qa/uploads`、`/episodes`、`/review`
- **端到端 E2E（强制覆盖）**：
  - 以真实浏览器执行：选择目录 → 上传 → 等待派生 → History/QA Review 验证

### 10.3 测试环境与数据准备

- **环境**：
  - local：`PRISMAX_DATA_PIPELINE_URL=http://127.0.0.1:8082`（前端）
  - beta/prod：使用线上 Cloud Run / `data.prismaxserver.com`
- **账号**：
  - `operator`：用于 Upload
  - `qa / senior qa / expert qa`：用于 Review 阶段验证队列与 round
- **测试数据（建议准备 3 套）**：
  - **Dataset-PASS**：满足 `mcap+mp4` 文件结构且 MCAP 校验通过（至少 1 episode）
  - **Dataset-STRUCT-FAIL**：结构不符合（例如 mp4 数量不等于 3、嵌套目录、root 下出现非 mcap）
  - **Dataset-MCAP-FAIL**：结构符合但 MCAP 校验失败（触发 `DERIVED_VALIDATION_FAILED` 并写入 `mcap_validation_result`）

### 10.4 关键观测点（必须可查）

- **前端**：
  - 上传前校验错误提示是否阻断上传
  - session 创建失败时的 msg（400/401/403）
  - PUT 上传失败是否能明确到具体文件（当前前端会 throw `Upload failed for <relative_path>`）
- **后端 API（逻辑正确性）**：
  - `/data/upload-sessions` 400：缺 manifest / episode keys mismatch / files 过多 / relative_path 非法
  - signed url 的 `content_type` 一致性（签名绑定）
- **DB 状态**（用于最终断言）：
  - `data_uploads.status`：`UPLOADING → UPLOADED → DERIVED_READY` 或 `DERIVED_VALIDATION_FAILED`
  - `data_episodes.status`：`UPLOADING/FAILED/UPLOADED/DERIVING/DERIVED_READY/DERIVED_VALIDATION_FAILED`
  - `data_uploads.mcap_validation_result`：失败时包含 `failed_episode_key/id` + `failed_checks`/`error`
- **存储对象**：
  - raw：`raw/{upload_id}/{episode}.mcap`、`raw/{upload_id}/{episode}/...mp4`、`raw/{upload_id}/{episode}/_MANIFEST.json`
  - derived：`derived/{upload_id}/{episode}/...mp4`（存在且可播放）

### 10.5 风险优先级（建议回归排序）

- P0：operator 鉴权、manifest 触发 worker、MCAP fail 写入 reason、DERIVED_READY 可进入 QA/History
- P1：Content-Type 导致 signed url PUT 失败、URL 过期、并发上传（部分失败）提示
- P2：大文件/大批量（接近 2000 files）稳定性、长时间派生/队列延迟

---

## 11. E2E 测试用例（完整集）

说明：

- **验证口径**：除 UI 提示外，尽量以 “History 状态 + Reason + QA Review 可见性” 作为最终可见断言；如有权限访问 DB/日志，可作为增强断言。
- **用例中出现的变量**：
  - `T`：选择的 `task_id`
  - `M`：选择的 `machine_id`
  - `E`：episode_key（例如 `A`）
  - `U`：upload_id（由后端返回）

### 11.1 Upload Data（正常链路）

#### E2E-UP-001：单 episode 成功上传并派生成功（DERIVED_READY）

- **前置条件**：
  - 账号角色为 `operator`
  - 使用 `Dataset-PASS`（结构合法，MCAP 校验通过）
- **步骤**：
  - 进入 `Upload Data`
  - 任意选择一个任务卡片点击 `Upload`
  - 选择 `Robot Name`（machine）
  - 选择包含该 dataset 的目录（webkitdirectory）
  - 在 `Upload Session` 中点击 `Start Upload`
  - 等待上传完成提示（前端提示 “Upload completed. Worker will process episodes.”）
  - 进入 `Upload History` 并刷新
- **断言**：
  - History 出现新的 `upload_id=U`，task=T，machine=M
  - status 最终到 `DERIVED_READY`（允许异步延迟，需轮询等待）
  - Reason 列为 `-`（或空）且不显示 failed_checks/error
- **增强断言（可选）**：
  - derived bucket 下存在 `derived/{U}/{E}/` 的 mp4，并可在 QA Review 页面成功播放

#### E2E-UP-002：多 episode（≥2）成功上传并派生成功

- **前置条件**：同 E2E-UP-001，但 dataset 包含多个 episode_key
- **步骤**：同 E2E-UP-001
- **断言**：
  - History status 最终 `DERIVED_READY`
  - QA Review 中对应 upload 可拉取到多个 episode（sampled list）

#### E2E-UP-003：并发上传进度条正确（上传数/总数）

- **前置条件**：Dataset-PASS，文件数至少 > 5（覆盖 `UPLOAD_CONCURRENCY=5`）
- **步骤**：开始上传，观察进度条
- **断言**：
  - `uploadedCount` 递增，最终到 `files.length`
  - 上传完成后 UI 不再处于 isUploading 状态

### 11.2 Upload Data（前端结构校验阻断）

#### E2E-UP-010：root 下存在非 `.mcap` 文件（应阻断）

- **前置条件**：operator；准备目录：root 下放 `readme.txt` 或 `foo.csv`
- **步骤**：选择该目录
- **断言**：
  - `Upload Session` 显示 warning：`Only .mcap files are allowed at root: ...`
  - `Start Upload` 按钮不可用（formatErrors 非空）

#### E2E-UP-011：episode 文件夹 mp4 数量不等于 3（应阻断）

- **前置条件**：operator；`E/` 下只有 2 个或 4 个 mp4
- **步骤**：选择目录
- **断言**：
  - 显示 `Episode E must have exactly 3 .mp4 files`
  - 不允许开始上传

#### E2E-UP-012：存在嵌套目录（E/sub/xxx.mp4）（应阻断）

- **断言**：显示 `Nested folders are not allowed`

### 11.3 Upload Session 创建失败（API 400/401/403）

#### E2E-UP-020：非 operator 用户尝试上传（前端禁用 + 后端兜底）

- **前置条件**：非 operator 登录
- **步骤**：进入 Upload Data
- **断言**：
  - 任务卡片 `Upload` 按钮禁用
  - 页面 banner 提示 operator 才可上传

#### E2E-UP-021：token 缺失/过期（session 创建失败）

- **前置条件**：operator，但清空 `localStorage.gatewayToken` 或模拟 token 失效
- **步骤**：开始上传
- **断言**：
  - 前端提示 `Missing gateway token` 或 `invalid token`
  - 不会进入 PUT 上传阶段

#### E2E-UP-022：manifest keys 缺失导致 session 400（回归保护）

说明：当前前端会自动为每个 episode 添加 `{episode}/_MANIFEST.json` 占位；此用例用于回归后端约束。

- **方法建议**：
  - 通过 API 直接调用 `/data/upload-sessions`，故意不传 manifest paths（或用旧前端分支）
- **断言**：
  - 400 且 msg 为 `manifest required for each episode`，并返回 `missing_manifests`

### 11.4 PUT 上传失败类（signed url / content-type / 过期）

#### E2E-UP-030：Signed URL 过期后 PUT 失败（需重新创建 session）

- **前置条件**：operator；拿到 signed url 后等待超过 TTL（默认 900s）
- **步骤**：尝试继续上传（或在上传中等待到过期）
- **断言**：
  - PUT 返回非 2xx，前端提示 `Upload failed for <relative_path>`
  - 重新发起上传（重新创建 session）后可恢复

#### E2E-UP-031：Content-Type 不一致导致 PUT 失败（兼容性）

- **前置条件**：构造一种浏览器/文件类型让 `file.type` 与后端签名的 content_type 不一致（或用代理篡改 header）
- **断言**：PUT 失败；回归点为“前端签名与 PUT 使用同一 content_type”

### 11.5 worker：manifest 校验失败（missing/size mismatch）

#### E2E-UP-040：缺少文件（manifest 指向的文件未上传）

- **前置条件**：operator；上传过程中中断某个 mp4（例如网络断开/强制取消），但仍上传了 manifest
- **步骤**：让 `_MANIFEST.json` 成功上传触发 worker
- **断言**：
  - `data_episodes.status` 变为 `FAILED`（若可查）
  - upload history 可能不进入 `DERIVED_READY`
  - 若有日志/返回，包含 `missing: [path...]`

#### E2E-UP-041：size mismatch（manifest size_bytes 与实际不一致）

- **方法建议**：
  - 通过 API 构造 manifest 中的 size_bytes 与真实 blob.size 不一致（或上传后替换对象）
- **断言**：
  - episode=FAILED 且 size_mismatch 列表包含 expected/actual

### 11.6 worker：MCAP 校验失败（DERIVED_VALIDATION_FAILED）

#### E2E-UP-050：MCAP 校验失败写入 `mcap_validation_result` 并在 History 展示

- **前置条件**：operator；使用 `Dataset-MCAP-FAIL`
- **步骤**：正常上传直至完成
- **断言**：
  - History 中该 upload status 为 `DERIVED_VALIDATION_FAILED`
  - Reason 列展示：
    - `Episode <failed_episode_key>`（或 episode_id）
    - `failed_checks` 列表（或 `error`）

### 11.7 worker：派生成功（加水印 & derived 可用）

#### E2E-UP-060：派生视频可在 QA Review 播放（signed GET URL）

- **前置条件**：完成一个 `DERIVED_READY` 的 upload；准备 QA 账号
- **步骤**：
  - 用 QA 账号进入 `Verify Quality`
  - 选择对应 task，进入 review viewer
  - 切换到 `Upload #U`，播放视频
- **断言**：
  - 页面能拉到 episodes（`/data/qa/uploads/{U}/episodes` 返回非空）
  - 视频 `<source src=...signed_url>` 可播放（至少首帧加载成功）

### 11.8 Upload History 刷新与展示

#### E2E-UP-070：History 列字段展示正确

- **前置条件**：至少存在 1 条 upload（成功或失败）
- **步骤**：进入 `Upload History`，点击 Refresh
- **断言**：
  - 表格列：ID/Task/Machine/Status/Reason/Created/Uploaded 都有值或 `-`
  - 失败时 Reason 能反映 `mcap_validation_result`

### 11.9 QA Review：round/人数/分歧推进状态

#### E2E-QA-001：base QA 提交 round=1（需要 3 人）

- **前置条件**：
  - upload status 为 `DERIVED_READY`
  - 3 个不同的 `qa` 账号
- **步骤**：
  - 三个 QA 分别对同一 upload 提交 review（分数差 < 30 且 gate 一致）
- **断言**：
  - 第 3 个提交后，该 upload status 更新为 `REVIEW_FIRST_ROUND_SUCCEEDED`

#### E2E-QA-002：round=1 触发分歧（进入 REVIEW_FIRST_ROUND_FAILED）

- **前置条件**：同 E2E-QA-001
- **步骤**：
  - 三个 QA 中至少一个在 gate 上与其它人不一致，或分数差距 ≥ 30
- **断言**：
  - upload status 进入 `REVIEW_FIRST_ROUND_FAILED`
  - `senior qa` 队列中该条优先可见（`/data/qa/uploads` priority）

#### E2E-QA-003：senior QA round=2（需要 2 人）推进到 second round succeeded/failed

- **前置条件**：upload 已在 `REVIEW_FIRST_ROUND_FAILED`；2 个 `senior qa`
- **断言**：
  - 满足人数后推进到 `REVIEW_SECOND_ROUND_SUCCEEDED` 或 `REVIEW_SECOND_ROUND_FAILED`

#### E2E-QA-004：expert QA round=3（需要 1 人）最终成功

- **前置条件**：upload 已在 `REVIEW_SECOND_ROUND_FAILED`；1 个 `expert qa`
- **断言**：
  - 提交一次后推进到 `REVIEW_THIRD_ROUND_SUCCEEDED`

