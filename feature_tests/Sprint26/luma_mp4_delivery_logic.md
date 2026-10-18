# `luma_mp4_delivery` 功能与逻辑分析

> 分析日期：2026-10-16（UTC+8）
> 分析目录：`0_QA_PrismaX/product_requirements/luma_mp4_delivery/`
> 快照来源：`fix/luma-serial-letter-guard` 分支 `7554497`，包含当时未提交的工作区修改
> 注意：该目录是从主仓库抽出的代码副本和片段，不应直接修改或运行；`excerpts/` 不是完整 Python 模块。

---

## 1. 目标与结论

这套代码负责把 PrismaX 内部的 `MP4 + MCAP` episode 转换成 Luma 约定的统一格式，并上传到：

```text
gs://prismax-raw-luma/<staging_id>/
```

完整流程是：

1. 接收 Yun 上传，或从 Verlet 的 Cloudflare R2 拉取数据；
2. 注册原始视频和 MCAP，生成内部审核用的视频预览；
3. 根据 review 状态、文件完整性、rig profile、夹爪标定和客户配额筛选候选 episode；
4. 在临时目录中重写 MCAP，统一夹爪、相机 topic 和任务字段的语义；
5. 将三路 MP4 和转换后的 MCAP 上传到 Luma bucket；
6. 所有文件上传成功后，才在数据库中记录本次交付。

它不是简单的文件复制工具，而是一条带数据语义转换、质量门禁、配额控制和失败恢复能力的交付流水线。

---

## 2. 核心概念

### 2.1 Episode

一个 episode 表示一段完整的机器人操作数据，通常包含：

- 三路相机视频：`cam_high.mp4`、`cam_left.mp4`、`cam_right.mp4`；
- 一份遥测 MCAP；
- 可选的 URDF；
- 可选的夹爪标定 metadata。

数据库使用 `staging_id` 标识 episode，Luma bucket 也以它作为目录名。

### 2.2 Rig

**Rig 是一套具有固定硬件结构、数据格式和信号语义的机器人采集配置。**

它不只代表供应商或机器人型号，还包括：

- 相机和机器人硬件组合；
- 视频格式，以及单目/双目形态；
- MCAP topic 和 `/task_info` 字段；
- Leader gripper 的单位、零点和开合方向；
- 交付前需要执行的转换。

同一供应商可能有多套 rig。Yun 的 SVO2 与 MP4 rig 使用相反的夹爪极性，因此代码以 `(supplier, episode_format)` 选择 `RigProfile`，不能只看 supplier。

当前有三个 profile：

| Rig profile | 视频形态 | Leader gripper 原始语义 | 交付处理 |
| --- | --- | --- | --- |
| `yun/svo2` | ZED 双目 SVO2 | `1=closed, 0=open` | 用 `(closed, open)=(1,0)` 归一化，并裁出左眼 |
| `yun/mp4` | 单目 MP4 | `0=closed, 1=open` | 用 `(0,1)` 归一化，视频原样交付 |
| `verlet/mp4` | 单目 MP4 | 每个 episode 不同的 motor radians | 读取该 episode 的标定后严格归一化 |

未知组合没有默认 profile，会直接停止交付，避免把一套 rig 的信号规则误用于另一套。

### 2.3 R2

这里的 R2 指 **Cloudflare R2**，是一种兼容 Amazon S3 API 的对象存储。Verlet 使用它向 PrismaX 发布原始 episode。

```text
Verlet 采集数据
      │
      ▼
Cloudflare R2（供应商入口）
      │ bio_ingest.py 下载并校验
      ▼
PrismaX 本地 staging（注册、后处理、转换）
      │
      ▼
Google Cloud Storage（最终交付）
      │
      ▼
Luma
```

R2 中主要包括三路 MP4、MCAP、`_status` manifest，以及早期标定文件和机器人描述文件。访问配置如下：

| 环境变量 | 用途 |
| --- | --- |
| `R2_ENDPOINT` | R2 的 S3-compatible endpoint |
| `R2_ACCESS_KEY` | Access key |
| `R2_SECRET_KEY` | Secret key |
| `R2_BIO_BUCKET` | 可选 bucket 名；默认 `prisma-bio-batch3` |

### 2.4 RAW、L1 和 L2

| 层级 | 含义 | 用途 | 是否交付 Luma |
| --- | --- | --- | --- |
| RAW | 供应商上传的原始文件 | 内部源数据 | 不直接以 RAW 产品交付 |
| L1（Level 1） | 高质量、接近原始的视频产品 | 正式交付、算法处理 | 是 |
| L2（Level 2） | 480p H.264 轻量预览 | Web Review UI | 否 |

MP4 流程中，L1 并不重新生成，而是把 RAW MP4 原地注册为 `video_l1`；RAW 与 L1 指向同一个文件。L2 则是单独转码的浏览器预览：

```text
RAW cam_high.mp4  ─┬─► video_l1（原文件，交付来源）
                   └─► video_l2/high.mp4（480p 预览）

RAW cam_left.mp4  ─┬─► video_l1
                   └─► video_l2/left.mp4

RAW cam_right.mp4 ─┬─► video_l1
                   └─► video_l2/right.mp4
```

“Level”表示处理层级，不是质量评分。L2 不能替代 L1 作为训练或正式交付数据。

---

## 3. 整体架构

```text
Yun 上传 API ─────────────┐
                          ▼
Verlet R2 ─► bio_ingest ─► episodes / files
                          │ RAW: 3 MP4 + 1 MCAP + [URDF]
                          ▼
                    Postprocess
              ┌───────────┼────────────┐
              ▼           ▼            ▼
       video_l1 alias   mcap alias   video_l2 preview
              │           │
              └─────┬─────┘
                    ▼
              Candidate 筛选
       review / 文件 / rig / 标定 / 配额
                    │
                    ▼
              deliver_episode
       临时重写 MCAP；MP4 原样改名
                    │
                    ▼
       gs://prismax-raw-luma/<staging_id>/
                    │ 全部成功
                    ▼
       customer_statuses = PENDING + batch
```

最终目录结构：

```text
<staging_id>/
  telemetry.webui.mcap
  cam_high.mp4
  cam_left_wrist.mp4
  cam_right_wrist.mp4
  [<robot>.urdf]
```

---

## 4. 数据进入系统

### 4.1 Yun 上传

`_derive_format()` 检查原始文件名，只要存在 `.mp4`，就将 upload 标为 `episode_format='mp4'`。典型输入是三路 MP4、一份 MCAP，以及可选 URDF，最初都以 `kind='raw'` 注册。

### 4.2 Verlet R2 ingest

`bio_ingest.py` 使用 `boto3` 读取 R2，流程如下：

1. 并发读取两个 prefix 下的 `_status` manifest；
2. 只接受 `status=completed`、未 excluded 且 `audit_clean != false` 的记录；
3. 以 manifest 的 artifact 列表为准，要求恰好一个 MCAP 和三路固定 MP4；
4. 对仍在上传中的不完整 episode 本轮跳过，下次重新发现；
5. 用 `idempotency_key` 防止重复注册，包括 unreviewed 被提升为 reviewed 的情况；
6. 并发下载文件，检查大小，并在 R2 提供 SHA-256 时校验整文件 hash；
7. 通过统一上传 API 注册，不绕过 staging 的文件放置和磁盘保护；
8. 每个 episode 下载前检查取消信号与剩余空间。

Job 的 prepare 阶段完成下载和注册；后续再扫描所有 Verlet episode，确认交付代码能够读取左右臂标定，使问题尽早暴露。

### 4.3 Verlet 标定来源

Verlet 的 gripper 使用原始 motor radians，每个 episode 都必须有左右臂各自的 `(closed, open)`。

读取顺序是：

```text
本地 RAW MCAP 的 gripper_limits metadata record
                    │
           完全没有该 record
                    ▼
已注册的 *_gripper_limits.json sidecar
```

关键规则：

- MCAP record 必须声明 `units='motor_radians'`；
- 左右臂必须同时有 closed/open；
- 数值必须有限，且 `abs(open-closed) >= 1e-6`；
- 如果 MCAP 中存在 record 但内容非法，直接拒绝，不回退 sidecar；
- sidecar 只服务没有 MCAP record 的早期 export；
- sidecar 注册为 `metadata` 而不是 `raw`，避免 RAW 回收时删除交付前置条件。

---

## 5. Postprocess

`process_episode_any()` 按 SVO2 → ego → 普通 MP4 的顺序判断格式。Ego 原始文件也是 MP4，因此必须先判断 ego。

对于普通 MP4：

- **L1**：把三路 RAW MP4 原地注册为 `video_l1`，不复制、不转码；
- **MCAP**：把 RAW telemetry MCAP 原地注册为 `mcap`，此阶段不修改；
- **L2**：转成 `high/left/right.mp4` 的 480p H.264 预览；
- **时长**：优先使用 `cam_high` 的 `frames / fps` 填写 `length_seconds`；
- **Graph cache**：best-effort 生成，失败不阻断后处理。

由于 L1 与 RAW 是同一路径的 alias，回收逻辑必须识别这种关系；删除 RAW 实体会同时破坏 L1。

Quick Process 只读取视频容器 header 来补 `length_seconds`，不转码，也不注册新产品。它用于让尚未完成完整后处理的 episode 尽快参与时长和配额计算。

---

## 6. 候选筛选与配额

### 6.1 候选筛选

`find_candidates()` 会在 SQL 查询中直接应用 `supplier`、`task_name`、`robot_type` scope，避免读取全库后再过滤。

可交付 episode 必须满足：

1. `review_status != 'FAIL'`；
2. Luma 尚无 `customer_upload_time`；
3. format 不在 `PAUSED_FORMATS`，当前该列表为空；
4. 本地存在 MCAP 和至少一个 L1 视频；
5. 文件没有非预期丢失；
6. rig 有明确 `RigProfile`；
7. 两个 leader topic 都有可用的 gripper limits。

常见拒绝原因：

| 原因 | 含义 |
| --- | --- |
| `not post-processed` | 尚无 MCAP 产品 |
| `product missing on disk` | DB 认为存在，但文件意外丢失 |
| `no level-1 videos` | 没有 L1 视频 |
| `no delivery profile for rig ...` | 未定义该 rig 的数据语义 |
| `gripper calibration missing` | 标定缺失或不完整 |

若文件行的 `size_bytes=NULL` 且文件不存在，说明它被主动回收，此 episode 直接退出候选范围，不记为异常。URDF 是可选附件，有则附带，无则不阻塞交付。

### 6.2 Requested-hours 配额

配额按 `(task_name, robot_type)` 分桶：

```text
remaining_seconds = requested_hours × 3600
                    - 已交付且状态为 PASS/PENDING 的时长
```

候选按 `staging_id` 从旧到新处理：

- 没有对应配额：`no_quota`；
- 配额已经满足：`quota_met`；
- `length_seconds` 缺失或无效：`unknown_length`；
- 配额尚有余额时保留当前 episode，即使它使总量略微超过目标；
- `PASS` 和 `PENDING` 消耗配额，`FAIL` 不消耗；
- CLI 的 `--ignore-quota` 可以跳过此限制，Web Job 正常会应用。

---

## 7. 交付转换

所有转换都在临时目录中处理本地文件的副本，不修改内部源数据。

### 7.1 Gripper 归一化

只处理两个 leader `JointState` topic 的第七个 position/velocity，follower 不变：

```text
delivered_position = (raw_position - closed) / (open - closed)
delivered_velocity = raw_velocity / (open - closed)
```

所有 rig 最终统一为：

```text
closed = 0.0
open   = 1.0
```

Yun 已归一化数据不 clamp，以保持既有 corpus 行为。Verlet 使用 strict 模式：有限值 clamp 到 `[0,1]`；超出范围超过 `1e-6` 才计数；任一臂超过 1% 消息超出标定范围时，整个 episode 拒绝交付。

### 7.2 Camera topic

```text
/robot/camera/cam_high/...  -> /robot/camera/high/...
/robot/camera/cam_left/...  -> /robot/camera/left_wrist/...
/robot/camera/cam_right/... -> /robot/camera/right_wrist/...
```

映射显式定义，因为 `cam_left -> left_wrist` 是 rig 语义，不是简单字符串处理。

### 7.3 `/task_info`

Yun 使用字段改名：

- `task_name -> task`；
- `task_id -> serial_number`；
- `task_description` 改成 master task label；
- 只为缺字母的 `YAM-BIO-` serial 补 B，例如 `YAM-BIO-016 -> YAM-BIO-B-016`；
- `BIO-NEW-006` 等其他 family 保持原样。

Verlet 的 `task_id` 恒为 `"0"`，因此直接重建：

```json
{
  "task": "<master task label>",
  "task_description": "<master task label>",
  "serial_number": "<subtask prose>"
}
```

`serial_number` 来自 `subtasks[].description`。多个 subtask 用 `; ` 连接，开头的 `BIO-NEW-<n> ·` collection 标识会被移除。

Yun 路径是在原 dict 上改名，并不会主动删除所有额外字段；Verlet 路径则明确重建为三个字段。无法解析为 JSON object 的 `/task_info` 会原样透传。

### 7.4 MCAP 中不变的内容

转换会重新写 MCAP container，但保持 schema、channel metadata、消息顺序、时间戳和 sequence。除指定的 gripper、camera topic 和 task info 外，其余消息数据不应改变。

### 7.5 视频与文件名

MP4 rig 是单目，L1 视频不裁剪、不转码，只统一文件名：

| 内部文件 | Luma 对象名 |
| --- | --- |
| 任意编号 MCAP，如 `64.mcap` | `telemetry.webui.mcap` |
| `cam_high.mp4` | `cam_high.mp4` |
| `cam_left.mp4` | `cam_left_wrist.mp4` |
| `cam_right.mp4` | `cam_right_wrist.mp4` |
| `<robot>.urdf` | 保留原名 |

代码优先在临时目录创建目标文件名的 symlink，避免复制大视频；不支持 symlink 时才退回复制。

`luma_video_crop.py` 只用于 SVO2：将双目视频裁成左眼 HEVC，并恢复源 PTS。它会核对帧数和尺寸，防止重编码引入帧复制或时间错位。

---

## 8. 上传、落账与幂等

`deliver_episode()` 的执行顺序：

1. 创建临时目录；
2. 转换 MCAP；
3. 必要时处理视频，MP4 则原样保留；
4. 整理成交付文件名；
5. 通过 `gcloud storage cp` 上传；
6. 所有文件成功后写 `customer_statuses`。

上传失败最多重试 3 次。每个 `gcloud` 调用最多运行 600 秒；超时后会终止整个进程组，避免子 worker 残留并卡住任务。

成功后写入：

```text
customer_id              = 3
customer_task_status     = PENDING
customer_upload_batch_id = 本轮 batch
customer_upload_time     = now
```

Batch 默认取 Luma 历史最大 batch id 加 1，并在一次 job 的 prepare 阶段只解析一次。

数据库状态是幂等边界：已有 `customer_upload_time` 的 episode 不会再次成为候选。如果上传中途失败，bucket 可能留下部分对象，但数据库不会标记完成；下次运行会重新上传同名文件。它不是 GCS 与数据库之间的原子事务，但通过“最后写数据库”避免把不完整 episode 记录为已交付。

`PENDING` 表示已经交给 Luma、尚无 verdict。Luma 实际不返回 verdict，因此 PENDING 会长期保留并计入配额。

---

## 9. 运行方式

### 9.1 WebUI Job

`upload_luma` 使用 `CPU + GPU + UPLOAD` 资源，支持按 supplier、task、robot type、upload 和 staging id 限定范围。

```text
prepare     -> 解析 batch id
discover    -> 候选筛选
            -> staging_ids 过滤
            -> 配额过滤
            -> limit
process_one -> 交付单个 episode
```

即使本轮只有不需要 crop 的 MP4，当前 job kind 仍会占用 GPU。

### 9.2 定时任务

快照中唯一的时钟任务是在每天 08:00 `America/Los_Angeles` 运行：

```text
yun / Block manipulation postprocess
                  │ after_key
                  ▼
yun / Block manipulation upload_luma
```

该 scope 当前是 SVO2，不是 MP4；它是增加 MP4 定时交付时可复用的 postprocess → delivery 模板。调度器支持服务重启和抢占后的恢复，人工 cancel 则会停止当天重试。

### 9.3 CLI

```bash
python upload/submit_to_luma.py --dry-run
python upload/submit_to_luma.py --limit 3 --yes
python upload/submit_to_luma.py --yes
```

CLI 没有 supplier/task scope，会扫描全部已知 rig。精确交付 MP4 应使用 Web Job。运行需要 `STAGING_DB_URL`，以及对 Luma bucket 有写权限的 `gcloud` 登录。

---

## 10. 失败策略与风险边界

### 10.1 会阻止交付

- rig 未定义；
- 任一 leader 缺少标定；
- MCAP 中的标定 record 存在但非法；
- 标定 span 为 0；
- calibrated gripper 超范围消息超过 1%；
- MCAP/L1 未生成或文件意外丢失；
- SVO2 crop 的尺寸、帧数或 PTS 不一致；
- `gcloud` 连续三次失败。

### 10.2 不会阻止交付

- URDF 缺失；
- graph cache 生成失败；
- R2 episode 尚未完整上传：本轮跳过，下轮再发现；
- 产品被明确回收：退出候选范围，不作为异常上报。

### 10.3 仍需人工判断的风险

- Gripper 极性无法只靠数值推断，必须结合 rig profile 和视频；
- 单目与双目不能仅凭宽度判断，必须依赖 format；
- wrist 视频交叉时，代码无法判断 CameraInfo 是否也应交换；
- L1 是 RAW alias，错误回收 RAW 会破坏 L1；
- GCS 与数据库不是同一事务，失败后可能留下未落账的部分对象。

---

## 11. 历史修复

`migrations/` 下的脚本是一次性修复工具，不属于日常交付流程。

### 11.1 Migration 一览

| 文件 | 修复内容 | 关键安全措施 |
| --- | --- | --- |
| `unship_luma_mp4_2026_08_25.py` | 撤回早期格式错误的 MP4 交付，并删除 Luma delivery row | 先记录和删除 bucket 对象，最后删 DB 状态；本地源不动 |
| `reshape_luma_mp4_mcaps_2026_08_25.py` | 统一已交付 MCAP、camera topic、task info 和对象名 | 从本地源重建；上传前校验输出 |
| `backfill_luma_urdf_2026_08_26.py` | 为已交付 Yun MP4 补传 URDF | 只向已有且非空的 episode prefix 增加缺失 URDF |
| `redeliver_luma_mp4_gripper_2026_09_03.py` | 修复 Yun MP4 夹爪极性反向 | 从本地 MCAP 重建；只允许 gripper slot 变化 |
| `register_verlet_gripper_sidecars_2026_09_03.py` | 检查和补齐早期 Verlet 标定 sidecar | 优先使用本地 MCAP；无可靠来源则 held back |
| `swap_luma_wrist_names_2026_09_09.py` | 交换 55 个 Verlet episode 的左右 wrist 视频对象名 | 三步 server-side swap；manifest 防止重复交换 |
| `redeliver_luma_serial_2026_09_10.py` | 修复错误生成的 `BIO-NEW-B-*` serial | 只允许 `serial_number` 变化；支持 manifest resume |

共同原则：从本地源重新派生，不直接修改旧 payload；上传前限制差异范围；记录 manifest；不重复写 delivery row，避免重复计算 batch 和配额。

### 11.2 历史数字不一致

快照对 Yun MP4 夹爪反向事件的数量有不同表述：

- `README.md` 写 979 个 episode；
- `submit_to_luma.py` 注释写 857 个；
- migration docstring 没有给出同一数字。

实现结论没有冲突：`yun/mp4` 曾误套 `yun/svo2` 的 `(1,0)` profile，修复后改用 `(0,1)`。准确影响数量应以 migration manifest 或生产数据库为准，不能直接采用快照注释。

---

## 12. 文件导航与测试

### 12.1 主要文件

| 文件 | 职责 |
| --- | --- |
| `core/submit_to_luma.py` | 候选筛选、rig profile、标定、配额衔接、上传和落账 |
| `core/luma_mcap_transform.py` | 夹爪、camera topic、task info 转换 |
| `core/gcloud_run.py` | 有 timeout 的 `gcloud` 进程管理 |
| `core/luma_video_crop.py` | SVO2 左眼裁剪和 PTS 恢复 |
| `ingest/bio_ingest.py` | Verlet R2 ingest 和标定 sidecar 管理 |
| `excerpts/postprocess_mp4.py` | MP4 L1/L2/MCAP 后处理 |
| `excerpts/quota.py` | requested-hours 配额 |
| `excerpts/job_webui_luma_spec.py` | Luma JobSpec |
| `excerpts/job_webui2_kinds.py` | Job kind 与资源声明 |
| `excerpts/job_webui2_schedule.py` | 定时任务链 |

### 12.2 测试固定的业务合同

- camera topic 必须统一成交付名称；
- `task_id` 必须映射为 `serial_number`；
- 只能为 `YAM-BIO` 补任务字母，不能修改 `BIO-NEW`；
- 不同 rig 最终都必须满足 `closed=0, open=1`；
- 缺失或不匹配的标定必须拒绝，不能套默认值；
- Verlet 多个 subtasks 不能被截断；
- URDF 可选，未知 rig 禁止交付；
- MCAP 标定优先于 sidecar；
- scope 必须进入 SQL 查询；
- R2 discovery 必须以 manifest 为准；
- 下载必须响应 cancel 并保护磁盘空间。

---

## 13. 最终理解

这条链路解决了三类问题：

1. **文件统一**：把不同 rig 的文件名和目录整理成稳定的 Luma layout；
2. **语义统一**：把 gripper、camera topic、task 和 serial 转换成同一合同；
3. **交付治理**：通过 review、rig allowlist、标定、配额、batch、timeout 和 migration 控制交付质量及恢复过程。

最重要的设计原则是：**源数据不改，交付副本可重建；无法确认语义时不猜；所有对象上传成功后才写数据库状态。**
