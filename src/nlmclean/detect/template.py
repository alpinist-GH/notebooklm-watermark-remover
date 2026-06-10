"""Multi-scale, edge-based template matching for the NotebookLM watermark.

The bundled templates (assets/templates/wm_video.png, wm_doc.png) are grayscale
crops of the watermark from real exports. Matching runs on Canny edge maps so
the slide's background color or gradient doesn't affect the score.
"""

from __future__ import annotations

import sys
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from nlmclean.core.region import Region

ACCEPT_SCORE = 0.55
PAD = 6
# geometric scale sweep: template may be rendered larger/smaller than our crop
_SCALES = np.geomspace(0.4, 2.5, num=12)


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


def _edges(gray: np.ndarray) -> np.ndarray:
    return cv2.Canny(gray, 50, 150)


def match_template(img_bgr: np.ndarray, kind: str) -> tuple[Region, float] | None:
    tmpl = _load_template(kind)
    if tmpl is None:
        return None

    img_h, img_w = img_bgr.shape[:2]
    # watermark lives bottom-right: search only that quadrant (faster, fewer false hits)
    sx = int(img_w * 0.60)
    sy = int(img_h * 0.70)
    search = cv2.cvtColor(img_bgr[sy:, sx:], cv2.COLOR_BGR2GRAY)
    search_edges = _edges(search)

    best: tuple[float, int, int, int, int] | None = None  # score, x, y, w, h
    for scale in _SCALES:
        tw = max(8, round(tmpl.shape[1] * scale))
        th = max(4, round(tmpl.shape[0] * scale))
        if tw >= search.shape[1] or th >= search.shape[0]:
            continue
        scaled = cv2.resize(tmpl, (tw, th), interpolation=cv2.INTER_AREA)
        result = cv2.matchTemplate(search_edges, _edges(scaled), cv2.TM_CCOEFF_NORMED)
        _, score, _, loc = cv2.minMaxLoc(result)
        if best is None or score > best[0]:
            best = (float(score), loc[0], loc[1], tw, th)

    if best is None or best[0] < ACCEPT_SCORE:
        return None

    score, x, y, w, h = best
    region = Region(sx + x, sy + y, w, h).padded(PAD).clamped(img_w, img_h)
    return region, min(1.0, score)
