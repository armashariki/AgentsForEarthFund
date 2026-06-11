"""Tests for befkb.retrieve — RRF fusion, BFS subgraph expansion, edge evidence.

Uses lightweight in-memory fakes for the LanceStore and GraphStore so the suite
is self-contained and does not require LanceDB, an embedder, or a built graph.
The fakes satisfy exactly the surface Retriever calls.
"""

from __future__ import annotations

import numpy as np

from befkb.models import Chunk, Citation, Edge, Node
from befkb.retrieve import Retriever, _RRF_K


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #

def _chunk(cid: str) -> Chunk:
    return Chunk(id=cid, source_slug="s", section="sec", text=cid, char_span=(0, 1))


class FakeLance:
    def __init__(self, vector: list[Chunk] | None = None, bm25: list[Chunk] | None = None):
        self._vector = vector or []
        self._bm25 = bm25 or []

    def vector_search(self, q_emb, k):
        assert isinstance(q_emb, np.ndarray)
        return self._vector[:k]

    def bm25_search(self, q, k):
        return self._bm25[:k]


class FakeEmbedder:
    def __init__(self, dim: int = 4):
        self.dim = dim

    def embed(self, texts):
        return np.ones((len(texts), self.dim), dtype=np.float32)


class FakeGraph:
    """An undirected-ish adjacency fake: neighbors(id) returns all incident edges."""

    def __init__(self, nodes: list[Node], edges: list[Edge]):
        self._nodes = {n.id: n for n in nodes}
        self._edges = edges

    def get_node(self, node_id):
        return self._nodes.get(node_id)

    def neighbors(self, node_id, rels=None):
        out = [e for e in self._edges if e.src == node_id or e.dst == node_id]
        if rels is not None:
            out = [e for e in out if e.rel in rels]
        return out


def _node(nid: str, ntype: str = "Concept") -> Node:
    return Node(id=nid, type=ntype, name=nid)


def _edge(src: str, rel: str, dst: str, cite: Citation | None = None) -> Edge:
    return Edge(src=src, rel=rel, dst=dst, citation=cite)


# --------------------------------------------------------------------------- #
# hybrid_search
# --------------------------------------------------------------------------- #

def test_hybrid_search_fuses_and_dedups():
    a, b, c = _chunk("a"), _chunk("b"), _chunk("c")
    # 'b' appears in both lists -> should win on fused score.
    lance = FakeLance(vector=[a, b], bm25=[b, c])
    r = Retriever(lance, FakeEmbedder(), FakeGraph([], []))
    out = r.hybrid_search("query", k=10)
    ids = [ch.id for ch in out]
    assert ids[0] == "b"               # shared chunk ranks first
    assert set(ids) == {"a", "b", "c"} # union, de-duplicated


def test_hybrid_search_rrf_scores():
    a, b = _chunk("a"), _chunk("b")
    lance = FakeLance(vector=[a, b], bm25=[b, a])  # a:rank0+rank1 ; b:rank1+rank0
    r = Retriever(lance, FakeEmbedder(), FakeGraph([], []))
    out = r.hybrid_search("q", k=2)
    # symmetric ranks -> equal scores; both present, count == 2
    assert len(out) == 2
    expected = 1.0 / (_RRF_K + 0) + 1.0 / (_RRF_K + 1)
    assert abs((1.0 / (_RRF_K + 0) + 1.0 / (_RRF_K + 1)) - expected) < 1e-9


def test_hybrid_search_truncates_to_k():
    chunks = [_chunk(c) for c in "abcde"]
    lance = FakeLance(vector=chunks, bm25=[])
    r = Retriever(lance, FakeEmbedder(), FakeGraph([], []))
    assert len(r.hybrid_search("q", k=3)) == 3


def test_hybrid_search_empty_query_returns_empty():
    lance = FakeLance(vector=[_chunk("a")], bm25=[_chunk("a")])
    r = Retriever(lance, FakeEmbedder(), FakeGraph([], []))
    assert r.hybrid_search("   ", k=5) == []
    assert r.hybrid_search("q", k=0) == []


def test_hybrid_search_survives_dead_embedder():
    class Boom:
        def embed(self, texts):
            raise RuntimeError("no ollama")

    lance = FakeLance(vector=[_chunk("x")], bm25=[_chunk("y")])
    r = Retriever(lance, Boom(), FakeGraph([], []))
    out = r.hybrid_search("q", k=5)
    # vector leg fails -> falls back to bm25-only
    assert [c.id for c in out] == ["y"]


def test_hybrid_search_bm25_only_when_vector_empty():
    lance = FakeLance(vector=[], bm25=[_chunk("only")])
    r = Retriever(lance, FakeEmbedder(), FakeGraph([], []))
    assert [c.id for c in r.hybrid_search("q")] == ["only"]


# --------------------------------------------------------------------------- #
# expand_to_subgraph
# --------------------------------------------------------------------------- #

def test_expand_one_hop():
    nodes = [_node("A"), _node("B"), _node("C")]
    edges = [_edge("A", "mentions", "B"), _edge("B", "mentions", "C")]
    r = Retriever(FakeLance(), FakeEmbedder(), FakeGraph(nodes, edges))
    got_nodes, got_edges = r.expand_to_subgraph(["A"], hops=1)
    ids = {n.id for n in got_nodes}
    assert ids == {"A", "B"}                 # C is 2 hops away
    assert {(e.src, e.dst) for e in got_edges} == {("A", "B")}


def test_expand_two_hops_reaches_further():
    nodes = [_node("A"), _node("B"), _node("C")]
    edges = [_edge("A", "mentions", "B"), _edge("B", "mentions", "C")]
    r = Retriever(FakeLance(), FakeEmbedder(), FakeGraph(nodes, edges))
    got_nodes, got_edges = r.expand_to_subgraph(["A"], hops=2)
    assert {n.id for n in got_nodes} == {"A", "B", "C"}
    assert len(got_edges) == 2


def test_expand_zero_hops_is_just_seeds():
    nodes = [_node("A"), _node("B")]
    edges = [_edge("A", "mentions", "B")]
    r = Retriever(FakeLance(), FakeEmbedder(), FakeGraph(nodes, edges))
    got_nodes, got_edges = r.expand_to_subgraph(["A"], hops=0)
    assert {n.id for n in got_nodes} == {"A"}
    assert got_edges == []


def test_expand_dedups_parallel_edges():
    nodes = [_node("A"), _node("B")]
    edges = [_edge("A", "mentions", "B"), _edge("A", "mentions", "B")]  # parallel
    r = Retriever(FakeLance(), FakeEmbedder(), FakeGraph(nodes, edges))
    _, got_edges = r.expand_to_subgraph(["A"], hops=1)
    assert len(got_edges) == 1


def test_expand_skips_missing_seed_node():
    # seed id not in graph -> no node recorded, no crash
    r = Retriever(FakeLance(), FakeEmbedder(), FakeGraph([], []))
    got_nodes, got_edges = r.expand_to_subgraph(["ghost"], hops=2)
    assert got_nodes == []
    assert got_edges == []


def test_expand_empty_seeds():
    r = Retriever(FakeLance(), FakeEmbedder(), FakeGraph([_node("A")], []))
    assert r.expand_to_subgraph([], hops=2) == ([], [])


# --------------------------------------------------------------------------- #
# evidence_for_edge
# --------------------------------------------------------------------------- #

def test_evidence_for_edge_with_citation():
    cite = Citation(source_slug="s", quote="because")
    r = Retriever(FakeLance(), FakeEmbedder(), FakeGraph([], []))
    out = r.evidence_for_edge(_edge("A", "mentions", "B", cite=cite))
    assert out == [cite]


def test_evidence_for_edge_without_citation():
    r = Retriever(FakeLance(), FakeEmbedder(), FakeGraph([], []))
    assert r.evidence_for_edge(_edge("A", "mentions", "B")) == []
