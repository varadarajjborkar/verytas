import numpy as np
import pytest

from verytas.checks.color import ciede2000, contrast_ratio, dominant_colours, hex_to_rgb, rgb_to_lab


@pytest.mark.parametrize(
    ("lab1", "lab2", "expected"),
    [
        # Reference pairs from Sharma, Wu & Dalal (2005), Table 1.
        ((50.0, 2.6772, -79.7751), (50.0, 0.0, -82.7485), 2.0425),
        ((50.0, 0.0, 0.0), (50.0, -1.0, 2.0), 2.3669),
        ((50.0, 2.5, 0.0), (73.0, 25.0, -18.0), 27.1492),
        ((60.2574, -34.0099, 36.2677), (60.4626, -34.1751, 39.4387), 1.2644),
        ((22.7233, 20.0904, -46.6940), (23.0331, 14.9730, -42.5619), 2.0373),
    ],
)
def test_ciede2000_matches_reference_data(lab1, lab2, expected):
    assert ciede2000(lab1, lab2) == pytest.approx(expected, abs=1e-4)


def test_ciede2000_is_symmetric_and_zero_on_identity():
    a, b = rgb_to_lab((10, 132, 255)), rgb_to_lab((240, 80, 20))
    assert ciede2000(a, a) == pytest.approx(0)
    assert ciede2000(a, b) == pytest.approx(ciede2000(b, a))


def test_contrast_ratio_extremes():
    assert contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0)
    assert contrast_ratio((119, 119, 119), (255, 255, 255)) == pytest.approx(4.48, abs=0.01)


def test_hex_parsing():
    assert hex_to_rgb("#0a84ff") == (10, 132, 255)
    assert hex_to_rgb("fff") == (255, 255, 255)
    with pytest.raises(ValueError):
        hex_to_rgb("#12345")


def test_dominant_colours_finds_the_two_blocks():
    img = np.zeros((20, 20, 3), dtype=np.uint8)
    img[:, :15] = (255, 0, 0)
    img[:, 15:] = (0, 0, 255)
    colours = dominant_colours(img, k=2)
    assert colours[0][0] == (255, 0, 0)
    assert colours[0][1] == pytest.approx(0.75)
    assert colours[1][0] == (0, 0, 255)
