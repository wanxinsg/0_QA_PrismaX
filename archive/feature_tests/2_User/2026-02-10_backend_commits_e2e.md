## Commits 影响分析总结（2026-02-10，app-prismax-rp-backend）

### 📊 概览

**功能范围**:  
- **队列管理**（`app_prismax_tele_op_services/queue_helper.py`）  
- **视觉 dolls 对比 / OpenAI 调用**（`app_prismax_tele_op_services/app.py`, `app_prismax_tele_op_services/image_recognitions.py`）  
- **Discord 用户档案绑定 / 解绑 & 多环境回调**（`app_prismax_user_management/app.py`, `app_prismax_user_management/discord_oauth.py`）

**主要相关 Commit（今天）**:  
- `f33b375d675f5357accdb29e1c9c91fcb972d6c4` — added helper to remove duplicate position in robot_queue  
- `3e247d7ab7a71f6f697692b4e10cb5c94e8d8f41` — trying on gpt5 mini instead of gpt 5.2 mini  
- `cfd4bddc741b83a17560a2abb7b8c01a24aaf6ab` — PRIS-117: improve backend env url support for discord  

---

## 1. 机器人队列去重（`queue_helper.normalize_waiting_positions`）

### 核心行为与设计意图

- 在 `activate_next_user_in_queue` 中新增调用 `normalize_waiting_positions(conn, robot_id)`，目的是修正常见的「队列前排 position 重复」问题。  
- `normalize_waiting_positions` 逻辑概览：  
  - 针对指定 `robot_id`、`status='waiting'` 的记录：  
    - 找出 **最小的 position** 以及该 position 上的记录条数 `cnt`。  
    - 若 `cnt <= 1`：不做任何处理直接返回。  
    - 若 `cnt > 1`：认为队列前缀存在 position 重复，进行两步修正：  
      1. 将所有 `position > front_pos` 的 waiting 记录整体 `position += (cnt - 1)`，为去重后的前排预留空间。  
      2. 对当前 `position = front_pos` 且 `status='waiting'` 的记录按 `created_at, id` 做 `ROW_NUMBER()`，将其位置更新为连续区间 `[front_pos, front_pos + cnt - 1]`。  
  - 最后通过 `logging.info` 打印本次规范化的 position 变更情况（包含 robot_id、front_pos、duplicate_count 和 shift_by）。

### 建议的 E2E 测试场景

#### 场景 1：正常激活，确保队列 position 连续且无重复

- **目的**: 验证在正常的队列流转下不会产生新的 position 错乱，并且如果存在重复，能够被自动修正。  
- **前置条件**:  
  - 某个 `robot_id` 下，使用系统已有的「加入队列」 API（例如 Tele-Op 前端调用的接口）让 3 个用户依次入队，形成等待队列。  
  - 确认他们的初始 `position` 依次为 1, 2, 3（可通过队列查询接口或直接查表确认）。  
- **测试步骤**:  
  1. 通过前端或后端 API 让当前 active 用户释放机器人（或等待超时，由调度任务触发 `release_robot_and_activate_next` → `activate_next_user_in_queue`）。  
  2. 通过前端队列查看页面或相应的队列查询 API 获取当前队列信息。  
- **预期结果**:  
  - 新的 active 用户 `position == 1`。  
  - 所有 waiting 用户的 `position` 值为 2, 3, ...，**连续且无重复**。  
  - 若之前存在错误数据（例如 position 重复），日志应出现一次 `Normalized front waiting duplicates...`；在纯干净数据下则可以不出现该日志。

#### 场景 2：模拟 position 错乱（脏数据修复）

- **目的**: 针对已有数据库脏数据场景，验证 `normalize_waiting_positions` 能够正确修复前排重复 position，且保留用户相对先后顺序。  
- **前置条件**:  
  - 在测试环境中，为同一个 `robot_id` 人工构造如下 `robot_queue` 状态（可用 SQL 或脚本）：  
    - 多条 `status='waiting'` 记录，其中至少有两条 `position = 2`，后面还存在 `position = 3, 4, ...`。  
- **测试步骤**:  
  1. 触发一次队列流转（例如释放当前 active 用户，触发 `activate_next_user_in_queue`）。  
  2. 在触发后，通过队列查询接口或直接查 DB，获取该 `robot_id` 下所有 waiting 记录的 `position`。  
- **预期结果**:  
  - 所有 waiting 记录的 `position` 被重排为不重复的连续整数序列。  
  - 最小的 waiting position 仍为 2（active 用户占 position=1），后续为 3, 4, ...。  
  - 原先重复 position=2 的记录，依据 `created_at, id` 的顺序排在位置 2,3，而后面的用户被整体向后平移。  
  - 日志中存在 `Normalized front waiting duplicates...`，且描述的 duplicate_count 与 shift_by 与 DB 结果一致。

#### 场景 3：边界队列（0/1 个 waiting 用户）

- **目的**: 确保在 waiting 队列为空或仅有 1 个用户时，规范化逻辑不会引入异常或多余变更。  
- **前置条件**:  
  - 构造两类队列状态：  
    1. 该 `robot_id` 完全没有 waiting 用户。  
    2. 只有 1 个 waiting 用户，position 任意（通常为 2）。  
- **测试步骤**:  
  1. 触发 `activate_next_user_in_queue` 相关流程（例如释放 active 用户、或手动调用后台任务入口）。  
  2. 检查队列 API/数据库中的等待队列数据。  
- **预期结果**:  
  - 不发生异常（无 5xx / 无 DB 错误）。  
  - 单个 waiting 用户的 position 不出现越界或跳变。  
  - 日志中 **不应该** 打出 `Normalized front waiting duplicates...`（因为 duplicate_count <= 1）。

#### 场景 4：多机器人并发（可选但推荐）

- **目的**: 验证多机器人并发场景下，队列修正逻辑隔离良好，仅影响对应 `robot_id`。  
- **前置条件**:  
  - 测试环境存在至少两个 `robot_id`，每个都拥有 waiting 队列，并可通过 UI 或脚本同时释放当前 active 用户。  
- **测试步骤**:  
  1. 几乎同时触发两个机器人的释放/激活流程（可以通过并发脚本或多终端操作）。  
  2. 查询两个 `robot_id` 各自的 waiting 队列信息。  
- **预期结果**:  
  - 各自队列内的 position 连续且不重复。  
  - 不会出现「A 机器人队列被 B 机器人的操作干扰」的现象。  
  - 日志中针对不同 robot_id 的规范化记录互相独立。

---

## 2. 视觉 dolls 比对与 OpenAI 调用

### 核心改动与行为

- `POST /vision/dolls_compare` 流程中：  
  - **第一次尝试**：对所有相机的首帧进行成对比较，调用 `analyze_compare_pairwise(norm_views, robotId, model_name="gpt-5-mini")`。  
  - 若被判定为 **abnormal**，则进行 **第二次尝试**：对第二帧成对分析，调用 `analyze_compare_pairwise(..., model_name="gpt-5")`。  
  - 若仍然 abnormal，则进行 **第三次尝试**：使用 3–5 帧补充，跨 1–5 帧做投票，最终结果模型名为 `"gpt-5"`，策略标记为 `"vote5"`。  
  - 无论使用哪次结果，最终都会根据 `success_count` 更新 `tele_op_control_history` 表中的 `controlled_result`、`controlled_status` 和 `reward_points`。  
- `image_recognitions.py` 的增强：  
  - 新增统一的 `_log_openai_exception` 辅助函数，对 OpenAI 错误进行结构化记录（包含 model_name、robotId、view_id、status_code、错误类型等）。  
  - `_text_verbosity_for(model_name)` 目前固定返回 `"low"`，所有 Responses API 调用都使用低冗余文本输出。  
  - 加载 OpenAI Key 时若读取为空，会打印 warning 日志，便于排查配置问题。  
  - `analyze_single_image` 与 `analyze_compare_pairwise` 在请求前后增加了耗时与 usage 等信息的日志记录，并在 pairwise 解析失败时 fallback 到单帧分析。

### 建议的 E2E 测试场景

#### 场景 1：Happy Path —— 单机位多帧，三次尝试逻辑可达

- **目的**: 验证模型切换与三段式策略在真实流程中的表现，确保成功路径下 DB 与日志都符合预期。  
- **前置条件**:  
  - 准备一组已知 ground truth 的 `views` 数据，至少包含一个相机（例如 `cam1`），每个 camera 包含 START/END 图像（可以以 base64 形式嵌入请求）。  
  - `INTERNAL_API_TOKEN` 正确配置，OpenAI Key 有效。  
- **测试步骤**:  
  1. 调用 `POST /vision/dolls_compare`，body 包含：  
     - `views`: 符合接口契约的 START/END 镜头结构；  
     - `robotId`: 对应测试机器人 ID；  
     - `controlToken`: 绑定到某次 Tele-Op 控制记录；  
     - Header: `Authorization: Bearer <INTERNAL_API_TOKEN>`。  
  2. 观察 HTTP 响应、后台日志，并查询 `tele_op_control_history` 中与该 `control_token` 对应的数据。  
- **预期结果**:  
  - HTTP 返回 200，响应体中 `status` 字段为 `"success"`（或与实际实现一致的成功状态），且包含合理的 `views` 与 `moved` 结果。  
  - `tele_op_control_history` 中：  
    - `controlled_result` 为 JSON 字符串，内容与最终 `views` 一致；  
    - `controlled_status` 反映成功状态；  
    - `reward_points` 按成功 camera 数量正确累加。  
  - 日志中可以看到：  
    - pairwise 调用开始时记录的视图 key 列表与模型名称（`gpt-5-mini` 或 `gpt-5`）；  
    - pairwise 结束时的总耗时统计与结果摘要。

#### 场景 2：OpenAI Key 缺失

- **目的**: 验证在 OpenAI Key 缺失或 Secret 配置错误时，服务的可观测性和失败行为是否可控。  
- **前置条件**:  
  - 在测试环境中临时移除或遮蔽 OpenAI 的 Secret（例如让 `access_secret_version` 返回空值）。  
- **测试步骤**:  
  1. 再次调用 `POST /vision/dolls_compare`，可使用较小的 `views` 以减少不必要的流量。  
- **预期结果**:  
  - 日志出现 `[image_recognitions] OpenAI key missing; secret_id=...` 的 warning。  
  - 随后在创建 OpenAI client 或发起 responses 请求时触发异常，并被 `_log_openai_exception` 捕获记录（包含错误类型、状态码等）。  
  - `/vision/dolls_compare` 返回明确的错误状态码（当前实现若尚未收敛，建议在后续版本中固化为 5xx），不会长时间 hang 住。

#### 场景 3：OpenAI 异常（429/500 等），fallback 与日志

- **目的**: 在 OpenAI 自身报错时，验证 pairwise 与 fallback 单帧分析的行为，以及日志是否足够支撑定位问题。  
- **前置条件**:  
  - 通过测试 key、代理或 mock 框架，让 `client.responses.create` 对指定请求抛出异常（例如模拟 429 或 500）。  
- **测试步骤**:  
  1. 调用 `/vision/dolls_compare`，确保路径进入 pairwise 分析。  
- **预期结果**:  
  - 日志中存在 `_log_openai_exception("pairwise", ...)` 的记录，字段包括 model_name、robotId、view_id 等关键信息。  
  - 若 pairwise 返回文本不能解析为 JSON，将看到 `pairwise parse failed; fallback single-image` 的 warning。  
  - 系统会尝试使用单帧分析进行兜底，不会导致接口无响应；若仍失败，则返回清晰的错误。  

#### 场景 4：多机位多帧 + vote 策略验证

- **目的**: 验证第三次「投票策略」在多机位多帧场景下的行为。  
- **前置条件**:  
  - 构造 `views` 数据，让至少一个相机在前两轮 pairwise 中被判定为 abnormal，从而必须进入第三轮 vote。  
- **测试步骤**:  
  1. 调用 `/vision/dolls_compare`，并在响应中查看 `attempts` 结构（如果对外返回）或相应的日志。  
- **预期结果**:  
  - `attempts` 中包含 1/2/3 三次记录（或日志显示三阶段调用）。  
  - 最终结果的 `model` 为 `"gpt-5"`，`meta.strategy` 为 `"vote5"`。  
  - DB 中 `controlled_result` 采用的是第三轮 vote 的结果。

---

## 3. Discord 用户档案绑定/解绑 & 多环境回调

### 核心改动与设计意图

- `discord_oauth.load_discord_config` 现在：  
  - 固定 `callback_route = '/auth/discord/callback'`；  
  - `allowed_return_urls` 固定为：  
    - `https://app.prismax.ai/account`  
    - `https://beta-app.prismax.ai/account`  
    - `http://localhost:3000/account`  
    - `http://127.0.0.1:3000/account`  
  - `default_return_url` 为上述列表中的第一个。  
- 在 OAuth state（`DiscordStatePayload`）中新增 `callback_url` 字段：  
  - `build_discord_authorization_url` 会使用前端传入的 `backend_host_url` 通过 `format_callback_url` 生成真实的 callback URL，并同时：  
    - 写入 `redirect_uri` 参数；  
    - 写入 state 的 `cu` 字段（回调 URL），供回调阶段使用。  
  - `parse_discord_state` 会强制要求 `cu` 存在，否则视为 `invalid_state`。  
- `exchange_discord_code_for_token` 现在显式接受 `callback_url` 参数，并作为 `redirect_uri` 传给 Discord 的 token endpoint，确保不同环境下回调 URL 一致。  
- `/auth/discord/initiate` 接口：  
  - 要求请求体或 query 中必须提供：  
    - `return_url`（将来重定向回前端的地址，必须命中 allow-list）；  
    - `backend_host_url`（当前后端基础 URL，用于构造 OAuth callback_url）；  
  - 若缺失上述任一参数，会返回 400，提示「Missing required parameters」。  
  - 成功时，返回可供前端跳转的 `authorization_url`。  
- `/auth/discord/callback` 接口：  
  - 从 `state` 中解析出 `return_url` 与 `callback_url`，并用 `callback_url` 换 access token；  
  - 最终基于 `return_url` 将用户重定向回前端，并携带 `discord_status` / `discord_reason` / `discord_username` 等参数。  
- `/api/user-profile/discord-unlink` 接口（PRIS-117 的一部分）：  
  - 允许用户使用 email 或钱包地址 + Authorization token 发起 Discord 解绑请求，成功后清空 `users` 表中的 Discord 相关字段。

### 建议的 E2E 测试场景

#### 场景 1：生产环境绑定成功（主站 + 正式后端）

- **目的**: 验证在线上环境域名下，initiate → Discord 授权 → callback → 用户资料更新的完整流程。  
- **前置条件**:  
  - 后端部署在正式域名（如 `https://user.prismaxserver.com`）；  
  - 前端在 `https://app.prismax.ai/account`；  
  - Discord 应用配置的 redirect URI 中包含 `https://user.prismaxserver.com/auth/discord/callback`。  
- **测试步骤**:  
  1. 前端调用 `POST /auth/discord/initiate`：  
     - Body: `email` 或 `wallet_address` + `chain` + `return_url="https://app.prismax.ai/account"` + `backend_host_url="https://user.prismaxserver.com"`；  
     - Header: `Authorization: Bearer <用户登录 token>`。  
  2. 后端返回 `authorization_url`，浏览器跳转到该 URL 完成 Discord 授权。  
  3. 授权后，Discord 回调到 `https://user.prismaxserver.com/auth/discord/callback?code=...&state=...`。  
  4. callback 处理结束后，重定向到 `https://app.prismax.ai/account?...`。  
- **预期结果**:  
  - initiate 返回 200，`authorization_url` 中的 `redirect_uri` 为 `https://user.prismaxserver.com/auth/discord/callback`；  
  - `state` 可以被服务端成功解析，包含期望的 `callback_url` 与 `return_url`；  
  - 最终浏览器落在 `https://app.prismax.ai/account`，URL 中有 `discord_status=success`；  
  - DB 中对应用户的 `user_profile_discord_id` / `user_profile_discord_name` 字段被成功写入。

#### 场景 2：本地开发环境绑定

- **目的**: 保证本地前后端联调时，固定 allow-list + `backend_host_url` 模式仍然兼容。  
- **前置条件**:  
  - 本地后端运行在 `http://localhost:8000`；  
  - 前端运行在 `http://localhost:3000/account` 或 `http://127.0.0.1:3000/account`；  
  - Discord 应用 redirect URI 中包含 `http://localhost:8000/auth/discord/callback`。  
- **测试步骤**:  
  1. 前端调用 `POST /auth/discord/initiate`：  
     - `backend_host_url="http://localhost:8000"`；  
     - `return_url="http://localhost:3000/account"`；  
     - 其余参数和线上类似。  
  2. 完成 OAuth 授权后，观察浏览器最终跳转和后端日志。  
- **预期结果**:  
  - initiate 返回的 `authorization_url` 中 `redirect_uri` = `http://localhost:8000/auth/discord/callback`；  
  - 回调阶段能够正常换取 access token 和用户信息，不会因 host 为 `localhost` 而错误升级为 https；  
  - 最终前端落在本地账号页面，URL 中带有 `discord_status=success`。

#### 场景 3：非法/缺失参数（负向用例）

- **目的**: 验证请求参数校验与安全防护是否如预期工作。  
- **用例 A：缺少 backend_host_url**  
  - 步骤：调用 `POST /auth/discord/initiate` 时不传 `backend_host_url` 或传空字符串。  
  - 预期：返回 400，body 中 `success=False` 且错误信息为「Invalid request. Missing required parameters」。  
- **用例 B：return_url 不在 allow-list**  
  - 步骤：传 `return_url="https://malicious.example.com/callback"`。  
  - 预期：后端返回 400，错误信息为「Invalid return URL」，日志中记录 `Rejected Discord return URL`。  
- **用例 C：state 无效 / 被篡改**  
  - 步骤：完成一次正常 initiate 后，手工修改回调 URL 中的 `state` 值再访问。  
  - 预期：  
    - `parse_discord_state` 抛出 `DiscordStateError`；  
    - callback 将用户重定向到 `DISCORD_CONFIG.default_return_url`（`https://app.prismax.ai/account`），并带上 `discord_status=error` 和 `discord_reason`（如 `invalid_state` / `invalid_return_url`）。

#### 场景 4：Discord 解绑 `/api/user-profile/discord-unlink`

- **目的**: 验证用户解绑 Discord 的完整路径，确保数据正确清理且与前端状态一致。  
- **前置条件**:  
  - 已按场景 1 或 2 完成某个用户的 Discord 绑定，DB 中存在该用户的 Discord 字段。  
- **测试步骤**:  
  1. 使用该用户的 email 或钱包地址 + 有效 Authorization token 调用 `POST /api/user-profile/discord-unlink`。  
  2. 刷新前端账户页面或查询 DB。  
- **预期结果**:  
  - 接口返回成功（根据实际实现确认字段，一般包含 `success=True`）；  
  - `users` 表中对应用户的 `user_profile_discord_id` / `user_profile_discord_name` 等字段被清空或置空；  
  - 前端 UI 中账号页从「已绑定 Discord」变为「未绑定」状态。

---

## 总结

- 本次多处改动集中在：**队列一致性修复**、**视觉对比模型与日志可观测性增强**、以及 **Discord OAuth 多环境 URL 管理与用户档案绑定流程**。  
- 上述 E2E 测试用例覆盖了主干成功路径与关键失败/异常路径，建议在每日回归或特性上线前，对高优场景（特别是队列正常流转、Vision dolls Compare 成功路径、本地 + 线上 Discord 绑定流程）至少跑一轮，确保行为稳定可控。

