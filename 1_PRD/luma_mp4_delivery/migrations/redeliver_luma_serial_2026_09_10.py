#!/usr/bin/env python3
"""One-off: re-deliver Luma mcaps whose ``serial_number`` carried a fabricated
task letter.

``luma_mcap_transform.canonical_serial`` inserted the default task letter into
any identifier shaped ``<segments>-<number>``.  That is right for the MP4 rig's
unlettered ``YAM-BIO-016``, which is what it was written for, but ``BIO-NEW-<n>``
shares the shape and is a *collection* id from a different corpus.  It shipped
as ``BIO-NEW-B-006`` -- an identifier present neither in the rig's recordings
nor in the vendor's task sheet -- on 1,920 yun episodes across batches 36-46.

This rewrites each affected episode's mcap **from our local copy** through the
corrected transform and overwrites just that object.  Nothing else in the
episode folder is touched and our stored copy is never modified.

Scope is derived, not hardcoded: an episode is in scope when it is delivered to
Luma, its mcap is on disk, and the serial its ``/task_info`` yields under the
*old* rule differs from the one it yields now.  That test reads the *local*
mcap, which the run never changes, so the set does **not** shrink as episodes
are fixed -- it stays at 1,920.  Re-running is safe (idempotent) but re-uploads
everything; ``--skip-uploaded`` resumes from the manifests instead.

**Not self-inverse.**  The fix is not "strip a B from the bucket" -- it is
"re-derive from the local mcap", which is idempotent: running twice uploads the
same correct bytes.  The bucket copy is only ever read for verification.

Every upload is preceded by a per-episode check that the rewrite differs from
the *previously delivered* bytes in the ``/task_info`` ``serial_number`` and
nothing else -- not the gripper, not a topic name, not a message count -- so a
mistaken rig profile cannot quietly ship a re-inverted gripper alongside the
serial it was meant to correct.

Usage::

    python migration/redeliver_luma_serial_2026_09_10.py --dry-run
    python migration/redeliver_luma_serial_2026_09_10.py --limit 3 --yes
    python migration/redeliver_luma_serial_2026_09_10.py --verify --limit 3
    # The full pass can outlive the session that starts it, so run it detached
    # and resumable from its manifests:
    setsid nohup python3 -u migration/redeliver_luma_serial_2026_09_10.py --yes --skip-uploaded --jobs 12 > resume.log 2>&1 < /dev/null &

Run 2026-09-10: 869 uploaded before the session harness killed the first pass,
the remaining 1,051 on resume, 0 failures.  Manifests are
``redeliver_luma_serial_*.jsonl`` next to this script.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
import multiprocessing
from concurrent.futures import ProcessPoolExecutor, as_completed

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "upload")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from mcap.reader import make_reader                          # noqa: E402

from staging import Config, LUMA_CUSTOMER_ID, StagingStore   # noqa: E402
import luma_mcap_transform as lmt                            # noqa: E402
from luma_mcap_transform import (                            # noqa: E402
    TASK_INFO_TOPIC,
    transform_mcap,
)
from submit_to_luma import (                                 # noqa: E402
    BUCKET,
    delivered_basename,
    limits_for,
    profile_for,
)

RETRIES = 3


def old_canonical_serial(value: str, *, letter: str = "B") -> str:
    """The pre-fix rule, kept verbatim so "what we shipped" is reproducible.

    Only used to decide scope and to build the reference bytes the rewrite is
    checked against.  It is never used to produce anything that is uploaded.
    """
    parts = (value or "").split("-")
    if len(parts) < 2 or not parts[-1].isdigit():
        return value
    if len(parts[-2]) == 1 and parts[-2].isalpha():
        return value
    return "-".join(parts[:-1] + [letter, parts[-1]])


def _load_legacy_transform():
    """A second, independent copy of the transform running the *old* rule.

    The reference bytes have to come from the pre-fix transform, and the
    obvious way to get them -- swapping ``lmt.canonical_serial`` around each
    call -- is a data race: the module global is shared, so under a thread pool
    one episode's "old" patch lands in another's "new" rewrite.  That is not
    theoretical; it produced two ``BIO-NEW-B-003`` rewrites on the first
    three-episode dry run.

    Loading the module a second time under its own name gives the legacy rule
    its own namespace, patched once at import and never mutated again, so both
    transforms are pure and the pool can run wide.
    """
    import importlib.util
    path = os.path.join(_ROOT, "upload", "luma_mcap_transform.py")
    spec = importlib.util.spec_from_file_location(
        "luma_mcap_transform__legacy", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.canonical_serial = old_canonical_serial
    return mod


_LEGACY = _load_legacy_transform()


def _task_info(path: str) -> "dict | None":
    """The delivered ``/task_info`` payload of an mcap, as a dict."""
    with open(path, "rb") as fh:
        for _s, _c, msg in make_reader(fh).iter_messages(topics=[TASK_INFO_TOPIC]):
            text = lmt._decode_std_string(msg.data)
            if text is None:
                return None
            try:
                obj = json.loads(text)
            except json.JSONDecodeError:
                return None
            return obj if isinstance(obj, dict) else None
    return None


def _rewrite(module, src: str, dst: str, task: str, limits,
             from_subtasks: bool, calibrated: bool) -> None:
    """Run ``module``'s delivery transform.  Pure: no shared state is mutated."""
    module.transform_mcap(src, dst, task_description=task,
                          gripper_limits=limits,
                          serial_from_subtasks=from_subtasks,
                          strict=calibrated)


def _messages(path: str) -> list:
    """``(topic, payload)`` for every message, in file order."""
    out = []
    with open(path, "rb") as fh:
        for _s, ch, msg in make_reader(fh).iter_messages():
            out.append((ch.topic, msg.data))
    return out


def check(before: str, after: str, want_serial: str) -> "list[str]":
    """Reasons this rewrite must not be uploaded.  Empty means good.

    ``before`` is the episode re-derived under the *old* rule -- byte-for-byte
    what Luma already holds -- so the comparison is against the delivered
    artefact rather than against our raw copy.  Exactly one message may differ,
    it must be ``/task_info``, and within it only ``serial_number`` may move.
    """
    problems: list[str] = []
    a, b = _messages(before), _messages(after)
    if len(a) != len(b):
        return [f"message count moved: {len(a)} -> {len(b)}"]
    differing = [i for i, ((ta, pa), (tb, pb)) in enumerate(zip(a, b))
                 if ta != tb or pa != pb]
    for i in differing:
        if a[i][0] != b[i][0]:
            problems.append(f"msg {i}: topic {a[i][0]} -> {b[i][0]}")
            return problems
        if a[i][0] != TASK_INFO_TOPIC:
            problems.append(f"msg {i}: payload moved on {a[i][0]}, "
                            f"which this fix must not touch")
            return problems
    if len(differing) > 1:
        problems.append(f"{len(differing)} messages differ; only /task_info may")
        return problems
    old, new = _task_info(before), _task_info(after)
    if new is None:
        return ["rewritten /task_info is not a JSON object"]
    if old is not None:
        moved = {k for k in set(old) | set(new) if old.get(k) != new.get(k)}
        if moved - {"serial_number"}:
            problems.append(f"/task_info keys moved besides serial_number: "
                            f"{sorted(moved)}")
    if new.get("serial_number") != want_serial:
        problems.append(f"serial is {new.get('serial_number')!r}, "
                        f"expected {want_serial!r}")
    if not differing:
        problems.append("nothing changed; episode should not have been in scope")
    return problems


def affected(store: StagingStore) -> list:
    """Episodes whose delivered serial moves under the fix.

    ``(staging_id, task_name, supplier, episode_format, local_mcap_path,
    old_serial, new_serial)``.
    """
    rows = store.db.query_all(
        "SELECT cs.staging_id, e.task_name, e.supplier, e.episode_format, f.path "
        "FROM customer_statuses cs "
        "JOIN episodes e ON e.staging_id = cs.staging_id "
        "JOIN files f ON f.staging_id = cs.staging_id AND f.kind = 'mcap' "
        "WHERE cs.customer_id = ? AND cs.customer_upload_time IS NOT NULL "
        "  AND f.size_bytes IS NOT NULL "
        "ORDER BY cs.staging_id",
        (LUMA_CUSTOMER_ID,))
    out = []
    for r in rows:
        sid = int(r["staging_id"])
        path = str(r["path"])
        if not os.path.exists(path):
            continue
        info = _task_info(path)
        if not info:
            continue
        src = str(info.get("serial_number") or info.get("task_id") or "")
        if not src:
            continue
        old, new = old_canonical_serial(src), lmt.canonical_serial(src)
        if old == new:
            continue
        out.append((sid, str(r["task_name"] or ""), str(r["supplier"] or ""),
                    str(r["episode_format"] or ""), path, old, new))
    return out


def upload(local: str, staging_id: int) -> None:
    dest = f"{BUCKET}/{staging_id}/{delivered_basename('mcap', os.path.basename(local))}"
    last = ""
    for _attempt in range(RETRIES):
        proc = subprocess.run(["gcloud", "storage", "cp", local, dest],
                              capture_output=True, text=True, timeout=1800)
        if proc.returncode == 0:
            return
        last = (proc.stderr or "").strip()[:300]
        time.sleep(2)
    raise RuntimeError(f"upload failed for {staging_id}: {last}")


def one(store: StagingStore, row, apply: bool) -> dict:
    sid, task, supplier, fmt, src, old, new = row
    rec = {"staging_id": sid, "old_task_id": old, "new_task_id": new,
           "supplier": supplier, "episode_format": fmt}
    profile = profile_for(supplier, fmt)
    if profile is None:
        rec["error"] = f"no delivery profile for rig {supplier}/{fmt}"
        return rec
    limits = limits_for(store, sid, profile)
    if not limits:
        rec["error"] = "gripper calibration missing"
        return rec
    from_subtasks = profile.task_info == "subtasks"
    calibrated = profile.gripper == "calibrated"
    with tempfile.TemporaryDirectory(prefix=f"luma.serial.{sid}.") as tmp:
        base = delivered_basename("mcap", os.path.basename(src))
        before = os.path.join(tmp, f"before_{base}")
        after = os.path.join(tmp, base)
        try:
            _rewrite(_LEGACY, src, before, task, limits, from_subtasks, calibrated)
            _rewrite(lmt, src, after, task, limits, from_subtasks, calibrated)
        except Exception as e:                       # noqa: BLE001
            rec["error"] = f"transform: {type(e).__name__}: {e}"
            return rec
        problems = check(before, after, new)
        if problems:
            rec["error"] = "; ".join(problems)
            return rec
        rec["bytes"] = os.path.getsize(after)
        if not apply:
            rec["would_upload"] = (
                f"{BUCKET}/{sid}/{delivered_basename('mcap', base)}")
            return rec
        try:
            upload(after, sid)
        except Exception as e:                       # noqa: BLE001
            rec["error"] = f"upload: {type(e).__name__}: {e}"
            return rec
        rec["uploaded"] = True
    return rec


def verify(rows, limit: int) -> int:
    """Read the *bucket* copy back and report its delivered serial."""
    rows = rows[:limit] if limit else rows
    bad = 0
    with tempfile.TemporaryDirectory(prefix="luma.serial.verify.") as tmp:
        for sid, _task, _sup, _fmt, src, _old, new in rows:
            base = delivered_basename("mcap", os.path.basename(src))
            dest = f"{BUCKET}/{sid}/{base}"
            local = os.path.join(tmp, f"{sid}_{base}")
            proc = subprocess.run(["gcloud", "storage", "cp", dest, local],
                                  capture_output=True, text=True, timeout=1800)
            if proc.returncode != 0:
                print(f"  {sid}: download failed: "
                      f"{(proc.stderr or '').strip()[:160]}")
                bad += 1
                continue
            info = _task_info(local) or {}
            got = info.get("serial_number")
            ok = got == new
            bad += 0 if ok else 1
            print(f"  {sid}: bucket serial {got!r} "
                  f"{'OK' if ok else f'EXPECTED {new!r}'}")
            os.remove(local)
    return bad


def _previously_uploaded() -> "set[int]":
    """Staging ids an earlier run of this migration recorded as uploaded.

    Resuming by manifest rather than by re-deriving scope matters: the scope
    test compares old-rule and new-rule output on the *local* mcap, which does
    not change when the bucket does, so every episode stays "in scope" after it
    is fixed.  Re-uploading is harmless (idempotent) but wasted transfer, so
    completed work is read back from the manifests instead.
    """
    import glob
    here = os.path.dirname(os.path.abspath(__file__))
    done: "set[int]" = set()
    for path in glob.glob(os.path.join(here, "redeliver_luma_serial_*.jsonl")):
        with open(path) as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue                  # a final line cut short by a kill
                if rec.get("uploaded"):
                    done.add(int(rec["staging_id"]))
    return done


_STORE = None


def _init_worker() -> None:
    """Give each worker process its own store, and so its own DB connection.

    The pool is processes, not threads: the transform is pure-Python CPU work,
    so under the GIL six threads ran at roughly one core (869 episodes took
    5h20m).  Workers are spawned rather than forked so none inherits the
    parent's open database connection.
    """
    global _STORE
    _STORE = StagingStore(Config.from_env())


def _work(task) -> dict:
    row, apply = task
    return one(_STORE, row, apply)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true",
                    help="actually upload (default: dry run)")
    ap.add_argument("--dry-run", action="store_true", help="explicit dry run")
    ap.add_argument("--limit", type=int, default=None,
                    help="stop after this many episodes")
    ap.add_argument("--jobs", type=int, default=4)
    ap.add_argument("--verify", action="store_true",
                    help="read bucket copies back instead of writing")
    ap.add_argument("--skip-uploaded", action="store_true",
                    help="skip episodes an earlier run's manifest records as uploaded")
    ap.add_argument("--manifest", default="")
    args = ap.parse_args(argv)

    store = StagingStore(Config.from_env())
    rows = affected(store)
    print(f"episodes whose delivered serial moves: {len(rows)}")
    if args.skip_uploaded:
        done = _previously_uploaded()
        before = len(rows)
        rows = [r for r in rows if r[0] not in done]
        print(f"  skipping {before - len(rows)} already uploaded by an earlier run")
    if not rows:
        print("nothing to do.")
        return 0
    if args.limit:
        rows = rows[: args.limit]
    from collections import Counter
    print(f"  in this run: {len(rows)}")
    print("  by rig:", dict(Counter((r[2], r[3]) for r in rows)))
    print("  corrections:", dict(Counter((r[5], r[6]) for r in rows).most_common(5)))

    if args.verify:
        bad = verify(rows, args.limit or 0)
        print(f"\nverify: {len(rows) - bad}/{len(rows)} correct in the bucket")
        return 1 if bad else 0

    apply = args.yes and not args.dry_run
    if not apply:
        print("\nDRY RUN -- nothing uploaded.  Re-run with --yes.")

    manifest = args.manifest or os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        f"redeliver_luma_serial_{int(time.time())}.jsonl")
    ok = failed = 0
    ctx = multiprocessing.get_context("spawn")
    with open(manifest, "w") as fh, ProcessPoolExecutor(
            args.jobs, mp_context=ctx, initializer=_init_worker) as ex:
        futs = {ex.submit(_work, (r, apply)): r for r in rows}
        for fut in as_completed(futs):
            try:
                rec = fut.result()
            except Exception as e:           # noqa: BLE001 -- a worker died
                r = futs[fut]
                rec = {"staging_id": r[0], "old_task_id": r[5],
                       "new_task_id": r[6],
                       "error": f"worker: {type(e).__name__}: {e}"}
            fh.write(json.dumps(rec) + "\n")
            fh.flush()
            if "error" in rec:
                failed += 1
                print(f"  FAIL {rec['staging_id']}: {rec['error'][:160]}", flush=True)
            else:
                ok += 1
                if ok % 100 == 0:
                    print(f"  ...{ok} done", flush=True)
    print(f"\n{'uploaded' if apply else 'checked'}={ok} failed={failed}")
    print(f"manifest: {manifest}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
