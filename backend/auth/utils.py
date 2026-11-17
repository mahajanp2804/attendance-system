from datetime import datetime, timedelta, timezone
from typing import Optional
import hashlib, hmac
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from config import settings
from db.session import get_db
from db.models import User, RoleEnum, TimetableSlot, Subject

pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


# ─── Password ─────────────────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_ctx.hash(plain)

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)


# ─── JWT tokens ───────────────────────────────────────────────────────────────

def password_fingerprint(password_hash: str) -> str:
    """
    Keyed hash of the stored password hash, put in every token as "pwd".
    It changes whenever the password does, so tokens issued before a
    password change stop working — no extra DB column needed.
    """
    return hmac.new(settings.SECRET_KEY.encode(), password_hash.encode(), hashlib.sha256).hexdigest()[:32]

def token_matches_password(payload: dict, user: User) -> bool:
    return hmac.compare_digest(str(payload.get("pwd", "")), password_fingerprint(user.password_hash))

def create_access_token(user_id: str, role: str, password_hash: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    return jwt.encode(
        {"sub": user_id, "role": role, "exp": expire, "type": "access",
         "pwd": password_fingerprint(password_hash)},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

def create_refresh_token(user_id: str, password_hash: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": user_id, "exp": expire, "type": "refresh",
         "pwd": password_fingerprint(password_hash)},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")


# ─── FastAPI dependencies ─────────────────────────────────────────────────────

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    payload = decode_token(token)
    if payload.get("type") != "access":
        raise HTTPException(status_code=401, detail="Invalid token type")

    user_id = payload.get("sub")
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found or inactive")
    if not token_matches_password(payload, user):
        raise HTTPException(status_code=401, detail="Password changed — please log in again")
    return user


def require_role(*roles: RoleEnum):
    """Dependency factory — only allows specified roles."""
    async def checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Access denied. Required role(s): {[r.value for r in roles]}"
            )
        return current_user
    return checker

require_student   = require_role(RoleEnum.student)
require_professor = require_role(RoleEnum.professor, RoleEnum.admin)
require_admin     = require_role(RoleEnum.admin)


# ─── Class ownership ──────────────────────────────────────────────────────────

async def teaches_subject(user: User, subject_id: str, db: AsyncSession) -> bool:
    """True if the user is an admin or the subject's professor."""
    if user.role == RoleEnum.admin:
        return True
    if user.role != RoleEnum.professor:
        return False
    subject = await db.get(Subject, str(subject_id))
    return subject is not None and str(subject.professor_id) == str(user.id)


async def teaches_slot(user: User, slot_id: str, db: AsyncSession) -> bool:
    """True if the user is an admin or the professor of the slot's subject."""
    if user.role == RoleEnum.admin:
        return True
    slot = await db.get(TimetableSlot, str(slot_id))
    return slot is not None and await teaches_subject(user, slot.subject_id, db)


async def ensure_teaches_subject(user: User, subject_id: str, db: AsyncSession):
    """403 unless the user teaches this subject (admins always pass)."""
    if not await teaches_subject(user, subject_id, db):
        raise HTTPException(status_code=403, detail="You don't teach this class")
