"""The /students/{id}/embed endpoint, with a fake FaceNet model and a fake DB session."""

import asyncio
import threading
import types

import cv2
import numpy as np
import pytest

import recognition.embedder as embedder_module
import routes.students as students_routes
from recognition.faiss_index import faiss_index

rng = np.random.default_rng(1)


def unit(v):
    return (v / np.linalg.norm(v)).astype("float32")


STUDENT = unit(rng.normal(size=512))


class FakeEmbedder:
    def __init__(self):
        self.threads = set()
        self.face = STUDENT   # whose face the uploaded photos show

    def embed(self, image):
        self.threads.add(threading.current_thread().name)
        return unit(self.face + rng.normal(scale=0.05, size=512))   # each photo slightly different


class FakeDB:
    def add(self, obj):
        pass

    async def get(self, model, id):
        return types.SimpleNamespace(name=f"Name of {id}", roll_number=f"R-{id}")


@pytest.fixture
def enroll(monkeypatch, tmp_path):
    photos = tmp_path / "photos"
    photos.mkdir()
    for i in range(3):
        cv2.imwrite(str(photos / f"{i}.jpg"), np.full((20, 20, 3), 128, np.uint8))
    student = types.SimpleNamespace(face_photos_dir=str(photos), embedding_path=None, embedding_ready=False)

    async def fake_get(student_id, db):
        return student
    monkeypatch.setattr(students_routes, "_get_student_or_404", fake_get)
    fake = FakeEmbedder()
    monkeypatch.setattr(embedder_module, "embedder", fake)
    (tmp_path / "empty").mkdir()
    faiss_index.load_all(str(tmp_path / "empty"))

    def run(student_id="stu-new", force=False):
        return asyncio.run(students_routes.generate_embedding(student_id, force=force, db=FakeDB(), _prof=None))
    return types.SimpleNamespace(run=run, student=student, embedder=fake)


def test_embedding_runs_on_the_worker_and_marks_student_ready(enroll):
    out = enroll.run()
    assert out["status"] == "success" and out["photos_used"] == 3
    assert enroll.student.embedding_ready is True
    assert all(t.startswith("ml-worker") for t in enroll.embedder.threads)


def test_new_student_is_recognisable_without_a_restart(enroll):
    enroll.run()
    student_id, similarity = faiss_index.search(STUDENT)[0]
    assert student_id == "stu-new" and similarity > 0.75


def test_reenrolling_does_not_duplicate_the_student(enroll):
    enroll.run()
    enroll.run()
    assert faiss_index._student_ids.count("stu-new") == 1


def test_same_face_for_a_second_student_is_refused(enroll):
    from fastapi import HTTPException
    enroll.run("stu-first")
    with pytest.raises(HTTPException) as refused:
        enroll.run("stu-second")
    assert refused.value.status_code == 409
    assert "R-stu-first" in refused.value.detail   # names who it clashes with
    assert "stu-second" not in faiss_index._student_ids
