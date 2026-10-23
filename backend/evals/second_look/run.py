"""Second-look benchmark: does asking the larger model on close calls make must-rule judgements better?

A hand-labelled set of sentences against Kitepath's semantic must rules, written to be hard: digs by hint,
fear dressed as encouragement, results with half their caveats, offers aimed at teenagers through their
parents. Each sentence is judged the way production judges a paragraph (prism's rule question, the
Ollama judge, its resampling), by the small judge and by the larger one. The policies are then scored
from those answers:

- small only: what production did before;
- close-call cascade: the small judge, except a close call (within the band of the threshold) takes the
  larger model's answer. This was the first design; it never fired, because the small judge is wrong at
  its highest certainty, not near the line;
- both, larger decides: both judges asked at once, the larger one's answer used. What production does now
  for must rules, at the slower of the two calls.

The labels are one person's reading of the brand rules, so treat the numbers as a direction, not a
certification. This calls Ollama Cloud: about two calls per sentence, plus resamples on low certainty.

    .venv/bin/python -m evals.second_look.run --out evals/results/second_look.jsonl
    .venv/bin/python -m evals.second_look.run --report evals/results/second_look.jsonl
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import time
from pathlib import Path

# (rule code, text, breaks the rule?)
CASES = [
    ("MSG-RIVALS", "Unlike some other apps, our mentors actually reply.", True),
    ("MSG-RIVALS", "Tired of apps that just play videos at you? Try a mentor.", True),
    ("MSG-RIVALS", "Other platforms sell you a library. We sit with you.", True),
    ("MSG-RIVALS", "Still paying for courses you never finish elsewhere?", True),
    ("MSG-RIVALS", "We teach by doing: practice, feedback and a mentor.", False),
    ("MSG-RIVALS", "Lots of learners try many apps before they find a routine that sticks.", False),
    ("MSG-RIVALS", "Video lessons are only half of it; the other half is practice.", False),
    ("MSG-RIVALS", "Compare our plans and pick the one that suits your week.", False),
    ("MSG-EXAMSTRESS", "Don't let this board season be the one you regret.", True),
    ("MSG-EXAMSTRESS", "Every mark you lose now is a college you lose later.", True),
    ("MSG-EXAMSTRESS", "Toppers start today. Everyone else starts too late.", True),
    ("MSG-EXAMSTRESS", "Boards are close. Here is a calm two-week plan.", False),
    ("MSG-EXAMSTRESS", "Exams are stressful. Revise a little every day and ask when stuck.", False),
    ("MSG-EXAMSTRESS", "Missed a chapter? A mentor can help you catch up this weekend.", False),
    ("LEGAL-RESULTS", "Ananya topped her school in maths with us. Join now!", True),
    ("LEGAL-RESULTS", "98% of our learners scored above 90 last year.", True),
    ("LEGAL-RESULTS", "Rohan cleared JEE thanks to KiteMentor.", True),
    ("LEGAL-RESULTS", "Ananya (2026 boards, shared with her consent) scored in the nineties.", False),
    ("LEGAL-RESULTS", "Our maths course covers the whole Class 10 syllabus.", False),
    ("LEGAL-RESULTS", "Results season is coming: here is how to read your marksheet.", False),
    ("LEGAL-MINORS", "Hey Class 9! Ask your parents for the annual plan today.", True),
    ("LEGAL-MINORS", "Students, drop your number in the comments to win a free month.", True),
    ("LEGAL-MINORS", "Teens: subscribe now and unlock every course.", True),
    ("LEGAL-MINORS", "Parents can try a course free for seven days.", False),
    ("LEGAL-MINORS", "Class 9 learners: today's lesson is on fractions.", False),
    ("LEGAL-MINORS", "Parents, the annual plan covers both your children.", False),
    ("LEGAL-TESTIMONIAL", "\"Kitepath changed my life,\" says every learner we've met.", True),
    ("LEGAL-TESTIMONIAL", "Farah got a twenty lakh job because of Kitepath.", True),
    ("LEGAL-TESTIMONIAL", "Learners tell us it is the best decision they ever made.", True),
    ("LEGAL-TESTIMONIAL", "Farah now runs her team's weekly SQL reports.", False),
    ("LEGAL-TESTIMONIAL", "Meet Kabir, who started our Python track in June.", False),
    ("LEGAL-TESTIMONIAL", "Share your learning story with us; we will ask before we post it.", False),
]


async def _judge_all(model: str, rules: dict, out: list[dict], label: str) -> None:
    from verytas.checks.base import RuleView
    from verytas.checks.semantic import _rule_question
    from verytas.config import Settings
    from verytas.providers.ollama_judge import OllamaJudge

    settings = Settings()
    key = settings.ollama_api_key
    if key is None:
        raise SystemExit("OLLAMA_API_KEY is not set (backend/.env)")
    fallback = settings.ollama_api_key_fallback
    judge = OllamaJudge(key.get_secret_value(), model=model, base_url=settings.ollama_base_url,
                        resamples=settings.judge_resamples,
                        fallback_key=fallback.get_secret_value() if fallback else None)
    try:
        for row in out:
            r = rules[row["rule"]]
            view = RuleView(id=1, code=r["code"], category=r["category"], kind="semantic", severity=r["severity"],
                            title=r["title"], text=r["text"], good_examples=tuple(r["good_examples"]),
                            bad_examples=tuple(r["bad_examples"]))
            started = time.monotonic()
            try:
                answer = (await judge.ask(row["text"], {"rule_1": _rule_question(view)}))["rule_1"]
                row[label] = round(answer.p_yes, 3)
            except Exception as exc:  # noqa: BLE001, a failed call is recorded, not fatal to the run
                row[label] = None
                row[f"{label}_error"] = str(exc)[:200]
            row[f"{label}_s"] = round(time.monotonic() - started, 2)
            print(f"{label:5s} {row['rule']:18s} {row.get(label)} {row['text'][:60]}")
    finally:
        await judge.aclose()


def run(out_path: Path) -> None:
    from verytas.config import Settings
    from verytas.showcase import kitepath

    settings = Settings()
    rules = {r["code"]: r for r in kitepath.RULES}
    rows = [{"rule": code, "text": text, "breaks": breaks} for code, text, breaks in CASES]
    asyncio.run(_judge_all(settings.ollama_judge_model, rules, rows, "small"))
    asyncio.run(_judge_all(settings.second_look_model, rules, rows, "large"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("".join(json.dumps(r) + "\n" for r in rows))


def report(path: Path, threshold: float = 0.6, band: float = 0.1) -> str:
    rows = [json.loads(x) for x in path.read_text().splitlines() if x.strip()]
    rows = [r for r in rows if r.get("small") is not None and r.get("large") is not None]
    if not rows:
        return ("# Second-look benchmark\n\nNo sentence got an answer from both judges; "
                "see the errors in the results file.\n")

    def policy(r: dict, name: str) -> tuple[bool, float]:
        close = abs(r["small"] - threshold) <= band
        if name == "small only":
            return r["small"] >= threshold, r["small_s"]
        if name == "both, larger decides":
            return r["large"] >= threshold, max(r["small_s"], r["large_s"])
        return ((r["large"] if close else r["small"]) >= threshold,
                r["small_s"] + (r["large_s"] if close else 0.0))

    lines = ["# Second-look benchmark", "",
             f"{len(rows)} hand-labelled sentences against Kitepath's semantic must rules, judged as production "
             f"judges a paragraph. Flag threshold {threshold}, close call within {band} of it.", "",
             "| Policy | Correct | Caught (of breaking) | False flags (of fine) | Seconds per sentence (median) |",
             "|---|---|---|---|---|"]
    bad = [r for r in rows if r["breaks"]]
    fine = [r for r in rows if not r["breaks"]]
    for name in ("small only", "close-call cascade", "both, larger decides"):
        got = [(r, *policy(r, name)) for r in rows]
        correct = sum(flag == r["breaks"] for r, flag, _ in got)
        caught = sum(flag for r, flag, _ in got if r["breaks"])
        false = sum(flag for r, flag, _ in got if not r["breaks"])
        secs = statistics.median(s for _, _, s in got)
        lines.append(f"| {name} | {correct}/{len(rows)} | {caught}/{len(bad)} | {false}/{len(fine)} | {secs:.1f} |")
    close = [r for r in rows if abs(r["small"] - threshold) <= band]
    lines += ["", f"Close calls the cascade would have re-asked: {len(close)} of {len(rows)}. Where the judges "
              "disagree:", ""]
    changed = [r for r in rows if (r["small"] >= threshold) != (r["large"] >= threshold)]
    if changed:
        lines += ["| Rule | Sentence | Label | Small | Large |", "|---|---|---|---|---|"]
        for r in changed:
            lines.append(f"| {r['rule']} | {r['text']} | {'breaks' if r['breaks'] else 'fine'} | {r['small']} | "
                         f"{r['large']} |")
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=Path("evals/results/second_look.jsonl"))
    ap.add_argument("--report", type=Path, help="score an existing results file and stop")
    args = ap.parse_args()
    path = args.report or args.out
    if not args.report:
        run(args.out)
    md = report(path)
    path.with_suffix(".md").write_text(md)
    print(md)


if __name__ == "__main__":
    main()
