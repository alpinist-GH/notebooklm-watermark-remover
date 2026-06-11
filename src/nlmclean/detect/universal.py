"""Universal static-watermark detection for video - no template required.

A burned-in watermark is the only thing in a video that never moves: sample
frames across the whole duration, and watermark pixels are those that are
temporally static (low per-pixel std) while also being structured (high edge
energy in the temporal median). Moving content fails the static test; flat
static backgrounds fail the edge test.

Known limits (callers surface these to the user): near-static footage gives
no temporal signal, animated/moving watermarks are not static, and marks over
a constant-color area are indistinguishable from background. The manual
region selector remains the fallback for all of those.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from nlmclean.core.imgio import imdecode_bytes
from nlmclean.core.region import Region
from nlmclean.ffmpeg.probe import VideoInfo
from nlmclean.ffmpeg.runner import extract_frame

_SAMPLES = 16
# below this mean temporal std (gray levels) the video barely moves and
# "static" stops being a useful signal - bail out with low confidence
_MIN_MOTION = 3.0
# a pixel counts as static when its std is well below the frame average
_STATIC_FRACTION = 0.35
_MIN_COMPONENT_PX = 40  # specks below this are noise
_MAX_AREA_FRACTION = 0.20  # bigger blobs are scenery, not a watermark
_PAD = 6
_KERNEL3 = np.ones((3, 3), np.uint8)


def _sample_gray_frames(src: Path, info: VideoInfo) -> list[np.ndarray]:
    times = (
        [info.duration * (i + 0.5) / _SAMPLES for i in range(_SAMPLES)]
        if info.duration
        else [0.0]
    )
    frames = []
    for t in times:
        try:
            frame = imdecode_bytes(extract_frame(src, t))
        except Exception:
            continue
        frames.append(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY))
    return frames


def detect_static_overlay(
    src: Path, info: VideoInfo
) -> tuple[Region | None, np.ndarray | None, float]:
    """Find any static structured overlay. Returns (bbox, full-frame uint8 mask,
    confidence 0..1); (None, None, low) when nothing trustworthy was found."""
    frames = _sample_gray_frames(src, info)
    if len(frames) < 4:
        return None, None, 0.0
    stack = np.stack(frames).astype(np.float32)
    sigma = stack.std(axis=0)
    median = np.median(stack, axis=0).astype(np.uint8)

    motion = float(sigma.mean())
    if motion < _MIN_MOTION:
        return None, None, 0.2  # video too still for temporal detection

    static = sigma < _STATIC_FRACTION * motion

    # structured = strong edges in the temporal median frame
    gx = cv2.Sobel(median, cv2.CV_32F, 1, 0, ksize=3)
    gy = cv2.Sobel(median, cv2.CV_32F, 0, 1, ksize=3)
    edge = cv2.magnitude(gx, gy)
    edge_u8 = cv2.normalize(edge, None, 0, 255, cv2.NORM_MINMAX).astype(np.uint8)
    otsu, _ = cv2.threshold(edge_u8, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    structured = edge_u8 > otsu

    cand = ((static & structured) * 255).astype(np.uint8)
    cand = cv2.morphologyEx(cand, cv2.MORPH_CLOSE, _KERNEL3)

    # selectivity: a watermark is a small static island among moving edges. In a
    # slideshow most edges are static (shared page furniture) - that is page
    # content, not an overlay, and must depress confidence.
    selectivity = 1.0 - float((static & structured).sum()) / max(1, int(structured.sum()))

    h, w = cand.shape
    n, labels, stats, _cents = cv2.connectedComponentsWithStats(cand, 8)
    keep = np.zeros_like(cand)
    best_score = 0.0
    for i in range(1, n):
        x, y, cw, ch, area = stats[i]
        if area < _MIN_COMPONENT_PX or area > _MAX_AREA_FRACTION * h * w:
            continue
        if cw >= 0.9 * w or ch >= 0.9 * h:
            continue  # letterbox bars / static frame borders
        comp = labels == i
        # static-ness of the component relative to overall motion: 1 = frozen
        stillness = 1.0 - float(np.median(sigma[comp])) / motion
        if stillness <= 0.5:
            continue
        keep[comp] = 255
        best_score = max(best_score, stillness)

    if not keep.any():
        return None, None, 0.2

    ys, xs = np.nonzero(keep)
    bbox = Region(
        int(xs.min()), int(ys.min()), int(xs.max() - xs.min() + 1), int(ys.max() - ys.min() + 1)
    )
    bbox = bbox.padded(_PAD).clamped(w, h, margin=1)
    mask = cv2.dilate(keep, _KERNEL3, iterations=2)  # cover the anti-aliased fringe

    # confidence grows with how frozen the best component is, with how much the
    # rest of the frame moves (more motion = cleaner signal), and with how
    # exclusive the static signal is to this overlay
    confidence = (
        float(np.clip(best_score, 0.0, 1.0))
        * min(1.0, motion / (2 * _MIN_MOTION))
        * float(np.clip(selectivity, 0.0, 1.0))
    )
    return bbox, mask, float(np.clip(confidence, 0.0, 1.0))
