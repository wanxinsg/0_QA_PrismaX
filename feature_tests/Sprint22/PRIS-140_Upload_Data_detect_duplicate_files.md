# PRIS-140 Upload Data：Admin Detect Duplicate Files 前后端逻辑分析

> 分析日期：2026-07-23
> 前端仓库：`app-prismax-rp`，本地分支 `testing`，HEAD `e22922a084c216111be7a6fde03398fba64778a6`
> 后端仓库：`app-prismax-rp-backend`，本地分支 `testing`，HEAD `7faf09e6f20ed16a569c6a259890d0f848639988`
> 数据来源：仅阅读并核对当前两个仓库的最终代码实现（未参考仓库内其他 QA/PRD md 文档，未执行远端拉取、未连接测试数据库）

## 1. 功能概述

"Detect Duplicate Files" 不是用户上传时一次性触发的单一检测，而是数据处理管线（Worker）中**自动运行的两层重复检测机制**，外加一个供人工复核的 Admin 页面：

| 层级 | 检测点 | 判定维度 | 触发时机 | 结果 |
| --- | --- | --- | --- | --- |
| **Layer 1：尺寸级阻断** | Worker 处理 `_MANIFEST.json`，MCAP 校验之后、Episode 标记为已上传之前 | 该 Episode 的 `.mcap` 文件大小 + 该 Episode 下**全部** `.mp4` 文件大小之和，与库中任一 `DERIVED_READY` Episode 完全相等 | 每次上传的 manifest 落地后，Worker 自动执行 | 立即判定重复，Episode 直接置为 `DERIVED_VALIDATION_FAILED`，**不再继续**派生/视频处理 |
| **Layer 2：vPDQ 感知哈希（近似重复，人工复核）** | Episode 完成派生并置为 `DERIVED_READY` **之后** | 同 `task_id` + 同 `video_slot` 的历史 `DERIVED_READY` Episode 视频，用 vPDQ 帧哈希做时间对齐相似度比对 | Episode 派生完成后自动比对；一旦超过阈值，写入待审核记录（不阻断） | Episode 状态**保持** `DERIVED_READY`；仅当 Admin 在「Video Duplicates」页面手动标记 **Mark duplicate** 后，才会把该 Episode 置为 `DERIVED_VALIDATION_FAILED` |

Admin 侧涉及的入口：

- **Admin Portal →「Video Duplicates」页签**：Layer 2 的人工复核界面（本次分析的核心）。
- **Admin Portal →「Data Download」页签（`RoboticDataAdmin`）**：Failed Only 视图中把 Layer 1/Layer 2 造成的失败统一显示为 **"Duplication"**。
- **Admin Portal →「Dataset Stats」页签（`DatasetStatsAdmin`）**：失败原因分布图中把同样的失败统一显示为 **"Duplicate video"**。

需要特别说明：前端上传页面 `Upload.js` 中「Skipped N duplicate paths」提示，只是**同一次文件选择内、按相对路径去重**的客户端逻辑（例如用户在文件夹选择器里重复选中同一文件两次），与本报告分析的服务端重复文件检测（Layer 1/Layer 2）没有任何关系，见第 3.5 节。

两层检测都不提供"覆盖上传"（overwrite）交互——一旦判定为重复，只能是失败/待人工复核，没有允许用户强制覆盖已有数据的路径。

## 2. 后端实现（`app-prismax-rp-backend`）

### 2.1 Layer 1：MCAP + 视频总大小精确匹配

文件：`app_prismax_data_worker/worker.py`

常量定义：

```47:47:app-prismax-rp-backend/app_prismax_data_worker/worker.py
DUPLICATE_SIZE_SKIP_TASK_ID = 12
```

核心判重函数——**不使用文件名、不使用文件内容哈希（如 SHA256/MD5），只比较两个数值**：

```1439:1469:app-prismax-rp-backend/app_prismax_data_worker/worker.py
def _find_existing_duplicate_files(conn, upload_id: int, raw_folder: str, mcap_size, video_size):
    if mcap_size is None or video_size is None:
        return None

    mcap_size = int(mcap_size or 0)
    video_size = int(video_size or 0)
    if mcap_size <= 0 or video_size <= 0:
        return None

    stmt = sqlalchemy.text("""
        SELECT
            e.episode_id,
            e.upload_id,
            e.status,
            e.mcap_size_bytes,
            e.video_size_bytes
        FROM data_episodes e
        WHERE e.mcap_size_bytes = :mcap_size
          AND e.video_size_bytes = :video_size
          AND UPPER(COALESCE(e.status, '')) = 'DERIVED_READY'
          AND NOT (e.upload_id = :upload_id AND e.raw_video_folder_path = :raw_folder)
        ORDER BY e.episode_id DESC
        LIMIT 1
    """)
```

判定逻辑要点：

- **判定维度**：`mcap_size_bytes`（单个 `.mcap` 文件大小）+ `video_size_bytes`（该 Episode 下**所有** `.mp4` 文件大小之**和**，不是逐个视频比较）。两者必须与数据库中已有的某个 `DERIVED_READY` Episode**完全相等**才判定为重复。
- `total_video_size` 和 `mcap_size` 的计算来源（同一函数内，Step 2 遍历 GCS blob）：

```1543:1577:app-prismax-rp-backend/app_prismax_data_worker/worker.py
    size_mismatch = []
    invalid_video_paths = []
    total_video_size = 0
    mcap_size = None
    api_file_metadata_rows = []
    ...
        if rel_path.endswith('.mp4'):
            total_video_size += blob.size or 0
            ...
        if rel_path.endswith('.mcap') and mcap_size is None:
            mcap_size = blob.size
```

- **搜索范围是全局的**：不限定同一 `task_id`、同一用户或同一机器，只要曾经成功派生（`DERIVED_READY`）的任意 Episode 大小相同即命中；按 `episode_id DESC` 取最近一条。
- **排除自身重跑**：`NOT (upload_id = 当前 AND raw_video_folder_path = 当前)`，避免同一个 Episode 重新处理时把自己判成重复。
- **跳过条件**：
  - `mcap_size` 或 `video_size` 为 `None`，或转换后 `<= 0`，直接不判定（`return None`）。
  - `task_id == 12` 时，整个 Layer 1 判重逻辑被跳过（测试任务专用豁免，见下方调用处 `if int(task_id or 0) != DUPLICATE_SIZE_SKIP_TASK_ID`）。

调用处与失败记录：

```1677:1707:app-prismax-rp-backend/app_prismax_data_worker/worker.py
        task_id = upload_row._mapping.get('task_id')
        machine_id = upload_row._mapping.get('machine_id')
        product_name = upload_row._mapping.get('product_name')
        if int(task_id or 0) != DUPLICATE_SIZE_SKIP_TASK_ID:
            duplicate_match = _find_existing_duplicate_files(
                conn,
                upload_id=upload_id,
                raw_folder=raw_folder,
                mcap_size=mcap_size,
                video_size=total_video_size,
            )
            if duplicate_match:
                payload = _record_episode_processing_error(
                    conn,
                    upload_id=upload_id,
                    raw_folder=raw_folder,
                    step="duplicate_file_validation",
                    error_message="duplicate files",
                    status=VALIDATION_FAILED_STATUS,
                    details={
                        "episode_key": episode_key,
                        "mcap_size_bytes": int(mcap_size or 0),
                        "video_size_bytes": int(total_video_size or 0),
                        "matched_episode_id": duplicate_match.get("episode_id"),
                        "matched_upload_id": duplicate_match.get("upload_id"),
                        "matched_status": duplicate_match.get("status"),
                        "validation_error_code": "duplicate_files",
                    },
                )
                _update_upload_status(conn, upload_id)
                return {"ok": False, "status": VALIDATION_FAILED_STATUS, "error": "duplicate files", "validation": payload}, 200
```

Layer 1 命中重复后：

- Episode `status` → `DERIVED_VALIDATION_FAILED`（`VALIDATION_FAILED_STATUS`）。
- `processing_error.step = "duplicate_file_validation"`，`error_message = "duplicate files"`。
- `details.validation_error_code = "duplicate_files"`，并记录命中的 `matched_episode_id` / `matched_upload_id` / `matched_status`。
- 调用 `_update_upload_status(conn, upload_id)` 汇总更新 `data_uploads.status`。
- Worker 对该 manifest 的处理**在此提前 return，不再执行**后续 MCAP 深度校验、视频派生、水印、vPDQ 等步骤（Layer 1 判重发生在管线较早阶段）。
- **Layer 1 不会写入 `data_video_duplicate_reviews` 表**，因此这类失败不会出现在 Admin「Video Duplicates」页面，也没有 decision 接口可以恢复；只能通过重新上传解决。

### 2.2 Layer 2：vPDQ 感知哈希近似重复检测（生成待人工复核记录）

文件：`app_prismax_data_worker/worker.py`（主逻辑）+ `app_prismax_data_worker/video_duplicate_review_helper.py`（写库辅助）+ `vpdq_artifact_helper.py` / `vpdq_frame_index_helper.py`（哈希产物存取）

#### 2.2.1 触发时机

Episode 派生完成、写入 file metadata 并把状态置为 `DERIVED_READY` **之后**，Worker 才计算/比对 vPDQ 哈希（非阻断步骤，即便比对失败也不影响 Episode 已经 READY 的状态）：

```1858:1866:app-prismax-rp-backend/app_prismax_data_worker/worker.py
                        "vPDQ hash failed for upload=%s episode=%s path=%s; continuing without duplicate review for this video",
```

```2100:2110:app-prismax-rp-backend/app_prismax_data_worker/worker.py
        "Failed syncing vPDQ duplicate reviews for upload=%s episode=%s episode_id=%s",
    ...
        "[worker][step 6/7] upload=%s episode=%s vpdq duplicate review summary=%s",
```

#### 2.2.2 可配置阈值（环境变量，均有默认值）

```49:70:app-prismax-rp-backend/app_prismax_data_worker/worker.py
VPDQ_HASH_BUCKET = os.getenv('VPDQ_HASH_BUCKET') or DATA_DERIVED_BUCKET
VPDQ_HASH_PREFIX = os.getenv('VPDQ_HASH_PREFIX', 'duplicate-detection/vpdq')
VPDQ_SECONDS_PER_HASH = float(os.getenv('VPDQ_SECONDS_PER_HASH', '1.0'))
VPDQ_DISTANCE_THRESHOLD = int(os.getenv('VPDQ_DISTANCE_THRESHOLD', '31'))
VPDQ_OFFSET_BUCKET_SECONDS = float(os.getenv('VPDQ_OFFSET_BUCKET_SECONDS', '1.0'))
VPDQ_REVIEW_SCORE_THRESHOLD = float(os.getenv('VPDQ_REVIEW_SCORE_THRESHOLD', '35'))
VPDQ_REVIEW_SHORTER_COVERAGE_THRESHOLD = float(os.getenv('VPDQ_REVIEW_SHORTER_COVERAGE_THRESHOLD', '40'))
VPDQ_REVIEW_CONTIGUOUS_SECONDS_THRESHOLD = float(os.getenv('VPDQ_REVIEW_CONTIGUOUS_SECONDS_THRESHOLD', '10'))
VPDQ_ALGORITHM_VERSION = os.getenv('VPDQ_ALGORITHM_VERSION', 'vpdq-v1')
VPDQ_CANDIDATE_MODE = os.getenv('VPDQ_CANDIDATE_MODE', 'legacy').strip().lower()
VPDQ_INDEX_BUCKET = os.getenv('VPDQ_INDEX_BUCKET') or VPDQ_HASH_BUCKET
VPDQ_INDEX_PREFIX = os.getenv('VPDQ_INDEX_PREFIX', 'duplicate-detection/vpdq-index')
VPDQ_CANDIDATE_DISTANCE_THRESHOLD = int(os.getenv('VPDQ_CANDIDATE_DISTANCE_THRESHOLD', '45'))
VPDQ_FRAME_TOP_K = int(os.getenv('VPDQ_FRAME_TOP_K', '50'))
VPDQ_VIDEO_CANDIDATE_LIMIT = int(os.getenv('VPDQ_VIDEO_CANDIDATE_LIMIT', '20'))
VPDQ_REVIEW_LIMIT_PER_SLOT = int(os.getenv('VPDQ_REVIEW_LIMIT_PER_SLOT', '3'))
```

| 变量 | 默认值 | 含义 |
| --- | --- | --- |
| `VPDQ_DISTANCE_THRESHOLD` | 31 | 单帧哈希 Hamming 距离 ≤ 该值才视为"该帧匹配" |
| `VPDQ_OFFSET_BUCKET_SECONDS` | 1.0 | 计算两视频时间偏移量时的分桶粒度（秒） |
| `VPDQ_REVIEW_SCORE_THRESHOLD` | 35 | `score`（见 2.2.4）≥ 该值即视为可疑 |
| `VPDQ_REVIEW_SHORTER_COVERAGE_THRESHOLD` | 40 | 两个视频里较短者的整体覆盖率(%) ≥ 该值即视为可疑 |
| `VPDQ_REVIEW_CONTIGUOUS_SECONDS_THRESHOLD` | 10 | 最长连续匹配时长(秒) ≥ 该值即视为可疑 |
| `VPDQ_REVIEW_LIMIT_PER_SLOT` | 3 | 每个 source 视频最多生成的待审记录数（Top N） |
| `VPDQ_CANDIDATE_MODE` | `legacy` | 候选查询模式：`legacy`（SQL 直查同 task+slot）或 `flat`（Faiss 帧级索引） |
| `VPDQ_CANDIDATE_DISTANCE_THRESHOLD` | 45 | 仅 `flat` 模式下，帧级粗筛的距离阈值 |

#### 2.2.3 候选范围（legacy 模式）

```916:967:app-prismax-rp-backend/app_prismax_data_worker/worker.py
def _find_vpdq_candidate_metadata(
    conn,
    source_row,
    *,
    candidate_metadata_ids=None,
    limit=None,
):
    filters = [
        "m.file_kind = 'video'",
        "m.video_slot = :video_slot",
        "e.task_id = :task_id",
        "e.status = 'DERIVED_READY'",
        "m.metadata_id < :metadata_id",
        "m.episode_id <> :episode_id",
    ]
```

即候选视频必须满足：**同一 `task_id`** + **同一 `video_slot`**（`env`/`left`/`right`）+ 状态为 `DERIVED_READY` + `metadata_id` 小于当前视频（即比当前视频更早入库）+ 不是同一个 Episode。**不做跨 task 的全局搜索**，也不比较不同 slot 的视频。

#### 2.2.4 相似度比对算法

```791:882:app-prismax-rp-backend/app_prismax_data_worker/worker.py
def _compare_vpdq_artifacts(source_artifact, candidate_artifact):
    ...
    buckets = {}
    for source_index, source_feature in enumerate(source_features):
        source_ts = float(source_feature.get("timestamp") or 0.0)
        source_hex = source_feature.get("hex")
        for candidate_index, candidate_feature in enumerate(candidate_features):
            distance = _hex_hamming_distance(source_hex, candidate_feature.get("hex"))
            if distance > VPDQ_DISTANCE_THRESHOLD:
                continue
            candidate_ts = float(candidate_feature.get("timestamp") or 0.0)
            bucket = round((source_ts - candidate_ts) / VPDQ_OFFSET_BUCKET_SECONDS) * VPDQ_OFFSET_BUCKET_SECONDS
            ...
    return {
        "score": best_shorter_coverage,
        "source_coverage": source_coverage,
        "candidate_coverage": candidate_coverage,
        "shorter_side": shorter_side,
        "shorter_coverage_pct": shorter_coverage_pct,
        "symmetric_min_coverage_pct": min(source_coverage["coverage_pct"], candidate_coverage["coverage_pct"]),
        "temporal_alignment": temporal_alignment,
    }
```

算法要点：

1. 每秒对视频取一帧（`VPDQ_SECONDS_PER_HASH=1.0`）计算 vPDQ 感知哈希。
2. 逐帧两两比较两个视频的哈希 Hamming 距离，距离 ≤ `VPDQ_DISTANCE_THRESHOLD` 的帧对视为"匹配帧对"。
3. 把匹配帧对按"时间偏移量"（source 时间戳 − candidate 时间戳，按 `VPDQ_OFFSET_BUCKET_SECONDS` 取整分桶）分组，找出匹配帧数最多、平均距离最小的那个"最佳偏移量"分桶（即假设两段视频是同一段录制但整体有一个固定时间平移）。
4. `score`（前端显示为 "Similarity %"）= 在最佳偏移量下，**两个视频中较短者**被匹配帧覆盖的百分比（`best_shorter_coverage`）。
5. 同时计算该偏移量下最长连续匹配时长（`longest_contiguous_run`），用于判断是否存在一段连续雷同的片段。

可疑判定（三个条件满足其一即可，非全部满足）：

```884:891:app-prismax-rp-backend/app_prismax_data_worker/worker.py
def _is_vpdq_suspicious(comparison):
    temporal = comparison.get("temporal_alignment") or {}
    longest_run = temporal.get("longest_contiguous_run") or {}
    return (
        float(comparison.get("score") or 0) >= VPDQ_REVIEW_SCORE_THRESHOLD
        or float(comparison.get("shorter_coverage_pct") or 0) >= VPDQ_REVIEW_SHORTER_COVERAGE_THRESHOLD
        or float(longest_run.get("duration_seconds") or 0) >= VPDQ_REVIEW_CONTIGUOUS_SECONDS_THRESHOLD
    )
```

#### 2.2.5 挑选 Top N 并写入待审核记录

`_sync_episode_vpdq_reviews`（`worker.py:1185-1344`）遍历当前 Episode 每个视频 slot 的 source，对其所有候选逐一比对，收集"可疑"候选，再用 helper 排序取前 `VPDQ_REVIEW_LIMIT_PER_SLOT`（默认 3）个：

```1275:1330:app-prismax-rp-backend/app_prismax_data_worker/worker.py
            if not can_write_reviews:
                if suspicious_candidates:
                    logging.warning(...)
                continue

            selected_reviews = select_top_review_candidates(suspicious_candidates, VPDQ_REVIEW_LIMIT_PER_SLOT)
            ...
            for selected in selected_reviews:
                candidate_row = selected["candidate_row"]
                comparison = selected["comparison"]
                match_details = {
                    "algorithm": "vpdq",
                    "algorithm_version": VPDQ_ALGORITHM_VERSION,
                    ...
                    "scores": comparison,
                }
                review_id = record_video_duplicate_review(
                    conn,
                    source_episode_id=source_row.get("episode_id"),
                    source_video_metadata_id=source_row.get("metadata_id"),
                    matched_episode_id=candidate_row.get("episode_id"),
                    matched_video_metadata_id=candidate_row.get("metadata_id"),
                    task_id=source_row.get("task_id"),
                    machine_id=source_row.get("machine_id"),
                    video_slot=source_row.get("video_slot"),
                    score=round(float(comparison.get("score") or 0), 3),
                    algorithm_version=VPDQ_ALGORITHM_VERSION,
                    match_details=match_details,
                )
```

排序规则（分数越高、覆盖率越高、连续匹配时长越长、平均距离越小者优先）：

```7:21:app-prismax-rp-backend/app_prismax_data_worker/video_duplicate_review_helper.py
def select_top_review_candidates(candidates, limit=3):
    def sort_key(item):
        comparison = item.get("comparison") or {}
        temporal = comparison.get("temporal_alignment") or {}
        longest_run = temporal.get("longest_contiguous_run") or {}
        mean_distance = temporal.get("best_offset_distance_mean")
        return (
            -float(comparison.get("score") or 0),
            -float(comparison.get("shorter_coverage_pct") or 0),
            -float(longest_run.get("duration_seconds") or 0),
            float(mean_distance) if mean_distance is not None else 256.0,
            -int((item.get("candidate_row") or {}).get("metadata_id") or 0),
        )
    return sorted(candidates or [], key=sort_key)[:max(0, int(limit))]
```

写库函数（`INSERT ... ON CONFLICT DO NOTHING`，防止同一对视频被重复插入待审记录）：

```24:101:app-prismax-rp-backend/app_prismax_data_worker/video_duplicate_review_helper.py
def record_video_duplicate_review(
    conn, *, source_episode_id, source_video_metadata_id, matched_episode_id,
    matched_video_metadata_id, task_id=None, machine_id=None, video_slot=None,
    score=0, algorithm_version="vpdq-v1", match_details=None,
):
    """Create a pending admin review row for a near-duplicate video pair."""
    ...
    if source_video_metadata_id is None or matched_video_metadata_id is None:
        raise ValueError("video duplicate reviews require both metadata IDs")
    if int(source_video_metadata_id) == int(matched_video_metadata_id):
        return None
    ...
    insert_row = conn.execute(sqlalchemy.text("""
        INSERT INTO data_video_duplicate_reviews (...)
        VALUES (..., 'PENDING', CAST(:match_details AS jsonb), NOW())
        ON CONFLICT DO NOTHING
        RETURNING review_id
    """), {...}).fetchone()
```

新记录初始 `status = 'PENDING'`。若因唯一索引冲突（同一对视频、同一算法版本已存在记录）导致插入被跳过，函数会回查已存在的 `review_id` 并返回 `None`（不重复计数，但记录已存在）。

### 2.3 数据库表：`data_video_duplicate_reviews`

迁移文件：`app_prismax_data_pipeline/sql/20260616_data_video_duplicate_reviews.sql`

```1:45:app-prismax-rp-backend/app_prismax_data_pipeline/sql/20260616_data_video_duplicate_reviews.sql
CREATE TABLE IF NOT EXISTS data_video_duplicate_reviews (
    review_id BIGSERIAL PRIMARY KEY,
    source_episode_id BIGINT NOT NULL REFERENCES data_episodes(episode_id) ON DELETE CASCADE,
    source_video_metadata_id BIGINT REFERENCES data_api_episode_file_metadata(metadata_id) ON DELETE SET NULL,
    matched_episode_id BIGINT NOT NULL REFERENCES data_episodes(episode_id) ON DELETE CASCADE,
    matched_video_metadata_id BIGINT REFERENCES data_api_episode_file_metadata(metadata_id) ON DELETE SET NULL,
    task_id BIGINT,
    machine_id TEXT,
    video_slot TEXT,
    score NUMERIC(6, 3) NOT NULL DEFAULT 0,
    algorithm_version TEXT NOT NULL DEFAULT 'vpdq-v1',
    status TEXT NOT NULL DEFAULT 'PENDING',
    match_details JSONB NOT NULL DEFAULT '{}'::jsonb,
    reviewed_by_admin_id BIGINT REFERENCES admin_whitelist(admin_id) ON DELETE SET NULL,
    reviewed_at TIMESTAMPTZ,
    admin_note TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT chk_data_video_duplicate_review_status
        CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'IGNORED')),
    CONSTRAINT chk_data_video_duplicate_review_video_slot
        CHECK (video_slot IS NULL OR video_slot IN ('env', 'left', 'right'))
);

CREATE INDEX IF NOT EXISTS idx_data_video_duplicate_reviews_status_created
    ON data_video_duplicate_reviews (status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_data_video_duplicate_reviews_source_episode
    ON data_video_duplicate_reviews (source_episode_id);
CREATE INDEX IF NOT EXISTS idx_data_video_duplicate_reviews_matched_episode
    ON data_video_duplicate_reviews (matched_episode_id);
CREATE INDEX IF NOT EXISTS idx_data_video_duplicate_reviews_scope
    ON data_video_duplicate_reviews (task_id, video_slot, status);

CREATE UNIQUE INDEX IF NOT EXISTS uq_data_video_duplicate_reviews_pair
    ON data_video_duplicate_reviews (
        LEAST(source_video_metadata_id, matched_video_metadata_id),
        GREATEST(source_video_metadata_id, matched_video_metadata_id),
        algorithm_version
    )
    WHERE source_video_metadata_id IS NOT NULL
      AND matched_video_metadata_id IS NOT NULL;
```

要点：

- `status` 取值枚举为 `PENDING` / `APPROVED` / `REJECTED` / `IGNORED`（数据库 CHECK 约束）；目前后端逻辑只会写入 `PENDING`，Admin decision 接口只会更新为 `APPROVED` 或 `REJECTED`，`IGNORED` 目前代码里没有写入路径。
- 唯一索引以 `(LEAST(source_metadata_id, matched_metadata_id), GREATEST(...), algorithm_version)` 建立，确保同一对视频（不论谁是 source/matched）+ 同一算法版本只会有一条记录。
- `match_details` 保存完整的算法参数与比对分数（JSONB），供 Admin 页面展示与后续排查。
- 关联表：`data_episodes`（`status`、`processing_error`、`mcap_size_bytes`、`video_size_bytes`）、`data_api_episode_file_metadata`（视频文件元数据）、`admin_whitelist`（审核人）。

### 2.4 Admin API（`app_prismax_data_pipeline/app.py`）

统一鉴权（三层校验）：

```566:581:app-prismax-rp-backend/app_prismax_data_pipeline/app.py
def _require_admin_jwt():
    try:
        verify_jwt_in_request()
    except Exception:
        return None, (jsonify({"success": False, "msg": "invalid token"}), 401)

    claims = get_jwt() or {}
    if str(claims.get("role") or "").lower() != "admin":
        return None, (jsonify({"success": False, "msg": "admin access required"}), 403)

    wallet_address = get_jwt_identity()
    admin = _get_admin_by_wallet(wallet_address)
    if not admin:
        return None, (jsonify({"success": False, "msg": "admin access required"}), 403)

    return admin, None
```

即：JWT 必须有效（否则 401）；JWT `role` 必须为 `admin`（否则 403）；JWT identity 对应钱包必须仍在 `admin_whitelist` 中（否则 403）。三个重复检测相关接口全部复用该函数。

#### API 1 — 获取待审 / 全部重复记录列表

```
GET /data/admin/video-duplicate-reviews
```

```1927:1962:app-prismax-rp-backend/app_prismax_data_pipeline/app.py
@app.route('/data/admin/video-duplicate-reviews', methods=['GET'])
def get_admin_video_duplicate_reviews():
    admin, error_response = _require_admin_jwt()
    if error_response:
        return error_response

    try:
        status = _parse_duplicate_review_status(request.args.get("status", "PENDING"))
    except ValueError as exc:
        return jsonify({"success": False, "msg": str(exc)}), 400

    try:
        limit = max(1, min(100, int(request.args.get("limit", 50))))
    ...
    group_by = str(request.args.get("group_by", "review") or "review").strip().lower()
    if group_by not in {"review", "upload"}:
        return jsonify({"success": False, "msg": "group_by must be review or upload"}), 400
    try:
        hide_task_12 = _parse_bool_query_arg("hide_task_12", False)
```

请求参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `status` | `PENDING` | `PENDING` / `APPROVED` / `REJECTED` / `IGNORED` / `ALL`，非法值返回 400 |
| `limit` | 50 | 1–100，超出范围会被 400（不是静默钳制） |
| `offset` | 0 | ≥0 |
| `group_by` | `review` | `review`（按记录）或 `upload`（按上传分组，前端固定用这个） |
| `episode_limit` / `episode_offset` | 100 / 0 | 仅 `group_by=upload` 时用于分页分组内的 Episode |
| `hide_task_12` | false | 只按 **source（当前被检测的上传）** 的 `task_id` 过滤，不看 matched 一侧 |

`hide_task_12` 的过滤条件明确写在 SQL 注释里：

```1963:1966:app-prismax-rp-backend/app_prismax_data_pipeline/app.py
    status_condition = "TRUE" if status == "ALL" else "r.status = :status"
    # Test-data visibility is determined by the upload under review (the source),
    # never by the older matched video or the denormalized review task value.
    test_data_filter = "AND COALESCE(se.task_id, -1) <> 12" if hide_task_12 else ""
```

返回结构（每条记录，`_serialize_duplicate_review_row`）：

```1833:1859:app-prismax-rp-backend/app_prismax_data_pipeline/app.py
def _serialize_duplicate_review_row(row, storage_client):
    ...
    return {
        "review_id": int(row_data["review_id"]),
        "status": row_data.get("status"),
        "score": float(score) if score is not None else 0.0,
        "created_at": row_data.get("created_at"),
        "updated_at": row_data.get("updated_at"),
        "reviewed_at": row_data.get("reviewed_at"),
        "reviewed_by_admin_id": row_data.get("reviewed_by_admin_id"),
        "admin_note": row_data.get("admin_note"),
        "task_id": row_data.get("task_id"),
        "machine_id": row_data.get("machine_id"),
        "video_slot": row_data.get("video_slot"),
        "match_details": raw_details,
        "source": _duplicate_review_video_payload(row_data, "source", storage_client),
        "matched": _duplicate_review_video_payload(row_data, "matched", storage_client),
        "video_url_expires_in_seconds": DOWNLOAD_TTL_SECONDS,
    }
```

其中 `source` / `matched` 各自包含 `episode_id`、`upload_id`、`task_id`、`machine_id`、`product_name`、`scenario`、`episode_status`、`upload_status`、`metadata_id`、`video_slot`、`relative_path`、`size_bytes`、`video_url`（GCS 签名 URL，有效期 `DOWNLOAD_TTL_SECONDS = 7 * 24 * 60 * 60` 秒即 7 天）、`uploader`（`user_id`/`email`/`wallet_address`/`wallet_chain`）。

`pagination` 字段包含 `group_by`、`limit`、`offset`、`has_more`、`total_upload_count`（仅 `group_by=upload`）、`total_review_count`、`next_offset`、`next_episode_offset` 等，用于前端做游标式翻页。

#### API 2 — 用户重复检测排行统计

```
GET /data/admin/video-duplicate-review-user-stats
```

```2207:2287:app-prismax-rp-backend/app_prismax_data_pipeline/app.py
@app.route('/data/admin/video-duplicate-review-user-stats', methods=['GET'])
def get_admin_video_duplicate_review_user_stats():
    ...
    # Attribute duplicate activity to the user's source upload. A test upload
    # must stay hidden even when its matched video belongs to a production task.
    test_data_filter = (
        "AND COALESCE(source_upload.task_id, source_episode.task_id, -1) <> 12"
        if hide_task_12 else ""
    )
    ...
        rows = conn.execute(sqlalchemy.text(f"""
            SELECT source_upload.user_id, ...
                   COUNT(r.review_id) AS duplicate_detection_count,
                   COUNT(DISTINCT source_upload.upload_id) AS affected_upload_count,
                   COUNT(r.review_id) FILTER (WHERE r.status = 'APPROVED') AS confirmed_duplicate_count,
                   COUNT(r.review_id) FILTER (WHERE r.status = 'PENDING') AS pending_review_count,
                   MAX(r.created_at) AS latest_detection_at
            FROM data_video_duplicate_reviews r
            JOIN data_episodes source_episode ON source_episode.episode_id = r.source_episode_id
            JOIN data_uploads source_upload ON source_upload.upload_id = source_episode.upload_id
            LEFT JOIN users u ON u.userid = source_upload.user_id
            ...
            ORDER BY duplicate_detection_count DESC, affected_upload_count DESC, source_upload.user_id DESC
            LIMIT :limit
        """), {"limit": limit}).fetchall()
```

按用户聚合：检测到的重复匹配总数（`duplicate_detection_count`）、涉及的不同上传数（`affected_upload_count`）、已被 Admin 确认为重复的数量（`confirmed_duplicate_count`，即 `status = APPROVED`）、待审数量（`pending_review_count`）。附带钱包地址（按 Solana/Base/Monad/Aptos/Ethereum 优先级取第一个非空地址）。

#### API 3 — Admin 人工决策

```
POST /data/admin/video-duplicate-reviews/<review_id>/decision
```

```2316:2435:app-prismax-rp-backend/app_prismax_data_pipeline/app.py
@app.route('/data/admin/video-duplicate-reviews/<int:review_id>/decision', methods=['POST'])
def update_admin_video_duplicate_review_decision(review_id):
    admin, error_response = _require_admin_jwt()
    if error_response:
        return error_response

    payload = request.get_json(silent=True) or {}
    decision = str(payload.get("decision") or "").strip().upper()
    decision_status_map = {
        "DUPLICATED": "APPROVED", "DUPLICATE": "APPROVED", "APPROVED": "APPROVED",
        "NOT_DUPLICATED": "REJECTED", "NOT_DUPLICATE": "REJECTED", "REJECTED": "REJECTED",
    }
    review_status = decision_status_map.get(decision)
    if review_status is None:
        return jsonify({"success": False, "msg": "decision must be DUPLICATED or NOT_DUPLICATED"}), 400

    note = payload.get("note")
    if note is not None:
        note = str(note).strip()[:2000] or None
    ...
        if review_status == "APPROVED":
            failure_payload = _duplicate_review_failure_payload(review_data, note=note)
            conn.execute(sqlalchemy.text("""
                UPDATE data_episodes
                SET status = 'DERIVED_VALIDATION_FAILED',
                    processing_error = CAST(:processing_error AS jsonb)
                WHERE episode_id = :episode_id
            """), {...})
        elif review_status == "REJECTED":
            ...
            should_restore_episode = (
                str(review_data.get("source_episode_status") or "").upper() == "DERIVED_VALIDATION_FAILED"
                and isinstance(details, dict)
                and details.get("validation_error_code") == "duplicate_files"
                and int(details.get("duplicate_review_id") or 0) == int(review_id)
            )
            if should_restore_episode:
                conn.execute(sqlalchemy.text("""
                    UPDATE data_episodes
                    SET status = 'DERIVED_READY', processing_error = '{}'::jsonb
                    WHERE episode_id = :episode_id
                """), {"episode_id": review_data.get("source_episode_id")})

        _sync_duplicate_review_upload_status(conn, review_data.get("source_upload_id"))
```

请求体：

```json
{ "decision": "DUPLICATED | DUPLICATE | APPROVED | NOT_DUPLICATED | NOT_DUPLICATE | REJECTED", "note": "可选，会被截断到 2000 字符" }
```

行为要点：

- `decision` 非法（不在别名映射表中）返回 400。
- `review_id` 不存在返回 404（`"duplicate review not found"`）。
- 标记为 **DUPLICATED**：该 review 的 `status → APPROVED`；同时把对应的 **source Episode** 置为 `DERIVED_VALIDATION_FAILED`，并写入结构化 `processing_error`（见下方 `_duplicate_review_failure_payload`，包含 `duplicate_review_id`、`duplicate_detection_algorithm: "vpdq"`、`duplicate_score` 等字段）。**注意：只会更新 source Episode，不会影响 matched（更早那个）Episode 的状态**。
- 标记为 **NOT_DUPLICATED**：该 review 的 `status → REJECTED`；**仅当**当前 source Episode 的失败正是由**这一条** review 造成的（`processing_error.details.validation_error_code == "duplicate_files"` 且 `duplicate_review_id == 当前 review_id`）时，才会把 Episode 恢复为 `DERIVED_READY` 并清空 `processing_error`。如果 Episode 因为其他原因失败，或已经被另一条 review 判重，则不会被这次 REJECTED 决策恢复。
- 决策完成后统一调用 `_sync_duplicate_review_upload_status(conn, source_upload_id)` 重新计算并更新 `data_uploads.status`（聚合该 Upload 下所有 Episode 状态）。
- 决策接口是**幂等可重复调用**的——已经是 `APPROVED` 的 review 可以再次被标记 `APPROVED`（会重复执行同样的 UPDATE，`reviewed_at` 会刷新）；前端 UI 通过 `disabled={saving || review.status === 'APPROVED'}` 在按钮层面做了防重复点击，但接口本身没有阻止。

Layer 2 失败写入的 `processing_error` 结构：

```1898:1924:app-prismax-rp-backend/app_prismax_data_pipeline/app.py
def _duplicate_review_failure_payload(review_data, note=None):
    ...
    details = {
        "episode_key": episode_key,
        "mcap_size_bytes": int(review_data.get("source_mcap_size_bytes") or 0),
        "video_size_bytes": int(review_data.get("source_video_size_bytes") or 0),
        "matched_episode_id": review_data.get("matched_episode_id"),
        "matched_upload_id": review_data.get("matched_upload_id"),
        "matched_status": review_data.get("matched_episode_status"),
        "matched_video_metadata_id": review_data.get("matched_video_metadata_id"),
        "source_video_metadata_id": review_data.get("source_video_metadata_id"),
        "duplicate_review_id": review_data.get("review_id"),
        "duplicate_detection_algorithm": "vpdq",
        "duplicate_score": float(review_data.get("score") or 0),
        "validation_error_code": "duplicate_files",
    }
    if note:
        details["admin_note"] = note
    return {
        "step": "duplicate_file_validation",
        "error_message": "duplicate files",
        "recorded_at": datetime.utcnow().isoformat() + "Z",
        "details": details,
    }
```

可以看到 Layer 1 与 Layer 2 写入的 `processing_error.details` 结构基本一致（都含 `validation_error_code: "duplicate_files"`、`matched_episode_id` 等），区别在于 Layer 2 额外带有 `duplicate_review_id` 和 `duplicate_detection_algorithm: "vpdq"`；这也是前端和其他后端接口区分/统一展示两层失败的依据（见 2.5 节）。

`data_uploads.status` 汇总逻辑：

```1862:1895:app-prismax-rp-backend/app_prismax_data_pipeline/app.py
def _sync_duplicate_review_upload_status(conn, upload_id):
    ...
    failure_statuses = {"DERIVED_VALIDATION_FAILED", "FAILED"}
    active_statuses = {"UPLOADED", "DERIVING"}
    status_set = {str(row._mapping.get("status") or "").upper() for row in rows}

    if all(status == "DERIVED_READY" for status in status_set):
        next_status = "DERIVED_READY"
    elif "DERIVED_READY" in status_set and all(status in failure_statuses or status == "DERIVED_READY" for status in status_set):
        next_status = "DERIVED_PARTIALLY_READY"
    elif all(status in failure_statuses for status in status_set):
        next_status = "DERIVED_VALIDATION_FAILED" if "DERIVED_VALIDATION_FAILED" in status_set else "FAILED"
    elif all(status in active_statuses or status in failure_statuses or status == "DERIVED_READY" for status in status_set):
        next_status = "UPLOADED"
    else:
        return
```

### 2.5 与其他 Admin 接口的联动

**Dataset Stats 失败原因标签**（`/data/admin/dataset-stats`）：

```2532:2545:app-prismax-rp-backend/app_prismax_data_pipeline/app.py
def _dataset_stats_failure_label(processing_error):
    payload = processing_error or {}
    ...
    details = payload.get("details") if isinstance(payload.get("details"), dict) else {}
    if details.get("duplicate_review_id") or details.get("matched_episode_id"):
        return "Duplicate video"
    for key in ("failure_label", "reason", "validation_error_code", "error_code"):
        value = details.get(key)
        if value:
            return _dataset_stats_humanize(value)
```

由于 Layer 1 和 Layer 2 的失败 `details` 都包含 `matched_episode_id`（Layer 2 还额外有 `duplicate_review_id`），**两层失败在 Dataset Stats 的 "Failure comments" 分布图里都会被统一归类为 "Duplicate video"**，无法在该图表中区分是 Layer 1 精确尺寸匹配还是 Layer 2 vPDQ 近似匹配导致的失败。

Episode 是否计入"FAIL"由状态决定：

```2563:2569:app-prismax-rp-backend/app_prismax_data_pipeline/app.py
def _dataset_stats_review_status(episode_status):
    status = str(episode_status or "").strip().upper()
    if status == "DERIVED_READY":
        return "PASS"
    if status in {"DERIVED_VALIDATION_FAILED", "FAILED"}:
        return "FAIL"
    return ""
```

## 3. 前端实现（`app-prismax-rp`）

### 3.1 Admin Portal 入口

文件：`src/components/Admin/AdminPortal.js`

```19:20:app-prismax-rp/src/components/Admin/AdminPortal.js
import RoboticDataAdmin from '../RoboticData/RoboticDataAdmin';
import VideoDuplicateReviews from './VideoDuplicateReviews';
```

```92:141:app-prismax-rp/src/components/Admin/AdminPortal.js
                className={`${styles.tabButton} ${activeTab === 'data-download' ? styles.tabButtonActive : ''}`}
                onClick={() => setActiveTab('data-download')}
              >
              ...
                className={`${styles.tabButton} ${activeTab === 'video-duplicates' ? styles.tabButtonActive : ''}`}
                onClick={() => setActiveTab('video-duplicates')}
              >
                Video Duplicates
              </button>
              ...
            ) : activeTab === 'data-download' ? (
              <RoboticDataAdmin adminToken={adminAccessToken} />
            ) : activeTab === 'video-duplicates' ? (
              <VideoDuplicateReviews adminToken={adminAccessToken} />
```

`AdminPortal` 把登录后获取的 `adminAccessToken` 以 props 形式传给子组件，子组件内部统一使用 `Authorization: Bearer <token>` 调用 Admin API。

### 3.2 核心组件：`VideoDuplicateReviews.js`

文件：`src/components/Admin/VideoDuplicateReviews.js`（全文 628 行）+ `VideoDuplicateReviews.module.css`

#### 3.2.1 数据加载：列表接口调用

```174:232:app-prismax-rp/src/components/Admin/VideoDuplicateReviews.js
    const loadReviews = useCallback(async (nextOffset = 0, nextEpisodeOffset = 0) => {
        ...
        try {
            const params = new URLSearchParams({
                admin: 'true',
                status: showReviewed ? 'ALL' : 'PENDING',
                group_by: 'upload',
                hide_task_12: String(hideTask12),
                limit: String(UPLOADS_PER_PAGE),      // 10
                offset: String(nextOffset),
                episode_limit: String(EPISODES_PER_PAGE), // 100
                episode_offset: String(nextEpisodeOffset),
            });
            const response = await fetch(`${PRISMAX_DATA_PIPELINE_URL}/data/admin/video-duplicate-reviews?${params.toString()}`, {
                headers: {Authorization: `Bearer ${adminToken}`},
            });
```

- `UPLOADS_PER_PAGE = 10`、`EPISODES_PER_PAGE = 100`（组件顶部常量）。
- `showReviewed` 状态控制 `status` 参数：默认 `true`（即 "All reviews" 标签页），`false` 时只查 `PENDING`。
- `group_by` 固定传 `upload`，即前端总是按 Upload 分组展示，不使用 `review` 平铺模式。
- 翻页采用**游标式**（`nextOffset` / `nextEpisodeOffset`），`cursorHistory` 数组保存历史游标供"Previous"按钮回退。

#### 3.2.2 用户排行榜接口调用

```239:267:app-prismax-rp/src/components/Admin/VideoDuplicateReviews.js
    const loadUserStats = useCallback(async () => {
        ...
        const response = await fetch(
            `${PRISMAX_DATA_PIPELINE_URL}/data/admin/video-duplicate-review-user-stats?limit=100&admin=true&hide_task_12=${hideTask12UserStats}`,
            {headers: {Authorization: `Bearer ${adminToken}`}},
        );
```

注意排行榜的 "Hide test data" 开关（`hideTask12UserStats`）与上方列表的开关（`hideTask12`）是**两个独立的 state**，互不联动——用户在列表区打开"隐藏测试数据"不会自动影响排行榜的显示，反之亦然。

#### 3.2.3 决策提交

```273:305:app-prismax-rp/src/components/Admin/VideoDuplicateReviews.js
    const updateDecision = useCallback(async (reviewId, decision) => {
        if (!adminToken || !reviewId) return;
        const label = decision === 'DUPLICATED' ? 'duplicated' : 'not duplicated';
        const note = window.prompt(`Optional note for ${label}:`, '');
        if (note === null) return;

        setIsSavingId(reviewId);
        try {
            const response = await fetch(`${PRISMAX_DATA_PIPELINE_URL}/data/admin/video-duplicate-reviews/${reviewId}/decision?admin=true`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json', Authorization: `Bearer ${adminToken}`},
                body: JSON.stringify({decision, note}),
            });
            ...
            showNotification?.(`Review ${reviewId} marked ${label}.`, 'success');
            loadReviews(offset, episodeOffset);
            loadUserStats();
```

要点：

- 点击「Mark duplicate」或「Not a duplicate」会弹出**浏览器原生 `window.prompt`** 让 Admin 填写可选备注（note）；如果用户点击 prompt 的"取消"（`note === null`），则**直接中止**，不会发起请求。如果留空直接确定，会传空字符串 `note: ""`（后端会把空字符串处理为 `None`，见 `str(note).strip()[:2000] or None`）。
- 提交期间用 `isSavingId` 禁用对应卡片的两个按钮，防止重复点击；按钮同时有 `disabled={saving || review.status === 'REJECTED'}`（"Not a duplicate"按钮）和 `disabled={saving || review.status === 'APPROVED'}`（"Mark duplicate"按钮），即已经是该状态的按钮会被禁用，但仍可以点另一个按钮"反悔"改判。
- 决策成功后会同时刷新列表（`loadReviews`）与用户排行榜（`loadUserStats`），并通过 `showNotification` 弹出 toast。
- 失败时通过 `isSessionExpiredError` 判断是否为登录态过期，若是则调用 `handleAdminSessionExpired` 触发统一的重新登录流程。

#### 3.2.4 UI 展示与分组逻辑

- `hasHiddenTaskId` / `visibleReviews`：前端**在拿到接口数据后又做了一次本地过滤**——即便后端 `hide_task_12` 已经在 SQL 层面过滤过，前端仍会按 `review.source.task_id === '12'` 再滤一遍（双重保险，理论上冗余）。

```54:57:app-prismax-rp/src/components/Admin/VideoDuplicateReviews.js
function hasHiddenTaskId(review) {
    const sourceTaskId = review?.source?.task_id ?? review?.task_id;
    return String(sourceTaskId || '').trim() === HIDDEN_TASK_ID;
}
```

- `reviewGroups`：按 `getUploadGroupKey`（优先用 `upload_id`，否则退化为按单条 `review_id` 分组）把同一 Upload 下的多条 review 聚合成一个可展开/收起的卡片。
- 每个 Upload 分组卡片头部展示：Upload ID、场景标签（scenario）、匹配数量、上传者身份（钱包地址截断显示+复制按钮/邮箱/wallet chain 徽章）、该组内**最高相似度分数**、待审数量徽章（`Reviewed` / `N pending`）。
- 展开后，每条 review 展示：创建时间、视频 slot（大写）、相似度分数（`score.toFixed(1)%`）、状态徽章（`decisionDetails`：`APPROVED→Duplicate`绿色、`REJECTED→Not duplicate`红色、其他→`Pending`）、左右两个视频对比面板（Episode ID、Upload ID、Task ID、机器名/ID、scenario、相对路径、"Open video"外链——即签名 URL）、底部两个操作按钮。
- 空状态：`visibleReviews.length === 0` 时显示 "No duplicate reviews found for this filter."。

#### 3.2.5 排行榜表格

展示列：`#`（排名）、User（钱包/邮箱+ID）、Detected matches（`duplicate_detection_count`）、Affected uploads（`affected_upload_count`）、Confirmed（`confirmed_duplicate_count`）、Pending（`pending_review_count`），数字用 `toLocaleString('en-US')` 格式化千分位。

### 3.3 「Data Download」失败列表中的重复标记

文件：`src/components/RoboticData/RoboticDataAdmin.js`

Failed Only 视图解析 `episode.processing_error`，只要 `step`、`validation_error_code` 或 `error_message` 三者之一包含 `"duplicate"` 字样（大小写不敏感），就统一显示为一条 **"Duplication"** 拒绝原因（不展示更细的 Layer 1/Layer 2 区分，也不展示具体 matched episode）：

```108:124:app-prismax-rp/src/components/RoboticData/RoboticDataAdmin.js
function getEpisodeRejectionRows(episode) {
    const processingError = episode?.processing_error || {};
    const details = processingError?.details || {};
    const step = String(processingError?.step || '').trim().toLowerCase();
    const errorMessage = String(processingError?.error_message || '').trim();
    const validationCode = String(details?.validation_error_code || '').trim().toLowerCase();
    if (
        step.includes('duplicate')
        || validationCode.includes('duplicate')
        || errorMessage.toLowerCase().includes('duplicate')
    ) {
        return [{
            key: 'duplication',
            description: 'Duplication',
            detail: '',
        }];
    }
    ...
```

该函数在展示其他失败原因明细时，会显式把 `matched_episode_id` / `matched_upload_id` / `matched_status` / `validation_error_code` 等重复检测相关字段加入"隐藏字段"黑名单（不在通用明细区展示，避免与专门的 "Duplication" 分支重复）：

```163:178:app-prismax-rp/src/components/RoboticData/RoboticDataAdmin.js
    const rawDetails = [];
    const hiddenDetailKeys = new Set([
        'failed_checks', 'failed_check_details', 'failed_episode_id', 'failed_episode_key',
        'validated_at', 'validation_timestamp', 'passed_checks', 'total_checks', 'summary',
        'validation_error_code', 'matched_episode_id', 'matched_upload_id', 'matched_status',
    ]);
```

### 3.4 「Dataset Stats」中的重复占比展示

文件：`src/components/Admin/DatasetStatsAdmin.js`

该组件只是把后端 `/data/admin/dataset-stats` 返回的 `failure_comments`（数组，每项含 `label`/`count`）原样归一化展示为一个失败原因分布表（`normalizeRows`），"Duplicate video" 作为其中一个 `label` 与其他失败原因（如 MCAP 校验失败）并列展示占比：

```119:132:app-prismax-rp/src/components/Admin/DatasetStatsAdmin.js
function normalizeRows(rows, total) {
    return (Array.isArray(rows) ? rows : [])
        .map((row) => {
            const count = toNumber(row?.count ?? row?.episode_count ?? 0);
            return {
                label: sanitizeFailureLabel(row?.label ?? row?.status ?? row?.review_status ?? row?.failure_label ?? ''),
                count,
                percentage: percentOf(count, total),
            };
        })
        .filter((row) => row.label);
}
```

前端没有对 "Duplicate video" 做任何特殊处理（没有专属颜色/点击跳转到 Video Duplicates 页面等），纯粹是后端标签的直接展示。

### 3.5 非 Admin：上传页面的客户端路径去重（易混淆点，需与 Layer 1/2 区分）

文件：`src/components/Data/Upload.js`

```410:441:app-prismax-rp/src/components/Data/Upload.js
    const handlePickedFiles = (fileList) => {
        const seen = new Set();
        const normalized = [];
        let duplicates = 0;

        fileList.forEach((pickedItem) => {
            const file = pickedItem?.file || pickedItem;
            const providedRelativePath = pickedItem?.relativePath;
            const rawPath = providedRelativePath || file.webkitRelativePath || file.name;
            const relativePath = providedRelativePath
                ? rawPath.replace(/\\/g, '/').split('/').filter(Boolean).join('/')
                : normalizeRelativePath(rawPath);
            if (!relativePath || isIgnoredPath(relativePath)) return;
            if (seen.has(relativePath)) {
                duplicates += 1;
                return;
            }
            seen.add(relativePath);
            normalized.push({...});
        });

        setDuplicateCount(duplicates);
        setFiles(normalized);
        ...
```

```1012:1013:app-prismax-rp/src/components/Data/Upload.js
                            {duplicateCount > 0 && (
                                <div className={styles.warning}>Skipped {duplicateCount} duplicate paths.</div>
                            )}
```

这段逻辑只是在用户**一次性选择的文件集合**内，用 `relativePath`（相对路径字符串）做 `Set` 去重，跳过路径完全相同的重复项，纯前端本地处理，**不发起任何网络请求，不比较文件内容或大小，也不查询服务端是否已存在同名/同内容数据**。它与本报告的 Admin 重复检测（Layer 1 尺寸匹配、Layer 2 vPDQ 近似匹配）是完全独立的两套机制，测试时不应混淆。

## 4. 完整数据流程

```
用户在 Upload 页面选择文件
  └─ Upload.js: 客户端按 relativePath 去重（提示 "Skipped N duplicate paths"，与服务端检测无关）
        │
        ▼
上传原始文件到 GCS raw bucket，写入 _MANIFEST.json
        │
        ▼
Worker._process_manifest_object（worker.py）
        │
        ├─ 遍历 GCS blob，累加 total_video_size（全部 .mp4 之和）与 mcap_size（首个 .mcap）
        │
        ├─ 【Layer 1】task_id != 12 时调用 _find_existing_duplicate_files
        │      命中（mcap_size + video_size 与某 DERIVED_READY Episode 完全相等）？
        │        YES → Episode.status = DERIVED_VALIDATION_FAILED
        │              processing_error.step = duplicate_file_validation
        │              validation_error_code = duplicate_files
        │              （不写 data_video_duplicate_reviews，流程提前结束）
        │              → Data Download Failed 视图显示 "Duplication"
        │              → Dataset Stats 失败分布显示 "Duplicate video"
        │        NO  → 继续 MCAP 校验、视频派生、水印等后续步骤
        │
        ▼
Step 6：写入视频 file metadata，计算 vPDQ 哈希 artifact 并上传 GCS
Episode.status = DERIVED_READY（先置为 READY）
        │
        ▼
【Layer 2】_sync_episode_vpdq_reviews（非阻断，异常会被吞掉只记日志）
        同 task_id + 同 video_slot 的历史 DERIVED_READY 视频作为候选
        逐一用 vPDQ 帧哈希做时间对齐比对，计算 score/coverage/最长连续匹配时长
        任一指标超过阈值 → 加入可疑候选 → 按分数排序取 Top 3
        写入 data_video_duplicate_reviews（status = PENDING）
        Episode 仍保持 DERIVED_READY，不受影响
        │
        ▼
Admin 打开 Admin Portal →「Video Duplicates」页签
  GET /data/admin/video-duplicate-reviews?group_by=upload&status=...
  按 Upload 分组展示，左右对比 source / matched 视频（签名 URL 播放）
        │
        ├─ 点击「Mark duplicate」→ POST .../decision {decision: DUPLICATED}
        │     review.status = APPROVED
        │     source Episode.status = DERIVED_VALIDATION_FAILED（写入含 duplicate_review_id 的 processing_error）
        │     → Data Download Failed 视图显示 "Duplication"
        │     → Dataset Stats 失败分布显示 "Duplicate video"
        │
        └─ 点击「Not a duplicate」→ POST .../decision {decision: NOT_DUPLICATED}
              review.status = REJECTED
              仅当该 Episode 当前失败正是由这条 review 造成时，才恢复为 DERIVED_READY
        │
        ▼
_sync_duplicate_review_upload_status → 按该 Upload 下所有 Episode 状态重新计算 data_uploads.status
```

## 5. 关键文件与代码位置速查表

### 后端（`app-prismax-rp-backend`）

| 文件 | 内容 | 关键行号 |
| --- | --- | --- |
| `app_prismax_data_worker/worker.py` | Layer 1 判重函数、Layer 1 调用与失败记录 | 47, 1439–1469, 1543–1577, 1677–1707 |
| `app_prismax_data_worker/worker.py` | Layer 2 阈值常量、vPDQ 比对算法、可疑判定、候选查询、同步写审核记录 | 49–70, 791–882, 884–891, 916–967, 1185–1344 |
| `app_prismax_data_worker/video_duplicate_review_helper.py` | Top N 候选排序、写入 PENDING 审核记录（含唯一索引冲突处理） | 1–130（全文） |
| `app_prismax_data_worker/vpdq_artifact_helper.py` | vPDQ 哈希 artifact 的 GCS 路径构建、读写 | 全文 |
| `app_prismax_data_worker/vpdq_frame_index_helper.py` | `flat` 候选模式下的 Faiss 帧级索引加载/查询 | 全文 |
| `app_prismax_data_pipeline/app.py` | Admin 鉴权 | 566–581 |
| `app_prismax_data_pipeline/app.py` | 3 个 Admin API：列表 / 用户统计 / 决策 + 失败 payload 构建 + 状态汇总同步 | 1768–1924（辅助函数）, 1927–2205（API 1）, 2207–2313（API 2）, 2316–2435（API 3） |
| `app_prismax_data_pipeline/app.py` | Dataset Stats 失败标签归类逻辑 | 2532–2545, 2563–2569 |
| `app_prismax_data_pipeline/sql/20260616_data_video_duplicate_reviews.sql` | `data_video_duplicate_reviews` 表结构、约束、索引 | 1–45（全文） |

### 前端（`app-prismax-rp`）

| 文件 | 内容 | 关键行号 |
| --- | --- | --- |
| `src/components/Admin/AdminPortal.js` | 挂载「Video Duplicates」/「Data Download」/「Dataset Stats」页签 | 19–20, 92–141 |
| `src/components/Admin/VideoDuplicateReviews.js` | 审核 UI 全部逻辑：列表加载、分组、决策提交、用户排行榜 | 全文 628 行；重点 43–65（工具函数）、174–232（列表接口）、239–267（排行榜接口）、273–305（决策接口）、413–624（UI 渲染） |
| `src/components/RoboticData/RoboticDataAdmin.js` | Failed Only 视图把重复失败统一显示为 "Duplication" | 108–124, 163–178 |
| `src/components/Admin/DatasetStatsAdmin.js` | 直接展示后端返回的 "Duplicate video" 失败标签占比 | 119–132 |
| `src/components/Data/Upload.js` | 客户端按相对路径去重（非 Admin，非服务端检测，仅供对比区分） | 410–441, 1012–1013 |

## 6. 从代码实现中可提炼的关键测试关注点

以下均为直接从当前代码逻辑推导，供设计测试用例参考：

1. **Layer 1 判定维度**：只比较 `mcap_size_bytes` 精确值 + 全部视频总大小精确值，与文件名、文件夹名、内容哈希无关。构造两个文件名不同但大小完全相同的上传，预期会被判重；构造大小相差 1 字节的上传，预期不会被判重。
2. **Layer 1 跳过条件**：`task_id == 12` 完全跳过判重；`mcap_size` 或 `video_size` 为 0/null 时不判重（例如视频文件为空或 manifest 缺失视频信息）。
3. **Layer 1 搜索范围**：不限定 task/机器/用户，只要曾经存在任意 `DERIVED_READY` Episode 大小相同即命中，需要验证跨用户、跨任务场景。
4. **Layer 1 失败不进入 Video Duplicates 页面**：由于没有写 `data_video_duplicate_reviews`，需验证这类失败在 Admin「Video Duplicates」页看不到，也没有恢复入口（只能重新上传）。
5. **Layer 2 候选范围**：仅同 `task_id` + 同 `video_slot` 且 `metadata_id` 更小（更早上传）的 `DERIVED_READY` 视频会被比对；跨 task 或跨 slot 的相同视频不会被 Layer 2 发现。
6. **Layer 2 三选一可疑条件**：`score`、`shorter_coverage_pct`、`longest_run` 满足任一超过阈值即生成待审记录，不要求三者同时满足；建议分别构造只满足单一条件的用例。
7. **Layer 2 每 slot Top N 限制**：`VPDQ_REVIEW_LIMIT_PER_SLOT` 默认 3，若某视频有 5 个可疑候选，只会写入分数最高的 3 条。
8. **唯一索引去重**：同一对视频 + 同算法版本重复触发比对（例如 Episode 重新处理）不会产生第二条待审记录（`ON CONFLICT DO NOTHING`）。
9. **Decision 接口 - APPROVED 副作用**：只影响 source Episode，不影响 matched Episode；`processing_error` 中 `duplicate_review_id` 与操作的 review_id 一致。
10. **Decision 接口 - REJECTED 恢复条件**：仅当当前失败恰好由**这条** review 造成才会恢复为 `DERIVED_READY`；如果 Episode 已经被别的原因（如另一条 review 判重，或已经被人工再次改判）覆盖，REJECTED 不会误恢复。
11. **Decision 接口的 decision 别名**：`DUPLICATED`/`DUPLICATE`/`APPROVED` 三者等价，`NOT_DUPLICATED`/`NOT_DUPLICATE`/`REJECTED` 三者等价；其他任意字符串返回 400。
12. **note 长度截断**：超过 2000 字符的 note 会被静默截断，不会报错。
13. **`hide_task_12` 的过滤基准**：列表接口和用户统计接口都明确按 **source**（当前被检查的上传）一侧的 task_id 过滤，不看 matched 一侧；需验证 source 属于 task 12 但 matched 属于生产 task 的组合是否正确隐藏。
14. **前端双重过滤**：即使后端已按 `hide_task_12` 过滤，前端 `visibleReviews` 仍会本地再过滤一次，两者应保持一致，不应出现"接口未返回但前端又滤掉"或"接口已过滤但前端反而显示"的不一致。
15. **列表分页参数边界**：`limit`/`episode_limit` 超出 1–100 直接 400（不像其他部分 Admin 接口那样静默钳制），需验证 0、101、非整数等边界值。
16. **Dataset Stats 与 Data Download 的标签统一但信息更少**：两处都无法区分 Layer 1 精确匹配与 Layer 2 vPDQ 近似匹配导致的失败，也不展示具体的 review_id / score，只能在「Video Duplicates」页面看到完整信息。
17. **decision 接口幂等性**：对已是目标状态的 review 重复提交同一 decision，接口不会报错，会重复更新 `reviewed_at`；前端仅在按钮层面禁用，不能依赖前端限制作为唯一防线。
18. **window.prompt 取消行为**：Admin 点击决策按钮后如果在浏览器原生弹窗点击"取消"，前端不会发起任何请求，页面状态不变；需确认这一点不会造成用户误以为已提交。

## 7. 测试分析：风险与优先级

以下风险均从当前代码实现直接推导，用于指导用例优先级排布（P0 最高）。

| 优先级 | 风险/发现 | 影响 | 建议 |
| --- | --- | --- | --- |
| P0 | Layer 1 是全自动、全局搜索、无人工复核入口的硬失败；只要 `mcap_size_bytes` + 视频总大小与任意历史 `DERIVED_READY` Episode 完全相等就永久判重 | 两个内容完全不同、但字节数恰好相同的正常录制会被误判为重复且无法申诉，只能重新上传（且新上传如果还是这个尺寸，会再次被拒绝，形成死循环风险） | 用構造的等大小不同内容文件验证误判场景；确认产品是否接受"精确尺寸命中直接硬拒绝"而非"送入人工复核队列" |
| P0 | 两层检测都不校验文件内容（无 SHA256/MD5），`Video_Duplicate_Detection_Overview.md` 明确列为未实现功能 | Layer 1 可能因为尺寸巧合误报；同时经过转码/裁剪但尺寸变化的真实重复视频，只能指望 Layer 2 的 vPDQ 兜底，Layer 2 又要求同 task+同 slot 才能命中 | 构造"内容重复但尺寸不同 + 跨 task"的用例，确认这类重复目前确实无法被任何一层检出（属于已知限制，非缺陷） |
| P0 | Admin 鉴权三层校验（JWT 有效 + role=admin + 钱包在 `admin_whitelist`），三个重复检测接口共用同一个 `_require_admin_jwt` | 任一环节遗漏会导致上传者钱包地址、邮箱、内部 upload/episode ID 等敏感信息泄露给未授权用户 | 对 3 个接口分别做 401/403 全组合测试，不能只测其中一个接口就认为其余两个也安全 |
| P0 | `VPDQ_CANDIDATE_MODE` 生产环境实际取值不确定（见 `Video_Duplicate_Detection_Overview.md` §11.1）：代码默认值是 `legacy`，`cloudbuild.yaml` 未显式设置为 `flat` | 若实际是 `legacy`，Layer 2 每次比对都会拉取该 task+slot 下**全部**历史 `DERIVED_READY` 视频做逐帧详细比较，没有 Faiss/Top 20 candidate 剪枝，随着历史数据增长可能出现比对耗时线性膨胀、Worker 处理单个 Episode 超时的风险 | 上线前向 DevOps 确认 `app-prismax-data-worker` 服务的实际 `VPDQ_CANDIDATE_MODE`；在此基础上补充一组"该 task+slot 下历史视频数量较大"的性能测试 |
| P1 | Decision 接口没有乐观锁/版本号保护，两个 Admin 几乎同时对同一 `review_id` 提交不同决策时，后提交者会覆盖前者且不会报错 | 并发操作下可能出现"Admin A 看到的还是 Pending，实际已经被 Admin B 处理"的脏读/覆盖问题 | 构造两个并发请求分别提交 `DUPLICATED` 与 `NOT_DUPLICATED`，验证最终状态、`processing_error`、`data_uploads.status` 是否与"后写入者获胜"的预期一致 |
| P1 | 文档自己承认的已知设计缺陷：一个 Episode 若在 `env`/`left`/`right` 上各产生一条 review，REJECTED 时只检查**当前**存储在 `processing_error.details.duplicate_review_id` 的单个值是否等于本次 review_id | 如果 review A 先被 APPROVED（Episode 失败，记录 review A 的 ID），随后 review B 也被 APPROVED（覆盖为 review B 的 ID），此时如果 Admin 又把 review B 标记 `NOT_DUPLICATED`，Episode 会被误恢复为 `DERIVED_READY`，尽管 review A 仍然是 `APPROVED`（已确认重复） | 必须构造"同一 Episode 存在 ≥2 条 APPROVED review，随后 REJECTED 最后一条"的场景，验证是否出现误恢复（预期：会误恢复，这是已知缺陷，需要作为发现记录） |
| P1 | `hide_task_12` 只按 **source** 一侧的 `task_id` 过滤（列表接口、用户统计接口均如此），且前端拿到数据后又用同样的逻辑本地过滤一次 | 需要验证两层过滤结果完全一致；如果后端 SQL 与前端 JS 的判断口径出现偏差（例如后端看 `se.task_id`，前端看 `review.source.task_id`），可能出现"接口已经隐藏但页面又显示"或反之的情况 | 构造 source=12/matched=生产、source=生产/matched=12 两种组合，同时用浏览器 Network 面板核对接口返回与页面渲染是否一致 |
| P1 | 列表接口 `limit`/`episode_limit` 超出 1–100 直接返回 400，不是静默钳制，行为与仓库里其他部分 Admin 接口的风格（静默钳制到边界值）不一致 | 如果前端或第三方调用方按照"其他接口都是静默钳制"的惯性传入越界值（如 `limit=0`、`limit=200`），会收到意外的 400 而非预期结果 | 专门用例覆盖 `limit=0`、`limit=101`、`limit=abc`、负数等边界/非法输入 |
| P1 | `note` 字段被静默截断到 2000 字符（`str(note).strip()[:2000] or None`），没有任何截断提示 | Admin 填写了超长备注，提交后不会收到"已截断"的反馈，可能误以为完整保存 | 构造恰好 2000 字符与 2001 字符的 note，核对数据库/接口返回的 `admin_note` 是否被截断，且确认前端没有额外提示 |
| P2 | `window.prompt` 是浏览器原生对话框，自动化测试框架（Playwright/Selenium/Cypress）需要专门处理原生 dialog 事件才能继续交互 | 如果自动化脚本没有正确处理 `window.prompt`，测试会挂起或误判为失败 | 手工/探索测试重点验证"点击取消"（不发请求）与"留空直接确定"（发送 `note: ""`）两条路径的真实网络行为；自动化用例需要显式挂载 `page.on('dialog', ...)` 之类的处理器 |
| P2 | 视频签名 URL 有效期为 `DOWNLOAD_TTL_SECONDS = 7 * 24 * 60 * 60` 秒（7 天），页面没有过期检测或自动刷新机制 | 一个 Pending 状态的重复记录如果超过 7 天才被处理，Admin 点击 "Open video" 时链接可能已经失效（返回 GCS 403） | 需要一次跨越 7 天以上的长周期回归（或通过 mock/临时缩短 TTL 的方式）验证过期链接的实际表现和用户提示 |
| P2 | Decision 接口对已是目标状态的 review 重复提交不会报错（幂等），前端仅通过按钮 `disabled` 状态做限制 | 如果通过 API 直接绕过前端（如脚本/Postman）重复提交，`reviewed_at`、`admin_note` 会被不断刷新，没有次数限制 | 单独用 API 直接反复提交同一 decision，确认接口层面的实际行为（预期：成功且刷新时间戳，不是缺陷，但需要文档化） |
| P2 | Dataset Stats 与 Data Download 两处把 Layer 1（尺寸精确匹配）与 Layer 2（vPDQ 近似匹配）失败统一显示为同一文案（"Duplicate video" / "Duplication"） | 现场运营人员无法仅凭这两个页面判断某条失败具体是哪一层触发的，必须跳转到 Video Duplicates 页确认（Layer 1 失败在该页甚至看不到） | 构造 Layer 1 与 Layer 2 各一条失败记录，验证两个页面上文案确实完全相同、无法区分，并确认这是预期行为而非缺陷 |
| P3 | 前端"Hide test data"开关在 Video Duplicates 列表区（`hideTask12`）与用户排行榜区（`hideTask12UserStats`）是两个独立 state，不会互相联动 | 用户在列表区打开隐藏开关后，误以为排行榜也已经过滤，实际上排行榜仍在展示 task 12 的数据 | 专门用例验证切换其中一个开关不影响另一个区域的展示 |

## 8. 测试数据建议

| 数据组 | 关键构造 | 用途 |
| --- | --- | --- |
| A：Layer 1 精确重复 | 两次上传使用同一份 `.mcap`/`.mp4` 文件复制改名（保证字节数完全相同），文件夹路径、episode key 不同 | 验证 `_find_existing_duplicate_files` 精确命中判重 |
| B：Layer 1 边界值 | 视频总大小 ±1 字节、mcap 大小 ±1 字节（相对已有 `DERIVED_READY` Episode） | 验证不会因为"接近"而误判，必须精确相等才命中 |
| C：Layer 1 空值/零值 | manifest 缺失 `.mcap` 文件（`mcap_size=None`）；或全部 `.mp4` 大小之和为 0 | 验证跳过判重（`mcap_size <= 0` 或 `video_size <= 0` 时直接 `return None`） |
| D：Layer 1 Task 12 豁免 | 与已有 `DERIVED_READY` Episode 大小完全相同的文件，以 `task_id=12` 上传 | 验证 Layer 1 整体跳过 |
| E：Layer 1 跨维度命中 | 不同 `user_id`/不同 `machine_id`/不同 `task_id`，但大小完全相同 | 验证 Layer 1 是全局搜索，不受这些维度限制 |
| F：Layer 1 自身重跑 | 同一个 `upload_id` + `raw_video_folder_path` 因为 Worker 重试被重复处理 | 验证不会把自己判定为自己的重复（`NOT (upload_id=... AND raw_video_folder_path=...)`） |
| G：Layer 2 三选一各自独立命中 | 分别构造三组视频对：① 仅 `score ≥ 35%`；② 仅 `shorter_coverage_pct ≥ 40%`；③ 仅最长连续匹配 `≥ 10s`（三者应尽量互斥，即只满足其中一个条件） | 验证 `_is_vpdq_suspicious` 的 OR 逻辑，三条路径都能各自触发送审 |
| H：Layer 2 超过 Top N | 同一个 source 视频与 ≥5 个同 task+slot 的历史视频都命中"可疑"条件 | 验证只会生成分数最高的 `VPDQ_REVIEW_LIMIT_PER_SLOT`（默认 3）条待审记录 |
| I：Layer 2 跨 task / 跨 slot 不命中（已知限制） | 内容完全相同的视频分别放在：① 不同 `task_id`；② 同一 Episode 的不同 `video_slot`（如同一段视频既用作 left 又用作 right） | 验证这两种情况**不会**被 Layer 2 发现（用于确认已知限制的边界，而非报缺陷） |
| J：一个 Episode 多个 Review | 同一 Episode 的 `env`/`left`/`right` 三个 slot 各自命中一个不同的历史视频 | 验证多条 review 共存、决策相互独立处理的行为（对应第 7 节 P1 风险） |
| K：`hide_task_12` 组合 | ① source task=12，matched task=生产 task；② source task=生产 task，matched task=12 | 验证过滤只看 source 一侧，两种组合的显示/隐藏结果应不同 |
| L：Admin 权限矩阵 | 有效 Admin（在白名单）、JWT role=admin 但钱包已从白名单移除、普通用户 Token、过期 Token、无 Token | 验证 401/403 全组合及数据隔离 |
| M：分页测试数据 | 至少 15 组不同 Upload、每组 1-3 条 review 记录（`UPLOADS_PER_PAGE=10`，用于跨页） | 验证 `group_by=upload` 的游标式分页、Previous/Next 正确性 |
| N：`note` 边界值 | 空字符串、恰好 2000 字符、2001 字符、`null`/不传该字段 | 验证截断逻辑 `str(note).strip()[:2000] or None` |
| O：Decision 幂等/状态切换 | 对同一 review 连续提交 `APPROVED→APPROVED`、`APPROVED→REJECTED`、`REJECTED→APPROVED` | 验证 Episode 状态、`processing_error`、`data_video_duplicate_reviews.status` 在各种切换顺序下的最终一致性 |
| P：签名 URL 过期 | 一条 `created_at` 超过 7 天前的 review（或临时调小 `DOWNLOAD_TTL_SECONDS` 验证） | 验证 "Open video" 链接过期后的实际表现 |

## 9. 完整 E2E 测试用例

### 9.1 Layer 1：文件大小重复检测（后端自动，通过上传/DB/失败展示间接验证）

| ID | 优先级 | 场景 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| DUP-L1-001 | P0 | 精确尺寸重复命中 | 已存在一个 `DERIVED_READY` Episode A（已知 mcap/视频总大小） | 上传一份 mcap 大小与视频总大小都与 A 完全相同、但文件名/文件夹不同的新数据 | 新 Episode 直接进入 `DERIVED_VALIDATION_FAILED`；`processing_error.step=duplicate_file_validation`，`details.validation_error_code=duplicate_files`，`details.matched_episode_id` 指向 A |
| DUP-L1-002 | P1 | 视频总大小相差 1 字节不命中 | 同 DUP-L1-001，但让某个 mp4 文件大小 +1 字节 | 上传该数据 | 不触发 Layer 1，继续正常派生流程 |
| DUP-L1-003 | P1 | mcap 大小相差 1 字节不命中 | 同上，mcap 大小 -1 字节 | 上传该数据 | 不触发 Layer 1 |
| DUP-L1-004 | P1 | mcap 缺失时跳过判重 | manifest 中没有 `.mcap` 文件 | 上传该数据 | `mcap_size=None`，Layer 1 直接跳过（不判重），后续走其它校验逻辑（可能因缺 mcap 而在别的步骤失败，但不是因为"duplicate"） |
| DUP-L1-005 | P1 | 视频总大小为 0 时跳过判重 | 全部 mp4 文件大小之和为 0（如空文件） | 上传该数据 | Layer 1 跳过（`video_size <= 0`） |
| DUP-L1-006 | P0 | Task 12 完全豁免 | 与 DERIVED_READY Episode A 大小相同的数据，`task_id=12` | 上传该数据 | 不触发 Layer 1 判重，即便大小完全相同 |
| DUP-L1-007 | P1 | 跨 User/Machine/Task 全局命中 | Episode A 属于 User1/Machine1/Task1，新上传属于 User2/Machine2/Task2，但大小相同 | 上传该数据 | 依然被判定为重复（Layer 1 不限定这些维度） |
| DUP-L1-008 | P1 | 自身重跑不误判 | 同一 `upload_id` + `raw_video_folder_path` 因 Worker 重试再次处理 manifest | 触发 Worker 对同一 manifest 重新处理 | 不会把自己当作重复（`NOT (upload_id=... AND raw_video_folder_path=...)` 条件生效） |
| DUP-L1-009 | P1 | 只匹配 `DERIVED_READY` 状态 | Episode A 大小相同但状态为 `DERIVED_VALIDATION_FAILED`（非 READY） | 上传与 A 大小相同的新数据 | 不会与非 `DERIVED_READY` 的 A 匹配，不触发 Layer 1（除非另有其它 READY Episode 大小相同） |
| DUP-L1-010 | P1 | 多个历史候选时取最新 | 存在两条大小相同的 `DERIVED_READY` Episode（A 更早、B 更晚） | 上传与两者大小都相同的新数据 | `matched_episode_id` 应为 `episode_id` 更大的那个（`ORDER BY episode_id DESC LIMIT 1`），此处应为 B |
| DUP-L1-011 | P0 | Layer 1 失败不进入 Video Duplicates 页 | 已产生一条 DUP-L1-001 式的失败 | Admin 打开「Video Duplicates」页，切换 "All reviews" | 该失败记录**不会**出现在列表中（因为没有写入 `data_video_duplicate_reviews`） |
| DUP-L1-012 | P1 | Layer 1 失败只能靠重新上传恢复 | 同上 | 检查是否存在任何 Admin 操作可以恢复该 Episode | 确认没有 API/UI 能直接恢复；只能重新上传（大小需变化以绕开判重） |

### 9.2 Layer 2：vPDQ 近似重复检测生成（后端自动）

| ID | 优先级 | 场景 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| DUP-L2-001 | P0 | 仅 score 达标触发送审 | 构造两个视频，最佳时间对齐下"较短视频覆盖率"（`score`）≥35%，其余两指标均不达标 | 上传第二个视频完成派生 | 在 `data_video_duplicate_reviews` 生成一条 `PENDING` 记录 |
| DUP-L2-002 | P0 | 仅 shorter_coverage 达标触发送审 | 构造视频使 `shorter_coverage_pct` ≥40%，其余指标不达标 | 同上 | 生成 PENDING 记录 |
| DUP-L2-003 | P0 | 仅最长连续匹配达标触发送审 | 构造视频使 `longest_run.duration_seconds` ≥10s，其余指标不达标 | 同上 | 生成 PENDING 记录 |
| DUP-L2-004 | P1 | 三个指标都不达标不送审 | 构造相似度很低的两个视频 | 上传完成派生 | 不生成任何 review 记录 |
| DUP-L2-005 | P1 | 超过 Top N 只保留最佳 3 条 | 同一 source 视频与 5 个同 task+slot 的历史视频均命中可疑条件，分数互不相同 | 上传完成派生 | 只生成 3 条 review，且是分数最高（其次覆盖率、连续时长、平均距离）的前 3 名 |
| DUP-L2-006 | P1 | 跨 task 不命中 | 内容相同的视频分别在 Task1、Task2 下（其余条件均满足） | 上传完成派生 | 不生成 review（`_find_vpdq_candidate_metadata` 的 `task_id` 过滤生效） |
| DUP-L2-007 | P1 | 跨 slot 不命中 | 同一段视频内容分别用作 `left` 和 `right` | 上传完成派生 | 不生成 review（`video_slot` 过滤生效） |
| DUP-L2-008 | P1 | 只与更早的 metadata 比较 | 视频 X（`metadata_id` 较小）与视频 Y（`metadata_id` 较大，同 task+slot、内容相似）都存在 | 分别以 X 为 source、Y 为 source 触发比较 | 只有以"更晚上传"的一方作为 source 时才会生成 review（`m.metadata_id < :metadata_id`），不会双向都生成 |
| DUP-L2-009 | P2 | 相同一对视频不会重复生成 review | 已存在一条 X↔Y 的 PENDING review | 让 Worker 针对 X 的 Episode 重新触发一次比较（如重跑） | 因唯一索引 `ON CONFLICT DO NOTHING` 生效，不产生第二条记录，`review_id` 保持不变 |
| DUP-L2-010 | P2 | vPDQ 计算失败不影响 Episode 状态 | Mock/构造视频文件损坏导致 vPDQ 哈希计算异常 | 上传该视频完成处理 | Episode 仍然正常进入 `DERIVED_READY`（Layer 2 异常只记录日志，不阻断主流程），只是不会为该视频生成 vPDQ artifact/review |

### 9.3 Admin 鉴权（三个重复检测接口通用）

| ID | 优先级 | 场景 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| DUP-AUTH-001 | P0 | 无 Token 访问 | 不带 Authorization Header | 分别请求列表、用户统计、决策 3 个接口 | 全部返回 401 `invalid token` |
| DUP-AUTH-002 | P0 | 普通用户 Token 访问 | 有效非 Admin JWT | 分别请求 3 个接口 | 全部返回 403 `admin access required` |
| DUP-AUTH-003 | P0 | Admin Role 但钱包不在白名单 | JWT `role=admin`，但 identity 钱包已从 `admin_whitelist` 移除 | 分别请求 3 个接口 | 全部返回 403 |
| DUP-AUTH-004 | P0 | 过期 Token | 已过期的 Admin JWT | 分别请求 3 个接口 | 全部返回 401 |
| DUP-AUTH-005 | P0 | 有效 Admin 全部放行 | 有效 Admin JWT，钱包在白名单 | 分别请求 3 个接口（决策接口用合法 review_id） | 全部成功返回预期数据/结果 |
| DUP-AUTH-006 | P1 | 白名单被移除后立即生效 | Admin 已登录并成功请求过，随后被移除白名单 | 不刷新 Token，直接再次请求 | 立即返回 403，不依赖 Token 重新签发 |

### 9.4 API 1 — 列表接口 `GET /data/admin/video-duplicate-reviews`

| ID | 优先级 | 场景 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| DUP-LIST-001 | P0 | 默认参数 | 存在若干 PENDING/APPROVED/REJECTED 记录 | 不传任何参数请求接口 | `status` 默认 `PENDING`，`group_by` 默认 `review`，`limit` 默认 50，只返回 PENDING 记录 |
| DUP-LIST-002 | P0 | `status=ALL` | 同上 | 传 `status=ALL` | 返回全部状态的记录 |
| DUP-LIST-003 | P1 | `status` 非法值 | - | 传 `status=FOO` | 返回 400，提示合法取值 |
| DUP-LIST-004 | P1 | `group_by=upload` 分组 | 一个 Upload 下有多条 review | 传 `group_by=upload` | 返回按 `upload_id` 聚合的数据结构，`pagination.total_upload_count` 正确 |
| DUP-LIST-005 | P1 | `group_by` 非法值 | - | 传 `group_by=foo` | 返回 400 |
| DUP-LIST-006 | P1 | `limit` 边界 | - | 分别传 `limit=0`、`limit=1`、`limit=100`、`limit=101`、`limit=abc` | `0`/`101`/`abc` 返回 400；`1`/`100` 正常返回且条数受限 |
| DUP-LIST-007 | P1 | `offset` 边界 | 数据量 > limit | 传 `offset=0`、正常翻页、`offset=-1`、`offset=abc` | 负数/非数字返回 400；正常值正确翻页 |
| DUP-LIST-008 | P1 | `episode_limit`/`episode_offset`（仅 `group_by=upload`） | 单个 Upload 下 review 数量较多 | 分别设置边界值 | 同 `limit`/`offset` 的校验规则（1–100，非法值 400） |
| DUP-LIST-009 | P0 | `hide_task_12=true` 只按 source 过滤 | 构造 source=12/matched=生产 和 source=生产/matched=12 两条记录 | 传 `hide_task_12=true` | 只隐藏 source task_id=12 的记录，source 为生产 task 的记录即使 matched 是 task 12 也应正常返回 |
| DUP-LIST-010 | P1 | `hide_task_12` 非法值 | - | 传 `hide_task_12=maybe` | 返回 400（依赖 `_parse_bool_query_arg` 的校验） |
| DUP-LIST-011 | P0 | 返回结构完整性 | 存在一条含完整 source/matched 信息的 review | 请求接口 | 校验 `source`/`matched` 各字段（episode_id、upload_id、task_id、machine_id、product_name、scenario、video_slot、relative_path、size_bytes、video_url、uploader）均正确；`video_url` 为可访问的签名 URL |
| DUP-LIST-012 | P1 | 分页游标正确性 | 数据组 M（≥15 组 Upload） | 使用 `group_by=upload` 连续翻页直到 `has_more=false` | 所有 Upload 恰好各出现一次，不重复不遗漏；`next_offset`/`next_episode_offset` 与实际翻页结果一致 |

### 9.5 API 2 — 用户统计接口 `GET /data/admin/video-duplicate-review-user-stats`

| ID | 优先级 | 场景 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| DUP-STATS-001 | P0 | 基本聚合正确性 | 某用户有 5 条 review（2 条 APPROVED、1 条 PENDING、2 条其他状态），涉及 3 个不同 Upload | 请求接口 | `duplicate_detection_count=5`、`affected_upload_count=3`、`confirmed_duplicate_count=2`、`pending_review_count=1` |
| DUP-STATS-002 | P1 | 排序规则 | 多个用户，检测数量、涉及 Upload 数不同 | 请求接口 | 按 `duplicate_detection_count DESC, affected_upload_count DESC, user_id DESC` 排序 |
| DUP-STATS-003 | P0 | `hide_task_12` 只按 source 过滤 | 同 DUP-LIST-009 的组合，但换算成用户维度 | 传 `hide_task_12=true` | 只排除 source upload/episode 的 `task_id=12` 记录，即使 matched 属于生产 task |
| DUP-STATS-004 | P1 | `limit` 边界 | - | `limit=0`/`101`/`abc` | 返回 400 |
| DUP-STATS-005 | P1 | 钱包地址优先级 | 用户同时绑定多条链地址 | 请求接口 | 按 Solana > Base > Monad > Aptos > Ethereum 优先级返回第一个非空地址及对应 `wallet_chain` |
| DUP-STATS-006 | P2 | 无匹配数据 | 无任何 review 记录 | 请求接口 | 返回空数组，`total_count=0` |

### 9.6 API 3 — 决策接口 `POST /data/admin/video-duplicate-reviews/{review_id}/decision`

| ID | 优先级 | 场景 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| DUP-DEC-001 | P0 | Mark duplicate 基本流程 | 存在一条 PENDING review，对应 source Episode 为 `DERIVED_READY` | POST `{decision: "DUPLICATED"}` | review `status=APPROVED`；source Episode → `DERIVED_VALIDATION_FAILED`，`processing_error.details.duplicate_review_id` 等于该 review_id，`duplicate_detection_algorithm="vpdq"`；matched Episode 状态不变 |
| DUP-DEC-002 | P0 | Not a duplicate 且能恢复 | 紧接 DUP-DEC-001 之后，对同一条 review | POST `{decision: "NOT_DUPLICATED"}` | review `status=REJECTED`；source Episode 恢复为 `DERIVED_READY`，`processing_error` 清空为 `{}` |
| DUP-DEC-003 | P0 | Not a duplicate 但不应恢复（已被其他原因/其他 review 覆盖） | source Episode 因另一条不同的 review（或其他原因）已处于失败状态 | 对一条 PENDING review 提交 `NOT_DUPLICATED` | review 变为 `REJECTED`，但 Episode 状态**不变**（因为 `duplicate_review_id` 不匹配当前 review） |
| DUP-DEC-004 | P1 | decision 别名等价性 | 存在 PENDING review（准备多条） | 分别提交 `DUPLICATED`/`DUPLICATE`/`APPROVED`，以及 `NOT_DUPLICATED`/`NOT_DUPLICATE`/`REJECTED` | 三个"重复"别名效果一致（→APPROVED），三个"非重复"别名效果一致（→REJECTED） |
| DUP-DEC-005 | P1 | 非法 decision 值 | - | POST `{decision: "MAYBE"}` | 返回 400 |
| DUP-DEC-006 | P1 | 缺少 decision 字段 | - | POST `{}` | 返回 400 |
| DUP-DEC-007 | P0 | review_id 不存在 | - | POST 到一个不存在的 review_id | 返回 404 `duplicate review not found` |
| DUP-DEC-008 | P1 | note 边界值 | - | 分别提交长度为 0、2000、2001 字符的 `note` | 2001 字符的会被截断为 2000；0 长度/空白字符串保存为 `null` |
| DUP-DEC-009 | P1 | 不传 note | - | POST 时不带 `note` 字段 | `admin_note` 保存为 `null`，不报错 |
| DUP-DEC-010 | P2 | 幂等重复提交同一 decision | review 已是 APPROVED | 再次提交 `DUPLICATED` | 请求成功，`reviewed_at` 被刷新，`processing_error` 重新写入（内容一致），不报错 |
| DUP-DEC-011 | P1 | `reviewed_by_admin_id` 正确记录 | 使用 Admin X 的 Token 提交决策 | 提交后查询该 review | `reviewed_by_admin_id` 等于 Admin X 的 `admin_id` |
| DUP-DEC-012 | P0 | `data_uploads.status` 联动更新 | 一个 Upload 下只有 1 个 Episode，且该 Episode 只依赖这一条 review | Mark duplicate 后查询该 Upload | `data_uploads.status` 按 `_sync_duplicate_review_upload_status` 规则更新（如全部 Episode 都失败则变为 `DERIVED_VALIDATION_FAILED`） |
| DUP-DEC-013 | P0 | 多 Review 场景下的恢复缺陷复现（对应第 7 节 P1 风险） | 数据组 J：同一 Episode 的 review A、review B 均为可疑记录 | 依次：① Mark review A duplicate（Episode 失败，记录 A 的 ID）；② Mark review B duplicate（覆盖为记录 B 的 ID）；③ 对 review B 提交 Not a duplicate | 步骤③后 Episode 被错误恢复为 `DERIVED_READY`，尽管 review A 仍是 `APPROVED`（记录该已知设计缺陷的复现结果） |
| DUP-DEC-014 | P2 | 未鉴权/越权提交决策 | 使用普通用户 Token | 提交任意 decision | 返回 403，且不应对 review/Episode 产生任何变更 |

### 9.7 前端 `VideoDuplicateReviews` 页面交互

| ID | 优先级 | 场景 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| DUP-UI-001 | P0 | 打开页面默认展示 | 有效 Admin 登录，存在若干 review | Admin Portal → 点击「Video Duplicates」 | 页面默认按 "All reviews" 拉取（`showReviewed=true`），按 Upload 分组展示 |
| DUP-UI-002 | P1 | 切换 Pending/All | 同上 | 点击 "Pending" 标签 | 只请求/展示 `status=PENDING` 的记录；再切回 "All reviews" 恢复全部 |
| DUP-UI-003 | P1 | Hide test data（列表区） | 数据组 K | 打开开关 | 前端隐藏 `source.task_id === '12'` 的分组；与接口返回的 `hide_task_12=true` 结果核对一致 |
| DUP-UI-004 | P3 | Hide test data 不联动排行榜 | 同上 | 只打开列表区开关，不动排行榜开关 | 排行榜区域展示不变（各自独立 state） |
| DUP-UI-005 | P1 | 分组展开/收起 | 至少一个 Upload 分组含多条 review | 点击分组标题 | 展开显示该组内所有 review 卡片；再次点击收起 |
| DUP-UI-006 | P1 | 分组头部信息正确性 | 同上 | 展开前查看分组头部 | Upload ID、scenario 标签、匹配数量、上传者身份、最高相似度分数、待审徽章（"Reviewed"/"N pending"）均正确 |
| DUP-UI-007 | P1 | 视频对比面板 | 展开一条 review | 查看 "Uploaded video" 与 "Similar video" 两个面板 | Episode ID、Upload ID、Task ID、机器名、scenario、相对路径均正确；点击 "Open video" 能正常播放签名 URL 视频 |
| DUP-UI-008 | P0 | Mark duplicate 交互 | 一条 PENDING review | 点击 "Mark duplicate" → 弹出 `window.prompt` → 输入备注并确定 | 请求成功后 toast 提示、列表刷新、该 review 状态徽章变为 "Duplicate"（绿色），"Mark duplicate" 按钮变为禁用 |
| DUP-UI-009 | P1 | Not a duplicate 交互 | 一条 PENDING review | 点击 "Not a duplicate" → 弹窗确定（留空） | 请求体 `note` 为空字符串；状态徽章变为 "Not duplicate"（红色），该按钮变为禁用 |
| DUP-UI-010 | P1 | 弹窗取消不发请求 | 同上 | 点击任一决策按钮后，在 `window.prompt` 点击"取消" | 不发起网络请求，页面状态不变（用浏览器 Network 面板确认无请求） |
| DUP-UI-011 | P2 | 提交中禁用按钮防重复点击 | 网络延迟场景（可用节流模拟） | 点击 "Mark duplicate" 后立即再次点击 | 提交期间两个按钮均禁用，不会发出重复请求 |
| DUP-UI-012 | P1 | 决策失败提示 | Mock 接口返回 500/401 | 点击任一决策按钮并确认 | 显示错误 toast；若为登录过期（401），触发统一的重新登录流程（`handleAdminSessionExpired`） |
| DUP-UI-013 | P1 | 分页 Previous/Next | 数据组 M（≥2 页） | 点击 Next 加载下一页，再点击 Previous 回退 | 数据正确切换；首页 Previous 禁用，末页（`has_more=false`）Next 禁用 |
| DUP-UI-014 | P1 | 用户排行榜展示与刷新 | 存在多个用户的重复检测记录 | 查看排行榜表格；触发一次决策提交 | 列（#、User、Detected matches、Affected uploads、Confirmed、Pending）数值正确；决策提交成功后排行榜自动刷新对应计数 |
| DUP-UI-015 | P1 | 排行榜 Hide test data 独立开关 | 数据组 K | 只打开排行榜区域的开关 | 排行榜按 `hide_task_12` 重新请求；列表区域不受影响 |
| DUP-UI-016 | P2 | 空状态展示 | 当前筛选条件下无匹配记录 | 切换到该筛选条件 | 显示 "No duplicate reviews found for this filter." |
| DUP-UI-017 | P2 | 非 Admin 访问该组件 | 无 `adminToken` | 直接渲染 `VideoDuplicateReviews` 组件（或 token 失效后） | 显示 "Admin access required."，不发起任何接口请求 |

### 9.8 跨页面联动：Data Download / Dataset Stats

| ID | 优先级 | 场景 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| DUP-CROSS-001 | P1 | Layer 1 失败在 Data Download 显示 "Duplication" | 已产生 DUP-L1-001 式的失败 | Admin Portal →「Data Download」→ Failed Only 视图 | 该 Episode 的失败原因显示为 "Duplication"，不展示 `matched_episode_id` 等原始字段 |
| DUP-CROSS-002 | P1 | Layer 2（已 Mark duplicate）在 Data Download 显示 "Duplication" | 已完成 DUP-DEC-001 | 同上 | 同样显示 "Duplication"，与 Layer 1 失败展示文案一致、无法区分 |
| DUP-CROSS-003 | P1 | Layer 1 失败在 Dataset Stats 显示 "Duplicate video" | 同 DUP-CROSS-001 | Admin Portal →「Dataset Stats」查看失败原因分布 | 该 Episode 计入 "Duplicate video" 分类 |
| DUP-CROSS-004 | P1 | Layer 2 失败在 Dataset Stats 显示 "Duplicate video" | 同 DUP-CROSS-002 | 同上 | 同样计入 "Duplicate video"，占比与 Layer 1 失败合并统计 |
| DUP-CROSS-005 | P1 | Not a duplicate 后 Dataset Stats/Data Download 恢复正常 | 完成 DUP-DEC-002（Episode 恢复 `DERIVED_READY`） | 分别查看两个页面 | 该 Episode 不再出现在 Failed 列表/失败分布中，计入 PASS |
| DUP-CROSS-006 | P2 | 两处标签文案与 Video Duplicates 页详细信息串联核对 | 同 DUP-CROSS-002 | 从 Data Download/Dataset Stats 跳转确认后，再到「Video Duplicates」页用 Upload ID 搜索/定位 | 能在 Video Duplicates 页找到对应的详细 score、matched episode 等信息，验证三处数据来源一致 |

### 9.9 非 Admin：客户端路径去重（对比验证，防止与服务端检测混淆）

| ID | 优先级 | 场景 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| DUP-CLIENT-001 | P1 | 同批次选中重复路径 | 普通用户打开 Upload 页面 | 通过文件夹选择器选中同一文件两次（或包含重复相对路径的文件集合） | 页面显示 "Skipped N duplicate paths."，重复项不出现在待上传列表中；**不发起任何网络请求** |
| DUP-CLIENT-002 | P1 | 不同批次选择不去重 | 已上传过一批文件 | 再次选择一批路径不同但内容相同的文件 | 不会提示 "duplicate paths"（该逻辑只在同一次选择内生效），文件正常进入待上传列表 |
| DUP-CLIENT-003 | P0 | 客户端去重与服务端检测互不影响 | 一批文件本身没有客户端路径重复 | 正常上传，且这批文件与历史数据触发 Layer 1/Layer 2 | 客户端不会提示 duplicate paths；Layer 1/Layer 2 检测正常按 2.1/2.2 节逻辑独立运行 |
| DUP-CLIENT-004 | P2 | 大小写/路径分隔符差异 | 选择路径分别为 `A/b.mp4` 与 `a/B.mp4`（大小写不同）的两个"同名"文件 | 上传 | 由于 `relativePath` 是精确字符串匹配，大小写不同不会被判定为客户端重复（两者都会被保留） |
| DUP-CLIENT-005 | P2 | 忽略路径不计入重复计数 | 选择集合中包含系统忽略文件（如 `.DS_Store`）重复多份 | 上传 | 被 `isIgnoredPath` 过滤的文件不计入 `duplicateCount`，也不出现在待上传列表 |

### 9.10 环境/配置相关

| ID | 优先级 | 场景 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| DUP-ENV-001 | P0 | 确认生产环境实际的 `VPDQ_CANDIDATE_MODE` | 有权限查看 Cloud Run 服务配置 | 查询 `app-prismax-data-worker` 服务环境变量 | 确认实际值是 `legacy` 还是 `flat`，并据此决定 9.2 节 Layer 2 相关用例的候选范围预期（是否需要额外验证 Top 20/Faiss 索引路径） |
| DUP-ENV-002 | P1 | `flat` 模式下的 Faiss 索引缺失回退 | `VPDQ_CANDIDATE_MODE=flat`，且目标 task+slot 尚未构建 Faiss 索引 | 上传新视频触发 Layer 2 | 应自动回退到 `_find_vpdq_candidate_metadata`（legacy 查询），日志出现 `vpdq_flat_fallback_legacy`，不应导致处理失败 |
| DUP-ENV-003 | P2 | `flat` 模式下近期未索引视频补漏 | `VPDQ_CANDIDATE_MODE=flat`，两个相似视频在同一小时内相继上传（尚未被小时级索引更新任务收录） | 上传第二个视频 | 第一个视频应通过"近期未索引"扫描（`VPDQ_RECENT_UNINDEXED_LIMIT`）被纳入候选，仍然生成待审记录，不会因索引滞后而漏检 |
| DUP-ENV-004 | P3 | 各 VPDQ 阈值环境变量可调 | 有权限修改测试环境变量 | 将 `VPDQ_REVIEW_SCORE_THRESHOLD` 临时调整为极端值（如 100 或 0）并重新触发比较 | 阈值调整后送审行为随之变化（调到 100 几乎不再送审，调到 0 几乎全部送审），验证配置确实生效而非硬编码 |

## 10. Admin API 参考 cURL

先设置测试环境的数据服务地址与 Admin JWT（仅当前 Shell 会话生效，不要把真实 Token 提交到 Git）：

```bash
export PRISMAX_DATA_PIPELINE_URL="https://<data-pipeline-host>"
export PRISMAX_ADMIN_JWT="<admin-jwt>"
export DUP_REVIEW_ID="<review-id>"
```

1. 获取待审记录列表（按 Upload 分组，隐藏 task 12）：

```bash
curl --get \
  --url "${PRISMAX_DATA_PIPELINE_URL}/data/admin/video-duplicate-reviews" \
  --header "Authorization: Bearer ${PRISMAX_ADMIN_JWT}" \
  --header "Accept: application/json" \
  --data-urlencode "status=PENDING" \
  --data-urlencode "group_by=upload" \
  --data-urlencode "hide_task_12=true" \
  --data-urlencode "limit=10" \
  --data-urlencode "episode_limit=100"
```

2. 获取全部状态的记录（不分组，按单条 review 平铺）：

```bash
curl --get \
  --url "${PRISMAX_DATA_PIPELINE_URL}/data/admin/video-duplicate-reviews" \
  --header "Authorization: Bearer ${PRISMAX_ADMIN_JWT}" \
  --header "Accept: application/json" \
  --data-urlencode "status=ALL" \
  --data-urlencode "group_by=review"
```

3. 获取用户重复检测排行统计：

```bash
curl --get \
  --url "${PRISMAX_DATA_PIPELINE_URL}/data/admin/video-duplicate-review-user-stats" \
  --header "Authorization: Bearer ${PRISMAX_ADMIN_JWT}" \
  --header "Accept: application/json" \
  --data-urlencode "limit=100" \
  --data-urlencode "hide_task_12=false"
```

4. 提交决策：标记为重复：

```bash
curl --request POST \
  --url "${PRISMAX_DATA_PIPELINE_URL}/data/admin/video-duplicate-reviews/${DUP_REVIEW_ID}/decision" \
  --header "Authorization: Bearer ${PRISMAX_ADMIN_JWT}" \
  --header "Content-Type: application/json" \
  --data '{"decision": "DUPLICATED", "note": "confirmed same recording, QA test"}'
```

5. 提交决策：标记为非重复（可能恢复 Episode）：

```bash
curl --request POST \
  --url "${PRISMAX_DATA_PIPELINE_URL}/data/admin/video-duplicate-reviews/${DUP_REVIEW_ID}/decision" \
  --header "Authorization: Bearer ${PRISMAX_ADMIN_JWT}" \
  --header "Content-Type: application/json" \
  --data '{"decision": "NOT_DUPLICATED", "note": ""}'
```

6. 验证鉴权失败场景（无 Token / 非法 decision）：

```bash
curl --include --get \
  --url "${PRISMAX_DATA_PIPELINE_URL}/data/admin/video-duplicate-reviews"

curl --include --request POST \
  --url "${PRISMAX_DATA_PIPELINE_URL}/data/admin/video-duplicate-reviews/${DUP_REVIEW_ID}/decision" \
  --header "Authorization: Bearer ${PRISMAX_ADMIN_JWT}" \
  --header "Content-Type: application/json" \
  --data '{"decision": "MAYBE"}'
```

排查鉴权或状态码问题时，建议加上 `--include` 同时查看 HTTP Status 与 Response Headers。
