# PRIS-298：Robotics Data Portal — 业务逻辑 / 数据流 / API / 测试用例

> **联调基线**：Marketing `d9ccda2` + Backend `1ccf165`  
> **范围**：`prismax-marketing-rp` `/robotic-data`（Browse / My Data / History / Download / Package）+ `app-prismax-rp-backend` Data Pipeline

## 模块功能概述

PRIS-298 将 Robotics Data 相关功能从旧的 `app-prismax-rp` 迁移至独立的用户侧 Portal（`prismax-marketing-rp` `/robotic-data`），同步完成了数据模型的重构。

**核心功能包括四个部分：**

- **Browse Datasets**：浏览公开的机器人数据集目录，支持按 Task / Machine 筛选和 Episode 预览，用户可将感兴趣的 Episode 加入个人数据库（My Data）。
- **My Data**：用户的个人 Episode 数据库，展示已拥有 Episode 的列表、Task/Robot 分类统计和月度额度使用情况，支持从这里直接发起下载。
- **Download History**：记录每次下载的模式（Browser / Manifest / API）、涉及的 Episode 数量、文件大小和成功/失败状态。
- **API Package & Download Session**：用户可将 Episode 组合成可复用的 Package，再通过 API Key 创建 Download Session 批量获取数据，适用于自动化数据管道场景。

**本次重构的四个关键变化：**

1. 数据授权的最小单元从 Upload 改为 **Episode**，My Data 是 Browser / Manifest / API 三种下载方式共用的授权来源。
2. 月度额度只统计"本月首次加入 My Data 的新 Episode 数"，已拥有的 Episode 可以反复下载，不重复计费。
3. 浏览器下载改为 **直链（signed URL）**，文件直接从存储服务传到用户浏览器，不再经过 Next.js 服务器中转，避免大文件传输超时。
4. 权限由旧的 `operator/admin` 角色改为 **会员（Membership）分层**：普通用户只要有有效会员套餐即可使用全部功能。

---

## 1. 业务逻辑

### 1.1 各系统的角色


| 系统                               | 做什么                                                                  |
| -------------------------------- | -------------------------------------------------------------------- |
| `prismax-marketing-rp`（新 Portal） | 用户直接使用的网站，包含数据浏览、My Data 管理、下载和 Package 管理页面，是本次 PRIS-298 的主要交付端     |
| `app-prismax-rp`（旧 Portal）       | 本次不承载用户侧功能。注意它原先按角色（operator/admin）拦截请求，可能误拦有 Membership 的普通用户（R-09） |
| `app-prismax-rp-backend`（后端）     | 处理所有业务逻辑：校验权限、管理 Episode 所有权、计算额度、生成下载链接、记录历史                        |
| PostgreSQL（数据库）                  | 持久化存储：用户拥有哪些 Episode、下载记录、Package 内容、API Key 信息                      |
| GCS / CDN（文件存储）                  | 实际存放 MCAP、视频等数据文件，用户下载时直接从这里取文件                                      |


### 1.2 核心数据对象


| 对象                               | 通俗理解                                                               |
| -------------------------------- | ------------------------------------------------------------------ |
| My Data 条目（User Library Episode） | 记录"某用户拥有某个 Episode"，是 My Data 的最小单元。同一用户对同一 Episode 只会有一条          |
| 下载记录（Download）                   | 用户每次发起下载后的历史，记录下载了哪些 Episode、用哪种方式、是否成功                            |
| API Package                      | 用户自定义的 Episode 集合，类似"收藏夹"，供 API 批量下载使用。同一 Episode 可以被多个 Package 共用 |
| 会员套餐（Membership Plan）            | 决定用户能否执行写入和下载操作，以及每月最多可以新增多少个 Episode 到 My Data                    |
| API Key                          | 用于程序化调用下载接口的密钥。使用时仍需要绑定账号有有效的会员套餐                                  |


### 1.3 加入 My Data 时会发生什么

- Episode 有三种状态：`ACTIVE`（正常可用）、`ARCHIVED`（曾移除，重新加入时会恢复为 ACTIVE，不重复扣额度）。
- **P0 未决**：`REVOKED`（被撤销）和 `REFUNDED`（已退款）的 Episode 不会自动恢复，但当前代码没有统一规定这两种状态该怎么处理。Add、Browser 下载、Manifest 下载、Package 创建四个入口都需要遵循同一套产品规则，必须在上线前由产品确认。
- "加入 My Data"只是建立所有权关系，**不会**创建下载历史记录，**不会**更新下载次数。
- 创建 API Package 也是同理：只建立所有权和 Episode 映射，不写下载历史，不更新下载次数。

### 1.4 月度额度是怎么算的

```
本月已用 = 当前 UTC 自然月内首次加入 My Data 的 Episode 数
本次新增 = 本次请求中用户还未拥有的 Episode 数（去重后）
是否允许 = 套餐为无限量  OR  (本月已用 + 本次新增) <= 月度上限
超额时   → 整批请求失败（402），不允许只写入一部分
```

**以下情况不消耗额度**：重复加入已拥有的 Episode（包括恢复 ARCHIVED）；重复下载已拥有的 Episode；同一 Episode 在多个 Package 中复用。

**并发保护**：后端使用 PostgreSQL Advisory Transaction Lock，防止两个并发请求同时读到相同的剩余额度，导致超卖。

### 1.5 三种下载方式的区别


| 方式                | 接口                                | 自动加入 My Data       | 产生下载历史   | 更新下载次数           |
| ----------------- | --------------------------------- | ------------------ | -------- | ---------------- |
| 浏览器下载（Browser UI） | POST `/data/downloads/ui`         | ✅                  | ✅（构建成功后） | ✅（实际交付的 Episode） |
| Manifest 下载       | POST manifest endpoint            | ✅                  | ✅        | ✅                |
| API Session 下载    | POST `/v1/data/download-sessions` | ❌（创建 Package 时已建立） | ✅        | ✅                |
| 仅加入 My Data       | POST `/data/my-data`              | ✅                  | ❌        | ❌                |
| 仅创建 Package       | POST `/data/api-packages`         | ✅                  | ❌        | ❌                |


**三者必须保持一致**：实际交付的 Episode = 下载历史中的 Episode = 下载次数增加的 Episode

### 1.6 文件是如何传到用户浏览器的

- 后端生成每个文件的临时访问链接（signed URL），返回给前端。前端通过 `<a href=signedUrl download=download_name>` 触发浏览器直接下载，**不再**经过 `/api/download-file` 中转（旧版本 `37e8684` 仍走中转，`d9ccda2` 已改为直链）。
- 文件名优先使用响应中的 `download_name` 字段。MCAP 文件的格式为 `{episode_key}.mcap`，其他文件为 `{episode_key}_{原始文件名}`。
- CDN 和 raw GCS 的文件名行为目前不完全一致（P2 风险，记录差异即可，不影响上线判断）。
- 多个文件按顺序依次下载，每个文件最多重试 3 次。如果部分文件失败，页面需要明确列出哪些 Episode 的文件下载失败。

### 1.7 如何防止重复操作（防重放）

- 每次下载请求都需要在 Header 中携带 `Idempotency-Key`，后端以 `(用户ID, 下载模式, idempotency_key)` 作为唯一标识。
- 用同一个 key 重复发起完全相同的请求 → 返回第一次的结果，不重复扣额度、不重复写历史。
- 用同一个 key 但改变了 Episode 列表 → 返回 409 错误，不覆盖原始结果。
- **P0 风险**：API Session 的防重标识目前没有包含 `package_id`，如果两个 Package 里的 Episode 完全相同，可能会错误复用另一个 Package 的 Session 结果。

### 1.8 谁能做什么：权限与会员分层


| 操作                                | 需要什么资格                       |
| --------------------------------- | ---------------------------- |
| 浏览公开数据（Browse `?public=1`）、查看公开预览 | 无需登录                         |
| 查看自己的 My Data 列表和统计               | 登录即可（不要求有效会员）                |
| 查看和注销自己的 API Key                  | 登录即可                         |
| 加入 My Data、发起下载、创建 Package、查看下载历史 | 登录 + 有效会员（Active Membership） |
| 通过 API Key 创建 Download Session    | API Key 有效 + Key 所属账号有有效会员   |


旧版本按角色（operator/admin）控制权限的逻辑已从后端移除，普通用户只要有有效会员套餐就能正常使用。

### 1.9 My Data 的统计数字是怎么来的

- **总数（total_episodes）**：用户所有状态为 ACTIVE 的 Episode 数量，不受任何筛选条件影响。
- **筛选后总数（filtered_total_episodes）**：按当前选中的 Task 和 Robot 交叉筛选后的数量，没有选筛选条件时等于总数。
- 左侧 Task 分类的计数会受 Robot 筛选影响；Robot 分类的计数会受 Task 筛选影响。计数为 0 的选项仍然保留显示，不会消失。
- 列表中的"日期"列显示的是 `recorded_at`（即数据实际录制/上传的时间），**不是**该 Episode 被加入 My Data 的时间。
- 后端在处理 `task_id` 和 `search` 这两个参数时，必须做显式类型转换，否则传入空值时 PostgreSQL 会因无法推断类型而返回 500 错误。

### 1.10 必须始终成立的规则


| #      | 规则                                                             |
| ------ | -------------------------------------------------------------- |
| INV-01 | 同一用户对同一 Episode 只能有一条所有权记录，不允许重复                               |
| INV-02 | 月度额度只统计本 UTC 月内首次加入的 Episode，不统计下载次数                           |
| INV-03 | 重复下载已拥有的 Episode 不消耗月度额度                                       |
| INV-04 | "加入 My Data"和"创建 Package"这两个操作不写下载历史、不改变下载次数                   |
| INV-05 | 只有文件真正成功交付（状态 READY）才会增加下载次数                                   |
| INV-06 | 实际交付的 Episode 列表、下载历史里的 Episode 列表、下载次数增加的 Episode 列表，三者必须完全一致 |
| INV-07 | 无权限或非所有者的请求不得对任何数据表产生写入                                        |
| INV-08 | 携带相同 Idempotency-Key 的重复请求只产生一次实际效果                            |
| INV-09 | 超过月度额度的请求必须整批失败，不允许只写入部分                                       |


### 1.11 上线前必须解决的问题


| ID   | 级别  | 问题描述                                                  | 可能造成的影响                                       |
| ---- | --- | ----------------------------------------------------- | --------------------------------------------- |
| R-01 | P0  | 数据库迁移脚本会清空下载历史和 Package 相关三张表（TRUNCATE）               | 历史记录和 Package 数据将永久丢失，无法恢复                    |
| R-02 | P0  | REVOKED / REFUNDED 状态的 Episode 在四个入口的处理规则尚未由产品统一确认    | 可能导致额度被绕过，或用户无法正常下载                           |
| R-03 | P0  | API Session 的防重指纹未包含 `package_id`                     | 两个不同 Package 里的 Episode 完全相同时，Session 可能被错误复用 |
| R-04 | P0  | 并发场景下月度额度可能被超卖                                        | 用户实际加入的 Episode 数超过套餐上限                       |
| R-05 | P1  | 下载失败（FAILED）状态的 key 没有明确的重试机制                         | 用户可能永远无法完成这次下载，或重试时产生重复交付                     |
| R-06 | P1  | 下载卡在 PENDING 状态没有超时清理机制                               | 请求永远挂起，用户无法感知结果                               |
| R-07 | P1  | Package 里包含未就绪（non-READY）或不可见的 Episode 时，系统静默跳过而非明确告知 | 用户以为已经下载了所有 Episode，实际缺少部分文件                  |
| R-08 | P1  | Package 在创建 Session 时动态读取 Episode 的当前路径，而不是保存创建时的快照   | Episode 路径或状态变化后，同一 Package 的下载内容可能与之前不同      |
| R-09 | P1  | 旧 `app-prismax-rp` 仍可能按角色拦截请求                         | 有有效会员但角色不是 operator/admin 的用户会被误拦，无法下载        |


---

## 2. 数据流

### 2.1 把 Episode 加入 My Data

```
POST /data/my-data  {episode_ids: [...]}
  ↓ 校验登录状态和有效会员
  ↓ 标准化 ID、去重、校验上限（最多 200 个正整数）
  ↓ 查询哪些已拥有、哪些是新的
  ↓ 计算新 Episode 会占用的月度额度
  超额 → 整批返回 402，data 字段直接是额度对象（不再嵌套）
  正常 → 写入 ACTIVE 记录，ARCHIVED 的恢复为 ACTIVE（并发写入受 Advisory Lock 保护）
       → 返回 {added_episode_ids, already_owned_episode_ids, quota}

只影响 data_user_library_episodes 表；
下载记录、下载次数、最后下载时间均不改变。
```

### 2.2 浏览器下载（Browser / Manifest）

```
POST /data/downloads/ui  {selected_episode_ids, idempotency_key, user_id?}
  ↓ 校验 Idempotency-Key（同 key + 同内容 → 直接返回原结果，不重复写）
  ↓ 自动加入 My Data（同时检查额度）
  ↓ 构建下载任务，为每个文件生成临时访问链接（signed URL）
  ↓ 状态置为 READY
  ↓ 写入下载历史（以 Episode 为粒度）
  ↓ 成功交付的 Episode 下载次数 +1
  ↓ 返回 {signedUrls, download_names, download_id}

前端对每个链接创建 <a href=url download=文件名> 触发浏览器保存
多文件依次触发，每个文件最多重试 3 次；有失败时在页面明确列出哪些 Episode 失败

验收关键点：实际交付的 Episode = 历史记录的 Episode = 下载次数 +1 的 Episode
```

### 2.3 API 下载：创建 Package 再发起 Session

```
# 第一步 — 创建 Package（只需做一次）
POST /data/api-packages  {selected_episode_ids, name?}
  ↓ 校验登录和有效会员
  ↓ 自动加入 My Data（同时检查额度）
  ↓ 写入 Package 及其 Episode 映射
  ↓ 返回 package_id
  不写下载历史，不更新下载次数

# 第二步 — 发起 Download Session（每次下载调一次）
POST /v1/data/download-sessions  X-API-Key: {key}  {package_id}
  ↓ 确认 API Key 有效（ACTIVE）
  ↓ 确认 Key 所属账号有有效会员
  ↓ 确认 Package 的所有者和 Key 的所有者是同一个用户
  ↓ 读取 Package 内各 Episode 的当前路径、可见性、Ready 状态
  ↓ 构建 Session，保存本次实际解析到的文件列表（用于审计）
  ↓ 写入下载历史，更新下载次数
  ↓ 返回文件路径集合
```

### 2.4 My Data 页面的数据查询

```
GET /data/my-data/summary?task_id=&robot=
  → total_episodes            用户所有 ACTIVE Episode 的总数（不受筛选影响）
  → filtered_total_episodes   按 Task 和 Robot 交叉筛选后的数量
  → task_counts               各 Task 的数量（受当前 Robot 筛选影响）
  → robot_counts              各 Robot 的数量（受当前 Task 筛选影响）

GET /data/my-data/episodes?task_id=&robot=&search=&sort=created_at&page=
  → sort=created_at 实际按 recorded_at = COALESCE(uploaded_at, upload.created_at) 排序
  → 页面上的日期列显示 recorded_at，不是该 Episode 被加入 My Data 的时间
  注意：task_id 和 search 参数必须做显式类型转换，传空值否则会触发 PostgreSQL 500
```

### 2.5 下载历史的读取

```
GET /data/downloads/history
  → pagination.total_count      包含成功（READY）和失败（FAILED）的全部记录数
  → pagination.successful_count 只统计 READY 的成功次数
    （旧版后端没有这个字段时，前端显示 0，不要用 total_count 代替）

GET /data/downloads/{download_id}
  → selected_episode_ids  精确的实际交付 Episode 列表
```

---

## 3. API List


| Method       | Endpoint                                 | 需要的权限      | 主要参数                                                | 返回 / 行为                                    |
| ------------ | ---------------------------------------- | ---------- | --------------------------------------------------- | ------------------------------------------ |
| GET          | `/data/downloadable-uploads?public=1`    | 无需登录       | 目录筛选条件                                              | 公开可浏览的数据集                                  |
| GET          | `/data/membership/current`               | 有效会员       | —                                                   | 当前套餐信息和额度配置                                |
| GET          | `/data/downloads/limits`                 | 有效会员       | —                                                   | Browser / Manifest 的数量限制和当前额度              |
| POST         | `/data/my-data/check`                    | 有效会员       | `{episode_ids}`                                     | 告知哪些已拥有、哪些是新的、是否会超额（`would_exceed_quota`）  |
| POST         | `/data/my-data`                          | 有效会员       | `{episode_ids}`                                     | 建立所有权关系，不写下载历史                             |
| GET          | `/data/my-data/summary`                  | 已登录        | `task_id?`, `robot?`                                | 总数、筛选后总数、Task/Robot 分类计数                   |
| GET          | `/data/my-data/episodes`                 | 已登录        | page、page_size、task_id、robot、search、sort            | 分页 Episode 列表，含 `recorded_at`              |
| POST         | `/data/downloads/ui`                     | 有效会员       | `{selected_episode_ids, idempotency_key, user_id?}` | 自动建立所有权 + 发起浏览器下载                          |
| POST         | manifest endpoint                        | 有效会员       | `{selected_episode_ids, idempotency_key}`           | 自动建立所有权 + 发起 Manifest 下载                   |
| GET          | `/data/downloads/history`                | 有效会员       | page / filter                                       | 下载历史分页列表，含 `pagination.successful_count`   |
| GET          | `/data/downloads/{download_id}`          | 有效会员       | —                                                   | 精确的 `selected_episode_ids` 和下载详情           |
| POST         | `/data/api-packages`                     | 有效会员       | `{selected_episode_ids, name?}`                     | 创建 Package，同一 Episode 可跨 Package 共用，不写下载历史 |
| GET / DELETE | `/data/api-keys` / `/data/api-keys/{id}` | 已登录        | —                                                   | 查看或注销自己的 API Key                           |
| POST         | API Key 创建接口                             | 有效会员       | Key 配置                                              | 创建新的 API Key                               |
| POST         | `/v1/data/download-sessions`             | 有效 API Key | `{package_id}`                                      | 校验所有权和会员状态，构建 Session                      |


> Manifest 下载和 API Key 创建的具体路由，以测试环境的 OpenAPI 文档或路由代码为准。

### 需要特别注意的响应结构

`**POST /data/my-data/check` 的响应**

```json
{
  "data": {
    "owned_episode_ids": [101],
    "new_episode_ids": [102, 103],
    "owned_episode_count": 1,
    "new_episode_count": 2,
    "would_exceed_quota": false,
    "quota": {
      "used_episodes": 10, "new_episodes": 2, "projected_episodes": 12,
      "remaining_episodes": 88, "monthly_episode_limit": 100,
      "unlimited_episode_download": false, "billing_month": "UTC month"
    }
  }
}
```

注意：表示是否超额的布尔字段叫 `would_exceed_quota`，不是 `quota_exceeded`。

`**POST /data/my-data` 超额时的 402 响应**

注意：超额时 `data` 字段直接就是额度对象，**不是**再包一层 `quota`：

```json
{
  "success": false,
  "data": {
    "used_episodes": 98, "new_episodes": 3, "projected_episodes": 101,
    "remaining_episodes": 0, "monthly_episode_limit": 100
  }
}
```

**各 HTTP 状态码的含义**


| 状态码       | 什么情况会返回                              | 对数据的要求                          |
| --------- | ------------------------------------ | ------------------------------- |
| 200 / 201 | 操作成功                                 | 响应内容与数据库一致                      |
| 400       | 参数格式错误，或 ID 数量超过 200                 | 不写入任何业务数据                       |
| 401       | 未登录或 Token 无效                        | 不泄露任何用户数据                       |
| 402       | 本次操作会超过月度额度                          | 整批回滚，不允许只写入一部分                  |
| 403       | 无有效会员 / 所有者不匹配 / user_id 与 Token 不一致 | 不产生任何副作用（包括 `last_used_at` 不变）  |
| 409       | 同一 Idempotency-Key 对应了不同的请求内容        | 不覆盖原始请求的结果                      |
| 5xx       | 后端内部构建失败                             | 不增加下载次数，失败状态可恢复（PENDING/FAILED） |


---

## 4. 测试用例

> 结果填写：`☐` → `Pass` / `Fail` / `Blocked` / `N/A`  
> P0 Fail 阻断发布；产品规则尚未确认的 P0 项记为 Blocked，不能直接 Pass。

**测试账号和数据准备**


| 标识                 | 说明                                     |
| ------------------ | -------------------------------------- |
| 标准会员用户             | 普通用户，有有效会员，月度额度上限 100，本月已用 0           |
| 低余额会员用户            | 有有效会员，本月剩余额度仅 2                        |
| 无会员Operator用户      | 有 operator 角色，但无有效会员套餐                 |
| APIKey待过期会员用户      | 有一个有效的 API Key，后续让其会员套餐过期              |
| 无限额度用户             | 无限额度套餐 / Admin 用户                      |
| 全新Episode          | 全新 Episode，从未被任何用户加入过 My Data，状态 READY |
| 已拥有ACTIVE Episode  | 已在标准会员用户的 My Data 中，状态 ACTIVE          |
| 归档ARCHIVED Episode | 曾在标准会员用户的 My Data 中，当前状态 ARCHIVED      |
| 撤销REVOKED Episode  | 状态 REVOKED（被撤销）                        |
| 退款REFUNDED Episode | 状态 REFUNDED（已退款）                       |


另需准备：包含 READY/非 READY/不可见/文件缺失/大 MCAP/视频等混合情况的 Episode；两个 Episode 列表完全相同但 `package_id` 不同的 Package。

---

### 4.1 权限验证


| ID          | P   | 操作步骤                                                                           | 预期结果                                                                 | 结果  |
| ----------- | --- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------- | --- |
| E2E-AUTH-01 | P0  | 用 标准会员用户（无 operator/admin 角色）分别执行：加入 My Data、Browser 下载、Manifest 下载、创建 Package | 所有操作均成功，不因为角色问题返回 403                                                | ☐   |
| E2E-AUTH-02 | P0  | 用 无会员Operator用户（有 operator 角色但无有效会员）调用加入 My Data、下载、创建 Package、查看历史等所有写入和下载接口  | 全部返回 403，数据库不产生任何写入                                                  | ☐   |
| E2E-AUTH-03 | P0  | 用一个已登录但无有效会员的用户打开 My Data 页面，然后尝试点击下载                                          | 页面能正常加载 My Data 列表和统计（只读）；点击下载时返回 403                                | ☐   |
| E2E-AUTH-04 | P0  | 调用 Browser 下载接口，请求体中的 `user_id` 填写另一个用户的 ID                                    | 返回 403，提示 user_id 与 Token 不符；将 `user_id` 改成本人或省略后，请求正常成功             | ☐   |
| E2E-AUTH-05 | P0  | 用 APIKey待过期会员用户 的 API Key 创建 Download Session，期间会员套餐已过期                        | 返回 403，API Key 的 `last_used_at` 时间不变；为 APIKey待过期会员用户 恢复有效会员后重试，能正常成功 | ☐   |
| E2E-AUTH-06 | P0  | 用 标准会员用户 的 Token 猜测 低余额会员用户 的 download ID、package ID 或 API Key ID，尝试访问         | 返回 403 或 404，不泄露任何 Episode 路径、额度或用户数据，且不对数据库产生任何写入                   | ☐   |
| E2E-AUTH-07 | P1  | 不登录访问 Browse `?public=1` 和公开 preview，再尝试访问 My Data preview                     | 公开数据正常展示；访问 My Data preview 时返回 401                                  | ☐   |
| E2E-AUTH-08 | P1  | 分别用新 Portal（Marketing）和旧 Portal（`app-prismax-rp`）对同一账号执行相同操作，比较入口门槛            | 新 Portal 按会员状态判断；旧 Portal 若误拦普通会员，记录为 R-09 风险                        | ☐   |


### 4.2 所有权与月度额度


| ID         | P   | 操作步骤                                                                                             | 预期结果                                                                                                | 结果  |
| ---------- | --- | ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------- | --- |
| E2E-MYD-01 | P0  | 用 标准会员用户 将 全新Episode 加入 My Data                                                                  | 接口返回 added 列表包含该 Episode；数据库新增一条 ACTIVE 记录，下载次数为 0，最后下载时间为空；本月已用额度 +1；不产生下载历史                       | ☐   |
| E2E-MYD-02 | P0  | 对同一个 全新Episode 连续重复加入 3 次                                                                        | 每次返回 already_owned；数据库始终只有一条记录；创建时间、已用额度、下载次数均不改变                                                   | ☐   |
| E2E-MYD-03 | P0  | 先调用 check，再调用 post，传入 `[已拥有ACTIVE Episode, 全新Episode]`                                           | check 正确区分 owned 和 new；post 只对 全新Episode 消耗 1 个额度，已拥有ACTIVE Episode 不重复计费                           | ☐   |
| E2E-MYD-04 | P1  | 调用 post，传入同一个 归档ARCHIVED Episode 的 ID 重复三次                                                       | 后端自动去重；只写入一条 ACTIVE 记录；额度只消耗 1                                                                      | ☐   |
| E2E-MYD-05 | P0  | 用 低余额会员用户（剩余额度 2）依次加入两个全新 Episode，再加入第三个                                                         | 前两次成功，额度恰好用完；第三次返回 402                                                                              | ☐   |
| E2E-MYD-06 | P0  | 用 低余额会员用户 一次性 post 三个全新 Episode                                                                  | check 返回 `would_exceed_quota=true`；post 返回 402；数据库完全没有写入                                            | ☐   |
| E2E-MYD-07 | P1  | 模拟 UTC 月份切换：标准会员用户 在上个月拥有 已拥有ACTIVE Episode，本月再下载该 Episode、再加入另一个全新Episode                       | 新月已用额度从 0 开始；下载已拥有的 Episode 不消耗额度；加入另一个全新Episode 消耗 1，变为本月第 1                                       | ☐   |
| E2E-MYD-08 | P1  | 对 归档ARCHIVED Episode 分别通过加入 My Data 和发起下载来恢复                                                     | 两种方式都只恢复同一条记录的状态为 ACTIVE，不产生第二行；是否重新消耗额度须按产品确认的规则核验                                                 | ☐   |
| E2E-MYD-09 | P0  | 对 撤销REVOKED Episode 和 退款REFUNDED Episode，分别通过加入 My Data、Browser 下载、Manifest 下载、创建 Package 四个入口操作 | 四个入口必须执行完全相同的产品规则；如果规则尚未由产品确认，标记为 Blocked                                                           | ☐   |
| E2E-MYD-10 | P0  | 同时发出 10 个并发请求，都是将同一个全新 Episode 加入 My Data                                                        | 数据库最终只有一条记录；已用额度只 +1；不出现 500 错误、死锁或唯一键冲突                                                            | ☐   |
| E2E-MYD-11 | P0  | 用 低余额会员用户（剩余额度 2）同时并发加入 3 个不同的全新 Episode                                                         | 最多 2 个成功，至少 1 个返回 402；绝不允许 3 个都成功（超卖）                                                               | ☐   |
| E2E-MYD-12 | P1  | 一次传入 250 个 ID；另一次传入 150 个 ID 但剩余额度只有 100                                                         | 250 个返回 400（参数超限）；150 个返回 402（超额）；两次均不写入任何数据                                                        | ☐   |
| E2E-MYD-13 | P1  | 传入非法值（负数、字符串）、不存在的 ID、不可见的 ID，以及合法和非法混合的情况                                                       | 返回明确的 4xx 错误；不出现 500 或 SQL 错误信息泄露；不写入任何数据（包括合法部分）                                                   | ☐   |
| E2E-MYD-14 | P0  | 同一批请求中混合：已拥有ACTIVE Episode、撤销REVOKED Episode、退款REFUNDED Episode、全新Episode，一起 check 和 post        | 已拥有ACTIVE Episode 不受影响；全新Episode 消耗 1 个额度；撤销REVOKED Episode 和 退款REFUNDED Episode 按产品策略处理；各状态之间不互相污染 | ☐   |


### 4.3 My Data 页面展示


| ID        | P   | 操作步骤                                                              | 预期结果                                                        | 结果  |
| --------- | --- | ----------------------------------------------------------------- | ----------------------------------------------------------- | --- |
| E2E-UI-01 | P0  | 打开 `/robotic-data?view=my-data`                                   | 页面正常显示（不是 Coming Soon）；拥有数量、剩余额度、分类统计、Episode 列表均与 API 返回一致 | ☐   |
| E2E-UI-02 | P0  | 不选任何筛选条件，查看 My Data 总数                                            | 页面显示的总数等于 `total_episodes`，与 `filtered_total_episodes` 相同   | ☐   |
| E2E-UI-03 | P0  | 在左侧选择一个 Task，再选择一个 Robot                                          | Task 和 Robot 的数量实时交叉更新；计数为 0 的选项仍然保留；"All"显示筛选后总数           | ☐   |
| E2E-UI-04 | P0  | 传入非法的 task_id（如 `abc`），再传入合法的 task 和 robot 组合                     | 非法参数返回 400；合法参数返回 200；不出现 GROUP BY 导致的 500 错误               | ☐   |
| E2E-UI-05 | P0  | 分别测试：无筛选条件、只选 task、只输 search 关键词、task + search 组合                 | 所有合法请求返回 200；不出现因空参数导致的 PostgreSQL 500 错误                   | ☐   |
| E2E-UI-06 | P0  | 准备一个 Episode，使其加入 My Data 的时间和实际录制时间不同，查看排序和日期列                   | 日期列显示的是实际录制时间（`recorded_at`），不是加入 My Data 的时间               | ☐   |
| E2E-UI-07 | P1  | 用不同大小写的 Robot 名称（如 `Robot-A` 和 `robot-a`）进行搜索                     | 搜索不区分大小写，两种写法都能命中相同的结果                                      | ☐   |
| E2E-UI-08 | P1  | 分别使用左侧 Task 搜索框和表格上方的 search 框，再点击"Clear all"                     | 两个搜索框互不干扰；Clear all 同时清空所有筛选条件并重置到第一页                       | ☐   |
| E2E-UI-09 | P1  | 准备 37 条跨多个 Task 和 Robot 的 Episode，逐页翻完，并与 summary 和 check 接口的数据对账 | 翻页过程中无重复或遗漏；总数、分类计数、所有权分类与接口返回完全一致                          | ☐   |
| E2E-UI-10 | P1  | 分别在 390px / 768px / 1024px / 1280px 宽度下操作页面，并测试键盘导航               | 无重要内容被遮挡；筛选、按钮、下载等关键操作可通过键盘完成；各状态（加载中、空态、禁用）文案可辨识           | ☐   |


### 4.4 数据浏览与加入 My Data


| ID         | P   | 操作步骤                                                                     | 预期结果                                                                                                         | 结果  |
| ---------- | --- | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------ | --- |
| E2E-BRW-01 | P0  | 在 Browse 页面选择一个 Machine，观察 Task 数量变化；再选一个 Task，观察 Machine 数量变化；最后点 Clear | 选 Machine 后 Task 计数正确更新；选 Task 后 Machine 计数正确更新；Clear 后恢复所有选项                                                | ☐   |
| E2E-BRW-02 | P0  | 展开大量 Task 后缓慢向下滚动，通过 Network 面板观察 preview 请求的数量                          | 只有视窗附近（约上方 1 屏 + 下方 2 屏）和 Hex 推荐的 Episode 触发 preview 请求，不发起全量请求                                              | ☐   |
| E2E-BRW-03 | P0  | 快速上下滚动、缩放窗口、来回让同一 Episode 进出视窗                                           | 同一个 preview 请求不会重复发起；在一段时间内请求总数维持在合理范围                                                                       | ☐   |
| E2E-BRW-04 | P1  | 模拟浏览器不支持 IntersectionObserver 的环境（可通过 JS 覆盖）访问 Browse 页面                 | 回退为只加载前 12 条 preview，页面正常可用，不发起全量加载                                                                          | ☐   |
| E2E-BRW-05 | P0  | 在 Browse 页面选中一批 Episode（包含已拥有和全新的），点击加入 My Data                          | 只有全新 Episode 消耗额度；切换到 My Data 页面可以看到新加入的 Episode；下载次数为 0；不产生下载历史                                             | ☐   |
| E2E-BRW-06 | P1  | 在未登录状态下浏览数据，然后点击加入 My Data 或下载                                           | 浏览操作正常可用；点击写入操作时触发登录流程；不产生任何匿名写入                                                                             | ☐   |
| E2E-BRW-07 | P0  | 用 标准会员用户 在 Browse 页面播放一个尚未加入 My Data 的 Episode 预览                        | 视频在 30 秒时自动暂停，出现"You've reached the 30-second preview"遮罩；遮罩中显示的完整时长与该 Episode 的实际时长一致；显示"+ Add to My Data"按钮 | ☐   |
| E2E-BRW-08 | P0  | 在 30 秒预览遮罩上点击"+ Add to My Data"（已登录 标准会员用户，该 Episode 未在 My Data 中）       | Episode 成功加入 My Data；遮罩消失，视频从当前位置继续播放完整内容；My Data 页面可看到该 Episode，月度额度 +1；不产生下载历史，下载次数不变                      | ☐   |
| E2E-BRW-09 | P0  | 用已将该 Episode 加入 My Data 的 标准会员用户，再次打开同一 Episode 的预览播放                    | 视频直接播放完整内容，不在 30 秒处出现遮罩拦截；无多余的 Add to My Data 调用                                                             | ☐   |
| E2E-BRW-10 | P0  | 未登录状态下播放预览至 30 秒遮罩，点击"+ Add to My Data"                                  | 触发登录流程（跳转登录页或弹出登录弹窗）；登录完成后，该 Episode 自动加入 My Data，视频可继续播放；不产生任何匿名写入记录                                        | ☐   |
| E2E-BRW-11 | P1  | 用 无会员Operator用户 在 30 秒遮罩上点击"+ Add to My Data"                            | 返回权限不足错误提示（对应 403）；遮罩继续保持显示；数据库无写入；不产生额度变动                                                                   | ☐   |
| E2E-BRW-12 | P1  | 用 低余额会员用户（本月剩余额度已用完）在 30 秒遮罩上点击"+ Add to My Data"                        | 返回超额提示（对应 402）；遮罩继续保持显示；提示引导用户升级套餐；数据库无写入                                                                    | ☐   |


### 4.5 浏览器下载、下载历史与文件交付


| ID         | P   | 操作步骤                                                                          | 预期结果                                                                                             | 结果  |
| ---------- | --- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | --- |
| E2E-DL-01  | P0  | 用 标准会员用户 对 全新Episode 发起 Browser 下载（首次）                                        | 全新Episode 自动加入 My Data；本月已用额度 +1；下载历史新增一条 READY 记录；全新Episode 的下载次数变为 1                           | ☐   |
| E2E-DL-02  | P0  | 对已拥有的 全新Episode 连续再下载 3 次                                                     | 每次下载成功后各新增一条历史记录，下载次数各 +1；本月已用额度不再增加；最终该 Episode 下载次数为 4                                         | ☐   |
| E2E-DL-03  | P0  | 用 Manifest 下载 `[已拥有ACTIVE Episode, 全新Episode, 归档ARCHIVED Episode]` 三个 Episode | 额度只消耗 2（全新Episode 和 归档ARCHIVED Episode 是新的）；实际下载的文件列表、历史记录中的 Episode 列表、下载次数 +1 的 Episode 列表完全一致 | ☐   |
| E2E-DL-04  | P0  | 在 My Data 页面选择 10 个 Episode 下载，再尝试选超过 10 个                                    | 10 个以内正常触发下载；超过 10 个时前端拦截并提示；直接调接口绕过前端限制时，后端按接口约定处理                                              | ☐   |
| E2E-DL-05  | P0  | 用同一个 Idempotency-Key 连续发起两次（或并发）完全相同的下载请求                                     | 两次都返回同一个 download_id；额度、历史记录、下载次数只产生一次变化                                                         | ☐   |
| E2E-DL-06  | P0  | 用同一个 Idempotency-Key，但第二次修改了 Episode 列表                                       | 返回 409 冲突错误；新的 Episode 列表不被写入；第一次请求的结果不变                                                         | ☐   |
| E2E-DL-07  | P0  | 分别下载单个文件和多个文件，通过 Network 面板抓包检查请求路径                                           | 文件直接从 signed URL 下载；不出现对 `/api/download-file` 的请求                                                | ☐   |
| E2E-DL-08  | P0  | 下载一个较大的 MCAP 文件或视频文件                                                          | 文件正常下载完成，不出现因服务器中转导致的超时或内存溢出；下载完成后可以验证文件完整性                                                      | ☐   |
| E2E-DL-09  | P0  | 下载 raw GCS 路径的文件，检查本地保存的文件名                                                   | 文件名优先使用响应中的 `download_name`；MCAP 文件名格式为 `{episode_key}.mcap`；浏览器保存对话框中的文件名正确                     | ☐   |
| E2E-DL-10  | P1  | 下载走 CDN 路径的文件，记录实际文件名                                                         | 记录 CDN 和 raw GCS 之间的文件名差异，作为 R-08 的观测数据，不影响本次上线判断                                                | ☐   |
| E2E-DL-11  | P1  | 下载多个文件，其中一个文件持续触发错误（可模拟网络故障）                                                  | 该文件最多重试 3 次；已成功的文件继续正常下载；页面上以 warning 形式列出哪些 Episode 的文件下载失败                                     | ☐   |
| E2E-DL-12  | P0  | 在下载构建过程中模拟故障（如后端宕机、网络中断），然后检查数据库状态                                            | 失败的下载记录状态为 FAILED，不增加下载次数；PENDING 状态的记录在故障恢复后可以继续处理；相同请求重试不产生重复的历史记录                             | ☐   |
| E2E-HIS-01 | P0  | 制造一批下载历史，其中包含 READY 和 FAILED 两种状态，打开历史页面                                      | 页面显示的"成功次数"只统计 READY 记录（`successful_count`）；FAILED 记录仍然显示在列表中，但不计入成功数                            | ☐   |
| E2E-HIS-02 | P0  | 所有历史记录均为 FAILED 状态；或模拟旧版后端响应（不含 `successful_count` 字段）                        | 成功次数显示为 0；不用 `total_count` 来代替，避免把失败记录也算进成功数                                                     | ☐   |
| E2E-HIS-03 | P1  | 点击某条下载历史查看详情                                                                  | 详情中的 `selected_episode_ids` 与实际交付的 Episode 完全一致；页面不出现因依赖旧版 upload 字段而导致的报错                       | ☐   |


### 4.6 API 下载（Package / Key / Session）


| ID         | P   | 操作步骤                                                                                                             | 预期结果                                                                                                           | 结果  |
| ---------- | --- | ---------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | --- |
| E2E-PKG-01 | P0  | 先创建 Package A 包含 全新Episode 和 已拥有ACTIVE Episode，再创建 Package B 包含 全新Episode、已拥有ACTIVE Episode 和 归档ARCHIVED Episode | 两个 Package 都创建成功；不返回旧版的 409 重复错误；归档ARCHIVED Episode 消耗 1 个额度，全新Episode/已拥有ACTIVE Episode 不重复计费；不产生下载历史，不更新下载次数 | ☐   |
| E2E-PKG-02 | P0  | 创建 Package 后，立即查询下载历史和 My Data 所有权                                                                               | Package 和 Episode 映射存在；所有权记录正确；下载历史为空                                                                          | ☐   |
| E2E-PKG-03 | P0  | Package 所有者用自己的有效 API Key 为该 Package 创建 Download Session                                                         | Session 创建成功；文件实际交付后，下载历史和下载次数与实际交付的 Episode 完全一致                                                              | ☐   |
| E2E-PKG-04 | P0  | 用 低余额会员用户 的 API Key 去请求 标准会员用户 创建的 Package                                                                       | 返回 403 或 404；不泄露 Package 内容、文件路径；不产生任何历史记录、下载次数或额度变化                                                           | ☐   |
| E2E-PKG-05 | P0  | 准备两个 Episode 列表完全相同、但 `package_id` 不同的 Package，用同一个 Idempotency-Key 分别创建 Session                                 | 两个 Session 不应互相复用；如果出现错误复用，记录为 R-03 风险命中                                                                       | ☐   |
| E2E-PKG-06 | P1  | 创建 Package 后，修改其中某个 Episode 的路径、Ready 状态或可见性，再创建 Session                                                         | Session 基于 Episode 的当前状态构建；响应中明确告知哪些 Episode 被过滤掉；后端记录本次实际交付了哪些文件                                              | ☐   |
| E2E-PKG-07 | P1  | Package 中同时包含状态为 READY 的、非 READY 的和不可见的 Episode                                                                  | 响应中清晰区分"请求了多少"/"符合条件的有多少"/"实际交付了多少"，不以完整交付的口吻掩盖缺失                                                              | ☐   |
| E2E-PKG-08 | P1  | 查看 API Key 列表，尝试查看他人的 Key；然后注销一个 Key 并再次使用                                                                       | 只能看到和操作自己的 Key；注销后该 Key 创建 Session 时返回失败；不泄露其他用户的数据                                                            | ☐   |


### 4.7 数据库迁移与性能


| ID          | P   | 操作步骤                                                        | 预期结果                                          | 结果  |
| ----------- | --- | ----------------------------------------------------------- | --------------------------------------------- | --- |
| E2E-MIG-01  | P0  | 在脱敏的生产数据副本上执行迁移脚本 `20260730_data_user_library_episodes.sql` | 新表结构、主键、外键和索引均符合预期；执行耗时和数据库锁情况在可接受范围内         | ☐   |
| E2E-MIG-02  | P0  | 迁移前后分别统计 downloads / packages / mappings 三张表的记录数，与审批文档对账    | TRUNCATE 的清空结果与审批确认一致；备份数据可以正常查询              | ☐   |
| E2E-MIG-03  | P0  | 从备份中执行完整的数据恢复演练                                             | 历史记录和 Package 数据能够恢复；恢复时间符合 RTO/RPO 要求        | ☐   |
| E2E-MIG-04  | P0  | 按产品决策执行老用户数据的 Backfill（将历史下载记录迁移为 My Data 所有权）              | 已有下载记录的 Episode 被正确迁移，不被重复计入本月额度；迁移数量可与原始记录对账 | ☐   |
| E2E-MIG-05  | P1  | 对同一个环境重复执行迁移脚本两次                                            | 第二次执行要么幂等（无副作用），要么明确报错；不出现数据处于中间状态的情况         | ☐   |
| E2E-PERF-01 | P1  | 为账号准备大量 My Data 数据（如几百条），分页翻页、搜索、切换 Task/Robot 筛选           | 响应时间达到项目 SLA；不出现无索引的全表扫描或明显超时                 | ☐   |
| E2E-PERF-02 | P1  | 为一个包含大量 Episode 的 Package 创建 Download Session，观察构建和下载过程     | 构建耗时、失败率和前端反馈均在可接受范围内                         | ☐   |


---

## 5. 发布准入清单

- [ ] Marketing `d9ccda2` 与 Backend `1ccf165` 同步上线，两者版本可追踪
- [ ] 产品已确认 REVOKED / REFUNDED Episode 的处理规则，四个入口已统一实现
- [ ] API Session 的防重指纹已包含 `package_id`，或已书面确认接受此风险
- [ ] 数据库迁移的备份、Backfill 决策、恢复演练和数量对账均已完成
- [ ] PENDING / FAILED 状态有超时自动处理机制和告警
- [ ] 所有 P0 测试用例通过；P1 用例已修复或有书面风险接受记录
- [ ] Browser / Manifest / API 三种路径的实际交付 Episode = 历史记录 = 下载次数增量，三者对账通过
- [ ] 大文件下载已改为 signed URL 直链，不再经过 `/api/download-file` 中转
- [ ] `successful_count`、`filtered_total_episodes`、`recorded_at` 在前后端联调中表现一致
- [ ] 普通 Active Plan 用户、无会员 operator、过期 Key 用户、Admin 的权限矩阵测试通过
- [ ] 产品已确认无有效会员时 My Data 只读的展示策略
- [ ] 产品已确认 Browse `?public=1` 匿名访问的数据范围