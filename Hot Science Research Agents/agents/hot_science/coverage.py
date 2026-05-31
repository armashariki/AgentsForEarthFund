"""Coverage Agent for UC-I-1 Hot Science candidates."""

from __future__ import annotations

from dataclasses import dataclass

from agents.hot_science.schema import CandidateRecord, PressCoverage


PRESS_SOURCE_TYPES = {"popular_press"}


@dataclass(frozen=True)
class CoverageResult:
    candidates: list[CandidateRecord]


class CoverageAgent:
    """Attach known popular-press coverage to evaluated candidates.

    The first implementation consolidates press mentions already discovered by
    Source Monitor. Dedicated outlet API searches are the next plug-in point.
    """

    def attach_coverage(self, candidates: list[CandidateRecord]) -> CoverageResult:
        for candidate in candidates:
            for mention in candidate.discovered_via:
                if mention.source_type not in PRESS_SOURCE_TYPES or not mention.url:
                    continue
                if any(coverage.url == mention.url for coverage in candidate.press_coverage):
                    continue
                candidate.press_coverage.append(
                    PressCoverage(
                        outlet=mention.source,
                        url=mention.url,
                        headline=candidate.title,
                        date=mention.date_seen,
                        verified=False,
                        verification_note="Press mention discovered; body verification pending.",
                    )
                )
            candidate.pop_press_found = bool(candidate.press_coverage)
            candidate.add_audit(
                "coverage",
                "coverage_attached" if candidate.pop_press_found else "no_coverage_found",
            )
        return CoverageResult(candidates=candidates)
