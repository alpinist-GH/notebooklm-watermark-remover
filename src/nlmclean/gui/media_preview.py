"""Built-in preview: plays videos and renders images / PDF pages / PPTX slides."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from nlmclean.core.dispatch import kind_of

try:  # QtMultimedia may be missing in stripped builds; degrade to a notice label
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
    from PySide6.QtMultimediaWidgets import QVideoWidget

    _HAS_MULTIMEDIA = True
except ImportError:  # pragma: no cover
    _HAS_MULTIMEDIA = False

_PAGE_PLACEHOLDER, _PAGE_IMAGE, _PAGE_VIDEO = range(3)


class MediaPreview(QWidget):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._pixmap: QPixmap | None = None
        self._player = None
        self._audio = None

        self._stack = QStackedWidget()

        self._placeholder = QLabel("Select a finished file to preview it here.")
        self._placeholder.setAlignment(Qt.AlignCenter)
        self._placeholder.setStyleSheet("color: #888; font-size: 14px;")
        self._stack.addWidget(self._placeholder)

        self._image_label = QLabel()
        self._image_label.setAlignment(Qt.AlignCenter)
        self._image_label.setMinimumSize(1, 1)
        self._stack.addWidget(self._image_label)

        self._stack.addWidget(self._build_video_page())

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self._stack)

    def _build_video_page(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        if not _HAS_MULTIMEDIA:
            notice = QLabel("Video preview unavailable (QtMultimedia not installed).")
            notice.setAlignment(Qt.AlignCenter)
            layout.addWidget(notice)
            return page

        self._video_widget = QVideoWidget()
        self._play_btn = QPushButton()
        self._play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
        self._play_btn.setFixedWidth(40)
        self._play_btn.clicked.connect(self._toggle_play)
        self._slider = QSlider(Qt.Horizontal)
        self._slider.sliderMoved.connect(self._seek)

        controls = QHBoxLayout()
        controls.addWidget(self._play_btn)
        controls.addWidget(self._slider, stretch=1)
        layout.addWidget(self._video_widget, stretch=1)
        layout.addLayout(controls)
        return page

    def _ensure_player(self):
        # lazy: avoids touching audio devices until a video is actually previewed
        if self._player is None:
            self._player = QMediaPlayer(self)
            self._audio = QAudioOutput(self)
            self._player.setAudioOutput(self._audio)
            self._player.setVideoOutput(self._video_widget)
            self._player.positionChanged.connect(self._slider.setValue)
            self._player.durationChanged.connect(lambda d: self._slider.setRange(0, d))
        return self._player

    # ----------------------------------------------------------------- API
    def show_file(self, path: Path) -> None:
        self.clear()
        kind = kind_of(path)
        if kind == "video" and _HAS_MULTIMEDIA:
            player = self._ensure_player()
            player.setSource(QUrl.fromLocalFile(str(path)))
            self._stack.setCurrentIndex(_PAGE_VIDEO)
            self._play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))
            player.play()
            return

        pixmap = self._render_pixmap(path, kind)
        if pixmap is None:
            self._placeholder.setText(f"No preview available for {path.name}")
            self._stack.setCurrentIndex(_PAGE_PLACEHOLDER)
            return
        self._pixmap = pixmap
        self._rescale_image()
        self._stack.setCurrentIndex(_PAGE_IMAGE)

    def clear(self) -> None:
        """Release the current file. Must run before the file is moved/deleted:
        on Windows the media player keeps it locked while loaded."""
        if self._player is not None:
            self._player.stop()
            self._player.setSource(QUrl())
        self._pixmap = None
        self._image_label.clear()
        self._placeholder.setText("Select a finished file to preview it here.")
        self._stack.setCurrentIndex(_PAGE_PLACEHOLDER)

    # ------------------------------------------------------------- internal
    @staticmethod
    def _render_pixmap(path: Path, kind: str | None) -> QPixmap | None:
        from nlmclean.gui.preview_dialog import bgr_to_pixmap

        try:
            if kind == "image":
                pixmap = QPixmap(str(path))
                return pixmap if not pixmap.isNull() else None
            if kind == "pdf":
                from nlmclean.core.pdf import _render_page_bgr

                return bgr_to_pixmap(_render_page_bgr(path.read_bytes(), 0, 2.0))
            if kind == "pptx":
                from nlmclean.gui.inspect import _first_slide_image

                return bgr_to_pixmap(_first_slide_image(path))
        except Exception:
            return None
        return None

    def _rescale_image(self) -> None:
        if self._pixmap is None:
            return
        self._image_label.setPixmap(
            self._pixmap.scaled(
                self._image_label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )
        )

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._rescale_image()

    def _toggle_play(self) -> None:
        if self._player is None:
            return
        if self._player.playbackState() == QMediaPlayer.PlayingState:
            self._player.pause()
            self._play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))
        else:
            self._player.play()
            self._play_btn.setIcon(self.style().standardIcon(QStyle.SP_MediaPause))

    def _seek(self, position: int) -> None:
        if self._player is not None:
            self._player.setPosition(position)
