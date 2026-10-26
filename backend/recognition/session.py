"""
Session-level deduplication tracker.
Ensures the first recognition per student per class session is the one that counts.
Held in memory during a live session; DB is the source of truth after session ends.
"""

from datetime import datetime, timezone
from dataclasses import dataclass, field
from typing import Optional
import threading


@dataclass
class RecognitionEvent:
    student_id: str
    confidence: float
    recognised_at: datetime
    face_snapshot_path: Optional[str] = None


class SessionTracker:
    """
    Tracks which students have been recognised in the current scan session.
    Thread-safe for concurrent frame processing.
    """

    def __init__(self, session_id: str):
        self.session_id = session_id
        self._recognised: dict[str, RecognitionEvent] = {}  # student_id → first event
        self._lock = threading.Lock()

    def try_mark(
        self,
        student_id: str,
        confidence: float,
        snapshot_path: Optional[str] = None,
    ) -> tuple[bool, Optional[RecognitionEvent]]:
        """
        Attempt to mark a student as present.
        Returns (True, event) if first time — should be written to DB.
        Returns (False, existing_event) if already marked — ignore this detection.
        """
        with self._lock:
            if student_id in self._recognised:
                return False, self._recognised[student_id]

            event = RecognitionEvent(
                student_id=student_id,
                confidence=confidence,
                recognised_at=datetime.now(timezone.utc),
                face_snapshot_path=snapshot_path,
            )
            self._recognised[student_id] = event
            return True, event

    def is_recognised(self, student_id: str) -> bool:
        with self._lock:
            return student_id in self._recognised

    def get_all_recognised(self) -> list[RecognitionEvent]:
        with self._lock:
            return list(self._recognised.values())

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._recognised)


class SessionTrackerRegistry:
    """
    Global registry of active scan sessions.
    Keyed by class_session_id.
    """

    def __init__(self):
        self._sessions: dict[str, SessionTracker] = {}
        self._lock = threading.Lock()

    def get_or_create(self, session_id: str) -> SessionTracker:
        with self._lock:
            if session_id not in self._sessions:
                self._sessions[session_id] = SessionTracker(session_id)
            return self._sessions[session_id]

    def remove(self, session_id: str):
        with self._lock:
            self._sessions.pop(session_id, None)

    def active_sessions(self) -> list[str]:
        with self._lock:
            return list(self._sessions.keys())


# Global registry singleton
tracker_registry = SessionTrackerRegistry()
