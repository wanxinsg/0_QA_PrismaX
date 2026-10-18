# PRIS-268 Account Page Upgrade - 前后端改动梳理与 E2E 测试用例

## 一、分析范围

### 前端仓库

仓库：`app-prismax-rp`

涉及提交：

| Hash | 日期 | Commit Message | 说明 |
|---|---|---|---|
| `df6e36af13ccf37426c040cdf674e70676189730` | 2026-07-02 | `updated for account page` | 初版 Account Page upgrade，新增 API Keys 管理能力 |
| `3d89421468740c7149e0f12b666040dc2ec97837` | 2026-07-03 | `updated ui` | 当前 repo 实际 UI：API Keys 按 role group 展示，不使用 tab |

涉及文件：

- `src/components/Account/Account.js`
- `src/components/Account/Account.module.css`

### 后端仓库

仓库：`app-prismax-rp-backend`

备注：上述前端提交没有直接修改后端代码，但 Account Page 依赖 user management 与 data pipeline 的现有接口。

---

## 二、一句话主线

Account Page 从原来的个人资料 + 会员升级展示，升级为更完整的账户控制台：新增按角色分组的 API Keys 管理区、重做 Community Membership 卡片、优化 Twitter/Discord 链接展示，并基于用户角色控制 Subscriber(download) 与 Operator(upload) key 的查看、创建、撤销权限。

---

## 三、前端改动逻辑

## 3.1 页面布局与视觉升级

核心变化：

- Account 页面主体宽度扩大，整体卡片化。
- `Personal Info`、`Community`、`API Keys` 区域改为统一深色卡片风格。
- 引入 `lucide-react` 图标，包括 `Key`、`Plus`、`Copy`、`Download`、`Gamepad2`、`UsersRound` 等。
- 新增内联 `TwitterXIcon` 与 `DiscordIcon`，替代旧的文字式 OAuth 按钮。
- 移除旧 check-circle 图片依赖，会员权益和状态统一用 icon + CSS 表达。
- 移动端下 Personal Info、Community、API Keys 纵向排列，按钮和 key reveal 区域自适应宽度。

## 3.2 Personal Info 区域

保留既有能力：

- 加载用户资料：`GET /api/get-users`
- 编辑并保存用户名、profile email、telegram、phone：`POST /api/update-user-info`
- email login 用户编辑态下 email 只读。
- wallet 用户修改 profile email 时，如果 email 发生变化，会打开 `EmailVerificationModal`。
- email + wallet 同时存在时，可点击 unlink wallet。

新增/优化点：

- 从 `get-users` 返回中读取 `user_role`，同步到 `userRoleValue`，用于 API Keys 权限判断。
- Twitter / Discord 从按钮升级为 icon tile：
  - 未链接：社交 icon + `Plus` 小徽标。
  - 已链接：社交 icon + `Check` 小徽标、账号名、`Unlink`。
- Twitter OAuth 回跳 query 参数仍会处理并清理：`twitter_status`、`twitter_reason`、`twitter_username`。

## 3.3 Community Membership 区域

旧版 `membershipSection / membershipBox` 被新版 `renderCommunityMembershipSection()` 替代。

会员层级：

| Tier | Rank | 当前态表现 | 非当前态表现 |
|---|---:|---|---|
| Explorer | 0 | `CURRENT`，绿色 Explorer 卡 | 高级会员下显示 `Included` |
| Amplifier | 1 | `CURRENT`，展示 `Activated · paid $99` | Explorer 可看到 `$99 one-time initiation fee` 与 `Upgrade - $99` |
| Innovator | 2 | `CURRENT`，展示 `Activated · paid $399` | Explorer/Amplifier 可看到 `$399 one-time initiation fee` 与 `Upgrade - $399` |

升级按钮仍打开 `UpgradeMembershipModal`。升级成功关闭 modal 后会重新调用 `fetchUserInfo()` 刷新会员等级。

## 3.4 API Keys 管理区

当前 repo 的 API Keys 区域**没有 tab**，而是同时渲染两个 role group：

| Group | 类型 | 标识 | Scope | 图标 | 说明 |
|---|---|---|---|---|---|
| Subscriber | download API key | `DOWNLOAD` + `Researcher plan` | `episodes:read` | `Download` | Download episode data to train models |
| Operator | upload API key | `UPLOAD` | `episodes:write` | `Gamepad2` | Upload episodes from teleoperation stations |

新增状态：

- `uploadApiKeys` / `downloadApiKeys`
- `isLoadingUploadApiKeys` / `isLoadingDownloadApiKeys`
- `isCreatingUploadApiKey` / `isCreatingDownloadApiKey`
- `revokingUploadApiKeyId` / `revokingDownloadApiKeyId`
- `newUploadApiKey` / `newDownloadApiKey`
- `hasFetchedUploadApiKeysRef` / `hasFetchedDownloadApiKeysRef`

权限规则：

| 用户角色 | Subscriber/download group | Operator/upload group |
|---|---|---|
| `operator` | 可查看、创建、撤销 | 可查看、创建、撤销 |
| `admin` | 前端允许查看、创建、撤销 | 不可管理，显示无权限提示 |
| 其他 / 空角色 | 不可管理，显示无权限提示 | 不可管理，显示无权限提示 |

前端行为：

- 页面中同时展示 Subscriber 与 Operator 两个 group，不需要切换 tab。
- 有权限且页面加载完成后，分别拉取对应 key list。
- Subscriber group 展示静态 quota strip：`500 GB / mo`、`210 GB`、`100 req/min`，并提供 `Upgrade plan ->` 入口。
- list 只展示 `status === ACTIVE` 的 key。
- key row 展示：状态点、`apiKey.name || "{type}-key"`、`key_prefix...`、`last used ...`、`Revoke`。
- key secret 只在创建成功后以 `New subscriber/operator API key` 形式显示一次。
- 点击 Copy 使用 `navigator.clipboard.writeText()`。
- 点击 Revoke 成功后从当前 group 列表移除。

---

## 四、后端接口依赖

## 4.1 User Management 接口

| 接口 | 方法 | 使用场景 | 关键入参 | 关键返回/行为 |
|---|---|---|---|---|
| `/api/get-users` | GET | Account 页面初始化获取用户资料 | `email` 或 `wallet_address`、`chain`、`recaptcha_token`、`Authorization` | 返回 `user_name`、`user_class`、`user_role`、profile email、Twitter/Discord、phone、linked wallet 等 |
| `/api/update-user-info` | POST | 保存 Personal Info | `email` 或 `wallet_address`、`user_name`、`telegram_id`、`phone_number`、`user_profile_email`、`chain` | 成功后前端更新本地展示 |
| `/api/disconnect-wallet-from-email` | POST | email 用户解绑 wallet | `email`、`wallet_address`、`chain` | 成功后清理 wallet localStorage 并 reload |

## 4.2 Data Pipeline API Key 接口

| 接口 | 方法 | 权限 | 页面 group | 返回/行为 |
|---|---|---|---|---|
| `/data/api-keys` | GET | robotic data user | Subscriber | 返回当前用户 download keys，含 `api_key_id`、`key_prefix`、`status`、`last_used_at` |
| `/data/api-keys` | POST | robotic data user | Subscriber | 创建 download API key，返回完整 `api_key`，仅创建后展示一次 |
| `/data/api-keys/{api_key_id}` | DELETE | robotic data user | Subscriber | 将 download key 置为 `REVOKED` |
| `/data/upload-api-keys` | GET | `operator` | Operator | 返回当前用户 upload keys，含 `upload_api_key_id`、`key_prefix`、`status`、`last_used_at` |
| `/data/upload-api-keys` | POST | `operator` | Operator | 创建 upload API key，返回完整 `api_key`，仅创建后展示一次 |
| `/data/upload-api-keys/{upload_api_key_id}` | DELETE | `operator` | Operator | 将 upload key 置为 `REVOKED` |

---

## 五、风险点与关注点

| 风险点 | 说明 | 建议验证 |
|---|---|---|
| 前端角色判断与后端权限文案不完全一致 | 前端 download 权限判断是 `operator || admin`，后端是 `_require_robotic_data_user()`；若 robotic data user 不等于这两个角色，可能出现前端禁用但后端允许，或前端允许但后端拒绝 | 用 operator/admin/普通用户分别验证接口返回与 UI 一致性 |
| API Keys 没有 tab | 两个 group 同屏展示，E2E 不应写成 tab 切换 | 验证 Subscriber 与 Operator 两个卡片都存在 |
| Subscriber quota 是静态展示 | 当前代码写死 `500 GB / mo`、`210 GB`、`100 req/min` | 验证 UI 文案，不把 quota 当作真实后端联动 |
| 新 key 只展示一次 | 创建后如果刷新页面，完整 secret 不会再出现 | 验证创建成功时 copy 可用，并确认刷新后只展示 prefix |
| 只显示 ACTIVE keys | list 过滤掉 `REVOKED`，撤销后应立即消失 | 验证撤销后 UI 与接口状态一致 |
| fetch 只执行一次 | `hasFetched*Ref` 避免重复请求；后台状态变化不会自动轮询刷新 | 创建/撤销后依赖本地列表更新和主动刷新 |
| Clipboard API | 非 HTTPS 或浏览器权限限制可能导致复制失败 | 验证成功/失败 notification |
| 移动端布局 | API Keys group 内容多，容易出现 key secret 或按钮溢出 | 桌面、平板、手机分别截图检查 |

---

## 六、E2E 测试用例

| Case ID | 模块 | 测试场景 | 前置条件 | 测试步骤 | 预期结果 | 优先级 |
|---|---|---|---|---|---|---|
| PRIS-268-E2E-001 | 页面加载 | email 登录用户进入 Account Page | 用户已登录；localStorage 有 `userEmail`、`gatewayToken`、`emailLogin=true`；reCAPTCHA 可用 | 1. 打开 Account Page；2. 等待 loading 结束；3. 观察 profile、Personal Info、Community、Operator、API Keys 区域 | 调用 `GET /api/get-users` 成功；页面显示用户头像、email、个人资料；API Keys 下同时显示 Subscriber 与 Operator group；无 JS error | P0 |
| PRIS-268-E2E-002 | 页面加载 | wallet 登录用户进入 Account Page | 用户已通过 wallet 登录；localStorage 有 `walletAddress`、`gatewayToken`、`selectedChain` | 1. 打开 Account Page；2. 等待加载完成 | Header 显示短地址和对应 chain icon；`GET /api/get-users` 带 `wallet_address` 和 `chain`；profile email 使用 `user_profile_email` | P0 |
| PRIS-268-E2E-003 | 页面加载 | email + wallet 绑定用户显示 unlink wallet | 用户账号同时存在 `userEmail` 与 `walletAddress` | 1. 打开 Account Page；2. hover unlink 图标；3. 点击 unlink | hover 显示 `Unlink Wallet` tooltip；点击调用 `/api/disconnect-wallet-from-email`；成功后清理 wallet localStorage 并 reload；reload 后显示成功 notification | P0 |
| PRIS-268-E2E-004 | Personal Info | 普通保存个人资料 | 非 email-login 或 email-login 用户均可；接口正常 | 1. 点击 `Edit`；2. 修改 User name、Phone Number、Telegram ID；3. 点击 `Save` | 调用 `POST /api/update-user-info`；保存成功后退出编辑态；页面显示新值；出现 `Personal info updated successfully.` | P0 |
| PRIS-268-E2E-005 | Personal Info | email-login 用户编辑态下 email 只读 | `emailLogin=true` | 1. 点击 `Edit`；2. 查看 Email 字段；3. 尝试修改 email | Email 字段显示为文本，不出现 email input；保存不会改变登录 email | P1 |
| PRIS-268-E2E-006 | Personal Info | wallet 用户输入非法 profile email | wallet 登录或非 email-login；当前可编辑 email | 1. 点击 `Edit`；2. 输入 `abc@`；3. 点击 `Save` | 不调用 update 接口；提示 `Please enter a valid email address.`；焦点回到 email input | P0 |
| PRIS-268-E2E-007 | Personal Info | wallet 用户修改 profile email 触发验证 modal | wallet 已连接；新 email 与原 email 不同 | 1. 点击 `Edit`；2. 输入合法新 email；3. 点击 `Save` | 打开 `EmailVerificationModal`；未验证前不保存新 email；modal 中 email 为输入的新 email | P0 |
| PRIS-268-E2E-008 | Personal Info | email verification 成功后保存 profile email | 延续 Case 007；验证码流程可通过 | 1. 在 EmailVerificationModal 完成验证；2. 等待保存完成 | modal 关闭；调用 `/api/update-user-info` 保存新 `user_profile_email`；页面展示新 email；出现保存成功提示 | P0 |
| PRIS-268-E2E-009 | Social | 未链接 Twitter 时点击 Link Twitter | 用户未绑定 Twitter；OAuth 环境可用 | 1. 打开 Account Page；2. 点击 Twitter icon tile | 按钮进入 linking 状态或跳转 OAuth；回跳 `twitter_status=success` 后显示 success notification；页面刷新 Twitter display name | P1 |
| PRIS-268-E2E-010 | Social | Twitter OAuth 失败提示 | 构造 Account URL 带 `twitter_status=error&twitter_reason=access_denied` | 1. 打开该 URL；2. 观察 notification 与 URL | 显示 `Twitter authorization was cancelled.`；URL 中 `twitter_status/twitter_reason/twitter_username` 被清理 | P1 |
| PRIS-268-E2E-011 | Social | 已链接 Twitter 显示账号并可 unlink | 用户已有 `user_profile_twitter_id` 和 `user_profile_twitter_name` | 1. 打开 Account Page；2. 查看 Twitter 行；3. 点击 `Unlink` | 显示 X icon、绿色 check badge、账号名、`Unlink`；点击后调用 unlink 流程；成功后变回 link tile | P1 |
| PRIS-268-E2E-012 | Social | 未链接 Discord 时点击 Link Discord | 用户未绑定 Discord；OAuth 环境可用 | 1. 打开 Account Page；2. 点击 Discord icon tile | 触发 Discord OAuth linking；成功后刷新用户资料并显示 Discord 名称 | P1 |
| PRIS-268-E2E-013 | Social | 已链接 Discord 显示账号并可 unlink | 用户已有 `user_profile_discord_id` 和 `user_profile_discord_name` | 1. 打开 Account Page；2. 查看 Discord 行；3. 点击 `Unlink` | 显示 Discord icon、绿色 check badge、账号名、`Unlink`；成功 unlink 后变回 link tile | P1 |
| PRIS-268-E2E-014 | Community | Explorer 会员看到升级路径 | 用户 `user_class=Explorer Member` | 1. 打开 Account Page；2. 查看 Community 区域；3. 点击 Amplifier/Innovator upgrade | Explorer 显示 `CURRENT`；Amplifier 显示 `$99` 与 `Upgrade - $99`；Innovator 显示 `$399` 与 `Upgrade - $399`；点击任一打开 `UpgradeMembershipModal` | P0 |
| PRIS-268-E2E-015 | Community | Amplifier 会员看到 included/current/upgrade 状态 | 用户 `user_class=Amplifier Member` | 1. 打开 Account Page；2. 查看 Community 区域；3. 点击 Innovator upgrade | Explorer 显示 `Included`；Amplifier 显示 `CURRENT` 和 `Activated · paid $99`；Innovator 显示 `$399` 与 upgrade 按钮 | P0 |
| PRIS-268-E2E-016 | Community | Innovator 会员不显示升级按钮 | 用户 `user_class=Innovator Member` | 1. 打开 Account Page；2. 查看 Community 区域 | Explorer 与 Amplifier 显示 included/activated；Innovator 显示 `CURRENT` 和 `Activated · paid $399`；没有 upgrade 按钮 | P0 |
| PRIS-268-E2E-017 | API Keys | API Keys 区域按 group 展示 | 任意登录用户 | 1. 打开 Account Page；2. 滚动到 API Keys | 标题为 `API Keys`；副标题为 `Keys are grouped by role...`；下方没有 tab；同时展示 Subscriber 和 Operator 两个 group | P0 |
| PRIS-268-E2E-018 | API Keys | Subscriber group 静态信息展示 | 任意登录用户 | 1. 查看 Subscriber group | 显示 Download icon、`Subscriber`、`DOWNLOAD` tag、`Researcher plan`、`episodes:read`；显示 quota strip：`500 GB / mo`、`210 GB`、`100 req/min`、`Upgrade plan ->` | P0 |
| PRIS-268-E2E-019 | API Keys | Operator group 静态信息展示 | 任意登录用户 | 1. 查看 Operator group | 显示 Gamepad icon、`Operator`、`UPLOAD` tag、`episodes:write`；显示 `New key` 按钮；无 quota strip | P0 |
| PRIS-268-E2E-020 | API Keys | Operator 用户加载两个 group 的 keys | 用户 `user_role=operator`；存在或不存在 keys 均可 | 1. 打开 Account Page；2. 等待 API Keys 加载 | 调用 `GET /data/api-keys` 和 `GET /data/upload-api-keys`；两个 `New key` 按钮可点击；有 ACTIVE key 时显示 name/prefix/last used/Revoke；无 key 时显示 empty 文案 | P0 |
| PRIS-268-E2E-021 | API Keys | Operator 创建 Subscriber/download API key | 用户 `user_role=operator`；后端允许 download key 创建 | 1. 点击 Subscriber group 的 `New key`；2. 等待接口返回；3. 点击 copy | 调用 `POST /data/api-keys`；按钮显示 `Creating...`；成功后显示 `New subscriber API key` 和完整 secret；copy 成功提示 `subscriber API key copied.` | P0 |
| PRIS-268-E2E-022 | API Keys | Operator 创建 Operator/upload API key | 用户 `user_role=operator`；后端允许 upload key 创建 | 1. 点击 Operator group 的 `New key`；2. 等待接口返回；3. 点击 copy | 调用 `POST /data/upload-api-keys`；成功后显示 `New operator API key` 和完整 secret；copy 成功提示 `operator API key copied.` | P0 |
| PRIS-268-E2E-023 | API Keys | Operator 撤销 Subscriber/download API key | 用户 `user_role=operator`；至少存在一个 ACTIVE download key | 1. 点击 Subscriber key 的 `Revoke`；2. 等待接口返回 | 调用 `DELETE /data/api-keys/{id}`；按钮显示 `Revoking...`；成功后该 key 从 Subscriber 列表消失；提示 `Download API key revoked.` | P0 |
| PRIS-268-E2E-024 | API Keys | Operator 撤销 Operator/upload API key | 用户 `user_role=operator`；至少存在一个 ACTIVE upload key | 1. 点击 Operator key 的 `Revoke`；2. 等待接口返回 | 调用 `DELETE /data/upload-api-keys/{id}`；成功后该 key 从 Operator 列表消失；提示 `Upload API key revoked.` | P0 |
| PRIS-268-E2E-025 | API Keys | Admin 只能管理 Subscriber group | 用户 `user_role=admin`，且后端允许 robotic data user | 1. 打开 Account Page；2. 查看两个 group；3. 点击 Subscriber `New key`；4. 尝试 Operator `New key` | Subscriber 可加载和创建 download key；Operator 显示 `Only operators can create upload API keys.`，`New key` disabled，列表显示 `No access to operator API keys.` | P0 |
| PRIS-268-E2E-026 | API Keys | 普通用户无 API key 权限 | 用户 `user_role` 为空或普通角色 | 1. 打开 Account Page；2. 查看 Subscriber 与 Operator group | 两个 group 均显示权限提示；两个 `New key` disabled；不发起 list/create/delete 请求 | P0 |
| PRIS-268-E2E-027 | API Keys | 只展示 ACTIVE keys | 用户有 ACTIVE 与 REVOKED keys | 1. 打开 Account Page；2. 查看对应 group 列表 | 仅展示 `status=ACTIVE` 的 key；REVOKED key 不显示 | P1 |
| PRIS-268-E2E-028 | API Keys | API key list 接口失败 | 模拟 `/data/api-keys` 或 `/data/upload-api-keys` 返回 500/403 | 1. 打开有权限用户的 Account Page；2. 等待请求失败 | 页面不崩溃；loading 结束；显示 error notification，内容优先使用后端 `msg` | P1 |
| PRIS-268-E2E-029 | API Keys | 创建 API key 失败 | 模拟 create 接口返回非 2xx 或 `success=false` | 1. 点击任一可用 group 的 `New key`；2. 等待失败 | `Creating...` 恢复为 `New key`；不显示 `New ... API key`；显示失败 notification | P1 |
| PRIS-268-E2E-030 | API Keys | 撤销 API key 失败 | 模拟 delete 接口返回 404/500 | 1. 点击 Revoke；2. 等待失败 | `Revoking...` 恢复为 `Revoke`；key 仍保留在列表；显示失败 notification | P1 |
| PRIS-268-E2E-031 | API Keys | Clipboard 复制失败 | 禁用 clipboard 权限或在不支持环境测试 | 1. 创建 key；2. 点击 Copy | 不崩溃；显示 copy 失败 notification | P2 |
| PRIS-268-E2E-032 | API Keys | 无 tab 回归检查 | 任意用户 | 1. 打开 Account Page；2. 检查 API Keys 区域 DOM/视觉 | 不存在 Upload API / Download API tablist；Subscriber 与 Operator group 同屏展示 | P0 |
| PRIS-268-E2E-033 | Operator Section | 通过 URL 自动打开 operator 注册 modal | 用户可访问 Account Page；URL 为 Account Page `?open=register-robot` | 1. 打开 URL；2. 观察 OperatorSection | OperatorSection 收到 `autoOpenRegisterModal=true`；注册 modal 自动打开；profile email 传入当前 Account email | P1 |
| PRIS-268-E2E-034 | Loading/Fallback | get-users 缺 token 或失败时 fallback 展示 | localStorage 缺少 `gatewayToken` 或接口失败 | 1. 打开 Account Page；2. 等待加载结束 | 页面不无限 loading；可显示 fallback user info；console 不出现阻断型 crash | P1 |
| PRIS-268-E2E-035 | Chain Icon | 不同 chain wallet 显示正确 icon | 分别准备 solana/ethereum/base/monad/aptos linked wallet 用户 | 1. 逐个账号打开 Account Page；2. 查看 header icon | 对应 chain 显示正确 icon；未知/空 chain 不显示错误图标；地址使用短地址格式 | P2 |
| PRIS-268-E2E-036 | Responsive | 桌面布局检查 | Chrome desktop 1440px 宽 | 1. 打开 Account Page；2. 检查 Personal Info、Community、API Keys | 内容居中；Personal Info 三列；Community 三列；Subscriber/Operator group 宽度正常；按钮和文本无重叠 | P1 |
| PRIS-268-E2E-037 | Responsive | 平板布局检查 | 768px 左右 viewport | 1. 打开 Account Page；2. 检查所有卡片 | Community/API Keys 不溢出；group header 和 New key 按钮可点击；quota strip 不遮挡 | P1 |
| PRIS-268-E2E-038 | Responsive | 手机布局检查 | 375px 或 390px viewport | 1. 打开 Account Page；2. 滚动检查所有区块；3. 执行 create/revoke/copy 可点击性检查 | Personal Info、Community、API Keys 单列展示；New key/Copy/Revoke 按钮可用；long email/key secret 不撑破容器 | P0 |
| PRIS-268-E2E-039 | Regression | 会员升级 modal 关闭后刷新用户等级 | Explorer 或 Amplifier 用户；可完成升级流程或 mock 成功 | 1. 点击升级按钮；2. 完成升级；3. 关闭 modal | `handleCloseUpgradeModal(true)` 后重新调用 `fetchUserInfo()`；Community 当前态更新；头像 badge 更新 | P1 |
| PRIS-268-E2E-040 | Security | API key secret 刷新后不再显示完整值 | 已创建一个新 API key 并能看到 secret | 1. 刷新页面；2. 查看对应 group | 完整 `api_key` 不再展示；列表只显示 `key_prefix...`；不会在 DOM 中残留旧 secret | P0 |

---

## 七、测试数据建议

| 用户类型 | 必要字段 | 用途 |
|---|---|---|
| Explorer 普通用户 | `user_class=Explorer Member`, `user_role=''` | 普通用户页面、无 API key 权限、升级入口 |
| Amplifier 普通用户 | `user_class=Amplifier Member` | Community included/current/upgrade 状态 |
| Innovator 普通用户 | `user_class=Innovator Member` | Community 无升级按钮状态 |
| Operator 用户 | `user_role=operator` | Subscriber + Operator API key 完整 CRUD |
| Admin 用户 | `user_role=admin` | Subscriber 权限、Operator 禁用状态 |
| Wallet 用户 | `walletAddress`, `selectedChain`, `emailLogin=false` | profile email 验证、chain icon、unlink wallet |
| Email login 用户 | `userEmail`, `emailLogin=true` | email 只读、profile 保存 |
| 社交已链接用户 | Twitter/Discord id + name | linked social 展示和 unlink |

---

## 八、验收标准

- Account Page 在桌面与移动端均能完整渲染，无布局重叠、横向溢出、按钮文字挤压。
- Personal Info 原有编辑、email verification、wallet unlink、Twitter/Discord link/unlink 流程不回归。
- Community 区域按 `user_class` 正确显示 current/included/upgrade 状态。
- API Keys 区域没有 tab，按 Subscriber/download 与 Operator/upload 两个 group 同屏展示。
- API Keys 区域按 `user_role` 正确控制权限，且与后端实际权限一致。
- Subscriber(download) 与 Operator(upload) API key 均可完成 list/create/copy/revoke 成功链路。
- API key secret 只在创建成功后展示一次；刷新后仅保留 prefix。
- 接口失败、无 token、clipboard 失败等异常路径均有可理解提示，页面不崩溃。
