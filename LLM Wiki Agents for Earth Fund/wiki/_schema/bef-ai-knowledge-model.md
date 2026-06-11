---
type: schema
title: BEF AI-Knowledge Model — Innovation Assessment Lens (v3)
status: draft-for-review
created: 2026-06-06
updated: 2026-06-06
owner: Head of AI, Bezos Earth Fund
supersedes: v2 (grant-evaluation framing)
---

# BEF AI-Knowledge Model — Innovation Assessment Lens (v3)

**Purpose (reframed).** This layer judges one thing: **is this *real, cutting-edge AI innovation* that
credibly advances a climate or nature challenge — and how does it sit against the field?** It is a
**technology-assessment lens**, not a funding decision.

**Division of labor (explicit).** This layer = *technical innovation + credibility + landscape* — the
head-of-AI's lens. **Program / portfolio / funding fit belongs to the program directors** and is
deliberately **out of scope here.** Accordingly, v3 **removes** the v2 grant-evaluation machinery —
BEF program-fit criteria, the cost-effectiveness "bar," ITN cause-prioritization, and the OECD-DAC
program tier (only its *coherence* lens survives, for trade-offs). What it keeps and sharpens:
**innovation, frontier positioning, evidence it works, AI leverage, environmental-claim credibility,
responsible AI.**

**Evidence basis & tags.** From a deep-research pass (27 sources, 24/25 claims adversarially verified)
+ direct source grounding. **✓verified** = 3-0 adversarial · **·sourced** = single authoritative
source · **[to-confirm]** = named, not yet grounded. Gaps marked, not hidden.

---

## Design principle (authoritative, kept from v2)

**Lenses, not a checklist.** OECD's own guidance: evaluation criteria are "a set of complementary
lenses, not a checklist… not to be used in a mechanistic way" — **apply the lenses that fit the item**
(a paper, a tool, a proposed capability each draw a different subset) and **record which you skipped and
why.** Guardrail: purpose-driven selection, *not* cherry-picking the easy ones. ✓verified *(OECD 2021).*
→ This is the authoritative basis for "rigorous but **not** bureaucratic."

---

## The assessment — six lenses

### 1 · Innovation & invention
Is this a **genuine advance**, or derivative / "AI-washing"? Novel method, architecture, dataset, or
application; what it actually invents vs. repackages. *Grounding: NIH Factor 1 "Significance &
Innovation"; NSF "Intellectual Merit." ·sourced.*
- **Strong:** a real methodological or applied first; extends or beats prior art.
- **Concern:** thin wrapper on an existing model; "we used an LLM" as the whole novelty.

### 2 · Technical soundness & rigor
Do the **claims match the evidence**? Method validity, baselines, ablations, reproducibility,
benchmarks, honest failure modes. *Grounding: NIH Factor 2 "Rigor & Feasibility (Approach)." ·sourced.*
- **Concern:** cherry-picked results, no baseline, irreproducible, benchmark-gaming.

### 3 · Frontier & landscape positioning  *(the lens you elevated)*
**Where does this sit against the state of the art, and who else is working on it?** Ahead of / at /
behind the frontier; what it beats or extends; is the space a **real gap or crowded**; which labs,
companies, open-source efforts, and funders are active. This is how "cutting-edge / what's working /
how others are thinking about AI for climate & nature" gets answered.
*Grounding: Rolnick et al. 2019 / Climate Change AI "high-leverage" field map as the reference taxonomy
[to-confirm tags] + the system's own accumulating landscape memory (Organizations / Benchmarks / Methods
tracked over time). Now grounded by [[ai-for-climate-and-nature-landscape]] — 3 research passes, ~48 verified claims, maturity-tiered for both pillars; refresh it as the field moves.*
- **Strong:** demonstrably advances the frontier; clearly differentiated; fills a recognized gap.
- **Concern:** reinvents something mature/open-source; unaware of obvious prior work.

### 4 · Evidence it's working & traction  *("what is working, what is successful")*
Beyond claims: **benchmarks beaten, pilots, deployments, adoption, measured real-world results.** Plus
**maturity/TRL & infrastructure fit** — readiness vs. the ask, and what compute/data/infrastructure it
needs vs. what exists.
- **Strong:** real deployments or SOTA results; clear path from lab to field on existing infrastructure.
- **Concern:** notebook-only; demands infrastructure that doesn't exist; "pilot" with no outcomes.

### 5 · AI suitability / leverage
Is **AI genuinely the right, high-leverage tool** for this climate-or-nature problem — or is it forced
("AI for its own sake")? *Grounding: Rolnick/CCAI "high-leverage"; the substance of BEF's "Suitability"
criterion, relocated here. ·sourced.*
- **Concern:** a problem solved better by sensors/policy/known methods, with AI bolted on for novelty.

### 6 · Climate / nature outcome & credibility  *(kept as a reality check — co-equal pillars, different machinery)*
Does it **credibly advance a real climate OR nature challenge**, and is the environmental claim **real and
measured vs. hype**? *Not credit/grant due-diligence — a credibility filter to tell a real solution from
greenwashing / biodiversity-washing.*

- **Materiality** — does it address a substantive climate or nature challenge at all?
- **CLIMATE credibility (carbon is fungible — judge the number):** additionality + MRV + permanence
  (Oxford Principles 2024 ✓); score MRV confidence with **CarbonPlan VCL 1–5** (Impact × Type ×
  Responsibility) ✓; watch the **four greenwashing failure modes** — fraudulent crediting, inflated
  baselines, lack of additionality, unverifiable claims (Sasaki 2025) ✓. *(CA forest over-crediting ≈29%
  is the cautionary exhibit ✓ — magnitude [contested].)*
- **NATURE credibility (biodiversity is NON-FUNGIBLE — you cannot judge a single number):** score
  **data-protocol quality + a basket of fit-for-purpose indicators + independent verification**, not one
  CO₂e-style unit (Kim et al. 2025, Royal Society B ✓). **Independent third-party verification (VVB) is
  the gating weak point** — 8 of 11 biodiversity-credit suppliers had none ✓. Demand counterfactual
  reasoning while accepting the field is **less mature but catching up** (Ferraro & Pattanayak; Langhammer
  2024 ✓).
- **Climate–nature trade-offs:** does advancing one pillar risk the other (afforestation vs. biodiversity;
  BECCS land use; hydropower vs. rivers; blue carbon)? Home: **OECD "coherence"** ✓ + **IUCN Global
  Standard for NbS** (Crit 3 net biodiversity gain; Crit 6 balance trade-offs) ·sourced.

### + Responsible AI & footprint  *(cross-cutting)*
The AI's **own compute/energy/carbon cost** (a climate cost!), equity/environmental justice, dual-use,
data governance, **Indigenous data sovereignty** (nature/land data), model risk. *Grounding: BEF's own
"used **responsibly**" framing ·sourced + responsible-AI norms.*

### Gating flags (sink an item regardless of other scores)
1. **Not real innovation** — derivative / AI-washing.
2. **Environmental benefit not credible** — greenwashing / biodiversity-washing / no measured outcome.

### Scoring (light)
Per applied lens → **{strong / adequate / weak / concern / n-a}** + confidence + a one-line, source-cited
note; record **which lenses applied/skipped and why** (OECD guardrail). No funding/fit score — that's the
directors'.

---

## Ontology (v3 — reframed for innovation + landscape)

| Type | Role (note the reframing from "funding" to "assessment") |
|---|---|
| `Paper` / `Proposal` / `Tool` | the thing assessed; carries the six-lens verdict in frontmatter |
| **`Assessment`** | the head-of-AI's verdict (cutting-edge / promising / derivative / not-credible / watch) + rationale + gating flags *(was "Decision")* |
| **`Outcome`** | did the approach pan out in the field over time; what happened *(reframed from grant outcome)* |
| **`Thesis`** | a position on **AI capability for climate/nature** (e.g., "foundation models for remote sensing are crossing into deployment-grade for deforestation") + confidence |
| `Method` / `Approach` | the AI technique (digital twins, bioacoustics, world models, remote sensing…) |
| **`Organization` / `Lab`** | **who is doing what** in AI-for-climate/nature *(new — powers the landscape lens)* |
| **`Benchmark` / `Result`** | **state-of-the-art tracking** over time *(new)* |
| `Domain` | BEF focus areas — *Climate:* emissions monitoring, fire detection, renewables, CDR, livestock, EV batteries · *Nature:* forest protection, wildlife monitoring, ocean (illegal fishing/reefs/deep-sea), biodiversity & species ID, genomics, ag/alt-proteins |
| `Risk` | recurring concern (AI-washing, inflated baseline, no VVB, climate↔nature trade-off) |
| **`Author` / `Person`** | who wrote/built it — to connect ideas across papers, labs, and time *(added 2026-06-09)* |
| **`Technology`** | tools / models / systems / open-source / hardware (e.g., GPUs) a work uses or builds on *(added 2026-06-09)* |
| **`Idea` / `Concept`** | a recurring idea/approach to connect across works *(added 2026-06-09)* |

**Relations:** `assessed-as` · `advances-over` / `benchmarked-against` · `state-of-the-art-for` ·
`built-by` (→ Organization) · `uses-method` · `addresses-domain` · `supports` / `contradicts` /
`duplicates` / `supersedes` · `has-tradeoff-with` (climate↔nature) · `verified-by` (VVB) ·
`informs` / `challenges` (→ Thesis) · `authored-by` (→ Author) · `uses-technology` (→ Technology) · `applies-idea` (→ Idea).

> **Head-of-AI request (2026-06-09) — keep for future versions:** the tool must map & connect not only
> assessments but **authors/people, ideas/concepts, and technologies used** (tools, models, systems,
> open-source, hardware incl. GPUs) — so we can trace *who* works on what, which *ideas/tech* recur, and how
> they link across the corpus. Captured now via `authors:` / `technologies:` page frontmatter (see the two
> ingested assessments); to be promoted into full `Author` / `Technology` / `Idea` entity pages + a real
> relationship graph in a later build (a natural fit for the R2R/graph "middle").

---

## Lightweight assessment-capture practice
- **Assessment Record** (when you assess something): item ref · lenses applied (+ skipped & why) ·
  verdicts · gating flags · frontier positioning · the verdict + rationale. *Agent drafts from your notes;
  you approve in minutes.*
- **Outcome Record** (later): did the approach succeed in the field → updates/challenges a `Thesis`.
- **Thesis pages** (capability positions): reviewed periodically so the org's read on the frontier stays current.
- **Anti-over-proceduralization:** purpose-selected lenses only; if it feels like box-ticking, you're applying too many.

## How a query resolves (reframed to the new purpose)
A colleague asks about *"physical AI for digital twins"* → traverse `Method` → `Organization`/`Lab`
doing it + `Benchmark`/SOTA → our `Assessment`s (cutting-edge / derivative + why) → `Outcome`s (what
panned out) → `Thesis` (our current read) → `has-tradeoff-with` / `supersedes` edges. Answer: **here's
the state of the art, who's pushing it, what we've judged real vs. hype, what's working, and where it
trades climate against nature** — cited to source.

## Operational mapping (into the LLM-maintained KB)
`Paper`/`Tool`/`Method`/`Organization`/`Benchmark`/`Domain` → R2R documents + graph entities; the agent
applies the six lenses on ingest. **`Assessment`/`Outcome`/`Thesis`** → human-in-the-loop (agent-drafted,
you approve). Verdicts → page **frontmatter** (Dataview/search filters: `innovation: strong`, `vvb: none`,
`frontier: behind`). The rubric becomes the standing ingest rule in `CLAUDE.md`.

## Contested / still open
- **Contested:** CA over-crediting magnitude (CARB disputes); biodiversity credits & "nature-positive" are
  contested concepts (verified lit leans cautionary).
- **[to-confirm]:** the **frontier/landscape lens** would benefit most from a dedicated research pass (the
  current AI-for-climate-and-nature landscape — who's cutting-edge, what's working — + the Rolnick/CCAI
  taxonomy tags + technology-scouting/horizon-scanning frameworks); plus the still-open **nature** cites
  (TNFD/SBTN/IPBES, the biodiversity indicator basket, full IUCN NbS criteria).
- **·sourced (not adversarially verified):** NIH framework; BEF "Suitability"/"used responsibly" language.

## Your steer (updated — program-fit items removed)
1. **Default vs. optional lenses** — which of the six are always applied vs. situational.
2. **Your working theses** on AI capability for climate *and* nature — give me 3–6 to seed `Thesis` pages.
3. **How you want assessments captured** (where your read currently lives — notes, Slack, docs).
4. **Sensitivity tiers** — public / internal / restricted, for colleague queries.

## Immediate follow-on
1. **(Recommended) Landscape research pass** to ground lens 3 — the live AI-for-climate-and-nature frontier
   (who/what's cutting-edge & working) + Rolnick/CCAI taxonomy + the open nature cites — for true depth on
   exactly the focus you named.
2. Wire the six lenses into `CLAUDE.md` + generate `_templates/` per entity type.
3. Hand-assess **2–3 real papers/tools** to test whether the output reads like *your* judgment.
