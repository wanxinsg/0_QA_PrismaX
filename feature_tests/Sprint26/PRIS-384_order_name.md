# PRIS-384 订单名称：Commit 逻辑分析与测试用例

> 分析日期：2026-10-14（UTC+8）  
> 范围：`app-prismax-rp-backend`、`app-prismax-rp`、`prismax-marketing-rp`  
> 三条功能线都已合进各自 `testing`。

JSON 字段叫 `name`。数据库列叫 `data_orders.order_name`。

| 仓库 | Commit | 时间（作者时区 / 北京时间） | Author | Message |
| --- | --- | --- | --- | --- |
| backend | `ca99a8874842671aa8df8689a584b4ca5e0f1072` | 2026-10-10 01:35 `-0700` / 10-10 16:35 | Aparna Rangamani | `PRIS-384: save wip` |
| backend | `b20f8ec03a6eed933dfadb0d0fc98a59d574c2c9` | 2026-10-13 15:13 `-0700` / 10-14 06:13 | Aparna Rangamani | `PRIS-384: improve duplicate order name error handling` |
| admin 前端 | `7139dae180885c971dfb13f96cdd89996c39e577` | 2026-10-13 15:09 `-0700` / 10-14 06:09 | Aparna Rangamani | `PRIS-384: add order name support` |
| 营销站 | `9db9e8f9a5dc1308eedbe70a7b2b2fbe91231bf4` | 2026-10-13 15:15 `-0700` / 10-14 06:15 | Aparna Rangamani | `PRIS-384: add order name support` |

`ca99a88` 已经是 `testing` 的祖先，负责加列、校验和接口。今天合进去的 `b20f8ec` 把重名从数据库冲突改成创建/更新前的明确 `409`。两个前端在同一天加上表单、列表和详情展示。

---

## 1. 业务目标

订单除了 `ORD-<数字>`，还要有一个给人看的名称：

- 新建订单必须填名称，草稿也要填。最长 80 个字符。
- 同一组织内名称不区分大小写，也不能只靠空格区分。取消、完成的订单仍然占着这个名字。
- 不同组织可以起同样的名字。
- 迁移前已经存在的订单保持 `order_name = NULL`，列表退回显示订单号。下次编辑时必须补上名称。

同一批前端提交还把机器人选项里的 `yam` 排到第一位，新建时默认选中它。

---

## 2. 数据规则

迁移脚本：`app_prismax_user_management/order_management/sql/20261010_data_orders_order_name.sql`。测之前要先跑过。

```text
请求里的 name
    │  连续空白（含 Tab、换行）压成一个空格，再去掉首尾空白
    ▼
validate_order_name
    │  空          → 400  order_name_required
    │  超过 80 字  → 400  order_name_too_long
    ▼
_require_unique_order_name
    │  同一 organization_id
    │  LOWER(order_name) 相同
    │  更新时排除当前订单 id
    │  命中        → 409  duplicate_order_name，不写库
    ▼
data_orders.order_name
    │  可空
    │  CHECK：NULL，或 char_length 在 1 到 80
    │  唯一索引：(organization_id, lower(order_name)) WHERE order_name IS NOT NULL
    ▼
响应字段 name（可能是 null）
```

唯一性不看状态。`draft`、`cancelled`、`complete` 都占名字。`NULL` 不进唯一索引，所以多张历史订单可以同时没有名称。

应用层先查再写。查到重复时返回：

```text
HTTP 409
code: duplicate_order_name
msg:  The order name "<规范化后的名称>" has already been used in this organization. Choose a different name.
```

响应信封是 `{"success": false, "code": "...", "msg": "..."}`。管理端和营销站都把 `msg` 显示出来。

---

## 3. 后端

### 3.1 规范化

`validate_order_name`：

| 输入 | 结果 |
| --- | --- |
| `null`、`""`、`"   "` | `400`，`order_name_required`，文案 `name is required` |
| `"  Kitchen \t manipulation  "` | 存成 `Kitchen manipulation` |
| 正好 80 个字符 | 通过 |
| 规范化之后超过 80 | `400`，`order_name_too_long`，文案 `name must be 80 characters or fewer` |

长度按字符算，不是字节。80 个汉字可以通过。

### 3.2 创建

两条创建接口都走 `_order_payload(..., require_robot_type=True)`，所以名称和机器人都必填：

| 调用方 | 接口 |
| --- | --- |
| 组织 owner | `POST /api/orders` |
| Admin | `POST /api/admin/organizations/<organization_id>/orders` |

`as_draft: true` 仍然要名称。空名称在进库之前就被拒绝，`create_order` 不会被调用。

写入前按组织做不区分大小写的查重。命中则 `409`，`INSERT` 不执行。

### 3.3 更新

| 调用方 | 接口 |
| --- | --- |
| 组织 owner | `PATCH /api/orders/<ORD-id>` |
| Admin | `PATCH /api/admin/orders/<ORD-id>` |

请求里没有 `name` 时，沿用订单上已有的名称。已有名称是 `null`、请求里又没给名称，返回 `400` `order_name_required`。

查重带 `id <> 当前订单`。改别的字段、名称保持不变，可以通过。改成组织里另一张订单的名称（大小写不同也算）返回 `409`，`UPDATE` 不执行。

### 3.4 读

列表和详情的 `name` 直接来自 `order_name`。没有名称时是 `null`，不是空字符串。

创建、更新的 history `details` 里没有写入名称，只有状态、时薪、机器人。名称变更不要到订单历史里找。

---

## 4. 管理端 `7139dae`

页面：Admin Orders。

### 4.1 表单

创建和编辑都有必填 **Order name**，`maxLength=80`，占位符 `e.g. Kitchen manipulation — Q3 training set`。

提交前把连续空白压成一个空格。压完是空的，表单内出现 `Enter an order name.`（`role="alert"`），不发请求，Cancel / Save order 仍在。输入框一改，这条错误清掉。

本地校验失败留在编辑器里。接口失败走另一条路：顶部通知显示 `msg`，然后编辑器关掉。重名就是这条路，文案是第 2 节那句 `The order name "..." has already been used...`。用户要改名字必须重新打开表单。

编辑标题是 `Edit <名称>`，没有名称时是 `Edit <ORD-id>`。编辑时组织下拉禁用。

### 4.2 列表、详情、确认框

| 位置 | 有名称 | 没有名称 |
| --- | --- | --- |
| 列表主标题 | 名称，旁边小字订单号 | 只显示订单号，不重复两遍 |
| 列表副标题 | `组织名 · 第一个任务` | 同样，组织不再当主标题 |
| 详情标题 | 名称 + 订单号 | 只显示订单号 |
| Order summary | `Order name` 一行，值是名称 | 值是 `—` |
| 取消确认标题 | `Cancel <名称> (<ORD-id>)?` | `Cancel <ORD-id>?` |

### 4.3 发票

开票勾选行：订单号是粗体，名称有则显示为 `<名称> · <组织>`，没有名称则只有组织。

已开发票表：有名称时名称在上、订单号是小字；没有名称，或这张发票里的订单不在当前已加载列表里，只显示订单号。

Mark as complete 确认文案里，能对上名称的写成 `<名称> (<ORD-id>)`，对不上的仍是订单号。例如 `Orders to complete: Pilot run (ORD-1080), ORD-1081.`

发票 PDF 本身是管理员上传的文件，这次没有把名称写进 PDF。

### 4.4 机器人默认项

`product_name` 去掉首尾空白后等于 `yam`（不区分大小写）的机器人移到第一位。创建订单时默认选中这一位，提交的 `robot_type_id` 是它的 `machine_id`。列表里没有 YAM 时，顺序和默认项保持接口原样。

---

## 5. 营销站 `9db9e8f`

页面：客户订单工作台 `OrderWorkspace`。

### 5.1 表单

**Order name** 必填，`maxLength=80`，同一句占位符。旁边的说明是：`How this order appears in your orders list and invoices.`

空名称（含纯空白）停在表单里，文案 `Enter an order name.`，不发请求。保存草稿和正式提交都走这个校验。

接口失败时用 toast 显示 `msg`，表单留在当前页，已填内容还在。这和管理端不同：管理端会把编辑器关掉。

同一张表单把原来的说明小字改成了 info tooltip：

| 字段 | tooltip |
| --- | --- |
| Robot | `Demonstrations are captured on the selected robot platform.` |
| Proposed hourly rate | `Rate is negotiated. Leave blank or propose a figure — PrismaX will confirm the agreed rate before production begins.` |
| Task list & demos | 说明要分享可查看的表格或 Drive，用来框定生产范围 |

新建时机器人同样把 `yam` 放到第一位并默认选中。编辑沿用订单上的 `robot_type_id`。

### 5.2 列表和详情

| 位置 | 有名称 | 没有名称 |
| --- | --- | --- |
| 列表 Order 列 | 名称加粗，下面小字订单号，`title` 是完整名称 | 只显示订单号 |
| 详情标题 | 名称，旁边订单号 | 只显示订单号 |
| 编辑页标题 | `Edit <名称>` | `Edit <ORD-id>` |

列表筛选（All / Active / Complete / Drafts / Cancelled）不按名称搜索，只按状态。

### 5.3 发票列表没有接名称

营销站发票表的 Orders included 仍是 `(invoice.order_ids || []).join(", ")`，只显示 `ORD-...`。名称出现在订单列表和详情标题，不出现在这张发票表里。tooltip 里的 “invoices” 指的是这个名称将来怎么被认出，不是这张表已经改了。

---

## 6. 已知实现口径

执行下面的用例时按这些判定，不要当成缺陷：

1. 重名比较发生在空白压缩之后，并且不区分大小写。`Kitchen run`、`kitchen RUN`、`  Kitchen   run  ` 互相冲突。
2. 取消和已完成的订单仍占名称。唯一索引和查重 SQL 都没有排除状态。
3. 另一个组织可以使用完全相同的名称。
4. 编辑自己并保持原名可以通过。只改大小写也可以，库里的值会变成新的写法。
5. 历史订单的 `name` 是 `null`。两个前端都退回显示 `ORD-id`。
6. 管理端任何保存失败都会关掉编辑器，包括重名、网络错误。营销站保存失败留在表单上。
7. 营销站发票表只显示订单号。Admin 发票表和完成确认才会把名称和订单号放在一起。
8. 订单历史事件不记录名称。
9. 两个前端的 `maxLength=80` 让浏览器挡掉第 81 个字符。超过 80 的拒绝要用接口直接打。
10. 列表没有按名称搜索。管理端筛选仍是组织和状态，营销站筛选仍是状态。

---

## 7. 测试数据与环境

- 环境已执行 `20261010_data_orders_order_name.sql`。未执行时创建会在写库阶段失败，不会走到 `duplicate_order_name`。
- 一个组织 owner 账号，能进营销站订单页。
- 一个 Admin 账号，能进 Admin Orders。
- 同一组织里准备：一张已命名订单、一张 `name` 为 `null` 的历史订单、一张已取消但仍占用某个名称的订单。
- 另一个组织里有一张同名订单，用来确认跨组织不冲突。
- 机器人目录里同时有 Piper 和 YAM，且接口顺序不是 YAM 在前。
- 浏览器：桌面 Chrome。抓包看 `POST /api/orders`、`PATCH /api/orders/<id>`、`POST /api/admin/organizations/<id>/orders`、`PATCH /api/admin/orders/<id>`。

---

## 8. 测试用例

优先级：P0 必测 / P1 重要 / P2 补充。

| ID | 模块 | 优先级 | 场景 | 前置条件 | 操作步骤 | 预期结果 |
| --- | --- | --- | --- | --- | --- | --- |
| PRIS-384-001 | 营销站创建 | P0 | 新建订单必填名称 | Owner 已登录，组织已选 | 打开 New production order，不填名称，其余必填项填完，点提交 | 表单留在原地，出现 `Enter an order name.`；Network 没有 `POST /api/orders` |
| PRIS-384-002 | 营销站创建 | P0 | 纯空白不算名称 | 同上 | 名称填三个空格，点 Save draft | 同样出现 `Enter an order name.`；不发请求 |
| PRIS-384-003 | 营销站创建 | P0 | 空白被压缩后入库 | 组织内还没有 `Kitchen manipulation` | 名称填 `  Kitchen   manipulation  `，填完机器人、任务、截止日期，提交 | `201`；请求体 `name` 为 `Kitchen manipulation`；详情标题是这个名称，旁边有 `ORD-` 单号 |
| PRIS-384-004 | 营销站创建 | P0 | 草稿也要名称 | 同上 | 名称留空，点保存草稿 | 不发请求，表单内提示要填名称 |
| PRIS-384-005 | 营销站创建 | P0 | 同组织重名 | 该组织已有 `Cable insertion pilot` | 再新建一张，名称用同样文字，提交 | toast 为 `The order name "Cable insertion pilot" has already been used in this organization. Choose a different name.`；表单不关闭，已填内容还在；库里没有新订单 |
| PRIS-384-006 | 营销站创建 | P0 | 大小写和空格算重名 | 已有 `Kitchen run` | 分别试 `kitchen RUN` 和 `  Kitchen   run ` | 两次都是 `409` `duplicate_order_name`；toast 里引号中的名称是压缩后的写法 |
| PRIS-384-007 | 营销站创建 | P1 | 跨组织可以同名 | 组织 A 已有该名称；用组织 B 的 owner | 在组织 B 用同一名称提交 | `201`，两张订单都在 |
| PRIS-384-008 | 营销站创建 | P1 | 已取消订单仍占名 | 同组织有一张已取消订单，名称是 `Retired pilot` | 新建时使用 `Retired pilot` | `409`，不能创建 |
| PRIS-384-009 | 营销站创建 | P1 | 80 个字符可以通过 | 该名称未被占用 | 输入正好 80 个字符并提交 | 创建成功；列表和详情显示完整 80 字；列表单元格 `title` 是这 80 字 |
| PRIS-384-010 | 营销站创建 | P1 | 第 81 个字符进不了输入框 | 打开新建表单 | 连续输入或粘贴 81 个字符 | 输入框停在 80。接口另测：直接 `POST /api/orders`，`name` 为 81 个 `x`，返回 `400` `order_name_too_long`，`msg` 为 `name must be 80 characters or fewer` |
| PRIS-384-011 | 营销站创建 | P2 | 80 个汉字 | 名称未被占用 | 提交 80 个汉字的名称 | `201`。81 个汉字的直接接口调用返回 `400` `order_name_too_long` |
| PRIS-384-012 | 营销站列表和详情 | P0 | 列表有名称 | 一张有名称、一张 `name=null` | 打开订单列表 | 有名称的行是名称加粗、下面小字订单号；空名行只有订单号 |
| PRIS-384-013 | 营销站列表和详情 | P0 | 详情标题 | 打开有名称的订单，再打开空名订单 | 看详情标题 | 有名称：名称和订单号同时可见。空名：标题只有订单号，没有空白名称 |
| PRIS-384-014 | 营销站列表和详情 | P0 | 编辑保持原名 | 订单处于 owner 可编辑状态（draft / submitted / pending_approval） | 打开编辑，不改名称，改 notes 后保存 | `200`；请求带原来的 `name`；toast `Order updated.`；详情名称不变 |
| PRIS-384-015 | 营销站列表和详情 | P0 | 编辑改成别人的名称 | 同组织另一张订单已占用目标名 | 把当前订单改成那个名称并保存 | toast 为重名文案；表单仍打开；刷新后名称还是旧的 |
| PRIS-384-016 | 营销站列表和详情 | P1 | 只改自己的大小写 | 当前名称是 `Kitchen run` | 改成 `kitchen run` 并保存 | 保存成功；之后列表显示新的大小写 |
| PRIS-384-017 | 营销站列表和详情 | P1 | 编辑历史空名订单 | 找一张 `name=null`、且 owner 仍可编辑的订单 | 打开编辑，不填名称就保存；再填一个未占用的名称保存 | 第一次停在表单并提示 `Enter an order name.`。第二次成功，列表从只显示单号变成显示名称 |
| PRIS-384-018 | 营销站列表和详情 | P1 | 接口漏传名称 | 用接口 `PATCH /api/orders/<id>`，body 只有 `notes` | 对有名称的订单打一次；对 `name=null` 的订单再打一次 | 有名称：`200`，名称不变。空名：`400` `order_name_required` |
| PRIS-384-019 | 营销站列表和详情 | P2 | 状态筛选不按名称 | 列表里有多张不同状态的命名订单 | 切 Active、Drafts、Cancelled | 每行仍按 PRIS-384-012 显示名称；筛选结果只跟状态有关 |
| PRIS-384-020 | 营销站机器人和说明 | P1 | YAM 排第一并默认选中 | 机器人接口把 Piper 排在 YAM 前面 | 打开新建订单，看 Robot 按钮，不改选择直接提交 | YAM 在第一位且为选中态；请求 `robot_type_id` 是 YAM 的 `machine_id` |
| PRIS-384-021 | 营销站机器人和说明 | P2 | 没有 YAM | 目录里没有 product name 为 yam 的机器人 | 打开新建订单 | 顺序与接口一致，默认仍是列表第一项 |
| PRIS-384-022 | 营销站机器人和说明 | P2 | tooltip | 打开新建或编辑表单 | 看 Order name、Robot、时薪、任务链接旁的说明 | 悬停或聚焦 info 图标能看到第 5.1 节的四句说明；这些说明不再是字段下方的常驻小字 |
| PRIS-384-023 | 管理端 | P0 | 管理端创建必填名称 | Admin 已登录 Orders | Create order，名称留空或只填空格，其余填完，点 Save order | 编辑器不关；alert 为 `Enter an order name.`；没有创建请求；Cancel 和 Save order 仍在 |
| PRIS-384-024 | 管理端 | P0 | 管理端压缩空白 | 该组织没有 `Cable insertion pilot` | 名称填 `  Cable insertion   pilot `，选组织和任务，保存 | 请求 `name` 为 `Cable insertion pilot`；成功通知 `Order created.`；编辑器关闭 |
| PRIS-384-025 | 管理端 | P0 | 管理端重名会关编辑器 | 同组织已有该名称 | 再用这个名称创建 | 通知原文是 `The order name "<名称>" has already been used in this organization. Choose a different name.`；Save order 和名称输入框消失；订单列表没有新增 |
| PRIS-384-026 | 管理端 | P0 | 列表和详情 | 准备有名称和 `name=null` 各一张 | 看列表，再打开有名称的详情 | 有名称：主标题是名称，小字是单号，副标题以组织名开头。空名：主标题只有单号。详情标题含名称和单号；summary 有 `Order name` |
| PRIS-384-027 | 管理端 | P0 | 空名详情 | 打开 `name=null` 的订单 | 看标题和 summary | 标题只有订单号；Order name 的值是 `—` |
| PRIS-384-028 | 管理端 | P1 | 取消确认带名称 | 有名称的订单允许取消 | 点 Cancel order | 确认标题是 `Cancel <名称> (<ORD-id>)?`。空名订单则是 `Cancel <ORD-id>?` |
| PRIS-384-029 | 管理端 | P1 | 编辑改重名 | 订单可被 Admin 编辑 | 把名称改成同组织另一张订单的名称，只改大小写，保存 | 通知为重名文案；编辑器关闭；重新打开后名称仍是旧值 |
| PRIS-384-030 | 管理端 | P1 | 编辑历史空名 | Admin 可编辑一张 `name=null` 的订单 | 打开编辑，填一个新名称并保存 | 标题在打开时是 `Edit <ORD-id>`；保存成功后列表和详情改用新名称 |
| PRIS-384-031 | 管理端 | P1 | YAM 默认选中 | 机器人接口不是 YAM 在前 | Create order，不点其他机器人，填名称后保存 | 机器人按钮顺序是 YAM 在前且已按下；请求 `robot_type_id` 是 YAM |
| PRIS-384-032 | 管理端发票 | P0 | 开票勾选显示名称 | 一张 `ready_for_invoice` 且有名称，另一张同状态但没有名称 | 打开 Invoices | 有名称的勾选行同时能看到订单号、名称、组织。没有名称的行能看到订单号和组织，没有空白名称 |
| PRIS-384-033 | 管理端发票 | P0 | 发票表 | 一张已出发票，包含一张有名称的订单，和一张当前订单列表里不存在的 `ORD-id` | 看 Invoices 表的 Orders 列 | 有名称的显示名称，小字是订单号。列表里找不到的那个只显示订单号 |
| PRIS-384-034 | 管理端发票 | P1 | 完成确认 | 一张 issued 发票含 `ORD-A`（有名称）和 `ORD-B`（列表中无名称或未加载） | 点 Mark as complete | 确认文案是 `Orders to complete: <名称> (ORD-A), ORD-B.` |
| PRIS-384-035 | 管理端发票 | P2 | PDF 内容 | 上传一张不含订单名称的 PDF 并开票 | 下载该 PDF | PDF 内容就是上传的文件，不会因为这次改动自动写入订单名称 |
| PRIS-384-036 | 回归 | P1 | 营销站发票表 | 组织已有发票 | 看订单列表底部 Invoices 的 Orders included | 仍是逗号分隔的 `ORD-id`，不显示订单名称 |
| PRIS-384-037 | 回归 | P1 | 非 owner 不能借名称接口建单 | 组织成员不是 owner | `POST /api/orders`，body 含合法 `name` | `403` `owner_required`；不创建订单 |
| PRIS-384-038 | 回归 | P2 | 创建失败不留半条订单 | 制造一次 `409` 重名 | 查该组织订单列表和 `data_orders` | 没有新行，也没有只写了一半任务的订单 |

---

## 9. 发布前检查

- [ ] `20261010_data_orders_order_name.sql` 已在目标库执行；`order_name` 可空，唯一索引是 `(organization_id, lower(order_name))` 且只覆盖非空名称
- [ ] 营销站新建、存草稿都不能跳过名称（P0）
- [ ] 同组织大小写 / 多空格重名返回上面的 `409` 文案，营销站表单不关，管理端编辑器关掉并出通知（P0）
- [ ] 跨组织同名可以创建（P1）
- [ ] 已取消订单的名称不能被复用（P1）
- [ ] 历史 `name=null` 的订单列表显示单号；编辑时必须补名称（P0）
- [ ] 管理端发票勾选、发票表、完成确认按「有名称 / 无名称」两种样子显示（P0）
- [ ] 营销站发票表仍只显示订单号（P1）
- [ ] 新建订单时 YAM 排第一并且默认选中（P1）
