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
