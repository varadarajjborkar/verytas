"""An OCR benchmark: marketing images with known text, degraded the ways real uploads are.

Every image is drawn from a seed, so the set is reproducible and free of anyone's artwork. Each one is
a social card, poster, banner, story, price list, contact card or legal-heavy post carrying headlines,
body copy, prices, discounts, dates, hashtags, URLs, phone numbers and small disclaimers, in Latin
script, Devanagari (Hindi) or Hinglish (Hindi words in Latin script). Independent draws vary:

- background: flat, gradient, photo-like noise, busy shapes;
- contrast of the text against what is under it (measured, not intended), and coloured text;
- font family (sans, serif, display, handwriting-style, mono) and size, down to 11 px legal lines;
- a small rotation of the whole layout, downscaling, and JPEG recompression at several qualities.

The ground truth is the exact list of lines drawn, top to bottom, plus the "critical tokens" in them
(prices, percentages, numbers, dates, URLs, phone numbers, hashtags, brand names): the strings a brand
check depends on. Images and a `cases.jsonl` go to an output folder, never into the repo:

    .venv/bin/python -m evals.ocr.generate --out /private/tmp/.../scratchpad/ocrbench --count 240

Devanagari needs real text shaping (conjuncts, vowel signs), which Pillow here lacks, so those lines
are shaped by rsvg-convert (pango) and composited as masks.
"""

from __future__ import annotations

import argparse
import colorsys
import io
import json
import math
import random
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from xml.sax.saxutils import escape

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

DEFAULT_OUT = Path("/private/tmp/claude-502/-Users-varadarajborkar-praj-code/"
                   "298965cb-f1e3-424a-8f01-ca8c15eeb018/scratchpad/ocrbench")
SYS = Path("/System/Library/Fonts")
SUP = SYS / "Supplemental"

# Font class -> files. Every style inside a collection (bold, italic, condensed...) joins the pool.
FONT_FILES: dict[str, list[Path]] = {
    "sans": [SUP / "Arial.ttf", SUP / "Arial Bold.ttf", SYS / "Helvetica.ttc", SYS / "HelveticaNeue.ttc",
             SUP / "Verdana.ttf", SUP / "Tahoma.ttf", SUP / "Trebuchet MS.ttf", SYS / "Avenir Next.ttc",
             SUP / "Futura.ttc", SUP / "GillSans.ttc", SYS / "Optima.ttc", SYS / "SFNS.ttf"],
    "serif": [SUP / "Georgia.ttf", SUP / "Times New Roman.ttf", SUP / "Baskerville.ttc", SYS / "Palatino.ttc",
              SUP / "Hoefler Text.ttc", SUP / "Didot.ttc", SUP / "Charter.ttc", SUP / "Rockwell.ttc"],
    "display": [SUP / "Impact.ttf", SUP / "Arial Black.ttf", SUP / "DIN Condensed Bold.ttf",
                SUP / "Arial Rounded Bold.ttf", SUP / "Arial Narrow Bold.ttf", SUP / "Copperplate.ttc",
                SUP / "Phosphate.ttc", SUP / "SuperClarendon.ttc"],
    "handwriting": [SUP / "Brush Script.ttf", SUP / "Bradley Hand Bold.ttf", SUP / "SnellRoundhand.ttc",
                    SYS / "MarkerFelt.ttc", SUP / "Chalkduster.ttf", SUP / "Comic Sans MS.ttf",
                    SUP / "Apple Chancery.ttf", SYS / "Noteworthy.ttc"],
    "mono": [SUP / "Courier New.ttf", SYS / "Menlo.ttc", SUP / "Andale Mono.ttf", SYS / "Monaco.ttf"],
}
HEAD_WEIGHTS = {"sans": 40, "display": 25, "serif": 17, "handwriting": 13, "mono": 5}
BODY_WEIGHTS = {"sans": 58, "serif": 27, "mono": 8, "handwriting": 7}
DEVANAGARI = ["Kohinoor Devanagari", "Devanagari MT", "Devanagari Sangam MN", "ITF Devanagari", "Mukta",
              "Shobhika", "Cambay Devanagari"]

BRANDS = ["Zestora", "NovaBrew", "Kiraana Kart", "Lumo Wear", "Chaiwala Co.", "Verdant Foods", "PixelPulse",
          "Aarav Jewels", "Sundari Silks", "TrailMate", "Rasoi Fresh", "Bluefin Mobiles"]
HEADLINES = ["Mega Monsoon Sale", "Fresh Drop, Fresh Start", "Brew Better Mornings", "Festive Season Special",
             "Taste the Difference", "Glow Up This Diwali", "Weekend Wow Deals", "New Season, New You",
             "Grand Opening Offer", "Style That Travels", "Snacks Made Simple", "Upgrade Your Everyday",
             "Big Billion Bonanza", "Summer Clearance Event", "Meet Our Newest Range"]
SUBS = ["Limited time only", "While stocks last", "Free delivery on orders above Rs. 499", "Shop in store and online",
        "Handpicked for you", "Now available across India", "Order before midnight", "Made fresh every morning"]
BODIES = ["Treat yourself to the best of the season", "Quality you can trust at prices you will love",
          "Visit your nearest store today", "Download our app for exclusive member deals",
          "Pure ingredients and honest pricing", "Pick up your favourites before they are gone",
          "Gift something special to someone special", "Tried, tested and loved by thousands"]
ITEMS = ["Masala Chai 250g", "Cold Brew Pack", "Cotton Kurta", "Running Shoes", "Basmati Rice 5kg", "Silk Dupatta",
         "Wireless Earbuds", "Trail Backpack", "Almond Mix 500g", "Steel Bottle 1L"]
TAGS = ["MonsoonMagic", "FestiveVibes", "ShopSmart", "DiwaliDhamaka", "FreshStart", "WeekendDeals", "NewDrop",
        "MadeInIndia", "TasteOfHome", "StyleSeries"]
DOMAINS = [".in", ".com", ".co.in", ".store"]
LEGAL = ["*Terms and conditions apply.", "Offer valid on select products only while stocks last.",
         "Prices are inclusive of all taxes.", "Not valid in combination with any other offer or coupon.",
         "Images are for representation purposes only.",
         "The company reserves the right to modify or withdraw this offer.",
         "Delivery charges may apply on orders below the minimum value.", "Discount applicable on MRP."]
MONTHS = ["Oct", "Nov", "Dec", "Jan"]

HI_HEAD = ["बड़ी बचत का त्योहार", "ताज़ा स्वाद, नई शुरुआत", "दिवाली धमाका ऑफर", "आज ही खरीदें", "मानसून सेल शुरू"]
HI_BODY = ["सभी उत्पादों पर {p}% की छूट", "कीमत सिर्फ ₹{a} से शुरू", "ऑफर {d} अक्टूबर तक मान्य", "अपने नज़दीकी स्टोर पर आएं",
           "मुफ़्त होम डिलीवरी हर ऑर्डर पर", "शर्तें लागू"]
HI_PHONE = "अधिक जानकारी के लिए कॉल करें {ph}"
HINGLISH = ["Diwali Dhamaka Sale, sabse sasta offer", "Aaj hi kharido aur paao {p}% ki bachat",
            "Ab ghar baithe order karo", "Sirf ₹{a} mein, jaldi karo!", "Apni pasand ka maal, apne budget mein",
            "Offer {d} October tak hi hai", "Free delivery, koi hidden charge nahi",
            "Tyohar ki khushiyan, hamare saath"]

# (width, height) formats as posted: square, portrait, landscape banner, story, poster.
FORMATS = {"card": (1080, 1080), "portrait": (1080, 1350), "banner": (1200, 628), "story": (1080, 1920),
           "poster": (1000, 1400), "small": (800, 800)}


@dataclass
class Block:
    role: str
    text: str
    px: float  # font size on a 1080-wide canvas
    crit: list[dict] = field(default_factory=list)
    devanagari: bool = False
    bold: bool = False


# ---------------------------------------------------------------------------------------- content

def money(rng: random.Random) -> int:
    return rng.choice([99, 149, 199, 249, 299, 399, 499, 599, 799, 999, 1299, 1499, 1999, 2499, 2999, 3499, 4999,
                       12999])


def indian(n: int) -> str:
    s = str(n)
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def c(token: str, kind: str) -> dict:
    return {"t": token, "kind": kind}


def make_brand(rng: random.Random) -> Block:
    name = rng.choice(BRANDS)
    text = name.upper() if rng.random() < 0.3 else name
    return Block("brand", text, rng.uniform(40, 70), [c(text, "brand")], bold=True)


def make_headline(rng: random.Random, script: str) -> Block:
    if script == "devanagari":
        return Block("headline", rng.choice(HI_HEAD), rng.uniform(64, 110), devanagari=True, bold=True)
    if script == "hinglish":
        return Block("headline", rng.choice([HINGLISH[0], HINGLISH[4], HINGLISH[7]]),
                     rng.uniform(56, 90), bold=True)
    text = rng.choice(HEADLINES)
    if rng.random() < 0.25:
        text = text.upper()
    return Block("headline", text, rng.uniform(64, 120), bold=True)


def make_discount(rng: random.Random) -> Block:
    n = rng.choice([10, 15, 20, 25, 30, 35, 40, 50, 60, 70])
    text = rng.choice([f"Flat {n}% OFF", f"Up to {n}% off", f"Save {n}% today", f"Extra {n}% cashback",
                       f"{n}% OFF on everything"])
    return Block("discount", text, rng.uniform(56, 110), [c(f"{n}%", "percent")], bold=True)


def make_price(rng: random.Random) -> Block:
    a, b = money(rng), money(rng)
    mrp, now = max(a, b) + 500, min(a, b)
    sym = rng.choice(["₹", "Rs. ", "Rs ", "₹"])
    kind = rng.randrange(4)
    if kind == 0:
        text, toks = f"{sym}{indian(now)}", [f"{sym.strip()}{indian(now)}"]
    elif kind == 1:
        text, toks = f"Only {sym}{indian(now)}/-", [f"{sym.strip()}{indian(now)}"]
    elif kind == 2:
        text = f"MRP {sym}{indian(mrp)} Now {sym}{indian(now)}"
        toks = [f"{sym.strip()}{indian(mrp)}", f"{sym.strip()}{indian(now)}"]
    else:
        text, toks = f"Starting at {sym}{indian(now)}", [f"{sym.strip()}{indian(now)}"]
    return Block("price", text, rng.uniform(60, 130), [c(t, "price") for t in toks], bold=True)


def make_date(rng: random.Random) -> Block:
    d, m = rng.randint(1, 28), rng.choice(MONTHS)
    kind = rng.randrange(3)
    if kind == 0:
        text, toks = f"Offer valid till {d} {m} 2026", [f"{d} {m} 2026"]
    elif kind == 1:
        d2 = f"{d:02d}/{rng.randint(10, 12)}/2026"
        d3 = f"{min(d + 3, 28):02d}/{d2[3:5]}/2026"
        text, toks = f"{d2} to {d3}", [d2, d3]
    else:
        text, toks = f"Sale ends {d}th {m}", [f"{d}th {m}"]
    return Block("date", text, rng.uniform(24, 36), [c(t, "date") for t in toks])


def make_hashtags(rng: random.Random) -> Block:
    tags = ["#" + t for t in rng.sample(TAGS, rng.choice([2, 3]))]
    return Block("hashtag", " ".join(tags), rng.uniform(28, 44), [c(t, "hashtag") for t in tags])


def make_url(rng: random.Random, brand: str | None = None) -> Block:
    slug = (brand or rng.choice(BRANDS)).lower().replace(" ", "").replace(".", "")
    host = slug + rng.choice(DOMAINS)
    path = rng.choice(["", "/sale", "/offers", "/new-arrivals", "/shop?ref=social"])
    text = rng.choice(["www.", "", "shop.", "https://"]) + host + path
    if rng.random() < 0.2:
        text = f"hello@{host}"
    return Block("url", text, rng.uniform(28, 42), [c(text, "url")])


def make_phone(rng: random.Random, lang: str = "en") -> Block:
    d = lambda n: "".join(rng.choice("0123456789") for _ in range(n))  # noqa: E731
    kind = rng.randrange(3)
    if kind == 0:
        num = f"+91 {rng.choice('6789')}{d(4)} {d(5)}"
    elif kind == 1:
        num = f"1800-{d(3)}-{d(4)}"
    else:
        num = f"{rng.choice('6789')}{d(9)}"
    if lang == "hi":
        return Block("phone", HI_PHONE.format(ph=num), rng.uniform(28, 44), [c(num, "phone")], devanagari=True)
    lead = rng.choice(["Call ", "Toll free ", "WhatsApp ", "Order on "]) if kind != 1 else "Toll free "
    return Block("phone", lead + num, rng.uniform(28, 44), [c(num, "phone")])


def make_legal(rng: random.Random, n: int = 1) -> Block:
    text = " ".join(rng.sample(LEGAL, n + 1))
    return Block("legal", text, rng.uniform(12, 20))


def make_body(rng: random.Random, script: str) -> Block:
    if script == "devanagari":
        d, p, a = rng.randint(2, 31), rng.choice([10, 20, 25, 30, 40, 50]), indian(money(rng))
        text = rng.choice(HI_BODY).format(p=p, a=a, d=d)
        toks = []
        if f"{p}%" in text:
            toks = [c(f"{p}%", "percent")]
        elif "₹" in text:
            toks = [c(f"₹{a}", "price")]
        elif "अक्टूबर" in text:
            toks = [c(str(d), "date")]
        return Block("body", text, rng.uniform(34, 52), toks, devanagari=True)
    if script == "hinglish":
        d, p, a = rng.randint(2, 31), rng.choice([10, 20, 25, 30, 40, 50]), indian(money(rng))
        text = rng.choice(HINGLISH).format(p=p, a=a, d=d)
        toks = []
        if f"{p}%" in text:
            toks = [c(f"{p}%", "percent")]
        elif "₹" in text:
            toks = [c(f"₹{a}", "price")]
        elif "October" in text:
            toks = [c(str(d), "date")]
        return Block("body", text, rng.uniform(30, 46), toks)
    return Block("body", rng.choice(BODIES), rng.uniform(26, 40))


def make_item(rng: random.Random) -> Block:
    price = money(rng)
    sym = rng.choice(["₹", "Rs. "])
    text = f"{rng.choice(ITEMS)}   {sym}{indian(price)}"
    return Block("price", text, rng.uniform(30, 46), [c(f"{sym.strip()}{indian(price)}", "price")])


def template(rng: random.Random, name: str, script: str) -> tuple[str, list[Block]]:
    """(format, blocks) for a layout. The legal block, if any, is last and anchors to the bottom."""
    brand = make_brand(rng)
    slug = brand.text
    if script == "devanagari":
        blocks = [brand, make_headline(rng, script), make_body(rng, script), make_body(rng, script),
                  make_phone(rng, "hi"), make_url(rng, slug)]
        if name in ("poster", "legal"):
            blocks.append(make_legal(rng, 1))
        return rng.choice(["card", "portrait", "poster", "story"]), blocks
    if script == "hinglish":
        blocks = [brand, make_headline(rng, script), make_body(rng, script), make_body(rng, script),
                  make_hashtags(rng), make_url(rng, slug)]
        if name in ("poster", "legal"):
            blocks.append(make_legal(rng, 1))
        return rng.choice(["card", "portrait", "story", "small"]), blocks
    if name == "social":
        return rng.choice(["card", "portrait", "small"]), [
            brand, make_headline(rng, script), make_discount(rng), make_body(rng, script), make_url(rng, slug),
            make_legal(rng, 1)]
    if name == "poster":
        return rng.choice(["poster", "portrait"]), [
            make_headline(rng, script), Block("sub", rng.choice(SUBS), rng.uniform(34, 52)), make_price(rng),
            make_date(rng), make_phone(rng), make_hashtags(rng), make_legal(rng, 2)]
    if name == "banner":
        return "banner", [make_discount(rng), make_headline(rng, script), make_price(rng), make_date(rng),
                          make_url(rng, slug)]
    if name == "story":
        return "story", [brand, make_headline(rng, script), make_body(rng, script), make_body(rng, script),
                         make_hashtags(rng), make_url(rng, slug), make_phone(rng)]
    if name == "legal":
        return rng.choice(["card", "portrait"]), [make_headline(rng, script), make_body(rng, script),
                                                  make_legal(rng, 2), make_legal(rng, 2), make_legal(rng, 1)]
    if name == "pricelist":
        return rng.choice(["card", "portrait", "small"]), [brand, make_headline(rng, script)] + \
            [make_item(rng) for _ in range(rng.randint(3, 5))] + [make_legal(rng, 1)]
    return rng.choice(["card", "small", "banner"]), [brand, make_phone(rng), make_url(rng, slug), make_url(rng, slug),
                                                     make_date(rng)]  # contact


TEMPLATE_WEIGHTS = {"social": 24, "poster": 18, "banner": 12, "story": 12, "legal": 12, "pricelist": 10, "contact": 12}


# ------------------------------------------------------------------------------------------ fonts

_font_cache: dict[tuple, ImageFont.FreeTypeFont] = {}
_pools: dict[str, list[tuple[Path, int]]] = {}


def font_pool(cls: str) -> list[tuple[Path, int]]:
    """Every (file, face index) of a class that opens here; missing fonts are skipped quietly."""
    if cls not in _pools:
        found = []
        for path in FONT_FILES[cls]:
            if not path.is_file():
                continue
            for idx in range(40):
                try:
                    ImageFont.truetype(str(path), 20, index=idx)
                except OSError:
                    break
                found.append((path, idx))
        _pools[cls] = found
    return _pools[cls]


def load(path: Path, idx: int, size: int) -> ImageFont.FreeTypeFont:
    key = (path, idx, size)
    if key not in _font_cache:
        _font_cache[key] = ImageFont.truetype(str(path), size, index=idx)
    return _font_cache[key]


_glyph_ok: dict[tuple, bool] = {}


def has_rupee(path: Path, idx: int) -> bool:
    """True when the face draws a real rupee sign (not the missing-glyph box, not blank)."""
    key = (path, idx)
    if key not in _glyph_ok:
        f = load(path, idx, 64)
        a, b = f.getmask("₹"), f.getmask("\U0010fffd")
        _glyph_ok[key] = bool(a.getbbox()) and bytes(a) != bytes(b) and f.getlength("₹") > 1
    return _glyph_ok[key]


_shaped: dict[tuple, Image.Image] = {}


def shaped(text: str, family: str, bold: bool) -> Image.Image:
    """Alpha mask of a Devanagari line at a 100 px em, shaped by pango through rsvg-convert."""
    key = (text, family, bold)
    if key not in _shaped:
        w = int(len(text) * 80 + 200)
        svg = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='240'>"
               f"<text x='40' y='150' font-family='{family}' font-size='100' "
               f"font-weight='{'bold' if bold else 'normal'}' fill='white'>{escape(text)}</text></svg>")
        png = subprocess.run(["rsvg-convert", "-f", "png"], input=svg.encode(), capture_output=True, check=True).stdout
        mask = Image.open(io.BytesIO(png)).convert("RGBA").getchannel("A")
        box = mask.getbbox()
        _shaped[key] = mask.crop(box) if box else mask
    return _shaped[key]


# ---------------------------------------------------------------------------------- backgrounds

def noise_field(rng: np.random.RandomState, h: int, w: int, octaves: int = 5) -> np.ndarray:
    out = np.zeros((h, w, 3), np.float32)
    for o in range(octaves):
        cell = max(2, int(max(h, w) / (3 * 2**o)))
        small = rng.rand(max(2, h // cell + 2), max(2, w // cell + 2), 3).astype(np.float32)
        out += cv2.resize(small, (w, h), interpolation=cv2.INTER_CUBIC) / 2**o
    out -= out.min()
    return out / max(out.max(), 1e-6)


def rand_colour(rng: random.Random, sat=(0.3, 1.0), val=(0.2, 1.0)) -> np.ndarray:
    return np.array(colorsys.hsv_to_rgb(rng.random(), rng.uniform(*sat), rng.uniform(*val)), np.float32)


def background(kind: str, w: int, h: int, seed: int) -> Image.Image:
    rng, nrng = random.Random(seed), np.random.RandomState(seed)
    if kind == "flat":
        plain = rand_colour(rng) if rng.random() < 0.8 else np.ones(3) * rng.choice([0.97, 0.08])
        arr = np.ones((h, w, 3), np.float32) * plain
    elif kind in ("gradient", "shapes"):
        c0, c1 = rand_colour(rng), rand_colour(rng)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        if rng.random() < 0.5:
            ang = rng.uniform(0, math.pi)
            t = (xx / w * math.cos(ang) + yy / h * math.sin(ang))
            t = (t - t.min()) / max(t.max() - t.min(), 1e-6)
        else:
            t = np.clip(np.hypot(xx - w * rng.uniform(.2, .8), yy - h * rng.uniform(.2, .8)) / max(w, h) * 1.2, 0, 1)
        arr = c0 * (1 - t[..., None]) + c1 * t[..., None]
    else:  # photo-like: layered noise, soft blobs, vignette, film grain
        base = noise_field(nrng, h, w)
        tint = np.stack([rand_colour(rng), rand_colour(rng), rand_colour(rng)])
        arr = np.clip(base @ tint / 1.5 + 0.1, 0, 1)
        for _ in range(rng.randint(2, 5)):
            blob = np.zeros((h, w), np.float32)
            cv2.circle(blob, (rng.randrange(w), rng.randrange(h)), rng.randint(min(w, h) // 8, min(w, h) // 3), 1.0, -1)
            blob = cv2.GaussianBlur(blob, (0, 0), min(w, h) / 12)
            arr = np.clip(arr + blob[..., None] * (rand_colour(rng) - 0.5) * 0.8, 0, 1)
        yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
        vig = 1 - 0.35 * (np.hypot(xx - w / 2, yy - h / 2) / (math.hypot(w, h) / 2)) ** 2
        arr = arr * vig[..., None] + nrng.normal(0, 0.03, (h, w, 1)).astype(np.float32)
    img = Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8))
    if kind == "shapes":
        draw = ImageDraw.Draw(img, "RGBA")
        for _ in range(rng.randint(30, 70)):
            col = tuple(int(v * 255) for v in rand_colour(rng)) + (rng.randint(90, 230),)
            x, y = rng.randrange(-50, w), rng.randrange(-50, h)
            s = rng.randint(30, max(60, min(w, h) // 3))
            shape = rng.randrange(4)
            if shape == 0:
                draw.ellipse((x, y, x + s, y + s * rng.uniform(.5, 1.5)), fill=col)
            elif shape == 1:
                draw.rectangle((x, y, x + s * rng.uniform(.5, 3), y + s * rng.uniform(.2, 1.5)), fill=col)
            elif shape == 2:
                pts = [(x + rng.randint(0, s), y + rng.randint(0, s)) for _ in range(rng.randint(3, 6))]
                draw.polygon(pts, fill=col)
            else:
                for k in range(rng.randint(3, 8)):
                    draw.line((x, y + k * s // 6, x + s * 2, y + k * s // 6 + rng.randint(-s, s)), fill=col,
                              width=rng.randint(3, 14))
    return img


# ----------------------------------------------------------------------------------- composition

def luminance(rgb) -> float:
    lin = [(v / 255) / 12.92 if v / 255 <= 0.03928 else (((v / 255) + 0.055) / 1.055) ** 2.4 for v in rgb]
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def ratio(a, b) -> float:
    la, lb = luminance(a), luminance(b)
    return (max(la, lb) + 0.05) / (min(la, lb) + 0.05)


TARGETS = {"high": (9, 21), "medium": (3.8, 6), "low": (1.3, 2.3)}


def pick_colour(rng: random.Random, bg_mean, target: float, coloured: bool) -> tuple[int, int, int]:
    cands = [(255, 255, 255), (0, 0, 0), (20, 20, 30), (245, 245, 235)]
    for _ in range(300):
        if coloured:
            hsv = colorsys.hsv_to_rgb(rng.random(), rng.uniform(.5, 1), rng.uniform(.15, 1))
            cands.append(tuple(int(v * 255) for v in hsv))
        else:
            g = int(rng.uniform(0, 255))
            cands.append((g, g, g))
    return min(cands, key=lambda col: abs(math.log(ratio(col, bg_mean) / target)))


def weighted(rng: random.Random, weights: dict):
    return rng.choices(list(weights), list(weights.values()))[0]


def size_class(px: float) -> str:
    return "tiny" if px < 14 else "small" if px < 22 else "medium" if px < 44 else "large"


def build(i: int, seed: int, out: Path) -> dict:
    rng = random.Random(f"{seed}:{i}")
    tname = weighted(rng, TEMPLATE_WEIGHTS)
    script = rng.choices(["latin", "hinglish", "devanagari"], [70, 15, 15])[0]
    fmt, blocks = template(rng, tname, script)
    if script != "latin":
        tname = f"{script}_{'legal' if any(b.role == 'legal' for b in blocks) else 'card'}"
    W, H = FORMATS[fmt]
    k = W / 1080
    head_cls, body_cls = weighted(rng, HEAD_WEIGHTS), weighted(rng, BODY_WEIGHTS)
    bg_kind = rng.choice(["flat", "gradient", "photo", "shapes"])
    contrast_cls = rng.choices(["high", "medium", "low"], [40, 30, 30])[0]
    coloured = rng.random() < 0.35
    shadow = bg_kind in ("photo", "shapes") and rng.random() < 0.3
    angle = 0.0 if rng.random() < 0.6 else rng.choice([-1, 1]) * rng.uniform(1, 8)
    dscale = rng.choices([1.0, 0.5, 0.3], [60, 25, 15])[0]
    quality = rng.choices([0, 90, 70, 40, 20], [30, 20, 20, 15, 15])[0]  # 0 = lossless PNG
    align = rng.choice(["center", "left"])
    dev_family = rng.choice(DEVANAGARI)

    # Fonts and sizes, shrunk where a line would overrun the canvas.
    head_face, body_face = rng.choice(font_pool(head_cls)), rng.choice(font_pool(body_cls))
    placed = []
    for b in blocks:
        big = b.role in ("brand", "headline", "discount") or (b.role == "price" and b.px > 50)
        face = head_face if big else body_face
        size = max(8, round(b.px * k))
        text = b.text
        crit = [dict(t) for t in b.crit]
        if not b.devanagari and "₹" in text and not has_rupee(*face):
            text = text.replace("₹", "Rs. ")
            for t in crit:
                t["t"] = t["t"].replace("₹", "Rs.")
        limit = W * 0.92
        if b.devanagari:
            mask = shaped(text, dev_family, b.bold)
            width = mask.width * size / 100
            if width > limit:
                size = max(8, int(size * limit / width))
            placed.append({"b": b, "text": text, "crit": crit, "size": size, "face": None})
        else:
            f = load(*face, size)
            while f.getlength(text) > limit and size > 8:
                size -= 1
                f = load(*face, size)
            placed.append({"b": b, "text": text, "crit": crit, "size": size, "face": face})

    def measure(p):
        if p["face"] is None:
            m = shaped(p["text"], dev_family, p["b"].bold)
            return int(m.width * p["size"] / 100), max(p["size"], int(m.height * p["size"] / 100))
        f = load(*p["face"], p["size"])
        x0, y0, x1, y1 = f.getbbox(p["text"])
        return int(x1 - x0), int(y1 - y0)

    for p in placed:
        p["w"], p["h"] = measure(p)
    main = [p for p in placed if p["b"].role != "legal"]
    legal = [p for p in placed if p["b"].role == "legal"]
    gap = lambda p: int(p["size"] * 0.55) + 6  # noqa: E731
    need = sum(p["h"] + gap(p) for p in main) + sum(p["h"] + gap(p) for p in legal) + int(0.16 * H)
    H = max(H, need)
    bg = background(bg_kind, W, H, rng.randrange(1 << 30))
    arr = np.asarray(bg)

    main_h = sum(p["h"] + gap(p) for p in main)
    top = (H - main_h - sum(p["h"] + gap(p) for p in legal)) / 2 + rng.uniform(-0.04, 0.04) * H
    y = max(int(0.05 * H), int(top))
    for p in main:
        p["y"] = y
        y += p["h"] + gap(p)
    y = H - int(0.04 * H) - sum(p["h"] + gap(p) for p in legal)
    for p in legal:
        p["y"] = max(y, main[-1]["y"] + main[-1]["h"] + 8) if main else y
        y += p["h"] + gap(p)
    margin = int(0.05 * W)
    for p in placed:
        p["x"] = (W - p["w"]) // 2 if align == "center" else margin

    canvas = bg.convert("RGBA")
    cx0, cy0 = W / 2, H / 2
    ratios = []
    for p in placed:
        x, y, w, h = p["x"], p["y"], p["w"], p["h"]
        region = arr[max(0, y):min(H, y + h), max(0, x):min(W, x + w)].reshape(-1, 3)
        bg_mean = tuple(float(v) for v in region.mean(axis=0)) if len(region) else (128, 128, 128)
        target = rng.uniform(*TARGETS[contrast_cls])
        col = pick_colour(rng, bg_mean, target, coloured)
        ratios.append(ratio(col, bg_mean))
        pad = 6
        if p["face"] is None:
            mask = shaped(p["text"], dev_family, p["b"].bold)
            sc = p["size"] / 100
            mask = mask.resize((max(1, int(mask.width * sc)), max(1, int(mask.height * sc))), Image.LANCZOS)
            m = Image.new("L", (mask.width + 2 * pad, mask.height + 2 * pad))
            m.paste(mask, (pad, pad))
        else:
            f = load(*p["face"], p["size"])
            x0, y0, x1, y1 = f.getbbox(p["text"])
            m = Image.new("L", (int(x1 - x0) + 2 * pad, int(y1 - y0) + 2 * pad))
            ImageDraw.Draw(m).text((pad - x0, pad - y0), p["text"], font=f, fill=255)
        ccx, ccy = x + w / 2, y + h / 2
        if angle:  # rotate the block about its own centre and move the centre about the canvas centre
            th = math.radians(angle)
            dx, dy = ccx - cx0, ccy - cy0
            ccx = cx0 + dx * math.cos(th) + dy * math.sin(th)
            ccy = cy0 - dx * math.sin(th) + dy * math.cos(th)
            m = m.rotate(angle, resample=Image.BICUBIC, expand=True)
        pos = (int(ccx - m.width / 2), int(ccy - m.height / 2))
        if shadow:
            sh = Image.new("RGBA", m.size, (0, 0, 0, 0))
            sh.putalpha(m.filter(ImageFilter.GaussianBlur(max(1, p["size"] // 14))).point(lambda v: int(v * 0.8)))
            canvas.alpha_composite(sh, (pos[0] + max(1, p["size"] // 18), pos[1] + max(1, p["size"] // 18)))
        layer = Image.new("RGBA", m.size, col + (0,))
        layer.putalpha(m)
        canvas.alpha_composite(layer, pos)

    img = canvas.convert("RGB")
    if dscale != 1.0:
        img = img.resize((max(1, int(W * dscale)), max(1, int(img.height * dscale))), Image.LANCZOS)
    ext = "png" if quality == 0 else "jpg"
    name = f"ocr_{i:04d}.{ext}"
    if quality == 0:
        img.save(out / name)
    else:
        img.save(out / name, quality=quality)

    # "size" is the smallest line that is not fine print: legal lines are tiny by design and are
    # reported under their own role, so they don't make every image look small.
    min_px = min(p["size"] for p in (main or placed)) * dscale
    med_ratio = sorted(ratios)[len(ratios) // 2]
    lines = [p["text"] for p in sorted(placed, key=lambda p: p["y"])]
    crit = [dict(t, role=p["b"].role) for p in sorted(placed, key=lambda p: p["y"]) for t in p["crit"]]
    roles = [{"role": p["b"].role, "text": p["text"], "px": round(p["size"] * dscale, 1)}
             for p in sorted(placed, key=lambda p: p["y"])]
    return {
        "id": f"ocr_{i:04d}", "file": name, "lines": lines, "critical": crit, "roles": roles,
        "tags": {
            "template": tname, "script": script, "format": fmt, "background": bg_kind,
            "contrast": "high" if med_ratio >= 7 else "medium" if med_ratio >= 3 else "low",
            "contrast_ratio": round(med_ratio, 2), "coloured_text": coloured,
            "angle": "0" if not angle else "1-3" if abs(angle) <= 3 else "4-8", "angle_deg": round(angle, 1),
            "jpeg": "png" if quality == 0 else f"q{quality}", "scale": {1.0: "100%", 0.5: "50%", 0.3: "30%"}[dscale],
            "size": size_class(min_px), "min_font_px": round(min_px, 1),
            "legal_px": round(min((p["size"] for p in legal), default=0) * dscale, 1),
            "font": body_cls if script != "devanagari" else "devanagari",
            "head_font": head_cls if script != "devanagari" else "devanagari",
            "shadow": shadow, "width": img.width, "height": img.height,
        },
    }


def main() -> None:
    p = argparse.ArgumentParser(prog="evals.ocr.generate")
    p.add_argument("--out", type=Path, default=DEFAULT_OUT)
    p.add_argument("--count", type=int, default=240)
    p.add_argument("--seed", type=int, default=7)
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    cases = [build(i, args.seed, args.out) for i in range(args.count)]
    with (args.out / "cases.jsonl").open("w") as fh:
        for case in cases:
            fh.write(json.dumps(case, ensure_ascii=False) + "\n")
    print(f"{len(cases)} images and cases.jsonl written to {args.out}")


if __name__ == "__main__":
    main()
