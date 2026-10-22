"""Realities: self-consistent fictional brand worlds.

A reality is everything a brand team would load into a governance tool on
day one: house style, banned and preferred wording, a confidential codename,
and a few statistics whose approved value changed over time. The simulator
generates content inside a reality and knows, from the reality alone, what a
correct reviewer should say about it.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import date, timedelta

from pydantic import BaseModel, Field, ValidationError


class StatIn(BaseModel):
    subject: str = Field(description="What is counted, plural noun phrase, e.g. 'restaurants on the platform'")
    unit: str = Field(description="Short unit word that appears after the number, e.g. 'restaurants' or '%'")
    old_value: int = Field(gt=0)
    new_value: int = Field(gt=0)


class RealityIn(BaseModel):
    name: str = Field(description="Brand name with distinctive internal casing, e.g. 'PayLoop' or 'nuTrail'")
    industry: str
    audience: str
    voice: str = Field(description="One sentence on how the brand sounds")
    products: list[str] = Field(min_length=2, max_length=4)
    banned: dict[str, str] = Field(min_length=3, max_length=6,
                                   description="Hype or off-brand words mapped to the plain word to use instead")
    codename: str = Field(description="Two-word internal project codename that must never be published")
    stats: list[StatIn] = Field(min_length=2, max_length=3)
    hype_examples: list[str] = Field(min_length=2, max_length=3,
                                     description="Off-brand sentences in exactly the voice the brand forbids")
    plain_examples: list[str] = Field(min_length=2, max_length=3, description="On-brand sentences")


@dataclass
class Reality:
    spec: RealityIn
    change_date: date
    embargo_until: date
    seed: int
    # Filled in once the reality is loaded into a workspace.
    fact_ids: dict[str, dict[str, int]] = field(default_factory=dict)
    colour: tuple[int, int, int] = (240, 130, 40)  # mascot colour, set from the brand name

    @property
    def name(self) -> str:
        return self.spec.name

    def wrong_casings(self) -> list[str]:
        n = self.name
        variants = {n.lower(), n.upper(), n[:1].upper() + n[1:].lower()}
        return sorted(v for v in variants if v != n)


# --- offline library ---------------------------------------------------------------------------
# Hand-written so a campaign can run with no key at all. Industries and voices
# differ on purpose: the same check should hold for a bank and a snack brand.

_LIBRARY: list[dict] = [
    {
        "name": "PayLoop", "industry": "consumer fintech", "audience": "freelancers in India",
        "voice": "calm, plain and precise; money is serious",
        "products": ["PayLoop Wallet", "LoopCard", "Invoice Buddy"],
        "banned": {"game-changer": "useful", "revolutionary": "new", "guaranteed returns": "returns",
                   "risk-free": "lower-risk", "crush it": "do well"},
        "codename": "Project Kestrel",
        "stats": [{"subject": "freelancers using PayLoop", "unit": "freelancers", "old_value": 40000,
                   "new_value": 65000},
                  {"subject": "average payout time in hours", "unit": "hours", "old_value": 48, "new_value": 24}],
        "hype_examples": ["This is the most insane money hack you will ever see!!!",
                          "Smash that button and watch your cash EXPLODE."],
        "plain_examples": ["Send an invoice and get paid within a day.", "Your money stays in a regulated account."],
    },
    {
        "name": "GrubHive", "industry": "food delivery", "audience": "students and young professionals",
        "voice": "warm, witty and quick, never mean to customers",
        "products": ["HivePass", "Midnight Menu", "GroupGrub"],
        "banned": {"cheapest": "low-cost", "hangry": "hungry", "insane deals": "good deals",
                   "best in the world": "well loved"},
        "codename": "Operation Honeycomb",
        "stats": [{"subject": "restaurants on GrubHive", "unit": "restaurants", "old_value": 1200, "new_value": 2100},
                  {"subject": "cities served", "unit": "cities", "old_value": 18, "new_value": 31}],
        "hype_examples": ["LITERALLY the greatest food app ever made, fight me.",
                          "Other apps are trash, we are the GOAT."],
        "plain_examples": ["Order from local spots near you.", "Split the bill with GroupGrub in two taps."],
    },
    {
        "name": "lumaSkin", "industry": "skincare", "audience": "people with sensitive skin",
        "voice": "gentle, honest and evidence-led; no miracle claims",
        "products": ["Calm Serum", "Barrier Balm", "Daily Shield SPF"],
        "banned": {"miracle": "effective", "anti-aging": "skin-supporting", "cure": "soothe",
                   "chemical-free": "fragrance-free", "flawless": "healthy-looking"},
        "codename": "Project Moonmilk",
        "stats": [{"subject": "customers who reported less redness", "unit": "%", "old_value": 72, "new_value": 81},
                  {"subject": "dermatologists in our advisory panel", "unit": "dermatologists", "old_value": 6,
                   "new_value": 11}],
        "hype_examples": ["This miracle serum will ERASE ten years overnight!!",
                          "Say goodbye to wrinkles forever, guaranteed."],
        "plain_examples": ["Calm Serum is tested on sensitive skin.", "Patch test first, then use daily."],
    },
    {
        "name": "ShipStack", "industry": "B2B developer tooling", "audience": "platform engineers",
        "voice": "direct, technical and dry; let the numbers talk",
        "products": ["ShipStack CI", "Preview Envs", "StackGuard"],
        "banned": {"blazing fast": "fast", "seamless": "smooth", "next-gen": "current",
                   "10x engineer": "engineer", "synergy": "teamwork"},
        "codename": "Project Glacier",
        "stats": [{"subject": "teams using ShipStack", "unit": "teams", "old_value": 800, "new_value": 1500},
                  {"subject": "median build time in seconds", "unit": "seconds", "old_value": 90, "new_value": 55}],
        "hype_examples": ["Our blazing fast next-gen synergy platform changes EVERYTHING.",
                          "Legacy CI is dead and we killed it."],
        "plain_examples": ["Median builds finish in under a minute.", "Preview environments spin up per pull request."],
    },
    {
        "name": "FizzUp", "industry": "sports drink", "audience": "amateur athletes and gym-goers",
        "voice": "energetic but inclusive; hype the effort, not the product",
        "products": ["FizzUp Zero", "Recovery Fizz", "Electro Shots"],
        "banned": {"beast mode": "focused", "no pain no gain": "train smart", "fat-burning": "refreshing",
                   "clinically proven": "tested"},
        "codename": "Codename Tidepool",
        "stats": [{"subject": "gyms stocking FizzUp", "unit": "gyms", "old_value": 3000, "new_value": 5200},
                  {"subject": "grams of sugar per can", "unit": "grams", "old_value": 9, "new_value": 4}],
        "hype_examples": ["UNLEASH THE BEAST and destroy every workout!!!",
                          "Weak people drink water. Winners drink FizzUp."],
        "plain_examples": ["Four grams of sugar per can.", "Cold, light and made for after training."],
    },
    {
        "name": "TutorNest", "industry": "edtech", "audience": "parents of school students",
        "voice": "reassuring, respectful and clear; never shame a child",
        "products": ["NestLive", "Doubt Desk", "Exam Sprint"],
        "banned": {"topper guarantee": "structured practice", "dumb": "stuck", "100% results": "steady progress",
                   "secret formula": "method"},
        "codename": "Project Lantern",
        "stats": [{"subject": "students on TutorNest", "unit": "students", "old_value": 90000, "new_value": 140000},
                  {"subject": "tutors with a teaching degree", "unit": "tutors", "old_value": 450, "new_value": 700}],
        "hype_examples": ["Your child will DEFINITELY top the class or your money back!!",
                          "Other kids are already ahead. Don't let yours fall behind."],
        "plain_examples": ["Live classes with a qualified tutor.", "Ask a doubt any time and get a clear answer."],
    },
]


def offline_reality(rng: random.Random, today: date, avoid: list[str] | None = None) -> Reality:
    fresh = [w for w in _LIBRARY if w["name"] not in (avoid or [])] or _LIBRARY
    return _finish(RealityIn.model_validate(rng.choice(fresh)), rng, today)


def _finish(spec: RealityIn, rng: random.Random, today: date) -> Reality:
    # Values must actually change, or "outdated" can't be told from "supported".
    for s in spec.stats:
        if s.old_value == s.new_value:
            s.new_value = s.old_value + max(1, s.old_value // 3)
    change = today - timedelta(days=rng.randint(30, 300))
    embargo = today + timedelta(days=rng.randint(20, 200))
    return Reality(spec=spec, change_date=change, embargo_until=embargo, seed=rng.randint(0, 2**31))


WORLD_SYSTEM = (
    "You invent fictional but realistic brands for testing a brand-governance tool. The brand must not be a "
    "real company. Keep it internally consistent: the banned words are things this brand's marketing team "
    "would actually be tempted to write, and the stats are believable for its size. Return one JSON object "
    "with keys: name, industry, audience, voice, products (2-4), banned (object, 3-6 entries, banned phrase -> "
    "plain replacement), codename (two words), stats (2-3 objects with subject, unit, old_value, new_value as "
    "whole numbers, new different from old), hype_examples (2-3), plain_examples (2-3)."
)


async def llm_reality(llm, model: str, rng: random.Random, today: date, avoid: list[str]) -> Reality:
    hint = rng.choice(["a regional bank", "a meme-heavy snack brand", "an indie game studio", "a telecom",
                       "a dating app", "a D2C fashion label", "a crypto exchange", "a hospital chain",
                       "a ride-hailing app", "a news podcast network", "an airline", "a pet-care startup",
                       "a government health campaign", "a streetwear drop", "an AI writing assistant"])
    user = f"Invent a brand that is {hint}. Do not reuse these names: {', '.join(avoid) or 'none'}."
    for _ in range(2):
        raw = await llm.json(model, WORLD_SYSTEM, user, temperature=1.0)
        try:
            return _finish(RealityIn.model_validate(raw), rng, today)
        except ValidationError as exc:
            user += f"\nYour last answer failed validation: {str(exc)[:300]}"
    return offline_reality(rng, today)
