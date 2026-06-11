"""Watermark region detection: template matching with a geometry fallback."""

from __future__ import annotations

import numpy as np

from nlmclean.core.region import Region
from nlmclean.detect.heuristic import HEURISTIC_CONFIDENCE, heuristic_region
from nlmclean.detect.profiles import HEURISTIC_PROFILE, profiles_for


def detect_region(img_bgr: np.ndarray, kind: str) -> tuple[Region, float, str]:
    """Locate a known watermark in a frame/page/slide image.

    kind: "video", "doc" or "image". Tries every profile registered for the
    kind and keeps the best hit. Returns (region, confidence 0..1, profile
    name). Confidence below ~0.5 means the caller should ask the user to
    confirm the region.
    """
    h, w = img_bgr.shape[:2]

    from nlmclean.detect.template import match_template  # deferred: loads template assets

    best: tuple[Region, float, str] | None = None
    for profile in profiles_for(kind):
        match = match_template(img_bgr, profile)
        if match is not None and (best is None or match[1] > best[1]):
            best = (match[0], match[1], profile.name)
    if best is not None:
        return best

    fallback = HEURISTIC_PROFILE[kind]
    return heuristic_region(w, h, fallback), HEURISTIC_CONFIDENCE, fallback
