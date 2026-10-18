# prismax-marketing-rp 新 Robotics Data 与 My Data 分析

## 1. 分析范围

本文分析新前端 `prismax-marketing-rp` 中的 Robotics Data 页面及 My Data tab，覆盖：

- 页面、路由与组件结构
- Browse Datasets 主要功能
- My Data 主要功能
- 前后端接口与数据流
- 鉴权、会员与额度模型
- 当前风险和改进建议
- 构建及自动化测试现状
- 建议测试范围、测试场景和优先级

主要代码位置：

- `prismax-marketing-rp/app/robotic-data/page.tsx`
- `prismax-marketing-rp/app/robotic-data/[episodeId]/page.tsx`
- `prismax-marketing-rp/app/robotic-data/RoboticDataPageClient.tsx`
- `prismax-marketing-rp/components/robotic-data/RoboticDataWorkspace.js`
- `prismax-marketing-rp/components/robotic-data/MyDataWorkspace.js`
- `prismax-marketing-rp/components/robotic-data/HexChat.js`
- `prismax-marketing-rp/components/robotic-data/HexPanel.js`
- `prismax-marketing-rp/next.config.ts`
- `app-prismax-rp-backend/app_prismax_data_pipeline/app.py`
- `app-prismax-rp-backend/app_prismax_data_pipeline/sql/20260730_data_user_library_episodes.sql`

### 1.1 分析依据与限制

本文严格以当前仓库中的可执行代码和可执行配置为分析依据，包括：

- 当前前端页面、React 组件、工具函数与 CSS module
- 当前后端路由、鉴权、查询、额度和下载实现
- 当前数据库 migration SQL 中的表、约束和索引
- 当前 Next.js 配置、package scripts 和已有自动化测试
- 对当前代码实际执行的只读搜索、`npm test` 和 `npm run build`

以下材料不作为本文依据，本文不引用或复用其中的结论：

- `QA_PrismaX` 下的历史测试或需求分析文档
- `QA_Assistance` 下的历史页面检查文档
- 既往 Sprint、PR、测试报告或人工验收结论
- `MY_DATA_DESIGN.md` 等说明性设计文档

文中的内容分为三类：

- **代码事实**：可以从当前代码、SQL 或实际命令结果直接验证。
- **代码推导风险**：根据当前状态依赖、请求顺序和错误处理推导出的潜在行为，需要运行时测试确认。
- **建议测试/改进**：为了验证风险而提出，不表示该问题已经在运行环境复现。

## 2. 总体结论

新前端已形成较完整的数据消费链路：

```text
公开数据目录
  -> Task/Robot 筛选
  -> Episode 预览与选择
  -> Add to My Data
  -> 用户个人数据库
  -> 浏览器下载 / Manifest / API Package / API 下载
```

从当前前端调用和后端实现看，My Data 所有权、会员和额度处理能够对接：

- 当前代码没有提供删除 My Data episode 的前端操作或后端路由；有效 library row 会持续作为用户所有权记录。
- 同一 episode 重复添加不会重复消耗月度额度。
- 只有第一次加入用户 My Data 的 episode 才消耗额度。
- 会员失效后，历史 My Data 保持可读，但不能创建新的下载授权。
- UI、Manifest、API 下载最终使用统一的服务端授权逻辑。
- 下载请求支持 idempotency key，避免请求重试导致重复记录。

当前主要风险集中在 My Data 的交互语义、tab 状态保存、重复请求、跨筛选选择，以及组件体积和自动化测试覆盖不足。

## 3. 页面与路由结构

### 3.1 路由

| URL | 页面状态 | 说明 |
| --- | --- | --- |
| `/robotic-data` | Browse Datasets | 默认数据浏览页 |
| `/robotic-data?view=my-data` | My Data | 用户个人数据库 |
| `/robotic-data/:episodeId` | Browse + Episode Detail | 打开指定 episode 深链 |

`RoboticDataPageClient` 读取 `view` query 参数，并监听 `popstate`，在 Browse 和 My Data 之间同步浏览器前进、后退状态。

### 3.2 组件关系

```text
RoboticDataPage
  -> RoboticDataPageClient
       |-> EmailAccountMenu
       |-> Browse Datasets tab
       |    -> RoboticDataWorkspace
       |         |-> EpisodeDetailModal
       |         |-> HexPanel / HexChat
       |         |-> Browser Download
       |         |-> Manifest Download
       |         |-> API Access
       |         `-> Download History
       `-> My Data tab
            -> MyDataWorkspace
                 |-> Summary / Task Sidebar
                 |-> Episode Table
                 |-> Preview Player
                 `-> Direct Download
```

两个 workspace 当前采用条件渲染。切换 tab 时，离开的 workspace 会被卸载，其内部状态不会保留。

## 4. Browse Datasets 功能分析

`RoboticDataWorkspace.js` 是 Browse Datasets 的核心组件，负责：

- 加载公开 downloadable episodes
- 加载 tasks 与 machines
- Category、task、robot 筛选
- Task 展开和分批展示 episode
- Episode 视频和图片 preview 懒加载
- Episode 多选和 task 级选择
- Episode detail modal
- Episode 分享链接
- Add to My Data
- Direct browser download
- Manifest batch download
- API key 与 API package
- Download history
- Hex 推荐 episode
- 下载额度展示

### 4.1 优点

- Preview 只针对当前可见 episode 批量请求，避免首屏加载所有视频。
- 深链会自动定位 episode，展开相应 task 并打开详情。
- Direct download、Manifest 和 API package 均使用 episode ID 作为主要选择单位。
- 下载请求包含幂等键，降低重复提交导致重复计数的风险。
- Manifest 文件数量限制使用真实文件数；数据缺失时才使用估算值。
- Admin/unlimited membership 可以绕过普通 Manifest 文件上限。
- 分享地址基于当前 `window.location.origin`，beta 环境不会错误生成 production 链接。

### 4.2 工程风险

`RoboticDataWorkspace.js` 接近 3000 行，一个组件同时管理目录、筛选、preview、选择、下载、额度、API、历史和 Hex，导致：

- 状态依赖复杂，容易产生回归。
- API 请求错误处理方式不完全统一。
- 下载逻辑在 Browse 与 My Data 中重复。
- 很难为独立业务模块编写单元测试。
- UI 调整可能意外影响授权或下载状态。

建议后续拆分为：

```text
useRoboticCatalog
useEpisodeSelection
useEpisodePreviews
useDownloadQuota
useDownloadManager
useApiAccess
CatalogSidebar
EpisodeGrid
SelectionPanel
DownloadCenter
ApiAccessPanel
HistoryPanel
```

## 5. My Data 功能分析

`MyDataWorkspace.js` 负责用户个人数据管理，当前支持：

- My Data 总 episode 数
- Category/task 汇总
- Robot 汇总和筛选
- 250ms 防抖搜索
- 服务端分页
- 服务端排序
- 当前页全选
- 跨页 episode 选择
- 三路相机 preview
- Preview 同步播放、暂停、拖动和倍速
- 单 episode 下载
- 最多 10 个 episode 的浏览器下载
- Monthly quota 展示
- 会员失效后的只读模式
- 下载次数和最后加入时间展示
- 请求序号保护，避免旧响应覆盖新响应

### 5.1 My Data 数据含义

根据 migration SQL 的联合主键，以及后端所有 My Data 查询的过滤条件，`data_user_library_episodes` 中每一行表示：

```text
(user_id, episode_id) -> 该 episode 属于这个用户的 My Data
```

重要字段语义：

- `created_at`：episode 第一次加入 My Data 的时间，也是首次消耗额度的时间。
- `download_count`：成功的 UI、Manifest 或 API delivery 包含该 episode 时递增。
- `status`：目前主要使用 `ACTIVE`，为未来 archive/delete 生命周期保留。

后端 `_get_data_api_monthly_episode_usage` 通过 library row 的 `created_at` 和 billing month 计算当月使用量；`download_count` 由独立更新语句递增。因此，从当前实现可确认额度使用量不以下载次数计算。

## 6. 数据流分析

### 6.1 应用代理数据流

浏览器不直接请求 Cloud Run 或 data domain，而是请求同源代理：

```text
Browser
  -> /prismax-data/*
  -> Next.js rewrite
  -> Data Pipeline backend
```

环境选择：

```text
Local       -> http://127.0.0.1:8082
Beta        -> app-prismax-data-pipeline-beta Cloud Run
Production  -> https://data.prismaxserver.com
```

Hex 使用独立的 `/prismax-hex/*` 同源代理。

### 6.2 Browse 页面初始化数据流

```text
RoboticDataWorkspace mount
  -> GET /data/downloadable-uploads?public=1
  -> GET /data/tasks
  -> GET /data/machines
  -> normalize task/machine/episode data
  -> build task rows
  -> render sidebar and episode grid
  -> calculate visible episode IDs
  -> POST /data/downloadable-uploads/previews?public=1
  -> merge signed preview URLs into episode cards
```

公开目录加载不要求登录；下载额度、API access、历史等用户功能要求 Bearer token。

### 6.3 Episode 深链数据流

```text
GET /robotic-data/:episodeId
  -> page extracts episodeId
  -> RoboticDataPageClient passes initialEpisodeId
  -> catalog data loads
  -> find matching episode
  -> select episode
  -> expand owning task
  -> open EpisodeDetailModal
```

如果 episode 不在公开 downloadable 数据集中，当前逻辑不会显示明确的“episode 不存在或不可访问”状态。

### 6.4 Add to My Data 数据流

```text
User selects episode IDs
  -> POST /data/my-data
       Authorization: Bearer <gatewayToken>
       body: { episode_ids: [...] }
  -> backend authenticates active membership
  -> validates every episode is downloadable
  -> locks user's quota transaction
  -> splits IDs into already-owned and new
  -> checks new IDs against monthly quota
  -> inserts missing library rows
  -> returns added IDs, owned IDs and quota
  -> frontend shows result
  -> refresh current quota
```

代码事实：`_ensure_user_library_episodes` 先查询已存在的 library rows，只将缺失 episode 计入 projected usage 并插入，因此已在 My Data 的 episode 不再次消耗 quota。

### 6.5 My Data 初始化数据流

```text
Open ?view=my-data
  -> gateway token available?
       no  -> show Sign in state
       yes -> parallel requests:
               GET /data/my-data/summary
               GET /data/api-download-membership/current
  -> summary builds category/task/robot sidebar
  -> membership response sets active/inactive state
  -> select first task automatically
  -> GET /data/my-data/episodes?page=1&page_size=10&task_id=...
  -> render episode table
  -> automatically open first visible episode
  -> GET /data/downloadable-episodes/:episodeId/preview-videos
  -> render up to high/left/right preview streams
```

### 6.6 My Data 筛选与分页数据流

```text
Search input
  -> wait 250ms
  -> set normalized search
  -> reset page to 1
  -> GET /data/my-data/episodes
       ?page=
       &page_size=
       &task_id=
       &robot=
       &search=
       &sort=
       &direction=
  -> request ID check
       stale response -> discard
       latest response -> update table and pagination
```

服务端 search 当前覆盖：

- episode ID
- upload ID
- task scenario
- environment/category
- robot/product name
- My Data added date

### 6.7 My Data preview 数据流

```text
Click episode row
  -> set detail episode
  -> clear previous preview state
  -> GET /data/downloadable-episodes/:episodeId/preview-videos
  -> combine derived_videos and additional_videos
  -> map videos to high/left/right slots
  -> synchronized HTML video playback
```

并发保护使用递增 request ID 和当前 gateway token。快速切换 episode 时，旧请求返回结果会被丢弃。

### 6.8 浏览器下载数据流

```text
Select 1-10 episode IDs
  -> membership active check
  -> POST /data/downloads/ui
       user_id
       selected_episode_ids
       idempotency_key
  -> backend validates authenticated user and requested user ID
  -> auto-add missing episodes to My Data
  -> enforce quota only for missing episodes
  -> create download operation
  -> generate signed file URLs
  -> mark operation ready
  -> increment per-episode download_count
  -> frontend fetches each signed URL
  -> converts response to Blob
  -> triggers browser file download
  -> refresh episode list and quota summary
```

注意：服务端 delivery 成功和浏览器最终保存文件不是同一个原子过程。服务端返回文件后，如果浏览器下载中途失败，download history/count 仍可能已经更新。

### 6.9 Manifest 与 API 数据流

```text
Manifest:
Selected episodes
  -> POST /data/downloads/manifest
  -> auto-add missing My Data rows
  -> write manifest download history
  -> return manifest.json

API Package:
Selected episodes
  -> POST /data/api-packages
  -> auto-add missing My Data rows
  -> create reusable package mapping
  -> no download history at package creation time

API Delivery:
API key + package
  -> POST /v1/data/download-sessions
  -> validate key and package ownership
  -> ensure My Data ownership
  -> write API download history
  -> increment episode download_count
```

## 7. 鉴权、会员和额度状态

| 用户状态 | Browse public data | Preview | 查看 My Data | Add to My Data | Download | API Package |
| --- | --- | --- | --- | --- | --- | --- |
| 未登录 | 可用 | 可用 | 不可用 | 不可用 | 不可用 | 不可用 |
| 已登录、会员有效 | 可用 | 可用 | 可用 | 可用 | 可用 | 可用 |
| 已登录、会员失效 | 可用 | 可用 | 已有数据只读 | 不可用 | 不可用 | 不可用 |
| Session 失效 | 可用 | 可用 | 触发 logout/login | 不可用 | 不可用 | 不可用 |

代码事实：额度边界由后端 `_ensure_user_library_episodes` 决定。前端当前没有使用“选择数量 > remaining quota”直接拒绝请求，因为部分 episode 可能已经属于用户。

## 8. 主要问题与风险

### P1：缺少 All episodes task 入口

My Data summary 加载后自动选择第一个 task，但侧栏只有具体 task 按钮，没有清空 `taskId` 的入口。只要用户存在 task，就很难重新查看全库 episode。

建议增加明确的 `All episodes` 按钮，并显示总 episode 数。

### P1：搜索框存在双重语义

`searchInput` 同时用于：

- 过滤左侧 task 名称
- 请求服务端搜索 episode/upload/date/robot/task

输入 episode ID 时，左侧没有 task 命中，却会回退显示全部 category；右侧查询仍受当前 `taskId` 限制。用户容易误认为是在整个 My Data 中搜索。

建议拆分成两个字段：

- `Search tasks`
- `Search episodes`

或在 episode 搜索开始时自动清空 task filter，并明确展示当前搜索范围。

### P1：切换 tab 丢失 workspace 状态

Browse 和 My Data 条件渲染，切换后原组件卸载。可能丢失：

- Browse 已选 episode
- 展开的 task
- active download tab 和进度信息
- My Data task/robot/search/page
- My Data episode 选择与当前 preview

建议保留两个 workspace 的挂载状态并使用 CSS 隐藏，或将关键状态提升到页面级/store。

### P1：下载计数与客户端保存不是原子过程

后端生成 signed URLs 后已记录 delivery，但浏览器逐文件下载可能失败。大文件、网络波动或浏览器拦截多文件下载时，用户可能看到历史和 count 已更新，但本地文件不完整。

建议：

- 展示逐文件成功/失败状态。
- 支持失败文件重试。
- 明确 delivery prepared 与 browser saved 的区别。
- 对浏览器多文件下载增加提示和权限检测。

### P2：筛选可能产生重复请求

filter 改变会先触发一次 `loadEpisodes()`，随后 effect 将 page 设为 1，可能再次请求。request ID 能防止旧响应覆盖，但仍增加接口压力和 loading 闪动。

建议在 filter change handler 中同步更新 filter 与 page，或使用 reducer 管理完整 query state。

### P2：跨页 selection 缺少可见性提示

选择会跨分页和筛选保留，这是合理能力，但 UI 只显示总选择数。用户可能下载当前视图中看不到的旧选择。

建议显示：

```text
8 selected · 3 hidden by current filters
```

并增加 `Clear all` 和 `Clear hidden selections`。

### P2：自动加载每页第一条 preview

每次筛选或翻页后，页面自动打开第一条 episode 并请求视频 URL。用户只浏览表格时也会产生额外 preview 请求和网络流量。

建议仅在用户点击行时加载，或提供可配置的自动预览行为。

### P2：错误状态区分不足

Preview 失败会显示成没有 preview，未区分：

- episode 确实没有 preview
- signed URL 接口失败
- session 失效
- 视频 URL 过期
- 浏览器无法解码

建议提供不同的 empty/error/retry 状态。

### P3：UI 中存在占位数据

- `Length` 列固定显示 `—`。
- Telemetry 使用装饰曲线但显示 `Telemetry unavailable`。
- Streams 状态仅按 preview 数量估算。

建议在数据未接入前移除容易误导的展示，或明确标识为 unavailable。

### P3：组件体积和重复逻辑

Browse 和 My Data 各自维护 signed file 下载、文件名、错误处理和 session 失效逻辑，长期可能出现行为差异。

建议抽取共享的下载与授权 client。

## 9. 测试现状

当前执行：

```bash
npm test
```

结果：

```text
tests: 4
pass: 4
fail: 0
```

现有测试覆盖：

- Episode share link 保留当前 deployment origin。
- Manifest 使用真实 selected file count。
- 文件数量不可用时按每 episode 四个文件估算。
- Unlimited membership 绕过 Manifest 文件限制。

生产构建执行：

```bash
npm run build
```

当前结果：

```text
sh: next: command not found
```

原因是当前项目目录没有可用的 `node_modules`/Next.js 可执行文件。因此尚未验证：

- Next.js production build
- TypeScript 编译
- React/Next.js hydration
- CSS module production 输出
- standalone build
- 路由及 rewrite 的生产行为

## 10. 测试分析与建议

### 10.1 测试分层

建议采用四层覆盖：

| 层级 | 目标 | 建议工具 |
| --- | --- | --- |
| 纯函数单元测试 | 格式化、过滤、限制、URL、selection reducer | Node test/Vitest |
| 组件测试 | 状态、交互、loading/error/empty | React Testing Library |
| API contract/integration | 前后端 request/response、权限和额度 | Pytest + frontend mocked contract |
| E2E | 登录、选择、My Data、下载、深链 | Playwright |

### 10.2 P0 冒烟测试

以下测试应该阻断发布：

1. `/robotic-data` 能加载公开 task 和 episode。
2. 未登录用户可浏览和 preview，但下载时触发登录。
3. 有效会员可将 episode 加入 My Data。
4. 重复添加同一 episode 不重复消耗 quota。
5. `/robotic-data?view=my-data` 可直接进入 My Data。
6. My Data summary、episode table 和 quota 正确显示。
7. My Data 单 episode 下载成功。
8. 选择 10 个 episode 可以下载，选择 11 个被前端阻止。
9. 会员失效用户可以查看已有 My Data，但下载按钮禁用。
10. Session 失效后清理本地会话并打开登录流程。

### 10.3 Browse 功能测试

| 编号 | 场景 | 预期结果 | 优先级 |
| --- | --- | --- | --- |
| B-01 | 首次打开 Browse | episodes/tasks/machines 并行加载，页面正常显示 | P0 |
| B-02 | Episodes API 失败 | 显示错误，目录清空，不产生未处理异常 | P0 |
| B-03 | Tasks API 失败 | Episode 主数据仍可处理，task fallback 合理 | P1 |
| B-04 | Robot 筛选 | 仅显示对应 robot episode | P1 |
| B-05 | Category/task 多选 | 结果与选择状态一致 | P1 |
| B-06 | 展开 task/load more | 不重复、不丢 episode，最大数量正确 | P1 |
| B-07 | Preview batch 部分缺失 | 有 URL 的正常播放，缺失项显示 empty | P1 |
| B-08 | 快速切换过滤条件 | 不显示已不可见 episode 的错误 preview | P1 |
| B-09 | Episode 深链有效 | 定位、选择、展开、详情全部正确 | P0 |
| B-10 | Episode 深链无效 | 显示明确的不存在/不可访问提示 | P1 |
| B-11 | 分享链接 | 当前 beta/prod origin 正确 | P1 |

### 10.4 Add to My Data 与额度测试

| 编号 | 场景 | 预期结果 | 优先级 |
| --- | --- | --- | --- |
| D-01 | 添加一个新 episode | added=1，quota used +1 | P0 |
| D-02 | 重复添加已有 episode | already_owned=1，quota 不变 | P0 |
| D-03 | 新旧 episode 混合添加 | 只对新 episode 计费 | P0 |
| D-04 | 额度刚好够 | 请求成功，remaining=0 | P0 |
| D-05 | 超出额度 | 服务端拒绝，My Data 不发生部分写入 | P0 |
| D-06 | 两个并发添加请求 | advisory lock 防止超卖和重复计费 | P0 |
| D-07 | 非 downloadable episode | 整个请求失败并指出非法选择 | P1 |
| D-08 | 会员失效 | POST `/data/my-data` 返回 403 | P0 |
| D-09 | Token 失效 | 前端退出并重新要求登录 | P0 |

### 10.5 My Data 查询测试

| 编号 | 场景 | 预期结果 | 优先级 |
| --- | --- | --- | --- |
| M-01 | 空 My Data | 总数 0，空状态正确，无无限 loading | P0 |
| M-02 | 多 category/task | 汇总数量与 episode 总数一致 | P0 |
| M-03 | All episodes | 无 task filter，返回全部数据 | P0 |
| M-04 | Task filter | 返回指定 task 数据 | P0 |
| M-05 | Robot filter | 大小写处理正确，数量一致 | P1 |
| M-06 | 搜索 episode ID | 能在预期范围内定位 episode | P0 |
| M-07 | 搜索 upload ID | 返回对应 episode | P1 |
| M-08 | 搜索日期 | `YYYY-MM-DD` 查询正确 | P1 |
| M-09 | 搜索无结果 | 表格显示无匹配，不错误显示全量 | P1 |
| M-10 | 快速连续输入 | 只采用最后一次查询结果 | P0 |
| M-11 | 切换 filter 时位于 page > 1 | 重置 page 1，不短暂显示错误页 | P1 |
| M-12 | 最后一页删除/条件变化 | 不停留在超出 total_pages 的页码 | P1 |
| M-13 | 各排序字段 | 前端参数与后端排序一致 | P1 |

### 10.6 Selection 测试

| 编号 | 场景 | 预期结果 | 优先级 |
| --- | --- | --- | --- |
| S-01 | 单行选择/取消 | selected count 正确 | P0 |
| S-02 | 当前页全选 | 当前页 IDs 全部加入 | P0 |
| S-03 | 当前页取消全选 | 只移除当前页 IDs | P1 |
| S-04 | 跨页选择 | 翻页后旧选择保留 | P1 |
| S-05 | 切换 task/robot/search | hidden selection 有明确提示 | P1 |
| S-06 | 选择 10 个 | 下载按钮可用 | P0 |
| S-07 | 选择 11 个 | 下载按钮禁用并显示原因 | P0 |
| S-08 | 过滤后 clear all | 所有可见和隐藏选择均清除 | P1 |

### 10.7 Preview 测试

| 编号 | 场景 | 预期结果 | 优先级 |
| --- | --- | --- | --- |
| P-01 | high/left/right 全部存在 | 三路按正确 slot 显示 | P0 |
| P-02 | 只有一个视频 | 放入对应或 fallback slot | P1 |
| P-03 | 视频列表顺序随机 | 最终 slot 顺序稳定 | P1 |
| P-04 | 快速点击多个 episode | 旧请求不能覆盖最新 episode | P0 |
| P-05 | Preview API 404/500 | 显示可区分的错误和重试 | P1 |
| P-06 | Signed URL 过期 | 显示视频加载失败，不假装无数据 | P1 |
| P-07 | Play/Pause | 所有有效视频同步执行 | P1 |
| P-08 | Scrub | 三路 currentTime 同步 | P1 |
| P-09 | 0.5x/1x/2x/4x | playbackRate 全部更新 | P2 |
| P-10 | 视频时长不同 | scrub 不超出短视频 duration | P1 |

### 10.8 下载测试

| 编号 | 场景 | 预期结果 | 优先级 |
| --- | --- | --- | --- |
| DL-01 | 单 episode 多文件 | 所有文件名唯一并可保存 | P0 |
| DL-02 | 多 episode | 文件名包含 episode key，避免覆盖 | P0 |
| DL-03 | 第一个文件失败 | 显示失败，不错误报告全部完成 | P0 |
| DL-04 | 中间文件失败 | 已完成和失败文件状态可识别 | P1 |
| DL-05 | 服务器返回空 files | 显示错误，不报告成功 | P0 |
| DL-06 | 重试相同 idempotency key | 不重复记录 download operation | P0 |
| DL-07 | 新 episode 下载 | 自动加入 My Data 并消耗一次额度 | P0 |
| DL-08 | 已有 episode 下载 | quota 不增加，download_count 增加 | P0 |
| DL-09 | 浏览器阻止多文件下载 | 给出明确提示 | P1 |
| DL-10 | 大文件下载 | 内存、进度和页面响应可接受 | P1 |

### 10.9 Login、Membership 与 Limit Display 测试

当前代码中 Login 和 Membership 是两个不同门禁：

```text
gatewayToken/userId
  -> 决定用户是否登录、是否可发起用户请求
  -> GET /data/api-download-membership/current
       200 -> 读取 membership、monthly limit、used、remaining
       403 -> 已登录但没有 active data membership
       401/session expired -> 清理会话并重新登录
```

两处页面对 membership 响应的处理并不完全相同：

- Browse：额度接口成功后通过 `normalizeDownloadQuota` 转成 `ready`；任何非成功响应进入 `error`，相关 Add/Download/API Package 操作因 `quotaUnavailable` 被禁用。
- My Data：额度接口成功时显示 `used / monthly_limit`；403 明确转为 `inactive`，保留 library 查询和 preview，但下载按钮禁用。
- Browse 的 episode 统计区在有限额度且 quota ready 时显示 `selected / remaining`；未登录、loading、error 或 unlimited 时不显示 `/ remaining`。
- My Data quota card 显示的是 `used / monthly_limit`，下面显示 `remaining`，与 Browse 的 `selected / remaining` 语义不同。
- Browse 只根据 membership 字符串等于 `admin` 绕过 Manifest 文件/episode 上限；quota 是否 unlimited 则根据 `unlimited_episode_download === true` 或 `monthly_episode_limit === null` 判断。

#### Login 状态测试

| 编号 | 登录状态/响应 | Browse 预期 | My Data 预期 | 优先级 |
| --- | --- | --- | --- | --- |
| LM-01 | 无 gateway token、无 user ID | 公开目录和 preview 可浏览；用户操作触发登录；不显示 quota limit | 显示 Sign in 空状态，不请求 summary/episodes/quota | P0 |
| LM-02 | 点击 Browse 账户入口（未登录） | 调用 `requestLogin`，打开登录 modal | 不适用 | P1 |
| LM-03 | 点击 My Data Sign in | 调用 `requestLogin`，登录成功后 token 更新并开始加载 | 登录后不应残留 signed-out 页面 | P0 |
| LM-04 | 有 token 但 user ID 为空 | quota 可以请求，但下载 gate 仍要求登录；不能发送错误 user ID | My Data 可读取，但下载时重新要求登录 | P0 |
| LM-05 | 登录账号切换/token 变化 | 清空旧 summary、episodes、selection、preview 和 quota | 不得短暂显示上一账号数据 | P0 |
| LM-06 | Token 过期，membership 返回 session-expired 错误 | 调用 logout + openLogin；quota 进入 error 前不得允许下载 | 调用 logout + openLogin，不显示其他用户数据 | P0 |
| LM-07 | Token 过期，summary/episodes 返回 session-expired 错误 | 不适用 | 清理会话并回到登录状态 | P0 |
| LM-08 | 登录完成时 query 为 `view=my-data` | 保持 My Data tab | 自动加载当前账号 My Data 和 membership | P1 |
| LM-09 | Logout | 清除 Browse 用户额度/API/history 状态 | My Data 立即变为 Sign in 状态并清除缓存数据 | P0 |

#### Membership 与额度显示测试

| 编号 | Membership/API 返回 | Browse limit 显示与门禁 | My Data limit 显示与门禁 | 优先级 |
| --- | --- | --- | --- | --- |
| LM-10 | Active，limit=1000、used=100、remaining=900 | 选择 3 个时 Episodes 显示 `3 / 900`；Add/Download/API 可操作 | 显示 `100 / 1000`、`900 new episodes remaining this month`；下载可用 | P0 |
| LM-11 | Active，limit=1000、used=1000、remaining=0 | 显示 `selected / 0`；前端仍可提交，因为所选数据可能已拥有，最终由服务端判断 | 显示 `1000 / 1000` 和 `0 new episodes remaining`；已有 episode 下载仍应成功 | P0 |
| LM-12 | Active，remaining=0，选择全新 episode | 前端可提交，后端额度检查拒绝 Add/Download/API Package | My Data 中不会出现未成功加入的新 episode | P0 |
| LM-13 | Active，remaining=0，选择已拥有 episode | 服务端允许下载，不增加 used；download count 增加 | 下载成功，quota 仍为 `1000 / 1000` | P0 |
| LM-14 | Active，limit=0、used=0、remaining=0 | 显示 `selected / 0`，quota 状态仍应为 ready | 显示 `0 / 0`，进度条宽度为 0%，已有 My Data 保持可读 | P0 |
| LM-15 | Membership endpoint 返回 403 | Browse 当前实现显示 quota error，隐藏 `/ remaining`，禁用 Add/Download/API Package | 显示 `Membership: Inactive`、只读提示，所有下载按钮禁用 | P0 |
| LM-16 | Membership endpoint 返回 401/过期错误 | 触发 session-expired 流程，不能只停留在额度错误 | 触发 session-expired 流程 | P0 |
| LM-17 | Membership endpoint 返回 500 | 显示 quota error；隐藏 limit；禁用依赖 quota 的操作 | 显示 quota load error；不得错误标记为 inactive | P0 |
| LM-18 | 响应缺少 `monthly_episode_limit` | `normalizeDownloadQuota` 抛错，额度状态为 error并禁用操作 | 当前组件直接使用返回对象；应验证显示不会出现 `undefined` | P1 |
| LM-19 | `remaining_episodes` 缺失但 limit/used 有效 | Browse fallback 为 `max(limit-used, 0)` | 当前 My Data 可能显示 `undefined new episodes remaining`，应记录为契约/展示缺陷 | P1 |
| LM-20 | used 大于 limit | Browse remaining clamp 为 0，不显示负数 | 后端正常应返回 remaining=0；进度条最大为 100% | P1 |
| LM-21 | used/remaining 为字符串数字 | Browse normalization 后显示数值正确 | My Data 插值和比例计算正确 | P2 |
| LM-22 | used/remaining 为负数 | Browse normalization clamp 到 0 | 验证 My Data 不显示负数；当前代码没有显式 clamp 展示值 | P1 |
| LM-23 | Unlimited flag=true、limit=null | Browse 不显示 `/ remaining`，quota ready，普通 quota 不限制选择 | 验证 My Data 对 null limit 的实际显示；当前 UI 可能显示 `used / null` | P1 |
| LM-24 | membership=`admin` | Manifest 超过 800 files 时仍允许；其他操作继续受 quota ready 约束 | 按接口返回的 used/limit 显示，不因 admin 字符串自动隐藏 limit | P0 |
| LM-25 | membership 大小写为 `ADMIN` | Browse 使用 lowercase 比较，仍绕过 Manifest 上限 | My Data 正常显示接口额度 | P1 |
| LM-26 | membership 字符串未知但 quota 数据有效 | Browse 按有限 quota ready 处理，不应自动获得 admin 权限 | My Data 按 active 显示额度 | P1 |

#### Membership 切换与刷新测试

| 编号 | 操作 | 预期结果 | 优先级 |
| --- | --- | --- | --- |
| LM-27 | Add to My Data 成功 | Browse finally 中重新请求 membership；remaining/used 更新 | P0 |
| LM-28 | Direct download 成功或失败 | Browse finally 中刷新 quota，显示服务端最新值 | P0 |
| LM-29 | Manifest download 成功或失败 | Browse finally 中刷新 quota | P1 |
| LM-30 | My Data 下载成功 | 并行刷新 episodes 和 summary/quota；download count 与 limit 同步更新 | P0 |
| LM-31 | 用户停留页面时会员刚过期 | 下一次 membership refresh 后禁用操作；My Data 进入只读状态需要重新加载验证 | P1 |
| LM-32 | 用户续费后从 inactive 变 active | 重新请求成功后 quota card 从 Inactive 恢复 `used / limit`，下载按钮恢复 | P1 |
| LM-33 | 快速切换账号导致旧 quota 响应晚返回 | request ID/token 检查必须阻止旧账号 limit 覆盖新账号 | P0 |
| LM-34 | Browser back/forward 切换 Browse/My Data | 两个 tab 应根据各自 membership 状态显示正确 limit，不混用不同格式 | P1 |

#### Limit 显示边界与一致性检查

1. Browse 的 `selected / remaining` 必须明确第二个数字是“剩余可新增 episode”，不是月度总额。
2. My Data 的 `used / monthly_limit` 必须与下方 remaining 满足 `remaining = max(limit - used, 0)`，除非后端明确返回其他规则。
3. 额度接口处于 loading 时，不得短暂显示上一个账号的 limit。
4. 额度接口 error 时，不得显示旧 limit，也不得允许依赖额度授权的操作。
5. Inactive membership 不应显示 `0 / 0`，应显示 `Inactive`，避免被误解为有效的零额度套餐。
6. Remaining=0 不等于完全不能下载：已经属于 My Data 的 episode 仍可由服务端授权。
7. Admin 的 Manifest unlimited 与 episode quota unlimited 是两套不同判断，测试中必须分别验证。
8. Progress bar 对 limit=0、used>limit、负数和非数字响应不得产生 `NaN%`、负宽度或超过 100% 的宽度。

### 10.10 权限与安全测试

1. 修改 request body 中的 `user_id`，服务端必须拒绝访问其他用户数据。
2. 使用用户 A token 请求用户 B 的 My Data，必须只返回 token 所属用户数据。
3. 使用失效、伪造或空 Bearer token 请求 My Data，返回 401/403。
4. 非会员不能通过直接调用下载接口绕过前端禁用状态。
5. 非公开或不可下载 episode 不能通过手工 ID 加入 My Data。
6. 用户只能读取和使用自己创建的 API package。
7. Signed URL 应有合理过期时间，不应永久公开。
8. Search、sort、direction 参数必须使用白名单，防止 SQL 注入。
9. Idempotency key 不能被用于重放不同 episode selection。
10. API key secret 只在创建时完整展示，之后不能再次泄露。

### 10.11 性能测试

建议重点测量：

- 1、100、1,000、10,000 个 My Data episode 下的 summary 响应时间。
- Task/category 数量较多时侧栏渲染时间。
- 快速搜索产生的请求数，确认没有重复请求放大。
- Preview batch 大小与首屏视频请求数量。
- 三路视频同时播放时 CPU、内存和网络占用。
- 10 个 episode、多文件、大体积下载时浏览器峰值内存。
- `COUNT(*) OVER()` 分页查询在大用户 library 下的数据库成本。
- 多用户同时 Add to My Data 时 advisory lock 的等待时间。

建议性能目标：

| 指标 | 建议目标 |
| --- | --- |
| Browse catalog API P95 | < 1.5s |
| My Data summary P95 | < 800ms |
| My Data page query P95 | < 800ms |
| Search 输入到结果更新 | < 1s |
| Preview URL 获取 P95 | < 1s |
| 页面交互期间主线程长任务 | < 200ms |

### 10.12 浏览器与响应式测试

至少覆盖：

- Chrome 最新版
- Safari 最新版
- Edge 最新版
- iOS Safari
- Android Chrome

重点检查：

- 多文件下载权限差异
- Safari Blob 下载行为
- 三路视频自动播放限制
- 小屏下 sidebar、preview、table 的布局
- 表格横向滚动与固定操作区
- 键盘操作、focus 状态和 screen reader label

## 11. 建议发布门槛

发布前建议至少完成：

1. 增加 My Data 的 `All episodes` 入口。
2. 明确或拆分 task search 与 episode search。
3. 确认 tab 切换是否应该保留状态，并按产品要求实现。
4. 补充 My Data P0 组件/E2E 测试。
5. 安装依赖并通过 `npm run build`。
6. 完成 beta 环境真实账号的会员、额度和只读回归。
7. 完成 1、10、11 episode 的下载边界测试。
8. 验证重复添加、混合添加和并发添加不会重复计费。
9. 验证无效 episode 深链和 preview 失败的用户提示。
10. 验证 beta/prod rewrite 指向正确后端。

## 12. 最终评价

从当前可执行代码可以确认，新 Robotics Data 前端已串联公开目录、个人库、下载和 API 消费入口。后端代码分别实现了已拥有 episode 去重、失效会员只读查询、delivery 路径鉴权和下载计数；这些结论均来自当前路由、SQL 查询和辅助函数，而不是说明性文档。

当前版本更大的风险不是主链路缺失，而是 My Data 的筛选和状态语义不够清晰，以及缺少覆盖这些交互的自动化测试。优先解决 All episodes、搜索范围、tab 状态和下载失败反馈，再补齐 P0 E2E 与 API 额度测试后，整体发布可信度会明显提高。
