#!/usr/bin/env python3
"""Deliver staged episodes to Luma's GCS bucket.

Mirrors ``submit_svo2_to_scale.py`` (same discover / deliver / record shape,
same WebUI job wiring, same requested-hours quota) for a customer who takes
delivery **in a bucket** rather than through a task API.  There is no task to
create and no verdict to collect: "submitting" an episode means copying its
files to ``gs://prismax-raw-luma/<staging_id>/`` and recording the delivery on
the episode's ``customer_statuses`` row for :data:`LUMA_CUSTOMER_ID`.

What is delivered, per episode -- one flat folder, no subdirectories::

    gs://prismax-raw-luma/<staging_id>/telemetry.webui.mcap
    gs://prismax-raw-luma/<staging_id>/cam_high.mp4          (L1, one eye)
    gs://prismax-raw-luma/<staging_id>/cam_left_wrist.mp4
    gs://prismax-raw-luma/<staging_id>/cam_right_wrist.mp4
    gs://prismax-raw-luma/<staging_id>/<robot>.urdf          (when uploaded)

Everything is uploaded from local disk, after two transforms applied in a temp
dir (our stored copies are never modified): the mcap gets the leader gripper
inverted, and -- for the ZED (``svo2``) rig only -- each L1 video is cropped to
the **single delivered eye**.  Those L1s are side-by-side stereo and Luma takes
only the eye their previews are derived from; see :mod:`luma_video_crop`, which
also explains why that crop cannot be done without re-encoding.

The crop is gated on :data:`STEREO_FORMATS`, not on anything measured off the
video: the MP4 rigs and the ego (360) uploads are single-view and Luma's queue
holds thousands of each, so cropping by shape would quietly halve them.

The camera-original ``.svo2`` files are **no longer delivered**.  They were,
copied bucket-to-bucket from the RAW mirror, until the single-eye requirement
landed: an ``.svo2`` is inherently full stereo, so shipping it would hand over
the very eye the video crop exists to withhold.  Dropping them also removes the
RAW-mirror precondition, so an episode is now deliverable as soon as it is
post-processed, whether or not its RAW has reached GCS.

An episode is *deliverable* when:

  1. its ``review_status`` is not ``FAIL`` (FAILed data is staged for
     inspection only and is never delivered), AND
  2. it has a telemetry ``.mcap`` and its L1 videos on local disk, AND
  3. it has not been delivered to Luma yet -- no ``customer_statuses`` row with
     a ``customer_upload_time`` (idempotent re-runs), AND
  4. its supplier has a :class:`RigProfile`, and -- on a rig that publishes the
     leader gripper raw -- that episode's gripper calibration is on file.  The
     mcap transform normalises and inverts that signal, and a rig whose unit we
     cannot state would be delivered as noise that looks like data.

Delivery is **capped by the customer's requested hours**, exactly as the Scale
flow is: the quota helpers in ``submit_svo2_to_scale`` are customer-agnostic
(``task_quota`` takes a ``customer_id``; ``apply_task_quota`` / ``quota_rows``
are duck-typed over the candidate), so they are reused here rather than
duplicated.

A delivered episode is recorded ``PENDING``, not ``PASS``: Luma returns no
per-episode verdict, so the row means "handed over, verdict outstanding".
``PENDING`` counts toward delivered hours (see ``QUOTA_COUNTED_STATUSES``), so
the quota is spent on delivery rather than on a review that may never come.

Usage:
    python submit_to_luma.py --dry-run
    python submit_to_luma.py --yes
"""

from __future__ import annotations

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Optional

# This script lives in upload/; put the project root on sys.path so the
# ``staging`` package resolves even when it isn't installed.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from staging import Config, CustomerTaskStatus, LUMA_CUSTOMER_ID, StagingStore

# The quota machinery is shared with the Scale flow: `task_quota` is already
# parameterised by customer_id, and the other two only touch attributes our
# Candidate also has (staging_id / task_name / robot_type / length_s).
from submit_svo2_to_scale import (  # noqa: E402
    apply_task_quota,
    quota_rows,
    task_quota,
)
from luma_mcap_transform import (  # noqa: E402
    LEADER_TOPICS,
    MP4_NORMALISED_LIMITS,
    SVO2_NORMALISED_LIMITS,
    transform_mcap,
)
from luma_video_crop import crop_all  # noqa: E402
import gcloud_run  # noqa: E402  (upload/)

BUCKET = "gs://prismax-raw-luma"

# The products every delivery must carry, all from local disk; the
# camera-original .svo2 files are deliberately not among them (see the module
# docstring -- they are full stereo).
LOCAL_KINDS = ("mcap", "video_l1")

# The robot description, delivered alongside the products when the upload
# carried one.  The MP4 rig's "Biology Lab" uploads ship a ``.urdf`` next to the
# cameras and the mcap (staging 27437 onward), and ingest registers it as RAW
# like everything else in the upload folder -- it is not a post-processed
# product, so it has no kind of its own to select on and is matched by suffix.
#
# It is **optional, and never a precondition**: the SVO2 rig sends no URDF at
# all, and blocking on one would strand thousands of episodes.  An episode whose
# URDF is missing from disk is delivered without it rather than held back -- the
# mcap and the videos are the delivery, and holding those hostage to an
# accessory file serves nobody.
URDF_SUFFIX = ".urdf"
URDF_KIND = "raw"

# Episode formats held back from delivery, and why.
#
# Empty today.  ``mp4`` sat here from 2026-08-25 while the MP4 rig's identifier
# was untangled: it records the robot id as ``task_id``, and omits the task
# letter on everything up to staging_id 26706 (``YAM-BIO-016``).  Field ops
# confirmed the letter names the task and that the unlettered episodes are all
# task B, so ``luma_mcap_transform.canonical_serial`` fills it in and the format
# is deliverable again.
#
# Add a format here to stop delivering it without touching anything else: the
# format is excluded from candidate selection, so paused episodes simply stay
# undelivered rather than being recorded as anything.
PAUSED_FORMATS: tuple[str, ...] = ()


# The object name every episode's telemetry lands under, whatever the rig
# called it locally.  The SVO2 pipeline writes ``telemetry.webui.mcap`` as its
# product; the MP4 upload registers the rig's raw mcap in place, so its
# basename is whatever the rig numbered it (``0.mcap``, ``64.mcap``,
# ``110.mcap``) -- arbitrary, and different for every episode.  Luma sees one
# dataset, so it gets one name.
DELIVERED_MCAP_NAME = "telemetry.webui.mcap"

# The MP4 rig's single-view videos, named onto the SVO2 spelling.  Same three
# physical cameras, same mapping as ``luma_mcap_transform.CAMERA_TOPIC_RENAMES``
# applies to the topics -- kept consistent with it by hand, and pinned by a test.
DELIVERED_VIDEO_NAMES = {
    "cam_left.mp4": "cam_left_wrist.mp4",
    "cam_right.mp4": "cam_right_wrist.mp4",
}


def delivered_basename(kind: str, basename: str) -> str:
    """The object name ``basename`` must land under in the customer's bucket.

    Delivery is name-stable by design -- an object that changes name looks to
    the customer like a new file and leaves the old one orphaned -- so this is
    the single place that decides it, used both when building a candidate's
    ``dest`` and when staging the bytes to upload.
    """
    if kind == "mcap":
        return DELIVERED_MCAP_NAME
    if kind == "video_l1":
        return DELIVERED_VIDEO_NAMES.get(basename, basename)
    # A URDF keeps the name it was uploaded under.  The mcap and the videos are
    # renamed because their local names are arbitrary (a rig's file numbering)
    # and the same three cameras are meant either way; a URDF's name identifies
    # the robot model it describes (``dual_yam_platform_d405_d435.urdf``), so
    # flattening two rigs' descriptions onto one object name would make two
    # different robots look like one file.
    return basename

RETRIES = 3


@dataclass
class Candidate:
    """One episode ready to deliver, with every source resolved."""

    staging_id: int
    task_name: str
    robot_type: str
    supplier: str
    length_s: Optional[float]
    # Decides whether the L1 videos are side-by-side stereo and so need
    # cropping to one eye: only the ZED (svo2) rig records that way.
    episode_format: str = ""
    # {leader topic: (closed, open)} in the rig's raw units -- the rig constant
    # on a normalised rig, this episode's own calibration on a calibrated one
    # (its MCAP's ``gripper_limits`` record; a sidecar for older exports).
    # Always set on a deliverable candidate; the transform requires it.
    gripper_limits: "dict[str, tuple[float, float]] | None" = None
    # True on a calibrated rig, where the limits are a claim about *this*
    # episode and so are worth checking against it.  Drives the transform's
    # clamp + out-of-range gate; off for the normalised rigs, whose ULP-level
    # overshoot has shipped unclamped for thousands of episodes.
    calibrated: bool = False
    # True on a rig whose /task_info is rebuilt with the subtask prose as
    # ``serial_number`` rather than renamed field by field.
    serial_from_subtasks: bool = False
    # {"kind", "basename", "dest", and exactly one of "path" / "src_url"}
    files: list[dict] = field(default_factory=list)

    @property
    def local_paths(self) -> list[str]:
        return [f["path"] for f in self.files if f.get("path")]

    @property
    def remote_urls(self) -> list[str]:
        return [f["src_url"] for f in self.files if f.get("src_url")]


@dataclass(frozen=True)
class RigProfile:
    """How one supplier's telemetry has to be treated to be deliverable.

    ``gripper`` says what unit the **leader gripper** is published in, which is
    not something the data reveals and not something a rig can be asked at
    delivery time:

    * ``"normalised"`` -- already ``[0, 1]``, so Luma's ``1 - x`` is the whole
      transform.  This is the ``yun`` rig, and was the only case until 2026-09.
    * ``"calibrated"`` -- a raw encoder value whose zero point and span move
      per episode, so it can only be delivered against that episode's own
      ``(closed, open)`` limits.  This is the ``verlet`` rig: over its 76
      "Biology Lab" episodes the leader gripper ran -6.31 to 6.35, and ``1 - x``
      on one of them came out negative on 70.6% of its messages.
    """

    gripper: str
    # ``(closed, open)`` in the rig's raw units, for a "normalised" rig whose
    # polarity is a constant.  None on a "calibrated" rig, where the pair is a
    # property of the episode (see :func:`gripper_limits`).
    limits: "tuple[float, float] | None" = None
    # How this rig's ``/task_info`` reaches the delivered three keys.
    # "rename" -- it already uses the delivered spellings, or the MP4 rig's;
    # "subtasks" -- it shares no spellings and carries the subtask as prose, so
    # the payload is rebuilt with that prose as ``serial_number`` (verlet).
    task_info: str = "rename"


# Keyed by ``(supplier, episode_format)`` -- the rig, not the supplier.
#
# Supplier alone was the original key and it was wrong: ``yun`` operates two
# rigs whose already-normalised leader grippers are normalised to **opposite
# ends**, and one profile for both delivered the mp4 rig inverted for 857
# episodes.  Nothing in the numbers distinguishes them -- both are smooth
# signals spanning [0, 1] -- so the polarity was only recoverable by watching
# the jaws in the wrist video (staging 27982/27975 vs 27968/27965, 2026-09-03).
#
# A rig that is not here is **not deliverable**, deliberately, and that is the
# behaviour to keep: the gripper is the one delivered signal whose correctness
# nothing downstream can see, so an unknown rig must stop the delivery rather
# than borrow whichever convention happens to be the default.
RIG_PROFILES: dict[tuple, RigProfile] = {
    ("yun", "svo2"): RigProfile(gripper="normalised",
                                limits=SVO2_NORMALISED_LIMITS),
    ("yun", "mp4"): RigProfile(gripper="normalised",
                               limits=MP4_NORMALISED_LIMITS),
    ("verlet", "mp4"): RigProfile(gripper="calibrated",
                                  task_info="subtasks"),
}


def profile_for(supplier: str, episode_format: str) -> "RigProfile | None":
    """The delivery profile for one rig, or None if it has none."""
    return RIG_PROFILES.get(((supplier or "").strip().lower(),
                             (episode_format or "").strip().lower()))


def limits_for(store: StagingStore, staging_id: int, profile: RigProfile
               ) -> "dict[str, tuple[float, float]] | None":
    """``{leader topic: (closed, open)}`` for one episode, or None.

    None means "cannot be stated for this episode", which holds it back.  A
    normalised rig spreads its constant across the leader topics; a calibrated
    one reads the episode's own calibration (:func:`gripper_limits`).
    """
    if profile.gripper == "calibrated":
        return gripper_limits(store, staging_id)
    if profile.limits is None:
        return None
    return {t: profile.limits for t in LEADER_TOPICS}


# Only the ZED rig records side-by-side stereo.  The MP4 rigs and the ego (360)
# uploads are single-view, and Luma's queue holds thousands of both -- halving
# one of those would deliver half a picture, so the eye crop is gated on this
# rather than on anything measured off the pixels.  A mono 1920-wide frame is
# indistinguishable from a stereo one by dimensions alone, and encoders round
# odd widths to even, so there is no geometric test that could stand in here.
STEREO_FORMATS = ("svo2",)


def is_stereo(c: "Candidate") -> bool:
    """True when this episode's Level-1 videos are side-by-side stereo."""
    return (c.episode_format or "").lower() in STEREO_FORMATS


# The sidecar carrying one episode's gripper calibration, matched by suffix.
#
# Two kinds carry it, and both are read.  ``metadata`` is where the verlet bio
# sidecars live (written by ``migration/register_verlet_gripper_sidecars_
# 2026_09_03.py`` from the supplier's aggregate ``dataset_info.json``), and it
# is the right home for a delivery *precondition*: ``kind='raw'`` is reclaimable
# -- ``StagingStore.delete_raw_files`` takes every RAW file of an eligible
# episode off local disk -- and an episode whose calibration was reclaimed would
# silently stop being deliverable.  ``raw`` is still accepted because a sidecar
# that genuinely arrives *inside* an upload is registered there like the URDF,
# and such an upload should not need a migration to be deliverable.
GRIPPER_LIMITS_SUFFIX = "_gripper_limits.json"
GRIPPER_LIMITS_KINDS = ("metadata", "raw")

# Which leader topic each arm's limits describe.  The supplier keys calibration
# by arm and the transform keys it by topic; this is that join, and it is the
# fallback for a document that does not name the topic itself.
ARM_LEADER_TOPIC = {
    "left": "/robot/arm_left_leader/joint_states",
    "right": "/robot/arm_right_leader/joint_states",
}


def _limits_pair(entry: dict) -> "tuple[float, float] | None":
    """``(closed, open)`` from one arm's entry, or None if unusable.

    A degenerate span is rejected rather than passed on: the delivery divides
    by ``open - closed``, so zero span is the corruption the fail-closed
    default exists to prevent, not a value to forward and discover later.
    """
    closed, opened = entry.get("closed_rad"), entry.get("open_rad")
    if not isinstance(closed, (int, float)) or isinstance(closed, bool):
        return None
    if not isinstance(opened, (int, float)) or isinstance(opened, bool):
        return None
    if abs(float(opened) - float(closed)) < 1e-6:
        return None
    return (float(closed), float(opened))


def _arms_of(doc: dict) -> dict:
    """The per-arm calibration entries, from either document shape.

    Our sidecar nests them under ``gripper_calibration.arms`` and names each
    arm's ``leader_topic``; the supplier's own per-episode record (as published
    inside ``dataset_info.json``) puts the same numbers under ``gripper_limits``
    keyed by arm, with no topic.  Both are read, so a sidecar the supplier
    eventually ships unchanged works without a second parser.
    """
    arms = ((doc.get("gripper_calibration") or {}).get("arms")
            if isinstance(doc.get("gripper_calibration"), dict) else None)
    if isinstance(arms, dict) and arms:
        return arms
    limits = doc.get("gripper_limits")
    return limits if isinstance(limits, dict) else {}


def _sidecar_path(store: StagingStore, staging_id: int) -> "str | None":
    """The registered sidecar for this episode, preferring ``metadata``."""
    rows = store.db.query_all(
        "SELECT kind, path, original_name FROM files WHERE staging_id = ?",
        (staging_id,))
    by_kind: dict = {}
    for r in rows:
        kind, path = str(r["kind"]), str(r["path"])
        name = str(r["original_name"] or os.path.basename(path))
        if kind in GRIPPER_LIMITS_KINDS and name.lower().endswith(
                GRIPPER_LIMITS_SUFFIX):
            by_kind.setdefault(kind, path)
    for kind in GRIPPER_LIMITS_KINDS:
        if kind in by_kind:
            return by_kind[kind]
    return None


# Since 2026-09-10 every verlet export carries its calibration *inside* the
# MCAP, as a ``gripper_limits`` metadata record: string values
# ``left_closed_rad`` / ``left_open_rad`` / ``right_closed_rad`` /
# ``right_open_rad`` in ``motor_radians``.  That record is the source of truth.
# The sidecar is only read for the exports that predate it (all 76 of upload
# 396 and 294 of 400), whose sidecars were built from the supplier's retired
# per-prefix ``dataset_info.json``.
MCAP_CALIBRATION_RECORD = "gripper_limits"
MCAP_CALIBRATION_UNITS = "motor_radians"


def _local_raw_mcaps(store: StagingStore, staging_id: int) -> list[str]:
    """Our own copies of the episode's supplier MCAP that are still on disk.

    RAW specifically, never the bucket's copy: a re-export can move the
    gripper's raw zero point, so limits are only valid against the bytes they
    shipped with (staging 32588: bucket left (0.046, -5.276), ours
    (6.327, 0.982)).  On the verlet rig the ``mcap`` product *is* this file.
    A reclaimed row keeps its path with a NULL size.
    """
    rows = store.db.query_all(
        "SELECT path, size_bytes FROM files WHERE staging_id = ? "
        "AND kind = 'raw' AND lower(path) LIKE ? ORDER BY id",
        (staging_id, "%.mcap"))
    return [str(r["path"]) for r in rows
            if r["size_bytes"] is not None and os.path.exists(str(r["path"]))]


def mcap_calibration_record(path: str) -> "dict | None":
    """The ``gripper_limits`` metadata record of an MCAP, or None."""
    from mcap.reader import make_reader

    with open(path, "rb") as fh:
        for rec in make_reader(fh).iter_metadata():
            if rec.name == MCAP_CALIBRATION_RECORD:
                return dict(rec.metadata)
    return None


def _record_limits(record: dict) -> "dict[str, tuple[float, float]] | None":
    """Per-topic ``(closed, open)`` from an MCAP record, or None.

    Stricter than the sidecar reader on purpose: both arms or nothing, finite
    numbers only, and the unit must be the raw one the transform assumes.
    """
    if str(record.get("units") or "") != MCAP_CALIBRATION_UNITS:
        return None
    out: dict = {}
    for arm, topic in ARM_LEADER_TOPIC.items():
        try:
            closed = float(record[f"{arm}_closed_rad"])
            opened = float(record[f"{arm}_open_rad"])
        except (KeyError, TypeError, ValueError):
            return None
        if not (math.isfinite(closed) and math.isfinite(opened)):
            return None
        pair = _limits_pair({"closed_rad": closed, "open_rad": opened})
        if pair is None:
            return None
        out[topic] = pair
    return out


def gripper_limits(store: StagingStore, staging_id: int
                   ) -> "dict[str, tuple[float, float]] | None":
    """This episode's ``(closed, open)`` leader-gripper values, per topic.

    Read from the ``gripper_limits`` record in our local RAW MCAP whenever that
    file carries one.  A record is final: one that fails validation holds the
    episode back rather than falling through to a sidecar, which could only
    describe older bytes.  Only an MCAP without the record -- or no longer on
    disk -- falls back to the sidecar (:func:`_sidecar_limits`).

    ``None`` means no usable calibration, which holds the episode back (see
    :func:`find_candidates`) rather than delivering it uncalibrated: the one
    outcome worse than not delivering an episode is delivering it with a
    gripper signal that is wrong in a way nothing downstream can see.
    """
    for path in _local_raw_mcaps(store, staging_id):
        try:
            record = mcap_calibration_record(path)
        except Exception:  # noqa: BLE001 - an unreadable MCAP vouches for nothing
            return None
        if record is not None:
            return _record_limits(record)
    return _sidecar_limits(store, staging_id)


def _sidecar_limits(store: StagingStore, staging_id: int
                    ) -> "dict[str, tuple[float, float]] | None":
    """Per-topic limits from the registered sidecar, for record-less exports.

    A missing file, unreadable JSON, an arm with no numbers, a degenerate span:
    each returns ``None`` or drops that arm.  A partial document is *not*
    completed from defaults -- :func:`find_candidates` requires every topic in
    :data:`LEADER_TOPICS`, so one arm parsing still means "held back".
    """
    path = _sidecar_path(store, staging_id)
    if not path:
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            doc = json.load(fh)
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict):
        return None

    out: dict = {}
    for arm, entry in _arms_of(doc).items():
        if not isinstance(entry, dict):
            continue
        topic = entry.get("leader_topic") or ARM_LEADER_TOPIC.get(str(arm))
        pair = _limits_pair(entry)
        if not topic or pair is None:
            continue
        out[str(topic)] = pair
    return out or None


def is_urdf(row) -> bool:
    """True for the robot-description file in an upload's RAW rows."""
    return (str(row["kind"]) == URDF_KIND
            and str(row["path"]).lower().endswith(URDF_SUFFIX))


# ── Candidate discovery ──────────────────────────────────────────────────────


def find_candidates(store: StagingStore, *,
                    supplier: Optional[str] = None,
                    task_name: Optional[str] = None,
                    robot_type: Optional[str] = None,
                    ) -> tuple[list[Candidate], list[dict]]:
    """Return ``(deliverable, incomplete)``, ascending by staging_id.

    ``incomplete`` lists episodes that match the eligibility filter but are
    missing something -- ``{"staging_id", "reason"}`` -- so the tab can explain
    a short queue instead of silently dropping them.

    **The scope belongs here, not in the caller.**  Eligibility costs a file
    lookup and an ``os.path.exists`` per product, so narrowing afterwards means
    paying for the whole corpus to answer a question about one supplier's task:
    on the production corpus an unscoped call reads 24,116 episodes and stats
    109,537 files (~1.8 s warm, far worse once a transcode has evicted the
    dentry cache), where the ``verlet``/``Biology Lab`` slice the daily rule
    actually asks about is a few hundred.  ``task_name`` is an exact match on
    the master task name, the same test ``process_jobs._filter_ids_by_task``
    applies, so pushing it down changes the cost and not the answer.

    An episode whose products were **deliberately reclaimed** is not reported
    there.  A reclaimed row keeps its path but carries a NULL ``size_bytes``
    (the shape ``StagingStore.delete_raw_files`` and the L1 cleanup leave
    behind, meaning "these bytes are on no disk"), which is what separates it
    from a product that went missing by accident.  Those episodes are out of
    scope rather than anomalous: listing thousands of them as "product missing
    on disk" buries the handful of genuine breakages the list exists to
    surface.
    """
    # An empty PAUSED_FORMATS must not emit ``NOT IN ()`` -- that is a syntax
    # error, not an empty set, so the clause is omitted entirely instead.
    pause_sql = ""
    if PAUSED_FORMATS:
        ph_fmt = ", ".join("?" for _ in PAUSED_FORMATS)
        pause_sql = f"  AND e.episode_format NOT IN ({ph_fmt}) "
    scope_sql = ""
    scope_args: list[str] = []
    for column, value in (("supplier", supplier), ("task_name", task_name),
                          ("robot_type", robot_type)):
        value = (value or "").strip()
        if value:
            scope_sql += f"  AND e.{column} = ? "
            scope_args.append(value)
    rows = store.db.query_all(
        "SELECT e.staging_id, e.task_name, e.robot_type, e.supplier, "
        "       e.length_seconds, e.episode_format "
        "FROM episodes e "
        "LEFT JOIN customer_statuses cs "
        "  ON cs.staging_id = e.staging_id AND cs.customer_id = ? "
        "WHERE e.review_status != 'FAIL' "
        "  AND (cs.customer_upload_time IS NULL) "
        + pause_sql + scope_sql +
        "ORDER BY e.staging_id",
        tuple([LUMA_CUSTOMER_ID, *PAUSED_FORMATS, *scope_args]),
    )
    if not rows:
        return [], []
    ids = [int(r["staging_id"]) for r in rows]
    ph = ",".join("?" for _ in ids)
    files: dict[int, list] = {}
    for f in store.db.query_all(
        "SELECT staging_id, kind, path, cloud_url, size_bytes FROM files "
        f"WHERE staging_id IN ({ph}) "
        "  AND (kind IN ('mcap', 'video_l1') "
        "       OR (kind = 'raw' AND lower(path) LIKE '%.urdf')) "
        "ORDER BY staging_id, kind, id",
        tuple(ids),
    ):
        files.setdefault(int(f["staging_id"]), []).append(f)

    out: list[Candidate] = []
    incomplete: list[dict] = []
    for r in rows:
        sid = int(r["staging_id"])
        mine = files.get(sid) or []
        local = [f for f in mine if f["kind"] in LOCAL_KINDS]
        # Reclaimed on purpose (row kept, size cleared, file gone) -> out of
        # scope, and deliberately not reported as incomplete.
        if any(f["size_bytes"] is None and not os.path.exists(f["path"])
               for f in local):
            continue
        missing_local = [f["path"] for f in local if not os.path.exists(f["path"])]
        if not local or not any(f["kind"] == "mcap" for f in local):
            incomplete.append({"staging_id": sid, "reason": "not post-processed"})
            continue
        if missing_local:
            incomplete.append({"staging_id": sid, "reason": "product missing on disk"})
            continue
        if not any(f["kind"] == "video_l1" for f in local):
            incomplete.append({"staging_id": sid, "reason": "no level-1 videos"})
            continue
        # What the gripper has to be transformed into is a property of the rig,
        # not of the episode, and getting it wrong is invisible downstream --
        # so an episode whose rig we cannot state that for is held back rather
        # than delivered on a default.
        supplier = str(r["supplier"] or "")
        fmt = str(r["episode_format"] or "")
        profile = profile_for(supplier, fmt)
        if profile is None:
            incomplete.append({"staging_id": sid,
                               "reason": f"no delivery profile for rig "
                                         f"{supplier or '(none)'}/{fmt or '(none)'}"})
            continue
        limits = limits_for(store, sid, profile)
        if not limits or any(t not in limits for t in LEADER_TOPICS):
            incomplete.append({"staging_id": sid,
                               "reason": "gripper calibration missing"})
            continue
        cand = Candidate(
            staging_id=sid,
            task_name=str(r["task_name"] or ""),
            robot_type=str(r["robot_type"] or ""),
            supplier=str(r["supplier"] or ""),
            length_s=(None if r["length_seconds"] is None
                      else float(r["length_seconds"])),
            episode_format=str(r["episode_format"] or ""),
            gripper_limits=limits,
            calibrated=(profile.gripper == "calibrated"),
            serial_from_subtasks=(profile.task_info == "subtasks"),
        )
        # The URDF rides along when the upload carried one and it is still on
        # disk.  Deliberately resolved after the completeness checks above and
        # never fed into them: it is an extra, not a product (see URDF_SUFFIX).
        urdfs = [f for f in mine if is_urdf(f) and os.path.exists(f["path"])]
        for f in local + urdfs:
            base = delivered_basename(f["kind"], os.path.basename(f["path"]))
            cand.files.append({"kind": f["kind"], "path": f["path"],
                               "basename": base,
                               "dest": f"{BUCKET}/{sid}/{base}"})
        out.append(cand)
    return out, incomplete


def resolve_batch_id(store: StagingStore, explicit: Optional[int] = None) -> int:
    """Batch number to stamp on this run: one past Luma's highest so far."""
    if explicit is not None:
        return int(explicit)
    row = store.db.query_one(
        "SELECT MAX(customer_upload_batch_id) FROM customer_statuses "
        "WHERE customer_id = ?", (LUMA_CUSTOMER_ID,),
    )
    return int((row[0] or 0)) + 1


# ── Delivery ─────────────────────────────────────────────────────────────────


def _cp(sources: list[str], dest_dir: str, *, log) -> None:
    """One ``gcloud storage cp`` of ``sources`` into ``dest_dir``, with retries."""
    last = ""
    for attempt in range(1, RETRIES + 1):
        rc, _out, err = gcloud_run.run(
            ["gcloud", "storage", "cp", *sources, dest_dir])
        if rc == 0:
            return
        last = gcloud_run.error_text(err)
        log(f"  attempt {attempt}/{RETRIES} failed: {last}")
    raise RuntimeError(f"gcloud cp failed: {last}")


def _stage_delivered_names(local: list[str], c: Candidate,
                           tmpdir: Optional[str], *, log) -> list[str]:
    """Return ``local`` with every path renamed to its delivered basename.

    A path already carrying its delivered name is returned untouched.  Anything
    else is symlinked into ``tmpdir`` under the delivered name -- the bytes are
    not copied, and a filesystem that refuses the symlink falls back to a real
    copy rather than uploading under the wrong name.
    """
    by_path = {f["path"]: f for f in c.files if f.get("path")}
    out: list[str] = []
    for p in local:
        base = os.path.basename(p)
        # A transformed file is already in tmpdir under its delivered name; for
        # anything else the kind comes from the candidate's own file list.
        kind = (by_path.get(p) or {}).get("kind", "")
        want = delivered_basename(kind, base) if kind else base
        if want == base or tmpdir is None:
            out.append(p)
            continue
        staged = os.path.join(tmpdir, want)
        try:
            os.symlink(os.path.abspath(p), staged)
        except OSError:
            shutil.copy2(p, staged)
        log(f"  delivering {base} as {want}")
        out.append(staged)
    return out


def deliver_episode(store: StagingStore, c: Candidate, *, batch_id: int,
                    log=print) -> dict:
    """Copy one episode's files to Luma's bucket and record the delivery.

    Two transforms happen in a temp dir before anything is uploaded, neither of
    which touches our stored copies:

    * the telemetry mcap is rewritten with the leader gripper normalised
      against this rig's ``(closed, open)`` into Luma's convention -- closed
      0.0, open 1.0 -- the MP4 rig's camera topics renamed onto the names the
      SVO2 rig already delivers, and ``/task_info``'s ``task_description`` set
      to the task label -- see :mod:`luma_mcap_transform`;
    * each Level-1 video is cropped to the single delivered eye, see
      :mod:`luma_video_crop` -- our L1 is side-by-side stereo and Luma is only
      to receive the eye their previews come from.

    Objects land under :func:`delivered_basename`, which is the same name the
    candidate's ``dest`` advertises -- ``telemetry.webui.mcap`` and
    ``cam_high`` / ``cam_left_wrist`` / ``cam_right_wrist``, whatever the rig
    called them locally -- so both upload formats present one layout.

    An episode that was uploaded with a ``.urdf`` gets it too, copied through
    untransformed and under its own name; the SVO2 rig ships none, so its
    absence is normal and never a failure.

    The ``customer_statuses`` row is written only after every file has landed,
    so an interrupted delivery is retried whole on the next run rather than
    being recorded as done.  A crop failure therefore fails the episode before
    any upload, rather than delivering a half-cropped set.
    """
    dest_dir = f"{BUCKET}/{c.staging_id}/"
    local, remote = c.local_paths, c.remote_urls
    tmpdir = None
    try:
        mcaps = [f for f in c.files if f["kind"] == "mcap" and f.get("path")]
        videos = [f for f in c.files
                  if f["kind"] == "video_l1" and f.get("path")]
        if mcaps or videos:
            tmpdir = tempfile.mkdtemp(prefix=f"luma.{c.staging_id}.")
        for f in mcaps:
            out = os.path.join(tmpdir, delivered_basename("mcap",
                                                          os.path.basename(f["path"])))
            res = transform_mcap(f["path"], out, task_description=c.task_name,
                                 gripper_limits=c.gripper_limits,
                                 serial_from_subtasks=c.serial_from_subtasks,
                                 strict=c.calibrated)
            log(f"  mcap: normalised the leader gripper to closed=0, open=1 on "
                f"{res['patched']}/{res['messages']} message(s)")
            if c.calibrated:
                for topic, g in sorted(res["gripper"].items()):
                    lo, hi = g["limits"]
                    log(f"    {topic.split('/')[2]}: closed={lo:g} open={hi:g}"
                        + (f", {g['out_of_range']} sample(s) clamped into range"
                           if g["out_of_range"] else ""))
            if res["renamed"]:
                log(f"  mcap: renamed {len(res['renamed'])} camera topic(s) "
                    f"onto the delivered names")
            local = [out if p == f["path"] else p for p in local]
        if videos and is_stereo(c):
            # The three cameras crop concurrently; this is the slow step of a
            # delivery (~27 s/episode against ~3 s of upload), so it is the one
            # worth parallelising.
            cropped = crop_all([f["path"] for f in videos], tmpdir, log=log)
            local = [cropped.get(p, p) for p in local]
        elif videos:
            log(f"  videos: {c.episode_format or 'unknown'} format, single "
                f"view -- delivered as-is (no eye to drop)")
        for f in c.files:
            if f.get("path") and is_urdf(f):
                log(f"  urdf: {os.path.basename(f['path'])}")
        # Upload by *delivered* name.  ``_cp`` copies into a directory, so the
        # name an object lands under is the local basename -- which for the MP4
        # rig is the rig's arbitrary numbering.  Anything whose delivered name
        # differs is staged into the temp dir under that name first; a symlink
        # is enough (gcloud reads through it) and costs nothing, so the large
        # untransformed videos are never duplicated on disk.
        local = _stage_delivered_names(local, c, tmpdir, log=log)
        if local:
            _cp(local, dest_dir, log=log)
        if remote:
            _cp(remote, dest_dir, log=log)
    finally:
        if tmpdir:
            shutil.rmtree(tmpdir, ignore_errors=True)
    store.set_customer_status(
        c.staging_id, LUMA_CUSTOMER_ID,
        customer_task_status=CustomerTaskStatus.PENDING,
        customer_upload_batch_id=batch_id,
        customer_upload_time=time.time(),
    )
    log(f"  {len(local)} uploaded + {len(remote)} copied -> {dest_dir}")
    return {"staging_id": c.staging_id, "batch_id": batch_id,
            "uploaded": len(local), "copied": len(remote),
            "files": len(c.files)}


# ── CLI ──────────────────────────────────────────────────────────────────────


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true",
                    help="report what would be delivered, copy nothing.")
    ap.add_argument("--yes", action="store_true", help="skip the confirmation.")
    ap.add_argument("--limit", type=int, default=None,
                    help="deliver at most this many episodes.")
    ap.add_argument("--batch-id", type=int, default=None,
                    help="stamp this batch number instead of the next one.")
    ap.add_argument("--ignore-quota", action="store_true",
                    help="deliver every eligible episode, ignoring the "
                         "customer's requested hours.")
    args = ap.parse_args(argv)

    store = StagingStore(config=Config.from_env())
    candidates, incomplete = find_candidates(store)
    print(f"{len(candidates)} episode(s) eligible, {len(incomplete)} incomplete",
          flush=True)

    excluded: list[dict] = []
    if not args.ignore_quota:
        quota = task_quota(store, LUMA_CUSTOMER_ID)
        candidates, excluded = apply_task_quota(candidates, quota, log=print)
    if args.limit is not None:
        candidates = candidates[: int(args.limit)]

    hours = sum(float(c.length_s or 0.0) for c in candidates) / 3600.0
    print(f"{len(candidates)} to deliver ({hours:.2f} h), "
          f"{len(excluded)} held back by quota", flush=True)
    if args.dry_run or not candidates:
        for c in candidates[:10]:
            print(f"  {c.staging_id}: {len(c.files)} file(s)  {c.task_name}")
        return 0
    if not args.yes:
        resp = input(f"Deliver {len(candidates)} episode(s) to {BUCKET}? [y/N] ")
        if resp.strip().lower() not in ("y", "yes"):
            print("aborted")
            return 1

    batch_id = resolve_batch_id(store, args.batch_id)
    ok = failed = 0
    for i, c in enumerate(candidates, 1):
        print(f"[{i}/{len(candidates)}] episode {c.staging_id}", flush=True)
        try:
            deliver_episode(store, c, batch_id=batch_id, log=print)
            ok += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            print(f"  FAILED: {exc}", file=sys.stderr, flush=True)
    print(f"\ndelivered {ok}, failed {failed} (batch {batch_id})", flush=True)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
