"""
FaceNet embedder.
Converts a face crop (numpy array) into a 512-dim L2-normalised embedding.
Also handles batch embedding generation for student enrollment.
"""

import numpy as np
import torch
import cv2
import os
from PIL import Image
from facenet_pytorch import InceptionResnetV1, MTCNN
from typing import Optional
from config import settings


class FaceEmbedder:
    def __init__(self):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model = None
        self._aligner = None

    def _load(self):
        if self._model is None:
            # InceptionResnetV1 pretrained on VGGFace2 — 512-dim embeddings
            self._model = InceptionResnetV1(pretrained="vggface2").eval().to(self.device)
            # MTCNN for alignment (ensures face is properly centred before embedding)
            self._aligner = MTCNN(
                image_size=160,
                margin=20,
                keep_all=False,
                device=self.device,
                post_process=True,
            )
        print(f"✅ FaceNet loaded on {self.device}")

    def embed(self, face_bgr: np.ndarray) -> Optional[np.ndarray]:
        """
        Embed a single face crop (BGR numpy array).
        Returns L2-normalised 512-dim numpy vector, or None if alignment fails.
        """
        self._load()
        # Convert BGR → RGB PIL for MTCNN
        face_rgb = cv2.cvtColor(face_bgr, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(face_rgb)

        aligned = self._aligner(pil_img)
        if aligned is None:
            return None

        with torch.no_grad():
            tensor = aligned.unsqueeze(0).to(self.device)
            embedding = self._model(tensor).cpu().numpy()[0]

        # L2 normalise
        norm = np.linalg.norm(embedding)
        if norm == 0:
            return None
        return embedding / norm

    def embed_batch(self, face_crops: list[np.ndarray]) -> list[Optional[np.ndarray]]:
        """Embed multiple face crops in one forward pass for efficiency."""
        self._load()
        tensors, indices = [], []

        for i, crop in enumerate(face_crops):
            face_rgb = cv2.cvtColor(crop, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(face_rgb)
            aligned = self._aligner(pil_img)
            if aligned is not None:
                tensors.append(aligned)
                indices.append(i)

        results = [None] * len(face_crops)
        if not tensors:
            return results

        with torch.no_grad():
            batch = torch.stack(tensors).to(self.device)
            embeddings = self._model(batch).cpu().numpy()

        for j, idx in enumerate(indices):
            emb = embeddings[j]
            norm = np.linalg.norm(emb)
            results[idx] = emb / norm if norm > 0 else None

        return results


async def generate_and_save_embedding(
    student_id: str,
    photos_dir: str,
    output_dir: str,
) -> str:
    """
    Generate mean embedding from all face photos in photos_dir.
    Saves a .npy file to output_dir/{student_id}.npy.
    Returns the saved path.
    """
    embedder = FaceEmbedder()
    embedder._load()

    photo_files = [
        f for f in os.listdir(photos_dir)
        if f.lower().endswith((".jpg", ".jpeg", ".png"))
    ]
    if not photo_files:
        raise ValueError("No photos found in photos_dir")

    embeddings = []
    for filename in photo_files:
        path = os.path.join(photos_dir, filename)
        img = cv2.imread(path)
        if img is None:
            continue
        emb = embedder.embed(img)
        if emb is not None:
            embeddings.append(emb)

    if not embeddings:
        raise ValueError("Could not extract any valid face embeddings from the photos")

    # Average all embeddings and re-normalise → one robust reference vector
    mean_emb = np.mean(embeddings, axis=0)
    norm = np.linalg.norm(mean_emb)
    mean_emb = mean_emb / norm if norm > 0 else mean_emb

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{student_id}.npy")
    np.save(out_path, mean_emb)

    return out_path


# Singleton
embedder = FaceEmbedder()
