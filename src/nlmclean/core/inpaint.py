"""Shared OpenCV inpainting helpers used by every format handler."""

from __future__ import annotations

import cv2
import numpy as np

from nlmclean.core.region import Region

INPAINT_RADIUS = 5


def inpaint_region(img: np.ndarray, region: Region, method: str = "telea") -> np.ndarray:
    """Return a copy of `img` with `region` reconstructed from its surroundings.

    Inpainting runs on a crop with a halo around the region rather than the full
    frame - cv2.inpaint cost scales with image area, not mask area.
    """
    h, w = img.shape[:2]
    r = region.clamped(w, h)

    halo = max(INPAINT_RADIUS * 3, 16)
    crop_rect = r.padded(halo).clamped(w, h)
    crop = img[crop_rect.y : crop_rect.y + crop_rect.h, crop_rect.x : crop_rect.x + crop_rect.w]

    mask = np.zeros(crop.shape[:2], dtype=np.uint8)
    mx, my = r.x - crop_rect.x, r.y - crop_rect.y
    mask[my : my + r.h, mx : mx + r.w] = 255

    flags = cv2.INPAINT_TELEA if method == "telea" else cv2.INPAINT_NS
    patched = cv2.inpaint(crop, mask, INPAINT_RADIUS, flags)

    out = img.copy()
    out[crop_rect.y : crop_rect.y + crop_rect.h, crop_rect.x : crop_rect.x + crop_rect.w] = patched
    return out


def inpaint_roi(roi: np.ndarray, method: str = "telea") -> np.ndarray:
    """Inpaint the interior of an ROI crop whose border pixels are clean context.

    Used by the video quality pipeline: the ROI is the detected region plus a halo;
    everything except the outermost halo ring is masked for reconstruction.
    """
    mask = np.full(roi.shape[:2], 255, dtype=np.uint8)
    ring = max(2, INPAINT_RADIUS)
    mask[:ring, :] = 0
    mask[-ring:, :] = 0
    mask[:, :ring] = 0
    mask[:, -ring:] = 0
    flags = cv2.INPAINT_TELEA if method == "telea" else cv2.INPAINT_NS
    return cv2.inpaint(roi, mask, INPAINT_RADIUS, flags)
