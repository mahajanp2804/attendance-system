"""
Routes:
  GET    /api/students/              — list all students (professor)
  POST   /api/students/              — create student (professor/admin)
  GET    /api/students/{id}          — get student profile
  PATCH  /api/students/{id}          — update student (professor/admin)
  DELETE /api/students/{id}          — deactivate student (admin)
  POST   /api/students/{id}/enroll   — enroll in subjects (professor)
  DELETE /api/students/{id}/enroll/{subject_id} — unenroll
  GET    /api/students/{id}/subjects — list enrolled subjects
  POST   /api/students/{id}/photos   — upload face photos (professor)
  POST   /api/students/{id}/embed    — trigger embedding generation (professor)
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from fastapi import status as http_status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_
from pydantic import BaseModel, EmailStr
from typing import Optional
import os, uuid

from db.session import get_db
from db.models import User, RoleEnum, Enrollment, Subject, Semester
from auth.utils import get_current_user, require_professor, hash_password, ensure_teaches_subject
from config import settings

router = APIRouter(prefix="/api/students", tags=["students"])

# Face photo upload limits
MAX_PHOTO_BYTES       = 5 * 1024 * 1024   # 5 MB per photo
MAX_PHOTOS_PER_UPLOAD = 20
IMAGE_SIGNATURES      = (b"\xff\xd8\xff", b"\x89PNG\r\n\x1a\n")   # JPEG, PNG


# ─── Schemas ──────────────────────────────────────────────────────────────────

class StudentCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    roll_number: str
    department: Optional[str] = None
    year_of_study: Optional[int] = None

class StudentUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    department: Optional[str] = None
    year_of_study: Optional[int] = None
    is_active: Optional[bool] = None

class StudentOut(BaseModel):
    id: str
    name: str
    email: str
    roll_number: Optional[str]
    department: Optional[str]
    year_of_study: Optional[int]
    is_active: bool
    embedding_ready: bool

class EnrollRequest(BaseModel):
    subject_ids: list[str]


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _student_out(u: User) -> StudentOut:
    return StudentOut(
        id=str(u.id), name=u.name, email=u.email,
        roll_number=u.roll_number, department=u.department,
        year_of_study=u.year_of_study, is_active=u.is_active,
        embedding_ready=u.embedding_ready,
    )

async def _get_student_or_404(student_id: str, db: AsyncSession) -> User:
    result = await db.execute(
        select(User).where(User.id == student_id, User.role == RoleEnum.student)
    )
    student = result.scalar_one_or_none()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    return student


# ─── List students ────────────────────────────────────────────────────────────

@router.get("/", response_model=list[StudentOut])
async def list_students(
    department: Optional[str] = Query(None),
    year: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    _prof: User = Depends(require_professor),
):
    q = select(User).where(User.role == RoleEnum.student)
    if department:
        q = q.where(User.department == department)
    if year:
        q = q.where(User.year_of_study == year)
    if search:
        q = q.where(
            User.name.ilike(f"%{search}%") | User.roll_number.ilike(f"%{search}%")
        )
    q = q.order_by(User.name)
    result = await db.execute(q)
    return [_student_out(u) for u in result.scalars().all()]


# ─── Create student ───────────────────────────────────────────────────────────

@router.post("/", response_model=StudentOut, status_code=201)
async def create_student(
    body: StudentCreate,
    db: AsyncSession = Depends(get_db),
    _prof: User = Depends(require_professor),
):
    # Check email / roll_number uniqueness
    existing = await db.execute(
        select(User).where(
            (User.email == body.email) | (User.roll_number == body.roll_number)
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email or roll number already exists")

    student = User(
        name=body.name,
        email=body.email,
        password_hash=hash_password(body.password),
        role=RoleEnum.student,
        roll_number=body.roll_number,
        department=body.department,
        year_of_study=body.year_of_study,
    )
    db.add(student)
    await db.flush()
    return _student_out(student)


# ─── Get single student ───────────────────────────────────────────────────────

@router.get("/{student_id}", response_model=StudentOut)
async def get_student(
    student_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Students can only view themselves; professors can view anyone
    if current_user.role == RoleEnum.student and str(current_user.id) != student_id:
        raise HTTPException(status_code=403, detail="Access denied")
    return _student_out(await _get_student_or_404(student_id, db))


# ─── Update student ───────────────────────────────────────────────────────────

@router.patch("/{student_id}", response_model=StudentOut)
async def update_student(
    student_id: str,
    body: StudentUpdate,
    db: AsyncSession = Depends(get_db),
    _prof: User = Depends(require_professor),
):
    student = await _get_student_or_404(student_id, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(student, field, value)
    db.add(student)
    return _student_out(student)


# ─── Deactivate student ───────────────────────────────────────────────────────

@router.delete("/{student_id}", status_code=204)
async def deactivate_student(
    student_id: str,
    db: AsyncSession = Depends(get_db),
    _prof: User = Depends(require_professor),
):
    student = await _get_student_or_404(student_id, db)
    student.is_active = False
    db.add(student)


# ─── Enroll in subjects ───────────────────────────────────────────────────────

@router.post("/{student_id}/enroll", status_code=201)
async def enroll_student(
    student_id: str,
    body: EnrollRequest,
    db: AsyncSession = Depends(get_db),
    prof: User = Depends(require_professor),
):
    student = await _get_student_or_404(student_id, db)
    enrolled, skipped = [], []

    for subject_id in body.subject_ids:
        # Check subject exists
        sub = await db.get(Subject, subject_id)
        if not sub:
            skipped.append({"subject_id": subject_id, "reason": "subject not found"})
            continue
        # Only into classes this professor teaches (a 403 rolls back the whole request)
        await ensure_teaches_subject(prof, subject_id, db)
        # Check not already enrolled
        existing = await db.execute(
            select(Enrollment).where(
                Enrollment.student_id == student.id,
                Enrollment.subject_id == subject_id,
            )
        )
        if existing.scalar_one_or_none():
            skipped.append({"subject_id": subject_id, "reason": "already enrolled"})
            continue
        db.add(Enrollment(student_id=student.id, subject_id=subject_id))
        enrolled.append(subject_id)

    return {"enrolled": enrolled, "skipped": skipped}


# ─── Unenroll from subject ────────────────────────────────────────────────────

@router.delete("/{student_id}/enroll/{subject_id}", status_code=204)
async def unenroll_student(
    student_id: str,
    subject_id: str,
    db: AsyncSession = Depends(get_db),
    prof: User = Depends(require_professor),
):
    await ensure_teaches_subject(prof, subject_id, db)
    result = await db.execute(
        select(Enrollment).where(
            Enrollment.student_id == student_id,
            Enrollment.subject_id == subject_id,
        )
    )
    enrollment = result.scalar_one_or_none()
    if not enrollment:
        raise HTTPException(status_code=404, detail="Enrollment not found")
    await db.delete(enrollment)


# ─── List enrolled subjects ───────────────────────────────────────────────────

@router.get("/{student_id}/subjects")
async def get_enrolled_subjects(
    student_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role == RoleEnum.student and str(current_user.id) != student_id:
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(Subject)
        .join(Enrollment, Enrollment.subject_id == Subject.id)
        .where(Enrollment.student_id == student_id)
        .order_by(Subject.name)
    )
    subjects = result.scalars().all()
    return [
        {"id": str(s.id), "name": s.name, "code": s.code, "department": s.department}
        for s in subjects
    ]


# ─── Upload face photos ───────────────────────────────────────────────────────

@router.post("/{student_id}/photos")
async def upload_face_photos(
    student_id: str,
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
    _prof: User = Depends(require_professor),
):
    student = await _get_student_or_404(student_id, db)
    if len(files) > MAX_PHOTOS_PER_UPLOAD:
        raise HTTPException(status_code=400, detail=f"Upload at most {MAX_PHOTOS_PER_UPLOAD} photos at a time")

    save_dir = os.path.join(settings.FACE_PHOTOS_DIR, student_id)
    os.makedirs(save_dir, exist_ok=True)

    saved, skipped = [], []
    for file in files:
        ext = os.path.splitext(file.filename)[1].lower()
        if ext not in {".jpg", ".jpeg", ".png"}:
            skipped.append({"file": file.filename, "reason": "not a .jpg or .png"})
            continue
        data = await file.read(MAX_PHOTO_BYTES + 1)
        if len(data) > MAX_PHOTO_BYTES:
            skipped.append({"file": file.filename, "reason": "larger than 5 MB"})
            continue
        # Check the file really is an image, not just named like one
        if not data.startswith(IMAGE_SIGNATURES):
            skipped.append({"file": file.filename, "reason": "not a valid JPEG or PNG image"})
            continue
        filename = f"{uuid.uuid4().hex}{ext}"
        with open(os.path.join(save_dir, filename), "wb") as f:
            f.write(data)
        saved.append(filename)

    if saved:
        student.face_photos_dir = save_dir
        db.add(student)

    return {"saved": len(saved), "files": saved, "skipped": skipped}


# ─── Trigger embedding generation ────────────────────────────────────────────

@router.post("/{student_id}/embed")
async def generate_embedding(
    student_id: str,
    force: bool = False,
    db: AsyncSession = Depends(get_db),
    _prof: User = Depends(require_professor),
):
    """
    Triggers face embedding generation for a student.
    Requires at least 3 face photos to have been uploaded first.
    Refuses (409) a face that already matches another enrolled student;
    pass ?force=true to enroll anyway (e.g. identical twins).
    """
    student = await _get_student_or_404(student_id, db)

    if not student.face_photos_dir or not os.path.exists(student.face_photos_dir):
        raise HTTPException(status_code=400, detail="No face photos uploaded yet. Upload photos first.")

    photos = [
        f for f in os.listdir(student.face_photos_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]
    if len(photos) < 3:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least 3 photos, found {len(photos)}. Upload more photos."
        )

    # Import here to avoid circular deps; recognition engine built in Step 5
    try:
        from recognition.embedder import compute_mean_embedding, save_embedding
        from recognition.faiss_index import faiss_index
        from recognition.worker import run_ml
    except ImportError:
        # Recognition engine not built yet (Step 5)
        return {"status": "pending", "message": "Recognition engine not yet available. Come back after Step 5."}

    try:
        embedding = await run_ml(compute_mean_embedding, student.face_photos_dir)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Embedding generation failed: {str(e)}")

    # The same face enrolled as two students means the scanner can only ever mark
    # whichever one is closer — so refuse unless the professor confirms
    if not force:
        clash = next((m for m in faiss_index.search(embedding, top_k=2) if m[0] != student_id), None)
        if clash and clash[1] >= settings.RECOGNITION_THRESHOLD:
            other = await db.get(User, clash[0])
            who = f"{other.name} ({other.roll_number})" if other else "another student"
            raise HTTPException(
                status_code=409,
                detail=f"This face matches {who}, who is already enrolled ({clash[1]:.0%} similar). "
                       "Check you picked the right student.",
            )

    embedding_path = save_embedding(student_id, embedding, settings.EMBEDDINGS_DIR)
    # Make the student recognisable straight away, without a server restart
    faiss_index.add_student(student_id, embedding)
    student.embedding_path = embedding_path
    student.embedding_ready = True
    db.add(student)
    return {"status": "success", "embedding_path": embedding_path, "photos_used": len(photos)}
