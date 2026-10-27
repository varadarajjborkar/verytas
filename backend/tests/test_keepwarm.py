"""The keep-warm timer: only in its window, never past its budget, and nothing at all after its end date."""

from __future__ import annotations

import asyncio
from datetime import datetime

from verytas.vision.keepwarm import IST, Plan, read_minutes, tick, write_minutes


def _plan(tmp_path, budget=10.0):
    return Plan.from_env({"KEEPWARM_START": "2026-10-31", "KEEPWARM_END": "2026-11-14",
                          "KEEPWARM_BUDGET_USD": str(budget), "KEEPWARM_PRICE_USD_HR": "0.0491",
                          "KEEPWARM_LEDGER": str(tmp_path / "ledger.json")})


def _run(plan, when, up=False):
    calls = []

    async def wake():
        calls.append("wake")

    async def touch():
        calls.append("touch")

    what = asyncio.run(tick(plan, datetime.fromisoformat(when).replace(tzinfo=IST), up=up, wake=wake, touch=touch))
    return what, calls


def test_it_wakes_and_counts_only_inside_the_daily_window(tmp_path):
    plan = _plan(tmp_path)
    assert _run(plan, "2026-10-31T08:59") == ("idle", [])
    assert _run(plan, "2026-10-31T09:00") == ("warm", ["wake", "touch"])
    assert _run(plan, "2026-10-31T12:00", up=True) == ("warm", ["touch"])
    assert read_minutes(plan.ledger) == 10
    # After closing, a worker still up is counted until the idle stop catches it, but never kept awake.
    assert _run(plan, "2026-10-31T21:10", up=True) == ("tail", [])
    assert _run(plan, "2026-10-31T21:10", up=False) == ("tail", [])
    assert read_minutes(plan.ledger) == 15
    assert _run(plan, "2026-10-31T22:00", up=True) == ("idle", [])


def test_nothing_happens_before_the_start_or_after_the_end(tmp_path):
    plan = _plan(tmp_path)
    assert _run(plan, "2026-10-30T12:00") == ("idle", [])
    assert _run(plan, "2026-11-13T20:55") == ("warm", ["wake", "touch"])
    assert _run(plan, "2026-11-14T12:00") == ("over", [])
    assert _run(plan, "2027-01-01T12:00", up=True) == ("over", [])


def test_the_budget_is_a_hard_stop(tmp_path):
    plan = _plan(tmp_path, budget=1.0)
    write_minutes(plan.ledger, 60 / 0.0491 - 4)  # four minutes short of a dollar: the next tick would pass it
    assert _run(plan, "2026-11-02T10:00") == ("budget spent", [])
    # An unreadable ledger counts as spent rather than as zero.
    plan.ledger.write_text("garbage")
    assert _run(_plan(tmp_path), "2026-11-02T10:00") == ("budget spent", [])


def test_two_weeks_of_daytime_fits_the_budget(tmp_path):
    plan = _plan(tmp_path)
    days, hours, tail_h = 14, 12, 0.5
    assert plan.spent_usd(days * (hours + tail_h) * 60) < plan.budget_usd
