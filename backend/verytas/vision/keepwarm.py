"""Keep the vision worker awake in the hours judges are likely to look, inside a fixed budget, then stop.

    python -m verytas.vision.keepwarm        (verytas-keepwarm.timer runs it every five minutes)

In the window (dates and daily hours, India time) it wakes the worker if it is stopped (vision/wake.py)
and touches it, so the instance's 20-minute idle stop doesn't fire. Outside the window it does nothing,
and the idle stop puts the worker back to sleep on its own.

Money comes first. Every tick that finds the worker up in the window, or in the half hour after it while
the idle stop catches up, adds five minutes to a ledger file. Before doing anything, the tick prices
those minutes at the on-demand rate, and once that reaches the budget it never wakes the worker again.
After the end date it exits at once, so nothing needs remembering. All of it is set in the unit file
(deploy/systemd/verytas-keepwarm.service), so the dates and the cap are in the repository, not on a disk.
The account-wide budget action (stop both instances at $40) still stands behind this.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx

from verytas.config import get_settings
from verytas.vision.wake import Waker

log = logging.getLogger("verytas.keepwarm")
IST = ZoneInfo("Asia/Kolkata")
TICK = timedelta(minutes=5)
# The idle stop fires 20 minutes after the last touch; this long after the window the worker may still be up.
TAIL = timedelta(minutes=30)


@dataclass(frozen=True)
class Plan:
    start: date            # first day kept warm
    end: date              # first day no longer kept warm
    opens: time            # daily, India time
    closes: time
    budget_usd: float
    price_usd_per_hour: float
    ledger: Path

    @classmethod
    def from_env(cls, env: dict[str, str]) -> Plan:
        return cls(start=date.fromisoformat(env["KEEPWARM_START"]), end=date.fromisoformat(env["KEEPWARM_END"]),
                   opens=time.fromisoformat(env.get("KEEPWARM_OPENS", "09:00")),
                   closes=time.fromisoformat(env.get("KEEPWARM_CLOSES", "21:00")),
                   budget_usd=float(env["KEEPWARM_BUDGET_USD"]), price_usd_per_hour=float(env["KEEPWARM_PRICE_USD_HR"]),
                   ledger=Path(env.get("KEEPWARM_LEDGER", "/srv/verytas/data/keepwarm.json")))

    def spent_usd(self, minutes: float) -> float:
        return minutes / 60 * self.price_usd_per_hour

    def phase(self, now: datetime) -> str:
        """over (past the end date), warm (in a daily window), tail (just after one) or idle."""
        local = now.astimezone(IST)
        if local.date() >= self.end:
            return "over"
        if local.date() < self.start:
            return "idle"
        opens = datetime.combine(local.date(), self.opens, IST)
        closes = datetime.combine(local.date(), self.closes, IST)
        if opens <= local < closes:
            return "warm"
        return "tail" if closes <= local < closes + TAIL else "idle"


def read_minutes(path: Path) -> float:
    try:
        return float(json.loads(path.read_text())["minutes"])
    except FileNotFoundError:
        return 0.0
    except (ValueError, KeyError, TypeError):
        # An unreadable ledger is treated as a spent budget: never risk money on a guess.
        return float("inf")


def write_minutes(path: Path, minutes: float) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps({"minutes": minutes, "updated": datetime.now(IST).isoformat()}))
    os.replace(tmp, path)


async def tick(plan: Plan, now: datetime, *, up: bool, wake, touch) -> str:
    """One five-minute step. `up` says whether the worker answers now; `wake` and `touch` act on it.
    Returns what happened, for the journal."""
    phase = plan.phase(now)
    if phase in ("over", "idle"):
        return phase
    minutes = read_minutes(plan.ledger)
    if phase == "tail":
        if up:  # still billing while the idle stop catches up: counted, not extended
            write_minutes(plan.ledger, minutes + TICK.total_seconds() / 60)
        return "tail"
    if plan.spent_usd(minutes + TICK.total_seconds() / 60) > plan.budget_usd:
        return "budget spent"
    # Counted before acting: a wake that fails halfway may still have started a billed instance.
    write_minutes(plan.ledger, minutes + TICK.total_seconds() / 60)
    if not up:
        await wake()
    await touch()
    return "warm"


async def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    settings = get_settings()
    if not (settings.vision_worker_url and settings.vision_worker_instance_id):
        log.info("no vision worker configured; nothing to keep warm")
        return 0
    plan = Plan.from_env(dict(os.environ))
    base = settings.vision_worker_url.rstrip("/")
    token = settings.vision_worker_token.get_secret_value() if settings.vision_worker_token else ""
    waker = Waker(settings.vision_worker_instance_id, f"{base}/health", settings.vision_wake_timeout_s)

    async with httpx.AsyncClient(timeout=10) as client:
        try:
            up = (await client.get(f"{base}/health", timeout=3)).status_code == 200
        except httpx.HTTPError:
            up = False

        async def touch() -> None:
            res = await client.post(f"{base}/keep-warm", headers={"X-Vision-Token": token})
            res.raise_for_status()

        what = await tick(plan, datetime.now(IST), up=up, wake=waker, touch=touch)
    log.info("%s (%.2f of %.2f USD used)", what, plan.spent_usd(read_minutes(plan.ledger)), plan.budget_usd)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
