"""Vector store: numpy brute-force cosine (default) or Qdrant-embedded.

Brute-force cosine is sub-second on CPU below ~100K items (HERMES_DESIGN §11.3);
Qdrant is local on-disk (no server), offered for future RAG/search.
"""

from __future__ import annotations

import numpy as np
from sqlalchemy import select

from hermes.logging import get_logger
from hermes.storage.models import VectorRow

log = get_logger("vectorstore")


class VectorStore:
    async def upsert(self, uids: list[str], vectors: np.ndarray) -> None: ...

    async def search(self, vector: np.ndarray, *, top_k: int, threshold: float) -> list[tuple[str, float]]: ...

    async def get(self, uid: str) -> np.ndarray | None: ...


class NumpyVectorStore(VectorStore):
    """Vectors persisted in the SQLite ``vectors`` table as packed float32."""

    def __init__(self, session_factory):
        self.session_factory = session_factory
        self._cache: dict[str, np.ndarray] = {}

    @staticmethod
    def _pack(v: np.ndarray) -> bytes:
        return np.ascontiguousarray(v, dtype=np.float32).tobytes()

    @staticmethod
    def _unpack(b: bytes) -> np.ndarray:
        return np.frombuffer(b, dtype=np.float32).copy()

    async def upsert(self, uids: list[str], vectors: np.ndarray) -> None:
        vectors = np.asarray(vectors, dtype=np.float32)
        async with self.session_factory() as session:
            for uid, vec in zip(uids, vectors):
                self._cache[uid] = vec
                await session.merge(VectorRow(uid=uid, vec=self._pack(vec)))
            await session.commit()

    async def get(self, uid: str) -> np.ndarray | None:
        if uid in self._cache:
            return self._cache[uid]
        async with self.session_factory() as session:
            row = (await session.execute(select(VectorRow).where(VectorRow.uid == uid))).scalar_one_or_none()
            if row is None:
                return None
            vec = self._unpack(row.vec)
            self._cache[uid] = vec
            return vec

    async def search(self, vector: np.ndarray, *, top_k: int, threshold: float) -> list[tuple[str, float]]:
        vector = np.asarray(vector, dtype=np.float32)
        async with self.session_factory() as session:
            rows = (await session.execute(select(VectorRow))).scalars().all()
        if not rows:
            return []
        uids = [r.uid for r in rows]
        matrix = np.stack([self._unpack(r.vec) for r in rows])
        # +1e-9 guards zero-norm.
        vn = vector / (np.linalg.norm(vector) + 1e-9)
        mn = matrix / (np.linalg.norm(matrix, axis=1, keepdims=True) + 1e-9)
        sims = mn @ vn
        order = np.argsort(-sims)
        out: list[tuple[str, float]] = []
        for i in order[:top_k]:
            s = float(sims[i])
            if s >= threshold:
                out.append((uids[i], s))
        return out


class QdrantLocalStore(VectorStore):
    def __init__(self, session_factory, path: str, collection: str, dim: int):
        from qdrant_client import QdrantClient

        self._session_factory = session_factory
        self.dim = dim
        self.collection = collection
        self.client = QdrantClient(path=path)
        self._ensure()

    def _ensure(self) -> None:
        from qdrant_client.models import Distance, VectorParams

        if not self.client.collection_exists(self.collection):
            self.client.create_collection(
                self.collection, vectors_config=VectorParams(size=self.dim, distance=Distance.COSINE)
            )

    async def upsert(self, uids: list[str], vectors: np.ndarray) -> None:
        from qdrant_client.models import PointStruct

        vectors = np.asarray(vectors, dtype=np.float32)
        points = [
            PointStruct(id=abs(hash(u)) % (2**63), vector=vectors[i].tolist(), payload={"uid": u})
            for i, u in enumerate(uids)
        ]
        self.client.upsert(self.collection, points=points)

    async def get(self, uid: str) -> np.ndarray | None:
        return None

    async def search(self, vector: np.ndarray, *, top_k: int, threshold: float) -> list[tuple[str, float]]:
        vector = np.asarray(vector, dtype=np.float32).tolist()
        hits = self.client.search(self.collection, query_vector=vector, limit=top_k, score_threshold=threshold)
        return [(h.payload.get("uid", str(h.id)), float(h.score)) for h in hits]


def build_vector_store(backend: str, session_factory, *, qdrant_path: str, collection: str, dim: int) -> VectorStore:
    if backend == "qdrant":
        try:
            return QdrantLocalStore(session_factory, str(qdrant_path), collection, dim)
        except Exception as exc:  # noqa: BLE001
            log.warning("vectorstore.qdrant_failed_fallback_numpy", error=str(exc))
    return NumpyVectorStore(session_factory)
