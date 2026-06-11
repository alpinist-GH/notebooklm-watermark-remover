"""Per-file preview: shows the detected watermark rectangle on a representative
frame/page/slide and lets the user move/resize it, re-run detection, or preview
the inpainted result."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGraphicsPixmapItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from nlmclean.core.inpaint import inpaint_region
from nlmclean.core.region import Region
from nlmclean.detect import detect_region
from nlmclean.detect.mask import stroke_mask_for_region


def bgr_to_pixmap(img: np.ndarray) -> QPixmap:
    h, w = img.shape[:2]
    qimg = QImage(img.data, w, h, 3 * w, QImage.Format_BGR888)
    return QPixmap.fromImage(qimg.copy())


_EDGE = 10  # px hit zone for resize


class RegionRectItem(QGraphicsRectItem):
    """Movable, edge/corner-resizable rectangle."""

    def __init__(self, rect: QRectF, bounds: QRectF) -> None:
        super().__init__(rect)
        self._bounds = bounds
        self._resize_dir: tuple[int, int] | None = None
        self._press_pos = None
        self._press_rect = None
        self.setPen(QPen(QColor(230, 60, 60), 2))
        self.setBrush(QBrush(QColor(230, 60, 60, 60)))
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsRectItem.ItemIsMovable, True)

    def _direction(self, pos) -> tuple[int, int]:
        r = self.rect()
        dx = (-1 if abs(pos.x() - r.left()) < _EDGE else 0) or (
            1 if abs(pos.x() - r.right()) < _EDGE else 0
        )
        dy = (-1 if abs(pos.y() - r.top()) < _EDGE else 0) or (
            1 if abs(pos.y() - r.bottom()) < _EDGE else 0
        )
        return dx, dy

    def hoverMoveEvent(self, event) -> None:
        dx, dy = self._direction(event.pos())
        if dx and dy:
            cursor = Qt.SizeFDiagCursor if dx == dy else Qt.SizeBDiagCursor
        elif dx:
            cursor = Qt.SizeHorCursor
        elif dy:
            cursor = Qt.SizeVerCursor
        else:
            cursor = Qt.SizeAllCursor
        self.setCursor(cursor)
        super().hoverMoveEvent(event)

    def mousePressEvent(self, event) -> None:
        self._resize_dir = self._direction(event.pos())
        if self._resize_dir != (0, 0):
            self._press_pos = event.pos()
            self._press_rect = QRectF(self.rect())
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:
        if self._resize_dir and self._resize_dir != (0, 0) and self._press_rect is not None:
            dx, dy = self._resize_dir
            delta = event.pos() - self._press_pos
            r = QRectF(self._press_rect)
            if dx < 0:
                r.setLeft(r.left() + delta.x())
            elif dx > 0:
                r.setRight(r.right() + delta.x())
            if dy < 0:
                r.setTop(r.top() + delta.y())
            elif dy > 0:
                r.setBottom(r.bottom() + delta.y())
            if r.width() >= 8 and r.height() >= 8:
                self.setRect(r.normalized())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        self._resize_dir = None
        super().mouseReleaseEvent(event)
        self._clamp_to_bounds()

    def _clamp_to_bounds(self) -> None:
        scene_rect = self.mapRectToScene(self.rect())
        clamped = scene_rect.intersected(self._bounds)
        if clamped != scene_rect and not clamped.isEmpty():
            self.setPos(0, 0)
            self.setRect(clamped)

    def scene_region(self) -> Region:
        r = self.mapRectToScene(self.rect())
        return Region(round(r.x()), round(r.y()), round(r.width()), round(r.height()))


class PreviewDialog(QDialog):
    def __init__(self, preview: np.ndarray, region: Region, kind: str, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Adjust watermark region")
        self.resize(960, 640)
        self._preview = preview
        self._kind = "video" if kind == "video" else "doc"
        self._showing_result = False

        self._scene = QGraphicsScene(self)
        self._pix_item = QGraphicsPixmapItem(bgr_to_pixmap(preview))
        self._scene.addItem(self._pix_item)
        bounds = QRectF(0, 0, preview.shape[1], preview.shape[0])
        self._rect_item = RegionRectItem(QRectF(*region.as_tuple()), bounds)
        self._scene.addItem(self._rect_item)

        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.SmoothPixmapTransform)
        self._view.setDragMode(QGraphicsView.NoDrag)

        detect_btn = QPushButton("Auto-detect")
        detect_btn.clicked.connect(self._auto_detect)
        self._result_btn = QPushButton("Preview result")
        self._result_btn.setCheckable(True)
        self._result_btn.toggled.connect(self._toggle_result)
        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        top = QHBoxLayout()
        top.addWidget(QLabel("Drag the rectangle over the watermark; drag edges to resize."))
        top.addStretch(1)
        top.addWidget(detect_btn)
        top.addWidget(self._result_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self._view)
        layout.addWidget(buttons)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._view.fitInView(self._pix_item, Qt.KeepAspectRatio)

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._view.fitInView(self._pix_item, Qt.KeepAspectRatio)

    def _auto_detect(self) -> None:
        region, _conf = detect_region(self._preview, self._kind)
        self._rect_item.setPos(0, 0)
        self._rect_item.setRect(QRectF(*region.as_tuple()))

    def _toggle_result(self, checked: bool) -> None:
        if checked:
            region = self.selected_region()
            mask = stroke_mask_for_region(self._preview, region, self._kind)
            cleaned = inpaint_region(self._preview, region, mask=mask)
            self._pix_item.setPixmap(bgr_to_pixmap(cleaned))
        else:
            self._pix_item.setPixmap(bgr_to_pixmap(self._preview))

    def selected_region(self) -> Region:
        h, w = self._preview.shape[:2]
        return self._rect_item.scene_region().clamped(w, h)
