# Sprint 22 Private Arm 与 Marketing Commit 改动说明

> 分析日期：2026-07-30  
> 前端仓库：`app-prismax-rp`  
> 后端仓库：`app-prismax-rp-backend`

## 1. Commit 范围

| 仓库 | Commit | Commit message | 改动规模 |
| --- | --- | --- | --- |
| 前端 | `1edc2433462a7093d06119e4bad4ad46ae8d58c6` | `changed back private arm` | 5 个文件，`+16 / -61` |
| 后端 | `5e0d453f0fdcccafeb9d5839ea618796f58519ac` | `allow cors for markerting` | 1 个文件，`+9 / -1` |
| 后端 | `be89b57a0bbf40ec2066bf48fc404cdeacb685dc` | `changed back private arm` | 4 个文件，`+49 / -233` |

后端 `be89b57` 的直接父提交是 `5e0d453`，因此两个后端 Commit 是连续改动。

## 2. 总体结论

本次改动包含两部分：

1. 为 PrismaX Marketing 网站开放后端 CORS，并支持 Discord、Twitter OAuth 登录后跳回 Marketing Account 页面。
2. 撤回 Teleop Cup Arm 活动功能，将前端入口恢复为 Private Arm，同时删除活动专属限次、积分和排行榜逻辑。

## 3. 前端改动

### `1edc2433462a7093d06119e4bad4ad46ae8d58c6`

- 将机器人入口的 slug 从 `teleop-cup-arm` 改回 `private-arm`。
- 将 Teleop Cup Arm 卡片恢复为 Reserved Private Arm：
  - 使用普通机械臂图片和 Reserved Banner。
  - 描述改为仅供 VIP、合作伙伴和特殊活动使用，需要 Access Code。
  - 删除世界杯足球主题图片和对应 CSS。
- 删除右侧面板中的 **Cup Leaderboard** Tab。
- 删除对 `/tele_op/teleop_cup_leaderboard` 的请求；除 Monad 外统一使用普通 `/tele_op/leaderboard`。
- Teleop Cup Arm 不再显示 Session Complete Modal，仅 `arena-arm` 保留该弹窗。
- `TeleOpRightPanel` 不再接收 `robotSlug` 参数。
- 机器人名称改为直接读取后端返回的 `robotData.robotName`，不再使用前端配置名称作为 fallback。

## 4. 后端改动

### `5e0d453f0fdcccafeb9d5839ea618796f58519ac`

在 `app_prismax_user_management/app.py` 中为以下 Marketing 来源增加 CORS：

- `https://www.prismax.ai`
- `https://beta-www.prismax.ai`
- Marketing 正式和 Beta Cloud Run 域名
- `http://localhost:3001`
- `http://127.0.0.1:3001`

原有 App、Beta App 和本地 `3000` 来源继续保留。

### `be89b57a0bbf40ec2066bf48fc404cdeacb685dc`

#### Private Arm / Teleop Cup 回退

- 删除 `teleop-cup-arm` 活动机械臂配置。
- 删除活动每日控制次数限制：
  - Amplifier Member：每天 3 次。
  - Innovator Member：每天 6 次。
- Teleop Cup Arm 不再启用 Vision，只有 `arena-arm` 启用。
- 创建控制历史时不再写入 `campaign_key`。
- Session 完成状态统一返回普通 `reward_points`，不再针对活动返回 `campaign_points`。
- Session 奖励计算不再生成或累加 `campaign_points`。
- 删除 Teleop Cup 排行榜更新接口：
  - `POST /tele_op/teleop_cup_leaderboard/update`
- 删除 Teleop Cup 排行榜查询接口：
  - `GET /tele_op/teleop_cup_leaderboard`

此次提交没有删除数据库中的活动字段或排行榜表，只是业务代码停止使用相关字段和接口。

#### Marketing OAuth

Discord 和 Twitter OAuth 增加以下允许回跳的 Account 页面：

- PrismaX Marketing 正式站和 Beta 站。
- Marketing 正式和 Beta Cloud Run 地址。
- `localhost:3001/account`。
- `127.0.0.1:3001/account`。

同时修正 Twitter OAuth 的默认 Beta Return URL：未配置环境变量时，改为使用 `DEFAULT_TWITTER_BETA_RETURN_URL`，不再错误地回退到正式站地址。

## 5. 前后端对应关系

| 功能 | 前端 `1edc243` | 后端 `be89b57` |
| --- | --- | --- |
| Teleop Cup 入口 | 改回 Private Arm | 删除活动机械臂特殊逻辑 |
| Cup Leaderboard | 删除 Tab 和请求 | 删除查询与更新接口 |
| 活动限次 | 不再展示活动说明 | 删除每日 3/6 次限制 |
| 活动积分 | 不再展示活动排行榜 | 删除 `campaign_points` 计算和返回 |
| Session Complete | 仅 Arena Arm 显示 | Teleop Cup 不再启用 Vision |

## 6. QA 验证重点

- Marketing 正式站、Beta 站及 Cloud Run 环境可以正常调用用户服务，不出现 CORS 拦截。
- Marketing 本地 `3001` 环境可以正常调用用户服务。
- Discord 和 Twitter OAuth 完成后只能跳转到允许的 Account URL。
- Twitter Beta OAuth 默认跳回 Beta Account 页面，而不是正式站。
- Teleop 选择页显示 Private Arm，不再显示 Teleop Cup Arm。
- Private Arm 显示 Reserved Banner、正确名称和说明。
- Private Arm 页面不显示 Cup Leaderboard。
- 普通排行榜和 Monad 排行榜仍可正常加载。
- Private Arm 不再受到 Amplifier 每天 3 次、Innovator 每天 6 次的活动限制。
- Private Arm Session 不再产生或返回活动积分。
- Arena Arm 的 Vision 和 Session Complete Modal 不受此次回退影响。

## 7. E2E 测试用例

### 7.1 测试数据与环境准备

| 项目 | 要求 |
| --- | --- |
| 环境 | Marketing 正式/Beta 环境、App 正式/Beta 环境；如验证本地 CORS，准备 `localhost:3001` |
| 用户 | 普通用户、Amplifier Member、Innovator Member；至少一个已绑定 Discord/Twitter 的测试用户 |
| 机器人 | `private-arm`、`arena-arm` 均已在 `robot_status` 配置且可进入队列；准备一个 Monad 场景用于排行榜回归 |
| Session | Private Arm 可连续完成至少 7 次短 Session；Arena Arm 可完成一次正常 Session |
| 工具 | 浏览器 DevTools/Network；能够检查请求 Origin、响应状态、CORS Header、OAuth 回跳 URL 和 Session 完成响应 |

### 7.2 Marketing CORS

| ID | 优先级 | 场景 | 前置条件 | 测试步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| CORS-01 | P0 | Marketing 正式站调用用户服务 | 打开 `https://www.prismax.ai` | ① 从 Marketing 页面触发 Account/用户信息请求；② 检查 Network 请求和响应。 | 请求成功；浏览器无 CORS Error；响应允许 `https://www.prismax.ai` Origin；页面正确展示结果。 |
| CORS-02 | P0 | Marketing Beta 站调用用户服务 | 打开 `https://beta-www.prismax.ai` | 重复 CORS-01。 | Beta Origin 被允许，请求及页面功能正常。 |
| CORS-03 | P1 | Marketing Cloud Run 域名调用用户服务 | 分别打开正式/Beta 的两类 Cloud Run 域名 | 从每个域名触发同一用户服务请求。 | 4 个已配置 Cloud Run Origin 均被允许；无 CORS Error。 |
| CORS-04 | P1 | 本地 3001 调用用户服务 | Marketing 前端运行于 `localhost:3001` 和 `127.0.0.1:3001` | 分别从两个地址触发用户服务请求。 | 两个 Origin 均被允许，请求成功。 |
| CORS-05 | P0 | 原 App Origin 回归 | 打开 App 正式站、Beta 站及本地 3000 | 分别触发原有用户服务请求。 | 原有 Origin 继续被允许，功能无回归。 |
| CORS-06 | P0 | 未授权 Origin 被拒绝 | 准备一个不在 allowlist 的测试 Origin | 携带该 Origin 发送实际请求和 OPTIONS Preflight。 | 响应不授予该 Origin；浏览器阻止跨域读取；服务端不返回通配符 `*`。 |
| CORS-07 | P1 | Preflight Header/Method | 从 Marketing Origin 触发带 Authorization/JSON 的请求 | 检查 OPTIONS 和后续实际请求。 | OPTIONS 成功；允许所需 Method/Header；随后实际请求成功且不会重复失败。 |

### 7.3 Discord 与 Twitter OAuth

| ID | 优先级 | 场景 | 前置条件 | 测试步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| OAUTH-01 | P0 | Marketing 正式站 Discord 登录回跳 | 测试用户可登录 Discord | ① 从 `www.prismax.ai/account` 发起 Discord OAuth；② 完成授权。 | 登录成功；最终返回 `https://www.prismax.ai/account`；用户状态正确刷新。 |
| OAUTH-02 | P0 | Marketing Beta 站 Discord 登录回跳 | 同上 | 从 `beta-www.prismax.ai/account` 发起并完成授权。 | 最终返回 Beta Account 页面，不跳到正式站或 App 站。 |
| OAUTH-03 | P0 | Marketing 正式站 Twitter 登录回跳 | 测试用户可登录 Twitter | 从 `www.prismax.ai/account` 发起并完成 Twitter OAuth。 | 登录成功并返回正式 Marketing Account 页面。 |
| OAUTH-04 | P0 | Twitter Beta 默认回跳 | Beta 环境未设置 `TWITTER_BETA_RETURN_URL` Override | 从 Beta Marketing Account 发起并完成 Twitter OAuth。 | 默认返回 `https://beta-www.prismax.ai/account`，不错误跳转至正式站。 |
| OAUTH-05 | P1 | Cloud Run 与本地 OAuth 回跳 | 使用已加入 allowlist 的 Cloud Run/3001 Account URL | 分别发起 Discord 和 Twitter OAuth。 | OAuth 完成后返回原始、已允许的 Account URL。 |
| OAUTH-06 | P0 | 非法 Return URL | 构造未授权域名作为 Return URL | 发起 Discord/Twitter OAuth，并完成或检查初始化响应。 | 非法 URL 不被接受；不会重定向到攻击者域名。 |
| OAUTH-07 | P0 | 相似域名与路径绕过 | 使用 `prismax.ai.evil.com`、`evil.com/?next=https://www.prismax.ai/account`、非 `/account` 路径等 Return URL | 分别发起 OAuth。 | 所有非精确 allowlist URL 均被拒绝或安全回退，不发生 Open Redirect。 |
| OAUTH-08 | P1 | OAuth State 防篡改回归 | 已生成一次有效 OAuth State | 修改 State 中的 Return URL、使 State 过期或重复使用。 | 篡改、过期或重放的 State 被拒绝；不会登录或跳转到未授权地址。 |
| OAUTH-09 | P1 | 原 App OAuth 回归 | App 正式/Beta 环境可用 | 分别从 `app.prismax.ai/account` 和 `beta-app.prismax.ai/account` 完成 Discord/Twitter OAuth。 | 原有 App OAuth 登录和回跳保持正常。 |

### 7.4 Private Arm 前端与流程

| ID | 优先级 | 场景 | 前置条件 | 测试步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| ARM-01 | P0 | Private Arm 卡片展示 | 后端返回 slug 为 `private-arm` 的机器人 | 打开 Teleop 机器人选择页。 | 显示 Private Arm 卡片、普通机械臂图片、Reserved Banner 和 Reserved Access 描述；不出现 Teleop Cup、World Cup 或足球主题内容。 |
| ARM-02 | P0 | 机器人名称取自后端 | 后端为 Private Arm 配置明确的 `robotName` | 打开选择页并等待机器人数据加载完成。 | 卡片名称与后端 `robotName` 一致且不为空；无 `undefined`、空标题或旧的 Teleop Cup 名称。 |
| ARM-03 | P0 | Private Arm 进入队列 | 用户拥有 Private Arm 访问资格 | 点击 Private Arm，完成必要授权并进入队列。 | 前端使用 `private-arm` 对应的 Robot ID；成功进入正确队列；无旧 `teleop-cup-arm` 请求或找不到机器人的错误。 |
| ARM-04 | P0 | Cup Leaderboard 已移除 | 已进入 Private Arm 页面 | 检查桌面端和移动端右侧面板/Tab。 | 不显示 **Cup Leaderboard**；DOM 中无可操作的 Cup Tab；不会请求 `/tele_op/teleop_cup_leaderboard`。 |
| ARM-05 | P0 | 普通排行榜回归 | 普通排行榜有测试数据 | 打开 Private Arm 的排行榜区域并检查 Network。 | 请求 `/tele_op/leaderboard`；数据、当前用户和排名正常展示。 |
| ARM-06 | P1 | Monad 排行榜回归 | 进入 Monad 排行榜场景 | 打开 Monad 排行榜并检查 Network。 | 仍请求 `/tele_op/monad_leaderboard`，数据正常展示。 |
| ARM-07 | P1 | Live Chat 与 Tab 切换回归 | 已进入 Private Arm 页面 | 在 Queue/Controls、Live Chat、Leaderboard 间切换并调整窗口尺寸。 | Tab 可正常切换；滑块位置正确；无空白面板、布局错位或前端异常。 |

### 7.5 Private Arm 限次、积分与接口

| ID | 优先级 | 场景 | 前置条件 | 测试步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- |
| ARM-08 | P0 | Amplifier 不再受每天 3 次限制 | Amplifier Member；当天可完成至少 4 次 Private Arm Session | 在同一 UTC 日期内依次开始第 1～4 次控制。 | 第 4 次仍可正常进入队列并控制；不返回“reached 3”或活动限次 403。 |
| ARM-09 | P0 | Innovator 不再受每天 6 次限制 | Innovator Member；当天可完成至少 7 次 Private Arm Session | 在同一 UTC 日期内依次开始第 1～7 次控制。 | 第 7 次仍可正常进入队列并控制；不返回活动限次 403。 |
| ARM-10 | P0 | Private Arm 使用普通奖励 | 完成一次可获得奖励的 Private Arm Session | ① 完成 Session；② 查询 Session Complete Status 和用户积分。 | 返回并累加普通 `reward_points`；奖励规则与普通机械臂一致；前端不展示 Campaign Points。 |
| ARM-11 | P1 | 新控制历史不依赖活动字段 | 可检查测试环境数据库或内部日志 | 完成一次 Private Arm Session 并查看对应控制历史。 | Session 创建和结算成功；流程不依赖 `campaign_key`/`campaign_points`；无数据库字段或 SQL Error。 |
| ARM-12 | P0 | 旧 Cup 排行榜接口已下线 | 可直接访问后端 API | 分别调用 `GET /tele_op/teleop_cup_leaderboard` 和带/不带 Token 的 `POST /tele_op/teleop_cup_leaderboard/update`。 | 两个旧路由均不可用（预期 404）；不会返回旧排行榜数据或执行更新。 |
| ARM-13 | P0 | Arena Arm Vision 回归 | Arena Arm 在线且可控制 | 开始并完成一次 Arena Arm Session。 | Vision 仍启用；完成后正常显示 Session Complete Modal；奖励与完成状态正常。 |
| ARM-14 | P1 | Private Arm 不触发 Arena 专属完成弹窗 | 完成一次 Private Arm Session | 等待 Session 结束并观察 UI。 | 不显示 Arena Arm 的 Session Complete Modal；页面无报错，后续可正常返回或再次排队。 |
| ARM-15 | P1 | 并发排队回归 | 两个有 Private Arm 权限的测试用户 | 两个用户同时加入 Private Arm 队列。 | 两者获得唯一且顺序正确的队列位置；删除活动逻辑后未引入重复位置或 500 Error。 |
