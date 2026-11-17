from pydantic_settings import BaseSettings
from typing import List
import json, os

class Settings(BaseSettings):
    # App
    APP_NAME: str = "Smart Attendance System"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://attendance_user:attendance_pass@localhost:5432/attendance_db"
    DATABASE_URL_SYNC: str = "postgresql://attendance_user:attendance_pass@localhost:5432/attendance_db"

    # Auth
    SECRET_KEY: str = "dev-secret-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # CORS
    CORS_ORIGINS: str = '["http://localhost:5173","http://localhost:3000"]'

    @property
    def cors_origins_list(self) -> List[str]:
        return json.loads(self.CORS_ORIGINS)

    # File storage
    EMBEDDINGS_DIR: str = "data/embeddings"
    FACE_PHOTOS_DIR: str = "data/face_photos"
    SNAPSHOTS_DIR: str = "data/snapshots"

    # Face recognition
    RECOGNITION_THRESHOLD: float = 0.75
    YOLO_MODEL_PATH: str = "data/models/yolov8n-face.pt"
    MIN_FACE_SIZE: int = 40      # px — ignore tiny detections

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

# Anyone who knows the secret key can sign their own admin tokens, so never run
# outside DEBUG with a known placeholder or a short key
_PLACEHOLDER_KEYS = {
    "dev-secret-change-in-production",
    "change-this-to-a-long-random-string-in-production",
    "change-this-in-production-use-openssl-rand-hex-32",
}
if settings.SECRET_KEY in _PLACEHOLDER_KEYS or len(settings.SECRET_KEY) < 32:
    if not settings.DEBUG:
        raise RuntimeError(
            "SECRET_KEY is missing, a placeholder, or shorter than 32 characters. "
            "Generate one with `openssl rand -hex 32` and set it in backend/.env"
        )
    print("⚠️  Using a weak SECRET_KEY — fine for local DEBUG, never in production")

# Ensure data dirs exist at startup
for d in [settings.EMBEDDINGS_DIR, settings.FACE_PHOTOS_DIR, settings.SNAPSHOTS_DIR,
          os.path.dirname(settings.YOLO_MODEL_PATH)]:
    os.makedirs(d, exist_ok=True)
