"""Comments pinned to a moment of a video or an area of an image, as a manager marks what to change."""

from __future__ import annotations

from tests.media_fixtures import b64, caption_video, png, text_image
from tests.test_media import _auth, world  # noqa: F401, the fixture is used by name


def _piece(client, world, monkeypatch):  # noqa: F811
    from verytas.media import video

    monkeypatch.setattr(video, "transcribe", lambda pcm, model, vocabulary=None: ([], "en", 0.0))
    clip = client.post("/media", headers=_auth(world["creator"]),
                       files={"file": ("reel.mp4", caption_video([(0, 3, "Join the waitlist")]), "video/mp4")}).json()
    res = client.post("/contents?wait=true", headers=_auth(world["creator"]), json={
        "title": "Reel", "channel": "instagram", "tier": "public", "body": "New reel",
        "attachments": {"images": [{"id": "poster", "alt": "The launch poster",
                                    "data_base64": b64(png(text_image(["Launch day"], size=(900, 600))))}],
                        "videos": [{"id": "reel", "blob_id": clip["id"]}]},
        "creator_notes": {"brief": "Launch reel: our mascot waves, then the waitlist caption."}})
    assert res.status_code == 201, res.text
    return res.json()["content"]["id"], res.json()["version"]["id"]


def test_a_manager_pins_a_comment_to_a_moment_and_to_an_area(client, world, monkeypatch):  # noqa: F811
    cid, vid = _piece(client, world, monkeypatch)
    h = _auth(world["reviewer"])
    moment = client.post(f"/contents/{cid}/comments", headers=h, json={
        "body": "The mascot's tail turns red here", "version_id": vid, "media_id": "reel",
        "time_start": 1.5, "time_end": 2.25, "box": [0.4, 0.1, 0.7, 0.6]})
    assert moment.status_code == 201, moment.text
    area = client.post(f"/contents/{cid}/comments", headers=h, json={
        "body": "Logo too close to the edge", "version_id": vid, "media_id": "poster", "box": [0.0, 0.0, 0.2, 0.15]})
    assert area.status_code == 201, area.text
    listed = {c["body"]: c for c in client.get(f"/contents/{cid}/comments", headers=_auth(world["creator"])).json()}
    pinned = listed["The mascot's tail turns red here"]
    assert (pinned["media_id"], pinned["time_start"], pinned["time_end"]) == ("reel", 1.5, 2.25)
    assert listed["Logo too close to the edge"]["box"] == [0.0, 0.0, 0.2, 0.15]


def test_pins_must_point_at_something_real(client, world, monkeypatch):  # noqa: F811
    cid, vid = _piece(client, world, monkeypatch)
    h = _auth(world["reviewer"])

    def post(**pin):
        return client.post(f"/contents/{cid}/comments", headers=h, json={"body": "here", **pin}).status_code

    assert post(version_id=vid, media_id="poster", time_start=1.0) == 422  # an image has no moments
    assert post(version_id=vid, media_id="missing", box=[0, 0, 0.5, 0.5]) == 422
    assert post(version_id=vid, media_id="reel", box=[0.5, 0.5, 0.2, 0.9]) == 422  # x1 before x0
    assert post(media_id="reel", time_start=1.0) == 422  # no version to pin to
    assert post(media_id="reel") == 422  # errcheck 246: a media id alone names no version
    assert post(version_id=vid, media_id="reel", time_start=3.0, time_end=1.0) == 422
