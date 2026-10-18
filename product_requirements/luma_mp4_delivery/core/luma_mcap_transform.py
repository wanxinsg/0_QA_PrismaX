#!/usr/bin/env python3
"""Luma delivery transform: normalise a telemetry mcap for the customer.

Three things happen here, all at *delivery time only* -- our stored copy is
never modified, so the reviewer UI, Scale deliveries and VLA Foundry keep
seeing the original:

1. the leader gripper action is inverted (see below);
2. the MP4-rig camera topics are renamed onto the names the SVO2 rig already
   delivers (:data:`CAMERA_TOPIC_RENAMES`);
3. ``/task_info`` is normalised -- ``task_description`` set to the task
   label, and the MP4 rig's ``task_id`` promoted to ``serial_number``
   (:func:`normalise_task_info`).

Why 2 and 3: Luma has received thousands of SVO2 episodes and 258 MP4 ones, and
the two rigs spell the same three cameras differently -- ``cam_high`` /
``cam_left`` / ``cam_right`` against ``high`` / ``left_wrist`` /
``right_wrist`` -- so a consumer keying on topic name sees two incompatible
schemas for one dataset.  The MP4 rig also writes the operator-language
instruction into ``task_description`` where the SVO2 delivery carries the task
label, and records the robot identifier as ``task_id`` where the SVO2 rig calls
it ``serial_number``.  All three are normalised onto the SVO2 spelling, which is
the one the bulk of the delivered corpus already uses.

Luma consumes the leader gripper as a **normalised** signal in which **closed
is 0.0 and open is 1.0**.  This rewrites a copy of an episode's
``telemetry.webui.mcap`` at *delivery time only*: our stored copy is never
modified, so the reviewer UI, Scale deliveries and VLA Foundry keep seeing the
original values.

That convention is not a specification we were handed; it is what the ``yun``
ZED (``svo2``) rig has actually been delivering since the inversion was
introduced, across ~4.7k episodes, and on 2026-09-03 it was made the reference
every other rig is matched to.  It was established by reading pixels: in the
wrist videos of staging 27982 and 27975 the jaws are shut on an object when
that rig's raw leader reads 1.0 and wide open when it reads 0.0, so the
delivered ``1 - x`` put **closed at 0.0**.

The trap this module exists to avoid is that the raw signal's polarity and
units differ per rig, and *nothing downstream can see* a gripper delivered
backwards.  Three rigs, verified frame by frame:

* ``yun`` ``svo2`` -- already normalised, and **1.0 is closed**
  (:data:`SVO2_NORMALISED_LIMITS`).
* ``yun`` ``mp4``  -- also normalised, but the other way round: **0.0 is
  closed** (:data:`MP4_NORMALISED_LIMITS`).  Delivering ``1 - x`` here shipped
  it inverted; see staging 27968 and 27965.
* ``verlet`` -- a **raw encoder value** in motor radians whose span and zero
  point move from episode to episode (over upload 396 the leader ran -6.31 to
  6.35, one episode sitting entirely below zero), so it can only be delivered
  against that episode's own supplier-published ``(closed, open)`` pair.

So the caller states each topic's ``(closed, open)`` in the rig's own raw units
and the patch is simply ``(x - closed) / (open - closed)``: closed maps to 0.0
and open to 1.0 whatever the rig's polarity or scale.  For the svo2 rig, whose
limits are ``(1.0, 0.0)``, that is exactly the ``1 - x`` it has always shipped,
bit for bit -- the reference is preserved by construction rather than by
special-casing.

The limits are never inferred from the episode.  An operator who never fully
opens the gripper would calibrate the run to their own partial range, and the
observed per-episode spans (0.0-5.3, 1.0-6.3, -6.3--1.0) differ by more than
any real gripper does.  For a calibrated rig they come from the supplier; for a
normalised rig they are the rig constant above.

What is changed, and nothing else:

* topics ``/robot/arm_left_leader/joint_states`` and
  ``/robot/arm_right_leader/joint_states`` (:data:`LEADER_TOPICS`),
* the **unnamed 7th** entry of ``JointState.position`` -- the gripper.  The rig
  publishes six *named* joints (shoulder_pan..wrist_3) but seven positions; the
  trailing one is the gripper and carries no name (see the joint-map notes in
  ``upload/submit_svo2_to_scale.py``),
* the matching ``velocity`` entry is scaled by ``-1 / (open - closed)``,
  because that is ``d/dt`` of the position patch -- without it a consumer
  differentiating position would disagree with the velocity field.  ``effort``
  is left alone (always zero on this rig).

Why only the leader: on the rig this was written for, the leader gripper is
normalised to ``[0, 1]`` while the *follower* spans ~1.32-6.45 -- a different
unit, where ``1 - x`` goes negative.  Applying this to a follower topic would
corrupt the signal, so the topic list is explicit rather than a "leader"
substring match.  The same reasoning is why the limits are per topic: the two
arms of one rig are calibrated separately.

The rewrite is a byte patch: each message is copied verbatim except for the two
float64 slots, located by parsing the CDR header of that message (the layout is
stable in practice, but it is parsed per message rather than assumed).  Schemas,
channels, log/publish times and sequence numbers are preserved, so the output
differs from the input only in those slots.
"""

from __future__ import annotations

import json
import math
import re
import struct
from typing import Iterable, Optional

from mcap.reader import make_reader
from mcap.writer import Writer

# The two topics carrying a leader arm's JointState.  Explicit, not a substring
# match: applying the inversion to a follower topic would corrupt it.
LEADER_TOPICS = (
    "/robot/arm_left_leader/joint_states",
    "/robot/arm_right_leader/joint_states",
)

# Index of the gripper within JointState.position / .velocity.  Six named
# joints are published, and the gripper is the unnamed seventh.
GRIPPER_INDEX = 6

# ``(closed, open)`` for the rigs that publish an already-normalised leader
# gripper.  They are normalised to opposite ends, which is the whole reason
# these are two named constants rather than one default: the polarity is a
# property of the rig and is invisible in the numbers.
#
# The svo2 pair reproduces ``1 - x`` exactly -- ``(x - 1.0) / (0.0 - 1.0)`` --
# so the reference rig's delivered bytes do not move.
SVO2_NORMALISED_LIMITS = (1.0, 0.0)
MP4_NORMALISED_LIMITS = (0.0, 1.0)

# How much of an episode may fall outside its own calibration before the
# delivery is refused.  A sample or two beyond the limits is ordinary (the
# operator squeezed past the calibrated stop) and is clamped; a systematic
# excess means the limits do not belong to this episode, and shipping it would
# hand the customer a signal that is wrong in a way nothing downstream can see.
MAX_OUT_OF_RANGE = 0.01

# How far outside ``[0, 1]`` still counts as inside, in normalised units.  The
# SVO2 rig's own normalisation lands 0.3-0.7% of its messages on
# ``1.0000000000000002`` -- one ULP above 1.0, from dividing by its own span --
# and counting that as a calibration mismatch would refuse episodes that are
# perfectly good.  A millionth of the gripper's travel is far below anything
# mechanical.
OUT_OF_RANGE_TOLERANCE = 1e-6


class GripperLimitsError(ValueError):
    """Gripper limits are unusable, or do not match the episode they were used on."""

# The MP4 rig's camera topics, mapped onto the SVO2 spelling already delivered.
# The three cameras are the same three physical cameras on both rigs -- the
# overhead and the two wrist cams -- and the rest of the pipeline already treats
# them as one set: post-processing names both rigs' Level-2 videos ``high`` /
# ``left`` / ``right``, and ``db_dataset._pair_cams`` exists precisely to bridge
# this ``cam_`` prefix.  Written out in full rather than derived by stripping a
# prefix, because ``cam_left`` -> ``left_wrist`` is a naming claim about the
# rig, not a string operation.
CAMERA_TOPIC_RENAMES = {
    "/robot/camera/cam_high/image_raw/compressed/camera_info":
        "/robot/camera/high/image_raw/compressed/camera_info",
    "/robot/camera/cam_left/image_raw/compressed/camera_info":
        "/robot/camera/left_wrist/image_raw/compressed/camera_info",
    "/robot/camera/cam_right/image_raw/compressed/camera_info":
        "/robot/camera/right_wrist/image_raw/compressed/camera_info",
}

TASK_INFO_TOPIC = "/task_info"

# The letter in an identifier like ``YAM-BIO-B-018`` names the **task**, not the
# rig.  The MP4 rig omits it on everything up to staging_id 26706
# (``YAM-BIO-016``) and writes it from 26707 on (``YAM-BIO-B-018``); field ops
# confirmed the unlettered ones are all task B.  So a missing letter is filled
# in, and a letter that is already there is left alone -- this never overwrites
# what the rig recorded.
DEFAULT_TASK_LETTER = "B"

# The letter belongs to the ``YAM-BIO`` task library and to nothing else, so
# only that family is lettered.  ``BIO-NEW-<n>`` is a *collection* id from a
# different corpus that happens to share the ``<segments>-<number>`` shape;
# lettering it invented ``BIO-NEW-B-006``, an identifier that exists neither in
# the rig's recordings nor in the vendor's task sheet, and 1,920 episodes were
# delivered carrying one before it was caught (batches 36-46, all yun).
# Anything outside this family is passed through: an unrecognised prefix is a
# reason to leave the rig's own value alone, not to guess at a task letter.
LETTERED_FAMILY = "YAM-BIO-"


def canonical_serial(value: str, *, letter: str = DEFAULT_TASK_LETTER) -> str:
    """Insert the task letter into a ``YAM-BIO`` identifier that omits it.

    ``YAM-BIO-016`` -> ``YAM-BIO-B-016``; ``YAM-BIO-B-018`` unchanged;
    ``BIO-NEW-006`` unchanged -- it is not a ``YAM-BIO`` task id.

    The task letter is the **single-character segment before the number**, which
    is what distinguishes ``YAM-BIO-B-018`` (lettered) from ``YAM-BIO-016``
    (not).  Matching on segments rather than a regex over the whole string
    matters: ``[A-Z]+`` happily treats the ``B`` of ``YAM-BIO-B-018`` as part
    of the prefix and appends a second one.  Anything not shaped
    ``<segments>-<number>``, or not in :data:`LETTERED_FAMILY`, is returned
    untouched rather than guessed at.
    """
    if not (value or "").startswith(LETTERED_FAMILY):
        return value
    parts = value.split("-")
    if len(parts) < 2 or not parts[-1].isdigit():
        return value
    if len(parts[-2]) == 1 and parts[-2].isalpha():
        return value                      # already carries a task letter
    return "-".join(parts[:-1] + [letter, parts[-1]])


def _decode_std_string(data: bytes) -> "str | None":
    """The text of a ``std_msgs/String`` CDR blob, or None if it is not one."""
    if len(data) < 8:
        return None
    try:
        (n,) = struct.unpack_from("<I", data, 4)
        return data[8:8 + n].decode("utf-8").rstrip("\x00")
    except (struct.error, UnicodeDecodeError):
        return None


def _std_string_cdr(text: str) -> bytes:
    """Encode ``text`` as a little-endian ``std_msgs/String`` CDR blob."""
    raw = text.encode("utf-8") + b"\x00"
    return b"\x00\x01\x00\x00" + struct.pack("<I", len(raw)) + raw


# The collection id the verlet rig prefixes onto every description:
# ``BIO-NEW-1115 \u00b7 One-handed opening of a tube``.  Anchored, and required
# to end in ``-<digits>`` before the separator, so it cannot bite into ordinary
# prose that happens to contain a middle dot.  A prefix shape we have not seen
# simply is not stripped -- which shows up as a serial that still carries it,
# rather than as a silently truncated description.
_COLLECTION_PREFIX = re.compile(r"^[A-Z][A-Z0-9-]*-\d+\s*\u00b7\s*")


def _strip_collection_prefix(text: str) -> str:
    """``BIO-NEW-1115 \u00b7 Righting a plate`` -> ``Righting a plate``.

    ``serial_number`` names the subtask, and the collection id is not part of
    it: the same subtask is recorded under 6-14 different ``BIO-NEW`` folders,
    so leaving the prefix on would give one activity that many serials and
    defeat grouping by it.  Stripping leaves 27 stable values across the
    corpus, one per distinct instruction.
    """
    stripped = _COLLECTION_PREFIX.sub("", text, count=1).strip()
    # Never return empty: a description that is *only* a collection id is not
    # something to deliver as a blank identifier.
    return stripped or text.strip()


def subtask_serial(info: dict) -> str:
    """The subtask instruction to deliver as ``serial_number``.

    ``serial_number`` names the *subtask*.  The yun rigs express that as the
    letter in ``YAM-BIO-C-011`` -- workable because their Biology Lab corpus has
    three subtasks.  The verlet rig has 27 and growing, records no identifier at
    all (``task_id`` is the literal ``"0"`` on all 786 episodes), and carries
    the subtask as prose in ``subtasks[].description``.  So the prose *is* the
    identifier here; a code would have to be invented, and an invented code
    that collided with yun's A/B/C would be worse than none.

    ``subtasks`` is plural and every episode so far carries exactly one.  More
    than one is joined in order rather than truncated to the first -- an
    episode that really did two things should not be delivered claiming one --
    and an empty list falls back to the episode's own task name, which in this
    rig's payload is the same sentence.

    The rig's ``BIO-NEW-<n>`` collection prefix is removed either way; see
    :func:`_strip_collection_prefix` for why the id is not part of the subtask.
    """
    subs = info.get("subtasks")
    parts = []
    if isinstance(subs, list):
        for entry in subs:
            if isinstance(entry, dict):
                text = str(entry.get("description") or "").strip()
                if text:
                    parts.append(text)
    if parts:
        return "; ".join(_strip_collection_prefix(p) for p in parts)
    fallback = str(info.get("task_name") or info.get("task") or "").strip()
    return _strip_collection_prefix(fallback) if fallback else ""


def normalise_task_info(data: bytes, task: str, *,
                        serial_from_subtasks: bool = False) -> bytes:
    """Return the ``/task_info`` payload normalised for delivery.

    ``serial_from_subtasks`` selects the verlet rig's mapping: that payload
    shares no key spellings with the delivered shape -- it carries ``operator``,
    ``skill``, ``object`` and ``subtasks`` that no other rig sends, a
    ``task_name`` holding the per-episode instruction where the customer expects
    the task label, and a ``task_id`` of ``"0"``.  Renaming its fields the way
    the MP4 rig's are renamed would deliver seven keys, the instruction in
    ``task``, and a serial of ``"0"``.  So that rig is rebuilt rather than
    renamed: ``task`` and ``task_description`` become the task label and
    ``serial_number`` becomes the subtask prose (see :func:`subtask_serial`),
    leaving exactly the three keys every other delivery carries.

    Otherwise, two changes, both making the MP4 rig's payload read like the
    SVO2 one that the bulk of the delivered corpus already carries:

    * ``task_description`` is set to ``task``, the task label.  The MP4 rig
      writes the per-episode instruction in the operator's language there.
    * ``task_name`` is renamed to ``task``, and ``task_id`` to
      ``serial_number`` -- the SVO2 spellings, and the ones the customer reads.
      The identifier passes through :func:`canonical_serial`, which fills in an
      omitted task letter (``YAM-BIO-016`` -> ``YAM-BIO-B-016``) and leaves an
      identifier that already carries one alone.

    Both rigs therefore deliver exactly ``{"task", "task_description",
    "serial_number"}``.  A payload that is not a ``std_msgs/String`` carrying a
    JSON object is returned untouched: there is nothing to rewrite, and failing
    a delivery over it would be worse than passing it through.
    """
    text = _decode_std_string(data)
    if text is None:
        return data
    try:
        info = json.loads(text)
    except json.JSONDecodeError:
        return data
    if not isinstance(info, dict):
        return data
    if serial_from_subtasks:
        # Rebuilt, not renamed: start from nothing so a key this rig invents
        # later cannot leak into the delivery unnoticed.
        return _std_string_cdr(json.dumps({
            "task": task,
            "task_description": task,
            "serial_number": subtask_serial(info),
        }))
    out = dict(info)
    # One spelling for the task label: the SVO2 rig's ``task``.
    if "task" not in out and "task_name" in out:
        out["task"] = out.pop("task_name")
    out.pop("task_name", None)
    out["task_description"] = task
    # One spelling for the robot identifier: the SVO2 rig's ``serial_number``.
    serial = out.get("serial_number") or out.get("task_id") or ""
    out.pop("task_id", None)
    if serial:
        out["serial_number"] = canonical_serial(serial)
    return _std_string_cdr(json.dumps(out))


class Svo2JointStateLayoutError(ValueError):
    """A leader JointState did not match the expected CDR layout."""


def _cdr_offsets(data: bytes) -> "tuple[Optional[int], Optional[int]]":
    """Byte offsets of ``position[6]`` and ``velocity[6]`` in one CDR message.

    Returns ``(position_offset, velocity_offset)``; either is ``None`` when the
    array is too short to hold a gripper entry.  Raises
    :class:`Svo2JointStateLayoutError` if the message cannot be parsed at all.

    sensor_msgs/JointState is ``Header{ stamp{int32,uint32}, string frame_id }``
    then three ``string[]``/``float64[]`` sequences (name, position, velocity,
    effort).  CDR aligns each primitive to its own size, measured from the start
    of the encapsulation body (byte 4).
    """
    o = 4          # skip the 4-byte encapsulation header
    base = 4

    def align(n: int) -> None:
        nonlocal o
        o += (-(o - base)) % n

    try:
        align(4); o += 8                      # stamp.sec + stamp.nanosec
        align(4)
        (slen,) = struct.unpack_from("<I", data, o); o += 4 + slen   # frame_id
        align(4)
        (n_name,) = struct.unpack_from("<I", data, o); o += 4
        for _ in range(n_name):               # name[]: length-prefixed strings
            align(4)
            (slen,) = struct.unpack_from("<I", data, o); o += 4 + slen
        align(4)
        (n_pos,) = struct.unpack_from("<I", data, o); o += 4
        align(8)
        pos_base = o; o += 8 * n_pos
        align(4)
        (n_vel,) = struct.unpack_from("<I", data, o); o += 4
        align(8)
        vel_base = o
    except struct.error as exc:
        raise Svo2JointStateLayoutError(f"truncated JointState: {exc}") from exc

    pos_off = (pos_base + 8 * GRIPPER_INDEX) if n_pos > GRIPPER_INDEX else None
    vel_off = (vel_base + 8 * GRIPPER_INDEX) if n_vel > GRIPPER_INDEX else None
    if pos_off is not None and pos_off + 8 > len(data):
        raise Svo2JointStateLayoutError("position[6] runs past end of message")
    if vel_off is not None and vel_off + 8 > len(data):
        raise Svo2JointStateLayoutError("velocity[6] runs past end of message")
    return pos_off, vel_off


def patch_leader_gripper(data: bytes, limits, *,
                         clamp: bool = False) -> "tuple[bytes, bool, bool]":
    """Return ``(patched, changed, out_of_range)`` for one leader JointState.

    ``limits`` is the ``(closed, open)`` pair of raw values this rig's gripper
    moves between; the delivered position is ``(x - closed)/(open - closed)``
    and the delivered velocity is ``v / (open - closed)``, which is its
    derivative.  Closed lands on 0.0 and open on 1.0 whatever the rig's
    polarity or units.

    There is deliberately **no default**.  Every delivery bug this module
    guards against is a rig whose polarity nobody stated, and a default is how
    an unstated one silently becomes somebody else's convention: the yun mp4
    rig shipped inverted for 857 episodes against a default that described the
    svo2 rig.  The caller must say which rig this is.

    ``out_of_range`` reports a position more than
    :data:`OUT_OF_RANGE_TOLERANCE` outside ``[0, 1]``, or one that is not
    finite.  ``clamp`` additionally pulls a finite overshoot back into range;
    it is off by default because the rigs that publish an already-normalised
    gripper have been delivered unclamped for thousands of episodes and their
    ULP-level overshoot is not worth a corpus discontinuity.  A non-finite
    value is never clamped -- "no reading" must not become "fully open".
    """
    closed, open_ = float(limits[0]), float(limits[1])
    span = open_ - closed
    if span == 0.0:
        raise GripperLimitsError(f"gripper limits are degenerate: {limits}")
    pos_off, vel_off = _cdr_offsets(data)
    if pos_off is None:
        return data, False, False
    buf = bytearray(data)
    (x,) = struct.unpack_from("<d", buf, pos_off)
    y = (x - closed) / span
    if not math.isfinite(y):
        out_of_range = True
    else:
        out_of_range = (y < -OUT_OF_RANGE_TOLERANCE
                        or y > 1.0 + OUT_OF_RANGE_TOLERANCE)
        if clamp:
            y = min(1.0, max(0.0, y))
    # Canonicalise negative zero.  A fully closed gripper lands exactly on
    # zero, and which *signed* zero it lands on depends on the sign of the
    # span: the svo2 rig's ``(1.0, 0.0)`` divides by -1 and yields ``-0.0``
    # where the old ``1 - x`` yielded ``+0.0``.  The two compare equal and mean
    # the same thing, but they are different bytes, and the svo2 corpus is the
    # delivered reference -- 3887 of 47677 messages in staging 27982 alone
    # would have changed for no reason anybody could see.
    if y == 0.0:
        y = 0.0
    struct.pack_into("<d", buf, pos_off, y)
    if vel_off is not None:
        (v,) = struct.unpack_from("<d", buf, vel_off)
        struct.pack_into("<d", buf, vel_off, v / span)
    return bytes(buf), True, out_of_range


def transform_mcap(src: str, dst: str, *,
                   gripper_limits: "dict[str, tuple[float, float]]",
                   topics: Iterable[str] = LEADER_TOPICS,
                   topic_renames: "dict[str, str] | None" = None,
                   task_description: "str | None" = None,
                   serial_from_subtasks: bool = False,
                   strict: bool = False,
                   ) -> dict:
    """Copy ``src`` to ``dst``, normalised for delivery.

    Normalises the leader gripper on ``topics`` to "closed 0.0, open 1.0";
    renames channels per ``topic_renames`` (default
    :data:`CAMERA_TOPIC_RENAMES`, a no-op on an SVO2 mcap, whose cameras
    already carry the target names); and, when ``task_description`` is given,
    sets that field on ``/task_info``.

    ``gripper_limits`` maps a leader topic to that arm's ``(closed, open)`` raw
    values and is **required** -- a normalised rig passes its constant
    (:data:`SVO2_NORMALISED_LIMITS` / :data:`MP4_NORMALISED_LIMITS`), a
    calibrated rig passes the episode's own supplier-published pair.  A mapping
    that **misses** one of ``topics`` is an error rather than a fallback: on a
    raw-gripper rig that fallback is precisely the corruption this argument
    exists to prevent, so a caller cannot half-apply limits.

    ``strict`` turns on clamping and the out-of-range check, and belongs to the
    *calibrated* rigs only.  It is not "were limits given" -- limits are always
    given now.  The normalised rigs have shipped unclamped for thousands of
    episodes and land 0.3-0.7% of messages one ULP outside ``[0, 1]`` purely
    from their own division; clamping those would move bytes that nobody asked
    to move and would refuse episodes that are perfectly good.

    Raises :class:`GripperLimitsError` under ``strict`` if more than
    :data:`MAX_OUT_OF_RANGE` of an arm's messages fall outside its calibration
    -- the limits are then not this episode's, and the delivery fails before
    anything is uploaded.

    Everything else -- schemas, metadata, message order, log/publish times,
    sequence numbers -- is carried across unchanged.  Returns a summary
    ``{"messages", "patched", "topics", "renamed", "gripper"}``, where
    ``gripper`` reports the limits used per topic and how many messages were
    clamped into range.
    """
    wanted = set(topics)
    missing = sorted(wanted - set(gripper_limits or {}))
    if missing:
        raise GripperLimitsError(
            f"no gripper limits for {', '.join(missing)}")
    limits_of = {t: tuple(gripper_limits[t]) for t in wanted}
    seen = {t: 0 for t in wanted}
    out_of_range = {t: 0 for t in wanted}
    renames = (CAMERA_TOPIC_RENAMES if topic_renames is None else topic_renames)
    renamed: dict[str, str] = {}
    n_msgs = n_patched = 0
    schema_ids: dict[int, int] = {}
    channel_ids: dict[int, int] = {}

    with open(src, "rb") as fh, open(dst, "wb") as out:
        reader = make_reader(fh)
        writer = Writer(out)
        writer.start()
        summary = reader.get_summary()
        for key, value in (getattr(summary, "metadata", None) or {}).items():
            try:
                writer.add_metadata(key, value)
            except Exception:  # noqa: BLE001 - metadata is best-effort
                pass
        for schema, channel, message in reader.iter_messages():
            if schema is not None and schema.id not in schema_ids:
                schema_ids[schema.id] = writer.register_schema(
                    name=schema.name, encoding=schema.encoding, data=schema.data)
            if channel.id not in channel_ids:
                out_topic = renames.get(channel.topic, channel.topic)
                if out_topic != channel.topic:
                    renamed[channel.topic] = out_topic
                channel_ids[channel.id] = writer.register_channel(
                    topic=out_topic,
                    message_encoding=channel.message_encoding,
                    schema_id=schema_ids.get(getattr(schema, "id", -1), 0),
                    metadata=dict(channel.metadata or {}),
                )
            data = message.data
            if channel.topic in wanted:
                data, changed, was_out = patch_leader_gripper(
                    data, limits_of[channel.topic], clamp=strict)
                n_patched += int(changed)
                seen[channel.topic] += 1
                out_of_range[channel.topic] += int(was_out)
            elif task_description is not None and channel.topic == TASK_INFO_TOPIC:
                data = normalise_task_info(
                    data, task_description,
                    serial_from_subtasks=serial_from_subtasks)
            writer.add_message(
                channel_id=channel_ids[channel.id],
                log_time=message.log_time,
                publish_time=message.publish_time,
                sequence=message.sequence,
                data=data,
            )
            n_msgs += 1
        writer.finish()
    if strict:
        for topic, n in seen.items():
            if n and out_of_range[topic] / n > MAX_OUT_OF_RANGE:
                raise GripperLimitsError(
                    f"{topic}: {out_of_range[topic]}/{n} messages "
                    f"({100.0 * out_of_range[topic] / n:.1f}%) fall outside the "
                    f"calibration {limits_of[topic]} -- these limits are not "
                    f"this episode's")
    return {"messages": n_msgs, "patched": n_patched,
            "topics": sorted(wanted), "renamed": renamed,
            "gripper": {t: {"limits": list(limits_of[t]), "messages": seen[t],
                            "out_of_range": out_of_range[t], "clamped": strict}
                        for t in sorted(wanted)}}
