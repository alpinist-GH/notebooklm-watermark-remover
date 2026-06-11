"""PDF watermark removal with three strategies per page, first success wins.

A. Object removal - the watermark is a small drawn XObject in the bottom-right
   corner: walk the content stream tracking the CTM, drop the matching `Do` ops.
   Verified by render-diffing the first treated page; on failure everything is
   restored and we fall through.
B. Embedded-image patch - the common NotebookLM case: each page is one full-page
   image with the watermark baked in. Extract it, inpaint, write back in place.
C. Render-patch overlay - always works: render just the watermark rect, inpaint
   it, and draw the patch over the page as a new image XObject.

pikepdf (MPL-2.0) does the object surgery; pypdfium2 (Apache/BSD) does the
rendering. PyMuPDF is deliberately not used (AGPL).
"""

from __future__ import annotations

import io
import zlib
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import pikepdf
import pypdfium2 as pdfium
from pikepdf import Name
from PIL import Image

from nlmclean.core.inpaint import inpaint_region, inpaint_roi
from nlmclean.core.job import Job, ProgressCallback, null_progress
from nlmclean.core.region import Region
from nlmclean.detect import detect_region
from nlmclean.detect.mask import stroke_mask_for_region

_DETECT_SCALE = 2.0
_PATCH_SCALE = 2.0
_JPEG_QUALITY = 92
_ROI_HALO = 8


@dataclass
class _PageGeometry:
    width: float  # page points
    height: float
    region: Region  # watermark rect in top-down page points


# ---------------------------------------------------------------- rendering


def _render_page_bgr(pdf_bytes: bytes, page_index: int, scale: float) -> np.ndarray:
    doc = pdfium.PdfDocument(pdf_bytes)
    try:
        bitmap = doc[page_index].render(scale=scale, rev_byteorder=True)  # RGB(A)
        arr = bitmap.to_numpy()
    finally:
        doc.close()
    if arr.ndim == 2:
        return cv2.cvtColor(arr, cv2.COLOR_GRAY2BGR)
    if arr.shape[2] == 4:
        return cv2.cvtColor(arr, cv2.COLOR_RGBA2BGR)
    return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)


def _page_size(page: pikepdf.Page) -> tuple[float, float]:
    box = [float(v) for v in page.mediabox]
    return box[2] - box[0], box[3] - box[1]


def _detect_geometry(
    pdf_bytes: bytes, page: pikepdf.Page, explicit: Region | None
) -> _PageGeometry:
    pw, ph = _page_size(page)
    if explicit is not None:
        return _PageGeometry(pw, ph, explicit)
    img = _render_page_bgr(pdf_bytes, 0, _DETECT_SCALE)
    region_img, _conf, _profile = detect_region(img, "doc")
    return _PageGeometry(pw, ph, region_img.scaled(1.0 / _DETECT_SCALE))


def _region_for_page(geom: _PageGeometry, page: pikepdf.Page) -> tuple[Region, float, float]:
    """Scale the page-1 region to this page's size (exports are uniform, but be safe)."""
    pw, ph = _page_size(page)
    region = geom.region if pw == geom.width else geom.region.scaled(pw / geom.width)
    return region, pw, ph


# ---------------------------------------------------------------- strategy A


def _xobject_bbox(ctm: np.ndarray, xobj) -> tuple[float, float, float, float] | None:
    """Drawn bbox (x0, y0_up, w, h) in page points of an XObject under the given CTM."""
    if xobj.get(Name.Subtype) == Name.Image:
        corners = [(0, 0), (1, 0), (1, 1), (0, 1)]
    elif xobj.get(Name.Subtype) == Name.Form and Name.BBox in xobj:
        b = [float(v) for v in xobj.BBox]
        corners = [(b[0], b[1]), (b[2], b[1]), (b[2], b[3]), (b[0], b[3])]
    else:
        return None
    pts = np.array([[x, y, 1.0] for x, y in corners]) @ ctm
    x0, y0 = pts[:, 0].min(), pts[:, 1].min()
    return x0, y0, pts[:, 0].max() - x0, pts[:, 1].max() - y0


def _matrix(operands) -> np.ndarray:
    a, b, c, d, e, f = (float(v) for v in operands)
    return np.array([[a, b, 0.0], [c, d, 0.0], [e, f, 1.0]])


def _try_object_removal(pdf: pikepdf.Pdf, page: pikepdf.Page, geom: _PageGeometry) -> bool:
    """Remove small bottom-right XObject draws. Returns True if anything was removed."""
    region, pw, ph = _region_for_page(geom, page)
    # detected region is top-down; convert to y-up page coords for bbox intersection
    ry0_up = ph - (region.y + region.h)
    xobjects = page.resources.get(Name.XObject, None) if Name.Resources in page else None
    if xobjects is None:
        xobjects = page.get(Name.Resources, pikepdf.Dictionary()).get(Name.XObject, None)
    if xobjects is None:
        return False

    try:
        ops = pikepdf.parse_content_stream(page)
    except pikepdf.PdfError:
        return False

    ctm = np.eye(3)
    stack: list[np.ndarray] = []
    kept = []
    removed_names: list[Name] = []
    for instruction in ops:
        operator = str(instruction.operator)
        if operator == "q":
            stack.append(ctm.copy())
        elif operator == "Q":
            ctm = stack.pop() if stack else np.eye(3)
        elif operator == "cm":
            try:
                ctm = _matrix(instruction.operands) @ ctm
            except (TypeError, ValueError):
                pass
        elif operator == "Do":
            name = instruction.operands[0]
            xobj = xobjects.get(name)
            bbox = _xobject_bbox(ctm, xobj) if xobj is not None else None
            if bbox is not None:
                bx, by, bw, bh = bbox
                small = bw < 0.20 * pw and bh < 0.20 * ph
                overlaps = (
                    bx < region.x + region.w
                    and bx + bw > region.x
                    and by < ry0_up + region.h
                    and by + bh > ry0_up
                )
                if small and overlaps:
                    removed_names.append(name)
                    continue  # drop this draw op
        kept.append(instruction)

    if not removed_names:
        return False

    page.Contents = pdf.make_stream(pikepdf.unparse_content_stream(kept))
    # drop XObjects that are no longer referenced anywhere in the kept stream
    still_used = {
        str(ins.operands[0]) for ins in kept if str(ins.operator) == "Do" and ins.operands
    }
    for name in removed_names:
        if str(name) not in still_used and name in xobjects:
            del xobjects[name]
    return True


def _verify_page(original: bytes, modified: bytes, page_index: int, geom: _PageGeometry) -> bool:
    """Only the watermark region may change; the rest of the page must be identical."""
    before = _render_page_bgr(original, page_index, _DETECT_SCALE)
    after = _render_page_bgr(modified, page_index, _DETECT_SCALE)
    if before.shape != after.shape:
        return False
    diff = cv2.absdiff(before, after).mean(axis=2)
    r = geom.region.scaled(_DETECT_SCALE).padded(4).clamped(diff.shape[1], diff.shape[0])
    inside = diff[r.y : r.y + r.h, r.x : r.x + r.w]
    outside = diff.copy()
    outside[r.y : r.y + r.h, r.x : r.x + r.w] = 0
    changed_inside = float(inside.mean()) > 0.5  # something was actually removed
    clean_outside = float(outside.mean()) < 1.0
    return changed_inside and clean_outside


# ---------------------------------------------------------------- strategy B


def _dominant_image(page: pikepdf.Page) -> tuple[Name, pikepdf.Object] | None:
    xobjects = page.get(Name.Resources, pikepdf.Dictionary()).get(Name.XObject, None)
    if xobjects is None:
        return None
    pw, ph = _page_size(page)
    page_aspect = pw / ph
    best: tuple[int, Name, pikepdf.Object] | None = None
    for name, xobj in xobjects.items():
        if xobj.get(Name.Subtype) != Name.Image:
            continue
        w, h = int(xobj.get(Name.Width, 0)), int(xobj.get(Name.Height, 0))
        if w < 800 or h == 0:
            continue
        if abs((w / h) - page_aspect) / page_aspect > 0.10:
            continue
        if best is None or w * h > best[0]:
            best = (w * h, Name(name), xobj)
    return (best[1], best[2]) if best else None


def _try_image_patch(page: pikepdf.Page, geom: _PageGeometry) -> bool:
    found = _dominant_image(page)
    if found is None:
        return False
    _name, xobj = found
    try:
        pil = pikepdf.PdfImage(xobj).as_pil_image().convert("RGB")
    except Exception:
        return False

    region, pw, _ph = _region_for_page(geom, page)
    img = cv2.cvtColor(np.asarray(pil), cv2.COLOR_RGB2BGR)
    # detection ran on the page render; rerunning on the actual embedded image is
    # more accurate when its resolution differs from the render
    region_px, conf, _profile = detect_region(img, "doc")
    if conf < 0.5:
        region_px = region.scaled(img.shape[1] / pw)

    cleaned = inpaint_region(img, region_px, mask=stroke_mask_for_region(img, region_px, "doc"))
    rgb = cv2.cvtColor(cleaned, cv2.COLOR_BGR2RGB)

    original_filter = xobj.get(Name.Filter)
    is_jpeg = original_filter == Name.DCTDecode or (
        isinstance(original_filter, pikepdf.Array) and Name.DCTDecode in original_filter
    )
    if is_jpeg:
        buf = io.BytesIO()
        Image.fromarray(rgb).save(buf, format="JPEG", quality=_JPEG_QUALITY)
        xobj.write(buf.getvalue(), filter=Name.DCTDecode)
    else:
        xobj.write(zlib.compress(rgb.tobytes()), filter=Name.FlateDecode)
    xobj.Width = rgb.shape[1]
    xobj.Height = rgb.shape[0]
    xobj.ColorSpace = Name.DeviceRGB
    xobj.BitsPerComponent = 8
    if Name.DecodeParms in xobj:
        del xobj[Name.DecodeParms]
    return True


# ---------------------------------------------------------------- strategy C


def _overlay_patch(
    pdf: pikepdf.Pdf, pdf_bytes: bytes, page: pikepdf.Page, page_index: int, geom: _PageGeometry
) -> None:
    region, _pw, ph = _region_for_page(geom, page)
    rendered = _render_page_bgr(pdf_bytes, page_index, _PATCH_SCALE)
    roi_rect = (
        region.scaled(_PATCH_SCALE).padded(_ROI_HALO).clamped(rendered.shape[1], rendered.shape[0])
    )
    roi = rendered[roi_rect.y : roi_rect.y + roi_rect.h, roi_rect.x : roi_rect.x + roi_rect.w]
    patch = inpaint_roi(roi, mask=stroke_mask_for_region(rendered, roi_rect, "doc"))

    buf = io.BytesIO()
    Image.fromarray(cv2.cvtColor(patch, cv2.COLOR_BGR2RGB)).save(
        buf, format="JPEG", quality=_JPEG_QUALITY
    )
    stream = pikepdf.Stream(pdf, buf.getvalue())
    stream.Type = Name.XObject
    stream.Subtype = Name.Image
    stream.Width = patch.shape[1]
    stream.Height = patch.shape[0]
    stream.ColorSpace = Name.DeviceRGB
    stream.BitsPerComponent = 8
    stream.Filter = Name.DCTDecode
    name = page.add_resource(stream, Name.XObject, prefix="NLMPatch")

    # patch rect back to page points, y-up for the placement matrix
    x_pt = roi_rect.x / _PATCH_SCALE
    w_pt = roi_rect.w / _PATCH_SCALE
    h_pt = roi_rect.h / _PATCH_SCALE
    y_pt_up = ph - (roi_rect.y / _PATCH_SCALE) - h_pt
    content = f"q {w_pt:.2f} 0 0 {h_pt:.2f} {x_pt:.2f} {y_pt_up:.2f} cm {name} Do Q"
    page.contents_add(pikepdf.Stream(pdf, content.encode("ascii")), prepend=False)


# ---------------------------------------------------------------- entry point


def strip_pdf_metadata(pdf: pikepdf.Pdf) -> None:
    """Drop the document info dictionary and the XMP metadata stream."""
    if Name.Info in pdf.trailer:
        del pdf.trailer[Name.Info]
    if Name.Metadata in pdf.Root:
        del pdf.Root[Name.Metadata]


def clean_pdf(job: Job, progress: ProgressCallback = null_progress) -> None:
    pdf_bytes = Path(job.src).read_bytes()
    with pikepdf.open(io.BytesIO(pdf_bytes)) as pdf:
        if len(pdf.pages) == 0:
            raise ValueError("empty PDF")

        progress(0.0, "detecting watermark")
        geom = _detect_geometry(pdf_bytes, pdf.pages[0], job.region)

        # Strategy A is verified once on the first page it changes (a generator
        # draws every page the same way); on failure it's disabled for the doc.
        object_removal_ok: bool | None = None
        total = len(pdf.pages)

        for i, page in enumerate(pdf.pages):
            job.cancel.raise_if_cancelled()
            original_contents = page.get(Name.Contents)

            done = False
            if object_removal_ok is not False:
                try:
                    done = _try_object_removal(pdf, page, geom)
                except Exception:
                    done = False
                if done and object_removal_ok is None:
                    buf = io.BytesIO()
                    pdf.save(buf)
                    object_removal_ok = _verify_page(pdf_bytes, buf.getvalue(), i, geom)
                    if not object_removal_ok:
                        if original_contents is not None:
                            page.Contents = original_contents
                        done = False

            if not done:
                try:
                    done = _try_image_patch(page, geom)
                except Exception:
                    done = False
            if not done:
                _overlay_patch(pdf, pdf_bytes, page, i, geom)

            progress((i + 1) / total, "cleaning pages")

        if job.strip_metadata:
            strip_pdf_metadata(pdf)
        pdf.save(str(job.dst))
    progress(1.0, "done")
