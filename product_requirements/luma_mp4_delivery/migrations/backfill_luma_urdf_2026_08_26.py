#!/usr/bin/env python3
"""Add the missing robot description to Luma deliveries that shipped without it.

The MP4 rig's "Biology Lab" uploads carry a ``.urdf`` next to the cameras and
the mcap (staging 27437 onward, supplier ``yun``).  ``submit_to_luma`` learned
to deliver it on 2026-08-26 -- but by then every episode that has one had
already been delivered, and a delivered episode is never re-offered
(``find_candidates`` filters on ``customer_upload_time``), so the new code would
only ever have shipped the URDF for uploads still to come.  This backfills the
ones already in the bucket.

What it does per episode
------------------------

Copies the episode's local ``.urdf`` into its existing
``gs://prismax-raw-luma/<staging_id>/`` folder, under the same name
``submit_to_luma.delivered_basename`` would give it -- the uploaded name, which
identifies the robot model.  Nothing else in the folder is touched, and no
local file is read except the URDF itself.

``customer_statuses`` is deliberately left alone: these episodes *were*
delivered and still are.  This completes the contents behind an existing
delivery, it is not a new one -- so no batch is stamped, no quota is spent, and
the delivered-hours totals do not move.  (Same reasoning as
``redeliver_luma_swapped_eye_2026_08_10.py``, which corrected bytes under a
delivery without re-recording it.)

Safety
------

* Only episodes with a Luma ``customer_upload_time`` are considered, so this
  cannot quietly create a folder for something that was never delivered.
* The destination prefix is **listed first** and an episode whose folder holds
  no objects is skipped, loudly: an empty prefix means the delivery is not
  actually in the bucket (it was withdrawn by
  ``unship_luma_mp4_2026_08_25.py``, say), and dropping a lone URDF into it
  would leave a folder that looks delivered and contains no data.  Such an
  episode should be re-delivered by the normal path instead, which now includes
  the URDF anyway.
* An episode whose folder already holds a ``.urdf`` is skipped, so re-running
  is a no-op rather than a re-upload.
* The prefix is built from the integer ``staging_id``, so it cannot address
  anything outside one episode's folder, and only ``cp`` is ever run -- nothing
  here deletes or overwrites an existing object.
* Every episode acted on is written to a JSONL manifest before its upload.

Usage::

    .venv/bin/python migration/backfill_luma_urdf_2026_08_26.py
    .venv/bin/python migration/backfill_luma_urdf_2026_08_26.py --apply --limit 1
    .venv/bin/python migration/backfill_luma_urdf_2026_08_26.py --apply
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_HERE)
for _p in (_ROOT, os.path.join(_ROOT, "upload")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from staging import Config, StagingStore              # noqa: E402
from staging.config import LUMA_CUSTOMER_ID           # noqa: E402

from submit_to_luma import (                          # noqa: E402
    BUCKET,
    URDF_SUFFIX,
    delivered_basename,
)

RETRIES = 3

# How many prefixes to list per ``gcloud storage ls`` call.  One call per
# episode is ~1.5 s of process startup each; gcloud takes many URLs at once and
# prints one flat list of object URLs, which is all this needs.
LIST_CHUNK = 40


def candidates(store: StagingStore,
               staging_ids: "list[int] | None") -> "list[dict]":
    """Delivered-to-Luma episodes whose upload carried a URDF, oldest first.

    The URDF is a RAW row matched by suffix -- ingest registers it like every
    other file in the upload folder, so there is no product kind to select on
    (the same rule ``submit_to_luma.is_urdf`` applies at delivery time).
    """
    where, params = "", []
    if staging_ids:
        ph = ",".join("?" for _ in staging_ids)
        where = f" AND e.staging_id IN ({ph})"
        params = list(staging_ids)
    rows = store.db.query_all(
        "SELECT e.staging_id, e.task_name, e.episode_format, e.supplier, "
        "       f.path, f.size_bytes, cs.customer_upload_batch_id "
        "FROM episodes e "
        "JOIN customer_statuses cs "
        "  ON cs.staging_id = e.staging_id AND cs.customer_id = ? "
        "     AND cs.customer_upload_time IS NOT NULL "
        "JOIN files f "
        "  ON f.staging_id = e.staging_id AND f.kind = 'raw' "
        f"     AND lower(f.path) LIKE '%{URDF_SUFFIX}' "
        + where +
        " ORDER BY e.staging_id, f.path",
        tuple([LUMA_CUSTOMER_ID] + params),
    )
    return [dict(r) for r in rows]


def list_prefixes(sids: "list[int]") -> "dict[int, list[str]]":
    """Objects already in the bucket, per staging_id.

    A staging_id missing from the result (or mapped to an empty list) has
    nothing under its prefix.
    """
    found: "dict[int, list[str]]" = {sid: [] for sid in sids}
    for i in range(0, len(sids), LIST_CHUNK):
        chunk = sids[i:i + LIST_CHUNK]
        proc = subprocess.run(
            ["gcloud", "storage", "ls", *[f"{BUCKET}/{s}/" for s in chunk]],
            capture_output=True, text=True)
        # A prefix that does not exist is an error on that URL alone; gcloud
        # still lists the rest, so a non-zero rc is not fatal here.
        for line in (proc.stdout or "").splitlines():
            url = line.strip()
            if not url.startswith(f"{BUCKET}/") or url.endswith("/"):
                continue
            rest = url[len(BUCKET) + 1:]
            head, _, _ = rest.partition("/")
            if head.isdigit() and int(head) in found:
                found[int(head)].append(url)
    return found


def _cp(src: str, dest_dir: str, *, log) -> None:
    last = ""
    for attempt in range(1, RETRIES + 1):
        proc = subprocess.run(["gcloud", "storage", "cp", src, dest_dir],
                              capture_output=True, text=True)
        if proc.returncode == 0:
            return
        last = (proc.stderr or "").strip()[:300]
        log(f"  attempt {attempt}/{RETRIES} failed: {last}")
    raise RuntimeError(f"gcloud cp failed: {last}")


def plan_one(row: dict, objects: "list[str]") -> dict:
    """What this episode needs, without touching anything.

    ``action`` is one of ``upload`` / ``already-has-urdf`` / ``not-in-bucket``
    / ``missing-on-disk``.
    """
    sid = int(row["staging_id"])
    path = str(row["path"])
    base = delivered_basename("raw", os.path.basename(path))
    rec = {"staging_id": sid, "task_name": row.get("task_name"),
           "episode_format": row.get("episode_format"),
           "batch_id": row.get("customer_upload_batch_id"),
           "path": path, "dest": f"{BUCKET}/{sid}/{base}",
           "bucket_objects": len(objects), "action": "upload"}
    if not objects:
        rec["action"] = "not-in-bucket"
    elif any(o.lower().endswith(URDF_SUFFIX) for o in objects):
        rec["action"] = "already-has-urdf"
    elif not os.path.exists(path):
        rec["action"] = "missing-on-disk"
    return rec


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="really upload; without it nothing is copied.")
    ap.add_argument("--limit", type=int, default=None,
                    help="act on at most this many episodes (the canary).")
    ap.add_argument("--staging-ids", default="",
                    help="comma-separated staging_ids to restrict to.")
    ap.add_argument("--manifest", default="",
                    help="JSONL manifest path (default: beside this script).")
    args = ap.parse_args()

    sids = [int(x) for x in args.staging_ids.replace(",", " ").split()] or None
    store = StagingStore(config=Config.from_env())
    rows = candidates(store, sids)
    print(f"{len(rows)} delivered episode(s) with a URDF", flush=True)
    if not rows:
        store.close()
        return 0

    objects = list_prefixes(sorted({int(r["staging_id"]) for r in rows}))
    plans = [plan_one(r, objects.get(int(r["staging_id"]), [])) for r in rows]

    by_action: "dict[str, list[dict]]" = {}
    for p in plans:
        by_action.setdefault(p["action"], []).append(p)
    for action, group in sorted(by_action.items()):
        print(f"  {action}: {len(group)}"
              + (f"  e.g. {group[0]['staging_id']}" if group else ""))
    for p in by_action.get("not-in-bucket", []):
        print(f"  !! {p['staging_id']}: delivered but nothing in the bucket "
              f"-- re-deliver it instead", file=sys.stderr)
    for p in by_action.get("missing-on-disk", []):
        print(f"  !! {p['staging_id']}: URDF row present, file gone "
              f"({p['path']})", file=sys.stderr)

    todo = by_action.get("upload", [])
    if args.limit is not None:
        todo = todo[: int(args.limit)]
    if not args.apply:
        print(f"\ndry run: would upload {len(todo)} URDF(s)", flush=True)
        for p in todo[:10]:
            print(f"  {p['staging_id']}: {os.path.basename(p['path'])} "
                  f"-> {p['dest']}")
        store.close()
        return 0

    path = args.manifest or os.path.join(
        _HERE, f"backfill_luma_urdf_{int(time.time())}.jsonl")
    ok = failed = 0
    with open(path, "a", encoding="utf-8") as fh:
        for i, p in enumerate(todo, 1):
            print(f"[{i}/{len(todo)}] episode {p['staging_id']}", flush=True)
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
            fh.flush()
            try:
                _cp(p["path"], f"{BUCKET}/{p['staging_id']}/", log=print)
                ok += 1
            except Exception as exc:  # noqa: BLE001
                failed += 1
                print(f"  FAILED: {exc}", file=sys.stderr, flush=True)
    print(f"\nuploaded {ok}, failed {failed}", flush=True)
    print(f"manifest: {path}", flush=True)
    store.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
