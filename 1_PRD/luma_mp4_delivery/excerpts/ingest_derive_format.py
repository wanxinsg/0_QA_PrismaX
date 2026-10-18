# EXCERPT -- not importable on its own.
# Source: webui/ingest_api.py, lines 173-185 (branch fix/luma-serial-letter-guard @ 7554497 + uncommitted working tree, 2026-09-23).
# How an upload is tagged episode_format='mp4': any .mp4 among the raw files.

def _derive_format(filenames) -> EpisodeFormat:
    """Infer the episode format from the uploaded raw file names.

    Any ``.mp4`` raw marks an MP4+MCAP upload; otherwise the historic SVO2
    default applies.  (``r405`` -- the future RealSense RGBD format -- has no
    recognisable extension yet, so it must be passed explicitly.)
    """
    for name in filenames:
        if str(name).lower().endswith(".mp4"):
            return EpisodeFormat.MP4
    return EpisodeFormat.SVO2


