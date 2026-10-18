# QA Review Dashboard — Developer Handoff

Admin portal page (fifth tab: **QA Review**). The HTML file is a self-contained visual prototype — all data is mocked inline. This doc describes what to build against real backend data.

## Page structure

Three stacked regions inside the admin shell:

1. **Summary cards** (3) — top-level counts + hours
2. **QA session status** — two independent bar charts
3. **Review status of uploads** — filterable table with a row-detail modal

Design tokens (dark theme, CSS vars, accent colors, radii) are defined in `:root` and reused throughout. New work should pull from these rather than introducing new values. Tier colors are fixed: Explorer = blue, Amplifier = amber, Innovator = purple.

---

## 1. Summary cards

Three cards, each showing an **upload count** (primary) and a **total hours** figure (secondary), plus a subline.

| Card | Count | Hours | Subline |
|---|---|---|---|
| Total uploads | all uploads | sum of upload hours | — |
| Review complete | count done | hours done | % of uploads · % of hours |
| Under review | count in progress | hours in progress | % of uploads · % of hours |

Notes for backend:
- Complete + Under review should reconcile to Total for both counts and hours.
- Confirm the meaning of "hours" — currently interpreted as **captured demonstration hours contained in the uploads**, not reviewer time spent. The label should reflect whichever is correct.
- Percentages are computed two ways (by upload count and by hours); they will diverge with real data.

---

## 2. QA session status — two charts

Side by side, **each with its own independent time-span toggle** (D / W / M):

- **D** = last 7 days
- **W** = last 8 weeks
- **M** = last 6 months

The two charts do not share state — a user can view sessions by week and reviewers by month simultaneously. (Year was intentionally removed for now.)

**Chart A — Sessions reviewed:** single-series bar chart, count of QA review sessions completed per bucket.

**Chart B — Reviewers participating:** stacked bar chart, count of distinct reviewers per bucket, **segmented by membership tier** (Explorer / Amplifier / Innovator). Legend shown above the plot.

Backend: expose an aggregation endpoint keyed by granularity (`day` | `week` | `month`) returning labeled buckets. Sessions and reviewer-by-tier are the same time buckets, so ideally one endpoint serves both. The three spans should be aggregation windows over the same underlying data, not separate stores, so totals stay consistent across views.

---

## 3. Review status of uploads

### Table columns
`Upload ID` · `Uploaded time` (mm-dd-yy) · `Machine type` · `Round` · `Final QA score` · `Review progress` · `Status`

- **Final QA score** — shown only when review is complete; otherwise `—`. Color thresholds: green ≥ 85, amber 75–84, red < 75.
- **Review progress** — progress bar + `n/target` (target currently 90). Bar turns green at completion. Confirm whether the denominator is a target number of episode-reviews or distinct episodes — this changes the fraction math.
- **Status** — two states only: *Review complete*, *Under review*. **Queued does not exist yet** — do not add it.

### Filters (all combine with each other + search)
- **Search** — by Upload ID
- **Machine type** — Piper, TOK2, YAM, Ego station, Humanoid (drive from real machine registry)
- **Review round** — Round 1 / 2 / 3 (three rounds total)
- **Status** — Review complete / Under review
- **Export CSV** — exports the current filtered view

Result count ("N uploads") updates live as filters change.

Round semantics to confirm: currently each upload belongs to a single round. If uploads move *through* rounds (1→2→3), decide whether the filter means "currently in round N" or should show cross-round history.

### Row detail modal (click any row)
Opens a modal for that upload. Header shows: Upload ID, machine type, uploaded time, status, review count, final QA score.

Body lists each **reviewed episode**. Under each episode:
- episode name + reviewer count + average score
- a table of individual reviewers: **User ID**, **tier** (colored dot), **verdict** (Pass/Fail), **QA score** (same color thresholds)

Backend needs: per upload → episodes reviewed → per episode → list of `{userId, tier, verdict, score}`. Verdict is currently derived from score (≥70 = pass) — if the backend stores an explicit pass/fail vote separate from the numeric score, surface that instead. Empty state ("No episodes reviewed yet") renders when an upload has zero reviews.

Modal closes via X, backdrop click, or Escape.

---

## Mock data to replace

Everything in the `<script>` block is placeholder: `chartData` (day/week/month buckets), the `mkRow` generator (upload rows), and `buildEpisodes` (seeded fake reviewers). Swap these for real API calls. The seeded RNG in `buildEpisodes` exists only to keep the mock stable across opens; drop it once wired to real data.

## Placeholder / dev-only elements
- The other four admin tabs (General Admin, VLA Admin, Data Download, Video Duplicates) are visual only here; they route to existing pages in the real app. Only QA Review is active.
