# Prismax 用户管理系统业务逻辑说明

> **代码来源**：`app-prismax-rp-backend/app_prismax_user_management/app.py` 及相关辅助模块  
> **适用范围**：需求理解、测试设计、线上排查  
> **最近更新**：2026-07-07

---

## 目录

1. [系统架构速览](#一系统架构速览)
2. [核心数据结构](#二核心数据结构)
   - [users 主表](#1-users-表用户主表)
   - [关联表汇总](#2-关联表汇总)
3. [认证与登录](#三认证与登录)
   - [邮箱验证码登录](#1-发送验证码--authsend-verification-code)
   - [OAuth 第三方登录](#4-oauth-统一登录--authoauth-login)
   - [Token 校验与退出](#5-token-校验与退出)
   - [管理员登录](#6-管理员登录--apiadmin-login)
   - [Beta 内测访问控制](#7-beta-内测访问控制)
4. [用户查询与账户绑定](#四用户查询与账户绑定)
5. [用户资料与外部账号绑定](#五用户资料与外部账号绑定)
   - [基本资料更新](#1-更新基本资料--apiupdate-user-info)
   - [Twitter OAuth](#3-twitter-oauth-绑定与解绑)
   - [Discord OAuth](#4-discord-oauth-绑定与解绑)
6. [会员等级与支付](#六会员等级与支付)
   - [Stripe 支付](#1-stripe-支付与会员升级)
   - [加密货币支付](#2-加密货币支付--apirecord-crypto-payment)
   - [管理员对账](#3-管理员-stripe-对账--apiadminstripereconcile-payments)
7. [积分系统](#七积分系统)
8. [机器人相关功能](#八机器人相关功能)
   - [TeleOp 会员权限](#2-teleop-会员权限按-robot_class)
   - [Fleet 机器人购买](#3-fleet-机器人购买系统)
9. [Operator 操作员系统](#九operator-操作员系统)
10. [VLA Admin 管理接口](#十vla-admin-管理接口)
    - [任务管理](#2-任务管理--apivla-admintasks)
    - [Hex AI 管理](#3-hex-ai-管理接口)
11. [QA 审核员管理](#十一qa-审核员管理)
12. [第三方渠道集成](#十二第三方渠道集成)
    - [Galxe](#1-galxe-渠道集成)
    - [Partner Device Listing](#2-partner-device-listing-合作伙伴设备入驻)
13. [管理端其他功能](#十三管理端其他功能)
14. [关键要点小结](#十四关键要点小结)

---

## 一、系统架构速览

### 登录方式

| 方式 | 接口 | login_type |
|------|------|-----------|
| 邮箱验证码 | `/auth/send-verification-code` + `/auth/save` | `'0'` |
| Google OAuth | `/auth/oauth-login` | `'1'` |
| Apple OAuth | `/auth/oauth-login` | `'2'` |
| 多链钱包 | `/api/get-users` 自动创建 | — |

所有登录方式最终均收敛到 `users.hash_code` 作为长效会话令牌（`Authorization: Bearer <hash_code>`）。

### 会员等级与权限对照

| 等级 | 升级价格 | TeleOp training 臂 | TeleOp open 臂 | TeleOp access 臂 | Fast Track | Fleet 购买 |
|------|---------|-------------------|---------------|-----------------|-----------|-----------|
| Explorer Member | 免费 | ❌ 禁止 | ❌ 禁止 | ❌ 禁止 | ❌ | ❌ |
| Amplifier Member | $99 | ✅ 每日≤3次 | ✅ 终身≤3次 | ✅ 无次数限制 | ❌ | ✅ |
| Innovator Member | $399 | ✅ 无限制 | ✅ 无限制 | ✅ 无限制 | ✅ 每日6次（共享） | ✅ |

### 角色体系

- `user_class`：会员等级（付费驱动），控制功能权限与积分倍率。
- `user_role`：功能性角色（审批驱动），与 `user_class` 完全独立：
  - `operator`：经审核的数据操作员，可上传机器人操作数据。
  - `qa` / `senior qa` / `expert qa`：QA 审核员，由管理员分配。

### 账户体系

用户可通过**邮箱**或**多链钱包**（Solana/Ethereum/Base/Monad/Aptos）任一渠道进入，通过 `linked_email` / `linked_wallet_address` 互相绑定为同一身份，以邮箱侧为主身份。

---

## 二、核心数据结构

> 以下字段从 SQL 查询与更新逻辑推断，实际 DDL 以数据库为准。

### 1. `users` 表（用户主表）

**身份与登录**

| 字段 | 说明 |
|------|------|
| `userid` | 主键，自增 |
| `email` | 登录邮箱（邮箱体系，可为空） |
| `login_type` | `'0'`=邮箱验证码，`'1'`=Google，`'2'`=Apple |
| `hash_code` | 会话令牌，每次登录/登出时刷新 |

**多链钱包地址**

`solana_receive_address` / `ethereum_receive_address` / `base_receive_address` / `monad_receive_address` / `aptos_receive_address`

**账户绑定**

| 字段 | 说明 |
|------|------|
| `linked_email` | 钱包用户绑定的邮箱 |
| `linked_wallet_address` | 邮箱用户绑定的钱包地址 |

**会员与积分**

| 字段 | 说明 |
|------|------|
| `user_class` | `Explorer Member` / `Amplifier Member` / `Innovator Member` |
| `total_points` | 当前可用积分 |
| `referral_code` | 该用户对外分享的推荐码 |
| `referrers_referral_code` | 注册时填写的推荐人推荐码 |
| `referred_reward_point` | 10% 分成已结算积分（防重复结算） |
| `referral_initial_reward` | 邀请奖励已发放总额（每被邀请人 500 积分） |

**角色**

| 字段 | 说明 |
|------|------|
| `user_role` | `operator` / `qa` / `senior qa` / `expert qa`，或为空 |

**个人资料**

| 字段 | 说明 |
|------|------|
| `user_name` | 昵称 |
| `user_profile_email` | 对外联系邮箱（与登录邮箱可不同，需验证码修改） |
| `telegram_id` | Telegram ID |
| `phone_number` | 电话号码 |
| `user_profile_twitter_id` / `user_profile_twitter_name` | Twitter 绑定 |
| `user_profile_discord_id` / `user_profile_discord_name` | Discord 绑定 |

**渠道来源**

| 字段 | 说明 |
|------|------|
| `acquisition_source` | 注册渠道标记，当前支持 `'galxe'` |

**其他**：`created_at`（创建时间）

---

### 2. 关联表汇总

#### 积分与认证

| 表名 | 用途 |
|------|------|
| `email_verification_codes` | 邮箱验证码（6位，10分钟有效，记录IP） |
| `point_transactions` | 积分流水（`daily_login` / `quiz` / `comment_reward` 等） |
| `auth_save_logs` | 登录行为日志（IP、UA、reCAPTCHA 分） |

#### 支付与购买

| 表名 | 用途 |
|------|------|
| `purchase_records` | 所有会员购买记录（Stripe + 多链） |
| `verify_payment_records` | 多链/Stripe 对账快照 |
| `fleet_purchase_info` | Fleet 机器人购买申请 |

#### 机器人/操作员

| 表名 | 用途 |
|------|------|
| `data_machines` | Operator 注册的机器人（含 `is_default_producer`） |
| `data_sample_machines` | 机器人型号标准库（管理员维护，含 Fleet 展示字段） |
| `data_operator_applications` | Operator 资格申请（`pending`/`approved`/`denied`） |
| `data_uploads` | Operator 上传记录 |
| `data_episodes` | 单集 episode（含 `video_duration_hours`） |
| `data_tasks` | VLA 任务配置（含 `is_visible_beta` / `is_visible_production`） |
| `data_qa_sessions` | QA 审核会话记录（含 `qa_score`） |

#### 管理/风控

| 表名 | 用途 |
|------|------|
| `admin_whitelist` | 管理员钱包地址白名单 |
| `admin_invite_codes` | 管理员一次性邀请码 |
| `detected_bot_users` | 疑似刷分账户记录 |
| `reserve_info` | ~~机器人预约（已停用）~~ |

#### 新增系统表

| 表名 | 用途 |
|------|------|
| `fleet_purchase_info` | Fleet 机器人购买申请（含联系人信息、`machine_id`、`email_sent`） |
| `data_partner_device_requests` | Partner Device 入驻申请（含 `serial_number_info` JSONB） |
| `hex_capability_requests` | Hex AI 能力请求（用户提交的目录缺口） |
| `hex_chat_logs` | Hex AI 会话聊天日志（按 `turn_number`/`event_index` 排序） |

---

## 三、认证与登录

### 1. 发送验证码 `/auth/send-verification-code`

1. 入参：`email`、`recaptchaToken`（v3）、`recaptchaV2Token`（v2）。
2. **机器邮箱拦截**：Hotmail 等明显机器邮箱做"假发送"，不真正发送。
3. **冷却限流**：同一邮箱 30 秒内不可重复请求。
4. **双重 reCAPTCHA**：v3 分数 > 0.3，v2 必须通过。
5. 生成 6 位验证码写入 `email_verification_codes`（同一 email 更新已有记录）。
6. 当日总发送量超过 1500（每 500 递增）时，自动发送管理员告警邮件。
7. 发送 HTML 验证邮件，返回成功。

### 2. 验证码校验并建用户 `/auth/verify-code`

1. 入参：`email`、`code`。
2. 校验记录存在 + code 一致 + 未过期。
3. 通过后向 `users` 插入 `email`（已存在则忽略）。

### 3. 邮箱验证码登录保存 `/auth/save`

1. 入参：`email`、`code`（`login_type='0'` 时需要）、`type`、`recaptchaToken`、`referrers_referral_code`（可选）。
2. 写入 `auth_save_logs`（含 IP、UA、reCAPTCHA 分）。
3. reCAPTCHA 分 < 0.5 → 直接拒绝。
4. `_verify_email_code` 校验验证码。
5. 生成新 `hash_code`（高熵随机串）。
6. Upsert `users`：
   - 首次创建：写入 `referrers_referral_code`。
   - 后续登录：仅更新 `hash_code` 和 `login_type`，不覆盖推荐关系。
7. 返回 `email` + `hash_code`。

### 4. OAuth 统一登录 `/auth/oauth-login`

统一处理 Google/Apple 第三方登录（取代旧有 `login_type` 模式）：

1. 入参：`provider`（`'google'`/`'apple'`）、`providerToken`、`recaptchaToken`、`referrers_referral_code`（可选）。
2. reCAPTCHA 分 < 0.5 → 拒绝。
3. 调用 `_validate_google_oauth_token` 或 `_validate_apple_oauth_token` 验证 Token，提取 `email`。
   - Google → `login_type = '1'`；Apple → `login_type = '2'`。
4. 生成 `hash_code`，写 `auth_save_logs`。
5. Upsert `users`（首次创建保留 `referrers_referral_code`，后续只更新 `hash_code`/`login_type`）。
6. 返回完整用户行与 `success: true`。

### 5. Token 校验与退出

| 接口 | 方法 | 逻辑 |
|------|------|------|
| `/verify_token` | POST | 按 `hash_code` 查 `users`；找到返回完整用户行，否则返回 `invalid` |
| `/logout` | POST | 按 `email` 找用户，随机生成新 `hash_code` 写入，使旧 token 失效（服务端旋转 token） |

### 6. 管理员登录 `/api/admin-login`

- **方式**：Solana 钱包签名（客户端对固定 `MESSAGE_TEXT` 签名，服务端 `verify_sol_sig` 验证）。
- **结果**：颁发 JWT `access_token`（30 分钟）+ `refresh_token`，`role` 声明为 `admin`。
- 后续管理接口使用 `@jwt_required()` + `get_jwt_identity()` 鉴权。

### 7. Beta 内测访问控制

| 接口 | 功能 |
|------|------|
| `/auth/beta/verify-access-code` | 校验一次性访问码（限流 10次/分钟，常量时间比较），通过后颁发 24 小时 JWT Beta Token |
| `/auth/beta/validate-token` | 验证 Beta Token 签名与过期时间，返回 `success: true` 或失败原因 |

---

## 四、用户查询与账户绑定

### 获取用户信息 `/api/get-users`

**入参**：`email`（可选）、`wallet_address`（可选）、`chain`（默认 `solana`）、`token`（邮箱查询时必须）、`recaptcha_token`、`source`（可选，仅接受 `'galxe'`）。

**核心逻辑**：

```
reCAPTCHA 分 > 0.2
  └─ 有 wallet_address
      ├─ 找到 → 若有 linked_email，返回邮箱用户（邮箱为主身份）
      └─ 未找到 → 链上余额检查 → 有余额则创建用户（如有 source=galxe，写入 acquisition_source）
  └─ 有 email（必须带 token）
      └─ email + hash_code 精确匹配
  └─ 两者都有
      ├─ 两者都找到 → 防止高等级钱包用户（Amplifier/Innovator）绑定到另一邮箱
      └─ 解绑旧关系 → 重新绑定 → 返回邮箱用户为主
  └─ 都未找到 → 404
```

### 解除邮箱与钱包绑定 `/api/disconnect-wallet-from-email`

- 入参：`email`、`wallet_address`、`chain`、`token`。
- 将邮箱记录的 `linked_wallet_address` 和钱包记录的 `linked_email` 分别置 `NULL`。
- 若两侧均无有效绑定，返回 404。

---

## 五、用户资料与外部账号绑定

### 身份校验统一规则

- **邮箱用户**：`email + token(hash_code)` 精确匹配。
- **钱包用户**：`wallet_address + chain + token(hash_code)` 精确匹配。
- 所有编辑接口：找不到匹配用户或 token 失效 → 401/403。
- 字段更新策略：**动态 SQL**，仅对请求中实际出现的字段生成 `SET` 子句。

### 1. 更新基本资料 `/api/update-user-info`

- 可更新字段：`user_name`、`telegram_id`、`twitter_name`/`user_profile_twitter_name`、`phone_number`。
- 不可通过此接口修改 `user_class`、积分、推荐码等敏感字段。

### 2. 更新对外邮箱 `/auth/update-user-profile-email/verify-code`

1. 用户先请求发送验证码到新邮箱（复用 `/auth/send-verification-code`）。
2. 提交：`email`（新邮箱）+ `code` + `user_id` + `token`。
3. 校验验证码 + 登录态，更新 `users.user_profile_email`。

### 3. Twitter OAuth 绑定与解绑

| 接口 | 说明 |
|------|------|
| `POST /auth/twitter/initiate` | 构造带 state 的 Twitter 授权 URL（state 含 `uid`、token 哈希、回跳 URL） |
| `GET /auth/twitter/callback` | 校验 state 签名+过期+token 哈希，换取 access token，写入 `user_profile_twitter_id/name` |
| `POST /api/user-profile/twitter-unlink` | 将 `user_profile_twitter_id/name` 置 NULL（幂等） |

### 4. Discord OAuth 绑定与解绑

| 接口 | 说明 |
|------|------|
| `POST /auth/discord/initiate` | 构造带 state 的 Discord 授权 URL（入参含 `return_url`、`backend_host_url`） |
| `GET /auth/discord/callback` | 校验 state，换取 access token，写入 `user_profile_discord_id/name`，重定向含 `discord_status=success/error` |
| `POST /api/user-profile/discord-unlink` | 将 `user_profile_discord_id/name` 置 NULL（幂等） |

---

## 六、会员等级与支付

### 升级规则

| 当前等级 | 支付金额 | 升级后等级 |
|---------|---------|----------|
| Explorer Member | $99 | Amplifier Member |
| Amplifier Member | $399 | Innovator Member |
| 其他组合 | 任意 | 不升级 |

### 1. Stripe 支付与会员升级

**创建支付会话 `/api/create-stripe-checkout-session`**：
- 入参：`user_id`、`membership_type`（`Amplifier Membership` → 9900 分 / `Innovator Membership` → 39900 分）。
- 返回 Stripe Checkout Session 跳转 URL。

**Webhook `/api/stripe-payment-completed`**：
- 验证 `STRIPE_WEBHOOK_SECRET_LIVE` 签名。
- 仅处理 `checkout.session.completed` 事件。
- `payment_status == 'paid'` 且有 `metadata.user_id` → 按升级规则写 `purchase_records` 并升级 `user_class`。

### 2. 加密货币支付 `/api/record-crypto-payment`

1. 入参：`wallet_address`、`amount_total`（美元整数）、`user_id`、`transaction_hash`、`currency`、`chain`。
2. 哈希唯一性校验（防重复录入）。
3. 调用 `verify_*_payment` 验证链上 transfer：
   - 收款地址必须为 Prismax 官方地址。
   - 金额须在 $99 或 $399 的允许误差范围内。
4. 写入 `purchase_records`，按升级规则升级 `user_class`。

### 3. 管理员 Stripe 对账 `/api/admin/stripe/reconcile-payments`

> 需 JWT 权限。

- 主动从 Stripe 拉取所有 `succeeded` Payment Intent 列表。
- 与本地 `purchase_records` 比对，找出漏录记录。
- 按创建时间顺序补录并触发会员升级（跳过已有争议的支付）。
- 返回摘要：补录数量、升级情况、异常列表、未解决记录。

---

## 七、积分系统

### 积分规则速查

| 行为 | Explorer | Amplifier | Innovator | 倍率说明 |
|------|---------|-----------|-----------|---------|
| 首次初始化 | 1000 | 1000 | 1000 | Monad 链 ×2 |
| 每日登录 | 10 | 30 | 50 | Monad 链 ×2 |
| 测验（每题） | 500 | 500 | 500 | 全对额外 +1000 |
| 推荐邀请奖励 | 500/人 | 500/人 | 500/人 | 一次性 |
| 推荐分成 | 被推荐人积分 ×10% | 同左 | 同左 | 增量结算 |

### 1. 每日登录积分 `/api/daily-login-points`

- 入参：`wallet_address + chain` 或 `email`；`user_local_date`（可选，需在 UTC ±1 天内）。
- 若 `total_points == 0`：初始化赠送 1000 × multiplier 积分。
- 否则检查当天是否有 `daily_login` 记录，无则按等级发放并写 `point_transactions`。

### 2. 查询积分明细 `/api/get-point-transactions`

- 带身份参数：返回该用户最近 14 天积分记录 + 当前 `total_points`。
- 不带参数：返回所有用户最近 14 天记录（后台用）。

### 3. 推荐奖励结算 `/api/get-users-by-referral`

1. 锁行防并发：`userid + hash_code`。
2. 校验 `referrers_referral_code == users.referral_code`。
3. 汇总所有被推荐人 `total_points`。
4. **邀请奖励**：500/人，用 `referral_initial_reward` 记录已发，只补发差值。
5. **10% 分成**：`target = floor(总积分 × 10%)`，用 `referred_reward_point` 记录已发，只发增量。

### 4. 测验积分 `/api/quiz/check-status` 与 `/api/quiz/submit`

- `check-status`：查询是否有 `transaction_type = 'quiz'` 记录。
- `submit`：reCAPTCHA 校验 → 防重复提交 → 计分（每题 500 分，全对额外 +1000）→ 写 `point_transactions`。

> ~~评论奖励 `/api/check-comment-reward`~~ 已因 PRIS-125 暂时关闭。

---

## 八、机器人相关功能

### 1. ~~机器人预约 `/api/reserve-robot`~~（已下线）

> 接口已注释，功能由 Fleet 购买系统取代。

### 2. TeleOp 会员权限（按 robot_class）

**机械臂分类**（由后端 `robot_status` 表的 `robot_class` 字段驱动，前端路由为 `/tele-op/:robotSlug`）：

| robot_class | 典型机型 | Explorer | Amplifier | Innovator |
|-------------|---------|---------|-----------|-----------|
| `training` | 原 arm1/arm4 | ❌ | ✅ 每日 UTC ≤3次 | ✅ 无限制 |
| `open` | 原 arm3 | ❌ | ✅ 终身 ≤3次 | ✅ 无限制 |
| `access` | 原 arm2 | ❌ | ✅ 无次数限制（需管理员邀请码绑定） | ✅ 无限制 |

**错误提示规则**：
- Explorer 入队任意机器人 → `"Explorer tier cannot use robots"` (403)。
- Amplifier 超 `training` 日限 → 403，含 `robot_name`。
- Amplifier 超 `open` 终身限 → 403，含 `"Amplifier members have reached the 3 total uses limit for {robot_name}"`，前端据此弹升级弹窗。

**通用队列互斥**（所有等级均生效）：用户同一时间只能在一个机器人队列中处于 `waiting/active` 状态。

**Fast Track**（仅 Innovator）：全机器人合计每天 6 次，超出后仍可入队但不标记 Fast Track，返回提示 `"You have reached the maximum 6 fast tracks a day"`。

### 3. Fleet 机器人购买系统

#### 获取可购机器人 `/api/fleet/get-available-robots`（公开接口）

- 无需认证，返回 `is_fleet_visible = true` 的机器人列表，按 `fleet_order` 排序。
- 返回字段：`machine_id`、`manufacture`、`product_name`、`machine_description`、`fleet_selling_points`、`fleet_functionality_points`、`fleet_purchase_price` 等。

#### 提交购买申请 `/api/fleet/request-purchase-robot`

- 限流：4次/分钟（IP 维度）。
- 权限：**Amplifier Member 及以上**（Bearer token 鉴权）。
- 必填：`user_id`、`machine_id`、`email`、`first_name`、`last_name`、`phone_number`（≥7 位数字）。
- 选填：`telegram`、`project_company`、`location`。
- 校验：`machine_id` 须 `is_fleet_visible = true`；新邮箱做可送达性校验。
- 写入 `fleet_purchase_info`，异步发送确认邮件，更新 `email_sent` 字段。

#### 管理员查看购买申请 `/api/admin/get-fleet-purchase-info`（需 JWT）

- 分页，联查 `data_sample_machines` 得 `robot_name`。

### 4. 用户统计

| 接口 | 权限 | 内容 |
|------|------|------|
| `/api/user-stats` | JWT | 各会员等级用户数 + 活跃 TeleOp 用户数 |
| `/api/user-stats-v2` | JWT | 等级 × 登录渠道交叉表；TeleOp 会话数/总时长/活跃用户数 |

---

## 九、Operator 操作员系统

Operator 系统完整闭环：**注册机器人 → 申请审核 → 上传数据 → QA 评审 → Dashboard 统计**。

### 1. 机器人注册

| 接口 | 说明 |
|------|------|
| `GET /api/operator/get-robot-registration-options` | 返回 `data_sample_machines` 可选型号（按 manufacturer 分组） |
| `POST /api/operator/register-robot/validate-serial-number` | 校验序列号格式（Airbot/Agilex/I2rt/RealMan），返回 `valid: true/false/null` |
| `POST /api/operator/register-robot` | 注册机器人到 `data_machines`，首台自动设为默认生产者 |
| `POST /api/operator/unregister-robot` | 注销机器人（有上传记录则拒绝；删完所有机器人时清除 operator 角色和申请） |
| `POST /api/operator/set-default-producer` | 切换默认生产者（仅 1 台时不可切换） |

**序列号格式规则**：

| 制造商 | 长度 | 前缀要求 |
|--------|------|---------|
| Airbot | 16 | `PZ` 开头 + 9 位数字结尾 |
| Agilex Robotics | 23 | `MD` 开头 |
| I2rt Robotics | 11 | `JG` 开头 |
| RealMan | 16 | `RM` 开头 |
| 其他 | — | 返回 `valid: null` |

### 2. Operator 成员资格申请

| 接口 | 说明 |
|------|------|
| `GET /api/operator/get-user-data` | 返回已注册机器人列表 + `operator_status`（`approved`/`pending`/`denied`/`null`） |
| `POST /api/operator/submit-membership-application` | 提交申请（需邮箱归属校验 + 至少1台机器人 + 无 pending 申请）→ 写 `data_operator_applications`，通知管理员 |

### 3. 管理端：申请审核

| 接口 | 说明 |
|------|------|
| `GET /api/admin/get-operator-applications`（JWT） | 按 `status` 筛选，分页返回（含会员等级、积分、钱包、机器人列表） |
| `POST /api/admin/review-operator-application`（JWT） | 批准：`user_role = 'operator'` + 发通知邮件；拒绝：清空 `user_role` |

### 4. Operator Dashboard

| 接口 | 说明 |
|------|------|
| `GET /vla/operator-dashboard/summary` | 自查：平均 QA 分、episode 数、日均上传时长、趋势数据（支持 `7d/30d/90d/1y/all`） |
| `GET /vla/operator-dashboard/uploads` | 自查：上传分页列表（可按 `machine_id` 筛选，最大 `page_size=50`） |
| `GET /vla/admin/operator-dashboard/summary`（JWT） | 管理员查看指定 `user_id` 的统计 |
| `GET /vla/admin/operator-dashboard/uploads`（JWT） | 管理员查看指定 `user_id` 的上传列表 |

---

## 十、VLA Admin 管理接口

> 所有接口均需 JWT 认证。

### 1. 样本机器人型号管理 `/api/vla-admin/sample-machines`

| 方法 | 说明 |
|------|------|
| GET | 返回 `data_sample_machines` 全部数据及列元数据 |
| POST (Upsert) | 按 `machine_id` 插入或更新，动态校验列类型与约束 |

### 2. 任务管理 `/api/vla-admin/tasks`

| 方法 | 说明 |
|------|------|
| GET | 返回 `data_tasks` 全部任务及列元数据 |
| POST | 创建任务（自动生成 `task_id`，支持 `preview_video_upload_id` 解析） |
| PATCH `/<task_id>` | 动态更新指定字段（忽略未知字段） |
| POST `/<task_id>/set-visibility` | 独立设置 `is_visible_beta` / `is_visible_production`（布尔，至少提供一个） |

### 3. Hex AI 管理接口

| 接口 | 说明 |
|------|------|
| `GET /api/vla-admin/hex-capability-requests` | 列出用户在 Hex AI 中提出的能力缺口请求，支持 `status` 过滤（`pending/approved/denied/all`），分页 20条/页 |
| `GET /api/vla-admin/hex-capability-requests/export` | 导出当前 `status` 过滤下的请求为 Excel（文件名：`hex-capability-requests-{status}-{YYYYMMDD}.xlsx`） |
| `GET /api/vla-admin/hex-sessions/<session_id>/chat-logs` | 查看指定 session 的聊天日志，按 `turn_number`/`event_index` 排序（最大 500 条），表不存在时返回空列表 |

---

## 十一、QA 审核员管理

> 所有接口均需 JWT 认证，通过 `users.user_role` 字段区分 QA 角色。

| 接口 | 说明 |
|------|------|
| `GET /api/admin/get-qa-reviewers` | 分页返回所有 `user_role IN ('qa', 'senior qa', 'expert qa')` 的用户，含 `review_count`、平均 QA 分；排序：expert qa > senior qa > qa，同角色按评审数降序 |
| `POST /api/admin/set-qa-reviewer-role` | 按 `user_id`/邮箱/钱包地址查找用户；传 `qa`/`senior qa`/`expert qa` 设置角色，传空值/`null` 取消角色 |

---

## 十二、第三方渠道集成

### 1. Galxe 渠道集成

#### 渠道来源标记

- 前端在 `/api/get-users` 请求中附加 `?source=galxe`，系统仅接受 `'galxe'`，其他值忽略。
- 新钱包用户创建时，将 `acquisition_source = 'galxe'` 写入 `users`。

#### 注册验证接口 `/api/galxe/verify-registration`

- **调用方**：Galxe 平台 REST API（需 `GALXE_REST_API_KEY` Header 鉴权）。
- **入参**（Query）：`address` / `wallet_address` / `solana_address` / `evm_address`（四选一）。
- **逻辑**：查询 `users` 中 `acquisition_source = 'galxe'` 且对应链地址匹配的用户。
- **返回**：已注册 → `registered: true, eligible: 1`；未注册 → `registered: false, eligible: 0`。
- `GALXE_REST_API_KEY` 未配置 → 503。

### 2. Partner Device Listing（合作伙伴设备入驻）

#### 提交入驻申请 `/api/partner-device/request-listing`

- **限流**：4次/分钟 + 10次/小时（IP 维度）。
- **权限**：Amplifier Member 及以上（Bearer token 鉴权）。
- **必填**：`manufacturer`、`model`、`deviceType`（须在 `DEVICE_TYPES` 范围内）、`serialFormat`（≤50 字符）、`examples`（换行分隔，≤5 条，每条 ≤50 字符）、`firstName`、`lastName`。
- **选填**：`specUrl`、`email`（账号有邮箱时优先用账号邮箱）。
- **序列号验证**：后端解析 `serialFormat` 生成正则，对 `examples` 逐一校验：
  - 全通过 → `validation_passed: true`。
  - 有失败 → `validation_passed: false`，含 `failed_examples` 和 `failure_reason`（`examples_mismatch` / `format_parse_error`）。
- 结果序列化为 JSONB 写入 `data_partner_device_requests`，返回新记录 `id`。

#### 管理员查看申请 `/api/admin/get-partner-device-requests`（需 JWT）

- 分页返回所有申请，按提交时间降序。

---

## 十三、管理端其他功能

### 管理员白名单

| 接口 | 说明 |
|------|------|
| `POST /api/add-admin-whitelist`（JWT） | 添加钱包地址到白名单 |
| `DELETE /api/delete-admin-whitelist`（JWT） | 按 `admin_id` 删除 |
| `GET /api/get-admin-whitelist`（JWT） | 查看白名单列表 |

### 管理员邀请码

| 接口 | 说明 |
|------|------|
| `POST /api/create-admin-invite-code`（JWT） | 创建一次性邀请码 |
| `GET /api/get-admin-invite-codes`（JWT） | 查看所有邀请码及使用状态 |
| `POST /api/use-admin-invite-code` | 用户凭邀请码绑定账号（一次性，已用返回 409） |
| `GET /api/check-admin-invite-binding` | 用户查询自己是否已被邀请码绑定 |

### 其他

- **反作弊检测** `detect_and_reset_bots()`：检测未来日期或项目启动前的积分交易，识别疑似刷分账户记录到 `detected_bot_users`。
- **支付对账快照** `/api/verify-payment-records`：多链/Stripe 对账记录查询与更新。

---

## 十四、关键要点小结

| 维度 | 要点 |
|------|------|
| **会话模型** | 所有登录方式最终收敛到 `users.hash_code`，服务端旋转 token 实现登出 |
| **账户统一** | `linked_email` + `linked_wallet_address` 将邮箱与多链钱包合并为同一身份，以邮箱为主 |
| **双维度角色** | `user_class`（付费驱动）与 `user_role`（审批驱动）独立控制权限 |
| **支付完整性** | Stripe Webhook + 管理员主动对账 + 链上验证，三重保障不漏单 |
| **积分防刷** | reCAPTCHA、邮箱黑名单、时间区间检测、行锁防并发结算 |
| **Operator 闭环** | 注册机器人 → 申请审核 → 上传数据 → QA 评审 → Dashboard 统计 |
| **商业化扩展** | Galxe 渠道追踪、Fleet 机器人购买、Partner Device 入驻，持续扩展平台能力 |
