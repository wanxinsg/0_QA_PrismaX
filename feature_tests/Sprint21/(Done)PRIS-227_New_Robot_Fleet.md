# PRIS-227 Aparna 2026-06-17 Commit Logic Analysis

## 1. 分析范围

本次仅分析 Aparna 在 2026-06-17 的相关提交逻辑（前端 + 后端）：

- `app-prismax-rp`
  - `db6430dc6f10883ac459a999b48fc263d29706b1`
  - `77e7055a48b0598d0f15e6fef486f232301d02f6`
- `app-prismax-rp-backend`
  - `da59f5883fb7161b995304507dd866bae44c3d3c`

核心目标：完成 PRIS-227 的新 Fleet 购买闭环（用户下单 + 后端入库 + 邮件触达 + Admin 可追踪）。

---

## 2. 高层业务变化

从“展示机器人信息”为主，升级为“可发起购买请求并被运营跟进”的完整流程。

主线包括：

1. 用户侧 `/fleet` 页面升级到 `FleetV2`，支持 Buy now 主流程。  
2. 对会员等级进行下单门槛控制（Explorer 先升级）。  
3. 购买请求落库到 `fleet_purchase_info`。  
4. 下单后发送购买启动邮件，并记录是否发送成功。  
5. Admin 侧可分页查看购买意向记录。  

---

## 3. 前端逻辑（app-prismax-rp）

## 3.1 `db6430...`：主功能落地

### 3.1.1 路由与页面入口

- `Home` 中将 `/fleet` 切到 `FleetV2`（主入口切换）。
- 表明新 Fleet 流程已成为默认路径，而非实验分支页面。

### 3.1.2 用户购买流程

- `FleetV2` 引入购买状态管理：
  - 机器人详情弹窗（`RobotModalV2`）
  - 购买信息弹窗（`PurchaseInfoModal`）
  - 升级会员弹窗（`UpgradeMembershipModal`）
- Buy now 分流规则：
  - 未登录（无 token）：触发登录/侧边面板
  - `Explorer Member`：先弹升级会员
  - `Amplifier/Innovator Member`：直接进入购买信息填写

### 3.1.3 升级成功后的续接

- 支付成功后可回到 Fleet 流程继续购买，而不是中断在升级闭环。
- 对 `/fleet` 场景做了更明确的按钮与文案（例如 “Continue purchasing your robot” / “Place order”）。

### 3.1.4 Admin 可见性

- `AdminPortal` 用 `FleetPurchaseInfoTable` 替代旧 reserve 入口（或并行替换）。
- `FleetPurchaseInfoTable` 对接 `/api/admin/get-fleet-purchase-info`，支持分页、加载态、错误态、空态。
- 表格包含联系人、项目、机型、创建时间、邮件发送状态等字段。

## 3.2 `77e7055...`：补强与可编辑性修复

- `VLAAdminMachinesTable` 增加 `jsonb` 字段编辑支持（以前对复杂字段编辑不友好）：
  - `input_type=json_csv` 时使用 `textarea`
  - 前端增加 JSON 格式校验提示
  - 编辑态对复杂结构做安全字符串化显示
- Fleet 与 Modal 有若干样式/缩进/文案修正，提升交互一致性。

---

## 4. 后端逻辑（app-prismax-rp-backend）

`da59...` 的核心是把前端新流程对应的 API 与数据处理补齐。

## 4.1 新增 API：`POST /api/fleet/request-purchase-robot`

### 4.1.1 输入与鉴权

- 接收用户联系方式、项目信息、`machine_id`、`user_id` 等。
- 要求 token（Header Bearer 或 body fallback）。
- 校验 `user_id` 对应的 `hash_code` 与 token 一致。

### 4.1.2 业务规则

- 会员等级限制：仅允许 `Innovator Member` 或 `Amplifier Member` 下单。
- 校验 `machine_id` 存在并取到 `robot_name`。
- 对新邮箱做有效性检查（包含可投递性校验）。

### 4.1.3 数据落库与邮件

- 插入 `fleet_purchase_info`（`email_sent` 初始为 `False`）。
- 触发购买启动邮件模板 `fleet_purchase_initiated_email.txt`。
- 根据发送结果回写 `email_sent` 字段。

### 4.1.4 返回结果

- 成功返回 `success=true`，并携带 `email_sent`，便于前端或运营感知通知状态。

## 4.2 新增 API：`GET /api/fleet/get-available-robots`

- 返回 `data_sample_machines` 里 `is_fleet_visible=true` 的机型。
- 作为 `FleetV2` 的商品源数据，按 `fleet_order` 排序。

## 4.3 新增 API：`GET /api/admin/get-fleet-purchase-info`

- 管理端分页查询购买记录，并 join 机型名称。
- 返回 `data/page/page_size/total_count/total_pages`。
- 服务 `FleetPurchaseInfoTable` 的分页与列表展示。

## 4.4 JSONB 编辑支持补强（配合前端 77e7055）

- 数据类型识别新增 `json/jsonb -> json_csv`。
- 入参校验支持 JSON 解析失败提示。
- upsert 时对对应字段做 `CAST(:column AS jsonb)`，避免字符串直接写错类型。

---

## 5. 端到端流程（E2E）

1. 用户进入 `/fleet`，拉取可购买机器人列表。  
2. 点击 Buy now：  
   - Explorer -> 先升级会员；成功后回到购买链路  
   - Amplifier/Innovator -> 直接进入购买信息填写  
3. 提交后端 `request-purchase-robot`：鉴权、会员校验、机型校验、邮箱校验。  
4. 记录写入 `fleet_purchase_info`。  
5. 发送购买启动邮件并回写 `email_sent`。  
6. Admin 在后台分页查看并跟进线索。  

---

## 6. 设计意图与收益

- 把 Fleet 从“内容页”升级为“可转化交易入口”。
- 用会员门槛保证业务策略一致（权益与下单能力对齐）。
- 用 Admin 列表 + 邮件状态，形成可运营闭环（可见、可跟进、可追踪）。
- JSONB 编辑能力补齐后，管理员维护机器元数据的成本降低。

---

## 7. 风险点与测试关注

## 7.1 风险点

- 会员状态与前后端判断不一致会导致“前端可下单但后端拒绝”。
- 邮件发送失败后虽然不阻断下单，但运营提醒需要依赖 `email_sent` 监控。
- `json_csv` 输入若为合法 JSON 但不符合业务语义（例如结构不对）仍可能写入。
- 支付跳转回流（query 参数）若边界处理不足，可能出现 modal 状态错乱。

## 7.2 测试策略（全新设计）

本节为面向 PRIS-227 的独立测试策略，不复用历史测试模板或旧条目。

### 7.2.1 目标与范围

- 验证 Fleet 购买主链路从 UI 到 DB 再到 Admin 可追踪全链路可用。
- 验证会员门槛、鉴权、数据校验、邮件状态回写等关键业务规则。
- 验证 JSONB 编辑增强在 Admin 端的可用性和数据安全性。

### 7.2.2 分层测试方法

1. **接口层（API Contract）**  
   - 对新增接口进行正向/逆向校验：状态码、错误信息、字段类型、分页结构。  
2. **流程层（Business Flow）**  
   - 覆盖用户身份分流（未登录、Explorer、Amplifier、Innovator）与状态跳转。  
3. **数据层（Persistence）**  
   - 校验 `fleet_purchase_info` 的字段落库完整性和 `email_sent` 回写一致性。  
4. **运营层（Admin Operability）**  
   - 校验 Admin 列表分页、排序、空态、异常态；保证线索可见可追踪。  
5. **可恢复性（Failure Recovery）**  
   - 邮件失败、接口异常、网络中断后流程是否可恢复且不丢单。  

### 7.2.3 风险驱动优先级

- **P0（阻断发布）**
  - 用户可下单但后端拒绝（前后端会员策略不一致）。
  - 下单成功但未写库或写库后状态错误。
  - Admin 无法看到新下单记录。
- **P1（高影响）**
  - 邮件状态显示与真实发送结果不一致。
  - 分页数据重复/丢失/total_count 错误。
  - JSONB 编辑报错或写入错误类型。
- **P2（体验）**
  - 文案、按钮状态、Modal 关闭与回流交互不一致。
  - 移动端布局与桌面端交互细节偏差。

### 7.2.4 测试数据策略

- 会员用户各准备 1 个账号：Explorer、Amplifier、Innovator。
- 机器人数据准备：可见机型 >= 3，包含不同类别和价格。
- 购买请求数据：
  - 有效样例：完整联系人+项目信息。
  - 无效样例：缺失必填、错误邮箱、非法 token、不存在 machine_id。
- JSONB 字段样例：
  - 合法数组、合法对象、空字符串、非法 JSON 文本。

### 7.2.5 上线前准入标准（Exit Criteria）

- P0 用例 100% 通过。
- P1 用例通过率 >= 95%，无未评估高风险缺陷。
- 关键路径（下单成功 + Admin 可见 + 邮件状态回写）连续跑 3 次稳定通过。
- 无新增 Sev-1/Sev-2 缺陷未闭环。

### 7.2.6 线上观测建议

- 指标：
  - `/api/fleet/request-purchase-robot` 成功率、4xx/5xx 比例、P95 延迟。
  - `email_sent=false` 占比（日/周趋势）。
  - Admin 列表查询成功率与慢查询占比。
- 告警：
  - 购买成功率连续 10 分钟低于阈值。
  - `email_sent=false` 异常升高。
  - Admin 查询错误率突增。

## 7.3 E2E 测试条目（单表汇总）

| 分类 | ID | 场景 | 前置条件 | 操作步骤 | 预期结果 |
|---|---|---|---|---|---|
| 账号与入口分流 | E2E-001 | 未登录用户点击 Buy now | 未登录状态 | 打开 `/fleet` -> 打开任意机器人详情 -> 点 Buy now | 不进入下单表单；触发登录/连接流程 |
| 账号与入口分流 | E2E-002 | Explorer 用户触发升级链路 | Explorer 账号登录 | `/fleet` -> Buy now | 弹出升级会员 Modal，不直接提交购买请求 |
| 账号与入口分流 | E2E-003 | Amplifier 用户直接下单 | Amplifier 账号登录 | `/fleet` -> Buy now | 直接进入购买信息填写 Modal |
| 账号与入口分流 | E2E-004 | Innovator 用户直接下单 | Innovator 账号登录 | `/fleet` -> Buy now | 直接进入购买信息填写 Modal |
| 下单主流程 | E2E-010 | Amplifier 正常下单成功 | Amplifier 登录，机型可购买 | 填完整表单 -> 提交 | 返回成功；展示成功态；后端写入 `fleet_purchase_info` |
| 下单主流程 | E2E-011 | Innovator 正常下单成功 | Innovator 登录 | 同上 | 返回成功；记录中 `email_sent` 为 true/false 之一且字段存在 |
| 下单主流程 | E2E-012 | 下单后 Admin 可见 | 已完成一次成功下单 | Admin 打开 Fleet Purchase Info 列表第一页 | 能看到新记录，字段完整，机型名称正确 |
| 下单主流程 | E2E-013 | 升级后继续购买 | Explorer 登录且可完成升级回流 | Buy now -> 完成升级 -> 回到 Fleet -> 提交购买 | 升级完成后可继续购买并成功提交 |
| 输入校验与错误处理 | E2E-020 | 缺少必填 first_name | Amplifier 登录 | 留空 first_name 提交 | 返回 4xx + 明确错误信息；不写库 |
| 输入校验与错误处理 | E2E-021 | 缺少 machine_id | Amplifier 登录 | 构造请求不带 machine_id | 返回 4xx；不写库 |
| 输入校验与错误处理 | E2E-022 | 非法 token | 构造无效 token | 提交购买请求 | 返回 401；不写库 |
| 输入校验与错误处理 | E2E-023 | 会员等级不符合 | Explorer 直接调用提交接口 | 直接请求 `request-purchase-robot` | 返回 401（membership 不合法） |
| 输入校验与错误处理 | E2E-024 | 非法邮箱 | 有效账号 + 非法邮箱 | 提交请求 | 返回 400；不写库 |
| 输入校验与错误处理 | E2E-025 | machine_id 不存在 | 有效账号 | 传不存在 machine_id | 返回 404；不写库 |
| 邮件与状态回写 | E2E-030 | 邮件发送成功 | 邮件服务可用 | 完成一次下单 | 记录 `email_sent=true` |
| 邮件与状态回写 | E2E-031 | 邮件发送失败回退 | 模拟 SMTP 失败 | 完成一次下单 | 下单仍成功，记录保留，`email_sent=false` |
| 邮件与状态回写 | E2E-032 | Admin 查看邮件状态 | 至少一条 true/false 数据 | 打开 Admin 列表 | Email Sent 列与 DB 一致 |
| Admin 列表与分页 | E2E-040 | 分页第一页加载 | 数据量 > 10 | 打开列表页 | 展示 10 条，含 total_pages/total_count |
| Admin 列表与分页 | E2E-041 | 翻页到下一页 | 至少 2 页数据 | 点击 Next | 数据切换正确，无重复/无丢失 |
| Admin 列表与分页 | E2E-042 | 边界页按钮状态 | 在第一页/最后一页 | 分别观察 Prev/Next | 按钮禁用状态正确 |
| Admin 列表与分页 | E2E-043 | 空数据场景 | 清空测试环境数据 | 打开列表 | 展示空态文案，不报错 |
| JSONB 编辑增强 | E2E-050 | JSONB 合法数组保存 | Admin 登录 | 在 `json_csv` 字段输入 `["a","b"]` 保存 | 保存成功，DB 为 jsonb |
| JSONB 编辑增强 | E2E-051 | JSONB 合法对象保存 | Admin 登录 | 输入 `{"k":"v"}` 保存 | 保存成功，DB 为 jsonb |
| JSONB 编辑增强 | E2E-052 | JSONB 非法文本拦截 | Admin 登录 | 输入 `["a",]` 保存 | 前端/后端返回校验错误，不写库 |
| JSONB 编辑增强 | E2E-053 | JSONB 空值处理 | 字段非 required | 输入空字符串保存 | 保存成功并按规则写入 null/空值 |
| 稳定性与并发 | E2E-060 | 同用户连续提交 | Amplifier 登录 | 30 秒内连续提交 3 次 | 受限流/防重策略约束，系统稳定无 5xx |
| 稳定性与并发 | E2E-061 | 多用户并发提交 | 10 个测试用户 | 并发发起购买请求 | 成功率达到预期，数据无串写 |
| 稳定性与并发 | E2E-062 | Admin 查询压力 | 数据量 >= 5k | 连续翻页查询 | 接口稳定，无明显超时 |

---

## 8. 执行建议

- 每次发布至少执行：E2E-001/002/003/010/012/020/022/030/031/040/050（冒烟最小集）。
- 大版本发布执行全部 E2E 条目，并在失败项后补充缺陷单与回归记录。
- 将 E2E-010、E2E-020、E2E-031、E2E-050 纳入自动化优先改造清单。

---

## 9. 一句话结论

PRIS-227（Aparna 6/17 提交）本质是在 Fleet 场景打通了“可购买 + 可运营”的最小闭环，并补上了 Admin 对结构化字段维护能力，属于一次从展示型页面向交易型流程的关键升级。

