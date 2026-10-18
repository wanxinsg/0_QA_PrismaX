"""Ingest verlet's Biology Lab episodes from Cloudflare R2, with calibration.

One owner for what was a pair of one-off scripts on 2026-09-03/04: pull the
episodes the supplier has published to ``prisma-bio-batch3`` that we do not hold
yet, register each through the ordinary upload API, and give every episode the
gripper-calibration sidecar without which it cannot be delivered to Luma.

Two things about this supplier's bucket shape the code has to know, because
neither is guessable:

* **The episode directory is repeated** -- ``<payload_prefix>/<episode_dir>/
  cam_high.mp4`` -- while the mcap sits a level up at ``<payload_prefix>.mcap``.
  So discovery reads the artifact list out of each ``_status`` manifest, which
  names every key outright, and uses the bucket listing only to confirm those
  keys have landed.  The manifest is authoritative about what an episode
  *contains*; the listing is authoritative about what has *arrived*.
* **Calibration travels inside each episode's MCAP.**  It began as one
  aggregate ``dataset_info.json`` per prefix (:func:`load_calibration`), but the
  supplier retired that file on 2026-09-10 and every export since carries a
  ``gripper_limits`` metadata record instead.  The sidecar is now built from the
  record in **our own local copy** of the MCAP (:func:`resolve_sidecar`), never
  from the bucket's: a re-export can move the gripper's raw zero point, so the
  limits are only valid against the bytes they shipped with.  Staging 32588 is
  the proof -- the bucket's current copy reads left ``(0.046, -5.276)``, our
  copy and our sidecar agree on ``(6.327, 0.982)``, and both are right for
  their own file.

The two top-level prefixes are **not a partition -- they are a pipeline.**
Episodes land in ``verlet-bio-mcap-unreviewed`` and are **promoted** into
``verlet-bio-mcap`` once the supplier has reviewed them, and promotion is a
*re-export*: on 2026-09-05, of 811 directories present in both, 810 carried the
same supplier ``episode_id`` (the same recording) while all 811 had a different
``run_sha256`` and 634 had different media sizes.

That is why :func:`pending` skips a directory we already hold under *either*
key.  Read as a partition -- which is how it looks until the first promotion --
the reviewed copy is an unseen episode, and ingesting it duplicates a recording
we already have: 810 of them, the first time this ran after promotion began.

Each prefix still gets its own idempotency-key prefix, because the two copies
have separate calibration entries and the key is what says which one an
episode's sidecar was built from.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

# ``staging_client`` is a flat module under ``client/``.  Put it on the path
# here rather than relying on the caller to have done it: the webui2 job kind
# arranges ``workers/`` and ``upload/`` but not ``client/``, and the resulting
# ImportError only fires once there is something to fetch -- which is to say,
# never in a test run against an already-ingested bucket.
_CLIENT_DIR = str(Path(__file__).resolve().parent.parent.parent / "client")
if _CLIENT_DIR not in sys.path:
    sys.path.insert(0, _CLIENT_DIR)

BUCKET_ENV = "R2_BIO_BUCKET"
DEFAULT_BUCKET = "prisma-bio-batch3"

# Idempotency-key prefix per bucket prefix.  Distinct on purpose: see the module
# docstring on episodes that appear under both.
PREFIXES = {
    "verlet-bio-mcap": "verlet-bio-mcap-",
    "verlet-bio-mcap-unreviewed": "verlet-bio-unrev-",
}
KEY_LIKE = "verlet-bio-%"
DATASET_INFO = "dataset_info.json"

TASK_NAME = "Biology Lab"
SUPPLIER = "verlet"
UPLOADER = "verlet"
ROBOT_TYPE = "yam"
EPISODE_FORMAT = "mp4"

RGB_VIDEOS = ("cam_high.mp4", "cam_left.mp4", "cam_right.mp4")

SIDECAR_BASENAME = "verlet_gripper_limits.json"

# The metadata record the supplier writes into every MCAP exported since
# 2026-09-03, and the per-rig index published beside the episodes on 2026-09-10.
MCAP_CALIBRATION_RECORD = "gripper_limits"
ROBOTS_DIR = "robots"
ROBOTS_INDEX = f"{ROBOTS_DIR}/index.json"

# What the supplier's dataset_info declared the embodiment to be, before that
# file was retired.  Carried forward so a sidecar built from an MCAP record
# describes the robot the same way the 1,454 built from dataset_info do.
SUPPLIER_ROBOT_TYPE = "i2rt_yam_bimanual"
SIDECAR_SCHEMA = 1

# The supplier keys calibration by arm; the delivery transform keys it by topic.
LEADER_TOPIC = {
    "left": "/robot/arm_left_leader/joint_states",
    "right": "/robot/arm_right_leader/joint_states",
}


class CredentialsMissing(RuntimeError):
    """The R2 credentials are not in the environment."""


def bucket_name() -> str:
    return os.environ.get(BUCKET_ENV) or DEFAULT_BUCKET


def client():
    """A boto3 S3 client pointed at R2.

    Raises :class:`CredentialsMissing` rather than returning a client that will
    fail later with a signature error: a job that cannot reach the bucket
    should say so in its first log line, not halfway through a listing.
    """
    missing = [v for v in ("R2_ENDPOINT", "R2_ACCESS_KEY", "R2_SECRET_KEY")
               if not os.environ.get(v)]
    if missing:
        raise CredentialsMissing(
            f"missing {', '.join(missing)} -- add them to the service "
            f"environment (/etc/actuate-webui.env) and restart")
    import boto3
    from botocore.config import Config as BotoConfig

    # ``response_checksum_validation="when_required"`` turns off botocore's
    # default response checking, which is **broken for ranged downloads**:
    # ``download_file`` fetches anything over 8 MB as parts, and botocore
    # validates each part's bytes against the object's *whole-object*
    # ``ChecksumSHA256``, which cannot match.  Every file above the threshold
    # failed with "Expected checksum ... did not match calculated checksum"
    # while the object itself was perfect -- a plain GET of the same key hashed
    # to exactly the declared value and the media decoded without error.
    #
    # Integrity is not dropped, it is moved somewhere correct: :func:`_download`
    # verifies the finished file end to end against that same declared
    # checksum, which is a stronger check than the one being disabled and is
    # indifferent to how the transfer was chunked.
    return boto3.client(
        "s3", endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY"],
        aws_secret_access_key=os.environ["R2_SECRET_KEY"], region_name="auto",
        config=BotoConfig(response_checksum_validation="when_required"))


# ------------------------------------------------------------------ discovery
@dataclass
class BucketEpisode:
    """One complete episode in the bucket, joined to its ``_status`` manifest."""

    prefix: str
    folder: str              # the manifest's payload_prefix
    episode_dir: str
    mcap: tuple              # (key, size)
    videos: list             # [(key, size), ...] in RGB_VIDEOS order
    episode_id: str = ""     # the supplier's recording uuid, from the manifest

    @property
    def idempotency_key(self) -> str:
        return PREFIXES[self.prefix] + self.episode_dir

    @property
    def total_bytes(self) -> int:
        return self.mcap[1] + sum(sz for _, sz in self.videos)


def _list_all(s3, bucket: str, prefix: str) -> dict:
    out = {}
    for page in s3.get_paginator("list_objects_v2").paginate(
            Bucket=bucket, Prefix=prefix):
        for o in page.get("Contents", []):
            out[o["Key"]] = int(o["Size"])
    return out


def discover(s3, *, prefixes=None, log: Callable[[str], None] = lambda _m: None
             ) -> "tuple[list, list, list]":
    """``(episodes, excluded, incomplete)`` across the bucket's prefixes.

    ``incomplete`` is "not ready in this snapshot" -- a manifest published ahead
    of its media, or media whose manifest has not landed -- and is skipped
    silently; the next run picks it up.  Nothing here raises on a half-arrived
    episode, because the supplier uploads continuously and a snapshot always
    catches some mid-flight.
    """
    bucket = bucket_name()
    episodes, excluded, incomplete = [], [], []
    for prefix in (prefixes or sorted(PREFIXES)):
        sizes = _list_all(s3, bucket, prefix + "/")
        status_keys = [k for k in sizes if k.startswith(f"{prefix}/_status/")]
        log(f"  {prefix}/: {len(sizes)} objects, {len(status_keys)} manifests")

        def _load(key):
            return json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())

        with ThreadPoolExecutor(min(32, max(len(status_keys), 1))) as pool:
            docs = list(pool.map(_load, status_keys))

        claimed = set()
        for doc in sorted(docs, key=lambda d: str(d.get("payload_prefix") or "")):
            folder = str(doc.get("payload_prefix") or doc.get("folder") or "")
            if not folder:
                incomplete.append(f"{prefix}: manifest with no payload_prefix")
                continue
            state = str(doc.get("status") or "completed")
            if doc.get("excluded") or state != "completed":
                excluded.append(f"{prefix}/{folder}: status={state}")
                continue
            if doc.get("audit_clean") is False:
                # The supplier's own audit failed; not ours to reinterpret.
                excluded.append(f"{prefix}/{folder}: audit_clean=false")
                continue
            keys = [f"{prefix}/{a['path']}" for a in (doc.get("artifacts") or [])
                    if a.get("path")]
            claimed.update(keys)
            if any(k not in sizes for k in keys):
                incomplete.append(f"{prefix}/{folder}: artifacts not all landed")
                continue
            mcaps = [(k, sizes[k]) for k in keys if k.endswith(".mcap")]
            videos = {os.path.basename(k): (k, sizes[k])
                      for k in keys if k.endswith(".mp4")}
            missing = [n for n in RGB_VIDEOS if n not in videos]
            if len(mcaps) != 1 or missing:
                incomplete.append(f"{prefix}/{folder}: {len(mcaps)} mcap(s), "
                                  f"missing {missing or 'nothing'}")
                continue
            episodes.append(BucketEpisode(
                prefix=prefix, folder=folder, episode_dir=folder.split("/")[-1],
                mcap=mcaps[0], videos=[videos[n] for n in RGB_VIDEOS],
                episode_id=str(doc.get("episode_id") or "")))

        # Media with no manifest yet.  Neither the prefix-level sidecar nor the
        # ``robots/`` tree (URDFs and meshes per rig) is episode media; counted
        # as media they surface as phantom "not ready" episodes on every run.
        orphans = {k for k in sizes
                   if not k.startswith(f"{prefix}/_status/")
                   and not k.startswith(f"{prefix}/{ROBOTS_DIR}/")
                   and k != f"{prefix}/{DATASET_INFO}"} - claimed
        for folder in sorted({"/".join(k.split("/")[:3]) for k in orphans}):
            incomplete.append(f"{folder}: media with no manifest in this snapshot")
    return episodes, excluded, incomplete


def registered_keys(store) -> set:
    rows = store.db.query_all(
        "SELECT idempotency_key AS k FROM episodes WHERE idempotency_key LIKE ?",
        (KEY_LIKE,))
    return {str(r["k"]) for r in rows}


def held_episode_dirs(store) -> set:
    """Every episode directory we already hold, under either prefix's key."""
    dirs = set()
    for key in registered_keys(store):
        where = bucket_prefix_of(key)
        if where is not None:
            dirs.add(where[1])
    return dirs


def pending(store, episodes: list) -> "tuple[list, list]":
    """``(to_fetch, already_held_under_the_other_prefix)``.

    The second list is the promoted copies -- recordings we already hold that
    the supplier has since re-exported into the reviewed prefix.  Returned
    rather than silently dropped so a run can say how many it skipped and why;
    a caller that ingested them would create a duplicate episode per recording.
    """
    have = registered_keys(store)
    held = held_episode_dirs(store)
    to_fetch, promoted = [], []
    for e in episodes:
        if e.idempotency_key in have:
            continue
        (promoted if e.episode_dir in held else to_fetch).append(e)
    return to_fetch, promoted


# --------------------------------------------------------------------- ingest
def _sha256_b64(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(4 << 20), b""):
            h.update(chunk)
    return base64.b64encode(h.digest()).decode()


def _download(s3, bucket: str, key: str, dest: str, expected: int) -> None:
    """Fetch one object and verify it end to end.

    A truncated or corrupted transfer is the failure that matters: a partial
    MP4 registers fine and only breaks much later, in post-processing.

    Size is checked against the run's frozen listing, but the supplier
    re-encodes objects in place, so a mismatch is re-checked against the
    object's *current* size before it is called a failure.  When the object
    declares a ``ChecksumSHA256`` the finished file is hashed and compared to
    it -- one whole-object check on the bytes that landed, which is what
    botocore's per-range validation was trying and failing to do.
    """
    s3.download_file(bucket, key, dest)
    got = os.path.getsize(dest)
    head = s3.head_object(Bucket=bucket, Key=key)
    current = int(head["ContentLength"])
    if got != expected and got != current:
        raise RuntimeError(f"short read for {key}: {got} != {expected}")
    declared = head.get("ChecksumSHA256")
    if declared:
        actual = _sha256_b64(dest)
        if actual != declared:
            raise RuntimeError(
                f"checksum mismatch for {key}: {actual} != {declared}")


def fetch_episode(s3, ep: BucketEpisode, dest_dir: str, jobs: int = 6) -> list:
    """Download one episode's media; return the local paths.

    Basenames are unique within an episode (three fixed cameras plus an mcap
    named for the episode), so the bucket's nesting can be flattened.
    """
    bucket = bucket_name()
    wanted = [ep.mcap, *ep.videos]
    with ThreadPoolExecutor(jobs) as pool:
        list(pool.map(
            lambda ks: _download(s3, bucket, ks[0],
                                 os.path.join(dest_dir, os.path.basename(ks[0])),
                                 ks[1]),
            wanted))
    return [os.path.join(dest_dir, os.path.basename(k)) for k, _ in wanted]


def next_upload_id(server: str) -> int:
    """A fresh upload batch id from the server."""
    import staging_client

    return staging_client.Client(server).next_upload_id()


def ingest_one(s3, ep: BucketEpisode, *, upload_id: int, scratch: str,
               server: str, jobs: int = 6) -> int:
    """Fetch one bucket episode and register it through the upload API.

    Deliberately the API rather than a direct insert: file placement, the
    free-space floor and supplier inference all live behind ``POST /episodes``,
    so an episode ingested here is indistinguishable from a collector's upload
    and lands in the post-processing queue by itself.
    """
    import staging_client

    tmpdir = tempfile.mkdtemp(prefix=f"bio_{ep.episode_dir[:24]}_", dir=scratch)
    try:
        paths = fetch_episode(s3, ep, tmpdir, jobs)
        return staging_client.Client(server).upload_episode(
            paths, robot_type=ROBOT_TYPE, uploader_identity=UPLOADER,
            upload_id=upload_id, task_name=TASK_NAME, supplier=SUPPLIER,
            episode_format=EPISODE_FORMAT, idempotency_key=ep.idempotency_key)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


# ------------------------------------------------------------------- sidecars
def load_calibration(s3) -> dict:
    """``{(prefix, episode_dir): (prefix, key, doc, header, entry)}``.

    Keyed on the pair, never the episode directory alone: one directory exists
    under both prefixes with a different supplier ``episode_id`` and different
    limits, and a flat lookup silently resolves to whichever prefix was read
    last.
    """
    bucket = bucket_name()
    out = {}
    for prefix in sorted(PREFIXES):
        key = f"{prefix}/{DATASET_INFO}"
        try:
            doc = json.loads(s3.get_object(Bucket=bucket, Key=key)["Body"].read())
        except Exception:          # noqa: BLE001 - a prefix may not have one yet
            continue
        gc = doc.get("gripper_calibration") or {}
        header = {k: v for k, v in gc.items() if k != "episodes"}
        for folder, entry in (gc.get("episodes") or {}).items():
            out[(prefix, folder.split("/")[-1])] = (prefix, key, doc, header, entry)
    return out


def bucket_prefix_of(idempotency_key: str) -> "tuple[str, str] | None":
    """``(bucket prefix, episode_dir)`` for an idempotency key, or None."""
    for kp in sorted(PREFIXES, key=lambda p: len(PREFIXES[p]), reverse=True):
        pfx = PREFIXES[kp]
        if idempotency_key.startswith(pfx):
            return kp, idempotency_key[len(pfx):]
    return None


def sidecar_for(staging_id: int, episode_dir: str, prefix: str, key: str,
                doc: dict, header: dict, entry: dict) -> dict:
    """The per-episode document written beside the episode."""
    limits = entry.get("gripper_limits") or {}
    source = entry.get("source") or {}
    arms = {}
    for arm in ("left", "right"):
        lim = limits.get(arm) or {}
        arms[arm] = {"leader_topic": LEADER_TOPIC[arm],
                     "closed_rad": lim.get("closed_rad"),
                     "open_rad": lim.get("open_rad"),
                     "source": source.get(arm)}
    return {
        "schema_version": SIDECAR_SCHEMA,
        "staging_id": staging_id,
        "episode_dir": episode_dir,
        "supplier_episode_id": entry.get("episode_id"),
        "robot": doc.get("dataset") or {},
        "gripper_calibration": {
            "units": header.get("units"),
            "convention": header.get("convention"),
            "note": header.get("note"),
            "arms": arms,
        },
        "provenance": {
            "bucket": bucket_name(), "prefix": prefix, "source_key": key,
            "supplier_schema_version": doc.get("schema_version"),
            "supplier_generated_at": doc.get("generated_at"),
            "written_at": time.time(), "written_by": __name__,
        },
    }


def sidecar_problems(sidecar: dict) -> list:
    """Reasons this sidecar must not be written.  Empty means good."""
    problems = []
    for arm, a in sidecar["gripper_calibration"]["arms"].items():
        c, o = a.get("closed_rad"), a.get("open_rad")
        if not isinstance(c, (int, float)) or isinstance(c, bool) \
                or not isinstance(o, (int, float)) or isinstance(o, bool):
            problems.append(f"{arm}: missing closed_rad/open_rad")
        elif abs(o - c) < 1e-6:
            # The delivery divides by this span; zero is the corruption the
            # fail-closed default exists to prevent, not a value to forward.
            problems.append(f"{arm}: degenerate span {c} -> {o}")
    if not (sidecar.get("robot") or {}).get("robot_type"):
        problems.append("no robot_type in the dataset block")
    return problems


def station_of(episode_dir: str) -> "str | None":
    """The rig segment of an episode directory: ``..._2eef9edf-9372ecc6_ep5``
    -> ``9372ecc6``, the key ``robots/index.json`` is published under."""
    m = re.search(r"-([0-9a-f]{8})_ep\d+$", episode_dir)
    return m.group(1) if m else None


def load_robots(s3) -> dict:
    """``{station: rig entry}`` from every prefix's ``robots/index.json``.

    Informational -- it fills the sidecar's ``robot`` block -- so a missing or
    unreadable index degrades to an empty one rather than failing anything.
    """
    out: dict = {}
    for prefix in sorted(PREFIXES):
        try:
            doc = json.loads(s3.get_object(
                Bucket=bucket_name(), Key=f"{prefix}/{ROBOTS_INDEX}")["Body"].read())
        except Exception:          # noqa: BLE001 - optional
            continue
        if isinstance(doc, dict):
            out.update({k: v for k, v in doc.items() if isinstance(v, dict)})
    return out


def local_mcap(store, staging_id: int) -> "str | None":
    """Our own copy of the episode's supplier MCAP, if it is still on disk.

    The RAW one specifically: it is the file the supplier exported, and the one
    whose raw gripper values the delivery normalises.  A reclaimed RAW row keeps
    its path with a NULL size, which is how "not on disk" is told apart from
    "missing by accident".
    """
    for r in store.db.query_all(
            "SELECT path, size_bytes FROM files WHERE staging_id = ? "
            "AND kind = 'raw' AND lower(path) LIKE ?", (staging_id, "%.mcap")):
        if r["size_bytes"] is not None and os.path.exists(str(r["path"])):
            return str(r["path"])
    return None


def mcap_calibration(path: str) -> "dict | None":
    """The ``gripper_limits`` metadata record of an MCAP, or None."""
    from mcap.reader import make_reader

    with open(path, "rb") as fh:
        for rec in make_reader(fh).iter_metadata():
            if rec.name == MCAP_CALIBRATION_RECORD:
                return dict(rec.metadata)
    return None


def _num(value) -> "float | None":
    """MCAP metadata values are strings; None for anything that is not a number."""
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sidecar_from_record(staging_id: int, episode_dir: str, record: dict, *,
                        mcap_path: str, robot: "dict | None" = None,
                        episode_id: "str | None" = None) -> dict:
    """The same per-episode document :func:`sidecar_for` writes, from an MCAP."""
    arms = {}
    for arm in ("left", "right"):
        arms[arm] = {"leader_topic": LEADER_TOPIC[arm],
                     "closed_rad": _num(record.get(f"{arm}_closed_rad")),
                     "open_rad": _num(record.get(f"{arm}_open_rad")),
                     "source": record.get(f"{arm}_source")}
    return {
        "schema_version": SIDECAR_SCHEMA,
        "staging_id": staging_id,
        "episode_dir": episode_dir,
        "supplier_episode_id": episode_id or None,
        "robot": {"robot_type": SUPPLIER_ROBOT_TYPE, **(robot or {})},
        "gripper_calibration": {
            "units": record.get("units"),
            "convention": record.get("convention"),
            "note": "Read from the episode's own MCAP; valid only for those bytes.",
            "arms": arms,
        },
        "provenance": {
            "source": "mcap_metadata", "record": MCAP_CALIBRATION_RECORD,
            "mcap": os.path.basename(mcap_path),
            "written_at": time.time(), "written_by": __name__,
        },
    }


def _same_arms(a: dict, b: dict) -> bool:
    try:
        x = a["gripper_calibration"]["arms"]
        y = b["gripper_calibration"]["arms"]
        return all(abs(float(x[arm][w]) - float(y[arm][w])) < 1e-9
                   for arm in ("left", "right") for w in ("closed_rad", "open_rad"))
    except (KeyError, TypeError, ValueError):
        return False


def resolve_sidecar(store, staging_id: int, *, robots: "dict | None" = None,
                    episode_id: "str | None" = None) -> "tuple[dict | None, str]":
    """What this episode's sidecar should be.  -> ``(sidecar or None, action)``.

    ``action`` is ``"write"`` (return value must be written), ``"unchanged"``
    (the record agrees with the sidecar on file -- leave it and its provenance
    alone) or ``"kept"`` (no record in our copy; the sidecar on file stays).

    ``"kept"`` covers the exports that predate the record (all of batch 396 and
    part of 400): their sidecars were built from the ``dataset_info.json`` that
    described exactly those bytes, so they are still right, and there is
    nothing newer to replace them with.  An episode with neither a record nor a
    sidecar raises -- held back from delivery rather than guessed at.
    """
    row = store.db.query_one(
        "SELECT idempotency_key FROM episodes WHERE staging_id = ?", (staging_id,))
    key = str(row["idempotency_key"]) if row else ""
    where = bucket_prefix_of(key)
    if where is None:
        raise RuntimeError(f"unrecognised idempotency key {key!r}")
    episode_dir = where[1]

    on_file = sidecar_row(store, staging_id)
    existing = None
    if on_file and os.path.exists(str(on_file["path"])):
        try:
            existing = json.load(open(str(on_file["path"])))
        except (OSError, ValueError):
            existing = None

    mcap = local_mcap(store, staging_id)
    record = mcap_calibration(mcap) if mcap else None
    if record is None:
        if existing is not None:
            return None, "kept"
        raise RuntimeError(
            f"no {MCAP_CALIBRATION_RECORD} record in our copy of {episode_dir} "
            f"({'RAW mcap not on disk' if mcap is None else 'record absent'}) "
            f"and no sidecar on file")

    station = station_of(episode_dir)
    sidecar = sidecar_from_record(
        staging_id, episode_dir, record, mcap_path=mcap,
        robot=(robots or {}).get(station) if station else None,
        episode_id=episode_id or (existing or {}).get("supplier_episode_id"))
    problems = sidecar_problems(sidecar)
    if problems:
        raise RuntimeError("; ".join(problems))
    if existing is not None and _same_arms(existing, sidecar):
        return None, "unchanged"
    return sidecar, "write"


def sidecar_row(store, staging_id: int) -> Optional[dict]:
    return store.db.query_one(
        "SELECT id, path, size_bytes FROM files WHERE staging_id = ? "
        "AND kind = 'metadata' AND original_name = ?",
        (staging_id, SIDECAR_BASENAME))


def write_sidecar(store, staging_id: int, sidecar: dict) -> "tuple[str, str]":
    """Write atomically and register (or refresh).  -> ``(path, action)``.

    ``kind='metadata'``, not ``raw``: RAW is reclaimable, and a delivery
    *precondition* filed somewhere a routine reclamation deletes it becomes an
    episode that silently stops being deliverable months later.
    """
    from staging.models import FileKind

    row = sidecar_row(store, staging_id)
    path = Path(row["path"]) if row else Path(
        store.kind_dir(staging_id, FileKind.METADATA)) / SIDECAR_BASENAME
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(sidecar, indent=2, sort_keys=True) + "\n",
                   encoding="utf-8")
    os.replace(tmp, path)
    if row is None:
        store.register_existing_file(staging_id, FileKind.METADATA, str(path))
        return str(path), "registered"
    store.db.execute("UPDATE files SET size_bytes = ? WHERE id = ?",
                     (path.stat().st_size, row["id"]))
    store._recompute_total_size(staging_id)      # noqa: SLF001
    store.db.commit()
    return str(path), "refreshed"


def episodes_needing_sidecar(store) -> list:
    """``(staging_id, idempotency_key)`` for bio episodes without a current one.

    Includes episodes that already have one: :func:`resolve_sidecar` leaves an
    agreeing one untouched, and checking is what catches an episode whose
    sidecar is missing or no longer matches its own MCAP.
    """
    rows = store.db.query_all(
        "SELECT staging_id, idempotency_key FROM episodes "
        "WHERE idempotency_key LIKE ? ORDER BY staging_id", (KEY_LIKE,))
    return [(int(r["staging_id"]), str(r["idempotency_key"])) for r in rows]
