# Wiki Log

Append-only, chronological record of everything that happens to the wiki. Newest at the bottom.
Each entry starts with a greppable prefix: `grep "^## \[" wiki/log.md | tail -5`.

## [2026-06-05] bootstrap | LLM Wiki instance scaffolded  →  schema + structure + 3 example pages
Created `CLAUDE.md` (schema), `README.md`, the `wiki/` structure (`index.md`, `overview.md`,
templates), and three `status: example` seed pages to demonstrate the entity/concept/source
formats. No real sources ingested yet. Next: drop real documents into `raw/` and ingest.

## [2026-06-05] query  | "how to scale this wiki to enterprise (1k–10k docs)?"  →  filed: analyses/enterprise-scaling-research.md
Deep-research pass (27 sources, 120 claims, 25 adversarially verified → 20 confirmed / 5 killed).
Verdict: **hybrid** — build the synthesis layer (GraphRAG-family: nano-graphrag / LazyGraphRAG),
buy the enterprise plumbing (Onyx EE for permissions/SSO/audit), design around the unsolved
ACL-into-derived-pages problem via permission-tiered synthesis. Filed full analysis +
phased build-out plan to `analyses/enterprise-scaling-research.md`; added to index.

## [2026-06-06] query  | "is there an OSS framework for THE MIDDLE (retrieval+graph+orchestration)?"  →  R2R
Deep-research pass 2 (23 sources, 113 claims, 25 verified → 23 confirmed / 2 killed). Verdict:
**R2R (SciPhi, MIT)** is the closest single integrated middle (hybrid retrieval + Leiden/community
GraphRAG synthesis + Deep Research agent + access control, one REST API). Universal gap: none export
synthesis to markdown → a thin custom exporter is the one bespoke piece. Graphiti = best incremental
KG layer. (Presented in chat + memory; not yet filed as a wiki page.)

## [2026-06-06] design | BEF AI-Knowledge Model v1  →  wiki/_schema/bef-ai-knowledge-model.md
Drafted the judgment/decision layer (Layer B): a 10-dimension evaluative rubric + entity ontology
(Paper/Proposal/**Decision**/**Outcome**/**Thesis**/Method/Domain/Risk) + typed relationships +
the exemplar-query resolution + stack mapping. v1 for the head-of-AI to red-pen; 4 open decisions
flagged (rubric/weights, BEF theses, decision-capture mechanism, sensitivity tiers).

## [2026-06-06] research+design | Judgment layer v2 (climate AND nature, framework-grounded)  →  _schema/bef-ai-knowledge-model.md
Deep-research pass (27 sources, 126 claims, 24/25 verified) + direct grounding of BEF/NIH sources.
Rebuilt the rubric as 5 tiers grounded in NAMED frameworks: BEF's own 5 Grand Challenge criteria
(Impact/Viability/Suitability/Scalability/Societal Benefit) on top; ITN/INT + Open Phil cost-effectiveness
"bar"; OECD-DAC 6 criteria as purpose-selected LENSES ("not a checklist" — authoritative basis for
rigorous-not-bureaucratic); climate credibility (Oxford Principles, CarbonPlan VCL, 4 greenwashing failure
modes, CA over-crediting [contested]); NATURE credibility with DIFFERENT machinery (biodiversity
NON-FUNGIBLE → data protocols + indicator basket + independent VVB gate, not a single unit); climate–nature
trade-offs (OECD coherence + IUCN NbS). Two gating checks (additionality; independent verification).
verified/sourced/to-confirm tags throughout. Still [to-confirm]: TNFD/SBTN/IPBES + biodiversity metrics.

## [2026-06-06] design | Judgment layer v3 — reframed to INNOVATION-ASSESSMENT lens  →  _schema/bef-ai-knowledge-model.md
Per head-of-AI direction: this layer is a TECHNOLOGY-ASSESSMENT lens (is this real, cutting-edge AI that
credibly advances climate/nature?), NOT a funding/program decision — program fit delegated to program
directors. REMOVED (confirmed): BEF program-fit tier, cost-effectiveness "bar", ITN cause-prioritization,
OECD-DAC program tier (kept only 'coherence' for trade-offs). KEPT environmental-impact credibility as a
reality check (anti-greenwashing / anti-biodiversity-washing; climate & nature different machinery).
ELEVATED 'frontier & landscape positioning' to a first-class lens (SOTA / who-else / what's-working).
Six lenses: innovation · rigor · frontier-positioning · evidence-it-works · AI-leverage · climate/nature
credibility (+ responsible-AI cross-cutting). Ontology reframed: Decision→Assessment, added Organization/
Lab + Benchmark/Result for landscape tracking. Next (recommended): landscape research pass to ground lens 3.

## [2026-06-06] research | Landscape & frontier — climate pass + dedicated nature pass  →  topics/ai-for-climate-and-nature-landscape.md
Two deep-research passes (climate: 24/25 verified; nature: 24/25 verified — nature run separately after the
combined pass verified 0 nature claims). Filed a balanced, maturity-tiered landscape map. Headlines:
DEPLOYED 🟢 — ECMWF AIFS (operational weather ML), Climate TRACE/Carbon Mapper (emissions MRV), BirdNET,
iNaturalist, MegaDetector/SpeciesNet, Global Fishing Watch, WRI–Meta canopy maps, ESA BIOMASS. EARLY 🟡 —
GenCast/Aurora, DestinE, geospatial FMs (AlphaEarth/Prithvi/Clay), BioCLIP. HYPE 🟠 — generative materials
"novelty" [contested], "universal geo-FM" (GEO-Bench-2/PANGAEA: no geo-FM dominates). Seeded Organizations/
Methods/Benchmarks + 10 frontier Theses. Grounds rubric lens 3. GAPS: Global South/China, BEF named
grantees, eDNA/anti-poaching/genomics, maturity-gap quantification — a closing pass would fill these.

## [2026-06-06] operationalize | Wired six-lens rubric into CLAUDE.md + templates + 3 hand-assessments
Executed "operationalize" step. (1) Added a "Domain layer" section to `CLAUDE.md` — the six-lens assessment
as the standing ingest rule + the v3 ontology + where pages live. (2) Created `_templates/` for assessment·
thesis·paper·organization·method·benchmark; created `assessments/` and `theses/` dirs. (3) Hand-assessed 3
real systems spanning the maturity spectrum + both pillars: [[assessment-alphaearth]] (nature, promising,
vendor-benchmark caution), [[assessment-mattergen]] (climate, frontier, contested novelty), [[assessment-birdnet]]
(nature, deployed/cutting-edge). These test whether the rubric reads like the head-of-AI's judgment — awaiting
calibration. BACKLOG narrowed to: Global South & China · eDNA+ML · conservation genomics (others de-scoped).

## [2026-06-09] ingest | First 2 real papers assessed  →  assessments/alejo-nbs-ai, assessments/stein-relational-accountability
First live use of the tool on real documents (dropped in `raw/`). (1) **Alejo et al. 2026** (Earth's Future) —
RL/CAPTAIN to align biodiversity+carbon+water for Canada's 30×30; verdict **promising** (AI applied, not
frontier; RL-vs-classical-optimization open question; modeled-not-realized outcomes). (2) **Stein 2026** (npj
Climate Action) — a *critique* of AI-for-climate; rubric correctly routed it as **"important perspective"**
(most innovation lenses N/A; lands on Responsible-AI). **The two CONNECT:** Stein's relational-accountability
critique directly challenges Alejo's top-down optimization of ecosystems/Indigenous lands — first real
relationship/contradiction surfaced by the wiki. Captured authors + technologies per new requirement.

## [2026-06-10] ingest | AI for climate: from technological solutions to relational accountability  →  nodes:15 merged:0 edges:14 chunks:24 flagged:4

## [2026-06-10] ingest | Maximizing Nature‐Based Solutions Using Artificial Intelligence to Align Global Biodiversity, Climate, and Water Targets  →  nodes:119 merged:80 edges:141 chunks:109 flagged:13

## [2026-06-11] apply  | "AI for climate: from technological solutions to relational accountability"  →  connections:1 novel:0 flagged:0

## [2026-06-11] ingest | AI for climate: from technological solutions to relational accountability  →  nodes:15 merged:1 edges:14 chunks:24 flagged:4

## [2026-06-11] ingest | Maximizing Nature‐Based Solutions Using Artificial Intelligence to Align Global Biodiversity, Climate, and Water Targets  →  nodes:84 merged:72 edges:98 chunks:109 flagged:13

## [2026-06-11] apply  | "AI for climate: from technological solutions to relational accountability"  →  connections:1 novel:0 flagged:0

## [2026-06-11] apply  | "AI for climate: from technological solutions to relational accountability"  →  connections:1 novel:0 flagged:0
