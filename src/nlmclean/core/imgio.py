"""Unicode-safe image IO.

cv2.imread/imwrite fail silently on Windows paths with non-ASCII characters,
so all disk IO goes through numpy buffers + imdecode/imencode instead.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np


def imread(path: Path | str) -> np.ndarray:
    data = np.fromfile(str(path), dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError(f"could not decode image: {path}")
    return img


def imdecode_bytes(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ValueError("could not decode image bytes")
    return img


def imencode_bytes(img: np.ndarray, ext: str, *, jpeg_quality: int = 95) -> bytes:
    params: list[int] = []
    if ext.lower() in (".jpg", ".jpeg"):
        params = [cv2.IMWRITE_JPEG_QUALITY, jpeg_quality]
    ok, buf = cv2.imencode(ext, img, params)
    if not ok:
        raise ValueError(f"could not encode image as {ext}")
    return buf.tobytes()


def imwrite(path: Path | str, img: np.ndarray, *, jpeg_quality: int = 95) -> None:
    ext = Path(path).suffix or ".png"
    Path(path).write_bytes(imencode_bytes(img, ext, jpeg_quality=jpeg_quality))
