## PrismaX Point System 积分系统说明

本文件基于 `app-prismax-rp-backend` 代码与接口文档，对当前 **积分类型、来源与计算逻辑** 做整理，便于研发与测试对齐。  
This document summarizes the **point types, sources, and calculation rules** in the PrismaX backend (`app-prismax-rp-backend`) for development and QA.

---

## 1. 数据模型 / Data Model

- **用户总积分字段 / User total points**
  - 表 / Table: `users`
  - 字段 / Column: `total_points`
  - 含义 / Meaning: 当前用户累计可用积分（包括登录、遥操作、评论、问卷、邀请等所有来源的结果）。

- **积分流水表 / Point transaction ledger**
  - 表 / Table: `point_transactions`
  - 关键字段 / Key columns:
    - `userid`: 用户 ID / user id
    - `points_change`: 本次积分变动值 / delta of points
    - `transaction_type`: 业务类型（如 `daily_login`、`first_time_tele_op` 等）
    - `created_at_utc`: 创建时间（UTC）
    - `user_local_date`: 用户本地日期（部分类型使用，如每日登录）
  - 作用 / Purpose: 记录可审计的积分变动明细，用于前端展示和风控分析。

- **积分流水查询接口 / Transaction query API**
  - `GET /api/get-point-transactions`
  - 输入 / Input:
    - 通过 `wallet_address + chain` 或 `email` 定位用户
    - 可选 `chain`：`solana` / `ethereum` / `base` / `monad` / `aptos`，默认 `solana`
  - 行为 / Behavior:
    - 返回最近 14 天的 `point_transactions` 记录
    - 若按单个用户查询，同时返回该用户当前 `total_points`

---

## 2. 每日登录积分（含新用户初始积分）  
## Daily Login Points (incl. New User Initial Points)

- **后端接口 / Backend API**
  - `POST /api/daily-login-points` （文件：`app_prismax_user_management/app.py`）

- **触发来源 / Trigger**
  - 前端在应用上下文初始化、登录成功或连接钱包后自动调用（`SwapMainAppContext.handleDailyLoginPoints`）。

- **用户定位 / User lookup**
  - 通过钱包地址：`wallet_address + chain`，按链映射到 `users` 表对应地址列
  - 或通过邮箱：`email`（小写化后查询 `users.email`）

- **链倍数 / Chain multiplier**
  - 当 `chain == 'monad'` 时：`multiplier = 2`
  - 其他链：`multiplier = 1`

- **新用户初始积分 / New user initial points**
  - 条件 / Condition: `current_total_points == 0`
  - 计算 / Calculation:
    - `initial_points = 1000 * multiplier`
  - 写入 / Write:
    - `UPDATE users SET total_points = initial_points WHERE userid = :user_id`
  - 特点 / Note:
    - 只改 `users.total_points`，**不写入 `point_transactions`**。
    - 前端通过返回字段 `is_first_time` 用于“首次登录/欢迎”提示。

- **每日登录积分类型 / Transaction type: `daily_login`**
  - **防重复 / Idempotency**
    - SQL 按 `(userid, transaction_type='daily_login', user_local_date)` 检查：
      - 若当日已有记录，则不再发放。
  - **基础每日积分（按会员等级） / Base daily points (by membership)**
    - `Explorer Member`: `base_daily_points = 10`
    - `Amplifier Member`: `base_daily_points = 30`
    - `Innovator Member`: `base_daily_points = 50`
  - **最终发放积分 / Final points**
    - `daily_points = base_daily_points * multiplier`
  - **数据库写入 / DB updates**
    - `users.total_points += daily_points`
    - `INSERT INTO point_transactions (userid, points_change, transaction_type, user_local_date) VALUES (:user_id, :points, 'daily_login', :user_local_date)`

- **日期安全校验 / Date validation**
  - 若前端传 `user_local_date`：
    - 服务端校验该日期必须在当前 UTC 日期的 ±1 天范围内，否则报错
  - 否则：
    - 默认使用当前服务器日期 `datetime.now()`（UTC 转字符串 `YYYY-MM-DD`）。

---

## 3. 机器人遥操作积分（Tele‑Op Points）

涉及模块位于 `app_prismax_tele_op_services`：  
Tele‑op–related logic lives in `app_prismax_tele_op_services`.

### 3.1 首次遥操作奖励：`first_time_tele_op`  
### First-time Tele‑Op Reward

- **业务含义 / Meaning**
  - 用户首次成功控制机器人，获得一次性大额奖励 3000 积分。

- **判定逻辑 / First-time detection**
  - 在奖励计算函数中（`queue_helper.reward_control_session`）查询：
    - `point_transactions` 中是否存在：
      - `transaction_type = 'first_time_tele_op'`
      - `points_change = 3000`
      - `userid = current user`
  - 若不存在，视为首次遥操作。

- **积分计算 / Points**
  - `reward_points = 3000`
  - `transaction_type = 'first_time_tele_op'`

- **数据库写入 / DB updates**
  - 更新遥操作历史：
    - `tele_op_control_history.reward_points = 3000`
    - 同时写入会话结束时间、控制时长（小时）等信息
  - 更新用户总积分：
    - `users.total_points += 3000`
  - 写入积分流水：
    - `INSERT INTO point_transactions (userid, points_change, transaction_type, created_at_utc) VALUES (..., 3000, 'first_time_tele_op', ... )`

- **前端信号 / Frontend signal**
  - `/use_robot` 接口在分发控制 token 时也会返回 `isFirstTime` 字段，供前端提示；真正积分发放在会话结束/离队逻辑中完成。

---

### 3.2 非首次遥操作时长奖励：`robot_control_reward`  
### Subsequent Tele‑Op Duration Reward

- **业务含义 / Meaning**
  - 用户非首次控制机器人时，根据本次会话控制时长获得积分奖励。

- **输入 / Inputs**
  - `user_id`
  - `control_token`
  - `inactive`：标记是否为“非主动离开/超时”等场景

- **安全检查 / Safety checks**
  - 在 `tele_op_control_history` 中根据 `control_token` 查询：
    - 若已存在 `controlled_end_time`：
      - 视为本控制会话已经处理过，直接返回 0，避免重复奖励。

- **时长计算 / Session duration**
  - `session_duration_seconds = (now_utc - issued_at).total_seconds()`

- **奖励规则 / Reward rules**
  - 情形一 / Case 1：`inactive == True` 且 `session_duration_seconds < 50`
    - 视为挂机过短（<50 秒），不发积分：`reward_points = 0`
  - 情形二 / Case 2：已拿过首控奖励，按秒计费
    - 若 `inactive == True`：
      - 先扣除 30 秒：`session_duration_seconds = max(session_duration_seconds - 30, 0)`
    - 然后：
      - `reward_points = int(session_duration_seconds * 0.3)`
      - `transaction_type = 'robot_control_reward'`

- **数据库写入 / DB updates**
  - 更新 `tele_op_control_history`：
    - `controlled_end_time = NOW() AT TIME ZONE 'UTC'`
    - `controlled_hours` = 控制时长（秒）/3600，保留 4 位小数
    - `reward_points = reward_points`
  - 更新 `users`：
    - `users.total_points += reward_points`
  - 写入 `point_transactions`（reward_points > 0 时）：
    - `INSERT INTO point_transactions (userid, points_change, transaction_type, created_at_utc) VALUES (..., reward_points, 'robot_control_reward', NOW() AT TIME ZONE 'UTC')`

---

### 3.3 娃娃识别任务奖励：`dolls_compare_reward`  
### Doll Comparison Task Reward

- **接口 / API**
  - `POST /vision/dolls_compare`（`app_prismax_tele_op_services/app.py`）

- **业务流程 / Flow**
  - 前端/机器人服务上传一组视角截图 `views`，后端调用 GPT 模型进行多轮比对：
    1. 先用第一帧逐视角对比
    2. 若结果异常，再使用第二帧
    3. 若仍异常，对 3–5 帧做多帧投票
  - 通过 `evaluate_compare_result` 得到：
    - `abnormal`：是否异常
    - `success_count`：成功视角数量

- **积分计算 / Points**
  - 若最终状态为成功（`not abnormal` 且 `success_count > 0`）：
    - `reward_inc = 100 * success_count`
  - 否则：`reward_inc = 0`

- **数据库写入 / DB updates**
  - 更新 `tele_op_control_history` 中本次 `control_token` 的记录：
    - `controlled_result` 保存识别结果 JSON
    - `controlled_status` 标记为 `"success"` 或 `"failed"`
    - `reward_points += reward_inc`
  - 若 `reward_inc > 0` 且存在 `user_id`：
    - `users.total_points += reward_inc`
    - `INSERT INTO point_transactions (userid, points_change, transaction_type, created_at_utc) VALUES (..., reward_inc, 'dolls_compare_reward', NOW() AT TIME ZONE 'UTC')`

---

## 4. 问卷积分：`quiz`  
## Quiz Points

- **接口 / APIs**
  - `GET /api/quiz/check-status`：查询是否已完成问卷及已得积分
  - `POST /api/quiz/submit`：提交问卷答案并发放积分

- **防刷逻辑 / Anti-abuse**
  - 在提交接口中，首先检查 `point_transactions`：
    - 是否存在 `transaction_type = 'quiz'` 且 `userid = current user`
    - 如果存在，说明已经完成问卷，返回 `already_completed = True` 并拒绝再次发放积分。
  - 集成 reCAPTCHA 校验，低于阈值（如 `< 0.5`）直接拒绝。

- **积分计算 / Point calculation**
  - 输入 / Inputs:
    - `correct_answers`: 答对题目数量（int）
    - `total_questions`: 总题目数（默认 5）
  - 计算 / Formula:
    - 基础分 / Base:  
      `base_points = correct_answers * 500`
    - 全对额外奖励 / Full-score bonus:  
      `bonus_points = 1000 if correct_answers == total_questions else 0`
    - 总积分 / Total:  
      `total_points = base_points + bonus_points`

- **数据库写入 / DB updates**
  - 写入流水：
    - `INSERT INTO point_transactions (userid, points_change, transaction_type) VALUES (..., total_points, 'quiz')`
  - 更新用户总积分：
    - `users.total_points += total_points`

---

## 5. ~~评论奖励积分：`comment_reward`~~（已因 PRIS-125 暂时关闭）  
## ~~Comment Reward Points~~

- **接口 / API**
  - ~~`POST /api/check-comment-reward`~~

- **有效评论判定 / Valid comment check**
  - 请求体字段 / Request body:
    - ~~`user_id`~~
    - ~~`message`~~
  - 判定条件 / Conditions:
    - ~~`message` 长度 ≥ 10 字符~~
    - ~~单词数 ≥ 3（通过空格拆分）~~
    - ~~若不满足，视为无效请求，不发积分。~~

- **每日限制 / Daily limit**
  - ~~通过 `point_transactions` 检查当天是否已有记录：~~
    - ~~`transaction_type = 'comment_reward'`~~
    - ~~`DATE(created_at_utc) = today_utc`~~
  - ~~若已存在，则返回“当日已领取”，不再发放积分。~~

- **积分规则（按会员等级） / Points by membership**
  - ~~从 `users.user_class` 获取实际等级：~~
    - ~~`Explorer Member`：`points = 50`~~
    - ~~其他（`Amplifier Member` / `Innovator Member`）：`points = 150`~~

- **数据库写入 / DB updates**
  - ~~`users.total_points += points`~~
  - ~~`INSERT INTO point_transactions (userid, points_change, transaction_type) VALUES (..., points, 'comment_reward')`~~

---

## 6. 邀请 / 推荐积分（不写入流水）  
## Referral / Invite Points (No `point_transactions` Records)

- **接口 / API**
  - `GET /api/get-users-by-referral`

- **关键字段 / Key fields in `users`**
  - `referral_code`：当前用户的邀请码
  - `referrers_referral_code`：当前用户填写的邀请人 code
  - `referral_initial_reward`：已经发放的“邀请人数 × 500 积分”累计
  - `referred_reward_point`：已经发放的“10% 分润积分”累计

- **授权与锁控制 / Auth & locking**
  - 通过 `(userid, hash_code)` 验证请求人身份
  - 使用 `SELECT ... FOR UPDATE` 锁定推荐人行，避免并发下重复结算。

- **步骤一：邀请人数奖励 / Step 1: Invite count reward**
  - 查询所有 `referrers_referral_code = :referral_code` 的用户列表，计数为 `referee_count`
  - 目标奖励 / Target:
    - `invite_target = referee_count * 500`
  - 补差 / Delta:
    - `invite_delta = invite_target - referral_initial_reward`
  - 若 `invite_delta > 0`：
    - `users.total_points += invite_delta`
    - `referral_initial_reward = invite_target`

- **步骤二：总积分 10% 分润 / Step 2: 10% revenue share**
  - 求所有被邀请人当前 `total_points` 之和：`referees_total`
  - 目标 / Target:
    - `target = referees_total // 10`  （整数除法，下取整）
  - 补差 / Delta:
    - `delta = target - referred_reward_point`
  - 若 `delta > 0`：
    - `users.total_points += delta`
    - `referred_reward_point = target`

- **重要说明 / Important note**
  - 上述两个步骤 **都只更新 `users` 表字段**，**不会写入 `point_transactions`**。
  - 积分审计时，需要结合 `users.referral_initial_reward` 与 `users.referred_reward_point` 来还原邀请来源。

---

## 7. 反作弊与榜单 / Anti-abuse & Leaderboards

- **反作弊检测 / Bot detection**
  - 函数 / Function: `detect_and_reset_bots`
  - 逻辑 / Logic:
    - 扫描 `point_transactions` 中日期异常的记录：
      - `user_local_date > CURRENT_DATE + 2`（未来日期）
      - 或 `user_local_date < '2025-06-02'`（项目启动前的老数据）
    - 将命中的用户写入 `detected_bot_users` 表，记录：
      - 钱包 / 邮箱
      - `points_before_reset`
      - `points_after_reset`（预期为 0）
      - 原因说明等
    - 当前代码中将重置总积分的 SQL 留为注释，方便后续按策略启用。

- **遥操作榜单 / Tele‑Op leaderboards**
  - 表 / Tables:
    - `tele_op_leaderboard`
    - `monad_leaderboard`
  - 排名依据 / Ranking criteria:
    - `users.total_points`
    - `tele_op_control_history.controlled_hours`
  - 说明 / Note:
    - 榜单刷新逻辑仅 **读取** 已有积分与时长，不额外发放积分。

---

## 8. 总结 / Summary

- **主要积分类型 / Main point types**
  - `daily_login`：每日登录积分（含链倍数 & 依会员等级差异）
  - `first_time_tele_op`：首次遥操作奖励 3000 分
  - `robot_control_reward`：根据遥操作时长按秒计费（0.3 分/秒）
  - `dolls_compare_reward`：娃娃识别任务，每成功视角 +100 分
  - `quiz`：问卷积分，按答对题数与是否全对计算
  - `comment_reward`：~~每日一次有效评论奖励（50 或 150 分）~~（已因 PRIS-125 暂时关闭）
  - 邀请/推荐积分：通过 `users.referral_initial_reward` 与 `referred_reward_point` 直接影响 `total_points`，**不写入 `point_transactions`**

- **按 Membership 维度的规则差异 / Per-membership rules by type**
  - `daily_login` & 初始积分：
    - Explorer：首次 1000 分（Monad 链 2000），每日 10 分（Monad 20）。
    - Amplifier：首次 1000 分（Monad 2000），每日 30 分（Monad 60）。
    - Innovator：首次 1000 分（Monad 2000），每日 50 分（Monad 100）。
  - Tele‑Op 首次控制 `first_time_tele_op`：
    - Explorer：无机器人权限，不获得该类积分。
    - Amplifier：首次成功控制机器人奖励 3000 分。
    - Innovator：与 Amplifier 相同，首次 3000 分。
  - Tele‑Op 时长奖励 `robot_control_reward`：
    - Explorer：无权限，无该类积分。
    - Amplifier / Innovator：有效控制时长按约 0.3 分/秒结算，`inactive && <50s` 为 0 分，inactive 时先扣 30 秒。`each session(5mins) at most: 0.3 * 5 * 60 = 90 points` 
  - 娃娃识别 `dolls_compare_reward`：
    - Explorer：不使用机器人，无该类积分。
    - Amplifier / Innovator：每个成功视角 +100 分（100 × success_count）。
  - ~~评论奖励 `comment_reward`~~（已因 PRIS-125 暂时关闭）：
    - ~~Explorer：每日最多 1 次，每次 50 分。~~
    - ~~Amplifier / Innovator：每日最多 1 次，每次 150 分。~~
  - 问卷 `quiz`：
    - 三种 Membership 完全相同：每题 500 分，全对额外 +1000 分，仅可完成一次。
  - 邀请 & 10% 分润：
    - 三种 Membership 完全相同：每个被邀请用户 500 分，加上其当前总积分的 10%（向下取整），都直接进入 `users.total_points` 而不写入 `point_transactions`。

- **审计与测试建议 / Audit & QA hints**
  - 针对需要可追踪的积分发放路径，应优先检查：
    - `point_transactions` 中对应 `transaction_type` 的记录
    - `users.total_points` 变动是否与流水一致
  - 对邀请相关积分，应通过 `users` 表中的累计字段进行验证，而不是仅看 `point_transactions`。

### 前端逻辑

- 数据来源：`GET /api/get-point-transactions`（同上接口返回的数据）。
- 前端计算逻辑（发生在首页 Dashboard）：
  1. 在用户本地时区生成“今天”的日期字符串：`YYYY-MM-DD`。
  2. 遍历接口返回的 `data`（近 14 天内的积分变动），对每条记录确定其“记账日”：
     - 若存在 `user_local_date`，直接解析为 `YYYY-MM-DD` 使用；
     - 否则使用 `created_at_utc` 将 UTC 时间转换为本地时间，再取 `YYYY-MM-DD`。
  3. 仅保留“记账日 == 今天”且 `points_change > 0` 的记录。
  4. 对上述记录的 `points_change` 求和（向下取整）后显示为“Daily Prisma Points”。

- 相关字段：
  - `points_change`: 本次变动的积分，正数为增加；
  - `user_local_date`: 后端记录的用户本地日期（若有则优先）；
  - `created_at_utc`: 变动发生的 UTC 时间戳（用于本地化日期的后备）。

-
- All‑Time Prisma Points：直接使用接口返回的 `total_points`。
- Earnings 折线图：使用近 14 天 `point_transactions`，前端按天聚合 `points_change > 0` 之和。



### API — GET /api/get-point-transactions

**作用**  
按用户（通过 `email` 或 `wallet_address`）查询近 14 天的积分变动记录，并在用户维度查询时附带返回当前 `total_points`。

### 入参
- **email**（可选，和 `wallet_address` 二选一）：用于按邮箱定位用户（会转为小写）
- **wallet_address**（可选，和 `email` 二选一）：用于按链上地址定位用户
- **chain**（可选，默认 `solana`）：仅在使用 `wallet_address` 查询时用于选择 `users` 表中对应链地址列；支持：`solana | ethereum | base | monad | aptos`

### 时间窗口
- 固定查询最近 14 天：`created_at_utc >= (UTC现在 - 14天)`，按 `created_at_utc` 倒序返回。

### 读取的数据表
- **users**
  - 用途：通过 `email` 或（当有 `wallet_address` 时）通过链映射列 `CHAIN_COLUMN_MAP[chain]` 定位到 `userid`；同时读取 `total_points`。
  - 关键读取字段：`userid`, `total_points`，以及用于匹配的 `email` 或链上地址列（如 `solana_address` 等）。
- **point_transactions**
  - 用途：按 `userid` 和 14 天窗口提取积分变动记录。
  - 典型字段（根据实际表结构可能包含）：`transaction_id`, `userid`, `points_change`, `transaction_type`, `user_local_date`, `created_at_utc` 等。

### 返回
- 当使用 `email` 或 `wallet_address` 成功定位到用户时：
  - `success: true`
  - `data: [ ...point_transactions 记录... ]`
  - `total_points: <users.total_points>`
- 当未带用户标识（`email`/`wallet_address` 都无）时：
  - 返回近 14 天的全量 `point_transactions`（不附带 `total_points`）。


### point_transactions 的更新来源与写入规则

- 日常登录（Daily Login）
  - 接口：`POST /api/daily-login-points`
  - 动作：按会员等级与链（Monad ×2）计算当日登录积分，更新 `users.total_points`，并插入 `point_transactions`：
    - `transaction_type='daily_login'`
    - 写入 `user_local_date=YYYY-MM-DD`（用于前端本地日聚合）
  - 防重：按 `userid + user_local_date` 当日只发一次。

- Tele‑Op 会话结束结算
  - 位置：控制服务的奖励结算（`process_session_rewards`）
  - 规则：
    - 首次控制奖励固定 3000 分（`transaction_type='first_time_tele_op'`）
    - 之后以约 `0.3 分/秒` 结算（非活跃减 30 秒），`transaction_type='robot_control_reward'`
  - 动作：更新 `users.total_points`；插入 `point_transactions`，时间使用 `created_at_utc=NOW() AT TIME ZONE 'UTC'`。

- 白皮书测验（Quiz）
  - 接口：`POST /api/quiz/submit`
  - 动作：人机验证通过后计算总分；若已完成过则拒绝；否则插入 `point_transactions (transaction_type='quiz')` 并更新 `users.total_points`。

- ~~有意义评论奖励（每日一次）~~（已因 PRIS-125 暂时关闭）
  - ~~接口：`POST /api/check-comment-reward`~~
  - ~~动作：用 `DATE(created_at_utc)=UTC今日` 防重复；发放积分并插入 `point_transactions (transaction_type='comment_reward')`。~~

- 邀请/返利（读取时结算，避免过多流水）
  - 接口：`GET /api/get-users-by-referral`
  - 动作：读取时为邀请人结算初始邀请奖励（每个被邀请用户 500 分）与 10% 返利，直接累加到 `users.total_points`；不写入 `point_transactions`。


### total_points 与 reward_points / point_transactions 的影响分析

- 定义：`total_points` 为 `users.total_points` 的持久化累计值，按事件发生“即时累加”。不是事后按 `point_transactions` 回放聚合得出。
- 一般规则：绝大多数积分发放同时做两件事
  - 写入 `users.total_points`（累加）
  - 写入 `point_transactions`（审计流水，含 `transaction_type`）
- 例外：邀请/返利读取时结算，仅更新 `users.total_points`，不写入 `point_transactions`（以 `users.referred_reward_point` 与 `users.referral_initial_reward` 记录已结算额度，防重复）。

#### 事件与写入的表
- 日常登录（Daily Login）
  - 表更新：`users`（`total_points += daily_points`），`point_transactions`（`transaction_type='daily_login'`，含 `user_local_date`）
- Tele‑Op 会话结算
  - 表更新：
    - `tele_op_control_history`（写入本次会话 `reward_points`、`controlled_end_time`、`controlled_hours`）
    - 如 `reward_points > 0`：`users`（`total_points += reward_points`），`point_transactions`（`transaction_type='first_time_tele_op' | 'robot_control_reward'`）
- 白皮书测验（Quiz）
  - 表更新：`users`（累加计算后的分值），`point_transactions`（`transaction_type='quiz'`）
- ~~有意义评论（每日一次）~~（已因 PRIS-125 暂时关闭）
  - ~~表更新：`users`（按会员等级累加），`point_transactions`（`transaction_type='comment_reward'`）~~
- 邀请/返利（读取即结算）
  - 表更新：仅 `users`（累加初始邀请 500×人数；返利差额 `floor(sum(referees.total_points)×10%) - referred_reward_point`），不写 `point_transactions`

#### 流程图（含表标注）

```mermaid
flowchart TD
  subgraph Tele-Op 会话结算
    A[开始会话\ntele_op_control_history] --> B{是否首次控制?}
    B -- 是 --> C[reward_points = 3000\n(首次奖励)]
    B -- 否 --> D{inactive?}
    D -- 是且<50s --> E[reward_points = 0]
    D -- 否/是且≥50s --> F[reward_points = floor((duration - (inactive?30s:0)) * 0.3)]

    C --> G[UPDATE tele_op_control_history\nSET reward_points, controlled_end_time, controlled_hours]
    E --> G
    F --> G

    G --> H{reward_points > 0?}
    H -- 否 --> I[结束]
    H -- 是 --> J[UPDATE users\nSET total_points = total_points + reward_points\n(users)]
    J --> K[INSERT point_transactions\n(points_change=reward_points,\n type=first_time_tele_op|robot_control_reward)]
    K --> I
  end

  subgraph Daily Login
    L[请求 /api/daily-login-points] --> M{当日是否已发?}
    M -- 否 --> N[计算 daily_points\n(Explorer 10, Amplifier 30, Innovator 50; Monad ×2)]
    N --> O[UPDATE users\nSET total_points += daily_points\n(users)]
    O --> P[INSERT point_transactions\n(points_change=daily_points,\n type=daily_login,\n user_local_date)]
    M -- 是 --> Q[跳过发放]
  end

  subgraph Quiz
    R[请求 /api/quiz/submit] --> S{是否已完成过?}
    S -- 否 --> T[计算 points: 500/题 + 全对额外 1000]
    T --> U[INSERT point_transactions\n(points_change=points,\n type=quiz)]
    U --> V[UPDATE users\nSET total_points += points\n(users)]
    S -- 是 --> W[拒绝重复领取]
  end

  subgraph 评论奖励（已因 PRIS-125 暂时关闭）
    X[请求 /api/check-comment-reward] --> Y{今天已领过?}
    Y -- 否 --> Z[计算 points: Explorer 50,\n非 Explorer 150]
    Z --> AA[UPDATE users\nSET total_points += points\n(users)]
    AA --> AB[INSERT point_transactions\n(points_change=points,\n type=comment_reward)]
    Y -- 是 --> AC[跳过发放]
  end

  subgraph 邀请/返利(读取结算)
    AD[请求 /api/get-users-by-referral] --> AE[校验 referrer]
    AE --> AF[计算初始邀请奖励: 500×referees_count]
    AF --> AG[UPDATE users\nSET total_points += invite_delta,\n referral_initial_reward = target\n(users)]
    AE --> AH[计算 10% 返利目标: floor(sum(referees.total_points)×10%)]
    AH --> AI[delta = target - referred_reward_point]
    AI --> AJ{delta > 0?}
    AJ -- 是 --> AK[UPDATE users\nSET total_points += delta,\n referred_reward_point = target\n(users)]
    AJ -- 否 --> AL[无变更]
    note right of AG: 不写入 point_transactions
    note right of AK: 不写入 point_transactions
  end
```

#### 重要说明
- `users.total_points` 为“事件驱动、逐次累加”的权威来源；前端展示 All‑Time 值时直接读取该字段。
- 事后修改 `tele_op_control_history.reward_points` 或随意增删 `point_transactions` 并不会自动回滚/同步 `users.total_points`。如需修正历史，需要相应更新 `users.total_points` 与对应审计流水，保证一致性。


#### 为什么“手动改会话积分不会自动影响总分”
- 一句话版：系统在“发放当时”就把积分累加进 `users.total_points` 并记一条流水。之后你去改历史记录表（例如 `tele_op_control_history.reward_points` 或某条 `point_transactions`），不会触发任何“回调”去重算 `users.total_points`；前端读取总分时也只看 `users.total_points`，不是汇总其他表。

- 原因：
  - All‑Time 展示接口直接读取 `users.total_points` 字段，而不是动态聚合 `point_transactions` 或 `tele_op_control_history`。
  - 发放流程是“事件驱动、即时累加”的设计，没有后台触发器或任务会在你修改历史记录后自动同步总分。

- 举例：
  - 某次会话原来算了 120 分，系统已经把 120 加到该用户的 `users.total_points`，并写入一条对应的 `point_transactions`。
  - 如果你事后把这次会话的 `reward_points` 改成 300：
    - `users.total_points` 不会自动多出 180；仍然停留在“+120”的状态。
    - 正确处理是另外把差额 `+180` 加到 `users.total_points`，同时补一条“纠正流水”（例如 `transaction_type='teleop_adjustment'`，`points_change=180`）用于审计。
  - 如果反向把 300 改回 120，也需要把差额 `-180` 同步减回并留痕。

- 正确修复步骤（建议）：
  1) 计算差额：`delta = newReward - oldReward`。
  2) 更新会话表：把 `tele_op_control_history.reward_points` 改为正确值（保持历史一致）。
  3) 同步总分：`UPDATE users SET total_points = total_points + :delta WHERE userid = :uid`。
  4) 审计留痕（其一）：
     - 新增一条纠正流水（推荐）：`point_transactions(points_change=delta, transaction_type='teleop_adjustment')`；
     - 或（不推荐）直接更新原始流水值，会弱化审计可追溯性。
---

## 10. 各 Membership 等级积分规则汇总 / Membership Rules by Point Source

本节对前文中提到的所有积分来源，分别按 Membership 等级（Explorer / Amplifier / Innovator）做一页式对照。  
This section summarizes, for each point source, how rules differ across membership tiers.

### 10.1 每日登录 & 初始积分 / Daily Login & Initial Points

**新用户初始积分（`total_points == 0` 时） / New user initial points**

| Membership  | Initial points (non‑Monad) | Initial points (Monad, ×2) | Notes |
|------------|----------------------------|-----------------------------|-------|
| Explorer   | 1000                       | 2000                        | Triggered once when `total_points == 0` |
| Amplifier  | 1000                       | 2000                        | Same logic, independent of user_class |
| Innovator  | 1000                       | 2000                        | Same logic, independent of user_class |

**每日登录积分 `daily_login` / Daily login points**

| Membership  | Base daily points (non‑Monad) | Effective on Monad (×2) |
|------------|--------------------------------|--------------------------|
| Explorer   | 10                             | 20                       |
| Amplifier  | 30                             | 60                       |
| Innovator  | 50                             | 100                      |

> 最终发放规则：`daily_points = base_daily_points × multiplier`，其中 `multiplier = 2` 仅在 `chain='monad'` 时生效。  
> Final rule: `daily_points = base_daily_points × multiplier`, where `multiplier = 2` only when `chain == 'monad'`.

---

### 10.2 机器人遥操作 / Tele‑Op Related Points

> Explorer 成员无法使用机器人，不会获得任何 Tele‑Op 相关积分。  
> Explorer members cannot use robots; they never earn Tele‑Op points.

**使用权限 / Access**

| Membership  | Can use Tele‑Op? | Notes |
|------------|------------------|-------|
| Explorer   | No               | Blocked at API level (`use_robot` / queue joins, etc.) |
| Amplifier  | Yes              | Subject to queue/join limits per robot |
| Innovator  | Yes              | Same as Amplifier + queue fast‑track, but same point formula |

**首次遥操作奖励 `first_time_tele_op`（3000 分） / First‑time reward**

| Membership  | Eligible? | Rule |
|------------|-----------|------|
| Explorer   | No        | Cannot use Tele‑Op |
| Amplifier  | Yes       | First Tele‑Op session grants 3000 points once |
| Innovator  | Yes       | Same as Amplifier |

**时长奖励 `robot_control_reward` / Duration‑based reward**

| Membership  | Eligible? | Rule (when eligible) |
|------------|-----------|----------------------|
| Explorer   | No        | N/A |
| Amplifier  | Yes       | If `inactive && duration < 50s` → 0; else `int(effective_seconds × 0.3)` |
| Innovator  | Yes       | Same duration logic as Amplifier |

**娃娃识别任务 `dolls_compare_reward` / Doll comparison reward**

| Membership  | Eligible? | Rule |
|------------|-----------|------|
| Explorer   | No        | N/A |
| Amplifier  | Yes       | If GPT result is successful: `100 × success_count` points |
| Innovator  | Yes       | Same as Amplifier |

---

### 10.3 评论奖励 `comment_reward` / Comment Reward

**每天一次、按等级差异计分 / Once per day, tier‑dependent amount**

| Membership  | Daily limit | Points per rewarded comment |
|------------|------------|------------------------------|
| Explorer   | 1          | 50                           |
| Amplifier  | 1          | 150                          |
| Innovator  | 1          | 150                          |

> “有意义评论”判定逻辑（长度、单词数等）对三种等级一致，仅奖励分值不同。  
> The “meaningful comment” check is identical across tiers; only the awarded amount differs.

---

### 10.4 问卷积分 `quiz` / Quiz Points

**与 Membership 无关 / Independent of membership**

| Membership  | Rule |
|------------|------|
| Explorer   | Points = `500 × correct_answers + (1000 if all correct else 0)` |
| Amplifier  | Same as Explorer |
| Innovator  | Same as Explorer |

> 只要通过 reCAPTCHA 且未完成过问卷，三种等级的计算公式完全相同。  
> As long as reCAPTCHA passes and the quiz has not been completed before, all tiers share the same formula.

---

### 10.5 邀请与 10% 分润 / Referral & 10% Revenue Share

**对所有 Membership 一致 / Same for all tiers**

| Membership  | Invite reward                    | 10% revenue share                                     |
|------------|-----------------------------------|-------------------------------------------------------|
| Explorer   | `500 × number_of_referees`       | `floor(sum(referees.total_points) × 10%)`            |
| Amplifier  | Same as Explorer                 | Same as Explorer                                      |
| Innovator  | Same as Explorer                 | Same as Explorer                                      |

> 这些奖励只更新 `users.total_points` 和累积字段（`referral_initial_reward`, `referred_reward_point`），不写入 `point_transactions`，与会员等级无关。  
> These rewards only update `users.total_points` and the cumulative fields, not `point_transactions`, and are independent of membership tier.

## 9. English-only High-level Summary

This section provides a concise **English-only** overview of the PrismaX point system, mirroring the Chinese descriptions above.

- **Core storage**
  - `users.total_points`: the authoritative all-time point total per user, updated immediately whenever points are granted.
  - `point_transactions`: append-only audit log of point changes (`points_change`, `transaction_type`, timestamps, optional `user_local_date`).

- **Main point sources**
  - **Daily login**
    - API: `POST /api/daily-login-points`
    - Base: `Explorer 10`, `Amplifier 30`, `Innovator 50`; multiplied by `2x` on `monad` chain.
    - First-time users (with `total_points == 0`) get an initial `1000 * multiplier` points directly into `users.total_points` (no `point_transactions` row).
    - Writes: `users.total_points += daily_points`, and `point_transactions(..., transaction_type='daily_login', user_local_date=YYYY-MM-DD)` once per day.
  - **Tele‑Op sessions**
    - First-ever control: `3000` points (`transaction_type='first_time_tele_op'`).
    - Subsequent sessions: roughly `0.3 points/second` of active control, with a 30‑second deduction when leaving as inactive; short inactive sessions (<50s) yield `0` points (`transaction_type='robot_control_reward'`).
    - Writes: `tele_op_control_history` gets `reward_points`, `controlled_end_time`, `controlled_hours`; if `reward_points > 0`, also updates `users.total_points` and inserts a `point_transactions` row.
  - **Doll comparison tasks**
    - API: `POST /vision/dolls_compare`
    - Awards `100 * success_count` points if the final GPT‑based comparison result is successful (`transaction_type='dolls_compare_reward'`).
    - Writes: increments `tele_op_control_history.reward_points`, updates `users.total_points`, and inserts into `point_transactions`.
  - **Quiz**
    - API: `POST /api/quiz/submit`
    - Points: `500` per correct answer + `1000` bonus for answering all questions correctly.
    - One‑time only per user, enforced via `point_transactions` lookup.
    - Writes: `point_transactions(..., transaction_type='quiz')` and increments `users.total_points`.
  - **~~Comment reward~~** (temporarily disabled per PRIS-125)
    - ~~API: `POST /api/check-comment-reward`~~
    - Once per UTC day per user, only for “meaningful” comments (length and word-count checks).
    - ~~Points: `50` for `Explorer`, `150` for non‑Explorer members.~~
    - ~~Writes: `users.total_points += points` and `point_transactions(..., transaction_type='comment_reward')`.~~
  - **Referral & revenue share (no ledger rows)**
    - API: `GET /api/get-users-by-referral`
    - Invite reward: `500 * number_of_referees`, reconciled against `users.referral_initial_reward`.
    - Revenue share: `floor(sum(referees.total_points) * 10%)`, reconciled against `users.referred_reward_point`.
    - Both adjustments update `users.total_points` directly without inserting `point_transactions`.

- **Front‑end consumption**
  - All‑time points on Dashboard: read `total_points` returned by `GET /api/get-point-transactions` (when querying by a specific user).
  - Daily points: aggregate `points_change > 0` for transactions whose effective date (from `user_local_date` or localized `created_at_utc`) equals “today”.
  - Earnings chart: aggregate positive `points_change` over the last 14 days by date.

- **Consistency and manual corrections**
  - `users.total_points` is not recomputed from history; it is event‑driven and cumulative.
  - Manually editing `tele_op_control_history` or `point_transactions` does **not** automatically adjust `users.total_points`.
  - Proper correction flow:
    1. Compute `delta = newReward - oldReward`.
    2. Update the session record (e.g. `tele_op_control_history.reward_points`).
    3. Apply `delta` to `users.total_points`.
    4. Add an adjustment row in `point_transactions` (e.g. `transaction_type='teleop_adjustment'`) for auditability.

#### 为什么“手动改会话积分不会自动影响总分”
- 一句话版：系统在“发放当时”就把积分累加进 `users.total_points` 并记一条流水。之后你去改历史记录表（例如 `tele_op_control_history.reward_points` 或某条 `point_transactions`），不会触发任何“回调”去重算 `users.total_points`；前端读取总分时也只看 `users.total_points`，不是汇总其他表。

- 原因：
  - All‑Time 展示接口直接读取 `users.total_points` 字段，而不是动态聚合 `point_transactions` 或 `tele_op_control_history`。
  - 发放流程是“事件驱动、即时累加”的设计，没有后台触发器或任务会在你修改历史记录后自动同步总分。

- 举例：
  - 某次会话原来算了 120 分，系统已经把 120 加到该用户的 `users.total_points`，并写入一条对应的 `point_transactions`。
  - 如果你事后把这次会话的 `reward_points` 改成 300：
    - `users.total_points` 不会自动多出 180；仍然停留在“+120”的状态。
    - 正确处理是另外把差额 `+180` 加到 `users.total_points`，同时补一条“纠正流水”（例如 `transaction_type='teleop_adjustment'`，`points_change=180`）用于审计。
  - 如果反向把 300 改回 120，也需要把差额 `-180` 同步减回并留痕。

- 正确修复步骤（建议）：
  1) 计算差额：`delta = newReward - oldReward`。
  2) 更新会话表：把 `tele_op_control_history.reward_points` 改为正确值（保持历史一致）。
  3) 同步总分：`UPDATE users SET total_points = total_points + :delta WHERE userid = :uid`。
  4) 审计留痕（其一）：
     - 新增一条纠正流水（推荐）：`point_transactions(points_change=delta, transaction_type='teleop_adjustment')`；
     - 或（不推荐）直接更新原始流水值，会弱化审计可追溯性。

