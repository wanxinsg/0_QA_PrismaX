# `teleop-data-collection-package` 逻辑分析

> 分析日期：2026-10-16（UTC+8）  
> 分析范围：`teleop-data-collection-package/` 当前代码  
> 包名：`yam-data-collection`  
> Python 入口：`yam-data-collect = yam_data_collection.cli:main`

---

## 1. 一句话总结

这是一个用于双臂 YAM 遥操作的数据采集包：它**不直接操作 CAN 和机械臂**，而是从 4 个既有 `i2rt/minimum_gello.py` 进程读取只读 Portal 遥测，同时独立采集 3 路 RealSense 彩色视频，按 episode 写成：

- 一个 MCAP：保存任务信息、4 路关节状态、3 路相机 `CameraInfo` 和相机时间诊断；
- 三个 MP4：保存 `cam_high`、`cam_left`、`cam_right` 的真实图像；
- 一份 `record_config.yaml`：保存采集时使用的配置和模式。

它的核心设计不是“尽量多录”，而是**发现丢帧、队列溢出、遥测停滞或时间异常时 fail closed，拒绝把不可信的 episode 当成正常数据发布**。

---

## 2. 系统边界

```text
4 个 i2rt 机械臂进程                     3 台 RealSense
(CAN 的唯一 owner)                       D435 + D405 + D405
        │                                         │
        │ Portal get_telemetry()                  │ librealsense frame queue
        ▼                                         ▼
4 路 RobotSnapshot                       3 个独立 CameraWorker
        │                                         │
        ├──────────────┐             ┌────────────┤
        ▼              ▼             ▼            ▼
  180 Hz 状态采样   时间连续性检查   CameraInfo   FFmpeg 实时编码
        │              │             │            │
        └──────────────┴──────┬──────┴────────────┘
                              ▼
                         一个 episode
                    MCAP + 3 个 live MP4
                              │
                   完整性校验、关闭、发布
                              │
              ┌───────────────┴────────────────┐
              ▼                                ▼
       H.264 final 配置                  HEVC final 配置
       采集后直接发布                    保留 pending
              │                                │
              ▼                                ▼
      <dataset>/<id>.mcap             离线 transcode 成 HEVC
      videos/<id>/*.mp4                         │
                                                ▼
                                      <dataset>/<id>.mcap
                                      videos/<id>/*.mp4
```

职责边界：

- `i2rt` 负责真实机械臂/CAN 控制，并通过 Portal 暴露最新状态；本包只读，不会争抢 CAN。
- 本包负责采集、时间戳、编码、MCAP 组织、质量门禁、发布和离线修复。
- 图像像素不写入 MCAP；MCAP 里的每条相机消息是与 MP4 帧一一对应的 `CameraInfo`。
- Preview 和 Web UI 是 best-effort 展示层，失败不应进入正式采集热路径。

---

## 3. 配置如何解析

`config.py` 将 YAML 解析为不可变配置对象，主要有五部分：

| 配置段 | 作用 |
| --- | --- |
| `collection_config` | dataset 路径、状态频率、episode 长度、编码参数、队列大小、CPU 亲和性、验证 profile |
| `telemetry` | 4 个机械臂角色各自的 Portal host/port |
| `cameras` | 3 个相机角色的 serial、frame id |
| `capture_modes` | `30hz` / `60hz` 对应的分辨率、FPS、intrinsics、dataset 子目录和验证 profile |
| `task_info` | 每个 episode 写入 `/task_info` 的任务元数据 |

正式模式有两个固定约束：

| 模式 | 相机目标 | 状态采样 | 默认验证 profile |
| --- | --- | --- | --- |
| `30hz` | 三路 30 Hz；分辨率由该配置的 mode 决定 | 180 Hz | `yam_30hz` |
| `60hz` | 三路 60 Hz；通常 D435 与 D405 分辨率不同 | 180 Hz | `yam_60hz` |

选择 `--mode` 后，loader 会把公共配置与对应 mode 合并，并把结果写到独立的 dataset 子目录。这样 30 Hz 和 60 Hz 不会共用 episode 编号或 `record_config.yaml`。

加载阶段还会拒绝错误角色、错误 FPS/profile 组合、不合法 codec/CRF/thread/CPU set、相机 serial 重复、尺寸或内参格式错误等配置。正式采集默认要求每台相机都有有效标定；`allow_uncalibrated_intrinsics: true` 只用于 smoke test。

---

## 4. 启动阶段

`EpisodeCollector.start()` 的顺序如下：

1. 应用 recorder CPU affinity；后续 Portal、RealSense 和 Python worker 继承此 CPU 集合。FFmpeg 子进程可单独绑定 `live_video_cpu_set`，两者要求不重叠。
2. 获取 dataset 操作锁，避免实时采集与离线转码/发布同时修改同一 dataset。
3. 建目录并写 `record_config.yaml`，记录最终解析后的 profile、频率和 capture mode。
4. 可选启动 runtime diagnostics，持续记录 CPU、内存、磁盘、温度、频率、队列和编码吞吐。
5. 并行读取 4 路 Portal，确认遥测可用。
6. 启动 3 台 RealSense；每台最多尝试 3 次，并要求能实际读到第一帧。
7. 为每台相机启动一个独立 `_CameraWorker`，避免串行读三台相机导致相互阻塞或失同步。
8. 用最近约 2 秒的帧检查三路相机 FPS 和最大 gap；不达标则不开放录制。
9. 对 4 路机械臂做约 1 秒的遥测连续性探测，检查 RPC 延迟、sequence、源时间戳和停滞。
10. 启动固定频率状态线程；此时处于 `IDLE`，相机与遥测持续运行，但不写 episode。

RealSense 时间戳优先使用 `global_time`。程序会等待启动帧完成时钟切换，并检查设备时间与 host time 的偏差及单调性；不能可靠使用 global time 时，整个 session 固定退回 `host_receive`，避免在同一段数据中混用两套时钟。

---

## 5. Episode 状态机

```text
                  Space
    IDLE ─────────────────────► ARMING
     ▲                            │
     │                            │ 2 秒满负载健康检查通过
     │                            ▼
     │                         RECORDING
     │                            │
     │            Enter / 达到 total_sampled_frames
     │                            ▼
     └────────────────────── FINALIZING

ARMING / RECORDING 中：
- q：放弃当前 episode
- 相机、遥测、MCAP、FFmpeg 或队列错误：自动放弃

close() 后进入 CLOSED。
```

按 Space 后并不会立即让操作者开始动作，而是先进入 `ARMING`：

- 创建 `.pending/<id>/<id>.partial.mcap`；
- 创建 `videos_live/<id>.partial/` 和三路异步 FFmpeg writer；
- 在真实的 3 路视频编码 + 4 路状态写入负载下运行 2 秒；
- 要求每路至少有足够帧、状态样本足够、队列深度低、pipe write 延迟可接受且无后台错误；
- 通过后才切换到 `RECORDING`，提示操作者开始遥操作。

此设计用于避免设备表面上已经启动，但在完整负载下马上掉帧或堵塞。

---

## 6. 关节状态采集逻辑

4 个角色固定为：

- `left_leader`
- `right_leader`
- `left_follower`
- `right_follower`

状态线程以 180 Hz 为目标循环。每次采样会：

1. 用线程池并行调用 4 个 Portal `get_telemetry()`；单个 RPC 默认 50 ms timeout，超时后重建 Portal client。
2. 验证每路 `sequence` 与 `source_timestamp_ns` 不倒退，并持续向前推进。
3. 检查本地采样 gap、机械臂源时间 gap 和时间戳停滞；运行时预算来自验证 profile：约为 joint-camera sync 阈值的 2 倍。
4. 向 MCAP 写 4 条 `JointState`。

时间戳语义非常重要：

| 字段 | 含义 |
| --- | --- |
| MCAP `log_time` | Collector 本次固定频率采样时间 |
| `JointState.header.stamp` | `i2rt` 真正读取硬件状态的源时间 |
| MCAP `publish_time` | 同样使用硬件源时间 |

因此，Portal RPC 即使晚到，也不会把一条旧状态伪装成“刚刚采到”的状态。正式 joint-camera sync 校验使用 `header.stamp`。

Leader 为保持 Piper 格式兼容，只写 position，velocity/effort 为空；Follower 必须写满 7 个 joint 的 position、velocity、effort。

### 推荐的 queued 版本

README 当前推荐通过 `scripts/capture_queued.py` 使用 `QueuedEpisodeCollector`。它和基础 `EpisodeCollector` 的协议相同，唯一关键差异是：

- 基础版：180 Hz 采样线程直接做 MCAP 序列化；
- queued 版：采样线程完成读取和时间检查后，把四臂 snapshot 放入容量 512 的 `_StateMcapWriter` 队列，由单独线程写 MCAP。

这样可以减少 MCAP 序列化对 180 Hz 调度的干扰。队列是有界的；满队列或 writer 失败会使 episode 失败，不会静默丢状态。

---

## 7. 相机和视频采集逻辑

每个相机有独立线程，帧到达 `_on_camera_frame()` 后按以下顺序处理：

1. 更新最近 2 秒的 arrival window，供下一次 preflight 使用。
2. 若当前为 `IDLE`，只送低频 preview，不写文件。
3. Episode 开始后，先等待第一组完整四臂状态成功写入；用四路状态中最早的源时间建立 `camera_start_timestamp_ns` watermark。
4. 丢弃在 watermark 之前就已进入 RealSense native queue 的旧帧，避免 episode 以“比全部关节状态更早”的图像开头。
5. 将图像放进该相机的 `AsyncFfmpegWriter` 有界队列。
6. 只有视频帧成功入队后，才向 MCAP 写一条同时间戳的 `CameraInfo`，并累加帧数与 timing diagnostics。

这个顺序保证：**每一条 CameraInfo 都对应一个被编码器接受的 MP4 帧**。如果视频队列满，整个 episode 失败，而不是只写 MCAP 或只丢视频帧。

YUYV 图像在 Python 中保持 packed buffer，交给 FFmpeg 原生转换和编码，减少 Python 侧 CPU 与内存复制。`owns_image=True` 时还能把已拥有的连续内存直接交给异步 writer。

保存时会额外把每帧的以下诊断批量写入 MCAP：capture time、host receive time、RealSense device time、device frame number、timestamp domain 和所选时钟来源。这些信息用于区分真实设备丢帧与 host 调度/回调延迟。

---

## 8. MCAP 内容

每个 episode 的 MCAP 至少包含：

| Topic/内容 | 数量与用途 |
| --- | --- |
| `/task_info` | 1 条 JSON 字符串，创建 writer 时立即写入 |
| 4 路 `JointState` | 目标 180 Hz，Piper-compatible topic 映射 |
| 3 路 `CameraInfo` | 每个被视频 writer 接受的帧写 1 条 |
| frame timing diagnostics | episode 结束时按相机写入的时间/帧号批量诊断 |

MCAP 不保存图像 bytes，这能让关节/任务元数据保持可快速读取，同时把高带宽视频交给标准 MP4 编码。

---

## 9. 保存、校验和发布

按 Enter 或达到 `total_sampled_frames` 后：

1. 从 active state 中 detach episode，进入 `FINALIZING`，阻止新 callback 继续拿到 writer。
2. 等待已经进入的相机/状态操作全部 drain。
3. queued 版本先 drain 状态写队列。
4. 写入相机 timing diagnostics，关闭 MCAP。
5. 依次关闭三个 FFmpeg writer；commit 失败时删除 partial 视频。
6. 把 partial MCAP/视频目录改名为完整的 pending/live 资产。
7. 校验 MCAP 可读，且每个 MP4 的可解码帧数严格等于对应 CameraInfo 数量。

之后按 final codec 分两条路径：

### 9.1 H.264-final

live H.264 本身就是最终资产，不再编码。验证通过后先原子移动完整视频目录到 `videos/<id>/`，再把 pending MCAP 移到 dataset 根目录。MCAP 最后发布，因此外部不会先看到一个缺视频的正式 episode。

### 9.2 HEVC-final

实时阶段只产出计算量较低的 H.264，保留在：

```text
<dataset>/.pending/<id>/<id>.mcap
<dataset>/videos_live/<id>/*.mp4
```

采集结束后由 `transcode` / `transcode-dataset` 串行转为 HEVC。转码先写私有 staging 目录，逐路核对 codec、分辨率和帧数，再先发布完整视频目录、最后发布根目录 MCAP。覆盖旧 episode 时会先备份旧的一整对资产，失败则 best-effort rollback。

Dataset lock 保证离线转码不会和实时采集并行争抢 CPU/磁盘或同时改目录。

---

## 10. 正式质量校验

`quality.py` 同时校验 MCAP 时序和外部 MP4。主要 mandatory checks 是：

- 三路相机平均 FPS；
- 单路相机最大 frame gap；
- 分辨率至少 640×480，strict profile 还要求精确匹配配置；
- 三路相机相互同步；
- 相机与四路关节状态同步；
- 每路关节平均频率高于 45 Hz；
- MP4 codec、尺寸、FPS 和可解码帧数；
- MP4 帧数严格等于 MCAP 对应相机的 CameraInfo 数量。

主要阈值：

| Profile | 平均相机频率 | 最大 gap | camera sync | joint-camera sync |
| --- | --- | --- | --- | --- |
| `yam_30hz` | 29.5–30.5 Hz | ≤ 69 ms | ≤ 34 ms | ≤ 34 ms |
| `yam_60hz` | 59.0–60.5 Hz | ≤ 69 ms | ≤ 17 ms | ≤ 17 ms |
| `piper_compatible` | 自动识别 15/30/60 Hz | ≤ 69 ms | ≤ 34 ms | ≤ 34 ms |
| `yam_60hz_strict` | 59.5–60.5 Hz | ≤ 35 ms | ≤ 17 ms | ≤ 17 ms |

需要区分两类 gate：

- **发布完整性 gate**：MCAP 必须可读，MP4 与 CameraInfo 帧数必须一致；不允许发布损坏或不成对的资产。
- **正式质量 gate**：FPS、gap、同步等是否达到 profile。基础 pipeline 会保留忠实但质量不通过的数据供诊断；当前推荐的 `capture_queued.py` 开启了 `auto_delete_failed_validation=True`，因此交互采集时正式验证失败的 episode 会自动删除并记录删除时长。

---

## 11. 失败和数据安全策略

以下问题会使 active episode 失败：

- 相机线程异常、无帧、时间戳不前进或 global time 异常；
- 视频队列溢出或 FFmpeg pipe/进程失败；
- Portal timeout、sequence/源时间倒退、状态长时间不推进；
- 状态采样 gap 或源状态 gap 超出运行时预算；
- MCAP 写入失败；
- queued 状态写队列溢出；
- finalization 或 live asset 完整性校验失败。

安全措施包括：

- 采集中先写 `.partial`，完成后才改名；
- 正式根目录 MCAP 是“episode 已发布”的最后标记；
- callback 使用 active-operation 引用计数，finalizer 等正在写的操作排空；
- 失败时清理 partial；如果已经形成完整 pending/live 文件但完整性校验失败，会保留供诊断，而不是误发布；
- overwrite 发布会备份旧完整资产，失败时回滚；
- 用户删除或自动删除会记录 episode 时长及原因：`validation_failed`、`recording_error`、`user_deleted`。

---

## 12. 辅助能力

| 模块/命令 | 作用 |
| --- | --- |
| `discover-cameras` | 按物理 serial 列出 RealSense，避免依赖不稳定的 `/dev/videoN` |
| `check` | 检查 Portal；可选实际启动相机读一帧 |
| `camera-test` | 不依赖机械臂/Portal/MCAP，单独验证 USB、固件、时序、编码和磁盘吞吐 |
| `web` | 仅绑定 loopback 的本地 Web 控制台，可启停 i2rt 和采集，并显示预览/状态 |
| `validate` / `validate-dataset` | 校验一个 episode 或整个 dataset |
| `experiment` | 在隔离 dataset 中做 CPU/USB/编码条件的 A/B/C 试验并输出环境与性能报告 |
| `repair-30hz` | 仅对满足严格条件的 30 Hz、device frame delta=3 dropout，复制前一帧生成独立衍生 dataset |
| `capture-auto-repair` | 保存后关闭输入，再串行尝试上述修复，然后重新启动采集 |
| `runtime_diagnostics` | 记录进程/系统 CPU、内存、NVMe、温度、频率和 writer 队列指标 |

30 Hz 修复不会改原始 MCAP/视频。它只在诊断信息完整且 dropout 模式明确时，对缺口插入“前一帧副本”，重写 CameraInfo/timing，重新编码视频，并在独立 derived dataset 写 manifest 与 hash。

---

## 13. 推荐运行链路

当前 README 推荐使用 queued collector：

```bash
# 先确认硬件和端点
uv run yam-data-collect discover-cameras
uv run yam-data-collect check --config config.yaml --mode 30hz --start-cameras

# 正式交互采集
taskset -c 16-23 .venv/bin/python scripts/capture_queued.py \
  --config config.yaml --mode 30hz

# 如果 final codec 是 HEVC，采集退出后串行转码
.venv/bin/yam-data-collect transcode-dataset \
  --config config.yaml --mode 30hz

# 校验整个正式 dataset
.venv/bin/yam-data-collect validate-dataset \
  --config config.yaml --mode 30hz /path/to/dataset
```

交互按键：

| 按键 | 行为 |
| --- | --- |
| Space | `IDLE` 时创建并 arm 新 episode；通过健康检查后开始 recording |
| Enter | 保存当前 recording episode |
| Space（保存审核时） | 保留刚保存的 episode，并立即开始下一段 |
| `q` | 录制中放弃；保存审核时删除刚保存的 episode |

---

## 14. 代码导航

| 文件 | 核心职责 |
| --- | --- |
| `yam_data_collection/cli.py` | 全部 CLI 入口和命令分发 |
| `config.py` | YAML 合并、模式解析、配置验证 |
| `collector.py` | 主状态机、启动检查、采集、finalization、错误处理 |
| `queued_collector.py` | 将关节状态 MCAP 写入移出 180 Hz 采样线程 |
| `telemetry.py` | Portal 只读 client、timeout/reconnect、payload 校验 |
| `cameras.py` | RealSense 启停、帧队列、时间戳和 pixel format |
| `mcap_writer.py` | Piper-compatible topic/schema 和时间戳写入 |
| `video.py` | 异步 FFmpeg writer、ffprobe、转码和插帧编码 |
| `video_pipeline.py` | pending、验证、原子发布、回滚、HEVC pipeline |
| `quality.py` | MCAP/视频检查和同步统计 |
| `validation_profiles.py` | 30/60 Hz/Piper 的正式阈值 |
| `offline_repair.py` | 30 Hz 特定 dropout 的非破坏性派生修复 |
| `camera_test.py` | 相机独立 qualification |
| `web_console.py` / `web_runtime.py` | 本地 Web UI、机械臂进程管理和 capture adapter |
| `experiment.py` | A/B/C 性能实验和报告 |
| `runtime_diagnostics.py` | 运行时主机及 writer 指标采样 |

---

## 15. 最终理解

这个 package 本质上是一条带事务语义的数据采集 pipeline：

1. 在录制前证明硬件和时间流健康；
2. 录制时让四臂状态、三路 CameraInfo 与三路 MP4 保持可验证的一一关系；
3. 任何实时过载或数据停滞都让整段失败，而不是悄悄缺样本；
4. 先生成 pending 资产并验证，再原子发布完整 episode；
5. 把高负载 HEVC 转码放到采集之后，避免影响实时数据；
6. 用独立 validation profile 明确 30 Hz、60 Hz 和 Piper compatibility 的验收标准。

所以它不仅是“录相机 + 存关节角”的脚本，更接近一个针对机器人训练数据设计的、可恢复且可审计的采集事务系统。
