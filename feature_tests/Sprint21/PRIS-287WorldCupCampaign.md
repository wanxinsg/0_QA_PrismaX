# PRIS-287 World Cup Campaign / Teleop Cup Arm - 前后端逻辑与 E2E 测试用例

## 一、分析范围

### 前端仓库

- 仓库：`app-prismax-rp`
- 分支：`testing`
- Commit：`d540d3272b3bbfd1b31c9eeeddf3b57c77dbf3b8`
- Commit Message：`updated for tele cup arm`
- 作者：`lanmanc <zfc6861@qq.com>`
- 日期：2026-07-11

涉及文件：

- `src/components/TeleOp/Leaderboard.js`
- `src/components/TeleOp/TeleOp.js`
- `src/components/TeleOp/TeleOpRightPanel.js`
- `src/components/TeleOp/TeleOpSelection.js`
- `src/components/TeleOp/TeleOpSelection.module.css`

### 后端仓库

- 仓库：`app-prismax-rp-backend`
- 分支：`testing`
- Commit：`6ff2cad482cd802fc0953fd9c4cbab479b7e6310`
- Commit Message：`updated for tele cup arm`
- 作者：`lanmanc <zfc6861@qq.com>`
- 日期：2026-07-11

涉及文件：

- `app_prismax_tele_op_services/app.py`
- `app_prismax_tele_op_services/queue_helper.py`

---

## 二、一句话主线

PRIS-287 把原来的 Private Arm 入口替换为世界杯主题的 `Teleop Cup Arm`：Amplifier 每个 UTC 日最多控制 3 次，Innovator 最多 6 次；控制时长和 Vision 结果累积为 Campaign Points，独立生成 Cup Leaderboard，并在 Teleop 页面和 Session Complete 中展示 Campaign 结果。

---

## 三、核心业务规则

| 项目 | 当前代码规则 |
|---|---|
| Robot slug | `teleop-cup-arm` |
| Campaign robot | `CAMPAIGN_ARM_SLUGS = {"teleop-cup-arm"}` |
| Vision enabled | `arena-arm`、`teleop-cup-arm` |
| Amplifier 每日限制 | 3 次/UTC 日 |
| Innovator 每日限制 | 6 次/UTC 日 |
| Campaign 基础积分 | Eligible control duration × 0.3，向下取整 |
| Inactive 扣减 | Eligible duration = session duration - 30 秒，最低为 0 |
| Inactive 短 session | 总时长少于 50 秒时，本次时长积分为 0 |
| Vision 积分 | Vision `reward_inc` 同时累计到普通积分；Campaign session 还累计到 Campaign Points |
| 排行榜开始时间 | `2026-07-13 00:00:00` |
| 排行范围 | Amplifier Member、Innovator Member |
| 排行顺序 | Campaign Points DESC → Controlled Hours DESC → User ID |
| 排行展示数量 | Top 50，并可附带当前用户自己的排名 |

---

## 四、端到端数据流

1. 用户进入 TeleOp Selection 页面。
2. 前端展示 `Teleop Cup Arm` 卡片，并通过 `teleop-cup-arm` 找到后端返回的 robot ID。
3. 用户点击卡片进入排队/控制流程。
4. `join_queue` 查询 robot slug、用户等级及当日 Campaign 控制历史。
5. Amplifier 当日达到 3 次、Innovator 达到 6 次时，后端返回 `403`；未达到限制则继续原有排队逻辑。
6. 用户获得控制权后，`use_robot` 创建 `tele_op_control_history`，把 `campaign_key` 写为 `teleop-cup-arm`。
7. Teleop Cup Arm 启用 Vision compare 能力。
8. Session 结束时，后端按 eligible duration 计算普通 reward points；Campaign session 同时计算 `campaign_points`。
9. Vision compare 成功产生的奖励也会累加到本次 Campaign Points，并通过状态条件避免同一个 Vision 结果重复更新。
10. Session Complete API 对 Campaign session 返回 Campaign Points，而不是普通 reward points。
11. 内部任务调用 Cup Leaderboard update API，从 Campaign 控制历史重新生成排行榜快照。
12. 前端仅在当前 robot 为 `teleop-cup-arm` 时显示 `Cup Leaderboard` tab，并请求排行榜 API。

---

## 五、前端改动逻辑

### 5.1 Teleop Cup Arm 选择卡片

`TeleOpSelection.js` 将原来的 `private-arm` 卡片替换为：

```js
{
    robotSlug: 'teleop-cup-arm',
    name: 'Teleop Cup Arm',
    description: 'Celebrate the World Cup live. Open to Amplifiers (3/day) and Innovators (6/day).'
}
```

展示逻辑：

- 使用 `private arm - soccer .png` 作为 World Cup Campaign 图片。
- 图片填满卡片媒体区域，使用 `object-fit: contain`。
- 图片应用 `grayscale(100%)`。
- Robot 名称优先使用后端 `robotData.robotName`。
- 后端尚未返回名称时，fallback 为前端配置的 `Teleop Cup Arm`，避免空标题。
- 点击卡片继续复用原有 `handleStartOperation(robotId, robotData)`。

### 5.2 Session Complete Modal

前端新增：

```js
const SESSION_COMPLETE_ROBOT_SLUGS = new Set([
    'arena-arm',
    'teleop-cup-arm',
]);
```

因此 Teleop Cup Arm session 结束后会和 Arena Arm 一样打开 Session Complete Modal。后端仍使用 `reward_points` 字段名返回结果，但 Campaign session 中该字段的值实际来自 `campaign_points`。

### 5.3 Cup Leaderboard Tab

`TeleOp.js` 把当前 `robotSlug` 传给 `TeleOpRightPanel`。

只有满足以下条件时显示 Cup Leaderboard：

```js
robotSlug === 'teleop-cup-arm'
```

Tab 行为：

- 新增 `Cup Leaderboard` tab。
- 使用独立 ref 计算 active tab 下方滑块位置。
- 点击后渲染 `<Leaderboard leaderboardChain="teleop-cup" />`。
- 切换到其他 robot 时，如果当前仍停留在 Cup Leaderboard，自动回退到原来的 left panel。
- Live Chat、普通 Leaderboard、Queue 和 Controls 保持原有逻辑。

### 5.4 Leaderboard API 路由

`Leaderboard.js` 增加 endpoint mapping：

```text
teleop-cup → /tele_op/teleop_cup_leaderboard
monad      → /tele_op/monad_leaderboard
default    → /tele_op/leaderboard
```

存在当前 user ID 时，前端附加：

```http
?userId={encodedUserId}
```

后端同时兼容 `userId` 和 `user_id`。

---

## 六、后端改动逻辑

### 6.1 Campaign 配置

```python
CAMPAIGN_ARM_SLUGS = {"teleop-cup-arm"}
VISION_ENABLED_ARM_SLUGS = {"arena-arm", "teleop-cup-arm"}
CAMPAIGN_DAILY_CONTROL_LIMITS = {
    "Amplifier Member": 3,
    "Innovator Member": 6,
}
TELEOP_CUP_LEADERBOARD_START_UTC = "2026-07-13 00:00:00"
```

配置意义：

- Campaign 判断基于稳定的 robot slug，不依赖 robot ID。
- 同一个 slug 可对应多个 robot ID。
- 每日限制仅明确配置 Amplifier 和 Innovator。
- 排行榜只统计 Campaign 开始时间之后产生的历史。

### 6.2 加入队列与每日次数限制

`join_queue` 在锁定 robot status 时额外读取 `robot_slug`。

对于 Campaign robot 和受限会员等级，查询：

```sql
SELECT COUNT(*)
FROM tele_op_control_history
WHERE user_id = :uid
  AND campaign_key = :campaign_key
  AND DATE(issued_at AT TIME ZONE 'UTC') = DATE(NOW() AT TIME ZONE 'UTC')
```

达到限制时返回 `403`：

- Amplifier：每天最多 3 次。
- Innovator：每天最多 6 次。
- 日期边界按 UTC，而不是用户本地时区。
- 当前计数依据已创建的 control history，不要求 session 已完成或已获得积分。

### 6.3 Control History Campaign 标记

`use_robot` 创建控制记录时新增 `campaign_key`：

```text
teleop-cup-arm → campaign_key = teleop-cup-arm
其他 robot     → campaign_key = NULL
```

这使每日限制、积分和排行榜能从共享的 `tele_op_control_history` 中隔离 Campaign 数据。

### 6.4 Vision Enablement 与 Vision Points

Vision 原来只对 `arena-arm` 开启，现在改为 slug set 判断，因此 `teleop-cup-arm` 也会触发 Vision compare。

Vision 结果更新：

- 写入 `controlled_result` 和 `controlled_status`。
- `reward_points += reward_inc`。
- 如果 `campaign_key = teleop-cup-arm`，同时执行 `campaign_points += reward_inc`。
- SQL 限制 `controlled_status IS NULL`，相同 control token 已处理后不会再次累计 Vision reward。
- 使用 `UPDATE ... RETURNING user_id`，只有实际更新成功且奖励大于 0 时才继续写用户积分流水。

### 6.5 Session 时长积分

`process_session_rewards` 增加 Campaign 逻辑：

1. 读取 `campaign_key`。
2. 根据 `issued_at` 计算 session duration。
3. 如果 inactive，eligible duration 扣除 30 秒，最低为 0。
4. inactive 且总时长小于 50 秒时，本次时长积分为 0。
5. 其他情况按 `int(eligible_duration_seconds * 0.3)` 计算。
6. Campaign session 将同样的时长积分累加到 `campaign_points`。
7. 使用 `controlled_end_time IS NULL` 防止 session end 重复处理。

普通 reward points 仍保留首次用户 3000 分逻辑；Campaign Points 不使用 3000 分首次奖励，而是按本次 eligible duration 独立计算。这保证 World Cup 排行榜不会因平台首次奖励失真。

### 6.6 Session Complete 返回值

`fetch_tele_op_session_complete_status` 使用条件表达式：

```sql
CASE
    WHEN campaign_key = 'teleop-cup-arm'
    THEN COALESCE(campaign_points, 0)
    ELSE reward_points
END AS reward_points
```

兼容性说明：

- 前端仍读取原来的 `reward_points` key。
- Teleop Cup Arm 显示的是 Campaign Points。
- 其他 robot 行为不变。

### 6.7 Cup Leaderboard 更新 API

```http
POST /tele_op/teleop_cup_leaderboard/update
Authorization: Bearer {INTERNAL_API_TOKEN}
```

逻辑：

- 仅接受完全匹配的内部 API token；否则返回 `401`。
- 从 `robot_status` 查询所有 `teleop-cup-arm` robot IDs；未配置返回 `404`。
- 在一个 DB transaction 中清空并重建 `teleop_cup_leaderboard`。
- 统计 `campaign_key = teleop-cup-arm` 且 `issued_at >= 2026-07-13 00:00:00` 的记录。
- 只保留 `Amplifier Member` 和 `Innovator Member`。
- 按总 Campaign Points、总控制时长、user ID 排名。
- 用户有 email 时保存 email；没有 email 时保存优先级最高的收款钱包地址。
- 返回更新条数和匹配到的 robot IDs。

### 6.8 Cup Leaderboard 查询 API

```http
GET /tele_op/teleop_cup_leaderboard
GET /tele_op/teleop_cup_leaderboard?userId={userId}
```

响应结构示例：

```json
{
  "leaderboard": [
    {
      "user_id": "123",
      "total_points": 120,
      "rank": 1,
      "controlled_hours": 0.25,
      "email": "u***@example.com",
      "wallet_address": null,
      "user_class": "Innovator Member"
    }
  ],
  "self": {
    "user_id": "999",
    "total_points": 10,
    "rank": 58,
    "controlled_hours": 0.02,
    "email": null,
    "wallet_address": "0x12***89",
    "user_class": "Amplifier Member"
  }
}
```

- `leaderboard` 最多返回 Top 50。
- 当前用户不在 Top 50 时，只要排行榜表中存在该用户，仍可通过 `self` 返回。
- Email 和 wallet address 经 `mask_sensitive_value` 脱敏。
- 当前 GET endpoint 本身没有新增登录或内部 token 校验。

---

## 七、数据库与部署前置条件

本次后端 commit 使用了以下结构，但没有在同一 commit 中提供 migration：

```text
tele_op_control_history.campaign_key
tele_op_control_history.campaign_points
teleop_cup_leaderboard 表
```

部署前必须确认：

- 两个新字段已存在，并为历史数据提供兼容默认值或允许 NULL。
- `teleop_cup_leaderboard.user_id` 具有用于 `ON CONFLICT (user_id)` 的 unique constraint/index。
- 排行榜表包含 `total_points`、`rank`、`controlled_hours`、`email`、`wallet_address`、`updated_at`。
- `robot_status` 至少存在一条 `robot_slug = teleop-cup-arm` 的配置。
- `INTERNAL_API_TOKEN` 已配置给排行榜定时刷新调用方。
- 定时任务/外部服务会主动调用 update API；当前代码没有展示自动调度逻辑。
- Campaign start timestamp 与数据库 session timezone 的解释方式已经确认。

如果数据库结构未准备好，加入队列、创建控制记录、结束 session、刷新排行榜和查询排行榜都可能返回 500。

---

## 八、测试分析与风险

| 模块 | 风险等级 | 测试重点 |
|---|---|---|
| Robot 配置 | 高 | slug 与 robot ID 映射、未配置 robot、多个同 slug robot |
| 每日控制限制 | 高 | Amplifier 3 次、Innovator 6 次、UTC 跨日、并发 join |
| Campaign Points | 高 | 时长、inactive 扣减、首次奖励隔离、Vision 累加、幂等 |
| 数据库兼容性 | 高 | 新字段、排行榜表、unique constraint、历史 NULL 数据 |
| 排行榜 | 高 | 开始时间、会员过滤、排序 tie-break、Top 50+self、刷新鉴权 |
| Session Complete | 中 | Campaign Points 映射到旧 `reward_points` key，其他 robot 不回归 |
| 前端条件展示 | 中 | Cup tab 只对正确 slug 出现，切换 robot 后状态恢复 |
| 隐私 | 高 | Email/wallet 必须脱敏，GET endpoint 当前无新增鉴权 |
| Campaign 图片/UI | 低 | 图片比例、fallback 名称、移动端卡片和灰度展示 |

### 需要产品或开发确认的问题

1. 每日次数是按“获得过 control token”计数，还是只统计成功完成的 session？当前实现是前者。
2. 用户加入队列时未产生 control history；并发请求或多个排队入口是否可能超过每日限制？
3. Campaign start 使用无 timezone 的字符串 cast，数据库 timezone 是否固定为 UTC？
4. Cup Leaderboard GET 是否应该公开访问，还是需要用户鉴权？
5. Vision reward 与时长 reward 同时进入 Campaign Points 是否符合最终计分规则？
6. inactive 小于 50 秒完全不得分、超过 50 秒再扣 30 秒是否为最终产品规则？
7. Campaign 结束时间和排行榜冻结策略尚未在代码中体现。

---

## 九、E2E 测试前置条件

### 账号

- Amplifier Member 用户 A。
- Innovator Member 用户 B。
- 非 Amplifier/Innovator 用户 C，用于会员范围验证。
- 有 email 用户和仅有 wallet address 用户各一名。
- 可使用内部 API token 的测试客户端。

### Robot 与环境

- `robot_status` 配置至少一台 `teleop-cup-arm`。
- 至少一台普通 robot 和一台 `arena-arm`，用于回归对比。
- Teleop Cup Arm 可进入 available、busy、paused 等状态。
- Vision compare 测试环境能返回成功、失败和重复 callback。
- 可以控制测试时间或准备 UTC 23:59/00:00 边界数据。

### 数据库

- Campaign 字段和排行榜表已部署。
- 可准备 Campaign start 前后、不同会员等级、同分同控制时长的数据。
- 测试完成后能够清理或隔离 Campaign control history 和排行榜快照。

---

## 十、E2E 测试用例

| Case ID | 标题 | 前置条件 | 测试步骤 | 预期结果 |
|---|---|---|---|---|
| PRIS-287-E2E-001 | Teleop Selection 展示 World Cup Arm 卡片 | 后端返回 `teleop-cup-arm` robot | 1. 登录并进入 Teleop Selection。<br>2. 找到 World Cup 卡片。<br>3. 检查图片、名称和描述。 | 1. 显示 `Teleop Cup Arm`。<br>2. 描述包含 Amplifier 3/day、Innovator 6/day。<br>3. 足球机械臂图片完整显示且为灰度。<br>4. 无 broken image。 |
| PRIS-287-E2E-002 | Robot name fallback | 前端有 Cup 配置；后端 robot name 为空但 slug 与 ID 映射存在 | 1. 打开 Teleop Selection。 | 卡片名称 fallback 为 `Teleop Cup Arm`，不显示空标题或 `undefined`。 |
| PRIS-287-E2E-003 | 点击 Cup Arm 进入原有 Teleop 流程 | Cup robot available | 1. 点击 Cup Arm 卡片。<br>2. 加入队列并等待获得控制权。 | 1. 使用 Cup robot ID 进入队列。<br>2. 正常收到 queue/control 状态。<br>3. 不进入其他 robot session。 |
| PRIS-287-E2E-004 | Cup Leaderboard tab 条件展示 | Cup robot 与普通 robot 均可选择 | 1. 选择 Cup robot。<br>2. 检查右侧 tabs。<br>3. 切换普通 robot。 | 1. Cup robot 显示 `Cup Leaderboard`。<br>2. 普通 robot 不显示该 tab。<br>3. 切换 robot 后 active tab 自动恢复为默认 panel。 |
| PRIS-287-E2E-005 | Cup Leaderboard 前端请求 | Cup robot；当前用户有 user ID | 1. 点击 `Cup Leaderboard`。<br>2. 检查 Network 和页面。 | 请求 `/tele_op/teleop_cup_leaderboard?userId={id}`；页面展示排行榜且无 JS error。 |
| PRIS-287-E2E-006 | Amplifier 前 3 次允许控制 | Amplifier 当日 UTC 计数为 0 | 1. 连续完成/获得 3 次 Cup control token。<br>2. 每次重新加入队列。 | 前 3 次均可通过 Campaign limit 检查并创建带 `campaign_key` 的 history。 |
| PRIS-287-E2E-007 | Amplifier 第 4 次被拒绝 | Amplifier 当日已有 3 条 Cup control history | 再次加入 Cup queue。 | 返回 `403`；错误文案说明每天最多 3 次；不新增 control history。 |
| PRIS-287-E2E-008 | Innovator 前 6 次允许、第 7 次拒绝 | Innovator 当日初始计数为 0 | 连续尝试 7 次获得 Cup 控制。 | 前 6 次允许；第 7 次返回 `403`，文案说明每天最多 6 次。 |
| PRIS-287-E2E-009 | 普通 robot 不受 Cup 每日限制 | 用户已达到 Cup 每日上限；普通 robot available | 加入普通 robot queue。 | 不使用 Cup limit 拒绝；普通 robot 可按原规则排队。 |
| PRIS-287-E2E-010 | UTC 跨日后次数重置 | 用户在 UTC 当日达到上限；可控制时间跨至次日 00:00 | 在 UTC 次日再次加入 Cup queue。 | 新 UTC 日计数从 0 开始，用户重新获得对应会员等级的日额度。 |
| PRIS-287-E2E-011 | 并发加入队列的额度一致性 | Amplifier 当日已有 2 次 | 同时发送两个 join queue 请求。 | 最终最多一个请求进入可产生第 3 次控制的流程；不得形成第 4 条 Campaign history。若两者均通过，记录为并发缺陷。 |
| PRIS-287-E2E-012 | Control history 正确写入 campaign_key | 用户获得 Cup 控制 token | 完成 `use_robot` 并查询测试 DB。 | 新 history 的 `campaign_key = teleop-cup-arm`；普通 robot history 为 NULL。 |
| PRIS-287-E2E-013 | 正常 session Campaign 时长积分 | Cup session 持续 100 秒且非 inactive；无 Vision reward | 正常结束 session。 | Campaign 时长积分为 `int(100 × 0.3) = 30`；controlled end time/hours 被写入。 |
| PRIS-287-E2E-014 | Inactive session 扣除 30 秒 | Cup session 持续 100 秒并按 inactive 结束 | 触发 inactive reward processing。 | Eligible duration 为 70 秒；Campaign 时长积分为 21。 |
| PRIS-287-E2E-015 | Inactive 短 session 不得分 | Cup session inactive，持续 49 秒 | 结束 session。 | 本次时长 reward 和 Campaign Points 均不增加。 |
| PRIS-287-E2E-016 | Inactive 50 秒边界 | 分别准备 49.9、50、50.1 秒 inactive session | 逐一处理结束奖励。 | `<50` 进入零分分支；`>=50` 按扣除 30 秒后的 eligible duration 计算，边界行为与代码一致。 |
| PRIS-287-E2E-017 | 首次用户 3000 普通奖励不进入 Cup 排行分 | 新用户首次控制 Cup Arm；session 100 秒 | 完成 session 并读取 history/Session Complete。 | 普通 reward 按首次奖励规则处理；Campaign 时长积分为 30，而不是 3000；Session Complete 显示 Campaign Points。 |
| PRIS-287-E2E-018 | Vision reward 累加 Campaign Points | Cup session；Vision compare 返回正 reward | 1. 触发 Vision callback。<br>2. 结束 session。 | Vision reward 累加到普通 reward；Campaign session 同时累加到 campaign_points；最终 Campaign Points 为时长分加 Vision 分。 |
| PRIS-287-E2E-019 | Vision callback 幂等 | 同一 control token 和相同结果 callback 两次 | 连续调用两次 Vision compare。 | 只有第一次在 `controlled_status IS NULL` 时更新；第二次不重复增加 reward/campaign points 或用户积分流水。 |
| PRIS-287-E2E-020 | Arena Arm Vision 回归 | Arena Arm session | 触发 Vision compare 并完成 session。 | Arena Arm 仍启用 Vision；不写 Cup campaign key/points；Session Complete 返回普通 reward points。 |
| PRIS-287-E2E-021 | Campaign session end 幂等 | 同一 Cup control token | 重复触发两次 session reward processing。 | 只有第一次更新 `controlled_end_time` 和积分；第二次不重复累加。 |
| PRIS-287-E2E-022 | Session Complete 显示 Campaign Points | Cup history 同时存在普通 reward=3000、campaign points=30 | 请求 Session Complete 状态并打开 modal。 | API 的 `reward_points` 返回 30；前端 Modal 显示 30，不显示 3000。 |
| PRIS-287-E2E-023 | 未授权刷新排行榜 | 无 token、错误 token、普通用户 token | 分别 POST leaderboard update。 | 均返回 `401 Unauthorized`；排行榜表不改变。 |
| PRIS-287-E2E-024 | 有效内部 token 刷新排行榜 | 正确 INTERNAL_API_TOKEN；存在 Cup robot 和历史 | POST leaderboard update。 | 返回 `200`、`status=ok`、更新条数和 robot IDs；排行榜按当前历史重建。 |
| PRIS-287-E2E-025 | 未配置 Cup robot 时刷新失败 | 测试环境临时无 `teleop-cup-arm` robot_status | 使用有效内部 token刷新。 | 返回 `404` 和明确配置错误；不生成错误排行榜。 |
| PRIS-287-E2E-026 | Campaign start 前数据被排除 | 同一用户在开始时间前后都有 Cup history | 刷新排行榜并核对总分/时长。 | 只累计 `2026-07-13 00:00:00` 及之后记录。 |
| PRIS-287-E2E-027 | 非目标会员不进入排行榜 | Amplifier、Innovator、其他 user class 均有 Cup points | 刷新并查询排行榜。 | 只包含 Amplifier 和 Innovator；其他等级不出现。 |
| PRIS-287-E2E-028 | 排名 tie-break 顺序 | 多用户同分；部分同 controlled hours | 刷新排行榜。 | 先按 points 降序，再按 controlled hours 降序，仍相同按 user ID 排序；rank 连续且稳定。 |
| PRIS-287-E2E-029 | Top 50 与 self | 当前用户排名第 51 或更低 | GET leaderboard 并传 `userId`。 | `leaderboard` 只含 Top 50；响应额外包含当前用户 `self` 排名。 |
| PRIS-287-E2E-030 | Email 和 Wallet 脱敏 | 一名有 email 用户、一名仅 wallet 用户上榜 | GET leaderboard。 | Email/wallet 均经过掩码；不返回完整敏感值；有 email 时按当前逻辑不返回 wallet。 |
| PRIS-287-E2E-031 | 空排行榜 | 表为空 | GET leaderboard。 | 返回 `200` 和 `leaderboard=[]`；无 user match 时不返回 `self`；前端显示可控空状态。 |
| PRIS-287-E2E-032 | 多个 Cup robot ID 聚合 | 两台 robot 使用相同 Cup slug并产生 Campaign history | 刷新排行榜。 | update 响应包含两个 robot IDs；所有带 Cup campaign key 的历史统一进入 Campaign 排名。 |
| PRIS-287-E2E-033 | 数据库结构缺失时部署保护 | 隔离环境缺少字段或排行榜表 | 执行 join/use/session/leaderboard smoke test。 | 部署检查应在放量前失败并阻止上线；不能到用户流程才暴露 500。 |
| PRIS-287-E2E-034 | 移动端 Cup 卡片和右侧 Panel | viewport 390×844；Cup robot configured | 1. 打开选择页。<br>2. 进入 Cup Teleop。<br>3. 切换 Cup Leaderboard/Live Chat。 | 卡片不溢出；图片比例正常；tabs 可操作且 active indicator 对齐；排行榜可滚动。 |
| PRIS-287-E2E-035 | 普通 Teleop 全流程回归 | 普通 robot available | 选择、排队、控制、结束并查看普通 leaderboard。 | 原有 Teleop 行为、普通积分和 leaderboard endpoint 不受 Campaign 改动影响。 |

---

## 十一、建议的测试优先级

### P0

- 数据库结构与 robot 配置 smoke test。
- Amplifier/Innovator 每日额度及 UTC 跨日。
- Campaign Points：正常、inactive、首次奖励隔离、Vision、幂等。
- Session Complete 返回 Campaign Points。
- Leaderboard update 鉴权、开始时间、会员过滤与排序。

### P1

- Top 50 + self。
- Email/wallet 脱敏。
- Cup tab 条件展示及切换 robot 状态恢复。
- 并发 join 额度一致性。
- Arena Arm 和普通 Teleop 回归。

### P2

- Campaign 图片、fallback 名称和移动端布局。
- 空排行榜、多个 Cup robot ID。
- 长时间运行后的性能与排行榜刷新耗时。

---

## 十二、验收结论模板

| 验收项 | 结果 | 备注/证据 |
|---|---|---|
| Teleop Cup Arm 前端入口 | Pending | |
| Amplifier 3/day | Pending | |
| Innovator 6/day | Pending | |
| UTC 跨日重置 | Pending | |
| Campaign 时长积分 | Pending | |
| Vision Campaign Points | Pending | |
| Session/Callback 幂等 | Pending | |
| Session Complete | Pending | |
| Cup Leaderboard Update | Pending | |
| Cup Leaderboard Query | Pending | |
| 隐私脱敏 | Pending | |
| 数据库与配置前置条件 | Pending | |
| 普通 Teleop/Arena 回归 | Pending | |

