"""Tests for the orchestration layer (`befkb.pipeline`).

These exercise the *pure* parts of the pipeline — module importability and the
canonical-id remap + log-append helpers — so they pass before the heavy sibling
modules (parser/extract/resolve/...) land. The end-to-end ingest/apply paths are
covered by integration tests once siblings exist.
"""

from __future__ import annotations

import importlib
import tempfile
from pathlib import Path

from befkb import pipeline
from befkb.config import Settings
from befkb.models import Edge, Node, ResolutionResult


def test_pipeline_imports_without_sibling_modules() -> None:
    # Importing pipeline must never require chunk/extract/resolve/... to exist.
    importlib.reload(pipeline)
    assert callable(pipeline.ingest)
    assert callable(pipeline.apply)


def test_merge_map_only_includes_merged() -> None:
    res = ResolutionResult(
        merged=[("technology:captain-rl", "technology:captain")],
        created=[Node(id="method:rl", type="Method", name="Reinforcement Learning")],
        needs_review=[("idea:a", "idea:b", 0.81)],
    )
    m = pipeline._merge_map(res)
    assert m == {"technology:captain-rl": "technology:captain"}


def test_remap_nodes_drops_merged_away_and_dedupes() -> None:
    merge = {"technology:captain-rl": "technology:captain"}
    nodes = [
        Node(id="technology:captain-rl", type="Technology", name="CAPTAIN-RL"),  # merged away
        Node(id="method:rl", type="Method", name="Reinforcement Learning"),       # survives
        Node(id="method:rl", type="Method", name="Reinforcement Learning"),       # dup -> dropped
    ]
    out = pipeline._remap_nodes(nodes, merge)
    ids = [n.id for n in out]
    assert ids == ["method:rl"]


def test_remap_edges_rewrites_endpoints_drops_selfloops_and_dupes() -> None:
    merge = {
        "technology:captain-rl": "technology:captain",
        "method:rl-dup": "method:rl",
    }
    edges = [
        # endpoint rewritten through the merge map
        Edge(src="source:paper", rel="uses-technology", dst="technology:captain-rl"),
        # both endpoints collapse onto the same canonical id -> self-loop, dropped
        Edge(src="method:rl", rel="advances-over", dst="method:rl-dup"),
        # duplicate of the first after remap -> deduped
        Edge(src="source:paper", rel="uses-technology", dst="technology:captain"),
    ]
    out = pipeline._remap_edges(edges, merge)
    assert len(out) == 1
    e = out[0]
    assert (e.src, e.rel, e.dst) == ("source:paper", "uses-technology", "technology:captain")


def test_append_log_writes_greppable_entry() -> None:
    with tempfile.TemporaryDirectory() as td:
        s = Settings()
        s.wiki_root = Path(td)
        s.wiki_dir = Path(td) / "wiki"
        pipeline._append_log(s, "[2026-06-10] ingest | Test Source  →  nodes:3")
        log = (Path(td) / "wiki" / "log.md").read_text(encoding="utf-8")
        assert "## [2026-06-10] ingest | Test Source" in log
        # greppable: line starts with the canonical prefix
        assert any(ln.startswith("## [") for ln in log.splitlines())


def test_append_log_never_raises_on_bad_path() -> None:
    s = Settings()
    # point wiki_dir at something that can't be created under a file path
    s.wiki_dir = Path("/dev/null/cannot/create/here/wiki")
    # must swallow the error, not propagate
    pipeline._append_log(s, "[2026-06-10] ingest | x  →  y")
