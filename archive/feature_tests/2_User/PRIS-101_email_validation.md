# Commits 影响分析总结

## 📊 概览

**功能**: User Management - Email Verification Code 发送与邮箱风控  
**Commit**: eb724897fcb7e1a39fdfe893c2f3ae209bc15eb4  
**标题**: PRIS-101: add further email validation checks  
**日期**: 2026-01-26 19:23:12 (-0800)  
**作者**: Aparna Rangamani  
**仓库**: app-prismax-rp-backend  
**影响范围**: Backend（`app_prismax_user_management`）  
**变更类型**: 安全增强 / 风控拦截 / 依赖新增  
**风险等级**: ⚠️ 中风险（误杀与网络依赖风险）

---

## 🔍 Commit 详细分析

### 变更文件
- `app_prismax_user_management/app.py`
- `app_prismax_user_management/requirements.txt`

---

## ✅ 核心改动点（行为变化）

### 1) send_verification_code() 新增两层邮箱校验与拦截（对外返回保持“已发送”）
该 commit 在 `send_verification_code()` 中加入“可疑邮箱”拦截逻辑，但在拦截时仍返回：
- HTTP 200
- `{"success": true, "msg": "Verification code sent"}`

目的偏向于：不向外暴露“邮箱是否被系统接受/是否真实发送验证码”，降低枚举与探测风险。

#### 第一层：first-pass（早期、低成本拦截）
新增逻辑：
- 将 email 转小写后取域名：`email_domain = email.split('@')[1] if '@' in email else None`
- 认定可疑条件（任一命中）：
  - `email_domain is None`（没有 `@` 或无法解析域名）
  - `email_domain in blocklist`（一次性/临时邮箱域名黑名单，来自 `disposable-email-domains`）
  - 或命中原有 `EMERGENCY_BLOCK_PATTERNS`（紧急拦截正则）

命中后行为：
- `logging.warning(...)`
- `time.sleep(2)`（增加攻击成本/降速）
- 直接返回“Verification code sent”（不再进入后续验证码生成/发送流程）

#### 第二层：first-time 用户更严格校验（成本更高）
在通过 reCAPTCHA 且准备生成验证码之前：
- 查询 `email_verification_codes` 表是否已出现过该 email
- 若没出现过（第一次请求）：
  - 使用 `email-validator` 执行 `validate_email(email, check_deliverability=True)`
  - 校验失败（抛 `EmailNotValidError`）则记录原因并直接返回“Verification code sent”（不发码）

备注：该逻辑的“首次出现”依据是验证码表 `email_verification_codes` 中是否存在记录，而非用户表/注册表。

---

### 2) 新增依赖（requirements 变化）
`app_prismax_user_management/requirements.txt` 新增：
- `disposable-email-domains`（一次性邮箱域名 blocklist）
- `email-validator`（邮箱格式与可投递性校验，启用 deliverability）

---

## 🎯 设计意图（推断）
- **反滥用**: 阻断一次性邮箱、明显异常邮箱，减少验证码发送滥用与注册攻击。
- **反枚举**: 对外统一返回“已发送”，减少攻击者从响应中获取有效/无效邮箱信号。
- **分层成本控制**: 先用域名黑名单/紧急正则做 cheap check；再对“首次出现邮箱”做更严 deliverability check，降低整体系统成本。

---

## ⚠️ 风险与影响评估

### 1) 误杀与用户体验风险（中）
- `disposable-email-domains` 的 blocklist 可能覆盖真实用户邮箱域（尤其是别名/转发/小众域名），会导致用户收不到验证码，但页面可能显示“已发送”，用户难以自助定位原因。
- “首次出现”的判定使用 `email_verification_codes` 表：
  - 如果该表有清理/过期删除策略，同一邮箱未来可能再次被当成“首次出现”触发严格校验，体验不一致。
  - 如果某邮箱被攻击者提前触发过一次请求并写入记录，后续可能绕开严格校验（仅仍受第一层规则影响）。

### 2) 性能与网络依赖风险（中）
- `check_deliverability=True` 通常涉及 DNS/MX 等检查，可能带来额外延迟，甚至在网络/解析受限环境下导致大量误判或异常。
- 第一层命中时强制 `sleep(2)`，在攻击流量/误杀较多时会增加 worker 占用，需关注接口并发与超时配置。

### 3) 可观测性风险（低-中）
两处拦截都会打 warning 日志，但第一层日志文案仍为 “Blocked suspicious email pattern”，实际原因可能是“无域名/一次性域名/正则命中”，排查时不够精确。

---

## 🧪 回归建议（重点验证）

### P0（必须）
1. 正常邮箱（常见域名，如 gmail/outlook/company domain）
   - 第一次请求：通过 reCAPTCHA 后能完成严格校验并真正发送验证码（需结合实际发送链路确认）。
   - 第二次请求：由于 `email_verification_codes` 已有记录，严格 deliverability 校验应被跳过，流程应更接近旧逻辑。

2. 一次性邮箱域名（在 blocklist 中）
   - 应在 first-pass 被拦截：返回 200 且 success:true，但实际不发送验证码；日志有 warning；接口耗时应明显增加（约 2 秒）。

3. 非法格式邮箱
   - 无 `@`：应在 first-pass 直接拦截（不发码，返回“已发送”）。

### P1（建议）
4. 不可投递邮箱（例如无 MX / 不存在的域）
   - 首次请求：应被 deliverability 校验拦截（不发码，返回“已发送”），并记录原因日志。

5. 部署环境网络限制验证
   - 在生产/测试环境确认 DNS 解析与 outbound 网络策略是否允许 deliverability 校验；否则可能出现系统性误杀。

6. 压测/并发观察
   - 重点观察命中拦截时 `sleep(2)` 对吞吐与响应时间的影响，以及是否触发上游超时/重试风暴。

---

## ✅ 总结
该提交在 `send_verification_code()` 中引入分层邮箱风控：一次性邮箱域名拦截 + 首次邮箱的 deliverability 校验，同时对外保持统一“已发送”响应以降低枚举风险。主要风险在于误杀与网络依赖导致的延迟/不稳定，以及 `sleep(2)` 在高命中时对服务并发带来的压力。

