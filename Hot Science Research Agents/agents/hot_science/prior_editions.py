"""Prior-edition checks for Hot Science candidates."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher

from agents.hot_science.schema import CandidateRecord, PriorEditionMention
from agents.hot_science.storage import CandidateStore, normalize_title


@dataclass(frozen=True)
class PriorEditionResult:
    candidates: list[CandidateRecord]


class PriorEditionCheckerAgent:
    """Flag candidates that appear to have been covered in earlier runs."""

    def __init__(self, store: CandidateStore):
        self.store = store

    def check(self, candidates: list[CandidateRecord]) -> PriorEditionResult:
        history = [
            record
            for record in self.store.list_candidates()
            if record.target_month and record.target_month not in {c.target_month for c in candidates}
        ]
        for candidate in candidates:
            for previous in history:
                confidence = prior_match_confidence(candidate, previous)
                if not confidence:
                    continue
                candidate.prior_editions.append(
                    PriorEditionMention(
                        title=previous.title,
                        target_month=previous.target_month,
                        url=previous.publication.primary_source_url or previous.publication.url,
                        note="Matched previous Hot Science candidate history.",
                        confidence=confidence,
                    )
                )
                candidate.add_audit(
                    "prior_edition_checker",
                    "prior_edition_match",
                    f"{previous.target_month}: {previous.title}",
                )
                break
            if not candidate.prior_editions:
                candidate.add_audit("prior_edition_checker", "no_prior_edition_match")
        return PriorEditionResult(candidates=candidates)


def prior_match_confidence(current: CandidateRecord, previous: CandidateRecord) -> str | None:
    current_doi = current.normalized_doi()
    previous_doi = previous.normalized_doi()
    if current_doi and previous_doi and current_doi == previous_doi:
        return "high"
    current_title = normalize_title(current.title)
    previous_title = normalize_title(previous.title)
    if not current_title or not previous_title:
        return None
    score = SequenceMatcher(None, current_title, previous_title).ratio()
    if score >= 0.94:
        return "high"
    if score >= 0.88:
        return "medium"
    return None
