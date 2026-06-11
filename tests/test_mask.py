"""Stroke-mask precision: only the watermark's own pixels may be touched."""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from nlmclean.core.inpaint import inpaint_region
from nlmclean.core.region import Region
from nlmclean.detect import template as template_mod
from nlmclean.detect.mask import stroke_mask_for_region
from tests.make_fixtures import draw_slide, mark_rect, mark_stroke_mask

W, H = 1280, 720


def _template_from_fixture(w: int = W, h: int = H) -> np.ndarray:
    """Grayscale crop of the fixture's own mark - same workflow as the real asset."""
    frame = draw_slide(w, h, kind="video")
    x, y, mw, mh = mark_rect(w, h, "video")
    return cv2.cvtColor(frame[y : y + mh, x : x + mw], cv2.COLOR_BGR2GRAY)


@pytest.fixture()
def fake_template(monkeypatch):
    tmpl = _template_from_fixture()

    def load(kind: str):
        return tmpl if kind == "video" else None

    monkeypatch.setattr(template_mod, "_load_template", load)
    return tmpl


def _detected_region(w: int, h: int) -> Region:
    x, y, mw, mh = mark_rect(w, h, "video")
    return Region(x, y, mw, mh).padded(8).clamped(w, h)


def test_no_template_returns_none(fake_template):
    frame = draw_slide(W, H, kind="doc")
    assert stroke_mask_for_region(frame, _detected_region(W, H), "doc") is None


def test_mask_aligns_to_strokes(fake_template):
    frame = draw_slide(W, H, kind="video")
    region = _detected_region(W, H)
    mask = stroke_mask_for_region(frame, region, "video")
    assert mask is not None

    gt = mark_stroke_mask(W, H, "video")
    gt_crop = gt[region.y : region.y + region.h, region.x : region.x + region.w]
    covered = ((mask > 0) & (gt_crop > 0)).sum() / max(1, (gt_crop > 0).sum())
    assert covered > 0.99, f"mask misses {1 - covered:.1%} of the strokes"
    # no stray pixels far from the strokes (mask itself is 1px dilated)
    far = cv2.dilate(gt_crop, np.ones((9, 9), np.uint8)) == 0
    assert ((mask > 0) & far).sum() == 0, "mask has pixels far outside the strokes"


def test_mask_aligns_at_other_resolution(fake_template):
    w, h = 1470, 956
    frame = draw_slide(w, h, kind="video")
    region = _detected_region(w, h)
    mask = stroke_mask_for_region(frame, region, "video")
    assert mask is not None

    gt = mark_stroke_mask(w, h, "video")
    gt_crop = gt[region.y : region.y + region.h, region.x : region.x + region.w]
    covered = ((mask > 0) & (gt_crop > 0)).sum() / max(1, (gt_crop > 0).sum())
    assert covered > 0.90, f"mask misses {1 - covered:.1%} of the strokes at 1470px"


def test_unalignable_region_returns_none(fake_template):
    frame = draw_slide(W, H, kind="video", mark=False)
    assert stroke_mask_for_region(frame, _detected_region(W, H), "video") is None


def test_masked_inpaint_touches_only_strokes(fake_template):
    frame = draw_slide(W, H, kind="video")
    region = _detected_region(W, H)
    mask = stroke_mask_for_region(frame, region, "video")
    cleaned = inpaint_region(frame, region, mask=mask)

    gt = mark_stroke_mask(W, H, "video")
    diff = np.abs(frame.astype(np.int16) - cleaned.astype(np.int16)).max(axis=2)
    on = float(diff[gt > 0].mean())
    assert on > 30.0, f"strokes barely changed (diff {on:.1f})"
    # everything beyond the mask's 1px dilation must be bit-identical
    fringe = cv2.dilate(gt, np.ones((5, 5), np.uint8))
    assert int(diff[fringe == 0].max()) == 0, "pixels outside the strokes were modified"
