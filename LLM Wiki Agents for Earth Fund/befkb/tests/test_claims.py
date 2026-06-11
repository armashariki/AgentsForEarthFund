"""Tests for CUSTOM LAYER 1 — claim extraction + shaky-claim flagging.

These use fakes (no Ollama, no sibling modules) so they're fast + deterministic
and run before retrieve.py / graphstore.py land. The fakes match the
cross-module contract signatures exactly:

  Retriever.hybrid_search(query, k) -> list[Chunk]    (+ optional .embedder)
  LLMClient.complete(prompt, schema=..., system=...) -> BaseModel | str

The point of the tests is the *flagging logic* and the *epistemic guardrail*:
Check B must NEVER set a hard 'contradicts-KB' status, only a review note.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import numpy as np

from befkb.claims import (
    _vagueness_reason,
    extract_claims,
    flag_shaky,
    write_review_queue,
)
from befkb.config import Settings
from befkb.models import Chunk, Claim, Doc, Section


# --------------------------------------------------------------------------- #
# Fakes
# --------------------------------------------------------------------------- #

class FakeLLM:
    """Scripted LLM: returns a model instance built by a per-schema callback."""

    def __init__(self, on_extract=None, on_support=None):
        self.on_extract = on_extract
        self.on_support = on_support

    def complete(self, prompt, *, schema=None, system=None):
        name = getattr(schema, "__name__", "")
        if name == "_ClaimList":
            return self.on_extract(prompt) if self.on_extract else schema(claims=[])
        if name == "_SupportVerdict":
            return self.on_support(prompt) if self.on_support else schema(verdict="supported")
        return schema() if schema else ""


class FakeRetriever:
    """Returns a fixed hit list; carries an optional .embedder like the real one."""

    def __init__(self, hits=None, embedder=None):
        self._hits = hits or []
        self.embedder = embedder

    def hybrid_search(self, query, k=10):
        return self._hits[:k]


class FakeEmbedder:
    def embed(self, texts):
        # deterministic non-zero vector so cosine is computable
        return np.array([[1.0, 0.0, 0.0] for _ in texts], dtype=np.float32)


def _doc(markdown: str, sections=None, slug="paper-x") -> Doc:
    if sections is None:
        sections = [Section(title="Methods", text=markdown, char_span=(0, len(markdown)))]
    return Doc(source_slug=slug, path="/raw/paper.pdf", title="Paper X",
               markdown=markdown, sections=sections)


# --------------------------------------------------------------------------- #
# extract_claims
# --------------------------------------------------------------------------- #

def test_extract_claims_basic_and_span_recovery():
    from befkb.claims import _ClaimList, _ExtractedClaim

    body = (
        "CAPTAIN is a reinforcement-learning system for conservation planning. "
        "It increased protected species coverage by 30% over the greedy baseline."
    )
    doc = _doc(body)

    def on_extract(_prompt):
        return _ClaimList(claims=[
            _ExtractedClaim(
                text="CAPTAIN is a reinforcement-learning system for conservation planning.",
                quote="CAPTAIN is a reinforcement-learning system for conservation planning.",
            ),
            _ExtractedClaim(text="x", quote=""),  # too short -> dropped
        ])

    claims = extract_claims(doc, FakeLLM(on_extract=on_extract))
    assert len(claims) == 1
    c = claims[0]
    assert c.source_slug == "paper-x"
    assert c.status == "supported"
    assert c.id.startswith("claim:paper-x:")
    # span recovered from the verbatim quote
    assert c.source_span is not None
    s, e = c.source_span
    assert doc.markdown[s:e].startswith("CAPTAIN is a reinforcement-learning")


def test_extract_skips_boilerplate_and_short_sections():
    doc = _doc(
        "ignored",
        sections=[
            Section(title="References", text="[1] Foo et al. 2020. " * 10, char_span=(0, 100)),
            Section(title="Intro", text="too short", char_span=(100, 109)),
        ],
    )
    called = {"n": 0}

    def on_extract(_p):
        from befkb.claims import _ClaimList
        called["n"] += 1
        return _ClaimList(claims=[])

    extract_claims(doc, FakeLLM(on_extract=on_extract))
    assert called["n"] == 0  # neither boilerplate nor short section was sent to the LLM


# --------------------------------------------------------------------------- #
# vagueness heuristic
# --------------------------------------------------------------------------- #

def test_vagueness_bare_superlative():
    assert _vagueness_reason("Our model is state-of-the-art.")
    # grounded superlative (has comparator) is NOT vague
    assert not _vagueness_reason("Our model is state-of-the-art compared to the greedy baseline.")


def test_vagueness_hedged_no_number():
    assert _vagueness_reason("The method may substantially improve outcomes.")
    # concrete number rescues a hedged sentence
    assert not _vagueness_reason("The method may improve outcomes by 12%.")


# --------------------------------------------------------------------------- #
# flag_shaky — Check A
# --------------------------------------------------------------------------- #

def test_check_a_unsupported_sets_status_and_evidence():
    from befkb.claims import _SupportVerdict

    doc = _doc("The source says nothing about quantum supremacy here at all, only conservation.")
    claim = Claim(id="claim:paper-x:1", text="The system achieves quantum supremacy.",
                  source_slug="paper-x", source_span=(0, 40))

    def on_support(_p):
        return _SupportVerdict(verdict="unsupported-by-source",
                               rationale="source never mentions quantum supremacy",
                               quote="only conservation")

    flagged = flag_shaky([claim], doc, FakeRetriever(), graph=None,
                         llm=FakeLLM(on_support=on_support), settings=Settings())
    assert len(flagged) == 1
    assert claim.status == "unsupported-by-source"
    assert "Source-check" in claim.rationale
    assert any(c.quote == "only conservation" for c in claim.evidence)


def test_check_a_overstated_maps_to_vague():
    from befkb.claims import _SupportVerdict

    doc = _doc("The results suggest a modest correlation between coverage and budget.")
    claim = Claim(id="claim:paper-x:2", text="The results prove coverage causes budget gains.",
                  source_slug="paper-x", source_span=(0, 60))

    def on_support(_p):
        return _SupportVerdict(verdict="overstated", rationale="source says 'suggest', claim says 'prove'")

    flag_shaky([claim], doc, FakeRetriever(), None, FakeLLM(on_support=on_support), Settings())
    assert claim.status == "vague"
    assert "Overstated" in claim.rationale


def test_supported_claim_not_flagged():
    from befkb.claims import _SupportVerdict

    doc = _doc("CAPTAIN increased coverage by 30 percent over the greedy baseline in the study.")
    claim = Claim(id="claim:paper-x:3",
                  text="CAPTAIN increased coverage by 30% over the greedy baseline.",
                  source_slug="paper-x", source_span=(0, 70))

    def on_support(_p):
        return _SupportVerdict(verdict="supported", rationale="stated verbatim")

    flagged = flag_shaky([claim], doc, FakeRetriever(), None,
                         FakeLLM(on_support=on_support), Settings())
    assert flagged == []
    assert claim.status == "supported"


# --------------------------------------------------------------------------- #
# flag_shaky — Check B (the guardrail)
# --------------------------------------------------------------------------- #

def test_check_b_high_sim_neighbour_adds_note_but_no_hard_verdict():
    from befkb.claims import _SupportVerdict

    doc = _doc("This source asserts coverage rose by 30% under CAPTAIN.")
    claim = Claim(id="claim:paper-x:4",
                  text="CAPTAIN raised coverage by 30%.",
                  source_slug="paper-x", source_span=(0, 50))

    # A KB chunk from a DIFFERENT source with an explicit high similarity.
    neighbour = Chunk(id="ch1", source_slug="other-paper", section="Results",
                      text="An independent study found CAPTAIN did NOT raise coverage.",
                      char_span=(0, 60))
    neighbour.__dict__["similarity"] = 0.95  # retriever-attached cosine

    def on_support(_p):
        return _SupportVerdict(verdict="supported")  # Check A passes; Check B still notes

    flagged = flag_shaky([claim], doc, FakeRetriever(hits=[neighbour]), None,
                         FakeLLM(on_support=on_support), Settings())
    assert len(flagged) == 1
    # GUARDRAIL: status must NOT be flipped to contradicts-KB by a 7B/similarity signal.
    assert claim.status != "contradicts-KB"
    assert claim.status == "supported"
    assert "Possible contradiction" in claim.rationale
    assert "HUMAN REVIEW" in claim.rationale
    assert any(c.source_slug == "other-paper" for c in claim.evidence)


def test_check_b_same_source_neighbour_ignored():
    doc = _doc("self text " * 10)
    claim = Claim(id="claim:paper-x:5", text="A neutral factual claim with 5 widgets.",
                  source_slug="paper-x")
    # neighbour from the SAME source must never count as a contradiction
    same = Chunk(id="ch", source_slug="paper-x", section="S", text="same source text",
                 char_span=(0, 10))
    same.__dict__["similarity"] = 0.99
    flagged = flag_shaky([claim], doc, FakeRetriever(hits=[same]), None, FakeLLM(), Settings())
    assert flagged == []  # nothing flagged: no Check-A demotion, no cross-source neighbour


def test_check_b_low_sim_neighbour_ignored():
    doc = _doc("body " * 20)
    claim = Claim(id="claim:paper-x:6", text="A neutral factual claim with 5 widgets.",
                  source_slug="paper-x")
    far = Chunk(id="ch", source_slug="other", section="S", text="unrelated", char_span=(0, 5))
    far.__dict__["similarity"] = 0.40  # below threshold
    flagged = flag_shaky([claim], doc, FakeRetriever(hits=[far]), None, FakeLLM(), Settings())
    assert flagged == []


# --------------------------------------------------------------------------- #
# write_review_queue
# --------------------------------------------------------------------------- #

def test_write_review_queue_renders_checklist():
    from befkb.models import Citation

    flagged = [
        Claim(id="claim:p:1", text="Unsupported thing.", source_slug="p",
              status="unsupported-by-source", rationale="Source-check: not grounded.",
              evidence=[Citation(source_slug="p", quote="nothing here")]),
        Claim(id="claim:p:2", text="Vague best-ever claim.", source_slug="p",
              status="vague", rationale="Vague: superlative with no comparator"),
    ]
    with tempfile.TemporaryDirectory() as td:
        out = write_review_queue(flagged, Path(td))
        assert out.exists()
        text = out.read_text(encoding="utf-8")
        assert "Claim review queue" in text
        assert "- [ ]" in text
        assert "unsupported-by-source" in text
        assert "vague" in text
        assert "Unsupported thing." in text
        assert "Nothing here is asserted true or false" in text


def test_write_review_queue_empty():
    with tempfile.TemporaryDirectory() as td:
        out = write_review_queue([], Path(td))
        assert out.exists()
        assert "No shaky claims flagged" in out.read_text(encoding="utf-8")
