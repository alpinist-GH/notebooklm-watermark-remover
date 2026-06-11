"""Settings dialog: video mode, output folder, metadata stripping, detection mode."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
)


class SettingsDialog(QDialog):
    """Reads QSettings on open, writes them back on OK."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(420)
        settings = QSettings()

        form = QFormLayout()

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Fast (delogo)", "fast")
        self.mode_combo.addItem("Quality (inpaint)", "quality")
        if settings.value("mode", "fast") == "quality":
            self.mode_combo.setCurrentIndex(1)
        self.mode_combo.setToolTip(
            "Fast blurs/erases the watermark with ffmpeg in one pass.\n"
            "Quality re-paints every frame with OpenCV inpainting (slower, cleaner)."
        )
        form.addRow("Video mode:", self.mode_combo)

        self.detect_combo = QComboBox()
        self.detect_combo.addItem("NotebookLM / Gemini (templates)", "auto")
        self.detect_combo.addItem("Universal (any static video watermark)", "universal")
        if settings.value("detect_mode", "auto") == "universal":
            self.detect_combo.setCurrentIndex(1)
        self.detect_combo.setToolTip(
            "Universal mode finds any static watermark in a video by comparing\n"
            "frames over time. Works best on footage with movement; falls back\n"
            "to manual region selection when unsure."
        )
        form.addRow("Detection:", self.detect_combo)

        self.same_folder_radio = QRadioButton("Same folder as source (suffix _clean)")
        self.custom_folder_radio = QRadioButton("Folder:")
        self.folder_label = QLabel("-")
        self.folder_label.setStyleSheet("color: #888;")
        browse_btn = QPushButton("Browse…")
        browse_btn.clicked.connect(self._browse)
        custom_row = QHBoxLayout()
        custom_row.addWidget(self.custom_folder_radio)
        custom_row.addWidget(self.folder_label, stretch=1)
        custom_row.addWidget(browse_btn)

        self.output_dir: Path | None = None
        saved = settings.value("output_dir", "")
        if saved and Path(saved).is_dir():
            self.output_dir = Path(saved)
            self.folder_label.setText(saved)
            self.custom_folder_radio.setChecked(True)
        else:
            self.same_folder_radio.setChecked(True)

        self.strip_metadata_check = QCheckBox("Strip metadata from outputs")
        self.strip_metadata_check.setChecked(
            settings.value("strip_metadata", False, bool)
        )
        self.strip_metadata_check.setToolTip(
            "Removes EXIF from images, Info/XMP from PDFs, document properties\n"
            "from PPTX and container tags from videos when writing the output."
        )

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel("Output location:"))
        layout.addWidget(self.same_folder_radio)
        layout.addLayout(custom_row)
        layout.addWidget(self.strip_metadata_check)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _browse(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, "Output folder")
        if chosen:
            self.output_dir = Path(chosen)
            self.folder_label.setText(chosen)
            self.custom_folder_radio.setChecked(True)

    def accept(self) -> None:
        if self.custom_folder_radio.isChecked() and self.output_dir is None:
            self.same_folder_radio.setChecked(True)
        settings = QSettings()
        settings.setValue("mode", self.mode_combo.currentData())
        settings.setValue("detect_mode", self.detect_combo.currentData())
        settings.setValue("strip_metadata", self.strip_metadata_check.isChecked())
        out = self.output_dir if self.custom_folder_radio.isChecked() else None
        settings.setValue("output_dir", str(out) if out else "")
        super().accept()

    def selected_output_dir(self) -> Path | None:
        return self.output_dir if self.custom_folder_radio.isChecked() else None
