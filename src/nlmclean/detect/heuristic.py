"""Fallback watermark placement derived from known NotebookLM export geometry.

All position constants live here so a change in NotebookLM's export layout
is a one-file fix. Reference geometry (from real exports):

- Video Overviews: ~200x60 px logo at (1240, 850) on a 1470x956 frame,
  i.e. right margin ~30 px / bottom margin ~46 px, scaling linearly with width.
- PDF / PPTX slide exports: same corner, ~115 px from the right edge and
  ~30 px from the bottom at slide scale.
"""

from __future__ import annotations

from nlmclean.core.region import Region

REF_WIDTH = 1470.0

# (mark_w, mark_h, right_margin, bottom_margin) at REF_WIDTH
_GEOMETRY = {
    "video": (200, 60, 30, 46),
    "doc": (200, 60, 30, 30),
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
