# Scale AI Robotics Marketplace | Collection Requirements

**Purpose of this document:** Outline high-level data collection requirements for Scale's marketplace partners.

---

## Contents

1. [Target Embodiments](#target-embodiments)
2. [Collection Quality Criteria](#collection-quality-criteria)
3. [File Format](#file-format)

---

## Target Embodiments

### Bi-manual manipulators

- **Arms:** 5+ DOF arms, fixed baseline during recording
- **Base:** Static or mobile
- **End effectors:** 2-finger gripper (parallel jaw or finger), 3-finger gripper, or dextrous hand
- **RGB Cameras (+Depth):**
  - 2 RGB wrist cameras with gripper in view (one per end-effector)
  - 1–2 RGB cameras with both arms in view (e.g. ego, birds-eye, worms-eye)
- **Replayable trajectories** from commanded joint states

### Humanoids

(As applicable.)

### Embodiments we're open to but not proactively pursuing

- UMI-style grippers

---

## Collection Quality Criteria

| Criterion | Description |
|-----------|-------------|
| **Smoothness** | Demonstrations are continuous and fluid, avoiding unnecessary pauses |
| **Efficiency** | Tasks are performed in the minimum feasible time without unnecessary steps, while still meeting overall quality expectations |
| **Completeness** | Demonstrations clearly achieve the intended outcome of the task from start to finish |
| **Diversity** | Each episode contains a difference in embodiment, environment, scene arrangements/distractors, demonstration performed, objects used, manipulation approaches, or start/end configurations |
| **Consistency** | For the same task, speeds should be consistent when following the same trajectory |
| **Field of view** | Task actions are clearly visible within the camera view |
| **Non-robot actions** | Demonstrations use motions that are natural and realistic for the robot, avoiding actions that a robot could not reasonably perform |
| **No sensitive information** | Demonstrations do not contain any confidential or proprietary information |

---

## File Format

> **Note:** Accommodating the varied model training pipelines of Scale's Marketplace customers requires us to collect a comprehensive representation of the scene at collection time. This will require intrinsic and extrinsic camera calibration, localization of arms in relation to each other and each camera, and odometry when collection is mobile.

To ingest data from our data partners, we require an **MCAP** with the following topics:

### Image Topic

- Each image should have a timestamp
- Images should be compressed

### CameraInfo Topic

- Includes camera intrinsic information for each camera
- Could be published alongside image topics, or as a separate metadata file

### JointState Topic

- For every arm in the scene, both follower and leader if applicable
- **Controller input:** If teleoperation is leader-follower with identical arms, controller inputs should come as separate JointState topics per arm. If leader-follower with different kinematically equivalent arms, or not leader-follower, provide a topic with the output from the controller used (VR, GELLO, etc.)

### Commanded Output

- If not directly mirroring JointStates, we require commanded JointStates as an output of your control schema

### tf2

- A full TF tree of each arm
- A full TF tree for each controller output
- A tf message for any mobile manipulator base (odometry)

### tf_static

- A single message describing the physical position of each arm and camera in relation to a static point
- Includes relationship between mobile manipulator base and robot base when appropriate

### robot_description

- A URDF which comprehensively defines the kinematics of the robot, inclusive of the end effector

---

*Confidential | ©2025 Scale Inc.*

---

# 中文

# Scale AI 机器人市场 | 数据采集要求

**文档目的：** 概述 Scale 市场合作伙伴的高层数据采集要求。

---

## 目录

1. [目标形态](#目标形态-1)
2. [采集质量准则](#采集质量准则-1)
3. [文件格式](#文件格式-1)

---

## 目标形态

### 双臂操作机器人

- **机械臂：** 5+ 自由度，录制期间固定基线
- **底座：** 固定式或移动式
- **末端执行器：** 二指夹爪（平行夹爪或手指式）、三指夹爪或灵巧手
- **RGB 相机（可选深度）：**
  - 2 个腕部 RGB 相机，夹爪在视野内（每个末端执行器一个）
  - 1–2 个 RGB 相机，双臂均在视野内（如第一人称、俯视、仰视）
- **可回放轨迹** 来自指令关节状态

### 人形机器人

（按适用情况填写。）

### 可接受但非主动推进的形态

- UMI 式夹爪等

---

## 采集质量准则

| 准则 | 说明 |
|------|------|
| **平滑性** | 示教连续流畅，避免不必要的停顿 |
| **效率** | 在满足整体质量的前提下，以最短可行时间完成任务，无多余步骤 |
| **完整性** | 示教从始至终清晰达成任务目标 |
| **多样性** | 每段数据在形态、环境、场景布置/干扰物、示教方式、使用物体、操作方式或起止配置上有所差异 |
| **一致性** | 同一任务下，沿相同轨迹时速度应保持一致 |
| **视野** | 任务动作在相机视野内清晰可见 |
| **非机器人动作** | 示教使用对机器人而言自然、真实的动作，避免机器人难以合理执行的动作 |
| **无敏感信息** | 示教不包含任何机密或专有信息 |

---

## 文件格式

> **说明：** 为适配 Scale 市场客户多样化的模型训练流程，我们需在采集时获得场景的完整表示。这需要相机内参与外参标定、各臂相对彼此及各相机的位置、以及移动采集时的里程计。

为接入合作伙伴数据，我们要求提供符合以下主题的 **MCAP** 文件：

### 图像主题 (Image Topic)

- 每张图像需带时间戳
- 图像需为压缩格式

### 相机信息主题 (CameraInfo Topic)

- 包含每台相机的内参
- 可与图像主题一起发布，或作为独立元数据文件

### 关节状态主题 (JointState Topic)

- 场景中每条机械臂均需提供（若有从臂/主臂则均需）
- **控制器输入：** 若遥操作为主从式且双臂相同，控制器输入应以每条臂独立的 JointState 主题提供；若主从臂运动学等效但形态不同，或非主从式，需提供所用控制器（VR、GELLO 等）输出的主题

### 指令输出 (Commanded Output)

- 若非直接镜像 JointState，需提供作为控制架构输出的指令 JointState

### tf2

- 每条臂的完整 TF 树
- 每个控制器输出的完整 TF 树
- 移动操作底座（若有）的 TF 消息（里程计）

### tf_static

- 一条消息描述每条臂与每台相机相对于固定参考点的物理位置
- 若适用，包含移动操作底座与机器人底座的相对关系

### robot_description

- 一份完整定义机器人运动学（含末端执行器）的 URDF

---

*机密 | ©2025 Scale Inc.*
