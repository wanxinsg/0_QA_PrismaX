# PRIS-374 上传归属回填：Commit 逻辑分析

> 分析日期：2026-10-12（UTC+8）  
> 仓库：`app-prismax-rp-backend`  
> Commit：`aa08cdf653cd4bd3102650c9d346c25c0a3f6d70`  
> 作者：Aparna Rangamani `<aparna@prismax.ai>`  
> 提交时间：2026-10-09 00:23:22 `-0700`（北京时间 2026-10-09 15:23）  
> 说明：`PRIS-374: save code for reference`  
> 本地 `testing` HEAD 当时是 `a8a968e`。该 commit 没有父提交，不在当前分支上，需要按 hash 单独取出。

---

## 1. 这个 commit 是什么

这是一份**没有父提交的代码快照**，用来把当时的后端代码和一套一次性回填脚本存档。它不是对线上服务的增量改动，也不提供新的 HTTP 接口。

| 项目 | 值 |
| --- | --- |
| 父提交 | 无 |
| 规模 | 245 个文件，68098 行新增 |
| 与 PRIS-374 直接相关的代码 | `app_prismax_data_pipeline/temp/pris_374_backfill_jobs/` |
| 其余内容 | data pipeline、data worker、preview worker、user management、forum、hex、tele-op 等目录的整包拷贝，外加 `.idea`、`__pycache__`、`.DS_Store` |

回填脚本是离线命令行工具。人工按顺序跑完后，只改 `data_uploads.user_id` 和 `data_uploads.job_id`。`task_id`、episode 状态、GCS 对象、QA 分数都不动。

脚本目录的 `.gitignore` 忽略 `output/`、`input/`、`__pycache__/`。扫描结果、匹配表、分配计划和回滚备份都落在本地 `output/`，不会进 git。表格默认路径是同目录 `input/backfill-data-raw.xlsx`。

依赖：pipeline 自己的运行环境，外加 `openpyxl`（读 xlsx）。脚本通过 `import app` 连库，导入时会读 data pipeline 的数据库配置。

---

## 2. 业务目标

把用户 `1676140`、任务 `131` 名下的一批上传，按表格里的第三方编号 `BIO-NEW-<数字>` 对上 episode，再整条 upload 划给用户 `1713449` 的两个 job：

| 表格 sheet 名前缀 | 目标 `job_id` |
| --- | --- |
| `luma_171` | 36 |
| `luma_200` | 37 |

编号不在数据库字段里，而在每条 episode 原始 MCAP 的 ROS topic `/task_info` 里。所以脚本先从 GCS 把这段 payload 读出来，再和表格对。

已知对照样本（供应商用户 `1665748`，只用于校验读取器，不参与默认扫描）：

| episode_id | upload_id | 期望 `serial_number` |
| --- | --- | --- |
| 88715 | 2058 | `BIO-NEW-171` |
| 88761 | 2061 | `BIO-NEW-172` |

---

## 3. 数据流

```text
data_episodes + data_uploads          GCS 原始 MCAP
user_id=1676140, task_id=131          /task_info（最多 20 条）
        │                                      │
        └──────── scan_episodes.py ────────────┘
                         │
                         ▼
              output/<run>/episode_scan.csv
                         │
                         │  + input/backfill-data-raw.xlsx
                         ▼
              match_spreadsheet.py
                         │
                         ▼
         matches.csv / upload_summary.csv / spreadsheet_codes.csv
         hours_check.csv / unmatched / code_summary / ...
                         │
                         ▼
              assign_jobs.py plan          只写 CSV 和 summary.json
                         │
                         ▼
              assign_jobs.py apply         先写 revert_backup，再 UPDATE
                         │
                         ▼
              data_uploads.user_id = 1713449
              data_uploads.job_id  = 36 或 37
```

建议执行顺序：

```text
python check_known_pairs.py
python scan_episodes.py --run-name full
python match_spreadsheet.py --run-name full
python assign_jobs.py plan --run-name full
python assign_jobs.py apply --run-name full
```

`check_upload_vs_episode.py` 与主流程并行，用来看同一个 upload 里的 `serial_number` 是否一致，不产生分配输入。

---

## 4. 编号怎么认

正则（大小写不敏感）：

```text
(?<![A-Za-z0-9])BIO[-_ ]?NEW[-_ ]?0*(\d+)(?!\d)
```

归一成 `BIO-NEW-<整数>`。`BIO-NEW-171`、`BIO_NEW_0171`、`bio new 171` 都是 `BIO-NEW-171`。前后紧贴字母或数字的片段不算。

`match_spreadsheet.py` 会遍历 payload JSON 里的**每一个字符串字段**。  
`check_known_pairs.py` 和 `check_upload_vs_episode.py` 只看 JSON 顶层的 `serial_number`。

因此会出现：读取器认为 serial 正确，但匹配脚本在别的字段里又扫到第二个编号；或者 serial 字段为空，编号却写在别的字段里，匹配仍能命中。

每条 MCAP 最多解码 20 条 `/task_info`。第 21 条及之后的编号不会进入扫描结果。

读取方式是 GCS range 请求（1MB 一块，缓存 32 块），按 MCAP 索引只拉 `/task_info`，不整文件下载。

---

## 5. 阶段一：扫描 `scan_episodes.py`

从库里取出：

```sql
SELECT u.user_id, e.episode_id, e.upload_id, e.status,
       e.raw_bucket, e.raw_mcap_path, e.video_duration_hours, e.created_at
FROM data_episodes e
JOIN data_uploads u ON u.upload_id = e.upload_id
WHERE u.user_id IN :user_ids
  AND u.task_id = :task_id
```

默认 `--user-ids 1676140`，`--task-id 131`，`--workers 3`。注释里把 `1665748` 标成备用供应商，需要显式传入才会扫。

状态过滤默认丢掉 `DERIVED_VALIDATION_FAILED` 和 `FAILED`。传 `--exclude-statuses ''` 则一条都不丢。被丢掉的 episode 仍会在 CSV 里记一行，`scan_outcome=excluded_status`，不再读 GCS。

可读结果：

| `scan_outcome` | 含义 |
| --- | --- |
| `ok` | 读到至少一条 `/task_info` |
| `blob_not_found` | GCS 上没有这个对象 |
| `no_mcap_path` | `raw_mcap_path` 为空 |
| `no_task_info` | 文件在，topic 上没有消息 |
| `error` | MCAP / GCS / worker 其它失败 |
| `excluded_status` | 状态在排除列表里 |

CSV 是追加写的。同一个 `episode_id` 已有记录就跳过；`--retry-errors` 会重读上一次结果不是 `ok` 的 episode。中断（Ctrl+C）后已写入的行保留，用同一 `--run-name` 再跑即可续上。匹配阶段对每个 `episode_id` 只取 CSV 里的最后一行。

可选缩小范围：`--upload-ids`、`--limit-uploads`、`--max-episodes-per-upload`（每个 upload 均匀抽 N 条，含首尾）。抽查结果不能拿去 `apply`，因为没扫到的 episode 会被当成“未匹配”，整条 upload 仍可能被划走，extra 时长会被放大。

---

## 6. 阶段二：对表 `match_spreadsheet.py`

离线，不再访问数据库和 GCS。输入是 `episode_scan.csv` 和表格。

表格要求：

- xlsx：每个 sheet 有 `code` 列，可选 `hours`。没有 `code` 列的 sheet 跳过并打印警告。
- csv：列 `sheet,code,hours`。

同一 `code` 在全表出现多次，或在同一 sheet 出现多次，都标 `duplicate_in_spreadsheet=true`。

一条 episode（`scan_outcome=ok`，且状态不在排除列表）里出现的每个表格编号，都会产生匹配行。一个编号同时出现在两张 sheet 上时，这条 episode 会各记一行，upload 随后会被看成冲突。

一条 episode 里有多个不同 `BIO-NEW` 编号时，每个编号单独匹配，并标 `ambiguous=true`。

对不上的原因：

| reason | 条件 |
| --- | --- |
| `scan_<outcome>` | 扫描不是 `ok` |
| `no_bio_new_code` | 读到了 payload，里面没有 `BIO-NEW` |
| `code_not_in_spreadsheet` | 有编号，但表格里没有 |

编号级汇总标志：

| flag | 条件 |
| --- | --- |
| `MULTI_UPLOAD` | 同一个表格编号命中了多个 upload |
| `AMBIGUOUS_EPISODES` | 命中的 episode 里还有别的编号 |
| `DUPLICATE_IN_SPREADSHEET` | 表格里该编号重复 |
| `UNPARSED_CODE` | 单元格对不上 `BIO-NEW` 正则，按原文保留 |
| `UNREADABLE_EPISODES_EXIST` | 这个编号没匹配上，且本次扫描里存在读失败的 episode |

时长核对只写报告，不参与能不能分配。默认相对容差 10%（`--hours-tolerance 0.10`）：

| verdict | 条件 |
| --- | --- |
| `NO_MATCH` | 本次扫描里没有 episode |
| `NO_SHEET_HOURS` | 表格小时为空或 0 |
| `NO_DURATION` | 命中了，但 episode 时长都空 |
| `OK` | `abs(视频时长合计 / 表格小时 - 1) <= 0.10` |
| `UNDER` / `OVER` | 超出容差，偏低或偏高 |

`NOT_FOUND` 的含义是：**这次扫描到的 episode 里没有**。没扫到的 upload、被状态过滤掉的 episode、第 21 条之后的消息，都不会被算进去。

写出的表：`spreadsheet_codes.csv`、`episode_codes.csv`、`matches.csv`、`code_summary.csv`、`hours_check.csv`、`unmatched_episodes.csv`、`excluded_episodes.csv`、`upload_summary.csv`。`--export-xlsx` 再合并成 `backfill_results.xlsx`。

`assign_jobs.py` 实际只读三份：`matches.csv`、`upload_summary.csv`、`spreadsheet_codes.csv`。`episode_scan.csv` 只用来给 extra episode 填 `scan_outcome`。

---

## 7. 阶段三：分配 `assign_jobs.py`

默认是 dry-run。`plan` 只出报告；`apply` 才写库，并且要在交互里输入 `APPLY <条数>`，或显式加 `--yes`。非交互终端没有 `--yes` 会直接拒绝。

### 7.1 一张 upload 归哪个 job

对 `matches.csv` 里的每一行，用 sheet 名前缀找到 job，把编号放进该 upload 的 `codes_by_job`。

| 情况 | `target_job` | 写入动作 |
| --- | --- | --- |
| 只命中一个 job | 那个 job | 进入后续用户 / job 判断 |
| 命中多个 job，`--conflicts job37`（默认） | 37，前提是 37 在命中集合里；否则取 job id 升序的第一个 | 仍可能 update |
| 命中多个 job，`--conflicts skip` | 同上，但动作改成 skip，原因 `conflict_left_for_review` | 不写 |

`suggested_job` 按“去掉表格重复编号后，剩余编号更多的 job”排序，只写进 `conflicts.csv`，**apply 不读它**。默认冲突策略下，即使 job 36 的独立编号更多，真正写入的仍是 job 37。

`partial=true` 表示 `n_episodes_matched < n_episodes_scanned`：这个 upload 里还有没对上表格的 episode。partial **不会**阻止分配。更新粒度是整条 upload，这些 episode 会跟着走，时长记在 extra 里。

sheet 对不上任何 `--sheet-job` 前缀时，脚本直接退出，不写计划。默认映射是 `luma_171=36` 和 `luma_200=37`，可用多次 `--sheet-job PREFIX=JOB_ID` 覆盖。

### 7.2 要不要更新这一行

读当前行：`SELECT upload_id, user_id, job_id, task_id FROM data_uploads WHERE upload_id IN (...)`。

按下面顺序只取第一条：

| 顺序 | 条件 | action | reason |
| --- | --- | --- | --- |
| 1 | 库里没有这条 upload | `skip` | `not_in_db` |
| 2 | 冲突且 `--conflicts skip` | `skip` | `conflict_left_for_review` |
| 3 | 已经是目标用户 **并且** 已经是目标 job | `already_applied` | 空 |
| 4 | 当前用户不是 `from_user`（默认 1676140） | `skip` | `user_mismatch` |
| 5 | 已有别的 `job_id`，且没加 `--override-existing-job` | `skip` | `already_in_job_<id>` |
| 6 | 其余 | `update` | 空 |

第 4 条在第 5 条前面。upload 已经在目标用户名下、但 job 不对或 job 为空时，原因是 `user_mismatch`。`--override-existing-job` 解决不了这种情况，它只放行“人还是原用户、job 已经是别的 id”。

`task_id` 只出现在计划 CSV 里，UPDATE 不改它。

### 7.3 写库前要先过的检查

对每个目标 job：

- job 不存在，或 `deleted_at` 已填：算 **problem**，计划照写，但 `plan` / `apply` 在写库前退出。
- `data_jobs.assigned_user_id` 不是目标用户：默认是 problem。加 `--allow-job-owner-mismatch` 后降级为 warning，可以继续。
- `users` 表里没有目标用户：只是 warning，不阻断。

时长用 `app.jobs_helper.JOB_FAILED_STATUSES` 排除失败 episode 后汇总。若这个集合和扫描用的 `DERIVED_VALIDATION_FAILED, FAILED` 不一致，记一条 warning。

每个目标 job 的报告里同时给出：

- 表格小时合计
- 已匹配 episode 的 CSV 时长
- 这些 upload 在库里的全部有效 episode 时长（含没对上编号的）
- extra：划走的 upload 里、不在匹配 episode 集合中、且状态不算失败的时长、条数、涉及 upload 数、占该 job 计划时长的百分比
- 失败且未匹配的 episode：单列，不计入 extra 小时
- 其中来自冲突 upload 的库内时长
- 该 job 现在的时长，以及 apply 之后的预计时长（现在的时长 + 本次 `update` 那些 upload 的时长；`already_applied` 已经在“现在”里，不重复加）

另外三条一致性 warning：匹配 episode 在库里找不到；CSV 时长和库里同时长相差超过 0.05 小时；逐条相加和聚合 SQL 相差超过 0.01 小时。warning 不阻断 apply。

计划文件在 `output/<run>/job_assignment/`：

| 文件 | 内容 |
| --- | --- |
| `assignment_plan.csv` | 每条 upload 的动作、当前/目标用户和 job |
| `conflicts.csv` | 默认 job、建议 job、各 job 的独立编号数 |
| `partial_uploads.csv` | 扫描条数、匹配条数、未匹配条数、extra |
| `skipped_uploads.csv` | skip 原因 |
| `extra_episodes.csv` | 会跟着 upload 走、但没对上表格的 episode |
| `summary.json` | 上面的汇总、problems、warnings、库实例名 |

### 7.4 apply 怎么写

1. 再跑一遍和 `plan` 相同的计算。problems 非空则退出。
2. 没有 `action=update` 的行则结束。
3. 确认文案通过后，先把备份 CSV `fsync` 到磁盘：`revert_backup_<UTC时间>.csv`，字段是 `upload_id, old_user_id, old_job_id, new_user_id, new_job_id, applied_at`。
4. 开事务。`SELECT ... FOR UPDATE` 锁住待改 upload。
5. 按目标 job 分组执行：

```sql
UPDATE data_uploads
SET job_id = :new_job, user_id = :new_user
WHERE user_id = :from_user
  AND upload_id IN :ids
  AND (job_id IS NULL OR job_id = :new_job)
```

`--override-existing-job` 时去掉最后的 `job_id` 条件。

6. 任一组的 `rowcount` 不等于这组 upload 数，或者写完后 `user_id` / `job_id` 不是目标值：抛错，事务回滚。备份文件留在磁盘，库没有变化。
7. 提交后重算每个 job 的时长，和计划里的 `expected_hours_after_apply` 并排打印，并写 `apply_<时间>.json`。

episode 没有自己的 `job_id`。job 时长是 `data_uploads.job_id` join `data_episodes` 汇总的，所以 upload 一改，它下面所有未失败 episode 的时长都算进新 job。这就是 extra 的来源。

---

## 8. 回滚 `assign_jobs.py revert`

```text
python assign_jobs.py revert --backup-file <revert_backup.csv>          # 只打印
python assign_jobs.py revert --backup-file <revert_backup.csv> --apply  # 写回
```

对备份里的每一行看当前 `(user_id, job_id)`：

| 当前值 | 处理 |
| --- | --- |
| 等于备份里的新用户、新 job | 恢复成旧用户、旧 job |
| 已经等于旧值 | 跳过，算 already original |
| 两者都不是 | 不动，算 changed since apply，最多打印 20 条 |

恢复 SQL 要求当前仍是备份里的新用户和新 job，写回旧值后再逐条核对。对不上则整笔回滚。确认文案是 `REVERT <条数>`。

回滚只恢复 `user_id` 和 `job_id`。apply 之后如果有人改过 QA、下载或别的列，那些列保持现状；这两列若已再次被改，本行会被留在“changed since apply”。

---

## 9. 两个检查脚本

### 9.1 `check_known_pairs.py`

无参数。按写死的两个 episode 读 GCS，核对 `upload_id`、`serial_number`、读取错误。任一失败则进程退出码 1。

`user_id == 1665748` 只打印 `user_1665748_match`，**不计入失败**。人已经从 1665748 挪走之后，这个脚本仍可能 PASS。

### 9.2 `check_upload_vs_episode.py`

默认每个 upload 均匀抽 5 条 episode，读 `serial_number`。`--all` 才全读。

| upload verdict | 含义 |
| --- | --- |
| `single_serial` | 抽到的成功样本只有一个 serial |
| `multiple_serials` | 同一个 upload 里出现多个 serial |
| `no_data` | 一条 serial 都没读到 |

另外打印：同一个 serial 出现在多个 upload、单条 MCAP 内部多条 `/task_info` 的 serial 不一致、没有 `serial_number` 的 payload 样例（最多 3 条）、错误类型、下载字节数。

这个脚本的“一个 upload 一个 serial”和主流程的“一个 upload 可以因为多个 `BIO-NEW` 变成冲突”用的不是同一套字段。抽查通过，不代表 `matches.csv` 里没有冲突。

---

## 10. 快照里其余 230 多个文件

按顶层目录计数：

| 目录 | 文件数 | 和这次回填的关系 |
| --- | --- | --- |
| `app_prismax_data_pipeline` | 59 | 含回填脚本；其余是 pipeline 应用、SQL、订阅 / QA 测试的存档 |
| `app_prismax_user_management` | 57 | 存档 |
| `app_prismax_forum` | 30 | 存档，含 `forum.db` |
| `app_prismax_data_worker` | 27 | 存档 |
| `app_prismax_preview_worker` | 24 | 存档 |
| `app_prismax_hex` | 24 | 存档 |
| `app_prismax_tele_op_services` | 8 | 存档 |
| `.idea`、`__pycache__`、`.DS_Store`、根上的构建文件 | 其余 | 本地工程文件，不应进发布 |

这些文件没有相对父提交的 diff。不能把这个 commit 当成“PRIS-374 改了 forum / hex / worker”。发布、回归和测试范围只覆盖 `temp/pris_374_backfill_jobs/` 这 9 个文件，以及它们写入的两列。

---

## 11. 风险

1. **整条 upload 一起走。** 只要有一条 episode 对上表格，同 upload 下没对上的 episode 也会换用户、换 job，并计入新 job 时长。`partial_uploads.csv` 和 `extra_episodes.csv` 是 apply 前必须看的。
2. **冲突默认进 job 37。** `suggested_job` 只是报告。job 36 编号更多时，默认仍写 37。要人工处理就得用 `--conflicts skip`，看完 `conflicts.csv` 再决定，脚本不会按建议 job 自动写。
3. **一个编号出现在两张 sheet 上，会把相关 upload 全部打成冲突。** 因为匹配按“编号 × sheet 行”展开。
4. **抽查扫描不能用于 apply。** `--max-episodes-per-upload` 或 `check_upload_vs_episode` 的 5 条抽样，会把没读到的 episode 算成未匹配。
5. **只扫到前 20 条 `/task_info`。** 编号若在更后面的消息里，这条 episode 会变成 `no_bio_new_code` 或匹配失败。
6. **两套解析。** 检查脚本看 `serial_number`，匹配脚本扫全部字符串。两边结果可以不一致。
7. **`user_mismatch` 比 override 优先。** 已经挂在 `1713449` 上、但 job 不对的行不会被改正，除非先把用户改回 `1676140`。
8. **目标用户不在 `users` 表只是 warning。** job 不存在或已删除才会挡住写入。
9. **时长口径有两套状态列表。** 扫描排除列表写死两个状态；job 时长用运行中的 `JOB_FAILED_STATUSES`。不一致时只警告，小时数仍按后者算。
10. **`NOT_FOUND` 不是全局结论。** 换 `--user-ids`、`--task-id` 或漏扫 upload 后，表格里的编号会显示找不到。
11. **脚本连的是 `app.py` 当前配置的库。** `summary.json` 里有 instance 和 database name。apply 前要用它确认不是连错环境。
12. **这个 commit 本身不能合并当发布。** 它是无父提交的整库快照，里面有 IDE 文件、字节码和 forum 的 sqlite。

---

## 12. 测试要点

下面用脚本的 plan / apply / revert 验证。库操作先在非生产库做；生产上至少先跑 `plan`，核对 `summary.json` 的 database 名称后再决定是否 `apply`。

### 12.1 读取与匹配

| # | 场景 | 期望 |
| --- | --- | --- |
| R1 | `check_known_pairs.py`，两条样本仍在且 MCAP 可读 | 两条 PASS，退出码 0。`serial_number` 分别为 `BIO-NEW-171`、`BIO-NEW-172` |
| R2 | 样本 episode 已不在库 | 该条 FAIL `not found`，退出码 1 |
| R3 | 样本 user 已不是 1665748，但 upload 和 serial 正确 | 仍 PASS，打印 `user_1665748_match=False` |
| R4 | payload 里分别是 `BIO-NEW-171`、`BIO_NEW_0171`、`bio new 171` | 匹配编号都是 `BIO-NEW-171` |
| R5 | 编号前后紧贴字母或数字 | 不抽取 |
| R6 | 编号在 `serial_number` 以外的字段 | `match_spreadsheet` 能命中；`check_upload_vs_episode` 可能是 `no_data` |
| R7 | 同一条 MCAP 里两条 `/task_info` 的 serial 不同 | 检查脚本 `task_info_consistent=false`；匹配脚本两个编号都会留下，episode 标 ambiguous |
| R8 | `/task_info` 超过 20 条，编号只在第 21 条 | 扫描结果里没有这个编号 |
| R9 | `raw_mcap_path` 空、对象不存在、topic 无消息 | outcome 分别是 `no_mcap_path`、`blob_not_found`、`no_task_info`，不进入匹配 |
| R10 | 状态是 `FAILED` 或 `DERIVED_VALIDATION_FAILED` | 默认不读 GCS，CSV 记 `excluded_status` |
| R11 | 同一 `--run-name` 重跑 | 已 `ok` 的 episode 不再下载；`--retry-errors` 只重读非 `ok` |
| R12 | 扫描中断后再跑同一命令 | 已落盘的行保留，剩余 episode 补上 |
| R13 | 表格同一 code 出现两次，或分属 `luma_171` 与 `luma_200` | `duplicate_in_spreadsheet=true`；两张 sheet 都有时，upload 进入冲突 |
| R14 | 一个 code 命中多个 upload | `code_summary` 带 `MULTI_UPLOAD` |
| R15 | 视频时长相对表格小时在 ±10% 内 / 外 | `hours_check` 为 `OK` / `UNDER` 或 `OVER`。两种情况的 upload 都仍可进入分配 |
| R16 | 编号只存在于没扫到的 upload | 该行 `NOT_FOUND`，不能据此断定库里没有数据 |

### 12.2 分配计划

| # | 场景 | 期望 |
| --- | --- | --- |
| A1 | 只命中 `luma_171` | `target_job=36`，`conflict=false` |
| A2 | 只命中 `luma_200` | `target_job=37` |
| A3 | 两张 sheet 都命中，默认 conflicts | `target_job=37`，`conflicts.csv` 有建议 job；建议 job 即使是 36，计划里的目标仍是 37 |
| A4 | 同样冲突，`--conflicts skip` | action=`skip`，reason=`conflict_left_for_review`，不出现在待更新列表 |
| A5 | 当前用户 1676140，`job_id` 空 | action=`update` |
| A6 | 已经是用户 1713449 且 job 正确 | action=`already_applied`，apply 不再 UPDATE 它 |
| A7 | 当前用户既不是 1676140 也不是“1713449 + 目标 job” | `skip` / `user_mismatch`。加上 `--override-existing-job` 仍然 skip |
| A8 | 用户仍是 1676140，但 `job_id` 已是别的 job | 默认 `skip` / `already_in_job_<id>`；加 `--override-existing-job` 后变为 `update`，SQL 不再要求原 job 为空或等于新 job |
| A9 | 匹配 episode 数小于扫描 episode 数 | `partial=true`，action 仍可以是 `update`。extra 小时出现在 summary 和 `extra_episodes.csv` |
| A10 | 未匹配 episode 的状态属于失败列表 | 出现在 extra 列表，`counts_toward_job_hours=false`，不进 extra 小时 |
| A11 | sheet 名没有对应 `--sheet-job` | 进程退出，不生成可执行计划 |
| A12 | 目标 job 不存在或已删除 | summary 里有 problem，`plan` 和 `apply` 都不写库 |
| A13 | job 的 `assigned_user_id` 不是 1713449 | 默认 problem 并中止；`--allow-job-owner-mismatch` 后变成 warning，可以写 |
| A14 | `users` 里没有 1713449 | 只有 warning，不中止 |
| A15 | `JOB_FAILED_STATUSES` 与两个排除状态不同 | warning，小时仍按 `JOB_FAILED_STATUSES` 算 |
| A16 | `plan` | 数据库行不变；`job_assignment/` 下六份文件齐全；summary 里的 database 与当前环境一致 |

### 12.3 写入与回滚

| # | 场景 | 期望 |
| --- | --- | --- |
| W1 | `apply` 不加 `--yes`，且在交互终端 | 先写出备份，再等待输入 `APPLY <N>`。输入错误则退出，库不变 |
| W2 | 非交互且没有 `--yes` | 拒绝写入 |
| W3 | 确认后成功 | 仅 `action=update` 的行变成用户 1713449、对应 job。`task_id` 不变。`already_applied` 和 `skip` 不变 |
| W4 | 更新行数和计划不一致，或写后状态不对 | 事务回滚，库保持原样，备份 CSV 仍在 |
| W5 | apply 之后的 job 时长 | 打印值与 `expected_hours_after_apply` 一致（允许前面 warning 里已经指出的 CSV/DB 差） |
| W6 | 用对应备份 `revert --apply` | 仍保持新用户+新 job 的行回到旧值；已经是旧值的行不动 |
| W7 | apply 之后又有人改了该行的 user 或 job，再 revert | 该行留在 changed since apply，不覆盖 |
| W8 | 用抽查 run（限制了 episode 数）去 apply | 不应执行。partial / extra 会包含所有没被抽到的 episode |

### 12.4 不在本次验证范围

- 快照里的 forum、hex、worker、user management、preview worker
- 任何新 API、页面、SDK
- episode 状态、QA 分数、GCS 文件、下载配额
- 把 `suggested_job` 自动写成最终 job（当前脚本没有这条路径）
