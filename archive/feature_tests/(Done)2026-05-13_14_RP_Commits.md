# app-prismax-rp / app-prismax-rp-backend — 2026-05-13 ~ 2026-05-14 改动分析与测试策略

**日期范围：** 2026-05-13 00:00:00 ~ 2026-05-14 23:59:59（+0800）  
**涉及仓库：** `app-prismax-rp`、`app-prismax-rp-backend`  
**分析基线：** 两仓 `git fetch --all` 后 `git log --all`  
**合并落点：** 前端 `origin/testing` @ `2d13bd0`；后端 `origin/testing` @ `87197a1`

---

## 一、Commit 清单

### 1.1 app-prismax-rp

| 时间 | Hash | 作者 | 说明 |
|------|------|------|------|
| 2026-05-13 02:00 | `3e1b643` | Chris | RoboticData episode 详情弹窗展示平均时长 |
| 2026-05-13 05:17 | `7d87c86` | Aparna | PRIS-191：Operator Dashboard 展示 episode / upload 时长 |
| 2026-05-13 15:56 | `2d01d38` | Aparna | PRIS-178：上传任务详情弹窗改版 |
| 2026-05-14 03:32 | `2a627c3` | aparna-prismax | Merge PR #38 `PRIS-178-upload-details` |
| 2026-05-14 08:52 | `9fb994d` | Aparna | PRIS-202：QA 提交成功弹窗 |
| 2026-05-14 10:08 | `7770dd1` | Aparna | PRIS-191：Dashboard UI 增强 |
| 2026-05-14 10:23 | `41a5f44` | Aparna | PRIS-191：移动端适配；移除 UploadHistory |
| 2026-05-14 10:24 | `2d13bd0` | aparna-prismax | Merge PR #39 `PRIS-191-operator-dashboard` |

### 1.2 app-prismax-rp-backend

| 时间 | Hash | 作者 | 说明 |
|------|------|------|------|
| 2026-05-13 01:59 | `6d31493` | Chris | 下载列表返回 `video_duration_hours`；worker 默认端口 8080 |
| 2026-05-13 04:41 | `607e0a3` | Aparna | PRIS-191：Dashboard 使用 `video_duration_hours` 统计 |
| 2026-05-13 15:58 | `44fb4a3` | Aparna | PRIS-178：三摄任务预览 API |
| 2026-05-14 03:53 | `592dea0` | aparna-prismax | Merge PR #33 `PRIS-178-upload-details` |
| 2026-05-14 08:53 | `d15e4db` | Aparna | PRIS-202：QA 成功弹窗「不再显示」用户设置 API |
| 2026-05-14 10:25 | `c822a57` | Aparna | PRIS-191：Upload QA 分数改为轮次共识均值 |
| 2026-05-14 10:26 | `87197a1` | aparna-prismax | Merge PR #34 `PRIS-191-operator-dashboard` |

### 1.3 主题与依赖

| 主题 | 前端 | 后端 | 说明 |
|------|------|------|------|
| PRIS-178 上传任务详情 | `UploadInfoModal` | `GET /data/tasks/uploadable-task-preview/<task_id>` | 上传前查看三摄示例与任务元数据 |
| PRIS-191 Operator Dashboard | `UploadDashboard`、`DataHub` | `/vla/operator-dashboard/*`、`/vla/admin/operator-dashboard/*` | 替代独立 History 页，聚合指标与上传列表 |
| PRIS-202 QA 提交反馈 | `QAReviewSuccessModal` | `POST /data/user-settings/dont-show-again-qa-review-success-modal` | 提交后弹窗与偏好持久化 |
| 时长字段贯通 | `EpisodeDetailModal`、Dashboard | `video_duration_hours`、下载列表字段 | 依赖 worker 写入 episode 时长 |
| 本地/部署小改 | — | worker `PORT` 默认 8080 | 仅影响本地或未显式设 `PORT` 的部署 |

---

## 二、改动详细分析

### 2.1 PRIS-178 — 上传任务详情弹窗（`UploadInfo` → `UploadInfoModal`）

#### 前端

- `UploadInfo.js` / `UploadInfo.module.css` 删除；新增 `UploadInfoModal.js` + 样式（Portal 挂 `#root`）。
- `Upload.js` 改为引用 `UploadInfoModal`；打开任务详情时拉取预览视频。
- 预览请求：`GET ${PRISMAX_DATA_PIPELINE_URL}/data/tasks/uploadable-task-preview/${task_id}`。
- 返回 `data.videos` 后按文件名排序：`cam_high`（不含 left/right）→ `left` → `right`；同档用稳定 hash 打散。
- 多路 `<video>` 在 `loadedmetadata` 后同步 `currentTime=0` 并 `play()`（`muted`、`loop`、`playsInline`）。
- 左侧缩略列表可滚动；未到底时显示 “1 more video” 提示，点击平滑下滚。
- 右侧展示 Objectives / Action / Task variations / General variations / Notes；无预览时显示 `No preview available`。
- Footer：`View guidelines`（当前无绑定）、`Upload data` 回调 `onUpload`；遮罩或关闭按钮调用 `onClose`。

#### 后端

- 路由：`GET /data/tasks/uploadable-task-preview/<int:task_id>`（`app_prismax_data_pipeline/app.py`）。
- 取该 `task_id` 下最早 `upload_id` 的首条 `DERIVED_READY` episode。
- 从 `derived_bucket` + `derived_video_folder_path`（或 `raw_video_folder_path` 替换 `raw/`→`derived/`）列举 `.mp4`，最多 3 条。
- URL 优先 CDN（`build_derived_cdn_url`），否则 signed URL。
- 无 episode / 无 bucket / 无路径：仍 `success: true`，`videos: []`。

---

### 2.2 PRIS-191 — Operator Dashboard 与 Upload History 收敛

#### 信息架构

- `DataHub` 子导航由 **Upload / History / Dashboard** 改为 **Upload / Dashboard**；`UploadHistory.js` 及样式删除。
- `UploadWorkspace` 在 `/data/upload/dashboard` 渲染 `UploadDashboard`，否则为 `Upload`。
- **遗留路由：** 顶层仍有 `path="history"` → `Navigate` 到 `/data/upload/history`，但子工作区不再渲染 History 组件；访问旧 URL 可能落到 Upload 页或出现空白/路由异常，需回归。

#### 前端 `UploadDashboard`

- 时间范围：`7d` / `30d` / `90d` / `1y` / `all`；切换重置分页与已选 upload。
- 指标卡：Avg QA Score（含环比 delta）、Total Episodes（含环比 %）、Avg Hrs / Day。
- 图表：QA score trend（Y 轴 70–100）、Episode hrs / day；`isAnimationActive={false}`。
- 上传表：Upload ID、Task、Upload time、Episodes、**Total hrs**、Quality score、Pass/Fail、Continue（`UPLOADING` 且非 admin）。
- 机器筛选：原生 `<select>` 改为 `MachineDropdown`；分页 `page_size=5`。
- 行点击打开 `EpisodeDrawer`：episode 列表、Accepted/Rejected 筛选、失败原因展开；子行展示 `video_duration_seconds` 与 `· 3 cams`。
- Admin 模式：`adminUserId` 存在时请求 `/vla/admin/operator-dashboard/*` 并带 `user_id`。

#### 后端 Operator Dashboard（`app_prismax_user_management/app.py`）

| 接口 | 鉴权 | 主要参数 |
|------|------|----------|
| `GET /vla/operator-dashboard/summary` | `Authorization: Bearer <gatewayToken>` 或 `?token=` | `duration` |
| `GET /vla/operator-dashboard/uploads` | 同上 | `duration`, `machine_id`, `page`, `page_size`（1–50） |
| `GET /vla/admin/operator-dashboard/summary` | JWT + `role=admin` | `user_id`, `duration` |
| `GET /vla/admin/operator-dashboard/uploads` | JWT + `role=admin` | `user_id`, `duration`, `machine_id`, `page`, `page_size` |

**时长统计（`607e0a3`）**

- Episode：`video_duration_seconds = round(video_duration_hours * 3600, 1)`（小时为 0 则 `null`）。
- Upload 行：`total_hrs` 为下属 episode 秒数之和换算为小时（保留 2 位小数）。
- Summary：`episode_hrs_trend` 按时间桶 `SUM(video_duration_hours)`；`avg_hrs_per_day` 在固定窗口为 `total_hrs / 天数`，`all` 为 `total_hrs / max(首条上传至今天数, 1)`。
- 趋势 X 轴：`7d` 为星期缩写；`30d`/`90d` 为 `dd mon`；`1y`/`all` 为 `yyyy mon`。

**QA 分数（`c822a57`）**

- 不再取「最近一条 `data_qa_sessions`」或 `review_result.upload_score` 单值。
- 仅当 upload `status` 为 `REVIEW_FIRST/SECOND/THIRD_ROUND_SUCCEEDED` 时，取 **最高已完成 `qa_round` 内所有 reviewer 的 `AVG(qa_score)::int`**；未达成功态为 `NULL`（前端显示 `—`）。

---

### 2.3 PRIS-202 — QA Review 提交成功弹窗

#### 前端

- 新增 `QAReviewSuccessModal`；`DataQAReview` 在 upload 级 review 提交成功后：
  - `userSettings.dont_show_again_qa_review_success_modal === true` → 沿用 `CustomNotification`，`onDismiss` 走 `handleLoadNextEpisodeAfterSubmit`；
  - 否则 `setShowQAReviewSuccessModal(true)`。
- 弹窗：成功文案、±15% 共识得 100 分说明；**Continue reviewing** / **My earnings**（后者当前 `onClick` 为空）。
- **Don't show again**：勾选后 `POST /data/user-settings/dont-show-again-qa-review-success-modal`，并更新 context `dont_show_again_qa_review_success_modal`。
- `handleLoadNextEpisodeAfterSubmit`：优先同 task 其他 upload，否则跨 task；无剩余则 `/data/review`；`loadUploadEpisodes` + `fetchUploads` + 约 1.5s 等待。
- Validator Access Modal 的 `dont_show_again_validator_access_modal` 与 QA 成功弹窗偏好分离。

#### 后端

- `POST /data/user-settings/dont-show-again-qa-review-success-modal`：校验 token，合并 `users.settings` JSON：`dont_show_again_qa_review_success_modal: true`。

---

### 2.4 时长字段 — RoboticData 与 Data Pipeline

#### 前端 `3e1b643`

- `RoboticDataWorkspace` 映射 `durationHours: episode.video_duration_hours`；同 scenario 有效正值求平均。
- `EpisodeDetailModal`「Avg duration」由固定 `TBD` 改为 `formatDurationHours`（无效/≤0 为 `-`；整数无小数，否则一位小数 + `h`）。

#### 后端 `6d31493`

- `get_downloadable_uploads` 查询增加 `e.video_duration_hours`。
- `app_prismax_data_worker/worker.py` 默认 `PORT` 由 8085 改为 **8080**（未设环境变量时）。

---

## 三、测试策略

### 3.1 测试分层与优先级

| 层级 | 范围 | 优先级 |
|------|------|--------|
| API / 契约 | 预览 API、Dashboard 四接口、用户设置 API、下载列表 `video_duration_hours` | P0 |
| 前端 E2E | Upload 详情弹窗、Dashboard 全链路、QA 提交后弹窗与跳转 | P0 |
| 数据一致性 | 时长加总、QA 轮次均值 vs DB、三摄 URL 可播放 | P0 |
| 回归 | 上传流程、QA 提交流程、RoboticData 下载、旧 History URL | P1 |
| 兼容 / 体验 | 移动端 Dashboard、Firefox QA 视频提示、图表无动画 | P2 |

**建议角色：** Operator（Dashboard + Upload）、QA（Review 提交）、Admin（代看 Operator Dashboard）、普通用户（无 Data Hub 权限）。

**建议数据：** 至少 1 个含 `DERIVED_READY` 三摄 MP4 的 task；1 个无衍生视频的 task；多 reviewer 完成 QA 的 upload；`UPLOADING` 中断 upload；`video_duration_hours` 有值/为 0/为 NULL 的 episode 混合。

---

### 3.2 PRIS-178 — 上传任务详情弹窗

| # | 测试点 | 步骤要点 | 预期 |
|---|--------|----------|------|
| F178-01 | 打开弹窗 | Upload 页打开任务详情 | 遮罩 + 标题；请求 preview API |
| F178-02 | 三摄预览 | 有 3 路 MP4 | 排序 high → left → right；多路同步播放 |
| F178-03 | 少于 3 路 | 仅 1–2 个 MP4 | 仅展示存在项；不报错 |
| F178-04 | 无预览 | task 无 `DERIVED_READY` | `No preview available`；其余元数据仍展示 |
| F178-05 | API 失败 | 断网或 5xx | 加载结束；空状态；Upload 主流程可用 |
| F178-06 | 元数据 | objectives / action / variations / notes | 标签与列表解析正确；空块隐藏 |
| F178-07 | 关闭 | 遮罩 / ✕ | 关闭且不触发上传 |
| F178-08 | Upload data | 点主按钮 | `onUpload`；进入原上传流程 |
| F178-09 | Guidelines | View guidelines | 记录当前是否无跳转（产品预期） |

**API**

| # | 测试点 | 预期 |
|---|--------|------|
| A178-01 | 合法 `task_id` | `success: true`；`videos` ≤3；`url` 可 GET |
| A178-02 | 无 episode | `videos: []` |
| A178-03 | 无 derived 路径 | `videos: []`；含 `episode_id` 时字段一致 |
| A178-04 | 非法 task_id | 不 500；空列表或合业务码 |

---

### 3.3 PRIS-191 — Operator Dashboard

#### 3.3.1 Summary

| # | 测试点 | 预期 |
|---|--------|------|
| D191-01 | 默认 `30d` | 三指标 + 两图有数据或空态文案 |
| D191-02 | 切换 `7d/90d/1y/all` | 请求带 `duration`；卡片与图同步 |
| D191-03 | Avg QA | 仅 `REVIEW_*_ROUND_SUCCEEDED` 的 upload 参与；与 SQL 手算均值一致 |
| D191-04 | QA delta | 有上期数据时显示 ↑/↓ |
| D191-05 | Total episodes | 计数为 episode 行数；环比 % 合理 |
| D191-06 | Avg hrs/day | 固定窗口 = 总时长/天数；`all` 按首条上传跨度 |
| D191-07 | QA trend | Y 70–100；无数据时 “No QA data…” |
| D191-08 | Hrs trend | 单位为 h；与 `SUM(video_duration_hours)` 一致 |

#### 3.3.2 Uploads 表与 Drawer

| # | 测试点 | 预期 |
|---|--------|------|
| D191-09 | 分页 | `page_size=5`；翻页总数正确 |
| D191-10 | 机器筛选 | Dropdown 筛选；重置页码 |
| D191-11 | Total hrs | 与 episode `video_duration_seconds` 汇总一致 |
| D191-12 | Quality score | 未成功 QA 为 `—`；成功为轮次均值 |
| D191-13 | Pass/Fail | 与 `episode_summary` 一致 |
| D191-14 | Continue | 仅 `UPLOADING` 且非 admin；跳转带 `resumeUpload` state |
| D191-15 | Drawer | 筛选 all/accepted/rejected；失败展开原因 |
| D191-16 | Episode 时长 | 有 `video_duration_seconds` 显示秒数 + `· 3 cams` |
| D191-17 | Escape | Drawer `Escape` 关闭 |

#### 3.3.3 导航与 History 移除

| # | 测试点 | 预期 |
|---|--------|------|
| D191-18 | 子导航 | 仅 Upload、Dashboard |
| D191-19 | 旧 URL `/data/upload/history` | 无 History UI；不白屏；记录实际落点 |
| D191-20 | 书签 `/data/history` | 重定向行为符合当前路由表 |
| D191-21 | Admin 代看 | `user_id` 正确；非 admin JWT 403 |

#### 3.3.4 鉴权与异常

| # | 测试点 | 预期 |
|---|--------|------|
| D191-22 | 无 token | 400 / 401 |
| D191-23 | 非法分页 | 400 |
| D191-24 | Admin 缺 `user_id` | 400 |

---

### 3.4 PRIS-202 — QA 提交成功弹窗

| # | 测试点 | 预期 |
|---|--------|------|
| Q202-01 | 首次提交成功 | 出现成功弹窗（非仅 toast） |
| Q202-02 | Continue reviewing | 关闭弹窗；加载下一 upload；URL `?upload=` 更新 |
| Q202-03 | 同 task 多 upload | 优先切到其他 upload |
| Q202-04 | 无其他 upload | 跨 task 或回 `/data/review` |
| Q202-05 | Don't show again | 勾选并继续；settings 持久化 |
| Q202-06 | 再次提交 | 短通知 + dismiss 后自动下一集 |
| Q202-07 | 未勾选 DSA | 仍显示完整弹窗 |
| Q202-08 | 提交失败 | 无成功弹窗；原表单状态合理 |
| Q202-09 | My earnings | 记录是否仍无跳转 |
| Q202-10 | Validator Access DSA | 与 QA 成功 DSA 互不覆盖 |

**API：** 无 token → 400；非法 token → 401；合法 POST 后 DB `settings` 含 `dont_show_again_qa_review_success_modal: true`。

---

### 3.5 时长字段 — RoboticData 与 Pipeline

| # | 测试点 | 预期 |
|---|--------|------|
| T-01 | 下载列表 API | 响应含 `video_duration_hours` |
| T-02 | Episode 详情 Avg duration | 同 scenario 平均；无数据为 `-` |
| T-03 | 非法/0/负时长 | 不参与平均；展示 `-` |
| T-04 | Worker 端口 | 未设 `PORT` 时监听 8080；健康检查通过 |

---

### 3.6 跨模块回归（P1）

- Upload：选机、选 task、manifest、并发上传、失败重试。
- Data QA Review：episode 打分、batch、note、多轮状态；提交 payload `qa_score` 与 rubric 一致。
- RoboticData：Episode 详情、选中、manifest 上限（参见 `PRIS_SPRINT_19.MD`）。
- Data Hub 权限：非 operator/qa 不可进；QA 菜单限制仍生效。
- `CustomNotification`、Firefox 视频提示、ValidatorAccessModal 与本次改动无冲突。

---

### 3.7 测试环境与执行建议

**环境**

- 前端对接 **testing** 对应 Data Pipeline + User Management；CDN / GCS 可访问衍生 MP4。
- DB：`data_episodes.video_duration_hours` 已由 worker 回填或测试造数。
- 账号：Operator、QA、Admin 各一；QA 账号可完成 upload 级 submit。

**执行顺序**

1. 后端契约（预览、Dashboard、DSA API）+ SQL 对照 QA 分与时长。  
2. PRIS-178 / PRIS-191 / PRIS-202 前端主路径。  
3. History 旧链路与 Admin 代看。  
4. Upload + QA + RoboticData 回归。

**缺陷记录建议字段：** 仓库、commit、角色、task_id / upload_id、浏览器、接口响应片段、DB 快照（upload status、qa_round、sessions 条数）。

---

## 四、风险与关注点

1. **History 移除与遗留路由：** 子导航已删 History，但顶层仍可能重定向到 `/data/upload/history`；需确认产品期望（重定向到 Dashboard 或 Upload）并防书签失效。
2. **QA 分数口径变更：** Dashboard 由「最近 session」改为「最高轮次 reviewer 均值」；与运营/数据团队确认展示定义，并与发分逻辑对照。
3. **时长依赖 worker：** `video_duration_hours` 缺失时 Dashboard / RoboticData 显示 `—`；区分「未回填」与「真实为 0」。
4. **预览 episode 选取：** 每 task 固定「最早 upload 的首条 DERIVED_READY」；多 upload 时示例是否代表最新策略需产品确认。
5. **PRIS-202 My earnings：** 按钮暂无行为，避免误判为缺陷。
6. **Worker 默认端口：** 本地或脚本若写死 8085 需同步，否则联调失败。

---

## 五、参考

- 同目录：`PRIS_SPRINT_19.MD`（RoboticData Episode 详情与 manifest 上限）
- 同目录：`3_Mcap Data/Data_QA_Review_Logic.md`（QA 轮次与 `data_qa_sessions`）
- 同目录：`3_Mcap Data/Operator_Logic.md`（Operator 角色与申请）
