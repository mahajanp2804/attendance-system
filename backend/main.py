from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config import settings
from db.session import init_db
from auth.router import router as auth_router


# ─── Lifespan (startup / shutdown) ───────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("🚀 Starting Attendance System API...")
    await init_db()
    # Load FAISS index (face recognition)
    from recognition.faiss_index import faiss_index
    faiss_index.load_all(settings.EMBEDDINGS_DIR)
    print(f"✅ FAISS index ready: {faiss_index.student_count} students")
    yield
    # Shutdown
    print("👋 Shutting down...")


# ─── App ──────────────────────────────────────────────────────────────────────

app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ─── CORS ─────────────────────────────────────────────────────────────────────

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ──────────────────────────────────────────────────────────────────
# Step 1 — Auth (done)
app.include_router(auth_router)

# Step 2 — Students & Professors
from routes.students import router as students_router
from routes.professors import router as professors_router
app.include_router(students_router)
app.include_router(professors_router)

# Step 3 — Timetable
from routes.timetable import router as timetable_router
app.include_router(timetable_router)

# Step 4 — Attendance
from routes.attendance import router as attendance_router
app.include_router(attendance_router)

# Step 5 — Face recognition WebSocket
from routes.recognition import router as recognition_router
app.include_router(recognition_router)


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/health", tags=["health"])
async def health():
    return {"status": "ok", "app": settings.APP_NAME}

# Face snapshots are biometric data, so they're not served as public static files —
# professors fetch them through GET /api/attendance/records/{id}/snapshot
