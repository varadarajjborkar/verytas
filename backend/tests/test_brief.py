"""The creator's brief: what is in the images and video, typed or said in a voice note."""

from __future__ import annotations

import io
import wave
from datetime import timedelta

import numpy as np

from tests.media_fixtures import caption_video
from tests.test_media import _auth, world  # noqa: F401, the fixture is used by name
from verytas.media.files import sniff


def _voice_note(seconds: float = 1.0) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16_000)
        tone = (np.sin(np.linspace(0, 2 * np.pi * 220 * seconds, int(16_000 * seconds))) * 8000).astype(np.int16)
        w.writeframes(tone.tobytes())
    return buf.getvalue()


def _clip(client, token):
    return client.post("/media", headers=_auth(token),
                       files={"file": ("reel.mp4", caption_video([(0, 2, "Hello")]), "video/mp4")}).json()["id"]


def test_a_video_needs_a_brief(client, world):  # noqa: F811
    res = client.post("/contents", headers=_auth(world["creator"]), json={
        "title": "Reel", "channel": "instagram", "tier": "public", "body": "New reel",
        "attachments": {"videos": [{"id": "reel", "blob_id": _clip(client, world["creator"])}]},
        "creator_notes": {"brief": "too short"}})
    assert res.status_code == 422 and res.json()["detail"]["code"] == "brief_required"


def test_a_voice_note_brief_is_transcribed_and_read_with_the_notes(client, world, monkeypatch):  # noqa: F811
    from verytas.media import video
    from verytas.media.video import Cue

    def heard(pcm, model, vocabulary=None):
        # The voice note is the 1 s tone; the reel's own soundtrack is silent and longer.
        said = "Kit the mascot waves at the start, then I talk about the waitlist" if len(pcm) < 20_000 else ""
        return ([Cue(0.0, 1.0, said)] if said else []), "en", 0.9

    monkeypatch.setattr(video, "transcribe", heard)
    note = client.post("/media", headers=_auth(world["creator"]),
                       files={"file": ("brief.wav", _voice_note(), "audio/wav")})
    assert note.status_code == 201 and note.json()["media_type"] == "audio/wav"
    res = client.post("/contents?wait=true", headers=_auth(world["creator"]), json={
        "title": "Reel", "channel": "instagram", "tier": "public", "body": "New reel",
        "attachments": {"videos": [{"id": "reel", "blob_id": _clip(client, world["creator"])}]},
        "creator_notes": {"brief_audio_blob_id": note.json()["id"]}})
    assert res.status_code == 201, res.text
    review = client.get(f"/reviews/{res.json()['review_id']}", headers=_auth(world["creator"])).json()
    assert not any("voice-note brief" in n for n in review["coverage"].get("notes", []))


def test_the_sweep_keeps_a_voice_note_a_version_uses(client, world, monkeypatch):  # noqa: F811
    from sqlalchemy import update

    from verytas.media import video
    from verytas.media.storage import reclaim_orphans
    from verytas.models import MediaBlob, utcnow

    monkeypatch.setattr(video, "transcribe", lambda pcm, model, vocabulary=None: ([], "en", 0.0))
    note = client.post("/media", headers=_auth(world["creator"]),
                       files={"file": ("brief.wav", _voice_note(), "audio/wav")}).json()["id"]
    clip = _clip(client, world["creator"])
    client.post("/contents?wait=true", headers=_auth(world["creator"]), json={
        "title": "Reel", "channel": "instagram", "tier": "public", "body": "New reel",
        "attachments": {"videos": [{"id": "reel", "blob_id": clip}]}, "creator_notes": {"brief_audio_blob_id": note}})

    async def sweep():
        async with client.app.state.db.sessionmaker() as s:
            await s.execute(update(MediaBlob).values(created_at=utcnow() - timedelta(days=3)))
            await s.commit()
            return await reclaim_orphans(s, older_than=timedelta(hours=24))

    assert client.portal.call(sweep) == 0


def test_phone_audio_formats_are_recognised():
    assert sniff(_voice_note()) == "audio/wav"
    assert sniff(b"OggS" + b"\x00" * 20) == "audio/ogg"
    assert sniff(b"ID3" + b"\x00" * 20) == "audio/mpeg"


def test_utf16_text_is_not_taken_for_audio():
    # errcheck 247: FF FE (a UTF-16 byte order mark) passed the loose MPEG frame check.
    assert sniff("hello".encode("utf-16")) == "unknown"
    assert sniff(bytes([0xFF, 0xFB, 0x90, 0x64]) + b"\x00" * 20) == "audio/mpeg"


def test_a_revision_keeps_its_brief(client, world, monkeypatch):  # noqa: F811
    # errcheck 250: a revision that sent creator_notes without the brief was refused for lacking one.
    from verytas.media import video

    monkeypatch.setattr(video, "transcribe", lambda pcm, model, vocabulary=None: ([], "en", 0.0))
    h = _auth(world["creator"])
    res = client.post("/contents?wait=true", headers=h, json={
        "title": "Reel", "channel": "instagram", "tier": "public", "body": "New reel",
        "attachments": {"videos": [{"id": "reel", "blob_id": _clip(client, world["creator"])}]},
        "creator_notes": {"brief": "Kit waves, then the waitlist caption appears."}}).json()
    again = client.post(f"/contents/{res['content']['id']}/versions?wait=true", headers=h, json={
        "body": "New reel, shorter", "creator_notes": {"intent": "same reel"}})
    assert again.status_code == 201, again.text
