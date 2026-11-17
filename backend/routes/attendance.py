"""
Routes:
  GET    /api/attendance/sessions                      — list class sessions
  POST   /api/attendance/sessions                      — create/open a session (professor)
  PATCH  /api/attendance/sessions/{id}/close           — close session, auto-mark absentees
  GET    /api/attendance/sessions/{id}/records         — all records for a session
  PATCH  /api/attendance/records/{id}                  — override a single record (professor)
  GET    /api/attendance/records/{id}/snapshot         — face snapshot for a record (professor)
  GET    /api/attendance/summary                       — per-subject % for a student
  GET    /api/attendance/report                        — full report (professor, exportable)
  GET    /api/attendance/export                        — download CSV/Excel (professor)
  GET    /api/attendance/low-attendance                — students below threshold (professor)
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse, FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, and_, case
from pydantic import BaseModel
from typing import Optional
from datetime import date, datetime, timezone
import io, csv, os

from config import settings
from db.session import get_db
from db.models import (
    User, ClassSession, AttendanceRecord, TimetableSlot,
    Subject, Semester, Enrollment, RoleEnum, AttendanceStatus
)
from auth.utils import get_current_user, require_professor, teaches_slot, ensure_teaches_subject

router = APIRouter(prefix="/api/attendance", tags=["attendance"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class SessionCreate(BaseModel):
    slot_id: str
    date: date
    notes: Optional[str] = None

class SessionOut(BaseModel):
    id: str
    slot_id: str
    subject_name: str
    subject_code: str
    date: date
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    is_completed: bool
    total_students: int
    present_count: int

class RecordOut(BaseModel):
    id: str
    student_id: str
    student_name: str
    roll_number: Optional[str]
    status: str
    recognised_at: Optional[datetime]
    confidence: Optional[float]
    is_overridden: bool
    override_reason: Optional[str]

class OverrideRequest(BaseModel):
    status: AttendanceStatus
    reason: str

class AttendanceSummaryItem(BaseModel):
    subject_id: str
    subject_name: str
    subject_code: str
    total_classes: int
    present: int
    absent: int
    percentage: float
    is_low: bool   # below 75%


# ─── Helpers ──────────────────────────────────────────────────────────────────

async def _session_out(session: ClassSession, db: AsyncSession) -> SessionOut:
    slot = await db.get(TimetableSlot, str(session.slot_id))
    subject = await db.get(Subject, str(slot.subject_id)) if slot else None

    total = await db.scalar(
        select(func.count()).where(AttendanceRecord.session_id == session.id)
    )
    present = await db.scalar(
        select(func.count()).where(
            AttendanceRecord.session_id == session.id,
            AttendanceRecord.status == AttendanceStatus.present,
        )
    )
    return SessionOut(
        id=str(session.id),
        slot_id=str(session.slot_id),
        subject_name=subject.name if subject else "Unknown",
        subject_code=subject.code if subject else "",
        date=session.date,
        started_at=session.started_at,
        ended_at=session.ended_at,
        is_completed=session.is_completed,
        total_students=total or 0,
        present_count=present or 0,
    )


async def _ensure_teaches(user: User, slot_id: str, db: AsyncSession):
    """403 unless the user teaches this class (admins always pass)."""
    if not await teaches_slot(user, slot_id, db):
        raise HTTPException(status_code=403, detail="You don't teach this class")


# ─── Sessions ─────────────────────────────────────────────────────────────────

@router.get("/sessions", response_model=list[SessionOut])
async def list_sessions(
    slot_id: Optional[str] = Query(None),
    subject_id: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = select(ClassSession).join(TimetableSlot, TimetableSlot.id == ClassSession.slot_id)

    if slot_id:
        q = q.where(ClassSession.slot_id == slot_id)
    if subject_id:
        q = q.where(TimetableSlot.subject_id == subject_id)
    if from_date:
        q = q.where(ClassSession.date >= from_date)
    if to_date:
        q = q.where(ClassSession.date <= to_date)

    # Professor sees only their sessions
    if current_user.role == RoleEnum.professor:
        q = (q.join(Subject, Subject.id == TimetableSlot.subject_id)
               .where(Subject.professor_id == current_user.id))

    q = q.order_by(ClassSession.date.desc(), ClassSession.started_at.desc())
    result = await db.execute(q)
    sessions = result.scalars().all()
    return [await _session_out(s, db) for s in sessions]


@router.post("/sessions", response_model=SessionOut, status_code=201)
async def create_session(
    body: SessionCreate,
    db: AsyncSession = Depends(get_db),
    prof: User = Depends(require_professor),
):
    await _ensure_teaches(prof, body.slot_id, db)

    # Prevent duplicate sessions for same slot+date
    existing = await db.execute(
        select(ClassSession).where(
            ClassSession.slot_id == body.slot_id,
            ClassSession.date == body.date,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="Session already exists for this slot and date")

    session = ClassSession(
        slot_id=body.slot_id,
        date=body.date,
        started_at=datetime.now(timezone.utc),
        conducted_by=str(prof.id),
        notes=body.notes,
    )
    db.add(session)
    await db.flush()

    # Pre-create ABSENT records for all enrolled students
    slot = await db.get(TimetableSlot, body.slot_id)
    if slot:
        enrolled = await db.execute(
            select(Enrollment).where(Enrollment.subject_id == slot.subject_id)
        )
        for enrollment in enrolled.scalars().all():
            db.add(AttendanceRecord(
                session_id=str(session.id),
                student_id=str(enrollment.student_id),
                status=AttendanceStatus.absent,
            ))

    return await _session_out(session, db)


@router.patch("/sessions/{session_id}/close", response_model=SessionOut)
async def close_session(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    prof: User = Depends(require_professor),
):
    session = await db.get(ClassSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    await _ensure_teaches(prof, session.slot_id, db)
    if session.is_completed:
        raise HTTPException(status_code=400, detail="Session already closed")

    session.is_completed = True
    session.ended_at = datetime.now(timezone.utc)
    db.add(session)
    return await _session_out(session, db)


# ─── Records for a session ────────────────────────────────────────────────────

@router.get("/sessions/{session_id}/records", response_model=list[RecordOut])
async def get_session_records(
    session_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    q = (
        select(AttendanceRecord, User)
        .join(User, User.id == AttendanceRecord.student_id)
        .where(AttendanceRecord.session_id == session_id)
        .order_by(User.name)
    )
    if current_user.role == RoleEnum.student:
        # Students only see their own record, never their classmates'
        q = q.where(AttendanceRecord.student_id == str(current_user.id))
    else:
        session = await db.get(ClassSession, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Session not found")
        await _ensure_teaches(current_user, session.slot_id, db)
    result = await db.execute(q)
    rows = result.all()
    return [
        RecordOut(
            id=str(r.id),
            student_id=str(r.student_id),
            student_name=u.name,
            roll_number=u.roll_number,
            status=r.status.value,
            recognised_at=r.recognised_at,
            confidence=r.confidence,
            is_overridden=r.is_overridden,
            override_reason=r.override_reason,
        )
        for r, u in rows
    ]


# ─── Override a record ────────────────────────────────────────────────────────

@router.patch("/records/{record_id}", response_model=RecordOut)
async def override_record(
    record_id: str,
    body: OverrideRequest,
    db: AsyncSession = Depends(get_db),
    prof: User = Depends(require_professor),
):
    record = await db.get(AttendanceRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    session = await db.get(ClassSession, str(record.session_id))
    await _ensure_teaches(prof, session.slot_id, db)

    record.status = body.status
    record.is_overridden = True
    record.override_by = str(prof.id)
    record.override_reason = body.reason
    record.override_at = datetime.now(timezone.utc)
    db.add(record)

    student = await db.get(User, str(record.student_id))
    return RecordOut(
        id=str(record.id),
        student_id=str(record.student_id),
        student_name=student.name if student else "",
        roll_number=student.roll_number if student else None,
        status=record.status.value,
        recognised_at=record.recognised_at,
        confidence=record.confidence,
        is_overridden=record.is_overridden,
        override_reason=record.override_reason,
    )


# ─── Face snapshot for a record ───────────────────────────────────────────────

@router.get("/records/{record_id}/snapshot")
async def get_record_snapshot(
    record_id: str,
    db: AsyncSession = Depends(get_db),
    prof: User = Depends(require_professor),
):
    """Face crop captured when the student was recognised — class professor only."""
    record = await db.get(AttendanceRecord, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    session = await db.get(ClassSession, str(record.session_id))
    await _ensure_teaches(prof, session.slot_id, db)

    # Only ever serve files from inside the snapshots folder
    snapshots_dir = os.path.realpath(settings.SNAPSHOTS_DIR)
    path = os.path.realpath(record.face_snapshot) if record.face_snapshot else ""
    if not path.startswith(snapshots_dir + os.sep) or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="No snapshot for this record")
    return FileResponse(path, media_type="image/jpeg")


# ─── Attendance summary (per student, per subject) ────────────────────────────

@router.get("/summary", response_model=list[AttendanceSummaryItem])
async def attendance_summary(
    student_id: Optional[str] = Query(None),
    semester_id: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    # Students always see their own; professors can query anyone
    target_id = student_id if current_user.role != RoleEnum.student else str(current_user.id)

    # Active semester fallback
    if not semester_id:
        active = await db.execute(select(Semester).where(Semester.is_active == True))
        sem = active.scalar_one_or_none()
        semester_id = str(sem.id) if sem else None

    # Get enrolled subjects
    q = (
        select(Subject)
        .join(Enrollment, Enrollment.subject_id == Subject.id)
        .where(Enrollment.student_id == target_id)
    )
    if semester_id:
        q = q.where(Subject.semester_id == semester_id)
    subjects_result = await db.execute(q)
    subjects = subjects_result.scalars().all()

    summary = []
    for subject in subjects:
        # Count total sessions for this subject
        total_sessions = await db.scalar(
            select(func.count(ClassSession.id))
            .join(TimetableSlot, TimetableSlot.id == ClassSession.slot_id)
            .where(
                TimetableSlot.subject_id == subject.id,
                ClassSession.is_completed == True,
            )
        ) or 0

        # Count present records
        present_count = await db.scalar(
            select(func.count(AttendanceRecord.id))
            .join(ClassSession, ClassSession.id == AttendanceRecord.session_id)
            .join(TimetableSlot, TimetableSlot.id == ClassSession.slot_id)
            .where(
                AttendanceRecord.student_id == target_id,
                TimetableSlot.subject_id == subject.id,
                AttendanceRecord.status.in_([AttendanceStatus.present, AttendanceStatus.late]),
                ClassSession.is_completed == True,
            )
        ) or 0

        absent_count = total_sessions - present_count
        percentage = round((present_count / total_sessions * 100), 1) if total_sessions > 0 else 0.0

        summary.append(AttendanceSummaryItem(
            subject_id=str(subject.id),
            subject_name=subject.name,
            subject_code=subject.code,
            total_classes=total_sessions,
            present=present_count,
            absent=absent_count,
            percentage=percentage,
            is_low=percentage < 75.0,
        ))

    return sorted(summary, key=lambda x: x.subject_name)


# ─── Students below 75% (professor dashboard) ────────────────────────────────

@router.get("/low-attendance")
async def low_attendance_students(
    semester_id: Optional[str] = Query(None),
    threshold: float = Query(75.0),
    db: AsyncSession = Depends(get_db),
    _prof: User = Depends(require_professor),
):
    """Returns all students below the attendance threshold across all subjects."""
    if not semester_id:
        active = await db.execute(select(Semester).where(Semester.is_active == True))
        sem = active.scalar_one_or_none()
        semester_id = str(sem.id) if sem else None

    # Get all enrolled students for subjects in this semester
    q = (
        select(User, Subject, Enrollment)
        .join(Enrollment, Enrollment.student_id == User.id)
        .join(Subject, Subject.id == Enrollment.subject_id)
        .where(User.role == RoleEnum.student, User.is_active == True)
    )
    if semester_id:
        q = q.where(Subject.semester_id == semester_id)

    result = await db.execute(q)
    rows = result.all()

    low = []
    for student, subject, _ in rows:
        # Total completed sessions for this subject
        total = await db.scalar(
            select(func.count(ClassSession.id))
            .join(TimetableSlot, TimetableSlot.id == ClassSession.slot_id)
            .where(TimetableSlot.subject_id == subject.id, ClassSession.is_completed == True)
        ) or 0

        if total == 0:
            continue

        present = await db.scalar(
            select(func.count(AttendanceRecord.id))
            .join(ClassSession, ClassSession.id == AttendanceRecord.session_id)
            .join(TimetableSlot, TimetableSlot.id == ClassSession.slot_id)
            .where(
                AttendanceRecord.student_id == student.id,
                TimetableSlot.subject_id == subject.id,
                AttendanceRecord.status.in_([AttendanceStatus.present, AttendanceStatus.late]),
                ClassSession.is_completed == True,
            )
        ) or 0

        percentage = round(present / total * 100, 1)
        if percentage < threshold:
            low.append({
                "student_id":   str(student.id),
                "student_name": student.name,
                "roll_number":  student.roll_number,
                "subject_id":   str(subject.id),
                "subject_name": subject.name,
                "subject_code": subject.code,
                "total_classes": total,
                "present":       present,
                "absent":        total - present,
                "percentage":    percentage,
            })

    return sorted(low, key=lambda x: x["percentage"])


# ─── Export attendance as CSV ─────────────────────────────────────────────────

@router.get("/export")
async def export_attendance(
    subject_id: Optional[str] = Query(None),
    semester_id: Optional[str] = Query(None),
    from_date: Optional[date] = Query(None),
    to_date: Optional[date] = Query(None),
    db: AsyncSession = Depends(get_db),
    prof: User = Depends(require_professor),
):
    # Build query for sessions
    q = (
        select(AttendanceRecord, User, ClassSession, Subject)
        .join(User, User.id == AttendanceRecord.student_id)
        .join(ClassSession, ClassSession.id == AttendanceRecord.session_id)
        .join(TimetableSlot, TimetableSlot.id == ClassSession.slot_id)
        .join(Subject, Subject.id == TimetableSlot.subject_id)
        .where(ClassSession.is_completed == True)
    )
    # Professors only export their own classes; admins export everything
    if prof.role != RoleEnum.admin:
        q = q.where(Subject.professor_id == str(prof.id))
    if subject_id:
        await ensure_teaches_subject(prof, subject_id, db)
        q = q.where(Subject.id == subject_id)
    if semester_id:
        q = q.where(Subject.semester_id == semester_id)
    if from_date:
        q = q.where(ClassSession.date >= from_date)
    if to_date:
        q = q.where(ClassSession.date <= to_date)
    q = q.order_by(User.name, ClassSession.date)

    result = await db.execute(q)
    rows = result.all()

    # Write CSV in memory
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "Roll No", "Student Name", "Subject Code", "Subject Name",
        "Date", "Status", "Recognised At", "Confidence", "Overridden", "Override Reason"
    ])
    for record, student, session, subject in rows:
        writer.writerow([
            student.roll_number or "",
            student.name,
            subject.code,
            subject.name,
            session.date.isoformat(),
            record.status.value,
            record.recognised_at.isoformat() if record.recognised_at else "",
            f"{record.confidence:.3f}" if record.confidence else "",
            "Yes" if record.is_overridden else "No",
            record.override_reason or "",
        ])

    output.seek(0)
    filename = f"attendance_export_{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
