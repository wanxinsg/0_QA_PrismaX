# EXCERPT -- not importable on its own.
# Source: webui2/jobs/schedule.py, lines 1-76 (branch fix/luma-serial-letter-guard @ 7554497 + uncommitted working tree, 2026-09-23).
# Seeded clock-driven jobs (the daily postprocess -> upload_luma pair).

"""Clock-driven jobs: the ones due at a wall-clock time, not "when it is quiet".

Production has exactly one of these -- the Luma **"Block manipulation" / supplier
``yun``** sweep at 08:00 Pacific, as postprocess-then-deliver -- and it lived in
a Python tuple.  Changing its time, pausing it for a day, or adding a second
recurring sweep was therefore a code edit and a service restart.  Here they are
rows, so they are an ordinary thing to manage from the Jobs tab.

Three behaviours are carried over from the production scheduler because each one
was a fix for something real:

* **Arming is separate from queueing.**  A job arms once per local day at its
  time and stays armed until its work is actually *gone*, not until it has been
  started.  A run the dispatcher preempted, or that the machine was too busy
  for, picks itself up again instead of waiting for tomorrow.  The exception is
  a run somebody *cancelled*: that stamps the day (``queue._disarm_schedule``),
  because a job that came straight back within seconds of being stopped is not
  resilience, it is a job that will not take no for an answer.  ``clear_stamp``
  -- the "Run today" button -- is the way back within the day.
* **The day stamp is written on disarm, not on arm.**  The armed set lives in
  memory, so a stamp written at arming time would be the only trace left after a
  restart -- and it would say "already done".  Stamping on disarm is what makes
  a service restarted at 08:05 resume the day's work rather than skip it.
* **``after_key`` chains a two-stage sweep.**  While the stage it names is still
  armed, an empty "is there work?" probe here means "not built yet", not
  "nothing to do", so the downstream stage stays armed.  That is the whole
  reason the Luma postprocess and the Luma delivery are scheduled as a pair: an
  episode has nothing to deliver until its products exist.

Exempt from the idle window by default (``ignore_window``): 08:00 is inside the
23:00-09:00 window by an hour, and the hard 09:00 stop would cut every run short
after sixty minutes.  The point of putting something on a clock is that it
finishes.
"""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from ..api.common import db, require

# Seeded once, into an empty table, and recorded in ``settings`` so deleting a
# seeded job does not resurrect it on the next boot.
SEEDED_SETTING = "webui2.scheduled_jobs.seeded"

LUMA_SUPPLIER = "yun"
LUMA_TASK = "Block manipulation"

# The production schedule, as the seed.  Two entries in this order because the
# delivery is downstream of the post-processing; the delivery also waits behind
# it for the GPU they both need, so the ordering enforces itself.
DEFAULT_JOBS: List[Dict[str, Any]] = [
    {
        "key": "luma-block-yun-postprocess",
        "label": f"Daily {LUMA_TASK} postprocess ({LUMA_SUPPLIER})",
        "kind": "postprocess",
        "params": {"supplier": LUMA_SUPPLIER, "task_name": LUMA_TASK},
        "hour": 8, "minute": 0, "priority": 4,
        "note": "Builds the products the Luma delivery below sends.",
    },
    {
        "key": "luma-block-yun-deliver",
        "label": f"Daily {LUMA_TASK} delivery to Luma ({LUMA_SUPPLIER})",
        "kind": "upload_luma",
        "params": {"supplier": LUMA_SUPPLIER, "task_name": LUMA_TASK},
        "hour": 8, "minute": 0, "priority": 4,
        "after_key": "luma-block-yun-postprocess",
        "note": "Crops each Level-1 to the primary eye and uploads it.",
    },
]
