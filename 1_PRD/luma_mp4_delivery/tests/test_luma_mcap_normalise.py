"""The delivered mcap must read the same whichever rig recorded it.

Luma receives episodes from two rigs.  The SVO2 rig spells its cameras
``high`` / ``left_wrist`` / ``right_wrist`` and carries the robot id as
``serial_number``; the MP4 rig spells the same three cameras ``cam_high`` /
``cam_left`` / ``cam_right``, carries the robot id as ``task_id``, and writes
the per-episode instruction in the operator's language into
``task_description``.  A consumer keying on topic name saw two incompatible
schemas for one dataset.

``luma_mcap_transform`` now normalises the MP4 shape onto the SVO2 one at
delivery time, so both rigs deliver the same topics and the same
``{"task", "task_description", "serial_number"}`` payload.  The letter in an
identifier names the **task**, not the rig; the MP4 rig omits it on its earlier
episodes, and field ops confirmed those are all task B.

Run with:  .venv/bin/python tests/test_luma_mcap_normalise.py
"""

from __future__ import annotations

import json
import os
import struct
import sys
import tempfile

from mcap.reader import make_reader
from mcap.writer import Writer

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "upload")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import luma_mcap_transform as lmt  # noqa: E402


def _std_string(text: str) -> bytes:
    raw = text.encode("utf-8") + b"\x00"
    return b"\x00\x01\x00\x00" + struct.pack("<I", len(raw)) + raw


def _mcap(path: str, cam_topics, task_info: dict) -> None:
    with open(path, "wb") as fh:
        w = Writer(fh)
        w.start(profile="ros2", library="test")
        ci = w.register_schema(name="sensor_msgs/msg/CameraInfo",
                               encoding="ros2msg", data=b"")
        for t in cam_topics:
            cid = w.register_channel(topic=t, message_encoding="cdr", schema_id=ci)
            w.add_message(channel_id=cid, log_time=1, publish_time=1,
                          data=b"\x00\x01\x00\x00", sequence=0)
        ss = w.register_schema(name="std_msgs/msg/String",
                               encoding="ros2msg", data=b"string data\n")
        tc = w.register_channel(topic="/task_info", message_encoding="cdr",
                                schema_id=ss)
        w.add_message(channel_id=tc, log_time=2, publish_time=2, sequence=0,
                      data=_std_string(json.dumps(task_info, ensure_ascii=False)))
        w.finish()


def _delivered(cam_topics, task_info, task="Biology Lab"):
    """Topics and /task_info of the transformed copy."""
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "s.mcap"), os.path.join(d, "d.mcap")
        _mcap(src, cam_topics, task_info)
        res = lmt.transform_mcap(
            src, dst, task_description=task,
            gripper_limits={t: lmt.SVO2_NORMALISED_LIMITS
                            for t in lmt.LEADER_TOPICS})
        topics, info = set(), None
        with open(dst, "rb") as fh:
            for _s, c, m in make_reader(fh).iter_messages():
                topics.add(c.topic)
                if c.topic == "/task_info":
                    info = json.loads(m.data[8:].decode("utf-8").rstrip("\x00"))
        return topics, info, res


MP4_CAMS = ["/robot/camera/cam_high/image_raw/compressed/camera_info",
            "/robot/camera/cam_left/image_raw/compressed/camera_info",
            "/robot/camera/cam_right/image_raw/compressed/camera_info"]
SVO2_CAMS = ["/robot/camera/high/image_raw/compressed/camera_info",
             "/robot/camera/left_wrist/image_raw/compressed/camera_info",
             "/robot/camera/right_wrist/image_raw/compressed/camera_info"]


def test_mp4_camera_topics_become_the_delivered_names():
    topics, _info, res = _delivered(
        MP4_CAMS, {"task_name": "Biology Lab", "task_description": "用B滴管…",
                   "task_id": "YAM-BIO-B-020"})
    assert set(SVO2_CAMS) <= topics, sorted(topics)
    assert not [t for t in topics if "cam_" in t], sorted(topics)
    assert len(res["renamed"]) == 3, res["renamed"]
    print("test_mp4_camera_topics_become_the_delivered_names OK")


def test_mp4_task_id_is_delivered_as_serial_number():
    _topics, info, _res = _delivered(
        MP4_CAMS, {"task_name": "Biology Lab", "task_description": "用B滴管…",
                   "task_id": "YAM-BIO-B-020"})
    assert info["serial_number"] == "YAM-BIO-B-020", info
    # The MP4 spellings are gone -- both rigs deliver one key set.
    assert "task_id" not in info and "task_name" not in info, info
    assert sorted(info) == ["serial_number", "task", "task_description"], info
    print("test_mp4_task_id_is_delivered_as_serial_number OK")


def test_short_form_task_id_gains_the_task_letter():
    """``YAM-BIO-016`` is task B with the letter omitted."""
    _topics, info, _res = _delivered(
        MP4_CAMS, {"task_name": "Biology Lab", "task_description": "x",
                   "task_id": "YAM-BIO-016"})
    assert info["serial_number"] == "YAM-BIO-B-016", info
    print("test_short_form_task_id_gains_the_task_letter OK")


def test_operator_language_description_never_reaches_the_customer():
    _topics, info, _res = _delivered(
        MP4_CAMS, {"task_name": "Biology Lab",
                   "task_description": "将闭合的培养皿A装入编号A自封袋。",
                   "task_id": "YAM-BIO-B-020"})
    assert info["task_description"] == "Biology Lab", info
    assert json.dumps(info, ensure_ascii=False).isascii(), info
    print("test_operator_language_description_never_reaches_the_customer OK")


def test_svo2_delivery_is_unchanged():
    """The rig the corpus is mostly made of must not move."""
    topics, info, res = _delivered(
        SVO2_CAMS, {"task": "Biology Lab", "serial_number": "YAM-BIO-B-021",
                    "task_description": "Biology Lab"})
    assert set(SVO2_CAMS) <= topics, sorted(topics)
    assert res["renamed"] == {}, res["renamed"]
    assert info == {"task": "Biology Lab", "serial_number": "YAM-BIO-B-021",
                    "task_description": "Biology Lab"}, info
    print("test_svo2_delivery_is_unchanged OK")


def test_existing_serial_is_never_overwritten_by_task_id():
    _topics, info, _res = _delivered(
        SVO2_CAMS, {"serial_number": "YAM-BIO-B-021", "task_id": "SOMETHING-ELSE",
                    "task_description": "Biology Lab"})
    assert info["serial_number"] == "YAM-BIO-B-021", info


def test_a_task_letter_already_present_is_never_doubled():
    """Regression: a regex prefix match turned B-018 into B-B-018."""
    assert lmt.canonical_serial("YAM-BIO-B-018") == "YAM-BIO-B-018"
    assert lmt.canonical_serial("YAM-BIO-A-012") == "YAM-BIO-A-012"
    assert lmt.canonical_serial("YAM-BIO-016") == "YAM-BIO-B-016"
    # Nothing that is not <segments>-<number> is guessed at.
    assert lmt.canonical_serial("weird") == "weird"
    assert lmt.canonical_serial("") == ""


def test_only_the_yam_bio_family_is_lettered():
    """Regression: BIO-NEW-006 was delivered to Luma as BIO-NEW-B-006.

    ``BIO-NEW-<n>`` is a collection id from a different corpus that happens to
    share the ``<segments>-<number>`` shape, so the unguarded letter insertion
    manufactured an identifier present in neither the recordings nor the
    vendor's sheet.  1,920 episodes shipped with one.
    """
    for serial in ("BIO-NEW-006", "BIO-NEW-001", "BIO-NEW-040", "BIO-NEW-1489"):
        assert lmt.canonical_serial(serial) == serial, serial
    # The YAM-BIO family still gets the letter it is missing.
    assert lmt.canonical_serial("YAM-BIO-016") == "YAM-BIO-B-016"
    # ...and an unknown family is passed through rather than guessed at.
    assert lmt.canonical_serial("SOMETHING-ELSE-007") == "SOMETHING-ELSE-007"


def test_a_bio_new_serial_survives_the_full_delivery_transform():
    """The guard has to hold through ``normalise_task_info``, not just alone."""
    for payload in ({"task_name": "Biology Lab", "task_id": "BIO-NEW-006",
                     "task_description": "取出橙架C2中的培养管。"},
                    {"task": "Biology Lab", "serial_number": "BIO-NEW-021",
                     "task_description": "Biology Lab"}):
        _topics, info, _res = _delivered(
            MP4_CAMS if "task_name" in payload else SVO2_CAMS, payload)
        want = payload.get("task_id") or payload.get("serial_number")
        assert info["serial_number"] == want, (info, want)


def test_both_formats_deliver_an_identical_key_set():
    _t1, mp4, _r1 = _delivered(
        MP4_CAMS, {"task_name": "Biology Lab", "task_description": "用B滴管…",
                   "task_id": "YAM-BIO-016"})
    _t2, svo2, _r2 = _delivered(
        SVO2_CAMS, {"task": "Biology Lab", "serial_number": "YAM-BIO-B-021",
                    "task_description": "Biology Lab"})
    assert sorted(mp4) == sorted(svo2), (mp4, svo2)
    print("test_existing_serial_is_never_overwritten_by_task_id OK")


def _noop():
    pass


# --------------------------------------------------------------------------- #
# Gripper normalisation
# --------------------------------------------------------------------------- #
_JOINT_NAMES = ["shoulder_pan", "shoulder_lift", "elbow", "wrist_1", "wrist_2",
                "wrist_3"]


def _joint_state(position: float, velocity: float) -> bytes:
    """One JointState CDR blob: six named joints plus the unnamed gripper."""
    out = bytearray(b"\x00\x01\x00\x00")
    out += struct.pack("<II", 1_787_000_000, 0)          # header.stamp
    out += struct.pack("<I", 1) + b"\x00"                # frame_id ""
    while (len(out) - 4) % 4:
        out += b"\x00"
    out += struct.pack("<I", len(_JOINT_NAMES))
    for n in _JOINT_NAMES:
        raw = n.encode() + b"\x00"
        while (len(out) - 4) % 4:
            out += b"\x00"
        out += struct.pack("<I", len(raw)) + raw
    for values in ([0.0] * 6 + [position], [0.0] * 6 + [velocity], [0.0] * 7):
        while (len(out) - 4) % 4:
            out += b"\x00"
        out += struct.pack("<I", 7)
        while (len(out) - 4) % 8:
            out += b"\x00"
        out += struct.pack("<7d", *values)
    return bytes(out)


def _leader_mcap(path: str, samples) -> None:
    """A telemetry mcap carrying ``samples`` on both leader topics."""
    with open(path, "wb") as fh:
        w = Writer(fh)
        w.start(profile="ros2", library="test")
        sid = w.register_schema(name="sensor_msgs/msg/JointState",
                                encoding="ros2msg", data=b"")
        for topic in lmt.LEADER_TOPICS:
            cid = w.register_channel(topic=topic, message_encoding="cdr",
                                     schema_id=sid)
            for i, (pos, vel) in enumerate(samples):
                w.add_message(channel_id=cid, log_time=i + 1,
                              publish_time=i + 1, sequence=i,
                              data=_joint_state(pos, vel))
        w.finish()


def _delivered_grippers(samples, **kw):
    """The (position, velocity) pairs delivered for ``samples``, plus summary."""
    with tempfile.TemporaryDirectory() as d:
        src, dst = os.path.join(d, "s.mcap"), os.path.join(d, "d.mcap")
        _leader_mcap(src, samples)
        kw.setdefault("gripper_limits",
                      {t: lmt.SVO2_NORMALISED_LIMITS for t in lmt.LEADER_TOPICS})
        res = lmt.transform_mcap(src, dst, **kw)
        out = []
        with open(dst, "rb") as fh:
            for _s, c, m in make_reader(fh).iter_messages():
                if c.topic == lmt.LEADER_TOPICS[0]:
                    po, vo = lmt._cdr_offsets(m.data)   # noqa: SLF001
                    out.append((struct.unpack_from("<d", m.data, po)[0],
                                struct.unpack_from("<d", m.data, vo)[0]))
        return out, res


def test_the_two_normalised_rigs_are_normalised_to_opposite_ends():
    """Both publish [0, 1]; only the wrist video says which end is closed.

    The svo2 rig reads 1.0 closed, so its delivery is ``1 - x`` -- and that
    arithmetic must not move a bit, because it is the reference thousands of
    episodes were delivered on.  The yun mp4 rig reads 0.0 closed, so its
    delivery is the identity; it shipped inverted for 857 episodes precisely
    because one constant stood in for both rigs.
    """
    svo2, res = _delivered_grippers([(0.0, 0.5), (0.25, -2.0), (1.0, 0.0)])
    assert svo2 == [(1.0, -0.5), (0.75, 2.0), (0.0, -0.0)], svo2
    assert res["patched"] == 6, res

    mp4, _ = _delivered_grippers(
        [(0.0, 0.5), (0.25, -2.0), (1.0, 0.0)],
        gripper_limits={t: lmt.MP4_NORMALISED_LIMITS for t in lmt.LEADER_TOPICS})
    assert mp4 == [(0.0, 0.5), (0.25, -2.0), (1.0, 0.0)], mp4

    # The two rigs disagree on every sample that is not the midpoint -- which
    # is exactly why the delivered value cannot be read off the raw number.
    assert [p for p, _ in svo2] == [1.0 - p for p, _ in mp4], (svo2, mp4)
    print("gripper: the two normalised rigs deliver opposite ends OK")


def test_closed_is_delivered_as_zero_on_every_rig():
    """The one invariant: whatever the rig, a shut gripper leaves as 0.0.

    Pinned per rig at its own 'closed' raw value, in the rig's own units.
    """
    for label, limits, closed_raw, open_raw in (
            ("yun svo2", lmt.SVO2_NORMALISED_LIMITS, 1.0, 0.0),
            ("yun mp4", lmt.MP4_NORMALISED_LIMITS, 0.0, 1.0),
            ("verlet", (6.327, 1.087), 6.327, 1.087)):
        got, _ = _delivered_grippers(
            [(closed_raw, 0.0), (open_raw, 0.0)],
            gripper_limits={t: limits for t in lmt.LEADER_TOPICS})
        assert round(got[0][0], 9) == 0.0, (label, got)
        assert round(got[1][0], 9) == 1.0, (label, got)
        # ...and never as a negative zero, which is equal but not the same
        # bytes the svo2 corpus already carries.
        assert str(got[0][0]) == "0.0", (label, got[0][0])
    print("gripper: closed delivers as 0.0 on every rig OK")


def test_a_raw_gripper_is_normalised_against_its_own_limits():
    """closed -> 0.0, open -> 1.0, and velocity scaled by the span."""
    limits = {t: (1.0, 6.0) for t in lmt.LEADER_TOPICS}
    got, res = _delivered_grippers(
        [(1.0, 0.0), (6.0, 0.0), (3.5, 5.0)], gripper_limits=limits)
    positions = [round(p, 12) for p, _v in got]
    assert positions == [0.0, 1.0, 0.5], got
    # d/dt of (x - closed)/span is v/span: 5.0 over a span of 5 -> 1.0.
    assert round(got[2][1], 12) == 1.0, got
    assert res["gripper"][lmt.LEADER_TOPICS[0]]["limits"] == [1.0, 6.0]
    print("gripper: raw signal normalised against its limits OK")


def test_an_episode_that_does_not_fit_its_limits_is_refused():
    """Limits from a different episode must fail the delivery, not ship."""
    limits = {t: (0.0, 1.0) for t in lmt.LEADER_TOPICS}
    # A raw-unit episode (0..5.3) against normalised limits: mostly off-scale.
    samples = [(x / 10.0, 0.0) for x in range(0, 53)]
    try:
        _delivered_grippers(samples, gripper_limits=limits, strict=True)
    except lmt.GripperLimitsError as exc:
        assert "not this episode's" in str(exc), exc
    else:
        raise AssertionError("delivered an episode that does not fit its limits")
    print("gripper: mismatched limits refuse the delivery OK")


def test_the_rigs_own_ulp_overshoot_is_not_a_mismatch():
    """1.0000000000000002 is the SVO2 rig's own rounding, not a bad calibration.

    0.3-0.7% of a real episode's leader messages land one ULP above 1.0, so
    counting those as out of range would refuse episodes that deliver fine --
    and clamping them would change bytes the customer already has.
    """
    ulp = 1.0 + 2 ** -52
    got, res = _delivered_grippers([(ulp, 0.0)] * 10)
    assert got[0][0] < 0.0, got          # 1 - x, unclamped, as before
    assert res["gripper"][lmt.LEADER_TOPICS[0]]["out_of_range"] == 0, res
    # ...and against explicit limits it is inside the tolerance too.
    _got, res2 = _delivered_grippers(
        [(ulp, 0.0)] * 10, gripper_limits={t: (0.0, 1.0) for t in lmt.LEADER_TOPICS})
    assert res2["gripper"][lmt.LEADER_TOPICS[0]]["out_of_range"] == 0, res2
    print("gripper: ULP overshoot is not a calibration mismatch OK")


def test_partial_limits_are_refused_rather_than_defaulted():
    """Half a calibration is the corruption the argument exists to prevent."""
    only_left = {lmt.LEADER_TOPICS[0]: (1.0, 6.0)}
    try:
        _delivered_grippers([(1.0, 0.0)], gripper_limits=only_left)
    except lmt.GripperLimitsError as exc:
        assert lmt.LEADER_TOPICS[1] in str(exc), exc
    else:
        raise AssertionError("a missing arm fell back to the default limits")
    print("gripper: partial limits refused OK")


def test_unparseable_task_info_passes_through():
    """A payload we cannot read must not fail the delivery."""
    assert lmt.normalise_task_info(b"\x00\x01", "T") == b"\x00\x01"
    blob = _std_string("not json")
    assert lmt.normalise_task_info(blob, "T") == blob
    print("test_unparseable_task_info_passes_through OK")


def test_the_verlet_payload_is_rebuilt_not_renamed():
    """Its subtask prose becomes ``serial_number``; nothing else survives.

    The verlet rig shares no key spellings with the delivered shape and its
    ``task_id`` is the literal ``"0"`` on every episode, so renaming field by
    field would ship seven keys, the per-episode instruction in ``task``, and a
    serial of "0".
    """
    payload = {
        "operator": "Anonymous",
        "task_name": "BIO-NEW-1115 \u00b7 One-handed opening of a tube",
        "task_description": "BIO-NEW-1115 \u00b7 One-handed opening of a tube",
        "task_id": "0",
        "skill": [], "object": [],
        "subtasks": [{"skill": "", "description":
                      "BIO-NEW-1115 \u00b7 One-handed opening of a tube"}],
    }
    out = json.loads(lmt._decode_std_string(          # noqa: SLF001
        lmt.normalise_task_info(_std_string(json.dumps(payload)), "Biology Lab",
                                serial_from_subtasks=True)))
    assert sorted(out) == ["serial_number", "task", "task_description"], out
    assert out["task"] == "Biology Lab"
    assert out["task_description"] == "Biology Lab"
    assert out["serial_number"] == "One-handed opening of a tube"
    print("task_info: the verlet payload is rebuilt to the delivered keys OK")


def test_every_rig_delivers_the_same_three_keys():
    """One key set for the customer, whatever the rig recorded."""
    yun_svo2 = {"task": "Biology Lab", "serial_number": "YAM-BIO-C-011",
                "task_description": "Biology Lab"}
    yun_mp4 = {"task_name": "Biology Lab", "task_id": "YAM-BIO-C-014",
               "task_description": "operator-language instruction"}
    verlet = {"operator": "A", "task_name": "x", "task_description": "x",
              "task_id": "0", "skill": [], "object": [],
              "subtasks": [{"skill": "", "description": "Righting a plate"}]}
    seen = []
    for payload, from_subtasks in ((yun_svo2, False), (yun_mp4, False),
                                   (verlet, True)):
        out = json.loads(lmt._decode_std_string(      # noqa: SLF001
            lmt.normalise_task_info(_std_string(json.dumps(payload)),
                                    "Biology Lab",
                                    serial_from_subtasks=from_subtasks)))
        seen.append(sorted(out))
        assert out["task_description"] == "Biology Lab", out
        assert out["serial_number"], out
    assert seen[0] == seen[1] == seen[2], seen
    print("task_info: every rig delivers the same three keys OK")


def test_multiple_subtasks_are_joined_rather_than_truncated():
    """An episode that did two things must not be delivered claiming one."""
    payload = {"task_name": "x", "subtasks": [
        {"skill": "", "description": "Righting a plate"},
        {"skill": "", "description": "Capping the flask"}]}
    out = json.loads(lmt._decode_std_string(          # noqa: SLF001
        lmt.normalise_task_info(_std_string(json.dumps(payload)), "Biology Lab",
                                serial_from_subtasks=True)))
    assert out["serial_number"] == "Righting a plate; Capping the flask", out
    # ...and an empty list falls back to the episode's own task name rather
    # than delivering a blank identifier.
    empty = {"task_name": "Righting a plate", "subtasks": []}
    out2 = json.loads(lmt._decode_std_string(         # noqa: SLF001
        lmt.normalise_task_info(_std_string(json.dumps(empty)), "Biology Lab",
                                serial_from_subtasks=True)))
    assert out2["serial_number"] == "Righting a plate", out2
    print("task_info: multiple subtasks joined, empty falls back OK")


def test_the_collection_prefix_is_stripped_from_the_serial():
    """``serial_number`` is the subtask, and the collection id is not part of it.

    The same instruction is recorded under 6-14 different ``BIO-NEW`` folders,
    so keeping the prefix would give one activity that many serials -- across
    the 786-episode corpus, stripping is what turns them into 27 stable values.
    """
    strip = lmt._strip_collection_prefix                  # noqa: SLF001
    assert strip("BIO-NEW-1115 \u00b7 Righting a plate") == "Righting a plate"
    assert strip("BIO-NEW-607 \u00b7 Capping the flask") == "Capping the flask"
    # A prefix shape we have not seen is left alone rather than guessed at --
    # visible as a serial that still carries it, not a truncated description.
    assert strip("session 7 \u00b7 Righting a plate") == "session 7 \u00b7 Righting a plate"
    # ...and ordinary prose containing the separator is never bitten into.
    assert strip("Open the box \u00b7 then cap it") == "Open the box \u00b7 then cap it"
    # A description that is only a collection id stays as it is rather than
    # becoming a blank identifier.
    assert strip("BIO-NEW-1115") == "BIO-NEW-1115"
    print("task_info: the collection prefix is stripped from the serial OK")


if __name__ == "__main__":
    test_mp4_camera_topics_become_the_delivered_names()
    test_mp4_task_id_is_delivered_as_serial_number()
    test_short_form_task_id_gains_the_task_letter()
    test_operator_language_description_never_reaches_the_customer()
    test_svo2_delivery_is_unchanged()
    test_existing_serial_is_never_overwritten_by_task_id()
    test_a_task_letter_already_present_is_never_doubled()
    test_both_formats_deliver_an_identical_key_set()
    test_unparseable_task_info_passes_through()
    test_the_two_normalised_rigs_are_normalised_to_opposite_ends()
    test_closed_is_delivered_as_zero_on_every_rig()
    test_a_raw_gripper_is_normalised_against_its_own_limits()
    test_an_episode_that_does_not_fit_its_limits_is_refused()
    test_the_rigs_own_ulp_overshoot_is_not_a_mismatch()
    test_partial_limits_are_refused_rather_than_defaulted()
    test_the_verlet_payload_is_rebuilt_not_renamed()
    test_every_rig_delivers_the_same_three_keys()
    test_multiple_subtasks_are_joined_rather_than_truncated()
    test_the_collection_prefix_is_stripped_from_the_serial()
    print("all luma mcap normalisation tests OK")
