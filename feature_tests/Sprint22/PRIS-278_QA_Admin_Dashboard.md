# PRIS-278 QA Review Admin：Commit、逻辑与 E2E 测试分析

> 分析日期：2026-07-20  
> 前端仓库：`app-prismax-rp`，本地分支 `testing`，HEAD `e26c1026359884a1483fb8945fb84781a2c8281a`  
> 后端仓库：`app-prismax-rp-backend`，本地分支 `testing`，HEAD `4b8db1c7187b3ffc1e0d85df7188b9560501716f`  
> 功能范围：PRIS-278 QA Review Admin Dashboard，以及同一 PR 中的 Operator Dashboard 路由迁移  
> 数据来源：本地 Git 历史和最终代码；未执行远端拉取、未连接测试数据库。

## 1. 总体结论

PRIS-278 在 Admin Portal 新增 **QA Review** 页签，为管理员提供以下能力：

- 汇总 QA 流程中的 Upload 数量、视频小时数、已完成及审核中占比。
- 按日、周、月查看 QA Session 数和不同会员等级的参与 Reviewer 数。
- 搜索、筛选和分页查看进入 QA Pipeline 的 Upload。
- 查看 Upload 各轮次、各 Episode、各 Reviewer 的 Verdict 和 QA Score。
- 按当前筛选条件导出全部 Upload CSV。

后端新增 5 个 Admin-only 接口。鉴权同时校验 JWT 中 `role=admin` 和 `admin_whitelist` 钱包白名单，不是仅凭前端隐藏页签。

本 PR 还把 Operator Dashboard 的 4 个接口从 `app_prismax_user_management` 迁到 `app_prismax_data_pipeline`，并将路径由 `/vla/...` 改成 `/data/...`。这部分虽然不是 QA Review Admin 主页面，但与 PR 同时发布，必须做回归测试。

当前没有检索到针对新增 QA Review Admin 接口或组件的自动化测试。最高风险集中在：

1. 汇总、列表、详情和 CSV 之间的统计口径一致性。
2. Session 重试或重复记录导致 `reviewed` 计数膨胀。
3. 前端搜索和切换筛选时存在旧请求覆盖新请求的竞态。
4. Episode 详情请求失败没有错误提示，页面会看起来像“没有审核数据”。
5. Operator Dashboard 跨服务迁移后的鉴权、CORS、环境变量及旧路径兼容性。

## 2. Commit List

### 2.1 前端仓库 `app-prismax-rp`

PR 合并范围：`b233394^1..b233394^2`，净变更为 4 个文件、约 `+1435/-6`。

| # | Commit | 日期（Asia/Singapore） | 类型 | 原始说明 | 逻辑摘要 |
| --- | --- | --- | --- | --- | --- |
| 1 | `21638509d66a328c27bc0cdd262a67d9297068b6` | 2026-07-17 05:49 | 功能 | PRIS-278: implement first version of qa admin dashboard; refactor routes for operator admin dashboard | 新增 QA Review Admin 页面、汇总图表和 Upload 表格；Admin Portal 增加页签；Operator Dashboard 切到 data-pipeline `/data` 路由。 |
| 2 | `82d029824b528194dec541569c622a4aea46a9a0` | 2026-07-17 16:41 | 功能完善 | PRIS-278: add features with collapsible score list; pagination; misc improvements | 增加 15 条/页分页、Upload 详情弹窗、Round 切换、Episode 折叠及 Reviewer Score 明细。 |
| 3 | `c0aee7bed946965136af27df76dc4f7305ee6254` | 2026-07-18 05:21 | UI | PRIS-278: styling improvements | 优化详情 Loading、Episode 数量显示和响应式样式。 |
| 4 | `b233394ee9754d6f4f356d7be4af082cb0d87ba6` | 2026-07-18 05:32 | Merge | Merge pull request #66 from PrismaXAI/PRIS-278-qa-review-admin-dashboard | 将上述 3 个功能提交合入 `testing`。 |

最终涉及文件：

- `src/components/Admin/AdminPortal.js`
- `src/components/Admin/QAReviewTab/AdminQAReviewStats.js`
- `src/components/Admin/QAReviewTab/AdminQAReviewStats.module.css`
- `src/components/Data/UploadDashboard.js`

### 2.2 后端仓库 `app-prismax-rp-backend`

PR 合并范围：`20eb353^1..20eb353^2`，净变更为 3 个文件、约 `+802/-360`。

| # | Commit | 日期（Asia/Singapore） | 类型 | 原始说明 | 逻辑摘要 |
| --- | --- | --- | --- | --- | --- |
| 1 | `3f4e75959913f873751b93f03f256cd68cc1dc18` | 2026-07-17 05:47 | 功能 | PRIS-278: implement first version of qa admin dashboard | 在 data-pipeline 新增 QA Admin 汇总、趋势、列表、导出和详情接口；将 Operator Dashboard 实现由 user-management 迁入 data-pipeline；增加 QA 状态集合、Median Score 和 Episode 明细 Helper。 |
| 2 | `45d3974686c0e18ba84c4bfde6b89a74c59f068c` | 2026-07-17 16:32 | 功能完善 | PRIS-278: add pagination support; clean up code | Upload 列表固定 15 条/页；拆分查询、计数、Payload Helper；详情支持 Round；整理 QA Helper。 |
| 3 | `20eb3539a61db71675c9229da03635cc433743bd` | 2026-07-18 05:24 | Merge | Merge pull request #54 from PrismaXAI/PRIS_278-qa-review-admin-dashboard | 将上述 2 个功能提交合入 `testing`。 |

最终涉及文件：

- `app_prismax_data_pipeline/app.py`
- `app_prismax_data_pipeline/qa_helper.py`
- `app_prismax_user_management/app.py`

说明：日期按提交中 `+0800` 时间记录；GitHub merge commit 使用 `-0700`，表中换算为新加坡日期。Merge commit 只列作发布追踪，不重复计入功能代码量。

## 3. 前后端业务逻辑

### 3.1 页面入口和权限

Admin 登录成功后，`AdminPortal` 将 `adminAccessToken` 传给 `AdminQAReviewStats`。页面所有请求使用：

```http
Authorization: Bearer <admin JWT>
```

后端 `_require_admin_jwt()` 执行三层判断：

1. JWT 必须有效，否则返回 `401 invalid token`。
2. JWT claim 的 `role` 必须为 `admin`，否则返回 `403 admin access required`。
3. JWT identity 对应的钱包必须存在于 `admin_whitelist`，否则返回 `403 admin access required`。

因此需要分别测试普通用户 Token、伪造 Admin Role、已从白名单移除的 Admin，以及过期 Token。

### 3.2 QA Pipeline 数据范围

Dashboard 仅纳入以下 Upload Status：

| 分类 | Status |
| --- | --- |
| 尚在 QA 流程 | `DERIVED_READY`、`DERIVED_PARTIALLY_READY`、`REVIEW_FIRST_ROUND_FAILED`、`REVIEW_SECOND_ROUND_FAILED` |
| Review complete | `REVIEW_FIRST_ROUND_SUCCEEDED`、`REVIEW_SECOND_ROUND_SUCCEEDED`、`REVIEW_THIRD_ROUND_SUCCEEDED` |

`Under review = Total - Complete`。其他 Upload 状态不会出现在汇总、列表和机器类型筛选项中。

注意：这是一套产品定义口径，不等同于“数据库内所有 Upload”。如果未来新增第三轮失败状态或新的 QA 中间状态，却未同步更新常量，Dashboard 会漏数。

### 3.3 Summary 汇总卡

接口：`GET /data/admin/qa-review/summary`

- Total uploads：QA Pipeline 状态集合内的 Upload 数。
- Total hours：这些 Upload 下所有 Episode 的 `video_duration_hours` 之和。
- Reviews completed：处于任一 `REVIEW_*_ROUND_SUCCEEDED` 状态的 Upload 和小时数。
- Under review：Total 减 Complete。
- 百分比保留 1 位小数；分母为 0 时返回 0。
- 小时数保留 2 位小数；无 Episode 或时长为空按 0 处理。

风险点：Summary 对 Episode 不做状态过滤；只要属于该 Upload，其时长都会计入，包括失败、处理中或异常 Episode。该口径需要与产品预期确认。

### 3.4 Session 和 Reviewer 趋势图

接口：`GET /data/admin/qa-review/chart-stats`

一次请求返回 3 种粒度：

| 粒度 | 时间窗口 | Sessions reviewed | Reviewers participating |
| --- | --- | --- | --- |
| Day | 当前天及前 6 天，共 7 桶 | 每日 `data_qa_sessions` 记录数 | 每日按会员等级去重的 `user_id` 数 |
| Week | 当前周及前 7 周，共 8 桶 | 每周 Session 记录数 | 每周按会员等级去重的 Reviewer 数 |
| Month | 当前月及前 5 月，共 6 桶 | 每月 Session 记录数 | 每月按会员等级去重的 Reviewer 数 |

空时间桶由 PostgreSQL `generate_series` 补 0。Reviewer 仅分为 Explorer、Amplifier、Innovator；`user_class` 为空或不在三者中的用户不会进入堆叠柱，但其 Session 仍计入 Session 柱状图。

这里的“reviewed”实际按 `data_qa_sessions.created_at` 计数，并未额外判断提交完成标志。需要准备未完成、重复、重试 Session 数据确认产品口径。

### 3.5 Upload 列表、筛选与分页

接口：`GET /data/admin/qa-review/uploads`

| 参数 | 逻辑 |
| --- | --- |
| `search` | 对转换成文本的 `upload_id` 做大小写不敏感的包含匹配，例如 `12` 会匹配 `12`、`120`、`312`。 |
| `machine_type` | 与 `data_machines.product_name` 精确匹配。 |
| `round` | 必须可转换为整数，按该 Upload 最大 `qa_round` 精确匹配。 |
| `status=complete` | 仅返回三个 Round Success 状态。 |
| `status=under_review` | 返回 QA Pipeline 中除 Success 状态外的 Upload。 |
| `page` | 最小被钳制为 1；每页固定 15 条；按 `uploaded_at`，为空时按 `created_at` 倒序。 |

列表字段：Upload ID、上传时间、机器类型、当前最高 Round、Final QA Score、当前 Round Session 数、目标 Reviewer 数、显示状态。

Round 目标人数来自常量：Round 1 = 99、Round 2 = 9、Round 3 = 1。进度条最大显示 100%，但文字仍会显示真实的 `reviewed/target`，因此重复 Session 时可能出现 `100/99`。

Final QA Score 仅对 Success 状态计算，取最高 Round 所有 Session `qa_score` 的中位数并四舍五入为整数；尚未成功的 Upload 显示空值。

### 3.6 Upload / Episode / Reviewer 详情

接口：`GET /data/admin/qa-review/uploads/{upload_id}/episodes?round=N`

逻辑如下：

1. 查询 Upload 已存在 QA Session 的最大 Round；没有 Session 时按 Round 1。
2. 未传 Round 时展示最大 Round；传入值会钳制在 `1..current_round`。
3. Episode 列表只取该 Upload 下 `DERIVED_READY` 状态的 Episode。
4. 从指定 Round 的 `data_qa_sessions.review_result.result[]` 中解析 `episode_id`、`episode_score` 和 `episode_vote`。
5. 每个 Episode 展示 Reviewer 数、Score 算术平均值，以及 Reviewer User ID、会员等级、Pass/Fail 和个人分数。
6. 没被 Reviewer 覆盖的 Ready Episode 仍显示，Reviewer 数为 0、平均分为空。

Upload 最终 QA Score 是“Session 总分中位数”，Episode 弹窗中的 Avg 是“该 Episode Reviewer 分数的算术平均数”，两者不是同一口径，不能直接互相推导。

### 3.7 CSV 导出

接口：`GET /data/admin/qa-review/uploads/export`

- 使用与列表相同的 `search`、`machine_type`、`round`、`status` 过滤逻辑。
- 不带分页，导出全部命中 Upload。
- 列为：`upload_id`、`uploaded_time`、`machine_type`、`round`、`final_qa_score`、`reviewed`、`target`、`status`。
- 文件名：`qa-review-uploads_YYYY-MM-DD.csv`。

需验证 CSV 与 UI 筛选后的 `count` 一致，并重点检查逗号、双引号、换行、Unicode 机器名称，以及以 `= + - @` 开头的值在 Excel 中的公式注入风险。

### 3.8 Operator Dashboard 路由迁移

同一 PR 将以下 API 从 user-management 迁移至 data-pipeline：

| 旧路径 | 新路径 |
| --- | --- |
| `/vla/operator-dashboard/summary` | `/data/operator-dashboard/summary` |
| `/vla/operator-dashboard/uploads` | `/data/operator-dashboard/uploads` |
| `/vla/admin/operator-dashboard/summary` | `/data/admin/operator-dashboard/summary` |
| `/vla/admin/operator-dashboard/uploads` | `/data/admin/operator-dashboard/uploads` |

前端 `UploadDashboard.js` 同步从 `PRISMAX_BACKEND_URL` 改用 `PRISMAX_DATA_PIPELINE_URL`。旧实现已从 user-management 删除，没有兼容代理时旧客户端会直接失败。

迁移后的普通用户接口仍使用用户 Hash Token，Admin 变体使用 Admin JWT。部署验证必须覆盖服务路由、CORS、Secret/DB 权限和环境 URL，不能只做本地组件测试。

### 3.9 Developer Handoff 与代码实现差异

对照文档：`QA_PrismaX/PM_PRD/qa-review-dev-handoff.md`。该 handoff 基于自包含的 Mock Prototype 描述目标页面；以下结论来自当前本地 `testing` 分支的前后端最终实现。

#### 3.9.1 明确差异

| 优先级 | 对照项 | Handoff 描述 | 当前代码实现 | 测试/产品影响 |
| --- | --- | --- | --- | --- |
| P0 | Review Progress Target | 固定 `90` | Round 1 = `99`、Round 2 = `9`、Round 3 = `1` | 进度条、完成阈值和边界测试完全不同；必须确认以哪套数字为准。 |
| P0 | Review Progress 含义 | 尚未确认 denominator 是 Episode Review 数还是不同 Episode 数 | numerator 是当前最高 Round 的 `data_qa_sessions` 行数；target 是该 Round 的目标 Reviewer 数 | 当前实现实际采用“本轮 Reviewer/Session 数”，不是 Episode 数。正常提交路径禁止同一用户重复审核同一个 Upload，但仍需验证并发或历史重复数据。 |
| P1 | Total uploads 范围 | 字面描述为 `all uploads` | 只统计 `QA_PIPELINE_STATUSES` 内的 Upload | Processing、Upload Failed、Validation Failed 等状态不会进入 Total；需确认 handoff 是否实际意指“全部 QA Pipeline Upload”。 |
| P1 | Modal Episode 范围 | Body 只列出 reviewed episodes | 返回该 Upload 下全部 `DERIVED_READY` Episode，未被审核的 Episode 也显示为 `0 reviewers`、Avg `—` | Episode 数和 Empty State 与 handoff 不同。 |
| P1 | Empty State 触发条件 | Upload 有 0 Review 时显示 `No episodes reviewed yet` | 只有接口返回 0 个 Ready Episode 时才显示；存在 Ready Episode 但 0 Review 时仍展示 Episode 列表 | 当前文案可能把“没有 Ready Episode”误表达成“没有 Review”。 |
| P2 | QA Review 页签位置 | 第 5 个 Admin Tab，其他 4 个 Tab | 当前是第 6 个 Tab，新增了 `Dataset Stats` | 不影响核心功能，但 handoff 的导航说明已过期。 |

Review target 的当前代码依据：

```python
QA_REVIEWER_COUNT_BY_ROUND = {
    1: 99,
    2: 9,
    3: 1,
}
```

Review Progress 的当前查询口径：

```sql
SELECT COUNT(*) AS session_count
FROM data_qa_sessions q
WHERE q.upload_id = u.upload_id
  AND q.qa_round = COALESCE(latest_round.qa_round, 1)
```

Summary 当前只纳入以下状态：

```text
DERIVED_READY
DERIVED_PARTIALLY_READY
REVIEW_FIRST_ROUND_FAILED
REVIEW_SECOND_ROUND_FAILED
REVIEW_FIRST_ROUND_SUCCEEDED
REVIEW_SECOND_ROUND_SUCCEEDED
REVIEW_THIRD_ROUND_SUCCEEDED
```

#### 3.9.2 Handoff 待确认项，代码已经确定行为

| 对照项 | 当前实现选择 | 是否建议写回 Handoff |
| --- | --- | --- |
| Final QA Score 聚合 | 仅 Success 状态展示；取最高 Round 所有 Session `qa_score` 的中位数并取整 | 是。Handoff 只规定展示条件和颜色，没有规定聚合公式。 |
| Episode Avg Score | 对指定 Round 内该 Episode 的非空 Reviewer Score 计算算术平均并取整 | 是。需要明确其与 Upload Final Median 是两套口径。 |
| Round 列表筛选 | 按 Upload 已存在 QA Session 的最大 Round 精确筛选 | 是。相当于“当前/最高 Round”，不是任意历史 Round。 |
| Round 历史查看 | Modal 在 `current_round > 1` 时展示 Round Tabs，可切换历史 Round | 是。属于 handoff 未描述的功能扩展。 |
| Upload ID 搜索 | 对 ID 转成文本后做包含匹配，例如 `12` 可匹配 `12`、`120`、`312` | 是。需明确是否期望精确搜索。 |
| 分页 | 固定每页 15 条，Prev/Next 翻页，筛选变化回到第 1 页 | 建议。属于 handoff 未定义的必要大数据行为。 |
| Admin 鉴权 | 有效 JWT + `role=admin` + identity 钱包仍在 `admin_whitelist` | 是。属于正式接口契约。 |
| CSV 范围 | 复用当前 Search/Machine/Round/Status 条件，但不受当前页限制，导出全部命中记录 | 是。可避免“current filtered view”被理解为只导出当前页。 |
| Machine Type 选项 | 从已进入 QA Pipeline 的 Upload 关联机器中读取不同 `product_name` | 建议。没有相关 QA Upload 的注册机器不会出现在下拉框。 |

#### 3.9.3 与 Handoff 一致的实现

- 页面包含 3 张 Summary 卡、两张独立图表和可筛选 Upload 表格。
- Complete 与 Under review 在当前 QA Pipeline 统计范围内可回算为 Total。
- Hours 使用 Episode 的 `video_duration_hours`，代表采集数据时长，不是 Reviewer 工作时长。
- D/W/M 分别展示当前及最近 7 天、8 周、6 个月；两张图的时间粒度状态相互独立。
- Reviewer 在每个时间桶内按 `user_id` 去重，并按 Explorer、Amplifier、Innovator 分层。
- Final QA Score 仅在 Review Complete 时展示；颜色阈值为 `>=85` 绿色、`75–84` 黄色、`<75` 红色。
- UI 只显示 Review complete 和 Under review，不存在 Queued。
- Search、Machine Type、Round、Status 可组合筛选，Result Count 随筛选更新。
- Verdict 使用后端明确保存的 `episode_vote`，没有用 Score `>=70` 在前端临时推导。
- Modal 支持 X、Backdrop 和 Escape 三种关闭方式。
- Tier 颜色与 handoff 一致，页面 CSS 使用作用域内的 Design Variables。

#### 3.9.4 建议确认顺序

1. 产品先确认 Review Target 是固定 `90`，还是按 Round 使用 `99/9/1`。
2. 明确 Review Progress 的业务名称和单位：Reviewer 数、Session 数、Episode Review 数或不同 Episode 数。
3. 明确 Summary 的 `all uploads` 是所有数据库 Upload，还是所有进入 QA Pipeline 的 Upload。
4. 明确 Modal 是只展示 reviewed episodes，还是展示所有 Ready Episode 并标出未审核项。
5. 根据最终决定同步更新 handoff、API Contract、UI 文案和 E2E 预期，避免测试以不同口径判定结果。

## 4. 风险与代码审查发现

| 优先级 | 风险/发现 | 影响 | 建议 |
| --- | --- | --- | --- |
| P0 | Operator Dashboard 旧接口已删除且路径、服务域名同时变化 | 旧前端、缓存页面或第三方调用全部 404；配置错误会导致 Operator Dashboard 整页不可用 | 上线前验证所有环境的 `PRISMAX_DATA_PIPELINE_URL`、CORS 和网关；确认是否需要旧路径临时兼容或监控。 |
| P0 | Admin 权限依赖 JWT Role + 实时白名单 | 任一校验遗漏会造成 QA Reviewer 明细和 User ID 泄露 | 对 401/403 组合做 API 自动化；确认日志不输出 Token。 |
| P1 | `reviewed` 使用当前 Round 的 Session 行数，不是 distinct Reviewer | 重试、重复提交可能导致审核进度超过目标并提前造成错误判断 | 用重复 `user_id` Session 验证；若产品要人数，应改为 `COUNT(DISTINCT user_id)` 或只计有效终态 Session。 |
| P1 | 趋势图 Session 数未显式过滤“已提交/有效”记录 | Sessions reviewed 图可能包含未完成或废弃 Session | 明确 `data_qa_sessions` 是否只在提交时创建；否则增加状态/结果非空过滤。 |
| P1 | 搜索/筛选请求没有 AbortController 或请求序号保护 | 慢请求可能在新请求后返回，旧结果覆盖当前筛选条件 | E2E 人工延迟接口验证；前端增加取消或 latest-request guard。 |
| P1 | Episode 详情失败时无可见错误状态 | 500/401/网络错误会被用户误认为“No episodes reviewed yet” | 增加 `episodesError`、Retry 和 Token 过期统一处理。 |
| P1 | Chart 请求失败只写 Console；CSV 失败也没有 UI 提示或 Loading 防重复 | 管理员无法区分零数据和接口故障，可能重复点击导出 | 增加 Error/Retry、Export loading、成功/失败 Toast。 |
| P1 | Summary 小时数包含 Upload 下所有 Episode 状态 | QA 可审核小时数可能被失败或处理中 Episode 放大 | 与 PRD 确认是 Upload 总时长还是 Ready Episode 时长，并用混合状态数据验证。 |
| P1 | Dashboard 数据未限定 QA Launch Date | 如果历史数据已处于同类状态，会进入总计但不一定符合新 QA 制度 | 明确是否应展示 All-time；如需上线后数据，应增加时间条件。 |
| P2 | 非法 `status` 被静默忽略；Round 可接受 0、负数和 4 以上整数 | API 行为不一致，调用错误不易发现；列表可能返回空数据 | 对枚举和 Round 1–3 做严格 400 校验。 |
| P2 | 详情 Round 超范围会被静默钳制 | 请求 Round 99 却返回当前 Round，调用方可能误判 | 返回 400 或在响应中明确 requested/effective round。 |
| P2 | `page` 超总页数返回空数组但仍返回有效 `total_pages` | 筛选后停留页码或直接请求大页码时体验不明确 | 前端已在筛选时重置第一页；API 可选择 400、钳制末页或保持并文档化。 |
| P2 | Episode 详情只展示 `DERIVED_READY` Episode | 失败/部分就绪 Episode 的审核结果可能完全不可见 | 确认详情定义；至少测试混合状态 Upload，避免 Reviewer 数与列表进度无法解释。 |
| P2 | User ID 以 `USR-{id}` 原样展示 | 管理员可看到内部 ID，属于敏感运营数据 | 确认 Admin 产品需求和审计要求；禁止普通用户访问。 |
| P2 | CSV 未做 Spreadsheet Formula Injection 防护 | 可控机器名称若以公式字符开头，管理员用 Excel 打开时存在风险 | 对危险前缀进行单引号转义，或确认字段不可由不可信用户控制。 |
| P2 | 大数据下 Summary 全量聚合、CSV 无分页、列表有多个 LATERAL 子查询 | 数据量增长后可能超时或占用大量内存 | 使用生产量级数据做性能测试，检查索引和 `EXPLAIN ANALYZE`，CSV 考虑流式输出。 |
| P3 | 前端使用 `==` 而非 `===` 比较 Episode 数 | 当前数字类型下通常无功能问题，但不符合一致编码规范 | 改为严格比较。 |

## 5. 测试数据建议

建议建立一组可复用的、可通过 SQL/API 精确核对的数据矩阵：

| 数据组 | 关键构造 | 用途 |
| --- | --- | --- |
| A：空环境 | QA Pipeline 状态集合内无 Upload | 验证 0、空图、空表、CSV Header。 |
| B：Round 1 审核中 | 1 个 Upload，99 目标，0/1/98/99/100 条 Session 分别准备 | 进度、边界、重复 Session、超目标。 |
| C：多 Round | Round 1 Failed、Round 2 Failed、Round 3 Success，三轮分数和 Reviewer 不同 | 最高 Round、状态、Round Tab、Final Median。 |
| D：混合 Episode | 同一 Upload 含 Ready、Failed、Processing、时长为空 Episode | Summary 小时口径与详情可见范围。 |
| E：分数边界 | 分数 `null`、74、75、84、85、100；奇数和偶数个 Session | 中位数、平均数、颜色阈值和空值。 |
| F：会员等级 | Explorer、Amplifier、Innovator、未知、空值，同一用户同桶多 Session | Reviewer 去重与堆叠图口径。 |
| G：分页 | 31 个符合条件 Upload，上传时间含相同值和 `uploaded_at=null` | 15/15/1 分页、排序稳定性、页码边界。 |
| H：特殊字符 | Machine Type 含逗号、双引号、中文、换行、`=1+1` | 筛选与 CSV 安全。 |
| I：权限 | Admin 白名单、Admin 非白名单、普通用户、过期 Token、无 Token | 401/403 和数据隔离。 |
| J：迁移回归 | 普通 Operator 和 Admin 代理查看同一用户数据 | 新服务路由、Token 类型、数据一致性。 |

## 6. E2E 测试用例

### 6.1 权限、入口与基础状态

| ID | 优先级 | 场景 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| QAADM-E2E-001 | P0 | Admin 打开 QA Review 页签 | 有效 Admin JWT，钱包在白名单 | 登录 Admin Portal；点击 **QA Review** | 页签高亮；Summary、两个图表、Upload 表格发起请求并正常显示；控制台无致命错误。 |
| QAADM-E2E-002 | P0 | 未登录直接访问接口 | 无 Token | 分别请求 5 个 `/data/admin/qa-review/*` 接口 | 全部返回 401；不返回任何统计、Reviewer 或 User ID 数据。 |
| QAADM-E2E-003 | P0 | 普通用户 Token 访问 | 有效非 Admin JWT | 调用全部 Admin QA Review 接口 | 全部返回 403 `admin access required`。 |
| QAADM-E2E-004 | P0 | Admin Role 但不在白名单 | JWT role=admin，identity 不在 `admin_whitelist` | 调用全部接口 | 全部返回 403；不能仅凭 role 绕过白名单。 |
| QAADM-E2E-005 | P0 | 白名单移除即时生效 | Admin 已登录，随后从白名单移除 | 刷新页面或重新请求 | 后端返回 403；前端进入统一 Session/权限错误处理，不继续展示新数据。 |
| QAADM-E2E-006 | P1 | Token 过期 | 过期 Admin JWT | 打开页面或等待 Token 过期后切换筛选 | 返回 401；页面不应永久 Loading；应提示重新登录。 |
| QAADM-E2E-007 | P1 | 空数据环境 | 数据组 A | 打开页面并导出 CSV | Summary 全为 0；图表每桶为 0；表格显示空态；CSV 只有 Header。 |

### 6.2 Summary 和图表统计

| ID | 优先级 | 场景 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| QAADM-E2E-008 | P0 | Total = Complete + Under review | 准备全部 QA Pipeline 状态及无关状态 Upload | 打开页面；用 DB 查询核对 | Upload 数和小时数满足 Total = Complete + Under review；无关状态不计入。 |
| QAADM-E2E-009 | P1 | Complete 状态映射 | 分别准备 Round 1/2/3 Success | 查看 Summary 和列表 | 三种 Success 均计为 Complete，列表显示 `Review complete`。 |
| QAADM-E2E-010 | P1 | Under review 状态映射 | 准备 Ready、Partially Ready、Round 1/2 Failed | 查看 Summary 和列表 | 全部计为 Under review；列表状态一致。 |
| QAADM-E2E-011 | P1 | Episode 小时数与空值 | 同一 Upload 有 1.25、0.5、null 小时 Episode | 查看 Summary | 合计为 1.75 小时，空值按 0；百分比使用相同分母。 |
| QAADM-E2E-012 | P1 | 混合 Episode 状态的小时口径 | 数据组 D | 对比 DB 和 Summary | 当前实现会累加所有状态 Episode；结果与文档口径一致，并确认产品是否接受。 |
| QAADM-E2E-013 | P1 | 百分比舍入 | 构造 1/3 Complete | 查看 Summary | Upload 百分比为 33.3%，Under review 为 66.7%；零分母为 0。 |
| QAADM-E2E-014 | P1 | Day 时间桶边界 | Session 位于当天、6 天前、7 天前及 UTC 边界 | 选择 D | 仅当前及前 6 天进入 7 个桶；桶标签和服务器时区口径正确。 |
| QAADM-E2E-015 | P1 | Week/Month 时间桶 | Session 跨周、跨月、跨年 | 分别选择 W/M | 返回 8 周/6 月；按时间升序；跨年标签不会导致数据错位。 |
| QAADM-E2E-016 | P1 | Reviewer 同桶去重 | 同一用户同一天提交多个 Session | 查看 Reviewers 图 | 对应会员等级 Reviewer 只计 1；Sessions 图按实际 Session 条数增加。 |
| QAADM-E2E-017 | P1 | Reviewer 跨桶重复参与 | 同一用户在两个日期/周参与 | 切换 D/W | 每个桶分别计 1；不会全周期只计一次。 |
| QAADM-E2E-018 | P1 | 未知会员等级 | user_class 为空或不在三种已知等级 | 查看两个图 | Session 计入 Sessions；不进入三种 Reviewer 堆叠；确认与产品口径一致。 |
| QAADM-E2E-019 | P1 | 图表接口失败 | Mock 500/超时 | 打开页面 | Summary/表格不受影响；图表区域应有可见错误和重试能力。当前实现预计只留空图，作为缺陷记录。 |

### 6.3 Upload 列表、筛选和分页

| ID | 优先级 | 场景 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| QAADM-E2E-020 | P0 | 默认列表与排序 | 至少 31 个 QA Upload | 打开页面 | 每页 15 条；按 `uploaded_at/created_at` 倒序；显示总数和 Page 1 of 3。 |
| QAADM-E2E-021 | P1 | Upload ID 包含搜索 | ID 包含 `12` 的多条数据 | 输入 `12`，等待 250ms | 返回 ID 文本中包含 `12` 的记录；总数、页数同步更新。 |
| QAADM-E2E-022 | P1 | 搜索去抖 | 可观察 Network | 快速输入 5 个字符 | 中间定时器被取消；最终结果对应完整输入。允许已有请求存在时，最终页面仍必须是最新条件。 |
| QAADM-E2E-023 | P0 | 旧请求覆盖新请求竞态 | Mock 第一个搜索请求延迟，第二个快速返回 | 连续改变搜索词 | 最终表格必须对应第二个搜索词。当前实现可能失败，应记录前端竞态缺陷。 |
| QAADM-E2E-024 | P1 | Machine Type 筛选 | 至少两类 Machine，含 Unknown | 逐一筛选 | 只返回精确匹配机器类型；Unknown robot 不应错误进入可选机器列表。 |
| QAADM-E2E-025 | P1 | Round 1/2/3 筛选 | 多 Round 数据组 C | 逐一切换 Round | 按最大 Round 筛选；切换后回到第 1 页。 |
| QAADM-E2E-026 | P1 | Complete/Under review 筛选 | 混合 Status | 切换 Status | 结果与 Summary 分类一致；总数和分页更新。 |
| QAADM-E2E-027 | P1 | 组合筛选 | 多机器、多 Round、多状态 | 同时设置搜索、机器、Round、状态 | 所有条件按 AND 生效；无结果显示明确空态。 |
| QAADM-E2E-028 | P1 | 筛选后页码重置 | 先到第 3 页 | 修改任一筛选 | 自动回到 Page 1，不出现因旧页码导致的假空数据。 |
| QAADM-E2E-029 | P1 | Prev/Next 边界 | 31 条数据 | 连续翻页 | 第 1 页 Prev 禁用；第 3 页 Next 禁用；Loading 时按钮禁用；无重复或遗漏。 |
| QAADM-E2E-030 | P1 | 相同上传时间的分页稳定性 | 多条 Upload 时间完全相同 | 重复前后翻页 | 同一条数据不应跨页漂移或重复。若出现，建议 SQL 增加 `upload_id DESC` 次排序。 |
| QAADM-E2E-031 | P1 | Session 超目标 | 数据组 B 中 100/99 | 查看进度 | 进度条不超过 100%；文字显示 100/99；确认是否为重复 Session 缺陷。 |
| QAADM-E2E-032 | P1 | Final Score 中位数 | 当前 Round 分数为 `[60, 80, 100]` 及 `[60, 80]` | 查看列表 | 分别显示 80 和 70；非 Success 状态显示 `—`。 |
| QAADM-E2E-033 | P1 | Score 颜色边界 | 分数 74/75/84/85 | 查看列表和详情 | `<75` 红、`75–84` 黄、`>=85` 绿；null 为 Pending 样式。 |
| QAADM-E2E-034 | P2 | 非法 API 参数 | 直接传 `page=x`、`round=x`、未知 status | 调接口 | page/round 非整数返回 400；当前未知 status 会被忽略，记录并确认是否应严格校验。 |
| QAADM-E2E-035 | P2 | 页码越界 | 仅 2 页数据 | 请求 page=0、page=999 | page=0 被钳制为 1；page=999 返回空数组且声明正确 total_pages；行为与 API 约定一致。 |
| QAADM-E2E-036 | P1 | 列表接口失败和恢复 | Mock 500 后恢复 200 | 打开页面，再触发筛选重试 | 表格显示失败，不展示陈旧数据为新结果；恢复后正确刷新。 |

### 6.4 Episode / Reviewer 详情

| ID | 优先级 | 场景 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| QAADM-E2E-037 | P0 | 打开 Upload 详情 | 有 Ready Episode 和 Session | 点击列表行 | 弹窗显示正确 Upload、机器、日期、状态、进度、Episode 数和 Final QA；背景点击及 Close 可关闭。 |
| QAADM-E2E-038 | P1 | Escape 关闭与事件清理 | 弹窗已打开 | 按 Escape；重复开关弹窗 | 弹窗关闭；不累积键盘监听器，不出现一次按键触发多次异常。 |
| QAADM-E2E-039 | P1 | 多 Round 切换 | 数据组 C | 打开详情，切换 Round 1/2/3 | 默认最高 Round；每个 Tab 返回对应 Round 的 Reviewer 和分数；切换时显示 Loading。 |
| QAADM-E2E-040 | P1 | 单 Round 不显示 Tab | 仅 Round 1 | 打开详情 | 不展示冗余 Round Tabs；内容默认为 Round 1。 |
| QAADM-E2E-041 | P1 | Episode 展开/折叠 | 多 Episode、多 Reviewer | 展开多个 Episode，再切 Round | 每个 Episode 独立展开；显示 User ID、Tier、Verdict、Score；切 Round 后展开状态重置。 |
| QAADM-E2E-042 | P1 | 未审核 Ready Episode | Ready Episode 不在任何 review_result 中 | 打开详情 | Episode 仍出现，显示 0 reviewers、Avg `—`，展开后无 Reviewer 行。 |
| QAADM-E2E-043 | P1 | 非 Ready Episode 可见性 | 数据组 D | 打开详情 | 当前仅 Ready Episode 出现；核对 Episode 数和产品需求，失败 Episode 不应被错误计入详情数量。 |
| QAADM-E2E-044 | P1 | review_result 异常数据 | result 非数组、非法 episode_id/score/vote | 打开详情 | 接口不崩溃；非法项被跳过；有效项仍展示；Verdict 非 pass/fail 显示 `—`。 |
| QAADM-E2E-045 | P1 | Episode 平均分 | Reviewer 分数 `[74,75,85]`，含一个 null | 展开 Episode | Avg 按有效分数算术平均并取整；null 不进入分母；各 Reviewer 原值正确。 |
| QAADM-E2E-046 | P1 | 详情接口失败 | Mock 401/404/500/超时 | 点击行 | 应显示明确错误并可重试，不应误显示“No episodes reviewed yet”。当前实现预计失败，建议立缺陷。 |
| QAADM-E2E-047 | P1 | 快速切换不同 Upload | Upload A 请求慢，B 请求快 | 先点 A，关闭并立即点 B | 弹窗最终只能展示 B 数据。当前无请求隔离，需验证是否被 A 的旧响应覆盖。 |
| QAADM-E2E-048 | P2 | Round 越界 API | 请求 round=0、-1、99、非整数 | 直接调用接口 | 非整数 400；数值越界当前被钳制到有效 Round，响应 `round` 应反映实际值。 |
| QAADM-E2E-049 | P1 | 无 Session Upload | QA Pipeline Upload 无 Session | 打开详情 | current_round=1；所有 Ready Episode 显示 0 Reviewer；页面不报错。 |

### 6.5 CSV 导出

| ID | 优先级 | 场景 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| QAADM-E2E-050 | P0 | 默认导出 | 有多页数据 | 点击 Export CSV | 下载文件名包含当天日期；导出全部命中数据，不只当前 15 条。 |
| QAADM-E2E-051 | P0 | 筛选条件导出一致性 | 设置组合筛选 | 记录 UI count；导出并解析 CSV | 数据行数等于 UI count；每行均满足搜索、机器、Round、Status 条件。 |
| QAADM-E2E-052 | P1 | CSV 字段和空值 | 有 Score/Target null 数据 | 导出 | Header 顺序正确；null 输出空字段；日期、状态、Reviewed 与 UI/API 一致。 |
| QAADM-E2E-053 | P1 | CSV 特殊字符 | 数据组 H | 导出并用标准 CSV Parser/Excel 打开 | 逗号、引号、换行、中文不破坏列；危险公式前缀应被安全处理或登记安全风险。 |
| QAADM-E2E-054 | P1 | 导出失败 | Mock 401/500/超时 | 点击 Export | 应有失败提示且允许重试，不产生损坏文件；当前实现只写 Console，建议立缺陷。 |
| QAADM-E2E-055 | P1 | 重复点击导出 | 大数据导出响应较慢 | 连续点击多次 | 应防止并发重复请求/重复下载，并显示导出中状态；当前实现需重点验证。 |
| QAADM-E2E-056 | P2 | 大数据导出性能 | 生产量级数据 | 导出并记录耗时、内存、文件大小 | 在 SLA 内成功，无网关超时或进程 OOM；CSV 行数完整。 |

### 6.6 Operator Dashboard 迁移回归

| ID | 优先级 | 场景 | 前置条件 | 步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| QAADM-E2E-057 | P0 | 普通 Operator Summary 新路由 | 有效用户 Hash Token | 打开 Operator Upload Dashboard | 请求 data-pipeline `/data/operator-dashboard/summary` 成功；指标、图表正确。 |
| QAADM-E2E-058 | P0 | 普通 Operator Upload 列表新路由 | 有多页 Upload | 筛选时间/机器并翻页 | `/data/operator-dashboard/uploads` 返回正确数据、机器列表和分页。 |
| QAADM-E2E-059 | P0 | Admin 查看指定 Operator Summary | 有效 Admin JWT 和 user_id | 从 Admin 入口查看 Operator | `/data/admin/operator-dashboard/summary` 成功且只统计指定用户。 |
| QAADM-E2E-060 | P0 | Admin 查看指定 Operator Uploads | 有效 Admin JWT 和 user_id | 翻页、筛选机器 | 新接口正确返回指定用户数据，不能串到其他用户。 |
| QAADM-E2E-061 | P0 | 部署配置/CORS | 测试环境使用真实域名 | 浏览器完整走一次 057–060 | 请求发往正确 `PRISMAX_DATA_PIPELINE_URL`；预检、Authorization Header 和响应 CORS 正常。 |
| QAADM-E2E-062 | P1 | 旧路径兼容策略 | 已部署新版本 | 请求 4 个旧 `/vla/*` 路径 | 按发布策略返回兼容响应、明确 404 或重定向；监控能发现仍在调用旧路径的客户端。 |
| QAADM-E2E-063 | P1 | 迁移前后数据口径 | 可在同一快照运行旧/新实现或保留基准 | 对同一用户、同一时间范围比较 | Summary、趋势、Upload、Episode 统计一致；Median/旧 Average 的产品变更有明确预期。 |
| QAADM-E2E-064 | P1 | Token 类型隔离 | 普通 Hash Token 与 Admin JWT | 交叉调用普通/Admin 接口 | 普通接口仅接受预期用户 Token；Admin 接口不能被普通 Token 调用。 |

## 7. 建议的自动化分层

### 7.1 后端 API / Integration（优先补齐）

建议为 5 个 Admin QA Review 接口新增 pytest，并使用事务测试库：

- 鉴权参数化：无 Token、无效 Token、普通用户、非白名单 Admin、有效 Admin。
- 状态集合参数化：每个 QA 状态与一个无关状态。
- `_build_qa_episode_breakdown`：非法 JSON、空结果、重复 Episode、空分数、Verdict 枚举。
- Median 与 Average：奇数、偶数、空值、边界分数。
- Round、Status、Page 参数校验及组合筛选。
- CSV 使用 Python `csv` 模块解析后断言，不用字符串分割。
- Operator Dashboard 迁移前后使用同一 Fixture 做 Contract 对比。

### 7.2 前端组件测试

- Mock 5 个接口，验证 Loading、Empty、Error、Success。
- 使用 fake timers 验证 250ms 搜索去抖。
- 人为乱序 resolve Promise，验证最新请求保护。
- 验证筛选重置 Page、分页按钮边界和 Loading 禁用。
- 验证 Modal Round 切换、折叠、Escape 和请求失败状态。
- 验证 Export loading、错误 Toast、Blob URL 释放。

### 7.3 浏览器 E2E

P0 建议至少自动化：001–005、008、020、023、032、037、039、046、050–051、057–061。测试中同时断言 UI、Network Response 和 DB/Fixture 基准，避免只检查“页面有文字”。

## 8. 发布前建议

1. 先确认三个产品口径：`reviewed` 是 Session 数还是 distinct Reviewer 数；Summary Hours 是否包含非 Ready Episode；历史 QA 数据是否应计入 All-time。
2. 在前端补充请求取消/最新请求保护，并为 Chart、Episode、CSV 增加可见错误与 Retry。
3. 为新增接口至少补齐鉴权、状态映射、分页、Round、Score 和 CSV 的后端测试。
4. 用生产量级数据执行 Summary、列表、详情和 CSV 性能测试，检查相关索引及慢查询。
5. 在测试环境完成 Operator Dashboard 的真实跨域回归，确认旧 `/vla` 路径的兼容或下线策略。
6. 对 CSV 字段实施 Formula Injection 防护，再允许管理员使用 Excel 打开导出文件。

## 9. Reference：QA Review Admin 全部 API 的 cURL

先设置测试环境的数据服务地址、Admin JWT 和一个待查询的 Upload ID。以下变量仅对当前 Shell 会话生效，请勿将真实 Token 提交到 Git：

```bash
export PRISMAX_DATA_PIPELINE_URL="https://<data-pipeline-host>"
export PRISMAX_ADMIN_JWT="<admin-jwt>"
export QA_UPLOAD_ID="<upload-id>"
```

1. 获取 Summary 汇总卡：

```bash
curl --request GET \
  --url "${PRISMAX_DATA_PIPELINE_URL}/data/admin/qa-review/summary" \
  --header "Authorization: Bearer ${PRISMAX_ADMIN_JWT}" \
  --header "Accept: application/json"
```

2. 获取 Session 和 Reviewer 趋势图；单次响应包含 `day`、`week`、`month` 三种粒度：

```bash
curl --request GET \
  --url "${PRISMAX_DATA_PIPELINE_URL}/data/admin/qa-review/chart-stats" \
  --header "Authorization: Bearer ${PRISMAX_ADMIN_JWT}" \
  --header "Accept: application/json"
```

3. 获取 Upload 列表，不带筛选时默认请求第 1 页，每页固定 15 条：

```bash
curl --request GET \
  --url "${PRISMAX_DATA_PIPELINE_URL}/data/admin/qa-review/uploads?page=1" \
  --header "Authorization: Bearer ${PRISMAX_ADMIN_JWT}" \
  --header "Accept: application/json"
```

带全部筛选条件的示例。`status` 可使用 `complete` 或 `under_review`，`round` 当前应使用 `1`、`2` 或 `3`：

```bash
curl --get \
  --url "${PRISMAX_DATA_PIPELINE_URL}/data/admin/qa-review/uploads" \
  --header "Authorization: Bearer ${PRISMAX_ADMIN_JWT}" \
  --header "Accept: application/json" \
  --data-urlencode "search=123" \
  --data-urlencode "machine_type=<machine-type>" \
  --data-urlencode "round=1" \
  --data-urlencode "status=under_review" \
  --data-urlencode "page=1"
```

4. 获取指定 Upload 的 Episode / Reviewer 详情；不传 `round` 时返回当前最高 Round：

```bash
curl --request GET \
  --url "${PRISMAX_DATA_PIPELINE_URL}/data/admin/qa-review/uploads/${QA_UPLOAD_ID}/episodes" \
  --header "Authorization: Bearer ${PRISMAX_ADMIN_JWT}" \
  --header "Accept: application/json"
```

查询指定 Round：

```bash
curl --get \
  --url "${PRISMAX_DATA_PIPELINE_URL}/data/admin/qa-review/uploads/${QA_UPLOAD_ID}/episodes" \
  --header "Authorization: Bearer ${PRISMAX_ADMIN_JWT}" \
  --header "Accept: application/json" \
  --data-urlencode "round=2"
```

5. 导出全部命中条件的 Upload CSV。导出接口不分页，支持与列表相同的四个筛选参数：

```bash
curl --get \
  --url "${PRISMAX_DATA_PIPELINE_URL}/data/admin/qa-review/uploads/export" \
  --header "Authorization: Bearer ${PRISMAX_ADMIN_JWT}" \
  --header "Accept: text/csv" \
  --data-urlencode "search=123" \
  --data-urlencode "machine_type=<machine-type>" \
  --data-urlencode "round=1" \
  --data-urlencode "status=complete" \
  --output "qa-review-uploads_$(date +%F).csv"
```

排查鉴权或状态码时，可在上述命令中加入 `--include`，同时输出 HTTP Status 和 Response Headers。Admin JWT 除了有效外，其 `role` 必须为 `admin`，且 JWT identity 对应的钱包必须仍存在于 `admin_whitelist`。
