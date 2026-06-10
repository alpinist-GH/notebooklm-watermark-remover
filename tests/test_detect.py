from nlmclean.detect import detect_region
from tests.make_fixtures import draw_slide, mark_rect


def _contains(region, rect) -> bool:
    x, y, w, h = rect
    return region.x <= x and region.y <= y and region.x + region.w >= x + w


def test_detects_doc_mark():
    img = draw_slide(kind="doc")
    region, conf = detect_region(img, "doc")
    assert conf > 0
    assert _contains(region, mark_rect(img.shape[1], img.shape[0], "doc"))


def test_detects_video_mark():
    img = draw_slide(kind="video")
    region, _ = detect_region(img, "video")
    assert _contains(region, mark_rect(img.shape[1], img.shape[0], "video"))


def test_scales_with_resolution():
    img = draw_slide(2940, 1912, kind="doc")  # 2x reference size
    region, _ = detect_region(img, "doc")
    assert _contains(region, mark_rect(2940, 1912, "doc"))
