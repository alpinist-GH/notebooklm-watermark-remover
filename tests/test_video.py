import pytest

from nlmclean.core.imgio import imdecode_bytes
from nlmclean.core.job import Job
from nlmclean.core.video import clean_video
from nlmclean.detect import template as template_mod
from nlmclean.ffmpeg.probe import probe
from nlmclean.ffmpeg.runner import extract_frame
from tests.helpers import diff_in_and_out, stroke_diff
from tests.make_fixtures import REF_H, REF_W


def test_probe_stderr_fallback(video_file, ffmpeg_exe):
    """Release bundles ship no ffprobe - the `ffmpeg -i` stderr parser must work."""
    from nlmclean.ffmpeg.probe import _probe_ffmpeg_stderr

    info = _probe_ffmpeg_stderr(ffmpeg_exe, video_file)
    assert (info.width, info.height) == (1470, 956)
    assert info.has_audio
    assert abs(info.duration - 2.0) < 0.3
    assert info.fps > 0


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


@pytest.mark.parametrize("mode", ["fast", "quality"])
def test_clean_video_strokes_only(video_file, tmp_path, monkeypatch, mode):
    """With an aligned template the cleanup must touch only the watermark strokes."""
    from tests.test_mask import _template_from_fixture

    tmpl = _template_from_fixture(REF_W, REF_H)
    monkeypatch.setattr(
        template_mod, "_load_template", lambda kind: tmpl if kind == "video" else None
    )

    dst = tmp_path / f"strokes_{mode}.mp4"
    clean_video(Job(src=video_file, dst=dst, mode=mode))

    for t in (0.5, 1.5):
        before = imdecode_bytes(extract_frame(video_file, t))
        after = imdecode_bytes(extract_frame(dst, t))
        on, off = stroke_diff(before, after, "video", fringe=6)
        assert on > 40.0, f"strokes not removed at t={t} (diff {on:.1f})"
        # off-stroke pixels (including inside the old rectangle) = codec noise only
        assert off < 4.0, f"bleeding outside strokes at t={t} (diff {off:.1f})"
