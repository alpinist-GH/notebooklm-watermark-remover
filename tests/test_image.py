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


def test_clean_gemini_image(tmp_path):
    from tests.make_fixtures import draw_gemini_image, make_gemini_image

    src = tmp_path / "photo.png"
    make_gemini_image(src)
    dst = tmp_path / "photo_clean.png"
    clean_image(Job(src=src, dst=dst))

    _, (x, y, w, h) = draw_gemini_image()
    out = imread(dst)
    src_img = imread(src)
    import numpy as np

    # sparkle area must change a lot, the rest of the image not at all
    sparkle = np.abs(
        out[y : y + h, x : x + w].astype(int) - src_img[y : y + h, x : x + w].astype(int)
    )
    assert sparkle.mean() > 10
    untouched = np.abs(out[: y - 30].astype(int) - src_img[: y - 30].astype(int))
    assert untouched.max() == 0


def test_image_output_has_no_exif(tmp_path):
    from PIL import Image

    from tests.make_fixtures import draw_slide

    src = tmp_path / "tagged.jpg"
    exif = Image.Exif()
    exif[0x010F] = "TestCamera"  # Make
    exif[0x013B] = "Test Artist"  # Artist
    Image.fromarray(draw_slide(kind="doc")[:, :, ::-1]).save(src, exif=exif)
    assert Image.open(src).getexif()  # fixture really carries EXIF

    dst = tmp_path / "tagged_clean.jpg"
    clean_image(Job(src=src, dst=dst))
    assert not Image.open(dst).getexif()
