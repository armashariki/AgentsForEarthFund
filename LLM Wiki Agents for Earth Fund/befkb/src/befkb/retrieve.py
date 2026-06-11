"""Retrieval over the two indexes: the LanceDB chunk store and the graph.

Three responsibilities, kept dependency-light:

1. ``hybrid_search`` — reciprocal-rank fusion (RRF) of dense (vector) and sparse
   (BM25) chunk retrieval, so a query finds chunks that *either* index ranks high.
2. ``expand_to_subgraph`` — a bounded breadth-first walk out from a set of seed
   node ids, collecting the Nodes and Edges reachable within ``hops``. This turns
   a few anchor nodes (e.g. resolved entities from a new doc) into the local
   neighbourhood the applicability/narration layer reasons over.
3. ``evidence_for_edge`` — surface the provenance (a :class:`Citation`) attached
   to a single edge, so every graph fact a connection rests on can be quoted back
   to ``raw/``.

This module reads only; it never mutates the stores it is handed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional, Protocol

import numpy as np

from .models import Chunk, Citation, Edge, Node

if TYPE_CHECKING:  # pragma: no cover — siblings imported only for type checking
    from .llm import Embedder

# RRF damping constant (Cormack et al. 2009). Larger -> flatter contribution from
# rank position; 60 is the field-standard default and what the contract specifies.
_RRF_K = 60


# --------------------------------------------------------------------------- #
# Structural protocols for the two stores we read from.
#
# We type against duck-typed Protocols rather than importing chunk.py /
# graphstore.py concretely: it keeps retrieve.py importable on its own and
# avoids a hard import cycle, while still documenting the exact surface we use.
# --------------------------------------------------------------------------- #

class _LanceStoreLike(Protocol):
    def vector_search(self, q_emb: np.ndarray, k: int) -> list[Chunk]: ...
    def bm25_search(self, q: str, k: int) -> list[Chunk]: ...


class _GraphStoreLike(Protocol):
    def get_node(self, node_id: str) -> Optional[Node]: ...
    def neighbors(self, node_id: str, rels: Optional[list[str]] = None) -> list[Edge]: ...


# --------------------------------------------------------------------------- #
# Retriever
# --------------------------------------------------------------------------- #

class Retriever:
    """Hybrid (dense + sparse) chunk search plus local graph expansion.

    Parameters
    ----------
    lance:
        The LanceDB-backed chunk store (``chunk.LanceStore``); supplies
        ``vector_search`` and ``bm25_search``.
    embedder:
        Produces query embeddings (``llm.get_embedder``); ``embed`` returns an
        ``(n, dim)`` array whose rows are vectors.
    graph:
        The knowledge graph (``graphstore.NetworkXGraphStore``); supplies
        ``get_node`` and ``neighbors``.
    """

    def __init__(self, lance: "_LanceStoreLike", embedder: "Embedder", graph: "_GraphStoreLike"):
        self.lance = lance
        self.embedder = embedder
        self.graph = graph

    # ------------------------------------------------------------------ #
    # Chunk retrieval
    # ------------------------------------------------------------------ #

    def hybrid_search(self, query: str, k: int = 10) -> list[Chunk]:
        """Fuse vector and BM25 chunk retrieval via Reciprocal Rank Fusion.

        Each list contributes ``1 / (RRF_K + rank)`` per chunk (rank is 0-based);
        scores are summed across the two lists and the union is returned sorted by
        fused score, truncated to ``k``. A chunk that only one index returns still
        scores; a chunk both rank highly floats to the top.
        """
        query = (query or "").strip()
        if not query or k <= 0:
            return []

        # Pull a slightly deeper candidate pool from each retriever so the fusion
        # has room to rerank, then truncate the fused result to k.
        pool = max(k, 1)

        # --- dense / vector leg ---
        vector_hits: list[Chunk] = []
        try:
            q_emb = self.embedder.embed([query])
            if isinstance(q_emb, np.ndarray) and q_emb.shape[0] > 0:
                vector_hits = self.lance.vector_search(q_emb[0], pool) or []
        except Exception:
            # A dead embedder / empty index must not sink the whole query; fall
            # back to whatever BM25 can find.
            vector_hits = []

        # --- sparse / lexical leg ---
        try:
            bm25_hits = self.lance.bm25_search(query, pool) or []
        except Exception:
            bm25_hits = []

        if not vector_hits and not bm25_hits:
            return []

        # --- RRF fusion ---
        scores: dict[str, float] = {}
        by_id: dict[str, Chunk] = {}
        for hits in (vector_hits, bm25_hits):
            for rank, chunk in enumerate(hits):
                if chunk is None or not getattr(chunk, "id", None):
                    continue
                scores[chunk.id] = scores.get(chunk.id, 0.0) + 1.0 / (_RRF_K + rank)
                by_id.setdefault(chunk.id, chunk)

        ranked_ids = sorted(scores, key=lambda cid: scores[cid], reverse=True)
        return [by_id[cid] for cid in ranked_ids[:k]]

    # ------------------------------------------------------------------ #
    # Graph expansion
    # ------------------------------------------------------------------ #

    def expand_to_subgraph(
        self, seed_node_ids: list[str], hops: int = 2
    ) -> tuple[list[Node], list[Edge]]:
        """Breadth-first walk out from ``seed_node_ids``, up to ``hops`` away.

        Returns every reachable Node (seeds included, when they exist in the
        graph) and every Edge traversed within the hop budget, both de-duplicated.
        Edges are de-duplicated on the ``(src, rel, dst)`` triple so parallel
        edges in the underlying MultiDiGraph collapse to one logical fact.

        ``hops=0`` returns just the seed Nodes and no edges.
        """
        seeds = [s for s in (seed_node_ids or []) if s]
        if not seeds:
            return [], []

        visited: set[str] = set()
        nodes: dict[str, Node] = {}
        edges: dict[tuple[str, str, str], Edge] = {}

        def _remember_node(node_id: str) -> None:
            if node_id in nodes:
                return
            node = self.graph.get_node(node_id)
            if node is not None:
                nodes[node_id] = node

        # Seed the frontier; record seed nodes even at hops==0.
        frontier: list[str] = []
        for sid in seeds:
            if sid not in visited:
                visited.add(sid)
                _remember_node(sid)
                frontier.append(sid)

        for _ in range(max(hops, 0)):
            if not frontier:
                break
            next_frontier: list[str] = []
            for node_id in frontier:
                try:
                    incident = self.graph.neighbors(node_id) or []
                except Exception:
                    incident = []
                for edge in incident:
                    if edge is None:
                        continue
                    key = (edge.src, edge.rel, edge.dst)
                    edges.setdefault(key, edge)
                    # The neighbour is whichever endpoint isn't the current node
                    # (neighbors() may return edges in either direction).
                    for endpoint in (edge.src, edge.dst):
                        if endpoint and endpoint not in visited:
                            visited.add(endpoint)
                            _remember_node(endpoint)
                            next_frontier.append(endpoint)
            frontier = next_frontier

        return list(nodes.values()), list(edges.values())

    # ------------------------------------------------------------------ #
    # Evidence
    # ------------------------------------------------------------------ #

    def evidence_for_edge(self, edge: Edge) -> list[Citation]:
        """Return the edge's citation as a single-element list, or ``[]`` if none."""
        if edge is None or edge.citation is None:
            return []
        return [edge.citation]
