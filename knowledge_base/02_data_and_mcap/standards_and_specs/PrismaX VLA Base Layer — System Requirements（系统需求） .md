<!--
This document is intentionally bilingual (中文 / English).
Format: each section provides Chinese first, then English.
-->

# PrismaX VLA Base Layer — System Requirements（系统需求）

## 1. 目的｜Purpose

**中文**：本文档定义 PrismaX VLA Base Layer 在“机器人数据采集 → 质检 → 存储 → 对客户交付”链路中的系统需求，包括机器注册、数据与元数据字段、存储分层、角色与门户能力、以及初期数据采集计划（TOK2 700 小时）。

**English**: This document defines system requirements for the PrismaX VLA Base Layer across the “robot data collection → QA → storage → customer delivery” pipeline, including machine registration, data/metadata fields, storage tiers, roles and portal capabilities, and the initial TOK2 700-hour collection plan.

## 2. 范围｜Scope

**中文**：本范围覆盖数据采集与交付平台能力，不包含具体机器人控制算法实现；同时对“底盘里程计/导航数据质量”不做默认保证，除非明确纳入采集要求并完成验证。

**English**: This scope covers platform capabilities for data collection and delivery, not robot control algorithm implementation. Base odometry/navigation quality is not assumed unless explicitly required and validated.

## 3. 角色与入口｜Actors & Portals

| 角色（中文） | Role (EN) | 主要职责（中文） | Responsibilities (EN) | 入口（中文） | Surface (EN) |
| --- | --- | --- | --- | --- | --- |
| 采集操作员 | Operator | 执行任务、提交数据 | Execute tasks and submit data | 操作员 UI | Operator UI |
| 质检员 | QA operator | 目检/抽检、打分、驳回/通过 | Review, score, approve/reject | QA UI | QA UI |
| 终端客户 | End customer | 搜索/预览样例、管理 API Key、下载数据、提交缺失需求 | Search/preview, manage API keys, download, request new data | 客户 UI + 下载 API | Customer UI + Download API |
| 管理员 | Admin | 管理类别/场景、收集反馈、配置新任务 | Manage categories/scenarios, gather feedback, configure new tasks | 管理后台 | Admin portal |

## 4. 核心实体与字段｜Core Entities & Fields

### 4.1 机器注册（Robot / Machine Registration）

**中文**：机器注册用于唯一标识数据来源，并支持后续权限与追溯。

**English**: Machine registration uniquely identifies data sources and supports access control and traceability.

建议字段（Recommended fields）：
- **Machine ID**：Solana 钱包地址 / Machine ID / UUID（任选其一，但必须全局唯一）  
  **Machine ID**: Solana wallet address / Machine ID / UUID (choose one, must be globally unique)
- **制造商名称**：Machine Manufacture Name  
  **Manufacturer name**: Machine Manufacture Name
- **机器类型 ID**：Machine type ID  
  **Machine type ID**: Machine type ID
- **机器描述**：Machine description  
  **Machine description**: Machine description
- **机器 IP**：Machine IP  
  **Machine IP**: Machine IP
- **机器位置**：Machine location  
  **Machine location**: Machine location
- **日产出量（估计）**：Data produced per day  
  **Estimated daily output**: Data produced per day

### 4.2 Episode / 任务元数据（Dataset Metadata）

**中文**：每条可交付数据应具备最小可检索元数据，以支持 QA、检索与下载。

**English**: Each deliverable item should include minimum searchable metadata to support QA, discovery, and download.

建议字段（Recommended fields）：
- **长度/时长**：Length / Duration
- **任务描述**：Task description
- **时间戳**：Timestamp（至少包含开始/结束时间，建议全链路统一时钟）
- **质检员**：Quality Check Operator（ID）
- **质量分数**：Quality Score（数值 + 评分规则版本）
- **状态**：Raw / In QA / Approved / Rejected

### 4.3 数据工件（Artifacts: MCAP / Video / Calibration）

**中文**：遵循《PrismaX Mcap Data Collection Quality Standards》关键约束：**MCAP 不应包含图像 topic**，相机视频应以独立 **MP4** 交付，并提供相机内参与必要标定信息。

**English**: Follow key constraints in “PrismaX Mcap Data Collection Quality Standards”: **MCAP should not contain image topics**; camera videos should be delivered as separate **MP4** files, with camera intrinsics and required calibration info.

最小工件集合（Minimum artifact set, high level）：
- **MCAP**：关节观测（observed joint states）、控制指令（commanded states / actions）、tf tree / URDF（如适用）
- **MP4**：每路相机视频（末端相机 + 固定相机）
- **CameraInfo / Calibration**：每路相机内参（最低要求），推荐补充外参/眼在手/眼在外误差指标（如适用）

## 5. 存储分层｜Storage Tiers

### 5.1 原始数据存储（Raw Data Storage）

**中文**：采用低成本云存储；**所有产出数据应自动、即时上传**（失败可重试，需可追踪）。

**English**: Use cost-effective cloud storage; **all produced data should auto-upload immediately** (retry on failure, traceable).

### 5.2 可交付数据存储（Ready-to-use / Approved Data Storage）

**中文**：提供高吞吐访问（下载/拉取速度优先）；通过可用的 PrismaX ID / API Key 授权；**所有经 QA 通过的数据应可被客户即时检索与下载**。

**English**: Provide high-throughput access (fast download/pull); grant access via PrismaX ID / API key; **all QA-approved data should be instantly searchable and downloadable**.

## 6. 质检流程与工具｜QA Workflow & Tools

**中文**：提供 QA 可视化界面，基于《PrismaX Mcap Data Collection Quality Standards》执行检查；支持：
- 逐条浏览与关键指标展示（帧率/同步/缺帧/抖动等）
- 评分（Quality Score）与记录评分规则版本
- 驳回（Reject）并填写原因、可选修复建议

**English**: Provide a QA visualization UI aligned with “PrismaX Mcap Data Collection Quality Standards”, supporting:
- Per-episode review with key metrics (FPS, sync, gaps, jitter, etc.)
- Scoring (Quality Score) with scoring rubric versioning
- Reject with reasons and optional remediation suggestions

## 7. 客户体验｜End Customer Experience

**中文**：客户侧应支持：
- 按类别/场景检索，并预览样例数据
- 管理 API Key（创建/禁用/轮换）
- 提交“数据缺口”请求（当前不存在的数据）
- 下载 API：按筛选条件拉取可交付数据

**English**: Customer side should support:
- Search by category/scenario and preview sample data
- API key management (create/disable/rotate)
- Submit requests for unavailable data
- Download API to pull approved data by filters

## 8. 管理后台｜Admin Portal

**中文**：管理员应支持：
- 管理类别/场景（增删改查）
- 汇总客户反馈，创建/配置新类别与场景

**English**: Admins should be able to:
- Manage categories/scenarios (CRUD)
- Aggregate customer feedback and configure new categories/scenarios

## 9. 操作员工作流｜Operator Workflow

**中文**：
- 操作员 ID：email
- 操作员 UI：查看任务类别与场景、领取/执行任务、提交数据

**English**:
- Operator ID: email
- Operator UI: browse categories/scenarios, execute tasks, submit data

## 10. 初期数据采集计划（TOK2 700 小时）｜Initial Collection Plan (TOK2 700 hours)

### 10.1 机器人与数据切分说明｜Robot setup & episode splitting

**中文**：初期在 TOK2 机器人上采集 700 小时。TOK2 为 6 自由度双臂 + 1 自由度平行夹爪；底盘可移动但非自驱。可执行“多工位”任务，但目前**未审查/验证**底盘里程计数据质量。

**English**: We will collect the initial 700 hours of data on TOK2 robots. TOK2 is a 6-DoF bimanual setup with 1-DoF parallel grippers; the base is mobile but not self-propelled. Multi-station tasks are possible, but we have **not examined or validated** base odometry quality.

**中文**：长时序任务将按“语义完整”原则拆分成多个 episode（例如不在轨迹中途拆分）。

**English**: For long-horizon tasks, we will split runs into multiple episodes such that each episode remains semantically meaningful (e.g., do not split mid-trajectory).

### 10.2 三条数据轨道｜Three Tracks

**中文**：700 小时分为三条轨道：**居家（home）/ 实验室（lab）/ 办公室（office）**，以形成连贯训练数据集，而非随机任务集合。

**English**: The 700 hours are organized into three tracks—**home / lab / office**—to produce cohesive training datasets rather than random tasks.

### 10.3 任务列表｜Task List

#### 实验室（In the lab）

- **分拣紧固件（Sorting fasteners）**  
  中文：从混装零件箱中取出紧固件/小零件，按标签分拣到零件盒不同格子。  
  EN: Take fasteners or small industrial parts from a mixed bin and sort them into labeled compartments.

- **高度规测量（Height gauge）**  
  中文：使用数字高度规测量精密销钉高度，按长度分为合格/不合格。  
  EN: Use a digital height gauge to measure precision pin heights and sort pass/no-pass by length.

  中文：使用高度规测量例如 1×3×4 英寸铝块的尺寸。  
  EN: Use a height gauge to measure dimensions of nominal e.g. 1×3×4" aluminum blocks.

  中文：使用高度规测量玻璃/硅晶圆厚度。  
  EN: Use a height gauge to measure thickness of glass/silicon wafers.

  中文：变体目标为“最接近目标尺寸”的物体筛选。  
  EN: In variants, the goal is to find the item closest to a target dimension.

- **18650 电池质检（18650 battery QA）**  
  中文：用万用表测量 18650 电芯电压，并按电压阈值分为合格/不合格。  
  EN: Measure voltages of 18650 cells with a multimeter and sort pass/no-pass by voltage.

- **整理电子工作台（Cleaning up an electronics bench）**  
  中文：面对凌乱实验台（工具、紧固件、电子元件、电缆等），将物品归位、丢弃垃圾并分类整理。  
  EN: Clean up a messy lab bench with tools/fasteners/components/cables by sorting, binning, and discarding trash.

- **SMD 元件分拣（SMD component sorting）**  
  中文：将电子元件料盘/线轴放置到货架上对应标签位置。  
  EN: Place spools of electronic components into labeled positions on a shelf.

#### 居家（In the home）

- **叠衣服（Folding laundry）**  
  中文：变体 1：仅纯色 T 恤（不同尺码）。  
  EN: Variant 1: solid-colored t-shirts of varying sizes only.  
  中文：变体 2：加入外套/毛衣等厚重衣物。  
  EN: Variant 2: incorporate heavier clothing such as jackets and sweaters.  
  中文：变体 3：加入裤子与连衣裙。  
  EN: Variant 3: incorporate pants and dresses.  
  中文：变体 4：加入毛巾与洗护用品类织物。  
  EN: Variant 4: towels and other toiletries.

- **整理餐具（Organizing dishes）**  
  中文：将洗好的餐具从水槽取出，整齐摆放到沥水架晾干。  
  EN: Take washed dishes from a sink and place them neatly in a dish rack to dry.

- **餐具分类收纳（Tableware organization and storage）**  
  中文：将刀、勺、叉、筷等分拣到收纳盒不同格子。  
  EN: Sort tableware (knives, spoons, forks, chopsticks, etc.) into organizer compartments.

- **分装液体（Decanting liquids）**  
  中文：将瓶中液体倒入量杯至指定刻度；目标量以文本提示给出（不在画面中展示）。  
  EN: Pour liquid from a bottle into a measuring cup up to a predetermined amount given as a text prompt (not visually present).

- **积木操作（Block manipulation）**  
  中文：按结构示意图搭建木质玩具积木结构；变体：使用 LEGO 搭建。  
  EN: Build structures from toy wooden blocks according to a diagram; variant: build from LEGO instead.

#### 办公室（In the office）

- **扫码（Barcode scanning）**  
  中文：从箱/篮中取物，并用台式扫码枪扫描条码。  
  EN: Take items from a bin/basket and scan barcodes with a countertop scanner.

- **整理办公桌（Organizing an office desk）**  
  中文：整理凌乱桌面（纸张、便签、笔与文具），丢弃垃圾并将物品放回合适位置。  
  EN: Clean up a messy desk with paper/notes/pens/stationery by discarding trash and organizing items.

- **归还图书（Book return）**  
  中文：将书籍从箱中取出并按规则上架（按题材/字母序/标签类别等）；部分变体由机器人自行选择“最合理”排序，并可在后续加提示标签。  
  EN: Take books from a bin and shelve them by a varying scheme (genre/alphabetical/labeled categories). In some variants, shelves are unlabeled and the robot devises a logical ordering (can be labeled later with a prompt).

- **组装工位（Assembling a workstation）**  
  中文：将显示器（已接通）、HDMI 线、笔记本、电源排插及配件（充电器、Hub、线缆、鼠标）组装为可用工作台。  
  EN: Assemble a functional workstation from a desk setup including a monitor (already plugged in), HDMI cable, laptop, power strip, and accessories (charger, hubs, cables, mouse).
