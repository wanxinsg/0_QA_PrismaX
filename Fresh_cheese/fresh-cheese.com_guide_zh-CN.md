# Ingestion WebUI — 操作员指南

> 内部资料 · fresh-cheese.com  
> 本指南说明 WebUI 的日常操作方式，以及如何在节点上使用 Claude Code 回答 UI 无法处理的问题。  
> 原文最后更新：2026 年 9 月 14 日。

## 目录

1. [每日检查](#每日检查)
2. [GUI 面板](#gui-面板)
3. [Review](#review)
4. [Suppliers](#suppliers)
5. [Customers](#customers)
6. [Tasks](#tasks)
7. [Jobs](#jobs)
8. [Storage](#storage)
9. [Agent](#agent)
10. [如何向 Claude 询问数据](#如何向-claude-询问数据)
11. [数据库 Schema](#数据库-schema)

---

## 每日检查

每天按以下顺序执行：

1. 打开 [Jobs](#jobs) 面板，确认**所有自动任务（auto-job）均为 ON**。自动任务一旦失败就会被关闭，并会一直保持关闭状态，直到有人手动重新开启。
2. 检查同一面板中的 Failures 区域，确保其中**没有任何失败记录**。
3. 快速检查 [Storage](#storage)。磁盘由人工管理，目前容量已接近上限。

---

## GUI 面板

### Review

用于查看和搜索 Episode。

![Review 面板中的 Episode 列表与视频预览](<fresh-cheese.com guide/images/image4.png>)

*Review 面板：Episode 列表与视频预览。*

使用顶部搜索栏搜索 Episode。

![Review 面板顶部的搜索栏](<fresh-cheese.com guide/images/image1.png>)

*搜索栏。*

### Suppliers

这里可以查看有用的供应商信息。

> **注意**  
> 此面板中的通过、失败和配额数字并不总是准确。只能将其视为粗略参考；如需真实数字，请使用 [Claude Code](#如何向-claude-询问数据) 查询。

![Suppliers 面板](<fresh-cheese.com guide/images/image9.png>)

*Suppliers 面板。*

### Customers

履约配额的准确性完全取决于这里录入的数据是否准确。

> **常见问题**  
> **交付数量不会超过配额。**如果某个客户的工时看起来不足，在认定数据缺失之前，先检查此面板中的配额；需要时在这里修改。

![显示履约配额的 Customers 面板](<fresh-cheese.com guide/images/image10.png>)

*Customers 面板。*

### Tasks

在这里新增和编辑 Task。

![Task 管理面板](<fresh-cheese.com guide/images/image13.png>)

*Tasks 面板。*

### Jobs

转换、处理和上传工作都在这里管理。

![Jobs 面板](<fresh-cheese.com guide/images/image12.png>)

*Jobs 面板。*

#### 队列

可以调度 Job；系统会根据可用资源依次运行它们。

**取消机制比较特殊：**系统会先等待当前运行 Job 中正在执行的 Task 完成，然后才取消。

![Job 队列](<fresh-cheese.com guide/images/image3.png>)

*Job 队列。*

#### 自动任务

> **不要编辑这些任务。**  
> 但是必须每天登录并确认它们全部处于 **ON** 状态。自动任务失败后会被取消，必须手动重新开启。

![带开关的自动任务列表](<fresh-cheese.com guide/images/image6.png>)

*自动任务列表。*

#### Failures

确保此区域没有失败记录。

![Job Failures 区域](<fresh-cheese.com guide/images/image5.png>)

*Failures 区域。*

### Storage

此页签非常重要：Storage 由人工管理，当前容量已经相当紧张。

![Storage 页签](<fresh-cheese.com guide/images/image11.png>)

*Storage 页签。*

下面的区域用于选择上传 API 将文件写入三个磁盘中的哪一个。

![当前写入磁盘选择器](<fresh-cheese.com guide/images/image2.png>)

*活动磁盘选择器。*

#### 释放空间

此面板通过删除文件释放空间。当前磁盘已满时：

1. 找到可回收空间最多的磁盘。
2. 删除不需要的文件。将 **Canary limit** 设置为较大的值（例如 `9999`），即可删除全部允许删除的文件。
3. 将该磁盘设置为活动磁盘。

![包含 Canary limit 的存储回收面板](<fresh-cheese.com guide/images/image7.png>)

*存储回收面板。*

---

## Agent

WebUI 用于抽查数据和管理 Job。**任何分析类问题——工时、开票数字、审计、缺失 Episode——都应在节点上使用 Claude Code。**

### 登录节点

通过 SSH 登录节点：

```bash
ssh administrator@fresh-cheese.com
```

密码：`[敏感凭据已省略，请从授权密码管理器获取]`

进入项目目录并启动 Claude：

```bash
cd /sdb-disk/data_ingestion
claude --dangerously-skip-permissions
```

> `--dangerously-skip-permissions` 会跳过权限确认，只应在已授权、受控的节点和明确的工作范围内使用。

![终端中启动 Claude Code](<fresh-cheese.com guide/images/image8.png>)

*在项目目录中启动 Claude Code。*

### 必须说明的一件事

进入后，建议使用 `/resume` 恢复旧会话。否则，请在第一条提示中写明：

> We are on webui v2 and database v2

目前只需要这一句。旧代码库和旧数据库尚未删除，如果不说明，Claude 有时会选错数据库。

---

## 如何向 Claude 询问数据

使用自然语言提问即可。Claude 会通过 `psql` 直接查询生产数据库，并读取 `AGENTS.md`（其中记录了系统的工作规则）。因此，它计算工时的方式与 Customers 页签一致，同时还能按任意维度拆分结果。它也可以打开原始 MCAP 和视频，而 UI 无法完成这些工作。

### 可以询问什么

#### 交付和开票数字

> How many hours of Block manipulation and Biology Lab were delivered to Luma and not marked as FAIL?  
> 有多少小时的 Block manipulation 和 Biology Lab 已交付给 Luma，并且没有被标记为 FAIL？

> What are the total hours from yun for the Block manipulation task? Break down total hours, delivered hours to Luma, accepted hours, and undelivered.  
> yun 的 Block manipulation Task 总共有多少小时？请拆分为总工时、已交付给 Luma 的工时、已接受工时和未交付工时。

要求提供**明细拆分**而不是单个数字，才能得到可用于开票的表格，同时也能暴露卡住但尚未交付的 Episode。

#### 列表和电子表格

> Can you pull a CSV of all the uploaded episode_id, original mcap filename, and lengths for yun Block manipulation tasks?  
> 请导出 yun 的 Block manipulation Task 中所有已上传 Episode 的 `episode_id`、原始 MCAP 文件名和时长 CSV。

**必须说明文件保存位置**，例如：“put it in `user_files/`”。否则文件会落在之后可能被清理的临时目录中。

#### 缺失或标签错误的 Episode

> Why were the other 118 not delivered?  
> 为什么另外 118 条没有交付？

> Dig around for B-010, C-024 and C-025. Did they get labelled as something else? Did verlet do them?  
> 深入检查 B-010、C-024 和 C-025。它们是否被标成了其他名称？是否由 verlet 完成？

> Help us chase down the mislabelled episodes in episodes.jpg — their labels don't match anything in the task_id column of tasks.xlsx.  
> 帮助排查 `episodes.jpg` 中标签错误的 Episode；它们的标签与 `tasks.xlsx` 的 `task_id` 列均不匹配。

Claude 可以从每个 Episode 的 MCAP 中读取 Task 名称，因此能够判断“Episode 是缺失、重命名还是失败”。仅查询数据库无法回答这个问题。也可以直接给它截图或电子表格进行分析。

#### 媒体问题

> I think some of the Block manipulation episodes were overexposed. Inspect the L2 for good episodes, then pull the RAW back from the cloud.  
> 我怀疑部分 Block manipulation Episode 过曝。先检查 L2 找出正常 Episode，再从云端取回 RAW。

### 如何提出一个好问题

- **明确供应商、Task 和客户**，例如 `yun`、`Block manipulation`、`Luma`。不同供应商使用的 Task 名可能不同，否则 Claude 会要求补充信息。
- **明确所说的工时类型。**录制工时、交付工时和接受工时是三个不同数字，三者之间的差异通常最值得调查。
- **结果看起来不对时要质疑。**例如：“I feel like this is still not right — isn't the subtask description in serial_number?” 上周正是这句话修正了标签审计。Claude 会重新检查，而不是坚持原答案。
- 任何将用于开票的结果，都要**要求展示查询语句**。

### 对答案做合理性检查

| 检查项 | 原因 |
| --- | --- |
| “Accepted” 不等于 “passed” | Luma 几乎没有将数据标记为 PASS，大多数已交付 Episode 仍是 PENDING。“Accepted”实际表示“尚未被拒绝”，该数字之后可能下降。 |
| 谁的 FAIL？ | 内部 Review 状态与客户结论是不同字段，而且经常不一致。“Not FAIL”含义不明确，必须说明是谁判定的。 |
| FAIL 和 DUPLICATE 默认排除 | 大多数交付统计默认排除这两类；如需计入，必须明确提出。 |
| 工时不足可能是配额导致 | 交付达到客户请求工时后会停止。认定数据缺失前，先检查 [Customers](#customers) 面板。 |

### 要求 Claude 修改内容时

- **批量或破坏性操作必须分阶段执行：**dry run → 小规模 canary → 完整执行。如果 Claude 没有主动提出，应明确要求，并仔细阅读 dry run 结果。
- **代码修复后必须重启服务。**Job 运行在 WebUI 进程中，只编辑文件不会立即生效。需要明确要求：“restart the webui so it picks up the fix”。
- **长时间任务要后台运行。**重新上传和扫描可能持续数小时；Claude 会将其置于后台并汇报进度。可以关闭会话，之后使用 `/resume` 恢复。

---

## 数据库 Schema

这是生产 PostgreSQL 数据库 `staging`，即 WebUI 使用的 “database v2”。行数统计截至 2026 年 9 月 14 日。无需亲自编写 SQL，因为 Claude 会代写。本节用于了解提问时应使用哪些术语，以及帮助理解 Claude 展示的查询。

### 首先要知道的四件事

1. **时间使用 Unix 秒：**例如 `upload_time`、`customer_upload_time`、`*_at`，使用 `to_timestamp(…)` 阅读。
2. **工时来自 `episodes.length_seconds`：**求和后除以 3600。尚未完成后处理的 Episode 没有时长。
3. **存在两种结论：**`episodes.review_status` 是内部结论；`customer_statuses.customer_task_status` 是客户结论，两者经常不一致。
4. **“已交付给客户”表示该 Episode 与客户之间存在 `customer_statuses` 记录，并且设置了 `customer_upload_time`。**客户 2 是 Scale AI，客户 3 是 Luma。

### 表之间的关系

```text
episodes ─┬─ files                 on staging_id
          ├─ episode_products      on staging_id
          ├─ customer_statuses ─── customers              on customer_id
          └─ tasks ────────────┬── customer_task_hours    on task_name（客户配额）
                               └── supplier_task_hours    on task_name

job_queue ─┬─ job_runs         on queue_id
           ├─ scheduled_jobs   on schedule_key = key
           └─ auto_rules       on rule_key = key
```

### 示例：已交付给 Luma 且未被 Luma 判定失败的工时

```sql
SELECT e.task_name, e.supplier,
       COUNT(*) AS episodes,
       ROUND((SUM(e.length_seconds) / 3600)::numeric, 2) AS hours
FROM customer_statuses cs
JOIN episodes e USING (staging_id)
WHERE cs.customer_id = 3                    -- Luma
  AND cs.customer_upload_time IS NOT NULL   -- 已交付
  AND cs.customer_task_status <> 'FAIL'     -- 未被 Luma 拒绝
GROUP BY 1, 2
ORDER BY 1, 2;
```

如需同时排除被**内部**拒绝的 Episode，增加：

```sql
AND e.review_status NOT IN ('FAIL', 'DUPLICATE')
```

### Episodes 与文件

#### `episodes`（43,070 行）

每个已录制 Episode 一行；几乎所有查询都从这里开始。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `staging_id` | bigint · 主键 | 全系统使用的 Episode ID，包括 UI、CSV 和 `gs://…/<staging_id>/` 路径。 |
| `upload_time` | float | 到达时间，Unix 秒；使用 `to_timestamp(upload_time)`。 |
| `upload_id` | int | 供应商上传批次（目前 428 个），不是客户交付批次。 |
| `uploader_identity` | text | 上传账号；按供应商统计时应使用 `supplier`。 |
| `robot_type` | text | `yam`、`piperx` 或 `ego`；配额按 Task 和 Robot Type设置。 |
| `task_name` | text | 精确 Task 名称，与 `tasks.task_name` 对应。 |
| `internal_comment` | text | 内部审核备注；自动摄取失败也会写入此字段。 |
| `review_status` | text | 内部结论：`PENDING`、`PASS`、`FAIL`、`DUPLICATE`；与客户结论分开。 |
| `length_seconds` | float | 时长；后处理测量前为 NULL。工时=`SUM(length_seconds)/3600`。 |
| `total_size_bytes` | bigint | Episode 文件大小总和；磁盘空间问题优先查询 `episode_products`。 |
| `mistakes` | text (JSON) | 审核者标记的错误时间戳列表；`'[]'` 表示没有。 |
| `idempotency_key` | text | 防止上传重试产生重复 Episode。 |
| `supplier` | text | 采集方：`verlet`、`yun` 或 `zhu`；供应商统计必须使用此字段。 |
| `episode_format` | text | 原始格式：`svo2` 或 `mp4`；Luma 对两者的交付处理不同。 |
| `vla_task_id` | text | VLA Foundry 上传 ID；NULL 表示尚未发送，Foundry 是内部阶段。 |
| `vla_score` | float | Foundry 质量分；目前所有 Episode 均为空。 |
| `vla_upload_batch_id` | int | Foundry 上传批次。 |
| `vla_upload_time` | float | 发送到 Foundry 的时间，Unix 秒。 |
| `vla_comment` | text | 未使用。 |
| `episode_type` | text | 头戴相机 ego 录制为 `ego`，其他为空。 |
| `episode_meta` | text | 实际保存 yun 的子任务序列号；Episodes 搜索栏会搜索此字段。 |

#### `files`（621,748 行）

每个 Episode 文件一行，一个 Episode 通常包含多个文件。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | bigint · 主键 | 文件 ID。 |
| `staging_id` | bigint | 所属 Episode。 |
| `kind` | text | `raw`、`mcap`、`video_l1`、`video_l2`、`graph_l2` 或 `metadata`。 |
| `path` | text | 本地绝对路径；本地文件删除后记录仍保留，因此该字段不证明文件存在。 |
| `size_bytes` | bigint | NULL 表示本地副本已回收。 |
| `original_name` | text | 供应商上传的原始文件名。 |
| `cloud_url` | text | RAW 镜像位置；`prismax-raw-svo2-prod` 可由 Scale AI读取，ego 媒体进入 S3；NULL 表示仅在本地。 |
| `storage_root` | text | `/sdb-disk`、`/extra-disk` 或 `/extra_disk_2`。 |

#### `episode_products`（42,606 行）

由系统自动维护的每 Episode 文件汇总，是回答“磁盘上有哪些文件”的最快入口。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `staging_id` | bigint · 主键 | Episode ID。 |
| `raw_n` / `raw_local_n` / `raw_cloud_n` | int | RAW 总数、本地数、云端镜像数；总数等于云端数时表示完整备份。 |
| `raw_convertible_n` | int | 可由后处理转换的本地 RAW；大于 0 且无 L2 表示等待处理。 |
| `raw_needs_mcap_n` | int | 应生成 MCAP 的 RAW 数，ego 上传除外。 |
| `l1_n` / `l1_local_n` / `l2_n` / `mcap_n` / `graph_n` / `meta_n` | int | 各类产物数量。 |
| `raw_bytes` / `l1_bytes` / `l2_bytes` / `total_bytes` | bigint | 仍在本地磁盘的字节数；已回收文件按 0 计算。 |
| `has_alias` | bool | MP4 rig 中 RAW `.mp4` 同时是 L1；删除 RAW 也会删除 L1。 |
| `raw_path` | text | 示例 RAW 路径，可用于判断 Episode 所在磁盘。 |

#### `ego_media_hashes`（1,241 行）

每个已摄取 ego 视频的指纹，用于阻止相同内容以新文件名重复上传。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `sha256` | text · 主键 | 文件内容哈希。 |
| `staging_id` | bigint | 已经保存该录制内容的 Episode。 |

### 客户、Tasks 与配额

#### `customers`（2 行）

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `customer_id` | int · 主键 | **2 = Scale AI，3 = Luma；不存在 1。** |
| `name` | text | 客户名称。 |

#### `customer_statuses`（29,879 行）

每条向客户交付的 Episode 对应一行。**没有记录表示未向该客户交付。**

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | bigint · 主键 | 记录 ID。 |
| `staging_id` | bigint | Episode。 |
| `customer_id` | int | 2=Scale AI，3=Luma。 |
| `customer_task_id` | text | 客户自己的 Episode ID；Luma 始终为 NULL。 |
| `customer_task_status` | text | 客户结论：`PENDING`、`PASS`、`FAIL`、`DUPLICATE`。Luma 的 accepted 实际表示 not FAIL。 |
| `customer_upload_batch_id` | int | 按客户累计的交付批次号。 |
| `customer_upload_time` | float | 交付时间，Unix 秒；交付统计要求此字段非空。 |
| `customer_comment` | text | 客户拒绝原因或内部备注。 |

#### `customer_task_hours`（39 行）

客户配额。交付达到客户对某个 Task 的请求工时后停止；Customers 面板编辑的就是此表。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `task_name` | text · 主键组成 | Task。 |
| `customer_id` | int · 主键组成 | 客户。 |
| `robot_type` | text · 主键组成 | Robot Type；配额作用于一个 Task 和一个 Robot Type。 |
| `requested_hours` | float | 客户请求工时。 |

#### `tasks`（105 行）

Tasks 面板维护的 Task 主列表。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `task_name` | text · 主键 | 规范名称；重命名会同步更新两个配额表。 |
| `description` | text | 详细说明，目前只有 15 个 Task有值。 |
| `sort_order` | int | 展示顺序。 |

#### `supplier_task_hours`（1 行）

向供应商请求的采集工时，与客户配额使用相同键，目前很少使用。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `task_name` / `supplier` / `robot_type` | text · 联合主键 | Task、供应商和 Robot Type。 |
| `requested_hours` | float | 请求工时。 |

#### `delivery_orders`（0 行）

用于表达“在截止日期前，由供应商 S 交付 Task T 的 N 小时数据”。该表已存在但尚未使用。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | bigint · 主键 | Order ID。 |
| `customer_id` / `supplier` / `task_name` / `robot_type` | — | 交付对象和内容。 |
| `hours_requested` / `hours_delivered` | float | Order 进度。 |
| `deadline` | float | Unix 秒；有截止日期的 Order优先级更高。 |
| `state` / `note` / `paused_until` / `created_at` / `updated_at` | — | 状态及审计字段。 |

### Jobs

#### `job_runs`（4,082 行）

每次 Job运行一行并保存结果；查询“什么失败了”应从这里开始。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | bigint · 主键 | Run ID。 |
| `queue_id` | bigint | 触发本次运行的 `job_queue.id`。 |
| `kind` | text | `postprocess`、`upload_luma`、`upload_scale`、`upload_vla`、`mirror_raw`、各种 ingest 等。 |
| `params` | text (JSON) | 作用范围，例如 supplier和 task_name。 |
| `origin` | text | `manual`、`auto` 或 `scheduled`。 |
| `status` | text | `running`、`done`、`failed`、`cancelled` 或服务重启造成的 `interrupted`。 |
| `started_at` / `finished_at` | float | Unix 秒。 |
| `episodes_total` / `episodes_done` / `episodes_failed` | int | 进度计数。 |
| `dry_run` | bool | true 表示只记录原本会执行的操作。 |
| `error` / `log_tail` | text | 错误信息和日志尾部。 |
| `summary` | text (JSON) | Job结束报告。 |

#### `job_queue`（4,014 行）

所有进入队列的 Job，无论是否已运行。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | bigint · 主键 | Queue ID。 |
| `kind` / `params` | — | 与 `job_runs` 中含义一致。 |
| `resources` | text | 所需 `cpu`、`gpu`、`upload`、`download` 资源；全部可用后才启动。 |
| `priority` | int | UI 中的星级。 |
| `state` | text | `queued`、`running`、`done`、`failed` 或 `cancelled`。 |
| `run_window` | text | `any` 或 `idle`；后者只能在太平洋时间 23:00–09:00运行。 |
| `origin` / `requested_by` / `note` | text | 谁因为什么请求了 Job。 |
| `schedule_key` / `rule_key` / `order_id` | — | 对应的定时任务、自动规则或 Delivery Order。 |
| `deadline` / `created_at` / `started_at` / `finished_at` | float | Unix 秒。 |

#### `scheduled_jobs`（5 行）

每天固定时间运行的 Job，例如 08:00 的 Luma postprocess→deliver 组合，以及 23:30 的 verlet Biology Lab ingest。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `key` | text · 唯一 | 例如 `luma-block-yun-deliver`。 |
| `kind` / `params` / `label` / `note` | — | 执行内容与数据范围。 |
| `hour` / `minute` | int | 太平洋时间。 |
| `after_key` | text | 等待另一个定时 Job完成。 |
| `enabled` | bool | 是否开启。 |
| `consecutive_failures` / `paused_until` | — | 失败后依次退避 5分钟、15分钟，最长 6小时；非零失败数需要检查。 |
| `ignore_window` / `preempt_auto` | bool | 是否可越过 idle窗口，以及是否要求自动任务让出资源。 |
| `last_fired_day` / `priority` / `created_at` / `updated_at` | — | 调度记录。 |

#### `auto_rules`（3 行）

持续推动处理流程的规则：`postprocess-arrivals`、`mirror-raw-nightly` 和 `foundry-nightly`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `key` / `kind` / `params` / `label` / `note` | — | 规则排入队列的内容。 |
| `run_window` | text | `any` 或 `idle`。 |
| `max_batch` | int | 单次最多排入数量；0 表示无限制。 |
| `enabled` / `priority` | — | 是否开启及优先级。 |
| `consecutive_failures` / `paused_until` / `last_queued_at` | — | 与定时 Job相同的退避和记录字段。 |

#### `job_state`（8 行）

旧 WebUI v1 留下的 Job快照，忽略此表。

### Download API 与设置

#### `download_api_keys`（2 行）

外部 Download API的 Key；数据库只保存 Key哈希。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` / `label` / `prefix` / `enabled` / `created_at` / `last_used_at` | — | `prefix` 是 Key前几位，用于区分不同 Key。 |
| `key_hash` | text | Key的 SHA-256；不保存原始 Key。 |

#### `download_sessions`（2 行）

每次 Download Client运行对应一个 Session，记录客户端已经下载的内容。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` / `key_id` / `label` / `created_at` / `last_used_at` | — | Session元数据。 |

#### `download_session_episodes`（6,229 行）

Session 已完整下载的 Episode；只有全部文件到达后才会出现。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session_id` / `staging_id` | 联合主键 | Session与 Episode。 |
| `state` / `bytes` / `length_seconds` / `recorded_at` | — | 下载状态、大小、时长和记录时间。 |

#### `download_session_files`（38,059 行）

逐文件下载回执。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `session_id` / `file_id` | 联合主键 | Session与文件。 |
| `staging_id` / `bytes` / `recorded_at` | — | Episode、字节数和记录时间。 |

#### `settings`（6 行）

服务 Key/Value 设置。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `key` / `value` | text | `active_data_root` 是新上传写入磁盘；`webui2.service` 记录运行中的服务；其他为内部标记。 |

