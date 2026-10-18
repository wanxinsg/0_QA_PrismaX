"""Crop Luma's Level-1 videos down to the single delivered eye.

Every ``.svo2`` camera on the ZED rig records **side-by-side stereo**: left and
right eye concatenated into one 1920x600 frame (960x600 per eye).  Our stored
Level-1 product is that frame muxed verbatim, so it carries both eyes.  Luma is
only to receive the eye their videos are actually derived from -- the *left*
eye, which :mod:`svo2_convert` uses for the primary L2 streams (``high.mp4`` /
``left.mp4`` / ``right.mp4``, the ones the WebUI displays).

Which eye that is flipped on 2026-08-10: the primary L2 used to be the right
eye and this module cropped to match.  Episodes converted before then still
have right-eye primaries on disk and were delivered the right eye, which was
correct at the time -- **re-delivering one of them through this module now
would send the eye that does not match its previews**.  Only staging
13204-13244 (upload 138) was corrected in place, by swapping its L2 files and
re-cropping its delivery; see
``migration/redeliver_luma_swapped_eye_2026_08_10.py``, whose PSNR probe is the
way to check any given episode before re-delivering it.

Why this re-encodes
-------------------
The obvious trick is to leave the bitstream alone and just narrow the display
window -- HEVC has a conformance window exactly for that, the eye boundary at
x=960 is CTU-aligned, and it costs under a second per file::

    ffmpeg -i cam_high.mp4 -c copy -bsf:v hevc_metadata=crop_left=960 out.mp4

That does *not* work here, and it is worth being explicit about why: the
conformance window only changes which decoded pixels are **displayed**.  Both
eyes remain fully encoded in the file -- the output is byte-for-byte the same
size -- and one flag flip restores them::

    ffmpeg -i out.mp4 -c copy -bsf:v hevc_metadata=crop_left=0 undo.mp4
    -> 1920x600, the other eye intact

Since the requirement is that the other eye is not *delivered*, the pixels have
to actually go, which means decoding and re-encoding.  HEVC is not separable at
the midline whatever the alignment: intra prediction, motion vectors, deblocking
and CABAC all cross it unless the encoder emitted independent tiles there, and
the camera's does not.

Cost, measured on the A4000 (episode 13050, three ~170 s cameras):

    serial            57.1 s/episode
    3 concurrent      27.2 s/episode      <- what this module does
    upload of result   ~3.0 s/episode     (240 MB at 80.5 MiB/s)

So the encode dominates the upload roughly 9:1 and the three cameras are run
concurrently; overlapping the encode with the upload would save the ~3 s the
upload takes and is not worth the machinery.

:data:`CQ` 24 measures 45.8 dB Y-PSNR against the source's delivered eye -- visually
transparent -- for 67 MB where the source frame (both eyes) is 276 MB.  CQ 20
buys 0.7 dB for 1.8x the bytes, which is not a trade worth making on a
deliverable this size.

Keeping the capture timestamps
------------------------------
Re-encoding destroys the frame timing unless it is put back.  Our L1 carries
the *real* per-frame capture time (see ``svo2_convert.make_level1``), and the
first version of this module lost it: with a filter graph and no frame-rate
mode ffmpeg resamples onto a constant grid, and even with ``-fps_mode
passthrough`` the encoder's own time base (1/framerate by default) quantises
every PTS to a 1/60 multiple.  The delivered videos came out on a synthetic
constant-rate grid -- which the customer noticed, because a dropped frame is
then unlocatable.

Rather than fight the encoder's timestamp handling, the encode is made exactly
1:1 in frames (``-fps_mode passthrough`` for no duplicate/drop, ``-bf 0`` so
decode order is presentation order) and the source's timestamps are then
transplanted onto the encoded packets verbatim -- :func:`restamp_from_source`,
the same PyAV remux ``svo2_convert.make_level1`` uses.  Measured on episode
13187: 1060 distinct inter-frame intervals preserved, max difference 0.000 us,
for 0.3 s on top of a ~14 s encode.

The 1:1 frame count is verified rather than assumed; a mismatch raises, because
a silently misaligned timestamp track is worse than a failed delivery.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from fractions import Fraction

import av

# Must stay identical to svo2_convert._CROP_PRIMARY_EYE: the whole point is that
# Luma's video is the same eye their L2 previews were cut from.
DELIVERED_EYE = "left"
CROP_FILTER = "crop=iw/2:ih:0:0"

# Container/timestamp resolution of the delivered video.  Microseconds: fine
# enough for the ~0.5 ms of real capture jitter, and it matches the L1 our
# timestamps are copied from.
TIMESCALE = 1_000_000

CQ = 24
TARGET_BITRATE = "7M"
MAX_BITRATE = "12M"

# Cameras per episode; they encode concurrently on separate NVENC sessions.
MAX_WORKERS = 3


class NotStereo(ValueError):
    """Raised when a source is not the side-by-side stereo layout."""


def _probe_dims(path: str) -> tuple[int, int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=width,height", "-of", "csv=p=0:s=x", path],
        capture_output=True, text=True, check=True).stdout.strip()
    w, _, h = out.partition("x")
    return int(w), int(h)


def detect_encoder(preferred: str = "auto") -> str:
    """``hevc_nvenc`` when the GPU can actually take a session, else ``libx265``.

    Probed rather than assumed: the host's GPU has wedged before, and silently
    falling back is much better than failing a customer delivery.
    """
    if preferred != "auto":
        return preferred
    try:
        probe = subprocess.run(
            ["ffmpeg", "-hide_banner", "-v", "error", "-f", "lavfi",
             "-i", "nullsrc=s=256x256:d=0.1", "-c:v", "hevc_nvenc",
             "-f", "null", "-"],
            capture_output=True, text=True, timeout=60)
        if probe.returncode == 0:
            return "hevc_nvenc"
    except (OSError, subprocess.SubprocessError):
        pass
    return "libx265"


def source_pts_us(path: str) -> list[int]:
    """Every frame's presentation timestamp in ``path``, microseconds, ascending.

    Sorted deliberately: packets come out in *decode* order, which differs from
    presentation order whenever the source has B-frames.  The cropped output is
    encoded with ``-bf 0``, so its packet order **is** presentation order --
    pairing the two positionally is only correct if this side is in presentation
    order too.  Our L1s happen to be all-P (a verbatim copy of the ZED stream),
    but a B-frame source would otherwise get its timestamps shuffled onto the
    wrong frames, which the muxer rejects as non-monotonic rather than
    delivering quietly.
    """
    out: list[int] = []
    with av.open(path) as container:
        stream = container.streams.video[0]
        for packet in container.demux(stream):
            if packet.pts is None or not packet.size:
                continue
            out.append(int(round(float(packet.pts * packet.time_base) * TIMESCALE)))
    return sorted(out)


def restamp_from_source(encoded: str, dst: str, pts_us: list[int]) -> int:
    """Copy ``encoded``'s packets to ``dst``, replacing PTS/DTS with ``pts_us``.

    A stream copy -- the encoded pixels are untouched -- so this only rewrites
    the timing.  ``encoded`` must be 1:1 in frames with the source and free of
    B-frames (``crop_one`` enforces both), so the Nth packet is the Nth source
    frame and the mapping is positional.

    Returns the number of packets written; raises if the counts disagree rather
    than delivering a video whose timestamps are silently off by a frame.
    """
    time_base = Fraction(1, TIMESCALE)
    n = 0
    with av.open(encoded) as inp, av.open(
            dst, "w", format="mp4",
            options={"movflags": "+faststart",
                     "movie_timescale": str(TIMESCALE)}) as out:
        in_stream = inp.streams.video[0]
        out_stream = out.add_stream_from_template(in_stream)
        out_stream.time_base = time_base
        out_stream.codec_tag = "hvc1"
        # Each packet's duration is only known once the next timestamp arrives,
        # so muxing runs one packet behind.
        pending = None
        for packet in inp.demux(in_stream):
            if not packet.size:
                continue
            if n >= len(pts_us):
                raise RuntimeError(
                    f"{os.path.basename(encoded)}: encoded {n + 1}+ frames but "
                    f"the source has {len(pts_us)}")
            pts = pts_us[n]
            n += 1
            if pending is not None:
                prev_pts, prev = pending
                prev.duration = max(1, pts - prev_pts)
                out.mux(prev)
            packet.stream = out_stream
            packet.time_base = time_base
            packet.pts = packet.dts = pts
            pending = (pts, packet)
        if pending is not None:
            _, prev = pending
            prev.duration = (pts_us[-1] - pts_us[-2]) if len(pts_us) > 1 else 1
            out.mux(prev)
    if n != len(pts_us):
        raise RuntimeError(
            f"{os.path.basename(encoded)}: encoded {n} frames, source has "
            f"{len(pts_us)} -- refusing to deliver misaligned timestamps")
    return n


def crop_one(src: str, dst: str, *, encoder: str = "auto") -> dict:
    """Write the delivered eye of ``src`` to ``dst``.

    Raises :class:`NotStereo` when the source is not twice as wide as one eye
    should be -- a mono source cropped in half would silently deliver half a
    picture, which is worse than a failed delivery.
    """
    enc = detect_encoder(encoder)
    w, h = _probe_dims(src)
    if w < 2 or w % 2:
        raise NotStereo(f"{os.path.basename(src)} is {w}x{h}; "
                        "not a side-by-side stereo frame")

    # The encoder writes here; dst gets the restamped copy (see below).
    fd, encoded = tempfile.mkstemp(suffix=".mp4", dir=os.path.dirname(dst) or None,
                                   prefix=f".{os.path.basename(dst)}.enc.")
    os.close(fd)

    cmd = ["ffmpeg", "-v", "error", "-y"]
    if enc == "hevc_nvenc":
        cmd += ["-hwaccel", "cuda"]
    cmd += ["-i", src, "-vf", CROP_FILTER, "-c:v", enc]
    if enc == "hevc_nvenc":
        cmd += ["-preset", "p4", "-rc", "vbr", "-cq", str(CQ),
                "-b:v", TARGET_BITRATE, "-maxrate", MAX_BITRATE]
    else:
        cmd += ["-crf", str(CQ), "-preset", "medium"]
    # The encode must be exactly 1:1 in frames with the source so the capture
    # timestamps can be transplanted back afterwards (see the module docstring):
    #   passthrough -- do not resample onto a constant grid (which also
    #                  duplicates a frame to make the rate come out),
    #   -bf 0       -- no B-frames, so decode order is presentation order and
    #                  the Nth packet out is the Nth frame in.
    cmd += ["-fps_mode", "passthrough", "-bf", "0"]
    # No audio on these streams; -an keeps a stray track from riding along.
    cmd += ["-an", encoded]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"crop failed for {os.path.basename(src)}: "
                f"{(proc.stderr or '').strip()[:300]}")
        # Put the real capture timestamps back (the encode is 1:1 by
        # construction; restamp_from_source verifies that).
        frames = restamp_from_source(encoded, dst, source_pts_us(src))
    finally:
        if os.path.exists(encoded):
            os.unlink(encoded)

    out_w, out_h = _probe_dims(dst)
    if (out_w, out_h) != (w // 2, h):
        raise RuntimeError(
            f"crop produced {out_w}x{out_h} for {os.path.basename(src)}, "
            f"expected {w // 2}x{h}")
    return {"src": src, "dst": dst, "encoder": enc,
            "src_dims": (w, h), "dst_dims": (out_w, out_h),
            "frames": frames,
            "src_bytes": os.path.getsize(src),
            "dst_bytes": os.path.getsize(dst)}


def crop_all(paths: list[str], outdir: str, *, encoder: str = "auto",
             max_workers: int = MAX_WORKERS, log=print) -> dict[str, str]:
    """Crop every path into ``outdir``, keeping the basename.

    The basename is preserved deliberately -- Luma's side keys off
    ``cam_high.mp4`` / ``cam_left_wrist.mp4`` / ``cam_right_wrist.mp4``, and the
    mcap transform already delivers under the stored basename for the same
    reason.  Returns ``{source path: cropped path}``.

    Any failure propagates: a partial episode must not be recorded as
    delivered, and the caller's temp dir is discarded whole.
    """
    if not paths:
        return {}
    os.makedirs(outdir, exist_ok=True)
    # Detect once, not per file: the probe costs a subprocess, and all three
    # cameras must land on the same encoder anyway.
    enc = detect_encoder(encoder)
    jobs = [(p, os.path.join(outdir, os.path.basename(p))) for p in paths]

    # Concurrency is what makes this affordable -- 2.1x on three cameras
    # (57.1 s -> 27.2 s), each ffmpeg holding its own NVENC session.

    results: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        futures = {pool.submit(crop_one, s, d, encoder=enc): (s, d)
                   for s, d in jobs}
        for fut in futures:
            info = fut.result()          # re-raises the first failure
            results[info["src"]] = info["dst"]
            log(f"  crop: {os.path.basename(info['src'])} "
                f"{info['src_dims'][0]}x{info['src_dims'][1]} -> "
                f"{info['dst_dims'][0]}x{info['dst_dims'][1]} "
                f"({info['src_bytes'] / 1e6:.0f} -> "
                f"{info['dst_bytes'] / 1e6:.0f} MB, {DELIVERED_EYE} eye)")
    return results


def have_ffmpeg() -> bool:
    return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))
