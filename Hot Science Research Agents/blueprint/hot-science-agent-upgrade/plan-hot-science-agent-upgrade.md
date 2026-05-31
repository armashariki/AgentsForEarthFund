# Hot Science Agent Upgrade Plan

## Overview

- Improve the UC-I-1 Hot Science pipeline by converting Science R&D reviewer feedback into reusable rules, tests, and output changes.
- Prioritize the failure modes shown in `updated docs`: topical adjacency, wrong primary work, wrong date, fuzzy novelty, weak source coverage, and unclear manual-review routing.
- Keep the current registry-based Phase 1 architecture intact; the work stays inside `agents/hot_science/`, `config/`, `scripts/`, and `tests/`.
- Keep prompts in `config/prompts.py`, model IDs in `config/models.py`, and source lists, thresholds, seed terms, domains, and rubric weights in config.
- Treat scores as decision support for human voting, not automatic final selection.

## Reviewer Feedback To General Rules

- Press items are discovery leads only; the candidate must be the resolved primary paper/report.
- Prefer peer-reviewed journal records over Zenodo, Figshare, OSF, GitHub, code releases, datasets, supplements, and journal-level records for the same logical work.
- Use the primary paper/report publication date for target-month eligibility; press dates, submission dates, received dates, deposit dates, and RSS item dates do not qualify.
- Route title-only plausible items to manual review after trying to recover an abstract; do not promote them as verified candidates.
- Require abstract-first evidence of fit before scoring: the abstract or primary metadata must support a one-sentence Hot Science relevance claim.
- Enforce the run-specific search focus as a hard relevance check alongside the standing Hot Science scope.
- Separate topical relevance from monthly eligibility; a strong wrong-month item can enter an optional watchlist but not the monthly candidate set.
- Exclude historical, paleoclimate, formation-history, tectonic, archaeology, social-science-only, methods-only, and pollutant-only items unless the abstract shows direct contemporary or future climate relevance.
- Treat ambiguous words such as emissions, particles, atmosphere, migration, collapse, heat, and ice as insufficient unless the abstract shows the climate mechanism.
- Make domain tags evidence-backed; tags such as cryosphere, sea level, drought, disease vectors, flooding, urban heat, and sea surface temperature require supporting abstract evidence.
- Remove audience relevance from selection scoring; reserve it for future summary-drafting workflows.
- Make cross-disciplinary relevance and cascading impact additive-only signals; absence should not exclude or heavily penalize an otherwise strong paper.
- Replace fuzzy novelty keywords with explicit novelty subtypes: new finding in an established area, first observation, or substantial advance over prior work.
- Make geographic scope and generalizability visible scoring signals so narrow regional papers can remain eligible while ranking lower for broad-impact roundups.

## Expected Behavior

- The review pack starts with a visible run configuration: target month, search focus, source set, standing criteria version, rubric version, and date eligibility rules.
- Top candidates appear before the manual-review queue.
- Manual-review items show a plain-language reason such as unresolved primary paper, title-only evidence, ambiguous date field, no abstract, or source type needs review.
- Preprints appear in a separate labeled section, not mixed with peer-reviewed candidates.
- Strong but wrong-month papers can appear in a separate non-target-month watchlist if enabled.
- Excluded records include specific reasons, not just generic low relevance.
- Candidate rows include the evidence-of-fit claim and the abstract or metadata snippet that supports it.
- Scoring output no longer includes audience relevance as a selection dimension.
- Source diagnostics show whether journal/API coverage, RSS feeds, press feeds, and institutional sources contributed verified, manual-review, excluded, or error records.

## Architecture And Files

- `config/hot_science_sources.yaml`
  - Add configurable domain terms for flooding, disease vectors, urban heat, sea surface temperature, and other Science R&D-approved domains.
  - Add rubric weights and scoring dimensions outside code.
  - Add optional watchlist behavior flags.
  - Replace journal RSS backfill reliance with source definitions that can support OpenAlex/Crossref ISSN and publication-month filters.

- `agents/hot_science/config.py`
  - Extend config dataclasses for domains, rubric dimensions/weights, watchlist settings, and source identifiers such as ISSNs.
  - Keep config backwards-compatible with existing YAML defaults.

- `agents/hot_science/schema.py`
  - Add structured fields for `fit_assessment`, `routing_reason`, `date_eligibility`, `watchlist_reason`, `rubric_version`, and `primary_work_type`.
  - Consider adding fields for evidence snippets and reviewer calibration labels.

- `agents/hot_science/resolver.py`
  - Resolve press leads to primary works using DOI hints, journal-reference text, fetched press pages when enabled, and scholarly API lookup.
  - Rank possible primary works by source-type priority: peer-reviewed journal article, attribution report, institutional data release, preprint, artifact.
  - Preserve artifacts as provenance attached to the canonical paper rather than as standalone candidates.

- `agents/hot_science/verification.py`
  - Validate article-level records before date eligibility.
  - Distinguish publication/online publication date from submission, received, updated, press, and repository deposit dates.
  - Emit structured routing reasons for manual review and structured exclusion reasons for ineligible items.

- `agents/hot_science/evaluator.py`
  - Add the abstract-first evidence-of-fit gate before scoring.
  - Replace broad keyword climate checks with claim-supported relevance assessment.
  - Remove audience relevance from composite selection scoring.
  - Implement weighted scoring from config.
  - Add explicit novelty subtype and meaningful-impact rationale fields.
  - Require evidence-backed domain tagging.

- `agents/hot_science/compiler.py`
  - Put top candidates first.
  - Show run configuration and criteria/rubric version.
  - Add "Why this is here" for manual-review queue items.
  - Add preprint and optional non-target-month watchlist sections.
  - Include source coverage diagnostics in Markdown/CSV outputs.

- `config/prompts.py`
  - Update Hot Science prompts only if an LLM-backed evaluator or resolver is introduced.
  - Keep prompt updates centralized here.

- `scripts/diagnose_hot_science_candidate.py`
  - Extend diagnostics to show primary-work alternatives, date fields, resolver decisions, fit assessment, and routing reason.

- `tests/test_hot_science_pipeline.py`
  - Add fixture-driven tests for every reviewer-confirmed failure mode and keep example.

## Calibration Examples

- Keep example: Hidden ocean heat moving toward Antarctica's ice shelves; relevant to cryosphere/ocean warming and in the correct window.
- Keep but lower broad-impact ranking: Slovakia wildfire paper; relevant but geographically narrow.
- Relevant but wrong month: salmon predator in warming Alaska waters; route to watchlist if enabled, not monthly set.
- Wrong primary work: Sea Land Breeze / ocean warming item where the agent selected a Zenodo deposit instead of the Nature Climate Change paper.
- False positive off-scope: Cascadia subduction zone paper; geology/earthquake focus, not Hot Science climate impact.
- False positive off-scope: Twelve Apostles formation paper; formation history and ancient climate context without contemporary climate relevance.
- False positive off-scope: East Africa rifting paper; tectonic shift, not the run focus.
- Historical/paleoclimate exclusion: Maya collapse, Neanderthal, ancient Antarctic ice unless direct contemporary/future implication is explicit.
- Ambiguous keyword exclusion: airborne microplastics where emissions/particles/atmosphere do not imply greenhouse gas or climate mechanism.
- Methods-only exclusion: Arctic sea ice thickness method paper unless it reports a substantive climate finding.
- Social-science-only exclusion: climate citizenship/textbook paper for natural-science Hot Science selection.
- Not article-level exclusion: journal-level metadata record.
- Manual review: title-only plausible climate item with no abstract after recovery attempts.
- Separate bucket: preprints.

## Implementation Phases

- Phase 1: Add schema/config support for routing reasons, fit assessment, rubric version, domains, weights, watchlist settings, and primary-work type.
- Phase 2: Add calibration fixtures from updated docs and tests that currently document expected behavior, even before all logic passes.
- Phase 3: Improve primary-work resolution and date discipline, including artifact preference rules and date-field validation.
- Phase 4: Implement abstract-first evidence-of-fit, evidence-backed domain tagging, and manual-review routing for title-only items.
- Phase 5: Rework scoring to remove audience relevance, add weights, novelty subtype, meaningful-impact evidence, and additive-only secondary signals.
- Phase 6: Redesign compiler output order and explanations: top candidates first, run config, preprints, watchlist, manual-review reasons, source diagnostics.
- Phase 7: Replace or supplement journal RSS backfills with scholarly API queries by ISSN/month, then run April 2026 regression diagnostics.

## Testing And Evaluation

- Unit-test resolver preference for canonical articles over code/data deposits.
- Unit-test date eligibility for online publication date vs press, submission, received, updated, and deposit dates.
- Unit-test evidence-of-fit for keep, exclude, and manual-review examples.
- Unit-test domain tags so ambiguous keywords do not create unsupported climate tags.
- Unit-test scoring weights and removal of audience relevance from the composite.
- Unit-test manual-review output so each item has a routing reason.
- Add snapshot or fixture tests for the April 2026 commented examples.
- Run `python -m pytest tests/test_hot_science_pipeline.py -v`.
- Run a local April 2026 diagnostic with `scripts/run_hot_science.py` after source changes.
- For live AWS/Bedrock features, gate tests behind explicit environment flags and the existing `.env` pattern.

## Open Questions

- Should the non-target-month watchlist be enabled by default or only on request?
- What exact rubric weights should Science R&D approve after removing audience relevance?
- Should preprints be scored in their own section, or only listed with minimal metadata?
- Which institutional data sources are approved for the allowlist, and who owns changes to that allowlist?
- How broad should the initial domain list become before it starts hurting precision?
- Should LLM-backed evidence-of-fit be introduced now, or should deterministic/fixture-driven rules come first?
- What is the minimum acceptable abstract recovery effort before title-only manual review?
- Should social science ever enter Hot Science if it reports climate impacts, or should natural/Earth-system science remain a hard gate for UC-I-1?

