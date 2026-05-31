"""Bedrock model configurations with three tiers."""

from dataclasses import dataclass

from strands.models.bedrock import BedrockModel

from config.settings import settings


@dataclass(frozen=True)
class ModelTier:
    name: str
    model_id: str
    description: str


MODEL_TIERS = {
    "strong": ModelTier(
        name="Claude Sonnet 4",
        model_id=settings.model_strong,
        description="Complex analysis, grant evaluation, research synthesis",
    ),
    "fast": ModelTier(
        name="Nova Pro",
        model_id=settings.model_fast,
        description="Specialist agents, literature search, data analysis",
    ),
    "lite": ModelTier(
        name="Nova Lite",
        model_id=settings.model_lite,
        description="Routing, classification, lightweight tasks",
    ),
}


def get_model(tier: str) -> BedrockModel:
    """Get a BedrockModel instance for the given tier.

    Args:
        tier: One of 'strong', 'fast', or 'lite'.

    Returns:
        Configured BedrockModel instance.
    """
    if tier not in MODEL_TIERS:
        raise ValueError(f"Unknown model tier '{tier}'. Choose from: {list(MODEL_TIERS.keys())}")

    model_tier = MODEL_TIERS[tier]
    model_config = {
        "model_id": model_tier.model_id,
        "region_name": settings.aws_region,
    }

    if settings.guardrail_id:
        model_config.update(
            guardrail_id=settings.guardrail_id,
            guardrail_version=settings.guardrail_version or "DRAFT",
            guardrail_trace="enabled",
        )

    return BedrockModel(**model_config)
