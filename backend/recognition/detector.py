"""
YOLOv8 face detector.
Detects all faces in a frame and returns bounding boxes + confidence scores.
"""

import numpy as np
import cv2
import urllib.request
from pathlib import Path
from typing import NamedTuple
from ultralytics import YOLO
from config import settings

YOLO_FACE_MODEL_URL = (
    "https://github.com/YapaLab/yolo-face/releases/download/1.0.0/yolov8n-face.pt"
)


class FaceBox(NamedTuple):
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float


def _ensure_yolo_model(path: str) -> str:
    model_path = Path(path)
    if model_path.exists():
        return str(model_path)

    model_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading YOLO face model to {model_path}...")
    urllib.request.urlretrieve(YOLO_FACE_MODEL_URL, model_path)
    print("✅ YOLO face model ready.")
    return str(model_path)


class YOLOFaceDetector:
    def __init__(self):
        self._model = None

    def _load(self):
        if self._model is None:
            model_path = _ensure_yolo_model(settings.YOLO_MODEL_PATH)
            self._model = YOLO(model_path)

    def detect(self, frame: np.ndarray) -> list[FaceBox]:
        """
        Detect all faces in a BGR numpy frame.
        Returns list of FaceBox (x1,y1,x2,y2,confidence).
        Filters out boxes smaller than MIN_FACE_SIZE.
        """
        self._load()
        results = self._model(frame, verbose=False)[0]
        boxes = []

        if results.boxes is None:
            return boxes

        for box in results.boxes:
            x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
            conf = float(box.conf[0])

            # Filter tiny/low-confidence detections
            w, h = x2 - x1, y2 - y1
            if w < settings.MIN_FACE_SIZE or h < settings.MIN_FACE_SIZE:
                continue
            if conf < 0.5:
                continue

            boxes.append(FaceBox(x1=x1, y1=y1, x2=x2, y2=y2, confidence=conf))

        return boxes

    def crop_face(self, frame: np.ndarray, box: FaceBox, padding: float = 0.15) -> np.ndarray:
        """Crop face region with optional padding."""
        h, w = frame.shape[:2]
        pad_x = int((box.x2 - box.x1) * padding)
        pad_y = int((box.y2 - box.y1) * padding)

        x1 = max(0, box.x1 - pad_x)
        y1 = max(0, box.y1 - pad_y)
        x2 = min(w, box.x2 + pad_x)
        y2 = min(h, box.y2 + pad_y)

        return frame[y1:y2, x1:x2]


# Singleton instance — loaded once on first use
detector = YOLOFaceDetector()
