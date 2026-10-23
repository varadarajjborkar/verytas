"""Precedent benchmark: do past decisions on similar words predict what a reviewer decides next?

Reads a seeded showcase database (`python -m verytas.cli seed-showcase`), whose four companies carry
weeks of reviewer decisions. Decisions are replayed in time order. For each decision in the held-out last
30%, three predictors guess whether the reviewer upheld the finding (accepted or fixed it) or dismissed
it, using only decisions made before it in the same workspace:

- always upheld: the base rate;
- rule majority: what reviewers decided most often on this rule so far;
- precedent: the two nearest earlier cases on the same rule (prism/precedent.py), falling back to the
  rule majority when there are none.

The seeded reviewers decide by persona (each has an acceptance rate per rule), so this is a hard test for
word similarity: a precedent can only help where the same kind of words got the same answer before.
Only cases that say whether the words break the rule vote (an "intentional" or "guideline unclear"
dismissal does not), and quotes are compared unmasked, as the seeded demo has no codenames in them.

The committed `backend/showcase.db` is a small sample; the numbers in evals/results come from a full
seed of all four companies (`python -m verytas.cli seed-showcase --db <path>`).

    .venv/bin/python -m evals.precedent.run --db /path/to/showcase.db
"""

from __future__ import annotations

import argparse
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from verytas.prism.precedent import Book, Case, words


def _cases(db: Path) -> list[tuple[int, bool, Case]]:
    con = sqlite3.connect(db)
    rows = con.execute("""
        select c.workspace_id, r.code, f.id, f.quote, d.action, d.reason_code, d.reason_text, d.created_at, u.name,
               f.model is not null
        from decisions d
        join findings f on f.id = d.finding_id
        join rules r on r.id = f.rule_id
        join reviews rv on rv.id = f.review_id
        join content_versions v on v.id = rv.version_id
        join contents c on c.id = v.content_id
        join users u on u.id = d.actor_id
        where d.id in (select max(id) from decisions group by finding_id)
          and d.action in ('accepted', 'edited', 'rejected') and f.quote is not null
        order by d.created_at, d.id""").fetchall()
    out = []
    for ws, code, fid, quote, action, reason, why, at, by, modelled in rows:
        q = quote[:280]
        out.append((ws, bool(modelled), Case(code, q, action, reason, why, by,
                                             datetime.fromisoformat(at), fid, words(q))))
    return out


def run(db: Path, held_out: float = 0.3) -> str:
    rows = _cases(db)
    cut = int(len(rows) * (1 - held_out))
    books: dict[int, Book] = defaultdict(Book)
    votes: dict[tuple[int, str], Counter] = defaultdict(Counter)
    tally = {name: Counter() for name in ("always upheld", "rule majority", "precedent")}
    modelled_tally = {name: Counter() for name in tally}
    used = Counter()
    on_precedent = {name: Counter() for name in ("rule majority", "precedent")}
    for i, (ws, modelled, case) in enumerate(rows):
        truth = case.action in ("accepted", "edited")
        if i >= cut:
            seen = votes[(ws, case.rule_code)]
            majority = seen[True] >= seen[False]
            near = books[ws].nearest(case.rule_code, case.quote, where=lambda c: c.breaks is not None)
            if near:
                up = sum(c.breaks for c in near)
                guess = majority if up * 2 == len(near) else up * 2 > len(near)
                used["with precedent"] += 1
            else:
                guess = majority
                used["fell back"] += 1
            if near:
                for name, g in (("rule majority", majority), ("precedent", guess)):
                    on_precedent[name]["right" if g == truth else "wrong"] += 1
            for name, g in (("always upheld", True), ("rule majority", majority), ("precedent", guess)):
                for t in (tally, modelled_tally) if modelled else (tally,):
                    t[name]["right" if g == truth else "wrong"] += 1
        # Learn after predicting, so a decision never predicts itself.
        books[ws].cases.setdefault(case.rule_code, []).insert(0, case)
        votes[(ws, case.rule_code)][truth] += 1

    def table(t: dict) -> list[str]:
        out = ["| Predictor | Agrees with the reviewer |", "|---|---|"]
        for name, c in t.items():
            n = c["right"] + c["wrong"]
            out.append(f"| {name} | {c['right']}/{n} ({c['right'] / max(n, 1):.0%}) |")
        return out

    lines = ["# Precedent benchmark", "",
             f"{len(rows)} reviewer decisions from the seeded demo, replayed in time order; the last "
             f"{len(rows) - cut} are predicted from the ones before them.", "", "All findings:", "", *table(tally),
             "", "Model-judged findings only (where precedents are shown and given to the judge):", "",
             *table(modelled_tally), "",
             f"Predictions with a precedent: {used['with precedent']}; with none similar enough, fell back to the "
             f"rule majority: {used['fell back']}.", "", "Only where a precedent exists:", "", *table(on_precedent)]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--out", type=Path, default=Path("evals/results/precedent.md"))
    args = ap.parse_args()
    md = run(args.db)
    args.out.write_text(md)
    print(md)


if __name__ == "__main__":
    main()
