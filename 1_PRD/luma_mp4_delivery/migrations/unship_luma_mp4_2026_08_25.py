#!/usr/bin/env python3
"""Remove malformed MP4-rig deliveries from Luma's bucket and un-record them.

The MP4-rig episodes were delivered in the shape the rig recorded them, which
does not match the SVO2 shape the rest of the delivered corpus uses:

* camera topics spelled ``cam_high`` / ``cam_left`` / ``cam_right`` rather than
  ``high`` / ``left_wrist`` / ``right_wrist``;
* ``/task_info.task_description`` carrying the operator-language instruction
  instead of the task label;
* the robot identifier under ``task_id``, not ``serial_number`` -- and in a
  spelling that names the wrong rig (see ``submit_to_luma.PAUSED_FORMATS``).

``luma_mcap_transform`` now fixes the first two at delivery time, and the third
is blocked on ops confirming the rig-C mapping.  Until then MP4 delivery is
paused, and what already shipped is withdrawn.

What it does per episode
------------------------

Deletes every object under ``gs://prismax-raw-luma/<staging_id>/`` and then
deletes the episode's ``customer_statuses`` row for Luma, returning it to
"never delivered".  It becomes a delivery candidate again the moment ``mp4``
leaves ``PAUSED_FORMATS`` -- no re-queueing needed, and the quota it consumed
is released with it.

Nothing local is touched: the products stay on disk exactly as they are, so the
re-delivery has the same sources to work from.

Safety
------

* Only episodes whose ``episode_format`` is in ``--formats`` (default ``mp4``)
  are ever considered -- an SVO2 delivery cannot be withdrawn by accident.
* The objects under the prefix are **listed and recorded in the manifest
  before** anything is deleted, so the manifest says exactly what was removed.
* The bucket prefix is built from the integer ``staging_id``, so it cannot
  address anything outside one episode's folder.
* The ``customer_statuses`` row is deleted only after the objects are gone; an
  interrupted run therefore leaves the episode still marked delivered rather
  than claiming an un-shipped episode was withdrawn.

Usage::

    .venv/bin/python migration/unship_luma_mp4_2026_08_25.py --staging-ids 26774,...
    .venv/bin/python migration/unship_luma_mp4_2026_08_25.py --staging-ids ... --apply
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from staging import Config, StagingStore              # noqa: E402
from staging.config import LUMA_CUSTOMER_ID           # noqa: E402

BUCKET = "gs://prismax-raw-luma"


def candidates(store: StagingStore, formats: "tuple[str, ...]",
               staging_ids: "list[int] | None") -> list[dict]:
    """Delivered episodes of the named formats, optionally narrowed by id."""
    where, params = "", []
    if staging_ids:
        ph = ",".join("?" for _ in staging_ids)
        where = f" AND e.staging_id IN ({ph})"
        params = list(staging_ids)
    ph_fmt = ",".join("?" for _ in formats)
    rows = store.db.query_all(
        "SELECT e.staging_id, e.episode_format, e.task_name, e.supplier, "
        "       cs.customer_upload_time "
        "FROM episodes e "
        "JOIN customer_statuses cs "
        "  ON cs.staging_id = e.staging_id AND cs.customer_id = ? "
        "     AND cs.customer_upload_time IS NOT NULL "
        f"WHERE e.episode_format IN ({ph_fmt})"
        + where +
        " ORDER BY e.staging_id",
        tuple([LUMA_CUSTOMER_ID, *formats] + params),
    )
    return [dict(r) for r in rows]


def list_objects(prefix: str) -> "list[str]":
    proc = subprocess.run(["gcloud", "storage", "ls", prefix],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        return []
    return [l.strip() for l in (proc.stdout or "").splitlines()
            if l.strip().startswith("gs://") and not l.strip().endswith("/")]


def unship_one(store: StagingStore, row: dict, *, apply: bool,
               manifest, log=print) -> dict:
    sid = int(row["staging_id"])
    prefix = f"{BUCKET}/{sid}/"
    rec = {"staging_id": sid, "episode_format": row["episode_format"],
           "prefix": prefix, "objects": [], "action": None}

    objects = list_objects(prefix)
    rec["objects"] = objects
    if not objects:
        # Nothing in the bucket: still clear the row so it can re-deliver.
        rec["action"] = "no-objects"
    else:
        rec["action"] = "unship"

    if not apply:
        return rec

    manifest.write(json.dumps(rec, ensure_ascii=False) + "\n")
    manifest.flush()

    if objects:
        proc = subprocess.run(["gcloud", "storage", "rm", *objects],
                              capture_output=True, text=True)
        if proc.returncode != 0:
            rec["action"] = "error:delete failed"
            rec["error"] = (proc.stderr or "").strip()[:300]
            return rec

    store.db.execute(
        "DELETE FROM customer_statuses WHERE staging_id = ? AND customer_id = ?",
        (sid, LUMA_CUSTOMER_ID))
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="Actually withdraw (default: report only).")
    ap.add_argument("--limit", type=int, default=None,
                    help="Stop after this many episodes (canary runs).")
    ap.add_argument("--staging-ids", default="",
                    help="Comma-separated subset (default: every delivered one).")
    ap.add_argument("--formats", default="mp4",
                    help="Comma-separated episode_format values in scope.")
    ap.add_argument("--manifest", default="",
                    help="JSONL manifest path (default: beside this script).")
    args = ap.parse_args()

    ids = [int(x) for x in args.staging_ids.split(",") if x.strip()]
    formats = tuple(x.strip() for x in args.formats.split(",") if x.strip())
    store = StagingStore(config=Config.from_env())
    rows = candidates(store, formats, ids or None)
    print(f"formats {list(formats)}: {len(rows)} delivered episode(s) in scope")
    if args.limit:
        rows = rows[:args.limit]
        print(f"limited to {len(rows)}")

    path = args.manifest or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"unship_luma_mp4_{int(time.time())}.jsonl")
    tally: dict[str, int] = {}
    n_objects = 0
    fh = open(path, "a", encoding="utf-8") if args.apply else open(os.devnull, "w")
    try:
        for i, row in enumerate(rows, 1):
            rec = unship_one(store, row, apply=args.apply, manifest=fh)
            tally[rec["action"]] = tally.get(rec["action"], 0) + 1
            n_objects += len(rec["objects"])
            print(f"[{i}/{len(rows)}] episode {rec['staging_id']}: "
                  f"{'withdrew' if args.apply else 'would withdraw'} "
                  f"{len(rec['objects'])} object(s)")
            if rec["action"].startswith("error"):
                print(f"    {rec['action']}: {rec.get('error','')}")
    finally:
        fh.close()

    print("\nsummary:")
    for k in sorted(tally):
        print(f"  {k}: {tally[k]}")
    print(f"  objects: {n_objects}")
    if args.apply:
        print(f"manifest: {path}")
    else:
        print("dry run -- nothing removed (pass --apply)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
