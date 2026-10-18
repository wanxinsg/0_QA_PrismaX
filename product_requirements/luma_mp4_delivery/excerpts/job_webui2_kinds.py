# EXCERPT -- not importable on its own.
# Source: webui2/jobs/kinds.py, lines 199-340 (branch fix/luma-serial-letter-guard @ 7554497 + uncommitted working tree, 2026-09-23).
# webui2 kind 'verlet_bio_ingest' (prepare/discover/process_one).

def _verlet_bio_prepare(store, params: Dict[str, Any], log) -> dict:
    """Pull the episodes the supplier has published that we do not hold.

    Ingest happens here, not in ``process_one``, for the same reason the ego
    scan does: an episode has no ``staging_id`` until it has been registered, so
    there is nothing for ``discover`` to return until this has run.  Progress is
    logged per episode -- the run counter belongs to the calibration check
    below, which is the part that has ids to count.
    """
    import bio_ingest

    limit = int(params.get("limit") or 0)
    try:
        s3 = bio_ingest.client()
    except bio_ingest.CredentialsMissing as exc:
        # Not a per-episode failure: without credentials the job can do nothing,
        # and saying so in the first line beats a listing that dies obscurely.
        raise RuntimeError(f"verlet bio ingest: {exc}") from exc

    base: Dict[str, Any] = {}

    log(f"listing s3://{bio_ingest.bucket_name()} ...")
    episodes, excluded, incomplete = bio_ingest.discover(s3, log=log)
    todo, promoted = bio_ingest.pending(store, episodes)
    log(f"  {len(episodes)} complete episode(s), "
        f"{len(episodes) - len(todo) - len(promoted)} already registered, "
        f"{len(todo)} to fetch")
    if promoted:
        log(f"  {len(promoted)} skipped: the supplier re-exported these into the "
            f"reviewed prefix, but we already hold the recording")
    if excluded:
        log(f"  {len(excluded)} excluded by the supplier")
    if incomplete:
        log(f"  {len(incomplete)} not ready in this snapshot (skipped)")
    if limit:
        todo = todo[:limit]
    if not todo:
        return {**base, "ingested": 0, "bytes": 0}
    if _dry(params):
        total = sum(e.total_bytes for e in todo)
        log(f"[dry run] would fetch {len(todo)} episode(s), "
            f"{total / 1e9:.1f} GB, into a new upload batch")
        return {**base, "ingested": 0, "bytes": 0}

    server = params.get("server") or os.environ.get(
        "STAGING_SERVER_URL") or "http://localhost"
    upload_id = params.get("upload_id") or bio_ingest.next_upload_id(server)
    scratch = os.path.join(store.active_data_root(), ".r2_fetch")
    os.makedirs(scratch, exist_ok=True)
    log(f"  fetching into upload batch {upload_id}")

    from staging.diskspace import MIN_FREE_BYTES, free_bytes_for_path

    cancel = params.get("_cancel") or (lambda: False)
    # The run's episode counters otherwise stay at 0/0 for the whole fetch --
    # the runner only learns ids after this returns -- so report the fetch.
    progress = params.get("_progress") or (lambda done, total, failed=0: None)
    root = store.active_data_root()
    done = failed = 0
    sent = 0
    progress(0, len(todo))
    for i, ep in enumerate(todo, 1):
        # The runner's cancel and free-space checks sit between the episodes of
        # the calibration pass, which comes after this whole loop, so on their
        # own they neither stop a fetch nor catch it filling the disk.  On
        # 2026-09-14 a run cancelled at 03:12 kept fetching until 04:45, and
        # its last 914 episodes failed ENOSPC.
        if cancel():
            log(f"  cancelled -- stopping before {ep.episode_dir}")
            break
        try:
            free = free_bytes_for_path(root)
        except OSError as exc:
            log(f"  STOPPING: could not read free space on {root}: {exc}")
            break
        # Twice the episode: it is staged under the data root, then placed.
        need = MIN_FREE_BYTES + 2 * int(ep.total_bytes or 0)
        if free < need:
            log(f"  STOPPING before {ep.episode_dir}: {free / 1e9:.1f} GB free "
                f"on {root}, need {need / 1e9:.1f} GB; the next run picks up "
                f"the rest")
            break
        try:
            sid = bio_ingest.ingest_one(
                s3, ep, upload_id=int(upload_id), scratch=scratch, server=server)
            done += 1
            sent += ep.total_bytes
            log(f"  [{i}/{len(todo)}] #{sid} {ep.episode_dir[:48]} "
                f"{ep.total_bytes / 1e6:.0f} MB")
        except Exception as exc:            # noqa: BLE001 - keep going
            failed += 1
            log(f"  [{i}/{len(todo)}] FAILED {ep.episode_dir}: {exc}")
        progress(done, len(todo), failed)
    log(f"  ingested {done}/{len(todo)}, {sent / 1e9:.1f} GB"
        + (f", {failed} failed" if failed else ""))
    return {**base, "ingested": done, "failed": failed, "bytes": sent,
            "upload_id": int(upload_id)}


def _verlet_bio_discover(store, params: Dict[str, Any]) -> List[int]:
    """Every verlet bio episode, for the calibration check.

    All of them, not just this run's: the check is a metadata read per episode,
    and it is what catches an older episode whose calibration stopped being
    readable (a reclaimed RAW, a legacy sidecar gone missing).
    """
    ids = [sid for sid, _key in _bio().episodes_needing_sidecar(store)]
    return ids[: int(params["limit"])] if params.get("limit") else ids


def _verlet_bio_one(store, sid: int, params: Dict[str, Any], log) -> dict:
    """Check that the Luma delivery can read this episode's gripper calibration.

    Nothing is written.  The delivery reads the ``gripper_limits`` record
    straight out of our local RAW MCAP, falling back to a sidecar only for the
    exports that predate the record (upload 396, most of 400), so this calls
    that same loader: an episode it cannot calibrate fails here, in the ingest
    run, instead of silently never becoming a Luma candidate.
    """
    import submit_to_luma as luma

    limits = luma.gripper_limits(store, sid) or {}
    missing = [t for t in luma.LEADER_TOPICS if t not in limits]
    if missing:
        raise RuntimeError(
            "no usable gripper calibration (no valid gripper_limits record in "
            f"the local RAW MCAP, and no sidecar to fall back to) for "
            f"{', '.join(missing)}")
    return {"staging_id": sid, "calibrated": True}


def _bio():
    import bio_ingest

    return bio_ingest


# ---------------------------------------------------------------------------
# Uploads
# ---------------------------------------------------------------------------



# --- kind registrations (lines 636-737) ---
    "postprocess": Kind(
        key="postprocess",
        label="Post-process episodes",
        resources=(CPU, GPU),
        discover=_postprocess_discover,
        process_one=_postprocess_one,
        writes_local=True,
        description="Convert RAW .svo2/.mp4 uploads into the mcap, the Level-1 "
                    "originals and the Level-2 previews.",
    ),
    "ego_ingest": Kind(
        key="ego_ingest",
        label="Ingest ego uploads",
        resources=(CPU, GPU),
        discover=_ego_discover,
        process_one=_ego_one,
        prepare=_ego_prepare,
        accepts=("limit",),
        prepare_bound=True,
        writes_local=True,
        description="Scan the FTP upload roots, verify GoPro chapters, convert "
                    "the 360 head camera to equirect and join the wrist videos.",
    ),
    "verlet_bio_ingest": Kind(
        key="verlet_bio_ingest",
        label="Ingest verlet Biology Lab",
        resources=(DOWNLOAD,),
        discover=_verlet_bio_discover,
        process_one=_verlet_bio_one,
        prepare=_verlet_bio_prepare,
        accepts=("limit", "upload_id"),
        prepare_bound=True,
        writes_local=True,
        description="Fetch new Biology Lab episodes from the supplier's "
                    "Cloudflare bucket, register them through the upload API, "
                    "and check every one's gripper calibration can be read "
                    "from its MCAP.",
    ),
    "mirror_raw": Kind(
        key="mirror_raw",
        label="Mirror RAW to its bucket",
        resources=(UPLOAD,),
        discover=_mirror_discover,
        process_one=_mirror_one,
        description="Send RAW that is in no bucket yet to whichever one routing "
                    "picks: the internal bucket unless Scale AI has asked for "
                    "or already been sent that episode.",
    ),
    "upload_scale": Kind(
        key="upload_scale",
        label="Upload to Scale AI",
        resources=(UPLOAD,),
        discover=_scale_discover,
        process_one=_scale_one,
        prepare=_scale_prepare,
        description="One pass: put the episode's RAW in the bucket Scale can "
                    "read, then submit it. Replaces the old GCS-then-submit "
                    "two-step.",
    ),
    "upload_scale_ego": Kind(
        key="upload_scale_ego",
        label="Upload ego episodes to Scale AI",
        resources=(CPU, UPLOAD),
        discover=_delegating_discover("ego_scale"),
        process_one=_delegating_one("ego_scale", "deliver to Scale (ego)"),
        prepare=_delegating_prepare("ego_scale"),
        writes_local=True,
        description="The ego delivery is a different mechanism: it merges the "
                    ".360 chapters losslessly (CPU) and uploads to S3, with no "
                    "Scale task API call. Only episodes whose data card is "
                    "complete are uploaded -- Scale cannot use media that no "
                    "manifest describes, so the rest are skipped with a "
                    "reason in the log until a reviewer fills the card in.",
    ),
    "upload_scale_ego_l2": Kind(
        key="upload_scale_ego_l2",
        label="Upload ego 360 previews to Scale AI",
        resources=(UPLOAD,),
        discover=_delegating_discover("ego_preview"),
        process_one=_delegating_one("ego_preview",
                                    "upload the 360 preview (ego)"),
        accepts=("supplier", "task_name", "upload_id", "limit",
                 "staging_ids"),
        description="Puts each ego episode's Level-2 equirect MP4 -- the "
                    "browser-playable reprojection of the .360 head camera, "
                    "not the wrist previews -- next to its deliverables in "
                    "the Scale bucket. Same data-card gate as the ego "
                    "delivery, but it does not wait for (or record) a "
                    "delivery batch, so an already-delivered episode can get "
                    "its preview later.",
    ),
    "upload_luma": Kind(
        key="upload_luma",
        label="Upload to Luma",
        resources=(CPU, GPU, UPLOAD),
        discover=_delegating_discover("luma"),
        process_one=_delegating_one("luma", "deliver to Luma"),
        prepare=_delegating_prepare("luma"),
        writes_local=True,
        description="Crops each Level-1 to the primary eye (a re-encode, so it "
                    "holds the GPU) and uploads the result plus the mcap.",
    ),
