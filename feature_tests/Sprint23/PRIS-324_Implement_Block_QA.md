# PRIS-324 — Implement QA Reviewer Blocklist

> **Repos involved:** `app-prismax-rp` (frontend) · `app-prismax-rp-backend` (backend)
> **Merged:** 2026-08-17
> **Author:** Aparna Rangamani

---

## 功能概述

引入 QA 审核封禁（Blocklist）机制，允许管理员对存在异常审核行为的 QA 用户进行临时封禁，封禁期间用户无法提交 QA 审核，前端同步展示封禁状态提示，到期后自动或手动解封。

---

## 后端实现（`app-prismax-rp-backend`）

### 1. 数据库表：`data_qa_blocklist`

新建表用于记录所有封禁事件，每次封禁插入一条新行，支持重复封禁。

```sql
CREATE TABLE IF NOT EXISTS data_qa_blocklist (
    qa_blocklist_id       BIGSERIAL PRIMARY KEY,
    user_id               BIGINT NOT NULL REFERENCES users(userid),
    status                TEXT NOT NULL DEFAULT 'blocked',   -- 'blocked' | 'reinstated'
    blocked_reason        TEXT,
    blocked_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    blocked_by_admin_id   BIGINT,
    desired_reinstated_at TIMESTAMPTZ NOT NULL,              -- 预期解封时间
    reinstated_at         TIMESTAMPTZ,
    reinstated_by_admin_id BIGINT,
    reinstated_reason     TEXT,                              -- 'manual' | 'scheduled'
    qa_role_snapshot      TEXT                               -- 封禁时的 qa_role 快照
);

-- 同一用户同时只能有一条 active block
CREATE UNIQUE INDEX data_qa_blocklist_one_active_per_user
    ON data_qa_blocklist (user_id) WHERE status = 'blocked';

-- 定时任务查询用索引
CREATE INDEX data_qa_blocklist_due_idx
    ON data_qa_blocklist (desired_reinstated_at) WHERE status = 'blocked';
```

---

### 2. QA 资格校验加入封禁检查：`_require_qa_eligible_user`

新增 `should_check_blocklist=True` 参数。若用户在封禁名单中（`status = 'blocked'`），返回 `403 QA_BLOCKED`。

```python
def _require_qa_eligible_user(should_check_review_count=False, should_check_blocklist=True):
    ...
    if should_check_blocklist:
        blocked_row = conn.execute(sqlalchemy.text("""
            SELECT 1 FROM data_qa_blocklist
            WHERE user_id = :user_id AND status = 'blocked'
            LIMIT 1
        """), {"user_id": user["userid"]}).fetchone()
        if blocked_row:
            return None, None, (jsonify({
                "success": False,
                "code": "QA_BLOCKED",
                "msg": "QA review access is temporarily paused.",
            }), 403)
```

**精细控制拦截范围**——并非所有 QA 接口都拦截，封禁期间用户仍可"查看"但不能"提交审核"：

| 接口 | 封禁检查 | 说明 |
|------|----------|------|
| 提交 QA 审核相关接口 | ✅ 启用（默认） | 被拦截，返回 403 |
| `GET /data/qa/uploads` | ❌ 关闭 | 可正常浏览上传列表 |
| `GET /data/qa/uploads/{id}/episodes` | ❌ 关闭 | 可查看 episode |
| `GET /data/qa/episodes/{id}/joint-states` | ❌ 关闭 | 可查看关节数据 |
| `GET /data/qa/reviewable-uploads/previews` | ❌ 关闭 | 可预览 |
| `GET /data/qa/get-validator-access-data` | ❌ 关闭 | 可查看资格数据 |

---

### 3. 新增 API 端点

#### 管理员接口

**`GET /data/admin/qa-review/blocklist`** — 分页获取封禁名单

- 需要管理员 JWT
- 默认分页大小 20 条，按 `blocked_at DESC` 排序
- 联表 `users` 返回 email、wallet 等信息

**`POST /data/admin/qa-review/blocklist/add`** — 封禁用户

- 支持三种用户查找方式：`user_id` / `email` / `wallet`（需指定 chain）
- 默认封禁时长 30 天（`QA_BLOCKLIST_DEFAULT_DURATION_DAYS = 30`）
- 封禁时同步将 `users.qa_role` 置为 `NULL`，原值存入 `qa_role_snapshot`
- 同一用户已有 active block 则返回 `409`

**`POST /data/admin/qa-review/blocklist/reinstate`** — 手动解封（管理员）

```sql
UPDATE data_qa_blocklist
SET status                 = 'reinstated',
    reinstated_at          = NOW(),
    reinstated_by_admin_id = :admin_id,
    reinstated_reason      = 'manual'
WHERE qa_blocklist_id = :qa_blocklist_id
  AND status = 'blocked'
RETURNING qa_blocklist_id, user_id
```

- 通过 `qa_blocklist_id` 精确定位，仅更新 `status = 'blocked'` 的行
- 用 `RETURNING` 判断是否命中，未命中则返回 404

#### 内部 / 用户接口

**`POST /data/qa/blocklist/reinstate-due`** — 定时自动解封（Internal Token 鉴权）

```sql
UPDATE data_qa_blocklist
SET status            = 'reinstated',
    reinstated_at     = NOW(),
    reinstated_reason = 'scheduled'
WHERE status = 'blocked'
  AND desired_reinstated_at <= NOW()
RETURNING qa_blocklist_id, user_id
```

- 批量解封所有已到期记录，由外部调度器每 24 小时调用一次
- `reinstated_reason = 'scheduled'`，与手动解封可区分

**`GET /data/qa/blocklist/my-status`** — 用户查询自身封禁状态

- 返回 `blocked`（bool）、`blocked_at`、`desired_reinstated_at`
- 供前端决定是否展示封禁 Banner

---

### 4. 注意：解封后 `qa_role` 不会自动恢复

封禁时：`users.qa_role` → `NULL`，原值 → `qa_role_snapshot`

两条解封 SQL 均**只更新 `data_qa_blocklist` 表**，不写回 `users.qa_role`。
解封后用户虽不再被 `QA_BLOCKED` 拦截，但 `qa_role` 仍为 `NULL`，实质上仍无法通过 QA 资格校验。`qa_role_snapshot` 目前仅作审计用途。

---

### 5. Validator 轮换逻辑更新（`qa_helper.py`）

- **扩展轮换池**：之前只包含 `qa_role = 'qa'`，现扩展至 `qa_role IN ('qa', 'senior_qa')`。`senior_qa` 不是独立赛道，仅是同一池中的手动升级标签。
- **新增 `to_foldback` 逻辑**：本轮轮换后存活的 `senior_qa` 用户统一降回 `'qa'`（"每月重新赢取"），被移除的 `senior_qa` 与普通 `qa` 一样直接失去 QA 资格。
- **封禁用户排除晋升**：晋升候选池增加 `NOT EXISTS (SELECT 1 FROM data_qa_blocklist WHERE status = 'blocked')` 过滤，防止被封用户（`qa_role` 已被清空）在下轮被静默重新晋升。

---

## 前端实现（`app-prismax-rp`）

### 1. 管理员端：`VLAAdminQAReviewers.js`

新增 `QAReviewersBlocklist` 组件，追加在现有 QA 审核员列表页底部（可折叠）：

- **列表展示**：分页表格，字段包括用户 ID、email、wallet、封禁原因、封禁时间、预期解封时间
- **添加封禁**：`AddToBlocklistModal` 弹窗
  - 支持 `user_id` / `email` / `wallet` 三种查找方式（选 wallet 时额外选 chain）
  - 可填写封禁原因（可选），默认 30 天
  - 提交前弹出 `ConfirmModal` 二次确认：「Block {identifier} for 30 days?」
- **手动解封**：每行 Reinstate 按钮 → `ConfirmModal` 确认 → 调用后端接口 → 刷新当前页

---

### 2. 用户端：`DataHub.js`

#### 封禁状态拉取

登录后通过 `useEffect` 异步拉取 `/data/qa/blocklist/my-status`：

```javascript
setQaBlockStatus({
    blocked: Boolean(json.data.blocked),
    blockedAt: json.data.blocked_at || null,
    desiredReinstatedAt: json.data.desired_reinstated_at || null,
});
```

#### `QaBlockBanner` 警告横幅

被封禁时在 QA Review 页顶部展示琥珀色警告条：

> **Your QA review access is temporarily paused due to abnormal review activity.**
> It runs from {blockedAt} to {reinstatedAt} UTC, and only affects the QA review section — the rest of your account is unaffected.

**解封日期取整逻辑**：`ceilToNextUtcDayIfNeeded` 将 `desired_reinstated_at` 向上取整到下一个 UTC 自然日，原因是自动解封任务每 24 小时才运行一次，若显示原始时间戳会让用户误以为当天即可解封。

#### 导航与路由限制（封禁期间）

| 位置 | 行为 |
|------|------|
| `My Progress` 导航链接 | 置灰（`opacity: 0.45`），点击触发 warning 通知而非跳转 |
| `/data/review/progress` 路由 | `<Navigate to="/data/review" replace />` 直接重定向 |

---

### 3. 新增样式：`DataHub.module.css`

```css
/* 封禁 Banner */
.qaBlockBanner {
    border: 1px solid rgba(240, 160, 75, 0.35);
    background: rgba(240, 160, 75, 0.08);
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 13px;
}
.qaBlockBannerTitle { font-weight: 600; color: #f5c98a; }  /* 加粗金橙色 */
.qaBlockBannerBody  { color: #d9c9b3; }                     /* 浅暖色 */

/* 禁用的导航链接 */
.dataHubPageSubnavLinkDisabled { opacity: 0.45; cursor: default; }
```

---

## 整体数据流

```
管理员操作 (Admin UI)
  │
  ├─ POST /blocklist/add
  │     ├─ users.qa_role → NULL
  │     └─ data_qa_blocklist INSERT (status='blocked', qa_role_snapshot)
  │
  └─ POST /blocklist/reinstate
        └─ data_qa_blocklist UPDATE (status='reinstated', reinstated_reason='manual')

定时任务 (每 24h)
  └─ POST /blocklist/reinstate-due
        └─ data_qa_blocklist UPDATE (status='reinstated', reinstated_reason='scheduled')
             WHERE desired_reinstated_at <= NOW()

用户访问 QA 审核接口
  └─ _require_qa_eligible_user(should_check_blocklist=True)
        └─ SELECT 1 FROM data_qa_blocklist WHERE user_id=? AND status='blocked'
              ├─ 命中 → 403 QA_BLOCKED
              └─ 未命中 → 正常继续

用户前端 (DataHub)
  └─ GET /data/qa/blocklist/my-status
        ├─ blocked=false → 正常显示
        └─ blocked=true  → QaBlockBanner + My Progress 禁用 + /progress 路由重定向
```

---

## 补丁：Operator 开放 QA 权限（2026-08-18）

> **Commits**：`d5b2340`（前端） · `db453ed`（后端）  
> **性质**：针对 Block QA 功能的后续改善，移除对 Operator 角色的 QA 准入限制，并新增防自审校验

### 变更背景

PRIS-324 第一期（2026-08-17）上线时，原有逻辑保留了「Operator 不得访问 QA Review」的限制（`isOperatorBlockedFromQA`）。本次补丁将该限制完全移除，Operator 现在与普通用户享有相同的 QA 审核准入资格。

---

### 后端改动（`app.py`）

**① 移除 Operator QA 禁止拦截**

```python
# 原代码（已注释）
# if _normalize_user_role(user.get("user_role")) == 'operator':
#     return None, None, (jsonify({"success": False,
#         "msg": "Operators are not eligible for QA review."}), 403)
```

**② 新增防自审校验（`submit_upload_qa_review`）**

```python
# 查询时额外取出 upload 的 user_id
SELECT upload_id, status, user_id FROM data_uploads ...

# 提交审核时判断是否为自己的数据
upload_user_id = upload_row._mapping.get("user_id")
if upload_user_id == user["userid"]:
    return jsonify({
        "success": False,
        "msg": "You have uploaded this data. Please select a different upload to review."
    }), 403
```

由于 Operator 既可上传数据又可参与 QA 审核，故加入自审拦截，返回 HTTP 403。

---

### 前端改动（`DataHub.js`）

| 位置 | 原逻辑 | 新逻辑 |
|------|--------|--------|
| `isOperatorBlockedFromQA` 变量 | `isOperator && !hasQaRole` | 整行注释删除 |
| `canAccessQAReview` | `isLoggedIn && !isOperatorBlockedFromQA` | 简化为 `isLoggedIn` |
| QA Review 导航项样式 | Operator 时返回 `navItemDisabled` | 注释删除，正常显示 |
| `handleQAReviewRestrictedClick` | Operator 时弹出专属提示 | 相关分支注释删除 |
| `ReviewWorkspace` prop | 传入 `isOperator` | prop 删除 |
| `ReviewWorkspace` noAccess 文案 | Operator 时显示专属提示 | 删除，统一显示通用提示 |

---

### Operator + Blocklist 交互逻辑

Operator 被封禁后尝试提交审核，执行顺序如下：

```
submit_upload_qa_review 被调用
  ↓
_require_qa_eligible_user(should_check_review_count=True, should_check_blocklist=True 【默认】)
  ↓
① Blocklist 检查（最先执行）：
   SELECT 1 FROM data_qa_blocklist WHERE user_id=? AND status='blocked'
  ↓ 命中
  ↓
返回 403 QA_BLOCKED —— 在此终止，角色判断、自审检查均不执行
```

**结论**：Blocklist 检查早于所有角色判断，Operator 被封禁后**无法提交审核**，行为与普通 QA 用户被封禁完全一致。

---

### 完整测试用例

#### 一、Blocklist 核心功能（第一期）

| 用例 ID | 场景 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---------|------|----------|----------|----------|--------|
| BL-01 | 管理员按 user_id 封禁用户 | 管理员已登录，目标用户存在且未被封禁 | 打开 Admin > QA Reviewers，展开 Blocklist，点击「Add to blocklist」，选 User ID，输入有效 user_id，填写原因，点击 Add，二次确认 | 操作成功，目标用户出现在 Blocklist 表格第一行，封禁时间正确，预期解封时间为封禁时间 +30 天；`users.qa_role` 被置为 NULL | P0 |
| BL-02 | 管理员按 email 封禁用户 | 同 BL-01 | 查找方式选 Email，输入有效 email | 同 BL-01 | P0 |
| BL-03 | 管理员按 wallet 封禁用户 | 目标用户有绑定 wallet | 查找方式选 Wallet，选正确 chain，输入 wallet 地址 | 同 BL-01 | P1 |
| BL-04 | 封禁不存在的用户 | — | 输入不存在的 user_id/email/wallet | 提示「User not found」，无记录插入 | P1 |
| BL-05 | 重复封禁已被封禁的用户 | 目标用户已在 Blocklist | 再次对同一用户执行封禁 | 返回 409，提示「User is already blocked」 | P1 |
| BL-06 | 被封禁用户尝试提交 QA 审核 | 普通 QA 用户已被封禁 | 登录被封禁账号，进入 QA Review，选取 episode 提交审核 | 接口返回 403 `QA_BLOCKED`，前端展示错误提示 | P0 |
| BL-07 | 被封禁用户前端封禁 Banner 显示 | 同 BL-06 | 登录被封禁账号，访问 `/data/review` | 页面顶部出现琥珀色 Banner，显示封禁开始日期和预期解封日期（向上取整到下一 UTC 自然日） | P0 |
| BL-08 | 被封禁用户 My Progress 禁用 | 同 BL-06 | 查看 QA Review 导航栏 | `My Progress` 链接置灰（opacity 0.45），点击弹出 warning 通知，不跳转 | P0 |
| BL-09 | 被封禁用户直接访问 `/data/review/progress` | 同 BL-06 | 浏览器直接输入 URL `/data/review/progress` | 自动重定向至 `/data/review` | P0 |
| BL-10 | 被封禁期间仍可浏览 QA 上传列表 | 同 BL-06 | 访问 QA Review 主页 | 可正常查看 upload 列表，可预览 episode，但无法提交审核 | P1 |
| BL-11 | 管理员手动解封 | 目标用户在 Blocklist | 点击对应行的 Reinstate 按钮，二次确认 | 该行从 Blocklist 消失，`reinstated_reason = 'manual'`，`reinstated_at` 有值 | P0 |
| BL-12 | 定时任务自动解封 | 存在 `desired_reinstated_at ≤ NOW()` 的封禁记录 | 调用 `POST /data/qa/blocklist/reinstate-due`（或等待定时器触发） | 到期记录状态变为 `reinstated`，`reinstated_reason = 'scheduled'` | P1 |
| BL-13 | 解封后用户 QA 状态 | 用户刚被解封 | 以解封用户身份登录，访问 QA Review | Banner 消失，`My Progress` 恢复正常；**注意：`qa_role` 仍为 NULL，用户需管理员重新授予 QA 角色才可提交审核** | P1 |
| BL-14 | Blocklist 分页展示 | Blocklist 中记录超过 20 条 | 进入管理员 Blocklist 页 | 正确分页，每页 20 条，翻页正常 | P2 |
| BL-15 | 封禁无 `qa_role` 的普通用户 | 目标用户 `qa_role = NULL` | 封禁操作 | `qa_role_snapshot` 存为 NULL，封禁正常插入 | P2 |

#### 二、Operator QA 权限补丁（2026-08-18）

| 用例 ID | 场景 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|---------|------|----------|----------|----------|--------|
| OPR-01 | Operator 访问 QA Review 页面 | Operator 账号已登录，未被封禁 | 访问 `/data/review` | 页面正常加载，QA Review 导航链接可点击，无「not available to Operators」提示 | P0 |
| OPR-02 | Operator 审核他人上传的 episode | Operator 账号已登录，未被封禁 | 选取他人上传的 episode，完成审核并提交 | 审核提交成功，返回 200 | P0 |
| OPR-03 | Operator 尝试审核自己上传的 episode | Operator 账号已登录，名下有上传数据 | 选取自己上传的 episode，尝试提交审核 | 接口返回 403，提示「You have uploaded this data. Please select a different upload to review.」 | P0 |
| OPR-04 | Operator 被加入 Blocklist 后尝试提交审核 | Operator 账号已被管理员封禁 | 以被封禁 Operator 身份登录，进入 QA Review，尝试提交审核 | 接口返回 403 `QA_BLOCKED`（Blocklist 检查早于角色判断和自审检查）；前端展示封禁 Banner，`My Progress` 置灰，`/progress` 路由重定向 | P1 |
| OPR-05 | Operator 被封禁后仍可浏览 QA 列表 | 同 OPR-04 | 访问 QA Review 主页，浏览上传列表 | 可正常查看，无法提交 | P1 |
| OPR-06 | 普通 QA 用户流程不受影响 | 普通 QA 用户账号，未被封禁 | 正常执行 QA 审核全流程 | 提交审核、查看进度等功能均正常，无异常 | P1 |
| OPR-07 | 非登录用户访问 `/data/review` | 未登录 | 直接访问 QA Review 页 | 提示「Please log in」，行为与改动前一致 | P2 |
| OPR-08 | Operator 重复审核同一 upload（他人数据） | Operator 已对某 upload 提交过审核 | 再次选取同一 upload 提交 | 按原有次数/状态限制返回对应错误，与普通 QA 用户行为一致 | P2 |
