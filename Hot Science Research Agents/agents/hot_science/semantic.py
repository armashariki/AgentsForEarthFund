"""Semantic retrieval helpers for UC-I-1 Hot Science."""

from __future__ import annotations

import json
import math
import os

import boto3

from agents.hot_science.config import HotScienceConfig
from agents.hot_science.schema import CandidateRecord


def annotate_retrieval_signals(candidate: CandidateRecord, config: HotScienceConfig) -> None:
    """Attach lexical seed matches and a placeholder for semantic score."""
    text = candidate_search_text(candidate)
    candidate.seed_term_matches = [
        term for term in config.seed_terms if term.casefold() in text
    ]
    if candidate.retrieval_score is None:
        candidate.add_missing_reason(
            "retrieval_score",
            "Semantic embedding score not computed in this run.",
        )


def candidate_search_text(candidate: CandidateRecord) -> str:
    return " ".join(
        part for part in [candidate.title, candidate.abstract, candidate.publication.venue] if part
    ).casefold()


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """Compute cosine similarity for two embedding vectors."""
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


class BedrockSemanticScorer:
    """Bedrock Titan embedding scorer for retrieval intent similarity."""

    def __init__(self, model_id: str | None = None, region_name: str | None = None):
        from config.settings import settings

        self.model_id = model_id or settings.model_embed
        self.client = boto3.client("bedrock-runtime", region_name=region_name or settings.aws_region)

    def embed_text(self, text: str) -> list[float]:
        body = {
            "inputText": text[:25000],
            "dimensions": 1024,
            "normalize": True,
        }
        response = self.client.invoke_model(
            modelId=self.model_id,
            body=json.dumps(body),
            contentType="application/json",
            accept="application/json",
        )
        payload = json.loads(response["body"].read().decode("utf-8"))
        return payload["embedding"]

    def score_candidate(self, candidate: CandidateRecord, config: HotScienceConfig) -> float:
        intent_embedding = self.embed_text(config.intent.description)
        candidate_embedding = self.embed_text(candidate_search_text(candidate))
        score = cosine_similarity(intent_embedding, candidate_embedding)
        candidate.retrieval_score = round(score, 4)
        candidate.add_audit(
            "source_monitor",
            "semantic_score",
            f"score={candidate.retrieval_score}",
        )
        return score


def semantic_scoring_enabled() -> bool:
    return os.getenv("HOT_SCIENCE_ENABLE_BEDROCK_EMBEDDINGS") == "1"
