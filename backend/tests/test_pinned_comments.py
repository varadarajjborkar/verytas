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


def test_a_manager_draws_on_the_picture_and_the_creator_sees_it(client, world, monkeypatch):  # noqa: F811
    cid, vid = _piece(client, world, monkeypatch)
    marks = [{"type": "stroke", "width": 0.006, "points": [[0.1, 0.1], [0.2, 0.15], [0.3, 0.2]]},
             {"type": "text", "x": 0.35, "y": 0.2, "text": "Logo too close to the edge"}]
    res = client.post(f"/contents/{cid}/comments", headers=_auth(world["reviewer"]), json={
        "body": "See the marks", "version_id": vid, "media_id": "poster", "marks": marks})
    assert res.status_code == 201, res.text
    seen = client.get(f"/contents/{cid}/comments", headers=_auth(world["creator"])).json()
    assert seen[-1]["marks"][1]["text"] == "Logo too close to the edge"
    # Off the frame, unpinned, or too much drawing are refused.
    bad = [{"type": "stroke", "width": 0.006, "points": [[1.5, 0.1]]}]
    assert client.post(f"/contents/{cid}/comments", headers=_auth(world["reviewer"]), json={
        "body": "x", "version_id": vid, "media_id": "poster", "marks": bad}).status_code == 422
    assert client.post(f"/contents/{cid}/comments", headers=_auth(world["reviewer"]), json={
        "body": "x", "marks": marks}).status_code == 422
    huge = [{"type": "stroke", "width": 0.006, "points": [[0.5, 0.5]] * 1000}] * 5
    assert client.post(f"/contents/{cid}/comments", headers=_auth(world["reviewer"]), json={
        "body": "x", "version_id": vid, "media_id": "poster", "marks": huge}).status_code == 422


def test_the_review_player_streams_the_video_in_ranges(client, world, monkeypatch):  # noqa: F811
    cid, vid = _piece(client, world, monkeypatch)
    detail = client.get(f"/contents/{cid}", headers=_auth(world["creator"])).json()
    assert [v["id"] for v in detail["versions"][-1]["videos"]] == ["reel"]
    url = f"/contents/{cid}/versions/{vid}/videos/reel"
    part = client.get(url, headers=_auth(world["reviewer"]) | {"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100 and part.headers["content-disposition"] == "inline"
    image_as_video = client.get(f"/contents/{cid}/versions/{vid}/videos/poster", headers=_auth(world["reviewer"]))
    assert image_as_video.status_code == 404
