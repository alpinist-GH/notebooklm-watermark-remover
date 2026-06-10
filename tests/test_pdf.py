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
