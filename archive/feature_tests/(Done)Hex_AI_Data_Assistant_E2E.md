# Hex AI Data Assistant 逻辑分析与测试方案（d2aa944..b400816）

## 分析范围

仓库：`app-prismax-rp-backend`  
提交区间：`d2aa94464882f80a44395bf505ffd0db7a3684df` 到 `b400816482fe7d06ee744c8cff85b670900a8c8d`（included）

区间内主要有效功能提交：
- `d2aa944` Improve Hex catalog browsing with pipeline allowlist and upload-time intent.
- `004d212` Add Hex capability requests with grounded task matching and admin raise flow.

备注：`1e6e60b`、`b400816` 为 merge commit，本身不引入独立业务逻辑。

---

## 一句话主线

这段改动把 Hex 从“通用目录检索”升级为“与 Robotic Data 目录强一致 + 时间意图自动识别 + 质量过滤显式触发 + 能力缺口可上报闭环 + 下载额度前置校验”的可控推荐与下载助手。

---

## 核心逻辑拆解（按模块）

## 1) 目录检索范围与 Pipeline 对齐（Allowlist）

涉及文件：
- `app_prismax_hex/hex/agent.py`
- `app_prismax_hex/hex/pipeline_client.py`
- `app_prismax_hex/hex/tools.py`

关键逻辑：
- 每轮对话在可用条件下通过 `GET /data/downloadable-uploads` 拉取用户当前可见目录 episode 集合。
- `count_episodes` 与所有 `add_*` 推荐工具都叠加该集合约束（`pipeline_visible_episode_ids`）。
- 若 pipeline 目录加载失败，记录错误并回退数据库路径，避免硬失败。

业务意义：
- Hex 推荐结果与 Robotic Data 网格可见范围一致，减少“Hex 推荐了但 UI 看不到/不可下载”的错配。

---

## 2) 上传时间意图解析与自动注入

涉及文件：
- `app_prismax_hex/hex/upload_time_filter.py`
- `app_prismax_hex/hex/catalog_intent.py`
- `app_prismax_hex/hex/agent.py`
- `app_prismax_hex/hex/tools.py`

关键逻辑：
- 识别自然语言时间窗口：`yesterday`、`last week`、`last N days`、`recent uploads` 等。
- 转换为统一参数 `upload_since_days`，在 agent 执行工具前自动 merge。
- 会话支持 sticky 窗口：用户后续短回复（如 `yes`/`any`/`sure`）可延续上轮时间窗口。
- 仅当工具结果出现 `filters_applied.upload_since_days` 才允许回复中声称应用了时间过滤，防止“口径漂移”。

业务意义：
- 时间限定检索不依赖 LLM 精准传参，时效性推荐更稳定。

---

## 3) broad browse 与 quality 策略解耦

涉及文件：
- `app_prismax_hex/hex/catalog_intent.py`
- `app_prismax_hex/hex/agent.py`
- `app_prismax_hex/hex/tools.py`

关键逻辑：
- 新增 `add_episodes_from_catalog`，处理“any/no preference/只说时间窗口”的广义采样诉求。
- 质量门槛由 `quality_filter_allowed` 控制，仅用户明确提到质量时允许走质量过滤。
- 对模型工具调用做归一化：
  - 未提质量时，剥离 `min_quality`。
  - `add_episodes_by_quality` 在不满足条件时降级到 `add_episodes_from_catalog`。

业务意义：
- 避免“用户没提质量却隐式加了高质量阈值导致返回 0”的体验问题。

---

## 4) Fast Path 扩展（降低延迟与不稳定性）

涉及文件：
- `app_prismax_hex/hex/agent.py`
- `app_prismax_hex/hex/catalog_intent.py`

关键逻辑：
- 新增两个无需 LLM 的直达路径：
  - 纯时间窗口计数问题 -> 直接 `count_episodes`
  - 纯时间窗口推荐问题 -> 直接 `add_episodes_from_catalog`
- 既减少 token 与模型波动，也保持响应一致性。

业务意义：
- 高频短问答（如“last week 有多少”“给我 10 个昨天上传的”）响应更快、结果更稳。

---

## 5) Capability Requests（Raise to admin）闭环

涉及文件：
- `app_prismax_hex/hex/capability_requests.py`（新增）
- `app_prismax_hex/hex/asgi.py`
- `app_prismax_hex/hex/validation.py`
- `app_prismax_hex/hex/chat_guard.py`
- `app_prismax_hex/hex/store.py`

关键逻辑：
- 服务端根据整轮工具结果识别可上报场景：
  - `unknown_task_phrase`（任务语义匹配过弱）
  - `zero_catalog_match`（有实质过滤但 0 结果）
  - `weak_task_match`（有结果但匹配置信不足）
- agent 通过 SSE 增加 `capability_request_offer` 事件，携带 `pending_token`。
- 用户显式同意后，调用 `POST /v1/sessions/{id}/capability-request` 落库。
- 引入 7 天同意图去重，避免重复噪音工单。
- 新增后台列表接口：`GET /v1/admin/hex-capability-requests`（Bearer 管控）。
- off-topic 问题由 `chat_guard` 拦截并拒答，不进入 capability request 流程。

业务意义：
- 将“找不到/匹配不准”的产品缺口从聊天失败转为可运营、可追踪的改进输入。

---

## 6) 下载策略与额度校验前置

涉及文件：
- `app_prismax_hex/hex/membership.py`（新增）
- `app_prismax_hex/hex/tools.py`
- `app_prismax_hex/hex/pipeline_client.py`
- `app_prismax_data_pipeline/app.py`

关键逻辑：
- `prepare_download_estimate` 输出中加入月额度信息（`monthly_quota`），并根据额度动态调整方法可用性。
- `create_api_package` 在 Hex 侧先校验 membership 和 projected quota，超限直接返回可解释结果。
- pipeline 侧 `POST /data/api-packages` 增加重复 episode 检测，默认返回 409；支持 `allow_already_packaged=true`。
- manifest 默认上限从 1000 收敛到 800（Hex 与 pipeline 口径一致）。

业务意义：
- 用户在“创建 API 包”前就能看到可否执行与失败原因，减少盲试。

---

## 7) 健康检查与可观测性增强

涉及文件：
- `app_prismax_hex/hex/asgi.py`
- `app_prismax_hex/hex/catalog_db.py`

关键逻辑：
- `/health` 返回 DB 探针状态、capability requests 表可用性与权限状态。
- `db-whoami` 增补 capability 表权限字段，便于排查“表已建但不可写”的运维问题。

---

## 端到端流程（高层）

1. 用户输入问题（可能含时间窗口、质量诉求、任务短语）。  
2. agent 先解析意图与上下文（quality gating / upload window / sticky window）。  
3. 满足 fast path 时直接执行工具；否则进入 LLM 工具调用循环。  
4. 工具层统一施加：pipeline allowlist + 上传时间条件 + 下载去重/seed 去重。  
5. 若出现“匹配弱/无结果”，构造 capability offer，等待用户同意再落库。  
6. 涉及下载时，先过额度与重复包校验，再调用 pipeline 创建 API package。  

---

## 测试策略（Test Strategy）

## 目标

- 验证“推荐范围一致性、意图识别准确性、下载约束正确性、能力上报闭环完整性”。
- 覆盖正常路径、边界路径、降级路径、权限与配置异常路径。

## 分层策略

- 单元测试（逻辑函数）
  - `upload_time_filter`：时间短语解析、信息问句豁免、N 天边界值。
  - `catalog_intent`：quality gating、fast path 触发判定、tool call 归一化。
  - `capability_requests`：offer 触发判定、token 生命周期、去重行为。
  - `membership`：额度快照计算、quota 文案、pipeline 402 payload 归一化。

- 集成测试（服务内联动）
  - `agent + tools`：参数自动 merge、生效过滤回写 `filters_applied`。
  - `asgi + session store`：SSE 事件顺序、capability consent 提交、admin 列表接口。
  - `tools + pipeline_client`：allowlist 成功/失败回退、API package 冲突与 quota 响应映射。

- 端到端测试（前后端+真实接口路径）
  - 覆盖用户真实对话与下载动作闭环（见下方 E2E 清单）。

## 关键质量门禁（建议）

- 逻辑正确性：
  - 未明确提质量时，不应出现隐式 `min_quality`。
  - 声称使用时间窗口时，工具结果必须有 `filters_applied.upload_since_days`。
  - 推荐/计数结果不得超出 pipeline allowlist 范围。

- 稳定性：
  - pipeline catalog 拉取失败时可回退，不影响基本查询可用性。
  - capability request 表不存在或无权限时返回可解释错误，不应导致主链路崩溃。

- 安全与权限：
  - admin 列表接口必须校验 `HEX_ADMIN_BEARER`。
  - off-topic 内容不得触发 capability request。

---

## E2E 测试用例（建议执行集）

以下用例默认在已登录用户场景执行；每个用例需记录请求/响应、SSE 事件序列、最终 UI 文案与推荐结果。

| 用例 ID | 用例名称 | 前置条件 | 测试步骤 | 预期结果 |
|---|---|---|---|---|
| E2E-01 | 纯时间窗口计数 Fast Path | 账户目录中有 `last week` 上传数据 | 发送消息：`how many episodes uploaded last week?` | 触发 `count_episodes` fast path，不走 LLM 工具链；回复包含明确计数与时间范围说明；`meta.fast_path=true` 且 `meta.catalog_count_only=true`。 |
| E2E-02 | 纯时间窗口推荐 Fast Path | 目录中有昨日上传数据 | 发送消息：`show me 10 episodes uploaded yesterday` | 触发 `add_episodes_from_catalog` fast path；返回 0~10 条推荐；`filters_applied.upload_since_days=1`；回复不出现质量过滤措辞。 |
| E2E-03 | broad follow-up 继承 sticky 时间窗口 | 已执行 E2E-02 | 下一轮仅发送：`any` | 自动复用上一轮时间窗口；推荐工具继续带 `upload_since_days=1`（可在 `filters_applied` 看到）。 |
| E2E-04 | quality gating 正向 | 目录中存在不同质量分布数据 | 发送：`recommend 20 episodes with quality >= 90` | 允许走 quality 路径（`add_episodes_by_quality` 或等价质控路径）；返回中包含 `filters_applied.min_quality=90`。 |
| E2E-05 | quality gating 反向（不应误加质量） | 目录中低质量数据存在 | 发送：`recommend 20 episodes from last week` | 不应隐式出现 `min_quality`；走 broad/time-only 逻辑，结果仅受时间窗口与目录可见性限制。 |
| E2E-06 | allowlist 强一致性验证 | 准备一批 DB 中存在但 `downloadable-uploads` 不可见的 episode | 发起 count 与 add（task/machine/text 多种过滤） | 结果均不包含不可见 episode；`filters_applied.pipeline_catalog` 存在且 visible count 正确。 |
| E2E-07 | pipeline catalog 加载失败回退 | 模拟 pipeline endpoint 超时或 5xx | 发起普通推荐请求 | 主流程不中断，可回退到 DB 查询；响应可见 pipeline load warning 或等价提示字段。 |
| E2E-08 | unknown task phrase -> capability offer -> 用户同意 | 输入目录中不存在的任务短语 | 发送：`find episodes for <unknown phrase>`；收到 `capability_request_offer` 后调用 consent 接口并传 `approve=true` | offer 事件返回 `pending_token`；consent 接口返回 `ok=true` 且成功写入 capability request。 |
| E2E-09 | weak task match -> capability offer | 准备一个与现有 task 语义接近但不完全匹配的短语 | 发起查询并观察回复与事件 | 回复提示“可能不是你想要的任务”；同时出现可上报 offer（reason 为 weak match 语义）。 |
| E2E-10 | capability token 过期/无效 | 使用过期 token 或随机 token | 调用 `POST /v1/sessions/{id}/capability-request` | 返回 404，错误语义为 `expired or not found`。 |
| E2E-11 | admin 列表权限 | 分别准备设置/不设置 `HEX_ADMIN_BEARER` 环境 | 分别以正确/错误/缺失 Bearer 调用 admin 列表接口 | 仅正确 Bearer 可访问；未配置时返回 503；鉴权失败返回 401。 |
| E2E-12 | `prepare_download_estimate` 额度信息 | 用户有 membership，且账户接近额度上限 | 调用估算（seed 或 `episode_ids`） | 返回 `monthly_quota` 快照；API package 方法可用性与 quota 状态一致。 |
| E2E-13 | `create_api_package` 重复 episode 冲突 | 目标 episode 已在该用户历史 package 内 | 不带 `allow_already_packaged` 创建 package | 返回冲突信息（重复 episode 列表或等价冲突标识）；UI/回复可引导“允许重复打包”分支。 |
| E2E-14 | `create_api_package` quota 超限 | 选择 episode 数使 projected 超过 monthly limit | 调用创建 package | 返回 `quota_exceeded=true` 与 quota 详情；不会创建成功 package。 |
| E2E-15 | off-topic 拦截 | 无 | 发送明显非数据目录问题（旅游/财经/写邮件等） | 返回固定拒答；不触发 catalog 工具链与 capability request。 |

---

## 回归关注点（建议）

- 旧前端是否正确消费新增 SSE 事件 `capability_request_offer`。
- 旧调用方对 `get_episodes_by_id` 参数由必填改可选后的兼容性。
- `DATA_MANIFEST_DOWNLOAD_MAX_FILES` 默认值变更（1000 -> 800）对历史脚本与文档的一致性。
- pipeline 慢响应时，agent 每轮都拉目录可能带来时延上升，需观察超时参数与缓存策略。

---

## 结论

该区间是一次“正确性优先 + 体验兜底 + 运营闭环”导向的系统性增强：
- 推荐结果更可信（可见性强一致）。
- 时间与质量意图更可控（减少误过滤）。
- 下载路径更可解释（额度与冲突前置）。
- 无结果场景不再只是失败，而是可追踪的改进输入（Raise to admin）。

