"""Paisaloop: a fictional Indian UPI payments and SIP investing app (PaisaPay for payments, LoopSIP for mutual
fund SIPs, LoopCard for a debit card). There is no mascot; the brand is a coin-and-loop emblem, a wordmark and
a violet and mint palette. The regulatory pressure is advertising codes for money: no assured returns, the
mutual-fund risk line wherever a fund or a return is promoted, cashback with its terms, fees stated, KYC
spoken of plainly, and fair comparisons only. The compliance officer is the strict reviewer; the social
manager is the practical one, and the two split on the unclear rules."""

from __future__ import annotations

from verytas.showcase import art
from verytas.showcase.gen import Slip, routine
from verytas.showcase.spec import CLEAN, Company, Member, Piece

VIOLET, INDIGO, MINT, AMBER = (84, 52, 190), (52, 30, 130), (60, 205, 150), (255, 190, 50)
OFFWHITE, INK = (246, 244, 252), (28, 22, 52)
BRAND = "Paisaloop"
DISCLAIMER = "Mutual fund investments are subject to market risks, read all scheme related documents carefully."


# --- artwork -----------------------------------------------------------------------------------------
# A coin with a rupee on its face, wrapped in a loop arrow, with an amber spark. Everything else in the system
# (card, app screen, partner, rival, pattern) is drawn with different shapes so no two assets match each other.

def _mark(size=400, ring=VIOLET, shade=INDIGO, face=(255, 255, 255), glyph=VIOLET, arrow=MINT, spark=AMBER):
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 400

    def b(*v):
        return tuple(x * s for x in v)

    w = lambda n: max(2, round(n * s))  # noqa: E731
    d.ellipse(b(10, 10, 390, 390), fill=ring + (255,))
    d.pieslice(b(10, 10, 390, 390), 20, 200, fill=shade + (255,))
    d.ellipse(b(70, 70, 330, 330), fill=face + (255,))
    # the rupee: two bars, a bowl and a slanted tail
    d.rectangle(b(140, 125, 262, 141), fill=glyph + (255,))
    d.rectangle(b(140, 156, 262, 172), fill=glyph + (255,))
    d.arc(b(110, 125, 250, 225), 270, 90, fill=glyph + (255,), width=w(16))
    d.line([b(150, 205)[:2], b(262, 290)[:2]], fill=glyph + (255,), width=w(18))
    # the loop: an arc round the coin that ends in an arrowhead
    d.arc(b(36, 36, 364, 364), 205, 335, fill=arrow + (255,), width=w(22))
    d.polygon([b(338, 112), b(372, 168), b(310, 160)], fill=arrow + (255,))
    # the spark
    d.ellipse(b(290, 36, 360, 106), fill=spark + (255,))
    d.ellipse(b(310, 56, 340, 86), fill=ring + (255,))
    return img


def _lockup(color=VIOLET, mark=None):
    return art.lockup(mark or _mark(), "Paisaloop", color)


def _rev():
    return art.on_color(_lockup((255, 255, 255), _mark(ring=(255, 255, 255), shade=(214, 204, 244), face=VIOLET,
                                                      glyph=(255, 255, 255))), VIOLET, 30)


def _wordmark():
    """The name set with a loop swooshing under it and a coin at the end, so it is more than a line of text."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (620, 230), "white")
    d = ImageDraw.Draw(img)
    f = art.font(104)
    d.text((26, 28), "Paisaloop", fill=VIOLET, font=f)
    d.arc((30, 120, 560, 215), 10, 170, fill=MINT, width=14)
    d.polygon([(40, 168), (24, 140), (66, 152)], fill=MINT)
    d.ellipse((540, 44, 598, 102), fill=AMBER)
    d.ellipse((556, 60, 582, 86), fill=VIOLET)
    d.rectangle((70, 196, 330, 206), fill=INDIGO)
    return img


def _app_icon():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, 511, 511), radius=116, fill=VIOLET + (255,))
    m = _mark(360, ring=(255, 255, 255), shade=(214, 204, 244), face=VIOLET, glyph=(255, 255, 255))
    img.paste(m, (76, 70), m)
    return img


def _old_logo():
    """The 2024 logo: a green coin-stack badge with a block P, the name in capitals beneath. Retired in the
    spring rebrand but still on partner decks and old merchant stickers."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (440, 440), "white")
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((70, 14, 370, 314), radius=48, fill=(18, 110, 82))
    for i in range(4):
        d.ellipse((120, 250 - i * 26, 320, 290 - i * 26), fill=(240, 190, 60), outline=(150, 105, 20), width=3)
    d.rectangle((150, 60, 188, 215), fill=(255, 255, 255))
    d.pieslice((150, 56, 290, 170), 270, 90, fill=(255, 255, 255))
    d.pieslice((188, 86, 258, 140), 270, 90, fill=(18, 110, 82))
    d.text((36, 340), "PAISALOOP", fill=(18, 80, 62), font=art.font(62))
    return img


def _partner():
    """Harbourline Bank: a shield with waves and a star, no lettering."""
    from PIL import ImageDraw

    img = art.emblem("shield", 300, (0, 96, 128), (0, 62, 96), (255, 205, 80))
    d = ImageDraw.Draw(img)
    for i in range(3):
        y = 150 + i * 36
        d.arc((60, y, 140, y + 46), 180, 360, fill=(255, 255, 255, 255), width=7)
        d.arc((140, y, 220, y + 46), 180, 360, fill=(255, 255, 255, 255), width=7)
    d.polygon([(150, 52), (162, 86), (198, 86), (169, 106), (180, 140), (150, 119), (120, 140), (131, 106),
               (102, 86), (138, 86)], fill=(255, 205, 80, 255))
    return img


def _competitor():
    """Mintfold's mark: a folded coral diamond with a crease and a seed. Their name sits beside it in content."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (300, 300), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(150, 10), (290, 150), (150, 290), (10, 150)], fill=(232, 84, 72, 255))
    d.polygon([(150, 10), (290, 150), (150, 150)], fill=(250, 140, 120, 255))
    d.polygon([(10, 150), (150, 150), (150, 290)], fill=(170, 40, 60, 255))
    d.line([(10, 150), (290, 150)], fill=(255, 235, 225, 255), width=5)
    d.line([(150, 10), (150, 290)], fill=(255, 235, 225, 255), width=5)
    d.ellipse((120, 120, 180, 180), fill=(255, 245, 200, 255))
    d.polygon([(70, 214), (96, 190), (112, 222), (84, 238)], fill=(255, 245, 200, 255))
    return img


def _card():
    """LoopCard, the debit card: a violet to mint sweep, a chip, contactless arcs and a ghosted coin."""
    from PIL import Image, ImageDraw

    w, h = 640, 400
    base = art.gradient((w, h), VIOLET, INDIGO)
    mask = Image.new("L", (w, h), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, w - 1, h - 1), radius=34, fill=255)
    d = ImageDraw.Draw(base)
    d.pieslice((330, -170, 830, 330), 90, 270, fill=(110, 78, 214))
    d.ellipse((410, 150, 600, 340), outline=(255, 255, 255), width=5)
    d.ellipse((440, 180, 570, 310), outline=AMBER, width=4)
    d.rounded_rectangle((52, 118, 148, 190), radius=12, fill=(235, 190, 80))
    d.line([(52, 154), (148, 154)], fill=(150, 110, 30), width=3)
    d.line([(100, 118), (100, 190)], fill=(150, 110, 30), width=3)
    for i in range(3):
        d.arc((170 + i * 12, 128 - i * 4, 210 + i * 24, 182 + i * 8), 300, 60, fill=(255, 255, 255), width=4)
    for g in range(4):
        for k in range(4):
            d.ellipse((56 + g * 120 + k * 22, 250, 66 + g * 120 + k * 22, 260), fill=(255, 255, 255))
    d.text((56, 312), "LoopCard", fill=(255, 255, 255), font=art.font(34))
    d.rectangle((430, 330, 590, 340), fill=MINT)
    out = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    out.paste(base, (0, 0), mask)
    return out


def _phone():
    """The app home screen on a phone: balance card, a row of actions, recent payments and a pay button."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (420, 820), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, 419, 819), radius=58, fill=INK + (255,))
    d.rounded_rectangle((16, 16, 403, 803), radius=44, fill=OFFWHITE + (255,))
    d.rectangle((16, 60, 403, 210), fill=VIOLET + (255,))
    d.ellipse((40, 84, 100, 144), fill=MINT + (255,))
    d.rounded_rectangle((120, 94, 300, 108), radius=7, fill=(214, 204, 244, 255))
    d.rounded_rectangle((120, 122, 230, 134), radius=6, fill=(170, 150, 230, 255))
    d.rounded_rectangle((44, 170, 376, 330), radius=26, fill=INDIGO + (255,))
    d.text((70, 196), "Balance", fill=(214, 204, 244), font=art.font(26, False))
    d.rounded_rectangle((70, 244, 260, 266), radius=11, fill=(255, 255, 255, 255))
    d.pieslice((286, 190, 366, 270), 180, 360, fill=AMBER + (255,))
    for i, c in enumerate([MINT, AMBER, (240, 110, 110), (110, 160, 240)]):
        x = 52 + i * 82
        d.ellipse((x, 360, x + 62, 422), fill=c + (255,))
        d.rounded_rectangle((x + 4, 432, x + 58, 442), radius=5, fill=(190, 184, 214, 255))
    for i in range(3):
        y = 480 + i * 86
        d.ellipse((44, y, 100, y + 56), fill=(214, 204, 244, 255))
        d.rounded_rectangle((116, y + 8, 290, y + 22), radius=7, fill=(120, 108, 170, 255))
        d.rounded_rectangle((116, y + 32, 220, y + 44), radius=6, fill=(196, 190, 220, 255))
        d.rounded_rectangle((320, y + 16, 376, y + 36), radius=9, fill=MINT + (255,) if i % 2 == 0 else (240, 110, 110, 255))
    d.rounded_rectangle((120, 726, 300, 780), radius=27, fill=MINT + (255,))
    d.text((176, 738), "Pay", fill=INK + (255,), font=art.font(30))
    d.polygon([(268, 742), (288, 753), (268, 764)], fill=INK + (255,))
    return img


ARTWORK = [
    {"name": "Paisaloop wordmark", "kind": "wordmark", "part": "wordmark", "wordmark": "Paisaloop",
     "image": _wordmark, "notes": "Brand book 2026, p.2. One word, capital P only: Paisaloop, never PaisaLoop."},
    {"name": "Paisaloop logo", "kind": "logo", "wordmark": "Paisaloop",
     "image": lambda: _lockup().convert("RGBA"),
     "notes": "Primary lockup: the coin-and-loop emblem left of the name. Clear space of one coin width. Brand book 2026, p.4."},
    {"name": "Paisaloop logo, reversed", "kind": "logo", "wordmark": "Paisaloop", "image": _rev,
     "notes": "White on brand violet, for posters, cards and video end frames. Brand book 2026, p.5."},
    {"name": "Paisaloop app icon", "kind": "icon", "part": "icon", "image": _app_icon,
     "notes": "Store listings and the home screen. Never stretched into a banner."},
    {"name": "Paisaloop logo 2024", "kind": "logo", "retired": True, "wordmark": "PAISALOOP", "image": _old_logo,
     "notes": "Retired in the spring rebrand. Still found on merchant stickers and partner decks."},
    {"name": "Harbourline Bank", "kind": "partner", "wordmark": "Harbourline Bank", "image": _partner,
     "notes": "UPI partner bank. Shown at equal height beside ours, never inside our logo's clear space."},
    {"name": "Mintfold", "kind": "competitor", "wordmark": "Mintfold", "image": _competitor,
     "notes": "A rival payments and investing app. Its mark must not appear in our content."},
    {"name": "Coin trail", "kind": "pattern",
     "image": lambda: art.pattern("dots", 600, OFFWHITE, VIOLET, MINT), "notes": "Backgrounds for print and event stages."},
    {"name": "LoopCard debit card", "kind": "product", "image": _card,
     "notes": "The debit card as shown on the site and in ads. Always at its own proportions."},
    {"name": "PaisaPay home screen", "kind": "product", "image": _phone,
     "notes": "The approved app screenshot for stores and decks. Show balances only as drawn."},
]


# --- the library ---------------------------------------------------------------------------------------

def _r(code, category, kind, severity, title, text, pattern=None, bad=None, good=None, ref=None):
    return {"code": code, "category": category, "kind": kind, "severity": severity, "title": title, "text": text,
            "pattern": pattern or {}, "bad_examples": bad or [], "good_examples": good or [], "source_ref": ref}


RULES = [
    _r("LEGAL-MFDISC", "legal", "semantic", "must", "Fund promotions carry the risk line",
       "Any post that promotes a mutual fund, a SIP or returns must carry the line: " + DISCLAIMER,
       bad=["Start a SIP on LoopSIP from 100 rupees a month", "Invest in our equity fund today",
            "ELSS funds come with a lock-in of 3 years, start now"],
       good=[DISCLAIMER], ref="Compliance memo C-7, section 2"),
    _r("LEGAL-PAST", "legal", "semantic", "must", "Past returns carry the standard warning",
       "Whenever past returns or a performance chart are shown, say that past returns are not indicative of future "
       "returns and point to the scheme documents.",
       bad=["Our LoopSIP equity fund has climbed through the last three years",
            "Our equity fund turned every month of saving into a bigger pot over the last few years"],
       good=["Past returns are not indicative of future returns"],
       ref="Compliance memo C-7, section 3"),
    _r("CLAIM-ASSURED", "claims", "deterministic", "must", "No assured or fixed returns",
       "Investments never come with promised outcomes. Do not say or imply assured, guaranteed or fixed returns.",
       {"type": "banned_terms", "terms": ["guaranteed returns", "assured returns", "assured income", "fixed returns",
                                          "sure returns", "guaranteed profit", "assured profit", "double your money",
                                          "can't lose", "never lose", "no loss", "assured savings",
                                          "pakka returns"]},
       ref="Compliance memo C-7, section 1; marketing code M-3"),
    _r("CLAIM-RISKFREE", "claims", "deterministic", "must", "Nothing is risk-free",
       "Markets carry risk. We do not call any fund, SIP or product risk-free, zero risk or completely safe.",
       {"type": "banned_terms", "terms": ["risk-free", "risk free", "zero risk", "no risk", "100% safe", "completely safe",
                                          "totally safe", "bilkul safe"]}, ref="Compliance memo C-7, section 1"),
    _r("CLAIM-IMPLIED", "claims", "semantic", "must", "No implied promise of growth",
       "Do not suggest that money grows steadily, that gains are certain or that saving here beats the market. "
       "A SIP is a habit, not a return.",
       bad=["Put money in a SIP and it grows every month", "Your money grows every month with a SIP",
            "Watch your savings multiply, month after month"],
       good=["A SIP lets you invest a fixed amount every month and keeps you regular"], ref="Compliance memo C-7, section 1"),
    _r("LEGAL-CASHBACK", "legal", "semantic", "must", "Cashback names its cap, who qualifies and when it ends",
       "Cashback and rewards state the most a user can earn, what they must do and the last day. Full terms are "
       "one tap away in the app.",
       bad=["Cashback on every payment, no strings attached", "Earn rewards on everything you buy this week",
            "Cashback on every payment today"],
       good=["Up to 150 rupees cashback on a bill payment until Sunday. Terms apply, see the offer page in the app"],
       ref="Marketing code M-5"),
    _r("LEGAL-FEES", "legal", "semantic", "must", "Say what it costs",
       "State any fee or charge next to the offer, or say where the charges are listed. Never imply a service "
       "is free when a charge applies.",
       bad=["Withdraw instantly, no questions asked", "Everything is covered, nothing to pay"],
       good=["UPI transfers between people carry no fee. Other charges are listed in the app under Charges"],
       ref="Marketing code M-5; fee schedule 2026"),
    _r("LEGAL-FREE", "legal", "deterministic", "must", "Free means free, with its limit",
       "Do not say free forever or zero charges. Say what is free and what is not.",
       {"type": "banned_terms", "terms": ["free forever", "zero charges", "no charges ever", "totally free", "100% free",
                                          "completely free", "free money", "no hidden charges"]},
       ref="Marketing code M-5"),
    _r("LEGAL-MINORS", "legal", "semantic", "must", "Money products are for adults",
       "Payments and investing are for KYC-verified adults. Do not address school students or children, or suggest "
       "they open an account.",
       bad=["Class nine students can start a SIP with pocket money", "School students can open a card with pocket money"],
       good=["Parents can read about long-term saving in our guide for families"], ref="Compliance memo C-9"),
    _r("LEGAL-KYC", "legal", "deterministic", "must", "Never wave KYC away",
       "KYC is a legal step. Do not say it is skipped, optional or not needed.",
       {"type": "banned_terms", "terms": ["no kyc", "without kyc", "kyc-free", "skip kyc", "kyc not needed",
                                          "kyc optional"]}, ref="Compliance memo C-9"),
    _r("MSG-COMPETITOR", "messaging", "deterministic", "must", "Never name another app",
       "Do not name competing payments or investing apps, even to say we are different. Talk about what we do.",
       {"type": "banned_terms", "terms": ["Mintfold"]}, ref="Brand book 2026, p.11"),
    _r("MSG-FAIRCOMP", "messaging", "semantic", "must", "Fair comparisons only",
       "Never compare us with other apps by name or by hint. A comparison needs a dated, published source, and "
       "needs legal sign-off.",
       bad=["Unlike other payment apps, our payments never fail", "Other apps hide their charges",
            "We put the two big names side by side"],
       good=["PaisaPay shows the status of every payment as it happens"], ref="Brand book 2026, p.11"),
    _r("LEGAL-FINFLUENCER", "legal", "semantic", "must", "Partner posts disclose and never pick funds",
       "A creator partner says it is a paid partnership, and never recommends a specific fund, tells followers to "
       "buy, or shares their own holdings as advice.",
       bad=["This is the fund I would put everything in right now, buy before Friday",
            "I put all my savings in this fund and you should too"],
       good=["I use Paisaloop to track my SIPs. This is a paid partnership, not investment advice"],
       ref="Compliance memo C-11"),
    _r("TERM-NAME", "terminology", "deterministic", "must", "Our names, spelled our way",
       "Write PaisaPay, LoopSIP and LoopCard exactly like this, with a capital in the middle.",
       {"type": "casing", "terms": ["PaisaPay", "LoopSIP", "LoopCard"]}, ref="Brand book 2026, p.3"),
    _r("TERM-HOUSE", "terminology", "deterministic", "should", "House words",
       "Use our house words.",
       {"type": "preferred_terms", "map": {"customer": "user", "e-mail": "email", "login": "sign in",
                                           "money-back": "cashback", "e-wallet": "PaisaPay balance"}},
       ref="Brand book 2026, p.9"),
    _r("TONE-PLAIN", "tone", "semantic", "should", "Calm, plain words about money",
       "Write like a steady friend who knows money: plain, calm, specific. No jargon, no hype, no pressure.",
       bad=["Leverage alpha-generating instruments to optimise your portfolio", "Moon-shot returns incoming, stack up"],
       good=["Pick an amount you can keep up every month and let it run"], ref="Brand book 2026, p.6"),
    _r("TONE-URGENCY", "tone", "deterministic", "should", "No pressure to invest",
       "Money decisions are not flash sales. Say when an offer ends; do not rush people.",
       {"type": "banned_terms", "terms": ["hurry", "last chance", "don't miss out", "act now", "limited period only",
                                          "invest now or regret", "once in a lifetime", "jaldi karo"]},
       ref="Brand book 2026, p.7"),
    _r("CONF-FINDATA", "confidentiality", "deterministic", "must", "No account identifiers",
       "PAN, Aadhaar, account and transaction numbers never appear in a post, even in a screenshot.",
       {"type": "banned_terms", "terms": ["pan number", "aadhaar number", "account number", "transaction id"]},
       ref="Privacy policy 4.2"),
    _r("VIS-PALETTE", "visual", "deterministic", "should", "Brand colours only",
       "Posters and cards use the Paisaloop palette: violet, indigo, mint, amber and off-white.",
       {"type": "palette", "colors": ["#5434BE", "#341E82", "#3CCD96", "#FFBE32", "#F6F4FC", "#1C1634"],
        "max_delta_e": 22, "min_share": 0.2}, ref="Brand book 2026, p.15"),
    _r("LEGAL-GRIEVANCE", "legal", "semantic", "should", "Complaints go to the grievance officer",
       "A post about a failed payment, a refund or a complaint names the grievance route: the grievance email or "
       "the support line, never a personal account.",
       bad=["Payment failed? Just DM us and we will sort it", "Tell us in the comments if your money is stuck"],
       good=["If a payment goes wrong, write to our grievance officer at grievance@paisaloop.example"],
       ref="Compliance memo C-12"),
]

# The offline judge scores a text by its word overlap with the rule's examples, so every semantic rule also
# carries ordinary, compliant copy; the hosted judge reads the rule itself and ignores this.
_ORDINARY = [
    "Pay your bills from one place and see the status of each payment as it happens in the app, and write to us if you are stuck",
    "Pick an amount you can keep up every month and let your plan run on its own, with a note of what it is for and when it ends",
    "This week on the blog: a short guide to budgeting, bill reminders and keeping your records in one view that you can read with us",
    "We ask for the details we need and nothing more, so that you can pay, save and start from the same app, and you can change it at any time",
]
for _rule in RULES:
    if _rule["kind"] == "semantic":
        _rule["good_examples"] = [*_rule["good_examples"], *_ORDINARY]

FACTS = [
    {"key": "users_old", "statement": "Paisaloop has 8 million users", "value": 8, "unit": "million",
     "subject": "users", "source_ref": "Annual report 2025, p.3", "from": -420},
    {"key": "users", "statement": "Paisaloop has 11 million users", "value": 11, "unit": "million",
     "subject": "users", "source_ref": "Annual report 2026, p.3", "from": -150, "supersedes": "users_old"},
    {"key": "aum_old", "statement": "Investors hold 900 crore rupees in SIPs on Paisaloop", "value": 900,
     "unit": "crore", "subject": "SIP assets", "source_ref": "Investments report, March 2026", "from": -230},
    {"key": "aum", "statement": "Investors hold 1,400 crore rupees in SIPs on Paisaloop", "value": 1400,
     "unit": "crore", "subject": "SIP assets", "source_ref": "Investments report, September 2026",
     "from": -40, "supersedes": "aum_old"},
    {"statement": "A SIP on Paisaloop starts at 100 rupees a month", "value": 100, "unit": "rupees",
     "subject": "minimum SIP", "source_ref": "Product sheet, LoopSIP 2026", "from": -300},
    {"statement": "UPI payments on PaisaPay succeed 99.2% of the time", "value": 99.2, "unit": "%",
     "subject": "UPI success rate", "source_ref": "Payments ops report, September 2026", "from": -40},
    {"statement": "Paisaloop is rated 4.6 out of 5 in the app stores", "value": 4.6, "unit": "out of 5",
     "subject": "rating", "source_ref": "Store listing, September 2026", "from": -45},
    {"key": "cb_monsoon", "statement": "Monsoon cashback of up to 75 rupees on a bill payment", "value": 75,
     "unit": "rupees", "subject": "cashback on bill payment", "source_ref": "Monsoon cashback brief", "from": -55,
     "to": -44},
    {"key": "cb_festive", "statement": "Festive cashback of up to 150 rupees on a bill payment", "value": 150,
     "unit": "rupees", "subject": "cashback on bill payment", "source_ref": "Festive cashback brief",
     "from": -3, "to": 9},
    {"statement": "Transfers between people on PaisaPay carry no fee", "subject": "UPI transfer fee",
     "source_ref": "Fee schedule 2026", "from": -300},
    {"statement": "ELSS funds have a lock-in of 3 years", "value": 3, "unit": "years", "subject": "ELSS lock-in",
     "source_ref": "Product sheet, tax saving 2026", "from": -300},
    {"statement": "PaisaPay supports UPI payments of up to 1 lakh rupees a day", "value": 100000, "unit": "rupees",
     "subject": "daily UPI limit", "source_ref": "Payments policy 2026", "from": -200},
    {"statement": "Complaints are acknowledged within 24 hours", "value": 24, "unit": "hours",
     "subject": "complaint acknowledgement", "source_ref": "Grievance policy 2026", "from": -200},
    {"statement": "SIPs in the Compass fund start at 500 rupees a month", "value": 500, "unit": "rupees",
     "subject": "Compass fund minimum SIP", "source_ref": "Compass launch brief (embargoed)", "from": 14},
]

TERMS = [
    {"term": "Project Compass", "note": "The new LoopSIP fund. Embargoed until launch day", "embargo": 14},
    {"term": "Project Lantern", "note": "Credit line inside PaisaPay. Not announced; regulator filing pending"},
    {"term": "Project Anchor", "note": "Co-branded card with Ridgeway Bank. Never public until the bank announces it"},
    {"term": "Project Ember", "note": "Earlier codename for LoopCard. Public since the card launched", "embargo": -25},
]

CONTACTS = [
    {"kind": "phone", "value": "+91 22 4000 1200", "label": "User support", "source_ref": "paisaloop.example/contact"},
    {"kind": "phone", "value": "+91 22 4000 1299", "label": "Grievance officer", "source_ref": "Grievance policy 2026"},
    {"kind": "phone", "value": "+91 22 4000 1250", "label": "Press desk", "source_ref": "paisaloop.example/press"},
    {"kind": "email", "value": "grievance@paisaloop.example", "label": "Grievance officer", "source_ref": "Grievance policy 2026"},
    {"kind": "email", "value": "*@paisaloop.example", "label": "Company domain", "source_ref": "IT policy"},
    {"kind": "url", "value": "paisaloop.example", "label": "Website", "source_ref": "Brand book 2026, p.2"},
    {"kind": "url", "value": "help.paisaloop.example", "label": "Help centre", "source_ref": "Support charter"},
    {"kind": "handle", "value": "@paisaloop", "label": "Social handle", "source_ref": "Brand book 2026, p.2"},
    {"kind": "handle", "value": "@paisaloop_help", "label": "Support handle", "source_ref": "Support charter"},
]

EVENTS = [
    {"key": "monsoon", "created": 54, "name": "Monsoon Cashback Week", "kind": "sale", "start": -52, "end": -44,
     "hashtags": ["#MonsoonCashback"], "avoid_terms": ["unlimited cashback", "free money"],
     "guidance": "Lead with paying bills easily; the cashback comes second and always with its terms.",
     "summary": "Cashback on bill payments across the monsoon week."},
    {"key": "downtime", "created": 40, "name": "UPI downtime, early September", "kind": "crisis", "start": -38, "end": -36,
     "blackout": True, "guidance": "Acknowledge plainly. No jokes, no promotions, point to the grievance route.",
     "summary": "UPI payments failed in waves over two days after a bank-side outage."},
    {"key": "circular", "created": 36, "name": "Advertising circular for fund promotions", "kind": "other", "start": -35,
     "guidance": "New circular: every fund promotion carries the risk line, every performance claim carries the past "
     "returns warning. Review every fund post twice.",
     "summary": "Regulatory change in how mutual funds may be advertised."},
    {"key": "tax", "created": 32, "name": "Early tax-saving push", "kind": "campaign", "start": -30, "end": -12,
     "hashtags": ["#SaveTaxSmart"], "avoid_terms": ["assured savings", "tax-free returns"],
     "guidance": "ELSS is a market product with a lock-in. Explain the lock-in, never promise savings or returns. "
     "The big window closes on 31 March; this is the early push.",
     "summary": "Explainers on ELSS and tax-saving SIPs ahead of the March rush."},
    {"key": "festive", "created": 12, "name": "Festive Cashback Week", "kind": "sale", "start": -3, "end": 9,
     "hashtags": ["#PaisaloopFestive"], "avoid_terms": ["unlimited cashback", "free money", "lowest ever"],
     "guidance": "Lead with ease of paying; cashback comes second with its cap, who qualifies and the last day.",
     "summary": "Festive cashback on bill payments."},
    {"key": "compass", "created": 5, "name": "LoopSIP Compass fund launch", "kind": "launch", "start": 14,
     "hashtags": ["#NewFundSoon"], "guidance": "Until launch day, tease the feeling, not the fund: no returns, no "
     "minimums, no dates, no codename.", "summary": "A new fund on LoopSIP."},
]

PEOPLE = [
    {"name": "Aarav Khanna", "kind": "celebrity", "aliases": ["Aarav"], "channels": ["instagram", "youtube"],
     "events": ["festive"], "from": -40, "to": 90, "notes": "Actor. Festive Cashback Week only; fee and exclusivity "
     "terms in contract K-31."},
    {"name": "Faiz Qureshi", "kind": "creator", "aliases": ["Faiz", "FinWithFaiz"], "channels": ["instagram", "youtube"],
     "from": -55, "to": 120, "notes": "Creator partner. Posts disclose the partnership and never name a fund."},
    {"name": "Dr. Shalini Rao", "kind": "ambassador", "aliases": ["Shalini Rao"], "channels": [], "from": -400,
     "to": -30, "notes": "Financial literacy ambassador. Agreement ended; renewal under discussion."},
]

TEAM = [
    Member("admin", "tanvi@paisaloop.example", "Tanvi Deshmukh", "brand_admin", title="Head of brand",
           blurb="Owns the brand library: rules, facts, artwork, events. Sees every screen."),
    Member("approver", "rahul@paisaloop.example", "Rahul Menon", "approver", title="Social media manager",
           blurb="Works the review queue: approves, sends back, rules on escalations."),
    Member("reviewer", "pooja@paisaloop.example", "Pooja Venkat", "reviewer"),
    Member("auditor", "latha@paisaloop.example", "Latha Iyer", "auditor"),
    Member("compliance", "farida@paisaloop.example", "Farida Ansari", "reviewer"),
]
CREATORS = [
    Member("anika", "anika@paisaloop.example", "Anika Sethi", "creator", "careful"),
    Member("vihaan", "vihaan@paisaloop.example", "Vihaan Chopra", "creator", "marketer"),
    Member("kriti", "kriti@paisaloop.example", "Kriti Bansal", "creator", "intern"),
    Member("jaspreet", "jaspreet@paisaloop.example", "Jaspreet Gill", "creator", "regional"),
    Member("dhruv", "dhruv@paisaloop.example", "Dhruv Pillai", "creator", "marketer"),
    Member("growth", "team@growthlab.example", "GrowthLab Studio (agency)", "creator", "agency"),
    Member("faiz", "faiz@creators.example", "Faiz Qureshi (creator partner)", "creator", "influencer"),
    Member("meenal", "meenal@paisaloop.example", "Meenal Kulkarni", "creator", "regional"),
]
DEMO = [
    ("approver", "approver", "manager", "Social media manager",
     "Works the review queue: approves, sends back, rules on escalations."),
    ("admin", "admin", "manager", "Head of brand",
     "Owns the brand library: rules, facts, artwork, events. Sees every screen."),
    ("compliance", "compliance", "manager", "Compliance officer",
     "Stricter than the queue: rejects fund posts the social team would pass, and says why."),
    ("c2", "kriti", "creator", "Content creator", "Instagram and X. Writes fast and slips on promises and hype."),
    ("c4", "dhruv", "creator", "Content creator", "Performance marketing. Quotes numbers that have moved on."),
    ("c5", "growth", "creator", "Agency", "An outside agency writing campaigns for the brand."),
]

# How each reviewer tends to rule: Pooja is lenient on anything that reads like a payments post, Rahul is
# practical, Farida (compliance) upholds nearly every legal and claims finding. The unclear rules (implied
# growth, cashback terms, comparisons) are where they split and say so.
_UNCLEAR = ("guideline_unclear", "Does the rule mean this? It reads as a habit message, not a return.")
STANCE = {
    "reviewer": {"LEGAL-MFDISC": (0.45, [("not_applicable", "A payments post. No fund is promoted here.")]),
                 "LEGAL-PAST": (0.5, [("false_positive", "No performance is shown."), _UNCLEAR]),
                 "CLAIM-IMPLIED": (0.35, [_UNCLEAR, ("false_positive", "A saving habit, not a promise.")]),
                 "MSG-FAIRCOMP": (0.5, [("false_positive", "Names nobody.")]),
                 "TONE-PLAIN": (0.8, [("false_positive", "Plain enough for this channel.")]),
                 "TERM-HOUSE": (0.95, []), "*": (0.8, [("not_applicable", "Does not apply.")])},
    "approver": {"LEGAL-MFDISC": (0.6, [("intentional", "Short push copy; the risk line sits on the landing page.")]),
                 "CLAIM-IMPLIED": (0.3, [_UNCLEAR, ("false_positive", "General statement, not a figure.")]),
                 "LEGAL-CASHBACK": (0.5, [("guideline_unclear", "Does the terms line sit in the post or can it link out?"),
                                          ("false_positive", "Terms are one tap away in the app.")]),
                 "MSG-FAIRCOMP": (0.45, [_UNCLEAR, ("false_positive", "Names nobody.")]),
                 "A11Y-READ": (0.3, [("not_applicable", "Hinglish; the grade does not mean anything.")]),
                 "*": (0.7, [("false_positive", "Reads fine to me.")])},
    "compliance": {"LEGAL-MFDISC": (1.0, []), "LEGAL-PAST": (1.0, []), "CLAIM-IMPLIED": (0.95, []),
                   "LEGAL-CASHBACK": (0.9, [("guideline_unclear", "Terms link is fine, but the cap must be in the post.")]),
                   "LEGAL-FINFLUENCER": (1.0, []), "CLAIM-CONTRADICTED": (1.0, []), "CLAIM-OUTDATED": (1.0, []),
                   "CLAIM-UNSUPPORTED": (0.9, []), "TONE-SHIFT": (0.3, [("not_applicable", "Not a compliance matter.")]),
                   "TONE-PLAIN": (0.3, [("not_applicable", "Tone is the brand team's call.")]),
                   "*": (0.9, [("not_applicable", "Outside compliance's remit.")])},
}


# --- images -----------------------------------------------------------------------------------------------

def _img(key, alt, img):
    return lambda: [art.image_attachment(key, alt, img() if callable(img) else img)]


def _poster(headline, sub="", logo="ok", figure=None, size=(1080, 1080), fine="", fine_color=(255, 255, 255)):
    """A violet campaign card. `logo` says how the mark was used: as registered, stretched into a wider slot, the
    retired 2024 version, the rival's mark, or recoloured. `fine` is small print set in `fine_color`."""
    from PIL import ImageDraw

    img = art.card(size, VIOLET, headline, sub, art=figure, art_w=330)
    rev = _rev()
    if logo == "ok":
        art.paste(img, rev, (74, 860), width=420)
    elif logo == "stretched":
        art.paste(img, rev, (74, 860), width=round(420 * 1.3), height=round(420 * rev.height / rev.width))
    elif logo == "old":
        art.paste(img, _old_logo(), (74, 800), width=380)
    elif logo == "recolour":
        art.paste(img, art.recolour(rev, "brg"), (74, 860), width=420)
    elif logo == "rival":
        art.paste(img, _competitor(), (74, 760), width=240)
    if fine:
        ImageDraw.Draw(img).text((74, 1010), fine, fill=fine_color, font=art.font(15, False))
    return img


def _chart():
    """A bar chart of a fund's past years, climbing left to right, with no warning on it."""
    from PIL import ImageDraw

    img = art.canvas((1080, 1080), OFFWHITE)
    d = ImageDraw.Draw(img)
    d.text((70, 70), "Three years of the LoopSIP equity fund", fill=INK, font=art.font(52))
    d.line([(110, 880), (990, 880)], fill=INK, width=5)
    d.line([(110, 260), (110, 880)], fill=INK, width=5)
    for i, hgt in enumerate([150, 230, 280, 360, 430, 520]):
        x = 170 + i * 135
        d.rectangle((x, 880 - hgt, x + 90, 880), fill=AMBER if i == 5 else VIOLET)
    art.paste(img, _lockup().convert("RGBA"), (70, 930), width=360)
    return img


def _compare():
    from PIL import ImageDraw

    img = art.canvas((1080, 1080), OFFWHITE)
    d = ImageDraw.Draw(img)
    d.text((80, 90), "Which app pays you back sooner?", fill=INK, font=art.font(58))
    art.paste(img, _lockup().convert("RGBA"), (60, 440), width=420)
    art.paste(img, _competitor(), (640, 380), width=300)
    d.text((660, 700), "Mintfold", fill=(170, 40, 60), font=art.font(54))
    d.text((510, 480), "vs", fill=INK, font=art.font(48))
    return img


def _star(name, caption):
    img = art.portrait((1080, 1080), (208, 160, 128), OFFWHITE, VIOLET, caption)
    art.paste(img, _lockup().convert("RGBA"), (60, 40), width=300)
    return img


def _partner_card():
    from PIL import ImageDraw

    img = art.canvas((1200, 628), (255, 255, 255))
    art.paste(img, _lockup().convert("RGBA"), (80, 200), width=420)
    art.paste(img, _partner(), (720, 150), width=300)
    ImageDraw.Draw(img).text((690, 470), "Harbourline Bank", fill=(0, 80, 110), font=art.font(36))
    return img


def _card_post(stretched=False):
    card = _card()
    if stretched:
        card = art.stretch(card, 1.3, 1.0)
    img = art.canvas((1080, 1080), OFFWHITE)
    art.paste(img, card, (60 if stretched else 120, 300), width=960 if stretched else 840)
    art.paste(img, _lockup().convert("RGBA"), (70, 80), width=360)
    return img


def _screen_post():
    img = art.card((1080, 1080), VIOLET, "Everything in one view", "Bills, cards and SIPs", art=_phone(), art_w=330)
    art.paste(img, _rev(), (74, 860), width=420)
    return img


# --- the eight weeks, scripted ------------------------------------------------------------------------------

def _back(note, by="compliance", autoby="reviewer"):
    return [(1, "send", {}), (3, "autodecide", {"by": autoby}), (6, "back", {"note": note, "by": by})]


def _fx(note, body, by="compliance", autoby="reviewer"):
    """Sent, triaged by a reviewer, sent back by `by`, fixed, resent, approved and published."""
    return [*_back(note, by, autoby), (20, "fix", {"body": body}), (21, "send", {}), (26, "approve", {}),
            (40, "publish", {})]


def _rounds(first, second, final, by="compliance"):
    """Two sends back: the first fix still carries a problem, the second is clean."""
    return [(1, "send", {}), (3, "autodecide", {"by": "reviewer"}), (6, "back", {"note": first[0], "by": by}),
            (14, "fix", {"body": first[1]}), (15, "send", {}), (17, "autodecide", {"by": by}),
            (22, "back", {"note": second[0], "by": by}), (30, "fix", {"body": final}), (31, "send", {}),
            (36, "approve", {}), (50, "publish", {})]


def _stories() -> list[Piece]:
    pk = Piece
    mon, down, circ, tax, fest, comp = "monsoon", "downtime", "circular", "tax", "festive", "compass"
    return [
        # Monsoon cashback, eight weeks back
        pk("m-clean", "anika", "Bill day in the rain", "instagram", "Rain on the window, bills on the list. Pay electricity and water bills on PaisaPay this week and earn cashback on a bill payment. Terms apply, see the offer page in the app. #MonsoonCashback", 51, CLEAN, event=mon),
        pk("m-hype", "kriti", "Cashback on everything", "instagram", "Cashback on every payment!! Rain or shine 🤑 Pay now, last chance this week! #MonsoonCashback", 50.5,
           _fx("Cashback needs its cap, who qualifies and the last day. No money emoji, no countdown.", "Earn cashback on a bill payment this week. Terms apply, see the offer page in the app. #MonsoonCashback", "approver"), event=mon),
        pk("m-film", "growth", "Monsoon film description", "youtube", "Watch how PaisaPay turns bill day into cashback day, with guaranteed cashback on every bill. #MonsoonCashback", 49,
           _fx("We cannot promise cashback on every bill. Keep to the terms in the offer page.", "Watch how PaisaPay turns bill day into cashback day. Offer terms are in the app. #MonsoonCashback"), event=mon),
        pk("m-dispute", "dhruv", "Monsoon cashback line", "x", "Monsoon cashback of up to 75 rupees on a bill payment, until the weekend. Terms apply, see the app. #MonsoonCashback", 47,
           [(1, "send", {}), (2, "dispute", {"rule": "CLAIM-OUTDATED", "claim": "The 75 rupee cap was live in the monsoon week this ran in. The brief and the dates are in the cashback brief."}),
            (4, "autodecide", {"by": "approver"}), (9, "approve", {"note": "Offer was live on the posting date; checked against the monsoon brief."}), (30, "publish", {})], event=mon),
        # The September outage
        pk("o-ack", "anika", "We know payments are failing", "x", "We know some UPI payments are failing right now. Debits that did not reach the receiver are reversed automatically. We will update here, and Help in the app lists every route to support.", 38.2, [(0.3, "send", {}), (0.8, "approve", {}), (1.1, "publish", {})], event=down),
        pk("o-joke", "kriti", "UPI is having a moment", "x", "lol UPI is having a moment, grab popcorn. Refunds coming soon, chill!", 37.8,
           [(0.5, "send", {}), (1.5, "autodecide", {"by": "approver"}), (2, "back", {"note": "No jokes while payments fail. Acknowledge it plainly and point to the grievance route.", "by": "approver"}),
            (6, "fix", {"body": "UPI payments are failing for some of you. We are working on it. If a debit did not reach the receiver it is reversed automatically; write to grievance@paisaloop.example if it has not reached you."}),
            (6.5, "send", {}), (7, "approve", {}), (7.5, "publish", {})], event=down),
        pk("o-promo", "vihaan", "Weekend cashback is on", "instagram", "Weekend cashback is on! Pay your bills on PaisaPay and earn a reward.", 37.2,
           [(1, "send", {}), (3, "back", {"note": "Promotions are paused until UPI is stable. Hold this until the outage ends.", "by": "approver"})], event=down),
        pk("o-back", "anika", "UPI is back", "x", "UPI payments are working again. If a debit did not reach the receiver, it is reversed automatically. If it has not reached you, write to grievance@paisaloop.example.", 36.2, [(0.4, "send", {}), (1, "approve", {}), (2, "publish", {})], event=down),
        pk("o-faiz", "faiz", "Who handled the outage better", "instagram", "Heard Mintfold handled the downtime better than most. Maybe they have a point. #PaisaloopPartner", 36, _back("Do not name another app, and an outage is not the moment for a comparison.", "approver"), event=down),
        # The advertising circular and fund promotions
        pk("c-note", "anika", "A note on fund posts", "linkedin", "From this month every fund promotion carries the standard risk line. " + DISCLAIMER + " We are updating every template.", 35, CLEAN, event=circ),
        pk("c-split", "vihaan", "Start a SIP from a small amount", "instagram", "Start a SIP on LoopSIP from 100 rupees a month. Small amounts, regular habit.", 34,
           [(1, "send", {}), (3, "autodecide", {"by": "reviewer"}), (4, "autodecide", {"by": "approver"}),
            (5, "comment", {"by": "approver", "body": "I am fine with this one: it is a habit message. Farida, your call on the risk line."}),
            (7, "back", {"note": "Under the circular a SIP post carries the risk line, habit message or not.", "by": "compliance"}),
            (20, "fix", {"body": "Start a SIP on LoopSIP from 100 rupees a month. Small amounts, regular habit. " + DISCLAIMER}), (21, "send", {}), (26, "approve", {}), (40, "publish", {})], event=circ),
        pk("c-chart", "dhruv", "Three years of the equity fund", "x", "Our LoopSIP equity fund has climbed through the last three years. See the chart.", 33,
           _fx("A performance chart needs the past returns warning and the risk line.", "Our LoopSIP equity fund over the last three years. Past returns are not indicative of future returns. " + DISCLAIMER), event=circ,
           images=_img("chart", "Bar chart of the LoopSIP equity fund over three years above the Paisaloop logo", _chart)),
        pk("c-fine", "growth", "Start your SIP poster", "instagram", "Start your SIP today. " + DISCLAIMER, 32,
           _fx("The risk line in the image is tiny and pale. It has to be legible: use white on violet at a readable size.", "Start your SIP today. " + DISCLAIMER + " The line is now set in white on violet."), event=circ,
           colors=[{"fg": "#9A8CD2", "bg": "#7A62CC", "where": "risk line in the poster", "large": False}],
           fix_colors=[{"fg": "#FFFFFF", "bg": "#5434BE", "where": "risk line in the poster", "large": False}],
           images=_img("fine", "Poster reading Start your SIP today, with a very small pale risk line at the foot", lambda: _poster("Start your SIP today", "Small steps, every month", "ok", figure=_phone(), fine=DISCLAIMER, fine_color=(140, 122, 214))),
           fix_images=_img("fine", "Poster reading Start your SIP today, with the risk line set in white", lambda: _poster("Start your SIP today", "Small steps, every month", "ok", figure=_phone(), fine=DISCLAIMER))),
        pk("c-oldusers", "vihaan", "Our community", "linkedin", "Paisaloop has 8 million users who pay and save from one app.", 31,
           _fx("The count is last year's: 11 million.", "Paisaloop has 11 million users who pay and save from one app.", "approver")),
        # Tax-saving season
        pk("t-first", "dhruv", "Tax-saving season is here", "linkedin", "Tax-saving season is here. ELSS funds come with a lock-in of 3 years, the shortest of any tax-saving option. #SaveTaxSmart", 29,
           _fx("Do not call it the shortest, and add the risk line.", "Tax-saving season is here. ELSS funds come with a lock-in of 3 years. Plan your investment before the financial year ends. " + DISCLAIMER + " #SaveTaxSmart"), event=tax),
        pk("t-guide", "anika", "How ELSS works", "blog", "A plain guide to ELSS: what the 3 year lock-in means, how a SIP fits in and what to check in the scheme documents. " + DISCLAIMER + " #SaveTaxSmart", 28, CLEAN, event=tax),
        pk("t-assured", "growth", "Tax email", "email", "Save tax and grow your money. Assured savings every year with ELSS, only on Paisaloop. #SaveTaxSmart", 27,
           [(0.3, "send", {}), (0.5, "escalate", {"message": "The client brief asks for 'assured savings'. Their legal team signed the line off. Please confirm we can run it.", "rule": "CLAIM-ASSURED"}),
            (7, "resolve", {"outcome": "upheld", "note": "Not allowed: ELSS is a market product and savings are never assured. Explain the lock-in and the tax section instead."}),
            (9, "back", {"note": "Remove the promise; see the escalation.", "by": "approver"}),
            (22, "fix", {"body": "Save tax with ELSS, a tax-saving mutual fund with a 3 year lock-in. " + DISCLAIMER + " #SaveTaxSmart"}), (23, "send", {}), (29, "approve", {}), (52, "publish", {})], event=tax),
        pk("t-rounds", "kriti", "Tax saving made easy", "instagram", "Tax saving made easy lol. Put your money in ELSS and it grows every month, risk free! #SaveTaxSmart", 26,
           _rounds(("Risk-free and 'grows every month' are both off. Plain words, and the risk line.", "ELSS is easy, honestly. Your money grows over time, zero risk of losing it. #SaveTaxSmart"),
                   ("Still an implied promise, and 'zero risk' is not allowed. Say what ELSS is and add the risk line.", ""),
                   "ELSS is a tax-saving mutual fund with a lock-in of 3 years. Read what it means before you start. " + DISCLAIMER + " #SaveTaxSmart"), event=tax),
        pk("t-fin", "faiz", "ELSS is the only one worth it", "youtube", "Honest take: this ELSS fund is the one I would put everything in. Buy before the weekend, I did. #SaveTaxSmart", 25,
           [(2, "send", {}), (5, "autodecide", {"by": "compliance"}),
            (8, "comment", {"by": "compliance", "body": "A creator partner may not pick a fund or tell followers to buy, and the paid partnership has to be stated. Not publishable as written."}),
            (10, "back", {"note": "No fund picks, no 'buy', and disclose the partnership. See Farida's comment.", "by": "compliance"})], event=tax),
        pk("t-hinglish", "jaspreet", "ELSS shuru karo", "instagram", "Tax bachana hai? ELSS mein SIP shuru karo, pakka returns milenge! #SaveTaxSmart", 24,
           [(1, "send", {}), (2, "dispute", {"rule": "CLAIM-ASSURED", "claim": "Here 'pakka' is just 'for sure start it', the way we say it in Punjabi-Hindi. It is encouragement, not a promised return.", "language": "Hinglish"}),
            (4, "autodecide", {"by": "compliance"}), (9, "back", {"note": "In Hinglish too: no promised returns. Say that returns depend on the market.", "by": "compliance"}),
            (24, "fix", {"body": "Tax bachana hai? ELSS mein SIP shuru karo. Returns market par depend karte hain. " + DISCLAIMER + " #SaveTaxSmart"}), (25, "send", {}), (30, "approve", {}), (50, "publish", {})],
           event=tax, notes={"language": "Hinglish", "intent": "Encourage people to start an ELSS SIP; 'pakka' is idiom for 'definitely start'."}),
        pk("t-meenal", "meenal", "Tax bachane ka plan", "instagram", "Tax bachane ka plan bana lo. ELSS ka lock-in teen saal ka hota hai. " + DISCLAIMER + " #SaveTaxSmart", 22, CLEAN, event=tax,
           notes={"language": "Hinglish"}),
        # Numbers that moved on
        pk("a-aum", "dhruv", "Assets on Paisaloop", "linkedin", "Investors hold 900 crore rupees in SIPs on Paisaloop. Join them.", 20,
           _fx("That figure is from March. The current one is 1,400 crore rupees.", "Investors hold 1,400 crore rupees in SIPs on Paisaloop. " + DISCLAIMER, "compliance")),
        pk("a-rate", "vihaan", "Rated by you", "instagram", "Rated 4.9 out of 5 by the people who use Paisaloop every day.", 19,
           _fx("The listed rating is 4.6.", "Rated 4.6 out of 5 in the app stores.", "approver")),
        pk("a-sla", "dhruv", "Payments that work", "linkedin", "UPI payments on PaisaPay succeed 100% of the time.", 17,
           _fx("The ops report says 99.2%. We cannot claim every payment succeeds.", "UPI payments on PaisaPay succeed 99.2% of the time.", "compliance")),
        pk("a-news", "anika", "Your monthly note", "email", "Your monthly note: how to read your SIP statement, what the units mean and where to see each instalment. " + DISCLAIMER + " Questions? Write to grievance@paisaloop.example.", 18, CLEAN),
        # Money, minors, KYC, fees
        pk("k-risk", "kriti", "SIPs are safe", "instagram", "SIPs are 100% safe, zero risk, just invest and relax.", 16,
           _rounds(("No 'zero risk' and no '100% safe'. A SIP does not remove market risk.", "SIPs spread your investment over time and keep your money growing every month, so relax."),
                   ("'Keeps your money growing' is still a promise.", ""), "A SIP spreads what you invest across dates, but market risk stays. " + DISCLAIMER)),
        pk("k-teen", "kriti", "Students can start too", "instagram", "School students can start a SIP with their pocket money. Class nine and up!", 15,
           _fx("Investing is for KYC-verified adults. Do not address students.", "Parents, here is a short guide to talking about long-term saving at home.", "compliance")),
        pk("k-kyc", "growth", "Sign up in a minute", "instagram", "Sign up in a minute. No KYC needed, start investing right away.", 14,
           _fx("KYC is a legal step and we cannot say it is not needed.", "Complete your KYC once, from your phone, and start from the same app.", "compliance")),
        pk("k-fee", "vihaan", "Instant withdrawals", "instagram", "Withdraw instantly, no questions asked. Zero charges, free forever.", 13,
           _fx("Say what it costs: charges are listed in the app. Never 'free forever'.", "Withdraw to your bank account from the app. Charges are listed under Charges in the app.", "compliance")),
        pk("k-human", "jaspreet", "Hinglish SIP post", "instagram", "SIP mein guaranteed returns milenge, bilkul risk free, jaldi karo!", 12,
           _fx("Guaranteed, risk free and jaldi karo all break the code, in any language.", "SIP ek aadat hai. Apni salary ke hisaab se rakam chuno. " + DISCLAIMER, "compliance"), notes={"language": "Hinglish"}),
        # Leaks and escalations
        pk("l-anchor", "growth", "Press release draft", "press release", "Paisaloop is in talks with Ridgeway Bank under Project Anchor to launch a co-branded card. A statement will follow.", 13,
           [(0.5, "send", {}), (1, "escalate", {"message": "The client asked for a holding statement in case the news leaks. Please confirm the term is fine inside a draft.", "rule": "CONF-LEAK"}),
            (6, "resolve", {"outcome": "upheld", "note": "Drafts stay in the shared doc, not here. This codename never goes in a post."})]),
        pk("l-lantern", "dhruv", "Credit is coming", "x", "Something big for credit is coming: Project Lantern puts a credit line inside PaisaPay.", 11,
           _fx("Lantern is not announced. Tease the feeling, not the product.", "A new way to manage your money is on its way. Watch this space.", "approver")),
        pk("l-contact", "dhruv", "Reach the grievance officer", "x", "Need to reach our grievance officer directly? Call +91 22 4000 1355.", 10,
           [(0.5, "send", {}), (1, "escalate", {"message": "This is the grievance officer's new direct line, issued this week. It is public but not yet in the contact list.", "rule": "CONTACT-PUBLIC"}),
            (6, "resolve", {"outcome": "cleared", "reason_code": "not_applicable", "note": "Confirmed with the grievance officer. The brand team will add the number to the register."}),
            (8, "approve", {}), (30, "publish", {})]),
        pk("l-hinglish-safety", "meenal", "UPI PIN kisi ko mat batao", "blog", "Apna UPI PIN kisi ko mat batao, na call par, na message par. Paisaloop kabhi PIN nahi maangta. Koi dikkat ho to help.paisaloop.example par likho.", 9, CLEAN, notes={"language": "Hinglish"}),
        # Partners, rivals and artwork
        pk("p-bank", "anika", "Paisaloop and Harbourline Bank", "linkedin", "PaisaPay now works with Harbourline Bank accounts, so you can link your account and start paying from your phone. Setup takes a few minutes.", 10, [(1, "send", {}), (4, "approve", {}), (24, "publish", {})],
           images=_img("bank", "Paisaloop and Harbourline Bank logos side by side", _partner_card)),
        pk("p-compare", "growth", "Which app pays you back", "instagram", "We put the two big names side by side. Swipe to see who pays you back sooner.", 9,
           _back("A rival's logo in a comparison graphic is a no. Show our own product.", "approver"),
           images=_img("cmp", "Comparison graphic with the Paisaloop logo and a rival app's logo", _compare)),
        pk("p-old", "kriti", "Merchant sticker poster", "instagram", "Pay with PaisaPay at your favourite shops. Look for the sticker at the counter.", 8.5,
           _fx("That is the 2024 logo. Use the current lockup.", "Pay with PaisaPay at your favourite shops. Look for the new sticker at the counter.", "approver"),
           images=_img("old", "Merchant poster with the old Paisaloop logo", lambda: _poster("Pay here with PaisaPay", "Look for the sticker", "old", figure=_phone())),
           fix_images=_img("old", "Merchant poster with the Paisaloop logo", lambda: _poster("Pay here with PaisaPay", "Look for the sticker", "ok", figure=_phone()))),
        pk("p-stretch", "growth", "Banner for the festive launch", "instagram", "A festive banner for the new app home screen. #PaisaloopFestive", 7.5,
           _fx("The logo is stretched. Use the registered lockup at its own proportions.", "A festive banner for the new app home screen. Logo corrected. #PaisaloopFestive", "approver"), event=fest,
           images=_img("banner", "Festive banner reading Everything in one view with a wide Paisaloop logo", lambda: _poster("Everything in one view", "Festive week", "stretched", figure=_phone())),
           fix_images=_img("banner", "Festive banner reading Everything in one view with the Paisaloop logo", lambda: _poster("Everything in one view", "Festive week", "ok", figure=_phone()))),
        pk("p-card", "anika", "Meet LoopCard", "instagram", "Meet LoopCard, the debit card that lives in your app. Freeze it, unfreeze it and pay with a tap.", 7, CLEAN,
           images=_img("card", "LoopCard debit card above the Paisaloop logo", _card_post)),
        pk("p-cardwide", "growth", "LoopCard stretched", "instagram", "LoopCard comes in violet and mint. Pay with a tap, anywhere you see the contactless sign.", 6.2, [(1, "send", {})],
           images=_img("cardw", "A wide LoopCard debit card above the Paisaloop logo", lambda: _card_post(stretched=True))),
        pk("p-recolour", "dhruv", "Festive colours", "instagram", "Festive week on PaisaPay. #PaisaloopFestive", 2.4, [(1, "send", {})], event=fest,
           images=_img("rec", "Festive poster reading Everything in one view with a recoloured Paisaloop logo", lambda: _poster("Everything in one view", "Festive week", "recolour", figure=_phone()))),
        pk("p-rival", "growth", "Switch and see", "instagram", "Which one feels better to pay with? Swipe and tell us.", 5,
           [(1, "send", {})], images=_img("rival", "Poster with the Paisaloop logo and another app's mark", lambda: _poster("Which feels better to pay with?", "", "rival", figure=None))),
        pk("p-star", "anika", "Aarav on festive payments", "instagram", "Aarav Khanna pays his festive bills on PaisaPay. Terms apply, see the offer page in the app. #PaisaloopFestive", 4, [(1, "send", {}), (4, "approve", {}), (26, "publish", {})], event=fest,
           images=_img("aarav", "Aarav Khanna smiling in a violet jacket above the Paisaloop logo", lambda: _star("Aarav", "Festive payments"))),
        pk("p-star2", "meenal", "Aarav on LinkedIn", "linkedin", "Aarav Khanna and the festive cashback week on PaisaPay. #PaisaloopFestive", 3.4,
           [(2, "send", {}), (5, "autodecide", {"by": "reviewer"}), (8, "back", {"note": "Aarav's agreement covers Instagram and YouTube only, not LinkedIn. Take it down or ask the brand team.", "by": "approver"})], event=fest,
           images=_img("aarav2", "Aarav Khanna in a studio next to the festive offer", lambda: _star("Aarav", "Festive offer"))),
        # The festive week
        pk("f-clean", "anika", "Festive week on PaisaPay", "instagram", "Festive week on PaisaPay: up to 150 rupees cashback on a bill payment until Sunday. Terms apply, see the offer page in the app. #PaisaloopFestive", 2.9, [(1, "send", {})], event=fest),
        pk("f-push", "vihaan", "Festive push", "push", "Festive cashback is live. Pay a bill, see your reward. Terms apply.", 2.7, [(0.5, "send", {}), (2, "approve", {}), (3, "publish", {})]),
        pk("f-free", "kriti", "Unlimited cashback", "instagram", "UNLIMITED cashback on EVERYTHING 🤑💸 festive dhamaka, free money!!! #PaisaloopFestive", 2.5, [(1, "send", {})], event=fest),
        pk("f-cap", "dhruv", "Festive cashback", "x", "Festive cashback of up to 250 rupees on a bill payment this week. Terms apply, see the app. #PaisaloopFestive", 2.2, [(1, "send", {}), (3, "autodecide", {"by": "compliance"})], event=fest),
        pk("f-hinglish", "jaspreet", "Diwali par bills", "instagram", "Is Diwali par bills bharo aur cashback pao. Cap aur terms app mein dekho. #PaisaloopFestive", 2.0, [(1, "send", {}), (3, "autodecide", {"by": "approver"})], event=fest, notes={"language": "Hinglish"}),
        pk("f-link", "faiz", "Festive cashback explained", "youtube", "My festive routine: pay bills, set the SIP, [click here](https://paisaloop.example/festive) for the offer. Paid partnership with Paisaloop, not investment advice. #PaisaloopFestive", 1.6,
           [(1, "send", {}), (3, "autodecide", {"by": "reviewer"})], event=fest),
        pk("f-partner", "faiz", "How I track my SIPs", "instagram", "I use Paisaloop to keep my SIPs and my UPI bills in one app. This is a paid partnership with Paisaloop, not investment advice. " + DISCLAIMER + " #PaisaloopPartner", 4.5, [(1, "send", {}), (5, "approve", {}), (30, "publish", {})]),
        # The Compass launch under embargo
        pk("x-leak", "growth", "Compass announcement", "email", "Project Compass opens for SIPs from 500 rupees a month. Be among the first to join.", 1.4,
           [(0.3, "send", {}), (0.6, "escalate", {"message": "The fund house told us the launch date is public. Please confirm we can name the fund in this email.", "rule": "CONF-LEAK"}),
            (5, "resolve", {"outcome": "upheld", "note": "The date is public only from launch day. Until then no codename, no minimum and no dates."})], event=comp),
        pk("x-tease", "anika", "Something new for LoopSIP", "instagram", "A new chapter is coming to LoopSIP. Stay tuned for the news. #NewFundSoon", 1.1, [(1, "send", {})], event=comp),
        pk("x-lp", "anika", "App store listing refresh", "app store", "Pay bills, send money with UPI and start a SIP, all in one app. PaisaPay supports UPI payments of up to 1 lakh rupees a day. Rated 4.6 out of 5 in the app stores.", 0.9, CLEAN,
           images=_img("lp", "PaisaPay home screen with balance, recent payments and a Pay button", lambda: _screen_post())),
        pk("x-draft", "kriti", "Draft: festive reel", "instagram", "Rough idea for a festive reel. Not ready yet.", 0.6, []),
        pk("x-withdraw", "vihaan", "Old cashback idea", "x", "Cashback of up to 75 rupees on a bill payment, today only.", 6.5, [(1, "send", {}), (4, "back", {"note": "That offer ended in the monsoon week. Withdraw it.", "by": "approver"}), (8, "withdraw", {})]),
        pk("x-apply", "meenal", "Account email", "email", "Login to your Paisapay account and check your e-mail for the new statement.", 5.5,
           [(1, "send", {}), (3, "autodecide", {"by": "reviewer"}), (6, "back", {"note": "House words and the product spelling: sign in, email, PaisaPay.", "by": "reviewer"}), (8, "applyfix", {}), (9, "send", {}), (14, "approve", {}), (30, "publish", {})]),
    ]


# Reviewers' calls on first-round findings of the scripted stories, so guideline health has a record to read.
DECISIONS = [
    ("m-hype", 2, "LEGAL-CASHBACK", "approver", "rejected", "guideline_unclear",
     "Does the cap need to be in the post, or is the offer page enough?"),
    ("m-hype", 2, "LEGAL-CASHBACK", "compliance", "accepted", None, None),
    ("c-split", 2, "LEGAL-MFDISC", "reviewer", "rejected", "not_applicable", "A habit message, no fund is named as a pick."),
    ("c-split", 2, "LEGAL-MFDISC", "compliance", "accepted", None, None),
    ("c-chart", 2, "LEGAL-PAST", "reviewer", "rejected", "false_positive", "The chart shows no number, only bars."),
    ("c-chart", 2, "LEGAL-PAST", "compliance", "accepted", None, None),
    ("t-first", 2, "LEGAL-MFDISC", "approver", "rejected", "intentional", "A tax explainer, the risk line is on the landing page."),
    ("t-first", 2, "LEGAL-MFDISC", "compliance", "accepted", None, None),
    ("t-rounds", 2, "CLAIM-IMPLIED", "reviewer", "rejected", "guideline_unclear", "Does 'grows' imply a return? It is a saving line."),
    ("t-rounds", 2, "CLAIM-IMPLIED", "compliance", "accepted", None, None),
    ("t-hinglish", 2, "CLAIM-ASSURED", "compliance", "accepted", None, None),
    ("p-compare", 2, "MSG-COMPETITOR", "approver", "accepted", None, None),
    ("o-faiz", 2, "MSG-COMPETITOR", "approver", "accepted", None, None),
    ("o-faiz", 2, "CLAIM-UNSUPPORTED", "reviewer", "rejected", "not_applicable", "Hearsay about another app, not a claim about us; the competitor rule covers it."),
    ("k-fee", 2, "LEGAL-FEES", "reviewer", "accepted", None, None),
    ("k-fee", 2, "LEGAL-FEES", "approver", "rejected", "guideline_unclear", "Is 'no questions asked' a fee claim, or only a tone?"),
    ("t-fin", 3, "LEGAL-FINFLUENCER", "reviewer", "accepted", None, None),
    ("k-risk", 2, "CLAIM-UNSUPPORTED", "approver", "accepted", None, None),
    ("m-film", 2, "LEGAL-CASHBACK", "reviewer", "accepted", None, None),
]


# --- routine work: banks per persona ---------------------------------------------------------------------

CLEAN_BANK = [
    ("Monday SIP habit", "instagram", "A SIP is a habit before it is an investment. Pick an amount you can keep up every month and let it run on its own. " + DISCLAIMER),
    ("Pay a bill, skip the queue", "x", "Electricity, water, broadband. Pay all your bills from one place on PaisaPay and see each payment's status as it happens."),
    ("UPI limits explained", "blog", "Wondering how much you can send? PaisaPay supports UPI payments of up to 1 lakh rupees a day. This guide explains daily limits, how they reset and what to do if a payment is held."),
    ("Safety note", "x", "Your UPI PIN is yours alone. Paisaloop will never ask you for it on a call, a message or an email."),
    ("KYC in a few steps", "linkedin", "Complete your KYC once, from your phone, and you can pay bills and start a SIP from the same app."),
    ("Reading your SIP statement", "email", "Your monthly SIP statement lists every instalment, the units you hold and the date of each purchase. Open it in the app under Investments. " + DISCLAIMER),
    ("Split bills with friends", "instagram", "The trip is over, the bill is not. Split it on PaisaPay and send each friend a request in a tap."),
    ("Grievance route", "linkedin", "If a payment goes wrong, write to grievance@paisaloop.example. We acknowledge every complaint within 24 hours."),
    ("SIP minimum", "x", "SIPs on Paisaloop start at 100 rupees a month. Choose a date that follows your salary and let it run. " + DISCLAIMER),
    ("Rent payments", "instagram", "Pay rent from the same app you use for bills. Add your landlord once and schedule it for the day you choose."),
    ("ELSS plain guide", "blog", "ELSS funds are tax-saving mutual funds with a lock-in of 3 years. This guide explains what the lock-in means, how a SIP fits in and what to check in the scheme documents. " + DISCLAIMER),
    ("Bill day in Hinglish", "instagram", "Bill ka din ho ya recharge ka, PaisaPay se ek hi jagah pay karo. Har payment ka status live dikhta hai."),
    ("SIP aadat", "instagram", "SIP ek aadat hai. Apni salary ke hisaab se rakam chuno aur har mahine chalne do. " + DISCLAIMER),
    ("App update", "x", "Our latest update makes the payment screen easier to read in bright light and adds a larger text option. Update from your app store."),
    ("Stuck payment", "whatsapp", "Hello, if a payment is stuck, open Help in the app and share the payment reference. You can also write to grievance@paisaloop.example."),
    ("Why we ask for KYC", "blog", "KYC helps keep your money and ours safe. It confirms who you are before you invest or move larger amounts, and it is a one-time step."),
    ("Budget week", "linkedin", "This week on the blog: how to plan a month of spending in one view, and how a SIP can sit beside it."),
    ("Card freeze", "instagram", "Lost your LoopCard? Freeze it in the app in a tap and unfreeze it when you find it. Your card details stay hidden unless you reveal them."),
    ("Accessibility note", "blog", "Every screen in the Paisaloop app supports larger text and screen readers, and every image in our guides has a description. Let the support desk know about any gap."),
    ("Salary day plan", "instagram", "Salary day plan: pay the bills, set the SIP, keep something aside. Small, regular steps do the work."),
    ("Understanding charges", "blog", "Our charges are listed in the app under Charges, next to every service. UPI transfers between people carry no fee on PaisaPay."),
    ("Shop QR", "x", "Run a small shop? Show your PaisaPay QR at the counter and see every payment in one place."),
    ("Scam alert", "instagram", "Someone asks you to scan a QR to receive money? You never need to scan to receive. Stop and tell us at help.paisaloop.example."),
    ("Mutual fund basics", "youtube", "In this video our educator explains what a mutual fund is, what a SIP does and why the scheme documents matter. Chapters are listed below and a transcript is in the help centre. " + DISCLAIMER),
    ("Family transfers", "email", "Send a transfer to your family in a tap and add a note so everyone knows what it was for. Transfers between people carry no fee."),
    ("Weekend reading", "linkedin", "Weekend reading: a short guide to building an emergency fund before you start a SIP."),
    ("Support hours", "x", "Need help? Our support team is on +91 22 4000 1200. You can also write to us at help.paisaloop.example."),
    ("Bank link", "instagram", "Link your bank account once and pay with UPI from your phone. Add more accounts any time from settings."),
    ("Bill reminders", "push", "Your electricity bill is due soon. Pay it on PaisaPay and see the status as it happens."),
    ("Data promise", "linkedin", "We ask for the details we need and nothing more. We do not sell your data, and you can delete your account any time from settings."),
    ("Festive shopping tip", "x", "Festive shopping tip: check the name on the QR before you pay, and never share your UPI PIN."),
]

_VOICE = "Keep our calm, plain voice about money: no slang, no hype, no pressure."
SLIPS = {
    "intern": [
        Slip("Monday motivation", "x", "Mondays are for SIPs lol. Stop being broke bro, start investing!!",
             "Mondays are a good day to set up a SIP. Start small and stay regular. " + DISCLAIMER, _VOICE),
        Slip("Money grows", "instagram", "Put money in a SIP and it grows every month. Easy!",
             "A SIP lets you invest a fixed amount every month. " + DISCLAIMER, "No implied growth, and add the risk line."),
        Slip("Cashback blast", "instagram", "Cashback on every payment today 🤑🚀",
             "Cashback on a bill payment this festive week. Terms apply, see the offer page in the app.", "Cashback needs its terms; no money emoji."),
        Slip("Rush", "x", "Hurry!! Last chance to start your SIP, act now!!!",
             "Start your SIP when you are ready. Pick an amount you can keep up every month.", "No pressure to invest."),
        Slip("Rival jab", "instagram", "Mintfold is slow, we are faster.", "PaisaPay shows the status of every payment as it happens.",
             "Never name another app."),
        Slip("Free forever", "instagram", "Zero charges on everything, free forever!",
             "UPI transfers between people carry no fee on PaisaPay. Other charges are listed in the app.", "Say what is free and what costs."),
        Slip("Safe SIP", "x", "SIPs are risk-free, just invest and relax.",
             "SIPs spread your investment over time but do not remove market risk. " + DISCLAIMER, "Nothing is risk-free."),
    ],
    "agency": [
        Slip("Assured film", "youtube", "Assured returns on every SIP. Start today with Paisaloop.",
             "Our film follows three neighbours as they set up a first plan on their phones. " + DISCLAIMER, "We never assure returns."),
        Slip("Zero risk", "instagram", "Zero risk, high growth: the smart way to invest.",
             "A SIP is one way to invest regularly. " + DISCLAIMER, "No zero risk, no growth promise."),
        Slip("Past returns ad", "instagram", "Our equity fund turned every month of saving into a bigger pot over the last few years. See the factsheet.",
             "Past returns are not indicative of future returns. See the factsheet for the full record. " + DISCLAIMER, "Past returns need their warning."),
        Slip("Beat the rival", "linkedin", "Better than Mintfold, every single day.", "Pay bills, set a SIP and track both in one app.",
             "Never name another app."),
        Slip("No KYC", "instagram", "No KYC needed, start investing in a minute.", "Complete your KYC once and start investing from your phone.",
             "KYC is a legal step."),
        Slip("Jargon", "linkedin", "We leverage best-in-class fintech rails to monetise financial inclusion at scale.",
             "PaisaPay helps people pay bills and save from one app.", "Write like a steady friend, not a pitch deck."),
        Slip("Double it", "instagram", "Double your money with LoopSIP.", "Start a SIP with LoopSIP. " + DISCLAIMER, "No promise of doubling."),
    ],
    "marketer": [
        Slip("Old user count", "linkedin", "Over 15 million users trust Paisaloop.", "Paisaloop has 11 million users who pay bills and save from one app.", "The count is 11 million."),
        Slip("Old assets", "linkedin", "Investors hold 900 crore rupees in SIPs on Paisaloop.",
             "Investors hold 1,400 crore rupees in SIPs on Paisaloop. " + DISCLAIMER, "That figure is from March."),
        Slip("Success rate", "x", "UPI payments on PaisaPay succeed 100% of the time.", "UPI payments on PaisaPay succeed 99.2% of the time.",
             "The ops figure is 99.2%."),
        Slip("Rating", "instagram", "Rated 4.9 out of 5 by our users.", "Rated 4.6 out of 5 in the app stores.", "The listed rating is 4.6."),
        Slip("Old cashback", "x", "Get up to 75 rupees cashback on a bill payment this week. Terms apply.",
             "Get up to 150 rupees cashback on a bill payment until Sunday. Terms apply, see the offer page in the app.", "That cashback ended."),
        Slip("Small SIP", "instagram", "Begin investing with just 10 rupees a month. " + DISCLAIMER, "Begin investing with just 100 rupees a month. " + DISCLAIMER,
             "SIPs start at 100 rupees."),
        Slip("Daily limit", "blog", "Send up to 5 lakh rupees a day on PaisaPay.", "Send up to 1 lakh rupees a day on PaisaPay.",
             "The daily UPI limit is 1 lakh."),
    ],
    "influencer": [
        Slip("Fund pick", "instagram", "This is the fund I would put everything in right now. Buy before Friday. #PaisaloopPartner",
             "I track my SIPs on Paisaloop. Paid partnership, not investment advice. " + DISCLAIMER + " #PaisaloopPartner",
             "No fund picks, disclose the partnership."),
        Slip("Guaranteed", "instagram", "My SIP gave me guaranteed returns, you will not lose. #PaisaloopPartner",
             "My SIP habit keeps me regular. Paid partnership, not advice. " + DISCLAIMER + " #PaisaloopPartner", "No guaranteed returns."),
        Slip("Switched apps", "instagram", "Switched from Mintfold to Paisaloop, way better. #PaisaloopPartner",
             "I use Paisaloop to pay bills and track my SIPs. Paid partnership, not advice. #PaisaloopPartner", "Never name another app."),
        Slip("Hinglish hype", "instagram", "Bhai paisa double ho jayega, risk free hai, SIP lo abhi! #PaisaloopPartner",
             "SIP ek aadat hai, bhai. Paid partnership, advice nahi. " + DISCLAIMER + " #PaisaloopPartner", _VOICE),
        Slip("Call me", "instagram", "Questions on SIPs? WhatsApp me on 00000 12345 for my tips. #PaisaloopPartner",
             "Questions? Write to help.paisaloop.example. Paid partnership, not advice. #PaisaloopPartner", "Only the company's numbers in posts."),
        Slip("Offer link", "youtube", "Grab the offer here: [click here](https://paisaloop.example/offer)",
             "Grab the offer here: [festive offer details](https://paisaloop.example/offer)", "Link text must say where it goes."),
    ],
    "regional": [
        Slip("Hinglish guarantee", "instagram", "SIP mein guaranteed returns milenge, pakka!",
             "SIP ek aadat hai. Rakam chuno aur har mahine chalne do. " + DISCLAIMER, "No promised returns, in any language."),
        Slip("Name casing", "instagram", "Paisapay pe ab Loopsip shuru karo.", "PaisaPay pe ab LoopSIP shuru karo. " + DISCLAIMER, "Our names are PaisaPay and LoopSIP."),
        Slip("Hindi urgency", "instagram", "Jaldi karo, last chance cashback ka!", "Cashback ka last din Sunday hai. Terms app mein dekho.", "No pressure."),
        Slip("House words", "email", "Login karo aur e-mail verify karo.", "Sign in karo aur email verify karo.", "House words: sign in, email."),
        Slip("Hindi risk free", "instagram", "Bilkul risk free, paisa safe. Paisaloop se SIP karo.", "Paisaloop se SIP karo. " + DISCLAIMER,
             "Nothing is risk-free."),
        Slip("Customer word", "whatsapp", "Hello customer, your statement is ready in the app.", "Hello, your statement is ready in the app.", "House word: user."),
    ],
    "careful": [
        Slip("Playlist link", "linkedin", "Money basics playlist: [click here](https://paisaloop.example/playlist) for the list.",
             "Money basics playlist: [open the full playlist](https://paisaloop.example/playlist).", "Link text must say where it goes."),
        Slip("Customer note", "email", "Our customers can now freeze a LoopCard in the app.", "Our users can now freeze a LoopCard in the app.", "House word: user."),
    ],
}


ADMIN_LOG = [
    (40, "patch_rule", {"code": "MSG-FAIRCOMP", "patch": {
        "text": "Never compare us with other apps by name or by hint. A hint counts when the sentence clearly points "
                "at a rival; a comparison needs a dated, published source and legal sign-off.",
        "bad_examples": ["Unlike other payment apps, our payments never fail", "Other apps hide their charges",
                         "Not like those slow apps"]}}),
    (22, "new_fact", {"key": "banks", "statement": "Paisaloop supports UPI payments with 9 partner banks", "value": 9,
                      "unit": "banks", "subject": "partner banks", "source_ref": "Partnerships report, September 2026",
                      "from": -22}),
    (14, "patch_rule", {"code": "LEGAL-CASHBACK", "patch": {
        "text": "Cashback and rewards state the most a user can earn and the last day in the post itself. The full "
                "terms may sit one tap away in the app.",
        "bad_examples": ["Cashback on every payment, no strings attached", "Earn rewards on everything you buy this week",
                         "Huge rewards whatever you buy, limitless"]}}),
]


def build() -> Company:
    def pieces() -> list[Piece]:
        out = _stories() + routine("paisaloop", CREATORS, CLEAN_BANK, SLIPS, 53, 0.4, rate=0.035)
        keys = [p.key for p in out]
        assert len(keys) == len(set(keys)), "duplicate piece keys"
        return out

    return Company(
        key="paisaloop", brand=BRAND, industry="Fintech: UPI payments, a debit card and SIP investing in one app",
        domain="paisaloop.example", days=54, team=TEAM, creators=CREATORS, rules=RULES, facts=FACTS, terms=TERMS,
        contacts=CONTACTS, assets=ARTWORK, events=EVENTS, people=PEOPLE, pieces=pieces, decisions=DECISIONS,
        stance=STANCE, admin_log=ADMIN_LOG, demo=DEMO)
