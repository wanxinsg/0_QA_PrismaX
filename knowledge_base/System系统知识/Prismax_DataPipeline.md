# Prismax Data Pipeline — 完整 Data Flow 分析

基于 **app-prismax-rp**（前端）与 **app-prismax-rp-backend**（后端）中 datapipeline 相关代码的完整分析。

---

## 一、架构总览

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                            app-prismax-rp (Frontend)                              │
│  /data → DataHub → [ Upload | Upload History | Verify Quality | Preview ]         │
└───────────────────────────────┬───────────────────────────────────────────────────┘
                                │ PRISMAX_DATA_PIPELINE_URL
                                ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│              app-prismax-data-pipeline (Flask API, Cloud Run)                      │
│  • JWT/token 鉴权 (operator / qa)   • Cloud SQL (PostgreSQL)   • GCS Signed URLs   │
└───────┬─────────────────────────────────────────────────────────┬────────────────┘
        │                                                           │
        │ 触发（上传 _MANIFEST.json 后）                              │ 读/写
        ▼                                                           ▼
┌───────────────────────────────┐                    ┌──────────────────────────────┐
│ app_prismax_data_worker       │                    │ Cloud SQL                    │
│ (Eventarc / Pub-Sub 触发)      │◄───────────────────│ data_tasks, data_machines   │
│ • 校验 manifest + 文件         │                    │ data_uploads, data_episodes  │
│ • 水印 → derived bucket        │                    │ data_qa_sessions, users      │
└───────────────┬───────────────┘                    └──────────────────────────────┘
                │
                │ 写
                ▼
┌───────────────────────────────┐
│ GCS                            │
│ • DATA_RAW_BUCKET (raw/)       │  ← 前端 PUT 上传
│ • DATA_DERIVED_BUCKET (derived/)│ ← Worker 写水印视频
└───────────────────────────────┘
```

- **前端**：React，路由 `/data/*`，所有 Data 请求发往 `PRISMAX_DATA_PIPELINE_URL`。
- **Data Pipeline 服务**：Flask，Cloud SQL + Secret Manager + GCS 签名 URL，角色校验（operator / qa）。
- **Data Worker**：由 GCS 对象事件（`_MANIFEST.json` 上传）触发，校验、水印、写 derived，并更新 DB 状态。

---

## 二、配置与入口

### 2.1 前端 Base URL

| 环境 | PRISMAX_DATA_PIPELINE_URL |
|------|---------------------------|
| 本地 | `http://127.0.0.1:8082` |
| Beta | `https://app-prismax-data-pipeline-beta-1053158761087.us-west1.run.app` |
| 生产 | `https://data.prismaxserver.com` |

- 定义：`app-prismax-rp/src/configs/config.js`
- 使用方：`DataHub.js`、`Upload.js`、`UploadHistory.js`、`DataQAReview/DataQAReview.js`

### 2.2 前端路由（DataHub）

| 路径 | 组件 | 说明 |
|------|------|------|
| `/data` | Navigate → `upload` | 默认进上传 |
| `/data/upload` | DataUpload | 选 task/machine，选文件，创建 session，直传 GCS |
| `/data/history` | UploadHistory | 当前用户上传历史 |
| `/data/review` | DataReviewTaskHub | QA：按 task 聚合的 upload 卡片，进具体 task |
| `/data/review/:taskId` | DataQAReview | QA：选 upload → 拉 episodes → 看视频、打分、提交 review |
| `/data/preview` | DataPreview | 占位 “Coming soon” |

### 2.3 后端 API 与角色

| 接口 | 方法 | 角色 | 说明 |
|------|------|------|------|
| `/data/tasks` | GET | 无 | 列表 data_tasks |
| `/data/machines` | GET | 无 | 列表 data_machines |
| `/data/uploading-history` | GET | token | 当前用户最近 100 条 data_uploads |
| `/data/upload-sessions` | POST | operator | 创建上传会话，写 data_uploads + data_episodes，返回 GCS signed PUT URLs |
| `/data/qa/uploads` | GET | qa | 可 QA 的 upload 列表（含 episode 统计） |
| `/data/qa/uploads/<id>/episodes` | GET | qa | 某 upload 的 episodes（含 derived 视频 signed URL） |
| `/data/qa/sessions` | POST | qa | 为 episode 创建 QA session（data_qa_sessions） |
| `/data/qa/sessions/<id>/review` | POST | qa | 提交评分/备注，更新 data_qa_sessions |

---

## 三、端到端 Data Flow（按场景）

### 3.1 上传流程（Operator）

1. **DataHub 加载元数据**
   - `GET /data/tasks`、`GET /data/machines`（无鉴权），缓存到 `taskListCache` / `machineListCache`。
   - Upload 页用 `dataTasks`、`dataMachines` 做 scenario 筛选、任务/机器选择。

2. **用户选择 Task、Machine 并选文件**
   - 文件约定：根目录 `{episode_key}.mcap`，每个 episode 目录 `{episode_key}/*.mp4`（如 3 个 mp4）。
   - 前端 `validateFilesForFormat` 校验格式；必须能解析出 episode keys，且每个 episode 对应一个 `_MANIFEST.json` 占位。

3. **创建上传会话**
   - `POST /data/upload-sessions`  
     Body: `{ token, task_id, machine_id, files }`  
     `files`: 每项 `{ relative_path, size_bytes?, content_type? }`，外加每个 episode 的 `{episode_key}/_MANIFEST.json` 占位。
   - 后端：
     - 校验 token → users，要求 `user_role = operator`。
     - `_parse_files` 校验数量与路径；`_extract_episode_keys`（.mcap 与 .mp4 目录）、`_extract_manifest_keys`；要求每个 episode 都有 manifest，且 manifest 与 episode 一一对应。
     - 插入 `data_uploads`（status=UPLOADING, expected_episode_keys），再为每个 episode 插入 `data_episodes`（status=UPLOADING, raw_bucket, raw_mcap_path, raw_video_folder_path）。
     - 为每个 `files` 项（含 manifest 占位）生成 GCS signed PUT URL（`raw/{upload_id}/{relative_path}`）。
   - 响应：`upload_id, bucket, upload_prefix, signed_urls, expected_episode_keys, episode_count, expires_at`。

4. **前端直传 GCS**
   - 用 `signed_urls` 的 `relative_path → signed_url` 映射，对每个文件（含 .mcap、.mp4）`PUT` 到对应 signed URL。
   - 然后对每个 episode 生成并上传 `_MANIFEST.json`（`buildManifestPayload`：manifest_version, upload_id, episode_key, machine_id, task_id, files 等）到 `{episode_key}/_MANIFEST.json`。

5. **Worker 被触发（GCS 事件）**
   - 仅处理 `DATA_RAW_BUCKET` 下路径以 `/_MANIFEST.json` 结尾的对象。
   - 解析路径得 `upload_id`, `episode_key`；下载 manifest，校验 `upload_id`/`episode_key`；校验 manifest 中列出的文件是否都存在且大小一致。
   - 若有缺失或大小不一致：对应 `data_episodes` 置为 FAILED，返回 200（带 missing/size_mismatch）。
   - 否则：该 episode 置 UPLOADED（并写 mcap_size_bytes, video_size_bytes），然后置 DERIVING；从 raw 下载每个 .mp4，ffmpeg 水印后上传到 `DATA_DERIVED_BUCKET` 的 `derived/{upload_id}/{episode_key}/...`；最后该 episode 置 DERIVED_READY，写 derived_bucket、derived_video_folder_path，并聚合更新 `data_uploads.status`（全部 DERIVED_READY → upload 置 DERIVED_READY；全部至少 UPLOADED → upload 置 UPLOADED、uploaded_at）。

6. **上传历史**
   - `GET /data/uploading-history`（Header `Authorization: Bearer <token>`）从 `data_uploads` 按 user_id 取最近 100 条，前端 UploadHistory 展示。

**小结**：Operator 选 task/machine → 前端校验文件 → 后端创建 session + 写 DB + 返回 signed URLs → 前端 PUT 文件 + 写 manifest → GCS 事件触发 Worker → Worker 校验、水印、写 derived、更新 data_episodes/data_uploads。

---

### 3.2 QA 审核流程（QA 角色）

1. **进入 Review 列表**
   - 进入 `/data/review` 时，DataHub 若为 QA 则调用 `GET /data/qa/uploads`（Bearer token）。
   - 后端 `_require_user_role("qa")`，查询：`data_uploads` JOIN `data_episodes`，只保留至少有一个 episode 为 DERIVED_READY 的 upload，带 episode_count、derived_ready_count 等。
   - DataReviewTaskHub 按 task_id 聚合 upload，展示卡片（task 标题、upload 数），点击 “Review” 进入 `/data/review/:taskId`。

2. **选择 Task 下的 Upload**
   - DataQAReview 用 `taskId` 过滤 `qaUploads`，选一个 upload 后请求该 upload 的 episodes。

3. **拉取 Episodes 与衍生视频**
   - `GET /data/qa/uploads/<upload_id>/episodes?offset=&limit=`（Bearer token）。
   - 后端：只返回 status=DERIVED_READY 的 episodes；LEFT JOIN data_qa_sessions 得到 review_count、avg_score；对 derived 目录下列出 .mp4，生成 GCS signed GET URL，放在每条 episode 的 `derived_videos` 里。
   - 前端先取 limit=5，再后台按 5 条一批追加，用于列表与播放。

4. **创建 QA Session**
   - 用户对某 episode 打分时，若该 episode 还没有 session，先 `POST /data/qa/sessions` Body: `{ episode_id }`（可选 qa_score, note）。
   - 后端校验 episode 存在，插入 `data_qa_sessions(episode_id, qa_score, user_id, note)`，返回 `qa_session_id`。
   - 前端把 sessionId 记在 reviewState 里，避免重复创建。

5. **提交评分**
   - `POST /data/qa/sessions/<qa_session_id>/review` Body: `{ qa_score, note }`，qa_score 必填 0–100。
   - 后端只更新当前用户自己的 session：`UPDATE data_qa_sessions SET qa_score, note WHERE qa_session_id AND user_id`。
   - 前端可再调 `loadUploadEpisodes` 刷新列表（含 review_count/avg_score）。

**小结**：QA 看 upload 列表（按 task 聚合）→ 选 task → 选 upload → 拉 episodes（含 derived 视频 URL）→ 对 episode 创建 session（若需要）→ 提交 review 更新 data_qa_sessions。

---

## 四、核心数据表与字段（推断）

- **data_tasks**：任务元数据（task_id, scenario/environment/scene, data_format, description 等），供上传选任务、QA 展示 task 标题。
- **data_machines**：机器列表（machine_id 等），供上传选机器。
- **data_uploads**：user_id, machine_id, task_id, status（UPLOADING → UPLOADED → DERIVED_READY）, expected_episode_keys, created_at, uploaded_at。
- **data_episodes**：upload_id, machine_id, task_id, status（UPLOADING → UPLOADED → DERIVING → DERIVED_READY / FAILED）, raw_bucket, raw_mcap_path, raw_video_folder_path, derived_bucket, derived_video_folder_path, mcap_size_bytes, video_size_bytes 等；与 upload 内 episode 一一对应。
- **data_qa_sessions**：episode_id, user_id, qa_score, note, created_at；一个 episode 可有多次 session（不同用户或同一用户先创建后提交）。
- **users**：userid, user_role（operator/qa）, email, hash_code（token）等；鉴权与角色校验用。

---

## 五、GCS 路径约定

- **Raw**：`raw/{upload_id}/{relative_path}`  
  - 根级：`raw/{upload_id}/{episode_key}.mcap`  
  - 视频：`raw/{upload_id}/{episode_key}/xxx.mp4`  
  - Manifest：`raw/{upload_id}/{episode_key}/_MANIFEST.json`
- **Derived**：`derived/{upload_id}/{episode_key}/xxx.mp4`（水印后），由 Worker 写入。

---

## 六、文件与关键代码位置

| 功能 | 前端 (app-prismax-rp) | 后端 (app-prismax-rp-backend) |
|------|------------------------|--------------------------------|
| 配置/入口 | `src/configs/config.js` | - |
| Data 路由/列表 | `src/components/Data/DataHub.js` | - |
| 上传 UI + session + 直传 | `src/components/Data/Upload.js` | `app_prismax_data_pipeline/app.py` → create_upload_session |
| 上传历史 | `src/components/Data/UploadHistory.js` | app.py → get_user_upload_history |
| QA 任务卡片 | `src/components/Data/DataQAReview/DataReviewTaskHub.js` | app.py → get_qa_uploads |
| QA 单 task 审核 | `src/components/Data/DataQAReview/DataQAReview.js` | app.py → get_qa_upload_episodes, create_qa_session, submit_qa_review |
| 任务/机器 API | DataHub 调用 | app.py → get_data_tasks, get_data_machines |
| Manifest 触发与衍生 | - | `app_prismax_data_worker/worker.py` → handle_manifest_event |

---

## 七、安全与鉴权要点

- **Token**：从 `Authorization: Bearer <token>` 或 body/query 的 `token` 获取；与 `users.hash_code` 匹配。
- **Operator**：仅能调 `POST /data/upload-sessions` 和 `GET /data/uploading-history`（后者按 user_id 过滤）。
- **QA**：仅能调 `/data/qa/*`；`/data/qa/sessions/<id>/review` 仅能更新当前 user_id 的 session。
- **CORS**：生产仅允许配置的 ALLOWED_CORS_ORIGINS（如 app.prismax.ai, gateway.prismax.ai, beta-app.prismax.ai）。

---

以上即为 app-prismax-rp 与 app-prismax-rp-backend 中 datapipeline 的完整 data flow 分析，从配置、路由、API、DB、GCS 到 Worker 触发与 QA 闭环均已覆盖。

---

## 八、测试策略

### 8.1 测试范围与优先级

| 优先级 | 范围 | 说明 |
|--------|------|------|
| **P0** | 上传会话创建、文件直传 GCS、Worker 触发与 episode 状态、QA 列表/episodes/打分 | 核心数据流端到端 |
| **P0** | 鉴权与角色：operator / qa / 无 token / 无效 token | 安全与权限 |
| **P1** | 上传历史、格式校验边界、signed URL 有效性、分页 episodes | 功能与兼容性 |
| **P1** | 前端 Data 路由、Upload/History/Review 页面交互与 UI | 前端回归 |
| **P2** | tasks/machines 返回字段、CORS、环境 URL 切换、静态资源 | 环境与细节 |

---

### 8.2 后端 API 测试

#### 8.2.1 无需鉴权

- **GET /data/tasks**：返回 200，`data` 为数组；表结构变更时 SELECT * 与前端展示兼容。
- **GET /data/machines**：同上。

#### 8.2.2 Token 鉴权（上传历史）

- **GET /data/uploading-history**
  - 无 token / 无效 token：400 或 401，`msg` 明确。
  - 合法 token：200，`data` 为当前用户最近 100 条 data_uploads；字段含 upload_id, task_id, machine_id, status, created_at, uploaded_at。

#### 8.2.3 Operator 角色（上传会话）

- **POST /data/upload-sessions**
  - 无 token / 无效 token：401。
  - 非 operator（如 qa）：403，msg 含 "operator"。
  - 缺 task_id 或 machine_id：400。
  - **files 校验**：空列表、超 MAX_FILES_PER_UPLOAD、relative_path 含 `..`/非法字符、无 episode 可解析：400，msg 明确。
  - **manifest 校验**：缺少某 episode 的 manifest、或 manifest 与 episode 不一一对应：400，可选返回 missing_manifests / extra_manifests。
  - **合法请求**（operator + 合法 task_id/machine_id/files，且每个 episode 有对应 _MANIFEST.json 占位）：200；响应含 upload_id, bucket, upload_prefix, signed_urls（与 files 一一对应）, expected_episode_keys, episode_count, expires_at；DB 中 data_uploads 一条 status=UPLOADING，data_episodes 条数与 expected_episode_keys 一致且 status=UPLOADING。

#### 8.2.4 QA 角色（审核相关）

- **GET /data/qa/uploads**
  - 无 token / 非 qa：401/403。
  - 合法 qa：200，仅含至少有一个 DERIVED_READY episode 的 upload；含 episode_count、derived_ready_count 等。

- **GET /data/qa/uploads/<upload_id>/episodes**
  - 非 qa：403。非法 upload_id 或无 DERIVED_READY：空列表或 404 视实现而定。
  - 合法 qa + 合法 upload_id：200；data 仅 DERIVED_READY 的 episodes；每条含 derived_videos（signed GET URL）；meta 含 total_count, offset, limit, has_more。offset/limit 边界（0、负数、超 100）返回 400 或按约定裁剪。

- **POST /data/qa/sessions**
  - Body：episode_id 必填；qa_score 可选，若传则 0–100。
  - 非 qa：403。episode_id 不存在：404。
  - 合法：200，返回 qa_session_id, created_at；DB 插入 data_qa_sessions。

- **POST /data/qa/sessions/<qa_session_id>/review**
  - Body：qa_score 必填 0–100，note 可选。
  - 缺 qa_score 或越界：400。非 qa 或非本用户 session：403/404。
  - 合法：200；DB 中对应 session 的 qa_score、note 更新。

---

### 8.3 Worker 测试

- **触发条件**：仅当 bucket=DATA_RAW_BUCKET 且 object 以 `/_MANIFEST.json` 结尾时处理；否则 200 ignored。
- **路径解析**：`raw/{upload_id}/{episode_key}/_MANIFEST.json` 解析出 upload_id、episode_key；非法路径或 upload_id 非数字：400 或 ignored。
- **Manifest 校验**：manifest 内 upload_id/episode_key 与路径一致；files 非空；否则 400。
- **文件校验**：manifest 中列出的文件在 GCS 均存在且 size_bytes 一致；有缺失或大小不一致：对应 data_episodes 置 FAILED，返回 200 并带 missing/size_mismatch（便于排查）。
- **成功路径**：episode 置 UPLOADED → DERIVING；下载 raw 下 .mp4，ffmpeg 水印后上传到 derived bucket；episode 置 DERIVED_READY，写 derived_bucket、derived_video_folder_path；聚合更新 data_uploads.status（全 DERIVED_READY → UPLOADED → DERIVED_READY，并设 uploaded_at）。
- **幂等**：同一 manifest 再次触发，若 episode 已 DERIVED_READY，可返回 200 "already derived" 且不重复处理。

---

### 8.4 签名 URL 与 GCS

- **PUT URL（上传）**：create_upload_session 返回的 signed_urls 在 TTL 内可成功 PUT 对应 relative_path 的文件；过期或错误签名应 403。
- **GET URL（QA 看视频）**：get_qa_upload_episodes 返回的 derived_videos[].signed_url 在 TTL 内可 GET 到视频内容。
- **环境**：Cloud Run/ADC 下使用统一 google.auth 签名，无凭证时错误可观测（日志/返回）。

---

### 8.5 前端测试

#### 8.5.1 配置与路由

- 本地/Beta/生产对应 PRISMAX_DATA_PIPELINE_URL 正确；切换 host 后 Data 请求发往对应域名。
- `/data` 重定向到 `/data/upload`；侧栏与路由：Upload Data、Upload History、Verify Quality、Preview 高亮与跳转正确；非 QA 点击 Verify Quality 有受限提示。

#### 8.5.2 上传流程（Operator）

- 进入 Upload：tasks、machines 加载成功；scenario 筛选、任务/机器选择正常。
- **格式校验**：符合约定（根目录 .mcap + 每 episode 目录下约定数量 .mp4）通过；非法（多/少 .mp4、错误目录结构、文件夹名 .mcap 结尾等）展示明确 errors 且上传按钮不可用或提交被阻。
- 创建会话 → 直传文件（含 .mcap、.mp4）→ 上传各 episode 的 _MANIFEST.json；进度与完成提示正常；失败时提示明确。
- 上传历史：登录 operator 后列表来自 /data/uploading-history，条数、字段与后端一致；无 token 时提示或空列表。

#### 8.5.3 QA 审核流程（QA）

- QA 进入 /data/review：列表与 GET /data/qa/uploads 一致；按 task 聚合卡片，点击进入 /data/review/:taskId。
- 选择 upload → 拉取 episodes；列表与分页（offset/limit）正常；每条 episode 的 derived_videos 可播放（signed URL 有效）。
- 对某 episode 打分：无 session 时先创建 session 再提交 review；有 session 直接提交；提交后 score/note 更新，可选刷新列表看到 review_count/avg_score。
- 非 QA 无法访问 QA 接口或进入后提示无权限。

#### 8.5.4 UI 回归

- DataHub：侧栏、场景列表、占位文案无错位。
- Upload：文件选择、错误展示、进度、完成与历史入口；Preview、Register Robots 等占位/禁用状态正常。
- DataQAReview：upload 选择、episode 列表、视频区域、打分与备注、提交与返回；新图标无 404。
- 响应式：主要 breakpoint 下布局无严重错位。

---

### 8.6 数据一致性

- 创建 upload-session 后：data_uploads 的 expected_episode_keys 与 data_episodes 条数及 raw_video_folder_path 一致。
- Worker 处理完成后：data_episodes.status 为 DERIVED_READY，derived_video_folder_path 与 GCS derived 路径一致；data_uploads.status 随全部 episode 状态聚合正确。
- QA 提交 review 后：data_qa_sessions 有对应记录；再次拉取 episodes 时 review_count、avg_score 正确。

---

### 8.7 冒烟与回归建议

- **冒烟（P0）**  
  1. GET /data/tasks、/data/machines → 200。  
  2. Operator：选 task/machine + 合法文件 → 格式通过 → POST upload-sessions → 直传 1 个 episode（mcap + mp4 + _MANIFEST.json）→ Worker 处理完成 → GET uploading-history 有新记录。  
  3. QA：GET /data/qa/uploads 有数据 → 选 upload → GET episodes 有 derived_videos → 创建 session → 提交 review → 刷新后 review_count/avg_score 更新。

- **回归**  
  - 覆盖 401/403/400 边界（无 token、错误角色、缺参、files/manifest 非法）。  
  - 前端格式校验边界、上传失败与历史空态、QA 无权限提示。  
  - Beta 环境 PRISMAX_DATA_PIPELINE_URL 与 CORS、Data 三页 UI 与图标。

---

## 九、E2E 测试用例

以下用例为端到端场景，覆盖从前端操作到后端 API、Worker、DB 与 GCS 的完整链路。格式：**用例编号 | 标题 | 优先级 | 前置条件 | 步骤 | 预期结果**。

---

### 9.1 上传流程（Operator）

| 编号 | 标题 | 优先级 | 前置条件 | 步骤 | 预期结果 |
|------|------|--------|----------|------|----------|
| **E2E-U-01** | 完整上传单 episode 并出现在历史与 QA 列表 | P0 | 已登录 operator；存在至少 1 个 task、1 台 machine；准备 1 个 episode：根目录 `ep1.mcap`，目录 `ep1/` 下约定数量 .mp4 | 1. 进入 /data/upload<br>2. 选择 task、machine<br>3. 选择上述文件（含 ep1.mcap、ep1/*.mp4）<br>4. 确认无格式错误，点击上传<br>5. 等待上传完成（含 manifest）<br>6. 等待 Worker 处理（可轮询或事件）<br>7. 进入 Upload History<br>8. QA 账号进入 /data/review | 1. tasks/machines 加载成功，可选<br>2. 格式校验通过，可提交<br>3. POST upload-sessions 返回 200，有 upload_id、signed_urls<br>4. 所有 PUT 成功，manifest 上传成功<br>5. 前端提示上传完成<br>6. 该 upload 下 episode 为 DERIVED_READY，upload status 为 DERIVED_READY<br>7. 历史列表含该 upload_id，状态正确<br>8. QA 列表含该 upload，可选该 task 进入审核 |
| **E2E-U-02** | 多 episode 上传 | P0 | 同 E2E-U-01；准备 2 个及以上 episode（ep1.mcap + ep1/*.mp4，ep2.mcap + ep2/*.mp4…） | 1. 进入 /data/upload，选 task、machine<br>2. 选择所有 episode 文件<br>3. 上传至完成<br>4. 等待 Worker 处理完所有 episode | 格式通过；session 返回 episode_count 与所选一致；每个 episode 均有 manifest；Worker 逐个处理；data_episodes 条数等于 episode 数；全部 DERIVED_READY 后 data_uploads.status=DERIVED_READY |
| **E2E-U-03** | 格式错误：根目录无 .mcap | P1 | 已登录 operator；仅有某目录下 .mp4，无根目录 .mcap | 选择该目录下 .mp4 文件，尝试上传 | 前端格式校验报错（如 no episode keys），上传不可用或提交被阻；不调用 POST upload-sessions |
| **E2E-U-04** | 格式错误：episode 目录下 .mp4 数量不符 | P1 | 已登录 operator；有 ep1.mcap，但 ep1/ 下 .mp4 数量与 task data_format 约定不符（如要求 3 个仅 2 个） | 选择文件后查看校验结果 | 前端展示明确 errors（如 mp4 数量），上传不可用或提交被阻 |
| **E2E-U-05** | 格式错误：文件夹名以 .mcap 结尾 | P1 | 已登录 operator；存在名为 `xx.mcap` 的文件夹且其下含 .mp4 | 选择包含该结构的文件 | 前端校验报错（非法目录结构），上传不可用或提交被阻 |
| **E2E-U-06** | 未选 task 或 machine 时上传 | P1 | 已登录 operator；已选合法文件 | 不选 task 或 不选 machine，点击上传 | 前端提示需选择 task 和 machine，不发起 POST upload-sessions 或请求被前端拦截 |
| **E2E-U-07** | 非 operator 调用上传会话 API | P1 | 已登录 qa 或普通用户；有合法 task_id、machine_id、files | 通过前端或接口直接 POST /data/upload-sessions | 后端返回 403，msg 含 operator；不创建 data_uploads/data_episodes |
| **E2E-U-08** | 无 token 创建上传会话 | P1 | 未登录或 token 失效 | POST /data/upload-sessions 无 Authorization、body 无 token | 401，msg 如 token is required 或 invalid token |
| **E2E-U-09** | 上传历史：有记录 | P0 | 已登录 operator；该用户至少有 1 条上传记录 | 进入 /data/history | 列表展示最近记录，含 upload_id、task、machine、status、created、uploaded；与 GET /data/uploading-history 一致 |
| **E2E-U-10** | 上传历史：无 token | P1 | 未登录或 token 失效 | 进入 /data/history | 列表为空或提示需登录；GET /data/uploading-history 返回 400/401 |

---

### 9.2 QA 审核流程（QA）

| 编号 | 标题 | 优先级 | 前置条件 | 步骤 | 预期结果 |
|------|------|--------|----------|------|----------|
| **E2E-Q-01** | QA 完整审核单 episode 并提交评分 | P0 | 已登录 qa；存在至少 1 个 DERIVED_READY 的 upload | 1. 进入 /data/review<br>2. 在列表中找到并点击某 task 的 Review<br>3. 选择该 task 下的一个 upload<br>4. 等待 episodes 加载，选择第一个 episode<br>5. 确认 derived 视频可播放<br>6. 输入分数（0–100）和可选备注<br>7. 点击提交 review<br>8. 刷新或重新进入该 upload episodes 列表 | 1. GET /data/qa/uploads 200，列表有数据<br>2. 进入 /data/review/:taskId<br>3. 选 upload 后 GET episodes 200，有 derived_videos<br>4. 视频区域展示，signed URL 可播放<br>5. 播放正常<br>6. 若无 session 先 POST /data/qa/sessions 再 POST review<br>7. 提交成功提示；data_qa_sessions 有记录<br>8. 该 episode 的 review_count、avg_score 更新 |
| **E2E-Q-02** | QA 对同一 episode 先创建 session 再提交 review | P0 | 已登录 qa；某 upload 有 DERIVED_READY 的 episode 且该 episode 尚无 QA session | 1. 进入该 upload 的 episodes，选该 episode<br>2. 输入分数与备注，提交 review | 首次提交时先 POST /data/qa/sessions（episode_id），再 POST review；返回 200；DB 有 1 条 data_qa_sessions，qa_score/note 正确 |
| **E2E-Q-03** | QA 对同一 episode 再次提交更新评分 | P1 | 已登录 qa；该 episode 已有当前用户的一条 QA session | 修改分数和备注，再次点击提交 review | POST /data/qa/sessions/<id>/review 200；DB 中该 session 的 qa_score、note 更新；前端可刷新看到新 avg_score |
| **E2E-Q-04** | Episodes 分页 | P1 | 已登录 qa；某 upload 的 DERIVED_READY episodes 数 > 5 | 1. 选择该 upload<br>2. 观察首屏加载的 episodes<br>3. 滚动或切换至更多 episodes | 首批 limit=5；后续按 5 条追加；total_count、has_more 正确；所有 episode 的 derived_videos 可访问 |
| **E2E-Q-05** | 评分边界：未填分数提交 | P1 | 已登录 qa；已选 episode，未填分数 | 点击提交 review | 前端提示需输入 0–100 分数，不提交或后端返回 400 |
| **E2E-Q-06** | 评分边界：分数超出 0–100 | P1 | 已登录 qa；已选 episode | 输入 <0 或 >100 或非数字，提交 | 前端校验限制在 0–100 或后端 400 |
| **E2E-Q-07** | 非 QA 进入 Verify Quality | P1 | 已登录 operator 或普通用户 | 1. 进入 /data<br>2. 点击侧栏 Verify Quality | Verify Quality 置灰或点击后提示需 QA 角色；不调用 /data/qa/* 或调用返回 403 |
| **E2E-Q-08** | 无 token 访问 QA 列表 | P1 | 未登录或 token 失效 | 直接请求 GET /data/qa/uploads（无 Authorization） | 401；前端若从 /data/review 进入则提示错误或列表为空 |

---

### 9.3 路由与导航

| 编号 | 标题 | 优先级 | 前置条件 | 步骤 | 预期结果 |
|------|------|--------|----------|------|----------|
| **E2E-R-01** | /data 默认进入上传 | P1 | 已登录 | 访问 /data 或 /data/ | 重定向到 /data/upload；侧栏 Upload Data 高亮 |
| **E2E-R-02** | 上传 / 历史 / 审核 / Preview 导航 | P1 | 已登录 | 依次点击 Upload Data、Upload History、Verify Quality（若为 QA）、Preview Datasets | 路由分别为 /data/upload、/data/history、/data/review、/data/preview；对应侧栏高亮；Preview 为占位 “Coming soon” |
| **E2E-R-03** | 从 Review 列表进入某 task 审核 | P1 | 已登录 qa；存在可审核的 upload | 在 /data/review 点击某 task 卡片的 Review | 跳转 /data/review/:taskId；该 task 的 upload 列表展示，可选 upload 看 episodes |
| **E2E-R-04** | 审核页返回列表 | P1 | 已在 /data/review/:taskId | 点击返回或 Back | 回到 /data/review（任务列表） |

---

### 9.4 元数据与配置

| 编号 | 标题 | 优先级 | 前置条件 | 步骤 | 预期结果 |
|------|------|--------|----------|------|----------|
| **E2E-M-01** | 上传页加载 tasks 与 machines | P0 | 后端有 data_tasks、data_machines 数据 | 进入 /data/upload | 无报错；任务列表、机器列表有数据；scenario 筛选可选（若有 environment/scenario） |
| **E2E-M-02** | 环境 URL：Beta 使用 Data Pipeline Beta URL | P1 | 前端部署在 Beta 域名（如 beta-app.prismax.ai） | 在上传或 QA 流程中触发任意 Data 请求 | 请求发往 PRISMAX_DATA_PIPELINE_URL（Beta）；无 CORS 错误 |
| **E2E-M-03** | 本地开发使用 8082 | P2 | 本地运行前端，NODE_ENV=development 或 host localhost | 触发 Data 请求 | 请求发往 http://127.0.0.1:8082 |

---

### 9.5 异常与空状态

| 编号 | 标题 | 优先级 | 前置条件 | 步骤 | 预期结果 |
|------|------|--------|----------|------|----------|
| **E2E-E-01** | 上传会话 API 缺 task_id/machine_id | P1 | 已登录 operator | POST /data/upload-sessions，body 缺 task_id 或 machine_id | 400，msg 含 task_id and machine_id are required |
| **E2E-E-02** | 上传会话 API files 缺少 manifest 占位 | P1 | 已登录 operator；body 仅有 .mcap 与 .mp4，无 _MANIFEST.json 占位 | POST /data/upload-sessions | 400，msg 如 manifest required for each episode；可选 missing_manifests |
| **E2E-E-03** | Worker：manifest 中文件缺失 | P1 | 已创建 upload-session 并写入 data_episodes；GCS 上少传一个 manifest 中列出的文件 | 上传 _MANIFEST.json 触发 Worker | Worker 返回 200，body 含 missing；对应 data_episodes 该 episode status=FAILED |
| **E2E-E-04** | QA 列表无数据 | P1 | 已登录 qa；当前无 DERIVED_READY 的 upload（或 DB 为空） | 进入 /data/review | 展示 “No QA uploads ready for review” 或等价空态；无报错 |
| **E2E-E-05** | 上传历史空状态 | P1 | 已登录 operator；该用户从未上传 | 进入 /data/history | 展示 “No uploads yet” 或等价空态；表格无数据行 |

---

### 9.6 数据一致性校验（E2E 视角）

| 编号 | 标题 | 优先级 | 前置条件 | 步骤 | 预期结果 |
|------|------|--------|----------|------|----------|
| **E2E-D-01** | 创建会话后 DB 与响应一致 | P0 | 已登录 operator | 1. 完成 POST /data/upload-sessions（合法 body）<br>2. 查 DB：data_uploads、data_episodes | data_uploads 新增 1 条，status=UPLOADING，expected_episode_keys 与请求一致；data_episodes 条数 = len(expected_episode_keys)，raw_video_folder_path 与 upload_id、episode_key 对应 |
| **E2E-D-02** | Worker 完成后 episode 与 upload 状态 | P0 | 已完成单 episode 上传并上传 _MANIFEST.json | 等待 Worker 处理完成；查 DB 与 GCS | 该 episode status=DERIVED_READY，derived_video_folder_path 存在；GCS derived bucket 下有对应 .mp4；upload 的 data_uploads.status=DERIVED_READY（若仅 1 个 episode） |
| **E2E-D-03** | 提交 review 后会话与统计 | P0 | 已登录 qa；已对某 episode 提交 review | 1. 查 DB data_qa_sessions<br>2. 再次 GET /data/qa/uploads/<id>/episodes | 该 episode 有对应 data_qa_sessions，qa_score、note 正确；episodes 接口中该 episode 的 review_count、avg_score 正确 |

---

以上 E2E 用例可与「八、测试策略」中的冒烟与回归配合使用：P0 用例作为发布前必跑，P1/P2 纳入回归或按需执行。
