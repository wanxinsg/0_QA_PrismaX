# PRIS-333 Egocentric Waitlist

> 分析日期：2026-09-18  
> 范围：三仓联动。首页独立 Waitlist 表单 + 独立表 + Admin 列表。  
> 日汇总见 [`Sep18.md`](./Sep18.md)。早期 Landing Page 改动见 [`PRIS-333_Marketing_landing-page_improvements.md`](./PRIS-333_Marketing_landing-page_improvements.md)。

| 仓库 | Commit | PR |
| --- | --- | --- |
| `prismax-marketing-rp` | `cd9a05d` — add new egocentric waitlist form; minor changes | [#15](https://github.com/PrismaXAI/prismax-marketing-rp/pull/15) `694b0fe` |
| `app-prismax-rp-backend` | `d1c496e` — add new egocentric waitlist form | [#78](https://github.com/PrismaXAI/app-prismax-rp-backend/pull/78) `47d4e83` |
| `app-prismax-rp` | `4b560d9` — show egocentric waitlist on admin portal; minor table renaming | [#87](https://github.com/PrismaXAI/app-prismax-rp/pull/87) `f3f3003` |

依赖：先执行 `20260917_create_marketing_egocentric_waitlist_requests.sql`。

---

## 1. Feature 描述

Network「Join the waitlist」从 Discover/Researcher 的 Request Access 拆出，改为独立 Egocentric Waitlist。提交写入新表，Admin Data Subscribers 可查看。

| 项目 | 旧行为 | 新行为 |
| --- | --- | --- |
| 入口 | `openRequestAccess("egocentric_waitlist")` | `openEgocentricWaitlist()` 独立弹窗 |
| 写入 | `marketing_interest_access_requests` | `marketing_egocentric_waitlist_requests` |
| 字段 | email 等，不收集 use case / data interest | 必填 email + setup；选填 name / region / tasks / hours |
| Request Access | 含 `egocentric_waitlist` 分支 | 只剩 `"discover" \| "researcher"`，始终收集 use case / data interest |
| Admin | 混在 Interest Requests | Data Subscribers → **Egocentric Waitlist** 独立表 |

**不在本次范围：**

- 不发确认邮件、不开通账号、没有 Approve/Deny
- 不改 Robotics Data Beta 申请（见 [`PRIS-349_roboticsdatabetarelease.md`](./PRIS-349_roboticsdatabetarelease.md)）
- Footer Forum / Terms / Brand Kit 是同 commit 附带改动，一并回归

---

## 2. 业务流程

```text
Homepage #network 「Join the waitlist」
  → EgocentricWaitlistModal
  → POST /api/marketing/egocentric-waitlist
      必填：email、setup
      选填：name、region、tasks、hours_per_week
  → INSERT marketing_egocentric_waitlist_requests
  → Admin Data Subscribers → Egocentric Waitlist
      GET /api/admin/get-marketing-egocentric-waitlist-requests?page=&page_size=10
```

---

## 3. 营销站表单

- Provider 挂在 `app/layout.tsx`，与 Contact Sales / Request Access 并列。
- 必填校验：合法 email + Recording setup。失败文案：`Please add a valid email and your recording setup.`
- Setup：`Smartphone` / `Action camera (GoPro etc.)` / `AR / VR headset` / `No equipment yet`
- Hours/week：`Under 5` / `5–10` / `10–20` / `20+`
- 成功页：`You're on the list.`；关闭后 reset 表单。
- Escape、遮罩、关闭按钮均可关闭；打开时锁定 body 滚动。
- 不要求登录。

文件：

- `components/EgocentricWaitlistModal.tsx`
- `components/home/Network/Network.tsx`（CTA 改绑新 modal）
- `components/RequestAccessModal.tsx`（去掉 waitlist 分支）
- `components/SiteFooter/SiteFooter.tsx`（Forum 隐藏；Terms / Brand Kit `external: true`）

---

## 4. 后端

### 4.1 提交

`POST /api/marketing/egocentric-waitlist`

- Rate limit：`4/min`、`7/hour`、`15/day`（按 IP）
- Email 去空格并小写；`email_validator` 校验，不检查可达性
- 缺 email → 400 `Email is required`
- 缺 setup → 400 `Recording setup is required`
- 同 email 已存在 → **429**，`You're already on the waitlist. Our team is working on your request, and we'll be in touch soon.`
- 成功 → 200 `Request submitted successfully`
- `POST /api/marketing/request-access` 不再接受 `egocentric_waitlist`

表 `email` **没有 UNIQUE 约束**，去重只在应用层。并发双提交可能插入两条。

### 4.2 Admin 列表

`GET /api/admin/get-marketing-egocentric-waitlist-requests?page=&page_size=10`

- 仅 `@jwt_required()`，**没有显式 `role=admin` 检查**（与原 Interest Requests 相同）。有任意有效 JWT 即可读。
- 按 `created_at DESC`，默认每页 10 条。

---

## 5. Admin 信息架构

Data Subscribers sub-nav：

| section id | 标签 | 说明 |
| --- | --- | --- |
| `data-sub-contact-sales` | Contact Sales | 标题去掉 Submissions |
| `data-sub-discover-researcher-interest` | Discover/Researcher Interest | 原 Interest Requests |
| `data-sub-egocentric-waitlist` | Egocentric Waitlist | 本次新增 |
| `data-sub-information` | Subscribers’ Information | 同日 Beta 改动，非本 feature |
| `data-sub-pending` | Pending Beta Access | 同日 Beta 改动，非本 feature |

Egocentric 列：Request ID / Email / Name / Region / Setup / Tasks / Hours/Week / Created At。

旧 section id `data-sub-interest-requests` 不再定位。

---

## 6. Footer 附带改动

- Forum 链接注释掉，Resources 不再展示 Forum。
- `Terms & Policies`、`Brand Kit` 增加 `external: true`（新标签打开）。

---

## 7. 风险点

| 编号 | 风险 | 优先级 | 验证重点 |
| --- | --- | --- | --- |
| R-01 | 旧 Request Access 入口残留 | 高 | CTA 打开 `Join the waitlist`；请求打 `/egocentric-waitlist`，不打 `/request-access` |
| R-02 | Discover/Researcher 回退 | 高 | use case / data interest 必须出现；type 只能是 discover/researcher |
| R-03 | 重复提交 | 高 | 同 email 第二次 429，不进成功页，不新增行 |
| R-04 | 并发双写 | 中 | 表无 UNIQUE；连点/并发可能两条，记已知风险 |
| R-05 | 前端校验被绕过 | 高 | 缺 setup / 非法 email 直接打 API 必须 400 |
| R-06 | Admin 鉴权偏弱 | 中 | 普通用户 JWT 是否能拉 waitlist（记录实际行为） |
| R-07 | 旧书签失效 | 中 | 运营按新名称找表 |
| R-08 | Footer 外链 | 中 | Terms / Brand Kit 新开标签；Forum 不再出现 |
| R-09 | Rate limit | 低 | 超限 429，页面不白屏 |

---

## 8. 测试数据与环境

- 营销站、Admin、user-management 含上表 commit；Waitlist 表已建。
- 未用过的 waitlist 邮箱；已在 waitlist 的邮箱。
- Discover Request Access 与 Waitlist 可共用对比邮箱。
- Admin 白名单钱包；可直打 API。
- 桌面 Chrome；可看 Network / DB。

---

## 9. E2E 测试用例

| ID | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| PRIS-333-001 | P0 | 打开 Egocentric Waitlist | 营销站首页 | 滚到 Network，点 Egocentric 卡片 `Join the waitlist` | 打开独立弹窗，标题 `Join the waitlist`；email 自动聚焦；页面不可滚动 |
| PRIS-333-002 | P0 | 必填校验 | 弹窗已开 | 不填或填非法 email，不选 setup，点提交 | 高亮无效字段；提示 `Please add a valid email and your recording setup.`；不发请求 |
| PRIS-333-003 | P0 | 最小必填提交 | 新 email | 只填 email + setup，提交 | `POST /api/marketing/egocentric-waitlist` 200；成功页 `You're on the list.`；DB 有记录，选填字段为空 |
| PRIS-333-004 | P0 | 完整字段提交 | 新 email | 填 name/region/tasks/hours，选 AR/VR，提交 | 后端原样入库；Admin 表对应列可见 |
| PRIS-333-005 | P0 | 重复 email | 该 email 已在 waitlist | 再提交一次 | 429；弹窗显示 already on the waitlist 文案；不进入成功页；不新增行 |
| PRIS-333-006 | P0 | Discover/Researcher 未混用 | — | Plans 打开 Discover 或 Researcher Request Access | 仍是 Request Access；含 use case / data interest；提交 `/request-access`，type 不是 `egocentric_waitlist` |
| PRIS-333-007 | P0 | 旧 type 被拒绝 | 可直接调 API | `POST /request-access` 带 `request_type=egocentric_waitlist` | 失败，不写入 interest 表，也不写入 waitlist 表 |
| PRIS-333-008 | P1 | 关闭并重置 | 填了一半或已成功 | Escape / 遮罩 / X / 成功页 Close，再打开 | 表单重置；成功态消失；滚动恢复 |
| PRIS-333-009 | P1 | 提交中防重复 | 人为延迟接口 | 连点提交 | 按钮 `Submitting…` 且 disabled；至多一次成功写入 |
| PRIS-333-010 | P0 | Admin 列表可见 | 已有至少 1 条 | Admin → Data Subscribers → Egocentric Waitlist | 标题 `Egocentric Waitlist`；8 列齐全；最新记录在最上 |
| PRIS-333-011 | P1 | Admin 分页 | >10 条 | 翻页 | `page` 变化；空页不出现；边界 Previous/Next disabled |
| PRIS-333-012 | P1 | Admin 空态 | 无数据环境 | 打开 Egocentric Waitlist | `No egocentric waitlist requests found`；不白屏 |
| PRIS-333-013 | P0 | Data Subscribers 信息架构 | Admin 已登录 | 检查 sub-nav 与 General | 出现 Discover/Researcher Interest、Egocentric Waitlist；无旧 `Interest Requests` 标题；Contact Sales 标题缩短 |
| PRIS-333-014 | P1 | Footer | 任意营销站页 | 看 Resources / Company；点 Terms、Brand Kit | 无 Forum；Terms 与 Brand Kit 新标签打开，原页保留 |
| PRIS-333-015 | P2 | 限流 | 同一 IP 短时多次提交 | 超过 4/min 或 15/day | 429；前端展示错误，不崩溃 |
| PRIS-333-016 | P1 | 未登录可提交 | 无账号 | 打开首页直接提交 waitlist | 不要求登录；只校验 email/setup |
| PRIS-333-017 | P2 | 无 token 调 Admin GET | — | 不带 Authorization 调 waitlist Admin API | 401；不返回数据 |
| PRIS-333-018 | P0 | 两套获客表单互不写入 | 同一 email | 先 Discover Request Access，再 Egocentric Waitlist | 分别进 interest 表和 waitlist 表；Admin 两张表都能看到 |

---

## 10. 发布前检查清单

- [ ] 三仓含上表 commit；`marketing_egocentric_waitlist_requests` 已建
- [ ] 营销站、Admin、user-management 一起发，避免表单打到旧 API
- [ ] 所有 P0：独立提交、去重、Admin 可见；Discover/Researcher 未回退；旧 `egocentric_waitlist` type 被拒绝
- [ ] Footer：无 Forum；Terms / Brand Kit 新标签
- [ ] 已知限制：email 无 DB UNIQUE；Admin GET 未校验 `role=admin`

---

## 11. 关联说明

- 与 Robotics Data Beta 申请、My Data 门禁 **无写入耦合**；同日 Data Subscribers 还挂了 Subscribers / Pending，测 Waitlist 时不要和那两张表串台。
- 早期 Landing Page（Events / Network GIF / Request Access v3）见 [`PRIS-333_Marketing_landing-page_improvements.md`](./PRIS-333_Marketing_landing-page_improvements.md)。本次是把其中 Egocentric CTA 从 Request Access 拆成独立表单。
