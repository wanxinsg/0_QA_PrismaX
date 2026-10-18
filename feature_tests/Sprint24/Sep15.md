# Sep 15 改动：业务逻辑、测试分析与 E2E 用例

> 日期：2026-09-15  
> 范围：9 月 15 日 Commit 分析中的第 4、5、6、8 项。  
> 本文独立于 `PRIS-326_330_ondemandorder.md`，不包含第 1、2、3、7 项。

## 1. 范围与 Commit

| 编号 | 功能域 | 仓库 | Commit |
| --- | --- | --- | --- |
| 4 | Admin Access Token 自动刷新 | `app-prismax-rp` | `990f2a4` Refresh expired admin sessions |
| 4 | Admin Refresh API | `app-prismax-rp-backend` | `3577cd2` Add admin session refresh endpoint |
| 5 | 营销站 Order 多 Organization 适配、外链及视频卡视觉调整 | `prismax-marketing-rp` | `befbd1e` updated for order；`3e78004` PRIS-333: remove grayscale gradient on video cards |
| 6 | Cloud Run Job 部署冲突重试 | `app-prismax-rp-backend` | `56f56c6` Retry conflicting Cloud Run job deployments |
| 8 | 从 Order Task 精确过滤 My Data | `prismax-marketing-rp` | `1015a0d` Filter delivered data by order task |

## 2. 总体业务影响

1. Admin Access Token 过期后，Order Admin 请求可使用 Refresh Token 静默换取新 Access Token，并自动重试原请求一次。
2. 营销站 Orders 页面支持一个内部用户访问多个 Organization；组织相关的查询和写操作均绑定当前 Organization。
3. 首页 Data 视频卡不再叠加灰度渐变；Account 页 Plans 链接改为安全的新标签打开。
4. Cloud Build 部署三个 Cloud Run Jobs 时，遇到明确的资源冲突可自动有限重试，减少并发发布导致的偶发失败。
5. 从 Order 交付进度点击某个 Task 的 “View in My Data” 后，My Data 同时按 Order 和 Task 精确过滤，而不是只按 Order 过滤。

---

## 3. 第 4 项：Admin Session 自动刷新

### 3.1 业务逻辑

#### 登录与令牌保存

- `/api/admin-login` 登录成功后必须同时返回：
  - `access_token`：Admin Access Token，有效期 30 分钟。
  - `refresh_token`：Admin Refresh Token。
- 前端所有 Admin 钱包登录分支统一调用 `applyAdminSession`：
  - 缺少任意一个 Token 时登录失败。
  - Access Token 保存到 `prismax_admin_token`。
  - Refresh Token 保存到 `prismax_admin_refresh_token`。
  - 同步更新 React 中的 Admin 登录态和 Access Token。

#### Access Token 过期后的恢复流程

```text
Order Admin API 请求
  └─ 返回 401
      ├─ localStorage 已存在另一个更新后的 Access Token
      │    └─ 直接使用该 Token 重试原请求
      └─ 当前仍是旧 Token
           └─ POST /api/admin-refresh
                Authorization: Bearer <refresh_token>
                ├─ 成功：保存新 Access Token
                │        → 触发 prismax:admin-session-refreshed
                │        → 更新 AdminPortal 内存 Token
                │        → 原请求只重试一次
                └─ 失败：清除 Access/Refresh Token
                         → 触发 prismax:admin-session-expired
                         → 退出 Admin Portal
```

- `adminRefreshRequest` 是共享中的 Promise。同一时刻多个请求收到 401 时，只发起一次 Refresh 请求，其他请求复用结果。
- 原请求最多重试一次，防止 Refresh 成功但新 Access Token 仍被服务端拒绝时产生无限循环。
- Refresh 失败、缺少 Refresh Token或重试仍为 401 时，前端清理两个 Token，并显示统一提示：`Admin session expired. Please reconnect your wallet.`

#### Refresh API 权限

`POST /api/admin-refresh` 必须同时满足：

- JWT 类型为 Refresh Token。
- Token claim `role=admin`。
- JWT identity 中存在非空钱包地址。
- 钱包当前仍在 `admin_whitelist` 中。

满足后签发新的 30 分钟 Admin Access Token；不会签发新的 Refresh Token。已被移出白名单的 Admin 即使持有历史 Refresh Token也无法续期。

### 3.2 测试分析与风险

| 风险 | 分析 | 验证重点 |
| --- | --- | --- |
| 并发 401 造成刷新风暴 | 多个组件可能同时请求 | 只允许一个 `/api/admin-refresh` 请求；其他调用复用新 Token |
| 无限重试 | 新 Token 也可能无效 | 原请求只重试一次，第二次 401 必须退出 |
| React Token 与 localStorage 不一致 | 仅更新存储会让后续组件继续使用旧 Token | `prismax:admin-session-refreshed` 必须更新 `AdminPortal` 状态 |
| Refresh 权限失效 | Admin 可能已被移出白名单 | Refresh 时重新检查 `admin_whitelist` |
| 不完整登录响应 | 旧环境可能只返回 Access Token | 前端拒绝建立不完整 Session，不进入 Admin 页面 |
| 功能覆盖范围 | 自动刷新封装在 `orderAdminApi.requestEnvelope` | 验证 Order Admin 全部 backend/data-pipeline 请求；其他 Admin API 不能假定已自动覆盖 |
| Token 泄漏 | Token 位于浏览器存储 | 登出或续期失败时必须同时删除 Access/Refresh Token；日志和错误信息不得输出 Token |

### 3.3 完整 E2E 测试用例

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| SEP15-04-001 | P0 | Admin 登录返回完整 Session | 钱包在 `admin_whitelist` | 连接钱包并完成签名登录；检查登录响应和浏览器存储 | 响应同时包含 Access/Refresh Token；两个 Token 分别保存；Admin Portal 进入登录态 |
| SEP15-04-002 | P0 | Access Token 过期后静默刷新 | Access 已过期，Refresh 有效，钱包仍在白名单 | 打开 Admin Orders 或发起 `listOrders` | 原请求先返回 401；随后仅调用一次 `/api/admin-refresh`；使用新 Access Token 重试成功；页面不退出、不丢失当前操作上下文 |
| SEP15-04-003 | P0 | Refresh Token 过期 | Access 和 Refresh 均过期 | 发起任一 Order Admin 请求 | Refresh 返回 401；两个本地 Token 被清除；触发 expired event；退出 Admin Portal并显示统一重连提示 |
| SEP15-04-004 | P0 | Admin 被移出白名单 | 登录后从 `admin_whitelist` 移除钱包；Access 过期但 Refresh 尚有效 | 再次请求 Admin Orders | `/api/admin-refresh` 返回 403；不签发新 Token；前端清理 Session并要求重新连接 |
| SEP15-04-005 | P0 | 非 Admin Refresh Token | 准备普通用户 Refresh Token | 用该 Token 调用 `/api/admin-refresh` | 返回 403 `Admin access required`；不得返回 Access Token |
| SEP15-04-006 | P1 | Access Token 代替 Refresh Token | 准备有效 Admin Access Token | 用 Access Token 调用 `/api/admin-refresh` | JWT 类型校验失败，返回 401/422；不得签发新 Token |
| SEP15-04-007 | P0 | 并发请求只刷新一次 | Access 过期；同时触发 Orders、Jobs、Invoices 等多个 `orderAdminApi` 请求 | 并发发出请求并记录网络调用 | 只出现一个 Refresh 请求；各原请求使用同一个新 Access Token各重试一次并成功 |
| SEP15-04-008 | P1 | 另一请求已完成刷新 | 请求 A 已把新 Token写入 localStorage；请求 B 使用旧 Token后收到 401 | 让 B 在 A 刷新完成后处理 401 | B 直接使用存储中的新 Token重试，不再发起第二个 Refresh 请求 |
| SEP15-04-009 | P0 | 新 Token重试仍为 401 | Mock Refresh 成功，但原接口继续返回 401 | 发起 Order Admin 请求 | 总计只执行原请求两次；随后清除 Token并退出，不发生循环 |
| SEP15-04-010 | P1 | Refresh 网络/JSON 异常 | 模拟断网、500 或非 JSON 响应 | 等待 Access 过期后发起请求 | Refresh 安全失败；不产生未处理 Promise；清除 Session并显示统一提示 |
| SEP15-04-011 | P1 | 登录响应缺 Token | Mock `/api/admin-login` 只返回 Access 或只返回 Refresh | 完成钱包签名 | 报错 `Admin login did not return a complete session.`；不得设置 Admin 登录态 |
| SEP15-04-012 | P1 | Refreshed event 同步页面状态 | Admin Portal 已挂载且持有旧内存 Token | 触发真实刷新；随后继续操作当前 Order | `AdminPortal` 接收到 refreshed event并更新 Access Token；后续请求不再携带旧 Token |
| SEP15-04-013 | P1 | 登出清理回归 | Admin 已完成一次 Token刷新 | 主动退出或触发 expired event | Access/Refresh Token及 Admin 内存态都被清除；刷新浏览器后不会自动恢复失效 Session |

---

## 4. 第 5 项：营销站 Orders 同步与视觉调整

### 4.1 多 Organization Orders 业务逻辑

- Orders Workspace 首先调用 `GET /api/organizations` 获取当前用户全部可访问 Organization。
- 无可访问 Organization：清空 Organization、Orders、Invoices并进入 `organization_required` 状态。
- 只有一个 Organization：自动选择，不展示切换器。
- 多个 Organization：默认选择访问列表第一项，并显示 Organization 下拉框。
- 切换 Organization 时：
  - 清空当前选中的 Order。
  - 清空编辑中的 Order。
  - 返回 Order 列表视图。
  - 使用新 `organization_id` 重新请求 Organization、Orders 和 Invoices。
- 创建 Order 时在 payload 中传 `organization_id`。
- 邀请成员、撤销邀请、移除成员均携带当前 `organization_id`，防止操作落到错误 Organization。
- Organization `is_internal=true` 时，标题区域显示 `Internal PrismaX access`。
- `is_owner=true` 才显示 Manage access 和 New order；Internal Owner 是否可操作由后端返回的权限字段决定。

### 4.2 其他营销站改动

#### Account Plans 链接

- `Compare every plan in detail` 仍指向 `/#plans`。
- 改为 `target="_blank"`，在新标签页打开。
- 使用 `rel="noopener noreferrer"`，避免新页面获取 opener。

#### 首页视频卡

- `.media::after` 的灰度渐变覆盖层被移除，`content: none`。
- 视频/图片原始色彩应直接呈现。
- 不能影响卡片点击、播放控制、文字可读性、hover 或布局。

### 4.3 测试分析与风险

| 风险 | 分析 | 验证重点 |
| --- | --- | --- |
| 跨 Organization 数据混用 | 多个请求并行加载，切换可能与旧请求竞态 | Orders/Invoices/Team 始终与当前 Organization 一致；快速切换不残留旧数据 |
| 写操作作用到错误组织 | 过去接口依赖隐式单 Organization | Create/Invite/Revoke/Remove 都检查请求中的 `organization_id` |
| 单 Organization 回归 | 新逻辑增加访问列表请求 | 单 Organization 自动进入且无多余切换器 |
| Internal Owner UI 泄漏 | 内部访问需要标识，但客户成员列表不应暴露内部账号 | 仅当前内部用户看到 access 标记；Team 数据遵循后端隐藏规则 |
| 新标签安全 | `target=_blank` 可能引入 opener 风险 | 必须同时包含 `noopener noreferrer` |
| 移除渐变影响可读性 | 原覆盖层可能提升对比度 | 多分辨率、暗/亮视频帧下检查文字与交互 |

### 4.4 完整 E2E 测试用例

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| SEP15-05-001 | P0 | 多 Organization 初始加载 | 用户可访问 A、B；两边各有不同 Orders/Invoices | 登录并进入 `/robotic-data?view=orders` | 调用 `/api/organizations`；默认选择第一项；显示 Organization 下拉；只加载默认组织的数据 |
| SEP15-05-002 | P0 | Organization 切换 | 当前选择 A，已打开或正在编辑 A 的 Order | 下拉选择 B | 当前详情和编辑态清空，返回列表；请求携带 B ID；只显示 B 的 Organization、Orders、Invoices |
| SEP15-05-003 | P0 | 快速连续切换隔离 | A/B/C 响应速度不同 | 快速执行 A→B→C | 最终页面只显示 C；较晚返回的 A/B 响应不能污染当前视图 |
| SEP15-05-004 | P1 | 单 Organization | 用户只可访问 A | 进入 Orders | 自动选择 A并正常加载；不显示 Organization switcher |
| SEP15-05-005 | P0 | 无 Organization | `/api/organizations` 返回空数组 | 进入 Orders | 显示联系 PrismaX/Organization required 提示；Organization、Orders、Invoices 均清空；不能创建 Order |
| SEP15-05-006 | P0 | 越权 Organization ID | 用户只可访问 A | 修改请求为 B 的 `organization_id` | 后端返回 403/404；页面不展示 B 的名称、成员、Order 或 Invoice |
| SEP15-05-007 | P0 | 在选中 Organization 创建 Order | 用户是 A/B Owner，当前选择 B | 创建 Draft和直接 Submit各一次 | payload 含 B ID；两条 Order 均只出现在 B，不出现在 A |
| SEP15-05-008 | P0 | Team 写操作按 Organization 隔离 | 当前选择 B；B 有 Member和 Invitation | 创建邀请、撤销邀请、移除成员 | 每个请求携带 B ID；只修改 B；A 的成员和邀请不变 |
| SEP15-05-009 | P1 | Internal access 标识 | 用户以 Internal Owner访问 A | 进入 A Orders | Organization 副标题显示 `Internal PrismaX access`；权限按钮与后端 `is_owner` 一致 |
| SEP15-05-010 | P1 | Gateway Token变化重置状态 | 用户先登录多组织账号并选 B | 更换/清除 gateway token | 已选 Organization、列表、详情、编辑态重置；新账号不得看到旧账号数据 |
| SEP15-05-011 | P2 | Plans 新标签链接 | 打开 Account Plan区域 | 点击 `Compare every plan in detail` | 新标签打开 `/#plans`；原 Account 页保留；元素含 `target=_blank` 和 `rel="noopener noreferrer"` |
| SEP15-05-012 | P2 | 视频卡无灰度覆盖层 | 首页存在 DataSection 视频卡 | 检查暗色、亮色、彩色视频并触发 hover/播放 | `.media::after` 不生成覆盖内容；画面无灰度渐变；布局、点击和播放功能不变 |
| SEP15-05-013 | P2 | 视频卡响应式回归 | 桌面、平板、移动端视口 | 浏览 DataSection并滚动/播放 | 无覆盖层残留、闪烁或层级遮挡；卡片尺寸及圆角正常 |

---

## 5. 第 6 项：Cloud Run Job 部署冲突重试

### 5.1 部署逻辑

Cloud Build 中以下三个部署步骤由直接执行 `gcloud run jobs deploy` 改为通过 Bash 包装脚本：

- `${_MCAP_GRAPH_BACKFILL_JOB}`
- `${_PREVIEW_TASK_BACKFILL_JOB}`
- `${_PREVIEW_SELECTION_JOB}`

包装脚本 `scripts/deploy_cloud_run_job.sh`：

1. 原样透传 Job 名称和所有 `gcloud run jobs deploy` 参数。
2. 每次执行将 stdout/stderr 写入临时日志，并打印前 240 行。
3. 成功则立即以 0 退出。
4. 仅当日志包含精确文本 `ABORTED: Conflict for resource` 时重试。
5. 最多尝试 5 次；第 1～4 次冲突后分别等待 5、10、15、20 秒。
6. 非冲突错误立即返回原始非零状态，不重试。
7. 第 5 次仍冲突时返回第 5 次的非零状态，Cloud Build失败。
8. 脚本退出时删除临时日志。

这些步骤仍然只负责部署定义：不会执行 Cloud Run Job，也不会创建 Scheduler trigger；历史 backfill 仍需人工触发。

### 5.2 测试分析与风险

| 风险 | 分析 | 验证重点 |
| --- | --- | --- |
| 误重试永久错误 | 权限、参数、镜像错误无法靠等待恢复 | 只有精确 Conflict 文本可重试，其他错误一次即失败 |
| 无限等待 | 并发更新可能长期存在 | 固定最多 5 次，总退避 50 秒 |
| 参数丢失 | 包装脚本位于 gcloud 前 | Job 名称、image、region、service account、memory、timeout 等必须原样转发 |
| 日志不可诊断 | 输出被临时文件捕获 | 每次尝试均打印最多 240 行；最终退出码保留 |
| 临时文件泄漏 | Build 容器中多次运行 | 正常和异常退出均由 trap 清理 |
| 发布后误执行 backfill | Deploy 与 Execute 含义不同 | 验证 Build 只更新 Job配置，不出现 `gcloud run jobs execute` |
| 覆盖范围误解 | 只有三个指定 Cloud Run Job 使用包装脚本 | 其他 Cloud Run 服务/Job 部署不自动获得此重试能力 |

### 5.3 完整流水线 E2E/集成测试用例

> 建议在临时 Cloud Build 项目或用可记录调用的 `gcloud` stub 执行，避免测试误改生产 Job。

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| SEP15-06-001 | P0 | 首次部署成功 | Stub `gcloud` 第一次返回 0 | 运行脚本并传完整 deploy 参数 | 仅调用一次 `gcloud run jobs deploy`；参数完全一致；脚本返回 0 |
| SEP15-06-002 | P0 | 一次冲突后成功 | 第一次返回非零且含 Conflict文本，第二次成功 | 运行脚本并记录时间/调用 | 调用两次；第一次后等待约 5 秒；输出重试提示；最终返回 0 |
| SEP15-06-003 | P1 | 多次冲突后成功 | 前四次 Conflict，第五次成功 | 运行脚本 | 共调用 5 次；等待序列为 5/10/15/20 秒；最终返回 0 |
| SEP15-06-004 | P0 | 五次均冲突 | 每次返回同一 Conflict错误码 | 运行脚本 | 只尝试 5 次；第 5 次后不再 sleep；返回最后一次非零状态，Build失败 |
| SEP15-06-005 | P0 | 非冲突错误立即失败 | 返回权限拒绝、镜像不存在或参数错误，日志不含目标 Conflict文本 | 运行脚本 | 只调用一次；无 retry提示和 sleep；保留原始错误码 |
| SEP15-06-006 | P1 | 相似但不完全匹配的错误 | 返回包含 `Conflict` 但不含精确字符串的错误 | 运行脚本 | 不重试，避免宽泛匹配掩盖其他故障 |
| SEP15-06-007 | P1 | stdout/stderr 日志输出 | 每次生成可识别日志 | 制造一次失败后成功 | 每次尝试日志都被输出；敏感环境变量不被脚本额外打印；最终状态正确 |
| SEP15-06-008 | P2 | 超长日志截断 | Stub 输出超过 240 行 | 运行脚本 | 每次只打印前 240 行，但退出码和 Conflict识别仍基于完整日志文件 |
| SEP15-06-009 | P1 | 临时文件清理 | 可检查临时目录 | 分别执行成功、非冲突失败、5 次冲突失败 | 三种退出路径都不遗留 `deploy_log` 临时文件 |
| SEP15-06-010 | P0 | 三个 Cloud Build Job均采用包装脚本 | 使用修改后的 `cloudbuild.yaml` | 启动非生产 Build或静态检查解析后的步骤 | MCAP graph backfill、Preview task backfill、Preview selection全部经脚本部署；各自 image/region/资源参数保持不变 |
| SEP15-06-011 | P0 | 不自动执行 Job | 完成一次成功 Build | 查看 Cloud Build和 Cloud Run执行历史 | Job配置更新，但没有新增 Job execution，也没有新增 Scheduler trigger |
| SEP15-06-012 | P1 | Backend prefix兼容 | `_BACKEND_PREFIX` 分别为空和合法子目录前缀 | 构建对应源码布局 | Bash 能找到 `${_BACKEND_PREFIX}scripts/deploy_cloud_run_job.sh`，三个步骤均可执行 |

---

## 6. 第 8 项：Order Task → My Data 精确过滤

### 6.1 业务逻辑

旧行为只把 Order ID传给 My Data，因此用户点击某个 Order Task后会看到该 Order下所有 Tasks 的 Episode。新行为把 Order和 Task同时传递：

```text
Order Detail → 点击某个 catalog Task 的 View in My Data
  → onOpenMyDataForOrder(orderId, taskId)
  → URL: /robotic-data?view=my-data&source=<ORD-id>&task_id=<positive-int>
  → MyDataWorkspace:
       selectedSources = [ORD-id]
       taskId = <task_id>
       page = 1
       selectedIds = []
  → 结果只包含该 Order、该 Task 的 Episodes
```

- 页面首次加载或浏览器刷新时，会从 URL恢复 `source` 和 `task_id`。
- `task_id` 只有在转换后为正整数时才生效；无效值转为 `null`，仍可保留 Order Source过滤。
- 每次收到新的 Source/Task请求时重置分页并清除已选 Episode，避免把旧筛选下的选择带到新结果。
- 离开 My Data section时，同时从 URL删除 `source` 和 `task_id`。
- Custom Order Item 的 `task_id=null`，点击处理受到保护，不会发起带无效 Task的跳转。

### 6.2 测试分析与风险

| 风险 | 分析 | 验证重点 |
| --- | --- | --- |
| 只恢复 Order、不恢复 Task | 深链接刷新后可能扩大结果范围 | 首次加载解析两个参数并同时设置过滤器 |
| 非法 Task ID | `Number()` 对空字符串和小数有特殊行为 | 只接受正整数；0、负数、小数、文本都不能成为 Task过滤 |
| 旧选择污染新过滤 | 用户可能已经选中其他 Episode | 切换请求后 `selectedIds=[]`、`page=1` |
| URL 残留 | 离开 My Data后旧参数可能在返回时再次触发 | 切到 Browse/Orders时同时删除 source/task_id |
| Order/Task 不匹配 | 用户可手改 URL | 返回空态或由后端权限过滤，不得回退显示其他 Task数据 |
| Custom Task 无 catalog ID | 无法用 task_id精确查询 | 不应构造 `task_id=null/undefined`；UI应无动作或明确提示 |
| 自动化测试深度 | Commit附带测试是源码正则断言 | 仍需浏览器和真实 API E2E验证 URL、状态与结果集 |

### 6.3 完整 E2E 测试用例

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| SEP15-08-001 | P0 | 从 Order Task精确进入 My Data | Order A ≥delivering，Task 10/20 均有 Episodes | 打开 A详情；点击 Task 10的 View in My Data | 进入 My Data；URL含 `view=my-data&source=<A>&task_id=10`；Source只选 A、Task只选 10；结果无 Task 20 Episode |
| SEP15-08-002 | P0 | 同一 Order切换不同 Task | 完成上一用例 | 返回 A详情并点击 Task 20 | URL改为 Task 20；分页回到 1；旧选中项清空；结果只含 A/Task 20 |
| SEP15-08-003 | P0 | 深链接刷新恢复 | 准备有效的 A/Task 10 URL | 直接粘贴 URL并刷新浏览器 | My Data自动打开；Order Source和 Task过滤均恢复；结果范围与从按钮进入一致 |
| SEP15-08-004 | P1 | 浏览器前进/后退 | 依次访问 A/Task 10、A/Task 20和 Orders | 使用浏览器 Back/Forward | 每个历史 URL恢复对应 section/source/task；不出现筛选与 URL不一致 |
| SEP15-08-005 | P0 | 切换过滤时清空选择 | A/Task 10有多页数据，已在第 2 页选择 Episodes | 点击 A/Task 20入口 | 页码重置为 1，已选数量为 0；下载请求不得包含 Task 10的旧 ID |
| SEP15-08-006 | P1 | 缺少 task_id | 访问 `view=my-data&source=A` | 加载页面 | 只按 A过滤；Task过滤为空；页面不崩溃，保持旧深链接兼容性 |
| SEP15-08-007 | P1 | 非法 task_id | 分别使用 `0`、`-1`、`1.5`、`abc` | 逐个直接访问 URL | 非法值不设置 Task过滤；不发出错误 Task查询；Source A仍按权限正常处理 |
| SEP15-08-008 | P0 | Order与Task不匹配 | Task 20不属于 Order B | 访问 `source=B&task_id=20` | 显示空结果或后端许可范围内的 B/20交集；不得显示 A/20或 B的其他 Task |
| SEP15-08-009 | P0 | 越权 Order Source | 当前用户无权访问 Order C | 访问 `source=C&task_id=10` | 返回空态或 403；不得泄漏 C的 Episode数量、预览或元数据 |
| SEP15-08-010 | P1 | Custom Task无 task_id | Order含 `task_id=null` 的 Custom Item | 点击该行或检查入口状态 | 不调用 `onOpenMyDataForOrder`，URL不出现 `task_id=null/undefined`；当前页面状态不被破坏 |
| SEP15-08-011 | P1 | 离开 My Data清理 URL | 当前 URL含 source和 task_id | 切换到 Browse，再切换到 Orders | 两次目标 URL均不再包含 source/task_id；Orders的 invite参数规则不受影响 |
| SEP15-08-012 | P1 | 新请求 revision相同字段重触发 | 先在 My Data手动修改过滤和选择，再从同一个 Order Task再次点击入口 | 重复点击同一 A/Task 10 | revision更新并重新应用 A/10；页码和选择再次重置 |
| SEP15-08-013 | P1 | 多 Organization同 ID范围隔离 | Internal Owner可访问 A/B，两边包含相同 Task ID | 在 A和B中分别点击 Task 10 | 每次 Source绑定对应 ORD；结果不能因 Task ID相同而跨 Organization混合 |
| SEP15-08-014 | P2 | 静态自动化回归 | 安装项目测试依赖 | 执行 `node --test tests/orderTaskNavigation.test.mjs` | 两个源码契约测试通过：点击传 Order+Task；深链接恢复两种过滤 |

---

## 7. 跨功能回归场景

| ID | 优先级 | 场景 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- |
| SEP15-CROSS-001 | P0 | Admin续期不影响营销站用户 Session | 同一浏览器分别准备 Admin和普通 gateway session；触发 Admin Access刷新 | 只更新 Admin Token；普通用户登录态、Organization选择和 My Data过滤不变 |
| SEP15-CROSS-002 | P0 | 多 Organization Order Task闭环 | Internal Owner在 A/B间切换；分别打开每个组织的 Order Task到 My Data | URL、Source、Task和结果集始终对应当前 Order；无跨组织数据 |
| SEP15-CROSS-003 | P1 | Session刷新期间执行 Organization请求 | Admin Access刚过期时触发多个 Order Admin请求，同时营销站切换 Organization | Admin请求共享刷新并成功；营销站请求使用自己的 gateway token，不被 Admin事件登出 |
| SEP15-CROSS-004 | P1 | Cloud Build部署后冒烟 | 使用新脚本成功部署后端 Jobs和包含 4/5/8 的前端 | Admin Refresh、多 Organization Orders、Order Task过滤均通过核心 P0冒烟；部署过程未执行 backfill Jobs |

## 8. 测试数据与环境准备

- 两个客户 Organization：A、B。
- 一个可访问 A/B 的 Internal Owner，一个仅属于 A 的普通 Owner，一个 A Member。
- A、B 各至少一个 `delivering` 或更后状态的 Order。
- 每个 Order至少两个 catalog Tasks；每个 Task至少 3 条可见 Episode。
- 一个含 `task_id=null` 的 Custom Order Item。
- 一个白名单 Admin钱包，以及可在测试中移出白名单的 Admin钱包。
- 可生成短期/已过期 Access Token、有效/已过期 Refresh Token的测试环境。
- Cloud Run重试测试使用隔离 GCP项目或 `gcloud` stub，禁止用生产 Job制造冲突。
- 桌面和移动端浏览器各一套；允许检查 Network、localStorage和 URL History。

## 9. 发布准入标准

- [ ] 第 4 项所有 P0用例通过；并发 401只发起一次 Refresh，失败后 Token完整清理。
- [ ] 明确记录自动刷新仅覆盖 `orderAdminApi` 的范围；未接入模块保留原登录过期处理。
- [ ] 第 5 项所有 P0用例通过；Organization切换和写操作无跨租户污染。
- [ ] Plans新标签安全属性及视频卡桌面/移动端视觉回归通过。
- [ ] 第 6 项所有 P0用例通过；只重试精确 Conflict，最多 5次且不执行 Job。
- [ ] 第 8 项所有 P0用例通过；Order和Task过滤同时生效，越权和不匹配组合不泄漏数据。
- [ ] `tests/orderTaskNavigation.test.mjs` 和现有 `orderAdminApi.test.js` 通过。
- [ ] 四条跨功能回归至少完成 P0项，且无 Session、Organization或数据筛选互相污染。

