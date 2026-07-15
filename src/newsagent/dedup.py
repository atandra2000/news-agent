"""Dedup: SHA-256 exact match + 64-bit SimHash near-duplicate detection.

Zero deps. Near-dup if Hamming distance between SimHashes <= ``threshold``.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass


@dataclass
class DedupResult:
    is_new: bool
    canonical_uid: str | None = None
    is_near_dup: bool = False


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 2]


def simhash(text: str, bits: int = 64) -> int:
    tokens = _tokens(text)
    if not tokens:
        return 0
    v = [0] * bits
    for tok in tokens:
        h = int.from_bytes(hashlib.md5(tok.encode("utf-8")).digest()[:8], "little")
        for i in range(bits):
            if (h >> i) & 1:
                v[i] += 1
            else:
                v[i] -= 1
    out = 0
    for i in range(bits):
        if v[i] > 0:
            out |= 1 << i
    # Mask to signed 63-bit so it fits SQLite/NumPy INTEGER columns safely.
    return out & ((1 << 63) - 1)


def hamming(a: int, b: int) -> int:
    return (a ^ b).bit_count()


class Deduper:
    def __init__(self, *, simhash_threshold: int = 3):
        self.simhash_threshold = simhash_threshold
        self._by_simhash: list[tuple[int, str]] = []  # (simhash, canonical_uid)

    def check(self, uid: str, text: str) -> DedupResult:
        # Exact SHA-256 match handled by DB uniqueness; here we only do SimHash.
        sh = simhash(text)
        for existing_sh, canonical in self._by_simhash:
            if hamming(sh, existing_sh) <= self.simhash_threshold:
                return DedupResult(is_new=False, canonical_uid=canonical, is_near_dup=True)
        return DedupResult(is_new=True)

    def add(self, text: str, canonical_uid: str) -> None:
        self._by_simhash.append((simhash(text), canonical_uid))

    def reset(self) -> None:
        self._by_simhash.clear()
