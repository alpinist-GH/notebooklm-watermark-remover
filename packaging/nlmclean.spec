# PyInstaller spec - one-folder GUI bundle for Windows and macOS.
# Build:  pyinstaller packaging/nlmclean.spec
# Run packaging/fetch_ffmpeg.py first so the static ffmpeg gets bundled.

import sys
from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent  # noqa: F821 (SPECPATH injected by PyInstaller)

datas = []
templates = ROOT / "assets" / "templates"
if templates.exists():
    datas.append((str(templates), "assets/templates"))
ffmpeg_bin = ROOT / "packaging" / "ffmpeg_bin"
if ffmpeg_bin.exists():
    datas.append((str(ffmpeg_bin), "ffmpeg"))  # -> _internal/ffmpeg/, found by locate.py

a = Analysis(
    [str(ROOT / "packaging" / "launch_gui.py")],
    pathex=[str(ROOT / "src")],
    datas=datas,
    hiddenimports=[
        # output-window preview player
        "PySide6.QtMultimedia",
        "PySide6.QtMultimediaWidgets",
    ],
    excludes=[
        "tkinter",
        "imageio_ffmpeg",  # releases use the bundled static ffmpeg
        "PySide6.QtWebEngineCore",
        "PySide6.QtWebEngineWidgets",
        "PySide6.QtQml",
        "PySide6.QtQuick",
        "PySide6.QtQuick3D",
        "PySide6.QtCharts",
        "PySide6.QtDataVisualization",
        "PySide6.QtPdf",
        "PySide6.Qt3DCore",
        "PySide6.Qt3DRender",
    ],
    noarchive=False,
)

# Qt DLLs pulled in via plugin deps that the app never loads (no QML/Quick UI,
# no Qt PDF, no GL rendering). Qt6Network must stay: QtMultimedia links it.
# plugins/tls stays pruned: the preview player only opens local files.
_PRUNE = (
    "Qt6Quick",
    "Qt6Qml",
    "Qt6Pdf",
    "Qt6ShaderTools",
    "Qt6VirtualKeyboard",
    "opengl32sw",
    "plugins\\tls",
    "plugins/tls",
)
a.binaries = [b for b in a.binaries if not any(p in b[0] for p in _PRUNE)]

pyz = PYZ(a.pure)

icon = ROOT / "assets" / ("icon.icns" if sys.platform == "darwin" else "icon.ico")

exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="nlmclean",
    icon=str(icon),
    console=False,
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="nlmclean", upx=False)

if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="nlmclean.app",
        icon=str(ROOT / "assets" / "icon.icns"),
        bundle_identifier="org.nlmclean.app",
        info_plist={
            "NSHighResolutionCapable": True,
            "CFBundleShortVersionString": "0.2.0",
        },
    )
