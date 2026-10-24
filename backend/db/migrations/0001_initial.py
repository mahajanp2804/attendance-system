"""Initial migration — create all tables

Revision ID: 0001_initial
Revises: 
Create Date: 2024-01-01 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── users ──────────────────────────────────────────────────────────────
    op.create_table(
        'users',
        sa.Column('id',              postgresql.UUID, primary_key=True),
        sa.Column('name',            sa.String(120), nullable=False),
        sa.Column('email',           sa.String(200), nullable=False),
        sa.Column('password_hash',   sa.String(256), nullable=False),
        sa.Column('role',            sa.Enum('student','professor','admin', name='roleenum'), nullable=False),
        sa.Column('is_active',       sa.Boolean, default=True),
        sa.Column('roll_number',     sa.String(30)),
        sa.Column('department',      sa.String(100)),
        sa.Column('year_of_study',   sa.Integer),
        sa.Column('embedding_path',  sa.String(500)),
        sa.Column('face_photos_dir', sa.String(500)),
        sa.Column('embedding_ready', sa.Boolean, default=False),
        sa.Column('created_at',      sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at',      sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )
    op.create_index('ix_users_email',       'users', ['email'], unique=True)
    op.create_index('ix_users_roll_number', 'users', ['roll_number'], unique=True)

    # ── semesters ──────────────────────────────────────────────────────────
    op.create_table(
        'semesters',
        sa.Column('id',         postgresql.UUID, primary_key=True),
        sa.Column('name',       sa.String(100), nullable=False),
        sa.Column('start_date', sa.Date, nullable=False),
        sa.Column('end_date',   sa.Date, nullable=False),
        sa.Column('is_active',  sa.Boolean, default=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # ── subjects ───────────────────────────────────────────────────────────
    op.create_table(
        'subjects',
        sa.Column('id',           postgresql.UUID, primary_key=True),
        sa.Column('name',         sa.String(150), nullable=False),
        sa.Column('code',         sa.String(30),  nullable=False),
        sa.Column('semester_id',  postgresql.UUID, sa.ForeignKey('semesters.id'), nullable=False),
        sa.Column('professor_id', postgresql.UUID, sa.ForeignKey('users.id')),
        sa.Column('department',   sa.String(100)),
        sa.Column('created_at',   sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('code', 'semester_id', name='uq_subject_code_semester'),
    )
    op.create_index('ix_subjects_semester_id',  'subjects', ['semester_id'])
    op.create_index('ix_subjects_professor_id', 'subjects', ['professor_id'])

    # ── enrollments ────────────────────────────────────────────────────────
    op.create_table(
        'enrollments',
        sa.Column('id',          postgresql.UUID, primary_key=True),
        sa.Column('student_id',  postgresql.UUID, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('subject_id',  postgresql.UUID, sa.ForeignKey('subjects.id'), nullable=False),
        sa.Column('enrolled_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('student_id', 'subject_id', name='uq_enrollment'),
    )
    op.create_index('ix_enrollments_student_id', 'enrollments', ['student_id'])
    op.create_index('ix_enrollments_subject_id', 'enrollments', ['subject_id'])

    # ── timetable_slots ────────────────────────────────────────────────────
    op.create_table(
        'timetable_slots',
        sa.Column('id',         postgresql.UUID, primary_key=True),
        sa.Column('subject_id', postgresql.UUID, sa.ForeignKey('subjects.id'), nullable=False),
        sa.Column('day',        sa.Enum('monday','tuesday','wednesday','thursday','friday','saturday', name='dayenum'), nullable=False),
        sa.Column('start_time', sa.Time, nullable=False),
        sa.Column('end_time',   sa.Time, nullable=False),
        sa.Column('room',       sa.String(50)),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index('ix_timetable_slots_subject_id', 'timetable_slots', ['subject_id'])

    # ── class_sessions ─────────────────────────────────────────────────────
    op.create_table(
        'class_sessions',
        sa.Column('id',           postgresql.UUID, primary_key=True),
        sa.Column('slot_id',      postgresql.UUID, sa.ForeignKey('timetable_slots.id'), nullable=False),
        sa.Column('date',         sa.Date, nullable=False),
        sa.Column('started_at',   sa.DateTime(timezone=True)),
        sa.Column('ended_at',     sa.DateTime(timezone=True)),
        sa.Column('is_completed', sa.Boolean, default=False),
        sa.Column('conducted_by', postgresql.UUID, sa.ForeignKey('users.id')),
        sa.Column('notes',        sa.Text),
        sa.Column('created_at',   sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('slot_id', 'date', name='uq_session_slot_date'),
    )
    op.create_index('ix_class_sessions_slot_id', 'class_sessions', ['slot_id'])

    # ── attendance_records ─────────────────────────────────────────────────
    op.create_table(
        'attendance_records',
        sa.Column('id',              postgresql.UUID, primary_key=True),
        sa.Column('session_id',      postgresql.UUID, sa.ForeignKey('class_sessions.id'), nullable=False),
        sa.Column('student_id',      postgresql.UUID, sa.ForeignKey('users.id'), nullable=False),
        sa.Column('status',          sa.Enum('present','absent','late','excused', name='attendancestatus'), nullable=False),
        sa.Column('recognised_at',   sa.DateTime(timezone=True)),
        sa.Column('confidence',      sa.Float),
        sa.Column('face_snapshot',   sa.String(500)),
        sa.Column('is_overridden',   sa.Boolean, default=False),
        sa.Column('override_by',     postgresql.UUID, sa.ForeignKey('users.id')),
        sa.Column('override_reason', sa.Text),
        sa.Column('override_at',     sa.DateTime(timezone=True)),
        sa.Column('created_at',      sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at',      sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.UniqueConstraint('session_id', 'student_id', name='uq_attendance_per_session'),
    )
    op.create_index('ix_attendance_session_id', 'attendance_records', ['session_id'])
    op.create_index('ix_attendance_student_id', 'attendance_records', ['student_id'])


def downgrade() -> None:
    op.drop_table('attendance_records')
    op.drop_table('class_sessions')
    op.drop_table('timetable_slots')
    op.drop_table('enrollments')
    op.drop_table('subjects')
    op.drop_table('semesters')
    op.drop_table('users')
    op.execute("DROP TYPE IF EXISTS attendancestatus")
    op.execute("DROP TYPE IF EXISTS dayenum")
    op.execute("DROP TYPE IF EXISTS roleenum")
