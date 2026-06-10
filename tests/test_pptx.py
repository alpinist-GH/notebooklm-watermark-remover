import zipfile

from nlmclean.core.imgio import imdecode_bytes
from nlmclean.core.job import Job
from nlmclean.core.pptx import clean_pptx
from tests.helpers import assert_watermark_removed


def test_clean_pptx(pptx_file, tmp_path):
    dst = tmp_path / "deck_clean.pptx"
    clean_pptx(Job(src=pptx_file, dst=dst))

    with zipfile.ZipFile(pptx_file) as zin, zipfile.ZipFile(dst) as zout:
        assert zin.namelist() == zout.namelist(), "zip structure must be preserved"
        # XML entries copied verbatim
        assert zin.read("ppt/presentation.xml") == zout.read("ppt/presentation.xml")
        # every slide image cleaned
        for name in zin.namelist():
            if name.startswith("ppt/media/image") and "logo" not in name:
                before = imdecode_bytes(zin.read(name))
                after = imdecode_bytes(zout.read(name))
                assert_watermark_removed(before, after, "doc")
        # the small non-slide image must be untouched
        assert zin.read("ppt/media/image_logo.png") == zout.read("ppt/media/image_logo.png")
