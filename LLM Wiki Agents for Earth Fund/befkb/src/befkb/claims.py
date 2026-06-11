"""CUSTOM LAYER 1 — claim extraction + shaky-claim flagging.

This module turns a parsed :class:`~befkb.models.Doc` into a set of atomic,
check-worthy :class:`~befkb.models.Claim` objects, then *flags* the ones that
look shaky. It is deliberately epistemically humble: it **never asserts truth**.
A 7B local model is treated as a noisy assistant — its outputs are validated,
cleaned, and (for the dangerous verdicts) demoted to "human review" notes rather
than hard statuses.

Three flagging checks (see ``flag_shaky``):

* **Check A — unsupported-by-source.** For each claim we retrieve the claim's own
  source context and ask the LLM (schema-constrained) whether the source text
  ``supported`` / ``unsupported-by-source`` / ``overstated`` the claim. We set
  ``status`` + ``rationale`` + ``evidence`` (a citation back into the source).
* **Vagueness — heuristic.** Hedge words, missing units/quantities, or a bare
  "state-of-the-art" with no named comparator mark a claim ``vague``. No LLM.
* **Check B — contradicts-KB (HIGH-PRECISION STUB).** We hybrid-retrieve the top
  KB chunks for the claim; if a *very-high-similarity* neighbour from a different
  source exists, we attach a "possible contradiction — human review" note to the
  claim's rationale/evidence **without** setting a ``contradicts-KB`` verdict. We
  do not trust a 7B model to adjudicate contradictions automatically.

``write_review_queue`` renders the flagged claims as a markdown checklist (with
both-side citations) under ``settings.review_dir`` for a human to triage.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, Optional

from pydantic import BaseModel, Field

from .config import Settings
from .llm import LLMClient
from .models import (
    Citation,
    Claim,
    Doc,
    Section,
    short_hash,
)

if TYPE_CHECKING:  # avoid hard import cycles / dependence on yet-unwritten siblings
    from .graphstore import GraphStore
    from .retrieve import Retriever

# --------------------------------------------------------------------------- #
# Tunables (module-local; not worth polluting Settings with)
# --------------------------------------------------------------------------- #

# Check B: a KB neighbour must be *this* similar (cosine, 0..1) before we even
# whisper "possible contradiction". High precision by design — we'd rather miss
# a real contradiction than cry wolf and erode trust in the queue.
_KB_CONTRADICTION_SIM = 0.86

# Max claims we LLM-judge per call budget guard (defensive; large docs).
_MAX_CLAIMS_PER_SECTION = 12

# Hedge / weasel words that signal a vague, non-check-worthy assertion.
_HEDGE_WORDS = (
    "may", "might", "could", "possibly", "perhaps", "appears", "seems",
    "suggests", "potentially", "arguably", "some", "many", "several",
    "various", "often", "generally", "typically", "largely", "broadly",
    "significant", "substantial", "considerable", "promising", "robust",
)

# Bare superlatives that need a named comparator to be check-worthy.
_BARE_SUPERLATIVES = (
    "state-of-the-art", "state of the art", "best", "first", "novel",
    "unprecedented", "groundbreaking", "leading", "superior", "outperforms",
    "world-class", "cutting-edge", "breakthrough",
)

# Comparator cues — if present, a superlative is *grounded* (not bare).
_COMPARATOR_CUES = (
    "than", "compared", "versus", " vs", "relative to", "over the",
    "baseline", "prior", "previous", "outperform", "exceed", "against",
)

# Boilerplate / non-claim sections we never decompose.
_BOILERPLATE_SECTIONS = (
    "references", "bibliography", "acknowledgements", "acknowledgments",
    "author contributions", "conflict of interest", "funding",
    "supplementary", "appendix", "data availability", "competing interests",
)


# --------------------------------------------------------------------------- #
# LLM response schemas (schema-constrained so 7B output is parseable)
# --------------------------------------------------------------------------- #

class _ExtractedClaim(BaseModel):
    text: str = Field(description="One atomic, check-worthy factual assertion, self-contained.")
    quote: str = Field(default="", description="Verbatim span from the source supporting this claim.")


class _ClaimList(BaseModel):
    claims: list[_ExtractedClaim] = Field(default_factory=list)


class _SupportVerdict(BaseModel):
    verdict: str = Field(
        default="supported",
        description="One of: supported | unsupported-by-source | overstated",
    )
    rationale: str = Field(default="", description="One sentence justifying the verdict.")
    quote: str = Field(default="", description="The exact source span that grounds (or fails to ground) the claim.")


# --------------------------------------------------------------------------- #
# Prompts
# --------------------------------------------------------------------------- #

_EXTRACT_SYSTEM = (
    "You are a careful scientific claim extractor. You decompose passages into "
    "atomic, check-worthy factual claims. A check-worthy claim is a specific, "
    "verifiable assertion about what something IS, DOES, or ACHIEVES — not an "
    "opinion, a research aspiration, a section heading, a citation, or boilerplate. "
    "Each claim must stand alone (resolve pronouns; name the subject). Prefer "
    "claims that carry a number, a named method, a named system, or a measurable "
    "outcome. Quote the supporting span verbatim. If a passage has no check-worthy "
    "claims, return an empty list. Never invent content not in the passage."
)

_EXTRACT_PROMPT = (
    "Decompose the following passage into atomic, check-worthy claims.\n"
    "Return at most {max_claims} of the most check-worthy claims.\n\n"
    "Section title: {title}\n"
    "Passage:\n\"\"\"\n{text}\n\"\"\"\n"
)

_SUPPORT_SYSTEM = (
    "You are a source-grounding checker. Given a CLAIM and the SOURCE CONTEXT it "
    "was drawn from, decide whether the source text supports the claim. Answer "
    "with exactly one verdict:\n"
    " - 'supported': the source context states or directly entails the claim.\n"
    " - 'unsupported-by-source': the source context does not contain or entail "
    "the claim (the claim may be hallucinated or drawn from elsewhere).\n"
    " - 'overstated': the source says something weaker/narrower/more hedged than "
    "the claim (e.g. claim says 'proves', source says 'suggests').\n"
    "Judge ONLY against the provided source context — not your own knowledge. "
    "Quote the most relevant source span."
)

_SUPPORT_PROMPT = (
    "CLAIM:\n{claim}\n\n"
    "SOURCE CONTEXT:\n\"\"\"\n{context}\n\"\"\"\n\n"
    "Does the source context support the claim?"
)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

def extract_claims(doc: Doc, llm: LLMClient) -> list[Claim]:
    """Decompose a document into atomic, check-worthy :class:`Claim` objects.

    One schema-constrained LLM call per content section (boilerplate sections are
    skipped). ``source_span`` is recovered best-effort by locating the model's
    verbatim quote inside the section text; if the quote can't be found we fall
    back to the section's char span. All claims start ``status='supported'`` and
    are demoted later by :func:`flag_shaky`.
    """
    sections = doc.sections or _fallback_sections(doc)
    claims: list[Claim] = []
    seen_texts: set[str] = set()

    for section in sections:
        if _is_boilerplate(section.title):
            continue
        text = (section.text or "").strip()
        if len(text) < 60:  # too short to carry a real claim
            continue

        try:
            result = llm.complete(
                _EXTRACT_PROMPT.format(
                    title=section.title or "(untitled)",
                    text=text[:6000],  # guard 7B context window
                    max_claims=_MAX_CLAIMS_PER_SECTION,
                ),
                schema=_ClaimList,
                system=_EXTRACT_SYSTEM,
            )
        except Exception:
            # A noisy/failed structured call must not sink the whole ingest.
            continue

        extracted = getattr(result, "claims", []) or []
        for ec in extracted[:_MAX_CLAIMS_PER_SECTION]:
            ctext = _clean_text(getattr(ec, "text", ""))
            if not ctext:
                continue
            key = ctext.lower()
            if key in seen_texts:  # de-dup across sections
                continue
            seen_texts.add(key)

            span = _locate_span(getattr(ec, "quote", "") or "", section, text)
            claims.append(
                Claim(
                    id=f"claim:{doc.source_slug}:{short_hash(ctext)}",
                    text=ctext,
                    source_slug=doc.source_slug,
                    source_span=span,
                    status="supported",
                    confidence=0.5,
                )
            )
    return claims


def flag_shaky(
    claims: list[Claim],
    doc: Doc,
    retriever: "Retriever",
    graph: "GraphStore",
    llm: LLMClient,
    settings: Settings,
) -> list[Claim]:
    """Flag shaky claims in place and return only the flagged subset.

    Runs three checks per claim (see module docstring). Mutates each ``Claim``'s
    ``status`` / ``rationale`` / ``evidence`` as appropriate. The returned list is
    the subset whose ``status`` ended up non-``supported`` OR which carries a
    human-review note in its rationale (Check B never changes status).

    All collaborators are duck-typed and optional-tolerant: if ``retriever`` is
    ``None`` or a search raises, that check is skipped for that claim rather than
    crashing the pipeline.
    """
    flagged: list[Claim] = []

    for claim in claims:
        note_added = False

        # --- Vagueness (cheap heuristic first; may short-circuit Check A) ----
        vague_reason = _vagueness_reason(claim.text)

        # --- Check A: unsupported-by-source (LLM, schema-constrained) --------
        # Only worth an LLM call if we can actually fetch the claim's context.
        context, ctx_citation = _claim_source_context(claim, doc, retriever)
        if context:
            verdict = _judge_support(claim, context, llm)
            if verdict is not None:
                v = verdict.verdict.strip().lower()
                if v in ("unsupported-by-source", "unsupported"):
                    claim.status = "unsupported-by-source"
                    claim.rationale = _compose_rationale(
                        claim.rationale,
                        f"Source-check: {verdict.rationale.strip() or 'not grounded in the cited source context.'}",
                    )
                    claim.evidence.append(_verdict_citation(verdict, claim, ctx_citation))
                    note_added = True
                elif v == "overstated":
                    # "overstated" is a flavour of vagueness in our status enum —
                    # the claim says more than the source warrants.
                    claim.status = "vague"
                    claim.rationale = _compose_rationale(
                        claim.rationale,
                        f"Overstated vs. source: {verdict.rationale.strip() or 'source is weaker/more hedged than the claim.'}",
                    )
                    claim.evidence.append(_verdict_citation(verdict, claim, ctx_citation))
                    note_added = True

        # --- Vagueness: apply only if Check A didn't already demote it --------
        if claim.status == "supported" and vague_reason:
            claim.status = "vague"
            claim.rationale = _compose_rationale(claim.rationale, f"Vague: {vague_reason}")
            note_added = True

        # --- Check B: contradicts-KB (HIGH-PRECISION STUB — note only) -------
        kb_note = _kb_contradiction_note(claim, retriever)
        if kb_note is not None:
            note_text, kb_citation = kb_note
            claim.rationale = _compose_rationale(claim.rationale, note_text)
            if kb_citation is not None:
                claim.evidence.append(kb_citation)
            note_added = True
            # NOTE: we deliberately do NOT set status='contradicts-KB'. A 7B model
            # (or a similarity heuristic) must not auto-assert a KB contradiction.

        if claim.status != "supported" or note_added:
            flagged.append(claim)

    return flagged


def write_review_queue(flagged: list[Claim], out_dir: Path) -> Path:
    """Write a markdown checklist of shaky claims to ``out_dir``.

    ``out_dir`` is normally ``settings.review_dir``. The file is grouped by claim
    status, each entry a ``- [ ]`` checkbox with the claim text, rationale, and
    both-side citations (source span + any KB neighbour). Returns the file path.

    The queue *never asserts truth* — every entry is framed as "needs a human".
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    source_slug = flagged[0].source_slug if flagged else "unknown"
    out_path = out_dir / f"review-{slug_for(source_slug)}.md"

    lines: list[str] = []
    lines.append(f"# Claim review queue — `{source_slug}`")
    lines.append("")
    lines.append(
        "> Machine-flagged claims that need a human decision. "
        "Nothing here is asserted true or false — these are *candidates* for review."
    )
    lines.append("")
    lines.append(f"**{len(flagged)} claim(s) flagged.**")
    lines.append("")

    if not flagged:
        lines.append("_No shaky claims flagged._")
        out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return out_path

    # Group by status for scannability; "supported-but-noted" (Check B) last.
    buckets: dict[str, list[Claim]] = {}
    for c in flagged:
        key = c.status if c.status != "supported" else "supported (KB-neighbour note)"
        buckets.setdefault(key, []).append(c)

    status_order = [
        "unsupported-by-source",
        "contradicts-KB",
        "vague",
        "supported (KB-neighbour note)",
    ]
    ordered_keys = [k for k in status_order if k in buckets]
    ordered_keys += [k for k in buckets if k not in ordered_keys]

    for key in ordered_keys:
        lines.append(f"## {key} ({len(buckets[key])})")
        lines.append("")
        for c in buckets[key]:
            lines.append(f"- [ ] **{_escape_md(c.text)}**")
            lines.append(f"  - id: `{c.id}` · confidence: {c.confidence:.2f}")
            if c.rationale:
                lines.append(f"  - rationale: {_escape_md(c.rationale)}")
            for cit in _dedup_citations(c.evidence):
                lines.append(f"  - evidence: {_format_citation(cit)}")
            if c.source_span:
                lines.append(
                    f"  - source span: `{c.source_slug}` chars "
                    f"{c.source_span[0]}–{c.source_span[1]}"
                )
            lines.append("")
        lines.append("")

    out_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return out_path


# --------------------------------------------------------------------------- #
# Check A helpers
# --------------------------------------------------------------------------- #

def _claim_source_context(
    claim: Claim, doc: Doc, retriever: Optional["Retriever"]
) -> tuple[str, Optional[Citation]]:
    """Best-effort retrieval of the source text a claim was drawn from.

    Strategy: (1) if we have a ``source_span``, slice it (plus a window) straight
    out of the doc markdown — exact and free. (2) Otherwise fall back to a
    hybrid-search restricted to the claim's own source.
    Returns ``(context_text, citation)`` or ``("", None)`` if nothing usable.
    """
    # (1) Exact span window from the parsed doc — most reliable.
    if claim.source_span and doc.markdown:
        start, end = claim.source_span
        lo = max(0, start - 200)
        hi = min(len(doc.markdown), end + 200)
        window = doc.markdown[lo:hi].strip()
        if window:
            quote = doc.markdown[start:end].strip()[:400] or None
            return window, Citation(
                source_slug=claim.source_slug,
                char_span=(lo, hi),
                quote=quote,
            )

    # (2) Hybrid search within the same source.
    if retriever is not None:
        try:
            hits = retriever.hybrid_search(claim.text, k=5)
        except Exception:
            hits = []
        same_source = [h for h in hits if getattr(h, "source_slug", None) == claim.source_slug]
        if same_source:
            top = same_source[0]
            ctx = "\n\n".join(h.text for h in same_source[:3] if getattr(h, "text", ""))
            return ctx, Citation(
                source_slug=claim.source_slug,
                char_span=getattr(top, "char_span", None),
                quote=(top.text[:300] if getattr(top, "text", "") else None),
            )

    return "", None


def _judge_support(claim: Claim, context: str, llm: LLMClient) -> Optional[_SupportVerdict]:
    """Ask the LLM (schema-constrained) whether ``context`` supports ``claim``."""
    try:
        return llm.complete(  # type: ignore[return-value]
            _SUPPORT_PROMPT.format(claim=claim.text, context=context[:5000]),
            schema=_SupportVerdict,
            system=_SUPPORT_SYSTEM,
        )
    except Exception:
        return None


def _verdict_citation(
    verdict: _SupportVerdict, claim: Claim, fallback: Optional[Citation]
) -> Citation:
    """Build a source-side citation for a Check-A verdict, preferring its quote."""
    quote = (verdict.quote or "").strip() or None
    if quote:
        return Citation(
            source_slug=claim.source_slug,
            char_span=(fallback.char_span if fallback else None),
            quote=quote[:400],
        )
    if fallback is not None:
        return fallback
    return Citation(source_slug=claim.source_slug)


# --------------------------------------------------------------------------- #
# Check B helper (high-precision stub — never sets a hard verdict)
# --------------------------------------------------------------------------- #

def _kb_contradiction_note(
    claim: Claim, retriever: Optional["Retriever"]
) -> Optional[tuple[str, Optional[Citation]]]:
    """Return a 'possible contradiction — human review' note, or ``None``.

    High precision: we only emit a note when a KB chunk from a *different* source
    sits above ``_KB_CONTRADICTION_SIM`` cosine similarity to the claim. We do NOT
    decide whether it actually contradicts — that's the human's job. Similarity is
    read off the hit's score if the retriever attaches one; otherwise we recompute
    cosine from embeddings if both are present; otherwise we conservatively skip.
    """
    if retriever is None:
        return None
    try:
        hits = retriever.hybrid_search(claim.text, k=8)
    except Exception:
        return None

    # Only neighbours from *other* sources can contradict this claim.
    neighbours = [h for h in hits if getattr(h, "source_slug", None) != claim.source_slug]
    if not neighbours:
        return None

    embedder = getattr(retriever, "embedder", None)
    best_hit = None
    best_sim = -1.0
    for h in neighbours:
        sim = _hit_similarity(h, claim, embedder)
        if sim is not None and sim > best_sim:
            best_sim, best_hit = sim, h

    if best_hit is None or best_sim < _KB_CONTRADICTION_SIM:
        return None

    cit = Citation(
        source_slug=getattr(best_hit, "source_slug", "unknown"),
        char_span=getattr(best_hit, "char_span", None),
        quote=(best_hit.text[:300] if getattr(best_hit, "text", "") else None),
    )
    note = (
        f"Possible contradiction — HUMAN REVIEW: a near-identical-topic KB chunk "
        f"(source `{cit.source_slug}`, similarity {best_sim:.2f}) covers the same "
        f"ground; a human should check whether it agrees or conflicts. "
        f"(No automatic contradicts-KB verdict is asserted.)"
    )
    return note, cit


def _hit_similarity(hit, claim: Claim, embedder) -> Optional[float]:
    """Pull or compute a cosine similarity in [0,1] for a retrieval hit.

    Prefers an attached score; else recomputes from embeddings; else ``None``.
    """
    # 1) retriever-attached score (RRF scores aren't cosine, so only trust an
    #    explicit cosine/sim attribute, not a generic 'score').
    for attr in ("similarity", "cosine", "_sim"):
        val = getattr(hit, attr, None)
        if isinstance(val, (int, float)):
            return _clamp01(float(val))

    # 2) recompute from embeddings if we can.
    hit_emb = getattr(hit, "embedding", None)
    if hit_emb is not None and embedder is not None:
        try:
            import numpy as np

            q = embedder.embed([claim.text])
            if q is None or len(q) == 0:
                return None
            qv = np.asarray(q[0], dtype=np.float32)
            hv = np.asarray(hit_emb, dtype=np.float32)
            denom = (np.linalg.norm(qv) * np.linalg.norm(hv))
            if denom == 0:
                return None
            return _clamp01(float(np.dot(qv, hv) / denom))
        except Exception:
            return None
    return None


# --------------------------------------------------------------------------- #
# Vagueness heuristic
# --------------------------------------------------------------------------- #

def _vagueness_reason(text: str) -> str:
    """Return a short reason string if the claim reads as vague, else ``""``.

    Heuristic, deterministic, no LLM:
      * a bare superlative ('state-of-the-art', 'best', ...) with no comparator;
      * heavy hedging with no concrete number/unit to anchor the claim.
    """
    low = text.lower()
    has_number = bool(re.search(r"\d", low))
    has_comparator = any(cue in low for cue in _COMPARATOR_CUES)

    # Bare superlative without a named comparator.
    for sup in _BARE_SUPERLATIVES:
        if sup in low and not has_comparator:
            return f"superlative '{sup}' with no named comparator/baseline"

    # Hedged + no quantity → unfalsifiable.
    hedges = [w for w in _HEDGE_WORDS if re.search(rf"\b{re.escape(w)}\b", low)]
    if hedges and not has_number:
        return f"hedged ('{hedges[0]}') with no quantity/unit to verify"

    return ""


# --------------------------------------------------------------------------- #
# Small utilities
# --------------------------------------------------------------------------- #

def _is_boilerplate(title: str) -> bool:
    t = (title or "").strip().lower()
    return any(b in t for b in _BOILERPLATE_SECTIONS)


def _fallback_sections(doc: Doc) -> list[Section]:
    """If a Doc has no sections, treat the whole markdown as one section."""
    md = doc.markdown or ""
    if not md.strip():
        return []
    return [Section(title=doc.title or "document", text=md, char_span=(0, len(md)))]


def _locate_span(quote: str, section: Section, section_text: str) -> Optional[tuple[int, int]]:
    """Find the verbatim quote inside the section to recover a doc char span.

    Returns absolute (doc-level) char offsets by adding the section's start.
    Falls back to the section's own span when the quote can't be located.
    """
    base = section.char_span[0] if section.char_span else 0
    q = (quote or "").strip()
    if q:
        idx = section_text.find(q)
        if idx == -1:  # try a looser, whitespace-normalized search
            idx = _loose_find(section_text, q)
        if idx != -1:
            return (base + idx, base + idx + len(q))
    return section.char_span if section.char_span else None


def _loose_find(haystack: str, needle: str) -> int:
    """Whitespace-insensitive substring search; returns index in haystack or -1."""
    norm_needle = re.sub(r"\s+", " ", needle).strip()
    if not norm_needle:
        return -1
    # Build a regex that tolerates arbitrary whitespace between tokens.
    pattern = r"\s+".join(re.escape(tok) for tok in norm_needle.split(" "))
    m = re.search(pattern, haystack)
    return m.start() if m else -1


def _clean_text(text: str) -> str:
    """Drop empty/degenerate LLM claim text; collapse whitespace."""
    t = re.sub(r"\s+", " ", (text or "")).strip()
    # Defensive against 7B noise: reject fragments and obvious non-claims.
    if len(t) < 12:
        return ""
    if t.lower().startswith(("see ", "table ", "figure ", "fig.", "section ")):
        return ""
    return t


def _compose_rationale(existing: str, addition: str) -> str:
    """Append a rationale note without losing prior notes."""
    existing = (existing or "").strip()
    addition = (addition or "").strip()
    if not existing:
        return addition
    if not addition or addition in existing:
        return existing
    return f"{existing} | {addition}"


def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else (1.0 if x > 1 else x)


def slug_for(text: str) -> str:
    """Local slug (avoids importing slugify for one call; keeps file self-contained)."""
    t = re.sub(r"[^a-zA-Z0-9]+", "-", text or "").strip("-").lower()
    return t or "review"


def _dedup_citations(citations: list[Citation]) -> list[Citation]:
    seen: set[tuple] = set()
    out: list[Citation] = []
    for c in citations:
        key = (c.source_slug, c.char_span, (c.quote or "")[:80])
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
    return out


def _format_citation(c: Citation) -> str:
    parts = [f"`{c.source_slug}`"]
    if c.char_span:
        parts.append(f"chars {c.char_span[0]}–{c.char_span[1]}")
    if c.quote:
        q = c.quote.strip().replace("\n", " ")
        if len(q) > 160:
            q = q[:157] + "…"
        parts.append(f'"{_escape_md(q)}"')
    return " — ".join(parts)


def _escape_md(text: str) -> str:
    """Light markdown escaping so claim text doesn't break the checklist."""
    return (text or "").replace("\n", " ").replace("|", "\\|").strip()
