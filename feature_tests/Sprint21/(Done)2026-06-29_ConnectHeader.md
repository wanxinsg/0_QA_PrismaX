# app-prismax-rp — 2026-06-29 Commit 分析与测试策略

**涉及仓库：** `app-prismax-rp`（前端）  
**分析范围：** `0f65640` → `5f9665e`（5 commits，2026-06-24 ~ 2026-06-26）；增量 `d1f0986` + `1960513`（2026-06-29，见 §六）  
**提交作者：** lanmanc、Aparna Rangamani  

| 文件 | 净变动 |
|------|--------|
| `src/components/header/ConnectModal.js` | +207 / -85 |
| `src/components/header/ConnectModal.module.css` | +97 / 0 |
| `src/components/header/ConnectWalletHeader.js` | +80 / -18 |
| `src/components/Data/DataQAReview/DataQAReview.js` | +10 / -14 |
| `src/components/Data/DataQAReview/Modals/LeaveQAReviewModalV2.js` | -1（注释清理） |
| `public/email-verify-qa-promo-banner.jpeg` | 新增（约 512 KB） |

---

## 一、Commit 清单

| # | Hash | 日期 | 作者 | 说明 |
|---|------|------|------|------|
| 1 | `3d3ce9e` | 2026-06-24 | Aparna | promo-email: add verify qa banner image |
| 2 | `100f07d` | 2026-06-26 | Aparna | Merge PR #57 (PRIS-243-leave-qa-modal) |
| 3 | `215b724` | 2026-06-26 | Aparna | PRIS-243: make expert qa has started check consistent with other users; minor fix |
| 4 | `b6f14c0` | 2026-06-26 | Aparna | Merge PR #58 (PRIS-243-leave-qa-modal) |
| 5 | `5f9665e` | 2026-06-25 | lanmanc | changed login so that email can login with wallet |

---

## 二、改动详细分析

### 2.1 Email + Wallet 联合登录（`5f9665e`）

#### 一句话主线

用户以 Email 登录后，可在 Connect Modal 内绑定钱包；已绑定时展示「Linked wallet」卡片并支持解绑。Header 展示逻辑统一为**有 email 优先展示 email**。

---

#### 2.1.1 `ConnectWalletHeader.js` — Header 展示逻辑

**改前：** `walletAddress === CONNECT_DEFAULT_TEXT` 才显示 email 图标，即「没有钱包时才显示 email」。  
**改后：** 只要 `userEmail` 存在，就直接显示 email 图标和邮箱地址；如果同时连了钱包，也以 email 为主展示。

```js
// 改后：email 优先
{userEmail
    ? <img src={email_svg} alt="Email" />
    : walletAddress === CONNECT_DEFAULT_TEXT ? "" : <钱包图标>
}
{userEmail
    ? shortenAddress(userEmail)    // Email 登录
    : walletAddress                // 钱包登录
}
```

**新增 `handleModalWalletUnlink`：**

| 步骤 | 说明 |
|------|------|
| 读取 localStorage | `gatewayToken`、`userEmail`、`walletAddress`、`selectedChain` |
| 调用后端 | `POST /api/disconnect-wallet-from-email`（Body: `{email, wallet_address, chain}`） |
| 成功 | 清空钱包相关 state & localStorage（`walletAddress`、`lastConnectedWallet`、`lastConnectedChain`、`selectedChain`），重置 chain 为 `solana`，调用 `onWalletConnected(null, 0, 0, 0)` |
| 失败 | 抛出 Error，由 ConnectModal 捕获显示 toast |

`ConnectModal` 新增两个 prop：`onWalletUnlink`、`showNotification`，由 `ConnectWalletHeader` 注入。

---

#### 2.1.2 `ConnectModal.js` — 三种登录状态的 UI 表现

| 登录状态 | 主账号展示 | 额外区域 |
|----------|-----------|---------|
| 仅 Email | email 地址 | 「Connect Wallet」折叠区（可连钱包） |
| Email + 钱包已绑 | email 地址 | 「Linked wallet」卡片（地址 + 链 + 解绑按钮） |
| 仅钱包 | 钱包地址 | 复制按钮（原有行为） |

**关键逻辑变量：**
- `hasEmail = Boolean(userEmail)` — 以 email 是否存在为首要判断
- `primaryIsEmail = hasEmail` — 决定主账号展示 email 还是钱包
- `shouldShowConnectedWalletSection = hasEmail && !isWalletConnected` — 是否显示「Connect Wallet」区

**Disconnect 优先级调整：**
- 改前：有钱包连接时先断钱包
- 改后：有 email 时优先执行 `onEmailDisconnect`，否则才执行 `onWalletDisconnect`

**Unlink Wallet 交互：**
- 带 `TooltipBottom` 组件，hover 时提示「Unlink Wallet」
- 图标随 hover 状态切换：`disconnect-orange-camel.svg` → `disconnect-orange-topaz.svg`
- 成功 toast：`Your wallet has been successfully unlinked from your email.`
- 失败 toast：`Failed to unlink your wallet. Please try again.`（或后端返回的错误信息）

---

### 2.2 PRIS-243 Leave QA Review 守卫修复（`215b724`）

#### `hasStartedCurrentBatch` 逻辑统一（`DataQAReview.js`）

**问题：** Expert QA 与普通用户的「是否已开始 QA」判断逻辑不一致，Expert 只看提交记录，导致 Expert 刚填写 rubric 但未提交时，离开页面不会触发拦截弹窗。

**改前（两套逻辑）：**

```js
// Expert QA
if (isExpertQa) return Object.keys(locallySubmittedEpisodeIds).length > 0;
// 普通用户：检查当前 batch 内 episode 是否有 rubric 填写
return effectiveSampledEpisodeIds.some(episodeId => ...);
```

**改后（统一逻辑，移除 isExpertQa 分支）：**

```js
const hasStartedCurrentBatch = useMemo(() => {
    return Object.values(reviewState || {}).some((episodeData) => {
        const rubric = episodeData?.rubric || {};
        return MANUAL_QA_REQUIREMENTS.some((item) => {
            const value = rubric[item.key];
            return value !== '' && value !== null && value !== undefined;
        });
    });
}, [reviewState]);
```

遍历**整个 `reviewState`**（不限于当前 batch），只要任意 episode 的 rubric 有非空值，就视为「已开始 QA」，触发 Leave QA 拦截弹窗。

> **注意：** 依赖项从 `[effectiveSampledEpisodeIds, isExpertQa, locallySubmittedEpisodeIds, reviewState]` 缩减为 `[reviewState]`，重渲染频率降低。

#### `LeaveQAReviewModalV2.js`

删除一行注释掉的旧文案，无功能变化。

---

### 2.3 营销资源（`3d3ce9e`）

新增 `public/email-verify-qa-promo-banner.jpeg`（约 512 KB），用于 Email 验证/QA 推广邮件 banner，无任何代码逻辑变更。

---

## 三、测试分析

### 3.1 风险矩阵

| 模块 | 变更类型 | 风险等级 | 影响范围 |
|------|----------|----------|---------|
| Email + Wallet 绑定/解绑 | 新功能 | **高** | 全量用户登录流程、localStorage 状态、后端 API |
| Header 展示逻辑变更 | 行为变更 | **高** | 所有已登录用户的 Header 显示 |
| Disconnect 优先级变更 | 行为变更 | **中** | Email 登录用户点击 Disconnect 的行为 |
| hasStartedCurrentBatch 逻辑统一 | Bug 修复 | **中** | Expert QA 离开页面的拦截判断 |
| 营销图片资源 | 静态资源 | **低** | 仅影响邮件 banner 展示 |

### 3.2 核心测试场景梳理

#### A. Email 登录状态（4 个核心路径）

```
[A1] Email 登录 → ConnectModal 展示「Connect Wallet」区
[A2] Email 登录 → 连接钱包 → ConnectModal 展示「Linked wallet」卡片
[A3] Email + Wallet → Unlink Wallet → 恢复「Connect Wallet」状态
[A4] Email + Wallet → Disconnect → 登出 Email（非断钱包）
```

#### B. 纯钱包登录（回归）

```
[B1] 钱包登录 → Header 正确显示钱包图标 + 钱包地址
[B2] 钱包登录 → ConnectModal 无「Connect Wallet」、无「Linked wallet」
[B3] 钱包登录 → Disconnect → 钱包断开
```

#### C. Leave QA Guard（Expert QA 修复验证）

```
[C1] Expert QA：填写 rubric 未提交 → 离开 → 弹出 Leave QA 弹窗
[C2] Expert QA：未填写任何 rubric → 离开 → 不弹窗
[C3] 普通 QA：填写 rubric 未提交 → 离开 → 弹出弹窗（回归）
```

### 3.3 后端接口依赖

| 接口 | 方法 | 触发场景 |
|------|------|---------|
| `/api/disconnect-wallet-from-email` | POST | Unlink Wallet 按钮 |

请求体：
```json
{
  "email": "user@example.com",
  "wallet_address": "0x...",
  "chain": "solana"
}
```

返回字段：`{ "success": true/false, "msg": "..." }`

---

## 四、E2E 测试用例

| 用例编号 | 模块 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|----------|------|----------|----------|---------|--------|
| T1-01 | Email 登录 + 连接钱包 | Email OTP 登录，未连钱包 | 检查 Header 展示 | 显示 Email 图标 + 邮箱地址缩写，无钱包图标 | P0 |
| T1-02 | Email 登录 + 连接钱包 | Email OTP 登录，未连钱包 | 点击 Header 打开 ConnectModal | 主账号区显示邮箱地址；底部出现「Connect Wallet」折叠按钮；Network / Wallet 列表**未**自动展开 | P0 |
| T1-03 | Email 登录 + 连接钱包 | ConnectModal 已打开 | 点击「Connect Wallet」按钮 | 折叠展开，显示 Network 选择器（Solana / Base）和 Wallet 列表 | P0 |
| T1-04 | Email 登录 + 连接钱包 | 折叠区已展开 | 选择 Solana 链，点击 Phantom | Phantom 钱包授权弹窗打开 | P0 |
| T1-05 | Email 登录 + 连接钱包 | Phantom 授权弹窗打开 | 在 Phantom 中授权连接 | 「Connect Wallet」区消失，出现「Linked wallet」卡片 | P0 |
| T1-06 | Email 登录 + 连接钱包 | Linked wallet 卡片已出现 | 检查「Linked wallet」卡片内容 | 显示：钱包图标、"Linked wallet" 标签、钱包地址缩写、链信息（`Phantom · Solana`）、Unlink 按钮 | P0 |
| T1-07 | Email 登录 + 连接钱包 | Email + 钱包绑定状态 | 关闭 Modal | Header 仍显示 Email 图标 + 邮箱地址，不变为钱包 | P0 |
| T2-01 | Unlink Wallet（成功） | Email 已登录且已绑定钱包，Modal 已打开 | 确认「Linked wallet」卡片可见 | 卡片正常显示，Unlink 按钮（橙色骆驼图标）可点 | P0 |
| T2-02 | Unlink Wallet（成功） | Linked wallet 卡片可见 | Hover Unlink 按钮 | Tooltip 显示「Unlink Wallet」；图标切换为橙色 Topaz 样式 | P1 |
| T2-03 | Unlink Wallet（成功） | Linked wallet 卡片可见 | 点击 Unlink 按钮 | 按钮进入 disabled 状态（`isBusy = true`），不可重复点击 | P0 |
| T2-04 | Unlink Wallet（成功） | Unlink 请求发出 | 等待接口响应 | `POST /api/disconnect-wallet-from-email` 被调用，参数包含 email、wallet_address、chain | P0 |
| T2-05 | Unlink Wallet（成功） | 接口返回成功 | 检查 Toast 提示 | 显示：`Your wallet has been successfully unlinked from your email.` | P0 |
| T2-06 | Unlink Wallet（成功） | 接口返回成功 | 检查 Modal 状态 | 「Linked wallet」卡片消失，重新出现「Connect Wallet」折叠区 | P0 |
| T2-07 | Unlink Wallet（成功） | 接口返回成功 | 检查 localStorage | `walletAddress`、`lastConnectedWallet`、`lastConnectedChain`、`selectedChain` 均被清除 | P0 |
| T2-08 | Unlink Wallet（成功） | 解绑完成 | 关闭 Modal，检查 Header | Header 仍显示 Email 图标 + 邮箱地址 | P0 |
| T3-01 | Unlink Wallet（失败） | Mock 后端返回 `{ success: false, msg: "Custom error message" }` | 点击 Unlink 按钮 | 按钮进入 disabled 状态 | P0 |
| T3-02 | Unlink Wallet（失败） | 接口返回失败 | 检查 Toast 提示 | 显示后端返回的 `msg` 内容（`Custom error message`） | P0 |
| T3-03 | Unlink Wallet（失败） | 接口返回失败 | 检查 Modal 状态 | 「Linked wallet」卡片保持不变，未被清除 | P0 |
| T3-04 | Unlink Wallet（失败） | 接口返回失败 | 检查 localStorage | 钱包相关数据未被清除 | P0 |
| T3-05 | Unlink Wallet（失败） | 失败处理完成 | 再次检查 Unlink 按钮 | `isBusy` 重置为 false，按钮恢复可点 | P0 |
| T4-01 | Disconnect 优先级 | Email 已登录（有 `userEmail`），ConnectModal 已打开 | 确认主账号显示 email | ConnectModal 主账号区显示邮箱地址 | P0 |
| T4-02 | Disconnect 优先级 | Email 已登录 | 点击「Disconnect」按钮 | `onEmailDisconnect()` 被调用，而非 `onWalletDisconnect()` | P0 |
| T4-03 | Disconnect 优先级 | Disconnect 完成 | 检查登录状态 | email token 清除，Modal 关闭，Header 变为未登录状态 | P0 |
| T4-04 | Disconnect 优先级 | Email + 钱包绑定状态执行 Disconnect | 检查钱包状态 | 断开后钱包连接状态同步清除 | P1 |
| T5-01 | 纯钱包登录回归 | 未使用 Email，直接连接 Phantom | 检查 Header 展示 | 显示钱包图标 + 钱包地址缩写，**不**显示 Email 图标 | P0 |
| T5-02 | 纯钱包登录回归 | 纯钱包登录状态 | 打开 ConnectModal | 主账号区显示钱包地址，显示「复制地址」按钮 | P0 |
| T5-03 | 纯钱包登录回归 | ConnectModal 已打开 | 确认无「Linked wallet」卡片 | 「Linked wallet」卡片不出现 | P0 |
| T5-04 | 纯钱包登录回归 | ConnectModal 已打开 | 确认无「Connect Wallet」折叠区 | `shouldShowConnectedWalletSection = false`，折叠区不出现 | P0 |
| T5-05 | 纯钱包登录回归 | ConnectModal 已打开 | 点击「Disconnect」 | `onWalletDisconnect()` 被调用，Header 变为未登录状态 | P0 |
| T6-01 | Expert QA Leave Guard | Expert QA 角色，进入 QA Review 页 | 不填写任何 rubric，点击导航离开 | **不弹出** Leave QA Review 弹窗，直接离开 | P0 |
| T6-02 | Expert QA Leave Guard | Expert QA 角色，返回 QA Review | 填写至少一个 rubric 字段（任意非空值），不提交，点击导航离开 | **弹出** Leave QA Review 弹窗 | P0 |
| T6-03 | Expert QA Leave Guard | Leave QA 弹窗已出现 | 点击「Stay」 | 弹窗关闭，留在 QA Review 页，已填写内容保留 | P0 |
| T6-04 | Expert QA Leave Guard | Leave QA 弹窗已出现 | 点击「Leave」 | 正常离开页面 | P0 |
| T6-05 | Expert QA Leave Guard | 离开后在同会话内返回 QA Review | 检查 rubric 恢复状态 | 已填写的 rubric 内容从本地恢复 | P1 |
| T7-01 | 普通 QA Leave Guard（回归） | 普通 QA 角色，进入 QA Review 页 | 不填写任何 rubric，导航离开 | **不弹出**弹窗 | P0 |
| T7-02 | 普通 QA Leave Guard（回归） | 普通 QA 角色 | 填写任意 rubric 字段后导航离开 | **弹出** Leave QA Review 弹窗 | P0 |
| T7-03 | 普通 QA Leave Guard（回归） | Leave QA 弹窗已出现 | 检查弹窗内容 | 显示「Your answers will be saved locally.」文案 | P1 |
| T8-01 | 多钱包类型（Phantom/Solana） | Email 已登录 | 连接 Phantom（Solana）→ 检查 Linked wallet 卡片 → 执行 Unlink | 卡片显示 Phantom 图标 + Solana 链信息；Unlink 请求中 `chain: "solana"`；解绑后状态完全清除 | P1 |
| T8-02 | 多钱包类型（MetaMask/Base） | Email 已登录 | 连接 MetaMask（Base）→ 检查 Linked wallet 卡片 → 执行 Unlink | 卡片显示 MetaMask 图标 + Base 链信息；Unlink 请求中 `chain: "base"`；解绑后状态完全清除 | P1 |
| T8-03 | 多钱包类型（OKX/Solana） | Email 已登录 | 连接 OKX（Solana）→ 检查卡片 → 执行 Unlink | OKX 图标正确；解绑流程正常 | P2 |
| T8-04 | 多钱包类型（Coinbase/Base） | Email 已登录 | 连接 Coinbase（Base）→ 检查卡片 → 执行 Unlink | Coinbase 图标正确；解绑流程正常 | P2 |
| T9-01 | 异常/边界 | Email 登录 + 钱包已绑定 | 刷新页面后重新打开 Modal | 「Linked wallet」卡片正常恢复显示 | P1 |
| T9-02 | 异常/边界 | localStorage 中无 `gatewayToken` | 点击 Unlink 按钮 | Toast 提示 `Missing email session or linked wallet information.`，不调用后端 | P1 |
| T9-03 | 异常/边界 | localStorage 中无 `walletAddress` | 点击 Unlink 按钮 | Toast 提示 `Missing email session or linked wallet information.`，不调用后端 | P1 |
| T9-04 | 异常/边界 | 网络超时，Unlink 接口无响应 | 点击 Unlink 按钮，等待超时 | 按钮保持 disabled；超时后显示失败 toast，按钮恢复可点 | P1 |
| T9-05 | 异常/边界 | Linked wallet 卡片可见 | 快速连续点击 Unlink 按钮 | 第一次点击后按钮即 disabled，不重复发送请求 | P1 |
| T9-06 | 异常/边界 | 未传入 `onWalletUnlink` prop | 检查 Unlink 按钮状态 | 按钮 disabled，不报错 | P2 |

---

## 五、回归测试范围

| 模块 | 回归项 |
|------|--------|
| 登录入口 | Email OTP 登录、Google 登录、Apple 登录 |
| 钱包连接 | Phantom / MetaMask / OKX / Coinbase 各链连接 |
| ConnectModal | 已有的 Email 验证码流程、reCAPTCHA 弹窗 |
| Header | 钱包地址展示、链信息展示、复制地址 |
| QA Review | 普通 QA 的 Leave Guard、已提交 episode 计数、rubric 状态恢复 |
| localStorage | 登录/登出后 `gatewayToken`、`userEmail`、`walletAddress` 的写入与清除 |
| Galxe 归因 | URL 参数透传、登出重定向（见 §六） |
| 会员支付 | UpgradeMembershipModal USD / USDC / USDT 路径（见 §六） |
| ConnectModal 打开模式 | Header 手动打开 vs 支付流程程序化打开（见 §六） |

---

## 六、6/29 增量分析（`d1f0986` + `1960513`）

**增量范围：** `5f9665e` 之后两个 commit（2026-06-29，lanmanc）  
**关联 commit：**

| Hash | 说明 | 改动文件 |
|------|------|----------|
| `d1f0986` | fixing galxe bug | `ConnectWalletHeader.js`、`AuthContext.js`、`index.js` |
| `1960513` | email paid for usdc, connect wallet modal auto pops | `UpgradeMembershipModal.js`、`ConnectModal.js`、`ConnectWalletHeader.js`、`SwapMainAppContext.js` |

---

### 6.1 改动摘要

#### 6.1.1 Galxe 归因修复（`d1f0986`）

| 改前 | 改后 |
|------|------|
| `index.js` 启动时将 `source=galxe` 写入 localStorage | 删除 localStorage 持久化 |
| 注册时从 `localStorage.getItem('acquisitionSource')` 读取 | 注册时从 URL `urlParams.get('source')` 实时读取 |
| 登出后重定向至 `/` | Galxe quest URL 下登出重定向至 `/?source=galxe&campaign=signup_quest` |
| `handleLogoutWithEmail` 同步调用 `logout()` | 改为 `async/await logout()` |

#### 6.1.2 Email + 加密货币支付（`1960513`）

| 能力 | 实现 |
|------|------|
| 未连钱包时 USDC/USDT 支付 | `UpgradeMembershipModal` 调用 `requestConnectWalletModal()`，不再弹 error toast |
| 跨组件触发 ConnectModal | `SwapMainAppContext` 计数器 `connectWalletModalRequest`（同 `transactionTrigger` 模式） |
| 自动展开钱包列表 | `ConnectModal` 新增 prop `openWalletListOnOpen` |
| 文案 | 「Connect a wallet」→「Connect Wallet」 |

**ConnectModal 双模式打开：**

| 触发方式 | `openWalletListOnOpen` | 钱包列表状态 |
|----------|------------------------|--------------|
| Header 点击 Login / Email | `false` | 默认折叠 |
| UpgradeMembershipModal「Connect Wallet」 | `true` | 自动展开 |

---

### 6.2 风险矩阵（增量）

| 模块 | 变更类型 | 风险等级 | 影响范围 |
|------|----------|----------|---------|
| Galxe URL 归因 / 登出重定向 | Bug 修复 + 策略变更 | **高** | Galxe quest 引流用户注册与复访 |
| UpgradeMembershipModal 加密货币支付 | 新 UX | **高** | Email 用户会员升级流程 |
| ConnectModal 双模式打开 | 行为变更 | **中** | 所有 ConnectModal 入口 |
| ConnectModal 文案 | UI 变更 | **低** | 自动化 selector 需同步 |

---

### 6.3 后端接口依赖（增量）

| 接口 | 方法 | 触发场景 |
|------|------|---------|
| `GET /api/get-users?...&source=galxe` | GET | Galxe 来源钱包/Email 注册 |
| `POST /logout` | POST | Email 登出（含 Galxe 重定向） |
| `POST /api/create-stripe-checkout-session` | POST | USD 会员支付 |
| 链上支付（`transactionTrigger`） | — | USDC/USDT 会员支付 |

---

### 6.4 已有用例修订说明

§四 中以下用例已在本次文档更新中同步文案与断言（`1960513` 影响）：

- **T1-02**：补充「Network / Wallet 列表未自动展开」
- **T1-03 / T1-05 / T2-06 / T5-04**：「Connect a wallet」→「Connect Wallet」

以下用例需**新增断言**（Galxe，`d1f0986` 影响）：

| 原用例 | 补充 |
|--------|------|
| **T4-03** | 普通 URL 下行为不变；Galxe URL 见 **T4-05** |

---

### 6.5 新增 E2E 用例

#### T10 — Galxe 归因（`d1f0986`）

| 用例编号 | 模块 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|----------|------|----------|----------|---------|--------|
| T10-01 | Galxe 归因 | 访问 `/?source=galxe&campaign=signup_quest`，未登录 | 连接钱包完成注册 | `GET /api/get-users` 请求含 `source=galxe` | P0 |
| T10-02 | Galxe 归因 | 同上 URL，未登录 | Email OTP 登录完成注册 | 后端 `acquisition_source='galxe'` | P0 |
| T10-03 | Galxe 归因 | Galxe URL 进入后站内跳转（URL 参数丢失） | 再连接钱包 | **无法**带上 `source=galxe`（已知 trade-off，需产品确认） | P1 |
| T10-04 | Galxe 登出 | 当前 URL 含 Galxe 参数，Email 已登录 | 点击 Disconnect / Logout | 重定向至 `/?source=galxe&campaign=signup_quest` | P0 |
| T10-05 | Galxe 登出 | 普通 URL（无 Galxe 参数），Email 已登录 | 点击 Logout | 重定向至 `/` | P0 |
| T10-06 | Galxe + Referral | `?source=galxe&ref=ABC123&campaign=signup_quest` | 钱包连接注册 | 同时透传 `referrers_referral_code` 与 `source=galxe` | P1 |
| T10-07 | Galxe localStorage | 任意路径访问 | 检查 localStorage | **不再**写入 `acquisitionSource` | P1 |

#### T11 — Email + 加密货币会员支付（`1960513`）

| 用例编号 | 模块 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|----------|------|----------|----------|---------|--------|
| T11-01 | 会员支付 | Email 登录，未连钱包 | 打开 UpgradeMembershipModal，选 USDC | 支付按钮文案为「Connect Wallet」 | P0 |
| T11-02 | 会员支付 | 同上，选 USDC | 点击「Connect Wallet」 | ConnectModal 自动弹出，钱包列表已展开 | P0 |
| T11-03 | 会员支付 | T11-02 Modal 已打开 | 不连钱包，关闭 Modal | UpgradeMembershipModal 仍在；不显示 error toast | P0 |
| T11-04 | 会员支付 | T11-03 后 | 再次点击「Connect Wallet」 | Modal 再次弹出且列表仍展开 | P0 |
| T11-05 | 会员支付 | Email 登录，Modal 内连上 Phantom | 关闭 Modal，再点支付 | 触发链上支付（`transactionTrigger++`），不再弹 Connect Modal | P0 |
| T11-06 | 会员支付 | Email 登录，未连钱包 | 选 USD，点支付 | 走 Stripe checkout，不弹 Connect Modal | P0 |
| T11-07 | 会员支付 | Email 登录，未连钱包，链支持 USDT | 选 USDT，点支付 | 行为与 USDC 一致：自动弹 Modal + 展开列表 | P1 |
| T11-08 | 会员支付 | Email + 已绑钱包 | 选 USDC，点支付 | 直接进入链上支付，按钮非「Connect Wallet」 | P0 |

#### T12 — ConnectModal 打开模式（`1960513`）

| 用例编号 | 模块 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|----------|------|----------|----------|---------|--------|
| T12-01 | Modal 打开模式 | Email 登录，未连钱包 | Header 点击 Login / Email 图标 | Modal 打开，钱包列表折叠 | P0 |
| T12-02 | Modal 打开模式 | Email 登录，未连钱包 | UpgradeMembershipModal 点「Connect Wallet」 | Modal 打开，钱包列表展开 | P0 |
| T12-03 | Modal 打开模式 | 刚执行 T12-02 并关闭 Modal | Header 手动打开 ConnectModal | 钱包列表折叠（`openWalletListOnConnectModalOpen` 已 reset） | P0 |

#### T4-05 — Disconnect 补充（`d1f0986`，从 T4-03 拆分）

| 用例编号 | 模块 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
|----------|------|----------|----------|---------|--------|
| T4-05 | Disconnect + Galxe | URL 含 `source=galxe&campaign=signup_quest`，Email 已登录 | 点击 Disconnect | email token 清除；页面重定向至 `/?source=galxe&campaign=signup_quest` | P0 |

---

### 6.6 跨文档一致性提醒

| 文档 | 需同步内容 |
|------|-----------|
| `PRIS-236_Support_Galxe_Quest.md` | 前端归因由 localStorage 改为 URL 实时读取 |
| `PRIS-208_Connect_Improvement.md` TC-208-021 | 操作步骤「Connect a wallet」→「Connect Wallet」 |
| `PRIS-265_move_chain_Robot_AI迁移.md` | 会员支付路径可跳过手动点击直接展开链选择 |

---

### 6.7 增量测试执行优先级

```
P0 必测（6/29 新 commit 核心）
├── T10-01, T10-02, T10-04, T10-05     Galxe 注册 + 登出
├── T11-01 ~ T11-06, T11-08            Email + USDC/USD 支付
├── T12-01 ~ T12-03                    Modal 双模式打开
├── T4-05                              Galxe 登出重定向
└── 更新后的 T1-02, T1-03              文案 + 折叠状态

P1 建议
├── T10-03, T10-06, T10-07             Galxe 边界
└── T11-07                             USDT 路径

P0 回归（§四 原文档，文案已更新）
├── T2-xx, T5-xx, T6-xx, T7-xx        无代码触碰，全量回归
└── T1-04 ~ T1-07, T2-xx               Email+Wallet 主路径
```
