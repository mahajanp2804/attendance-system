"""
FAISS index for fast nearest-neighbour face matching.
Loads all student embeddings into an in-memory index at startup.
Supports hot-reload when new embeddings are added.
"""

import numpy as np
import faiss
import os
import threading
from typing import Optional
from config import settings


class FaissIndex:
    """
    Wraps a FAISS IndexFlatIP (inner product on L2-normalised vectors = cosine similarity).
    Thread-safe for concurrent read (search) and write (add/reload).
    """

    def __init__(self):
        self._index: Optional[faiss.IndexFlatIP] = None
        self._student_ids: list[str] = []          # maps FAISS row → student_id
        self._lock = threading.RLock()
        self.DIM = 512

    def _new_index(self) -> faiss.IndexFlatIP:
        return faiss.IndexFlatIP(self.DIM)

    def load_all(self, embeddings_dir: str) -> int:
        """
        Scan embeddings_dir for *.npy files and load them all into FAISS.
        Each file is named {student_id}.npy and contains a 512-dim vector.
        Returns number of students loaded.
        """
        index = self._new_index()
        student_ids = []

        for fname in sorted(os.listdir(embeddings_dir)):
            if not fname.endswith(".npy"):
                continue
            student_id = fname[:-4]   # strip .npy
            path = os.path.join(embeddings_dir, fname)
            try:
                vec = np.load(path).astype("float32")
                if vec.shape != (self.DIM,):
                    print(f"⚠️  Skipping {fname}: unexpected shape {vec.shape}")
                    continue
                index.add(vec.reshape(1, -1))
                student_ids.append(student_id)
            except Exception as e:
                print(f"⚠️  Failed to load {fname}: {e}")

        with self._lock:
            self._index = index
            self._student_ids = student_ids

        print(f"✅ FAISS index loaded: {len(student_ids)} students")
        return len(student_ids)

    def add_student(self, student_id: str, embedding: np.ndarray):
        """Add or update a single student's embedding (hot-reload safe)."""
        vec = embedding.astype("float32").reshape(1, -1)
        with self._lock:
            if student_id in self._student_ids:
                # FAISS doesn't support update — rebuild
                self.load_all(settings.EMBEDDINGS_DIR)
                return
            if self._index is None:
                self._index = self._new_index()
            self._index.add(vec)
            self._student_ids.append(student_id)

    def search(
        self,
        query: np.ndarray,
        top_k: int = 1,
        allowed_ids: Optional[set[str]] = None,
    ) -> list[tuple[str, float]]:
        """
        Find the top_k closest students to the query embedding.
        If allowed_ids is given, only those students can be returned
        (e.g. the students enrolled in the class being scanned).
        Returns list of (student_id, cosine_similarity) sorted by similarity desc.
        Cosine similarity on L2-normalised vectors ∈ [-1, 1]; higher = better match.
        """
        with self._lock:
            if self._index is None or self._index.ntotal == 0:
                return []

            vec = query.astype("float32").reshape(1, -1)
            # When filtering, rank everyone so allowed students aren't cut off by top_k
            k = self._index.ntotal if allowed_ids is not None else min(top_k, self._index.ntotal)
            scores, indices = self._index.search(vec, k)

            results = []
            for score, idx in zip(scores[0], indices[0]):
                if idx == -1:
                    continue
                student_id = self._student_ids[idx]
                if allowed_ids is not None and student_id not in allowed_ids:
                    continue
                results.append((student_id, float(score)))
                if len(results) == top_k:
                    break

        return results

    def is_ready(self) -> bool:
        with self._lock:
            return self._index is not None and self._index.ntotal > 0

    @property
    def student_count(self) -> int:
        with self._lock:
            return len(self._student_ids)


# Global singleton — loaded once at app startup
faiss_index = FaissIndex()
