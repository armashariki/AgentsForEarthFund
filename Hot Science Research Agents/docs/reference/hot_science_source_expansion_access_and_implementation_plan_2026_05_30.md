# Hot Science Source Expansion — Access & Implementation Plan

**Repository:** DeepGreen / `agents/hot_science`
**Date:** 2026-05-30
**Scope:** Access path, cost/licensing, technical integration, codebase implementation, testing, deployment (Fly.io → AWS), governance, and a prioritized roadmap for 15 priority sources.
**Verification:** Every source below was checked against official (or first-party) documentation; exact pages are listed inline and in Appendix A. Where a fact is not publicly documented, that is stated explicitly.

> **Status note:** This plan was written before the Phase 1 implementation pass. The current repository now enables Semantic Scholar without a key for pilot breadth, with documented 429 risk; Unpaywall can be enabled through environment flags; and the NOAA/NCEI feed has been repointed. Use this file as the implementation roadmap, and use `source_expansion_phase1_readiness_2026_05_30.md` for the latest readiness status.

> **Reading note on the existing architecture.** Three facts about the current code drive most of this plan:
> 1. `scan_source` in `clients.py` dispatches by `source.id` for `openalex`/`crossref`/`semantic_scholar`, then falls through to (a) `scan_journal_by_issn` for any `peer_reviewed_journal` source that has `issns` and kind `rss`/`scholarly_api`, (b) `scan_oai_pmh` for `oai_pmh`, (c) `scan_rss` for `rss`/`institutional_feed`/`preprint_feed`.
> 2. `scan_journal_by_issn` **already** queries OpenAlex *and* Crossref by ISSN + month window and merges the RSS feed. **This means the AGU/Wiley and EGU/Copernicus journals can be added as pure-config entries (issns + url) with no new client code.**
> 3. Any failure inside `scan_source` is caught and turned into a synthetic `source_status="source_error"` `CandidateRecord`; the run never crashes. New clients must preserve this contract.

---

## 1. Executive Summary

Hot Science currently discovers via two core scholarly APIs (OpenAlex, Crossref), unauthenticated Semantic Scholar, publisher RSS feeds (Nature family, Science family, PNAS, AGU/Wiley, EGU/Copernicus), two popular-science feeds (ScienceDaily), institutional feeds (Copernicus C3S, NOAA/NCEI, NSIDC, WWA), and one preprint OAI-PMH source (EarthArXiv). The biggest coverage gaps are: (a) **broad metadata breadth** (Semantic Scholar with key), (b) **climate-health** (PubMed/Europe PMC), (c) **preprints beyond Earth-sciences** (arXiv physics/stats/econ/ML), (d) **deeper institutional climate-record releases** (deeper NCEI APIs and datasets), (e) **data/report DOIs** (DataCite), and (f) **open-access verification/enrichment** (Unpaywall, CORE, DOAJ).

The good news: **13 of the 15 sources are free**, and **9 require no key at all**. Only two carry meaningful access friction (Springer Nature's non-commercial clause, and CORE's paid faster tier). The two journal-publisher items (AGU/Wiley, EGU/Copernicus) are **config-only** because the ISSN-backfill path already exists.

**Recommended P0 (do first, all free, low effort):** add Semantic Scholar key when available, Europe PMC, arXiv, Unpaywall enrichment, and deeper NCEI/NOAA/NSIDC coverage.

**P1:** PubMed/E-utilities, DataCite, NSIDC, PLOS, DOAJ (as whitelist/enrichment).

**P2/P3:** Springer Nature Metadata API (legal review on non-commercial clause first), CORE (enrichment only; evaluate v3 free-tier limits), EurekAlert (manual-review press leads only).

Bottom line: a single engineer can bring the P0 set online in roughly a week, mostly by editing `hot_science_sources.yaml` and adding three small scholarly-API clients, with no procurement.

---

## 2. Current Source Coverage Baseline

From `config/hot_science_sources.yaml` (enabled unless noted):

| Bucket | Sources currently enabled |
|---|---|
| Broad scholarly API | OpenAlex Works, Crossref Works, Semantic Scholar (`enabled: true`, key recommended) |
| Peer-reviewed journal RSS (+ISSN backfill) | Nature, Nature Communications, Nature Climate Change, Nature Geoscience, Science, Science Advances, PNAS, AGU/Wiley journals, EGU/Copernicus journals |
| Popular press RSS | ScienceDaily Climate, ScienceDaily Environment |
| Institutional data release | Copernicus C3S, NOAA/NCEI feed, NSIDC feeds, WMO (disabled — no stable RSS) |
| Attribution report | World Weather Attribution |
| Preprint | EarthArXiv (OAI-PMH), ESS Open Archive (disabled), |
| Press API (disabled) | NYT Climate, Guardian Environment |

**Coverage gaps this plan closes:** non-OpenAlex/Crossref metadata breadth; geoscience society/EGU journals as first-class sources; climate-health (biomedical) literature; broad preprints (arXiv); cryosphere institutional releases (NSIDC); US climate-record releases now that Climate.gov is archived; data/report DOIs (DataCite); and OA verification/enrichment (Unpaywall, CORE, DOAJ).

---

## 3. Missing Priority Source Matrix

| # | Source | Bucket it serves | Primary role | Free? | Key? | Net-new client code? |
|---|---|---|---|---|---|---|
| 1 | Semantic Scholar | Peer-reviewed + preprint metadata | Top-candidate discovery | Yes | Recommended | Already exists (enable) |
| 2 | PubMed / NCBI E-utilities | Climate-health peer-reviewed | Top-candidate discovery (filtered) | Yes | Optional | Yes (2-step ESearch→EFetch) |
| 3 | Europe PMC | Biomedical + preprints + full-text flags | Top-candidate + enrichment | Yes | No | Yes (single REST) |
| 4 | arXiv | Preprints (physics/stats/ML/econ) | Preprint bucket only | Yes | No | Yes (Atom) |
| 5 | DataCite | Datasets/reports/software DOIs | Data-release + reports | Yes | No | Yes (REST) |
| 6 | EurekAlert | Press releases | Manual-review press leads | Yes | No (RSS) | Reuse `rss` |
| 7 | NSIDC | Cryosphere data releases + analyses | Data-release + leads | Yes | No | Reuse `institutional_feed` (RSS) |
| 8 | NOAA / NCEI | US climate records/data releases | Data-release | Yes | Token (CDO only) | Reuse `institutional_feed`; optional CDO client |
| 9 | AGU / Wiley journals | Geoscience peer-reviewed | Top-candidate discovery | Yes (metadata) | No | **None — config-only (ISSN backfill)** |
| 10 | EGU / Copernicus journals | Geoscience peer-reviewed (OA) | Top-candidate discovery | Yes | No | **None — config-only (ISSN backfill)** |
| 11 | Springer Nature Metadata API | Climate journals beyond Nature RSS | Top-candidate discovery | Free tier (non-commercial) | Yes | Yes (REST) |
| 12 | PLOS | OA journals (PLOS Climate etc.) | Top-candidate discovery (filtered) | Yes | No | Yes (Solr) |
| 13 | CORE | Repository aggregation + full text | Enrichment / repository discovery | Free tier | Yes | Yes (REST) — optional |
| 14 | DOAJ | OA journal/article directory | Whitelist / enrichment | Yes | No (GET) | Optional (REST) |
| 15 | Unpaywall | OA status + PDF locations | Enrichment (DOI-keyed) | Yes | No (email) | Yes — wire into `access.py` |

---

## 4 & 5. Source-by-Source Access + Technical Integration

Each entry answers the 10 standard questions. Buckets used: **TOP** (eligible top candidate), **LEAD** (must resolve to a primary paper before becoming a top candidate), **PREPRINT** (separate watchlist bucket), **DATA** (institutional data release — eligible with source-type + date verification), **ENRICH** (metadata enrichment only).

---

### 4.1 Semantic Scholar Academic Graph — TOP — **P0**

**1. What it is.** Ai2's academic graph (~200M+ papers across all disciplines), exposing papers, authors, citations, venues, external IDs, and open-access PDF links. It is a metadata + graph product, not a full-text distribution service.

**2. Why add it.** Broadens beyond OpenAlex/Crossref with strong relevance ranking, citation counts (a useful impact signal for the rubric's `impact_magnitude`), and OA PDF links. It complements OpenAlex; it does not replace it. Without it we miss papers where S2's relevance ranking or its abstract coverage beats OpenAlex.

**3. Access path.** Public REST API. **API key is optional but strongly recommended.** Unauthenticated callers share one global pool; an individual key grants a per-user rate (officially "1 request per second across all endpoints," higher on review). Request a key via the form on the API product page (`semanticscholar.org/product/api#api-key-form`). No institutional approval, no license, no paid tier required for normal use.
- Rate limits: shared pool ≈ 100 requests / 5 minutes unauthenticated; ~1 rps with a key (Tutorial: `semanticscholar.org/product/api/tutorial`).

**4. Cost & licensing.** Free. No redistribution of full text (S2 FAQ: for reproducing/redistributing article text, contact the author/publisher). Storing metadata/abstracts is fine. No deployment-specific terms beyond rate limits; a Fly/AWS egress IP simply shares or uses the key's bucket.

**5. Technical integration.** Endpoint already coded: `GET https://api.semanticscholar.org/graph/v1/paper/search` with `query`, `limit`, `fields=title,authors,year,publicationDate,venue,externalIds,url,abstract,isOpenAccess,openAccessPdf`. The relevance-search endpoint **does not date-filter server-side**, so the client **post-filters** by `publicationDate` against the window (this is already implemented in `scan_semantic_scholar`). For larger pulls, the **bulk search** endpoint (`/paper/search/bulk`) supports `publicationDateOrYear` and token pagination; consider it only if volume grows. Fields → `CandidateRecord`: `title`, `externalIds.DOI`→`doi`, `authors[].name`, `venue`→`PublicationInfo.venue`, `publicationDate`→`online_publication_date`, `url`, `isOpenAccess`→`open_access`, `abstract`. Citation counts (`citationCount`) can be added to the audit trail for the impact dimension.

**6. Implementation in this codebase.** No new code — the client and the YAML entry already exist. The current pilot keeps `enabled: true` for breadth, even without a key. Note `build_retrieval_queries` already degrades gracefully by using a single broad query when no key is present. Failure mode: a 429/HTTP error already becomes a `source_error` record via `scan_source`'s `except`. Add `SEMANTIC_SCHOLAR_API_KEY` as soon as available to reduce shared-pool 429s.

**7. Data quality & eligibility.** TOP. Merge with OpenAlex/Crossref via DOI in `_already_seen`/`_dedupe_records` (already DOI-first, then URL, then normalized title). DOI conflicts: prefer the Crossref/OpenAlex record's DOI; S2 record merges its `discovered_via`. Missing abstract → `add_missing_reason("abstract", …)` (already done). Non-peer-reviewed S2 hits (preprints) should be routed to PREPRINT if `externalIds` shows arXiv/SSRN and no journal venue — add a small guard.

**8. Security/secrets.** Secret name: `SEMANTIC_SCHOLAR_API_KEY` (already referenced). `.env` locally; Fly secret for pilot; AWS Secrets Manager later. No OAuth/IP restrictions.

**9. Operational impact.** With a key at ~1 rps, 3 queries add ~3–5 s. Run every time. Cache per (query, window) for a run. Show source status in UI (already emitted via progress events). Failures nonfatal.

**10. Recommendation.** **Keep enabled for the pilot and add the free key. P0. Implementation: low. Access: low (free key). Coverage value: high.** Bottom line: the key is the cheapest reliability win available.

---

### 4.2 PubMed / NCBI E-utilities — TOP (filtered) — **P1**

**1. What it is.** NCBI's primary API over MEDLINE/PubMed: ~37M biomedical citations with MeSH terms, publication types, authors, journal, dates, abstracts, and (often) DOI via ArticleId. Records are peer-reviewed citations; full text lives in PMC.

**2. Why add it.** Fills the **climate-driven human-health** gap (heat mortality, vector-borne disease, air quality) where biomedical journals are under-indexed by the current geoscience-leaning feeds. Complements OpenAlex/Crossref; the MeSH vocabulary lets us target climate-health precisely.

**3. Access path.** Public REST (E-utilities). **`NCBI_API_KEY` is optional.** Without key: 3 requests/second. With a free key (generated in any NCBI account → Account Settings → API Key Management): 10 rps. Higher rates by emailing `eutilities@ncbi.nlm.nih.gov`. Large jobs must run weekends or 21:00–05:00 ET. Source: NLM Support KA-05317 / KA-05510 and `eutilities.github.io/site/API_Key/usageandkey`.

**4. Cost & licensing.** Free. PubMed metadata is public-domain-ish (US government); abstracts may carry publisher copyright — store but don't redistribute full abstracts wholesale. No deployment terms beyond rate policy; **register the tool name + email** with NCBI to avoid IP blocks (use `tool=` and `email=` params plus the `User-Agent`).

**5. Technical integration.** Two-step:
- `ESearch`: `GET eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi?db=pubmed&term=<climate query>&datetype=edat&mindate=YYYY/MM/DD&maxdate=YYYY/MM/DD&retmax=N&retmode=json&api_key=…` → returns PMIDs. **Date filter is server-side** via `datetype=edat` (Entrez date) or `pdat` (publication date) + `mindate`/`maxdate`.
- `EFetch`/`ESummary`: `GET efetch.fcgi?db=pubmed&id=<PMIDs>&retmode=xml` → full metadata incl. `<ArticleTitle>`, `<AbstractText>`, `<ArticleId IdType="doi">`, `<Journal>`, `<PubDate>`/`<ArticleDate>` (online-first via `<ArticleDate DateType="Electronic">`), `<AuthorList>`, `<MeshHeadingList>`, `<PublicationTypeList>`.
- **Climate-relevance control:** build the `term` with a constrained climate clause AND-ed to the broad query, e.g. `("climate change"[MeSH Terms] OR "global warming"[tiab] OR "heat wave"[tiab] OR "extreme heat"[tiab]) AND (health OR mortality OR ...)`, and post-filter on MeSH headings / seed terms so health-only papers without a climate signal are dropped. Route papers lacking a climate MeSH/term to LEAD or discard.
- Map → `CandidateRecord`: title, DOI, authors, `PublicationInfo.venue`=journal, `online_publication_date`=ArticleDate(Electronic) else PubDate, `raw_publication_date`, abstract. Pagination via `retstart`/`retmax`. Sorting by `sort=pub_date`.

**6. Implementation.** New `scan_pubmed(...)` (two HTTP calls) in `clients.py`; new `id == "pubmed"` branch in `scan_source`. New `kind: scholarly_api`, `source_type: peer_reviewed_journal`, but with a dedicated climate-term builder. Helper: `_pubmed_efetch_records(xml)`. Env: `NCBI_API_KEY` (optional). Failure (HTTP, empty ESearch) → `source_error`. Manual-review: papers with health MeSH but no climate signal.

**7. Data quality.** TOP only if a climate signal is present; otherwise drop. DOI from ArticleId; merge by DOI. Missing DOI is common in PubMed → keep PMID in `discovered_via.url` (`pubmed.ncbi.nlm.nih.gov/<PMID>`) and let dedup fall back to title. Missing abstract → missing_reason.

**8. Security.** `NCBI_API_KEY` in `.env`/Fly secrets/AWS Secrets Manager. No OAuth. Register tool+email to protect the deployment IP.

**9. Operational impact.** Two round-trips per query; with a key, ~10 rps is ample. Add ~2–4 s. Run in full mode. Cache PMID→record per run. Nonfatal failures.

**10. Recommendation.** **Add (P1). Implementation: medium (2-step + relevance filter). Access: low. Coverage value: medium-high for health.** Bottom line: the only good route to climate-health papers — but it needs a disciplined climate-term filter to avoid noise.

---

### 4.3 Europe PMC — TOP + ENRICH — **P0/P1**

**1. What it is.** EBI's index of 40M+ records unifying PubMed (MED), PMC full text, and preprints (PPR: bioRxiv/medRxiv etc.), plus agricultural and patent literature, with abstracts, MeSH, citation counts, full-text-availability flags, and DOIs/PMIDs/PMCIDs.

**2. Why add it.** A single free, keyless endpoint covering biomedical + preprints + full-text flags. Complements PubMed by adding preprints and full-text availability and by offering a simpler one-call REST interface. Often a faster path to the same climate-health coverage with less ceremony than E-utilities.

**3. Access path.** Public REST, **free, no key, no registration** (EBI docs: `europepmc.org/RestfulWebService`; rOpenSci `europepmc`). Optional `email` param for courtesy.

**4. Cost & licensing.** Free. Metadata reuse permitted; full-text reuse follows each article's license (the API exposes license + `isOpenAccess`). No deployment-specific restrictions.

**5. Technical integration.** `GET https://www.ebi.ac.uk/europepmc/webservices/rest/search?query=<lucene>&format=json&pageSize=N&cursorMark=*&resultType=core`.
- **Date window:** Lucene field `FIRST_PDATE:[2026-04-01 TO 2026-04-30]` (year-only also valid; `3000` = "to present"). Source filter `SRC:MED`/`SRC:PPR`. Publication type `PUB_TYPE:"…"`.
- `resultType=core` returns full metadata: title, authorList, journalInfo (title + print/electronic dates), doi, pmid/pmcid, abstractText, MeSH, citedByCount, `isOpenAccess`, `fullTextUrlList`.
- Sorting: `sort=P_PDATE_D desc` or `sort_date:y`. Pagination via `cursorMark`.
- Map → `CandidateRecord`: title, doi, authors, venue=journalInfo.journal.title, `online_publication_date` (electronic pub date), abstract, `open_access`=isOpenAccess, full-text URL → `discovered_via.url`.

**6. Implementation.** New `scan_europe_pmc(...)`; `id == "europe_pmc"` branch. `kind: scholarly_api`. No env var (optional `DEEPGREEN_CONTACT_EMAIL` reused as courtesy email). Helper `_europepmc_records(json)`. Failures → `source_error`.

**7. Data quality.** TOP for MED-sourced peer-reviewed records with a climate signal; **PPR-sourced records → PREPRINT bucket** (set `source_type=preprint` for those items). Dual-purpose: also usable as ENRICH (full-text availability + OA status) keyed by DOI/PMID. Merge by DOI; Europe PMC and PubMed will overlap heavily — dedup handles it.

**8. Security.** No secrets. Optional email only.

**9. Operational impact.** One call per query; very fast. Run every time. Nonfatal.

**10. Recommendation.** **Add (P0 for discovery breadth; doubles as enrichment). Implementation: low. Access: low. Coverage value: medium-high.** Bottom line: the easiest biomedical+preprint win; arguably do this before raw E-utilities.

---

### 4.4 arXiv — PREPRINT only — **P0**

**1. What it is.** Cornell's preprint repository; the API returns Atom XML with title, authors, abstract, categories, DOI (if author-supplied), `journal_ref`, and submission/update timestamps. Categories relevant here: `physics.ao-ph` (atmospheric/oceanic), `physics.geo-ph`, `stat.ME`/`stat.AP`/`stat.ML`, `cs.LG`, `econ.*`, `q-bio.PE`.

**2. Why add it.** Captures **non-Earth-sciences preprints** (climate ML, statistics of extremes, climate econ, atmospheric physics) that EarthArXiv (Earth-sciences only) misses. Strictly a preprint feed — never a final peer-reviewed candidate.

**3. Access path.** Public, **no API key, free** (`info.arxiv.org/help/api`). Polite limit: **~1 request / 3 seconds**; descriptive `User-Agent` requested. ToU: `info.arxiv.org/help/api/tou.html` (descriptive metadata only; don't circumvent rate limits).

**4. Cost & licensing.** Free. Metadata reuse fine. Don't redistribute full PDFs. No deployment terms beyond rate limits; concurrent workflows can trip 429s, so a single sequential client is safest.

**5. Technical integration.** `GET http://export.arxiv.org/api/query?search_query=<q>&sortBy=submittedDate&sortOrder=descending&start=0&max_results=N`.
- Climate query: `(cat:physics.ao-ph OR cat:stat.AP) AND (abs:climate OR abs:"global warming" OR abs:"extreme heat")`. Date filtering: arXiv supports `submittedDate:[YYYYMMDDHHMM TO YYYYMMDDHHMM]` in `search_query`; otherwise sort by `submittedDate` and post-filter (the existing date-window pattern).
- Atom fields → `CandidateRecord`: `title`, `summary`→abstract, `author/name`, `arxiv:doi`→doi (often null), `link[@title='pdf']`/`id`→url, `published`/`updated`→`online_publication_date`, `arxiv:primary_category`→audit. `venue`="arXiv".

**6. Implementation.** New `scan_arxiv(...)` (Atom parse — reuse the existing `ET`/`_text` helpers). Could also be modeled as a `preprint_feed` if a per-category Atom URL is put in config, but a dedicated client is cleaner because of category + date query construction. `kind: preprint_feed` (new client dispatched by `id == "arxiv"`). No env var. Map categories in a `_ARXIV_CLIMATE_CATEGORIES` constant. Failures → `source_error`.

**7. Data quality.** **PREPRINT bucket always.** Never a TOP candidate unless/until a peer-reviewed publication is verified (e.g., `journal_ref` populated AND a DOI resolving to a journal article via Crossref). Merge by arXiv id/DOI; if a later journal version is found via OpenAlex/Crossref, the journal record wins and the arXiv mention merges into `discovered_via`. Missing DOI is normal → keep arXiv URL.

**8. Security.** None.

**9. Operational impact.** With the 1-per-3s courtesy delay, a few category queries add ~10–15 s — so run **only in full mode**. Cache per run. Nonfatal.

**10. Recommendation.** **Add (P0). Implementation: low. Access: low. Coverage value: medium (high for ML/stats/econ preprints).** Bottom line: cheap preprint breadth; just keep it firmly in the preprint bucket and throttle it.

---

### 4.5 DataCite — DATA + reports — **P1**

**1. What it is.** The DOI registry for research **datasets, software, reports, preprints, and some articles**, with rich `resourceTypeGeneral` typing. Public REST returns JSON:API records with titles, creators, publisher, publicationYear, dates, descriptions, types, and related identifiers.

**2. Why add it.** Surfaces **official institutional data releases and reports** that have DOIs (e.g., model/data outputs, agency reports) which the article-only feeds miss. Complements NSIDC/NCEI by catching DOI-minted releases across many institutions.

**3. Access path.** Public REST, **free, no auth** for harvesting (Introduction: `support.datacite.org/docs/api`). Authentication only needed to *create* DOIs. OAI-PMH and DataCite Commons also available for bulk.

**4. Cost & licensing.** Free. Metadata is CC0. No redistribution limits. No deployment-specific terms.

**5. Technical integration.** `GET https://api.datacite.org/dois?query=<lucene>&resource-type-id=<type>&published=YYYY&page[size]=N&page[cursor]=1&sort=-updated`.
- **Type filter:** `resource-type-id=dataset|text|software|report|preprint` (note: reports are typically `resourceTypeGeneral=Text` with `resourceType=Report`, so also filter on `query=types.resourceType:Report`). For Hot Science, **whitelist `dataset`, `report`, and `text/report`; exclude `journal-article`** so DataCite doesn't pollute the paper top-candidate pool (those come from OpenAlex/Crossref).
- **Date:** `published=2026` (year) or `query=publicationYear:2026`; finer month filtering isn't first-class, so post-filter on the `dates` array (`dateType:Issued`/`Available`). Source: `support.datacite.org/docs/how-can-i-query-the-rest-api-to-retrieve-results-for-a-specific-date-range`.
- Climate terms via `query=climate OR "sea ice" OR permafrost`. Cursor pagination (`page[cursor]`). Map → `CandidateRecord` with `source_record_type` = resourceTypeGeneral, `venue` = publisher, `online_publication_date` from `dates[Issued]`, url = `doi.org/<doi>`.

**6. Implementation.** New `scan_datacite(...)`; `id == "datacite"` branch. `kind: scholarly_api` but `source_type: institutional_data_release`. Helper `_datacite_records(json)` with a type allowlist. No env var. Failures → `source_error`.

**7. Data quality.** **DATA bucket** (eligible institutional data release) with **source-type + date verification**; **never** routed into the peer-reviewed paper pool. Datasets/software → DATA; reports → DATA (attribution-report-adjacent). DOI conflicts: if a DataCite DOI duplicates an OpenAlex article DOI, the article wins. Missing description/date → missing_reason and route to manual review rather than top candidate.

**8. Security.** None.

**9. Operational impact.** One-to-few calls; fast. Run in full mode. Nonfatal.

**10. Recommendation.** **Add (P1). Implementation: medium (type whitelisting). Access: low. Coverage value: medium for data releases.** Bottom line: the right tool for DOI-minted data/reports — keep it strictly out of the paper pool.

---

### 4.6 EurekAlert — LEAD (manual-review press) — **P2/P3**

**1. What it is.** AAAS's embargoed/real-time science press-release service. Provides **18 topic RSS feeds** (incl. earth science / environment / atmospheric science) of news releases. No open data API.

**2. Why add it.** Early discoverability of newsworthy climate findings, often before the paper is indexed. But releases are PR, not papers.

**3. Access path.** RSS feeds (listing at `eurekalert.org/rss.php`); **no registration to read RSS**. There is **no public structured API**; scraping the site is discouraged by terms.

**4. Cost & licensing.** Free to subscribe to RSS. **Terms forbid wholesale "content aggregation" and reproducing full release text without permission** (registered journalists excepted); **attribution to "EurekAlert!, operated by AAAS" is required** (`eurekalert.org/termsAndConditions`, `archive.eurekalert.org/rss.php`). → **Store only headline + link + date; never store/redisplay full release text.**

**5. Technical integration.** Reuse `scan_rss` with the topic feed URL(s). Pull title, link, pubDate, short description. **Resolve to the primary paper:** the release usually names the journal + DOI in the body; a follow-up step should fetch the release page, extract the DOI/journal, and look that DOI up via Crossref/OpenAlex to create the real candidate. If no DOI can be resolved, keep as a LEAD for human review only.

**6. Implementation.** Config-only for ingestion (`kind: rss`, `source_type: popular_press`, the topic feed URL). Add a small `resolve_press_lead()` helper (DOI/journal extraction → Crossref lookup) — can live in a new `press_resolution.py` to keep `clients.py` lean. Failures → `source_error`.

**7. Data quality.** **LEAD only.** EurekAlert items are **always manual-review until the underlying peer-reviewed paper is confirmed.** Once resolved to a DOI, the resolved Crossref/OpenAlex record becomes the candidate and the EurekAlert mention is recorded in `discovered_via`. Media-only items with no paper → never a top candidate.

**8. Security.** None.

**9. Operational impact.** One RSS fetch; fast. The resolution step adds Crossref lookups. Run in full mode. Nonfatal. Show as "press leads (manual review)" in UI.

**10. Recommendation.** **Add later (P2), or P3 if resolution tooling isn't ready. Implementation: medium (needs resolution). Access: low. Coverage value: low-medium (discoverability, not coverage).** Bottom line: useful as an early-warning lead feed, but treat it as journalism, not evidence — store headlines only and always resolve before promoting.

---

### 4.7 NSIDC — DATA + LEAD — **P1**

**1. What it is.** NASA DAAC + NOAA@NSIDC cryosphere data center. Publishes (a) **news & data releases** (RSS at `nsidc.org/news-analyses/news-stories` — "Get RSS feed of NSIDC news & stories"), (b) **Sea Ice Today / Ice Sheets Today** analysis posts, and (c) **dataset releases** (many with DataCite DOIs) covering sea ice, glaciers, snow, permafrost, ice sheets.

**2. Why add it.** Authoritative cryosphere monitoring and data releases that map directly to the `cryosphere` domain. Complements Copernicus C3S on the ice side.

**3. Access path.** **RSS, free, no key.** Dataset discovery also via NASA Earthdata CMR (Common Metadata Repository) and DataCite. ⚠️ **Continuity risk:** NSIDC announced reduced Sea Ice Today services from 2025-10-15 due to non-renewed funding, plus a sensor transition (SSMIS→JAXA AMSR2). Feeds may degrade.

**4. Cost & licensing.** Free; NSIDC/NASA data are openly licensed. NASA data access (CMR) may require a free Earthdata login for some granules, but the **news RSS needs nothing**.

**5. Technical integration.** Reuse `scan_rss` against the news RSS feed. Distinguish item types by the feed's category/template: **News Release / data release → DATA; analysis/"Sea Ice Today" posts → LEAD (analysis, not a paper).** For actual dataset DOIs, rely on the DataCite client (4.5) filtered to NSIDC's publisher/prefix, or Earthdata CMR if dataset-level granularity is needed later.

**6. Implementation.** Config-only ingestion: `kind: institutional_feed`, `source_type: institutional_data_release`, the RSS URL, `enabled: true`. Add the NSIDC DataCite prefix to the DataCite client's optional `provider`/`client-id` filter for dataset releases. Failures → `source_error`.

**7. Data quality.** Data releases → DATA (eligible, with date verification). Analysis posts → LEAD/manual review (they're institutional analysis, not peer-reviewed). Never auto-promote an analysis post to a peer-reviewed top candidate.

**8. Security.** None for RSS. (Earthdata login only if CMR granule access is added later.)

**9. Operational impact.** One RSS fetch; fast. Run every time. Nonfatal. Flag the funding/continuity risk in the run report.

**10. Recommendation.** **Add (P1). Implementation: low. Access: low. Coverage value: medium (high for cryosphere).** Bottom line: turn on the news RSS now; lean on DataCite for the DOI'd datasets; watch for feed degradation.

---

### 4.8 NOAA / NCEI — DATA — **P0 (replace generic feed)**

**1. What it is.** NOAA's National Centers for Environmental Information: US/global climate records, monthly climate reports (National/Global Climate Report), and data services. **Climate.gov is archived as of 2025-06-25** (content frozen, redirects to `noaa.gov/climate`); the **Billion-Dollar Disasters** product was retired after CY2024. Data access remains via NCEI services and the Climate Data Online (CDO) API.

**2. Why add it.** Broad NOAA agency RSS is generic PR, not climate-specific, and Climate.gov news is archived. The packaged project now points `noaa_climate` at NCEI's news RSS; deeper NCEI climate-report and data-release surfaces should be added next to keep authoritative US climate-record releases flowing.

**3. Access path.**
- **NCEI monthly climate reports / news:** web pages and (where available) RSS — free, no key. Best institutional-data-release surface now that Climate.gov is frozen.
- **NCEI Access Data Service** (`ncei.noaa.gov/access/services/data/v1`, `…/search/v1`): free, no token for many datasets.
- **CDO API v2** (`ncei.noaa.gov/cdo-web/api/v2/`): **token required** (free; request at `ncdc.noaa.gov/cdo-web/token`); limited to **5 req/s and 10,000 req/day**.

**4. Cost & licensing.** Free. US-government data, freely reusable. No deployment terms beyond the CDO token rate caps. **Governance note:** NOAA climate communications are being defunded/archived under 2025 executive actions — expect feed instability and document the provenance/retirement caveats.

**5. Technical integration.**
- For **discovery of releases**: reuse `scan_rss`/`institutional_feed` against NCEI's news/report feed (and keep `noaa.gov/climate` content as a secondary). Items are DATA.
- For **data values** (optional, later): a `scan_ncei_cdo(...)` client using the token to pull e.g. Global Summary of the Month anomalies — but this returns *data*, not discoverable "releases," so it's lower priority for Hot Science discovery.
- Map RSS items → `CandidateRecord` as institutional_data_release with `online_publication_date` from pubDate.

**6. Implementation.** The existing `noaa_climate` source is repointed to the NCEI news feed; keep the note recording the Climate.gov archival date and the Billion-Dollar Disasters retirement. Optionally add a token-gated `ncei_cdo` source (`kind: institutional_feed`/new client) with env `NOAA_CDO_TOKEN`. Failures -> `source_error`.

**7. Data quality.** DATA bucket; **date verification required** (use the report's publication date, not the data period). Monthly reports are eligible institutional releases. Don't promote a data table to a "paper."

**8. Security.** `NOAA_CDO_TOKEN` only if the CDO client is added — `.env`/Fly/AWS Secrets Manager. No token for plain RSS.

**9. Operational impact.** RSS is fast; CDO calls (if added) respect 5 rps. Run every time (RSS). Nonfatal. Surface the archival/retirement caveat in UI/notes.

**10. Recommendation.** **Add now (P0) — at minimum repoint the existing NOAA feed to a climate-specific NCEI surface. Implementation: low (RSS) / medium (CDO). Access: low (RSS) / low (free token). Coverage value: medium.** Bottom line: the generic feed is the weakest current source; swap it for NCEI's climate reports and note the political-archival risk.

---

### 4.9 AGU / Wiley journals — TOP — **P0 (config-only)**

**1. What it is.** AGU's 24 peer-reviewed geoscience journals, hosted on Wiley Online Library (`agupubs.onlinelibrary.wiley.com`), each with a per-journal RSS channel ("Get RSS Feed"). Many are gold OA.

**2. Why add it.** Core geoscience coverage (atmospheres, oceans, hydrology, biogeochemistry, geohealth) currently absent. These journals carry a large share of high-impact climate findings.

**3. Access path.** **Metadata: free.** Per-journal **RSS feeds (free, no key)** + **Crossref/OpenAlex ISSN backfill (free, no key)**. Full-text TDM requires Wiley's **TDM API + a Wiley TDM Client Token + an institutional subscription** (June 2025 Wiley TDM Client Python package) — **not needed** for Hot Science discovery, which is metadata-only.

**4. Cost & licensing.** Metadata free; no license needed for discovery. Full-text only under Wiley TDM license (skip). No deployment terms for metadata.

**5. Technical integration.** **None new.** Add each journal as a `peer_reviewed_journal` source with `kind: rss`, its RSS `url`, and its `issns`. The existing `_journal_source_has_issns` → `scan_journal_by_issn` then auto-queries OpenAlex **and** Crossref by ISSN+month and merges the RSS — giving DOIs, abstracts, online dates, authors, OA status.

**Priority journals + ISSNs** (verify each against the journal's Wiley landing page / OpenAlex `issn` lookup; print / online):
| Journal | ISSN(s) |
|---|---|
| Geophysical Research Letters | 0094-8276 / 1944-8007 |
| JGR: Atmospheres | 2169-897X / 2169-8996 |
| JGR: Oceans | 2169-9275 / 2169-9291 *(confirmed)* |
| JGR: Earth Surface | 2169-9003 / 2169-9011 |
| Earth's Future | 2328-4277 (online) |
| GeoHealth | 2471-1403 (online) |
| Global Biogeochemical Cycles | 0886-6236 / 1944-9224 |
| Water Resources Research | 0043-1397 / 1944-7973 |
| Reviews of Geophysics | 8755-1209 / 1944-9208 |

**6. Implementation.** Pure `hot_science_sources.yaml` additions (9 entries). No `clients.py` change. RSS URL pattern: each journal page exposes an RSS channel link; confirm the exact feed URL per journal. Tests: a fixture per representative journal confirming ISSN-backfill produces records.

**7. Data quality.** TOP. Dedup by DOI with OpenAlex/Crossref (the backfill already merges). Online-first dates come through Crossref `published-online`. Missing abstract handled by existing logic.

**8. Security.** None.

**9. Operational impact.** Each journal triggers OpenAlex+Crossref+RSS calls — adds up across 9 journals. Run in full mode, and rely on the existing per-source `max_results` budgeting. Nonfatal.

**10. Recommendation.** **Add now (P0). Implementation: low (config). Access: low (metadata free). Coverage value: high.** Bottom line: zero code, high yield — just add ISSNs and the backfill does the rest.

---

### 4.10 EGU / Copernicus Publications journals — TOP — **P0 (config-only)**

**1. What it is.** EGU's gold-open-access journals published by Copernicus Publications (CC BY), each with its own site (e.g., `acp.copernicus.org`, `tc.copernicus.org`) exposing Articles + Preprints and RSS feeds.

**2. Why add it.** Premier European Earth-system venues (atmospheric chemistry, cryosphere, hydrology, biogeosciences, earth-system dynamics/data) — central to Hot Science intent and fully open access.

**3. Access path.** **Free, no key.** Per-journal **RSS** + **Crossref/OpenAlex ISSN backfill**. Copernicus also exposes structured metadata, but the ISSN backfill is sufficient.

**4. Cost & licensing.** Fully free/OA (CC BY). No deployment terms.

**5. Technical integration.** Same as AGU/Wiley: config-only with `issns`.

**Priority journals + ISSNs** (print / web; confirmed ones noted, others verify):
| Journal | ISSN(s) |
|---|---|
| Earth System Dynamics (ESD) | 2190-4979 / 2190-4987 *(confirmed)* |
| Earth System Science Data (ESSD) | 1866-3508 / 1866-3516 |
| Climate of the Past (CP) | 1814-9324 / 1814-9332 |
| The Cryosphere (TC) | 1994-0416 / 1994-0424 *(confirmed)* |
| Atmospheric Chemistry and Physics (ACP) | 1680-7316 / 1680-7324 *(confirmed)* |
| Biogeosciences (BG) | 1726-4170 / 1726-4189 |
| Hydrology and Earth System Sciences (HESS) | 1027-5606 / 1607-7938 |
| Natural Hazards and Earth System Sciences (NHESS) | 1561-8633 / 1684-9981 |
| Ocean Science (OS) | 1812-0784 / 1812-0792 |
| Geoscientific Model Development (GMD) | 1991-959X / 1991-9603 |

**6. Implementation.** Pure YAML additions (10 entries). **GMD special handling:** GMD is methods/model-description heavy; add a per-source relevance guard so pure model-description papers (no climate finding) are routed to manual review / lower priority rather than auto-TOP. This is best done in `annotate_retrieval_signals` / semantic scoring rather than the client.

**7. Data quality.** TOP (except GMD methods-only → manual review). Dedup by DOI. Note: Copernicus DOIs also appear in DataCite — dedup prevents double counting.

**8. Security.** None.

**9. Operational impact.** As with AGU — 10 journals × (OpenAlex+Crossref+RSS). Full mode. Nonfatal.

**10. Recommendation.** **Add now (P0). Implementation: low (config). Access: low. Coverage value: high.** Bottom line: config-only, fully OA, directly on-intent — with a methods filter on GMD.

---

### 4.11 Springer Nature Metadata API — TOP — **P2 (legal review first)**

**1. What it is.** Springer Nature's developer APIs (`dev.springernature.com`): **Metadata API** and newer **Meta API** (versioned metadata for ~16M documents) plus an **Open Access API** (metadata + full text where OA). Covers SN journals broadly.

**2. Why add it.** Reaches SN climate journals **beyond the current Nature-family RSS feeds** — e.g., Climatic Change, Climate Dynamics, Nature Water, Nature Sustainability, Communications Earth & Environment, Scientific Reports — by query rather than per-journal RSS. Differs from the existing Nature RSS sources (which only cover four titles) by enabling cross-journal date+keyword search.

**3. Access path.** **Free API key** via the developer portal (register; key visible after sign-up). Free tier exists; **Open Access API free tier throttles at ~100 hits/min** with a single key. **Premium plan** (higher limits, advanced queries, multiple keys) targets institutions/government/enterprise — **pricing not public; contact Springer Nature Data Solutions** (`datasolutions.springernature.com`; technical contact `supportapi@springernature.com`).

**4. Cost & licensing.** Free tier free, **but the free APIs are for "non-commercial use."** ⚠️ **Governance:** BEF must confirm whether its deployment qualifies as non-commercial; if not, Premium licensing/contract is required. Rate limit ~100 hits/min (OA API free tier). Metadata storage permitted under the API terms; full-text only for OA content. These terms apply equally to Fly and AWS.

**5. Technical integration.** `GET https://api.springernature.com/meta/v2/json?q=<query>&api_key=<KEY>&s=<start>&p=<page>` (Meta API) or `…/metadata/json`. Query supports keyword + constraints; date via `onlinedatefrom`/`onlinedateto` or `year:` and `journalid`/ISSN constraints. Returns title, creators, DOI, publicationName, abstract (where available), online date, openAccess flag. Pagination via `s`/`p`. Map → `CandidateRecord` directly.

**6. Implementation.** New `scan_springer(...)`; `id == "springer_nature"` branch; `kind: scholarly_api`. Env: `SPRINGER_NATURE_API_KEY`. Helper `_springer_records(json)`. Failures → `source_error`. **Largely redundant with Crossref/OpenAlex ISSN backfill** — so an alternative, lower-friction path is to simply add the target SN journals' ISSNs as config-only backfill sources (like AGU/EGU) and skip the SN API entirely. Prefer that unless SN abstracts/coverage prove materially better.

**7. Data quality.** TOP. Dedup by DOI with OpenAlex/Crossref. Scientific Reports is huge and broad → apply the climate relevance filter strictly to avoid flooding.

**8. Security.** `SPRINGER_NATURE_API_KEY` in `.env`/Fly/AWS Secrets Manager. No OAuth.

**9. Operational impact.** 100 hits/min is the ceiling on the free tier — keep query count modest; full mode only. Cache per run. Nonfatal.

**10. Recommendation.** **Add later (P2) — and only after legal reviews the non-commercial clause; otherwise cover the same journals via ISSN backfill (P0, no terms issue). Implementation: medium. Access: medium (key easy, terms not). Coverage value: medium.** Bottom line: the ISSN-backfill route gets most of the value with none of the licensing risk — make SN API a deliberate, reviewed choice, not a default.

---

### 4.12 PLOS — TOP (filtered) — **P1**

**1. What it is.** PLOS's Solr-backed Search API over all PLOS OA journals (PLOS ONE, PLOS Climate, PLOS Water, PLOS Sustainability and Transformation, PLOS Biology, etc.). Returns DOI (`id`), title, author, abstract, journal, `publication_date`.

**2. Why add it.** Direct, free access to **PLOS Climate / PLOS Water** and climate-relevant PLOS ONE articles, with precise date queries. Complements OpenAlex for OA breadth.

**3. Access path.** Public Solr API, **free, no key** (older docs mention registration, but the API serves keyless). Rate limit: **7200/day, 300/hour, 10/min, max 5 concurrent connections**; contact `api@plos.org` for more (`api.plos.org/solr/faq`). Attribution to PLOS requested.

**4. Cost & licensing.** Free. PLOS content is CC BY — abstracts/metadata reusable with attribution. No deployment terms beyond rate limits.

**5. Technical integration.** `GET http://api.plos.org/search?q=<query>&fq=doc_type:full&fq=publication_date:[2026-04-01T00:00:00Z TO 2026-04-30T23:59:59Z]&fl=id,title,author,abstract,journal,publication_date&rows=N&start=0&wt=json`.
- **Date window is server-side** via the `publication_date:[… TO …]` range (`api.plos.org/solr/search-fields`).
- `doc_type:full` excludes partial-document index entries. Restrict to relevant journals with `fq=journal_key:(PLoSClimate OR PLoSWater OR PLoSONE)` and **apply the climate relevance filter** so broad PLOS ONE biology/ecology hits don't flood TOP.
- Map → `CandidateRecord`: `id`→doi, title, author, abstract, journal→venue, publication_date→online_publication_date, url=`doi.org/<id>`.

**6. Implementation.** New `scan_plos(...)`; `id == "plos"` branch; `kind: scholarly_api`. Helper `_plos_records(json)`. No env var. Failures → `source_error`. Relevance: require a seed-term/domain hit in title/abstract before TOP eligibility for PLOS ONE.

**7. Data quality.** TOP for climate-relevant items; route broad bio/ecology PLOS ONE hits without a climate signal to manual review. Dedup by DOI. PLOS DOIs also in OpenAlex — dedup merges.

**8. Security.** None.

**9. Operational impact.** 5 s recommended latency per query; a few queries add ~10 s — full mode. Respect 10/min. Nonfatal.

**10. Recommendation.** **Add (P1). Implementation: low-medium (relevance filter). Access: low. Coverage value: medium.** Bottom line: cleanest route to PLOS Climate/Water; gate PLOS ONE behind a climate filter.

---

### 4.13 CORE — ENRICH / repository discovery — **P2 (enrichment only)**

**1. What it is.** The world's largest aggregator of OA research (300M+ metadata records, 40M+ full texts) harvested from 10,000+ repositories, journals, and preprint servers. API v3 (`api.core.ac.uk/v3`).

**2. Why add it.** Full-text discovery and repository copies for papers we've already found by DOI; secondary discovery of OA works. **Not** a clean primary-paper source because it returns many repository duplicates of the same DOI.

**3. Access path.** **Free API key by registration** at `core.ac.uk/services/api` (under a minute; CORE API is free and "does not require registration subject to rate limits," but a key gives a better rate). **Faster institutional/enterprise rate is typically paid**; 30-day free trial for Institution/Enterprise. Commercial use allowed under T&C.

**4. Cost & licensing.** Free tier free (with rate quotas — historically strict, e.g., batch search ~1 req/10 s on v2; v3 uses token-bucket quotas tied to the key). Higher throughput is paid — **contact CORE via the registration/contact form for pricing**. Metadata reuse permitted under T&C.

**5. Technical integration.** `POST/GET https://api.core.ac.uk/v3/search/works?q=<query>&limit=N` with `Authorization: Bearer <CORE_API_KEY>`. Filters by year range, language, and `fullText` presence. Returns title, authors, DOI, year, abstract, downloadUrl, repository info. **Use after DOI discovery** (`/works/<id>` or DOI lookup) to attach a repository full-text location, or as a de-duped discovery pass.

**6. Implementation.** New `enrich_core(record)` in `access.py` (or `clients.py`) rather than a discovery source, keyed by DOI. If used for discovery, dedup aggressively by DOI/title so repository copies collapse onto the canonical record. Env: `CORE_API_KEY`. Failures → log + skip (enrichment failures should be nonfatal and not create `source_error` candidates).

**7. Data quality.** **ENRICH first.** If used as discovery, never TOP without a resolved DOI; collapse repository duplicates into `discovered_via`. DOI conflicts: canonical publisher DOI wins.

**8. Security.** `CORE_API_KEY` in `.env`/Fly/AWS Secrets Manager.

**9. Operational impact.** Quota-limited — keep calls minimal; admin/full mode only. Cache by DOI. Nonfatal.

**10. Recommendation.** **Add later (P2), as enrichment. Implementation: medium. Access: medium (free key, paid for speed). Coverage value: low-medium (high for full-text location).** Bottom line: valuable for finding OA PDFs of paywalled papers, but Unpaywall covers most of that need more cheaply — adopt CORE only if Unpaywall gaps appear.

---

### 4.14 DOAJ — whitelist / ENRICH — **P1 (as quality signal)**

**1. What it is.** Directory of Open Access Journals — a vetted index of OA journals and their articles (not-for-profit). Public Search API (`doaj.org/api/v3`), plus OAI-PMH and a full Journal CSV.

**2. Why add it.** Best used as a **journal-quality whitelist/signal** (is this a DOAJ-indexed, vetted OA journal?) and secondarily for OA article discovery. Helps the rubric trust/relevance signals and filter predatory venues.

**3. Access path.** **Public Search API, no key for GET** (key only for depositing). Rate limit **2 req/s with bursts up to 5**; **max 1000 records per search** (use OAI-PMH or the data dump for bulk). `doaj.org/api/v3/docs`.

**4. Cost & licensing.** Free, not-for-profit. Metadata openly reusable. Journal CSV (≤30-day freshness) downloadable without login. No deployment terms beyond rate limits.

**5. Technical integration.**
- **Whitelist (recommended):** periodically download the **Journal CSV** (`doaj.org/docs/journal-csv`) → build a set of DOAJ ISSNs → use as a quality flag on candidates (set an audit signal `journal_in_doaj=true`).
- **Article search (optional):** `GET https://doaj.org/api/v3/search/articles/<escaped-query>?page=1&pageSize=N` with ElasticSearch syntax incl. `bibjson.year:[2026 TO 2026]`. Returns DOI, title, authors, abstract, journal, year, links.

**6. Implementation.** Preferred: a small `doaj_whitelist.py` that loads the CSV ISSNs (cached, refreshed weekly) and annotates records — no per-run API calls. Optional `scan_doaj(...)` for discovery. No env var. Whitelist load failure → log + skip (don't fail the run).

**7. Data quality.** As a **signal/whitelist**, not a standalone TOP source. If used for discovery, TOP only with a climate signal; dedup by DOI. Note Unpaywall already returns `journal_is_in_doaj` — so DOAJ-as-signal may be obtainable for free as a side effect of Unpaywall enrichment.

**8. Security.** None.

**9. Operational impact.** CSV whitelist = zero per-run latency. Discovery API respects 2 rps. Nonfatal.

**10. Recommendation.** **Add (P1) as a whitelist/quality signal, not a primary source. Implementation: low. Access: low. Coverage value: low-medium (quality, not breadth).** Bottom line: cheapest as a journal-quality flag; you may even get it free via Unpaywall's `journal_is_in_doaj`.

---

### 4.15 Unpaywall — ENRICH (DOI-keyed) — **P0**

**1. What it is.** OA status + full-text location service over 50,000+ publishers/repositories, keyed by DOI. Returns OA status, best OA location, all OA locations, license, host type, and journal/DOAJ flags.

**2. Why add it.** Verifies open-access status and finds free full-text PDFs **after** a DOI is discovered — directly serving `access.py`. Lets Hot Science attach a legitimate readable link to each candidate.

**3. Access path.** **Free, no key.** **Email is required** as a URL param. Endpoint `https://api.unpaywall.org/v2/{doi}?email=<addr>`. Suggested limit **100,000 requests/day**; bulk via the data snapshot (`unpaywall.org/products/snapshot`). Docs: `unpaywall.org/products/api`, `unpaywall.org/data-format`.

**4. Cost & licensing.** Free. Email used only for usage tracking/notifications. Metadata reusable; the API points to OA copies (it doesn't redistribute full text itself). No deployment terms beyond the daily soft limit.

**5. Technical integration.** Per-DOI lookup after discovery: `GET https://api.unpaywall.org/v2/10.xxxx/yyyy?email=$UNPAYWALL_EMAIL`. Returns `is_oa`, `oa_status` (gold/green/hybrid/bronze/closed), `best_oa_location{url, url_for_pdf, version, license, host_type}`, `oa_locations[]`, `journal_is_oa`, `journal_is_in_doaj`, `journal_issns`, `publisher`, `title`, `year`, `published_date`, `genre`, `has_repository_copy`. Map → `PublicationInfo.open_access` and an OA-location field on the record / `access.py` result.

**6. Implementation.** Wire into **`agents/hot_science/access.py`** as `verify_open_access(doi) -> OaResult`, called during the access/verification stage (not in the source scan). Env: `UNPAYWALL_EMAIL` (or reuse `DEEPGREEN_CONTACT_EMAIL`). Enrichment failures → log + skip (no `source_error` candidate; missing OA info just leaves `open_access=None`).

**7. Data quality.** **ENRICH only — never a discovery/TOP source.** Use strictly after DOI discovery. If `is_oa` and a `best_oa_location.url_for_pdf` exists, attach it; otherwise mark closed. Resolves the `open_access` field that OpenAlex/Crossref leave null.

**8. Security.** `UNPAYWALL_EMAIL` (low-sensitivity) in `.env`/Fly/AWS config; it's not a secret per se but keep it configurable.

**9. Operational impact.** One call per unique DOI; batch over the final candidate set, not the raw set, to stay well under 100k/day. Cache by DOI. Run in full mode (verification stage). Nonfatal.

**10. Recommendation.** **Add now (P0), as enrichment in `access.py`. Implementation: low. Access: low. Coverage value: high (for OA verification/links).** Bottom line: the canonical, free way to confirm OA and attach a readable PDF — bolt it onto the verification stage.

---

## 6. Cost / License / Access Complexity Table

| Source | Free? | Key/credential | License/approval | Access complexity | Impl. complexity | Coverage value | Priority |
|---|---|---|---|---|---|---|---|
| Semantic Scholar | Yes | Optional key (free) | None | Low | Low (enable) | High | P0 |
| PubMed/E-utilities | Yes | Optional key (free) | Register tool+email | Low | Medium | Med-High | P1 |
| Europe PMC | Yes | None | None | Low | Low | Med-High | P0 |
| arXiv | Yes | None | ToU (metadata only) | Low | Low | Medium | P0 |
| DataCite | Yes | None | None (CC0) | Low | Medium | Medium | P1 |
| EurekAlert | Yes (RSS) | None | AAAS terms (no full text; attribution) | Low | Medium (resolution) | Low-Med | P2/P3 |
| NSIDC | Yes | None | Open (NASA/NSIDC) | Low | Low | Medium | P1 |
| NOAA/NCEI | Yes | Token for CDO (free) | US-gov open | Low | Low/Med | Medium | P0 |
| AGU/Wiley | Yes (metadata) | None | None (metadata) | Low | Low (config) | High | P0 |
| EGU/Copernicus | Yes (OA) | None | CC BY | Low | Low (config) | High | P0 |
| Springer Nature API | Free tier | Key (free) | **Non-commercial clause** | Medium | Medium | Medium | P2 |
| PLOS | Yes | None | CC BY (attribution) | Low | Low-Med | Medium | P1 |
| CORE | Free tier | Key (free; paid for speed) | T&C | Medium | Medium | Low-Med | P2 |
| DOAJ | Yes | None (GET) | Open | Low | Low | Low-Med | P1 |
| Unpaywall | Yes | Email required | Terms (usage tracking) | Low | Low | High | P0 |

---

## 7. Environment Variables and Secrets Needed

| Env var | Source(s) | Required? | Sensitivity | Where it lives |
|---|---|---|---|---|
| `SEMANTIC_SCHOLAR_API_KEY` | Semantic Scholar | Recommended | Secret | `.env` → Fly secret → AWS Secrets Manager |
| `NCBI_API_KEY` | PubMed | Optional (raises 3→10 rps) | Secret | same |
| `SPRINGER_NATURE_API_KEY` | Springer Nature | Required if used | Secret | same |
| `CORE_API_KEY` | CORE | Required if used | Secret | same |
| `NOAA_CDO_TOKEN` | NCEI CDO (optional client) | Required if CDO client added | Secret | same |
| `UNPAYWALL_EMAIL` | Unpaywall | Required | Low (contact email) | `.env`/Fly/AWS config (can reuse `DEEPGREEN_CONTACT_EMAIL`) |
| `DEEPGREEN_CONTACT_EMAIL` | OpenAlex/Crossref/Europe PMC courtesy, Unpaywall fallback | Already used | Low | already configured |

No key needed: Europe PMC, arXiv, DataCite, EurekAlert (RSS), NSIDC (RSS), NOAA RSS, AGU/Wiley, EGU/Copernicus, PLOS, DOAJ (GET).

---

## 8. Code Changes Needed

**`config/hot_science_sources.yaml`**
- Keep `semantic_scholar` `enabled: true` for pilot breadth; add `SEMANTIC_SCHOLAR_API_KEY` when available to reduce 429s.
- Repoint `noaa_climate` `url` to an NCEI climate-report/news feed; update note (Climate.gov archived 2025-06-25; Billion-Dollar Disasters retired after CY2024).
- Add config-only sources: 9 AGU/Wiley journals + 10 EGU/Copernicus journals (`kind: rss`, `source_type: peer_reviewed_journal`, `issns: [...]`, RSS `url`).
- Add `europe_pmc`, `pubmed`, `arxiv`, `datacite`, `plos`, `nsidc`, (optional `springer_nature`, `ncei_cdo`, `doaj`) source entries.
- Add `eurekalert` (`kind: rss`, `source_type: popular_press`).

**`agents/hot_science/clients.py`** — add and dispatch (in `scan_source`, by `id`):
- `scan_semantic_scholar` — exists.
- `scan_europe_pmc`, `scan_pubmed` (ESearch→EFetch), `scan_arxiv` (Atom), `scan_datacite`, `scan_plos`, optional `scan_springer`, optional `scan_ncei_cdo`, optional `scan_doaj`.
- Helpers: `_europepmc_records`, `_pubmed_efetch_records`, `_arxiv_records`, `_datacite_records`, `_plos_records`, `_springer_records`.
- Constants: `_ARXIV_CLIMATE_CATEGORIES`, DataCite type allowlist, a shared climate-relevance guard used by PubMed/PLOS/Scientific Reports.
- If the file grows too large, split scholarly-API clients into `clients_scholarly.py` and feed/press into `clients_feeds.py`, re-exported from `clients.py`.

**`agents/hot_science/access.py`** — add `verify_open_access(doi)` (Unpaywall) and optional `enrich_core(record)`; call during the verification stage over the final candidate set.

**New modules (optional):** `press_resolution.py` (EurekAlert lead → DOI resolution), `doaj_whitelist.py` (CSV-based journal-quality flag).

**Buckets / routing:** ensure `source_type` drives bucketing — `preprint` (arXiv, Europe PMC PPR items) → PREPRINT; `institutional_data_release` (DataCite, NSIDC, NCEI) → DATA with date verification; `popular_press` (EurekAlert) → LEAD (resolve before TOP). Preserve `CandidateRecord`/`PublicationInfo`/`SourceMention` shapes; add at most one optional OA-location field if needed for Unpaywall results.

**Contract to preserve:** every new client must let exceptions bubble to `scan_source`'s handler (→ synthetic `source_error` record), never crash the run; enrichment helpers must fail soft (log + skip).

---

## 9. Tests Needed

Add tests **with** each new client (fixtures = saved API responses, no live network):

| New client | Fixture(s) | Assertions |
|---|---|---|
| `scan_europe_pmc` | `europepmc_search.json` | parses title/doi/authors/date/abstract/OA; date-window filter; PPR→preprint routing |
| `scan_pubmed` | `pubmed_esearch.json`, `pubmed_efetch.xml` | 2-step flow; DOI from ArticleId; MeSH/relevance filter drops non-climate health |
| `scan_arxiv` | `arxiv_query.atom` | Atom parse; category mapping; **always preprint bucket**; date post-filter |
| `scan_datacite` | `datacite_dois.json` | type allowlist (dataset/report; excludes journal-article); DATA bucket; date from `dates[Issued]` |
| `scan_plos` | `plos_search.json` | `publication_date` range; `doc_type:full`; climate filter on PLOS ONE |
| `scan_springer` (if built) | `springer_meta.json` | key header; date constraint; dedup by DOI |
| AGU/Wiley + EGU/Copernicus | reuse OpenAlex/Crossref ISSN fixtures | ISSN-backfill yields records for a representative journal |
| Unpaywall (`access.py`) | `unpaywall_doi.json` | OA status + best PDF location mapped; closed-access handled; failure → soft skip |
| EurekAlert resolution | `eurekalert_feed.xml` + `crossref_lookup.json` | lead stays LEAD until DOI resolves; full text never stored |

Plus a **`scan_source` failure test** per new `id` confirming an HTTP error produces a single `source_error` `CandidateRecord` and does not raise.

---

## 10. Deployment Steps for Fly.io (pilot)

1. Add secrets: `fly secrets set SEMANTIC_SCHOLAR_API_KEY=… NCBI_API_KEY=… UNPAYWALL_EMAIL=… [SPRINGER_NATURE_API_KEY=… CORE_API_KEY=… NOAA_CDO_TOKEN=…]`.
2. Confirm `DEEPGREEN_CONTACT_EMAIL` is set (used by OpenAlex/Crossref/Europe PMC courtesy + Unpaywall fallback).
3. Deploy the updated config + clients; run a single-month smoke test in full mode and inspect per-source progress events for `source_error` records.
4. Verify outbound egress reaches: `api.semanticscholar.org`, `eutils.ncbi.nlm.nih.gov`, `www.ebi.ac.uk`, `export.arxiv.org`, `api.datacite.org`, `api.plos.org`, `api.unpaywall.org`, `api.springernature.com`, `api.core.ac.uk`, `doaj.org`, `nsidc.org`, `ncei.noaa.gov`, `agupubs.onlinelibrary.wiley.com`, `*.copernicus.org`, `www.eurekalert.org`. (Hot Science's HTTP layer already has urllib→requests→curl fallback for finicky feeds.)
5. Watch for 429s on Semantic Scholar/arXiv; confirm the polite delays/retries hold.

> Note: the sandbox used to verify these APIs only had egress to package registries, so live API verification was done via official documentation, not live calls from this environment. Run the Fly smoke test to confirm egress.

---

## 11. Later Deployment Steps for AWS / DeepGreen

1. Move every secret in §7 to **AWS Secrets Manager** (or SSM Parameter Store, SecureString); inject via task role / environment at runtime — never bake into images.
2. Re-register the **NCBI tool name + email** and confirm the AWS egress IP isn't rate-throttled (NCBI blocks abusive IPs; the registered tool+email lifts blocks).
3. If outbound traffic egresses via a NAT gateway with a stable IP, note that Semantic Scholar/NCBI rate buckets are partly IP-aware — keep the per-source clients sequential.
4. Re-evaluate Springer Nature **non-commercial** terms against the production posture before enabling at scale; if commercial, execute a Premium contract first (Data Solutions).
5. Add Unpaywall/CORE enrichment behind a feature flag so production can disable third-party calls if a data-governance review requires it.
6. Cache layer (e.g., DynamoDB/Redis) for DOI→Unpaywall and PMID→record to stay under daily soft limits at production volume.

---

## 12. Risks and Governance Concerns

### Table 4: Risk Matrix
| Source | Main risk | Level | Mitigation | Block run on failure? |
|---|---|---|---|---|
| Semantic Scholar | 429s without key / shared pool | Medium | Enable only with key; retries; sequential | No |
| PubMed | IP block for unregistered heavy use; health-not-climate noise | Medium | Register tool+email; strict climate MeSH filter; off-peak large jobs | No |
| Europe PMC | Low | Low | Standard retries | No |
| arXiv | 429 under concurrency; preprint mistaken for final | Medium | 1-per-3s delay; preprint bucket lock | No |
| DataCite | Polluting paper pool with datasets | Medium | Type allowlist; DATA bucket only | No |
| EurekAlert | **Terms: no wholesale aggregation / no full-text reuse** | Medium-High | Headlines+links only; attribution; resolve to DOI; manual review | No |
| NSIDC | **Funding/continuity (Sea Ice Today reduced 2025-10)**; sensor transition | Medium | Treat as best-effort; surface caveat; lean on DataCite for DOIs | No |
| NOAA/NCEI | **Climate.gov archived; products retired (political)** | Medium-High | Repoint to NCEI; record provenance/retirement caveats; don't rely as sole authority | No |
| AGU/Wiley | TDM full text is licensed (don't fetch) | Low | Metadata-only via ISSN backfill | No |
| EGU/Copernicus | GMD methods-only noise | Low | Relevance guard on GMD | No |
| Springer Nature | **Non-commercial clause**; pricing opaque | High (legal) | Legal review; or use ISSN backfill instead | No |
| PLOS | Broad PLOS ONE flooding TOP | Medium | Climate filter; journal_key restriction | No |
| CORE | Quota/paid speed; repository duplicates | Medium | Enrichment-only; dedup by DOI; admin mode | No |
| DOAJ | 1000-record cap | Low | Use CSV whitelist, not bulk search | No |
| Unpaywall | Daily soft limit at scale | Low | Cache by DOI; batch final set only | No |

**Cross-cutting governance:**
- **US-federal climate data instability (2025):** Climate.gov archived, Billion-Dollar Disasters retired, NSIDC Sea Ice Today funding reduced. Document provenance and retirement caveats; don't treat any single federal feed as guaranteed-persistent; mirror critical NCEI report URLs.
- **Non-commercial / TDM licensing:** Springer Nature free APIs and Wiley TDM are non-commercial / licensed. Confirm BEF's use posture with General Counsel (Erin Jones) before enabling the SN API or any full-text fetch.
- **Copyright hygiene:** store metadata/abstracts and links; do **not** store/redistribute full-text or full press releases. EurekAlert requires attribution and forbids wholesale reuse.
- **No run should ever crash on a source:** keep the synthetic `source_error` contract; enrichment fails soft.

---

## 13. Recommended Implementation Sequence

**Wave 1 — P0, free, ~1 week, mostly config + 3 small clients**
1. **Harden Semantic Scholar** by adding the free key when available.
2. **AGU/Wiley** + **EGU/Copernicus** journals — config-only ISSN entries (highest value, zero code).
3. **Europe PMC** client (biomedical + preprints + OA flags in one call).
4. **arXiv** client (preprint bucket, throttled, full mode).
5. **Unpaywall** enrichment in `access.py`.
6. **Repoint NOAA feed** to NCEI climate reports; add **NSIDC** news RSS.

**Wave 2 — P1**
7. **PubMed/E-utilities** (with climate MeSH filter; register tool+email).
8. **DataCite** (datasets/reports, type allowlist, DATA bucket).
9. **PLOS** (PLOS Climate/Water + filtered PLOS ONE).
10. **DOAJ** as a journal-quality whitelist (CSV) — or free via Unpaywall's `journal_is_in_doaj`.

**Wave 3 — P2/P3 (reviewed/optional)**
11. **CORE** enrichment (only if Unpaywall leaves OA-PDF gaps).
12. **Springer Nature API** — only after legal clears the non-commercial clause; otherwise covered by ISSN backfill.
13. **EurekAlert** press leads — only with the DOI-resolution step and manual-review gating.

GMD methods filter and the shared climate-relevance guard ship alongside Waves 1–2.

---

## 14. Questions You Need to Answer Internally

1. **Non-commercial posture:** Does BEF's Hot Science deployment qualify as "non-commercial" for Springer Nature's free APIs and for any Wiley/Elsevier TDM? (→ Erin Jones / General Counsel.) This gates §4.11 and any full-text fetching.
2. **Citation-count signal:** Do we want Semantic Scholar/Europe PMC `citationCount` feeding the `impact_magnitude` rubric dimension, knowing recent papers have near-zero counts?
3. **Federal-data persistence:** Are we comfortable depending on NCEI/NSIDC feeds given 2025 defunding/archival? Do we mirror critical report URLs?
4. **NCBI registration owner:** Whose email/tool name registers with NCBI for the production IP? (Affects block-lift contact.)
5. **Unpaywall scope:** Run OA verification over the **final** candidate set only (cheap) or the **raw** set (heavier)? Recommend final set.
6. **EurekAlert appetite:** Do we want press leads at all, given they're never evidence and add manual-review load?
7. **Springer vs. ISSN backfill:** Is there evidence SN's abstracts/coverage beat OpenAlex+Crossref for the target journals? If not, skip the SN API entirely.
8. **GMD/Scientific Reports relevance threshold:** What similarity/relevance cutoff routes methods-only / broad-OA hits to manual review vs. TOP?
9. **Caching layer:** Where do DOI→Unpaywall and PMID→record caches live in production (Dynamo/Redis)?
10. **DOAJ source vs. signal:** Use DOAJ only as a quality flag, or also as a discovery source?

---

## 15. Appendix A — Official Documentation Links

**Broad scholarly / metadata**
- Semantic Scholar API tutorial & key form: https://www.semanticscholar.org/product/api/tutorial · https://www.semanticscholar.org/product/api#api-key-form
- NCBI E-utilities key & usage policy: https://support.nlm.nih.gov/kbArticle/?pn=KA-05317 · https://support.nlm.nih.gov/kbArticle/?pn=KA-05510 · https://eutilities.github.io/site/API_Key/usageandkey/
- Europe PMC REST: https://europepmc.org/RestfulWebService
- arXiv API + ToU: https://info.arxiv.org/help/api/ · https://info.arxiv.org/help/api/tou.html
- DataCite REST API: https://support.datacite.org/docs/api · date filtering https://support.datacite.org/docs/how-can-i-query-the-rest-api-to-retrieve-results-for-a-specific-date-range · queries https://support.datacite.org/docs/api-queries

**Press / institutional**
- EurekAlert terms / RSS: https://www.eurekalert.org/termsAndConditions · https://archive.eurekalert.org/rss.php · https://archive.eurekalert.org/terms.php
- NSIDC news (RSS link) / Sea Ice Today: https://nsidc.org/news-analyses/news-stories · https://nsidc.org/sea-ice-today
- NOAA NCEI Access / CDO API + token: https://www.ncei.noaa.gov/access · https://www.ncdc.noaa.gov/cdo-web/webservices/v2 · token: https://www.ncdc.noaa.gov/cdo-web/token
- Climate.gov archival notice: https://www.climate.gov/faqs · redirect: https://www.noaa.gov/climate
- NOAA Billion-Dollar Disasters retirement: https://www.nesdis.noaa.gov/about/documents-reports/notice-of-changes/2025-notice-of-changes/billion-dollar-weather-and-climate-disasters

**Journals / publishers**
- AGU/Wiley journals (per-journal RSS + ISSNs): https://agupubs.onlinelibrary.wiley.com/ · Wiley TDM: https://onlinelibrary.wiley.com/library-info/resources/text-and-datamining
- EGU/Copernicus journals: https://publications.copernicus.org/open-access_journals/journals_by_subject.html · https://www.egu.eu/publications/open-access-journals/
- Springer Nature developer portal: https://dev.springernature.com/ · API details: https://support.springernature.com/en/support/solutions/articles/6000195668-springer-nature-link-api-details · Data Solutions (Premium): https://datasolutions.springernature.com/products/open-access/
- PLOS Search API: https://api.plos.org/solr/faq/ · fields: https://api.plos.org/solr/search-fields

**OA / repository / enrichment**
- CORE API: https://core.ac.uk/services/api · docs: https://api.core.ac.uk/docs/v3
- DOAJ API: https://doaj.org/api/v3/docs · Journal CSV: https://doaj.org/docs/journal-csv
- Unpaywall API: https://unpaywall.org/products/api · data format: https://unpaywall.org/data-format

**Appendix B — ISSN verification note.** ISSNs marked *(confirmed)* were taken directly from the journal's first-party page/encyclopedic record during this research. The remaining ISSNs are standard values that should be confirmed against each journal's Wiley/Copernicus landing page (which displays print/online ISSNs) or via an OpenAlex `https://api.openalex.org/sources?filter=issn:<issn>` lookup before merging into config.
