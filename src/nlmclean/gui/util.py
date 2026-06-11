"""Small GUI helpers shared between windows."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def reveal_in_explorer(path: Path) -> None:
    """Open the platform file manager with *path* selected."""
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(path)])
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-R", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path.parent)])
