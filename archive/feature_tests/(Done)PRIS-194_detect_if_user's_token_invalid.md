# Commit 分析：9a2cb6c — fixing invalid token

## 基本信息

| 字段 | 内容 |
|------|------|
| Commit Hash | `9a2cb6c7434c854db3846902390e26b73703ff6c` |
| 作者 | Chris |
| 日期 | 2026-05-14 |
| 仓库 | `app-prismax-rp`（前端） |
| 父提交 | `0028e26`（Merge PR #40 PRIS-202） |
| 改动规模 | 19 个文件，+422 / -91 行 |

---

## 问题背景

后端在 JWT / gateway token 过期或无效时，返回 `401` 及相应错误消息（如 `"invalid token"`、`"token expired"` 等）。

**改前行为：** 各页面将 token 失效当作普通 API 错误，只弹红色 error toast（直接显示 `invalid token`），用户依然停留在已登录 UI，前端状态与后端实际鉴权状态不一致。

**改后行为：** 统一检测 session 过期 → 清理本地会话数据 → 静默断开钱包 → 弹出友好提示引导用户重新登录。

---

## 整体架构

```
API 返回 invalid token / 401
    ↓
isSessionExpiredError() 检测
    ↓ 是
handleUserSessionExpired() / handleAdminSessionExpired()
    ├── clearLocalSessionData()      ← 清理 localStorage + React 状态
    ├── dispatch CustomEvent         ← 通知全局 UI 组件
    └── showNotification(error, 8s)  ← 用户友好提示

CustomEvent 监听者：
    ConnectWalletHeader  → disconnectWallet({ showSuccess: false })
    AdminPortal          → setAdminLogin(false) + setAdminAccessToken('')
```

---

## 改动详解

### 1. 新增 `src/utils/authErrors.js`（核心工具库）

全新文件，集中定义 token 失效相关常量与工具函数：

| 导出 | 说明 |
|------|------|
| `isSessionExpiredError(errorOrMessage)` | 匹配各类 token 失效文案，返回 `true/false` |
| `getApiErrorMessage(data, fallback)` | 从 `msg / message / error / detail` 中取错误信息 |
| `USER_SESSION_EXPIRED_MESSAGE` | `"Your session has expired. Please log in again."` |
| `ADMIN_SESSION_EXPIRED_MESSAGE` | `"Admin session expired. Please reconnect your wallet."` |
| `USER_SESSION_EXPIRED_EVENT` | 自定义事件名 `prismax:user-session-expired` |
| `ADMIN_SESSION_EXPIRED_EVENT` | 自定义事件名 `prismax:admin-session-expired` |

`isSessionExpiredError` 匹配的关键词：

```js
text.includes('invalid token')
|| text.includes('token expired')
|| text.includes('expired token')
|| text.includes('jwt expired')
|| text.includes('invalid jwt')
|| text === 'unauthorized'
|| text.includes('unauthorized access')
|| text.includes('not authenticated')
```

---

### 2. `src/context/SwapMainAppContext.js`（全局 Handler）

新增三个方法并注入到 Context，供所有子组件使用：

**`clearLocalSessionData()`**：从 `ConnectWalletHeader.disconnectWallet` 抽取，统一会话清理逻辑：
1. 读取并备份 `betaAccessToken`、`selectedChain`
2. `localStorage.clear()`
3. 恢复 `betaAccessToken`、`selectedChain`、`emailLogin=false`
4. 调用 `clearUserData()` 清空 React 用户状态

**`handleUserSessionExpired()`**：普通用户 session 过期处理：
1. 调用 `clearLocalSessionData()`
2. `dispatch('prismax:user-session-expired')`
3. 弹出 error toast，持续 8 秒

**`handleAdminSessionExpired()`**：Admin session 过期处理：
1. `localStorage.removeItem('prismax_admin_token')`
2. `dispatch('prismax:admin-session-expired')`
3. 弹出 error toast，持续 8 秒

---

### 3. `src/components/header/ConnectWalletHeader.js`

- `disconnectWallet` 改为 `useCallback`，新增 `{ showSuccess: boolean }` 参数
- 监听 `prismax:user-session-expired` 事件，触发 `disconnectWallet({ showSuccess: false })`，避免在 session 过期断开后再弹「断开成功」提示
- 断开逻辑统一改为调用 `clearLocalSessionData()`

---

### 4. `src/components/Admin/AdminPortal.js`

监听 `prismax:admin-session-expired` 事件，执行：

```js
setAdminLogin(false);
setAdminAccessToken('');
```

---

### 5. 各业务组件（统一拦截）

在 API 失败的 catch / else 分支中统一增加如下判断（约 15 个组件）：

```js
if (isSessionExpiredError(result.msg)) {
    handleUserSessionExpired?.();  // 或 handleAdminSessionExpired
    return;  // 不再走原有 error toast 逻辑
}
```

涉及组件汇总：

| 模块 | 文件 | 使用 Handler |
|------|------|------|
| Account | `OperatorSection.js` | `handleUserSessionExpired` |
| Account | `RegisterRobotModal.js` | `handleUserSessionExpired` |
| Account | `UnregisterRobotModal.js` | `handleUserSessionExpired` |
| Admin | `RobotTeleStatus.js` | `handleAdminSessionExpired` |
| Admin | `VLAAdminMachinesTable.js` | `handleAdminSessionExpired` |
| Admin | `VLAAdminOperatorApplications.js` | `handleAdminSessionExpired` |
| Admin | `VLAAdminQAReviewers.js` | `handleAdminSessionExpired` |
| Admin | `VLAAdminTasksTable.js` | `handleAdminSessionExpired` |
| Data | `DataHub.js` | `handleUserSessionExpired` |
| Data | `DataQAReview.js` | `handleUserSessionExpired` |
| Data | `Upload.js` | `handleUserSessionExpired` |
| Robotic Data | `RoboticData.js` | `handleUserSessionExpired` |
| Robotic Data | `RoboticDataAdmin.js` | `handleAdminSessionExpired` |
| Robotic Data | `RoboticDataWorkspace.js` | `handleUserSessionExpired`（10+ 处） |
| TeleOp | `TeleOpQueueBody.js` | `handleUserSessionExpired` |

> `RoboticDataWorkspace.js` 改动最多，在 fetch episodes、preview、direct/single/batch download、create/revoke API key、create API package 等场景均有拦截。部分使用 `useRef` 避免 stale closure 问题。

---

## 完整用户流程（改后）

**普通用户 session 过期：**

```
用户操作 → API 返回 401 "invalid token"
    → isSessionExpiredError() = true
    → handleUserSessionExpired()
        → clearLocalSessionData()（清 localStorage、React state）
        → dispatch 'prismax:user-session-expired'
        → toast: "Your session has expired. Please log in again."（8s）
    → ConnectWalletHeader 监听到事件
        → disconnectWallet({ showSuccess: false })
        → UI 回到未连接钱包状态，不弹「断开成功」
```

**Admin session 过期：**

```
Admin 操作 → API 返回 401
    → isSessionExpiredError() = true
    → handleAdminSessionExpired()
        → 清除 prismax_admin_token
        → dispatch 'prismax:admin-session-expired'
        → toast: "Admin session expired. Please reconnect your wallet."（8s）
    → AdminPortal 监听到事件
        → setAdminLogin(false) + setAdminAccessToken('')
        → UI 回到 Admin 登录状态
```

---

## QA 测试用例

### TC-01：普通用户 Token 过期（通用）

**前提：** 用户已登录，手动使 gateway token 失效（如修改 localStorage 中的 token）  
**操作：** 访问任意需要鉴权的页面功能（Data Hub、QA Review、Upload 等）  
**预期：**
- 显示 toast："Your session has expired. Please log in again."，持续约 8 秒
- 页面自动回到未连接钱包状态
- **不**显示 `"invalid token"` 原始错误
- **不**显示 "wallet disconnected successfully"
- `betaAccessToken`、`selectedChain` 在 localStorage 中仍存在

---

### TC-02：Admin Token 过期

**前提：** Admin 已登录，手动清除或篡改 `prismax_admin_token`  
**操作：** 在 Admin Portal 执行任意操作（查看 Machines、Operator Applications 等）  
**预期：**
- 显示 toast："Admin session expired. Please reconnect your wallet."，持续约 8 秒
- Admin Portal 退出登录状态（回到登录界面）
- 普通用户 session 不受影响

---

### TC-03：普通业务错误不触发登出

**前提：** 用户已正常登录  
**操作：** 触发非 token 相关的 API 错误（如网络超时、参数错误等）  
**预期：**
- 显示具体业务错误 toast
- 用户**不**被登出，页面状态保持

---

### TC-04：session 过期后断开不弹成功提示

**操作：** 触发 session 过期流程（TC-01）  
**预期：**
- 只显示过期提示 toast，**不**出现 "Your wallet has been successfully disconnected."

---

### TC-05：RoboticDataWorkspace 多场景覆盖

**前提：** 用户已进入 Robotic Data 页面，token 过期  
**操作（逐一验证）：**
1. 触发 episode 列表加载
2. 触发 episode 预览图/视频加载
3. 触发 Direct Download
4. 触发 Single Episode Download
5. 触发 Batch Download
6. 触发 Create API Key
7. 触发 Revoke API Key
8. 触发 Create API Package

**每项预期：** 均触发 session 过期登出流程，**不**显示 `invalid token` 原始消息

---

### TC-06：DataQAReview 场景

**前提：** token 过期  
**操作：** 加载 QA Review 任务 / 提交 QA Review  
**预期：** 触发 session 过期登出，**不**显示原始错误

---

### TC-07：联合回归（与 PRIS-202 同批）

**前提：** 正常登录，完成 QA Review  
**操作：** 点击「Don't show again」提交  
**预期：** 功能正常，与 token 过期逻辑无干扰

---

## 注意事项

- 此 commit **不涉及后端改动**，仅为前端鉴权体验统一
- `isSessionExpiredError` 做的是**字符串匹配**，依赖后端返回的 `msg` 字段内容，如后端返回格式变更需同步更新
- Admin 与普通用户走两套独立的过期处理路径，互不影响
