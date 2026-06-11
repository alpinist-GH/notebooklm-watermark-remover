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


def test_strip_pptx_metadata(pptx_file, tmp_path):
    core_xml = (
        b'<?xml version="1.0"?><cp:coreProperties xmlns:cp="http://schemas.'
        b'openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc='
        b'"http://purl.org/dc/elements/1.1/"><dc:creator>Secret Author'
        b"</dc:creator></cp:coreProperties>"
    )
    with zipfile.ZipFile(pptx_file, "a") as z:
        z.writestr("docProps/core.xml", core_xml)

    dst = tmp_path / "deck_clean.pptx"
    clean_pptx(Job(src=pptx_file, dst=dst, strip_metadata=True))
    with zipfile.ZipFile(dst) as zout:
        assert b"Secret Author" not in zout.read("docProps/core.xml")
        assert b"coreProperties" in zout.read("docProps/core.xml")  # still valid XML part

    dst_keep = tmp_path / "deck_keep.pptx"
    clean_pptx(Job(src=pptx_file, dst=dst_keep))
    with zipfile.ZipFile(dst_keep) as zout:
        assert b"Secret Author" in zout.read("docProps/core.xml")
