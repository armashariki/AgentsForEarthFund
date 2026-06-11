"""Tests for the Layer-2 killer query (applicability.py).

We exercise the *structural* logic — path discovery, ranking, kind classification,
evidence collection, the no-grants fallback, and file_back — against a real
NetworkXGraphStore. The sibling LLM/extract/resolve/claims modules are faked so the
test is hermetic (no Ollama, no network, no PDF parsing).
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

import numpy as np
import pytest

from befkb import applicability as A
from befkb.config import Settings
from befkb.graphstore import NetworkXGraphStore
from befkb.models import (
    Citation,
    Claim,
    Connection,
    Doc,
    Edge,
    Node,
)


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #

class FakeEmbedder:
    """Deterministic 4-dim embeddings keyed by a substring hash — stable across calls."""

    def embed(self, texts):
        rng_vecs = []
        for t in texts:
            h = abs(hash(t.lower())) % 9973
            v = np.array([(h % 7) + 1, (h % 5) + 1, (h % 3) + 1, (h % 11) + 1], dtype=np.float32)
            rng_vecs.append(v / np.linalg.norm(v))
        return np.vstack(rng_vecs) if rng_vecs else np.zeros((0, 4), dtype=np.float32)


class FakeRetriever:
    """evidence_for_edge returns a citation derived from the edge's own citation."""

    def evidence_for_edge(self, edge: Edge):
        if edge.citation is not None:
            return [Citation(source_slug=edge.citation.source_slug, quote="retriever-evidence")]
        return []


class FakeLLM:
    """Returns a narration that fills `why` for every given path index."""

    def complete(self, prompt, *, schema=None, system=None):
        if schema is A._Narration:
            # narrate however many paths the prompt mentions ([0], [1], ...)
            import re

            idxs = sorted({int(m) for m in re.findall(r"\[(\d+)\] grant", prompt)})
            return A._Narration(
                summary="Narrated summary from the model.",
                connections=[
                    A._ConnectionNarration(path_index=i, why=f"why-for-{i}") for i in idxs
                ],
            )
        return "ok"


@pytest.fixture
def settings(tmp_path) -> Settings:
    s = Settings()
    s.data_dir = tmp_path / "data"
    s.wiki_dir = tmp_path / "wiki"
    s.hub_degree_threshold = 8
    s.ensure_dirs()
    return s


def _seed_graph(settings: Settings) -> NetworkXGraphStore:
    """Build a small graph: a paper, an idea bridge, a grant, an org, a tradeoff edge."""
    g = NetworkXGraphStore(settings)
    nodes = [
        Node(id="source:new-paper", type="Source", name="New Paper"),
        Node(id="idea:top-down-optimization", type="Idea", name="Top-down optimization"),
        Node(id="grant:rewild-amazon", type="Grant", name="Rewild Amazon", props={"internal": True}),
        Node(id="technology:captain", type="Technology", name="CAPTAIN"),
        Node(id="grant:captain-deploy", type="Grant", name="CAPTAIN Deployment", props={"internal": True}),
        Node(id="organization:ubc", type="Organization", name="UBC"),
        Node(id="concept:30x30", type="Concept", name="30x30"),
        Node(id="grant:tradeoff-grant", type="Grant", name="Tradeoff Grant", props={"internal": True}),
    ]
    g.upsert_nodes(nodes)
    edges = [
        # shared-idea path: new-paper -applies-idea-> idea <-applies-idea- grant
        Edge(src="source:new-paper", rel="applies-idea", dst="idea:top-down-optimization",
             citation=Citation(source_slug="new-paper", quote="we optimize top-down"), confidence=0.8),
        Edge(src="grant:rewild-amazon", rel="applies-idea", dst="idea:top-down-optimization",
             citation=Citation(source_slug="rewild", quote="grant uses top-down"), confidence=0.7),
        # capability path: new-paper -uses-technology-> captain <-uses-technology- grant
        Edge(src="source:new-paper", rel="uses-technology", dst="technology:captain",
             citation=Citation(source_slug="new-paper", quote="we use CAPTAIN"), confidence=0.9),
        Edge(src="grant:captain-deploy", rel="uses-technology", dst="technology:captain",
             citation=Citation(source_slug="deploy", quote="deploys CAPTAIN"), confidence=0.85),
        # tradeoff path: new-paper -has-tradeoff-with-> concept:30x30 <-addresses-domain- grant
        Edge(src="source:new-paper", rel="has-tradeoff-with", dst="concept:30x30",
             citation=Citation(source_slug="new-paper", quote="tension with 30x30"), confidence=0.6),
        Edge(src="grant:tradeoff-grant", rel="addresses-domain", dst="concept:30x30",
             citation=Citation(source_slug="tg", quote="targets 30x30"), confidence=0.6),
    ]
    g.upsert_edges(edges)
    return g


# --------------------------------------------------------------------------- #
# Pure-function unit tests
# --------------------------------------------------------------------------- #

def test_classify_kind_shared_idea(settings):
    g = _seed_graph(settings)
    paths = g.paths("source:new-paper", "grant:rewild-amazon", max_hops=3)
    assert paths, "expected an idea-bridge path"
    kind = A._classify_kind(g, paths[0], "source:new-paper", "grant:rewild-amazon")
    assert kind == "shared-idea"


def test_classify_kind_capability_transfer(settings):
    g = _seed_graph(settings)
    paths = g.paths("source:new-paper", "grant:captain-deploy", max_hops=3)
    assert paths
    kind = A._classify_kind(g, paths[0], "source:new-paper", "grant:captain-deploy")
    assert kind == "capability-transfer"


def test_classify_kind_tradeoff(settings):
    g = _seed_graph(settings)
    paths = g.paths("source:new-paper", "grant:tradeoff-grant", max_hops=3)
    assert paths
    kind = A._classify_kind(g, paths[0], "source:new-paper", "grant:tradeoff-grant")
    assert kind == "tradeoff"


def test_path_node_ids_undirected(settings):
    g = _seed_graph(settings)
    paths = g.paths("source:new-paper", "grant:rewild-amazon", max_hops=3)
    ids = A._path_node_ids(paths[0])
    assert ids[0] == "source:new-paper"
    assert ids[-1] == "grant:rewild-amazon"
    assert "idea:top-down-optimization" in ids


def test_collect_evidence_dedups(settings):
    g = _seed_graph(settings)
    paths = g.paths("source:new-paper", "grant:captain-deploy", max_hops=3)
    cites = A._collect_evidence(FakeRetriever(), paths[0])
    assert cites, "expected per-hop evidence"
    # all citations have a source slug; no exact duplicates
    keys = [(c.source_slug, c.quote) for c in cites]
    assert len(keys) == len(set(keys))


def test_build_connections_ranks_and_classifies(settings):
    g = _seed_graph(settings)
    grants = g.nodes_by_type("Grant")
    conns = A._build_connections(
        g, FakeRetriever(), FakeEmbedder(), settings,
        anchor_ids=["source:new-paper"], grants=grants, max_hops=3,
    )
    assert conns
    # one connection per reachable grant
    grant_ids = {c.grant_id for c in conns}
    assert {"grant:rewild-amazon", "grant:captain-deploy", "grant:tradeoff-grant"} <= grant_ids
    # sorted strongest-first
    strengths = [c.strength for c in conns]
    assert strengths == sorted(strengths, reverse=True)
    # kinds were classified
    kinds = {c.grant_id: c.kind for c in conns}
    assert kinds["grant:rewild-amazon"] == "shared-idea"
    assert kinds["grant:captain-deploy"] == "capability-transfer"
    assert kinds["grant:tradeoff-grant"] == "tradeoff"


def test_overlay_shaky_claims_on_path(settings):
    g = _seed_graph(settings)
    grants = g.nodes_by_type("Grant")
    conns = A._build_connections(
        g, FakeRetriever(), FakeEmbedder(), settings,
        anchor_ids=["source:new-paper"], grants=grants, max_hops=3,
    )
    flagged = [
        Claim(id="c1", text="on path", source_slug="new-paper", status="vague"),
        Claim(id="c2", text="off path", source_slug="unrelated-doc", status="vague"),
        Claim(id="c3", text="contradiction", source_slug="anything", status="contradicts-KB"),
    ]
    kept = A._overlay_shaky_claims(conns, flagged)
    texts = {c.text for c in kept}
    assert "on path" in texts          # source on a path
    assert "contradiction" in texts    # always surfaced
    assert "off path" not in texts     # dropped


# --------------------------------------------------------------------------- #
# End-to-end (with faked siblings)
# --------------------------------------------------------------------------- #

def _install_fake_siblings(monkeypatch, new_nodes, claims_list, anchor_map):
    """Install fake befkb.extract / resolve / claims / ingest.parser modules.

    A submodule must be swapped in *both* ``sys.modules`` (so a fresh
    ``import befkb.X`` finds the fake) and as an attribute on the already-imported
    ``befkb`` package object (so ``from . import X`` — which reads the package
    attribute when the real submodule has already been imported elsewhere in the
    test session — also finds the fake). Patching only ``sys.modules`` silently
    binds the real module once any other test imports it, so we do both.
    """
    import befkb as _befkb  # the live package object whose attributes `from . import` reads
    doc = Doc(source_slug="new-paper", path="/tmp/new.pdf", title="New Paper", markdown="body")

    # ingest.parser
    parser_mod = types.ModuleType("befkb.ingest.parser")
    ingest_pkg = types.ModuleType("befkb.ingest")

    class _P:
        def parse(self, path):
            return doc

    parser_mod.get_parser = lambda path, prefer=None: _P()  # type: ignore
    ingest_pkg.parser = parser_mod  # type: ignore
    monkeypatch.setitem(sys.modules, "befkb.ingest", ingest_pkg)
    monkeypatch.setitem(sys.modules, "befkb.ingest.parser", parser_mod)
    monkeypatch.setattr(_befkb, "ingest", ingest_pkg, raising=False)

    # extract
    extract_mod = types.ModuleType("befkb.extract")
    extract_mod.extract_graph = lambda d, c, llm, s: (new_nodes, [])  # type: ignore
    monkeypatch.setitem(sys.modules, "befkb.extract", extract_mod)
    monkeypatch.setattr(_befkb, "extract", extract_mod, raising=False)

    # resolve
    resolve_mod = types.ModuleType("befkb.resolve")
    resolve_mod.anchor = lambda nodes, graph, emb, s: anchor_map  # type: ignore
    monkeypatch.setitem(sys.modules, "befkb.resolve", resolve_mod)
    monkeypatch.setattr(_befkb, "resolve", resolve_mod, raising=False)

    # claims
    claims_mod = types.ModuleType("befkb.claims")
    claims_mod.extract_claims = lambda d, llm: claims_list  # type: ignore
    claims_mod.flag_shaky = lambda cl, d, r, g, llm, s: cl  # type: ignore
    monkeypatch.setitem(sys.modules, "befkb.claims", claims_mod)
    monkeypatch.setattr(_befkb, "claims", claims_mod, raising=False)
    return doc


def test_how_does_this_apply_end_to_end(settings, monkeypatch):
    g = _seed_graph(settings)
    new_nodes = [
        Node(id="source:new-paper", type="Source", name="New Paper"),
        Node(id="technology:captain", type="Technology", name="CAPTAIN"),
    ]
    # anchor: new doc's "source:new-paper" resolves onto the graph's same id
    anchor_map = {
        "source:new-paper": "source:new-paper",
        "technology:captain": "technology:captain",
    }
    claims_list = [Claim(id="c1", text="shaky claim", source_slug="new-paper", status="vague")]
    _install_fake_siblings(monkeypatch, new_nodes, claims_list, anchor_map)

    result = A.how_does_this_apply(
        Path("/tmp/new.pdf"), FakeLLM(), g, FakeRetriever(), FakeEmbedder(), settings, max_hops=3
    )
    assert result.new_doc == "New Paper"
    assert result.connections, "should connect to grants"
    # narration prose got written onto the connections
    assert all(c.why for c in result.connections)
    assert result.summary
    # shaky claim on a path is surfaced
    assert any(cl.text == "shaky claim" for cl in result.flagged_claims)

    # file_back writes a real analysis page
    out = A.file_back(result, settings.wiki_dir, graph=g)
    assert out.exists()
    text = out.read_text()
    assert text.startswith("---")
    assert "type: analysis" in text
    assert "## Connections" in text


def test_no_grants_fallback(settings, monkeypatch):
    """A graph with no Grant nodes still returns most-related Source/Method nodes."""
    g = NetworkXGraphStore(settings)
    g.upsert_nodes([
        Node(id="source:new-paper", type="Source", name="New Paper"),
        Node(id="method:reinforcement-learning", type="Method", name="Reinforcement Learning"),
        Node(id="source:related", type="Source", name="Related Work"),
    ])
    new_nodes = [Node(id="source:new-paper", type="Source", name="New Paper")]
    anchor_map = {"source:new-paper": "source:new-paper"}
    _install_fake_siblings(monkeypatch, new_nodes, [], anchor_map)

    result = A.how_does_this_apply(
        Path("/tmp/new.pdf"), FakeLLM(), g, FakeRetriever(), FakeEmbedder(), settings
    )
    assert "No internal Grant nodes" in result.summary
    # returns related Source/Method nodes (not grants)
    assert result.connections
    assert all(c.grant_id.startswith(("source:", "method:")) for c in result.connections)


def test_novel_to_kb_detected(settings, monkeypatch):
    g = _seed_graph(settings)
    new_nodes = [
        Node(id="source:new-paper", type="Source", name="New Paper"),
        Node(id="technology:brand-new-tool", type="Technology", name="Brand New Tool"),
    ]
    # brand-new-tool has no canonical match and isn't in the graph -> novel
    anchor_map = {"source:new-paper": "source:new-paper"}
    _install_fake_siblings(monkeypatch, new_nodes, [], anchor_map)

    result = A.how_does_this_apply(
        Path("/tmp/new.pdf"), FakeLLM(), g, FakeRetriever(), FakeEmbedder(), settings
    )
    assert "Brand New Tool" in result.novel_to_kb
