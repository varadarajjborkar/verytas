"""Content templates: what people actually post, with slots for plants.

A template is a piece of content written once (by the LLM, or from the offline
bank) with `{{S1}}`-style slots where a planted phrase goes. The same template
is then filled many times with different variants, which is how one model call
turns into dozens of test cases with exact ground truth.

Slot types: term (a banned phrase), codename, brand (the brand name, so its
casing can vary) and stat (a number whose approved value is known).
"""

from __future__ import annotations

import random
import re
import sys
from collections import Counter
from dataclasses import dataclass, field

from blackbox.world import Reality

SLOT = re.compile(r"\{\{(S\d+)\}\}")

# What online content is made of in 2026, roughly. Channel names are free text
# in the API; the mix here is what a social, support and marketing team ships.
GENRES: dict[str, str] = {
    "launch_post": "a LinkedIn or X product launch post",
    "roast_reply": "a brand account roasting a fan or a rival who asked for it, playful not cruel",
    "flame_war": "a heated reply thread between customers where the brand steps in",
    "meme_caption": "a meme caption with a top-text/bottom-text or POV format",
    "hot_take": "a spicy one-paragraph opinion post from the brand",
    "crisis_apology": "an apology statement after an outage or a bad campaign",
    "sponsored_post": "an influencer's sponsored post with #ad",
    "complaint_reply": "a support reply to an angry public complaint",
    "review_response": "a reply to a 2-star app store or Google review",
    "ama_answer": "a Reddit AMA answer from the founder",
    "humblebrag": "a LinkedIn humblebrag milestone post",
    "thread": "a numbered X thread (1/5 style) explaining an update",
    "newsletter": "a short newsletter section",
    "push_notification": "two or three push notification lines",
    "release_notes": "app store release notes",
    "job_post": "a casual job post for the team",
    "giveaway": "a giveaway or contest post with rules",
    "ragebait_poll": "an engagement-bait poll post",
    "hinglish_caption": "an Instagram reel caption mixing Hindi and English (Hinglish)",
    "short_script": "a 30-second YouTube Short or reel voiceover script",
    "podcast_ad": "a host-read podcast ad",
    "press_excerpt": "a press release excerpt with a quote from the CEO",
    "discord_announcement": "a Discord community announcement with emoji",
    "quote_dunk": "a quote-post dunking on a competitor's claim",
    "unhinged_tweet": "an 'unhinged brand Twitter' post, chaotic but harmless",
    "whatsapp_forward": "a forwarded-many-times WhatsApp promo message",
}

CHANNELS = {
    "launch_post": "linkedin", "roast_reply": "x", "flame_war": "x", "meme_caption": "instagram",
    "hot_take": "x", "crisis_apology": "blog", "sponsored_post": "instagram", "complaint_reply": "x",
    "review_response": "app_store", "ama_answer": "reddit", "humblebrag": "linkedin", "thread": "x",
    "newsletter": "email", "push_notification": "push", "release_notes": "app_store", "job_post": "linkedin",
    "giveaway": "instagram", "ragebait_poll": "x", "hinglish_caption": "instagram", "short_script": "youtube",
    "podcast_ad": "audio", "press_excerpt": "press", "discord_announcement": "discord", "quote_dunk": "x",
    "unhinged_tweet": "x", "whatsapp_forward": "whatsapp",
}


@dataclass
class Slot:
    id: str
    type: str  # term | codename | brand | stat
    ref: str  # the banned term, or the stat subject


@dataclass
class Template:
    genre: str
    channel: str
    title: str
    body: str
    slots: list[Slot] = field(default_factory=list)
    source: str = "offline"


# --- offline bank -------------------------------------------------------------------------------
# Clean on purpose: no shouting, no long hashtags, no vague links, no claims.
# Every violation in an offline case is one the harness planted and can score.

_OFFLINE: dict[str, list[str]] = {
    "launch_post": ["Big week for us. {{BRAND}} just shipped {product}, built with feedback from {audience}.\n\n"
                    "It took a while and we learned a lot. Tell us what you think in the comments."],
    "roast_reply": ["You asked {{BRAND}} to roast your setup. Respectfully, that keyboard has seen things.\n\n"
                    "Get {product} and let your desk start healing."],
    "flame_war": ["Okay everyone, deep breaths. Both of you are right about the price and wrong about the colour.\n\n"
                  "{{BRAND}} support is in your DMs now, no need to fight in the replies."],
    "meme_caption": ["POV: you finally tried {product} and now you judge everyone who hasn't.\n\nTag that one friend."],
    "hot_take": ["Hot take from {{BRAND}}: most {industry} apps are built for investors, not for {audience}.\n\n"
                 "We would rather be useful than loud."],
    "crisis_apology": ["Yesterday {{BRAND}} was down for three hours. That is on us and we are sorry.\n\n"
                       "Here is what broke, what we fixed, and what we are changing so it does not happen again."],
    "sponsored_post": ["#ad Been using {product} for a month now and it quietly fixed my mornings.\n\n"
                       "Not a miracle, just a nice routine. Thanks {{BRAND}} for sending it over."],
    "complaint_reply": ["Hey, that is not the experience we want for you. We have looked at your order and a "
                        "refund is on its way.\n\nIf anything else is off, reply here and the {{BRAND}} team will "
                        "pick it up."],
    "review_response": ["Thanks for the honest review. You are right that the last update moved things around.\n\n"
                        "We have put the old menu back in settings. {{BRAND}} reads every review."],
    "humblebrag": ["Three years ago {{BRAND}} was two people and a laptop.\n\nToday we shipped {product}. "
                   "Grateful to {audience} who stuck with us."],
    "thread": ["1/4 What changed in {product} this month, a thread.\n\n2/4 Faster sign-up. 3/4 A cleaner home "
               "screen.\n\n4/4 And a lot of small fixes from {{BRAND}} that you will never notice, "
               "which is the point."],
    "hinglish_caption": ["Yaar honestly {product} ke bina ab kaam hi nahi chalta.\n\n{{BRAND}} ne sach mein life "
                         "thodi easy kar di. Try karo, phir batana."],
    "discord_announcement": ["Hey team, new drop in the server today. {product} is live for everyone.\n\n"
                             "Drop your feedback in the feedback channel, the {{BRAND}} devs are reading."],
    "whatsapp_forward": ["Forwarded as received. {{BRAND}} is giving early access to {product} this weekend.\n\n"
                         "Share with family and friends who might like it."],
}

_TERM_LINES = ["Honestly this one is a {x} for {audience}.", "People keep calling it {x} and we are not mad.",
               "Our team's word for it was {x}."]
_CODENAME_LINES = ["Psst, {x} is coming soon.", "Cannot say much about {x} yet, but stay close.",
                   "The team behind {x} says hi."]
_STAT_LINES = ["Update: {x} {subject} as of this week.", "We just crossed {x} {subject}."]
_STAT_LINES_PCT = ["In our latest survey, {x} of {subject}.", "Fresh numbers: {x} of {subject}."]


def offline_templates(reality: Reality, rng: random.Random, n: int) -> list[Template]:
    spec = reality.spec
    ctx = {"product": rng.choice(spec.products), "audience": spec.audience, "industry": spec.industry}
    out = []
    for _ in range(n):
        genre = rng.choice(list(_OFFLINE))
        # format() turns the bank's {{BRAND}} into {BRAND}; restore it as slot S1.
        body = rng.choice(_OFFLINE[genre]).format(**ctx).replace("{BRAND}", "{{S1}}")
        slots = [Slot("S1", "brand", spec.name)]
        extra = []
        for i, kind in enumerate(rng.sample(["term", "codename", "stat"], k=rng.randint(1, 3)), start=2):
            sid = f"S{i}"
            if kind == "term":
                term = rng.choice(list(spec.banned))
                extra.append(rng.choice(_TERM_LINES).format(x="{{" + sid + "}}", audience=spec.audience))
                slots.append(Slot(sid, "term", term))
            elif kind == "codename":
                extra.append(rng.choice(_CODENAME_LINES).format(x="{{" + sid + "}}"))
                slots.append(Slot(sid, "codename", spec.codename))
            else:
                stat = rng.choice(spec.stats)
                lines = _STAT_LINES_PCT if stat.unit == "%" else _STAT_LINES
                extra.append(rng.choice(lines).format(x="{{" + sid + "}}", subject=stat.subject))
                slots.append(Slot(sid, "stat", stat.subject))
        body = body + "\n\n" + " ".join(extra)
        out.append(Template(genre, CHANNELS[genre], f"{GENRES[genre][:60]}", body, slots, "offline"))
    return out


# --- LLM templates ------------------------------------------------------------------------------

CONTENT_SYSTEM = (
    "You write realistic online content exactly as it appears in 2026: replies, threads, captions, roasts, "
    "support macros, Hinglish captions, sponsored posts, flame wars. Write like real social and support teams "
    "and real users do, with natural slang, emoji and rhythm. Everything is fictional test data for a "
    "brand-governance tool. No slurs, no real people, no attacks on protected groups; roasts stay playful.\n\n"
    "Each request item lists placeholder slots like {{S2}}. Put every listed placeholder into the text exactly "
    "once, written literally with the double braces, where that kind of phrase would naturally go. A stat slot "
    "stands for a number only: write the unit or noun after it yourself (for percentages write the % sign "
    "after the slot). Write the brand name only through its brand slot, never directly.\n\n"
    'Return {"items": [{"id": ..., "title": ..., "body": ...}]}. Bodies are 2 to 6 short paragraphs '
    "separated by blank lines."
)


def plan_slots(reality: Reality, rng: random.Random) -> list[Slot]:
    spec = reality.spec
    slots = [Slot("S1", "brand", spec.name)]
    kinds = rng.sample(["term", "codename", "stat", "stat"], k=rng.randint(1, 3))
    for i, kind in enumerate(kinds, start=2):
        if kind == "term":
            slots.append(Slot(f"S{i}", "term", rng.choice(list(spec.banned))))
        elif kind == "codename":
            slots.append(Slot(f"S{i}", "codename", spec.codename))
        else:
            slots.append(Slot(f"S{i}", "stat", rng.choice(spec.stats).subject))
    return slots


def _describe(slot: Slot, reality: Reality) -> str:
    if slot.type == "brand":
        return f"{{{{{slot.id}}}}} = the brand name ({slot.ref})"
    if slot.type == "term":
        return f"{{{{{slot.id}}}}} = the phrase '{slot.ref}', used the way a hyped-up marketer would"
    if slot.type == "codename":
        return f"{{{{{slot.id}}}}} = the secret internal project name '{slot.ref}', teased or leaked casually"
    stat = next(s for s in reality.spec.stats if s.subject == slot.ref)
    unit = "a percentage" if stat.unit == "%" else f"a count of {stat.subject}"
    return f"{{{{{slot.id}}}}} = a number that is {unit}; say clearly what it counts"


async def llm_templates(llm, model: str, reality: Reality, rng: random.Random, n: int,
                        batch: int = 6) -> list[Template]:
    spec = reality.spec
    out: list[Template] = []
    for start in range(0, n, batch):
        items, plans = [], {}
        for i in range(start, min(n, start + batch)):
            genre = rng.choice(list(GENRES))
            slots = plan_slots(reality, rng)
            plans[f"i{i}"] = (genre, slots)
            items.append({"id": f"i{i}", "genre": GENRES[genre], "slots": [_describe(s, reality) for s in slots]})
        user = (f"Brand: {spec.name} ({spec.industry}), audience {spec.audience}, voice: {spec.voice}. "
                f"Products: {', '.join(spec.products)}.\n\nItems:\n" + "\n".join(map(str, items)))
        try:
            raw = await llm.json(model, CONTENT_SYSTEM, user)
        except RuntimeError as exc:
            print(f"  content batch skipped: {exc}", file=sys.stderr)
            continue
        returned = (raw.get("items") if isinstance(raw, dict) else raw) or []
        dropped: Counter[str] = Counter()
        for item in returned:
            if not isinstance(item, dict) or not isinstance(item.get("body"), str):
                dropped["malformed"] += 1
                continue
            if str(item.get("id")) not in plans:
                dropped[f"unknown id {item.get('id')!r}"] += 1
                continue
            genre, slots = plans[str(item["id"])]
            body = _defuse_brand(item["body"], spec.name)
            present = set(SLOT.findall(body))
            # The model sometimes leaves out a codename or banned-phrase slot
            # (it is reluctant to "leak" things). Keep the post and add the
            # missing phrase the way the offline lines do, so nothing is wasted.
            for s in slots:
                if s.id not in present and s.type != "brand":
                    body += " " + _fallback_line(s, reality, rng)
                    present.add(s.id)
            kept = [s for s in slots if s.id in present]
            # A slot the model used twice would give one plant two spans; keep the first.
            for s in kept:
                first = body.find("{{" + s.id + "}}") + len(s.id) + 4
                body = body[:first] + body[first:].replace("{{" + s.id + "}}", spec.name if s.type == "brand" else "")
            if not any(s.type != "brand" for s in kept):
                dropped["no test slot used"] += 1
                continue
            out.append(Template(genre, CHANNELS[genre], str(item.get("title") or GENRES[genre])[:200], body,
                                kept, "llm"))
        if dropped or not returned:
            print(f"  content batch: {len(returned)} returned, dropped {dict(dropped) or 'all (empty reply)'}",
                  file=sys.stderr)
    return out


def _fallback_line(slot: Slot, reality: Reality, rng: random.Random) -> str:
    marker = "{{" + slot.id + "}}"
    if slot.type == "term":
        return rng.choice(_TERM_LINES).format(x=marker, audience=reality.spec.audience)
    if slot.type == "codename":
        return rng.choice(_CODENAME_LINES).format(x=marker)
    return rng.choice(_STAT_LINES).format(x=marker, subject=slot.ref)


def _defuse_brand(body: str, name: str) -> str:
    """The model sometimes writes the brand directly despite the instruction.
    Normalise those to the correct casing so they never act as unplanned plants."""
    return re.sub(re.escape(name), name, body, flags=re.IGNORECASE)
