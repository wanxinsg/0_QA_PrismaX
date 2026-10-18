# PrismaX 测试策略与 E2E 测试条目

**日期**：2026-07-01
**覆盖范围**：
- `app-prismax-rp`：`eb04dded` → HEAD（含）
- `app-prismax-rp-backend`：`dd79553` → HEAD（含）

---

## 一、Commit 汇总

### Frontend — `app-prismax-rp`

| Commit | 日期 | 描述 |
|--------|------|------|
| `eb04dde` | 2026-06-30 | PRIS-264: Admin Portal 新增 Partner Device 请求表格组件 |
| `f95a41b` | 2026-06-30 | PRIS-264: VLA 侧边菜单固定（sticky）；新增 Partner Device 路由 |
| `ff6f159` | 2026-06-30 | PRIS-264: VLA 顶部子导航栏固定（sticky） |
| `5132bd9` | 2026-06-30 | PRIS-270: 修复固定顶导航栏后 Dashboard 分页圆点 z-index 问题 |
| `145c988` | 2026-06-30 | PRIS-264: Fleet 页面迁移至 Data 模块；全局路由/引用更新 |
| `0c9b455` | 2026-06-30 | PRIS-264: Fleet 页面重定向；修复 showNotification() 显示 |
| `4326c08` | 2026-06-30 | PRIS-264: 注册设备滚动布局优化；Admin Portal 布局修复；从 VLA tab 移除 Register Robot 入口 |
| `de3f808` | 2026-06-30 | PRIS-276: QA Review 页面实时同步用户 role/class |
| `6a24eff` | 2026-06-29 | PRIS-270: 应用顶导航栏固定定位 |
| `09521ba` | 2026-06-29 | Hex Metadata 结构化查询 UI；Admin 能力请求表格分页 + Excel 导出 |

### Backend — `app-prismax-rp-backend`

| Commit | 日期 | 描述 |
|--------|------|------|
| `dd79553` | 2026-06-30 | 新增 Forum 后端服务（FastAPI + Cloud SQL）；线程/评论/分类/Auth CRUD 接口 |
| `8ca1f7b` | 2026-06-30 | Forum 服务接入 Cloud SQL Postgres |
| `4d01b14` | 2026-06-30 | Forum Auth 切换为 PrismaX 用户体系 |
| `c22b4e8` | 2026-06-30 | Forum 新增媒体文件上传（GCS）；内容清洗（sanitize） |
| `63d5dbd` | 2026-06-30 | 修复 Forum 环境变量转义问题 |
| `36db4fe` | 2026-06-30 | PRIS-264: Partner Device 请求接口；Stripe Fleet 成功路径更新 |
| `c936670` | 2026-06-30 | PRIS-276: `get_qa_validator_access_data` 返回 `user_role` 和 `user_class` |
| `18dd264` / `18a2c22` / `e531fa3` | 2026-06-30 | Forum 云构建配置更新（prod/beta 媒体桶） |

---

## 二、本次变更功能模块分析

| # | 模块名称 | Ticket | 端 | 变更要点 | 涉及文件/接口 |
|---|----------|--------|----|----------|---------------|
| 1 | **应用布局 — 固定顶导航栏** | PRIS-270 | 前端 | 顶导航栏改为 `position: fixed`，全站滚动时保持可见；修复 Dashboard 分页圆点被顶导航遮挡的 z-index 问题 | `ConnectWalletHeader.module.css`<br>`Home.module.css`<br>`Dashboard.module.css` |
| 2 | **Partner Device — 用户申请侧** | PRIS-264 | 前端 | 新增 Partner Device 路由与页面；VLA 侧边菜单 / 顶部子导航栏 sticky；注册设备弹窗滚动布局优化；VLA tab 移除 Register Robot 入口 | `DataHub.js / .module.css`<br>`PartnerDevice.js`<br>`RegisterDeviceModal.js / .module.css` |
| 3 | **Partner Device — Fleet 迁移** | PRIS-264 | 前端 | Fleet 页面从独立路由迁移至 Data 模块（`/data/fleet`）；修复全局引用路径；更新 LeftPanel、MobileMenu、Home 等入口的路由指向 | `DataHub.js`<br>`Fleet/*.js`（路径迁移）<br>`LeftPanel.js`<br>`MobileMenu.js`<br>`Home.js` |
| 4 | **Partner Device — Admin 管理侧** | PRIS-264 | 前端 | Admin Portal 新增 Partner Device 请求管理表格，支持分页（每页 10 条） | `AdminPortal.js / .module.css`<br>`VLAAdminPartnerDeviceRequestsTable.js` |
| 5 | **Partner Device — 后端接口** | PRIS-264 | 后端 | 新增用户提交设备上架申请接口；新增 Admin 分页查询申请列表接口；Stripe Fleet 支付成功回调路径更新 | `POST /api/partner-device/request-listing`<br>`GET /api/admin/get-partner-device-requests`<br>`app_prismax_user_management/app.py` |
| 6 | **Hex — 元数据结构化查询** | — | 前端 | 新增 `HexStructuredLookup` 面板：支持 JSON 粘贴 / 文件拖拽输入 episode IDs，批量查询并展示聚合元数据（大小、时长等），支持下载 JSON 及推送至 Ask Hex | `HexStructuredLookup.js / .module.css`<br>`HexPanel.js / .module.css`<br>`HexChat.js`<br>`parseEpisodeIdsJson.js`<br>`api/hex.js` |
| 8 | **Hex — Admin 能力请求管理** | — | 前端 | Admin Hex Capability Requests 表格新增分页；新增 Excel 全量导出功能 | `VLAAdminHexCapabilityRequests.js`<br>`api/hexAdmin.js` |
| 9 | **QA Review — 用户角色实时同步** | PRIS-276 | 前端 + 后端 | 后端 `get_qa_validator_access_data` 接口新增返回 `user_role` / `user_class` 字段；前端 DataQAReview 在接口回调中实时比对并更新 state + localStorage，无需重新登录即可感知角色变化 | 后端：`app_prismax_data_pipeline/app.py`<br>前端：`DataQAReview.js` |
| 10 | **Forum 社区 — 全新后端服务** | — | 后端 | 独立 FastAPI 微服务（`app_prismax_forum`）；Cloud SQL Postgres 存储；GCS 媒体上传；内容 XSS 清洗；复用 PrismaX JWT Auth 体系 | `app_prismax_forum/`（全新目录）<br>接口：线程 CRUD / 草稿 / 发布 / 点赞 / 收藏<br>评论 CRUD / 点赞<br>分类列表<br>`POST /forum/images`（媒体上传）<br>`GET /forum/me`、`POST /forum/logout` |

---

## 三、测试策略

### 3.1 总体原则
1. **变更驱动**：测试范围以本次 commit 涉及的功能模块为主，回归覆盖关联的已有功能（Fleet 迁移、Auth 链路）。
2. **分层测试**：单元测试（后端接口 contract）→ 集成测试（前后端联动）→ E2E 测试（真实用户场景）。
3. **角色全覆盖**：涉及权限/角色变化的功能（PRIS-276、Admin Portal）需覆盖 `guest / user / amplifier / innovator / qa / admin` 多角色。
4. **环境**：Staging 环境执行 E2E；Production 烟雾测试验证关键路径。

### 3.2 优先级定义
| 优先级 | 说明 |
|--------|------|
| P0 | 核心用户路径，阻断发布 |
| P1 | 主要功能，发布前必须通过 |
| P2 | 非核心功能或边界场景，可跟版修复 |

### 3.3 测试范围矩阵

| 功能模块 | 单元/接口测试 | 集成测试 | E2E | 优先级 |
|----------|-------------|----------|-----|--------|
| 顶导航栏固定（PRIS-270） | — | — | ✅ | P1 |
| Partner Device 申请流程（PRIS-264） | ✅ 后端接口 | ✅ 前后端联调 | ✅ | P1 |
| Admin Partner Device 管理（PRIS-264） | ✅ 后端接口 | ✅ | ✅ | P1 |
| Fleet 页面迁移回归（PRIS-264） | — | — | ✅ | P1 |
| Hex 元数据结构化查询 | ✅ API | ✅ | ✅ | P1 |
| Admin 能力请求表格分页/导出 | — | — | ✅ | P2 |
| QA 角色实时同步（PRIS-276） | ✅ 后端接口 | ✅ | ✅ | P0 |
| Forum 线程 CRUD | ✅ | ✅ | ✅ | P1 |
| Forum 评论 CRUD | ✅ | ✅ | ✅ | P1 |
| Forum 媒体上传 | ✅ | ✅ | ✅ | P1 |
| Forum Auth（PrismaX 用户） | ✅ | ✅ | ✅ | P0 |

### 3.4 回归测试重点
- **Fleet 迁移**：原有 Fleet 链接（收藏、外部跳转）需重定向至新路径，不出现 404
- **DataQAReview**：PRIS-276 角色同步不影响现有 QA 任务的加载与提交

---

## 四、E2E 测试条目

> 说明：**前置条件**中 "已登录" 指使用对应角色账号登录 Staging 环境。

| # | 测试模块 | 测试场景 | 操作步骤 | 预期结果 | 优先级 |
|---|----------|----------|----------|----------|--------|
| **布局 — 顶导航栏（PRIS-270）** |
| 1 | 顶导航栏固定 | 任意页面向下滚动时顶部导航栏保持可见 | 1. 登录后进入 Dashboard / Data / Fleet 任意长页面<br>2. 向下滚动页面至底部 | 顶导航栏始终固定在视口顶部，不随页面滚动消失 | P1 |
| 2 | 分页圆点可点击 | Dashboard 分页圆点不被顶导航遮挡 | 1. 进入 Dashboard<br>2. 检查轮播/分页圆点区域的可见性及可点击性 | 分页圆点完整显示，点击响应正常，无被顶导航栏遮盖的情况 | P1 |
| 3 | VLA 顶部子导航 sticky | VLA 页面内容滚动时顶部子导航固定 | 1. 进入 Data > VLA 页面<br>2. 向下滚动内容区域 | VLA 顶部子导航栏固定在顶导航下方，侧边菜单同步保持可见 | P1 |
| **Partner Device（PRIS-264）** |
| 4 | 导航至 Partner Device | 从 Data 模块访问 Partner Device 页面 | 1. 登录普通用户账号<br>2. 点击左侧导航 Data<br>3. 查找 Partner Device 入口并点击 | 正确路由至 Partner Device 页面，页面无 404 / 空白 | P1 |
| 5 | 提交 Partner Device 申请 | 用户提交设备上架申请 | 1. 进入 Partner Device 页面<br>2. 填写设备序列号、名称等必填字段<br>3. 点击提交 | 提交成功，页面给出成功提示；后端 `POST /api/partner-device/request-listing` 返回 200 | P1 |
| 6 | 提交申请表单校验 | 必填字段为空时禁止提交 | 1. 进入 Partner Device 申请表单<br>2. 不填写任何内容直接提交 | 表单显示必填项错误提示，接口不发起请求 | P2 |
| 7 | 注册设备弹窗滚动 | Register Device 弹窗内容可正常滚动 | 1. 进入 Partner Device 页面<br>2. 点击注册设备按钮，弹出 RegisterDeviceModal<br>3. 在弹窗内向下滚动 | 弹窗内容可流畅滚动，底部按钮始终可见且可点击 | P1 |
| 8 | Admin 查看 Partner Device 请求列表 | Admin Portal 展示申请列表并支持分页 | 1. 使用 admin 账号登录<br>2. 进入 Admin Portal > Partner Device Requests<br>3. 存在多于 10 条数据时翻页 | 表格展示申请记录（序列号、申请人、状态等）；分页控件正常跳转，每页展示 10 条 | P1 |
| 9 | Admin 列表权限隔离 | 普通用户无法访问 Admin Partner Device 接口 | 1. 使用普通 user 账号的 token<br>2. 直接请求 `GET /api/admin/get-partner-device-requests` | 接口返回 401 / 403，无数据泄露 | P0 |
| 10 | Fleet 迁移 — 路由跳转 | Fleet 页面从旧路径重定向至新路径 | 1. 直接访问旧 Fleet URL（如 `/fleet`）<br>2. 从首页、Left Panel、MobileMenu 各入口导航至 Fleet | 均正确跳转至 `/data/fleet`（新路径），无 404；页面数据正常加载 | P1 |
| 11 | Fleet 迁移 — 购买/预约流程 | Fleet 下的购买和预约操作不受迁移影响 | 1. 进入 Data > Fleet<br>2. 选择一台机器人，点击预约/购买<br>3. 完成 Stripe 付款流程 | 支付流程正常，成功回调跳转路径正确（新 Fleet 路径） | P1 |
| 12 | VLA tab 中 Register Robot 入口已移除 | VLA 标签下不再显示注册机器人的入口 | 1. 进入 Data > VLA 页面<br>2. 查看所有 tab 和菜单项 | VLA tab 中不存在 "Register Robot" 入口；功能入口仅在 Partner Device 页面出现 | P2 |
| **Hex 元数据结构化查询** |
| 13 | JSON 粘贴查询 | 粘贴 episode ID JSON 后批量查询元数据 | 1. 登录有 Hex 权限的用户<br>2. 进入 Data > Hex 工作台，找到 Metadata Lookup 面板<br>3. 粘贴合法的 episode ID JSON（格式：`{"episode_ids": [...]}` 或数组）<br>4. 点击查询 | 查询成功，显示结构化聚合信息（总大小、总时长、条数等）；各字段格式正确（如 "1.2 GB"、"5.3 min"） | P1 |
| 14 | JSON 拖拽上传查询 | 拖拽 JSON 文件至查询面板触发查询 | 1. 准备包含 episode IDs 的 JSON 文件<br>2. 将文件拖拽至 Metadata Lookup 面板输入区域 | 文件内容自动填入输入框，查询自动触发或点击查询可正常执行 | P1 |
| 15 | 非法 JSON 输入提示 | 输入格式错误时展示解析错误 | 1. 在 Metadata Lookup 面板粘贴非法 JSON（如 `{invalid}`）<br>2. 点击查询 | 显示解析错误提示（parse error），不发起网络请求 | P2 |
| 16 | 查询结果下载 JSON | 点击下载按钮获取元数据 JSON 文件 | 1. 完成一次成功查询（见用例 13）<br>2. 点击 "Download" 按钮 | 浏览器触发 `episode-metadata.json` 文件下载，内容与页面展示一致 | P2 |
| 17 | 推送至 Ask Hex | 将查询结果添加到 Ask Hex 对话 | 1. 完成一次成功查询<br>2. 点击 "Add to Ask Hex" 按钮 | 结果内容出现在 HexChat 输入或上下文区域中，可用于后续对话 | P2 |
| 18 | Admin 能力请求表格分页 | Admin 端能力请求表每页 10 条可翻页 | 1. 使用 admin 账号进入 Admin > Hex Capability Requests<br>2. 数据超过 10 条时点击下一页 | 翻页正常，每页显示 10 条；总条数和总页数正确显示 | P2 |
| 19 | Admin 能力请求 Excel 导出 | 点击导出按钮下载 Excel 文件 | 1. 进入 Admin > Hex Capability Requests<br>2. 点击 Export 按钮 | 触发 `.xlsx` 文件下载，文件内容包含全部能力请求记录（非当页） | P2 |
| **QA 角色实时同步（PRIS-276）** |
| 20 | QA 角色变更实时生效 | 管理员在后台修改用户角色后无需重新登录即可生效 | 1. 用户 A 以 `user` 角色登录并进入 DataQAReview 页面<br>2. 管理员将用户 A 的角色改为 `qa`<br>3. 用户 A 在当前 DataQAReview 页面触发 `get_qa_validator_access_data` 接口调用（页面刷新或下一次 interval）<br>4. 观察页面功能变化 | 用户无需重新登录，页面权限实时更新为 `qa` 角色对应功能；localStorage 中 `userRole` / `userClass` 同步更新 | P0 |
| 21 | 角色未变更时不触发更新 | 角色相同时不覆盖本地状态 | 1. 用户以当前角色正常进入 DataQAReview<br>2. 调用接口返回的 role 与本地一致 | `setUserRole` / `setUserClass` 不被调用，无不必要的 re-render | P2 |
| 22 | 接口返回 user_role / user_class 字段 | 后端接口包含新字段 | 1. 以任意 QA 用户身份调用 `GET /api/qa-validator-access-data` | 响应 JSON 中包含 `user_role` 和 `user_class` 字段，值与数据库一致 | P0 |
| **Forum 社区（后端服务）** |
| 23 | Forum Auth — PrismaX 用户登录 | 使用 PrismaX JWT 访问 Forum 接口 | 1. 使用有效的 PrismaX token 请求 `GET /forum/me` | 返回 200 及当前用户信息（id、用户名等），token 验证正常 | P0 |
| 24 | Forum Auth — 未认证用户拒绝 | 无 token 访问需认证的 Forum 接口 | 1. 不携带任何认证信息请求 `POST /forum/threads` | 返回 401 Unauthorized | P0 |
| 25 | 发布 Forum 线程（普通发布） | 创建并直接发布一篇 Forum 帖子 | 1. 使用有效 token 发送 `POST /forum/threads`（`status: "published"`）<br>2. 包含标题、正文、分类 | 返回 201 及帖子详情；`GET /forum/threads` 列表中可见该帖子 | P1 |
| 26 | 创建 Forum 草稿 | 创建一篇草稿帖子 | 1. 发送 `POST /forum/threads`（`status: "draft"`） | 返回 201；草稿不在公开列表显示；`GET /forum/me/drafts` 中可见 | P1 |
| 27 | 发布草稿 | 将草稿帖子发布 | 1. 创建草稿（见用例 26）<br>2. 发送 `POST /forum/threads/{id}/publish` | 返回 200；帖子状态变为 `published`；公开列表中可见 | P1 |
| 28 | 编辑 Forum 线程 | 帖子作者可修改自己的帖子 | 1. 用创建者 token 发送 `PATCH /forum/threads/{id}`，修改标题或正文 | 返回 200，内容已更新；其他用户 token 修改同一帖子返回 403 | P1 |
| 29 | 删除 Forum 线程 | 作者删除自己的帖子 | 1. 发送 `DELETE /forum/threads/{id}` | 返回 200；`GET /forum/threads/{id}` 返回 404 | P1 |
| 30 | 线程点赞 / 取消点赞 | 对帖子进行点赞和取消点赞 | 1. 发送 `POST /forum/threads/{id}/like`（点赞）<br>2. 再次发送（取消点赞） | 第一次返回 `{liked: true}`；第二次返回 `{liked: false}`；点赞数正确增减 | P1 |
| 31 | 收藏 / 取消收藏线程 | 用户收藏和取消收藏帖子 | 1. 发送 `POST /forum/threads/{id}/save`<br>2. 再次发送取消 | 操作结果 toggle 正确；`GET /forum/me/saved` 中条目相应增减 | P2 |
| 32 | 发表评论 | 在帖子下发表评论 | 1. 发送 `POST /forum/threads/{id}/comments`，body 包含评论内容 | 返回 201 及评论详情；`GET /forum/threads/{id}/comments` 可见该评论 | P1 |
| 33 | 评论点赞 | 对评论点赞 | 1. 发送 `POST /forum/comments/{id}/like` | 返回 `{liked: true}`；评论点赞数 +1 | P2 |
| 34 | 媒体文件上传 | 上传图片至 Forum | 1. 发送 `POST /forum/images`（multipart/form-data），附带图片文件 | 返回 200 及 GCS 图片 URL；通过返回 URL 可正常访问图片 | P1 |
| 35 | 媒体上传类型校验 | 上传非图片文件被拒绝 | 1. 发送 `POST /forum/images`，附带 `.txt` 或 `.exe` 文件 | 返回 400 / 422，提示文件类型不支持 | P2 |
| 36 | 分类列表 | 获取 Forum 所有分类 | 1. 发送 `GET /forum/categories` | 返回 200 及分类列表（含分类 ID、名称等）；列表不为空 | P1 |
| 37 | Forum XSS 内容清洗 | 发帖/评论中的 XSS 脚本被过滤 | 1. 发帖正文或评论中包含 `<script>alert(1)</script>` 或 `<img onerror=...>` | 存储的内容中脚本标签被清洗或转义，返回内容中无可执行脚本 | P1 |
| 38 | Forum 线程列表分页 | 获取帖子列表支持分页参数 | 1. 发送 `GET /forum/threads?page=1&size=10`<br>2. 发送 `GET /forum/threads?page=2&size=10` | 两次返回不同的帖子集合；`total` / `pages` 字段正确 | P1 |

---

## 五、测试执行建议

1. **P0 优先**：QA 角色同步（#20、#22）、Forum Auth（#23、#24）、Admin 权限隔离（#9）应在 Staging 部署后第一批执行。
2. **前后端联调**：Partner Device（#5、#8）、Fleet 迁移（#10）、Forum CRUD（#25-#33）需前后端同时在 Staging 部署后执行。
3. **布局验证**：布局相关用例（#1-#3、#12）建议在 Chrome、Safari、移动端浏览器各执行一次。
4. **回归检查**：Fleet 迁移（#10、#11）需在 Staging 对照旧书签/深链接验证重定向，防止用户习惯路径 404。
5. **Forum 服务独立性**：Forum 后端为新服务，建议单独拉起一套独立的 smoke test，验证服务健康、Cloud SQL 连通、GCS 媒体桶可写。
