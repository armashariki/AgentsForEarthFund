# Hot Science Source Expansion Blueprint

## Overview

- Goal: bring substantially more Hot Science sources online while preserving the pipeline's precision, date discipline, source-error isolation, and output clarity.
- Primary input: `docs/reference/hot_science_source_expansion_access_and_implementation_plan_2026_05_30.md`.
- Current architecture supports three fast lanes:
  - Config-only source expansion through `config/hot_science_sources.yaml`.
  - New source-client dispatch branches in `agents/hot_science/clients.py`.
  - Access/enrichment expansion through `agents/hot_science/access.py`.
- The highest-value immediate work is not one giant integration; it is a set of independent source agents with disjoint ownership.
- All source additions must preserve the existing `source_error` behavior: source failures are reported, not allowed to crash a run.
- Source lists, URLs, notes, ISSNs, enabled flags, seed terms, and thresholds stay in config.
- Secrets stay in `.env` locally, Fly secrets for the pilot, and AWS Secrets Manager later.

## Source Readiness Summary

- Can implement now without paid credentials:
  - Europe PMC.
  - arXiv.
  - DataCite.
  - PLOS.
  - PubMed/NCBI, with optional key recommended.
  - AGU/Wiley journal sources. Initial RSS URLs have been verified and config entries are enabled.
  - EGU/Copernicus journal sources. Initial RSS URLs have been verified and config entries are enabled.
  - NSIDC feeds. Initial RSS URLs have been verified and config entries are enabled.
  - NOAA/NCEI replacement feed. Initial RSS URL has been verified and `noaa_climate` points at NCEI news.
  - Unpaywall enrichment, because code already exists behind env flags.
  - DOAJ quality signal, preferably through Unpaywall first and CSV whitelist later.
- Can configure now but should remain disabled/manual-review gated:
  - EurekAlert, because terms require headline/link/date handling and press items must resolve to primary papers.
- Needs credentials before production hardening:
  - Semantic Scholar is enabled unauthenticated for pilot breadth, but should use `SEMANTIC_SCHOLAR_API_KEY` when available to reduce rate-limit failures.
  - PubMed/NCBI key optional but recommended via `NCBI_API_KEY`.
  - CORE, via `CORE_API_KEY`, if Unpaywall gaps justify it.
  - NOAA CDO API, via `NOAA_CDO_TOKEN`, only if the CDO client is added.
- Needs legal/governance review before enablement:
  - Springer Nature Metadata API, due to non-commercial terms.
  - Any PDF downloading or full-text storage.
  - CORE paid/enterprise tier, if needed.

## Expected Behavior

- The UI default of blank source IDs continues to mean "run every enabled source."
- Full Hot Science runs search a much wider source set than the original pilot.
- Peer-reviewed journal sources can become top candidates only after date, source-type, dedupe, abstract/metadata, and fit gates pass.
- Press sources remain leads unless a DOI or primary source is resolved.
- Preprints remain in a separate preprint bucket unless later resolved to a verified journal article.
- Institutional data releases remain eligible but are clearly labeled as institutional/data-release records, not papers.
- DataCite records are limited to datasets, reports, and official release-like records; journal articles from DataCite are excluded or deduped against canonical paper sources.
- Unpaywall enriches verified candidates with open-access and PDF-link metadata but does not download PDFs by default.
- Source diagnostics in the output make clear which sources were configured, enabled, completed, failed, and contributed records.

## Deployable Agent Workstreams

### Agent A: Config-First Source Expansion

- Ownership:
  - `config/hot_science_sources.yaml`.
  - Config assertions in `tests/test_hot_science_pipeline.py`.
- Sources:
  - AGU/Wiley journals.
  - EGU/Copernicus journals.
  - NSIDC.
  - NOAA/NCEI replacement.
  - EurekAlert disabled/manual-review source entries.
  - Semantic Scholar enablement gate.
- Immediate tasks:
  - Verify exact current RSS URLs and ISSNs before enabling.
  - Maintain AGU/Wiley entries as `kind: rss`, `source_type: peer_reviewed_journal`, with ISSNs.
  - Maintain EGU/Copernicus entries as `kind: rss`, `source_type: peer_reviewed_journal`, with ISSNs.
  - Maintain `nsidc_news` and `nsidc_sea_ice_today` as `kind: institutional_feed`, `source_type: institutional_data_release`.
  - Keep `noaa_climate` pointed at the NCEI feed unless a better climate-specific API/feed is confirmed.
  - Add EurekAlert source entries as disabled or enabled only if press-lead gating is explicitly accepted.
  - Keep `semantic_scholar` enabled for pilot breadth, but document unauthenticated rate-limit risk and add `SEMANTIC_SCHOLAR_API_KEY` when available.
- Why this is high leverage:
  - The current code already has ISSN/month backfill through OpenAlex and Crossref.
  - AGU/Wiley and EGU/Copernicus add many high-value climate journals with almost no client code.

### Agent B: Open Discovery Client Expansion

- Ownership:
  - `agents/hot_science/clients.py`.
  - Client fixtures/tests in `tests/test_hot_science_pipeline.py`.
- Sources:
  - Europe PMC.
  - arXiv.
  - DataCite.
- Immediate tasks:
  - Add `scan_europe_pmc` and parser.
  - Add `scan_arxiv` and Atom parser.
  - Add `scan_datacite` and JSON:API parser.
  - Add explicit `source.id` dispatch branches.
  - Add source entries in config.
  - Add fixture-based tests with no live network.
- Routing:
  - Europe PMC `SRC:MED` maps to peer-reviewed candidate records.
  - Europe PMC `SRC:PPR` maps to preprints.
  - arXiv always maps to preprints.
  - DataCite maps to institutional data releases only after type allowlisting.

### Agent C: Health and Biomedical Client Expansion

- Ownership:
  - `agents/hot_science/clients.py`.
  - PubMed/PLOS fixtures/tests.
  - Shared climate-health relevance guard if needed.
- Sources:
  - PubMed/NCBI.
  - PLOS.
- Immediate tasks:
  - Add `scan_pubmed` using ESearch then EFetch XML.
  - Add `scan_plos` using the PLOS Solr API.
  - Add source entries in config.
  - Add tests for date filters, DOI parsing, abstracts, authors, and climate filtering.
- Routing:
  - PubMed records become candidates only when climate-health signal is explicit.
  - Generic health-only records are excluded or manual-review.
  - PLOS Climate/Water can be more permissive.
  - PLOS ONE must pass a stricter climate-domain filter.

### Agent D: Access, Enrichment, and Quality Signals

- Ownership:
  - `agents/hot_science/access.py`.
  - Optional `agents/hot_science/doaj_whitelist.py`.
  - Tests for access/enrichment behavior.
- Sources:
  - Unpaywall.
  - DOAJ.
  - CORE later if justified.
- Immediate tasks:
  - Turn on existing Unpaywall flow in pilot with `HOT_SCIENCE_ENABLE_UNPAYWALL=1`.
  - Set `UNPAYWALL_EMAIL` or `DEEPGREEN_CONTACT_EMAIL`.
  - Add tests for OA DOI, closed DOI, disabled/missing email, and failed API.
  - Capture richer audit signals from Unpaywall: `oa_status`, `license`, `host_type`, `journal_is_in_doaj`, `has_repository_copy`.
  - Use DOAJ first as a quality signal through Unpaywall's `journal_is_in_doaj`.
  - Add a cached DOAJ CSV whitelist later if needed.
- Deferred tasks:
  - CORE enrichment after Unpaywall gaps are measured.
  - PDF downloading remains disabled.

### Agent E: Source Health, Reporting, and Deployment QA

- Ownership:
  - `agents/hot_science/compiler.py`.
  - `web/backend/artifacts.py`.
  - `web/frontend/src/App.tsx`.
  - `docs/hot_science_fly_ui.md`.
  - Deployment smoke scripts or documented runbook.
- Immediate tasks:
  - Improve admin source-health visibility from existing progress events and source diagnostics.
  - Add report section for access/enrichment status.
  - Keep normal user output clean: primary downloadable DOCX only.
  - Keep admin/debug history hidden but complete.
  - Add Fly secret/runbook updates for new optional keys.
  - Run constrained and full all-enabled-source smoke checks after each wave.

## Implementation Plan

### Config Changes

- Add source entries for AGU/Wiley journals:
  - `agu_geophysical_research_letters`.
  - `agu_jgr_atmospheres`.
  - `agu_jgr_oceans`.
  - `agu_jgr_earth_surface`.
  - `agu_earths_future`.
  - `agu_geohealth`.
  - `agu_global_biogeochemical_cycles`.
  - `agu_water_resources_research`.
  - `agu_reviews_of_geophysics`.
- Add source entries for EGU/Copernicus journals:
  - `egu_earth_system_dynamics`.
  - `egu_earth_system_science_data`.
  - `egu_climate_of_the_past`.
  - `egu_the_cryosphere`.
  - `egu_atmospheric_chemistry_and_physics`.
  - `egu_biogeosciences`.
  - `egu_hydrology_and_earth_system_sciences`.
  - `egu_natural_hazards_and_earth_system_sciences`.
  - `egu_ocean_science`.
  - `egu_geoscientific_model_development`.
- Add source entries for open APIs:
  - `europe_pmc`.
  - `arxiv`.
  - `datacite`.
  - `plos`.
  - `pubmed`.
- Add or repoint institutional and lead feeds:
  - `nsidc_news`.
  - `noaa_climate` or `ncei_climate_reports`.
  - `eurekalert_earth_science`, likely disabled first.
  - `eurekalert_environment`, likely disabled first.
- Add notes for source limitations:
  - EurekAlert stores headline/link/date only.
  - arXiv is preprint-only.
  - DataCite excludes journal articles.
  - GMD methods-only papers require stricter fit review.
  - Springer Nature remains disabled pending legal review.
  - CORE remains disabled pending API key and quota review.

### Client Code Changes

- Add dispatch branches in `scan_source` for:
  - `europe_pmc`.
  - `arxiv`.
  - `datacite`.
  - `plos`.
  - `pubmed`.
  - Optional later: `springer_nature`, `core`, `ncei_cdo`, `doaj`.
- Add parser functions:
  - `_records_from_europe_pmc_payload`.
  - `_records_from_arxiv_atom`.
  - `_records_from_datacite_payload`.
  - `_records_from_plos_payload`.
  - `_records_from_pubmed_efetch_xml`.
- Add query helpers:
  - Europe PMC Lucene query with `FIRST_PDATE` range.
  - arXiv category/date query with polite throttling.
  - DataCite type allowlist and month post-filter.
  - PLOS Solr query with `doc_type:full` and publication date range.
  - PubMed ESearch/EFetch with `tool`, `email`, and optional `NCBI_API_KEY`.
- Keep canonical date fields compatible with the verifier:
  - Use `publicationDate`, `published`, `published-online`, or `date-published`.
  - Avoid non-canonical fields that route everything to manual review.

### Verification And Routing Changes

- Preserve existing source-type gates:
  - `peer_reviewed_journal`.
  - `institutional_data_release`.
  - `attribution_report`.
  - `preprint`.
  - `popular_press`.
- Add or strengthen source-specific guards:
  - PLOS ONE needs a direct climate-domain signal.
  - PubMed needs a climate-health signal.
  - DataCite excludes `journal-article` and research artifacts that are not official data/report releases.
  - arXiv remains preprint-only.
  - Europe PMC PPR remains preprint-only.
  - EurekAlert remains manual-review until DOI or primary source resolution.
  - GMD methods-only papers route to manual review or exclusion unless there is a substantive climate finding.

### Access And Enrichment Changes

- Use the existing Unpaywall gate:
  - `HOT_SCIENCE_ENABLE_UNPAYWALL=1`.
  - `UNPAYWALL_EMAIL` or `DEEPGREEN_CONTACT_EMAIL`.
- Keep `HOT_SCIENCE_DOWNLOAD_PDFS` off.
- Add richer audit data without forcing schema churn:
  - OA status.
  - License.
  - Host type.
  - DOAJ journal flag.
  - Repository copy flag.
- Treat DOAJ as a quality signal first.
- Treat CORE as optional later enrichment only.

### Deployment Changes

- Update `.env.example` with optional new source variables:
  - `SEMANTIC_SCHOLAR_API_KEY`.
  - `NCBI_API_KEY`.
  - `UNPAYWALL_EMAIL`.
  - `HOT_SCIENCE_ENABLE_UNPAYWALL`.
  - `NOAA_CDO_TOKEN`.
  - `CORE_API_KEY`.
  - `SPRINGER_NATURE_API_KEY`.
- Update Fly docs with source-expansion setup.
- Set pilot Fly secrets for sources that are approved:
  - `DEEPGREEN_CONTACT_EMAIL`.
  - `UNPAYWALL_EMAIL`.
  - `HOT_SCIENCE_ENABLE_UNPAYWALL=1`.
  - `SEMANTIC_SCHOLAR_API_KEY` when obtained.
  - `NCBI_API_KEY` when obtained.
- Do not set Springer or CORE until legal/quota decisions are complete.

## Implementation Phases

### Phase 1: Source URL And Credential Readiness Audit

- Verify exact RSS URLs for AGU/Wiley journals.
- Verify exact RSS URLs for EGU/Copernicus journals.
- Verify NSIDC news RSS URL.
- Verify NCEI climate-report/news feed or API endpoint.
- Verify EurekAlert feed URLs and terms constraints.
- Confirm whether `SEMANTIC_SCHOLAR_API_KEY` is available.
- Confirm contact email for OpenAlex/Crossref/PubMed/Unpaywall.
- Output:
  - A source readiness table.
  - A list of sources safe to enable immediately.
  - A list of secrets/manual actions still required.

### Phase 2: Config-Only High-Value Journal Expansion

- Add AGU/Wiley source entries.
- Add EGU/Copernicus source entries.
- Add NSIDC source entry.
- Repoint or supplement NOAA/NCEI source.
- Add disabled or guarded EurekAlert entries.
- Update config-load tests.
- Run:
  - `python -m pytest tests/test_hot_science_pipeline.py -q`.
  - Constrained all-enabled-source scan with low `max_results_per_source`.
- Output:
  - Source count increase.
  - Source diagnostic report.
  - No source crashes.

### Phase 3: Enable Existing And Low-Friction Enrichment

- Enable Unpaywall in local/Fly config.
- Add Unpaywall fixture tests.
- Add richer audit fields.
- Enable Semantic Scholar only if key is available.
- Add Semantic Scholar smoke test or source-health check.
- Keep PDF download disabled.
- Output:
  - Candidate OA status and PDF-link enrichment.
  - No full-text storage.

### Phase 4: Open Discovery Clients

- Implement Europe PMC.
- Implement arXiv.
- Implement DataCite.
- Add config entries and fixture tests.
- Validate routing:
  - Europe PMC peer-reviewed vs preprint.
  - arXiv preprint-only.
  - DataCite institutional-data-release only.
- Output:
  - Expanded biomedical/preprint/data-release recall.
  - Clear buckets in DOCX/Markdown outputs.

### Phase 5: Health And OA Journal Clients

- Implement PLOS.
- Implement PubMed/NCBI.
- Add climate-health and PLOS ONE relevance guards.
- Register NCBI tool/email and optionally set `NCBI_API_KEY`.
- Add fixtures and tests.
- Output:
  - Stronger climate-health coverage.
  - Controlled PLOS coverage without broad noise.

### Phase 6: Source Health UI And Report Polish

- Add admin source-health panel or summary.
- Add report section for access/enrichment status.
- Add source-health metadata to admin run history if needed.
- Keep normal-user UI focused on run/download.
- Output:
  - Easier QA for source performance.
  - Clear per-source failures and contribution counts.

### Phase 7: Optional And Reviewed Sources

- CORE:
  - Add only after Unpaywall gaps are measured and `CORE_API_KEY` is obtained.
  - Use as enrichment, not primary discovery.
- Springer Nature:
  - Add only after legal clears non-commercial terms or a paid license exists.
  - Prefer ISSN backfill for Springer journals if legal is unclear.
- EurekAlert:
  - Enable only after press-resolution/manual-review behavior is explicit.
  - Store headline/link/date only.
- Output:
  - No unapproved legal/licensing exposure.

### Phase 8: Full Regression And Deployment

- Run full tests:
  - `npm run build --prefix web/frontend`.
  - `python -m pytest tests/ -q`.
- Run constrained source-health scan.
- Run full April 2026 scan.
- Render/QA DOCX output.
- Deploy to Fly.
- Validate:
  - `/health`.
  - source progress events.
  - source diagnostics CSV.
  - primary DOCX download.
  - admin/debug artifacts.
- Output:
  - Shareable source-expansion run report.
  - Deployment notes and source coverage summary.

## Testing Strategy

- Unit tests:
  - Config loads all new source IDs.
  - ISSN-backed sources generate OpenAlex/Crossref filters.
  - Each new client parses fixture payloads.
  - Each new client filters outside-month records.
  - Each new client maps canonical date fields correctly.
  - Each new client preserves `source_error` behavior.
- Routing tests:
  - arXiv routes to preprint.
  - Europe PMC PPR routes to preprint.
  - DataCite dataset/report routes to institutional data release.
  - DataCite journal article is excluded or ignored.
  - PLOS ONE weak climate match does not become a top candidate.
  - PubMed health-only paper without climate signal is excluded or manual-review.
  - EurekAlert unresolved press remains manual-review.
- Access tests:
  - Unpaywall OA result maps to open access and PDF link.
  - Unpaywall closed result maps to paywalled.
  - Missing email does not call Unpaywall.
  - Unpaywall failure adds audit but does not fail the run.
- Integration tests:
  - Constrained all-enabled-source scan.
  - Full-source scan for April 2026.
  - Output includes source inventory and source diagnostics.
  - UI blank source field still means all enabled sources.
- Deployment checks:
  - Fly health endpoint.
  - Fly secrets present.
  - Fly volume persistence.
  - DOCX render QA.

## Agent Execution Strategy

- Start Agent A first because config-only expansion unlocks the most sources fastest.
- Run Agent B and Agent C in parallel because their write scopes can be split by client functions and fixtures.
- Run Agent D in parallel with B/C because `access.py` is a separate path.
- Hold Agent E until source diagnostics and new client outputs exist, then polish report/UI behavior.
- Keep each agent's write scope disjoint:
  - Agent A: config and config tests.
  - Agent B: Europe PMC, arXiv, DataCite clients and tests.
  - Agent C: PubMed, PLOS clients and tests.
  - Agent D: access/enrichment tests and docs.
  - Agent E: UI/report/deployment QA.

## Sources We Can Bring Online Fastest

- Fastest with no new code after URL verification:
  - AGU/Wiley journals.
  - EGU/Copernicus journals.
  - NSIDC feed.
  - NOAA/NCEI feed replacement.
- Fastest with existing code and secrets:
  - Unpaywall.
  - Semantic Scholar.
- Fastest with new but straightforward clients:
  - Europe PMC.
  - arXiv.
  - DataCite.
  - PLOS.
  - PubMed.
- Slower or gated:
  - EurekAlert, due to press-lead terms and manual-review handling.
  - CORE, due to API key/quota decision.
  - Springer Nature, due to non-commercial/legal review.

## Open Questions

- What contact email should be used for OpenAlex, Crossref, PubMed tool registration, Europe PMC courtesy, and Unpaywall?
- Do we have or can we request `SEMANTIC_SCHOLAR_API_KEY` now?
- Should we enable PubMed before `NCBI_API_KEY`, or wait for the key to avoid tighter rate limits?
- Should DataCite include software records, or only datasets and reports?
- Which NOAA/NCEI surface is the preferred canonical source for Hot Science: RSS/news, climate monitoring pages, Access Data Service, or CDO API?
- Should EurekAlert be enabled as disabled-by-default config now, or omitted until DOI resolution is improved?
- Should source expansion happen first locally only, then Fly, or go to Fly after each wave?
- Should Springer journals be covered only through ISSN backfill for now, avoiding the Springer Nature API legal issue?
- What threshold should route GMD and broad PLOS ONE methods-style records to manual review instead of top candidates?
