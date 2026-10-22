"""Markdown report for one campaign, built from the local store."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from blackbox.store import Store

REPORTS = Path(__file__).resolve().parent / ".runs" / "reports"


def _pct(a: int, b: int) -> str:
    return f"{100 * a / b:.0f}%" if b else "n/a"


def render(store: Store, run_id: int) -> str:
    started, finished, config, summary = store.db.execute(
        "SELECT started, finished, config, summary FROM runs WHERE id = ?", (run_id,)).fetchone()
    config, summary = json.loads(config), json.loads(summary or "{}")
    rows = store.db.execute("SELECT case_id, genre, source, body, verdicts FROM cases WHERE run_id = ?",
                            (run_id,)).fetchall()

    by_tier: dict[str, Counter[str]] = defaultdict(Counter)
    by_arm: dict[str, Counter[str]] = defaultdict(Counter)
    by_genre: dict[str, Counter[str]] = defaultdict(Counter)
    unplanned: Counter[str] = Counter()
    examples: dict[str, tuple[str, str, str]] = {}
    for case_id, genre, _source, body, verdicts in rows:
        v = json.loads(verdicts)
        for p in v["plants"]:
            tier = p["tier"] if p["expect"] == "flag" else "control"
            by_tier[tier][p["verdict"]] += 1
            by_arm[p["arm"]][p["verdict"]] += 1
            by_genre[genre][p["verdict"]] += 1
            if p["verdict"] in ("missed", "false_positive") and p["arm"] not in examples:
                s, e = p["span"]
                context = body[max(0, s - 60):e + 60].replace("\n", " ") if s >= 0 else "(attachment)"
                examples[p["arm"]] = (case_id, p["text"], context)
        for u in v["unplanned"]:
            unplanned[f"{u['category']} / {u['title']} ({u['level']})"] += 1

    failures = store.db.execute(
        "SELECT kind, count(*), min(detail) FROM failures WHERE run_id = ? AND kind NOT IN ('missed', "
        "'false_positive') GROUP BY kind ORDER BY 2 DESC", (run_id,)).fetchall()

    lines = [f"# Black-box run {run_id}", "",
             f"Realities: {', '.join(summary.get('realities', []))}. Cases: {summary.get('cases', 0)}. "
             f"Generator: {config['gen']}. Reviews: {config['review']}. Time: {summary.get('seconds')} s. "
             f"LLM calls: {summary.get('llm_calls', 0)} ({summary.get('llm_tokens', 0)} tokens).", "",
             "## Detection", "",
             "The evolver spends most of each generation on arms that failed before, so these rates run lower "
             "than on a uniform sample. Read them as 'how bad are the weak spots', and use the arm table for "
             "per-technique rates.", "",
             "| Plants | Caught | Missed | Recall |", "|---|---|---|---|"]
    for tier in ("core", "evasion", "adversarial"):
        c = by_tier.get(tier, Counter())
        lines.append(f"| {tier} | {c['caught']} | {c['missed']} | {_pct(c['caught'], c['caught'] + c['missed'])} |")
    ctl = by_tier.get("control", Counter())
    lines += ["", f"Controls (should pass): {ctl['ok']} passed, {ctl['false_positive']} flagged "
                  f"(false-positive rate {_pct(ctl['false_positive'], ctl['ok'] + ctl['false_positive'])}).", ""]

    lines += ["## Contract and invariant failures", ""]
    if failures:
        lines += ["| Kind | Count | Example |", "|---|---|---|"]
        lines += [f"| {k} | {n} | {d[:160].replace('|', '/')} |" for k, n, d in failures]
    else:
        lines.append("None.")

    weak = sorted(((a, c) for a, c in by_arm.items() if c["missed"] + c["false_positive"]),
                  key=lambda x: -(x[1]["missed"] + x[1]["false_positive"]))
    lines += ["", "## Weakest arms", "", "| Arm | Failures | Trials | Example |", "|---|---|---|---|"]
    for arm, c in weak[:15]:
        fails = c["missed"] + c["false_positive"]
        ex = examples.get(arm)
        sample = f"`{ex[1][:40]!r}` in \"...{ex[2][:90]}...\"" if ex else ""
        lines.append(f"| {arm} | {fails} | {sum(c.values())} | {sample.replace('|', '/')} |")

    lines += ["", "## Recall by genre", "", "| Genre | Caught | Missed |", "|---|---|---|"]
    for genre, c in sorted(by_genre.items(), key=lambda x: -x[1]["missed"]):
        lines.append(f"| {genre} | {c['caught']} | {c['missed']} |")

    lines += ["", "## Findings nobody planted (top 10)", "",
              "Not necessarily wrong: generated text can contain real issues. Review before calling these false "
              "positives.", ""]
    lines += [f"- {n} x {k}" for k, n in unplanned.most_common(10)] or ["None."]
    return "\n".join(lines) + "\n"


def write(store: Store, run_id: int) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"run-{run_id}.md"
    path.write_text(render(store, run_id))
    return path
