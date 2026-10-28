"""Recall benchmark: does Inki get the turns of a long conversation that its question depends on?

Each case is a conversation between a creator and the brand team, 40 to 90 turns long, with a decision made
early (a logo variant, a date legal cleared, a budget, a channel), then the ordinary traffic of a working
thread: acknowledgements, chatter, other decisions on look-alike subjects, and sometimes the decision
changing later. The last turn asks Inki about it, in other words than the decision used, sometimes in
Hinglish. The needed turns are labelled.

Policies:
- window: the most recent INKI_TRANSCRIPT turns only (Inki before this change);
- recall: the recent turns plus the earlier ones verytas/memory/thread.py picks, for each embedding model.

Scored per case: hit (every needed turn reached Inki), latest (when the decision changed, the change
reached it), and how many earlier turns were added (the cost of a hit: fewer is better). Deterministic,
offline apart from downloading the embedding models once.

    .venv/bin/python -m evals.memory.run --models hash BAAI/bge-small-en-v1.5 \
        sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 --out evals/results/memory.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import random
import resource
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path

from verytas.api.messages import INKI_TRANSCRIPT
from verytas.memory.embed import embedder_for
from verytas.memory.thread import NoCache, Turn, earlier_turns, expand

CHATTER = [
    "ok", "sounds good", "will check and come back", "thanks!", "on it", "noted", "sure, one sec", "lunch now",
    "back", "cool", "any update?", "not yet, still on it", "got it", "👍", "haan theek hai", "done", "perfect",
    "let me see", "can we talk tomorrow?", "yes tomorrow works", "sent the draft", "looking now", "hmm",
    "one more thing", "that's fine", "will update the caption", "ok uploading v2", "great, thanks",
    "chalo, kal baat karte hain", "is the review done?", "it's running", "ok cool", "sorry, was in a meeting",
]
# Decisions on other subjects, with words close to the real ones: the distractors.
OTHER = [
    "For the Diwali story use the red logo, the blue one is only for LinkedIn.",
    "Budget for the photo shoot is separate, ask finance.",
    "Legal said testimonials need written consent from parents.",
    "Post the reel on Instagram first, YouTube Shorts next week.",
    "Don't mention the price in the teaser.",
    "Use 'live class', never 'webinar'.",
    "The mentor count we can quote is 1,200.",
    "Keep the hashtags to three at most.",
    "Schedule the carousel for Friday 6 pm.",
    "The scholarship page goes live on the 3rd.",
]


@dataclass
class Case:
    name: str
    decision: list[str]                     # the turns that hold the answer (the second is usually the reply)
    question: str
    change: list[str] = field(default_factory=list)  # a later turn that changes the decision, when there is one
    kind: str = "en"


CASES = [
    Case("logo", ["For the festive post use the blue logo variant, not the red one.", "Understood, blue variant."],
         "@Inki which logo colour did we settle on for the festive post?"),
    Case("logo-hi", ["For the festive post use the blue logo variant, not the red one.", "Understood, blue variant."],
         "@Inki festive post mein kaunsa logo lagana tha?", kind="hinglish-q"),
    Case("embargo", ["Legal cleared the Falcon name, but only after the 12th. Until then say 'something new'.",
                     "Got it, no name before the 12th."], "@Inki when can I start using the product name?"),
    Case("budget", ["Approved budget for the creator reel is 20k, including editing.", "Thanks, 20k all in."],
         "@Inki how much money do I have for the reel?"),
    Case("channel", ["Let's run this one on LinkedIn only, it's for parents not students.", "Makes sense, LinkedIn."],
         "@Inki where are we posting this piece?"),
    Case("tone", ["Please keep it calm, no countdowns or 'last chance' lines, exam season is stressful.",
                  "Will remove the countdown."], "@Inki what did the brand team say about urgency in the copy?"),
    Case("stat", ["You can quote 82% only with the year and the sample, '2026 boards, 14,000 learners'.",
                  "Adding the year and sample."], "@Inki what has to go next to the 82 percent figure?"),
    Case("deadline-hi", ["Final draft chahiye Thursday tak, Friday ko schedule karenge.", "Thursday tak bhej dungi."],
         "@Inki when is the final draft due?", kind="hinglish-fact"),
    Case("logo-change", ["For the festive post use the blue logo variant, not the red one.",
                         "Understood, blue variant."],
         "@Inki which logo do we use for the festive post?",
         change=["Update: marketing wants the red logo after all for the festive post, sorry for the churn."]),
    Case("budget-change", ["Approved budget for the creator reel is 20k, including editing.", "Thanks, 20k all in."],
         "@Inki what's the reel budget now?",
         change=["Finance came back, reel budget is cut to 15k, editing included."]),
    Case("music", ["No trending audio on this one, use the licensed track from our library.", "Okay, library track."],
         "@Inki can I use a trending sound on the reel?"),
    Case("caption-len", ["Keep the X post under 200 characters, it gets cut in previews.", "Will trim it."],
         "@Inki is there a length limit for the X version?"),
]


# Written after the policy was tuned on CASES and never tuned against: the honest number.
HELD_OUT = [
    Case("thumb", ["Thumbnail: use the photo of Ananya at the whiteboard, not the stock image.", "Swapping it now."],
         "@Inki whose picture goes on the cover image?"),
    Case("cta", ["Last line should say 'Start free for 7 days', no 'Buy now'.", "Changed the last line."],
         "@Inki what should the call to action be?"),
    Case("consent", ["We have Riya's mother's written consent, so her name and marks can be used.", "Great, thanks."],
         "@Inki are we allowed to name the student in the story?"),
    Case("tag", ["Tag the partner school's handle in the first comment, not in the caption.", "Okay, first comment."],
         "@Inki where does the school's handle go?"),
    Case("lang", ["Make a Tamil version too, the Chennai centre will share it.", "Will get the Tamil copy done."],
         "@Inki which extra language did they ask for?"),
    Case("slot-hi", ["Post Saturday subah 10 baje karna, weekdays pe reach kam hai.", "Saturday 10 am set kar diya."],
         "@Inki posting time kya decide hua tha?", kind="hinglish-fact"),
    Case("price-hi", ["Price mat likhna post mein, sirf 'affordable plans' bolna.", "Theek hai, price hata diya."],
         "@Inki can I mention how much the plan costs?", kind="hinglish-fact"),
    Case("rival-hi", ["Never name SkillSprint, even as a comparison.", "Noted, no competitor names."],
         "@Inki dusre app ka naam le sakte hain kya comparison mein?", kind="hinglish-q"),
    Case("length", ["Cut the video to 45 seconds, anything longer drops off on Reels.", "Trimming to 45s."],
         "@Inki how long should the final cut be?"),
    Case("approval", ["Arjun has to sign off anything that mentions results, not just me.",
                      "I'll send it to Arjun too."],
         "@Inki who needs to approve the results post?"),
    Case("hashtag-change", ["Use #KiteLearns and #BoardPrep only.", "Okay, those two."], "@Inki which hashtags now?",
         change=["Drop #BoardPrep, legal flagged it; #KiteLearns and #StudySmart instead."]),
    Case("date-change", ["The webinar recording goes up on the 5th.", "Will plan around the 5th."],
         "@Inki when does the recording go live?",
         change=["Small change: the recording is delayed to the 8th because of edits."]),
]


# Written before the follow-up rule (a picked turn brings later turns on the same subject) and used to judge it:
# decisions that change, some twice, with the change worded unlike the original.
FRESH = [
    Case("venue", ["The meetup is at the Indiranagar centre, 4 pm.", "Indiranagar, 4 pm, got it."],
         "@Inki where is the meetup happening?",
         change=["Heads up, we moved the meetup to the Koramangala office because of the rain, same time."]),
    Case("discount", ["You can mention 20% off for the first month.", "20% first month, okay."],
         "@Inki what offer can I put in the post?",
         change=["Finance says no percentages this quarter, just say 'special launch pricing'."]),
    Case("format", ["Do it as a carousel, 6 slides max.", "Carousel, 6 slides."],
         "@Inki what format did we agree for this post?",
         change=["Thinking again, let's make it a single image, carousels are underperforming."]),
    Case("owner", ["Meera will review the final version, not Arjun.", "Okay, sending it to Meera."],
         "@Inki who reviews the final version?",
         change=["Meera is on leave next week so Arjun picks up the final review after all."]),
]


async def _picked(model, turns, question, recent, k, phrasings=None):
    return await earlier_turns(NoCache(), model, 1, turns, question, k, phrasings)


def build(case: Case, rng: random.Random) -> tuple[list[Turn], set[int], set[int]]:
    """A conversation for the case: (turns, ids holding the answer, ids holding a later change)."""
    turns: list[Turn] = []

    def say(text, who=None):
        turns.append(Turn(len(turns) + 1, who or rng.choice(["Creator", "Brand team"]), text))
        return turns[-1].message_id

    for _ in range(rng.randint(2, 8)):
        say(rng.choice(CHATTER))
    need = {say(case.decision[0], "Brand team" if not case.kind.startswith("hinglish-f") else "Brand team")}
    need |= {say(t, "Creator") for t in case.decision[1:]}
    later: set[int] = set()
    length = rng.randint(40, 90)
    change_at = rng.randint(len(turns) + 10, length - INKI_TRANSCRIPT - 2) if case.change else None
    while len(turns) < length:
        if change_at and len(turns) == change_at:
            later |= {say(t, "Brand team") for t in case.change}
            continue
        say(rng.choice(OTHER) if rng.random() < 0.12 else rng.choice(CHATTER))
    say(case.question, "Creator")
    return turns, need, later


async def _phrasings(convs) -> dict[str, list[str]]:
    """The fast model's rewordings of each question, asked once per question (it is the same in every seed)."""
    from verytas.config import Settings
    from verytas.providers.ollama import OllamaLLM

    st = Settings()
    llm = OllamaLLM(st.ollama_api_key.get_secret_value(), model=st.ollama_model, fast_model=st.ollama_fast_model)
    out: dict[str, list[str]] = {}
    for _, turns, _, _ in convs:
        q = turns[-1].text
        if q not in out:
            out[q] = await expand(llm, q, [t.text for t in turns[-3:-1]])
    await llm.aclose()
    return out


async def run(models: list[str], seeds: int, k: int, cases: list[Case], with_expansion: bool = False) -> dict:
    out: dict = {"cases": len(cases) * seeds, "k": k, "window": INKI_TRANSCRIPT, "policies": {}}
    variants = [(c, s) for c in cases for s in range(seeds)]
    convs = [(c, *build(c, random.Random(f"{c.name}:{s}"))) for c, s in variants]
    reworded = await _phrasings(convs) if with_expansion else {}
    if reworded:
        out["phrasings"] = reworded
    for policy in ["window", *models]:
        rows = []
        model = embedder_for(policy) if policy != "window" else None
        if model is not None:
            model.passages(["warm up"])
        started = time.perf_counter()
        for case, turns, need, later in convs:
            question = turns[-1].text
            recent_turns = turns[-INKI_TRANSCRIPT - 1:-1]
            seen = {t.message_id for t in recent_turns}
            added = 0
            if model is not None:
                older = turns[:-INKI_TRANSCRIPT - 1]
                got = await _picked(model, older, question, [(t.who, t.text) for t in recent_turns], k,
                                    reworded.get(question))
                seen |= {t.message_id for t in got}
                added = len(got)
            rows.append({"case": case.name, "kind": case.kind, "hit": need <= seen or bool(later and later <= seen),
                         "need_all": need <= seen, "latest": (later <= seen) if later else None, "added": added})
        elapsed = time.perf_counter() - started
        latest = [r["latest"] for r in rows if r["latest"] is not None]
        out["policies"][policy] = {
            "hit_rate": round(statistics.mean(r["hit"] for r in rows), 3),
            "by_kind": {kind: round(statistics.mean(r["hit"] for r in rows if r["kind"] == kind), 3)
                        for kind in sorted({r["kind"] for r in rows})},
            "latest_rate": round(statistics.mean(latest), 3) if latest else None,
            "added_mean": round(statistics.mean(r["added"] for r in rows), 2),
            "ms_per_case": round(1000 * elapsed / len(rows), 1),
            "misses": sorted({r["case"] for r in rows if not r["hit"]}),
        }
        print(policy, json.dumps(out["policies"][policy]))
    out["peak_rss_mb"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024 / 1024, 1)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", nargs="+", default=["hash", "BAAI/bge-small-en-v1.5"])
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--k", type=int, default=6)
    ap.add_argument("--set", choices=["tuned", "held-out", "fresh", "all"], default="all")
    ap.add_argument("--expand", action="store_true", help="reword each question with the fast model first")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args()
    cases = {"tuned": CASES, "held-out": HELD_OUT, "fresh": FRESH, "all": CASES + HELD_OUT + FRESH}[args.set]
    result = asyncio.run(run(args.models, args.seeds, args.k, cases, args.expand))
    print("peak RSS", result["peak_rss_mb"], "MB")
    if args.out:
        args.out.write_text(json.dumps(result, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
