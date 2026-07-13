"""Embedder hashing backend — unit test."""

from __future__ import annotations

import numpy as np

from hermes.llm.embed import Embedder


def test_hashing_embedder_shape():
    emb = Embedder(model="hashing", dim=768, normalize=True)
    out = emb.encode(["hello world", "second text"])
    assert out.shape == (2, 768)


def test_hashing_embedder_unit_length():
    emb = Embedder(model="hashing", dim=128, normalize=True)
    out = emb.encode(["x", "y", "z"])
    norms = np.linalg.norm(out, axis=1)
    np.testing.assert_allclose(norms, 1.0, atol=1e-5)


def test_hashing_embedder_deterministic():
    emb = Embedder(model="hashing", dim=64, normalize=True)
    a = emb.encode(["alpha", "beta"])
    b = emb.encode(["alpha", "beta"])
    np.testing.assert_array_equal(a, b)
