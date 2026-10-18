# 2026-07-09 Pipeline 多视频支持与 Upload Pause - 改动逻辑与 E2E 测试用例

## 一、分析范围

### 前端仓库

仓库：`app-prismax-rp`  
分支：`testing`  
作者：`lanmanc <zfc6861@qq.com>`

涉及提交：

| Hash | 日期 | Commit Message |
|---|---|---|
| `532649d` | 2026-07-07 | reinforce crypto payment |
| `9644bcf` | 2026-07-08 | updated pipeline support addtion videos other than 3 |
| `7902582` | 2026-07-08 | created pause upload |
| `46bca02` | 2026-07-08 | improved paused for upload |
| `a5bf753` | 2026-07-08 | clarify upload pause worker status |
| `17ff1e5` | 2026-07-08 | clean readme |

### 后端仓库

仓库：`app-prismax-rp-backend`  
分支：`testing`  
作者：`lanmanc <zfc6861@qq.com>`

涉及提交：

| Hash | 日期 | Commit Message |
|---|---|---|
| `d2b8b39` | 2026-07-07 | Merge branch 'testing' of https://github.com/PrismaXAI/app-prismax-rp-backend into testing |
| `1adc67d` | 2026-07-08 | updated pipeline support addtion videos other than 3 |
| `e70e1e6` | 2026-07-08 | Merge branch 'testing' of https://github.com/PrismaXAI/app-prismax-rp-backend into testing |
| `fc5670a` | 2026-07-08 | added paused fuction |
| `9c72c7e` | 2026-07-08 | improved paused for upload |
| `b0513ea` | 2026-07-08 | relax upload pause blocking |

备注：

- `e70e1e6` 是 merge commit，把 PRIS-247 MCAP graph 后端能力合入主线，已在 `PRIS_addmcapdatadisplaypanel.md` 中分析。
- 本文重点分析 lanmanc 的业务主线：多视频支持、Upload Pause、支付确认增强、Admin 下载 visibility 逻辑调整。

---

## 二、一句话主线

这组改动把数据 pipeline 从“每个 episode 固定 1 个 MCAP + 3 个 MP4”升级为“每个 episode 至少包含 env/left/right 三个主视频，同时允许额外视频随包下载”；同时新增管理员 Upload Pause 控制，让平台维护期间可以阻止新建/恢复上传，但不强行中断已在 worker DERIVING 的任务。

---

## 三、核心改动概览

| 模块 | 改动 |
|---|---|
| 上传文件校验 | 前后端都从“必须 exactly 3 个 mp4”改为“至少 3 个 mp4，且能识别 env/left/right 主视频” |
| 主视频选择 | env/high、left、right 按文件名优先级选择 primary，其他 mp4 归入 additional videos |
| Worker 派生处理 | 所有 mp4 都检查 duration；只有 primary env/left/right 参与 derived video 与 vPDQ |
| 下载 payload | `assets` 保留 `mcap/env/left/right`，新增 `additional_videos` 数组 |
| Robotic Data 文件计数 | UI 不再固定按 `episode * 4` 计算，而是使用后端返回的 `video_count` |
| Admin Upload Pause | 新增 `/data/admin/upload-control` 管理接口和 UI 控制卡片 |
| 普通上传入口 | `/data/upload-control` 提供暂停状态；上传页在暂停时隐藏任务卡并显示维护提示 |
| API 上传入口 | `/v1/data/upload-sessions` 和 resume 也会被暂停状态拦截 |
| Crypto payment | Solana 支付提交后等待链上 confirmed，再调用后端记录付款 |
| Admin Download visibility | Admin 下载列表不再硬编码排除 task 12，改为使用 task visibility column |

---

## 四、多视频支持改动逻辑

## 4.1 旧逻辑问题

旧逻辑隐含假设：

- 每个 episode 必须有 1 个 `.mcap`。
- 每个 episode 必须正好有 3 个 `.mp4`。
- 3 个视频分别是：
  - env/high/environment
  - left
  - right
- 文件数量固定后，下载 manifest、API package、UI 选择计数都可以按 `episode_count * 4` 计算。

问题：

- 新数据采集可能包含超过 3 个视频，例如额外视角、debug camera、第三方摄像头等。
- 如果仍要求 exactly 3 个 mp4，会阻塞合法数据上传。
- 如果下载端仍固定取 3 个视频，会导致额外视频不可下载，或者 manifest 文件数量计算错误。

## 4.2 前端上传校验

提交：`9644bcf`  
文件：`src/components/Data/FileFormatCheck/mcapMp4.js`

核心变化：

- `REQUIRED_VIDEO_COUNT = 3` 改为 `MIN_VIDEO_COUNT = 3`。
- 新增 `VIDEO_SLOTS = ['env', 'left', 'right']`。
- 每个 episode 统计：
  - `mcapCount`
  - `mp4Count`
  - `videoPaths`
- 新增 primary video 选择逻辑：
  - 文件名包含 `left` -> left slot
  - 文件名包含 `right` -> right slot
  - 其他 mp4 -> env slot
- 每个 slot 的 primary 优先级：
  - env: 文件名 stem 正好是 `high` 或 `env` 优先
  - left: stem 正好是 `left` 优先
  - right: stem 正好是 `right` 优先
  - 其次按文件名排序
- 校验规则变为：
  - episode 必须 exactly 1 个 `.mcap`
  - episode 至少 3 个 `.mp4`
  - 必须能选出 env/left/right 三个 primary mp4

业务意义：

- 允许一个 episode 有 4 个、5 个或更多 mp4。
- 仍保证 pipeline 最核心的 env/left/right 三路主视频存在。
- 额外视频不会干扰主视频选择。

## 4.3 后端上传会话校验

提交：`1adc67d`  
文件：`app_prismax_data_pipeline/app.py`

新增函数：

```python
_validate_upload_primary_videos(files)
```

覆盖入口：

- `POST /data/upload-sessions`
- `POST /data/upload-sessions/<upload_id>/resume`
- `POST /v1/data/upload-sessions`
- `POST /v1/data/upload-sessions/<upload_id>/resume`

校验逻辑与前端保持一致：

- episode 根目录必须有 exactly 1 个 `.mcap`。
- episode 文件夹下必须至少 3 个 `.mp4`。
- episode 文件夹内只允许 `.mp4` 文件。
- `.mp4` 扩展名必须小写。
- episode 文件必须直接位于 `{episode}/filename.mp4`，不允许多层目录。
- 必须能选出 primary env/high、left、right。

失败响应：

```json
{
  "success": false,
  "msg": "upload files failed mcap/mp4 validation",
  "validation_errors": []
}
```

业务意义：

- 前端校验不是唯一防线，API 上传也被后端统一保护。
- 防止绕过 UI 上传结构非法的数据。

## 4.4 Worker 处理逻辑

提交：`1adc67d`  
文件：

- `app_prismax_data_worker/worker.py`
- `app_prismax_data_worker/backfill_video_vpdq.py`

核心变化：

- 新增 `_split_primary_additional_video_paths(video_paths)`。
- manifest processing 阶段从 mp4 列表中选出：
  - `primary_video_paths_by_slot`
  - `additional_video_paths`
- 若缺少 primary env/left/right，则记录 `primary_video_validation` 错误，episode processing failed。
- 所有 mp4 仍会检查存在性、大小、duration。
- 只有 primary videos 会进入：
  - derived video 生成
  - vPDQ duplicate review
- additional-only videos：
  - duration checked
  - skipped vPDQ/derived

业务意义：

- 额外视频作为原始数据保留并可下载。
- 不扩大派生处理和重复检测的计算成本。
- 旧的核心质量检查仍集中在 env/left/right 三路主视频。

## 4.5 下载与 API Package Payload

提交：`1adc67d`  
文件：`app_prismax_data_pipeline/app.py`

核心变化：

- 新增 `VIDEO_SLOT_KEYS = ("env", "left", "right")`。
- 新增 `_split_primary_additional_videos(video_items, path_getter)`。
- 新增 `_download_asset_sequence(sample)`，下载顺序固定为：
  1. mcap
  2. env
  3. left
  4. right
  5. additional videos
- raw sample payload、CDN sample payload、metadata sample payload 都新增：

```json
{
  "assets": {
    "mcap": {},
    "env": {},
    "left": {},
    "right": {}
  },
  "additional_videos": []
}
```

- direct download file list 也从 `sample["assets"].values()` 改为 `_download_asset_sequence(sample)`。
- API download session cookie 授权也覆盖 additional videos。

业务意义：

- API client 可以稳定使用 `assets.mcap/env/left/right` 获取主文件。
- 额外视频通过 `additional_videos` 单独暴露，不破坏旧字段结构。
- 下载授权、manifest、直链下载都覆盖额外视频。

## 4.6 Robotic Data UI 文件计数

提交：`9644bcf`

涉及文件：

- `src/components/RoboticData/RoboticDataWorkspace.js`
- `src/components/RoboticData/RoboticDataAdmin.js`
- `src/components/RoboticData/apiPackageExample.js`

核心变化：

- 后端 `get_downloadable_uploads` 和 `get_admin_downloadable_upload_groups` 返回 `video_count`。
- 前端 episode 的 `mp4Count` 从固定 `3` 改为：

```js
Number(episode?.video_count) || 3
```

- selected file count 从：

```js
selectedEpisodeCount * FILES_PER_EPISODE
```

改为：

```js
selectedMcapCount + selectedVideoCount
```

- manifest over-limit 文案显示真实文件数。
- API package 示例代码新增下载 `additional_videos`。

业务意义：

- 选择 1 个 episode 时，如果实际有 5 个 mp4，UI 会按 6 个文件计算，而不是 4 个。
- manifest limit 判断更准确。
- 用户复制 API 示例时不会漏下 additional videos。

---

## 五、Upload Pause 改动逻辑

## 5.1 后端系统设置表

提交：`fc5670a`  
新增 SQL：`app_prismax_data_pipeline/sql/20260708_data_system_settings.sql`

新增表：

```sql
CREATE TABLE IF NOT EXISTS data_system_settings (
    setting_key TEXT PRIMARY KEY,
    value_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_by_admin_id BIGINT
);
```

Upload pause 使用固定 key：

```txt
data_upload_pause
```

默认暂停文案：

```txt
Data uploads are temporarily paused while we upgrade the system. Please come back soon.
```

## 5.2 普通用户查询暂停状态

新增接口：

```http
GET /data/upload-control
```

返回：

```json
{
  "success": true,
  "data": {
    "paused": false,
    "message": "...",
    "updated_at": null,
    "updated_by_admin_id": null
  }
}
```

前端 Upload 页面：

- 页面加载时查询一次。
- 每 60 秒轮询一次。
- 如果 `paused=true`：
  - 显示 Upload paused 维护页面。
  - 隐藏正常 task card grid。
  - 禁止开始 upload flow。
  - 关闭 upload info modal、file modal、upload session view。
  - 点击 `Check again` 重新查询状态。

## 5.3 管理员控制接口

新增接口：

```http
GET /data/admin/upload-control
POST /data/admin/upload-control
```

权限：

- 需要 admin JWT。

GET 返回：

- 当前 paused setting。
- 当前 admin id。
- `recent_active`：最近 24 小时 active upload/episode 统计。
- `older_stuck`：24 小时以前仍处于 UPLOADING/UPLOADED/DERIVING 的历史卡住记录。

POST body：

```json
{
  "paused": true
}
```

POST 成功后写入 `data_system_settings`。

## 5.4 Pause 阻塞策略变化

初始版本 `fc5670a`：

- 当有任何 `UPLOADING`、`UPLOADED`、`DERIVING` upload 或 episode 时，禁止 pause。
- 返回 `409 DATA_UPLOAD_ACTIVE`。

优化版本 `9c72c7e`：

- 只统计最近 24 小时 active flow。
- 额外暴露 older stuck records，便于 admin 判断历史脏数据。
- 时间统一用 UTC ISO 格式。

最终版本 `b0513ea`：

- pause 阻塞条件从“有 recent active flow”放宽为“worker 正在 DERIVING”。
- `UPLOADING` / `UPLOADED` 记录只提示 admin review，不直接阻塞 pause。
- 后端返回：
  - `has_worker_activity`
  - `worker_deriving_count`

业务意义：

- 平台维护时可以尽快暂停新上传。
- 不会因为历史 UPLOADED/UPLOADING 脏记录永久无法暂停。
- 仍避免在 worker 正在 DERIVING 时切断新入口导致状态不一致。

## 5.5 Admin UI

提交：

- `7902582`
- `46bca02`
- `a5bf753`

新增组件：

```txt
src/components/Admin/DataUploadPauseControl.js
```

UI 功能：

- 显示当前状态：
  - `Uploads paused`
  - `Uploads enabled`
- 显示 recent uploads / worker episodes 状态计数。
- 显示 recent upload IDs 和 recent worker episode IDs。
- 显示 older stuck records。
- 显示 Manifest worker status：
  - `DERIVING: N`
  - `No active manifest worker`
- 当 `worker_deriving_count > 0` 时，Pause uploads 按钮 disabled。
- `Resume uploads` 不受 deriving 阻塞限制。
- 支持 `Check status` 手动刷新。
- 组件最终放在 Admin general tab 的较后位置。

---

## 六、Crypto Payment 增强

提交：`532649d`  
文件：`src/components/header/ConnectWalletHeader.js`

核心变化：

- Solana transaction 构建前获取 latest blockhash。
- `provider.signAndSendTransaction(transaction)` 返回值兼容：
  - string signature
  - object.signature
  - Uint8Array signature，使用 `bs58.encode`
- 如果 wallet 没有返回 signature，抛出明确错误。
- 提交交易后先显示 info notification：
  - submitted
  - waiting for confirmation
  - explorer link
- 调用：

```js
connection.confirmTransaction({
  signature,
  blockhash,
  lastValidBlockHeight,
}, "confirmed")
```

- 如果 confirmation 有 error，则认为支付失败。
- 确认成功后再显示 success notification，并调用后端记录 payment。
- `onMembershipPaymentSuccess` 优先使用后端返回的：

```js
data.data?.transaction_hash
```

没有时 fallback 到本地 signature。

业务意义：

- 避免交易刚 submit 但尚未 confirmed 时就提示成功。
- 兼容不同 wallet adapter 的 signature 返回格式。
- 降低支付记录和链上状态不一致的风险。

---

## 七、Admin Download Visibility 调整

提交：`d2b8b39`  
文件：`app_prismax_data_pipeline/app.py`

核心变化：

- Admin downloadable upload groups 原逻辑：

```python
AND COALESCE(u.task_id, -1) <> 12
```

- 改为读取 task visibility column：

```python
visibility_column = _get_data_tasks_visibility_column()
tasks_visibility_clause = "" if include_test_uploads else f"AND (t.task_id IS NULL OR t.{visibility_column} = true)"
```

业务意义：

- 不再硬编码排除 task 12。
- Admin 数据下载列表和任务 visibility 配置保持一致。
- `include_test_uploads=true` 时仍可包含测试/不可见任务。

---

## 八、README 清理

提交：`17ff1e5`  
文件：`API_README.md`

改动：

- 删除旧的 API README 内容。

影响：

- 不改变运行时逻辑。
- 风险主要是文档可追溯性降低，建议确认是否已有新的 API 文档来源替代。

---

## 九、影响范围与风险点

| 模块 | 风险等级 | 风险说明 |
|---|---|---|
| 上传校验 | 高 | 前后端校验规则改变，可能影响所有 mcap/mp4 上传 |
| Worker manifest processing | 高 | additional videos 的处理方式改变，需确保主视频派生不漏、不误选 |
| API package/download session | 高 | Payload 增加 `additional_videos`，需验证旧 client 不受影响，新 client 能下载全量文件 |
| Robotic Data manifest limit | 中 | 文件数改为动态计算，需验证 over-limit 文案和按钮状态 |
| Admin Upload Pause | 高 | 会影响所有新建/恢复上传入口，包括 UI 上传和 API 上传 |
| Upload 页面轮询 | 中 | 暂停/恢复状态变化应及时反映，不能卡住用户流程 |
| Payment confirmation | 中 | 支付路径增加确认等待，需验证不同 wallet 返回格式 |
| Admin visibility | 中 | 下载列表范围从硬编码变为 visibility 配置，可能改变 admin 可见数据 |
| README 删除 | 低 | 无运行时影响，但需确认文档迁移 |

---

## 十、E2E 测试前置条件

### 账号与权限

- Operator 用户：可进入 Upload 页面并上传数据。
- Admin 用户：可进入 Admin Portal，拥有 admin token。
- API key 用户：可调用 `/v1/data/upload-sessions`。
- 普通非 operator 用户：用于验证 upload gate 不被破坏。

### 测试数据

建议准备以下文件集合：

| 数据集 | 结构 |
|---|---|
| 标准 3 视频 | `ep1.mcap` + `ep1/high.mp4` + `ep1/left.mp4` + `ep1/right.mp4` |
| 4 视频 | 标准 3 视频 + `ep1/wrist.mp4` |
| 5+ 视频 | 标准 3 视频 + 多个 additional mp4 |
| 缺 left | `high.mp4` + `right.mp4` + additional mp4 |
| 缺 env/high | `left.mp4` + `right.mp4` + additional mp4 |
| 大写扩展名 | `left.MP4` |
| 多层目录 | `ep1/cam/left.mp4` |
| 非 mp4 文件 | `ep1/readme.txt` |
| 多 episode 混合 | ep1 3 视频，ep2 5 视频 |

### 环境状态

- 后端已执行或允许自动创建 `data_system_settings` 表。
- GCS bucket 可访问。
- Worker 可正常处理 manifest。
- Robotic Data 下载功能可访问。
- Solana 测试钱包有足够余额，用于支付确认测试。

---

## 十一、E2E 测试用例与建议补充检查点

| 类型 | 模块 | ID | 标题/检查点 | 前置条件 | 步骤/检查方式 | 预期结果/说明 |
|---|---|---|---|---|---|---|
| E2E | 多视频上传 | PIPELINE-VIDEO-E2E-001 | 旧格式 1 MCAP + 3 MP4 上传兼容 | Operator 登录；upload 未暂停 | 1. 进入 Upload 页面。<br>2. 选择 task 和 machine。<br>3. 上传标准 3 视频数据集。<br>4. 完成上传并等待 worker 处理。 | 1. 前端校验通过。<br>2. 后端 create upload session 成功。<br>3. Worker 正常生成 derived data。<br>4. Robotic Data 中 episode 可下载。 |
| E2E | 多视频上传 | PIPELINE-VIDEO-E2E-002 | Episode 超过 3 个 MP4 时上传成功 | Operator 登录；准备 4 视频数据集 | 1. 上传 `high.mp4`、`left.mp4`、`right.mp4`、`wrist.mp4`。<br>2. 等待 worker 完成。<br>3. 创建 API package 或 manifest download。<br>4. 查看 download session payload。 | 1. 上传校验通过。<br>2. `assets` 中包含 `mcap/env/left/right`。<br>3. `additional_videos` 中包含 `wrist.mp4`。<br>4. 下载文件数为 5。 |
| E2E | 多视频上传 | PIPELINE-VIDEO-E2E-003 | 多个候选视频时按优先级选择 primary | 准备 `env.mp4/high.mp4`、多个 left/right 候选和 additional 视频 | 1. 上传多视频 episode。<br>2. 查看后端 download payload。<br>3. 查看 derived/video duplicate 相关结果。 | 1. env slot 优先选择 stem 为 `high` 或 `env` 的文件。<br>2. left/right slot 优先选择 stem 正好为 `left` / `right` 的文件。<br>3. 未选中的 mp4 出现在 `additional_videos`。<br>4. vPDQ/derived 只针对 primary videos。 |
| E2E | 多视频上传 | PIPELINE-VIDEO-E2E-004 | 缺少 left MP4 时 mcap/mp4 前端校验失败 | 准备缺 left 数据集 | 1. 在 Upload 页面选择文件。<br>2. 触发文件格式校验。 | 1. 前端显示 episode 缺少 primary left。<br>2. Upload 按钮不可继续或流程被阻止。<br>3. 不创建 upload session。 |
| E2E | API 上传 | PIPELINE-VIDEO-E2E-005 | API upload session 后端校验缺 primary | API key 可用；准备缺 env/high 的 files payload | 1. 调用 `POST /v1/data/upload-sessions`。 | 1. 返回 `400`。<br>2. `success=false`。<br>3. `msg=upload files failed mcap/mp4 validation`。<br>4. `validation_errors` 包含缺少 env/high 信息。 |
| E2E | 多视频上传 | PIPELINE-VIDEO-E2E-006 | 多层目录、非 mp4、MP4 大写扩展名被拒绝 | 准备非法 files payload | 1. 分别上传 `ep1/cam/left.mp4`、`ep1/readme.txt`、`ep1/left.MP4`。 | 1. 前后端至少一层阻止上传。<br>2. 后端 validation error 指明非法路径或扩展名。 |
| E2E | Robotic Data | PIPELINE-VIDEO-E2E-007 | Robotic Data 选择多个 episode 时文件数按真实 video_count 计算 | ep1 有 3 视频，ep2 有 5 视频；均 DERIVED_READY | 1. 进入 Robotic Data Workspace。<br>2. 选择 ep1 和 ep2。<br>3. 查看 manifest 下载按钮状态和提示。 | 1. selected mcap count = 2。<br>2. selected video count = 8。<br>3. selected file count = 10。<br>4. 文案显示真实文件数而不是按 4 files/episode 固定估算。 |
| E2E | Robotic Data | PIPELINE-VIDEO-E2E-008 | additional videos 会计入 manifest 文件上限 | 准备多个多视频 episodes，使总文件数超过 `MANIFEST_DOWNLOAD_MAX_FILES` | 1. 在 Robotic Data Workspace/Admin 中选择这些 episodes。<br>2. 查看 manifest download 按钮和提示。 | 1. manifest 下载被禁用或给出 warning。<br>2. 提示包含真实 selected file count。<br>3. 建议使用 API download。 |
| E2E | API 下载 | PIPELINE-VIDEO-E2E-009 | API package 示例代码不会漏下载额外视频 | 已创建包含 additional_videos 的 package | 1. 复制 UI 中 API download example。<br>2. 替换 api key/package id 后执行。<br>3. 查看本地下载目录。 | 1. 下载 mcap/env/left/right。<br>2. 下载 additional videos。<br>3. 文件路径保持 `{episode}/{filename}`。<br>4. MD5 校验通过。 |
| E2E | Worker | PIPELINE-VIDEO-E2E-010 | additional-only 视频不参与 vPDQ/derived | 多视频 episode 完成 worker processing | 1. 查看 worker 日志。<br>2. 查看 vPDQ artifact 或 duplicate review 记录。 | 1. additional video 有 duration 检查日志。<br>2. additional video 有 skipped vPDQ/derived 日志。<br>3. vPDQ 记录只覆盖 primary env/left/right。 |
| E2E | Upload Pause | UPLOAD-PAUSE-E2E-001 | Admin Portal 显示 Data upload control | Admin 登录 | 1. 进入 Admin Portal general tab。<br>2. 查看 Data upload control 卡片。<br>3. 点击 Check status。 | 1. 卡片显示当前 paused/enabled 状态。<br>2. 显示 recent uploads、recent worker episodes、manifest worker status。<br>3. 请求 `/data/admin/upload-control` 返回 200。 |
| E2E | Upload Pause | UPLOAD-PAUSE-E2E-002 | 无 DERIVING worker 时 Admin 可暂停上传 | 无 recent DERIVING upload/episode；Admin 登录 | 1. 点击 `Pause uploads`。<br>2. 确认状态刷新。<br>3. 调用 `GET /data/upload-control`。 | 1. POST `/data/admin/upload-control` 返回 200。<br>2. UI 状态变为 `Uploads paused`。<br>3. 普通查询接口返回 `paused=true`。 |
| E2E | Upload Pause | UPLOAD-PAUSE-E2E-003 | Manifest worker 正在 DERIVING 时 Pause disabled 或后端 409 | 至少 1 个 recent DERIVING upload 或 episode | 1. 打开 Upload Control。<br>2. 查看 Manifest worker status。<br>3. 尝试点击 Pause uploads 或直接调用 POST paused=true。 | 1. UI 显示 `DERIVING: N`。<br>2. Pause uploads 按钮 disabled。<br>3. 若直接调用 API，返回 `409 DATA_UPLOAD_ACTIVE`。<br>4. 错误文案说明 worker is actively deriving。 |
| E2E | Upload Pause | UPLOAD-PAUSE-E2E-004 | 只有 UPLOADED/UPLOADING 记录时暂停不被硬阻塞 | recent records 中存在 UPLOADED 或 UPLOADING，但 `worker_deriving_count=0` | 1. 打开 Upload Control。<br>2. 查看 warning。<br>3. 点击 Pause uploads。 | 1. UI 提示 review recent upload records。<br>2. Pause 按钮可点击。<br>3. 后端返回 200。<br>4. 状态变为 paused。 |
| E2E | Upload Pause | UPLOAD-PAUSE-E2E-005 | paused=true 时普通 Upload 页面显示维护态并阻止开始上传 | Admin 已暂停上传；Operator 登录 | 1. 进入 Data Upload 页面。<br>2. 查看页面内容。<br>3. 点击 Check again。<br>4. 尝试从 task card 或 direct upload 入口开始上传。 | 1. 页面显示 `Upload paused`。<br>2. 显示系统升级文案。<br>3. 不显示正常 task grid 或不能进入上传流程。<br>4. Check again 会重新请求 `/data/upload-control`。 |
| E2E | Upload Pause | UPLOAD-PAUSE-E2E-006 | paused=true 时 `/data/upload-sessions` 返回 503 | paused=true；Operator token 可用 | 1. 直接调用 `POST /data/upload-sessions`。 | 1. 返回 `503`。<br>2. `success=false`。<br>3. `code=DATA_UPLOAD_PAUSED`。<br>4. `msg` 为暂停文案。 |
| E2E | Upload Pause | UPLOAD-PAUSE-E2E-007 | paused=true 时 `/v1/data/upload-sessions` 返回 503 | paused=true；API key 可用 | 1. 调用 `POST /v1/data/upload-sessions`。<br>2. 调用 resume API upload session。 | 1. 新建和 resume 都返回 `503 DATA_UPLOAD_PAUSED`。<br>2. 不生成新的 upload session。 |
| E2E | Upload Pause | UPLOAD-PAUSE-E2E-008 | Admin Resume uploads 后普通用户可上传 | paused=true；Admin 登录 | 1. Admin 点击 `Resume uploads`。<br>2. Operator 打开 Upload 页面并点击 Check again。<br>3. 开始一次标准上传。 | 1. Admin POST 返回 200。<br>2. `/data/upload-control` 返回 `paused=false`。<br>3. Upload 页面恢复 task grid。<br>4. 上传 session 可创建。 |
| E2E | Upload Pause | UPLOAD-PAUSE-E2E-009 | 24 小时以前的 stuck records 显示但不阻塞 pause | 构造 older UPLOADING/UPLOADED/DERIVING 记录，recent 无 DERIVING | 1. 打开 Upload Control。<br>2. 查看 Older stuck records。<br>3. 点击 Pause uploads。 | 1. UI 显示 older stuck records 数量和 oldest/latest 时间。<br>2. Pause 不因 older stuck records 被阻塞。<br>3. 后端返回 200。 |
| E2E | Upload Pause | UPLOAD-PAUSE-E2E-010 | 非 admin token 不能访问 `/data/admin/upload-control` | 普通用户 token 或无 token | 1. 调用 GET `/data/admin/upload-control`。<br>2. 调用 POST `/data/admin/upload-control`。 | 1. 返回 401/403。<br>2. 不泄露 active upload samples。<br>3. paused setting 不被修改。 |
| E2E | Payment | PAYMENT-E2E-001 | Solana membership payment confirmed 后记录付款 | 测试钱包余额充足；后端 payment API 可用 | 1. 发起 Solana membership payment。<br>2. 钱包签名并发送交易。<br>3. 等待 confirmed。<br>4. 查看通知和会员状态。 | 1. 先显示 submitted/waiting confirmation。<br>2. 链上 confirmed 后显示 success。<br>3. 后端 payment record 成功。<br>4. `onMembershipPaymentSuccess` 使用后端 transaction hash 或 fallback signature。 |
| E2E | Payment | PAYMENT-E2E-002 | string/object/Uint8Array signature 均能处理 | 可 mock wallet adapter 或使用不同钱包 | 1. 分别模拟 `signAndSendTransaction` 返回 string。<br>2. 返回 `{signature}`。<br>3. 返回 Uint8Array signature。 | 1. 三种格式都能得到有效 signature。<br>2. explorer link 正确。<br>3. 后续 confirmation 和 payment record 正常。 |
| E2E | Payment | PAYMENT-E2E-003 | confirmation 返回 error 时显示失败并不误报成功 | mock `confirmTransaction` 返回 `value.err` | 1. 发起支付。<br>2. 模拟交易确认失败。 | 1. 显示 transaction failed。<br>2. 不显示 confirmed successfully。<br>3. 不调用或不成功记录 payment。<br>4. processing 状态最终恢复。 |
| E2E | Admin Download | ADMIN-DOWNLOAD-E2E-001 | include_test_uploads=false 时按 task visibility 过滤 | 准备 visible task 和 hidden/test task 的 uploads | 1. 调用 admin downloadable upload groups，`include_test_uploads=false`。<br>2. 再调用 `include_test_uploads=true`。 | 1. false 时仅返回 visible task 或 task_id null 的 uploads。<br>2. true 时包含 hidden/test task uploads。<br>3. 不再只针对 task_id=12 做硬编码排除。 |
| 检查点 | 多视频 | PIPELINE-VIDEO-CHECK-001 | 前后端 primary video 选择规则必须一致 | 具备多视频测试数据；可对比 UI 校验和后端校验结果 | 检查前端 `mcapMp4.js` 与后端 `_validate_upload_primary_videos` / `_split_primary_additional_videos` 的 slot 判断和排序规则。 | 避免 UI 校验通过但后端拒绝，或前后端选出的 primary env/left/right 不一致。 |
| 检查点 | 多视频 | PIPELINE-VIDEO-CHECK-002 | additional videos 下载授权必须完整 | 有包含 additional videos 的 download session 或 API package | 检查 additional videos 的 signed URL 或 CDN cookie 授权。 | additional videos 可以成功下载，不出现 403、cookie 缺失或 URL 过期异常。 |
| 检查点 | API 下载 | PIPELINE-VIDEO-CHECK-003 | 旧客户端只读取 `assets` 时仍可下载核心 4 文件 | 已创建包含 additional videos 的 package；准备旧版下载脚本 | 使用只读取 `assets` 的旧逻辑下载。 | 旧客户端仍能下载 `mcap/env/left/right`，新增 `additional_videos` 不破坏旧字段结构。 |
| 检查点 | API 下载 | PIPELINE-VIDEO-CHECK-004 | 新客户端读取 `additional_videos` 时可下载全量文件 | 已创建包含 additional videos 的 package；准备新版下载脚本 | 使用读取 `assets` + `additional_videos` 的逻辑下载。 | 新客户端可下载核心文件和全部 additional videos。 |
| 检查点 | Worker | PIPELINE-VIDEO-CHECK-005 | backfill vPDQ 只处理 primary videos | 有多视频 episode；可调用或查看 backfill vPDQ 结果 | 检查 backfill 返回的 `raw_matched_count` 和 `matched_count`，并确认 matched rows 只包含 primary videos。 | `raw_matched_count` 和 `matched_count` 差异可解释，additional videos 不进入 vPDQ。 |
| 检查点 | Upload Pause | UPLOAD-PAUSE-CHECK-001 | 暂停开关不应中断已创建并正在上传文件的浏览器任务 | 一个上传任务已进入文件上传阶段；随后 admin 打开 paused | 观察正在上传的 session 和新建/resume session 行为。 | 已创建并正在上传的浏览器任务不被前端强制中断；新建/resume session 必须被拦截。 |
| 检查点 | Upload Pause | UPLOAD-PAUSE-CHECK-002 | paused 状态应对 UI 上传和 API 上传一致 | paused=true；Operator token 和 API key 均可用 | 分别通过 UI upload、`/data/upload-sessions`、`/v1/data/upload-sessions` 尝试创建或恢复上传。 | UI 和 API 入口都遵守 paused 状态，返回一致的 `DATA_UPLOAD_PAUSED` 语义。 |
| 检查点 | Upload Pause | UPLOAD-PAUSE-CHECK-003 | Admin active samples 不泄露敏感信息 | Admin 调用 `/data/admin/upload-control` | 检查 response 中的 `upload_samples`、`episode_samples`。 | 不包含 token、signed URL、Authorization header、用户私密凭据等敏感信息。 |
| 检查点 | Upload Pause | UPLOAD-PAUSE-CHECK-004 | `updated_by_admin_id` 和 `updated_at` 可用于审计 | Admin 执行 pause/resume | 查看 `/data/admin/upload-control` 和 `data_system_settings` 记录。 | 每次状态变更都记录更新时间和操作 admin id。 |
| 检查点 | Upload Pause | UPLOAD-PAUSE-CHECK-005 | 系统设置表创建策略可上线 | 目标环境 DB 权限明确 | 检查线上 DB 是否允许服务自动 `CREATE TABLE IF NOT EXISTS`；必要时执行 migration SQL。 | 若服务账号无建表权限，应通过 migration 预先执行 `20260708_data_system_settings.sql`。 |
| 检查点 | Payment | PAYMENT-CHECK-001 | confirmed 等待期间避免用户重复点击付款 | 钱包支付流程可用 | 发起付款后，在 waiting confirmation 阶段尝试重复点击付款按钮。 | UI 应禁用重复提交或保持 processing 状态，避免多笔重复交易。 |
| 检查点 | Payment | PAYMENT-CHECK-002 | confirmation 超时或 blockhash 过期时提示用户重试 | 可 mock Solana confirmation timeout/blockhash expired | 模拟 confirmation 长时间无结果或 blockhash 过期。 | 用户看到明确失败/重试提示，processing 状态恢复，不误报支付成功。 |
| 检查点 | Payment | PAYMENT-CHECK-003 | 后端 payment record 返回结构与前端兼容 | 后端 payment API 可用 | 检查 payment record response。 | 响应应兼容前端读取 `data.data?.transaction_hash`，否则前端可 fallback 到本地 signature。 |

---

## 十二、回归范围

需要重点回归：

- 标准 3 视频上传。
- API upload create/resume。
- Worker manifest processing。
- Robotic Data Workspace 下载 manifest / API package。
- Robotic Data Admin failed/raw manifest 下载。
- Data Upload 页面 task list、operator gate、file modal。
- Admin Portal general tab 其他模块布局。
- Membership crypto payment。
- Admin downloadable uploads visibility。
