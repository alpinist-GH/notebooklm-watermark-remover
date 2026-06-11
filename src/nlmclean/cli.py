"""Command-line interface: nlmclean FILES... [options]"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from nlmclean import __version__
from nlmclean.core.dispatch import DEFAULT_SUFFIX, default_output, process_job
from nlmclean.core.job import Job
from nlmclean.core.region import Region


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nlmclean",
        description=(
            "Remove the NotebookLM watermark from exported MP4 videos, PDFs, "
            "PPTX slides, and PNG/JPG images. Runs fully locally."
        ),
    )
    parser.add_argument("files", nargs="+", type=Path, metavar="FILE")
    parser.add_argument(
        "--mode",
        choices=["fast", "quality"],
        default="fast",
        help="video removal mode: fast = ffmpeg delogo, quality = per-frame inpainting "
        "(default: fast)",
    )
    parser.add_argument(
        "--region",
        type=Region.parse,
        default=None,
        metavar="X,Y,W,H",
        help="explicit watermark rectangle in pixels - skips auto-detection",
    )
    parser.add_argument(
        "--detect",
        choices=["auto", "universal"],
        default="auto",
        help="video watermark detection: auto = NotebookLM/Gemini templates, "
        "universal = find any static watermark by comparing frames over time "
        "(default: auto)",
    )
    parser.add_argument(
        "--strip-metadata",
        action="store_true",
        help="also remove metadata from outputs (EXIF, PDF info/XMP, PPTX "
        "document properties, video container tags)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=None,
        help="write outputs here instead of next to each input",
    )
    parser.add_argument(
        "--suffix",
        default=DEFAULT_SUFFIX,
        help=f"output filename suffix (default: {DEFAULT_SUFFIX})",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    failures = 0
    for src in args.files:
        dst = default_output(src, args.output_dir, args.suffix)
        job = Job(
            src=src,
            dst=dst,
            mode=args.mode,
            detect=args.detect,
            region=args.region,
            strip_metadata=args.strip_metadata,
        )

        last = {"pct": -1}

        def show_progress(fraction: float, stage: str, _last=last, _src=src) -> None:
            pct = int(fraction * 100)
            if pct != _last["pct"]:
                _last["pct"] = pct
                print(f"\r{_src.name}: {stage} {pct:3d}%", end="", flush=True)

        result = process_job(job, show_progress)
        print()
        if result.ok:
            print(f"{src.name} -> {result.dst}")
        else:
            failures += 1
            print(f"{src.name}: FAILED - {result.message}", file=sys.stderr)

    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
