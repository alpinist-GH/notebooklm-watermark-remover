"""PNG/JPG watermark removal - decode, detect, inpaint, re-encode same format."""

from __future__ import annotations

from nlmclean.core.imgio import imread, imwrite
from nlmclean.core.inpaint import inpaint_region
from nlmclean.core.job import Job, ProgressCallback, null_progress
from nlmclean.detect import detect_region
from nlmclean.detect.mask import stroke_mask_for_region


def clean_image(job: Job, progress: ProgressCallback = null_progress) -> None:
    progress(0.0, "reading image")
    img = imread(job.src)
    region = job.region
    if region is None:
        region, _conf = detect_region(img, "doc")
    job.cancel.raise_if_cancelled()
    progress(0.5, "inpainting")
    cleaned = inpaint_region(img, region, mask=stroke_mask_for_region(img, region, "doc"))
    imwrite(job.dst, cleaned)
    progress(1.0, "done")
