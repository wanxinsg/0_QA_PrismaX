# Points Earned and Counted on Each Arm

How points are earned and counted when users control robot arms. Arm = `robot_id`; each has `robot_class` in `robot_status`: `'access'`, `'training'`, or `'open'`.

---

## 1. Quick Reference

**Points per session (any arm)**  
= **Base session reward** (below) **+** **Dolls compare reward** (only access & open arms: 100 × success_count).


| Arm type             | Base reward  | Dolls compare | Usage limit (Amplifier) |
| -------------------- | ------------ | ------------- | ----------------------- |
| **access** (private) | Same formula | Yes           | None                    |
| **training**         | Same formula | **No**        | 3 joins/day (UTC)       |
| **open**             | Same formula | Yes           | 3 lifetime uses         |


Explorer Member cannot use robots (403). Storage: `users.total_points`, `tele_op_control_history.reward_points`, `point_transactions`.

---

## 2. Base Session Reward (All Arms)

Calculated in `queue_helper.process_session_rewards()` when a session ends (leave or disconnect). No double-credit: if `controlled_end_time` already set, skip.


| Condition                                          | Points                             |
| -------------------------------------------------- | ---------------------------------- |
| First tele-op (no prior `first_time_tele_op` 3000) | 3000                               |
| Inactive exit, session < ~50 s                     | 0                                  |
| Else: active or long enough                        | `int(session_seconds × 0.3)`       |
| Else: inactive, ≥50 s                              | `int(max(duration − 30, 0) × 0.3)`  |


---

## 3. Dolls Compare Reward (Access & Open Only)

**Eligibility:** Only **access** and **open** arms. **Training** arms do not get it — the caller (robot/server) does not invoke `POST /vision/dolls_compare` for training arms; the backend does not check `robot_class`.

**When it runs:** Caller sends `control_token` + `robotId` + `views` to `/vision/dolls_compare`. If result is success: `reward_inc = 100 * success_count`. Then: add to `tele_op_control_history.reward_points`, `users.total_points`, and insert `point_transactions` with `transaction_type = 'dolls_compare_reward'`.

### success_count

From `evaluate_compare_result(res)` in `image_recognitions.py`. Input: `res["views"]` = per-camera `start`/`end` with `left`/`right` counts.

- Per camera: `sl,sr` = start left/right, `el,er` = end left/right. `dl = el - sl`, `dr = er - sr`.
- If `sl+sr ≠ el+er` → abnormal (camera skipped). If `dl=0` and `dr=0` → add 0. If `dl ≠ -dr` → abnormal. Else `success_count += abs(dl)`.
- Returns `(abnormal, success_count)`. Reward: `status = "success"` iff `not abnormal and success_count > 0`; then `reward_inc = 100 * success_count`.

---

## 4. Counting & Storage

- **Per arm:** Sum `tele_op_control_history.reward_points` for that `robot_id` (and optionally `user_id`). Each row = one session; columns include `user_id`, `robot_id`, `control_token`, `controlled_hours`, `reward_points`.
- **User total:** `users.total_points` (all sources). Tele-op types: `first_time_tele_op`, `robot_control_reward`, `dolls_compare_reward`.
- **APIs:** `POST /fetch_tele_op_control_history` (userId) — sessions + `total_reward_points`; `POST /fetch_tele_op_session_complete_status` (controlToken) — single session.

---

## 5. Other Point Sources (Not Per-Arm)


| Source           | transaction_type | Rule                                            |
| ---------------- | ---------------- | ----------------------------------------------- |
| Daily login      | `daily_login`    | Once/day; 10/30/50 by tier × chain multiplier   |
| First-time daily | —                | If total_points was 0 → 1000 × multiplier       |
| Referral         | (no row)         | 500 per referee + 10% of referees’ total_points |
| Quiz             | `quiz`           | One-time: 500 per correct + 1000 if all correct |


---

## 6. Code & Tables Reference


| What              | Where                                                                 |
| ----------------- | --------------------------------------------------------------------- |
| Session reward    | `queue_helper.py`: `process_session_rewards()`                        |
| Join / arm checks | `app.py`: `/queue/join`                                               |
| Dolls compare     | `app.py`: `vision_dolls_compare()`                                    |
| success_count     | `image_recognitions.py`: `evaluate_compare_result()`                  |
| History API       | `app.py`: `/fetch_tele_op_control_history`                            |
| Tables            | `tele_op_control_history`, `users.total_points`, `point_transactions` |


---

## For Users: How Your Points Work (English)

**How do I earn points when I control a robot?**

Each time you finish a control session, you earn **teleop-time points** based on how long you controlled the robot. If it’s your **first time** ever controlling any robot, you get a one-time **welcome bonus** (3,000 points) for that session instead of the time-based amount.

| When | Points |
|------|--------|
| First time ever controlling any robot | 3,000 |
| Disconnected or timed out, session under ~1 minute | 0 |
| Active session or you leave normally | 0.3 × seconds (rounded down) |
| Disconnected or timed out, session ≥ ~1 minute | 0.3 × (seconds − 30), rounded down |

- **Active sessions:** You earn points at **0.3 points per second** of control (i.e. the amount is the number of seconds × 0.3, rounded down). The longer you control (and leave normally), the more you earn.
- **If you’re disconnected or timed out:** Short sessions under about 1 minute don’t earn points. Longer sessions still earn points, but a short time is deducted before the rate is applied.
- You never get points twice for the same session.

**Do all robots give the same points?**

Teleop-time points use the **same rules on every robot**. Reward points depend on arm type:

| Arm type | Teleop-time points | Reward points |
|----------|---------------------|---------------|
| Arena Arms | Yes (same rules) | Yes |
| Private Arms | Yes (same rules) | Yes |
| Training Arms (Black and Gold) | Yes (same rules) | No — teleop-time points only |

**What are reward points?**  
After your session, the system compares the number of dolls on the tray before and after you controlled the robot (using camera views). For each doll that is counted as having moved **in a consistent way between sides**, you earn **100 points**.  

*What does “in a consistent way between sides” mean?* The tray is treated as having two sides (e.g. left and right). The system checks that (1) the **total** number of dolls is the same before and after—no dolls disappear or appear from nowhere—and (2) any change on one side is matched by the opposite change on the other (e.g. 3 fewer on the left and 3 more on the right means 3 dolls moved from left to right). Only movements that satisfy both conditions count; each such doll adds 100 points. If counts don’t match or the pattern is inconsistent, those dolls don’t count toward reward points.

Reward points are added on top of your teleop-time points. If the comparison cannot be completed or the result is invalid, no reward points are given for that session. Only Arena Arms and Private Arms run this check; Training Arms do not.