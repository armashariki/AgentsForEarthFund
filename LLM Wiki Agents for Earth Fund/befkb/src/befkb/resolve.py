"""Entity resolution — fold new nodes into the canonical knowledge graph.

When extraction (``extract.py``) emits a fresh batch of :class:`~befkb.models.Node`
objects, many of them already exist in the graph under a slightly different surface
form: ``"GPT-4"`` vs ``"GPT 4"``, ``"CAPTAIN"`` vs ``"the CAPTAIN system"``,
``"reinforcement learning"`` vs ``"RL"``. Writing them in verbatim would fork the
graph into near-duplicate nodes — the #1 way a knowledge graph rots. Resolution
maps each new node to a *canonical* node when we are confident they are the same
real-world thing, queues borderline pairs for a human, and only mints a genuinely
new node when nothing matches.

Two entry points, same scoring, different side effects:

* :func:`resolve` — the **write** path used during ingest. Auto-merges confident
  matches (records the alias on the canonical node + an ``id -> canonical_id`` row
  in the graph's alias table, via :meth:`GraphStore.upsert_nodes` /
  ``set_alias``), queues mid-confidence pairs as ``needs_review``, and upserts the
  rest as brand-new nodes. Returns a :class:`~befkb.models.ResolutionResult`.
* :func:`anchor` — the **read-only** path used during ``apply``. Same blocking +
  scoring, but it never touches the graph: it just returns ``{new_id:
  canonical_id}`` for every new node whose best match clears ``resolve_review_min``.
  This is how a freshly-parsed document's entities get pinned to existing graph
  nodes so the applicability traversal has something to start from.

Scoring per (new, candidate) pair is the **max** of:
  * a lexical score — ``rapidfuzz`` ``token_set_ratio`` over the cross product of
    each side's ``{name} ∪ aliases``, divided by 100; and
  * a semantic score — cosine similarity of the two *names'* embeddings.

Blocking: candidates are drawn only from ``graph.nodes_by_type(new.type)`` — we
never compare a Method against a Person. (Names are also normalised before lexical
scoring so casing/punctuation/whitespace don't sink an otherwise-perfect match.)
"""

from __future__ import annotations

import re
from typing import Iterable, Optional

import numpy as np
from rapidfuzz.fuzz import token_set_ratio

from .config import Settings
from .graphstore import GraphStore
from .llm import Embedder
from .models import Node, ResolutionResult

__all__ = ["resolve", "anchor", "score_pair"]


# --------------------------------------------------------------------------- #
# Normalisation + scoring primitives
# --------------------------------------------------------------------------- #

def _normalize(name: str) -> str:
    """Lowercase, strip punctuation to spaces, collapse whitespace.

    ``"GPT-4"`` and ``"GPT 4"`` both normalise to ``"gpt 4"``; ``"CAPTAIN"`` and
    ``"  captain "`` both to ``"captain"``. Used for the lexical comparison and as
    a cheap blocking key within a type bucket.
    """
    if not name:
        return ""
    text = name.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _surface_forms(node: Node) -> list[str]:
    """Every surface string for a node: its name plus aliases, normalised + deduped."""
    forms: list[str] = []
    seen: set[str] = set()
    for raw in [node.name, *node.aliases]:
        norm = _normalize(raw)
        if norm and norm not in seen:
            seen.add(norm)
            forms.append(norm)
    return forms


def _lexical_score(a: Node, b: Node) -> float:
    """Best ``token_set_ratio`` (0..1) over the cross product of both nodes' forms."""
    a_forms = _surface_forms(a)
    b_forms = _surface_forms(b)
    if not a_forms or not b_forms:
        return 0.0
    best = 0.0
    for af in a_forms:
        for bf in b_forms:
            best = max(best, token_set_ratio(af, bf))
            if best >= 100.0:
                return 1.0
    return best / 100.0


def _cosine(u: np.ndarray, v: np.ndarray) -> float:
    """Cosine similarity of two 1-D vectors, clamped to [0, 1]; 0 on degenerate input."""
    if u is None or v is None:
        return 0.0
    nu = float(np.linalg.norm(u))
    nv = float(np.linalg.norm(v))
    if nu == 0.0 or nv == 0.0:
        return 0.0
    sim = float(np.dot(u, v) / (nu * nv))
    if not np.isfinite(sim):
        return 0.0
    # cosine is in [-1, 1]; negatives mean "unrelated", floor them at 0 so they
    # can never *raise* a score above the lexical signal.
    return max(0.0, min(1.0, sim))


def score_pair(
    a: Node,
    b: Node,
    a_emb: Optional[np.ndarray] = None,
    b_emb: Optional[np.ndarray] = None,
) -> float:
    """Similarity in [0, 1] = max(lexical token_set_ratio, name embedding cosine).

    Embeddings are optional; when both are supplied the semantic channel can rescue
    a match that lexical scoring misses (e.g. ``"reinforcement learning"`` vs
    ``"RL"``). When they are absent we fall back to lexical alone.
    """
    lex = _lexical_score(a, b)
    sem = _cosine(a_emb, b_emb) if (a_emb is not None and b_emb is not None) else 0.0
    return max(lex, sem)


# --------------------------------------------------------------------------- #
# Embedding helper (one batched call, name-keyed cache, defensive)
# --------------------------------------------------------------------------- #

def _embed_names(names: Iterable[str], embedder: Optional[Embedder]) -> dict[str, np.ndarray]:
    """Embed a set of names in a single batched call → ``{name: vector}``.

    Returns an empty map (so callers fall back to lexical-only) if there is no
    embedder or the embedding call fails for any reason — resolution must never
    crash an ingest because the embedding server hiccuped.
    """
    uniq = [n for n in dict.fromkeys(names) if n and n.strip()]
    if not uniq or embedder is None:
        return {}
    try:
        mat = embedder.embed(uniq)
    except Exception:
        return {}
    if mat is None or getattr(mat, "shape", (0,))[0] != len(uniq):
        return {}
    return {name: np.asarray(mat[i], dtype=np.float32) for i, name in enumerate(uniq)}


# --------------------------------------------------------------------------- #
# Best-match search within a type block
# --------------------------------------------------------------------------- #

def _best_match(
    new: Node,
    candidates: list[Node],
    name_vecs: dict[str, np.ndarray],
) -> tuple[Optional[Node], float]:
    """Highest-scoring existing candidate for ``new`` and its score (0 if none)."""
    new_emb = name_vecs.get(new.name)
    best_node: Optional[Node] = None
    best_score = 0.0
    for cand in candidates:
        if cand.id == new.id:
            # identical id — already the same canonical node; treat as a perfect match
            return cand, 1.0
        s = score_pair(new, cand, new_emb, name_vecs.get(cand.name))
        if s > best_score:
            best_score = s
            best_node = cand
    return best_node, best_score


def _candidates_by_type(new: Node, graph: GraphStore) -> list[Node]:
    """Blocking: existing nodes of the same type are the only merge candidates."""
    try:
        return graph.nodes_by_type(new.type)
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def resolve(
    new_nodes: list[Node],
    graph: GraphStore,
    embedder: Optional[Embedder],
    settings: Settings,
    write: bool = True,
) -> ResolutionResult:
    """Resolve a batch of new nodes against the graph, writing merges by default.

    For each new node, block candidates by type and find the best match:

    * ``score >= settings.resolve_auto_merge`` → **merge**. The new node's name
      and aliases are folded onto the canonical node (so future lookups find it),
      an ``id -> canonical_id`` alias row is recorded, and the pair is reported in
      ``merged``. If ``write`` is False this is recorded but not persisted.
    * ``settings.resolve_review_min <= score < auto_merge`` → **needs_review**:
      reported as ``(new_id, candidate_id, score)`` and *also* created as a node
      (we never silently drop a fact — a human disambiguates later from the queue).
    * ``score < resolve_review_min`` → **create** a new canonical node.

    Within a single batch we resolve **incrementally**: a node created earlier in
    the batch becomes a candidate for later nodes, so two surface forms of the same
    new entity collapse without needing a prior graph entry. Returns a
    :class:`ResolutionResult`; all graph mutation goes through ``graph`` (which
    ``pipeline.ingest`` later persists via ``graph.save()``).
    """
    result = ResolutionResult()
    if not new_nodes:
        return result

    # one batched embedding of every new name + every candidate name we might compare
    all_names: list[str] = [n.name for n in new_nodes if n.name]
    for n in new_nodes:
        for cand in _candidates_by_type(n, graph):
            all_names.append(cand.name)
    name_vecs = _embed_names(all_names, embedder)

    auto = settings.resolve_auto_merge
    review_min = settings.resolve_review_min

    # nodes minted earlier in this batch, grouped by type, so intra-batch dupes merge
    batch_created: dict[str, list[Node]] = {}

    for new in new_nodes:
        if not new or not new.name or not new.name.strip():
            continue  # defensive: never resolve a nameless node

        candidates = list(_candidates_by_type(new, graph))
        candidates.extend(batch_created.get(str(new.type), []))

        match, score = _best_match(new, candidates, name_vecs)

        if match is not None and score >= auto:
            # --- auto-merge -------------------------------------------------
            result.merged.append((new.id, match.id))
            if write and new.id != match.id:
                # fold the new surface form onto the canonical node, then alias
                _merge_into(match, new, graph)
        elif match is not None and score >= review_min:
            # --- borderline: queue for review, but still keep the node ------
            result.needs_review.append((new.id, match.id, round(score, 4)))
            created = _create(new, graph, write)
            result.created.append(created)
            batch_created.setdefault(str(new.type), []).append(created)
        else:
            # --- genuinely new ----------------------------------------------
            created = _create(new, graph, write)
            result.created.append(created)
            batch_created.setdefault(str(new.type), []).append(created)

    return result


def anchor(
    new_nodes: list[Node],
    graph: GraphStore,
    embedder: Optional[Embedder],
    settings: Settings,
) -> dict[str, str]:
    """READ-ONLY resolution: ``{new_node_id: canonical_id}`` for confident matches.

    Same blocking + scoring as :func:`resolve`, but it never writes to the graph
    and never mints nodes. Used by ``applicability.apply`` to pin a fresh document's
    extracted entities onto existing graph nodes (the seeds for path traversal).

    A new node is anchored to its best same-type candidate whenever that candidate's
    score clears ``settings.resolve_review_min`` (we anchor a touch more eagerly than
    we auto-merge: a near-miss anchor only seeds traversal, it does not mutate the
    KB). Nodes with no good match are simply absent from the returned map. The
    returned canonical id is run through ``graph.resolve_alias`` so anchors always
    point at the live canonical node even if it was itself a prior merge target.
    """
    out: dict[str, str] = {}
    if not new_nodes:
        return out

    all_names: list[str] = [n.name for n in new_nodes if n.name]
    for n in new_nodes:
        for cand in _candidates_by_type(n, graph):
            all_names.append(cand.name)
    name_vecs = _embed_names(all_names, embedder)

    review_min = settings.resolve_review_min
    resolve_alias = getattr(graph, "resolve_alias", None)

    for new in new_nodes:
        if not new or not new.name or not new.name.strip():
            continue
        candidates = _candidates_by_type(new, graph)
        match, score = _best_match(new, candidates, name_vecs)
        if match is not None and score >= review_min:
            canonical = match.id
            if callable(resolve_alias):
                try:
                    canonical = resolve_alias(match.id)
                except Exception:
                    canonical = match.id
            out[new.id] = canonical
    return out


# --------------------------------------------------------------------------- #
# Write helpers (only touched when write=True)
# --------------------------------------------------------------------------- #

def _create(new: Node, graph: GraphStore, write: bool) -> Node:
    """Upsert a brand-new canonical node (no-op on the graph when ``write`` is False)."""
    if write:
        graph.upsert_nodes([new])
    return new


def _merge_into(canonical: Node, new: Node, graph: GraphStore) -> None:
    """Fold ``new`` onto the canonical node and record the id alias.

    The new node's name (a previously-unseen surface form) and its aliases become
    aliases of the canonical node, and its provenance is carried over — we upsert a
    Node carrying the *canonical* id so :meth:`GraphStore.upsert_nodes` merges
    aliases/provenance/props in for us (canonical name is kept; new name demoted to
    an alias). We then write an ``id -> canonical_id`` row so any edge or lookup that
    still references the old id follows through to the canonical node.
    """
    alias_payload = Node(
        id=canonical.id,
        type=canonical.type,
        name=canonical.name,
        aliases=list(dict.fromkeys([*new.aliases, new.name])),
        provenance=list(new.provenance),
        props=dict(new.props),
        sensitivity=canonical.sensitivity,
    )
    graph.upsert_nodes([alias_payload])
    set_alias = getattr(graph, "set_alias", None)
    if callable(set_alias) and new.id != canonical.id:
        try:
            set_alias(new.id, canonical.id)
        except Exception:
            pass
