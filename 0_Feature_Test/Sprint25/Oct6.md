# Oct 6 改动：业务逻辑、测试分析与测试用例

> 日期：2026-10-06（UTC+8）  
> 范围：`app-prismax-rp`、`app-prismax-rp-backend`、`prismax-marketing-rp` 当日合入 `testing` 的全部 commit。  
> 分析基线：三仓 `git pull` 后的本地 `testing`，与 `origin/testing` 一致。  
> 最终 HEAD：frontend `8cdcf90` / backend `8cb5a1d` / marketing `15575b5`。  
> 本文只测最终态。Merge commit 本身没有独立逻辑。

与 [`PriceControl.md`](./PriceControl.md) 的关系：会员访问池、48 条预览封顶、整任务选择仍以该文档为准。本文覆盖的目录计数改动**取代**其中「Browse 计数按 asset、`ASSETS_PER_EPISODE = 4`」这一条展示规则。配额单位仍是 episode，没有改成 asset。

---

## 1. 范围与 Commit

### 1.1 app-prismax-rp

| Hash | 时间 (+08) | 作者 | 说明 |
| --- | --- | --- | --- |
| `bb351a4` | 06:31 | Aparna Rangamani | PRIS-373：Admin 单发 / 群发邮件第一版 |
| `591e060` | 08:50 | Aparna Rangamani | PRIS-373：Send Email 弹窗收到 Data Subscribers shared |
| `25665b0` | 09:06 | Aparna Rangamani | PRIS-373：四张表增加 Download CSV |
| `d3e68ff` | 11:10 | Aparna Rangamani | PRIS-373：三张获客表展示 IP 与地点 |
| `8cdcf90` | 11:14 | aparna-prismax | Merge PR #88 `PRIS-373-marketing-contact-email-updates` |

### 1.2 app-prismax-rp-backend

| Hash | 时间 (+08) | 作者 | 说明 |
| --- | --- | --- | --- |
| `0db6399` | 02:45 | lanmanc | 个人月付数据订阅、Stripe 账期额度 |
| `22299bd` | 02:45 | lanmanc | Merge `testing` |
| `12b04d6` | 05:49 | lanmanc | `/auth/save` 拒绝未校验的 Google / Apple 登录 |
| `65479a1` | 06:29 | Aparna Rangamani | PRIS-373：单发与群发用户邮件 |
| `b7a7a42` | 11:03 | Aparna Rangamani | PRIS-373：获客表单记录 IP 与地理信息 |
| `8cb5a1d` | 11:13 | aparna-prismax | Merge PR #82 `PRIS-373-marketing-contact-email-updates` |

### 1.3 prismax-marketing-rp

| Hash | 时间 (+08) | 作者 | 说明 |
| --- | --- | --- | --- |
| `0338cbe` | 02:45 | lanmanc | Account 订阅结账；首页 / Account 价格与额度改读数据库 |
| `bc82180` | 09:35 | lanmanc | 目录计数去掉 ×4，按 episode 展示 |
| `15575b5` | 11:49 | lanmanc | 浏览器下载直连 GCS 签名链接，删除 `/api/download-file` |

### 1.4 主题与依赖

| 主题 | Frontend | Backend | Marketing | 依赖 |
| --- | --- | --- | --- | --- |
| 个人月付订阅 | — | Stripe Checkout / Portal / Webhook；额度窗口跟已付账期 | Account 结账；首页与 Account 展示库内价格和额度 | 先跑订阅 SQL，并写入已核对的 Stripe Price ID。见 §3 |
| 旧登录接口收紧 | 无 UI 改动 | `/auth/save` 只接受邮箱验证码 | — | Google / Apple 必须走 `/auth/oauth-login` |
| PRIS-373 邮件 / CSV / IP | Data Subscribers 四区按钮与列 | 发信 API、IP 落库、Admin 列表带 IP | — | GeoIP 库 `gs://prismax-geoip/geoip/GeoLite2-City.mmdb`；发信依赖现有邮件通道 |
| 目录按 episode 计数 | — | 计数接口本身未改口径 | Browse 侧栏、任务、机器、已选配额去掉 ×4 | 与 [`PriceControl.md`](./PriceControl.md) 的 asset 文案冲突，以本文为准 |
| 浏览器直连 GCS | — | 签名仍在 `/data/downloads/ui` | 删除 Next 代理，浏览器直接拉签名 URL | 签名 URL 必须允许浏览器跨域读取 |

---

## 2. 总体业务影响

1. 登录用户可以在 Account 页自助购买 Discover 或 Researcher 月付。价格和每月 episode 额度来自 `data_api_download_membership_plans`，不再写死在前端。只有 Stripe 发票已付，才会开通并推进额度窗口。
2. 客户端不能再给 `/auth/save` 传 Google / Apple 类型来跳过邮箱验证码。
3. Admin 可对 Contact Sales、Egocentric Waitlist、Discover/Researcher Interest、Robotics Data Beta 单发或群发「数据银行已开放」类邮件，并导出 CSV。前三张表同时展示提交者 IP 和地点。
4. Robotics Data 目录上的数字改为 episode，不再乘 4。My Data 浏览器下载不再经过营销站自己的下载代理。

---

## 3. 个人月付数据订阅

### 3.1 业务逻辑

数据在 `data_api_download_membership_plans`（套餐价格、额度、`stripe_price_id`）和 `data_user_subscriptions`（用户当前订阅快照）。组织权益表不读不写。已下载进个人库的 episode 不因换期删除。

公开可买套餐只有 `discover` 和 `researcher`。`basic` / `pro` 如果出现在用户的 `user_data_download_membership` 上，下载准入同样要求一条当前已付且未过期的订阅，否则报 `An active, paid data subscription is required.`

主要接口（data-pipeline，前缀 `/prismax-data`）：

| 方法 | 路径 | 谁可调 | 作用 |
| --- | --- | --- | --- |
| GET | `/data/subscriptions/plans` | 无需登录 | 返回 ACTIVE 的 Discover / Researcher：额度、月价、是否已配置 Stripe Price |
| GET | `/data/subscriptions/status` | 登录用户 | 读已落库快照。`refresh=1`，或状态是 active 但当前不在已付窗口内时，向 Stripe 再同步一次 |
| POST | `/data/subscriptions/checkout` | 登录用户 | 创建或复用 Stripe Checkout。body：`membership`、`request_id` |
| POST | `/data/subscriptions/confirm` | 登录用户 | 用 `session_id` 核对这笔 Checkout 属于当前用户，再同步订阅 |
| POST | `/data/subscriptions/portal` | 登录用户 | 打开 Stripe Billing Portal |
| POST | `/data/subscriptions/webhook` | Stripe | 校验签名后同步订阅；同一 `stripe_event_id` 只处理一次 |

开通规则：

- 订阅 metadata 的 `purpose` 必须是 `personal_data_subscription`，且 `user_id` 对得上。
- Stripe Price 必须是活跃的月付 USD 许可价格，金额与库里的 `monthly_price_usd` 一致，livemode 与 `DATA_STRIPE_LIVEMODE` 一致。对不上返回 503，不创建结账。
- 已有未取消、未过期的订阅时，Checkout 返回 409，文案要求改走 Manage billing。同一用户同时只允许一条这类订阅。
- **只有**最新发票 `status=paid`，且账单行覆盖当前账期、价格 ID 一致，才写入 `membership`、`paid_through_at`、`quota_period_*`。未付款的升级保留上一期已付方案和窗口。旧发票重放不会把窗口往回拨，也不会增加已用额度。
- 额度窗口等于该次已付 Stripe 账期，不再按自然月 `YYYY-MM` 切。下载计数仍只统计这个窗口内新写入个人库的 episode。
- 同步成功后，把 `users.user_data_download_membership` 更新成这条个人订阅的套餐，供旧读取路径兼容。

Account 页（`/account`）：

- 价格和「N episodes / month」来自 `plans`。缺 Discover 或 Researcher、额度或价格非法时，两套都不展示数字，并给出 Retry。
- Enterprise 仍是「Talk to sales」，不走 Stripe。
- 没有可管理订阅时，Discover / Researcher 按钮是 Subscribe，跳转 Checkout。
- 已有可管理订阅时，其他套餐按钮文案是 Change plan，实际打开 Billing Portal，不直接换价。当前套餐按钮禁用。
- 从 Checkout 成功返回（`?subscription=success&session_id=`）后最多轮询 confirm 10 次、间隔 1.5 秒。仍未 entitled 时提示用 Refresh status。取消返回只提示方案未变。
- 已开通时展示已用 / 月额度，以及重置时间（额度窗口结束，UTC）。

首页 Plans 只改展示：月价和 episode 额度同样读 `plans`。按钮仍走原来的获客链接，不在首页直接结账。

部署前必须先建表。两条 SQL 二选一，不要当成两个都要再跑一遍的前置：

- `app_prismax_data_pipeline/sql/20261002_personal_data_subscriptions.sql`：只建表和 `stripe_price_id` 列，Price ID 需另行 UPDATE。
- `app_prismax_data_pipeline/sql/20261002_cloud_sql_personal_subscriptions_live.sql`：同一套表，并写入已确认的 Live Price ID。

还需要 data-pipeline 配好 `DATA_STRIPE_API_KEY`、`DATA_STRIPE_WEBHOOK_SECRET`、`DATA_STRIPE_PORTAL_CONFIGURATION_ID`、`DATA_SUBSCRIPTION_ACCOUNT_URL`（https；仅非 live 允许 localhost http）。缺任一项时 `available=false`，Subscribe 按钮禁用。

### 3.2 测试分析与风险

| 风险 | 分析 | 验证重点 |
| --- | --- | --- |
| 未建表或未填 Price ID 就发版 | Checkout 对空 `stripe_price_id` 返回 503 | 按钮禁用或明确失败，不产生半截 Stripe Customer 以外的脏订阅。plans 的 `purchasable` 为 false |
| 库内价格和 Stripe Price 不一致 | `validate_price` 直接 503 | 改库里月价但不改 Stripe 时不能结账 |
| 未付款就开通 | `apply_paid_state` 要求 paid 且账单行覆盖当前账期 | 卡在 incomplete / 待支付时，会员和额度窗口保持原样；Account 显示 Awaiting payment confirmation |
| 重复订阅 | 用户锁 + 远端订阅检查 + 部分唯一索引 | 连点 Subscribe、两个标签同时结账，最终只有一条未取消订阅 |
| 换期把历史下载清掉或重复计数 | 所有权仍在 `data_user_library_episodes`，用量按窗口过滤 | 新账期已用从 0 起算，My Data 旧 episode 还在 |
| `basic` / `pro` 旧用户被拦住 | 这两档现在也要有已付订阅行 | 仅有 membership 字段、没有 `data_user_subscriptions` 的用户，下载和 Hex 都应拒绝 |
| 组织会员被误伤 | 本模块不写组织表 | 只靠 Organization 进 My Data 的路径保持 [`PriceControl.md`](./PriceControl.md) / 既有门禁，不要求个人 Stripe 订阅 |
| Webhook 与 confirm 竞态 | 两边都调用同一套 sync，事件 ID 去重 | 成功回跳和 webhook 后状态一致，不双计额度 |
| 首页和 Account 价格不一致 | 两边都读同一个 plans 接口 | 改库后刷新，两处月价和额度相同；Enterprise 不变 |
| 取消结账误开通 | success 才 confirm | `subscription=canceled` 不写订阅 |

### 3.3 测试用例

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| OCT6-SUB-001 | P0 | 未订阅用户购买 Discover | 用户无个人订阅；Discover 的 Stripe Price 与库内月价一致；`purchasable=true` | Account 点 Discover 的 Subscribe，用 Stripe 测试卡付清，回到 Account | 跳转 Checkout；回来后状态 active 且 entitled；`users.user_data_download_membership=discover`；当前套餐标记在 Discover；展示已用 / 月额度和重置日 |
| OCT6-SUB-002 | P0 | 购买 Researcher | 同上，选 Researcher | 完成支付 | membership 与额度等于 Researcher 行，不是 Discover |
| OCT6-SUB-003 | P0 | 未付款不开通 | Checkout 打开后不支付，或使用会停留在 incomplete 的方式 | 回到 Account，并直接查 `data_user_subscriptions` | 无 entitled；若已有上一档已付方案，套餐和 `quota_period_*` 不变；界面可为 Awaiting payment confirmation |
| OCT6-SUB-004 | P0 | 取消结账 | 进入 Checkout 后点返回 / 取消 | 观察 Account 提示和库 | 文案为方案未变；不新增 active 订阅 |
| OCT6-SUB-005 | P0 | 已有订阅不能再开一单 | 用户已有未取消订阅 | 再点另一套餐的 Change plan，并另开标签直接调 checkout | Change plan 进入 Billing Portal；checkout API 409，提示已有订阅、使用 Manage billing |
| OCT6-SUB-006 | P0 | 额度窗口跟账期 | 刚付清的订阅 | 在窗口内首次把 episode 加入 My Data，看配额；把 `quota_period_end` 改到过去后再请求 | 窗口内按 episode 扣减；过期后不再 entitled，不能继续新增。已在库内的 episode 仍在 My Data |
| OCT6-SUB-007 | P0 | 价格以数据库为准 | 把 Discover 的 `monthly_price_usd` 和对应 Stripe Price 一起改成新金额 | 刷新首页 Plans 和 Account | 两处都显示新月价和新的 `N episodes / month`。只改库、不改 Stripe 时 Subscribe 失败，不进入可支付页面 |
| OCT6-SUB-008 | P1 | plans 不完整 | 临时让 Researcher 行不是 ACTIVE，或额度非法 | 打开 Account 和首页 | 不展示半套数字；有错误文案和 Retry；Enterprise 仍可 Talk to sales |
| OCT6-SUB-009 | P1 | 配置缺失 | 去掉 webhook secret 或 portal configuration | 看 `status.available`，点 Subscribe | available 为 false；按钮禁用或 503，不创建结账 |
| OCT6-SUB-010 | P1 | Webhook 重放 | 对同一 `invoice.paid` 事件投递两次 | 查订阅行和 webhook 表 | 只处理一次；`paid_through_at` 不回退；已用 episode 不增加 |
| OCT6-SUB-011 | P1 | 他人的 session | 用户 A 完成支付，用户 B 拿 A 的 `session_id` 调 confirm | B 调用 confirm | 403，B 的订阅不变 |
| OCT6-SUB-012 | P1 | Portal 管理 | 已付用户点 Manage billing，在 Portal 设为期末取消 | 返回 Account 并 Refresh | `cancel_at_period_end=true`；文案由 Next renewal 变为 Access ends；当前窗口内仍 entitled |
| OCT6-SUB-013 | P1 | 旧 basic / pro | 用户 membership 为 basic 或 pro，且没有已付订阅行 | 打开 Browse 并尝试加入 My Data；如有 Hex 入口再调一次 | 拒绝，并提示需要有效的已付数据订阅 |
| OCT6-SUB-014 | P1 | 组织用户回归 | 用户无个人订阅，但是某 Organization 成员 | 打开 My Data；再尝试目录下载 | My Data 门禁保持原规则；目录下载仍要求个人 membership，不因本需求意外放开或收紧组织数据 |
| OCT6-SUB-015 | P2 | 未登录 | 无 gateway token | 打开 Account；直接 GET plans、POST checkout | plans 200；checkout / status 401。Account 不进入结账 |
| OCT6-SUB-016 | P2 | 成功回跳延迟 | 支付完成但 webhook 稍晚 | 停在 Account 等待 | 先显示 Confirming your payment…；10 次内开通则成功文案；超时则提示 Refresh status，手动刷新后变为 active |

---

## 4. `/auth/save` 拒绝社交登录绕过

### 4.1 业务逻辑

`POST /auth/save` 只处理邮箱登录。

- `login_type` 不是 `'0'`：400，`Use OAuth login for Google or Apple`。不再读取客户端自称的 Google / Apple 类型。
- 没有 email：400，`Authentication error`。
- 通过以上检查后，必须用 `_verify_email_code` 证明该邮箱的验证码。验证码失败 400。
- Google / Apple 仍只走 `POST /auth/oauth-login`，由服务端校验 provider token。

没有新表。营销站登录 UI 若本来就走 oauth-login，界面可以不变。

### 4.2 测试分析与风险

| 风险 | 分析 | 验证重点 |
| --- | --- | --- |
| 旧客户端仍传 type 1 / 2 | 接口直接 400 | 不能靠伪造 body 登录或注册 |
| 邮箱登录被误伤 | type 0 仍校验验证码 | 正确验证码可以登录；错误、过期、空验证码不行 |
| OAuth 被一起关掉 | 本改动不进 oauth-login | Google、Apple 正常登录 |
| 只挡登录、不挡别的写接口 | 范围仅 `/auth/save` | 抽一条无关的已登录 API，确认未被这个判断误伤 |

### 4.3 测试用例

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| OCT6-AUTH-001 | P0 | 伪造 Google 类型 | 已知邮箱，不提供该邮箱验证码 | `POST /auth/save`，`login_type=1`，带 email | 400，`Use OAuth login for Google or Apple`；用户表不新增、不发 token |
| OCT6-AUTH-002 | P0 | 伪造 Apple 类型 | 同上 | `login_type=2` | 同 001 |
| OCT6-AUTH-003 | P0 | 邮箱验证码仍可用 | 对该邮箱调用 send-verification-code 并取得验证码 | `login_type=0`，email + 正确 code，带上原有 recaptcha | 登录或注册成功，返回原有 token 字段 |
| OCT6-AUTH-004 | P0 | 错误验证码 | type 0 | 使用错误或过期 code | 400，不发 token |
| OCT6-AUTH-005 | P1 | 缺邮箱 | `login_type=0`，无 email | 调用 `/auth/save` | 400，`Authentication error` |
| OCT6-AUTH-006 | P1 | 正式 OAuth | Google 或 Apple 测试账号 | 走产品登录按钮 | 成功，请求打到 `/auth/oauth-login` 而不是 `/auth/save` |
| OCT6-AUTH-007 | P2 | 空 body / 缺 type | — | `{}` 或不传 login_type | 400，且不 500 |

---

## 5. PRIS-373：Admin 发信、CSV、IP

### 5.1 业务逻辑

Admin Data Subscribers 四个分区都能发信和导出 CSV。发信需要 Admin JWT，`role=admin`。

| 分区 | 单发 | 群发 | 邮件 | 发出后写入 |
| --- | --- | --- | --- | --- |
| Contact Sales | `POST .../contact-sales-submissions/{id}/send-email` | `.../send-email-bulk` | 主题 `The PrismaX data bank is open to you`，开头感谢联系销售 | `user_email_sent_at`、`user_email_sent_by_admin_id` |
| Egocentric Waitlist | `.../marketing-egocentric-waitlist-requests/{id}/send-email` | `.../send-email-bulk` | 同一主题，开头感谢加入 waitlist | 同上 |
| Discover/Researcher Interest | `.../marketing-interest-access-requests/{id}/send-email` | `.../send-email-bulk` | 主题 `You’re in — the PrismaX data bank is open` | 同上 |
| Robotics Data Beta | 行内仍走原 review approve | `POST .../robotics-data-beta-applications/approve-bulk` | 原批准信：`You’re approved — the PrismaX data bank is open` | `approval_email_sent_at`，并把 `status` 置为 `approved` |

群发规则：

- 弹窗先拉 `.../email-recipients?include_sent=`。同一邮箱合成一行，默认全选。
- 默认不带已发送记录。勾选 Include already sent 后才把它们列入收件人。
- 前端按收件人分组，每批最多 20 个 id 调 bulk。同一邮箱只发一封，多个 id 一起标已发送。
- 已发送且这次未要求重发的，记为 skipped。没有邮箱，或 Beta 的 `status=denied`，记为 not_eligible，不发信。
- 发送中不能关弹窗。结束后显示 Sent to N recipients；失败列出邮箱。关闭时若有成功发送，列表刷新。
- 三张获客表的行内 Send email 是单条发送，不经过弹窗。

CSV：

- Contact Sales、Waitlist、Interest 会按 `page_size=500` 翻完所有页再下载。列里包含 IP Address、Location、User Email Sent At。
- Beta 的 Download CSV 导出当前已加载列表，列是 Email、User ID、Requested At、Company、Role、Robot Platforms、Access Need、Approval Email Sent At。没有 IP 列。

IP：

- Contact Sales、Interest Access、Egocentric Waitlist 在提交成功后记 IP。优先 `CF-Connecting-IP`，否则用连接地址。
- 非法 IP、`127.0.0.1`、`::1`、`10.*`、`192.168.*` 不记。公网 IP 写入 `ip_addresses`（GeoLite2 的国家、城市、经纬度、时区）和 `ip_address_history`。记 IP 失败只打日志，不影响表单成功。
- Admin 这三张表 LEFT JOIN 出 `ip_address` 和 `location`（城市, 国家）。未发送的行排在前面，其次按创建时间倒序。
- Beta 申请不记这套 IP。

### 5.2 测试分析与风险

| 风险 | 分析 | 验证重点 |
| --- | --- | --- |
| 群发把已发用户又打一遍 | 默认 `include_sent` 为 false，行锁后再看 sent 列 | 不勾选时已发送行被跳过，收件箱只有一封 |
| 同一人多条表单收到多封 | 按小写邮箱合并 | 一个邮箱一封；相关行都写上 sent_at |
| Beta 拒绝用户被发批准信 | `status <> 'denied'` 才合格，发出后改 approved | denied 出现在 skipped，状态仍是 denied |
| 非 Admin 发信 | 四个发信入口都查 `role=admin` | 普通用户 JWT 403 |
| CSV 只含当前页 | 获客表循环 total_pages | 超过 500 行时文件行数等于总条数 |
| IP 被私网或伪造头污染 | 私网直接 return；公网才解析 | 本机直连不产生地理行；经 Cloudflare 的公网提交能在 Admin 看到 |
| 记 IP 失败导致表单失败 | 记录包在 try 里，失败只打日志 | 表单仍 200，Admin 上 IP 为空 |
| 单发和群发状态不一致 | 都写同一 sent 列 | 单发后该行不再出现在默认群发名单，列表排序沉底 |

### 5.3 测试用例

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| OCT6-MAIL-001 | P0 | Contact Sales 单发 | Admin 登录；有一条未发信的销售表单，邮箱真实可收 | 行内点 Send email | 按钮变为 Sending… 后恢复；该行 User Email Sent At 有值；收件箱一封，主题 `The PrismaX data bank is open to you`，正文感谢联系销售 |
| OCT6-MAIL-002 | P0 | Waitlist 与 Interest 单发 | 两张表各一条未发送 | 分别点 Send email | Waitlist 主题与销售相同，正文提到 waitlist。Interest 主题为 `You’re in — the PrismaX data bank is open` |
| OCT6-MAIL-003 | P0 | 默认群发跳过已发送 | 同一张表里一条已发送、两条未发送，邮箱互不相同 | Send email to all，不勾 Include already sent，发送 | 只发给两条未发送；已发送那条不在名单或被跳过；总结 Sent to 2 recipients |
| OCT6-MAIL-004 | P0 | 同一邮箱合并 | 同一邮箱有两条未发送 Interest | 群发，确认名单里该邮箱只有一行但带两个 id | 只收到一封；两条记录的 sent_at 都被写上 |
| OCT6-MAIL-005 | P0 | 重发 | 一条已发送 | 勾选 Include already sent，选中后发送 | 再收一封；sent_at 更新 |
| OCT6-MAIL-006 | P0 | Beta 批准群发 | 一条 pending、一条 denied | 对 Beta 点 Send email to all，不包含已批准 | pending 收到批准信且 status 变为 approved；denied 不发信、状态不变 |
| OCT6-MAIL-007 | P1 | 取消选择 | 名单 3 人 | Deselect all，再只选 1 人发送 | 只发出 1 封；未选的 sent_at 仍空 |
| OCT6-MAIL-008 | P1 | 超过 20 人 | 至少 21 个不同未发送邮箱 | 全选发送 | 前端分成至少两批请求；全部成功时总结人数等于邮箱数，不是 id 数 |
| OCT6-MAIL-009 | P1 | 发送中关闭 | 打开弹窗后开始发送 | 点遮罩、关闭和 Esc | 发送完成前关不掉；完成后可关，列表刷新 |
| OCT6-MAIL-010 | P1 | 非 Admin | 普通用户 token | 调任一 send-email 与 send-email-bulk | 403，`Admin access required`；数据库 sent 列不变 |
| OCT6-MAIL-011 | P2 | 无收件人 | 表为空，或全部已发送且不包含已发送 | 打开群发弹窗 | 无可用收件人，发送按钮不可完成发送；不报 500 |
| OCT6-CSV-001 | P0 | 获客 CSV 含 IP 与全量 | Contact Sales 超过一页，且含有 IP 的行和未记 IP 的行 | Download CSV | 文件名以 contact-sales 开头；行数等于总条数；有 IP Address、Location、User Email Sent At 列；时间是 UTC ISO |
| OCT6-CSV-002 | P0 | 另两张获客表 | Waitlist、Interest 各有数据 | 分别 Download CSV | 列与各表字段一致，都含 IP Address 和 Location |
| OCT6-CSV-003 | P1 | Beta CSV | 有 pending 和已发批准信的申请 | Download CSV | 列含 Approval Email Sent At，不含 IP；平台显示 YAM 等标签而不是原始 key |
| OCT6-CSV-004 | P2 | 空表 | 某张获客表无数据 | 点 Download CSV | 不下载损坏文件；按钮有 Preparing… 状态后恢复。Beta 无数据时按钮禁用 |
| OCT6-IP-001 | P0 | 公网提交写入 IP | 从带 `CF-Connecting-IP` 的公网地址分别提交 Contact Sales、Interest、Waitlist | Admin 打开三张表 | 新行有 IP 和地点；`ip_addresses` 有国家/城市；表单本身成功 |
| OCT6-IP-002 | P0 | 私网不记 | 从 127.0.0.1 或 10.x / 192.168.x 提交 | 查 Admin 和 `ip_address_history` | 表单成功；该行没有 IP，也没有对应 history |
| OCT6-IP-003 | P1 | 未发送排在前面 | 同一张表既有已发信也有未发信 | 刷新列表 | `user_email_sent_at` 为空的行在前；同组内创建时间新的在前 |
| OCT6-IP-004 | P1 | 地理库不可用 | 暂时让 GeoIP 文件缺失后提交公网表单 | 看接口响应和 Admin | 表单仍成功；IP 为空或只有 IP 无地点，服务不 500。恢复文件后新提交能解析地点 |
| OCT6-IP-005 | P2 | Beta 不出现 IP 列 | 打开 Beta Applications | 看表头和 CSV | 无 IP Address 列 |

---

## 6. 目录计数改为 episode

### 6.1 业务逻辑

`ASSETS_PER_EPISODE = 4` 已从 `roboticDataRules.mjs` 删除。目录数字直接使用接口返回的 episode 数。

受影响的展示：

- 任务侧栏、分类、单个任务、机器筛选徽章：单位从 assets 改为 episodes。
- 任务卡片上的数量单位改为 Episodes。
- 已选统计的标签从 Assets 改为 Episodes，数值等于选中的 episode 数，不再乘 4。旁边的配额也改为 `已选 / 月额度`，两边都不乘 4。
- 机器和任务的分面计数同样不再乘 4。
- Episode 详情里的场景数量改为 episode 口径。

后端 catalog 计数接口没有在这批 commit 里改公式。若接口本来就返回 episode 数，页面现在与接口一致；若线上仍有人对照旧的 asset 截图，数字会变成原来的四分之一，这是预期。

月配额的扣减单位仍是 episode，与 [`PriceControl.md`](./PriceControl.md) 的额度规则一致。变的只是 Browse 上的展示乘数。

### 6.2 测试分析与风险

| 风险 | 分析 | 验证重点 |
| --- | --- | --- |
| 页面残留 ×4 | 常量已删，调用点改为 `countCatalogTaskEpisodes` | 侧栏合计、任务数、机器数、已选数都等于 episode，找不到 assets 文案 |
| 配额被放大 4 倍 | 已选和分母以前都乘 4 | 选 1 条时显示 `1 / 月额度`，而不是 `4 / 额度×4` |
| 计数未加载时的占位 | 失败显示 `— episodes`，加载中显示 `… episodes` | 预览列表仍可用，并有 warning：Episode counts are unavailable |
| 筛选后合计不对 | 机器计数只累加当前选中任务 | 切换任务和机器后，徽章等于当前筛选下的 episode 之和 |
| 和旧文档不一致 | PriceControl 仍写 asset ×4 | 本轮 Browse 以本文为准，不要按旧文案提 bug |

### 6.3 测试用例

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| OCT6-EP-001 | P0 | 侧栏与任务卡 | 某任务 catalog 返回 N 条 episode，且计数已加载 | 打开 Browse，看 All tasks、该分类、该任务、任务卡 | 四处都是 N episodes / Episodes，不是 4N assets |
| OCT6-EP-002 | P0 | 机器筛选 | 两台机器分别有 a、b 条 | 看机器徽章；只选一台；再配合一个任务 | 全选时为 a+b episodes；单选为该机器条数；与任务交集后等于该任务在该机器上的 episode 数 |
| OCT6-EP-003 | P0 | 已选配额 | 月额度为 Q，选中 K 条 episode | 看右侧 Episodes 统计 | 标签是 Episodes；值为 `K / Q`。K=1 时不是 4，分母不是 4Q |
| OCT6-EP-004 | P1 | 计数接口失败 | 阻断 catalog count 请求 | 刷新 Browse | 预览仍在；数量为 `— episodes`；提示 Episode counts are unavailable |
| OCT6-EP-005 | P1 | 计数加载中 | 慢网打开页面 | 计数返回前看侧栏 | 显示 `… episodes`，返回后变成具体数字 |
| OCT6-EP-006 | P1 | 详情弹层 | 打开一条 episode | 看场景数量 | 用 episode 数，不再出现 asset ×4 |
| OCT6-EP-007 | P2 | 无任务 | 过滤到 0 个任务 | 看侧栏 | 0 episodes 或空状态，不出现 NaN、负数或 assets |

---

## 7. 浏览器下载直连 GCS

### 7.1 业务逻辑

My Data 的浏览器下载不再请求营销站 `POST /api/download-file`。该 route 已删除。

流程：

1. 权限、额度和签名仍由 `/data/downloads/ui` 完成。响应里的文件带 `url`（GCS 签名链接）以及 `download_name` 或路径。
2. 浏览器 `fetch(signedUrl)`，`credentials: 'omit'`，不附带登录 token。
3. 用户选了本地目录时，把响应 body 写入该目录下的文件。写入失败会中止 writable，并尽量删掉半截文件。
4. 未选目录时，把内容做成 blob，用 `<a download>` 触发浏览器下载。文件名优先 `download_name`；否则 episode 号加原始文件名，`.mcap` 则用 `{episode}.mcap`。
5. 没有 `url`，或 GCS 返回非 2xx，该文件失败并带文件名，不继续假装成功。

### 7.2 测试分析与风险

| 风险 | 分析 | 验证重点 |
| --- | --- | --- |
| 签名链接不能被浏览器跨域读取 | 代理删除后，CORS 或 Content-Disposition 由 GCS 决定 | 下载成功，Network 里文件请求的 host 是 storage.googleapis.com，不是营销站 |
| 登录态被带到 GCS | fetch 明确 omit credentials | 该请求没有 Authorization，也没有站点 Cookie |
| 旧代理还被调用 | route 文件已删 | 下载过程中没有 `/api/download-file`；直接打开该路径应 404 |
| 目录写入半截文件 | 失败时 abort 并 removeEntry | 中途断网后目录里不留下不可用文件，界面标该条失败 |
| 文件名错误 | mcap 与普通文件分支不同 | `.mcap` 保存为 `{episode}.mcap`；其他文件保留原名并带 episode 前缀 |
| 权限被绕过 | 签名仍在下载 API | 无会员、超额、不属于自己的 episode 在签名阶段失败，不会拿到可下的 URL |

### 7.3 测试用例

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| OCT6-DL-001 | P0 | 单文件浏览器下载 | 已付用户，My Data 中有可下文件 | 不选目录，下载一条 | 浏览器保存文件；Network 先打下载签名接口，再直连 GCS；无 `/api/download-file` |
| OCT6-DL-002 | P0 | 保存到本地目录 | 浏览器支持目录选择 | 选目录后下载一条 mcap 和一条非 mcap | mcap 名为 `{episode}.mcap`；另一个为 `{episode}_{原文件名}`；内容可打开 |
| OCT6-DL-003 | P0 | 无权限拿不到链接 | 无个人订阅的用户，或别人的 episode | 尝试浏览器下载 | 签名接口拒绝；没有发往 GCS 的成功请求 |
| OCT6-DL-004 | P1 | 签名过期或 GCS 4xx/5xx | 使用过期 URL，或阻断 storage 主机 | 触发下载 | 该条失败，提示含文件名和 HTTP 状态；其他已成功的条不受影响 |
| OCT6-DL-005 | P1 | 目录写入中断 | 选目录后，在 pipe 过程中断网 | 看目录和界面 | 该条失败；目录中没有留下同名半截文件 |
| OCT6-DL-006 | P1 | 不携带登录凭证 | 已登录后下载 | 看 GCS 请求头 | 无 Authorization，credentials 不带站点登录态 |
| OCT6-DL-007 | P2 | 旧代理消失 | — | 直接打开 `/api/download-file` | 404 |
| OCT6-DL-008 | P2 | 批量中的一条缺 url | 构造一条无 url、一条正常 | 连续下载 | 缺 url 的失败并点名文件；正常的那条仍保存 |

---

## 8. 跨功能回归

| ID | 优先级 | 场景 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- |
| OCT6-CROSS-001 | P0 | 购买后按 episode 配额下载 | 新订阅用户在 Browse 选 1 条加入 My Data，再浏览器下载 | 已选显示 1 而不是 4；配额扣 1 个 episode；下载直连 GCS |
| OCT6-CROSS-002 | P0 | 发信不改变会员 | 对无订阅用户的 Interest 行发「你已进入」邮件 | 邮件发出；该用户 `user_data_download_membership` 不变，不能因此下载 |
| OCT6-CROSS-003 | P0 | 登录方式互不影响 | 邮箱验证码登录后购买；退出再走 Google 登录 | 两种登录都成功；`/auth/save` 不被 Google 按钮调用 |
| OCT6-CROSS-004 | P1 | Admin 四区不串台 | 从上到下打开 Contact Sales、Interest、Waitlist、Beta | 各表的发送、CSV、IP 列只作用于本表 |
| OCT6-CROSS-005 | P1 | 首页价格与结账分离 | 首页看到数据库月价后点 Discover CTA；再到 Account 点 Subscribe | 首页仍进原来的获客流程；真正扣款只发生在 Account 的 Checkout |
| OCT6-CROSS-006 | P1 | 访问池回归 | 按 [`PriceControl.md`](./PriceControl.md) 抽一条：预览仍最多 48，Researcher 池包含 Discover | 池规则不变；只是计数文案不再乘 4 |
| OCT6-CROSS-007 | P2 | 记 IP 失败不影响发信 | 一条没有 IP 的旧表单 | 仍可单发和出现在 CSV，IP 单元格为空 |

---

## 9. 测试数据与环境

- 三仓 `testing` 已含第 1 节 HEAD。营销站、Admin、user-management、data-pipeline 一起指向这组构建。
- 订阅库已执行 Live SQL 或「建表 SQL + 手工写入 Price ID」二者之一。Discover、Researcher 为 ACTIVE，月价与 Stripe 月付 Price 一致。
- data-pipeline 已配置 Stripe key、webhook secret、portal configuration、Account 回跳 URL。用测试模式时 `DATA_STRIPE_LIVEMODE=false`，且 Price 也是 test price。
- Webhook 能打到 `/data/subscriptions/webhook`。
- GeoIP：user-management 能读 `gs://prismax-geoip/geoip/GeoLite2-City.mmdb`。
- 邮件：测试邮箱能收 Admin 发出的 HTML 邮件。
- 用户：
  - 无订阅的邮箱用户
  - 可完成 Stripe 测试支付的用户
  - 已有 active 订阅的用户
  - membership 为 basic 或 pro、但没有订阅行的用户
  - 仅 Organization、无个人订阅的用户
  - Admin
  - Google / Apple 测试账号
- 获客数据：三张表各有未发送、已发送、同一邮箱两条、无 IP 的旧行。Beta 有 pending、approved、denied。
- My Data：至少一条 mcap、一条非 mcap，属于当前订阅用户。
- 目录：至少一个任务在两台机器上都有 episode，便于对计数。
- 浏览器：桌面 Chrome。目录下载用例需要支持 File System Access API 的 Chrome。

建议单测（环境允许时）：

- backend `app_prismax_data_pipeline/test_data_subscriptions.py`
- backend `app_prismax_user_management/test_auth_save.py`
- marketing `tests/roboticDataRules.test.mjs`
- marketing `tests/browserDownloads.test.mjs`
- marketing `tests/dataMembershipCache.test.mjs`

---

## 10. 发布准入

- [ ] 三仓 `testing` 为 frontend `8cdcf90`、backend `8cb5a1d`、marketing `15575b5`。
- [ ] 订阅表和 Stripe Price ID 已写入目标库；plans 接口能返回两个套餐且 `purchasable=true`。
- [ ] Webhook、Portal、回跳 URL 已在该环境配好。先在测试 Stripe 完成 OCT6-SUB-001 到 006，再切 Live。
- [ ] OCT6-AUTH 的 P0：伪造 type 1/2 不能登录；邮箱验证码和正式 OAuth 仍可用。
- [ ] OCT6-MAIL 的 P0：四类邮件主题和跳过规则正确；Beta denied 不会被发成 approved。
- [ ] OCT6-CSV-001 / 002 与 OCT6-IP-001 / 002：CSV 全量且含 IP；私网不落库。
- [ ] OCT6-EP 的 P0：页面不再出现 ×4 的 assets 计数。
- [ ] OCT6-DL 的 P0：下载直连 GCS，旧 `/api/download-file` 不再被调用。
- [ ] 跨功能 P0 通过。访问池规则仍以 [`PriceControl.md`](./PriceControl.md) 为准。

---

## 11. 已知限制

1. 首页 Plans 只同步价格和额度文案，购买按钮仍走原获客链接。自助扣款只在 Account。
2. 已有订阅时，Change plan 打开 Billing Portal，不会按所点的套餐预选价格。
3. `basic` / `pro` 现在也要求一条已付订阅。只有 membership 字段的旧用户会被下载准入拒绝。
4. IP 只在三张获客表的新提交上记录。历史行和 Beta 申请没有回填。
5. 私网判断只排除回环、`10.*` 和 `192.168.*`，不是完整的保留地址段。
6. 获客 CSV 按 500 行翻页拉全量，数据很大时会连续请求。Beta CSV 只导出当前已加载的申请列表。
7. 群发总结按邮箱行计数。同一封邮件对应多条表单时，Sent to N 的 N 小于 id 数。
8. 目录改成 episode 后，和 10 月 5 日之前按 asset 截图的数字对不上，预期约为原来的 1/4。
