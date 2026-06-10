"""Probe video metadata. Prefers ffprobe JSON; falls back to parsing `ffmpeg -i`
stderr because imageio-ffmpeg (the dev fallback) ships ffmpeg without ffprobe."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from nlmclean.ffmpeg.locate import find_ffmpeg, find_ffprobe, subprocess_flags


@dataclass
class VideoInfo:
    width: int
    height: int
    fps: float
    duration: float  # seconds
    nb_frames: int
    has_audio: bool
    vfr: bool = False


def probe(path: Path) -> VideoInfo:
    ffprobe = find_ffprobe()
    if ffprobe:
        return _probe_ffprobe(ffprobe, path)
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        return _probe_ffmpeg_stderr(ffmpeg, path)
    raise RuntimeError("ffmpeg/ffprobe not found - install ffmpeg or use a release build")


def _parse_rate(rate: str) -> float:
    try:
        return float(Fraction(rate))
    except (ValueError, ZeroDivisionError):
        return 0.0


def _probe_ffprobe(ffprobe: str, path: Path) -> VideoInfo:
    cmd = [
        ffprobe, "-v", "error",
        "-show_entries",
        "stream=codec_type,width,height,r_frame_rate,avg_frame_rate,nb_frames",
        "-show_entries", "format=duration",
        "-of", "json", str(path),
    ]  # fmt: skip
    out = subprocess.run(
        cmd, capture_output=True, text=True, timeout=60, **subprocess_flags()
    ).stdout
    data = json.loads(out or "{}")

    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if video is None:
        raise ValueError(f"no video stream in {path}")
    has_audio = any(s.get("codec_type") == "audio" for s in data.get("streams", []))

    fps = _parse_rate(video.get("avg_frame_rate", "0/1")) or _parse_rate(
        video.get("r_frame_rate", "0/1")
    )
    duration = float(data.get("format", {}).get("duration") or 0.0)
    nb_frames = int(video.get("nb_frames") or 0) or round(duration * fps)
    vfr = video.get("r_frame_rate") != video.get("avg_frame_rate")

    return VideoInfo(
        width=int(video["width"]),
        height=int(video["height"]),
        fps=fps,
        duration=duration,
        nb_frames=nb_frames,
        has_audio=has_audio,
        vfr=vfr,
    )


_RE_SIZE = re.compile(r"Video:.*?(\d{2,5})x(\d{2,5})")
_RE_FPS = re.compile(r"(\d+(?:\.\d+)?)\s*fps")
_RE_DURATION = re.compile(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)")


def _probe_ffmpeg_stderr(ffmpeg: str, path: Path) -> VideoInfo:
    proc = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path)],
        capture_output=True, text=True, timeout=60, **subprocess_flags(),
    )  # fmt: skip
    err = proc.stderr or ""

    size = _RE_SIZE.search(err)
    if not size:
        raise ValueError(f"could not probe {path}")
    fps_m = _RE_FPS.search(err)
    dur_m = _RE_DURATION.search(err)

    fps = float(fps_m.group(1)) if fps_m else 30.0
    duration = 0.0
    if dur_m:
        hh, mm, ss = dur_m.groups()
        duration = int(hh) * 3600 + int(mm) * 60 + float(ss)

    return VideoInfo(
        width=int(size.group(1)),
        height=int(size.group(2)),
        fps=fps,
        duration=duration,
        nb_frames=round(duration * fps),
        has_audio="Audio:" in err,
    )
