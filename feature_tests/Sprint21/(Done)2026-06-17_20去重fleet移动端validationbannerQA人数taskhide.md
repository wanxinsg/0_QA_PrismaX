# Prismax Validation 上线 — 2026-06-17 ~ 2026-06-21 Commit 分析与测试策略

**涉及仓库：** `app-prismax-rp`（前端）、`app-prismax-rp-backend`（后端）  
**日期跨度：** 2026-06-17 ~ 2026-06-21（作者时区 -0400）  
**提交作者：** lanmanc  
**涉及分支：** 前端 `testing`（`e0dab08` 为 HEAD）；后端 `testing`

| 仓库 | Commit 范围 | 改动规模 |
|------|------------|---------|
| app-prismax-rp | `c230da72` → `e0dab08e01`（18 commits） | 22 文件，+1174 / -1379 |
| app-prismax-rp-backend | `eb3507c1`、`f9bd5767`（2 commits） | 4 文件，+28 / -8 |

> **2026-06-21 追加批次（§2.8 ~ §2.10）：** `e6ea08b` → `e0dab08`（3 commits），涵盖 Upload Operator Gate、生产环境 task 隐藏、废弃组件清理；Validation Banner 移动端居中样式在 `f02accd` 中已回滚，**净效果无 CSS 变化**。

---

## 一、Commit 清单

### 1.1 前端（app-prismax-rp）

| # | Hash | 时间 | 说明 |
|---|------|------|------|
| 1 | `c230da7` | 06-17 22:52 | fixing duplication check for admin panel |
| 2 | `15206e6` | 06-19 17:42 | updated for mobile view |
| 3 | `9071c63` | 06-20 16:19 | Update dashboard validation banner |
| 4 | `e38533f` | 06-20 16:32 | Update mobile dashboard validation banner |
| 5 | `b2def3f` | 06-20 17:05 | Tune mobile dashboard carousel heights |
| 6 | `beb2a7b` | 06-20 17:18 | Gate validation banner launch |
| 7 | `b642843` | 06-20 17:35 | Improve mobile data and dashboard layouts |
| 8 | `fd8d9ca` | 06-20 18:04 | Align validation banner typography |
| 9 | `939d682` | 06-20 18:34 | Replace text loading states with skeleton tiles |
| 10 | `b17a0f2` | 06-20 18:37 | Adjust mobile dashboard carousel spacing |
| 11 | `60e51f8` | 06-20 18:53 | Align mobile dashboard dots |
| 12 | `e25fadf` | 06-20 19:10 | Adjust mobile validation media spacing |
| 13 | `d7b4699` | 06-20 19:30 | Adjust dashboard carousel arrows |
| 14 | `1c21146` | 06-20 19:45 | Remove first dashboard left arrow |
| 15 | `af88371` | 06-20 23:40 | Fix dashboard reverse animation direction |
| 16 | `e6ea08b` | 06-21 14:21 | Center mobile validation banner content |
| 17 | `f02accd` | 06-21 17:47 | updated logic |
| 18 | `e0dab08` | 06-21 22:19 | fixing ui logic |

### 1.2 后端（app-prismax-rp-backend）

| # | Hash | 时间 | 说明 | 文件 |
|---|------|------|------|------|
| 19 | `eb3507c1` | 06-19 17:42 | changed the number for first round to 99 | `qa_helper.py` |
| 20 | `f9bd5767` | 06-19 20:18 | fixing galxe bug for eth | `app.py`、`galxe_rest_credential.py`、`test_galxe_rest_credential.py` |

---

## 二、主题分组与改动详细分析

### 2.1 Admin Panel — 视频去重检查修复（`c230da7`）

**仓库：** app-prismax-rp  
**文件：** `Admin/VideoDuplicateReviews.js` + `VideoDuplicateReviews.module.css`（+43 / -30）

- 修复 Admin 后台视频去重审核面板的重复检测逻辑
- 补充对应 CSS 样式（+15 行），优化去重结果展示

---

### 2.2 Fleet Robot Modal — 移动端适配（`15206e6`）

**仓库：** app-prismax-rp  
**文件：** `Fleet/RobotModalV2.module.css`（+115 行）

- 大规模补充移动端响应式样式
- 覆盖 Robot Modal 在窄屏下的布局、间距、字体等规则

---

### 2.3 Validation 上线 — 前端 Banner 与门控（`9071c63` ~ `fd8d9ca`）

**仓库：** app-prismax-rp  
**关联后端：** `eb3507c1`（QA 轮次阈值，见 §2.6）

这是本次变更的核心主题，前端 5 个 commit 组成完整的 Validation 入口迭代：

#### 2.3.1 倒计时组件（`9071c63`）

```
VALIDATION_LAUNCH_TIME = Date.UTC(2026, 5, 23, 16, 0, 0)
// 即 2026-06-23 16:00:00 UTC = PDT 09:00 AM
```

- 新增 `renderValidationCountdown()` 函数，计算 `days / hours / minutes / seconds`
- `isLive` 状态：`Date.now() >= VALIDATION_LAUNCH_TIME` 时为 `true`
- Banner 显示文案：未上线 → `"Goes live Tue, Jun 23 · 9:00 AM PDT"`；已上线 → `"Validation is now live"`
- 倒计时时钟使用 `setInterval` 每秒更新，卡片样式全面重写（`Dashboard.module.css` +104）

#### 2.3.2 移动端 Banner（`e38533f`）

- 在移动端 Carousel 中渲染 validation banner（`Dashboard.js` +29）
- 移动端专属 CSS 规则 +110 行，涵盖尺寸、间距、字体、动效

#### 2.3.3 功能门控（`beb2a7b`）

```js
const handleBeginValidating = () => {
    if (Date.now() < VALIDATION_LAUNCH_TIME) {
        showNotification?.('info', 'Coming soon. Goes live Tue, Jun 23 · 9:00 AM PDT.');
        return;
    }
    navigate('/data/review');
};
```

- 点击 "Begin Validating" 按钮时检查 `VALIDATION_LAUNCH_TIME`
- 未到时间：触发全局 info 通知，**不跳转**
- 已到时间：正常导航至 `/data/review`
- 同步修改 `renderValidationCountdown` 签名：新增 `showClock` 参数，部分场景可隐藏倒计时时钟

#### 2.3.4 字体排版对齐（`fd8d9ca`）

- 纯 CSS 改动，7 处样式调整，统一 banner 文字间距与字重

---

### 2.4 Dashboard Carousel — 移动端打磨（`b2def3f` ~ `af88371`）

**仓库：** app-prismax-rp

7 个 commit 对 Carousel 导航和动画进行系统性打磨：

| Commit | 内容 | 文件 |
|--------|------|------|
| `b2def3f` | 调整 carousel 高度（+21/-26） | `Dashboard.module.css` |
| `b642843` | 整体优化移动端 Data + Dashboard 布局（4 文件，+40/-10） | `Dashboard.js/.module.css`、`RoboticDataPage2.module.css`、`RoboticDataWorkspace.module.css` |
| `b17a0f2` | Carousel 间距微调（+3/-3） | `Dashboard.module.css` |
| `60e51f8` | 分页指示点对齐修复（+6/-3） | `Dashboard.module.css` |
| `e25fadf` | Validation media 间距 1 行调整 | `Dashboard.module.css` |
| `d7b4699` | 重写箭头渲染逻辑：改为条件渲染（`typeof prevTarget/nextTarget === 'number'`），移动端双向箭头 | `Dashboard.js`（+34/-13）|
| `1c21146` | 移除首屏左箭头（首页无 prev 时不显示） | `Dashboard.js`（-9）|
| `af88371` | **修复反向动画方向**：简化为 `newPage > currentPage ? 'forward' : 'backward'`，修复边缘翻页方向错误 | `Dashboard.js`（+1/-3）|

**Carousel 核心逻辑：**
- `currentPage` state + `changePage(newPage)` 函数
- 支持：点击箭头 / 点击 dots / 触屏 swipe（`handleTouchStart/Move/End`）
- 动画方向由 `newPage > currentPage` 决定（`af88371` 修复后）
- `isMobile` 断点：`useIsMobile(930)`

---

### 2.5 Skeleton Loading 统一（`939d682`）

**仓库：** app-prismax-rp  
**影响面最广的单个 commit**，6 个文件 +286 行：

| 模块 | 改动 |
|------|------|
| `DataReviewHub.js` | 新增 `ReviewHubSkeleton` 组件，`isQaUploadsLoading` 时展示 |
| `DataReviewHub.module.css` | Skeleton tile 动画样式 |
| `Upload.js` | 加载时展示 Skeleton |
| `Upload.module.css` | Skeleton 样式 |
| `RoboticDataWorkspace.js` | 加载时展示 Skeleton |
| `RoboticDataWorkspace.module.css` | Skeleton 样式 |

所有模块原来的 `"Loading uploads…"` 文字 loading 全部替换为 skeleton tile 动画。

---

### 2.6 QA 审核轮次人数调整（`eb3507c1`）

**仓库：** app-prismax-rp-backend  
**文件：** `app_prismax_data_pipeline/qa_helper.py`  
**关联前端：** §2.3 Validation Banner 引导用户进入 `/data/review` 后，本改动控制 upload 状态何时流转

#### 变更内容

```python
# 变更前
QA_REVIEWER_COUNT_BY_ROUND = {1: 3, 2: 2, 3: 1}

# 变更后
QA_REVIEWER_COUNT_BY_ROUND = {1: 99, 2: 9, 3: 1}
```

| 轮次 | 变更前 | 变更后 | 影响 |
|------|--------|--------|------|
| Round 1 | 3 | **99** | 第一轮需累计 99 份审核才会触发状态流转 |
| Round 2 | 2 | **9** | 第二轮需 9 份审核才会汇总 |
| Round 3 | 1 | 1 | 无变化（专家仲裁轮） |

#### 运行时逻辑（`app_prismax_data_pipeline/app.py` — QA Review 提交接口）

1. 插入当前 reviewer 的 `data_qa_sessions` 记录
2. 查询同一 `upload_id` + `qa_round` 下全部 session：`round_rows`
3. `round_required = QA_REVIEWER_COUNT_BY_ROUND.get(qa_round, 1)`
4. **仅当** `len(round_rows) >= round_required` 时：
   - 调用 `_detect_round_disagreement()` 检测 gate/score 分歧
   - 根据轮次与分歧结果更新 `data_uploads.status`（`*_SUCCEEDED` 或 `*_FAILED`）
   - Round 3 直接标记 `REVIEW_THIRD_ROUND_SUCCEEDED`
   - 无分歧时调用 `_build_final_decision()` 并触发 `_reward_final_decision_qa_points()` 积分奖励
5. API 响应始终返回：
   - `round_review_count` / `round_required_review_count`（现为 99/9/1）
   - `round_complete` / `status_updated`

#### 业务含义

- **Round 1 → 99**：Validation 上线初期，同一 upload 不会在 3 人提交后就结束，需凑满 99 份才汇总——与前端 Banner「大规模验证启动」策略一致
- **Round 2 → 9**：分歧复核轮门槛提高，Senior QA 队列需更多 reviewer 才能推进
- **前端可见性**：Review Hub 在 `round_complete=false` 时 upload 仍停留当前 status；单次提交 review 不会立即改变 upload 终态

---

### 2.7 Galxe REST 校验 — EVM 地址支持（`f9bd5767`）

**仓库：** app-prismax-rp-backend  
**文件：** `app_prismax_user_management/app.py`、`galxe_rest_credential.py`

#### 问题背景

原实现仅通过 `solana_receive_address` 精确匹配 Galxe 用户，导致通过 **ETH / Base / Monad** 钱包注册且 `acquisition_source='galxe'` 的用户无法通过 Galxe Quest 校验接口。

#### 变更内容

**地址标准化：**

```python
def normalize_wallet_address(address): ...   # 新增，通用 trim
def normalize_solana_address(address):       # 保留，委托 normalize_wallet_address
```

**接口入参扩展**（`GET /api/galxe/verify-registration`）：

| 参数 key（优先级从左到右） | 说明 |
|---------------------------|------|
| `address` | 通用地址 |
| `wallet_address` | 通用钱包地址 |
| `solana_address` | Solana 地址（原有） |
| `evm_address` | **新增**，EVM 链地址 |

**数据库查询逻辑：**

```sql
-- 变更后
WHERE acquisition_source = 'galxe'
  AND (
    solana_receive_address = :address          -- Solana：精确匹配
    OR LOWER(ethereum_receive_address) = :address_lower
    OR LOWER(base_receive_address) = :address_lower
    OR LOWER(monad_receive_address) = :address_lower
  )
```

- **Solana**：精确匹配（Base58 大小写敏感）
- **EVM 链**：`LOWER()` 大小写不敏感
- 鉴权/错误码未变：503（未配置 Key）、401（Unauthorized）、400（Missing address）

---

### 2.8 Validation Banner 移动端居中 — 提交后回滚（`e6ea08b` + `f02accd`）

**仓库：** app-prismax-rp  
**文件：** `Dashboard/Dashboard.module.css`

#### `e6ea08b` 改动（居中）

- `.mobileValidationText`：`align-items: center`，`text-align: center`，padding `40px 48px 0`
- `.mobileValidationTitle`：`text-align: center`
- `.mobileValidationText .countdown`：flex 居中
- `.mobileValidationButton`：`align-self: center`

#### `f02accd` 改动（回滚为左对齐）

- 恢复 `align-items: flex-start`、`text-align: left`、padding `40px 40px 0`
- 移除 countdown flex 居中
- 按钮恢复 `align-self: flex-start`

#### 净效果

相对 `e6ea08b` 之前，**`Dashboard.module.css` 无净变化**。现有 MB-01 ~ MB-06 用例仍适用；无需新增居中专项用例，但回归时应确认 `f02accd` 回滚未引入布局回归。

---

### 2.9 生产环境 Task 隐藏 + 废弃组件清理（`f02accd`）

**仓库：** app-prismax-rp  
**改动规模：** 7 文件，+28 / -1205

#### 2.9.1 新增 `src/utils/taskVisibility.js`

```js
const PRODUCTION_APP_ORIGIN = 'https://app.prismax.ai';
const PRODUCTION_HIDDEN_TASK_IDS = new Set(['12']);

export function isTaskHiddenOnProduction(taskOrEpisode) { ... }
export function filterProductionHiddenTasks(rows) { ... }
```

**规则：**
- 仅当 `window.location.origin === 'https://app.prismax.ai'` 时生效
- 隐藏 `task_id = '12'` 的任务/episode/upload
- 支持 `task_id` 与 `taskId` 两种字段名
- 非生产 origin（localhost、staging、beta）**不受影响**

**接入点（API 返回后过滤）：**

| 模块 | 过滤对象 |
|------|----------|
| `DataHub.js` | task list 缓存、QA uploads |
| `DataQAReview.js` | QA uploads |
| `UploadDashboard.js` | uploads 列表 |
| `RoboticDataWorkspace.js` | tasks、episodes |

#### 2.9.2 删除 `RoboticData/RoboticData.js`（-1190 行）

- 旧版 Robotic Data 页面组件，当前路由已改用 `RoboticDataPage2` → `RoboticDataWorkspace`
- 代码库内 **无任何 import 引用**，属死代码清理
- 回归重点：确认 `/robotic-data` 路由仍正常，无 404 或白屏

---

### 2.10 Upload Operator Gate — 非 Operator 上传 UX 重构（`e0dab08`）

**仓库：** app-prismax-rp  
**改动规模：** 6 文件，+396 / -19

#### 2.10.1 行为变更对比

| 场景 | 变更前 | 变更后 |
|------|--------|--------|
| 非 operator 用户 | 顶部 warning banner；Upload 按钮 `disabled` | 无 banner；按钮可点，弹出 Operator Gate Modal |
| 点击 Task Card | 仅 operator 可触发（`startUploadFlow` 内 early return） | 所有用户可点 → 打开 `UploadInfoModal` |
| 点击 Upload 按钮 | 同 Card，且 disabled | `startDirectUploadFlow` → 跳过 Info Modal，直接进文件选择 |
| 未登录用户上传 | 部分场景无明确引导 | Toast：`Please log in to upload data.` |
| 实际上传（`handleUpload`） | Toast error | 弹出 Operator Gate Modal |

#### 2.10.2 双入口上传流程

```
点击 Task Card ──→ startUploadFlow() ──→ UploadInfoModal
                                              │
                              点击 "Upload data" ──→ handleUploadInfoContinue()
                                              │
点击 Upload 按钮 ──→ startDirectUploadFlow() ──┘
                                              │
                         已登录 + 是 operator ──→ File Upload Modal
                         已登录 + 非 operator ──→ Operator Gate Modal
                         未登录 ──────────────→ Toast warning
```

#### 2.10.3 Operator Gate Modal（新增 UI）

**触发条件：** 非 operator 用户尝试上传（Direct Upload / Info Modal Continue / handleUpload）

**Modal 内容：**
- 标题：`Register as an operator to upload`
- 说明：需 robot arm 才能 capture episodes
- **Optional 卡片** → 关闭 Modal 并导航 `/fleet`
- **Register as operator** → 关闭 Modal 并导航 `/account?open=register-robot`（带 `state.openOperatorRegisterModal: true`）
- **Maybe later** / 关闭按钮 / 点击 backdrop → 关闭 Modal

**样式：** `Upload.module.css` 新增 `.operatorGate*` 系列（~200 行）；Task Card 增加 hover/focus-visible 交互。

#### 2.10.4 Account 页 Deep Link 自动打开注册弹窗

**`Account.js`：**
```js
const shouldOpenOperatorRegisterModal =
    location.state?.openOperatorRegisterModal
    || new URLSearchParams(location.search).get('open') === 'register-robot';
```

**`OperatorSection.js`：**
- 新增 prop `autoOpenRegisterModal`
- `useEffect`：登录完成且非 loading 时自动调用 `handleRegisterNewRobot()`（仅一次，`hasAutoOpenedRegisterModalRef` 防重复）
- 未登录时不自动打开

#### 2.10.5 UploadInfoModal 微调

- Upload 按钮 SVG 改为完整 upload 图标（带底边 tray）
- `.btnPrimary` 固定 `height: 33px`，padding 调整

---

## 三、测试策略

### 3.1 整体风险评估

| 特性 | 层级 | 风险等级 | 原因 |
|------|------|----------|------|
| Validation 功能门控 | 前端 | **高** | 时间逻辑直接影响用户能否进入核心功能，且依赖系统时间 |
| QA Round 1 阈值 99 | 后端 | **高** | 直接影响 upload 状态流转；与 Validation 上线策略强绑定 |
| Galxe EVM 地址匹配 | 后端 | **高** | 外部 Galxe Quest 依赖此接口；ETH 大小写、多链字段需全覆盖 |
| Dashboard Carousel 动画 | 前端 | **中** | 多种导航方式（箭头 / dots / swipe），移动端适配复杂 |
| Validation Banner 移动端 | 前端 | **中** | 独立 mobile 布局、隐藏倒计时时钟、视频 inline 播放、dots 对齐 |
| Data 页面移动端布局 | 前端 | **中** | Review Hub / Upload / Workspace 窄屏布局与 skeleton 适配 |
| QA Round 2 阈值 9 | 后端 | **中** | 影响分歧复核轮推进速度 |
| Admin 去重修复 | 前端 | **中** | Admin 功能，影响内部操作正确性 |
| Galxe Solana 回归 | 后端 | **中** | 查询条件重构，需确认 Solana 路径未被破坏 |
| Skeleton Loading | 前端 | **低** | UI 替换，不涉及业务逻辑，但需保证 3 个模块一致性 |
| Robot Modal 移动端 | 前端 | **中** | 多断点（768px/430px）响应式，触摸交互与滚动行为需验证 |
| Upload Operator Gate | 前端 | **高** | 非 operator 上传路径全面重构；双入口 + Modal + Account deep link 多分支 |
| 生产环境 Task 隐藏 | 前端 | **中** | 仅生产 origin 生效；需 staging/local 与 production 对比验证 |
| RoboticData.js 删除 | 前端 | **低** | 死代码清理；仅需确认 `/robotic-data` 路由无回归 |

### 3.2 测试重点与策略

#### 策略一：Validation 全链路（前端门控 + 后端阈值，最高优先级）

Validation 上线时间：**2026-06-23 16:00:00 UTC（PDT 09:00 AM）**

**前端 — 时间门控：**
- **上线前**：按钮不可跳转，弹出 info 通知
- **上线后**：正常导航至 `/data/review`
- **倒计时精度**：`days/hours/minutes/seconds` 数值正确，每秒更新
- 测试手段：mock `Date.now()` / 修改 `VALIDATION_LAUNCH_TIME`；E2E 中通过 `page.evaluate` 覆盖

**后端 — 轮次阈值（与前端联动）：**
- 通过 API 提交 QA review，观察 `round_required_review_count`、`round_complete`、`status_updated`
- Round 1：第 1~98 次 `round_complete=false`；第 99 次才触发汇总
- Round 2：第 1~8 次未完成；第 9 次触发
- upload 未满员时 status 保持不变（如 `DERIVED_READY`）
- 用户从 Banner 进入 Review Hub 提交 1 次 review 后，upload 不应过早消失或状态跳变

#### 策略二：Carousel 与 Dashboard 移动端专项测试

移动端断点：**930px**（`useIsMobile(930)`）；小屏手机：**420px**（`useIsMobile(420)`）；Fleet Modal：**768px / 430px**

- Validation Banner 使用独立 `mobileValidationBox` 布局，**移动端不渲染倒计时时钟**（`showClock: !isMobile`），仅显示上线文案
- Carousel 支持 swipe / 箭头 / dots；首页无左箭头；slide 高度 `--mobile-dashboard-slide-height` 需跨页一致
- 验证 `playsInline` 视频自动播放、触摸目标可点击、dots 居中对齐
- Data 页面（Review Hub / Upload / Workspace）在 ≤930px 下 skeleton 与内容布局无溢出

#### 策略三：Carousel 多端多交互组合测试（桌面）

涉及 3 种导航方式 × 2 种屏幕模式（移动 / 桌面）× 边界页面（首页、末页）：
- 首页不显示左箭头；末页不显示右箭头
- 翻页动画方向正确（forward/backward）
- 循环翻页边界（如从末页到首页）

#### 策略四：Skeleton Loading 一致性检查

- DataReviewHub / Upload / RoboticDataWorkspace 三处 skeleton 展示条件统一
- 数据加载完成后 skeleton 正确消失，内容正常渲染
- 骨架结构与真实内容布局大致吻合（避免 layout shift）

#### 策略五：Galxe REST 接口多链覆盖

- 准备测试用户：`acquisition_source='galxe'`，分别绑定 Solana / ETH / Base / Monad 地址
- EVM 地址大小写混合查询（DB 小写，查询大写）应匹配成功
- 负向：非 galxe 来源用户、未注册地址、错误 API Key
- 参数别名：`evm_address`、`wallet_address`、`address` 均可传入
- 运行 `test_galxe_rest_credential.py` 单元测试回归

#### 策略六：回归兜底

- 所有改动在 `testing` 分支，上线前需全流程回归
- 重点回归：Dashboard 整页渲染、`/data/review` 入口、Mobile 视图、QA API 响应字段、Galxe 校验接口

#### 策略七：Upload Operator Gate 全分支（2026-06-21 新增，高优先级）

**用户角色矩阵：**

| 角色 | Task Card 点击 | Upload 按钮点击 | Info Modal Continue | 实际上传 |
|------|---------------|----------------|---------------------|----------|
| 未登录 | UploadInfoModal → Continue → Toast | Toast | Toast | Toast / Gate |
| 已登录非 operator | UploadInfoModal → Gate Modal | Gate Modal | Gate Modal | Gate Modal |
| 已登录 operator | UploadInfoModal → File Modal | File Modal | File Modal | 正常上传 |

**Deep Link 闭环：**
- Gate Modal「Register as operator」→ `/account?open=register-robot` → RegisterRobotModal 自动打开
- 验证 URL 参数与 navigation state 两种入口等价
- 未登录跳转 Account 时不应自动弹窗（需先登录）

**UI/交互：**
- Task Card hover/focus-visible 效果
- Gate Modal：backdrop 点击关闭、Escape（如有）、Maybe later、Fleet 卡片跳转
- 确认顶部 operator warning banner **已移除**

#### 策略八：生产环境 Task 隐藏（2026-06-21 新增）

- **生产 origin**（`https://app.prismax.ai`）：task_id=12 在 DataHub / Upload / QA Review / Upload Dashboard / RoboticDataWorkspace **均不可见**
- **非生产 origin**（localhost、staging、beta）：task_id=12 **仍可见**
- 测试手段：Playwright `page.addInitScript` mock `window.location.origin`，或在 staging 与 production 分别人工核对
- 边界：`taskId` vs `task_id` 字段、空数组、非数组入参

#### 策略九：RoboticData 路由回归（2026-06-21 新增）

- 确认 `RoboticData.js` 删除后 `/robotic-data`、`/robotic-data/:episodeId` 仍由 `RoboticDataPage2` 正常渲染
- 有/无 `hasRoboticDataAccess` 权限两种路径
- Admin 侧 `RoboticDataAdmin` 不受影响

### 3.3 测试环境要求

- **视口**：桌面（>930px）；移动端（≤930px，推荐 390×844 iPhone 14）；小屏（≤420px）；Fleet Modal 额外测 768px / 430px
- **设备**：除浏览器 DevTools 外，建议在真机（iOS Safari / Android Chrome）验证 touch、视频 autoplay、Modal 滚动
- **时间 mock**：Validation 门控测试需 mock `Date.now()` 或修改 `VALIDATION_LAUNCH_TIME`
- **网络延迟**：Skeleton 测试需 slow 3G 或接口延迟 mock
- **QA 阈值测试**：需多个 QA 测试账号（或脚本模拟 token）对同一 upload 提交 review；或临时调低常量验证流转逻辑
- **Galxe 测试**：需配置 `GALXE_REST_API_KEY`；准备 galxe 来源测试用户及多链地址数据
- **服务**：`app_prismax_data_pipeline`（QA API）、`app_prismax_user_management`（Galxe API）
- **Upload Operator Gate 测试**：需准备 3 类账号——未登录、已登录非 operator、已登录 operator；operator 判定依据 `userRole === 'operator'`（不区分大小写）
- **Task 隐藏测试**：需 API 返回含 task_id=12 的数据；生产环境验证需部署到 `app.prismax.ai` 或 mock origin

---

## 四、E2E / API 测试用例汇总

> 前缀说明：`VB` = Validation Banner，`QA-R` = QA Review 轮次阈值，`CR` = Carousel，`SK` = Skeleton，`GX` = Galxe REST 校验，`AD` = Admin，`FM` = Fleet Modal，`MB` = Mobile 移动端专项，`OG` = Operator Gate Upload，`TV` = Task Visibility 生产隐藏，`AC` = Account Deep Link，`RD` = RoboticData 路由回归

| ID | 模块 | 层级 | 平台 | 用例标题 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|----|------|------|------|----------|----------|----------|----------|--------|
| VB-01 | Validation Banner | 前端 | 桌面 | 上线前：倒计时显示正确 | mock `Date.now()` < `VALIDATION_LAUNCH_TIME`；视口 > 930px | 打开 Dashboard，查看 Validation 卡片 | 显示 `"Goes live Tue, Jun 23 · 9:00 AM PDT"`；倒计时 days/hrs/min/sec 数值正确且每秒递减 | P0 |
| VB-02 | Validation Banner | 前端 | 桌面 | 上线前：点击 Begin Validating 触发通知 | mock `Date.now()` < `VALIDATION_LAUNCH_TIME`；视口 > 930px | 点击 Begin Validating 按钮 | 页面不跳转；显示 info 通知 `"Coming soon. Goes live Tue, Jun 23 · 9:00 AM PDT."` | P0 |
| VB-03 | Validation Banner | 前端 | 桌面 | 上线后：倒计时切换为 Live 状态 | mock `Date.now()` >= `VALIDATION_LAUNCH_TIME`；视口 > 930px | 打开 Dashboard，查看 Validation 卡片 | Banner 显示 `"Validation is now live"`；无倒计时时钟 | P0 |
| VB-04 | Validation Banner | 前端 | 桌面 | 上线后：点击 Begin Validating 正常跳转 | mock `Date.now()` >= `VALIDATION_LAUNCH_TIME`；视口 > 930px | 点击 Begin Validating 按钮 | 页面导航至 `/data/review`，无 info 通知 | P0 |
| VB-05 | Validation Banner | 前端 | 桌面 | 倒计时跨越上线时刻自动切换 | mock 时间从上线前 1 秒推进到上线后；视口 > 930px | 停留在 Dashboard 等待倒计时归零 | 无需刷新，Banner 自动切换为 Live 状态 | P1 |
| VB-06 | Validation Banner | 前端 | 移动端 | 移动端 Banner 正常渲染 | 视口 ≤ 930px；上线前 | 打开 Dashboard | Carousel 首屏可见 `mobileValidationBox` 布局；标题/副标题/按钮/视频无溢出 | P0 |
| VB-07 | Validation Banner | 前端 | 移动端 | 移动端 Banner 门控逻辑 | 视口 ≤ 930px；上线前 | 点击 Begin Validating | 触发 info 通知，不跳转 | P0 |
| MB-01 | Validation Banner | 前端 | 移动端 | 移动端不显示倒计时时钟 | mock 上线前；视口 ≤ 930px | 查看 Validation Banner | 仅显示 subtitle / goes live 文案；**无** days/hrs/min/sec 数字时钟（`showClock: false`） | P0 |
| MB-02 | Validation Banner | 前端 | 移动端 | 移动端 validation 视频 inline 自动播放 | 视口 ≤ 930px | 打开 Dashboard Validation 页 | 视频静音自动播放（`playsInline`、`muted`）；无播放控件；不被浏览器强制全屏 | P1 |
| MB-03 | Validation Banner | 前端 | 移动端 | 移动端上线后 Live 状态与跳转 | mock 已上线；视口 ≤ 930px | 查看 Banner 后点击 Begin Validating | 显示 Live 文案；正常跳转 `/data/review` | P0 |
| MB-04 | Validation Banner | 前端 | 移动端 | 小屏手机布局（≤420px） | 视口 ≤ 420px；上线前/后各测一次 | 打开 Dashboard Validation 页 | 标题、按钮、视频、dots 无溢出；按钮可点击 | P1 |
| MB-05 | Validation Banner | 前端 | 移动端 | 移动端 validation dots 居中对齐 | 视口 ≤ 930px | 查看 Banner 底部 `mobileValidationDots` | dots 水平居中，与 Carousel 其他页 dots 视觉对齐 | P1 |
| MB-06 | Validation Banner | 前端 | 移动端 | 移动端 validation media 间距正常 | 视口 ≤ 930px | 查看 Banner 文字区与视频区间距 | 文字与视频间距合理，无重叠或过大空白 | P2 |
| QA-R-01 | QA Review 轮次阈值 | 后端 | API | 第 1 次 review 未达阈值不更新 status | upload status=`DERIVED_READY`；Round 1 | 1 名 QA 提交 review | `round_required_review_count=99`，`round_review_count=1`，`round_complete=false`，`status_updated=false`；DB status 仍为 `DERIVED_READY` | P0 |
| QA-R-02 | QA Review 轮次阈值 | 后端 | API | 第 98 次 review 仍未完成 | 同一 upload 已有 97 条 Round 1 session | 第 98 名 QA 提交 review | `round_review_count=98`，`round_complete=false`，status 不变 | P0 |
| QA-R-03 | QA Review 轮次阈值 | 后端 | API | 第 99 次 review 触发 Round 1 汇总 | 同一 upload 已有 98 条 Round 1 session | 第 99 名 QA 提交 review（无分歧） | `round_complete=true`，`status_updated=true`，status=`REVIEW_FIRST_ROUND_SUCCEEDED` | P0 |
| QA-R-04 | QA Review 轮次阈值 | 后端 | API | 99 人分歧触发 FAILED | 同一 upload 98 条 session；第 99 人 gate/score 显著分歧 | 第 99 名 QA 提交 review | status=`REVIEW_FIRST_ROUND_FAILED`；Senior QA 队列可见 | P1 |
| QA-R-05 | QA Review 轮次阈值 | 后端 | API | Round 2 需 9 人完成 | upload status=`REVIEW_FIRST_ROUND_FAILED` | 依次提交 8 次 Round 2 review | 前 8 次 `round_complete=false`；status 不变 | P0 |
| QA-R-06 | QA Review 轮次阈值 | 后端 | API | Round 2 第 9 次触发汇总 | 同一 upload 已有 8 条 Round 2 session | 第 9 名 Senior QA 提交 review | `round_complete=true`，status 更新为 `REVIEW_SECOND_ROUND_*` | P0 |
| QA-R-07 | QA Review 轮次阈值 | 后端 | API | Round 3 仍为 1 人 | upload status=`REVIEW_SECOND_ROUND_FAILED` | 1 名 Expert QA 提交 Round 3 review | 立即 `round_complete=true`，status=`REVIEW_THIRD_ROUND_SUCCEEDED` | P1 |
| QA-R-08 | QA Review 轮次阈值 | 前后端 | 桌面 | 提交 review 不立即改变 upload 终态 | mock 已上线；upload 在 Review Hub 可见；视口 > 930px | 用户完成 1 次 review 提交 | 前端显示提交成功；upload 仍留在队列；无过早消失或状态跳变 | P1 |
| MB-07 | QA Review | 前后端 | 移动端 | 移动端从 Banner 进入并完成 review | mock 已上线；视口 ≤ 930px；QA 账号 | Dashboard → Begin Validating → Review Hub → 提交 1 次 review | 全流程可用；表单/modal 不溢出；upload 不因单次提交而流转 | P0 |
| CR-01 | Carousel | 前端 | 桌面 | 初始首页不显示左箭头 | 视口 > 930px | 查看 Carousel 首屏 | 左侧无箭头；右侧显示右箭头 | P0 |
| CR-02 | Carousel | 前端 | 桌面 | 末页不显示右箭头 | 视口 > 930px；末页 | 查看 Carousel | 右侧无箭头；左侧显示左箭头 | P0 |
| CR-03 | Carousel | 前端 | 桌面 | 点击右箭头向前翻页 | 视口 > 930px；首页 | 点击右箭头 | forward 动画，dots 高亮更新 | P0 |
| CR-04 | Carousel | 前端 | 桌面 | 点击左箭头向后翻页 | 视口 > 930px；非首页 | 点击左箭头 | backward 动画，dots 高亮更新 | P0 |
| CR-05 | Carousel | 前端 | 通用 | 动画方向正确 | 桌面或移动端 | 分别向前和向后翻页 | 向前：内容从右侧滑入；向后：从左侧滑入 | P0 |
| CR-06 | Carousel | 前端 | 通用 | 点击 dots 跳转到指定页 | 桌面或移动端 | 点击任意 dot | 切换至对应页，动画方向与目标方向一致 | P1 |
| CR-07 | Carousel | 前端 | 移动端 | 左右 swipe 翻页 | 视口 ≤ 930px | 在 Carousel 区域左滑后右滑 | 左滑前进；右滑后退；边界无翻页 | P0 |
| CR-08 | Carousel | 前端 | 移动端 | swipe 边界不超出首末页 | 视口 ≤ 930px；首页 | 向右滑动（尝试后退） | 停留在首页，无异常跳转 | P1 |
| CR-09 | Carousel | 前端 | 移动端 | 中间页双向箭头均显示 | 视口 ≤ 930px；中间页 | 查看 Carousel | 左右箭头均可见且可点击 | P1 |
| CR-10 | Carousel | 前端 | 通用 | 快速连续点击箭头无状态混乱 | 任意视口 | 快速连点右箭头 3 次 | 最终页面序号正确，无卡死/跳过 | P2 |
| MB-08 | Carousel | 前端 | 移动端 | 移动端首页无左箭头 | 视口 ≤ 930px；Carousel 首屏 | 查看 Validation 页 | 仅显示右箭头；无左箭头 | P0 |
| MB-09 | Carousel | 前端 | 移动端 | 移动端 slide 高度跨页一致 | 视口 ≤ 930px | swipe 在 Validation 页与 Control 页间切换 | 两页高度一致（`--mobile-dashboard-slide-height`），切换无高度跳动 | P1 |
| MB-10 | Carousel | 前端 | 移动端 | 移动端 swipe 动画方向正确 | 视口 ≤ 930px | 连续 swipe 前进/后退 | forward/backward 动画方向正确，无反向错误 | P0 |
| MB-11 | Carousel | 前端 | 移动端 | 移动端点击箭头翻页 | 视口 ≤ 930px | 点击右箭头再点击左箭头 | 翻页正常，dots 高亮同步更新 | P1 |
| MB-12 | Carousel | 前端 | 移动端 | 移动端 Control 页布局正常 | 视口 ≤ 930px | swipe 至第二页 Control 页 | 视频、标题、按钮、`paginationDots2` 布局正常 | P1 |
| MB-13 | Dashboard | 前端 | 移动端 | Points 数据区窄屏布局 | 视口 ≤ 930px | 查看 Dashboard 中部 All-Time / Daily Points 卡片 | 卡片堆叠或自适应排列；数值与图标可读，无横向溢出 | P1 |
| SK-01 | Skeleton Loading | 前端 | 桌面 | DataReviewHub 加载中显示 skeleton | API 延迟 2 s；视口 > 930px | 进入 Data Review Hub | 展示 skeleton tile，无 "Loading uploads…" | P0 |
| SK-02 | Skeleton Loading | 前端 | 桌面 | DataReviewHub skeleton 消失后内容正常 | 正常网络；视口 > 930px | 进入页面等待加载完成 | Skeleton 消失，视频卡片列表正常渲染 | P0 |
| SK-03 | Skeleton Loading | 前端 | 桌面 | Upload 页加载中显示 skeleton | API 延迟 2 s；视口 > 930px | 进入 Upload 页面 | 展示 skeleton，无旧文字 loading | P0 |
| SK-04 | Skeleton Loading | 前端 | 桌面 | Upload skeleton 消失后内容正常 | 正常网络；视口 > 930px | 进入 Upload 页面等待加载完成 | Skeleton 消失，上传列表正常渲染 | P0 |
| SK-05 | Skeleton Loading | 前端 | 桌面 | RoboticDataWorkspace 加载中显示 skeleton | API 延迟 2 s；视口 > 930px | 进入 Robotic Data Workspace | 展示 skeleton | P0 |
| SK-06 | Skeleton Loading | 前端 | 桌面 | RoboticDataWorkspace skeleton 消失后内容正常 | 正常网络；视口 > 930px | 进入页面等待加载完成 | Skeleton 消失，工作区内容正常渲染 | P0 |
| SK-07 | Skeleton Loading | 前端 | 通用 | API 返回空数据时 skeleton 正确消失 | API 返回 `[]` | 进入任意含 skeleton 的页面 | 显示空状态 UI，非一直 skeleton | P1 |
| SK-08 | Skeleton Loading | 前端 | 通用 | Skeleton 过渡无明显 layout shift | 网络延迟环境 | 观察 skeleton → 内容过渡 | 过渡自然，无闪烁 | P2 |
| MB-14 | Skeleton Loading | 前端 | 移动端 | DataReviewHub 移动端 skeleton | API 延迟 2 s；视口 ≤ 930px | 进入 Data Review Hub | skeleton tile 适配窄屏；无横向滚动条 | P0 |
| MB-15 | Skeleton Loading | 前端 | 移动端 | Upload 移动端 skeleton 与内容 | 视口 ≤ 930px | 进入 Upload 页面并等待加载 | skeleton 与列表内容布局正常（≤900px 断点） | P1 |
| MB-16 | Skeleton Loading | 前端 | 移动端 | RoboticDataWorkspace 移动端 skeleton | 视口 ≤ 930px | 进入 Workspace 并等待加载 | skeleton 与内容布局正常（820px/640px 断点） | P1 |
| MB-17 | Data Review | 前端 | 移动端 | Review Hub 审核 modal 窄屏可用 | 视口 ≤ 930px；mock 已上线 | 打开 scoring/selection modal 并完成操作 | modal 不超出视口；按钮可点击；可滚动查看全部字段 | P0 |
| MB-18 | Data 页面 | 前端 | 移动端 | Robotic Data 页面整体布局 | 视口 ≤ 768px | 浏览 Robotic Data 相关页面 | 布局随断点自适应，无内容被遮挡 | P1 |
| GX-01 | Galxe REST 校验 | 后端 | API | ETH 地址已注册用户校验通过 | 用户 `acquisition_source=galxe`，`ethereum_receive_address` 小写 | `GET ...?evm_address=0xABC...` + API Key | 200；`registered=true`，`eligible=1` | P0 |
| GX-02 | Galxe REST 校验 | 后端 | API | Base 地址匹配 | galxe 来源，仅 `base_receive_address` | `GET ...?address=<base_addr>` + API Key | `registered=true`，`eligible=1` | P0 |
| GX-03 | Galxe REST 校验 | 后端 | API | Monad 地址匹配 | galxe 来源，仅 `monad_receive_address` | `GET ...?wallet_address=<monad_addr>` + API Key | `registered=true`，`eligible=1` | P0 |
| GX-04 | Galxe REST 校验 | 后端 | API | Solana 地址回归（精确匹配） | galxe 来源，`solana_receive_address` 已填 | `GET ...?solana_address=<exact_addr>` + API Key | `registered=true`；大小写必须完全一致 | P0 |
| GX-05 | Galxe REST 校验 | 后端 | API | 非 galxe 来源用户不可 eligible | `acquisition_source` 非 galxe | 调用 verify-registration | `registered=false`，`eligible=0` | P0 |
| GX-06 | Galxe REST 校验 | 后端 | API | 未注册地址 | 无对应用户 | `GET ...?evm_address=0x000...` + API Key | `registered=false`，`eligible=0`，`success=true` | P1 |
| GX-07 | Galxe REST 校验 | 后端 | API | 缺少 address 参数 | 有效 API Key | `GET /api/galxe/verify-registration`（无 address） | 400；`msg="Missing address"` | P1 |
| GX-08 | Galxe REST 校验 | 后端 | API | 无效 API Key | — | 错误 `X-Galxe-Api-Key` | 401；`msg="Unauthorized"` | P1 |
| GX-09 | Galxe REST 校验 | 后端 | API | Bearer Token 鉴权 | 有效 API Key | `Authorization: Bearer <key>` | 200；正常返回 | P2 |
| GX-10 | Galxe REST 校验 | 后端 | API | EVM 地址大小写混合查询 | DB 小写，查询大写 | verify-registration | 匹配成功（LOWER 比较） | P0 |
| GX-11 | Galxe REST 校验 | 后端 | API | Galxe Quest 端到端 | Galxe 配置 REST credential 指向 testing | 完成 quest 条件后触发校验 | Quest 显示已完成；eligible=1 | P1 |
| AD-01 | Admin 去重 | 前端 | 桌面 | 视频去重检查结果正确显示 | 登录 Admin | 进入 Video Duplicate Reviews，触发去重 | 结果正确展示，无误报 | P1 |
| AD-02 | Admin 去重 | 前端 | 桌面 | 去重面板布局正常 | 登录 Admin | 进入 Video Duplicate Reviews | 无溢出、遮挡 | P2 |
| FM-01 | Fleet Modal | 前端 | 移动端 | Robot Modal 768px 布局正常 | 视口 ≤ 768px | 进入 Fleet，打开 Robot Modal | 内容完整展示，无横向溢出 | P1 |
| FM-02 | Fleet Modal | 前端 | 移动端 | Robot Modal 关闭正常 | 视口 ≤ 768px | 打开后点击关闭 | Modal 正常关闭，无残影 | P1 |
| MB-19 | Fleet Modal | 前端 | 移动端 | Robot Modal 430px 小屏布局 | 视口 ≤ 430px | 打开 Robot Modal | 文字不截断；按钮可点击；关键信息可见 | P1 |
| MB-20 | Fleet Modal | 前端 | 移动端 | Modal 内滚动不穿透背景 | 视口 ≤ 768px；Modal 内容较长 | 在 Modal 内上下滑动 | Modal 内滚动流畅；背景页面不跟随滚动 | P2 |
| MB-21 | 全链路 | 前后端 | 移动端 | Validation 移动端完整路径 | mock 已上线；视口 ≤ 930px；QA 账号 | Dashboard Banner → Review Hub → 提交 review | 全程无布局错乱；API 正常；upload 不立即流转 | P0 |
| MB-22 | 全链路 | 前端 | 移动端 | 真机 touch 与视频播放 | iOS Safari 或 Android Chrome 真机 | 打开 Dashboard Validation 页，swipe 翻页 | touch/swipe 响应正常；视频 autoplay 正常 | P1 |
| OG-01 | Upload Operator Gate | 前端 | 桌面 | 非 operator：Upload 按钮弹出 Gate Modal | 已登录；`userRole` ≠ operator；Upload 页有 task | 点击某 task 的 Upload 按钮 | 弹出 Operator Gate Modal；标题为 `Register as an operator to upload`；**不**打开 File Modal | P0 |
| OG-02 | Upload Operator Gate | 前端 | 桌面 | 非 operator：Task Card → Info Modal → Continue 弹出 Gate | 已登录非 operator | 点击 Task Card → UploadInfoModal 中点击 Upload data | Gate Modal 弹出；不进入 File Modal | P0 |
| OG-03 | Upload Operator Gate | 前端 | 桌面 | operator：Upload 按钮直达 File Modal | 已登录 operator | 点击 Upload 按钮 | 跳过 UploadInfoModal，直接打开 File Upload Modal | P0 |
| OG-04 | Upload Operator Gate | 前端 | 桌面 | operator：Task Card → Info Modal → Continue 正常 | 已登录 operator | 点击 Task Card → Upload data | 打开 File Upload Modal | P0 |
| OG-05 | Upload Operator Gate | 前端 | 桌面 | 未登录：Direct Upload 提示登录 | 未登录（无 gatewayToken） | 点击 Upload 按钮 | Toast：`Please log in to upload data.`；无 Gate Modal | P0 |
| OG-06 | Upload Operator Gate | 前端 | 桌面 | 未登录：Info Modal Continue 提示登录 | 未登录 | Task Card → Upload data | Toast：`Please log in to upload data.` | P0 |
| OG-07 | Upload Operator Gate | 前端 | 桌面 | Gate Modal：Register 跳转 Account 并自动开弹窗 | 已登录非 operator | Gate Modal 点击 Register as operator | URL 含 `open=register-robot`；RegisterRobotModal 自动打开（仅一次） | P0 |
| OG-08 | Upload Operator Gate | 前端 | 桌面 | Gate Modal：Fleet 卡片跳转 | 已登录非 operator | Gate Modal 点击 Optional Fleet 卡片 | Modal 关闭；导航至 `/fleet` | P1 |
| OG-09 | Upload Operator Gate | 前端 | 桌面 | Gate Modal：Maybe later 关闭 | 已登录非 operator | 点击 Maybe later | Modal 关闭；停留 Upload 页 | P1 |
| OG-10 | Upload Operator Gate | 前端 | 桌面 | Gate Modal：backdrop 点击关闭 | 已登录非 operator | 点击 Modal 外部 backdrop | Modal 关闭 | P2 |
| OG-11 | Upload Operator Gate | 前端 | 桌面 | 顶部 operator warning banner 已移除 | 已登录非 operator | 打开 Upload 页 | **无** `Your account is not marked as operator` banner | P0 |
| OG-12 | Upload Operator Gate | 前端 | 桌面 | Upload 按钮不再 disabled | 已登录非 operator | 查看 Upload 按钮 | 按钮可点击，无 disabled 样式 | P0 |
| OG-13 | Upload Operator Gate | 前端 | 桌面 | Task Card 键盘 Enter 触发 Info Modal | 已登录任意角色 | focus Task Card 后按 Enter | 打开 UploadInfoModal | P2 |
| OG-14 | Upload Operator Gate | 前端 | 桌面 | Upload 按钮 stopPropagation | 已登录 operator | 点击 Upload 按钮（非 Card 空白区） | 触发 Direct Upload，**不**仅打开 Info Modal | P1 |
| OG-15 | Upload Operator Gate | 前端 | 移动端 | 移动端 Gate Modal 布局正常 | 视口 ≤ 930px；已登录非 operator | 点击 Upload 按钮 | Modal 不超出视口；按钮可点击；Fleet 卡片可读 | P0 |
| OG-16 | Upload Operator Gate | 前端 | 移动端 | 移动端非 operator 完整引导路径 | 视口 ≤ 930px；已登录非 operator | Upload → Gate → Register → Account Modal | 全流程无布局错乱；RegisterRobotModal 正常展示 | P0 |
| AC-01 | Account Deep Link | 前端 | 桌面 | URL 参数 `?open=register-robot` 自动开弹窗 | 已登录 | 直接访问 `/account?open=register-robot` | RegisterRobotModal 自动打开 | P0 |
| AC-02 | Account Deep Link | 前端 | 桌面 | navigation state 自动开弹窗 | 已登录 | `navigate('/account', { state: { openOperatorRegisterModal: true } })` | RegisterRobotModal 自动打开 | P0 |
| AC-03 | Account Deep Link | 前端 | 桌面 | 未登录不自动开弹窗 | 未登录 | 访问 `/account?open=register-robot` | 不弹出 RegisterRobotModal（或先要求登录） | P1 |
| AC-04 | Account Deep Link | 前端 | 桌面 | 自动开弹窗仅触发一次 | 已登录 | 从 Upload Gate 跳转 Account 后关闭再刷新 | 刷新后不重复自动弹出（`hasAutoOpenedRegisterModalRef`） | P2 |
| TV-01 | Task Visibility | 前端 | 桌面 | 生产 origin 隐藏 task_id=12（DataHub） | mock origin=`https://app.prismax.ai`；API 含 task 12 | 打开 Data Hub / Upload | task_id=12 不出现在列表 | P0 |
| TV-02 | Task Visibility | 前端 | 桌面 | 非生产 origin 仍显示 task_id=12 | origin=`http://localhost:3000`；API 含 task 12 | 打开 Upload 页 | task_id=12 正常显示 | P0 |
| TV-03 | Task Visibility | 前端 | 桌面 | QA Review 列表过滤 | mock 生产 origin | 打开 `/data/review` | task_id=12 相关 upload 不可见 | P0 |
| TV-04 | Task Visibility | 前端 | 桌面 | Upload Dashboard 列表过滤 | mock 生产 origin | 打开 Upload Dashboard | task_id=12 upload 不可见 | P1 |
| TV-05 | Task Visibility | 前端 | 桌面 | RoboticDataWorkspace tasks/episodes 过滤 | mock 生产 origin；有 robotic data 权限 | 打开 `/robotic-data` | task_id=12 的 task/episode 不可见 | P1 |
| TV-06 | Task Visibility | 前端 | 桌面 | `taskId` 字段别名兼容 | mock 生产 origin；数据用 `taskId: '12'` | 打开含该数据的页面 | 同样被隐藏 | P2 |
| TV-07 | Task Visibility | 前端 | 桌面 | 空数组/非数组安全 | filter 入参 `null` / `undefined` | 调用 filter 逻辑（单元或页面加载） | 返回 `[]`，无 crash | P2 |
| RD-01 | RoboticData 路由 | 前端 | 桌面 | `/robotic-data` 正常渲染 | 有 robotic data 权限 | 访问 `/robotic-data` | RoboticDataPage2 + Workspace 正常；无白屏/404 | P0 |
| RD-02 | RoboticData 路由 | 前端 | 桌面 | `/robotic-data/:episodeId` 深链 | 有权限；有效 episodeId | 访问带 episodeId 的 URL | Workspace 加载对应 episode | P1 |
| RD-03 | RoboticData 路由 | 前端 | 桌面 | 无权限 Coming Soon | 无 robotic data 权限 | 访问 `/robotic-data` | 显示 Coming Soon / 无权限提示，非 crash | P1 |
| RD-04 | RoboticData 路由 | 前端 | 桌面 | Admin RoboticDataAdmin 不受影响 | Admin token | 打开 Admin Portal Robotic Data 页 | 正常加载，与 `RoboticData.js` 删除无关 | P2 |

---

## 五、回归清单

### 5.1 Validation 全链路（前后端联动）

1. Dashboard Validation Banner 完整渲染（桌面 + 移动端，上线前/后两种状态）
2. Begin Validating 门控：上线前拦截、上线后跳转 `/data/review`
3. Review Hub 提交 review 后 upload 不立即流转（Round 1 需 99 人）
4. QA API 响应字段正确（`round_required_review_count` 为 99/9/1）

### 5.2 前端 UI（含移动端）

5. Carousel 全页翻页（桌面箭头 + 移动端 swipe/箭头/dots）
6. Validation Banner 移动端：`mobileValidationBox` 布局、无倒计时时钟、视频 inline 播放、dots 对齐
7. Dashboard Points 区、Robotic Data 页面窄屏布局（≤930px / ≤768px）
8. Data Review Hub / Upload / RoboticDataWorkspace skeleton 加载（桌面 + 移动端）
9. Review Hub 审核 modal 移动端可用性
10. Admin Video Duplicate Reviews 正常访问
11. Fleet Robot Modal 移动端（768px / 430px）布局与滚动
12. 真机 touch / 视频 autoplay 验证（iOS Safari / Android Chrome）

### 5.3 后端 API

13. Round 1 未满 99 人 / Round 2 未满 9 人时 upload status 不流转
14. Galxe `/api/galxe/verify-registration` — Solana 回归 + ETH/Base/Monad 新路径
15. Galxe 非 galxe 用户隔离
16. `test_galxe_rest_credential.py` 全量通过

### 5.4 Upload Operator Gate 与 Account Deep Link（2026-06-21 新增）

17. 非 operator 用户 Upload 页无顶部 warning banner
18. Upload 按钮对非 operator 可点击，弹出 Operator Gate Modal
19. Task Card 与 Upload 按钮双入口行为正确（Info Modal vs Direct Upload）
20. Gate Modal → Register → `/account?open=register-robot` → RegisterRobotModal 自动打开
21. Gate Modal → Fleet → `/fleet` 跳转正常
22. operator 用户双入口均可进入 File Upload Modal 并完成上传
23. 未登录用户触发 Toast 而非 Gate Modal

### 5.5 生产环境 Task 隐藏（2026-06-21 新增）

24. 生产 origin 下 task_id=12 在 DataHub / Upload / QA Review / Upload Dashboard / RoboticDataWorkspace 均不可见
25. localhost / staging origin 下 task_id=12 仍可见

### 5.6 RoboticData 路由（2026-06-21 新增）

26. `/robotic-data` 及 episode 深链在 `RoboticData.js` 删除后仍正常
27. 无权限路径仍显示 Coming Soon，无 crash

---

## 六、已有 E2E 自动化覆盖

| 用例 ID |  spec 文件 | 状态 |
|---------|-----------|------|
| VB-01 ~ VB-04 | `tests/validation-banner.spec.js` | ✅ 已实现（VB-01 含倒计时 tick 断言） |
| VB-05 | — | ⬜ 待补充（跨越上线时刻自动切换） |
| OG-01 ~ OG-16 | — | ⬜ 待补充（建议新建 `tests/upload-operator-gate.spec.js`） |
| AC-01 ~ AC-04 | — | ⬜ 待补充 |
| TV-01 ~ TV-07 | — | ⬜ 待补充（需 mock origin + API fixture） |
| RD-01 ~ RD-03 | — | ⬜ 待补充 |

**建议 Playwright 辅助函数：**

```js
// mock 生产 origin
await page.addInitScript(() => {
  Object.defineProperty(window.location, 'origin', {
    get: () => 'https://app.prismax.ai',
  });
});

// mock 用户角色（需配合 app 实际 auth mock 机制）
// operator: userRole = 'operator'
// non-operator: userRole = 'user' / 'reviewer' 等
```

---

*文档更新时间：2026-06-22 | 前端：`c230da72` → `e0dab08e01`（app-prismax-rp，18 commits）| 后端：`eb3507c1`、`f9bd5767`（app-prismax-rp-backend）*
