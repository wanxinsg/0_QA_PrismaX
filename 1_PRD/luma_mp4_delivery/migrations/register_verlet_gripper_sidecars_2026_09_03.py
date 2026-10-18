#!/usr/bin/env python3
"""CLI for the verlet gripper sidecars -- a wrapper, not an implementation.

Ran on 2026-09-03/04 over the first 1,169 Biology Lab episodes, when the
supplier published calibration as one aggregate ``dataset_info.json`` per bucket
prefix.  They retired that file on 2026-09-10; every export since carries a
``gripper_limits`` metadata record inside the MCAP instead.  The logic lives in
:func:`workers.verlet.bio_ingest.resolve_sidecar`, which the webui2
``verlet_bio_ingest`` job shares: the sidecar comes from the record in **our own
local copy** of the MCAP, never the bucket's -- a re-export can move the
gripper's zero point, so limits are only valid against the bytes they came with.

This stays for the shell case: re-checking every sidecar against its MCAP
without pulling anything.

Usage::

    STAGING_DB_URL=... python migration/register_verlet_gripper_sidecars_2026_09_03.py \
        [--dry-run] [--limit N] [--manifest PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "workers", "verlet")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import bio_ingest  # noqa: E402  (workers/verlet/)

from staging import Config, StagingStore  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--manifest", default=None,
                    help="append one JSON line per episode written")
    args = ap.parse_args(list(argv) if argv is not None else None)

    # The bucket is only needed for the rig index, which is informational; the
    # calibration itself is read from local disk.
    robots: dict = {}
    try:
        robots = bio_ingest.load_robots(bio_ingest.client())
    except bio_ingest.CredentialsMissing as exc:
        print(f"note: {exc} -- sidecars get no rig details", file=sys.stderr)
    print(f"robots index: {len(robots)} rig(s)")

    store = StagingStore(Config.from_env())
    rows = bio_ingest.episodes_needing_sidecar(store)
    counts: dict = {}
    to_write, failed = [], []
    for sid, _key in rows:
        try:
            sidecar, action = bio_ingest.resolve_sidecar(store, sid, robots=robots)
        except RuntimeError as exc:
            failed.append((sid, str(exc)))
            continue
        counts[action] = counts.get(action, 0) + 1
        if sidecar is not None:
            to_write.append((sid, sidecar))

    print(f"\n  {len(rows)} ingested episode(s)")
    for action in ("unchanged", "kept", "write"):
        print(f"    {counts.get(action, 0):5}  {action}")
    print(f"    {len(failed):5}  held back (no calibration source)")
    for sid, why in failed[:10]:
        print(f"      #{sid}: {why}")

    if args.limit:
        to_write = to_write[:args.limit]
    if args.dry_run:
        if to_write:
            print(f"\nsample (#{to_write[0][0]}):\n"
                  f"{json.dumps(to_write[0][1], indent=2, sort_keys=True)}")
        print("\ndry run; nothing written")
        return 1 if failed else 0

    manifest = open(args.manifest, "a", encoding="utf-8") if args.manifest else None
    written = {"registered": 0, "refreshed": 0}
    try:
        for sid, sidecar in to_write:
            path, action = bio_ingest.write_sidecar(store, sid, sidecar)
            written[action] += 1
            if manifest:
                manifest.write(json.dumps(
                    {"staging_id": sid, "path": path, "action": action,
                     "at": time.time()}) + "\n")
    finally:
        if manifest:
            manifest.close()

    print(f"\n{written['registered']} registered, {written['refreshed']} refreshed")
    # Each sidecar stands alone, so the good ones are written; a non-zero exit
    # still says some episodes remain held back.
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
