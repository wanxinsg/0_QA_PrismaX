# Sprint 25 Feature Test Notes

---

# PRIS-370: Add `#discover-plan` and `#researcher-plan` Shareable Links

> 分析日期：2026-10-02  
> 仓库：`prismax-marketing-rp`  
> Commit：`747bfc1a138fb20f0b737b41661964e6aa491e46`  
> 作者：Aparna Rangamani  
> 涉及文件：`components/RequestAccessModal.tsx`（单文件，+25 行）

---

## 1. 改动逻辑

### 背景

首页已有 `/#contact-sales` 可分享链接——打开即滚到 Plans 区块并弹出 Contact Sales 弹窗，地址栏保持 `#contact-sales`。本次为 Request Access 弹窗补充同等机制，新增两个 hash 入口：

| Hash | 对应套餐 | 弹窗 `requestType` |
| --- | --- | --- |
| `/#discover-plan` | Discover | `"discover"` |
| `/#researcher-plan` | Researcher | `"researcher"` |

完整 URL（生产环境）：

- https://prismax.ai/#discover-plan  
- https://prismax.ai/#researcher-plan

Beta 环境：

- https://beta-www.prismax.ai/#discover-plan  
- https://beta-www.prismax.ai/#researcher-plan

### 核心实现

**1）Hash 映射表（新增）**

```tsx
const PLAN_HASHES: Record<string, RequestAccessType> = {
  "#discover-plan": "discover",
  "#researcher-plan": "researcher",
};
```

**2）`useEffect` 监听（新增，挂在 `RequestAccessProvider` 内）**

```tsx
useEffect(() => {
  function handlePlanHash() {
    if (pathname !== "/") return;           // 只在首页生效
    const type = PLAN_HASHES[window.location.hash];
    if (!type) return;                      // 不匹配则退出，不影响其他 hash
    lastFocusRef.current = document.activeElement as HTMLElement;
    scrollToHash("plans", { smooth: false, preventUrlRewrite: true });
    setRequestType(type);
    setOpen(true);
  }
  handlePlanHash();                         // 挂载即检测一次
  window.addEventListener("hashchange", handlePlanHash);
  return () => window.removeEventListener("hashchange", handlePlanHash);
}, [pathname]);
```

**3）依赖**

- `usePathname`（next/navigation）：pathname 变化时 effect 重新注册。
- `scrollToHash`（`lib/scrollToHash.ts`）：`smooth: false` 避免与随后的 body overflow 锁定冲突；`preventUrlRewrite: true` 保持地址栏 hash 不被改写为 `#plans`。

### 行为细节

| 场景 | 行为 |
| --- | --- |
| 在首页直接打开 `/#discover-plan` | 瞬间滚到 Plans 区块 → 弹出 Discover 申请弹窗 |
| 在首页直接打开 `/#researcher-plan` | 瞬间滚到 Plans 区块 → 弹出 Researcher 申请弹窗 |
| 在首页 hash 从 `#discover-plan` 变为 `#researcher-plan` | `hashchange` 触发 → 弹窗换成 Researcher |
| 非首页（如 `/robotic-data`）带同样 hash | `pathname !== "/"` 直接返回，不触发任何行为 |
| hash 不在映射表内（如 `#plans`、`#contact-sales`） | 不受影响，各自逻辑独立 |

---

## 2. 关联上下文

- **`ContactSalesModal.tsx`**：同样的模式，`/#contact-sales` → 滚 Plans + 弹 Contact Sales。本次是相同模式在 Request Access 侧的复制。
- **`Plans.tsx`**：Plans 卡片点 CTA 走 `openRequestAccess(plan.key)`，本次 hash 入口是同一 modal 的另一条打开路径，`requestType` 设置方式完全相同。
- **`lib/scrollToHash.ts`** 中 `preventUrlRewrite` 注释即以 `#contact-sales` 为例，说明与本次用途一致。

---

## 3. 测试分析

### 3.1 测试范围

| 维度 | 说明 |
| --- | --- |
| 改动范围 | 单文件、单 effect，无后端改动，无新接口 |
| 核心验证 | hash 触发 → 滚动 + 弹窗正确套餐；URL 保持；非首页隔离 |
| 回归范围 | Plans 区块点击 CTA 不退化；`#contact-sales` 不受影响；`#plans` 等其他 hash 正常 |
| 无需验证 | 后端 `/api/marketing/request-access` 逻辑（未改动）；弹窗提交流程（未改动） |

### 3.2 风险点

| 编号 | 风险 | 优先级 | 验证重点 |
| --- | --- | --- | --- |
| R-01 | 地址栏被改写为 `#plans` | 高 | 打开 `/#discover-plan` 后地址栏应保持不变 |
| R-02 | 滚动动画与弹窗锁定冲突 | 高 | `smooth: false` 是否生效；弹窗正常打开不白屏、不卡住 |
| R-03 | 非首页误触发 | 高 | `/robotic-data#discover-plan` 等路由不弹窗 |
| R-04 | 无效 hash 干扰 | 中 | `#plans`、`#contact-sales`、`#network` 均不受影响 |
| R-05 | hashchange 多次触发 | 中 | 同页 hash 连续切换弹窗状态是否正确 |
| R-06 | 弹窗关闭后焦点还原 | 低 | 关闭后焦点回到触发前元素 |
| R-07 | Plans 按钮点击回退 | 高 | 直接点套餐 CTA 的 `openRequestAccess` 不受影响 |

---

## 4. 测试数据与环境

- 环境：Beta 站（`https://beta-www.prismax.ai`）及本地 dev
- 无需特殊账号权限（hash 入口不做权限校验，弹窗内鉴权逻辑未改动）
- 浏览器：桌面 Chrome（主）；Firefox / Safari 各跑一轮回归
- 工具：地址栏直输 URL；DevTools Network 面板确认无多余请求

---

## 5. E2E 测试用例

### 5.1 核心 hash 入口

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| PRIS-370-001 | P0 | `#discover-plan` 打开 Discover 弹窗 | 打开 `https://beta-www.prismax.ai/#discover-plan` | 等页面加载完成 | 页面瞬间滚到 Plans 区块；Request Access 弹窗打开，标题/套餐为 **Discover**；地址栏保持 `#discover-plan` |
| PRIS-370-002 | P0 | `#researcher-plan` 打开 Researcher 弹窗 | 打开 `https://beta-www.prismax.ai/#researcher-plan` | 等页面加载完成 | 页面瞬间滚到 Plans 区块；Request Access 弹窗打开，标题/套餐为 **Researcher**；地址栏保持 `#researcher-plan` |
| PRIS-370-003 | P0 | 地址栏不改写 | 打开 `/#discover-plan` | 弹窗弹出后，检查地址栏 | 地址栏仍为 `#discover-plan`，未被替换为 `#plans` |
| PRIS-370-004 | P0 | 滚动位置正确 | 从页面顶部打开 `/#researcher-plan` | 等弹窗出现 | Plans 区块在视口内可见（在弹窗后方）；`smooth: false` 即时到位，无动画中途卡断 |
| PRIS-370-005 | P0 | `hashchange` 切换套餐 | 已在首页，弹窗已关 | 地址栏改为 `#discover-plan`，再改为 `#researcher-plan` | 每次 hash 变化弹窗打开对应套餐；两次弹窗套餐分别正确 |

### 5.2 隔离与边界

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| PRIS-370-006 | P0 | 非首页不触发 | 打开 `/robotic-data#discover-plan` | 等页面加载 | 不弹 Request Access 弹窗；页面正常展示 |
| PRIS-370-007 | P0 | 非首页不触发（Researcher） | 打开 `/robotic-data#researcher-plan` | 等页面加载 | 不弹弹窗 |
| PRIS-370-008 | P1 | `#plans` 不触发弹窗 | 打开 `/#plans` | 等页面加载 | 仅滚到 Plans 区块，不弹任何弹窗 |
| PRIS-370-009 | P1 | `#contact-sales` 不受影响 | 打开 `/#contact-sales` | 等页面加载 | 滚到 Plans 区块，弹出 **Contact Sales** 弹窗（非 Request Access）；行为与本次改动无关 |
| PRIS-370-010 | P1 | 其他 hash 不受影响 | 打开 `/#network`、`/#hero` | 等页面加载 | 不弹窗；滚动行为与之前一致 |
| PRIS-370-011 | P1 | 无 hash 首页不触发 | 打开 `https://beta-www.prismax.ai` | 等页面加载 | Plans 区块不自动滚动，不弹窗 |

### 5.3 Plans 按钮回归

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| PRIS-370-012 | P0 | Discover 按钮正常 | 首页 Plans 区块可见 | 点 Discover 套餐 `Request access →` 按钮 | 弹出 Request Access 弹窗，套餐为 **Discover**；地址栏不变（不追加 hash） |
| PRIS-370-013 | P0 | Researcher 按钮正常 | 首页 Plans 区块可见 | 点 Researcher 套餐 `Request access →` 按钮 | 弹出 Request Access 弹窗，套餐为 **Researcher**；地址栏不变 |
| PRIS-370-014 | P1 | 先 hash 后按钮 | 先打开 `/#discover-plan`（Discover 弹窗），关闭后点 Researcher 按钮 | 关弹窗 → 点 Researcher CTA | 弹出 Researcher 弹窗；套餐正确切换 |

### 5.4 焦点与弹窗关闭

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| PRIS-370-015 | P1 | Escape 关闭弹窗 | `/#discover-plan` 弹窗已开 | 按 Escape | 弹窗关闭；焦点还原到触发前元素（若有）；body 滚动解锁 |
| PRIS-370-016 | P1 | 遮罩关闭弹窗 | 弹窗已开 | 点弹窗外部遮罩 | 弹窗关闭；地址栏 hash 保留；body 滚动解锁 |
| PRIS-370-017 | P2 | 弹窗开启时 body 锁定 | `/#researcher-plan` 弹窗已开 | 尝试滚动页面 | 无法滚动；关闭弹窗后可正常滚动 |

### 5.5 跨浏览器与分享场景

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| PRIS-370-018 | P1 | Firefox 打开 Discover 链接 | Firefox 浏览器 | 粘贴 `https://beta-www.prismax.ai/#discover-plan` 到地址栏 | 行为与 Chrome 一致；弹窗正常打开 |
| PRIS-370-019 | P1 | Safari 打开 Researcher 链接 | Safari 浏览器 | 粘贴 `https://beta-www.prismax.ai/#researcher-plan` | 行为与 Chrome 一致 |
| PRIS-370-020 | P2 | 外部页面跳转 | 其他页面的 `<a href="https://beta-www.prismax.ai/#discover-plan">` | 点击外链跳转 | 新标签落地于首页，滚到 Plans，弹出 Discover 弹窗 |

---

## 6. 发布前检查清单

- [ ] `/#discover-plan`：滚动 + Discover 弹窗 + 地址栏不变（P0）
- [ ] `/#researcher-plan`：滚动 + Researcher 弹窗 + 地址栏不变（P0）
- [ ] 非首页路由带同 hash 不触发弹窗（P0）
- [ ] Plans 区块 CTA 按钮点击不退化（P0）
- [ ] `/#contact-sales` 行为不受影响（P0）
- [ ] `/#plans`、`/#network` 等其他 hash 不触发弹窗（P1）
- [ ] 弹窗关闭后 body 滚动解锁、焦点还原（P1）
- [ ] 无后端接口改动需发布（本次纯前端）

---

## 7. 关联说明

- 同模式参考：`ContactSalesModal.tsx` 的 `/#contact-sales` 入口（Sprint24 已测）。
- 弹窗提交流程（`POST /api/marketing/request-access`）未改动，无需重测。
- 如后续需要深链直接选中某个 Plan 并预填表单，需单独评估改动范围。
