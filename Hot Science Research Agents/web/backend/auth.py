"""Pilot authentication helpers for the DeepGreen web backend."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from dataclasses import dataclass
from typing import Any


DEFAULT_SESSION_TTL_SECONDS = 12 * 60 * 60


@dataclass(frozen=True)
class UserIdentity:
    username: str
    is_admin: bool = False

    def to_dict(self) -> dict[str, str | bool]:
        return {"username": self.username, "is_admin": self.is_admin}


@dataclass(frozen=True)
class AuthConfig:
    users: dict[str, str]
    admin_users: frozenset[str]
    session_secret: str
    session_ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS

    @classmethod
    def from_env(cls) -> "AuthConfig":
        users_json = os.getenv("DEEPGREEN_UI_USERS_JSON", "")
        users = parse_users_json(users_json)
        admin_users = frozenset(
            user.strip()
            for user in os.getenv("DEEPGREEN_UI_ADMIN_USERS", "user1").split(",")
            if user.strip()
        )
        session_secret = os.getenv("DEEPGREEN_UI_SESSION_SECRET") or secrets.token_urlsafe(32)
        ttl = int(os.getenv("DEEPGREEN_UI_SESSION_TTL_SECONDS", str(DEFAULT_SESSION_TTL_SECONDS)))
        return cls(
            users=users,
            admin_users=admin_users,
            session_secret=session_secret,
            session_ttl_seconds=ttl,
        )

    def authenticate(self, username: str, password: str) -> UserIdentity | None:
        expected = self.users.get(username)
        if expected is None:
            return None
        if not hmac.compare_digest(expected, password):
            return None
        return UserIdentity(username=username, is_admin=username in self.admin_users)

    def create_token(self, identity: UserIdentity, *, now: int | None = None) -> str:
        issued_at = now or int(time.time())
        payload = {
            "sub": identity.username,
            "admin": identity.is_admin,
            "iat": issued_at,
            "exp": issued_at + self.session_ttl_seconds,
        }
        encoded_payload = _b64encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        signature = _sign(encoded_payload, self.session_secret)
        return f"{encoded_payload}.{signature}"

    def verify_token(self, token: str, *, now: int | None = None) -> UserIdentity | None:
        try:
            encoded_payload, signature = token.split(".", 1)
        except ValueError:
            return None
        expected = _sign(encoded_payload, self.session_secret)
        if not hmac.compare_digest(signature, expected):
            return None
        try:
            payload = json.loads(_b64decode(encoded_payload).decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, ValueError):
            return None
        username = str(payload.get("sub") or "")
        if username not in self.users:
            return None
        expires_at = int(payload.get("exp") or 0)
        if expires_at < (now or int(time.time())):
            return None
        return UserIdentity(username=username, is_admin=username in self.admin_users)


def parse_users_json(value: str) -> dict[str, str]:
    """Parse the secret-backed user map."""
    if not value or value.startswith("<"):
        return {}
    try:
        payload: Any = json.loads(value)
    except json.JSONDecodeError as exc:
        raise ValueError("DEEPGREEN_UI_USERS_JSON must be a JSON object.") from exc
    if not isinstance(payload, dict):
        raise ValueError("DEEPGREEN_UI_USERS_JSON must be a JSON object.")
    users: dict[str, str] = {}
    for username, password in payload.items():
        if not isinstance(username, str) or not isinstance(password, str):
            raise ValueError("DEEPGREEN_UI_USERS_JSON keys and values must be strings.")
        if username and password:
            users[username] = password
    return users


def _sign(encoded_payload: str, secret: str) -> str:
    digest = hmac.new(
        secret.encode("utf-8"),
        encoded_payload.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    return _b64encode(digest)


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(value + padding)
