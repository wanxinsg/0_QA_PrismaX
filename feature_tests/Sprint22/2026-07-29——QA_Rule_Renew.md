# Sprint 22 前后端 Commit 逻辑与 E2E 测试分析

> 分析日期：2026-07-29  
> 前端仓库：`app-prismax-rp`，分支：`testing`  
> 前端范围：`59e9adb40360d96388a48c2f65683d528ec97740`（含）→ `eb1605a39ca09bc6baecefc32cf66c1cc813113a`  
> 后端仓库：`app-prismax-rp-backend`，分支：`testing`  
> 后端范围：`8db96a83fb63008fc5d77e2b42e0e23c593bc3e7`（含）→ `a84ef42656ec6c45119047cb2b3062b11960d4e4`  
> 数据来源：已执行 `git fetch origin`，两个仓库的本地 `testing` HEAD 均与 `origin/testing` 一致；分析时两个 worktree 均为 clean。

## 1. 总体结论

本次范围包含 4 个前端 Commit 和 4 个后端 Commit，主要影响 6 个功能域：

1. Dataset Stats 增加 Task 总时长，并调整 Robot Type 与 Operator ID 的联动行为。
2. QA Review Admin 增加统一的 **Hide test data** 开关，Task 12 过滤覆盖汇总、图表、列表、CSV 和详情。
3. Data QA 待审核列表改为由后端统一排序，并按 Task Category 聚合展示。
4. QA 审核人数从 `99 / 9 / 1` 调整为 `31 / 9 / 1`，新增 10% 少数票容忍、分数去极值和并发提交锁。
5. 新增 Round 1 历史数据修复脚本，用于将旧 99 人规则下的数据迁移到 31 人规则。
6. MCAP Camera 最低分辨率从 `640×480` 提升到 `1280×720`。

最高风险不是 UI，而是以下三项：

- `public=1` 可绕过 Robotic Data 用户鉴权并取得公开预览信息，需要产品和安全侧明确确认这是预期能力。
- Round 1 修复脚本会修改审核状态，并可能补发 QA 积分，上线前必须先 Dry Run、备份和核对幂等性。
- 31 人规则、10% 容忍和分数去极值共同改变最终判定边界，必须用边界样本和并发场景验证。

## 2. Commit List

### 2.1 前端 `app-prismax-rp`

| # | Commit | 时间（+0800） | Author | Commit message | 主要改动 |
| --- | --- | --- | --- | --- | --- |
| 1 | `59e9adb40360d96388a48c2f65683d528ec97740` | 2026-07-28 10:28 | lanmanc | `updated ui` | Dataset Stats 展示 Task 总小时数；Robot Type 切换不再清空 Operator ID |
| 2 | `d255b8ef5907073b50dde3a55de76c0a41b573b0` | 2026-07-28 11:34 | lanmanc | `updated` | QA Review Admin 增加 Hide test data，并向全部相关请求传递 `hide_task_12` |
| 3 | `e534de11b947a707eeeb626375f2554dd418ca3c` | 2026-07-28 12:28 | lanmanc | `updated from qa display order` | 移除前端排序，使用后端返回顺序；标题优先显示 `task_category` |
| 4 | `eb1605a39ca09bc6baecefc32cf66c1cc813113a` | 2026-07-29 06:09 | lanmanc | `updated for qa` | 前端识别新的 `camera_resolution_min_1280x720` 校验错误键 |

前端净改动：9 个文件，约 `+204 / -103`。

### 2.2 后端 `app-prismax-rp-backend`

| # | Commit | 时间（+0800） | Author | Commit message | 主要改动 |
| --- | --- | --- | --- | --- | --- |
| 1 | `8db96a83fb63008fc5d77e2b42e0e23c593bc3e7` | 2026-07-28 11:00 | lanmanc | `updated` | 新增 Public Preview 模式；Dataset Stats 返回 Task 总小时数并修正筛选联动 |
| 2 | `00ca93706db0b7b80d45a8d17bac022cdedafb67` | 2026-07-28 11:34 | lanmanc | `updated for qa` | QA Admin 全链路过滤 Task 12；引入审核 Gate 共识规则 |
| 3 | `f08c0f9e10b991fb41861fb5396041f84b2a627b` | 2026-07-28 12:28 | lanmanc | `updated for qa display order` | `/data/qa/uploads` 改为按 Round、剩余人数、优先级和时间统一排序 |
| 4 | `a84ef42656ec6c45119047cb2b3062b11960d4e4` | 2026-07-29 06:09 | lanmanc | `updated for qa` | Round 1 改为 31 人、分数去极值、提交加锁、增加修复脚本、分辨率提升至 1280×720 |

后端净改动：9 个文件，约 `+984 / -101`。

## 3. 详细逻辑分析

### 3.1 Dataset Stats：Task 总时长与筛选联动

后端 Task 统计结果新增 `total_hours`；前端同时兼容 `total_hours` 和 `total_duration_hours`，统一格式化为一位小数，例如 `12.3h`。Task 下拉项现在显示为：

```text
Task Name    120 (12.3h)
```

Robot Type 改变后，前端不再主动清空 Operator ID；后端 Robot Options 查询也保留 Operator 条件。这样可以维持用户已选择的组合筛选，但当新 Robot Type 与原 Operator 没有数据交集时，页面会得到空结果，而不是自动回退。

关注点：

- 后端小时单位与前端格式必须一致，不能把秒或分钟误当成小时。
- `null`、`0`、字符串数字和超长 Task 名都应正确显示。
- Robot Type 与 Operator ID 的双向约束可能使下拉选项为空，需要确认产品是否希望保留旧选择。

### 3.2 Public Preview 模式

后端为以下接口增加 `public=1`：

| Method | API | Public 行为 |
| --- | --- | --- |
| GET | `/data/downloadable-uploads?public=1` | 无需 Robotic Data 用户权限即可获取可公开 Upload/Episode 列表 |
| POST | `/data/downloadable-uploads/previews?public=1` | 无需登录即可批量取得 Preview 信息，单次最多 200 个 ID |
| GET | `/data/downloadable-episodes/{episode_id}/preview-videos?public=1` | 无需登录即可取得 Ready 且可见 Task 的视频预览 URL |

公开列表不再返回 `raw_mcap_path` 和 `raw_video_folder_path`，改为返回 `has_mcap`；Preview URL 有效期为 86400 秒。数据仍受 Task 可见性和 `DERIVED_READY` 状态限制。

但是，`public=1` 实质上是鉴权旁路。公开列表最多可返回 50,000 条，并暴露 Episode ID、Upload ID、Task ID、机器信息、时长、质量分数、上传时间等元数据。当前前端范围内未发现消费 `public=1` 的代码，因此需要确认它是否供外部页面或第三方使用。

建议在上线前明确：

- 哪些字段允许匿名公开，是否需要隐藏 Upload ID、Machine ID、Quality Score 等。
- 是否需要限流、审计、缓存、验证码或短期 Public Token。
- Preview URL 的 24 小时 TTL 是否过长。
- 枚举 Episode ID 是否构成信息泄露。
- `public=1` 之外的 `public=true`、`public=01` 等值是否应统一支持或拒绝。

### 3.3 QA Review Admin：Hide test data

前端新增统一开关，并在以下请求中显式发送 `hide_task_12=true|false`：

| Method | API | 影响 |
| --- | --- | --- |
| GET | `/data/admin/qa-review/summary` | 汇总卡排除或包含 Task 12 |
| GET | `/data/admin/qa-review/chart-stats` | 趋势图排除或包含属于 Task 12 的 Session |
| GET | `/data/admin/qa-review/uploads` | 列表、总数及筛选选项保持同一口径 |
| GET | `/data/admin/qa-review/uploads/export` | CSV 与页面使用相同过滤条件 |
| GET | `/data/admin/qa-review/uploads/{upload_id}/episodes` | 开关开启时，Task 12 Upload 详情返回 404 |

切换开关时，前端会重置分页并关闭已打开的详情弹窗，避免旧详情与新筛选条件混用。无效布尔值由后端返回 400。

主要风险是统计口径不一致：Summary、Chart、List、CSV 和 Detail 必须对同一批 Task 12 数据作相同处理。特别要检查 Chart 使用 Session 关联过滤，而其他接口主要使用 Upload 的 `task_id`。

### 3.4 Data QA 待审核列表排序

前端删除 Newest、Most uploads、Title A-Z 等本地排序，完全保留后端顺序。后端 `/data/qa/uploads` 使用 CTE 计算：

1. 过滤不可见 Task、当前角色不可审核的状态，以及当前用户已审核过的 Upload。
2. 生成 `task_category`，优先使用 Scenario，其次 Environment，最后回退 `Task {id}`。
3. 计算当前 Round 的去重 Reviewer 数、目标人数和剩余人数。
4. 先在每个 Category 内找出最高优先的代表 Upload。
5. 使用代表 Upload 的属性决定 Category 之间的顺序。
6. Category 顺序确定后，再对每个 Category 内的全部 Upload 排序。

#### 3.4.1 `Queue Priority` 的含义

`Queue Priority` 不是数据库中的独立业务字段，也不是人工设置的 Task Priority。后端根据**当前 QA 用户角色和 Upload Status** 动态生成 `queue_priority`，数值越小越优先：

| QA 角色 | Upload Status | QA Round | Queue Priority |
| --- | --- | ---: | ---: |
| Base QA | `DERIVED_READY` | 1 | 1 |
| Base QA | `DERIVED_PARTIALLY_READY` | 1 | 2 |
| Senior QA | `REVIEW_FIRST_ROUND_FAILED` | 2 | 1 |
| Senior QA | `DERIVED_READY` | 1 | 2 |
| Senior QA | `DERIVED_PARTIALLY_READY` | 1 | 3 |
| Expert QA / Super QA | `REVIEW_SECOND_ROUND_FAILED` | 3 | 1 |
| Expert QA / Super QA | `REVIEW_FIRST_ROUND_FAILED` | 2 | 2 |
| Expert QA / Super QA | `DERIVED_READY` | 1 | 3 |
| Expert QA / Super QA | `DERIVED_PARTIALLY_READY` | 1 | 4 |

例如，对 Base QA 来说，当两个 Upload 的 Round 和 Remaining 相同时，`DERIVED_READY` 会排在 `DERIVED_PARTIALLY_READY` 前面。

#### 3.4.2 两层排序逻辑

排序不是把所有 Upload 放在一起直接比较，而是分为 **Category 排序**和 **Category 内排序**两层。

第一层：为每个 `task_category` 选出最高优先的代表 Upload：

```text
Round DESC
→ Remaining ASC
→ Queue Priority ASC
→ Created ASC
→ Upload ID ASC
```

含义如下：

- `Round DESC`：Round 越高越优先，例如 Round 3 优先于 Round 2，Round 2 优先于 Round 1。
- `Remaining ASC`：距离本轮目标 Reviewer 数越近越优先，例如还差 1 人优先于还差 10 人。
- `Queue Priority ASC`：状态对应的 Priority 数值越小越优先。
- `Created ASC`：创建时间越早越优先。
- `Upload ID ASC`：前面条件全部相同时，Upload ID 越小越优先，保证排序稳定。

第二层：使用每个 Category 的代表 Upload 决定 Category 之间的顺序：

```text
代表 Upload 的 Round DESC
→ 代表 Upload 的 Remaining ASC
→ 代表 Upload 的 Queue Priority ASC
→ 代表 Upload 的 Created ASC
→ 代表 Upload 的 Upload ID ASC
→ Task Category ASC
```

因此，只要一个 Category 中存在高 Round 或接近完成的 Upload，整个 Category 就可能被提前。这里的 `Category Priority` 不是额外配置，而是从该 Category 的最高优先 Upload 派生出来的。

第三步：Category 的先后顺序确定后，再排列同一 Category 内的所有 Upload：

```text
Round DESC
→ Remaining ASC
→ Queue Priority ASC
→ Reviewer Count DESC
→ Created ASC
→ Upload ID ASC
```

最终页面顺序可以概括为：

```text
先找出每个 Category 的最高优先 Upload
→ 根据这些代表 Upload 排列 Category
→ Category 内部再按 Round、Remaining、Priority、Reviewer Count、Created、ID 排序
```

示例：Category A 中有一个 Round 2、还差 1 人的 Upload；Category B 全部是 Round 1，即使 Category B 的 Upload 创建得更早，Category A 仍会整体排在 Category B 前面。

接口新增字段：`task_category`、`qa_round`、`reviewer_count`、`required_reviewer_count`、`remaining_reviewer_count`。

主要风险：

- 不同 Task 如果 Scenario/Environment 文本相同，会被合并为同一 Category，前端标题也不再直观区分 Task ID。
- 高 Round、接近完成的 Upload 会优先，需验证低优先级数据是否长期饥饿。
- 单个高优先 Upload 会提高整个 Category 的排序位置，需要验证这是否符合产品预期。
- 前端已无排序兜底，任何 SQL 顺序变化都会直接反映到页面。
- 前端测试数据仍可能使用旧目标人数 99，需避免把过时 Fixture 当成真实契约。

### 3.5 QA Round 人数、Gate 共识与分数去极值

最终规则为：

| Round | 所需 Reviewer 数 | Gate 少数票容忍 | Score 去极值 |
| --- | ---: | ---: | --- |
| Round 1 | 31 | 10%，四舍五入后为 3 | 去掉最高 3 个和最低 3 个 |
| Round 2 | 9 | 10%，四舍五入后为 1 | 去掉最高 1 个和最低 1 个 |
| Expert | 1 | 单人直接决定 | 不去除 |

Gate 判定逻辑：

- 多数意见存在，且少数票数不超过容忍值，则 Gate 形成共识。
- 平票或少数票超过容忍值，则判定 Disagreement，进入下一 Round。
- 31 人边界：`28:3` 可形成共识，`27:4` 进入下一 Round。
- 9 人边界：`8:1` 可形成共识，`7:2` 进入 Expert。

Score 判定逻辑：

- 先按当前 Round 人数计算两端各移除约 10%，再计算剩余分数的最大最小差。
- 去极值后的 Score Gap `>= 30` 判定 Disagreement。
- 最终 QA Score 仍取该决定性 Round **全部分数** 的中位数，不使用去极值后的集合。

需要特别验证 `29` 与 `30` 的 Gap 边界，以及“去极值集合用于判断、全量集合用于最终中位数”是否符合产品预期。

### 3.6 并发审核提交

审核提交接口现在先对 Upload 执行 `SELECT ... FOR UPDATE`，再检查当前用户是否重复提交并插入 Review。作用是将同一 Upload 的并发审核串行化，避免：

- 两名 Reviewer 同时成为第 31 人时重复推进状态。
- 同一用户并发请求绕过重复检查。
- 状态推进和积分发放重复执行。

锁只解决应用事务中的并发问题；仍应确认数据库层是否有 Reviewer + Upload + Round 唯一约束，以及历史重复行是否会被 `COUNT` 错误计入人数。

### 3.7 Round 1 历史数据修复脚本

新增：

```bash
python -m app_prismax_data_pipeline.reconcile_qa_round_one
python -m app_prismax_data_pipeline.reconcile_qa_round_one --apply
python -m app_prismax_data_pipeline.reconcile_qa_round_one --upload-id <ID>
```

默认是 Dry Run。脚本主要处理 `DERIVED_READY`、`DERIVED_PARTIALLY_READY` 和旧的 `REVIEW_FIRST_ROUND_FAILED`：

- Round 1 已达到 31 人：按新规则重新计算，推进到成功或失败状态。
- 旧状态为 Round 1 Failed 但人数不足 31：根据 Episode Ready 情况退回待审核队列。
- 已存在 Round 2 Review：跳过，避免覆盖已经开始的下一轮。
- 没有 Ready Episode 或属于终态：跳过。
- Apply 模式对每个 Upload 加行锁，并可能根据最终决定补发 QA 积分。

上线执行建议：先做数据库快照，只对单个 Upload Dry Run 与 Apply 验证，再全量 Dry Run，对变更数量和状态分布人工复核后执行全量 Apply。Apply 后再次 Dry Run，预期没有新的待变更项；同时核对积分交易未重复生成。

### 3.8 Camera 最低分辨率提升

MCAP Camera 最低分辨率由 `640×480` 调整为 `1280×720`，新的失败键为：

```text
camera_resolution_min_1280x720
```

前端 Upload Dashboard 和 Robotic Data Admin 将其显示为 `E-003: Camera resolution is below 1280×720`，并保留旧键 `camera_resolution_min_640x480` 的兼容文案，以便历史记录仍可读取。

该变化会使之前可通过的设备数据开始失败，需确认 Device Spec、上传文档、已有测试样本和 Worker 部署顺序同步更新。

### 3.9 非业务文件进入后端 Commit

本次后端范围还包含：

- `.DS_Store`：已被 `.gitignore` 覆盖，但因文件已被 Git 追踪，仍出现在 Commit 中。
- `app_prismax_forum/forum.db`：73 KB SQLite 文件，当前包含 5 张表且所有表均为 0 行，不含现有用户数据；该文件当前未被 `.gitignore` 忽略。

虽然本次检查未发现 `forum.db` 中存在数据，仍建议从 Git 索引移除两个本地生成文件，并将 `forum.db` 或合适的数据库文件模式加入忽略规则，避免以后误提交 Email、密码 Hash 或论坛内容。

## 4. 风险分级

| 等级 | 风险 | 可能影响 | 建议 |
| --- | --- | --- | --- |
| P0 | `public=1` 绕过用户鉴权 | 数据目录和媒体 URL 可被匿名枚举 | 产品/安全确认字段范围；做匿名访问、限流和枚举测试 |
| P0 | Reconcile Apply 修改状态并可能补发积分 | 错误推进状态、重复积分、难以回滚 | DB 快照、Dry Run、单条验证、全量复核、幂等回归 |
| P0 | Round 1 从 99 改为 31 | 存量 Upload 状态与新规则不一致 | 脚本执行前后做状态、Review 数和积分对账 |
| P1 | 10% Gate 容忍和 Score 去极值 | 判定结果与旧规则不同 | 覆盖 28:3/27:4、8:1/7:2、Gap 29/30 |
| P1 | 审核并发临界点 | 重复推进、重复积分或丢 Review | 30→31 并发、同用户双提交、事务回滚测试 |
| P1 | 同 Scenario 合并 Category | 不同 Task 混组，显示和优先级不符合预期 | 同名 Scenario、多 Task、多 Round 排序测试 |
| P1 | Task 12 各接口过滤口径不同 | Summary、Chart、CSV 和列表数值不一致 | 建立固定 Task 12/非 Task 12 对照数据集 |
| P1 | 分辨率标准直接提升 | 旧设备和历史样本突然失败 | 1279×720、1280×719、1280×720 边界验证 |
| P2 | Robot/Operator 选择保留 | 新组合无交集导致空结果 | 验证空态、选项刷新和用户恢复路径 |
| P2 | Public URL 有效期 24 小时 | URL 泄露后的暴露窗口较长 | 验证过期、重签名和缓存策略 |
| P2 | 二进制本地文件进入 Git | 后续可能提交个人或敏感数据 | 移出 Git 索引，完善 ignore 和 CI 检查 |
| P2 | React 测试存在 `act(...)` Warning | 异步断言可能不稳定 | 用 `waitFor`/`act` 收敛异步状态更新 |

## 5. E2E / API 测试用例

### 5.1 Public Preview

| ID | 场景 | 操作/数据 | 预期结果 | 优先级 |
| --- | --- | --- | --- | --- |
| PUB-001 | 未登录且无 `public=1` | 调用三个 Preview API | 返回 401/403，不返回业务数据 | P0 |
| PUB-002 | Public 列表成功 | 未登录调用 `downloadable-uploads?public=1` | 仅返回可见 Task、Ready Episode；无 raw path | P0 |
| PUB-003 | Public 列表字段最小化 | 检查响应字段 | `has_mcap` 正确；不存在 `raw_mcap_path`、`raw_video_folder_path` | P0 |
| PUB-004 | 隐藏 Task | Public 查询隐藏 Task 的 Episode | 不出现在列表，详情不可访问 | P0 |
| PUB-005 | 非 Ready Episode | 使用 Failed/Processing Episode ID | 列表不返回，详情返回 404 | P0 |
| PUB-006 | 批量上限 | POST 200 和 201 个 ID | 200 个可处理；201 个返回 400 | P1 |
| PUB-007 | ID 枚举 | 连续请求存在/不存在 ID | 不存在 ID 不泄露额外信息；有合理限流与审计 | P0 |
| PUB-008 | URL 生命周期 | 获取 URL 后立即、过期后访问 | 有效期内可播放；过期后拒绝并可重新获取 | P1 |
| PUB-009 | Public 参数边界 | `1/0/true/01/空值/重复参数` | 行为符合明确契约，不意外开启 Public | P1 |
| PUB-010 | 大列表性能 | 构造接近 50,000 条数据 | 延迟、内存、响应大小在阈值内，不拖垮服务 | P1 |

### 5.2 Dataset Stats 与 QA Admin

| ID | 场景 | 操作/数据 | 预期结果 | 优先级 |
| --- | --- | --- | --- | --- |
| ADM-001 | Task 总小时数 | 准备已知时长数据 | 下拉 Count 和 Hours 均正确，Hours 保留一位小数 | P1 |
| ADM-002 | 空/零时长 | `total_hours=null/0` | UI 不显示 `NaN`/`undefined`，格式符合设计 | P1 |
| ADM-003 | Robot 保留 Operator | 选择 Operator 后切换 Robot Type | Operator 不被主动清空，请求条件与 UI 一致 | P1 |
| ADM-004 | 无交集组合 | Robot 与 Operator 没有共同数据 | 显示正确空态，可恢复筛选，不使用旧数据 | P1 |
| ADM-005 | 开启 Hide test data | 准备 Task 12 与普通 Task 数据 | Summary、Chart、List、CSV 全部排除 Task 12 | P0 |
| ADM-006 | 关闭 Hide test data | 使用同一数据集关闭开关 | 五个数据面均重新包含 Task 12 | P0 |
| ADM-007 | 切换时分页重置 | 在第 2 页切换开关 | 回到第 1 页，总数和列表同步刷新 | P1 |
| ADM-008 | 切换时关闭详情 | 打开详情后切换开关 | 旧 Modal 关闭；不能继续展示被隐藏数据 | P1 |
| ADM-009 | 隐藏后直接访问详情 | `hide_task_12=true` 请求 Task 12 Upload | 返回 404 | P0 |
| ADM-010 | CSV 对账 | 相同 Filter 下载 CSV | 行数、Upload 集合与列表筛选一致 | P0 |
| ADM-011 | 非法布尔值 | `hide_task_12=abc` | 返回 400；前端给出可理解错误 | P1 |

### 5.3 QA 共识、排序与并发

| ID | 场景 | 操作/数据 | 预期结果 | 优先级 |
| --- | --- | --- | --- | --- |
| QA-001 | Round 1 未满 | 30 个有效 Reviewer | 不完成 Round 1 | P0 |
| QA-002 | Round 1 达标 | 31 个有效 Reviewer | 立即按新规则计算并推进 | P0 |
| QA-003 | Round 1 Gate 容忍边界 | 28:3 | 形成多数共识，不因该 Gate 升级 | P0 |
| QA-004 | Round 1 Gate 超限 | 27:4 | Disagreement，进入 Round 2 | P0 |
| QA-005 | Round 2 Gate 容忍边界 | 8:1 | 形成多数共识 | P0 |
| QA-006 | Round 2 Gate 超限 | 7:2 | Disagreement，进入 Expert | P0 |
| QA-007 | Expert 决定 | 1 个 Expert Review | 单人结果成为决定性结果 | P0 |
| QA-008 | Score 去极值 | 31 分数含 3 个高、3 个低异常值 | 去除两端各 3 个后计算 Gap | P0 |
| QA-009 | Score Gap 边界 | 去极值后 Gap=29 和 Gap=30 | 29 不升级；30 升级 | P0 |
| QA-010 | 最终中位数口径 | 异常值会影响全量中位数的样本 | 最终分数取全量中位数，结果与规则一致 | P1 |
| QA-011 | 同 Upload 两用户并发 | 第 30 人后两用户同时提交 | 两条 Review 均保留，只推进一次、奖励一次 | P0 |
| QA-012 | 同用户双提交 | 同一用户并发发送两次 | 只接受一次；另一请求明确拒绝 | P0 |
| QA-013 | 事务失败回滚 | 在状态推进或积分阶段注入失败 | Review、状态、积分保持一致，无半提交 | P0 |
| QA-014 | 排除已审核 Upload | 用户已审核某 Upload | 不再返回给同一用户 | P1 |
| QA-015 | 同 Category 排序 | 多 Round、不同剩余人数和创建时间 | 严格按 Round、Remaining、Priority、Created、ID 排序 | P1 |
| QA-016 | 同名 Scenario 不同 Task | 两 Task 使用同一 Scenario | 聚合和标题行为符合产品确认，无误导 | P1 |
| QA-017 | Category 饥饿 | 持续新增高优先级数据 | 低优先级 Category 不会永久无法获得 Review | P2 |

### 5.4 Reconcile 脚本与分辨率

| ID | 场景 | 操作/数据 | 预期结果 | 优先级 |
| --- | --- | --- | --- | --- |
| MIG-001 | 默认 Dry Run | 不带 `--apply` 执行 | 输出计划但数据库零写入 | P0 |
| MIG-002 | 单条 Apply | 使用 `--upload-id` | 只修改指定 Upload，状态符合新规则 | P0 |
| MIG-003 | 31 人重新计算 | Round 1 ≥31 且无 Round 2 | 推进到正确成功/失败状态 | P0 |
| MIG-004 | 旧失败且不足 31 | Episode 全 Ready/部分 Ready | 分别回退到正确待审核状态 | P0 |
| MIG-005 | 已有 Round 2 | Round 2 已提交 Review | 脚本跳过，不覆盖现有流程 | P0 |
| MIG-006 | 无 Ready Episode/终态 | 构造两类 Upload | 均跳过并给出原因 | P1 |
| MIG-007 | 重复 Apply | 对同一数据执行两次 | 第二次无额外状态变化、无重复积分 | P0 |
| MIG-008 | 历史重复 Review 行 | 同 Reviewer 存在重复行 | 不错误抬高有效 Reviewer 数；若会抬高应先清洗 | P0 |
| RES-001 | 宽度不足 | `1279×720` | E-003，键为 `camera_resolution_min_1280x720` | P0 |
| RES-002 | 高度不足 | `1280×719` | E-003 | P0 |
| RES-003 | 边界通过 | `1280×720` | 校验通过 | P0 |
| RES-004 | 更高分辨率 | `1920×1080` | 校验通过 | P1 |
| RES-005 | 多 Camera 混合 | 一个通过、一个不足 | Episode 校验失败并指出失败 Camera | P1 |
| RES-006 | 历史错误展示 | 打开旧 `640×480` 错误记录 | 前端仍能显示旧 E-003 文案，不显示 Unknown | P1 |

## 6. 建议的执行顺序

1. 先确认 Public Preview 的产品和安全边界，再做 PUB-001～PUB-010。
2. 用固定 Task 12 对照数据执行 ADM-005～ADM-010，完成跨接口数据对账。
3. 在隔离环境构造 31/9/1 Reviewer 数据，完成 QA Gate、Score 和并发边界测试。
4. 对生产副本执行 Reconcile Dry Run；审核输出后再做单条 Apply 和重复 Apply。
5. 用真实 MCAP 样本覆盖 1279×720、1280×719、1280×720 和多 Camera。
6. 最后执行前端完整 Build/Test、后端完整 Test Suite 和关键接口性能测试。

## 7. 已执行验证

### 7.1 前端定向测试

```bash
npm test -- --runInBand --watchAll=false \
  src/components/Admin/DatasetStatsAdmin.test.js \
  src/components/Admin/QAReviewTab/AdminQAReviewStats.test.js
```

结果：2 个 Test Suite 通过，7 个 Test 通过。

发现非阻断 Warning：`ReactDOMTestUtils.act` 已废弃，以及 QA Review Admin 测试存在异步状态更新未包裹在 `act(...)` 中的提示。建议修复，避免未来出现 Flaky Test。

### 7.2 后端定向测试

```bash
python3 -m unittest \
  app_prismax_data_pipeline.test_qa_helper \
  app_prismax_data_worker.test_scale_validate_mcap
```

结果：19 个 Test 全部通过。

### 7.3 当前自动化缺口

- 缺少 Public Preview 三个接口的鉴权、安全边界和字段收敛测试。
- 缺少 QA Admin 五个数据面的集成对账测试。
- 缺少 `/data/qa/uploads` SQL 排序与同名 Category 的集成测试。
- 缺少 Reconcile 脚本的数据库级 Dry Run、Apply、重复 Apply 测试。
- 缺少真正并发的第 31 人提交和同用户双提交测试。
- 缺少前后端契约测试来保证 `31 / 9 / 1` 与新增字段同步。

## 8. 发布准入建议

满足以下条件后再放行：

- Public Preview 已通过产品和安全确认，匿名响应字段、限流和 URL TTL 有明确结论。
- 31/9/1 的 Gate、Score Gap 和最终中位数边界用例全部通过。
- 并发第 31 人测试确认状态和积分仅推进一次。
- Reconcile 在生产副本上 Dry Run、单条 Apply、重复 Apply 均通过，并有数据库回滚方案。
- Task 12 的 Summary、Chart、List、CSV、Detail 对账无差异。
- 1280×720 标准已同步到产品文档、设备要求、Worker 与前端错误文案。
- `.DS_Store` 和 `forum.db` 已从 Git 追踪中清理，并增加防止再次提交的规则。
