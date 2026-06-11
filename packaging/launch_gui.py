"""PyInstaller entry point - GUI by default, CLI when arguments are given.

Passing files (or dropping them onto the exe in Explorer) processes them
directly with default settings instead of opening the window.
"""

import io
import sys


def main() -> int:
    if len(sys.argv) > 1:
        # the exe is windowed: stdout/stderr are None, so give the CLI's
        # progress prints somewhere harmless to go
        for name in ("stdout", "stderr"):
            if getattr(sys, name) is None:
                setattr(sys, name, io.StringIO())
        from nlmclean.cli import main as cli_main

        return cli_main()

    from nlmclean.gui.app import main as gui_main

    return gui_main()


sys.exit(main())
