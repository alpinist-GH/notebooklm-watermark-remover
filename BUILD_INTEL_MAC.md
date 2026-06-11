# Building nlmclean on an Intel Mac (x86_64)

The published `nlmclean-v0.1.0-macos.dmg` was built by CI on Apple Silicon
(`macos-14`), so it is an **arm64** bundle and will not launch on an Intel Mac.
Build from source natively on the Intel machine to get an x86_64 bundle. Nothing
here is platform-locked; the macOS ffmpeg this fetches (evermeet.cx) is already
an x86_64 static build.

## Prerequisites

- An **Intel** Mac (or Apple Silicon running an x86_64 Python under Rosetta — see note).
- Python 3.12 recommended (CI pins 3.12; 3.11–3.13 also fine).
  Check you are on an x86_64 Python:
  ```sh
  python3 -c "import platform; print(platform.machine())"   # must print: x86_64
  ```
- Xcode Command Line Tools (`xcode-select --install`) — needed for `codesign`/`hdiutil`.

## Build

```sh
git clone https://github.com/alpinist-GH/notebooklm-watermark-remover.git
cd notebooklm-watermark-remover

python3 -m venv .venv
source .venv/bin/activate

pip install -e ".[dev]"           # installs the app + PyInstaller

python packaging/fetch_ffmpeg.py  # downloads the x86_64 static ffmpeg

pyinstaller packaging/nlmclean.spec --noconfirm

bash packaging/make_dmg.sh nlmclean-v0.1.0-macos-intel.dmg
```

The result is `nlmclean-v0.1.0-macos-intel.dmg` in the current directory, and the
raw app at `dist/nlmclean.app`.

## First launch

The app is ad-hoc signed (unsigned by a developer ID), so Gatekeeper will block
the first open. Right-click `nlmclean.app` → **Open** → **Open**, or:

```sh
xattr -dr com.apple.quarantine /Applications/nlmclean.app
```

## Smoke test before packaging (optional)

```sh
./dist/nlmclean.app/Contents/MacOS/nlmclean --help          # CLI passthrough
./dist/nlmclean.app/Contents/MacOS/nlmclean some_video.mp4  # clean a file
```

## Notes

- **Apple Silicon shortcut:** if you only have an M-series Mac but need an Intel
  build, install an x86_64 Python via an x86_64 Homebrew under Rosetta
  (`arch -x86_64 /usr/local/bin/python3 -m venv .venv`) and run the same steps —
  the whole toolchain (pip wheels, PyInstaller, ffmpeg) will be x86_64.
- **Universal2** is *not* configured here; this produces a single-arch x86_64
  bundle, which is what an Intel Mac needs.
- To automate this in releases, add a `macos-13` (Intel runner) row to the matrix
  in `.github/workflows/release.yml` so the next tag also produces an Intel dmg.
