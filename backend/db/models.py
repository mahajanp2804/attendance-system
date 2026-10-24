from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Date, Time,
    ForeignKey, Text, Float, Enum as SAEnum, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base
from sqlalchemy.sql import func
import uuid
import enum

Base = declarative_base()

def gen_uuid():
    return str(uuid.uuid4())


# ─── Enums ────────────────────────────────────────────────────────────────────

class RoleEnum(str, enum.Enum):
    student   = "student"
    professor = "professor"
    admin     = "admin"

class DayEnum(str, enum.Enum):
    monday    = "monday"
    tuesday   = "tuesday"
    wednesday = "wednesday"
    thursday  = "thursday"
    friday    = "friday"
    saturday  = "saturday"

class AttendanceStatus(str, enum.Enum):
    present  = "present"
    absent   = "absent"
    late     = "late"
    excused  = "excused"


# ─── Users ────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id             = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name           = Column(String(120), nullable=False)
    email          = Column(String(200), unique=True, nullable=False, index=True)
    password_hash  = Column(String(256), nullable=False)
    role           = Column(SAEnum(RoleEnum), nullable=False, default=RoleEnum.student)
    is_active      = Column(Boolean, default=True)
    created_at     = Column(DateTime(timezone=True), server_default=func.now())
    updated_at     = Column(DateTime(timezone=True), onupdate=func.now())

    # Student-specific
    roll_number    = Column(String(30), unique=True, nullable=True, index=True)
    department     = Column(String(100), nullable=True)
    year_of_study  = Column(Integer, nullable=True)   # 1, 2, 3, 4

    # Face recognition
    embedding_path = Column(String(500), nullable=True)   # path to .npy file
    face_photos_dir= Column(String(500), nullable=True)   # dir of enrollment photos
    embedding_ready= Column(Boolean, default=False)

    # Relationships
    enrollments    = relationship("Enrollment", back_populates="student", cascade="all, delete-orphan")
    attendance_records = relationship(
        "AttendanceRecord",
        back_populates="student",
        foreign_keys="AttendanceRecord.student_id",
        cascade="all, delete-orphan",
    )
    taught_subjects    = relationship("Subject", back_populates="professor")


# ─── Semesters ────────────────────────────────────────────────────────────────

class Semester(Base):
    __tablename__ = "semesters"

    id         = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name       = Column(String(100), nullable=False)   # e.g. "Sem 1 2024-25"
    start_date = Column(Date, nullable=False)
    end_date   = Column(Date, nullable=False)
    is_active  = Column(Boolean, default=False)        # only one active at a time
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    subjects   = relationship("Subject", back_populates="semester", cascade="all, delete-orphan")


# ─── Subjects ─────────────────────────────────────────────────────────────────

class Subject(Base):
    __tablename__ = "subjects"

    id           = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name         = Column(String(150), nullable=False)
    code         = Column(String(30), nullable=False)           # e.g. "CS301"
    semester_id  = Column(UUID(as_uuid=False), ForeignKey("semesters.id"), nullable=False, index=True)
    professor_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True, index=True)
    department   = Column(String(100), nullable=True)
    created_at   = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("code", "semester_id", name="uq_subject_code_semester"),)

    semester     = relationship("Semester", back_populates="subjects")
    professor    = relationship("User", back_populates="taught_subjects")
    timetable_slots = relationship("TimetableSlot", back_populates="subject", cascade="all, delete-orphan")
    enrollments  = relationship("Enrollment", back_populates="subject", cascade="all, delete-orphan")


# ─── Enrollments (student ↔ subject) ─────────────────────────────────────────

class Enrollment(Base):
    __tablename__ = "enrollments"

    id         = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    student_id = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    subject_id = Column(UUID(as_uuid=False), ForeignKey("subjects.id"), nullable=False, index=True)
    enrolled_at= Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("student_id", "subject_id", name="uq_enrollment"),)

    student    = relationship("User", back_populates="enrollments")
    subject    = relationship("Subject", back_populates="enrollments")


# ─── Timetable slots ──────────────────────────────────────────────────────────

class TimetableSlot(Base):
    __tablename__ = "timetable_slots"

    id          = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    subject_id  = Column(UUID(as_uuid=False), ForeignKey("subjects.id"), nullable=False, index=True)
    day         = Column(SAEnum(DayEnum), nullable=False)
    start_time  = Column(Time, nullable=False)
    end_time    = Column(Time, nullable=False)
    room        = Column(String(50), nullable=True)
    created_at  = Column(DateTime(timezone=True), server_default=func.now())

    subject     = relationship("Subject", back_populates="timetable_slots")
    sessions    = relationship("ClassSession", back_populates="slot", cascade="all, delete-orphan")


# ─── Class sessions (each actual class that happened) ─────────────────────────

class ClassSession(Base):
    __tablename__ = "class_sessions"

    id            = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    slot_id       = Column(UUID(as_uuid=False), ForeignKey("timetable_slots.id"), nullable=False, index=True)
    date          = Column(Date, nullable=False)
    started_at    = Column(DateTime(timezone=True), nullable=True)
    ended_at      = Column(DateTime(timezone=True), nullable=True)
    is_completed  = Column(Boolean, default=False)
    # professor who conducted (may differ from default)
    conducted_by  = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    notes         = Column(Text, nullable=True)
    created_at    = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (UniqueConstraint("slot_id", "date", name="uq_session_slot_date"),)

    slot          = relationship("TimetableSlot", back_populates="sessions")
    attendance_records = relationship("AttendanceRecord", back_populates="session", cascade="all, delete-orphan")


# ─── Attendance records ────────────────────────────────────────────────────────

class AttendanceRecord(Base):
    __tablename__ = "attendance_records"

    id              = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    session_id      = Column(UUID(as_uuid=False), ForeignKey("class_sessions.id"), nullable=False, index=True)
    student_id      = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=False, index=True)
    status          = Column(SAEnum(AttendanceStatus), nullable=False, default=AttendanceStatus.absent)

    # Face recognition metadata
    recognised_at   = Column(DateTime(timezone=True), nullable=True)   # first detection time
    confidence      = Column(Float, nullable=True)                      # FaceNet match score
    face_snapshot   = Column(String(500), nullable=True)               # path to face crop image

    # Manual override
    is_overridden   = Column(Boolean, default=False)
    override_by     = Column(UUID(as_uuid=False), ForeignKey("users.id"), nullable=True)
    override_reason = Column(Text, nullable=True)
    override_at     = Column(DateTime(timezone=True), nullable=True)

    created_at      = Column(DateTime(timezone=True), server_default=func.now())
    updated_at      = Column(DateTime(timezone=True), onupdate=func.now())

    __table_args__ = (UniqueConstraint("session_id", "student_id", name="uq_attendance_per_session"),)

    session         = relationship("ClassSession", back_populates="attendance_records")
    student         = relationship("User", back_populates="attendance_records", foreign_keys=[student_id])
    overridden_by_user = relationship("User", foreign_keys=[override_by])
