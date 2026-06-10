"""Route files to format handlers and run jobs to a JobResult."""

from __future__ import annotations

from pathlib import Path

from nlmclean.core.job import CancelledError, Job, JobResult, ProgressCallback, null_progress

VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
PDF_EXTS = {".pdf"}
PPTX_EXTS = {".pptx"}
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
SUPPORTED_EXTS = VIDEO_EXTS | PDF_EXTS | PPTX_EXTS | IMAGE_EXTS

DEFAULT_SUFFIX = "_clean"


def kind_of(path: Path) -> str | None:
    ext = path.suffix.lower()
    if ext in VIDEO_EXTS:
        return "video"
    if ext in PDF_EXTS:
        return "pdf"
    if ext in PPTX_EXTS:
        return "pptx"
    if ext in IMAGE_EXTS:
        return "image"
    return None


def default_output(src: Path, out_dir: Path | None = None, suffix: str = DEFAULT_SUFFIX) -> Path:
    directory = out_dir if out_dir is not None else src.parent
    return directory / f"{src.stem}{suffix}{src.suffix}"


def process_job(job: Job, progress: ProgressCallback = null_progress) -> JobResult:
    kind = kind_of(job.src)
    if kind is None:
        return JobResult(ok=False, message=f"unsupported file type: {job.src.suffix}")
    if not job.src.exists():
        return JobResult(ok=False, message=f"file not found: {job.src}")

    # imported lazily so e.g. a missing ffmpeg doesn't break document handling
    try:
        if kind == "video":
            from nlmclean.core.video import clean_video as handler
        elif kind == "pdf":
            from nlmclean.core.pdf import clean_pdf as handler
        elif kind == "pptx":
            from nlmclean.core.pptx import clean_pptx as handler
        else:
            from nlmclean.core.image import clean_image as handler

        job.dst.parent.mkdir(parents=True, exist_ok=True)
        handler(job, progress)
        return JobResult(ok=True, dst=job.dst)
    except CancelledError:
        return JobResult(ok=False, message="cancelled")
    except Exception as exc:  # surfaced to CLI stderr / GUI tooltip
        return JobResult(ok=False, message=str(exc))
