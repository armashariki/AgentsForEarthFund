---
type: analysis
title: Scaling the LLM Wiki to Enterprise — Build vs Buy
aliases: [Enterprise Scaling Research, Build vs Buy]
created: 2026-06-05
updated: 2026-06-05
sources: []   # external research (cited inline); this page is meta about the wiki itself
tags: [architecture, enterprise, graphrag, permissions, research]
status: maintained
confidence: medium
---

# Scaling the LLM Wiki to Enterprise — Build vs Buy

> Filed-back research answer. Demonstrates the "good answers become wiki pages" loop.
> Based on a deep-research pass (27 sources fetched, 120 claims extracted, 25 adversarially
> verified, 20 confirmed / 5 killed). Confidence is annotated per section. **The single most
> important caveat is at the bottom — read it.**

## Question

How do we take Karpathy's LLM Wiki (a compile-once, persistent, interlinked markdown synthesis
that works to ~100 docs) and scale it to **1,000–10,000 documents**, **org-wide**, with
**document-level permissions, SSO, and audit**, **self-hosted/local-first** preferred?

## Bottom line (verdict)

**Hybrid: buy the plumbing, build the brain.** No single self-hostable product delivers all
three of (a) a **compounding synthesis** (the Karpathy property), (b) **document-level ACL
propagation into derived pages**, and (c) **self-hosting at 1k–10k docs**. So:

- **Build** the synthesis layer with a **GraphRAG-family engine** (the only thing that actually
  preserves "compile knowledge once" at scale) — start from **nano-graphrag** (hackable) or
  **LazyGraphRAG** (cost-optimal).
- **Buy/adopt** the enterprise plumbing — permissions, SSO, audit, connectors — from **Onyx**
  (self-hostable, MIT core; the permission features are paid Enterprise Edition). Don't build
  IAM/SSO/audit from scratch; it's a tar pit.
- **Design around** the one genuinely unsolved problem: **propagating per-document permissions
  into LLM-synthesized pages.** No surveyed system does this. Mitigate with permission-tiered
  synthesis (below), and treat org-wide-with-permissions as the *last* phase, not the first.

The markdown wiki you already have (this repo) stays as the **human-facing artifact** the whole
way up. It is forward-compatible with everything below.

## The finding that determines everything

The market splits cleanly into two camps, and **neither camp alone is the LLM Wiki**:

| Camp | Examples | Has compounding synthesis? | Has enterprise permissions? |
|---|---|---|---|
| **Synthesis engines** | Microsoft GraphRAG, LightRAG, nano-graphrag, Cognee | ✅ Yes — this is the Karpathy property | ❌ No permissions/SSO/audit |
| **Permission-aware search** | Onyx, RAGFlow, Glean, NotebookLM Ent. | ❌ No — re-derives per query (RAG) | ✅ (varies) |

Karpathy's idea lives in the **top-left** (compile a persistent synthesis). Enterprise
requirements live in the **bottom-right** (permissions/SSO/audit). **The whole engineering
problem is joining these two rows** — and the join (ACLs into synthesized content) is the
unsolved part. This is *why* the answer is a hybrid and not a single tool.

## Build-vs-buy scorecard

Scored for **this** user: self-hosted-preferred, org-wide + permissions/SSO/audit, 1k–10k DD/
research docs, hands-on solo-ish builder. ✅ strong · ◐ partial/caveated · ❌ no/weak.

| Option | Self-host | Scales 1k–10k | Compounding synthesis (Karpathy) | Doc perms + SSO + audit | Maturity | Effort to adopt |
|---|---|---|---|---|---|---|
| **Markdown wiki alone** (this repo, Phase 0) | ✅ | ❌ caps ~100–150 | ✅✅ *is* the synthesis | ❌ | n/a (just files+agent) | ✅ done |
| **nano-graphrag** (fork & build) | ✅ | ◐ recompute/entity-res limits | ✅✅ | ❌ | ◐ ~1.1k LOC, MIT, last rel. Oct 2024 | ◐ medium |
| **LightRAG** | ✅ | ◐ set-merge insert; weak entity dedup | ✅✅ dual-level | ❌ | ✅ active (EMNLP 2025) | ◐ medium |
| **LazyGraphRAG** (MS GraphRAG lib) | ✅ | ✅ cheap index, query-time cost | ✅ (query-time) | ❌ | ◐ newer | ◐ medium |
| **Cognee** | ✅ | ◐ | ✅ memory graph | ❌ | ❌ immature (no connectors/certs) | ◐ medium |
| **Onyx Community (free MIT)** | ✅ | ✅ | ❌ RAG, not synthesis | ◐ basic; **doc-level RBAC is EE-only** | ✅ high | ✅ low |
| **Onyx Enterprise (paid)** | ✅ | ✅ | ❌ RAG, not synthesis | ✅✅ ACL mirror + SSO/SAML/SCIM | ✅ high | ◐ medium + license |
| **RAGFlow** | ✅ | ✅ | ◐ added GraphRAG mode | ◐ some team features | ✅ active | ◐ medium |
| **Glean** (commercial) | ❌ cloud | ✅✅ | ◐ knowledge graph, mostly perm-search | ✅✅ | ✅ high | ✅ low (but $$$, not local) |
| **Hebbia / Rogo** (commercial, finance/DD) | ❌ cloud | ✅ | ◐ agentic over docs, not a maintained wiki | ✅ | ✅ | ◐ ($$$, not local) |
| **NotebookLM Enterprise** (Google) | ❌ GCP | ◐ per-notebook | ◐ per-notebook, not org wiki | ✅ GCP IAM | ✅ | ✅ (not local, not a wiki) |
| **Microsoft Viva Topics** | ❌ | — | was the closest to "auto-wiki" | ✅ | ❌ **RETIRED** | ❌ don't adopt |
| **★ Hybrid (Onyx EE + GraphRAG synthesis + this wiki)** | ✅ | ✅ | ✅✅ | ◐ retrieval ✅, derived-page ACL ❌ unsolved | ◐ integration risk | ❌ high — the target |

## Path A — BUILD: what actually preserves the Karpathy property

**GraphRAG-family engines are the real-world implementation of "compile knowledge once."**
Microsoft GraphRAG extracts entities/relationships, runs **hierarchical Leiden community
detection**, and writes **bottom-up community summaries** where higher-level summaries
recursively fold in lower-level ones — a *persistent indexed artifact*, not per-query work.
[arXiv:2404.16130](https://arxiv.org/html/2404.16130v2) *(verified 3-0)*. That is structurally
the same move as Karpathy's "entity pages + concept pages + an overview that already reflects
everything," just done with graph clustering instead of an agent editing markdown.

The four build-path candidates that genuinely compound a synthesis:

- **nano-graphrag** — ~1,100 LOC, MIT, built because official GraphRAG is "difficult/painful to
  read or hack." Persists a reloadable graph; incremental insert with md5 dedup. **Most forkable
  starting point.** [repo](https://github.com/gusye1234/nano-graphrag) *(3-0; incremental 2-1).*
  ⚠️ Last release **Oct 2024** (~1.5 yrs stale in a fast field).
- **LightRAG** — graph index + **dual-level retrieval** (specific entities + abstract themes);
  merges new docs via set-merging (no full reprocess). Active (EMNLP 2025).
  [site](https://lightrag.github.io/) · [repo](https://github.com/HKUDS/LightRAG) *(6,7: 3-0).*
- **LazyGraphRAG** — **cost-optimal.** Indexing cost = **plain vector RAG (~0.1% of full
  GraphRAG)** because it defers all LLM work to query time and uses NLP noun-phrase extraction
  instead of LLM entity extraction. Microsoft self-reports **>700× lower global-query cost** at
  comparable quality. [MS Research](https://www.microsoft.com/en-us/research/blog/lazygraphrag-setting-a-new-standard-for-quality-and-cost/)
  *(0.1%/mechanism 3-0; 700× is vendor benchmark, 2-1).* ⚠️ Index-cost-only — you **pay at query
  time** (cost scales with a relevance-budget knob).
- **Cognee** — Apache-2.0 "memory" engine: embeddings + KG + an add→cognify→improve pipeline
  with remember/recall/forget. [repo](https://github.com/topoteretes/cognee) *(17,18: 3-0).*
  ⚠️ Immature for enterprise: no connectors, no compliance certs, no published benchmarks.

**The scaling bottleneck you flagged is real and only PARTIALLY solved** *(this is the crux).*
Chunk-level dedup is cheap, but **nano-graphrag and vanilla GraphRAG re-run Leiden community
detection + LLM community-report generation across the whole graph on every insert** — exactly
the 10k-doc cost trap. LightRAG avoids full reprocessing via set-merge, **but its entity dedup
is exact-key matching** that misses `Donald J. Trump` vs `Donald Trump`-class duplicates and
lacks semantic/temporal conflict resolution (open issues #1323, #1631, #2528). So "incremental"
in this whole family means *"add without full re-chunk,"* **not** *"cheap delta-merge with
robust entity resolution."* Mitigations: prefer **LazyGraphRAG** (no upfront community
summaries to recompute), refresh communities **periodically (nightly batch)** rather than
per-insert, and bolt on a dedicated **entity-resolution / temporal layer** (Graphiti/Zep-style)
if entity drift hurts. *(claims 4,5,7 — high confidence.)*

**Rough cost envelope at 10k docs (≈10M–200M tokens) — ORDER OF MAGNITUDE, EXTRAPOLATED:**
full-GraphRAG-style indexing with a cheap model is plausibly **hundreds to low-thousands of
dollars per full rebuild** (much more with a frontier model, and you pay it *again* on naive
re-index); **LazyGraphRAG keeps indexing near-free (~embeddings only) and shifts spend to query
time.** The "GraphRAG cost cliff" (indexing costs fell ~1000× in 18 months as models cheapened)
is real but directional. **Treat all 10k-doc numbers as estimates** (see caveat).

## Path B — BUY/ADOPT: the permission-aware side

- **Onyx (formerly Danswer)** — the strongest **self-hostable backbone**. MIT Community Edition
  (chat/RAG/agents), Docker/K8s/Helm/Terraform, can run airgapped, **mirrors document-level
  ACLs** from source systems (Drive/Salesforce/Confluence/SharePoint…), SSO via
  **OAuth/OIDC/SAML** + **SCIM** group provisioning.
  [repo](https://github.com/onyx-dot-app/onyx) · [access controls](https://docs.onyx.app/security/architecture/access_controls)
  *(self-host/MIT/SSO/perm-mirror 3-0).* **Two load-bearing caveats:** (1) **document-level RBAC
  and permission-sync are paid Enterprise Edition, NOT in the free MIT build** *(3-0)* — the
  "free self-hosted" framing does not give you the permissions story for free; (2) Onyx is
  **permission-aware RAG, not a synthesis/wiki engine** — it does not produce the compounding
  artifact. *(This is precisely why it's the backbone, not the whole answer.)*
- **RAGFlow** — Apache-2.0, self-hostable, **excellent deep-document parsing** (great for messy
  PDFs/DD docs); has added a GraphRAG mode and some team features. Best slotted as the
  **ingestion/parsing component**, not the synthesis brain or the permissions backbone.
  [repo](https://github.com/infiniflow/ragflow). *(Note: earlier "it has no GraphRAG / no
  permissions" claims were adversarially **refuted** — it has been adding both.)*
- **Commercial (cloud; not local)** — **Glean** is the category leader in permission-aware
  "work AI" with a knowledge graph, but it's cloud and enterprise-priced, and is mostly
  permission-aware *search*, not a maintained Karpathy synthesis.
  [ref](https://futurumgroup.com/insights/glean-doubles-arr-to-200m-can-its-knowledge-graph-beat-copilot/)
  **Hebbia / Rogo** are finance/DD-specific (very on-point for a fund's due-diligence work) but
  cloud, pricey, and agentic-over-docs rather than a compounding wiki.
  **NotebookLM Enterprise** (Google/GCP) is per-notebook, IAM-gated, not an org wiki.
- **Microsoft Viva Topics** — was the *closest commercial thing to an auto-maintained wiki of
  "topics," but it is being **RETIRED**.* Microsoft folded the bet into Copilot/SharePoint.
  [reworked](https://www.reworked.co/knowledge-findability/viva-topics-is-dead-long-live-topics/) ·
  [MS docs](https://learn.microsoft.com/en-us/microsoft-365/topics/changes-coming-to-topics).
  **Signal:** even Microsoft couldn't make the always-on auto-wiki pay off as a product — a
  caution that the maintenance economics are the hard part (which is exactly Karpathy's bet that
  LLMs finally make maintenance ~free).

## The one genuinely unsolved problem (read this)

**Propagating per-document permissions into LLM-DERIVED / synthesized pages is unsolved across
ALL surveyed evidence.** Retrieval-layer permissioning is solved (Onyx mirrors source ACLs; the
academic "permission-aware RAG" work validates IDs against IAM at query time —
[arXiv:2504.13425](https://arxiv.org/pdf/2504.13425), IEEE permission-aware RAG). **But once an
LLM writes an `overview.md` or a GraphRAG community summary that fuses a public report with a
restricted DD memo, the derived page has no coherent owner-set.** No product or paper
demonstrably solves ACL inheritance through synthesis. *(claims 10,11,12 — high confidence.)*

Practical ways to design around it (none free):
1. **Permission-tiered synthesis** — maintain separate synthesis layers per security boundary
   (e.g., `public/`, `internal/`, `restricted/`). A user sees the synthesis for tiers they can
   access. Synthesis never crosses a tier boundary. Simple, robust, costs N× synthesis.
2. **Least-common-denominator synthesis + gated drill-down** — synthesis pages stay at the
   lowest permission level; the *raw drill-down* (citations into `raw/`) is permission-checked.
   The synthesis may omit restricted specifics.
3. **Regenerate-on-scope** — generate a synthesis view per querying user's permission set at
   query time (expensive; closer to RAG; loses the "compiled once" benefit).

For an environmental fund, **tiered synthesis (#1)** is usually the sane default.

## Recommendation — phased local build-out

Each phase delivers standalone value; stop wherever the ROI flattens.

- **Phase 0 — Markdown LLM Wiki (DONE).** This repo. `CLAUDE.md` schema + `raw/`→`wiki/`
  structure + Obsidian. Works to ~100–150 docs. *Use it now; ingest real sources.*
- **Phase 1 — Break the flat-index ceiling (days).** Add **hybrid search** over `wiki/` so the
  agent stops reading the whole index: **[qmd](https://github.com/tobi/qmd)** (local BM25+vector
  +rerank, has CLI **and** MCP — Karpathy's own suggestion) → put it in `tools/`, update
  `CLAUDE.md` "Search." Split `index.md` into per-category sub-indexes. Now comfortable to
  **~1,000 docs**, still local, still single/few-user. **Cheapest, highest-leverage step.**
- **Phase 2 — Add the synthesis engine for thousands (weeks).** Stand up a **GraphRAG-family
  engine over `raw/`** to generate/refresh the higher-level pages (overview, topic pages,
  community summaries) and write them back as wiki pages. Start **LazyGraphRAG** (cost) or fork
  **nano-graphrag** (control); run **incremental ingest as a nightly batch**, not per-document;
  add an entity-resolution pass if drift bites. This restores "compile-once synthesis" at
  **1k–10k docs**. Store vectors in **pgvector/Qdrant**; rerank with a small cross-encoder.
- **Phase 3 — Enterprise: org-wide + permissions + SSO + audit (months).** Put **Onyx
  (Enterprise Edition)** underneath as the permission-aware retrieval + SSO/SAML + audit +
  connectors backbone; the GraphRAG synthesis + markdown wiki sit on top as the
  compounding-knowledge layer Onyx lacks. Implement **permission-tiered synthesis** to handle
  the unsolved ACL-into-derived-pages problem. **This is the genuinely hard, frontier phase** —
  re-evaluate buy options (Glean; a managed GraphRAG; Onyx EE license cost) before committing
  engineering months here.

**Repos to start from:** [nano-graphrag](https://github.com/gusye1234/nano-graphrag) ·
[LightRAG](https://github.com/HKUDS/LightRAG) ·
[GraphRAG/LazyGraphRAG](https://github.com/microsoft/graphrag) ·
[Onyx](https://github.com/onyx-dot-app/onyx) · [qmd](https://github.com/tobi/qmd) ·
[RAGFlow](https://github.com/infiniflow/ragflow) (parsing) ·
[Cognee](https://github.com/topoteretes/cognee) (memory option).

## Caveats (the research was explicit about these)

- **Scale is extrapolated.** No surveyed primary source demonstrates GraphRAG-family behavior at
  1k–10k docs (10M–200M tokens). The canonical GraphRAG paper tops out at **~1.7M tokens — ~2
  orders of magnitude below your target.** Every 10k-doc cost/quality figure here is an
  estimate, not a measurement. *(claim 9, 3-0.)*
- **Vendor numbers.** LazyGraphRAG's 0.1% indexing and 700× query-cost figures are Microsoft
  self-reported; the 700× was the one split verification vote.
- **"Incremental" is overstated.** nano-graphrag's "no duplicated computation" dedups chunks but
  recomputes communities/reports each insert — the costly part.
- **Onyx permissions cost money.** The exact features you need (doc-level RBAC, permission-sync)
  are paid EE, not the free MIT build.
- **Coverage gaps.** Glean, Credal, Hebbia, Rogo, Microsoft Copilot, Google Agentspace, RAPTOR,
  Zep/Graphiti, Letta/MemGPT, Mem0, Khoj, Reor, qmd were in scope but produced **no surviving
  verified claims** in this batch — their absence is "unverified here," **not** "judged
  unsuitable." Worth a follow-up pass, especially Hebbia/Rogo for DD and Graphiti for entity
  resolution.

## Open questions (highest-value follow-ups)

1. Can Onyx EE's document ACLs actually be propagated into GraphRAG community summaries, or must
   derived pages be regenerated per permission scope? **(The gating unknown for the whole
   pattern at enterprise scale.)**
2. Real measured indexing $ and wall-clock for a GraphRAG engine on a genuine 10k-doc DD corpus?
3. Do any unevaluated commercial tools (Hebbia/Rogo/Glean/Credal-in-VPC) deliver maintained
   synthesis **with** permission propagation — which would flip parts of this to "buy"?
4. Is a Graphiti/Zep-style delta-merge + entity-resolution layer cheaper than just adopting
   LazyGraphRAG and eating query-time cost?

## Related
- [[overview]] · `CLAUDE.md` → Scaling notes · `README.md` → Scaling
