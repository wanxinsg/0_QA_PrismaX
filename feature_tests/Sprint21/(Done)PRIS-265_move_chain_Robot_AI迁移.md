# PRIS-265 / Move Chain Selection Icon + Robot Slug 迁移 — 全栈逻辑与测试分析

> 仓库：`app-prismax-rp`（前端） · `app-prismax-rp-backend`（后端） · `roarm-m3-web`（Robot Server）

---

## 1) 分析范围

本次 PRIS-265 及相关同期改动涉及 **7 个 commit、3 个仓库**，按主题分为四条主线：

| 主线 | 仓库 | Commit | 作者 | 日期 | 说明 |
|------|------|--------|------|------|------|
| **A. 链选择 UI 迁移** | `app-prismax-rp` | `e648b32` | lanmanc | 2026-06-23 | updated chain selection + robot id for ai |
| **B. Robot Slug / Vision（前端）** | `app-prismax-rp` | `e648b32` | lanmanc | 2026-06-23 | TeleOp Session Complete Modal 改 slug 判断 |
| **B. Robot Slug / Vision（后端）** | `app-prismax-rp-backend` | `0c028d1` | lanmanc | 2026-06-23 | fixing ai image based on robot id issue |
| **B. Robot Slug / Vision（Robot）** | `roarm-m3-web` | `2160a6c` | lanmanc | 2026-06-23 | fixing roarm_server ai issue |
| **C. QA Review Hub 预览提速** | `app-prismax-rp-backend` | `228f673` | lanmanc | 2026-06-23 | improving speed |
| **C. QA Review Hub 预览提速** | `app-prismax-rp-backend` | `43f796c` | lanmanc | 2026-06-23 | fixing loading issue |
| **D. 推广邮件资源** | `app-prismax-rp` | `3d3ce9e` | Aparna | 2026-06-24 | promo-email: add verify qa banner image |

### 部署矩阵（必须对齐）

| 能力 bundle | 必须同时部署的 commit | 只部署一部分的风险 |
|-------------|----------------------|-------------------|
| **Connect 链选择** | FE `e648b32` | 仅后端变更无影响；缺 FE 则仍为旧 Header 链选择器 |
| **Review Hub 预览** | BE `228f673` + `43f796c` | 仅 228f673 → 预览 URL 404 / loading 卡死 |
| **TeleOp Vision 全链路** | FE `e648b32` + BE `0c028d1` + Robot `2160a6c` | 见 §7 风险 R11–R14 |
| **邮件 Banner** | FE `3d3ce9e` | 邮件图片 404 |

---

## 2) 一句话主线

- **PRIS-265（产品）**：链选择从 Header 下沉到 Connect Modal，与钱包连接合并为同一流程。
- **Robot Slug 迁移（技术）**：全栈以 `robot_slug`（尤其 `arena-arm`）驱动 TeleOp 弹窗、Vision 开关、抓帧与 AI 图像 Prompt，淘汰 `arm1/arm4/arm5` 及本地 `ROBOT_ID` 硬编码。
- **Review Hub 提速（性能）**：预览接口从 GCS 全量列举改为 DB metadata 直拼 URL，`43f796c` 修复路径映射导致的加载失败。

---

## 3) 系统级逻辑总图

```
┌─────────────────────────────────────────────────────────────────────────┐
│  A. Connect / 链选择（FE e648b32）                                        │
│  Header 移除链图标 → ConnectModal 展开 wallet → Network + Wallet 分区    │
│  handleChainSelect → localStorage.selectedChain → walletRows 联动        │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  B. TeleOp Robot Slug + Vision（FE + BE + Robot，四段闭环）               │
│                                                                          │
│  FE e648b32：会话结束 → robotSlug==='arena-arm' → SessionCompleteModal   │
│       ↓ 用户入队控制                                                      │
│  BE 0c028d1：use_robot → robot_slug==='arena-arm' → visionEnabled        │
│       ↓ lock_request WebSocket                                           │
│  Robot 2160a6c：g_vision_enabled → 抓 start/end 帧 → dolls_compare POST  │
│       ↓ POST /vision/dolls_compare                                       │
│  BE 0c028d1：image_recognitions → VISION_PROMPT（Arena 亚克力盒场景）     │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  C. QA Review Hub 预览（BE 228f673 + 43f796c）                          │
│  DataReviewHub.js → POST /data/qa/reviewable-uploads/previews            │
│  DB metadata 快路径 → _derive_preview_video_object_path → CDN/signed URL  │
│  metadata 缺失 / 路径无效 → 回退 GCS list_blobs                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│  D. 推广邮件 Banner（FE 3d3ce9e）                                        │
│  public/email-verify-qa-promo-banner.jpeg → 邮件 HTML 绝对 URL 引用       │
└─────────────────────────────────────────────────────────────────────────┘
```

### TeleOp Vision 端到端时序（改后）

```
1. 用户排到 arena-arm → Backend use_robot()
2. Backend → Robot WS: lock_request { token, visionEnabled: true }
3. Robot: g_vision_enabled = True → 返回 { status: "ok" }
4. 前端建立控制 WS → handle_control_connection()
5. g_vision_enabled && 未抓过该 token → _capture_session_start_views()
   → 从 IMAGE_RECOGNITION_CAM 端口抓 5 帧 start → g_snapshot_token = token
6. 用户操作机器人...
7. 会话结束 → cleanup_user_session() → _capture_session_end_and_post()
   → sleep 2s → 抓 5 帧 end → POST /vision/dolls_compare
8. Backend analyze_compare_pairwise() + VISION_PROMPT
9. 前端 arena-arm 非首次用户 → TeleopSessionCompleteModal

Training / Private：visionEnabled=false → 步骤 5、7 全部跳过（无抓帧、无 AI POST）
```

---

## 4) 前端逻辑 — `app-prismax-rp`

### 4.1 链选择 UI 迁移（`e648b32` · PRIS-265 核心）

#### 改动前

- `ConnectWalletHeader` 顶部有独立链选择器（图标 + 下拉）
- 状态 `isChainDropdownOpen`；需处理点击外部关闭、与钱包面板互斥

#### 改动后

- Header **不再显示**链选择图标/下拉
- 链选择移入 `ConnectModal`，仅在展开 **「Connect a wallet」** 后可见
- UI 分区：**Network**（链）→ 分隔线 → **Wallet**（钱包）

#### 数据流

```
ConnectWalletHeader
  ├── CHAIN_OPTIONS（key / label / icon）
  ├── handleChainSelect(chain)
  │     ├── email + wallet 已登录 → warning，禁止切换
  │     └── 否则 setSelectedChain + localStorage('selectedChain')
  └── ConnectModal
        ├── chainOptions={CHAIN_OPTIONS}
        ├── onChainSelect={handleChainSelect}
        └── selectedChain → walletRows（Solana 才显示 WalletConnect）
```

#### 文件级变更

| 文件 | 变更 |
|------|------|
| `ConnectWalletHeader.js` | 删除 Header 链选择器、`isChainDropdownOpen`、document click 监听；`CHAIN_OPTIONS` 增加 `icon`；向 Modal 传 `chainOptions` / `onChainSelect` |
| `ConnectModal.js` | 新增 Network 区 pill 按钮链选择 |
| `ConnectModal.module.css` | 新增 chain pill 样式；删除未用 `.footer` |
| `TeleOp.js` | Session Complete 判断改 slug（见 §4.2） |

#### 链与钱包联动

| 链 key | label | 钱包列表 |
|--------|-------|----------|
| `solana` | Solana | Phantom / MetaMask / OKX / Coinbase / **WalletConnect** |
| `ethereum` | Ethereum | Phantom / MetaMask / OKX / Coinbase |
| `base` | Base | Phantom / MetaMask / OKX / Coinbase |
| `monad` | Monad | Phantom / MetaMask / OKX / Coinbase |

### 4.2 TeleOp Session Complete Modal（`e648b32` · 同 commit 附带）

| | 改动前 | 改动后 |
|---|--------|--------|
| 判断方式 | 硬编码 `robotId` | `robotDataDict[robotId].robotSlug` |
| 条件 | `robotId !== 'arm1' && !== 'arm4' && !== 'arm5'` | `robotSlug === 'arena-arm'` |
| 语义 | 排除训练臂，其余弹窗 | **仅** arena 臂弹窗 |

| robotSlug | 类型 | 旧逻辑弹窗 | 新逻辑弹窗 |
|-----------|------|-----------|-----------|
| `training-arm-black` / `training-arm-gold` | 训练臂 | 否 | 否 |
| `arena-arm` | 竞技场臂 | 是 | 是 |
| `private-arm` | VIP / 私有臂 | 是（若非 arm1/4/5） | **否** |

**触发时机（不变）：** 会话正常结束 → 非首次用户 → 非 session 过期 → 满足 slug → `TeleopSessionCompleteModal`。

### 4.3 推广邮件 Banner（`3d3ce9e`）

- 新增 `public/email-verify-qa-promo-banner.jpeg`（约 513 KB）
- 前端代码无引用；CRA `public/` 映射站点根路径
- 邮件 HTML 引用：`https://<domain>/email-verify-qa-promo-banner.jpeg`

---

## 5) 后端逻辑 — `app-prismax-rp-backend`

### 5.1 QA Review Hub 预览提速（`228f673` + `43f796c`）

#### 背景

前端 `DataReviewHub.js` 批量调用：

```
POST /data/qa/reviewable-uploads/previews
Authorization: Bearer <gatewayToken>
Body: { "uploads": [upload_id, ...] }   // 最多 200
```

**改动前：** 每个 upload 调用 `_list_public_derived_media()` → GCS `list_blobs` 扫描整个 derived 文件夹，列表页延迟高。

#### `228f673` — 快路径

1. SQL：每个 `upload_id` 取 `MIN(episode_id)` 且 `status = DERIVED_READY`
2. 批量查 `data_api_episode_file_metadata`
3. `_select_preview_video_metadata()`：选预览视频，优先级 `env` > `left` > `right`
4. `_build_derived_object_url()`：已知 object path 直接生成 CDN / signed URL
5. 预览图：直接拼 `{derived_folder}preview.jpg`
6. metadata 缺失 → 回退 `_list_public_derived_media()`

**快路径响应字段（`previews[]` 每个元素）：**

| 字段 | 说明 |
|------|------|
| `upload_id` | 请求的 upload ID（必有） |
| `preview_video_url` | 预览视频 URL；无资源时为 `null` |
| `preview_video_url_type` | `cdn` 或 `signed_url`（仅快路径） |
| `preview_image_url` | 预览图 URL（`preview.jpg`）；无资源时为 `null` |
| `preview_image_url_type` | `cdn` 或 `signed_url`（仅快路径） |

```json
{
  "success": true,
  "previews": [
    {
      "upload_id": 123,
      "preview_video_url": "https://...",
      "preview_video_url_type": "cdn",
      "preview_image_url": "https://...",
      "preview_image_url_type": "signed_url"
    }
  ]
}
```

> **回退路径**（无 metadata）：可能缺少 `preview_video_url_type`；**无 episode**：`preview_video_url` / `preview_image_url` 均为 `null`。

#### `43f796c` — 路径修复

`228f673` 直接用 metadata.`object_path` 可能指向 raw 或非 derived 前缀 → 预览 404 / 前端 loading 卡死。

新增 `_derive_preview_video_object_path()`：

```
derived_folder = derived_video_folder_path 或 raw/ → derived/

if object_path.startswith(derived_folder):  return object_path
else: return derived_folder + relative_path 去首段后的文件名
```

无法解析合法 derived path 时回退 GCS list。

### 5.2 TeleOp Vision + AI Prompt（`0c028d1`）

#### `use_robot()` — 按 slug 开启 Vision

```python
SELECT stream1_ws_url, stream2_ws_url, robot_slug FROM robot_status ...
vision_enabled = robot_slug == "arena-arm"

probe_robot_sync(ws_url, control_token, vision_enabled=vision_enabled)
# WebSocket: { "type": "lock_request", "token": "...", "visionEnabled": true|false }
```

| robot_slug | visionEnabled |
|------------|---------------|
| `arena-arm` | `true` |
| 其他（training / private 等） | `false` |

#### `image_recognitions.py` — 统一 Prompt

| | 改动前 | 改动后 |
|---|--------|--------|
| Prompt 选择 | `PROMPT_LIST = {'arm1': PROMPT1, 'arm2': PROMPT2, ...}` | 统一 `VISION_PROMPT = PROMPT2` |
| arm1 场景 | 矩形 + 圆形双托盘（PROMPT1） | 已注释，不再使用 |
| Arena 场景 | PROMPT2（透明亚克力盒 + p(x)/(x)q） | 所有 vision 会话均用此 Prompt |

#### `/vision/dolls_compare` — AI 分析入口

Robot Server POST 到此接口；后端 `analyze_compare_pairwise()` 使用 `VISION_PROMPT` 做多帧投票分析，并可能触发积分奖励（`dolls_compare_reward`）。

---

## 6) Robot Server 逻辑 — `roarm-m3-web`（`2160a6ce`）

> 补齐 TeleOp Vision 链路的**机器人侧**；与 BE `0c028d1`（19:17）相隔 4 分钟提交（19:21）。

### 6.1 改动前的问题

| # | 问题 | 影响 |
|---|------|------|
| 1 | `lock_request` 忽略 `visionEnabled` | 后端已发字段，Robot 行为不变 |
| 2 | 所有会话均抓 start 帧 | Training 臂浪费相机/CPU |
| 3 | `ROBOT_ID in ("arm1","arm4")` 硬编码跳过 POST | 与 `robot_slug` 模型不一致 |
| 4 | 同 token 重连重复抓 start | 多余抓帧与潜在重复 POST |

### 6.2 新增全局状态

```python
g_vision_enabled = False   # 由 central server lock_request 设置
g_snapshot_token = None    # 已成功完成 session-start 抓帧的 token
```

### 6.3 `handle_lock_request` — 消费 `visionEnabled`

```python
vision_enabled = bool(data.get('visionEnabled', False))
# grant lock ...
g_vision_enabled = vision_enabled
print(f"Vision enabled for token {token}: {g_vision_enabled}")
```

- 字段缺失 → `False`
- 新 token 上锁 → `g_snapshot_token = None`
- 同 token 重连 lock → 更新 `g_vision_enabled` 为最新值

### 6.4 抓帧门控

| 函数 | 门控条件 | 行为 |
|------|----------|------|
| `_capture_session_start_views()` | `not g_vision_enabled` | 跳过；日志 `Vision disabled... skipping start capture` |
| `handle_control_connection()` | `g_vision_enabled && g_snapshot_token != token` | 才调用 start 抓帧；防同 token 重连重复 |
| `_capture_session_end_and_post()` | `not g_vision_enabled` | 跳过 end 抓帧与 POST |
| start 抓帧成功 | — | `g_snapshot_token = g_current_token` |

**删除的逻辑：**

```python
# 已移除
if ROBOT_ID in ("arm1", "arm4"):
    print(f"[snapshot] Skipping dolls_compare POST for robot {ROBOT_ID}")
    return
```

是否 POST 完全由 central server 的 `visionEnabled` 决定，不再看本地 `ROBOT_ID`。

### 6.5 状态清理（全生命周期）

以下场景均重置 `g_vision_enabled = False`、`g_snapshot_token = None`：

| 场景 | 函数 |
|------|------|
| Token 过期 | `clear_expired_token()` |
| 会话清理 | `cleanup_user_session()` |
| 控制连接 token 过期/不匹配 | `handle_control_connection()` |
| 控制循环中 session 过期 | `handle_control_connection()` while 循环 |
| Dev bypass 无 lock 连接 | `ALLOW_CONTROL_WITHOUT_LOCK` 分支（**强制** vision=false） |

### 6.6 行为对比（Robot 侧）

| 场景 | 改动前 | 改动后 |
|------|--------|--------|
| arena-arm（backend 发 true） | 抓帧 + POST（除非本地 ROBOT_ID=arm1/arm4） | 抓帧 + POST |
| training-arm | 仍抓 start；POST 取决于 ROBOT_ID | 不抓帧、不 POST |
| arm1/arm4 物理机 | 硬编码跳过 POST | 若 backend 发 `visionEnabled=true` 则会 POST |
| 同 token 重连 | 重复抓 start | 不重复（`g_snapshot_token` 去重） |
| Dev 无 lock 连接 | 会抓 start | `g_vision_enabled=False`，不抓 |

### 6.7 Robot 日志关键字（QA 断言用）

```
Vision enabled for token <token>: True/False
[snapshot] Vision disabled for this session; skipping start capture
[snapshot] session start captured 5 frames for <port> from ws://localhost:<port>
[snapshot] Vision disabled for this session; skipping end capture and POST
[snapshot] POST https://teleop.prismaxserver.com/vision/dolls_compare -> HTTP 200
[snapshot] Duplicate dolls_compare token detected (<token>); skipping POST
```

### 6.8 已知缺陷：use_robot 过程中刷新导致重复算分

> **状态**：改动后（`2160a6ce` + `0c028d1`）已观测到的回归风险，需在发版前重点验证。

#### 现象

用户在 **arena-arm** 控制会话中（已调用 `use_robot` 且控制 WS 已连接），执行**浏览器刷新**后，`dolls_compare` 相关积分（`dolls_compare_reward` / `tele_op_control_history.reward_points`）可能被**累计两次**。

#### 根因链（三层叠加）

```
刷新页面
  ↓
前端：WS 被浏览器直接断开（未发 {command:'disconnect'}，未调 queue/leave）
  ↓
Robot：handle_control_connection finally → cleanup_user_session()
  ↓
Robot：_capture_session_end_and_post()（g_vision_enabled=true）
  ↓  sleep 2s + 抓 end 帧
Robot：POST /vision/dolls_compare  ← 【第一次算分】
  ↓
后端：reward_points += 100*N；INSERT point_transactions (dolls_compare_reward)
      （无 control_token 幂等校验，每次 POST 都累加）

--- 用户仍在 queue，同一 control_token 仍有效（5min）---

刷新后再次进入 TeleOp → use_robot() → 新控制 WS
  ↓
Robot：g_snapshot_token 已在 cleanup 中清空 → 重新抓 start 帧
  ↓
用户正常结束 → disconnect/quit → cleanup → end POST
  ↓
若 g_last_dolls_compare_token 去重失效 → POST  again ← 【第二次算分】
```

#### 为何 `2160a6ce` 后更容易暴露

| 因素 | 说明 |
|------|------|
| Vision 门控打开 | arena-arm 刷新断开也会走 `_capture_session_end_and_post`（以前 arm 可能被 `ROBOT_ID` 跳过 POST，且不去重 token） |
| 刷新 ≠ 正常结束 | 前端 `useEffect` 卸载时若 `isTeleOpMode===true` **不会**调用 `disconnectControlWebSocket()`，Robot 将刷新视为异常断连并 cleanup |
| Robot 去重不可靠 | `g_last_dolls_compare_token` 仅进程内存；早退路径（缺 start/end 帧）**不设置** token；与 cleanup 的 2s `sleep` 存在竞态 |
| 后端无幂等 | `vision_dolls_compare` 使用 `reward_points = COALESCE(reward_points,0) + :rp`，同一 `control_token` 多次 POST 会重复 INSERT `dolls_compare_reward` |

#### 关键代码位置

**前端** — 刷新不断开控制 WS（除非 `isTeleOpMode` 已为 false）：

```154:159:app-prismax-rp/src/components/TeleOp/TeleOp.js
        return () => {
            // Don't disconnect on cleanup if still in teleop mode
            if (!isTeleOpMode) {
                disconnectControlWebSocket();
            }
        };
```

**Robot** — 异常断连触发完整 cleanup（含 vision 算分）：

```816:821:roarm-m3-web/roarm_server.py
    finally:
        async with g_lock:
            if g_control_websocket == websocket:
                await cleanup_user_session()
```

**后端** — 累加式计分，无去重：

```1707:1747:app-prismax-rp-backend/app_prismax_tele_op_services/app.py
                    if control_token:
                        conn.execute(..., {
                            "rp": reward_inc,  # COALESCE(reward_points,0) + :rp
                            "ct": control_token,
                        })
                        if reward_inc > 0:
                            ... INSERT INTO point_transactions ... 'dolls_compare_reward'
```

#### 重复算分的两条典型路径

| 路径 | 条件 | 结果 |
|------|------|------|
| **路径 A（确定会算分）** | 刷新后 start 帧已存在 → cleanup 成功 POST | 至少 **1 次** dolls_compare 积分（会话尚未真正结束） |
| **路径 B（重复算分）** | 路径 A 已 POST 且设了 `g_last_dolls_compare_token`，但用户重连后再次成功 end POST | 若去重失败 → **2 次**；若去重成功 → 仍 **1 次**（但第一次是误算） |
| **路径 C（去重失效）** | 第一次 end POST 早退（缺帧）未设 token → 用户重连玩完再 POST | **2 次** POST 均可能成功计分 |

#### 与 `process_session_rewards`（时长积分）的区别

| 奖励类型 | 触发 | 去重 |
|----------|------|------|
| `dolls_compare_reward` | Robot POST `/vision/dolls_compare` | **无**（后端） |
| `robot_control_reward` / `first_time_tele_op` | 前端 `queue/leave` → `process_session_rewards` | 有（`controlled_end_time IS NULL`） |

刷新**不会**调 `queue/leave`，故时长积分通常不在刷新时结算；用户报告的「重复算分」主要指 **Vision / dolls_compare 积分**。

#### 建议修复方向（供研发参考）

| 优先级 | 层 | 建议 |
|--------|-----|------|
| P0 | **后端** | `vision_dolls_compare` 对同一 `control_token` 幂等：已存在 `dolls_compare_reward` 或 `controlled_status` 非空则跳过累加 |
| P0 | **Robot** | 刷新/异常断连**不**走 end POST；仅 `{command:'disconnect'}` / `quit` 时算分 |
| P1 | **Robot** | cleanup 期间加 session 锁，避免 2s sleep 与新连接竞态导致双 cleanup |
| P1 | **前端** | `beforeunload` 发送 disconnect，或刷新前调 `queue/leave`；重连时识别同一 `control_token` 不重复触发 vision |
| P2 | **Robot** | `g_last_dolls_compare_token` 持久化到 DB 或由后端返回「已算分」 |

---

## 7) 全栈联动关系

| 能力 | 前端 | 后端 | Robot Server | 对齐点 |
|------|------|------|--------------|--------|
| Arena 会话结束 UI | `robotSlug === 'arena-arm'` → Session Complete | — | — | 同一 slug |
| Vision 开关 | — | `robot_slug == 'arena-arm'` → `visionEnabled` | `g_vision_enabled` 来自 lock_request | 三段协议一致 |
| 抓帧 / AI POST | — | 接收 `/vision/dolls_compare` | 仅 `g_vision_enabled` 时抓帧+POST | 非 arena 无抓帧 |
| AI Prompt | Session Complete 后可能展示结果 | `VISION_PROMPT`（Arena） | payload 含 `robotId`（配置项） | 不再用 arm1 双托盘 Prompt |
| QA 预览 | `DataReviewHub.js` | metadata 快路径 + 路径修复 | — | 视频可播放、加载更快 |

---

## 8) QA 风险点（汇总）

| # | 风险 | 模块 | 说明 |
|---|------|------|------|
| R1 | 链选择入口不可发现 | Connect | 用户习惯 Header 切链，需确认 Modal 内 Network 区可见 |
| R2 | 未展开 wallet 无法切链 | Connect | 必须先点「Connect a wallet」 |
| R3 | email+wallet 禁止切链 | Connect | 入口变了，warning 仍需弹出 |
| R4 | 链切换钱包列表不同步 | Connect | Solana ↔ EVM 时 WalletConnect 出现/消失 |
| R5 | private-arm 弹窗行为变更 | TeleOp FE | 不再弹 Session Complete，需产品确认 |
| R6 | 预览路径映射 | Data Pipeline | 仅部署 228f673 不部署 43f796c → 加载失败 |
| R7 | metadata 缺失回退 | Data Pipeline | 无 metadata 的 episode 须仍能出预览 |
| R8 | 邮件 Banner 404 | Static | 部署后公网 URL 须可访问 |
| R9 | 仅部署 BE 未部署 Robot | TeleOp | arena 无 dolls_compare；Robot 日志无 `Vision enabled: True` |
| R10 | 仅部署 Robot 未部署 BE | TeleOp | `visionEnabled` 恒 false，arena 也不走 vision |
| R11 | ROBOT_ID 与 robot_slug 配置不一致 | TeleOp | 旧逻辑靠本地 ROBOT_ID；新逻辑靠 backend slug |
| R12 | 同 token 重连重复 POST | Robot | `g_snapshot_token` + `g_last_dolls_compare_token` 双重去重须验证 |
| R13 | 相机不可达 | Robot | start 失败 → end 缺 start_list → 跳过 POST（原有逻辑） |
| R14 | Dev bypass 误开 vision | Robot | `ALLOW_CONTROL_WITHOUT_LOCK=true` 时 vision 强制关闭 |
| R15 | AI Prompt 误用 | TeleOp BE | arm1 旧场景不再使用 PROMPT1 |
| R16 | Vision 全链路积分/奖励 | TeleOp BE | dolls_compare 成功后 `dolls_compare_reward` 仅 arena 应有 |
| **R17** | **刷新异常断连误算分** | **Robot + FE** | 刷新触发 cleanup → 未真正结束会话即 dolls_compare POST |
| **R18** | **同一 control_token 重复 POST** | **Robot + BE** | `g_last_dolls_compare_token` 内存去重不可靠；后端无幂等 |
| **R19** | **cleanup 与新连接竞态** | **Robot** | end POST `sleep(2s)` 期间用户重连，可能双 cleanup / 状态被清空 |
| **R20** | **刷新后再次 use_robot** | **FE + BE** | 同一 token 二次 `use_robot` + 重连，与第一次误算分叠加 |

---

## 9) 完整测试策略

### 9.1 测试分层

| 层级 | 范围 | 工具 / 手段 | 负责验证 |
|------|------|-------------|----------|
| **L1 API** | `/data/qa/reviewable-uploads/previews` | curl / Postman / pytest | 响应结构、路径、回退 |
| **L2 组件/UI** | ConnectModal、Header、TeleOp 弹窗 | 手工 + DevTools | 布局、localStorage |
| **L3 集成** | FE ↔ BE | Network 抓包 | previews、鉴权、url_type |
| **L4 Robot** | `roarm_server.py` 日志 | SSH / 日志面板 | visionEnabled、抓帧、POST |
| **L5 E2E** | 跨三仓库真实路径 | 手工 / Playwright | 见 §11 |

### 9.2 环境与数据准备

| 项 | 要求 |
|----|------|
| **站点** | Beta `https://beta-app.prismax.ai`（主测）；生产发版前抽检 |
| **浏览器** | Chrome（主）、Safari（移动）、Firefox（抽检） |
| **前端版本** | 含 `e648b32`、`3d3ce9e` |
| **后端版本** | 含 `228f673`、`43f796c`、`0c028d1` |
| **Robot 版本** | 含 `2160a6ce`（arena 物理机或 staging robot） |
| **账号** | 未登录 / 仅 email / 仅 wallet / email+wallet / Innovator（TeleOp）/ QA 权限（Review Hub） |
| **TeleOp** | 可排队 `arena-arm`、`training-arm-*`；如有权限 `private-arm` |
| **QA Review** | Review Hub ≥30 条 `DERIVED_READY` upload（含 metadata 与无 metadata 各若干） |
| **钱包扩展** | MetaMask（Base/ETH）、Phantom（Solana） |
| **Robot 日志** | arena / training 物理机 `roarm_server` stdout 可读（或 log 采集） |

### 9.3 执行顺序（三阶段 + 发版门禁）

```
Phase 0 — 部署门禁（发版前，约 15 min）
  □ 确认三仓库 commit 版本与部署矩阵（§1）一致
  □ TC-265-028 smoke（previews API）
  □ TC-265-001 smoke（Header 无链选择器）

Phase 1 — 冒烟 P0（约 45 min）
  Connect：TC-265-001 ~ 010
  Review Hub API：TC-265-028 ~ 030
  E2E：E2E-265-001、E2E-265-006

Phase 2 — 回归 P1（约 2 h）
  Connect 边界：TC-265-011 ~ 020
  Review Hub：TC-265-031 ~ 036、E2E-265-007
  TeleOp Vision：TC-265-021 ~ 022、TC-265-037 ~ 042
  **刷新重复算分（§6.8）**：TC-265-049 ~ 052、E2E-265-014、E2E-265-016
  E2E：E2E-265-002 ~ 005、E2E-265-013（Vision 全链路）

Phase 3 — 扩展 P2（按需，约 1 h）
  TeleOp 弹窗边界：TC-265-023 ~ 025
  Robot 边界：TC-265-043 ~ 046
  Banner：TC-265-026 ~ 027、E2E-265-010
  回归：E2E-265-008 ~ 012
```

### 9.4 通过标准

| 级别 | 标准 |
|------|------|
| **P0** | 100% 通过方可 sign-off |
| **P1** | ≥95% 通过；失败项有 ticket 且非 blocker |
| **P2** | best-effort；记录风险接受项 |
| **Review Hub 性能** | 50 upload 的 previews POST：P95 较改前降低；预览可播放率 100% |
| **TeleOp Vision** | arena 会话：Robot 日志有 start+end 抓帧 + dolls_compare HTTP 200；training 无抓帧日志 |
| **刷新不算重（§6.8）** | arena 控制中刷新后：`point_transactions` 中同一 `control_token` 的 `dolls_compare_reward` **≤1 条**；`reward_points` 不异常翻倍 |

### 9.5 缺陷记录模板

1. 用例 ID、环境、浏览器 / Robot 机器 ID
2. 截图或录屏
3. Network：请求 URL、status、response 摘要
4. localStorage 快照（`selectedChain`）
5. 日志片段：**TeleOp BE** / **data_pipeline** / **roarm_server**（按场景）

### 9.6 自动化建议（Playwright / pytest）

| 可自动化 | 暂建议手工 |
|----------|-----------|
| Connect Modal 链选择 UI（TC-001~010 子集） | TeleOp 真机控制全流程 |
| previews API pytest（TC-028~036） | Robot 日志断言 |
| Review Hub 首屏加载（E2E-006） | dolls_compare AI 结果准确性 |
| Banner HTTP 200（TC-026） | 邮件客户端渲染 |

---

## 10) 分项测试用例（总表）

> 共 **52** 条；按用例 ID 排序。执行顺序建议见 §9.3。

| 用例ID | 优先级 | 分类 | 模块 | 用例标题 | 前置条件 | 测试步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| TC-265-001 | P0 | A. 链选择 UI | Header | Header 不再显示链选择器 | 任意登录态 | 打开首页，观察 header 右侧 | 无链图标、无下拉；仅 Connect 文案/地址 |
| TC-265-002 | P0 | A. 链选择 UI | ConnectModal | Modal 内 Network 区展示 | 未登录 | Connect → 展开「Connect a wallet」 | 可见 NETWORK / 链 pills / 分隔线 / WALLET / 钱包列表 |
| TC-265-003 | P0 | A. 链选择 UI | ConnectModal | 默认选中当前链 | `localStorage.selectedChain=base` | 打开 modal 并展开 wallet | Base 链 active 高亮 |
| TC-265-004 | P0 | A. 链选择 UI | ConnectModal | 切换链并持久化 | 未登录；列表已展开 | 点 Ethereum → 关 modal → 重开 | Ethereum active；localStorage 已更新 |
| TC-265-005 | P0 | A. 链选择 UI | ConnectModal | Solana 显示 WalletConnect | 当前链 Solana | 展开 wallet 列表 | 含 WalletConnect |
| TC-265-006 | P0 | A. 链选择 UI | ConnectModal | EVM 隐藏 WalletConnect | 链为 Base/ETH/Monad | 展开 wallet 列表 | **不含** WalletConnect |
| TC-265-007 | P0 | A. 链选择 UI | ConnectModal | 切链后列表联动 | 列表已展开 | Solana → Base → Solana | WalletConnect 即时出现/消失 |
| TC-265-008 | P0 | A. 链选择 UI | ConnectModal | email+wallet 禁止切链 | 双登录态 | 展开列表点其他链 | warning 弹出；链不变 |
| TC-265-009 | P0 | A. 链选择 UI | ConnectModal | 仅 wallet 可切链 | 仅 wallet | 切换链 | 成功；localStorage 更新 |
| TC-265-010 | P0 | A. 链选择 UI | ConnectModal | 连接中禁止切链 | isBusy | 点其他链按钮 | disabled，无法切换 |
| TC-265-011 | P1 | B. 链选择边界 | ConnectModal | 未展开无 Network 区 | 打开 Modal | 不点「Connect a wallet」 | 无 Network/Wallet 分区 |
| TC-265-012 | P1 | B. 链选择边界 | ConnectModal | 列表展开/收起 | 打开 Modal | 多次点击 wallet 切换 | 正常展开收起；无抖动 |
| TC-265-013 | P1 | B. 链选择边界 | ConnectModal | 关闭后状态 | 已展开并切链 | 关 modal 再开 | 列表默认收起；链选择保留 |
| TC-265-014 | P1 | B. 链选择边界 | Wallet | Base MetaMask 连接 | 装 MetaMask；链 Base | 选 MetaMask | Base EVM 连接成功 |
| TC-265-015 | P1 | B. 链选择边界 | Wallet | Solana Phantom 连接 | 链 Solana；装 Phantom | 选 Phantom | Solana 连接成功 |
| TC-265-016 | P1 | B. 链选择边界 | 样式 | 链按钮 active 视觉 | 列表展开 | 依次点各链 | 仅当前链白底高亮 |
| TC-265-017 | P1 | B. 链选择边界 | 样式 | 移动端布局 | 移动视口 | 展开 wallet 列表 | pills 换行不溢出 |
| TC-265-018 | P1 | B. 链选择边界 | Base Mini App | mini app 切链 | Base mini app | Modal 内选链连接 | 无 Header 链选择残留 |
| TC-265-019 | P1 | B. 链选择边界 | 回归 | PRIS-208 登录不受影响 | 未登录 | Email/Google/Apple 登录 | 登录正常 |
| TC-265-020 | P1 | B. 链选择边界 | 回归 | 刷新恢复链状态 | 已切链 | 刷新 → 开 modal | 显示上次链为 active |
| TC-265-021 | P1 | D. TeleOp 弹窗 | TeleOp FE | arena-arm 结束弹窗 | 非首次；可控制 arena | 正常结束会话 | `TeleopSessionCompleteModal` 弹出 |
| TC-265-022 | P1 | D. TeleOp 弹窗 | TeleOp FE | training-arm 无弹窗 | 非首次；training 臂 | 正常结束会话 | 不弹 Session Complete |
| TC-265-023 | P2 | D. TeleOp 弹窗 | TeleOp FE | private-arm 无弹窗 | 非首次；private 权限 | 正常结束会话 | 不弹 Session Complete（行为变更） |
| TC-265-024 | P2 | D. TeleOp 弹窗 | TeleOp FE | 首次用户 FirstTime | 首次 TeleOp | 结束 arena 会话 | `FirstTimeCompleteModal`；无 Session Complete |
| TC-265-025 | P2 | D. TeleOp 弹窗 | TeleOp FE | session 过期无弹窗 | 控制中 token 过期 | 触发过期结束 | 不弹 Session Complete |
| TC-265-026 | P2 | G. 静态资源 | Static | Banner 可访问 | 已部署 `3d3ce9e` | GET `/email-verify-qa-promo-banner.jpeg` | 200；图片正常 |
| TC-265-027 | P2 | G. 静态资源 | Email | 邮件模板引用 | 有 promo 模板 | 邮件/HTML 预览 | Banner 绝对 URL 正常加载 |
| TC-265-028 | P0 | C. Review Hub API | API | previews 基本成功 | QA token；已知 upload_ids | POST previews，`uploads: [id1,id2]` | `200`；`success:true`；`previews` 为数组；**每个元素必含** `upload_id`、`preview_video_url`、`preview_image_url`（值可为 URL 或 `null`）；快路径另含 `preview_video_url_type`、`preview_image_url_type` |
| TC-265-029 | P0 | C. Review Hub API | API | 有 metadata 视频可播放 | episode 有 metadata 且 `DERIVED_READY` | 取响应中该 `upload_id` 的 `preview_video_url`，浏览器或 curl 打开 | URL 返回 `200`；`.mp4` 可播放；非 404 |
| TC-265-030 | P0 | C. Review Hub API | API | preview.jpg 可访问 | 同上 | 取响应中该 `upload_id` 的 `preview_image_url`，浏览器或 curl 打开 | URL 返回 `200`；`preview.jpg` 图片正常显示 |
| TC-265-031 | P1 | C. Review Hub API | API | env slot 优先级 | episode 含 env/left/right | 对比 URL 与 metadata | 优先 env 视角 |
| TC-265-032 | P1 | C. Review Hub API | API | metadata 缺失回退 | 无 metadata 的 DERIVED_READY | 请求该 upload preview | 仍返回 URL（GCS list 回退） |
| TC-265-033 | P1 | C. Review Hub API | API | 超 200 上限 | QA token | `uploads` 传 201 个 id | 400；`uploads is limited to 200` |
| TC-265-034 | P1 | C. Review Hub API | API | 无 episode 空结构 | 无 DERIVED_READY episode | 请求该 upload | 返回对应项：`upload_id` 匹配；`preview_video_url:null`；`preview_image_url:null` |
| TC-265-035 | P1 | C. Review Hub API | 性能 | 批量请求延迟 | ≥50 个 upload | 计时单次 POST previews | P95 低于改前基线 |
| TC-265-036 | P1 | C. Review Hub API | API | url_type 字段 | 有 metadata 的快路径环境 | 检查含 metadata 的 upload 响应项 | 含 `preview_video_url_type`、`preview_image_url_type`，值为 `cdn` 或 `signed_url` |
| TC-265-037 | P1 | E. TeleOp Vision | TeleOp BE | arena lock_request visionEnabled | arena 激活 use_robot | 查 BE 日志或 WS 抓包 | `lock_request` 含 `visionEnabled: true` |
| TC-265-038 | P1 | E. TeleOp Vision | TeleOp BE | training visionEnabled false | training 臂 use_robot | 同上 | `visionEnabled: false` |
| TC-265-039 | P1 | E. TeleOp Vision | Robot | arena 接收 visionEnabled | Robot 含 `2160a6ce`；arena 会话 | 查 roarm_server 日志 | `Vision enabled for token ...: True` |
| TC-265-040 | P1 | E. TeleOp Vision | Robot | arena start 抓帧 | 同上；控制连接建立 | 查 Robot 日志 | `session start captured 5 frames`；`g_snapshot_token` 生效 |
| TC-265-041 | P1 | E. TeleOp Vision | Robot | arena end POST dolls_compare | 正常结束 arena 会话 | 查 Robot + BE 日志 | `POST .../vision/dolls_compare -> HTTP 200` |
| TC-265-042 | P1 | E. TeleOp Vision | Robot | training 跳过 vision | training 臂完整会话 | 查 Robot 日志 | `Vision disabled... skipping start/end capture`；无 POST |
| TC-265-043 | P2 | E. TeleOp Vision | Robot | 同 token 重连不重复 start | arena 会话中重连控制 WS | 查 Robot 日志 | 仅第一次有 `session start captured` |
| TC-265-044 | P2 | E. TeleOp Vision | Robot | 重复 token 不重复 POST | 同 control_token 异常触发两次 end | 查 Robot 日志 | `Duplicate dolls_compare token detected`；仅一次 POST |
| TC-265-045 | P2 | E. TeleOp Vision | TeleOp BE | AI Prompt 统一 | dolls_compare 触发后 | 查 `[image_recognitions]` 日志 | VISION_PROMPT（亚克力盒）；非 arm1 双托盘 |
| TC-265-046 | P2 | E. TeleOp Vision | Robot | token 过期清理 vision 状态 | 等待 token 过期 | 查 Robot 日志 | `g_vision_enabled` 重置；下次会话重新 lock |
| TC-265-047 | P2 | E. TeleOp Vision | Robot | 相机不可达降级 | 模拟 stream 端口不可用 | 完成 arena 会话 | start 失败；end 时 `Missing start image`；无 POST |
| TC-265-048 | P2 | E. TeleOp Vision | Robot | Dev bypass 关闭 vision | `ALLOW_CONTROL_WITHOUT_LOCK=true` | 无 lock 直接控制 | `g_vision_enabled=False`；无抓帧 |
| TC-265-049 | P0 | F. 刷新重复算分 | TeleOp | 控制中刷新触发 Robot cleanup | arena；非首次；已连接控制 WS | 1. 记录 `control_token` 与积分<br>2. 操作 30s 后 **F5 刷新**<br>3. 查 Robot 日志与 DB | Robot：`cleanup_user_session` + 可能出现 `POST dolls_compare`；DB 可能出现第 1 次 `dolls_compare_reward`（**误算**） |
| TC-265-050 | P0 | F. 刷新重复算分 | TeleOp | 刷新后重连同一 token 不重复算分 | 接 TC-265-049；queue 仍 active | 1. 刷新后重进 TeleOp<br>2. `use_robot` 重连<br>3. 正常结束<br>4. 查 `point_transactions` | **理想**：该 token 仅 1 条 `dolls_compare_reward`<br>**已知风险**：可能出现 2 条或积分累加 |
| TC-265-051 | P1 | F. 刷新重复算分 | DB | dolls_compare 幂等校验 | 可查 DB | 对 TC-265-050 的 token 查 `tele_op_control_history` / `point_transactions` | `dolls_compare_reward` 条数与 `points_change` 总和正确；与 Modal 一致 |
| TC-265-052 | P1 | F. 刷新重复算分 | Robot | 刷新 vs 正常 quit 日志对比 | arena；日志可读 | A组：控制中 F5 刷新<br>B组：点结束发 `disconnect` | A组：异常断连 cleanup，**不应**算分（修复后）<br>B组：仅 1 次 end POST + 1 次算分 |

**分类说明：** A 链选择 UI · B 链选择边界 · C Review Hub API · D TeleOp 弹窗 · E TeleOp Vision 全栈 · F 刷新重复算分（§6.8） · G 静态资源

**按分类统计：**

| 分类 | P0 | P1 | P2 | 小计 |
|------|----|----|-----|------|
| A. 链选择 UI | 10 | 0 | 0 | 10 |
| B. 链选择边界 | 0 | 10 | 0 | 10 |
| C. Review Hub API | 3 | 6 | 0 | 9 |
| D. TeleOp 弹窗 | 0 | 2 | 3 | 5 |
| E. TeleOp Vision | 0 | 6 | 6 | 12 |
| F. 刷新重复算分 | 2 | 2 | 0 | 4 |
| G. 静态资源 | 0 | 0 | 2 | 2 |
| **合计** | **15** | **24** | **13** | **52** |

---

## 11) E2E 端到端测试用例表

> 覆盖**真实用户路径**，跨 FE / BE / Robot 三层；Beta 环境手工或 Playwright 执行。

| E2E ID | 优先级 | 场景名称 | 角色/账号 | 前置数据 | 端到端步骤 | 跨层验证点 | 预期结果 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| **E2E-265-001** | P0 | Connect 切链后连钱包 | 未登录；MetaMask | 无 | 1. 打开 app → Connect<br>2. 展开 wallet；确认 Header 无链图标<br>3. Network 选 Base<br>4. Wallet 选 MetaMask 授权 | UI：Network/Wallet 分区<br>Storage：`selectedChain=base` | 连接成功；header 显示 Base 地址 |
| **E2E-265-002** | P0 | Solana 切链含 WalletConnect | 未登录 | 无 | 1. Connect → 展开 wallet<br>2. 选 Solana → 确认 WalletConnect<br>3. 切 Base → 消失<br>4. 切回 Solana | Storage：链值变化<br>UI：列表联动 | WalletConnect 仅 Solana 出现 |
| **E2E-265-003** | P0 | email+wallet 禁止切链 | 双登录 | 已双绑定 | 1. Connect → 展开 wallet<br>2. 点其他链 | UI：warning<br>Storage：链不变 | warning 正确；链未切换 |
| **E2E-265-004** | P0 | Arena TeleOp UI + BE vision | Innovator；非首次 | arena-arm 可排队 | 1. Live Control → Arena 入队<br>2. 控制并正常结束 | FE：`/tele-op/arena-arm`<br>BE：`visionEnabled=true`<br>FE：Session Complete 弹窗 | 弹窗出现；BE 发 true |
| **E2E-265-005** | P0 | Training TeleOp 无 vision | Innovator；非首次 | training-arm 可排队 | 1. Training 入队控制<br>2. 正常结束 | FE：training slug<br>BE：`visionEnabled=false`<br>Robot：无抓帧日志 | 无 Session Complete；无 vision |
| **E2E-265-006** | P0 | Review Hub 滚动预览 | QA 账号 | ≥30 upload；含 metadata | 1. Data → QA Review Hub<br>2. 首屏等待<br>3. 滚动加载<br>4. DevTools 看 previews | Network：POST previews<br>媒体：可播放/显示 | 不卡 loading；无大量 404 |
| **E2E-265-007** | P1 | Review Hub 翻页预览 | QA 账号 | 单行多页 | 1. 行内翻页<br>2. 观察新页预览 | Network：仅新 upload_ids | 新页预览正常；无重复请求 |
| **E2E-265-008** | P1 | 刷新后链状态 | 已连 wallet（Base） | `selectedChain=base` | 1. 刷新<br>2. Connect → 展开 wallet | Storage + UI | 链选择与连接态一致 |
| **E2E-265-009** | P1 | Private 臂无 Complete 弹窗 | private 权限 | private-arm | 1. 控制并结束会话 | FE：slug；弹窗 | 无 Session Complete |
| **E2E-265-010** | P2 | 邮件 Banner 公网可引用 | 无 | 已部署 `3d3ce9e` | 1. 访问 beta URL<br>2. 嵌入 HTML 预览 | HTTP 200 | 图片可加载 |
| **E2E-265-011** | P2 | PRIS-208 登录 + 新链选择 | 未登录 | 无 | 1. Email OTP 登录<br>2. Connect 切链（仅 email） | 登录态 + 链切换 | 互不影响 |
| **E2E-265-012** | P2 | metadata 缺失降级 | QA 账号 | 1 个无 metadata upload | 1. Review Hub 找该卡片 | API：GCS 回退 | 有预览或明确空态 |
| **E2E-265-013** | P0 | **Arena Vision 全链路** | Innovator；非首次 | arena 机含 Robot `2160a6c`；日志可读 | 1. Arena 入队 → use_robot<br>2. 建立控制连接<br>3. 操作后正常结束<br>4. 查 Robot + BE 日志 | BE：`visionEnabled=true`<br>Robot：start 5帧 + end POST 200<br>BE：`[image_recognitions]`<br>FE：Session Complete | 四层全通；training 作对照（E2E-005） |
| **E2E-265-014** | **P0** | **Arena 刷新重复算分（§6.8）** | Innovator；非首次 | arena；可查 DB；Robot 日志 | 1. 入队 → use_robot → 控制 30s<br>2. 记录 `control_token`、积分基线<br>3. **F5 刷新**<br>4. 重进 TeleOp → use_robot → 控制 → 正常结束<br>5. 查 DB + Modal 积分 | DB：同一 token 的 `dolls_compare_reward` **≤1**<br>Robot：刷新时是否误 POST；结束时是否 `Duplicate token` |
| **E2E-265-015** | P2 | 发版门禁：三仓库版本 | 测试环境 | 已知 commit 列表 | 1. 核对 FE/BE/Robot 部署版本<br>2. 跑 Phase 0 smoke | 版本矩阵 §1 | 缺任一 Vision commit 则 TeleOp E2E-013 不通过 |
| **E2E-265-016** | P1 | 刷新不误触 queue/leave | Innovator | arena 控制中 | 1. F5 刷新<br>2. 查 Network 是否有 `queue/leave` | 刷新瞬间**无** leave 请求；算分仅来自 Robot dolls_compare |

### E2E 执行矩阵

| 维度 | 必测组合 |
|------|----------|
| 浏览器 | Chrome 桌面 + Safari 移动 |
| 链 | Solana + Base（E2E-001/002） |
| TeleOp UI | arena（E2E-004）+ training（E2E-005） |
| TeleOp Vision 全链路 | arena（**E2E-265-013**）+ training 对照（E2E-005） |
| **刷新重复算分** | **E2E-265-014**（P0 必测）+ TC-265-049/050 |
| Review Hub | 滚动（E2E-006）+ 翻页（E2E-007）+ metadata 降级（E2E-012） |
| 登录态 | 未登录（E2E-001/002）+ 双登录（E2E-003） |
| 部署 | 发版门禁（E2E-015） |

### 用例统计

| 类型 | P0 | P1 | P2 | 合计 |
|------|----|----|-----|------|
| 分项 TC | 15 | 24 | 13 | **52** |
| E2E | 7 | 6 | 4 | **16** |

---

## 12) 设计意图总结

| 层 | 意图 |
|----|------|
| **产品** | 链选择合并进 Connect 流程；仅 Arena 臂走 Session Complete + Vision 奖励链路 |
| **前端** | 链 UI 下沉 Modal；TeleOp 用 `robot_slug` 替代 arm ID 白名单 |
| **后端** | previews 用 DB metadata 提速；`robot_slug` 驱动 `visionEnabled`；统一 AI Prompt |
| **Robot** | 消费 `visionEnabled` 门控抓帧/POST；去掉本地 `ROBOT_ID` 硬编码；防重连重复抓帧 |
| **运营** | 邮件 Banner 作为 `public/` 静态资源 |

---

## 13) 相关文档

- [PRIS-208 Connect Improvement](./PRIS-208_Connect_Improvement.md) — Connect Modal 登录主流程
- [PRIS-172 Review Hub Performance](./PRIS-172_ReviewHub_Performance.md) — Review Hub 性能基线
- [TeleOps 系统知识](./0_System系统知识/TeleOps_Tele.md) — `robot_slug` / `robot_class` 模型
