## CHAIN APIs 测试用例（XMind 风格，新增 monad 链）

- 总览
  - 新增链：monad（与现有 `solana` / `ethereum` / `base` 并列）
  - 覆盖目标：确保 `monad` 在所有含 `chain` 的接口中均被正确识别、验证、路由与存储
  - 依赖前置：
    - 后端 `valid_chains` 增加 `monad`；
    - 针对 `monad` 的地址列映射（如 `monad_receive_address`）与交易哈希列（如 `monad_transaction_hash`）；
    - RPC/区块链验证（若 `monad` 走 EVM 流程，则须配置 `EVM_RPC_ENDPOINTS[\"monad\"]` 与验证逻辑）。
  - 兼容性与归一化：大小写（`MoNaD`）、首尾空格（` monad `）应归一化为小写 `monad`

- POST /auth/twitter/initiate（monad）
  - 成功路径
    - email + token + chain=monad + 合法 return_url → 200，success=true，返回 authorization_url
    - wallet_address + token + chain=monad → 200，success=true，返回 authorization_url
    - 链值归一化：`MoNaD` / ` monad ` → 等价于 `monad`
  - 失败路径
    - 无 Authorization → 401
    - 缺少 email 与 wallet_address → 400
    - 后端未更新 `valid_chains` 包含 monad → 400（Invalid chain）

- GET /api/get-users（monad）
  - 成功路径
    - email + Bearer token + recaptcha_token + chain=monad → 200，返回 email 用户数据
    - wallet_address + recaptcha_token + chain=monad → 200，返回 monad 钱包用户数据（自动建号前的余额/有效性校验通过）
    - email + wallet_address + chain=monad → 绑定/校正关系后返回 200
  - 失败路径
    - 未更新 `valid_chains` → 400（Invalid chain）
    - 未配置 recaptcha_token（非测试环境）→ 400 / 403
    - email 查询但无 Authorization → 401
    - 钱包不存在或余额校验失败（若实现了 monad 链余额校验）→ 500（不应 5xx，如实现不同以实际返回为准）
  - 数据列映射
    - 验证地址列：若实现 `monad_receive_address`，则查询/插入/绑定应走该列
    - 若 `monad` 复用 EVM 地址列策略，确认列名与映射一致性

- POST /api/disconnect-wallet-from-email（monad）
  - 成功路径
    - email + wallet_address + chain=monad + Bearer token → 200，解绑成功
    - 解绑后：`email` 侧 `linked_wallet_address=null`；`wallet(monad)` 侧 `linked_email=null`
  - 失败路径
    - 无 Authorization → 401
    - 缺少 email 或 wallet_address → 400
    - 链与列映射未更新（后端未支持 monad 列）→ 200/错误消息或 4xx（不应 5xx），不产生脏数据
  - 幂等
    - 已解绑重复调用 → 200（不抛异常）

- POST /api/update-user-info（monad）
  - 成功路径
    - email + token + chain=monad → 200，字段（user_name/telegram_id/phone_number/user_profile_email/twitter_*）更新成功
    - wallet_address + token + chain=monad → 200，基于 monad 地址列定位并更新
  - 失败路径
    - 无 Authorization → 401
    - 缺少 email 与 wallet_address → 400
    - 未更新 `valid_chains` → 400（Invalid chain）
  - 一致性
    - `user_profile_email` 小写归一化
    - 未提供字段不被覆盖

- POST /api/daily-login-points（monad）
  - 成功路径
    - email 或 wallet_address + chain=monad → 200，首次登录 is_first_time=true；每日积分 +1
    - 不提供 `user_local_date` → 服务端 UTC±1 校验通过
  - 失败路径
    - 缺少 email 与 wallet_address → 400
    - 未更新 `valid_chains` → 400（Invalid chain）
    - 日期格式不合法 / 超出 UTC±1 → 400，提示当前 UTC 日期
    - 用户不存在 → 404

- GET /api/get-point-transactions（monad）
  - 成功路径
    - email 或 wallet_address + chain=monad → 200，返回交易列表与 `total_points`
    - 列表按 `created_at_utc` DESC；当日聚合与 Dashboard 逻辑一致
  - 失败路径
    - 未更新 `valid_chains` → 400（Invalid chain）
    - 用户不存在 → 404
  - 归一化
    - `MoNaD` / ` monad ` → 等价于 `monad`

- POST /api/record-crypto-payment（monad）
  - 成功路径（EVM 兼容假设）
    - wallet_address + amount_total + user_id + currency + chain=monad + transaction_hash → 200，写入 `monad_transaction_hash`（或共用 EVM 列策略）
    - 校验通过后可触发会员升级（依据金额与当前等级）
  - 失败路径
    - 缺少 wallet_address / amount_total / user_id → 400
    - 未更新 `valid_chains` → 400（Invalid chain）
    - 交易哈希重复（跨列去重应包含 `monad_transaction_hash`）→ 409
    - 交易验证失败（哈希无效 / 接收地址不匹配 / RPC 无法访问）→ 409
  - 一致性与日志
    - `payment_chain=monad`，日志含 chain 与 hash
    - 幂等性：重复上报同哈希固定返回 409，数据库不重复
  - 配置依赖
    - 若 monad 为 EVM 兼容：`EVM_RPC_ENDPOINTS[\"monad\"]`、校验函数（可复用 EVM 验证流程或新增 `verify_monad_payment`）

- 跨链/跨接口回归（引入 monad 后的整体稳定性）
  - 所有接口 `valid_chains` 包含 monad，`Invalid chain` 错误不再出现
  - 地址与交易哈希列映射覆盖 monad（读/写/去重/查询）
  - 链参数归一化测试：`monad` 与变体一致
  - 绑定/解绑/查询/更新：solana/ethereum/base/monad 四链互不干扰
  - 文档一致性：`CHAIN_APIs.md` 中链列表、示例、返回字段同步包含 monad

- 测试数据与环境准备（monad）
  - 钱包地址：准备 1 个有效 monad 地址
  - 用户：可用 email + token
  - 交易：有效/无效 monad 交易哈希（若需真实验证，配置测试网与接收地址）
  - RPC：配置 `EVM_RPC_ENDPOINTS[\"monad\"]`；网络连通性与速率限制观测


