"""Generate the app icon (PNG + ICO + ICNS) - a slide with the corner wiped clean."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

ASSETS = Path(__file__).resolve().parents[1] / "assets"


def draw_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 256.0

    # slide
    d.rounded_rectangle(
        [24 * s, 40 * s, 232 * s, 216 * s], radius=24 * s, fill=(38, 50, 79, 255)
    )
    # content lines
    for i, width in enumerate((140, 110, 125)):
        y = (78 + i * 30) * s
        d.rounded_rectangle(
            [48 * s, y, (48 + width) * s, y + 14 * s], radius=7 * s, fill=(120, 144, 196, 255)
        )
    # "watermark" being erased: dashed outline in the bottom-right corner
    x0, y0, x1, y1 = 150 * s, 172 * s, 212 * s, 198 * s
    d.rounded_rectangle([x0, y0, x1, y1], radius=6 * s, outline=(255, 120, 90, 255),
                        width=max(2, int(5 * s)))
    # eraser swoosh
    d.line([x0 - 14 * s, y1 + 10 * s, x1 + 6 * s, y0 - 10 * s],
           fill=(255, 200, 90, 255), width=max(3, int(10 * s)))
    return img


def main() -> None:
    ASSETS.mkdir(exist_ok=True)
    base = draw_icon(256)
    base.save(ASSETS / "icon.png")
    base.save(
        ASSETS / "icon.ico",
        sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)],
    )
    draw_icon(512).save(ASSETS / "icon.icns")
    print(f"wrote icons to {ASSETS}")


if __name__ == "__main__":
    main()
