"""Batch table: model + progress-bar delegate."""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionProgressBar

from nlmclean.core.job import CancelToken
from nlmclean.core.region import Region

# item statuses
QUEUED = "Queued"
DETECTING = "Detecting"
READY = "Ready"
PROCESSING = "Processing"
DONE = "Done"
FAILED = "Failed"
CANCELLED = "Cancelled"

_ids = itertools.count(1)


@dataclass
class FileItem:
    path: Path
    kind: str = "?"
    item_id: int = field(default_factory=lambda: next(_ids))
    status: str = QUEUED
    progress: float = 0.0
    stage: str = ""
    message: str = ""
    confidence: float = 0.0
    region: Region | None = None  # preview-image coordinates
    region_scale: float = 1.0
    region_is_manual: bool = False
    preview: np.ndarray | None = None
    planned_dst: Path | None = None  # where the output will be written
    dst: Path | None = None  # where it actually was written
    cancel: CancelToken = field(default_factory=CancelToken)

    def job_region(self) -> Region | None:
        if self.region is None:
            return None
        return self.region if self.region_scale == 1.0 else self.region.scaled(self.region_scale)


COLUMNS = ("File", "Type", "Region", "Status", "Progress", "Output")
COL_FILE, COL_TYPE, COL_REGION, COL_STATUS, COL_PROGRESS, COL_OUTPUT = range(6)


class FileTableModel(QAbstractTableModel):
    def __init__(self) -> None:
        super().__init__()
        self.items: list[FileItem] = []

    # --- Qt model API -------------------------------------------------
    def rowCount(self, parent=None) -> int:
        if parent is not None and parent.isValid():
            return 0
        return len(self.items)

    def columnCount(self, parent=None) -> int:
        return len(COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        item = self.items[index.row()]
        col = index.column()

        if role == Qt.DisplayRole:
            if col == COL_FILE:
                return item.path.name
            if col == COL_TYPE:
                return item.kind
            if col == COL_REGION:
                if item.region is None:
                    return "-"
                tag = "manual" if item.region_is_manual else f"conf {item.confidence:.2f}"
                return f"{item.region} ({tag})"
            if col == COL_STATUS:
                return item.status
            if col == COL_OUTPUT:
                target = item.dst or item.planned_dst
                return str(target) if target else "-"
            return None  # progress drawn by delegate

        if role == Qt.ToolTipRole:
            if col == COL_FILE:
                return str(item.path)
            if col == COL_STATUS and item.message:
                return item.message
            if col == COL_OUTPUT:
                target = item.dst or item.planned_dst
                if target is None:
                    return None
                hint = "double-click to open" if item.dst else "will be written here"
                return f"{target}\n({hint})"
            return None

        if role == Qt.ForegroundRole and col in (COL_REGION, COL_STATUS):
            if item.status == FAILED:
                return QColor("#d9534f")
            if item.status == READY and not item.region_is_manual and item.confidence < 0.5:
                return QColor("#e8a33d")  # low confidence: nudge the user to confirm
            return None

        if role == Qt.UserRole:
            return item
        return None

    # --- mutations ----------------------------------------------------
    def add(self, item: FileItem) -> None:
        row = len(self.items)
        self.beginInsertRows(QModelIndex(), row, row)
        self.items.append(item)
        self.endInsertRows()

    def remove_rows(self, rows: list[int]) -> None:
        for row in sorted(rows, reverse=True):
            self.beginRemoveRows(QModelIndex(), row, row)
            del self.items[row]
            self.endRemoveRows()

    def find(self, item_id: int) -> tuple[int, FileItem] | None:
        for row, item in enumerate(self.items):
            if item.item_id == item_id:
                return row, item
        return None

    def refresh_row(self, row: int) -> None:
        self.dataChanged.emit(self.index(row, 0), self.index(row, len(COLUMNS) - 1))

    def refresh_all(self) -> None:
        if self.items:
            self.dataChanged.emit(
                self.index(0, 0), self.index(len(self.items) - 1, len(COLUMNS) - 1)
            )

    def has_path(self, path: Path) -> bool:
        return any(item.path == path for item in self.items)


class ProgressDelegate(QStyledItemDelegate):
    def paint(self, painter, option, index) -> None:
        item: FileItem = index.data(Qt.UserRole)
        if item is None or item.status not in (PROCESSING, DONE):
            return super().paint(painter, option, index)
        bar = QStyleOptionProgressBar()
        bar.rect = option.rect.adjusted(4, 6, -4, -6)
        bar.minimum, bar.maximum = 0, 100
        bar.progress = 100 if item.status == DONE else int(item.progress * 100)
        bar.text = f"{bar.progress}%"
        bar.textVisible = True
        QApplication.style().drawControl(QStyle.CE_ProgressBar, bar, painter)
