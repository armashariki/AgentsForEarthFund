---
type: assessment
title: "Assessment: Maximizing Nature-Based Solutions Using AI to Align Biodiversity, Climate & Water (Alejo et al. 2026)"
aliases: [Alejo NbS RL, CAPTAIN NbS Canada]
created: 2026-06-09
updated: 2026-06-09
subject: alejo-2026-nbs-ai
source_file: "raw/Earth s Future - 2026 - Alejo - Maximizing Nature‐Based Solutions Using Artificial Intelligence to Align Global.pdf"
doi: 10.1029/2025EF007560
venue: "Earth's Future (AGU), 2026"
authors: ["Camilo Alejo", "Amy Luers", "Andréa Ventimiglia", "María-Isabel Arce-Plata", "H. Damon Matthews"]
technologies: ["CAPTAIN (reinforcement learning)", "reinforcement learning", "R (Terra, aoh)", "Google Earth Engine", "IUCN Red List range data", "BirdLife range data", "ESA-CCI land cover", "Spawn biomass carbon", "Pekel surface water", "Species Habitat Index"]
verdict: promising
maturity: promising-early
pillar: both
gating_flags: []
confidence: medium
tags: [nature, climate, water, nbs, reinforcement-learning, conservation-planning]
status: draft
---

# Assessment: Maximizing NbS Using AI to Align Biodiversity, Climate & Water (Alejo et al. 2026)

**A credible, useful integrated framework — but the AI is applied, not frontier.** Uses an RL agent
(CAPTAIN) to jointly prioritize land for *biodiversity + irrecoverable carbon + water* co-benefits toward
Canada's 30×30 targets. The contribution is the multi-objective **integration**, not a new AI method.

## What it is
Trains a reinforcement-learning agent on simulated ecosystems, then applies it to real Canadian data
(10×10 km planning units) to select conservation and restoration priority areas that maximize threatened-
species occurrence plus co-benefits (ecological integrity, irrecoverable carbon, surface-water stability),
under a budget and avoiding high-human-footprint areas. Case study: Canada; scenarios for conserve-30% and
restore-30%-of-degraded-land. **Genuinely climate AND nature AND water.** Notably co-authored by **Amy Luers
(Microsoft)**.

## Six-lens read
| Lens | Verdict | Note (cited) |
|---|---|---|
| 1 · Innovation & invention | **adequate** | Novel *integration* — RL to jointly optimize biodiversity + carbon + water (prior work optimizes one). The method itself, **CAPTAIN** (Silvestro 2022), is not new. |
| 2 · Technical rigor | **strong (caveats)** | Peer-reviewed (AGU); real data (IUCN/BirdLife/ESA-CCI/Spawn/Pekel); 10 replicates; validated vs. random + existing PAs. ⚠️ RL trained on **simulated** envs → applied to Canada (sim-to-real); 10% budget is arbitrary; SHS thresholds intermediate (acknowledged). |
| 3 · Frontier positioning | **niche-applied** | Applied RL for spatial conservation prioritization — historically a Marxan/Zonation/ILP domain. A thoughtful extension, not a frontier-AI advance. See [[ai-for-climate-and-nature-landscape]]. |
| 4 · Evidence & traction | **early / research** | Canada scenarios vs. existing Protected Areas; not deployed or adopted in planning. |
| 5 · AI suitability / leverage | **adequate — open question** | Budgeted multi-objective spatial optimization is legitimate, but is **RL *uniquely* suited vs. established optimization** (Marxan / integer programming)? The paper doesn't strongly justify RL's superiority — a real lens-5 question. |
| 6 · Climate/nature credibility | **strong framing; modeled, not measured** | Transparent trade-offs (e.g., the ecological-integrity scenario *lowers* threatened-species count vs. the carbon scenario). But the "outcome" is *identified priority areas*, not realized biodiversity/carbon gains; depends on input-data/model assumptions. Directly tackles climate–nature trade-offs (→ lens 6 + IUCN NbS). |
| + Responsible AI & footprint | **low footprint; governance gap** | Tiny model (8 hidden neurons), low compute. Prioritizes conservation **including on Indigenous lands** (figures show IPCAs) without deep engagement of Indigenous governance — exactly the gap [[assessment-stein-relational-accountability]] warns about. |

## Gating flags
- _(none)_ — real contribution; credible environmental framing.

## Verdict
**Promising** — a credible, genuinely tri-objective (biodiversity + carbon + water) NbS-prioritization
framework. The value is the integration; the AI is competent-applied, not novel. *Upgrades if validated
against realized conservation outcomes, or shown to beat established planning tools.* *Watch:* RL-vs-classical-
optimization justification, modeled-not-realized outcomes, sim-to-real transfer.

## Connections (the dots)
- **In tension with [[assessment-stein-relational-accountability]]** — this is precisely the *top-down,
  optimize-the-landscape-as-data* approach that Stein's critique challenges (treats ecosystems as data
  inputs; prioritizes Indigenous lands without engaging Indigenous governance). A genuine `contradicts` /
  `informs` relationship between a technical method and a critique of its worldview.
- Domain: AI-for-nature → conservation planning · [[ai-for-climate-and-nature-landscape]] · [[bef-ai-knowledge-model]]

## Related
- [[bef-ai-knowledge-model]] · [[ai-for-climate-and-nature-landscape]]
