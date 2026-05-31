"""Shared test fixtures for DeepGreen tests."""

import os

import pytest


RUN_LIVE_BEDROCK = os.getenv("DEEPGREEN_RUN_LIVE_BEDROCK_TESTS") == "1"
RUN_LIVE_WEB = os.getenv("DEEPGREEN_RUN_LIVE_WEB_TESTS") == "1"


# Sample queries for testing
SAMPLE_GRANT_QUERIES = [
    (
        "Evaluate a proposal for using satellite imagery to monitor deforestation "
        "in the Amazon basin. Budget: $2M over 3 years."
    ),
    (
        "A community organization proposes a $500K environmental justice project "
        "to address air quality in underserved urban neighborhoods."
    ),
    "Tell me about climate.",  # vague query
]

SAMPLE_RESEARCH_QUERIES = [
    (
        "What are the most promising approaches to ocean-based carbon dioxide removal, "
        "and what are the key scientific uncertainties?"
    ),
    "What is the impact of microplastics on marine biodiversity?",
    "Research",  # vague query
]

SAMPLE_LITERATURE_QUERIES = [
    "Find recent publications on AI applications for biodiversity monitoring.",
    "Latest papers on nature-based solutions for climate adaptation.",
    "papers",  # vague query
]


@pytest.fixture
def grant_query():
    return SAMPLE_GRANT_QUERIES[0]


@pytest.fixture
def research_query():
    return SAMPLE_RESEARCH_QUERIES[0]


@pytest.fixture
def literature_query():
    return SAMPLE_LITERATURE_QUERIES[0]


class MockBedrockResponse:
    """Mock for Bedrock model responses in unit tests."""

    def __init__(self, text: str):
        self.text = text

    def __str__(self):
        return self.text
