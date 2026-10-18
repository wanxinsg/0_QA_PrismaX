**Prisma(x)**

后端设计 — 定价与访问控制

*内部文档 | 2026 年 5 月*

## 1. 订阅档位

三个档位用于控制用户可访问的数据范围，以及用户可以如何下载数据。定价按 episode 数量计量。小时数仅作为内部容量规划单位使用，绝不向用户展示。

| 维度 | Discover | Researcher | Enterprise |
|---|---:|---:|---:|
| 月付价格 | $9 | $89 | $899 |
| 年付价格 | $7/月 | $71/月 | $719/月 |
| 每月 Episodes | 100 | 1,500 | 18,000 |
| 每日上限 | 30 分钟 | 3 小时 | 20 小时（软限制） |
| 数据池 | 20% 数据库 | 60% 数据库 | 100% |
| 最高分辨率 | 640x480 @ 30fps | 1080p @ 60fps | 完整原始数据 |
| 最大任务长度 | <= 2 分钟 | <= 3 分钟 | 所有长度 |
| 机械臂类型 | 4 种 | 8 种 | 12+ 全部类型 |
| 浏览器下载 | ✓ | ✓ | ✓ |
| API 访问 | ✗ | ✓ | ✓ |
| JSON 下载 | ✗ | ✗ | ✓ |
| 新发布窗口 | T+60 天 | T+30 天 | T+0（第 1 天） |

*⚠️ 小时数仅用于内部容量规划和每日上限执行。用户只看到 episodes。*

## 2. 数据池定义

数据库中的每个 episode 都且仅属于一个数据池档位。数据池归属在摄入时设置，并作为元数据字段存储。访问控制在查询时执行；超出用户所属数据池范围的请求返回 HTTP 403，并展示通用的“当前计划不可用”消息。

### 2.1 Discover 数据池 — 20%

- 任务类型：常见家庭操作、基础 pick-and-place，仅包含高频场景
- Episode 时长：<= 2 分钟（摄入时通过 `duration_seconds` 元数据字段强制执行）
- 机械臂类型：4 种标准类型，Discover Tok2、Agixl Piper、I2st YAM、RealMan RL360
- 分辨率：最高 640x480 @ 30fps
- 发布延迟：自 Enterprise 发布日期起 T+60 天

### 2.2 Researcher 数据池 — 60%

- 包含所有 Discover 数据池内容
- Episode 时长：<= 3 分钟
- 机械臂类型：8 种（Discover 4 种 + Universal UR5、Universal UR10、Franka Panda、UFACTORY xArm）
- 分辨率：最高 1080p @ 60fps
- 发布延迟：自 Enterprise 发布日期起 T+30 天

### 2.3 Enterprise 数据池 — 100%

- 完整数据库，包含所有机械臂类型、所有任务长度、所有分辨率，包括未处理的原始数据
- 包含边缘案例、失败模式 episodes、自定义场景
- 完整标注元数据；较低档位只提供精简元数据
- 新数据在 T+0 发布，比 Pro 提前 30 天，比 Discover 提前 60 天

### 2.4 数据池执行 Schema

| 字段 | 类型 | 示例 | 说明 |
|---|---|---|---|
| `pool_tier` | ENUM | `'starter'` | `starter` \| `pro` \| `enterprise` |
| `published_at` | TIMESTAMP | `2026-05-01` | Enterprise 发布日期（T+0） |
| `duration_seconds` | INT | `142` | 用于数据池归属和任务长度闸门 |
| `arm_type` | VARCHAR | `'ur5'` | 根据档位机械臂 allowlist 校验 |
| `resolution_tier` | ENUM | `'standard'` | `standard` \| `hd` \| `raw` |

## 3. 下载请求决策流程

每个下载请求按以下顺序执行校验。首次失败会立即返回。所有失败都会带 reason code 记录日志，用于分析。

| 步骤 | 校验 | 失败响应 |
|---:|---|---|
| 1 | 有效的 session token 或 API key | `401 UNAUTHORIZED` |
| 2 | 有效订阅，未过期且未取消 | `402 PAYMENT_REQUIRED` |
| 3 | Episode(s) 位于档位数据池范围内 | `403 POOL_RESTRICTED` |
| 4 | 分辨率不超过档位上限 | `403 RESOLUTION_RESTRICTED` |
| 5 | Episode 时长不超过档位上限 | `403 TASK_LENGTH_RESTRICTED` |
| 6 | 下载方式对该档位开放 | `403 METHOD_RESTRICTED` |
| 7 | 批量大小不超过下载方式限制 | `400 BATCH_LIMIT_EXCEEDED` |
| 8 | 未超过每日上限 | `429 DAILY_CAP`（Discover：硬阻断；Researcher：入队；Enterprise：限速） |
| 9 | 每月 episode 配额未耗尽 | `429 MONTHLY_QUOTA_EXCEEDED` |
| 10 | API 频率限制（仅 Enterprise API） | `429 RATE_LIMIT`，带 `Retry-After` |
| 11 | 通过，扣减计数器并启动下载 | `200 OK` |

## 4. 每日上限与配额执行

### 4.1 每日上限行为

每日上限按已消耗的数据分钟数执行，而不是按 episodes 执行。这样可以在不受 episode 长度变化影响的情况下做细粒度控制。上限每日 00:00 UTC 重置。

| 档位 | 每日上限 | 超出上限后的行为 | 用户消息 |
|---|---|---|---|
| Discover | 30 分钟 | 硬阻断，立即返回 HTTP 429 | 通用限制消息 + 升级 CTA |
| Researcher | 3 小时 | 软排队，HTTP 202，请求最多排队 2 小时 | “即将处理”，不展示时间 |
| Enterprise | 20 小时（软限制） | 超出后限速到 1 ep/min，HTTP 202 | 展示队列位置 |

*⚠️ 具体上限值（30 分钟、3 小时、20 小时）绝不出现在用户可见文案中。只能使用通用消息。*

### 4.2 Redis 计数器结构

- Key pattern：`cap:{account_id}:daily`，写入时将 TTL 设置为距下一个 00:00 UTC 的秒数
- Key pattern：`quota:{account_id}:monthly`，TTL 设置为距账单周年日的秒数
- 计数递增发生在下载完成时，而不是请求发起时
- 部分下载（已取消）按已传输字节数成比例计入
- 加购小时数单独存储：`addon:{account_id}`，优先于每月配额消耗

### 4.3 每月配额耗尽

- Discover / Researcher：阻断所有下载，直到下一个账单周期或购买 add-on
- Enterprise：限速到 1 episode/min，并向账户发送邮件，不阻断
- 每月计数器在账单周年日重置，而不是自然月重置

## 5. 下载方式执行

| 方式 | Discover | Researcher | Enterprise |
|---|---|---|---|
| Browser | <=10 videos/batch | <=10 videos/batch | <=10 videos/batch |
| API | HTTP 403 | 不限量，有频率限制 | 不限量，有频率限制 |
| JSON manifest | HTTP 403 | HTTP 403 | 每次导出 <=800 episodes |

- 浏览器批量限制在服务端执行，独立于 UI；没有有效档位的直接 API 调用仍然返回 403
- API 访问需要绑定到 `account_id` 的 key。Key 以 bcrypt hash 存储；明文只在创建时返回一次

### 5.1 API 频率限制（Pro 和 Enterprise）

| 限制 | Researcher | Enterprise |
|---|---:|---:|
| 每分钟请求数 | 60 rpm | 60 rpm |
| 每次请求 episodes | 最高 100 | 最高 100 |
| 并发下载数 | 最高 5 | 最高 10 |
| 频率限制响应头 | `X-RateLimit-Limit`、`-Remaining`、`-Reset` | `X-RateLimit-Limit`、`-Remaining`、`-Reset` |

## 6. Enterprise 留存机制

以下是用于降低“批量下载后流失”行为的运营策略。不会向用户披露。

### 6.1 新鲜度模型 — 错峰发布

- 新数据集在 T+0 发布给 Enterprise
- Pro 访问权限在 Enterprise 发布日期后 T+30 天开放
- Discover 访问权限在 Enterprise 发布日期后 T+60 天开放
- `publication_date` 按 episode 存储在 `episodes` 表中，并在查询时评估
- 取消订阅会立即移除 T+0 访问权限，对未发布数据不提供宽限期

### 6.2 软每日上限 — 防止夜间批量抓取

- 500h/month 在 20h/day 最大值下，至少需要 25 天才能耗尽月度额度
- 超过上限后：以 1 episode/min 入队，而不是拒绝。返回 HTTP 202 并附队列位置
- 防止单次夜间流水线运行在一个 session 内下载完整数据库

### 6.3 数据水印

- 所有下载的 MP4 和 MCAP 文件都嵌入与 `account_id` 绑定的不可感知水印
- 水印可在等价质量设置的重新编码后保留
- 重新分发带水印数据违反 ToS，会触发账户终止
- 内部水印检测服务可用于违规调查

## 7. 已批准的用户可见文案

以下是限制和拒绝状态唯一允许使用的文案。具体阈值、数据池百分比和执行逻辑绝不能出现在用户可见字符串中。

| 状态 | 已批准文案 |
|---|---|
| 未订阅 | Download is available for subscribers. Choose a plan to continue. |
| 每日上限 — Discover | You've reached your usage limit for today. Your selection is saved. |
| 每日上限 — Pro queue | Your download is queued and will begin shortly. |
| 每月配额耗尽 | You've used your monthly data allocation. |
| 数据池限制 | This content is not available on your current plan. |
| 下载方式被阻断 | This download method is available on higher plans. |
| 批量大小超限 | Please select up to [n] videos at a time for browser download. |

*⚠️ 绝不要在用户可见消息中包含诸如“30 minutes”、“3 hours”、“20%”或队列等待时间等具体值。*

## 8. 错误码

| HTTP 状态 | Code | 含义 |
|---:|---|---|
| 401 | `UNAUTHORIZED` | Session token / API key 无效或缺失 |
| 402 | `PAYMENT_REQUIRED` | 没有有效订阅 |
| 403 | `POOL_RESTRICTED` | Episode 超出档位数据池 |
| 403 | `METHOD_RESTRICTED` | 下载方式不适用于该档位 |
| 403 | `RESOLUTION_RESTRICTED` | 分辨率超过档位上限 |
| 403 | `TASK_LENGTH_RESTRICTED` | Episode 时长超过档位上限 |
| 400 | `BATCH_LIMIT_EXCEEDED` | Episode 数量超过下载方式的批量限制 |
| 429 | `DAILY_CAP` | 已达到每日上限（Discover 硬阻断） |
| 429 | `MONTHLY_QUOTA_EXCEEDED` | 每月 episode 配额已耗尽 |
| 429 | `RATE_LIMIT` | 命中 API 频率限制，包含 `Retry-After` 响应头 |
| 202 | `QUEUED` | 请求已进入队列（Pro 软上限 / Enterprise 限速） |

## 9. 分析事件

| Event | 关键字段 |
|---|---|
| `download.initiated` | `account_id`, `tier`, `method`, `episode_count`, `estimated_minutes` |
| `download.completed` | `account_id`, `tier`, `actual_minutes`, `resolution`, `arm_types`, `pool` |
| `download.blocked` | `account_id`, `tier`, `block_reason`（error code）, `upgrade_shown` |
| `paywall.shown` | `account_id`, `trigger_type`, `current_tier` |
| `paywall.converted` | `account_id`, `from_tier`, `to_tier`, `trigger_type`, `revenue` |
| `quota.cap_hit` | `account_id`, `tier`, `cap_type`（`daily` \| `monthly`）, `action_taken`（`block` \| `queue` \| `throttle`） |
