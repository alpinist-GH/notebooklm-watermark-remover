"""Build a preview image + detected region for any supported file.

The GUI shows one representative frame/page/slide per file and lets the user
adjust the detected rectangle on it. `region_scale` converts coordinates from
that preview image into the units the format handler expects in Job.region
(PDF handlers take page points; the preview is rendered at 2x).
"""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from pathlib import PurePosixPath

import numpy as np

from nlmclean.core.dispatch import kind_of
from nlmclean.core.imgio import imdecode_bytes, imread
from nlmclean.core.region import Region
from nlmclean.detect import detect_region


@dataclass
class Inspection:
    kind: str
    preview: np.ndarray  # BGR
    region: Region  # in preview-image coordinates
    confidence: float
    region_scale: float  # multiply preview coords by this to get Job.region coords


def inspect_file(path) -> Inspection:
    kind = kind_of(path)
    if kind is None:
        raise ValueError(f"unsupported file type: {path.suffix}")

    if kind == "video":
        from nlmclean.core.video import detect_video_region
        from nlmclean.ffmpeg.probe import probe
        from nlmclean.ffmpeg.runner import extract_frame

        info = probe(path)
        preview = imdecode_bytes(extract_frame(path, min(1.0, info.duration / 2)))
        region, conf = detect_video_region(path, info)
        return Inspection("video", preview, region, conf, 1.0)

    if kind == "pdf":
        from nlmclean.core.pdf import _DETECT_SCALE, _render_page_bgr

        preview = _render_page_bgr(path.read_bytes(), 0, _DETECT_SCALE)
        region, conf = detect_region(preview, "doc")
        return Inspection("pdf", preview, region, conf, 1.0 / _DETECT_SCALE)

    if kind == "pptx":
        preview = _first_slide_image(path)
        region, conf = detect_region(preview, "doc")
        return Inspection("pptx", preview, region, conf, 1.0)

    preview = imread(path)
    region, conf = detect_region(preview, "doc")
    return Inspection("image", preview, region, conf, 1.0)


def _first_slide_image(path) -> np.ndarray:
    from nlmclean.core.pptx import _IMAGE_EXTS, _MIN_SLIDE_WIDTH

    with zipfile.ZipFile(path) as z:
        for name in z.namelist():
            if not name.startswith("ppt/media/"):
                continue
            if PurePosixPath(name).suffix.lower() not in _IMAGE_EXTS:
                continue
            try:
                img = imdecode_bytes(z.read(name))
            except ValueError:
                continue
            if img.shape[1] >= _MIN_SLIDE_WIDTH:
                return img
    raise ValueError("no slide images found in PPTX")
