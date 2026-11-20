# Smart Attendance System

Face-recognition based attendance system with timetable management, semester tracking, and separate student/professor portals.

## Tech Stack
- **Backend** — Python 3.11, FastAPI, SQLAlchemy (async), PostgreSQL
- **Face Recognition** — YOLOv8 (detection) + FaceNet (embeddings) + FAISS (fast matching)
- **Frontend** — React 18, Vite, Tailwind CSS (PWA — works on mobile)
- **Auth** — JWT (access + refresh tokens), bcrypt passwords

---

## Quick Start

### 1. Clone and set up environment
```bash
git clone <repo>
cd attendance-system

cp backend/.env.example backend/.env
# Edit backend/.env — set a strong SECRET_KEY (openssl rand -hex 32)
```
The API refuses to start with the placeholder key (or one shorter than 32 characters) unless `DEBUG=true`.

### 2. Start everything with Docker
```bash
docker-compose up --build
```
This starts PostgreSQL on `5432`, backend on `8000`, frontend on `5173`.

### 3. Seed demo data
```bash
docker exec attendance_backend python db/seed.py
```

Demo accounts:
| Email | Password | Role |
|---|---|---|
| admin@college.edu | admin123 | Admin |
| priya.sharma@college.edu | prof123 | Professor |
| student01@college.edu | student123 | Student |

### 4. Open the app
- Frontend: http://localhost:5173
- API docs: http://localhost:8000/docs

---

## Running Without Docker (local dev)

### Backend
```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Make sure PostgreSQL is running, then:
cp .env.example .env            # edit DATABASE_URL if needed
alembic upgrade head            # run migrations
python db/seed.py               # seed demo data
uvicorn main:app --reload       # start dev server
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

---

## Running Tests

The backend tests stub out the face models, so they don't need torch or a GPU.

```bash
cd backend
pip install -r requirements-test.txt
pytest
```

The API access-control tests also need a throwaway Postgres database. They are skipped unless you set `TEST_DATABASE_URL`, and they **drop and recreate every table**, so the database name must contain `test`:

```bash
createdb attendance_test
TEST_DATABASE_URL=postgresql+asyncpg://localhost/attendance_test pytest
```

GitHub Actions runs the full suite against Postgres 16, and checks the frontend builds, on every push to `main`.

---

## Project Structure
```
attendance-system/
├── backend/
│   ├── main.py                  # FastAPI app entry point
│   ├── config.py                # Settings from .env
│   ├── alembic.ini              # DB migration config
│   ├── auth/
│   │   ├── router.py            # /api/auth/* endpoints
│   │   └── utils.py             # JWT, password hashing, role guards
│   ├── routes/
│   │   ├── students.py          # Student management (Step 2)
│   │   ├── professors.py        # Professor management (Step 2)
│   │   ├── timetable.py         # Timetable CRUD (Step 3)
│   │   ├── attendance.py        # Attendance records (Step 4)
│   │   └── recognition.py       # WebSocket face scan (Step 5)
│   ├── recognition/
│   │   ├── detector.py          # YOLOv8 face detection
│   │   ├── embedder.py          # FaceNet 512-dim embeddings
│   │   ├── faiss_index.py       # Fast nearest-neighbour index
│   │   └── session.py           # Per-class deduplication
│   ├── db/
│   │   ├── models.py            # SQLAlchemy ORM models
│   │   ├── session.py           # Async DB connection
│   │   ├── seed.py              # Demo data
│   │   └── migrations/          # Alembic migration scripts
│   └── tests/                   # pytest suite (face models stubbed)
├── .github/workflows/           # CI: backend tests + frontend build
├── frontend/
│   └── src/
│       ├── pages/
│       │   ├── Login.jsx
│       │   ├── student/         # Student portal pages
│       │   └── professor/       # Professor portal pages
│       ├── components/          # Shared UI components
│       ├── hooks/               # API client
│       └── store/               # Auth state (Zustand)
└── docker-compose.yml
```

---

## Build Steps
| Step | What | Status |
|------|------|--------|
| 1 | Database schema, models, migrations, auth | ✅ Done |
| 2 | Student & professor management APIs | ✅ Done |
| 3 | Timetable API + semester management | ✅ Done |
| 4 | Attendance recording, override, export | ✅ Done |
| 5 | Face recognition engine + WebSocket | ✅ Done |
| 6 | React frontend — both portals | ✅ Done |
