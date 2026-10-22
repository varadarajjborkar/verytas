"""Colour maths for visual and accessibility checks.

sRGB -> CIELAB (D65) and the CIEDE2000 colour difference, implemented from
Sharma, Wu & Dalal (2005), plus WCAG 2.x relative luminance and contrast ratio.
Small enough to own outright instead of pulling in a heavy colour library.
"""

from __future__ import annotations

import math

import numpy as np

RGB = tuple[int, int, int]
LAB = tuple[float, float, float]


def hex_to_rgb(value: str) -> RGB:
    v = value.strip().lstrip("#")
    if len(v) == 3:
        v = "".join(ch * 2 for ch in v)
    if len(v) != 6:
        raise ValueError(f"not a hex colour: {value!r}")
    return int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16)


def rgb_to_hex(rgb: RGB) -> str:
    return "#{:02X}{:02X}{:02X}".format(*rgb)


def _srgb_to_linear(c: float) -> float:
    c /= 255.0
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def relative_luminance(rgb: RGB) -> float:
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(fg: RGB, bg: RGB) -> float:
    """WCAG contrast ratio, from 1.0 (identical) to 21.0 (black on white)."""
    l1, l2 = sorted((relative_luminance(fg), relative_luminance(bg)), reverse=True)
    return (l1 + 0.05) / (l2 + 0.05)


_D65 = (0.95047, 1.0, 1.08883)


def rgb_to_lab(rgb: RGB) -> LAB:
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    x = (0.4124564 * r + 0.3575761 * g + 0.1804375 * b) / _D65[0]
    y = (0.2126729 * r + 0.7151522 * g + 0.0721750 * b) / _D65[1]
    z = (0.0193339 * r + 0.1191920 * g + 0.9503041 * b) / _D65[2]

    def f(t: float) -> float:
        return t ** (1 / 3) if t > (6 / 29) ** 3 else t / (3 * (6 / 29) ** 2) + 4 / 29

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def ciede2000(lab1: LAB, lab2: LAB) -> float:
    """CIEDE2000 colour difference (kL = kC = kH = 1)."""
    l1, a1, b1 = lab1
    l2, a2, b2 = lab2

    c1, c2 = math.hypot(a1, b1), math.hypot(a2, b2)
    c_bar = (c1 + c2) / 2
    g = 0.5 * (1 - math.sqrt(c_bar**7 / (c_bar**7 + 25**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = math.hypot(a1p, b1), math.hypot(a2p, b2)

    def hue(b: float, ap: float) -> float:
        if b == 0 and ap == 0:
            return 0.0
        h = math.degrees(math.atan2(b, ap))
        return h + 360 if h < 0 else h

    h1p, h2p = hue(b1, a1p), hue(b2, a2p)

    dl = l2 - l1
    dc = c2p - c1p
    if c1p * c2p == 0:
        dh = 0.0
    elif abs(h2p - h1p) <= 180:
        dh = h2p - h1p
    elif h2p - h1p > 180:
        dh = h2p - h1p - 360
    else:
        dh = h2p - h1p + 360
    d_h = 2 * math.sqrt(c1p * c2p) * math.sin(math.radians(dh / 2))

    l_bar = (l1 + l2) / 2
    cp_bar = (c1p + c2p) / 2
    if c1p * c2p == 0:
        hp_bar = h1p + h2p
    elif abs(h1p - h2p) <= 180:
        hp_bar = (h1p + h2p) / 2
    elif h1p + h2p < 360:
        hp_bar = (h1p + h2p + 360) / 2
    else:
        hp_bar = (h1p + h2p - 360) / 2

    t = (
        1
        - 0.17 * math.cos(math.radians(hp_bar - 30))
        + 0.24 * math.cos(math.radians(2 * hp_bar))
        + 0.32 * math.cos(math.radians(3 * hp_bar + 6))
        - 0.20 * math.cos(math.radians(4 * hp_bar - 63))
    )
    d_theta = 30 * math.exp(-(((hp_bar - 275) / 25) ** 2))
    r_c = 2 * math.sqrt(cp_bar**7 / (cp_bar**7 + 25**7))
    s_l = 1 + (0.015 * (l_bar - 50) ** 2) / math.sqrt(20 + (l_bar - 50) ** 2)
    s_c = 1 + 0.045 * cp_bar
    s_h = 1 + 0.015 * cp_bar * t
    r_t = -math.sin(math.radians(2 * d_theta)) * r_c

    return math.sqrt(
        (dl / s_l) ** 2 + (dc / s_c) ** 2 + (d_h / s_h) ** 2 + r_t * (dc / s_c) * (d_h / s_h)
    )


def nearest_brand_colour(rgb: RGB, palette: list[RGB]) -> tuple[RGB, float]:
    lab = rgb_to_lab(rgb)
    return min(((p, ciede2000(lab, rgb_to_lab(p))) for p in palette), key=lambda t: t[1])


def dominant_colours(pixels: np.ndarray, k: int = 5, iters: int = 12, seed: int = 0) -> list[tuple[RGB, float]]:
    """k-means over RGB pixels. Returns (colour, share of pixels), largest first.

    `pixels` is an (N, 3) uint8 array; callers should downsample large images
    first. Deterministic for a given seed so reviews are reproducible.
    """
    data = pixels.reshape(-1, 3).astype(np.float64)
    if len(data) == 0:
        return []
    k = min(k, len(np.unique(data, axis=0)))
    rng = np.random.default_rng(seed)
    centres = data[rng.choice(len(data), size=k, replace=False)]
    for _ in range(iters):
        labels = np.argmin(((data[:, None, :] - centres[None, :, :]) ** 2).sum(axis=2), axis=1)
        new = np.array([data[labels == i].mean(axis=0) if np.any(labels == i) else centres[i] for i in range(k)])
        if np.allclose(new, centres):
            break
        centres = new
    counts = np.bincount(labels, minlength=k) / len(data)
    order = np.argsort(-counts)
    return [(tuple(int(round(v)) for v in centres[i]), float(counts[i])) for i in order]


def _luminance_array(rgb: np.ndarray) -> np.ndarray:
    """WCAG relative luminance of every pixel of an (H, W, 3) or (N, 3) uint8 array."""
    c = rgb.astype(np.float64) / 255.0
    lin = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    return lin @ np.array([0.2126, 0.7152, 0.0722])


def text_contrast(crop: np.ndarray) -> tuple[RGB, RGB, float, bool] | None:
    """(text colour, background colour, contrast ratio, busy background) for a crop holding one line of text.

    The crop should have a margin around the text: its border is the background. The text is the pixels
    that differ from the background, on whichever side (darker or lighter) differs most; its colour is
    the far edge of those (the 99th percentile of their difference), not their anti-aliased or
    JPEG-blurred edges. Small and compressed text then reads at or slightly above its true contrast,
    never below it: a compliant caption must not be blocked by a measurement artefact. A background whose
    border spans a wide range of luminance (a photo) is reported as busy: the one colour given for it is
    then a median. None when nothing stands out.
    """
    if crop.ndim != 3 or min(crop.shape[:2]) < 6:
        return None
    rgb = crop[..., :3]
    lum = _luminance_array(rgb)
    ring = np.concatenate([lum[0], lum[-1], lum[1:-1, 0], lum[1:-1, -1]])
    ring_rgb = np.concatenate([rgb[0], rgb[-1], rgb[1:-1, 0], rgb[1:-1, -1]])
    bg = float(np.median(ring))
    diff = lum - bg
    darker, lighter = diff < -0.01, diff > 0.01
    side = darker if np.abs(diff[darker]).sum() >= np.abs(diff[lighter]).sum() else lighter
    if side.sum() < 12:
        return None
    dist = np.abs(diff[side])
    far = float(np.percentile(dist, 99))
    text_l = bg - far if side is darker else bg + far
    core = side.copy()
    core[side] = dist >= np.percentile(dist, 97)
    near = np.abs(ring - bg) <= max(0.02, float(np.median(np.abs(ring - bg))))
    bg_rgb: RGB = tuple(int(v) for v in np.median(ring_rgb[near], axis=0))  # type: ignore[assignment]
    text_rgb: RGB = tuple(int(v) for v in np.median(rgb[core], axis=0))  # type: ignore[assignment]
    hi_l, lo_l = max(bg, text_l), min(bg, text_l)
    busy = float(np.percentile(ring, 90) - np.percentile(ring, 10)) > 0.25
    return text_rgb, bg_rgb, (hi_l + 0.05) / (lo_l + 0.05), busy
