"""Faces in images and video frames: who they are, and whether the brand's record lets them appear.

For each clearly visible face the agent looks for its person among:
1. the brand's approved people (Library, People), against their reference photos;
2. people the creator's brief names who aren't in the library, against a public portrait the reference
   finder fetched (Wikidata and Wikimedia Commons), when the content may leave the machine.

An identified person goes through `licence()`: the agreement's channels, campaigns and dates decide.
Someone the brief names and the face matches, but the brand has no agreement with, is the case that
gets a brand sued, so it is a blocker. A prominent face nobody can name is a warning that asks who it is.
"""

from __future__ import annotations

import asyncio
import io
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from verytas.checks.base import RawFinding
from verytas.checks.likeness import PersonView, licence
from verytas.media import faces as face_model
from verytas.prism.board import Evidence

# Above this a face is the person's; between SAME_PERSON and this it only resembles them, and the
# finding says so at warning strength rather than accuse anyone on a near-miss.
IDENTIFIED = 0.42
MAX_FACES = 6
MAX_WEB_LOOKUPS = 3
# A face this large (its shorter side against the image's) is a subject, not a passer-by.
PROMINENT = 0.12
_NAME = re.compile(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2})\b")
_NOT_NAMES = {"Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday", "January", "February",
              "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"}


@dataclass
class Known:
    label: str
    vectors: list[np.ndarray]
    person: PersonView | None = None
    source_url: str | None = None
    restricted: bool = False


@dataclass
class PeopleContext:
    """What the face check needs about the brand and this piece, loaded once per review."""

    people: list[PersonView]
    photos: dict[int, list[bytes]]
    restricted: set[int]
    channel: str
    event_id: int | None
    author_id: int | None
    on: date
    models_dir: Path
    allow_web: bool
    avoid: list[str] = field(default_factory=list)  # names never sent out (confidential terms, assets)
    _known: list[Known] | None = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def known(self, run: Any) -> list[Known]:
        """Everyone a face could be, with their face descriptions; computed on first need."""
        async with self._lock:
            if self._known is None:
                self._known = await self._load(run)
            return self._known

    async def _load(self, run: Any) -> list[Known]:
        out: list[Known] = []
        for person in self.people:
            vectors = []
            for raw in self.photos.get(person.id, []):
                try:
                    v = await run.blocking(face_model.describe, Image.open(io.BytesIO(raw)), self.models_dir)
                except Exception:  # noqa: BLE001, an unreadable photo is skipped, the others still count
                    v = None
                if v is not None:
                    vectors.append(v)
            if vectors:
                out.append(Known(person.name, vectors, person, restricted=person.id in self.restricted))
        if self.allow_web:
            out += await self._from_web(run)
        return out

    async def _from_web(self, run: Any) -> list[Known]:
        from verytas.services.references import find_portrait

        listed = {n.casefold() for p in self.people for n in (p.name, *p.aliases)}
        avoid = {a.casefold() for a in self.avoid}
        names = [n for n in dict.fromkeys(_NAME.findall(run.brief))
                 if n.casefold() not in listed and n.split()[0] not in _NOT_NAMES
                 and not any(a in n.casefold() or n.casefold() in a for a in avoid)][:MAX_WEB_LOOKUPS]
        out = []
        for name in names:
            ref = await find_portrait(name)
            if ref is None:
                continue
            v = await run.blocking(face_model.describe, Image.open(io.BytesIO(ref.image)), self.models_dir)
            if v is not None:
                out.append(Known(ref.name, [v], source_url=ref.source_url))
        if names:
            run.notes.append(f"looked up public portraits for people the brief names: {', '.join(names)}")
        return out


async def faces_agent(run: Any, node: Any, pil: Image.Image, image_id: str, locator: dict[str, Any]) -> None:
    ctx: PeopleContext | None = run.people
    if ctx is None:
        return
    try:
        found = await run.blocking(face_model.find, pil, ctx.models_dir)
    except face_model.FacesUnavailable as exc:
        run.notes.append(f"{image_id}: faces were not checked ({exc})")
        run.partial.add("legal")
        return
    node.detail = {"faces": len(found)}
    if not found:
        return
    known = await ctx.known(run)
    side = min(pil.size)
    unlicensed = run.rule_by_code.get("LIKENESS-UNLICENSED")
    unknown = run.rule_by_code.get("LIKENESS-UNKNOWN")
    out: list[RawFinding] = []
    for i, face in enumerate(found[:MAX_FACES], start=1):
        score, who = max(((face_model.similarity(face.embedding, v), k) for k in known for v in k.vectors),
                         default=(0.0, None), key=lambda t: t[0])
        where = {**locator, "image": image_id, "box": list(face.box)}
        unit = f"{image_id}:face{i}"
        if who is not None and score >= face_model.SAME_PERSON:
            sure = score >= IDENTIFIED
            seems = "" if sure else "resembles; "
            if who.person is not None:
                allowed, why = licence(who.person, channel=ctx.channel, event_id=ctx.event_id, on=ctx.on,
                                       author_id=ctx.author_id)
                if sure:
                    # What the cross-check compares with the people the caption names (prism/board.py).
                    run.board.post(Evidence("person", image_id, who.person.name,
                                            tuple(locator["time"]) if locator.get("time") else None,
                                            tuple(face.box), {"similarity": round(score, 3)}))
                if allowed:
                    run.glance.append(f"{who.label} appears ({why})")
                    continue
                if who.restricted:
                    why = "the brand's agreement doesn't cover this piece"
                title = (f"{who.label} isn't licensed for this piece" if sure
                         else f"May be {who.label}, who isn't licensed here")
                detail = f"{why[0].upper()}{why[1:]} ({seems}face matched their reference photo at {score:.2f})."
            else:
                title = (f"Looks like {who.label}, who has no agreement with the brand" if sure
                         else f"May be {who.label}, who has no agreement with the brand")
                detail = (f"The face {seems}matches the public portrait of {who.label} ({who.source_url}) at "
                          f"{score:.2f}, and the brand's records have no agreement with them.")
            if unlicensed:
                out.append(RawFinding(unit_id=unit, category=unlicensed.category, title=title,
                                      explanation=f"{detail} {unlicensed.text}", confidence=0.9 if sure else 0.6,
                                      checker="faces", rule_code=unlicensed.code, source=image_id, locator=where))
        elif unknown and face.side >= PROMINENT * side:
            out.append(RawFinding(
                unit_id=unit, category=unknown.category, title="A person appears who isn't identified",
                explanation=f"This face doesn't match anyone in the brand's records"
                            f"{' or the brief' if run.brief else ''}. {unknown.text}",
                confidence=0.7, checker="faces", rule_code=unknown.code,
                source=image_id, locator=where))
    run.add(node, "media", out)
