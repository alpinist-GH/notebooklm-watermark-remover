"""GUI smoke tests - run headless via QT_QPA_PLATFORM=offscreen (set in CI)."""

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytest.importorskip("PySide6")

from nlmclean.gui.file_table import DONE, READY  # noqa: E402
from nlmclean.gui.main_window import MainWindow  # noqa: E402


@pytest.fixture()
def window(qtbot, tmp_path):
    # keep QSettings out of the real registry and isolated per test
    from PySide6.QtCore import QCoreApplication, QSettings

    QCoreApplication.setOrganizationName("nlmclean-test")
    QCoreApplication.setApplicationName("nlmclean-test")
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "settings")
    )
    win = MainWindow()
    qtbot.addWidget(win)
    return win


def test_add_and_process_image(window, qtbot, image_file, tmp_path):
    window.output_dir = tmp_path
    window.add_files([image_file])
    assert len(window.model.items) == 1
    item = window.model.items[0]
    assert item.kind == "image"
    # the Output column shows the destination before processing starts
    assert item.planned_dst == tmp_path / "slide_clean.png"

    qtbot.waitUntil(lambda: item.status == READY, timeout=15000)
    assert item.region is not None
    assert item.confidence > 0

    window._start_all()
    qtbot.waitUntil(lambda: item.status == DONE, timeout=30000)
    assert item.dst == item.planned_dst and item.dst.exists()


def test_output_column_defaults_next_to_source(window, image_file):
    from PySide6.QtCore import Qt

    from nlmclean.gui.file_table import COL_OUTPUT

    window.add_files([image_file])
    item = window.model.items[0]
    assert item.planned_dst == image_file.parent / "slide_clean.png"
    shown = window.model.data(window.model.index(0, COL_OUTPUT), Qt.DisplayRole)
    assert shown == str(item.planned_dst)


def test_unsupported_and_duplicate_files_ignored(window, image_file, tmp_path):
    bogus = tmp_path / "notes.txt"
    bogus.write_text("hello")
    window.add_files([bogus, image_file, image_file])
    assert len(window.model.items) == 1


def test_remove_selected_rows(window, qtbot, image_file, pdf_file):
    window.add_files([image_file, pdf_file])
    assert len(window.model.items) == 2
    window.table.selectRow(0)
    window._remove_selected()
    assert len(window.model.items) == 1
    assert window.model.items[0].path == pdf_file
    window.table.selectRow(0)
    window._remove_selected()
    assert not window.model.items
    assert window.stack.currentWidget() is window.drop_zone


def test_settings_dialog_roundtrip(window, qtbot, tmp_path):
    from nlmclean.gui.settings_dialog import SettingsDialog

    dialog = SettingsDialog(window)
    qtbot.addWidget(dialog)
    dialog.mode_combo.setCurrentIndex(1)  # quality
    dialog.strip_metadata_check.setChecked(True)
    dialog.detect_combo.setCurrentIndex(1)  # universal
    dialog.accept()

    assert window.settings.value("mode") == "quality"
    assert window.settings.value("strip_metadata", False, bool) is True
    assert window.settings.value("detect_mode") == "universal"

    reopened = SettingsDialog(window)
    qtbot.addWidget(reopened)
    assert reopened.mode_combo.currentData() == "quality"
    assert reopened.strip_metadata_check.isChecked()
    assert reopened.detect_combo.currentData() == "universal"


def test_finished_file_lands_in_output_window(window, qtbot, image_file, tmp_path):
    window.output_dir = tmp_path
    window.add_files([image_file])
    item = window.model.items[0]
    qtbot.waitUntil(lambda: item.status == READY, timeout=15000)
    window._start_all()
    qtbot.waitUntil(lambda: item.status == DONE, timeout=30000)

    win = window.output_win
    assert win is not None
    assert win.list.count() == 1
    from PySide6.QtCore import Qt

    assert win.list.item(0).data(Qt.UserRole) == str(item.dst)
    # re-finishing the same path must not duplicate the entry
    win.add_output(item.dst)
    assert win.list.count() == 1
    win.shutdown()


def test_output_window_docks_beside_input(window, qtbot):
    window.show()
    qtbot.waitExposed(window)
    win = window._output_window()
    window._show_output_beside(win)
    assert win.docked
    assert win.x() == window.frameGeometry().right() + 1
    assert win.y() == window.frameGeometry().top()
    assert win.height() == window.height()

    # the output window follows when the input window moves
    window.move(window.x() + 40, window.y() + 25)
    assert win.x() == window.frameGeometry().right() + 1
    assert win.y() == window.frameGeometry().top()

    # dragging the output window away undocks it: it stops following
    win.move(win.x() + 120, win.y())
    assert not win.docked
    parked = win.pos()
    window.move(window.x() - 40, window.y())
    assert win.pos() == parked
    win.shutdown()


def test_media_preview_renders_image(qtbot, image_file):
    from nlmclean.gui.media_preview import MediaPreview

    preview = MediaPreview()
    qtbot.addWidget(preview)
    preview.resize(400, 300)
    preview.show_file(image_file)
    assert preview._stack.currentIndex() == 1  # image page
    assert preview._image_label.pixmap() is not None
    preview.clear()
    assert preview._stack.currentIndex() == 0  # placeholder


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
