"""Local embeddings. Default zero-dep hashing embedder; optional sentence-transformers.

Hashing yields stable vectors for offline clustering/verifier retrieval.
Set NEWSAGENT_EMBED_MODEL=bge-small-en for real semantic embeddings.
"""

from __future__ import annotations

import hashlib
import math

import numpy as np

from newsagent.logging import get_logger

log = get_logger("embed")


class Embedder:
    """Unit-norm text vectors; pluggable model."""

    def __init__(self, model: str = "hashing", dim: int = 768, normalize: bool = True):
        self.model = model
        self.dim = dim
        self.normalize = normalize
        self._st_model = None
        if model not in ("hashing", "hash"):
            self._load_st()

    def _load_st(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer

            self._st_model = SentenceTransformer(self.model)
            self.dim = self._st_model.get_sentence_embedding_dimension()
            log.info("embed.loaded_st", model=self.model, dim=self.dim)
        except Exception as exc:  # noqa: BLE001
            log.warning("embed.st_unavailable", model=self.model, error=str(exc))
            self._st_model = None
            self.model = "hashing"

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        text = text.lower()
        tokens = []
        buf = []
        for ch in text:
            if ch.isalnum():
                buf.append(ch)
            else:
                if buf:
                    tokens.append("".join(buf))
                    buf = []
        if buf:
            tokens.append("".join(buf))
        return tokens

    def _hash_vector(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = self._tokenize(text)
        if not tokens:
            tokens = ["<empty>"]
        for tok in tokens:
            h = hashlib.md5(tok.encode("utf-8")).digest()
            # Two 32-bit buckets per token.
            i1 = int.from_bytes(h[0:4], "little") % self.dim
            i2 = int.from_bytes(h[4:8], "little") % self.dim
            s1 = 1.0 if (h[8] & 1) else -1.0
            s2 = 1.0 if (h[9] & 1) else -1.0
            vec[i1] += s1
            vec[i2] += s2
        # Lexical weighting by token frequency smoothing.
        vec /= math.sqrt(len(tokens)) + 1.0
        return vec

    def encode_one(self, text: str) -> np.ndarray:
        if self._st_model is not None and self.model != "hashing":
            vec = np.asarray(
                self._st_model.encode(text, normalize_embeddings=self.normalize), dtype=np.float32
            )
            return vec
        vec = self._hash_vector(text)
        if self.normalize:
            n = np.linalg.norm(vec)
            if n > 0:
                vec = vec / n
        return vec.astype(np.float32)

    def encode(self, texts: list[str]) -> np.ndarray:
        if self._st_model is not None and self.model != "hashing":
            vecs = self._st_model.encode(
                texts, batch_size=32, normalize_embeddings=self.normalize, show_progress_bar=False
            )
            return np.asarray(vecs, dtype=np.float32)
        return np.stack([self.encode_one(t) for t in texts]).astype(np.float32)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    na = np.linalg.norm(a)
    nb = np.linalg.norm(b)
    if na == 0 or nb == 0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))
