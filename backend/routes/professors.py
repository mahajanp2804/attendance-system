"""
Routes:
  GET    /api/professors/            — list professors (admin)
  POST   /api/professors/            — create professor (admin)
  GET    /api/professors/{id}        — get professor profile
  PATCH  /api/professors/{id}        — update professor (admin)
  GET    /api/professors/{id}/subjects — subjects taught
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel, EmailStr
from typing import Optional

from db.session import get_db
from db.models import User, RoleEnum, Subject
from auth.utils import get_current_user, require_professor, require_admin, hash_password

router = APIRouter(prefix="/api/professors", tags=["professors"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class ProfessorCreate(BaseModel):
    name: str
    email: EmailStr
    password: str
    department: Optional[str] = None

class ProfessorUpdate(BaseModel):
    name: Optional[str] = None
    email: Optional[EmailStr] = None
    department: Optional[str] = None
    is_active: Optional[bool] = None

class ProfessorOut(BaseModel):
    id: str
    name: str
    email: str
    department: Optional[str]
    is_active: bool
    role: str


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _prof_out(u: User) -> ProfessorOut:
    return ProfessorOut(
        id=str(u.id), name=u.name, email=u.email,
        department=u.department, is_active=u.is_active,
        role=u.role.value,
    )

async def _get_prof_or_404(prof_id: str, db: AsyncSession) -> User:
    result = await db.execute(
        select(User).where(
            User.id == prof_id,
            User.role.in_([RoleEnum.professor, RoleEnum.admin])
        )
    )
    prof = result.scalar_one_or_none()
    if not prof:
        raise HTTPException(status_code=404, detail="Professor not found")
    return prof


# ─── List professors ──────────────────────────────────────────────────────────

@router.get("/", response_model=list[ProfessorOut])
async def list_professors(
    db: AsyncSession = Depends(get_db),
    _prof: User = Depends(require_professor),
):
    result = await db.execute(
        select(User)
        .where(User.role.in_([RoleEnum.professor, RoleEnum.admin]))
        .order_by(User.name)
    )
    return [_prof_out(u) for u in result.scalars().all()]


# ─── Create professor (admin only) ───────────────────────────────────────────

@router.post("/", response_model=ProfessorOut, status_code=201)
async def create_professor(
    body: ProfessorCreate,
    db: AsyncSession = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    existing = await db.execute(select(User).where(User.email == body.email))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Email already registered")

    prof = User(
        name=body.name,
        email=body.email,
        password_hash=hash_password(body.password),
        role=RoleEnum.professor,
        department=body.department,
    )
    db.add(prof)
    await db.flush()
    return _prof_out(prof)


# ─── Get professor ────────────────────────────────────────────────────────────

@router.get("/{prof_id}", response_model=ProfessorOut)
async def get_professor(
    prof_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _prof_out(await _get_prof_or_404(prof_id, db))


# ─── Update professor ─────────────────────────────────────────────────────────

@router.patch("/{prof_id}", response_model=ProfessorOut)
async def update_professor(
    prof_id: str,
    body: ProfessorUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Professors can update their own profile; admin can update anyone
    if current_user.role != RoleEnum.admin and str(current_user.id) != prof_id:
        raise HTTPException(status_code=403, detail="Can only update your own profile")

    prof = await _get_prof_or_404(prof_id, db)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(prof, field, value)
    db.add(prof)
    return _prof_out(prof)


# ─── Professor's subjects ─────────────────────────────────────────────────────

@router.get("/{prof_id}/subjects")
async def get_professor_subjects(
    prof_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Subject)
        .where(Subject.professor_id == prof_id)
        .order_by(Subject.name)
    )
    subjects = result.scalars().all()
    return [
        {
            "id": str(s.id),
            "name": s.name,
            "code": s.code,
            "department": s.department,
            "semester_id": str(s.semester_id),
        }
        for s in subjects
    ]
