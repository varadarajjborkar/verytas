"""Text contrast in images is measured from the pixels, not only from colours someone typed in."""

from __future__ import annotations

import numpy as np

from tests.media_fixtures import b64, png, text_image
from tests.test_media import _submit, world  # noqa: F401, the fixture is used by name
from verytas.checks.color import contrast_ratio, hex_to_rgb, text_contrast


def test_measured_contrast_matches_the_wcag_ratio_of_the_colours_drawn():
    for fg, bg in [("#000000", "#FFFFFF"), ("#AAAAAA", "#FFFFFF"), ("#767676", "#FFFFFF"),
                   ("#FFFFFF", "#1A3A8A"), ("#FFFFFF", "#FFD400")]:
        _, _, ratio, busy = text_contrast(np.array(text_image(["Learn one thing a day"], size=(700, 120),
                                                              bg=bg, fg=fg)))
        assert abs(ratio - contrast_ratio(hex_to_rgb(fg), hex_to_rgb(bg))) < 0.05 and not busy


def test_pale_text_in_an_image_is_flagged_and_dark_text_is_not(client, world):  # noqa: F811
    pale = b64(png(text_image(["Festive fest starts Monday"], size=(900, 600), fg="#B0B0B0")))
    dark = b64(png(text_image(["Festive fest starts Monday"], size=(900, 600), fg="#222222")))
    _, review = _submit(client, world, body="Poster for the fest", attachments={"images": [
        {"id": "pale", "alt": "Fest poster with the start day", "data_base64": pale},
        {"id": "dark", "alt": "Fest poster with the start day", "data_base64": dark}]})
    low = [f for f in review["findings"] if f["checker"] == "contrast"]
    assert [f["locator"]["image"] for f in low] == ["img:pale"]
    assert "needs 4.5:1" in low[0]["title"] and len(low[0]["locator"]["box"]) == 4


def _caption(px: int, fg: str, jpeg: int | None = None, mode: str = "RGB"):
    import io

    from PIL import Image, ImageDraw, ImageFont

    from tests.media_fixtures import font

    img = Image.new(mode, (30 * px, 3 * px), "white" if mode == "RGB" else (0, 0, 0, 0))
    ImageDraw.Draw(img).text((px, px // 2), "Learn one thing a day", fill=fg, font=ImageFont.truetype(font().path, px))
    if jpeg:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=jpeg)
        img = Image.open(buf).convert("RGB")
    return img


def test_compliant_grey_text_is_never_measured_below_its_contrast_small_or_compressed():
    # errcheck 237: #767676 on white is 4.54:1; anti-aliasing and JPEG used to read it as 2.6 to 4.3.
    for px in (11, 14, 18, 28):
        for jpeg in (None, 40):
            _, _, ratio, _ = text_contrast(np.array(_caption(px, "#767676", jpeg)))
            assert ratio >= 4.5, (px, jpeg, ratio)
    # Truly pale text still reads as pale.
    assert text_contrast(np.array(_caption(14, "#AAAAAA", 40)))[2] < 3.0


def test_text_over_transparency_is_not_measured():
    # errcheck 238: flattening a transparent PNG to white invents the background (white text read as 1:1).
    from verytas.media.ocr import OcrLine
    from verytas.prism.agents import _low_contrast_lines

    img = _caption(28, "white", mode="RGBA")
    line = OcrLine("Learn one thing a day", 0.99, (28, 14, 600, 50))
    assert _low_contrast_lines(img, [line], 4.5, 3.0) == []
