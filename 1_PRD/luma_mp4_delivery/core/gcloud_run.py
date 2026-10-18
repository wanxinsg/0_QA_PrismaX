"""Bounded ``gcloud`` invocation, shared by every path that uploads to a bucket.

``subprocess.run(["gcloud", ...])`` with no ``timeout`` is how a delivery job
wedges.  On 2026-09-04 a ``gcloud storage cp`` for staging 30578 sat at 0% CPU
for twenty minutes with every socket to Google in ``CLOSE-WAIT`` -- the remote
end had gone, gcloud's worker never noticed, and because the call could not
return, the caller's retry loop never ran and the whole Luma delivery stopped
until somebody killed the process by hand.

Two things make that survivable, and both are easy to get wrong on your own,
which is why they live here rather than in each caller:

* **A timeout**, so a hang becomes an ordinary failure the caller can retry.
* **Killing by process group.**  gcloud spawns parallel workers; killing only
  the direct child leaves those reparented to init, still holding sockets.
  That is exactly what the 30578 hang left behind.

:func:`error_text` exists for the third mistake: gcloud writes per-file progress
to stderr, so ``stderr[:300]`` is a list of ``Copying file://...`` lines with
the actual error past the cut -- the 30578 failure was logged three times
without once saying why.
"""

from __future__ import annotations

import os
import signal
import subprocess

# The ceiling on a *hang*, not a throughput budget: a Luma episode is ~400 MB
# across five files and lands in seconds.  Anything still running at ten
# minutes is not slow, it is stuck.
DEFAULT_TIMEOUT_S = 600


class GcloudTimeout(RuntimeError):
    """A gcloud invocation exceeded its timeout and was killed."""


def run(argv: "list[str]", *, timeout: "float | None" = None
        ) -> "tuple[int, str, str]":
    """Run ``argv``, bounded.  Returns ``(returncode, stdout, stderr)``.

    A timeout returns ``-1`` with an explanatory stderr rather than raising, so
    a caller's ordinary "did it fail?" branch covers it too.
    """
    timeout = DEFAULT_TIMEOUT_S if timeout is None else timeout
    proc = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, start_new_session=True)
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out or "", err or ""
    except subprocess.TimeoutExpired:
        _kill_group(proc)
        return -1, "", f"timed out after {timeout:g}s and was killed"


def run_checked(argv: "list[str]", *, timeout: "float | None" = None) -> str:
    """:func:`run`, raising on failure.  Returns stdout.

    The drop-in for ``subprocess.run(..., check=True)`` at a call site that has
    no retry loop of its own: a hang now raises like any other failure instead
    of blocking forever.
    """
    rc, out, err = run(argv, timeout=timeout)
    if rc == 0:
        return out
    detail = error_text(err) or f"exit {rc}"
    if rc == -1:
        raise GcloudTimeout(f"{argv[0]} {' '.join(argv[1:3])}: {detail}")
    raise subprocess.CalledProcessError(rc, argv, output=out, stderr=err)


def _kill_group(proc: subprocess.Popen) -> None:
    """SIGTERM then SIGKILL the whole group, so no worker is left orphaned."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(os.getpgid(proc.pid), sig)
        except (ProcessLookupError, PermissionError):
            return
        try:
            proc.communicate(timeout=10)
            return
        except subprocess.TimeoutExpired:
            continue


def error_text(stderr: str, limit: int = 300) -> str:
    """The part of gcloud's stderr worth logging: the tail, minus progress."""
    lines = [ln.strip() for ln in (stderr or "").splitlines() if ln.strip()]
    lines = [ln for ln in lines if not ln.startswith("Copying ")] or lines
    return " | ".join(lines[-3:])[-limit:]
