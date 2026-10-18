# app-prismax-rp-backend 变更分析（0bd8b82 至 414e7a2）

> 分析日期：2026-08-14  
> 仓库：`app-prismax-rp-backend`  
> 分支：`testing`  
> 范围：`0bd8b827^..414e7a2`（包含起始提交）  
> 规模：5 个提交、14 个文件、约 `+1462 / -85`

---

## 1. 总体结论

这批改动主要完成四件事：

1. 更可靠地区分 Beta/Production 数据集可见性。
2. 增加历史 Preview 数据的按 Task 回填能力。
3. 增加历史 MCAP graph 缓存回填任务。
4. 对新上传数据启用 Preview 自动选择和处理，并增强并发保护。

整体流程变为：

```text
历史数据
├── 按 Task 补齐最多 48 个 Preview
└── 批量补齐 mcap_graph.json

新数据
└── 定时扫描最新完成的 Upload
    └── 自动选择 Episode
        └── 生成 Preview
```

## 2. 提交列表

| Commit | 日期 | 标题 |
| --- | --- | --- |
| `0bd8b82` | 2026-08-12 | Recognize beta marketing dataset origin |
| `9de6d42` | 2026-08-13 | Add task scoped preview backfill |
| `fb2a3d4` | 2026-08-13 | Include historical derived uploads in preview backfill |
| `96aec5d` | 2026-08-13 | Add MCAP graph backfill job |
| `414e7a2` | 2026-08-13 | Automate preview selection for new uploads |

## 3. 逐提交分析

### 3.1 `0bd8b82` — Recognize beta marketing dataset origin

修改：`app_prismax_data_pipeline/app.py`、`test_data_membership_downloads.py`。

数据任务可见性判断从主要依赖请求 `Origin`，改为按以下优先级判断：

1. `PRISMAX_ENV`
2. Cloud Run 的 `K_SERVICE`
3. 请求 `Origin` hostname
4. 请求目标 `Host`
5. 默认 Production

新增识别 `beta-www.prismax.ai`、`beta-app.prismax.ai`、Beta/testing Cloud Run service、localhost 和明确的 production/beta 环境变量。

影响：

- Beta marketing 站点会查询 `is_visible_beta`。
- 无 `Origin` 的服务间请求可以通过 `K_SERVICE` 正确识别。
- `PRISMAX_ENV=production` 优先级最高，可避免请求 Origin 误导生产服务。
- 不涉及数据库结构变化。

### 3.2 `9de6d42` — Add task scoped preview backfill

核心新增：

- `app_prismax_preview_worker/task_backfill_selection.py`
- `app_prismax_preview_worker/task_preview_backfill.py`
- 对应的两个测试文件

选择策略：

- 只处理 `is_visible_beta=true` 的 Task。
- 每个 Task 默认目标为 48 个 READY Preview。
- 已 READY 的 Episode 计入目标，不重复生成。
- 优先重试非 READY 记录，然后选择全新 Episode。
- Upload 按创建时间从新到旧排列。
- 不同 Upload 之间采用 round-robin，避免 Preview 全来自一个 Upload。
- 同一个 Upload 内使用 SHA-256 稳定排序，重跑结果一致。
- 12 个 Cloud Run Task 按 `task_id % task_count` 固定分片。

容错机制：

- 每个 Task 使用 PostgreSQL session advisory lock。
- 获取锁后重新查询，避免使用过期计划。
- 单个 Episode 失败不会立即终止整个 Task。
- 默认额外尝试 12 个 replacement candidate。
- Preview 目标路径冲突时不创建新对象。
- 最终未达到目标时，Job 以失败退出，便于监控。

新增手工 Cloud Run Job：

```text
app-prismax-preview-task-backfill
12 tasks / parallelism 12
target-per-task=48
timeout=4h
```

该 Job 只部署，不会被自动执行。

### 3.3 `fb2a3d4` — Include historical derived uploads in preview backfill

修改：`app_prismax_preview_worker/task_preview_backfill.py`。

最初 Preview backfill 同时要求：

```text
episode.status = DERIVED_READY
upload.status ∈ {DERIVED_READY, DERIVED_PARTIALLY_READY}
```

该提交移除了 Upload 状态限制，现在只要求 Episode 自身为 `DERIVED_READY`。

影响：

- 旧 Upload 状态不完整或未迁移时，只要 Episode 已完成 Derived，仍可进入回填。
- 历史数据覆盖率提高。
- 安全边界有所放宽：流程完全信任 Episode 状态，可能处理 Upload 整体未结束但个别 Episode 已 READY 的记录。
- 新数据自动选择不受影响，仍检查 Upload 最终状态。

### 3.4 `96aec5d` — Add MCAP graph backfill job

新增：

- `app_prismax_data_worker/mcap_graph_backfill.py`
- `app_prismax_data_worker/test_mcap_graph_backfill.py`

功能：

- 查询所有 `DERIVED_READY` 且有 Raw MCAP 路径的 Episode。
- 从 Raw bucket 下载 MCAP。
- 使用现有 `build_mcap_graph()` 生成 graph。
- 将 `mcap_graph.json` 写入对应 Derived Episode 目录。
- 已存在的 graph 自动跳过。

幂等与并发处理：

- 上传使用 `if_generation_match=0`，只允许对象不存在时创建。
- 并发创建时，后到者捕获 `PreconditionFailed` 并记为 `existing_race`。
- 相同目标目录对应多个 Episode 时视为碰撞，不写入。
- 12 个 Cloud Run Task 按 `episode_id % task_count` 分片。
- 支持 `--dry-run`、`--episode-ids` 和 `--limit`。

新增手工 Cloud Run Job：

```text
app-prismax-mcap-graph-backfill
12 tasks / parallelism 12
timeout=2h
```

注意：`--dry-run` 不创建 graph，但仍初始化 GCS Client 并查询对象是否存在，因此仍需要云端凭据和 Bucket 读取权限。

### 3.5 `414e7a2` — Automate preview selection for new uploads

主要修改 `app_prismax_preview_worker/worker.py`、README、自动选择测试和 `cloudbuild.yaml`。

#### 并发控制修复

旧代码使用事务级锁：

```sql
pg_advisory_xact_lock(...)
```

该锁只持续到选择 Episode 的数据库事务结束；视频处理期间锁已释放，仍可能重复转码。

新代码改为 session advisory lock：

- 开始处理 Upload 前获取锁。
- 整个视频处理期间保持锁连接。
- 无论成功或异常都在 `finally` 中释放。
- 获取不到锁时返回 `BUSY`，不会误标为 FAILED。

这是本提交最关键的正确性修复。

#### 自动扫描

`process_ready_uploads()` 现在：

- 只扫描 `DERIVED_READY` 或 `DERIVED_PARTIALLY_READY` 的 Upload。
- 只处理 `upload_id >= PREVIEW_AUTO_MIN_UPLOAD_ID`。
- 默认部署高水位为 `783`。
- 每次处理最新一个未完成 Upload。
- `PARTIAL/FAILED` 等待 30 分钟后重试。
- `PROCESSING` 超过 2 小时视为 stale，允许重试。
- 高水位未配置或为 0 时拒绝执行。

高水位含义：

```text
upload_id < 783 → 历史数据，只走 backfill
upload_id ≥ 783 → 新数据，可进入自动 Preview 流程
```

Cloud Run Preview selection Job 的重试次数从 0 改为 1。

## 4. 风险和观察点

### 4.1 README 与 Cloud Build 的 Scheduler 表述不完全一致

README 说明 Scheduler 每 5 分钟自动触发，但 `cloudbuild.yaml` 只部署 Cloud Run Job，并明确说明不会创建 Scheduler trigger。

自动化成立的前提是 Scheduler 已在部署体系外创建。如果没有 Scheduler，代码虽支持自动处理，但不会自动运行。

建议确认：

- Scheduler 是否存在及是否每 5 分钟运行。
- Scheduler service account 是否有 Cloud Run Job 执行权限。
- Scheduler 是否调用正确区域和 Job。

### 4.2 `PREVIEW_AUTO_MIN_UPLOAD_ID=783` 是硬编码部署高水位

- Beta、Production 共享默认值时，可能不适合各自数据。
- 回滚或使用其他数据库时，`783` 不一定有意义。
- 建议按环境维护该 substitution，并监控第一个自动处理的 Upload。

### 4.3 路径冲突仍计入历史回填目标

冲突 Episode 会被排除，但 `target_count` 仍基于原始 eligible 数量。如果安全候选不足，任务产生 shortfall 并失败。

这不会覆盖数据，但可能出现“大部分已成功，Job 仍失败”的运维现象。

### 4.4 MCAP graph backfill 没有数据库状态记录

它只依赖 GCS 对象是否存在判断完成情况。

优点是实现简单、重跑安全；缺点是无法直接从数据库查询进度，失败详情主要依赖 Cloud Logging，需要结合 Job summary 或 GCS inventory 核对完成度。

### 4.5 自动 Preview 采用最新优先

扫描按 `created_at DESC, upload_id DESC` 选择。失败 Upload 有 30 分钟冷却，不会每 5 分钟永久堵塞，但在新 Upload 持续进入时，旧 Upload 可能延迟较长。

## 5. 测试结果

本次新增的纯选择算法测试已实际运行：

```text
8 tests passed
```

覆盖稳定排序、Upload 间 round-robin、READY 计数、replacement candidate 和 Task 分片。

其余测试在当前宿主 Python 环境中因缺少 `sqlalchemy` 和 Google Cloud 依赖，未能导入运行。这是本地依赖问题，不是测试断言失败。

分析过程未修改 `app-prismax-rp-backend` 仓库。

## 6. 上线前建议验证

### P0

1. 确认 Cloud Scheduler 已创建并能执行 `app-prismax-preview-selection`。
2. 确认各环境 `PREVIEW_AUTO_MIN_UPLOAD_ID` 的值。
3. 并发执行同一 Upload，验证只有一个进程获得 advisory lock，另一个返回 `BUSY`。
4. 验证 `PARTIAL/FAILED` 在 30 分钟内不重试，之后可以重试。
5. 验证 `PROCESSING` 超过 2 小时会重新进入自动处理。

### P1

1. Preview task backfill 先执行 `--dry-run`，核对目标数、READY 数和冲突数。
2. 验证多 Upload Task 按 round-robin 选择。
3. 验证 Episode 失败后使用 replacement candidate 补足目标。
4. MCAP graph backfill 先用少量 `--episode-ids` 验证路径和内容。
5. 并行运行 graph backfill，确认条件写入能安全处理竞争。

## 7. 最终评价

这 5 个提交形成了较完整的数据补全和自动化链路：

- 数据集环境识别更可靠；
- 历史 Preview 可按 Task 均衡补齐；
- 历史 MCAP graph 可幂等批量生成；
- 新 Upload 可自动进入 Preview 流程；
- Upload/Task 级 advisory lock 降低了重复转码和并发写入风险。

上线前最值得确认：

1. Cloud Scheduler 是否已配置为每 5 分钟执行 `app-prismax-preview-selection`。
2. 各部署环境的 `PREVIEW_AUTO_MIN_UPLOAD_ID` 是否都应为 `783`。
