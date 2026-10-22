"""The vision worker's HTTP contract, with the model chain stubbed: auth, input limits, reference caching
and the box scaling the client does."""

from __future__ import annotations

import asyncio
import base64
import io
import threading

import httpx
import pytest
from fastapi.testclient import TestClient
from PIL import Image

from verytas.vision import client as vision_client
from verytas.vision import worker
from verytas.vision.chain import Character, Reference


def _b64(size=(64, 48), fmt="PNG") -> str:
    buf = io.BytesIO()
    Image.new("RGB", size, "white").save(buf, fmt)
    return base64.b64encode(buf.getvalue()).decode()


class FakeChain:
    prepared = 0

    def __init__(self, models_dir, device="cpu"):
        self.lock = threading.Lock()

    def reference(self, ref_id, artwork):
        FakeChain.prepared += 1
        return Reference(ref_id, None, None)

    def characters(self, scene, refs, prompt):
        w, h = scene.size
        return [Character([0, 0, w, h], 0.9, {r.id: 0.95 for r in refs}, {r.id: [] for r in refs})]


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setattr(worker, "Chain", FakeChain)
    FakeChain.prepared = 0
    return worker.create_app(tmp_path, token="s3cret")


def test_requests_need_the_token(app):
    with TestClient(app) as c:
        assert c.get("/health").json()["status"] == "ok"
        body = {"scenes": [_b64()]}
        assert c.post("/characters", json=body).status_code == 401
        assert c.post("/characters", json=body, headers={"X-Vision-Token": "nope"}).status_code == 401
        assert c.post("/characters", json=body, headers={"X-Vision-Token": "s3cret"}).status_code == 200


def test_bad_images_and_oversized_batches_are_refused(app):
    auth = {"X-Vision-Token": "s3cret"}
    with TestClient(app) as c:
        assert c.post("/characters", json={"scenes": ["%%%"]}, headers=auth).status_code == 422
        not_image = base64.b64encode(b"plain text").decode()
        assert c.post("/characters", json={"scenes": [not_image]}, headers=auth).status_code == 422
        too_many = {"scenes": [_b64()] * (worker.MAX_SCENES + 1)}
        assert c.post("/characters", json=too_many, headers=auth).status_code == 422


def test_artwork_is_prepared_once_across_requests(app):
    auth = {"X-Vision-Token": "s3cret"}
    body = {"scenes": [_b64()], "references": [{"id": "1", "image_base64": _b64((32, 32))}]}
    with TestClient(app) as c:
        first = c.post("/characters", json=body, headers=auth).json()
        c.post("/characters", json=body, headers=auth)
        assert first["scenes"][0][0]["likeness"] == {"1": 0.95}
        assert c.get("/health").json()["models_loaded"] and FakeChain.prepared == 1


def test_the_client_scales_boxes_back_to_the_original_image(app, monkeypatch):
    transport = httpx.ASGITransport(app=app)
    real = httpx.AsyncClient
    monkeypatch.setattr(vision_client.httpx, "AsyncClient", lambda **kw: real(transport=transport, **kw))
    big = Image.new("RGB", (2560, 1440), "white")  # shrunk to 1280 wide before sending
    vc = vision_client.VisionClient("http://127.0.0.1:8100", "s3cret", 10)
    [[ch]] = asyncio.run(vc.characters([big], [("1", Image.new("RGBA", (16, 16)))]))
    assert ch.box == [0, 0, 2560, 1440] and ch.best() == ("1", 0.95)


def test_the_client_reports_a_worker_that_is_down():
    vc = vision_client.VisionClient("http://127.0.0.1:9", None, 2)
    with pytest.raises(vision_client.VisionUnavailable):
        asyncio.run(vc.characters([Image.new("RGB", (8, 8))], []))


def test_the_worker_refuses_to_listen_publicly_without_a_token(monkeypatch):
    monkeypatch.delenv("VERYTAS_VISION_TOKEN", raising=False)
    monkeypatch.setattr("sys.argv", ["worker", "--host", "0.0.0.0"])
    with pytest.raises(SystemExit):
        worker.main()


def test_plain_http_is_only_for_this_machine_or_a_private_network():
    for ok in ("http://127.0.0.1:8100", "http://localhost:8100", "http://10.0.3.7:8100", "https://vision.example"):
        vision_client.VisionClient(ok, None, 5)
    for bad in ("http://vision.example", "http://15.252.228.168:8100", "ftp://10.0.0.1"):
        with pytest.raises(ValueError):
            vision_client.VisionClient(bad, None, 5)


def test_oversized_bodies_and_odd_tokens_are_refused_before_parsing(app):
    with TestClient(app) as c:
        # A non-ASCII token is a mismatch, not a crash.
        assert c.post("/characters", content=b"{}", headers={"X-Vision-Token": "s3crét".encode(),
                                                             "content-type": "application/json"}).status_code == 401
        assert c.post("/characters", content=b"junk", headers={"content-type": "application/json"}).status_code == 401
        big = {"X-Vision-Token": "s3cret", "content-length": str(worker.MAX_BODY_BYTES + 1)}
        assert c.post("/characters", content=b"{}", headers=big).status_code == 413


def test_images_outside_the_accepted_formats_or_sizes_are_refused(app):
    auth = {"X-Vision-Token": "s3cret"}
    with TestClient(app) as c:
        tiff = io.BytesIO()
        Image.new("RGB", (8, 8)).save(tiff, "TIFF")
        body = {"scenes": [base64.b64encode(tiff.getvalue()).decode()]}
        assert c.post("/characters", json=body, headers=auth).status_code == 422
        assert c.post("/characters", json={"scenes": [_b64((worker.MAX_SIDE + 1, 8))]}, headers=auth).status_code == 413


def test_a_malformed_reply_is_unavailable_not_a_crash(monkeypatch):
    async def reply(self, body):
        return {"scenes": []}  # one scene sent, none answered

    monkeypatch.setattr(vision_client.VisionClient, "_post", reply)
    vc = vision_client.VisionClient("http://127.0.0.1:8100", None, 5)
    with pytest.raises(vision_client.VisionUnavailable):
        asyncio.run(vc.characters([Image.new("RGB", (8, 8))], []))


def test_a_long_video_goes_in_batches_in_order(monkeypatch):
    sent = []

    async def reply(self, body):
        sent.append(len(body["scenes"]))
        return {"scenes": [[{"box": [0, 0, 1, 1], "score": 0.5, "likeness": {}, "differences": {}}]
                           for _ in body["scenes"]]}

    monkeypatch.setattr(vision_client.VisionClient, "_post", reply)
    vc = vision_client.VisionClient("http://127.0.0.1:8100", None, 5)
    out = asyncio.run(vc.characters([Image.new("RGB", (8, 8))] * (vision_client.BATCH + 3), []))
    assert sent == [vision_client.BATCH, 3] and len(out) == vision_client.BATCH + 3
