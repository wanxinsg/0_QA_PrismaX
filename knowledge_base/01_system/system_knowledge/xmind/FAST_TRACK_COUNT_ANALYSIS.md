# Fast Track 次数逻辑分析

## 1. 概述

- **功能**：Innovator 会员加入队列时可使用 Fast Track，插队到「当前最后一个 Fast Track 用户」之后。
- **限制**：**每个 UTC 自然日、全机器人共享，最多 6 次 Fast Track**。
- **实现位置**：`app_prismax_tele_op_services/app.py`，`/queue/join` 接口。

---

## 2. 次数统计逻辑

### 2.1 数据来源

- **表**：`robot_queue`
- **统计条件**：
  - `user_id = :uid`（当前用户）
  - `fast_track = TRUE`（仅统计已使用 Fast Track 的记录）
  - `DATE(created_at AT TIME ZONE 'UTC') = DATE(NOW() AT TIME ZONE 'UTC')`（按 UTC 日期「今天」）

### 2.2 核心 SQL（当日已使用次数）

```sql
SELECT COUNT(*)
FROM robot_queue
WHERE user_id = :uid
  AND fast_track = TRUE
  AND DATE(created_at AT TIME ZONE 'UTC') = DATE(NOW() AT TIME ZONE 'UTC')
```

### 2.3 判定规则

| 常量 | 值 | 说明 |
|------|----|------|
| `fast_track_limit` | 6 | 每日 Fast Track 上限 |
| `can_use_fast_track` | `fast_track_count_today < fast_track_limit` | 今日已用次数 < 6 才允许本次使用 |

- **第 1～6 次**：`fast_track_count_today` 为 0～5，`can_use_fast_track = True`，本次加入会被标记为 Fast Track 并插队。
- **第 7 次及以后**：`fast_track_count_today = 6`，`can_use_fast_track = False`，本次加入**仍可入队**，但按普通队尾入队，不插队、不标记 `fast_track`，并返回提示文案。

---

## 3. 与 join 流程的关系

### 3.1 顺序（app.py 中）

1. **先入队**  
   插入 `robot_queue` 一条记录：`position = max_pos + 1`，`fast_track = FALSE`。

2. **再判断是否可 Fast Track**（仅当 `user_class == 'Innovator Member'`）  
   - 用上面的 SQL 统计该用户**今日、全机器人、已标记为 fast_track 的记录数**。  
   - 若 `fast_track_count_today < 6`，则 `can_use_fast_track = True`。

3. **若可 Fast Track**  
   - 计算插队后的 `final_position`（在「最后一个 Fast Track 的 Innovator」之后）。  
   - 通过一系列 `UPDATE` 重排队列，并把**当前这条入队记录**更新为：  
     `position = final_position`，`fast_track = TRUE`。  
   - 这样，本次加入会被计入「今日 Fast Track 次数」。

4. **若已达上限**  
   - 不更新位置、不把 `fast_track` 设为 TRUE，用户保持刚入队时的队尾位置。  
   - 在响应中设置 `fast_track_limit_reached = True`，前端可展示：“You have reached the maximum 6 fast tracks a day. Please come back tomorrow.”

### 3.2 次数统计的语义

- **统计的是「今日已发生的 Fast Track 使用次数」**，不包含「当前这次请求」在未更新前的状态（当前这条先以 `fast_track = FALSE` 插入，只有后续 UPDATE 才会设为 TRUE）。  
- 因此：  
  - 第 1 次 Fast Track：统计 0 条 → 允许 → 更新为 `fast_track = TRUE`（今日 1 条）。  
  - 第 6 次：统计 5 条 → 允许 → 更新后今日 6 条。  
  - 第 7 次：统计 6 条 → 不允许，不更新 `fast_track`，今日仍为 6 条。  
- **按 UTC 日期**：零点（UTC）后重新按「新的一天」计数。

---

## 4. 关键代码位置

| 逻辑 | 文件 | 行号区间 |
|------|------|----------|
| 每日上限常量 | `app.py` | 564 |
| 今日 Fast Track 次数查询 | `app.py` | 565–573 |
| 是否允许本次 Fast Track | `app.py` | 576–578 |
| 插队与更新 `fast_track = TRUE` | `app.py` | 580–691 |
| 达上限时的响应文案 | `app.py` | 713–714 |

---

## 5. 要点小结

1. **按用户、按 UTC 日、全机器人共享**：不区分 robot_id，所有机器人当天的 Fast Track 共用一个 6 次上限。  
2. **只统计已生效的 Fast Track**：仅 `robot_queue.fast_track = TRUE` 且 `created_at` 在当日（UTC）的记录参与计数。  
3. **达上限仍可入队**：第 7 次及以后只是不能插队、不标记 Fast Track，普通入队仍然成功。  
4. **会员限制**：仅 `user_class == 'Innovator Member'` 会进入 Fast Track 逻辑；其他会员不会增加 Fast Track 计数。

---

## 6. 可选扩展（当前未实现）

- 后端目前**没有**单独接口返回「今日剩余 Fast Track 次数」或「今日已用次数」；前端若需展示，可考虑：
  - 在现有某接口（如队列状态/用户状态）中增加字段，例如：  
    `fast_track_used_today`、`fast_track_remaining_today`；或  
  - 新增一个轻量查询接口，用与上面相同的 `COUNT` 条件返回今日已用次数，前端用 `6 - count` 得到剩余次数。

如需在某个具体接口里加「剩余次数」或「已用次数」字段，可以指定接口路径，再按该接口补 SQL 与返回结构即可。
