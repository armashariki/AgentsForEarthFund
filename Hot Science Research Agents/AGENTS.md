# Hot Science Research Agents

## Project Scope

This project is the Hot Science / Research and Literature Monitoring pilot for finding climate-change and global-warming research papers, institutional reports, attribution reports, and official data releases for the Hot Science team.

The runnable pipeline lives in `agents/hot_science/`. The editable source inventory, source enablement, seed terms, domains, and scoring rubric live in `config/hot_science_sources.yaml`. The command-line runner is `scripts/run_hot_science.py`. The deployable pilot UI is in `web/`.

## Architecture Rules

1. Keep source lists, thresholds, source enablement, seed terms, and rubrics in `config/hot_science_sources.yaml`, not hardcoded in agent files.
2. Keep search criteria in Markdown/text files under `criteria/` or a documented external path, then pass them with `--criteria-file`.
3. Keep concise API search text separate from long criteria by using `--query` or `--query-file`.
4. Never commit `.env`, `.deepgreen/`, generated outputs, Fly secrets, passwords, API keys, local databases, `node_modules`, or virtual environments.
5. UI and CLI should use the same pipeline code path so results remain consistent.
6. Normal users should receive top candidates plus manual-review candidates in the downloadable output.
7. Source failures should be nonfatal and visible in run summaries/source-breakdown outputs.

## Important Files

- Pipeline: `agents/hot_science/`
- Source config: `config/hot_science_sources.yaml`
- Criteria: `criteria/`
- CLI runner: `scripts/run_hot_science.py`
- Regression/QA: `scripts/run_hot_science_regression.py`, `tests/test_hot_science_*`
- UI/backend: `web/backend/`
- UI/frontend: `web/frontend/`
- Fly deployment: `Dockerfile`, `fly.toml`, `docs/hot_science_fly_ui.md`
- Source expansion plan: `blueprint/hot-science-source-expansion/`
- Reference source-access docs: `docs/reference/`

## Current Source Posture

Maximize enabled no-cost/public sources first. Current enabled discovery sources include OpenAlex, Crossref, unauthenticated Semantic Scholar, Nature RSS feeds, Science/Science Advances, PNAS, AGU/Wiley journals, EGU/Copernicus journals, ScienceDaily, Copernicus C3S, NOAA/NCEI, NSIDC, World Weather Attribution, and EarthArXiv. Optional keys should be added through `.env`, Fly secrets, or the eventual production secret manager.
