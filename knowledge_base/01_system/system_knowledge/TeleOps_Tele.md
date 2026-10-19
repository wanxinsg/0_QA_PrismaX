## Tele-Op 系统业务总览

Tele-Op（远程机械臂控制）系统由 `app_prismax_tele_op_services` 提供后端能力，核心目标是：
- **管理用户排队控制多个机器人（由后端 `robot_status` 的 `robot_id` / `robot_class` / `robot_slug` 等驱动，如 arm1 / arm2 / arm3 / arm4）**
- **与前端实时同步队列与机器人状态（Socket.IO + Redis）**
- **记录与结算控制时长、积分与排行榜**
- **在 Tele-Op 任务结束后调用视觉识别服务进行成果判定与积分奖励**

系统主要依赖以下数据库表（从代码推断）：
- `robot_status`：每个机器人当前状态（是否可用、当前控制用户、直播暂停、WebSocket / 流媒体地址等）；**PRIS-130 起**还包含 `robot_class`、`robot_name`、`robot_slug`，用于前端路由与按“机器人类型”区分排队规则。
- `robot_queue`：各机器人队列（waiting / active / completed / left 等）、用户位置、控制 token、激活时间
- `users`：用户基本信息、等级（Explorer / Amplifier / Innovator）、钱包地址、累计积分等
- `tele_op_control_history`：每次控制会话的控制 token、起止时间、控制时长（小时）、奖励积分、结果 JSON 等
- `point_transactions`：用户积分变更流水（首次 Tele-Op 奖励、控制奖励、视觉任务奖励等）
- `tele_op_leaderboard` / `monad_leaderboard`：Tele-Op 排行榜与 Monad 特定排行榜
- `purchase_records`：用于校验 `robot_class == 'access'`（原 arm2）使用资格（是否有 Monad 购买记录）

## 模块与组件划分

### Web 应用与基础设施

- **`app.py`**：Flask + Flask-SocketIO 主服务，负责：
  - 初始化 Flask、CORS、SocketIO（使用 Redis 作为消息队列）
  - 从 GCP Secret Manager 读取数据库、JWT、Redis、机器人控制 URL、AES 密钥等
  - 创建 Cloud SQL（PostgreSQL）连接池（`get_db_connection`）
  - 管理 Tele-Op 队列相关 HTTP API 与 WebSocket 事件
  - 启动 APScheduler 后台任务定时检查超时会话

- **后台任务 `start_background_jobs` + `check_and_update_robot_availability`**
  - 每 10 秒扫描所有机器人：
    - 从 `robot_status` + `robot_queue` 拿到当前 active 会话与已用时长
    - 若激活时间超出 `TIMEOUT_SEC = 300` 秒（5 分钟），触发：
      - `release_robot_and_activate_next`：结束当前会话、释放机器人、激活下一个队列用户
      - 同时更新队列并通过 SocketIO 广播

### 队列与会话管理模块 `queue_helper.py`

该模块集中封装 Tele-Op 队列业务逻辑：

- **`get_queue_data(conn, robot_id)`**
  - 查询指定机器人在 `robot_queue` 中所有 waiting/active 记录，按 position 排序
  - Join `users` 获取用户名、邮箱、各链钱包地址、会员等级等
  - 计算 active 用户剩余控制时间（300 秒减去已用秒数）
  - 返回结构：
    - `robotId`
    - `queue`：用户列表（user_id、username、email、wallet_address、position、status、remaining_time、member_class）
    - `robotAvailable`：来自 `robot_status.is_available`

- **`broadcast_queue_update(conn, robot_id, to_sid=None, socketio=None)`**
  - 调用 `get_queue_data` 获取最新队列
  - 若 `to_sid` 存在则只推送给指定客户端，否则广播到以 `robot_id` 为房间名的 SocketIO 房间
  - 事件名统一为 `queue_update`

- **`check_and_update_robot_availability(get_db_connection, access_secret_version, socketio=None)`**
  - 后台定时扫描所有机器人：
    - 更新 `robot_status.last_check`
    - 若发现 active 会话且 `elapsed_sec > TIMEOUT_SEC`：
      - 记录日志
      - 调用 `release_robot_and_activate_next` 执行会话结束与机器人释放、队列推进

- **`process_session_rewards(conn, control_token, user_id, inactive=False)`**
  - 根据控制 token 为 Tele-Op 会话结算积分：
    - 校验 `tele_op_control_history` 中是否存在该 token，且 `controlled_end_time` 为空（未结算）
    - 检查用户是否已有 `first_time_tele_op` 且 `points_change = 3000` 的积分流水
    - 计算本次会话时长：`current_time - issued_at`
    - 奖励逻辑：
      - 若 `inactive=True` 且时长 < 50 秒：**奖励 0 分**
      - 若从未获得过首次奖励：
        - 本次只给 **3000 分**，`transaction_type = 'first_time_tele_op'`
      - 否则按时长发放：
        - 若 `inactive=True`，时长减 30 秒后再计算
        - 奖励积分 = `int(session_duration_seconds * 0.3)`，`transaction_type = 'robot_control_reward'`
    - 更新 `tele_op_control_history`：
      - 设置 `controlled_end_time = now`
      - 计算 `controlled_hours`（秒数 / 3600，保留 4 位小数）
      - 写入本次 `reward_points`
    - 若积分 > 0：
      - 累加到 `users.total_points`
      - 在 `point_transactions` 写入一条记录
    - 注意：对 `control_token` 的更新带有幂等保护，避免重复结算

- **`release_robot_and_activate_next(conn, robot_id, user_id, socketio=None)`**
  - 获取当前 active 用户在 `robot_queue` 中的控制 token
  - 将该用户的队列记录 `status` 改为 `completed`
  - 调用 `process_session_rewards` 完成本次会话积分结算
  - 更新 `robot_status`：
    - `is_available = TRUE`
    - `current_user_id = NULL`
  - 调用 `activate_next_user_in_queue` 激活下一个 waiting 用户

- **`activate_next_user_in_queue(conn, robot_id, socketio=None)`**
  - 按 position 升序从 `robot_queue` 中查找第一个 `status = 'waiting'` 的用户（`FOR UPDATE` 锁定行）
  - 若不存在 waiting 用户则返回 False
  - 为该用户生成随机 `control_token`
  - 更新该用户队列记录：
    - `status = 'active'`
    - `control_token = <生成 token>`
    - `activated_at = NOW()`
    - `position = 1`
  - 更新 `robot_status`：
    - `current_user_id = user_id`
    - `is_available = FALSE`
  - 将其它 waiting 用户 position 全部减 1，保证队列连续
  - 如果提供 `socketio`，调用 `broadcast_queue_update` 通知前端

- **`handle_user_leave_queue(conn, robot_id, user_id, inactive=False, socketio=None)`**
  - 用户主动离开队列（可能是 active 或 waiting 状态），流程：
    - 查询该用户在 `robot_queue` 中的当前状态与位置
    - 若不存在对应队列记录，直接返回 False
    - 将其 `status` 改为 `left`
    - 若原状态为 `active`：
      - 查出该用户最近一次 `status = 'left'` 的 `control_token`
      - 调用 `process_session_rewards` 进行奖励结算（支持 `inactive=True` 的特殊处理）
      - 把 `robot_status` 改为可用
      - 尝试 `activate_next_user_in_queue` 激活下一个用户
      - 若没有下一个用户，确保机器人保持 `is_available = TRUE, current_user_id = NULL`
    - 若原状态为 `waiting`：
      - 把该用户后面的 waiting 用户 position 全部 -1，保持队列连续
    - 最后通过 `broadcast_queue_update` 广播最新队列

- **`get_queue_statistics(get_db_connection, robot_id=None)`**
  - 统计 24 小时内 Tele-Op 队列使用情况，用于监控：
    - 指定机器人：waiting / active / completed 数量
    - 所有机器人：每个机器人 waiting / active 数量

### 视觉识别模块 `image_recognitions.py`

该模块封装使用 OpenAI 视觉模型进行“娃娃数量对比”识别，是 Tele-Op 成果判定（抓娃娃成败）的核心：

- **基础能力**
  - 从 GCP Secret Manager 读取 OpenAI API Key，并懒加载 `OpenAI` 客户端
  - 定义不同机器人场景的提示词：
    - `PROMPT1`：arm1（左为矩形托盘，右为圆形托盘）
    - `PROMPT2`：arm2/arm3（透明亚克力盒，左右由黑线分隔）
  - 将 base64 图片转换为 `data:image/...` URL 供 OpenAI 调用

- **`analyze_single_image(image_b64, robotId, model_name="gpt-4o")`**
  - 对单张图片进行计数：
    - 使用 Responses API，system + user 双角色构造提示
    - 要求模型严格返回 `{"left": <int>, "right": <int>}` JSON
  - 解析模型返回（尽量从原始文本中提取 JSON 段），最终返回左右计数

- **`analyze_compare(views, robotId, model_name="gpt-4o")`**
  - 对多视角（cam1/cam2/…）的 START/END 图片逐一调用 `analyze_single_image`
  - 输出结构：
    - `views[cam_id]["start"] = {left, right}`
    - `views[cam_id]["end"] = {left, right}`
    - 并附带耗时等 meta 信息

- **`analyze_compare_pairwise(views, robotId, model_name)`**
  - 针对同一视角的 START/END 两张图片，构造更复杂 Prompt：
    - 同时计算两张图各自 left/right
    - 额外判断从左到右、右到左移动了多少个物体
  - 若 pairwise 解析失败，则回退到逐帧 `analyze_single_image`
  - 输出：
    - `views[cam_id]["start"/"end"] = {left, right}`
    - `meta["moved"][cam_id] = {"l_to_r", "r_to_l"}`

- **`evaluate_compare_result(res)`**
  - 根据识别结果检查一致性：
    - START/END 总数是否相等（保证物体总数守恒）
    - 左减右的变化是否互为相反数（dl == -dr）
  - 汇总所有相机视角，返回：
    - `abnormal`: 是否有不一致/异常
    - `success_count`: 成功移动的物体数量总和

- **`single_frame_views_by_index`、`_majority`、`_get_counts_from_attempt`、`build_voted_views_across_five`**
  - 针对第三次尝试，利用最多 5 帧（1~5）结果进行“投票”整合：
    - 先复用前两次尝试（result1/result2）的结果
    - 再对额外帧做单帧识别
    - 最终对每一侧的多次计数取众数，得到更稳定的最终计数

## 主要业务流程说明

### 1. Tele-Op 直播与机器人状态展示

- 前端通过 `/robots/status` 获取机器人概要状态：
  - 每个 `robot_id` 对应一条记录，包含：
    - `is_available`：当前是否空闲
    - `current_user`：当前控制用户名称
    - `queue_length`：队列长度（waiting + active）
    - `youtube_stream_id`：对应直播流 ID
    - `live_paused`：直播是否被暂停（影响能否排队）
    - **`robot_class`**（PRIS-130）：机器人类型，用于排队规则分支，如 `'access'`（邀请制）、`'training'`（训练臂）、`'open'`（开放臂）等
    - **`robot_name`**（PRIS-130）：展示用名称，前端用于导航栏、队列提示等
    - **`robot_slug`**（PRIS-130）：URL 用 slug，前端路由为 `/tele-op/:robotSlug`，需与后端一致以保证正确进入对应机器人页

- 前端通过 `/get_live_paused_status` 获取所有机器人 `live_paused` 状态，用于 UI 显示与排队按钮开关。

### 2. 用户排队加入逻辑 `/queue/join`

整体 join 流程（POST）：

1. **参数与认证**
   - 请求体必须携带 `userId`、`robotId`
   - Header 中必须有 `Authorization: Bearer <token>`，与 `users.hash_code` 一致，否则返回 401

2. **机器人状态检查**
   - 查询 `robot_status`：
     - 若机器人不存在返回 404
     - 若 `live_paused = TRUE` 且非 TEST_MODE，禁止加入队列，返回 403

3. **用户与会员等级校验**
   - 从 `robot_status` 读取当前机器人的 **`robot_class`**、`robot_name`（PRIS-130）。
   - 从 `users` 读取：
     - `user_name`、`user_class`、`hash_code`、`monad_receive_address`
   - 限制规则：
     - `Explorer Member`：**不能使用机器人**，返回 403
     - 若 **`robot_class == 'access'`**（PRIS-130，原 arm2 逻辑）：
       - 必须有 Monad 钱包地址，或者在 `purchase_records` 中存在非空 Monad 交易 hash，否则返回 403（提示连接 Monad 钱包）
       - 且需通过邀请码校验（见下）

4. **跨机器人队列互斥**
   - 查询 `robot_queue`：
     - 若用户在其他机器人上有 `status in ('waiting','active')` 的记录，则不能加入当前队列，返回 403

5. **重复加入处理**
   - 若用户已经在当前机器人队列中（waiting/active），直接返回其 position 与提示 “Already in queue”

6. **邀请码校验（仅 `robot_class == 'access'`）**
   - 若机器人为 **`robot_class == 'access'`**：用户必须已绑定有效邀请码（或本次请求带有效邀请码），否则返回 403；通过后才继续后续排队逻辑。

7. **会员权益规则（按 robot_class，PRIS-130）**
   - **Amplifier Member**
     - **`robot_class == 'training'`**（原 arm1/arm4）：每天（UTC）最多加入 3 次该机器人队列，多于 3 次返回 403，错误文案含 `robot_name`，如 "Amplifier members can join the queue for {robot_name} up to 3 times per day (UTC)"
     - **`robot_class == 'open'`**（原 arm3）：一生最多 3 次该机器人的 `tele_op_control_history` 记录，再次加入返回 403，错误文案以 "Amplifier members have reached the 3 total uses limit for" 开头并含 `robot_name`，前端据此弹升级弹窗
   - **Innovator Member**
     - 拥有“快速通道”（fast_track）权益：
       - 每天（UTC）最多使用 fast track 6 次（全机器人共享）
       - 代码逻辑：
         - 先普通插入到队列末尾（position = max_pos + 1）
         - 检查过去一天内该用户 `fast_track = TRUE` 的记录数
         - 若未超出限制，则尝试把本次 position 向前移动：
           - 若已有其他 Innovator fast_track 用户，则排到最后一个 Innovator fast_track 用户后面
           - 若没有，则：
             - 如果有当前 active 用户：理想情况排在 position 2；若 position2 已有 waiting 用户，则排在 position2 用户之后
             - 如果没有 active 用户：尝试直接排到队首 position 1
         - 若最终 `final_position < initial_position`：
           - 将 `final_position` 到 `initial_position-1` 区间的其他用户 position +1 让出位置
           - 更新本用户 position 为 `final_position`，并标记 `fast_track = TRUE`
       - 若 fast track 次数已达上限，则保留普通队列位置，并在响应中附加提示文案（如 "You have reached the maximum 6 fast tracks a day. Please come back tomorrow."）。

8. **激活队首用户**
   - 若本用户最终 position=1 且机器人当前 `is_available = TRUE`：
     - 检查当前机器人是否已有 active 用户（确保幂等）
     - 若没有，则调用 `activate_next_user_in_queue` 立即将其激活

9. **队列变更广播**
   - 调用 `broadcast_queue_update`，将最新队列状态推送给该机器人房间的所有 SocketIO 客户端

### 3. 获取控制 Token 与控制会话

#### 3.1 前端在队首后获取控制 Token `/queue/control-token`

- 条件：
  - 需提供 `userId`、`robotId` 与 `Authorization` header
  - 校验 `users.hash_code`，否则 401
  - 查找 `robot_queue` 中：
    - `robot_id = robotId`
    - `user_id = userId`
    - `status = 'active'`
    - `position = 1`
- 若不存在，返回 403 “Not at front of queue or not active”
- 若存在：
  - 取出 `control_token` 与 `activated_at`
  - 返回：
    - `control_token`
    - `expires`：`activated_at + 5 分钟` 的 Unix 时间戳
    - `robotId`

#### 3.2 前端请求实际控制入口 `/use_robot`

- 请求体：`robotId`、`userId`，以及 `Authorization` header
- 步骤：
  1. 再次认证用户，并检查 `Explorer Member` 限制
  2. 确认该用户在 `robot_queue` 中处于 `active` 状态，并取出 `control_token` 与 `activated_at`
  3. 根据 `TELE_OP_CONTROL_URL_ARM_<robotId>` 从 Secret Manager 获取机器人 WebSocket 控制 URL
  4. 查询 `robot_status` 获取两路流媒体 WebSocket URL（`stream1_ws_url`、`stream2_ws_url`）
  5. 调用 `probe_robot_sync` 向机器人服务器发一次 WebSocket `{"type":"lock_request","token": control_token}` 探测其空闲情况（即便返回 busy 也不会中断流程）
  6. 将 `robot_status.is_available` 置为 FALSE，避免并发占用
  7. 若 `tele_op_control_history` 中不存在该 `control_token` 记录，则插入一条：
     - `user_id`、`robot_id`、`issued_at`、`expires_at`（由 `activated_at + 5 分钟` 计算）、`control_token`
  8. 判断是否为首次 Tele-Op 控制用户：
     - 查询 `point_transactions` 是否存在 `transaction_type = 'first_time_tele_op', points_change = 3000`
     - 用于前端展示 `isFirstTime`
  9. 使用 AES-GCM + URL_AES_KEY 对控制 URL 和流媒体 URL 做加密（`encrypt_url`）
  10. 返回：
      - `encrypted_url`：加密后的控制 WebSocket URL
      - `encrypted_stream1_url` / `encrypted_stream2_url`：加密后的流媒体 URL
      - `control_token`
      - `expires`：Unix 到期时间
      - `isFirstTime`：是否首控

#### 3.3 获取解密密钥 `/session_url_decrypt_key`

- 请求体：`userId` + `Authorization`
- 再次校验用户身份与会员等级：
  - Explorer 级别禁止获取此密钥
- 若通过：
  - 从 Secret Manager 获取 `ROBOT_URL_AES_KEY_V1`，返回 base64 编码字符串与 15 分钟过期时间 `exp`
  - 前端使用此 key 解密 `encrypted_url` 等，得到真实 WebSocket 地址

### 4. 会话结束与离队流程

#### 4.1 用户主动离开队列 `/queue/leave`

- 请求体：`userId`、`robotId`、`inactive`（是否因不活跃离开）
- 验证 `hash_code`，否则 401
- 委托 `queue_helper.handle_user_leave_queue` 处理：
  - 若用户为 active：
    - 标记 `robot_queue.status = 'left'`
    - 查 `control_token`，调用 `process_session_rewards` 进行积分结算：
      - 若 `inactive=True` 且时长极短，发 0 分
    - 若有下一个 waiting 用户则激活，否则机器人保持空闲
  - 若为 waiting：
    - 删除/标记离开，并重排序后续 position
  - 最终广播队列更新

#### 4.2 机器人侧超时断连 `/robot/disconnect`

- 供机器人服务在**控制端 30 秒无响应**时调用：
  - Header 需携带内部 `INTERNAL_API_TOKEN`，否则 401
  - 请求体包含 `robotId`
  - 后端流程：
    - 查找当前 robot active 用户
    - 若存在：
      - 调用 `handle_user_leave_queue(..., inactive=True)`，按“因不活跃离开”逻辑处理积分与队列
      - 返回 `{"status": "ok", "user_id": ...}`
    - 若不存在 active 用户，则返回 `{"status": "ok", "message": "No active user"}`

#### 4.3 机器人主动释放 `/robot/free`

- 机器人服务在内部逻辑认为可以释放机器人时调用：
  - 校验 `INTERNAL_API_TOKEN`
  - 将 `robot_status` 中对应机器人：
    - `is_available = TRUE`
    - `current_user_id = NULL`
  - 不处理队列（纯粹释放机器人），供上层逻辑结合使用

### 5. 用户 Tele-Op 历史与完成状态查询

- **`/user/control_history`**
  - 请求体：`userId` + `Authorization`
  - 验证用户身份后，从 `tele_op_control_history` 获取该用户所有 Tele-Op 会话：
    - `robot_id`、`issued_at`、`controlled_end_time`、`controlled_hours`、`reward_points`
  - 聚合返回：
    - `sessions`：每个会话的明细
    - `total_controlled_hours`：总控制时长
    - `total_reward_points`：总获积分

- **`/fetch_tele_op_session_complete_status`**
  - 用于查询某个 `control_token` 对应会话是否完成及最终结果：
    - 请求体：`userId`、`controlToken` + `Authorization`
    - 验证用户身份后，从 `tele_op_control_history` 查 target 行
    - 若 `controlled_status` 为空：返回 `{"status": "not_finished"}`
    - 若存在：返回整行字段（时间字段转 ISO 字符串），包含：
      - `controlled_status`、`controlled_result`（JSON 字符串）、`reward_points`、`controlled_hours` 等

### 6. Tele-Op 排行榜逻辑

- **`/tele_op/leaderboard/update`**
  - 内部定时任务或运维触发，用于刷新总排行榜：
    - 需内部 token 校验
    - 逻辑：
      - 建立索引 `tele_op_leaderboard_rank_idx`（如不存在）
      - 清空原表
      - 从 `tele_op_control_history` 聚合每个用户总控制小时数
      - Join `users`，取用户总积分、邮箱、多个链的钱包地址
      - 以：
        - `total_points` 降序
        - 若积分相同，则 `total_hours` 降序
        - 再按 user_id 排序
      - 按该顺序生成排名 rank，从 1 开始
      - 写入 `tele_op_leaderboard` 表，冲突时更新

- **`/tele_op/leaderboard`**
  - GET 接口，返回前 50 名排行榜 + 指定用户自己的排名信息（self）
  - 对邮箱与钱包地址进行脱敏展示（`mask_sensitive_value`）

- **`/tele_op/monad_leaderboard/update` & `/tele_op/monad_leaderboard`**
  - 与总排行榜类似，但仅统计有 `monad_receive_address` 的用户，并把该地址作为 `wallet_address`
  - 用于展示 Monad 特定活动排行榜

### 7. 视觉任务与奖励流程 `/vision/dolls_compare`

该接口通常由机器人服务在 Tele-Op 抓娃娃结束后调用，负责将多视角、多帧图片上传到后端进行 AI 判定。

1. **参数与鉴权**
   - 请求方法：POST
   - JSON 体包含：
     - `views`：形如 `{ "cam1": {"start": [...], "end": [...]}, "cam2": {...} }` 的结构
       - 每个 `start` / `end` 可以是单帧或多帧 base64 图片
     - `robotId`：arm1 / arm2 / arm3
     - `controlToken`：对应 Tele-Op 会话的控制 token
   - Header 必须带内部 `INTERNAL_API_TOKEN`，否则 401

2. **视图归一化**
   - `_normalize_views`：
     - 对每个相机的 start/end：
       - 将字符串或列表统一为最多前 5 帧
     - 输出两个结构：
       - `norm_views`：每个相机只保留第一帧 start/end（用于前两次 pairwise 尝试）
       - `multi_views`：完整 1~5 帧 start/end 列表（用于第三次多帧投票）

3. **三阶段尝试策略**
   - **Attempt 1：第一帧 pairwise（`gpt-5.1-mini`）**
     - 使用 `analyze_compare_pairwise(norm_views, robotId, "gpt-5.1-mini")`
     - 得到每个相机 START/END 左右计数与可能的移动数
     - 通过 `evaluate_compare_result` 检测是否 abnormal + 成功移动总数

   - **Attempt 2：第二帧 pairwise（`gpt-5.1`，如必要）**
     - 若 Attempt 1 结果 abnormal，则：
       - 取 `multi_views` 的第二帧，构造 `second_only`
       - 再调用 `analyze_compare_pairwise`（`gpt-5.1`）
       - 再次用 `evaluate_compare_result` 评估

   - **Attempt 3：多帧投票（`gpt-5.1`）**
     - 若前两次仍 abnormal：
       - 调用 `build_voted_views_across_five`，综合 1~5 帧：
         - 前两帧可复用 Attempt 1/2 结果
         - 后续帧按单帧识别
         - 最后对每侧/每状态取多数票
       - 使用结果构造 `voted_result` 并再次用 `evaluate_compare_result` 检测

4. **结果判定与积分奖励**
   - 若最终 `abnormal == False` 且 `success_count > 0`：
     - `status = "success"`
     - `reward_inc = 100 * success_count`（每成功一个对象奖励 100 分）
   - 否则：
     - `status = "failed"`
     - `reward_inc = 0`

5. **写回 Tele-Op 控制历史与积分**
   - 若提供了 `robotId` 与 `controlToken`：
     - 更新 `tele_op_control_history`：
       - `controlled_result`：写入最终 views JSON 字符串
       - `controlled_status`：success / failed
       - `reward_points`：累加 `reward_inc`
     - 若 `reward_inc > 0`：
       - 查 `tele_op_control_history` 获取对应的 `user_id`
       - 更新 `users.total_points += reward_inc`
       - 在 `point_transactions` 写入一条 `transaction_type = 'dolls_compare_reward'` 的积分流水

6. **响应**
   - 返回：
     - `success: True/False`
     - `model`：使用的最终模型
     - `views`：最终每视角 START/END 计数
     - `attempts`：记录三次尝试的策略与中间结果（用于调试与审计）

## 实时队列 WebSocket 连接流程

### 客户端连接 Socket.IO `connect` 事件

- 客户端在建立 Socket.IO 连接时需要提供 `auth` 参数对象：
  - `robotId`、`token`（即用户 hash_code）、`userId`
- 服务端 `handle_connect(auth)` 逻辑：
  1. 校验 `auth` 对象格式及必要字段
  2. 到 `users` 表校验 `hash_code` 是否匹配
  3. 验证通过后：
     - 将连接加入以 `robotId` 为名的房间（`join_room(robot_id)`）
     - 调用 `get_queue_data` 获取当前机器人队列数据
     - 向该客户端发送一次 `queue_update` 事件（初始化视图）
     - 发送 `connection_success` 事件，包含：
       - `robotId`、`userId`、`sid`
  4. 任一步失败则返回 `False`，Socket.IO 将断开连接

### 队列变化的实时同步

- 下列场景变更队列后，都会通过 `broadcast_queue_update` 向对应 robot 房间广播：
  - 用户 join / leave 队列
  - 后台任务检测到超时并激活下一个用户
  - 机器人断连、释放等导致 active 用户变化
  - `activate_next_user_in_queue` 被调用成功

前端只需要监听同一个 `queue_update` 事件，即可实时更新 Tele-Op 队列 UI。

---

## Tele-Op System Overview (English)

The Tele-Op (remote robot control) system is implemented by `app_prismax_tele_op_services`. Its main goals are:
- **Manage user queues for multiple robots (driven by backend `robot_status` with `robot_id` / `robot_class` / `robot_slug`, e.g. arm1 / arm2 / arm3 / arm4)**
- **Keep queue and robot status in sync with the frontend in real time (Socket.IO + Redis)**
- **Record and settle control duration, points, and leaderboards**
- **After each Tele-Op session, run vision recognition to evaluate results and grant extra rewards**

Key database tables (inferred from the code):
- `robot_status`: current status per robot (availability, current user, live paused flag, WebSocket / stream URLs, etc.)
- `robot_queue`: queue per robot (waiting / active / completed / left), user positions, control tokens, activation timestamps
- `users`: user profile, membership tier (Explorer / Amplifier / Innovator), wallet addresses, total points, etc.
- `tele_op_control_history`: per control session, stores control token, start/end time, controlled hours, reward points, and result JSON
- `point_transactions`: every points change (first-time Tele-Op reward, control reward, vision task reward, etc.)
- `tele_op_leaderboard` / `monad_leaderboard`: leaderboards for Tele-Op and for Monad-specific events
- `purchase_records`: used to validate `robot_class == 'access'` (formerly arm2) access (whether a Monad purchase exists)

## Modules and Components

### Web Application and Infrastructure

- **`app.py`** (Flask + Flask-SocketIO main service):
  - Initializes Flask, CORS, and Socket.IO (using Redis as message queue)
  - Loads DB credentials, JWT secret, Redis URL, robot control URLs, AES key, etc. from GCP Secret Manager
  - Creates the Cloud SQL (PostgreSQL) engine (`get_db_connection`)
  - Exposes Tele-Op-related HTTP APIs and WebSocket handlers
  - Starts APScheduler background jobs to check for timed‑out sessions

- **Background jobs `start_background_jobs` + `check_and_update_robot_availability`**
  - Runs every 10 seconds:
    - Reads `robot_status` + `robot_queue` to find active sessions and elapsed time
    - If elapsed time exceeds `TIMEOUT_SEC = 300` seconds (5 minutes), it:
      - Calls `release_robot_and_activate_next` to end the current session, free the robot, and activate the next user
      - Broadcasts queue updates via Socket.IO

### Queue and Session Management (`queue_helper.py`)

This module centralizes Tele-Op queue business logic:

- **`get_queue_data(conn, robot_id)`**
  - Queries all waiting/active rows for a robot from `robot_queue`, ordered by position
  - Joins `users` to fetch username, email, wallet addresses on different chains, membership class, etc.
  - Computes remaining control time (300 seconds minus elapsed)
  - Returns:
    - `robotId`
    - `queue`: list of users (user_id, username, email, wallet_address, position, status, remaining_time, member_class)
    - `robotAvailable`: from `robot_status.is_available`

- **`broadcast_queue_update(conn, robot_id, to_sid=None, socketio=None)`**
  - Calls `get_queue_data` to get the latest queue state
  - If `to_sid` is provided, sends only to that client
  - Otherwise broadcasts to the Socket.IO room named by `robot_id`
  - Emits event `queue_update`

- **`check_and_update_robot_availability(get_db_connection, access_secret_version, socketio=None)`**
  - Periodically scans all robots:
    - Updates `robot_status.last_check`
    - If an active session exists and `elapsed_sec > TIMEOUT_SEC`:
      - Logs the timeout
      - Calls `release_robot_and_activate_next` to terminate the session, free the robot, and move the queue forward

- **`process_session_rewards(conn, control_token, user_id, inactive=False)`**
  - Settles rewards for a Tele-Op session based on its control token:
    - Checks that a row exists in `tele_op_control_history` and `controlled_end_time` is NULL
    - Checks if the user already has a `first_time_tele_op` transaction with `points_change = 3000`
    - Calculates session duration: `current_time - issued_at`
    - Reward rules:
      - If `inactive=True` and duration < 50 seconds: **0 points**
      - If the user never received the first-time bonus:
        - Grant **3000 points** only; `transaction_type = 'first_time_tele_op'`
      - Otherwise (normal sessions):
        - If `inactive=True`, subtract 30 seconds from duration before computing
        - Reward points = `int(session_duration_seconds * 0.3)`, `transaction_type = 'robot_control_reward'`
    - Updates `tele_op_control_history`:
      - Sets `controlled_end_time = now`
      - Computes `controlled_hours` (seconds / 3600, rounded to 4 decimals)
      - Writes this session’s `reward_points`
    - If reward points > 0:
      - Adds them to `users.total_points`
      - Inserts a `point_transactions` record
    - Uses idempotent update logic on `control_token` to avoid double-settlement

- **`release_robot_and_activate_next(conn, robot_id, user_id, socketio=None)`**
  - Gets the current active user’s control token from `robot_queue`
  - Marks that queue row as `status = 'completed'`
  - Calls `process_session_rewards` to finalize rewards for this session
  - Updates `robot_status`:
    - `is_available = TRUE`
    - `current_user_id = NULL`
  - Calls `activate_next_user_in_queue` to activate the next waiting user

- **`activate_next_user_in_queue(conn, robot_id, socketio=None)`**
  - Selects the first `status = 'waiting'` row for the robot from `robot_queue` (with `FOR UPDATE`)
  - If none found, returns False
  - Generates a random `control_token` for that user
  - Updates that row:
    - `status = 'active'`
    - `control_token = <generated>`
    - `activated_at = NOW()`
    - `position = 1`
  - Updates `robot_status`:
    - `current_user_id = user_id`
    - `is_available = FALSE`
  - Decrements the position of all remaining waiting users by 1 to keep positions continuous
  - If `socketio` is available, calls `broadcast_queue_update`

- **`handle_user_leave_queue(conn, robot_id, user_id, inactive=False, socketio=None)`**
  - Handles a user leaving the queue voluntarily (could be active or waiting):
    - Looks up the user’s current status and position in `robot_queue`
    - If no row, returns False
    - Sets `status = 'left'` for that user
    - If the user was `active`:
      - Fetches the most recent `control_token` with `status = 'left'`
      - Calls `process_session_rewards` (with `inactive` flag if applicable)
      - Updates `robot_status` to available
      - Attempts to `activate_next_user_in_queue`
      - If nobody is waiting, ensures `is_available = TRUE` and `current_user_id = NULL`
    - If the user was `waiting`:
      - Decrements the position of all later waiting users by 1
    - Finally, calls `broadcast_queue_update` to notify clients

- **`get_queue_statistics(get_db_connection, robot_id=None)`**
  - Computes 24‑hour queue stats for monitoring:
    - For a specific robot: waiting / active / completed counts
    - For all robots: per‑robot waiting / active counts

### Vision Recognition (`image_recognitions.py`)

This module wraps OpenAI vision models to compare doll counts and is the core of “Tele-Op result evaluation”:

- **Base capabilities**
  - Reads OpenAI API key from GCP Secret Manager and lazily initializes an `OpenAI` client
  - Defines prompts per robot scenario:
    - `PROMPT1`: arm1 (left rectangle tray, right circular tray)
    - `PROMPT2`: arm2/arm3 (transparent acrylic box, separated by a black middle line)
  - Converts base64 image strings into `data:image/...` URLs for the OpenAI API

- **`analyze_single_image(image_b64, robotId, model_name="gpt-4o")`**
  - Counts objects in a single image:
    - Uses the Responses API with system and user messages
    - Instructs the model to return strict JSON `{"left": <int>, "right": <int>}`
  - Parses the response and returns left/right counts

- **`analyze_compare(views, robotId, model_name="gpt-4o")`**
  - For each camera (cam1/cam2/…), runs `analyze_single_image` on both START and END images
  - Returns:
    - `views[cam]["start"] = {left, right}`
    - `views[cam]["end"] = {left, right}`
    - Plus a `meta` section with elapsed time, etc.

- **`analyze_compare_pairwise(views, robotId, model_name)`**
  - Given START and END images per camera, builds a pairwise prompt to:
    - Count left/right for both START and END
    - Estimate how many objects moved from left to right and from right to left
  - If JSON parsing fails, falls back to separate `analyze_single_image` calls
  - Returns:
    - `views[cam]["start"/"end"] = {left, right}`
    - `meta["moved"][cam] = {"l_to_r", "r_to_l"}`

- **`evaluate_compare_result(res)`**
  - Validates the result per camera:
    - Checks if START and END total counts are equal (conservation of objects)
    - Checks if `dl == -dr` (left/right deltas must cancel out)
  - Aggregates across all cameras and returns:
    - `abnormal`: whether any camera is inconsistent
    - `success_count`: total number of successfully moved objects

- **`single_frame_views_by_index`, `_majority`, `_get_counts_from_attempt`, `build_voted_views_across_five`**
  - Used for the third attempt (multi‑frame voting):
    - Reuses results from attempts 1 and 2 when possible
    - Analyzes additional frames individually
    - Takes a majority vote across up to 5 frames per side to get a robust final count

## Main Business Flows

### 1. Live Status and Robot Overview

- The frontend calls `/robots/status` to get a public summary:
  - For each `robot_id`:
    - `is_available`: whether it’s free
    - `current_user`: current controller’s username
    - `queue_length`: length of the queue (waiting + active)
    - `youtube_stream_id`: live stream ID
    - `live_paused`: whether the live is paused (affects queue availability)
    - **`robot_class`** (PRIS-130): e.g. `'access'`, `'training'`, `'open'`, used for join rules (invite-only, daily cap, lifetime cap)
    - **`robot_name`** (PRIS-130): display name used in nav bar and queue messages
    - **`robot_slug`** (PRIS-130): URL slug; frontend route is `/tele-op/:robotSlug`

- The frontend calls `/get_live_paused_status` to fetch `live_paused` for all robots and drive UI (enable/disable queue buttons).

### 2. Join Queue Flow `/queue/join`

Overall POST flow:

1. **Parameters and authentication**
   - Body must contain `userId` and `robotId`
   - Header must include `Authorization: Bearer <token>`, which must match `users.hash_code`; otherwise 401

2. **Robot availability checks**
   - Looks up `robot_status`:
     - If robot not found: 404
     - If `live_paused = TRUE` and not in TEST_MODE: joining is forbidden, returns 403

3. **User and membership checks**
   - Reads **`robot_class`**, **`robot_name`** from `robot_status` for the requested robot (PRIS-130).
   - Reads from `users`:
     - `user_name`, `user_class`, `hash_code`, `monad_receive_address`
   - Rules:
     - `Explorer Member`: **cannot use robots**, returns 403
     - If **`robot_class == 'access'`** (PRIS-130, formerly arm2):
       - User must have a Monad wallet connected or at least one `purchase_records` entry with a non‑empty Monad transaction hash; otherwise 403 with “connect Monad wallet” message
       - Invite code must be valid (see below)

4. **Cross‑robot mutual exclusion**
   - Queries `robot_queue`:
     - If the user is already in any other robot’s queue with `status IN ('waiting', 'active')`, joining is rejected (403)

5. **Duplicate join handling**
   - If the user is already in the target robot’s queue (waiting/active), returns the existing `position` with message “Already in queue”

6. **Invite code (only when `robot_class == 'access'`)**
   - If the robot has **`robot_class == 'access'`**, the user must have a valid bound invite code (or provide one in the request); otherwise 403. Then proceed with queue logic.

7. **Membership benefits (by robot_class, PRIS-130)**
   - **Amplifier Member**
     - **`robot_class == 'training'`** (formerly arm1/arm4): at most 3 joins per UTC day; error message includes `robot_name`, e.g. “Amplifier members can join the queue for {robot_name} up to 3 times per day (UTC)”.
     - **`robot_class == 'open'`** (formerly arm3): at most 3 lifetime uses for that robot in `tele_op_control_history`; error message starts with “Amplifier members have reached the 3 total uses limit for” and includes `robot_name`; frontend uses this prefix to show the upgrade modal.
   - **Innovator Member**
     - Has “fast track” privilege:
       - Up to 6 fast‑track uses per UTC day (across all robots)
       - Logic:
         - First, insert the user at the end of the queue (`position = max_pos + 1`)
         - Count today’s `fast_track = TRUE` entries for this user
         - If within limit, try to move the user forward:
           - If there are existing Innovator fast‑track users, place behind the last one
           - Otherwise:
             - If there is an active user: ideally move to position 2; if another waiting user already occupies position 2, place immediately after that user
             - If no active user: try to move to the head of queue (position 1)
         - If final_position < initial_position:
           - Shift other users in `[final_position, initial_position)` by +1
           - Set the current user’s position to `final_position` and mark `fast_track = TRUE`
       - If fast‑track quota is exceeded, the user keeps the normal queue position and a message is attached (e.g. “You have reached the maximum 6 fast tracks a day. Please come back tomorrow.”).

8. **Activate front user**
   - If `final_position = 1` and the robot is currently `is_available = TRUE`:
     - Double‑checks there’s no other active user (idempotency)
     - Calls `activate_next_user_in_queue` to activate immediately

9. **Broadcast queue changes**
   - Calls `broadcast_queue_update` so all Socket.IO clients in the robot’s room get the updated queue

### 3. Getting Control Token and Starting a Session

#### 3.1 Get control token at the front `/queue/control-token`

- Requirements:
  - Must send `userId`, `robotId`, and `Authorization` header
  - Checks `users.hash_code`; otherwise 401
  - Looks in `robot_queue` for:
    - `robot_id = robotId`
    - `user_id = userId`
    - `status = 'active'`
    - `position = 1`
- If not found, returns 403 “Not at front of queue or not active”
- If found:
  - Reads `control_token` and `activated_at`
  - Returns:
    - `control_token`
    - `expires`: Unix timestamp for `activated_at + 5 minutes`
    - `robotId`

#### 3.2 Request actual control entry `/use_robot`

- Body: `robotId`, `userId`, plus `Authorization` header
- Steps:
  1. Re‑verifies the user and enforces `Explorer Member` restriction
  2. Confirms the user has an `active` entry in `robot_queue` and fetches `control_token` and `activated_at`
  3. Uses Secret Manager key `TELE_OP_CONTROL_URL_ARM_<robotId>` to fetch the robot’s WebSocket control URL
  4. Reads `stream1_ws_url` / `stream2_ws_url` from `robot_status`
  5. Calls `probe_robot_sync` once to send `{"type":"lock_request","token": control_token}` to the robot server (even if “busy”, the flow continues)
  6. Sets `robot_status.is_available = FALSE` to prevent concurrent grabs
  7. If `tele_op_control_history` has no row for this `control_token`, inserts one:
     - `user_id`, `robot_id`, `issued_at`, `expires_at` (activated_at + 5 min), `control_token`
  8. Determines if this is the user’s first Tele-Op:
     - Looks for `point_transactions` entry with `transaction_type = 'first_time_tele_op'` and `points_change = 3000`
     - Used for `isFirstTime` in the response
  9. Encrypts control and stream URLs with AES‑GCM + `URL_AES_KEY` (`encrypt_url`)
  10. Returns:
      - `encrypted_url`: encrypted control WebSocket URL
      - `encrypted_stream1_url` / `encrypted_stream2_url`: encrypted stream URLs
      - `control_token`
      - `expires`: Unix expiration timestamp
      - `isFirstTime`: whether this is the user’s first Tele-Op

#### 3.3 Get decrypt key `/session_url_decrypt_key`

- Body: `userId` + `Authorization`
- Re‑validates the user and membership:
  - Explorer members are forbidden to get this key
- If valid:
  - Reads `ROBOT_URL_AES_KEY_V1` from Secret Manager, returns `key_b64` plus a 15‑minute expiry `exp`
  - The frontend uses this key to decrypt `encrypted_url` and others into real WebSocket URLs

### 4. Session End and Leaving Queue

#### 4.1 User leaves queue `/queue/leave`

- Body: `userId`, `robotId`, `inactive` (whether leaving due to inactivity)
- Validates `hash_code`; otherwise 401
- Delegates to `queue_helper.handle_user_leave_queue`:
  - If user is `active`:
    - Marks `robot_queue.status = 'left'`
    - Fetches `control_token` and calls `process_session_rewards`:
      - If `inactive=True` and duration is very short, zero points
    - Activates the next waiting user if any; otherwise robot stays free
  - If user is `waiting`:
    - Marks as left and reorders positions
  - Always broadcasts the updated queue

#### 4.2 Robot‑side timeout disconnect `/robot/disconnect`

- Called by the robot server when there is **no control signal for ~30 seconds**:
  - Requires internal `INTERNAL_API_TOKEN` in the header; otherwise 401
  - Body contains `robotId`
  - Backend:
    - Looks up the active user for that robot
    - If found:
      - Calls `handle_user_leave_queue(..., inactive=True)` to treat it as an inactive leave
      - Returns `{"status": "ok", "user_id": ...}`
    - If not found:
      - Returns `{"status": "ok", "message": "No active user"}`

#### 4.3 Robot manually freed `/robot/free`

- Called by internal robot logic when it wants to mark itself free:
  - Validates `INTERNAL_API_TOKEN`
  - Updates `robot_status`:
    - `is_available = TRUE`
    - `current_user_id = NULL`
  - Does not manipulate the queue; higher‑level logic decides what to do next

### 5. User Tele-Op History and Completion Status

- **`/user/control_history`**
  - Body: `userId` + `Authorization`
  - After validating the user, queries `tele_op_control_history` for all of their sessions:
    - `robot_id`, `issued_at`, `controlled_end_time`, `controlled_hours`, `reward_points`
  - Aggregates and returns:
    - `sessions`: list of session details
    - `total_controlled_hours`
    - `total_reward_points`

- **`/fetch_tele_op_session_complete_status`**
  - Checks whether a specific `controlToken` session is finished and its result:
    - Body: `userId`, `controlToken` + `Authorization`
    - Validates the user, then queries `tele_op_control_history`
    - If `controlled_status` is NULL: returns `{"status": "not_finished"}`
    - Otherwise returns full row (time fields converted to ISO strings), including:
      - `controlled_status`, `controlled_result` (JSON string), `reward_points`, `controlled_hours`, etc.

### 6. Tele-Op Leaderboards

- **`/tele_op/leaderboard/update`**
  - Internal job used to refresh the global leaderboard:
    - Requires internal token
    - Logic:
      - Ensures index `tele_op_leaderboard_rank_idx` exists
      - Clears the table
      - Aggregates total controlled hours per user from `tele_op_control_history`
      - Joins `users` to get total points, email, multi‑chain wallet addresses
      - Ranks users by:
        - `total_points` DESC
        - then `total_hours` DESC
        - then user_id
      - Inserts rows into `tele_op_leaderboard` with rank starting from 1 (upserts on conflict)

- **`/tele_op/leaderboard`**
  - GET endpoint returning:
    - The top 50 users
    - Optionally a `self` block for a specific `user_id`
  - Email and wallet addresses are masked via `mask_sensitive_value`

- **`/tele_op/monad_leaderboard/update` & `/tele_op/monad_leaderboard`**
  - Same idea as the main leaderboard, but only for users with a non‑empty `monad_receive_address`
  - `wallet_address` is always the Monad address

### 7. Vision Task and Rewards `/vision/dolls_compare`

This endpoint is usually called by the robot server after a doll‑grabbing Tele-Op session to upload multi‑view, multi‑frame images for AI judgment.

1. **Parameters and authentication**
   - Method: POST
   - JSON body:
     - `views`: like `{ "cam1": {"start": [...], "end": [...]}, "cam2": {...} }`
       - Each `start` / `end` can be a single frame or list of base64 images
     - `robotId`: arm1 / arm2 / arm3
     - `controlToken`: the Tele-Op control token
   - Header must include internal `INTERNAL_API_TOKEN`; otherwise 401

2. **View normalization**
   - `_normalize_views`:
     - For each camera’s start/end:
       - Normalizes to lists and trims to at most the first 5 frames
     - Produces:
       - `norm_views`: only first frame per cam (for attempts 1 and 2)
       - `multi_views`: full 1–5 frames per cam (for attempt 3 voting)

3. **Three‑stage strategy**
   - **Attempt 1: first frame pairwise (`gpt-5.1-mini`)**
     - Calls `analyze_compare_pairwise(norm_views, robotId, "gpt-5.1-mini")`
     - Gets START/END counts and movements per camera
     - Uses `evaluate_compare_result` to compute `abnormal` and `success_count`

   - **Attempt 2: second frame pairwise (`gpt-5.1`, if needed)**
     - If attempt 1 is abnormal:
       - Build `second_only` from the second frame in `multi_views`
       - Run `analyze_compare_pairwise(..., "gpt-5.1")` and re‑evaluate

   - **Attempt 3: multi‑frame voting (`gpt-5.1`)**
     - If still abnormal:
       - Calls `build_voted_views_across_five` to combine frames 1–5:
         - Reuses results from attempts 1 and 2 when possible
         - Analyzes remaining frames individually
         - Takes majority vote per side for START and END
       - Builds `voted_result` and re‑evaluates it

4. **Result and reward calculation**
   - If `abnormal == False` and `success_count > 0`:
     - `status = "success"`
     - `reward_inc = 100 * success_count` (100 points per successful object)
   - Otherwise:
     - `status = "failed"`
     - `reward_inc = 0`

5. **Persist to Tele-Op history and points**
   - If `robotId` and `controlToken` are present:
     - Updates `tele_op_control_history`:
       - `controlled_result`: final views JSON
       - `controlled_status`: success / failed
       - `reward_points`: incremented by `reward_inc`
     - If `reward_inc > 0`:
       - Looks up `user_id` for that `control_token`
       - Increments `users.total_points` by `reward_inc`
       - Inserts a `point_transactions` row with `transaction_type = 'dolls_compare_reward'`

6. **Response**
   - Returns:
     - `success: True/False`
     - `model`: final model used
     - `views`: final START/END counts per camera
     - `attempts`: details of each attempt (strategy and intermediate results)

## Real‑Time Queue WebSocket Flow

### Client Socket.IO `connect` event

- When establishing a Socket.IO connection, the client must pass an `auth` object:
  - `robotId`, `token` (user’s `hash_code`), `userId`
- Server‑side `handle_connect(auth)`:
  1. Validates `auth` and required fields
  2. Verifies `hash_code` against the `users` table
  3. On success:
     - Joins the room named by `robotId` (`join_room(robot_id)`)
     - Calls `get_queue_data` for this robot
     - Sends an initial `queue_update` event to this client
     - Sends `connection_success` with:
       - `robotId`, `userId`, `sid`
  4. If any step fails, returns `False` and Socket.IO disconnects the client

### Real‑time queue updates

- After any of the following events, the backend broadcasts an updated `queue_update`:
  - User joins or leaves the queue
  - Background job times out a session and activates the next user
  - Robot disconnect/free events change the active user
  - `activate_next_user_in_queue` completes successfully

The frontend only needs to listen to the `queue_update` event to keep the Tele-Op queue UI in sync in real time.
