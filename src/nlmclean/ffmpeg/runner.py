"""Run ffmpeg with live progress parsing and hard cancellation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from nlmclean.core.job import CancelledError, CancelToken, ProgressCallback, null_progress
from nlmclean.ffmpeg.locate import find_ffmpeg, subprocess_flags


def run_ffmpeg(
    args: list[str],
    *,
    duration: float,
    output: Path,
    progress: ProgressCallback = null_progress,
    cancel: CancelToken | None = None,
    stage: str = "processing",
) -> None:
    """Run `ffmpeg <args>` reporting progress from `-progress pipe:1` key=value lines.

    On cancel: kills the process and deletes the partial output file.
    On nonzero exit: raises RuntimeError with the tail of stderr.
    """
    exe = find_ffmpeg()
    if not exe:
        raise RuntimeError("ffmpeg not found")

    cmd = [exe, "-y", *args, "-progress", "pipe:1", "-nostats", "-loglevel", "error"]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        **subprocess_flags(),
    )
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if cancel is not None and cancel.cancelled:
                proc.kill()
                proc.wait()
                output.unlink(missing_ok=True)
                raise CancelledError()
            key, _, value = line.strip().partition("=")
            if key == "out_time_us" and duration > 0 and value.lstrip("-").isdigit():
                fraction = min(1.0, int(value) / (duration * 1_000_000))
                progress(fraction, stage)
        stderr = proc.stderr.read() if proc.stderr else ""
        code = proc.wait()
        if code != 0:
            output.unlink(missing_ok=True)
            tail = "\n".join(stderr.strip().splitlines()[-8:])
            raise RuntimeError(f"ffmpeg failed (exit {code}):\n{tail}")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait()


# accurate-seek coarse window: jump (via fast keyframe seek) to this many
# seconds before the target, then decode the remainder accurately
_ACCURATE_SEEK_WINDOW = 5.0


def extract_frame(src: Path, at_seconds: float, *, accurate: bool = False) -> bytes:
    """Decode a single frame as PNG bytes (used by detection sampling and GUI preview).

    With ``accurate=False`` (default) a plain ``-ss`` before ``-i`` does a fast
    keyframe seek - fine for one-off previews where the exact frame doesn't
    matter. But plain input seeking lands on the nearest *preceding keyframe*,
    and on sparse-keyframe slideshow exports some ffmpeg builds (notably the
    macOS evermeet static build) return the *same* keyframe for many different
    timestamps. That collapses the temporal signal that universal detection and
    temporal mask refinement rely on - they see "no motion" and bail.

    ``accurate=True`` uses a two-stage seek: a fast keyframe jump to a few
    seconds before the target (``-ss`` before ``-i``), then an accurate decode
    of the small remainder (``-ss`` after ``-i``). This returns the frame at the
    requested time on every ffmpeg build, without decoding from the start, so
    samples spread across the video are genuinely distinct.
    """
    exe = find_ffmpeg()
    if not exe:
        raise RuntimeError("ffmpeg not found")
    t = max(0.0, at_seconds)
    if accurate:
        coarse = max(0.0, t - _ACCURATE_SEEK_WINDOW)
        seek = ["-ss", f"{coarse:.3f}", "-i", str(src), "-ss", f"{t - coarse:.3f}"]
    else:
        seek = ["-ss", f"{t:.3f}", "-i", str(src)]
    cmd = [
        exe, *seek,
        "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1",
    ]  # fmt: skip
    proc = subprocess.run(cmd, capture_output=True, timeout=120, **subprocess_flags())
    if proc.returncode != 0 or not proc.stdout:
        raise RuntimeError(f"could not extract frame at {at_seconds}s from {src}")
    return proc.stdout
