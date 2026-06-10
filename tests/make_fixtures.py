"""Synthesize watermarked test fixtures that mimic NotebookLM export geometry.

A fake "NotebookLM"-style mark is drawn at the exact spot the heuristic
detector expects, so the engine can be exercised end-to-end without real
exports (which we don't commit).
"""

from __future__ import annotations

import subprocess
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

from nlmclean.core.imgio import imencode_bytes
from nlmclean.detect.heuristic import _GEOMETRY, REF_WIDTH

REF_W, REF_H = 1470, 956


def mark_rect(w: int, h: int, kind: str) -> tuple[int, int, int, int]:
    """(x, y, w, h) of the drawn fake watermark - matches heuristic geometry."""
    mark_w, mark_h, right, bottom = _GEOMETRY[kind]
    s = w / REF_WIDTH
    mw, mh = round(mark_w * s), round(mark_h * s)
    return w - round(right * s) - mw, h - round(bottom * s) - mh, mw, mh


def draw_slide(
    w: int = REF_W,
    h: int = REF_H,
    kind: str = "doc",
    *,
    mark: bool = True,
    bg: tuple[int, int, int] = (245, 240, 230),
    title: str = "Slide",
) -> np.ndarray:
    """Render a fake slide as a BGR numpy array."""
    img = Image.new("RGB", (w, h), bg)
    drawer = ImageDraw.Draw(img)
    if w >= 600 and h >= 600:
        # some non-watermark content so "rest of the page unchanged" checks are meaningful
        drawer.rectangle([60, 60, w - 60, 140], fill=(70, 90, 160))
        drawer.text((80, 85), title, fill=(255, 255, 255))
        drawer.rectangle([60, 200, w // 2, h - 200], outline=(120, 120, 120), width=3)

    if mark:
        x, y, mw, mh = mark_rect(w, h, kind)
        drawer.rounded_rectangle([x, y, x + mw, y + mh], radius=8, fill=(40, 40, 40))
        drawer.text((x + 10, y + mh // 3), "NotebookLM", fill=(240, 240, 240))

    return np.asarray(img)[:, :, ::-1].copy()  # RGB -> BGR


def make_image(path: Path, **kwargs) -> np.ndarray:
    img = draw_slide(kind="doc", **kwargs)
    path.write_bytes(imencode_bytes(img, path.suffix or ".png"))
    return img


def make_pdf(path: Path, n_pages: int = 2) -> None:
    pages = [
        Image.fromarray(draw_slide(kind="doc", title=f"Page {i + 1}")[:, :, ::-1])
        for i in range(n_pages)
    ]
    pages[0].save(path, format="PDF", save_all=True, append_images=pages[1:])


_CONTENT_TYPES = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="png" ContentType="image/png"/>
<Default Extension="xml" ContentType="application/xml"/>
</Types>"""

_PRESENTATION_XML = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main">
<p:sldSz cx="12192000" cy="6858000"/>
</p:presentation>"""  # 16:9 in EMU


def make_pptx(path: Path, n_slides: int = 3) -> None:
    # 16:9 slide images to match sldSz; full-page PNGs like a NotebookLM export
    w, h = 1280, 720
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CONTENT_TYPES)
        z.writestr("ppt/presentation.xml", _PRESENTATION_XML)
        for i in range(n_slides):
            img = draw_slide(w, h, kind="doc", title=f"Slide {i + 1}")
            z.writestr(f"ppt/media/image{i + 1}.png", imencode_bytes(img, ".png"))
        # a small non-slide image (logo) that must pass through untouched
        logo = draw_slide(200, 200, kind="doc", mark=False)
        z.writestr("ppt/media/image_logo.png", imencode_bytes(logo, ".png"))


def make_video(path: Path, ffmpeg: str, seconds_per_slide: float = 1.0, fps: int = 10) -> None:
    """Two static slides with the video-geometry mark, plus a sine audio track."""
    w, h = REF_W, REF_H
    slides = [
        draw_slide(w, h, kind="video", title="Video slide 1"),
        draw_slide(w, h, kind="video", title="Video slide 2", bg=(225, 235, 250)),
    ]
    duration = seconds_per_slide * len(slides)
    cmd = [
        ffmpeg, "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "pipe:0",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}",
        "-map", "0:v", "-map", "1:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
        str(path),
    ]  # fmt: skip
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    assert proc.stdin is not None
    frames_per_slide = round(seconds_per_slide * fps)
    for slide in slides:
        raw = slide.tobytes()
        for _ in range(frames_per_slide):
            proc.stdin.write(raw)
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("fixture video encoding failed")
