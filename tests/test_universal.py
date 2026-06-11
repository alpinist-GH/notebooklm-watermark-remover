"""Universal (template-free) static-watermark detection on video."""

import numpy as np
import pytest

from nlmclean.core.imgio import imdecode_bytes
from nlmclean.core.job import Job
from nlmclean.core.video import clean_video
from nlmclean.detect.universal import detect_static_overlay
from nlmclean.ffmpeg.probe import probe
from nlmclean.ffmpeg.runner import extract_frame
from tests.make_fixtures import make_universal_video


@pytest.fixture(scope="module")
def universal_video(tmp_path_factory, ffmpeg_exe):
    path = tmp_path_factory.mktemp("universal") / "clip.mp4"
    rect = make_universal_video(path, ffmpeg_exe)
    return path, rect


def test_finds_static_overlay_anywhere(universal_video):
    path, (x, y, w, h) = universal_video
    region, mask, conf = detect_static_overlay(path, probe(path))
    assert region is not None and mask is not None
    assert conf >= 0.5
    # detected bbox must cover the drawn overlay (with some slack)
    assert region.x <= x + 8 and region.y <= y + 8
    assert region.x + region.w >= x + w - 8
    assert region.y + region.h >= y + h - 8
    # and the mask should mark a sensible number of overlay pixels
    assert (mask > 0).sum() > 200


def test_static_video_refuses(video_file):
    # the NLM fixture is two still slides: almost no temporal signal
    _region, _mask, conf = detect_static_overlay(video_file, probe(video_file))
    assert conf < 0.5


def test_clean_video_universal_mode(universal_video, tmp_path):
    path, (x, y, w, h) = universal_video
    dst = tmp_path / "clip_clean.mp4"
    clean_video(Job(src=path, dst=dst, mode="fast", detect="universal"))
    assert dst.exists()

    before = imdecode_bytes(extract_frame(path, 1.5))
    after = imdecode_bytes(extract_frame(dst, 1.5))
    inside_before = before[y : y + h, x : x + w].astype(int)
    inside_after = after[y : y + h, x : x + w].astype(int)
    # the bright overlay must be gone (big change inside the rect)
    assert np.abs(inside_after - inside_before).mean() > 15
    # the gradient outside is untouched up to codec noise
    outside = np.abs(after[:, x + w + 40 :].astype(int) - before[:, x + w + 40 :].astype(int))
    assert outside.mean() < 6


def test_universal_mode_with_explicit_region_errors_never(universal_video, tmp_path):
    from nlmclean.core.region import Region

    path, (x, y, w, h) = universal_video
    dst = tmp_path / "clip_manual.mp4"
    clean_video(
        Job(
            src=path,
            dst=dst,
            mode="fast",
            detect="universal",
            region=Region(x - 4, y - 4, w + 8, h + 8),
        )
    )
    assert dst.exists()
