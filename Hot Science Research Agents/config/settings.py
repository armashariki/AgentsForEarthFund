"""Centralized configuration loading from .env file."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

# Load .env from project root
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def _require(var: str) -> str:
    """Get a required environment variable or raise."""
    value = os.getenv(var)
    if not value:
        raise EnvironmentError(f"Required environment variable {var} is not set. Check your .env file.")
    return value


def _optional(var: str, default: str = "") -> str:
    """Get an optional environment variable with a default."""
    value = os.getenv(var, default)
    if value.startswith("<") and value.endswith(">"):
        return default
    return value


def _optional_int(var: str, default: int) -> int:
    """Get an optional integer environment variable with a default."""
    value = _optional(var, "")
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise EnvironmentError(f"Environment variable {var} must be an integer.") from exc


@dataclass(frozen=True)
class Settings:
    # AWS
    aws_region: str = field(default_factory=lambda: _require("AWS_REGION"))
    aws_profile: str = field(default_factory=lambda: _optional("AWS_PROFILE", "default"))

    # Bedrock Models
    model_strong: str = field(default_factory=lambda: _require("MODEL_STRONG"))
    model_fast: str = field(default_factory=lambda: _require("MODEL_FAST"))
    model_lite: str = field(default_factory=lambda: _require("MODEL_LITE"))
    model_embed: str = field(default_factory=lambda: _require("MODEL_EMBED"))

    # Knowledge Base
    kb_id: str = field(default_factory=lambda: _optional("KB_ID"))
    kb_s3_bucket: str = field(default_factory=lambda: _optional("KB_S3_BUCKET", "deepgreen-knowledge-base"))
    aoss_collection_arn: str = field(default_factory=lambda: _optional("AOSS_COLLECTION_ARN"))
    kb_vector_index_name: str = field(default_factory=lambda: _optional("KB_VECTOR_INDEX_NAME", "deepgreen-grants-index"))
    kb_name: str = field(default_factory=lambda: _optional("KB_NAME", "DeepGreen-Grants-KB"))
    kb_data_source_name: str = field(default_factory=lambda: _optional("KB_DATA_SOURCE_NAME", "deepgreen-s3-source"))

    # Guardrail
    guardrail_id: str = field(default_factory=lambda: _optional("GUARDRAIL_ID"))
    guardrail_version: str = field(default_factory=lambda: _optional("GUARDRAIL_VERSION", "DRAFT"))
    guardrail_name: str = field(default_factory=lambda: _optional("GUARDRAIL_NAME", "DeepGreen-Guardrail"))

    # IAM
    iam_role_name: str = field(default_factory=lambda: _optional("IAM_ROLE_NAME", "DeepGreen-AgentRole"))
    iam_policy_name: str = field(default_factory=lambda: _optional("IAM_POLICY_NAME", "DeepGreen-AgentPolicy"))

    # Application
    app_name: str = field(default_factory=lambda: _optional("APP_NAME", "DeepGreen"))
    log_level: str = field(default_factory=lambda: _optional("LOG_LEVEL", "INFO"))
    hot_science_data_dir: str = field(default_factory=lambda: _optional("HOT_SCIENCE_DATA_DIR", ".deepgreen/hot_science"))
    hot_science_report_retention_days: int = field(default_factory=lambda: _optional_int("HOT_SCIENCE_REPORT_RETENTION_DAYS", 30))
    deepgreen_ui_users_json: str = field(default_factory=lambda: _optional("DEEPGREEN_UI_USERS_JSON"))
    deepgreen_ui_admin_users: str = field(default_factory=lambda: _optional("DEEPGREEN_UI_ADMIN_USERS", "user1"))
    deepgreen_ui_session_secret: str = field(default_factory=lambda: _optional("DEEPGREEN_UI_SESSION_SECRET"))
    deepgreen_ui_session_ttl_seconds: int = field(default_factory=lambda: _optional_int("DEEPGREEN_UI_SESSION_TTL_SECONDS", 43200))


settings = Settings()
