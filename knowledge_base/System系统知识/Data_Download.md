# Robotic Data 下载功能 — 系统分析文档

> **文档版本：** v6.0 | **基准代码日期：** 2026-04-23
> **覆盖范围：** `app-prismax-rp`（前端）+ `app-prismax-rp-backend/app_prismax_data_pipeline`（后端）
> **目的：** 系统梳理用户端（Operator/Admin）和管理端（Admin）数据下载功能的完整逻辑，供 QA 测试设计与 E2E 用例编写使用

---

## 目录

1. [功能概述与核心差异](#1-功能概述与核心差异)
   - 1.1 [用户端（Operator/Admin）下载功能概述](#11-用户端operatoradmin下载功能概述)
   - 1.2 [管理端（Admin）下载功能概述](#12-管理端admin下载功能概述)
   - 1.3 [用户端 vs Admin 端核心差异对照表](#13-用户端-vs-admin-端核心差异对照表)
2. [用户端完整业务逻辑](#2-用户端完整业务逻辑)
   - 2.1 [数据加载与展示](#21-数据加载与展示)
   - 2.2 [分组、排序与筛选](#22-分组排序与筛选)
   - 2.3 [直接下载（UI 模式，≤10 个 Episode）](#23-直接下载ui-模式10-个-episode)
   - 2.4 [批量下载（Manifest 模式，无数量限制）](#24-批量下载manifest-模式无数量限制)
   - 2.5 [单 Episode 下载](#25-单-episode-下载)
   - 2.6 [分享链接（Share Episode Link）](#26-分享链接share-episode-link)
   - 2.7 [下载历史](#27-下载历史)
3. [Admin 端完整业务逻辑](#3-admin-端完整业务逻辑)
   - 3.1 [认证入口](#31-认证入口)
   - 3.2 [数据加载与展示（Upload 粒度）](#32-数据加载与展示upload-粒度)
   - 3.3 [下载操作（UI 模式 / Manifest 模式）](#33-下载操作ui-模式--manifest-模式)
   - 3.4 [Admin 历史记录](#34-admin-历史记录)
4. [后端 API 清单](#4-后端-api-清单)
   - 4.1 [API 总览](#41-api-总览)
   - 4.2 [GET /data/downloadable-uploads（用户端列表）](#42-get-datadownloadable-uploads用户端列表)
   - 4.3 [GET /data/admin/downloadable-upload-groups（Admin 列表）](#43-get-dataadmindownloadable-upload-groupsadmin-列表)
   - 4.4 [POST /data/downloads/ui（直接下载）](#44-post-datadownloadsui直接下载)
   - 4.5 [POST /data/downloads/manifest（批量下载）](#45-post-datadownloadsmanifest批量下载)
   - 4.6 [GET /data/downloads/script（下载脚本）](#46-get-datadownloadsscript下载脚本)
   - 4.7 [GET /data/downloads/history（下载历史）](#47-get-datadownloadshistory下载历史)
   - 4.8 [GET /data/tasks 与 GET /data/machines（公开接口）](#48-get-datatasks-与-get-datamachines公开接口)
   - 4.9 [POST /data/downloadable-uploads/previews（Episode 预览视频）](#49-post-datadownloadable-uploadspreviews-episode-预览视频)
5. [共享机制：GCS Signed URL 与数据库](#5-共享机制gcs-signed-url-与数据库)
   - 5.1 [GCS Signed URL 生成机制](#51-gcs-signed-url-生成机制)
   - 5.2 [data_downloads 表结构与状态流转](#52-data_downloads-表结构与状态流转)
   - 5.3 [关键配置与常量](#53-关键配置与常量)
6. [数据流时序图](#6-数据流时序图)
   - 6.1 [用户端直接下载时序](#61-用户端直接下载时序)
   - 6.2 [用户端批量下载时序](#62-用户端批量下载时序)
   - 6.3 [Admin 端下载时序](#63-admin-端下载时序)
7. [错误处理与边界条件](#7-错误处理与边界条件)
8. [测试策略](#8-测试策略)
   - 8.1 [测试范围与分层](#81-测试范围与分层)
   - 8.2 [测试前提与环境准备](#82-测试前提与环境准备)
9. [E2E 测试用例](#9-e2e-测试用例)
   - 9.1 [权限与认证](#91-权限与认证)
   - 9.2 [数据展示：加载、分组与筛选](#92-数据展示加载分组与筛选)
   - 9.3 [直接下载（UI 模式）](#93-直接下载ui-模式)
   - 9.4 [批量下载（Manifest 模式）](#94-批量下载manifest-模式)
   - 9.5 [单 Episode 下载与分享链接](#95-单-episode-下载与分享链接)
   - 9.6 [下载历史](#96-下载历史)
   - 9.7 [Admin 端专项](#97-admin-端专项)
   - 9.8 [边界与异常场景](#98-边界与异常场景)
   - 9.9 [风险点与回归关注](#99-风险点与回归关注)

---

## 1. 功能概述与核心差异

### 1.1 用户端（Operator/Admin）下载功能概述

用户端下载功能面向具有 `operator` 或 `admin` 角色的已登录用户，允许其浏览并下载自己的机器人采集数据（Episode 数据）。数据按任务（Task / Scenario）分组展示，支持机器型号和任务类别两维度筛选。

**核心功能：**

| 功能 | 说明 |
|------|------|
| 数据浏览 | 按 Task 分组展示所有可下载的 Episode，支持展开/折叠与分页 |
| Robot arm 筛选 | 按机器型号（`product_name`）过滤显示的 Episode |
| Category 筛选 | 按任务类别（`scenario`）过滤 |
| 直接下载 | 选中 ≤10 个 Episode，后端生成 GCS Signed URL，浏览器逐文件下载 |
| 批量下载 | 选中任意数量 Episode，生成并下载 `manifest.json`（不再同时下载 `download.py`） |
| 单 Episode 下载 | 点击单个 Episode 卡片的下载图标，直接下载该 Episode 的全部文件 |
| 分享链接 | 生成 `{baseUrl}/robotic-data/{episode_id}` 格式链接，复制到剪贴板 |
| 下载历史 | 查看本账号所有历史下载记录，任务名称/数据格式/数量/大小/过期时间一览 |
| Episode 视频预览 | Episode 缩略图展示真实视频（懒加载，调用 `/data/downloadable-uploads/previews` 接口） |

**认证机制：** Bearer `gatewayToken`（operator 或 admin 角色），前端在发请求前会进行双重权限前置检查——无 token 则不发请求，有 token 但非允许角色则显示 "Robotic data access required." 错误提示。

---

### 1.2 管理端（Admin）下载功能概述

管理端下载功能面向通过钱包登录的 Admin 用户，数据浏览粒度为 **Upload**（而非 Task），可查看所有用户上传的数据，并以 Upload 批次或单独 Episode 为单位下载。

**核心功能：**

| 功能 | 说明 |
|------|------|
| Upload 分组浏览 | 按 Upload 分组展示所有 Episode，显示 `UPL-XXXX` 标签、Task 信息、Machine 信息 |
| Robot arm / Category 筛选 | 同用户端，支持内存过滤 |
| 按 Upload 批次下载 | 指定 `selected_upload_ids`，下载该 Upload 下所有 Episode |
| 按 Episode 下载 | 在 Upload 分组内单独选中部分 Episode 下载 |
| 批量下载（Manifest）| 生成并下载 `manifest.json`（不再同时下载 `download.py`），用于本地批量脚本下载 |
| Admin 历史记录 | 隔离记录 Admin 操作历史（`user_id` 为负数，与用户历史天然隔离） |

**认证机制：** Bearer `adminJWT`（JWT Admin，通过钱包登录获取，需同时满足 JWT role=admin + 钱包地址在白名单中）。

---

### 1.3 用户端 vs Admin 端核心差异对照表

| 维度 | 用户端（Operator / Admin） | 管理端（Admin） |
|------|-------------------|----------------|
| **认证 Token** | `gatewayToken`（Bearer，用户表 operator **或** admin 角色） | `adminJWT`（Bearer，JWT Admin + 钱包白名单） |
| **入口路由** | `/robotic-data` | `/admin` → Data Download Tab |
| **数据展示粒度** | Task 分组（按 scenario） | Upload 分组（按 upload_id / created_at） |
| **列表接口** | `GET /data/downloadable-uploads` | `GET /data/admin/downloadable-upload-groups` |
| **下载请求参数** | `{ token, user_id, selected_episode_ids }` | `{ selected_upload_ids, admin: true }` |
| **后端 user_id 写法** | token 里的 userid（正整数） | `-abs(admin_id)`（负整数，与用户记录隔离） |
| **历史记录隔离** | `data_downloads.user_id > 0` | `data_downloads.user_id < 0` |
| **历史查询参数** | `?user_id={userId}` | `?admin=true` |
| **列表最大条数** | **50000** 条（Episode） | 分页加载，默认 **24** 条/页（`ADMIN_UPLOAD_GROUP_PAGE_SIZE`），支持 Load more |
| **下载 Episode 上限（UI）** | 10 个 | 10 个（同） |
| **Manifest 模式上限** | 无限制 | 无限制（同） |
| **GCS URL 生成逻辑** | 完全相同 | 完全相同 |

---

## 2. 用户端完整业务逻辑

### 2.1 数据加载与展示

页面挂载时 `loadData()` 并发触发四个接口请求：

| 接口 | 认证 | 作用 |
|------|------|------|
| `GET /data/downloadable-uploads` | Bearer gatewayToken | 获取所有可下载 Episode 列表 |
| `GET /data/tasks` | 无 | 获取 Task 元数据（scenario / title） |
| `GET /data/machines` | 无 | 获取机器信息（product_name） |
| `GET /data/downloads/history?user_id={userId}` | Bearer gatewayToken | 获取当前用户下载历史 |

**前端权限前置检查（发请求前）：**
- 无 `gatewayToken` → 清空所有状态，不发任何请求
- 有 token 但非 `operator`/`admin` 角色 → 设 `error: 'Robotic data access required.'`，清空数据，不发请求
- 权限判断通过独立模块 `access.js` 的 `hasRoboticDataAccess(userRole)` 函数统一处理，允许角色集合：`['operator', 'admin']`

**后端 SQL（`GET /data/downloadable-uploads`）：**

```sql
SELECT e.episode_id, e.upload_id, e.task_id, e.raw_mcap_path,
       u.machine_id, u.status, u.created_at,
       t.scenario, t.data_format,
       m.product_name,
       latest_qa.quality_score
FROM data_episodes e
JOIN data_uploads u ON u.upload_id = e.upload_id
LEFT JOIN data_tasks t ON t.task_id = e.task_id
LEFT JOIN data_machines m ON m.machine_id = u.machine_id
-- 从 data_qa_sessions 取该 upload 最近一次 QA 质量分
LEFT JOIN LATERAL (
    SELECT CASE
               WHEN COALESCE(q.review_result->>'upload_score', '') ~ '^[0-9]+$'
                   THEN (q.review_result->>'upload_score')::int
               ELSE q.qa_score
           END AS quality_score
    FROM data_qa_sessions q
    WHERE q.upload_id = e.upload_id
    ORDER BY q.created_at DESC, q.qa_session_id DESC
    LIMIT 1
) latest_qa ON TRUE
WHERE e.status = 'DERIVED_READY'  -- 只返回已完成处理的 Episode
ORDER BY t.scenario ASC NULLS LAST, e.upload_id DESC, e.episode_id ASC
LIMIT 50000
```

> **排序说明：** 后端排序（scenario ASC）让同 scenario 的 episodes 在原始数组中连续分布，方便前端分组遍历；前端拿到数据后会完全重新分组排序（`localeCompare`），后端排序对最终页面展示顺序几乎无直接影响。

> **字段说明：**
> - `quality_score`：来自该 upload 最近一次 QA 审核会话，优先取 `review_result->>'upload_score'`（整型字符串），其次取 `qa_score` 字段。无 QA 记录时为 `NULL`。
> - `WHERE e.status = 'DERIVED_READY'`：只返回已完成数据处理（派生数据就绪）的 Episode，排除处理中或失败的记录。

**Episode 视频预览懒加载：**

主列表加载完成后，前端按需调用 `POST /data/downloadable-uploads/previews` 获取预览视频 URL（详见 4.9 节）。加载策略：

- 展开某 Task 组时，对当前可见的 Episode（最多 `MAX_EXPANDED_EPISODE_COUNT` = **48** 条）批量请求预览 URL
- 返回的 `episode_id → preview_video_url` 映射存入 `episodePreviewUrls` 状态
- 有 URL 的 Episode 缩略图渲染为 `<video autoPlay muted loop>`，无 URL 时降级为彩色色块

**视频预览双状态追踪与骨架屏：**

在原有 `episodePreviewUrls` 基础上新增两个状态，实现更细粒度的加载反馈：

| 状态变量 | 类型 | 说明 |
|---------|------|------|
| `episodePreviewLoadingIds` | `Record<string, boolean>` | 正在请求预览 URL 的 Episode ID 集合；请求开始时置 `true`，响应返回或出错后删除 |
| `episodePreviewVideoStates` | `Record<string, 'loading'｜'ready'｜'error'>` | 视频元素自身的加载状态；有 URL 时初始化为 `'loading'`，`onCanPlayThrough` 触发后转为 `'ready'`，`onError` 触发后转为 `'error'` |
| `visiblePreviewEpisodeIdSet` | `Set<string>` | 由 `visiblePreviewEpisodeIds` 衍生的 Set，用于 O(1) 查找"该 Episode 是否应有预览" |

**骨架屏显示逻辑（`showPreviewSkeleton`）：**
- `isLoadingPreviewUrl = episodePreviewLoadingIds[key] || (visibleSet.has(key) && !(key in episodePreviewUrls))`：URL 尚未返回时为 `true`
- `isLoadingPreviewVideo = Boolean(previewVideoUrl) && previewVideoState === 'loading'`：URL 已有但视频元素尚未 ready 时为 `true`
- `showPreviewSkeleton = isLoadingPreviewUrl || isLoadingPreviewVideo`：任一为 true 则渲染 `<div className={styles.thumbSkeleton}/>` （shimmer 动画覆盖层）
- 视频元素在 `isLoadingPreviewVideo` 为 `true` 时设置 `style={{display: 'none'}}`，骨架屏消失前不可见

**已选 Episode 勾选框持久显示：** 已选 Episode 卡片不再仅在 hover 时显示勾选框；新增 `videoCheckboxPersistent`（`z-index: 6`）类使勾选框始终可见，点击可直接取消选中（通过 `stopPropagation` 阻止事件冒泡至卡片）。

**无 Episode 空状态文案：** 无 Task 可展示时（未触发筛选），文案为 `"Access restricted."`（涉及 `RoboticDataWorkspace.js` 和 `RoboticData.js` 两处）。

---

### 2.2 分组、排序与筛选

**分组与排序（三步转换）：**

**第一步：按 `task_id` 分组**

将扁平的 `episodes[]` 按 `task_id` 聚合成 `taskRows[]`，每组包含：
- `taskId`
- `title`：优先用 `scenario`，若无则降级为 `"Task {id}"`
- `episodes[]`：该 Task 下的所有 Episode

**第二步：Task 组内 Episode 排序（双级排序）**

```
upload_id 降序（新 upload 在前）
  └── 同 upload_id 内：episode_id 升序
```

效果：同一 Task 下，最新批次上传的数据排在最前面，同批次内按 Episode 编号从小到大展示。

**第三步：Task 组整体排序**

所有 `taskRows` 按 `title` 做 JS `localeCompare` **字母升序**排列。

> 这与后端 SQL 的 `t.scenario ASC`（字节序）不同：`localeCompare` 是 locale 感知的，对大小写、特殊字符、多语言字符的处理更准确。

**最终展示结构示例：**

```
taskRows（按 title 字母序）
├── Pick and Place
│     ├── episode 3（upload_id=20）← 较新 upload
│     ├── episode 4（upload_id=20）
│     ├── episode 1（upload_id=15）← 较旧 upload
│     └── episode 2（upload_id=15）
├── Pour Water
│     └── episode 7（upload_id=18）
└── Sort Objects
      └── episode 5（upload_id=19）
```

**展开/折叠机制：**

| 常量 | 值 | 说明 |
|------|----|------|
| `COLLAPSED_EPISODE_COUNT` | 4 | 折叠时最多显示 4 条 Episode |
| `EXPANDED_PAGE_SIZE` | 20 | 展开后初始显示 20 条，"Load more" 每次再加 20 |
| `MAX_EXPANDED_EPISODE_COUNT` | **48** | 展开后最多显示的 Episode 上限（"Load more" 不超过此值）；同时作为预览视频批量请求的最大数量（仅用户端 `RoboticDataWorkspace.js`） |

**右侧已选面板 Chip 溢出折叠：**

当已选 Episode 数量较多时，右侧选集面板的 Chip 标签会溢出。逻辑限制最多显示 **2 行**，超出部分折叠为汇总 Chip：

| 常量 | 值 | 说明 |
|------|----|------|
| `SELECTED_CHIP_ROW_LIMIT` | 2 | 最多显示的 Chip 行数 |
| `SELECTED_CHIP_GAP_PX` | 4 | Chip 之间的间距（px），用于汇总 Chip 宽度计算 |

**折叠逻辑（`measureVisibleSelectedChipCount`）：**
1. 通过 `data-selected-chip="true"` 属性找到所有 Chip 节点，计算 `offsetTop` 确定行数。
2. 超过 `SELECTED_CHIP_ROW_LIMIT` 行时，记录可见数量 `visibleCount`。
3. 若汇总 Chip（".. N files"）无法在最后一行容纳，则 `visibleCount--`，直至可容纳。
4. 不可见的 Chip 以 `".. N files"` 汇总 Chip 代替展示，该汇总 Chip 带 ✕ 按钮，点击调用 `removeSelectedEpisodes(hiddenEpisodeIds)` 批量移除。

**响应式更新：** 使用 `ResizeObserver` 监听容器尺寸变化 + `requestAnimationFrame` 异步测量，确保容器宽度变化时（如窗口缩放）折叠数量实时更新。

**新增函数 `removeSelectedEpisodes(episodeIds)`：** 支持一次性从 `selectedEpisodeIds` 中移除多个 episode，供汇总 Chip ✕ 按钮使用。

**筛选逻辑（内存过滤，不重新请求接口）：**

| 筛选维度 | 数据来源 | 默认 |
|---------|---------|------|
| Robot arm（机器型号） | `product_name` → `machine_name` → `"Machine {id}"` | 全选 |
| Category（任务类别） | `task.scenario` | 全选 |

过滤规则为双重过滤：先按 Category 过滤，再按 Robot arm 过滤。若 task 组内所有 Episode 均被隐藏，则该组整组隐藏。

**URL 深链（`/robotic-data/:episodeId`）：** 数据加载完成后自动将对应 Episode 加入 `selectedEpisodeIds`，展开所在 Task 组，并确保 `expandedTaskVisibleCounts` ≥ `EXPANDED_PAGE_SIZE`。

---

### 2.3 直接下载（UI 模式，≤10 个 Episode）

**适用场景：** 选中 Episode 数量 ≤ 10，直接在浏览器触发文件下载。

**触发方式：**
- 多选 Episode 后点击 "Download" 按钮（`handleDirectDownload`）
- 点击单个 Episode 卡片的下载图标（`handleSingleEpisodeDownload`，固定传 1 个 `episode_id`）

**完整业务流程：**

```
① 前端选中 Episodes（数量检查：> 10 则拦截，提示用 Batch Download）
        │
        ▼
② POST /data/downloads/ui
   Headers: Authorization: Bearer {gatewayToken}
   Body: { token, user_id, selected_episode_ids: [1, 2, 3] }
        │
        ▼
③ 后端处理（_prepare_download_payload，mode="ui"）
   a. 验证 token 权限 + user_id 与 token 一致性（防越权）
   b. 查询 data_episodes → 获取 raw_bucket / raw_mcap_path / raw_video_folder_path
   c. INSERT data_downloads（status=PENDING）
   d. 对每个 Episode：
      ├─ get_blob(raw_mcap_path) → 存在则生成 GET Signed URL（TTL=7天）
      │                          → 不存在则加入 skipped_episode_ids
      └─ list_blobs(prefix=raw_video_folder_path) → 遍历 .mp4 → 各自生成 Signed URL
   e. UPDATE data_downloads（status=READY，或全部跳过则 FAILED）
   f. 返回 files[]（扁平列表，mcap + 各路视频，每个文件一条）
        │
        ▼
④ 后端响应 200 + JSON：
   {
     "success": true,
     "data": {
       "download_id": 123,
       "mode": "ui",
       "episode_count": 2,
       "total_bytes": 1234567,
       "expires_at": "2026-04-24T...",
       "files": [
         { "upload_id": 10, "episode_id": 1, "episode_key": "episode_001",
           "relative_path": "episode_001.mcap", "url": "https://storage.googleapis.com/...", "size_bytes": 500000 },
         { "relative_path": "episode_001/front_view.mp4", "url": "...", "size_bytes": 200000 },
         { "relative_path": "episode_001/side_view.mp4",  "url": "...", "size_bytes": 180000 }
       ],
       "skipped_episode_ids": []
     }
   }
        │
        ▼
⑤ 前端逐文件顺序下载（performDirectDownload）：
   for (file of files):
     fetch(file.url)          ← 浏览器直接请求 GCS Signed URL（不经后端）
     → response.blob()
     → createObjectURL(blob)
     → <a download> 触发本地保存（文件名由 buildBrowserDownloadFileName(file) 决定：
        MCAP 文件 → {episode_key}.mcap（无 episode_key 则取 relative_path 末段）
        其他文件  → {episode_key}_{baseName}（无 episode_key 则取 relative_path 末段））
     → revokeObjectURL()
     → 更新 downloadProgress（completedFiles++，downloadedBytes+=）
        │
        ▼
⑥ 全部完成 → showNotification('success') → refreshHistory()
```

**下载进度状态机：**

```
idle → preparing → downloading（逐文件更新 completedFiles / downloadedBytes）→ completed
                                                                              ↘ failed
```

---

### 2.4 批量下载（Manifest 模式，无数量限制）

**适用场景：** Episode 数量 > 10，或需要在本地以脚本方式批量下载。

**触发方式：** 点击 "Download manifest.json" 按钮（`handleBatchDownload`，说明文案："Download a manifest.json file for the selected episodes."）

**完整业务流程：**

```
① 前端选中任意数量 Episodes
        │
        ▼
② 发出请求（只发一个请求，不并发请求 /data/downloads/script）：
   POST /data/downloads/manifest
   Headers: Authorization: Bearer {gatewayToken}
   Body: { token, user_id, selected_episode_ids: [...] }
   → 后端处理（_prepare_download_payload，mode="api"，无数量限制）
   → 返回 manifest JSON 文件流（Content-Disposition: attachment; filename=download_{id}_manifest.json）
        │
        ▼
③ manifest.json 结构（下载到本地）：
   {
     "manifest_version": 1,
     "download_id": 456,
     "mode": "api",
     "selected_upload_ids": [10, 11],
     "data_format": "mcap/mp4",
     "created_at": "...",
     "expires_at": "2026-04-24T...",
     "samples": [
       {
         "upload_id": 10, "episode_id": 1, "episode_key": "episode_001",
         "task_id": 5, "task_name": "Pick and Place", "data_format": "mcap/mp4",
         "assets": {
           "mcap":       { "relative_path": "episode_001.mcap",      "url": "...", "size_bytes": 500000 },
           "front_view": { "relative_path": "episode_001/front.mp4", "url": "...", "size_bytes": 200000 },
           "side_view":  { "relative_path": "episode_001/side.mp4",  "url": "...", "size_bytes": 180000 }
         }
       }
     ],
     "skipped_episode_ids": []
   }
        │
        ▼
④ 前端触发浏览器下载（只下载 manifest.json，不下载 download.py）：
   1. downloadResponseBlob(manifestResponse, 'manifest.json')
        │
        ▼
⑤ 用户本地运行脚本（需自行获取 download.py，或自行编写下载逻辑）：
   python3 download.py --manifest manifest.json --output ./dataset
        │
        ▼
⑥ download.py 执行逻辑：
   - 遍历 samples[].assets，对每个 asset 依次下载
   - 输出目录：{output}/upload_{upload_id}/{episode_key}/{relative_path}
   - 幂等：目标文件已存在且 size > 0 则跳过（打印 "Skipping existing file"）
   - 重试：最多 3 次，指数退避（2s → 4s → 8s，最大 10s）
   - SSL 失败：打印 pip install certifi / macOS 修复建议
        │
        ▼
⑦ 下载完成 → showNotification('success', 'Downloaded manifest.json.') → refreshHistory()
```

---

### 2.5 单 Episode 下载

**触发：** 点击 Episode 卡片上的独立下载图标（`handleSingleEpisodeDownload`）

内部直接复用直接下载逻辑，固定传 1 个 `episode_id`，走与多选直接下载完全相同的 `POST /data/downloads/ui` 流程。**不影响当前已选的 Episode 列表状态。**

---

### 2.6 分享链接（Share Episode Link）

**触发：** 点击 Episode 卡片上的分享图标（`handleShareEpisode`）

**链接格式：** `{baseUrl}/robotic-data/{episode.id}`

生成后写入剪贴板，弹出成功提示。

**接收方行为：** 打开链接时，`RoboticDataPage2` 读取路由参数 `:episodeId`，等待 episodes 数据加载完成后自动将该 Episode 加入 `selectedEpisodeIds`，展开并定位到所在 Task 组。若 episode_id 不存在，页面正常加载，无副作用。

---

### 2.7 下载历史

**触发时机：** 页面初始加载（并发请求之一） + 每次下载完成后（`refreshHistory()`）

**请求：** `GET /data/downloads/history?user_id={userId}`，Bearer gatewayToken

**返回字段：** `download_id`、`user_id`、`mode`（ui/api）、`status`（PENDING/READY/FAILED）、`episode_count`、`total_bytes`、`download_count`、`expires_at`、`created_at`、`selected_upload_ids`、`error_message`

**隔离机制：** 后端仅返回 `user_id = {userId}` 的记录，且校验 token userid 与参数 user_id 一致（防越权）。

**历史面板 UI：**

| 区域 | 说明 |
|------|----|
| **总数统计行**（historySummary） | 面板顶部展示 "Total downloads" 标签 + 历史记录总条数，始终可见（即使列表为空） |
| **任务图标框**（historyIconBox） | 每条历史记录左侧蓝色圆角图标，显示任务名前两个单词的首字母缩写（如 "Pick and Place" → "PP"） |
| **任务名称**（historyName） | 通过 `upload_id` 映射到 `uploadHistoryMetaMap`，优先展示关联任务的 `scenario`/`title`；无法匹配时降级显示 `Upload #<id>` |
| **摘要行**（historySub） | 显示 Episode 数量 + 文件总大小 |
| **数据格式 Badge**（historyBadge） | 右侧展示格式化后的数据格式，如 `MP4+MCAP`（由 `formatHistoryDataFormat()` 规范化：`mcap/mp4` → `MP4+MCAP`，多格式用 `+` 连接）；格式为空时不渲染 badge |
| **日期**（historyDate） | 右上角，`created_at` 格式化日期 |
| **空状态** | 无历史记录时显示 "No download history yet."，嵌套在 historySection 容器内 |

**数据映射逻辑（`uploadHistoryMetaMap`）：**

通过 `episodes` 数组构建 `upload_id → {taskTitle, dataFormat}` 映射。每条历史记录取 `selected_upload_ids[0]` 作为查找键：
- 匹配到 → 展示关联的任务标题和数据格式
- 未匹配（Upload 已不在当前列表中） → 降级显示 `Upload #<id>`，格式 badge 不渲染

---

## 3. Admin 端完整业务逻辑

### 3.1 认证入口

Admin 通过钱包登录获取 `adminJWT`：

```
连接钱包 → POST /api/admin-login（签名验证）
→ 后端校验：JWT role=admin + 钱包地址在 admin_whitelist 表中
→ 返回 adminJWT（Bearer Token）
→ 前端存储 adminJWT，后续所有 Admin 请求均携带此 Token
```

钱包地址不在白名单 → 403 "admin access required"；JWT 格式/签名非法 → 401 "invalid token"。

---

### 3.2 数据加载与展示（Upload 粒度）

**触发：** Admin 访问 Data Download Tab 时加载。

**请求：** `GET /data/admin/downloadable-upload-groups?admin=true&limit=24&offset=0`，Bearer adminJWT

**分页加载机制：**

前端不再一次性加载所有 Upload Groups，改为分页加载：

| 常量 / 状态 | 说明 |
|------|------|
| `ADMIN_UPLOAD_GROUP_PAGE_SIZE = 24` | 每页加载的 Upload Group 数量 |
| `uploadGroupsOffset` | 当前已加载的 offset 位置，初始为 0 |
| `hasMoreUploadGroups` | 是否还有更多可加载（来自后端 `pagination.has_more`） |
| `isLoadingMoreUploadGroups` | 正在加载更多时为 `true`，用于 Load more 按钮 disabled 和 "Loading..." 文案 |
| `pendingLoadMorePreviewIds` | 加载更多后待请求预览 URL 的 Episode ID 列表，加载完预览后清空 |

**首次加载**：`loadData({append: false, offset: 0})`，同时请求 Upload Groups 和下载历史；**Load more**：`loadData({append: true, offset: uploadGroupsOffset})`，只请求 Upload Groups（不重新拉历史），新数据按 `upload_id` 去重后追加到现有列表末尾。

**后端 SQL（两阶段查询）：**

```sql
-- 阶段一：分页取 upload_id（排除 UPLOADED / UPLOADING 状态）
SELECT u.upload_id
FROM data_uploads u
WHERE UPPER(COALESCE(u.status, '')) NOT IN ('UPLOADED', 'UPLOADING')
ORDER BY u.created_at DESC, u.upload_id DESC
LIMIT :limit OFFSET :offset;

-- 阶段二：按 upload_id IN 查询完整 Episode 详情
SELECT u.upload_id, u.user_id, u.machine_id, u.status,
       u.created_at, u.uploaded_at,
       t.task_id, t.scenario, t.data_format,
       m.product_name,
       e.episode_id, e.raw_mcap_path, e.raw_video_folder_path,
       e.mcap_size_bytes, e.video_size_bytes
FROM data_uploads u
LEFT JOIN data_tasks t ON t.task_id = u.task_id
LEFT JOIN data_machines m ON m.machine_id = u.machine_id
LEFT JOIN data_episodes e ON e.upload_id = u.upload_id
WHERE u.upload_id IN :upload_ids
ORDER BY u.created_at DESC, u.upload_id DESC, e.episode_id ASC
```

**前端按 `upload_id` 合并分组后展示：**

```
groups（按 created_at DESC，新的在前）
├── UPL-0020（task: Pick and Place，machine: Prismax-A1）
│     ├── episode 3
│     └── episode 4
├── UPL-0019（task: Sort Objects）
│     └── episode 5
└── UPL-0015（task: Pick and Place）
      ├── episode 1
      └── episode 2
└── ...（点击 Load more 继续加载）
```

每个分组显示 `UPL-XXXX` 标签（`upload_id` 格式化为 4 位）、task scenario、machine 型号、episode 数量。列表底部：当 `hasMoreUploadGroups = true` 时显示 "Load more" 按钮；加载中显示 "Loading..."（`isLoadMoreBusy`）。

**预览骨架屏（与用户端一致）：**

Admin 端 Episode 卡片新增与用户端相同的预览骨架屏机制：
- `episodePreviewLoadingIds`：Episode ID → `true`，URL 请求中；响应后删除
- `episodePreviewVideoStates`：Episode ID → `'loading'` / `'ready'` / `'error'`
- 加载更多时，新 Group 的前 `COLLAPSED_EPISODE_COUNT = 4` 个 Episode 自动触发预览 URL 请求
- `showPreviewSkeleton` 逻辑同用户端：URL 加载中或视频元素加载中均显示 shimmer 骨架屏

Admin 同样支持 Robot arm 和 Category 两维度内存过滤，逻辑与用户端一致。

---

### 3.3 下载操作（UI 模式 / Manifest 模式）

Admin 端同样支持直接下载（UI 模式）和批量下载（Manifest 模式），核心差异仅在于请求参数：

**直接下载（POST /data/downloads/ui）：**

```
Headers: Authorization: Bearer {adminJWT}
Body: { selected_upload_ids: [10, 11], admin: true }
      └── 也可传 selected_episode_ids 实现 Episode 级别精选
```

**批量下载（POST /data/downloads/manifest）：**

```
Headers: Authorization: Bearer {adminJWT}
Body: { selected_upload_ids: [...], admin: true }
```

**后端处理：**
1. 验证 adminJWT（role=admin + 白名单）
2. 根据 `selected_upload_ids` 查询其下所有 episodes，或直接使用 `selected_episode_ids`
3. 计算 `user_id = -abs(admin_id)`（负数，隔离存储）
4. 后续逻辑与用户端完全相同（`_prepare_download_payload`）

---

### 3.4 Admin 历史记录

**请求：** `GET /data/downloads/history?admin=true`，Bearer adminJWT

**后端查询：**

```sql
SELECT ... FROM data_downloads
WHERE user_id = -abs(admin_id)  -- 负数
ORDER BY created_at DESC, download_id DESC
```

**隔离保障：** Admin 记录的 `user_id` 为负数，用户端记录的 `user_id` 为正数，同一张 `data_downloads` 表通过正负值天然隔离，任何一方均无法访问对方的历史记录。

---

## 4. 后端 API 清单

### 4.1 API 总览

| # | 方法 | 路径 | 认证方式 | 调用方 | 用途 |
|---|------|------|---------|--------|------|
| 1 | GET | `/data/downloadable-uploads` | Bearer（operator **或** admin） | 用户端 | 获取可下载 Episode 列表 |
| 2 | GET | `/data/admin/downloadable-upload-groups` | Bearer adminJWT / Bearer admin | Admin 端 | 获取可下载 Upload 分组列表 |
| 3 | POST | `/data/downloads/ui` | Bearer（operator/admin / adminJWT） | 用户端 + Admin | 创建直接下载，返回 Signed URL 列表 |
| 4 | POST | `/data/downloads/manifest` | Bearer（operator/admin / adminJWT） | 用户端 + Admin | 创建批量下载 Manifest 文件 |
| 5 | GET | `/data/downloads/script` | Bearer（operator/admin / adminJWT） | 用户端 + Admin | 获取 download.py 脚本 |
| 6 | GET | `/data/downloads/history` | Bearer（operator/admin / adminJWT） | 用户端 + Admin | 查询下载历史 |
| 7 | GET | `/data/tasks` | 无 | 用户端 + Admin | 获取 Task 元数据（公开） |
| 8 | GET | `/data/machines` | 无 | 用户端 + Admin | 获取机器列表（公开） |
| 9 | POST | `/data/downloadable-uploads/previews` | Bearer（operator **或** admin） | 用户端 | 获取指定 Episode 的预览视频 Signed URL |

---

### 4.2 GET /data/downloadable-uploads（用户端列表）

**用途：** 返回所有可下载的 Episode 列表，仅供用户端使用
**认证：** Bearer Token，`user_role = operator` **或** `admin`（通过 `_require_robotic_data_user()` 统一校验）
**限制：** 最多返回 **50000** 条
**数据过滤：** 仅返回 `e.status = 'DERIVED_READY'` 的 Episode

**返回字段：**
`episode_id`、`upload_id`、`task_id`、`raw_mcap_path`、`machine_id`、`product_name`、`status`、`created_at`、`scenario`、`data_format`、`episode_key`、`quality_score`（来自最近一次 QA 审核，可为 NULL）

**错误响应：**

| 情况 | HTTP 状态 | 错误信息 |
|------|-----------|---------|
| 无 token | 401 | unauthorized |
| 非 operator/admin 角色 | 403 | operator access required |

---

### 4.3 GET /data/admin/downloadable-upload-groups（Admin 列表）

**用途：** 返回所有 Upload 分组及其下属 Episodes，仅供 Admin 端使用
**认证：**
- `?admin=true` → JWT Admin（JWT role=admin + 钱包白名单）
- 无该参数 → Bearer Token，`user_role = admin`（用户表管理员角色）

**返回格式：** 按 `upload_id` 分组，每组包含 `upload_label`（"UPL-XXXX"）、Episodes 列表及汇总字段

**分页参数：**

| 参数 | 类型 | 默认值 | 范围 | 说明 |
|------|------|------|------|------|
| `limit` | int | 24 | 1~100 | 每页返回的 Upload Group 数量 |
| `offset` | int | 0 | ≥ 0 | 分页起始位置 |

**成功响应（200）：**

```json
{
  "success": true,
  "data": [...],
  "pagination": {
    "limit": 24,
    "offset": 0,
    "count": 24,
    "total_upload_count": 150,
    "has_more": true,
    "next_offset": 24
  }
}
```

> `has_more = false` 时 `next_offset` 为 `null`；前端读取 `pagination.has_more` 决定是否显示 "Load more" 按钮，读取 `pagination.next_offset` 作为下次请求的 `offset` 参数。

**错误响应：**

| 情况 | HTTP 状态 | 错误信息 |
|------|-----------|---------|
| 无效 JWT | 401 | invalid token |
| 钱包地址不在白名单 | 403 | admin access required |
| limit 非法（非整数或超出 1~100） | 400 | limit must be an integer between 1 and 100 |
| offset 非法（非整数或负数） | 400 | offset must be a non-negative integer |

---

### 4.4 POST /data/downloads/ui（直接下载）

**用途：** 创建直接下载任务，生成并返回每个文件的 GCS GET Signed URL 列表
**Episode 上限：** 10 个（`DIRECT_DOWNLOAD_MAX_EPISODES`）
**认证：** operator Bearer Token 或 adminJWT Bearer Token

**请求体：**

```json
// 用户端
{ "token": "...", "user_id": 123, "selected_episode_ids": [1, 2, 3] }

// Admin 端
{ "selected_upload_ids": [10, 11], "admin": true }
```

**核心处理（`_prepare_download_payload`，mode="ui"）：**
1. 权限校验（user_id 与 token 一致性 / adminJWT 白名单）
2. 查询 `data_episodes` 获取 GCS 路径
3. INSERT `data_downloads`（status=PENDING）
4. 对每个 Episode 的每个文件生成 GET Signed URL（TTL=7天）
5. UPDATE `data_downloads`（status=READY 或 FAILED）
6. 返回扁平化 `files[]` 列表

**成功响应（200）：**

```json
{
  "success": true,
  "data": {
    "download_id": 123,
    "mode": "ui",
    "episode_count": 2,
    "total_bytes": 1234567,
    "expires_at": "2026-04-24T12:00:00Z",
    "files": [
      { "upload_id": 10, "episode_id": 1, "episode_key": "episode_001",
        "relative_path": "episode_001.mcap", "url": "https://storage.googleapis.com/...", "size_bytes": 500000 }
    ],
    "skipped_episode_ids": []
  }
}
```

**错误响应：**

| 情况 | HTTP 状态 | 错误信息 |
|------|-----------|---------|
| user_id 与 token 不匹配 | 403 | user_id does not match token |
| 超过 10 个 Episode | 400 | exceeded max episodes for direct download |
| 全部 Episode 被跳过（无 mcap） | 400 | no downloadable raw episodes found |
| 空 selected_episode_ids | 400 | selected_episode_ids or selected_upload_ids is required |

---

### 4.5 POST /data/downloads/manifest（批量下载）

**用途：** 创建批量下载 Manifest，以 JSON 文件附件形式返回
**Episode 上限：** 无限制
**认证：** 同 4.4

**请求体：** 同 4.4

**响应头：**
```
Content-Type: application/json
Content-Disposition: attachment; filename=download_{download_id}_manifest.json
```

**响应体：** 完整 manifest JSON 对象（见 2.4 节 manifest.json 结构）

内部同样调用 `_prepare_download_payload(mode="api")`，与 UI 模式唯一区别是返回完整 manifest 对象而非 `files[]`。

---

### 4.6 GET /data/downloads/script（下载脚本）

**用途：** 返回 `download.py` 批量下载辅助脚本
**认证：** operator / admin（用户表）/ JWT Admin 均可

**响应头：**
```
Content-Type: text/x-python
Content-Disposition: attachment; filename=download.py
```

Admin 端请求时需加 `?admin=true` 参数。

---

### 4.7 GET /data/downloads/history（下载历史）

**用途：** 查询下载历史记录
**认证：** operator / admin（用户表）/ JWT Admin

**请求参数：**

| 场景 | 参数 | user_id 取值 |
|------|------|-------------|
| 用户端 | `?user_id={userId}` | token userid（必须与 token 一致，防越权） |
| Admin 端 | `?admin=true` | `-abs(admin_id)` |

**成功响应（200）：**

```json
{
  "success": true,
  "data": [
    {
      "download_id": 123,
      "user_id": 456,
      "mode": "ui",
      "status": "READY",
      "episode_count": 3,
      "total_bytes": 1234567,
      "download_count": 1,
      "expires_at": "2026-04-24T12:00:00Z",
      "created_at": "2026-04-17T12:00:00Z",
      "selected_upload_ids": [10],
      "error_message": null
    }
  ]
}
```

**错误响应：**

| 情况 | HTTP 状态 | 错误信息 |
|------|-----------|---------|
| 用户端传入不匹配的 user_id | 403 | user_id does not match token |
| 无效 adminJWT | 401 | invalid token |

---

### 4.8 GET /data/tasks 与 GET /data/machines（公开接口）

**用途：** 分别返回 Task 列表和 Machine 列表，供前端筛选与展示
**认证：** 无（公开接口，前端不携带 Authorization 头）
**用途场景：** 用户端页面加载时并发请求，Admin 端相同

---

### 4.9 POST /data/downloadable-uploads/previews（Episode 预览视频）

**用途：** 批量获取指定 Episode 的派生视频预览 Signed URL，供前端 Episode 缩略图懒加载使用
**认证：** Bearer Token，`user_role = operator` **或** `admin`
**Episode 数量限制：** 单次请求最多 200 个 `episode_id`

**请求体：**

```json
{
  "selected_episode_ids": [1, 2, 3, 4]
}
```

**后端处理：**
1. 校验 `selected_episode_ids` 非空且不超过 200
2. 查询 `data_episodes`（含 `derived_bucket`、`derived_video_folder_path`）
3. 对每个 Episode 调用 `_list_public_derived_videos()` 获取派生视频列表，取第一个有效 Signed URL（通过 `_pick_preview_video_url()` 辅助函数）
4. URL TTL = 86400 秒（1天）

**成功响应（200）：**

```json
{
  "success": true,
  "data": [
    { "episode_id": 1, "preview_video_url": "https://storage.googleapis.com/..." },
    { "episode_id": 2, "preview_video_url": null },
    { "episode_id": 3, "preview_video_url": "https://storage.googleapis.com/..." }
  ]
}
```

> 无派生视频时 `preview_video_url` 为 `null`，前端降级展示彩色色块。

**错误响应：**

| 情况 | HTTP 状态 | 错误信息 |
|------|-----------|---------|
| 无 token 或非允许角色 | 401/403 | unauthorized / operator access required |
| selected_episode_ids 为空 | 400 | selected_episode_ids is required |
| selected_episode_ids 超过 200 | 400 | selected_episode_ids is limited to 200 |

---

## 5. 共享机制：GCS Signed URL 与数据库

### 5.1 GCS Signed URL 生成机制

**存储桶：**
- 原始数据（用户下载）：`prismax-data-raw-prod`（环境变量 `DATA_RAW_BUCKET`）
- 处理后数据：`prismax-data-derived-prod`（`DATA_DERIVED_BUCKET`）

**签名方式（GCS v4 签名）：**

```python
blob.generate_signed_url(
    version="v4",
    expiration=timedelta(seconds=ttl_seconds),
    method="GET",           # 下载用 GET；上传用 PUT
    service_account_email=...,
    access_token=...        # 来自 GCP 服务账号凭证
)
```

**TTL 配置：**

| 用途 | TTL |
|------|-----|
| 默认（`SIGNED_URL_TTL_SECONDS`） | 86400 秒（1天） |
| 下载用 URL（manifest / ui 模式） | 604800 秒（**7天**，`DOWNLOAD_TTL_SECONDS`） |
| 上传用 URL（PUT，upload session） | 86400 秒（1天） |

**每个 Episode 包含的文件：**
- `{episode_key}.mcap`（原始传感器数据，**必须存在，否则整个 Episode 被跳过**）
- `{episode_key}/{video_name}.mp4` × N（多路视频，如 front_view / side_view / wrist_view）

**文件查找逻辑（`_build_raw_sample_payload`）：**
1. `raw_bucket.get_blob(raw_mcap_path)` — mcap 不存在则返回 None，该 Episode 加入 `skipped_episode_ids`
2. `list_blobs(prefix=raw_video_folder_path)` — 遍历目录下所有 `.mp4`（无 mp4 则 assets 中无视频字段）

---

### 5.2 data_downloads 表结构与状态流转

**表结构：**

| 字段 | 类型 | 说明 |
|------|------|------|
| `download_id` | SERIAL PK | 自增 ID |
| `user_id` | INTEGER | 用户 ID（Admin 记录为**负数**） |
| `mode` | VARCHAR | `"ui"` 或 `"api"` |
| `status` | VARCHAR | `PENDING` / `READY` / `FAILED` |
| `manifest_version` | INTEGER | 固定为 1 |
| `selected_upload_ids` | JSONB | 关联的 upload_id 列表 |
| `episode_count` | INTEGER | 成功生成 URL 的 Episode 数量 |
| `total_bytes` | BIGINT | 所有文件总字节数 |
| `download_count` | INTEGER | 固定为 1（当前实现） |
| `error_message` | VARCHAR(1000) | 失败时的错误信息 |
| `expires_at` | TIMESTAMP | 记录过期时间（创建时间 + 7天） |
| `created_at` | TIMESTAMP | 记录创建时间 |

**状态流转：**

```
INSERT（status=PENDING）
  ├─ GCS URL 生成全部成功 → UPDATE（status=READY，episode_count、total_bytes 填充）
  └─ 失败（无可用 Episode / 超限）→ UPDATE（status=FAILED，error_message 填充）
```

**相关表关系：**

```
data_tasks (task_id, scenario, data_format)
     ↑
data_uploads (upload_id, user_id, machine_id, task_id, status, created_at)
     ↑
data_episodes (episode_id, upload_id, task_id, raw_bucket, raw_mcap_path, raw_video_folder_path)
     ↓（每次下载操作写入一条）
data_downloads (download_id, user_id, mode, status, ...)

data_machines (machine_id, product_name, machine_name)
     ↑（JOIN data_uploads）
```

**性能索引：**
```sql
CREATE INDEX IF NOT EXISTS idx_data_episodes_upload_id ON data_episodes (upload_id);
```

---

### 5.3 关键配置与常量

**前端常量：**

| 常量 | 值 | 说明 |
|------|----|------|
| `DIRECT_DOWNLOAD_MAX_EPISODES` | 10 | 直接下载（浏览器）最大 Episode 数 |
| `COLLAPSED_EPISODE_COUNT` | 4 | Task 组折叠时显示的 Episode 数量 |
| `EXPANDED_PAGE_SIZE` | 20 | 展开后每页加载/每次 Load more 的数量 |
| `MAX_EXPANDED_EPISODE_COUNT` | **48** | 展开后最多显示的 Episode 数量上限；也是预览视频批量请求的最大值（用户端 `RoboticDataWorkspace.js`） |
| `SELECTED_CHIP_ROW_LIMIT` | 2 | 右侧选集面板 Chip 最大显示行数；超出折叠为 ".. N files" |
| `SELECTED_CHIP_GAP_PX` | 4 | Chip 间距（px），用于计算汇总 Chip 是否能在末行容纳 |
| `ADMIN_UPLOAD_GROUP_PAGE_SIZE` | 24 | Admin 端 Upload Groups 每页加载数量（`RoboticDataAdmin.js`） |

**前端状态变量（用户端 `RoboticDataWorkspace.js`）：**

| 状态变量 | 初始值 | 说明 |
|---------|------|------|
| `episodePreviewLoadingIds` | `{}` | Episode ID → `true`，表示该 Episode 的预览 URL 正在请求中；权限变更、数据重载时同步清空 |
| `episodePreviewVideoStates` | `{}` | Episode ID → `'loading'｜'ready'｜'error'`；有 URL 返回时置 `'loading'`，`onCanPlayThrough` 后置 `'ready'`，`onError` 后置 `'error'`；权限变更、数据重载时同步清空 |

**Admin 端前端状态变量（`RoboticDataAdmin.js`）：**

| 状态变量 | 初始值 | 说明 |
|---------|------|------|
| `uploadGroupsOffset` | 0 | 当前已加载的分页偏移量 |
| `hasMoreUploadGroups` | `false` | 来自后端 `pagination.has_more`，控制 Load more 按钮显示 |
| `isLoadingMoreUploadGroups` | `false` | 加载更多时为 `true`，与 `pendingLoadMorePreviewIds` 共同构成 `isLoadMoreBusy` |
| `pendingLoadMorePreviewIds` | `[]` | Load more 后等待预览 URL 返回的 Episode ID 列表；所有预览加载完成后清空 |
| `episodePreviewLoadingIds`（Admin） | `{}` | Admin 端独立维护，逻辑与用户端一致 |
| `episodePreviewVideoStates`（Admin） | `{}` | Admin 端独立维护，逻辑与用户端一致 |

**前端模块：**

| 模块 | 导出 | 说明 |
|------|------|------|
| `access.js` | `hasRoboticDataAccess(userRole)` | 返回 boolean，允许 `operator` 和 `admin` 角色 |
| `access.js` | `ROBOTIC_DATA_ACCESS_ERROR` | `'Robotic data access required.'`（统一错误文案常量） |

**后端常量：**

| 常量 | 值 | 说明 |
|------|----|------|
| `SIGNED_URL_TTL_SECONDS` | 86400（1天） | 默认 Signed URL TTL |
| `DOWNLOAD_TTL_SECONDS` | 604800（7天） | 下载用 Signed URL TTL（manifest / ui 模式） |
| `DIRECT_DOWNLOAD_MAX_EPISODES` | 10 | UI 模式最大 Episode 数量 |
| `MAX_FILES_PER_UPLOAD` | 2000 | 每个 Upload 最大文件数 |
| `DATA_RAW_BUCKET` | `prismax-data-raw-prod` | 原始数据存储桶 |
| `DATA_DERIVED_BUCKET` | `prismax-data-derived-prod` | 处理后数据存储桶 |
| `ROBOTIC_DATA_ALLOWED_USER_ROLES` | `("operator", "admin")` | 用户端下载功能允许的用户角色集合（由 `_require_robotic_data_user()` 使用） |

---

## 6. 数据流时序图

### 6.1 用户端直接下载时序

```
Operator浏览器        Frontend(React)           Backend(Flask)           GCS
      │                     │                        │                     │
      │──选中Episodes───────►│                        │                     │
      │──点击Download────────►│                        │                     │
      │                     │──POST /downloads/ui────►│                     │
      │                     │  {token,user_id,        │                     │
      │                     │   selected_episode_ids} │                     │
      │                     │                        │──验证token/user_id   │
      │                     │                        │──查询data_episodes   │
      │                     │                        │──INSERT PENDING      │
      │                     │                        │──生成Signed URLs────►│
      │                     │                        │◄──返回URLs───────────│
      │                     │                        │──UPDATE READY        │
      │                     │◄──{files:[{url,...}]}──│                     │
      │                     │  [逐文件循环]           │                     │
      │                     │──fetch(file.url)────────────────────────────►│
      │                     │◄──文件Blob──────────────────────────────────│
      │◄──浏览器保存文件─────│                        │                     │
      │                     │──GET /downloads/history►│                     │
      │◄──显示历史记录───────│◄──{data:[...]}──────────│                    │
```

### 6.2 用户端批量下载时序

```
Operator浏览器        Frontend(React)           Backend(Flask)           GCS
      │                     │                        │                     │
      │──点击Download manifest►│                       │                     │
      │                     │──POST /downloads/manifest►│                   │
      │                     │  (不再并发请求 /downloads/script)              │
      │                     │                        │──验证权限            │
      │                     │                        │──查询episodes        │
      │                     │                        │──INSERT PENDING      │
      │                     │                        │──生成Signed URLs────►│
      │                     │                        │◄──返回URLs───────────│
      │                     │                        │──UPDATE READY        │
      │                     │◄──manifest.json─────────│                     │
      │◄──保存manifest.json──│                        │                     │
      │                     │                        │                     │
      │──python3 download.py --manifest manifest.json --output ./dataset   │
      │   (用户需自行获取 download.py 脚本)                                  │
      │──────────────────────────────────────────────────────────────────►│
      │◄──所有文件下载到本地──────────────────────────────────────────────│
```

### 6.3 Admin 端下载时序

```
Admin浏览器           Frontend(React)           Backend(Flask)           GCS
      │                     │                        │                     │
      │──连接钱包────────────►│                        │                     │
      │                     │──POST /api/admin-login──►│                   │
      │◄──adminJWT───────────│◄──JWT(role=admin)───────│                   │
      │──访问DataDownload Tab►│                        │                     │
      │                     │──GET /admin/downloadable-upload-groups►│      │
      │                     │  ?admin=true, Bearer adminJWT           │     │
      │                     │                        │──验证JWT+whitelist   │
      │◄──显示Upload列表─────│◄──{groups:[...]}────────│                   │
      │──选择Upload/Episode──►│                        │                     │
      │──点击Download────────►│                        │                     │
      │                     │──POST /downloads/ui─────►│                   │
      │                     │  {selected_upload_ids,  │                     │
      │                     │   admin:true}           │                     │
      │                     │  Bearer: adminJWT       │                     │
      │                     │                        │──验证JWT Admin        │
      │                     │                        │──user_id=-abs(id)    │
      │                     │                        │──生成Signed URLs────►│
      │                     │◄──{files:[...]}─────────│◄──URLs──────────────│
      │◄──浏览器下载文件──────│                        │                     │
```

---

## 7. 错误处理与边界条件

### 权限相关

| 场景 | 前端行为 | 后端响应 |
|------|----------|---------|
| 无 token 访问用户端 | 清空数据，不发任何请求 | — |
| 非 operator/admin 角色访问 | 显示 "Robotic data access required."，清空数据 | — |
| Operator 传入不同 user_id | — | 403 "user_id does not match token" |
| token 过期 | — | 401 unauthorized |
| 无效 adminJWT | — | 401 "invalid token" |
| 钱包地址不在白名单 | — | 403 "admin access required" |

### 数据相关

| 场景 | 处理方式 |
|------|---------|
| Episode 的 mcap blob 不存在于 GCS | 跳过该 Episode，加入 `skipped_episode_ids` |
| 所有 Episodes 都跳过 | DB 记录 FAILED，返回 400 "no downloadable raw episodes found" |
| UI 模式超过 10 个 Episodes | 前端拦截提示使用 Batch Download，后端也返回 400 |
| Manifest 模式无数量限制 | 性能瓶颈在于 GCS list_blobs 请求量 |
| Signed URL 过期（7天后） | 用户下载失败，需重新发起下载请求 |
| Episode 有 mcap 但无 mp4 | 该 Episode 仍包含在结果中，assets 只含 mcap 字段 |
| 空 selected_episode_ids | 400 "selected_episode_ids or selected_upload_ids is required" |

### 下载相关

| 场景 | 处理方式 |
|------|---------|
| 单文件 fetch 失败（UI 模式） | `downloadSignedFile` 抛出异常，`downloadProgress.status` 转为 `failed`，停止后续文件下载 |
| manifest 请求失败 | batch download 整体失败，弹出错误提示 |
| download.py SSL 证书失败 | 打印 `pip install certifi` / macOS 修复建议 |
| download.py 单文件失败 | 最多重试 3 次，指数退避（2s → 4s → 8s，最大 10s）；三次均失败则报错退出 |

### 前端状态管理

- 所有下载状态均为组件内 `useState`，**无全局 store**
- `downloadProgress` 完整跟踪：`status / mode / totalFiles / completedFiles / totalEpisodes / downloadedBytes / totalBytes / currentFileName / message / error`
- 下载进行中不阻止用户浏览其他内容
- 每次下载完成后自动调用 `refreshHistory()` 刷新历史记录

---

## 8. 测试策略

### 8.1 测试范围与分层

| 测试层 | 覆盖目标 | 优先级 |
|--------|---------|--------|
| **接口测试（API）** | 认证校验、参数边界、响应结构、DB 状态流转 | P0 |
| **E2E 测试** | 前端触发 → 后端处理 → GCS Signed URL → 文件实际可下载（用 staging GCS） | P0 |
| **UI 功能测试** | 数据展示、分组排序、筛选交互、下载进度状态机、历史记录刷新 | P1 |
| **异常/边界测试** | 权限拦截、数量限制、文件缺失、URL 过期、空选、并发请求 | P1 |
| **download.py 脚本测试** | 幂等性、重试、目录结构、SSL 异常 | P2 |

**不在范围内：** GCS 存储桶内部读写性能基准、Admin 钱包登录流程本身（由 Admin 模块单独覆盖）。

---

### 8.2 测试前提与环境准备

**测试账号要求：**

| 账号类型 | 用途 | 要求 |
|----------|------|------|
| Operator 用户 A | 用户端下载测试主账号 | `user_role = operator` |
| Operator 用户 B | 用户端历史隔离验证 | `user_role = operator`，不同 user_id |
| 非 Operator 用户 | 权限拒绝场景 | `user_role ≠ operator` 且 `≠ admin` |
| Admin（钱包登录） | Admin 端下载测试 | 钱包地址在 `admin_whitelist` |
| 非白名单钱包 | Admin 权限拒绝场景 | 钱包地址**不在** `admin_whitelist` |
| 过期/伪造 token | 认证失败场景 | 手动构造过期或无效 token |

**数据前提：**

| 场景 | 所需测试数据 |
|------|------------|
| 正常下载（UI/Manifest） | Episode 数据行存在，且 GCS 中有对应 `.mcap` + `.mp4` 文件 |
| skipped_episode 场景 | Episode 记录存在，但 GCS 中**无** mcap 文件 |
| 超量 UI 下载 | 可选中 Episode 数量 ≥ 11 |
| 历史记录展示 | 已存在 ≥ 1 条 `data_downloads` 记录 |
| 空状态页面 | DB 中无任何可下载 Episode |
| Admin Upload 分组 | 多个 Upload，含跨 Task 和跨 Machine 的数据 |

---

## 9. E2E 测试用例

### 9.1 权限与认证

**用户端权限：**

| # | 场景 | 前置条件 | 操作 | 预期结果 | 优先级 |
|---|------|---------|------|---------|--------|
| P-01 | 未登录访问 `/robotic-data` | 浏览器无 token | 直接打开 `/robotic-data` | 不发任何数据请求，无 Episode 列表，无报错 | P0 |
| P-02 | 非允许角色登录 | token 存在但 `user_role ≠ operator` 且 `≠ admin` | 使用普通用户 token 访问 | 前端显示 "Robotic data access required."，列表不渲染，不发请求 | P0 |
| P-03 | Operator 正常登录 | token 存在且 `user_role = operator` | 正常登录后访问 | Episode 列表正常加载，四个接口均 200 | P0 |
| P-03b | Admin 角色（用户表）登录用户端 | token 存在且 `user_role = admin`（用户表 admin，非 JWT Admin） | 使用 admin 角色 token 访问 `/robotic-data` | Episode 列表正常加载，访问权限与 operator 一致；不显示错误提示 | P0 |
| P-04 | Operator 下载时篡改 user_id | 有效 token | 手动修改请求 body 中 `user_id` 为他人 ID | 后端返回 403 "user_id does not match token"，不生成下载 | P0 |
| P-05 | 过期 token 尝试下载 | token 已过期 | 用过期 token 请求 POST /downloads/ui | 后端返回 401，前端进度条转为 failed | P1 |

**Admin 端权限：**

| # | 场景 | 前置条件 | 操作 | 预期结果 | 优先级 |
|---|------|---------|------|---------|--------|
| P-06 | 未连接钱包访问 Admin | 无 adminJWT | 直接进入 `/admin` 的 Data Download Tab | 显示连接钱包提示，不渲染 Upload 列表 | P0 |
| P-07 | 非白名单钱包连接 | 钱包地址不在白名单 | 连接非白名单钱包并获取 JWT | 后端返回 403 "admin access required" | P0 |
| P-08 | 有效 Admin 登录 | 钱包地址在白名单 | 正常钱包登录后访问 Data Download Tab | Upload 分组列表正常加载 | P0 |
| P-09 | 伪造 adminJWT 请求下载 | 无效 JWT | 用伪造 JWT 请求 POST /downloads/ui | 后端返回 401 "invalid token" | P0 |

---

### 9.2 数据展示：加载、分组与筛选

**数据加载：**

| # | 场景 | 前置条件 | 操作 | 预期结果 | 优先级 |
|---|------|---------|------|---------|--------|
| D-01 | 页面初始加载 | 有 operator token，DB 有数据 | 打开 `/robotic-data` | 四个接口（episodes、tasks、machines、history）并发请求均 200；Episode 列表、筛选器、历史记录均正常渲染 | P0 |
| D-02 | 空数据页面 | DB 中无 Episode | 打开 `/robotic-data` | 列表区域显示空状态，无报错，筛选器无内容 | P1 |
| D-03 | 数据超 1500 条 | DB 中 Episode > 1500 | 打开页面 | 页面能展示超过 1500 条 Episode（最多 50000 条）；分组、排序、筛选功能正常；无前端报错 | P2 |

**分组与排序：**

| # | 场景 | 前置条件 | 操作 | 预期结果 | 优先级 |
|---|------|---------|------|---------|--------|
| D-04 | 多 Task 字母排序 | 存在 3 个不同 scenario 的 Task | 打开页面 | Task 组按 scenario 名字母升序排列（localeCompare） | P1 |
| D-05 | 无 scenario 的 Task | 存在 task.scenario = null | 打开页面 | 该 Task 显示为 "Task {id}"，排在有 scenario 的 Task 后面 | P1 |
| D-06 | 同 Task 多 Upload 排序 | 同一 Task 下有 upload_id=20 和 upload_id=15 | 打开页面展开该 Task 组 | upload_id=20 的 Episodes 排在前；同 upload 内按 episode_id 升序 | P1 |
| D-07 | 展开/折叠与 Load more | 某 Task 有 > 20 个 Episodes | 折叠 → 展开 → 点击 Load more | 折叠时最多 4 条；展开后 20 条；每次 Load more 再加 20 条；最多展示 **48 条**（`MAX_EXPANDED_EPISODE_COUNT`），超出后 Load more 按钮消失 | P1 |

**筛选：**

| # | 场景 | 前置条件 | 操作 | 预期结果 | 优先级 |
|---|------|---------|------|---------|--------|
| D-08 | Robot arm 单类型过滤 | 存在多种机器型号的 Episodes | 取消选中某型号 | 该型号的 Episodes 隐藏；所有 Episode 均被过滤的 Task 组整组隐藏 | P1 |
| D-09 | Category 单类型过滤 | 存在多个 scenario | 只选中一个 scenario | 只显示该 scenario 的 Task 组 | P1 |
| D-10 | 筛选不触发网络请求 | 页面已加载 | 切换筛选条件（Robot arm / Category） | Network 面板无新的数据接口请求（只有内存过滤） | P1 |
| D-11 | 筛选后无结果 | 存在互斥的数据 | 选中无交集的 Robot arm + Category 组合 | 列表为空，无报错，无崩溃 | P2 |
| D-12 | Machine label 显示优先级 | 存在有/无 product_name 的机器 | 查看筛选器 Machine 标签 | 有 product_name → 显示 product_name；无 product_name → 显示 "Machine {id}" | P2 |

**深链 URL：**

| # | 场景 | 前置条件 | 操作 | 预期结果 | 优先级 |
|---|------|---------|------|---------|--------|
| D-13 | 深链打开存在的 episode | episode_id 有效 | 访问 `/robotic-data/{episodeId}` | 数据加载完成后该 Episode 自动选中，所在 Task 组自动展开并定位 | P1 |
| D-14 | 深链打开不存在的 episode | episode_id 无效 | 访问 `/robotic-data/99999999` | 页面正常加载，无 Episode 自动选中，无报错 | P2 |

**Episode 视频预览：**

| # | 场景 | 前置条件 | 操作 | 预期结果 | 优先级 |
|---|------|---------|------|---------|--------|
| D-15 | 展开 Task 组触发预览加载 | Episode 有派生视频（derived video） | 展开某 Task 组 | 前端调用 `POST /data/downloadable-uploads/previews`，传入当前可见 Episode ID 列表；缩略图从色块变为循环播放的视频 | P1 |
| D-16 | 无派生视频时降级展示 | Episode 无派生视频（preview_video_url = null） | 展开 Task 组，查看缩略图 | 缩略图降级为彩色色块 + 播放图标，不报错 | P1 |
| D-17 | 预览接口数量上限 | 构造超过 200 个 episode_id 的请求 | 直接调用 `/data/downloadable-uploads/previews`，body 含 201 个 ID | 后端返回 400 "selected_episode_ids is limited to 200" | P2 |
| D-18 | 预览接口权限校验 | 非允许角色 token | 用非 operator/admin token 请求预览接口 | 后端返回 403 | P1 |
| D-19 | LIMIT 50000 验证 | DB 中 Episode 数量 > 1500 | Operator 打开 `/robotic-data`，观察加载的 Episode 数量 | 页面能展示超过 1500 条 Episode（最多 50000 条）；分组、排序、筛选功能正常；无前端报错或性能崩溃 | P1 |
| D-20 | 选集 Chip 溢出折叠 | 选中超过 2 行能容纳数量的 Episode | 连续选中多个 Episode（直至 Chip 超过 2 行），观察右侧面板 | 超出 2 行的 Chip 折叠为 ".. N files" 汇总 Chip；所有可见 Chip + 汇总计数 = 已选总数；窗口缩放时折叠数量动态更新（无闪烁） | P1 |
| D-21 | 汇总 Chip 批量移除 | 右侧面板已出现 ".. N files" 汇总 Chip | 点击汇总 Chip 的 ✕ 按钮 | 被折叠的 N 个 Episode 全部从已选列表移除；汇总 Chip 消失；剩余可见 Chip 不受影响；Download/Batch Download 按钮状态刷新 | P1 |
| D-22 | 预览视频骨架屏加载中显示 | Episode 有 derived 视频，展开 Task 组时预览 URL 尚未返回 | 展开某 Task 组，立即观察 Episode 缩略图区域 | URL 请求期间 Episode 缩略图显示 shimmer 骨架屏；URL 返回且视频可播放前骨架屏仍显示（视频元素隐藏）；视频 `onCanPlayThrough` 触发后骨架屏消失、视频正常显示；URL 请求失败时骨架屏消失，降级为彩色色块 | P1 |
| D-23 | 已选 Episode 勾选框持久显示 | 已选中至少 1 个 Episode | 不 hover 该 Episode 卡片，观察勾选框是否可见；然后点击勾选框 | 已选 Episode 卡片在非 hover 状态下勾选框始终可见；点击勾选框后该 Episode 从已选列表中移除（不触发卡片点击事件）；其余已选 Episode 状态不受影响 | P2 |

---

### 9.3 直接下载（UI 模式）

| # | 场景 | 前置条件 | 操作 | 预期结果 | 优先级 |
|---|------|---------|------|---------|--------|
| DL-01 | 正常直接下载（1 个 Episode） | GCS 有对应 mcap + mp4 | 选中 1 个 Episode，点击 Download | 浏览器触发 `.mcap` 和对应 `.mp4` 文件下载；进度条经历 preparing → downloading → completed；历史记录新增一条 READY 记录 | P0 |
| DL-02 | 正常直接下载（10 个 Episode） | GCS 有 10 个 Episode 数据 | 选中恰好 10 个 Episode，点击 Download | 所有文件均成功下载 | P0 |
| DL-03 | 超过 10 个 Episode | 可选 Episode ≥ 11 | 选中 11 个 Episode，点击 Download | 前端拦截，弹出提示 "Direct Download is limited to 10 episodes. Use Batch Download instead."；不发网络请求 | P0 |
| DL-04 | 下载文件名与结构 | GCS 有 mcap + 多路视频，Episode 有 `episode_key` | 下载 1 个 Episode 并检查文件 | MCAP 文件命名为 `{episode_key}.mcap`；其他视频文件命名为 `{episode_key}_{baseName}`；文件大小与 `size_bytes` 相符 | P1 |
| DL-05 | 每个 Episode 文件数量 | GCS 有 3 路视频 + mcap | 下载 1 个包含 3 路视频的 Episode | 浏览器下载了 1 个 `.mcap` + 3 个 `.mp4`，共 4 个文件 | P1 |
| DL-06 | skipped_episode 场景 | 部分 Episode GCS 无 mcap | 选中含 GCS 无 mcap 的 Episode 下载 | 响应中 `skipped_episode_ids` 包含该 Episode ID；其余 Episode 正常下载；前端有 skipped 提示 | P1 |
| DL-07 | 全部 Episode 被跳过 | 所有选中 Episode 在 GCS 均无 mcap | 选中此类 Episodes，点击 Download | 后端返回 400；前端进度条转为 failed；弹出错误提示 | P1 |
| DL-08 | DB 状态流转（正常） | 有可下载 Episode | 完成一次直接下载 | DB 中 `data_downloads` 记录经历 PENDING → READY；`episode_count` 和 `total_bytes` 正确 | P0 |
| DL-09 | DB 状态流转（失败） | 触发全部跳过 | 全部跳过场景下触发下载 | DB 记录 status=FAILED，`error_message` 非空 | P1 |
| DL-10 | Signed URL 有效期 | 正常下载 | 完成下载后立即检查响应中 `expires_at` | `expires_at` ≈ 请求时间 + 7天（604800秒），误差 < 60秒 | P1 |

---

### 9.4 批量下载（Manifest 模式）

| # | 场景 | 前置条件 | 操作 | 预期结果 | 优先级 |
|---|------|---------|------|---------|--------|
| BL-01 | 正常批量下载 | 有可下载 Episodes | 选中若干 Episodes，点击 "Download manifest.json" | 浏览器下载 `manifest.json` **1 个文件**（不再同时下载 `download.py`）；成功通知 "Downloaded manifest.json."；历史记录新增一条 mode=api 的 READY 记录 | P0 |
| BL-02 | manifest.json 结构校验 | 已下载 manifest | 打开 manifest.json | 含 `manifest_version=1`；`samples[]` 非空；每个 sample 含 `assets`（mcap + 各路视频 key）；每个 asset 含有效 `url`、`relative_path`、`size_bytes` | P0 |
| BL-03 | Manifest 无数量上限 | 可选 Episode > 10 | 选中 > 10 个 Episode，点击 Batch Download | 正常生成 manifest，不报 400 | P0 |
| BL-04 | download.py 执行正确性 | manifest.json 和 download.py 已下载 | 运行 `python3 download.py --manifest manifest.json --output ./test_output` | 文件按 `upload_{id}/{episode_key}/` 目录结构下载；文件完整可读 | P1 |
| BL-05 | download.py 幂等性 | 文件已存在 | 再次运行同一命令 | 已存在文件跳过（打印 "Skipping existing file"），不重复下载 | P2 |
| BL-06 | download.py 重试逻辑 | 可 Mock URL | Mock 某文件 URL 前两次返回 500 | 脚本重试，第三次成功下载 | P2 |
| BL-07 | Manifest 过期（7天后） | manifest 已生成 7 天以上 | 用过期 manifest 执行脚本 | Signed URL 返回 403/401，脚本报错退出；提示 manifest 已过期 | P2 |
| BL-08 | DB mode 字段 | 完成批量下载 | 查询 DB | `data_downloads.mode = 'api'` | P1 |

---

### 9.5 单 Episode 下载与分享链接

**单 Episode 下载：**

| # | 场景 | 前置条件 | 操作 | 预期结果 | 优先级 |
|---|------|---------|------|---------|--------|
| SE-01 | 点击卡片下载图标 | Episode 在 GCS 有数据 | 点击 Episode 卡片下载图标 | 走与多选直接下载相同流程（POST /downloads/ui，传 1 个 episode_id）；文件正常下载 | P1 |
| SE-02 | 不影响已选列表 | 已选中其他 Episodes | 在已有选中项的情况下点击某卡片下载图标 | 只下载该卡片 Episode；右侧已选列表状态不变 | P1 |

**分享链接：**

| # | 场景 | 前置条件 | 操作 | 预期结果 | 优先级 |
|---|------|---------|------|---------|--------|
| SH-01 | 复制分享链接 | 有有效 episode | 点击 Episode 卡片分享图标 | 剪贴板内容为 `{baseUrl}/robotic-data/{episode_id}`；弹出成功提示 | P1 |
| SH-02 | 打开分享链接（存在） | episode_id 有效 | 用浏览器打开分享链接 | 页面加载后该 Episode 自动选中，所在 Task 组展开 | P1 |
| SH-03 | 打开分享链接（不存在） | episode_id 无效/已删除 | 访问含无效 episode_id 的分享链接 | 页面正常加载，无 Episode 自动选中，无报错 | P2 |
| SH-04 | 不同环境域名 | beta 和生产环境 | 在各环境复制分享链接 | beta → `https://beta-app.prismax.ai/robotic-data/{id}`；生产 → `https://app.prismax.ai/robotic-data/{id}` | P2 |

---

### 9.6 下载历史

| # | 场景 | 前置条件 | 操作 | 预期结果 | 优先级 |
|---|------|---------|------|---------|--------|
| H-01 | 历史初始加载 | 用户有历史下载记录 | Operator 登录后打开页面 | 历史列表与该用户 `data_downloads` 记录一致，按 `created_at` 倒序排列 | P1 |
| H-02 | 下载后自动刷新历史 | 完成一次下载 | 完成直接下载或批量下载 | 历史列表新增该条记录，无需手动刷新 | P1 |
| H-03 | 用户历史隔离 | 两个不同 Operator 账号均有记录 | 分别以两个账号登录查看历史 | 各自只能看到自己的下载历史，互不可见 | P0 |
| H-04 | Admin 历史隔离 | Admin 和 Operator 各有记录 | Admin 查看历史 | 只返回 Admin 的操作记录（`user_id < 0`），不包含用户记录 | P0 |
| H-05 | 历史记录字段完整性 | 有至少 1 条历史记录 | 查看历史记录详情 | 包含 `mode`（ui/api）、`status`（READY/FAILED）、`episode_count`、`total_bytes`、`expires_at`、`created_at` | P1 |
| H-06 | 越权查询历史 | 两个不同 Operator 账号 | 使用账号 A 的 token 请求账号 B 的 `?user_id={B_id}` | 后端返回 403 "user_id does not match token" | P0 |
| H-07 | 历史面板总数统计行 | 有历史记录 | 查看历史面板顶部 | 展示 "Total downloads" 标签和记录总数；空历史时总数为 0 | P1 |
| H-08 | 历史记录任务名称映射 | 有效历史记录，关联的 upload_id 在当前 Episode 列表中存在 | 查看历史记录条目 | 条目主标题显示任务 scenario 名称（如 "Pick and Place"），而非 "Upload #xxx"；左侧显示蓝色首字母图标（如 "PP"） | P1 |
| H-09 | 历史记录数据格式 badge | 任务有 data_format 字段（如 "mcap/mp4"） | 查看历史记录右侧 badge | badge 显示格式化后的格式字符串（如 `MP4+MCAP`）；无格式信息时不渲染 badge | P1 |
| H-10 | 历史记录 upload_id 无法映射时降级 | 历史记录对应的 upload 已不在当前 Episode 列表中（如数据已删除） | 查看该历史条目 | 标题降级显示 "Upload #<id>"；无格式 badge；无报错 | P2 |

---

### 9.7 Admin 端专项

| # | 场景 | 前置条件 | 操作 | 预期结果 | 优先级 |
|---|------|---------|------|---------|--------|
| A-01 | Upload Groups 列表加载 | Admin 已登录，DB 有多个 Upload | 打开 Data Download Tab | 按 `created_at DESC` 展示 Upload 分组；每组显示 `UPL-XXXX`、task scenario、machine 型号、episode 数量 | P0 |
| A-02 | 按 upload_id 批次下载 | 选中一个 Upload 分组 | 点击该分组下载 | 请求 body 使用 `selected_upload_ids`；下载该 Upload 下所有 Episodes | P0 |
| A-03 | 按 Episode 精选下载 | 在 Upload 分组内选部分 Episode | 选中分组内 2 个 Episode，点击下载 | 只下载选中的 2 个 Episode，不下载整个 Upload | P1 |
| A-04 | Admin 历史 user_id 为负数 | Admin 完成下载 | 查询 `data_downloads` 表 | 记录 `user_id = -abs(admin_id)`（负整数） | P0 |
| A-05 | Admin 与用户历史不互通 | Admin 和 Operator 均有记录 | 对比双方历史记录 | 各自历史互不可见；DB 层面通过 user_id 正负值自然隔离 | P0 |
| A-06 | Admin Upload Groups 分页首屏 | DB Upload 数量 > 24 | 打开 Data Download Tab | 首屏加载 24 个 Upload Group；底部显示 "Load more" 按钮（`has_more = true`）；页面无报错；历史记录正常加载 | P1 |
| A-07 | Admin 批量下载 | 选中多个 Upload | 点击 Batch Download | 生成的 manifest 中 `selected_upload_ids` 为选中 upload_id 列表；manifest 结构与用户端一致 | P1 |
| A-08 | Admin Load more 分页 | DB Upload 数量 > 48，已显示首屏 24 条 | 点击 "Load more" 按钮 | 新加载 24 条 Upload Group 追加到列表末尾；无重复 Upload（按 upload_id 去重）；新 Group 的 Episode 预览骨架屏正常显示；若总数 ≤ 48，"Load more" 按钮消失（`has_more = false`） | P1 |

---

### 9.8 边界与异常场景

| # | 场景 | 前置条件 | 操作 | 预期结果 | 优先级 |
|---|------|---------|------|---------|--------|
| E-01 | 未选 Episode 点击 Download | 无选中 Episode | 点击 Download 按钮 | 按钮不可点击（disabled 或点击无效），不发任何请求 | P1 |
| E-02 | Signed URL 过期后下载 | URL 已生成 7 天以上 | 7 天后使用同一 URL 下载 | 浏览器 fetch 返回 403/401；前端进度条转为 failed | P2 |
| E-03 | 直接下载时单文件 fetch 失败 | Mock 某 Signed URL 返回网络错误 | 触发多文件下载，中途某文件失败 | 该文件下载失败，进度条转为 failed，弹出错误提示；后续文件不继续下载 | P1 |
| E-04 | manifest 接口返回 500 | 后端异常 | 触发 Batch Download | 前端 Batch Download 整体失败，弹出错误提示；progress status=failed | P1 |
| E-05 | download.py 无网络环境 | 断网 | 断网后运行 download.py | 每个文件重试 3 次后失败，脚本报错退出；已下载的文件保留 | P2 |
| E-06 | Episode 有 mcap 无 mp4 | GCS 目录无 .mp4 文件 | 下载该 Episode | Episode 仍在结果中；assets 只含 mcap，无 mp4 字段；文件正常下载 | P1 |
| E-07 | Episode 无 mcap 文件 | GCS 中无 mcap blob | 下载包含此 Episode 的集合 | 该 Episode 整体被跳过，加入 `skipped_episode_ids`；其他 Episode 不受影响 | P0 |
| E-08 | 空 selected_episode_ids（API 直调） | 手动构造请求 | POST /downloads/ui，body 含空 `selected_episode_ids: []` | 后端返回 400 "selected_episode_ids or selected_upload_ids is required" | P1 |
| E-09 | 仅 DERIVED_READY 数据可见 | DB 中存在 status ≠ 'DERIVED_READY' 的 Episode | Operator 打开 `/robotic-data` | 处理中或失败状态的 Episode 不出现在列表中；只有 DERIVED_READY 的 Episode 可见 | P1 |
| E-10 | 预览视频 URL 过期（1天后） | 预览 URL 已生成超过 86400 秒 | 打开页面后 1 天再查看对应 Episode 缩略图 | 视频无法播放（GCS 返回 403/401）；降级到色块展示；重新加载页面后触发新的预览请求获取新 URL | P2 |

---

### 9.9 风险点与回归关注

以下场景在改动相关代码后，每次回归须重点覆盖：

| 风险点 | 风险原因 | 关联用例 |
|--------|---------|---------|
| **Operator 越权访问他人数据** | 后端依赖 user_id 与 token 的一致性校验，篡改请求参数即可尝试越权 | P-04、H-06 |
| **Admin JWT 双重校验** | role + 钱包白名单，任一失效会导致权限穿透 | P-07、P-09 |
| **skipped_episode 静默跳过** | 用户可能不知道部分文件未被包含在下载结果中 | DL-06、E-07 |
| **Admin 与用户历史隔离** | 依赖 user_id 正负值，若相关逻辑被修改则历史互串 | H-03、H-04、A-04、A-05 |
| **download.py Signed URL 有效期** | manifest 7天后过期，脚本失败但无显式提示让用户重新生成 | BL-07 |
| **data_downloads 状态流转** | PENDING 未转为 READY/FAILED 时历史记录展示异常 | DL-08、DL-09 |
| **前端筛选内存过滤时效性** | 筛选依赖本地 episodes 数组，接口数据不及时更新会展示旧数据 | D-10 |
| **UI 直接下载 10 个上限一致性** | 前后端均有此限制，若某一端修改而另一端未同步则行为不一致 | DL-03 |
| **admin 角色用户端访问权限同步** | 前端 `access.js` 和后端 `ROBOTIC_DATA_ALLOWED_USER_ROLES` 必须保持一致；若一端新增/删除角色而另一端未同步，将出现前端放行但后端拒绝（或反之）的问题 | P-03b |
| **DERIVED_READY 过滤引起数据不一致** | 历史上载入的 Episode 若状态不为 DERIVED_READY 将不再可见；若数据管道状态更新延迟，用户可能无法立即看到新上传的数据 | E-09 |
| **预览 URL TTL 短（1天）** | 预览 Signed URL 仅 1 天有效（与下载 URL 的 7 天不同），长时间停留在页面后视频预览会失效；需要刷新页面重新获取 | E-10 |
| **历史记录任务映射依赖 episodes 当前状态** | `uploadHistoryMetaMap` 从当前 `episodes` 数组中构建，若对应 Episode 已不在列表中（如数据被清理），历史记录任务名称会降级为 "Upload #id"，可能引起用户困惑 | H-10 |
| **LIMIT 50000 大数据量加载性能** | 单次返回最多 50000 条 Episode 时，浏览器端的分组排序（`taskRows` 构建）、筛选、状态更新可能出现性能瓶颈；若用户有超大量数据，首屏加载时间和内存占用须重点观察 | D-19 |
| **Chip 溢出降级（ResizeObserver 不支持的环境）** | 若浏览器不支持 `ResizeObserver`，折叠逻辑降级为不折叠（`resizeObserver = null`），所有 Chip 均显示；需确认目标浏览器覆盖范围 | D-20 |
| **视频骨架屏状态残留** | `episodePreviewVideoStates` 依赖 Token 失效 / 权限变更 / 数据重载等时机清空；若某路径遗漏清空逻辑，已不在列表中的 Episode key 仍留存于 state，下次该 ID 重新出现时骨架屏判断可能异常（直接跳过 `'loading'` 阶段） | D-22 |
| **批量下载命令可发现性下降** | v5.0 删除了命令展示区和"Copy command"按钮；v6.0 进一步移除了 download.py 自动下载，用户须自行获取脚本；UI 不提示运行命令，首次使用的用户可能不知如何运行脚本 | BL-04 |
| **Admin 分页列表合并去重一致性** | Load more 时前端按 `upload_id` 去重合并；若短时间内新 Upload 数据插入，`offset` 可能导致跳过部分 Upload（分页漂移）；建议刷新页面确保数据完整性 | A-08 |
| **Admin Load more `isLoadMoreBusy` 阻塞** | `isLoadMoreBusy = isLoadingMoreUploadGroups \|\| pendingLoadMorePreviewIds.length > 0`；若预览 URL 请求超时未响应，"Load more" 按钮将持续 "Loading..." 无法点击；须确保预览请求的错误处理路径能清空 `pendingLoadMorePreviewIds` | A-08 |
| **直接下载文件命名依赖 `episode_key`** | `buildBrowserDownloadFileName` 依赖 `file.episode_key` 字段；若后端某 API 返回的 `files[]` 中 `episode_key` 为空，则降级为取 `relative_path` 末段；需确认两端 `episode_key` 字段填充一致性 | DL-04 |

---

*文档基于源码截至 2026-04-23 的状态（commits：b841d0a / 7a291da / 2187a04 / 7897870 / 0c07798 / 920e863 / 424a038 / fd987ca / 5255247 / 859c117）。如代码有更新，请及时同步文档。*
