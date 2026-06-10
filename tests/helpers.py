from __future__ import annotations

import numpy as np

from tests.make_fixtures import mark_rect


def diff_in_and_out(
    original: np.ndarray, cleaned: np.ndarray, kind: str, halo: int = 12
) -> tuple[float, float]:
    """Mean abs diff (inside mark rect, outside mark rect + halo)."""
    assert original.shape == cleaned.shape
    h, w = original.shape[:2]
    x, y, mw, mh = mark_rect(w, h, kind)
    diff = np.abs(original.astype(np.int16) - cleaned.astype(np.int16)).mean(axis=2)

    inside = float(diff[y : y + mh, x : x + mw].mean())
    masked = diff.copy()
    x0, y0 = max(0, x - halo), max(0, y - halo)
    masked[y0 : y + mh + halo, x0 : x + mw + halo] = 0
    outside = float(masked.mean())
    return inside, outside


def assert_watermark_removed(
    original: np.ndarray,
    cleaned: np.ndarray,
    kind: str,
    *,
    min_inside: float = 15.0,
    max_outside: float = 4.0,
) -> None:
    inside, outside = diff_in_and_out(original, cleaned, kind)
    assert inside > min_inside, f"watermark region barely changed (diff {inside:.1f})"
    assert outside < max_outside, f"content outside watermark changed (diff {outside:.1f})"
