# roarm-m3-web — 2026-07-07 Commit 分析与测试策略

**仓库：** `roarm-m3-web`（branch: `testing`）  
**分析范围：** `2160a6c`（含）→ `8931fba`（HEAD）  
**日期跨度：** 2026-06-23 ~ 2026-06-29  
**提交作者：** lanmanc  
**改动规模：** 7 文件，+1345 / -26 行

---

## 一、Commit 清单

| # | Hash | 时间 | 说明 |
|---|------|------|------|
| 1 | `2160a6c` | 2026-06-23 19:21 | fixing roarm_server ai issue |
| 2 | `911b978` | 2026-06-28 16:24 | updated for youtube stream with roarm_streaming_server.py |
| 3 | `d60bedd` | 2026-06-28 16:43 | updated streaming gui |
| 4 | `dc5c7dc` | 2026-06-28 17:03 | improved stream manager |
| 5 | `42e9596` | 2026-06-28 17:19 | fixing bug |
| 6 | `1af54c7` | 2026-06-28 17:25 | updated stream manager |
| 7 | `3130f3c` | 2026-06-28 17:44 | auto open url |
| 8 | `10b8a3c` | 2026-06-28 17:48 | fixing bug |
| 9 | `0d2865c` | 2026-06-28 19:14 | reduced bitrate |
| 10 | `8931fba` | 2026-06-29 13:21 | no we could have no youtube stream |

---

## 二、改动详细分析

### 2.1 `2160a6c` — roarm_server AI 视觉开关动态化

**文件：** `roarm_server.py`  
**改动规模：** +48 / -4

#### 2.1.1 问题背景

旧逻辑通过硬编码 robot ID 决定是否跳过视觉快照（`arm1`、`arm4` 不执行 dolls_compare），无法灵活应对不同场景需求。

#### 2.1.2 核心改动

新增两个全局状态变量：

```python
g_vision_enabled = False   # 由中央服务器 lock 请求携带的 visionEnabled 字段设置
g_snapshot_token = None    # 已完成 start-capture 的 token，防止重复抓取
```

**lock 请求处理（`handle_lock_request`）：**
- 从请求数据读取 `visionEnabled` 字段（bool，默认 `False`）
- 将值赋给 `g_vision_enabled`，决定本 session 是否允许视觉功能

**快照函数 guard 条件：**

| 函数 | 变化 |
|------|------|
| `_capture_session_start_views()` | 开头检查 `g_vision_enabled`，为 `False` 时直接 return，跳过所有快照抓取 |
| `_capture_session_end_and_post()` | 开头检查 `g_vision_enabled`，为 `False` 时跳过结束帧抓取和 dolls_compare POST |

**移除硬编码逻辑：**
```python
# 旧代码（已删除）
if ROBOT_ID in ("arm1", "arm4"):
    print(f"[snapshot] Skipping dolls_compare POST for robot {ROBOT_ID}")
    return
```

**状态重置时机（全部节点均重置 `g_vision_enabled = False` + `g_snapshot_token = None`）：**
- token 过期清除
- lock 请求中新 token 分配
- 控制连接建立
- 控制连接断开
- `cleanup_user_session()`

**session start capture 去重：**
```python
if g_vision_enabled and g_snapshot_token != token:
    await _capture_session_start_views()
```
避免同一 token 重连时重复执行 start capture。

---

### 2.2 `911b978` ~ `0d2865c` — YouTube Live 推流 & Stream Manager GUI

**文件：** `roarm_streaming_server.py`（+374）、`roarm_stream_manager.py`（全新，873行）、`restart_roarm_streaming_server.sh`、`README.md`、`.gitignore`

#### 2.2.1 `roarm_streaming_server.py` — YouTube 推流模块

**新增 `YouTubePublisher` 类：**

- 通过 `ffmpeg` 将摄像头帧以 RTMPS 推送 YouTube Live
- 编码参数：`libx264 veryfast zerolatency`，视频码率 1200k（`0d2865c` 降码率），音频 `anullsrc` 静音填充
- 内部维护 `maxsize=1` 的 `Queue`（丢帧优先，防止堆积），独立后台线程写入 ffmpeg stdin
- ffmpeg 未安装或 pipe 断开时自动标记 `failed = True`，停止推流并打印告警
- 流密钥通过 `.robot_config.json` 读取，支持多种 key 名称兼容（`YOUTUBE_STREAM_KEY`、`YOUTUBE_RTMPS_URL` 等）
- 日志中对 RTMPS URL 做掩码处理（`mask_stream_url`）

**摄像头指定方式增强：**

| 新参数 | 说明 |
|--------|------|
| `--camera` | 支持 `/dev/video2`、`/dev/v4l/by-id/...`、数字索引 |
| `--camera-index` | 数字索引（兼容旧用法） |
| `--list-cameras` | 探测并打印所有可用摄像头后退出 |
| `--youtube on/off/ask` | 控制是否启用 YouTube Live 推流 |
| `--flip on/off/ask` | 原有参数，扩展非交互式支持 |

**`8931fba` 最终状态：** `--youtube` 默认为 `ask`，非 tty 环境自动跳过 YouTube（不强制）。

#### 2.2.2 `roarm_stream_manager.py` — 全新 Web GUI 管理工具

**服务入口：** `python3 roarm_stream_manager.py`，默认监听 `http://localhost:8080`

**后端（Python `ThreadingHTTPServer`）API：**

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 返回内嵌 HTML 页面 |
| `/api/cameras` | GET | 扫描可用摄像头，返回 JPEG 预览（base64） |
| `/api/streams` | GET | 返回当前所有运行中的流进程状态 |
| `/snapshot?camera=...` | GET | 实时抓取指定摄像头单帧 JPEG |
| `/api/start` | POST | 启动指定摄像头的流服务进程 |
| `/api/stop` | POST | 停止指定端口的流服务进程 |
| `/api/stop_all` | POST | 停止全部流服务进程 |

**前端功能：**
- 显示所有可用摄像头卡片，含 JPEG 预览、设备路径、分辨率信息
- 每张摄像头卡片可选择：端口（8001/8002/8003）、Flip 180°、是否作为 YouTube 流
- 标记 AI 检测摄像头（与 `.robot_config.json` 中 `IMAGE_RECOGNITION_CAM` 比对）
- 右侧面板显示运行中流列表（含 pid、ws_url、YouTube 状态），每路流可独立停止
- 每 3 秒轮询 `/api/streams` 刷新状态
- 支持暗色/亮色主题自适应（`prefers-color-scheme`）
- 启动时自动打开浏览器（可 `--no-browser` 禁用）
- 子进程日志写入 `.stream_manager_logs/stream_{port}.log`，配置持久化至 `.stream_manager_config.json`

#### 2.2.3 `restart_roarm_streaming_server.sh`

新增 `YOUTUBE_MODE` 第三参数（默认 `off`），启动命令增加 `--youtube "$YOUTUBE_MODE"` 透传。

---

## 三、改动影响范围评估

| 模块 | 风险等级 | 说明 |
|------|---------|------|
| `roarm_server.py` — visionEnabled | **高** | 核心会话逻辑变更，直接影响 dolls_compare 数据上报；旧的 robot ID 白名单逻辑被移除 |
| `roarm_streaming_server.py` — YouTube | **中** | 新增功能，不影响现有 WebSocket 流；YouTube 不可用时有 fallback |
| `roarm_stream_manager.py` | **低** | 独立工具，不影响现有服务；进程管理通过 subprocess 隔离 |
| `restart_roarm_streaming_server.sh` | **低** | 仅新增可选参数，旧调用方式向下兼容 |

---

## 四、测试策略

### 4.1 总体原则

1. **优先覆盖高风险变更**：`visionEnabled` 开关的行为正确性是本次测试重点，需覆盖所有 session 生命周期节点
2. **新功能验证**：YouTube 推流和 Stream Manager GUI 均为全新功能，需独立验证
3. **回归验证**：确保旧的 WebSocket 视频流功能、lock/unlock 流程不受影响
4. **边界条件**：token 重连、并发访问、进程异常退出等场景需要覆盖

### 4.2 测试分层

| 层级 | 范围 | 工具/方式 |
|------|------|----------|
| 单元测试 | `visionEnabled` 状态机、`YouTubePublisher` 帧队列逻辑 | pytest / mock |
| 集成测试 | lock 请求 → 视觉快照流程、Stream Manager API | pytest + WebSocket client |
| E2E 测试 | 完整用户会话（lock → 操作 → unlock → dolls_compare）、GUI 操作流程 | 手动 / 脚本模拟 |
| 回归测试 | WebSocket 视频流、lock/unlock 基础流程 | 现有测试用例 |

### 4.3 测试环境要求

- Linux 机器（用于 `/dev/video*` 摄像头路径测试）
- 至少 1 路 USB 摄像头
- `.robot_config.json` 配置完整（含 `ROBOT_ID`、`IMAGE_RECOGNITION_CAM`、可选 `YOUTUBE_STREAM_KEY`）
- ffmpeg 已安装（YouTube 推流测试）
- 中央服务器可发送带 `visionEnabled` 字段的 lock 请求

---

## 五、E2E 测试用例

### 5.1 visionEnabled 开关行为

| ID | 场景 | 前置条件 | 操作步骤 | 预期结果 |
|----|------|---------|---------|---------|
| V-01 | visionEnabled=true 时执行 start capture | 摄像头可用，流服务运行中 | 中央服务器发送 lock 请求，`visionEnabled: true`；客户端建立控制连接 | `_capture_session_start_views` 被调用，日志输出 `session start captured N frames` |
| V-02 | visionEnabled=false 时跳过 start capture | 同上 | 中央服务器发送 lock 请求，`visionEnabled: false`；客户端建立控制连接 | 日志输出 `Vision disabled for this session; skipping start capture`，无快照请求 |
| V-03 | visionEnabled=true 时执行 end capture 并 POST | V-01 完成后 | 客户端断开连接，触发 session 结束 | `_capture_session_end_and_post` 被调用，发送 POST 到 `/vision/dolls_compare`，响应成功 |
| V-04 | visionEnabled=false 时跳过 end capture 和 POST | V-02 完成后 | 客户端断开连接 | 日志输出 `Vision disabled for this session; skipping end capture and POST`，无 HTTP 请求发出 |
| V-05 | 同一 token 重连不重复执行 start capture | V-01 完成后，`g_snapshot_token` 已记录 | 相同 token 再次建立控制连接 | start capture 不再执行（`g_snapshot_token == token`），日志无 `session start captured` |
| V-06 | token 过期后 visionEnabled 重置 | session 进行中，`g_vision_enabled=true` | 等待 token 5 分钟过期 | `g_vision_enabled` 重置为 `False`，`g_snapshot_token` 重置为 `None` |
| V-07 | 新 token 替换旧 token 时状态重置 | 旧 session 已过期 | 中央服务器发送新 lock 请求（新 token，`visionEnabled: false`） | 新 session 的 `g_vision_enabled = False`，旧 snapshot token 清除 |
| V-08 | lock 请求未携带 visionEnabled 字段时默认 false | 无特殊前置 | 发送不含 `visionEnabled` 的 lock 请求 | `g_vision_enabled` 默认为 `False`，视觉功能不执行 |
| V-09 | cleanup_user_session 重置 visionEnabled | 任意 session 进行中 | 调用 cleanup（如服务端主动踢人） | `g_vision_enabled = False`，`g_snapshot_token = None` |
| V-10 | 旧 robot ID 白名单逻辑已移除（回归） | `ROBOT_ID = "arm1"` 或 `"arm4"` | 发送 lock 请求，`visionEnabled: true` | dolls_compare POST 正常发出（不再因 robot ID 而跳过） |

### 5.2 YouTube Live 推流

| ID | 场景 | 前置条件 | 操作步骤 | 预期结果 |
|----|------|---------|---------|---------|
| Y-01 | `--youtube on` 正常启动推流 | ffmpeg 已安装，`.robot_config.json` 含有效 `YOUTUBE_STREAM_KEY` | 执行 `python3 roarm_streaming_server.py --port 8001 --flip off --youtube on` | 日志输出 `[YouTube] Live streaming enabled: rtmps://...****xxxx`，ffmpeg 进程启动，YouTube 后台收到视频流 |
| Y-02 | `--youtube off` 禁用推流 | 同上 | 执行 `... --youtube off` | 日志输出 `[YouTube] Live streaming disabled from CLI.`，无 ffmpeg 进程 |
| Y-03 | ffmpeg 未安装时降级处理 | ffmpeg 不在 PATH 中 | 执行 `... --youtube on` | 日志输出 `[YouTube] ffmpeg was not found. YouTube Live streaming disabled.`，流服务正常启动，`failed = True` |
| Y-04 | `.robot_config.json` 无 stream key 时报错 | 配置文件不含 YouTube 相关 key | 执行 `... --youtube on` | 抛出 `RuntimeError: YouTube Live was requested, but no stream key was found`，进程退出 |
| Y-05 | 码率限制（1200k）生效 | Y-01 条件 | 启动推流，用 ffprobe 检查推流参数 | 视频码率不超过 1200k，`-preset veryfast -tune zerolatency` 生效 |
| Y-06 | 帧队列满时丢帧不阻塞 | Y-01 条件，ffmpeg 处理慢 | 模拟 ffmpeg 写入延迟（或调低 fps） | 旧帧被丢弃，最新帧覆盖，WebSocket 视频流不受阻塞 |
| Y-07 | ffmpeg pipe 断开时自动停止推流 | Y-01 条件 | 在推流过程中 kill ffmpeg 进程 | 日志输出 `[YouTube] ffmpeg pipe closed`，`failed = True`，WebSocket 流继续正常服务其他客户端 |
| Y-08 | RTMPS URL 在日志中被掩码 | Y-01 条件 | 查看启动日志 | 日志中 stream key 只显示末 4 位（如 `****xxxx`），不暴露完整 URL |
| Y-09 | `--youtube ask` 在非 tty 环境下默认禁用 | 无 tty（如 systemd service 或脚本调用） | 不传 `--youtube` 参数或传 `--youtube ask` | 日志输出 `No interactive terminal detected. YouTube Live streaming disabled by default.` |
| Y-10 | `restart_roarm_streaming_server.sh` 透传 youtube 参数 | ffmpeg 已安装，配置齐全 | 执行 `bash restart_roarm_streaming_server.sh 8001 off on` | 子进程以 `--youtube on` 启动，推流正常；重启后参数保持 |

### 5.3 Stream Manager GUI

| ID | 场景 | 前置条件 | 操作步骤 | 预期结果 |
|----|------|---------|---------|---------|
| G-01 | 启动 manager 并自动打开浏览器 | 摄像头已连接 | `python3 roarm_stream_manager.py` | 浏览器自动打开 `http://localhost:8080`，页面显示摄像头列表 |
| G-02 | 摄像头扫描显示预览图 | 至少 1 路摄像头可用 | 打开页面或点击 Refresh Cameras | 可用摄像头显示 JPEG 预览图、设备路径、Frame OK 状态 |
| G-03 | 启动流服务进程 | 摄像头可用，8001 端口未被占用 | 选择端口 8001，点击 Start | 右侧 Running Streams 出现该流条目，含 pid 和 ws_url；按钮变为 Stop |
| G-04 | 停止流服务进程 | G-03 完成后 | 点击 Stop 按钮 | Running Streams 中该条目消失，按钮变为 Start；ws://localhost:8001 不再可连接 |
| G-05 | Flip 180° 选项生效 | 摄像头可用 | 勾选 Flip 180，点击 Start | 启动的子进程包含 `--flip on` 参数；通过 ws 连接验证画面已旋转 |
| G-06 | AI detection camera 标记 | `.robot_config.json` 含 `IMAGE_RECOGNITION_CAM: "8001"` | 打开页面 | 端口 8001 的摄像头卡片显示 `AI detection camera` 红色标签 |
| G-07 | YouTube stream 单选互斥 | 两路摄像头可用 | 先为 cam1 勾选 YouTube stream 并启动；再尝试为 cam2 启动 YouTube stream | 第二次启动时返回错误 `YouTube is already enabled on port XXXX`，cam2 未启动 |
| G-08 | Stop All 停止全部流 | 已启动 2 路流 | 点击 Stop All | 所有流进程终止，Running Streams 面板显示空 |
| G-09 | 状态每 3 秒自动刷新 | 已启动流服务 | 在页面外通过命令行手动停止某个流进程 | 最多 3 秒后页面 Running Streams 自动更新，消失的流条目移除 |
| G-10 | 日志文件写入 | G-03 完成后 | 检查 `.stream_manager_logs/stream_8001.log` | 文件存在，内容为流服务的 stdout/stderr 输出 |
| G-11 | `--no-browser` 禁用自动打开 | 无 | `python3 roarm_stream_manager.py --no-browser` | 服务正常启动，不弹出浏览器；手动访问 `http://localhost:8080` 可正常使用 |
| G-12 | 非 Linux 系统摄像头索引探测 | macOS 或 Windows | 启动 manager | 摄像头按数字索引（0~9）探测，可用的正常显示预览 |
| G-13 | 暗色主题适配 | 系统设置为暗色模式 | 打开管理页面 | 页面背景、文字、边框颜色符合暗色主题 CSS 变量 |
| G-14 | `/snapshot` 实时预览接口 | 摄像头可用 | 在 camera 卡片点击 Preview 按钮 | 图片刷新为最新一帧（带时间戳防缓存），不影响流服务运行 |

### 5.4 `--list-cameras` 功能

| ID | 场景 | 前置条件 | 操作步骤 | 预期结果 |
|----|------|---------|---------|---------|
| L-01 | Linux 列出 `/dev/video*` 及 by-id 路径 | Linux，多路摄像头 | `python3 roarm_streaming_server.py --list-cameras` | 输出每个 `/dev/videoX` 的状态（OK/NO FRAME）及对应 `/dev/v4l/by-id/` 路径；进程正常退出 |
| L-02 | 非 Linux 列出数字索引 | macOS/Windows | `python3 roarm_streaming_server.py --list-cameras` | 输出 0~9 索引的探测结果；进程正常退出 |
| L-03 | 无摄像头时输出提示 | 无任何摄像头 | `python3 roarm_streaming_server.py --list-cameras` | 输出 `No working camera found.`，进程以 0 退出 |

### 5.5 回归测试（核心流程）

| ID | 场景 | 预期结果 |
|----|------|---------|
| R-01 | WebSocket 视频流正常（无 YouTube） | `ws://localhost:8001` 可连接，持续收到 base64 帧，FPS 接近 30 |
| R-02 | lock/unlock 基础流程 | 中央服务器 lock → 客户端连接 → 操作 → 断开，全程无异常日志 |
| R-03 | 并发两个客户端连接同一流端口 | 两个客户端均收到帧，互不干扰 |
| R-04 | 流服务超时断开（MAX_CONN_SECONDS=300） | 连接超过 5 分钟自动断开，服务不崩溃 |
| R-05 | `.robot_config.json` 缺失时服务正常启动 | 使用默认 `ROBOT_ID=arm1`，打印警告，流服务正常工作 |

---

## 六、已知风险与注意事项

1. **`visionEnabled` 依赖中央服务器正确传参**：若中央服务器未升级支持 `visionEnabled` 字段，所有机器人的视觉功能将默认关闭（`False`），需确认中央服务器同步部署。

2. **arm1/arm4 的特殊逻辑移除**：旧代码对 `arm1`、`arm4` 的 dolls_compare 硬跳过逻辑已删除，这两台机器人的行为现在完全由 `visionEnabled` 控制，需确保中央服务器对这两台机器人发送的 lock 请求中 `visionEnabled: false`（如之前的业务意图如此）。

3. **YouTube 推流码率**：1200k 视频码率在网络环境较差时可能导致 RTMPS 推流卡顿，需在实际网络环境中验证。

4. **Stream Manager 进程管理**：`stop_stream` 使用 `os.killpg` 发送 SIGTERM 到进程组，在 macOS 上行为可能与 Linux 不同，需在目标部署系统上验证。

5. **Stream Manager 单实例**：当前无端口冲突检测，若 8080 端口已被占用，manager 启动会报错，建议增加明确的端口冲突提示。
