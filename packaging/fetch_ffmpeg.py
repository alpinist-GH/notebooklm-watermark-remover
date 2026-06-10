"""Download static ffmpeg + ffprobe for bundling into release builds.

Usage: python packaging/fetch_ffmpeg.py [--dest packaging/ffmpeg_bin]

Sources:
- Windows: BtbN FFmpeg-Builds (GPL build with libx264) - https://github.com/BtbN/FFmpeg-Builds
- macOS:   evermeet.cx static builds (x86_64, runs on Apple Silicon via Rosetta 2)

The downloaded archive's SHA256 is printed and written next to the binaries.
These are GPL builds invoked strictly as separate subprocesses; the bundle ships
LICENSE.ffmpeg.txt with the source link (written by this script).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import shutil
import stat
import sys
import urllib.request
import zipfile
from pathlib import Path

# Only ffmpeg.exe is bundled (no ffprobe): nlmclean's prober falls back to
# parsing `ffmpeg -i` stderr, and a second static exe duplicates ~80MB of codecs.
# gyan.dev "essentials" carries everything we use (h264/aac/mp4/delogo/rawvideo).
WIN_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
MAC_URLS = {
    "ffmpeg": "https://evermeet.cx/ffmpeg/getrelease/ffmpeg/zip",
}

LICENSE_NOTE = """ffmpeg / ffprobe in this bundle are GPL-licensed static builds, invoked by
nlmclean strictly as separate subprocesses.

Source of the binaries:
  {source}

ffmpeg source code and license: https://ffmpeg.org/legal.html
GPL v3: https://www.gnu.org/licenses/gpl-3.0.html

Archive SHA256:
{hashes}
"""


def _download(url: str) -> bytes:
    print(f"downloading {url} ...")
    request = urllib.request.Request(url, headers={"User-Agent": "nlmclean-build"})
    with urllib.request.urlopen(request, timeout=300) as response:
        return response.read()


def _fetch_windows(dest: Path) -> dict[str, str]:
    data = _download(WIN_URL)
    digest = hashlib.sha256(data).hexdigest()
    print(f"sha256: {digest}")
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        for name in z.namelist():
            if name.rsplit("/", 1)[-1] == "ffmpeg.exe":
                (dest / "ffmpeg.exe").write_bytes(z.read(name))
                break
        else:
            raise RuntimeError("ffmpeg.exe not found in archive")
    return {WIN_URL: digest}


def _fetch_macos(dest: Path) -> dict[str, str]:
    hashes = {}
    for tool, url in MAC_URLS.items():
        data = _download(url)
        digest = hashlib.sha256(data).hexdigest()
        print(f"sha256 ({tool}): {digest}")
        hashes[url] = digest
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for name in z.namelist():
                if name.rsplit("/", 1)[-1] == tool:
                    out = dest / tool
                    out.write_bytes(z.read(name))
                    out.chmod(out.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return hashes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dest", type=Path, default=Path(__file__).parent / "ffmpeg_bin")
    args = parser.parse_args()

    dest: Path = args.dest
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True)

    if sys.platform == "win32":
        hashes = _fetch_windows(dest)
        source = WIN_URL
    elif sys.platform == "darwin":
        hashes = _fetch_macos(dest)
        source = "https://evermeet.cx/ffmpeg/"
    else:
        print("Linux builds use system/imageio ffmpeg; nothing to fetch", file=sys.stderr)
        return 0

    hash_lines = "\n".join(f"  {h}  {u}" for u, h in hashes.items())
    (dest / "LICENSE.ffmpeg.txt").write_text(
        LICENSE_NOTE.format(source=source, hashes=hash_lines), encoding="utf-8"
    )
    print(f"binaries ready in {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
