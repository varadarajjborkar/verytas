"""Approved people: who may appear in the brand's content, on what terms, and their reference photos.

The brand team records celebrities, ambassadors and staff with the channels, campaigns and dates their
agreement covers. A creator registers only themselves, so their own face in their own posts is never
mistaken for an unlicensed likeness. Reference photos are what a face in content is compared against;
each keeps where it came from (an upload, or a web address the reference finder used).
"""

from __future__ import annotations

import base64
from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from verytas.api.deps import CurrentUser, Session, can_read, require
from verytas.media.files import MAX_IMAGE_BYTES, MediaError, decode_b64, open_image, sniff
from verytas.models import Person, PersonReference, Role, Tier, User
from verytas.schemas import ApprovedPersonOut, PersonIn, PersonPatch, ReferenceApproval, ReferenceIn, ReferenceOut
from verytas.security.audit import append

router = APIRouter(tags=["people"])
Admin = Annotated[User, Depends(require(Role.brand_admin))]
Creator = Annotated[User, Depends(require(Role.creator))]
MAX_REFERENCES = 8


async def _person(session, user: User, person_id: int) -> Person:
    person = await session.scalar(select(Person).options(selectinload(Person.references))
                                  .where(Person.id == person_id))
    if person is None or person.workspace_id != user.workspace_id or not can_read(user, person.tier):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "person not found")
    return person


@router.get("/people", response_model=list[ApprovedPersonOut])
async def list_people(session: Session, user: CurrentUser) -> list[ApprovedPersonOut]:
    rows = (await session.scalars(select(Person).options(selectinload(Person.references))
                                  .where(Person.workspace_id == user.workspace_id).order_by(Person.name))).all()
    return [_shown(p, user) for p in rows if can_read(user, p.tier)]


def _shown(person: Person, user: User) -> ApprovedPersonOut:
    """Agreement notes (fees, terms) are the brand team's; everyone else sees who and when."""
    out = ApprovedPersonOut.model_validate(person)
    return out if user.role is Role.brand_admin else out.model_copy(update={"notes": None})


@router.post("/people", response_model=ApprovedPersonOut, status_code=status.HTTP_201_CREATED)
async def create_person(body: PersonIn, session: Session, admin: Admin) -> Person:
    if body.user_id is not None:
        linked = await session.get(User, body.user_id)
        if linked is None or linked.workspace_id != admin.workspace_id:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "no such user in this workspace")
    # The same agreement entered twice (a double click, a retry after a slow answer) is one person, not two.
    twin = await session.scalar(select(Person.id).where(
        Person.workspace_id == admin.workspace_id, Person.active, Person.kind == body.kind,
        func.lower(Person.name) == body.name.lower()))
    if twin is not None:
        raise HTTPException(status.HTTP_409_CONFLICT,
                            f"{body.name} is already listed; change their dates there, or add a surname or handle "
                            "if this is someone else")
    person = Person(workspace_id=admin.workspace_id, created_by=admin.id, **body.model_dump())
    session.add(person)
    await session.flush()
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="person.created",
                 object_type="person", object_id=person.id,
                 detail={"kind": body.kind, "valid_to": body.valid_to.isoformat() if body.valid_to else None})
    await session.commit()
    return await _person(session, admin, person.id)


@router.post("/people/me", response_model=ApprovedPersonOut, status_code=status.HTTP_201_CREATED)
async def register_myself(session: Session, user: Creator) -> Person:
    """A creator's own record: their face in their own posts is theirs to use. One per creator."""
    existing = await session.scalar(select(Person).where(Person.workspace_id == user.workspace_id,
                                                         Person.user_id == user.id))
    if existing is not None:
        return await _person(session, user, existing.id)
    person = Person(workspace_id=user.workspace_id, created_by=user.id, user_id=user.id, name=user.name,
                    kind="creator", valid_from=date.today(), tier=Tier.internal)
    session.add(person)
    try:
        await session.flush()
    except IntegrityError:  # two registrations at once: the other one won
        await session.rollback()
        existing = await session.scalar(select(Person).where(Person.workspace_id == user.workspace_id,
                                                             Person.user_id == user.id))
        return await _person(session, user, existing.id)
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="person.created",
                 object_type="person", object_id=person.id, detail={"kind": "creator", "self": True})
    await session.commit()
    return await _person(session, user, person.id)


@router.patch("/people/{person_id}", response_model=ApprovedPersonOut)
async def update_person(person_id: int, body: PersonPatch, session: Session, admin: Admin) -> Person:
    person = await _person(session, admin, person_id)
    changes = body.model_dump(exclude_unset=True)
    # A list or a switch can be emptied or turned off, never nulled: a null would break every read.
    nulled = sorted(k for k in ("aliases", "channels", "event_ids", "active") if k in changes and changes[k] is None)
    if nulled:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"{', '.join(nulled)} can't be null")
    for key, value in changes.items():
        setattr(person, key, value)
    if person.valid_to is not None and person.valid_to <= person.valid_from:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, "valid_to must be after valid_from")
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}", action="person.updated",
                 object_type="person", object_id=person.id, detail={"fields": sorted(changes)})
    await session.commit()
    return await _person(session, admin, person.id)


@router.post("/people/{person_id}/references", response_model=ReferenceOut, status_code=status.HTTP_201_CREATED)
async def add_reference(person_id: int, body: ReferenceIn, session: Session, user: CurrentUser) -> PersonReference:
    """A photo to compare faces against. The brand team adds them for anyone; a creator for themselves."""
    person = await _person(session, user, person_id)
    if user.role is not Role.brand_admin and person.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the brand team, or the person themselves, adds photos")
    if len(person.references) >= MAX_REFERENCES:
        raise HTTPException(status.HTTP_409_CONFLICT, f"{MAX_REFERENCES} photos is the limit; remove one first")
    try:
        raw = decode_b64(body.data_base64, MAX_IMAGE_BYTES)
        if not sniff(raw).startswith("image/"):
            raise MediaError("not an image")
        open_image(raw)
    except MediaError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_CONTENT, f"reference photo: {exc}") from None
    # A photo is only trusted to identify someone once the brand team has seen it: a creator could
    # otherwise register a celebrity's face as their own and have it cleared in their posts.
    ref = PersonReference(person_id=person.id, media_type=sniff(raw), data_base64=body.data_base64,
                          source=body.source, source_url=body.source_url, approved=user.role is Role.brand_admin)
    session.add(ref)
    await session.flush()
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}", action="person.reference_added",
                 object_type="person", object_id=person.id, detail={"source": body.source})
    await session.commit()
    return ref


@router.patch("/people/{person_id}/references/{ref_id}", response_model=ReferenceOut)
async def approve_reference(person_id: int, ref_id: int, body: ReferenceApproval, session: Session,
                            admin: Admin) -> PersonReference:
    """The brand team confirms a photo shows who the record says, so it may be used to identify them."""
    person = await _person(session, admin, person_id)
    ref = next((r for r in person.references if r.id == ref_id), None)
    if ref is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "photo not found")
    ref.approved = body.approved
    await append(session, workspace_id=admin.workspace_id, actor=f"user:{admin.id}",
                 action="person.reference_approved" if body.approved else "person.reference_unapproved",
                 object_type="person", object_id=person.id, detail={"reference": ref.id})
    await session.commit()
    return ref


@router.get("/people/{person_id}/references/{ref_id}/image")
async def reference_image(person_id: int, ref_id: int, session: Session, user: CurrentUser) -> Response:
    person = await _person(session, user, person_id)
    ref = next((r for r in person.references if r.id == ref_id), None)
    if ref is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "photo not found")
    return Response(base64.b64decode(ref.data_base64), media_type=ref.media_type,
                    headers={"Cache-Control": "private, no-cache", "X-Content-Type-Options": "nosniff"})


@router.delete("/people/{person_id}/references/{ref_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_reference(person_id: int, ref_id: int, session: Session, user: CurrentUser) -> None:
    person = await _person(session, user, person_id)
    if user.role is not Role.brand_admin and person.user_id != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "only the brand team, or the person themselves, removes photos")
    ref = next((r for r in person.references if r.id == ref_id), None)
    if ref is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "photo not found")
    await session.delete(ref)
    await append(session, workspace_id=user.workspace_id, actor=f"user:{user.id}",
                 action="person.reference_removed", object_type="person", object_id=person.id, detail={})
    await session.commit()
