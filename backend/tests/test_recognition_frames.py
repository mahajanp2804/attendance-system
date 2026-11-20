"""Frame processing in the face-scan endpoint, with fake YOLO/FaceNet models."""

import asyncio
import threading
import time

import numpy as np
import pytest

import routes.recognition as rr
from recognition.faiss_index import faiss_index
from recognition.session import SessionTracker

rng = np.random.default_rng(0)


def unit(v):
    return (v / np.linalg.norm(v)).astype("float32")


A, B, C = (unit(rng.normal(size=512)) for _ in range(3))
LOOKS_LIKE_B = unit(0.9 * B + 0.7 * A)   # closest to B, but also fairly close to A
FRAME = np.zeros((10, 10, 3), np.uint8)
EVERYONE = {"stu-a", "stu-b", "stu-c"}


class Box:
    def __init__(self, x1, y1, x2, y2):
        self.x1, self.y1, self.x2, self.y2 = x1, y1, x2, y2


class FakeModels:
    """Stands in for both the detector and the embedder: 'sees' the given faces."""

    def __init__(self, embeddings, delay=0.0):
        self.faces = [(Box(i * 60, 0, i * 60 + 50, 50), e) for i, e in enumerate(embeddings)]
        self.delay = delay
        self.threads = set()

    def detect(self, frame):
        self.threads.add(threading.current_thread().name)
        time.sleep(self.delay)   # a slow, blocking model call
        return [box for box, _ in self.faces]

    def crop_face(self, frame, box, padding=0.15):
        return frame

    def embed_batch(self, crops):
        return [embedding for _, embedding in self.faces]


@pytest.fixture
def marked(monkeypatch, tmp_path):
    """Index with students a/b/c, no DB or disk writes. Returns students marked present."""
    faiss_index.load_all(str(tmp_path))   # empty dir → empty index
    for student_id, vec in [("stu-a", A), ("stu-b", B), ("stu-c", C)]:
        faiss_index.add_student(student_id, vec)

    marked = []
    async def fake_mark(session_id, student_id, confidence, snapshot):
        marked.append(student_id)
    async def fake_info(student_id):
        return {"name": student_id.upper(), "roll_number": "R1"}
    monkeypatch.setattr(rr, "_mark_present_db", fake_mark)
    monkeypatch.setattr(rr, "_get_student_info", fake_info)
    monkeypatch.setattr(rr, "_save_snapshot", lambda *a: None)
    return marked


def see(monkeypatch, *embeddings, delay=0.0):
    models = FakeModels(embeddings, delay)
    monkeypatch.setattr(rr, "detector", models)
    monkeypatch.setattr(rr, "embedder", models)
    return models


def process(enrolled, tracker=None):
    async def run():
        out = await rr._process_frame(FRAME, "sess", tracker or SessionTracker("sess"), enrolled)
        await asyncio.sleep(0)   # let the fire-and-forget "mark present" task run
        return out
    return asyncio.run(run())


def test_models_run_off_the_event_loop(monkeypatch, marked):
    models = see(monkeypatch, A, delay=0.3)

    async def run():
        ticks = 0
        async def ticker():
            nonlocal ticks
            while True:
                await asyncio.sleep(0.02)
                ticks += 1
        task = asyncio.create_task(ticker())
        await rr._process_frame(FRAME, "sess", SessionTracker("sess"), EVERYONE)
        task.cancel()
        return ticks

    assert asyncio.run(run()) >= 5, "event loop was blocked while the model ran"
    assert models.threads and all(t.startswith("ml-worker") for t in models.threads)


def test_known_face_is_marked_present_once(monkeypatch, marked):
    see(monkeypatch, A)
    tracker = SessionTracker("sess")
    face = process(EVERYONE, tracker)["faces"][0]
    assert face["status"] == "recognised" and face["student_id"] == "stu-a"
    assert face["already_marked"] is False

    face = process(EVERYONE, tracker)["faces"][0]
    assert face["already_marked"] is True
    assert marked == ["stu-a"]


def test_random_face_is_low_confidence(monkeypatch, marked):
    see(monkeypatch, unit(rng.normal(size=512)))
    out = process(EVERYONE)
    assert out["faces"][0]["status"] == "low_confidence"
    assert out["unknown_count"] == 1
    assert marked == []


def test_empty_frame(monkeypatch, marked):
    see(monkeypatch)
    out = process(EVERYONE)
    assert out["faces"] == [] and out["unknown_count"] == 0


def test_lookalike_from_another_class_is_not_marked(monkeypatch, marked):
    see(monkeypatch, LOOKS_LIKE_B)
    assert process(EVERYONE)["faces"][0]["student_id"] == "stu-b"   # sanity: B is the match

    marked.clear()
    face = process({"stu-a", "stu-c"})["faces"][0]   # B isn't in this class
    assert face.get("student_id") != "stu-b"
    assert "stu-b" not in marked


def test_class_with_nobody_enrolled_matches_nobody(monkeypatch, marked):
    see(monkeypatch, A)
    out = process(set())
    assert out["faces"][0]["status"] == "unknown"
    assert out["total_enrolled"] == 0
    assert marked == []
