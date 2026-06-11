"""Tests for the graph spine.

The load-bearing test (`test_undirected_bridge_path`) proves the whole reason
``paths`` traverses undirected: the canonical applicability shape

    source:paper  --applies-idea-->  idea:top-down-optimization  <--applies-idea--  grant:foo

has NO directed walk from paper to grant (the idea is a sink reached from both
sides), yet IS connected as a 2-hop undirected bridge. A naive directed
shortest-path would report "not connected" and the engine would miss the link.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import networkx as nx
import pytest

from befkb.config import Settings
from befkb.graphstore import NetworkXGraphStore
from befkb.models import Citation, Edge, Node


def _store(tmp: Path) -> NetworkXGraphStore:
    s = Settings()
    s.data_dir = tmp
    s.ensure_dirs()
    return NetworkXGraphStore(s)


def _bridge_nodes() -> list[Node]:
    return [
        Node(id="source:paper", type="Source", name="A Paper"),
        Node(id="idea:top-down-optimization", type="Idea", name="Top-down optimization"),
        Node(id="grant:foo", type="Grant", name="Foo Grant", props={"internal": True}),
    ]


def _bridge_edges() -> list[Edge]:
    # Both edges point *into* the idea node — classic sink, no directed paper->grant walk.
    return [
        Edge(src="source:paper", rel="applies-idea", dst="idea:top-down-optimization",
             citation=Citation(source_slug="paper", quote="we optimize globally")),
        Edge(src="grant:foo", rel="applies-idea", dst="idea:top-down-optimization",
             citation=Citation(source_slug="grant", quote="optimizes reserve placement")),
    ]


def test_undirected_bridge_path():
    with tempfile.TemporaryDirectory() as td:
        g = _store(Path(td))
        g.upsert_nodes(_bridge_nodes())
        g.upsert_edges(_bridge_edges())

        # Directed has NO path (the raw MultiDiGraph): prove the trap is real.
        with pytest.raises(nx.NetworkXNoPath):
            nx.shortest_path(g.g, "source:paper", "grant:foo")

        # Undirected traversal DOES find the 2-hop bridge through the idea.
        paths = g.paths("source:paper", "grant:foo", max_hops=3, undirected=True)
        assert paths, "expected an undirected bridge path through the shared idea"
        shortest = paths[0]
        assert len(shortest) == 2, "the bridge is exactly two edges"
        rels = [e.rel for e in shortest]
        assert rels == ["applies-idea", "applies-idea"]
        # every fact carries evidence
        assert all(e.citation is not None for e in shortest)

        # And with undirected=False the directed traversal yields nothing.
        assert g.paths("source:paper", "grant:foo", undirected=False) == []


def test_upsert_node_merges_aliases_and_provenance():
    with tempfile.TemporaryDirectory() as td:
        g = _store(Path(td))
        g.upsert_nodes([
            Node(id="technology:captain", type="Technology", name="CAPTAIN",
                 aliases=["captain"],
                 provenance=[Citation(source_slug="a")]),
        ])
        g.upsert_nodes([
            Node(id="technology:captain", type="Technology", name="CAPTAIN",
                 aliases=["CAPTAIN system"],
                 provenance=[Citation(source_slug="b")],
                 props={"trl": 4}),
        ])
        node = g.get_node("technology:captain")
        assert node is not None
        assert set(node.aliases) >= {"captain", "CAPTAIN system"}
        assert node.name not in node.aliases  # canonical name not duplicated as alias
        assert {c.source_slug for c in node.provenance} == {"a", "b"}
        assert node.props.get("trl") == 4


def test_empty_name_node_dropped():
    with tempfile.TemporaryDirectory() as td:
        g = _store(Path(td))
        g.upsert_nodes([Node(id="concept:blank", type="Concept", name="   ")])
        assert g.get_node("concept:blank") is None


def test_neighbors_filter_by_rel():
    with tempfile.TemporaryDirectory() as td:
        g = _store(Path(td))
        g.upsert_nodes([
            Node(id="source:p", type="Source", name="P"),
            Node(id="person:x", type="Person", name="X"),
            Node(id="idea:i", type="Idea", name="I"),
        ])
        g.upsert_edges([
            Edge(src="source:p", rel="authored-by", dst="person:x"),
            Edge(src="source:p", rel="applies-idea", dst="idea:i"),
        ])
        all_n = g.neighbors("source:p")
        assert len(all_n) == 2
        only_ideas = g.neighbors("source:p", rels=["applies-idea"])
        assert [e.rel for e in only_ideas] == ["applies-idea"]


def test_save_load_roundtrip():
    with tempfile.TemporaryDirectory() as td:
        g = _store(Path(td))
        g.upsert_nodes(_bridge_nodes())
        g.upsert_edges(_bridge_edges())
        g.save()

        g2 = _store(Path(td))
        g2.load()
        assert g2.get_node("idea:top-down-optimization") is not None
        paths = g2.paths("source:paper", "grant:foo")
        assert paths and len(paths[0]) == 2


def test_alias_resolution_follows_merge():
    with tempfile.TemporaryDirectory() as td:
        g = _store(Path(td))
        g.upsert_nodes([Node(id="technology:captain", type="Technology", name="CAPTAIN")])
        # an alias id was merged into the canonical id by resolve.py
        g.set_alias("technology:captain-rl", "technology:captain")
        assert g.resolve_alias("technology:captain-rl") == "technology:captain"
        # get_node on the alias returns the canonical node
        node = g.get_node("technology:captain-rl")
        assert node is not None and node.id == "technology:captain"


def test_hub_penalty_orders_paths():
    with tempfile.TemporaryDirectory() as td:
        s = Settings()
        s.data_dir = Path(td)
        s.hub_degree_threshold = 3
        s.ensure_dirs()
        g = NetworkXGraphStore(s)

        # src and dst, plus two bridges: one clean idea, one mega-hub.
        g.upsert_nodes([
            Node(id="source:a", type="Source", name="A"),
            Node(id="grant:b", type="Grant", name="B"),
            Node(id="idea:clean", type="Idea", name="Clean"),
            Node(id="concept:hub", type="Concept", name="Hub"),
        ])
        edges = [
            Edge(src="source:a", rel="applies-idea", dst="idea:clean"),
            Edge(src="grant:b", rel="applies-idea", dst="idea:clean"),
            Edge(src="source:a", rel="mentions", dst="concept:hub"),
            Edge(src="grant:b", rel="mentions", dst="concept:hub"),
        ]
        # inflate the hub's degree well past the threshold
        for i in range(10):
            g.upsert_nodes([Node(id=f"source:x{i}", type="Source", name=f"X{i}")])
            edges.append(Edge(src=f"source:x{i}", rel="mentions", dst="concept:hub"))
        g.upsert_edges(edges)

        paths = g.paths("source:a", "grant:b", max_hops=3, hub_penalty=True)
        assert len(paths) >= 2
        # both are 2-hop, so hub cost breaks the tie: the clean idea path sorts first
        mids = [{e.src for e in p} | {e.dst for e in p} for p in paths]
        assert "idea:clean" in mids[0]
        assert "concept:hub" in mids[-1]
