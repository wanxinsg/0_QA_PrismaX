# EXCERPT -- not importable on its own.
# Source: workers/svo2/process_svo2.py, lines 95-145 (branch fix/luma-serial-letter-guard @ 7554497 + uncommitted working tree, 2026-09-23).
# MP4+MCAP post-processing: camera map and format detection.


# ── MP4 + MCAP upload type ───────────────────────────────────────────────────
#
# A second upload format ships one already-decoded single-view MP4 per camera
# (``cam_high.mp4`` / ``cam_left.mp4`` / ``cam_right.mp4``) plus one telemetry
# ``.mcap``.  Unlike SVO2 there is nothing to decode/split:
#
#   * the telemetry mcap passes through unchanged (registered as the MCAP
#     product directly -- no ``svo2_mcap_convert`` rewrite),
#   * each MP4 passes through as an L1 video (registered in place, keeping its
#     ``cam_*`` name, aliased against the RAW file -- so RAW must never be
#     deleted for these episodes, see staging.ingest.raw_deletable_episodes),
#   * each MP4 is transcoded to a single L2 video (``high``/``left``/``right``)
#     with the same L2 params as the SVO2 path (svo2_convert.make_level2_from_mp4).

# RAW mp4 basename -> level-2 display name (single view, no secondary ``...2``).
MP4_CAMERA_L2_NAMES = {
    "cam_high": "high",
    "cam_left": "left",
    "cam_right": "right",
}
# The camera whose duration defines the episode length (overhead view).
MP4_LENGTH_REFERENCE_CAMERA = "cam_high"


def _episode_raw_mp4s(store: StagingStore, staging_id: int) -> dict:
    """Return ``{cam_stem: raw_mp4_path}`` for an MP4-format episode.

    Empty when the episode has no ``.mp4`` raw files still on local disk (i.e.
    not this type).  Keyed by the file stem (``cam_high`` etc.) so callers can
    map to L2 names.
    """
    ep = store.get_episode(staging_id)
    if ep is None:
        return {}
    found: dict = {}
    for f in _local_raw_files(ep):
        if f.path.lower().endswith(".mp4"):
            stem = Path(f.path).stem
            found[stem] = f.path
    return found


def is_mp4_episode(store: StagingStore, staging_id: int) -> bool:
    return bool(_episode_raw_mp4s(store, staging_id))


def _is_mp4_episode(ep) -> bool:
    return any(f.path.lower().endswith(".mp4") for f in _local_raw_files(ep))



# --- dispatch (lines 460-478) ---
def process_episode_any(store: StagingStore, staging_id: int, **kwargs) -> dict:
    """Postprocess one episode, dispatching on its upload format.

    SVO2 episodes go through :func:`process_episode` (decode + eye-split +
    transcode); MP4+MCAP episodes through :func:`process_mp4_episode`
    (passthrough L1 + mcap, single-view L2 transcode).  Raises ``ValueError``
    if the episode is neither format.
    """
    if is_svo2_episode(store, staging_id):
        return process_episode(store, staging_id, **kwargs)
    if is_ego_episode(store, staging_id):
        # Ego raws are .mp4 too, so this check must run before the plain
        # MP4+MCAP dispatch.
        return process_ego_episode(store, staging_id, **kwargs)
    if is_mp4_episode(store, staging_id):
        return process_mp4_episode(store, staging_id, **kwargs)
    raise ValueError(
        f"episode {staging_id} is not an SVO2, ego, or MP4+MCAP upload")


# --- process_mp4_episode (lines 614-747) ---
def process_mp4_episode(
    store: StagingStore,
    staging_id: int,
    *,
    encoder: str = "h264_nvenc",
    levels=("l1", "l2"),
    convert_mcap: bool = True,
    generate_graph_cache: bool = True,
    overwrite: bool = False,
    max_workers: int = 3,  # accepted for signature parity; MP4 L2 is per-file
    log=print,
) -> dict:
    """Process one MP4+MCAP episode.  Returns the same summary shape as SVO2.

    * L1: each raw ``cam_*.mp4`` is registered in place (passthrough, keeping
      its ``cam_*`` name) -- no re-encode.  The registered path IS the RAW file
      path, so the two are aliased (RAW deletion is blocked for these episodes).
    * L2: each raw MP4 is transcoded once (single view) to
      ``<episode_dir>/video_l2/<high|left|right>.mp4`` with the shared L2 params.
    * mcap: the raw telemetry mcap passes through unchanged (registered as the
      MCAP product directly -- no SVO2-style rewrite).
    * length_seconds: taken from the overhead (``cam_high``) MP4.
    * graph cache: same best-effort L2 graph cache as SVO2.
    """
    raw_mp4s = _episode_raw_mp4s(store, staging_id)
    if not raw_mp4s:
        raise ValueError(f"episode {staging_id} is not an MP4+MCAP episode")

    out_dir = Path(store.episode_dir(staging_id))
    log(f"episode {staging_id}: MP4+MCAP passthrough/transcode -> {out_dir}")

    levels = tuple(levels)

    # ── L1: register the raw MP4s in place (passthrough). ────────────────────
    n1 = 0
    if "l1" in levels:
        l1_paths = [str(Path(p).resolve()) for p in raw_mp4s.values()]
        # Alias the RAW mp4 paths as L1 (they are already 'raw' file rows), so
        # dedupe only within the L1 kind -- see _register_alias.
        n1 = _register_alias(store, staging_id, FileKind.VIDEO_L1, l1_paths)
        log(f"episode {staging_id}: registered {n1} new L1 (passthrough)")

    # ── L2: transcode each single-view MP4 to high/left/right. ───────────────
    l2_paths: list[Path] = []
    n2 = 0
    if "l2" in levels:
        l2_dir = out_dir / "video_l2"
        l2_dir.mkdir(parents=True, exist_ok=True)
        for stem, src in sorted(raw_mp4s.items()):
            l2_name = MP4_CAMERA_L2_NAMES.get(stem)
            if l2_name is None:
                log(f"  skip L2 for unrecognised camera {stem!r}")
                continue
            dst = l2_dir / f"{l2_name}.mp4"
            if dst.is_file() and not overwrite:
                log(f"  L2 {dst.name} exists, skipping")
            else:
                log(f"  L2 transcode {Path(src).name} -> {dst.name}")
                svo2_convert._atomic(  # noqa: SLF001
                    dst,
                    lambda tmp, s=src: svo2_convert.make_level2_from_mp4(
                        Path(s), tmp, encoder=encoder),
                )
            l2_paths.append(dst)
        n2 = _register_new(store, staging_id, FileKind.VIDEO_L2,
                           [str(p.resolve()) for p in l2_paths])
        log(f"episode {staging_id}: registered {n2} new L2 file(s)")

    # ── length_seconds from the overhead camera. ─────────────────────────────
    ref = raw_mp4s.get(MP4_LENGTH_REFERENCE_CAMERA) or next(iter(raw_mp4s.values()), None)
    if ref is not None:
        _w, _h, fps, frames = svo2_convert._probe_mp4(Path(ref))  # noqa: SLF001
        if fps and frames:
            length = frames / fps
            ep = store.get_episode(staging_id)
            if ep is not None and (overwrite or ep.length_seconds is None):
                store.set_length_seconds(staging_id, length)
                log(f"episode {staging_id}: set length_seconds={length:.3f}")

    # ── mcap: passthrough (register the raw telemetry mcap directly). ────────
    nm = 0
    mcap_out: Optional[Path] = None
    if convert_mcap:
        src = _episode_raw_mcap(store, staging_id)
        if src is None:
            log(f"episode {staging_id}: no telemetry mcap, skipping")
        else:
            mcap_out = src
            nm = _register_alias(store, staging_id, FileKind.MCAP,
                                 [str(Path(src).resolve())])
            log(f"episode {staging_id}: registered {nm} mcap (passthrough)")

    # ── graph cache (best-effort, same as SVO2). ─────────────────────────────
    ngc = 0
    graph_out: Optional[Path] = None
    if generate_graph_cache:
        try:
            graph_out = _generate_and_register_graph_cache(
                store, staging_id, out_dir, mcap_out,
                l2_paths, overwrite=overwrite, log=log,
            )
            if graph_out is not None:
                ngc = _register_new(store, staging_id, FileKind.GRAPH_L2, [graph_out])
                log(f"episode {staging_id}: registered {ngc} new graph cache file(s)")
        except Exception as exc:
            log(f"episode {staging_id}: graph cache failed (non-fatal): {exc}")

    ep = store.get_episode(staging_id)
    return {
        "staging_id": staging_id,
        "l1_files": [str(Path(p).resolve()) for p in raw_mp4s.values()],
        "l2_files": [str(p) for p in l2_paths],
        "mcap_file": str(mcap_out) if mcap_out else None,
        "graph_cache_file": str(graph_out) if graph_out else None,
        "length_seconds": ep.length_seconds if ep else None,
        "registered_l1": n1,
        "registered_l2": n2,
        "registered_mcap": nm,
        "registered_graph_cache": ngc,
    }


# ── Quick (metadata-only) processing ─────────────────────────────────────────
#
# A full run transcodes gigabytes of video, which is why a fresh upload can sit
# for hours with no ``length_seconds`` -- and therefore no duration in the
# reviewer, and no hours in the Uploads totals.  But that number does not come
# out of the transcode: it is read from the source's container header (ffprobe
# for MP4, the MCAP summary index for SVO2), which costs milliseconds and
# touches no pixels.  "Quick Process" runs only that read, so the metadata is
# right immediately and the (still necessary) transcode can happen later.
#
# Nothing here writes files or registers products: an episode that has been
# quick-processed is still queued by the ordinary Postprocess run.
