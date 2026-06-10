from nlmclean.core.image import clean_image
from nlmclean.core.imgio import imread
from nlmclean.core.job import Job
from tests.helpers import assert_watermark_removed


def test_clean_image(image_file, tmp_path):
    dst = tmp_path / "slide_clean.png"
    clean_image(Job(src=image_file, dst=dst))
    assert dst.exists()
    assert_watermark_removed(imread(image_file), imread(dst), "doc")


def test_clean_image_jpeg(tmp_path):
    from tests.make_fixtures import make_image

    src = tmp_path / "slide.jpg"
    make_image(src)
    dst = tmp_path / "slide_clean.jpg"
    clean_image(Job(src=src, dst=dst))
    # JPEG is lossy - loosen the outside tolerance
    assert_watermark_removed(imread(src), imread(dst), "doc", max_outside=6.0)
