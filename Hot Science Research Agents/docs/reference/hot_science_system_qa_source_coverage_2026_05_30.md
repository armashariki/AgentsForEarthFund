# Hot Science System QA and Source Coverage Audit

Date: 2026-05-30

## Executive Summary

The Hot Science system is mechanically healthy, but its source coverage is not yet broad enough to claim a full or complete online search of climate-relevant papers.

Current status:

- Frontend production build passed.
- Python test suite passed: 86 passed, 8 skipped.
- Current source inventory: 20 configured sources, 15 enabled, 5 disabled.
- Live source URL check: most configured feed URLs responded; NOAA RSS timed out once.
- Live constrained all-enabled-source agent scan completed with zero source errors.
- Live Fly health check passed: `https://deepgreen-hot-science.fly.dev/health`.
- The UI now defaults to all enabled sources by leaving the source field blank.

Most important finding:

The current system searches a useful pilot set, but it is still concentrated in OpenAlex, Crossref, selected Nature/Science/PNAS feeds, ScienceDaily, a few institutional feeds, WWA, and EarthArXiv. For a stronger Hot Science search, the system should add PubMed/Europe PMC, Semantic Scholar with an API key, arXiv, DataCite, CORE/DOAJ/Unpaywall enrichment, EurekAlert, AGU/Wiley/EGU/Copernicus Publications journals, Springer Nature metadata, Elsevier/Scopus or ScienceDirect if licensed, and additional institutional climate/cryosphere/data-release sources.

## QA Checks Performed

### Local Checks

- `npm run build --prefix web/frontend`
  - Result: passed.
- `.venv/bin/python -m pytest tests/ -q`
  - Result: passed.
  - Summary: 86 passed, 8 skipped.

### Config Inventory

Source config reviewed:

- `config/hot_science_sources.yaml`
- `agents/hot_science/clients.py`
- `agents/hot_science/source_monitor.py`
- `web/frontend/src/App.tsx`

Current configured source count:

- Total configured: 20
- Enabled: 15
- Disabled: 5

### Live Source Health

Live Fly health check:

- Endpoint: https://deepgreen-hot-science.fly.dev/health
- Result: `{"status":"ok","service":"hot_science_api","auth_configured":true}`

Direct URL health check:

- Nature RSS: reachable.
- Nature Communications RSS: reachable.
- Nature Climate Change RSS: reachable.
- Nature Geoscience RSS: reachable.
- Science RSS: reachable.
- Science Advances RSS: reachable.
- PNAS RSS: reachable.
- ScienceDaily Climate RSS: reachable.
- ScienceDaily Environment RSS: reachable.
- WMO news page: reachable but disabled because it is not a stable RSS/API source.
- Copernicus C3S RSS: reachable.
- NOAA RSS: timed out once in direct check.
- World Weather Attribution feed: reachable.
- EarthArXiv OAI-PMH: reachable.

Live constrained all-enabled-source scan:

- Target month: 2026-04.
- Sources: all enabled sources.
- Max results per source: 1.
- Result:
  - Raw candidates: 99
  - Verified: 16
  - Evaluated/top candidates: 7
  - Manual review: 12
  - Excluded: 80
  - Preprints: 0
  - Source errors: 0

Interpretation:

- The source client path works across enabled sources.
- All-source mode is heavier than the three-source smoke test and should be treated as the normal production search mode.
- NOAA should be replaced or supplemented with more specific NOAA/NCEI climate feeds or APIs.

## What The System Is Searching Now

These are the currently configured sources in `config/hot_science_sources.yaml`.

### Enabled Broad Scholarly Indexes

1. OpenAlex Works
   - Type: scholarly API
   - Role: broad open scholarly discovery index.
   - Current implementation: keyword search with publication-date filters.
   - Endpoint used by code: `https://api.openalex.org/works`
   - Official docs: https://docs.openalex.org/api-entities/works/filter-works

2. Crossref Works
   - Type: scholarly API
   - Role: DOI and publisher metadata discovery.
   - Current implementation: bibliographic query with journal-article and date filters.
   - Endpoint used by code: `https://api.crossref.org/works`
   - Official docs: https://www.crossref.org/documentation/retrieve-metadata/rest-api/

### Enabled Journal and Publisher Feeds

3. Nature
   - RSS: https://www.nature.com/nature.rss
   - Also supplemented by ISSN/month backfill through OpenAlex and Crossref.

4. Nature Communications
   - RSS: https://www.nature.com/ncomms.rss
   - Also supplemented by ISSN/month backfill.

5. Nature Climate Change
   - RSS: https://www.nature.com/nclimate.rss
   - Also supplemented by ISSN/month backfill.

6. Nature Geoscience
   - RSS: https://www.nature.com/ngeo.rss
   - Also supplemented by ISSN/month backfill.

7. Science
   - RSS: https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=science
   - Also supplemented by ISSN/month backfill.

8. Science Advances
   - RSS: https://www.science.org/action/showFeed?type=etoc&feed=rss&jc=sciadv
   - Also supplemented by ISSN/month backfill.

9. PNAS
   - RSS: https://www.pnas.org/rss/current.xml
   - Also supplemented by ISSN/month backfill.

### Enabled Press and Discoverability Feeds

10. ScienceDaily Climate News
    - RSS: https://www.sciencedaily.com/rss/earth_climate/climate.xml
    - Role: press lead discovery.
    - Important caveat: ScienceDaily items must resolve to eligible underlying papers or official reports before inclusion.

11. ScienceDaily Environment News
    - RSS: https://www.sciencedaily.com/rss/earth_climate/environmental_science.xml
    - Role: press lead discovery.

### Enabled Institutional, Attribution, and Data Sources

12. Copernicus Climate Change Service
    - RSS: https://climate.copernicus.eu/rss.xml
    - Role: institutional climate data releases and updates.
    - Related official RSS page: https://www.copernicus.eu/en/main/rss-subscription
    - Climate Data Store: https://climate.copernicus.eu/climate-data-store

13. NOAA News
    - Current packaged RSS: https://www.ncei.noaa.gov/news.xml
    - Role: institutional NOAA releases.
    - QA caveat: direct health check timed out once; use more specific NOAA/NCEI sources where possible.
    - Climate.gov archive note: https://www.climate.gov/feeds

14. World Weather Attribution
    - RSS: https://www.worldweatherattribution.org/feed/
    - Role: attribution reports.

15. EarthArXiv
    - OAI-PMH: https://eartharxiv.org/api/oai/
    - Role: Earth science preprints, kept separate from final peer-reviewed top candidates.
    - Official OAI note: https://eartharxiv.github.io/

### Configured But Disabled

16. Semantic Scholar Academic Graph
    - Status: disabled.
    - Reason: should be enabled only after `SEMANTIC_SCHOLAR_API_KEY` is configured.
    - Official API: https://api.semanticscholar.org/api-docs/graph

17. World Meteorological Organization
    - Status: disabled.
    - Reason: current config notes no stable RSS endpoint; the news page is reachable but needs a dedicated scraper or API strategy.
    - Current URL: https://wmo.int/news

18. ESS Open Archive
    - Status: disabled.
    - Reason: feed/API endpoint not yet configured.

19. New York Times Climate
    - Status: disabled.
    - Reason: requires licensed/API access. Should remain a press/context source, not a primary paper source.

20. The Guardian Environment
    - Status: disabled.
    - Reason: requires Guardian Open Platform key or RSS fallback. Should remain a press/context source, not a primary paper source.

## What The System Should Search Next

These are the highest-priority additions for a more complete Hot Science paper search.

### Tier 1: Add Immediately

1. Semantic Scholar Academic Graph
   - Why: strong paper metadata, abstracts, author/venue data, citation graph, and relevance search.
   - Needed: configure `SEMANTIC_SCHOLAR_API_KEY`, rate limiting, retry/backoff.
   - Official docs: https://api.semanticscholar.org/api-docs/graph

2. PubMed / NCBI E-utilities
   - Why: essential for climate-health, pollution, epidemiology, vector-borne disease, occupational heat, wildfire smoke, food/health, and environmental health papers.
   - Needed: new `pubmed` client using ESearch/ESummary/EFetch; publication-date filters; optional `NCBI_API_KEY`.
   - Official docs: https://dataguide.nlm.nih.gov/eutilities/utilities.html

3. Europe PMC
   - Why: strong biomedical/life-science metadata and full-text links; complements PubMed.
   - Needed: REST client with date and query filters.
   - Official docs: https://europepmc.org/RestfulWebService

4. arXiv
   - Why: important for climate modeling, statistics, ML-for-climate, physics, Earth-system modeling, economics, and adaptation/impact modeling preprints.
   - Needed: preprint bucket only, not mixed into peer-reviewed top candidates.
   - Official docs: https://arxiv.org/help/api/user-manual

5. DataCite
   - Why: captures reports, datasets, data releases, preprints, software/data papers, and non-Crossref DOIs.
   - Needed: DOI metadata client with published/registered date filters and resource type gates.
   - Official docs: https://support.datacite.org/docs/api

6. EurekAlert Climate Change
   - Why: the criteria explicitly values discoverability through EurekAlert; it is a major source of press leads tied to peer-reviewed publications.
   - Needed: feed/scraper strategy and strict primary-paper resolution.
   - Climate page: https://www.eurekalert.org/climatechange
   - Eligibility guidelines: https://www.eurekalert.org/releaseguidelines/

7. NSIDC
   - Why: high-value cryosphere source for Arctic/Antarctic sea ice, snow, glaciers, data releases, and analysis.
   - Needed: RSS/feed integration for News & Stories and Sea Ice Today.
   - Official news page: https://nsidc.org/news-analyses/news-stories

8. NOAA/NCEI climate-specific coverage
   - Why: broad NOAA RSS can be slow/unstable and may miss climate-specific data releases.
   - Needed: NCEI climate monitoring, Climate Data Online, monthly reports, and dataset/status feeds.
   - NCEI CDO: https://www.ncei.noaa.gov/cdo-web/
   - NCEI RSS: https://www.ncei.noaa.gov/news.xml

9. AGU/Wiley journal coverage
   - Why: AGU journals are core climate, geoscience, ocean, water, cryosphere, wildfire, and Earth-system venues.
   - Needed: ISSN-controlled backfill through OpenAlex/Crossref plus Wiley/AGU feeds where stable.
   - Priority journals:
     - Geophysical Research Letters
     - Journal of Geophysical Research: Atmospheres
     - Journal of Geophysical Research: Oceans
     - Journal of Geophysical Research: Earth Surface
     - Earth's Future
     - GeoHealth
     - Global Biogeochemical Cycles
     - Water Resources Research
     - Reviews of Geophysics
   - AGU journal catalog: https://www.agu.org/publications/catalog/journals

10. EGU / Copernicus Publications journals
    - Why: direct climate and Earth-system relevance; many are open access.
    - Needed: journal RSS or Crossref/OpenAlex ISSN backfill.
    - Priority journals:
      - Earth System Dynamics
      - Earth System Science Data
      - Climate of the Past
      - The Cryosphere
      - Atmospheric Chemistry and Physics
      - Biogeosciences
      - Hydrology and Earth System Sciences
      - Natural Hazards and Earth System Sciences
      - Ocean Science
      - Geoscientific Model Development, but route pure-methods papers carefully.

11. Springer Nature Metadata API
    - Why: current Nature RSS coverage is not the same as full Springer Nature coverage. Important journals include Climatic Change, Climate Dynamics, Nature Water, Nature Sustainability, Communications Earth & Environment, Scientific Reports, and many BMC/Springer journals.
    - Needed: API key and publisher metadata client.
    - Official docs: https://dev.springernature.com/docs/api-endpoints/metadata-api/

12. PLOS Search API
    - Why: open access, strong environmental/biology/health coverage.
    - Needed: Solr query client with date filters.
    - Official docs: https://api.plos.org/text-and-data-mining.html

13. CORE
    - Why: institutional repository and open-access full-text discovery.
    - Needed: API key and repository-aware dedupe.
    - Role: enrichment and long-tail discovery, not top-candidate authority by itself.

14. Unpaywall
    - Why: access verification and open-access location lookup by DOI. It should enrich records after discovery, not be the main discovery source.
    - Current code already has some Unpaywall-style access logic when email is configured.
    - Official FAQ/data format:
      - https://unpaywall.org/faq
      - https://unpaywall.org/data-format

15. DOAJ
    - Why: open-access journal/article metadata and journal legitimacy signal.
    - Needed: article metadata/API integration where available, or journal whitelist/enrichment.
    - Role: credibility and OA enrichment.

## What The System Could Search Later

These are useful but lower priority, licensed, broader, or more operationally complex.

### Licensed or Access-Controlled Scholarly Indexes

1. Scopus / Elsevier APIs
   - Value: broad abstract/citation index and ScienceDirect/Elsevier coverage.
   - Caveat: requires licensed/API access.
   - Official docs: https://dev.elsevier.com/documentation/ScopusAPI

2. Web of Science API Expanded
   - Value: high-quality indexed scholarly metadata, citation data, affiliation/funding metadata.
   - Caveat: paid license/API key.
   - Official docs: https://developer.clarivate.com/apis/wos

3. Dimensions API
   - Value: broad publications, grants, patents, clinical trials, policy docs.
   - Caveat: access/licensing.

4. The Lens Scholarly API
   - Value: broad scholarly works plus patent joins; useful for intervention/technology boundary cases and prior-art context.
   - Caveat: API access request and terms.
   - Official docs: https://docs.api.lens.org/

5. NASA ADS
   - Value: atmospheric, planetary, space, physics, and Earth science search.
   - Caveat: token required; more useful for atmospheric/remote sensing/modeling than general climate impacts.
   - Official docs: https://ui.adsabs.harvard.edu/help/api/api-docs.html

### Additional Publishers and Journal Families

6. Elsevier ScienceDirect
   - Priority journals:
     - Global Environmental Change
     - Global and Planetary Change
     - Earth-Science Reviews
     - Remote Sensing of Environment
     - Science of the Total Environment
     - Agricultural and Forest Meteorology
     - Environmental Research
     - Environmental Research: Climate, if accessible through source metadata.
   - Official search API docs: https://dev.elsevier.com/documentation/SCIDIRSearchAPI.wadl

7. Wiley Online Library beyond AGU
   - Priority journals:
     - Global Change Biology
     - Global Ecology and Biogeography
     - Ecological Applications
     - Conservation Biology
     - Risk Analysis

8. Taylor & Francis
   - Priority journals:
     - Climate Policy
     - International Journal of Climatology, if source coverage requires publisher path.
     - Regional Environmental Change may be Springer, so verify venue ownership before implementation.

9. Oxford Academic
   - Priority journals:
     - BioScience
     - Environmental History only when relevant.
     - Public health journals for climate-health.

10. Cambridge Core
    - Priority journals:
      - Environmental Data Science
      - Global Sustainability
      - Disaster Medicine/Public Health journals where relevant.

11. SAGE
    - Priority journals:
      - Environment and Planning family, when directly climate-impact relevant.

12. Frontiers
    - Value: open access, climate, environmental science, public health, marine science, forests.
    - Caveat: use quality gates; route lower-confidence records through manual review.
    - RSS page: https://www.frontiersin.org/news/frontiers-social-media-and-rss/

13. MDPI
    - Value: open access and broad climate/environment coverage.
    - Caveat: use strict journal and quality filters; do not let volume overwhelm the search.
    - Example journal page: https://www.mdpi.com/journal/Climate

14. Royal Society of Chemistry
    - Value: environmental chemistry, atmospheric chemistry, water, sustainability.
    - RSS page: https://pubs.rsc.org/en/ealerts/rssfeed

### Institutional Reports, Data Releases, and Climate Services

15. WMO
    - Should move from disabled to a scraper/API-backed source if stable pages can be identified.
    - Current page: https://wmo.int/news

16. IPCC
    - Role: major assessment/special reports, not monthly paper discovery.
    - Use for official reports and context, not routine monthly journal search.

17. NASA Earth Observatory / NASA Earthdata / NASA GISS
    - Role: institutional data releases, Earth observation, temperature records, remote sensing.
    - NASA API portal: https://api.nasa.gov/

18. ECMWF and Copernicus data products
    - Role: climate monitoring bulletins, ERA5, reanalysis, data releases.
    - Already partially covered through Copernicus C3S RSS, but should be expanded to datasets and official monthly bulletins.

19. Berkeley Earth
    - Role: global temperature and climate data releases.

20. Global Carbon Project
    - Role: annual carbon budget and carbon-cycle papers/data releases.

21. World Glacier Monitoring Service
    - Role: glacier observations/data releases.

22. GCOS, WCRP, and Future Earth
    - Role: official climate-system reports and science program outputs.

23. National academies and major agency reports
    - Sources: National Academies, Royal Society, European Environment Agency, UNEP, FAO, WHO, World Bank, OECD.
    - Role: official institutional reports, only when meeting target-month and climate-impact rules.

### Press and Discoverability Sources

24. EurekAlert
    - Should be added now as a press-lead source.

25. Phys.org
    - Could be useful as an additional press lead aggregator, especially for geoscience and climate.
    - Must resolve to original paper/report.

26. University and institute press rooms
    - Examples:
      - NASA/JPL
      - NOAA
      - NCAR/UCAR
      - Potsdam Institute for Climate Impact Research
      - Met Office
      - Scripps
      - Woods Hole
      - Columbia Climate School
      - University climate centers
    - Role: lead discovery; never final source of truth.

27. Major media climate desks
    - Examples:
      - Carbon Brief
      - The Conversation
      - New York Times Climate
      - The Guardian Environment
      - Washington Post Climate
      - Inside Climate News
    - Role: discoverability/context only; final inclusion must point to original study/report.

## Recommended Target Architecture for Comprehensive Search

The best practical architecture is a layered source strategy:

1. Broad scholarly discovery
   - OpenAlex
   - Crossref
   - Semantic Scholar
   - PubMed
   - Europe PMC
   - DataCite
   - arXiv
   - Optional licensed indexes: Scopus, Web of Science, Dimensions, Lens

2. Curated high-value journal backfill
   - Use ISSN-controlled source definitions for high-priority climate journals.
   - Search by target-month publication date, not only keyword rank.
   - Keep the current OpenAlex/Crossref ISSN backfill pattern and expand the journal list.

3. Preprint discovery
   - EarthArXiv
   - arXiv
   - ESS Open Archive
   - OSF Preprints where relevant
   - Keep preprints in a separate bucket.

4. Institutional and report/data release discovery
   - WMO
   - NOAA/NCEI
   - NSIDC
   - Copernicus/ECMWF
   - NASA Earthdata/GISS/JPL
   - IPCC/UNEP/WHO/FAO/World Bank when relevant

5. Press lead discovery
   - ScienceDaily
   - EurekAlert
   - Phys.org
   - Selected institution press rooms
   - Selected major media only for discoverability, not eligibility.

6. Enrichment and verification
   - Unpaywall for open-access/full-text location.
   - DOI resolver for canonical DOI.
   - Crossref/DataCite for DOI metadata.
   - Publisher page for authoritative online-first publication date.
   - Manual review for media-only, title-only, wrong-date, and non-peer-reviewed ambiguities.

## Recommended Source Expansion Plan

### Phase A: Immediate Config/API Expansion

Add or enable:

- Semantic Scholar with API key.
- PubMed E-utilities.
- Europe PMC.
- arXiv.
- DataCite.
- EurekAlert climate.
- NSIDC.
- NOAA/NCEI specific feeds.
- WMO scraper or stable source path.

Expected benefit:

- Better climate-health, cryosphere, institutional, preprint, and official data-release coverage.

### Phase B: Journal Coverage Expansion

Add ISSN-backed source entries for:

- AGU/Wiley climate and geoscience journals.
- EGU/Copernicus journals.
- Springer climate/environment journals.
- Elsevier climate/environment journals where API/licensing allows.
- PLOS journals.
- Frontiers journals with stricter quality routing.
- RSC environmental journals where relevant.

Expected benefit:

- More complete monthly target-month capture.
- Less dependence on keyword-ranked API results.
- Better recall for papers that do not use the exact phrase "climate change" in the title/abstract.

### Phase C: Licensed Coverage Decision

Decide whether BEF has or wants access to:

- Scopus API.
- Web of Science API.
- Dimensions API.
- Lens API.
- Elsevier ScienceDirect API.
- Springer Nature API.

Expected benefit:

- Stronger completeness and citation/impact metadata.
- More expensive and governance-heavy, but valuable for team-confidence.

## QA Risks and Fixes

1. Risk: current source list cannot support "complete search" language.
   - Fix: describe the current tool as "broad multi-source search" until Tier 1 and journal expansion are complete.

2. Risk: generic RSS feeds miss article-level paper records.
   - Fix: prefer APIs and ISSN/month backfills for journals.

3. Risk: popular press items can enter manual review without verified underlying papers.
   - Fix: keep unresolved press in manual review only; never top candidates.

4. Risk: broad institutional RSS feeds can be unstable or too broad.
   - Fix: prefer NCEI, climate monitoring, and specific official datasets/pages over generic agency feeds.

5. Risk: all-enabled source scans are slower than pilot scans.
   - Fix: add progress telemetry by source, caching, rate-limit handling, and source-health summaries in the UI output.

6. Risk: licensed sources may create deployment/secrets/governance requirements.
   - Fix: treat licensed API integrations as separate source modules with explicit keys, rate limits, and allowed-use notes.

7. Risk: Google Scholar is attractive but not suitable as a programmatic source.
   - Fix: do not scrape Google Scholar. Use it only for manual QA spot checks unless an approved/licensed route exists.

## Bottom Line

The system is healthy enough to run, and the UI now defaults to maximum configured coverage. But for Hot Science quality, the source inventory should be expanded before the team treats the output as a comprehensive paper search.

The most important next source work is:

1. Enable Semantic Scholar with an API key.
2. Add PubMed and Europe PMC.
3. Add arXiv and DataCite.
4. Add EurekAlert and NSIDC.
5. Continue strengthening NOAA/NCEI climate sources beyond the packaged NCEI RSS feed.
6. Add AGU/Wiley and EGU/Copernicus journal families with ISSN/date backfill.
7. Decide whether to pursue Scopus, Web of Science, Dimensions, Lens, Springer Nature, and Elsevier API access.
