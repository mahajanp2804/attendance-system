"""
Seed script — populates DB with demo data for development.
Run from backend/: python db/seed.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from datetime import date, time, timedelta
from auth.utils import hash_password
from db.session import AsyncSessionLocal, init_db
from db.models import User, Semester, Subject, Enrollment, TimetableSlot, RoleEnum, DayEnum


async def seed():
    await init_db()

    async with AsyncSessionLocal() as db:

        # ── Admin ──────────────────────────────────────────────────────────
        admin = User(
            name="Admin",
            email="admin@college.edu",
            password_hash=hash_password("admin123"),
            role=RoleEnum.admin,
        )
        db.add(admin)

        # ── Professors ─────────────────────────────────────────────────────
        prof1 = User(
            name="Dr. Priya Sharma",
            email="priya.sharma@college.edu",
            password_hash=hash_password("prof123"),
            role=RoleEnum.professor,
            department="Computer Science",
        )
        prof2 = User(
            name="Dr. Rajesh Kumar",
            email="rajesh.kumar@college.edu",
            password_hash=hash_password("prof123"),
            role=RoleEnum.professor,
            department="Electronics",
        )
        db.add_all([prof1, prof2])

        # ── Students ───────────────────────────────────────────────────────
        students = []
        for i in range(1, 11):
            s = User(
                name=f"Student {i:02d}",
                email=f"student{i:02d}@college.edu",
                password_hash=hash_password("student123"),
                role=RoleEnum.student,
                roll_number=f"CS2024{i:03d}",
                department="Computer Science",
                year_of_study=2,
                embedding_ready=False,
            )
            students.append(s)
        db.add_all(students)

        await db.flush()   # get IDs before creating FK references

        # ── Active semester ────────────────────────────────────────────────
        sem = Semester(
            name="Semester 5 (2024-25)",
            start_date=date(2024, 8, 1),
            end_date=date(2024, 11, 30),
            is_active=True,
        )
        db.add(sem)
        await db.flush()

        # ── Subjects ───────────────────────────────────────────────────────
        sub_os = Subject(
            name="Operating Systems",
            code="CS301",
            semester_id=sem.id,
            professor_id=prof1.id,
            department="Computer Science",
        )
        sub_dbms = Subject(
            name="Database Management",
            code="CS302",
            semester_id=sem.id,
            professor_id=prof1.id,
            department="Computer Science",
        )
        sub_ec = Subject(
            name="Digital Electronics",
            code="EC301",
            semester_id=sem.id,
            professor_id=prof2.id,
            department="Electronics",
        )
        db.add_all([sub_os, sub_dbms, sub_ec])
        await db.flush()

        # ── Timetable slots ────────────────────────────────────────────────
        slots = [
            TimetableSlot(subject_id=sub_os.id,   day=DayEnum.monday,    start_time=time(9, 0),  end_time=time(10, 0),  room="CS-101"),
            TimetableSlot(subject_id=sub_os.id,   day=DayEnum.wednesday, start_time=time(9, 0),  end_time=time(10, 0),  room="CS-101"),
            TimetableSlot(subject_id=sub_dbms.id, day=DayEnum.tuesday,   start_time=time(11, 0), end_time=time(12, 0),  room="CS-102"),
            TimetableSlot(subject_id=sub_dbms.id, day=DayEnum.thursday,  start_time=time(11, 0), end_time=time(12, 0),  room="CS-102"),
            TimetableSlot(subject_id=sub_ec.id,   day=DayEnum.friday,    start_time=time(14, 0), end_time=time(15, 0),  room="EC-201"),
        ]
        db.add_all(slots)
        await db.flush()

        # ── Enroll all CS students in CS subjects ──────────────────────────
        for student in students:
            for subject in [sub_os, sub_dbms]:
                db.add(Enrollment(student_id=student.id, subject_id=subject.id))

        await db.commit()

    print("✅ Seed complete.")
    print("   admin@college.edu       / admin123")
    print("   priya.sharma@college.edu / prof123")
    print("   student01@college.edu   / student123  (01–10)")


if __name__ == "__main__":
    asyncio.run(seed())
