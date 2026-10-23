"""Dewlight: an Indian D2C skincare and personal care brand (sunscreens, a niacinamide serum, a face wash, a hair
oil). The pressure on this team is regulatory and ethical rather than tonal: no drug claims, no fairness language,
SPF and PA exactly as tested, real and labelled before/after photos, paid-partnership disclosure from every
creator. It has no mascot; the brand is a drop and a sun, and its products are the recognisable objects."""

from __future__ import annotations

import math

from verytas.showcase import art
from verytas.showcase.art import font as _font
from verytas.showcase.gen import Slip, routine
from verytas.showcase.spec import CLEAN, Company, Member, Piece, fixed

TEAL, DEEP, MINT, CORAL = (16, 110, 120), (10, 62, 74), (168, 222, 200), (240, 150, 110)
SUN, CREAM, INK = (250, 200, 90), (252, 248, 240), (22, 48, 56)
BRAND = "Dewlight"


# --- artwork -----------------------------------------------------------------------------------------
# The mark is a dew drop with a low sun behind it. Products are drawn as objects (tube, dropper bottle, pump
# bottle) so a bottle shot in a post has real shapes to be matched against, not a flat label.

def _mark(size=400, c1=TEAL, c2=MINT, sun=SUN, dot=CORAL, shine=(255, 255, 255)):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 400
    box = lambda *v: tuple(x * s for x in v)  # noqa: E731
    for i in range(5):  # rays fan out from the sun, behind the drop
        a = 205 + i * 32
        d.pieslice(box(250 - 150, 90 - 150, 250 + 150, 90 + 150), a, a + 12, fill=sun + (255,))
    d.ellipse(box(205, 45, 325, 165), fill=sun + (255,))
    d.polygon([box(185, 70), box(105, 215), box(265, 215)], fill=c1 + (255,))
    d.ellipse(box(90, 160, 280, 350), fill=c1 + (255,))
    d.pieslice(box(90, 160, 280, 350), 90, 270, fill=c2 + (255,))
    d.polygon([box(185, 70), box(105, 215), box(185, 215)], fill=c2 + (255,))
    d.ellipse(box(125, 245, 155, 285), fill=shine + (255,))
    d.ellipse(box(220, 270, 252, 302), fill=dot + (255,))
    d.arc(box(110, 180, 260, 330), 20, 100, fill=shine + (255,), width=max(2, round(5 * s)))
    return img


def _lockup(color=TEAL, mark=None):
    return art.lockup(mark or _mark(), "Dewlight", color)


def _rev():
    return art.on_color(_lockup((255, 255, 255), _mark(c1=(255, 255, 255), c2=(206, 232, 230))), TEAL, 30)


def _wordmark():
    """The name on its own: a coral dew drop over the i and a wave line under the word."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (560, 190), "white")
    d = ImageDraw.Draw(img)
    d.text((30, 28), "Dewlight", fill=TEAL, font=_font(104))
    d.ellipse((318, 20, 340, 42), fill=CORAL)
    for i in range(14):
        x = 34 + i * 36
        d.arc((x, 150, x + 36, 176), 0 if i % 2 else 180, 180 if i % 2 else 360, fill=MINT, width=6)
    return img


def _app_icon():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, 511, 511), radius=112, fill=TEAL + (255,))
    m = _mark(380, c1=(255, 255, 255), c2=(206, 232, 230))
    img.paste(m, (66, 66), m)
    return img


def _old_logo():
    """The 2024 logo: a bottle-green badge with a leaf, a ribbon and the name in capitals."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (440, 440), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((70, 10, 370, 310), fill=(28, 96, 60))
    d.ellipse((88, 28, 352, 292), outline=(236, 214, 120), width=6)
    d.pieslice((130, 80, 310, 260), 200, 340, fill=(236, 214, 120))
    d.polygon([(220, 90), (290, 170), (220, 250), (150, 170)], fill=(120, 190, 120))
    d.line([(220, 100), (220, 250)], fill=(28, 96, 60), width=4)
    for i in range(4):
        d.line([(220, 140 + i * 28), (270 - i * 6, 120 + i * 28)], fill=(28, 96, 60), width=3)
    d.polygon([(40, 320), (400, 320), (380, 360), (400, 400), (40, 400), (60, 360)], fill=(236, 214, 120))
    d.text((70, 330), "DEWLIGHT", fill=(28, 96, 60), font=_font(54))
    return img


def _tube(body, cap, band, title, sub, shape="sun", size=(300, 620)):
    """A squeeze tube standing on its cap: crimped seal at the top, a diagonal colour band, an emblem and a label."""
    from PIL import Image, ImageDraw

    w, h = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(w * .22, h * .08), (w * .78, h * .08), (w * .88, h * .84), (w * .12, h * .84)], fill=body + (255,))
    d.rectangle((w * .2, h * .02, w * .8, h * .08), fill=(225, 228, 230, 255))
    for i in range(9):
        x = w * .22 + i * w * .0625
        d.line([(x, h * .02), (x, h * .08)], fill=(150, 156, 160, 255), width=2)
    d.polygon([(w * .14, h * .66), (w * .86, h * .56), (w * .88, h * .84), (w * .12, h * .84)], fill=band + (255,))
    d.rounded_rectangle((w * .27, h * .84, w * .73, h * .98), radius=int(w * .05), fill=cap + (255,))
    e = art.emblem(shape, int(w * .34), band, DEEP, (255, 255, 255))
    img.paste(e, (int(w * .33), int(h * .12)), e)
    art.fit_text(d, (int(w * .2), int(h * .34)), title, int(w * .6), INK, start=int(h * .08))
    art.fit_text(d, (int(w * .2), int(h * .46)), sub, int(w * .6), INK, start=int(h * .05), bold=False)
    art.fit_text(d, (int(w * .22), int(h * .72)), "50 ml", int(w * .3), (255, 255, 255), start=int(h * .05))
    return img


def _sunscreen():
    return _tube((250, 218, 120), CORAL, CORAL, "Dew Shield", "SPF 40 PA+++", "sun")


def _facewash():
    return _tube((214, 240, 232), DEEP, (60, 150, 150), "Cloud Wash", "gentle face wash", "shield")


def _serum(size=(320, 620)):
    """A dropper bottle: amber glass, a coral bulb on a ribbed collar, a cream label with a leaf."""
    from PIL import Image, ImageDraw

    w, h = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((w * .4, h * .02, w * .6, h * .16), fill=CORAL + (255,))
    d.rectangle((w * .36, h * .14, w * .64, h * .22), fill=(210, 214, 216, 255))
    for i in range(7):
        x = w * .37 + i * w * .04
        d.line([(x, h * .14), (x, h * .22)], fill=(130, 136, 140, 255), width=2)
    d.rounded_rectangle((w * .24, h * .22, w * .76, h * .98), radius=int(w * .1), fill=(176, 112, 40, 255))
    d.rounded_rectangle((w * .28, h * .26, w * .4, h * .9), radius=8, fill=(214, 160, 84, 255))
    d.rounded_rectangle((w * .3, h * .44, w * .7, h * .84), radius=10, fill=CREAM + (255,))
    e = art.emblem("leaf", int(w * .22), TEAL, MINT, DEEP)
    img.paste(e, (int(w * .39), int(h * .47)), e)
    art.fit_text(d, (int(w * .34), int(h * .62)), "Even Dew", int(w * .32), INK, start=int(h * .07))
    art.fit_text(d, (int(w * .34), int(h * .73)), "5% niacinamide", int(w * .32), (90, 90, 90), start=int(h * .04), bold=False)
    return img


def _oil(size=(300, 660)):
    """A pump bottle of hair oil: dark amber body, a pump head and a gold loop emblem."""
    from PIL import Image, ImageDraw

    w, h = size
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((w * .46, h * .1, w * .54, h * .2), fill=(60, 60, 66, 255))
    d.rounded_rectangle((w * .3, h * .02, w * .7, h * .1), radius=10, fill=(60, 60, 66, 255))
    d.polygon([(w * .62, h * .04), (w * .86, h * .04), (w * .86, h * .08), (w * .62, h * .08)], fill=(60, 60, 66, 255))
    d.rounded_rectangle((w * .22, h * .18, w * .78, h * .98), radius=int(w * .12), fill=(104, 58, 30, 255))
    d.rounded_rectangle((w * .26, h * .22, w * .36, h * .92), radius=8, fill=(150, 96, 56, 255))
    d.rectangle((w * .22, h * .5, w * .78, h * .84), fill=(40, 80, 70, 255))
    e = art.emblem("loop", int(w * .3), (236, 200, 120), (250, 230, 170), (236, 200, 120))
    img.paste(e, (int(w * .35), int(h * .53)), e)
    art.fit_text(d, (int(w * .27), int(h * .69)), "Amla Night Oil", int(w * .46), (255, 255, 255), start=int(h * .06))
    art.fit_text(d, (int(w * .27), int(h * .78)), "100 ml", int(w * .3), (210, 230, 220), start=int(h * .04), bold=False)
    return img


def _old_pack():
    """The retired 2024 sun cream jar: round, green, with a flower ring. No longer sold."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (520, 460), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((60, 40, 460, 140), radius=30, fill=(236, 214, 120, 255))
    d.rounded_rectangle((40, 130, 480, 440), radius=60, fill=(28, 96, 60, 255))
    d.ellipse((150, 170, 370, 390), fill=(250, 245, 225, 255))
    for i in range(8):
        a = i * 45
        d.pieslice((170, 190, 350, 370), a, a + 22, fill=(120, 190, 120, 255))
    d.ellipse((220, 240, 300, 320), fill=(236, 214, 120, 255))
    d.text((176, 396), "Sun Cream", fill=(250, 245, 225, 255), font=art.font(38))
    return img


def _partner():
    """Arogyam Pharmacy: a blue shield with a white cross and three beads. No lettering."""
    from PIL import ImageDraw

    img = art.emblem("shield", 300, (30, 90, 170), (20, 62, 130), (150, 200, 240))
    d = ImageDraw.Draw(img)
    d.rectangle((128, 70, 172, 210), fill=(255, 255, 255, 255))
    d.rectangle((80, 118, 220, 162), fill=(255, 255, 255, 255))
    for i in range(3):
        d.ellipse((108 + i * 36, 222, 128 + i * 36, 242), fill=(150, 200, 240, 255))
    return img


def _competitor():
    """Glowmatic: a violet hexagon with a gold eight-point star. The name is set beside it, not inside it."""
    from PIL import ImageDraw

    img = art.emblem("hex", 300, (110, 50, 150), (80, 30, 120), (60, 20, 90))
    d = ImageDraw.Draw(img)
    cx, cy = 150, 150
    pts = []
    for i in range(16):
        r = 92 if i % 2 == 0 else 38
        a = math.pi / 8 * i - math.pi / 2
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    d.polygon(pts, fill=(250, 210, 70, 255))
    d.ellipse((130, 130, 170, 170), fill=(110, 50, 150, 255))
    return img


ARTWORK = [
    {"name": "Dewlight logo", "kind": "logo", "wordmark": "Dewlight", "image": lambda: _lockup().convert("RGBA"),
     "notes": "Primary lockup: the drop and sun emblem left of the name. Clear space of one drop width. Brand book 2026, p.4."},
    {"name": "Dewlight wordmark", "kind": "wordmark", "part": "wordmark", "wordmark": "Dewlight", "image": _wordmark,
     "notes": "The name alone, with the coral dew drop and the wave. Always Dewlight, never DewLight. Brand book 2026, p.2."},
    {"name": "Dewlight logo, reversed", "kind": "logo", "wordmark": "Dewlight", "image": _rev,
     "notes": "White on brand teal, for posters, video end cards and carton flaps. Brand book 2026, p.5."},
    {"name": "Dewlight app icon", "kind": "icon", "part": "icon", "image": _app_icon,
     "notes": "Store and marketplace listings. Never stretched into a banner."},
    {"name": "Dew Shield sunscreen tube", "kind": "packaging", "image": _sunscreen,
     "notes": "The sunscreen as sold: yellow tube, teal band, SPF 40 PA+++ printed on the front."},
    {"name": "Even Dew serum bottle", "kind": "product", "image": _serum,
     "notes": "The 5% niacinamide serum in its amber dropper bottle."},
    {"name": "Amla Night Oil bottle", "kind": "product", "image": _oil,
     "notes": "The hair oil in its dark amber pump bottle."},
    {"name": "Sun Cream jar 2024", "kind": "packaging", "retired": True, "image": _old_pack,
     "notes": "Retired with the rebrand. Still sits on old shelves and in old creative; do not show it."},
    {"name": "Dewlight logo 2024", "kind": "logo", "retired": True, "wordmark": "DEWLIGHT", "image": _old_logo,
     "notes": "Green badge logo, retired in March 2026. Still found on partner decks and old stockists' signs."},
    {"name": "Dewlight waves", "kind": "pattern",
     "image": lambda: art.pattern("waves", 600, CREAM, TEAL, MINT), "notes": "Backgrounds for cartons, stalls and print."},
    {"name": "Arogyam Pharmacy", "kind": "partner", "wordmark": "Arogyam Pharmacy", "image": _partner,
     "notes": "Pharmacy partner. Shown at equal height beside ours, never inside our logo's clear space."},
    {"name": "Glowmatic", "kind": "competitor", "wordmark": "Glowmatic", "image": _competitor,
     "notes": "A rival skincare brand. Its mark and its bottles must not appear in our content."},
]


# --- the library ---------------------------------------------------------------------------------------

def _r(code, category, kind, severity, title, text, pattern=None, bad=None, good=None, ref=None):
    return {"code": code, "category": category, "kind": kind, "severity": severity, "title": title, "text": text,
            "pattern": pattern or {}, "bad_examples": bad or [], "good_examples": good or [], "source_ref": ref}


RULES = [
    _r("TONE-WARM", "tone", "semantic", "should", "A knowledgeable friend, not a brochure",
       "Write like a friend who knows skin: plain, warm and specific. No clinical jargon and no hype.",
       bad=["Revolutionary dermo-cosmetic technology unlocks epidermal renewal paradigms"],
       good=["Apply a pea-sized amount each morning and notice how your skin feels"], ref="Brand book 2026, p.6"),
    _r("TONE-HYPE", "tone", "deterministic", "should", "No miracle language",
       "Skincare is a routine, not a miracle. Skip magic, miracle, flawless and countdown pressure.",
       {"type": "banned_terms", "terms": ["miracle", "magic", "magical", "game-changer", "game changer", "holy grail",
                                          "flawless", "cheapest", "lowest price", "hurry", "last chance",
                                          "don't miss out"]}, ref="Brand book 2026, p.7"),
    _r("TERM-NAMES", "terminology", "deterministic", "must", "Our names, spelled our way",
       "Write Dewlight, Dew Shield, Even Dew, Cloud Wash and Amla Night Oil exactly like this.",
       {"type": "casing", "terms": ["Dewlight", "Dew Shield", "Even Dew", "Cloud Wash", "Amla Night Oil"]},
       ref="Brand book 2026, p.3"),
    _r("TERM-HOUSE", "terminology", "deterministic", "should", "House spellings",
       "Use our house words so the range reads the same everywhere.",
       {"type": "preferred_terms", "map": {"sunblock": "sunscreen", "sun cream": "sunscreen", "skin care": "skincare",
                                           "face-wash": "face wash", "e-mail": "email"}}, ref="Brand book 2026, p.9"),
    _r("CLAIM-DRUG", "claims", "deterministic", "must", "No drug or medical claims",
       "Cosmetics do not cure, treat or heal. Never claim a cure, a treatment or a permanent result for acne, "
       "pigmentation, scars or hair loss.",
       {"type": "banned_terms", "terms": ["cures", "cure acne", "treats acne", "treats pigmentation",
                                          "treats dark spots", "clears acne", "heals", "permanent results",
                                          "permanently", "removes scars", "prescription strength", "ilaaj",
                                          "pakka theek"]},
       ref="Regulatory note RA-1; Drugs and Cosmetics Act, misleading claims"),
    _r("CLAIM-NATURAL", "claims", "deterministic", "must", "No chemical-free or toxin-free",
       "Everything is made of chemicals, water included. 'Chemical-free', 'toxin-free' and 'detox' are banned.",
       {"type": "banned_terms", "terms": ["chemical-free", "chemical free", "toxin-free", "toxin free", "detox",
                                          "100% natural", "zero chemicals"]},
       ref="Regulatory note RA-3; ASCI guidelines on misleading claims"),
    _r("MSG-FAIRNESS", "messaging", "deterministic", "must", "No fairness or whitening language",
       "We never promise a lighter skin tone. Fairness, whitening and lightening language is banned in every "
       "language, whatever the picture shows.",
       {"type": "banned_terms", "terms": ["fairness", "fair skin", "fairer", "whitening", "whiten", "lightens",
                                          "lightening", "gora"]},
       ref="Brand book 2026, p.12; ASCI guidance on skin-colour claims"),
    _r("CLAIM-PROOF", "claims", "semantic", "must", "Clinically proven needs the study",
       "'Clinically proven', 'dermatologist approved' and 'dermatologically tested' come only with the study "
       "behind them: its size, its length and what it measured.",
       bad=["Clinically proven to transform your skin, dermatologist approved for everyone",
            "Doctors recommend it and the science is proven"],
       good=["In a dermatologist-supervised study of 62 volunteers, 84% said their skin looked more even"],
       ref="Regulatory note RA-2"),
    _r("LEGAL-SUN", "legal", "deterministic", "must", "Sun protection exactly as tested",
       "Quote the SPF and PA we tested, and never say all-day, total or waterproof protection or that nobody "
       "needs to reapply.",
       {"type": "banned_terms", "terms": ["all-day protection", "all day protection", "100% protection",
                                          "total sun block", "waterproof", "sweatproof", "sunproof",
                                          "no need to reapply", "sunburn-proof"]},
       ref="Regulatory note RA-4; Lab report SUN-2026-03"),
    _r("LEGAL-PARTNER", "legal", "semantic", "must", "Paid partnerships say so",
       "A post by a creator we pay or gift must start with a clear disclosure such as 'Paid partnership with "
       "Dewlight' or #ad, before any code or link.",
       bad=["Obsessed with this sunscreen, use my code from the link in my bio to save on your order",
            "Dewlight sent me their new serum and I am loving it, grab yours with my code"],
       good=["Paid partnership with Dewlight. I wore Dew Shield on my commute and it sat well under makeup"],
       ref="ASCI influencer guidelines; Regulatory note RA-6"),
    _r("LEGAL-RESULTS", "legal", "semantic", "must", "Before and after must be real and labelled",
       "A before and after picture is real, unretouched and labelled as such, with the time between the two and "
       "'individual results vary'.",
       bad=["Before and after four weeks of Even Dew, see the transformation",
            "Look at her skin change completely with just one serum"],
       good=["Real skin, no filter and no retouching. Day one and week four of Even Dew. Individual results vary"],
       ref="Regulatory note RA-5"),
    _r("LEGAL-CRUELTY", "legal", "semantic", "must", "Cruelty free needs the certificate",
       "'Cruelty free' and 'vegan' are said only with the certification behind them and its year.",
       bad=["We are 100% cruelty free and vegan, always have been"],
       good=["Dewlight has been certified cruelty free since 2025; the certificate is on our website"],
       ref="Regulatory note RA-7"),
    _r("MSG-BODYSHAME", "messaging", "semantic", "must", "Never shame skin or bodies",
       "Do not use fear, embarrassment or comparison about skin, hair, weight or age. Nobody needs fixing.",
       bad=["Embarrassed by your oily, ugly skin? Everyone is staring at it",
            "Nobody will love you with those dark circles and that dull face"],
       good=["Oily or dry, your skin is yours; here is a routine that suits it"], ref="Brand book 2026, p.13"),
    _r("MSG-INCLUSIVE", "messaging", "semantic", "should", "Every skin tone, every person",
       "Show and speak to every skin tone, gender and age. No ideal complexion, and no assumption that skin care "
       "is for one kind of person.",
       bad=["Get the skin your boyfriend will love", "Glowing skin for the perfect bride"],
       good=["Every skin tone and every skin story is welcome here"], ref="Brand book 2026, p.13"),
    _r("MSG-COMPETITOR", "messaging", "deterministic", "must", "Never name another brand",
       "Do not name competing skincare brands, even to say we are different.",
       {"type": "banned_terms", "terms": ["Glowmatic", "Glow Matic"]}, ref="Brand book 2026, p.11"),
    _r("MSG-RIVALS", "messaging", "semantic", "must", "No digs at other brands",
       "Talk about what we make. Never mock or compare against other skincare brands, by name or by hint.",
       bad=["Unlike other brands that sell false hopes, we are honest", "The other big sunscreen feels sticky"],
       good=["Dew Shield is a light gel-cream that sinks in without a white cast"], ref="Brand book 2026, p.11"),
    _r("A11Y-INGREDIENTS", "accessibility", "semantic", "should", "Ingredients readable, in text too",
       "An ingredient list or usage note shown in an image must be readable at a glance (strong contrast) and "
       "repeated as text in the post.",
       bad=["Full ingredient list printed in pale grey on white in the picture only"],
       good=["Ingredients in dark ink on a plain card, and listed again in the caption"], ref="Brand book 2026, p.16"),
    _r("VIS-PALETTE", "visual", "deterministic", "should", "Brand colours only",
       "Posters and cards use the Dewlight palette: teal, mint, coral, sun yellow and cream.",
       {"type": "palette", "colors": ["#106E78", "#0A3E4A", "#A8DEC8", "#F0966E", "#FAC85A", "#FCF8F0"],
        "max_delta_e": 18, "min_share": 0.12}, ref="Brand book 2026, p.15"),
    _r("CONF-CUSTOMER", "confidentiality", "deterministic", "must", "No customer identifiers",
       "Order IDs, complaint numbers and customer phone numbers never appear in a post, even in a screenshot.",
       {"type": "banned_terms", "terms": ["order id", "order number", "complaint number", "ticket number",
                                          "complaint id"]}, ref="Privacy policy 4.2"),
]

# The offline judge scores a paragraph by its word overlap with the rule's examples, so every semantic rule
# also carries ordinary, compliant skincare copy; the hosted judge reads the rule itself and ignores this.
_ORDINARY = ["Apply a little each morning and see how your skin feels by the evening",
             "Our routine is simple: cleanse, apply your serum and finish with sunscreen",
             "This week on the blog: short guides to your routine, from the team that makes it"]
for _rule in RULES:
    if _rule["kind"] == "semantic":
        _rule["good_examples"] = [*_rule["good_examples"], *_ORDINARY]

FACTS = [
    {"key": "spf", "statement": "Dew Shield sunscreen is tested at SPF 40 and PA+++", "value": 40, "unit": "SPF",
     "subject": "Dew Shield SPF", "source_ref": "Lab report SUN-2026-03, independent lab, March 2026", "from": -230},
    {"statement": "Dew Shield is water resistant for up to 80 minutes in testing", "value": 80, "unit": "minutes",
     "subject": "Dew Shield water resistance", "source_ref": "Lab report SUN-2026-03, independent lab", "from": -230},
    {"statement": "Even Dew serum contains 5% niacinamide", "value": 5, "unit": "%", "subject": "Even Dew niacinamide",
     "source_ref": "Formulation sheet ED-2, 2026", "from": -300},
    {"statement": "62 volunteers used Even Dew for 8 weeks in a dermatologist-supervised study", "value": 62,
     "unit": "volunteers", "subject": "Even Dew dermatologist study", "source_ref": "Study DL-ED-04, 2026",
     "from": -150},
    {"statement": "84% of the 62 study volunteers said their skin looked more even after 8 weeks of Even Dew",
     "value": 84, "unit": "%", "subject": "Even Dew study volunteers more even", "source_ref": "Study DL-ED-04, 2026",
     "from": -150},
    {"statement": "Dewlight has been certified cruelty free since 2025", "value": 2025, "unit": "year",
     "subject": "cruelty free certification", "source_ref": "Certificate CF-2025-118, March 2025", "from": -420},
    {"key": "customers_old", "statement": "Dewlight has 400,000 customers", "value": 400000, "unit": "customers",
     "subject": "customers", "source_ref": "Annual review 2025, p.3", "from": -420},
    {"key": "customers", "statement": "Dewlight has 650,000 customers", "value": 650000, "unit": "customers",
     "subject": "customers", "source_ref": "Annual review 2026, p.3", "from": -200, "supersedes": "customers_old"},
    {"key": "rating_old", "statement": "Customers rate Dewlight 4.2 out of 5", "value": 4.2, "unit": "out of 5",
     "subject": "rating", "source_ref": "Marketplace listing, 2025", "from": -420},
    {"key": "rating", "statement": "Customers rate Dewlight 4.5 out of 5", "value": 4.5, "unit": "out of 5",
     "subject": "rating", "source_ref": "Marketplace listing, Sept 2026", "from": -60, "supersedes": "rating_old"},
    {"statement": "Cloud Wash has a pH of 5.5", "value": 5.5, "unit": "pH", "subject": "Cloud Wash pH",
     "source_ref": "Formulation sheet CW-1, 2026", "from": -300},
    {"statement": "Monsoon Sale gave 25% off on Dew Shield", "value": 25, "unit": "%", "subject": "sale discount Dew Shield",
     "source_ref": "Monsoon Sale brief", "from": -150, "to": -110},
    {"statement": "20% off on Dew Shield during the Festive Care Sale", "value": 20, "unit": "%",
     "subject": "sale discount Dew Shield", "source_ref": "Festive Care Sale brief", "from": -4, "to": 9},
    {"statement": "Moonlit retinol night serum contains 0.3% retinol", "value": 0.3, "unit": "%",
     "subject": "Moonlit retinol", "source_ref": "Moonlit launch brief (embargoed)", "from": 34},
]

TERMS = [
    {"term": "Project Moonlit", "note": "The retinol night line. Launch date and ingredients are embargoed.",
     "embargo": 34},
    {"term": "Tara Vellore", "note": "Celebrity collaboration capsule. Name and fee under contract until the "
     "announcement.", "embargo": 17},
    {"term": "Project Sandstone", "note": "Sunscreen reformulation after the batch complaints. Never public."},
]

CONTACTS = [
    {"kind": "phone", "value": "+91 22 4000 7100", "label": "Customer care", "source_ref": "dewlight.example/care"},
    {"kind": "phone", "value": "+91 22 4000 7111", "label": "Press desk", "source_ref": "dewlight.example/press"},
    {"kind": "phone", "value": "+91 22 4000 7133", "label": "WhatsApp order updates", "source_ref": "Care charter"},
    {"kind": "email", "value": "*@dewlight.example", "label": "Company domain", "source_ref": "IT policy"},
    {"kind": "url", "value": "dewlight.example", "label": "Website", "source_ref": "Brand book 2026, p.2"},
    {"kind": "url", "value": "care.dewlight.example", "label": "Care centre", "source_ref": "Care charter"},
    {"kind": "handle", "value": "@dewlight", "label": "Social handle", "source_ref": "Brand book 2026, p.2"},
    {"kind": "handle", "value": "@dewlight.care", "label": "Care handle", "source_ref": "Care charter"},
]

EVENTS = [
    {"key": "summer", "created": 52, "name": "Summer Sun Care campaign", "kind": "campaign", "start": -48, "end": -20,
     "hashtags": ["#SunSmartIndia"], "avoid_terms": ["sunblock", "all day protection", "waterproof"],
     "guidance": "Daily sunscreen habit, with the SPF and PA exactly as tested. Reapply, shade, hats. No claims about "
     "tanning or skin tone.", "summary": "A daily-sunscreen campaign around Dew Shield."},
    {"key": "skinday", "created": 40, "name": "World Skin Health Day", "kind": "other", "start": -35, "end": -35,
     "hashtags": ["#SkinHealthDay"], "guidance": "Educate, do not sell. See a dermatologist for medical concerns; "
     "no product claims in the same post.", "summary": "Skin health tips for one day, no discounts."},
    {"key": "complaint", "created": 16, "name": "Allergic-reaction complaints, Dew Shield batch", "kind": "crisis",
     "start": -16, "end": -11, "blackout": True,
     "guidance": "Acknowledge plainly. No jokes, no sales, no 'safe for everyone'. Point to customer care and a "
     "doctor.", "summary": "Reports of rashes on one batch of Dew Shield; the batch is paused."},
    {"key": "sale", "created": 4, "name": "Festive Care Sale", "kind": "sale", "start": -3, "end": 8,
     "hashtags": ["#FestiveCare"], "avoid_terms": ["cheapest", "lowest price ever"],
     "guidance": "Lead with care and routine, the discount second. State what, for whom and until when.",
     "summary": "20% off Dew Shield across the festive week."},
    {"key": "collab", "created": 4, "name": "Dewlight x a celebrity capsule", "kind": "partnership", "start": 17,
     "hashtags": ["#DewlightCapsule"], "guidance": "Until the announcement, tease the feeling, not the name. No "
     "photos, no fee, no dates.", "summary": "A limited capsule with a film actor."},
    {"key": "moonlit", "created": 6, "name": "Moonlit retinol launch", "kind": "launch", "start": 34,
     "hashtags": ["#MeetMoonlit"], "guidance": "Embargoed. No ingredient names, no strengths, no dates until launch "
     "day.", "summary": "A night serum line, launching in the winter."},
]

PEOPLE = [
    {"name": "Naina Verghese", "kind": "ambassador", "aliases": ["Naina"], "channels": ["instagram", "youtube"],
     "events": ["summer"], "from": -70, "to": 90,
     "notes": "Brand ambassador. Agreement 22-B: Instagram and YouTube, Summer Sun Care campaign only. Photos "
     "approved by her team."},
    {"name": "Tara Vellore", "kind": "celebrity", "aliases": ["Tara"], "channels": ["instagram"], "events": ["collab"],
     "from": 17, "to": 120, "notes": "Capsule collaboration. Cleared for posts only after the announcement."},
    {"name": "Kiara Malhotra", "kind": "creator", "aliases": ["Kiara"], "channels": ["instagram"],
     "from": -200, "to": 160, "notes": "Beauty creator under a paid agreement. Disclosure is required on every post."},
    {"name": "Zainab Qureshi", "kind": "creator", "aliases": ["Zainab"], "channels": ["instagram", "youtube"],
     "from": -160, "to": 200, "notes": "Skincare creator under a paid agreement. Disclosure is required."},
    {"name": "Dr. Sameer Khot", "kind": "other", "aliases": ["Sameer Khot"], "channels": ["youtube", "blog"],
     "from": -400, "to": -42, "notes": "Consulting dermatologist. Agreement ended; renewal under discussion."},
]

TEAM = [
    Member("admin", "ritika@dewlight.example", "Ritika Menon", "brand_admin", title="Head of brand",
           blurb="Owns the brand library: rules, facts, artwork, events. Sees every screen."),
    Member("approver", "dhruv@dewlight.example", "Dhruv Menon", "approver", title="Brand marketing manager",
           blurb="Works the review queue: approves, sends back, rules on escalations."),
    Member("reviewer", "farah@dewlight.example", "Farah Qureshi", "reviewer"),
    Member("auditor", "isha@dewlight.example", "Isha Rane", "auditor"),
    Member("ra", "kavya@dewlight.example", "Dr. Kavya Nambiar", "reviewer", title="Regulatory affairs"),
]
CREATORS = [
    Member("ira", "ira@dewlight.example", "Ira Kapoor", "creator", "careful"),
    Member("rhea", "rhea@dewlight.example", "Rhea D'Souza", "creator", "intern"),
    Member("nikhil", "nikhil@dewlight.example", "Nikhil Bansal", "creator", "marketer"),
    Member("sunita", "sunita@dewlight.example", "Sunita Iyengar", "creator", "regional"),
    Member("tanvi", "tanvi@dewlight.example", "Tanvi Shah", "creator", "careful"),
    Member("lumen", "studio@lumenworks.example", "Lumen Works (agency)", "creator", "agency"),
    Member("kiara", "kiara@creators.example", "Kiara Malhotra (beauty creator)", "creator", "influencer"),
    Member("zainab", "zainab@creators.example", "Zainab Qureshi (skincare creator)", "creator", "influencer"),
    Member("arman", "arman@dewlight.example", "Arman Pillai", "creator", "intern"),
    Member("meenal", "meenal@dewlight.example", "Meenal Rao", "creator", "regional"),
]
DEMO = [
    ("approver", "approver", "manager", "Brand marketing manager",
     "Works the review queue: approves, sends back, rules on escalations."),
    ("admin", "admin", "manager", "Head of brand",
     "Owns the brand library: rules, facts, artwork, events. Sees every screen."),
    ("c2", "nikhil", "creator", "Content creator", "Performance posts. His numbers and claims drift from the facts."),
    ("c1", "rhea", "creator", "Content creator", "Instagram and X. Her tone and claims slip when she is in a hurry."),
    ("c5", "lumen", "creator", "Agency", "An outside agency writing campaigns for the brand."),
    ("c6", "kiara", "creator", "Beauty creator", "A paid creator. Her posts need the partnership disclosure."),
]

# Farah is strict on tone and wording, Dhruv practical, Dr. Nambiar (regulatory) cares only about claims and law.
# The unclear rules (hype words, the fairness stance post, comparisons) are where they split and say so.
_UNCLEAR = ("guideline_unclear", "Does the rule mean this? It is not about our product.")
STANCE = {
    "reviewer": {"TONE-HYPE": (0.75, [("false_positive", "Not about the product."), _UNCLEAR]),
                 "TONE-WARM": (0.8, [("false_positive", "Warm enough for this channel.")]),
                 "MSG-FAIRNESS": (0.98, []), "MSG-BODYSHAME": (0.98, []), "TERM-HOUSE": (0.95, []),
                 "*": (0.8, [("not_applicable", "Does not apply.")])},
    "approver": {"TONE-HYPE": (0.5, [("intentional", "Playful on purpose for this post."), _UNCLEAR]),
                 "MSG-FAIRNESS": (0.6, [("intentional", "A statement against fairness creams, not a promise.")]),
                 "CLAIM-PROOF": (0.55, [("false_positive", "A general statement, not a claim about our study.")]),
                 "MSG-RIVALS": (0.4, [_UNCLEAR, ("false_positive", "Names nobody.")]),
                 "A11Y-INGREDIENTS": (0.4, [("not_applicable", "The list is repeated in the caption.")]),
                 "*": (0.7, [("false_positive", "Reads fine to me.")])},
    "ra": {"CLAIM-DRUG": (1.0, []), "CLAIM-NATURAL": (1.0, []), "CLAIM-PROOF": (1.0, []), "LEGAL-SUN": (1.0, []),
           "LEGAL-PARTNER": (1.0, []), "LEGAL-RESULTS": (1.0, []), "LEGAL-CRUELTY": (1.0, []),
           "CLAIM-CONTRADICTED": (1.0, []), "CLAIM-OUTDATED": (1.0, []), "MSG-FAIRNESS": (1.0, []),
           "TONE-HYPE": (0.3, [("not_applicable", "Not a regulatory matter.")]),
           "*": (0.6, [("not_applicable", "Outside regulatory's remit.")])},
}


# --- the pictures --------------------------------------------------------------------------------------

def _img(key, alt, img):
    return lambda: [art.image_attachment(key, alt, img() if callable(img) else img)]


def _poster(headline, sub="", logo="ok", prod=None, size=(1080, 1080), bg=TEAL):
    """A teal campaign card with a product on the right. `logo` says how the mark was used: as registered,
    stretched about a third wider, the retired 2024 version, or recoloured."""
    img = art.card(size, bg, headline, sub, art=prod, art_w=340)
    rev = _rev()
    if logo == "ok":
        art.paste(img, rev, (74, 880), width=420)
    elif logo == "stretched":
        natural = round(rev.height * 420 / rev.width)
        art.paste(img, rev, (74, 880), width=560, height=natural)
    elif logo == "old":
        art.paste(img, _old_logo(), (74, 840), width=330)
    elif logo == "recolour":
        art.paste(img, art.recolour(rev, "gbr"), (74, 880), width=420)
    return img


def _oldpack_ad():
    img = art.card((1080, 1080), TEAL, "Summer sun care", "Daily protection for the whole family", art=_old_pack(),
                   art_w=420)
    art.paste(img, _rev(), (74, 880), width=420)
    return img


def _compare():
    from PIL import Image, ImageDraw

    img = art.canvas((1080, 1080), CREAM)
    d = ImageDraw.Draw(img)
    d.text((80, 90), "Which sunscreen feels lighter?", fill=INK, font=art.font(60))
    art.paste(img, _sunscreen(), (110, 260), width=260)
    bottle = Image.new("RGBA", (300, 560), (0, 0, 0, 0))
    bd = ImageDraw.Draw(bottle)
    bd.rounded_rectangle((70, 10, 230, 70), radius=14, fill=(70, 40, 100, 255))
    bd.rounded_rectangle((40, 60, 260, 550), radius=50, fill=(200, 170, 220, 255))
    bottle.paste(_competitor().resize((180, 180)), (60, 200), _competitor().resize((180, 180)))
    art.paste(img, bottle, (660, 260), width=260)
    d.text((470, 460), "vs", fill=INK, font=art.font(52))
    return img


def _ambassador(skin, caption):
    img = art.portrait((1080, 1080), skin, CREAM, TEAL, caption)
    art.paste(img, _lockup().convert("RGBA"), (60, 40), width=300)
    return img


def _before_after(label: str = ""):
    """Two portraits, day one and week four. The fixed version carries the label the rule asks for."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1200, 700), CREAM)
    left = art.portrait((560, 560), (170, 118, 92), MINT, TEAL)
    right = art.portrait((560, 560), (176, 124, 96), MINT, TEAL)
    img.paste(left, (30, 30))
    img.paste(right, (610, 30))
    d = ImageDraw.Draw(img)
    d.text((40, 610), "Day one", fill=INK, font=art.font(40))
    d.text((620, 610), "Week four", fill=INK, font=art.font(40))
    if label:
        d.text((300, 650), label, fill=INK, font=art.font(26, False))
    return img


def _ingredient_panel(ink):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1000, 700), "white")
    d = ImageDraw.Draw(img)
    d.text((60, 50), "Even Dew ingredients", fill=ink, font=art.font(54))
    lines = ["Aqua, Glycerin, Niacinamide 5%", "Panthenol, Sodium hyaluronate", "Allantoin, Citric acid",
             "Phenoxyethanol, Ethylhexylglycerin"]
    for i, ln in enumerate(lines):
        d.text((60, 190 + i * 90), ln, fill=ink, font=art.font(40, False))
    art.paste(img, _serum().resize((140, 270)), (800, 250))
    return img


def _partner_card():
    from PIL import ImageDraw

    img = art.canvas((1200, 628), (255, 255, 255))
    art.paste(img, _lockup().convert("RGBA"), (80, 200), width=420)
    art.paste(img, _partner(), (700, 150), width=300)
    ImageDraw.Draw(img).text((690, 470), "Arogyam Pharmacy", fill=(30, 90, 170), font=art.font(36))
    return img


# --- the eight weeks, scripted -------------------------------------------------------------------------

def _back(note, by="approver"):
    return [(1, "send", {}), (3, "autodecide", {"by": "reviewer"}), (6, "back", {"note": note, "by": by})]


def _rounds(rounds: list[tuple[str, str]], by: str = "reviewer", final: str = "approver") -> list:
    """Sent back and fixed over several rounds: each (note, revised body), the last one finally approved."""
    flow: list = [(1, "send", {}), (3, "autodecide", {"by": by})]
    t = 6.0
    for note, body in rounds:
        flow += [(t, "back", {"note": note}), (t + 14, "fix", {"body": body}), (t + 15, "send", {})]
        if body is not rounds[-1][1]:
            flow.append((t + 18, "autodecide", {"by": by}))
        t += 20
    flow += [(t + 4, "approve", {"by": final}), (t + 20, "publish", {})]
    return flow


def _stories() -> list[Piece]:
    sm, sk, cr, sl, mo = "summer", "skinday", "complaint", "sale", "moonlit"
    pk = Piece
    return [
        # --- Summer Sun Care campaign ---
        pk("s-launch", "ira", "Dew Shield is here", "instagram", "Summer is here and so is Dew Shield, a sunscreen tested at SPF 40 and PA+++. Make it the last step of your morning routine. #SunSmartIndia", 51, CLEAN, event=sm,
           images=_img("tube", "The Dew Shield sunscreen tube on a teal card with the Dewlight logo", lambda: _poster("Meet Dew Shield", "SPF 40 PA+++", "ok", _sunscreen()))),
        pk("s-spf50", "nikhil", "Dew Shield SPF line", "instagram", "Dew Shield gives you SPF 50 protection. Wear it and forget it. #SunSmartIndia", 50,
           fixed("The tested value is SPF 40 and PA+++. Quote that exactly, and keep the reapply advice in.", "Dew Shield is tested at SPF 40 and PA+++. Wear it each morning and reapply when you are outdoors for long. #SunSmartIndia", "ra"), event=sm),
        pk("s-allday", "lumen", "Beach-day ad", "instagram", "All day protection on the beach. Dew Shield is waterproof and sweatproof, no need to reapply. #SunSmartIndia", 49,
           _rounds([("We cannot say all-day, waterproof or no reapply. The lab report says water resistant for 80 minutes.", "Dew Shield is water resistant for up to 80 minutes in testing. Reapply after swimming. Total sun block for the whole day. #SunSmartIndia"),
                    ("Total sun block is still a protection claim we cannot make. Say what was tested and nothing more.", "Dew Shield is water resistant for up to 80 minutes in testing. Reapply after swimming or towelling off. #SunSmartIndia")], "ra"), event=sm),
        pk("s-reapply", "tanvi", "How often to reapply", "blog", "Sunscreen works best when you reapply it every two hours outdoors. Keep a tube in your bag, wear a hat, and sit in the shade when the sun is high.", 47, CLEAN, event=sm),
        pk("s-lighten", "rhea", "Skin tone line", "instagram", "Dew Shield brightens and lightens your skin tone while it protects. #SunSmartIndia", 46,
           fixed("We never promise a lighter skin tone. Talk about protection and how it feels on skin.", "Dew Shield is a light gel-cream that sinks in and does not leave a white cast. #SunSmartIndia", "ra"), event=sm),
        pk("s-chem", "nikhil", "Clean sun care", "linkedin", "Chemical-free sun care that keeps your skin safe. Dew Shield is 100% natural and toxin free.", 45,
           _rounds([("Chemical-free and 100% natural are banned. Say what is in it instead.", "Dew Shield is a gentle daily sunscreen. It is toxin free and made for sensitive skin."),
                    ("Toxin free is the same claim. Describe the texture and the SPF as tested.", "Dew Shield is a gentle daily sunscreen with SPF 40 and PA+++, in a light gel-cream.")], "ra"), event=sm),
        pk("s-kiara-tag", "kiara", "My commute sunscreen", "instagram", "Day three of testing Dew Shield on my commute. It feels comfortable and not greasy. Use my code from the link in my bio and save on your order. #SunSmartIndia", 44,
           fixed("Start with the paid-partnership disclosure, before the code.", "Paid partnership with Dewlight. Day three of testing Dew Shield on my commute. It feels comfortable and not greasy. #SunSmartIndia", "ra"), event=sm),
        pk("s-stretch", "rhea", "Even Dew bottle shot", "instagram", "A little drop for your evening routine. #SunSmartIndia", 43,
           fixed("The logo is stretched. Use the registered lockup at its own proportions.", "A little drop for your evening routine. Logo corrected. #SunSmartIndia", "reviewer"), event=sm,
           images=_img("serum", "Even Dew serum bottle on a teal card with the Dewlight logo", lambda: _poster("Even Dew", "A little drop for your evening", "stretched", _serum())),
           fix_images=_img("serum", "Even Dew serum bottle on a teal card with the Dewlight logo", lambda: _poster("Even Dew", "A little drop for your evening", "ok", _serum()))),
        pk("s-recolour", "arman", "Dew Shield summer card", "instagram", "Dew Shield, tested at SPF 40 and PA+++. #SunSmartIndia", 42, _back("The logo has been recoloured. Use the teal or the white version from the library."), event=sm,
           images=_img("tubecol", "Dew Shield tube on a card with a recoloured Dewlight logo", lambda: _poster("Summer ready", "SPF 40 PA+++", "recolour", _sunscreen()))),
        pk("s-oldpack", "lumen", "Family sun care ad", "instagram", "Summer sun care for the whole family, from Dewlight. #SunSmartIndia", 41,
           fixed("That jar is the retired 2024 pack. Show the Dew Shield tube.", "Summer sun care for the whole family, from Dewlight. Pack updated. #SunSmartIndia", "approver"), event=sm,
           images=_img("jar", "A green sun cream jar above the Dewlight logo", _oldpack_ad),
           fix_images=_img("jar", "The Dew Shield tube above the Dewlight logo", lambda: _poster("Summer sun care", "Daily protection for the family", "ok", _sunscreen()))),
        pk("s-compare", "kiara", "Honest sunscreen comparison", "instagram", "I put Dew Shield next to the other big sunscreen and here is what I saw. Paid partnership with Dewlight. #SunSmartIndia", 40,
           _back("A rival's bottle in a comparison is a no. Show our own product and say what you like about it."), event=sm,
           images=_img("cmp", "A Dew Shield tube beside a violet bottle with a rival's star logo", _compare)),
        pk("s-glow", "zainab", "Switching sunscreens", "instagram", "Glowmatic sunscreen feels sticky and Dew Shield does not. Paid partnership with Dewlight. #SunSmartIndia", 39,
           [(1, "send", {}), (3, "autodecide", {"by": "reviewer"}), (4, "escalate", {"message": "The brief from the brand team said to contrast with the market leader. Can the team confirm I may name them?", "rule": "MSG-COMPETITOR"}),
            (10, "resolve", {"outcome": "upheld", "note": "Not allowed: we never name another brand. Describe the texture of Dew Shield on its own."})], event=sm),
        pk("s-naina", "ira", "Naina on her morning run", "instagram", "Naina Verghese wears Dew Shield on her morning run. SPF 40 and PA+++, and a hat. #SunSmartIndia", 38, CLEAN, event=sm,
           images=_img("naina", "Naina Verghese outdoors above the Dewlight logo", lambda: _ambassador((150, 100, 76), "Morning run"))),
        pk("s-naina-li", "lumen", "Naina on LinkedIn", "linkedin", "Naina Verghese is the face of our Summer Sun Care campaign. Meet her routine. #SunSmartIndia", 37,
           _back("Naina's agreement covers Instagram and YouTube only, not LinkedIn. Take it down or ask the brand team.", "ra"), event=sm,
           images=_img("naina2", "Naina Verghese smiling above the Dewlight logo", lambda: _ambassador((150, 100, 76), "Summer routine"))),
        pk("s-ingredients", "lumen", "Carton back panel", "packaging", "Back panel copy for the Even Dew carton: ingredients, directions and storage. Ingredients: Aqua, Glycerin, Niacinamide, Panthenol, Sodium hyaluronate.", 36,
           fixed("The ingredient text is too pale to read. Use the dark ink on white.", "Back panel copy for the Even Dew carton: ingredients, directions and storage. Ingredients: Aqua, Glycerin, Niacinamide, Panthenol, Sodium hyaluronate. Ink darkened.", "reviewer"),
           colors=[{"fg": "#A8CFC3", "bg": "#FFFFFF", "where": "ingredient list on the carton", "large": False}],
           fix_colors=[{"fg": "#163038", "bg": "#FFFFFF", "where": "ingredient list on the carton", "large": False}],
           images=_img("panel", "Even Dew ingredient list on a white card", lambda: _ingredient_panel((168, 207, 195))),
           fix_images=_img("panel", "Even Dew ingredient list on a white card", lambda: _ingredient_panel(INK))),
        pk("s-hinglish", "sunita", "Dhoop mein sunscreen", "instagram", "Dhoop mein jaane se pehle Dew Shield lagao. SPF 40 aur PA+++ ke saath. #SunSmartIndia", 35, CLEAN, event=sm, notes={"language": "Hinglish"}),
        pk("s-hi-chem", "meenal", "Bilkul safe sunscreen", "instagram", "Dew Shield bilkul chemical-free hai, skin ke liye safe. #SunSmartIndia", 34,
           [(1, "send", {}), (2, "dispute", {"rule": "CLAIM-NATURAL", "claim": "In Hinglish 'chemical-free' is how our dermatologist explained 'no harsh sulphates'. It is not a claim that the product has no chemicals.", "language": "Hinglish"}),
            (4, "autodecide", {"by": "ra"}), (9, "back", {"note": "The dispute is not upheld: say 'no harsh sulphates' if that is the fact, not chemical-free.", "by": "approver"}),
            (24, "fix", {"body": "Dew Shield mein harsh sulphates nahi hain, aur yeh roz lagane ke liye halka hai. #SunSmartIndia"}), (25, "send", {}), (30, "approve", {}), (50, "publish", {})],
           event=sm, notes={"language": "Hinglish", "intent": "Say there are no harsh sulphates."}),
        # --- World Skin Health Day ---
        pk("sk-clean", "ira", "Skin Health Day tips", "instagram", "On World Skin Health Day: drink water, wear sunscreen, and see a dermatologist when something worries you. #SkinHealthDay", 34.8, CLEAN, event=sk),
        pk("sk-stance", "tanvi", "What we will never sell", "linkedin", "On World Skin Health Day we want to be clear: Dewlight does not sell fairness creams and never will. Every skin tone is welcome here. #SkinHealthDay", 34.5,
           [(1, "send", {}), (2, "dispute", {"rule": "MSG-FAIRNESS", "claim": "The post says we never sell fairness creams. The word is the point: it is a stance against the claim, not a promise of lighter skin."}),
            (4, "autodecide", {"by": "approver"}), (9, "approve", {"note": "Intentional: the word is used to reject the claim."}), (30, "publish", {})], event=sk),
        pk("sk-shame", "arman", "Oily skin post", "instagram", "Embarrassed by your oily, ugly skin? Everyone is staring at it. #SkinHealthDay", 34,
           fixed("No shaming about skin. Oily or dry, your skin is yours.", "Oily or dry, your skin is yours. Here is a simple routine that suits it. #SkinHealthDay", "reviewer"), event=sk),
        pk("sk-cure", "nikhil", "Acne and spots", "instagram", "Even Dew cures acne and treats pigmentation in 7 days. Permanent results. #SkinHealthDay", 33,
           fixed("Cosmetics do not cure or treat. Describe the serum and what it contains.", "Even Dew is a niacinamide serum with 5% niacinamide for your daily routine. See a dermatologist for acne that worries you. #SkinHealthDay", "ra"), event=sk),
        pk("sk-clinical", "nikhil", "Clinically proven line", "x", "Clinically proven results for all skin types. Dermatologist approved. #SkinHealthDay", 33.5,
           _rounds([("Clinically proven needs the study. We have a study of 62 volunteers over 8 weeks; say that.", "Clinically proven results with Even Dew. Dermatologist approved for all skin types. #SkinHealthDay"),
                    ("Still no study behind it. Use the figure from study DL-ED-04.", "In a dermatologist-supervised study of 62 volunteers, 84% said their skin looked more even after 8 weeks of Even Dew. #SkinHealthDay")], "ra"), event=sk),
        pk("sk-niacin", "nikhil", "Serum strength", "instagram", "Even Dew packs 10% niacinamide for your skin. #SkinHealthDay", 32.5,
           fixed("The formulation sheet says 5% niacinamide.", "Even Dew has 5% niacinamide for your skin. #SkinHealthDay", "ra"), event=sk),
        pk("sk-sleep", "ira", "Sleep and skin", "instagram", "A good night's sleep is magic for your skin. Dim the lights and give yourself a calm evening. #SkinHealthDay", 32, CLEAN, event=sk),
        pk("sk-sameer", "ira", "Dr. Sameer answers", "youtube", "Dr. Sameer Khot answers your sunscreen questions in this talk. Chapters are listed below and a transcript is in the description. #SkinHealthDay", 31,
           [(1, "send", {}), (3, "autodecide", {"by": "ra"}), (6, "back", {"note": "Dr. Khot's agreement ended last month. Hold this until it is renewed.", "by": "approver"}),
            (8, "comment", {"by": "ra", "body": "Renewal is with legal. I will tell you the moment it is signed."})], event=sk,
           images=_img("sameer", "Dr. Sameer Khot beside the Dewlight logo", lambda: _ambassador((196, 150, 120), "Ask the dermatologist"))),
        pk("sk-ba", "zainab", "Four weeks of Even Dew", "instagram", "Before and after four weeks of Even Dew. Same light, same camera. Paid partnership with Dewlight. #SkinHealthDay", 30,
           fixed("A before and after must be labelled real, unretouched, with individual results vary.", "Day one and week four of Even Dew. Real skin, no filter and no retouching. Individual results vary. Paid partnership with Dewlight. #SkinHealthDay", "ra"), event=sk,
           images=_img("ba", "Two portraits, day one and week four", _before_after),
           fix_images=_img("ba", "Two portraits, day one and week four, labelled as real skin", lambda: _before_after("Real skin, no filter, no retouching. Individual results vary."))),
        # --- the complaint crisis (blackout) ---
        pk("cr-ack", "ira", "We have heard you", "x", "Some customers reacted to one batch of Dew Shield. We have paused that batch. If your skin reacts to any product, stop using it and speak to a doctor. Our care team is on +91 22 4000 7100.", 15.9, [(0.3, "send", {}), (0.8, "approve", {}), (1.2, "publish", {})]),
        pk("cr-joke", "rhea", "Rash joke", "x", "Plot twist: our sunscreen gave a few of you a rash lol. Aloe vera is free!", 15.5,
           [(0.5, "send", {}), (1.5, "autodecide", {"by": "approver"}), (2, "back", {"note": "No jokes while customers are hurt. Acknowledge it plainly.", "by": "approver"}),
            (6, "fix", {"body": "We are sorry that some of you reacted to a batch of Dew Shield. We have paused that batch and care is on +91 22 4000 7100."}), (6.5, "send", {}), (7, "approve", {}), (7.5, "publish", {})]),
        pk("cr-safe", "nikhil", "Safe for everyone", "instagram", "Dew Shield is dermatologically tested and safe for everyone. No side effects, ever.", 15,
           [(0.5, "send", {}), (1, "escalate", {"message": "Leadership asked me to reassure customers. Can I say it is safe for everyone?", "rule": "CLAIM-PROOF"}),
            (8, "resolve", {"outcome": "upheld", "note": "No. Never say safe for everyone or no side effects. Point people to care and a doctor."})]),
        pk("cr-promo", "arman", "Sale reminder", "instagram", "Stock up on Dew Shield with our cart offer. Order today.", 14, _back("Promotions are paused until the complaints are resolved. Hold this."), event=cr),
        pk("cr-case", "tanvi", "Resolved: a customer in Pune", "linkedin", "Complaint number DL-2291 from a customer in Pune is resolved, and her order ID 77421 is refunded.", 13,
           fixed("Never show a complaint number or order ID.", "A customer in Pune reported a reaction, and we refunded her order and checked in personally.", "approver"), event=cr),
        pk("cr-mail", "ira", "A note to customers", "email", "Dear customers, we have paused one batch of Dew Shield after reports of skin reactions. If you bought it, stop using it and write to care@dewlight.example for a refund. We are sorry.", 12.5, [(1, "send", {}), (4, "approve", {}), (6, "publish", {})]),
        pk("cr-recall", "lumen", "Batch recall draft", "press release", "Dewlight pauses a Dew Shield batch. Project Sandstone, our sunscreen reformulation, will follow.", 12,
           [(0.5, "send", {}), (1, "escalate", {"message": "The client asked for a holding statement naming the reformulation. Please confirm the codename is okay in a draft.", "rule": "CONF-LEAK"}),
            (6, "resolve", {"outcome": "upheld", "note": "Drafts stay in the shared doc. This codename never goes in a post."})]),
        # --- Festive Care Sale ---
        pk("fs-clean", "tanvi", "Festive Care Sale", "instagram", "Festive Care Sale: 20% off on Dew Shield until Sunday for everyone. Make sunscreen a daily habit, not a beach-day habit. #FestiveCare", 3.2, [(1, "send", {}), (4, "approve", {})], event=sl),
        pk("fs-old", "nikhil", "Monsoon prices again", "instagram", "25% off Dew Shield this week, monsoon prices are back! #FestiveCare", 3, [(1, "send", {}), (3, "autodecide", {"by": "ra"})], event=sl),
        pk("fs-wa", "sunita", "WhatsApp sale broadcast", "whatsapp", "Festive Care Sale shuru! Dew Shield par 20% off Sunday tak. Order karo dewlight.example par. #FestiveCare", 2.5, [(1, "send", {}), (3, "autodecide", {"by": "approver"})], event=sl, notes={"language": "Hinglish"}),
        pk("fs-kiara", "kiara", "My sale picks", "instagram", "The Festive Care Sale is on. Use my code from the link in my bio for more off. #FestiveCare", 2, [(1, "send", {})], event=sl),
        pk("fs-naina", "ira", "Naina's festive routine", "instagram", "Naina Verghese shares her festive skincare routine. #FestiveCare", 1.8, [(1, "send", {})], event=sl,
           images=_img("naina3", "Naina Verghese above the Dewlight logo", lambda: _ambassador((150, 100, 76), "Festive routine"))),
        pk("fs-cheap", "lumen", "Festive ad", "email", "The cheapest sunscreen in India, hurry, last chance to buy Dew Shield!", 1.4, [(1, "send", {})], event=sl),
        # --- the embargoed launches ---
        pk("mo-tease", "ira", "Something for your evenings", "instagram", "Something is coming for your evenings. Good things take time. #MeetMoonlit", 5.2, [(1, "send", {}), (4, "approve", {})], event=mo),
        pk("mo-leak", "lumen", "Moonlit press draft", "press release", "Dewlight Moonlit, a retinol night serum with 0.3% retinol, arrives in the winter under Project Moonlit.", 5,
           [(0.5, "send", {}), (1, "escalate", {"message": "Our contract lets us prepare press release drafts ahead of launch. Is the codename okay in a draft?", "rule": "CONF-LEAK"}),
            (7, "resolve", {"outcome": "upheld", "note": "Not in a post or a draft here. The codename and the strength stay in the shared brief."})], event=mo),
        pk("mo-fact", "nikhil", "Retinol serum strength", "instagram", "Our new retinol serum has 0.3% retinol. #MeetMoonlit", 4.5, [(1, "send", {}), (3, "autodecide", {"by": "ra"})], event=mo),
        pk("co-leak", "kiara", "Shoot day", "instagram", "Cannot wait for you to see what I made with Dewlight and Tara Vellore. Shoot day was unreal! Paid partnership with Dewlight. #DewlightCapsule", 3.4, [(1, "send", {}), (3, "autodecide", {"by": "approver"})], event="collab",
           images=_img("tara", "A film actor in a studio above the Dewlight logo", lambda: _ambassador((190, 140, 108), "Shoot day"))),
        pk("co-tease", "ira", "Made with a friend", "instagram", "Something we made with a friend is arriving soon. Stay tuned. #DewlightCapsule", 3.1, [(1, "send", {}), (4, "approve", {})], event="collab"),
        # --- facts, claims and copy ---
        pk("m-rating", "nikhil", "Marketplace rating line", "app store", "Rated 4.8 out of 5 by 650,000 customers.", 28,
           fixed("The listed rating is 4.5.", "Rated 4.5 out of 5 by 650,000 customers.", "ra")),
        pk("m-customers", "nikhil", "Customer count banner", "linkedin", "Join 400,000 customers on Dewlight. Daily skincare made simple.", 26,
           fixed("That is last year's figure: 650,000 customers.", "Join 650,000 customers on Dewlight. Daily skincare made simple.", "ra")),
        pk("m-cruelty", "nikhil", "Cruelty free post", "instagram", "Dewlight is 100% cruelty free and vegan, always have been.", 24,
           fixed("Cruelty free needs the certificate and the year. Vegan is not certified.", "Dewlight has been certified cruelty free since 2025. The certificate is on our website.", "ra")),
        pk("m-hair", "meenal", "Hair oil post", "instagram", "Amla Night Oil stops hair fall permanently. Lagao aur bhool jao!", 22,
           fixed("No permanent results or hair-fall claims. Describe the oil and how to use it.", "Warm a few drops of Amla Night Oil between your palms, work it through the ends and leave it overnight.", "ra"), notes={"language": "Hinglish"}),
        pk("m-pharmacy", "ira", "Dewlight at Arogyam Pharmacy", "linkedin", "Dewlight and Arogyam Pharmacy are bringing Dew Shield, Even Dew and Cloud Wash to your neighbourhood counter.", 20, CLEAN,
           images=_img("arogyam", "Dewlight and Arogyam Pharmacy logos side by side", _partner_card)),
        pk("m-listing", "tanvi", "Marketplace listing refresh", "app store", "Shop Dew Shield, Even Dew, Cloud Wash and Amla Night Oil. Read ingredients, usage notes and routines in one place. Customers rate Dewlight 4.5 out of 5.", 18, CLEAN,
           images=_img("icon", "Dewlight app icon, a white drop and sun on a teal tile", lambda: art.on_color(_app_icon(), CREAM, 60))),
        pk("m-email", "arman", "Write to me", "linkedin", "Questions about your routine? Write to me at arman.pillai@mail.example.", 13,
           fixed("Only company addresses in posts.", "Questions about your routine? Write to us at care@dewlight.example.", "approver")),
        pk("m-ai", "tanvi", "Blog illustration", "blog", "Our new guide to reading a sunscreen label has a hand-drawn look. Read it in the care centre.", 10,
           [(1, "send", {}), (3, "autodecide", {"by": "reviewer"}), (6, "back", {"note": "The illustration is AI-generated; say so in the post.", "by": "approver"}),
            (20, "fix", {"body": "Our new guide to reading a sunscreen label has a hand-drawn look. The illustration was made with AI. Read it in the care centre."}), (21, "send", {}), (26, "approve", {})],
           notes={"ai_used": True}),
        pk("m-rivalhint", "zainab", "Honest review", "youtube", "Honest review: other brands sell false hopes, Dew Shield is just honest. Paid partnership with Dewlight.", 11, _back("Hints count too. No digs at other brands.")),
        pk("m-casing", "sunita", "Naya serum", "instagram", "DewLight ka naya serum aa gaya, Even Dew. Roz raat ko lagao.", 8, fixed("Our name is Dewlight, small l.", "Dewlight ka naya serum aa gaya, Even Dew. Roz raat ko lagao.", "reviewer"), notes={"language": "Hinglish"}),
        pk("m-house", "ira", "Sun cream guide", "blog", "Our sunblock guide helps you choose the right sun cream for your skin type and your day.", 9,
           fixed("House words: sunscreen.", "Our sunscreen guide helps you choose the right sunscreen for your skin type and your day.", "approver")),
    ]


ADMIN_LOG = [
    (30, "patch_rule", {"code": "MSG-RIVALS", "patch": {
        "text": "Talk about what we make. Never mock or compare against other skincare brands, by name. A hint that "
                "'other brands sell false hopes' counts when the sentence clearly points at a rival.",
        "bad_examples": ["Unlike other brands that sell false hopes, we are honest", "The other big sunscreen feels sticky",
                         "Other brands sell false hopes"]}}),
    (25, "new_fact", {"key": "stockists", "statement": "Dew Shield, Even Dew and Cloud Wash are stocked in 3,200 Arogyam Pharmacy stores",
                      "value": 3200, "unit": "stores", "subject": "Arogyam Pharmacy stockists",
                      "source_ref": "Arogyam Pharmacy agreement, Sept 2026", "from": -25}),
]

DECISIONS = [
    ("sk-stance", 5, "MSG-FAIRNESS", "approver", "rejected", "intentional",
     "The word is the point of the post: we say we never sell fairness creams."),
    ("sk-sleep", 5, "TONE-HYPE", "approver", "rejected", "guideline_unclear",
     "Magic here is about sleep, not a product claim. Does the rule mean this?"),
    ("sk-sleep", 5, "TONE-HYPE", "reviewer", "accepted", None, None),
    ("s-glow", 5, "MSG-RIVALS", "approver", "rejected", "false_positive", "The competitor name is caught by MSG-COMPETITOR already."),
    ("s-hinglish", 5, "TERM-HOUSE", "reviewer", "rejected", "not_applicable", "Hinglish; the house words do not apply."),
    ("s-reapply", 4, "CLAIM-UNSUPPORTED", "reviewer", "rejected", "false_positive", "General advice about reapplying, not a claim about us."),
    ("m-pharmacy", 4, "CLAIM-UNSUPPORTED", "approver", "rejected", "not_applicable", "A partner announcement, not a product claim."),
    ("cr-ack", 1, "CLAIM-UNSUPPORTED", "reviewer", "rejected", "not_applicable", "Public care number, not a promotion."),
    ("fs-clean", 3, "TONE-WARM", "reviewer", "rejected", "false_positive", "Warm enough for a sale post."),
]


# --- routine work: banks per persona -------------------------------------------------------------------

CLEAN_BANK = [
    ("Morning routine", "instagram", "Cleanse, treat, moisturise and finish with sunscreen. Four small steps and your morning is done."),
    ("Sunscreen how-to", "blog", "Apply sunscreen as the last step of your morning routine. Use about two finger lengths for your face and neck, and reapply when you are outdoors for long."),
    ("Cloud Wash tip", "instagram", "Wet your face with lukewarm water, lather Cloud Wash for a slow count of twenty and rinse well. Gentle is the goal."),
    ("Serum layering", "linkedin", "Our team gets asked how to layer products. Thinnest first: face wash, serum, moisturiser, then sunscreen in the morning."),
    ("Hair oil night", "instagram", "Warm a few drops of Amla Night Oil between your palms, work it through the ends and leave it overnight. Wash in the morning."),
    ("Patch test reminder", "instagram", "New product? Do a patch test on your inner arm first. Wait a day and see how your skin feels before using it on your face."),
    ("Ingredient spotlight", "blog", "Niacinamide is a form of vitamin B3 used in skincare. In Even Dew it sits at 5%, alongside glycerin to keep skin comfortable."),
    ("Sunscreen myths", "x", "Cloudy day? UV still reaches you. Make sunscreen a daily habit, not a beach-day habit."),
    ("Customer care hours", "x", "Questions about your order or your routine? Our care team is on +91 22 4000 7100 every day. We are happy to help."),
    ("Skin check", "instagram", "Your skin changes with the seasons. Notice what feels tight or oily this week and adjust your routine, not your worries."),
    ("Sleep and skin", "instagram", "A rested face starts with a rested you. Keep your night routine short, and keep your pillowcase fresh."),
    ("Behind the formula", "linkedin", "Our formulation team tests every batch for stability and for how it feels on skin, before it reaches a shelf."),
    ("pH explained", "blog", "Skin likes a slightly acidic pH. Cloud Wash is pH 5.5, which is close to where healthy skin sits."),
    ("Ask the team", "youtube", "In this video our product team answers your questions on sunscreen and moisturiser. Chapters are listed below and a transcript is in the description."),
    ("Pharmacy shelf", "whatsapp", "Hello, Dew Shield is now on the shelf at Arogyam Pharmacy near you. Ask at the counter or order on dewlight.example."),
    ("Water resistant", "x", "Dew Shield is water resistant for up to 80 minutes in testing. Reapply after swimming or towelling off."),
    ("Community care", "instagram", "Every skin tone and every skin story is welcome here. Tell us what your routine looks like today."),
    ("Sunscreen reminder", "whatsapp", "Reminder: reapply sunscreen when you head out for lunch. Your skin will thank you tonight."),
    ("Tired eyes", "instagram", "Tired eyes? A cool compress, water and some rest make a kind start. Be gentle with yourself today."),
    ("Store listing", "app store", "Shop Dew Shield, Even Dew, Cloud Wash and Amla Night Oil. Read ingredients, usage notes and routines in one place."),
    ("Newsletter", "email", "This week in the Dewlight journal: how to read a sunscreen label, a simple evening routine and answers to your skin questions."),
    ("Storage note", "packaging", "Keep the cap closed and store Dew Shield away from direct heat. Use within twelve months of opening."),
    ("Recycle", "instagram", "Rinse, dry and recycle your empty Cloud Wash tube. We are working on refill options too."),
    ("Hindi corner", "instagram", "Subah ki routine mein sunscreen zaroor lagao. Dhoop mein jaane se pehle aur dhoop mein rehne ke baad bhi."),
    ("Dermatologist visit", "blog", "See a dermatologist when a rash does not settle, a mole changes or acne leaves marks that worry you. Skincare products support a routine; they do not replace medical care."),
    ("Reading labels", "linkedin", "A good label tells you the ingredients, how to use the product and when to stop. We print all three on every pack."),
    ("Evening wind-down", "instagram", "Wash off the day with Cloud Wash, pat your skin dry and dim the lights. Evenings are for slowing down."),
    ("Sun hours", "x", "Plan outdoor time with shade in mind and keep sunscreen in your bag. Small habits make summer easier."),
    ("Marketplace copy", "app store", "Even Dew serum, 5% niacinamide, comes with a dropper. Use two or three drops each morning."),
    ("Customer note", "instagram", "A customer told us she keeps Dew Shield in her office drawer. Where does yours live?"),
]

_TAG = "Paid partnership with Dewlight."
SLIPS = {
    "intern": [
        Slip("Sunscreen hype", "x", "OMG this sunscreen is literally magic, you NEED it!!! Hurry, last chance!!!",
             "Dew Shield is a daily sunscreen tested at SPF 40 and PA+++.", "No hype and no countdown. Say what it is and how it was tested."),
        Slip("Dark spots", "instagram", "Say goodbye to pigmentation. Even Dew treats dark spots.",
             "Even Dew is a niacinamide serum that fits into a daily routine.", "Cosmetics do not treat. Describe the serum."),
        Slip("Shiny face", "instagram", "Greasy, shiny face? Everyone is staring at it. Fix it today.",
             "Oily or dry, your skin is yours. Here is a routine that suits it.", "No shaming about skin."),
        Slip("Whitening glow", "instagram", "Whitening glow in just one wash with Cloud Wash.",
             "Cloud Wash is a gentle face wash with a pH of 5.5.", "No whitening or lightening language."),
        Slip("Emoji", "instagram", "New serum 💉💊 just dropped", "A new serum has arrived. Which step of your routine is it?", "Not our emoji."),
        Slip("Swipe", "x", "Better than Glowmatic, obviously.", "We make Dew Shield for a daily habit, not a quick fix.", "Never name another brand."),
        Slip("Shout", "instagram", "NEW SUNSCREEN IS HERE. BUY NOW.", "A new sunscreen has arrived. Make it your morning habit.", "Shouting in capitals reads badly in screen readers too."),
    ],
    "agency": [
        Slip("Brand film caption", "youtube", "We leverage best-in-class dermo-cosmetic science to operationalize radiance for all stakeholders.",
             "Our film follows three people through a week of simple skincare routines.", "Write like a friend, not a contract."),
        Slip("Detox serum", "instagram", "Detox your skin with our chemical-free serum.", "Even Dew is a niacinamide serum with 5% niacinamide.", "Detox and chemical-free are banned."),
        Slip("Fairer skin", "instagram", "Fairer skin in four weeks with Even Dew.", "Even Dew is a niacinamide serum for your evening routine.", "We never promise a lighter skin tone."),
        Slip("Permanent", "instagram", "Permanent results from the very first use.", "Use Even Dew each evening as part of a simple routine.", "No permanent results."),
        Slip("Proven", "linkedin", "Clinically proven to transform your skin. Dermatologist approved for everyone.",
             "In a dermatologist-supervised study of 62 volunteers, 84% said their skin looked more even after 8 weeks.", "Clinically proven needs the study."),
        Slip("Cheapest", "email", "The cheapest sunscreen in India, hurry!", "Dew Shield is on offer for the Festive Care Sale.", "No countdown pressure."),
        Slip("Name", "linkedin", "DewLight brings you summer.", "Dewlight brings you a daily sunscreen habit.", "Our name is Dewlight, small l."),
        Slip("Protection", "instagram", "All day protection, no need to reapply.", "Dew Shield is tested at SPF 40 and PA+++. Reapply when outdoors for long.", "Protection exactly as tested."),
    ],
    "marketer": [
        Slip("Customer count", "linkedin", "Join 400,000 customers on Dewlight.", "Join 650,000 customers on Dewlight.", "That count is last year's."),
        Slip("Rating", "instagram", "Customers rate Dewlight 4.8 out of 5.", "Customers rate Dewlight 4.5 out of 5.", "The listed rating is 4.5."),
        Slip("SPF", "instagram", "Dew Shield is SPF 50 and PA++++.", "Dew Shield is SPF 40 and PA+++.", "Quote the SPF and PA we tested."),
        Slip("Niacinamide", "x", "Even Dew packs 10% niacinamide.", "Even Dew has 5% niacinamide.", "The formulation sheet says 5%."),
        Slip("Old offer", "instagram", "25% off Dew Shield, monsoon prices are back.", "Dew Shield is part of the Festive Care Sale.", "That offer ended with the monsoon."),
        Slip("Cruelty", "instagram", "Dewlight is 100% cruelty free and vegan.", "Dewlight has been certified cruelty free since 2025.", "Cruelty free needs the certificate."),
        Slip("pH", "blog", "Cloud Wash has a pH of 7.", "Cloud Wash has a pH of 5.5.", "The sheet says 5.5."),
    ],
    "influencer": [
        Slip("No tag", "instagram", "Obsessed with Dew Shield, use my code from the link in my bio to save on your order.",
             f"{_TAG} Dew Shield sits well under my makeup. Use my code from the link in my bio.", "Start with the paid-partnership disclosure."),
        Slip("Rival", "instagram", f"Switched from Glowmatic to Dew Shield, big difference. {_TAG}",
             f"I use Dew Shield every morning. {_TAG}", "Never name another brand."),
        Slip("Before after", "instagram", f"Before and after four weeks of Even Dew. Wow. {_TAG}",
             f"Day one and week four of Even Dew. Real skin, no filter and no retouching. Individual results vary. {_TAG}", "Label before and after as real."),
        Slip("Clears", "instagram", f"Even Dew clears acne in 7 days, I promise. {_TAG}",
             f"Even Dew is a gentle niacinamide serum I add to my evening routine. {_TAG}", "Cosmetics do not clear acne."),
        Slip("Lightens", "instagram", f"Dew Shield brightens and lightens my skin tone. {_TAG}",
             f"Dew Shield feels light and does not leave a white cast on my skin. {_TAG}", "No lightening language."),
        Slip("Chemical free", "instagram", "Finally a chemical-free sunscreen. #ad", "A sunscreen that feels comfortable on my skin. #ad", "Chemical-free is banned."),
        Slip("Link text", "instagram", f"Grab the sale here: [click here](https://dewlight.example/sale) {_TAG}",
             f"Grab the sale here: [festive sale details](https://dewlight.example/sale) {_TAG}", "Link text must say where it goes."),
    ],
    "regional": [
        Slip("Hinglish chem", "instagram", "Dew Shield bilkul chemical-free hai, skin ke liye safe.",
             "Dew Shield SPF 40 aur PA+++ ke saath aata hai, roz lagao.", "Chemical-free is banned in every language."),
        Slip("Hindi cure", "instagram", "Pimples ka ilaaj: Even Dew lagao, pakka theek.", "Even Dew roz raat ko lagao, apni routine ke saath.", "No cures or treatments."),
        Slip("Fairness Hindi", "instagram", "Gora hone ka secret, ab Dew Shield ke saath.", "Dew Shield halka hai aur white cast nahi chhodta.", "No fairness language."),
        Slip("Name casing", "instagram", "DewLight ka naya serum aa gaya.", "Dewlight ka Even Dew serum ab available hai.", "Our name is Dewlight."),
    ],
    "careful": [
        Slip("Link text", "linkedin", "Sunscreen guide: [click here](https://dewlight.example/guide) for the full list.",
             "Sunscreen guide: [read the sunscreen guide](https://dewlight.example/guide).", "Link text must say where it goes."),
        Slip("House words", "blog", "Our sunblock guide helps you pick a sun cream for your skin.",
             "Our sunscreen guide helps you pick a sunscreen for your skin.", "House words: sunscreen."),
    ],
}


def build() -> Company:
    def pieces() -> list[Piece]:
        out = _stories() + routine("dewlight", CREATORS, CLEAN_BANK, SLIPS, 48, 0.3, rate=0.04)
        keys = [p.key for p in out]
        assert len(keys) == len(set(keys)), "duplicate piece keys"
        return out

    return Company(
        key="dewlight", brand=BRAND, industry="D2C skincare and personal care: sunscreens, a niacinamide serum, a face "
        "wash and a hair oil", domain="dewlight.example", days=56, team=TEAM, creators=CREATORS, rules=RULES,
        facts=FACTS, terms=TERMS, contacts=CONTACTS, assets=ARTWORK, events=EVENTS, people=PEOPLE, pieces=pieces,
        decisions=DECISIONS, stance=STANCE, admin_log=ADMIN_LOG, demo=DEMO)
