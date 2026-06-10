"""GUI entry point: nlmclean-gui"""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from nlmclean import __version__
from nlmclean.gui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("nlmclean")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("nlmclean")
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
