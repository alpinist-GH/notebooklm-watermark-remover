from __future__ import annotations

import pytest

from nlmclean.ffmpeg.locate import find_ffmpeg
from tests import make_fixtures

requires_ffmpeg = pytest.mark.skipif(find_ffmpeg() is None, reason="ffmpeg not available")


@pytest.fixture(scope="session")
def ffmpeg_exe() -> str:
    exe = find_ffmpeg()
    if exe is None:
        pytest.skip("ffmpeg not available")
    return exe


@pytest.fixture()
def image_file(tmp_path):
    path = tmp_path / "slide.png"
    make_fixtures.make_image(path)
    return path


@pytest.fixture()
def pdf_file(tmp_path):
    path = tmp_path / "deck.pdf"
    make_fixtures.make_pdf(path, n_pages=2)
    return path


@pytest.fixture()
def pptx_file(tmp_path):
    path = tmp_path / "deck.pptx"
    make_fixtures.make_pptx(path, n_slides=3)
    return path


@pytest.fixture(scope="session")
def video_file(tmp_path_factory, ffmpeg_exe):
    path = tmp_path_factory.mktemp("video") / "overview.mp4"
    make_fixtures.make_video(path, ffmpeg_exe)
    return path
