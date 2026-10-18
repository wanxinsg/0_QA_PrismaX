# Video Duplicate Detection Overview｜视频重复检测概览

> Last updated: July 23, 2026 (see §11 for a code verification addendum)  
> 最后更新：2026 年 7 月 23 日（另见第 11 节代码核对补充说明）
>
> Current algorithm: `vPDQ v1`  
> 当前算法：`vPDQ v1`
>
> Current search engine: `Faiss BinaryFlat` (unconfirmed against deployed env vars — see §11.1)  
> 当前搜索引擎：`Faiss BinaryFlat`（尚未与已部署环境变量核实，见第 11.1 节）

## 1. Purpose｜目的

The system detects:  
系统用于检测：

- Exact reuploads.  
  完全相同的重复上传。
- Re-encoded videos.  
  重新编码的视频。
- Trimmed clips.  
  被裁剪的视频片段。
- Videos with filters, watermarks, or small visual changes.  
  添加滤镜、水印或有轻微视觉变化的视频。
- Videos copied from another machine.  
  从其他机器复制的视频。

vPDQ matches are sent to the Admin Panel for manual review. They do not automatically reject an upload.  
vPDQ 匹配结果会发送到 Admin Panel 进行人工审核，不会自动拒绝上传。

## 2. Current Detection Flow｜当前检测流程

### Step 1: File size check｜步骤 1：文件大小检查

The Worker compares:  
Worker 会比较：

- MCAP file size.  
  MCAP 文件大小。
- Total size of all video files.  
  所有视频文件的总大小。

If both values match an older `DERIVED_READY` episode, the new episode is marked:  
如果这两个值都与较早的 `DERIVED_READY` Episode 一致，新 Episode 会被标记为：

```text
DERIVED_VALIDATION_FAILED
```

Important:  
重要说明：

- Task 12 skips this size check.  
  Task 12 会跳过该文件大小检查。
- This check does not use SHA256.  
  该检查不使用 SHA256。
- It searches across all tasks, machines, and users.  
  该检查会跨所有 Task、Machine 和 User 搜索。

### Step 2: Generate vPDQ fingerprints｜步骤 2：生成 vPDQ 指纹

For each primary video:  
对于每个 Primary Video：

- `env`
- `left`
- `right`

The Worker keeps approximately one frame per second and converts each frame into a 256-bit vPDQ hash.  
Worker 大约每秒保留一帧，并将每一帧转换为一个 256-bit vPDQ Hash。

The result is stored in GCS:  
结果存储在 GCS：

```text
gs://prismax-data-derived-prod/duplicate-detection/vpdq/task_{task_id}/slot_{slot}/metadata_{metadata_id}.json
```

### Step 3: Find similar historical videos｜步骤 3：查找相似的历史视频

The system only compares videos with:  
系统只会比较满足以下条件的视频：

- The same `task_id`.  
  `task_id` 相同。
- The same `video_slot`.  
  `video_slot` 相同。
- A historical episode status of `DERIVED_READY`.  
  历史 Episode 状态为 `DERIVED_READY`。
- An older `metadata_id`.  
  `metadata_id` 更早。

`machine_id` is not used as a filter.  
`machine_id` 不作为筛选条件。

This means videos from different machines can still match, but videos from different tasks currently cannot.  
这意味着不同 Machine 的视频仍然可以互相匹配，但不同 Task 的视频目前无法互相匹配。

### Step 4: Faiss candidate search｜步骤 4：Faiss 候选搜索

Faiss stores all historical frame hashes for each:  
Faiss 会存储以下每种组合对应的全部历史帧 Hash：

```text
task_id + video_slot
```

The index is stored under:  
索引存储在：

```text
gs://prismax-data-derived-prod/duplicate-detection/vpdq-index/
```

For every new frame, Faiss finds the closest historical frames using Hamming distance.  
对于每个新帧，Faiss 使用 Hamming Distance 查找最接近的历史帧。

The system then:  
随后系统会：

- Remove weak frame matches.  
  移除弱匹配帧。
- Group matches by historical video.  
  按历史视频对匹配结果分组。
- Check whether matches follow a consistent time offset.  
  检查匹配结果是否遵循一致的时间偏移。
- Keep the best historical video candidates.  
  保留最佳历史视频候选。
- Run a detailed comparison on those candidates.  
  对这些候选执行详细比较。

### Step 5: Check recently uploaded videos｜步骤 5：检查最近上传的视频

A new vPDQ artifact is not immediately added to Faiss.  
新的 vPDQ Artifact 不会立即加入 Faiss。

Until the hourly index update runs, the Worker also checks recent videos that are not yet indexed.  
在每小时索引更新任务运行之前，Worker 还会检查尚未建立索引的近期视频。

This prevents a duplicate uploaded shortly after the original from being missed.  
这可以防止在原视频上传后不久上传的重复视频被漏检。

### Step 6: Detailed comparison｜步骤 6：详细比较

The system calculates three main values:  
系统会计算三个主要指标：

- `score`: matching coverage at the best time alignment.  
  `score`：最佳时间对齐条件下的匹配覆盖率。
- `shorter_coverage`: how much of the shorter video appears in the other video.  
  `shorter_coverage`：较短视频有多少内容出现在另一个视频中。
- `longest_run`: the longest continuous matching section.  
  `longest_run`：最长的连续匹配片段。

A video is sent for Admin Review if any condition is met:  
只要满足以下任意一个条件，视频就会被发送到 Admin Review：

- Score is at least 35%.  
  Score 至少为 35%。
- Shorter coverage is at least 40%.  
  Shorter Coverage 至少为 40%。
- Continuous matching section is at least 10 seconds.  
  连续匹配片段至少为 10 秒。

Each source video keeps at most the best 3 review candidates.  
每个 Source Video 最多保留 3 个最佳审核候选。

### Step 7: Admin review｜步骤 7：Admin 审核

Possible decisions:  
可选的审核决定：

#### Mark duplicate｜标记为重复

- Review status becomes `APPROVED`.  
  Review Status 变为 `APPROVED`。
- The uploaded source episode becomes `DERIVED_VALIDATION_FAILED`.  
  新上传的 Source Episode 变为 `DERIVED_VALIDATION_FAILED`。
- The older matched episode is not changed.  
  较早的 Matched Episode 不会被修改。

#### Not a duplicate｜不是重复视频

- Review status becomes `REJECTED`.  
  Review Status 变为 `REJECTED`。
- The source episode normally remains unchanged.  
  Source Episode 通常保持不变。
- If that review previously caused the failure, the episode can be restored to `DERIVED_READY`.  
  如果该 Review 之前导致 Episode 失败，则 Episode 可以恢复为 `DERIVED_READY`。

Review records are stored in:  
Review 记录存储在：

```text
data_video_duplicate_reviews
```

## 3. Key Settings｜关键配置

| Setting｜配置项 | Current value｜当前值 | Meaning｜含义 |
| --- | --- | --- |
| Frame sampling interval<br>帧采样间隔 | 1 second<br>1 秒 | Approximately one vPDQ hash per second.<br>大约每秒生成一个 vPDQ Hash。 |
| Faiss candidate Hamming distance<br>Faiss 候选 Hamming Distance | `45` | Loose first-stage candidate filtering.<br>较宽松的第一阶段候选过滤。 |
| Detailed Hamming distance<br>详细比较 Hamming Distance | `31` | Stricter frame matching.<br>更严格的帧匹配。 |
| Historical frames per new frame<br>每个新帧对应的历史帧数量 | `50` | Faiss frame-level search size.<br>Faiss 帧级搜索数量。 |
| Indexed video candidates<br>已索引视频候选数量 | `20` | Videos kept after Faiss grouping.<br>Faiss 分组后保留的视频数量。 |
| Recent unindexed candidates<br>近期未索引候选数量 | `200` | Maximum recent videos checked outside Faiss.<br>在 Faiss 之外检查的近期视频数量上限。 |
| Score threshold<br>Score 阈值 | `35%` | Sends candidate to Admin Review.<br>达到阈值时将候选发送到 Admin Review。 |
| Shorter coverage threshold<br>较短视频覆盖率阈值 | `40%` | Helps detect trimmed videos.<br>用于检测被裁剪的视频。 |
| Continuous match threshold<br>连续匹配阈值 | 10 seconds<br>10 秒 | Helps detect copied video sections.<br>用于检测被复制的视频片段。 |
| Reviews per source video<br>每个 Source Video 的 Review 数量 | `3` | Limits Admin Review volume.<br>限制 Admin Review 数量。 |
| Index update frequency<br>索引更新频率 | Hourly<br>每小时 | Adds recent artifacts to Faiss.<br>将近期 Artifact 加入 Faiss。 |
| Algorithm version<br>算法版本 | `vpdq-v1` | Identifies the current detection behavior.<br>标识当前检测行为。 |

Threshold conditions use `OR`. Meeting any one of them can create a review.  
阈值条件使用 `OR` 逻辑；满足任意一个条件即可创建 Review。

## 4. Index Maintenance｜索引维护

### Full index build｜全量索引构建

Cloud Run Job:  
Cloud Run 任务：

```text
prismax-vpdq-index-build
```

Use it only when:  
仅在以下情况使用：

- Building indexes from scratch.  
  从零开始构建索引。
- Recovering a broken index.  
  恢复损坏的索引。
- Changing the Faiss index type.  
  更改 Faiss 索引类型。
- Making a major fingerprint format change.  
  对指纹格式进行重大修改。

### Incremental index update｜增量索引更新

Cloud Run Job:  
Cloud Run 任务：

```text
prismax-vpdq-index-update
```

This job adds new vPDQ artifacts to existing Faiss indexes.  
该任务将新的 vPDQ Artifact 添加到现有 Faiss 索引中。

It does not generate missing vPDQ artifacts.  
该任务不会生成缺失的 vPDQ Artifact。

### Automatic schedule｜自动调度

Cloud Scheduler:  
Cloud Scheduler：

```text
prismax-vpdq-index-update-hourly
```

Schedule:  
调度表达式：

```cron
15 * * * *
```

It runs every hour at minute 15 UTC.  
该任务在 UTC 时间每小时的第 15 分钟运行。

Both manual and scheduled executions have been tested successfully.  
手动执行和定时执行均已测试成功。

## 5. What Can Be Changed Later｜后续可以修改的内容

### Safe to tune without rebuilding artifacts｜无需重建 Artifact 即可安全调整

- Score threshold.  
  Score 阈值。
- Shorter coverage threshold.  
  Shorter Coverage 阈值。
- Continuous matching threshold.  
  连续匹配阈值。
- Hamming distance thresholds.  
  Hamming Distance 阈值。
- Number of Faiss candidates.  
  Faiss 候选数量。
- Number of recent unindexed candidates.  
  近期未索引候选数量。
- Maximum reviews per video.  
  每个视频的最大 Review 数量。
- Index update frequency.  
  索引更新频率。

Threshold changes should be based on real Admin decisions, not only a few test videos.  
阈值修改应基于真实的 Admin 审核结果，而不应只依据少量测试视频。

### Requires rebuilding the Faiss indexes｜需要重建 Faiss 索引

- Changing from BinaryFlat to BinaryIVF.  
  从 BinaryFlat 更改为 BinaryIVF。
- Changing how indexes are divided.  
  更改索引的分片方式。
- Changing the Faiss mapping format.  
  更改 Faiss Mapping 格式。

Existing vPDQ artifacts can still be reused.  
现有 vPDQ Artifact 仍可复用。

### Requires regenerating vPDQ artifacts｜需要重新生成 vPDQ Artifact

- Changing the one-second sampling interval.  
  更改每秒一次的采样间隔。
- Changing the vPDQ hash algorithm.  
  更改 vPDQ Hash 算法。
- Changing the hash format.  
  更改 Hash 格式。
- Changing the artifact schema.  
  更改 Artifact Schema。

These changes should also use a new algorithm version.  
进行这些修改时还应使用新的算法版本。

## 6. Important Limitations｜重要限制

### No cross-task vPDQ search｜不支持跨 Task 的 vPDQ 搜索

vPDQ currently compares only within the same `task_id`.  
vPDQ 目前只在相同 `task_id` 内进行比较。

A video copied into another task may not be detected by vPDQ.  
被复制到另一个 Task 的视频可能无法被 vPDQ 检测到。

### Size matching can produce false positives｜文件大小匹配可能产生误报

The size check is fast but does not verify file content.  
文件大小检查速度很快，但不会验证文件内容。

Two different files could theoretically have the same MCAP and total video sizes.  
理论上，两个不同文件可能具有相同的 MCAP 大小和视频总大小。

### Missing artifacts are skipped｜缺失的 Artifact 会被跳过

The index updater cannot recreate missing vPDQ artifacts.  
索引更新器无法重新创建缺失的 vPDQ Artifact。

Missing historical fingerprints require a separate backfill.  
缺失的历史指纹需要通过单独的 Backfill 任务补齐。

### New videos are not immediately added to Faiss｜新视频不会立即加入 Faiss

They are temporarily covered by the recent-unindexed search and added by the hourly updater.  
这些视频会暂时由近期未索引搜索覆盖，并由每小时更新任务添加到 Faiss。

### Multiple reviews can affect one episode｜多个 Review 可能影响同一个 Episode

One episode can have several reviews across `env`, `left`, and `right`.  
一个 Episode 可以在 `env`、`left` 和 `right` 上存在多个 Review。

The long-term rule should be:  
长期规则应为：

- If any review is marked duplicate, keep the episode failed.  
  如果任意 Review 被标记为重复，则保持 Episode 为失败状态。
- Restore the episode only when no approved duplicate review remains.  
  只有在不存在任何已批准的重复 Review 时，才恢复 Episode。

The current review actions are handled individually, so conflicting Admin decisions should be monitored.  
当前各个 Review Action 是独立处理的，因此应监控相互冲突的 Admin 决定。

## 7. Future Scaling｜未来扩展

The current Faiss type is BinaryFlat.  
当前 Faiss 类型为 BinaryFlat。

It is simple and provides exact search, but its work grows with the number of historical frame hashes inside each task and slot.  
它结构简单并提供精确搜索，但计算量会随着每个 Task 和 Slot 中历史帧 Hash 数量的增加而增长。

Consider BinaryIVF later if:  
如果出现以下情况，可以考虑改用 BinaryIVF：

- Candidate search becomes noticeably slow.  
  候选搜索速度明显变慢。
- A single task and slot reaches millions of frame hashes.  
  单个 Task 和 Slot 达到数百万帧 Hash。
- Index files become too large for Worker memory.  
  索引文件过大，超出 Worker 内存承载能力。
- The hourly updater cannot finish within one hour.  
  每小时更新任务无法在一小时内完成。

There is no need to migrate yet.  
目前尚不需要迁移。

## 8. Features Not Currently Implemented｜当前尚未实现的功能

- SHA256 duplicate checking.  
  SHA256 重复检查。
- Hidden video or MCAP watermarking.  
  隐藏式 Video 或 MCAP 水印。
- Cross-task vPDQ detection.  
  跨 Task 的 vPDQ 检测。
- Faiss BinaryIVF or HNSW.  
  Faiss BinaryIVF 或 HNSW。
- Automatic rejection based only on vPDQ.  
  仅根据 vPDQ 结果自动拒绝上传。
- Creating Admin Reviews for old duplicates during backfill.  
  在 Backfill 过程中为旧重复数据创建 Admin Review。

## 9. Key Logs｜关键日志

### Fingerprint creation｜指纹创建

```text
vpdq_hash_done
vpdq_artifact_written
```

### Faiss search｜Faiss 搜索

```text
vpdq_frame_index_loaded
vpdq_flat_candidates
```

### Detailed comparison｜详细比较

```text
vpdq_candidate_compared
vpdq_reviews_selected
video_duplicate_review_created
```

### Index maintenance｜索引维护

```text
vpdq_index_update_done
vpdq_index_update_noop
vpdq_index_published
```

### Errors｜错误

```text
vpdq_candidate_artifact_missing
vpdq_frame_index_load_failed
vpdq_source_sync_failed
```

## 10. Current Status｜当前状态

As of July 21, 2026:  
截至 2026 年 7 月 21 日：

- Historical vPDQ backfill is mostly complete.  
  历史 vPDQ Backfill 已基本完成。
- Small historical gaps are accepted.  
  少量历史数据缺口可以接受。
- Full Faiss indexes have been built.  
  Faiss 全量索引已构建完成。
- The Worker uses Faiss BinaryFlat.  
  Worker 使用 Faiss BinaryFlat。
- Exact duplicate detection has been verified.  
  精确重复检测已经验证。
- Admin Review creation has been verified.  
  Admin Review 创建流程已经验证。
- Admin decisions have been verified.  
  Admin 审核决定已经验证。
- The hourly incremental updater has been verified.  
  每小时增量更新任务已经验证。
- Cloud Scheduler execution has been verified.  
  Cloud Scheduler 执行已经验证。
- Normal uploads can continue without pausing.  
  正常上传可以继续，无需暂停。

## 11. Code Verification Notes (2026-07-23)｜代码核对记录（2026-07-23）

> Verified against `app-prismax-rp-backend` (`testing`, HEAD `7faf09e6f20ed16a569c6a259890d0f848639988`) and `app-prismax-rp` (`testing`, HEAD `e22922a084c216111be7a6fde03398fba64778a6`) source code only. No deployment console / runtime environment variables were inspected.  
> 仅核对 `app-prismax-rp-backend`（`testing` 分支，HEAD `7faf09e6f20ed16a569c6a259890d0f848639988`）与 `app-prismax-rp`（`testing` 分支，HEAD `e22922a084c216111be7a6fde03398fba64778a6`）的源代码，未查看部署控制台/运行时环境变量。

### 11.1 Open question: is Faiss BinaryFlat actually active？｜待确认：Faiss BinaryFlat 是否真的生效

This document states "Current search engine: Faiss BinaryFlat" as a fact. The code shows this is controlled by an environment variable whose **default is `legacy`, not `flat`**:  
本文档开头把"Current search engine: Faiss BinaryFlat"作为既定事实描述。但代码显示这是由一个环境变量控制的，其**默认值是 `legacy`，不是 `flat`**：

```57:57:app-prismax-rp-backend/app_prismax_data_worker/worker.py
VPDQ_CANDIDATE_MODE = os.getenv('VPDQ_CANDIDATE_MODE', 'legacy').strip().lower()
```

```1213:1222:app-prismax-rp-backend/app_prismax_data_worker/worker.py
            if VPDQ_CANDIDATE_MODE == "flat":
                candidate_rows = _find_flat_vpdq_candidate_metadata(
                    conn,
                    storage_client,
                    source_row,
                    source_artifact,
                )
            else:
                candidate_rows = _find_vpdq_candidate_metadata(conn, source_row)
```

`cloudbuild.yaml` deploys the `app-prismax-data-worker` Cloud Run service without setting `VPDQ_CANDIDATE_MODE` (or any other VPDQ env var) at all, unlike e.g. the Forum service which explicitly passes `--set-env-vars`:  
`cloudbuild.yaml` 在部署 `app-prismax-data-worker` 这个 Cloud Run 服务时，完全没有设置 `VPDQ_CANDIDATE_MODE`（或任何其他 VPDQ 相关环境变量），而同一文件里 Forum 服务的部署步骤是有显式 `--set-env-vars` 的：

```140:148:app-prismax-rp-backend/cloudbuild.yaml
- name: 'gcr.io/cloud-builders/gcloud'
  args:
    - run
    - deploy
    - ${_DATA_WORKER_SERVICE}
    - --image=gcr.io/thepinai/app-prismax-data-worker:$COMMIT_SHA
    - --platform=managed
    - --region=${_REGION}
    - --allow-unauthenticated
```

A full repo-wide search for `VPDQ_CANDIDATE_MODE`, `cloudbuild`, `.env*`, Terraform, and shell deploy scripts found no place that sets this variable to `flat`.  
在整个仓库范围内搜索 `VPDQ_CANDIDATE_MODE`、`cloudbuild`、`.env*`、Terraform 及部署脚本，均未找到任何把该变量设为 `flat` 的地方。

**Conclusion**: this cannot be confirmed or denied from source code alone — the variable may be set manually in the Cloud Run service configuration outside this repo. **This should be verified directly against the deployed `app-prismax-data-worker` service's environment variables before relying on this document's Step 4/5 description.**  
**结论**：仅凭源代码无法确认或排除这一点——该变量有可能是在本仓库之外、通过 GCP Console 或其他方式手动配置在 Cloud Run 服务上的。**在依赖本文档 Step 4/5 的描述之前，应直接核实已部署的 `app-prismax-data-worker` 服务的环境变量实际取值。**

If `VPDQ_CANDIDATE_MODE` is actually `legacy` in production, the following parts of this document do not reflect the active code path:  
如果生产环境实际是 `legacy` 模式，本文档以下内容与当前生效的代码路径不符：

| Section｜章节 | Doc says｜文档描述 | Actual behavior under `legacy`｜`legacy` 模式下的实际行为 |
| --- | --- | --- |
| Step 4: Faiss candidate search｜步骤 4 | Faiss narrows candidates to the best matches, keeping `20` indexed video candidates after grouping.<br>Faiss 缩小候选范围，分组后保留 20 个候选视频。 | `_find_vpdq_candidate_metadata` returns **every** matching historical video for the task+slot with no `20`-candidate cap; there is no frame-level pre-filtering.<br>`_find_vpdq_candidate_metadata` 会返回该 task+slot 下**全部**符合条件的历史视频，没有 20 个候选的上限，也没有帧级预筛选。 |
| Step 5: Check recently uploaded videos｜步骤 5 | A separate "recent unindexed" scan (up to `200` candidates) is needed to catch videos not yet in the Faiss index.<br>需要单独扫描最多 200 个"近期未索引"视频，以避免漏检尚未进入 Faiss 索引的视频。 | Not applicable — `legacy` mode queries the database directly every time, so there is no index staleness and nothing to separately "catch up" on.<br>不适用——`legacy` 模式每次都直接查库，不存在索引，因此也不存在"索引滞后需要额外补漏"的问题。 |
| §6 "New videos are not immediately added to Faiss"｜第 6 节"新视频不会立即加入 Faiss" | Listed as a current limitation.<br>被列为当前限制。 | Not a limitation under `legacy` mode, since no index is involved.<br>在 `legacy` 模式下不构成限制，因为压根不涉及索引。 |
| §4 Index Maintenance (hourly updater, Cloud Scheduler)｜第 4 节索引维护（每小时更新任务、Cloud Scheduler） | Presented as actively relied upon by the detection flow.<br>被描述为检测流程实际依赖的组件。 | Irrelevant to detection results under `legacy` mode — the updater could fail or stop entirely and Layer 2 detection would be unaffected.<br>在 `legacy` 模式下与检测结果无关——即便该更新任务失败或完全停止，Layer 2 检测也不受影响。 |

### 11.2 Everything else checked matches the code｜其余核对项均与代码一致

The following items were verified line-by-line against `worker.py`, `video_duplicate_review_helper.py`, `vpdq_frame_index_helper.py`, `backfill_video_vpdq.py`, and `app_prismax_data_pipeline/app.py`, and match this document exactly:  
以下内容已逐行对照 `worker.py`、`video_duplicate_review_helper.py`、`vpdq_frame_index_helper.py`、`backfill_video_vpdq.py` 和 `app_prismax_data_pipeline/app.py` 核实，均与本文档描述完全一致：

- Step 1 file-size check: dimensions (MCAP size + total video size), Task 12 skip, no SHA256, cross task/machine/user search.  
  步骤 1 文件大小检查：判定维度（MCAP 大小 + 视频总大小）、Task 12 跳过、不使用 SHA256、跨 Task/Machine/User 搜索。
- Step 2 fingerprint generation: env/left/right slots, ~1 fps sampling, 256-bit hash, GCS artifact path format.  
  步骤 2 指纹生成：env/left/right 三个 Slot、约 1 帧/秒采样、256-bit Hash、GCS Artifact 路径格式。
- Step 3 base candidate filters: same `task_id`, same `video_slot`, historical status `DERIVED_READY`, older `metadata_id`, `machine_id` not used as a filter.  
  步骤 3 基础候选过滤条件：同 `task_id`、同 `video_slot`、历史状态 `DERIVED_READY`、`metadata_id` 更早、`machine_id` 不作为过滤条件。
- Step 6 comparison metrics and OR-based review threshold logic (`score` ≥ 35%, `shorter_coverage` ≥ 40%, `longest_run` ≥ 10s), and the "best 3 review candidates per source video" cap.  
  步骤 6 比对指标与 OR 逻辑送审阈值（`score` ≥ 35%、`shorter_coverage` ≥ 40%、`longest_run` ≥ 10 秒），以及"每个 Source Video 最多 3 个审核候选"的上限。
- Step 7 Admin review side effects: `Mark duplicate` fails only the source episode (matched episode untouched); `Not a duplicate` restores the episode to `DERIVED_READY` only if the current failure was caused by that exact review.  
  步骤 7 Admin 审核副作用：`Mark duplicate` 只会让 Source Episode 失败（Matched Episode 不受影响）；`Not a duplicate` 仅在当前失败正是由该条 Review 造成时才会恢复为 `DERIVED_READY`。
- All numeric defaults in §3 Key Settings (`45`, `31`, `50`, `20`, `200`, `35%`, `40%`, `10s`, `3`, `vpdq-v1`) match the corresponding environment variable defaults in `worker.py`.  
  第 3 节"关键配置"里的全部数值默认值（`45`、`31`、`50`、`20`、`200`、`35%`、`40%`、`10 秒`、`3`、`vpdq-v1`）均与 `worker.py` 中对应环境变量的默认值一致。
- §6 "Multiple reviews can affect one episode" is an accurate, self-acknowledged description of the current single-review restore check (`duplicate_review_id` match only), not a discrepancy.  
  第 6 节"多个 Review 可能影响同一个 Episode"如实描述了当前恢复逻辑只检查单条 `duplicate_review_id` 是否匹配这一已知局限，与代码一致，不构成出入。
- §8 "Features Not Currently Implemented": confirmed no SHA256 check, no cross-task vPDQ search, no BinaryIVF/HNSW index type (only `IndexBinaryFlat` exists in `vpdq_frame_index_helper.py`), no auto-rejection from vPDQ alone, and `backfill_video_vpdq.py` does not call `record_video_duplicate_review` (no Admin Reviews created during backfill).  
  第 8 节"当前尚未实现的功能"：确认未实现 SHA256 检查、跨 Task vPDQ 搜索、BinaryIVF/HNSW 索引类型（`vpdq_frame_index_helper.py` 中只有 `IndexBinaryFlat`）、仅凭 vPDQ 自动拒绝，以及 `backfill_video_vpdq.py` 确实不会调用 `record_video_duplicate_review`（Backfill 过程不会创建 Admin Review）。

### 11.3 Not verifiable from source code｜无法从源代码验证

The following items are GCP infrastructure configuration (Cloud Run Job names, Cloud Scheduler cron expression) that are not committed to either repository, so they could not be confirmed or refuted from code:  
以下内容属于 GCP 基础设施配置（Cloud Run Job 名称、Cloud Scheduler cron 表达式），并未提交到任一代码仓库，因此无法通过代码确认或证伪：

- Cloud Run Job names `prismax-vpdq-index-build` / `prismax-vpdq-index-update`.  
  Cloud Run Job 名称 `prismax-vpdq-index-build` / `prismax-vpdq-index-update`。
- Cloud Scheduler job `prismax-vpdq-index-update-hourly` and its `15 * * * *` cron schedule.  
  Cloud Scheduler 任务 `prismax-vpdq-index-update-hourly` 及其 `15 * * * *` cron 调度表达式。
- §10 "Current Status" runtime claims (backfill completion, index build completion, verified executions).  
  第 10 节"当前状态"中的运行时结论（Backfill 完成度、索引构建完成度、各项验证是否已执行）。

Only `deploy_vpdq_backfill_job.sh` (for the one-off backfill job, not the index build/update jobs) exists in the repo.  
仓库里只存在 `deploy_vpdq_backfill_job.sh`（对应一次性 Backfill 任务，并非索引构建/更新任务）。
