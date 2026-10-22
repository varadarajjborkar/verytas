"""Local SQLite memory for the simulator (blackbox/.runs/blackbox.db, gitignored).

Arm statistics persist across runs, so every campaign starts where the last
one left off: arms that keep finding failures get more of the budget, arms
that always pass fade to an exploration trickle. Thompson sampling over a
Beta(failures + 1, passes + 1) posterior does that without tuning knobs.
"""

from __future__ import annotations

import json
import random
import sqlite3
import time
from pathlib import Path
from typing import Any

DB = Path(__file__).resolve().parent / ".runs" / "blackbox.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS arms (arm TEXT PRIMARY KEY, trials INTEGER NOT NULL DEFAULT 0,
                                 failures INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS runs (id INTEGER PRIMARY KEY AUTOINCREMENT, started REAL, finished REAL,
                                 config TEXT, summary TEXT);
CREATE TABLE IF NOT EXISTS cases (run_id INTEGER, case_id TEXT, generation INTEGER, reality TEXT, genre TEXT,
                                  channel TEXT, source TEXT, body TEXT, plants TEXT, findings TEXT,
                                  verdicts TEXT, PRIMARY KEY (run_id, case_id));
CREATE TABLE IF NOT EXISTS failures (id INTEGER PRIMARY KEY AUTOINCREMENT, run_id INTEGER, case_id TEXT,
                                     kind TEXT, arm TEXT, detail TEXT);
CREATE TABLE IF NOT EXISTS adversarial (family TEXT, term TEXT, text TEXT, born_run INTEGER,
                                        PRIMARY KEY (family, term, text));
"""


class Store:
    def __init__(self, path: Path = DB) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.executescript(_SCHEMA)

    def close(self) -> None:
        self.db.close()

    # --- runs ------------------------------------------------------------------------------------

    def start_run(self, config: dict[str, Any]) -> int:
        cur = self.db.execute("INSERT INTO runs (started, config) VALUES (?, ?)", (time.time(), json.dumps(config)))
        self.db.commit()
        return int(cur.lastrowid)

    def finish_run(self, run_id: int, summary: dict[str, Any]) -> None:
        self.db.execute("UPDATE runs SET finished = ?, summary = ? WHERE id = ?",
                        (time.time(), json.dumps(summary), run_id))
        self.db.commit()

    def last_run(self) -> int | None:
        row = self.db.execute("SELECT max(id) FROM runs WHERE finished IS NOT NULL").fetchone()
        return row[0]

    def save_case(self, run_id: int, row: dict[str, Any]) -> None:
        self.db.execute(
            "INSERT OR REPLACE INTO cases VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, row["case_id"], row["generation"], row["reality"], row["genre"], row["channel"], row["source"],
             row["body"], json.dumps(row["plants"]), json.dumps(row["findings"]), json.dumps(row["verdicts"])),
        )

    def add_failure(self, run_id: int, case_id: str, kind: str, arm: str | None, detail: str) -> None:
        self.db.execute("INSERT INTO failures (run_id, case_id, kind, arm, detail) VALUES (?,?,?,?,?)",
                        (run_id, case_id, kind, arm, detail[:2000]))

    def commit(self) -> None:
        self.db.commit()

    # --- arms ------------------------------------------------------------------------------------

    def record(self, arm: str, failed: bool) -> None:
        self.db.execute("INSERT INTO arms (arm, trials, failures) VALUES (?, 1, ?) ON CONFLICT(arm) DO UPDATE "
                        "SET trials = trials + 1, failures = failures + excluded.failures", (arm, int(failed)))

    def arm_stats(self) -> dict[str, tuple[int, int]]:
        return {a: (t, f) for a, t, f in self.db.execute("SELECT arm, trials, failures FROM arms")}

    def pick(self, arms: list[str], rng: random.Random) -> str:
        """Thompson sampling on the chance an arm exposes a failure."""
        stats = self.arm_stats()

        def draw(arm: str) -> float:
            trials, failures = stats.get(arm, (0, 0))
            return rng.betavariate(failures + 1, trials - failures + 1)

        return max(arms, key=draw)

    # --- adversarial variants --------------------------------------------------------------------

    def add_adversarial(self, family: str, term: str, texts: list[str], run_id: int) -> int:
        before = self.db.total_changes
        self.db.executemany("INSERT OR IGNORE INTO adversarial VALUES (?,?,?,?)",
                            [(family, term, t, run_id) for t in texts])
        self.db.commit()
        return self.db.total_changes - before

    def adversarial(self, family: str, term: str) -> list[str]:
        return [r[0] for r in self.db.execute("SELECT text FROM adversarial WHERE family = ? AND term = ?",
                                              (family, term))]
