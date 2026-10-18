# Login 改动联动逻辑分析（Frontend + Backend）

## 分析范围

本次基于以下 3 个与登录改造直接相关的 commit 做联合分析：

- `app-prismax-rp`（frontend）
  - `0f4966b` - addeding new modal for login
  - `2e2db8c` - improved login
- `app-prismax-rp-backend`（backend）
  - `17fba5f` - added new modal for login

---

## 一句话主线

这批改动把 PrismaX 登录从“跳转 gateway 的邮箱 token 验证”切换为“站内 Connect Modal 一站式登录（Email OTP / Google / Apple / Wallet）”，并在后端新增 `oauth-login` 真正验证第三方 token，形成前后端闭环。

---

## Commit 级别逻辑拆解

## 1) `0f4966b`（frontend）
**目标**：上线新的站内登录入口和弹窗，替代 gateway 跳转式登录流程。

**核心改动：**

- 新增 `ConnectModal` + 样式文件：
  - 单弹窗承载 Email、Google、Apple、Wallet 四类连接方式。
  - Email 采用“输入邮箱 -> 验证码（6 位 OTP）”流程。
  - 集成 reCAPTCHA v3（行为分）+ v2（人机弹窗）双重校验。
- `App.js` 路由切换：
  - 删除 `GatewayTokenVerifier` 入口与 `/email` token 验证路径。
  - 主路由直接回到 `Home`，不再依赖外部 gateway 回跳参数。
- `ConnectWalletHeader` 交互改造：
  - 未连接钱包且无邮箱态时，点击连接入口直接打开 `ConnectModal`。
  - 原 `handleLoginWithEmail` 从“跳转 gateway URL”改成“站内开 modal”。
  - 抽出 `handleModalWalletConnect`，把 modal 里的钱包连接映射回既有钱包连接函数。
- 删除 `GatewayTokenVerifier.js`：
  - 彻底移除 URL token 验证页面与 loading 过场逻辑。

**业务意义：**

- 登录体验从跨站跳转变成单页内闭环，减少跳转成本与状态丢失风险。
- 钱包登录与邮箱/社交登录统一到同一入口，入口认知更清晰。

---

## 2) `17fba5f`（backend）
**目标**：为前端新 modal 的 Google/Apple 登录提供后端 token 验证能力。

**核心改动：**

- 新增 OAuth 配置常量：
  - 支持 `GOOGLE_OAUTH_CLIENT_IDS` / `APPLE_OAUTH_CLIENT_IDS` 多 client id（逗号分隔）。
- 新增 `POST /auth/oauth-login`：
  - 入参：`provider`, `providerToken`, `recaptchaToken`, `referrers_referral_code`。
  - 先过 reCAPTCHA（`expected_action='login'`，阈值 `0.5`）。
  - `provider=google`：调用 Google `tokeninfo + userinfo`，验证 audience 与邮箱可用性。
  - `provider=apple`：基于 Apple JWKS 做 JWT 验签，验证 issuer/audience/email。
  - 成功后写 `auth_save_logs`，并 upsert `users`（更新 `hash_code`, `login_type`）。
  - 返回 `users` 数据，前端可直接建立登录态。
- CORS 调整：
  - 生产白名单移除 gateway 域名，只保留 `app` / `beta-app` / localhost。
- `requirements.txt` 增加 `cryptography`：
  - 支撑 JWT/JWK 验签依赖链。

**业务意义：**

- 社交登录从“前端声明 type”升级为“后端验 token 真伪”，安全性显著提升。
- 与前端 modal 的 OAuth 按钮形成真正可用的服务端能力。

---

## 3) `2e2db8c`（frontend）
**目标**：对新登录流程做配置收敛和稳定性增强。

**核心改动：**

- 新增 `src/configs/authPublicConfig.js`：
  - 统一导出 `RECAPTCHA_SITE_KEY`、`RECAPTCHA_V2_SITE_KEY`、`GOOGLE_CLIENT_ID`、`APPLE_CLIENT_ID`、`APPLE_REDIRECT_URI`。
- `ConnectModal` / `EmailVerificationModal` / `RecaptchaProvider` / `testHelpers` 改为读取统一配置：
  - 不再各处散落 `process.env.REACT_APP_*` 读取逻辑。
  - reCAPTCHA key、OAuth client id 在前端使用路径一致。

**业务意义：**

- 降低配置漂移风险（同一 key 多处来源不一致）。
- 减少测试环境与线上环境因变量缺失导致的“某流程可用、某流程不可用”问题。

---

## 前后端联动后的完整登录链路

## A) Email OTP 登录（站内）

1. 用户在 `ConnectModal` 输入邮箱并点击 Connect。  
2. 前端要求 reCAPTCHA v2（弹窗）+ v3（`send_code` action）后调用 `/auth/send-verification-code`。  
3. 用户输入 6 位 OTP。  
4. 前端再取 v3 token（`login` action）请求 `/auth/save`（`type='0'`）。  
5. 后端校验验证码、落库 `users.hash_code`，返回 session token。  
6. 前端可额外调 `/verify_token` 拉取完整用户态并写入 localStorage/context。  

**与旧流程差异：**
- 旧：跳 gateway，靠 URL token 回跳。  
- 新：站内完成验证码发送与登录态建立，不依赖外部跳转页。

---

## B) Google / Apple OAuth 登录（站内）

1. 用户在 `ConnectModal` 点 Google 或 Apple。  
2. 前端获取 provider token（Google access token / Apple id_token）。  
3. 前端取 reCAPTCHA v3 token（`login` action），调用 `/auth/oauth-login`。  
4. 后端校验 provider token：
   - Google：`tokeninfo` + `userinfo`，并校验 audience。  
   - Apple：JWKS 验签 + issuer/audience 校验。  
5. 校验通过后，后端 upsert `users` 并返回 `hash_code` 等用户信息。  
6. 前端写登录态（`gatewayToken`、`userEmail` 等），直接进入已连接状态。  

**关键改进点：**
- 社交登录不再只依赖前端传 `type=1/2`，而是服务端真实验签/验 token。

---

## 关键接口契约（联调重点）

- `/auth/save`（Email OTP）  
  - 请求关键字段：`email`, `code`, `type='0'`, `recaptchaToken`, `referrers_referral_code`  
  - 失败常见码：`400`（验证码/参数问题）、`403`（reCAPTCHA 不通过）

- `/auth/oauth-login`（Google/Apple）  
  - 请求关键字段：`provider`, `providerToken`, `recaptchaToken`, `referrers_referral_code`  
  - 失败常见码：`400`（provider 非法）、`401`（token 验证失败）、`403`（reCAPTCHA 不通过）

- `/verify_token`（补全用户态）  
  - 请求字段：`token`（即 `hash_code`）  
  - 用于前端在登录后拿到更完整的用户资料并同步上下文。

---

## QA 风险点与回归建议

## 高优先级风险

- **CORS 回归风险**：backend 移除 gateway 域名后，若还有历史页面或脚本从 gateway 域名直调 user-management，会被浏览器拦截。  
- **Apple email 可得性风险**：后端强依赖 Apple token 中 email，部分 Apple 场景可能只在首次授权返回 email，需重点验证“老用户再次登录”。
- **配置发布风险**：前端改为固定公共配置文件，若环境切换需不同 key/client id，需确认构建产物是否按预期替换。

## 建议补齐的回归用例

- Email 流程：
  - 正常发送验证码、错误验证码、过期验证码、连续重发倒计时、reCAPTCHA 失败分支。
- OAuth 流程：
  - Google 正常/取消授权/返回空 token；
  - Apple 正常/取消授权/后端 audience mismatch；
  - 后端返回 401/403 时前端错误提示是否准确。
- 跨端状态：
  - 登录后刷新页面、切链后状态保留、登出后本地存储清理是否完整。
- Referral：
  - URL `?ref=xxx` 与 localStorage fallback 场景下，`referrers_referral_code` 是否正确透传。

---

## 设计意图总结

- **产品层**：统一“Connect”入口，降低登录路径复杂度。  
- **技术层**：前端弹窗承载多登录方式，后端补齐 OAuth 真验证能力。  
- **风控层**：保留 reCAPTCHA 机制，并把社交登录接入同一风控通道。  
- **可维护性**：认证公开配置集中管理，减少前端多点分散读取。  

总体上，这是一组“登录架构从跳转式到站内闭环”的重构型改动：前端主导体验整合，后端补齐安全校验与落库逻辑，二者已形成可联调的完整闭环。

---

## 完整测试用例（PRIS-208）

## 测试范围与环境

- 站点：
  - 生产：`https://app.prismax.ai`
  - Beta：`https://beta-app.prismax.ai`
- 浏览器：Chrome（主）、Safari（Apple 登录重点）、Firefox（兼容性）
- 账号准备：
  - 新邮箱账号（未注册）
  - 旧邮箱账号（已注册）
  - 可正常登录的 Google 账号
  - 可正常登录的 Apple 账号（至少验证首次授权与再次登录）
- 验证手段：
  - 浏览器 Network 抓包
  - 后端日志（`/auth/save`, `/auth/oauth-login`, `/verify_token`）
  - 数据库抽查（`users`, `auth_save_logs`）

## 用例清单

### P0 - 主流程与核心风控

| 用例ID | 优先级 | 模块 | 用例标题 | 前置条件 | 测试步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-208-001 | P0 | ConnectModal | Connect 入口展示 | 未连接钱包，未邮箱登录 | 打开首页，点击 header 的 connect 区域 | 打开 `ConnectModal`；可见 Email、Google/Apple、Wallet 入口 |
| TC-208-002 | P0 | Email OTP | Email 发码成功 | 可用邮箱；reCAPTCHA 服务正常 | 输入合法邮箱 -> 完成人机验证 -> 点击 Connect | 调用 `/auth/send-verification-code` 成功；进入 OTP 视图并提示 “Verification code sent.” |
| TC-208-003 | P0 | Email OTP | Email OTP 登录成功 | 已收到有效验证码 | 输入 6 位正确验证码 | `/auth/save(type='0')` 成功；`/verify_token` 成功（若触发）；本地写入 `gatewayToken/userEmail/emailLogin=true`；UI 已登录 |
| TC-208-004 | P0 | Email OTP | OTP 错误码登录失败 | 已收到验证码 | 输入 6 位错误验证码 | `/auth/save` 失败（通常 400）；提示错误；OTP 输入框清空并可重输 |
| TC-208-005 | P0 | Email OTP | OTP 过期登录失败 | 验证码已过期 | 输入过期验证码 | 登录失败并提示；可重发并走新验证码链路 |
| TC-208-006 | P0 | Email OTP | 重发验证码倒计时 | 刚完成一次发码 | 倒计时期间点击 Resend | 倒计时内按钮不可用；倒计时结束后可重发 |
| TC-208-007 | P0 | 风控 | reCAPTCHA v3 分数不达标 | 模拟低分或无效 token | 提交 Email 或 OAuth 登录 | 后端 403；前端提示 “Security verification failed. Please try again.” |
| TC-208-008 | P0 | OAuth-Google | Google 登录成功 | Google 账号可用；client id 正确 | 点击 Google 并完成授权 | `/auth/oauth-login` 带 `provider='google'`、`providerToken`、`recaptchaToken`；返回成功含 `hash_code`；前端写入登录态并关闭 modal |
| TC-208-009 | P0 | OAuth-Apple | Apple 登录成功 | Safari/支持环境；Apple 账号可用 | 点击 Apple 并完成授权 | `/auth/oauth-login` 带 `provider='apple'`；后端 JWT 验签通过；前端写入登录态并关闭 modal |
| TC-208-010 | P0 | OAuth-Google | Google 用户取消授权 | 可打开 Google 授权弹窗 | 在 Google 授权页取消 | 不创建登录态；前端提示取消/失败信息 |
| TC-208-011 | P0 | OAuth-Apple | Apple 用户取消授权 | 可打开 Apple 授权弹窗 | 在 Apple 授权页取消 | 不创建登录态；前端提示 Apple 登录失败 |
| TC-208-012 | P0 | OAuth | OAuth token 非法 | 构造无效 `providerToken` | 调用 `/auth/oauth-login` | 返回 401；前端显示失败文案且不写登录态 |
| TC-208-013 | P0 | OAuth | provider 非法值 | 抓包改 `provider=facebook` | 提交 `/auth/oauth-login` | 返回 400：Unsupported OAuth provider |
| TC-208-014 | P0 | Referral | Referral 透传验证 | 访问 URL 带 `?ref=abc123` | 走 Email/OAuth 登录 | 请求带 `referrers_referral_code=abc123`；首次写入 referral，老用户不覆盖 |

### P1 - 登录态、会话、钱包集成与数据校验

| 用例ID | 优先级 | 模块 | 用例标题 | 前置条件 | 测试步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-208-015 | P1 | 会话 | 登录后刷新页面 | 已登录 | 刷新页面 | 登录态可恢复；用户信息不丢失 |
| TC-208-016 | P1 | 会话 | 登出行为 | 已登录 | 执行登出 | `gatewayToken/userEmail/emailLogin` 等被清理；UI 回到未登录态 |
| TC-208-017 | P1 | 路由 | `/email` 路由回归 | 无 | 直接访问 `/email` | 重定向到 `/`；不再走旧 gateway token 验证流 |
| TC-208-018 | P1 | 路由 | 旧 token 回跳链路失效验证 | 有历史 gateway 回跳 URL | 访问带 token 的历史 URL | 不依赖 `GatewayTokenVerifier`；仍可站内打开 ConnectModal 登录 |
| TC-208-019 | P1 | 会话 | 多 tab 会话一致性 | A tab 已登录 | 切到 B tab 刷新 | B tab 可读取登录态，行为符合产品定义 |
| TC-208-020 | P1 | 会话 | 会话 token 失效 | 手动写入无效 `gatewayToken` | 触发鉴权动作或初始化校验 | 识别 token 无效并清理登录态，提示重新登录 |
| TC-208-021 | P1 | Wallet | Modal 中钱包列表展开/收起 | 打开 ConnectModal | 多次点击 “Connect a wallet” | 列表正常展开/收起，无抖动和遮挡 |
| TC-208-022 | P1 | Wallet | Solana 链钱包选项 | 当前链为 Solana | 打开钱包列表 | 展示 Phantom/MetaMask/OKX/Coinbase/WalletConnect（按实现） |
| TC-208-023 | P1 | Wallet | EVM 链钱包选项 | 当前链非 Solana | 打开钱包列表 | 不展示 WalletConnect-Solana 专属项 |
| TC-208-024 | P1 | Wallet | Modal 内钱包连接成功 | 有可用钱包 | 在 modal 点击钱包并连接 | 调用对应连接方法；成功后 modal 关闭，header 显示已连接 |
| TC-208-025 | P1 | Wallet | 钱包连接失败兜底 | 模拟钱包拒绝或 provider 异常 | 发起钱包连接 | modal 显示失败文案；可继续尝试其他方式 |
| TC-208-026 | P1 | API/DB | `/auth/save` 成功日志 | 可完成 Email OTP 登录 | 完成一次 Email 登录 | `auth_save_logs` 有记录，`insert_status=success`，`recaptcha_score` 有值 |
| TC-208-027 | P1 | API/DB | `/auth/save` reCAPTCHA 失败日志 | 可模拟低分/失败 | 提交 `/auth/save` | 有失败日志（`insert_status=failed`）；接口 403 |
| TC-208-028 | P1 | API/DB | `/auth/oauth-login` 成功落库 | 可完成 Google/Apple 登录 | 完成 OAuth 登录 | `users` upsert；`login_type` 正确（Google=1, Apple=2）；`hash_code` 更新 |
| TC-208-029 | P1 | API/DB | `/auth/oauth-login` audience mismatch | 使用不匹配 client id 的 token | 调用 OAuth 登录 | 返回 401（audience mismatch 或等效信息） |
| TC-208-030 | P1 | API | `/verify_token` 成功与失败分支 | 准备有效/无效 token | 分别提交两种 token | 有效返回用户数据；无效返回失败且前端可处理 |

### P2 - 兼容性、可用性与边界

| 用例ID | 优先级 | 模块 | 用例标题 | 前置条件 | 测试步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- | --- |
| TC-208-031 | P2 | CORS | CORS 白名单验证（app/beta） | 在 `app`/`beta-app` 域访问 | 分别发起登录请求 | 预检与主请求均通过 |
| TC-208-032 | P2 | CORS | CORS 非白名单验证（gateway） | 在已移除 gateway 域访问 | 发起登录请求 | 被 CORS 拦截，符合预期 |
| TC-208-033 | P2 | OAuth-Apple | Apple 首登与二次登录 | Apple 账号可用 | 首次授权后再次登录 | 两次均可登录；若二次缺 email，记录为风险点 |
| TC-208-034 | P2 | ConnectModal | Modal 关闭与状态重置 | 打开 modal 并输入部分内容 | 关闭后再次打开 | 状态 reset（邮箱/验证码/错误提示/倒计时符合设计） |
| TC-208-035 | P2 | Email OTP | OTP 输入交互体验 | 打开 OTP 页面 | 逐位输入、退格、粘贴数字与混合字符 | 自动聚焦正确；仅收数字；满 6 位自动验证 |
| TC-208-036 | P2 | 异常处理 | 网络超时/500 异常提示 | 可模拟后端超时或 500 | 发起登录相关请求 | 前端有可理解提示，不空白不假死 |
| TC-208-037 | P2 | 开发环境 | 本地开发 bypass 路径 | 本地开发模式 | 执行发码与登录 | 符合本地 bypass 逻辑，不影响生产行为 |
| TC-208-038 | P2 | 配置 | 配置一致性校验 | 无 | 检查 `ConnectModal`、`RecaptchaProvider`、`EmailVerificationModal`、`testHelpers` 配置读取 | 均从 `authPublicConfig.js` 读取，无 env 分叉 |

---

## 执行建议（测试顺序）

1. 先跑 P0（001-014），确认主链路可用。  
2. 再跑 P1（015-030），确认状态一致性与后端落库。  
3. 最后跑 P2（031-038），覆盖兼容性与边界。  
4. 每个失败用例保留：请求参数、响应体、前端截图、日志片段、是否可复现。  

