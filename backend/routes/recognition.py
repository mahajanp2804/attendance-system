"""
Face recognition WebSocket endpoint.

Flow:
  1. Professor opens /api/recognition/ws/{session_id}
  2. Client sends raw JPEG frames as binary WebSocket messages
  3. Server detects all faces, matches via FAISS, deduplicates
  4. Server writes PRESENT records to DB (first recognition wins)
  5. Server sends back JSON with recognised faces + live counters
  6. On disconnect / session close → remaining students auto-marked absent
"""

import asyncio
import cv2
import json
import numpy as np
import os
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional

from db.session import AsyncSessionLocal
from db.models import AttendanceRecord, AttendanceStatus, ClassSession, User, RoleEnum
from recognition.detector import detector
from recognition.embedder import embedder
from recognition.faiss_index import faiss_index
from recognition.session import tracker_registry
from recognition.worker import run_ml
from config import settings
from auth.utils import decode_token, require_professor, teaches_slot

router = APIRouter(prefix="/api/recognition", tags=["recognition"])


# ─── HTTP helpers ─────────────────────────────────────────────────────────────

@router.post("/reload-index")
async def reload_faiss_index(_prof: User = Depends(require_professor)):
    """Force-reload FAISS index after new student embeddings are added."""
    count = faiss_index.load_all(settings.EMBEDDINGS_DIR)
    return {"status": "reloaded", "students_indexed": count}


@router.get("/index-status")
async def index_status(_prof: User = Depends(require_professor)):
    return {
        "ready": faiss_index.is_ready(),
        "students_indexed": faiss_index.student_count,
    }


# ─── WebSocket endpoint ───────────────────────────────────────────────────────

@router.websocket("/ws/{session_id}")
async def recognition_ws(websocket: WebSocket, session_id: str):
    """
    WebSocket for live face recognition during a class session.

    Auth: send JWT token as first text message after connecting.
    Then send JPEG frames as binary messages.

    Receives JSON:
      { "type": "result",
        "faces": [{"student_id", "name", "roll_number", "confidence", "box": [x1,y1,x2,y2], "already_marked": bool}],
        "unknown_count": int,
        "present_count": int,
        "total_enrolled": int,
        "session_id": str }
    """
    await websocket.accept()

    # ── Auth handshake ────────────────────────────────────────────────────────
    try:
        token_msg = await asyncio.wait_for(websocket.receive_text(), timeout=10.0)
        payload = decode_token(token_msg)
        if payload.get("type") != "access" or payload.get("role") not in ("professor", "admin"):
            await websocket.send_text(json.dumps({"type": "error", "message": "Professors only"}))
            await websocket.close()
            return
        professor_id = payload["sub"]
    except asyncio.TimeoutError:
        await websocket.send_text(json.dumps({"type": "error", "message": "Auth timeout"}))
        await websocket.close()
        return
    except Exception:
        await websocket.send_text(json.dumps({"type": "error", "message": "Auth failed"}))
        await websocket.close()
        return

    # ── Validate session exists ───────────────────────────────────────────────
    async with AsyncSessionLocal() as db:
        session_obj = await db.get(ClassSession, session_id)
        if not session_obj:
            await websocket.send_text(json.dumps({"type": "error", "message": "Session not found"}))
            await websocket.close()
            return
        if session_obj.is_completed:
            await websocket.send_text(json.dumps({"type": "error", "message": "Session already closed"}))
            await websocket.close()
            return

        # Token is valid, but the account must still be active and teach this class
        user = await db.get(User, professor_id)
        if not user or not user.is_active:
            await websocket.send_text(json.dumps({"type": "error", "message": "Account not active"}))
            await websocket.close()
            return
        if not await teaches_slot(user, session_obj.slot_id, db):
            await websocket.send_text(json.dumps({"type": "error", "message": "You don't teach this class"}))
            await websocket.close()
            return

        # Students enrolled in this class — only they can be matched,
        # so a lookalike from another class is never marked present here
        from db.models import TimetableSlot, Enrollment
        slot = await db.get(TimetableSlot, str(session_obj.slot_id))
        enrolled_ids: set[str] = set()
        if slot:
            rows = await db.scalars(
                select(Enrollment.student_id).where(Enrollment.subject_id == slot.subject_id)
            )
            enrolled_ids = {str(student_id) for student_id in rows}
        total_enrolled = len(enrolled_ids)

    # ── Get or create dedup tracker for this session ──────────────────────────
    tracker = tracker_registry.get_or_create(session_id)

    await websocket.send_text(json.dumps({
        "type": "connected",
        "session_id": session_id,
        "total_enrolled": total_enrolled,
        "index_ready": faiss_index.is_ready(),
        "students_indexed": faiss_index.student_count,
    }))

    # ── Main frame processing loop ────────────────────────────────────────────
    try:
        while True:
            raw = await websocket.receive()

            # Text control messages (e.g. "close")
            if "text" in raw:
                msg = json.loads(raw["text"])
                if msg.get("action") == "close":
                    break
                continue

            # Binary = JPEG frame
            if "bytes" not in raw:
                continue

            frame_bytes = raw["bytes"]
            frame = _decode_frame(frame_bytes)
            if frame is None:
                # Still reply, so the scanner knows it can send the next frame
                await websocket.send_text(json.dumps({"type": "skipped", "reason": "Could not decode frame"}))
                continue

            result = await _process_frame(frame, session_id, tracker, enrolled_ids)
            await websocket.send_text(json.dumps(result, default=str))

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(json.dumps({"type": "error", "message": str(e)}))
        except Exception:
            pass
    finally:
        tracker_registry.remove(session_id)


# ─── Frame processing ─────────────────────────────────────────────────────────

def _decode_frame(data: bytes) -> Optional[np.ndarray]:
    """Decode JPEG bytes → BGR numpy array."""
    try:
        arr = np.frombuffer(data, dtype=np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        return frame
    except Exception:
        return None


def _detect_and_match(frame: np.ndarray, enrolled_ids: set[str]) -> list[tuple]:
    """
    Blocking part of frame processing — runs on the inference worker.
    Detects all faces, embeds them in one batch and finds each one's closest
    enrolled student.
    Returns (box, student_id, similarity) per face; student_id is None when the
    face couldn't be embedded or nobody matched.
    """
    boxes = detector.detect(frame)
    if not boxes:
        return []

    crops = [detector.crop_face(frame, box) for box in boxes]
    embeddings = embedder.embed_batch(crops)

    results = []
    for box, embedding in zip(boxes, embeddings):
        matches = (
            faiss_index.search(embedding, top_k=1, allowed_ids=enrolled_ids)
            if embedding is not None else []
        )
        if matches:
            student_id, similarity = matches[0]
            results.append((box, student_id, similarity))
        else:
            results.append((box, None, None))
    return results


async def _process_frame(
    frame: np.ndarray,
    session_id: str,
    tracker,
    enrolled_ids: set[str],
) -> dict:
    """
    Detect all faces, embed, match FAISS, deduplicate, write DB if first recognition.
    Returns JSON-serialisable result dict.
    """
    matches = await run_ml(_detect_and_match, frame, enrolled_ids)

    faces_out = []
    unknown_count = 0

    for box, student_id, similarity in matches:
        if student_id is None:
            unknown_count += 1
            faces_out.append({
                "status": "unknown",
                "confidence": 0.0,
                "box": [box.x1, box.y1, box.x2, box.y2],
            })
            continue

        # Cosine similarity threshold — below this = unknown
        if similarity < settings.RECOGNITION_THRESHOLD:
            unknown_count += 1
            faces_out.append({
                "status": "low_confidence",
                "confidence": round(similarity, 3),
                "box": [box.x1, box.y1, box.x2, box.y2],
            })
            continue

        # Deduplication
        is_first, event = tracker.try_mark(student_id, similarity)

        if is_first:
            # Save face snapshot
            snapshot_path = _save_snapshot(frame, box, session_id, student_id)
            # Write PRESENT to DB asynchronously
            asyncio.create_task(
                _mark_present_db(session_id, student_id, similarity, snapshot_path)
            )

        # Fetch student info for response
        student_info = await _get_student_info(student_id)

        faces_out.append({
            "status": "recognised",
            "student_id": student_id,
            "name": student_info.get("name", ""),
            "roll_number": student_info.get("roll_number", ""),
            "confidence": round(similarity, 3),
            "already_marked": not is_first,
            "box": [box.x1, box.y1, box.x2, box.y2],
        })

    return {
        "type": "result",
        "faces": faces_out,
        "unknown_count": unknown_count,
        "present_count": tracker.count,
        "total_enrolled": len(enrolled_ids),
        "session_id": session_id,
    }


async def _mark_present_db(
    session_id: str,
    student_id: str,
    confidence: float,
    snapshot_path: Optional[str],
):
    """Write/update attendance record to PRESENT in DB."""
    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(AttendanceRecord).where(
                    AttendanceRecord.session_id == session_id,
                    AttendanceRecord.student_id == student_id,
                )
            )
            record = result.scalar_one_or_none()

            if record:
                # Only update if not manually overridden
                if not record.is_overridden:
                    record.status = AttendanceStatus.present
                    record.recognised_at = datetime.now(timezone.utc)
                    record.confidence = confidence
                    record.face_snapshot = snapshot_path
                    db.add(record)
            else:
                # Create new record
                db.add(AttendanceRecord(
                    session_id=session_id,
                    student_id=student_id,
                    status=AttendanceStatus.present,
                    recognised_at=datetime.now(timezone.utc),
                    confidence=confidence,
                    face_snapshot=snapshot_path,
                ))
            await db.commit()
        except Exception as e:
            await db.rollback()
            print(f"⚠️  DB write failed for {student_id}: {e}")


def _save_snapshot(
    frame: np.ndarray,
    box,
    session_id: str,
    student_id: str,
) -> Optional[str]:
    """Save face crop as JPEG snapshot. Returns relative path."""
    try:
        crop = detector.crop_face(frame, box)
        dir_path = os.path.join(settings.SNAPSHOTS_DIR, session_id)
        os.makedirs(dir_path, exist_ok=True)
        filename = f"{student_id}_{uuid.uuid4().hex[:8]}.jpg"
        full_path = os.path.join(dir_path, filename)
        cv2.imwrite(full_path, crop)
        return full_path
    except Exception:
        return None


# Simple in-memory student info cache to avoid repeated DB hits per frame
_student_cache: dict[str, dict] = {}

async def _get_student_info(student_id: str) -> dict:
    if student_id in _student_cache:
        return _student_cache[student_id]
    async with AsyncSessionLocal() as db:
        user = await db.get(User, student_id)
        if user:
            info = {"name": user.name, "roll_number": user.roll_number or ""}
            _student_cache[student_id] = info
            return info
    return {"name": "Unknown", "roll_number": ""}



