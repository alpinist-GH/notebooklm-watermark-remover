"""Output window: list of finished files with a built-in preview/player."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QAction, QDesktopServices
from PySide6.QtWidgets import (
    QFileIconProvider,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QSplitter,
    QStyle,
    QToolBar,
)

from nlmclean.gui.media_preview import MediaPreview
from nlmclean.gui.util import reveal_in_explorer


class OutputWindow(QMainWindow):
    """Owned by MainWindow; closing it only hides it (the input window quits the app)."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("nlmclean - Finished Files")
        self.resize(900, 560)
        self._really_close = False
        self.docked = True  # follows the input window until the user drags it away
        self._in_dock_move = False
        self._dock_pos = self.pos()
        self._icons = QFileIconProvider()

        self.list = QListWidget()
        self.list.setMinimumWidth(240)
        self.list.currentItemChanged.connect(self._selection_changed)
        self.list.itemDoubleClicked.connect(self._open_item)

        self.preview = MediaPreview()

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.list)
        splitter.addWidget(self.preview)
        splitter.setStretchFactor(1, 1)
        self.setCentralWidget(splitter)

        self._build_toolbar()
        self.statusBar().showMessage(
            "Click a file to preview it - double-click to open it in its default app"
        )

    def _build_toolbar(self) -> None:
        bar = QToolBar()
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.addToolBar(bar)

        act_open = QAction(
            self.style().standardIcon(QStyle.SP_DialogOpenButton), "Open", self
        )
        act_open.setStatusTip("Open the selected file in its default application")
        act_open.triggered.connect(lambda: self._open_item(self.list.currentItem()))
        bar.addAction(act_open)

        act_reveal = QAction(
            self.style().standardIcon(QStyle.SP_DirOpenIcon), "Show in Folder", self
        )
        act_reveal.setStatusTip("Show the selected file in the file manager")
        act_reveal.triggered.connect(self._reveal_item)
        bar.addAction(act_reveal)

        bar.addSeparator()
        act_clear = QAction(
            self.style().standardIcon(QStyle.SP_TrashIcon), "Clear List", self
        )
        act_clear.setStatusTip("Empty this list (files on disk are not deleted)")
        act_clear.triggered.connect(self._clear_list)
        bar.addAction(act_clear)

    # ------------------------------------------------------------- docking
    def dock_beside(self, main: QMainWindow) -> None:
        """Place this window flush against the input window's right edge."""
        fg = main.frameGeometry()
        x = fg.right() + 1
        width = self.width()
        screen = main.screen()
        if screen is not None:
            avail = screen.availableGeometry()
            overflow = (x + self.frameGeometry().width()) - (avail.right() + 1)
            if overflow > 0:
                # make room: nudge the input window left, then shrink to fit
                shift = min(overflow, max(0, fg.left() - avail.left()))
                if shift > 0:
                    main.move(main.x() - shift, main.y())
                    fg = main.frameGeometry()
                    x = fg.right() + 1
                    overflow -= shift
                if overflow > 0:
                    width = max(480, width - overflow)
        self._in_dock_move = True
        try:
            self.resize(width, main.height())
            self.move(x, fg.top())
        finally:
            self._in_dock_move = False
        self._dock_pos = self.pos()
        self.docked = True

    def moveEvent(self, event) -> None:
        # a late window-system move to the docked spot (e.g. during show())
        # is not a user drag - only moves away from it undock
        if self.isVisible() and not self._in_dock_move and self.pos() != self._dock_pos:
            self.docked = False  # the user dragged it away; stop following
        super().moveEvent(event)

    # ----------------------------------------------------------------- API
    def add_output(self, path: Path) -> None:
        for row in range(self.list.count()):
            if self.list.item(row).data(Qt.UserRole) == str(path):
                self.list.setCurrentRow(row)
                self.preview.show_file(path)  # reload: the file was just rewritten
                return
        item = QListWidgetItem(self._icons.icon(QFileIconProvider.IconType.File), path.name)
        item.setData(Qt.UserRole, str(path))
        item.setToolTip(str(path))
        self.list.addItem(item)
        self.list.setCurrentItem(item)

    def shutdown(self) -> None:
        self.preview.clear()
        self._really_close = True
        self.close()

    # ------------------------------------------------------------- internal
    def _selection_changed(self, current, _previous) -> None:
        if current is None:
            self.preview.clear()
            return
        self.preview.show_file(Path(current.data(Qt.UserRole)))

    def _open_item(self, item) -> None:
        if item is None:
            return
        path = Path(item.data(Qt.UserRole))
        # release our own lock first, then hand off to the default app
        self.preview.clear()
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))

    def _reveal_item(self) -> None:
        item = self.list.currentItem()
        if item is not None:
            reveal_in_explorer(Path(item.data(Qt.UserRole)))

    def _clear_list(self) -> None:
        self.preview.clear()
        self.list.clear()

    def closeEvent(self, event) -> None:
        if self._really_close:
            super().closeEvent(event)
            return
        self.preview.clear()
        event.ignore()
        self.hide()
