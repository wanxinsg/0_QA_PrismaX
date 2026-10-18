# PrismaX Python SDK

[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![Status](https://img.shields.io/badge/status-alpha-orange)]()

**PrismaX Python SDK**（`prismax`）是用于处理 PrismaX 机器人数据集的官方工具链：支持下载原始 MCAP 录制文件、将其转换为 [LeRobot v2.1](https://huggingface.co/docs/lerobot) 格式、将录制的片段渲染为 URDF 驱动的 3D 动画，并通过 Qt GUI 查看器对 LeRobot 数据集进行交互式检查。

本 README 涵盖日常使用说明：安装、登录、CLI、查看器。Python API、数据格式、架构说明及开发者信息请参阅 [`docs/`](docs/) 目录。

| 文档 | 内容 |
|------|------|
| [docs/python-api.md](docs/python-api.md) | 所有 `prismax.*` 子模块的可导入符号。 |
| [docs/data-formats.md](docs/data-formats.md) | MCAP 输入格式与 LeRobot v2.1 输出 schema。 |
| [docs/architecture.md](docs/architecture.md) | 转换/渲染流水线、原子写入、设计说明。 |
| [docs/viewer-internals.md](docs/viewer-internals.md) | 查看器播放模型、缓存布局、`prismax-viewer-serve` API。 |
| [docs/publishing.md](docs/publishing.md) | 将转换后的数据集上传至 Hugging Face Hub。 |
| [docs/development.md](docs/development.md) | 可编辑安装、仓库结构、故障排除、贡献指南。 |

---

## 安装

### 环境要求

- **Python** 3.10 或更高版本。
- **`ffmpeg`** 和 **`ffprobe`** 已配置到 `PATH`（转换和渲染必需）。SDK 自动检测 NVIDIA NVENC/NVDEC，若不可用则透明回退至 CPU（libx264）。
- **OpenGL / EGL** 系统库（visualization 扩展所需）。
- **可用的显示环境（X11 或 Wayland）**（`viewer` 扩展所需）。

在 Debian/Ubuntu 上：

```bash
sudo apt install ffmpeg libegl1 libgl1
```

### 安装方式

SDK 提供可选的依赖分组，按需安装即可。PyPI 发布版本在规划中；在此之前，请从源代码安装：

```bash
git clone https://github.com/PrismaXAI/prismax-python
cd prismax-python

# 核心功能：数据集下载 + MCAP→LeRobot 转换。
pip install ./prismax

# 添加 3D 可视化支持（pyrender、trimesh、yourdfpy、pillow）。
pip install './prismax[visualize]'

# 添加交互式 LeRobot 数据集查看器（PyQt6、pyqtgraph、PyAV）。
pip install './prismax[viewer]'

# 添加内置 URDF + 网格数据（当前支持：PiperX）。
pip install ./prismax-robots

# 从源代码安装所有功能：
pip install ./prismax-robots './prismax[all]'
```

| 扩展 | 新增内容 | 适用场景 |
|------|---------|---------|
| *(无)* | — | `download`、`convert`、`prismax-viewer-serve` |
| `visualize` | pyrender、trimesh、yourdfpy、pillow | `visualize` 命令及 `prismax.visualize` |
| `viewer` | PyQt6、pyqtgraph、PyAV、httpx | `prismax-viewer` GUI（本地 + SSH 远程） |
| `robots` | `prismax-robots` 数据包 | `--robot` 短名称查找 |
| `all` | `visualize` + `viewer` + `robots` | 完整功能集 |
| `dev` | pytest | 运行测试套件 |

---

## 登录prismax-cli downloadpkg_5jp2OIxaMNK5PIhWywsElBGi

`prismax-cli download` 支持本地 `manifest.json` 或 PrismaX `package_id`；使用 `package_id` 需要 API Token。一次性保存即可永久使用：

```bash
prismax-cli login              # 交互式提示；保存至磁盘
prismax-cli logout             # 删除已保存的 token
```

Token 保存在 `$XDG_CONFIG_HOME/prismax/credentials.json`，权限为 `0600`。每次执行需要认证的命令时，Token 的解析优先级如下：

1. 命令行参数 `--api-key <token>`，
2. `prismax-cli login` 保存的 token，
3. 环境变量 `PX_TOKEN`

```bash
(.venv) wanxin@Mac prismax-python % prismax-cli login 
PrismaX API token: /n
Saved API token to /Users/wanxin/.config/prismax/credentials.json

(.venv) wanxin@Mac prismax-python % prismax-cli logout
Removed /Users/wanxin/.config/prismax/credentials.jsonååå
```
---

## 命令行接口

安装 SDK 后会注册一个 `prismax-cli` 脚本，包含以下子命令：

```bash
prismax-cli --help
prismax-cli --version

prismax-cli login                                        # 保存 API token
prismax-cli logout                                       # 删除已保存的 token
prismax-cli download  <manifest|package_id> --root <dir>
prismax-cli convert   --root <mcap_dir> --out <lerobot_dir> [flags]
prismax-cli visualize --root <lerobot_dir> --episode <n>
                      (--urdf <path> | --robot <name>) [flags]
```

`python -m prismax.cli …` 等价于已安装的脚本。

### `download`

下载数据集的 MCAP 文件及每个片段的相机视频。

```bash
# 旧方式：使用本地 manifest.json。
prismax-cli download manifest.json --root my_dir

# 推荐方式：使用 PrismaX package_id（需要已保存的 token）。
prismax-cli download pkg_icbeps1twsw_MaFbHlVx2R19 --root my_dir
```

下载支持**断点续传**、**完整性校验**（通过 `x-goog-hash` 响应头进行 MD5 校验）以及**中断安全**（`SIGINT` 信号会在退出前删除正在下载的 `.part` 临时文件）。

### `convert`

将 MCAP 数据集目录转换为 LeRobot v2.1 格式。

```bash
prismax-cli convert --root mcap_dataset --out lerobot_out \
    [--fps 30] [--width 640] [--height 480] \
    [--robot-type dual_arm] \
    [--clean] \
    [--hardware-encoder auto|true|false] \
    [--nvenc-preset p4] [--nvenc-cq 23] \
    [--chunk SECONDS] [--chunk-mode fixed|adaptive]
```

主要参数说明：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--fps` | `30` | 目标视频帧率（重采样的主时钟）。 |
| `--width` / `--height` | `640` / `480` | 重新编码的视频分辨率，必须为偶数。 |
| `--robot-type` | `dual_arm` | 存储在 `meta/info.json` 中。 |
| `--clean` | 关闭（续写） | 写入前清空输出目录。 |
| `--hardware-encoder` | `auto` | `auto` 自动检测 NVENC；`true` 强制要求；`false` 强制使用 libx264。 |
| `--nvenc-preset` | `p4` | NVENC 速度/质量预设。 |
| `--nvenc-cq` | `23` | NVENC 恒定质量值（0–51）。 |
| `--chunk` | 关闭（一对一） | 将每个源 MCAP 拆分为多个时长不超过 `SECONDS` 秒的 LeRobot 片段。 |
| `--chunk-mode` | `fixed` | 分段边界的放置策略（见下文），需配合 `--chunk` 使用。 |

#### 片段分割（Episode Chunking）

默认情况下，每个源 MCAP 对应一个 LeRobot 片段。使用 `--chunk N` 可将长录制拆分为较短的子片段，适用于对超长片段处理困难的训练框架。

通过 `--chunk-mode` 可选择两种边界放置策略：

* **`fixed`**（默认）—— 按 `--chunk` 秒的倍数放置边界，针对边缘情况有三种兜底逻辑：
  1. 短于一个分块的片段直接作为单个片段输出。
  2. 时长在 `N` 到 `4*N` 秒之间的片段，拆分为 2–4 个近似等长的分块（避免因余数过小产生零碎片段）。
  3. 对于长片段，若末尾不足 10 秒，则合并到上一个分块，确保不输出低于 10 秒的片段。

  分块索引在使用相同 `--chunk` 值重复运行时保持稳定（支持断点续写）。

* **`adaptive`**（自适应）—— 目标分块长度相同，但将各内部边界对齐到**双臂均静止**的时刻，使切割点落在自然停顿处（如子任务之间），而非动作进行中。

  对于每个理想切割点（`i * --chunk` 秒处），规划器在其前后 `±--chunk/2` 秒范围内搜索静止片段；若找到，则将切割点置于该片段的中点，否则回退到理想切割点。末尾过短合并规则同样适用。

  静止判断基于跟随（观测）关节轨迹：计算 12 个非夹爪关节（夹爪单位与弧度不同且易产生微抖动）每帧的最大角速度，通过对逐帧位置数值微分获得。由于源 MCAP 中不存储速度数据，速度在运行时估算。静止状态需持续至少 0.5 秒才被计入。速度阈值对每个片段自动调整（第 20 百分位 × 1.5，限制在 `[0.01, 0.20] rad/s` 范围内），以适应不同速度的任务。

  自适应模式需提前解析整个 MCAP（规划切割点前需要获取完整关节轨迹），因此不支持跳过解析的快速续写路径；已输出的子片段仍会被跳过。在同一输出目录上更改 `--chunk` 或 `--chunk-mode` 可能导致现有分块失效；此时片段长度不匹配的警告会提示使用 `--clean` 重新运行。

  ```bash
  # 目标 60 秒分块，尽可能对齐到自然停顿。
  prismax-cli convert --root mcap_dataset --out lerobot_out \
      --chunk 60 --chunk-mode adaptive
  ```

### `visualize`

将单个片段渲染为 URDF 网格根据记录的关节状态驱动动画的 MP4 视频。

```bash
# 使用内置机器人（推荐——无需管理文件系统路径）。
prismax-cli visualize --root lerobot_out --episode 0 --robot piperx

# 使用自定义 URDF。
prismax-cli visualize --root lerobot_out --episode 0 \
    --urdf path/to/your_robot.urdf
```

`--urdf` 和 `--robot` **互斥**，二者必须指定其一。若使用 `--robot <name>` 但未安装 `[robots]` 扩展，`prismax-cli` 将以非零状态退出并输出一行安装提示，不显示完整错误堆栈。

可选渲染参数：

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--out` | 自动命名 | 输出 MP4，默认：`<dataset>--<ep>--<urdf>.mp4`。 |
| `--fps` | `30` | 输出视频帧率。 |
| `--width` / `--height` | `960` / `540` | 渲染分辨率。 |
| `--source` | `observation.state` | 回放的数据列（`observation.state` 或 `action`）。 |
| `--stride` | `1` | 帧采样间隔（大于 `1` 可用于快速预览）。 |
| `--max-frames` | 不限制 | 限制渲染的最大帧数。 |

---

## 端到端示例

```bash
# (1) 下载——若已有本地 MCAP 文件可跳过此步骤。
prismax-cli login
prismax-cli download pkg_icbeps1twsw_MaFbHlVx2R19 --root 10_Assemble_and_mix_salad

# (2) 转换。
prismax-cli convert --root 10_Assemble_and_mix_salad/<task_name> --out lerobot_out --clean

# (3) 使用内置 PiperX 机器人描述渲染第 0 个片段。
prismax-cli visualize \
    --root    lerobot_out \
    --episode 0 \
    --robot   piperx \
    --out     episode_0.mp4
```

如需将转换后的数据集发布至 Hugging Face Hub，请参阅 [docs/publishing.md](docs/publishing.md)。

---

## LeRobot 数据集查看器（GUI）

`viewer` 扩展会添加一个 `prismax-viewer` 控制台脚本，用于在 Linux 上启动交互式 Qt GUI，以探索 LeRobot v2.1 数据集。查看器可同步播放片段视频（最多三路并排）与实时状态/动作图表，让你无需进行完整 3D 渲染即可直观检查每条录制。查看器还支持通过 SSH 打开远程 Linux 机器上的数据集，在本地缓存元数据和已下载的片段，使后续打开无需重新传输数据。

```bash
pip install './prismax[viewer]'
```

此命令会安装 PyQt6、pyqtgraph、PyAV 和 httpx。仅需要 `download`、`convert` 或 `prismax-viewer-serve` 的无头/无 GUI 主机无需安装这些依赖。

### 本地数据集

```bash
# 从磁盘打开数据集。
prismax-viewer /path/to/lerobot_dataset

# 自动选择第 N 个片段（从 0 开始的显示索引）。
prismax-viewer --episode 5 /path/to/lerobot_dataset

# 不指定路径时，查看器打开并显示"打开数据集"对话框。
prismax-viewer

# 等价的模块调用方式。
python -m prismax.viewer /path/to/lerobot_dataset
```

若任何 GUI 依赖缺失，脚本将以非零状态退出，并输出一行指向 `pip install 'prismax[viewer]'` 的提示，不显示完整错误堆栈。

### 通过 SSH 访问远程数据集

查看器支持打开位于远程 Linux 机器上的 LeRobot 数据集，无需在远程端预先安装任何内容。传入 `--ssh [USER@]HOST --root /path/to/dataset`，查看器会自动在远程部署一个轻量（约 200 KB）的纯标准库 HTTP 服务器，通过现有 SSH 连接将其回环端口转发到本地，然后建立连接。认证使用你现有的 SSH 配置——密钥、`~/.ssh/config`、代理、跳板机、自定义身份文件等均保持正常工作。

```bash
# 密钥认证（或默认 ~/.ssh/config），用户名默认为当前用户。
prismax-viewer --ssh research-box --root /data/lerobot/2026-01-task

# 指定远程用户名。
prismax-viewer --ssh user@research-box --root /data/lerobot/2026-01-task

# 自定义 SSH 端口（默认 22）。
prismax-viewer --ssh user@host --port 2222 --root /data/10_Assemble_and_mix_salad

# 从文件读取密码（适用于脚本化启动）。
prismax-viewer --ssh-password-file /run/secrets/ssh_pw \
               --ssh user@host --root /data/10_Assemble_and_mix_salad

# 传入额外 SSH 选项（身份文件、跳板机等）。
prismax-viewer --ssh user@host --root /data/10_Assemble_and_mix_salad \
               --ssh-option IdentityFile=~/.ssh/research_ed25519 \
               --ssh-option ProxyJump=bastion
```

引导过程在**终端**中显示——每个步骤一行进度信息——SSH 连接建立后才会打开 GUI 窗口。认证失败时，查看器会通过 `getpass` 在终端中提示输入密码（不回显），最多重试三次。

SSH 相关参数：

| 参数 | 说明 |
|------|------|
| `--ssh [USER@]HOST` | 在远程机器上打开数据集，USER 默认为当前用户。 |
| `--root /path` | 远程数据集根目录（与 `--ssh` 配合使用时必填）。 |
| `--port N` | SSH 端口（默认 `22`）。 |
| `--ssh-option key=value` | 额外的 `ssh -o key=value` 选项，可重复使用。 |
| `--bootstrap {auto,zipapp,pip,system}` | 远程安装策略（默认：`auto` = zipapp）。 |
| `--ssh-password-file PATH` | 从 `PATH` 读取 SSH 密码（否则在终端中提示输入）。 |

远程服务器为**只读**、**仅监听回环地址**、**Bearer Token 认证**，并在闲置 10 分钟后自动退出。完整的引导序列、缓存布局及 HTTP API 说明请参阅 [docs/viewer-internals.md](docs/viewer-internals.md)。

你也可以通过直接传入 URL 来打开已在运行的 `prismax-viewer-serve` 实例（详见 [docs/viewer-internals.md](docs/viewer-internals.md)）：

```bash
PRISMAX_VIEWER_TOKEN=…  prismax-viewer http://lab-server.lan:8080/
# 或
prismax-viewer --token-file /run/secrets/viewer_token \
               http://lab-server.lan:8080/
```

---

## 许可证

MIT。许可证文本声明在各发行版的 `pyproject.toml` 文件中，适用于本仓库的所有代码。
