"""Rectangular watermark region with the scaling/clamping math shared by all handlers."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Region:
    x: int
    y: int
    w: int
    h: int

    @classmethod
    def parse(cls, text: str) -> Region:
        """Parse "x,y,w,h" (CLI --region syntax)."""
        parts = [int(p) for p in text.split(",")]
        if len(parts) != 4:
            raise ValueError(f"expected x,y,w,h - got {text!r}")
        region = cls(*parts)
        if region.w <= 0 or region.h <= 0:
            raise ValueError(f"region must have positive size - got {text!r}")
        return region

    def padded(self, pad: int) -> Region:
        return Region(self.x - pad, self.y - pad, self.w + 2 * pad, self.h + 2 * pad)

    def clamped(self, bound_w: int, bound_h: int, margin: int = 0) -> Region:
        """Clamp inside a (bound_w x bound_h) frame, keeping `margin` px away from every
        edge. ffmpeg's delogo filter rejects rects that touch the frame border, so video
        callers pass margin=1."""
        x = max(margin, self.x)
        y = max(margin, self.y)
        w = min(self.w, bound_w - margin - x)
        h = min(self.h, bound_h - margin - y)
        return Region(x, y, max(1, w), max(1, h))

    def scaled(self, factor: float) -> Region:
        return Region(
            round(self.x * factor),
            round(self.y * factor),
            max(1, round(self.w * factor)),
            max(1, round(self.h * factor)),
        )

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)

    def __str__(self) -> str:
        return f"{self.x},{self.y},{self.w},{self.h}"
