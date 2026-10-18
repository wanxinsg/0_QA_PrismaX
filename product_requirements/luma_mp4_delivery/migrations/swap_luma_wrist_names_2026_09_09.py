"""Swap the delivered wrist videos for the verlet episodes whose labels are crossed.

``migration/audit_verlet_wrist_swap_2026_09_08.py`` measured each wrist video's
motion energy against each arm's joint speed and found 55 Biology Lab episodes,
in 9 supplier sessions, where the video named for one wrist tracks the *other*
arm (median margin +1.2, arms moving independently).  Their Luma deliveries
therefore carry the two wrist views under each other's names.

This renames the two objects in place, per episode::

    gs://prismax-raw-luma/<staging_id>/cam_left_wrist.mp4  <->  cam_right_wrist.mp4

A rename inside one bucket is a server-side copy plus delete -- no egress, no
local copy -- done in three moves through a ``.swap_tmp_`` name, because there
is no atomic exchange.  Every move is bounded by a timeout: an unbounded gcloud
call is what wedged a job before (commit 31bb80b).

**What this does not touch.** The delivered mcap carries per-camera intrinsics
under ``/robot/camera/{left,right}_wrist/image_raw/compressed/camera_info``, and
those genuinely differ between the two cameras (distinct K, D and frame_id).
Whether they should swap along with the video depends on where the fault is --
streams written to the wrong filenames (camera_info is right, leave it) versus
cameras cross-plugged (camera_info is mislabelled too, swap it).  Nothing here
can tell those apart, so the mcap is left exactly as delivered and the question
is raised with a human rather than guessed at.

Nor does it touch our own copies: RAW and L1 keep the supplier's names, because
RAW is the supplier's bytes and the L1 rows are aliases of it.  And it does not
change the delivery code -- a re-delivery of one of these episodes would upload
the crossed names again.

Idempotent: the manifest is read back at start and an episode already recorded
as swapped is skipped, so a re-run cannot swap twice (which would undo it).

Usage::

    python migration/swap_luma_wrist_names_2026_09_09.py                # dry run
    python migration/swap_luma_wrist_names_2026_09_09.py --limit 1 --apply
    python migration/swap_luma_wrist_names_2026_09_09.py --apply
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import time

BUCKET = "gs://prismax-raw-luma"
LEFT, RIGHT = "cam_left_wrist.mp4", "cam_right_wrist.mp4"
TMP = ".swap_tmp_cam_left_wrist.mp4"
GCLOUD_TIMEOUT = 300
HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_CSV = os.path.join(os.path.dirname(HERE), "user_files", "verlet_wrist_crossed.csv")
MANIFEST = os.path.join(HERE, "swap_luma_wrist_names_2026_09_09.jsonl")


def _gcloud(args: list, timeout: int = GCLOUD_TIMEOUT) -> subprocess.CompletedProcess:
    return subprocess.run(["gcloud", "storage", *args], capture_output=True,
                          text=True, timeout=timeout)


def listing(sid: int) -> dict:
    """``{object name: size}`` for one episode's delivery prefix."""
    p = _gcloud(["ls", "-l", f"{BUCKET}/{sid}/"])
    if p.returncode != 0:
        return {}
    out = {}
    for line in p.stdout.splitlines():
        parts = line.split()
        if len(parts) >= 3 and parts[-1].startswith(f"{BUCKET}/{sid}/"):
            try:
                out[parts[-1].rsplit("/", 1)[1]] = int(parts[0])
            except ValueError:
                continue
    return out


def already_done() -> set:
    done = set()
    if os.path.exists(MANIFEST):
        with open(MANIFEST) as fh:
            for line in fh:
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if rec.get("result") == "swapped":
                    done.add(int(rec["staging_id"]))
    return done


def plan_one(sid: int) -> dict:
    have = listing(sid)
    if not have:
        return {"staging_id": sid, "skip": "no delivery prefix in the bucket"}
    if TMP in have:
        return {"staging_id": sid, "skip": f"leftover {TMP} -- repair by hand"}
    missing = [n for n in (LEFT, RIGHT) if n not in have]
    if missing:
        return {"staging_id": sid, "skip": f"missing {', '.join(missing)}"}
    if have[LEFT] == have[RIGHT]:
        # Verification below reads the exchange off the sizes; equal sizes make
        # a completed swap indistinguishable from an untouched pair.
        return {"staging_id": sid, "skip": "left and right are the same size"}
    return {"staging_id": sid, "size_left": have[LEFT], "size_right": have[RIGHT],
            "objects": sorted(have)}


def swap_one(act: dict) -> dict:
    sid = act["staging_id"]
    base = f"{BUCKET}/{sid}"
    moves = [(f"{base}/{LEFT}", f"{base}/{TMP}"),
             (f"{base}/{RIGHT}", f"{base}/{LEFT}"),
             (f"{base}/{TMP}", f"{base}/{RIGHT}")]
    for src, dst in moves:
        p = _gcloud(["mv", src, dst])
        if p.returncode != 0:
            act["result"] = "failed"
            act["error"] = f"{src} -> {dst}: {p.stderr.strip()[:300]}"
            return act
    after = listing(sid)
    ok = (after.get(LEFT) == act["size_right"] and after.get(RIGHT) == act["size_left"]
          and TMP not in after)
    act["result"] = "swapped" if ok else "verify-failed"
    act["after"] = {LEFT: after.get(LEFT), RIGHT: after.get(RIGHT)}
    act["at"] = time.time()
    return act


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", default=DEFAULT_CSV)
    ap.add_argument("--limit", type=int)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    ids = [int(r["staging_id"]) for r in csv.DictReader(open(args.csv))]
    done = already_done()
    print(f"{args.csv}: {len(ids)} episodes; {len(done)} already swapped per the manifest")

    acts, skips = [], []
    for sid in ids:
        if sid in done:
            skips.append((sid, "already swapped"))
            continue
        p = plan_one(sid)
        (skips if "skip" in p else acts).append((sid, p["skip"]) if "skip" in p else p)
    if args.limit:
        acts = acts[:args.limit]

    print(f"to swap: {len(acts)}   skipped: {len(skips)}")
    for sid, why in skips[:10]:
        print(f"  skip {sid}: {why}")
    if len(skips) > 10:
        print(f"  ... and {len(skips)-10} more skips")
    for a in acts[:5]:
        print(f"  {a['staging_id']}  left {a['size_left']:,}B <-> right {a['size_right']:,}B")
    if len(acts) > 5:
        print(f"  ... and {len(acts)-5} more")
    if not args.apply:
        print("\ndry run -- nothing moved.  Re-run with --apply.")
        return 0

    results = []
    with open(MANIFEST, "a") as fh:
        for a in acts:
            r = swap_one(a)
            results.append(r)
            fh.write(json.dumps(r, sort_keys=True) + "\n")
            fh.flush()
            print(f"  {r['staging_id']}: {r['result']}"
                  + (f"  {r.get('error','')}" if r["result"] != "swapped" else ""))
    bad = [r for r in results if r["result"] != "swapped"]
    print(f"\nswapped {len(results)-len(bad)}/{len(results)}; manifest {MANIFEST}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
