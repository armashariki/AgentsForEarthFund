"""SQLite storage for UC-I-1 candidate records and run summaries."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from agents.hot_science.schema import CandidateRecord, utc_now_iso


DEFAULT_DB_PATH = Path(".deepgreen") / "hot_science" / "candidates.sqlite3"


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    target_month: str
    status: str
    raw_count: int
    verified_count: int
    evaluated_count: int
    excluded_count: int
    created_at: str


class CandidateStore:
    """Relational store for candidate records.

    This is the local development adapter. The schema is intentionally simple:
    indexed operational fields plus the full canonical JSON payload. The same
    repository-facing contract can later be backed by Postgres or DynamoDB.
    """

    def __init__(self, db_path: str | Path = DEFAULT_DB_PATH):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS candidates (
                    candidate_id TEXT PRIMARY KEY,
                    target_month TEXT,
                    doi TEXT,
                    normalized_title TEXT NOT NULL,
                    title TEXT NOT NULL,
                    venue_type TEXT,
                    online_publication_date TEXT,
                    composite_score REAL,
                    overall_confidence TEXT,
                    source_status TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_candidates_doi ON candidates(doi)"
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_candidates_month_score
                ON candidates(target_month, composite_score)
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    target_month TEXT NOT NULL,
                    status TEXT NOT NULL,
                    raw_count INTEGER NOT NULL,
                    verified_count INTEGER NOT NULL,
                    evaluated_count INTEGER NOT NULL,
                    excluded_count INTEGER NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    def upsert_candidate(self, candidate: CandidateRecord) -> None:
        """Insert or replace one candidate record."""
        payload = candidate.to_dict()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO candidates (
                    candidate_id, target_month, doi, normalized_title, title,
                    venue_type, online_publication_date, composite_score,
                    overall_confidence, source_status, payload_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                    target_month = excluded.target_month,
                    doi = excluded.doi,
                    normalized_title = excluded.normalized_title,
                    title = excluded.title,
                    venue_type = excluded.venue_type,
                    online_publication_date = excluded.online_publication_date,
                    composite_score = excluded.composite_score,
                    overall_confidence = excluded.overall_confidence,
                    source_status = excluded.source_status,
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (
                    candidate.candidate_id,
                    candidate.target_month,
                    candidate.normalized_doi(),
                    normalize_title(candidate.title),
                    candidate.title,
                    candidate.publication.venue_type,
                    candidate.publication.online_publication_date,
                    candidate.significance.composite_score,
                    candidate.significance.overall_confidence,
                    candidate.source_status,
                    json.dumps(payload, sort_keys=True),
                    utc_now_iso(),
                ),
            )

    def upsert_candidates(self, candidates: Iterable[CandidateRecord]) -> None:
        for candidate in candidates:
            self.upsert_candidate(candidate)

    def list_candidates(self, target_month: str | None = None) -> list[CandidateRecord]:
        """List candidates, newest/highest-scored first."""
        sql = "SELECT payload_json FROM candidates"
        params: tuple[str, ...] = ()
        if target_month:
            sql += " WHERE target_month = ?"
            params = (target_month,)
        sql += " ORDER BY composite_score DESC NULLS LAST, title ASC"
        with self._connect() as conn:
            return [
                CandidateRecord.from_dict(json.loads(row["payload_json"]))
                for row in conn.execute(sql, params)
            ]

    def record_run(self, run: RunRecord) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    run_id, target_month, status, raw_count, verified_count,
                    evaluated_count, excluded_count, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run.run_id,
                    run.target_month,
                    run.status,
                    run.raw_count,
                    run.verified_count,
                    run.evaluated_count,
                    run.excluded_count,
                    run.created_at,
                ),
            )


def normalize_title(title: str) -> str:
    """Normalize a title for duplicate lookup and storage indexes."""
    return " ".join(title.casefold().split())
