import pikepdf

from nlmclean.core.job import Job
from nlmclean.core.pdf import _render_page_bgr, clean_pdf
from tests.helpers import assert_watermark_removed


def test_clean_pdf(pdf_file, tmp_path):
    dst = tmp_path / "deck_clean.pdf"
    clean_pdf(Job(src=pdf_file, dst=dst))

    with pikepdf.open(dst) as cleaned:
        n_pages = len(cleaned.pages)
    with pikepdf.open(pdf_file) as original:
        assert n_pages == len(original.pages)

    before_bytes = pdf_file.read_bytes()
    after_bytes = dst.read_bytes()
    for i in range(n_pages):
        before = _render_page_bgr(before_bytes, i, 2.0)
        after = _render_page_bgr(after_bytes, i, 2.0)
        assert before.shape == after.shape
        # rendering/JPEG round-trips are lossy; the structural check still holds
        assert_watermark_removed(before, after, "doc", max_outside=6.0)


def test_strip_pdf_metadata(pdf_file, tmp_path):
    # give the fixture real metadata first
    tagged = tmp_path / "tagged.pdf"
    with pikepdf.open(pdf_file) as pdf:
        with pdf.open_metadata() as meta:
            meta["dc:creator"] = ["Test Author"]
        pdf.docinfo["/Title"] = "Secret Title"
        pdf.save(tagged)

    dst = tmp_path / "tagged_clean.pdf"
    clean_pdf(Job(src=tagged, dst=dst, strip_metadata=True))
    with pikepdf.open(dst) as cleaned:
        assert "/Info" not in cleaned.trailer
        assert "/Metadata" not in cleaned.Root

    # default leaves metadata alone
    dst_keep = tmp_path / "tagged_keep.pdf"
    clean_pdf(Job(src=tagged, dst=dst_keep))
    with pikepdf.open(dst_keep) as kept:
        assert kept.docinfo.get("/Title") == "Secret Title"
