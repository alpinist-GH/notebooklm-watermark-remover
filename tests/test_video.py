import pytest

from nlmclean.core.imgio import imdecode_bytes
from nlmclean.core.job import Job
from nlmclean.core.video import clean_video
from nlmclean.ffmpeg.probe import probe
from nlmclean.ffmpeg.runner import extract_frame
from tests.helpers import diff_in_and_out


@pytest.mark.parametrize("mode", ["fast", "quality"])
def test_clean_video(video_file, tmp_path, mode):
    dst = tmp_path / f"overview_{mode}.mp4"
    clean_video(Job(src=video_file, dst=dst, mode=mode))
    assert dst.exists()

    src_info = probe(video_file)
    out_info = probe(dst)
    assert out_info.has_audio, "audio track must survive"
    assert abs(out_info.duration - src_info.duration) < 0.5
    assert (out_info.width, out_info.height) == (src_info.width, src_info.height)

    # sample a frame from each slide and check the corner was cleaned
    for t in (0.5, 1.5):
        before = imdecode_bytes(extract_frame(video_file, t))
        after = imdecode_bytes(extract_frame(dst, t))
        inside, outside = diff_in_and_out(before, after, "video", halo=16)
        assert inside > 10.0, f"watermark not removed at t={t} (diff {inside:.1f})"
        assert outside < 8.0, f"frame damaged outside watermark at t={t} (diff {outside:.1f})"
