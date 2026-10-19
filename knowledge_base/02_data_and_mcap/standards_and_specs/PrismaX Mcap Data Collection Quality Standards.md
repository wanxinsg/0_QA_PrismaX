  **PrismaX Robotics Collection Quality Standards**   

*Prepared for External Vendor Review*

| ID | Quality Category | Quality Item | Item Definition | Minimum | Recommended |
| ----- | ----- | ----- | ----- | ----- | ----- |
| **STD-001** | Topics | Camera Sensors | The camera sensors used to record the demonstration. Note: MCAP should not contain image topics; camera videos should be encoded as a separate MP4 files  | 1 camera per end effector 1 fixed camera that captures all end effector trajectories One cameraInfo topic per camera containing camera intrinsics | 1 camera per end effector 2 fixed cameras that each capture all end effector trajectories One cameraInfo topic per camera containing camera intrinsics |
| **STD-002** | Topics | Observed Joint States | The minimum number of observed manipulator joint states included in the episode recording. | 1 joint state topic per manipulator (including end effector) | 1 joint state topic per manipulator (including end effector) |
| **STD-003** | Topics | Commanded Joint States  | The minimum number of commanded manipulator joint states in the episode recording. | Leader/Follower Tele-operation: 1 commanded joint state topic per manipulator (including end effector) VR Tele-operation: 1 commanded pose/position topic per end effector  | Leader/Follower Tele-operation: 1 commanded joint state topic per manipulator (including end effector) VR Tele-operation: 1 commanded joint state topic per manipulator  |
| **STD-004** | Topics | Robot Description (URDF) | All data required to ensure reproducibility of operator trajectories and accurate spatial correspondence of executed motions. | MCAP includes a robot description parameter containing a URDF that matches the transform tree.  Transform tree structure is validated with a 3D viewer (e.g. rviz, Foxglove) | MCAP includes a robot description parameter containing a URDF that matches the transform tree.  Transform tree structure is validated with a 3D viewer (e.g. rviz, Foxglove) |
| **STD-005** | Topics | Navigation | All data required to enable reconstruction of mobile robot motion and environment traversal. | Only required for mobile robotsAverage odometry and pose frequency is \> 14.5 Hz Average IMU frequency is \> 90 HzOdometry drift is \< 2% of distance traveledAll camera frames have a corresponding position and pose All navigation topics shall reference frames included in the recorded tf tree, ensuring consistent spatial relationship. | Only required for mobile robotsAverage odometry and pose frequency is \> 29.5 Hz Average IMU frequency is \> 290 HzOdometry drift is \< 1% of distance traveledAll camera frames have a corresponding position and pose All navigation topics shall reference frames included in the recorded tf tree, ensuring consistent spatial relationship. |
| **STD-006** | Technical Specs | Camera (RGB) \- Minimum Average Frame Rate | The minimum camera frequency needed to capture the robot trajectory. | Average camera framerate is \>14.5 FPS on all cameras | Average camera framerate is \>29.5 FPS on all cameras  |
| **STD-007** | Technical Specs | Camera (RGB) \- Maximum Gap Between Frames | The maximum time between consecutive camera frames to ensure data continuity. | All camera frames are within 69ms of the previous/next frame from the same camera  | All camera frames are within 34ms of the previous/next frame from the same camera |
| **STD-008** | Technical Specs | Camera (RGB) \- Minimum Resolution | The minimum camera resolution needed to preserve spatial detail. | 640x480 | 1280x720 or higher |
| **STD-009** | Technical Specs | Camera to Camera Time Synchronization | The difference between camera image timestamps across different cameras. | All camera topics have timestamps Temporal misalignment across cameras is \<34ms | All cameras are hardware synchronized No temporal misalignment across cameras |
| **STD-010** | Technical Specs | Robot Joint States to Camera Time Synchronization | The temporal offset error between camera image timestamps and joint state timestamps. | Temporal misalignment between cameras and joint states is \<34ms | No temporal misalignment between cameras and joint states |
| **STD-011** | Technical Specs | Robot Joint States Frequency | The minimum joint state frequency needed to accurately represent robot movements. | Average joint state frequency is \>45 hz on all joints (including end effectors) All camera frames have at least one corresponding joint state  | Average joint state frequency is \>290 hz on all joints (including end effectors) All camera frames have at least one corresponding joint state  |
| **STD-012** | Technical Specs | Camera (Depth) \- Minimum Average Frame Rate | The minimum camera frequency needed to capture the robot trajectory. | Not required. If included: Average camera framerate is \>14.5 FPS on all cameras | Not required. If included: Average camera framerate is \>29.5 FPS on all cameras  |
| **STD-013** | Technical Specs | Camera (Depth) \- Maximum Gap Between Frames | The maximum time between consecutive camera frames to ensure data continuity. | Not required. If included: All camera frames are within 69ms of the previous/next frame from the same camera  | Not required. If included: All camera frames are within 34ms of the previous/next frame from the same camera |
| **STD-014** | Technical Specs | Camera (Depth) \- Minimum Resolution | The minimum camera resolution needed to preserve spatial detail. | Not required. If included: 640x480 | Not required. If included: 1280x720 or higher |
| **STD-015** | Technical Specs | Calibration: reprojection error | The quality of camera instrinsic/extrinsic calibrations | Not required | RMSE \<0.5 |
| **STD-016** | Technical Specs | Calibration: eye-in-hand | The error of the extrinsic transform between the end effector and its camera  | Not required | \<5mm |
| **STD-017** | Technical Specs | Calibration: eye-to-hand | The error of the extrinsic transform between the end effector and static cameras  | Not required | \<1cm |
| **STD-018** | Technical Specs | Physical Vibration and Jitter | The shakiness of the robot arms and cameras | Recording is free from vibrations; arm trajectory is smooth and free of jitters | Recording is free from vibrations; arm trajectory is smooth and free of jitters |
| **STD-019** | Technical Specs | Light Flickering in Videos | The presence of flickering lights in the camera images driven by misalignments between camera framerate and lighting frequency | Videos are free from flickering lights | Videos are free from flickering lights |
| **STD-020** | Demonstration | Operator Skill | The ability of an operator to control the robot to collect data | Operator is sufficiently skilled to produce data that meets the minimum requirements below. | Operator should pass a manipulation skills assessment consisting of common manipulations performed in demonstrations.  Suggested manipulations in appendix. |
| **STD-021** | Demonstration | Trajectory Smoothness | How smoothly the robot arms moves as it accomplishes tasks | Trajectories are continuous, fluid, and free of unnecessary pauses while avoiding configurations that induce kinematic singularities. | Trajectories are continuous, fluid, and free of unnecessary pauses while avoiding configurations that induce kinematic singularities. |
| **STD-022** | Demonstration | Demonstration Efficiency | The amount of time it takes to complete a demonstration while maintaining compliance with all other quality standards. (e.g. smoothness, completeness, non-robot actions, etc). | Demonstrations are efficient enough to be practical and beneficial for a robot end user. | Demonstrations are efficient enough to be practical and beneficial for a robot end user. |
| **STD-023** | Demonstration | Demonstration Completeness | The final outcome of a demonstration. | Demonstrations reach the intended final state of the task, as defined by the instructions for that task. Operators quickly recover from any mistakes made during the demonstration. | Demonstrations reach the intended final state of the task, as defined by the instructions for that task. Operators quickly recover from any mistakes made during the demonstration. |
| **STD-024** | Demonstration | Episode Diversity | Differences in demonstrations across episodes that prevent redundancy and improve generalization. Diversity categories:  **\- Environment:** the background setting (ideally use case) of the collected data **\- Scene:** the starting placement of objects within the environment **\- Demonstration:** the specific task being accomplished **\- Objects** **(primary and/or distractor):** the items being manipulated or stationary within the scene **\- Actions:** the manipulation and/or sequences of manipulations taken to achieve the demonstration end state.  | Demonstrations with the same values across all diversity categories repeat no more than 20 times. | Each demonstration is unique within the dataset such that at least one of the diversity categories is varied for each demonstration. |
| **STD-025** | Demonstration | Non-Robot Actions | Behaviors performed by collection operators that would be abnormal for a robot to execute.Examples:\- Using two arms simultaneously for a task typically performed with one (e.g. stacking 2 bowls at once using both arms)\- Using trajectories that would twist the arm obtusely, potentially reaching a singularity. | Demonstrations exclude  trajectories that are abnormal for a robot to perform. | Demonstrations exclude  trajectories that are abnormal for a robot to perform. |
| **STD-026** | Demonstration | Field of View Compliance | Whether manipulations of objects occur within the camera field of view | All task actions occur within the defined field of view of the recording specification. | All task actions occur within the defined field of view of the recording specification. |
| **STD-027** | Demonstration | Prohibited Information in View | Personal, confidential, or proprietary information that should not be captured in a recording. | All demonstrations are free of  prohibited data. | All demonstrations are free of  prohibited data. |
| **STD-028** | Demonstration | Language Compliance | Any text in the data, if present, should be in English |  |  |


---

**PrismaX 机器人数据采集质量标准**  

*供外部供应商评审*

| ID | 质量类别 | 质量项 | 定义 | 最低要求 | 建议 |
| ----- | ----- | ----- | ----- | ----- | ----- |
| **STD-001** | Topics（话题） | 相机传感器 | 用于记录演示的相机传感器。注意：MCAP 不应包含图像（image）话题；相机视频应编码为单独的 MP4 文件。 | 每个末端执行器 1 台相机<br>1 台固定相机，能够覆盖所有末端执行器的轨迹<br>每台相机 1 个 `cameraInfo` 话题，包含相机内参 | 每个末端执行器 1 台相机<br>2 台固定相机，均能够覆盖所有末端执行器的轨迹<br>每台相机 1 个 `cameraInfo` 话题，包含相机内参 |
| **STD-002** | Topics（话题） | 观测到的关节状态 | 在 episode 录制中包含的、对机械臂关节状态的最少观测数量。 | 每个机械臂（含末端执行器）1 个关节状态话题 | 每个机械臂（含末端执行器）1 个关节状态话题 |
| **STD-003** | Topics（话题） | 指令关节状态 | 在 episode 录制中包含的、对机械臂关节状态的最少指令数量。 | 主从（Leader/Follower）遥操作：每个机械臂（含末端执行器）1 个指令关节状态话题<br>VR 遥操作：每个末端执行器 1 个指令位姿/位置话题 | 主从（Leader/Follower）遥操作：每个机械臂（含末端执行器）1 个指令关节状态话题<br>VR 遥操作：每个机械臂 1 个指令关节状态话题 |
| **STD-004** | Topics（话题） | 机器人描述（URDF） | 确保操作员轨迹可复现、且执行运动具有准确空间对应关系所需的全部数据。 | MCAP 包含机器人描述参数，其中 URDF 与 transform（tf）树匹配。<br>使用 3D 查看器（如 rviz、Foxglove）验证 transform（tf）树结构。 | MCAP 包含机器人描述参数，其中 URDF 与 transform（tf）树匹配。<br>使用 3D 查看器（如 rviz、Foxglove）验证 transform（tf）树结构。 |
| **STD-005** | Topics（话题） | 导航 | 使移动机器人运动与环境穿行可重建所需的全部数据。 | 仅移动机器人需要<br><br>里程计与位姿平均频率 \> 14.5 Hz<br>IMU 平均频率 \> 90 Hz<br><br>里程计漂移 \< 行驶距离的 2%<br><br>每帧相机数据都有对应的位置与位姿<br>所有导航话题应引用录制的 tf 树中包含的坐标系，确保一致的空间关系。 | 仅移动机器人需要<br><br>里程计与位姿平均频率 \> 29.5 Hz<br>IMU 平均频率 \> 290 Hz<br><br>里程计漂移 \< 行驶距离的 1%<br><br>每帧相机数据都有对应的位置与位姿<br>所有导航话题应引用录制的 tf 树中包含的坐标系，确保一致的空间关系。 |
| **STD-006** | Technical Specs（技术规格） | 相机（RGB）- 最小平均帧率 | 捕捉机器人轨迹所需的最低相机频率。 | 所有相机平均帧率 \> 14.5 FPS | 所有相机平均帧率 \> 29.5 FPS |
| **STD-007** | Technical Specs（技术规格） | 相机（RGB）- 帧间最大间隔 | 为保证数据连续性，相邻相机帧之间允许的最大时间间隔。 | 同一相机的任意相邻帧间隔均 ≤ 69ms | 同一相机的任意相邻帧间隔均 ≤ 34ms |
| **STD-008** | Technical Specs（技术规格） | 相机（RGB）- 最小分辨率 | 保留空间细节所需的最低相机分辨率。 | 640x480 | 1280x720 或更高 |
| **STD-009** | Technical Specs（技术规格） | 相机间时间同步 | 不同相机之间图像时间戳的差异。 | 所有相机话题均有时间戳<br>相机间时间不对齐 \< 34ms | 所有相机硬件同步<br>相机间无时间不对齐 |
| **STD-010** | Technical Specs（技术规格） | 关节状态与相机时间同步 | 相机图像时间戳与关节状态时间戳之间的时间偏移误差。 | 相机与关节状态时间不对齐 \< 34ms | 相机与关节状态无时间不对齐 |
| **STD-011** | Technical Specs（技术规格） | 机器人关节状态频率 | 准确表示机器人运动所需的最低关节状态频率。 | 所有关节（含末端执行器）平均关节状态频率 \> 45 Hz<br>每帧相机数据至少有一个对应的关节状态 | 所有关节（含末端执行器）平均关节状态频率 \> 290 Hz<br>每帧相机数据至少有一个对应的关节状态 |
| **STD-012** | Technical Specs（技术规格） | 相机（深度）- 最小平均帧率 | 捕捉机器人轨迹所需的最低相机频率。 | 非必需；若包含：所有相机平均帧率 \> 14.5 FPS | 非必需；若包含：所有相机平均帧率 \> 29.5 FPS |
| **STD-013** | Technical Specs（技术规格） | 相机（深度）- 帧间最大间隔 | 为保证数据连续性，相邻相机帧之间允许的最大时间间隔。 | 非必需；若包含：同一相机的任意相邻帧间隔均 ≤ 69ms | 非必需；若包含：同一相机的任意相邻帧间隔均 ≤ 34ms |
| **STD-014** | Technical Specs（技术规格） | 相机（深度）- 最小分辨率 | 保留空间细节所需的最低相机分辨率。 | 非必需；若包含：640x480 | 非必需；若包含：1280x720 或更高 |
| **STD-015** | Technical Specs（技术规格） | 标定：重投影误差 | 相机内参/外参标定质量。 | 非必需 | RMSE \< 0.5 |
| **STD-016** | Technical Specs（技术规格） | 标定：手眼（eye-in-hand） | 末端执行器与其相机之间外参变换的误差。 | 非必需 | \< 5mm |
| **STD-017** | Technical Specs（技术规格） | 标定：眼到手（eye-to-hand） | 末端执行器与固定相机之间外参变换的误差。 | 非必需 | \< 1cm |
| **STD-018** | Technical Specs（技术规格） | 物理振动与抖动 | 机械臂与相机的晃动程度。 | 录制无振动；机械臂轨迹平滑且无抖动 | 录制无振动；机械臂轨迹平滑且无抖动 |
| **STD-019** | Technical Specs（技术规格） | 视频光源闪烁 | 由相机帧率与照明频率不匹配导致的画面闪烁。 | 视频无闪烁 | 视频无闪烁 |
| **STD-020** | Demonstration（演示） | 操作员技能 | 操作员控制机器人进行数据采集的能力。 | 操作员足够熟练，能产出满足以下最低要求的数据。 | 操作员应通过包含常见演示操作的操控技能评估。建议操作见附录。 |
| **STD-021** | Demonstration（演示） | 轨迹平滑性 | 机械臂完成任务时运动的平滑程度。 | 轨迹连续、流畅，避免不必要的停顿，并避免导致运动学奇异的构型。 | 轨迹连续、流畅，避免不必要的停顿，并避免导致运动学奇异的构型。 |
| **STD-022** | Demonstration（演示） | 演示效率 | 在满足其他所有质量标准（如平滑性、完整性、非机器人动作等）的前提下，完成一次演示所需时间。 | 演示足够高效，能对机器人终端用户实际有用并具备价值。 | 演示足够高效，能对机器人终端用户实际有用并具备价值。 |
| **STD-023** | Demonstration（演示） | 演示完整性 | 一次演示的最终结果。 | 演示达到任务预期最终状态（由该任务的说明定义）。<br><br>操作员能快速从演示中的任何错误中恢复。 | 演示达到任务预期最终状态（由该任务的说明定义）。<br><br>操作员能快速从演示中的任何错误中恢复。 |
| **STD-024** | Demonstration（演示） | Episode 多样性 | 不同 episode 演示之间的差异，避免冗余并提升泛化能力。多样性类别：<br>**- 环境（Environment）**：采集数据的背景场景（理想情况下为实际用例）<br>**- 场景（Scene）**：环境中物体的初始摆放<br>**- 演示（Demonstration）**：完成的具体任务<br>**- 物体（Objects，主要/干扰）**：被操控或静置的物体<br>**- 动作（Actions）**：为达到演示最终状态所采取的操控及其序列 | 在所有多样性类别取值完全相同的情况下，重复次数不超过 20 次。 | 数据集中每次演示均保持唯一性，即每次演示至少在一个多样性类别上有变化。 |
| **STD-025** | Demonstration（演示） | 非机器人动作 | 采集操作员执行的、对机器人来说不正常的行为。<br><br>示例：<br>- 对通常单臂完成的任务同时使用双臂（例如用双臂同时叠放两个碗）<br>- 使用会使机械臂出现过度扭转、可能接近奇异位形的轨迹 | 演示应排除对机器人来说不正常的轨迹。 | 演示应排除对机器人来说不正常的轨迹。 |
| **STD-026** | Demonstration（演示） | 视野合规 | 物体操控是否发生在相机视野范围内。 | 所有任务动作都发生在录制规范定义的视野范围内。 | 所有任务动作都发生在录制规范定义的视野范围内。 |
| **STD-027** | Demonstration（演示） | 视野内禁止信息 | 录制中不应包含的个人、机密或专有信息。 | 所有演示均不包含禁止数据。 | 所有演示均不包含禁止数据。 |
| **STD-028** | Demonstration（演示） | 语言合规 | 数据中如包含文字，则应为英文。 |  |  |

---

## 附：URDF 是什么

**URDF（Unified Robot Description Format，统一机器人描述格式）**是 ROS 生态中最常用的机器人模型描述格式，通常是一个 XML 文件（扩展名常见为 `.urdf`，也常用 `.xacro` 生成）。

URDF 主要用于描述机器人的结构与外观，典型包含：

- **Link（连杆）**：每个刚体部件的名称、几何形状（mesh/box/cylinder 等）、可视化与碰撞模型  
- **Joint（关节）**：连接哪些 link、关节类型（转动/移动/固定等）、轴向、限位、零位等  
- **惯性参数（可选）**：质量、惯量矩阵、质心位置（用于动力学/仿真）  
- **坐标系关系**：link/joint 定义的坐标变换关系，构成机器人运动学链（应与录制的 `tf` 树一致）

在本质量标准中要求 MCAP 中包含与 `tf` 树匹配的 URDF，是为了**支持轨迹复现、传感器/执行器空间对齐**，并可在 rviz、Foxglove 等工具中正确可视化与校验变换关系。

---

## 附：transform（tf）树是什么

**transform（tf）树**（ROS 中常说的 **tf / tf2 tree**）是指：系统里所有相关**坐标系（frame）**之间的位姿变换关系（平移 + 旋转）组成的一棵“树状”结构。

核心概念：

- **frame（坐标系）**：例如 `base_link`、`world/map`、`camera_link`、`ee_link` 等，每个 frame 都代表一个参考坐标系。
- **transform（变换）**：描述“子坐标系相对父坐标系”的位姿（平移 + 旋转，常用四元数/欧拉角表示）。
- **树结构（tree）**：通常要求任意两个 frame 之间只有一条路径（无环），这样才能唯一地推导出任意两坐标系之间的相对变换。
- **时间戳（timestamp）**：很多 transform 是随时间变化的（例如关节运动、移动底盘），因此 tf 消息带时间戳；查询某一时刻的空间关系，需要对应时刻（或可插值）的 tf 数据。

它解决的问题是：把相机、IMU、机械臂、末端执行器、世界坐标等全部放到**同一个一致的空间坐标体系**里，便于：

- **对齐多传感器数据**（例如把相机观测投到机器人/世界坐标系）
- **重建轨迹与环境穿行**（移动机器人导航相关）
- **可视化与校验**（rviz、Foxglove 能直接基于 tf 树渲染机器人与传感器位姿）

在本质量标准中要求“导航话题引用 tf 树中的 frame、且 URDF 匹配 tf 树”，本质是在保证：**所有数据引用的坐标系是同一套、且空间关系自洽**，否则会出现坐标对不上、轨迹无法复现、传感器融合失败等问题。

---

## 附：IMU frequency 是什么

**IMU frequency（IMU 频率）**指 **IMU（惯性测量单元）数据的发布/采样频率**，也就是 IMU 话题每秒输出多少条消息，单位通常是 **Hz**（例如 90 Hz 表示每秒约 90 条）。

- **IMU 数据一般包含**：角速度（gyro）、线加速度（accel）（有时还包含姿态/四元数、磁力计等）
- **为什么重要**：频率越高，越能捕捉快速运动与振动细节；用于里程计/姿态估计/传感器融合（如 EKF、VIO）时，通常能降低时延并提升稳定性
- **在本质量标准中的含义**：例如 “Average IMU frequency is \> 90 Hz / \> 290 Hz” 表示录制期间 **IMU 话题的平均输出频率**需高于该阈值（多用于移动机器人导航与位姿重建）