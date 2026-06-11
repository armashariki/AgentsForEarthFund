"""Tests for entity resolution (resolve.py).

Two canonical behaviours the spec calls out:
  * ``'GPT-4'`` and ``'GPT 4'`` resolve to the same node (a lexical merge — the
    surface forms differ only by punctuation, so ``token_set_ratio`` is perfect).
  * ``'reinforcement learning'`` *anchors* to a pre-existing node of the same
    name (read-only, used by the applicability path).

A deterministic offline embedder is used so the suite never touches Ollama. It
returns a *stable* unit vector per normalised name, so an identical name on both
sides yields cosine 1.0 (exercising the semantic channel) while distinct names are
near-orthogonal (so they rely on the lexical channel — exactly the real-world mix).
"""

from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path

import numpy as np

from befkb.config import Settings
from befkb.graphstore import NetworkXGraphStore
from befkb.models import Citation, Node
from befkb.resolve import anchor, resolve, score_pair


# --------------------------------------------------------------------------- #
# Fixtures / helpers
# --------------------------------------------------------------------------- #

def _norm(text: str) -> str:
    text = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


class FakeEmbedder:
    """Hash-seeded unit vectors, keyed on the *normalised* name.

    Equal normalised names -> identical vector -> cosine 1.0; different names ->
    independent random unit vectors -> ~orthogonal. This lets the embedding channel
    fire on true semantic identity in tests without a model server.
    """

    def __init__(self, dim: int = 768):
        self.dim = dim

    def _vec(self, text: str) -> np.ndarray:
        seed = int(hashlib.sha1(_norm(text).encode("utf-8")).hexdigest()[:8], 16)
        rng = np.random.default_rng(seed)
        v = rng.standard_normal(self.dim).astype(np.float32)
        n = np.linalg.norm(v)
        return v / n if n else v

    def embed(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return np.vstack([self._vec(t) for t in texts])


def _store(tmp: Path) -> NetworkXGraphStore:
    s = Settings()
    s.data_dir = tmp
    s.ensure_dirs()
    return NetworkXGraphStore(s)


def _settings(tmp: Path) -> Settings:
    s = Settings()
    s.data_dir = tmp
    s.ensure_dirs()
    return s


# --------------------------------------------------------------------------- #
# Scoring unit
# --------------------------------------------------------------------------- #

def test_score_pair_lexical_handles_punctuation():
    a = Node(id="technology:gpt-4", type="Technology", name="GPT-4")
    b = Node(id="technology:gpt-4-x", type="Technology", name="GPT 4")
    # punctuation-only difference -> token_set_ratio is perfect, no embedder needed
    assert score_pair(a, b) >= 0.92


def test_score_pair_uses_max_of_channels():
    emb = FakeEmbedder()
    a = Node(id="method:rl", type="Method", name="reinforcement learning")
    b = Node(id="method:rl2", type="Method", name="reinforcement learning")
    vecs = emb.embed([a.name, b.name])
    s = score_pair(a, b, vecs[0], vecs[1])
    assert s >= 0.99  # identical name -> both channels max out


# --------------------------------------------------------------------------- #
# resolve(): the GPT-4 / GPT 4 merge
# --------------------------------------------------------------------------- #

def test_gpt4_variants_merge():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        g = _store(tmp)
        s = _settings(tmp)
        emb = FakeEmbedder()

        # seed the canonical node
        g.upsert_nodes([
            Node(id="technology:gpt-4", type="Technology", name="GPT-4",
                 provenance=[Citation(source_slug="seed")]),
        ])

        # a new extraction surfaces the same model as "GPT 4"
        new = Node(id="technology:gpt-4-1", type="Technology", name="GPT 4",
                   provenance=[Citation(source_slug="new-paper", quote="we ran GPT 4")])
        res = resolve([new], g, emb, s, write=True)

        assert ("technology:gpt-4-1", "technology:gpt-4") in res.merged
        assert not res.created, "merged node must not be created as a new node"

        # the new surface form is now an alias on the canonical node ...
        canonical = g.get_node("technology:gpt-4")
        assert canonical is not None
        assert "GPT 4" in canonical.aliases
        # ... its provenance was folded in ...
        assert {c.source_slug for c in canonical.provenance} == {"seed", "new-paper"}
        # ... and the old id now resolves (via the alias table) to the canonical id.
        assert g.resolve_alias("technology:gpt-4-1") == "technology:gpt-4"
        assert g.get_node("technology:gpt-4-1").id == "technology:gpt-4"


def test_below_review_min_creates_new_node():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        g = _store(tmp)
        s = _settings(tmp)
        emb = FakeEmbedder()
        g.upsert_nodes([Node(id="method:rl", type="Method", name="reinforcement learning")])

        new = Node(id="organization:anthropic", type="Organization", name="Anthropic")
        res = resolve([new], g, emb, s, write=True)
        # nothing of the same type to match against -> brand new node
        assert [n.id for n in res.created] == ["organization:anthropic"]
        assert not res.merged
        assert g.get_node("organization:anthropic") is not None


def test_mid_confidence_goes_to_review_and_is_kept():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        g = _store(tmp)
        s = _settings(tmp)
        # tighten the band so a genuine partial overlap (tokens differ on BOTH
        # sides, so token_set_ratio is <1) lands in [review_min, auto).
        s.resolve_auto_merge = 0.97
        s.resolve_review_min = 0.55
        emb = FakeEmbedder()
        g.upsert_nodes([Node(id="concept:reef-restoration-monitoring", type="Concept",
                             name="Reef restoration monitoring")])

        new = Node(id="concept:coral-reef-monitoring", type="Concept",
                   name="Coral reef monitoring")
        res = resolve([new], g, emb, s, write=True)
        assert res.needs_review, "partial name overlap should queue for review"
        a_id, b_id, score = res.needs_review[0]
        assert a_id == "concept:coral-reef-monitoring"
        assert b_id == "concept:reef-restoration-monitoring"
        assert s.resolve_review_min <= score < s.resolve_auto_merge
        # still created (never silently dropped)
        assert any(n.id == "concept:coral-reef-monitoring" for n in res.created)


def test_write_false_does_not_mutate_graph():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        g = _store(tmp)
        s = _settings(tmp)
        emb = FakeEmbedder()
        g.upsert_nodes([Node(id="technology:gpt-4", type="Technology", name="GPT-4")])

        new = Node(id="technology:gpt-4-1", type="Technology", name="GPT 4")
        res = resolve([new], g, emb, s, write=False)
        # merge is *reported* ...
        assert ("technology:gpt-4-1", "technology:gpt-4") in res.merged
        # ... but the graph is untouched: no alias row, no folded alias.
        assert g.resolve_alias("technology:gpt-4-1") == "technology:gpt-4-1"
        assert "GPT 4" not in (g.get_node("technology:gpt-4").aliases or [])


def test_intra_batch_duplicates_collapse():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        g = _store(tmp)
        s = _settings(tmp)
        emb = FakeEmbedder()
        # two surface forms of the same NEW entity, nothing in the graph yet
        a = Node(id="technology:gpt-4-a", type="Technology", name="GPT-4")
        b = Node(id="technology:gpt-4-b", type="Technology", name="GPT 4")
        res = resolve([a, b], g, emb, s, write=True)
        # first is created, second merges into it
        assert len(res.created) == 1
        assert res.merged == [("technology:gpt-4-b", "technology:gpt-4-a")]


# --------------------------------------------------------------------------- #
# anchor(): read-only mapping for the applicability path
# --------------------------------------------------------------------------- #

def test_reinforcement_learning_anchors_to_existing_node():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        g = _store(tmp)
        s = _settings(tmp)
        emb = FakeEmbedder()
        # an existing canonical Method node
        g.upsert_nodes([Node(id="method:reinforcement-learning", type="Method",
                             name="reinforcement learning")])

        # a freshly-parsed doc mentions the same method under a fresh provisional id
        new = Node(id="method:rl-from-new-doc", type="Method", name="reinforcement learning")
        mapping = anchor([new], g, emb, s)
        assert mapping == {"method:rl-from-new-doc": "method:reinforcement-learning"}


def test_anchor_is_read_only():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        g = _store(tmp)
        s = _settings(tmp)
        emb = FakeEmbedder()
        g.upsert_nodes([Node(id="method:reinforcement-learning", type="Method",
                             name="reinforcement learning")])
        before = len(g.nodes_by_type("Method"))

        new = Node(id="method:rl-new", type="Method", name="reinforcement learning")
        anchor([new], g, emb, s)
        # no node minted, no alias written
        assert len(g.nodes_by_type("Method")) == before
        assert g.get_node("method:rl-new") is None
        assert g.resolve_alias("method:rl-new") == "method:rl-new"


def test_anchor_follows_alias_to_live_canonical():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        g = _store(tmp)
        s = _settings(tmp)
        emb = FakeEmbedder()
        g.upsert_nodes([Node(id="technology:captain", type="Technology", name="CAPTAIN")])
        # a prior merge pointed an old id at the canonical one
        g.set_alias("technology:captain-old", "technology:captain")

        new = Node(id="technology:captain-new", type="Technology", name="CAPTAIN")
        mapping = anchor([new], g, emb, s)
        # anchor returns the *live* canonical id, never a stale alias
        assert mapping["technology:captain-new"] == "technology:captain"


def test_anchor_no_match_absent_from_map():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        g = _store(tmp)
        s = _settings(tmp)
        emb = FakeEmbedder()
        g.upsert_nodes([Node(id="method:reinforcement-learning", type="Method",
                             name="reinforcement learning")])
        new = Node(id="organization:unrelated", type="Organization", name="Some Random Org")
        assert anchor([new], g, emb, s) == {}


def test_resolve_drops_nameless_nodes():
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        g = _store(tmp)
        s = _settings(tmp)
        emb = FakeEmbedder()
        res = resolve([Node(id="concept:blank", type="Concept", name="   ")], g, emb, s)
        assert not res.created and not res.merged and not res.needs_review


def test_resolve_works_without_embedder():
    # lexical channel alone must still merge punctuation variants
    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        g = _store(tmp)
        s = _settings(tmp)
        g.upsert_nodes([Node(id="technology:gpt-4", type="Technology", name="GPT-4")])
        new = Node(id="technology:gpt-4-1", type="Technology", name="GPT 4")
        res = resolve([new], g, None, s, write=True)
        assert ("technology:gpt-4-1", "technology:gpt-4") in res.merged
