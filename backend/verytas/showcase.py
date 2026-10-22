"""A demo workspace that looks like a real brand team at work.

    python -m verytas.cli seed-showcase --db showcase.db --write-env ../web/.env.local

One brand team (head of brand, social media manager, reviewer, auditor) and
seven creators, one of them an agency, with three weeks of history: pieces at
every stage, sent back and fixed, approved and published, escalations waiting,
brand events running and scheduled. Everything goes through the real API
(offline models), on a simulated clock, so every review, decision and timeline
entry is genuine and has a believable age. Tokens are written to the env file,
never printed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fastapi.testclient import TestClient

BRAND = "Kitepath"
NOW = datetime.now(UTC).replace(microsecond=0)
TODAY = date.today()


class _Clock(datetime):
    """Stands in for datetime inside verytas.models, so `utcnow()` reads the simulated time."""

    at: datetime = NOW

    @classmethod
    def now(cls, tz=None):  # noqa: D102
        return cls.at if tz is not None else cls.at.replace(tzinfo=None)


TEAM = [
    ("meera@kitepath.example", "Meera Rao", "brand_admin"),
    ("arjun@kitepath.example", "Arjun Mehta", "approver"),
    ("sana@kitepath.example", "Sana Iyer", "reviewer"),
    ("tara@kitepath.example", "Tara Bose", "auditor"),
]
CREATORS = [
    ("rohan@kitepath.example", "Rohan Kulkarni"),
    ("priya@kitepath.example", "Priya Nair"),
    ("dev@kitepath.example", "Dev Sharma"),
    ("aisha@kitepath.example", "Aisha Khan"),
    ("kabir@kitepath.example", "Kabir Singh"),
    ("neha@kitepath.example", "Neha Joshi"),
    ("studio9@agency.example", "Studio Nine (agency)"),
]

RULES = [
    {"code": "TONE-PLAIN", "category": "tone", "kind": "semantic", "severity": "should", "title": "Plain, warm words",
     "text": "Write like a good teacher: plain, warm and specific. No corporate jargon or hype.",
     "bad_examples": ["Leverage synergies to unlock learning paradigms"],
     "good_examples": ["Learn Python in six weeks, one evening at a time"], "source_ref": "Brand book 2026, p.6"},
    {"code": "TERM-HOUSE", "category": "terminology", "kind": "deterministic", "severity": "should",
     "title": "House spellings", "text": "Use our house spellings.",
     "pattern": {"type": "preferred_terms", "map": {"login": "sign in", "e-mail": "email", "webinar": "live class"}},
     "source_ref": "Brand book 2026, p.9"},
    {"code": "TERM-NAME", "category": "terminology", "kind": "deterministic", "severity": "must",
     "title": "Our names, spelled our way", "text": "Write Kitepath and KiteLearn exactly like this.",
     "pattern": {"type": "casing", "terms": ["Kitepath", "KiteLearn"]}, "source_ref": "Brand book 2026, p.3"},
    {"code": "CLAIM-PROMISE", "category": "claims", "kind": "deterministic", "severity": "must",
     "title": "No guaranteed outcomes", "text": "We never promise jobs, marks or results. Say what the course teaches.",
     "pattern": {"type": "banned_terms", "terms": ["guaranteed job", "100% placement", "guaranteed results",
                                                     "guaranteed marks"]}, "source_ref": "Legal note L-14"},
    {"code": "MSG-RIVALS", "category": "messaging", "kind": "semantic", "severity": "must",
     "title": "No digs at other platforms", "text": "Talk about what we do. Never mock or compare against other "
     "learning platforms, by name or by hint.", "bad_examples": ["Unlike some other apps, we actually teach"],
     "source_ref": "Brand book 2026, p.11"},
]
FACTS = [
    {"statement": "Kitepath has 1.2 million learners", "value": 1.2, "unit": "million", "subject": "learners",
     "source_ref": "Annual report 2026, p.4", "valid_from": "2026-04-01"},
    {"statement": "Kitepath offers 340 courses", "value": 340, "unit": "courses", "subject": "courses",
     "source_ref": "Catalogue, October 2026", "valid_from": "2026-10-01"},
    {"statement": "Learners rate Kitepath 4.7 out of 5", "value": 4.7, "unit": "out of 5", "subject": "rating",
     "source_ref": "App store listing, Sept 2026", "valid_from": "2026-09-01"},
]
CONTACTS = [
    {"kind": "phone", "value": "+91 80 4567 8900", "label": "Learner support",
     "source_ref": "kitepath.example/contact"},
    {"kind": "email", "value": "*@kitepath.example", "label": "Company domain", "source_ref": "IT policy"},
    {"kind": "url", "value": "kitepath.example", "label": "Website", "source_ref": "Brand book 2026, p.2"},
    {"kind": "handle", "value": "@kitepath", "label": "Social handle", "source_ref": "Brand book 2026, p.2"},
]


# Reviewers' calls on first-round findings, so guideline health has a record to read: the claims rule is
# overridden again and again (twice as "unclear"), tone and topic calls are upheld, and the rivals rule
# splits the team. (piece, hours after it was written, rule, who, action, reason, note)
DECISIONS = [
    ("r-tip", 3, "CLAIM-UNSUPPORTED", "reviewer", "rejected", "false_positive", "A study tip, not a claim about us."),
    ("p-sale", 5, "CLAIM-UNSUPPORTED", "approver", "rejected", "guideline_unclear",
     "\"Best yet\" is chatty, not a comparison. Does the rule mean this?"),
    ("p-sale", 5, "TONE-SHIFT", "approver", "accepted", None, None),
    ("p-exam", 5, "TONE-SHIFT", "approver", "accepted", None, None),
    ("n-swipe", 5, "TONE-SHIFT", "reviewer", "accepted", None, None),
    ("n-swipe", 5, "MSG-RIVALS", "approver", "accepted", None, None),
    ("s-brochure", 5, "TONE-SHIFT", "reviewer", "accepted", None, None),
    ("d-budget", 5, "MSG-OFF-TOPIC", "approver", "accepted", None, None),
    ("s-gossip", 5, "MSG-OFF-TOPIC", "reviewer", "accepted", None, None),
    ("s-gossip", 5, "CLAIM-UNSUPPORTED", "reviewer", "rejected", "guideline_unclear",
     "Celebrity gossip is off topic, but it isn't a claim about Kitepath."),
    ("d-money", 2, "MSG-OFF-TOPIC", "approver", "accepted", None, None),
    ("mentor", 2, "CLAIM-UNSUPPORTED", "approver", "rejected", "false_positive",
     "Ananya's group size is on her profile."),
    ("support", 2, "CLAIM-UNSUPPORTED", "reviewer", "rejected", "not_applicable",
     "Support hours are a listed public contact, not a promotion."),
    ("rivals", 2, "MSG-RIVALS", "approver", "rejected", "guideline_unclear",
     "\"Some other apps\" names nobody. Is a hint a dig?"),
]


@dataclass
class Piece:
    key: str
    creator: int  # index into CREATORS
    title: str
    channel: str
    body: str
    days_ago: float
    flow: list[tuple[float, str, dict]]  # (hours after creation, action, args)
    event: str | None = None


def _pieces() -> list[Piece]:
    send = ("send", {})
    return [
        Piece("diwali", 0, "Festive fest: learn something new", "instagram",
              "This festive season, learn something you'll keep. Pick any of 340 courses and start tonight. "
              "#LearnThisFestive", 2.2, [(1, *send)], event="fest"),
        Piece("cheap", 1, "Festive offer reel caption", "instagram",
              "The cheapest courses in India, this week only! Kitepath has 2 million learners. Hurry, offer ends "
              "soon!!! #LearnThisFestive", 1.6, [(2, *send)], event="fest"),
        Piece("falcon", 2, "Sneak peek: what's coming", "x",
              "Something big is coming: Project Falcon lands next month and changes how you revise.", 1.2,
              [(1, "escalate", {"message": "Falcon was named in the CEO's public interview on Monday, so it is "
                                           "not a secret any more. Please check with the brand team."})]),
        Piece("placement", 3, "Data science bootcamp launch", "linkedin",
              "Join our data science bootcamp with 100% placement and a guaranteed job at the end. Login to "
              "enrol today.", 3.5, [(3, *send), (20, "back", {"note": "We never promise jobs. Say what the "
                                                                   "bootcamp teaches and who it suits."}),
                                    (30, "fix", {"body": "Join our data science bootcamp: twelve weeks of "
                                                 "real projects, mentor reviews and a portfolio you can show. Sign "
                                                 "in to enrol today."}),
                                    (31, *send)]),
        Piece("call", 4, "Weekend doubt-clearing session", "facebook",
              "Stuck on calculus? Call me on 98200 12345 and I'll sort your doubts this weekend.", 0.8,
              [(1, "escalate", {"message": "This is my official teaching line for the weekend session, students "
                                           "already use it. Please allow it for this post."})]),
        Piece("rivals", 5, "Why learners switch to us", "linkedin",
              "Unlike some other apps that just show videos, we actually teach. Kitepath has 1.2 million learners "
              "who learn by doing.", 4.2, [(2, *send)]),
        Piece("rating", 0, "Thank you, learners", "instagram",
              "Thank you for rating Kitepath 4.7 out of 5. Every review helps us teach better.", 9,
              [(1, *send), (6, "approve", {}), (30, "publish", {})]),
        Piece("python", 1, "Python in six weeks", "linkedin",
              "Learn Python in six weeks, one evening at a time. Real exercises, friendly mentors, and a project "
              "you can show.", 7, [(1, *send), (5, "approve", {})]),
        Piece("webinar", 2, "Live webinar: exam strategy", "email",
              "Join our free webinar on exam strategy this Sunday. Register via the e-mail link.", 5,
              [(1, *send), (8, "back", {"note": "Use our house words (live class, email) and add a time."})]),
        Piece("kitelearn", 3, "KiteLearn 2.0 teaser", "instagram",
              "Kitelearn 2.0 is almost here. Same friendly tutor, now with voice. #KiteLearn2", 2.8,
              [(2, *send)], event="launch"),
        Piece("support", 4, "Need help? We're here", "x",
              "Need help with your course? Our support team is on +91 80 4567 8900, every day 9 to 9.", 6,
              [(1, *send), (4, "approve", {}), (20, "publish", {})]),
        Piece("synergy", 6, "Agency draft: brand film caption", "youtube",
              "We leverage synergies to unlock next-gen learning paradigms for the learners of tomorrow.", 1.0,
              [(1, *send)]),
        Piece("results", 6, "Agency draft: board exam campaign", "instagram",
              "Guaranteed results in your board exams with Kitepath. Login now, limited seats!", 0.5,
              [(0.2, "escalate", {"message": "The client asked for this exact line in their brief. Can the brand "
                                             "team confirm whether it is allowed?"}),
               (5, "resolve", {"outcome": "upheld", "note": "Not allowed: we never promise results. Try 'Prepare "
                                                             "for your board exams with mock tests and mentors'."})]),
        Piece("mentor", 5, "Meet our mentors", "linkedin",
              "Meet Ananya, who mentors 40 learners a week in our design track. Her tip: finish one small thing a "
              "day.", 11, [(1, *send), (10, "approve", {}), (40, "publish", {})]),
        Piece("courses", 2, "New this month: 20 courses", "instagram",
              "Twenty new courses landed this month, from Excel to Kannada for beginners. Which one are you "
              "starting?", 12, [(1, *send), (3, "approve", {}), (26, "publish", {})]),
        Piece("streak", 1, "Learning streak challenge", "x",
              "Can you learn for 7 days straight? Join the streak challenge and share your progress with "
              "#KiteStreak.", 0.3, [(0.2, *send)]),
        Piece("parents", 4, "A note for parents", "email",
              "Dear parents, here is how Kitepath keeps learning safe: verified mentors, no ads, and progress "
              "reports every Sunday.", 2.0, [(1, *send), (6, "comment", {"body": "Lovely. Can we add one line on "
                                                                        "how parents see the reports?"})]),
        Piece("hindi", 0, "Hinglish reel: padhai ka festival", "instagram",
              "Is festive season, padhai bhi celebrate karo! Naya course shuru karo aaj raat. #LearnThisFestive",
              0.9, [], event="fest"),
        *_history(),
    ]


def _clean() -> list[tuple[float, str, dict]]:
    return [(1, "send", {}), (4, "approve", {}), (20, "publish", {})]


def _fixed(note: str, body: str) -> list[tuple[float, str, dict]]:
    return [(1, "send", {}), (6, "back", {"note": note}), (20, "fix", {"body": body}), (21, "send", {}),
            (26, "approve", {}), (40, "publish", {})]


def _history() -> list[Piece]:
    """Three weeks of earlier work, so each creator's line on their profile has a shape: Rohan stays on brand,
    Priya's tone slides, Dev wanders off topic, Neha takes a sarcastic swipe, Kabir has one slip, and the
    agency writes like a contract. Every slip is the kind the brief names: tone, messaging, claims."""
    voice = "Keep our plain, warm voice: no slang, no digs, no hype."
    topic = "Stay on the course. Politics and money tips aren't ours to post."
    return [
        Piece("r-tip", 0, "Monday study tip", "x",
              "Study for 25 minutes, then take five. Small sessions add up over a week.", 19, _clean()),
        Piece("r-excel", 0, "Excel basics starts Saturday", "linkedin",
              "Our Excel basics course starts Saturday: formulas, charts and one real budget sheet.", 16, _clean()),
        Piece("r-story", 0, "Learner story: Farah", "instagram",
              "Farah finished our SQL track in eight weeks and now runs the weekly reports for her team.", 13,
              _clean()),
        Piece("r-set", 0, "Weekend practice set", "x",
              "This weekend's practice set has ten SQL questions, from easy to tricky. Try it and compare answers.",
              10, _clean()),
        Piece("p-stats", 1, "Course of the week: statistics", "linkedin",
              "Our statistics course explains averages and spread with cricket scores. Six short lessons.", 18,
              _clean()),
        Piece("p-sale", 1, "Weekend sale reminder", "instagram",
              "Our weekend sale is on.\n\nngl this one is kinda the best yet, gonna be fun lol", 14,
              _fixed(voice, "Our weekend sale is on: pick a course you'll actually finish. Ends Sunday.")),
        Piece("p-exam", 1, "Exam season pep talk", "instagram",
              "Exam season is here. Revise a little every day and sleep well.\n\nAnd honestly, anyone still "
              "cramming the night before is an idiot.", 11,
              _fixed(voice, "Exam season is here. Revise a little every day, sleep well, and ask a mentor when "
                            "you're stuck.")),
        Piece("d-excel", 2, "Learn Excel in a weekend", "linkedin",
              "Learn Excel in a weekend: two mornings, ten exercises and a sheet you'll use every month.", 17,
              _clean()),
        Piece("d-budget", 2, "Why we teach budgeting", "linkedin",
              "Our budgeting course shows you how to track spending in one sheet.\n\nAlso, the new budget is a "
              "disaster and the finance minister should resign before the election.", 9,
              _fixed(topic, "Our budgeting course shows you how to track spending in one sheet, and how to plan "
                            "a month ahead.")),
        Piece("d-money", 2, "Money skills for students", "instagram",
              "Our money skills course covers saving, spending and simple interest.\n\nSide tip: put your "
              "pocket money into crypto now, bitcoin is going to the moon.", 2.6, [(1, "send", {})]),
        Piece("n-swipe", 5, "We just teach", "linkedin",
              "Oh great, another app promising miracles. Yeah right. We just teach, one lesson at a time.", 16,
              _fixed(voice, "We just teach, one lesson at a time, with mentors who answer within a day.")),
        Piece("n-design", 5, "Design track: week one", "instagram",
              "Week one of the design track: sketch three logos, pick one, and share it for feedback.", 7, _clean()),
        Piece("k-maths", 4, "Maths in ten minutes", "x",
              "Ten minutes of maths a day beats two hours on Sunday. Today's set is on fractions.", 19, _clean()),
        Piece("k-board", 4, "Board exam timetable", "facebook",
              "Our free board exam timetable plans revision week by week. Download it from the course page.", 12,
              _clean()),
        Piece("s-brochure", 6, "Agency draft: parents' brochure", "email",
              "Please be advised that, pursuant to the aforementioned curriculum, stakeholders shall receive "
              "deliverables quarterly.", 14,
              _fixed("Write to parents like a teacher would.", "Every term, parents get a short report on what "
                                                                "their child learned and what comes next.")),
        Piece("s-gossip", 6, "Agency draft: festive teaser", "instagram",
              "Our festive courses open Friday.\n\nMeanwhile, Bollywood's biggest breakup rumour is all anyone "
              "talks about.", 9,
              _fixed(topic, "Our festive courses open Friday. Pick one skill to finish before the new year.")),
    ]


def _token_env(path: Path, values: dict[str, str]) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    seen = set()
    out = []
    for line in lines:
        key = line.split("=", 1)[0].strip()
        if key in values:
            out.append(f"{key}={values[key]}")
            seen.add(key)
        else:
            out.append(line)
    out += [f"{k}={v}" for k, v in values.items() if k not in seen]
    path.write_text("\n".join(out) + "\n")


def seed(db_path: Path, keys_dir: Path, env_out: Path | None) -> dict[str, int]:
    from verytas import models
    from verytas.config import Settings
    from verytas.main import create_app

    if db_path.exists():
        raise SystemExit(f"{db_path} exists; pick a new path so nothing is overwritten")
    settings = Settings(database_url=f"sqlite+aiosqlite:///{db_path}", llm_mode="offline", keys_dir=keys_dir)
    models.datetime = _Clock  # utcnow() now reads the simulated clock
    start = NOW - timedelta(days=21)
    _Clock.at = start
    counts = {"pieces": 0, "escalations": 0}
    try:
        with TestClient(create_app(settings)) as c:
            boot = c.post("/bootstrap", json={"workspace_name": BRAND, "admin_email": TEAM[0][0],
                                               "admin_name": TEAM[0][1]})
            boot.raise_for_status()
            tok = {"admin": boot.json()["token"]}
            h = lambda who: {"Authorization": f"Bearer {tok[who]}"}  # noqa: E731
            for email, name, role in TEAM[1:]:
                r = c.post("/users", headers=h("admin"), json={"email": email, "name": name, "role": role,
                                                              "clearance": "internal"})
                r.raise_for_status()
                tok[role] = r.json()["token"]
            for i, (email, name) in enumerate(CREATORS):
                r = c.post("/users", headers=h("admin"), json={"email": email, "name": name, "role": "creator",
                                                              "clearance": "internal"})
                r.raise_for_status()
                tok[f"c{i}"] = r.json()["token"]

            for spec in RULES:
                r = c.post("/rules", headers=h("admin"), json={**spec, "tier": "public"})
                r.raise_for_status()
                c.patch(f"/rules/{r.json()['id']}", headers=h("admin"), json={"status": "active"}).raise_for_status()
            for f in FACTS:
                c.post("/facts", headers=h("admin"), json={**f, "tier": "public"}).raise_for_status()
            c.post("/confidential-terms", headers=h("admin"),
                   json={"term": "Project Falcon", "note": "Revision mode, launches January",
                         "embargo_until": "2027-01-15"}).raise_for_status()
            for ct in CONTACTS:
                c.post("/public-contacts", headers=h("admin"), json=ct).raise_for_status()

            events: dict[str, int] = {}

            def make_event(key: str, body: dict) -> Callable[[], None]:
                def run() -> None:
                    r = c.post("/events", headers=h("admin"), json=body)
                    r.raise_for_status()
                    events[key] = r.json()["id"]
                return run

            actions: list[tuple[datetime, Callable[[], None]]] = [
                (NOW - timedelta(days=16), make_event("outage", {
                    "name": "App outage, early October", "kind": "crisis", "starts_on": str(TODAY - timedelta(days=16)),
                    "ends_on": str(TODAY - timedelta(days=13)), "blackout": True,
                    "guidance": "Acknowledge the outage plainly; no jokes about downtime.",
                    "summary": "Sign-in failures for six hours on two days."})),
                (NOW - timedelta(days=4), make_event("fest", {
                    "name": "Festive Learning Fest", "kind": "sale", "starts_on": str(TODAY - timedelta(days=3)),
                    "ends_on": str(TODAY + timedelta(days=7)), "hashtags": ["#LearnThisFestive"],
                    "avoid_terms": ["cheapest", "lowest price ever"],
                    "guidance": "Lead with what learners gain; the discount comes second. No countdown pressure.",
                    "summary": "30% off annual plans across the festive week."})),
                (NOW - timedelta(days=3.5), make_event("launch", {
                    "name": "KiteLearn 2.0 launch", "kind": "launch", "starts_on": str(TODAY + timedelta(days=20)),
                    "hashtags": ["#KiteLearn2"],
                    "guidance": "Until launch day, tease the feeling, not the features: no screenshots, no dates.",
                    "summary": "Voice tutoring in the KiteLearn app."})),
            ]
            state: dict[str, dict] = {}
            for p in _pieces():
                born = NOW - timedelta(days=p.days_ago)
                who = f"c{p.creator}"

                def create(p=p, who=who) -> None:
                    payload = {"title": p.title, "channel": p.channel, "body": p.body, "tier": "public"}
                    if p.event:
                        payload["event_id"] = events[p.event]
                    r = c.post("/contents?wait=true", headers=h(who), json=payload)
                    r.raise_for_status()
                    state[p.key] = {"id": r.json()["content"]["id"], "review": r.json()["review_id"], "who": who}
                    counts["pieces"] += 1
                actions.append((born, create))
                for hours, act, args in p.flow:
                    actions.append((born + timedelta(hours=hours), _step(c, h, state, p.key, act, args, counts)))
                for key, hours, code, by, act, reason, note in DECISIONS:
                    if key == p.key:
                        args = {"rule": code, "by": by, "action": act, "reason_code": reason, "reason_text": note}
                        actions.append((born + timedelta(hours=hours), _step(c, h, state, key, "decide", args, counts)))
            for at, run in sorted(actions, key=lambda a: a[0]):
                _Clock.at = min(at, NOW)
                run()
            _Clock.at = NOW
            if env_out is not None:
                # Dev has the richest history for a creator: a piece sent back, an open escalation, one published.
                _token_env(env_out, {"VERYTAS_API_TOKEN": tok["admin"], "VERYTAS_CREATOR_TOKEN": tok["c2"]})
    finally:
        models.datetime = datetime
    return counts


def _step(c, h, state, key: str, act: str, args: dict, counts: dict) -> Callable[[], None]:
    def run() -> None:
        s = state[key]
        cid, who = s["id"], s["who"]
        if act == "send":
            c.post(f"/contents/{cid}/transition", headers=h(who), json={"to": "in_review"}).raise_for_status()
        elif act == "back":
            c.post(f"/contents/{cid}/transition", headers=h("approver"),
                   json={"to": "changes_requested", "note": args["note"]}).raise_for_status()
        elif act in ("approve", "publish"):
            to = "approved" if act == "approve" else "published"
            r = c.post(f"/contents/{cid}/transition", headers=h("approver"), json={"to": to})
            if r.status_code == 409:  # open blockers or unchecked parts: the manager goes ahead with a reason
                r = c.post(f"/contents/{cid}/transition", headers=h("approver"), json={
                    "to": to, "override_blockers": True,
                    "note": "Checked by hand: the flagged parts were reviewed and are fine to publish."})
            r.raise_for_status()
        elif act == "fix":
            r = c.post(f"/contents/{cid}/versions?wait=true", headers=h(who), json={"body": args["body"]})
            r.raise_for_status()
            s["review"] = r.json()["review_id"]
        elif act == "decide":
            # Matched through the citation, which is how a reviewer sees which rule a finding comes from.
            findings = c.get(f"/reviews/{s['review']}", headers=h(args["by"])).json()["findings"]
            target = next((f for f in findings if any(x["kind"] == "rule" and x["label"].startswith(args["rule"] + " ")
                                                      for x in f["citations"])), None)
            if target is not None:
                c.post(f"/findings/{target['id']}/decision", headers=h(args["by"]), json={
                    "action": args["action"], "reason_code": args["reason_code"],
                    "reason_text": args["reason_text"]}).raise_for_status()
                counts["decisions"] = counts.get("decisions", 0) + 1
        elif act == "comment":
            c.post(f"/contents/{cid}/comments", headers=h("reviewer"), json={"body": args["body"]}).raise_for_status()
        elif act == "resolve":
            esc = c.get("/escalations", headers=h("approver"), params={"content_id": cid}).json()[0]
            c.post(f"/escalations/{esc['id']}/resolve", headers=h("approver"), json=args).raise_for_status()
        elif act == "escalate":
            findings = c.get(f"/reviews/{s['review']}", headers=h(who)).json()["findings"]
            target = next((f for f in findings if f["level"] == "blocker"), findings[0] if findings else None)
            if target is not None:
                c.post(f"/findings/{target['id']}/escalations", headers=h(who),
                       json={"message": args["message"]}).raise_for_status()
                counts["escalations"] += 1
    return run
