"""Routine work, generated from banks of lines per creator persona, so a company has weeks of believable
history without every post being written out by hand. Seeded by the company key: two runs give the same posts.

A persona is a way of working, not a person: how often they slip, what kind of slip, how fast they fix it,
and how much of their work is still waiting. The scripted stories in each company module sit on top."""

from __future__ import annotations

import random
from dataclasses import dataclass

from verytas.showcase.spec import Flow, Member, Piece


@dataclass(frozen=True)
class Slip:
    title: str
    channel: str
    bad: str
    good: str
    note: str  # what the reviewer says when sending it back


# slip chance, then weights for how a clean piece ends: published, approved, in review, draft, back-and-waiting
PERSONAS: dict[str, dict] = {
    "careful": {"slip": 0.06, "pace": 1.3, "end": (0.62, 0.14, 0.14, 0.05, 0.05), "fix_h": (3, 12)},
    "intern": {"slip": 0.34, "pace": 1.1, "end": (0.42, 0.10, 0.18, 0.15, 0.15), "fix_h": (10, 60)},
    "agency": {"slip": 0.30, "pace": 0.9, "end": (0.45, 0.15, 0.20, 0.05, 0.15), "fix_h": (20, 70)},
    "regional": {"slip": 0.16, "pace": 1.0, "end": (0.55, 0.12, 0.17, 0.08, 0.08), "fix_h": (6, 30)},
    "influencer": {"slip": 0.28, "pace": 0.7, "end": (0.40, 0.12, 0.20, 0.10, 0.18), "fix_h": (12, 72)},
    "marketer": {"slip": 0.20, "pace": 1.0, "end": (0.55, 0.15, 0.15, 0.05, 0.10), "fix_h": (4, 24)},
}


def routine(company_key: str, creators: list[Member], clean: list[tuple[str, str, str]],
            slips: dict[str, list[Slip]], first_day: float, last_day: float, tag: str = "g",
            rate: float = 0.09) -> list[Piece]:
    """`first_day` is the oldest (days ago), `last_day` the newest. `rate` is the daily chance a creator posts."""
    rng = random.Random(f"{company_key}:routine")
    out: list[Piece] = []
    pool = {m.key: list(clean) for m in creators}
    for m in creators:
        rng.shuffle(pool[m.key])
    spec_for = {m.key: PERSONAS[m.persona] for m in creators}
    # Slips are dealt round the persona's list so every kind of mistake shows up, not whichever the dice favour.
    queues: dict[str, list[Slip]] = {k: list(v) for k, v in slips.items()}
    for q in queues.values():
        rng.shuffle(q)
    d = first_day
    n = 0
    while d > last_day:
        for m in creators:
            p = spec_for[m.key]
            if rng.random() > rate * p["pace"]:
                continue
            days_ago = max(last_day, d - rng.random() * 1.6)
            n += 1
            key = f"{tag}{n}"
            mine = queues.get(m.persona, [])
            if mine and rng.random() < p["slip"]:
                s = mine.pop(0)
                mine.append(s)
                out.append(_slipped(key, m, s, days_ago, rng, p))
                continue
            if not pool[m.key]:
                pool[m.key] = list(clean)
                rng.shuffle(pool[m.key])
            title, channel, body = pool[m.key].pop()
            out.append(Piece(key, m.key, title, channel, body, days_ago, _clean_flow(rng, p, days_ago)))
        d -= 1.0
    return out


def _clean_flow(rng: random.Random, p: dict, days_ago: float) -> Flow:
    end = rng.choices(["pub", "appr", "rev", "draft", "back"], weights=p["end"])[0]
    send = (round(rng.uniform(0.3, 6), 1), "send", {})
    if end == "draft":
        return []
    t = send[0]
    flow: Flow = [send]
    if end == "rev":
        return flow
    if rng.random() < 0.5:
        flow.append((t + 2, "autodecide", {"by": "reviewer" if rng.random() < 0.6 else "approver"}))
    if end == "back":
        flow.append((t + rng.uniform(4, 20), "back", {"note": "Tighten the opening and check the tone against our "
                                                              "published posts."}))
        return flow
    flow.append((t + rng.uniform(3, 16), "approve", {}))
    if end == "pub":
        flow.append((t + rng.uniform(20, 48), "publish", {}))
    return flow


def _slipped(key: str, m: Member, s: Slip, days_ago: float, rng: random.Random, p: dict) -> Piece:
    lo, hi = p["fix_h"]
    t = round(rng.uniform(0.3, 5), 1)
    by = "reviewer" if rng.random() < 0.55 else "approver"
    flow: Flow = [(t, "send", {}), (t + 2, "autodecide", {"by": by}), (t + rng.uniform(3, 14), "back", {"note": s.note})]
    r = rng.random()
    if r < 0.18:
        return Piece(key, m.key, s.title, s.channel, s.bad, days_ago, flow)  # sent back, creator hasn't fixed it yet
    fix_at = flow[-1][0] + rng.uniform(lo, hi)
    flow += [(fix_at, "fix", {"body": s.good}), (fix_at + 0.5, "send", {})]
    if r < 0.30:
        return Piece(key, m.key, s.title, s.channel, s.bad, days_ago, flow)  # fixed, waiting for the reviewer
    flow.append((fix_at + rng.uniform(3, 20), "approve", {}))
    if r < 0.85:
        flow.append((fix_at + rng.uniform(22, 50), "publish", {}))
    return Piece(key, m.key, s.title, s.channel, s.bad, days_ago, flow)
