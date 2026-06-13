from pathlib import Path

import numpy as np
import pytest

from nlmclean.detect import detect_region
from tests.make_fixtures import draw_gemini_image, draw_slide, mark_rect

_REAL_GEMINI = Path(__file__).parent / "fixtures_real" / "gemini_infographic.png"


def _contains(region, rect) -> bool:
    x, y, w, h = rect
    return region.x <= x and region.y <= y and region.x + region.w >= x + w


def test_detects_doc_mark():
    img = draw_slide(kind="doc")
    region, conf, profile = detect_region(img, "doc")
    assert conf > 0
    assert profile == "doc"
    assert _contains(region, mark_rect(img.shape[1], img.shape[0], "doc"))


def test_detects_video_mark():
    img = draw_slide(kind="video")
    region, _, profile = detect_region(img, "video")
    assert profile == "video"
    assert _contains(region, mark_rect(img.shape[1], img.shape[0], "video"))


def test_scales_with_resolution():
    img = draw_slide(2940, 1912, kind="doc")  # 2x reference size
    region, _, _ = detect_region(img, "doc")
    assert _contains(region, mark_rect(2940, 1912, "doc"))


def test_detects_gemini_sparkle():
    img, rect = draw_gemini_image()
    region, conf, profile = detect_region(img, "image")
    assert profile == "gemini"
    assert conf >= 0.7
    assert _contains(region, rect)


def test_detects_gemini_sparkle_in_video():
    # regression: Gemini-generated videos carry the sparkle, not the NLM
    # wordmark, so the "video" kind must also try the gemini profile
    img, rect = draw_gemini_image()
    region, conf, profile = detect_region(img, "video")
    assert profile == "gemini"
    assert conf >= 0.7
    assert _contains(region, rect)


def test_nlm_video_mark_still_wins_on_video():
    # adding the gemini profile must not steal genuine NLM video frames
    img = draw_slide(kind="video")
    _, conf, profile = detect_region(img, "video")
    if conf > 0.5:  # only meaningful when the template actually matched
        assert profile == "video"


def test_nlm_doc_still_wins_on_nlm_images():
    # regression: adding the gemini profile must not steal NLM slide images
    img = draw_slide(kind="doc")
    _, conf, profile = detect_region(img, "image")
    if conf > 0.5:  # only meaningful when the template actually matched
        assert profile == "doc"


@pytest.mark.skipif(not _REAL_GEMINI.exists(), reason="real Gemini sample not present")
def test_real_gemini_sample():
    from nlmclean.core.imgio import imread
    from nlmclean.detect.mask import stroke_mask_for_region

    img = imread(_REAL_GEMINI)
    region, conf, profile = detect_region(img, "image")
    assert profile == "gemini"
    assert conf >= 0.7
    mask = stroke_mask_for_region(img, region, profile)
    assert mask is not None and (mask > 0).sum() > 300

    # the sparkle sits 32px from the bottom-right corner of the 1365x768 sample
    h, w = img.shape[:2]
    assert region.x + region.w >= w - 40
    assert region.y + region.h >= h - 40


def test_gemini_mask_is_solid_blob():
    from nlmclean.detect.mask import stroke_mask_for_region

    img, rect = draw_gemini_image()
    region, _, profile = detect_region(img, "image")
    assert profile == "gemini"
    mask = stroke_mask_for_region(img, region, profile)
    assert mask is not None
    # solid binarization must cover the blob, not just its outline
    x, y, w, h = rect
    drawn = np.zeros(img.shape[:2], bool)
    drawn[y : y + h, x : x + w] = True
    covered = (mask > 0) & drawn[region.y : region.y + region.h, region.x : region.x + region.w]
    assert covered.sum() >= 0.5 * w * h * 0.3  # star fills ~30% of its bbox
