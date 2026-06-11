"""Job/result types and the cancellation/progress plumbing shared by CLI and GUI."""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from nlmclean.core.region import Region

# fraction 0..1, human-readable stage label
ProgressCallback = Callable[[float, str], None]


def null_progress(_fraction: float, _stage: str) -> None:
    pass


class CancelledError(Exception):
    """Raised inside a handler when its CancelToken is triggered."""


class CancelToken:
    def __init__(self) -> None:
        self._event = threading.Event()

    def cancel(self) -> None:
        self._event.set()

    @property
    def cancelled(self) -> bool:
        return self._event.is_set()

    def raise_if_cancelled(self) -> None:
        if self.cancelled:
            raise CancelledError()


@dataclass
class Job:
    src: Path
    dst: Path
    mode: str = "fast"  # video only: "fast" (delogo) | "quality" (inpaint)
    detect: str = "auto"  # video only: "auto" (templates) | "universal" (any static mark)
    region: Region | None = None  # explicit region skips auto-detection
    profile: str | None = None  # watermark profile name when already detected
    strip_metadata: bool = False  # also remove EXIF / PDF info / docProps / tags
    cancel: CancelToken = field(default_factory=CancelToken)


@dataclass
class JobResult:
    ok: bool
    message: str = ""
    dst: Path | None = None
