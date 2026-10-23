"""Demo companies that look like real brand teams at work.

    python -m verytas.cli seed-showcase --db showcase.db --write-env ../web/.env.local

Four companies, each its own workspace in one database, with weeks of history: pieces at every stage, sent back
and fixed, approved and published, escalations waiting, disputes ruled on, brand events running and scheduled.
Everything goes through the real API (offline models) on a simulated clock, so every review, decision and
timeline entry is genuine and has a believable age. Tokens are written to the env and accounts files, never
printed. `kitepath` also carries the mascot drawing the fidelity tests use."""

from verytas.showcase.engine import seed
from verytas.showcase.kitepath import BRAND, _kit

__all__ = ["BRAND", "_kit", "seed"]
