#!/usr/bin/env python3
"""Replace already-delivered MP4-rig mcaps with the homogenised shape.

The MP4-rig episodes delivered before 2026-08-25 went out in the shape the rig
recorded them, which does not match the SVO2 shape the rest of the delivered
corpus uses:

* camera topics ``cam_high`` / ``cam_left`` / ``cam_right`` rather than
  ``high`` / ``left_wrist`` / ``right_wrist``;
* ``/task_info`` carrying ``task_name`` / ``task_id`` and the operator-language
  instruction, rather than ``task`` / ``serial_number`` and the task label;
* the identifier missing its task letter on everything up to staging_id 26706
  (``YAM-BIO-016`` where the SVO2 corpus says ``YAM-BIO-B-016``).

:mod:`luma_mcap_transform` now fixes all three at delivery time.  This applies
the same transform to the episodes that already shipped and **overwrites the
delivered object in place**.

Why overwrite rather than withdraw and re-deliver
-------------------------------------------------

Only the mcap changed: the Level-1 videos this fix does not touch, and they are
the bulk of each delivery.  Overwriting the one bad object leaves the customer
holding a complete episode throughout -- there is no window where the episode is
half-there -- costs one small upload instead of re-sending the videos, and
leaves ``customer_statuses`` (and so the requested-hours quota) untouched.

The object is written under its **delivered name**
(``submit_to_luma.delivered_basename``), and the old object is removed once the
new one is up.  For this format that is a rename as well as a re-shape: the MP4
upload registers the rig's raw mcap in place, so it shipped under whatever the
rig numbered it (``0.mcap``, ``64.mcap``, ``110.mcap``) where every SVO2
episode ships ``telemetry.webui.mcap``.  The single-view videos are renamed the
same way -- ``cam_left`` / ``cam_right`` to ``cam_left_wrist`` /
``cam_right_wrist`` -- with a server-side ``gcloud storage mv``, so their bytes
never leave the bucket.

Safety
------

* Only ``episode_format='mp4'`` episodes already delivered to Luma are in scope.
* Each rewritten mcap is verified **before** it is uploaded: the delivered
  payload must carry a ``serial_number``, must be ASCII, and must have no
  ``cam_*`` camera topic left.  An episode failing any of those is skipped, not
  uploaded.
* The gripper inversion is applied here exactly as the delivery does it -- this
  reuses ``transform_mcap``, so the re-shaped file differs from the original
  delivery only in the topic names and the ``/task_info`` payload.

Usage::

    .venv/bin/python migration/reshape_luma_mp4_mcaps_2026_08_25.py
    .venv/bin/python migration/reshape_luma_mp4_mcaps_2026_08_25.py --apply --limit 3
    .venv/bin/python migration/reshape_luma_mp4_mcaps_2026_08_25.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.path.insert(0, os.path.join(_ROOT, "upload"))

from staging import Config, StagingStore              # noqa: E402
from staging.config import LUMA_CUSTOMER_ID           # noqa: E402

from luma_mcap_transform import (                     # noqa: E402
    LEADER_TOPICS,
    MP4_NORMALISED_LIMITS,
    transform_mcap,
)
from submit_to_luma import delivered_basename         # noqa: E402
from mcap.reader import make_reader                   # noqa: E402

BUCKET = "gs://prismax-raw-luma"


def candidates(store: StagingStore,
               staging_ids: "list[int] | None" = None) -> list[dict]:
    """Delivered MP4 episodes and the mcap product each one shipped."""
    where, params = "", []
    if staging_ids:
        ph = ",".join("?" for _ in staging_ids)
        where = f" AND e.staging_id IN ({ph})"
        params = list(staging_ids)
    rows = store.db.query_all(
        "SELECT e.staging_id, e.task_name, mc.path "
        "FROM episodes e "
        "JOIN customer_statuses cs "
        "  ON cs.staging_id = e.staging_id AND cs.customer_id = ? "
        "     AND cs.customer_upload_time IS NOT NULL "
        "JOIN files mc ON mc.staging_id = e.staging_id AND mc.kind = 'mcap' "
        "WHERE e.episode_format = 'mp4'"
        + where +
        " ORDER BY e.staging_id",
        tuple([LUMA_CUSTOMER_ID] + params),
    )
    return [dict(r) for r in rows]


def inspect(path: str) -> dict:
    """Topics and ``/task_info`` of a local mcap."""
    topics, info = set(), {}
    with open(path, "rb") as fh:
        for _s, c, m in make_reader(fh).iter_messages():
            topics.add(c.topic)
            if c.topic == "/task_info":
                try:
                    info = json.loads(m.data[8:].decode("utf-8").rstrip("\x00"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    info = {}
    return {"topics": topics, "info": info}


def list_prefix(sid: int) -> "set[str]":
    """Object basenames currently under this episode's prefix."""
    proc = subprocess.run(["gcloud", "storage", "ls", f"{BUCKET}/{sid}/"],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        return set()
    return {u.strip().rsplit("/", 1)[-1]
            for u in (proc.stdout or "").splitlines()
            if u.strip().startswith("gs://") and not u.strip().endswith("/")}


def tidy_names(sid: int, present: "set[str]", stale: str, log=print) -> dict:
    """Drop the replaced mcap and rename the videos, from one listing.

    Driven by what the bucket actually holds rather than by what a delete
    reported, so a re-run over an episode that is already tidy is a clean no-op
    -- ``gcloud storage rm`` on a missing object is an error ("matched no
    objects or files"), and treating that as failure would make this script
    non-idempotent.

    ``gcloud storage mv`` within one bucket is a server-side copy plus a
    delete, so no bytes travel.
    """
    out = {"removed": [], "renamed": []}
    if stale and stale in present:
        rm = subprocess.run(["gcloud", "storage", "rm", f"{BUCKET}/{sid}/{stale}"],
                            capture_output=True, text=True)
        if rm.returncode == 0:
            out["removed"].append(stale)
        else:
            log(f"    removing stale {stale} FAILED: "
                f"{(rm.stderr or '').strip()[:160]}")
    for base in sorted(present):
        if not base.endswith(".mp4"):
            continue
        want = delivered_basename("video_l1", base)
        if want == base or want in present:
            continue
        mv = subprocess.run(
            ["gcloud", "storage", "mv",
             f"{BUCKET}/{sid}/{base}", f"{BUCKET}/{sid}/{want}"],
            capture_output=True, text=True)
        if mv.returncode == 0:
            out["renamed"].append((base, want))
        else:
            log(f"    rename {base} -> {want} FAILED: "
                f"{(mv.stderr or '').strip()[:160]}")
    return out


def reshape_one(store: StagingStore, row: dict, *, apply: bool,
                manifest, log=print) -> dict:
    sid, src = int(row["staging_id"]), row["path"]
    old_name = os.path.basename(src)
    new_name = delivered_basename("mcap", old_name)
    dest = f"{BUCKET}/{sid}/{new_name}"
    rec = {"staging_id": sid, "src": src, "dest": dest,
           "old_object": f"{BUCKET}/{sid}/{old_name}", "action": None,
           "renamed_videos": []}

    if not src or not os.path.isfile(src):
        rec["action"] = "skip:product missing on disk"
        return rec

    with tempfile.TemporaryDirectory(prefix=f"reshape.{sid}.") as tmp:
        out = os.path.join(tmp, new_name)
        # Limits are required since 2026-09-03.  This migration is mp4-only,
        # and the mp4 rig's pair is the *corrected* polarity -- re-running it
        # now would fix the inversion it originally shipped, not reproduce it.
        transform_mcap(src, out, task_description=row.get("task_name") or "",
                       gripper_limits={t: MP4_NORMALISED_LIMITS
                                       for t in LEADER_TOPICS})
        got = inspect(out)
        info = got["info"]
        rec["before"] = inspect(src)["info"]
        rec["after"] = info

        # Refuse to upload anything that is not actually the target shape.
        if not info.get("serial_number"):
            rec["action"] = "skip:no serial_number after transform"
            return rec
        if not json.dumps(info, ensure_ascii=False).isascii():
            rec["action"] = "skip:non-ASCII payload after transform"
            return rec
        leftover = sorted(t for t in got["topics"] if "/camera/cam_" in t)
        if leftover:
            rec["action"] = "skip:un-renamed camera topic"
            rec["leftover"] = leftover
            return rec

        rec["action"] = "reshape"
        if not apply:
            return rec

        manifest.write(json.dumps(rec, ensure_ascii=False) + "\n")
        manifest.flush()

        proc = subprocess.run(["gcloud", "storage", "cp", out, dest],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            rec["action"] = "error:upload failed"
            rec["error"] = (proc.stderr or "").strip()[:300]
            return rec

    # The new object is up; tidy what it replaced, driven by a real listing.
    tidied = tidy_names(sid, list_prefix(sid),
                        old_name if new_name != old_name else "", log=log)
    rec["removed"] = tidied["removed"]
    rec["renamed_videos"] = tidied["renamed"]
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="Actually overwrite the delivered object.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Stop after this many episodes (canary runs).")
    ap.add_argument("--staging-ids", default="",
                    help="Comma-separated subset to consider.")
    ap.add_argument("--manifest", default="",
                    help="JSONL manifest path (default: beside this script).")
    args = ap.parse_args()

    ids = [int(x) for x in args.staging_ids.split(",") if x.strip()]
    store = StagingStore(config=Config.from_env())
    rows = candidates(store, ids or None)
    print(f"{len(rows)} delivered MP4 episode(s) in scope")
    if args.limit:
        rows = rows[:args.limit]
        print(f"limited to {len(rows)}")

    path = args.manifest or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"reshape_luma_mp4_{int(time.time())}.jsonl")
    tally: dict[str, int] = {}
    fh = open(path, "a", encoding="utf-8") if args.apply else open(os.devnull, "w")
    try:
        for i, row in enumerate(rows, 1):
            rec = reshape_one(store, row, apply=args.apply, manifest=fh)
            tally[rec["action"]] = tally.get(rec["action"], 0) + 1
            if rec["action"] == "reshape":
                nvid = len(rec.get("renamed_videos") or [])
                print(f"[{i}/{len(rows)}] episode {rec['staging_id']}: "
                      f"{'uploaded' if args.apply else 'would upload'} "
                      f"{os.path.basename(rec['dest'])} "
                      f"serial={rec['after'].get('serial_number')}"
                      + (f", renamed {nvid} video(s)" if nvid else ""))
            else:
                print(f"[{i}/{len(rows)}] episode {rec['staging_id']}: {rec['action']}")
    finally:
        fh.close()

    print("\nsummary:")
    for k in sorted(tally):
        print(f"  {k}: {tally[k]}")
    if args.apply:
        print(f"manifest: {path}")
    else:
        print("dry run -- nothing uploaded (pass --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
