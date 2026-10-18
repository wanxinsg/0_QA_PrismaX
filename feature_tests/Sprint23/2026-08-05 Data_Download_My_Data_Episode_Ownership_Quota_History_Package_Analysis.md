m# Data Download / My Data：Episode 所有权、月度额度、下载历史与 Package 模型重构分析

> <span style="color:#2563eb">蓝色字体 = 今日（2026-08-05）补充 / 修订内容（含 `prismax-marketing-rp` testing 重拉后前端分析、`470ab3d`~HEAD 后端鉴权改版）</span>
>
> 拆分来源：`Commit_6e44b469_Data_Download_Analysis.md`  
> 核心后端 Commit：`6e44b469a6928e2e31bde46d53a24e77245e5016`（`updated for new data download`）  
> <span style="color:#2563eb">后续补充 Commit Range（含）：`470ab3dd6073cb60093b5084cbeaf2c2d6d2821f` → `b49ade4598e2a5b75e9ea0986841b6def8454ef7`（截至分析时 HEAD）</span>  
> 风险等级：P0，涉及数据模型、额度口径、API 契约、鉴权门槛和生产数据迁移

## 1. 总体结论

本次 Data Download / My Data 改动是一次模型重构，不是普通接口调整：

1. 下载授权从 Upload/Package 维度转为用户对 Episode 的持有关系。
2. 月度额度从“下载次数或 Package quota”改为“本 UTC 月首次加入 My Data 的 Episode 数量”。
3. 已拥有 Episode 可以重复下载，不重复扣减月度额度，但成功交付后会增加下载次数。
4. UI Download、Manifest 和 API Package 共用同一套 My Data Episode 授权与额度逻辑。
5. 下载历史改为 Episode 粒度，Package 不再保存 Upload、Bucket 和文件路径快照。
6. Package 可以复用已被其他 Package 使用的 Episode，不再返回旧的重复冲突 409。
7. Migration 会清空现有下载历史、API Package 和 Package-Episode 映射，生产发布前必须明确历史数据处置方案。
8. <span style="color:#2563eb">后续 Commit `470ab3d` 将 Robotic Data 鉴权从 `operator/admin` 角色门槛改为 **Active Data Membership Plan**；只读 My Data / API Key 列表等入口仅需登录（详见 [第 17 节](#17-后续后端-commit-range-470ab3d--head分析)）。</span>

当前主要阻断项：

- Migration 存在不可逆的数据清理风险。
- `REVOKED/REFUNDED` Episode 的重新授权语义不完整。
- API Download Session 的幂等指纹未包含 `package_id`。
- <span style="color:#2563eb">本次分析范围内的前端没有同步适配全部新 API 契约；`app-prismax-rp` 仍可能按旧角色门槛误拦已有会员的普通用户。</span>
- Hex 的额度判断和 Pipeline 402 Payload 存在不一致。

## 2. 核心概念变化

### 2.1 旧模型

旧模型主要围绕 Download 或 API Package 管理授权和额度：

```text
用户选择 Upload
→ 创建下载或 Package
→ Package 保存当时的 Upload、Episode、Bucket 和文件路径快照
→ 下载次数或 Package quota 决定是否允许继续下载
```

主要问题是：同一个 Episode 在不同下载方式或不同 Package 中重复出现时，所有权、额度和历史口径容易重复计算。

### 2.2 新模型

新模型首先建立用户与 Episode 的持有关系：

```text
用户选择 Episode
→ 检查用户是否已拥有该 Episode
→ 只对尚未拥有的 Episode 检查月度额度
→ 写入 My Data
→ UI / Manifest / API Package 使用同一份 Episode 所有权
→ 实际成功交付后写下载历史并增加下载次数
```

核心区别：

| 维度 | 旧模型 | 新模型 |
| --- | --- | --- |
| 所有权单位 | Download / Package / Upload | User + Episode |
| 月度额度 | 下载次数或 Package quota | 本月首次获得的 Episode 数 |
| 重复下载 | 可能重复占用额度 | 已拥有 Episode 不重复扣额 |
| Package 重复 Episode | 可能返回冲突 | 允许跨 Package 复用 |
| 下载历史 | Download/Upload 口径 | Episode 口径 |
| 文件路径 | Package 中保存快照 | Session 创建时从当前 Episode 读取 |

## 3. Episode 所有权模型

新增表：

```text
data_user_library_episodes
```

核心字段：

| 字段 | 含义 |
| --- | --- |
| `user_id` | Episode 所属用户 |
| `episode_id` | 被持有的 Episode |
| `status` | 当前所有权状态 |
| `download_count` | 成功下载次数 |
| `last_downloaded_at` | 最近一次成功下载时间 |
| `created_at` | 首次加入 My Data 的时间，也是月度额度统计依据 |
| `updated_at` | 最近更新时间 |

主键：

```text
(user_id, episode_id)
```

同一用户对同一个 Episode 最多存在一条所有权记录。

支持的状态：

| Status | 当前语义 |
| --- | --- |
| `ACTIVE` | 当前可用，可以下载并增加下载次数 |
| `ARCHIVED` | 再次加入时恢复为 `ACTIVE` |
| `REVOKED` | 会被识别为已有记录，但当前逻辑不会恢复为 `ACTIVE` |
| `REFUNDED` | 会被识别为已有记录，但当前逻辑不会恢复为 `ACTIVE` |

`REVOKED/REFUNDED` 是高风险状态：如果它们被视为“已拥有”，请求可能不再扣额度；但因为记录不是 ACTIVE，后续下载计数也不会更新。上线前必须明确它们应该：

- 永久拒绝下载；或
- 重新授权并恢复 ACTIVE；或
- 重新计入额度后建立新的有效授权。

## 4. 月度额度模型

额度定义为：

```text
当前 UTC 月创建的 My Data Episode 记录数
```

不是以下指标：

- 不是下载请求次数。
- 不是成功下载次数。
- 不是 Package 数量。
- 不是 Upload 数量。
- 不是重复下载次数。

例如，用户月度额度为 100：

```text
本月已经首次获得 80 个 Episode
本次请求包含 15 个已拥有 Episode + 10 个新 Episode

used = 80
existing = 15
new = 10
projected = 90
remaining after request = 10
```

本次请求只消耗 10 个额度。

如果再次下载这 25 个 Episode：

```text
new = 0
used 仍为 90
download_count 在成功交付后继续增加
```

### 4.1 授权核心流程

核心函数 `_ensure_user_library_episodes()`：

1. 标准化并去重 Episode ID。
2. 获取用户级 PostgreSQL Advisory Transaction Lock。
3. 读取用户当前 Membership Plan。
4. 查询用户已经拥有的 Episode。
5. 只对缺失 Episode 计算新增额度。
6. 验证 `used + new <= monthly_limit`。
7. 在额度允许时插入 My Data 记录。
8. 将已有 `ARCHIVED` 记录恢复为 `ACTIVE`。

用户级事务锁用于防止并发请求同时读取相同的剩余额度并发生超卖。

### 4.2 成功下载后的计数

成功交付后调用 `_increment_user_library_download_counts()`：

```text
download_count = download_count + 1
last_downloaded_at = 当前时间
```

只有 `ACTIVE` 记录会增加下载次数。因此必须确保：

- 构建失败不能增加次数。
- Package 创建不能增加次数。
- 仅加入 My Data 不能增加次数。
- 幂等重试不能重复增加次数。
- `REVOKED/REFUNDED` 不应通过其他下载入口绕过授权策略。

## 5. API 与流程变化

### 5.1 新增 My Data API

| Method | API | 行为 |
| --- | --- | --- |
| POST | `/data/my-data` | 将 Episode 加入 My Data；不创建下载历史、不增加下载次数 |
| POST | `/data/my-data/check` | 返回已拥有/新增 Episode、当前用量、预计用量及是否超额 |
| GET | `/data/my-data/summary` | 返回 My Data 总数及 Task/Robot 汇总 |
| GET | `/data/my-data/episodes` | 分页、过滤、搜索和排序 My Data Episode |
| GET | `/data/downloads/{download_id}` | 返回单条下载详情和精确的 `selected_episode_ids` |

### 5.2 现有下载入口变化

| 流程 | 新行为 |
| --- | --- |
| UI Download | 自动将 Episode 加入 My Data；响应改为 `selected_episode_ids`；支持 `Idempotency-Key` |
| Manifest Download | 共用 My Data 额度和 Episode ID；支持幂等键 |
| API Package | 创建前加入 My Data；允许 Episode 跨 Package 复用；创建本身不写下载历史 |
| API Download Session | 校验 Package Owner；从当前 Episode 读取文件路径；成功后创建历史并增加计数 |
| 下载历史 | 改为 Episode 粒度并增加分页；列表接口不直接返回 Episode ID 明细 |
| Hex | 只对新 Episode 估算额度；移除 Package Duplicate Conflict 逻辑 |

## 6. Package 模型重构

### 6.1 跨 Package 复用

同一个用户可以在多个 Package 中复用相同 Episode：

```text
Package A = Episode 1, 2, 3
Package B = Episode 2, 3, 4
```

新模型下 Package B 可以成功创建：

- Episode 2、3 已在 My Data 中，不重复扣额。
- Episode 4 是新 Episode，只对 Episode 4 扣额。
- 不再返回旧版 Duplicate Episode 409。

### 6.2 Package 不再保存路径快照

Package 详情不再返回或依赖：

- Upload Snapshot。
- Bucket Snapshot。
- MCAP/Video 路径快照。

创建 API Download Session 时，从 Episode 当前数据读取文件路径。好处是 Package 不会长期持有过期路径；风险是 Episode 路径、可见性或 Ready 状态发生变化后，同一个旧 Package 可能得到与创建时不同的下载结果。

### 6.3 Package Owner 校验

API Download Session 必须验证当前用户是 Package Owner。非 Owner 请求应返回 403 或不泄露资源存在性的 404，并且：

- 不返回 Episode 或文件路径。
- 不创建下载历史。
- 不增加下载次数。
- 不占用月度额度。

### 6.4 幂等风险

API Session 的幂等指纹当前没有包含 `package_id`。如果使用相同 Idempotency Key 和相同 Episode 集合请求不同 Package，可能错误复用先前 Package 的下载记录。

建议指纹至少包含：

```text
user_id
+ download_method
+ package_id（Package 下载时）
+ sorted unique episode_ids
+ 影响交付结果的关键选项
```

## 7. 下载历史重构

下载历史改为 Episode 粒度，并支持分页：

- 列表返回摘要，不直接展开全部 Episode ID。
- `GET /data/downloads/{download_id}` 返回精确 `selected_episode_ids`。
- Package 创建不代表实际下载，因此不生成下载历史。
- UI、Manifest 和 API Session 成功交付后才生成历史。
- 重复下载已拥有 Episode 会创建新的成功下载历史，并增加 `download_count`，但不消耗新额度。

需要验证以下一致性：

```text
历史中的 selected_episode_ids
= 实际交付的 Episode
= 增加 download_count 的 Episode
```

如果 Upload 中混合 Ready、非 Ready 或不可见 Episode，接口可能过滤部分 Episode。响应必须明确实际选择和交付数量，不能让用户以为完整 Upload 已经下载。

## 8. API 破坏性变化

| 变化 | 兼容性影响 |
| --- | --- |
| `selected_upload_ids` → `selected_episode_ids` | 旧前端读取不到选中结果 |
| 下载历史改为分页结构 | 旧前端可能把分页对象当数组处理 |
| Package 详情移除 Upload/Bucket/Path Snapshot | 依赖旧字段的客户端会失败 |
| 移除旧 Quota Snapshot 字段 | 旧额度展示可能为空或报错 |
| 重复 Episode 不再返回 409 | 旧 Duplicate Conflict UI 成为不可达分支 |
| Admin Unlimited Quota 语义调整 | 配置不完整时可能误返回 403 |

本次前端 Commit Range 没有发现对应的 Data Download 契约适配。发布前必须确认实际候选前端来自哪个 Commit，并执行真实的前后端契约测试。

<span style="color:#2563eb">补充（2026-08-05 重拉 testing 后）：`prismax-marketing-rp`（tip ≈ `ccddf83`，含 `4cb1f0a` My Data）已适配 `selected_episode_ids`，并上线完整 My Data UI（`MyDataWorkspace.js`）、Browse「Add to My Data」、下载 `idempotency_key`、按 `mode` 展示历史；Package 创建已去掉 409 冲突分支。剩余差距：历史无 Task 名（DD-R15）、Browse 仍 `?public=1`（DD-R17）、API Package 创建仍无幂等键。详见 [第 16 节](#16-新前端-prismax-marketing-rprobotic-data-页面契约适配分析)。</span>

## 9. Migration 影响

Migration 文件：

```text
app_prismax_data_pipeline/sql/20260730_data_user_library_episodes.sql
```

其中包含：

```sql
TRUNCATE TABLE
    data_downloads,
    data_api_package_episodes,
    data_api_packages
RESTART IDENTITY;
```

直接影响：

- 清空下载历史。
- 清空 API Package。
- 清空 Package 与 Episode 的映射。
- 重置相关 Identity。
- 不会把历史已下载 Episode 自动 Backfill 到 My Data。

这意味着旧用户过去下载过的数据，在新模型中可能被视为“从未拥有”，再次加入时重新消耗月度额度。

生产执行前必须完成：

1. 备份三张被清空的表以及相关依赖数据。
2. 明确是否允许删除历史下载与 Package。
3. 决定是否从历史下载记录 Backfill My Data Episode 所有权。
4. 在脱敏生产规模数据上验证执行时间和锁影响。
5. 验证失败后的数据库回滚方案。
6. 验证重复执行 Migration 的行为。
7. 执行迁移前后数量和用户额度对账。

## 10. Hex 一致性问题

1. Agent 仍保留 `duplicate_episode_conflict` 和 “Create new package with all selected” 旧分支，但新工具不会再产生该标志。
2. 本地额度快照只有在 `new_episodes > 0` 且预计用量超限时才设置 `quota_exceeded=true`；Pipeline 402 转换只判断 `projected > limit`。
3. 套餐降级后，如果 `used > limit` 但本次请求没有新 Episode，本地估算与 Pipeline 可能给出不同结论。
4. Pipeline 402 的 `remaining_episodes` Fallback 使用 `limit - used`，本地快照使用 `limit - projected`。
5. `prepare_download_estimate` 的描述仍将月度额度称为 API Package 限制，但实际额度同时约束 Browser、Manifest 和 API。
6. “完整下载 Upload”只检查单次请求是否包含全部可下载 Episode；多次部分下载累计覆盖完整 Upload 时仍不会标记为完整下载。

建议 Pipeline 成为额度计算的唯一事实来源，Hex 只展示标准化响应，避免在客户端重复实现额度公式。

## 11. 风险清单

| ID | 等级 | 风险 | 影响 | 上线要求 |
| --- | --- | --- | --- | --- |
| DD-R01 | P0 | Migration 清空历史和 Package | 历史数据永久丢失 | 备份、批准、Backfill、回滚演练 |
| DD-R02 | P0 | `REVOKED/REFUNDED` 授权语义不完整 | 可能绕过额度或无法正常下载 | 明确并实现状态转换规则 |
| DD-R03 | P0 | 幂等指纹缺少 `package_id` | 不同 Package 错误复用下载结果 | 将 Package 纳入指纹并增加冲突测试 |
| DD-R04 | P0 | 并发额度超卖 | 超出 Membership 月度额度 | 用户级锁、事务和数据库约束测试 |
| DD-R05 | P1 | FAILED 请求占用 Idempotency Key | 相同 Key 无法安全重试 | 定义 FAILED 重试或新 Key 恢复策略 |
| DD-R06 | P1 | PENDING 长期残留 | 状态卡死、用户重复请求 | 超时恢复、清理 Job 和告警 |
| DD-R07 | P1 | 无幂等键的网络重试 | 重复历史和重复 Download Count | 客户端强制 Key 或服务端生成稳定 Key |
| DD-R08 | P1 | 混合状态 Upload 静默过滤 Episode | 用户拿到不完整数据 | 响应明确 requested/eligible/delivered 数量 |
| DD-R09 | P1 | 前端未适配新契约 | 页面报错或显示错误 | 候选版本契约回归 |
| DD-R10 | P1 | Hex 与 Pipeline 额度口径不同 | 用户看到错误的剩余额度 | 统一公式和 402 Payload |
| DD-R11 | P1 | Package 使用当前路径 | 旧 Package 的交付内容可能变化 | 明确动态解析语义并记录审计信息 |
| DD-R12 | P1 | Admin/Unlimited 配置不完整 | Admin 意外被 403 拒绝 | 权限与 Plan 组合测试 |
| DD-R13 | P2 | Hex 保留旧冲突 UI | 显示不可达或误导操作 | 删除旧分支并更新工具描述 |
| <span style="color:#2563eb">DD-R14</span> | <span style="color:#2563eb">P2</span> | <span style="color:#2563eb">（已部分关闭）`prismax-marketing-rp` testing 已上线 My Data UI（`MyDataWorkspace.js`），且 Browse 侧 `postCreateApiPackage` 已去掉 409/`allow_already_packaged` 分支</span> | <span style="color:#2563eb">原“Coming soon / 死代码冲突分支”风险不再成立；仍需 E2E 验收 My Data 读写与 Membership 只读降级</span> | <span style="color:#2563eb">执行 FE2-01/FE2-08~FE2-10；确认 Beta 部署版本含 `4cb1f0a` 及后续 My Data 提交</span> |
| <span style="color:#2563eb">DD-R15</span> | <span style="color:#2563eb">P2</span> | <span style="color:#2563eb">`prismax-marketing-rp` 下载历史改为按 `mode` 展示（Browser/Manifest/API），不再依赖 `selected_upload_ids`；但标题仍非真实 Task 名</span> | <span style="color:#2563eb">用户只能区分下载方式，无法从历史列表直接识别具体 Task</span> | <span style="color:#2563eb">产品确认是否接受；或后端补充 task 名字段 / 前端按 `selected_episode_ids` 反查</span> |
| <span style="color:#2563eb">DD-R16</span> | <span style="color:#2563eb">P1</span> | <span style="color:#2563eb">后端已取消 `operator/admin` 角色门槛（`470ab3d`），但 `app-prismax-rp` 前端仍可能按旧 `hasRoboticDataAccess(userRole)` 提前拦截</span> | <span style="color:#2563eb">已有 Active Membership、但 `user_role` 非 operator/admin 的用户会被旧前端误拦，无法使用下载能力</span> | <span style="color:#2563eb">旧前端改为按 Membership / 登录态判断；或与产品确认是否仍保留前端角色白名单</span> |
| <span style="color:#2563eb">DD-R17</span> | <span style="color:#2563eb">P2</span> | <span style="color:#2563eb">`prismax-marketing-rp` 目录浏览/预览走 `?public=1` 匿名端点</span> | <span style="color:#2563eb">需确认匿名可见的数据范围是否符合预期，避免暴露不应公开的 Episode/Task 信息</span> | <span style="color:#2563eb">与产品确认“公开可浏览目录”范围，并补充匿名访问的数据隔离测试</span> |
| <span style="color:#2563eb">DD-R18</span> | <span style="color:#2563eb">P1</span> | <span style="color:#2563eb">鉴权分层后，只读入口（`GET /data/my-data/summary`、`episodes`、`GET/DELETE /data/api-keys`）不要求 Active Membership，写/下载入口要求</span> | <span style="color:#2563eb">无 Plan / 过期 Plan 用户仍可读 My Data 元数据或吊销 Key；若产品期望“无会员一律 403”，则当前实现漏检</span> | <span style="color:#2563eb">与产品确认分层策略；若需全量拒绝，把只读入口也改成 `_require_active_data_membership`</span> |
| <span style="color:#2563eb">DD-R19</span> | <span style="color:#2563eb">P1</span> | <span style="color:#2563eb">Membership 过期后已有 `X-API-Key` 会被 `_require_data_api_key` 直接 403（不更新 `last_used_at`）</span> | <span style="color:#2563eb">客户端可能只看到通用 403，不清楚是 Key 无效还是会员过期；已创建 Session 的行为需回归</span> | <span style="color:#2563eb">明确错误文案；覆盖“Key 仍 ACTIVE 但 Plan 过期”场景</span> |

## 12. E2E / API 测试用例

### 12.0 使用说明

- **优先级**：P0 = 发布阻断项，必须全部执行并通过，任一 Fail 都应阻断上线；P1 = 重要缺陷，发布前需要有明确结论（修复或产品书面接受风险）；P2 = 建议覆盖，可视排期取舍。
- **测试结果**：执行后请将「☐ 待执行」替换为 `Pass` / `Fail` / `Blocked` / `N/A`。`Fail` 需要附带 Bug 链接；`Blocked` 需要注明阻塞原因（如环境不具备、依赖用例未过）；涉及"需先与产品确认口径"的用例，在口径明确前一律视为 `Blocked`，不得直接判 `Pass`。
- 以下用例中出现的字段名已对照 `app_prismax_data_pipeline/app.py` 实际代码核实，与真实接口响应一致（而非早期草稿中的简写）：
  - `POST /data/my-data`、`POST /data/my-data/check` 请求体字段：`episode_ids`（数组，最多 200 个正整数；`data_api_helper.py` 的 `normalize_episode_ids` 校验）。
  - `POST /data/my-data/check` 响应字段：`data.owned_episode_ids`、`data.new_episode_ids`、`data.owned_episode_count`、`data.new_episode_count`、`data.would_exceed_quota`（布尔值，**不是** `quota_exceeded`），以及 `data.quota` 子对象：`used_episodes`、`new_episodes`、`projected_episodes`、`remaining_episodes`、`monthly_episode_limit`、`monthly_price_usd`、`membership`、`billing_month`、`unlimited_episode_download`（**不是** 简写的 `used`/`new`/`projected`）。
  - `POST /data/my-data` 成功响应（200）：`data.requested_episode_count`、`added_episode_count`、`already_owned_episode_count`、`added_episode_ids`、`already_owned_episode_ids`、`data.quota`（结构同上）。
  - 402（额度超限，`DataApiQuotaError`）响应体：`{"success": false, "msg": "...", "data": {used_episodes, new_episodes, projected_episodes, remaining_episodes, monthly_episode_limit, ...}}`——`data` 字段本身就是 quota 结构，字段名同上。
  - `POST /data/api-packages`（创建 Package）请求体字段是 `selected_episode_ids`（**不是** `episode_ids`），可选 `name`；鉴权与 My Data 接口相同，都是普通用户登录 Token。
  - <span style="color:#2563eb">`POST /v1/data/download-sessions`（创建 API Download Session，即 DL-06/07/10 中的"创建 Download Session"）鉴权方式是请求头 `X-API-Key`（对应 `data_api_keys` 表中的 Key），**不是**用户登录 Token；请求体字段是 `package_id`；"Package Owner" 在代码里等价于"该 `package_id` 所属的 `user_id` 与这把 API Key 绑定的 `user_id` 一致"。自 `470ab3d` 起，`_require_data_api_key` 还会调用 `_get_active_data_membership_plan`：Key 本身 ACTIVE 但用户 Membership / Plan 无效时返回 403，且不会更新 `last_used_at`。</span>
  - 幂等键：请求头 `Idempotency-Key`（大小写按此），唯一性约束是 `(user_id, mode, idempotency_key)`，`package_id` 确实不在约束内（对应 DD-R03/DL-10）。
  - <span style="color:#2563eb">**鉴权分层（`470ab3d`）**：已取消 `ROBOTIC_DATA_ALLOWED_USER_ROLES = ("operator","admin")`。写/下载类入口走 `_require_active_data_membership()`（登录 + Active Plan）；只读 My Data / API Key 列表与吊销、非 admin 预览走 `_require_authenticated_user()`（仅登录）。详见第 17 节对照表。</span>
  - 涉及数据库校验的步骤，均指查询对应表（`data_user_library_episodes`、`data_downloads`、`data_api_packages`、`data_api_package_episodes`、`data_api_keys`）而非仅凭接口响应推断。
- 上述字段名和接口路径已对照代码核实，但业务规则（如额度公式、状态流转）仍可能随后续开发调整；执行前建议再次确认代码或 API 文档未发生变化。
- <span style="color:#2563eb">`分类=新前端 prismax-marketing-rp` 的用例（FE2-01~FE2-10）针对独立前端仓库 `prismax-marketing-rp` testing（Next.js `/robotic-data`，含 Browse + My Data），详见 [第 16 节](#16-新前端-prismax-marketing-rprobotic-data-页面契约适配分析)；与 `app-prismax-rp` 并存时，SYS-10 须明确本次发布验收哪一套（或两套）。</span>
- <span style="color:#2563eb">`分类=鉴权与 Membership` 的用例（AUTH-01~AUTH-05）以及更新后的 SYS-03，覆盖 `470ab3d`/`ca1e000` 引入的鉴权分层与 My Data 过滤参数类型修复。</span>

### 12.1 全量用例（Episode 所有权与额度 / 下载与 Package 与幂等 / Migration 与权限与 Hex / 新前端 / 鉴权与 Membership）

| ID | 分类 | 优先级 | 场景描述 | 前置条件 | 操作步骤 | 预期结果 | 测试结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| MYD-01 | Episode 所有权与额度 | P0 | 验证用户首次将从未拥有过的 Episode 加入 My Data 时，所有权、额度、下载历史三者的初始状态是否符合新模型定义——加入不等于下载。 | 用户 U1 当月额度充足（`quota.monthly_episode_limit=100`，`quota.used_episodes=0`）；Episode E1 状态 `DERIVED_READY`，(U1,E1) 从未存在于 `data_user_library_episodes`。 | 1. 查库确认 (U1,E1) 不存在。<br>2. 记录调用前 `quota.used_episodes=0`。<br>3. 调用 `POST /data/my-data`，`episode_ids:[E1]`。<br>4. 检查响应体（`added_episode_ids`/`already_owned_episode_ids`/`quota`）。<br>5. 查询 `data_user_library_episodes` 中 (U1,E1)。<br>6. 查询 `data_downloads` 确认无新记录。 | 响应 200，`added_episode_ids=[E1]`、`already_owned_episode_ids=[]`；(U1,E1) 新增记录：`status=ACTIVE`、`download_count=0`、`last_downloaded_at=null`；`quota.used_episodes` 从 0 变为 1；`data_downloads` 无新增记录（加入 ≠ 下载）。 | ☐ 待执行 |
| MYD-02 | Episode 所有权与额度 | P0 | 验证已是 ACTIVE 的 Episode 被重复"加入"时保持幂等，防止用户反复调用刷额度或产生脏数据。 | 紧接 MYD-01，U1 已拥有 E1（ACTIVE），`quota.used_episodes=1`。 | 1. 记录当前 `quota.used_episodes=1`。<br>2. 连续 3 次调用 `POST /data/my-data`，`episode_ids:[E1]`（模拟重复点击/前端自动重试）。<br>3. 每次调用后查询 (U1,E1) 及 `quota.used_episodes`。 | 每次响应 200，`already_owned_episode_ids=[E1]`、`added_episode_ids=[]`；`data_user_library_episodes` 中仍只有 1 条记录，`created_at` 不变；`quota.used_episodes` 全程保持 1；`download_count` 保持 0；`data_downloads` 无新增。 | ☐ 待执行 |
| MYD-03 | Episode 所有权与额度 | P0 | 验证一次请求同时包含已拥有和全新 Episode 时，只对真正新增部分计算额度。 | U1 已拥有 E1（ACTIVE），`quota.used_episodes=1`；E2 为全新 Episode。 | 1. 调用 `POST /data/my-data/check`，`episode_ids:[E1,E2]`，记录 `owned_episode_ids`/`new_episode_ids`/`quota.used_episodes`/`quota.projected_episodes`。<br>2. 调用 `POST /data/my-data`，同样参数。<br>3. 查询两条记录及 `quota.used_episodes`。 | check 返回 `owned_episode_ids=[E1]`、`owned_episode_count=1`、`new_episode_ids=[E2]`、`new_episode_count=1`、`quota.used_episodes=1`、`quota.projected_episodes=2`；正式加入后 E1 记录不变，E2 新增 `status=ACTIVE`；`quota.used_episodes` 从 1 变为 2（只 +1，不是 +2）。 | ☐ 待执行 |
| MYD-04 | Episode 所有权与额度 | P1 | 验证同一次 payload 中重复传入同一 Episode ID 多次时，服务端去重而不是当作多次新增分别扣额。 | E3 为全新 Episode，U1 `used` 为已知基线值。 | 1. 调用 `POST /data/my-data`，`episode_ids:[E3,E3,E3]`。<br>2. 检查响应与数据库。 | 只新增 1 条 (U1,E3) 记录；`used` 只 +1（不是 +3）；不应报重复冲突错误。 | ☐ 待执行 |
| MYD-05 | Episode 所有权与额度 | P0 | 边界验证：新增数量恰好等于剩余额度时应成功放行，用尽但不超额。 | `quota.monthly_episode_limit=100`，`quota.used_episodes=98`，`quota.remaining_episodes=2`；E4、E5 为全新 Episode。 | 1. 调用 check，`episode_ids:[E4,E5]`，确认 `new_episode_count=2`、`quota.projected_episodes=100`、`would_exceed_quota=false`。<br>2. 调用 `POST /data/my-data` 同样参数。<br>3. 查询用量与记录；对再一个全新 Episode 发起加入验证是否 402。 | 请求成功（200），E4、E5 均加入且 `status=ACTIVE`；`quota.used_episodes=100`，不触发 402；后续再对新 Episode 请求应返回 402。 | ☐ 待执行 |
| MYD-06 | Episode 所有权与额度 | P0 | 验证请求新增数超过 Remaining 时被整体拒绝，不允许"部分插入"的脏数据。 | `quota.remaining_episodes=2`；E6、E7、E8 为全新 Episode（共 3 个）。 | 1. 调用 check，`episode_ids:[E6,E7,E8]`，确认 `new_episode_count=3 > quota.remaining_episodes=2`，`would_exceed_quota=true`。<br>2. 调用 `POST /data/my-data` 同样参数。<br>3. 检查响应状态码与 body。<br>4. 查询 (U1,E6)/(U1,E7)/(U1,E8) 是否存在。<br>5. 查询 `quota.used_episodes` 是否变化。 | 响应 402，body 为 `{"success":false,"msg":"...","data":{used_episodes,new_episodes,projected_episodes,remaining_episodes,monthly_episode_limit,...}}`；数据库中三条记录均不存在（无任何部分插入）；`used_episodes` 保持不变。 | ☐ 待执行 |
| MYD-07 | Episode 所有权与额度 | P1 | 验证额度严格按 UTC 自然月统计，跨月后旧记录不计入新月 `used`，但已拥有 Episode 依旧免费复用。 | 可控制/模拟系统时间进入新 UTC 月，或构造 `created_at` 落在上月的历史数据；U1 上月已用满 100 额度，其中含 E1。 | 1. 模拟进入新 UTC 自然月。<br>2. 调用 summary/check，确认新月 `used` 从 0 开始（不含上月记录）。<br>3. 对已拥有的 E1 发起下载（非新增），确认不消耗新月额度。<br>4. 对全新 Episode E9 发起加入，确认可成功。 | 新月 `used` 只统计本月 `created_at` 落在新月区间内的记录；对 E1 的下载/重复加入不产生新记录、不消耗新月额度；E9 成功加入，作为新月第 1 个额度。 | ☐ 待执行 |
| MYD-08 | Episode 所有权与额度 | P1 | 验证 ARCHIVED 状态的 Episode 再次加入或下载时能正确恢复为 ACTIVE，且不会在主键上产生重复行。 | 构造 (U1,E10) 记录，`status=ARCHIVED`。 | 1. 确认当前 `status=ARCHIVED`。<br>2. 调用 `POST /data/my-data`，`episode_ids:[E10]`。<br>3. 查询记录状态与主键数量。<br>4. 额外场景：改用下载入口（如 UI Download）触发恢复，重复验证。 | (U1,E10) 唯一记录被更新为 `status=ACTIVE`，`updated_at` 刷新，不产生第二条同主键记录；`created_at` 是否保留原值需与产品口径确认并记录；恢复是否消耗新增额度需明确产品口径（理论上"已存在记录"不应重复计额，需据此判定 Pass/Fail）。 | ☐ 待执行 |
| MYD-09 | Episode 所有权与额度 | P0 | 【高风险】验证 REVOKED/REFUNDED 状态 Episode 在被任一入口（My Data / UI / Manifest / API Package）再次请求时的行为，需先与产品确认预期策略（永久拒绝 / 重新授权恢复 ACTIVE / 重新计额后建立新授权），再据此判定结果。 | 构造 (U1,E11) `status=REVOKED`；(U1,E12) `status=REFUNDED`。 | 1. 分别通过 `POST /data/my-data`、UI Download、Manifest Download、创建含该 Episode 的 API Package 四个入口请求 E11、E12。<br>2. 每次请求后查询 status、`download_count`、`updated_at`。<br>3. 查询 `used` 是否被扣减。<br>4. 交叉核对四个入口行为是否彼此一致。 | 需先获得产品口径确认：若为"永久拒绝"，四入口都应明确报错，不产生下载/不扣额/不改 status；若为"重新授权"，四入口应一致地恢复 ACTIVE 且额度处理口径统一。**无论哪种策略，四个入口的行为必须完全一致**；若某入口（如 API Package）绕过限制而其他入口拒绝，判定为 P0 Bug。 | ☐ 待执行 |
| MYD-10 | Episode 所有权与额度 | P0 | 验证用户级 PostgreSQL Advisory Transaction Lock 是否真正生效：同一用户对同一全新 Episode 并发加入不产生重复记录或死锁。 | U1 用量充足；E13 为全新 Episode。 | 1. 使用并发脚本/压测工具，尽量同时（如用 barrier 同步启动）发起 10 个并发 `POST /data/my-data` 请求，`episode_ids:[E13]`。<br>2. 记录每个请求状态码和耗时。<br>3. 全部完成后查询 (U1,E13) 记录数与 `used` 变化。<br>4. 检查服务/数据库日志是否有死锁、超时。 | 最终仅 1 条 (U1,E13) 记录；`used` 只 +1；10 个请求全部正常返回（成功或"已拥有"语义），无 500/死锁/超时；无重复主键异常泄漏到响应中。 | ☐ 待执行 |
| MYD-11 | Episode 所有权与额度 | P0 | 验证剩余额度不足以满足所有并发请求时不会超卖：`quota.remaining_episodes=2` 且并发请求 3 个不同全新 Episode，最终成功数不超过 2。 | `quota.remaining_episodes=2`；E14、E15、E16 为 3 个互不相同的全新 Episode。 | 1. 同时发起 3 个并发请求，各自只含一个 Episode（E14/E15/E16），模拟真实并发场景。<br>2. 记录每个响应状态码（200/402）。<br>3. 查询最终成功插入的记录数。<br>4. 查询最终 `quota.used_episodes`。 | 最多 2 个请求成功，至少 1 个返回 402；最终成功记录数 ≤ 2，不出现 3 条全部成功导致超卖；最终 `used_episodes` 不超过 `monthly_episode_limit`；允许"哪 2 个成功"存在竞态不确定性，但总数不能超限。 | ☐ 待执行 |
| MYD-12 | Episode 所有权与额度 | P1 | 验证 `summary`、`episodes`（分页列表）、`check` 三个接口在同一批数据下结果互相吻合，避免用户在不同页面看到不一致的数字。 | 为 U1 构造跨 3 个 Task、2 个 Robot、混合 ACTIVE/ARCHIVED/REVOKED/REFUNDED 状态的 37 条 My Data 记录。 | 1. 调用 `GET /data/my-data/summary`，记录总数及 Task/Robot 汇总。<br>2. 调用 `GET /data/my-data/episodes`，`page_size=10` 翻 4 页，汇总实际返回条数与分组统计。<br>3. 用不同过滤（Task/Robot/关键字搜索/按创建时间排序）重复步骤 2。<br>4. 调用 `check` 传入部分 Episode ID，核对 `existing/new` 与 episodes 列表实际状态是否一致。 | summary 总数与 episodes 翻页汇总总数一致（需确认是否包含 REVOKED/REFUNDED，口径统一）；过滤/搜索/排序结果与预期子集完全匹配，无遗漏无重复；check 判定与 episodes 列表实际记录完全对应。 | ☐ 待执行 |
| MYD-13 | Episode 所有权与额度 | P1 | 验证请求体中包含不存在的、格式非法的、或当前用户不可见的 Episode ID 时的健壮性，防止 500、报错信息泄露或产生脏数据。 | 准备：不存在的 Episode ID（随机字符串/超大整数）、格式非法 ID（空字符串/SQL 注入字符串）、存在但当前用户不可见的 Episode。 | 1. 分别用上述 3 类 ID 调用 `check` 和 `POST /data/my-data`。<br>2. 混合合法 ID 和非法 ID 于同一请求中调用。<br>3. 检查响应状态码与错误信息内容。<br>4. 检查数据库确认无异常写入。 | 非法/不存在 ID 均返回明确 4xx（不应 500）；错误信息不暴露 SQL 语句或内部堆栈；混合请求中非法 ID 应导致整体拒绝（除非产品明确定义"部分成功"语义，需据此确认预期）；不产生任何脏数据。 | ☐ 待执行 |
| MYD-14 | Episode 所有权与额度 | P0 | 安全测试：验证用户 A 无法通过任何参数构造读取或影响用户 B 的所有权、额度和历史数据。 | 用户 U1、U2 各自拥有互不相同的 My Data 数据集。 | 1. 用 U1 Token 调用 `summary`/`episodes`/`check`，确认只返回 U1 数据。<br>2. 尝试在请求中构造/篡改 `user_id` 参数（若接口暴露）或猜测 U2 的 Episode 组合，确认无法读取/修改 U2 数据。<br>3. 用 U1 Token 加入一个 Episode，确认 U2 额度和记录不受影响。 | U1 只能看到/操作自己的数据，无法通过参数篡改访问 U2 数据；若接口信任前端传入的 `user_id` 而非从 Token 解析，判定为 P0 安全 Bug。 | ☐ 待执行 |
| MYD-15 | Episode 所有权与额度 | P1 | 验证超大批量 Episode ID 请求的性能与正确性，并区分两类边界：① 单次超过接口硬性数量上限（`normalize_episode_ids` 限制 `episode_ids` 最多 200 个）应报 400；② 数量合法但超过月度额度应报 402，两者不应混淆或被静默截断。 | 场景 A：准备 250 个全新 Episode ID（超过接口 200 个上限）；场景 B：准备 150 个全新 Episode ID（未超接口上限，但 `quota.monthly_episode_limit=100` 不足以承接）。 | 1. 场景 A：调用 `POST /data/my-data`，`episode_ids` 为 250 个 ID，记录状态码与 `msg`。<br>2. 场景 B：调用 check 与 `POST /data/my-data`，`episode_ids` 为 150 个全新 ID，记录状态码、耗时与 `quota` 字段。<br>3. 两个场景均查询数据库确认插入行为（应整体拒绝，而非静默截断只插入部分）。 | 场景 A：返回 400，`msg` 提示 "episode_ids is limited to 200"，不触碰数据库、不消耗额度；场景 B：接口在合理时间内响应（无超时），因超额返回 402，`data.new_episodes=150 > remaining_episodes`；两个场景数据库均无任何新增记录（不允许"自动截断只插入前 N 个"）；服务日志无异常报错或数据库锁超时。 | ☐ 待执行 |
| MYD-16 | Episode 所有权与额度 | P0 | 组合场景：验证一次请求同时包含 ACTIVE、REVOKED、REFUNDED、全新四种状态 Episode 时各自处理结果互不干扰，是对 MYD-09 结论的补充验证。 | U1 拥有 (E1:ACTIVE)、(E11:REVOKED)、(E12:REFUNDED)；另有全新 E17。 | 1. 调用 check，`episode_ids:[E1,E11,E12,E17]`，检查响应分类是否清晰区分四种状态。<br>2. 调用 `POST /data/my-data` 同样参数。<br>3. 分别查询四个 Episode 最终状态与用量变化。 | E1 不受影响不扣额；E17 正常加入扣 1 点额度；E11/E12 按 MYD-09 确认的产品策略执行；**若响应把 REVOKED/REFUNDED 误判为"已拥有"从而放行且不扣额也不下载，需作为 Bug 记录**（对应第 3 节高风险语义漏洞）。 | ☐ 待执行 |
| DL-01 | 下载与 Package 与幂等 | P0 | 验证 UI Download 首次下载全新 Episode 时，自动完成 My Data 加入、下载历史创建、`download_count` 增加的完整链路，且响应字段已切换为新契约 `selected_episode_ids`。 | U1 未拥有 E20；E20 `DERIVED_READY` 且文件齐全；用量充足。 | 1. 通过 UI 发起下载请求，选择 E20。<br>2. 检查响应字段，确认含 `selected_episode_ids:[E20]`，不应再出现 `selected_upload_ids`。<br>3. 查询 (U1,E20) 的 status/download_count/last_downloaded_at。<br>4. 查询 `data_downloads` 是否新增 1 条 Episode 粒度历史。<br>5. 查询 `used` 变化。 | 响应包含正确 `selected_episode_ids`；(U1,E20) 新增记录，`status=ACTIVE`、`download_count=1`、`last_downloaded_at=本次时间`；新增 1 条成功下载历史；`used` +1。 | ☐ 待执行 |
| DL-02 | 下载与 Package 与幂等 | P0 | 验证已拥有 Episode 被再次下载时不重复扣额，但会生成新下载历史并累加 `download_count`。 | 紧接 DL-01，U1 已拥有 E20，`download_count=1`。 | 1. 再次发起对 E20 的 UI Download，重复 3 次。<br>2. 每次检查响应、记录、`data_downloads` 新增情况、`used`。 | `download_count` 依次变为 2、3、4；`last_downloaded_at` 每次刷新；每次新增 1 条历史（共 3 条）；`used` 全程不变。 | ☐ 待执行 |
| DL-03 | 下载与 Package 与幂等 | P0 | 验证 Manifest 下载路径与 UI 共用同一套 My Data 逻辑，多 Episode 批量下载时文件、历史、计数三者必须完全对齐。 | U1 部分拥有部分未拥有一组 Episode：E21 已拥有，E22/E23 全新，同属一个 Task 下不同 Robot。 | 1. 通过 Manifest 请求 `[E21,E22,E23]`。<br>2. 检查 Manifest 内容/文件路径列表是否完整对应 3 个 Episode。<br>3. 查询三条记录的 status/download_count。<br>4. 查询 `data_downloads` 是否生成对应历史。<br>5. 查询 `used` 变化。 | Manifest 内容与 3 个 Episode 完全对应，无缺漏或多余；三者 `download_count` 均 +1；`used` 只 +2（E21 已拥有不计）；历史中 `selected_episode_ids` 精确等于 `[E21,E22,E23]`。 | ☐ 待执行 |
| DL-04 | 下载与 Package 与幂等 | P0 | 验证创建 API Package 本身只声明打包内容，不等于实际交付数据，不应生成下载历史或增加 `download_count`。 | U1 未拥有 E24、E25，用量充足。 | 1. 用 U1 登录 Token 调用 `POST /data/api-packages`，请求体 `{"selected_episode_ids":[E24,E25]}`。<br>2. 检查响应，确认返回 `package_id`。<br>3. 查询 (U1,E24/E25)：是否加入 My Data、`download_count` 是否仍为 0。<br>4. 查询 `data_downloads` 确认无新增历史。<br>5. 查询 `quota.used_episodes` 变化。 | 响应 201，返回 `package_id`/`status=ACTIVE`/`episode_count=2`/`quota`；E24、E25 加入 My Data 但 `download_count=0`；无对应下载历史记录；`quota.used_episodes` 正确扣减 2。 | ☐ 待执行 |
| DL-05 | 下载与 Package 与幂等 | P1 | 验证同一用户可在多个 Package 中复用相同 Episode，不再返回旧版 Duplicate 409，也不会因复用而重复扣额。 | U1 已创建 Package A=[E24,E25]（DL-04）；另有全新 Episode E26。 | 1. 创建 Package B=[E24,E25,E26]（E24/E25 与 A 重叠，E26 全新）。<br>2. 检查响应状态码，确认非旧版 409。<br>3. 查询 Package B 是否正确关联三个 Episode。<br>4. 查询 `used` 变化（应只 +1）。<br>5. 确认 Package A 未受影响。 | Package B 创建成功（200/201），不返回 409；`data_api_package_episodes` 中 Package B 关联 3 条记录；`used` 只 +1（对应 E26）；Package A 状态和关联不受影响。 | ☐ 待执行 |
| DL-06 | 下载与 Package 与幂等 | P0 | 验证 Package Owner 创建 Download Session 时能从 Episode 当前数据（而非历史快照）读取文件路径，交付成功后正确写历史和计数。**注意：该接口鉴权是 `X-API-Key`，不是登录 Token**，"Owner"指该 Key 绑定的 `user_id` 与 Package 所属 `user_id` 一致。 | U1 名下已生成一个 ACTIVE 状态的 Data API Key（`data_api_keys.user_id=U1`）；U1 是 Package B 的 Owner（DL-05）；E24/E25/E26 当前文件状态正常。 | 1. 携带 U1 的 `X-API-Key` 请求头，调用 `POST /v1/data/download-sessions`，请求体 `{"package_id":"B"}`。<br>2. 检查返回的签名 Cookie/下载路径是否为 Episode 当前实际文件路径。<br>3. 完成下载（实际下载或 mock 交付回调）。<br>4. 查询三个 Episode 的 `download_count`/`last_downloaded_at`。<br>5. 查询 `data_downloads` 是否新增历史且 `package_id=B`、`api_key_id` 为该 Key。 | Session 创建成功（200），路径正确指向当前文件；交付成功后三者 `download_count` 各 +1；新增 1 条历史，关联 Episode 精确匹配 `[E24,E25,E26]`；`quota.used_episodes` 不再变化（均已在 My Data 中）。 | ☐ 待执行 |
| DL-07 | 下载与 Package 与幂等 | P0 | 安全测试：验证非 Package Owner 无法通过构造/猜测 `package_id` 创建 Download Session 获取他人数据。**代码现状**：`package_id` 不存在时报错 `"package not found"`，存在但不属于该 Key 时报错 `"package does not belong to this API key"`——两种 `msg` 文案不同，需评估是否构成"存在性泄露"。 | Package B 属于 U1；准备与 U1 无关联用户 U2 名下的合法 `X-API-Key`。 | 1. 携带 U2 的 `X-API-Key`，对 Package B 的 `package_id` 调用 `POST /v1/data/download-sessions`。<br>2. 检查响应状态码与 `msg` 文本，确认无 Episode/路径信息泄露。<br>3. 查询数据库确认无历史/无计数变化/无额度扣减发生在 U2 身上。<br>4. 用不存在的 `package_id` 发起同样请求，对比两次响应的状态码与 `msg` 是否可被用于探测 Package 是否存在。 | 两种场景均返回 403，不含任何 Episode/路径信息；无副作用（不产生历史、不改计数、不扣 U2 额度）；**若两种场景的 `msg` 文案不同（当前代码确实不同："package not found" vs "package does not belong to this API key"），需与产品/安全确认这是否可接受，若不可接受则判定为 Bug（信息泄露：可被用于枚举他人 Package 是否存在）。** | ☐ 待执行 |
| DL-08 | 下载与 Package 与幂等 | P0 | 验证携带相同 `Idempotency-Key` 且请求内容一致时，无论顺序重试还是并发重试，只应真正交付和计数一次。 | U1 请求下载全新 Episode E27，生成 `Idempotency-Key:K1`。 | 1. 用 `K1` 发起下载 E27 请求，等待完成。<br>2. 用相同 `K1` 和请求体顺序再发 2 次。<br>3. 用相同 `K1` 和请求体并发发起 5 个请求。<br>4. 对比所有响应内容是否一致。<br>5. 查询 `download_count`（应为 1）、`data_downloads`（应仅 1 条）、`used`（只扣 1 次）。 | 所有重复请求（顺序+并发）返回与首次相同结果（相同 `download_id`）；`download_count` 全程只 +1；仅产生 1 条历史；`used` 只扣 1 次。 | ☐ 待执行 |
| DL-09 | 下载与 Package 与幂等 | P0 | 验证相同 Idempotency Key 但不同 Episode 集合时，服务端能识别为"指纹冲突"，返回明确错误，不静默复用或污染旧结果。 | U1 已用 `Idempotency-Key:K2` 成功下载过 `[E28]`。 | 1. 用相同 `K2`，但请求体改为 `[E28,E29]`。<br>2. 检查响应状态码与错误信息。<br>3. 查询 E29 是否被错误加入/计数。<br>4. 查询 K2 原历史是否被篡改。 | 返回明确幂等冲突错误（如 409），而非静默按旧结果或新内容处理；E29 不应被意外加入或计数；原 K2 历史记录保持不变。 | ☐ 待执行 |
| DL-10 | 下载与 Package 与幂等 | P0 | 【核心风险 DD-R03】验证相同 Idempotency Key + 相同 Episode 集合但用于不同 Package 请求 Download Session（`POST /v1/data/download-sessions`，`X-API-Key` 鉴权）时，是否会错误复用先前 Package 的下载记录/文件路径。**代码依据**：`data_downloads` 的幂等唯一约束是 `(user_id, mode, idempotency_key)`（见 `_insert_pending_download`），`package_id` 确实不在约束内，与本行风险描述一致。 | 用同一个 U1 的 `X-API-Key`，创建两个 Episode 集合相同（`[E30,E31]`）但 `package_id` 不同的 Package C 和 Package D。 | 1. 携带 `Idempotency-Key:K3`，调用 `POST /v1/data/download-sessions` `{"package_id":"C"}` 并完成交付，记录 `download_id`/路径/`data_downloads.package_id`。<br>2. 携带相同 `K3`，调用同一接口 `{"package_id":"D"}`（Episode 集合相同）。<br>3. 对比第 2 步响应与第 1 步，重点检查返回内容及 `data_downloads.package_id` 字段。<br>4. 查询 `data_downloads` 中该 `download_id` 记录最终归属哪个 `package_id`。 | 期望（修复后）：第 2 步应视为全新请求（因 `package_id` 不同），生成独立 `download_id` 且 `data_downloads.package_id` 正确指向 D。**若测试发现第 2 步直接复用了 C 的下载结果（返回相同 `download_id`、`package_id` 仍为 C 或未生成新记录），判定为 Fail，记为 P0 Bug（DD-R03），发布前强制阻断。** | ☐ 待执行 |
| DL-11 | 下载与 Package 与幂等 | P1 | 验证一次下载因构建失败被标记 FAILED 后，占用同一 Idempotency Key 是否导致用户无法用同一 Key 重新发起有效重试。 | 可通过 Mock/注入异常让某次下载以 `Idempotency-Key:K4` 失败落库为 FAILED。 | 1. 触发注定失败的下载（如缺视频文件），`Idempotency-Key:K4`，确认最终 FAILED。<br>2. 修复失败原因（补齐文件），用相同 `K4` 重新发起相同请求。<br>3. 检查是否能正常重试成功，还是被历史 FAILED 记录卡住。<br>4. 确认产品期望的恢复路径（新 Key 是否可用/是否有专门重试接口）。 | 记录当前实际行为并与产品期望策略对照；若相同 Key 无法安全恢复且无替代提示，判定为 P1 Bug（DD-R05）；无论何种结果，不应重复扣额或产生数据不一致。 | ☐ 待执行 |
| DL-12 | 下载与 Package 与幂等 | P1 | 验证下载会话处于 PENDING 时若服务中断，系统是否有超时清理/恢复机制，防止请求永久卡死且额度/计数处于不确定状态。 | 能在测试环境模拟服务中断（如处理中手动重启/杀进程）。 | 1. 发起下载请求，状态刚变 PENDING 时立即中断/重启处理服务。<br>2. 等待覆盖已知超时阈值的时长（如无明确配置则等待 30 分钟）。<br>3. 查询该记录最终状态。<br>4. 查询用户 `used` 与相关 Episode `download_count` 是否被正确处理。<br>5. 检查是否有清理 Job/告警/人工介入流程。 | 记录不应无限期停留 PENDING，应在合理时间内标记 FAILED 或自动恢复完成；若长期无清理机制，判定为 P1 Bug（DD-R06）；最终额度和计数应与实际交付状态一致，不能出现"已扣额但从未交付"且无法感知的情况。 | ☐ 待执行 |
| DL-13 | 下载与 Package 与幂等 | P1 | 验证目标 MCAP/视频文件缺失时，下载请求不能被错误标记成功，必须明确报错。 | 构造 E32，`status=DERIVED_READY` 但底层存储实际缺失 mcap 或某视频文件（如手动删除 GCS 对象）。 | 1. 分别通过 UI Download、Manifest、API Package+Session 三种入口尝试下载 E32。<br>2. 检查每种入口响应状态码和错误信息。<br>3. 查询 `download_count` 是否被错误增加。<br>4. 查询 `data_downloads` 是否被错误标记成功。<br>5. 核对 `used` 扣减时机是否与文档口径一致（加入 My Data 与实际交付分离）。 | 三种入口均明确返回失败，不应返回"成功"；`download_count` 不增加，`data_downloads` 不生成成功状态记录；错误信息能定位到"文件缺失"这一具体原因。 | ☐ 待执行 |
| DL-14 | 下载与 Package 与幂等 | P1 | 验证"下载整个 Upload"但其下 Episode 存在部分 READY/部分处理中或失败/部分不可见时，接口必须明确返回实际选择/交付数量，不能静默过滤误导用户。 | 构造一个 Upload，5 个 Episode 分别为：2 个 `DERIVED_READY`（可见）、1 个 `DERIVED_VALIDATION_FAILED`、1 个 `UPLOAD_PROCESSING`、1 个对当前用户不可见。 | 1. 用户对该 Upload 发起"下载整个 Upload"请求（UI 或 Manifest）。<br>2. 检查响应中实际选中/交付的 Episode 数量和 `selected_episode_ids`。<br>3. 检查是否有明确提示"共 X 个可下载，Y 个不可用"。<br>4. 查询实际生成的下载历史是否只含 2 个 `DERIVED_READY` Episode。 | 只有 2 个 `DERIVED_READY` Episode 被选中交付，`selected_episode_ids` 长度为 2；响应/页面明确说明实际下载数量与 Upload 总数差异；**若无任何差异提示，判定为 P1 Bug（DD-R08）**。 | ☐ 待执行 |
| DL-15 | 下载与 Package 与幂等 | P1 | 验证下载历史分页在数据量较大时不遗漏不重复，且详情接口 `GET /data/downloads/{download_id}` 返回的 `selected_episode_ids` 与实际交付完全精确匹配。 | 为 U1 构造 ≥25 条下载历史（可通过多次执行 DL-01~DL-03 累积）。 | 1. 调用历史列表接口，`page_size=10`，依次翻取第 1/2/3 页。<br>2. 汇总三页记录，检查总条数、有无重复 `download_id`、有无遗漏。<br>3. 确认返回结构为标准分页对象（含 `total`/`page`/`page_size`），评估旧客户端直接当数组遍历的兼容性风险。<br>4. 任选 3 条记录调用详情接口。<br>5. 核对详情中 `selected_episode_ids` 与该次实际交付是否完全一致。 | 三页汇总总条数与数据库实际记录数一致，无重复无遗漏；分页对象结构规范；详情接口 `selected_episode_ids` 精确匹配实际交付内容，不多不少。 | ☐ 待执行 |
| DL-16 | 下载与 Package 与幂等 | P1 | 验证不携带 `Idempotency-Key`（旧客户端/网络库自动重试且未生成 Key）时，网络超时触发的自动重试是否产生重复下载历史和重复 `download_count`。 | U1 即将下载 E33；构造服务端首次响应延迟超过客户端超时阈值的场景。 | 1. 不带 `Idempotency-Key`，发起下载 E33 请求，人为让处理耗时超过客户端超时设置。<br>2. 客户端超时后自动（或手动模拟）重发完全相同请求（同样不带 Key）。<br>3. 查询 `download_count` 变化。<br>4. 查询 `data_downloads` 是否新增 2 条记录。 | 记录当前实际行为：若无兜底幂等机制，预期 `download_count` +2、产生 2 条历史（对应已知风险 DD-R07）；应记录为 P1 缺陷或改进项，推动产品/研发决策是否发布前修复（如按用户+Episode+时间窗口生成兜底 Key）。 | ☐ 待执行 |
| DL-17 | 下载与 Package 与幂等 | P1 | 验证 Package 详情接口已完全移除 Upload/Bucket/文件路径快照字段，防止旧版本前端因读取到 undefined 字段而报错。 | 使用新模型下创建的 Package（如 DL-04 中的 Package A）。 | 1. 调用 Package 详情接口获取完整响应 JSON。<br>2. 逐一检查是否还包含 Upload Snapshot、Bucket Snapshot、MCAP/Video 路径快照等旧字段。<br>3. 用模拟旧版本前端（或代码走查）确认其读取这些旧字段时的实际行为（报错/undefined/优雅降级）。<br>4. 检查 Episode 列表是否改为引用当前 Episode 数据而非快照。 | 响应中不包含任何旧版快照字段；若旧版本前端会因此直接报错崩溃而非优雅降级，判定为兼容性风险（R-09/DD-R09），需发布前确认候选前端已适配。 | ☐ 待执行 |
| SYS-01 | Migration 与权限与 Hex | P0 | 验证 Migration 脚本 `20260730_data_user_library_episodes.sql` 在接近生产规模的脱敏数据副本上执行的完整表现，包括新表结构、数据处置是否符合已批准方案、执行耗时和锁影响——发布最高风险项。 | 已获得产品/数据团队书面批准的数据处置方案；已完成三张待清空表及相关依赖数据的完整备份；准备脱敏后、规模与生产相当的数据库副本。 | 1. 执行前记录三张待清空表及 `data_user_library_episodes` 行数快照。<br>2. 在副本环境执行 Migration SQL。<br>3. 记录执行耗时，监控执行期间锁等待/连接数/CPU-IO。<br>4. 执行后检查新表字段、主键、索引、默认值是否符合设计。<br>5. 检查三张表是否已清空且 Identity 已重置。<br>6. 按批准方案验证是否需要 Backfill，若需要则执行并核对数量。<br>7. 触发一次数据库回滚，验证回滚方案可行且耗时可接受。 | 执行时间在业务可接受维护窗口内，未发现长时间锁表导致其他请求超时；三张表被正确清空、Identity 重置，新表结构与设计一致；数据处置结果与已批准方案完全一致；回滚演练能在预期时间内恢复到迁移前状态，数据完整无损。 | ☐ 待执行 |
| SYS-02 | Migration 与权限与 Hex | P0 | 验证部署流水线意外重复执行同一个 Migration 脚本时系统行为是否安全，不会二次破坏数据或导致部署流程挂起。 | 紧接 SYS-01 完成一次成功执行之后的同一副本环境。 | 1. 再次执行同一份 Migration SQL。<br>2. 观察结果：是否报错、是否可安全跳过、是否会再次清空已产生的新数据。<br>3. 检查执行后表结构和数据是否发生非预期变化。 | 应符合部署平台的幂等策略（Migration 版本表阻止重复执行，或 SQL 本身对重复执行安全）；**若重复执行会再次清空届时已产生的新业务数据，判定为 P0 风险，发布前必须有明确的流水线保护措施。** | ☐ 待执行 |
| <span style="color:#2563eb">SYS-03</span> | <span style="color:#2563eb">Migration 与权限与 Hex</span> | <span style="color:#2563eb">P0</span> | <span style="color:#2563eb">【已按 `470ab3d` 更新预期】验证无有效会员 Plan 的用户访问各入口时，写/下载类被拒绝，只读类按分层策略放行（或产品确认后改为全拒）。不允许写入口"漏检"导致数据写入。</span> | <span style="color:#2563eb">构造从未订阅或 Plan `status!=ACTIVE` / membership 为空的测试用户 U3；Token 有效。</span> | <span style="color:#2563eb">1. 用 U3 Token 依次调用写/下载入口：`POST /data/my-data`、`check`、UI Download、Manifest、创建 API Package、`GET /data/api-download-membership/current`、创建 API Key。<br>2. 再调用只读入口：`GET /data/my-data/summary`、`GET /data/my-data/episodes`、`GET /data/api-keys`。<br>3. 若 U3 名下已有 ACTIVE API Key，再调用 `POST /v1/data/download-sessions`。<br>4. 检查写入口是否全部 403；只读入口是否按当前代码返回 200（若产品要求只读也 403，则记 DD-R18）。<br>5. 确认数据库无新写入/额度扣减。</span> | <span style="color:#2563eb">写/下载入口全部 403，错误信息指向 membership/plan；`X-API-Key` 路径同样 403 且不更新 `last_used_at`；只读入口当前实现预期为 200（仅登录即可）——**若产品口径要求全拒而实际放行，判定为 P1（DD-R18）**；数据库无新增业务数据。</span> | <span style="color:#2563eb">☐ 待执行</span> |
| SYS-04 | Migration 与权限与 Hex | P0 | 验证 Admin/Unlimited Quota 用户在三种下载路径下均不受月度额度限制，同时确认判断逻辑配置完整、不会因配置缺项被误判为普通用户从而遭遇意外 403。 | 构造 Admin 或 Unlimited Plan 测试用户 U4，且相关标记字段（plan 类型、role）完整设置；另构造一个"配置不完整"的 Unlimited 用户用于对照。 | 1. U4 一次性请求远超普通额度的 Episode 数量（如 200 个全新）。<br>2. 分别通过 UI/Manifest/API Package 三种入口执行请求。<br>3. 检查响应状态码，确认未因超出普通额度被拒绝。<br>4. 用配置不完整的 Unlimited 用户重复请求，观察是否被误判为普通用户导致 403。 | 配置完整的 U4 在三种入口下均不受额度限制，全部成功；配置不完整场景的实际行为需明确记录——若因字段缺失被误判 403，判定为 P1 Bug（DD-R12），需产品明确完整判断条件并推动修复。 | ☐ 待执行 |
| SYS-05 | Migration 与权限与 Hex | P1 | 验证 Hex 本地额度预估逻辑（`prepare_download_estimate` 等）是否与 Pipeline 后端保持一致，只对新 Episode 计入额度消耗。 | 为测试用户准备已拥有和全新混合的 Episode 集合（3 个已拥有 + 2 个全新）。 | 1. 通过 Hex 对话请求下载这 5 个 Episode。<br>2. 记录 Hex 展示的额度预估信息（Hex 侧的 used/new/projected/remaining 等价展示）。<br>3. 同时直接调用 `POST /data/my-data/check` 获取真实计算结果（`quota.new_episodes`）。<br>4. 对比两者数字是否完全一致。 | Hex 展示的新增数为 2（不是 5），与 Pipeline 返回的 `quota.new_episodes=2` 完全一致；若 Hex 本地估算对已拥有 Episode 也计入新增，判定为 Bug（DD-R10）。 | ☐ 待执行 |
| SYS-06 | Migration 与权限与 Hex | P1 | 验证 Hex 判断某 Upload 是否"完整下载"的逻辑，能否识别"多次分批下载累计覆盖全部 Episode"的情况，而非只检查单次请求。 | 一个 Upload 下 4 个可下载 Episode；测试用户此前分两次分别下载了其中 2 个和另外 2 个（从未在单次请求中覆盖全部 4 个）。 | 1. 询问 Hex"这个 Upload 是否已完整下载"。<br>2. 记录 Hex 回答（是/否）及判断依据。<br>3. 对比数据库中该用户对该 Upload 下 4 个 Episode 的实际拥有/下载状态。 | 若 Hex 回答"未完整下载"（即使 4 个均已在不同请求中下载过），记录为已知设计限制（第 10 节第 6 点），需与产品确认是否可接受；无论如何 Hex 不应给出与数据库实际状态矛盾、误导用户重复下载的结论。 | ☐ 待执行 |
| SYS-07 | Migration 与权限与 Hex | P1 | 验证 Hex Agent 在创建包含已被其他 Package 使用过的 Episode 的新 Package 时，不再触发过时的 `duplicate_episode_conflict` 旧交互分支。 | 用户已通过 Hex 或 API 创建过 Package A，包含若干 Episode。 | 1. 通过 Hex 请求创建新 Package，Episode 集合与 Package A 部分重叠。<br>2. 观察 Hex 回复和后续引导流程。<br>3. 检查后端原始响应是否包含旧版 `conflicting_episode_ids` 或类似冲突标志字段。<br>4. 检查 Hex 是否展示"是否强制创建新 Package"等过时文案。 | Package 创建直接成功，Hex 不展示任何旧版冲突确认对话或过时文案；若 Hex 仍保留旧分支逻辑并在边界条件下被触发，判定为需清理的技术债（DD-R13），记录但视严重程度决定是否阻断发布。 | ☐ 待执行 |
| SYS-08 | Migration 与权限与 Hex | P1 | 验证会员套餐降级导致 `quota.used_episodes > 新 monthly_episode_limit` 时，若本次请求全部为已拥有 Episode（`new_episode_count=0`），Hex 本地预估（Hex 侧字段为 `quota_exceeded`，见第 10 节）与 Pipeline `would_exceed_quota` 判断是否给出矛盾结论。 | 测试用户历史 `quota.used_episodes=80`（旧 `monthly_episode_limit=100` 下产生），随后套餐降级为 `monthly_episode_limit=50`（此时 `used_episodes>limit`）。 | 1. 用户请求重新下载一批已拥有的 Episode（预期 `new_episode_count=0`）。<br>2. 分别通过 Hex 对话和直接调用 `POST /data/my-data/check` 接口，记录各自是否超额（Hex 的 `quota_exceeded` vs Pipeline 的 `would_exceed_quota`）的结论。<br>3. 对比两条路径结论是否一致。<br>4. 实际发起下载，确认最终是否成功（因 `new_episode_count=0` 理论上不应拒绝）。 | 由于 `new_episode_count=0`，不应被拒绝；Hex 与 Pipeline 结论必须一致；**若 Hex（只在 `new_episodes>0` 时置 `quota_exceeded=true`）与 Pipeline 的 `would_exceed_quota`（只判断 `projected_episodes>monthly_episode_limit`）在此场景给出不同结果，判定为 Bug（DD-R10）**，需统一额度计算公式后重测。 | ☐ 待执行 |
| SYS-09 | Migration 与权限与 Hex | P1 | 验证 402 响应原始 Payload（`data.used_episodes`/`data.new_episodes`/`data.projected_episodes`/`data.remaining_episodes`）被 Hex/前端转换展示后，用户看到的数字与后端原始数据完全一致，不因字段命名或 fallback 逻辑差异展示错误的剩余额度。 | 构造一个明确触发 402 的请求（如 MYD-06 场景），已知 Pipeline 返回的原始字段值。 | 1. 直接调用 Pipeline 接口，记录原始 402 响应体完整字段值。<br>2. 通过前端 UI 发起同样请求，记录页面展示的错误提示文案及数字。<br>3. 通过 Hex 发起同样请求，记录 Hex 回复中的数字。<br>4. 对比三者 `used_episodes`/`remaining_episodes` 等数字是否完全一致。 | 前端和 Hex 展示的所有数字都应与 Pipeline 原始 Payload 完全一致；**若因 `remaining_episodes` fallback 计算方式不同（`monthly_episode_limit - used_episodes` vs `monthly_episode_limit - projected_episodes`，对应代码中 `remaining_episodes = max(monthly_episode_limit - projected_episodes, 0)`）导致展示不同数字，判定为 Bug（DD-R10）**，需统一 fallback 计算公式。 | ☐ 待执行 |
| SYS-10 | Migration 与权限与 Hex | P0 | 【发布阻断项】验证即将用于生产发布的实际前端候选版本（不一定是本次分析的 Commit Range）已完整适配全部 Data Download 新 API 契约变化。 | 与研发/发布负责人确认本次发布实际使用的前端 Commit/Tag（不能想当然使用本次分析范围的版本）。 | 1. 确认候选前端版本号/Commit SHA，检出或部署到测试环境。<br>2. 逐项核对第 8 节全部 API 破坏性变化：`selected_upload_ids`→`selected_episode_ids`、下载历史分页结构、Package 详情移除快照字段、移除旧 Quota Snapshot 字段、重复 Episode 不再返回 409、Admin Unlimited Quota 语义调整。<br>3. 对每一项在候选前端上实际触发对应场景，确认渲染/交互正确，无 JS 报错或字段 undefined 导致的异常显示。<br>4. 执行一次完整的"UI 下载 → 查看下载历史 → 查看 Package 详情"端到端回归。 | 全部 6 项破坏性变化在候选前端上均已正确适配，无因契约变化导致的页面报错或数据异常；**若候选前端仍是"未适配"版本或适配不完整，判定为发布阻断项（DD-R09/发布准入条件第 6 条），必须先完成适配才能发布。** | ☐ 待执行 |
| <span style="color:#2563eb">FE2-01</span> | <span style="color:#2563eb">新前端 prismax-marketing-rp</span> | <span style="color:#2563eb">P0</span> | <span style="color:#2563eb">【已按 testing 重写】验证 My Data Tab 已可用：入口可点、切换 `?view=my-data`、加载 `summary`/`episodes`/`membership`，侧栏 Task/Robot/Quota、预览与 Owned 状态正常。**代码**：`RoboticDataPageClient.tsx` + `MyDataWorkspace.js`（`4cb1f0a` 起）。</span> | <span style="color:#2563eb">测试账号已登录且 My Data 中至少有 1 个 ACTIVE Episode；Active Membership。</span> | <span style="color:#2563eb">1. 打开 `/robotic-data`，点击 "My Data" Tab（或 `?view=my-data`）。<br>2. 网络面板确认 `GET /data/my-data/summary`、`GET /data/my-data/episodes`、`GET /data/api-download-membership/current` 均为 200。<br>3. 检查侧栏分类/任务计数、Monthly quota、`Owned` 标识、相机预览与 episode 表格（含 DOWNLOADS）。<br>4. 用搜索/Robot 过滤切换 Task。</span> | <span style="color:#2563eb">My Data 可进入且非 "Coming soon"；三接口成功；UI 数字与接口字段一致；过滤后列表正确。若仍禁用 Coming soon，说明部署版本落后于 testing，判定 Fail。</span> | <span style="color:#2563eb">☐ 待执行</span> |
| <span style="color:#2563eb">FE2-02</span> | <span style="color:#2563eb">新前端 prismax-marketing-rp</span> | <span style="color:#2563eb">P1</span> | <span style="color:#2563eb">验证 Browse 创建 API Package 时不再出现旧版 409 冲突 UI。**现状**：testing 上 `postCreateApiPackage` 已只提交 `selected_episode_ids`/`name`，无 `allow_already_packaged`、无 409 分支。</span> | <span style="color:#2563eb">已存在 Package A（含 E1、E2）；额度充足。</span> | <span style="color:#2563eb">1. Browse 选中 E1、E2 及新 Episode E3，创建 API Package。<br>2. 观察是否有冲突弹窗。<br>3. 网络面板确认状态码 200/201，无 409。</span> | <span style="color:#2563eb">直接创建成功，无冲突二次确认；若仍弹出旧冲突 UI，判定 Fail（部署未含清理提交）。</span> | <span style="color:#2563eb">☐ 待执行</span> |
| <span style="color:#2563eb">FE2-03</span> | <span style="color:#2563eb">新前端 prismax-marketing-rp</span> | <span style="color:#2563eb">P2</span> | <span style="color:#2563eb">验证下载历史展示：testing 已改为 `formatDownloadMode(entry.mode)` + `episode_count`/`total_bytes`，不再读 `selected_upload_ids`（DD-R15 降级为“无 Task 名”体验问题）。</span> | <span style="color:#2563eb">已有至少一条 UI/Manifest/API 下载历史。</span> | <span style="color:#2563eb">1. Browse → 下载历史。<br>2. 核对标题是否为 Browser/Manifest/API download。<br>3. 核对 episode 数与 size 是否与接口一致。</span> | <span style="color:#2563eb">不再因缺失 `selected_upload_ids` 报错；展示下载方式而非 Task 名——记录产品是否接受（DD-R15）。</span> | <span style="color:#2563eb">☐ 待执行</span> |
| <span style="color:#2563eb">FE2-04</span> | <span style="color:#2563eb">新前端 prismax-marketing-rp</span> | <span style="color:#2563eb">P1</span> | <span style="color:#2563eb">【已按 `470ab3d` 改写】验证无 `operator/admin` 角色、但具备 Active Membership 的登录用户，在 `/robotic-data` 上可正常下载；并对照旧前端 `app-prismax-rp` 是否仍按角色误拦（DD-R16）。后端自 `470ab3d` 起不再校验 `user_role`，只校验 Active Membership。</span> | <span style="color:#2563eb">账号 U5：`user_role` 非 operator/admin，但 `user_data_download_membership` 指向 ACTIVE Plan；额度充足。另准备同条件账号在 `app-prismax-rp` 对照。</span> | <span style="color:#2563eb">1. 用 U5 登录 `prismax-marketing-rp` `/robotic-data`，选中 Episode 并执行 UI/Manifest/创建 Package。<br>2. 确认后端返回 200，额度与历史正确。<br>3. 用同一账号打开 `app-prismax-rp` Robotic Data 页面，观察是否被 `hasRoboticDataAccess(userRole)` 提前拦截。<br>4. 记录两套前端差异。</span> | <span style="color:#2563eb">marketing 前端：下载成功（角色不再是门槛）；若 `app-prismax-rp` 仍因角色白名单拦截已有会员用户，判定为 P1 Bug（DD-R16），需改前端门槛或明确产品仍要角色白名单。</span> | <span style="color:#2563eb">☐ 待执行</span> |
| <span style="color:#2563eb">FE2-05</span> | <span style="color:#2563eb">新前端 prismax-marketing-rp</span> | <span style="color:#2563eb">P1</span> | <span style="color:#2563eb">【已按 testing 重写】验证 Browse UI/Manifest 与 My Data 下载已在 body 携带 `idempotency_key`（`createIdempotencyKey`）。API Package 创建仍可不带 Key——记录差异。</span> | <span style="color:#2563eb">Active Membership；可抓包。</span> | <span style="color:#2563eb">1. Browse：Browser download / Manifest，确认 body 含 `idempotency_key`（如 `browser-…` / `manifest-…`）。<br>2. My Data：Download，确认 `idempotency_key`（如 `my-data-browser-…`）。<br>3. 创建 API Package，确认是否仍无幂等键。<br>4. 对带 Key 的入口快速重复点击，查 `download_count`/历史是否只 +1。</span> | <span style="color:#2563eb">UI/Manifest/My Data 下载请求含唯一 `idempotency_key`；重复点击不重复计数。Package 创建无 Key 记为已知差异（非阻断，除非产品要求）。</span> | <span style="color:#2563eb">☐ 待执行</span> |
| <span style="color:#2563eb">FE2-06</span> | <span style="color:#2563eb">新前端 prismax-marketing-rp</span> | <span style="color:#2563eb">P1</span> | <span style="color:#2563eb">验证 Browse 目录仍走 `?public=1` 匿名端点；My Data 预览改为鉴权 `GET /data/downloadable-episodes/{id}/preview-videos`（无 public）。确认公开范围符合预期。</span> | <span style="color:#2563eb">未登录会话 + 已登录有 My Data 的会话。</span> | <span style="color:#2563eb">1. 未登录打开 Browse，确认 `downloadable-uploads?public=1`。<br>2. 登录进 My Data 打开预览，确认 preview-videos **不带** `public=1` 且带 Authorization。<br>3. 未登录尝试下载，应要求登录。</span> | <span style="color:#2563eb">Browse 匿名范围符合产品预期；My Data 预览需登录；下载必须登录。</span> | <span style="color:#2563eb">☐ 待执行</span> |
| <span style="color:#2563eb">FE2-07</span> | <span style="color:#2563eb">新前端 prismax-marketing-rp</span> | <span style="color:#2563eb">P1</span> | <span style="color:#2563eb">回归 Browse 与 My Data 两侧额度展示：`used_episodes` / `monthly_episode_limit` / `remaining_episodes` 与 `GET .../membership/current` 一致，且下载后刷新。</span> | <span style="color:#2563eb">已有部分额度用量。</span> | <span style="color:#2563eb">1. 记录 membership/current 原始字段。<br>2. 对比 Browse 侧栏与 My Data 底部 Monthly quota。<br>3. 完成一次成功下载后确认两侧刷新。</span> | <span style="color:#2563eb">两侧数字与接口一致；下载后自动刷新，无需整页刷新。</span> | <span style="color:#2563eb">☐ 待执行</span> |
| <span style="color:#2563eb">FE2-08</span> | <span style="color:#2563eb">新前端 prismax-marketing-rp</span> | <span style="color:#2563eb">P0</span> | <span style="color:#2563eb">验证 Browse「Add to My Data」调用 `POST /data/my-data`，只对新 Episode 扣额；成功后可在 My Data Tab 看到新增项，且加入≠下载（`download_count` 仍为 0，无新 `data_downloads`）。</span> | <span style="color:#2563eb">Active Membership；选中含已拥有 + 全新 Episode。</span> | <span style="color:#2563eb">1. Browse 选中混合集合，点 Add to My Data。<br>2. 核对响应 `added_*` / `already_owned_*` / `quota`。<br>3. 切到 My Data 确认新 Episode 出现。<br>4. 查库 `download_count` 与 `data_downloads`。</span> | <span style="color:#2563eb">仅新增部分扣额；My Data 可见；`download_count=0`；无下载历史。</span> | <span style="color:#2563eb">☐ 待执行</span> |
| <span style="color:#2563eb">FE2-09</span> | <span style="color:#2563eb">新前端 prismax-marketing-rp</span> | <span style="color:#2563eb">P0</span> | <span style="color:#2563eb">验证 My Data 页内 Browser Download：`POST /data/downloads/ui` + `selected_episode_ids` + `idempotency_key`；成功后表格 DOWNLOADS +1，quota 不因已拥有而增加 used。</span> | <span style="color:#2563eb">My Data 中已有 ACTIVE Episode；membership active。</span> | <span style="color:#2563eb">1. 在 My Data 选中 ≤10 个 Episode 下载。<br>2. 抓包确认请求体字段。<br>3. 刷新列表核对 DOWNLOADS / `download_count`。<br>4. 核对 used 不变（已拥有）。</span> | <span style="color:#2563eb">下载成功；计数 +1；used 不变；超过 10 个时前端拦截提示。</span> | <span style="color:#2563eb">☐ 待执行</span> |
| <span style="color:#2563eb">FE2-10</span> | <span style="color:#2563eb">新前端 prismax-marketing-rp</span> | <span style="color:#2563eb">P0</span> | <span style="color:#2563eb">验证 Membership inactive（`membership/current` 403）时 My Data **只读**：仍可看 summary/episodes，Quota 显示 Inactive，Download 被前端拦截提示需 active membership（对齐 DD-R18 前端体验）。</span> | <span style="color:#2563eb">用户 Token 有效、My Data 有数据，但 membership 为空/Plan 非 ACTIVE。</span> | <span style="color:#2563eb">1. 打开 My Data，确认 summary/episodes 200。<br>2. 确认侧栏显示 Membership Inactive / read-only 文案。<br>3. 尝试 Download，应 warning 且不发成功下载（或后端 403）。</span> | <span style="color:#2563eb">可读不可下；文案明确；无错误扣额/无脏历史。</span> | <span style="color:#2563eb">☐ 待执行</span> |
| <span style="color:#2563eb">AUTH-01</span> | <span style="color:#2563eb">鉴权与 Membership</span> | <span style="color:#2563eb">P0</span> | <span style="color:#2563eb">验证任意 `user_role`（含 `null`/非 operator）只要具备 Active Membership，即可通过 `_require_active_data_membership` 完成 My Data 加入与下载。对应单测 `test_active_membership_accepts_any_user_role` / `test_authenticated_user_does_not_require_operator_role`。</span> | <span style="color:#2563eb">用户 U6：`user_role=null`，membership=`pro` 且 Plan ACTIVE；E40 全新。</span> | <span style="color:#2563eb">1. 调用 `POST /data/my-data` `episode_ids:[E40]`。<br>2. 调用 `POST /data/downloads/ui` 下载 E40。<br>3. 调用 `GET /data/api-download-membership/current`。</span> | <span style="color:#2563eb">三步均 200；`used_episodes` 正确 +1；不因缺少 operator/admin 角色被 403。</span> | <span style="color:#2563eb">☐ 待执行</span> |
| <span style="color:#2563eb">AUTH-02</span> | <span style="color:#2563eb">鉴权与 Membership</span> | <span style="color:#2563eb">P0</span> | <span style="color:#2563eb">验证有 operator 角色但无 Membership / Plan 非 ACTIVE 的用户，写入口仍 403（角色不能替代 Membership）。对应 `test_missing_membership_is_forbidden`。</span> | <span style="color:#2563eb">用户 U7：`user_role=operator`，`user_data_download_membership` 为空或指向非 ACTIVE Plan。</span> | <span style="color:#2563eb">1. 调用 `POST /data/my-data`、UI Download、创建 API Package、`GET .../membership/current`。<br>2. 记录状态码与 `msg`。</span> | <span style="color:#2563eb">全部 403；`msg` 含 membership / plan not active 一类语义；无库表写入。</span> | <span style="color:#2563eb">☐ 待执行</span> |
| <span style="color:#2563eb">AUTH-03</span> | <span style="color:#2563eb">鉴权与 Membership</span> | <span style="color:#2563eb">P0</span> | <span style="color:#2563eb">验证请求体 `user_id` 与 Token 用户不一致时下载被拒绝；一致或省略时以 Token 用户为准。对应 `test_download_request_rejects_another_user_id` / `test_download_request_uses_authenticated_owner_not_role`。</span> | <span style="color:#2563eb">会员用户 U8（userid=42），Active Membership。</span> | <span style="color:#2563eb">1. `POST /data/downloads/ui` body 带 `user_id=99` 与合法 `selected_episode_ids`。<br>2. 再发一次 `user_id=42` 或省略 `user_id`。</span> | <span style="color:#2563eb">步骤 1 返回 403（`user_id does not match token`）；步骤 2 按正常会员流程处理（成功或后续业务错误，但不因 user_id 不匹配失败）。</span> | <span style="color:#2563eb">☐ 待执行</span> |
| <span style="color:#2563eb">AUTH-04</span> | <span style="color:#2563eb">鉴权与 Membership</span> | <span style="color:#2563eb">P0</span> | <span style="color:#2563eb">验证 Membership 失效后，已有 ACTIVE API Key 不能再创建 Download Session，且失败时不更新 `last_used_at`。对应 `test_expired_membership_cannot_use_an_existing_api_key`（DD-R19）。</span> | <span style="color:#2563eb">U9 名下 API Key 状态 ACTIVE；随后清空 membership 或将 Plan 置非 ACTIVE；记录当前 `last_used_at`。</span> | <span style="color:#2563eb">1. 用该 Key 调用 `POST /v1/data/download-sessions`。<br>2. 再查 `data_api_keys.last_used_at`。<br>3. 可选：恢复 membership 后同一 Key 应可再次使用。</span> | <span style="color:#2563eb">步骤 1 返回 403；`last_used_at` 与调用前一致；恢复 membership 后 Key 可继续使用（除非产品另有吊销策略）。</span> | <span style="color:#2563eb">☐ 待执行</span> |
| <span style="color:#2563eb">AUTH-05</span> | <span style="color:#2563eb">鉴权与 Membership</span> | <span style="color:#2563eb">P1</span> | <span style="color:#2563eb">回归 `ca1e000`：`GET /data/my-data/episodes` 在可选过滤参数为 NULL/缺省或带 `task_id`/`search` 时，PostgreSQL 不因参数类型推断失败而 500。SQL 已改为 `CAST(:task_id AS BIGINT) IS NULL`、`CAST(:search_pattern AS TEXT) IS NULL`。</span> | <span style="color:#2563eb">登录用户已有若干 ACTIVE My Data 记录。</span> | <span style="color:#2563eb">1. 不带过滤：`GET /data/my-data/episodes?page=1&page_size=10`。<br>2. 仅 `task_id`：`...?task_id=<真实 task_id>`。<br>3. 仅 `search`：`...?search=episode`。<br>4. 组合 `task_id` + `robot` + `search`。<br>5. 非法 `task_id=abc`（若接口有校验则 400，否则记录实际行为）。</span> | <span style="color:#2563eb">合法请求均 200，分页正常；不应出现 Postgres 类型错误导致的 500；过滤结果与数据一致。</span> | <span style="color:#2563eb">☐ 待执行</span> |

## 13. 测试执行策略

### 阶段一：Migration 与 API 契约

1. 在旧 Schema 和脱敏生产规模数据上执行 Migration。
2. 检查新表、主键、索引、外键、权限和重复执行行为。
3. 对被清空表执行迁移前后数量对账。
4. 确认前端已适配 `selected_episode_ids` 和分页下载历史。
5. 验证普通用户、无 Plan、Admin 和 Unlimited Plan。
6. 验证 `470ab3d` 鉴权分层（只读 vs 写/下载）及 `prismax-marketing-rp` / `app-prismax-rp` 前端门槛差异（AUTH / FE2）。

### 阶段二：核心业务

1. 覆盖 My Data 新增、重复、混合、Archived、Revoked、Refunded。
2. 覆盖额度上限、超额、UTC 月切换和套餐降级。
3. 覆盖 UI、Manifest 和 API Package 三种下载路径。
4. 对账实际交付 Episode、历史 Episode 和 Download Count。

### 阶段三：并发与故障恢复

1. 相同 Episode 和不同 Episode 的并发授权。
2. Remaining 临界点的并发额度请求。
3. 相同/不同 Idempotency Key、Episode 集合和 Package。
4. PENDING、FAILED、服务重启、响应丢失和客户端重试。

### 阶段四：兼容性与性能

1. 旧客户端字段兼容或明确版本阻断。
2. 大量 My Data Episode 的分页、过滤和汇总性能。
3. 大 Package 创建和 Download Session 构建性能。
4. 多时区展示与 UTC 月度额度切换。

## 14. 可观测性建议

上线前建议增加：

- My Data 402 数量及比例。
- 用户 Used/New/Projected/Limit 的额度决策日志。
- PENDING 下载数量和超时持续时间。
- Idempotency Conflict、FAILED 和重试次数。
- 请求 Episode 数、Eligible 数与实际交付数差异。
- Download History Episode 数与 Download Count 更新数差异。
- `REVOKED/REFUNDED` 下载尝试审计。
- Package Owner 校验失败次数。
- UI、Manifest、API 三种下载方式的成功率和构建耗时。
- Migration 前后历史、Package、My Data 数量对账结果。

## 15. 发布准入条件

满足以下条件后再发布：

1. 下载历史和 Package 清理方案已获得批准，并完成备份与恢复演练。
2. 已明确历史下载是否 Backfill 到 My Data。
3. `REVOKED/REFUNDED` 的授权、额度和计数规则已经实现并测试。
4. API Session 幂等指纹已包含 Package 身份，或产品接受当前风险。
5. PENDING/FAILED 下载具备恢复与清理机制。
6. <span style="color:#2563eb">前端、Hex 和 Pipeline 使用一致的新 API 契约及额度口径；已明确本次发布实际使用 `app-prismax-rp` 还是 `prismax-marketing-rp`（或两者都需验收），并完成对应前端回归（SYS-10、FE2-01~FE2-10）。</span>
7. UI、Manifest、API Package 三种路径的 P0 用例全部通过。
8. 并发额度测试确认不会超卖。
9. 历史、实际交付和 Download Count 对账无差异。
10. Admin/Unlimited Plan 不会因配置缺失被误拒绝。
11. <span style="color:#2563eb">若 `prismax-marketing-rp` 随本次发布上线：My Data Tab 已可用（非 Coming soon），部署含 `4cb1f0a` 及后续；FE2-01/FE2-08~FE2-10（含 Membership inactive 只读）已通过；Package 409 冲突分支已清理（DD-R14 残余仅剩 E2E 确认）。</span>
12. <span style="color:#2563eb">`470ab3d` 鉴权分层已与产品确认：只读入口是否允许无 Membership；`app-prismax-rp` 角色白名单是否移除（DD-R16/DD-R18）；AUTH-01~AUTH-05 与更新后的 SYS-03 已通过。</span>
13. <span style="color:#2563eb">Membership 过期后 API Key / Session 行为与错误文案已验收（DD-R19）；`ca1e000` 过滤参数回归（AUTH-05）已通过。</span>

## 16. <span style="color:#2563eb">新前端 `prismax-marketing-rp`（Robotic Data 页面）契约适配分析</span>

<span style="color:#2563eb">分析对象：独立仓库 `prismax-marketing-rp`（Next.js 16 + React 19）。用户于 2026-08-05 **重新拉取 testing** 后本地 tip 与 `origin/testing` 对齐为 `ccddf83`（含 `4cb1f0a updated for my data` → `104b8db` / `fce4458` / `ba7d229` / `ccddf83`）。以下结论**覆盖此前“Coming soon”判断**，以当前 testing 代码为准。</span>

### 16.1 <span style="color:#2563eb">仓库定位与后端指向</span>

- <span style="color:#2563eb">页面入口：`app/robotic-data/page.tsx` → `RoboticDataPageClient.tsx`，按 Tab/`?view=` 切换：</span>
  - <span style="color:#2563eb">**Browse Datasets** → `RoboticDataWorkspace.js`</span>
  - <span style="color:#2563eb">**My Data** → `MyDataWorkspace.js`（`4cb1f0a` 起新增；后续提交持续增强）</span>
- <span style="color:#2563eb">生产后端 Origin 经 Next rewrites 指向 `https://data.prismaxserver.com`，Beta 指向 `https://app-prismax-data-pipeline-beta-1053158761087.us-west1.run.app`（`next.config.ts`），与 Pipeline / Hex 同一后端。</span>
- <span style="color:#2563eb">**无** Admin Portal（无 `RoboticDataAdmin.js`）；面向登录用户的 Browse + My Data 工作台。</span>
- <span style="color:#2563eb">鉴权：`gatewayToken` / `userId` 由 `lib/prismaxAuth` 会话经 props 传入。Browse 目录/预览仍可走 `?public=1`；写操作与 My Data 需 `Authorization: Bearer`。</span>

### 16.2 <span style="color:#2563eb">已正确适配新契约的部分（testing 现状）</span>

| 能力 | 代码落点 | 说明 |
| --- | --- | --- |
| <span style="color:#2563eb">My Data Tab 可用</span> | <span style="color:#2563eb">`RoboticDataPageClient.tsx`：`openSection('myData')` + `?view=my-data`</span> | <span style="color:#2563eb">不再 disabled / Coming soon</span> |
| <span style="color:#2563eb">My Data 只读 API</span> | <span style="color:#2563eb">`GET /data/my-data/summary`、`GET /data/my-data/episodes`</span> | <span style="color:#2563eb">与后端 `_require_authenticated_user` 对齐</span> |
| <span style="color:#2563eb">加入 My Data</span> | <span style="color:#2563eb">Browse `handleAddToMyData` → `POST /data/my-data` `{episode_ids}`</span> | <span style="color:#2563eb">成功后 toast `added` / `already_owned`；刷新额度</span> |
| <span style="color:#2563eb">My Data 内下载</span> | <span style="color:#2563eb">`POST /data/downloads/ui` + `selected_episode_ids` + `idempotency_key`（`my-data-browser-…`）</span> | <span style="color:#2563eb">前端限 ≤10；inactive membership 先拦截</span> |
| <span style="color:#2563eb">Browse UI / Manifest</span> | <span style="color:#2563eb">同上三入口字段 + `idempotency_key`（`browser-…` / `manifest-…`）</span> | <span style="color:#2563eb">额度成功后 `refreshDownloadQuota`</span> |
| <span style="color:#2563eb">API Package 创建</span> | <span style="color:#2563eb">`postCreateApiPackage` 仅 `name` + `selected_episode_ids`</span> | <span style="color:#2563eb">**已无** 409 / `allow_already_packaged`</span> |
| <span style="color:#2563eb">额度字段</span> | <span style="color:#2563eb">`downloadQuota.js` + Browse/My Data 侧栏</span> | <span style="color:#2563eb">`used_episodes` / `monthly_episode_limit` / `remaining_episodes` 等</span> |
| <span style="color:#2563eb">Membership inactive UX</span> | <span style="color:#2563eb">`membership/current` 403 → `membershipStatus='inactive'`</span> | <span style="color:#2563eb">My Data 只读文案；Download 按钮禁用（对齐 DD-R18）</span> |
| <span style="color:#2563eb">下载历史</span> | <span style="color:#2563eb">`formatDownloadMode(entry.mode)` + episode_count / total_bytes</span> | <span style="color:#2563eb">不再读 `selected_upload_ids`（DD-R15 降级）</span> |
| <span style="color:#2563eb">My Data 预览</span> | <span style="color:#2563eb">`GET .../preview-videos`（**无** `public=1`，带 Authorization）</span> | <span style="color:#2563eb">与 Browse 公开预览分流</span> |

### 16.3 <span style="color:#2563eb">仍存风险 / 待验收（对应 DD-R14~DD-R19）</span>

1. <span style="color:#2563eb">**DD-R14（部分关闭）**：代码层面 My Data + 409 清理已到位；发布阻断改为 **E2E**（FE2-01、FE2-08~FE2-10）及确认 Beta 部署含 `4cb1f0a+`，而非“产品接受 Coming soon”。</span>
2. <span style="color:#2563eb">**DD-R15（降级）**：历史标题为下载方式（Browser/Manifest/API），无真实 Task 名——需产品是否接受。</span>
3. <span style="color:#2563eb">**DD-R16**：marketing 与后端 Membership 模型一致；风险仍在 `app-prismax-rp` 若按角色白名单误拦（FE2-04）。</span>
4. <span style="color:#2563eb">**DD-R17**：Browse 目录/预览仍 `?public=1` 匿名——公开范围需产品确认。</span>
5. <span style="color:#2563eb">**幂等**：Browse UI/Manifest 与 My Data 下载已带 `idempotency_key`；**API Package 创建仍无**——记差异（FE2-05），非默认阻断。</span>
6. <span style="color:#2563eb">**Hex**：`HexChat.js` 仍可能用固定 `FILES_PER_EPISODE` 估算 Manifest 上限（与 My Data 契约弱相关，建议研发同步）。</span>

### 16.4 <span style="color:#2563eb">结论</span>

<span style="color:#2563eb">相对上一版分析（Coming soon / 无 MyDataWorkspace），testing **已闭环主要前端缺口**：My Data 读写、Add to My Data、Membership 只读降级、下载幂等键、Package 409 清理。当前 QA 重心从“缺页面”转为 **P0 E2E（FE2-01/08/09/10）+ 匿名公开范围（DD-R17）+ 历史 Task 名体验（DD-R15）**。SYS-10 仍须明确本次发布验收 `prismax-marketing-rp` 和/或 `app-prismax-rp`，并核对部署 tip ≥ `4cb1f0a`（建议 ≥ `ccddf83`）。</span>

## 17. <span style="color:#2563eb">后续后端 Commit Range（`470ab3d` → HEAD）分析</span>

<span style="color:#2563eb">分析仓库：`app-prismax-rp-backend`  </span>
<span style="color:#2563eb">范围：`470ab3dd6073cb60093b5084cbeaf2c2d6d2821f`（含）→ `b49ade4598e2a5b75e9ea0986841b6def8454ef7`（分析时 HEAD）</span>

| Commit | 日期 | Message | 与本文档相关性 |
| --- | --- | --- | --- |
| <span style="color:#2563eb">`470ab3d`</span> | <span style="color:#2563eb">2026-08-04</span> | <span style="color:#2563eb">`updated for robotic-data`</span> | <span style="color:#2563eb">**高**：鉴权从角色改为 Active Membership；新增 `test_data_membership_downloads.py`</span> |
| <span style="color:#2563eb">`ca1e000`</span> | <span style="color:#2563eb">2026-08-04</span> | <span style="color:#2563eb">`fix My Data episode filter parameter types`</span> | <span style="color:#2563eb">**高**：修复 `GET /data/my-data/episodes` 可选过滤参数 Postgres 类型推断</span> |
| <span style="color:#2563eb">`b49ade4`</span> | <span style="color:#2563eb">2026-08-04</span> | <span style="color:#2563eb">`updated for forum`</span> | <span style="color:#2563eb">**无关**：仅改 `app_prismax_forum` 鉴权清理，不纳入 Data Download 回归</span> |

### 17.1 <span style="color:#2563eb">`470ab3d`：鉴权模型改版</span>

<span style="color:#2563eb">**核心变化**</span>

1. <span style="color:#2563eb">删除常量 `ROBOTIC_DATA_ALLOWED_USER_ROLES = ("operator", "admin")`。</span>
2. <span style="color:#2563eb">新增 `_require_authenticated_user()`：校验 Token，不校验角色/会员。</span>
3. <span style="color:#2563eb">新增 `_require_active_data_membership()`：在登录基础上调用 `_get_active_data_membership_plan()`（原 `_get_data_api_download_membership_plan` 重命名），要求 `users.user_data_download_membership` 非空且对应 Plan `status='ACTIVE'`。</span>
4. <span style="color:#2563eb">`_require_robotic_data_user()` 变为别名，内部直接调用 `_require_active_data_membership()`。</span>
5. <span style="color:#2563eb">`_require_operator_download_request` 重命名为 `_require_data_member_download_request`：以 Token 的 `userid` 为下载归属用户；若 body 带 `user_id` 则必须与 Token 一致，否则 403。不再按 `user_role==admin` 做特殊分支。</span>
6. <span style="color:#2563eb">`_require_data_api_key` 在 Key 校验通过后额外检查该 Key 所属用户的 Active Membership；失败 403，且**不会**更新 `last_used_at`。</span>

<span style="color:#2563eb">**接口鉴权分层（非 Admin Portal 路径）**</span>

| 入口 | 鉴权助手 | 含义 |
| --- | --- | --- |
| <span style="color:#2563eb">`GET /data/downloadable-uploads?public=1`、公开预览</span> | <span style="color:#2563eb">无</span> | <span style="color:#2563eb">匿名可浏览</span> |
| <span style="color:#2563eb">`GET .../previews`、`.../preview-videos`（非 admin）</span> | <span style="color:#2563eb">`_require_authenticated_user`</span> | <span style="color:#2563eb">登录即可</span> |
| <span style="color:#2563eb">`GET /data/my-data/summary`、`GET /data/my-data/episodes`</span> | <span style="color:#2563eb">`_require_authenticated_user`</span> | <span style="color:#2563eb">登录即可读自己的库</span> |
| <span style="color:#2563eb">`GET /data/api-keys`、`DELETE /data/api-keys/<id>`</span> | <span style="color:#2563eb">`_require_authenticated_user`</span> | <span style="color:#2563eb">登录即可列/吊销自己的 Key</span> |
| <span style="color:#2563eb">`POST /data/my-data`、`/check`、创建 Package、创建 Key、membership/current、downloads/limits、UI/Manifest 下载、下载脚本/历史</span> | <span style="color:#2563eb">`_require_active_data_membership`</span> | <span style="color:#2563eb">必须 Active Plan</span> |
| <span style="color:#2563eb">`POST /v1/data/download-sessions`（`X-API-Key`）</span> | <span style="color:#2563eb">`_require_data_api_key` + membership</span> | <span style="color:#2563eb">Key 有效且用户 Plan ACTIVE</span> |
| <span style="color:#2563eb">`GET /data/downloadable-uploads`（无 `public=1`）</span> | <span style="color:#2563eb">`_require_robotic_data_user` → membership</span> | <span style="color:#2563eb">非公开目录仍要会员</span> |

<span style="color:#2563eb">**测试资产**</span>

<span style="color:#2563eb">新增 `app_prismax_data_pipeline/test_data_membership_downloads.py`，覆盖：</span>

- <span style="color:#2563eb">任意角色 + Active Membership 可访问</span>
- <span style="color:#2563eb">缺 Membership → 403</span>
- <span style="color:#2563eb">下载请求 `user_id` 匹配/不匹配</span>
- <span style="color:#2563eb">过期 Membership 不能用已有 API Key，且不碰 `last_used_at`</span>
- <span style="color:#2563eb">UI / Manifest / API Session 路径会 `_ensure_user_library_episodes` 并在 ready 后 `_increment_user_library_download_counts`</span>
- <span style="color:#2563eb">可选：`PRISMAX_TEST_DATABASE_URL` 下并发额度不超卖集成测</span>

<span style="color:#2563eb">**对既有结论的影响**</span>

- <span style="color:#2563eb">旧文档/用例里“无 Plan 则全部入口 403”的假设过时 → 已改写 SYS-03，并新增 DD-R18。</span>
- <span style="color:#2563eb">“前端缺角色校验是缺陷”的假设过时 → DD-R16 / FE2-04 / 第 16.3 节已改写为关注旧前端误拦。</span>
- <span style="color:#2563eb">Admin Portal（`_is_admin_request`）路径未改，仍走 `_require_admin_jwt`，月度额度仍可不 enforce。</span>

### 17.2 <span style="color:#2563eb">`ca1e000`：My Data episodes 过滤参数类型</span>

<span style="color:#2563eb">`list_my_data_episodes` SQL 将：</span>

- <span style="color:#2563eb">`(:task_id IS NULL OR e.task_id = :task_id)` → `(CAST(:task_id AS BIGINT) IS NULL OR ...)`</span>
- <span style="color:#2563eb">`(:search_pattern IS NULL OR ...)` → `(CAST(:search_pattern AS TEXT) IS NULL OR ...)`</span>

<span style="color:#2563eb">原因：PostgreSQL 在可选参数为 NULL 时无法可靠推断类型，导致带 `task_id` 或空 `search` 时可能 500。单测 `MyDataEpisodeQueryTest.test_optional_filters_have_explicit_postgres_types` 锁定该 SQL 形态。对应用例 AUTH-05。</span>

### 17.3 <span style="color:#2563eb">`b49ade4`：Forum（范围外）</span>

<span style="color:#2563eb">仅改动 `app_prismax_forum`（删除 demo/base auth、精简 deps、新增 token 辅助与 `test_auth.py`）。与 Data Download / My Data / Package / Quota **无交叉**，本分析不要求纳入第 12 节回归，也不增加风险项。</span>

### 17.4 <span style="color:#2563eb">建议的额外发布检查</span>

1. <span style="color:#2563eb">跑通 `test_data_membership_downloads.py`（含可选 DB 并发测）。</span>
2. <span style="color:#2563eb">执行 AUTH-01~AUTH-05 与更新后的 SYS-03。</span>
3. <span style="color:#2563eb">确认产品是否接受“只读 My Data / 列 Key 不要求 Membership”（DD-R18）；若否，发布前改代码。</span>
4. <span style="color:#2563eb">确认 `app-prismax-rp` 是否仍按角色白名单拦截（DD-R16）；若仍拦截，与 `prismax-marketing-rp` 行为不一致，需在发布说明中写清。</span>
5. <span style="color:#2563eb">回归 Membership 过期后 API Key / Session 错误文案是否可被客户端理解（DD-R19）。</span>

---

发布方式建议：将 Data Download / My Data 作为重大版本和独立数据迁移发布，不要与无关功能共用一个不可回滚的发布窗口。
