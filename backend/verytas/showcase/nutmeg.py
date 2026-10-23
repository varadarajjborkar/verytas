"""Nutmeg Lane: an Indian packaged food and drink brand (masala oats, ragi snacks, a cold coffee and a kids'
choco-malt drink fronted by Pip the squirrel). The pressure here is food regulation and children's advertising:
health and nutrient claims need a basis, "natural" and "sugar-free" are policed, allergens and the veg mark must
be on pack copy, and nothing aimed at children may push them to eat more or ask their parents for it."""

from __future__ import annotations

from verytas.showcase import art
from verytas.showcase.gen import Slip, routine
from verytas.showcase.spec import CLEAN, Company, Member, Piece, fixed

NUT, TURM, CREAM, LEAF, CHILLI, INK = (122, 66, 38), (240, 180, 40), (252, 246, 232), (60, 130, 80), (200, 70, 45), (52, 32, 20)
BRAND = "Nutmeg Lane"

# --- artwork -----------------------------------------------------------------------------------------
# Pip the squirrel is the one character; the rest is the packs, marks and patterns around it.


def _pip(body=(150, 92, 52), scarf=LEAF, size=400):
    """Pip: a squirrel with a striped tail, cream belly, round ears and a scarf with a knot, holding an acorn."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (400, 400), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    dark = tuple(max(0, c - 45) for c in body)
    belly = (244, 222, 186)
    d.ellipse((215, 30, 385, 280), fill=body + (255,))
    d.ellipse((248, 70, 352, 236), fill=tuple(min(255, c + 30) for c in body) + (255,))
    for y in (70, 112, 154):
        d.arc((232, y, 368, y + 90), 200, 340, fill=dark + (255,), width=9)
    d.ellipse((105, 190, 295, 372), fill=body + (255,))
    d.ellipse((140, 228, 262, 362), fill=belly + (255,))
    for x in (118, 214):
        d.ellipse((x, 346, x + 72, 388), fill=dark + (255,))
    d.ellipse((100, 66, 300, 232), fill=body + (255,))
    for x in (104, 244):
        d.ellipse((x, 40, x + 54, 98), fill=body + (255,))
        d.ellipse((x + 12, 54, x + 42, 88), fill=(226, 150, 140, 255))
    d.ellipse((140, 130, 262, 228), fill=belly + (255,))
    for cx in (166, 234):
        d.ellipse((cx - 20, 110, cx + 20, 152), fill="white")
        d.ellipse((cx - 9, 122, cx + 9, 146), fill=(35, 25, 20, 255))
        d.ellipse((cx - 3, 126, cx + 3, 132), fill="white")
    d.ellipse((188, 160, 214, 178), fill=(70, 40, 30, 255))
    d.arc((172, 168, 232, 204), 20, 160, fill=(70, 40, 30, 255), width=4)
    for cx in (148, 254):
        d.ellipse((cx - 14, 168, cx + 14, 188), fill=(235, 160, 150, 255))
    d.polygon([(124, 232), (278, 232), (270, 262), (132, 262)], fill=scarf + (255,))
    for x in (160, 200, 240):
        d.line([(x, 234), (x - 4, 260)], fill=(250, 214, 90, 255), width=5)
    d.ellipse((236, 246, 276, 286), fill=scarf + (255,))
    d.polygon([(246, 280), (270, 330), (250, 326), (232, 292)], fill=tuple(max(0, c - 30) for c in scarf) + (255,))
    d.ellipse((168, 292, 208, 340), fill=(196, 150, 84, 255))
    d.pieslice((164, 282, 212, 322), 180, 360, fill=(110, 70, 40, 255))
    return img if size == 400 else img.resize((size, size))


def _mark(size=400, c1=NUT, c2=(168, 104, 62), leaf=LEAF, mace=CHILLI):
    """The nutmeg seed with its red mace lacing and a two-leaf sprig: the emblem inside the logo."""
    from PIL import Image, ImageDraw

    s = size / 400
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse((50 * s, 110 * s, 350 * s, 380 * s), fill=c1 + (255,))
    d.pieslice((50 * s, 110 * s, 350 * s, 380 * s), 200, 340, fill=c2 + (255,))
    for i in range(4):
        d.arc((80 * s + i * 38 * s, 130 * s, 330 * s - i * 38 * s, 370 * s), 90, 270, fill=mace + (255,),
              width=max(3, round(7 * s)))
    d.line([(200 * s, 120 * s), (200 * s, 372 * s)], fill=(250, 232, 190, 255), width=max(2, round(6 * s)))
    d.polygon([(200 * s, 112 * s), (130 * s, 40 * s), (205 * s, 70 * s)], fill=leaf + (255,))
    d.polygon([(200 * s, 112 * s), (275 * s, 30 * s), (250 * s, 100 * s)], fill=tuple(c + 30 for c in leaf) + (255,))
    return img


def _lockup():
    return art.lockup(_mark(), "Nutmeg Lane", NUT)


def _wordmark():
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (640, 190), "white")
    d = ImageDraw.Draw(img)
    d.text((34, 26), "Nutmeg Lane", fill=NUT, font=art.font(84))
    d.arc((34, 124, 604, 176), 10, 170, fill=TURM, width=8)
    for i, x in enumerate((60, 100, 140)):
        d.ellipse((x, 150 - i * 3, x + 14, 164 - i * 3), fill=CHILLI)
    d.polygon([(560, 150), (590, 120), (598, 152)], fill=LEAF)
    return img


def _icon():
    """The Lane Club app: a steaming bowl with a spoon and three spice dots on a green tile."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, 511, 511), radius=112, fill=LEAF + (255,))
    d.pieslice((110, 200, 402, 440), 0, 180, fill=(255, 255, 255, 255))
    d.ellipse((110, 180, 402, 240), fill=(235, 245, 238, 255))
    for x in (190, 256, 322):
        d.arc((x - 30, 90, x + 30, 190), 250, 110, fill=(255, 255, 255, 255), width=9)
    d.line([(380, 150), (320, 250)], fill=TURM + (255,), width=14)
    d.ellipse((364, 120, 404, 170), fill=TURM + (255,))
    for i, x in enumerate((176, 240, 304)):
        d.ellipse((x, 330, x + 30, 360), fill=(CHILLI, TURM, NUT)[i] + (255,))
    return img


def _oats_pouch():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (420, 560), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(30, 20), (390, 20), (405, 540), (15, 540)], fill=(214, 112, 36, 255))
    d.rectangle((30, 20, 390, 54), fill=(170, 80, 22, 255))
    for x in range(40, 390, 18):
        d.line([(x, 22), (x, 50)], fill=(214, 112, 36, 255), width=3)
    art.fit_text(d, (58, 78), "Masala", 300, (255, 255, 255), start=84)
    art.fit_text(d, (58, 160), "Morning Oats", 300, (255, 240, 200), start=44)
    d.pieslice((120, 280, 300, 372), 0, 180, fill=(122, 66, 38, 255))
    d.ellipse((120, 266, 300, 296), fill=(250, 232, 190, 255))
    for x in (160, 210, 258):
        d.arc((x - 18, 212, x + 18, 276), 250, 110, fill=(255, 255, 255, 255), width=6)
    d.polygon([(310, 300), (360, 262), (350, 320)], fill=LEAF + (255,))
    d.ellipse((60, 300, 98, 334), fill=CHILLI + (255,))
    d.rounded_rectangle((38, 380, 382, 470), radius=26, fill=CREAM + (255,))
    art.fit_text(d, (62, 404), "spiced rolled oats", 296, NUT, start=34)
    d.rectangle((15, 500, 405, 540), fill=(170, 80, 22, 255))
    return img


def _oats_pouch_2024():
    """The 2024 pack: green foil, caps lettering, a starburst. Retired when the 2026 packs went on shelf."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (420, 560), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(40, 14), (380, 14), (398, 546), (22, 546)], fill=(52, 112, 70, 255))
    d.rectangle((40, 14, 380, 40), fill=(220, 220, 224, 255))
    art.fit_text(d, (70, 70), "MASALA OATS", 280, (250, 240, 210), start=52)
    d.polygon([(210, 150), (232, 196), (282, 196), (242, 224), (258, 272), (210, 242), (162, 272), (178, 224),
               (138, 196), (188, 196)], fill=(250, 200, 40, 255))
    d.ellipse((60, 330, 360, 480), outline=(250, 240, 210, 255), width=5)
    d.line([(100, 405), (320, 405)], fill=(250, 240, 210, 255), width=5)
    art.fit_text(d, (92, 352), "since 2019", 236, (250, 240, 210), start=34, bold=False)
    return img


def _ragi_box():
    """The Ragi Crunch carton in three faces, with a millet ear on the front and puffs in a round window."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (540, 540), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(40, 150), (330, 150), (330, 500), (40, 500)], fill=(176, 84, 52, 255))
    d.polygon([(330, 150), (490, 100), (490, 450), (330, 500)], fill=(124, 56, 34, 255))
    d.polygon([(40, 150), (200, 100), (490, 100), (330, 150)], fill=(206, 120, 80, 255))
    d.line([(90, 480), (118, 340)], fill=(250, 214, 90, 255), width=6)
    for i in range(6):
        d.ellipse((96 + i * 4, 340 + i * 22 - 8, 112 + i * 4, 366 + i * 22 - 8), fill=(250, 214, 90, 255))
        d.ellipse((120 - i * 4, 346 + i * 22 - 8, 136 - i * 4, 372 + i * 22 - 8), fill=(250, 214, 90, 255))
    art.fit_text(d, (56, 176), "Ragi", 250, (255, 255, 255), start=80)
    art.fit_text(d, (56, 258), "Crunch", 250, (255, 235, 200), start=60)
    d.ellipse((200, 330, 310, 440), fill=(250, 235, 200, 255))
    for x, y in ((220, 360), (250, 350), (270, 390), (232, 400), (262, 420)):
        d.ellipse((x, y, x + 20, y + 20), fill=(214, 150, 60, 255))
    d.rectangle((40, 470, 330, 500), fill=(250, 190, 60, 255))
    return img


def _choco_carton():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (420, 580), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rectangle((80, 180, 340, 560), fill=(104, 58, 38, 255))
    d.polygon([(80, 180), (210, 80), (340, 180)], fill=(150, 90, 60, 255))
    d.rectangle((190, 56, 230, 84), fill=(150, 90, 60, 255))
    d.line([(280, 20), (240, 150)], fill=(220, 60, 60, 255), width=12)
    d.polygon([(200, 330), (230, 300), (270, 330), (320, 300), (340, 340), (340, 400), (80, 400), (80, 340)],
              fill=(250, 232, 200, 255))
    art.fit_text(d, (100, 214), "Choco", 210, (255, 255, 255), start=60)
    art.fit_text(d, (100, 420), "Malt", 210, (250, 232, 200), start=72)
    for x, y in ((110, 500), (170, 520), (240, 500), (290, 524)):
        d.ellipse((x, y, x + 26, y + 16), fill=(214, 168, 90, 255))
    d.rectangle((80, 548, 340, 560), fill=(250, 190, 60, 255))
    return img


def _coffee_shot():
    """Lane Cold Coffee in a glass: layers, ice, a striped straw and beans on a pale counter."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (800, 800), (206, 228, 222))
    d = ImageDraw.Draw(img)
    d.ellipse((120, 600, 680, 740), fill=(176, 206, 198))
    d.polygon([(270, 190), (530, 190), (500, 650), (300, 650)], fill=(236, 246, 244), outline=(150, 180, 178))
    d.polygon([(278, 240), (522, 240), (508, 420), (292, 420)], fill=(244, 226, 196))
    d.polygon([(292, 420), (508, 420), (500, 640), (300, 640)], fill=(96, 56, 36))
    for i in range(6):
        d.arc((300 + i * 30, 400, 360 + i * 30, 470), 0, 180, fill=(190, 150, 110), width=5)
    for x, y in ((310, 260), (400, 290), (460, 250), (350, 340)):
        d.polygon([(x, y), (x + 56, y + 8), (x + 50, y + 62), (x - 6, y + 54)], fill=(250, 252, 252), outline=(190, 215, 215))
    for i in range(5):
        d.line([(450 + i * 6, 130 + i * 38), (418 + i * 6, 168 + i * 38)], fill=(220, 60, 60) if i % 2 else (255, 255, 255), width=16)
    for x, y in ((170, 560), (220, 620), (590, 590), (640, 540)):
        d.ellipse((x, y, x + 46, y + 30), fill=(70, 40, 26))
        d.line([(x + 6, y + 15), (x + 40, y + 15)], fill=(150, 100, 70), width=3)
    return img


def _freshbarrow():
    """A retail partner's mark: a leaf badge with a wheelbarrow. Name is set beside it in content."""
    from PIL import ImageDraw

    img = art.emblem("leaf", 300, (30, 120, 90), (20, 90, 70), (250, 220, 120))
    d = ImageDraw.Draw(img)
    d.polygon([(90, 130), (210, 130), (190, 190), (110, 190)], fill=(255, 255, 255, 255))
    d.line([(210, 140), (260, 120)], fill=(255, 255, 255, 255), width=8)
    d.ellipse((120, 188, 160, 228), fill=(250, 220, 120, 255))
    return img


def _crunchy_hills():
    """A rival's mark: a navy tile with snowy peaks and a low sun. Name is set beside it, not inside."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((10, 10, 290, 290), radius=42, fill=(28, 52, 96, 255))
    d.ellipse((170, 40, 250, 120), fill=(250, 170, 40, 255))
    d.polygon([(10, 250), (90, 100), (150, 200), (205, 140), (290, 250)], fill=(70, 120, 170, 255))
    d.polygon([(90, 100), (68, 140), (90, 130), (112, 142)], fill=(240, 245, 250, 255))
    d.polygon([(205, 140), (186, 172), (206, 164), (224, 174)], fill=(240, 245, 250, 255))
    d.rectangle((10, 230, 290, 290), fill=(240, 110, 40, 255))
    d.line([(30, 262), (80, 244), (130, 262), (180, 244), (230, 262), (270, 246)], fill=(255, 255, 255, 255), width=7)
    return img


ARTWORK = [
    {"name": "Pip", "kind": "mascot", "part": "full", "image": lambda: _pip(),
     "notes": "The kids' mascot. Always brown with a green scarf. Never redrawn or recoloured. Brand book 2026, p.9."},
    {"name": "Nutmeg Lane wordmark", "kind": "wordmark", "part": "wordmark", "wordmark": "Nutmeg Lane",
     "image": _wordmark, "notes": "Brand book 2026, p.3. Always Nutmeg Lane, capital L."},
    {"name": "Nutmeg Lane logo", "kind": "logo", "wordmark": "Nutmeg Lane", "image": lambda: _lockup().convert("RGBA"),
     "notes": "Primary lockup: nutmeg seed left of the name. Clear space of one seed width. Brand book 2026, p.4."},
    {"name": "Lane Club app icon", "kind": "icon", "part": "icon", "image": _icon,
     "notes": "The loyalty and recipe app. Never stretched into a banner."},
    {"name": "Masala Morning Oats pouch", "kind": "packaging", "image": _oats_pouch,
     "notes": "Current 2026 pack. Orange foil with the steaming bowl."},
    {"name": "Ragi Crunch carton", "kind": "packaging", "image": _ragi_box, "notes": "Current 2026 carton, 85 g."},
    {"name": "Pip's Choco-Malt carton", "kind": "packaging", "image": _choco_carton,
     "notes": "The kids' drink carton. Shown with a parent in mind, never as a reward."},
    {"name": "Masala Oats pouch 2024", "kind": "packaging", "retired": True, "image": _oats_pouch_2024,
     "notes": "Green foil pack retired in spring 2026. Still in old retailer decks and some festive creatives."},
    {"name": "Lane Cold Coffee glass", "kind": "product", "image": _coffee_shot,
     "notes": "Hero product shot. Show 'Serving suggestion' when ice cream or toppings are added."},
    {"name": "Spice trail", "kind": "pattern",
     "image": lambda: art.pattern("dots", 600, CREAM, NUT, LEAF), "notes": "Backgrounds for print and shelf strips."},
    {"name": "FreshBarrow", "kind": "partner", "wordmark": "FreshBarrow", "image": _freshbarrow,
     "notes": "Retail partner. Shown at equal height beside ours, never inside our logo's clear space."},
    {"name": "Crunchy Hills", "kind": "competitor", "wordmark": "Crunchy Hills", "image": _crunchy_hills,
     "notes": "A rival snack maker. Its mark must not appear in our content, even in a taste test."},
]


# --- the library ---------------------------------------------------------------------------------------

def _r(code, category, kind, severity, title, text, pattern=None, bad=None, good=None, ref=None):
    return {"code": code, "category": category, "kind": kind, "severity": severity, "title": title, "text": text,
            "pattern": pattern or {}, "bad_examples": bad or [], "good_examples": good or [], "source_ref": ref}


RULES = [
    _r("TONE-WARM", "tone", "semantic", "should", "Warm, homely, plain",
       "Write like someone who cooks for the family: warm, plain and specific. No hype, no shouting, no clinical words.",
       bad=["Unleash revolutionary flavour disruption", "Maximise snacking synergies"],
       good=["Stir it, wait three minutes and eat it while it is warm"], ref="Brand book 2026, p.6"),
    _r("TONE-URGENCY", "tone", "deterministic", "should", "No pressure to buy",
       "Food is not a flash sale. Say when an offer ends; never rush or guilt people into buying.",
       {"type": "banned_terms", "terms": ["hurry", "last chance", "while stocks last", "grab now", "don't miss out",
                                          "act now"]}, ref="Brand book 2026, p.7"),
    _r("TERM-HOUSE", "terminology", "deterministic", "should", "House words",
       "Use our house words. 'Healthy' is a regulated claim, so we say wholesome or describe the ingredients.",
       {"type": "preferred_terms", "map": {"healthy": "wholesome", "e-mail": "email", "junk food": "fried snacks"}},
       ref="Brand book 2026, p.8; Regulatory note R-1"),
    _r("TERM-NAME", "terminology", "deterministic", "must", "Our names, spelled our way",
       "Write Nutmeg Lane, Ragi Crunch, Masala Morning Oats and Lane Cold Coffee exactly like this.",
       {"type": "casing", "terms": ["Nutmeg Lane", "Ragi Crunch", "Masala Morning Oats", "Lane Cold Coffee"]},
       ref="Brand book 2026, p.3"),
    _r("MSG-COMPETITOR", "messaging", "deterministic", "must", "Never name another maker",
       "Do not name competing snack or drink brands, even to say we are different.",
       {"type": "banned_terms", "terms": ["Crunchy Hills", "Oatsville"]}, ref="Brand book 2026, p.11"),
    _r("MSG-COMPARE", "messaging", "semantic", "must", "No digs at other snacks",
       "Never mock or compare against other brands or snack types, by name or by hint. Disparagement is an ASCI "
       "breach. Talk about what we make.",
       bad=["Rival millet puffs mostly hollow air", "Taste test: who wins showdown",
            "Skip the fizzy cola and try our drink instead"],
       good=["Our Ragi Crunch is made with ragi flour, roasted and lightly spiced"], ref="ASCI code, Chapter I; Brand book p.11"),
    _r("MSG-CRISIS", "messaging", "semantic", "must", "Crisis weeks are plain",
       "While a recall, rumour or safety question is open: plain facts only, no jokes, no offers, no emoji.",
       bad=["lol brb rumour jokes cap", "Bumper bonanza stock up free"],
       good=["One batch is paused while testing finishes and the codes are on our care page"], ref="Crisis protocol C-2"),
    _r("KIDS-OVERUSE", "legal", "deterministic", "must", "Children are not told to eat more",
       "Content aimed at children must not encourage overconsumption or say how much to eat per day.",
       {"type": "banned_terms", "terms": ["three a day", "as many as you like", "as many as you want", "eat more",
                                          "have another", "every single day"]},
       ref="ASCI guidelines on advertising to children, 3; Regulatory note R-5"),
    _r("KIDS-PESTER", "legal", "semantic", "must", "No pester power, no superiority",
       "Never tell a child to ask or nag a parent to buy it, and never suggest children who have it are smarter, "
       "stronger or more popular than children who do not.",
       bad=["Nag mummy papa buy immediately", "Kids drinking become smarter stronger friends"],
       good=["Parents can find Pip's Choco-Malt in the dairy aisle"], ref="ASCI guidelines on advertising to children, 4 and 5"),
    _r("CLAIM-HEALTH", "claims", "deterministic", "must", "No health or cure claims",
       "Health, immunity, cure, disease and medical-approval claims need regulator approval we do not hold. Describe "
       "taste and ingredients.",
       {"type": "banned_terms", "terms": ["boosts immunity", "builds immunity", "immunity", "cures", "cure", "heals",
                                          "clinically proven", "doctor recommended", "detox", "fat burner", "weight loss"]},
       ref="Regulatory note R-3; FSSAI advertising and claims regulations"),
    _r("CLAIM-NUTRIENT", "claims", "semantic", "must", "Nutrient claims need a fact",
       "High protein, high fibre, low sugar and similar claims are used only where a published fact backs them, with "
       "the number and the serving.",
       bad=["Protein packed fibre rich low sugar", "High protein keeps kids full"],
       good=["Masala Morning Oats has 4 g of protein per serving"], ref="Regulatory note R-4; FSSAI nutrient claims"),
    _r("CLAIM-NATURAL", "claims", "deterministic", "must", "Natural and preservative claims only where true",
       "Our cold coffee carries stabilisers and added flavour, so 'natural' and 'nothing artificial' are off the table. "
       "'No added preservatives' is used only for the oats.",
       {"type": "banned_terms", "terms": ["100% natural", "completely natural", "all natural", "chemical-free",
                                          "nothing artificial", "no preservatives"]},
       ref="Regulatory note R-6; FSSAI labelling regulations"),
    _r("CLAIM-SUGAR", "claims", "deterministic", "must", "Sugar-free is a protected term",
       "Say 'no added sugar' only where the pack does, and give grams of sugar. 'Sugar-free' is reserved for products "
       "with none.", {"type": "banned_terms", "terms": ["sugar-free", "sugar free", "zero sugar", "sugarless"]},
       ref="Regulatory note R-7"),
    _r("CLAIM-RANK", "claims", "deterministic", "must", "No self-declared rankings",
       "We are not the number one, the best or the tastiest without a dated, published survey.",
       {"type": "banned_terms", "terms": ["number one", "#1", "no.1", "tastiest in india", "india's tastiest", "best in india",
                                         "india's favourite"]}, ref="Legal note L-19; ASCI superlatives"),
    _r("LEGAL-ALLERGEN", "legal", "semantic", "must", "Allergens on every pack and listing",
       "Packaging copy, product pages and recipe cards carry the allergen line that starts with Contains, and a "
       "'may contain traces' line where the kitchen shares equipment.",
       bad=["Puffed millet net quantity silent allergens"],
       good=["Contains: oats, wheat. May contain traces of peanuts and tree nuts"], ref="Regulatory note R-2; FSSAI labelling"),
    _r("LEGAL-LABEL", "legal", "semantic", "must", "Veg mark, serving suggestion, front-of-pack facts",
       "Pack and shelf copy show the green veg mark, say 'Serving suggestion' where a photo shows more than is in the "
       "pack, and keep energy and sugar per serving on the front.",
       bad=["Egg bites in rich gravy, mark missing", "Extra toppings pictured, caption line missing"],
       good=["Veg. Serving suggestion. Energy and sugar per serving on the front"], ref="Regulatory note R-8"),
    _r("LEGAL-OFFER", "legal", "semantic", "should", "Offers say what, for whom and until when",
       "A discount names the product, who gets it and the last day. Gifting boxes state their contents.",
       bad=["Enormous discounts everywhere", "Complimentary present limited"],
       good=["Fifteen percent off festive gift boxes until the end of the festive fest"], ref="Legal note L-25"),
    _r("VIS-PALETTE", "visual", "deterministic", "should", "Brand colours only",
       "Posters and cards use the Nutmeg Lane palette: nutmeg brown, turmeric, cream, leaf green and chilli.",
       {"type": "palette", "colors": ["#7A4226", "#F0B428", "#FCF6E8", "#3C8250", "#C8462D", "#34200E", "#D67024"],
        "max_delta_e": 20, "min_share": 0.15}, ref="Brand book 2026, p.15"),
    _r("VIS-LOGO-CLEAR", "visual", "semantic", "should", "Give the logo and Pip room",
       "Keep clear space of one seed width around the logo; never put it on a busy photo, beside a rival's mark, or "
       "change Pip's colours.", bad=["Emblem cluttered shelf image"],
       good=["Logo on a plain cream field with clear space"], ref="Brand book 2026, p.4 and p.9"),
    _r("A11Y-ALT-PACK", "accessibility", "deterministic", "should", "Say which pack is in the picture",
       "Alt text names the product and what is shown, not just 'photo' or 'pack'.",
       {"type": "alt_text", "min_length": 20}, ref="Brand book 2026, p.18"),
]

# The offline judge scores a text by its word overlap with a rule's examples, so every semantic rule also
# carries ordinary, compliant copy; the hosted judge reads the rule itself and ignores this.
_ORDINARY = ["A warm bowl on a busy morning and a recipe card for tonight",
             "Crunchy ragi snacks for the school bag and the long train ride",
             "This week in the Nutmeg Lane kitchen: new recipes, small batches and an honest label"]
for _rule in RULES:
    if _rule["kind"] == "semantic":
        _rule["good_examples"] = [*_rule["good_examples"], *_ORDINARY]

FACTS = [
    {"key": "stores_old", "statement": "Nutmeg Lane is sold in 2,400 stores", "value": 2400, "unit": "stores",
     "subject": "stores", "source_ref": "Sales report, March 2025", "from": -400},
    {"key": "stores", "statement": "Nutmeg Lane is sold in 3,100 stores", "value": 3100, "unit": "stores",
     "subject": "stores", "source_ref": "Sales report, June 2026", "from": -140, "supersedes": "stores_old"},
    {"key": "ragi_old", "statement": "Ragi Crunch is sold in a 100 g pack", "value": 100, "unit": "g",
     "subject": "Ragi Crunch pack size", "source_ref": "Product sheet, 2025", "from": -420},
    {"key": "ragi", "statement": "Ragi Crunch is sold in an 85 g pack", "value": 85, "unit": "g",
     "subject": "Ragi Crunch pack size", "source_ref": "Product sheet, July 2026", "from": -95, "supersedes": "ragi_old"},
    {"statement": "Masala Morning Oats has 4 g of protein per serving", "value": 4, "unit": "g",
     "subject": "Masala Morning Oats protein per serving", "source_ref": "Lab report LR-2026-18; pack back panel",
     "from": -200},
    {"key": "sugar_old", "statement": "Lane Cold Coffee has 9 g of sugar per serving", "value": 9, "unit": "g",
     "subject": "Lane Cold Coffee sugar per serving", "source_ref": "Pack back panel, 2025", "from": -420},
    {"key": "sugar", "statement": "Lane Cold Coffee has 6.5 g of sugar per serving", "value": 6.5, "unit": "g",
     "subject": "Lane Cold Coffee sugar per serving", "source_ref": "Pack back panel, new recipe, July 2026",
     "from": -90, "supersedes": "sugar_old"},
    {"key": "price_old", "statement": "Pip's Choco-Malt costs 135 rupees", "value": 135, "unit": "rupees",
     "subject": "Pip's Choco-Malt price", "source_ref": "Price list, 2025", "from": -420},
    {"key": "price", "statement": "Pip's Choco-Malt costs 149 rupees", "value": 149, "unit": "rupees",
     "subject": "Pip's Choco-Malt price", "source_ref": "Price list, Aug 2026", "from": -60, "supersedes": "price_old"},
    {"statement": "Nutmeg Lane products are made in 3 FSSAI-licensed kitchens", "value": 3, "unit": "kitchens",
     "subject": "licensed kitchens", "source_ref": "FSSAI licence register, 2026", "from": -300},
    {"statement": "Festive gift boxes of 2025 were 20% off", "value": 20, "unit": "%",
     "subject": "festive gift box discount", "source_ref": "Diwali 2025 brief", "from": -380, "to": -330},
    {"statement": "Festive gift boxes are 15% off during the Diwali gifting fest", "value": 15, "unit": "%",
     "subject": "festive gift box discount", "source_ref": "Diwali 2026 brief", "from": -3, "to": 14},
    {"statement": "Masala Morning Oats has no added preservatives", "subject": "Masala Morning Oats preservatives",
     "source_ref": "Ingredient list, pack back panel", "from": -200},
    {"statement": "Smoky Tamarind Ragi Crunch launches in 6 states", "value": 6, "unit": "states",
     "subject": "Smoky Tamarind launch states", "source_ref": "Launch brief (embargoed)", "from": 25},
]

TERMS = [
    {"term": "Smoky Tamarind", "note": "Unreleased Ragi Crunch flavour, launches at the end of the month", "embargo": 25},
    {"term": "Project Barrow", "note": "Exclusive range talks with a retail chain. Never public until both sides announce."},
    {"term": "Pip Junior", "note": "Toddler range under development. Internal name only", "embargo": 70},
    {"term": "Jaggery Latte", "note": "Public since the launch release", "embargo": -18},
]

CONTACTS = [
    {"kind": "phone", "value": "+91 80 4561 7700", "label": "Consumer care", "source_ref": "nutmeglane.example/care"},
    {"kind": "phone", "value": "+91 80 4561 7711", "label": "WhatsApp broadcast line", "source_ref": "Consumer care charter"},
    {"kind": "phone", "value": "+91 80 4561 7722", "label": "Press desk", "source_ref": "nutmeglane.example/press"},
    {"kind": "email", "value": "*@nutmeglane.example", "label": "Company domain", "source_ref": "IT policy"},
    {"kind": "url", "value": "nutmeglane.example", "label": "Website", "source_ref": "Brand book 2026, p.2"},
    {"kind": "url", "value": "care.nutmeglane.example", "label": "Care and batch codes page", "source_ref": "Crisis protocol C-2"},
    {"kind": "handle", "value": "@nutmeglane", "label": "Social handle", "source_ref": "Brand book 2026, p.2"},
    {"kind": "handle", "value": "@pipandfriends", "label": "Pip's kids channel", "source_ref": "Brand book 2026, p.9"},
]

EVENTS = [
    {"key": "school", "created": 55, "name": "Back-to-school lunchboxes", "kind": "campaign", "start": -52, "end": -38,
     "hashtags": ["#LunchboxLane"], "avoid_terms": ["boosts immunity", "smarter"],
     "guidance": "Speak to parents about snacks and tiffin ideas. No claims about marks, strength or immunity, and "
     "nothing that tells children to ask for it.", "summary": "Lunchbox ideas with Ragi Crunch and Pip's Choco-Malt."},
    {"key": "recall", "created": 27, "name": "Cold coffee batch hold, rumour week", "kind": "crisis", "start": -26,
     "end": -21, "blackout": True,
     "guidance": "One batch of Lane Cold Coffee is paused for testing while a rumour spreads. Plain facts and the care "
     "page only: no jokes, no offers, no emoji.", "summary": "A batch is on hold; a contamination rumour is trending."},
    {"key": "kabaddi", "created": 20, "name": "Kabaddi Nights drinks partner", "kind": "partnership", "start": -18,
     "end": 6, "hashtags": ["#LaneKabaddiNights"],
     "guidance": "We are the drinks partner of a city league. Never link Pip's Choco-Malt to athletes' strength or wins.",
     "summary": "Sponsorship of an eight-team kabaddi league."},
    {"key": "wfd", "created": 12, "name": "World Food Day", "kind": "campaign", "start": -7, "end": -6,
     "hashtags": ["#WorldFoodDay"], "guidance": "Talk about where food comes from. No donation or impact figures "
     "without a source, no sugar or nutrition claims.", "summary": "Stories about farmers and kitchens."},
    {"key": "diwali", "created": 6, "name": "Diwali gifting fest", "kind": "sale", "start": -4, "end": 16,
     "hashtags": ["#NutmegLaneDiwali"], "avoid_terms": ["cheapest", "lowest price ever"],
     "guidance": "Lead with the box and what is in it; the discount comes second. Current packs only: the 2024 "
     "pouch is retired.", "summary": "Gift boxes with 15% off through the festive fortnight."},
    {"key": "launch", "created": 3, "name": "Smoky Tamarind Ragi Crunch launch", "kind": "launch", "start": 25,
     "hashtags": ["#CrunchierTomorrow"], "avoid_terms": ["Smoky Tamarind"],
     "guidance": "Until launch day, tease the feeling, not the flavour: no name, no pack, no date.",
     "summary": "A new Ragi Crunch flavour, embargoed."},
]

PEOPLE = [
    {"name": "Rudra Sanghavi", "kind": "celebrity", "aliases": ["Rudra S"], "channels": ["instagram", "youtube"],
     "events": ["kabaddi"], "from": -20, "to": 60, "notes": "Kabaddi captain. League sponsorship content only; "
     "no health or strength claims in his name (contract N-31)."},
    {"name": "Dr. Anjali Pillai", "kind": "ambassador", "aliases": ["Anjali Pillai"], "channels": [], "from": -420,
     "to": -35, "notes": "Dietitian ambassador. Agreement ended; renewal under discussion."},
    {"name": "Chef Meher Irani", "kind": "creator", "aliases": ["Meher Irani"], "channels": ["instagram", "youtube"],
     "from": -200, "to": 200, "notes": "Recipe creator. Written consent for her photos and recipes."},
]

TEAM = [
    Member("admin", "radhika@nutmeglane.example", "Radhika Menon", "brand_admin", title="Head of brand",
           blurb="Owns the brand library: rules, facts, artwork, events. Sees every screen."),
    Member("approver", "sameer@nutmeglane.example", "Sameer Kulkarni", "approver", title="Marketing manager",
           blurb="Works the review queue: approves, sends back, rules on escalations."),
    Member("reviewer", "meghna@nutmeglane.example", "Meghna Desai", "reviewer"),
    Member("auditor", "gaurav@nutmeglane.example", "Gaurav Nair", "auditor"),
    Member("regulatory", "shabnam@nutmeglane.example", "Dr. Shabnam Rizvi", "reviewer"),
]
CREATORS = [
    Member("anita", "anita@nutmeglane.example", "Anita Gowda", "creator", "careful"),
    Member("ishaan", "ishaan@nutmeglane.example", "Ishaan Verma", "creator", "intern"),
    Member("jay", "jay@nutmeglane.example", "Jay Patel", "creator", "marketer"),
    Member("kavya", "lavanya@nutmeglane.example", "Lavanya Raman", "creator", "regional"),
    Member("mehul", "mehul@nutmeglane.example", "Mehul Joshi", "creator", "regional"),
    Member("rhea", "pallavi@foodcreators.example", "Pallavi Kulkarni (food creator)", "creator", "influencer"),
    Member("brightside", "hello@brightsidestudio.example", "Brightside Studio (agency)", "creator", "agency"),
]
DEMO = [
    ("approver", "approver", "manager", "Marketing manager",
     "Works the review queue: approves, sends back, rules on escalations."),
    ("admin", "admin", "manager", "Head of brand", "Owns the brand library: rules, facts, artwork, events."),
    ("legal", "regulatory", "manager", "Regulatory and food safety",
     "Rules on health, nutrient and allergen findings; sees every claim twice."),
    ("c1", "ishaan", "creator", "Content creator", "Instagram and X. His copy drifts into claims when he is in a hurry."),
    ("c3", "kavya", "creator", "Regional creator", "Writes in Tamil, Hindi and English. Has a piece sent back."),
    ("c6", "brightside", "creator", "Agency", "An outside agency writing festive and sponsorship campaigns."),
]

# Meghna is strict on children's rules, Sameer practical, Dr. Rizvi cares only about claims and labelling.
_UNCLEAR = ("guideline_unclear", "Does the rule mean this? It reads like a description, not a promise.")
STANCE = {
    "reviewer": {"KIDS-OVERUSE": (1.0, []), "KIDS-PESTER": (0.9, [_UNCLEAR]), "TERM-HOUSE": (0.95, []),
                 "TONE-SHIFT": (0.85, [("false_positive", "Warm enough for this channel.")]),
                 "CLAIM-NUTRIENT": (0.4, [("false_positive", "A recipe tip, not a claim about our product."), _UNCLEAR]),
                 "*": (0.8, [("not_applicable", "Does not apply to this piece.")])},
    "approver": {"TONE-SHIFT": (0.65, [("intentional", "Light-hearted on purpose for this post.")]),
                 "CLAIM-NUTRIENT": (0.25, [("false_positive", "General statement, not a figure."), _UNCLEAR]),
                 "MSG-COMPARE": (0.45, [_UNCLEAR, ("false_positive", "Names nobody.")]),
                 "A11Y-READ": (0.3, [("not_applicable", "Hinglish; the grade does not mean anything.")]),
                 "*": (0.7, [("false_positive", "Reads fine to me.")])},
    "regulatory": {"CLAIM-HEALTH": (1.0, []), "CLAIM-NUTRIENT": (0.95, []), "CLAIM-NATURAL": (1.0, []),
                   "CLAIM-SUGAR": (1.0, []), "CLAIM-OUTDATED": (1.0, []), "CLAIM-CONTRADICTED": (1.0, []),
                   "LEGAL-ALLERGEN": (1.0, []), "LEGAL-LABEL": (1.0, []), "CLAIM-UNSUPPORTED": (0.9, []),
                   "TONE-SHIFT": (0.3, [("not_applicable", "Not a regulatory matter.")]),
                   "*": (0.6, [("not_applicable", "Outside regulatory's remit.")])},
}


# --- images -----------------------------------------------------------------------------------------------

def _img(key, alt, img):
    return lambda: [art.image_attachment(key, alt, img() if callable(img) else img)]


def _poster(headline, sub="", logo="ok", picture=None, size=(1080, 1080)):
    """A cream campaign card. `logo` says how the mark was used: as registered, squeezed into a slot, or recoloured."""
    img = art.card(size, CREAM, headline, sub, fg=INK, art=picture, art_w=380)
    lk = _lockup()
    if logo == "ok":
        art.paste(img, lk, (74, 880), width=420)
    elif logo == "stretched":
        art.paste(img, lk, (74, 880), width=560, height=round(560 * lk.height / lk.width / 1.27))
    elif logo == "recolour":
        art.paste(img, art.recolour(lk, "gbr"), (74, 880), width=420)
    return img


def _pack_shot(logo="ok"):
    img = art.canvas((1080, 1080), CREAM)
    art.paste(img, _oats_pouch(), (330, 120), width=420)
    lk = _lockup()
    if logo == "stretched":
        art.paste(img, lk, (74, 840), width=560, height=round(560 * lk.height / lk.width / 1.3))
    else:
        art.paste(img, lk, (74, 840), width=420)
    return img


def _taste_test():
    from PIL import ImageDraw

    img = art.canvas((1080, 1080), CREAM)
    d = ImageDraw.Draw(img)
    d.text((70, 80), "Who wins the crunch?", fill=INK, font=art.font(64))
    art.paste(img, _ragi_box(), (40, 330), width=420)
    art.paste(img, _crunchy_hills(), (680, 380), width=300)
    d.text((500, 520), "vs", fill=INK, font=art.font(52))
    return img


def _sponsor_strip(with_rival: bool):
    from PIL import ImageDraw

    img = art.canvas((1200, 420), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((40, 24), "Kabaddi Nights, drinks partner", fill=INK, font=art.font(40))
    art.paste(img, _lockup(), (40, 150), width=420)
    art.paste(img, _freshbarrow(), (620, 130), width=220)
    if with_rival:
        art.paste(img, _crunchy_hills(), (900, 130), width=220)
    return img


def _ambassador(caption):
    img = art.portrait((1080, 1080), (205, 160, 130), CREAM, LEAF, caption)
    art.paste(img, _lockup(), (60, 40), width=300)
    return img


# --- the eight weeks, scripted -----------------------------------------------------------------------------

def _back(note, by="approver"):
    return [(1, "send", {}), (3, "autodecide", {"by": "reviewer"}), (6, "back", {"note": note, "by": by})]


def _alt(product):
    return f"{product} shown on a cream card with the Nutmeg Lane logo at the bottom"


def _stories() -> list[Piece]:
    sc, rc, kb, wf, dw, ln = "school", "recall", "kabaddi", "wfd", "diwali", "launch"
    pk = Piece
    return [
        # Back to school
        pk("s-lunch", "anita", "Lunchbox ideas", "instagram", "Five minutes, one bowl, a lunchbox that comes back empty. Ragi Crunch makes a good mid-morning snack for the school bag. #LunchboxLane", 51, CLEAN, event=sc),
        pk("s-immune", "ishaan", "Back to school with Pip", "instagram", "Back to school means Pip's Choco-Malt every morning! It boosts immunity so your little one never misses a day. #LunchboxLane", 50,
           fixed("Immunity claims are not approved. Talk about the taste and the routine.", "Back to school means a glass of Pip's Choco-Malt with breakfast. Made with malted barley and cocoa, a treat your child will look forward to. #LunchboxLane", "regulatory"), event=sc),
        pk("s-protein", "jay", "Oats for busy mornings", "instagram", "Masala Morning Oats is high protein, so school mornings stay full of energy. #LunchboxLane", 49,
           fixed("No fact backs 'high protein'. Use the lab figure with its serving.", "A warm bowl of Masala Morning Oats has 4 g of protein per serving, ready in three minutes. #LunchboxLane", "regulatory"), event=sc),
        pk("s-three", "brightside", "Pip's breakfast reel", "instagram", "Pip says: one Choco-Malt for breakfast, one after school, one at bedtime. Have three a day! #LunchboxLane", 48,
           [(0.3, "send", {}), (0.5, "escalate", {"message": "The client brief used this exact line for the reel. Please confirm it can run.", "rule": "KIDS-OVERUSE"}), (7, "resolve", {"outcome": "upheld", "note": "Not allowed: we never tell children how much to have. Show Pip's morning routine instead."}), (9, "back", {"note": "Remove the daily count; see the escalation.", "by": "approver"}), (20, "fix", {"body": "Pip's morning: wash hands, pack the bag, and a glass of Pip's Choco-Malt with breakfast. #LunchboxLane"}), (21, "send", {}), (28, "approve", {}), (50, "publish", {})], event=sc),
        pk("s-tamil", "kavya", "பள்ளி மீண்டும் தொடங்குகிறது", "email", "பள்ளி மீண்டும் தொடங்குகிறது. Ragi Crunch புதிய பேக்கில் கிடைக்கிறது. E-mail மூலம் ஆர்டர் செய்யுங்கள். #LunchboxLane", 47,
           fixed("House word: email, even in Tamil copy.", "பள்ளி மீண்டும் தொடங்குகிறது. Ragi Crunch புதிய பேக்கில் கிடைக்கிறது. Email மூலம் ஆர்டர் செய்யுங்கள். #LunchboxLane", "reviewer"), event=sc, notes={"language": "Tamil"}),
        pk("s-hindi", "mehul", "स्कूल का पहला दिन", "instagram", "स्कूल का पहला दिन, लंच बॉक्स में रागी क्रंच और एक मुस्कान। #LunchboxLane", 46, CLEAN, event=sc, notes={"language": "Hindi", "intent": "A warm first-day message for parents."}),
        pk("s-taste", "rhea", "Taste test", "instagram", "I put Ragi Crunch next to the other big millet snack. Swipe to see who wins! #LunchboxLane", 45, _back("A rival's logo in a taste-test graphic is a no. Show our own pack."), event=sc,
           images=_img("taste", "Taste test graphic with a Ragi Crunch carton and a rival's logo", _taste_test)),
        pk("s-stretch", "brightside", "Pip's school bag poster", "instagram", "Pip is packing a school bag. What goes in yours? #LunchboxLane", 44,
           fixed("The logo is squeezed. Use the registered lockup at its own proportions.", "Pip is packing a school bag. What goes in yours? Logo corrected. #LunchboxLane", "reviewer"), event=sc,
           images=_img("bag", "Pip the squirrel beside a school bag with the Nutmeg Lane logo", lambda: _poster("What is in your bag?", "Pip is packing", "stretched", _pip())),
           fix_images=_img("bag", "Pip the squirrel beside a school bag with the Nutmeg Lane logo", lambda: _poster("What is in your bag?", "Pip is packing", "ok", _pip()))),
        pk("s-kitchens", "anita", "Where it is made", "linkedin", "Every pack of Nutmeg Lane comes from one of our 3 FSSAI-licensed kitchens, with a batch code you can trace.", 43, CLEAN),
        pk("s-natural", "ishaan", "Cold coffee is 100% natural", "instagram", "Lane Cold Coffee is 100% natural, nothing artificial, no preservatives. Chill it and pour. #LunchboxLane", 42,
           fixed("Our cold coffee has stabilisers and added flavour, so 'natural' is off. Describe the ingredients.", "Lane Cold Coffee is made with brewed coffee, milk and a little sugar: 6.5 g of sugar per serving. Chill it, shake it, pour it. #LunchboxLane", "regulatory"), event=sc),
        pk("s-healthy", "mehul", "Healthy Tiffin Challenge", "instagram", "Join the Healthy Tiffin Challenge at your school: send us your child's lunchbox idea. #LunchboxLane", 41,
           [(1, "send", {}), (2, "dispute", {"rule": "TERM-HOUSE", "claim": "Healthy Tiffin Challenge is the name of the schools association's programme, a proper noun and not our claim about food."}), (4, "autodecide", {"by": "approver"}), (9, "approve", {"note": "Programme name checked with the association; fine to publish."}), (30, "publish", {})], event=sc),
        # World Food Day
        pk("w-ask", "anita", "Where does lunch come from", "instagram", "World Food Day is a good day to ask where your lunch comes from. We will share the story of our ragi this week. #WorldFoodDay", 7, CLEAN, event=wf),
        pk("w-meals", "jay", "World Food Day giving", "linkedin", "This World Food Day we helped serve 1 lakh meals with our kitchen partners. #WorldFoodDay", 7,
           fixed("No fact backs the meal count. Thank people instead of quoting a number.", "Thank you for sharing your lunchboxes with us this World Food Day. #WorldFoodDay", "regulatory"), event=wf),
        pk("w-sugar", "rhea", "World Food Day sip", "instagram", "World Food Day tip: skip the sugar-free cola and try Lane Cold Coffee over ice. #WorldFoodDay", 6.8,
           fixed("'Sugar-free' is protected and this is also a dig at cola. Give the sugar grams for ours.", "World Food Day tip: Lane Cold Coffee over ice, with 6.5 g of sugar per serving. #WorldFoodDay", "regulatory"), event=wf),
        # Cold coffee batch hold
        pk("r-ack", "anita", "A batch is on hold", "x", "One batch of Lane Cold Coffee is paused while testing finishes. The codes are on care.nutmeglane.example. If you have one at home, please call +91 80 4561 7700 and we will arrange a replacement.", 25.8, [(0.3, "send", {}), (0.8, "approve", {}), (1.1, "publish", {})], event=rc),
        pk("r-joke", "ishaan", "Coffee rumours", "x", "lol rumours say our cold coffee is spicy now, brb 🌶️ no cap it is just coffee", 25.5,
           [(0.5, "send", {}), (1.5, "autodecide", {"by": "approver"}), (2, "back", {"note": "No jokes while a batch is on hold. State the facts and point to the care page.", "by": "approver"}), (6, "fix", {"body": "One batch is paused while testing finishes. Please check the codes on care.nutmeglane.example."}), (6.5, "send", {}), (7, "approve", {}), (7.5, "publish", {})], event=rc),
        pk("r-promo", "brightside", "Cold coffee offer", "instagram", "Buy two get one free on Lane Cold Coffee this week! Stock up now.", 24.8,
           [(1, "send", {}), (3, "back", {"note": "Offers are paused during the batch hold. Hold this until the event ends.", "by": "approver"})], event=rc),
        pk("r-count", "jay", "How many batches", "x", "Only 1 batch out of 400 was affected, so the rest of your cold coffee is fine.", 24.4,
           [(1, "send", {}), (3, "autodecide", {"by": "regulatory"}), (4, "comment", {"by": "regulatory", "body": "We cannot quote a ratio or tell people the rest is fine while testing is open. Please say only what is paused."}), (6, "back", {"note": "See Dr. Qureshi's comment: say what is paused and where the codes are.", "by": "approver"}), (20, "fix", {"body": "The paused batch is on hold while testing finishes. Codes are on care.nutmeglane.example."}), (21, "send", {}), (26, "approve", {}), (40, "publish", {})], event=rc),
        pk("r-hindi", "mehul", "कोल्ड कॉफी बैच की जानकारी", "whatsapp", "नमस्ते, एक बैच जांच के लिए रोका गया है। कोड देखने के लिए मुझे 00000 12345 पर कॉल करें।", 24,
           fixed("Only the company's numbers in broadcasts.", "नमस्ते, एक बैच जांच के लिए रोका गया है। कोड देखने के लिए +91 80 4561 7711 पर कॉल करें।", "approver"), event=rc, notes={"language": "Hindi"}),
        pk("r-press", "anita", "Statement on the cold coffee batch", "press release", "Nutmeg Lane has paused one batch of Lane Cold Coffee while an independent lab completes tests. Batch codes and a replacement process are on care.nutmeglane.example.", 23.5, CLEAN, event=rc),
        pk("r-ask", "jay", "Reply time to families", "linkedin", "Our care team replies to every message about the batch within 24 hours.", 22.5,
           [(0.5, "send", {}), (1, "escalate", {"message": "This is in the consumer care charter but not in the fact library. Can the brand team add it, or should I soften the line?", "rule": "CLAIM-UNSUPPORTED"})], event=rc),
        # Kabaddi Nights
        pk("k-intro", "anita", "Our partner league", "instagram", "We are the drinks partner of Kabaddi Nights this season. Come cheer, bring the family and take home a recipe card. #LaneKabaddiNights", 17, CLEAN, event=kb),
        pk("k-rudra", "rhea", "Rudra and Pip's Choco-Malt", "x", "Rudra Sanghavi drinks Pip's Choco-Malt after practice and gets stronger every day! #LaneKabaddiNights", 15,
           [(2, "send", {}), (5, "autodecide", {"by": "regulatory"}), (8, "back", {"note": "Rudra's agreement covers Instagram and YouTube only, and we make no strength claims for a children's drink.", "by": "approver"})], event=kb),
        pk("k-strip", "brightside", "Match-night sponsor strip", "instagram", "Tonight's sponsors, with thanks. #LaneKabaddiNights", 14,
           fixed("A rival's mark sits in the sponsor strip. Ask the league for a version without it.", "Tonight's sponsors, with thanks. Strip updated. #LaneKabaddiNights", "approver"), event=kb,
           images=_img("strip", "Sponsor strip with the Nutmeg Lane logo, a retail partner and a rival snack maker", lambda: _sponsor_strip(True)),
           fix_images=_img("strip", "Sponsor strip with the Nutmeg Lane logo and a retail partner", lambda: _sponsor_strip(False))),
        pk("k-yt", "jay", "Kabaddi Nights highlights", "youtube", "Highlights from this week's Kabaddi Nights match. Sponsored by Nutmeg Lane. Chapters are listed below and a transcript is on our care page. #LaneKabaddiNights", 12, CLEAN, event=kb),
        pk("k-win", "ishaan", "Win like the champs", "instagram", "Drink Pip's Choco-Malt and you will win every match like the champs! #LaneKabaddiNights", 11,
           fixed("No link between the drink and winning, and nothing that tells children they will beat others.", "Cheer loud tonight with the family. Pip's Choco-Malt is on sale at the stall. #LaneKabaddiNights", "reviewer"), event=kb),
        pk("k-anjali", "jay", "A dietitian's word", "instagram", "Dr. Anjali Pillai says our oats are clinically proven to be a smart breakfast for the whole family. #LaneKabaddiNights", 10,
           [(0.5, "send", {}), (1, "escalate", {"message": "Dr. Pillai's renewal is agreed verbally and the paperwork is with legal. Can we run her name meanwhile?", "rule": "CLAIM-HEALTH"}), (9, "resolve", {"outcome": "upheld", "note": "Not until the signed renewal is on file, and never with a clinical claim. Use the oats recipe card without her name."})], event=kb),
        # Diwali gifting
        pk("d-box", "anita", "Diwali gift box", "instagram", "Our Diwali gift box brings Ragi Crunch, Masala Morning Oats and Pip's Choco-Malt in one box. 15% off festive gift boxes during the gifting fest. #NutmegLaneDiwali", 3.2, [(1, "send", {}), (2, "comment", {"by": "reviewer", "body": "Lovely. Can the alt text name both packs so it reads well aloud?"}), (4, "approve", {})], event=dw,
           images=_img("box", "Gift box with Ragi Crunch and Masala Morning Oats packs beside the Nutmeg Lane logo", lambda: _poster("Gifts from our kitchen", "Ragi Crunch and Masala Morning Oats", "ok", _ragi_box()))),
        pk("d-old", "jay", "Diwali oats poster", "instagram", "Diwali gift box: 20% off, just like last year! Masala Morning Oats in the box. #NutmegLaneDiwali", 2.1, [(1, "send", {}), (3, "autodecide", {"by": "regulatory"})], event=dw,
           images=_img("old", "Festive poster showing the green Masala Oats pouch from 2024 and the Nutmeg Lane logo", lambda: _poster("Light a lamp, share a bowl", "Diwali gift box", "ok", _oats_pouch_2024()))),
        pk("d-pip", "ishaan", "Pip's festive look", "instagram", "Pip is celebrating Diwali with you. Share a snack with a neighbour. #NutmegLaneDiwali", 1.5, [(1, "send", {})], event=dw,
           images=_img("pipfest", "Pip the squirrel in festive purple and saffron above the words Share a snack", lambda: _poster("Share a snack", "Diwali week", "ok", _pip(body=(220, 130, 60), scarf=(150, 60, 160))))),
        pk("d-pack", "brightside", "Oats pack shot", "instagram", "Masala Morning Oats, now in our gift box. #NutmegLaneDiwali", 1.1, [(1, "send", {})], event=dw,
           images=_img("pack", "Masala Morning Oats pouch on a cream card with the Nutmeg Lane logo", lambda: _pack_shot("stretched"))),
        pk("d-tamil", "kavya", "தீபாவளி வாழ்த்துகள்", "instagram", "தீபாவளி வாழ்த்துகள்! இந்த விழாவில் குடும்பத்துடன் ஒரு சூடான கிண்ணம் பகிர்ந்து கொள்ளுங்கள். #NutmegLaneDiwali", 2.6, [(1, "send", {}), (4, "approve", {})], event=dw, notes={"language": "Tamil"}),
        pk("d-cheap", "rhea", "Gift box deal", "instagram", "The cheapest gift box in India, grab now while stocks last! #NutmegLaneDiwali", 0.8, [(1, "send", {})], event=dw),
        # Launch under embargo
        pk("l-tease", "anita", "Something crunchier", "instagram", "Something crunchier is on its way. Guess the flavour. #CrunchierTomorrow", 2.8, [(1, "send", {}), (3, "approve", {})], event=ln),
        pk("l-leak", "rhea", "Flavour sneak peek", "instagram", "Psst, Smoky Tamarind Ragi Crunch is coming soon and I have tasted it. #CrunchierTomorrow", 2.2,
           [(1, "send", {}), (2, "escalate", {"message": "The sales team already shared the flavour with retailers, so I assumed it was public. Can I mention it?", "rule": "CONF-LEAK"}), (6, "resolve", {"outcome": "upheld", "note": "Retailer briefings are not public. The name stays embargoed until launch day."})], event=ln),
        pk("l-barrow", "brightside", "Retail exclusive", "linkedin", "Excited about Project Barrow, our exclusive range with a retail partner. Details soon.", 4,
           [(1, "send", {}), (3, "autodecide", {"by": "regulatory"}), (6, "back", {"note": "Project Barrow is confidential until both sides announce.", "by": "approver"}), (20, "withdraw", {})]),
        pk("l-press", "anita", "Jaggery Latte release", "press release", "Nutmeg Lane introduces Jaggery Latte, a ready-to-drink latte sweetened with jaggery. It reaches stores this month.", 13, CLEAN),
        # Labelling, claims and the rest
        pk("p-allergen", "jay", "Ragi Crunch back panel", "packaging", "Ragi Crunch puffed millet pack, comes in an 85 g pack. Veg.", 33,
           fixed("The allergen line is missing. Add Contains and the traces line.", "Ragi Crunch millet puffs, comes in an 85 g pack. Veg. Contains: ragi, wheat, soy. May contain traces of peanuts and tree nuts.", "regulatory")),
        pk("p-veg", "kavya", "Shelf strip for the oats", "print", "Masala Morning Oats shelf strip: warm, spiced and ready in three minutes. Energy and sugar per serving on the pack.", 31,
           fixed("The green veg mark is missing from the strip.", "Masala Morning Oats shelf strip: warm, spiced and ready in three minutes. Veg. Energy and sugar per serving on the pack.", "regulatory")),
        pk("p-pester", "ishaan", "Pip's video", "youtube", "Tell Mummy and Papa you need Pip's Choco-Malt right now! Pip will be so happy.", 29,
           fixed("Children must not be told to ask parents to buy. Talk to parents instead.", "Parents, Pip's Choco-Malt is in the dairy aisle if you want a treat for after school.", "reviewer")),
        pk("p-rival", "brightside", "Real ragi", "linkedin", "Unlike Crunchy Hills, our Ragi Crunch has real ragi in every bite.", 27,
           fixed("Never name another maker, and 'real' implies theirs is not.", "Our Ragi Crunch is made with ragi flour, roasted and lightly spiced.", "approver")),
        pk("p-best", "rhea", "India's tastiest", "instagram", "India's tastiest millet snack is back in a smaller pack. #NutmegLaneKitchen", 21,
           fixed("No self-declared rankings, and the pack size is 85 g now.", "Ragi Crunch is back in an 85 g pack. #NutmegLaneKitchen", "approver")),
        pk("p-sugar", "jay", "Not sugar-free", "blog", "Our Ragi Crunch is not a sugar-free snack: it is sweetened with jaggery, and the pack lists the grams.", 19,
           [(1, "send", {}), (2, "dispute", {"rule": "CLAIM-SUGAR", "claim": "The post says the opposite: it warns that the snack is NOT sugar-free. The term appears in a denial, not a claim."}), (4, "autodecide", {"by": "regulatory"}), (9, "approve", {"note": "Denial, not a claim; fine."}), (30, "publish", {})]),
        pk("p-protein", "ishaan", "Pip's protein", "instagram", "Packed with protein to keep kids full all day. Pip's Choco-Malt, every morning.", 16,
           fixed("No protein fact for the choco-malt, and no claims for a children's drink.", "Pip's Choco-Malt is a morning treat made with cocoa and malted barley.", "regulatory")),
        pk("p-sugarold", "jay", "Cold coffee sugar", "instagram", "Lane Cold Coffee has 9 g of sugar per serving. Chill it, shake it, pour it.", 9,
           fixed("That figure is from the old recipe: 6.5 g now.", "Lane Cold Coffee has 6.5 g of sugar per serving. Chill it, shake it, pour it.", "regulatory")),
        pk("p-contrast", "brightside", "Shelf poster", "print", "Diwali shelf poster for retail stores.", 5,
           fixed("The headline colour fails contrast. Use the dark brown.", "Diwali shelf poster for retail stores. Headline recoloured.", "reviewer"), event=dw,
           colors=[{"fg": "#F0B428", "bg": "#FCF6E8", "where": "headline on the poster", "large": True}],
           fix_colors=[{"fg": "#34200E", "bg": "#FCF6E8", "where": "headline on the poster", "large": True}],
           images=_img("shelf", "Diwali shelf poster headed Gifts from our kitchen with the Nutmeg Lane logo", lambda: _poster("Gifts from our kitchen", "Diwali gift boxes", "ok", _oats_pouch()))),
        pk("p-alt", "jay", "Coffee photo", "instagram", "A glass of Lane Cold Coffee over ice. Serving suggestion. #NutmegLaneKitchen", 8,
           fixed("The alt text says only 'photo'. Say which product and what is shown.", "A glass of Lane Cold Coffee over ice. Serving suggestion. #NutmegLaneKitchen", "reviewer"),
           images=lambda: [art.image_attachment("coffee", "photo", _coffee_shot())],
           fix_images=lambda: [art.image_attachment("coffee", "Glass of Lane Cold Coffee with ice and a striped straw on a pale counter", _coffee_shot())]),
        pk("p-ai", "anita", "Illustration for the blog", "blog", "Our new guide to reading a food label has a hand-drawn look. Read it on the care page.", 10,
           [(1, "send", {}), (3, "autodecide", {"by": "reviewer"}), (6, "back", {"note": "The illustration is AI-generated; say so in the post.", "by": "approver"}), (20, "fix", {"body": "Our new guide to reading a food label has a hand-drawn look. The illustration was made with AI. Read it on the care page."}), (21, "send", {}), (26, "approve", {})], notes={"ai_used": True}),
        pk("p-listing", "anita", "Retail listing refresh", "app store", "Lane Club has recipe cards, batch lookups and your orders. Nutmeg Lane is sold in 3,100 stores.", 9, CLEAN,
           images=_img("icon", "Lane Club app icon, a steaming white bowl on a green tile", lambda: art.on_color(_icon(), CREAM, 60))),
        pk("p-recolour", "ishaan", "Pip in pink", "instagram", "Pip has a new look for the weekend. #NutmegLaneKitchen", 6,
           [(1, "send", {}), (3, "autodecide", {"by": "reviewer"}), (6, "back", {"note": "Pip must keep the brown coat and the green scarf.", "by": "approver"})],
           images=_img("pinkpip", "Pip the squirrel in a pink coat above the words New look", lambda: _poster("New look", "Weekend", "recolour", art.recolour(_pip(), "gbr")))),
        pk("p-squash", "rhea", "Pip meme", "instagram", "When the monday alarm rings. Pip has feelings too. #NutmegLaneKitchen", 4,
           [(1, "send", {})],
           images=_img("squash", "A squashed Pip the squirrel looking sleepy above the words Monday mood", lambda: _poster("Monday mood", "", "ok", art.stretch(_pip(), 1.0, 0.55)))),
        pk("p-oldpack", "brightside", "Spring pack announcement", "instagram", "Meet the new look of Masala Morning Oats, now on shelf. #NutmegLaneKitchen", 30,
           fixed("That is the 2024 pack. Use the current pouch.", "Meet the new look of Masala Morning Oats, now on shelf. Pack picture updated. #NutmegLaneKitchen", "approver"),
           images=_img("announce", "Pack announcement card showing the Masala Morning Oats pouch and the Nutmeg Lane logo", lambda: _poster("A new look", "Masala Morning Oats", "ok", _oats_pouch_2024())),
           fix_images=_img("announce", "Pack announcement card showing the Masala Morning Oats pouch and the Nutmeg Lane logo", lambda: _poster("A new look", "Masala Morning Oats", "ok", _oats_pouch()))),
    ]


# --- routine work: banks per persona ---------------------------------------------------------------------

CLEAN_BANK = [
    ("Sunday breakfast", "instagram", "Sunday mornings are for slow breakfasts. Stir Masala Morning Oats with a pinch of jeera and let the kitchen smell like home. #NutmegLaneKitchen"),
    ("Ragi Crunch on the train", "instagram", "Some snacks travel well. Ragi Crunch stays crisp in the bag from one station to the next."),
    ("Cold coffee, your way", "x", "Shake Lane Cold Coffee with ice, pour it over a scoop of ice cream or drink it plain. Your glass, your rules."),
    ("How we roast", "blog", "Our coffee is roasted in small batches and cooled slowly before it is brewed for Lane Cold Coffee. This post walks through each step, from green beans to the bottle on your shelf."),
    ("Millet guide", "blog", "Millets are small grains that farmers have grown for centuries. Ragi, jowar and bajra each cook a little differently. This guide explains how to soak, roast and cook them at home."),
    ("Parent note", "whatsapp", "Hello parents, the new Pip's Choco-Malt recipe card is ready. Open the Lane Club app to see how to mix it with warm or cold milk."),
    ("Oats upma tonight", "instagram", "Recipe tonight: roast Masala Morning Oats for two minutes, add mustard seeds, curry leaves and chopped carrot, then splash in hot water. Done before the news starts."),
    ("Packing team", "linkedin", "We spent the week with our packing team, who check every seal by hand. Thank you to everyone who works behind the label."),
    ("Label reading", "blog", "Reading a food label is a skill. Start with the ingredients, which are listed by weight, then look at the serving size before you compare any numbers."),
    ("Allergen reminder", "email", "Our packs list allergens in bold on the back. Please read the line that starts with Contains before you share a snack with someone who has an allergy."),
    ("Tiffin tomorrow", "instagram", "Tiffin tomorrow: a roti roll, a few cucumber sticks and a handful of Ragi Crunch. Simple, quick and easy to pack."),
    ("Winter warm-up", "instagram", "Cold evenings call for a warm bowl. Masala Morning Oats with a spoon of ghee works at dinner too."),
    ("Care line", "x", "Questions about a pack? Our consumer care team is on +91 80 4561 7700 and will help."),
    ("Behind Pip", "instagram", "Pip the squirrel started as a doodle on a recipe card. Now Pip sits on the carton and reminds you to wash your hands before snack time."),
    ("Coffee ice cubes", "x", "Freeze a tray of Lane Cold Coffee into cubes. Your next glass will not go watery."),
    ("Hinglish tip", "instagram", "Subah ki jaldi mein bhi nashta zaroor karo. Masala Morning Oats teen minute mein ready."),
    ("Farmer note", "linkedin", "Ragi is a hardy crop that grows in dry fields with little water. We buy it from farmer groups and are glad to tell you more about where it comes from."),
    ("Tea-time swap", "instagram", "Try a bowl of roasted millet next to your usual tea-time snack and tell us which one you reach for."),
    ("Weekend brunch", "youtube", "In this video we make a quick brunch with Masala Morning Oats, a ripe tomato and a squeeze of lime. Chapters are listed below and a transcript is on our care page."),
    ("Millet quiz", "x", "Quick quiz: which millet is used for a dosa, ragi, jowar or bajra? Reply with your guess."),
    ("Choco-Malt mornings", "instagram", "Warm milk, a spoon of Pip's Choco-Malt and a story before school. That is how mornings go at our house."),
    ("Newsletter note", "email", "This month in the Nutmeg Lane kitchen: new recipe cards, a look at how we pack and answers to your questions about labels."),
    ("Chai pairing", "instagram", "Masala chai and Ragi Crunch is a pairing worth trying on a rainy evening."),
    ("Pouch recycling", "blog", "Our pouches are made of layered film that local centres cannot recycle yet. This post explains how to return empty pouches to us and what happens to them next."),
    ("Weekend travel", "instagram", "Packing for a long weekend? Slip a pack of Ragi Crunch and a bottle of Lane Cold Coffee into the bag."),
    ("Pip asks", "instagram", "Pip wants to know: what do you pack in your tiffin on Mondays? Tell us in the comments."),
    ("Farmers' market", "linkedin", "Our team will be at the farmers' market this Saturday with samples and recipe cards. Come say hello."),
    ("Recipe cards", "whatsapp", "Hello, your recipe card for Masala Morning Oats upma is ready. Reply with the word yes to receive more cards each week."),
    ("Oats back panel", "packaging", "Masala Morning Oats. Rolled oats with spices and dried vegetables. Add hot water, stir and wait three minutes. Veg. Contains: oats, wheat. May contain traces of peanuts. Serving suggestion shown."),
    ("Kitchen open day", "press release", "Nutmeg Lane will host a community cooking day at our Bengaluru kitchen this month. Journalists and food writers are welcome to attend."),
]

_NOTE = "Keep our warm, plain voice: no slang, no digs, no hype."
SLIPS = {
    "intern": [
        Slip("Pip and immunity", "instagram", "Pip's Choco-Malt boosts immunity for your little champ! 💪",
             "A glass of Pip's Choco-Malt is a treat to look forward to after school.",
             "Health claims need an approved basis. Describe the taste, not an effect on the body."),
        Slip("Monday mood", "x", "OMG this cold coffee is literally insane lol, you NEED it.",
             "Monday again. Lane Cold Coffee over ice makes it easier.", _NOTE),
        Slip("Festive rush", "instagram", "Hurry, last chance to grab the Diwali box, while stocks last!!!",
             "The Diwali gift box is available until the end of the gifting fest.", "No countdown pressure, no shouting."),
        Slip("Three packs", "instagram", "Have three Ragi Crunch packs a day, you deserve it!",
             "One pack of Ragi Crunch makes a good snack for the bag.", "Never tell children how much to eat."),
        Slip("Rival dig", "x", "Crunchy Hills snacks are mostly air. Ours is real ragi.",
             "Ours is made with ragi flour, roasted and lightly spiced.", "Never name another maker, even by hint."),
        Slip("Natural claim", "instagram", "100% natural, no preservatives, zero chemicals!",
             "Made with ragi flour, jaggery and spices. See the ingredient list on the pack.", "Natural claims are off for the cold coffee."),
        Slip("Protein claim", "instagram", "High protein oats to keep kids full all day.",
             "Masala Morning Oats has 4 g of protein per serving.", "A nutrient claim needs the fact and the serving."),
        Slip("Ask mummy", "instagram", "Ask mummy to buy Pip's Choco-Malt today or you will miss out!",
             "Parents can find Pip's Choco-Malt in the dairy aisle.", "Children must not be told to ask for a product."),
        Slip("Lowercase tag", "instagram", "Start the day slowly. #nutmeglanemornings", "Start the day slowly. #NutmegLaneMornings",
             "Capitalise each word in a hashtag."),
        Slip("Sugar-free", "instagram", "Sugar-free cold coffee for your evening.", "Lane Cold Coffee has 6.5 g of sugar per serving.",
             "Sugar-free is a protected term; give the grams."),
        Slip("Cures", "x", "Masala Morning Oats cures a tired tummy after a heavy meal.",
             "Masala Morning Oats is a light meal after a heavy day.", "No cure or health claims."),
    ],
    "agency": [
        Slip("Brand film caption", "youtube", "We leverage best-in-class FMCG synergies to operationalise nutrition for all stakeholders.",
             "Our film follows a morning in a Bengaluru kitchen, from the stove to the lunchbox.", "Write like a cook, not a contract."),
        Slip("Smarter kids", "instagram", "Kids who drink Pip's Choco-Malt are smarter and stronger than their friends.",
             "Pip's Choco-Malt is a treat with cocoa and malt for after school.", "No superiority claims in children's advertising."),
        Slip("Number one", "linkedin", "India's number one millet snack is now in a bigger pack.",
             "Ragi Crunch is sold in an 85 g pack.", "No self-declared rankings; use the pack fact."),
        Slip("Old price", "instagram", "Pip's Choco-Malt for just 135 rupees.", "Pip's Choco-Malt costs 149 rupees.", "That price is last year's."),
        Slip("Nothing artificial", "instagram", "Nothing artificial, completely natural cold coffee.",
             "Lane Cold Coffee is made with brewed coffee, milk and a little sugar.", "Natural claims are off for the cold coffee."),
        Slip("Wordmark", "linkedin", "Nutmeg lane brings the home kitchen to the shelf.", "Nutmeg Lane brings the home kitchen to the shelf.",
             "Our name is Nutmeg Lane, capital L."),
        Slip("Gift box offer", "instagram", "Diwali gift box at 20% off!", "Festive gift boxes are 15% off during the gifting fest.",
             "That discount is last year's."),
    ],
    "marketer": [
        Slip("Store count", "linkedin", "Find Nutmeg Lane in 2,400 stores across India.", "Nutmeg Lane is sold in 3,100 stores.",
             "That count is from last year."),
        Slip("Pack size", "instagram", "Ragi Crunch now comes in a 100 g pack.", "Ragi Crunch now comes in an 85 g pack.",
             "The pack is 85 g."),
        Slip("Coffee sugar", "x", "Lane Cold Coffee has 9 g of sugar per serving.", "Lane Cold Coffee has 6.5 g of sugar per serving.",
             "That is the old recipe."),
        Slip("Choco price", "instagram", "Get Pip's Choco-Malt for 135 rupees this season.", "Get Pip's Choco-Malt for 149 rupees this season.",
             "That price is last year's."),
        Slip("Kitchen count", "linkedin", "Every pack comes from one of our 5 kitchens.", "Every pack comes from one of our 3 kitchens.",
             "The licence register says 3."),
        Slip("Protein number", "instagram", "Masala Morning Oats packs 12 g of protein into every bowl.",
             "Masala Morning Oats has 4 g of protein per serving.", "Use the lab figure with its serving."),
    ],
    "influencer": [
        Slip("Switched snacks", "instagram", "Switched from Crunchy Hills to Ragi Crunch and wow, the difference. #NutmegLanePartner",
             "I pack Ragi Crunch in my bag for long shoots and love the roasted flavour. #NutmegLanePartner", "Do not name other brands."),
        Slip("Immunity", "instagram", "My kids' immunity has never been better since Pip's Choco-Malt. #NutmegLanePartner",
             "My kids look forward to Pip's Choco-Malt after school. #NutmegLanePartner", "No health or immunity claims."),
        Slip("Call me", "instagram", "Questions about the oats? Call me on 00000 12345 for my code.",
             "Questions about the oats? Use the code in my bio.", "Only the company's numbers in posts."),
        Slip("Slangy reel", "instagram", "no cap bestie, this cold coffee slaps 🔥 #NutmegLanePartner",
             "This cold coffee over ice is my afternoon fix. #NutmegLanePartner", _NOTE),
        Slip("Clinically proven", "youtube", "Dietitian approved and clinically proven to keep you full.",
             "My honest review: the oats keep my mornings simple.", "No medical approval claims."),
        Slip("Offer link", "instagram", "Grab the offer here: [click here](https://nutmeglane.example/offer)",
             "Grab the offer here: [festive offer details](https://nutmeglane.example/offer)", "Link text must say where it goes."),
    ],
    "regional": [
        Slip("Healthy nashta", "instagram", "Healthy nashta, Masala Morning Oats ke saath.", "Wholesome nashta, Masala Morning Oats ke saath.",
             "House word: wholesome, not healthy."),
        Slip("Tamil email", "email", "புதிய சமையல் அட்டைகள் இன்று தயார். E-mail மூலம் பெறுங்கள்.",
             "புதிய சமையல் அட்டைகள் இன்று தயார். Email மூலம் பெறுங்கள்.", "House word: email."),
        Slip("Doosre brands", "instagram", "Doosre brands ke snacks bekaar hain, Ragi Crunch hi lo.",
             "Ragi Crunch try karo, ragi se bana hai.", "No digs at other brands, even in Hindi."),
        Slip("Name casing", "instagram", "Ragi crunch ab nayi pack mein.", "Ragi Crunch ab nayi pack mein.", "Our product is Ragi Crunch."),
        Slip("Immunity Hindi", "instagram", "Cold coffee pi kar immunity badhao.", "Cold coffee thandi aur tasty hai.",
             "No health or immunity claims, in any language."),
    ],
    "careful": [
        Slip("Playlist link", "linkedin", "Recipe playlist: [click here](https://nutmeglane.example/recipes) for the full list.",
             "Recipe playlist: [open the full recipe playlist](https://nutmeglane.example/recipes).", "Link text must say where it goes."),
        Slip("Email house word", "email", "Send us your tiffin photos by e-mail.", "Send us your tiffin photos by email.",
             "House word: email."),
    ],
}

# Reviewers' calls on first-round findings of the scripted stories, so guideline health has a record to read.
DECISIONS = [
    ("s-immune", 5, "CLAIM-HEALTH", "regulatory", "accepted", None, None),
    ("s-three", 2, "KIDS-OVERUSE", "reviewer", "accepted", None, None),
    ("s-natural", 5, "CLAIM-NATURAL", "regulatory", "accepted", None, None),
    ("w-sugar", 5, "CLAIM-SUGAR", "regulatory", "accepted", None, None),
    ("w-sugar", 5, "MSG-COMPARE", "approver", "rejected", "guideline_unclear",
     "A cola is not a competitor of ours. Is a dig at another drink category a comparison?"),
    ("p-rival", 5, "MSG-COMPETITOR", "approver", "accepted", None, None),
    ("p-best", 5, "CLAIM-RANK", "approver", "accepted", None, None),
    ("d-cheap", 2, "TONE-URGENCY", "approver", "accepted", None, None),
    ("l-leak", 2, "CONF-LEAK", "reviewer", "accepted", None, None),
    ("k-win", 3, "KIDS-PESTER", "reviewer", "accepted", None, None),
    ("r-joke", 2, "TONE-SHIFT", "approver", "accepted", None, None),
    ("d-old", 4, "CLAIM-OUTDATED", "regulatory", "accepted", None, None),
    ("r-count", 2, "CLAIM-UNSUPPORTED", "regulatory", "accepted", None, None),
]

ADMIN_LOG = [
    (14, "patch_rule", {"code": "KIDS-PESTER", "patch": {
        "text": "Never tell a child to ask or nag a parent to buy it, and never suggest children who have it are smarter, "
                "stronger or more popular than children who do not. Cheering at a match is fine; linking the drink to a "
                "win is not.",
        "bad_examples": ["Nag mummy papa buy immediately", "Kids drinking become smarter stronger friends",
                         "Drink win every match champs"]}}),
    (9, "new_fact", {"key": "rating", "statement": "Customers rate Nutmeg Lane 4.4 out of 5 on the Lane Club app",
                     "value": 4.4, "unit": "out of 5", "subject": "customer rating",
                     "source_ref": "Lane Club app listing, Oct 2026", "from": -9}),
]


def build() -> Company:
    def pieces() -> list[Piece]:
        out = _stories() + routine("nutmeg", CREATORS, CLEAN_BANK, SLIPS, 55, 0.3, rate=0.045)
        keys = [p.key for p in out]
        assert len(keys) == len(set(keys)), "duplicate piece keys"
        return out

    return Company(
        key="nutmeg", brand=BRAND, industry="Packaged food and drink: masala oats, ragi snacks, a cold coffee and a "
        "children's choco-malt drink", domain="nutmeglane.example", days=56, team=TEAM, creators=CREATORS, rules=RULES,
        facts=FACTS, terms=TERMS, contacts=CONTACTS, assets=ARTWORK, events=EVENTS, people=PEOPLE, pieces=pieces,
        decisions=DECISIONS, stance=STANCE, admin_log=ADMIN_LOG, demo=DEMO)
