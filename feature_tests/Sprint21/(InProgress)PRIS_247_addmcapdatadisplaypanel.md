# PRIS-247 Add MCAP Data Display Panel - 改动逻辑与 E2E 测试用例

## 一、分析范围

### 前端仓库

仓库：`app-prismax-rp`  
分支：`testing`  
作者：`Aparna Rangamani <aparna@prismax.ai>` / `aparna-prismax <aparna@prismax.ai>`

涉及提交：

| Hash | 日期 | Commit Message |
|---|---|---|
| `a3f4f41` | 2026-07-07 | PRIS-247: implement mcap motion data panel display |
| `e8a4410` | 2026-07-07 | PRIS-247: make ui styling improvements |
| `1f37759` | 2026-07-07 | PRIS-247: improve mobile responsiveness for qa page |
| `079f962` | 2026-07-07 | PRIS-247: improve video layout shift |
| `ab8cd5d` | 2026-07-07 | PRIS-247: minor animation adjustment |
| `5be29f7` | 2026-07-07 | Merge pull request #62 from PrismaXAI/PRIS-247-mcap-graph |
| `94f6c81` | 2026-07-09 | PRIS-247: add features to motion data panel with prefetch data and video seek |
| `9011c5e` | 2026-07-09 | PRIS-247: make further ui improvements for motion panel with increased height and mobile layout |
| `60abc49` | 2026-07-09 | Merge pull request #63 from PrismaXAI/PRIS-247-mcap-graph |

### 关联需求 PRIS-270（App / VLA Layout）

PRIS-270 与 MCAP 数据逻辑无直接关系，但会改变承载 QA Review、VLA 与 Upload 页面的公共布局，因此纳入本次 UI 回归分析。

| Hash | 日期 | 分支/状态 | Commit Message |
|---|---|---|---|
| `6a24eff` | 2026-06-29 | 已进入 `testing` 历史 | PRIS-270: make top bar for app fixed |
| `5132bd9` | 2026-06-30 | 已进入 `testing` 历史 | PRIS-270: fix pagination dot z-index for new fixed app topbar |
| `a01de6a` | 2026-07-10 | `origin/PRIS-270-vla-layout-v2`，待合入 `testing` | PRIS-270: change vla sidebar height on desktop |
| `c2af972` | 2026-07-10 | `origin/PRIS-270-vla-layout-v2`，待合入 `testing` | PRIS-270: update vla layout on mobile |

备注：`a01de6a` 的父提交是 PRIS-247 merge commit `60abc49`，`c2af972` 基于 `a01de6a`。因此 PRIS-270 VLA Layout v2 与本文分析的最新版 Motion Panel 共存，但截至本文更新时尚未进入本地 `testing` HEAD。

### 后端仓库

仓库：`app-prismax-rp-backend`  
分支：`testing`  
作者：`aparna-prismax <aparna@prismax.ai>`

涉及提交：

| Hash | 日期 | Commit Message |
|---|---|---|
| `47656fe` | 2026-07-07 | Merge pull request #50 from PrismaXAI/PRIS-247-mcap-display |
| `5e55a62` | 2026-07-09 | PRIS-247: improve mcap joint states processing speed |
| `cd430f3` | 2026-07-09 | Merge pull request #51 from PrismaXAI/PRIS-247-mcap-display |

备注：`47656fe` 是 merge commit，实际业务逻辑来自被合入的 `93af6e6 PRIS-247: implement mcap graph`。

---

## 二、一句话主线

PRIS-247 将 QA Review 页面从“只看 episode 视频”扩展为“视频 + MCAP JointState 曲线双向联动查看”：后端从 raw MCAP 中抽样解析左右臂关节状态；前端默认展开 Motion Data Panel，缓存当前 episode 并预取后续 4 个 episode 的数据。视频播放时间驱动曲线参考线，点击曲线时间点也会反向同步所有已显示视频，帮助 QA reviewer 快速对齐视频动作和机器人 motion data。

---

## 三、端到端数据流

1. QA reviewer 进入 Data QA Review 页面并打开某个 episode。
2. 前端拿到当前 `episodeId` 与视频 `currentTime`。
3. Motion Data Panel 在每次 episode 切换后默认展开；用户仍可用 `Motion data` 按钮收起或再次展开。
4. 前端立即请求当前 episode，并在后台预取列表中后续最多 4 个 episode：`GET /data/qa/episodes/{episodeId}/joint-states`。
5. 后端校验当前用户是否有 QA 访问权限。
6. 后端从 `data_episodes` 查询 `raw_bucket` 和 `raw_mcap_path`。
7. 后端从 GCS 下载 raw MCAP 文件。
8. 后端使用 `mcap` 和 `mcap-ros2-support` 解析 `sensor_msgs/msg/JointState`。
9. 后端按 topic 名称中的 `left` / `right` 拆分左右臂数据。
10. 后端先按 channel 每 10 条保留 1 条，再只解码保留的消息，并将时间转换为从 0 开始的相对时间。
11. 前端用 Recharts 渲染左右臂 joint 曲线。
12. 视频播放时，`currentTime` 驱动图表中的 vertical reference line；点击曲线则把点击时间写回所有当前显示视频的 `currentTime`。

---

## 四、后端改动逻辑

## 4.1 新增 JointState 查询接口

新增接口：

```http
GET /data/qa/episodes/<episode_id>/joint-states
```

核心返回结构：

```json
{
  "success": true,
  "data": {
    "left": [
      {
        "t": 0.0,
        "joint_name_1": 0.123456,
        "joint_name_2": -0.234567
      }
    ],
    "right": []
  }
}
```

核心逻辑：

- 动态 import `mcap.reader.make_reader` 与 `mcap_ros2.decoder.DecoderFactory`。
- 若依赖未安装，返回 `500` 与 `mcap libraries not installed`。
- 复用 `_require_qa_eligible_user()` 做 QA 用户权限校验。
- 根据 `episode_id` 查询 `data_episodes.raw_bucket` 与 `data_episodes.raw_mcap_path`。
- 如果 episode 不存在，返回 `404 episode not found`。
- 如果没有 `raw_mcap_path`，返回空的左右臂数组。
- 如果 GCS blob 不存在，返回空的左右臂数组。
- 下载 MCAP bytes 后通过 `reader.iter_messages()` 遍历原始消息。
- 仅处理 schema 存在且 `schema.name == "sensor_msgs/msg/JointState"` 的消息。
- 使用 `counts_by_channel` 独立统计每个 channel 的消息序号，每 10 条保留 1 条；未被保留的消息不执行 CDR 解码。
- 使用 `decoders_by_channel` 缓存每个 channel 的 decoder，避免重复创建。
- 对每条 JointState 消息：
  - `t` 使用 `message.log_time / 1e9` 转为秒。
  - `decoded_msg.name` 与 `decoded_msg.position` zip 成 joint name -> position。
  - position 保留 6 位小数。
- 按 topic 名称判断左右臂：
  - topic lower-case 包含 `left` -> left group。
  - topic lower-case 包含 `right` -> right group。
- 每侧可能存在多个 topic，选择抽样后数据量最多的 topic。
- 取左右臂第一条数据中最早时间作为 `t0`，把所有 `t` 转换为相对时间，保留 3 位小数。

## 4.2 新增依赖

`app_prismax_data_pipeline/requirements.txt` 新增：

```txt
mcap
mcap-ros2-support
```

业务意义：

- 后端可以直接解析 ROS2 MCAP 文件中的 JointState。
- 前端不需要下载或解析 MCAP，只消费轻量 JSON。
- 在解码前完成降采样，既降低接口返回体积和前端渲染压力，也显著减少后端 Python CDR 解码次数。

---

## 五、前端改动逻辑

## 5.1 新增 Motion Data Panel

提交：`a3f4f41`

涉及文件：

- `src/components/Data/DataQAReview/DataQAReview.js`
- `src/components/Data/DataQAReview/DataQAReview.module.css`
- `src/components/Data/DataQAReview/MotionDataPanel.js`
- `src/components/Data/DataQAReview/MotionDataPanel.module.css`

核心改动：

- 在 QA Review 页面引入 `MotionDataPanel`。
- 初版新增状态：

```js
const [motionOpen, setMotionOpen] = useState(false);
```

7 月 9 日版本已改为：

```js
const [motionOpen, setMotionOpen] = useState(true);
const [jointStatesCache, setJointStatesCache] = useState({});
const jointStatesRequestedRef = useRef(new Set());
```

- 在视频控制栏右侧新增 `Motion data` toggle 按钮。
- 展开后传入：
  - `episodeId={currentEpisodeId}`
  - `currentTime={currentTime}`
  - `isOpen={motionOpen}`

当前请求逻辑已从 `MotionDataPanel` 提升到 `DataQAReview` 父组件：

- 使用页面已有 token 请求接口。
- 请求不依赖 panel 是否展开；进入 episode 后即加载当前数据。
- `jointStatesRequestedRef` 防止同一 episode 正在加载或已成功加载时重复请求。
- `jointStatesCache` 按 episode ID 分别保存 `loading`、`ready`、`error` 和数据，切换时不会把上一 episode 的曲线当成当前结果。
- 请求失败或业务返回 `success=false` 时，从 requested set 删除该 episode，使后续 effect 有机会重试。
- 父组件向纯展示组件 `MotionDataPanel` 传入 `data`、`loading`、`error` 和 `onSeek`。
- 请求：

```js
GET `${PRISMAX_DATA_PIPELINE_URL}/data/qa/episodes/${episodeId}/joint-states`
Authorization: Bearer ${token}
```

- 成功后将 `json.data` 写入对应 episode 的缓存。
- loading/error/empty data 由 panel 根据父组件 props 展示。
- 使用 Recharts 展示左右臂：
  - `LineChart`
  - `XAxis`
  - `YAxis`
  - `Tooltip`
  - `Legend`
  - `ReferenceLine`
  - `ResponsiveContainer`
- 每个 joint 作为一条曲线。
- `currentTime` 作为 `ReferenceLine.x`，在图表中显示当前视频时间位置。
- 点击图表时读取 Recharts `activeLabel`，调用 `onSeek(Number(activeLabel))`；父组件把所有已渲染视频跳转到同一时间，并更新 `currentTime`。

## 5.2 UI 顺序与 Tooltip 优化

提交：`e8a4410`

核心改动：

- 将 `MotionDataPanel` 放入视频 viewer 容器内部，使其视觉上归属于视频查看区域。
- 调整控制栏右侧顺序：
  - duration
  - mute
  - fullscreen
  - Motion data
- 将图表时间展示改为 `mm:ss` 格式，和视频时间格式一致。
- 自定义 Recharts tooltip，并通过 `ReactDOM.createPortal` 渲染：
  - 普通场景渲染到 `document.body`。
  - fullscreen 场景渲染到 `document.fullscreenElement`。
- 解决 tooltip 被 panel overflow 或 fullscreen 容器裁剪的问题。

## 5.3 移动端响应式优化

提交：`1f37759`

核心改动：

- 小屏下 QA Review route 左右 padding 清零，让页面可用宽度最大化。
- `DataQAReview` 根容器增加 `overflow-x: hidden`，避免横向溢出。
- 顶部 episode 信息在移动端拆为：
  - `epInfoMobile`
  - `epNavGroup`
- 视频控制栏在窄屏下支持换行：
  - left controls 第一行
  - seek bar 独占一行
  - right controls 可换行
- viewer、camera pane、panel 等 flex 子元素增加 `min-width: 0`，避免撑破屏幕。
- Motion Data Panel 在小屏下从左右并排改为上下堆叠。
- Motion Data Panel 小屏下允许内部纵向滚动。
- 极窄屏隐藏部分 breadcrumb 并压缩 scenario 文案区域。

## 5.4 视频 Layout Shift 修复

提交：`079f962`

核心改动：

```css
.video {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    object-fit: contain;
}
```

业务目的：

- 视频元素固定填充既有容器。
- 降低视频加载、切换 episode、尺寸变化时造成的页面跳动。

## 5.5 展开动画微调

提交：`ab8cd5d`

核心改动：

```css
transition: max-height 0.25s ease;
```

调整为：

```css
transition: max-height 0.3s ease;
```

业务目的：

- Motion Data Panel 展开/收起动画更平滑。

## 5.6 Merge Commit

提交：`5be29f7`

这是前端 PR merge commit：

```txt
Merge pull request #62 from PrismaXAI/PRIS-247-mcap-graph
```

它将 `a3f4f41` 到 `ab8cd5d` 的前端功能分支合入 `testing`，本身没有额外独立业务逻辑。

## 5.7 数据预取、曲线点击 Seek 与新版响应式布局

提交：`94f6c81`、`9011c5e`、`60abc49`

核心逻辑：

- 每次切换 episode，Motion Data Panel 自动恢复为展开状态。
- 当前 episode 无论 panel 是否可见都会确保已加载或正在加载。
- 使用 `episodes.slice(currentEpisodeIndex + 1, currentEpisodeIndex + 5)` 后台预取后续最多 4 个 episode。
- 同一 episode 的展开、收起、前后切换优先复用内存缓存，不重复发起成功过的请求。
- 点击左右臂任一图表的有效数据点，会同步当前画面中全部视频，而不是只调整单个 camera。
- 桌面端图表高度调整为 `195px`，移动端为 `110px`；panel 的最大高度和移动端样式同步增加。
- `60abc49` 是 PR #63 的 merge commit，本身没有额外独立业务逻辑。

后端配套提交：`5e55a62`、`cd430f3`

- 抽样位置从“全部解码后切片”前移至“原始消息遍历阶段”。
- 在 1/10 抽样比例不变的情况下，避免解码约 90% 不会返回给前端的 JointState 消息。
- `cd430f3` 是 PR #51 的 merge commit，本身没有额外独立业务逻辑。

## 5.8 关联 PRIS-270：固定 App Topbar 与 VLA Layout v2

### 5.8.1 固定 App Topbar（已进入 testing）

提交：`6a24eff`、`5132bd9`

- App header 改为 `position: fixed`，固定高度 `79px`，位于页面顶部且 `z-index: 19`。
- 主内容增加顶部间距；移动端内容区域使用 `83px` top margin，避免被固定 header 遮挡。
- Dashboard pagination dots 的 `z-index` 从 `999` 降为 `18`，确保不会覆盖 `z-index: 19` 的固定 topbar。
- 对 QA Review 的影响：页面滚动、全屏切换和 Motion tooltip portal 需要验证不会与固定 header 发生遮挡或层级冲突。

### 5.8.2 Desktop VLA Sidebar 高度（待合入 testing）

提交：`a01de6a`

- `DataHub` sidebar 保持 sticky，顶部偏移 `79px`。
- 原 `max-height: calc(100vh - 40px)` 改为固定可视高度 `height: calc(100vh - 101px)`，内部纵向滚动。
- Data Labeling 与 Device Partners 两个 sidebar block 之间新增 divider。
- 对 Motion Panel 没有直接数据影响，但 DataHub 页面高度、滚动容器和 fixed topbar 的组合需要一起回归。

### 5.8.3 Mobile VLA / Upload Layout（待合入 testing）

提交：`c2af972`

- 在 `max-width: 980px` 下，左侧 sidebar 改为顶部横向 sticky navigation：`top: 83px`、`z-index: 11`，支持横向滚动并隐藏 scrollbar。
- sidebar section label 隐藏，Data Labeling 与 Device Partners 通过圆点 divider 分隔。
- desktop sidebar 内的 scenario list 在移动端隐藏。
- Upload workspace 新增独立的 `mobileScenarioBar`，用可横向滚动的 scenario chips 展示任务；当前选中项有 active 状态。
- mobile upload subnav 下移至 `top: 133px`，避免与 fixed topbar 和横向 sidebar 重叠。
- `.layout`、`.main` 等容器增加 `min-width: 0`，降低窄屏横向溢出风险。
- `UploadWorkspace` 新增 `scenarioOptions`、`selectedScenario`、`onScenarioSelect` props，点击 chip 复用现有 `handleScenarioSelect`。

PRIS-270 与 PRIS-247 的共同回归重点：

- 79/83px fixed topbar offset 与 QA Review、VLA sticky navigation 的位置一致性。
- 小于等于 980px 时页面不能产生非预期横向滚动；允许导航和 scenario bar 自身横向滚动。
- sticky/fixed 元素、Motion tooltip、Dashboard pagination dots 的 z-index 层级不能互相覆盖。
- 从 VLA/Upload 页面导航到 QA Review 后，Motion Panel 默认展开、预取和曲线 Seek 行为不应受布局状态影响。

---

## 六、影响范围与风险点

| 模块 | 风险等级 | 风险说明 |
|---|---|---|
| QA Review 页面 | 高 | 视频查看页面核心流程新增面板、控制栏按钮、响应式布局，可能影响 reviewer 日常审核效率 |
| 后端 MCAP 解析接口 | 高 | 依赖 GCS、DB、MCAP 文件结构、ROS2 decoder，异常路径较多 |
| 视频时间与曲线对齐 | 中 | 后端用 MCAP log_time 归零，前端用 video currentTime，对齐准确性依赖两者时间基准一致 |
| 移动端布局 | 中 | 控制栏换行、panel 堆叠、tooltip portal 都可能出现小屏视觉问题 |
| Fullscreen tooltip | 中 | tooltip 渲染目标会根据 fullscreen 状态变化，需要验证不会丢失或错位 |
| 性能与请求放大 | 高 | 页面会自动请求当前 episode 并预取后续 4 个；大 MCAP 仍需从 GCS 下载，快速切换或长列表可能形成并发请求与内存缓存压力 |
| 曲线点击 Seek | 中 | Recharts `activeLabel` 必须是有效数值，且需要同步当前显示的全部 camera 视频 |
| 空数据与异常处理 | 中 | raw_mcap_path 缺失、blob 不存在、无 JointState topic、依赖缺失都应有可解释表现 |
| PRIS-270 固定/Sticky 布局 | 高 | fixed topbar、DataHub sticky sidebar、mobile subnav 和 Motion tooltip 使用不同 z-index 与 top offset，存在遮挡、双滚动和层级冲突风险 |
| PRIS-270 分支状态 | 中 | VLA Layout v2 尚未合入 `testing`；测试环境若未部署 `origin/PRIS-270-vla-layout-v2`，只能验证旧 topbar，不能把新版 VLA 用例判为产品失败 |

---

## 七、E2E 测试前置条件

### 账号与权限

- QA eligible 用户账号，能够进入 Data QA Review 页面。
- 非 QA eligible 用户账号，用于权限负向验证。
- 至少一个可审核 upload，且包含多个 episodes。
- 建议 upload 至少包含 6 个 episodes，用于验证“当前 + 后续 4 个”的预取边界及缓存复用。

### 测试数据

建议准备以下 episode：

| 数据类型 | 说明 |
|---|---|
| 正常 MCAP | raw MCAP 存在，包含 left/right JointState topic |
| 单侧 MCAP | 只包含 left 或只包含 right JointState topic |
| 无 JointState MCAP | raw MCAP 存在，但不包含 `sensor_msgs/msg/JointState` |
| 缺失 raw_mcap_path | episode DB 中 `raw_mcap_path` 为空 |
| GCS blob 不存在 | DB 有 path，但 GCS 上对象不存在 |
| 大体积 MCAP | 用于验证接口耗时和图表渲染性能 |

### 环境与依赖

- 后端环境已安装：
  - `mcap`
  - `mcap-ros2-support`
- 后端可访问 GCS raw bucket。
- 前端 `PRISMAX_DATA_PIPELINE_URL` 指向正确后端环境。
- 浏览器建议覆盖：
  - Chrome desktop
  - Firefox desktop
  - Chrome mobile viewport 或真实移动设备

---

## 八、E2E 测试用例

| Case ID | 标题 | 前置条件 | 步骤 | 预期结果 |
|---|---|---|---|---|
| PRIS-247-E2E-001 | 进入 episode 后 Motion Data Panel 默认展开并展示左右臂曲线 | QA 用户登录；episode 有 raw MCAP；MCAP 包含 left/right JointState | 1. 进入 Data QA Review 页面。<br>2. 打开目标 episode，不点击 `Motion data`。<br>3. 等待数据加载完成。 | 1. Motion Data 按钮为 active，Panel 默认展开。<br>2. 显示 `Left Arm` 和 `Right Arm` 两个图表。<br>3. 每个图表中按 joint name 显示多条曲线。<br>4. Network 中当前 episode 的 `/joint-states` 返回 `200` 且 `success=true`。<br>5. 无前端报错。 |
| PRIS-247-E2E-002 | 视频播放时 Motion Data 图表 reference line 跟随 currentTime | 同 PRIS-247-E2E-001 | 1. 展开 Motion Data Panel。<br>2. 点击播放视频。<br>3. 观察图表中的竖向 reference line。<br>4. 拖动视频 seek bar 到中间位置。<br>5. 再拖动到接近结束位置。 | 1. 播放过程中 reference line 随视频时间向右移动。<br>2. 拖动 seek bar 后，reference line 跳转到对应时间位置。<br>3. 左右臂图表的 reference line 与当前视频时间一致。<br>4. 页面没有明显卡顿或布局跳动。 |
| PRIS-247-E2E-003 | 同一 episode 收起/展开复用缓存 | QA 用户登录；打开 DevTools Network | 1. 进入目标 episode并等待自动请求成功。<br>2. 点击 `Motion data` 收起。<br>3. 再次点击展开。<br>4. 重复操作两次。 | 1. 当前 episode 只请求一次 `/joint-states`。<br>2. 收起不清除缓存。<br>3. 再次展开立即显示已加载曲线。 |
| PRIS-247-E2E-004 | 切换 episode 后默认展开且使用对应缓存数据 | QA upload 至少有 2 个 episodes，两个 episode 的曲线可区分 | 1. 在 episode A 等待图表显示。<br>2. 手动收起 panel。<br>3. 切换到 episode B。<br>4. 再切回 episode A。 | 1. 切到 B 后 panel 自动恢复展开。<br>2. B 不短暂展示 A 的旧曲线。<br>3. B 展示自己的数据，时间从新视频进度对齐。<br>4. 返回 A 时复用已成功缓存，不重复请求 A。 |
| PRIS-247-E2E-005 | MCAP 只包含单侧 JointState 时页面可正常展示 | episode 的 MCAP 只包含 left 或 right topic | 1. 打开目标 episode。<br>2. 展开 Motion Data Panel。 | 1. 有数据的一侧正常显示曲线。<br>2. 无数据的一侧不导致页面崩溃。<br>3. Panel 不出现无限 loading。<br>4. Console 无 JavaScript error。 |
| PRIS-247-E2E-006 | MCAP 不包含 JointState topic 时页面稳定 | raw MCAP 存在，但无 `sensor_msgs/msg/JointState` | 1. 打开目标 episode。<br>2. 点击 `Motion data`。 | 1. 后端返回 `success=true`，`left=[]`，`right=[]`。<br>2. 前端不崩溃。<br>3. 不出现无限 loading。<br>4. 建议产品表现：显示空状态或保持空图表。 |
| PRIS-247-E2E-007 | episode 没有 raw_mcap_path 时 Motion Data 不报错 | episode DB 中 `raw_mcap_path` 为空 | 1. 打开目标 episode。<br>2. 点击 `Motion data`。 | 1. 接口返回 `200`。<br>2. 返回 `left=[]`，`right=[]`。<br>3. 前端不崩溃，不无限 loading。 |
| PRIS-247-E2E-008 | DB 有 raw_mcap_path 但 GCS 对象不存在时稳定返回空数据 | episode DB 有 path，但 bucket 中无对应 blob | 1. 打开目标 episode。<br>2. 点击 `Motion data`。 | 1. 接口返回 `200`。<br>2. 返回 `left=[]`，`right=[]`。<br>3. 前端不显示 error toast 或崩溃。 |
| PRIS-247-E2E-009 | 请求不存在的 episode joint-states 返回 404 | 准备一个不存在的 episode id | 1. 使用 QA 用户 token 直接请求 `/data/qa/episodes/{invalid_id}/joint-states`。 | 1. 接口返回 `404`。<br>2. 响应包含 `success=false` 与 `episode not found`。 |
| PRIS-247-E2E-010 | 非 QA eligible 用户无法访问 joint-states 接口 | 非 QA eligible 用户登录 | 1. 直接请求 `/data/qa/episodes/{episodeId}/joint-states`。<br>2. 或尝试从 UI 进入 QA Review 页面并展开 Motion Data。 | 1. 后端返回权限错误。<br>2. 非 QA 用户无法获取 motion data。<br>3. UI 不泄露数据。 |
| PRIS-247-E2E-011 | gatewayToken 失效时 Motion Data 请求失败可控 | 浏览器中 token 过期或手动替换为无效 token | 1. 打开 QA Review 页面。<br>2. 点击 `Motion data`。 | 1. `/joint-states` 返回 401/403 或业务权限错误。<br>2. 前端显示 `Motion data unavailable.` 或其他可控错误状态。<br>3. 不出现无限 loading。 |
| PRIS-247-E2E-012 | 全屏模式下 Motion Data tooltip 不被裁剪 | Chrome 浏览器；episode 有 motion data | 1. 打开 episode。<br>2. 点击全屏按钮。<br>3. 展开 Motion Data Panel。<br>4. 鼠标 hover 到图表曲线上。 | 1. tooltip 在全屏模式中可见。<br>2. tooltip 位置跟随鼠标附近。<br>3. tooltip 内容包含时间与 joint value。<br>4. tooltip 不被 panel 或 fullscreen 容器裁剪。 |
| PRIS-247-E2E-013 | 移动端 QA Review 页面展开 Motion Data 后布局不溢出 | Chrome DevTools 设置 viewport 为 390x844 或真实移动设备 | 1. 打开 QA Review 页面。<br>2. 展开 Motion Data Panel。<br>3. 播放视频。<br>4. 滚动 panel 内部。<br>5. 操作 Prev/Next episode。 | 1. 页面没有横向滚动条。<br>2. 控制栏按钮不重叠。<br>3. seek bar 独占行且可操作。<br>4. 左右臂图表上下堆叠。<br>5. Panel 内部可纵向滚动。<br>6. 顶部 episode 信息和导航按钮不互相覆盖。 |
| PRIS-247-E2E-014 | 359px 以下极窄屏 QA Review 页面可用 | Chrome DevTools 设置 viewport 宽度 320px | 1. 打开 QA Review 页面。<br>2. 展开 Motion Data Panel。<br>3. 操作视频播放、静音、全屏、Motion Data 按钮。 | 1. breadcrumb 按预期收缩或隐藏。<br>2. scenario trigger 不撑破页面。<br>3. 控制按钮可点击，不遮挡。<br>4. 无横向溢出。 |
| PRIS-247-E2E-015 | 切换 episode 或视频加载时 viewer 区域无明显跳动 | QA upload 有多个 episodes | 1. 打开 QA Review 页面。<br>2. 连续切换 Next/Prev episode。<br>3. 观察 video viewer、control bar、score panel 位置。<br>4. 展开 Motion Data 后再次切换。 | 1. 视频元素填充 viewer，不挤压其他 UI。<br>2. 控制栏和评分区域位置稳定。<br>3. 页面无明显上下跳动。 |
| PRIS-247-E2E-016 | 大体积 MCAP 的接口耗时和前端渲染可接受 | episode 对应大体积 raw MCAP | 1. 打开目标 episode。<br>2. 点击 `Motion data`。<br>3. 记录接口响应时间。<br>4. 观察图表渲染与页面交互。 | 1. 接口在可接受时间内返回。建议关注阈值：P95 不超过 5s，具体以产品性能目标为准。<br>2. 前端图表加载后页面仍可操作。<br>3. 视频播放不明显卡顿。<br>4. 后端无超时或内存异常。 |
| PRIS-247-E2E-017 | 后端缺少 MCAP 依赖时返回明确错误 | 测试环境临时移除或禁用 `mcap` / `mcap-ros2-support` 依赖 | 1. 请求 `/data/qa/episodes/{episodeId}/joint-states`。 | 1. 接口返回 `500`。<br>2. 响应包含 `mcap libraries not installed`。<br>3. 前端显示可控错误状态，不崩溃。 |
| PRIS-247-E2E-018 | Firefox 下 Motion Data Panel 基本功能可用 | Firefox 浏览器；episode 有 motion data | 1. 打开 QA Review 页面。<br>2. 展开 Motion Data Panel。<br>3. 播放视频。<br>4. hover 图表 tooltip。<br>5. 切换 episode。 | 1. 图表正常展示。<br>2. reference line 随播放时间更新。<br>3. tooltip 正常显示。<br>4. 页面无浏览器兼容性报错。 |
| PRIS-247-E2E-019 | 自动预取当前 episode 后续最多 4 个 episode | upload 至少 6 个 episodes；清空 Network 记录和浏览器缓存 | 1. 进入第 1 个 episode。<br>2. 不操作 Next，观察 `/joint-states` 请求。<br>3. 等待所有请求完成。 | 1. 请求 episode 1 当前数据。<br>2. 后台请求 episode 2、3、4、5。<br>3. 初始阶段不请求 episode 6。<br>4. 每个 episode 在同一加载周期内最多请求一次。 |
| PRIS-247-E2E-020 | 切换到已预取 episode 时直接复用缓存 | 已完成 E2E-019，episode 2 请求成功 | 1. 切换到 episode 2。<br>2. 观察 Network、loading 状态和曲线。 | 1. 不重复请求 episode 2。<br>2. 曲线可直接从缓存显示，不出现明显重新 loading。<br>3. 切换后会继续预取新进入窗口的 episode 6。 |
| PRIS-247-E2E-021 | 点击 Motion 曲线同步跳转所有当前视频 | 当前 episode 显示 3 路视频且左右臂图表有数据 | 1. 播放到非目标时间后暂停。<br>2. 点击左臂曲线约 10 秒数据点。<br>3. 检查 3 个 video 元素、seek bar 和 reference line。<br>4. 再点击右臂曲线另一时间点。 | 1. 所有已显示视频 `currentTime` 同步为点击点的 `activeLabel`。<br>2. seek bar 和左右图表 reference line 同步更新。<br>3. 左右臂任一图表均可触发。<br>4. 无 NaN、跳到负数或单路视频不同步。 |
| PRIS-247-E2E-022 | JointState 请求失败后允许重试并恢复 | 可将某 episode 第一次 `/joint-states` mock 为失败，下一次恢复 200 | 1. 进入目标 episode，使首次请求失败。<br>2. 确认 error 状态。<br>3. 切换到其他 episode后再切回，或触发依赖重新执行。 | 1. 首次显示 `Motion data unavailable.` 且不无限 loading。<br>2. 失败 episode 会从 requested set 移除。<br>3. 后续重新发起请求；成功后缓存变为 ready 并显示曲线。 |
| PRIS-247-E2E-023 | 面板收起时当前与后续 episode 仍按设计加载 | 进入 episode 后立即收起 panel；upload 至少 5 个 episodes | 1. 页面加载后立即点击收起。<br>2. 观察 Network。<br>3. 等待请求完成后再次展开。 | 1. 收起仅控制可见性，不取消当前和后续 4 个 episode 的加载。<br>2. 再次展开复用已完成数据。<br>3. 不产生额外重复请求。 |
| PRIS-270-E2E-001 | 固定 App Topbar 不遮挡 QA Review 内容 | 部署包含 `6a24eff` 的环境；QA 用户登录 | 1. 进入 QA Review。<br>2. 从页面顶部滚动到底部再返回。<br>3. 展开/收起 Motion Panel。<br>4. 操作 Prev/Next。 | 1. Topbar 始终固定在顶部。<br>2. QA 页面首行、episode 信息和控制栏不被 topbar 遮挡。<br>3. 页面不存在额外空白或跳动。<br>4. Motion 功能正常。 |
| PRIS-270-E2E-002 | Dashboard pagination dots 不覆盖 fixed topbar | Dashboard 有可切换 pagination dots | 1. 打开 Dashboard。<br>2. 滚动页面使 carousel 靠近顶部。<br>3. 点击 dots 并观察层级。 | 1. Pagination dots 可点击。<br>2. dots 保持在页面内容层，不能显示在 topbar 上方。<br>3. topbar 菜单仍可点击。 |
| PRIS-270-E2E-003 | Desktop VLA sidebar 高度与内部滚动正确 | 部署 `origin/PRIS-270-vla-layout-v2`；viewport > 980px；sidebar 项目足够多 | 1. 打开 DataHub/VLA。<br>2. 改变浏览器高度。<br>3. 滚动 sidebar 和主内容。 | 1. Sidebar sticky top offset 为 79px。<br>2. 高度随 viewport 保持 `calc(100vh - 101px)`。<br>3. Sidebar 内容可独立纵向滚动。<br>4. divider 可见，主内容不被挤压。 |
| PRIS-270-E2E-004 | Mobile VLA 导航横向滚动且不遮挡内容 | 部署 PRIS-270 v2；viewport 390x844 | 1. 打开 DataHub/VLA。<br>2. 横向滑动顶部 navigation。<br>3. 选择 Data Labeling 和 Device Partners 项目。<br>4. 纵向滚动页面。 | 1. Navigation 位于 fixed topbar 下方并保持 sticky。<br>2. 仅 navigation 自身可横向滚动，页面无横向溢出。<br>3. section label 隐藏，圆点 divider 可见。<br>4. 选中项正确且内容未被遮挡。 |
| PRIS-270-E2E-005 | Mobile Upload scenario chips 与 subnav 联动 | 部署 PRIS-270 v2；至少有多个 scenario；viewport <= 980px | 1. 进入 Data Upload 非 Dashboard route。<br>2. 横向滑动 scenario bar。<br>3. 点击不同 scenario chip。<br>4. 切换 Upload/subnav 页面。 | 1. Desktop scenario list 隐藏，mobile scenario bar 显示。<br>2. Chip 可横向滚动，当前 scenario active 状态唯一且正确。<br>3. 点击后复用现有选择逻辑并刷新对应内容。<br>4. subnav 位于 `top: 133px`，不与 topbar/sidebar 重叠。 |
| PRIS-270-E2E-006 | PRIS-270 布局下 Motion tooltip 与全屏层级正确 | 部署 PRIS-270 v2；episode 有 motion data；桌面和移动端各执行一次 | 1. 从 DataHub 导航到 QA Review。<br>2. hover Motion 曲线。<br>3. 进入全屏再次 hover。<br>4. 退出全屏。 | 1. 普通模式 tooltip 不被 fixed/sticky navigation 裁剪或覆盖。<br>2. 全屏 tooltip 渲染于 fullscreen element 内并可见。<br>3. 退出全屏后 topbar、页面 offset 和滚动位置正常。 |

---

## 九、建议补充检查点

| 分类 | 检查点 | 预期/说明 |
|---|---|---|
| API | `/joint-states` response body 不应包含原始 MCAP bytes 或敏感路径 | 响应只返回前端渲染所需的左右臂 joint time-series，不泄露 bucket 内部路径、signed URL、token 或原始文件内容。 |
| API | 空数据场景应保持 `success=true` | `raw_mcap_path` 为空、GCS blob 不存在、无 JointState topic 等“无 motion data”场景不应被误判为系统错误；返回 `left=[]`、`right=[]`。 |
| API | 解析异常建议增加后端日志 | 日志应包含 `episode_id`、`raw_mcap_path`、异常类型，便于排查；不要输出敏感 token、Authorization header 或完整 signed URL。 |
| UI | Motion Data 按钮 active 状态明确 | 展开后按钮状态应清晰可见，用户能判断 panel 当前是展开还是收起。 |
| UI | Loading 状态不会永久停留 | 接口成功、失败、空数据都应结束 loading；网络异常时进入可控 error/empty 状态。 |
| UI | Error 状态文案可理解 | 请求失败、权限失败或解析失败时，页面应显示用户可理解的错误状态，例如 `Motion data unavailable.`。 |
| UI | Empty 状态建议显式提示 | 建议显示 `No motion data available.`，避免空 panel 被误认为页面坏了。 |
| UI | 左右臂图表 legend 在 joint 较多时不要遮挡曲线 | 多 joint 场景下 legend、tooltip、chart area 不应重叠到影响 QA reviewer 判断。 |
| 性能 | 后端请求时下载并解析 MCAP，大文件可能慢 | 如果线上数据量大，建议后续评估缓存、预计算或异步生成 motion summary，避免每次展开都触发重解析。 |
| 性能 | 前端默认加载当前并预取后续 4 个 episode | 这是当前明确设计；需监控并发请求、GCS 下载量、后端响应时间和浏览器内存，不能再按“panel 打开才请求”的旧预期验收。 |
| 性能 | 同一 episode 重复打开不重复请求 | 作为回归点保留，避免重复展开/收起造成接口放大和图表重复渲染。 |
| 交互 | 点击曲线只接受有效 `activeLabel` | 无有效点位或非数字 label 时不应改变视频时间；有效点击应同步全部当前视频。 |

---

## 十、回归范围

需要重点回归以下已有能力：

- QA Review 页面正常加载 upload 和 episode。
- 视频播放、暂停、seek、静音、全屏。
- Prev/Next episode 切换。
- 评分面板与提交 QA review。
- Firefox 视频支持提示逻辑。
- 移动端 QA Review 基础操作。
- 无 MCAP 或无 motion data 的老数据仍可正常 review。
- PRIS-270 fixed topbar 下的 Home、Dashboard、DataHub、Upload 与 QA Review 顶部 offset。
- Desktop VLA sidebar 的 sticky、高度和内部滚动。
- Mobile VLA navigation、scenario chips 与 upload subnav 的横向滚动和层级。
