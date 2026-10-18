# Data QA Rules Summary

## 1. Scope and Entry Conditions

- QA review is upload-level (not single-episode-level) and stored as a QA session record.
- A reviewer can submit at most one QA session per `upload_id` (duplicate submit returns 409).
- Upload can enter QA queue from:
  - `DERIVED_READY`
  - `DERIVED_PARTIALLY_READY`
- Sampling and review source episodes only include episodes with status `DERIVED_READY`.

## 2. QA Roles and Queue Priority

Allowed roles:

- `qa`
- `senior qa`
- `expert qa`

Queue rules by role:

- `qa`: round 1 only (`DERIVED_READY` first, then `DERIVED_PARTIALLY_READY`).
- `senior qa`: round 2 first (`REVIEW_FIRST_ROUND_FAILED`), then round 1.
- `expert qa`: round 3 first (`REVIEW_SECOND_ROUND_FAILED`), then round 2, then round 1.

Access boundary note:

- Current review endpoints are QA-role only (`qa access required` for non-QA roles).
- `GET /data/qa/get-validator-access-data` is token-based and not limited to QA roles.

## 3. Round Structure and Completion Gates

Upload QA status flow:

```text
                        ┌──────────────────────┐
                        │     DERIVED_READY     │  ← initial
                        └──────────┬───────────┘
                                   │ 3 qa reviewers submit (round 1)
                    ┌──────────────┴──────────────┐
                    │ no disagreement             │ disagreement
                    ▼                             ▼
     REVIEW_FIRST_ROUND_SUCCEEDED    REVIEW_FIRST_ROUND_FAILED
                                                  │
                                                  │ 2 senior qa reviewers submit (round 2)
                                   ┌──────────────┴──────────────┐
                                   │ no disagreement             │ disagreement
                                   ▼                             ▼
                    REVIEW_SECOND_ROUND_SUCCEEDED  REVIEW_SECOND_ROUND_FAILED
                                                              │
                                                              │ 1 expert qa reviewer submits (round 3)
                                                              ▼
                                                  REVIEW_THIRD_ROUND_SUCCEEDED
```

Role-to-queue mapping:

| QA role | Priority 1 | Priority 2 | Priority 3 |
| ------- | ---------- | ---------- | ---------- |
| `qa` | `DERIVED_READY` (round 1) | — | — |
| `senior qa` | `REVIEW_FIRST_ROUND_FAILED` (round 2) | `DERIVED_READY` (round 1) | — |
| `expert qa` | `REVIEW_SECOND_ROUND_FAILED` (round 3) | `REVIEW_FIRST_ROUND_FAILED` (round 2) | `DERIVED_READY` (round 1) |

- Round 1: requires 3 reviewers.
- Round 2: requires 2 reviewers.
- Round 3: requires 1 reviewer.

Round completion behavior:

- If required reviewer count is not met, upload status stays unchanged.
- If reviewer count is met:
  - round 1/2:
    - disagreement -> mark round failed status and escalate to next round queue.
    - no disagreement -> mark round success and produce final decision.
  - round 3:
    - always mark `REVIEW_THIRD_ROUND_SUCCEEDED` and produce final decision.

Status mapping:

- round 1 success: `REVIEW_FIRST_ROUND_SUCCEEDED`
- round 1 failed (disagreement): `REVIEW_FIRST_ROUND_FAILED`
- round 2 success: `REVIEW_SECOND_ROUND_SUCCEEDED`
- round 2 failed (disagreement): `REVIEW_SECOND_ROUND_FAILED`
- round 3 complete: `REVIEW_THIRD_ROUND_SUCCEEDED`

## 4. Sampling Rules

For non-expert roles, sample is deterministic by `(upload_id, qa_round)`:

- `sample_size = min(total_derived_episodes, max(5, ceil(total_derived_episodes * 0.05)))`
- seed strategy uses SHA-256 and fixed suffix `qa-sample-v2`.
- sample IDs are stable per upload+round (helps reviewer consistency).

For `expert qa`:

- can load all derived episodes.
- submitted `sampled_episode_id` must be a subset of upload derived episodes.

For non-expert roles on submit:

- submitted `sampled_episode_id` must exactly match backend reference sample for that round.

## 5. Rubric (v2)

### Gate keys (`pass`/`fail`)

- `is_camera_feed_clear`
- `is_task_completed`
- `is_robot_hand_visible`
- `are_cameras_in_sync`

Episode vote rule:

- if any gate fails -> `episode_vote = fail`
- otherwise -> `episode_vote = pass`

### Score keys (integer `1..5`)

- `robot_control_quality`
- `movement_smoothness`
- `task_completion_speed`
- `task_fully_completed`
- `variation_across_episodes`

Score formulas:

- `episode_score = round((avg(score_items) / 5) * 100)`
- `upload_score = round(avg(all_episode_score))`

## 6. Disagreement Rules

A round has disagreement if either condition is true:

- Gate disagreement: any gate snapshot differs across reviewers.
- Score gap disagreement: `max(qa_score) - min(qa_score) >= 30`.

If no disagreement and reviewer count reached, current round is decisive.

## 7. Final Decision Rules

Final decision is built from decisive round:

- `final_gate`: per gate, if any reviewer snapshot is `fail`, final is `fail`; else `pass`.
- `final_gate_passed`: all final gates are `pass`.
- `final_upload_vote`: `pass` if all final gates pass, else `fail`.
- `final_quality_score`: median of round `qa_score`.

## 8. `review_result` Payload Validation Rules

Backend enforces strict validation on submit:

- `review_result` must be an object.
- `sampled_episode_id` is required, integer-only, unique.
- `result` must be array and length must equal sampled episode count.
- each `result[i].episode_id` must:
  - be integer,
  - belong to `sampled_episode_id`,
  - be unique.
- each gate field must be `pass` or `fail`.
- each score field must be integer in `1..5`.
- `episode_vote` must equal backend-derived vote.
- `episode_score` must equal backend-derived score and be integer `0..100`.
- `upload_vote` must equal derived aggregate vote (`all pass => pass`, else fail).
- `upload_score` must equal derived aggregate score and be integer `0..100`.
- `qa_score` must be integer `0..100`, and when `review_result.upload_score` exists, they must be equal.

## 9. Incentive Rule (Finalized Uploads)

After final decision is produced:

- reviewer is reward-eligible when both are true:
  - reviewer gate snapshot fully matches final gate;
  - `abs(reviewer.qa_score - final_quality_score) <= 8`.
- reward amount: `+100` points per reviewed episode (QA review reward type).

## 10. Safeguard Summary (Bots, Slashing, and Abuse Control)

How the current QA flow prevents low-quality automation and abuse:

- Role-gated access: only QA roles can use review endpoints, reducing open bot surface.
- One reviewer, one submission per upload: prevents spam retries to brute-force outcomes.
- Deterministic sampling with server-side verification: client cannot freely choose episodes (except expert subset rule), so cherry-picking is constrained.
- Strict payload consistency checks: gate/score/vote/aggregate values must match backend recomputation, which blocks fabricated review payloads.
- Multi-reviewer rounds plus disagreement escalation: suspicious or inconsistent reviews are diluted by consensus and escalated to higher-level reviewers.
- Conservative final gate merge: any fail signal is preserved in final gate, limiting optimistic manipulation.

Slashing status in current implementation:

- There is no explicit negative-point slashing rule in this flow.
- The practical penalty is reward denial: reviewers only receive points when their gate snapshot matches final gate and score is close to final score.
- This creates a slashing-like incentive: inaccurate or noisy reviews do not earn rewards, while aligned high-quality reviews do.
