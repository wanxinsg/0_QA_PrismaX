# EXCERPT -- not importable on its own.
# Source: workers/svo2/svo2_convert.py, lines 427-465 (branch fix/luma-serial-letter-guard @ 7554497 + uncommitted working tree, 2026-09-23).
# Single-view MP4 -> L2 preview transcode (not delivered to Luma; review only).

def make_level2_from_mp4(src_mp4: Path, out_path: Path, *, encoder: str) -> None:
    """Transcode one single-view MP4 to a single L2 video.

    The MP4+MCAP upload type ships one already-decoded single-view MP4 per
    camera (``cam_high.mp4`` etc.), not a side-by-side stereo HEVC stream, so
    there is no eye to split -- this produces exactly one L2 output.  It reuses
    the shared L2 encode settings (:func:`_encoder_args`) and the same fps /
    scale / pad normalisation (:func:`_l2_filter` without a crop) as the SVO2
    L2 path, so L2 clips are uniform (640-wide, 30 fps, GOP ``L2_GOP``,
    ``L2_BITRATE``) regardless of source format.

    Decode runs on NVDEC when the NVENC encoder was selected.  The frames still
    come back to system memory for swscale -- unlike the ego L2s this chain
    crops and pads, which ``scale_cuda`` cannot do -- but moving just the
    decode off the CPU is measurably faster and, because the filter graph still
    sees software frames, byte-for-byte identical (verified PSNR inf on a real
    ``cam_high.mp4``).
    """
    w, h, *_ = _probe_mp4(src_mp4)
    out_w, out_h = _scaled_dims(w, h)
    enc = _encoder_args(encoder)
    # Same normalisation as an SVO2 eye, minus the crop (single view already).
    vf = _l2_filter("null", out_w, out_h)
    cmd = [
        "ffmpeg", "-y",
        *_hwaccel_args(encoder),
        "-i", str(src_mp4),
        "-vf", vf,
        *enc, "-movflags", "+faststart", str(out_path),
    ]
    proc = subprocess.run(cmd, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg failed (rc={proc.returncode}) for {src_mp4.name}:\n"
            f"{proc.stderr.decode(errors='replace')[-4000:]}"
        )
