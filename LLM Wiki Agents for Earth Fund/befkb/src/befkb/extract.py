"""Entity + relation extraction into the wiki v3 ontology.

Schema-constrained LLM extraction, run section-by-section (so a 7B model keeps a
tight context), merged + canonicalised into Nodes/Edges. Two non-negotiable design
points:
  1. It MUST emit abstract ``Idea`` nodes (worldviews / recurring ideas like
     "top-down optimization" or "Indigenous data sovereignty") — the idea-level
     bridge is how a method paper connects to a critique.
  2. It MUST capture STANCE: a document that critiques/argues-against an idea gets a
     ``challenges``/``contradicts`` edge, NOT a neutral ``applies-idea`` — otherwise a
     critique is mis-read as agreement (the v0.1 valence bug this version fixes).

Everything carries provenance: every Node has a source Citation, every Edge a quote.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from .config import Settings
from .models import (
    Citation, Doc, Edge, ExtractedEntity, ExtractedRelation, Node,
    NodeType, RELATION_VOCAB, node_id,
)

_VALID_TYPES: set[str] = {
    "Technology", "Method", "Concept", "Idea", "Person", "Organization", "Grant",
}
_VALID_RELS: set[str] = set(RELATION_VOCAB)

# Relation orientation: rel -> (allowed subject types, allowed object types).
# Stance relations (challenges/contradicts/has-tradeoff-with/supports) are intentionally
# NOT oriented — direction is meaningful and must be preserved as the model emits it.
_ORIENT: dict[str, tuple[set[str], set[str]]] = {
    "authored-by":      ({"Source", "Grant"}, {"Person"}),
    "built-by":         ({"Technology"}, {"Organization"}),
    "uses-technology":  ({"Source", "Grant"}, {"Technology"}),
    "uses-method":      ({"Source", "Grant"}, {"Method"}),
    "applies-idea":     ({"Source", "Grant"}, {"Idea"}),
    "addresses-domain": ({"Source", "Grant"}, {"Concept"}),
    "affiliated-with":  ({"Person"}, {"Organization"}),
}

# Stance relations — when one of these connects a path it signals tension, not agreement.
STANCE_NEGATIVE = {"challenges", "contradicts", "has-tradeoff-with", "supersedes"}

_SYSTEM = """You build a knowledge graph from one section of a document. Extract the
ENTITIES the section mentions and the RELATIONS among them, INCLUDING the document's STANCE.

NODE TYPES (pick the single best fit):
- Technology: a concrete tool/model/system/algorithm/dataset/hardware (CAPTAIN, Google Earth Engine, an LLM, GPUs).
- Method: an AI/scientific technique or approach (reinforcement learning, remote sensing, bioacoustics).
- Concept: a domain concept/metric/target/place (30x30, irrecoverable carbon, Species Habitat Index, biodiversity, Canada).
- Idea: an ABSTRACT worldview / recurring idea / framing / stance (e.g. "top-down optimization", "ecosystems-as-data",
  "technosolutionism", "relational accountability", "Indigenous data sovereignty", "human exceptionalism"). ALWAYS extract
  these when an argument, critique, or worldview is present — they are the most important nodes for connecting documents.
- Person: an author or named individual (a real name, NOT a description like "a white settler researcher").
- Organization: a lab, company, university, agency, or funder. Do NOT extract bibliographic citations
  ("Walker et al., 2022", "IUCN, 2023") as organizations.

RELATIONS — use this vocabulary; the document itself is "this document":
- POSITIVE / NEUTRAL: this document uses-technology X / uses-method X / applies-idea X / addresses-domain X / authored-by PERSON ;
  TECHNOLOGY built-by ORG ; PERSON affiliated-with ORG ; X supports Y / advances-over Y
- STANCE / TENSION (CRITICAL — do not skip): if this document CRITIQUES, argues AGAINST, warns about, or problematises an idea,
  approach, or technology, emit:  this document  challenges  IDEA   (or  contradicts / has-tradeoff-with  the target).
  NEVER record a critique as a neutral applies-idea/uses-*. The stance is the whole point.

Use "this document" as the subject for uses-*/applies-idea/addresses-domain/authored-by/challenges/contradicts.
Be precise; prefer a few high-value entities over many noisy ones; extract Ideas generously; capture stance faithfully."""

_FEWSHOT = """EXAMPLE 1 (a method paper — positive stance):
Section: "We trained the CAPTAIN reinforcement-learning agent to prioritise conservation areas in Canada to meet 30x30 targets. This reflects a top-down optimization approach to nature."
{"entities":[
  {"name":"CAPTAIN","type":"Technology","span_quote":"CAPTAIN reinforcement-learning agent"},
  {"name":"reinforcement learning","type":"Method","span_quote":"reinforcement-learning"},
  {"name":"30x30","type":"Concept","span_quote":"30x30 targets"},
  {"name":"top-down optimization","type":"Idea","span_quote":"top-down optimization approach"}
],"relations":[
  {"src_name":"this document","rel":"uses-technology","dst_name":"CAPTAIN","quote":"We trained the CAPTAIN"},
  {"src_name":"CAPTAIN","rel":"uses-method","dst_name":"reinforcement learning","quote":"reinforcement-learning agent"},
  {"src_name":"this document","rel":"addresses-domain","dst_name":"30x30","quote":"meet 30x30 targets"},
  {"src_name":"this document","rel":"applies-idea","dst_name":"top-down optimization","quote":"top-down optimization approach"}
]}

EXAMPLE 2 (a critique — NEGATIVE stance; note `challenges`):
Section: "Dominant AI-for-climate approaches risk reproducing technosolutionism, treating ecological breakdown as a problem to be optimized away through top-down optimization. This bypasses Indigenous data sovereignty."
{"entities":[
  {"name":"technosolutionism","type":"Idea","span_quote":"technosolutionism"},
  {"name":"top-down optimization","type":"Idea","span_quote":"optimized away through top-down optimization"},
  {"name":"Indigenous data sovereignty","type":"Idea","span_quote":"Indigenous data sovereignty"}
],"relations":[
  {"src_name":"this document","rel":"challenges","dst_name":"technosolutionism","quote":"risk reproducing technosolutionism"},
  {"src_name":"this document","rel":"challenges","dst_name":"top-down optimization","quote":"a problem to be optimized away"},
  {"src_name":"this document","rel":"applies-idea","dst_name":"Indigenous data sovereignty","quote":"bypasses Indigenous data sovereignty"}
]}"""

# noise: bibliographic citations, license boilerplate, run-on list-phrases
_CITE = re.compile(r"(?:\bet al\.?\b|,\s*\d{4}\)?\s*$|^\(?\d{4}\)?$)", re.IGNORECASE)
_BOILER = ("creative commons", "license", "all rights reserved", "http://", "https://", "doi.org")


class _Extraction(BaseModel):
    entities: list[ExtractedEntity] = Field(default_factory=list)
    relations: list[ExtractedRelation] = Field(default_factory=list)


def _is_noise(name: str) -> bool:
    low = name.lower()
    if _CITE.search(name):
        return True
    if any(b in low for b in _BOILER):
        return True
    if len(name) > 80 or len(name.split()) > 11:   # run-on list phrases
        return True
    if len(name.strip()) < 2:
        return True
    return False


def _coerce_type(t: str) -> NodeType | None:
    t = (t or "").strip().title().replace("Organisation", "Organization")
    if t in _VALID_TYPES:
        return t  # type: ignore[return-value]
    low = t.lower()
    if "org" in low or "lab" in low or "company" in low or "university" in low:
        return "Organization"
    if "tech" in low or "tool" in low or "model" in low or "system" in low:
        return "Technology"
    if "method" in low or "approach" in low or "algorithm" in low:
        return "Method"
    if "idea" in low or "worldview" in low or "framing" in low or "stance" in low:
        return "Idea"
    if "person" in low or "author" in low:
        return "Person"
    return "Concept"


def extract_graph(doc: Doc, claims, llm, settings: Settings) -> tuple[list[Node], list[Edge]]:
    src_node = Node(
        id=f"source:{doc.source_slug}", type="Source",
        name=doc.title or doc.source_slug, aliases=[],
        props={"path": doc.path}, sensitivity="internal",
        provenance=[Citation(source_slug=doc.source_slug, quote=(doc.title or "")[:120])],
    )
    nodes: dict[str, Node] = {src_node.id: src_node}
    edges: list[Edge] = []
    name_to_id: dict[str, str] = {"this document": src_node.id, "this paper": src_node.id}

    sections = doc.sections or [type("S", (), {"title": "body", "text": doc.markdown})()]
    for sec in sections:
        text = (getattr(sec, "text", "") or "").strip()
        if len(text) < 60:
            continue
        if any(b in getattr(sec, "title", "").lower() for b in ("reference", "acknowledg", "appendix", "citation")):
            continue
        try:
            ex = llm.complete(
                f"{_FEWSHOT}\n\nNow extract from this section:\n{text[:3500]}",
                schema=_Extraction, system=_SYSTEM,
            )
        except Exception:
            continue
        for e in ex.entities:
            name = (e.name or "").strip()
            if not name or name.lower() in ("this document", "this paper") or _is_noise(name):
                continue
            ntype = _coerce_type(e.type)
            if ntype is None:
                continue
            nid = node_id(ntype, name)
            if nid not in nodes:
                nodes[nid] = Node(
                    id=nid, type=ntype, name=name, aliases=[], sensitivity="internal",
                    provenance=[Citation(source_slug=doc.source_slug, quote=(e.span_quote or name)[:160])],
                )
            name_to_id.setdefault(name.lower(), nid)
        for r in ex.relations:
            rel = (r.rel or "").strip().lower()
            if rel not in _VALID_RELS:
                rel = "mentions"
            sid = name_to_id.get((r.src_name or "").strip().lower())
            did = name_to_id.get((r.dst_name or "").strip().lower())
            if not sid or not did or sid == did:
                continue
            sid, did = _orient(rel, sid, did, nodes)
            edges.append(Edge(
                src=sid, rel=rel, dst=did, confidence=0.6,
                citation=Citation(source_slug=doc.source_slug, quote=(r.quote or "")[:160] or None),
            ))

    connected = {e.dst for e in edges} | {e.src for e in edges}
    for nid, n in nodes.items():
        if nid != src_node.id and nid not in connected:
            edges.append(Edge(src=src_node.id, rel="mentions", dst=nid, confidence=0.4,
                              citation=Citation(source_slug=doc.source_slug)))

    return list(nodes.values()), _dedupe_edges(edges)


def _orient(rel: str, sid: str, did: str, nodes: dict[str, Node]) -> tuple[str, str]:
    rule = _ORIENT.get(rel)
    if not rule:
        return sid, did
    subj_types, obj_types = rule
    st = nodes.get(sid).type if sid in nodes else "Source"
    dt = nodes.get(did).type if did in nodes else "Source"
    if st in obj_types and dt in subj_types and st not in subj_types:
        return did, sid
    return sid, did


def _dedupe_edges(edges: list[Edge]) -> list[Edge]:
    seen: dict[tuple[str, str, str], Edge] = {}
    for e in edges:
        key = (e.src, e.rel, e.dst)
        if key not in seen or (e.citation and e.citation.quote and not (seen[key].citation and seen[key].citation.quote)):
            seen[key] = e
    return list(seen.values())
