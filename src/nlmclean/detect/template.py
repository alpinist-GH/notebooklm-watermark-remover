"""Multi-scale intensity template matching for the NotebookLM watermark.

The bundled templates (assets/templates/wm_video.png, wm_doc.png) are grayscale
crops of the watermark from real exports. The mark is faint (~35 gray levels of
contrast), which defeats edge-based matching, so we correlate intensities with
TM_CCOEFF_NORMED: the mean subtraction makes it insensitive to background
brightness, and accepting negative peaks handles the polarity flip on dark
slides (where the translucent mark renders lighter than its background).
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from nlmclean.core.region import Region

ACCEPT_SCORE = 0.65
PAD = 6
# geometric scale sweep + exact 1.0: most exports match the template's native
# 720p resolution, and a faint 12px mark loses correlation at even +/-8% scale
_SCALES = np.unique(np.append(np.geomspace(0.4, 2.5, num=12), [1.0, 1.5, 2.0]))


def _assets_dir() -> Path:
    if getattr(sys, "frozen", False):  # PyInstaller bundle
        return Path(sys._MEIPASS) / "assets" / "templates"  # type: ignore[attr-defined]
    return Path(__file__).resolve().parents[3] / "assets" / "templates"


@lru_cache(maxsize=4)
def _load_template(kind: str) -> np.ndarray | None:
    path = _assets_dir() / f"wm_{kind}.png"
    if not path.exists():
        return None
    data = np.fromfile(str(path), dtype=np.uint8)
    tmpl = cv2.imdecode(data, cv2.IMREAD_GRAYSCALE)
    return tmpl


def match_template(img_bgr: np.ndarray, kind: str) -> tuple[Region, float] | None:
    tmpl = _load_template(kind)
    if tmpl is None:
        return None

    img_h, img_w = img_bgr.shape[:2]
    # watermark lives bottom-right: search only that quadrant (faster, fewer false hits)
    sx = int(img_w * 0.60)
    sy = int(img_h * 0.70)
    search = cv2.cvtColor(img_bgr[sy:, sx:], cv2.COLOR_BGR2GRAY)

    best: tuple[float, int, int, int, int] | None = None  # score, x, y, w, h
    for scale in _SCALES:
        tw = max(8, round(tmpl.shape[1] * scale))
        th = max(4, round(tmpl.shape[0] * scale))
        if tw >= search.shape[1] or th >= search.shape[0]:
            continue
        scaled = cv2.resize(tmpl, (tw, th), interpolation=cv2.INTER_AREA)
        result = cv2.matchTemplate(search, scaled, cv2.TM_CCOEFF_NORMED)
        min_v, max_v, min_loc, max_loc = cv2.minMaxLoc(result)
        # negative peak = same mark with inverted contrast (dark slide background)
        score, loc = (max_v, max_loc) if max_v >= -min_v else (-min_v, min_loc)
        if best is None or score > best[0]:
            best = (float(score), loc[0], loc[1], tw, th)

    if best is None or best[0] < ACCEPT_SCORE:
        return None

    score, x, y, w, h = best
    region = Region(sx + x, sy + y, w, h).padded(PAD).clamped(img_w, img_h)
    return region, min(1.0, score)
