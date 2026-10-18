#!/usr/bin/env python3
"""One-off: re-deliver the yun MP4 rig's Luma mcaps with the gripper unflipped.

The ``yun`` MP4 rig normalises its leader gripper with **0.0 closed**, the
opposite end from the ``yun`` SVO2 rig.  Delivery keyed its profile on the
supplier rather than the rig, so both got the SVO2 rig's ``1 - x`` and every
MP4 episode reached ``gs://prismax-raw-luma`` with the gripper inverted: closed
arrived as 1.0 where Luma's convention -- the one the SVO2 corpus established
-- is closed 0.0.  See :mod:`luma_mcap_transform` for how the polarity was
pinned (wrist video, staging 27968/27965 against 27982/27975).

This rewrites each affected episode's ``telemetry.webui.mcap`` **from our local
copy** through the corrected :func:`transform_mcap` and overwrites just that
object.  Nothing else in the episode folder is touched, and our stored copy is
never modified.

Scope: ``supplier='yun'``, ``episode_format='mp4'``, already delivered to Luma.
The SVO2 deliveries are the reference and are byte-for-byte unaffected; verlet
has never been delivered.

**Not self-inverse.**  The fix is not "invert what is in the bucket" -- it is
"re-derive from the local mcap", which is idempotent: running twice uploads the
same correct bytes.  That is why the source is always local and the bucket copy
is only ever read for verification.

Every upload is preceded by a per-episode check that the rewritten file differs
from the local source in the gripper slots **only**, so a bug in the transform
cannot quietly ship renamed topics or a mangled ``/task_info``.

Usage::

    python migration/redeliver_luma_mp4_gripper_2026_09_03.py --dry-run
    python migration/redeliver_luma_mp4_gripper_2026_09_03.py --limit 3 --yes
    python migration/redeliver_luma_mp4_gripper_2026_09_03.py --yes
    python migration/redeliver_luma_mp4_gripper_2026_09_03.py --verify --limit 5
"""

from __future__ import annotations

import argparse
import json
import os
import struct
import subprocess
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "upload")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mcap.reader import make_reader                        # noqa: E402

from staging import Config, LUMA_CUSTOMER_ID, StagingStore  # noqa: E402
from luma_mcap_transform import (                           # noqa: E402
    LEADER_TOPICS,
    MP4_NORMALISED_LIMITS,
    _cdr_offsets,
    transform_mcap,
)
from submit_to_luma import BUCKET, delivered_basename       # noqa: E402

RETRIES = 3


def affected(store: StagingStore) -> list:
    """``(staging_id, task_name, local_mcap_path)`` for every episode in scope."""
    rows = store.db.query_all(
        "SELECT cs.staging_id, e.task_name, f.path "
        "FROM customer_statuses cs "
        "JOIN episodes e ON e.staging_id = cs.staging_id "
        "JOIN files f ON f.staging_id = cs.staging_id AND f.kind = 'mcap' "
        "WHERE cs.customer_id = ? AND cs.customer_upload_time IS NOT NULL "
        "  AND lower(e.supplier) = 'yun' AND lower(e.episode_format) = 'mp4' "
        "  AND f.size_bytes IS NOT NULL "
        "ORDER BY cs.staging_id",
        (LUMA_CUSTOMER_ID,))
    return [(int(r["staging_id"]), str(r["task_name"] or ""), str(r["path"]))
            for r in rows]


def _grippers(path: str) -> list:
    """``(topic, position, velocity)`` for every leader JointState."""
    out = []
    with open(path, "rb") as fh:
        for _s, ch, msg in make_reader(fh).iter_messages(topics=list(LEADER_TOPICS)):
            pos, vel = _cdr_offsets(msg.data)
            if pos is None:
                continue
            out.append((ch.topic,
                        struct.unpack_from("<d", msg.data, pos)[0],
                        struct.unpack_from("<d", msg.data, vel)[0]
                        if vel is not None else None))
    return out


def check(local_src: str, rewritten: str) -> "list[str]":
    """Reasons this rewrite must not be uploaded.  Empty means good.

    The MP4 rig's corrected delivery is the identity on the gripper, so the
    rewritten file's gripper must equal the raw one -- and every value must sit
    in [0, 1], because a normalised rig that does not is not this rig.
    """
    problems = []
    src, out = _grippers(local_src), _grippers(rewritten)
    if len(src) != len(out):
        return [f"message count moved: {len(src)} -> {len(out)}"]
    if not src:
        return ["no leader gripper messages in the source"]
    for i, ((ts, ps, vs), (to, po, vo)) in enumerate(zip(src, out)):
        if ts != to:
            problems.append(f"msg {i}: topic {ts} -> {to}")
            break
        if struct.pack("<d", ps) != struct.pack("<d", po):
            problems.append(f"msg {i}: gripper moved {ps!r} -> {po!r}; "
                            f"the MP4 rig's corrected delivery is the identity")
            break
        if vs is not None and struct.pack("<d", vs) != struct.pack("<d", vo):
            problems.append(f"msg {i}: velocity moved {vs!r} -> {vo!r}")
            break
    lo = min(p for _t, p, _v in out)
    hi = max(p for _t, p, _v in out)
    if lo < -1e-6 or hi > 1.0 + 1e-6:
        problems.append(f"delivered gripper out of [0,1]: [{lo:.6f}, {hi:.6f}]")
    return problems


def rewrite(store_row, tmpdir: str) -> str:
    """Transform one episode's local mcap into ``tmpdir``; return the path."""
    sid, task, src = store_row
    dst = os.path.join(tmpdir, f"{sid}_{delivered_basename('mcap', os.path.basename(src))}")
    transform_mcap(src, dst, task_description=task,
                   gripper_limits={t: MP4_NORMALISED_LIMITS for t in LEADER_TOPICS})
    return dst


def upload(local: str, staging_id: int) -> None:
    dest = f"{BUCKET}/{staging_id}/{delivered_basename('mcap', os.path.basename(local))}"
    last = ""
    for _attempt in range(RETRIES):
        proc = subprocess.run(["gcloud", "storage", "cp", local, dest],
                              capture_output=True, text=True)
        if proc.returncode == 0:
            return
        last = (proc.stderr or "").strip()[:300]
        time.sleep(2)
    raise RuntimeError(f"upload failed for {staging_id}: {last}")


def verify(rows, limit: int) -> int:
    """Report the delivered gripper range of the *bucket* copy."""
    rows = rows[:limit] if limit else rows
    print(f"reading {len(rows)} object(s) back from {BUCKET}", flush=True)
    bad = 0
    with tempfile.TemporaryDirectory() as td:
        for sid, _task, src in rows:
            dest = f"{BUCKET}/{sid}/{delivered_basename('mcap', os.path.basename(src))}"
            out = os.path.join(td, f"{sid}.mcap")
            proc = subprocess.run(["gcloud", "storage", "cp", dest, out],
                                  capture_output=True, text=True)
            if proc.returncode != 0:
                print(f"  #{sid}: cannot read ({(proc.stderr or '').strip()[:80]})")
                bad += 1
                continue
            g = [p for _t, p, _v in _grippers(out)]
            raw = [p for _t, p, _v in _grippers(src)]
            same = (len(g) == len(raw)
                    and all(struct.pack("<d", a) == struct.pack("<d", b)
                            for a, b in zip(g, raw)))
            print(f"  #{sid}: bucket [{min(g):.4f}, {max(g):.4f}]  "
                  f"local [{min(raw):.4f}, {max(raw):.4f}]  "
                  f"{'CORRECTED' if same else 'STILL INVERTED'}")
            bad += 0 if same else 1
            os.unlink(out)
    print(f"\n{len(rows) - bad} corrected, {bad} not")
    return 1 if bad else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--yes", action="store_true", help="actually overwrite objects")
    ap.add_argument("--verify", action="store_true",
                    help="read the bucket copies back instead of writing")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--ids-from", default=None,
                    help="path to a file of staging ids (one per line); only "
                         "those are rewritten.  Re-running the whole set is "
                         "harmless but re-uploads objects that are already "
                         "correct, and every upload is a new generation of a "
                         "customer-visible object -- so a second pass should "
                         "name what it actually needs to touch.")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--manifest", default=None,
                    help="append one JSON line per object overwritten")
    args = ap.parse_args(list(argv) if argv is not None else None)

    store = StagingStore(Config.from_env())
    rows = affected(store)
    print(f"{len(rows)} delivered yun/mp4 episode(s) with a local mcap")
    if args.ids_from:
        with open(args.ids_from) as fh:
            wanted = {int(line) for line in fh if line.strip()}
        rows = [r for r in rows if r[0] in wanted]
        missing = wanted - {r[0] for r in rows}
        print(f"  restricted to {len(rows)} of {len(wanted)} requested id(s)")
        if missing:
            # Named but not in scope: delivered-and-local is the precondition
            # for rewriting anything, so say which rather than silently skip.
            print(f"  {len(missing)} requested id(s) not deliverable/local: "
                  f"{sorted(missing)[:10]}")

    if args.verify:
        return verify(rows, args.limit)

    todo = rows[:args.limit] if args.limit else rows
    print(f"selected {len(todo)}")
    if args.dry_run or not args.yes:
        if todo:
            sid, task, src = todo[0]
            with tempfile.TemporaryDirectory() as td:
                out = rewrite(todo[0], td)
                problems = check(src, out)
            print(f"  sample #{sid}: {'OK' if not problems else problems}")
        print("\nnothing written (pass --yes to overwrite)")
        return 0

    manifest = open(args.manifest, "a", encoding="utf-8") if args.manifest else None
    failed = []

    def one(row):
        """Rewrite, check, upload.  Raises so the caller records the failure."""
        sid, _task, src = row
        with tempfile.TemporaryDirectory() as td:
            out = rewrite(row, td)
            problems = check(src, out)
            if problems:
                raise RuntimeError("; ".join(problems))
            size = os.path.getsize(out)
            upload(out, sid)
        return sid, size

    started = time.time()
    # submit/as_completed rather than map: map re-raises on the first failure
    # and would abandon the rest of the batch, leaving the bucket half fixed --
    # the one state that is worse than all-wrong, because nothing downstream
    # could tell which episodes carry which convention.
    with ThreadPoolExecutor(args.jobs) as pool:
        futures = {pool.submit(one, row): row for row in todo}
        for i, fut in enumerate(as_completed(futures), 1):
            sid, task, src = futures[fut]
            try:
                _sid, size = fut.result()
            except Exception as exc:              # noqa: BLE001 - collected
                failed.append((sid, str(exc)))
                print(f"[{i}/{len(todo)}] FAILED #{sid}: {exc}", flush=True)
                continue
            if manifest:
                manifest.write(json.dumps({
                    "staging_id": sid,
                    "object": f"{BUCKET}/{sid}/"
                              f"{delivered_basename('mcap', os.path.basename(src))}",
                    "bytes": size, "at": time.time()}) + "\n")
                manifest.flush()
            if i % 25 == 0 or i == len(todo):
                rate = i / max(time.time() - started, 1e-9)
                print(f"[{i}/{len(todo)}] {rate * 60:.0f}/min", flush=True)
    if manifest:
        manifest.close()

    ok = len(todo) - len(failed)
    print(f"\n{ok}/{len(todo)} object(s) overwritten in "
          f"{(time.time() - started) / 60:.1f} min")
    if failed:
        print(f"\n{len(failed)} failure(s) -- re-running is safe, the rewrite "
              f"is derived from the local mcap and is idempotent:")
        for sid, err in failed[:15]:
            print(f"  #{sid}: {err}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
