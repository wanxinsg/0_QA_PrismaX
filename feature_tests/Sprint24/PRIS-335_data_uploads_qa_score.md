# PRIS-335 `data_uploads.qa_score`

> 分析日期：2026-09-18  
> 仓库：`app-prismax-rp-backend`（data-pipeline only）  
> Commit：`8aa3666` — *PRIS-335: add qa_score column to db; refactor code*  
> Merge：`de8e83f` PR [#77](https://github.com/PrismaXAI/app-prismax-rp-backend/pull/77) `PRIS-335-refactor-qa-final-score-db`  
> 范围：**仅 backend data-pipeline**。无 frontend / marketing / SDK 变更。UI 仍读原字段，分数来源从实时 median 改为读列。

日汇总见 [`Sep18.md`](./Sep18.md)。本文是 PRIS-335 的完整测试说明。

---

## 1. Feature 描述

终审 QA 分数写入 `data_uploads.qa_score`，读路径不再每次对 `data_qa_sessions` 做 `PERCENTILE_CONT` median。

| 项目 | 旧行为 | 新行为 |
| --- | --- | --- |
| 存储 | 只存在 `data_qa_sessions.qa_score`（按 reviewer / round） | 另存终审分到 `data_uploads.qa_score` |
| Dashboard / QA Review / Jobs | `QA_MEDIAN_SCORE_LATERAL` 每次计算 | `SELECT u.qa_score` |
| 未终审 upload | median 为 NULL | 列保持 NULL |
| helper 位置 | `app_prismax_data_pipeline/qa_helper.py` | `app_prismax_data_pipeline/qa/qa_helper.py` |

**不在本次范围：**

- 不改 QA 打分规则、轮次人数、outlier / median 算法
- 不改 frontend 展示字段名（仍是 `avg_qa_score` / `final_qa_score` 等）
- 不改 marketing、user-management、Upload SDK

---

## 2. Commit 与文件

| 路径 | 变更 |
| --- | --- |
| `sql/20260916_data_uploads_qa_score_column.sql` | `ALTER TABLE data_uploads ADD COLUMN qa_score NUMERIC(5,2)` |
| `qa/backfill_qa_score_column_db_migration.py` | 历史 SUCCEEDED upload 回填；默认 dry-run |
| `qa/qa_helper.py` | 从根目录迁入；终审时 `UPDATE data_uploads.qa_score` |
| `qa/QA_REVIEW_FLOW.md`、`qa/reconcile_qa_round_one.py`、`qa/test_qa_helper.py` | 随 helper 一起搬家 |
| `app.py` | Dashboard / QA Review / Jobs episode 查询改为 `u.qa_score`；import 改为 `qa.qa_helper` |

`QA_MEDIAN_SCORE_LATERAL` 仍留在 helper 里，**只给 backfill 用**。在线查询不再引用。

---

## 3. 业务逻辑

### 3.1 分数口径（未改）

Decisive round 的 `final_quality_score` 仍是该轮 reviewer `qa_score` 的 median（与 `QA_REVIEW_FLOW.md` 第 6 节一致）。

写入时机：某轮成为 decisive round 且算出 `final_quality_score` 后，`_reward_final_decision_qa_points` 执行：

```sql
UPDATE data_uploads
SET qa_score = :qa_score
WHERE upload_id = :upload_id
```

未终审（进行中、FAILED、未进 QA）的行保持 `NULL`。

### 3.2 读路径

| 功能 | 接口 / 函数 | 使用方式 |
| --- | --- | --- |
| Operator Dashboard summary / trend | `_compute_dashboard_summary` | `u.qa_score`；`is not None` 才计入平均分，NULL 不当 0 |
| Operator Dashboard uploads 列表 | `_compute_dashboard_uploads` | 每条 upload 的 `qa_score` |
| Admin QA Review 队列 | `_qa_review_uploads_query` | `u.qa_score AS final_qa_score` |
| Jobs episode 阶段 | `_jobs_episodes_for` → `stage_for_episode` | `qa_score >= 50` 记入 QC 阶段 |

Jobs 阶段规则（本次只换分数来源，阈值未改）：

```text
reported bad        → customer rejected
order accepted      → customer accepted
failed status       → rejected
qa_score >= 50      → QC
ready status        → initial
其他                → 不进入阶段breakdown
```

### 3.3 历史回填

脚本：`app_prismax_data_pipeline/qa/backfill_qa_score_column_db_migration.py`

- 默认 dry-run，必须加 `--apply` 才写库
- 已有 `qa_score` 的行跳过
- 只处理 `REVIEW_FIRST/SECOND/THIRD_ROUND_SUCCEEDED`
- 计算方式与旧 `QA_MEDIAN_SCORE_LATERAL` 相同（最高完成轮次的 reviewer median）
- `--apply` 按 500 行一批
- 支持 `--upload_id` 单条回填

### 3.4 部署顺序（必须按序）

```text
1. 执行 sql/20260916_data_uploads_qa_score_column.sql     # ADD COLUMN
2. 运行 qa/backfill_qa_score_column_db_migration.py        # 默认 dry-run
3. 确认 dry-run 后加 --apply
4. 发布 data-pipeline 代码
```

未 ALTER 就发代码：Dashboard / QA Review / Jobs 会因缺列 SQL 失败。  
只 ALTER 不 backfill：历史终审 upload 分数变空，直到脚本 apply 或该 upload 再次走终审写入。

---

## 4. 风险点

| 编号 | 风险 | 优先级 | 验证重点 |
| --- | --- | --- | --- |
| R-01 | 只发代码未 ALTER | 高 | Dashboard / QA Review / Jobs 500 |
| R-02 | 只 ALTER 未 backfill | 高 | 已完成 QA 的平均分、列表分数、Jobs QC 阶段变少或为 0 |
| R-03 | 先发代码后 backfill 窗口 | 中 | 窗口内旧数据空、新终审有值；尽快 backfill |
| R-04 | 分数口径变化 | 高 | 抽 5–10 个已终审 upload，列值 = 旧 median |
| R-05 | Jobs 阶段误判 | 高 | `qa_score` 为 49 / 50 / NULL 的 episode 阶段正确 |
| R-06 | NULL 被当成 0 | 高 | Dashboard 平均分忽略 NULL |
| R-07 | `from qa.qa_helper import` 路径失败 | 高 | 部署后 QA 提交、Dashboard、Jobs 抽屉都能加载 |
| R-08 | 生产直接 `--apply` | 高 | 先 dry-run；确认备份后再 apply |

---

## 5. 测试数据与环境

- data-pipeline 含 `8aa3666` / `de8e83f`
- 目标库已备份；先在 staging 跑完整迁移
- 至少一个 round 1 / round 2 / round 3 终审 upload，记录旧 median 作为对照
- 至少一个进行中、一个 FAILED upload（列应保持 NULL）
- 一个 job 同时含 `qa_score` 49、50、NULL 的 episode
- Operator 账号能打开 Dashboard；QA reviewer 能提交评审；Admin 能打开 QA Review 与 Jobs

---

## 6. E2E / 发布验证用例

> 生产列迁移。Backfill 先 dry-run；不要在未备份的生产库直接 `--apply`。

### 6.1 迁移与回填

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| PRIS-335-001 | P0 | 迁移后列存在 | Staging/目标库 | 跑 ALTER | `\d data_uploads` 可见 `qa_score numeric(5,2)`，原有数据不丢 |
| PRIS-335-002 | P0 | Dry-run 不写库 | 列已加 | 不带 `--apply` 跑 backfill | 打印将更新的 upload；DB 值仍为 NULL |
| PRIS-335-003 | P0 | Apply backfill | Dry-run 已审 | `--apply` | SUCCEEDED upload 写入 median；已有值跳过；非终审不写 |
| PRIS-335-004 | P1 | 抽检口径 | round1/2/3 各 1 个终审 upload | 手工算旧 median，比列值 | 一致（允许 80 vs 80.00） |
| PRIS-335-005 | P2 | 单 upload backfill | 指定 `--upload_id` | dry-run 再 apply | 只动这一行 |
| PRIS-335-006 | P0 | 未迁移保护 | 仅在确认过的环境 | 若列不存在就发代码 | Dashboard/QA/Jobs 报错；**禁止这样发生产** |

### 6.2 在线写入与读路径

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| PRIS-335-007 | P0 | 新 QA 终审写入 | 代码已发布，列已存在 | 让一个 upload 完成 decisive round | 该行 `data_uploads.qa_score = final_quality_score` |
| PRIS-335-008 | P0 | Dashboard 读列 | 有历史分数的 operator | 打开 Operator Dashboard | 平均分、trend、upload 列表与 backfill/新写入一致；接口不再含 median LATERAL |
| PRIS-335-009 | P0 | NULL 不拉低平均分 | 同一 operator 既有终审又有未终审 | 看 summary `avg_qa_score` | 只平均非 NULL；未终审不当 0 |
| PRIS-335-010 | P0 | QA Review 列表 | Admin QA Review | 查看已完成/进行中 upload 的 final score | 已终审有分；未终审为空，不是 0 |
| PRIS-335-011 | P0 | Jobs QC 阶段 | job 含 49、50、NULL | 打开 Job drawer 阶段 | `>=50` 进 QC；NULL/49 不因本逻辑进 QC |
| PRIS-335-012 | P1 | QA 提交回归 | QA reviewer 账号 | 提交一条 round 1 评审 | 会话写入成功；无 `ModuleNotFoundError`；未终审则列仍 NULL |
| PRIS-335-013 | P1 | FAILED 不写分 | round 1 进入 `REVIEW_FIRST_ROUND_FAILED` | 查 `data_uploads.qa_score` | 仍为 NULL，直到某轮 SUCCEEDED |
| PRIS-335-014 | P1 | 三处分数一致 | 刚终审的 upload 同时出现在 Dashboard、QA Review、Job | 对比三处 | 都读同一 `data_uploads.qa_score` |

---

## 7. 发布前检查清单

- [ ] `8aa3666` / PR #77 已在目标 data-pipeline
- [ ] `20260916_data_uploads_qa_score_column.sql` 已执行
- [ ] backfill dry-run 已审，再 `--apply`
- [ ] 抽检 round1/2/3 终审 upload，列值 = 旧 median（PRIS-335-004）
- [ ] 新终审会写入列（PRIS-335-007）
- [ ] Operator Dashboard / Admin QA Review / Jobs drawer 无 500，分数与阶段正确（PRIS-335-008～011）
- [ ] QA 提交无 import 错误（PRIS-335-012）
- [ ] 未 ALTER 的环境禁止发该 data-pipeline 版本

---

## 8. 关联说明

- 与 PRIS-333 Waitlist、Robotics Data Beta、My Data Rejected、Order Admin **无功能依赖**，但若同一天发 data-pipeline，必须先完成本文迁移。
- Jobs `stage_for_episode` 的 `>= 50` 阈值是既有逻辑；本次只把 `qa_score` 来源从 median join 换成列。
- 日汇总与其它 9/18 改动见 [`Sep18.md`](./Sep18.md)。
