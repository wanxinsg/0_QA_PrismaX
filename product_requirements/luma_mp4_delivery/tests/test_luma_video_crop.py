"""Tests for Luma's single-eye video delivery (upload/luma_video_crop.py).

Luma is only to receive the eye their previews are derived from, so the two
things that must hold are that the delivered file *is* that eye, and that the
other eye is genuinely gone rather than merely hidden.  The second is the whole
reason this re-encodes, so it is pinned here with an executable proof: the cheap
alternative (an HEVC conformance-window crop, stream copy) is shown to leave the
other eye recoverable.

Also covered: the format gate that keeps single-view episodes (the MP4 rigs
and ego 360, thousands of which sit in Luma's queue) from being halved, the
concurrent path, and the delivery wiring -- the .svo2 camera originals must
not be offered to Luma any more.

Needs ffmpeg/ffprobe; skipped without them.

Run with:  .venv/bin/python -m pytest tests/test_luma_video_crop.py
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _p in (_ROOT, os.path.join(_ROOT, "tests"), os.path.join(_ROOT, "upload")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import pytest  # noqa: E402

from pg_test_util import temp_db_url  # noqa: E402

from staging import Config, FileKind, StagingStore  # noqa: E402
from luma_mcap_transform import LEADER_TOPICS  # noqa: E402  (upload/)

import luma_video_crop as crop  # noqa: E402  (upload/)

_HAVE_FFMPEG = bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
needs_ffmpeg = pytest.mark.skipif(not _HAVE_FFMPEG,
                                  reason="ffmpeg/ffprobe not available")

# One eye is 960x600 on the real rig; the tests use a smaller but
# same-shaped frame so they stay fast.
EYE_W, EYE_H = 160, 120


def _stereo_clip(path: str, seconds: float = 1.0) -> str:
    """A side-by-side clip whose halves are visibly different colours.

    Left half red, right half blue, so a crop can be checked by sampling the
    output's colour rather than trusting the geometry alone -- a crop with the
    wrong offset has the right dimensions but the wrong eye.
    """
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y",
         "-f", "lavfi", "-i", f"color=c=red:s={EYE_W}x{EYE_H}:d={seconds}:r=30",
         "-f", "lavfi", "-i", f"color=c=blue:s={EYE_W}x{EYE_H}:d={seconds}:r=30",
         "-filter_complex", "[0:v][1:v]hstack=inputs=2,format=yuv420p[v]",
         "-map", "[v]", "-c:v", "libx265", "-x265-params", "log-level=none",
         "-t", str(seconds), path],
        check=True, capture_output=True)
    return path


def _dominant_channel(path: str) -> str:
    """'r' or 'b' -- which of red/blue dominates the first frame."""
    out = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", path, "-vf",
         "select=eq(n\\,0),signalstats,metadata=print:key=lavfi.signalstats.YAVG",
         "-vframes", "1", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    # Y is much higher for red (~76) than blue (~29) in BT.601 yuv420p.
    for line in out.splitlines():
        if "YAVG" in line:
            y = float(line.rsplit("=", 1)[1])
            return "r" if y > 50 else "b"
    raise AssertionError(f"no YAVG in ffmpeg output for {path}")


# --------------------------------------------------------------------------- #
# The crop itself
# --------------------------------------------------------------------------- #
@needs_ffmpeg
def test_crop_delivers_the_left_eye():
    """Geometry *and* content: the output is the left half, not the right."""
    with tempfile.TemporaryDirectory() as tmp:
        src = _stereo_clip(os.path.join(tmp, "cam_high.mp4"))
        dst = os.path.join(tmp, "out.mp4")
        info = crop.crop_one(src, dst, encoder="libx265")

        assert info["src_dims"] == (EYE_W * 2, EYE_H)
        assert info["dst_dims"] == (EYE_W, EYE_H)
        # The left half was red; a right-eye crop would come out blue.
        assert _dominant_channel(dst) == "r", "cropped the wrong eye"
        assert crop.DELIVERED_EYE == "left"
    print("crop: delivers the left eye OK")


@needs_ffmpeg
def test_crop_matches_the_l2_primary_eye():
    """The delivered eye is the one svo2_convert cuts the primary L2 from.

    These two constants live in different packages and there is no import
    between them, so nothing but this test stops one being flipped without the
    other -- which is exactly the drift that mis-delivered Luma batch 4.
    """
    sys.path.insert(0, os.path.join(_ROOT, "workers", "svo2"))
    import svo2_convert                                       # noqa: PLC0415

    assert crop.CROP_FILTER == svo2_convert._CROP_PRIMARY_EYE, (  # noqa: SLF001
        "luma_video_crop delivers a different eye than the one "
        "svo2_convert puts in the primary L2 streams")
    print("crop: delivered eye matches the L2 primary OK")


@needs_ffmpeg
def test_metadata_only_crop_would_leave_the_other_eye_recoverable():
    """Why this module re-encodes instead of rewriting the conformance window.

    The cheap path looks right -- it reports 960x600 in under a second -- but
    the other eye is still in the bitstream and one flag flip brings it back.
    If this ever stops being true, the expensive re-encode can go.
    """
    with tempfile.TemporaryDirectory() as tmp:
        src = _stereo_clip(os.path.join(tmp, "cam_high.mp4"))
        meta = os.path.join(tmp, "meta.mp4")
        undo = os.path.join(tmp, "undo.mp4")

        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", src, "-c", "copy",
             "-bsf:v", f"hevc_metadata=crop_left={EYE_W}", meta],
            check=True, capture_output=True)
        # It *looks* cropped...
        assert crop._probe_dims(meta) == (EYE_W, EYE_H)  # noqa: SLF001
        # ...but carries the whole frame's data, and it comes straight back.
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", meta, "-c", "copy",
             "-bsf:v", "hevc_metadata=crop_left=0", undo],
            check=True, capture_output=True)
        assert crop._probe_dims(undo) == (EYE_W * 2, EYE_H), (  # noqa: SLF001
            "the metadata crop became lossy -- re-check whether the "
            "re-encode is still needed")

        # A real crop cannot be undone that way.
        real = os.path.join(tmp, "real.mp4")
        crop.crop_one(src, real, encoder="libx265")
        assert crop._probe_dims(real) == (EYE_W, EYE_H)  # noqa: SLF001
    print("crop: metadata-only crop proven insufficient OK")


def test_only_stereo_formats_are_cropped():
    """The gate that protects the 2795 single-view episodes in Luma's queue.

    Luma's eligible queue is not all ZED: it holds thousands of mp4-rig and ego
    (360) episodes whose L1 is already a single view.  Cropping one of those in
    half would deliver half a picture, and nothing about the file reveals the
    difference -- a mono 1920-wide frame looks exactly like a stereo one, and
    encoders silently round odd widths to even, so a geometric check cannot
    stand in for knowing the format.
    """
    import submit_to_luma as luma

    def cand(fmt):
        return luma.Candidate(staging_id=1, task_name="t", robot_type="yam",
                              supplier="s", length_s=1.0, episode_format=fmt)

    assert luma.is_stereo(cand("svo2")) is True
    assert luma.is_stereo(cand("SVO2")) is True      # case-insensitive
    assert luma.is_stereo(cand("mp4")) is False      # the MP4 rigs
    assert luma.is_stereo(cand("r405")) is False
    assert luma.is_stereo(cand("")) is False         # unknown -> never crop
    print("delivery: eye crop gated on stereo formats OK")


@needs_ffmpeg
def test_crop_all_handles_three_cameras():
    with tempfile.TemporaryDirectory() as tmp:
        srcs = [_stereo_clip(os.path.join(tmp, f"cam_{n}.mp4"))
                for n in ("high", "left_wrist", "right_wrist")]
        outdir = os.path.join(tmp, "out")
        mapping = crop.crop_all(srcs, outdir, encoder="libx265",
                                log=lambda m: None)

        assert set(mapping) == set(srcs)
        for src, dst in mapping.items():
            # Basename preserved: Luma keys off cam_high.mp4 etc.
            assert os.path.basename(dst) == os.path.basename(src)
            assert os.path.dirname(dst) == outdir
            assert crop._probe_dims(dst) == (EYE_W, EYE_H)  # noqa: SLF001
        assert crop.crop_all([], outdir, log=lambda m: None) == {}
    print("crop: three cameras, basenames preserved OK")


# --------------------------------------------------------------------------- #
# Delivery wiring
# --------------------------------------------------------------------------- #
def test_svo2_originals_are_no_longer_offered_to_luma():
    """The .svo2s are full stereo; delivering them would defeat the crop."""
    import submit_to_luma as luma

    with tempfile.TemporaryDirectory() as tmp, temp_db_url() as url:
        store = StagingStore(config=Config(data_root=os.path.join(tmp, "data"),
                                           db_url=url))
        sid = store.create_episode(robot_type="yam", uploader_identity="a",
                                   supplier="yun", task_name="Pick", length_seconds=10.0)
        for name, kind in (("telemetry.webui.mcap", FileKind.MCAP),
                           ("cam_high.mp4", FileKind.VIDEO_L1),
                           ("cam_high.svo2", FileKind.RAW)):
            p = os.path.join(tmp, f"{sid}_{name}")
            with open(p, "wb") as f:
                f.write(b"x" * 8)
            store.add_files(sid, [p], kind)

        cands, incomplete = luma.find_candidates(store)
        assert len(cands) == 1, (cands, incomplete)
        kinds = {f["kind"] for f in cands[0].files}
        assert kinds == {"mcap", "video_l1"}, kinds
        assert not cands[0].remote_urls, "a bucket-to-bucket .svo2 copy survived"
        assert not any(p.endswith(".svo2") for p in cands[0].local_paths)
        store.close()
    print("delivery: .svo2 originals dropped from the payload OK")


def test_unmirrored_raw_no_longer_blocks_delivery():
    """Dropping the .svo2s removes the RAW-mirror precondition."""
    import submit_to_luma as luma

    with tempfile.TemporaryDirectory() as tmp, temp_db_url() as url:
        store = StagingStore(config=Config(data_root=os.path.join(tmp, "data"),
                                           db_url=url))
        sid = store.create_episode(robot_type="yam", uploader_identity="a",
                                   supplier="yun", task_name="Pick", length_seconds=10.0)
        for name, kind in (("telemetry.webui.mcap", FileKind.MCAP),
                           ("cam_high.mp4", FileKind.VIDEO_L1)):
            p = os.path.join(tmp, f"{sid}_{name}")
            with open(p, "wb") as f:
                f.write(b"x" * 8)
            store.add_files(sid, [p], kind)
        # No RAW rows at all, let alone a cloud_url: previously "no svo2 rows".
        cands, incomplete = luma.find_candidates(store)
        assert [c.staging_id for c in cands] == [sid], incomplete
        store.close()
    print("delivery: unmirrored RAW no longer blocks OK")


def test_urdf_rides_along_but_is_never_required():
    """The MP4 rig's "Biology Lab" uploads carry a robot description.

    It arrives in the upload folder, so ingest registers it as RAW like the
    cameras and the mcap -- there is no product kind to select it by, and the
    .svo2 rows sitting in the same kind are the reason the suffix, not the
    kind, is what decides.  It is delivered under its own name (it identifies
    the robot model, unlike the rig-numbered mcap) and it is an *extra*: the
    SVO2 rig ships none, so an episode without one delivers exactly as before.
    """
    import submit_to_luma as luma

    with tempfile.TemporaryDirectory() as tmp, temp_db_url() as url:
        store = StagingStore(config=Config(data_root=os.path.join(tmp, "data"),
                                           db_url=url))

        def episode(files):
            sid = store.create_episode(robot_type="yam", uploader_identity="a",
                                       supplier="yun", task_name="Biology Lab",
                                       length_seconds=10.0)
            for name, kind in files:
                p = os.path.join(tmp, f"{sid}_{name}")
                with open(p, "wb") as f:
                    f.write(b"x" * 8)
                store.add_files(sid, [p], kind)
            return sid

        base = [("telemetry.webui.mcap", FileKind.MCAP),
                ("cam_high.mp4", FileKind.VIDEO_L1)]
        with_urdf = episode(base + [("dual_yam_platform.urdf", FileKind.RAW),
                                    ("cam_high.svo2", FileKind.RAW)])
        without = episode(base)

        cands, incomplete = luma.find_candidates(store)
        by_id = {c.staging_id: c for c in cands}
        assert set(by_id) == {with_urdf, without}, (cands, incomplete)

        # The URDF is delivered, under its uploaded name, into the episode's
        # own folder -- and no other RAW row came with it.
        urdf = [f for f in by_id[with_urdf].files if f["basename"].endswith(".urdf")]
        assert len(urdf) == 1, by_id[with_urdf].files
        assert urdf[0]["kind"] == "raw"
        assert urdf[0]["dest"] == f"{luma.BUCKET}/{with_urdf}/{urdf[0]['basename']}"
        assert urdf[0]["basename"] == os.path.basename(urdf[0]["path"])
        assert not any(f["basename"].endswith(".svo2")
                       for f in by_id[with_urdf].files)

        # An episode with no URDF is untouched by any of this.
        assert {f["kind"] for f in by_id[without].files} == {"mcap", "video_l1"}
        store.close()
    print("delivery: urdf delivered when present, never required OK")


def test_a_missing_urdf_never_holds_an_episode_back():
    """A URDF that is gone from disk costs the episode its URDF, not its media.

    The mcap and the videos are the delivery; blocking one because an accessory
    file went missing would strand it for good, since nothing re-offers a
    delivered episode.
    """
    import submit_to_luma as luma

    with tempfile.TemporaryDirectory() as tmp, temp_db_url() as url:
        store = StagingStore(config=Config(data_root=os.path.join(tmp, "data"),
                                           db_url=url))
        sid = store.create_episode(robot_type="yam", uploader_identity="a",
                                   supplier="yun", task_name="Biology Lab", length_seconds=10.0)
        for name, kind in (("telemetry.webui.mcap", FileKind.MCAP),
                           ("cam_high.mp4", FileKind.VIDEO_L1),
                           ("dual_yam_platform.urdf", FileKind.RAW)):
            p = os.path.join(tmp, f"{sid}_{name}")
            with open(p, "wb") as f:
                f.write(b"x" * 8)
            added = store.add_files(sid, [p], kind)
        # The stored URDF goes missing; the mcap and the video stay.
        os.remove(added[0].path)

        cands, incomplete = luma.find_candidates(store)
        assert [c.staging_id for c in cands] == [sid], incomplete
        assert not any(p.endswith(".urdf") for p in cands[0].local_paths)
        store.close()
    print("delivery: a missing urdf does not block the media OK")


def test_a_rig_without_a_gripper_convention_is_never_delivered():
    """Discovery is rig-aware, and fails closed on a rig it cannot state.

    What unit the leader gripper is published in decides whether the delivered
    signal is a gripper or noise, and it cannot be measured off the episode.
    A supplier with no :data:`submit_to_luma.SUPPLIER_PROFILES` entry is held
    back with a reason rather than delivered on the old default -- which is how
    4586 verlet episodes came within one ``--ignore-quota`` of shipping their
    raw gripper through an inversion meant for a normalised one.
    """
    import submit_to_luma as luma

    with tempfile.TemporaryDirectory() as tmp, temp_db_url() as url:
        store = StagingStore(config=Config(data_root=os.path.join(tmp, "data"),
                                           db_url=url))

        def episode(supplier, episode_format="svo2"):
            sid = store.create_episode(robot_type="yam", uploader_identity="a",
                                       supplier=supplier, task_name="Biology Lab",
                                       length_seconds=10.0,
                                       episode_format=episode_format)
            for name, kind in (("telemetry.webui.mcap", FileKind.MCAP),
                               ("cam_high.mp4", FileKind.VIDEO_L1)):
                p = os.path.join(tmp, f"{sid}_{name}")
                with open(p, "wb") as f:
                    f.write(b"x" * 8)
                store.add_files(sid, [p], kind)
            return sid

        known = episode("yun", "svo2")            # normalised, 1.0 closed
        calibrated = episode("verlet", "mp4")     # raw gripper, no sidecar yet
        unknown = episode("zhu", "svo2")          # supplier has no profile
        # Same supplier as `known`, different rig: the profile is keyed on the
        # pair, so an unlisted *format* is as undeliverable as an unlisted
        # supplier.  Keying on supplier alone is what shipped yun mp4 inverted.
        unknown_rig = episode("yun", "r405")

        cands, incomplete = luma.find_candidates(store)
        assert [c.staging_id for c in cands] == [known], (cands, incomplete)
        # A normalised rig still carries limits -- its polarity constant.  They
        # are never absent: the transform has no default to fall back to.
        assert cands[0].gripper_limits == {
            t: luma.SVO2_NORMALISED_LIMITS for t in LEADER_TOPICS}
        assert cands[0].calibrated is False

        why = {i["staging_id"]: i["reason"] for i in incomplete}
        assert why[calibrated] == "gripper calibration missing", why
        assert "no delivery profile" in why[unknown], why
        assert "zhu" in why[unknown], why
        assert "no delivery profile" in why[unknown_rig], why
        assert "r405" in why[unknown_rig], why
        store.close()
    print("delivery: rigs without a gripper convention are held back OK")


def test_a_calibrated_rig_delivers_once_its_limits_are_on_file():
    """The gate opens exactly when the episode's calibration can be read.

    Pinned against the loader rather than the profile so that wiring the
    supplier's sidecar up is all that is left to do -- nothing else in
    discovery has to change for a calibrated rig to become deliverable.
    """
    import submit_to_luma as luma
    from luma_mcap_transform import LEADER_TOPICS

    with tempfile.TemporaryDirectory() as tmp, temp_db_url() as url:
        store = StagingStore(config=Config(data_root=os.path.join(tmp, "data"),
                                           db_url=url))
        sid = store.create_episode(robot_type="yam", uploader_identity="a",
                                   supplier="verlet", task_name="Biology Lab",
                                   length_seconds=10.0, episode_format="mp4")
        for name, kind in (("telemetry.webui.mcap", FileKind.MCAP),
                           ("cam_high.mp4", FileKind.VIDEO_L1)):
            p = os.path.join(tmp, f"{sid}_{name}")
            with open(p, "wb") as f:
                f.write(b"x" * 8)
            store.add_files(sid, [p], kind)

        assert not luma.find_candidates(store)[0], "delivered without limits"

        limits = {t: (1.0, 6.0) for t in LEADER_TOPICS}
        original = luma.gripper_limits
        luma.gripper_limits = lambda store, staging_id: limits
        try:
            cands, _ = luma.find_candidates(store)
        finally:
            luma.gripper_limits = original
        assert [c.staging_id for c in cands] == [sid], cands
        assert cands[0].gripper_limits == limits
        # ...and a calibration missing an arm is no calibration at all.
        half = {LEADER_TOPICS[0]: (1.0, 6.0)}
        luma.gripper_limits = lambda store, staging_id: half
        try:
            assert not luma.find_candidates(store)[0], "delivered half-calibrated"
        finally:
            luma.gripper_limits = original
        store.close()
    print("delivery: a calibrated rig ships once its limits are readable OK")


def test_gripper_limits_reads_the_registered_sidecar():
    """The real loader, against every document shape and failure it can meet.

    The stubbed tests above pin what discovery does with limits; this pins where
    the limits come from.  Every failure has to land on ``None`` rather than a
    partial or defaulted mapping, because :func:`find_candidates` turns ``None``
    into "held back" while a plausible-looking wrong answer would be delivered.
    """
    import json

    import submit_to_luma as luma

    def sidecar(store, sid, doc, *, kind=FileKind.METADATA,
                name="verlet_gripper_limits.json"):
        d = store.kind_dir(sid, kind)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, name)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(doc if isinstance(doc, str) else json.dumps(doc))
        store.register_existing_file(sid, kind, p)
        return p

    def ours(left=(5.29, -0.013), right=(5.31, -0.015)):
        return {"gripper_calibration": {"arms": {
            "left": {"leader_topic": luma.ARM_LEADER_TOPIC["left"],
                     "closed_rad": left[0], "open_rad": left[1]},
            "right": {"leader_topic": luma.ARM_LEADER_TOPIC["right"],
                      "closed_rad": right[0], "open_rad": right[1]}}}}

    with tempfile.TemporaryDirectory() as tmp, temp_db_url() as url:
        store = StagingStore(config=Config(data_root=os.path.join(tmp, "data"),
                                           db_url=url))

        def episode():
            return store.create_episode(robot_type="yam", uploader_identity="a",
                                        supplier="verlet",
                                        task_name="Biology Lab",
                                        length_seconds=10.0,
                                        episode_format="mp4")

        # No sidecar at all.
        assert luma.gripper_limits(store, episode()) is None

        # Our shape, in metadata/.
        sid = episode()
        sidecar(store, sid, ours())
        assert luma.gripper_limits(store, sid) == {
            luma.ARM_LEADER_TOPIC["left"]: (5.29, -0.013),
            luma.ARM_LEADER_TOPIC["right"]: (5.31, -0.015)}

        # The supplier's own shape -- arm-keyed, no topic named -- resolves
        # through ARM_LEADER_TOPIC, so a sidecar they ship unchanged works.
        sid = episode()
        sidecar(store, sid, {"gripper_limits": {
            "left": {"closed_rad": 6.3, "open_rad": 1.1},
            "right": {"closed_rad": 5.2, "open_rad": -0.02}}})
        assert luma.gripper_limits(store, sid) == {
            luma.ARM_LEADER_TOPIC["left"]: (6.3, 1.1),
            luma.ARM_LEADER_TOPIC["right"]: (5.2, -0.02)}

        # A sidecar that arrived inside the upload is registered as RAW, like
        # the URDF, and is still read.
        sid = episode()
        sidecar(store, sid, ours(), kind=FileKind.RAW)
        assert len(luma.gripper_limits(store, sid) or {}) == 2

        # A degenerate span would divide by ~zero in the delivery.  It must not
        # reach the transform, and the arm that is fine must not carry the
        # episode on its own -- discovery needs both topics.
        sid = episode()
        sidecar(store, sid, ours(left=(4.2, 4.2)))
        limits = luma.gripper_limits(store, sid)
        assert luma.ARM_LEADER_TOPIC["left"] not in (limits or {}), limits
        assert not luma.find_candidates(store)[0], "delivered half-calibrated"

        # Unreadable JSON, and a document with no calibration in it at all.
        sid = episode()
        sidecar(store, sid, "{not json")
        assert luma.gripper_limits(store, sid) is None
        sid = episode()
        sidecar(store, sid, {"robot": {"robot_type": "i2rt_yam_bimanual"}})
        assert luma.gripper_limits(store, sid) is None

        # Non-numeric limits are not coerced.
        sid = episode()
        sidecar(store, sid, {"gripper_limits": {
            "left": {"closed_rad": "5.29", "open_rad": None},
            "right": {"closed_rad": 5.2, "open_rad": -0.02}}})
        assert luma.gripper_limits(store, sid) == {
            luma.ARM_LEADER_TOPIC["right"]: (5.2, -0.02)}

        store.close()
    print("delivery: the gripper sidecar loader fails closed OK")


def test_gripper_limits_come_from_the_mcap_record_first():
    """The MCAP's own ``gripper_limits`` record wins; the sidecar is legacy only.

    Every verlet export since 2026-09-10 carries its calibration inside the
    MCAP.  A record, when present, is final -- valid or not -- and only an MCAP
    without one (upload 396, most of 400) falls back to the sidecar.  A record
    that fails validation must not be rescued by a sidecar, which could only
    describe older bytes.
    """
    import json

    from mcap.writer import Writer

    import submit_to_luma as luma

    left, right = luma.ARM_LEADER_TOPIC["left"], luma.ARM_LEADER_TOPIC["right"]

    def record(lc="5.30", lo="-0.02", rc="5.31", ro="-0.05",
               units="motor_radians"):
        # MCAP metadata values are strings, as the supplier writes them.
        return {"left_closed_rad": lc, "left_open_rad": lo,
                "right_closed_rad": rc, "right_open_rad": ro, "units": units}

    stale = {"gripper_limits": {
        "left": {"closed_rad": 0.046, "open_rad": -5.276},
        "right": {"closed_rad": 5.2, "open_rad": -0.02}}}

    with tempfile.TemporaryDirectory() as tmp, temp_db_url() as url:
        store = StagingStore(config=Config(data_root=os.path.join(tmp, "data"),
                                           db_url=url))

        def episode(rec=None, sidecar=None):
            sid = store.create_episode(robot_type="yam", uploader_identity="a",
                                       supplier="verlet",
                                       task_name="Biology Lab",
                                       length_seconds=10.0,
                                       episode_format="mp4")
            src = os.path.join(tmp, f"{sid}_src.mcap")
            with open(src, "wb") as fh:
                w = Writer(fh)
                w.start()
                if rec is not None:
                    w.add_metadata(luma.MCAP_CALIBRATION_RECORD, rec)
                w.finish()
            store.add_files(sid, [src], FileKind.RAW)
            if sidecar is not None:
                d = store.kind_dir(sid, FileKind.METADATA)
                os.makedirs(d, exist_ok=True)
                p = os.path.join(d, "verlet_gripper_limits.json")
                with open(p, "w", encoding="utf-8") as fh:
                    json.dump(sidecar, fh)
                store.register_existing_file(sid, FileKind.METADATA, p)
            return sid

        # A record beats a sidecar that disagrees with it.
        sid = episode(record(), sidecar=stale)
        assert luma.gripper_limits(store, sid) == {
            left: (5.30, -0.02), right: (5.31, -0.05)}

        # No record: the legacy sidecar decides.
        sid = episode(None, sidecar=stale)
        assert luma.gripper_limits(store, sid) == {
            left: (0.046, -5.276), right: (5.2, -0.02)}

        # No record and no sidecar: held back.
        assert luma.gripper_limits(store, episode(None)) is None

        # A record that fails validation is final, sidecar or not.
        missing_arm = {k: v for k, v in record().items() if k != "right_open_rad"}
        for bad in (record(lo="5.30"),          # degenerate span
                    record(units="degrees"),    # not the unit the transform assumes
                    record(rc="nan"),           # parses, but is not a number
                    record(ro="n/a"),
                    missing_arm):
            sid = episode(bad, sidecar=stale)
            assert luma.gripper_limits(store, sid) is None, bad

        # A reclaimed RAW (row kept, size cleared) vouches for nothing.
        sid = episode(record(), sidecar=stale)
        store.db.execute("UPDATE files SET size_bytes = NULL "
                         "WHERE staging_id = ? AND kind = 'raw'", (sid,))
        store.db.commit()
        assert luma.gripper_limits(store, sid) == {
            left: (0.046, -5.276), right: (5.2, -0.02)}
        store.close()
    print("delivery: gripper limits come from the MCAP record first OK")



def test_the_scope_narrows_the_query_not_its_result():
    """A scoped call must not pay for the episodes it was not asked about.

    Eligibility costs an ``os.path.exists`` per product, so narrowing afterwards
    made the daily ``verlet``/"Biology Lab" sweep -- and every "what would this
    queue?" probe behind the Jobs tab -- read all 24k undelivered episodes to
    find its few hundred.  Pinned by what gets stat-ed rather than by the answer:
    the answer is the same either way, and the cost is the whole point.
    """
    import submit_to_luma as luma

    with tempfile.TemporaryDirectory() as tmp, temp_db_url() as url:
        store = StagingStore(config=Config(data_root=os.path.join(tmp, "data"),
                                           db_url=url))

        def episode(task_name: str, supplier: str = "yun") -> int:
            sid = store.create_episode(robot_type="yam", uploader_identity="a",
                                       supplier=supplier, task_name=task_name,
                                       length_seconds=10.0)
            for name, kind in (("telemetry.webui.mcap", FileKind.MCAP),
                               ("cam_high.mp4", FileKind.VIDEO_L1)):
                path = os.path.join(tmp, f"{sid}_{name}")
                with open(path, "wb") as fh:
                    fh.write(b"x" * 8)
                store.add_files(sid, [path], kind)
            return sid

        wanted = episode("Pick")
        other = episode("Fold")
        elsewhere = episode("Pick", supplier="verlet")

        seen: list[str] = []
        real_exists = os.path.exists

        def recording_exists(path):
            seen.append(str(path))
            return real_exists(path)

        os.path.exists = recording_exists          # noqa: SLF001
        try:
            cands, _ = luma.find_candidates(store, supplier="yun",
                                            task_name="Pick")
        finally:
            os.path.exists = real_exists

        assert [c.staging_id for c in cands] == [wanted], cands
        for sid in (other, elsewhere):
            assert not any(f"/{sid}_" in p for p in seen), \
                f"episode {sid} was stat-ed despite being out of scope"
        assert any(f"/{wanted}_" in p for p in seen), seen

        # And the unscoped call still sees everything it used to.
        assert len(luma.find_candidates(store)[0]) == 2, "yun episodes lost"
        store.close()
    print("delivery: the scope narrows the candidate query OK")



if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
