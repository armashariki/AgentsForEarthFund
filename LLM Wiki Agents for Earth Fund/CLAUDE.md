# LLM Wiki — Maintainer Schema

This file is the **schema**: the configuration that turns a generic LLM agent into a
disciplined maintainer of this wiki. Read it in full at the start of every session before
ingesting, querying, or linting. It is co-evolved by the human and the agent over time —
when we discover a convention that works, we write it down here.

This instance implements the **LLM Wiki** pattern (Karpathy): the agent incrementally builds
and maintains a persistent, interlinked knowledge base that sits between the human and the
raw sources. Knowledge is **compiled once and kept current**, not re-derived from raw chunks
on every query (that would be plain RAG). The wiki is a **compounding artifact**.

---

## The three layers

1. **`raw/` — raw sources. IMMUTABLE. Source of truth.**
   Articles, papers, PDFs, reports, transcripts, data files, images (`raw/assets/`).
   You READ from here. You **never** modify, rename, or delete anything in `raw/`.
   Every wiki claim must trace back to a source here (or to a logged web lookup).

2. **`wiki/` — the wiki. LLM-OWNED. You write all of this.**
   Markdown pages: source summaries, entity pages, concept pages, topic syntheses,
   comparisons, filed-back analyses, plus `overview.md`, `index.md`, `log.md`.
   The human reads it; you write and maintain it. Keep it internally consistent.

3. **This `CLAUDE.md` — the schema.** Conventions + workflows. Co-evolved.

**Hard rule:** never write into `raw/`. Never invent facts. If a claim has no source, label it
`[unverified]` or do a web lookup and log it. Prefer flagging a contradiction over silently
overwriting a prior claim.

---

## Directory layout

```
raw/                 immutable sources (you only read)
  assets/            downloaded images referenced by sources
wiki/
  overview.md        the top-level evolving synthesis (read this second, after index)
  index.md           catalog of every page, grouped by category (read this first)
  log.md             append-only chronological record (ingests, queries, lints)
  sources/           one summary page per ingested source
  entities/          people, orgs, grantees, funds, places, products, projects
  concepts/          ideas, methods, mechanisms, frameworks, metrics
  topics/            higher-level syntheses that span many sources/entities
  analyses/          good query answers filed back as durable pages
  _templates/        page templates — copy these for new pages
tools/               optional local CLI/search tooling (see "Search" below)
```

## Naming conventions

- Filenames: `kebab-case.md`. Source pages: `YYYY-MM-DD-short-slug.md` (date = ingest date).
- One canonical page per real-world entity/concept. Pick **one** canonical name; record
  alternates in frontmatter `aliases:` so future sessions don't create duplicates.
- Before creating any new page, **search the wiki for an existing one** (`index.md` first,
  then grep titles/aliases). Duplicate pages are the #1 way this wiki rots. Merge, don't fork.

## Page format

Every wiki page starts with YAML frontmatter, then body using `[[wikilinks]]` for cross-refs.

```markdown
---
type: entity | concept | topic | source | analysis
title: Canonical Name
aliases: [Other Name, Acronym]
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: [2026-05-12-some-report, 2026-05-20-some-paper]   # source-page slugs
tags: [carbon-removal, due-diligence]
status: draft | maintained | example
confidence: high | medium | low
---

# Canonical Name

One-paragraph definition / what this is.

## Key points
- Claim. ^[[2026-05-12-some-report]]
- Claim that another source disputes. ^[[2026-05-20-some-paper]]

## Contradictions / open questions
- Source A says X; Source B says not-X. (flag, don't resolve silently)

## Related
- [[durable-carbon-removal]] · [[example-grantee-org]]
```

Frontmatter exists so that (a) future you can navigate fast, and (b) tooling (Obsidian
Dataview, a future search index, a future permissions layer) can query it. Always keep
`updated`, `sources`, and `status` current.

---

## Operation: INGEST

When the human drops a source into `raw/` and asks you to process it:

1. **Read** the source fully (for PDFs/images, read text first, then view key figures).
2. **Discuss** the key takeaways with the human briefly. Surface what's new vs. what the
   wiki already knows.
3. **Write a source summary** in `wiki/sources/YYYY-MM-DD-slug.md` — the durable record of
   what this source says, with the citable claims.
4. **Integrate** into the wiki: update/create the relevant `entities/` and `concepts/` pages.
   A single source typically touches **10–15 pages**. For each affected page: add the new
   claim, add the source to frontmatter `sources:`, bump `updated:`, fix cross-references.
   - **Entity resolution:** match new mentions to existing canonical pages via title +
     `aliases`. If unsure whether two things are the same, ask or flag — don't guess-merge.
   - **Contradictions:** if the new source contradicts an existing claim, add it to the
     page's "Contradictions / open questions" section with both citations. Update
     `overview.md` only if the synthesis genuinely shifts.
5. **Update `index.md`** — add the new pages, update one-line summaries of changed pages.
6. **Append to `log.md`** — one entry (format below).
7. **Report** to the human: what you created, what you changed, what contradicts, what's now
   worth investigating.

Default to **one source at a time with the human involved**. Batch-ingest (many sources, less
supervision) is allowed once the schema is mature — document the batch in a single log entry.

## Operation: QUERY

When the human asks a question:

1. Read `index.md` (and `overview.md` if the question is broad) to find candidate pages.
   *(At scale, use the search tool instead of reading the whole index — see "Search".)*
2. Drill into the relevant pages; follow `[[wikilinks]]`.
3. Synthesize an answer **with citations** back to source pages (and through them to `raw/`).
4. If the answer is novel and worth keeping (a comparison, a connection, an analysis), offer
   to **file it back** as `wiki/analyses/<slug>.md` and add it to `index.md` + `log.md`.
   Good answers should compound into the wiki, not vanish into chat history.
5. Output format fits the question: prose, a comparison table, a Marp slide deck, a chart.

## Operation: LINT

Periodically (or on request), health-check the wiki and propose fixes:

- **Contradictions** between pages that aren't yet flagged.
- **Stale claims** that newer sources have superseded (check `log.md` order).
- **Orphan pages** with no inbound `[[links]]`.
- **Missing pages** — concepts/entities mentioned often but lacking their own page.
- **Missing cross-references** — pages that should link to each other but don't.
- **Data gaps** — open questions that a web search or a new source could close.

Present findings as a checklist; apply fixes the human approves. Log a `lint` entry.

---

## index.md and log.md

**`index.md` is content-oriented** — the catalog. Grouped by category (overview, topics,
entities, concepts, sources, analyses). Each entry: a `[[link]]`, a one-line summary, and
optionally `updated` date / source count. Update it on **every** ingest. Read it first when
answering a query. This is the navigation backbone **until** the wiki outgrows it (see Scaling).

**`log.md` is chronological** — append-only. Start every entry with a consistent, greppable
prefix so unix tools work:

```
## [YYYY-MM-DD] ingest | Source Title  →  touched: 12 pages
## [YYYY-MM-DD] query  | "the question asked"  →  filed: analyses/slug.md
## [YYYY-MM-DD] lint   | 3 contradictions, 2 orphans  →  4 fixes applied
```

`grep "^## \[" wiki/log.md | tail -5` then gives the last five events.

## Search (optional, grows with scale)

At small scale, reading `index.md` is enough — no embeddings needed. As the wiki grows you'll
want real search over `wiki/`. Karpathy suggests **qmd** (local hybrid BM25+vector search over
markdown, with a CLI and an MCP server). When a search tool exists in `tools/`, prefer it over
reading the whole index for query/ingest lookups. Until then, use `grep`/title search.

---

## Scaling notes (this instance targets ENTERPRISE scale: 1k–10k docs)

The vanilla pattern is tuned for ~100 sources / hundreds of pages, where a **flat `index.md`**
fits in context. This instance is meant to grow past that. The known breakpoints and the
planned responses (to be finalized by the build-vs-buy research; see `README.md` → Scaling):

1. **Flat index stops fitting (~150–300 pages).** → Move to a **hierarchical index**: a small
   top-level `index.md` that links to per-category sub-indexes (`entities/_index.md`, etc.),
   and/or stand up the search tool so you stop reading the index wholesale.
2. **Ingest fan-out consistency (thousands of pages).** → Strict entity resolution +
   `aliases`; consider a property/knowledge-graph layer; never guess-merge.
3. **Lint becomes combinatorial.** → Scope lint by category/recency; let tooling pre-filter
   candidate contradictions before the agent reasons over them.
4. **Multi-user, permissions, SSO, audit.** → The markdown core stays; a retrieval +
   **permission-aware** backend (and access control on derived/synthesized pages) gets added
   underneath. This is the genuinely hard enterprise part and is the subject of the research.

Until those are in place, keep the wiki disciplined and forward-compatible: clean frontmatter,
canonical naming, tight cross-refs. A messy small wiki cannot be scaled; a clean one can.

## Guardrails

- `raw/` is read-only. Always.
- No unsourced claims. Cite or mark `[unverified]`.
- Flag contradictions; don't silently overwrite.
- Search before you create (avoid duplicate pages).
- Keep `index.md` and `log.md` current on every operation.
- When you change >5 pages in one pass, summarize the changes for the human.

---

## Domain layer: AI-innovation assessment for climate AND nature (v3)

This wiki's domain is **AI for climate AND nature** (co-equal — never let "climate" stand in for both).
When you ingest a paper / tool / model / proposal, apply the **six-lens assessment** from
[[bef-ai-knowledge-model]] — the standing ingest rule that makes the wiki read like a head of AI, not a
summarizer. Judge **real, cutting-edge AI that credibly advances a climate or nature challenge** — NOT
program/funding fit (that belongs to the program directors).

**The six lenses** (apply those that fit the item; record which you skip and why — OECD "lenses, not a checklist"):
1. **Innovation & invention** (real advance vs. AI-washing) · 2. **Technical rigor** (claims vs. evidence,
reproducible) · 3. **Frontier & landscape positioning** (vs. SOTA / who else — see
[[ai-for-climate-and-nature-landscape]]) · 4. **Evidence it's working & traction** (deployed? maturity/TRL) ·
5. **AI suitability / leverage** (uniquely suited, or forced?) · 6. **Climate/nature outcome & credibility**
(real & measured vs. hype — climate: additionality/MRV; nature: **non-fungible** → data protocols +
indicator basket + **independent verification**; + climate–nature trade-offs). Plus **Responsible AI &
footprint** (own energy cost, equity/justice, dual-use, data governance, Indigenous data sovereignty).
**Gating flags** that sink an item: *not real innovation*; *environmental benefit not credible.*

**Ontology → where pages live:**
- `assessments/` — an **Assessment** (verdict: cutting-edge / promising / derivative / not-credible / watch).
- `theses/` — a **Thesis** (a position BEF holds on AI capability for climate/nature) + confidence.
- `entities/` — **Organizations/Labs** and **Tools/Systems**.
- `concepts/` — **Methods/Approaches** and **Benchmarks**.
- `topics/` — landscape syntheses (the [[ai-for-climate-and-nature-landscape|frontier map]]).
- `_templates/` — `assessment` · `thesis` · `paper` · `organization` · `method` · `benchmark` (+ generic ones).

**Capture:** the agent drafts the Assessment from the source; the human approves. Outcomes (did the approach
pan out) and Theses are human-approved. Keep it light — purpose-selected lenses only.

**Deferred landscape backlog (revisit later — ONLY these three; all other gaps de-scoped):**
Global South & China conservation/climate AI · eDNA + ML · conservation genomics.
