"""Video watermark removal.

Two modes:
- fast: single ffmpeg pass - `removelogo` with a pixel-exact stroke mask when the
  template aligns (only the ~750 wordmark pixels are touched), `delogo` rectangle
  fallback otherwise
- quality: decode raw frames over a pipe, OpenCV-inpaint the watermark strokes,
  re-encode. NotebookLM videos are mostly still slides, so inpainted patches are
  cached by ROI hash - the typical hit rate is >95% and the bottleneck becomes
  x264 encoding.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
from collections import OrderedDict
from pathlib import Path

import numpy as np

from nlmclean.core.imgio import imdecode_bytes, imwrite
from nlmclean.core.inpaint import inpaint_roi
from nlmclean.core.job import CancelledError, Job, ProgressCallback, null_progress
from nlmclean.core.region import Region
from nlmclean.detect import detect_region
from nlmclean.detect.mask import refine_mask_temporal, stroke_mask_for_region
from nlmclean.ffmpeg.locate import find_ffmpeg, subprocess_flags
from nlmclean.ffmpeg.probe import VideoInfo, probe
from nlmclean.ffmpeg.runner import extract_frame, run_ffmpeg

ROI_HALO = 6
_CACHE_MAX = 64


def detect_video_region(src: Path, info: VideoInfo) -> tuple[Region, float]:
    """Sample 5 frames evenly, detect on each, take the median rect."""
    times = [info.duration * t for t in (0.1, 0.3, 0.5, 0.7, 0.9)] if info.duration else [0.0]
    rects: list[Region] = []
    confidences: list[float] = []
    for t in times:
        try:
            frame = imdecode_bytes(extract_frame(src, t))
        except Exception:
            continue
        region, conf, _profile = detect_region(frame, "video")
        rects.append(region)
        confidences.append(conf)
    if not rects:
        raise ValueError(f"could not decode any frame from {src}")
    med = Region(
        x=int(np.median([r.x for r in rects])),
        y=int(np.median([r.y for r in rects])),
        w=int(np.median([r.w for r in rects])),
        h=int(np.median([r.h for r in rects])),
    )
    return med.clamped(info.width, info.height), float(np.median(confidences))


def clean_video(job: Job, progress: ProgressCallback = null_progress) -> None:
    info = probe(job.src)
    region = job.region
    mask: np.ndarray | None = None
    if job.detect == "universal":
        from nlmclean.detect.universal import detect_static_overlay

        progress(0.0, "detecting watermark (universal)")
        found, frame_mask, conf = detect_static_overlay(job.src, info)
        if region is None:
            if found is None or conf < 0.5:
                raise ValueError(
                    "no static watermark found - universal detection needs moving "
                    "footage; draw the region manually instead"
                )
            region = found
        # an explicit region (manual or pre-detected) wins; the temporal mask
        # still gives stroke precision inside it when it was trustworthy
        region = region.clamped(info.width, info.height, margin=1)
        if frame_mask is not None and conf >= 0.5:
            crop = frame_mask[region.y : region.y + region.h, region.x : region.x + region.w]
            if crop.any():
                mask = crop
    elif region is None:
        progress(0.0, "detecting watermark")
        region, _conf = detect_video_region(job.src, info)
    # delogo (the fast-mode fallback) rejects rects touching the frame border
    region = region.clamped(info.width, info.height, margin=1)

    if mask is None:
        mask = _stroke_mask(job.src, info, region)
    if job.mode == "quality":
        _clean_quality(job, info, region, mask, progress)
    else:
        _clean_fast(job, info, region, mask, progress)


def _stroke_mask(src: Path, info: VideoInfo, region: Region) -> np.ndarray | None:
    """Region-sized stroke mask, refined against the video, or None (rect fallback)."""
    try:
        frame = imdecode_bytes(extract_frame(src, info.duration * 0.5 if info.duration else 0.0))
    except Exception:
        return None
    mask = stroke_mask_for_region(frame, region, "video")
    if mask is None:
        return None
    return refine_mask_temporal(src, info, region, mask)


def _filter_path(path: Path) -> str:
    """Escape a filename for use inside an ffmpeg filter option value."""
    return "'" + path.as_posix().replace(":", "\\:") + "'"


def _clean_fast(
    job: Job,
    info: VideoInfo,
    region: Region,
    mask: np.ndarray | None,
    progress: ProgressCallback,
) -> None:
    mask_file: Path | None = None
    if mask is not None:
        # removelogo interpolates only the white mask pixels - no rectangle blur
        frame_mask = np.zeros((info.height, info.width), np.uint8)
        frame_mask[region.y : region.y + region.h, region.x : region.x + region.w] = mask
        fd, tmp_name = tempfile.mkstemp(prefix="nlmclean_mask_", suffix=".png")
        os.close(fd)
        mask_file = Path(tmp_name)
        imwrite(mask_file, frame_mask)
        vf = f"removelogo=f={_filter_path(mask_file)}"
    else:
        vf = f"delogo=x={region.x}:y={region.y}:w={region.w}:h={region.h}"
    if info.vfr:
        vf += ",fps=source_fps"  # normalize odd VFR exports
    args = [
        "-i", str(job.src),
        "-vf", vf,
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-movflags", "+faststart",
    ]  # fmt: skip
    if job.strip_metadata:
        args += ["-map_metadata", "-1"]
    args.append(str(job.dst))
    try:
        run_ffmpeg(
            args,
            duration=info.duration,
            output=job.dst,
            progress=progress,
            cancel=job.cancel,
            stage="removing watermark (fast)",
        )
    finally:
        if mask_file is not None:
            mask_file.unlink(missing_ok=True)


def _read_exact(stream, n: int) -> bytes | None:
    chunks = []
    remaining = n
    while remaining > 0:
        chunk = stream.read(remaining)
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def _clean_quality(
    job: Job,
    info: VideoInfo,
    region: Region,
    mask: np.ndarray | None,
    progress: ProgressCallback,
) -> None:
    exe = find_ffmpeg()
    if not exe:
        raise RuntimeError("ffmpeg not found")
    w, h = info.width, info.height
    frame_bytes = w * h * 3
    roi = region.padded(ROI_HALO).clamped(w, h)

    roi_mask: np.ndarray | None = None
    if mask is not None:
        roi_mask = np.zeros((roi.h, roi.w), np.uint8)
        ox, oy = region.x - roi.x, region.y - roi.y
        roi_mask[oy : oy + mask.shape[0], ox : ox + mask.shape[1]] = mask

    decode_cmd = [
        exe, "-v", "error", "-i", str(job.src),
        "-map", "0:v:0", "-f", "rawvideo", "-pix_fmt", "bgr24", "pipe:1",
    ]  # fmt: skip
    encode_cmd = [
        exe, "-y", "-v", "error",
        "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}",
        "-r", f"{info.fps:.6f}", "-i", "pipe:0",
        "-i", str(job.src),
        "-map", "0:v", "-map", "1:a?",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-movflags", "+faststart", "-shortest",
    ]  # fmt: skip
    if job.strip_metadata:
        encode_cmd += ["-map_metadata", "-1"]
    encode_cmd.append(str(job.dst))

    decoder = subprocess.Popen(
        decode_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, **subprocess_flags()
    )
    encoder = subprocess.Popen(
        encode_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        **subprocess_flags(),
    )

    # LRU of inpainted patches keyed by ROI content hash - slides repeat for seconds at a time
    cache: OrderedDict[bytes, np.ndarray] = OrderedDict()
    frames_done = 0
    total = max(1, info.nb_frames)

    try:
        assert decoder.stdout is not None and encoder.stdin is not None
        while True:
            if job.cancel.cancelled:
                raise CancelledError()
            raw = _read_exact(decoder.stdout, frame_bytes)
            if raw is None:
                break
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(h, w, 3).copy()
            crop = frame[roi.y : roi.y + roi.h, roi.x : roi.x + roi.w]

            key = hashlib.blake2b(crop.tobytes(), digest_size=16).digest()
            patch = cache.get(key)
            if patch is None:
                patch = inpaint_roi(crop, mask=roi_mask)
                cache[key] = patch
                if len(cache) > _CACHE_MAX:
                    cache.popitem(last=False)
            else:
                cache.move_to_end(key)

            frame[roi.y : roi.y + roi.h, roi.x : roi.x + roi.w] = patch
            encoder.stdin.write(frame.tobytes())

            frames_done += 1
            if frames_done % 15 == 0:
                progress(min(1.0, frames_done / total), "removing watermark (quality)")

        encoder.stdin.close()
        decoder.wait()
        code = encoder.wait()
        if code != 0:
            job.dst.unlink(missing_ok=True)
            raise RuntimeError(f"ffmpeg encoder failed (exit {code})")
        out_info = probe(job.dst)
        if info.duration and abs(out_info.duration - info.duration) > 0.5:
            raise RuntimeError(
                f"output duration {out_info.duration:.2f}s does not match "
                f"input {info.duration:.2f}s"
            )
        progress(1.0, "done")
    except CancelledError:
        # kill before unlink - Windows can't delete a file the encoder still has open
        for proc in (decoder, encoder):
            if proc.poll() is None:
                proc.kill()
                proc.wait()
        job.dst.unlink(missing_ok=True)
        raise
    finally:
        for proc in (decoder, encoder):
            if proc.poll() is None:
                proc.kill()
                proc.wait()
