# MCAP 数据完整分析报告

## 📋 报告概览

**生成时间**: 2026-02-02  
**数据来源**: `/QA_PrismaX/Feature_CaseDesign/4_Mcap Data/output-20260129/`  
**分析工具**: parse_mcap.py v1.0  
**数据集数量**: 3个 (0.mcap, 50.mcap, 100.mcap)

---

## 📊 数据集对比总览

| 数据集 | 文件大小 | 消息总数 | 通道数 | 记录时长 | 开始时间 | 结束时间 |
|--------|----------|----------|--------|----------|----------|----------|
| **0.mcap** | 3.21 MB | 41,503 | 7 | 215.03秒 (3.58分钟) | 2026-01-29 14:42:55 | 2026-01-29 14:46:30 |
| **50.mcap** | 1.16 MB | 14,535 | 7 | 74.70秒 (1.25分钟) | 2026-01-29 17:40:31 | 2026-01-29 17:41:46 |
| **100.mcap** | 0.61 MB | 7,483 | 7 | 38.31秒 (0.64分钟) | 2026-01-29 21:14:32 | 2026-01-29 21:15:10 |

### 数据集特点

- **0.mcap**: 最大的数据集，记录时长最长，适合完整的操作流程分析
- **50.mcap**: 中等规模数据集，时长约为 0.mcap 的 1/3
- **100.mcap**: 最小的数据集，记录时长最短，可能是快速测试或特定操作片段

---

## 🔍 数据集详细分析

### 1️⃣ 0.mcap 详细信息

#### 基本信息
- **文件路径**: `output-20260129/0.mcap`
- **文件大小**: 3.21 MB
- **消息总数**: 41,503 条
- **通道数量**: 7 个
- **Schema 数量**: 2 个
- **记录时长**: 215.03 秒 (3分35秒)
- **录制时间段**: 2026-01-29 14:42:55 → 14:46:30

#### 数据通道明细

##### 机器人手臂关节状态通道

| 通道名称 | 消息编码 | 消息数量 | 平均帧率 | 平均大小 | 总数据量 |
|---------|---------|----------|----------|----------|----------|
| `/robot/arm_left_lead/joint_states` | CDR | 10,375 | 48.26 fps | 0.21 KB | 2.18 MB |
| `/robot/arm_left_follow/joint_states` | CDR | 10,375 | 48.26 fps | 0.32 KB | 3.28 MB |
| `/robot/arm_right_lead/joint_states` | CDR | 10,375 | 48.26 fps | 0.21 KB | 2.18 MB |
| `/robot/arm_right_follow/joint_states` | CDR | 10,375 | 48.26 fps | 0.32 KB | 3.28 MB |

**说明**:
- 左右手臂各有两个控制通道（lead 和 follow）
- 采样率稳定在 ~48 Hz，提供流畅的关节状态数据
- follow 通道数据略大（0.32 KB vs 0.21 KB），可能包含更多反馈信息

##### 摄像头信息通道

| 通道名称 | 消息编码 | 消息数量 | 平均大小 | 说明 |
|---------|---------|----------|----------|------|
| `/robot/left_camera/image_raw/compressed/camera_info` | CDR | 1 | 0.35 KB | 左摄像头参数（单次发送）|
| `/robot/env_camera/image_raw/compressed/camera_info` | CDR | 1 | 0.35 KB | 环境摄像头参数（单次发送）|
| `/robot/right_camera/image_raw/compressed/camera_info` | CDR | 1 | 0.35 KB | 右摄像头参数（单次发送）|

**说明**:
- 这些通道只包含摄像头的校准参数（内参、畸变参数等）
- 实际图像数据存储在对应文件夹的 MP4 视频文件中
- 每个摄像头只发送一次参数信息

#### 配套视频文件

文件夹 `0/` 包含三个摄像头的视频：
- `robot.env_camera.color.image_raw.mp4` - 环境视角
- `robot.left_camera.color.image_raw.mp4` - 左侧视角
- `robot.right_camera.color.image_raw.mp4` - 右侧视角

---

### 2️⃣ 50.mcap 详细信息

#### 基本信息
- **文件路径**: `output-20260129/50.mcap`
- **文件大小**: 1.16 MB
- **消息总数**: 14,535 条
- **通道数量**: 7 个
- **Schema 数量**: 2 个
- **记录时长**: 74.70 秒 (1分15秒)
- **录制时间段**: 2026-01-29 17:40:31 → 17:41:46

#### 数据通道明细

##### 机器人手臂关节状态通道

| 通道名称 | 消息数量 | 平均帧率 | 相比 0.mcap |
|---------|----------|----------|-------------|
| `/robot/arm_left_lead/joint_states` | 3,631 | ~48.6 fps | 35% 数据量 |
| `/robot/arm_left_follow/joint_states` | 3,631 | ~48.6 fps | 35% 数据量 |
| `/robot/arm_right_lead/joint_states` | 3,631 | ~48.6 fps | 35% 数据量 |
| `/robot/arm_right_follow/joint_states` | 3,631 | ~48.6 fps | 35% 数据量 |

**说明**:
- 采样率保持一致（~48 Hz）
- 时长约为 0.mcap 的 1/3
- 数据结构完全相同

##### 摄像头信息通道

与 0.mcap 结构相同，每个摄像头各 1 条参数消息。

#### 配套视频文件

文件夹 `50/` 包含对应的三个摄像头视频文件。

---

### 3️⃣ 100.mcap 详细信息

#### 基本信息
- **文件路径**: `output-20260129/100.mcap`
- **文件大小**: 0.61 MB
- **消息总数**: 7,483 条
- **通道数量**: 7 个
- **Schema 数量**: 2 个
- **记录时长**: 38.31 秒 (38秒)
- **录制时间段**: 2026-01-29 21:14:32 → 21:15:10

#### 数据通道明细

##### 机器人手臂关节状态通道

| 通道名称 | 消息数量 | 平均帧率 | 相比 0.mcap |
|---------|----------|----------|-------------|
| `/robot/arm_left_lead/joint_states` | 1,868 | ~48.8 fps | 18% 数据量 |
| `/robot/arm_left_follow/joint_states` | 1,868 | ~48.8 fps | 18% 数据量 |
| `/robot/arm_right_lead/joint_states` | 1,868 | ~48.8 fps | 18% 数据量 |
| `/robot/arm_right_follow/joint_states` | 1,868 | ~48.8 fps | 18% 数据量 |

**说明**:
- 最短的数据集，约 38 秒
- 采样率依然稳定在 ~48 Hz
- 适合快速测试或特定动作片段

##### 摄像头信息通道

与前两个数据集结构相同。

#### 配套视频文件

文件夹 `100/` 包含对应的三个摄像头视频文件。

---

## 🎯 所有通道汇总

所有三个数据集包含相同的 7 个数据通道：

### 1. 机器人控制通道（4个）

1. **`/robot/arm_left_lead/joint_states`**
   - 左臂主控制器关节状态
   - 高频采样（~48 Hz）
   - 包含位置、速度、力矩等信息

2. **`/robot/arm_left_follow/joint_states`**
   - 左臂从控制器关节状态
   - 跟随主控制器的反馈数据
   - 数据包略大，包含更多反馈信息

3. **`/robot/arm_right_lead/joint_states`**
   - 右臂主控制器关节状态
   - 与左臂对称的控制结构

4. **`/robot/arm_right_follow/joint_states`**
   - 右臂从控制器关节状态
   - 提供右臂的反馈控制数据

### 2. 视觉传感器通道（3个）

5. **`/robot/left_camera/image_raw/compressed/camera_info`**
   - 左侧摄像头校准参数
   - 包含：相机内参矩阵、畸变系数、投影矩阵等

6. **`/robot/env_camera/image_raw/compressed/camera_info`**
   - 环境摄像头校准参数
   - 用于整体场景观察

7. **`/robot/right_camera/image_raw/compressed/camera_info`**
   - 右侧摄像头校准参数
   - 与左摄像头配合实现立体视觉

---

## 📈 数据质量评估

### ✅ 优点

1. **采样率稳定**: 所有数据集的关节状态采样率都稳定在 ~48 Hz
2. **数据完整**: 三个数据集结构完全一致，无缺失通道
3. **多视角覆盖**: 三个摄像头提供环境、左、右三个视角
4. **双臂控制**: 支持左右双臂独立控制和协同操作
5. **主从架构**: Lead/Follow 架构提供更好的力控制和安全性

### ⚠️ 注意事项

1. **图像数据独立**: MCAP 文件不包含实际图像数据，需配合 MP4 视频使用
2. **摄像头参数**: camera_info 只在开始时发送一次，需要单独保存
3. **时间同步**: MCAP 中的关节数据和 MP4 视频需要通过时间戳同步

---

## 💡 使用建议

### 数据分析场景

| 场景 | 推荐数据集 | 说明 |
|------|-----------|------|
| 完整操作流程分析 | 0.mcap | 最长时长，数据最完整 |
| 快速验证测试 | 100.mcap | 最短时长，快速加载 |
| 中等规模分析 | 50.mcap | 平衡数据量和时长 |

### 数据提取方法

#### 1. 提取关节状态数据

```python
from parse_mcap import extract_messages_by_topic

# 提取左臂主控制器数据
messages = extract_messages_by_topic(
    "0.mcap",
    topic_filter=["/robot/arm_left_lead/joint_states"]
)
```

#### 2. 查看摄像头参数

```bash
# 使用 mcap-cli
mcap cat 0.mcap --topics /robot/left_camera/image_raw/compressed/camera_info
```

#### 3. 同步视频和关节数据

- MCAP 提供精确时间戳（纳秒级）
- MP4 视频提供视觉信息
- 通过时间戳对齐进行多模态分析

### 典型分析任务

1. **轨迹回放**: 使用关节状态数据重现机器人运动
2. **性能评估**: 分析采样率、延迟、数据完整性
3. **视觉定位**: 结合摄像头参数和视频进行3D重建
4. **异常检测**: 检查关节状态的异常值或突变
5. **协同分析**: 分析左右臂的协同操作模式

---

## 🛠️ 技术规格

### 数据编码

- **格式**: CDR (Common Data Representation)
- **标准**: ROS 2 DDS 消息格式
- **压缩**: 使用 LZ4 和 Zstandard 压缩

### Schema 信息

数据集包含 2 个 Schema：
- **Schema 1**: JointState 消息（关节状态）
- **Schema 2**: CameraInfo 消息（摄像头参数）

### 时间精度

- 时间戳单位：纳秒 (nanoseconds)
- 时间精度：亚毫秒级
- 适合高精度时序分析

---

## 📞 相关资源

### 分析工具

- `parse_mcap.py` - 完整分析脚本
- `quick_view.py` - 快速查看工具
- `run_demo.sh` - 交互式演示脚本

### 依赖库

```bash
pip install mcap>=1.0.0
pip install opencv-python>=4.8.0  # 图像处理（可选）
pip install numpy>=1.24.0
```

### 可视化工具

- [Foxglove Studio](https://foxglove.dev/) - 推荐的 MCAP 可视化工具
- [PlotJuggler](https://github.com/facontidavide/PlotJuggler) - 时序数据可视化
- mcap-cli - 命令行工具

---

## 📝 结论

三个 MCAP 数据集提供了不同时长的机器人操作数据，包含：

- ✅ 完整的双臂关节状态数据（~48 Hz 高频采样）
- ✅ 三个摄像头的校准参数
- ✅ 配套的视频数据（MP4 格式）
- ✅ 纳秒级精确时间戳

数据质量良好，采样率稳定，结构完整，适合用于：
- 机器人控制算法验证
- 轨迹分析和优化
- 视觉伺服研究
- 人机交互分析
- 故障诊断和性能评估

---

**报告生成者**: MCAP 数据解析工具 v1.0  
**脚本位置**: `/QA_PrismaX/McapData/`  
**数据位置**: `/QA_PrismaX/Feature_CaseDesign/4_Mcap Data/output-20260129/`
