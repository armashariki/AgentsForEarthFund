"""Significance Evaluator Agent for UC-I-1 Hot Science."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from agents.hot_science.config import HotScienceConfig, load_hot_science_config
from agents.hot_science.schema import CandidateRecord, ScoreItem, SignificanceAssessment
from agents.hot_science.verification import PRIMARY_ELIGIBLE_TYPES


METHODS_ONLY_TERMS = (
    "method",
    "protocol",
    "benchmark",
    "retrieval",
    "sampling technique",
    "model intercomparison",
)
METHOD_OR_TOOL_PERFORMANCE_TERMS = (
    "ai weather",
    "benchmark",
    "forecast accuracy",
    "forecast errors",
    "forecast model",
    "model performance",
    "outperform",
    "prediction model",
    "temperature-based diagnosis",
    "weather forecast",
)
ADAPTATION_RESPONSE_EVALUATION_TERMS = (
    "adaptation strategy",
    "early warning",
    "improving forecasts",
    "intervention",
    "policy efficacy",
    "reduce mortality",
    "response strategy",
)
CONCEPTUAL_OR_PERSPECTIVE_TERMS = (
    "perspective proposes",
    "proposes a framework",
    "position paper",
)
SOLUTIONS_TERMS = (
    "photovoltaic",
    "battery",
    "electric vehicle",
    "carbon pricing",
    "policy efficacy",
    "cost reduction",
)
PALEO_TERMS = (
    "ancient",
    "glacial-interglacial",
    "holocene",
    "ice core",
    "interglacial",
    "mid-brunhes",
    "million years",
    "million-year",
    "paleoclimate",
    "paleozoic",
    "past climate",
    "past climates",
    "pleistocene",
)
LAB_TERMS = ("growth chamber", "ex-situ", "laboratory experiment", "lab experiment")
CLIMATE_TERMS = (
    "anthropogenic",
    "attribution",
    "biodiversity",
    "carbon",
    "climate",
    "drought",
    "ecosystem",
    "food",
    "glacier",
    "greenhouse",
    "heat",
    "ice",
    "ice loss",
    "ocean heat",
    "ocean warming",
    "permafrost",
    "sea level",
    "sea-level",
    "thermal regime",
    "warming",
    "wildfire",
)
DIRECT_CLIMATE_LENS_TERMS = (
    "anthropogenic climate",
    "anthropogenic warming",
    "basal melting",
    "carbon budget",
    "carbon emission",
    "climate change",
    "climate-driven",
    "climate impact",
    "climate model",
    "climate projection",
    "climate risk",
    "climate scenario",
    "climatic impact",
    "emission target",
    "emissions target",
    "future ice loss",
    "future sea-level",
    "future warming",
    "global warming",
    "greenhouse gas",
    "greenhouse gases",
    "ice loss",
    "in a warming climate",
    "marine heat wave",
    "marine heatwave",
    "ocean heat",
    "ocean warming",
    "permafrost thaw",
    "projected warming",
    "rapidly warming",
    "rising sea level",
    "rising sea levels",
    "sea level rise",
    "sea surface temperature",
    "sea-level rise",
    "under climate change",
    "under global warming",
    "under warming",
    "warming climate",
    "warming ocean",
    "warming oceans",
    "warming waters",
    "warming world",
)
NON_CLIMATE_PRIMARY_DRIVER_TERMS = (
    "dominant drivers",
    "dominant driver",
    "exceeding the influence",
    "human activities as the dominant",
    "local human activities",
)
RUN_FOCUS_STOPWORDS = {
    "and",
    "especially",
    "finding",
    "findings",
    "for",
    "implication",
    "implications",
    "new",
    "research",
    "risk",
    "the",
    "with",
}
CONTEMPORARY_RELEVANCE_TERMS = (
    "anthropogenic",
    "climate change",
    "coastal risk",
    "contemporary",
    "current climate",
    "current or future",
    "future",
    "impact",
    "modern",
    "present-day",
    "projected",
    "risk",
    "sea-level",
    "under warming",
)
FORMATION_HISTORY_TERMS = (
    "formation",
    "formed",
    "limestone stack",
    "millions of years ago",
    "rose from the ocean",
    "tectonic uplift",
    "uplift",
)
TECTONIC_TERMS = (
    "continental breakup",
    "crust",
    "earthquake",
    "plate",
    "rift",
    "rifting",
    "seismic",
    "subduction",
    "tectonic",
)
AMBIGUOUS_POLLUTANT_TERMS = (
    "airborne microplastic",
    "microplastic",
    "plastic pollutant",
)
SOCIAL_SCIENCE_ONLY_TERMS = (
    "citizenship",
    "communication",
    "education",
    "literacy",
    "pedagogy",
    "textbook",
    "thematic analysis",
)
SUBSTANTIVE_FINDING_TERMS = (
    "alter",
    "decline",
    "decrease",
    "exposure",
    "finding",
    "findings",
    "future",
    "impact",
    "increase",
    "intensif",
    "observed",
    "project",
    "report",
    "reveal",
    "risk",
    "show",
    "weaken",
)
NATURAL_PROCESS_TERMS = (
    "atmospheric river",
    "biodiversity",
    "carbon cycle",
    "drought",
    "ecosystem",
    "fire weather",
    "permafrost",
    "ocean",
    "sea level",
    "sea-level",
    "temperature",
    "thermal",
    "warming",
    "wildfire",
)
EARTH_SYSTEM_TERMS = (
    "earth system",
    "cryosphere",
    "ocean",
    "atmosphere",
    "carbon cycle",
    "feedback",
    "monsoon",
    "enso",
    "permafrost",
)
NOVELTY_FIRST_OBSERVATION_TERMS = (
    "first observation",
    "first direct",
    "first evidence",
    "first record",
    "for the first time",
)
NOVELTY_ADVANCE_TERMS = (
    "advance",
    "higher-resolution",
    "improved",
    "new dataset",
    "new method",
    "novel",
    "record",
    "unprecedented",
)
NOVELTY_ESTABLISHED_AREA_TERMS = (
    "finding",
    "findings",
    "new",
    "observed",
    "reveals",
    "shows",
)
IMPACT_TERMS = (
    "billion",
    "coastal risk",
    "exposure",
    "global",
    "large-scale",
    "million",
    "multi-country",
    "regional",
    "risk",
    "system-level",
)
CROSS_DISCIPLINARY_TERMS = (
    "biodiversity",
    "cities",
    "economic",
    "food",
    "health",
    "migration",
)
CASCADING_TERMS = (
    "cascade",
    "cascading",
    "compound",
    "downstream",
    "feedback",
    "risk",
    "teleconnection",
)
AUDIENCE_TERMS = (
    "people",
    "population",
    "health",
    "cities",
    "food",
    "crop",
    "wildfire",
    "heat",
    "flood",
    "species",
    "whale",
    "walrus",
    "octopus",
)


@dataclass(frozen=True)
class EvaluationResult:
    evaluated: list[CandidateRecord]
    excluded: list[CandidateRecord]
    preprints: list[CandidateRecord] = field(default_factory=list)
    manual_review: list[CandidateRecord] = field(default_factory=list)


class SignificanceEvaluatorAgent:
    """Score verified candidates against the Hot Science rubric.

    This is the deterministic v1 evaluator scaffold. The prompt-based Claude
    evaluator can be layered behind this interface once we have the team's
    ground-truth March/April examples and desired calibration.
    """

    def __init__(self, config: HotScienceConfig | None = None):
        self.config = config or load_hot_science_config()

    def evaluate(
        self,
        candidates: list[CandidateRecord],
        *,
        user_criteria: str | None = None,
    ) -> EvaluationResult:
        evaluated: list[CandidateRecord] = []
        excluded: list[CandidateRecord] = []
        preprints: list[CandidateRecord] = []
        manual_review: list[CandidateRecord] = []
        for candidate in candidates:
            candidate.source_status = "verified"
            candidate.significance = SignificanceAssessment()
            candidate.rubric_version = None
            candidate.honorable_mention_candidate = False
            if _is_preprint_candidate(candidate):
                self._route_preprint(candidate)
                preprints.append(candidate)
                continue
            self._apply_hard_exclusions(candidate, user_criteria=user_criteria)
            if candidate.exclusion_flags:
                candidate.source_status = "excluded"
                candidate.add_audit("evaluator", "excluded", "hard_exclusion")
                excluded.append(candidate)
                continue
            if candidate.source_status == "manual_review":
                manual_review.append(candidate)
                continue
            self._score_candidate(candidate)
            candidate.source_status = "evaluated"
            candidate.add_audit("evaluator", "evaluated")
            evaluated.append(candidate)
        return EvaluationResult(
            evaluated=evaluated,
            excluded=excluded,
            preprints=preprints,
            manual_review=manual_review,
        )

    def _route_preprint(self, candidate: CandidateRecord) -> None:
        candidate.source_status = "preprint"
        candidate.routing_reason = "preprint_separate_bucket"
        candidate.fit_assessment.evidence_source = (
            "abstract" if candidate.abstract else "primary_metadata"
        )
        candidate.fit_assessment.evidence_snippet = _evidence_snippet(candidate)
        candidate.add_audit("evaluator", "preprint", "preprint_separate_bucket")

    def _apply_hard_exclusions(
        self,
        candidate: CandidateRecord,
        *,
        user_criteria: str | None,
    ) -> None:
        text = corpus_text(candidate)
        evidence_text = evidence_corpus_text(candidate)
        venue_type = candidate.publication.venue_type
        domain_tags = self._evidence_domain_tags(candidate)
        candidate.topic_tags = domain_tags
        candidate.fit_assessment.passed = None
        candidate.fit_assessment.relevance_claim = None
        candidate.fit_assessment.manual_review_reason = None
        candidate.fit_assessment.standing_scope_aligned = None
        candidate.fit_assessment.run_focus_aligned = None
        candidate.fit_assessment.supported_domain_tags = domain_tags
        candidate.fit_assessment.evidence_source = (
            "abstract" if candidate.abstract else "primary_metadata"
        )
        candidate.fit_assessment.evidence_snippet = _evidence_snippet(candidate)

        if venue_type not in PRIMARY_ELIGIBLE_TYPES and venue_type != "preprint":
            candidate.add_exclusion(
                "ineligible_source_type",
                f"Source type '{venue_type}' is not eligible for primary inclusion.",
            )
        if venue_type == "preprint":
            candidate.add_exclusion(
                "preprint_bucket",
                "Preprints are surfaced for review but not promoted to primary inclusion in v1.",
            )

        if _contains_any(text, FORMATION_HISTORY_TERMS):
            candidate.add_exclusion(
                "historical_or_formation_without_current_climate_implication",
                "Formation-history framing lacks explicit contemporary or future climate implications.",
            )
        if _contains_any(text, PALEO_TERMS) and not _contains_any(
            text, CONTEMPORARY_RELEVANCE_TERMS
        ):
            candidate.add_exclusion(
                "paleoclimate_without_current_implication",
                "Paleoclimate framing lacks explicit contemporary or future climate implications.",
            )
        if _is_historical_without_current_climate_relevance(text):
            candidate.add_exclusion(
                "historical_without_current_climate_implication",
                "Historical climate framing lacks explicit contemporary or future climate implications.",
            )
        if _contains_any(evidence_text, AMBIGUOUS_POLLUTANT_TERMS) and not _contains_any(
            evidence_text, ("climate change", "greenhouse", "warming", "radiative", "carbon")
        ):
            candidate.add_exclusion(
                "ambiguous_keyword_without_climate_mechanism",
                "Ambiguous atmospheric/emissions language does not support a climate mechanism.",
            )
        if _contains_any(evidence_text, METHODS_ONLY_TERMS) and not _has_substantive_climate_finding(
            evidence_text
        ):
            candidate.add_exclusion(
                "methods_only_without_substantive_climate_finding",
                "Methods or data-product framing lacks a substantive climate finding.",
            )
        if _contains_any(evidence_text, SOCIAL_SCIENCE_ONLY_TERMS) and not _contains_any(
            evidence_text, NATURAL_PROCESS_TERMS
        ):
            candidate.add_exclusion(
                "social_science_without_natural_science_finding",
                "Social-science, literacy, education, or communication framing lacks a natural-science finding.",
            )
        if _contains_any(evidence_text, TECTONIC_TERMS) and not _has_climate_mechanism(
            evidence_text
        ):
            candidate.add_exclusion(
                "no_evidence_of_hot_science_fit",
                "Tectonic or geology framing lacks an evidence-backed Hot Science climate connection.",
            )

        if not _has_climate_mechanism(evidence_text):
            candidate.add_exclusion(
                "no_evidence_of_hot_science_fit",
                "Abstract or primary metadata does not support a Hot Science relevance claim.",
            )
        if not domain_tags:
            candidate.add_exclusion(
                "no_supported_climate_impact_domain",
                "Evidence does not support any configured Hot Science climate-impact domain.",
            )

        focus_domains = self._run_focus_domain_ids(user_criteria)
        if focus_domains and not set(domain_tags).intersection(focus_domains):
            candidate.add_exclusion(
                "run_focus_mismatch",
                "Candidate fits standing Hot Science scope but not the run-specific focus.",
            )
            candidate.fit_assessment.run_focus_aligned = False
        elif focus_domains:
            candidate.fit_assessment.run_focus_aligned = bool(
                set(domain_tags).intersection(focus_domains)
            )
        else:
            candidate.fit_assessment.run_focus_aligned = None

        if _contains_any(text, SOLUTIONS_TERMS):
            candidate.add_exclusion(
                "solutions_paper",
                "Appears to focus on intervention performance or policy efficacy, out of scope for v1.",
            )
        if _contains_any(text, LAB_TERMS) and not _contains_any(text, ("field", "ecosystem", "system-level")):
            candidate.add_exclusion(
                "ex_situ_lab",
                "Lab-only study without clear field or system-level interpretation.",
            )
        if candidate.exclusion_flags:
            candidate.fit_assessment.passed = False
            candidate.fit_assessment.standing_scope_aligned = False
            return

        manual_review_reason = _strict_fit_manual_review_reason(candidate, evidence_text)
        if manual_review_reason:
            code, reason = manual_review_reason
            candidate.source_status = "manual_review"
            candidate.routing_reason = code
            candidate.fit_assessment.passed = None
            candidate.fit_assessment.standing_scope_aligned = False
            candidate.fit_assessment.manual_review_reason = reason
            candidate.add_missing_reason("fit_assessment.strict_gate", reason)
            candidate.add_audit("evaluator", "manual_review", code)
            return

        candidate.fit_assessment.passed = True
        candidate.fit_assessment.standing_scope_aligned = True
        candidate.fit_assessment.relevance_claim = _relevance_claim(candidate)
        candidate.routing_reason = "evidence_fit_in_target_month"

    def _score_candidate(self, candidate: CandidateRecord) -> None:
        text = corpus_text(candidate)
        tags = candidate.topic_tags or self._evidence_domain_tags(candidate) or topic_tags(text)
        candidate.topic_tags = tags
        candidate.theme_cluster = tags[0] if tags else "general_climate_research"

        confidence = "high" if candidate.abstract else "medium"
        if candidate.publication.abstract_accessible is False:
            confidence = "low"

        novelty_subtype = _novelty_subtype(text)
        novelty = _selection_score(
            text,
            NOVELTY_FIRST_OBSERVATION_TERMS
            + NOVELTY_ADVANCE_TERMS
            + NOVELTY_ESTABLISHED_AREA_TERMS,
        )
        impact = _selection_score(text, IMPACT_TERMS)
        earth = _selection_score(text, EARTH_SYSTEM_TERMS)
        cross = _additive_score(text, CROSS_DISCIPLINARY_TERMS)
        cascading = _additive_score(text, CASCADING_TERMS)
        audience = _additive_score(text, AUDIENCE_TERMS)

        novelty_item = ScoreItem(
            novelty,
            _novelty_rationale(novelty_subtype),
            confidence,
            evidence=_evidence_for_terms(
                candidate,
                NOVELTY_FIRST_OBSERVATION_TERMS
                + NOVELTY_ADVANCE_TERMS
                + NOVELTY_ESTABLISHED_AREA_TERMS,
            ),
            subtype=novelty_subtype,
            weight=self._dimension_weight("novelty"),
        )
        impact_item = ScoreItem(
            impact,
            "Meaningful impact, scale, or generalizability signals found in abstract/metadata.",
            confidence,
            evidence=_evidence_for_terms(candidate, IMPACT_TERMS),
            subtype=_impact_subtype(text),
            weight=self._dimension_weight("impact_magnitude"),
        )
        cross_item = ScoreItem(
            cross,
            "Additive-only cross-domain signal; absence does not penalize candidate selection.",
            confidence,
            evidence=_evidence_for_terms(candidate, CROSS_DISCIPLINARY_TERMS),
            weight=self._dimension_weight("cross_disciplinary"),
        )
        earth_item = ScoreItem(
            earth,
            "Earth-system process signals found in abstract/metadata.",
            confidence,
            evidence=_evidence_for_terms(candidate, EARTH_SYSTEM_TERMS),
            weight=self._dimension_weight("earth_system_signal"),
        )
        audience_item = ScoreItem(
            audience,
            "Audience-resonance signal reserved for future summary drafting, not selection.",
            confidence,
            evidence=_evidence_for_terms(candidate, AUDIENCE_TERMS),
            weight=self._dimension_weight("audience_relevance"),
        )
        cascading_item = ScoreItem(
            cascading,
            "Additive-only downstream/cascading impact signal; absence does not penalize candidate selection.",
            confidence,
            evidence=_evidence_for_terms(candidate, CASCADING_TERMS),
            weight=self._dimension_weight("cascading_impact"),
        )

        assessment = SignificanceAssessment(
            rubric_version=self.config.rubric.version,
            novelty=novelty_item,
            impact_magnitude=impact_item,
            cross_disciplinary=cross_item,
            earth_system_signal=earth_item,
            audience_relevance=audience_item,
            cascading_impact=cascading_item,
            composite_score=self._weighted_composite(
                {
                    "novelty": novelty_item,
                    "impact_magnitude": impact_item,
                    "cross_disciplinary": cross_item,
                    "earth_system_signal": earth_item,
                    "audience_relevance": audience_item,
                    "cascading_impact": cascading_item,
                }
            ),
            overall_confidence=confidence,
        )
        candidate.significance = assessment
        candidate.rubric_version = self.config.rubric.version
        candidate.honorable_mention_candidate = audience >= 3 and impact <= 2

    def _evidence_domain_tags(self, candidate: CandidateRecord) -> list[str]:
        text = evidence_corpus_text(candidate)
        tags: list[str] = []
        for domain in self.config.domains:
            if _contains_any(text, tuple(term.casefold() for term in domain.terms)):
                tags.append(domain.id)
        if tags:
            return tags
        return topic_tags(text)

    def _run_focus_domain_ids(self, user_criteria: str | None) -> set[str]:
        if not user_criteria:
            return set()
        text = _normalize_text(user_criteria)
        focus_ids: set[str] = set()
        for domain in self.config.domains:
            domain_terms = {_normalize_text(domain.id), _normalize_text(domain.label)}
            domain_terms.update(_normalize_text(term) for term in domain.terms)
            if any(term and term in text for term in domain_terms):
                focus_ids.add(domain.id)
        return focus_ids

    def _dimension_weight(self, dimension_id: str) -> float:
        try:
            return self.config.rubric.dimension(dimension_id).weight
        except ValueError:
            return 1.0

    def _weighted_composite(self, items: dict[str, ScoreItem]) -> float:
        total = 0.0
        if not self.config.rubric.dimensions:
            return float(sum(item.score or 0 for item in items.values()))
        for dimension in self.config.rubric.dimensions:
            if not dimension.selection_signal:
                continue
            item = items.get(dimension.id)
            if not item:
                continue
            score = item.score or 0
            total += score * dimension.weight
        return round(total, 2)


def corpus_text(candidate: CandidateRecord) -> str:
    return " ".join(
        part for part in [candidate.title, candidate.abstract, candidate.publication.venue] if part
    ).casefold()


def evidence_corpus_text(candidate: CandidateRecord) -> str:
    """Return the preferred evidence text for fit and domain checks."""
    if candidate.abstract:
        return candidate.abstract.casefold()
    return " ".join(
        part for part in [candidate.title, candidate.publication.venue] if part
    ).casefold()


def topic_tags(text: str) -> list[str]:
    tags: list[str] = []
    mapping = {
        "extreme_heat": ("heat", "temperature", "livability"),
        "cryosphere": ("ice", "glacier", "cryosphere", "permafrost"),
        "sea_level": ("sea level", "coastal", "ocean"),
        "fire": ("wildfire", "fire weather", "burned area"),
        "ecosystems": ("ecosystem", "biodiversity", "species", "forest", "peatland"),
        "food_systems": ("crop", "agriculture", "food"),
        "human_health": ("health", "mortality", "disease"),
        "climate_physics": ("warming", "energy imbalance", "attribution", "radiative"),
        "ocean_change": ("ocean warming", "ocean heat", "sea surface temperature"),
    }
    for tag, terms in mapping.items():
        if _contains_any(text, terms):
            tags.append(tag)
    return tags


def _score_by_terms(text: str, terms: tuple[str, ...]) -> int:
    hits = sum(1 for term in terms if term in text)
    return min(5, hits + 1)


def _selection_score(text: str, terms: tuple[str, ...]) -> int:
    """Score required selection dimensions with a modest baseline for fit-passing records."""
    return _score_by_terms(text, terms)


def _additive_score(text: str, terms: tuple[str, ...]) -> int:
    hits = sum(1 for term in terms if term in text)
    return min(5, hits)


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(_contains_term(text, term) for term in terms)


def _contains_term(text: str, term: str) -> bool:
    if not term:
        return False
    if term.isalpha() and len(term) <= 4:
        return re.search(rf"\b{re.escape(term)}\b", text) is not None
    return term in text


def _is_preprint_candidate(candidate: CandidateRecord) -> bool:
    return (
        candidate.publication.venue_type == "preprint"
        or candidate.publication.primary_work_type == "preprint"
    )


def _has_climate_mechanism(text: str) -> bool:
    return _contains_any(text, CLIMATE_TERMS)


def _has_substantive_climate_finding(text: str) -> bool:
    return _has_climate_mechanism(text) and _contains_any(text, SUBSTANTIVE_FINDING_TERMS)


def _has_direct_climate_lens(text: str) -> bool:
    return _contains_any(text, DIRECT_CLIMATE_LENS_TERMS)


def _strict_fit_manual_review_reason(
    candidate: CandidateRecord,
    evidence_text: str,
) -> tuple[str, str] | None:
    """Return a manual-review reason when fit is plausible but not precise enough.

    Hard exclusions remove clearly ineligible papers. This gate handles papers
    that mention climate-adjacent terms but do not yet justify promotion into
    the final Hot Science list without a reviewer decision.
    """

    full_text = corpus_text(candidate)

    if not _has_direct_climate_lens(full_text):
        return (
            "indirect_or_incidental_climate_lens",
            "Climate connection appears indirect or incidental; a reviewer should confirm that the underlying paper directly addresses climate change, global warming, or climate impacts.",
        )
    if _contains_any(full_text, METHOD_OR_TOOL_PERFORMANCE_TERMS):
        return (
            "method_or_tool_performance_focus",
            "Primary contribution appears to be a tool, forecast, benchmark, diagnostic, or model-performance result rather than a direct climate-impact finding.",
        )
    if _contains_any(full_text, ADAPTATION_RESPONSE_EVALUATION_TERMS):
        return (
            "adaptation_or_intervention_evaluation_focus",
            "Paper may evaluate an adaptation, response, warning, or intervention pathway; reviewer should confirm it reports a substantive climate-impact finding rather than only intervention performance.",
        )
    if _contains_any(full_text, NON_CLIMATE_PRIMARY_DRIVER_TERMS):
        return (
            "non_climate_primary_driver",
            "Evidence suggests a non-climate driver may be the primary result; reviewer should confirm climate change is central rather than contextual.",
        )
    if _contains_any(full_text, CONCEPTUAL_OR_PERSPECTIVE_TERMS):
        return (
            "conceptual_or_perspective_without_primary_finding",
            "Record appears conceptual, a perspective, or a position paper; reviewer should confirm it contains an eligible primary research finding.",
        )
    if not _has_substantive_climate_finding(evidence_text):
        return (
            "substantive_climate_finding_unclear",
            "Climate lens is present, but the abstract does not clearly state a substantive finding, impact, risk, or dataset output.",
        )
    return None


def _is_historical_without_current_climate_relevance(text: str) -> bool:
    historical = _contains_any(
        text,
        (
            "archaeolog",
            "historical",
            "human ancestors",
            "maya",
            "neanderthal",
            "tens of thousands",
            "thousands of years ago",
            "years ago",
        ),
    )
    return historical and not _contains_any(text, CONTEMPORARY_RELEVANCE_TERMS)


def _evidence_snippet(candidate: CandidateRecord) -> str | None:
    text = candidate.abstract or candidate.title
    if not text:
        return None
    return text[:320]


def _relevance_claim(candidate: CandidateRecord) -> str:
    tags = ", ".join(candidate.fit_assessment.supported_domain_tags) or "climate science"
    return f"This matters to Hot Science because the evidence supports a {tags} finding."


def _normalize_text(value: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.casefold()).split())


def _novelty_subtype(text: str) -> str:
    if _contains_any(text, NOVELTY_FIRST_OBSERVATION_TERMS):
        return "first_observation"
    if _contains_any(text, NOVELTY_ADVANCE_TERMS):
        return "substantial_advance_over_prior_work"
    if _contains_any(text, NOVELTY_ESTABLISHED_AREA_TERMS):
        return "new_finding_in_established_area"
    return "novelty_not_explicit"


def _novelty_rationale(subtype: str) -> str:
    labels = {
        "first_observation": "Novelty subtype: first observation or first direct evidence.",
        "substantial_advance_over_prior_work": "Novelty subtype: substantial advance over prior work.",
        "new_finding_in_established_area": "Novelty subtype: new finding in an established area.",
        "novelty_not_explicit": "Novelty subtype not explicit in abstract/metadata.",
    }
    return labels[subtype]


def _impact_subtype(text: str) -> str:
    if _contains_any(text, ("global", "multi-country", "large-scale", "billion")):
        return "broad_or_global_scope"
    if _contains_any(text, ("regional", "million", "coastal risk", "system-level")):
        return "regional_or_system_scale"
    if _contains_any(text, ("local", "site-specific", "case study")):
        return "local_or_site_specific"
    return "impact_scope_not_explicit"


def _evidence_for_terms(candidate: CandidateRecord, terms: tuple[str, ...]) -> str | None:
    text = candidate.abstract or candidate.title
    if not text:
        return None
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    for sentence in sentences:
        lowered = sentence.casefold()
        if _contains_any(lowered, terms):
            return sentence[:320]
    return None
