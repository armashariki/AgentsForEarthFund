# Hot Science Research Agents

This is the DeepGreen Hot Science research-agent project for finding climate-change and global-warming papers and official scientific outputs for the Hot Science team.

It contains a shared agent pipeline, command-line runner, tests, criteria files, source-expansion plans, and a deployable FastAPI + React pilot UI for Fly.io.

## What It Does

- Searches scholarly APIs, journal RSS feeds, institutional feeds, preprint feeds, and press/discoverability feeds.
- Uses strict target-month logic based on the underlying paper/report publication date, not merely the press article date.
- Buckets outputs into top candidates, manual-review candidates, excluded candidates, preprints, watch-list items, source errors, and unresolved press items.
- Produces downloadable report artifacts for the Hot Science team.
- Uses one shared pipeline for CLI and UI runs so behavior stays consistent.

## Project Layout

- `agents/hot_science/`: multi-agent Hot Science pipeline.
- `config/hot_science_sources.yaml`: source inventory, source enablement, seed terms, domains, and scoring rubric.
- `criteria/`: reusable search criteria files.
- `scripts/run_hot_science.py`: main command-line runner.
- `scripts/run_hot_science_regression.py`: regression/QA runner.
- `web/backend/`: FastAPI service and artifact generation.
- `web/frontend/`: React/Vite user interface.
- `docs/`: deployment and operations notes.
- `docs/reference/`: source-access and QA reference docs.
- `blueprint/`: implementation plans produced with the Imbue Blueprint planning approach.

## Current Enabled Sources

The active source list is controlled by `config/hot_science_sources.yaml`.

Currently enabled discovery sources include:

- OpenAlex Works
- Crossref Works
- Semantic Scholar Academic Graph, unauthenticated for now
- Nature
- Nature Communications
- Nature Climate Change
- Nature Geoscience
- Science
- Science Advances
- PNAS
- AGU/Wiley geoscience journals
- EGU/Copernicus geoscience journals
- ScienceDaily Climate News
- ScienceDaily Environment News
- Copernicus Climate Change Service
- NOAA/NCEI news feed
- NSIDC news and Arctic sea-ice feeds
- World Weather Attribution
- EarthArXiv

Currently disabled or optional sources require better feeds, registration, paid/licensed access, or additional implementation. See `docs/reference/hot_science_source_expansion_access_and_implementation_plan_2026_05_30.md`.

## Local Setup

From the root of `AgentsForEarthFund`:

```bash
cd "Hot Science Research Agents"
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Edit `.env` and set at least the contact email fields. Do not commit `.env`.

For better coverage, set:

```bash
OPENALEX_MAILTO=<your-team-contact-email>
CROSSREF_MAILTO=<your-team-contact-email>
UNPAYWALL_EMAIL=<your-team-contact-email>
DEEPGREEN_CONTACT_EMAIL=<your-team-contact-email>
HOT_SCIENCE_ENABLE_UNPAYWALL=1
```

Semantic Scholar runs without a key but may rate limit. Add `SEMANTIC_SCHOLAR_API_KEY` when available.

## Run the CLI Agent

```bash
cd "Hot Science Research Agents"
source .venv/bin/activate
mkdir -p outputs/hot_science
python scripts/run_hot_science.py \
  --target-month 2026-04 \
  --criteria-file criteria/april_2026_climate_change_global_warming.md \
  --query "climate change global warming climate impacts extreme heat drought extreme weather wildfire flooding sea level rise oceans cryosphere ecosystems health pollutants agriculture economics adaptation mitigation" \
  --max-results-per-source 25 \
  --json-out outputs/hot_science/april_2026_climate_change_global_warming.json \
  --markdown-out outputs/hot_science/april_2026_climate_change_global_warming.md \
  --review-csv-out outputs/hot_science/april_2026_climate_change_global_warming_review.csv \
  --source-breakdown-csv-out outputs/hot_science/april_2026_climate_change_global_warming_sources.csv
```

The long criteria file governs eligibility and report filtering. The short `--query` keeps external APIs from receiving a page-long prompt as a search string.

## Run Tests

```bash
cd "Hot Science Research Agents"
source .venv/bin/activate
python -m pytest tests/test_hot_science_pipeline.py tests/test_hot_science_progress.py tests/test_hot_science_calibration.py tests/test_hot_science_api.py tests/test_hot_science_web_phase1.py -q
```

## Run the UI Locally

```bash
cd "Hot Science Research Agents"
source .venv/bin/activate
npm ci --prefix web/frontend
npm run build --prefix web/frontend
uvicorn web.backend.main:app --reload --host 127.0.0.1 --port 8080
```

Then open `http://127.0.0.1:8080`.

## Deploy to Fly.io

See `docs/hot_science_fly_ui.md`.

At minimum, set pilot UI secrets and contact-email/API secrets with `fly secrets set`. Do not place credentials in `fly.toml`.

## Source Expansion

Use these references before adding new sources:

- `blueprint/hot-science-source-expansion/plan-hot-science-source-expansion.md`
- `docs/reference/hot_science_source_expansion_access_and_implementation_plan_2026_05_30.md`
- `docs/reference/hot_science_system_qa_source_coverage_2026_05_30.md`
- `docs/reference/source_expansion_phase1_readiness_2026_05_30.md`

Highest-priority next additions are PubMed/NCBI, AGU/Wiley ISSN-backed discovery, EGU/Copernicus journal feeds, and improved institutional feeds where stable no-cost endpoints exist.
