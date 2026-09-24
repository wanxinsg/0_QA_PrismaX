# PRIS-356 Admin Portal — Data Subscribers Tab

> 分析日期：2026-09-16  
> Commit：`app-prismax-rp` `b7955cf` — *PRIS-356: create new data subscribers admin tab*  
> 范围：**仅 FE（独立）**；无 backend / SDK 变更。API 与表能力保持原样，本次是 Admin Portal 信息架构重组。

---

## 1. Feature 描述

将获客 / 订阅意向相关两张 Admin 表从 **General** 迁出，独立成 **Data Subscribers** 顶层 Tab，方便运营处理 Contact Sales 与 Robotics Data 访问意向，而不与 General 运维（User Stats、Whitelist、Fleet Purchase 等）混在一起。

| 组件 | 旧位置 | 新位置 | 标题变化 |
| --- | --- | --- | --- |
| `ContactSalesSubmissionsTable` | General → Contact Sales | Data Subscribers → Contact Sales | 不变：`Contact Sales Submissions` |
| `MarketingInterestAccessRequestsTable` | General → Marketing Requests | Data Subscribers → Interest Requests | `Marketing Interest Access Requests` → **`Interest Requests`** |

文件移动：

- `src/components/Admin/General/ContactSalesSubmissionsTable.js` → `src/components/Admin/DataSubscribers/ContactSalesSubmissionsTable.js`（内容不变）
- `src/components/Admin/General/MarketingInterestAccessRequestsTable.js` → `src/components/Admin/DataSubscribers/MarketingInterestAccessRequestsTable.js`（仅标题文案）
- `src/components/Admin/AdminPortal.js`：新增 tab / sub-nav / 渲染分支；General 去掉上述两段

**不在本次范围：**

- 不新增 / 不修改 backend 接口
- 不改变分页、鉴权、列字段与数据源
- 不涉及 On-Demand Order / Jobs / SDK（与 PRIS-326/330 无耦合）

---

## 2. 页面结构与导航

入口：Admin Portal（需 `prismax_admin_token`）

新增顶层 Tab：**Data Subscribers**（位于 VLA-Operators 与 Dataset Stats 之间）

Sub-nav（`DATA_SUBSCRIBERS_SECTIONS`，默认展开）：

| section id | 标签 | 渲染组件 |
| --- | --- | --- |
| `data-sub-contact-sales` | Contact Sales | `ContactSalesSubmissionsTable` |
| `data-sub-interest-requests` | Interest Requests | `MarketingInterestAccessRequestsTable` |

General Tab 变更：

- 移除 sub-nav：`Contact Sales`、`Marketing Requests`
- 移除对应内容区挂载；其余 General 分区不变

---

## 3. 表能力（行为不变，仅搬家）

### 3.1 Contact Sales

- API：`GET /api/admin/get-contact-sales-submissions?page=&page_size=10`
- Header：`Authorization: Bearer <prismax_admin_token>`
- 列：Submission ID / Topic / First Name / Last Name / Email / Phone Number / Company / Job Title / Company Size / Message / Created At / Email Sent
- 分页：每页 10；空态 / loading / error 与搬家前一致

### 3.2 Interest Requests（原 Marketing Interest Access Requests）

- API：`GET /api/admin/get-marketing-interest-access-requests?page=&page_size=10`
- Header：同上
- 列：Request ID / Request Type / Email / Role / Name / Organization / Use Case / Data Interest / Created At
- 页面主标题改为 **Interest Requests**；空态文案仍可能含 “marketing interest…”（未改逻辑）

---

## 4. 风险点

| 编号 | 风险描述 | 优先级 |
| --- | --- | --- |
| R-01 | General 仍残留 Contact Sales / Marketing Requests 入口或内容，造成双份或找不到 | 高 |
| R-02 | Data Subscribers Tab / sub-nav 不出现、点了空白、或与其他 Tab 串内容 | 高 |
| R-03 | 搬家后 import 路径错误导致白屏 / chunk 加载失败 | 高 |
| R-04 | Interest Requests 标题已改，运营文档/口头仍用旧名导致找错区 | 中 |
| R-05 | 分页、鉴权失效（token 缺失）行为与搬家前不一致 | 中 |
| R-06 | sub-nav 点击滚动 / active section 高亮与 General/VLA 行为不一致 | 低 |
| R-07 | `AdminPortal.js` 中 Data Subscribers 分支残留注释掉的 VLA-Operators 模板代码，后续误开造成串台 | 低 |

---

## 5. E2E 测试用例

### 环境准备

- Admin 已登录 Admin Portal
- Contact Sales / Marketing Interest 两侧最好各有 ≥1 条历史数据（或可接受空态）
- 确认被测前端含 `b7955cf`（或等价 Data Subscribers Tab）

---

### 功能模块一：Tab 与信息架构

| TC | 测试目标 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| TC-01 | Data Subscribers 顶层 Tab 可见并可进入 | Admin 已登录 | 打开 Admin Portal，查看顶栏 Tab | 出现 **Data Subscribers**；点击后进入该 Tab，默认展开 sub-nav（Contact Sales / Interest Requests） | 高 |
| TC-02 | General 不再包含这两张表 | — | 打开 General Tab，检查 sub-nav 与页面内容 | 无 Contact Sales / Marketing Requests；User Stats、Fleet Purchase、Whitelist 等仍在 | 高 |
| TC-03 | Tab 切换不串内容 | 两边 Tab 均可打开 | General ↔ Data Subscribers ↔ VLA-Operators 来回切换 | 各 Tab 只渲染自身组件；Data Subscribers 仅两张订阅相关表 | 高 |
| TC-04 | Sub-nav 分区定位 | Data Subscribers 已打开 | 分别点击 Contact Sales / Interest Requests | 滚动/高亮对应 section；两个 section id 分别为 `data-sub-contact-sales`、`data-sub-interest-requests` | 中 |

---

### 功能模块二：Contact Sales

| TC | 测试目标 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| TC-05 | 列表加载与列齐全 | 有提交数据 | Data Subscribers → Contact Sales | 标题 `Contact Sales Submissions`；列与搬家前一致；请求 `get-contact-sales-submissions` | 高 |
| TC-06 | 分页 | 数据 >10 条 | 翻页 / 上一页 / 下一页 | `page` 变化；总数页正确；边界不可越界 | 中 |
| TC-07 | 空态 / 错误 | 无数据或断网 / 无 token | 打开 Contact Sales | 空态或 Error 提示；不白屏 | 中 |

---

### 功能模块三：Interest Requests

| TC | 测试目标 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| TC-08 | 标题与列表 | 有意向数据 | Data Subscribers → Interest Requests | 标题为 **Interest Requests**（非旧全称）；列齐全；请求仍为 `get-marketing-interest-access-requests` | 高 |
| TC-09 | 分页 / 空态 / 鉴权 | 同 TC-06/07 | 翻页；清 token 刷新 | 行为与搬家前一致 | 中 |

---

### 功能模块四：回归（负向）

| TC | 测试目标 | 前置条件 | 操作步骤 | 预期结果 | 优先级 |
| --- | --- | --- | --- | --- | --- |
| TC-10 | 旧 General 深链 / 书签失效可接受 | 若有人收藏旧 section id | 访问仍指向 `general-contact-sales` / `general-marketing-requests` 的旧锚点 | 不再定位到表；须改走 Data Subscribers；不要求兼容旧 id | 中 |
| TC-11 | 后端无变更确认 | 有权查 backend/SDK 版本 | 对比本次发布是否含相关 BE/SDK commit | 无对应 backend/SDK 改动；仅 FE 部署即可生效 | 低 |

---

## 6. 发布前检查清单

- [ ] 前端含 `b7955cf`（Data Subscribers Tab）
- [ ] Admin Portal 可见 Data Subscribers；General 无 Contact Sales / Marketing Requests
- [ ] Contact Sales 列表 / 分页 / 鉴权正常（TC-05～07）
- [ ] Interest Requests 标题正确，列表 / 分页正常（TC-08～09）
- [ ] Tab 切换无串内容、无白屏（TC-01～03）
- [ ] 无需同步发布 backend / SDK

---

## 7. 关联说明

- 与 PRIS-326 Jobs 上传、Org member removal **无依赖**；可单独测、单独发 FE。
- 营销站 / Request Access 提交若仍写入上述两个 API，搬家后运营入口变更为 Data Subscribers，对外表单链路不变。
