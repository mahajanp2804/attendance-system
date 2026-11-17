"""
Routes:
  GET    /api/semesters/                        — list semesters
  POST   /api/semesters/                        — create semester (professor)
  PATCH  /api/semesters/{id}/activate           — set active semester (professor)

  GET    /api/subjects/                         — list subjects (filtered by semester)
  POST   /api/subjects/                         — create subject (professor)
  PATCH  /api/subjects/{id}                     — update subject (professor)
  DELETE /api/subjects/{id}                     — delete subject (professor)

  GET    /api/timetable/                        — full weekly timetable
  GET    /api/timetable/today                   — today's slots
  POST   /api/timetable/slots                   — create slot (professor)
  PATCH  /api/timetable/slots/{id}              — update slot (professor)
  DELETE /api/timetable/slots/{id}              — delete slot (professor)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from pydantic import BaseModel
from typing import Optional
from datetime import date, time, datetime

from db.session import get_db
from db.models import (
    User, Semester, Subject, TimetableSlot, Enrollment,
    RoleEnum, DayEnum
)
from auth.utils import get_current_user, require_professor, ensure_teaches_subject

router = APIRouter(tags=["timetable"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class SemesterCreate(BaseModel):
    name: str
    start_date: date
    end_date: date

class SemesterOut(BaseModel):
    id: str
    name: str
    start_date: date
    end_date: date
    is_active: bool

class SubjectCreate(BaseModel):
    name: str
    code: str
    semester_id: str
    professor_id: Optional[str] = None
    department: Optional[str] = None

class SubjectUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    professor_id: Optional[str] = None
    department: Optional[str] = None

class SubjectOut(BaseModel):
    id: str
    name: str
    code: str
    semester_id: str
    professor_id: Optional[str]
    professor_name: Optional[str]
    department: Optional[str]

class SlotCreate(BaseModel):
    subject_id: str
    day: DayEnum
    start_time: time
    end_time: time
    room: Optional[str] = None

class SlotUpdate(BaseModel):
    day: Optional[DayEnum] = None
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    room: Optional[str] = None

class SlotOut(BaseModel):
    id: str
    subject_id: str
    subject_name: str
    subject_code: str
    professor_name: Optional[str]
    day: str
    start_time: str
    end_time: str
    room: Optional[str]


# ─── Semester endpoints ───────────────────────────────────────────────────────

@router.get("/api/semesters/", response_model=list[SemesterOut])
async def list_semesters(db: AsyncSession = Depends(get_db), _=Depends(get_current_user)):
    result = await db.execute(select(Semester).order_by(Semester.start_date.desc()))
    return [
        SemesterOut(id=str(s.id), name=s.name,
                    start_date=s.start_date, end_date=s.end_date, is_active=s.is_active)
        for s in result.scalars().all()
    ]


@router.post("/api/semesters/", response_model=SemesterOut, status_code=201)
async def create_semester(
    body: SemesterCreate,
    db: AsyncSession = Depends(get_db),
    _prof: User = Depends(require_professor),
):
    sem = Semester(name=body.name, start_date=body.start_date, end_date=body.end_date)
    db.add(sem)
    await db.flush()
    return SemesterOut(id=str(sem.id), name=sem.name,
                       start_date=sem.start_date, end_date=sem.end_date, is_active=sem.is_active)


@router.patch("/api/semesters/{semester_id}/activate", response_model=SemesterOut)
async def activate_semester(
    semester_id: str,
    db: AsyncSession = Depends(get_db),
    _prof: User = Depends(require_professor),
):
    # Deactivate all, then activate the target
    all_sems = await db.execute(select(Semester))
    for s in all_sems.scalars().all():
        s.is_active = (str(s.id) == semester_id)
        db.add(s)
    await db.flush()
    target = await db.get(Semester, semester_id)
    if not target:
        raise HTTPException(status_code=404, detail="Semester not found")
    return SemesterOut(id=str(target.id), name=target.name,
                       start_date=target.start_date, end_date=target.end_date, is_active=True)


# ─── Subject endpoints ────────────────────────────────────────────────────────

async def _enrich_subject(s: Subject, db: AsyncSession) -> SubjectOut:
    prof_name = None
    if s.professor_id:
        prof = await db.get(User, str(s.professor_id))
        prof_name = prof.name if prof else None
    return SubjectOut(
        id=str(s.id), name=s.name, code=s.code,
        semester_id=str(s.semester_id),
        professor_id=str(s.professor_id) if s.professor_id else None,
        professor_name=prof_name,
        department=s.department,
    )


@router.get("/api/subjects/", response_model=list[SubjectOut])
async def list_subjects(
    semester_id: Optional[str] = Query(None),
    department: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(Subject)
    if semester_id:
        q = q.where(Subject.semester_id == semester_id)
    if department:
        q = q.where(Subject.department == department)
    # Students see only their enrolled subjects
    if current_user.role == RoleEnum.student:
        q = q.join(Enrollment, and_(
            Enrollment.subject_id == Subject.id,
            Enrollment.student_id == current_user.id,
        ))
    # Professors see only the subjects they teach (they can't edit the others)
    elif current_user.role == RoleEnum.professor:
        q = q.where(Subject.professor_id == current_user.id)
    q = q.order_by(Subject.name)
    result = await db.execute(q)
    return [await _enrich_subject(s, db) for s in result.scalars().all()]


@router.post("/api/subjects/", response_model=SubjectOut, status_code=201)
async def create_subject(
    body: SubjectCreate,
    db: AsyncSession = Depends(get_db),
    prof: User = Depends(require_professor),
):
    # If professor_id not specified, assign to the creating professor
    professor_id = body.professor_id or str(prof.id)
    if professor_id != str(prof.id) and prof.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Only admins can assign a subject to another professor")
    subject = Subject(
        name=body.name, code=body.code,
        semester_id=body.semester_id,
        professor_id=professor_id,
        department=body.department,
    )
    db.add(subject)
    await db.flush()
    return await _enrich_subject(subject, db)


@router.patch("/api/subjects/{subject_id}", response_model=SubjectOut)
async def update_subject(
    subject_id: str,
    body: SubjectUpdate,
    db: AsyncSession = Depends(get_db),
    prof: User = Depends(require_professor),
):
    subject = await db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    await ensure_teaches_subject(prof, subject_id, db)
    changes = body.model_dump(exclude_unset=True)
    new_prof = changes.get("professor_id")
    if new_prof and new_prof != str(prof.id) and prof.role != RoleEnum.admin:
        raise HTTPException(status_code=403, detail="Only admins can assign a subject to another professor")
    for field, value in changes.items():
        setattr(subject, field, value)
    db.add(subject)
    return await _enrich_subject(subject, db)


@router.delete("/api/subjects/{subject_id}", status_code=204)
async def delete_subject(
    subject_id: str,
    db: AsyncSession = Depends(get_db),
    prof: User = Depends(require_professor),
):
    subject = await db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    await ensure_teaches_subject(prof, subject_id, db)
    await db.delete(subject)


# ─── Timetable slot endpoints ─────────────────────────────────────────────────

async def _enrich_slot(slot: TimetableSlot, db: AsyncSession) -> SlotOut:
    subject = await db.get(Subject, str(slot.subject_id))
    prof_name = None
    if subject and subject.professor_id:
        prof = await db.get(User, str(subject.professor_id))
        prof_name = prof.name if prof else None
    return SlotOut(
        id=str(slot.id),
        subject_id=str(slot.subject_id),
        subject_name=subject.name if subject else "Unknown",
        subject_code=subject.code if subject else "",
        professor_name=prof_name,
        day=slot.day.value,
        start_time=slot.start_time.strftime("%H:%M"),
        end_time=slot.end_time.strftime("%H:%M"),
        room=slot.room,
    )

DAY_ORDER = ["monday","tuesday","wednesday","thursday","friday","saturday"]


@router.get("/api/timetable/")
async def get_timetable(
    semester_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns full weekly timetable grouped by day."""
    q = select(TimetableSlot).join(Subject, Subject.id == TimetableSlot.subject_id)

    if semester_id:
        q = q.where(Subject.semester_id == semester_id)

    # Students only see slots for their enrolled subjects
    if current_user.role == RoleEnum.student:
        q = q.join(Enrollment, and_(
            Enrollment.subject_id == Subject.id,
            Enrollment.student_id == current_user.id,
        ))
    # Professor sees only their subjects
    elif current_user.role == RoleEnum.professor:
        q = q.where(Subject.professor_id == current_user.id)

    result = await db.execute(q.order_by(TimetableSlot.start_time))
    slots = result.scalars().all()
    enriched = [await _enrich_slot(s, db) for s in slots]

    # Group by day
    timetable = {day: [] for day in DAY_ORDER}
    for slot in enriched:
        if slot.day in timetable:
            timetable[slot.day].append(slot.model_dump())
    return timetable


@router.get("/api/timetable/today")
async def get_today_timetable(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Returns today's slots only."""
    today_name = datetime.now().strftime("%A").lower()  # e.g. "monday"
    q = (
        select(TimetableSlot)
        .join(Subject, Subject.id == TimetableSlot.subject_id)
        .where(TimetableSlot.day == today_name)
    )
    if current_user.role == RoleEnum.student:
        q = q.join(Enrollment, and_(
            Enrollment.subject_id == Subject.id,
            Enrollment.student_id == current_user.id,
        ))
    elif current_user.role == RoleEnum.professor:
        q = q.where(Subject.professor_id == current_user.id)

    result = await db.execute(q.order_by(TimetableSlot.start_time))
    slots = result.scalars().all()
    return [await _enrich_slot(s, db) for s in slots]


@router.post("/api/timetable/slots", response_model=SlotOut, status_code=201)
async def create_slot(
    body: SlotCreate,
    db: AsyncSession = Depends(get_db),
    _prof: User = Depends(require_professor),
):
    if body.start_time >= body.end_time:
        raise HTTPException(status_code=400, detail="start_time must be before end_time")
    slot = TimetableSlot(
        subject_id=body.subject_id, day=body.day,
        start_time=body.start_time, end_time=body.end_time, room=body.room,
    )
    db.add(slot)
    await db.flush()
    return await _enrich_slot(slot, db)


@router.patch("/api/timetable/slots/{slot_id}", response_model=SlotOut)
async def update_slot(
    slot_id: str,
    body: SlotUpdate,
    db: AsyncSession = Depends(get_db),
    _prof: User = Depends(require_professor),
):
    slot = await db.get(TimetableSlot, slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(slot, field, value)
    db.add(slot)
    return await _enrich_slot(slot, db)


@router.delete("/api/timetable/slots/{slot_id}", status_code=204)
async def delete_slot(
    slot_id: str,
    db: AsyncSession = Depends(get_db),
    _prof: User = Depends(require_professor),
):
    slot = await db.get(TimetableSlot, slot_id)
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    await db.delete(slot)
