"""Find ffmpeg/ffprobe binaries.

Resolution order:
1. binary bundled next to the frozen app (releases ship a static build in _internal/ffmpeg/)
2. imageio-ffmpeg's downloaded binary (dev/CI; ffmpeg only - it ships no ffprobe)
3. anything on PATH
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from functools import lru_cache
from pathlib import Path

_EXE = ".exe" if sys.platform == "win32" else ""


def subprocess_flags() -> dict:
    """Extra Popen kwargs - suppresses the console window flash on Windows GUI builds."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


def _bundled(name: str) -> str | None:
    if not getattr(sys, "frozen", False):
        return None
    candidate = Path(sys.executable).parent / "_internal" / "ffmpeg" / f"{name}{_EXE}"
    return str(candidate) if candidate.exists() else None


@lru_cache(maxsize=1)
def find_ffmpeg() -> str | None:
    bundled = _bundled("ffmpeg")
    if bundled:
        return bundled
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    return shutil.which("ffmpeg")


@lru_cache(maxsize=1)
def find_ffprobe() -> str | None:
    bundled = _bundled("ffprobe")
    if bundled:
        return bundled
    return shutil.which("ffprobe")


def ffmpeg_version() -> str | None:
    exe = find_ffmpeg()
    if not exe:
        return None
    try:
        out = subprocess.run(
            [exe, "-version"], capture_output=True, text=True, timeout=10, **subprocess_flags()
        ).stdout
        return out.splitlines()[0].strip() if out else None
    except Exception:
        return None
