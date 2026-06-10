"""Video watermark removal.

Two modes:
- fast: single ffmpeg pass with the `delogo` filter (near-instant, slight blur patch)
- quality: decode raw frames over a pipe, OpenCV-inpaint the watermark ROI, re-encode.
  NotebookLM videos are mostly still slides, so inpainted patches are cached by ROI
  hash - the typical hit rate is >95% and the bottleneck becomes x264 encoding.
"""

from __future__ import annotations

import hashlib
import subprocess
from collections import OrderedDict
from pathlib import Path

import numpy as np

from nlmclean.core.imgio import imdecode_bytes
from nlmclean.core.inpaint import inpaint_roi
from nlmclean.core.job import CancelledError, Job, ProgressCallback, null_progress
from nlmclean.core.region import Region
from nlmclean.detect import detect_region
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
        region, conf = detect_region(frame, "video")
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
    if region is None:
        progress(0.0, "detecting watermark")
        region, _conf = detect_video_region(job.src, info)
    # delogo rejects rects touching the frame border
    region = region.clamped(info.width, info.height, margin=1)

    if job.mode == "quality":
        _clean_quality(job, info, region, progress)
    else:
        _clean_fast(job, info, region, progress)


def _clean_fast(job: Job, info: VideoInfo, region: Region, progress: ProgressCallback) -> None:
    vf = f"delogo=x={region.x}:y={region.y}:w={region.w}:h={region.h}"
    if info.vfr:
        vf += ",fps=source_fps"  # normalize odd VFR exports
    args = [
        "-i", str(job.src),
        "-vf", vf,
        "-map", "0:v:0", "-map", "0:a?",
        "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-movflags", "+faststart",
        str(job.dst),
    ]  # fmt: skip
    run_ffmpeg(
        args,
        duration=info.duration,
        output=job.dst,
        progress=progress,
        cancel=job.cancel,
        stage="removing watermark (fast)",
    )


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


def _clean_quality(job: Job, info: VideoInfo, region: Region, progress: ProgressCallback) -> None:
    exe = find_ffmpeg()
    if not exe:
        raise RuntimeError("ffmpeg not found")
    w, h = info.width, info.height
    frame_bytes = w * h * 3
    roi = region.padded(ROI_HALO).clamped(w, h)

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
        str(job.dst),
    ]  # fmt: skip

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
                patch = inpaint_roi(crop)
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
