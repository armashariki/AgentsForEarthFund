# Hot Science Source Expansion Phase 1 Readiness Audit

Date: 2026-05-30

## Status

Phase 1 is complete.

This audit reviewed the source-expansion implementation plan, checked current local credential/config readiness, and live-tested candidate feed URLs where possible.

## Credential Readiness

Current local `.env` status:

- No active source-expansion values were found for:
  - `SEMANTIC_SCHOLAR_API_KEY`
  - `NCBI_API_KEY`
  - `NOAA_CDO_TOKEN`
  - `CORE_API_KEY`
  - `SPRINGER_NATURE_API_KEY`

Added after initial audit:

- `UNPAYWALL_EMAIL=<team-contact-email>`
- `DEEPGREEN_CONTACT_EMAIL=<team-contact-email>`
- `HOT_SCIENCE_ENABLE_UNPAYWALL=1`
- `HOT_SCIENCE_DOWNLOAD_PDFS=0`

`.env.example` already documents:

- `DEEPGREEN_CONTACT_EMAIL`
- `OPENALEX_MAILTO`
- `CROSSREF_MAILTO`
- `UNPAYWALL_EMAIL`
- `SEMANTIC_SCHOLAR_API_KEY`
- `NCBI_API_KEY`
- `CORE_API_KEY`
- `SPRINGER_NATURE_API_KEY`
- `HOT_SCIENCE_ENABLE_UNPAYWALL`
- `HOT_SCIENCE_DOWNLOAD_PDFS`

Interpretation:

- Phase 2 can proceed for no-key sources.
- Semantic Scholar is now enabled without `SEMANTIC_SCHOLAR_API_KEY` for pilot coverage, with the expectation that unauthenticated calls may be rate-limited and reported as nonfatal source errors.
- Unpaywall can be turned on once `UNPAYWALL_EMAIL` or `DEEPGREEN_CONTACT_EMAIL` is set.
- PubMed can be implemented without `NCBI_API_KEY`, but production should use a key.
- CORE and Springer Nature remain later-stage sources.

## Confirmed Feed URLs

### AGU / Wiley

All candidate AGU/Wiley RSS URLs below returned HTTP 200 and valid RSS/XML.

| Source ID | Feed URL | Status |
|---|---|---|
| `agu_geophysical_research_letters` | `https://agupubs.onlinelibrary.wiley.com/action/showFeed?jc=19448007&type=etoc&feed=rss` | Ready |
| `agu_jgr_atmospheres` | `https://agupubs.onlinelibrary.wiley.com/action/showFeed?jc=21698996&type=etoc&feed=rss` | Ready |
| `agu_jgr_oceans` | `https://agupubs.onlinelibrary.wiley.com/action/showFeed?jc=21699291&type=etoc&feed=rss` | Ready |
| `agu_jgr_earth_surface` | `https://agupubs.onlinelibrary.wiley.com/action/showFeed?jc=21699011&type=etoc&feed=rss` | Ready |
| `agu_earths_future` | `https://agupubs.onlinelibrary.wiley.com/action/showFeed?jc=23284277&type=etoc&feed=rss` | Ready |
| `agu_geohealth` | `https://agupubs.onlinelibrary.wiley.com/action/showFeed?jc=24711403&type=etoc&feed=rss` | Ready |
| `agu_global_biogeochemical_cycles` | `https://agupubs.onlinelibrary.wiley.com/action/showFeed?jc=19449224&type=etoc&feed=rss` | Ready |
| `agu_water_resources_research` | `https://agupubs.onlinelibrary.wiley.com/action/showFeed?jc=19447973&type=etoc&feed=rss` | Ready |
| `agu_reviews_of_geophysics` | `https://agupubs.onlinelibrary.wiley.com/action/showFeed?jc=19449208&type=etoc&feed=rss` | Ready |

Implementation readiness:

- These can be added in Phase 2 as config-only sources.
- Use `kind: rss`.
- Use `source_type: peer_reviewed_journal`.
- Include ISSNs so existing OpenAlex/Crossref ISSN backfill works.

### EGU / Copernicus Publications

All candidate EGU/Copernicus RSS URLs below returned HTTP 200 and valid RSS/XML.

| Source ID | Feed URL | Status |
|---|---|---|
| `egu_earth_system_dynamics` | `https://esd.copernicus.org/xml/rss2_0.xml` | Ready |
| `egu_earth_system_science_data` | `https://essd.copernicus.org/xml/rss2_0.xml` | Ready |
| `egu_climate_of_the_past` | `https://cp.copernicus.org/xml/rss2_0.xml` | Ready |
| `egu_the_cryosphere` | `https://tc.copernicus.org/xml/rss2_0.xml` | Ready |
| `egu_atmospheric_chemistry_and_physics` | `https://acp.copernicus.org/xml/rss2_0.xml` | Ready |
| `egu_biogeosciences` | `https://bg.copernicus.org/xml/rss2_0.xml` | Ready |
| `egu_hydrology_and_earth_system_sciences` | `https://hess.copernicus.org/xml/rss2_0.xml` | Ready |
| `egu_natural_hazards_and_earth_system_sciences` | `https://nhess.copernicus.org/xml/rss2_0.xml` | Ready |
| `egu_ocean_science` | `https://os.copernicus.org/xml/rss2_0.xml` | Ready |
| `egu_geoscientific_model_development` | `https://gmd.copernicus.org/xml/rss2_0.xml` | Ready |

Implementation readiness:

- These can be added in Phase 2 as config-only sources.
- Use `kind: rss`.
- Use `source_type: peer_reviewed_journal`.
- Include ISSNs so existing OpenAlex/Crossref ISSN backfill works.
- Add a note that GMD is methods-heavy and should be handled by strict methods-paper gating.

### NSIDC

Confirmed working feeds:

| Source ID | Feed URL | Status |
|---|---|---|
| `nsidc_news` | `https://nsidc.org/news/feed` | Ready |
| `nsidc_sea_ice_today` | `https://nsidc.org/arcticseaicenews/feed` | Optional ready |

Rejected candidate URLs:

- `https://nsidc.org/news-analyses/news-stories/rss.xml` returned 404.
- `https://nsidc.org/news-analyses/news-stories/feed` returned 404.
- `https://nsidc.org/ice-sheets-today/feed` returned 404.
- `https://nsidc.org/snow-today/feed` returned 404.

Implementation readiness:

- Add `nsidc_news` in Phase 2.
- `nsidc_sea_ice_today` is optional and should probably be treated as analysis/monitoring context rather than a top-candidate source.

### NOAA / NCEI

Confirmed working feeds/pages:

| Candidate | URL | Status |
|---|---|---|
| Former broad NOAA RSS | `https://www.noaa.gov/rss.xml` | Works, but too generic for this packaged project |
| NCEI news RSS | `https://www.ncei.noaa.gov/news.xml` | Ready |
| NCEI monthly global report page | `https://www.ncei.noaa.gov/access/monitoring/monthly-report/global/202604` | HTML page works, not RSS |

Rejected candidate URL:

- `https://www.ncei.noaa.gov/rss.xml` returned 404.

Implementation readiness:

- The packaged project replaces the generic `noaa_climate` RSS with `https://www.ncei.noaa.gov/news.xml`.
- The monthly report pages may be useful later, but the current RSS client cannot parse ordinary HTML pages as feeds.

## Not Ready Yet

### EurekAlert

Observed status:

- `https://www.eurekalert.org/rss.php` returned an HTTP 200 page, but it was a "Page not found" HTML response, not RSS.
- `https://archive.eurekalert.org/rss.php` failed with connection refused.
- The climate topic page did not expose obvious RSS links in the HTML inspected during this audit.

Recommendation:

- Do not enable EurekAlert in Phase 2.
- Add disabled config entries only if useful for documentation.
- Treat EurekAlert as blocked until a current official feed URL or acceptable access path is confirmed.
- Even after access is confirmed, EurekAlert must remain press-lead/manual-review only.

### Semantic Scholar

Status:

- Client code already exists.
- Config entry already exists.
- No local API key was found.
- Config is now enabled for unauthenticated pilot use.

Recommendation:

- Keep enabled for now because the user accepted rate-limit risk.
- Add `SEMANTIC_SCHOLAR_API_KEY` when available to reduce rate-limit failures.
- Treat Semantic Scholar 429s as expected nonfatal source errors until the key is configured.

### Unpaywall

Status:

- `AccessAgent` already has Unpaywall support behind `HOT_SCIENCE_ENABLE_UNPAYWALL=1`.
- Local `UNPAYWALL_EMAIL` and `DEEPGREEN_CONTACT_EMAIL` should be configured with the team contact email.
- Local `HOT_SCIENCE_ENABLE_UNPAYWALL=1` is now configured.
- Local `HOT_SCIENCE_DOWNLOAD_PDFS=0` remains configured so the system links to lawful OA copies without storing PDFs.

Recommendation:

- Unpaywall is ready for Phase 3 locally.
- Set the same values as Fly secrets before expecting deployed runs to use Unpaywall.
- Keep `HOT_SCIENCE_DOWNLOAD_PDFS=0`.

### CORE

Status:

- Requires `CORE_API_KEY`.
- No key found.

Recommendation:

- Defer.
- Use only if Unpaywall does not provide enough OA/full-text coverage.

### Springer Nature

Status:

- Requires `SPRINGER_NATURE_API_KEY`.
- Legal review needed for non-commercial terms.
- No key found.

Recommendation:

- Defer.
- Prefer ISSN backfill for relevant Springer journals until legal clears API use.

## Packaged Source Additions

The packaged project includes enabled config entries for:

- AGU/Wiley journal sources.
- EGU/Copernicus journal sources.
- `nsidc_news` and `nsidc_sea_ice_today`.
- NOAA/NCEI RSS using `https://www.ncei.noaa.gov/news.xml`.

Phase 2 should not yet enable:

- EurekAlert.
- CORE.
- Springer Nature.
- PDF downloads.

## Remaining Implementation Notes

- Add deeper fixture-based tests for AGU/EGU ISSN backfill behavior.
- Add at least one AGU and one EGU ISSN-backfill test using the existing `scan_journal_by_issn` behavior.
- Run a constrained all-enabled-source scan after adding the config.
- Expect source count to increase substantially.
