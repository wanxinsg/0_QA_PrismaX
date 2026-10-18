# QA-Review 相关 Commit 逻辑分析（May 22 - May 23）

## 分析范围

本次基于以下 4 个与 `qa-review` 直接相关的 commit 进行分析：

- `app-prismax-rp-backend`
  - `86f6ae6` - PRIS-181: add earnings integration to qa review endpoint
- `app-prismax-rp`
  - `721b668` - PRIS-181: add earnings modal and integrate it; misc improvements
  - `8ca5567` - PRIS-181, PRIS-191: improve earnings badge styling, date fix, fallback error code
  - `a902e0a` - PRIS-136: update validator status on qa review page

---

## 一句话主线

这批改动把 QA Review 从“只提交评分”扩展成“提交评分 -> 记录逐 episode 行为 -> 达成最终共识后发放积分 -> 前端可查看 earned/pending/missed 明细”的完整闭环，同时补齐了 QA 身份在页面展示上的专用状态样式和文案。

---

## Commit 级别逻辑拆解

## 1) `86f6ae6`（backend）  
**目标**：把积分发放逻辑接入 `submit_upload_qa_review`，并建立可追踪的 episode 级行为记录。

**核心改动：**

- 在 QA 提交后，新增写入 `data_qa_episode_activity`：
  - 按本次提交包含的 `episode_ids`，为每条 episode 记录 `(user_id, episode_id, qa_session_id)`。
  - `ON CONFLICT DO NOTHING`，避免重复写入冲突。
- 当 review 流程达到可生成 `final_decision` 的条件后：
  - 调用 `_reward_final_decision_qa_points(conn, upload_id, final_decision)` 发放奖励积分。
- 在 `qa_helper.py` 新增 `_reward_final_decision_qa_points`：
  - 读取该 upload 下所有 QA session。
  - 以 `final_quality_score` 为基准，筛选 `qa_score` 在 `±15` 范围内的评审者（命中奖励规则）。
  - 对命中用户的 episode，批量插入 `point_transactions`（每条 `+100`，类型 `data_qa_episode_review`）。
  - 再把生成的 `transaction_id` 回填到 `data_qa_episode_activity.point_transaction_id`，形成“行为记录 <-> 积分流水”关联。

**业务意义：**

- QA 奖励不再是抽象统计，而是可以追溯到每一个 episode 的审核行为和积分交易，满足“明细可查 + 奖励可追踪”。

---

## 2) `721b668`（frontend）  
**目标**：在 QA Review 页面正式落地“我的收益（My earnings）”入口与弹窗。

**核心改动：**

- 新增 `EarningsModal` 组件（含样式）：
  - 请求 `GET /data/qa/get-episode-earnings`。
  - 展示三个汇总指标：`total_points`、`pending_points`、`episodes_scored`。
  - 展示 episode 明细列表：episode id、scenario、提交时间、积分状态（granted/pending/missed）。
  - 明确说明规则：`pending` 在共识达成后发放；`—` 表示评分偏离超过 `±15%`。
- 入口接入两处：
  - `DataQAReview` 顶部 validator status 区域增加 “View earnings” 点击事件。
  - `QAReviewSuccessModal` 增加“View earnings”跳转（并支持 back 逻辑）。

**业务意义：**

- 将后端新增的积分体系前台可视化，用户在 QA 任务完成后可以立即看到收益状态，提升激励闭环与可解释性。

---

## 3) `8ca5567`（frontend）  
**目标**：修正 earnings 体验细节与错误码兜底展示，降低歧义。

**核心改动：**

- `EarningsModal` 日期逻辑修复：
  - 原先用时间差直接算天数，容易受时分秒和时区边界影响。
  - 现在改成“本地日期的午夜对齐”后再计算，`Today/Yesterday` 判定更稳定。
- `EarningsModal` 布局优化：
  - 列表 body 独立滚动、header 固定，长列表可读性更好。
  - 各列宽、对齐、换行细节优化，避免标签和积分状态错位。
- `UploadDashboard` 错误码兜底：
  - 引入 `FALLBACK_ERROR_CODE = E-000`。
  - 无论 failed check 还是 processing error，都能保证显示错误码，不再出现只有描述无 code 的情况。

**业务意义：**

- 这次不是改业务规则，而是提高“信息稳定性和一致性”，减少用户对时间标签和错误信息的误解。

---

## 4) `a902e0a`（frontend）  
**目标**：让 QA 用户在 QA Review 页面使用专属 validator 状态呈现，而不是沿用 member class 逻辑。

**核心改动：**

- `ValidatorStatus` 新增按 `userRole` 分支：
  - `qa / senior qa / expert qa` 映射成专属 label（Validator / Senior Validator / Expert Validator）。
  - 增加 QA 专属 badge / dot 样式。
- QA 角色与普通会员显示差异：
  - QA 不再展示“spots open”与 pip 进度条。
  - 改为直接展示 `reviews completed` 的数量文案。
- 保留 Innovator / Amplifier / Explorer 的原有分层逻辑，避免影响非 QA 用户。

**业务意义：**

- QA 身份展示与实际职责一致，避免把 QA 运营指标和会员资格指标混在一起，减少认知噪音。

---

## 端到端业务链路（从提交到发奖）

1. QA 在 `DataQAReview` 提交评分。  
2. 后端保存 QA session，并记录本次涉及的 episode 活动行。  
3. 当 upload 达到最终决策条件时，计算 `final_quality_score`。  
4. <span style="color: blue;">依据 `gate 与 final_gate 一致` + `分差 ±8` 规则筛选可奖励的 QA 评分。</span>  
5. 为命中记录写入积分流水（`point_transactions`，每条 +100）。  
6. 将流水 ID 回填到 episode activity，形成可追踪关系。  
7. 前端 `EarningsModal` 拉取汇总与明细，展示 granted/pending/missed。  

---

## 设计意图总结

- **PRIS-181 主体意图**：建立 QA 奖励的业务闭环（记录、结算、展示）。  
- **PRIS-136 主体意图**：把 QA 角色从“会员层级视角”中抽离，给出更准确的角色化状态展示。  
- **PRIS-191 关联意图**：修复边界体验（日期、布局、错误码），增强信息可信度。  

---

## 关注点与建议验证项

- **奖励映射正确性**：确认 `point_transactions` 与 `data_qa_episode_activity` 的一对一关联在高并发下保持稳定。  
- **幂等性**：验证同一 upload 在重复触发 final decision 时是否可能产生重复积分流水。  
- <span style="color: blue;">**规则一致性**：若前端仍展示 `±15%` 说明，需确认并同步为“gate 一致 + 分差 `±8`”，避免误导。</span>  
- **接口容错**：`get-episode-earnings` 在 token 失效、空数据、部分字段缺失时的 UI 回退已覆盖，但建议补充自动化用例。  

---

## 结论

这批改动是一次完整的 QA Review 激励能力落地：  
后端补全奖励发放与可追踪数据结构，前端补全入口与明细可视化，并同步优化 QA 角色状态展示。整体逻辑连贯，已具备“可运营、可解释、可追溯”的基础形态。

---

## 测试策略（QA Review Earnings 闭环）

## 1) 测试目标

- 验证“提交评分 -> 共识结算 -> 发奖入账 -> 前端可视化”全链路正确性。  
- <span style="color: blue;">验证奖励规则（`gate 与 final_gate 一致` + `分差 ±8`）在边界值和多人评审场景下行为一致。</span>  
- 验证 UI 展示与后端状态同步（granted/pending/missed、汇总数值、日期标签）。  
- 验证角色化展示（QA vs 非 QA）不互相污染。  

## 2) 分层策略

- **API/服务层（高优先）**：优先锁定积分计算、幂等、数据关联正确性。  
- **UI 集成层（中优先）**：验证 Earnings Modal 的数据映射、状态文案、交互入口。  
- **E2E 业务层（最高优先）**：覆盖真实用户路径，确保跨页面和跨接口闭环可用。  

## 3) 风险驱动重点

- **结算重复发奖风险**：final decision 重入是否导致重复写 `point_transactions`。  
- **关联错配风险**：transaction 回填 episode activity 时是否出现错行/漏行。  
- <span style="color: blue;">**规则遗漏风险**：只校验分差不校验 gate，可能导致错误发奖。</span>  
- <span style="color: blue;">**阈值回归风险**：实现阈值已收紧为 `±8`，旧用例仍按 `±15` 可能误判。</span>  
- **时间显示风险**：Today/Yesterday 在时区边界、跨天凌晨场景是否稳定。  
- **角色串线风险**：QA 角色样式是否错误落到 Innovator/Amplifier/Explorer 分支。  

## 4) 数据准备策略

- 构造 1 个 upload，含多 episode（建议 3~5 条），并准备 3~4 个 QA 用户。  
- <span style="color: blue;">预置 session gate：覆盖 `完全匹配 final_gate`、`单项 gate 不匹配` 两类。</span>  
- <span style="color: blue;">预置 session 分值：覆盖 `final_score-8`、`final_score`、`final_score+8`、越界值。</span>  
- 预置 episode 状态：可发奖、待发奖、missed 混合，便于校验 UI 三态。  
- 预置边界时间：当天、昨天、跨时区边界时间戳。  

## 5) 通过标准（Exit Criteria）

- 核心 E2E 用例（P0）100% 通过。  
- 奖励计算/发放/回填链路 0 个 blocker。  
- 关键展示项（points 汇总、列表状态、日期标签、角色态）与预期一致。  

---

## E2E 测试条目

以下条目按优先级组织，建议优先自动化 `P0`，`P1/P2` 可逐步补齐。

| Priority | Case ID | 测试场景 | 前置条件 | 测试步骤 | 预期结果 |
|---|---|---|---|---|---|
| P0 | P0-1 | 提交成功返回 | QA 用户可进入 `DataQAReview` 并提交评分 | 提交一次包含多个 episode 的 review | 提交接口成功，页面流程正常结束 |
| P0 | P0-2 | 生成 qa session 记录 | 完成一次 review 提交 | 查询 upload 对应 session 数据 | 新增一条 qa session 记录 |
| P0 | P0-3 | 写入 episode activity 记录 | 提交包含多个 episode 的 review | 查询 `data_qa_episode_activity` | 每个提交 episode 均有 activity 记录 |
| P0 | P0-4 | 第一轮即可产出 final score | upload 配置满足“单轮可决策”（如数据条件/规则允许） | 完成第一轮 QA 提交并查询 review 结果 | 第一轮后即生成 `final_decision.final_quality_score` |
| P0 | P0-5 | 第二轮产出 final score | upload 配置为第一轮不足以决策、第二轮可决策 | 连续完成两轮 QA 提交并查询 review 结果 | 第一轮无 final score；第二轮生成 final score |
| P0 | P0-6 | 第三轮产出 final score | upload 配置为前两轮不足以决策、第三轮可决策 | 连续完成三轮 QA 提交并查询 review 结果 | 第一/二轮无 final score；第三轮生成 final score |
| P0 | P0-7 | 触发 final decision 结算入口 | 当前 upload 距离达成 final decision 仅差最后一轮 | 提交最后一轮 review | 结算流程被触发 |
| P0 | P0-8 | 命中样本生成积分流水 | 已触发 final decision 且有命中样本 | 查询 `point_transactions` | 命中样本新增积分流水，`points_change=100` |
| P0 | P0-9 | activity 回填 transaction_id | 已产生积分流水 | 查询 `data_qa_episode_activity.point_transaction_id` | 命中记录均完成 transaction_id 回填 |
| <span style="color: blue;">P0</span> | <span style="color: blue;">P0-10</span> | <span style="color: blue;">gate 完全匹配且分差在阈值内可发奖</span> | <span style="color: blue;">已构造 final decision；样本 gate 全匹配且分差在 `±8` 内</span> | <span style="color: blue;">提交该样本评分并触发结算</span> | <span style="color: blue;">该样本被判定为可发奖（granted）</span> |
| <span style="color: blue;">P0</span> | <span style="color: blue;">P0-11</span> | <span style="color: blue;">gate 不匹配即不发奖（分数命中也不发）</span> | <span style="color: blue;">已构造 final decision；样本分差在 `±8` 内但至少 1 个 gate 与 final_gate 不一致</span> | <span style="color: blue;">提交该样本评分并触发结算</span> | <span style="color: blue;">该样本不发奖（missed）</span> |
| <span style="color: blue;">P0</span> | <span style="color: blue;">P0-12</span> | <span style="color: blue;">边界值 `-8` 命中奖励</span> | <span style="color: blue;">已构造 final score，当前样本偏差为 `-8` 且 gate 匹配</span> | <span style="color: blue;">提交该样本评分并触发结算</span> | <span style="color: blue;">该样本被判定为可发奖（granted）</span> |
| <span style="color: blue;">P0</span> | <span style="color: blue;">P0-13</span> | <span style="color: blue;">边界值 `+8` 命中奖励</span> | <span style="color: blue;">已构造 final score，当前样本偏差为 `+8` 且 gate 匹配</span> | <span style="color: blue;">提交该样本评分并触发结算</span> | <span style="color: blue;">该样本被判定为可发奖（granted）</span> |
| <span style="color: blue;">P0</span> | <span style="color: blue;">P0-14</span> | <span style="color: blue;">越界值 `-9` 不发奖</span> | <span style="color: blue;">已构造 final score，当前样本偏差为 `-9` 且 gate 匹配</span> | <span style="color: blue;">提交该样本评分并触发结算</span> | <span style="color: blue;">该样本不发奖（missed）</span> |
| <span style="color: blue;">P0</span> | <span style="color: blue;">P0-15</span> | <span style="color: blue;">越界值 `+9` 不发奖</span> | <span style="color: blue;">已构造 final score，当前样本偏差为 `+9` 且 gate 匹配</span> | <span style="color: blue;">提交该样本评分并触发结算</span> | <span style="color: blue;">该样本不发奖（missed）</span> |
| <span style="color: blue;">P0</span> | <span style="color: blue;">P0-16</span> | <span style="color: blue;">幂等性：重复结算不重复发奖</span> | <span style="color: blue;">upload 已完成过一次结算并发奖</span> | <span style="color: blue;">再次触发同 upload 结算路径</span> | <span style="color: blue;">不新增重复积分流水</span> |
| <span style="color: blue;">P0</span> | <span style="color: blue;">P0-17</span> | <span style="color: blue;">Earnings 汇总值正确</span> | <span style="color: blue;">已有 granted/pending/missed 混合数据</span> | <span style="color: blue;">打开 Earnings Modal</span> | <span style="color: blue;">`total_points`、`pending_points`、`episodes_scored` 与后端汇总一致</span> |
| <span style="color: blue;">P0</span> | <span style="color: blue;">P0-18</span> | <span style="color: blue;">Earnings 列表项字段正确</span> | <span style="color: blue;">earnings 明细已存在</span> | <span style="color: blue;">打开 Earnings Modal 列表</span> | <span style="color: blue;">每行 `episode_id/scenario/date/points` 显示正确</span> |
| <span style="color: blue;">P0</span> | <span style="color: blue;">P0-19</span> | <span style="color: blue;">DataQAReview 入口可打开 Earnings</span> | <span style="color: blue;">用户位于 `DataQAReview` 页面</span> | <span style="color: blue;">点击 View earnings 入口</span> | <span style="color: blue;">Earnings Modal 成功打开</span> |
| <span style="color: blue;">P0</span> | <span style="color: blue;">P0-20</span> | <span style="color: blue;">Success Modal 入口可打开 Earnings</span> | <span style="color: blue;">review 提交成功并出现 Success Modal</span> | <span style="color: blue;">点击 View earnings 按钮</span> | <span style="color: blue;">Earnings Modal 成功打开</span> |
| P1 | P1-1 | QA 角色文案展示正确 | 账号角色为 `qa` | 进入 QA Review 页面 | 显示 `Validator` |
| P1 | P1-2 | Senior QA 角色文案展示正确 | 账号角色为 `senior qa` | 进入 QA Review 页面 | 显示 `Senior Validator` |
| P1 | P1-3 | Expert QA 角色文案展示正确 | 账号角色为 `expert qa` | 进入 QA Review 页面 | 显示 `Expert Validator` |
| P1 | P1-4 | QA 页面隐藏 spots/pips | QA 账号登录 | 查看 validator status 区域 | 不显示 spots/pips，仅显示 reviews completed |
| P1 | P1-5 | 日期标签 Today 正确 | 准备当天 earnings 数据 | 打开 Earnings Modal | 当天记录显示 `Today` |
| P1 | P1-6 | 日期标签 Yesterday 正确 | 准备昨天 earnings 数据 | 打开 Earnings Modal | 昨天记录显示 `Yesterday` |
| P1 | P1-7 | 长列表 body 可滚动 | 构造 30+ 条 earnings 明细 | 打开 Earnings Modal 并滚动 | 列表 body 可滚动 |
| P1 | P1-8 | 长列表 header 固定可见 | 构造 30+ 条 earnings 明细 | 打开 Earnings Modal 并滚动 | 列表 header 保持可见 |
| P1 | P1-9 | 未映射 failed check 显示 `E-000` | 构造未知 failed check | 查看 UploadDashboard rejection rows | 展示 `E-000` |
| P1 | P1-10 | processing error 显示 `E-000` | 构造 processing error | 查看 UploadDashboard rejection rows | 展示 `E-000` |
| P1 | P1-11 | Earnings 接口失败提示正确 | 模拟 earnings 接口失败/超时 | 打开 Earnings Modal | 展示错误提示文案 |
| P1 | P1-12 | Earnings 空数据提示正确 | 接口返回空列表 | 打开 Earnings Modal | 展示 `No reviews yet` |
| P2 | P2-1 | 无 token 场景处理 | 未登录或清空 token | 访问 QA Review 与 earnings 入口 | 请求被拒绝且前端提示合理 |
| P2 | P2-2 | 过期 token 场景处理 | 使用过期 token | 访问 QA Review 与 earnings 入口 | 请求被拒绝且前端提示合理 |
| P2 | P2-3 | 非 QA 角色访问控制 | 非 QA 账号登录 | 访问 QA Review 与 earnings 入口 | 访问结果符合权限设计且提示合理 |
| P2 | P2-4 | 并发提交稳定性 | 多 QA 用户并发提交同一 upload | 并发完成最后几轮评分 | final decision 与发奖结果稳定，无重复无丢失 |

---

## 自动化落地建议（简版）

- <span style="color: blue;">**API 自动化**：优先覆盖 `P0-2` ~ `P0-16`，直接断言数据库结果与接口返回。</span>  
- <span style="color: blue;">**前端 E2E（Playwright/Cypress）**：优先覆盖 `P0-17` ~ `P0-20` 与 `P1-1` ~ `P1-12`。</span>  
- **数据校验脚本**：对账 `session -> activity -> point_transactions -> earnings API` 四层一致性。  
- **回归策略**：PR 阶段跑 P0；夜间构建跑 P0+P1；并发与权限场景放 nightly/weekly。  
