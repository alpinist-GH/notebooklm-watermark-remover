"""Pixel-precise watermark stroke masks.

The watermark is a constant overlay - the same pixels in every frame - so
instead of reconstructing the whole detected rectangle we can rebuild only the
~750 stroke pixels of the wordmark itself. Binarizing the bundled template
gives the stroke footprint; re-aligning the template inside the detected (or
manually drawn) region pins it to exact pixel positions. Everything outside
the strokes is left untouched.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from nlmclean.core.imgio import imdecode_bytes
from nlmclean.core.region import Region
from nlmclean.detect import template as _template
from nlmclean.ffmpeg.probe import VideoInfo
from nlmclean.ffmpeg.runner import extract_frame

ALIGN_SCORE = 0.5
_STROKE_DELTA = 8  # gray levels from the template's background mode
_KERNEL3 = np.ones((3, 3), np.uint8)
_REFINE_SAMPLES = 15
_REFINE_DELTA = 4.0  # mean gray-level deviation that marks a pixel as stroke


def _binarize_template(tmpl: np.ndarray) -> np.ndarray:
    """255 where the template deviates from a local background estimate.

    The wordmark is thin strokes whose polarity depends on the export theme
    (dark on light slides, light on dark ones). Grayscale closing erases dark
    strokes, opening erases light ones; whichever direction deviates more is
    the stroke polarity - robust to gradients and to dense glyph spacing.
    """
    kernel = np.ones((7, 7), np.uint8)
    t = tmpl.astype(np.int16)
    dark = cv2.morphologyEx(tmpl, cv2.MORPH_CLOSE, kernel).astype(np.int16) - t
    light = t - cv2.morphologyEx(tmpl, cv2.MORPH_OPEN, kernel).astype(np.int16)
    dev = dark if dark.clip(min=0).sum() >= light.clip(min=0).sum() else light
    return ((dev > _STROKE_DELTA) * 255).astype(np.uint8)


def _align(crop_gray: np.ndarray, tmpl: np.ndarray) -> tuple[float, int, int, int, int] | None:
    """Best (score, x, y, w, h) placement of the template inside the region crop."""
    ch, cw = crop_gray.shape[:2]
    # the region was sized from the same template (plus padding), so the right
    # scale is at or just below crop_w / tmpl_w; exact 1.0/1.5/2.0 match most
    # exports outright (see template.py)
    base = cw / tmpl.shape[1]
    scales = {round(base * f, 4) for f in np.geomspace(0.55, 1.0, num=7)}
    scales |= {1.0, 1.5, 2.0}

    best: tuple[float, int, int, int, int] | None = None
    for scale in sorted(scales):
        tw = round(tmpl.shape[1] * scale)
        th = round(tmpl.shape[0] * scale)
        if tw < 8 or th < 4 or tw > cw or th > ch:
            continue
        scaled = cv2.resize(tmpl, (tw, th), interpolation=cv2.INTER_AREA)
        result = cv2.matchTemplate(crop_gray, scaled, cv2.TM_CCOEFF_NORMED)
        min_v, max_v, min_loc, max_loc = cv2.minMaxLoc(result)
        # negative peak = same mark with inverted contrast (dark background)
        score, loc = (max_v, max_loc) if max_v >= -min_v else (-min_v, min_loc)
        if best is None or score > best[0]:
            best = (float(score), loc[0], loc[1], tw, th)
    return best


def stroke_mask_for_region(img_bgr: np.ndarray, region: Region, kind: str) -> np.ndarray | None:
    """Region-sized uint8 mask (255 = watermark stroke), or None if the template
    is missing or cannot be confidently aligned inside the region."""
    tmpl = _template._load_template(kind)
    if tmpl is None:
        return None
    h, w = img_bgr.shape[:2]
    r = region.clamped(w, h)
    crop = cv2.cvtColor(img_bgr[r.y : r.y + r.h, r.x : r.x + r.w], cv2.COLOR_BGR2GRAY)

    hit = _align(crop, tmpl)
    if hit is None or hit[0] < ALIGN_SCORE:
        return None
    _score, x, y, tw, th = hit

    strokes = _binarize_template(tmpl)
    scaled = cv2.resize(strokes, (tw, th), interpolation=cv2.INTER_AREA)
    scaled = ((scaled > 64) * 255).astype(np.uint8)
    mask = np.zeros((r.h, r.w), np.uint8)
    mask[y : y + th, x : x + tw] = scaled
    # 1px dilation covers the anti-aliased fringe of the strokes
    return cv2.dilate(mask, _KERNEL3)


def refine_mask_temporal(
    src: Path, info: VideoInfo, region: Region, base_mask: np.ndarray
) -> np.ndarray:
    """Sharpen the template mask using the video itself: the mark is identical in
    every frame, so pixels that consistently deviate from a per-frame background
    estimate are stroke pixels - this absorbs sub-pixel placement/scale drift."""
    times = (
        [info.duration * (i + 0.5) / _REFINE_SAMPLES for i in range(_REFINE_SAMPLES)]
        if info.duration
        else [0.0]
    )
    bg_mask = cv2.dilate(base_mask, _KERNEL3, iterations=2)
    acc = np.zeros(base_mask.shape, np.float64)
    n = 0
    for t in times:
        try:
            frame = imdecode_bytes(extract_frame(src, t))
        except Exception:
            continue
        crop = frame[region.y : region.y + region.h, region.x : region.x + region.w]
        if crop.shape[:2] != base_mask.shape:
            continue
        bg_est = cv2.inpaint(crop, bg_mask, 3, cv2.INPAINT_TELEA)
        acc += np.abs(crop.astype(np.int16) - bg_est.astype(np.int16)).mean(axis=2)
        n += 1
    if n == 0:
        return base_mask

    deviates = (acc / n) > _REFINE_DELTA
    refined = (deviates & (cv2.dilate(base_mask, _KERNEL3, iterations=3) > 0)).astype(np.uint8)
    refined = cv2.dilate(refined * 255, _KERNEL3)
    # safety: a refined mask that lost most of the template strokes means the
    # background estimate was unreliable - keep the template mask
    if refined.sum() < 0.5 * base_mask.sum():
        return base_mask
    return refined
