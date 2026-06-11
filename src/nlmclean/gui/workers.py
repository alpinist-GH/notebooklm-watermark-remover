"""QThreadPool workers. Videos process one at a time (x264 already saturates the
CPU); documents/images run up to three in parallel. Engine code stays Qt-free -
these workers adapt its callbacks to cross-thread Qt signals."""

from __future__ import annotations

import threading

from PySide6.QtCore import QObject, QRunnable, Signal

from nlmclean.core.dispatch import process_job
from nlmclean.core.job import Job
from nlmclean.gui.inspect import inspect_file

_video_gate = threading.Semaphore(1)
_doc_gate = threading.Semaphore(3)


class WorkerSignals(QObject):
    detected = Signal(int, object)  # item_id, Inspection
    detect_failed = Signal(int, str)  # item_id, error
    progress = Signal(int, float, str)  # item_id, fraction, stage
    finished = Signal(int, object)  # item_id, JobResult


class DetectWorker(QRunnable):
    def __init__(self, item_id: int, path, signals: WorkerSignals, detect: str = "auto") -> None:
        super().__init__()
        self.item_id = item_id
        self.path = path
        self.signals = signals
        self.detect = detect

    def run(self) -> None:
        try:
            inspection = inspect_file(self.path, self.detect)
        except Exception as exc:
            self.signals.detect_failed.emit(self.item_id, str(exc))
            return
        self.signals.detected.emit(self.item_id, inspection)


class ProcessWorker(QRunnable):
    def __init__(self, item_id: int, job: Job, kind: str, signals: WorkerSignals) -> None:
        super().__init__()
        self.item_id = item_id
        self.job = job
        self.kind = kind
        self.signals = signals

    def run(self) -> None:
        gate = _video_gate if self.kind == "video" else _doc_gate
        with gate:
            if self.job.cancel.cancelled:
                from nlmclean.core.job import JobResult

                self.signals.finished.emit(self.item_id, JobResult(ok=False, message="cancelled"))
                return
            result = process_job(
                self.job,
                lambda fraction, stage: self.signals.progress.emit(
                    self.item_id, fraction, stage
                ),
            )
        self.signals.finished.emit(self.item_id, result)
