"""Watermark region detection: template matching with a geometry fallback."""

from __future__ import annotations

import numpy as np

from nlmclean.core.region import Region
from nlmclean.detect.heuristic import HEURISTIC_CONFIDENCE, heuristic_region


def detect_region(img_bgr: np.ndarray, kind: str) -> tuple[Region, float]:
    """Locate the NotebookLM watermark in a frame/page/slide image.

    kind: "video" or "doc". Returns (region, confidence 0..1). Confidence below
    ~0.5 means the caller should ask the user to confirm the region.
    """
    h, w = img_bgr.shape[:2]

    from nlmclean.detect.template import match_template  # deferred: loads template assets

    match = match_template(img_bgr, kind)
    if match is not None:
        return match

    return heuristic_region(w, h, kind), HEURISTIC_CONFIDENCE
