# EXCERPT -- not importable on its own.
# Source: webui/process_jobs.py, lines 1286-1378 (branch fix/luma-serial-letter-guard @ 7554497 + uncommitted working tree, 2026-09-23).
# The 'luma' JobSpec (prepare/discover/process_one) that both UIs run the delivery through.

def _luma_prepare(store, params: dict, log) -> dict:
    """Resolve the delivery batch number once for the whole run."""
    import submit_to_luma as luma

    batch_id = luma.resolve_batch_id(store, params.get("batch_id"))
    log(f"Luma delivery batch {batch_id}")
    return {"batch_id": batch_id}


def _luma_discover(store, params: dict) -> list[int]:
    """Episodes to deliver to Luma this run, oldest first.

    Eligibility **already narrowed** (the supplier/embodiment view dropdowns and
    ``task_name`` for the daily scheduled deliveries go into the candidate query
    itself), then an optional explicit id selection, and the requested-hours
    quota applied **last** -- on exactly the set this run would deliver, so
    narrowing to one supplier cannot leave hours reserved for episodes that were
    filtered away.  The ordering that matters is unchanged; what moved is where
    the scope is applied, and ``_scale_discover`` still filters after the fact.
    """
    import submit_to_luma as luma

    _log = params.get("_log") if callable(params.get("_log")) else None
    # Narrowed in the candidate query, not over its result: eligibility stats
    # every product on disk, so the daily verlet/"Biology Lab" sweep used to
    # read all 24k undelivered episodes to find its few hundred.
    scope = {key: str(params.get(key) or "").strip()
             for key in ("supplier", "task_name", "robot_type")}
    candidates, incomplete = luma.find_candidates(store, **scope)
    stated = ", ".join(f"{key}={value!r}"
                       for key, value in scope.items() if value)
    if stated and _log:
        _log(f"scoped to {stated}: {len(candidates)} candidate(s)")

    wanted = params.get("staging_ids")
    if wanted:
        wanted_ids = {int(sid) for sid in wanted}
        candidates = [c for c in candidates if c.staging_id in wanted_ids]
        if _log:
            matched = {c.staging_id for c in candidates}
            missing = sorted(wanted_ids - matched)
            _log(f"selection: {len(wanted_ids)} staging_id(s) requested, "
                 f"{len(matched)} eligible")
            if missing:
                shown = ", ".join(str(s) for s in missing[:20])
                more = f" (+{len(missing) - 20} more)" if len(missing) > 20 else ""
                _log(f"  skipped {len(missing)} not eligible for Luma "
                     f"(not post-processed, already delivered, review FAIL, "
                     f"or no such episode): {shown}{more}")

    quota = luma.task_quota(store, luma.LUMA_CUSTOMER_ID)
    candidates, excluded = luma.apply_task_quota(candidates, quota, log=_log)

    limit = params.get("limit")
    if limit is not None:
        candidates = candidates[: int(limit)]
    prepared = params.setdefault("_prepared", {})
    prepared["candidates"] = {c.staging_id: c for c in candidates}
    prepared["incomplete"] = list(incomplete)
    prepared["excluded"] = excluded
    prepared["quota"] = quota
    return [c.staging_id for c in candidates]


def _luma_process_one(store, sid: int, params: dict, log) -> dict:
    import submit_to_luma as luma

    prepared = params.get("_prepared") or {}
    candidate = (prepared.get("candidates") or {}).get(sid)
    if candidate is None:
        raise RuntimeError(f"no candidate found for staging_id {sid}")
    return luma.deliver_episode(
        store, candidate, batch_id=prepared.get("batch_id") or 1, log=log)


_LUMA_SPEC = JobSpec(
    name="luma-upload",
    discover=_luma_discover,
    process_one=_luma_process_one,
    prepare=_luma_prepare,
)


_SPECS: dict[str, JobSpec] = {
    "svo2": _SVO2_SPEC,
    "ego": _EGO_SPEC,
    "gcs": _GCS_SPEC,
    "scale": _SCALE_SPEC,
    "ego_scale": _EGO_SCALE_SPEC,
    "ego_preview": _EGO_PREVIEW_SPEC,
    "luma": _LUMA_SPEC,
    "vla": _VLA_SPEC,
}
