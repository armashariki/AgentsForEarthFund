"""Custom Layer 2 — the killer query: *how does this new content connect to my grants?*

This module answers, for a freshly-arrived document, the single most useful question
the knowledge base can answer for a funder: **"does this connect to anything we fund,
and if so, how, and is the evidence solid?"**

The connection is *discovered structurally* by walking the existing knowledge graph
between the new document's entities/ideas (the *anchors*) and the internal ``Grant``
nodes (the *targets*). The path comes from the graph; the LLM only narrates it. We never
let the model invent a bridge that the graph does not contain.

Nine-step pipeline (implemented in :func:`how_does_this_apply`):

1. Parse + extract the new doc into nodes/edges (NO commit to the graph).
2. Read-only ``anchor`` of the new nodes onto canonical graph ids; collect ``novel_to_kb``.
3. Seed targets = ``graph.nodes_by_type("Grant")``.
4. For each (anchor, grant): ``graph.paths(...)`` undirected with hub-penalty; rank by
   short-hops > confidence > hub-penalty > endpoint embedding similarity; classify the
   :class:`Connection` kind.
5. Per-hop evidence via ``retriever.evidence_for_edge``.
6. ONE structured ``llm.complete`` that *narrates* the given paths (prose from the model,
   structure from the graph).
7. If the best path is weak, expand the frontier one hop and retry once, else say so honestly.
8. Overlay shaky claims (``claims.flag_shaky``) that sit on a discovered path.
9. ``file_back`` writes ``wiki/analyses/<slug>.md``.

If there are **zero** ``Grant`` nodes, we still return the most-related ``Source``/``Method``
nodes and say so in the summary, so the tool degrades gracefully on a young KB.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
from pydantic import BaseModel, Field

from .config import Settings
from .graphstore import GraphStore
from .llm import Embedder, LLMClient
from .models import (
    ApplicabilityResult,
    Citation,
    Claim,
    Connection,
    ConnectionKind,
    Edge,
    Node,
    slugify,
)

# Relations that, when present on a path, mark the connection as a *tradeoff* /
# tension rather than a straightforward overlap.
TRADEOFF_RELS: frozenset[str] = frozenset(
    {"has-tradeoff-with", "contradicts", "challenges", "supersedes"}
)
# Relations that mark a shared *organisation* (same lab / funder / affiliation).
SAME_ORG_RELS: frozenset[str] = frozenset(
    {"built-by", "affiliated-with", "authored-by"}
)
# Relations that suggest a *capability* the new work could lend a grant.
CAPABILITY_RELS: frozenset[str] = frozenset(
    {"uses-technology", "uses-method", "advances-over", "state-of-the-art-for"}
)

# A connection is "weak" (triggers the one-hop frontier expansion / honest no-connection)
# below this strength.
WEAK_STRENGTH = 0.30
# Cap how many paths we hand to the narrator LLM (keeps the prompt small + the 7B honest).
MAX_PATHS_TO_NARRATE = 8


# --------------------------------------------------------------------------- #
# LLM narration schema (mirrors ApplicabilityResult but is the *narration* unit:
# the model fills prose; we keep the structural fields ourselves).
# --------------------------------------------------------------------------- #

class _ConnectionNarration(BaseModel):
    """The model's prose for a single graph-derived path. No structure invented here."""
    path_index: int = Field(description="0-based index of the path being narrated")
    why: str = Field(default="", description="1-2 sentences: how the new doc relates to this grant")


class _Narration(BaseModel):
    """Structured narration output. Paths are GIVEN; the model only writes prose."""
    summary: str = Field(default="", description="2-4 sentence overall answer for the human")
    connections: list[_ConnectionNarration] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Internal helpers
# --------------------------------------------------------------------------- #

def _node_name(graph: GraphStore, node_id: str) -> str:
    n = graph.get_node(node_id)
    return n.name if n is not None else node_id.split(":", 1)[-1]


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    if a.size == 0 or b.size == 0:
        return 0.0
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return float(np.dot(a, b) / (na * nb))


def _embed_node(embedder: Embedder, graph: GraphStore, node_id: str) -> np.ndarray:
    """Embed a node by its display name + aliases (best-effort; tolerant of failures)."""
    node = graph.get_node(node_id)
    if node is None:
        text = node_id.split(":", 1)[-1].replace("-", " ")
    else:
        text = " ".join([node.name, *node.aliases]).strip() or node.name
    try:
        emb = embedder.embed([text])
        return np.asarray(emb[0], dtype=np.float32) if len(emb) else np.zeros((0,), dtype=np.float32)
    except Exception:
        return np.zeros((0,), dtype=np.float32)


def _path_node_ids(path: list[Edge]) -> list[str]:
    """Ordered unique node ids along an edge path (src of first edge ... dst of last)."""
    if not path:
        return []
    ids: list[str] = [path[0].src]
    for e in path:
        # tolerate undirected hops where the shared node may be on either end
        if e.src == ids[-1]:
            ids.append(e.dst)
        elif e.dst == ids[-1]:
            ids.append(e.src)
        else:
            # disjoint (shouldn't happen for a real path) — append both defensively
            ids.append(e.src)
            ids.append(e.dst)
    # de-dup preserving order
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _bridge_node_ids(path: list[Edge], anchor_id: str, grant_id: str) -> list[str]:
    """Intermediate nodes on a path (everything that is neither the anchor nor the grant)."""
    return [n for n in _path_node_ids(path) if n not in (anchor_id, grant_id)]


def _classify_kind(
    graph: GraphStore,
    path: list[Edge],
    anchor_id: str,
    grant_id: str,
) -> ConnectionKind:
    """Classify a connection from the structure of its path.

    Precedence (spec):
    - ``tradeoff``   if any tension relation (has-tradeoff-with/contradicts/challenges) sits
      on the path.
    - ``shared-idea`` if any *bridge* node has type ``Idea``.
    - ``same-org``   if the path runs through an ``Organization`` / uses an org-binding rel.
    - ``capability-transfer`` if the path carries a capability relation (uses-*, advances-over).
    - ``shared-entity`` otherwise (the default: a concrete shared Technology/Concept/Source).
    """
    rels = {e.rel for e in path}
    if rels & TRADEOFF_RELS:
        return "tradeoff"

    bridges = _bridge_node_ids(path, anchor_id, grant_id)
    bridge_types = []
    for bid in bridges:
        n = graph.get_node(bid)
        if n is not None:
            bridge_types.append(n.type)

    if any(t == "Idea" for t in bridge_types):
        return "shared-idea"
    if "Organization" in bridge_types or (rels & SAME_ORG_RELS):
        return "same-org"
    if rels & CAPABILITY_RELS:
        return "capability-transfer"
    return "shared-entity"


def _path_strength(
    path: list[Edge],
    anchor_id: str,
    grant_id: str,
    graph: GraphStore,
    settings: Settings,
    endpoint_sim: float,
) -> float:
    """Score a path so we can rank: short-hops > confidence > hub-penalty > endpoint sim.

    Returns a value in roughly [0, 1]; higher is a stronger connection.
    """
    if not path:
        return 0.0
    hops = len(path)
    # 1) hop term — 1 hop is best; decays with length.
    hop_term = 1.0 / float(hops)
    # 2) mean edge confidence along the path.
    conf_term = float(np.mean([max(0.0, min(1.0, e.confidence)) for e in path]))
    # 3) hub penalty — paths threading high-degree hub nodes are weaker.
    hub_term = 1.0
    if settings.hub_penalty:
        for nid in _bridge_node_ids(path, anchor_id, grant_id):
            try:
                deg = len(graph.neighbors(nid))
            except Exception:
                deg = 0
            if deg > settings.hub_degree_threshold:
                hub_term *= settings.hub_degree_threshold / float(deg)
    # 4) endpoint embedding similarity (semantic plausibility of anchor<->grant).
    sim_term = max(0.0, endpoint_sim)

    # Weighting reflects the spec's priority order.
    return float(
        0.45 * hop_term
        + 0.30 * conf_term
        + 0.15 * hub_term
        + 0.10 * sim_term
    )


def _collect_evidence(retriever, path: list[Edge]) -> list[Citation]:
    """Per-hop evidence via the retriever, plus each edge's own citation. De-duplicated."""
    cites: list[Citation] = []
    seen: set[tuple] = set()

    def _add(c: Optional[Citation]) -> None:
        if c is None:
            return
        key = (c.source_slug, c.char_span, (c.quote or "")[:120])
        if key not in seen:
            seen.add(key)
            cites.append(c)

    for e in path:
        _add(e.citation)
        try:
            for c in retriever.evidence_for_edge(e):
                _add(c)
        except Exception:
            # retriever is best-effort; a missing index must not sink the whole query.
            continue
    return cites


def _best_paths_for_pair(
    graph: GraphStore,
    embedder: Embedder,
    settings: Settings,
    anchor_id: str,
    grant_id: str,
    max_hops: int,
    anchor_emb_cache: dict[str, np.ndarray],
) -> list[tuple[list[Edge], float]]:
    """All graph paths between an anchor and a grant, scored + sorted (strongest first)."""
    try:
        raw_paths = graph.paths(
            anchor_id, grant_id, max_hops=max_hops, undirected=True, hub_penalty=True
        )
    except Exception:
        return []
    if not raw_paths:
        return []

    # NB: dict.setdefault eagerly evaluates its default, so it would embed on every call
    # and defeat the cache entirely — use an explicit membership check.
    if anchor_id not in anchor_emb_cache:
        anchor_emb_cache[anchor_id] = _embed_node(embedder, graph, anchor_id)
    if grant_id not in anchor_emb_cache:
        anchor_emb_cache[grant_id] = _embed_node(embedder, graph, grant_id)
    endpoint_sim = _cosine(anchor_emb_cache[anchor_id], anchor_emb_cache[grant_id])

    scored: list[tuple[list[Edge], float]] = []
    for p in raw_paths:
        if not p:
            continue
        s = _path_strength(p, anchor_id, grant_id, graph, settings, endpoint_sim)
        scored.append((p, s))
    # short-hops first as the primary key, then strength.
    scored.sort(key=lambda ps: (len(ps[0]), -ps[1]))
    # re-sort so the strongest (by strength) bubbles up while still respecting hop length:
    scored.sort(key=lambda ps: -ps[1])
    return scored


def _build_connections(
    graph: GraphStore,
    retriever,
    embedder: Embedder,
    settings: Settings,
    anchor_ids: list[str],
    grants: list[Node],
    max_hops: int,
) -> list[Connection]:
    """Discover one best Connection per (grant) over all anchors. Returns sorted, strongest first."""
    anchor_emb_cache: dict[str, np.ndarray] = {}
    # best path per grant across all anchors
    best_per_grant: dict[str, tuple[list[Edge], float, str]] = {}  # grant_id -> (path, strength, anchor)

    for grant in grants:
        for anchor_id in anchor_ids:
            if anchor_id == grant.id:
                continue
            scored = _best_paths_for_pair(
                graph, embedder, settings, anchor_id, grant.id, max_hops, anchor_emb_cache
            )
            if not scored:
                continue
            top_path, top_strength = scored[0]
            cur = best_per_grant.get(grant.id)
            if cur is None or top_strength > cur[1]:
                best_per_grant[grant.id] = (top_path, top_strength, anchor_id)

    connections: list[Connection] = []
    for grant in grants:
        if grant.id not in best_per_grant:
            continue
        path, strength, anchor_id = best_per_grant[grant.id]
        kind = _classify_kind(graph, path, anchor_id, grant.id)
        evidence = _collect_evidence(retriever, path)
        shared = _bridge_node_ids(path, anchor_id, grant.id) or [anchor_id]
        connections.append(
            Connection(
                grant_id=grant.id,
                grant_name=grant.name,
                path=path,
                shared_nodes=shared,
                evidence=evidence,
                why="",  # filled by the narrator LLM in step 6
                kind=kind,
                strength=round(float(strength), 4),
            )
        )
    connections.sort(key=lambda c: -c.strength)
    return connections


def _describe_path(graph: GraphStore, path: list[Edge]) -> str:
    """Human/LLM-readable rendering of a path: ``A —rel→ B —rel→ C``."""
    if not path:
        return "(direct)"
    parts: list[str] = []
    cursor = path[0].src
    parts.append(_node_name(graph, cursor))
    for e in path:
        nxt = e.dst if e.src == cursor else e.src
        parts.append(f"—{e.rel}→ {_node_name(graph, nxt)}")
        cursor = nxt
    return " ".join(parts)


def _narrate(
    llm: LLMClient,
    graph: GraphStore,
    new_doc_title: str,
    connections: list[Connection],
    novel_to_kb: list[str],
    new_stance: Optional[dict[str, str]] = None,
) -> _Narration:
    """ONE structured LLM call that narrates the GIVEN paths. The model never invents bridges."""
    if not connections:
        return _Narration(summary="", connections=[])

    new_stance = new_stance or {}
    lines: list[str] = []
    for i, c in enumerate(connections[:MAX_PATHS_TO_NARRATE]):
        stance_note = ""
        for nid in (list(c.shared_nodes) + [e.src for e in c.path] + [e.dst for e in c.path]):
            rel = new_stance.get(nid)
            if rel:
                stance_note = f"\n    NEW-DOC STANCE: this document **{rel}** \"{_node_name(graph, nid)}\""
                if rel in TRADEOFF_RELS:
                    break
        lines.append(
            f"[{i}] grant=\"{c.grant_name}\"  kind={c.kind}  strength={c.strength:.2f}\n"
            f"    path: {_describe_path(graph, c.path)}{stance_note}"
        )
    paths_block = "\n".join(lines)
    novel_block = ", ".join(novel_to_kb[:20]) if novel_to_kb else "(none)"

    system = (
        "You are the head of AI for a climate-and-nature funder. You are given GRAPH-DERIVED "
        "paths connecting a new document to internal grants. Each path is REAL and already "
        "verified by the knowledge graph. Your ONLY job is to write a short, precise prose "
        "explanation of WHY each path is relevant to the funder. Do NOT invent new entities, "
        "relationships, or bridges beyond what each given path states. CRITICAL: if a path is a "
        "'tradeoff' kind, OR a NEW-DOC STANCE line shows this document challenges/contradicts the "
        "shared node, the connection is a CRITIQUE / TENSION — say plainly that the new work "
        "questions or pushes against the grant's approach. NEVER describe a critique as 'alignment' "
        "or a 'shared goal'. Be concrete and concise."
    )
    prompt = (
        f"NEW DOCUMENT: {new_doc_title}\n"
        f"Entities in this doc that are NEW to the knowledge base: {novel_block}\n\n"
        f"GRAPH PATHS (path_index in brackets):\n{paths_block}\n\n"
        "For each path, write `why`: 1-2 sentences on how the new document relates to that grant, "
        "grounded strictly in the path shown. Then write an overall `summary` (2-4 sentences) the "
        "funder can read at a glance. Return JSON matching the schema."
    )
    try:
        out = llm.complete(prompt, schema=_Narration, system=system)
        if isinstance(out, _Narration):
            return out
        return _Narration.model_validate(out)
    except Exception:
        # 7B noise / transport failure — degrade to a deterministic structural narration.
        narrations = [
            _ConnectionNarration(
                path_index=i,
                why=f"Connected via {c.kind.replace('-', ' ')}: {_describe_path(graph, c.path)}.",
            )
            for i, c in enumerate(connections[:MAX_PATHS_TO_NARRATE])
        ]
        return _Narration(
            summary=(
                f"Found {len(connections)} graph connection(s) between “{new_doc_title}” and "
                "internal grants."
            ),
            connections=narrations,
        )


def _apply_narration(connections: list[Connection], narration: _Narration) -> None:
    """Write the model's prose back onto the structural Connections (in place)."""
    by_idx = {n.path_index: n for n in narration.connections}
    for i, c in enumerate(connections):
        n = by_idx.get(i)
        if n is not None and n.why.strip():
            c.why = n.why.strip()
        elif not c.why:
            c.why = f"Connected via {c.kind.replace('-', ' ')}."


def _frontier_expand_anchor_ids(
    graph: GraphStore,
    anchor_ids: list[str],
) -> list[str]:
    """Expand the anchor frontier by one hop: add direct neighbours of the current anchors.

    Used only when the first pass finds nothing / only weak paths (step 7). Returns a new,
    de-duplicated anchor list (originals kept first).
    """
    expanded: list[str] = list(anchor_ids)
    seen = set(anchor_ids)
    for aid in anchor_ids:
        try:
            edges = graph.neighbors(aid)
        except Exception:
            continue
        for e in edges:
            for nid in (e.src, e.dst):
                if nid != aid and nid not in seen:
                    seen.add(nid)
                    expanded.append(nid)
    return expanded


def _fallback_related_nodes(
    graph: GraphStore,
    embedder: Embedder,
    anchor_ids: list[str],
    new_doc_title: str,
    limit: int = 5,
) -> list[Connection]:
    """No Grant nodes exist → return the most-related Source/Method nodes instead.

    These are *not* grant connections; the summary makes that explicit. We rank candidate
    Source/Method nodes by embedding similarity to the new doc's anchors and emit zero-length
    paths (no bridge invented — just "these are the nearest things we already know about").
    """
    candidates: list[Node] = []
    for t in ("Source", "Method", "Technology", "Concept"):
        try:
            candidates.extend(graph.nodes_by_type(t))
        except Exception:
            continue
    if not candidates:
        return []

    # mean anchor embedding as the query vector
    anchor_embs = [_embed_node(embedder, graph, a) for a in anchor_ids]
    anchor_embs = [e for e in anchor_embs if e.size]
    if anchor_embs:
        q = np.mean(np.vstack(anchor_embs), axis=0)
    else:
        try:
            q = np.asarray(embedder.embed([new_doc_title])[0], dtype=np.float32)
        except Exception:
            q = np.zeros((0,), dtype=np.float32)

    scored: list[tuple[Node, float]] = []
    for n in candidates:
        if n.id in anchor_ids:
            continue
        sim = _cosine(q, _embed_node(embedder, graph, n.id))
        scored.append((n, sim))
    scored.sort(key=lambda ns: -ns[1])

    out: list[Connection] = []
    for n, sim in scored[:limit]:
        out.append(
            Connection(
                grant_id=n.id,
                grant_name=n.name,
                path=[],
                shared_nodes=[n.id],
                evidence=list(n.provenance),
                why=f"Most-related existing {n.type} (no grants in the KB yet).",
                kind="shared-entity",
                strength=round(max(0.0, sim), 4),
            )
        )
    return out


def _overlay_shaky_claims(
    connections: list[Connection],
    flagged: list[Claim],
    new_doc_slug: Optional[str] = None,
) -> list[Claim]:
    """Step 8: surface flagged claims that qualify trust in the discovered connections.

    The NEW document is never committed to the graph, so its claims can never be "on a
    graph path" — yet they are precisely the caveats a funder needs (they qualify trust in
    the new content that formed the connection). So we surface the new doc's shaky claims,
    plus any flagged claim whose source sits on a connection path, plus any KB contradiction.
    """
    if not flagged:
        return []
    path_slugs: set[str] = set()
    for c in connections:
        for cit in c.evidence:
            if cit.source_slug:
                path_slugs.add(cit.source_slug)
        for e in c.path:
            if e.citation and e.citation.source_slug:
                path_slugs.add(e.citation.source_slug)
    out: list[Claim] = [
        cl for cl in flagged
        if cl.source_slug == new_doc_slug or cl.source_slug in path_slugs
    ]
    # Always surface anything that directly contradicts the KB, even if off-path.
    for cl in flagged:
        if cl.status == "contradicts-KB" and cl not in out:
            out.append(cl)
    return out


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def how_does_this_apply(
    new_content: Path,
    llm: LLMClient,
    graph: GraphStore,
    retriever,
    embedder: Embedder,
    settings: Settings,
    max_hops: int = 3,
) -> ApplicabilityResult:
    """Answer "how does this new content connect to my grants?" — the Layer-2 killer query.

    Parses + extracts ``new_content`` (without committing), anchors its entities onto the
    existing graph read-only, then structurally discovers and narrates the strongest paths
    from those anchors to internal ``Grant`` nodes. Returns an :class:`ApplicabilityResult`.

    The path is always graph-derived; the LLM only narrates. Degrades gracefully when there
    are no grants (returns nearest Source/Method nodes and says so).
    """
    new_content = Path(new_content)

    # --- step 1: parse + extract (NO commit) -------------------------------- #
    # Imported lazily so this module stays importable even while siblings are in flux.
    from .ingest.parser import get_parser  # type: ignore
    from . import extract as _extract  # type: ignore
    from . import claims as _claims  # type: ignore

    parser = get_parser(new_content)
    doc = parser.parse(new_content)
    new_doc_title = doc.title or doc.source_slug

    claims_list: list[Claim] = []
    try:
        claims_list = _claims.extract_claims(doc, llm)
    except Exception:
        claims_list = []

    new_nodes, new_edges = _extract.extract_graph(doc, claims_list, llm, settings)

    # --- step 2: read-only anchor + novel_to_kb ----------------------------- #
    from . import resolve as _resolve  # type: ignore

    anchor_map: dict[str, str] = {}
    try:
        anchor_map = _resolve.anchor(new_nodes, graph, embedder, settings)
    except Exception:
        anchor_map = {}

    anchor_ids: list[str] = []
    seen_anchor: set[str] = set()
    novel_to_kb: list[str] = []
    for n in new_nodes:
        canonical = anchor_map.get(n.id)
        if canonical and graph.get_node(canonical) is not None:
            if canonical not in seen_anchor:
                seen_anchor.add(canonical)
                anchor_ids.append(canonical)
        elif graph.get_node(n.id) is not None:
            if n.id not in seen_anchor:
                seen_anchor.add(n.id)
                anchor_ids.append(n.id)
        else:
            # not present in the KB under any canonical id → novel
            if n.name and n.name not in novel_to_kb:
                novel_to_kb.append(n.name)

    # --- new-doc STANCE toward anchored nodes (fixes the valence bug) -------- #
    # The new document's OWN edges tell us whether it ENDORSES or CHALLENGES each
    # shared node. Discarding this (the original bug) makes a critique read as agreement.
    src_id = f"source:{doc.source_slug}"
    new_stance: dict[str, str] = {}          # canonical_node_id -> relation the new doc takes
    for e in new_edges:
        if e.src != src_id:
            continue
        canon = anchor_map.get(e.dst)
        if not canon or graph.get_node(canon) is None:
            canon = e.dst if graph.get_node(e.dst) is not None else None
        if not canon:
            continue
        # tension relations win over neutral/positive ones for the same node
        if e.rel in TRADEOFF_RELS or canon not in new_stance:
            new_stance[canon] = e.rel

    # --- step 3: seed targets = Grant nodes --------------------------------- #
    try:
        grants = [g for g in graph.nodes_by_type("Grant") if g is not None]
    except Exception:
        grants = []

    # --- no-grants graceful fallback ---------------------------------------- #
    if not grants:
        fb = _fallback_related_nodes(graph, embedder, anchor_ids, new_doc_title)
        summary = (
            "No internal Grant nodes exist in the knowledge base yet, so this is NOT a grant "
            "match. "
            + (
                f"The {len(fb)} most-related existing items are shown instead."
                if fb
                else "The knowledge base has nothing closely related yet."
            )
        )
        flagged = _overlay_shaky_claims(fb, _safe_flag_shaky(claims_list, doc, retriever, graph, llm, settings), doc.source_slug)
        return ApplicabilityResult(
            new_doc=new_doc_title,
            connections=fb,
            novel_to_kb=novel_to_kb,
            flagged_claims=flagged,
            summary=summary,
        )

    # --- step 4 + 5: discover, rank, classify paths; collect per-hop evidence #
    connections = _build_connections(
        graph, retriever, embedder, settings, anchor_ids, grants, max_hops
    )

    # --- step 7: weak best path → expand frontier one hop, retry once ------- #
    best_strength = connections[0].strength if connections else 0.0
    if best_strength < WEAK_STRENGTH:
        expanded_anchor_ids = _frontier_expand_anchor_ids(graph, anchor_ids)
        if len(expanded_anchor_ids) > len(anchor_ids):
            retry = _build_connections(
                graph, retriever, embedder, settings, expanded_anchor_ids, grants, max_hops
            )
            if retry and (not connections or retry[0].strength > best_strength):
                connections = retry
                best_strength = connections[0].strength

    # --- honest "no strong connection" -------------------------------------- #
    if not connections or best_strength < WEAK_STRENGTH:
        flagged = _overlay_shaky_claims(
            connections, _safe_flag_shaky(claims_list, doc, retriever, graph, llm, settings), doc.source_slug
        )
        summary = (
            f"No strong connection found between “{new_doc_title}” and the "
            f"{len(grants)} internal grant(s). "
            + (
                "Only weak, multi-hop links exist — treat as low-confidence."
                if connections
                else "The new document shares no graph path with any grant within "
                f"{max_hops} hops."
            )
        )
        return ApplicabilityResult(
            new_doc=new_doc_title,
            connections=connections,
            novel_to_kb=novel_to_kb,
            flagged_claims=flagged,
            summary=summary,
        )

    # apply the new doc's stance: a connection through a node the new doc CHALLENGES
    # is a TENSION, not an overlap — override the structural kind so it reads honestly.
    for c in connections:
        nodes_to_check = list(c.shared_nodes) + [e.src for e in c.path] + [e.dst for e in c.path]
        if any(new_stance.get(nid) in TRADEOFF_RELS for nid in nodes_to_check):
            c.kind = "tradeoff"

    # --- step 6: ONE structured narration of the GIVEN paths ---------------- #
    narration = _narrate(llm, graph, new_doc_title, connections, novel_to_kb, new_stance)
    _apply_narration(connections, narration)

    # --- step 8: overlay shaky claims sitting on a discovered path ----------- #
    flagged_all = _safe_flag_shaky(claims_list, doc, retriever, graph, llm, settings)
    flagged = _overlay_shaky_claims(connections, flagged_all, doc.source_slug)

    summary = narration.summary.strip() or (
        f"“{new_doc_title}” connects to {len(connections)} internal grant(s); "
        f"strongest link: {connections[0].grant_name} ({connections[0].kind})."
    )

    return ApplicabilityResult(
        new_doc=new_doc_title,
        connections=connections,
        novel_to_kb=novel_to_kb,
        flagged_claims=flagged,
        summary=summary,
    )


def _safe_flag_shaky(
    claims_list: list[Claim],
    doc,
    retriever,
    graph: GraphStore,
    llm: LLMClient,
    settings: Settings,
) -> list[Claim]:
    """Call claims.flag_shaky defensively (it is an LLM/IO path and may fail on a young KB)."""
    if not claims_list:
        return []
    try:
        from . import claims as _claims  # type: ignore

        flagged = _claims.flag_shaky(claims_list, doc, retriever, graph, llm, settings)
        return [c for c in flagged if c.status != "supported"]
    except Exception:
        # fall back to whatever the original extraction already marked non-supported
        return [c for c in claims_list if c.status != "supported"]


# --------------------------------------------------------------------------- #
# file_back — durable wiki page (step 9)
# --------------------------------------------------------------------------- #

def _fmt_citation(c: Citation) -> str:
    bits = [f"[[{c.source_slug}]]"] if c.source_slug else []
    if c.quote:
        q = c.quote.strip().replace("\n", " ")
        if len(q) > 200:
            q = q[:197] + "…"
        bits.append(f"“{q}”")
    if c.char_span:
        bits.append(f"(chars {c.char_span[0]}–{c.char_span[1]})")
    return " ".join(bits) if bits else "(no citation)"


def _render_path_md(result_path: list[Edge], graph: Optional[GraphStore]) -> str:
    if not result_path:
        return "_(direct / no intermediate path)_"
    if graph is not None:
        return f"`{_describe_path(graph, result_path)}`"
    # graph-less rendering (ids only)
    parts: list[str] = []
    cursor = result_path[0].src
    parts.append(cursor)
    for e in result_path:
        nxt = e.dst if e.src == cursor else e.src
        parts.append(f"—{e.rel}→ {nxt}")
        cursor = nxt
    return "`" + " ".join(parts) + "`"


def file_back(
    result: ApplicabilityResult,
    wiki_dir: Path,
    graph: Optional[GraphStore] = None,
) -> Path:
    """Write the applicability answer as a durable analysis page: ``wiki/analyses/<slug>.md``.

    Follows the wiki page format from ``CLAUDE.md``: YAML frontmatter + body with ``[[wikilinks]]``.
    Returns the path written. ``graph`` is optional and only improves path readability (names
    instead of raw ids).
    """
    wiki_dir = Path(wiki_dir)
    out_dir = wiki_dir / "analyses"
    out_dir.mkdir(parents=True, exist_ok=True)

    slug = "applies-" + slugify(result.new_doc)[:60]
    out_path = out_dir / f"{slug}.md"

    today = date.today().isoformat()
    grant_slugs = sorted({c.grant_id.split(":", 1)[-1] for c in result.connections})
    source_slugs = sorted(
        {cit.source_slug for c in result.connections for cit in c.evidence if cit.source_slug}
    )

    lines: list[str] = []
    lines.append("---")
    lines.append("type: analysis")
    lines.append(f"title: How “{result.new_doc}” applies to BEF grants")
    lines.append("aliases: []")
    lines.append(f"created: {today}")
    lines.append(f"updated: {today}")
    lines.append("sources: [" + ", ".join(source_slugs) + "]")
    lines.append("tags: [applicability, grant-connection]")
    lines.append("status: draft")
    conf = "high" if result.connections and result.connections[0].strength >= 0.6 else (
        "medium" if result.connections and result.connections[0].strength >= WEAK_STRENGTH else "low"
    )
    lines.append(f"confidence: {conf}")
    lines.append("---")
    lines.append("")
    lines.append(f"# How “{result.new_doc}” applies to BEF grants")
    lines.append("")
    lines.append(result.summary or "_(no summary)_")
    lines.append("")

    if result.novel_to_kb:
        lines.append("## New to the knowledge base")
        lines.append("")
        for name in result.novel_to_kb:
            lines.append(f"- {name}")
        lines.append("")

    lines.append("## Connections")
    lines.append("")
    if not result.connections:
        lines.append("_No grant connection found within the search horizon._")
        lines.append("")
    for i, c in enumerate(result.connections, 1):
        gslug = c.grant_id.split(":", 1)[-1]
        lines.append(
            f"### {i}. [[{gslug}|{c.grant_name}]]  ·  *{c.kind}*  ·  strength {c.strength:.2f}"
        )
        lines.append("")
        if c.why:
            lines.append(c.why)
            lines.append("")
        lines.append(f"- **Path:** {_render_path_md(c.path, graph)}")
        if c.shared_nodes:
            shared = ", ".join(f"[[{n.split(':', 1)[-1]}]]" for n in c.shared_nodes)
            lines.append(f"- **Shared nodes:** {shared}")
        if c.evidence:
            lines.append("- **Evidence:**")
            for cit in c.evidence[:6]:
                lines.append(f"  - {_fmt_citation(cit)}")
        lines.append("")

    if result.flagged_claims:
        lines.append("## Flagged claims on these paths")
        lines.append("")
        lines.append(
            "_Claims from the new document that are shaky or contradict the KB and sit on a "
            "connection path — they qualify the strength of the links above._"
        )
        lines.append("")
        for cl in result.flagged_claims:
            lines.append(f"- **[{cl.status}]** {cl.text}")
            if cl.rationale:
                lines.append(f"  - _{cl.rationale}_")
        lines.append("")

    lines.append("---")
    lines.append(
        "_Generated by befkb applicability (Layer 2). Paths are graph-derived; prose is "
        "model-narrated. Review before relying on it._"
    )
    lines.append("")

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
