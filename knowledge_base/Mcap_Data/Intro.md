# MCAP Data 简介（LeRobot 场景）

本文档用于说明在 LeRobot / 机器人数据集语境下的 **MCAP（.mcap）数据**：它是什么、在可视化界面里各元素对应什么数据、`state`/`action` 的含义，以及如何做 demo 数据质量检查。

> 说明：这里的 MCAP 指 **机器人日志格式**，不是金融里的市值（Market Cap）。

---

## 目录

- [1. MCAP 是什么](#1-mcap-是什么)
- [2. LeRobot 可视化内容与 MCAP 的映射](#2-lerobot-可视化内容与-mcap-的映射)
- [3. state 与 action（核心概念）](#3-state-与-action核心概念)
- [4. 为什么选 MCAP（与其他格式对比）](#4-为什么选-mcap与其他格式对比)
- [5. Demo 数据质量检查清单](#5-demo-数据质量检查清单)
- [6. 工程师打分法（快速决策）](#6-工程师打分法快速决策)

---

## 1. MCAP 是什么

**MCAP** 是一种面向机器人与多传感器的日志文件格式，常用于保存多模态时序数据，例如：

- 机器人实验数据（episode / trajectory）
- 相机图像（RGB / depth）
- 关节状态（joint states）
- 控制指令（actions / control signals）
- 强时间戳对齐的多 topic 数据

在实践中可以把它理解为“更适合 ML 数据管线的下一代 bag 容器格式”。

---

## 2. LeRobot 可视化内容与 MCAP 的映射

在 LeRobot 的数据可视化界面里，常见元素通常对应 MCAP 内的不同 topic 或 metadata：

### 2.1 多路相机画面（camera topics）

示例（不同数据集命名可能略有差异）：

```text
base_0_rgb
left_wrist_0_rgb
right_wrist_0_rgb
```

### 2.2 Language instruction（episode 级标注/元数据）

示例：

```text
anonymous task
```

这类字段通常是 episode 级 annotation/metadata（可能在 MCAP topic 中，也可能在索引/外部元数据里）。

### 2.3 关节曲线（state / actions）

示例（关节/自由度名称以具体机器人为准）：

```text
left_waist
left_shoulder
left_elbow
left_forearm_roll
left_wrist_angle
left_wrist_rotate
```

每条曲线常见会同时展示：

- `state`：真实测量到的关节状态（observation）
- `actions`：下发给控制器的控制指令（policy 输出 / 人操轨迹）

---

## 3. state 与 action（核心概念）

### 3.1 直觉定义

- **state**：机器人“现在是什么样子”（真实测量值）
- **action**：你/策略“下一步希望它怎么动”（控制指令）

典型因果关系为：

```text
state(t)  --[policy / controller]-->  action(t)  -->  state(t+1)
```

### 3.2 state 的含义与来源

在关节曲线里，`state` 通常是各关节的真实角度（joint position，常见单位为 rad），来源于：

- 编码器（encoder）
- 关节传感器
- 电机反馈

也就是说：**state 表示“已经做到的”**，而不是“希望到达的”。

### 3.3 action 的含义（常见三种）

结合常见 LeRobot 数据/控制配置，`action` 通常是以下之一（最常见是前两种）：

#### A) 目标关节角度（position control）

```text
action = target_joint_position
```

含义：下一时刻希望关节到达的目标角度。

#### B) 关节角度增量（delta position）

```text
action = Δjoint_angle
```

含义：在当前 state 基础上增加/减少一个小步长。

#### C) 速度 / 力矩（较少）

```text
action = joint_velocity 或 joint_torque
```

### 3.4 为什么 state 和 action 看起来很像

常见现象是：

- action 先变化
- state 滞后跟随，并受物理约束限制

原因链路通常为：

```text
action → 控制器 → 电机 → 真实物理运动 → state
```

### 3.5 训练使用方式（imitation learning 常见范式）

典型监督学习目标是学习：

```text
(state(t), image(t)) → action(t)
```

常见错误（会导致训练不稳定或学到“未来信息”）：

- 用 state 预测 state（而不是预测 action）
- 把 action 当 observation 使用（导致标签泄漏/因果混乱）
- 把 \(t+1\) 的 state 错对齐成 action

### 3.6 为什么可视化会同时画 state 与 action

将 `state` 与 `action` 放在同一图里主要用于工程诊断：

- 检查控制延迟（action 变化后 state 是否合理跟随）
- 判断 actuator 是否饱和/撞限位（action 到边界但 state 不动）
- 发现 bad demo（action 乱跳但 state 几乎不动）

---

## 4. 为什么选 MCAP（与其他格式对比）

### 4.1 相比 CSV / NPZ / JSON

- 不适合高频时序数据的高效存取与对齐
- 多相机图像与关节数据的时间戳同步成本高

### 4.2 相比 rosbag / rosbag2

- 管线更偏 ROS 生态，ML 数据处理成本更高
- 数据集封装与跨平台共享不够“轻量化”

### 4.3 MCAP 的优势（面向数据集/训练管线）

- 顺序读取性能好
- 原生多 topic
- 时间戳一致性强，适合多模态对齐

---

## 5. Demo 数据质量检查清单

目标：筛掉“看起来有，但实际上学不了”的 demo。

### 5.1 第一层：肉眼快速筛（10 秒一条）

#### 1) state/action 是否符合因果关系

期望看到：

```text
action(t)  ↑
state(t)   ↑（稍微慢一点）
```

危险信号（建议直接淘汰）：

- action 大跳，state 几乎不动
- state 比 action 先动（对齐/可视化可能有问题）
- 两条曲线完全不相关

#### 2) 是否存在“卡死 / 饱和 / 撞限位”

典型表现：

- action 已到边界
- state 长期贴着某个值

可能原因：

- 撞限位
- 电机力不足
- 控制输出被 clamp

这类数据会让模型学到错误因果。

#### 3) 是否有“抖动 / 抽搐”

典型表现：

- action 高频抖动
- state 小幅来回震荡
- 画面上动作不明显或不一致

常见原因：

- 人手操作不稳
- 控制环不干净
- demo 中存在犹豫/来回试探

处理建议：不一定全部删除，但建议标记、降低采样权重或后处理平滑。

### 5.2 第二层：时间与同步性检查（非常关键）

#### 4) 图像 vs 关节是否同步

用肉眼检查关键事件是否对齐，例如：

- 手靠近目标时，wrist/elbow 等关节是否同步变化
- 接触/插入/抓取发生的时刻，画面与 state 是否在同一时间附近

不同步常见表现：

- state 已经动了，画面还没动
- 画面已经碰到物体，state 还在旧值

可能原因：

- timestamp 对齐错误
- topic 延迟
- 采集 pipeline bug

这类 demo 通常“数量再多也难救”，优先定位对齐问题。

#### 5) action 是否“提前知道未来”

危险信号：

- action 在视觉变化发生前就大幅变化（像“预知”）

常见原因：

- action 错对齐到了 \(t+1\)
- state/image 滞后一帧（或 topic 缓存导致错位）

后果：训练会非常不稳定且难以排查。

### 5.3 第三层：数值稳定性（可半自动）

#### 6) state − action 的误差是否合理

经验判断：

- 正常：`|state - action|` 小，并表现为“有延迟的跟随”
- 异常：长期大误差，或突然爆炸

#### 7) 是否存在 NaN / 突变 / 断层

重点排查：

- 瞬间跳到 0
- 瞬间跳到 ±π
- 单帧断崖式变化

可能原因：

- 编码器 reset
- topic 掉包/缺帧
- episode 切换未清理状态

### 5.4 第四层：语义一致性（高级但很值）

#### 8) Language instruction 与动作是否一致

即使 instruction 暂时是：

```text
anonymous task
```

也要确保：

- 每个 episode 目标单一、可描述
- 不要“半段做 A、半段做 B”

混任务 demo 会显著污染训练信号。

#### 9) episode 结构是否完整

健康 episode 常见结构：

1. 初始静止
2. 接近目标
3. 操作执行
4. 稳定/结束

不健康信号：

- 一上来就疯狂动（缺少起始稳定段）
- 中途突然 reset
- 结尾关节“飞走”

---

## 6. 工程师打分法（快速决策）

建议对每条 demo 按 0/1/2 打分，快速决策保留与否：

| 项目 | 0 分 | 1 分 | 2 分 |
| --- | --- | --- | --- |
| state/action 因果 | 不成立 | 勉强 | 清晰 |
| 同步性 | 不同步 | 可疑 | 同步 |
| 平滑性 | 抽搐/抖动严重 | 一般 | 平滑 |
| 任务一致 | 混任务 | 部分混杂 | 单一明确 |
| 结构完整 | 缺段/断层 | 一般 | 完整 |

经验阈值：

- 总分 **≥ 7**：建议保留
- 总分 **≤ 5**：建议直接丢弃或返工采集/对齐
