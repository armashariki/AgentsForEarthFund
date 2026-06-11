"""Chunking + hybrid retrieval store.

Splits each :class:`~befkb.models.Doc` section into overlapping character windows,
embeds them, and writes them to a :class:`LanceStore`. The store is a thin wrapper
around an embedded LanceDB table (``chunks``) for dense vector search, plus a parallel
in-memory ``rank_bm25.BM25Okapi`` index (persisted to a JSON sidecar) for lexical search.

Design notes
------------
* **Local-first, zero-server.** LanceDB is embedded (a directory on disk); BM25 lives
  in-process and is rebuilt on every upsert from the persisted corpus.
* **Robust at small scale.** No ANN index is built — LanceDB falls back to an exact
  (brute-force) scan, which is correct and fast for the document counts here.
* **Idempotent upserts.** Chunk ids are deterministic, so re-ingesting a document
  replaces its rows rather than duplicating them.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

import numpy as np

from .config import Settings
from .models import Chunk, Doc, short_hash, slugify

# --------------------------------------------------------------------------- #
# Chunking
# --------------------------------------------------------------------------- #

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Cheap, dependency-free tokenizer for BM25 (lowercase alnum runs)."""
    return _TOKEN_RE.findall(text.lower())


def _chunk_id(source_slug: str, char_span: tuple[int, int]) -> str:
    """Deterministic chunk id so re-ingest overwrites instead of duplicating."""
    return f"{source_slug}:{char_span[0]}-{char_span[1]}:{short_hash(f'{source_slug}:{char_span[0]}:{char_span[1]}')}"


def _split_section(
    text: str,
    *,
    base_offset: int,
    chunk_chars: int,
    overlap: int,
) -> list[tuple[str, tuple[int, int]]]:
    """Window ``text`` into ~``chunk_chars`` pieces with ``overlap`` carry-over.

    Returns ``(chunk_text, (abs_start, abs_end))`` pairs where the span is in
    coordinates of the parent document (``base_offset`` is the section start).
    Tries to break on a whitespace boundary near the window edge to avoid
    splitting mid-word; falls back to a hard cut.
    """
    text = text or ""
    n = len(text)
    if n == 0:
        return []
    chunk_chars = max(1, int(chunk_chars))
    overlap = max(0, min(int(overlap), chunk_chars - 1))
    step = max(1, chunk_chars - overlap)

    out: list[tuple[str, tuple[int, int]]] = []
    start = 0
    while start < n:
        end = min(start + chunk_chars, n)
        # Prefer to end on a whitespace boundary if we are not at the very end.
        if end < n:
            window = text[start:end]
            ws = window.rfind(" ")
            nl = window.rfind("\n")
            cut = max(ws, nl)
            # Only honour the soft break if it leaves a reasonably full chunk.
            if cut != -1 and cut >= int(chunk_chars * 0.5):
                end = start + cut + 1
        piece = text[start:end].strip()
        if piece:
            # Recover the true span of the stripped piece within the document.
            raw = text[start:end]
            lead = len(raw) - len(raw.lstrip())
            trail = len(raw) - len(raw.rstrip())
            span = (base_offset + start + lead, base_offset + end - trail)
            out.append((piece, span))
        if end >= n:
            break
        # CRITICAL: advance from the ACTUAL window end, never start+step — a soft
        # whitespace break can pull `end` well short of start+step, and taking the
        # start+step branch would jump past `end`, silently dropping a span of text.
        start = max(end - overlap, start + 1)
    return out


def chunk_doc(doc: Doc, settings: Settings) -> list[Chunk]:
    """Split a parsed document into :class:`Chunk` objects (no embeddings yet)."""
    chunks: list[Chunk] = []
    seen: set[str] = set()

    sections = doc.sections or []
    # Fall back to the whole markdown body as one section if the parser gave none.
    if not sections and doc.markdown:
        from .models import Section

        sections = [Section(title=doc.title or "body", text=doc.markdown,
                             char_span=(0, len(doc.markdown)))]

    for section in sections:
        base = section.char_span[0] if section.char_span else 0
        for piece, span in _split_section(
            section.text,
            base_offset=base,
            chunk_chars=settings.chunk_chars,
            overlap=settings.chunk_overlap,
        ):
            cid = _chunk_id(doc.source_slug, span)
            if cid in seen:  # defensive against identical spans
                continue
            seen.add(cid)
            chunks.append(
                Chunk(
                    id=cid,
                    source_slug=doc.source_slug,
                    section=section.title or "body",
                    text=piece,
                    char_span=span,
                )
            )
    return chunks


# --------------------------------------------------------------------------- #
# Store: LanceDB (dense) + rank_bm25 (lexical)
# --------------------------------------------------------------------------- #

class LanceStore:
    """Embedded LanceDB table + a persisted BM25 sidecar.

    The LanceDB table ``chunks`` holds dense vectors for cosine search. A parallel
    ``rank_bm25.BM25Okapi`` index over all chunk texts provides lexical search; its
    corpus is mirrored to ``bm25.json`` so it survives process restarts and is
    rebuilt lazily on first use.
    """

    TABLE = "chunks"

    def __init__(self, settings: Settings):
        self.settings = settings
        self.dim = settings.embed_dim
        self._db_dir = Path(settings.lancedb_dir)
        self._db_dir.mkdir(parents=True, exist_ok=True)
        self._sidecar = self._db_dir / "bm25.json"

        import lancedb

        self._db = lancedb.connect(str(self._db_dir))
        self._table = self._open_or_create_table()

        # Lazily-built BM25 state.
        self._bm25 = None
        self._bm25_ids: list[str] = []
        self._bm25_corpus: dict[str, str] = self._load_sidecar()

    # ---- table lifecycle -------------------------------------------------- #

    def _arrow_schema(self):
        import pyarrow as pa

        return pa.schema(
            [
                pa.field("id", pa.string()),
                pa.field("source_slug", pa.string()),
                pa.field("section", pa.string()),
                pa.field("text", pa.string()),
                pa.field("char_start", pa.int64()),
                pa.field("char_end", pa.int64()),
                pa.field("vector", pa.list_(pa.float32(), self.dim)),
            ]
        )

    def _open_or_create_table(self):
        # Prefer opening an existing table; only create if it truly isn't there.
        # (Avoids relying on the version-specific list_tables/table_names quirks.)
        try:
            return self._db.open_table(self.TABLE)
        except Exception:
            pass
        try:
            return self._db.create_table(self.TABLE, schema=self._arrow_schema())
        except Exception:
            # Lost a create race (or it appeared between calls) — open it.
            return self._db.open_table(self.TABLE)

    # ---- BM25 sidecar ----------------------------------------------------- #

    def _load_sidecar(self) -> dict[str, str]:
        if self._sidecar.exists():
            try:
                data = json.loads(self._sidecar.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items()}
            except Exception:
                pass
        return {}

    def _save_sidecar(self) -> None:
        tmp = self._sidecar.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self._bm25_corpus, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self._sidecar)

    def _rebuild_bm25(self) -> None:
        """(Re)build the in-memory BM25 index from the persisted corpus."""
        from rank_bm25 import BM25Okapi

        self._bm25_ids = list(self._bm25_corpus.keys())
        if not self._bm25_ids:
            self._bm25 = None
            return
        tokenized = [_tokenize(self._bm25_corpus[i]) for i in self._bm25_ids]
        # BM25Okapi needs at least one non-empty doc; guard the degenerate case.
        if not any(tokenized):
            self._bm25 = None
            return
        self._bm25 = BM25Okapi(tokenized)

    def _ensure_bm25(self) -> None:
        if self._bm25 is None and self._bm25_corpus:
            self._rebuild_bm25()

    # ---- writes ----------------------------------------------------------- #

    def upsert(self, chunks: list[Chunk]) -> None:
        """Insert/replace chunk rows (and rebuild the BM25 index).

        Chunks must already carry ``embedding``. Existing rows with the same id
        are deleted first so re-ingestion is idempotent.
        """
        chunks = [c for c in chunks if c.text and c.text.strip()]
        if not chunks:
            return

        # Build vector rows ONLY for chunks with a valid embedding. Never fabricate a
        # zero vector — LanceDB's cosine metric silently drops zero-norm rows, making
        # them invisible to vector search while count() still counts them.
        import sys

        rows = []
        skipped_vec = 0
        for c in chunks:
            vec = c.embedding
            if vec is None or len(vec) != self.dim:
                skipped_vec += 1
                continue
            rows.append(
                {
                    "id": c.id,
                    "source_slug": c.source_slug,
                    "section": c.section,
                    "text": c.text,
                    "char_start": int(c.char_span[0]),
                    "char_end": int(c.char_span[1]),
                    "vector": list(map(float, vec)),
                }
            )
        if skipped_vec:
            print(
                f"[befkb] warning: {skipped_vec} chunk(s) lacked a valid embedding; "
                "indexed lexically only (kept out of the vector index).",
                file=sys.stderr,
            )

        # Idempotent re-ingest: evict ALL prior rows for these sources. Chunk ids encode
        # the char span, so they shift when a document's text changes — a by-new-id delete
        # would orphan the old rows in both LanceDB and BM25.
        slugs = {c.source_slug for c in chunks}
        slug_list = ", ".join("'" + s.replace("'", "''") + "'" for s in slugs)
        try:
            self._table.delete(f"source_slug IN ({slug_list})")
        except Exception:
            pass
        if rows:
            self._table.add(rows)

        # BM25 covers ALL chunks (lexical recall even when un-embedded). Prune prior
        # chunks of these same sources first (chunk id == "<source_slug>:<span>:<hash>").
        self._bm25_corpus = {
            cid: t for cid, t in self._bm25_corpus.items()
            if cid.split(":", 1)[0] not in slugs
        }
        for c in chunks:
            self._bm25_corpus[c.id] = c.text
        self._save_sidecar()
        self._rebuild_bm25()

    # ---- reads ------------------------------------------------------------ #

    def _row_to_chunk(self, row: dict) -> Chunk:
        vec = row.get("vector")
        embedding = list(map(float, vec)) if vec is not None else None
        return Chunk(
            id=row["id"],
            source_slug=row.get("source_slug", ""),
            section=row.get("section", "body"),
            text=row.get("text", ""),
            char_span=(int(row.get("char_start", 0)), int(row.get("char_end", 0))),
            embedding=embedding,
        )

    def vector_search(self, q_emb: np.ndarray, k: int = 10) -> list[Chunk]:
        """Dense cosine search. ``q_emb`` is an already-embedded query vector."""
        if k <= 0:
            return []
        q = np.asarray(q_emb, dtype=np.float32).reshape(-1)
        if q.size == 0:
            return []
        try:
            res = (
                self._table.search(q.tolist())
                .metric("cosine")
                .limit(k)
                .to_list()
            )
        except Exception:
            return []
        return [self._row_to_chunk(r) for r in res]

    def bm25_search(self, q: str, k: int = 10) -> list[Chunk]:
        """Lexical BM25 search over all chunk texts; returns top-``k`` chunks.

        Relevance gate is *term presence*, not score sign: BM25Okapi can assign
        zero/negative scores to terms that occur in (nearly) every document, but
        those chunks are still lexical matches. We keep any chunk that contains at
        least one query token, ranked by BM25 score (ties broken by index order).
        """
        if k <= 0 or not q or not q.strip():
            return []
        self._ensure_bm25()
        if self._bm25 is None or not self._bm25_ids:
            return []
        q_tokens = set(_tokenize(q))
        if not q_tokens:
            return []
        scores = self._bm25.get_scores(list(q_tokens))
        if len(scores) == 0:
            return []
        # Candidate = any chunk whose tokens overlap the query (true match).
        candidates = [
            i for i in range(len(self._bm25_ids))
            if q_tokens & set(_tokenize(self._bm25_corpus.get(self._bm25_ids[i], "")))
        ]
        if not candidates:
            return []
        candidates.sort(key=lambda i: float(scores[i]), reverse=True)
        top_ids = [self._bm25_ids[i] for i in candidates[:k]]
        return self._fetch_by_ids(top_ids)

    def _fetch_by_ids(self, ids: list[str]) -> list[Chunk]:
        """Fetch full chunk rows from LanceDB for an ordered id list."""
        if not ids:
            return []
        in_list = ", ".join("'" + i.replace("'", "''") + "'" for i in ids)
        try:
            rows = self._table.search().where(f"id IN ({in_list})").limit(len(ids)).to_list()
        except Exception:
            rows = []
        by_id = {r["id"]: r for r in rows}
        return [self._row_to_chunk(by_id[i]) for i in ids if i in by_id]

    # ---- introspection ---------------------------------------------------- #

    def count(self) -> int:
        try:
            return self._table.count_rows()
        except Exception:
            return len(self._bm25_corpus)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

def chunk_and_index(
    doc: Doc,
    embedder,
    store: LanceStore,
    settings: Settings,
) -> list[Chunk]:
    """Chunk ``doc``, embed each chunk, write to ``store``, return chunks w/ embeddings.

    Embeddings are attached to the returned :class:`Chunk` objects so callers
    (e.g. the ingest pipeline) can reuse them without re-embedding.
    """
    chunks = chunk_doc(doc, settings)
    if not chunks:
        return []

    texts = [c.text for c in chunks]
    embs = np.asarray(embedder.embed(texts), dtype=np.float32)
    if embs.ndim == 1:  # single-vector edge case
        embs = embs.reshape(1, -1)

    if embs.shape[0] == len(chunks):
        for i, c in enumerate(chunks):
            c.embedding = embs[i].tolist() if embs[i].size == settings.embed_dim else None
    else:
        # Batch came back short — re-embed individually so no chunk is silently left
        # vector-invisible. A still-failing chunk gets embedding=None (BM25-only).
        import sys

        print(
            f"[befkb] warning: embedder returned {embs.shape[0]} vectors for "
            f"{len(chunks)} chunks; re-embedding individually.",
            file=sys.stderr,
        )
        for c in chunks:
            e = np.asarray(embedder.embed([c.text]), dtype=np.float32).reshape(-1)
            c.embedding = e.tolist() if e.size == settings.embed_dim else None

    store.upsert(chunks)
    return chunks
