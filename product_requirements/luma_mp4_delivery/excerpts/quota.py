# EXCERPT -- not importable on its own.
# Source: upload/submit_svo2_to_scale.py, lines 666-938 (branch fix/luma-serial-letter-guard @ 7554497 + uncommitted working tree, 2026-09-23).
# Requested-hours quota helpers, shared with Scale; submit_to_luma imports task_quota / apply_task_quota / quota_rows from here.

# ── Requested-hours quota ────────────────────────────────────────────────────
#
# The customer asks for a number of hours *per task and embodiment*
# (``customer_task_hours``, the Task Management tab).  Delivering data for a
# task they never asked for, or piling more hours onto one they have already
# been given in full, is wasted work -- so submission is capped by what is
# still outstanding:
#
#   remaining = requested_hours - hours already delivered to this customer
#
# "Delivered" uses the same definition as the Upload history tab's
# requested-vs-uploaded table: episodes handed to the customer
# (``customer_upload_time`` set) that they have not rejected (PASS/PENDING).
# A FAILed episode does not consume quota -- we still owe those hours.
#
# Buckets are keyed by ``(task_name, robot_type)``, the natural key of the
# requested-hours table: 10 h of "Sort toys by category" on piperx is a
# different ask from 10 h of it on yam, and one must not eat the other's quota.

# Customer verdicts that count against the quota (their own rejections do not).
QUOTA_COUNTED_STATUSES = ("PASS", "PENDING")


def task_quota(store: StagingStore,
               customer_id: int = SCALE_AI_ID) -> dict[tuple[str, str], dict]:
    """Return the quota state per ``(task_name, robot_type)``, in seconds.

    One entry per requested-hours row with ``requested_hours > 0``::

        {("Sort toys by category", "yam"): {
            "requested_s": float, "delivered_s": float, "remaining_s": float}}

    Tasks the customer has not asked for are simply absent -- callers treat a
    missing bucket as "no quota", which is what excludes them from submission.
    """
    db = store.db
    out: dict[tuple[str, str], dict] = {}
    for r in db.query_all(
        "SELECT task_name, robot_type, requested_hours FROM customer_task_hours "
        "WHERE customer_id = ? AND requested_hours > 0",
        (customer_id,),
    ):
        key = (str(r["task_name"] or ""), str(r["robot_type"] or ""))
        out[key] = {
            "requested_s": float(r["requested_hours"] or 0.0) * 3600.0,
            "delivered_s": 0.0,
            "remaining_s": 0.0,
        }
    ph = ", ".join("?" for _ in QUOTA_COUNTED_STATUSES)
    for r in db.query_all(
        "SELECT e.task_name, e.robot_type, "
        "       COALESCE(SUM(COALESCE(e.length_seconds, 0)), 0) AS secs "
        "FROM episodes e JOIN customer_statuses cs "
        "  ON cs.staging_id = e.staging_id AND cs.customer_id = ? "
        " AND cs.customer_upload_time IS NOT NULL "
        f"WHERE cs.customer_task_status IN ({ph}) "
        "GROUP BY e.task_name, e.robot_type",
        (customer_id, *QUOTA_COUNTED_STATUSES),
    ):
        key = (str(r["task_name"] or ""), str(r["robot_type"] or ""))
        bucket = out.get(key)
        if bucket is not None:
            bucket["delivered_s"] = float(r["secs"] or 0.0)
    for bucket in out.values():
        bucket["remaining_s"] = bucket["requested_s"] - bucket["delivered_s"]
    return out


def apply_task_quota(candidates: list[Candidate],
                     quota: dict[tuple[str, str], dict],
                     *, log=None) -> tuple[list[Candidate], list[dict]]:
    """Split candidates into (submittable within quota, excluded).

    Walks ``candidates`` in their given order -- staging_id ascending, so the
    oldest data is delivered first -- and keeps taking episodes for a bucket
    while it has hours left.  The episode that crosses the line **is kept**:
    stopping short would leave the request unfilled, so the run slightly
    exceeds the requested hours rather than under-delivering (as specified).

    Each excluded entry is ``{"staging_id", "task_name", "robot_type",
    "supplier", "length_s", "reason"}`` -- ``length_s`` so callers can report
    the *hours* sitting held back, not just the episode count, and ``supplier``
    so they can say whose data it is -- with ``reason`` one of:

      * ``no_quota``      -- the customer has not requested this (task, robot);
      * ``quota_met``     -- their requested hours are already covered;
      * ``unknown_length`` -- the episode has no ``length_seconds``, so it
        cannot be counted against a quota.  Run Quick Process on it (which
        fills the length in from the source header, no transcoding) and it
        becomes submittable.
    """
    # Spend from a copy: the caller's quota dict stays a description of the
    # database, not of this run.
    left = {k: v["remaining_s"] for k, v in quota.items()}
    kept: list[Candidate] = []
    excluded: list[dict] = []

    def secs_of(c: Candidate) -> float:
        try:
            return float(c.length_s) if c.length_s is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    def drop(c: Candidate, reason: str) -> None:
        excluded.append({
            "staging_id": c.staging_id,
            "task_name": c.task_name,
            "robot_type": getattr(c, "robot_type", "") or "",
            "supplier": getattr(c, "supplier", "") or "",
            "length_s": secs_of(c),
            "reason": reason,
        })

    for c in candidates:
        key = (c.task_name or "", getattr(c, "robot_type", "") or "")
        if key not in left:
            drop(c, "no_quota")
            continue
        if left[key] <= 0:
            drop(c, "quota_met")
            continue
        secs = secs_of(c)
        if secs <= 0:
            # Unmeasurable episodes would ride along without ever consuming
            # quota -- an unbounded overshoot.  Hold them back instead.
            drop(c, "unknown_length")
            continue
        kept.append(c)
        left[key] -= secs

    if log is not None:
        by_reason: dict[str, int] = {}
        for e in excluded:
            by_reason[e["reason"]] = by_reason.get(e["reason"], 0) + 1
        log(f"requested-hours quota: {len(kept)} episode(s) submittable, "
            f"{len(excluded)} held back"
            + (" (" + ", ".join(f"{n} {r}" for r, n in sorted(by_reason.items()))
               + ")" if by_reason else ""))
        for key in sorted({(c.task_name or "",
                            getattr(c, "robot_type", "") or "") for c in kept}):
            q = quota[key]
            queued = sum(float(c.length_s or 0.0) for c in kept
                         if (c.task_name or "",
                             getattr(c, "robot_type", "") or "") == key)
            log(f"  {key[0]!r} [{key[1] or '—'}]: "
                f"{q['delivered_s']/3600:.2f} h delivered of "
                f"{q['requested_s']/3600:.2f} h requested "
                f"-> queueing {queued/3600:.2f} h")
    return kept, excluded


def find_submittable(store: StagingStore, *,
                     customer_id: int = SCALE_AI_ID,
                     respect_quota: bool = True,
                     log=None) -> dict:
    """Candidates that are both deliverable and still within the quota.

    The one entry point every caller (WebUI tab, WebUI job, CLI) should use, so
    the count the reviewer sees and the set the job submits cannot drift apart.
    Returns ``{"candidates", "incomplete", "excluded", "quota"}``.
    """
    candidates, incomplete = find_candidates(store)
    quota = task_quota(store, customer_id) if respect_quota else {}
    excluded: list[dict] = []
    if respect_quota:
        candidates, excluded = apply_task_quota(candidates, quota, log=log)
    return {
        "candidates": candidates,
        "incomplete": incomplete,
        "excluded": excluded,
        "quota": quota,
    }


def quota_rows(quota: dict[tuple[str, str], dict],
               kept: list[Candidate],
               excluded: list[dict]) -> list[dict]:
    """Per-(task, robot) rows for the UI: hours asked, done, left, on hand.

    Only buckets this run has something to say about -- a queued episode, a
    held-back one, or unfilled hours -- so the tab shows a short, actionable
    table rather than every task in the master list.

    Each row carries what the tab colours by: ``queued``/``queued_hours``
    (submittable now), ``held_back``/``held_back_hours`` with a ``held_reasons``
    breakdown (ready on disk but not sendable), and the requested/delivered/
    remaining hours behind that verdict.  Rows are ordered the way an operator
    reads them: what will ship now, then what is stuck over quota (largest pile
    first), then what is still owed but has nothing collected yet.

    ``suppliers`` splits the on-hand episodes by collector::

        [{"supplier": "verlet", "queued": 0, "queued_hours": 0.0,
          "held_back": 880, "held_back_hours": 18.54}, ...]

    Requested and delivered hours are *not* split: the customer asks for hours
    of a (task, embodiment) regardless of who collects them, so only the data
    we are holding can be attributed.  Ordered largest pile first.
    """
    rows: dict[tuple[str, str], dict] = {}

    def row(key: tuple[str, str]) -> dict:
        r = rows.get(key)
        if r is None:
            q = quota.get(key) or {"requested_s": 0.0, "delivered_s": 0.0,
                                   "remaining_s": 0.0}
            r = rows[key] = {
                "task_name": key[0],
                "robot_type": key[1],
                "requested_hours": round(q["requested_s"] / 3600.0, 2),
                "delivered_hours": round(q["delivered_s"] / 3600.0, 2),
                "remaining_hours": round(q["remaining_s"] / 3600.0, 2),
                "queued": 0,
                "queued_hours": 0.0,
                "held_back": 0,
                "held_back_hours": 0.0,
                "held_reasons": {},
                "suppliers": {},
            }
        return r

    def by_supplier(r: dict, supplier: str) -> dict:
        s = r["suppliers"].get(supplier)
        if s is None:
            s = r["suppliers"][supplier] = {
                "supplier": supplier,
                "queued": 0, "queued_hours": 0.0,
                "held_back": 0, "held_back_hours": 0.0,
            }
        return s

    for key, q in quota.items():
        if q["remaining_s"] > 0:
            row(key)
    for c in kept:
        r = row((c.task_name or "", getattr(c, "robot_type", "") or ""))
        hours = float(c.length_s or 0.0) / 3600.0
        r["queued"] += 1
        r["queued_hours"] += hours
        s = by_supplier(r, getattr(c, "supplier", "") or "")
        s["queued"] += 1
        s["queued_hours"] += hours
    for e in excluded:
        r = row((e["task_name"] or "", e["robot_type"] or ""))
        hours = float(e.get("length_s") or 0.0) / 3600.0
        r["held_back"] += 1
        r["held_back_hours"] += hours
        reason = str(e.get("reason") or "")
        r["held_reasons"][reason] = r["held_reasons"].get(reason, 0) + 1
        s = by_supplier(r, str(e.get("supplier") or ""))
        s["held_back"] += 1
        s["held_back_hours"] += hours
    for r in rows.values():
        r["queued_hours"] = round(r["queued_hours"], 2)
        r["held_back_hours"] = round(r["held_back_hours"], 2)
        for s in r["suppliers"].values():
            s["queued_hours"] = round(s["queued_hours"], 2)
            s["held_back_hours"] = round(s["held_back_hours"], 2)
        # Biggest pile first, so the split reads like the table it sits in.
        r["suppliers"] = sorted(
            r["suppliers"].values(),
            key=lambda s: (-(s["queued"] + s["held_back"]), s["supplier"]))

    def sort_key(r: dict) -> tuple:
        if r["queued"]:                                    # ships this run
            return (0, -r["queued_hours"], r["task_name"], r["robot_type"])
        if r["held_back"] and r["remaining_hours"] <= 0:    # over quota / unasked
            return (1, -r["held_back_hours"], r["task_name"], r["robot_type"])
        return (2, -r["remaining_hours"], r["task_name"], r["robot_type"])

    return sorted(rows.values(), key=sort_key)


