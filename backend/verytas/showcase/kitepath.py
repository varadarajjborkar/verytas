"""Kitepath: an Indian edtech app (courses, mentors, a tutor app called KiteLearn). Its mascot Kit is one of many
brand entities: logo lockup, wordmark, app icon, reversed and retired marks, a pattern, the learning-kit box,
a co-brand partner and a competitor. The regulatory pressure is exam-result and coaching-ad rules, so claims
about marks, ranks, placements and "free" are what the team polices hardest."""

from __future__ import annotations

from verytas.showcase import art
from verytas.showcase.art import b64 as _b64
from verytas.showcase.art import font as _font
from verytas.showcase.gen import Slip, routine
from verytas.showcase.spec import CLEAN, Company, Member, Piece, fixed

BLUE, ORANGE, YELLOW, CREAM, NAVY = (26, 95, 209), (240, 130, 40), (250, 200, 40), (250, 247, 238), (25, 35, 60)
BRAND = "Kitepath"
ORDER = ["rohan", "priya", "dev", "aisha", "kabir", "neha", "studio9", "zoya", "karthik", "ishita"]

# --- artwork -----------------------------------------------------------------------------------------
# Kit the kite mascot is the one character; everything else here is the rest of the brand system.

def _kit(eye=(25, 35, 60), tail=(240, 130, 40), size=400):
    """Kit, the mascot: a kite with a face, stripes and a bow-tied tail, detailed enough to be matched."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(200, 20), (370, 190), (200, 360), (30, 190)], fill=(26, 95, 209, 255))
    d.polygon([(200, 20), (370, 190), (200, 190)], fill=(64, 140, 235, 255))
    d.polygon([(30, 190), (200, 190), (200, 360)], fill=(18, 70, 160, 255))
    d.line([(200, 20), (200, 360)], fill=(250, 250, 250, 255), width=5)
    d.line([(30, 190), (370, 190)], fill=(250, 250, 250, 255), width=5)
    for cx in (150, 250):
        d.ellipse((cx - 30, 120, cx + 30, 180), fill="white")
        d.ellipse((cx - 14, 136, cx + 14, 168), fill=eye)
        d.ellipse((cx - 6, 140, cx + 2, 150), fill="white")
    d.arc((165, 205, 235, 255), 10, 170, fill=(250, 200, 40, 255), width=6)
    for i, y in enumerate(range(300, 400, 24)):
        x = 200 + (12 if i % 2 else -12)
        d.polygon([(x - 14, y), (x + 14, y + 10), (x - 14, y + 20)], fill=tail + (255,))
    return img


def _scene(mascot, caption: str):
    from PIL import Image, ImageDraw

    s = Image.new("RGB", (1000, 800), (250, 247, 238))
    d = ImageDraw.Draw(s)
    m = mascot.resize((300, 300), Image.LANCZOS)
    s.paste(m, (350, 140), m)
    d.text((60, 640), caption, fill=(30, 30, 30), font=_font(40))
    return s


def _wordmark(text: str, size=(520, 150), line: str | None = None):
    from PIL import Image, ImageDraw

    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    d.text((28, 36), text, fill=(26, 95, 209), font=_font(72 if line is None else 110))
    if line:
        d.text((34, 200), line, fill=(40, 40, 40), font=_font(48))
    return img



def _mark(size=400, c1=BLUE, c2=(64, 140, 235), tail=ORANGE):
    """The kite emblem used in the logo: Kit without the face."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size / 400
    d.polygon([(200 * s, 20 * s), (370 * s, 190 * s), (200 * s, 330 * s), (30 * s, 190 * s)], fill=c1 + (255,))
    d.polygon([(200 * s, 20 * s), (370 * s, 190 * s), (200 * s, 190 * s)], fill=c2 + (255,))
    d.line([(200 * s, 20 * s), (200 * s, 330 * s)], fill=(250, 250, 250, 255), width=max(2, round(5 * s)))
    d.line([(30 * s, 190 * s), (370 * s, 190 * s)], fill=(250, 250, 250, 255), width=max(2, round(5 * s)))
    for i, y in enumerate(range(335, 395, 20)):
        x = 200 + (10 if i % 2 else -10)
        d.polygon([((x - 12) * s, y * s), ((x + 12) * s, (y + 8) * s), ((x - 12) * s, (y + 16) * s)], fill=tail + (255,))
    return img


def _lockup(color=BLUE, mark=None):
    return art.lockup(mark or _mark(), "Kitepath", color)


def _old_logo():
    """The 2024 logo: a navy roundel with a yellow kite, the name set in capitals underneath."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (420, 420), "white")
    d = ImageDraw.Draw(img)
    d.ellipse((60, 10, 360, 310), fill=(18, 40, 100))
    d.ellipse((80, 30, 340, 290), outline=(250, 200, 40), width=6)
    d.polygon([(210, 60), (290, 160), (210, 260), (130, 160)], fill=(250, 200, 40))
    d.polygon([(210, 60), (290, 160), (210, 160)], fill=(255, 230, 120))
    d.line([(210, 260), (190, 290), (220, 305)], fill=(250, 200, 40), width=5)
    d.text((38, 335), "KITEPATH", fill=(18, 40, 100), font=art.font(66))
    return img


def _app_icon():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, 511, 511), radius=112, fill=BLUE + (255,))
    m = _mark(360, c1=(255, 255, 255), c2=(210, 226, 250), tail=ORANGE)
    img.paste(m, (76, 56), m)
    return img


def _kl_icon():
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (512, 512), (0, 0, 0, 0))
    ImageDraw.Draw(img).rounded_rectangle((0, 0, 511, 511), radius=112, fill=(20, 150, 140, 255))
    e = art.emblem("loop", 340, (255, 255, 255), (255, 214, 120), ORANGE)
    img.paste(e, (86, 86), e)
    return img


def _box():
    """The learning-kit box, drawn in three faces so it reads as an object and not as a flat rectangle."""
    from PIL import Image, ImageDraw

    img = Image.new("RGBA", (560, 520), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.polygon([(40, 150), (360, 150), (360, 470), (40, 470)], fill=(30, 120, 110, 255))
    d.polygon([(360, 150), (520, 90), (520, 410), (360, 470)], fill=(20, 85, 80, 255))
    d.polygon([(40, 150), (200, 90), (520, 90), (360, 150)], fill=(60, 160, 150, 255))
    d.rectangle((70, 300, 330, 380), fill=ORANGE + (255,))
    d.text((84, 175), "Learning", fill=(255, 255, 255, 255), font=art.font(56))
    d.text((84, 235), "kit", fill=(255, 255, 255, 255), font=art.font(56))
    d.text((84, 322), "for scholars", fill=(255, 255, 255, 255), font=art.font(34))
    for i in range(5):
        d.ellipse((390 + i * 16, 150 + i * 6, 402 + i * 16, 162 + i * 6), fill=YELLOW + (255,))
    return img


def _competitor():
    """A rival's mark: a red hexagon with a bolt. Name is set beside it in content, not inside the mark."""
    from PIL import ImageDraw

    img = art.emblem("hex", 300, (200, 40, 50), (150, 25, 40), (255, 200, 60))
    d = ImageDraw.Draw(img)
    d.polygon([(165, 70), (110, 160), (150, 160), (125, 235), (200, 135), (160, 135)], fill=(255, 255, 255, 255))
    return img


def _partner():
    return art.emblem("sun", 300, (30, 140, 90), (20, 100, 70), (250, 220, 120))


ARTWORK = [
    {"name": "Kit", "kind": "mascot", "part": "full", "image": lambda: _kit(),
     "notes": "Our mascot. Always blue, with the orange tail. Never redrawn or recoloured."},
    {"name": "Kitepath wordmark", "kind": "wordmark", "part": "wordmark", "wordmark": "Kitepath",
     "image": lambda: _wordmark("Kitepath"), "notes": "Brand book 2026, p.2. Always Kitepath, never KitePath."},
    {"name": "Kitepath logo", "kind": "logo", "wordmark": "Kitepath", "image": lambda: _lockup().convert("RGBA"),
     "notes": "Primary lockup: kite emblem left of the name. Clear space of one emblem width. Brand book 2026, p.4."},
    {"name": "Kitepath logo, reversed", "kind": "logo", "wordmark": "Kitepath",
     "image": lambda: art.on_color(_lockup((255, 255, 255), _mark(c1=(255, 255, 255), c2=(210, 226, 250))), BLUE, 30),
     "notes": "White on brand blue, for posters and video end cards. Brand book 2026, p.5."},
    {"name": "Kitepath app icon", "kind": "icon", "part": "icon", "image": _app_icon,
     "notes": "Store listings and the home screen. Never stretched into a banner."},
    {"name": "KiteLearn app icon", "kind": "icon", "part": "icon", "wordmark": "KiteLearn",
     "image": _kl_icon, "notes": "The tutor app's icon: a white loop on teal. Spell the name KiteLearn."},
    {"name": "Kitepath logo 2024", "kind": "logo", "retired": True, "wordmark": "KITEPATH",
     "image": _old_logo, "notes": "Retired in January 2026 with the rebrand. Still found on old decks and partner sites."},
    {"name": "Kite stripes", "kind": "pattern",
     "image": lambda: art.pattern("chevron", 600, CREAM, BLUE, ORANGE), "notes": "Backgrounds for print and event stages."},
    {"name": "Learning kit box", "kind": "packaging",
     "image": _box, "notes": "The box mailed to scholarship learners."},
    {"name": "Nalanda Foundation", "kind": "partner", "wordmark": "Nalanda Foundation",
     "image": _partner,
     "notes": "Scholarship partner. Shown at equal height beside ours, never inside our logo's clear space."},
    {"name": "SkillSprint", "kind": "competitor", "wordmark": "SkillSprint", "image": _competitor,
     "notes": "A rival platform. Its mark must not appear in our content."},
]


# --- the library ---------------------------------------------------------------------------------------

def _r(code, category, kind, severity, title, text, pattern=None, bad=None, good=None, ref=None):
    return {"code": code, "category": category, "kind": kind, "severity": severity, "title": title, "text": text,
            "pattern": pattern or {}, "bad_examples": bad or [], "good_examples": good or [], "source_ref": ref}


RULES = [
    _r("TONE-PLAIN", "tone", "semantic", "should", "Plain, warm words",
       "Write like a good teacher: plain, warm and specific. No corporate jargon or hype.",
       bad=["Leverage synergies to unlock learning paradigms"],
       good=["Learn Python in six weeks, one evening at a time"], ref="Brand book 2026, p.6"),
    _r("TONE-URGENCY", "tone", "deterministic", "should", "No countdown pressure",
       "Learning is not a flash sale. Say when an offer ends; do not shout or rush learners and parents.",
       {"type": "banned_terms", "terms": ["hurry", "last chance", "don't miss out", "limited seats", "act now",
                                          "only today"]}, ref="Brand book 2026, p.7"),
    _r("TONE-VOICE", "tone", "semantic", "may", "Sounds like a mentor",
       "Reads like a mentor talking to one learner: second person, concrete, never talking down.",
       {"type": "voice_score", "levels": ["distant and corporate", "neutral", "a warm, plain-speaking mentor"],
        "min_level": 1}, ref="Brand book 2026, p.6"),
    _r("TERM-HOUSE", "terminology", "deterministic", "should", "House spellings",
       "Use our house spellings.",
       {"type": "preferred_terms", "map": {"login": "sign in", "e-mail": "email", "webinar": "live class",
                                           "students": "learners", "e-learning": "online learning"}},
       ref="Brand book 2026, p.9"),
    _r("TERM-NAME", "terminology", "deterministic", "must", "Our names, spelled our way",
       "Write Kitepath, KiteLearn, KiteStreak and KiteMentor exactly like this.",
       {"type": "casing", "terms": ["Kitepath", "KiteLearn", "KiteStreak", "KiteMentor"]}, ref="Brand book 2026, p.3"),
    _r("MSG-COMPETITOR", "messaging", "deterministic", "must", "Never name another platform",
       "Do not name competing platforms, even to say we are different. Talk about what we do.",
       {"type": "banned_terms", "terms": ["SkillSprint", "Brainwave Academy"]}, ref="Brand book 2026, p.11"),
    _r("MSG-RIVALS", "messaging", "semantic", "must", "No digs at other platforms",
       "Talk about what we do. Never mock or compare against other learning platforms, by name or by hint.",
       bad=["Unlike some other apps, we actually teach", "Other apps just show videos"],
       good=["We teach by doing: practice, feedback and a mentor"], ref="Brand book 2026, p.11"),
    _r("MSG-INCLUSIVE", "messaging", "semantic", "should", "Every learner, every city",
       "Do not assume a learner's gender, city, language or income, and never suggest some people are born "
       "better at a subject.", bad=["Maths is hard for girls but we make it easy", "Real toppers do not need sleep"],
       good=["Maths is learnable by everyone, one step at a time"], ref="Brand book 2026, p.13"),
    _r("MSG-EXAMSTRESS", "messaging", "semantic", "must", "Never shame or scare about marks",
       "Do not threaten learners or parents with failure, backbenchers or lost years. Exams are stressful enough.",
       bad=["Do not be a failure this board season", "Backbenchers will never crack this"],
       good=["Revise a little every day and ask a mentor when you are stuck"], ref="Child-safety note C-3"),
    _r("CLAIM-PROMISE", "claims", "deterministic", "must", "No guaranteed outcomes",
       "We never promise jobs, marks, ranks or selection. Say what the course teaches.",
       {"type": "banned_terms", "terms": ["guaranteed job", "100% placement", "guaranteed results", "guaranteed marks",
                                          "guaranteed selection", "guaranteed rank", "sure shot"]},
       ref="Legal note L-14; Consumer Protection (Coaching) guidelines"),
    _r("CLAIM-RANK", "claims", "deterministic", "must", "No self-declared rankings",
       "We do not call ourselves number one, the best or the top platform without a published, dated survey.",
       {"type": "banned_terms", "terms": ["number one", "#1", "no.1", "india's best", "best in india", "top ranked"]},
       ref="Legal note L-19; ASCI guidelines on superlatives"),
    _r("LEGAL-FREE", "legal", "deterministic", "must", "Say what is free, and for how long",
       "'Free' always comes with its limit: a free course, a free trial of seven days. Never 'totally free'.",
       {"type": "banned_terms", "terms": ["100% free", "totally free", "free forever", "completely free"]},
       ref="Legal note L-21"),
    _r("LEGAL-RESULTS", "legal", "semantic", "must", "Results need a year, a count and consent",
       "A learner's result may be shown only with the exam year, how many learners the figure covers, and their "
       "written consent.", bad=["Our learner topped the board exams, join now", "Ananya scored a perfect score thanks to us"],
       good=["Ananya (2026 boards, shared with her consent) scored in the nineties"], ref="Legal note L-23"),
    _r("LEGAL-OFFER", "legal", "semantic", "should", "Offers state what, who and until when",
       "A discount or scholarship names what it applies to, who qualifies and the last day.",
       bad=["Scholarship for everyone, apply now", "Huge discount on all plans"],
       good=["Thirty percent off annual plans until Sunday for new learners"], ref="Legal note L-25"),
    _r("LEGAL-MINORS", "legal", "semantic", "must", "Speak to parents about money",
       "Under-eighteens are not asked to buy, subscribe or share contact details. Plans and prices are addressed to "
       "parents.", bad=["Ask your mom to buy the annual plan today", "Give us your phone number to win"],
       good=["Parents can try a course free for seven days"], ref="Child-safety note C-1"),
    _r("LEGAL-TESTIMONIAL", "legal", "semantic", "must", "Learner stories are true and consented",
       "A story names the real outcome and has the learner's written consent. No invented quotes.",
       bad=["Farah got a twenty lakh job because of Kitepath"], good=["Farah now runs her team's weekly SQL reports"],
       ref="Legal note L-24"),
    _r("VIS-LOGO-CLEAR", "visual", "semantic", "should", "Give the logo room",
       "Keep clear space of one emblem width around the logo; never place it on a busy photograph or beside "
       "another company's mark closer than that.", bad=["Logo placed on top of a crowded photo"],
       good=["Logo on a plain blue field with clear space"], ref="Brand book 2026, p.4"),
    _r("VIS-PALETTE", "visual", "deterministic", "should", "Brand colours only",
       "Posters and cards use the Kitepath palette: blue, orange, yellow and cream.",
       {"type": "palette", "colors": ["#1A5FD1", "#F08228", "#FAC828", "#FAF7EE", "#19233C"], "max_delta_e": 18,
        "min_share": 0.12}, ref="Brand book 2026, p.15"),
    _r("EMOJI-OFFTONE", "tone", "deterministic", "may", "Emoji we do not use",
       "A few emoji read as shouting or money talk in our channels.",
       {"type": "banned_emoji", "emojis": ["🔥", "💯", "🤑", "😎"]}, ref="Brand book 2026, p.8"),
    _r("CONF-LEARNER", "confidentiality", "deterministic", "must", "No learner identifiers",
       "Roll numbers, learner IDs and ID card numbers never appear in a post, even in a screenshot.",
       {"type": "banned_terms", "terms": ["roll number", "learner id", "aadhaar"]}, ref="Privacy policy 4.2"),
]

# The offline judge scores a text by its word overlap with the rule's examples, so every semantic rule also
# carries ordinary, compliant copy; the hosted judge reads the rule itself and ignores this.
_ORDINARY = ["Learn a little each evening and ask your mentor when you are stuck",
             "Our course starts with the basics and a mentor answers your questions every day",
             "This week on the course: short lessons, real practice and feedback from a mentor"]
for _rule in RULES:
    if _rule["kind"] == "semantic":
        _rule["good_examples"] = [*_rule["good_examples"], *_ORDINARY]

FACTS = [
    {"key": "learners_old", "statement": "Kitepath has 0.9 million learners", "value": 0.9, "unit": "million",
     "subject": "learners", "source_ref": "Annual report 2025, p.4", "from": -420},
    {"key": "learners", "statement": "Kitepath has 1.2 million learners", "value": 1.2, "unit": "million",
     "subject": "learners", "source_ref": "Annual report 2026, p.4", "from": -200, "supersedes": "learners_old"},
    {"key": "courses_old", "statement": "Kitepath offers 300 courses", "value": 300, "unit": "courses",
     "subject": "courses", "source_ref": "Catalogue, March 2026", "from": -230},
    {"key": "courses", "statement": "Kitepath offers 340 courses", "value": 340, "unit": "courses",
     "subject": "courses", "source_ref": "Catalogue, October 2026", "from": -22, "supersedes": "courses_old"},
    {"statement": "Learners rate Kitepath 4.7 out of 5", "value": 4.7, "unit": "out of 5", "subject": "rating",
     "source_ref": "App store listing, Sept 2026", "from": -52},
    {"statement": "Kitepath has 1,200 verified mentors", "value": 1200, "unit": "mentors", "subject": "mentors",
     "source_ref": "Mentor desk report, Aug 2026", "from": -70},
    {"statement": "Kitepath courses are taught in 9 languages", "value": 9, "unit": "languages", "subject": "languages",
     "source_ref": "Catalogue, October 2026", "from": -22},
    {"key": "price_old", "statement": "The Kitepath annual plan costs 3,999 rupees", "value": 3999, "unit": "rupees",
     "subject": "annual plan price", "source_ref": "Pricing page, 2025", "from": -420},
    {"key": "price", "statement": "The Kitepath annual plan costs 4,999 rupees", "value": 4999, "unit": "rupees",
     "subject": "annual plan price", "source_ref": "Pricing page, Aug 2026", "from": -60, "supersedes": "price_old"},
    {"statement": "82% of mock-test finishers scored above 75% in the 2026 board exams (14,000 learners surveyed)",
     "value": 82, "unit": "%", "subject": "mock-test finishers board exams", "source_ref": "Outcomes study 2026",
     "from": -120, "to": 150},
    {"statement": "Festive Fest 2025 gave 40% off annual plans", "value": 40, "unit": "%",
     "subject": "festive discount annual plans", "source_ref": "Festive Fest 2025 brief", "from": -380, "to": -330},
    {"statement": "30% off annual plans during the Festive Learning Fest", "value": 30, "unit": "%",
     "subject": "festive discount annual plans", "source_ref": "Festive Learning Fest brief", "from": -3, "to": 8},
    {"statement": "KiteLearn 2.0 tutors in 12 languages", "value": 12, "unit": "languages", "subject": "KiteLearn 2.0 languages",
     "source_ref": "KiteLearn 2.0 launch brief (embargoed)", "from": 20},
    {"statement": "Learner support is open 7 days a week", "value": 7, "unit": "days", "subject": "support days",
     "source_ref": "Support charter", "from": -200},
]

TERMS = [
    {"term": "Project Falcon", "note": "Revision mode, launches January", "embargo": 84},
    {"term": "Project Kestrel", "note": "Acquisition talks. Never public until the board announces it."},
    {"term": "Learner Graph", "note": "Internal name of the recommender; not a product name"},
    {"term": "Project Sparrow", "note": "Scholarship programme codename. Public since the launch", "embargo": -20},
]

CONTACTS = [
    {"kind": "phone", "value": "+91 80 4567 8900", "label": "Learner support", "source_ref": "kitepath.example/contact"},
    {"kind": "phone", "value": "+91 80 4567 8911", "label": "Press desk", "source_ref": "kitepath.example/press"},
    {"kind": "phone", "value": "+91 80 4567 8922", "label": "WhatsApp learner updates", "source_ref": "Support charter"},
    {"kind": "email", "value": "*@kitepath.example", "label": "Company domain", "source_ref": "IT policy"},
    {"kind": "url", "value": "kitepath.example", "label": "Website", "source_ref": "Brand book 2026, p.2"},
    {"kind": "url", "value": "help.kitepath.example", "label": "Help centre", "source_ref": "Support charter"},
    {"kind": "handle", "value": "@kitepath", "label": "Social handle", "source_ref": "Brand book 2026, p.2"},
    {"kind": "handle", "value": "@kitelearn", "label": "KiteLearn app handle", "source_ref": "Brand book 2026, p.2"},
]

EVENTS = [
    {"key": "teachers", "created": 52, "name": "Teachers' Day thank-you", "kind": "campaign", "start": -49, "end": -47,
     "hashtags": ["#ThankATeacher"], "guidance": "Celebrate mentors and school teachers by name; no discounts in the "
     "same post.", "summary": "Mentor stories for Teachers' Day."},
    {"key": "exam", "created": 44, "name": "Board Exam Prep Month", "kind": "campaign", "start": -40, "end": -22,
     "hashtags": ["#BoardPrepWithKite"], "avoid_terms": ["toppers guaranteed", "sure shot"],
     "guidance": "Support, not pressure: mock tests, doubt-clearing, sleep. Never promise marks.",
     "summary": "Free mock tests and mentor doubt sessions."},
    {"key": "advisory", "created": 31, "name": "Coaching advisory: results in ads", "kind": "other", "start": -30,
     "guidance": "New government advisory: any result shown in an ad needs the exam year, the learner count and "
     "consent. Review every results claim twice.", "summary": "Regulatory change after the coaching advisory."},
    {"key": "outage", "created": 16, "name": "App outage, early October", "kind": "crisis", "start": -16, "end": -13,
     "blackout": True, "guidance": "Acknowledge the outage plainly; no jokes about downtime.",
     "summary": "Sign-in failures for six hours on two days."},
    {"key": "fest", "created": 4, "name": "Festive Learning Fest", "kind": "sale", "start": -3, "end": 7,
     "hashtags": ["#LearnThisFestive"], "avoid_terms": ["cheapest", "lowest price ever"],
     "guidance": "Lead with what learners gain; the discount comes second. No countdown pressure.",
     "summary": "30% off annual plans across the festive week."},
    {"key": "launch", "created": 3.5, "name": "KiteLearn 2.0 launch", "kind": "launch", "start": 20,
     "hashtags": ["#KiteLearn2"], "guidance": "Until launch day, tease the feeling, not the features: no screenshots, "
     "no dates.", "summary": "Voice tutoring in the KiteLearn app."},
]

PEOPLE = [
    {"name": "Ananya Rao", "kind": "creator", "aliases": ["Ananya"], "channels": ["linkedin", "instagram"],
     "from": -300, "to": 200, "notes": "Design-track mentor. Written consent for profile photos and quotes."},
    {"name": "Vikrant Malhotra", "kind": "celebrity", "aliases": ["Vik Malhotra"], "channels": ["instagram", "youtube"],
     "events": ["exam"], "from": -45, "to": 60, "notes": "Cricketer. Board Exam Prep Month only; fee and exclusivity "
     "terms in contract K-77."},
    {"name": "Dr. Ritu Menon", "kind": "ambassador", "aliases": ["Ritu Menon"], "channels": [], "from": -400,
     "to": -35, "notes": "Scholarship ambassador. Agreement ended; renewal under discussion."},
]

TEAM = [
    Member("admin", "meera@kitepath.example", "Meera Rao", "brand_admin", title="Head of brand",
           blurb="Owns the brand library: rules, facts, artwork, events. Sees every screen."),
    Member("approver", "arjun@kitepath.example", "Arjun Mehta", "approver", title="Social media manager",
           blurb="Works the review queue: approves, sends back, rules on escalations."),
    Member("reviewer", "sana@kitepath.example", "Sana Iyer", "reviewer"),
    Member("auditor", "tara@kitepath.example", "Tara Bose", "auditor"),
    Member("legal", "vikram@kitepath.example", "Vikram Shah", "reviewer"),
]
CREATORS = [
    Member("rohan", "rohan@kitepath.example", "Rohan Kulkarni", "creator", "careful"),
    Member("priya", "priya@kitepath.example", "Priya Nair", "creator", "intern"),
    Member("dev", "dev@kitepath.example", "Dev Sharma", "creator", "marketer"),
    Member("aisha", "aisha@kitepath.example", "Aisha Khan", "creator", "regional"),
    Member("kabir", "kabir@kitepath.example", "Kabir Singh", "creator", "careful"),
    Member("neha", "neha@kitepath.example", "Neha Joshi", "creator", "intern"),
    Member("studio9", "studio9@agency.example", "Studio Nine (agency)", "creator", "agency"),
    Member("zoya", "zoya@creators.example", "Zoya Verma (creator partner)", "creator", "influencer"),
    Member("karthik", "karthik@kitepath.example", "Karthik Subramanian", "creator", "regional"),
    Member("ishita", "ishita@kitepath.example", "Ishita Banerjee", "creator", "marketer"),
]
DEMO = [
    ("approver", "approver", "manager", "Social media manager",
     "Works the review queue: approves, sends back, rules on escalations."),
    ("admin", "admin", "manager", "Head of brand",
     "Owns the brand library: rules, facts, artwork, events. Sees every screen."),
    ("c2", "dev", "creator", "Content creator", "Writes posts and fixes what Verytas flags. Has a piece sent back."),
    ("c1", "priya", "creator", "Content creator", "Instagram and X. Her tone drifts when she's in a hurry."),
    ("c6", "studio9", "creator", "Agency", "An outside agency writing campaigns for the brand."),
]

# How each reviewer tends to rule on a rule's findings: Sana is strict, Arjun practical, Vikram (legal) only
# cares about claims. The unclear rules (rivals, claims, results) are where they split and say so.
_UNCLEAR = ("guideline_unclear", "Does the rule mean this? It is a hint, not a comparison.")
STANCE = {
    "reviewer": {"TONE-SHIFT": (0.95, []), "TONE-PLAIN": (0.8, [("false_positive", "Warm enough for this channel.")]),
                 "CLAIM-UNSUPPORTED": (0.35, [("false_positive", "A study tip, not a claim about us."), _UNCLEAR]),
                 "MSG-RIVALS": (0.9, []), "TERM-HOUSE": (0.95, []), "*": (0.8, [("not_applicable", "Does not apply.")])},
    "approver": {"TONE-SHIFT": (0.7, [("intentional", "Light-hearted on purpose for this post.")]),
                 "CLAIM-UNSUPPORTED": (0.2, [("false_positive", "General statement, not a figure."), _UNCLEAR,
                                            ("not_applicable", "Public contact detail, not a promotion.")]),
                 "MSG-RIVALS": (0.4, [_UNCLEAR, ("false_positive", "Names nobody.")]),
                 "A11Y-READ": (0.3, [("not_applicable", "Hinglish; the grade does not mean anything.")]),
                 "*": (0.7, [("false_positive", "Reads fine to me.")])},
    "legal": {"CLAIM-UNSUPPORTED": (0.9, []), "CLAIM-CONTRADICTED": (1.0, []), "CLAIM-OUTDATED": (1.0, []),
              "LEGAL-RESULTS": (1.0, []), "TONE-SHIFT": (0.3, [("not_applicable", "Not a legal matter.")]),
              "*": (0.6, [("not_applicable", "Outside legal's remit.")])},
}


# --- the first three weeks, scripted: the stories the demo has always told ---------------------------

def _P(key, idx, title, channel, body, days_ago, flow, event=None, images=None):
    return Piece(key, ORDER[idx], title, channel, body, days_ago, flow, event=event, images=images)

def _old() -> list[Piece]:
    send = ("send", {})
    return [
        _P("diwali", 0, "Festive fest: learn something new", "instagram",
              "This festive season, learn something you'll keep. Pick any of 340 courses and start tonight. "
              "#LearnThisFestive", 2.2, [(1, *send)], event="fest"),
        _P("cheap", 1, "Festive offer reel caption", "instagram",
              "The cheapest courses in India, this week only! Kitepath has 2 million learners. Hurry, offer ends "
              "soon!!! #LearnThisFestive", 1.6, [(2, *send)], event="fest"),
        _P("falcon", 2, "Sneak peek: what's coming", "x",
              "Something big is coming: Project Falcon lands next month and changes how you revise.", 1.2,
              [(1, "escalate", {"message": "Falcon was named in the CEO's public interview on Monday, so it is "
                                           "not a secret any more. Please check with the brand team."})]),
        _P("placement", 3, "Data science bootcamp launch", "linkedin",
              "Join our data science bootcamp with 100% placement and a guaranteed job at the end. Login to "
              "enrol today.", 3.5, [(3, *send), (20, "back", {"note": "We never promise jobs. Say what the "
                                                                   "bootcamp teaches and who it suits."}),
                                    (30, "fix", {"body": "Join our data science bootcamp: twelve weeks of "
                                                 "real projects, mentor reviews and a portfolio you can show. Sign "
                                                 "in to enrol today."}),
                                    (31, *send)]),
        _P("call", 4, "Weekend doubt-clearing session", "facebook",
              "Stuck on calculus? Call me on 00000 12345 and I'll sort your doubts this weekend.", 0.8,
              [(1, "escalate", {"message": "This is my official teaching line for the weekend session, students "
                                           "already use it. Please allow it for this post."})]),
        _P("rivals", 5, "Why learners switch to us", "linkedin",
              "Unlike some other apps that just show videos, we actually teach. Kitepath has 1.2 million learners "
              "who learn by doing.", 4.2, [(2, *send)]),
        _P("rating", 0, "Thank you, learners", "instagram",
              "Thank you for rating Kitepath 4.7 out of 5. Every review helps us teach better.", 9,
              [(1, *send), (6, "approve", {}), (30, "publish", {})]),
        _P("python", 1, "Python in six weeks", "linkedin",
              "Learn Python in six weeks, one evening at a time. Real exercises, friendly mentors, and a project "
              "you can show.", 7, [(1, *send), (5, "approve", {})]),
        _P("webinar", 2, "Live webinar: exam strategy", "email",
              "Join our free webinar on exam strategy this Sunday. Register via the e-mail link.", 5,
              [(1, *send), (8, "back", {"note": "Use our house words (live class, email) and add a time."})]),
        _P("kitelearn", 3, "KiteLearn 2.0 teaser", "instagram",
              "Kitelearn 2.0 is almost here. Same friendly tutor, now with voice. #KiteLearn2", 2.8,
              [(2, *send)], event="launch"),
        _P("support", 4, "Need help? We're here", "x",
              "Need help with your course? Our support team is on +91 80 4567 8900, every day 9 to 9.", 6,
              [(1, *send), (4, "approve", {}), (20, "publish", {})]),
        _P("synergy", 6, "Agency draft: brand film caption", "youtube",
              "We leverage synergies to unlock next-gen learning paradigms for the learners of tomorrow.", 1.0,
              [(1, *send)]),
        _P("results", 6, "Agency draft: board exam campaign", "instagram",
              "Guaranteed results in your board exams with Kitepath. Login now, limited seats!", 0.5,
              [(0.2, "escalate", {"message": "The client asked for this exact line in their brief. Can the brand "
                                             "team confirm whether it is allowed?"}),
               (5, "resolve", {"outcome": "upheld", "note": "Not allowed: we never promise results. Try 'Prepare "
                                                             "for your board exams with mock tests and mentors'."})]),
        _P("mentor", 5, "Meet our mentors", "linkedin",
              "Meet Ananya, who mentors 40 learners a week in our design track. Her tip: finish one small thing a "
              "day.", 11, [(1, *send), (10, "approve", {}), (40, "publish", {})]),
        _P("courses", 2, "New this month: 20 courses", "instagram",
              "Twenty new courses landed this month, from Excel to Kannada for beginners. Which one are you "
              "starting?", 12, [(1, *send), (3, "approve", {}), (26, "publish", {})]),
        _P("streak", 1, "Learning streak challenge", "x",
              "Can you learn for 7 days straight? Join the streak challenge and share your progress with "
              "#KiteStreak.", 0.3, [(0.2, *send)]),
        _P("parents", 4, "A note for parents", "email",
              "Dear parents, here is how Kitepath keeps learning safe: verified mentors, no ads, and progress "
              "reports every Sunday.", 2.0, [(1, *send), (6, "comment", {"body": "Lovely. Can we add one line on "
                                                                        "how parents see the reports?"})]),
        # Kit in festival colours: the eyes and the tail were recoloured, so the official artwork was altered.
        _P("kitposter", 3, "Festive poster with Kit", "instagram",
              "Kit is celebrating with you this festive week. Learn one new thing a day. #LearnThisFestive", 0.7,
              [(1, *send)], event="fest",
              images=lambda: [{"id": "poster", "alt": "Kit the kite mascot above the words Learn one thing a day",
                               "data_base64": _b64(_scene(_kit(eye=(200, 40, 60), tail=(220, 40, 160)),
                                                          "Learn one thing a day"))}]),
        # The wordmark set by hand in a banner, with the wrong capital.
        _P("banner", 5, "Design track banner", "linkedin",
              "New on the design track: twelve short lessons on layout and type.", 1.4, [(1, *send)],
              images=lambda: [{"id": "banner", "alt": "Banner reading KitePath design track",
                               "data_base64": _b64(_wordmark("KitePath", size=(1200, 627), line="Design track"))}]),
        _P("hindi", 0, "Hinglish reel: padhai ka festival", "instagram",
              "Is festive season, padhai bhi celebrate karo! Naya course shuru karo aaj raat. #LearnThisFestive",
              0.9, [], event="fest"),
        *_history(),
    ]


def _clean() -> list[tuple[float, str, dict]]:
    return [(1, "send", {}), (4, "approve", {}), (20, "publish", {})]


def _fixed_old(note: str, body: str) -> list[tuple[float, str, dict]]:
    return [(1, "send", {}), (6, "back", {"note": note}), (20, "fix", {"body": body}), (21, "send", {}),
            (26, "approve", {}), (40, "publish", {})]


def _history() -> list[Piece]:
    """Three weeks of earlier work, so each creator's line on their profile has a shape: Rohan stays on brand,
    Priya's tone slides, Dev wanders off topic, Neha takes a sarcastic swipe, Kabir has one slip, and the
    agency writes like a contract. Every slip is the kind the brief names: tone, messaging, claims."""
    voice = "Keep our plain, warm voice: no slang, no digs, no hype."
    topic = "Stay on the course. Politics and money tips aren't ours to post."
    return [
        _P("r-tip", 0, "Monday study tip", "x",
              "Study for 25 minutes, then take five. Small sessions add up over a week.", 19, _clean()),
        _P("r-excel", 0, "Excel basics starts Saturday", "linkedin",
              "Our Excel basics course starts Saturday: formulas, charts and one real budget sheet.", 16, _clean()),
        _P("r-story", 0, "Learner story: Farah", "instagram",
              "Farah finished our SQL track in eight weeks and now runs the weekly reports for her team.", 13,
              _clean()),
        _P("r-set", 0, "Weekend practice set", "x",
              "This weekend's practice set has ten SQL questions, from easy to tricky. Try it and compare answers.",
              10, _clean()),
        _P("p-stats", 1, "Course of the week: statistics", "linkedin",
              "Our statistics course explains averages and spread with cricket scores. Six short lessons.", 18,
              _clean()),
        _P("p-sale", 1, "Weekend sale reminder", "instagram",
              "Our weekend sale is on.\n\nngl this one is kinda the best yet, gonna be fun lol", 14,
              _fixed_old(voice, "Our weekend sale is on: pick a course you'll actually finish. Ends Sunday.")),
        _P("p-exam", 1, "Exam season pep talk", "instagram",
              "Exam season is here. Revise a little every day and sleep well.\n\nAnd honestly, anyone still "
              "cramming the night before is an idiot.", 11,
              _fixed_old(voice, "Exam season is here. Revise a little every day, sleep well, and ask a mentor when "
                            "you're stuck.")),
        _P("d-excel", 2, "Learn Excel in a weekend", "linkedin",
              "Learn Excel in a weekend: two mornings, ten exercises and a sheet you'll use every month.", 17,
              _clean()),
        _P("d-budget", 2, "Why we teach budgeting", "linkedin",
              "Our budgeting course shows you how to track spending in one sheet.\n\nAlso, the new budget is a "
              "disaster and the finance minister should resign before the election.", 9,
              _fixed_old(topic, "Our budgeting course shows you how to track spending in one sheet, and how to plan "
                            "a month ahead.")),
        _P("d-money", 2, "Money skills for students", "instagram",
              "Our money skills course covers saving, spending and simple interest.\n\nSide tip: put your "
              "pocket money into crypto now, bitcoin is going to the moon.", 2.6, [(1, "send", {})]),
        _P("n-swipe", 5, "We just teach", "linkedin",
              "Oh great, another app promising miracles. Yeah right. We just teach, one lesson at a time.", 16,
              _fixed_old(voice, "We just teach, one lesson at a time, with mentors who answer within a day.")),
        _P("n-design", 5, "Design track: week one", "instagram",
              "Week one of the design track: sketch three logos, pick one, and share it for feedback.", 7, _clean()),
        _P("k-maths", 4, "Maths in ten minutes", "x",
              "Ten minutes of maths a day beats two hours on Sunday. Today's set is on fractions.", 19, _clean()),
        _P("k-board", 4, "Board exam timetable", "facebook",
              "Our free board exam timetable plans revision week by week. Download it from the course page.", 12,
              _clean()),
        _P("s-brochure", 6, "Agency draft: parents' brochure", "email",
              "Please be advised that, pursuant to the aforementioned curriculum, stakeholders shall receive "
              "deliverables quarterly.", 14,
              _fixed_old("Write to parents like a teacher would.", "Every term, parents get a short report on what "
                                                                "their child learned and what comes next.")),
        _P("s-gossip", 6, "Agency draft: festive teaser", "instagram",
              "Our festive courses open Friday.\n\nMeanwhile, Bollywood's biggest breakup rumour is all anyone "
              "talks about.", 9,
              _fixed_old(topic, "Our festive courses open Friday. Pick one skill to finish before the new year.")),
    ]


# Reviewers' calls on first-round findings of the scripted stories, so guideline health has a record to read.
DECISIONS = [
    ("r-tip", 3, "CLAIM-UNSUPPORTED", "reviewer", "rejected", "false_positive", "A study tip, not a claim about us."),
    ("p-sale", 5, "CLAIM-UNSUPPORTED", "approver", "rejected", "guideline_unclear",
     "\"Best yet\" is chatty, not a comparison. Does the rule mean this?"),
    ("p-sale", 5, "TONE-SHIFT", "approver", "accepted", None, None),
    ("p-exam", 5, "TONE-SHIFT", "approver", "accepted", None, None),
    ("n-swipe", 5, "TONE-SHIFT", "reviewer", "accepted", None, None),
    ("n-swipe", 5, "MSG-RIVALS", "approver", "accepted", None, None),
    ("s-brochure", 5, "TONE-SHIFT", "reviewer", "accepted", None, None),
    ("d-budget", 5, "MSG-OFF-TOPIC", "approver", "accepted", None, None),
    ("s-gossip", 5, "MSG-OFF-TOPIC", "reviewer", "accepted", None, None),
    ("s-gossip", 5, "CLAIM-UNSUPPORTED", "reviewer", "rejected", "guideline_unclear",
     "Celebrity gossip is off topic, but it isn't a claim about Kitepath."),
    ("d-money", 2, "MSG-OFF-TOPIC", "approver", "accepted", None, None),
    ("mentor", 2, "CLAIM-UNSUPPORTED", "approver", "rejected", "false_positive",
     "Ananya's group size is on her profile."),
    ("support", 2, "CLAIM-UNSUPPORTED", "reviewer", "rejected", "not_applicable",
     "Support hours are a listed public contact, not a promotion."),
    ("rivals", 2, "MSG-RIVALS", "approver", "rejected", "guideline_unclear",
     "\"Some other apps\" names nobody. Is a hint a dig?"),
]


# --- routine work: banks per persona ---------------------------------------------------------------------

CLEAN_BANK = [
    ("Study planner Sunday", "instagram", "Sunday is for planning. Pick three topics, give each a short slot and tick them off as you go. #StudyWithKite"),
    ("Python for beginners", "linkedin", "Our Python course starts with the basics and ends with a small project you can show. Learn a little each evening."),
    ("Mentor office hours", "x", "Mentors hold office hours every evening. Bring a question you are stuck on and leave with a plan."),
    ("Maths without panic", "instagram", "Fractions look scary until you draw them. Today's lesson draws every step."),
    ("Course spotlight: statistics", "linkedin", "Our statistics course explains averages and spread with cricket scores. Short lessons, real data."),
    ("Exam night routine", "x", "Pack your bag, set two alarms, sleep early. The revision is already done."),
    ("New in the catalogue", "blog", "This month the catalogue adds lessons on spreadsheets, public speaking and Kannada for beginners. Pick one and start with ten minutes a day."),
    ("Parent update", "whatsapp", "Hello parents, this week your child's mentor shared notes on fractions. You can read them in the app under Progress."),
    ("Doubt-clearing session", "email", "Stuck on a topic? Book a doubt-clearing session with a mentor. Pick a slot in the app and bring your question."),
    ("Learner story: Imran", "instagram", "Imran learned spreadsheets on his phone during his commute and now builds the monthly sheet for his shop."),
    ("Sign in help", "x", "Can't sign in? Reset your password from help.kitepath.example and you'll be back in a minute."),
    ("Why mentors", "linkedin", "Every course has a mentor who reads your work and answers your questions. That is the difference between watching and learning."),
    ("Reading habit", "instagram", "Ten pages a day adds up to a book a month. Start with something you enjoy."),
    ("KiteStreak tip", "x", "Keep your KiteStreak alive with a five-minute lesson on busy days. Small steps count."),
    ("Design track week", "instagram", "This week on the design track: spacing, alignment and why white space is not wasted space."),
    ("Language corner", "instagram", "Tamil, Kannada, Hindi and more: pick your course in the language you think in."),
    ("Teacher thanks", "linkedin", "Behind every learner is a teacher who believed in them. Thank you to the mentors who answer messages late at night."),
    ("Sleep and memory", "blog", "Sleep is when your brain files what you studied. Revise in the evening, sleep well and test yourself in the morning."),
    ("Quiz time", "x", "Quick quiz: which is bigger, one half or three eighths? Draw it and reply with your answer."),
    ("Typing basics", "facebook", "Our typing basics course has short daily drills. Ten minutes is enough to see progress."),
    ("Career talk", "youtube", "In this session our mentor explains how to build a small portfolio while you learn. Chapters are listed below and a transcript is in the help centre."),
    ("Weekend project", "linkedin", "Weekend project: build a one-page budget in a spreadsheet and share it with your mentor for feedback."),
    ("Accessibility note", "blog", "Every lesson has captions and a transcript, and every image has a description. Tell us if something is missing."),
    ("Mock test reminder", "email", "Your mock test is open this week. Take it in a quiet hour, then book a mentor session to go through the answers."),
    ("Revision map", "instagram", "Draw your syllabus as a map: topics in the middle, doubts on the edges. Your mentor can help you fill the edges."),
    ("Hindi corner", "instagram", "Naya hafta, naya course. Apni bhasha mein padho aur roz thoda aage badho."),
    ("Behind the scenes", "linkedin", "Our course team records every lesson twice: once for the teacher and once for a learner who is new to the topic."),
    ("Kit says", "instagram", "Kit's tip for today: if you are stuck, explain the problem out loud to a friend. #KiteTips"),
]

_VOICE = "Keep our plain, warm voice: no slang, no digs, no hype."
SLIPS = {
    "intern": [
        Slip("Monday motivation", "x", "Mondays, am I right? Yeah right, nobody wants to open a book today lol. But your streak does.",
             "Monday again. Open one lesson and keep your streak alive.", _VOICE),
        Slip("Result day pep", "instagram", "Results are out and honestly if you're panicking, bro, chill. It's gonna be fine, we got you.",
             "Results are out. Take a breath. Your mentor is a message away.", _VOICE),
        Slip("New Excel course", "linkedin", "Excel course just dropped!!! It's insane, you'll literally die. Hurry, last chance to join!!!",
             "Our Excel course is open: formulas, charts and one real budget sheet.", "No countdown pressure, no hype."),
        Slip("Why us", "x", "Other apps just show videos. We teach. Obviously.",
             "We teach by doing: practice, feedback and a mentor.", "No digs at other platforms, even by hint."),
        Slip("Cramming", "instagram", "Cramming the night before? That's what losers do. Start today.",
             "Start revising a little every day. The night before can be for sleep.", _VOICE),
        Slip("Girls and maths", "instagram", "Maths is hard for girls but we make it easy.",
             "Maths is learnable by everyone, one step at a time.", "Do not suggest any group finds a subject harder."),
        Slip("Board season", "x", "Do not be a failure this board season, start today.",
             "Board season is a good time to start small. Revise a little every day.", "Never frighten learners about marks."),
        Slip("Big sale", "instagram", "BIG SALE ON ALL PLANS NOW. GET IT TODAY.", "Our plans are open. Pick a course you will finish.",
             "Shouting in capitals reads badly in screen readers too."),
        Slip("New courses", "instagram", "🔥🔥🔥 new courses 💯", "New courses are in. Which one will you start?", "Not our emoji."),
        Slip("Study tag", "instagram", "Start something new today. #learnsomethingnewtoday",
             "Start something new today. #LearnSomethingNewToday", "Capitalise each word in a hashtag."),
    ],
    "agency": [
        Slip("Brand film caption", "youtube", "We leverage best-in-class pedagogy to operationalize outcomes for all stakeholders.",
             "Our film follows three learners through a month of lessons with their mentors.", "Write like a teacher, not a contract."),
        Slip("Selection ad", "instagram", "Guaranteed selection in competitive exams. Limited seats, act now!",
             "Prepare for competitive exams with structured mock tests and mentors.", "We never promise selection or rank."),
        Slip("Brand pride", "linkedin", "India's number one learning app is now bigger. Login today.",
             "Kitepath has 1.2 million learners. Sign in today.", "No self-declared rankings; use a backed number."),
        Slip("Free access", "instagram", "Free forever access to premium courses.",
             "Start with a free course; premium plans are optional.", "Say what is free and for how long."),
        Slip("Parents brochure", "email", "Pursuant to the aforementioned programme, deliverables shall be shared quarterly.",
             "Every term, parents get a short report on what their child learned.", "Write to parents like a teacher would."),
        Slip("Toppers", "instagram", "Toppers do not sleep. Real toppers choose Kitepath.",
             "Good sleep is part of good revision. Pick a plan that fits your week.", "Do not shame learners; no 'real toppers'."),
        Slip("Wordmark", "linkedin", "KitePath turns curiosity into careers.", "Kitepath helps curious learners build skills.",
             "Our name is Kitepath, small p."),
    ],
    "marketer": [
        Slip("Learner count", "linkedin", "Over 2 million learners trust Kitepath across 15 countries.",
             "Kitepath has 1.2 million learners.", "The approved figure is 1.2 million."),
        Slip("Rating", "instagram", "Learners rate Kitepath 4.9 out of 5.", "Learners rate Kitepath 4.7 out of 5.",
             "The listed rating is 4.7."),
        Slip("Catalogue size", "x", "Choose from 400 courses this season.", "Choose from 340 courses this season.",
             "The catalogue says 340."),
        Slip("Old price", "instagram", "Get the 3,999 annual plan this season.", "Get the 4,999 annual plan this season.",
             "That price is last year's."),
        Slip("Marks claim", "linkedin", "9 out of 10 learners improve their marks within a month.",
             "Learners who finish our mock-test series practise under exam conditions.", "No figure is approved for this."),
        Slip("Old count", "x", "Join 9 lakh learners on Kitepath.", "Join 1.2 million learners on Kitepath.",
             "That count is from last year."),
    ],
    "influencer": [
        Slip("Switched apps", "instagram", "Switched from SkillSprint to Kitepath and wow, the difference. #KitepathPartner",
             "I use Kitepath for my revision plan and love the mock tests. #KitepathPartner", "Do not name other platforms."),
        Slip("Call me", "instagram", "Unlike other apps, Kitepath actually explains stuff. Call me on 00000 12345 for my code.",
             "Kitepath explains things step by step. Use my code from the link in my bio.", "Only the company's numbers in posts."),
        Slip("Slangy reel", "instagram", "gonna crack boards with Kitepath, no cap, bestie vibes only #KitepathPartner",
             "Revising for boards with Kitepath, one lesson a day. #KitepathPartner", _VOICE),
        Slip("Marks promise", "instagram", "Kitepath got me guaranteed marks!! Do it too.",
             "Kitepath helped me plan my revision. Your marks are your own work.", "We never promise marks."),
        Slip("Honest review", "youtube", "Honest review: it's pricey but worth it. Not like those cheap apps.",
             "Honest review: the mock tests and mentors are what I use most.", "No digs at others, even by hint."),
        Slip("Offer link", "instagram", "Grab the offer here: [click here](https://kitepath.example/offer)",
             "Grab the offer here: [festive offer details](https://kitepath.example/offer)", "Link text must say where it goes."),
    ],
    "regional": [
        Slip("Hinglish login", "instagram", "Login karo aur webinar join karo, naya course shuru ho raha hai.",
             "Sign in karo aur live class join karo, naya course shuru ho raha hai.", "Use our house words: sign in, live class."),
        Slip("Hostile Hindi", "instagram", "Padhai mein gadha mat bano, roz thoda padho.", "Padhai mein roz thoda padho, hum saath hain.",
             _VOICE),
        Slip("Name casing", "instagram", "KitePath pe Tamil kalvi courses ab available hain.",
             "Kitepath pe Tamil kalvi courses ab available hain.", "Our name is Kitepath."),
        Slip("Tamil email", "email", "புதிய படிப்புகள் இன்று தொடங்குகின்றன. E-mail மூலம் பதிவு செய்யுங்கள்.",
             "புதிய படிப்புகள் இன்று தொடங்குகின்றன. Email மூலம் பதிவு செய்யுங்கள்.", "House word: email."),
        Slip("Marks pakka", "instagram", "Guaranteed marks, pakka! Kitepath se padho.", "Kitepath se padho, mentor saath hain.",
             "We never promise marks."),
        Slip("Kannada link", "youtube", "ಈ ವಾರದ ಹೊಸ ಪಾಠಗಳು: [here](https://kitepath.example/kn)",
             "ಈ ವಾರದ ಹೊಸ ಪಾಠಗಳು: [Kannada ಪಾಠಗಳ ಪಟ್ಟಿ](https://kitepath.example/kn)", "Link text must say where it goes."),
    ],
    "careful": [
        Slip("Playlist link", "linkedin", "Study playlist: [click here](https://kitepath.example/playlist) for the full list.",
             "Study playlist: [open the full study playlist](https://kitepath.example/playlist).", "Link text must say where it goes."),
        Slip("Webinar", "email", "Our webinar on revision strategy is on Saturday. Register by e-mail.",
             "Our live class on revision strategy is on Saturday. Register by email.", "House words: live class, email."),
    ],
}


# --- images -----------------------------------------------------------------------------------------------

def _rev():
    return art.on_color(_lockup((255, 255, 255), _mark(c1=(255, 255, 255), c2=(210, 226, 250))), BLUE, 30)


def _poster(headline, sub="", logo="ok", mascot=None, size=(1080, 1080)):
    """A blue campaign card. `logo` says how the mark was used: as registered, stretched into a slot, the
    retired 2024 version, or recoloured."""
    img = art.card(size, BLUE, headline, sub, art=mascot, art_w=380)
    rev = _rev()
    if logo == "ok":
        art.paste(img, rev, (74, 880), width=420)
    elif logo == "stretched":
        art.paste(img, rev, (74, 880), width=560, height=161)
    elif logo == "old":
        art.paste(img, _old_logo(), (74, 860), width=420)
    elif logo == "recolour":
        art.paste(img, art.recolour(rev, "gbr"), (74, 880), width=420)
    return img


def _img(key, alt, img):
    return lambda: [art.image_attachment(key, alt, img() if callable(img) else img)]


def _compare():
    img = art.canvas((1080, 1080), CREAM)
    from PIL import ImageDraw

    d = ImageDraw.Draw(img)
    d.text((80, 90), "Which app explains better?", fill=NAVY, font=art.font(64))
    art.paste(img, _lockup().convert("RGBA"), (60, 420), width=420)
    art.paste(img, _competitor(), (620, 380), width=300)
    d.text((620, 700), "SkillSprint", fill=(150, 25, 40), font=art.font(56))
    d.text((492, 470), "vs", fill=NAVY, font=art.font(48))
    return img


def _ambassador(name, caption):
    img = art.portrait((1080, 1080), (205, 160, 130), CREAM, BLUE, caption)
    art.paste(img, _lockup().convert("RGBA"), (60, 40), width=300)
    return img


def _partner_card():
    from PIL import ImageDraw

    img = art.canvas((1200, 628), (255, 255, 255))
    art.paste(img, _lockup().convert("RGBA"), (80, 200), width=420)
    art.paste(img, _partner(), (700, 150), width=300)
    ImageDraw.Draw(img).text((690, 470), "Nalanda Foundation", fill=(20, 100, 70), font=art.font(36))
    return img


# --- the eight weeks, scripted -----------------------------------------------------------------------------

def _back(note, by="approver"):
    return [(1, "send", {}), (3, "autodecide", {"by": "reviewer"}), (6, "back", {"note": note, "by": by})]


def _stories() -> list[Piece]:
    fest, ex = "fest", "exam"
    pk = Piece
    return [
        pk("t-rohan", "rohan", "Thank you, mentors", "linkedin", "Today we are sharing the stories behind the people who answer your late-night messages. Thank you, mentors. #ThankATeacher", 49, CLEAN, event="teachers"),
        pk("t-kabir", "kabir", "A teacher who changed my maths", "instagram", "My Class 9 teacher drew every fraction on the board until I stopped being afraid of them. Thank you.", 49, fixed("Add the event hashtag.", "My Class 9 teacher drew every fraction on the board until I stopped being afraid of them. Thank you. #ThankATeacher", "approver"), event="teachers"),
        pk("t-priya", "priya", "Teachers' Day sale", "instagram", "Teachers' Day sale!! Flat discount on all plans, hurry, last chance! #ThankATeacher", 48.5, fixed("Teachers' Day is for thanks, not a sale. Keep the discount out of it.", "Happy Teachers' Day to every mentor who stays online until the last doubt is cleared. #ThankATeacher", "approver"), event="teachers"),
        pk("e-mock", "ishita", "Free mock tests this month", "linkedin", "Mock tests are free this month. 82% of finishers scored above 75% in the 2026 board exams. #BoardPrepWithKite", 38, CLEAN, event=ex),
        pk("e-90", "dev", "Board results claim", "instagram", "Join Kitepath: 90% of learners score above 75% in the board exams. #BoardPrepWithKite", 37, fixed("The approved figure is 82% of mock-test finishers, with the sample size. Use that.", "82% of mock-test finishers scored above 75% in the 2026 board exams. Start your mock tests today. #BoardPrepWithKite", "legal"), event=ex),
        pk("e-guar", "studio9", "Board batch ad", "instagram", "Guaranteed selection if you join the board prep batch! Toppers guaranteed. Limited seats, act now! #BoardPrepWithKite", 36, [(0.3, "send", {}), (0.5, "escalate", {"message": "The client's legal team approved the line 'guaranteed selection' in their brief. Please confirm we can run it.", "rule": "CLAIM-PROMISE"}), (7, "resolve", {"outcome": "upheld", "note": "Not allowed: we do not promise selection or marks, whatever the brief says. Use the mock-test approach."}), (9, "back", {"note": "Remove the promise and the countdown; see the escalation.", "by": "approver"}), (20, "fix", {"body": "Prepare for the board exams with mock tests, mentor sessions and a revision plan that fits your week. #BoardPrepWithKite"}), (21, "send", {}), (28, "approve", {}), (50, "publish", {})], event=ex),
        pk("e-vik", "rohan", "Vikrant's exam-night routine", "instagram", "Vikrant Malhotra shares how he prepares the night before a big match, and how the same routine helps before an exam. #BoardPrepWithKite", 33, CLEAN, event=ex,
           images=_img("vik", "Vikrant Malhotra smiling in a blue jacket above the Kitepath logo", lambda: _ambassador("Vikrant", "Exam-night routine"))),
        pk("e-vik2", "zoya", "Vikrant and me", "linkedin", "Met Vikrant Malhotra at the studio today. He uses Kitepath mock tests too. #BoardPrepWithKite", 30, [(2, "send", {}), (5, "autodecide", {"by": "reviewer"}), (8, "back", {"note": "Vikrant's agreement covers Instagram and YouTube only, not LinkedIn. Take it down or ask the brand team.", "by": "approver"})], event=ex,
           images=_img("vik2", "Vikrant Malhotra with Zoya in a studio", lambda: _ambassador("Vikrant", "With Zoya"))),
        pk("e-stretch", "neha", "Board prep banner", "instagram", "Board Exam Prep Month starts now: free mock tests and mentor doubt sessions. #BoardPrepWithKite", 35,
           fixed("The logo is stretched. Use the registered lockup at its own proportions.", "Board Exam Prep Month starts now: free mock tests and mentor doubt sessions. Logo corrected. #BoardPrepWithKite", "reviewer"), event=ex,
           images=_img("banner", "Board prep poster reading Prepare calmly, with the Kitepath logo", lambda: _poster("Prepare calmly", "Mock tests and mentors", "stretched")),
           fix_images=_img("banner", "Board prep poster reading Prepare calmly, with the Kitepath logo", lambda: _poster("Prepare calmly", "Mock tests and mentors", "ok", _kit()))),
        pk("e-hinglish", "aisha", "Padhai ka gadha mat bano", "instagram", "Padhai mein gadha mat bano, roz thoda padho. Naya mock test aaj shuru. #BoardPrepWithKite", 31,
           [(1, "send", {}), (2, "dispute", {"rule": "TONE-SHIFT", "claim": "Gadha is not an insult here: 'gadha mehnat' is an idiom for hard work, and the line tells learners to keep at it.", "language": "Hinglish"}), (4, "autodecide", {"by": "approver"}), (9, "approve", {"note": "Idiom checked with the Hindi desk; fine to publish."}), (30, "publish", {})], event=ex, notes={"language": "Hinglish", "intent": "Encourage steady study; 'gadha mehnat' means hard work."}),
        pk("e-tamil", "karthik", "மாதிரி தேர்வு நினைவூட்டல்", "email", "இந்த வாரம் மாதிரி தேர்வு திறந்துள்ளது. E-mail மூலம் பதிவு செய்யுங்கள். #BoardPrepWithKite", 29,
           fixed("House word: email, even in Tamil copy.", "இந்த வாரம் மாதிரி தேர்வு திறந்துள்ளது. Email மூலம் பதிவு செய்யுங்கள். #BoardPrepWithKite", "reviewer"), event=ex, notes={"language": "Tamil"}),
        pk("e-night", "kabir", "Congrats to our SQL finishers", "instagram", "Congrats to roll number 4521 and everyone who finished the SQL track this week! #BoardPrepWithKite", 27,
           fixed("Never show a roll number or learner ID.", "Congrats to everyone who finished the SQL track this week! #BoardPrepWithKite", "approver"), event=ex),
        pk("r-ninety", "ishita", "Ananya's result", "linkedin", "Ananya scored a perfect score thanks to Kitepath. Join her batch today.", 28,
           [(1, "send", {}), (3, "autodecide", {"by": "legal"}), (4, "comment", {"by": "legal", "body": "Under the advisory this needs the exam year, the count it covers and Ananya's written consent. I cannot sign it off like this."}), (6, "back", {"note": "Results need a year, a count and consent. See Vikram's comment.", "by": "approver"}), (30, "withdraw", {})], event=None),
        pk("r-ok", "rohan", "How Ananya planned her revision", "linkedin", "Ananya shares how she planned revision for the 2026 board exams, with her consent. Results are individual and not a promise.", 26, CLEAN),
        pk("r-topped", "studio9", "Results ad draft", "instagram", "Our learner topped the board exams, join now. Guaranteed rank for every batch.", 25, _back("The advisory needs year, count and consent for any result, and we never promise rank."), ),
        pk("a-nine", "studio9", "Learner count banner", "linkedin", "Join 9 lakh learners on Kitepath. Annual plan from 3,999 rupees.", 22, fixed("Both figures are last year's: 1.2 million learners and 4,999 rupees.", "Join 1.2 million learners on Kitepath. The annual plan costs 4,999 rupees.", "legal")),
        pk("o-ack", "rohan", "We know sign-in failed", "x", "We know sign-in failed for some of you this morning. Our team fixed it by the afternoon and your streaks are safe. Sorry, and thank you for waiting.", 15.8, [(0.3, "send", {}), (0.8, "approve", {}), (1.1, "publish", {})], event=None),
        pk("o-joke", "priya", "Servers took a nap", "x", "lol our servers took a nap, brb. bear with us fam!", 15.5, [(0.5, "send", {}), (1.5, "autodecide", {"by": "approver"}), (2, "back", {"note": "No jokes while sign-in is down. Acknowledge it plainly.", "by": "approver"}), (6, "fix", {"body": "Sign-in is failing for some of you. We are working on it and will post here as soon as it is fixed."}), (6.5, "send", {}), (7, "approve", {}), (7.5, "publish", {})]),
        pk("o-promo", "neha", "Weekend offers", "instagram", "Weekend offers are on: pick an annual plan and start learning tonight.", 14.8, [(1, "send", {}), (3, "back", {"note": "Promotions are paused until sign-in is stable. Hold this until the outage ends.", "by": "approver"})]),
        pk("c-swap", "zoya", "Honest comparison", "instagram", "I put Kitepath next to the other big app. Swipe for my honest comparison.", 20,
           [(1, "send", {}), (3, "autodecide", {"by": "approver"}), (6, "back", {"note": "A competitor's logo in a comparison graphic is a no. Show our own product.", "by": "approver"})],
           images=_img("cmp", "Comparison graphic with the Kitepath logo and a rival's logo", _compare)),
        pk("c-old", "studio9", "Scholarship poster", "instagram", "Applications for the Kitepath scholarship open this month, with our partner Nalanda Foundation.", 18,
           fixed("That is the 2024 logo. Use the current lockup.", "Applications for the Kitepath scholarship open this month, with our partner Nalanda Foundation. Logo updated.", "approver"),
           images=_img("sch", "Scholarship poster with the Kitepath logo", lambda: _poster("Scholarships are open", "With Nalanda Foundation", "old")),
           fix_images=_img("sch", "Scholarship poster with the Kitepath logo", lambda: _poster("Scholarships are open", "With Nalanda Foundation", "ok"))),
        pk("c-recolour", "studio9", "Festive Kit poster", "instagram", "Kit is celebrating Dussehra with you. Learn one thing a day. #LearnThisFestive", 1.2, [(1, "send", {})], event=fest,
           images=_img("kitfest", "Kit the kite mascot in festive colours above Learn one thing a day", lambda: _poster("Learn one thing a day", "Dussehra week", "recolour", art.recolour(_kit(), "bgr")))),
        pk("c-squash", "priya", "Kit meme", "instagram", "When the mock test is harder than you thought. Kit has feelings too. #LearnThisFestive", 1.9, [(1, "send", {})], event=fest,
           images=_img("kitmeme", "A squashed Kit the kite mascot looking worried", lambda: _poster("Mock test mood", "", "ok", art.stretch(_kit(), 1.0, 0.55)))),
        pk("c-good", "rohan", "Learn one thing a day", "instagram", "A small lesson each day beats a big push once a week. Pick today's. #LearnThisFestive", 2.4, [(1, "send", {}), (4, "approve", {})], event=fest,
           images=_img("good", "Kit the kite mascot beside the words Learn one thing a day and the Kitepath logo", lambda: _poster("Learn one thing a day", "Festive week", "ok", _kit()))),
        pk("c-partner", "rohan", "Kitepath and Nalanda", "linkedin", "Kitepath and Nalanda Foundation are opening scholarships for learners who cannot afford a plan. Applications close at the end of the month.", 21, [(1, "send", {}), (4, "approve", {}), (24, "publish", {})],
           images=_img("pr", "Kitepath and Nalanda Foundation logos side by side", _partner_card)),
        pk("p-kestrel", "studio9", "Press release draft", "press release", "Kitepath is in advanced talks under Project Kestrel to join a larger education group. A statement will follow.", 19,
           [(0.5, "send", {}), (1, "escalate", {"message": "The client asked us to prepare a holding statement in case the news leaks. Please confirm the term is okay in a draft.", "rule": "CONF-LEAK"}), (6, "resolve", {"outcome": "upheld", "note": "Drafts stay in the shared doc, not here. This term never goes in a post."})]),
        pk("p-sparrow", "dev", "Scholarship launch", "linkedin", "Project Sparrow is now the Kitepath Scholarship. Applications open this month.", 17, CLEAN),
        pk("p-learnergraph", "dev", "How recommendations work", "blog", "Our Learner Graph picks the next lesson for you based on what you finished and where you got stuck.", 12, fixed("Learner Graph is an internal name. Describe what it does instead.", "Kitepath picks the next lesson for you based on what you finished and where you got stuck.", "approver")),
        pk("p-lang", "kabir", "KiteLearn 2.0 teaser", "instagram", "KiteLearn 2.0 will tutor you in 12 languages. #KiteLearn2", 2.1, [(1, "send", {}), (3, "autodecide", {"by": "legal"})], event="launch"),
        pk("ai-art", "ishita", "Illustration for the blog", "blog", "Our new guide to spaced repetition has a hand-drawn look. Read it in the help centre.", 10,
           [(1, "send", {}), (3, "autodecide", {"by": "reviewer"}), (6, "back", {"note": "The illustration is AI-generated; say so in the post.", "by": "approver"}), (20, "fix", {"body": "Our new guide to spaced repetition has a hand-drawn look. The illustration was made with AI. Read it in the help centre."}), (21, "send", {}), (26, "approve", {})],
           notes={"ai_used": True}),
        pk("lp-app", "ishita", "Play Store listing refresh", "app store", "Learn at your pace with 340 courses, 1,200 verified mentors and lessons in 9 languages. Learners rate Kitepath 4.7 out of 5.", 9, CLEAN,
           images=_img("icon", "Kitepath app icon, a white kite on a blue tile", lambda: art.on_color(_app_icon(), CREAM, 60))),
        pk("lp-4", "ishita", "App store rating line", "app store", "Rated 4.9 by 1.2 million learners.", 8, fixed("The listed rating is 4.7.", "Rated 4.7 by 1.2 million learners.", "legal")),
        pk("ask-fact", "ishita", "Mentor reply times", "linkedin", "Mentors reply to every doubt within 24 hours.", 4, [(0.5, "send", {}), (1, "escalate", {"message": "This is in the mentor charter but not in the fact library. Can the brand team add it, or tell me to soften the line?", "rule": "CLAIM-UNSUPPORTED"})]),
        pk("whats", "rohan", "Parent broadcast", "whatsapp", "Hello parents, progress reports go out every Sunday. Questions? Call +91 80 4567 8922 and we will help.", 6, CLEAN),
        pk("contact", "neha", "Write to me", "linkedin", "Questions about the design track? Write to me at neha.joshi@mail.example.", 13, fixed("Only company addresses in posts.", "Questions about the design track? Write to us at design@kitepath.example.", "approver")),
        pk("contrast", "studio9", "Exam poster for print", "print", "Board Exam Prep Month poster for school notice boards.", 34,
           fixed("The headline colour fails contrast. Use the dark navy.", "Board Exam Prep Month poster for school notice boards. Headline recoloured.", "reviewer"), event=ex,
           colors=[{"fg": "#FAC828", "bg": "#FFFFFF", "where": "headline on the poster", "large": True}], fix_colors=[{"fg": "#19233C", "bg": "#FFFFFF", "where": "headline on the poster", "large": True}],
           images=_img("print", "Poster headed Board Exam Prep Month with the Kitepath logo", lambda: _poster("Board Exam Prep Month", "Free mock tests", "ok", _kit()))),
        pk("hint", "zoya", "Switch and save", "instagram", "Other apps charge for the same things. Kitepath is different, trust me. #KitepathPartner", 11, _back("Hints count too. No comparisons with other platforms.")),
    ]


ADMIN_LOG = [
    (14, "patch_rule", {"code": "MSG-RIVALS", "patch": {
        "text": "Talk about what we do. Never mock or compare against other learning platforms, by name. A hint "
                "that only some apps 'just show videos' counts when the sentence clearly points at a rival.",
        "bad_examples": ["Unlike some other apps, we actually teach", "Other apps just show videos",
                         "Not like those cheap apps"]}}),
]


def build() -> Company:
    def pieces() -> list[Piece]:
        out = _old() + _stories() + routine("kitepath", CREATORS, CLEAN_BANK, SLIPS, 55, 0.3)
        keys = [p.key for p in out]
        assert len(keys) == len(set(keys)), "duplicate piece keys"
        return out

    return Company(
        key="kitepath", brand=BRAND, industry="Edtech: courses, mentors and a tutor app for school and early-career "
        "learners", domain="kitepath.example", days=56, team=TEAM, creators=CREATORS, rules=RULES, facts=FACTS,
        terms=TERMS, contacts=CONTACTS, assets=ARTWORK, events=EVENTS, people=PEOPLE, pieces=pieces,
        decisions=DECISIONS, stance=STANCE, admin_log=ADMIN_LOG, demo=DEMO)
