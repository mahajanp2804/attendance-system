"""
Shared test setup.

- The face models (torch, ultralytics, facenet-pytorch) are replaced by tiny stubs,
  so the suite runs anywhere in seconds; tests swap in fake detector/embedder objects.
- API tests need a throwaway Postgres. Set TEST_DATABASE_URL, e.g.
    postgresql+asyncpg://test:test@localhost:5432/attendance_test
  Its database name must contain "test": the tests drop and recreate every table.
  Without it, API tests are skipped and everything else still runs.
"""

import asyncio
import importlib.util
import os
import secrets
import sys
import tempfile
import types

import pytest

TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL")

# ── Environment — set before any app module is imported ──────────────────────
DATA_DIR = tempfile.mkdtemp(prefix="attendance-test-")
os.environ.update({
    "DATABASE_URL": TEST_DATABASE_URL or "postgresql+asyncpg://unused@localhost/unused_test",
    "SECRET_KEY": secrets.token_hex(32),
    "DEBUG": "false",
    "RECOGNITION_THRESHOLD": "0.75",
    "EMBEDDINGS_DIR": os.path.join(DATA_DIR, "embeddings"),
    "FACE_PHOTOS_DIR": os.path.join(DATA_DIR, "face_photos"),
    "SNAPSHOTS_DIR": os.path.join(DATA_DIR, "snapshots"),
    "YOLO_MODEL_PATH": os.path.join(DATA_DIR, "models", "yolov8n-face.pt"),
})


def pytest_sessionstart(session):
    # Run from the temp dir so a developer's backend/.env is never picked up
    # (app config reads .env from the working directory when first imported)
    os.chdir(DATA_DIR)


# ── Stub the heavy ML libraries when they aren't installed ───────────────────
def _stub(name: str, **attrs) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__dict__.update(attrs)
    sys.modules[name] = module
    return module

if importlib.util.find_spec("torch") is None:
    _stub("torch", device=lambda *a, **k: "cpu",
          cuda=types.SimpleNamespace(is_available=lambda: False))
if importlib.util.find_spec("facenet_pytorch") is None:
    _stub("facenet_pytorch", InceptionResnetV1=object, MTCNN=object)
if importlib.util.find_spec("ultralytics") is None:
    _stub("ultralytics", YOLO=object)
if importlib.util.find_spec("PIL") is None:
    _stub("PIL").Image = _stub("PIL.Image")


# ── Helpers ───────────────────────────────────────────────────────────────────
def run_sql(sql: str, **params):
    """Run one SQL statement on the test DB with its own short-lived connection."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    async def go():
        engine = create_async_engine(TEST_DATABASE_URL, poolclass=NullPool)
        async with engine.begin() as conn:
            await conn.execute(text(sql), params)
        await engine.dispose()
    asyncio.run(go())


USERS = {
    "admin":  ("admin@college.edu", "admin123"),
    "priya":  ("priya.sharma@college.edu", "prof123"),    # teaches CS301, CS302
    "rajesh": ("rajesh.kumar@college.edu", "prof123"),    # teaches EC301
    "s01":    ("student01@college.edu", "student123"),    # enrolled in CS301, CS302
}


class Api:
    """Test client plus seeded IDs and cached login tokens."""

    def __init__(self, client, slots, subjects, student_ids):
        self.client = client
        self.slots = slots              # subject code → a timetable slot id
        self.subjects = subjects        # subject code → subject id
        self.student_ids = student_ids  # email → user id
        self.tokens = {}

    def login(self, who: str) -> str:
        email, password = USERS[who]
        r = self.client.post("/api/auth/login", data={"username": email, "password": password})
        assert r.status_code == 200, r.text
        self.tokens[who] = r.json()["access_token"]
        return self.tokens[who]

    def h(self, who: str) -> dict:
        """Auth header for a demo user, logging in on first use."""
        if who not in self.tokens:
            self.login(who)
        return {"Authorization": f"Bearer {self.tokens[who]}"}


@pytest.fixture(scope="session")
def api():
    """Fresh seeded database and the running app."""
    if not TEST_DATABASE_URL:
        pytest.skip("set TEST_DATABASE_URL to run the API tests")
    from sqlalchemy.engine import make_url
    db_name = make_url(TEST_DATABASE_URL).database or ""
    if "test" not in db_name:
        pytest.exit(f"Refusing to wipe database '{db_name}': its name must contain 'test'")

    from sqlalchemy import select
    from db.session import engine, AsyncSessionLocal, drop_db
    from db.seed import seed
    from db.models import Subject, TimetableSlot, User

    async def setup():
        await drop_db()
        await seed()
        async with AsyncSessionLocal() as db:
            slots = (await db.execute(select(TimetableSlot.id, Subject.code).join(Subject))).all()
            subjects = (await db.execute(select(Subject.id, Subject.code))).all()
            users = (await db.execute(select(User.id, User.email))).all()
        await engine.dispose()   # the app's TestClient runs its own event loop
        return (
            {code: str(i) for i, code in slots},
            {code: str(i) for i, code in subjects},
            {email: str(i) for i, email in users},
        )

    slots, subjects, student_ids = asyncio.run(setup())

    from fastapi.testclient import TestClient
    from main import app
    with TestClient(app) as client:
        yield Api(client, slots, subjects, student_ids)
