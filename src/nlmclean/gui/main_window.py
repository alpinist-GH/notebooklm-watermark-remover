"""Main window: drag-and-drop batch list with per-file progress."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QThreadPool
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QLabel,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QTableView,
    QToolBar,
)

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
from nlmclean.gui.workers import DetectWorker, ProcessWorker, WorkerSignals

_FILTER = (
    "NotebookLM exports "
    "(*.mp4 *.mov *.m4v *.webm *.mkv *.pdf *.pptx *.png *.jpg *.jpeg *.webp)"
)


class DropZone(QLabel):
    def __init__(self) -> None:
        super().__init__("Drop MP4 / PDF / PPTX / PNG / JPG here\n\nor click “Add Files…”")
        self.setAlignment(Qt.AlignCenter)
        self.setStyleSheet(
            "QLabel { border: 2px dashed #888; border-radius: 12px; "
            "font-size: 16px; color: #888; margin: 24px; }"
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

        self._build_toolbar()
        self._build_center()
        self._build_statusbar()
        self._restore_settings()

    # ------------------------------------------------------------- UI setup
    def _build_toolbar(self) -> None:
        bar = QToolBar()
        bar.setMovable(False)
        self.addToolBar(bar)

        add_btn = QPushButton("Add Files…")
        add_btn.clicked.connect(self._pick_files)
        bar.addWidget(add_btn)

        bar.addSeparator()
        bar.addWidget(QLabel(" Video mode: "))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Fast (delogo)", "fast")
        self.mode_combo.addItem("Quality (inpaint)", "quality")
        bar.addWidget(self.mode_combo)

        bar.addSeparator()
        bar.addWidget(QLabel(" Output: "))
        self.output_combo = QComboBox()
        self.output_combo.addItem("Same folder (suffix _clean)")
        self.output_combo.addItem("Choose folder…")
        self.output_combo.activated.connect(self._output_changed)
        bar.addWidget(self.output_combo)

        bar.addSeparator()
        self.start_btn = QPushButton("Start")
        self.start_btn.clicked.connect(self._start_all)
        bar.addWidget(self.start_btn)
        self.cancel_btn = QPushButton("Cancel All")
        self.cancel_btn.clicked.connect(self._cancel_all)
        bar.addWidget(self.cancel_btn)

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
        mode = self.settings.value("mode", "fast")
        self.mode_combo.setCurrentIndex(1 if mode == "quality" else 0)
        out = self.settings.value("output_dir", "")
        if out and Path(out).is_dir():
            self.output_dir = Path(out)
            self.output_combo.setItemText(1, f"Folder: {out}")
            self.output_combo.setCurrentIndex(1)

    def closeEvent(self, event) -> None:
        self.settings.setValue("mode", self.mode_combo.currentData())
        self.settings.setValue("output_dir", str(self.output_dir) if self.output_dir else "")
        self._cancel_all()
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

    # -------------------------------------------------------------- actions
    def _output_changed(self, index: int) -> None:
        if index == 1:
            chosen = QFileDialog.getExistingDirectory(self, "Output folder")
            if chosen:
                self.output_dir = Path(chosen)
                self.output_combo.setItemText(1, f"Folder: {chosen}")
            else:
                self.output_combo.setCurrentIndex(0)
                self.output_dir = None
        else:
            self.output_dir = None
        # reflect the new destination in the Output column for everything not yet written
        for item in self.model.items:
            if item.status != DONE:
                item.planned_dst = default_output(item.path, self.output_dir)
        self.model.refresh_all()

    def _start_all(self) -> None:
        mode = self.mode_combo.currentData()
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
                cancel=item.cancel,
            )
            self.model.refresh_row(row)
            self.pool.start(ProcessWorker(item.item_id, job, item.kind, self.signals))
        self._update_overall()

    def _cancel_all(self) -> None:
        for item in self.model.items:
            if item.status == PROCESSING:
                item.cancel.cancel()

    def _context_menu(self, pos) -> None:
        index = self.table.indexAt(pos)
        if not index.isValid():
            return
        row = index.row()
        item = self.model.items[row]
        menu = QMenu(self)
        adjust = menu.addAction("Preview / adjust region…")
        adjust.setEnabled(item.preview is not None)
        remove = menu.addAction("Remove")
        open_out = menu.addAction("Open output")
        open_out.setEnabled(item.dst is not None and item.dst.exists())
        chosen = menu.exec(self.table.viewport().mapToGlobal(pos))
        if chosen == adjust:
            self._adjust_region(row)
        elif chosen == remove:
            item.cancel.cancel()
            self.model.remove_rows([row])
            if not self.model.items:
                self.stack.setCurrentWidget(self.drop_zone)
        elif chosen == open_out and item.dst:
            self._reveal(item.dst)

    def _double_clicked(self, index) -> None:
        item = self.model.items[index.row()]
        if index.column() == COL_OUTPUT:
            if item.dst is not None and item.dst.exists():
                self._reveal(item.dst)
            return
        self._adjust_region(index.row())

    def _adjust_region(self, row: int) -> None:
        item = self.model.items[row]
        if item.preview is None or item.region is None:
            return
        dialog = PreviewDialog(item.preview, item.region, item.kind, self)
        if dialog.exec() == PreviewDialog.Accepted:
            item.region = dialog.selected_region()
            item.region_is_manual = True
            if item.status in (FAILED, CANCELLED):
                item.status = READY
            self.model.refresh_row(row)

    @staticmethod
    def _reveal(path: Path) -> None:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", "-R", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path.parent)])
