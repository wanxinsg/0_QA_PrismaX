# MP4-format episodes → Luma: delivery code and process

This folder collects the code that takes an **MP4+MCAP** episode
(`episodes.episode_format = 'mp4'`) from upload to Luma's bucket, with an
explanation of every step.

> **These are copies. Do not edit or run them here.** Snapshot taken
> 2026-09-23 from branch `fix/luma-serial-letter-guard` @ `7554497` *plus
> uncommitted working-tree changes*. The live code is at the paths listed
> below, and it imports `staging`, `webui`, etc. from the repo root. The
> files in `excerpts/` are line ranges cut out of larger modules and will not
> import on their own; each one's header names its source file and lines.

## Contents

| Here | Canonical location | Role |
|---|---|---|
| `core/submit_to_luma.py` | `upload/submit_to_luma.py` | Selects candidates, applies rig profiles, stages files, uploads, records the delivery. CLI entry point too. |
| `core/luma_mcap_transform.py` | `upload/luma_mcap_transform.py` | Rewrites a **copy** of the mcap: gripper normalisation, camera-topic renames, `/task_info` normalisation. |
| `core/gcloud_run.py` | `upload/gcloud_run.py` | Runs `gcloud` with a timeout and kills the whole process group if it hangs. |
| `core/luma_video_crop.py` | `upload/luma_video_crop.py` | Crops stereo video to one eye. **Not used for mp4** (single-view), but `submit_to_luma` imports it. |
| `excerpts/quota.py` | `upload/submit_svo2_to_scale.py` L666-938 | Requested-hours quota (`task_quota`, `apply_task_quota`, `quota_rows`), shared with Scale. |
| `excerpts/ingest_derive_format.py` | `webui/ingest_api.py` L173-185 | How an upload is tagged `mp4`. |
| `excerpts/postprocess_mp4.py` | `workers/svo2/process_svo2.py` | MP4 post-processing (L1/mcap registered in place, L2 transcode, length). |
| `excerpts/l2_transcode_mp4.py` | `workers/svo2/svo2_convert.py` L427-465 | The L2 preview transcode. Only used for review, not delivered. |
| `excerpts/job_webui_luma_spec.py` | `webui/process_jobs.py` L1286-1378 | The `luma` JobSpec that both UIs use to run the delivery. |
| `excerpts/job_webui2_kinds.py` | `webui2/jobs/kinds.py` | The `upload_luma` and `verlet_bio_ingest` kinds: which resources each needs and how it is wired. |
| `excerpts/job_webui2_schedule.py` | `webui2/jobs/schedule.py` L1-73 | The seeded daily 08:00 postprocess → `upload_luma` pair. |
| `ingest/bio_ingest.py` | `workers/verlet/bio_ingest.py` | verlet only: pulls episodes from the supplier's R2 bucket and handles gripper calibration. |
| `migrations/*` | `migration/*` | One-off fixes applied to already-delivered mp4 episodes (see [History](#history)). |
| `tests/*` | `tests/*` | Tests for the delivery code (see [Tests](#tests)). |

## The pipeline at a glance

```
supplier upload                     post-process                    deliver
─────────────────                   ──────────────                  ───────────────────────────────
cam_high.mp4  ┐                     L1 = raw mp4s (aliased, no       find_candidates()  eligibility + rig profile
cam_left.mp4  ├─ POST /episodes ──▶      re-encode)              ──▶ apply_task_quota() requested hours
cam_right.mp4 │  episode_format      mcap = raw mcap (aliased)       deliver_episode():
<n>.mcap      │  = 'mp4'             L2 = 480p previews (review)       transform_mcap  → tmp
[*.urdf]      ┘                      length_seconds from cam_high      stage renamed    → tmp (symlinks)
                                                                       gcloud storage cp → gs://prismax-raw-luma/<id>/
                                                                       customer_statuses: PENDING, batch N
```

## 1. Ingest: how an episode becomes `mp4`

Two MP4 rigs deliver to Luma. They have different gripper conventions, so
they are handled differently:

| Rig `(supplier, format)` | How it arrives | Leader gripper as recorded |
|---|---|---|
| `yun` / `mp4` | Uploaded through `client/staging_client.py` → `POST /episodes` | Already normalised, **0.0 = closed**, 1.0 = open |
| `verlet` / `mp4` | `bio_ingest.py` pulls it from the supplier's Cloudflare R2 bucket (`prisma-bio-batch3`) and registers it through the same upload API | **Raw encoder radians.** The zero point and span change from episode to episode. |

`_derive_format` tags an upload `mp4` if any raw file ends in `.mp4`. Each
upload contains one single-view MP4 per camera (`cam_high`, `cam_left`,
`cam_right`) and one telemetry `.mcap`. The mcap is named by the rig's own
numbering (`0.mcap`, `64.mcap`, …). A yun Biology Lab upload from staging
27437 onward also includes a `.urdf`. Ingest registers all of these as
`kind='raw'`.

**verlet only:** calibration. Delivery needs each episode's
`(closed, open)` gripper values. Since 2026-09-10 they come from a
`gripper_limits` metadata record inside the verlet MCAP. Older exports
(upload 396 and most of 400) use a `*_gripper_limits.json` sidecar instead.
It is registered as `kind='metadata'`, not `raw`, because RAW can be
reclaimed and a delivery precondition must outlive it. The
`verlet_bio_ingest` job ingests new episodes and then checks that
*every* verlet episode's calibration can be read. It uses the same loader
as delivery (`submit_to_luma.gripper_limits`), so a calibration gap fails
during ingest rather than silently leaving the episode undeliverable. It
needs `R2_ENDPOINT`, `R2_ACCESS_KEY` and `R2_SECRET_KEY`.

## 2. Post-process: products, with almost no re-encoding

`process_svo2.process_episode_any` detects the format and sends mp4
episodes to `process_mp4_episode`:

* **L1** = each raw `cam_*.mp4`, **registered in place** as `video_l1`
  under the same path as the RAW row. Nothing is copied or re-encoded.
  Because L1 is an alias of RAW, RAW must never be reclaimed for these
  episodes (`staging/reclaim.py` enforces this with the alias test).
* **mcap** = the raw telemetry mcap, also registered in place.
* **L2** = a 480p h264 preview per camera (`high` / `left` / `right`). It is
  used only by the review UI and is **not delivered**.
* **`length_seconds`** is read from `cam_high`. The quota counts in seconds,
  and an episode without a length is held back as `unknown_length`. "Quick
  Process" fills the length in without transcoding.

## 3. Deliver: `submit_to_luma.py`

### 3a. Candidate selection: `find_candidates(store, supplier=, task_name=, robot_type=)`

The scope filters go into the SQL `WHERE` clause, not a filter applied
afterward. Selection is cheaper when the scope is narrow. An episode is
deliverable when all of the following hold:

1. `review_status != 'FAIL'`.
2. No Luma (`LUMA_CUSTOMER_ID = 3`) `customer_statuses` row has a
   `customer_upload_time` yet. This makes delivery idempotent: a delivered
   episode is never offered again.
3. The format is not listed in `PAUSED_FORMATS`. That list is empty today;
   `mp4` was paused from 2026-08-25 until the serial question was settled.
4. It has an `mcap` and at least one `video_l1`, and both are on local disk.
   An episode whose products were deliberately reclaimed (row kept,
   `size_bytes` NULL, file gone) is silently out of scope. A file missing any
   other way is reported as `incomplete` with a reason.
5. Its rig has a **`RigProfile`**, keyed on `(supplier, episode_format)`.
   The key is the rig, not the supplier; see [History](#history). A rig
   with no profile is held back (`no delivery profile for rig …`). There is
   deliberately no default.
6. Gripper limits exist for **both** leader topics. For `yun/mp4` this is
   the constant `MP4_NORMALISED_LIMITS = (0.0, 1.0)`. For `verlet/mp4` it
   is this episode's own calibration: the MCAP record first, then the
   sidecar. If the MCAP record exists but is invalid, the episode is held
   back and the sidecar is *not* tried. Otherwise the reason is
   `gripper calibration missing`.

A `.urdf` is added to the file list if the episode has one on disk. It is
never a precondition: a missing URDF means the episode ships without one,
not that it is held back.

### 3b. Quota: `task_quota` + `apply_task_quota` (`excerpts/quota.py`)

Luma's requested hours come from `customer_task_hours` and are bucketed by
`(task_name, robot_type)`. Delivered hours are the sum of episodes with a
Luma upload time and status PASS or PENDING. Candidates are walked oldest
first (by `staging_id`). An episode is kept while its bucket has hours
left, including the one that crosses the line. The rest are excluded as
`no_quota`, `quota_met` or `unknown_length`. The CLI's `--ignore-quota`
flag skips this step.

### 3c. `deliver_episode(store, candidate, batch_id=)`

All transforms happen in a temp dir. **Our stored copies are never
modified.**

1. **mcap → `transform_mcap`** (`core/luma_mcap_transform.py`). This is a
   byte-level patch. Schemas, channels, timestamps and sequence numbers are
   kept; only these things change:
   * **Leader gripper**: on `/robot/arm_{left,right}_leader/joint_states`,
     the unnamed 7th `position` entry becomes
     `(x − closed) / (open − closed)`. Luma's convention is **closed 0.0,
     open 1.0**. The `velocity` entry becomes `v / (open − closed)`. Follower
     topics are left alone.
     * `yun/mp4`, limits `(0, 1)`: the values pass through unchanged.
       (Inverting them was the 2026-09-03 bug.)
     * `verlet/mp4`: the transform runs in `strict` mode. Values are clamped
       into [0, 1], and if more than 1% of an arm's messages fall outside
       its limits, delivery is **refused** with `GripperLimitsError`. That
       usually means the limits belong to a different export.
   * **Camera topics**: `cam_high|cam_left|cam_right …/camera_info` are
     renamed to `high|left_wrist|right_wrist …`, the spelling the SVO2 corpus
     already uses.
   * **`/task_info`** is reduced to exactly
     `{task, task_description, serial_number}`:
     * yun: `task_name` → `task`, `task_description` is set to the task
       label (replacing the operator-language instruction), and
       `task_id` → `serial_number`. The serial goes through
       `canonical_serial`, which inserts the default task letter `B` into
       unlettered **`YAM-BIO-`** ids only (`YAM-BIO-016` →
       `YAM-BIO-B-016`). Every other id, such as `BIO-NEW-006`, passes
       through untouched.
     * verlet: the payload is rebuilt. `task` and `task_description` are
       the task label, and `serial_number` is the subtask prose with the
       `BIO-NEW-<n> ·` collection prefix stripped. The rebuild is needed
       because `task_id` is `"0"` on every verlet episode.
2. **Videos**: mp4 is not in `STEREO_FORMATS`, so the L1s are delivered
   as-is with no crop and no re-encode. The format is what decides this: a
   mono 1920-wide frame cannot be told apart from a stereo one by its
   dimensions.
3. **Stage under delivered names** (`_stage_delivered_names`, using
   symlinks in the temp dir so large videos are never duplicated):

   | local | delivered |
   |---|---|
   | `<n>.mcap` (transformed) | `telemetry.webui.mcap` |
   | `cam_high.mp4` | `cam_high.mp4` |
   | `cam_left.mp4` | `cam_left_wrist.mp4` |
   | `cam_right.mp4` | `cam_right_wrist.mp4` |
   | `<robot>.urdf` | unchanged (the name identifies the robot model) |

   `delivered_basename()` is the only place these names are decided.
   Keeping them stable matters: if a delivered object is renamed, Luma sees
   a new file and the old one is left orphaned.
4. **Upload**: one `gcloud storage cp` into
   `gs://prismax-raw-luma/<staging_id>/`, with 3 attempts. Each attempt is
   limited to 600 s by `gcloud_run`, which kills the whole process group,
   because a hung cp once stalled the whole job.
5. **Record**: only after every file has landed,
   `customer_statuses(staging_id, 3)` is set to
   `customer_task_status = PENDING`, `customer_upload_batch_id = N`,
   `customer_upload_time = now`. If a delivery is interrupted before this,
   the whole episode is retried on the next run. PENDING means "handed over,
   verdict outstanding". Luma never returns verdicts, and PENDING counts
   against the quota.

The batch number is one past Luma's current maximum, resolved once per run
(`resolve_batch_id`).

## 4. How it is run

**webui2 (production on :80)**: the `upload_luma` job kind uses resources
`cpu + gpu + upload`. The GPU is for the svo2 crop; an mp4-only run holds
it anyway. It can be scoped by `supplier` / `task_name` / `robot_type` /
`upload_id` / `staging_ids` / `limit`. Delivery can be triggered three ways:

* manually from the Jobs tab;
* by the seeded daily **08:00 America/Los_Angeles** pair: `postprocess`,
  then `upload_luma`, scoped to `yun` / "Block manipulation". That task is
  SVO2 today, but the pair is the template for adding a scheduled mp4 scope;
* by a standing rule or a delivery order (`auto_rules`, `delivery_orders`).

The job runs `webui/process_jobs._LUMA_SPEC`: `prepare` resolves the batch,
`discover` runs `find_candidates` + quota, and `process_one` runs
`deliver_episode`. The legacy `actuate-webui` service (the rollback target)
uses the same spec.

**CLI** (from the repo root, with `STAGING_DB_URL` set):

```bash
python upload/submit_to_luma.py --dry-run          # count and list, copy nothing
python upload/submit_to_luma.py --limit 3 --yes    # canary
python upload/submit_to_luma.py --yes              # full run, quota applied
```

The CLI has no scope flags, so it covers every rig. To deliver only mp4
episodes, use the job with `supplier=` (and `task_name=` if needed).

**Environment**: `STAGING_DB_URL`, and a `gcloud` login with write access
to `gs://prismax-raw-luma`.

## 5. Checking a delivery

* `gcloud storage ls gs://prismax-raw-luma/<staging_id>/` should show
  `telemetry.webui.mcap`, `cam_high.mp4`, `cam_left_wrist.mp4` and
  `cam_right_wrist.mp4`, plus a `.urdf` if the upload had one.
* Download the mcap and check that `/task_info` has exactly the three keys,
  that the camera topics are `high` / `left_wrist` / `right_wrist`, and that
  the leader gripper reads ≈0 when the wrist video shows the jaws shut.
  Gripper polarity can only be confirmed from the video; the numbers alone
  cannot show it.

## History

These are the mp4-specific incidents. Each one explains a rule above, and
each has a migration in `migrations/`.

| Date | What went wrong | Fix |
|---|---|---|
| 2026-08-25 | mp4 deliveries went out in the rig's own shape: `cam_*` topics, the operator-language `task_description`, `task_id` instead of `serial_number`, and `<n>.mcap` names. | The transform learned to rename and normalise. `unship_luma_mp4_2026_08_25.py` withdrew the malformed deliveries, `reshape_luma_mp4_mcaps_2026_08_25.py` overwrote delivered mcaps in place, and mp4 was paused (`PAUSED_FORMATS`) until the serial letter was confirmed. |
| 2026-08-26 | Episodes that were already delivered had no URDF. | `backfill_luma_urdf_2026_08_26.py` added it without re-recording the delivery. |
| 2026-09-03 | The profile was keyed on supplier, so `yun/mp4` got the SVO2 rig's `1 − x` and **979 episodes** shipped with the gripper inverted. | `RIG_PROFILES` is now keyed on `(supplier, format)`. `redeliver_luma_mp4_gripper_2026_09_03.py` rewrote the delivered mcaps from our local copies. |
| 2026-09-03 | verlet publishes raw encoder values and needs per-episode calibration. | `register_verlet_gripper_sidecars_2026_09_03.py` added the sidecars. Later exports carry an in-MCAP record. |
| 2026-09-09 | 55 verlet episodes had their wrist videos under each other's names. | `swap_luma_wrist_names_2026_09_09.py` renamed the two objects in the bucket. Our copies, and so any re-delivery, still carry the crossed names. |
| 2026-09-10 | `canonical_serial` inserted `B` into every `<prefix>-<n>`, which produced `BIO-NEW-B-006` on 1,920 yun episodes. | Lettering is now limited to the `YAM-BIO-` family (commit `7554497`). `redeliver_luma_serial_2026_09_10.py` rewrote those mcaps. |

Two rules came out of these incidents:

* Fixes to delivered data **re-derive from the local copy** and overwrite
  one object. They never patch the bucket copy, so running a fix twice gives
  the same bytes.
* Each fix checks that the rewrite differs from what was delivered **only
  in the field it is correcting**.

## Tests

From the repo root:

```bash
.venv/bin/python -m pytest tests/test_luma_mcap_normalise.py tests/test_luma_video_crop.py tests/test_verlet_bio_ingest.py
```

* `test_luma_mcap_normalise.py` covers the mp4 topic renames, the
  `task_id` → `serial_number` rename, `YAM-BIO`-only lettering, the two
  normalised rigs being at opposite ends, closed delivered as 0 on every
  rig, strict refusal for calibrated rigs, and the three-key `/task_info`
  for every rig.
* `test_luma_video_crop.py` covers the delivery module itself: the URDF
  rides along but is never required, an unknown rig is never delivered, a
  calibrated rig becomes deliverable once limits are on file, the MCAP
  record is preferred over the sidecar, and the scope is applied inside the
  query. Its crop tests are svo2-only.
* `test_verlet_bio_ingest.py` covers bucket discovery and sidecar splitting
  for verlet.
