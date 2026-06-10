"""Fallback watermark placement derived from known NotebookLM export geometry.

All position constants live here so a change in NotebookLM's export layout
is a one-file fix. Reference geometry measured on a real 2026-06 Video
Overview export (1280x720): logo + "NotebookLM" wordmark, 115x12 px of
visible strokes with the right edge 17 px and the bottom edge 16 px from
the frame border. Constants below include a little slack around that.
"""

from __future__ import annotations

from nlmclean.core.region import Region

REF_WIDTH = 1280.0

# (mark_w, mark_h, right_margin, bottom_margin) at REF_WIDTH
_GEOMETRY = {
    "video": (118, 18, 15, 14),
    "doc": (118, 18, 15, 14),
}

PAD = 8
HEURISTIC_CONFIDENCE = 0.3


def heuristic_region(img_w: int, img_h: int, kind: str) -> Region:
    mark_w, mark_h, right, bottom = _GEOMETRY[kind]
    s = img_w / REF_WIDTH
    w = round(mark_w * s)
    h = round(mark_h * s)
    x = img_w - round(right * s) - w
    y = img_h - round(bottom * s) - h
    return Region(x, y, w, h).padded(PAD).clamped(img_w, img_h)
