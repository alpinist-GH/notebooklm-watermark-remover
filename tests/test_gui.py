"""GUI smoke tests - run headless via QT_QPA_PLATFORM=offscreen (set in CI)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from nlmclean.gui.file_table import DONE, READY  # noqa: E402
from nlmclean.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture()
def window(qtbot):
    win = MainWindow()
    qtbot.addWidget(win)
    return win


def test_add_and_process_image(window, qtbot, image_file, tmp_path):
    window.output_dir = tmp_path
    window.add_files([image_file])
    assert len(window.model.items) == 1
    item = window.model.items[0]
    assert item.kind == "image"

    qtbot.waitUntil(lambda: item.status == READY, timeout=15000)
    assert item.region is not None
    assert item.confidence > 0

    window._start_all()
    qtbot.waitUntil(lambda: item.status == DONE, timeout=30000)
    assert item.dst is not None and item.dst.exists()


def test_unsupported_and_duplicate_files_ignored(window, image_file, tmp_path):
    bogus = tmp_path / "notes.txt"
    bogus.write_text("hello")
    window.add_files([bogus, image_file, image_file])
    assert len(window.model.items) == 1


def test_manual_region_scales_to_job_coords(window, qtbot, pdf_file):
    from nlmclean.core.region import Region

    window.add_files([pdf_file])
    item = window.model.items[0]
    qtbot.waitUntil(lambda: item.status == READY, timeout=15000)

    # PDF preview is rendered at 2x: a manual rect on it must be halved for the job
    item.region = Region(200, 100, 80, 40)
    item.region_is_manual = True
    assert item.region_scale == 0.5
    assert item.job_region() == Region(100, 50, 40, 20)
