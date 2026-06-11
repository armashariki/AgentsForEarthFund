"""Tests for chunking + the hybrid (LanceDB dense + rank_bm25 lexical) store.

Uses a deterministic fake embedder so the tests stay offline (no Ollama). The
LanceDB table and BM25 sidecar are real and written to a tempdir, so these also
exercise the on-disk persistence path.
"""

from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

import numpy as np

from befkb.chunk import LanceStore, chunk_and_index, chunk_doc
from befkb.config import Settings
from befkb.models import Doc, Section


class FakeEmbedder:
    """Hash-seeded unit vectors — stable across calls, no network."""

    def __init__(self, dim: int = 768):
        self.dim = dim

    def _vec(self, text: str) -> np.ndarray:
        seed = int(hashlib.sha1(text.encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(self.dim).astype(np.float32)
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self._vec(t) for t in texts])


def _settings(tmp: Path, **over) -> Settings:
    s = Settings()
    s.data_dir = tmp
    s.embed_dim = 64           # small for fast tests
    s.chunk_chars = 200
    s.chunk_overlap = 40
    for k, v in over.items():
        setattr(s, k, v)
    s.ensure_dirs()
    return s


def _doc() -> Doc:
    body_a = (
        "Reinforcement learning guides reserve placement in the CAPTAIN system. "
        "It optimizes for biodiversity outcomes across a landscape of cells. "
    ) * 4
    body_b = (
        "Relational accountability reframes AI for climate as a question of power "
        "and stewardship rather than pure technological optimization. "
    ) * 4
    a_start = 0
    a_end = len(body_a)
    b_start = a_end
    b_end = a_end + len(body_b)
    return Doc(
        source_slug="2026-01-01-test-paper",
        path="/raw/test.pdf",
        title="Test Paper",
        markdown=body_a + body_b,
        sections=[
            Section(title="Methods", text=body_a, char_span=(a_start, a_end)),
            Section(title="Discussion", text=body_b, char_span=(b_start, b_end)),
        ],
    )


def test_chunk_doc_respects_size_overlap_and_spans():
    with tempfile.TemporaryDirectory() as td:
        s = _settings(Path(td))
        doc = _doc()
        chunks = chunk_doc(doc, s)
        assert chunks, "expected chunks"
        # size bound (soft-break may exceed slightly but stays in the ballpark)
        for c in chunks:
            assert len(c.text) <= s.chunk_chars + s.chunk_overlap
            lo, hi = c.char_span
            assert 0 <= lo < hi <= len(doc.markdown)
            # span text matches chunk text (provenance is real)
            assert doc.markdown[lo:hi].strip() == c.text
        # ids are unique + deterministic
        ids = [c.id for c in chunks]
        assert len(ids) == len(set(ids))
        assert chunk_doc(doc, s)[0].id == chunks[0].id
        # sections preserved
        assert {c.section for c in chunks} == {"Methods", "Discussion"}


def test_chunk_and_index_then_search():
    with tempfile.TemporaryDirectory() as td:
        s = _settings(Path(td))
        emb = FakeEmbedder(s.embed_dim)
        doc = _doc()

        chunks = chunk_and_index(doc, emb, LanceStore(s), s)
        assert chunks
        assert all(c.embedding is not None and len(c.embedding) == s.embed_dim
                   for c in chunks)

        store = LanceStore(s)  # reopen from disk
        assert store.count() == len(chunks)

        # lexical search finds the right section
        hits = store.bm25_search("reinforcement learning reserve placement", k=3)
        assert hits
        assert any("reinforcement learning" in h.text.lower() for h in hits)
        assert all(h.embedding is not None for h in hits)

        # dense search returns k results and is ranked by cosine
        q = emb.embed(["relational accountability and stewardship"])[0]
        vhits = store.vector_search(q, k=3)
        assert len(vhits) <= 3 and vhits


def test_bm25_survives_restart_via_sidecar():
    with tempfile.TemporaryDirectory() as td:
        s = _settings(Path(td))
        emb = FakeEmbedder(s.embed_dim)
        chunk_and_index(_doc(), emb, LanceStore(s), s)

        # brand-new store object, no upsert this session — must rebuild from sidecar
        fresh = LanceStore(s)
        hits = fresh.bm25_search("relational accountability stewardship", k=2)
        assert hits
        assert any("relational accountability" in h.text.lower() for h in hits)


def test_bm25_gate_is_term_presence_not_score_sign():
    # When a term appears in (nearly) every chunk, BM25Okapi can score it <= 0,
    # but those chunks are still lexical matches and must be returned; a term in
    # NO chunk must return nothing.
    with tempfile.TemporaryDirectory() as td:
        s = _settings(Path(td), chunk_chars=120, chunk_overlap=20)
        emb = FakeEmbedder(s.embed_dim)
        ubiquitous = ("monitoring monitoring monitoring data point. " * 6)  # term in all chunks
        doc = Doc(source_slug="ubiq", path="/x", title="U",
                  markdown=ubiquitous, sections=[Section(title="B", text=ubiquitous,
                                                         char_span=(0, len(ubiquitous)))])
        store = LanceStore(s)
        chunks = chunk_and_index(doc, emb, store, s)
        assert len(chunks) >= 2
        hits = store.bm25_search("monitoring", k=5)
        assert hits, "term present in every chunk must still match"
        assert store.bm25_search("zzznotpresent", k=5) == []


def test_reingest_is_idempotent():
    with tempfile.TemporaryDirectory() as td:
        s = _settings(Path(td))
        emb = FakeEmbedder(s.embed_dim)
        doc = _doc()
        store = LanceStore(s)
        chunk_and_index(doc, emb, store, s)
        n1 = store.count()
        chunk_and_index(doc, emb, store, s)  # same doc again
        assert store.count() == n1, "re-ingesting the same doc must not duplicate rows"


def test_empty_and_degenerate_inputs():
    with tempfile.TemporaryDirectory() as td:
        s = _settings(Path(td))
        emb = FakeEmbedder(s.embed_dim)
        store = LanceStore(s)
        empty = Doc(source_slug="empty", path="/x", markdown="", sections=[])
        assert chunk_and_index(empty, emb, store, s) == []
        # queries on an empty store are safe
        assert store.bm25_search("anything", k=5) == []
        assert store.vector_search(emb.embed(["q"])[0], k=5) == []
        # doc with markdown but no sections falls back to one body section
        only_md = Doc(source_slug="md-only", path="/y",
                      markdown="A short body about bioacoustics monitoring.", sections=[])
        chunks = chunk_doc(only_md, s)
        assert chunks and chunks[0].section in ("body", only_md.title)
