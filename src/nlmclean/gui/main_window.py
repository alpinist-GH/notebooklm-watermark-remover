"""Main window: drag-and-drop batch list with per-file progress."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThreadPool
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QStackedWidget,
    QStyle,
    QTableView,
    QToolBar,
)

from nlmclean import __version__
from nlmclean.core.dispatch import SUPPORTED_EXTS, default_output, kind_of
from nlmclean.core.job import CancelToken, Job
from nlmclean.ffmpeg.locate import ffmpeg_version
from nlmclean.gui.file_table import (
    CANCELLED,
    COL_OUTPUT,
    COL_PROGRESS,
    DETECTING,
    DONE,
    FAILED,
    PROCESSING,
    READY,
    FileItem,
    FileTableModel,
    ProgressDelegate,
)
from nlmclean.gui.preview_dialog import PreviewDialog
from nlmclean.gui.settings_dialog import SettingsDialog
from nlmclean.gui.util import reveal_in_explorer
from nlmclean.gui.workers import DetectWorker, ProcessWorker, WorkerSignals

_FILTER = (
    "NotebookLM exports "
    "(*.mp4 *.mov *.m4v *.webm *.mkv *.pdf *.pptx *.png *.jpg *.jpeg *.webp)"
)

_DROP_TEXT = """
<div style='color:#888;'>
<h2 style='margin-bottom:4px;'>Drop files here</h2>
<p style='font-size:14px;'>MP4 &middot; MOV &middot; WEBM &middot; MKV &middot;
PDF &middot; PPTX &middot; PNG &middot; JPG &middot; WEBP</p>
<p style='font-size:12px;'>The watermark is detected automatically &mdash;
right-click a file to preview or adjust the region before processing.<br>
Everything is processed locally on this computer; nothing is uploaded.</p>
<p style='font-size:12px;'>or use <b>File &rsaquo; Add Files&hellip;</b> (Ctrl+O)</p>
</div>
"""


class DropZone(QLabel):
    def __init__(self) -> None:
        super().__init__(_DROP_TEXT)
        self.setTextFormat(Qt.RichText)
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            "QLabel { border: 2px dashed #888; border-radius: 12px; margin: 24px; }"
        )


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("nlmclean - NotebookLM Watermark Remover")
        self.resize(1100, 600)
        self.setAcceptDrops(True)

        # org/app names come from QApplication (set in app.py; tests redirect to a temp ini)
        self.settings = QSettings()
        self.model = FileTableModel()
        self.signals = WorkerSignals()
        self.signals.detected.connect(self._on_detected)
        self.signals.detect_failed.connect(self._on_detect_failed)
        self.signals.progress.connect(self._on_progress)
        self.signals.finished.connect(self._on_finished)
        self.pool = QThreadPool.globalInstance()
        self.output_dir: Path | None = None
        self.output_win = None  # created lazily on first finished file
        self._output_shown_once = False

        self._build_actions()
        self._build_menubar()
        self._build_toolbar()
        self._build_center()
        self._build_statusbar()
        self._restore_settings()

    # ------------------------------------------------------------- UI setup
    def _icon(self, sp: QStyle.StandardPixmap):
        return self.style().standardIcon(sp)

    def _build_actions(self) -> None:
        self.act_add = QAction(self._icon(QStyle.SP_DialogOpenButton), "Add Files…", self)
        self.act_add.setShortcut(QKeySequence.Open)
        self.act_add.setStatusTip("Pick video, PDF, PPTX or image files to clean")
        self.act_add.triggered.connect(self._pick_files)

        self.act_remove = QAction(self._icon(QStyle.SP_TrashIcon), "Remove Selected", self)
        self.act_remove.setShortcut(QKeySequence.Delete)
        self.act_remove.setShortcutContext(Qt.WindowShortcut)
        self.act_remove.setStatusTip("Remove the selected files from the input list")
        self.act_remove.triggered.connect(self._remove_selected)

        self.act_start = QAction(self._icon(QStyle.SP_MediaPlay), "Start", self)
        self.act_start.setStatusTip("Remove the watermark from every file in the list")
        self.act_start.triggered.connect(self._start_all)

        self.act_cancel = QAction(self._icon(QStyle.SP_MediaStop), "Cancel All", self)
        self.act_cancel.setStatusTip("Stop all files that are currently processing")
        self.act_cancel.triggered.connect(self._cancel_all)

        self.act_output_window = QAction(
            self._icon(QStyle.SP_FileDialogDetailedView), "Output Window", self
        )
        self.act_output_window.setStatusTip(
            "Show finished files - click one to preview and play it"
        )
        self.act_output_window.triggered.connect(self._toggle_output_window)

        self.act_settings = QAction(
            self._icon(QStyle.SP_FileDialogContentsView), "Settings…", self
        )
        self.act_settings.setMenuRole(QAction.PreferencesRole)
        self.act_settings.setStatusTip("Video mode, output folder, metadata stripping")
        self.act_settings.triggered.connect(self._show_settings)

        self.act_about = QAction(
            self._icon(QStyle.SP_MessageBoxInformation), "About nlmclean", self
        )
        self.act_about.setMenuRole(QAction.AboutRole)
        self.act_about.setStatusTip("Version and license information")
        self.act_about.triggered.connect(self._show_about)

        self.act_exit = QAction(self._icon(QStyle.SP_DialogCloseButton), "Exit", self)
        self.act_exit.setShortcut(QKeySequence.Quit)
        self.act_exit.setMenuRole(QAction.QuitRole)
        self.act_exit.setStatusTip("Cancel running jobs and quit")
        self.act_exit.triggered.connect(self.close)

    def _build_menubar(self) -> None:
        bar = self.menuBar()
        file_menu = bar.addMenu("&File")
        file_menu.addAction(self.act_add)
        file_menu.addAction(self.act_remove)
        file_menu.addSeparator()
        file_menu.addAction(self.act_output_window)
        file_menu.addSeparator()
        file_menu.addAction(self.act_exit)

        process_menu = bar.addMenu("&Process")
        process_menu.addAction(self.act_start)
        process_menu.addAction(self.act_cancel)

        settings_menu = bar.addMenu("&Settings")
        settings_menu.addAction(self.act_settings)

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self.act_about)
        about_qt = help_menu.addAction("About Qt")
        about_qt.triggered.connect(lambda: QMessageBox.aboutQt(self))

    def _build_toolbar(self) -> None:
        bar = QToolBar()
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(bar)
        bar.addAction(self.act_add)
        bar.addAction(self.act_remove)
        bar.addSeparator()
        bar.addAction(self.act_start)
        bar.addAction(self.act_cancel)
        bar.addSeparator()
        bar.addAction(self.act_output_window)
        bar.addAction(self.act_settings)
        bar.addSeparator()
        bar.addAction(self.act_exit)

    def _build_center(self) -> None:
        self.stack = QStackedWidget()
        self.drop_zone = DropZone()

        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setItemDelegateForColumn(COL_PROGRESS, ProgressDelegate(self.table))
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)  # Output column stretches
        self.table.setColumnWidth(0, 230)
        self.table.setColumnWidth(1, 60)
        self.table.setColumnWidth(2, 170)
        self.table.setColumnWidth(3, 90)
        self.table.setColumnWidth(4, 110)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)
        self.table.doubleClicked.connect(self._double_clicked)

        self.stack.addWidget(self.drop_zone)
        self.stack.addWidget(self.table)
        self.setCentralWidget(self.stack)

    def _build_statusbar(self) -> None:
        version = ffmpeg_version()
        text = version if version else "ffmpeg NOT FOUND - video files cannot be processed"
        self.statusBar().showMessage(text)

    def _restore_settings(self) -> None:
        out = self.settings.value("output_dir", "")
        self.output_dir = Path(out) if out and Path(out).is_dir() else None

    def closeEvent(self, event) -> None:
        self.settings.setValue("output_dir", str(self.output_dir) if self.output_dir else "")
        self._cancel_all()
        if self.output_win is not None:
            self.output_win.shutdown()
        super().closeEvent(event)

    # ------------------------------------------------------------ add files
    def dragEnterEvent(self, event) -> None:
        if any(
            Path(u.toLocalFile()).suffix.lower() in SUPPORTED_EXTS
            for u in event.mimeData().urls()
        ):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        self.add_files([Path(u.toLocalFile()) for u in event.mimeData().urls()])

    def _pick_files(self) -> None:
        start_dir = self.settings.value("last_dir", "")
        names, _ = QFileDialog.getOpenFileNames(self, "Add files", start_dir, _FILTER)
        if names:
            self.settings.setValue("last_dir", str(Path(names[0]).parent))
            self.add_files([Path(n) for n in names])

    def add_files(self, paths: list[Path]) -> None:
        for path in paths:
            kind = kind_of(path)
            if kind is None or not path.is_file() or self.model.has_path(path):
                continue
            item = FileItem(path=path, kind=kind, status=DETECTING)
            item.planned_dst = default_output(path, self.output_dir)
            self.model.add(item)
            self.pool.start(DetectWorker(item.item_id, path, self.signals))
        if self.model.items:
            self.stack.setCurrentWidget(self.table)

    # ------------------------------------------------------- worker signals
    def _on_detected(self, item_id: int, inspection) -> None:
        found = self.model.find(item_id)
        if not found:
            return
        row, item = found
        item.preview = inspection.preview
        item.region = inspection.region
        item.confidence = inspection.confidence
        item.region_scale = inspection.region_scale
        item.profile = inspection.profile
        item.status = READY
        self.model.refresh_row(row)

    def _on_detect_failed(self, item_id: int, message: str) -> None:
        found = self.model.find(item_id)
        if not found:
            return
        row, item = found
        item.status = FAILED
        item.message = message
        self.model.refresh_row(row)

    def _on_progress(self, item_id: int, fraction: float, stage: str) -> None:
        found = self.model.find(item_id)
        if not found:
            return
        row, item = found
        item.progress = fraction
        item.stage = stage
        self.model.refresh_row(row)

    def _on_finished(self, item_id: int, result) -> None:
        found = self.model.find(item_id)
        if not found:
            return
        row, item = found
        if result.ok:
            item.status = DONE
            item.dst = result.dst
            item.progress = 1.0
            self._add_output(result.dst)
        elif result.message == "cancelled":
            item.status = CANCELLED
        else:
            item.status = FAILED
            item.message = result.message
        self.model.refresh_row(row)
        self._update_overall()

    def _update_overall(self) -> None:
        total = len(self.model.items)
        done = sum(1 for i in self.model.items if i.status in (DONE, FAILED, CANCELLED))
        busy = sum(1 for i in self.model.items if i.status == PROCESSING)
        if busy:
            self.statusBar().showMessage(f"Processing… {done}/{total} finished")
        else:
            failed = sum(1 for i in self.model.items if i.status == FAILED)
            message = f"Finished: {done}/{total}"
            if failed:
                message += f" ({failed} failed)"
            self.statusBar().showMessage(message)

    # -------------------------------------------------------- output window
    def _output_window(self):
        if self.output_win is None:
            from nlmclean.gui.output_window import OutputWindow

            self.output_win = OutputWindow()
        return self.output_win

    def _add_output(self, dst: Path) -> None:
        win = self._output_window()
        win.add_output(dst)
        if not self._output_shown_once:
            # only steal focus once per session, not on every batch item
            self._output_shown_once = True
            win.show()
            win.raise_()

    def _toggle_output_window(self) -> None:
        win = self._output_window()
        if win.isVisible():
            win.hide()
        else:
            win.show()
            win.raise_()

    # -------------------------------------------------------------- actions
    def _show_settings(self) -> None:
        dialog = SettingsDialog(self)
        if dialog.exec() != SettingsDialog.Accepted:
            return
        self.output_dir = dialog.selected_output_dir()
        self._refresh_planned_dsts()

    def _refresh_planned_dsts(self) -> None:
        # reflect the new destination in the Output column for everything not yet written
        for item in self.model.items:
            if item.status != DONE:
                item.planned_dst = default_output(item.path, self.output_dir)
        self.model.refresh_all()

    def _show_about(self) -> None:
        ffmpeg = ffmpeg_version() or "not found"
        QMessageBox.about(
            self,
            "About nlmclean",
            f"<h3>nlmclean {__version__}</h3>"
            "<p>Removes the NotebookLM / Gemini watermark from videos, PDFs, "
            "slide decks and images, and can strip file metadata. All processing "
            "happens locally on this computer.</p>"
            "<p>Only use it on content you created or have the rights to edit.</p>"
            f"<p style='color:#888;'>ffmpeg: {ffmpeg}<br>"
            "License: MIT - "
            "<a href='https://github.com/alpinist-GH/notebooklm-watermark-remover'>"
            "GitHub</a></p>",
        )

    def _start_all(self) -> None:
        mode = self.settings.value("mode", "fast")
        strip_metadata = self.settings.value("strip_metadata", False, bool)
        for row, item in enumerate(self.model.items):
            if item.status not in (READY, FAILED, CANCELLED):
                continue
            item.cancel = CancelToken()
            item.status = PROCESSING
            item.progress = 0.0
            item.message = ""
            item.planned_dst = default_output(item.path, self.output_dir)
            job = Job(
                src=item.path,
                dst=item.planned_dst,
                mode=mode,
                region=item.job_region(),
                profile=item.profile,
                strip_metadata=strip_metadata,
                cancel=item.cancel,
            )
            self.model.refresh_row(row)
            self.pool.start(ProcessWorker(item.item_id, job, item.kind, self.signals))
        self._update_overall()

    def _cancel_all(self) -> None:
        for item in self.model.items:
            if item.status == PROCESSING:
                item.cancel.cancel()

    def _remove_selected(self) -> None:
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        if not rows:
            return
        for row in rows:
            self.model.items[row].cancel.cancel()
        self.model.remove_rows(rows)
        if not self.model.items:
            self.stack.setCurrentWidget(self.drop_zone)

    def _context_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        item = self.model.items[row]
        menu = QMenu(self)
        adjust = menu.addAction("Preview / adjust region…")
        adjust.setEnabled(item.preview is not None)
        menu.addAction(self.act_remove)
        open_out = menu.addAction("Open output")
        open_out.setEnabled(item.dst is not None and item.dst.exists())
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen == adjust:
            self._adjust_region(row)
        elif chosen == open_out and item.dst:
            reveal_in_explorer(item.dst)

    def _double_clicked(self, index) -> None:
        item = self.model.items[index.row()]
        if index.column() == COL_OUTPUT:
            if item.dst is not None and item.dst.exists():
                reveal_in_explorer(item.dst)
            return
        self._adjust_region(index.row())

    def _adjust_region(self, row: int) -> None:
        item = self.model.items[row]
        if item.preview is None or item.region is None:
            return
        dialog = PreviewDialog(item.preview, item.region, item.kind, self, profile=item.profile)
        if dialog.exec() == PreviewDialog.Accepted:
            item.region = dialog.selected_region()
            item.profile = dialog.selected_profile()
            item.region_is_manual = True
            if item.status in (FAILED, CANCELLED):
                item.status = READY
            self.model.refresh_row(row)
