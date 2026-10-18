# PRIS-346 订单交付图表：Commit 逻辑分析

> 分析日期：2026-10-12（UTC+8）  
> 范围：`app-prismax-rp-backend`、`prismax-marketing-rp`  
> `app-prismax-rp` 没有 PRIS-346 提交，也没有同名远程分支。

两条功能提交都已在各自 `testing` 上。

| 仓库 | Commit | 时间（`-0700` / 北京时间） | Author | Message |
| --- | --- | --- | --- | --- |
| backend | `4209a1f4bae040b8dfc30b47f40e0335094d057c` | 2026-10-08 15:34 / 10-09 06:34 | Aparna Rangamani | `PRIS-346: add apis for order delivery chart` |
| marketing | `cfc6ff7b0ca659901d8ea57bb996c135b510cb11` | 2026-10-08 13:23 / 10-09 04:23 | Aparna Rangamani | `PRIS-346: add orders delivery chart` |

营销站远程分支 `PRIS-346-data-delivery-chart` 仍指向 `cfc6ff7`。后端对应远程分支已经不在。

---

## 1. 业务目标

订单进入生产之后，按天 / 周 / 月看交付时长：

| 页面 | 位置 | 柱子含义 |
| --- | --- | --- |
| 订单详情 | Delivery progress 右侧的 **Delivery chart** | 绿柱 Accepted，粉柱 Rejected，堆叠 |
| 订单列表底部 | Invoices 右侧的 **Delivery activity** | 一根绿柱，高度是交付总时长，不拆拒绝 |

列表上的图可以按订单多选。详情图只画当前订单。

时长来源与现有 Delivery progress 相同：`DERIVED_READY` episode 的 `video_duration_hours * 3600`。拒绝时长来自 `data_order_reported_episodes.duration_seconds`。单测把 history 的全量 `totals` 和 `_delivery_progress` 的 delivered / reported_bad / accepted 对过一遍。

---

## 2. 数据流

```text
data_jobs + data_uploads + data_episodes          data_order_additional_episodes
status = DERIVED_READY                            status = DERIVED_READY
source = job, priority 0                          source = additional, priority 1
        │                                                    │
        └──────── DISTINCT ON (order_id, episode_id) ───────┘
                         job 优先
                         │
                         │  JOIN data_order_items（同一 order_id + task_id）
                         ▼
              用交付时间做 date_trunc（UTC）
              job：uploaded_at，否则 created_at
              additional：added_at，否则 uploaded_at，否则 created_at
                         │
                         │  LEFT JOIN data_order_reported_episodes
                         ▼
              每个桶：delivered_seconds、rejected_seconds
                         │
                         ▼
              Python 补齐固定窗口，accepted = max(delivered - rejected, 0)
                         │
                         ▼
              GET /api/orders/delivery-history
              GET /api/orders/<ORD-id>/delivery-history
                         │
                         ▼
              详情：堆叠柱（小时，两位小数）
              列表：单色柱（交付小时）
```

---

## 3. 后端 `4209a1f`

### 3.1 接口

都要登录。`granularity` 缺省是 `day`，只接受 `day`、`week`、`month`，其他值 `400`，文案 `granularity must be day, week, or month`。

**组织汇总** `GET /api/orders/delivery-history`

| 查询参数 | 作用 |
| --- | --- |
| `organization_id` | 指定组织。缺省走当前用户的组织上下文 |
| `granularity` | `day` / `week` / `month` |
| `order_ids` | 逗号分隔的 `ORD-<数字>`。缺省表示该组织里所有已开始的订单 |

先 `list_orders`，再留下状态属于下面集合的订单：

| 状态 | 能进图表 | 窗口右端 |
| --- | --- | --- |
| `production`、`delivering` | 是 | 今天（UTC 日期） |
| `ready_for_invoice`、`complete` | 是 | 最后一条交付所在的桶 |
| `draft`、`submitted`、`pending_approval`、`cancelled` 等 | 否，静默丢掉 | — |

`order_ids` 再和这份名单取交集。不在组织里、还没开始、或者不存在的单号被丢掉，接口仍是 `200`。单测里 `ORD-1044,ORD-9999` 在当前组织只有 `1044` 时，只查 `[1044]`；只传 `ORD-9999` 时查空列表。

窗口是否锚到今天：剩下的订单里**只要有一张**是 `production` 或 `delivering`，整张图就锚到今天。

**单张订单** `GET /api/orders/<order_ref>/delivery-history`

`_order_context` 会确认当前用户能看到这张订单所属的组织。订单还没进入上表四种状态时返回 `409`，`code=delivery_not_started`，文案 `delivery history is available once production starts`。`production` / `delivering` 锚到今天；`ready_for_invoice` / `complete` 锚到最后一条交付。

订单号必须是 `ORD-<数字>`，否则走现有的 invalid reference 错误。

### 3.2 哪些 episode 算进去

复用批量交付用的 `ORDER_EPISODES_BATCH_CTE`：

- 只收 `e.status = DERIVED_READY`。
- job 路径：未删除的 `data_jobs` → 其 upload → episode。`source='job'`，优先级 0。
- additional 路径：`data_order_additional_episodes`。`source='additional'`，优先级 1。
- `DISTINCT ON (order_id, episode_id)`，按优先级和 `job_id` 取一条。同一条 episode 既在 job 里又被手工加进订单时，按 **job** 计。
- 再 `JOIN data_order_items`，要求 `order_id` 和 `task_id` 都对得上。`task_id` 为空的行对不上，不进图表。`(order_id, task_id)` 在 `task_id IS NOT NULL` 时有唯一索引，这个 JOIN 不会因为重复行把时长乘倍。
- 时长是 `COALESCE(e.video_duration_hours * 3600, 0)`。

### 3.3 时间落在哪个桶

```text
date_trunc(granularity,
  COALESCE(
    additional.added_at    仅 source = 'additional' 时
    u.uploaded_at
    u.created_at
  ) AT TIME ZONE 'UTC'
)
```

| episode 来源 | 分桶时间 |
| --- | --- |
| job | `uploaded_at`，没有则 `created_at` |
| additional | `added_at`，没有则 `uploaded_at`，再没有则 `created_at` |

拒绝记录挂在同一条 episode 上，所以拒绝时长进的是**交付时间**那个桶，不是客户点击 Report 的那天。`data_order_reported_episodes` 的主键是 `(order_id, episode_id)`，一条 episode 只有一行拒绝。表还不存在时，拒绝时长按 0，和 Delivery progress 的兼容方式一样。

PostgreSQL `date_trunc('week')` 从周一开始。Python 用 `weekday()`（周一为 0）生成周起点，两边对齐。单测：今天 `2026-10-07`（周三）时，最后一根周柱是 `2026-10-05`。

### 3.4 窗口和返回值

SQL 不做日期过滤，把这些订单的全部分桶都查出来。Python 再切固定窗口，缺的桶补 0。

| granularity | 桶数 | label |
| --- | --- | --- |
| `day` | 7 | `月/日`，例如 `9/8` |
| `week` | 8 | 该周周一的 `月/日` |
| `month` | 12 | `Jan` … `Dec`，不带年份。连续 12 个月每个月名只出现一次 |

右端：

- `anchor_today=true`：右端是 UTC 的今天。
- `anchor_today=false` 且至少有一个桶：右端是最大的桶日期。已结束订单的日视图，最后一根柱落在最后交付那天，再往前补 6 天。
- 没有任何桶：右端退回今天，返回一排 0。

每个桶：

```text
accepted_seconds = max(delivered_seconds - rejected_seconds, 0)
```

三个秒数字段都 `round(..., 3)`。`bucket_start` 是 `YYYY-MM-DD`。

`totals` 是 SQL 返回的**全部桶**之和，包含窗口外面的历史。`totals.accepted_seconds` 是总交付减总拒绝之后再夹到 0，等于各桶 `accepted_seconds` 之和的前提是没有任何一桶的拒绝时长超过该桶交付时长。

响应：

```json
{
  "success": true,
  "data": {
    "granularity": "day",
    "buckets": [
      {
        "bucket_start": "2026-09-08",
        "label": "9/8",
        "delivered_seconds": 7200,
        "rejected_seconds": 1800,
        "accepted_seconds": 5400
      }
    ],
    "totals": {
      "delivered_seconds": 10800,
      "rejected_seconds": 1800,
      "accepted_seconds": 9000
    }
  }
}
```

### 3.5 单测锁住的行为

`test_repository.py`

| 用例 | 断言 |
| --- | --- |
| `test_delivery_history_reconciles_with_delivery_progress_totals` | 全量 totals 与 `_delivery_progress` 一致；日窗口 7 桶，右端是传入的 today；`9/8` 的 accepted 5400、rejected 1800；SQL 含去重、拒绝汇总、`added_at`、`uploaded_at`、`AT TIME ZONE 'UTC'` |
| `test_delivery_history_ends_at_last_delivery_when_not_active` | `anchor_today=false` 时右端是 `2026-03-03`，不是今天 |
| `test_delivery_history_week_and_month_windows` | 周 8 桶、右端周一；月 12 桶，从 `2025-11-01` 到 label `Oct` |
| `test_delivery_history_rejects_unknown_granularity` | `hour` 抛 `DomainError` |
| `test_delivery_history_works_before_reported_episode_migration` | 表不存在时 SQL 不引用 `data_order_reported_episodes` |

`test_routes.py`

| 用例 | 断言 |
| --- | --- |
| `test_order_delivery_history_requires_started_order` | `submitted` → `409` |
| `test_order_delivery_history_anchors_active_orders_to_today` | `delivering` + `granularity=week` → `anchor_today=true` |
| `test_order_delivery_history_anchors_finished_orders_to_last_delivery` | `ready_for_invoice` 默认 `day`，`anchor_today=false` |
| `test_order_delivery_history_rejects_unknown_granularity` | `hour` → `400` |
| `test_orders_delivery_history_only_includes_started_orders` | 组织里只有 `submitted` 时查空列表，`anchor_today=false` |
| `test_orders_delivery_history_filters_to_requested_orders` | 只保留组织内已开始的单号 |

---

## 4. 营销站 `cfc6ff7`

### 4.1 `orderApi`

| 方法 | 请求 |
| --- | --- |
| `orderDeliveryHistory(token, orderId, granularity)` | `GET /api/orders/{orderId}/delivery-history?granularity=` |
| `deliveryHistory(token, granularity, orderIds, organizationId)` | `GET /api/orders/delivery-history` |

汇总接口只在调用方传入 `orderIds` 时带 `order_ids`，传入 `organizationId` 时带 `organization_id`。`orderIds === null` 表示 All，不传 `order_ids`，由后端自己列出该组织已开始的订单。

### 4.2 详情：Delivery chart

`production`、`delivering`、`ready_for_invoice`、`complete` 才渲染。和 Delivery progress 用同一份状态列表。卡片放在详情双列网格里，进度卡右边；窄于 900px 时改成单列。

`DeliveryChart` 的 `variant` 默认 `detail`：

- 图例：Accepted `#60c87a`，Rejected `#f09b9b`。
- 堆叠柱：下绿上粉。拒绝为 0 时只有绿柱。
- Tooltip：accepted 小时；rejected 大于 0 才显示拒绝行；底部 total 是 `accepted + rejected`。
- 右下角标注 `hrs / day|week|month`。Y 轴不画刻度。
- Daily / Weekly / Monthly，默认 Daily。

小时换算：`Math.round((seconds / 3600) * 100) / 100`，最多两位小数。不足约 18 秒的时长会显示成 `0`，柱高接近 0，但只要原始 `delivered_seconds > 0`，空态文案不会出现。

`refreshKey` 是 `状态:交付秒:拒绝秒`。报坏 episode、状态变化或进度数字变化后会重新请求。已有数据时刷新只把图降到 55% 透明度，不换成 Loading。

### 4.3 列表：Delivery activity

订单列表底部从单独的 Invoices 标题，改成左右两张卡：

| 左（约 1.2fr） | 右（约 1fr） |
| --- | --- |
| Invoices | Delivery activity |

没有任何已开始订单时不渲染右卡，Invoices 占满一行。窄于 1200px 时上下堆叠。列表筛选（Active / Complete / Draft 等）只影响上面的订单表。底部图表用的是完整 `orders`，不跟当前筛选项走。

`DeliveryActivity` 把 `variant="summary"` 的图包一层，并加订单多选：

| 选择 | 传给接口的 `orderIds` | 按钮文案 |
| --- | --- | --- |
| 初始，或勾选 All orders，或把每一张都勾上 | `null`（不传 `order_ids`） | `Orders: All` |
| 勾了部分 | 这些 `ORD-…` | 一张时显示单号，多张时 `Orders: N selected` |
| 全部取消 | 空数组，不发请求 | `Orders: None`，图内文案 `No orders selected.` |

点下拉外部关闭菜单。组织用页面上的 `selectedOrganizationId`。`refreshKey` 把每张订单的状态、交付秒、拒绝秒拼在一起，任一变化都重拉。

汇总图只有一根绿柱，数据是 `delivered_seconds` 换算的小时。Tooltip 只显示 `{label}` 和 `{hours} hrs`，不拆 Accepted / Rejected。颜色和详情里的 Accepted 相同，读的数是交付总量。

### 4.4 空态和失败

| 条件 | 画面 |
| --- | --- |
| 没有 token，或一张订单都没选 | 不请求。没选时显示 `No orders selected.` |
| 首次加载 | `Loading…` |
| 请求失败 | 错误对象的 `message`，否则 `Could not load delivery history.` |
| 每个可见桶的 `delivered_seconds <= 0` | `No data for selected time period` |

窗口外有历史、窗口内全是 0 时，也会走到最后这条。接口里的 `totals` 前端没有展示。

---

## 5. 和 Delivery progress 对不齐的地方

进度卡是该订单的**全部历史**。柱状图是固定窗口。两边用同一套 episode 和同一套拒绝表，但裁切方式不同。

1. 进行中的订单（`production`、`delivering`）日视图右端是今天。最后一次交付早于 7 天前时，日视图是空的，进度卡仍有小时。周视图看 8 周，月视图看 12 个月，旧数据会在更粗的粒度里出现。
2. 已结束订单的窗口右端是最后一条交付，所以最后一根柱应该有数。更早、落在窗口外的交付仍然不在柱上，却留在进度卡和接口 `totals` 里。
3. 列表上同时选了进行中和已结束的订单时，因为存在进行中订单，整张图锚到今天。已结束订单的旧交付可能被裁出日视图。
4. 拒绝记在交付那天的桶里。今天报坏一条上周交付的 episode，变化出现在上周那根柱，不会新长出一根“今天”的柱。`refreshKey` 含拒绝秒数，报完会重拉。
5. 同一条 episode 既属于 job 又在 additional 表里时，按 job 处理，分桶时间用上传时间，不用 `added_at`。
6. 详情柱的高度是 accepted 加 rejected。拒绝不超过该桶交付时，这个高度等于 delivered，和列表上的绿柱一致。若某桶拒绝秒数大于交付秒数，accepted 被夹成 0，详情柱高等于拒绝时长，列表柱高等于交付时长，两张图不再一样高。Tooltip 的 total 也是 accepted + rejected。
7. 汇总图在选择 All 时不上传前端手头的 id 列表，后端按组织重列已开始订单。下拉框里的 id 来自前端已经加载的 `orders`。两边的状态集合相同；若两边列表短暂不一致，All 的柱会跟下拉框里看到的单号集合不同。勾选具体单号时才按那些 id 求交。
