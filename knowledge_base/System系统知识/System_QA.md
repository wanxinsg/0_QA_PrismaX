# QA 审阅页 — 测试策略文档

**分析范围**：`app-prismax-rp`（frontend）+ `app-prismax-rp-backend`（backend）`testing` 分支  
**当前版本**：v3.2（截至 2026-04-23）

---

## 1. 功能概述

QA 审阅页在原有基础上持续迭代，截至当前版本完成以下九件事：

1. **QA 评审维度升级（v1 → v2）**：Gate 维度从 6 项缩减为 4 项，Score 维度命名重构（5 项保留，语义更精准），前后端同步切换。
2. **校验者准入弹窗（ValidatorAccessModal）**：新增一个在用户点击"提交审阅"时弹出的引导弹窗，告知用户当前角色的月度审阅权限和剩余名额，同时提供"不再显示"能力，提升 Amplifier/Innovator 用户的评审体验。
3. **QA 多集抽样 + per-episode 严格校验**：抽样策略改为按比例抽取（最多 5%，最少 5 条），每个被抽中的 episode 需独立填写评分，提交 payload 从"单条共享 result"升级为"每 episode 一条 result"，服务端对 `episode_vote`、`episode_score`、`upload_vote`、`upload_score` 均做计算一致性强校验。
4. **QA 列表与页面加载提速**：后端 `get_qa_uploads` 移除多余 JOIN/GROUP BY，仅返回轻量字段；前端 DataHub 在非上传路由时跳过机器列表请求，减少首屏冗余 API 调用。
5. **Expert QA Upload 选择器**：在 QA 审阅页为 `expert qa` 及 `super qa` 角色新增 Upload 下拉选择器，可在同一 Task 下切换不同 Upload 批次；支持 `?upload=<id>` URL 参数深链，选择变更同步写入 URL（`replace: true`）；选择器被批次锁保护。
6. **Episode 切换视频自动归零**：切换当前 Episode 时自动将视频 `currentTime` 复位为 0 并停止播放，修复原来切换 episode 后视频从上次进度继续的 bug。另修复 Scenario 下拉因缺少 `dataTasks` prop 而无法正常显示的问题。
7. **DataReviewHub 正式上线**：新 QA 任务入口 `DataReviewHub` 完整实装并合入主分支（PR #33）。采用卡片式布局，以 `upload_id` 为卡片主键，每张卡片展示任务信息、Upload ID（super/expert qa 可见）、视频预览（懒加载，调用 `GET /data/qa/uploads/preview-urls`）。路由为 `/data/review`，旧 `DataReviewTaskHub.js` / `DataReviewTaskHubV2.js` 已删除。
8. **Expert QA 批次评审模式**：`expert qa` 可以任意浏览 Episode、逐集"Add to batch / Remove from batch"，自由积累待评集合后，通过"Submit selected episodes (N)"按钮一次性提交整批。Upload 选择器和 Round Tag 对 `isAdvancedQa`（expert qa OR super qa）可见。`super qa` 保持顺序抽样提交模式。
9. **requestedUploadId 降级流程优化**：当 `requestedUploadId` 不在 `filteredUploads` 中时，前端同步将 URL `?upload=` 参数更新为实际选中的 `preferredUploadId`，并显示 warning 通知（"The requested upload was not available for review. Redirecting to a similar upload."）。

---

## 2. 完整业务逻辑分析

### 2.1 QA 角色体系与访问控制

系统存在两套角色维度，互不干扰：


| 维度                | 字段                 | 值                                                                           | 说明                                  |
| ----------------- | ------------------ | --------------------------------------------------------------------------- | ----------------------------------- |
| **系统角色**（QA 工作人员） | `users.user_role`  | `qa` / `senior qa` / `expert qa` / `super qa`                               | 控制可审阅的 Upload 轮次、队列优先级及 UI 功能可见性    |
| **会员等级**（普通用户）    | `users.user_class` | `Explorer Member` / `Amplifier Member` / `Innovator MemberAmplifier Member` | 控制 ValidatorAccessModal 展示内容与月度审阅配额 |


**角色特性对照：**


| QA 角色           | Round Tag 可见 | Upload 选择器可见             | Upload ID 可见（DataReviewHub） | 评审模式                            |
| --------------- | ------------ | ------------------------ | --------------------------- | ------------------------------- |
| `qa`            | ✗            | ✗                        | ✗                           | 顺序抽样提交                          |
| `senior qa`     | ✓            | ✗                        | ✗                           | 顺序抽样提交                          |
| `**expert qa`** | ✓            | ✓（当 filteredUploads > 1） | ✓                           | **自由批次模式**（Add/Remove/Finalize） |
| `super qa`      | ✓            | ✓（当 filteredUploads > 1） | ✓                           | 顺序抽样提交 + Upload 切换              |


**访问控制规则**：

- `GET/POST /data/qa/uploads`* 系列接口：需 `user_role ∈ {qa, senior qa, expert qa, super qa}`（`QA_ALLOWED_ROLES`），否则 403。
- `GET /data/qa/uploads/preview-urls`：需 `user_role ∈ QA_ALLOWED_ROLES`，否则 403。
- `GET /data/qa/get-validator-access-data`：仅需有效 Bearer token（任何已登录用户），无 QA 角色要求。

---

### 2.2 Upload 状态机与多轮 QA 流转

Upload 的 QA 状态决定其处于哪一轮审阅，系统使用严格状态机驱动：

```
                        ┌──────────────────────┐
                        │     DERIVED_READY     │  ← 初始状态
                        └──────────┬───────────┘
                                   │ 3 名 qa 提交（round 1）
                    ┌──────────────┴──────────────┐
                    │ 无分歧（gate一致 AND score差<30）│ 有分歧
                    ▼                             ▼
     REVIEW_FIRST_ROUND_SUCCEEDED    REVIEW_FIRST_ROUND_FAILED
                                                  │
                                                  │ 2 名 senior qa 提交（round 2）
                                   ┌──────────────┴──────────────┐
                                   │ 无分歧                      │ 有分歧
                                   ▼                             ▼
                    REVIEW_SECOND_ROUND_SUCCEEDED  REVIEW_SECOND_ROUND_FAILED
                                                              │
                                                              │ 1 名 expert qa 提交（round 3）
                                                              ▼
                                                  REVIEW_THIRD_ROUND_SUCCEEDED
```

**角色与可见队列的对应关系**（`_get_qa_queue_rules`）：


| QA 角色       | 优先处理                                | 次优先                                | 最低优先                   |
| ----------- | ----------------------------------- | ---------------------------------- | ---------------------- |
| `qa`        | DERIVED_READY（round 1）              | —                                  | —                      |
| `senior qa` | REVIEW_FIRST_ROUND_FAILED（round 2）  | DERIVED_READY（round 1）             | —                      |
| `expert qa` | REVIEW_SECOND_ROUND_FAILED（round 3） | REVIEW_FIRST_ROUND_FAILED（round 2） | DERIVED_READY（round 1） |


**分歧判定规则**（`_detect_round_disagreement`）：

- **Gate 分歧**：本轮任意一个 gate key，若评审员之间出现 `pass` vs `fail` 的差异，则视为分歧。
- **Score 分歧**：本轮所有评审员的 `qa_score`，`max - min >= 30` 视为分歧。
- 两者任一成立 → `has_disagreement = true` → Upload 进入下一轮失败状态。

**最终决策生成**（`_build_final_decision`，无分歧时执行）：

- `final_gate`：每个 gate key，任一评审员投 fail 则结果为 fail（保守取值）。
- `final_gate_passed`：所有 gate key 均为 pass。
- `final_quality_score`：所有评审员 `qa_score` 的中位数。
- `final_upload_vote`：`final_gate_passed` 为 true 则 pass，否则 fail。

---

### 2.3 QA 评审维度（v2）

#### 2.3.1 维度定义


| 类型            | Key（后端）                     | 前端展示标签                       | 合法值             |
| ------------- | --------------------------- | ---------------------------- | --------------- |
| **Gate**（门控）  | `is_camera_feed_clear`      | Clear camera feed            | `pass` / `fail` |
| **Gate**      | `is_task_completed`         | Task completed as instructed | `pass` / `fail` |
| **Gate**      | `is_robot_hand_visible`     | Robot hand stays in frame    | `pass` / `fail` |
| **Gate**      | `are_cameras_in_sync`       | All cameras in sync          | `pass` / `fail` |
| **Score**（评分） | `robot_control_quality`     | Robot control quality        | 整数 1–5          |
| **Score**     | `movement_smoothness`       | Movement smoothness          | 整数 1–5          |
| **Score**     | `task_completion_speed`     | Task completion speed        | 整数 1–5          |
| **Score**     | `task_fully_completed`      | Task fully completed         | 整数 1–5          |
| **Score**     | `variation_across_episodes` | Variation across episodes    | 整数 1–5          |


#### 2.3.2 后端校验规则（`_validate_review_result_payload`）

> **重要**：`result` 数组为"**每个被抽中的 episode 独立一条**"，并包含 `episode_vote`、`episode_score` 字段，上传级聚合结果须与各 episode 计算值一致，服务端强校验。

校验依次执行，任意一步失败返回 HTTP 400：

1. `review_result` 必须为 object。
2. `review_result.sampled_episode_id` 必须存在且非空（非空整数数组，元素不可重复）。
3. `review_result.result` 必须为 array，**长度必须等于 `sampled_episode_id` 长度**（每个 episode 一条）。
4. 每条 `result[i]`：
  - `episode_id` 必须为整数，且必须在 `sampled_episode_id` 集合内，且在 `result` 中唯一。
  - `gate` 必须为 object；4 个 gate key 值归一化后必须为 `pass` 或 `fail`。
  - `score` 必须为 object；5 个 score key 值必须为整数 1–5。
  - `episode_vote` 必须为 `pass` 或 `fail`，且**必须与 gate 推导一致**：任一 gate 为 `fail` 则 `episode_vote = "fail"`，否则为 `"pass"`。
  - `episode_score` 必须为整数 0–100，且**必须等于**后端计算值：`int(round((score_sum / 5 / 5) * 100))`（5 项 score 均值 / 5 * 100 取整）。
5. `result` 覆盖的 `episode_id` 集合必须与 `sampled_episode_id` 完全相等（不多不少）。
6. `review_result.upload_vote` 必须为 `pass` 或 `fail`，且必须与聚合结果一致：所有 episode 均 pass → `"pass"`，否则 `"fail"`。
7. `review_result.upload_score` 必须为整数 0–100，且必须等于各 `episode_score` 的算术均值取整。

**计算公式汇总**：


| 字段              | 计算公式                                            |
| --------------- | ----------------------------------------------- |
| `episode_score` | `int(round( (Σscores / 5) / 5 × 100 ))`         |
| `episode_vote`  | 有任意 gate = fail → `"fail"`，否则 `"pass"`          |
| `upload_score`  | `int(round( Σepisode_scores / episode_count ))` |
| `upload_vote`   | 全部 episode_vote 均 pass → `"pass"`，否则 `"fail"`   |


#### 2.3.3 全量请求体结构

```json
{
  "qa_round": 1,
  "qa_score": 72,
  "note": "optional reviewer note",
  "dont_show_again_validator_access_modal": false,
  "review_result": {
    "rubric_version": "v2",
    "upload_id": 123,
    "sampled_episode_id": [101, 102, 103],
    "upload_score": 72,
    "upload_vote": "pass",
    "result": [
      {
        "episode_id": 101,
        "gate": {
          "is_camera_feed_clear": "pass",
          "is_task_completed": "pass",
          "is_robot_hand_visible": "pass",
          "are_cameras_in_sync": "pass"
        },
        "score": {
          "robot_control_quality": 4,
          "movement_smoothness": 4,
          "task_completion_speed": 3,
          "task_fully_completed": 4,
          "variation_across_episodes": 3
        },
        "episode_vote": "pass",
        "episode_score": 72
      },
      {
        "episode_id": 102,
        "gate": {
          "is_camera_feed_clear": "pass",
          "is_task_completed": "pass",
          "is_robot_hand_visible": "pass",
          "are_cameras_in_sync": "pass"
        },
        "score": {
          "robot_control_quality": 4,
          "movement_smoothness": 3,
          "task_completion_speed": 4,
          "task_fully_completed": 4,
          "variation_across_episodes": 3
        },
        "episode_vote": "pass",
        "episode_score": 72
      },
      {
        "episode_id": 103,
        "gate": {
          "is_camera_feed_clear": "fail",
          "is_task_completed": "pass",
          "is_robot_hand_visible": "pass",
          "are_cameras_in_sync": "pass"
        },
        "score": {
          "robot_control_quality": 3,
          "movement_smoothness": 3,
          "task_completion_speed": 3,
          "task_fully_completed": 3,
          "variation_across_episodes": 3
        },
        "episode_vote": "fail",
        "episode_score": 60
      }
    ]
  }
}
```

> **示例说明**：上例 3 个 episode，episode 101/102 均通过，103 因 `is_camera_feed_clear = "fail"` 而 `episode_vote = "fail"`；  
> `upload_vote = "fail"`（非全通过）；`upload_score = round((72 + 72 + 60) / 3) = 68`。  
> `qa_score` 须与 `upload_score` 相等，此处应为 68（示例中为说明结构，请以实际计算值填写）。

---

### 2.4 Episode 抽样一致性机制

**目标**：同一 Upload 在同一 QA 轮次中，不同评审员审阅的 Episode 集合必须完全一致。

#### 2.4.1 抽样策略


| 版本             | 策略                                      | Seed 格式                                     |
| -------------- | --------------------------------------- | ------------------------------------------- |
| 旧（~2026-04-13） | 全量抽取（N = 总 episode 数）                   | `"{upload_id}:{qa_round}:qa-sample-v1"`     |
| **新（当前）**      | **比例抽取：`min(N, max(5, ceil(N × 5%)))`** | `**"{upload_id}:{qa_round}:qa-sample-v2"**` |


新策略举例：


| 总 episode 数 | 抽样数                        |
| ----------- | -------------------------- |
| 10          | 5（min(10, max(5,1))=5）     |
| 50          | 5（min(50, max(5,3))=5）     |
| 100         | 5（min(100, max(5,5))=5）    |
| 200         | 10（min(200, max(5,10))=10） |
| 500         | 25（min(500, max(5,25))=25） |


> **注意**：seed 版本从 v1 切换为 v2，同一 upload 同一 round 的新抽样结果与旧记录不同，已有旧格式 session 将不被复用。

#### 2.4.2 抽样一致性的实现（`GET /data/qa/uploads/<upload_id>/episodes`）

```
1. 用当前 upload_id + qa_round 计算 target_sample_ids（_pick_deterministic_sample）

2. 查询该 upload 在当前 qa_round 中已有提交的 data_qa_sessions
        │
        ├── 有已提交记录 → 遍历各 session
        │     └── 解析 review_result.sampled_episode_id
        │           ├── 解析结果 == target_sample_ids → 复用该样本（sampled_episode_ids = candidate）
        │           └── 不等 → 继续遍历下一条
        │
        └── 无匹配记录（本轮第一个审阅者，或旧格式 session 不兼容）
              └── sampled_episode_ids = target_sample_ids（直接使用新算法结果）
```

> **关键规则**：历史样本须**完全等于**当前算法计算的 target_sample_ids，否则不复用。这确保了 v2 seed 切换后旧数据不会污染新轮次。

#### 2.4.3 提交时强一致性校验（`POST .../review`）

服务端会独立重新计算 `reference_sample_ids`（同上述逻辑），要求客户端提交的 `sampled_episode_id` **与之完全相等**，不等则返回 400 并附带 `expected_sampled_episode_id`。

> **例外**：`expert qa` 角色提交时，`sampled_episode_id` 只需是该 Upload 全部 episode 的子集（`issubset(all_episode_id_set)`），不要求与 `reference_sample_ids` 完全匹配。详见 2.13 节。

---

### 2.5 校验者准入弹窗（ValidatorAccessModal）业务逻辑

#### 2.5.1 弹窗触发条件

```
用户点击 [Submit] 按钮
        │
        ├── userSettings.dont_show_again_validator_access_modal === true
        │         └── 直接调用 POST .../review（跳过弹窗）
        │
        └── 否则（false / 未设置）
                  └── 打开 ValidatorAccessModal
                            └── 用户在弹窗内完成提交
```

`dont_show_again` 的初始值从登录响应写入 `SwapMainAppContext.userSettings`（`result.data.settings`），页面刷新不会丢失（前提：user-management 登录接口在响应中携带 `settings` 字段）。

#### 2.5.2 弹窗数据来源


| 数据字段                        | 来源                                                        | 备注                      |
| --------------------------- | --------------------------------------------------------- | ----------------------- |
| `spots_remaining`           | 静态写死 = 100                                                | 暂不反映真实名额                |
| `spots_total`               | 静态写死 = 100                                                | 同上                      |
| `reviews_done`              | `COUNT(*) FROM data_qa_sessions WHERE user_id = :user_id` | **跨月、跨 round 统计，非月度数据** |
| `reviews_allowed.amplifier` | 静态 = 10                                                   | Amplifier 月度上限          |
| `reviews_allowed.innovator` | 静态 = 30                                                   | Innovator 月度上限          |


**预加载时机**：组件挂载时，若 `dont_show_again = false`，自动调用 `GET /data/qa/get-validator-access-data`，结果缓存至 `validatorAccessData` state，弹窗打开时使用。若接口失败，`validatorAccessData` 为 null，弹窗回退显示 `-- / N`。

#### 2.5.3 弹窗 Tab 权限矩阵


| Tab          | `isDisabled` 条件                    | 内部按钮状态                      |
| ------------ | ---------------------------------- | --------------------------- |
| ExplorerTab  | `userClass !== 'Explorer Member'`  | "Upgrade to Amplifier" 按钮禁用 |
| AmplifierTab | `userClass !== 'Amplifier Member'` | "Start reviewing" 按钮禁用      |
| InnovatorTab | `userClass !== 'Innovator Member'` | "Begin validation" 按钮禁用     |


只有当前 `userClass` 对应的 Tab 按钮才可点击提交。

#### 2.5.4 提交流程（弹窗内）

```
用户点击 [Start reviewing / Begin validation]
        │
        ├── submittingUploadReview = true（按钮进入 loading，防止重复点击）
        │
        └── POST /data/qa/uploads/:id/review
              body: { ...review_payload, dont_show_again_validator_access_modal: <dontShowAgain> }
                    │
                    ├── 成功
                    │     ├── validatorAccessData.reviews_done + 1（弹窗内计数更新）
                    │     ├── 显示 CustomNotification（title: "Scores submitted"）
                    │     ├── finally: 关闭 ValidatorAccessModal
                    │     └── onDismiss（N 秒后）:
                    │           ├── loadUploadEpisodes()
                    │           ├── fetchUploads()
                    │           └── if updateDontShowAgain: setUserSettings({...dont_show_again...: true})
                    │
                    └── 失败
                          ├── showNotification('error', ...)（全局通知）
                          └── finally: 关闭 ValidatorAccessModal（弹窗必关）
```

---

### 2.6 dont_show_again 状态持久化

#### 数据流

```
1. 用户提交时勾选"不再显示"
        └── POST body 携带 dont_show_again_validator_access_modal: true

2. 后端（同一事务内）
        └── UPDATE users SET settings = settings || '{"dont_show_again_validator_access_modal": true}'
              ├── review INSERT 成功 → settings 更新
              └── review INSERT 失败（事务回滚）→ settings 不变

3. 前端（提交成功后 onDismiss 回调）
        └── setUserSettings({ ...userSettings, dont_show_again_validator_access_modal: true })
              └── 下次点 Submit → 直接提交，不弹窗

4. 页面刷新后
        └── 登录接口 /user-info 返回 result.data.settings
              └── SwapMainAppContext 写入 userSettings
                    └── dontShowAgainValidatorAccessModal 从 DB 恢复（需 user-management 支持）
```

---

### 2.7 CustomNotification 组件行为


| 行为            | 实现机制                                                             |
| ------------- | ---------------------------------------------------------------- |
| 挂载位置          | `ReactDOM.createPortal` → `document.body`（避免 z-index 层叠问题）       |
| 入场动画          | 下一帧 RAF 设 `visible=true`，CSS transition 生效                       |
| 进度条           | `requestAnimationFrame` 逐帧计算剩余时间百分比                              |
| 自动关闭          | `setTimeout(dismiss, duration)` → dismiss 后 250ms 执行 `onDismiss` |
| 手动关闭          | 点击 × → 立即 dismiss → 250ms 后 `onDismiss`                          |
| onDismiss 副作用 | `loadUploadEpisodes()` + `fetchUploads()` + 更新 `userSettings`    |


**设计意图**：列表数据刷新延迟到通知消失后执行，避免用户看到内容瞬间闪烁。

---

### 2.8 批次锁定机制（Batch Lock）

#### 2.8.1 设计目标

防止评审员在完成当前抽样批次前切换 upload 或 scenario，确保一轮评审的数据完整性。

#### 2.8.2 锁定触发条件

```
hasStartedCurrentBatch = true，当满足以下任一条件：
  ├── effectiveSampledEpisodeIds 中有任何 episode 的 locallySubmittedEpisodeIds[id] = true
  └── effectiveSampledEpisodeIds 中有任何 episode 的 rubric 任意字段被填写过（非空/非null/非undefined）
```

#### 2.8.3 锁定范围


| 用户操作                   | 锁定时触发                           | 行为                                                                                          |
| ---------------------- | ------------------------------- | ------------------------------------------------------------------------------------------- |
| 切换 Scenario 下拉         | `handleChangeScenario`          | 阻止路由跳转，展示 Warning 通知                                                                        |
| 点击"返回上一页"              | `handleBackToPreviousQa`        | 阻止 `navigate(-1)` / `navigate(fallback)`，展示 Warning 通知                                      |
| Scenario 下拉本身          | `ScenarioDropdown blocked=true` | 下拉无法展开，点击触发 `onBlockedAttempt`                                                              |
| Upload 下拉（Advanced QA） | `UploadDropdown blocked=true`   | 下拉无法展开，点击触发 `onBlockedAttempt`；`handleChangeUpload` 同样调用 `showBatchLockedNotification()` 守卫 |


#### 2.8.4 通知内容

```
// expert qa（自由批次模式）专属文案
"Please submit or clear your current batch of {N} episode(s) before leaving this upload."

// 其他 QA 角色（qa / senior qa / super qa）通用文案
"Please complete reviewing current {N} episode(s) before leaving this upload."
```

其中 `N = remainingEpisodeCount`（最小为 1）。对于 expert qa，`N = Object.keys(locallySubmittedEpisodeIds).length`（批次总数）；对于其他角色，`N = effectiveSampledEpisodeIds 中未在 locallySubmittedEpisodeIds 中的数量`。

#### 2.8.5 锁定解除

当 `hasStartedCurrentBatch = false`（未填写任何字段且无已本地提交的 episode），或批次整体提交成功后（`setLocallySubmittedEpisodeIds({})` + `setReviewState({})` 被调用），锁定自动解除。

---

### 2.9 DataHub 加载提速

**优化点**：机器列表请求（`fetchMachineListOnce`）现在只在上传相关路由下触发，其他路由（如 QA 审阅页）不再发起该请求。


| 路由前缀                      | `isUploadRoute` | 是否请求机器列表       |
| ------------------------- | --------------- | -------------- |
| `/data` 或 `/data/upload`* | `true`          | 是              |
| `/data/review*` 或其他       | `false`         | **否**（直接返回空数组） |


---

### 2.10 Expert QA Upload 选择器

#### 2.10.1 功能概述

为 `expert qa` / `super qa` 角色新增 Upload 批次下拉选择器，允许在同一 Task/Scenario 下切换不同 Upload，无需退出当前页面。选择结果实时同步到 URL，支持通过 `?upload=<id>` 参数直接跳入指定 Upload。

#### 2.10.2 显示条件

```javascript
const normalizedUserRole = String(userRole || '').trim().toLowerCase();
const isExpertQa   = normalizedUserRole === 'expert qa';
const isSuperQa    = normalizedUserRole === 'super qa';
const isAdvancedQa = isExpertQa || isSuperQa;   // 组合标记

shouldShowUploadSelector = isAdvancedQa && filteredUploads.length > 1
shouldShowRoundTag = normalizedUserRole === 'expert qa' || 'senior qa' || 'super qa'
```

仅满足以下**全部**条件时才在 Breadcrumb 区域的 ScenarioDropdown 后面展示 Upload 下拉：

- `isAdvancedQa`（即 `normalizedUserRole === 'expert qa'` 或 `normalizedUserRole === 'super qa'`）
- 当前 Scenario 下有超过 1 个 Upload（`filteredUploads.length > 1`）

非 expert qa / super qa 角色、或只有 1 个 Upload 时，不渲染该组件。

#### 2.10.2.1 三个角色布尔值的作用域分工

代码中存在三个独立的布尔值，各自控制不同维度，不可混淆：

| 变量 | 为 true 的角色 | 控制的功能 |
|------|--------------|---------|| `isAdvancedQa` | expert qa **或** super qa | ① Upload 下拉选择器是否渲染（`shouldShowUploadSelector`）  
② `?upload=<id>` URL 深链是否生效（`preferredUploadId` 读取逻辑） |
| `isExpertQa`（独立） | 仅 expert qa | ① 批次评审模式（Add to batch / Remove from batch / Finalize）  
② `effectiveSampledEpisodeIds` 来源（自选集合 vs 服务端抽样）  
③ `hasStartedCurrentBatch` / `remainingEpisodeCount` 计算逻辑  
④ 批次锁 Warning 专属文案（"submit or clear batch..."）  
⑤ 后端子集校验路径（`issubset` 而非完全匹配） |
| `isSuperQa`（独立） | 仅 super qa | 目前无独有业务逻辑，行为等同于"普通 QA + `isAdvancedQa` 赋予的 Upload 选择器与 URL 深链权限" |

**关键结论：** `isAdvancedQa` 只管 **UI 入口权限**（哪些角色能看到 Upload 选择器、能用 URL 深链）；真正的**评审行为差异**完全由 `isExpertQa` 单独决定，与 `isSuperQa` 无关。

#### 2.10.3 URL 参数深链（`?upload=<id>`）

```
URL: /data/review/:taskId?upload=<upload_id>
```

**读取逻辑（`requestedUploadId`）：**

- 从 `useSearchParams()` 解析 `upload` 参数，转为整数（无效值或非整数则为 `null`）

**选中优先级（每次 `filteredUploads` 或 `requestedUploadId` 变化时执行）：**

```
isAdvancedQa && filteredUploads 中存在 requestedUploadId
    → 选中 requestedUploadId
否则
    → 选中 filteredUploads[0].upload_id（默认第一个）
```

**降级时 URL 自动修正与通知：**

当 `requestedUploadId !== null`（URL 中明确携带了 `?upload=` 参数）但 `preferredUploadId !== requestedUploadId`（即请求的 Upload 不在 filteredUploads 中，发生了降级），前端会额外执行：

```
requestedUploadId 不为 null 且 preferredUploadId ≠ requestedUploadId
    → setSearchParams：将 URL ?upload= 参数更新为 preferredUploadId（preserve 其他参数）
    → showNotification('warning', "The requested upload was not available for review.
                                   Redirecting to a similar upload.")
```

效果：URL 被原地修正为实际选中的 Upload，刷新后不再触发二次降级；同时通过 warning 通知告知用户已发生重定向。

#### 2.10.4 切换逻辑（`handleChangeUpload`）

```
用户选择新 Upload
    │
    ├── showBatchLockedNotification()（批次锁检查）
    │     └── 批次锁定中 → 阻止切换，弹出 Warning 通知，return
    │
    ├── 更新 selectedUploadId
    ├── 调用 loadUploadEpisodes(nextUploadId)（加载新 Upload 的 Episodes）
    └── navigate(`/data/review/${taskId}?upload=${nextUploadId}`, { replace: true })
          （URL 写入，replace 模式不产生历史记录）
```

#### 2.10.5 UI 位置与样式

Upload 选择器插入在 Breadcrumb 导航中 ScenarioDropdown 之后、`Episode #xxx` 标签之前，以 `/` 分隔符衔接。复用已有 `scenarioSelectWrap` / `scenarioTrigger` / `scenarioMenu` / `scenarioOption` 样式，展示格式为 `Upload #<id>`。

---

### 2.11 Episode 切换视频自动归零

#### 2.11.1 问题背景

原有实现中，用户切换到不同 Episode 时，视频播放位置（`currentTime`）和播放状态（`isPlaying`）不会重置。新 Episode 的视频会从上一个 Episode 的进度位置继续播放，造成体验错误。

#### 2.11.2 修复方式

在 `DataQAReview` 组件中新增一个 `useEffect`，监听 `currentEpisodeIndex` 变化：

```javascript
useEffect(() => {
    setCurrentTime(0);
    setIsPlaying(false);
}, [currentEpisodeIndex]);
```

**效果：** 每次切换 Episode（通过 Prev/Next 按钮或列表点击），视频立即归零并暂停，用户从头看新 Episode 的视频。

#### 2.11.3 关联 bugfix：Scenario 下拉 dataTasks prop

同一迭代中修复了另一个 bug：`DataHub` 渲染 `DataReviewViewer` 时，`dataTasks` prop 未传入，导致 `ScenarioDropdown` 内部的 Scenario 选项无法正常展示。修复方式为在 `DataReviewViewer` 组件调用处补传：

```jsx
<DataReviewViewer
    canAccess={isQa}
    qaUploads={qaUploads}
    dataTasks={dataTasks}   {/* 补传此 prop */}
    qaUploadsStatus={qaUploadsStatus}
/>
```

---

### 2.12 DataReviewHub

> **历史背景**：前身为 `DataReviewTaskHubV2`（WIP，注册于 `/data/review/v2`），后重命名为 `DataReviewHub` 并迁移至主路由 `/data/review`，旧文件 `DataReviewTaskHub.js` / `DataReviewTaskHubV2.js` 已删除，`/data/review/v2` 路由已移除。

#### 2.12.1 功能定位

替代旧 `DataReviewTaskHub` 和 `DataReviewTaskHubV2`，成为 QA 任务入口页面。路由：`/data/review`（index route）。

#### 2.12.2 DataHub 路由最终形态

```jsx
// DataHub.js — /data/review 路由下的组件绑定
<Route index element={<DataReviewHubWrapper dataTasks={dataTasks} qaUploads={qaUploads} qaUploadsStatus={qaUploadsStatus} />} />
<Route path=":taskId" element={<DataReviewViewer qaUploads={qaUploads} qaUploadsStatus={qaUploadsStatus} dataTasks={dataTasks} />} />
```

#### 2.12.3 卡片数据结构与主键

**主键**：卡片标识符以 `uploadId` 单独作为主键（而非旧版的 `uploadId:taskId`）。


| 字段              | 说明                                                              |
| --------------- | --------------------------------------------------------------- |
| `card.uploadId` | 主键；卡片 key、预览 URL Map 的键、URL `?upload=<id>` 的来源                  |
| `card.taskId`   | 跳转详情页时仍使用（navigate 路径 `/data/review/:taskId?upload=<uploadId>`） |


#### 2.12.4 视频预览懒加载

`DataReviewHub` 在分页展示时对可见卡片调用 `handleFetchPreviews(uploadIds)`，批量获取预览 URL：

```
onNeedPreviews(uploadIds) 在以下时机触发：
  - 首屏渲染（initialFetchDone 后）
  - 翻页时
```

请求接口：`GET /data/qa/uploads/preview-urls?uploads=<id1>&uploads=<id2>&...`  
状态存储：`cardToVideoPreviewData: Map<uploadId, { url, isLoadingUrl, isLoadingVideo, isError }>`  
去重机制：`requestedUploadPreviewsRef`（Set），已请求的 uploadId 不再重复请求。  
有 URL → `<video autoPlay muted loop>`；无 URL / error → 降级为占位框。

#### 2.12.5 Upload ID 可见性

```javascript
const shouldShowUploadId = normalizedUserRole === 'super qa' || normalizedUserRole === 'expert qa';
```

卡片上 `#uploadId` 数字标识仅对 `super qa` / `expert qa` 展示。

---

### 2.13 Expert QA 批次评审模式

#### 2.13.1 与普通 QA 的核心区别

普通 `qa` / `senior qa` / `super qa` 的 `effectiveSampledEpisodeIds` 来自**服务端确定性抽样**，评审员按抽样集合逐集完成后统一提交。`expert qa` 的工作流完全不同：


| 属性                           | 普通 QA（含 super qa）       | expert qa                                              |
| ---------------------------- | ----------------------- | ------------------------------------------------------ |
| `effectiveSampledEpisodeIds` | 服务端 sampled_episode_ids | `Object.keys(locallySubmittedEpisodeIds)`（自选集合）        |
| `hasStartedCurrentBatch`     | 有已填写或已本地提交的 episode     | `Object.keys(locallySubmittedEpisodeIds).length > 0`   |
| `remainingEpisodeCount`      | 未提交的抽样集 episode 数       | `Object.keys(locallySubmittedEpisodeIds).length`（批次总数） |
| 提交按钮文案                       | `Submit & earn points`  | `Add to batch` / `Remove from batch`                   |
| 最终提交按钮                       | 同一按钮                    | 独立 `Submit selected episodes (N)` 按钮                   |
| 批次重置                         | 整体提交后自动清空               | 额外提供 `Clear batch` 按钮                                  |


#### 2.13.2 完整操作流程

```
expert qa 进入 DataQAReview 页面
    │
    ├── 浏览 Episode（任意顺序，不受抽样约束）
    │
    ├── 对当前 Episode 填写完整 gate + score
    │         │
    │         ├── "Add to batch" 按钮（currentEpisodeId 不在 batch 中时）
    │         │       → locallySubmittedEpisodeIds[id] = rubricResult
    │         │       → 自动跳到下一集（currentEpisodeIndex + 1）
    │         │       → 通知："Episode N added to batch. M selected for final submission."
    │         │
    │         └── "Remove from batch" 按钮（currentEpisodeId 已在 batch 中时）
    │                 → 从 locallySubmittedEpisodeIds 中删除
    │                 → 通知："Episode N removed from batch."
    │
    ├── 查看 batch 进度：
    │         "Batch selected: M"（superQaBatchMeta 区域）
    │         "Add any episodes you want, then submit the batch together."
    │
    ├── "Submit selected episodes (M)" 按钮（disabled 条件：M=0 或 uploadRubricResult.ready=false）
    │         → 与普通 QA 相同的 handleSubmitUploadReview / ValidatorAccessModal 流程
    │         → 提交后清空 batch
    │
    └── "Clear batch" 按钮（disabled 条件：M=0）
              → setLocallySubmittedEpisodeIds({})
              → 通知："Cleared current expert QA batch."
```

#### 2.13.3 批次锁行为差异

expert qa 的批次锁 Warning 文案与普通 QA 不同：

```
普通 QA（qa / senior qa / super qa）：
  "Please complete reviewing current N episode(s) before leaving this upload."

expert qa：
  "Please submit or clear your current batch of N episode(s) before leaving this upload."
```

批次锁触发条件（expert qa）：`hasStartedCurrentBatch = Object.keys(locallySubmittedEpisodeIds).length > 0`。

#### 2.13.4 Guard 校验

点击"Submit selected episodes"时，若 `selectedBatchCount <= 0`，弹出 Warning："Add at least one episode to the batch before final submit." 不调用提交接口。

#### 2.13.5 后端支持

`**qa_helper.py` — `_resolve_review_episode_ids`：**

当 `user_role = expert qa`（`QA_ROLE_EXPERT`）时，直接将传入的 `episode_ids`（即 `locallySubmittedEpisodeIds` 的 key 集合）作为返回集合，转换为排序后的整数列表：

```python
if _normalize_user_role(user_role) == QA_ROLE_EXPERT:
    return sorted({int(episode_id) for episode_id in (episode_ids or [])
                   if str(episode_id).isdigit()})
```

`**app.py` — `submit_upload_qa_review`：**

当 `user_role = expert qa` 时，`provided_sample_ids` 只需是 `all_episode_id_set` 的子集（`issubset`），不需要等于 `reference_sample_ids`：

```python
if _normalize_user_role(user_role) == "expert qa":
    if not set(provided_sample_ids).issubset(all_episode_id_set):
        return jsonify({"success": False, "msg": "sampled_episode_id mismatch for this round", ...})
    # 跳过 reference_sample_ids 完全匹配校验
```

---

## 3. 后端 API 清单

### 3.1 全量 API 概览

`app-prismax-rp-backend / app_prismax_data_pipeline/app.py` 中当前所有已激活路由：


| #   | Method   | Path                                     | 鉴权要求                                          | 所属场景                         | QA 涉及 |
| --- | -------- | ---------------------------------------- | --------------------------------------------- | ---------------------------- | ----- |
| 1   | GET      | `/data/tasks`                            | 无                                             | 任务元数据查询                      | —     |
| 2   | GET      | `/data/machines`                         | 无                                             | 机器元数据查询                      | —     |
| 3   | GET      | `/data/registered-machines`              | 任意已登录用户                                       | 用户名下注册机器                     | —     |
| 4   | GET      | `/data/uploading-history`                | 任意已登录用户                                       | 用户上传历史                       | —     |
| 5   | POST     | `/data/upload-sessions`                  | `operator`                                    | 创建上传会话（含 GCS 签名 URL）         | —     |
| 6   | POST     | `/data/upload-sessions/<id>/resume`      | `operator`                                    | 恢复断点续传会话                     | —     |
| 7   | GET      | `/data/downloadable-uploads`             | `operator`                                    | 可下载 Upload 列表                | —     |
| 8   | POST     | `/data/downloads/ui`                     | `operator`                                    | 创建 UI 直接下载（≤10 episodes）     | —     |
| 9   | POST     | `/data/downloads/manifest`               | `operator`                                    | 创建 API 批量下载 Manifest         | —     |
| 10  | GET      | `/data/downloads/script`                 | `operator`                                    | 下载辅助 Python 脚本               | —     |
| 11  | GET      | `/data/downloads/history`                | `operator`                                    | 用户下载历史                       | —     |
| 12  | **GET**  | `**/data/qa/uploads`**                   | `qa` / `senior qa` / `expert qa` / `super qa` | **QA 可审阅队列**                 | ✅     |
| 13  | **GET**  | `**/data/qa/uploads/<id>/episodes`**     | `qa` / `senior qa` / `expert qa` / `super qa` | **获取审阅 Episode + 视频**        | ✅     |
| 14  | **POST** | `**/data/qa/uploads/<id>/review`**       | `qa` / `senior qa` / `expert qa` / `super qa` | **提交 QA 评审**                 | ✅     |
| 15  | **GET**  | `**/data/qa/get-validator-access-data`** | 任意已登录用户                                       | **校验者准入弹窗数据**                | ✅     |
| 16  | **GET**  | `**/data/qa/uploads/preview-urls`**      | `qa` / `senior qa` / `expert qa` / `super qa` | **QA Review Hub 卡片视频预览 URL** | ✅     |


> 注：另有两个路由（`/data/public/task-samples`、`/data/uploads/<id>/signed-urls`）已在代码中注释掉，不参与测试。

---

### 3.2 QA 相关 API 详细规格

---

#### 3.2.1 `GET /data/qa/uploads` — 获取可审阅 Upload 队列

**鉴权**：Bearer token，`user_role ∈ {qa, senior qa, expert qa, super qa}`（`QA_ALLOWED_ROLES`），否则 403

**Query Params**：无

**核心逻辑**：

1. 根据 `user_role` 获取可见的 Upload `status` 列表（`_get_qa_queue_rules`）。
2. 过滤掉当前用户**已提交过评审**的 Upload（`NOT EXISTS data_qa_sessions WHERE user_id = :user_id`）。
3. 排序：先按角色优先级（priority 升序），再按 `created_at` 降序（最新 Upload 优先）。

**响应结构（精简后）**：

> **说明**：SQL 中的多表 JOIN / GROUP BY / 子查询已移除，响应字段从 11 个精简为 **2 个**，客户端需后续独立调用 `GET .../episodes` 获取详情。

```json
{
  "success": true,
  "data": [
    {
      "upload_id": 123,
      "task_id": 5
    }
  ]
}
```

**已移除字段**：


| 已移除字段                 | 原说明                    |
| --------------------- | ---------------------- |
| `machine_id`          | 机器 ID                  |
| `status`              | Upload 当前状态            |
| `qa_round`            | 当前轮次（由 status 推导）      |
| `created_at`          | 上传时间                   |
| `scenario`            | 任务场景名                  |
| `episode_count`       | 总 Episode 数            |
| `derived_ready_count` | 已 Derive 完毕的 Episode 数 |
| `round_review_count`  | 当前轮次已提交评审数             |
| `reviewer_role`       | 当前请求者角色（后端附加）          |
| `reviewer_id`         | 当前请求者 ID（后端附加）         |


**已知边界**：

- 精简后客户端无法在列表页直接展示 episode 统计、round 状态等信息，需二次请求。
- 当前用户已提交 **任意** round 的该 Upload，均不再显示（无论当前是否还在该轮）。
- 同一 `created_at` 的 Upload 排序不稳定（SQL 无第三排序字段，但字段已被移除）。

**错误码**：


| HTTP | msg                  | 原因                     |
| ---- | -------------------- | ---------------------- |
| 400  | `token is required`  | 无 Authorization header |
| 401  | `invalid token`      | Token 不存在或失效           |
| 403  | `qa access required` | user_role 不在 QA 允许角色内  |


---

#### 3.2.2 `GET /data/qa/uploads/<upload_id>/episodes` — 获取本轮审阅 Episode 列表

**鉴权**：Bearer token，`user_role ∈ QA_ALLOWED_ROLES`

**Path Param**：`upload_id`（整数）

**Query Params**：


| 参数       | 类型  | 默认         | 说明          |
| -------- | --- | ---------- | ----------- |
| `offset` | int | 0          | 分页偏移，必须 ≥ 0 |
| `limit`  | int | null（返回全部） | 单页上限，最大 100 |


**核心逻辑**：

1. 查 Upload `status` → 推导 `qa_round`；若当前角色无权审此 Upload → 403。
2. 查该 Upload 下 `status='DERIVED_READY'` 的所有 Episodes。
3. 确定本轮 `sampled_episode_ids`：
  - 若已有人提交过本轮评审 → 复用其 `review_result.sampled_episode_id`（过滤无效 id 后）
  - 否则 → `_pick_deterministic_sample(all_ids, upload_id, qa_round)`（基于 SHA-256 确定性排序）
4. 对 sampled episodes 执行 offset/limit 分页。
5. 为每个 episode 生成 GCS Derived `.mp4` 的 Signed URL（有效期 24 小时）。

**响应结构**：

```json
{
  "success": true,
  "data": [
    {
      "episode_id": 101,
      "upload_id": 123,
      "machine_id": "m-001",
      "task_id": 5,
      "status": "DERIVED_READY",
      "raw_mcap_path": "raw/123/ep1.mcap",
      "raw_video_folder_path": "raw/123/ep1/",
      "derived_bucket": "prismax-data-derived-prod",
      "derived_video_folder_path": "derived/123/ep1/",
      "derived_videos": [
        {
          "object_name": "derived/123/ep1/cam_high.mp4",
          "signed_url": "https://storage.googleapis.com/..."
        }
      ]
    }
  ],
  "meta": {
    "total_count": 20,
    "offset": 0,
    "limit": null,
    "qa_round": 1,
    "upload_status": "DERIVED_READY",
    "sampled_episode_id": [101, 102, 103],
    "sample_size": 20,
    "total_derived_count": 20,
    "returned_count": 20,
    "has_more": false
  }
}
```

**错误码**：


| HTTP | msg                                     | 原因                |
| ---- | --------------------------------------- | ----------------- |
| 400  | `offset must be an integer`             | offset 参数格式错误     |
| 400  | `offset must be >= 0`                   | offset 为负数        |
| 400  | `limit must be an integer`              | limit 参数格式错误      |
| 400  | `limit must be > 0`                     | limit ≤ 0         |
| 401  | `invalid token`                         | Token 无效          |
| 403  | `qa access required`                    | user_role 不合法     |
| 403  | `upload is not available for your role` | upload 状态与当前角色不匹配 |
| 404  | `upload not found`                      | upload_id 不存在     |


---

#### 3.2.3 `POST /data/qa/uploads/<upload_id>/review` — 提交 QA 评审

**鉴权**：Bearer token，`user_role ∈ QA_ALLOWED_ROLES`

**Path Param**：`upload_id`（整数）

**Request Body**（JSON）：


| 字段                                       | 类型          | 必填                                       | 说明                      |
| ---------------------------------------- | ----------- | ---------------------------------------- | ----------------------- |
| `qa_score`                               | int (0–100) | 可选（与 `review_result.upload_score` 二选一兜底） | 综合评分                    |
| `qa_round`                               | int         | 可选                                       | 若传入，必须与服务端推导值一致         |
| `note`                                   | string      | 否                                        | 评审备注                    |
| `dont_show_again_validator_access_modal` | bool        | 否                                        | true 时更新 users.settings |
| `review_result`                          | object      | **是**                                    | 完整评审结果（见 2.3.3）         |


**校验顺序**（任一失败即 400 返回，不继续后续校验）：

```
① review_result 必须为 object
② review_result.upload_id（若存在）必须等于 path 中的 upload_id
③ qa_score 推导（优先 body.qa_score，兜底 review_result.upload_score），须存在且为整数 0-100
④ review_result.upload_score（若存在）必须等于 qa_score
⑤ review_result.sampled_episode_id 必须存在且非空
⑥ qa_round（若存在）须可解析为整数
⑦ upload 必须存在（否则 404）
⑧ 当前角色须可审阅该 Upload（否则 403）
⑨ qa_round（若传）须等于服务端推导值
⑩ 当前用户未重复提交该 upload（否则 409）
⑪ sampled_episode_id 须与服务端 reference_sample_ids 完全相等
   （例外：expert qa 只需 issubset(all_episode_id_set)）
⑫ _validate_review_result_payload()（含以下全部子校验）：
     ⑫-a sampled_episode_id 非空，元素唯一
     ⑫-b result 长度 == sampled_episode_id 长度
     ⑫-c 每条 result[i].episode_id 在 sampled_episode_id 中且不重复
     ⑫-d 每条 gate 4 key 均为 pass/fail
     ⑫-e 每条 score 5 key 均为整数 1-5
     ⑫-f 每条 episode_vote 与 gate 推导一致
     ⑫-g 每条 episode_score 与 score 均值公式一致
     ⑫-h result 覆盖的 episode_id 集合 == sampled_episode_id 集合
     ⑫-i upload_vote 与所有 episode_vote 聚合一致
     ⑫-j upload_score 与所有 episode_score 均值一致
```

**事务内操作**（所有步骤同一事务，全部成功或全部回滚）：

1. INSERT `data_qa_sessions`
2. 查本轮所有提交，判断是否达到阈值 → 若达到则 UPDATE `data_uploads.status`
3. 若 `dont_show_again_validator_access_modal = true` → UPDATE `users.settings`（JSONB 合并）

**成功响应结构**：

```json
{
  "success": true,
  "data": {
    "qa_session_id": 999,
    "created_at": "2026-04-13T10:00:00Z",
    "upload_id": 123,
    "qa_round": 1,
    "round_review_count": 2,
    "round_required_review_count": 3,
    "round_complete": false,
    "disagreement": {
      "gate_disagreement": false,
      "score_gap": 10,
      "has_disagreement": false
    },
    "final_decision": null,
    "status_updated": false,
    "upload_status": "DERIVED_READY"
  }
}
```

**达到阈值且无分歧时的 `final_decision`**：

```json
{
  "final_gate": {
    "is_camera_feed_clear": "pass",
    "is_task_completed": "pass",
    "is_robot_hand_visible": "pass",
    "are_cameras_in_sync": "pass"
  },
  "final_gate_passed": true,
  "final_quality_score": 72,
  "final_upload_vote": "pass"
}
```

**错误码**：


| HTTP | msg                                                                    | 原因                                                   |
| ---- | ---------------------------------------------------------------------- | ---------------------------------------------------- |
| 400  | `review_result object is required`                                     | review_result 缺失或非 object                            |
| 400  | `review_result.upload_id mismatch`                                     | upload_id 与 path 不一致                                 |
| 400  | `qa_score is required`                                                 | qa_score 和 upload_score 均缺失                          |
| 400  | `qa_score must be an integer`                                          | qa_score 格式错误                                        |
| 400  | `qa_score must be between 0 and 100`                                   | qa_score 越界                                          |
| 400  | `qa_score must equal review_result.upload_score`                       | 两者不一致                                                |
| 400  | `review_result.sampled_episode_id is required`                         | sampled_episode_id 缺失或空                              |
| 400  | `review_result.sampled_episode_id must contain unique integers`        | sampled_episode_id 含重复元素                             |
| 400  | `qa_round must be an integer`                                          | qa_round 格式错误                                        |
| 400  | `qa_round mismatch, expected {N}`                                      | 客户端传的 round 与服务端不符                                   |
| 400  | `no derived episodes found for this upload`                            | Upload 下无 DERIVED_READY episode                      |
| 400  | `sampled_episode_id mismatch for this round`                           | episode 列表与服务端期望不一致（附 `expected_sampled_episode_id`） |
| 400  | `review_result.result must be an array`                                | result 缺失或非数组                                        |
| 400  | `review_result.result must contain one item per sampled episode`       | result 长度与 sampled_episode_id 不一致                    |
| 400  | `review_result.result[i].episode_id must be an integer`                | episode_id 格式错误                                      |
| 400  | `review_result.result[i].episode_id must belong to sampled_episode_id` | episode_id 不在抽样集合内                                   |
| 400  | `review_result.result[i].episode_id must be unique`                    | result 中 episode_id 重复                               |
| 400  | `review_result.result[i].gate.{key} must be pass/fail`                 | gate 值非法                                             |
| 400  | `review_result.result[i].score.{key} must be integer 1-5`              | score 值非法                                            |
| 400  | `review_result.result[i].episode_vote must be pass/fail`               | episode_vote 缺失或非法                                   |
| 400  | `review_result.result[i].episode_vote mismatch`                        | episode_vote 与 gate 推导不一致                            |
| 400  | `review_result.result[i].episode_score must be integer 0-100`          | episode_score 格式或越界                                  |
| 400  | `review_result.result[i].episode_score mismatch`                       | episode_score 与 score 均值计算不一致                        |
| 400  | `review_result.result must cover all sampled episodes`                 | result 未覆盖全部 sampled episode                         |
| 400  | `review_result.upload_vote must be pass/fail`                          | upload_vote 缺失或非法                                    |
| 400  | `review_result.upload_vote mismatch`                                   | upload_vote 与 episode_vote 聚合不一致                     |
| 400  | `review_result.upload_score must be integer 0-100`                     | upload_score 格式或越界                                   |
| 400  | `review_result.upload_score mismatch`                                  | upload_score 与 episode_score 均值不一致                   |
| 401  | `invalid token`                                                        | Token 无效                                             |
| 403  | `qa access required`                                                   | 非 QA 角色                                              |
| 403  | `upload is not available for your role`                                | 当前角色无权审此 Upload                                      |
| 404  | `upload not found`                                                     | upload_id 不存在                                        |
| 409  | `you already submitted a review for this upload in round {N}`          | 重复提交                                                 |


---

#### 3.2.4 `GET /data/qa/get-validator-access-data` — 校验者准入弹窗数据

**鉴权**：Bearer token（任意已登录用户，**无 QA 角色要求**）

**Query Params**：无

**核心逻辑**：

- 查询 `COUNT(*) FROM data_qa_sessions WHERE user_id = :user_id`（跨月、跨 round、跨 upload 全量统计）
- 其余字段均为静态写死值（当前版本）

**响应结构**：

```json
{
  "success": true,
  "data": {
    "spots_remaining": 100,
    "spots_total": 100,
    "reviews_done": 7,
    "reviews_allowed": {
      "amplifier": 10,
      "innovator": 30
    }
  }
}
```

**字段说明**：


| 字段                          | 当前实现           | 预期语义             |
| --------------------------- | -------------- | ---------------- |
| `spots_remaining`           | 写死 = 100       | 平台当前周期剩余名额       |
| `spots_total`               | 写死 = 100       | 平台当前周期总名额        |
| `reviews_done`              | 用户历史全量提交数（非月度） | 当前月度已完成数         |
| `reviews_allowed.amplifier` | 写死 = 10        | Amplifier 会员月度上限 |
| `reviews_allowed.innovator` | 写死 = 30        | Innovator 会员月度上限 |


**错误码**：


| HTTP | msg                 | 原因                     |
| ---- | ------------------- | ---------------------- |
| 400  | `Token is required` | 无 Authorization header |
| 401  | `Invalid token`     | Token 不存在或失效           |


> 注意：此接口的 error msg 大小写与其他 QA 接口不一致（`Token is required` vs `token is required`），属于小的一致性问题，建议记录。

---

#### 3.2.5 `GET /data/qa/uploads/preview-urls` — QA Review Hub 卡片视频预览

**用途：** 为 `DataReviewHub` 卡片懒加载视频预览 Signed URL，每个 `upload_id` 返回该 Upload 首个 `DERIVED_READY` episode 的首个 `.mp4` 的签名地址。

**鉴权：** Bearer token，`user_role ∈ QA_ALLOWED_ROLES`，否则 403

**Query Params：**


| 参数            | 类型      | 必填       | 说明                                                     |
| ------------- | ------- | -------- | ------------------------------------------------------ |
| `uploads`（重复） | int（重复） | 是，至少 1 个 | 要查询预览的 upload_id，可多个（`?uploads=1&uploads=2&uploads=3`） |


**核心逻辑：**

1. 解析 `request.args.getlist('uploads')`，转换为整数列表；非整数返回 400。
2. SQL：`SELECT DISTINCT ON (e.upload_id) e.episode_id, e.upload_id, e.derived_bucket, e.derived_video_folder_path, e.raw_video_folder_path FROM data_episodes e WHERE e.upload_id = ANY(:upload_ids) AND e.status = 'DERIVED_READY' ORDER BY e.upload_id ASC, e.episode_id ASC`（每个 upload 取 episode_id 最小的一条）。
3. 对每个 upload_id：在 `derived_video_folder_path`（若无则从 `raw_video_folder_path` 推导 `raw/ → derived/`）目录下找**第一个 `.mp4`**，生成 GET Signed URL。
4. URL TTL = `SIGNED_URL_TTL_SECONDS`（86400 秒，1 天）。
5. 无 episode / 无 mp4 → 该 upload_id 对应值为 `null`。

**成功响应（200）：**

```json
{
  "success": true,
  "previews": {
    "101": "https://storage.googleapis.com/...",
    "102": null,
    "103": "https://storage.googleapis.com/..."
  }
}
```

**错误码：**


| HTTP | msg                                      | 原因                            |
| ---- | ---------------------------------------- | ----------------------------- |
| 400  | `At least one uploads param is required` | 未传 uploads 参数                 |
| 400  | `Invalid uploads value: {x}`             | uploads 包含非整数值                |
| 401  | `invalid token`                          | Token 无效                      |
| 403  | `qa access required`                     | user_role 不在 QA_ALLOWED_ROLES |


> 注：此接口与 `POST /data/downloadable-uploads/previews`（Robotic Data 模块）不同：后者接收 `episode_id` 列表、面向 operator/admin；前者接收 `upload_id` 列表、面向 QA 角色，且响应结构为 `previews` 对象而非 `data` 数组。

---

### 3.3 数据上传 API（QA 流程上游）

#### 3.3.1 `POST /data/upload-sessions` — 创建上传会话

**鉴权**：Bearer token，`user_role = operator`

**用途**：Operator 上传 MCAP + MP4 数据前，先调用此接口创建 Upload Session，获取 GCS PUT 签名 URL。

**Request Body 关键字段**：


| 字段           | 必填  | 说明                                                     |
| ------------ | --- | ------------------------------------------------------ |
| `token`      | 是   | 可在 body 或 Authorization header 传入                      |
| `task_id`    | 是   | 关联任务 ID                                                |
| `machine_id` | 是   | 机器 ID                                                  |
| `files`      | 是   | 文件列表，含 `relative_path` / `size_bytes` / `content_type` |


**文件结构约束**：

- 每个 Episode 对应一个 `.mcap` 文件（路径无 `/`）或一组 mp4 视频文件夹（路径含 `/`）。
- 每个 Episode 必须有对应的 `_MANIFEST.json`（路径格式：`<episode_key>/_MANIFEST.json`），否则 400。
- 最多 2000 个文件（`MAX_FILES_PER_UPLOAD`）。

**成功**：创建 `data_uploads`（状态 `UPLOADING`）+ `data_episodes`（状态 `UPLOADING`），返回所有文件的 GCS PUT 签名 URL（有效期 24 小时）。

---

#### 3.3.2 `POST /data/upload-sessions/<upload_id>/resume` — 恢复断点续传

**鉴权**：Bearer token，`user_role = operator`，且 upload 归属当前用户

**用途**：Upload 中断后重新发起，系统通过检查 GCS 中的文件是否存在（含 size 校验）跳过已上传文件，仅返回缺失文件的签名 URL。

**约束**：

- Upload 必须处于 `UPLOADING` 状态（其他状态返回 400）。
- 提交的文件列表 `expected_episode_keys` 必须与原始 Session 完全匹配。

---

### 3.4 数据下载 API（与 QA 流程无直接关联，列表仅供参考）


| Method | Path                         | 说明                                                |
| ------ | ---------------------------- | ------------------------------------------------- |
| GET    | `/data/downloadable-uploads` | Operator 可下载的 Episode 列表（含 MCAP 路径）               |
| POST   | `/data/downloads/ui`         | 创建直接下载（最多 10 episodes，返回 GCS GET 签名 URL 列表）       |
| POST   | `/data/downloads/manifest`   | 创建批量下载，返回 `manifest.json` 文件（含所有 Episode 的签名 URL） |
| GET    | `/data/downloads/script`     | 下载辅助 Python 脚本（配合 manifest 使用，自动重试 + SSL 修复）      |
| GET    | `/data/downloads/history`    | 当前用户的历史下载记录                                       |


---

### 3.5 基础元数据查询 API


| Method | Path                        | 说明                                  | 鉴权    |
| ------ | --------------------------- | ----------------------------------- | ----- |
| GET    | `/data/tasks`               | 查询所有 Task（含 scenario、environment 等） | 无     |
| GET    | `/data/machines`            | 查询所有 Machine（含 product_name）        | 无     |
| GET    | `/data/registered-machines` | 查询当前用户名下注册的 Machine                 | 任意已登录 |
| GET    | `/data/uploading-history`   | 查询当前用户的 Upload 历史（最近 100 条）         | 任意已登录 |


---

## 4. 测试策略

### 4.1 测试风险评估


| 风险项                               | 风险等级            | 说明                                                                                              |
| --------------------------------- | --------------- | ----------------------------------------------------------------------------------------------- |
| v2 Key 切换破坏旧提交                    | **P0 / High**   | 线上若有旧 v1 payload 的客户端，提交将全部 400                                                                 |
| dont_show_again 页面刷新后失效           | **P0 / High**   | 依赖 user-management `/user-info` 返回 `settings` 字段，若未携带则状态丢失                                      |
| Episode 抽样不一致导致提交 400             | **P0 / High**   | 客户端持有的 episode 列表与服务端计算不一致时全量拒绝                                                                 |
| reviews_done 跨月统计显示偏差             | **P1 / Medium** | 用户看到的完成数远超月度配额，造成困惑                                                                             |
| 弹窗关闭时机（finally）遮盖错误信息             | **P1 / Medium** | 失败时弹窗立即关闭，用户可能错过错误上下文                                                                           |
| Explorer 用户意外触发提交                 | **P1 / Medium** | 需确认 isDisabled 在所有 Tab 下生效                                                                      |
| score_gap 边界（gap=30）判定            | **P2 / Low**    | 恰好 30 时触发分歧，需边界验证                                                                               |
| Episode 切换视频不归零（已修复，需回归）          | **P0 / High**   | 视频状态不重置会导致评分基于错误的播放进度；已修复，每次回归须覆盖                                                               |
| Scenario 下拉 dataTasks 缺失（已修复，需回归） | **P1 / Medium** | 下拉选项为空时用户无法切换 Scenario；已修复，需验证 prop 正确传递                                                        |
| Expert QA Upload 切换与批次锁的交互        | **P1 / Medium** | 锁定期间 Upload 切换被阻止，但若用户直接修改 URL 参数，可绕过前端锁定                                                       |
| ?upload= URL 参数仅 advanced QA 读取   | **P2 / Low**    | 其他 QA 角色收到含 ?upload= 的链接后该参数被忽略，默认选中第一个 Upload                                                  |
| expert qa 批次提交与服务端校验              | **P1 / Medium** | expert qa 的 `sampled_episode_id` 由前端自选，后端只做子集校验；若传入 all_episode_id_set 之外的 episode_id，后端仍返回 400 |
| DataReviewHub 预览视频 TTL 短（1天）      | **P2 / Low**    | QA Hub 卡片视频 Signed URL 仅 1 天有效，长时间停留后视频失效需刷新                                                    |
| Expert QA Upload 切换不保留评分状态        | **P2 / Low**    | 切换 Upload 后，原 Upload 的 `reviewState` / `locallySubmittedEpisodeIds` 不被保存                        |
| ?upload= URL 参数绕过批次锁              | **P2 / Low**    | 批次锁仅保护 UI 操作，用户手动修改 URL 参数可绕过前端锁定                                                               |
| `get_qa_uploads` 精简后客户端适配         | **High**        | API 仅返回 `upload_id` + `task_id`，前端如依赖旧字段将空值或报错                                                  |


### 4.2 测试范围矩阵


| 功能模块                                 | 优先级     | 测试类型     |
| ------------------------------------ | ------- | -------- |
| v2 Gate/Score key 校验（后端）             | **P0**  | 接口测试     |
| rubric_version v2 完整提交流程             | **P0**  | 接口 + E2E |
| 多轮 QA 状态流转（round 1→2→3）              | **P0**  | 接口测试     |
| 分歧检测（gate/score）                     | **P0**  | 接口测试     |
| 弹窗触发 vs 跳过逻辑                         | **P0**  | E2E      |
| dont_show_again 持久化（DB + 前端状态）       | **P0**  | 接口 + E2E |
| Episode 切换视频自动归零（回归）                 | **P0**  | E2E      |
| DataReviewHub 正常渲染与卡片展示              | **P0**  | E2E      |
| expert qa Add/Remove/Finalize 批次流程   | **P0**  | E2E      |
| ValidatorAccessModal 各角色展示           | **P1**  | E2E + UI |
| get-validator-access-data 接口         | **P1**  | 接口测试     |
| CustomNotification 行为与刷新时机           | **P1**  | UI + E2E |
| Episode 抽样一致性（提交强校验）                 | **P1**  | 接口测试     |
| 错误流程（提交失败/接口失败）                      | **P1**  | 接口 + E2E |
| 防重复提交（409）                           | **P1**  | 接口测试     |
| Expert QA Upload 选择器（显示 / 切换 / URL）  | **P1**  | E2E + UI |
| ?upload= URL 参数深链                    | **P1**  | E2E      |
| Scenario 下拉 dataTasks 修复（回归）         | **P1**  | UI       |
| Upload 选择器批次锁保护                      | **P1**  | E2E      |
| DataReviewHub 视频预览懒加载                | **P1**  | E2E + 接口 |
| expert qa Clear batch                | **P1**  | E2E      |
| expert qa 批次锁 Warning 文案专属           | **P1**  | E2E      |
| Upload 选择器对 expert qa 和 super qa 可见  | **P1**  | UI       |
| GET /data/qa/uploads/preview-urls 接口 | **P1**  | 接口测试     |
| Explorer 用户权限限制                      | **P2**  | UI       |
| 进度条 cursor 样式                        | **P2**  | UI       |
| ScoringModal / SelectionModal        | **不验收** | —        |


---

## 5. 测试用例

### 5.1 后端接口测试

---

#### TC-BE-001：v2 Key 合法提交（Gate 全 Pass）

**优先级**：P0  
**前置条件**：

- Upload 状态为 `DERIVED_READY`，当前用户为 `qa` 角色
- 该用户尚未提交过该 upload

**请求**：`POST /data/qa/uploads/:upload_id/review`

```json
{
  "qa_round": 1,
  "qa_score": 75,
  "review_result": {
    "rubric_version": "v2",
    "upload_id": "<id>",
    "sampled_episode_id": ["<valid_ids>"],
    "upload_score": 75,
    "upload_vote": "pass",
    "result": [{
      "gate": {
        "is_camera_feed_clear": "pass",
        "is_task_completed": "pass",
        "is_robot_hand_visible": "pass",
        "are_cameras_in_sync": "pass"
      },
      "score": {
        "robot_control_quality": 4,
        "movement_smoothness": 4,
        "task_completion_speed": 3,
        "task_fully_completed": 4,
        "variation_across_episodes": 3
      }
    }]
  }
}
```

**期望结果**：

- HTTP 200，`success: true`
- `data_qa_sessions` 新增一条记录，`qa_score=75`，`review_result.upload_vote=pass`

---

#### TC-BE-002：v2 Key 合法提交（Gate 含 Fail）

**优先级**：P0  
**前置条件**：同 TC-BE-001  
**变更**：`is_camera_feed_clear: "fail"`，`upload_vote: "fail"`，`upload_score: 20`，`qa_score: 20`  
**期望结果**：

- HTTP 200，`success: true`
- `data_qa_sessions` 记录 `qa_score=20`，`review_result.upload_vote=fail`

---

#### TC-BE-003：旧 v1 Key 提交——应被拒绝

**优先级**：P0  
**请求**：`result[0].gate` 使用旧 key，如 `{ "prohibited_data": "pass", "complete_task": "pass", ... }`（不含任何 v2 key）  
**期望结果**：

- HTTP 400
- `msg` 包含 `is_camera_feed_clear must be pass/fail`（或其他 v2 key 的缺失错误）

---

#### TC-BE-004：Gate 值非法（非 pass/fail）

**优先级**：P0  
**变更**：任意 gate key 值设为 `"yes"` / `"1"` / `null` / `""`  
**期望结果**：

- HTTP 400，`msg` 包含该 key 的 `must be pass/fail` 错误信息

---

#### TC-BE-005：Score 值越界

**优先级**：P0  
**测试点**：

- 值为 `0`（低于下限）→ HTTP 400
- 值为 `6`（超出上限）→ HTTP 400
- 值为 `"abc"`（非整数）→ HTTP 400
- 值为 `null`（缺失）→ HTTP 400
- 值为 `1.5`（浮点数）→ 需验证后端 `int()` 转换行为（Python `int(1.5)=1`，可能通过）

**期望结果**：

- 值 0 / 6 / "abc" / null → HTTP 400，`msg` 包含 `must be integer 1-5`
- 值 `1.5` → 建议验证并记录实际行为（当前后端用 `int()` 转换，可能不报错）

---

#### TC-BE-006：qa_score 与 review_result.upload_score 不一致

**优先级**：P0  
**变更**：`qa_score: 75`，`review_result.upload_score: 60`  
**期望结果**：

- HTTP 400，`msg` 包含 `qa_score must equal review_result.upload_score`

---

#### TC-BE-007：result 数组长度与 sampled_episode_id 不一致

**优先级**：P1  
**测试点**：

- `sampled_episode_id: [101, 102]`，`result: []`（空数组）→ HTTP 400
- `sampled_episode_id: [101, 102]`，`result: [{...}]`（少 1 条）→ HTTP 400
- `sampled_episode_id: [101]`，`result: [{...}, {...}]`（多 1 条）→ HTTP 400

**期望结果**：HTTP 400，`msg` 包含 `must contain one item per sampled episode`

---

#### TC-BE-008：重复提交同一 Upload

**优先级**：P0  
**前置条件**：该用户已提交过该 upload（`data_qa_sessions` 已有记录）  
**期望结果**：HTTP 409，`msg` 包含 `already submitted a review for this upload`

---

#### TC-BE-009：sampled_episode_id 与服务端期望不一致

**优先级**：P1  
**步骤**：提交时 `sampled_episode_id` 传入不匹配的 episode id 集合  
**期望结果**：

- HTTP 400，`msg` 包含 `sampled_episode_id mismatch for this round`
- 响应体包含 `expected_sampled_episode_id`（便于客户端诊断）

---

#### TC-BE-010：qa_round 传值与服务端推断不一致

**优先级**：P1  
**步骤**：Upload 实际处于 round 1（DERIVED_READY），请求体传 `qa_round: 2`  
**期望结果**：HTTP 400，错误说明 round 不匹配

---

#### TC-BE-011：GET /data/qa/get-validator-access-data——正常响应

**优先级**：P1  
**前置条件**：有效 Bearer token，该用户有若干 `data_qa_sessions` 记录（假设 N 条）  
**期望结果**：

- HTTP 200，`success: true`
- `data.reviews_done` = N（跨月全量统计）
- `data.spots_remaining: 100`，`data.spots_total: 100`（当前静态值）
- `data.reviews_allowed.amplifier: 10`，`data.reviews_allowed.innovator: 30`

---

#### TC-BE-012：GET /data/qa/get-validator-access-data——鉴权异常

**优先级**：P1  


| 场景                     | 期望                                  |
| ---------------------- | ----------------------------------- |
| 无 Authorization header | HTTP 400，`msg: "Token is required"` |
| Token 无效 / 已过期         | HTTP 401，`msg: "Invalid token"`     |


---

#### TC-BE-013：dont_show_again=true 时 users.settings 更新

**优先级**：P0  
**步骤**：

1. 提交 review 时携带 `dont_show_again_validator_access_modal: true`
2. 提交成功后查询 `users.settings`（通过 `/user-info` 或直接查 DB）

**期望结果**：`users.settings.dont_show_again_validator_access_modal = true`，其他 settings 字段不受影响（JSONB `||` 合并）

---

#### TC-BE-014：dont_show_again=false 时 settings 不变

**优先级**：P1  
**步骤**：提交 review 不携带该字段，或值为 `false`  
**期望结果**：`users.settings` 中该字段不存在或仍为原值

---

#### TC-BE-015：dont_show_again=true 但 review 提交失败时 settings 不更新

**优先级**：P1（事务原子性验证）  
**步骤**：构造一个必然失败的 review 提交（如 sampled_episode_id 不匹配），同时携带 `dont_show_again_validator_access_modal: true`  
**期望结果**：`users.settings` 不变，事务回滚，两者同步

---

#### TC-BE-016：Round 1 达阈值——无分歧时状态更新

**优先级**：P0  
**前置条件**：

- 3 名 `qa` 用户各提交一次，gate 全部一致，score 差值 < 30

**期望结果**：

- 第 3 次提交返回 HTTP 200，响应包含 `final_decision`
- `data_uploads.status` 变更为 `REVIEW_FIRST_ROUND_SUCCEEDED`
- `final_decision.final_gate_passed: true`
- `final_decision.final_quality_score` = 3 人分数的中位数

---

#### TC-BE-017：Round 1 达阈值——Gate 分歧时进入 Round 2

**优先级**：P0  
**前置条件**：

- 3 名 `qa` 用户各提交，其中 1 人 `is_camera_feed_clear: "fail"`，其余 2 人 `"pass"`

**期望结果**：

- `data_uploads.status` 变更为 `REVIEW_FIRST_ROUND_FAILED`
- 响应不包含 `final_decision`（或 final_decision 为空）

---

#### TC-BE-018：Round 1 达阈值——Score 分歧时进入 Round 2

**优先级**：P1  
**前置条件**：

- 3 名 `qa` 用户各提交，gate 全部一致，但 score 差值 = 30（边界值）

**期望结果**：`data_uploads.status` 变更为 `REVIEW_FIRST_ROUND_FAILED`（score_gap >= 30 触发分歧）

**补充**：验证 score_gap = 29 时不触发分歧（`REVIEW_FIRST_ROUND_SUCCEEDED`）

---

#### TC-BE-019：Senior QA 用户可审阅 Round 2 Upload

**优先级**：P1  
**前置条件**：Upload 状态为 `REVIEW_FIRST_ROUND_FAILED`，用户 `user_role = senior qa`  
**步骤**：`GET /data/qa/uploads`  
**期望结果**：列表包含该 upload（senior qa 优先队列）

---

#### TC-BE-020：qa 角色用户无法看到 Round 2 的 Upload

**优先级**：P1  
**前置条件**：同 TC-BE-019，但用户 `user_role = qa`  
**步骤**：`GET /data/qa/uploads`  
**期望结果**：列表不包含该 upload（状态不在 qa 角色的可视范围内）

---

#### TC-BE-021：多集提交——所有 episode 均 pass

**优先级**：P0  
**前置条件**：Upload 有 ≥ 5 个 DERIVED_READY episode，用户为 qa 角色，未提交过

**步骤**：

1. `GET .../episodes` 获取 `sampled_episode_id`（假设抽到 N 条）
2. 为每条 episode 构造合法 gate（全 pass）+ score（均为 4）
3. 计算 `episode_score = int(round((4×5/5)/5×100)) = 80`，`episode_vote = "pass"`
4. `upload_score = 80`，`upload_vote = "pass"`，`qa_score = 80`
5. POST 提交

**期望结果**：HTTP 200，`success: true`，`data_qa_sessions` 新增一条记录

---

#### TC-BE-022：多集提交——部分 episode 含 gate fail

**优先级**：P0  
**步骤**：抽样中有 1 条 episode `is_camera_feed_clear = "fail"`，其余全 pass；对应 `episode_vote = "fail"`，其余 `"pass"`；`upload_vote = "fail"`（非全 pass）；所有计算值一致

**期望结果**：HTTP 200，`success: true`

---

#### TC-BE-023：episode_vote 与 gate 推导不一致——应被拒绝

**优先级**：P0  
**步骤**：某条 episode gate 全为 pass，但 `episode_vote = "fail"`

**期望结果**：HTTP 400，`msg` 包含 `episode_vote mismatch`

---

#### TC-BE-024：episode_score 与 score 均值计算不一致——应被拒绝

**优先级**：P0  
**步骤**：某条 episode score 均为 4（期望 `episode_score = 80`），但传入 `episode_score = 75`

**期望结果**：HTTP 400，`msg` 包含 `episode_score mismatch`

---

#### TC-BE-025：upload_vote 与 episode_vote 聚合不一致——应被拒绝

**优先级**：P0  
**步骤**：所有 episode 均 `episode_vote = "pass"`，但 `upload_vote = "fail"`

**期望结果**：HTTP 400，`msg` 包含 `upload_vote mismatch`

---

#### TC-BE-026：upload_score 与 episode_score 均值不一致——应被拒绝

**优先级**：P0  
**步骤**：episode_scores = [80, 80]，期望 `upload_score = 80`，但传入 `upload_score = 75`；`qa_score` 同样不一致

**期望结果**：HTTP 400，`msg` 包含 `upload_score mismatch`

---

#### TC-BE-027：result 中 episode_id 重复——应被拒绝

**优先级**：P1  
**步骤**：`sampled_episode_id: [101, 102]`，`result` 中两条均为 `episode_id: 101`

**期望结果**：HTTP 400，`msg` 包含 `episode_id must be unique`

---

#### TC-BE-028：result 未覆盖全部 sampled episode——应被拒绝

**优先级**：P1  
**步骤**：`sampled_episode_id: [101, 102]`，result 只有 episode 101 一条（缺 102）

**期望结果**：HTTP 400，`msg` 包含 `must cover all sampled episodes`

---

#### TC-BE-029：抽样比例验证——大 Upload

**优先级**：P1  
**前置条件**：Upload 有 200 个 DERIVED_READY episode

**步骤**：`GET .../episodes`，检查 `meta.sample_size` 和 `meta.sampled_episode_id` 长度

**期望结果**：

- `sample_size = 10`（200 × 5% = 10，满足 max(5, 10) = 10）
- `sampled_episode_id` 长度 = 10
- 两个不同 QA 用户独立请求同一 upload，`sampled_episode_id` 完全相同（确定性抽样）

---

#### TC-BE-030：GET /data/qa/uploads 精简响应——只含 upload_id 和 task_id

**优先级**：P1  
**步骤**：QA 用户 `GET /data/qa/uploads`

**期望结果**：

- 每条记录仅含 `upload_id`、`task_id` 两个字段
- **不含** `machine_id`、`status`、`qa_round`、`episode_count`、`reviewer_role` 等字段
- 响应时间可观察到明显改善（无 JOIN/GROUP BY）

---

#### TC-BE-031：GET /data/qa/uploads/preview-urls 接口验证

**优先级**：P1  
**前置条件**：QA 用户，有 `DERIVED_READY` episode 且 GCS 中存在派生视频的 Upload（upload_id = A）；及无派生视频的 Upload（upload_id = B）

**场景 1：正常请求**  
请求：`GET /data/qa/uploads/preview-urls?uploads={A}&uploads={B}`  
期望：HTTP 200，`previews[A]` 为有效 Signed URL；`previews[B]` 为 `null`；URL TTL ≈ 86400 秒

**场景 2：缺少 uploads 参数**  
请求：`GET /data/qa/uploads/preview-urls`（无参数）  
期望：HTTP 400，`msg: "At least one uploads param is required"`

**场景 3：非整数 uploads 值**  
请求：`GET /data/qa/uploads/preview-urls?uploads=abc`  
期望：HTTP 400，`msg` 包含 `Invalid uploads value`

**场景 4：非 QA 角色**  
请求：以 operator / 普通用户 token 请求  
期望：HTTP 403，`msg: "qa access required"`

---

### 5.2 前端 E2E / UI 测试

---

#### TC-FE-001：QA v2 维度标签完整展示

**优先级**：P0  
**步骤**：登录 QA 账号，进入 DataQAReview 页面  
**期望结果**：

- Gate 区域展示且仅展示 4 个维度（Clear camera feed / Task completed as instructed / Robot hand stays in frame / All cameras in sync）
- Score 区域展示且仅展示 5 个维度（Robot control quality / Movement smoothness / Task completion speed / Task fully completed / Variation across episodes）
- 不出现任何 v1 标签（Prohibited data / Operator Skill / Trajectory smoothness 等）

---

#### TC-FE-002：所有字段未填时提交按钮禁用

**优先级**：P0  
**步骤**：进入 DataQAReview 页面，不填任何 gate/score  
**期望结果**：Submit 按钮为 `disabled` 状态，点击无响应

---

#### TC-FE-003：dont_show_again=false 时提交打开弹窗

**优先级**：P0  
**前置条件**：账号 `users.settings` 中无 `dont_show_again_validator_access_modal`（或为 false）  
**步骤**：填写所有评审字段 → 点击 Submit  
**期望结果**：

- `ValidatorAccessModal` 弹出
- 不直接调用 `POST .../review`（Network 面板无该请求）

---

#### TC-FE-004：dont_show_again=true 时提交直接跳过弹窗

**优先级**：P0  
**前置条件**：账号 `users.settings.dont_show_again_validator_access_modal = true`  
**步骤**：填写所有评审字段 → 点击 Submit  
**期望结果**：

- 弹窗不出现
- 直接调用 `POST .../review`
- 提交成功后 `CustomNotification` 出现，标题 "Scores submitted"

---

#### TC-FE-005：ValidatorAccessModal——Amplifier 用户展示

**优先级**：P1  
**前置条件**：`userClass = "Amplifier Member"`，`reviews_done = N`（来自 API）  
**步骤**：触发弹窗打开  
**期望结果**：

- 弹窗默认 Tab 为 AmplifierTab（自动定位到对应角色 Tab）
- 展示 `N / 10 reviews` 进度（真实 API 数据）
- `spots_remaining: 100 / 100 validator spots remaining`
- "Start reviewing" 按钮**可点击**
- ExplorerTab 内 "Upgrade to Amplifier" 按钮**禁用**（`isDisabled=true`）
- InnovatorTab 内 "Begin validation" 按钮**禁用**

---

#### TC-FE-006：ValidatorAccessModal——Explorer 用户展示

**优先级**：P1  
**前置条件**：`userClass = "Explorer Member"`  
**步骤**：触发弹窗打开  
**期望结果**：

- 默认 Tab 为 ExplorerTab
- 展示 "Review & Earn is not available for Explorer members" 文案
- "Upgrade to Amplifier" 按钮**可点击**（Explorer 自己的 Tab 不禁用）
- AmplifierTab 内 "Start reviewing" 按钮**禁用**
- InnovatorTab 内 "Begin validation" 按钮**禁用**

---

#### TC-FE-007：ValidatorAccessModal——Innovator 用户展示

**优先级**：P1  
**前置条件**：`userClass = "Innovator Member"`  
**步骤**：触发弹窗打开  
**期望结果**：

- 默认 Tab 为 InnovatorTab
- 展示 `reviews_done / 30 reviews` 进度
- "Begin validation" 按钮**可点击**
- ExplorerTab / AmplifierTab 内提交按钮**禁用**

---

#### TC-FE-008：弹窗内提交——成功流程（不勾选"不再显示"）

**优先级**：P0  
**前置条件**：Amplifier 用户，弹窗已打开  
**步骤**：

1. 不勾选"不再显示"复选框
2. 点击 "Start reviewing"

**期望结果**：

- 按钮立即变为 "Submitting..."（loading 状态，`isDisabled=true`）
- `POST .../review` 请求 body 中 `dont_show_again_validator_access_modal: false`
- 提交成功后弹窗关闭
- `CustomNotification` 出现，标题 "Scores submitted"，进度条开始倒计时

---

#### TC-FE-009：弹窗内提交——勾选"不再显示"后提交

**优先级**：P0  
**步骤**：

1. 打开弹窗
2. 勾选"不再显示"复选框
3. 点击提交

**期望结果**：

- `POST .../review` body 中 `dont_show_again_validator_access_modal: true`
- `CustomNotification` 的 `onDismiss` 执行后（约 4s+250ms），`userSettings` 更新
- 再次点击 Submit **不再弹窗**（直接提交）
- 登录刷新后 `dont_show_again` 状态从 DB 恢复（弹窗仍不出现）

---

#### TC-FE-010：弹窗关闭——不提交

**优先级**：P1  
**步骤**：弹窗打开后点击右上角 × 或点击遮罩层  
**期望结果**：

- 弹窗关闭
- 不触发 `POST .../review`（Network 无该请求）
- `CustomNotification` 不出现

---

#### TC-FE-011：CustomNotification 自动消失与数据刷新

**优先级**：P1  
**步骤**：触发提交成功后，`CustomNotification` 出现，等待自动消失（约 4s，不手动关闭）  
**期望结果**：

- 进度条在 4s 内匀速耗尽（动画可观察）
- 4s 后通知卡片开始淡出（约 250ms）
- 淡出完成后 `loadUploadEpisodes` 和 `fetchUploads` 的网络请求被触发（Network 面板）
- Upload 列表/状态更新（当前已提交的 upload 移出或更新状态）

---

#### TC-FE-012：CustomNotification 手动关闭

**优先级**：P1  
**步骤**：`CustomNotification` 出现后立即点击 × 关闭  
**期望结果**：

- 通知立即开始淡出（约 250ms）
- 淡出后 `onDismiss` 执行，数据刷新请求立即发起（早于自动关闭的 4s）

---

#### TC-FE-013：get-validator-access-data 请求仅在需要时发起

**优先级**：P1  
**步骤**：观察 Network 面板  
**期望结果**：

- `dont_show_again = false` 时，进入 DataQAReview 页面触发 1 次 `GET .../get-validator-access-data`
- `dont_show_again = true` 时，进入页面**不发起**该请求（`useCallback` 内部的 `if (!dontShowAgainValidatorAccessModal)` 守卫生效）

---

#### TC-FE-014：提交后数据刷新时机（延迟至通知消失）

**优先级**：P1  
**步骤**：提交成功后立即观察 Network 面板  
**期望结果**：

- `loadUploadEpisodes` 和 `fetchUploads` 的请求**不在提交成功后立即发起**
- 请求在 `onDismiss` 执行后才发起（约提交成功后 4s+250ms）

---

#### TC-FE-015：进度条 cursor 样式

**优先级**：P2  
**步骤**：进入 DataQAReview，鼠标悬停在视频播放进度条（`<input type="range">`）上  
**期望结果**：光标显示为手型（`cursor: pointer`）

---

#### TC-FE-016：多集评审——每个 episode 独立评分展示

**优先级**：P0  
**前置条件**：QA 用户，选择一个有多条抽样 episode 的 upload

**步骤**：

1. 进入 DataQAReview
2. 选择对应 upload（或 scenario）
3. 观察 episode 列表与评分区域

**期望结果**：

- 每个被抽中的 episode 可独立看到 gate + score 评分区域
- 切换 episode 时评分不互相覆盖（各 episode 独立维护 reviewState）
- `effectiveSampledEpisodeIds` 数量与 `meta.sampled_episode_id` 一致

---

#### TC-FE-017：批次锁定——填写部分内容后尝试切换 scenario

**优先级**：P1  
**前置条件**：选中一个多集 upload，对其中一个 episode 填写了至少一项 rubric

**步骤**：

1. 在当前 episode 填写部分评分
2. 尝试切换 Scenario 下拉

**期望结果**：

- Scenario 下拉无法展开（blocked=true）
- 点击后触发 Warning 通知，文案包含 `Please complete reviewing current N episode(s) before leaving this upload`
- 路由不跳转，当前 episode 评分状态保留

---

#### TC-FE-018：批次锁定——填写部分内容后尝试返回

**优先级**：P1  
**前置条件**：同 TC-FE-017

**步骤**：点击"Back"按钮

**期望结果**：

- Warning 通知出现，不执行 `navigate(-1)`
- 再次点击相同结果（不会因多次点击而跳过锁定）

---

#### TC-FE-019：非上传路由不触发机器列表请求

**优先级**：P1  
**步骤**：

1. 直接导航到 `/data/review`（QA 审阅页）
2. 打开 Network 面板观察请求

**期望结果**：

- 无 `/data/machines` 请求（`fetchMachineListOnce` 不被调用）
- 仍有 `/data/tasks` 请求（task 列表依然加载）
- 页面正常显示，无功能异常

---

#### TC-FE-020：Expert QA Upload 选择器显示条件

**优先级**：P1  
**前置条件**：用户 `user_role = expert qa` 或 `super qa`，某 Scenario 下存在 ≥ 2 个 Upload

**步骤**：

1. 以 expert qa 或 super qa 账号登录，进入有多个 Upload 的 Scenario
2. 观察 Breadcrumb 区域

**期望结果**：

- Breadcrumb 中 ScenarioDropdown 后出现 Upload 下拉（`Upload #xxx`），以 `/` 分隔
- 默认选中第一个 Upload
- 该 Scenario 只有 1 个 Upload 时，Upload 下拉不出现
- 非 expert qa / super qa 角色（qa / senior qa）登录时，无论 Upload 数量，Upload 下拉均不出现

---

#### TC-FE-021：Expert QA Upload 切换 + URL 同步

**优先级**：P1  
**前置条件**：expert qa 账号，某 Scenario 有 Upload A 和 Upload B

**步骤**：

1. 进入审阅页，默认选中 Upload A
2. 展开 Upload 下拉，选择 Upload B
3. 观察 URL 和 Episode 列表

**期望结果**：

- URL 变为 `/data/review/:taskId?upload=<B_upload_id>`（replace 模式，不产生新历史记录）
- Episode 列表更新为 Upload B 的 Episodes
- 切换后评分区域清空（`locallySubmittedEpisodeIds` / `reviewState` 不被 Upload B 的数据污染）

---

#### TC-FE-022：?upload= URL 参数深链

**优先级**：P1

**场景 A：expert qa，有效 upload_id**  
前置条件：expert qa 账号，Upload B 存在于当前 Scenario 的 filteredUploads 中  
步骤：直接访问 `/data/review/:taskId?upload=<B_upload_id>`  
期望：页面加载后自动选中 Upload B，Episode 列表为 Upload B 的内容

**场景 B：expert qa，upload_id 不在当前 Scenario**  
步骤：访问 `?upload=99999`（无效 id）  
期望：降级选中第一个 Upload（`filteredUploads[0]`）；URL 中 `?upload=` 参数自动更新为实际选中的 Upload ID；页面弹出 warning 通知 "The requested upload was not available for review. Redirecting to a similar upload."；刷新后不再触发二次降级

**场景 C：非 advanced QA 角色**  
步骤：以 qa / senior qa 身份访问含 `?upload=` 的 URL  
期望：`?upload=` 参数被忽略，选中第一个 Upload，无异常

---

#### TC-FE-023：Upload 选择器批次锁保护

**优先级**：P1  
**前置条件**：expert qa 账号，多个 Upload，已对当前 Episode 填写至少一项 rubric（`hasStartedCurrentBatch = true`）

**步骤**：

1. 填写当前 Episode 的任意一项 rubric
2. 尝试展开 Upload 下拉并切换到另一个 Upload

**期望结果**：

- Upload 下拉无法展开（`blocked=true`），点击触发 Warning 通知
- expert qa 角色 Warning 通知文案包含 `Please submit or clear your current batch of N episode(s) before leaving this upload`
- Upload 选择器保持原有选中值，Episode 列表不变
- 已填写的 rubric 内容保留

---

#### TC-FE-024：Episode 切换时视频自动归零

**优先级**：P0  
**前置条件**：QA 用户，有多集抽样的 Upload，视频有实际可播放内容

**步骤**：

1. 打开 Episode 1 的视频，播放至某一时间进度（如 10 秒处）
2. 点击切换到 Episode 2（Prev/Next 按钮或 Episode 列表）
3. 观察 Episode 2 视频播放器的初始状态

**期望结果**：

- Episode 2 的视频从 0:00 开始（`currentTime = 0`），不从 Episode 1 的进度继续
- 视频处于暂停状态（`isPlaying = false`），不自动播放
- 返回 Episode 1 后，再次从头开始（不保留上次播放位置）

---

#### TC-FE-025：Scenario 下拉 dataTasks prop 修复

**优先级**：P1  
**前置条件**：QA 用户，系统中存在多个 Scenario（Task）

**步骤**：

1. 进入 `/data/review` QA 审阅页（通过 DataReviewViewer 路径）
2. 点击 Breadcrumb 中的 Scenario 下拉
3. 观察下拉选项列表

**期望结果**：

- 下拉展开后显示所有可用 Scenario 选项（来自 `dataTasks` 数组）
- 选项不为空，不出现 "No options" 或空下拉状态
- 选择不同 Scenario 后路由正常跳转（如 `/data/review/:newTaskId`）

---

#### TC-FE-027：DataReviewHub 正常渲染与卡片展示

**优先级**：P0  
**前置条件**：QA 用户（任意 QA 角色），系统中存在可审阅的 Upload（`DERIVED_READY` 状态）

**步骤**：

1. 以 QA 账号登录，访问 `/data/review`
2. 观察页面渲染

**期望结果**：

- 渲染 `DataReviewHub` 组件，无白屏或 JS 报错
- 每个可审阅 Upload 以卡片形式展示，显示任务信息
- `expert qa` / `super qa` 角色的卡片上显示 `#<uploadId>` 数字标识；`qa` / `senior qa` 不显示
- 顶部 viewer bar 不出现（Hub 页面不触发 `isReviewViewerRoute`）
- 无可审阅 Upload 时显示空状态，无报错

---

#### TC-FE-028：DataReviewHub 卡片视频预览懒加载

**优先级**：P1  
**前置条件**：QA 用户，可审阅 Upload 有 `DERIVED_READY` 的 episode 且 GCS 中存在派生视频

**步骤**：

1. 打开 DataReviewHub，Network 面板就绪
2. 观察首屏渲染后的网络请求与卡片缩略图

**期望结果**：

- 前端发起 `GET /data/qa/uploads/preview-urls?uploads=…&uploads=…` 请求，包含可见卡片的 upload_id
- 有预览视频的卡片显示循环播放的 `<video>` 缩略图（自动播放、静音）
- 无派生视频的 Upload 卡片降级显示占位框，不报错
- 同一 upload_id 不重复请求（`requestedUploadPreviewsRef` 去重生效）
- 翻页时对新出现的 upload_id 补充请求

---

#### TC-FE-029：expert qa — Add to batch / Remove from batch

**优先级**：P0  
**前置条件**：用户 `user_role = expert qa`，进入 DataQAReview 页面，有多个 Episode

**步骤**：

1. 选择 Episode A，填写全部 gate + score 字段
2. 观察主操作按钮文案 → 应为 "Add to batch"
3. 点击 "Add to batch"
4. 观察通知、批次计数变化和自动跳转
5. 返回 Episode A，观察按钮文案变为 "Remove from batch"
6. 点击 "Remove from batch"

**期望结果**：

- 步骤 3 后：通知 "Episode A added to batch. 1 selected for final submission."；自动跳到下一集；"Batch selected: 1" 计数更新
- 步骤 6 后：通知 "Episode A removed from batch."；"Batch selected" 归 0
- `POST .../review` 不被调用（未触发最终提交）

---

#### TC-FE-030：expert qa — Finalize Batch Submit

**优先级**：P0  
**前置条件**：expert qa 用户，已向 batch 中添加 ≥ 1 个 Episode（所有已选 episode 的 rubric 均填写完整）

**步骤**：

1. 确认 "Submit selected episodes (N)" 按钮可点击（N > 0，`uploadRubricResult.ready = true`）
2. 点击 "Submit selected episodes (N)"
3. 根据 `dontShowAgainValidatorAccessModal` 状态决定走 ValidatorAccessModal 或直接提交

**期望结果**：

- 若 `dont_show_again = true`：直接调用 `POST .../review`；成功后 batch 清空、通知"Scores submitted"
- 若 `dont_show_again = false`：ValidatorAccessModal 弹出；弹窗内点击提交后同上
- batch 为空（N=0）时点击按钮 → Warning："Add at least one episode to the batch before final submit."；不调用接口
- 非 expert qa 角色不显示该按钮

---

#### TC-FE-031：expert qa — Clear batch

**优先级**：P1  
**前置条件**：expert qa 用户，batch 中有 ≥ 1 个 Episode

**步骤**：点击 "Clear batch" 按钮

**期望结果**：

- 通知："Cleared current expert QA batch."
- "Batch selected: 0"；"Submit selected episodes (0)" 按钮变为 disabled
- 所有已添加 episode 的按钮文案恢复为 "Add to batch"
- `POST .../review` 不被调用
- batch 为空时 "Clear batch" 按钮为 disabled

---

#### TC-FE-032：expert qa — 批次锁 Warning 文案

**优先级**：P1  
**前置条件**：expert qa 用户，batch 中已有 ≥ 1 个 Episode（`hasStartedCurrentBatch = true`）

**步骤**：

1. 尝试切换 Scenario 下拉
2. 尝试点击 Back 按钮

**期望结果**：

- 两种操作均弹出 Warning，文案为：`"Please submit or clear your current batch of N episode(s) before leaving this upload."`
- 与普通 QA / super qa 文案（`"Please complete reviewing current N episode(s) before leaving this upload."`）**不同**
- 路由不跳转，batch 保留

---

#### TC-FE-033：Upload 选择器对 expert qa 和 super qa 可见

**优先级**：P1  
**前置条件**：用户 `user_role = super qa` 或 `expert qa`，某 Scenario 下存在 ≥ 2 个 Upload

**步骤**：以 super qa 或 expert qa 账号进入有多个 Upload 的 Scenario，观察 Breadcrumb 区域

**期望结果**：

- Upload 选择器在 Breadcrumb 中显示（两种角色均可见，`isAdvancedQa = isExpertQa || isSuperQa`）
- 切换 Upload 时 URL 同步为 `?upload=<id>`
- batch 中有内容时切换触发批次锁 Warning：expert qa 显示批次专属文案；super qa 显示普通 QA 文案（"Please complete reviewing..."）
- Round Tag 显示（`shouldShowRoundTag` 含 super qa 和 expert qa）

---

### 5.3 边界与异常测试

---

#### TC-EDGE-001：ValidatorAccessData 接口失败时弹窗降级展示

**优先级**：P1  
**步骤**：通过 DevTools / Charles 拦截，模拟 `GET .../get-validator-access-data` 返回 500  
**期望结果**：

- `validatorAccessData = null`，弹窗仍可打开
- 进度展示使用 `?? '--'` 降级，如 `-- / 10` / `-- / 30`
- 弹窗不崩溃（无 JS 报错）
- "Start reviewing" / "Begin validation" 按钮仍可点击提交

---

#### TC-EDGE-002：提交 API 失败时弹窗正确关闭

**优先级**：P1  
**步骤**：模拟 `POST .../review` 返回 400 或 500  
**期望结果**：

- 全局错误通知出现（非 CustomNotification）
- `finally` 块中 `ValidatorAccessModal` 被关闭（弹窗不卡住）
- `CustomNotification` 不出现

---

#### TC-EDGE-003：快速连续点击提交——防重复提交

**优先级**：P1  
**步骤**：在弹窗内快速连续点击 "Start reviewing" 两次  
**期望结果**：

- `submittingUploadReview = true` 后函数 early return，只发送 1 次 API 请求
- 按钮在 loading 状态期间为 disabled，无法点击

---

#### TC-EDGE-004：Tab 切换——非当前 userClass 的进度展示

**优先级**：P2  
**前置条件**：Amplifier 用户  
**步骤**：弹窗打开后切换到 InnovatorTab  
**期望结果**：InnovatorTab 中 `reviews_done` 显示 `--`（因 `userClass !== 'Innovator Member'`，`reviewsDone` 传入为 null），展示 `-- / 30`

---

#### TC-EDGE-005：提交时 sampled_episode_id 与服务端不一致

**优先级**：P1  
**步骤**：手动构造请求，`sampled_episode_id` 使用不存在或错误的 episode id  
**期望结果**：

- HTTP 400，`msg` 包含 `sampled_episode_id mismatch`
- 响应包含 `expected_sampled_episode_id`，便于客户端同步

---

#### TC-EDGE-006：Score 差值恰好为 30——分歧判定边界

**优先级**：P2  
**前置条件**：Round 1，前 2 名 reviewer 已提交 `qa_score=40` 和 `qa_score=70`（差 30），gate 一致  
**步骤**：第 3 名 reviewer 提交任意合法 score  
**期望结果**：

- score_gap = 30（max - min = 70 - 40）→ `has_disagreement = true`
- `data_uploads.status = REVIEW_FIRST_ROUND_FAILED`

---

#### TC-EDGE-007：分歧最终决策——Gate fail 优先合并

**优先级**：P2  
**前置条件**：Round 3（expert qa），单人提交  
**步骤**：构造 gate 中部分 key 为 fail  
**期望结果**：

- `final_decision.final_gate` 中对应 key 为 `fail`
- `final_gate_passed = false`，`final_upload_vote = "fail"`

---

## 6. 已知限制与风险说明


| 项目                                       | 描述                                                                                              | 风险等级     | 建议                                                              |
| ---------------------------------------- | ----------------------------------------------------------------------------------------------- | -------- | --------------------------------------------------------------- |
| `spots_remaining` 静态值                    | 始终显示 100/100，不反映真实名额                                                                            | Low      | 后续迭代接入真实计算逻辑                                                    |
| `reviews_done` 跨月统计                      | 不区分月份，展示值可能远超月度配额上限，造成用户困惑                                                                      | Medium   | 后续迭代改为按当月统计                                                     |
| `dont_show_again` 刷新恢复依赖 user-management | 若 `/user-info` 响应不携带 `settings` 字段，页面刷新后 `userSettings = {}`，弹窗将再次出现                            | **High** | 需验证 user-management 登录响应是否带 `settings` 字段；若不带，需前后端联调修复          |
| ScoringModal / SelectionModal 未接入        | 两个 WIP 组件仅存在于代码中，`ValidatorAccessModal` 内 import 均注释掉                                           | N/A      | 不在当前版本验收范围内                                                     |
| `dont_show_again` 事务原子性                  | review 提交失败时 settings 不更新，逻辑正确；但测试需显式验证                                                         | Low      | TC-BE-015 覆盖                                                    |
| float score 值的隐式转换                       | Python `int(1.5) = 1`，可能导致浮点分数静默通过校验                                                            | Low      | 建议后端补充 `isinstance(value, int)` 类型检查，或在 TC-BE-005 中记录当前行为作为已知问题 |
| seed v1 → v2 切换影响已有 session              | 同一 upload/round 的新旧抽样结果不同；若测试环境中某 upload 已有 v1 session，该 session 将不被复用                          | Medium   | 测试时注意清理或新建 Upload，避免旧 v1 session 干扰抽样一致性验证（TC-BE-029）           |
| `get_qa_uploads` 精简后客户端适配                | API 仅返回 `upload_id` + `task_id`，前端如依赖旧字段（`status`、`qa_round` 等）将空值或报错                           | **High** | 测试须验证 QA 列表页在精简响应下功能完整，重点检查是否有空指针或展示异常（TC-BE-030）               |
| 批次锁定不阻止浏览器后退按钮                           | 仅拦截 React `navigate(-1)` 调用，若用户直接点击浏览器原生后退或关闭标签页，批次状态将丢失                                        | Low      | 可在后续版本通过 `beforeunload` 或 `useBlocker`（React Router v6）补充拦截     |
| expert qa 批次提交与服务端校验                     | expert qa 的 `sampled_episode_id` 由前端自选，后端只做子集校验；若传入 all_episode_id_set 之外的 episode_id，后端仍返回 400 | Medium   | TC-FE-030 覆盖 E2E 验证                                             |
| DataReviewHub 预览视频 TTL 1 天               | 卡片视频 Signed URL 仅 1 天有效，用户长时间停留在 Hub 页面后视频加载失败，需刷新页面重新请求预览 URL                                  | Low      | 告知用户刷新页面可恢复；后续可考虑定时刷新预览 URL                                     |
| Expert QA Upload 切换不保留评分状态               | 切换 Upload 后，原 Upload 的 `reviewState` / `locallySubmittedEpisodeIds` 不被保存；若用户误切换再切回，已填写内容丢失      | Low      | 批次锁可在一定程度上防止误操作；后续可考虑切换时弹出确认提示                                  |
| ?upload= URL 参数绕过批次锁                     | 批次锁仅保护 UI 操作，若用户在评分途中手动修改浏览器 URL 的 upload 参数，前端锁定无法感知，导致批次状态丢失                                  | Low      | 属于主动绕过行为，在当前阶段可接受；后续可通过路由 blocker 强化                            |


---

## 7. 测试优先级汇总


| 优先级              | 用例编号                                                                                                                                                                                              | 覆盖重点                                                                                                                              |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **P0（必测，上线前阻塞）** | TC-BE-001~~008, TC-BE-013, TC-BE-016~~017, TC-BE-021~~026, TC-FE-001~~004, TC-FE-008~009, TC-FE-016, TC-FE-024, TC-FE-027, TC-FE-029, TC-FE-030                                                   | v2 key 校验、完整提交流程、多轮状态流转、弹窗触发逻辑、dont_show_again、多集 per-episode 校验、Episode 切换视频归零、DataReviewHub 渲染、expert qa 批次 Add/Finalize        |
| **P1（重点，版本验收）**  | TC-BE-007, TC-BE-009~~012, TC-BE-014~~015, TC-BE-018~~020, TC-BE-027~~031, TC-FE-005~~007, TC-FE-010~~015, TC-FE-017~~019, TC-FE-020~~023, TC-FE-025, TC-FE-028, TC-FE-031~~033, TC-EDGE-001~~005 | 数据接口、边界校验、弹窗数据展示、通知行为、错误流程、防重复、批次锁定、精简列表、抽样比例验证、Expert QA Upload 选择器、Scenario 下拉修复、DataReviewHub 视频预览、expert qa Clear/Warning/选择器 |
| **P2（覆盖，时间允许）**  | TC-BE-019~~020, TC-FE-015, TC-EDGE-006~~007                                                                                                                                                       | 角色队列、UI 样式、分歧边界                                                                                                                   |
| **不验收**          | —                                                                                                                                                                                                 | ScoringModal、SelectionModal（WIP）                                                                                                  |


---

*文档编写：2026-04-12；当前版本：v3.2（2026-04-23）*