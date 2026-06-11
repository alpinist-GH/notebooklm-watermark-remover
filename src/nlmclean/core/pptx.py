"""PPTX watermark removal via pure zipfile rewrite.

NotebookLM exports each slide as a single full-page PNG in ppt/media/ with the
watermark baked into the image. We rewrite only those images and copy every
other zip entry verbatim - no XML is modified, so nothing else can break.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from pathlib import PurePosixPath

from nlmclean.core.imgio import imdecode_bytes, imencode_bytes
from nlmclean.core.inpaint import inpaint_region
from nlmclean.core.job import Job, ProgressCallback, null_progress
from nlmclean.core.region import Region
from nlmclean.detect import detect_region
from nlmclean.detect.mask import stroke_mask_for_region

_IMAGE_EXTS = {".png", ".jpg", ".jpeg"}
_MIN_SLIDE_WIDTH = 800
_ASPECT_TOLERANCE = 0.05


def _slide_aspect(zin: zipfile.ZipFile) -> float | None:
    try:
        root = ET.fromstring(zin.read("ppt/presentation.xml"))
    except (KeyError, ET.ParseError):
        return None
    ns = {"p": "http://schemas.openxmlformats.org/presentationml/2006/main"}
    sld_sz = root.find("p:sldSz", ns)
    if sld_sz is None:
        return None
    cx, cy = int(sld_sz.get("cx", 0)), int(sld_sz.get("cy", 0))
    return cx / cy if cx and cy else None


def _is_slide_image(width: int, height: int, slide_aspect: float | None) -> bool:
    if width < _MIN_SLIDE_WIDTH or height == 0:
        return False
    if slide_aspect is None:
        return True  # no presentation.xml info - process all large images
    return abs((width / height) - slide_aspect) / slide_aspect <= _ASPECT_TOLERANCE


def clean_pptx(job: Job, progress: ProgressCallback = null_progress) -> None:
    with zipfile.ZipFile(job.src) as zin:
        slide_aspect = _slide_aspect(zin)
        entries = zin.infolist()
        media = [
            e for e in entries
            if e.filename.startswith("ppt/media/")
            and PurePosixPath(e.filename).suffix.lower() in _IMAGE_EXTS
        ]  # fmt: skip

        # detection result reused across same-sized slides (one export = one geometry)
        region_cache: dict[tuple[int, int], Region] = {}
        processed = 0

        with zipfile.ZipFile(job.dst, "w", zipfile.ZIP_DEFLATED) as zout:
            try:
                for entry in entries:
                    job.cancel.raise_if_cancelled()
                    data = zin.read(entry.filename)
                    if entry in media:
                        try:
                            img = imdecode_bytes(data)
                        except ValueError:
                            img = None
                        if img is not None and _is_slide_image(
                            img.shape[1], img.shape[0], slide_aspect
                        ):
                            key = (img.shape[1], img.shape[0])
                            region = job.region or region_cache.get(key)
                            if region is None:
                                region, _conf, _profile = detect_region(img, "doc")
                                region_cache[key] = region
                            cleaned = inpaint_region(
                                img, region, mask=stroke_mask_for_region(img, region, "doc")
                            )
                            ext = PurePosixPath(entry.filename).suffix.lower()
                            data = imencode_bytes(cleaned, ext)
                            processed += 1
                            progress(processed / max(1, len(media)), "cleaning slides")
                    zout.writestr(entry, data)
            except BaseException:
                zout.close()
                job.dst.unlink(missing_ok=True)
                raise

    if processed == 0:
        job.dst.unlink(missing_ok=True)
        raise ValueError("no slide images found - is this a NotebookLM export?")
    progress(1.0, "done")
