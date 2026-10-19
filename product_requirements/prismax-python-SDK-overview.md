# PrismaX Python SDK 概览与测试策略分析

> 文档版本：2026-05-14
> 对应仓库：`prismax-python`（alpha 状态）

---

## 一、SDK 简介

**PrismaX Python SDK**（包名 `prismax`）是 PrismaX 机器人数据集的官方 Python 工具链，覆盖从数据采集后到模型训练前的完整数据处理链路：

| 功能模块 | CLI 命令 | 核心能力 |
|----------|----------|----------|
| 数据下载 | `prismax-cli download` | 从 PrismaX 平台拉取 MCAP 原始录制，支持断点续传、MD5 完整性校验、中断安全 |
| 格式转换 | `prismax-cli convert` | MCAP → LeRobot v2.1 格式，支持 GPU(NVENC) / CPU(libx264) 视频重编码，支持 fixed/adaptive 两种分片策略 |
| 3D 可视化 | `prismax-cli visualize` | 基于 URDF 模型将关节状态渲染为 MP4 动画 |
| GUI 查看器 | `prismax-viewer` | PyQt6 桌面应用，同步播放多路摄像头视频与关节状态/动作曲线图，支持本地和 SSH 远程数据集 |

典型工作流：

```bash
prismax-cli login
prismax-cli download pkg_xxx --root 10_Assemble_and_mix_salad/
prismax-cli convert --root 10_Assemble_and_mix_salad/task_name --out lerobot_out --clean
prismax-cli visualize --root lerobot_out --episode 0 --robot piperx
prismax-viewer /path/to/lerobot_out
```

---

## 二、运行环境要求

### 2.1 操作系统

| 平台 | 支持状态 | 说明 |
|------|----------|------|
| **Linux**（Debian/Ubuntu） | ✅ 官方支持 | 全功能，包含 GUI 查看器 |
| macOS | ⚠️ 未声明 | 核心下载/转换可能可用，3D 渲染和 GUI 查看器不保证正常 |
| Windows | ⚠️ 未声明 | 同上，且 OpenGL/EGL 依赖名称不同 |

> GUI 查看器明确要求 **X11 或 Wayland** 显示环境。

### 2.2 Python 版本

- 最低要求：**Python 3.10+**
- 推荐版本：**Python 3.12+**

### 2.3 系统级依赖

| 系统包 | 用途 | 是否必须 |
|--------|------|----------|
| `ffmpeg` + `ffprobe`（需在 PATH 中） | 视频转换、渲染、编解码 | ✅ 转换/渲染必须 |
| `libegl1` | EGL OpenGL 上下文（3D 渲染） | ✅ visualize 必须 |
| `libgl1` | OpenGL 库 | ✅ visualize 必须 |

```bash
sudo apt install ffmpeg libegl1 libgl1
```

### 2.4 Python 依赖包（按功能）

| 安装方式 | 依赖包 | 覆盖功能 |
|----------|--------|----------|
| 核心（无 extra） | `mcap`, `mcap-ros2-support`, `numpy`, `pandas`, `pyarrow`, `pyyaml`, `huggingface-hub` | download + convert |
| `[visualize]` | `pyrender`, `trimesh`, `yourdfpy`, `pillow`, `opencv-python` | 3D 渲染生成 MP4 |
| `[viewer]` | `PyQt6`, `pyqtgraph`, `PyAV`, `httpx` | 交互式 Qt GUI 查看器 |
| `[robots]` | `prismax-robots`（URDF + 网格数据） | 内置机器人模型（PiperX） |
| `[all]` | 以上全部 | 完整功能 |
| `[dev]` | `pytest` | 运行测试套件 |

### 2.5 硬件要求

| 硬件 | 是否必须 | 说明 |
|------|----------|------|
| CPU | ✅ 必须 | 视频软编码（libx264 fallback） |
| NVIDIA GPU（NVENC/NVDEC） | 可选 | 加速视频编码，无则自动 fallback |
| 显示器（X11 / Wayland） | GUI 查看器必须 | 无显示环境可通过 SSH 隧道在本地机器查看远端数据 |

---

## 三、测试策略分析

### 3.1 测试整体结构

仓库测试分为两类，存放于 `prismax/tests/`：

| 类型 | 文件命名 | 运行方式 | 说明 |
|------|----------|----------|------|
| **单元/集成测试** | `test_*.py` | `pytest prismax/tests -q` | 自动化，纳入 CI |
| **冒烟测试** | `smoke_*.py` | 手动执行 | 需要真实数据集或 Qt 环境，不在默认 pytest 中运行 |

### 3.2 各模块测试覆盖

#### 3.2.1 数据集转换（convert）

| 测试文件 | 覆盖内容 |
|----------|----------|
| `test_convert_chunking.py` | `_plan_chunks` 分片逻辑（fixed / adaptive）、`_split_evenly` 均分算法、`_build_frame_table` 帧表构建与切片 |
| `test_convert_chunk_dirs.py` | 分片后输出目录结构正确性 |
| `test_convert_parallel.py` | 并行转换时的多 episode 处理 |
| `test_convert_image_stats.py` | 图像统计（min/max/mean/std）计算正确性 |

**测试策略特点：**
- 使用**纯 Python 合成数据**（`_make_synthetic_data`），完全不依赖真实 MCAP 文件和 ffmpeg，执行速度快、零外部依赖
- 对分片算法做**属性测试**（Property-based testing 风格）：遍历 1～250s 的所有可能时长，验证切片无间隙、无重叠不变量
- 覆盖多种边界条件：零帧、单帧、极短/极长录制、尾部 stub 合并阈值边界值

#### 3.2.2 静止段检测（stillness）

| 测试文件 | 覆盖内容 |
|----------|----------|
| `test_stillness.py` | 关节速度计算（`compute_joint_speed`）、静止段识别（`find_still_segments`）、自适应切点规划（`plan_adaptive_cuts`）|

**测试策略特点：**
- 构造已知物理特性的信号（匀速运动、恒定速度、夹爪排除）验证速度计算精度
- 覆盖 Adaptive 模式的核心业务逻辑：切点吸附到静止段中点、切点不重用同一静止段、最小切块长度保护（防止 7s 超短 chunk 的回归问题）
- 包含针对真实录制场景的**回归测试**（`6328.mcap` 聚集静止段导致子块过短的 bug fix 验证）

#### 3.2.3 认证（auth）

| 测试文件 | 覆盖内容 |
|----------|----------|
| `test_auth.py` | Token 存储/加载/清除、三级优先级解析（参数 > 文件 > 环境变量）、空 Token 拒绝、JSON 格式错误容错 |
| `test_auth_cli.py` | CLI login/logout 命令行交互流程 |

**测试策略特点：**
- 通过 `monkeypatch` 重定向 `$XDG_CONFIG_HOME`，每个测试完全隔离于用户真实的 `~/.config`
- 验证凭证文件权限必须为 `0600`（POSIX 安全要求）
- 覆盖异常路径：空 Token、格式损坏的 JSON 文件（graceful 降级而非 crash）、空输入行

#### 3.2.4 Viewer HTTP 服务器（viewer server）

| 测试文件 | 覆盖内容 |
|----------|----------|
| `test_viewer_server.py` | `/healthz`、`/manifest`、`/list`、`/file`（含 Range/ETag/304）、`/digest` 等接口；路径越狱防护（`../../../etc/passwd`）；Bearer Token 鉴权 |

**测试策略特点：**
- 启动真实 HTTP server（`threading.Thread` daemon 模式），使用 `http.client` 发送真实 HTTP 请求
- 覆盖**安全边界**：路径穿越攻击（path traversal）返回 400，未携带 Token 返回 401，Token 错误返回 401
- 覆盖 HTTP 协议细节：断点续传（`Range: bytes=`）、条件请求（`If-None-Match`）、`Accept-Ranges` 声明
- 服务器日志行为测试：验证 `--log-dir` 模式下 stderr handler 被移除（防止管道缓冲区死锁的回归验证）

#### 3.2.5 SSH 远程引导（remote bootstrap）

| 测试文件 | 覆盖内容 |
|----------|----------|
| `test_remote_bootstrap.py` | `RemoteBootstrap` 完整状态机（SSH 连接 → Python 探测 → payload 推送 → 服务启动 → READY 解析） |
| `test_remote_probe.py` | 远端 Python 版本探测逻辑 |
| `test_remote_payload.py` | Zipapp payload 生成与推送 |
| `test_remote_password.py` | SSH 密码认证流程 |
| `test_remote_ssh_quoting.py` | SSH 命令参数转义/引号处理正确性 |

**测试策略特点：**
- 使用**假 SSH shim**（Python 脚本模拟 ssh 行为）替代真实 SSH 连接，实现端到端状态机验证而无需真实远端主机
- 假 SSH shim 能响应：master 控制连接、Python 探测、payload 写入、端口转发命令

#### 3.2.6 Viewer 其他模块

| 测试文件 | 覆盖内容 |
|----------|----------|
| `test_viewer_dataset.py` / `test_viewer_dataset_meta_only.py` | LeRobot 数据集元数据加载与 episode 列表解析 |
| `test_viewer_cache_*.py`（4 个文件） | 本地缓存路径管理、数据存储、持久化、Fetcher 下载逻辑 |
| `test_viewer_http_source.py` / `test_viewer_http_source_offline.py` | HTTP 数据源（在线/离线缓存）读取 |
| `test_viewer_status_bar.py` | 状态栏 UI 状态显示逻辑 |
| `test_viewer_attach_remote.py` | 连接远程 viewer server 的附加流程 |
| `test_viewer_app_cli.py` | viewer CLI 参数解析 |

#### 3.2.7 基础导入与 CLI 参数校验

| 测试文件 | 覆盖内容 |
|----------|----------|
| `test_imports.py` | 包导入、版本号存在、公共 API 可调用性、`DataSetConfig` 参数校验（fps/width/height/nvenc_cq 非法值）、各种错误路径（文件缺失、格式错误、路径重叠等） |
| `test_cli.py` | CLI 子命令基本 invocation |
| `test_robots.py` | 机器人模型注册表与短名称查找 |

#### 3.2.8 冒烟测试（手动执行）

| 文件 | 用途 |
|------|------|
| `smoke_viewer.py` | 以 offscreen 模式启动 Qt 主窗口，走完加载→播放→暂停完整流程 |
| `smoke_remote_viewer.py` | 通过 SSH 远端数据集端到端冒烟 |
| `smoke_reset_zoom.py` | 验证缩放重置交互 |
| `smoke_chart_balance.py` | 验证关节图表布局对称性 |

### 3.3 测试策略总结

| 维度 | 特点 |
|------|------|
| **测试分层** | 单元测试（纯逻辑）→ 集成测试（真实 HTTP/进程）→ 冒烟测试（Qt GUI） |
| **外部依赖隔离** | 转换/静止段测试完全使用合成数据，不依赖 ffmpeg/MCAP；SSH 测试用 fake shim |
| **安全测试** | 路径穿越攻击、Token 鉴权失败均有专项 case |
| **边界值覆盖** | 零帧、单帧、阈值边界（`MIN_TAIL_CHUNK_SECONDS` ± 1）均有覆盖 |
| **回归保护** | 关键 bug（7s 超短 chunk、管道死锁）对应有注释明确的回归测试 |
| **属性测试思路** | 分片算法通过遍历 1～250s 验证不变量，接近 Property-based testing |
| **CI 友好** | 自动化测试（`test_*.py`）零真实数据集依赖，`pytest` 直接可跑；冒烟测试手动执行不影响 CI |

### 3.4 当前测试盲区（QA 关注点）

以下领域在现有测试中**覆盖较弱或缺失**，建议 QA 重点关注：

1. **端到端 download → convert 全链路**：现有测试分别验证各模块，但真实 MCAP 文件的完整转换流程依赖手动 smoke 测试
2. **NVENC 硬件编码路径**：无 GPU 的 CI 环境无法自动覆盖，需要有 NVIDIA GPU 的机器单独验证
3. **macOS / Windows 兼容性**：完全空白，需要明确是否在规划中
4. **并发下载中断恢复**：`SIGINT` 安全退出、`.part` 文件清理的自动化测试缺失
5. **Viewer GUI 交互**：冒烟测试仅覆盖加载和播放，拖动进度条、切换 episode、SSH 断线重连等交互路径未自动化
6. **LeRobot 数据集格式合规性**：转换输出是否完全符合 LeRobot v2.1 schema 规范，缺少 schema 级别的合规校验测试

The following areas currently have **weak or missing test coverage** and are recommended as key QA focus areas:

1. **End-to-end download → convert pipeline**: Existing tests validate individual modules separately, but the complete conversion workflow using real MCAP files still relies on manual smoke testing.
2. **NVENC hardware encoding path**: CI environments without GPUs cannot automatically cover this path; dedicated validation on machines with NVIDIA GPUs is required.
3. **macOS / Windows compatibility**: Currently no coverage at all. It should be clarified whether support for these platforms is part of the roadmap.
4. **Concurrent download interruption recovery**: Automated tests are missing for SIGINT-safe shutdown behavior and cleanup of .part files.
5. **Viewer GUI interactions**: Current smoke tests only cover loading and playback. Interaction flows such as timeline seeking, episode switching, and SSH disconnect/reconnect are not automated.
6. **LeRobot dataset format compliance**: There is no schema-level validation to ensure converted outputs fully comply with the LeRobot v2.1 schema specification.