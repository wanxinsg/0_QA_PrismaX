## Data QA Review 逻辑说明（app_prismax_data_pipeline）

### 1. 背景与目标

`app_prismax_data_pipeline/app.py` 中实现了 **数据 QA 审核流程**，配合 `qa_helper.py` 中的规则，完成对一次数据上传（`data_uploads` 记录）的多轮人工质检。  
目标是：

- **基于角色分层审核**：普通 QA / Senior QA / Expert QA 拥有不同的队列与职责。
- **多轮复核**：最多 3 轮，每轮所需 reviewer 数与通过 / 失败规则不同。
- **可追踪审查结果**：所有审核记录写入 `data_qa_sessions`，最终汇总为上传级别的决策与质量分数，并同步回 `data_uploads.status`。

本文聚焦说明：

- QA 相关的核心表结构与状态含义（从代码角度推断）
- 队列规则（谁能看到哪些 upload 做 QA）
- Review 采样逻辑（如何选出 episode）  
- 审核提交接口的参数校验 / 一致性校验  
- 多轮审核的分歧检测与状态流转

---

### 2. 角色与轮次模型

#### 2.1 QA 角色定义（`qa_helper.py`）

```12:44:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp-backend/app_prismax_data_pipeline/qa_helper.py
QA_ROLE_BASE = "qa"
QA_ROLE_SENIOR = "senior qa"
QA_ROLE_EXPERT = "expert qa"
QA_ALLOWED_ROLES = {QA_ROLE_BASE, QA_ROLE_SENIOR, QA_ROLE_EXPERT}
```

- **普通 QA (`qa`)**
- **高级 QA (`senior qa`)**
- **专家 QA (`expert qa`)**

后端通过 `_normalize_user_role` 将 `users.user_role` 正规化为小写、去多余空格，再与上述常量比对。

#### 2.2 每轮所需 Reviewer 数

```12:16:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp-backend/app_prismax_data_pipeline/qa_helper.py
QA_REVIEWER_COUNT_BY_ROUND = {
    1: 3,
    2: 2,
    3: 1,
}
```

- **第 1 轮：需要 3 个 reviewer**
- **第 2 轮：需要 2 个 reviewer**
- **第 3 轮：需要 1 个 reviewer（相当于专家仲裁）**

只有当某轮的 `data_qa_sessions` 条数达到该轮要求的 reviewer 数时，才会触发该轮的 **结果汇总与 upload 状态更新**。

#### 2.3 轮次结果对应的 upload 状态

```18:27:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp-backend/app_prismax_data_pipeline/qa_helper.py
QA_ROUND_SUCCESS_STATUS = {
    1: "REVIEW_FIRST_ROUND_SUCCEEDED",
    2: "REVIEW_SECOND_ROUND_SUCCEEDED",
    3: "REVIEW_THIRD_ROUND_SUCCEEDED",
}

QA_ROUND_FAILED_STATUS = {
    1: "REVIEW_FIRST_ROUND_FAILED",
    2: "REVIEW_SECOND_ROUND_FAILED",
}
```

- 每轮 **通过** 会将 `data_uploads.status` 更新为对应的 `*_SUCCEEDED`。
- 前两轮如果发生 **分歧**，会更新为 `*_FAILED`，并由较高级别 QA（Senior / Expert）处理下一轮。
- 第三轮视为最终仲裁轮：只存在 `SUCCEEDED`，不会再标记 `FAILED`。

---

### 3. QA 队列规则（谁能看到哪些 Upload）

#### 3.1 队列规则表述

```51:67:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp-backend/app_prismax_data_pipeline/qa_helper.py
def _get_qa_queue_rules(user_role: str):
    if user_role == QA_ROLE_BASE:
        return [
            {"status": "DERIVED_READY", "qa_round": 1, "priority": 1},
        ]
    if user_role == QA_ROLE_SENIOR:
        return [
            {"status": "REVIEW_FIRST_ROUND_FAILED", "qa_round": 2, "priority": 1},
            {"status": "DERIVED_READY", "qa_round": 1, "priority": 2},
        ]
    if user_role == QA_ROLE_EXPERT:
        return [
            {"status": "REVIEW_SECOND_ROUND_FAILED", "qa_round": 3, "priority": 1},
            {"status": "REVIEW_FIRST_ROUND_FAILED", "qa_round": 2, "priority": 2},
            {"status": "DERIVED_READY", "qa_round": 1, "priority": 3},
        ]
    return []
```

- **普通 QA**
  - 只处理 `DERIVED_READY` 状态的 upload，对应 **第 1 轮**。
- **Senior QA**
  - 优先处理 `REVIEW_FIRST_ROUND_FAILED`（第 2 轮）。
  - 若没有待处理失败单，再补充处理 `DERIVED_READY`（第 1 轮）。
- **Expert QA**
  - 优先处理 `REVIEW_SECOND_ROUND_FAILED`（第 3 轮）。
  - 然后处理 `REVIEW_FIRST_ROUND_FAILED`（第 2 轮）。
  - 最后处理 `DERIVED_READY`（第 1 轮）。

#### 3.2 QA 队列接口：`GET /data/qa/uploads`

```492:548:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp-backend/app_prismax_data_pipeline/app.py
@app.route('/data/qa/uploads', methods=['GET'])
def get_qa_uploads():
    user, user_role, error_response = _require_qa_user()
    ...
    queue_rules = _get_qa_queue_rules(user_role)
    statuses = [rule["status"] for rule in queue_rules]
    ...
    priority_case = " ".join([
        f"WHEN '{rule['status']}' THEN {int(rule['priority'])}"
        for rule in queue_rules
    ])
    round_case = " ".join([
        f"WHEN '{rule['status']}' THEN {int(rule['qa_round'])}"
        for rule in queue_rules
    ])
    ...
    SELECT u.upload_id, u.task_id, u.machine_id, u.status,
           CASE u.status {round_case} ELSE NULL END AS qa_round,
           ...
           (
               SELECT COUNT(*)
               FROM data_qa_sessions q
               WHERE q.upload_id = u.upload_id
                 AND q.qa_round = (CASE u.status {round_case} ELSE NULL END)
           ) AS round_review_count
    FROM data_uploads u
    LEFT JOIN data_episodes e ON e.upload_id = u.upload_id
    WHERE u.status IN :statuses
      AND NOT EXISTS (
          SELECT 1 FROM data_qa_sessions uq
          WHERE uq.upload_id = u.upload_id
            AND uq.user_id = :user_id
      )
    GROUP BY ...
    ORDER BY CASE u.status {priority_case} ELSE 999 END ASC, u.created_at DESC
```

**关键点：**

- 调用前需通过 `_require_qa_user`，即：
  - `Authorization: Bearer <token>` 或 `token` 参数。
  - token 映射的用户角色必须在 `QA_ALLOWED_ROLES` 中，否则 403。
- 查询逻辑：
  - 只拉取符合当前角色队列规则的 `data_uploads`（`u.status IN :statuses`）。
  - 排除当前用户已审核过的 upload。
  - 按队列规则的 `priority` 与 `u.created_at` 进行排序。
- 返回字段：
  - `qa_round`：该 upload 此时对当前角色而言属于第几轮。
  - `round_review_count`：当前轮次已完成的 review 数。
  - 额外在返回后注入：
    - `reviewer_role`：当前用户角色。
    - `reviewer_id`：当前用户 id。

**前端使用建议：**

- 以 `round_review_count` 与 `QA_REVIEWER_COUNT_BY_ROUND[qa_round]` 结合展示「该轮目前已评审数 / 需要评审数」。
- 按返回顺序依次拉取进行审核即可，不需要自行实现排序逻辑。

---

### 4. QA 采样与 Episode 列表

#### 4.1 接口：`GET /data/qa/uploads/<upload_id>/episodes`

```551:704:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp-backend/app_prismax_data_pipeline/app.py
@app.route('/data/qa/uploads/<int:upload_id>/episodes', methods=['GET'])
def get_qa_upload_episodes(upload_id):
    _, user_role, error_response = _require_qa_user()
    ...
    upload_row = conn.execute("SELECT upload_id, status FROM data_uploads ...").fetchone()
    upload_status = upload_row._mapping.get("status")
    qa_round = _resolve_upload_qa_round(upload_status, user_role)
    ...
    rows = conn.execute("""
        SELECT e.episode_id, e.upload_id, e.machine_id, e.task_id, e.status,
               e.raw_mcap_path, e.raw_video_folder_path,
               e.derived_bucket, e.derived_video_folder_path
        FROM data_episodes e
        WHERE e.upload_id = :upload_id
          AND e.status = 'DERIVED_READY'
        ORDER BY e.episode_id ASC
    """).fetchall()
    all_episode_ids = [int(row._mapping["episode_id"]) for row in rows]
    existing_sample_rows = conn.execute("""
        SELECT review_result
        FROM data_qa_sessions
        WHERE upload_id = :upload_id
          AND qa_round = :qa_round
        ORDER BY created_at ASC, qa_session_id ASC
    """).fetchall()
    ...
    if not sampled_episode_ids:
        sampled_episode_ids = _pick_deterministic_sample(all_episode_ids, upload_id, qa_round)
```

**逻辑分解：**

- 仅允许 QA 角色访问，并依据当前 `upload.status` + `user_role` 解析出当前轮 `qa_round`。
- 从 `data_episodes` 中取出该 upload 下所有 `DERIVED_READY` 的 episode。
- 为保证「同一轮、不同 reviewer 审核的是同一批 episode」：
  - 若该轮已有 review 记录，则从最早的 review 的 `review_result.sampled_episode_id` 中抽取样本作为 **参考样本**。
  - 若该轮还没有任何 review，则调用 `_pick_deterministic_sample`，基于 `(episode_ids, upload_id, qa_round)` 生成一个 **稳定的随机样本**。

#### 4.2 采样算法 `_pick_deterministic_sample`

```162:177:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp-backend/app_prismax_data_pipeline/qa_helper.py
def _get_sample_size(total_count: int) -> int:
    if total_count <= 0:
        return 0
    return total_count

def _pick_deterministic_sample(episode_ids, upload_id: int, qa_round: int):
    sample_size = _get_sample_size(len(episode_ids))
    if sample_size <= 0:
        return []
    seed_raw = f"{upload_id}:{qa_round}:qa-sample-v1".encode("utf-8")
    seed = int.from_bytes(hashlib.sha256(seed_raw).digest()[:8], "big")
    rng = random.Random(seed)
    candidates = list(episode_ids)
    rng.shuffle(candidates)
    return sorted(candidates[:sample_size])
```

当前实现中 `_get_sample_size` 返回 `total_count` 本身，因此样本实际上是「**全量 episode**」，但仍然通过固定随机种子确保：

- 同一个 `upload_id` + `qa_round` 下，所有 reviewer 拿到的 sample 集合相同；
- 若未来需要做「抽样子集」时，只需调整 `_get_sample_size` 实现即可。

#### 4.3 分页与派生视频 URL

- 接口支持 `offset` / `limit` 分页，最大 `limit` 为 100。
- 对采样后的 episode 列表，再做分页裁剪。
- 对每个 episode：
  - 计算 `derived_bucket` 与 `derived_video_folder_path`（如为空则从 `raw_video_folder_path` 推导）。
  - 使用 GCS 客户端列出派生视频 `.mp4`，并为每个对象生成有限期的 **GET signed URL**。

前端可使用返回的 `derived_videos[].signed_url` 直接进行视频播放预览。

---

### 5. QA 审核提交逻辑

#### 5.1 接口：`POST /data/qa/uploads/<upload_id>/review`

```707:904:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp-backend/app_prismax_data_pipeline/app.py
@app.route('/data/qa/uploads/<int:upload_id>/review', methods=['POST'])
def submit_upload_qa_review(upload_id):
    user, user_role, error_response = _require_qa_user()
    ...
    payload = request.get_json() or {}
    review_result = payload.get("review_result")
    qa_score = payload.get("qa_score")
    note = payload.get("note")
    qa_round_from_payload = payload.get("qa_round")
```

请求体关键信息：

- `review_result`：**必填，object**，包含具体 gate 与 score 明细，以及 `sampled_episode_id` / `upload_vote` / `upload_score` 等。
- `qa_score`：本次 reviewer 对 upload 给出的 0–100 整体分数；可以省略，若为 `None` 会从 `review_result.upload_score` 兜底。
- `note`：文字备注。
- `qa_round`：可选；如果提供，会与后端推导出的真实轮次进行严格一致性校验。

#### 5.2 基础校验：上传 id / 分数 / 轮次

接口中的关键防御性校验包括：

- `review_result` 必须是 dict，否则 400。
- `review_result.upload_id` 若存在，必须等于 URL 中的 `upload_id`，否则 400。
- `qa_score`：
  - 必须最终能解析为 `int` 且在 **0–100** 范围内；
  - 若 `review_result.upload_score` 也存在，二者必须相等，否则 400。
- `review_result.sampled_episode_id`：
  - 使用 `_extract_sampled_episode_ids_from_review_result` 解析为 int 数组。
  - 不允许为空，否则 400。
- `qa_round`：
  - 从当前 `upload.status` + `user_role` 调用 `_resolve_upload_qa_round` 推导出真实轮次。
  - 若 payload 中带了 `qa_round` 且不等于真实轮次，则 400。

此外还会检查：

- 当前用户是否已经在本 upload 上提交过任何 review（无论轮次字段是否为空），若已提交则返回 409，不允许重复。

#### 5.3 样本一致性校验

```746:828:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp-backend/app_prismax_data_pipeline/app.py
provided_sample_ids = sorted(set(_extract_sampled_episode_ids_from_review_result(review_result)))
...
existing_sample_rows = conn.execute("""
    SELECT review_result
    FROM data_qa_sessions
    WHERE upload_id = :upload_id
      AND qa_round = :qa_round
""").fetchall()
...
if not reference_sample_ids:
    reference_sample_ids = _pick_deterministic_sample(all_episode_ids, upload_id, qa_round)

if provided_sample_ids != reference_sample_ids:
    return jsonify({
        "success": False,
        "msg": "sampled_episode_id mismatch for this round",
        "expected_sampled_episode_id": reference_sample_ids,
    }), 400
```

**目的：**确保前端上报的 `review_result.sampled_episode_id` 与该轮应当审核的 episode 集合完全一致，避免 reviewer 对错样本进行打标。

- 若该轮已存在历史 review，则以 **首个 review 的样本** 作为标准。
- 若该轮尚无 review，则以 `_pick_deterministic_sample` 结果作为标准。
- 若前端传来的集合和标准集合不相等，则返回 400，并在响应中返回 `expected_sampled_episode_id` 供前端对齐。

#### 5.4 `review_result` 结构校验

`_validate_review_result_payload` 会对 `review_result` 做强约束检查：

```194:239:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp-backend/app_prismax_data_pipeline/qa_helper.py
def _validate_review_result_payload(review_result):
    if not isinstance(review_result, dict):
        return False, "review_result must be an object"
    result_rows = review_result.get("result")
    if not isinstance(result_rows, list):
        return False, "review_result.result must be an array"
    if len(result_rows) != 1:
        return False, "review_result.result must contain exactly 1 shared item"
    ...
    for gate_key in QA_GATE_KEYS:
        gate_value = _normalize_gate_value(gate.get(gate_key))
        if gate_value not in {"pass", "fail"}:
            return False, f"...gate.{gate_key} must be pass/fail"
    for score_key in QA_SCORE_KEYS:
        value = score.get(score_key)
        parsed = int(value) in [1..5] 否则报错
    upload_vote: 必须为 pass / fail
    upload_score: 必须为 0–100 的整数
```

**关键约束：**

- `review_result.result` 必须是数组且 **只能包含一个对象**（共享 gate 与 score）。
- 每个 gate key（下述 6 个）都必须是 `"pass"` 或 `"fail"`：
  - `prohibited_data`
  - `complete_task`
  - `misalignment`
  - `fov_compliance`
  - `non_robot_actions`
  - `language_compliance`
- 每个 score key（下述 5 个）必须是 **1–5 的整数**：
  - `operator_skill`
  - `trajectory_smoothness`
  - `demonstration_efficiency`
  - `demonstration_completeness`
  - `episode_diversity`
- `upload_vote` 只能是 `"pass"` 或 `"fail"`。
- `upload_score` 必须是 0–100 的整数。

前端在构造 `review_result` 时必须完全符合以上约束，否则会拿到明确的 400 错误及错误信息字符串。

#### 5.5 写入 `data_qa_sessions`

通过所有校验后，会插入一条 QA 审核记录：

- 字段包括 `upload_id` / `qa_round` / `qa_score` / `user_id` / `note` / `review_result (jsonb)` / `created_at`。
- 插入完成后，会重新查询当前轮次所有 review 记录，进入 **多轮决策与状态流转逻辑**。

---

### 6. 分歧检测与最终决策

#### 6.1 分歧检测 `_detect_round_disagreement`

```125:159:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp-backend/app_prismax_data_pipeline/qa_helper.py
def _detect_round_disagreement(round_rows):
    ...
    scores = [int(row._mapping.get("qa_score")) ...]
    gate_snapshots = [
        _collect_gate_snapshot(row._mapping.get("review_result") or {})
        for row in round_rows
    ]
    score_gap = (max(scores) - min(scores)) if scores else 0
    gate_disagreement = False
    for gate_key in QA_GATE_KEYS:
        values = { snapshot.get(gate_key, "") for snapshot in gate_snapshots if snapshot.get(gate_key, "") }
        if len(values) > 1:
            gate_disagreement = True
            break
    has_disagreement = gate_disagreement or score_gap >= 30
    return {
        "gate_disagreement": gate_disagreement,
        "score_gap": score_gap,
        "has_disagreement": has_disagreement,
    }
```

**判定规则：**

- **Gate 分歧**：若任一 gate key 在不同 reviewer 的 snapshot 中出现了不一致的取值（例如有人是 `pass`，有人是 `fail`），则 `gate_disagreement = True`。
- **分数分歧**：若同一轮 `qa_score` 的最大值与最小值之差 `>= 30`，则认为存在显著分歧。
- `has_disagreement = gate_disagreement OR (score_gap >= 30)`。

#### 6.2 汇总决策 `_build_final_decision`

```253:279:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp-backend/app_prismax_data_pipeline/qa_helper.py
def _build_final_decision(round_rows):
    scores = [int(row._mapping.get("qa_score") or 0) for row in round_rows]
    gate_snapshots = [...]
    final_gate = {}
    for gate_key in QA_GATE_KEYS:
        values = { snapshot.get(gate_key, "") for snapshot in gate_snapshots if snapshot.get(gate_key, "") }
        if "fail" in values:
            final_gate[gate_key] = "fail"
        elif "pass" in values:
            final_gate[gate_key] = "pass"
        else:
            final_gate[gate_key] = ""
    all_gate_pass = all(final_gate.get(gate_key) == "pass" for gate_key in QA_GATE_KEYS)
    return {
        "final_gate": final_gate,
        "final_gate_passed": all_gate_pass,
        "final_quality_score": _calculate_median_score(scores),
        "final_upload_vote": "pass" if all_gate_pass else "fail",
    }
```

**汇总逻辑：**

- Gate 聚合：
  - 任一 reviewer 标记 `fail` 则最终 gate 为 `fail`。
  - 否则只要有 `pass` 即视为 `pass`。
  - 若无任何有效值则置空。
- 最终是否通过：所有 gate 均为 `pass` 才视为 `final_gate_passed = True`。
- `final_quality_score`：对所有 reviewer 的 `qa_score` 取 **中位数**。
- `final_upload_vote`：若所有 gate 通过则为 `"pass"`，否则 `"fail"`。

#### 6.3 与 upload 状态联动

在 `submit_upload_qa_review` 的 DB 事务中：

```861:887:/Users/wanxin/PycharmProjects/WORK/Prismax/app-prismax-rp-backend/app_prismax_data_pipeline/app.py
round_required = QA_REVIEWER_COUNT_BY_ROUND.get(qa_round, 1)
disagreement = _detect_round_disagreement(round_rows)
...
if len(round_rows) >= round_required:
    if qa_round == 3:
        next_status = QA_ROUND_SUCCESS_STATUS[3]
        final_decision = _build_final_decision(round_rows)
    else:
        next_status = (
            QA_ROUND_FAILED_STATUS[qa_round]
            if disagreement["has_disagreement"]
            else QA_ROUND_SUCCESS_STATUS[qa_round]
        )
        if not disagreement["has_disagreement"]:
            final_decision = _build_final_decision(round_rows)
    UPDATE data_uploads SET status = next_status WHERE upload_id = :upload_id
```

**行为总结：**

- 如果当前轮次尚未达到所需 reviewer 数：仅插入 `data_qa_sessions`，不更新 `data_uploads.status`。
- 当某轮 reviewer 数 **达到或超过** `round_required`：
  - 第 1 / 2 轮：
    - 若 `has_disagreement = True`：
      - `data_uploads.status` 更新为 `REVIEW_FIRST_ROUND_FAILED` / `REVIEW_SECOND_ROUND_FAILED`。
      - 不生成 `final_decision`（前端返回中该字段为 `null`）。
    - 若 `has_disagreement = False`：
      - `status` 更新为对应 `*_SUCCEEDED`。
      - 计算 `final_decision`（包含 gate 汇总、最终 vote、最终分数）。
  - 第 3 轮（专家仲裁）：
    - 无论是否有分歧，直接标记为 `REVIEW_THIRD_ROUND_SUCCEEDED`。
    - 一定计算 `final_decision`。

接口返回中包含：

- `round_review_count` / `round_required_review_count` / `round_complete`。
- `disagreement`：详述 gate / score 差异。
- `final_decision`：若该轮完成且条件满足则为对象，否则为 `null`。
- `upload_status` / `status_updated`：当前 upload 状态及是否在本次请求中发生变化。

---

### 7. QA Review 端到端流程梳理

下面是一次典型的 QA 审核生命周期（假设最终在第 2 轮才达成一致）的典型路径：

1. **数据就绪**
  - Data Worker 处理完 episode，将各 episode 标为 `DERIVED_READY`，并更新 upload 的 `status` 为 `DERIVED_READY`。
2. **第 1 轮（普通 QA）**
  - 普通 QA 调用 `GET /data/qa/uploads`，看到 `DERIVED_READY` 的 upload。
  - 点击进入某个 upload，调用 `GET /data/qa/uploads/<upload_id>/episodes` 获取采样 episode 列表及视频 URL。
  - 完成打分与 gate 标记后，调用 `POST /data/qa/uploads/<upload_id>/review` 提交 review。
  - 当第 1 轮 reviewer 数达到 3：
    - 若存在 gate / 分数分歧：upload 状态变为 `REVIEW_FIRST_ROUND_FAILED`。
    - 否则：upload 状态变为 `REVIEW_FIRST_ROUND_SUCCEEDED`，流程结束。
3. **第 2 轮（Senior QA）**
  - 若第 1 轮失败，Senior QA 的队列中会优先看到 `REVIEW_FIRST_ROUND_FAILED` 的 upload。
  - 其余流程与第 1 轮类似：同样是对同一批 episode 做 review。
  - 当第 2 轮 reviewer 数达到 2：
    - 若仍存在分歧：upload 状态变为 `REVIEW_SECOND_ROUND_FAILED`。
    - 否则：upload 状态变为 `REVIEW_SECOND_ROUND_SUCCEEDED`，流程结束。
4. **第 3 轮（Expert QA，仲裁）**
  - 若第 2 轮失败，Expert QA 队列优先显示 `REVIEW_SECOND_ROUND_FAILED`。
  - Expert QA 进行最终仲裁 review。
  - 一旦第 3 轮完成（只需 1 人），upload 状态更新为 `REVIEW_THIRD_ROUND_SUCCEEDED`，并生成最终决策。

从整体看，**低级别 QA 负责广覆盖，高级别 QA 负责处理有分歧的复杂 case，专家 QA 负责最终仲裁**，形成一个三级质检闭环。

---

### 8. 对前端 / QA 工具的对接建议

- **认证与角色**
  - 所有 QA 相关接口都依赖统一的 token → user → `user_role` → QA 角色映射。
  - 确保用户在登录后能正确拿到 `hash_code` 形式的 token，并在所有请求中带上 `Authorization: Bearer <token>`。
- **统一的样本集展示**
  - 前端展示给 QA reviewer 的 episode 列表应当完全来自  
  `GET /data/qa/uploads/<upload_id>/episodes` 返回的 `data` 与 `meta.sampled_episode_id`。
  - `review_result.sampled_episode_id` 应该与该 meta 中的数组保持一致，避免因误操作导致 400。
- **严格遵守 `review_result` 结构**
  - 可以在前端用一个固定的 schema（比如 TypeScript 类型 / JSON Schema）来约束表单输出，映射到  
  `QA_GATE_KEYS` 与 `QA_SCORE_KEYS`，并自动生成 `upload_vote` 与 `upload_score` 字段。
- **友好处理错误返回**
  - 对于 400 错误，后端会返回明确的 `msg`，前端可直接弹窗给 QA 同学，帮助定位是「sample mismatch」还是「字段格式不对」。
  - 对于 409 错误（已经审核过），前端可提示「你已经审过该上传」，并刷新队列。

以上即为 `app-prismax-rp-backend` 中 **Data QA Review** 的完整实现逻辑概览，后续若规则有变更（如抽样比例调整、gate/score 维度扩展），建议同步更新本文档以保持前后端与 QA 流程的一致理解。