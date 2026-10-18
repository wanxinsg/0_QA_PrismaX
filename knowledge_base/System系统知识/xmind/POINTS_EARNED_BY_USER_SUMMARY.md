# How Users Earn Points — Summary

This document summarizes how points are earned for users in **app_prismax_user_management**, including daily login, first-time bonus, and quiz. Robot control and dolls-compare rewards are implemented in other services; they are listed here for context and are documented in `POINTS_EARNED_AND_COUNTED_BY_ARM.md`.

---

## 1. Quick Reference

| Source              | API / trigger                    | transaction_type   | Rule |
|---------------------|----------------------------------|--------------------|------|
| **Daily login**     | `POST /api/daily-login-points`   | `daily_login`      | Once per day; base 10/30/50 by tier × chain multiplier |
| **First-time daily**| Same as daily login              | (no row)           | If `total_points` was 0 → grant 1000 × multiplier once |
| **Quiz**            | `POST /api/quiz/submit`          | `quiz`             | One-time: 500 per correct + 1000 if all correct |
| Robot control       | Tele-op session end              | `first_time_tele_op`, `robot_control_reward` | See arm doc |
| Dolls compare       | `POST /vision/dolls_compare`      | `dolls_compare_reward` | 100 × success_count (access/open arms only) |

User total is stored in `users.total_points`. Most of the above also write to `point_transactions` except the one-time initial grant on first daily login.

---

## 2. Daily Login Points

- **Endpoint:** `POST /api/daily-login-points`
- **Payload:** `wallet_address` or `email`, optional `chain` (default `solana`), optional `user_local_date` (YYYY-MM-DD).

**Behavior:**

- At most **one** daily login reward per user per calendar day (`user_local_date`). If the user already has a `point_transactions` row with `transaction_type = 'daily_login'` for that date, no additional points are given.
- **Base points by user class** (before chain multiplier):
  - **Explorer Member:** 10
  - **Other (non-Innovator):** 30
  - **Innovator Member:** 50
- **Chain multiplier:** `chain === 'monad'` → 2; otherwise 1.
- **Final daily points** = base × multiplier (e.g. Innovator on Monad: 50 × 2 = 100).
- `user_local_date` must be within UTC ±1 day; if omitted, server uses current date.
- On success, `users.total_points` is increased and a row is inserted into `point_transactions` with `transaction_type = 'daily_login'` and `user_local_date`.

---

## 3. First-Time Daily (Initial Points)

- **Trigger:** Same request as daily login (`POST /api/daily-login-points`).
- **Condition:** User's `total_points` is **0** at the time of the request.
- **Action:** Set `users.total_points = 1000 * multiplier` (multiplier: 2 for Monad, 1 otherwise). This is a one-time grant; **no** `point_transactions` row is created for it.
- After this, the normal daily login check runs; if the user has not yet received daily login for that day, they also get the daily login points (and a `daily_login` transaction row) in the same request.

---

## 4. Quiz Points

- **Endpoint:** `POST /api/quiz/submit` (requires reCAPTCHA and `userid`).
- **Rule:** **One-time** per user. If the user already has a `point_transactions` row with `transaction_type = 'quiz'`, submission is rejected.
- **Formula:**  
  - 500 points per correct answer  
  - Plus 1000 bonus if **all** questions are correct  
  - Total = `correct_answers * 500 + (1000 if correct_answers == total_questions else 0)`
- **Storage:** One row in `point_transactions` with `transaction_type = 'quiz'` and the awarded amount; `users.total_points` is increased by the same amount.

---

## 5. Other Point Sources (Not in User Management)

- **Robot control (tele-op):** Session time reward and optional first-time 3000 bonus. See `POINTS_EARNED_AND_COUNTED_BY_ARM.md` (e.g. `queue_helper.process_session_rewards()`).
- **Dolls compare:** 100 points per counted doll movement on access/open arms; `transaction_type = 'dolls_compare_reward'`.

All of these update `users.total_points` and (except the one-time initial grant) write to `point_transactions`.

---

## 6. Code & Tables (User Management)

| What            | Where in app_prismax_user_management   |
|-----------------|----------------------------------------|
| Daily login     | `app.py`: `daily_login_points()`       |
| First-time grant| `app.py`: inside `daily_login_points()` when `total_points == 0` |
| Quiz submit     | `app.py`: `submit_quiz_results()`      |
| Quiz status     | `app.py`: `check_quiz_status()`        |
| Point history   | `app.py`: `get_point_transactions()`   |

**Tables:** `users` (`total_points`), `point_transactions` (`userid`, `points_change`, `transaction_type`, `user_local_date` for daily login).

---

## 7. For Users (Plain English)

- **Daily login:** Log in once per day to earn points. Amount depends on your membership (Explorer / standard / Innovator) and chain (Monad gives double). You can only claim once per calendar day.
- **First time:** The very first time you claim daily login and had zero points, you get an extra one-time 1000 (or 2000 on Monad) before the daily amount.
- **Quiz:** Complete the quiz once. You earn 500 points per correct answer and an extra 1000 if you get every question right.
- **Robot control:** Control robots in the arena to earn time-based points and (on some arms) extra "dolls compare" points—see the robot/arm documentation for details.

Your **total points** are stored in your account and can be viewed via the point-transactions API (e.g. last 14 days) and in responses from daily login and quiz.

---

## User Summary (for end users)

**How do I earn points?**

You can earn points in several ways:

- **Daily login** — Log in once per day to claim points. You can only claim once per calendar day. How much you get depends on your membership level and which chain you use:

  - **Explorer Member:** 10 points per day (20 if you connect with Monad).
  - **Standard member** (other memberships except Innovator): 30 points per day (60 if you connect with Monad).
  - **Innovator Member:** 50 points per day (100 if you connect with Monad).

  If you connect with Monad, your daily login points are doubled for that day.

- **First-time bonus** — The first time you ever claim daily login (when you have no points yet), you receive a one-time welcome bonus (1,000 points, or 2,000 on Monad) in addition to your daily amount.

- **Quiz** — Complete the quiz once (5 questions). You earn 500 points per correct answer, plus an extra 1,000 points if you answer every question correctly. **Total: up to 3,500 points** (2,500 for 5 correct + 1,000 bonus for a perfect score).

- **Robot control** — When you control robots in the arena, you earn points based on how long you control them and (on some arms) extra points when the system counts how many dolls you moved correctly. See the robot control documentation for details.

Your points are saved to your account. You can see your balance and recent point activity in the app (for example after claiming daily login or completing the quiz).
