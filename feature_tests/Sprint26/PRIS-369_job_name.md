# PRIS-369 Job 名称：逻辑分析与测试用例

> 分析日期：2026-10-15（UTC+8）  
> 范围：`app-prismax-rp-backend`、`app-prismax-rp`、`sdk-vla-foundry`  
> 三条都已合进各自 `testing`。

| 仓库 | Commit | 时间（作者时区 / 北京时间） | Author | Message |
| --- | --- | --- | --- | --- |
| backend | `970a1ade54abd9d49ffd9d1780b1a82333f17e93` | 作者 2026-10-14 01:11 `-0700` / 10-14 16:11；合入 10-14 14:47 `-0700` / 10-15 05:47 | Aparna Rangamani | `PRIS-369: add job name support` |
| backend | `2f3a08d2a6609659650356a14f47e0f679de6b86` | 2026-10-14 14:56 `-0700` / 10-15 05:56 | aparna-prismax | Merge PR #85 `PRIS-369-add-job-name` |
| admin / operator 前端 | `eddc556` | 2026-10-14 14:43 `-0700` / 10-15 05:43 | Aparna Rangamani | `PRIS-369: add job name support` |
| admin / operator 前端 | `bdcba3d` | 2026-10-14 14:57 `-0700` / 10-15 05:57 | aparna-prismax | Merge PR #90 `PRIS-369-add-job-name` |
| SDK | `1d23320` | 2026-10-14 14:36 `-0700` / 10-15 05:36 | Aparna Rangamani | `feat: add job name to jobs listing` |
| SDK | `f7f51f6` | 2026-10-14 21:17 `-0700` / 10-15 12:17 | aparna-prismax | Merge PR #3 `feature/add-job-name` |

SDK 版本从 `0.3.1` 升到 `0.3.2`。上传仍用 `job_id`，这次只把名称加进列表。

---

## 1. 业务目标

Job 除了 `JOB-<数字>`，还要有一个给人看的名称：

- 新建必须填名称。最长 80 个字符。只去掉首尾空白，中间的空格保留。
- 全部未删除 Job 共用一个名称空间，不区分大小写，也不按操作员或订单拆开。
- 软删除之后名称可以再用。
- 迁移前已经存在的 Job 保持 `job_name = NULL`。列表第一行退回 `JOB-<id>`。用界面编辑这种旧 Job 时必须补上名称；接口如果根本不传 `job_name`，可以继续保持 `NULL`。

---

## 2. 数据规则

迁移脚本：`app_prismax_data_pipeline/sql/20261013_data_jobs_job_name.sql`。测之前要先跑过。

```text
请求里的 job_name
    │  只做 strip，不压缩中间空白
    ▼
validate_job_name
    │  缺失、非字符串、空、纯空白  → 400  field=job_name  msg=job_name is required
    │  strip 之后超过 80 字         → 400  field=job_name  msg=job_name must be at most 80 characters
    ▼
_jobs_job_name_taken
    │  deleted_at IS NULL
    │  lower(job_name) 相同
    │  更新时排除当前 job_id
    │  命中                         → 409  field=job_name  msg=That job name is already in use.
    ▼
data_jobs.job_name
    │  可空
    │  CHECK：NULL，或 char_length 在 1 到 80，且值等于 btrim(值)
    │  唯一索引：lower(job_name) WHERE deleted_at IS NULL
    ▼
并发撞上唯一索引时同样返回上面的 409
```

唯一性不看操作员、订单、付款状态。`NULL` 不进唯一索引，所以多条历史 Job 可以同时没有名称。

和订单名称（PRIS-384）的差别：

| | 订单 `name` | Job `job_name` |
| --- | --- | --- |
| 空白 | 连续空白压成一个空格 | 只去首尾，中间空格原样保存 |
| 唯一范围 | 同一组织 | 全表未删除 Job |
| 取消 / 删除后 | 取消的订单仍占名称 | 软删除后名称可再用 |
| 重名响应 | `409` `duplicate_order_name`，文案带上名称 | `409`，`field=job_name`，文案 `That job name is already in use.` |

前端看到 `field === 'job_name'` 时，错误留在名称输入框下面，弹窗不关。其它保存失败走弹窗底部的通用错误。

---

## 3. 后端

### 3.1 创建

`POST /data/admin/jobs`。Admin JWT。`job_name` 必填，通过后再校验用户、订单、任务、时薪、截止日期。

重名在 `INSERT` 之前查一次。两条请求同时通过检查时，唯一索引再挡一次，响应仍是同一句 `409`。失败不留下新行。

### 3.2 更新

`PATCH /data/admin/jobs/<job_id>`。

| 请求 | 结果 |
| --- | --- |
| body 里没有 `job_name` | 不校验名称；`COALESCE` 保留库里的值，历史 `NULL` 继续是 `NULL` |
| `job_name` 为 `""`、纯空白、非字符串 | `400` `job_name is required` |
| strip 后超过 80 | `400` `job_name must be at most 80 characters` |
| 与另一条未删除 Job 只差大小写 | `409`，`UPDATE` 不生效 |
| 与自己当前名称相同，或只改大小写 | 通过，库里写成新的写法 |

界面编辑总会带上 `job_name`。所以上面「不传名称则保留 NULL」只能用接口打出来。

### 3.3 读和搜索

`_jobs_fetch` 的每条 Job 都带 `job_name`，没有名称时是 `null`，不是空字符串。操作员列表 `GET /data/jobs`、Admin 看某个操作员的 Job、Admin 全量列表、单条详情都走这里。

全量搜索：`GET /data/admin/jobs/all`。

| 参数 | 行为 |
| --- | --- |
| `job_id` | 精确匹配 |
| `order_id` | 精确匹配 |
| `job_name` | 先 strip，再截到 80 字；空则不加这个条件。`ILIKE '%词%'`，不区分大小写。`%`、`_`、`!` 按字面量转义，转义符是 `!` |
| 三个一起传 | `AND` |

已软删除的 Job 不出现在列表和搜索里。

### 3.4 SDK 接口

`GET /v1/data/jobs`，Upload API key。只返回当前 key 对应用户、且未删除的 Job，按 `created_at` 倒序。

每条增加 `job_name`。历史 Job 该字段是 `null`。`job_id`、截止日期、时薪、付款状态、任务列表不变。没有按名称搜索。

---

## 4. 前端 `eddc556`

两处列表共用 `JobCell`：

| 页面 | 订单号 |
| --- | --- |
| Admin → Jobs（全量，可搜索） | 有名称时，名称下面同时有 `JOB-<id>` 和 `ORD-<id>` |
| Admin 看某个操作员的 Assigned jobs | 同上 |
| 操作员 Upload Dashboard 的 Assigned jobs | 有名称时下面只有 `JOB-<id>`，不显示订单号 |

单元格规则：

- 有名称：第一行是名称，`title` 是完整名称。超过约 180px 省略。有名称才在下面再写一遍 `JOB-<id>`。
- 没有名称：第一行就是 `JOB-<id>`，下面不再重复 ID。
- 列标题从 `Job ID` 改成 `Job`。

### 4.1 表单

创建和编辑都有 **Job name**，`maxLength=80`，右侧字数 `当前长度/80`。创建占位符是 `Name this job`，编辑占位符是 `JOB-<id>`。弹窗标题仍是 `New job` 或 `Edit JOB-<id>`，不用名称当标题。

提交前 `trim`。结果为空：输入框下出现 `Enter a job name.`，不发请求。输入一改，这条错误清掉。

`409` 或其它 `field=job_name` 的 `msg` 显示在名称字段下，弹窗留着，已填内容还在。

编辑一张 `job_name=null` 的旧 Job 时，输入框是空的，不保存就不能只改时薪或任务。

### 4.2 搜索

只在 Admin 全量 Jobs 页。占位符：`Search job name, JOB-123 or ORD-45`。回车或点 Search。

| 输入 | 请求 |
| --- | --- |
| 空白 | 清空条件 |
| 整段匹配 `JOB-<数字>` 或 `ORD-<数字>`，不区分大小写 | `job_id` 或 `order_id`，不是名称搜索 |
| 其它任何文字 | `job_name=<trim 后的原文>` |

因此一条真的叫 `JOB-12` 的 Job，在搜索框里输入 `JOB-12` 会去找 12 号 Job，不会按名称找。要按名称找它，需要输入能命中子串、又不符合这个整段格式的词，例如 `JOB-12 `（末尾空格在 trim 后仍是 `JOB-12`，还是 ID 搜索）或名称里的其它片段。纯 `JOB-12` 这个名字只能靠更短的子串（如 `JOB`）或接口直接传 `job_name=JOB-12` 搜到。

操作员自己的 Assigned jobs 没有搜索框。

### 4.3 这次没改到名称的地方

按现状测，不要报缺陷：

- 点开 Job 的详情抽屉，标题仍是 `<job_id> · <第一个任务名>`，meta 里的 Job ID 仍是数字，没有 `job_name`。
- 删除确认仍是 `Delete JOB-<id>?`。
- Unmark 确认仍是 `JOB-<id>`。
- 编辑弹窗标题仍是 `Edit JOB-<id>`。

---

## 5. SDK `1d23320`（0.3.2）

`prismax.list_jobs()` 原样返回 `/v1/data/jobs`，其中包含 `job_name`。

CLI `prismax jobs` 表头在 Job ID 后面增加 **Job Name**。`job_name` 为 `null` 或缺失时这一列空白，不回退成 `JOB-<id>`。没有任务的 Job 仍打出一行，任务三列为空。

上传命令仍是 `--job-id`。README 说明用 `list_jobs()` 看 ID、名称和任务；允许上传的任务范围还是该 Job 的任务，不按名称匹配。

---

## 6. 已知实现口径

1. 重名不区分大小写，范围是所有未删除 Job，不是同一个操作员或同一张订单。
2. 只去掉首尾空白。`Kitchen  run` 和 `Kitchen run` 是两个名称。
3. 软删除后该名称可以再建。删除的 Job 不再出现在 Admin 列表、操作员列表和 SDK 列表里。
4. 编辑自己并保持原名可以通过。只改大小写也可以，库里的值变成新写法。
5. 历史 `job_name` 是 `null`。列表第一行是 `JOB-<id>`。界面编辑必须补名称；`PATCH` 不带 `job_name` 则继续为 `null`。
6. 重名和名称校验失败时弹窗不关，错误在名称字段下。
7. 搜索框里完整的 `JOB-<数字>` / `ORD-<数字>` 走 ID，不走名称。
8. 名称搜索是包含匹配，不区分大小写，`%` 和 `_` 是字面量。
9. 详情抽屉、删除确认、Unmark 确认、编辑标题都不显示名称。
10. 输入框 `maxLength=80`，第 81 个字要用接口打。
11. SDK 不提供按名称搜索，也不接受用名称代替 `job_id` 上传。

---

## 7. 测试数据与环境

- 目标库已执行 `20261013_data_jobs_job_name.sql`。未执行时创建会在写库阶段失败，到不了 `That job name is already in use.`
- Admin 账号，能开 Admin → Jobs，也能开某个操作员的 Assigned jobs。
- 两个操作员账号：A 有一张已命名 Job、一张 `job_name=null` 的历史 Job；B 用来确认跨人也不能重名。A 的 Upload API key 对应 SDK 0.3.2。
- 一张已软删除、名称仍留在库里的 Job，用来确认名称可复用、列表里不再出现。
- 浏览器：桌面 Chrome。抓包看 `POST /data/admin/jobs`、`PATCH /data/admin/jobs/<id>`、`GET /data/admin/jobs/all`、`GET /v1/data/jobs`。

---

## 8. 测试用例

优先级：P0 必测 / P1 重要 / P2 补充。

| ID | 模块 | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- | --- |
| PRIS-369-001 | 创建 | P0 | 新建必填名称 | Admin 已登录，能新建 Job | 打开 New job，名称留空，其余必填项填完，保存 | 弹窗不关；名称下出现 `Enter a job name.`；Network 没有 `POST /data/admin/jobs` |
| PRIS-369-002 | 创建 | P0 | 纯空白不算名称 | 同上 | 名称填三个空格后保存 | 同样出现 `Enter a job name.`；不发请求 |
| PRIS-369-003 | 创建 | P0 | 首尾空白被去掉 | 还没有名为 `Cable insertion` 的未删除 Job | 名称填 `  Cable insertion  `，填完订单、任务、时薪、截止日期，保存 | `201`；请求体 `job_name` 为 `Cable insertion`；列表第一行是这个名称，下面有 `JOB-<id>` 和 `ORD-<id>`；悬停 `title` 是完整名称 |
| PRIS-369-004 | 创建 | P0 | 全表重名 | 任一操作员已有未删除 Job `Biology batch` | 给另一个操作员再建一张，名称用同样文字 | 弹窗不关；名称下原文是 `That job name is already in use.`；没有新 Job |
| PRIS-369-005 | 创建 | P0 | 大小写算重名 | 已有 `Biology batch` | 再用 `biology BATCH` 创建 | `409`，`field` 为 `job_name`，文案同上；库里没有新行 |
| PRIS-369-006 | 创建 | P1 | 中间空格不算同一个名字 | 已有 `Kitchen run` | 创建 `Kitchen  run`（run 前两个空格） | 创建成功；列表显示带两个空格的名称。再创建去掉多余空格的 `Kitchen run` 则 `409` |
| PRIS-369-007 | 创建 | P1 | 80 个字符 | 该名称未被占用 | 输入正好 80 个字符并保存 | 创建成功；单元格超出约 180px 的部分省略，`title` 仍是全部 80 字；字数显示 `80/80` |
| PRIS-369-008 | 创建 | P1 | 第 81 个字符 | 打开新建表单 | 连续输入或粘贴 81 个字符；再用接口 `POST /data/admin/jobs`，`job_name` 为 81 个 `x` | 输入框停在 80。接口返回 `400`，`field=job_name`，`msg` 为 `job_name must be at most 80 characters`，不创建 |
| PRIS-369-009 | 创建 | P2 | 80 个汉字 | 名称未被占用 | 提交 80 个汉字；再用接口提交 81 个汉字 | 80 个汉字成功。81 个汉字返回 `400` `job_name must be at most 80 characters` |
| PRIS-369-010 | 创建 | P1 | 软删除后名称可再用 | 一张名为 `Retired batch` 的 Job 已软删除 | 用同一名称新建 | 创建成功。Admin 列表和该操作员列表里只有新的这一张，旧的不再出现 |
| PRIS-369-011 | 编辑 | P0 | 不改名称保存 | 一张已命名、可编辑的 Job | 打开 Edit，不改名称，改 due date 后保存 | `200`；请求仍带原来的 `job_name`；列表名称不变，截止日期已更新 |
| PRIS-369-012 | 编辑 | P0 | 改成别人的名称 | 另一张未删除 Job 已占用目标名 | 把当前名称改成那个名称，只改大小写，保存 | 名称下出现 `That job name is already in use.`；弹窗不关；刷新后名称仍是旧值 |
| PRIS-369-013 | 编辑 | P1 | 只改自己的大小写 | 当前名称是 `Biology batch` | 改成 `biology batch` 并保存 | 保存成功；列表显示新的大小写 |
| PRIS-369-014 | 编辑 | P0 | 界面编辑旧 Job 必须补名称 | 一张 `job_name=null` 的历史 Job | 打开 Edit，名称留空，只改 notes 以外的可编辑项（时薪或截止日期）后保存；再填一个未占用的名称保存 | 第一次不发请求，提示 `Enter a job name.`。第二次成功，列表从只显示 `JOB-<id>` 变成名称在上、`JOB-<id>` 在下 |
| PRIS-369-015 | 编辑 | P1 | 接口不传名称 | 用 Admin token `PATCH /data/admin/jobs/<id>`，body 不含 `job_name`，只改 `due_date` 等原必填字段 | 对有名称的 Job 打一次；对 `job_name=null` 的 Job 再打一次 | 两次都成功。有名称的名称不变；空名的响应里 `job_name` 仍是 `null` |
| PRIS-369-016 | 编辑 | P2 | 接口把名称改成空白 | `PATCH` body 带 `"job_name": "   "` | 看响应和库 | `400`，`msg` 为 `job_name is required`，`field` 为 `job_name`；库里的名称不变 |
| PRIS-369-017 | 列表 | P0 | Admin 全量列表两种样子 | 准备有名称、无名称各一张，且都有 `order_id` | 打开 Admin → Jobs | 有名称：第一行名称，下面 `JOB-<id>` 和 `ORD-<id>`。无名称：只有第一行 `JOB-<id>`，没有空的名称行，也没有重复的 ID。列标题是 `Job` |
| PRIS-369-018 | 列表 | P0 | 操作员列表不显示订单号 | 用有名称 Job 的操作员打开 Upload Dashboard → Assigned jobs；再用 Admin 打开该操作员的 Assigned jobs | 看 Job 列 | 操作员：名称加下面的 `JOB-<id>`，没有 `ORD-`。Admin 看该操作员：名称下面同时有 `JOB-<id>` 和 `ORD-<id>`。无名称时两边都只显示 `JOB-<id>` |
| PRIS-369-019 | 列表 | P1 | 详情抽屉不用名称 | 点开一张有名称的 Job | 看抽屉标题和 meta | 标题仍是 `<数字 job_id> · <任务名>`；Job ID 是数字。名称只出现在背后的表格单元格里 |
| PRIS-369-020 | 列表 | P2 | 删除和 Unmark 文案 | 一张有名称、已付款的 Job | 点 Delete；再点 Unmark | 确认句仍是 `Delete JOB-<id>?` 和 `JOB-<id>`，不出现名称。取消后 Job 还在 |
| PRIS-369-021 | 搜索 | P0 | 按名称子串、不区分大小写 | 存在 `Biology batch`，另有名称不含这几个字母的 Job | 在 Admin Jobs 搜索 `batch`，再搜 `BIOLOGY` | 两次都只留下名称包含该词的 Job；请求是 `job_name=batch` 和 `job_name=BIOLOGY`。Clear 后回到未过滤列表 |
| PRIS-369-022 | 搜索 | P0 | `JOB-` / `ORD-` 仍是精确 ID | 已知 `JOB-12` 属于 `ORD-45`，且没有任何 Job 的名称恰好是别的号 | 分别搜索 `job-12` 和 `ORD-45` | 第一次请求 `job_id=12`，只出这一张。第二次请求 `order_id=45`，只出该订单下未删除的 Job。都不会带 `job_name` |
| PRIS-369-023 | 搜索 | P1 | 名叫 `JOB-12` 时搜索框不会按名称查 | 有一张未删除 Job，名称就是 `JOB-12`，它的 `job_id` 不是 12；另有真正的 12 号 Job | 搜索框输入 `JOB-12` 回车；再用接口 `GET /data/admin/jobs/all?job_name=JOB-12` | 搜索框结果是 `job_id=12` 那张，不是名叫 `JOB-12` 的那张。接口按名称能搜到名叫 `JOB-12` 的 Job |
| PRIS-369-024 | 搜索 | P1 | 通配符按字面量 | 有名称 `100%` 和名称 `100x` 的两条 Job | 搜索 `100%`；再搜索 `_` | `100%` 只命中名称里真有百分号的那条，不会变成「匹配全部」。单独的 `_` 不会匹配所有单字符名称，只命中名称里含有下划线的 Job |
| PRIS-369-025 | 搜索 | P2 | 搜不到已删除的名称 | `Retired batch` 已软删除，没有同名的未删除 Job | 搜索 `Retired` | 结果为空（或只有别的未删除且名称包含 Retired 的 Job），不出现已删除那张 |
| PRIS-369-026 | 搜索 | P2 | 超过 80 字的搜索词 | 有一张名称正好 80 字的 Job | 搜索框粘贴这 80 字再在末尾加一个 `z`，搜索 | 后端把 `job_name` 截成前 80 字再做包含匹配，这张 Job 仍能出现 |
| PRIS-369-027 | SDK | P0 | `list_jobs` 带名称 | 操作员 A 有一张名为 `Biology batch` 的 Job 和一张 `job_name=null` 的 Job；安装或指向 testing 的 SDK 0.3.2 | `prismax.list_jobs()` 和 `prismax jobs` | 接口每条都有 `job_name`。有名称的是 `Biology batch`，旧 Job 是 `null`。CLI 表头含 `Job Name`；有名称的那一列是 `Biology batch`，旧 Job 那一列空白，不是 `JOB-<id>`。只包含 A 的未删除 Job |
| PRIS-369-028 | SDK | P1 | 没有任务的命名 Job | A 有一张有名称、任务为空的 Job | `prismax jobs` | 仍打印一行：Job ID、Job Name、截止日期、时薪、付款状态有值，Task ID / Task Name / Assigned Hours 为空 |
| PRIS-369-029 | SDK | P1 | 上传仍用 Job ID | A 的某张已命名 Job 上有允许上传的任务 | `prismax upload` 使用该 Job 的数字 `--job-id`，场景用该 Job 的任务 | 上传会话能创建。把 `--job-id` 换成名称字符串则失败，SDK 没有按名称解析 Job |
| PRIS-369-030 | 回归 | P1 | 删除后操作员和 SDK 都看不到 | 删除 A 的一张已命名 Job | A 刷新 Assigned jobs；再用 A 的 key 调 `GET /v1/data/jobs` | 两边都没有这张 Job。用它的名称可以再建一张新的 |
| PRIS-369-031 | 回归 | P2 | 非 Admin 不能建 Job | 操作员 token | `POST /data/admin/jobs`，body 含合法 `job_name` | 被 Admin 鉴权拒绝；不创建 Job |
