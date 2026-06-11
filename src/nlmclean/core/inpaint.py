"""Shared OpenCV inpainting helpers used by every format handler."""

from __future__ import annotations

import cv2
import numpy as np

from nlmclean.core.region import Region

INPAINT_RADIUS = 5
STROKE_RADIUS = 3  # stroke masks are thin - nearby context is all that's needed


def inpaint_region(
    img: np.ndarray, region: Region, method: str = "telea", mask: np.ndarray | None = None
) -> np.ndarray:
    """Return a copy of `img` with `region` reconstructed from its surroundings.

    With `mask` (region-sized, 255 = watermark stroke) only the masked pixels are
    rebuilt and everything else in the region stays bit-identical; without it the
    whole rectangle is reconstructed. Inpainting runs on a crop with a halo around
    the region rather than the full frame - cv2.inpaint cost scales with image
    area, not mask area.
    """
    h, w = img.shape[:2]
    r = region.clamped(w, h)

    radius = INPAINT_RADIUS if mask is None else STROKE_RADIUS
    halo = max(radius * 3, 16)
    crop_rect = r.padded(halo).clamped(w, h)
    crop = img[crop_rect.y : crop_rect.y + crop_rect.h, crop_rect.x : crop_rect.x + crop_rect.w]

    crop_mask = np.zeros(crop.shape[:2], dtype=np.uint8)
    mx, my = r.x - crop_rect.x, r.y - crop_rect.y
    if mask is None:
        crop_mask[my : my + r.h, mx : mx + r.w] = 255
    else:
        mh = min(r.h, mask.shape[0])
        mw = min(r.w, mask.shape[1])
        crop_mask[my : my + mh, mx : mx + mw] = mask[:mh, :mw]

    flags = cv2.INPAINT_TELEA if method == "telea" else cv2.INPAINT_NS
    patched = cv2.inpaint(crop, crop_mask, radius, flags)

    out = img.copy()
    out[crop_rect.y : crop_rect.y + crop_rect.h, crop_rect.x : crop_rect.x + crop_rect.w] = patched
    return out


def inpaint_roi(
    roi: np.ndarray, method: str = "telea", mask: np.ndarray | None = None
) -> np.ndarray:
    """Inpaint the interior of an ROI crop whose border pixels are clean context.

    Used by the video quality pipeline: the ROI is the detected region plus a halo.
    With `mask` (ROI-sized, 255 = watermark stroke) only the stroke pixels are
    rebuilt; without it everything except the outermost halo ring is reconstructed.
    """
    if mask is None:
        radius = INPAINT_RADIUS
        mask = np.full(roi.shape[:2], 255, dtype=np.uint8)
        ring = max(2, INPAINT_RADIUS)
        mask[:ring, :] = 0
        mask[-ring:, :] = 0
        mask[:, :ring] = 0
        mask[:, -ring:] = 0
    else:
        radius = STROKE_RADIUS
    flags = cv2.INPAINT_TELEA if method == "telea" else cv2.INPAINT_NS
    return cv2.inpaint(roi, mask, radius, flags)
