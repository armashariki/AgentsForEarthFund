---
type: topic
title: AI for Climate and Nature — Landscape & Frontier (2025–2026)
aliases: [Landscape, Frontier Map, State of the Art]
created: 2026-06-06
updated: 2026-06-06
tags: [landscape, frontier, climate, nature, ai]
status: maintained
confidence: medium
---

# AI for Climate and Nature — Landscape & Frontier (2025–2026)

Grounds **lens 3 (frontier & landscape positioning)** of the [[bef-ai-knowledge-model]]. The current
state of the art, **maturity-tiered, climate and nature at equal depth.** From three deep-research
passes (climate + nature), ~48 adversarially-verified claims. Tags: **✓** verified 3-0 · **[contested]**
· **[vendor]** self-reported/promotional · **[gap]** not yet covered. Honest note: nature was verified in
a dedicated pass to reach parity with climate; remaining gaps are listed at the end, not hidden.

## The frontier in one view

### 🟢 Deployed at scale & working
- **CLIMATE — ML weather forecasting:** ECMWF **AIFS operational since 25 Feb 2025** (first operational ML
  weather model); beats physics IFS on many measures incl. cyclone tracks (+up to 20%), worse on TC
  intensity/stratosphere/short-range precip. ✓
- **CLIMATE — emissions MRV:** **Climate TRACE** (2.77M sources) and **Carbon Mapper** (Tanager-1 sat).
  Deployed for *coverage*; local accuracy [contested]. ✓
- **NATURE — perception (the strong suit):** **BirdNET** bioacoustics (Cornell K. Lisa Yang Center + TU
  Chemnitz; 6,000+ species) ✓ · **iNaturalist** CV (90,290 taxa, 89.2%, live since 2017) ✓ · camera-trap
  CV — **MegaDetector** (Microsoft, 80+ orgs), **Google SpeciesNet** (99.4% animal-image detection),
  **PyTorch-Wildlife** ✓ · **Global Fishing Watch** vessel detection (Sentinel-1 SAR + Sentinel-2 optical) ✓.
- **NATURE — forest/biomass MRV:** **WRI–Meta 1 m canopy-height maps** (DINOv3, free/open, monitoring
  TerraFund/AFR100 — 29M+ trees) ✓ · **ESA BIOMASS** satellite live 2025 (Level-1 open; Level-2 phased
  to 2026–27) ✓.

### 🟡 Promising but early
- **CLIMATE:** **GenCast** (DeepMind, Nature 2024 — beats ECMWF ENS on 97.2% of targets, research-grade) ·
  **Aurora** (Microsoft, Nature 2025 — 1.3B Earth-system FM, *not deployed*) · **DestinE** Earth digital
  twins (EU/ECMWF, "transitioning to operational," target 2030). ✓
- **NATURE:** **geospatial foundation models** — **AlphaEarth Foundations** (DeepMind; 64-D, 10 m global
  embeddings; 23.9% error reduction *[vendor, single benchmark]*), **Prithvi** (NASA–IBM), **Clay**,
  **TerraMind** · **biodiversity FMs** — **BioCLIP** (CVPR 2024; +17–20% on fine-grained biology). ✓

### 🟠 Contested / overhyped
- **CLIMATE — generative materials discovery:** **GNoME** (380–520k *predicted* crystals) & **MatterGen**
  (1 lab-synthesized candidate). Real frontier, but **"novelty" actively disputed** in peer review
  (duplicates, atom-swapping, 1970s-isostructural). Read "X novel materials" as "X predicted structures." [contested] ✓
- **NATURE — "universal geospatial foundation model":** **GEO-Bench-2** (Nov 2025) & **PANGAEA** show **no
  geo-FM dominates**; general-purpose backbones (DINOv3, ConvNeXt) often beat EO-specific FMs on high-res
  RGB; a universal geo-FM "remains open for future research." The most overstated area in nature AI. ✓

## Domain map

**Climate**
| Domain | Leaders | Key systems (maturity) | Benchmark |
|---|---|---|---|
| Weather forecasting | ECMWF, Google DeepMind, Microsoft, Huawei | AIFS 🟢 · GenCast/GraphCast 🟡 · Aurora 🟡 | [[weatherbench-2]] |
| Climate digital twins | ECMWF/EU (DestinE), NVIDIA (Earth-2) | DestinE 🟡 (km-scale) | — |
| Emissions MRV | Climate TRACE, Carbon Mapper | Climate TRACE 🟢 · Tanager-1 🟢 | — |
| Materials discovery | DeepMind, Microsoft | GNoME 🟠 · MatterGen 🟠 | Matbench |
| CDR verification | CarbonPlan | VCL framework (1–5) 🟡 | — |

**Nature**
| Domain | Leaders | Key systems (maturity) | Benchmark |
|---|---|---|---|
| Bioacoustics | Cornell K. Lisa Yang Center, Rainforest Connection | BirdNET 🟢 | [[birdset]] |
| Camera-trap CV | Microsoft AI for Good, Google | MegaDetector 🟢 · SpeciesNet 🟢 · PyTorch-Wildlife 🟢 | LILA BC |
| Species ID | iNaturalist, Pl@ntNet | iNat CV model 🟢 | iNaturalist |
| Geospatial FMs | Google DeepMind, NASA–IBM, Clay, AI2 | AlphaEarth 🟡 · Prithvi/Clay 🟡 | [[geo-bench-2]], PANGAEA |
| Biodiversity FMs | Imageomics (OSU) | BioCLIP 🟡 (→ BioCLIP 2) | TreeOfLife-10M |
| Ocean/marine | Global Fishing Watch, MBARI | GFW vessel detection 🟢 · FathomNet [gap] | — |
| Forest/biomass MRV | WRI Land & Carbon Lab, Meta, ESA | Canopy maps 🟢 · ESA BIOMASS 🟢 | — |
| Wildlife protection | AI2 (EarthRanger), CMU (PAWS) | EarthRanger/SMART [gap] | — |

## The climate–nature maturity gap (characterized)
- **Root cause:** climate AI wins where data is **abundant, standardized, physics-anchored, with shared
  benchmarks** (weather, emissions). Nature has the opposite — sparse, heterogeneous data, a long tail of
  species, and **biodiversity is non-fungible** (no CO₂e-style unit; see [[bef-ai-knowledge-model]] lens 6).
- **Benchmarks:** fewer and newer for nature (**BirdSet** and **GEO-Bench-2** are both 2024–25); bioacoustics
  "lacks uniform dataset selection and evaluation protocols." ✓
- **FM frontier:** immature for nature (no universal geo-FM; specialization beats generalization). ✓
- **[gap] not yet quantified:** relative funding, publication volume, commercial pull. **Strategic read:**
  nature is where AI is *less mature* — so targeted funding likely has **higher marginal leverage** there.

## Seed entities (for the knowledge base)
**Organizations/Labs:** Google DeepMind · Microsoft AI for Good Lab · Google Research · ECMWF · ESA ·
Cornell K. Lisa Yang Center for Conservation Bioacoustics · WRI Land & Carbon Lab · Global Fishing Watch ·
Climate TRACE · Carbon Mapper · Meta AI · NASA–IBM · Allen Institute for AI (AI2) · MBARI · iNaturalist ·
Imageomics Institute (OSU) · CarbonPlan.
**Methods/Approaches:** ML weather forecasting · Earth digital twins · generative materials discovery ·
geospatial/EO foundation models · biodiversity foundation models · bioacoustic CNNs · camera-trap detection·
SAR/optical vessel detection · canopy-height mapping.
**Benchmarks:** [[weatherbench-2]] · [[geo-bench-2]] · [[birdset]] · PANGAEA · TreeOfLife-10M · LILA BC.

## Frontier Theses (defensible positions — seed `Thesis` pages)
1. **ML medium-range weather forecasting has crossed into operational deployment** and now rivals/beats
   physics-based NWP on many measures — the first unambiguous "AI beats the incumbent" win here. ✓
2. **First-gen weather FMs (2022–24) are already being retired** (ECMWF dropping Pangu/GraphCast/FourCastNet
   at Cycle 50r1) — "SOTA weather model" has a ~12–18-month shelf life. ✓
3. **"One foundation model, many Earth tasks" (Aurora) is real as research but not deployed** — treat
   FM-for-Earth maturity claims skeptically. ✓
4. **Generative materials discovery's headline "novel materials" counts are inflated** — demand experimental
   validation, not in-silico stability. [contested] ✓
5. **AI-for-nature's strongest, genuinely-deployed tier is PERCEPTION** (bioacoustics, camera-trap CV,
   species ID, vessel detection) — high-leverage because it processes data humans cannot. ✓
6. **The "universal geospatial foundation model" is overhyped** — no geo-FM dominates; pick task-specific;
   general-purpose backbones often win on high-res RGB. ✓
7. **Biodiversity-specific FMs (BioCLIP) deliver real fine-grained gains but are early**, with immature
   evaluation. ✓
8. **Nature MRV via remote sensing is maturing into open operational infrastructure** (WRI–Meta canopy maps,
   ESA BIOMASS) — a real inflection for forest/restoration monitoring. ✓
9. **AI-for-nature materially lags AI-for-climate** (data scarcity, non-fungibility, fewer benchmarks) — so
   nature is where targeted philanthropic AI funding has the most marginal leverage. ✓ (partial)
10. **AI is high-leverage where it processes data volumes humans can't** (acoustics, camera floods,
    citizen-science photos, satellite revisits); it's "forced" where the bottleneck is measurement science
    (parts of CDR MRV) or where a simpler method suffices. ✓

## Backlog — gaps to revisit (narrowed by decision, 2026-06-06)
Only these **three** remain on the backlog; everything else was **de-scoped** (no longer planned).
- **[backlog] Global South & China** conservation/climate AI — not yet mapped (verification skewed Western/EU).
- **[backlog] eDNA + ML** — environmental-DNA metabarcoding + machine learning (reference-database bottlenecks).
- **[backlog] Conservation genomics.**
- _De-scoped:_ BEF named grantees · anti-poaching · coral reefs · FathomNet · restoration · maturity-gap quantification.

## Key sources
ECMWF AIFS · DeepMind GenCast (Nature 2024) · Microsoft Aurora (Nature 2025) · WeatherBench 2 · DestinE ·
Climate TRACE · Carbon Mapper · DeepMind GNoME (Nature 2023) · Microsoft MatterGen (Nature 2025) ·
BirdNET (Ecol. Informatics 2021) · iNaturalist v2.14 · Microsoft MegaDetector / Google SpeciesNet ·
Global Fishing Watch (Paolo et al., Nature 2024) · AlphaEarth Foundations (arXiv 2507.22291) · BioCLIP
(CVPR 2024) · GEO-Bench-2 (arXiv 2511.15658) · PANGAEA · BirdSet (ICLR 2025) · WRI Land & Carbon Lab /
Meta canopy maps · ESA BIOMASS.

## Related
- [[bef-ai-knowledge-model]] (lens 3) · [[overview]]
