# PRIS Sprint 19 — QA 特性分析与测试策略

**日期：** 2026-05-12
**Commit：** `5d3e91af38dff93b955fb465e3287795050989f1`
**作者：** Chris
**提交信息：** updated for data download
**涉及模块：** `app-prismax-rp` / RoboticData

---

## 一、改动概览


| 文件                                                         | 类型  | 净变动       |
| ---------------------------------------------------------- | --- | --------- |
| `src/components/RoboticData/EpisodeDetailModal.js`         | 新增  | +224 行    |
| `src/components/RoboticData/EpisodeDetailModal.module.css` | 新增  | +427 行    |
| `src/components/RoboticData/RoboticDataWorkspace.js`       | 修改  | +86 / -14 |
| `src/components/RoboticData/RoboticDataAdmin.js`           | 修改  | +4 / -4   |


---

## 二、改动详细分析

### 2.1 新增组件：`EpisodeDetailModal`

使用 `ReactDOM.createPortal` 挂载到页面 `#root`，点击遮罩层可关闭弹窗。

#### 弹窗结构

**Header**

- 显示任务标题（`taskTitle` → `task.scenario` → `Task {taskId}`，依次降级）
- 显示当前数据集中 episode 总数
- 右上角关闭按钮

**左侧面板**

- 预览媒体区：优先播放视频（`previewVideoUrl`），降级显示图片（`previewImageUrl`），再降级显示占位播放图标
- Episode ID 徽章 + Quality Score 徽章
- 文件清单：MP4 数量（`mp4Count`）× 数量、MCAP 数量（`mcapCount`）× 数量
- 数据集统计：
  - 相似 episodes 数（同 scenario 下）
  - 平均质量分（`taskAverageQuality`）
  - 总 episodes 数（`uploadEpisodeCount`）
  - 平均时长（当前固定显示 "TBD"）

**右侧面板**

- 任务描述文本（`task.details_description` → `task.description` → `task.notes`，依次降级）
- Overview 表格：Objectives / Action / Variations / Notes
- Tags 区域（当前为空占位）

**Footer**

- 展示本 episode 可下载文件总数（`mp4Count + mcapCount`）
- "Download episode" 按钮 → 触发单集直接下载并关闭弹窗
- "Select episode / Selected" 切换按钮 → 切换选中状态并关闭弹窗

---

### 2.2 `RoboticDataWorkspace.js` 改动

#### 交互行为变更（重要）

> **原行为**：点击视频卡片 → 选中/取消该 episode
> **新行为**：点击视频卡片 → 打开该 episode 的详情弹窗

选中/取消操作移入弹窗内的 "Select episode" 按钮。

#### 新增状态与计算逻辑

- `activeEpisodeDetailId`：记录当前打开弹窗的 episode ID
- `activeEpisodeDetail`（useMemo）：根据 ID 聚合以下上下文数据：
  - `scenarioEpisodeCount`：同 scenario（taskTitle）下的 episode 总数
  - `uploadEpisodeCount`：同 `uploadId` 批次下的 episode 总数
  - `taskAverageQuality`：同 scenario 下所有有效质量分的均值

#### Episode 数据字段新增

每个 episode 对象新增两个字段，用于弹窗中文件数展示：

```js
mp4Count: String(episode.raw_video_folder_path || '').trim() ? 3 : 0
mcapCount: String(episode.raw_mcap_path || '').trim() ? 1 : 0
```

#### Manifest 下载上限调整


| 项目                            | 旧值                                        | 新值                                                                     |
| ----------------------------- | ----------------------------------------- | ---------------------------------------------------------------------- |
| `MANIFEST_DOWNLOAD_MAX_FILES` | 1000                                      | **800**                                                                |
| 新增常量 `FILES_PER_EPISODE`      | —                                         | **4**（3 MP4 + 1 MCAP）                                                  |
| 文件数计算                         | `selectedVideoCount + selectedMcapCount`  | `selectedEpisodeCount * FILES_PER_EPISODE`                             |
| 超限提示文案                        | "JSON download is limited to 1000 files." | "manifest.json is limited to 800 files. Please select fewer episodes." |


#### API 示例代码优化

Python 下载脚本增加了进度输出：

```python
assets = []
for sample in session["samples"]:
    ...
    assets.append((asset, sample_cookie))

print(f"Starting download: {len(assets)} files")
for index, (asset, sample_cookie) in enumerate(assets, start=1):
    print(f"Downloading {index}/{len(assets)}: {asset['relative_path']}")
    ...
print("Download complete")
```

#### 字段名统一

全文将展示字段 `episode.episodeKey` 统一改为 `episode.episodeId`。

---

### 2.3 `RoboticDataAdmin.js` 改动

同步将 Admin 视图中的 `episode.episode_key` / `episodeKey` 改为 `episode.episode_id` / `episodeId`，与 Workspace 保持一致，共涉及 4 处。

---

## 三、测试策略

### 3.1 Episode 详情弹窗（EpisodeDetailModal）

#### 功能测试


| #    | 测试点                                         | 预期结果                                          |
| ---- | ------------------------------------------- | --------------------------------------------- |
| F-01 | 点击任意视频卡片                                    | 弹窗打开，显示对应 episode 信息                          |
| F-02 | 弹窗 Header — 有 previewVideoUrl               | 左侧播放视频，autoPlay + muted + loop                |
| F-03 | 弹窗 Header — 无视频但有 previewImageUrl           | 显示预览图片                                        |
| F-04 | 弹窗 Header — 无视频无图片                          | 显示播放占位图标                                      |
| F-05 | Episode ID 徽章                               | 显示正确的 `episodeId`                             |
| F-06 | Quality Score 徽章 — 有值                       | 格式正确（整数不显示小数，一位小数正常显示）                        |
| F-07 | Quality Score 徽章 — 无值 / null                | 显示 `-`                                        |
| F-08 | MP4 文件数 — `raw_video_folder_path` 有值        | 显示 `x3`                                       |
| F-09 | MP4 文件数 — `raw_video_folder_path` 为空        | 显示 `x0`                                       |
| F-10 | MCAP 文件数 — `raw_mcap_path` 有值               | 显示 `x1`                                       |
| F-11 | MCAP 文件数 — `raw_mcap_path` 为空               | 显示 `x0`                                       |
| F-12 | Footer 文件总数                                 | `mp4Count + mcapCount` 的正确和                   |
| F-13 | "Similar episodes" — 数量 < 100               | 显示精确数字                                        |
| F-14 | "Similar episodes" — 数量 ≥ 100               | 显示 `100+` / `200+` 等向下取整格式                    |
| F-15 | "Avg quality" — 同 scenario 有多个 episode      | 显示算术平均值（一位小数）                                 |
| F-16 | "Avg quality" — 无有效质量分                      | 显示 `-`                                        |
| F-17 | "Total episodes" 统计                         | 显示同 `uploadId` 批次的 episode 数量                 |
| F-18 | Overview 表格 — task 有值                       | 正确显示 Objectives / Action / Variations / Notes |
| F-19 | Overview 表格 — 含分号分隔值                        | 转换为逗号分隔显示                                     |
| F-20 | Overview 表格 — 字段为空                          | 显示 `-`                                        |
| F-21 | Description — `task.details_description` 有值 | 优先显示                                          |
| F-22 | Description — 无任何描述字段                       | 显示 `No description provided.`                 |
| F-23 | 弹窗标题 — `taskTitle` 有值                       | 优先显示 `taskTitle`                              |
| F-24 | 弹窗标题 — 无 `taskTitle` 但有 `task.scenario`     | 显示 `task.scenario`                            |
| F-25 | 弹窗标题 — 均无值                                  | 显示 `Task {taskId}` 或 `Task -`                 |


#### 关闭与交互测试


| #    | 测试点                               | 预期结果                            |
| ---- | --------------------------------- | ------------------------------- |
| C-01 | 点击右上角 ✕ 按钮                        | 弹窗关闭，`activeEpisodeDetailId` 清空 |
| C-02 | 点击遮罩层（弹窗外区域）                      | 弹窗关闭                            |
| C-03 | 点击弹窗内部区域                          | 弹窗不关闭                           |
| C-04 | 点击 "Download episode"             | 触发单集下载，弹窗关闭                     |
| C-05 | 点击 "Select episode"（未选中状态）        | 该 episode 加入已选列表，弹窗关闭           |
| C-06 | 点击 "Selected"（已选中状态）              | 该 episode 从已选列表移除，弹窗关闭          |
| C-07 | 弹窗打开时，底层列表的 selectedEpisodeIds 变化 | 弹窗内 isSelected 状态同步更新           |


#### 边界与异常测试


| #    | 测试点                                                 | 预期结果                               |
| ---- | --------------------------------------------------- | ---------------------------------- |
| E-01 | `activeEpisodeDetailId` 对应的 episode 在 taskRows 中不存在 | `activeEpisodeDetail` 为 null，弹窗不渲染 |
| E-02 | `#root` 元素不存在                                       | 组件返回 null，不抛出异常                    |
| E-03 | episode 对象为 null                                    | 组件返回 null                          |
| E-04 | 弹窗打开期间切换任务分组（折叠/展开）                                 | 弹窗不受影响，保持打开                        |
| E-05 | 快速连续点击不同视频卡片                                        | 弹窗始终展示最后一次点击的 episode              |


---

### 3.2 交互行为变更回归（视频卡片点击）


| #    | 测试点                      | 预期结果                           |
| ---- | ------------------------ | ------------------------------ |
| B-01 | 点击视频卡片 → **不再**直接选中      | 卡片不应切换选中样式                     |
| B-02 | 选中/取消仅通过弹窗内按钮操作          | 底部已选 chip 列表正确更新               |
| B-03 | Admin 视图 episode chip 显示 | 显示 `episodeId` 而非 `episodeKey` |


---

### 3.3 Manifest 下载上限


| #    | 测试点                                | 预期结果                                                                        |
| ---- | ---------------------------------- | --------------------------------------------------------------------------- |
| D-01 | 选中 200 个 episodes（= 800 文件，恰好达到上限） | 允许下载，无警告                                                                    |
| D-02 | 选中 201 个 episodes（= 804 文件，超出上限）   | 弹出警告："manifest.json is limited to 800 files. Please select fewer episodes." |
| D-03 | 选中 199 个 episodes（= 796 文件，低于上限）   | 正常进入下载流程                                                                    |
| D-04 | 旧上限（1000 文件 = 250 episodes）已失效     | 250 episodes 应触发超限警告                                                        |


---

### 3.4 回归测试范围

- 单集直接下载流程（`performDirectDownload`）
- Manifest JSON 下载流程
- API Package 下载流程
- 已选 episode chip 列表的增删
- Admin 视图 episode 信息展示
- 各类数据为空/缺失时的降级显示

---

### 3.5 测试环境要求

- 数据集中需准备以下类型的 episode：
  - 有 `raw_video_folder_path`（mp4Count = 3）
  - 无 `raw_video_folder_path`（mp4Count = 0）
  - 有 / 无 `raw_mcap_path`
  - 有 / 无预览视频 URL
  - 有 / 无预览图片 URL
  - 质量分为 null、整数、浮点数
- 同一 scenario 下需有多个 episodes 用于验证 "Similar episodes" 统计
- 需准备超过 200 个 episode 可供选择以验证下载上限

