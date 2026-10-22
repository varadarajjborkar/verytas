"""May this person's face appear in this piece? The company's record decides, not the detector.

The visual checks identify a face (against reference photos, helped by the creator's brief). Whether it
may be there is a question about agreements: a celebrity or ambassador is licensed for some channels and
campaigns between two dates, and a creator's own face belongs in their own posts. Using a recognisable
person outside that is a legal risk for the brand, so it is a blocker with the reason in plain words.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class PersonView:
    id: int
    name: str
    kind: str  # celebrity | ambassador | creator | staff | other
    valid_from: date
    valid_to: date | None = None
    channels: tuple[str, ...] = ()
    event_ids: tuple[int, ...] = ()
    user_id: int | None = None
    active: bool = True
    aliases: tuple[str, ...] = field(default=())


def licence(person: PersonView, *, channel: str, event_id: int | None, on: date,
            author_id: int | None) -> tuple[bool, str]:
    """(allowed, why). `why` names the agreement's terms either way, for the finding or the review note."""
    who = person.name
    if not person.active:
        return False, f"the brand's agreement with {who} is no longer active"
    if person.kind == "creator":
        if person.user_id is not None and person.user_id == author_id:
            return True, f"{who} appears in their own post"
        return False, f"{who} is registered as a creator for their own posts, not as someone others may feature"
    if on < person.valid_from:
        return False, f"the agreement with {who} starts on {person.valid_from.isoformat()}"
    if person.valid_to is not None and on > person.valid_to:
        return False, f"the agreement with {who} ended on {person.valid_to.isoformat()}"
    if person.channels and channel.casefold() not in {c.casefold() for c in person.channels}:
        return False, f"the agreement with {who} covers {', '.join(person.channels)}, not {channel}"
    if person.event_ids and event_id not in person.event_ids:
        return False, f"the agreement with {who} covers other campaigns, not this one"
    until = f" until {person.valid_to.isoformat()}" if person.valid_to else ""
    return True, f"{who} is a licensed {person.kind}{until}"
