"""PNG/JPG watermark removal - decode, detect, inpaint, re-encode same format.

Images carry either the NotebookLM wordmark (slides, infographics) or the
Gemini sparkle (AI-generated photos and infographics); detection tries both
profiles and the best match wins.
"""

from __future__ import annotations

from nlmclean.core.imgio import imread, imwrite
from nlmclean.core.inpaint import inpaint_region
from nlmclean.core.job import Job, ProgressCallback, null_progress
from nlmclean.detect import detect_region
from nlmclean.detect.mask import stroke_mask_for_kind, stroke_mask_for_region


def clean_image(job: Job, progress: ProgressCallback = null_progress) -> None:
    progress(0.0, "reading image")
    img = imread(job.src)
    region = job.region
    profile = job.profile
    if region is None:
        region, _conf, profile = detect_region(img, "image")
    job.cancel.raise_if_cancelled()
    progress(0.5, "inpainting")
    if profile is not None:
        mask = stroke_mask_for_region(img, region, profile)
    else:  # manual region without a known profile: first aligning template wins
        mask = stroke_mask_for_kind(img, region, "image")
    cleaned = inpaint_region(img, region, mask=mask)
    # imgio re-encodes pixels only - EXIF/XMP never survives, so Job.strip_metadata
    # is implicitly always honored for images (asserted by test_image.py)
    imwrite(job.dst, cleaned)
    progress(1.0, "done")
