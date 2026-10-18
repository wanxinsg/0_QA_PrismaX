# Hex 多视频下载估算与 Capability Request 联系方式 - 改动逻辑及测试用例

## 一、文档目的

本文用于验证后端 commit `8e945e18fa89650f2adf940573de07ab801c6e4c` 的两个功能模块：

1. Hex 下载估算从固定每个 episode 4 个文件，改为按实际 MCAP 和全部 MP4 数量统计。
2. Hex Capability Request 管理列表和 Excel 导出增加用户 Email、Telegram、Discord 联系方式。

---

## 二、分析范围

### 仓库与 Commit

- 仓库：`app-prismax-rp-backend`
- 分支：`testing`
- Commit：`8e945e18fa89650f2adf940573de07ab801c6e4c`
- Parent：`6ff2cad482cd802fc0953fd9c4cbab479b7e6310`
- 作者：`cw <xywchloe@gmail.com>`
- 日期：2026-07-13
- Commit Message：`Align Hex download estimates with additional videos and expose user contacts.`

### 涉及文件

| 文件 | 改动模块 |
|---|---|
| `app_prismax_hex/README.md` | 更新 Manifest 文件数规则说明 |
| `app_prismax_hex/hex/agent.py` | 更新 Hex system prompt，禁止固定假设每个 episode 4 个文件 |
| `app_prismax_hex/hex/download_limits.py` | 新增按 episode 估算实际文件数逻辑 |
| `app_prismax_hex/hex/episode_metadata.py` | 明确视频大小包含 primary 和 additional MP4 |
| `app_prismax_hex/hex/tools.py` | 查询实际 `video_count` 并用于下载方式判断 |
| `app_prismax_user_management/app.py` | Capability Request API/Excel 增加用户联系方式 |

---

## 三、改动主线

旧版本将一个 episode 固定估算为 `1 MCAP + 3 primary MP4 = 4 files`。当 episode 包含 additional videos 时，会低估 Manifest 文件数，可能错误地允许超过 800 文件上限的下载。

新版本从 `data_api_episode_file_metadata` 获取每个 episode 的真实视频数量，将 primary 和 additional MP4 全部纳入估算；同时管理员处理 Hex Capability Request 时，可以在列表 API 和 Excel 中看到用户提供的 Email、Telegram 或 Discord 联系方式。

---

## 四、Hex 下载估算逻辑

### 4.1 平台限制不变

| 下载方式 | 限制 |
|---|---|
| Browser Download | 最多 10 个 eligible episodes |
| Manifest JSON | 最多 800 个 asset files，实际值可由环境变量覆盖 |
| API Package | 受会员方案 `monthly_episode_limit` 限制 |

本次没有改变上述限额，只改变 Manifest 的文件数计算方式和提示文案。

### 4.2 实际 Video Count 来源

Hex 查询 downloadable episodes 时增加 lateral join：

```sql
SELECT COUNT(*) FILTER (WHERE fm.file_kind = 'video') AS video_count
FROM data_api_episode_file_metadata fm
WHERE fm.episode_id = e.episode_id
```

`video_count` 包含：

- env/high primary video
- left primary video
- right primary video
- 所有 additional MP4

### 4.3 单 Episode 文件数计算

计算函数：`estimate_episode_file_count(row)`

规则：

1. `raw_mcap_path` 非空时，MCAP 文件数加 1。
2. `video_count > 0` 时，加实际视频数量。
3. `video_count` 缺失、非法或为 0，但 `raw_video_folder_path` 存在时，fallback 为 3 个 primary videos。
4. 最终仍无法识别任何文件时，fallback 为 `HEX_ESTIMATED_FILES_PER_EPISODE`，默认 4。
5. row 不是 dict 时，也 fallback 为 4。

示例：

| MCAP | video_count | Video folder | 估算文件数 |
|---|---:|---|---:|
| 有 | 3 | 有 | 4 |
| 有 | 5 | 有 | 6 |
| 有 | 8 | 有 | 9 |
| 无 | 4 | 有 | 4 |
| 有 | 0/NULL | 有 | 4 |
| 无 | 0/NULL | 有 | 3 |
| 无 | 0/NULL | 无 | 4（全局 fallback） |

### 4.4 Selection 总文件数

```text
estimated_file_count = Σ estimate_episode_file_count(episode)
```

不再使用：

```text
eligible_episode_count × 4
```

### 4.5 Manifest Eligibility

```text
manifest allowed = eligible_episode_count > 0
                   AND estimated_file_count <= manifest_max_files
```

边界行为：

- 800 个文件：允许 Manifest。
- 801 个文件：不允许 Manifest。
- Browser 是否允许仍只根据 episode 数量判断，不受文件数影响。
- API Package 是否允许仍先根据 eligible episode 判断，再应用会员月度 quota。

### 4.6 Tool 返回字段

`prepare_download_estimate` 结果包括：

```json
{
  "eligible_episode_count": 2,
  "estimated_file_count": 11,
  "estimated_files_per_episode_avg": 5.5,
  "fallback_files_per_episode": 4,
  "estimated_files_per_episode": 5.5,
  "recommended_method": "browser"
}
```

字段说明：

- `estimated_files_per_episode_avg`：真实选择范围平均值，保留两位小数。
- `fallback_files_per_episode`：元数据缺失时使用的默认值。
- `estimated_files_per_episode`：兼容旧客户端，已标记 deprecated；有 episode 时返回平均值。
- `counting_basis`：解释 MCAP、primary/additional MP4 和 fallback 规则。

### 4.7 下载方式推荐顺序

在已登录且有 eligible episodes 时：

```text
Browser allowed → 推荐 browser
否则 Manifest allowed → 推荐 manifest_json
否则 → 推荐 api_package
```

未登录或没有 eligible episodes 时，`recommended_method = null`。

### 4.8 Size 文案

Hex metadata tool 的 `video_size_bytes` / `size` 被明确解释为：

```text
所有 MP4 的总大小，包括 primary 和 additional videos
```

该 commit 主要更新工具描述和 prompt，聚合数据本身仍依赖现有 episode metadata payload。

---

## 五、Capability Request 用户联系方式逻辑

### 5.1 管理接口

```http
GET /api/vla-admin/hex-capability-requests
GET /api/vla-admin/hex-capability-requests?status=all&page=1
GET /api/vla-admin/hex-capability-requests/export?status=pending
```

两个接口都使用 JWT，并沿用 VLA Admin 管理接口的权限流程。

#### “Admin GET”的准确含义

本文测试用例中原先使用的 “Admin GET” 是测试步骤简写，准确含义是：

> 使用有效的 VLA Admin JWT，通过 HTTP `GET` 方法直接请求 Hex Capability Request 管理列表接口，并检查 HTTP status code 和 JSON response body。

它不是浏览器中的普通页面访问，也不是创建或修改数据的 POST 请求。默认列表请求为：

```http
GET {PRISMAX_BACKEND_URL}/api/vla-admin/hex-capability-requests?status=pending&page=1
Authorization: Bearer {VLA_ADMIN_JWT}
Accept: application/json
```

参数说明：

| 参数 | 是否必填 | 默认值 | 说明 |
|---|---|---|---|
| `status` | 否 | `pending` | 可传 `pending`、`approved`、`rejected` 或 `all`；后端按传入字符串筛选 |
| `page` | 否 | `1` | 页码从 1 开始，小于 1 时后端按 1 处理 |

分页规则：

- 固定 `page_size=20`。
- `status=all` 返回所有状态，但仍分页。
- 不传 `status` 时只返回 `pending`。
- 列表按 `created_at DESC` 排序。

成功时预期：

```text
HTTP 200
Content-Type: application/json
```

响应必须包含：

```text
success
status
requests[]
pagination.page
pagination.page_size
pagination.total_count
pagination.total_pages
```

每个 `requests[]` item 除原有 request 字段外，本次需要重点验证：

```text
user_email
telegram_id
discord
```

#### curl 示例

默认查询 pending 第 1 页：

```bash
curl --request GET \
  "${PRISMAX_BACKEND_URL}/api/vla-admin/hex-capability-requests?status=pending&page=1" \
  --header "Authorization: Bearer ${VLA_ADMIN_JWT}" \
  --header "Accept: application/json"
```

查询全部状态第 2 页：

```bash
curl --request GET \
  "${PRISMAX_BACKEND_URL}/api/vla-admin/hex-capability-requests?status=all&page=2" \
  --header "Authorization: Bearer ${VLA_ADMIN_JWT}" \
  --header "Accept: application/json"
```

Excel Export 是另一个 GET endpoint，不属于本文后续所称的“管理列表 GET”：

```bash
curl --request GET \
  "${PRISMAX_BACKEND_URL}/api/vla-admin/hex-capability-requests/export?status=pending" \
  --header "Authorization: Bearer ${VLA_ADMIN_JWT}" \
  --output hex-capability-requests-pending.xlsx
```

### 5.2 Users 表关联

```sql
FROM hex_capability_requests h
LEFT JOIN users u ON u.userid = h.user_id
```

使用 LEFT JOIN，因此 capability request 没有匹配 user 时，请求记录仍应返回，只是联系方式为空。

### 5.3 Email 选择规则

```sql
COALESCE(
    NULLIF(TRIM(u.email), ''),
    NULLIF(TRIM(u.user_profile_email), '')
) AS user_email
```

优先级：

1. `users.email`
2. `users.user_profile_email`
3. 都为空时返回 `null`

字段会 `TRIM`，只有空格的值会被视为无效。

### 5.4 Telegram 规则

```sql
NULLIF(TRIM(u.telegram_id::text), '') AS telegram_id
```

- 数字/其他数据库类型统一转为字符串。
- 空字符串或只有空格时返回 `null`。

### 5.5 Discord 规则

查询内部字段：

- `discord_username`
- `discord_user_id`

最终管理 API 使用：

```text
discord = discord_username or discord_user_id or null
```

API 会移除内部的 `discord_username` 和 `discord_user_id`，只保留合并后的 `discord`。

### 5.6 管理 API 响应示例

```json
{
  "success": true,
  "status": "pending",
  "requests": [
    {
      "request_id": 100,
      "user_id": 200,
      "user_email": "qa@example.com",
      "telegram_id": "123456789",
      "discord": "qa-user",
      "status": "pending"
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total_count": 1,
    "total_pages": 1
  }
}
```

### 5.7 Excel Export

Excel `Capability Requests` sheet 新增三列：

```text
Email | Telegram | Discord
```

完整列顺序：

```text
Request ID, Created At, User ID, Email, Telegram, Discord,
Reason, User Message, Status, Session ID, Normalized Intent,
Admin Notes, Consent At
```

Export 不分页，会导出当前 status filter 下的全部请求。

---

## 六、风险分析

| 模块 | 风险等级 | 风险说明 |
|---|---|---|
| Manifest 文件数 | 高 | 估算决定下载方式是否可用，低估会超过平台 800 文件限制 |
| Metadata 完整性 | 高 | `video_count` 来自 `data_api_episode_file_metadata`，缺失时只能 fallback |
| Legacy Episode | 中 | 旧 episode 没有 metadata 时仍假设 3 个视频，可能与实际文件不一致 |
| Size 语义 | 中 | Tool 文案声明包含所有 MP4，需确认 metadata 聚合确实同步包含 additional videos |
| 查询性能 | 中 | 每个 selection 查询增加 lateral count，需关注大量 episode 时的 DB 性能 |
| 旧客户端兼容 | 中 | deprecated 字段从固定 4 变为实际平均值，旧客户端若假设整数可能受影响 |
| 联系方式隐私 | 高 | Admin API 和 Excel 新增 PII，必须严格控制 JWT/管理员权限和文件流转 |
| Contact Join | 中 | user ID 类型或历史孤儿记录不能导致 capability request 消失或接口 500 |
| Discord 合并字段 | 低 | username 优先于 ID，管理员无法同时在 API/Excel 看到两者 |

### 6.1 对其他 Hex 功能的影响范围

本次改动不只影响返回数字，还会改变 Hex Agent 对下载问题的工具选择、推荐方式和自然语言回答。影响链路如下：

```text
用户询问下载
→ Hex 调用 prepare_download_estimate
→ 读取 Workspace seed 或显式 episode IDs
→ 查询 downloadable catalog 和每个 episode 的 video_count
→ 应用 Browser / Manifest / API Package 限制
→ 应用会员 monthly quota
→ 重新计算 recommended_method
→ Agent 输出下载建议或进入 create_api_package
```

| Hex 功能 | 影响程度 | 是否回归 | 原因 |
|---|---|---|---|
| `prepare_download_estimate` | 直接、高 | 必须 | 文件数计算、Manifest eligibility 和返回字段发生变化 |
| 下载方式自然语言推荐 | 直接、高 | 必须 | System prompt 和 tool description 已修改 |
| `create_api_package` | 间接、高 | 必须 | Manifest 被拒绝后更可能推荐/触发 API Package |
| Membership monthly quota | 间接、高 | 必须 | quota 会再次重算 `recommended_method` |
| Workspace seed selection | 间接、中 | 必须 | 未显式传 IDs 时估算依赖当前 seed selection |
| Pipeline downloadable catalog | 间接、中 | 必须 | 不在 catalog 的 episode 会被排除，影响总文件数 |
| `summarize_episode_metadata` | 文案直接、数据间接 | 建议 | Tool 现在声明 size 包含所有 primary/additional MP4 |
| Episode duration/quality summary | 低 | 冒烟 | Tool 本身未改，但共享 Agent prompt/tool routing |
| Catalog search/recommendation | 低 | 冒烟 | 无代码直接改动，需确认 Agent 没有发生工具误选 |
| Capability Request 创建 | 低 | 冒烟 | 创建逻辑未改，但管理查询和导出需要继续消费旧记录 |
| Hex chat history | 低 | 冒烟 | API 未改，与 Capability Request 管理 UI 相邻 |
| 普通非下载对话 | 很低 | 简单冒烟 | 只需确认全局 Agent prompt 更新未造成明显回归 |

### 6.2 Download Metadata 依赖风险

新增 SQL 直接依赖：

```text
data_api_episode_file_metadata
data_api_episode_file_metadata.episode_id
data_api_episode_file_metadata.file_kind
```

需要区分两类 fallback：

1. 查询成功，但某个 episode 没有 metadata row：代码会根据 raw path fallback。
2. 表不存在、字段不存在、DB 权限不足或 lateral query 失败：整个 `prepare_download_estimate` 查询会失败，无法进入 fallback。

因此部署 smoke test 必须先验证 metadata 表结构和 Hex DB user 的 SELECT 权限。

实际文件与 metadata 还可能出现偏差：

- 同一个视频存在重复 metadata row，造成文件数高估。
- Additional video 未写入 metadata，造成文件数低估。
- Metadata row 存在但 GCS 文件已删除，造成文件数高估。
- `file_kind` 大小写或枚举值不是精确的 `video`，造成漏计。

### 6.3 下载推荐与 Monthly Quota 联动

`assess_download_methods` 先基于 episode/files 判断 Browser、Manifest、API Package；随后 `apply_monthly_quota_to_method_result` 可能将 API Package 改为不可用，并重新计算推荐方式。

必须验证以下组合：

| Browser | Manifest | API Package Quota | 最终推荐 |
|---|---|---|---|
| Allowed | Allowed | Allowed | `browser` |
| Denied | Allowed | Allowed | `manifest_json` |
| Denied | Denied | Allowed | `api_package` |
| Denied | Denied | Exceeded | `null`，不能继续推荐 API Package |
| Allowed | Allowed | Exceeded | `browser` |

### 6.4 Additional Video Size 语义风险

本 commit 只更新 `episode_metadata.py` docstring、tool description 和 Agent 文案，没有修改 `video_size_bytes` 的聚合实现。

因此不能只验证 Hex 回答文案，还必须核对上游 `video_size_bytes` 实际值是否已经包含：

- 三个 primary MP4
- 所有 additional MP4

如果上游仍只汇总 primary videos，Hex 会以确定语气给出错误的“所有 MP4 总大小”。

### 6.5 Capability Request 前端展示差异

后端 API 已返回：

```text
user_email
telegram_id
discord
```

Excel 也已新增 Email、Telegram、Discord 三列。但当前前端 `VLAAdminHexCapabilityRequests.js` 的表格仍只显示：

```text
ID | Created | User | Reason | User message | Status | Session | Chat
```

当前实际表现：

| 消费端 | 联系方式状态 |
|---|---|
| Admin API | 已返回 |
| Excel Export | 已展示 |
| Admin 页面列表 | 尚未渲染 |
| Chat Modal | 尚未渲染 |

验收前需要确认需求定义：

- 如果只要求 API/Excel expose contacts：当前实现符合范围。
- 如果要求管理员在页面直接看到联系方式：前端实现仍不完整，应记录缺陷或补充需求。

### 6.6 Admin 权限与 PII 风险

Capability Request 列表和 Export route 当前直接使用 `@jwt_required()`。Route 内部没有显式检查管理员角色或 Admin Wallet；需要确认是否由 JWT 签发流程、上游 gateway 或全局中间件保证只有管理员能获得/使用该 token。

必须用以下身份直接调用接口，而不能只通过 Admin UI 验证：

- 无 JWT
- 无效 JWT
- 过期 JWT
- 普通登录用户 JWT
- 有效 VLA Admin JWT

如果普通用户 JWT 可以访问，Email、Telegram、Discord、用户消息、Session ID 和 Admin Notes 都可能泄露，应判定为 P0 权限缺陷。

### 6.7 建议回归结论

需要回归，但不需要全量回归所有 Hex 功能：

- 必须回归：下载估算、下载方式推荐、API Package、monthly quota、Capability Request 列表/筛选/分页/Excel/权限。
- 建议冒烟：Workspace selection、catalog search、episode metadata summary、duration/quality summary、Capability Request 创建、Chat history。
- 无需深度回归：TeleOp、Upload、QA Review、支付等不调用本次 Hex/Capability Request 逻辑的模块。

---

## 七、测试前置条件

### Hex 下载数据

准备以下测试 fixtures。表中的 ID 是文档示例；执行时应替换成测试环境真实 episode ID，并在测试记录中保存映射。

| Fixture 变量 | 示例 ID | `data_episodes` 状态/路径 | 实际文件清单 | Metadata 预期 | 预期估算 |
|---|---:|---|---|---|---:|
| `EP_STD_3V` | `910001` | `DERIVED_READY`；MCAP path 和 video folder 均非空 | `episode.mcap`, `high.mp4`, `left.mp4`, `right.mp4` | 3 条 `file_kind='video'` | 4 |
| `EP_ADD_5V` | `910002` | `DERIVED_READY`；MCAP path 和 video folder 均非空 | `episode.mcap`, `high.mp4`, `left.mp4`, `right.mp4`, `wrist.mp4`, `overhead.mp4` | 5 条 `file_kind='video'` | 6 |
| `EP_ADD_8V` | `910003` | `DERIVED_READY`；MCAP path 和 video folder 均非空 | 1 个 MCAP、3 个 primary MP4、5 个 additional MP4 | 8 条 `file_kind='video'` | 9 |
| `EP_VIDEO_ONLY_4V` | `910004` | `DERIVED_READY`；`raw_mcap_path` 为空；video folder 非空 | 4 个 MP4，无 MCAP | 4 条 `file_kind='video'` | 4 |
| `EP_LEGACY_NO_META` | `910005` | `DERIVED_READY`；MCAP path 和 video folder 均非空 | 1 个 MCAP、3 个 primary MP4 | 无 metadata row | 4：1 MCAP + fallback 3 videos |
| `EP_EMPTY_FALLBACK` | `910006` | `DERIVED_READY`；MCAP/video folder 均为空 | 测试环境无可解析 raw path | 无 metadata row | 全局 fallback 4 |
| `EP_NOT_READY` | `910007` | `DERIVING` 或其他非 `DERIVED_READY` | 任意 | 任意 | 不计入 eligible，进入 skipped |
| `EP_NOT_IN_CATALOG` | `910008` | 可为 `DERIVED_READY`，但不在 `/data/downloadable-uploads` 返回结果 | 任意 | 任意 | 不计入 eligible，进入 catalog skipped |

以 `EP_ADD_5V` 为例，测试前应核对以下数据，而不是只使用无法对应实际数据的字母代号：

```text
episode_id = <EP_ADD_5V_ID>
status = DERIVED_READY
raw_mcap_path != NULL/empty
raw_video_folder_path != NULL/empty
data_api_episode_file_metadata 中 file_kind='video' 的行数 = 5
实际预期下载资产 = 1 MCAP + 5 MP4 = 6 files
```

建议用以下 SQL 核对测试数据；表/字段以测试环境 schema 为准：

```sql
SELECT e.episode_id,
       e.status,
       e.raw_mcap_path,
       e.raw_video_folder_path,
       COUNT(*) FILTER (WHERE fm.file_kind = 'video') AS video_count
FROM data_episodes e
LEFT JOIN data_api_episode_file_metadata fm
  ON fm.episode_id = e.episode_id
WHERE e.episode_id = :episode_id
GROUP BY e.episode_id, e.status, e.raw_mcap_path, e.raw_video_folder_path;
```

### 如何执行“下载估算”

本文后续的“执行下载估算”不是让 QA 手工计算，而是触发 Hex 的 `prepare_download_estimate` tool 并检查 tool result。

#### 方法一：Hex UI 黑盒测试

1. 使用测试用户登录 PrismaX App。
2. 在 Robotic Data Workspace/Hex workspace 中选中目标 episode。
3. 打开 Hex 对话。
4. 输入明确问题，例如：

```text
请估算当前选中 episodes 的下载文件数，并告诉我 Browser、Manifest JSON、API Package 哪些可用。请列出 eligible_episode_count、estimated_file_count 和 recommended_method。
```

5. 在 UI 回答和可用的 tool trace/network/debug log 中确认调用了 `prepare_download_estimate`。
6. 核对 tool result，而不只核对自然语言回答。

对于指定 ID，可使用：

```text
请估算 episode <EP_ADD_5V_ID> 的下载方式。这个问题只针对该 episode，请返回估算文件数和推荐方法。
```

#### 方法二：Tool 层精确验证

如果测试环境提供 Hex tool debug runner、后端测试入口或自动化 fixture，则直接给 `prepare_download_estimate` 传：

```json
{
  "episode_ids": [910002]
}
```

`910002` 仅为示例，必须替换成 `EP_ADD_5V` 的真实 ID。重点检查原始 tool result：

```json
{
  "requested_episode_count": 1,
  "eligible_episode_count": 1,
  "estimated_file_count": 6,
  "estimated_files_per_episode_avg": 6.0,
  "fallback_files_per_episode": 4,
  "recommended_method": "browser"
}
```

如果环境没有独立 Tool API，不要虚构 HTTP endpoint；通过 Hex UI 触发，并从服务日志/tool trace 采集结果。

### Capability Request 数据

准备以下用户及请求：

| Fixture 变量 | 示例 User ID | Email | Profile Email | Telegram | Discord Username | Discord ID | 用途 |
|---|---:|---|---|---|---|---|---|
| `USER_PRIMARY_CONTACTS` | `920001` | `primary@example.com` | `profile@example.com` | `123456789` | `qa-primary` | `998877` | 验证主 email 和 Discord username 优先 |
| `USER_FALLBACK_CONTACTS` | `920002` | NULL/空 | `fallback@example.com` | NULL | NULL | `discord-id-002` | 验证 profile email 和 Discord ID fallback |
| `USER_BLANK_CONTACTS` | `920003` | 三个空格 | 三个空格 | 三个空格 | 空 | 空 | 验证 trim 后返回 null |
| `REQUEST_ORPHAN_USER` | `929999`（users 表不存在） | - | - | - | - | - | 验证 LEFT JOIN 不过滤 request |

每个用户至少创建一条可识别的 pending capability request，并记录 `request_id`。不要只通过 user ID 猜测结果；API 验证时应先按 `request_id` 定位，再检查联系方式。

另需：

- VLA Admin JWT。
- 非管理员/无效/过期 JWT。
- `pending`、`approved`、`rejected` 等多种 status 请求。
- 能读取 `.xlsx` 的工具或 Excel/LibreOffice。

---

## 八、E2E 测试用例

### 8.1 Hex 下载估算

| Case ID | 标题 | 前置条件 | 测试步骤 | 预期结果 |
|---|---|---|---|---|
| HEX-DL-E2E-001 | 标准 1 MCAP + 3 MP4 | `EP_STD_3V` 已在 downloadable catalog；用户已登录 | 1. 用 SQL 核对该 ID 有 MCAP path、video folder 和 3 条 video metadata。<br>2. 登录 PrismaX App，进入 Robotic Data Workspace。<br>3. 清空已有 selection，只选中 `EP_STD_3V`。<br>4. 打开 Hex 对话框。<br>5. 输入：“请估算当前选中 episodes 的下载文件数，并告诉我 Browser、Manifest JSON、API Package 哪些可用。请列出 eligible_episode_count、estimated_file_count 和 recommended_method。”<br>6. 发送消息并等待回答完成。<br>7. 从 Hex tool trace、Network debug 信息或后端日志确认调用了 `prepare_download_estimate`。<br>8. 检查原始 tool result 和页面回答。 | `requested_episode_count=1`；`eligible_episode_count=1`；`estimated_file_count=4`；平均值 4.0；Browser/Manifest/API 在未受 quota 阻断时可用。 |
| HEX-DL-E2E-002 | Additional videos 纳入估算 | `EP_ADD_5V`：1 MCAP + `high/left/right/wrist/overhead.mp4`；5 条 video metadata | 1. 用 SQL 核对 `video_count=5`。<br>2. 登录 App 并进入 Robotic Data Workspace。<br>3. 清空 selection，只选中 `EP_ADD_5V`。<br>4. 打开 Hex。<br>5. 输入：“请估算当前所选 episode 的下载文件数和下载方式，并列出 estimated_file_count、estimated_files_per_episode_avg、counting_basis。”<br>6. 发送并等待回答。<br>7. 确认 Hex 调用 `prepare_download_estimate`。<br>8. 核对原始 tool result 和自然语言回答。 | `eligible_episode_count=1`；`estimated_file_count=6`；平均值 6.0；不是旧逻辑的 4；`counting_basis` 明确包含 primary 和 additional MP4。 |
| HEX-DL-E2E-003 | 5 个 Additional Videos | `EP_ADD_8V`：1 MCAP + 8 MP4；8 条 video metadata | 1. 登录 App，进入 Workspace并清空 selection。<br>2. 只选中 `EP_ADD_8V`。<br>3. 打开 Hex，输入：“请估算当前所选 episode 的下载资产数量，列出 MCAP/MP4 计数和 estimated_file_count。”<br>4. 发送并等待回答。<br>5. 确认调用 `prepare_download_estimate`。<br>6. 查看原始 tool result。 | `estimated_file_count=9`；Hex 回答为 1 MCAP + 8 MP4，不声称固定 4 files/episode。 |
| HEX-DL-E2E-004 | 多 Episode 累加与平均值 | `EP_STD_3V`、`EP_ADD_5V`、`EP_ADD_8V` 均 eligible | 1. 登录 App，进入 Workspace并清空已有 selection。<br>2. 只选中这 3 个 fixture IDs。<br>3. 打开 Hex，输入：“请估算当前 3 个 episodes 的总下载文件数和平均每 episode 文件数，并列出 requested、eligible、estimated_file_count。”<br>4. 发送并等待回答。<br>5. 确认调用 `prepare_download_estimate`。<br>6. 核对原始 tool result，确认没有混入其他 seed/recommendation。 | `requested=3`、`eligible=3`；总文件数 `4+6+9=19`；`estimated_files_per_episode_avg=6.33`；每个 ID 只计一次。 |
| HEX-DL-E2E-005 | 无 MCAP但有 4 个视频 | `EP_VIDEO_ONLY_4V` 的 `raw_mcap_path` 为空、video metadata=4 | 1. SQL 核对 MCAP path 为空且 `video_count=4`。<br>2. 登录 App，进入 Workspace，只选中该 ID。<br>3. 打开 Hex，输入：“请估算当前 episode 的下载文件数，并说明是否计算了 MCAP。”<br>4. 发送并确认调用 `prepare_download_estimate`。<br>5. 检查 tool result。 | `estimated_file_count=4`；只计算 4 个 MP4，不额外假设 MCAP。 |
| HEX-DL-E2E-006 | Legacy Metadata 缺失时使用 Primary Fallback | `EP_LEGACY_NO_META` 有 MCAP path/video folder，但没有 file metadata row | 1. SQL 确认 metadata count=0，MCAP/video folder path 非空。<br>2. 登录 App，进入 Workspace，只选择该 ID。<br>3. 打开 Hex，输入：“请估算当前 legacy episode 的下载文件数，并返回 fallback_files_per_episode 和 counting_basis。”<br>4. 发送并确认调用 `prepare_download_estimate`。<br>5. 检查 tool result。 | `estimated_file_count=4`：1 MCAP + fallback 3 videos；`fallback_files_per_episode=4`。 |
| HEX-DL-E2E-007 | Raw Path 与 Metadata 全部缺失 | `EP_EMPTY_FALLBACK` 的 MCAP/video folder 均为空且没有 metadata | 1. 用 SQL 核对 fixture。<br>2. 若该 ID仍在 downloadable catalog：登录 App、Workspace 只选该 ID、打开 Hex、输入标准下载估算 prompt、确认 `prepare_download_estimate` tool result。<br>3. 若 catalog 会先排除该 ID：在 Tool/函数集成测试中将对应 row 直接传给估算逻辑。 | 单 episode 使用全局 fallback 4；服务不因空 path 抛异常。若在 catalog 阶段被排除，应记录为 catalog skipped，并通过 Tool/函数测试验证 fallback。 |
| HEX-DL-E2E-008 | `video_count` 非法值 | Tool/函数级 fixture 的 row 包含 MCAP path、video folder，并分别设置 `video_count=null`、`""`、`"abc"` | 1. 对三组 row 分别调用 `estimate_episode_file_count`，或通过 mock query result 调用 `prepare_download_estimate`。<br>2. 记录异常和返回值。 | 三组均不抛 TypeError/ValueError；每组按 1 MCAP + fallback 3 videos 返回 4。 |
| HEX-DL-E2E-009 | Manifest 800 文件边界 | 准备 selection，使逐 episode 估算合计恰好 800；例如 100 个 fixtures，每个为 1 MCAP + 7 MP4=8 files | 1. 登录 App并进入 Workspace。<br>2. 清空 selection，只选择这 100 个 IDs。<br>3. 打开 Hex，输入标准下载估算 prompt。<br>4. 等待完成并确认调用 `prepare_download_estimate`。<br>5. 检查 `methods` 中 `manifest_json` item。 | `estimated_file_count=800`；Manifest `allowed=true`；reason 中 limit 为 800。 |
| HEX-DL-E2E-010 | Manifest 801 文件边界 | 准备 99 个 8-file episodes，加 1 个 9-file episode：`99×8+9=801` | 1. 登录 App进入 Workspace，清空 selection并只选这 100 个 IDs。<br>2. 打开 Hex，输入标准下载估算 prompt。<br>3. 确认调用 `prepare_download_estimate`。<br>4. 检查 Manifest method。 | `estimated_file_count=801`；Manifest `allowed=false`；reason 同时包含 801 estimated 和 800 limit。 |
| HEX-DL-E2E-011 | Browser 限制只按 Episode 数 | 准备 10 个 eligible episodes，每个估算 81 files，总计 810 | 1. 登录 App进入 Workspace，清空 selection并只选这 10 个 IDs。<br>2. 打开 Hex并输入标准下载估算 prompt。<br>3. 检查 Browser、Manifest 和推荐结果。 | Browser `allowed=true`（只看 10 episodes）；Manifest denied（810>800）；最终推荐 browser。 |
| HEX-DL-E2E-012 | 11 Episodes 且 Manifest 可用 | 11 个标准 fixtures，每个 4 files，总计 44 | 1. 登录 App进入 Workspace，只选这 11 个 IDs。<br>2. 打开 Hex并输入标准下载估算 prompt。<br>3. 检查 tool result。 | Browser denied（11>10）；Manifest allowed（44≤800）；推荐 `manifest_json`。 |
| HEX-DL-E2E-013 | Browser/Manifest 均不可用 | 101 个 fixtures，每个 8 files，总计 808；API monthly quota 可用 | 1. 登录 App进入 Workspace，只选这 101 个 IDs。<br>2. 打开 Hex并输入标准下载估算 prompt。<br>3. 检查 tool result 和 Agent回答。 | Browser denied；Manifest denied；API Package allowed；推荐 `api_package`。 |
| HEX-DL-E2E-014 | Anonymous 用户 | 退出登录；Workspace/Tool fixture 提供 `EP_STD_3V` | 1. 未登录状态触发相同估算。<br>2. 检查三种 methods。 | 三种方式均 `allowed=false`；reason 为 `Sign in required.`；`recommended_method=null`。 |
| HEX-DL-E2E-015 | 非 Ready Episode 被跳过 | `EP_NOT_READY` 的真实 ID；status 非 `DERIVED_READY` | 1. 通过 Tool debug runner显式传该 ID；如 UI 支持按 ID提问，则打开 Hex输入：“只估算 episode `<ID>`，并列出 skipped_episode_ids。”<br>2. 确认调用 `prepare_download_estimate`。<br>3. 检查原始结果。 | `requested=1`、`eligible=0`；无推荐方式；该 ID 出现在 `skipped_episode_ids`。 |
| HEX-DL-E2E-016 | 不在 Downloadable Catalog 的 Episode | `/data/downloadable-uploads` 不返回 `EP_NOT_IN_CATALOG` | 1. 先调用 catalog接口确认目标 ID缺失。<br>2. 通过 Tool runner显式传该 ID，或在 Hex输入：“只估算 episode `<ID>`，列出 catalog skipped IDs。”<br>3. 检查原始结果。 | 不纳入文件数；该 ID 出现在 `skipped_not_in_pipeline_catalog_episode_ids`，并返回 catalog note。 |
| HEX-DL-E2E-017 | 旧兼容字段 | `EP_STD_3V` 与 `EP_ADD_5V` 均可选择 | 1. 登录 App进入 Workspace，只选这两个 IDs。<br>2. 打开 Hex，输入标准下载估算 prompt。<br>3. 确认调用 `prepare_download_estimate`。<br>4. 检查完整 JSON 字段和值类型。 | 总文件数 10、平均值 5.0；同时返回新 average/fallback 字段和 deprecated `estimated_files_per_episode=5.0`。 |
| HEX-DL-E2E-018 | Size 包含 Additional MP4 | `EP_ADD_5V` 的 5 个 MP4 大小分别设为/记录为 10、20、30、40、50 MB | 1. 先核对上游 `video_size_bytes` 应为 150 MB。<br>2. Workspace 只选择该 ID。<br>3. 询问 Hex：“这个 episode 所有视频总大小是多少？”<br>4. 检查 `summarize_episode_metadata` 结果。 | 返回约 150 MB（允许单位换算误差），不是只统计 primary 的 60 MB；回答说明包含 additional videos。 |
| HEX-DL-E2E-019 | Hex 自然语言下载说明 | 选择包含 additional videos 的 episodes，询问“应该怎么下？” | 观察 tool call 与回答。 | Hex 调用 `prepare_download_estimate`；使用实际文件数推荐方式；不虚构固定 4 files/episode。 |
| HEX-DL-E2E-020 | 大 Selection 查询性能 | 准备接近实际最大规模的 episode selection | 连续执行估算并记录 DB/API 时间。 | 无超时；结果稳定；lateral metadata count 未造成不可接受退化。 |
| HEX-DL-E2E-021 | Metadata 表缺失 | 隔离环境隐藏/移除 `data_api_episode_file_metadata` | 调用 `prepare_download_estimate`。 | 部署 smoke test 应明确失败并阻止上线；不能误认为会使用 4-file fallback；日志能定位 metadata 表依赖。 |
| HEX-DL-E2E-022 | Metadata DB 权限不足 | 隔离环境撤销 Hex DB user 对 `data_api_episode_file_metadata` 的 SELECT；保留 `data_episodes` 权限 | 1. 使用已登录用户选择 `EP_STD_3V`。<br>2. 输入标准下载估算问题。<br>3. 检查 HTTP/Agent 错误和服务日志。 | 请求可控失败；日志能定位 permission denied；用户响应不包含 SQL、DB username/password；不得静默返回固定 4。 |
| HEX-DL-E2E-023 | 重复 Video Metadata | 为 `EP_ADD_5V` 的 `wrist.mp4` 人为插入第 2 条 `file_kind='video'` row，实际仍只有 5 MP4 | 1. SQL 确认 metadata count 从 5 变为 6。<br>2. 登录 App进入 Workspace，只选择该 ID。<br>3. 打开 Hex，输入：“请估算当前 episode 的下载文件数，并返回 estimated_file_count。”<br>4. 确认调用 `prepare_download_estimate` 并记录结果。<br>5. 与实际 manifest 的 6 assets 对比。 | 当前代码会估算 1+6=7，而实际为 1+5=6；测试应暴露高估问题并要求 metadata 唯一性约束/去重。 |
| HEX-DL-E2E-024 | Additional Video Metadata 未同步 | `EP_ADD_5V` 实际有 `wrist.mp4`、`overhead.mp4`，但删除这两条 metadata，使 count=3 | 1. SQL 确认 metadata count=3。<br>2. 登录 App进入 Workspace，只选择该 ID。<br>3. 打开 Hex并输入下载文件数估算问题。<br>4. 确认调用 `prepare_download_estimate`，记录结果并与实际 6 assets 对比。 | 当前估算为 1+3=4，实际为 6；测试应暴露低估问题。若 selection 因此错误通过 800 limit，判为高风险数据一致性缺陷。 |
| HEX-DL-E2E-025 | Metadata 有记录但文件已删除 | `EP_ADD_5V` 保留 5 条 metadata，但从测试 bucket 删除/隔离 `overhead.mp4` | 1. 登录 App进入 Workspace，只选择该 ID。<br>2. 打开 Hex并输入下载文件数估算问题。<br>3. 确认 tool result 为 6。<br>4. 从 Workspace 执行对应 Manifest/browser download。<br>5. 检查下载状态和错误信息。 | 估算仍为 6，但执行阶段应明确报告缺失文件；不得把不完整下载标记为完整成功。 |
| HEX-DL-E2E-026 | Monthly Quota 重算推荐方式 | 使用 101×8=808 files selection；Browser/Manifest denied；用户 `remaining_episodes < 101` | 1. 使用该 quota 用户登录 App。<br>2. Workspace 只选择这 101 个 IDs。<br>3. 打开 Hex并输入标准下载估算 prompt。<br>4. 确认调用 `prepare_download_estimate`。<br>5. 检查 `methods`、`monthly_quota`、`recommended_method` 和 Agent回答。 | API Package 被 monthly quota 改为 denied；`monthly_quota.quota_exceeded=true`；最终 `recommended_method=null`；Agent 不建议继续创建 package。 |
| HEX-DL-E2E-027 | Browser 可用但 API Quota Exceeded | 选择 `EP_STD_3V` 等不超过 10 个 eligible IDs；用户 API monthly quota 已用完 | 1. 使用 quota 已用完的用户登录 App。<br>2. Workspace 只选择不超过 10 个 eligible IDs。<br>3. 打开 Hex并输入标准下载估算 prompt。<br>4. 确认调用 tool并检查三种 methods。 | Browser 仍 allowed 且推荐 browser；Manifest可按文件数 allowed；只有 API Package 因 quota denied。 |
| HEX-DL-E2E-028 | Workspace Seed 默认选择 | Workspace 已选择包含 additional videos 的 episodes；不显式传 IDs | 询问下载方式。 | Tool 使用当前 seed selection；episode 数、文件数和推荐与显式传相同 IDs 一致。 |
| HEX-DL-E2E-029 | Create API Package Fast Path 回归 | Manifest 因文件数超限，API quota 可用 | 要求 Hex 创建 API package。 | 正确进入 create fast path；package episode 集合正确；返回 package ID，不受文件数返回字段变化影响。 |
| HEX-DL-E2E-030 | Duplicate API Package 回归 | 部分 episode 已在其他 package | 请求创建 API package。 | 保留 duplicate conflict/prompt 行为；不会因新的估算结果跳过重复确认。 |
| HEX-DL-E2E-031 | Duration/Quality Summary 工具路由 | 选择多个 episodes | 分别询问总时长、最低质量、最大文件。 | Duration/quality/size 使用 `summarize_episode_metadata`；下载问题才使用 `prepare_download_estimate`；无工具误选。 |
| HEX-DL-E2E-032 | Catalog Search 冒烟 | Hex catalog 有可搜索 task/robot | 询问并筛选 task、robot，再询问下载。 | Catalog 推荐结果正确；下载估算只使用最终选中的合法 catalog episodes。 |
| HEX-DL-E2E-033 | Capability Request 创建冒烟 | 提问 Hex 不支持的 catalog capability | 按原流程提交 capability request。 | Request 正常创建且 consent/reason/session 信息不受管理查询改动影响。 |

### 8.2 Capability Request 联系方式

| Case ID | 标题 | 前置条件 | 测试步骤 | 预期结果 |
|---|---|---|---|---|
| HEX-CONTACT-E2E-001 | 主 Email 优先 | `USER_PRIMARY_CONTACTS` 的 request ID 已记录；持有有效 VLA Admin JWT | 1. 请求 `GET /api/vla-admin/hex-capability-requests?status=pending&page=1`。<br>2. 确认 HTTP 200。<br>3. 按 request ID 找到该 item。 | `user_email="primary@example.com"`，不能返回 `profile@example.com`；`telegram_id="123456789"`；原有 request 字段完整。 |
| HEX-CONTACT-E2E-002 | Profile Email fallback | `USER_FALLBACK_CONTACTS` 主 email 空、profile email 为 `fallback@example.com` | 1. 使用 Admin JWT 请求管理列表 GET。<br>2. 按 request ID 定位 item。 | HTTP 200；`user_email="fallback@example.com"`。 |
| HEX-CONTACT-E2E-003 | Contact trim 与空值 | `USER_BLANK_CONTACTS` 的 contact 字段为纯空格 | 1. 请求管理列表 GET。<br>2. 按 request ID 定位 item。 | HTTP 200；`user_email`、`telegram_id`、`discord` 均为 JSON null，不返回 `"   "` 或空字符串。 |
| HEX-CONTACT-E2E-004 | Telegram 转字符串 | Telegram ID 为数字类型；持有有效 VLA Admin JWT | 请求管理列表 GET，并检查对应 request item。 | HTTP 200；`telegram_id` 为字符串且值完整。 |
| HEX-CONTACT-E2E-005 | Discord Username 优先 | `USER_PRIMARY_CONTACTS` 同时有 `qa-primary` 和 `998877` | 请求管理列表 GET，按 request ID 检查 item。 | HTTP 200；`discord="qa-primary"`，username 优先于 ID。 |
| HEX-CONTACT-E2E-006 | Discord ID fallback | `USER_FALLBACK_CONTACTS` 无 username、ID 为 `discord-id-002` | 请求管理列表 GET，按 request ID 检查 item。 | HTTP 200；`discord="discord-id-002"`。 |
| HEX-CONTACT-E2E-007 | API 不泄露内部 Discord 字段 | `USER_PRIMARY_CONTACTS` | 检查该 request item 的所有 keys。 | 返回合并字段 `discord`；不返回 `discord_username` 和 `discord_user_id`。 |
| HEX-CONTACT-E2E-008 | Orphan Request | Capability request user_id 无对应 users row；持有有效 VLA Admin JWT | 请求管理列表 GET，并通过 request ID 找到 orphan request。 | HTTP 200；请求记录仍存在；联系方式均为 null；LEFT JOIN 不应过滤该记录。 |
| HEX-CONTACT-E2E-009 | Pending 默认筛选 | 多 status 数据；持有有效 VLA Admin JWT | 请求 `GET /api/vla-admin/hex-capability-requests`，不传 status/page。 | HTTP 200；响应 `status=pending`；只返回 pending；`page=1`、`page_size=20`、total_count/total_pages 正确。 |
| HEX-CONTACT-E2E-010 | Status=all 分页 | 超过 20 条多状态数据 | 请求 `status=all&page=1/2`。 | 每页最多 20；按 created_at DESC；联系方式与正确用户匹配。 |
| HEX-CONTACT-E2E-011 | 指定状态筛选 | 有 approved/rejected 数据 | 分别请求对应 status。 | 只返回该状态；联系方式字段存在且分页统计正确。 |
| HEX-CONTACT-E2E-012 | Excel 新列与顺序 | 有完整联系方式数据 | 导出 pending Excel 并打开。 | Sheet 为 `Capability Requests`；Email、Telegram、Discord 位于 User ID 后；列顺序符合文档。 |
| HEX-CONTACT-E2E-013 | Excel fallback 一致性 | `USER_FALLBACK_CONTACTS` 的 request 可通过 API 和 Excel 查询 | 1. 记录 API 中的 `fallback@example.com` 和 `discord-id-002`。<br>2. 导出相同 status Excel。<br>3. 按 Request ID 找到同一行。 | Excel Email=`fallback@example.com`、Discord=`discord-id-002`，与 API 一致；Telegram 单元格为空。 |
| HEX-CONTACT-E2E-014 | Excel status filter | 多种 status 数据 | 导出 `status=approved`。 | 文件名含 approved 和 UTC 日期；只包含 approved 请求；不受分页限制。 |
| HEX-CONTACT-E2E-015 | Capability 表不存在 | 隔离环境移除/隐藏表 | 调用列表和 export。 | 列表返回成功空数组和 0 pagination；Excel 可下载且仅包含 header。 |
| HEX-CONTACT-E2E-016 | 未授权访问列表 | 无 token、无效/过期 token | 分别直接请求 `GET /api/vla-admin/hex-capability-requests?status=pending&page=1`，不通过 Admin UI。 | 返回 401/鉴权错误；响应不包含 `requests` 联系方式数据。 |
| HEX-CONTACT-E2E-017 | 未授权导出 | 无 token、无效/过期 token | 调用 export。 | 下载被拒绝；不返回含 PII 的 workbook。 |
| HEX-CONTACT-E2E-018 | 普通登录用户权限 | 非管理员有效 JWT | 调用列表与 export。 | 应按 VLA Admin 权限设计拒绝；若仅 `jwt_required` 即可访问，记录为高风险权限缺陷。 |
| HEX-CONTACT-E2E-019 | 特殊字符与公式注入 | 联系方式/用户消息以 `=`, `+`, `-`, `@` 开头 | 导出并打开 Excel。 | 单元格不应作为恶意公式执行；若被 Excel 当作公式，记录 CSV/XLSX injection 风险。 |
| HEX-CONTACT-E2E-020 | PII 日志检查 | 制造列表或 export DB 错误 | 检查服务日志。 | 日志不输出完整 Email、Telegram、Discord、JWT 或整个查询结果。 |
| HEX-CONTACT-E2E-021 | Admin 页面联系方式范围确认 | API 返回完整联系方式 | 打开 VLA Admin Capability Request 页面和 Chat Modal。 | 当前页面不显示联系方式；根据验收范围判定：若需求要求页面展示则记录功能缺失，若仅 API/Excel 则通过。 |
| HEX-CONTACT-E2E-022 | 普通用户 JWT 直接访问 PII | 获取普通登录用户有效 JWT | 不经过 Admin UI，直接调用列表和 export。 | 必须被拒绝；若返回 200 或下载 Excel，判为 P0 权限缺陷。 |
| HEX-CONTACT-E2E-023 | Admin Chat History 冒烟 | Capability request 有 session 和 chat logs | 从 Admin 页面打开 View chat。 | Chat history 正常加载；新增 contacts join 不影响 session ID、弹窗和日志接口。 |

---

## 九、建议优先级

### P0

- Additional videos 文件数准确性。
- Manifest 800/801 边界。
- Metadata 表结构、字段和 Hex DB user SELECT 权限。
- Manifest/API 都不可用时 `recommended_method` 必须为 null。
- Admin API/Excel 鉴权与 PII 防泄露。
- 普通用户有效 JWT 直接调用列表和 Export 必须被拒绝。
- Email/Discord fallback 和 LEFT JOIN orphan request。
- Excel 公式注入风险。

### P1

- Legacy metadata fallback。
- Browser/Manifest/API 推荐顺序。
- API Package monthly quota、fast path 和 duplicate conflict 联动。
- Workspace seed、pipeline catalog 和 skipped episode 行为。
- Status filter、分页和完整 Excel 导出。
- Size 是否真实包含 additional MP4。
- 大 selection 查询性能。

### P2

- Tool prompt/自然语言回答文案。
- Deprecated 字段兼容。
- 空表和异常日志表现。
- Catalog search、duration/quality summary、Capability Request 创建和 Chat history 冒烟。

---

## 十、验收记录

| 验收项 | 状态 | 证据/备注 |
|---|---|---|
| 标准 4-file episode | Not Started | |
| Additional videos 文件数 | Not Started | |
| Manifest 800/801 边界 | Not Started | |
| 下载方式推荐 | Not Started | |
| Legacy fallback | Not Started | |
| Metadata 表/权限 | Not Started | |
| Metadata 与实际文件一致性 | Not Started | |
| Additional video size | Not Started | |
| API Package quota/fast path | Not Started | |
| Workspace/Catalog 回归 | Not Started | |
| Admin API 联系方式 | Not Started | |
| Excel 联系方式 | Not Started | |
| Admin 页面联系方式范围 | Not Started | |
| Status/分页 | Not Started | |
| Admin 权限与 PII | Not Started | |
| 普通用户 JWT PII 访问 | Not Started | |
| Excel 公式注入 | Not Started | |
| Hex 其他核心功能冒烟 | Not Started | |
| 性能回归 | Not Started | |
