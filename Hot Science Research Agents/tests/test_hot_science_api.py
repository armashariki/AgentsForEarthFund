"""FastAPI route tests for the Hot Science pilot backend."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from agents.hot_science.compiler import CompilerAgent
from agents.hot_science.config import SourceConfig
from agents.hot_science.evaluator import SignificanceEvaluatorAgent
from agents.hot_science.orchestrator import HotScienceRunResult
from agents.hot_science.progress import ProgressEvent
from agents.hot_science.schema import CandidateRecord, PublicationInfo, SourceMention
from web.backend.artifacts import HotScienceArtifactStore
from web.backend.auth import AuthConfig
from web.backend.hot_science_service import HotScienceRunService
from web.backend.main import create_app


def test_health_and_login(tmp_path):
    client = _client(tmp_path)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["auth_configured"] is True

    failed = client.post(
        "/api/auth/login",
        json={"username": "user1", "password": "wrong"},
    )
    assert failed.status_code == 401

    login = client.post(
        "/api/auth/login",
        json={"username": "user1", "password": "password1"},
    )
    assert login.status_code == 200
    payload = login.json()
    assert payload["token_type"] == "bearer"
    assert payload["user"]["is_admin"] is True


def test_backend_imports_without_model_env_when_bedrock_embeddings_disabled():
    result = subprocess.run(
        [sys.executable, "-c", "import web.backend.main; print('ok')"],
        check=False,
        capture_output=True,
        text=True,
        env={
            **os.environ,
            "AWS_REGION": "",
            "MODEL_STRONG": "",
            "MODEL_FAST": "",
            "MODEL_LITE": "",
            "MODEL_EMBED": "",
            "HOT_SCIENCE_ENABLE_BEDROCK_EMBEDDINGS": "0",
        },
    )

    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout


def test_run_endpoint_requires_auth(tmp_path):
    client = _client(tmp_path)

    response = client.post(
        "/api/hot-science/runs",
        json={
            "target_month": "2026-04",
            "criteria_text": "Search query: climate change sea level rise",
        },
    )

    assert response.status_code == 401


def test_run_endpoint_returns_primary_docx_and_progress(tmp_path):
    client = _client(tmp_path)
    token = _login(client, "user2", "password2")

    response = client.post(
        "/api/hot-science/runs",
        headers=_auth(token),
        json={
            "target_month": "2026-04",
            "criteria_text": "Search query: climate change sea level rise\n\nInclude April papers.",
            "source_ids": ["openalex"],
            "max_results_per_source": 3,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["primary_artifact"]["kind"] == "docx"
    assert payload["primary_artifact"]["download_url"].startswith(
        "/api/hot-science/artifacts/"
    )
    assert payload["progress_events"][0]["event_type"] == "stage_started"
    assert payload["summary"]["run_id"] == "api-run-1"

    docx = client.get(payload["primary_artifact"]["download_url"], headers=_auth(token))
    assert docx.status_code == 200
    assert docx.headers["content-type"].startswith(
        "application/vnd.openxmlformats-officedocument"
    )


def test_normal_history_hides_debug_artifacts_and_admin_history_shows_them(tmp_path):
    client = _client(tmp_path)
    normal_token = _login(client, "user2", "password2")
    admin_token = _login(client, "user1", "password1")
    run = client.post(
        "/api/hot-science/runs",
        headers=_auth(normal_token),
        json={
            "target_month": "2026-04",
            "criteria_text": "Search query: climate change sea level rise",
        },
    ).json()

    normal_history = client.get("/api/hot-science/runs", headers=_auth(normal_token))
    assert normal_history.status_code == 200
    normal_run = normal_history.json()["runs"][0]
    assert normal_run["primary_artifact"]["kind"] == "docx"
    assert "artifacts" not in normal_run

    admin_history = client.get("/api/admin/hot-science/runs", headers=_auth(admin_token))
    assert admin_history.status_code == 200
    admin_run = admin_history.json()["runs"][0]
    assert any(artifact["kind"] == "json" for artifact in admin_run["artifacts"])

    json_artifact = next(
        artifact for artifact in admin_run["artifacts"] if artifact["kind"] == "json"
    )
    forbidden = client.get(json_artifact["download_url"], headers=_auth(normal_token))
    assert forbidden.status_code == 403
    allowed = client.get(json_artifact["download_url"], headers=_auth(admin_token))
    assert allowed.status_code == 200
    assert run["run_id"] == admin_run["run_id"]


def test_artifact_download_rejects_bad_paths(tmp_path):
    client = _client(tmp_path)
    token = _login(client, "user1", "password1")

    response = client.get(
        "/api/hot-science/artifacts/api-run-1/..%2Fescape.docx",
        headers=_auth(token),
    )

    assert response.status_code in {400, 404}


def test_admin_prunes_expired_runs(tmp_path):
    artifact_store = HotScienceArtifactStore(tmp_path)
    client = _client(tmp_path, artifact_store=artifact_store)
    admin_token = _login(client, "user1", "password1")
    client.post(
        "/api/hot-science/runs",
        headers=_auth(admin_token),
        json={
            "target_month": "2026-04",
            "criteria_text": "Search query: climate change sea level rise",
        },
    )
    manifest_path = tmp_path / "runs" / "api-run-1" / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["expires_at"] = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    manifest_path.write_text(json.dumps(manifest))

    history = client.get("/api/hot-science/runs", headers=_auth(admin_token))
    assert history.json()["runs"] == []

    pruned = client.post(
        "/api/admin/hot-science/prune-expired",
        headers=_auth(admin_token),
    )
    assert pruned.status_code == 200
    assert pruned.json()["removed"] == 1
    assert not (tmp_path / "runs" / "api-run-1").exists()


def _client(
    tmp_path,
    *,
    artifact_store: HotScienceArtifactStore | None = None,
) -> TestClient:
    artifact_store = artifact_store or HotScienceArtifactStore(tmp_path)
    service = HotScienceRunService(
        artifact_store=artifact_store,
        db_path=tmp_path / "candidates.sqlite3",
        runner=FakeRunner(),
    )
    app = create_app(
        service=service,
        artifact_store=artifact_store,
        auth_config=AuthConfig(
            users={"user1": "password1", "user2": "password2"},
            admin_users=frozenset({"user1"}),
            session_secret="test-secret",
        ),
    )
    return TestClient(app)


class FakeRunner:
    def run(self, target_month, **kwargs):
        callback = kwargs.get("progress_callback")
        if callback:
            callback(
                ProgressEvent(
                    event_type="stage_started",
                    stage="scanning_sources",
                    target_month=target_month,
                    run_id="api-run-1",
                    message="Scanning test sources",
                )
            )
        return HotScienceRunResult(
            run_id="api-run-1",
            target_month=target_month,
            user_criteria=kwargs["user_criteria"],
            raw_candidates=[],
            source_errors=[],
            compiled=_compiled_fixture(kwargs["user_criteria"]),
        )


def _compiled_fixture(user_criteria: str):
    candidate = SignificanceEvaluatorAgent().evaluate([_candidate()]).evaluated[0]
    source = SourceConfig(
        id="nature_climate_change",
        name="Nature Climate Change",
        kind="rss",
        source_type="peer_reviewed_journal",
    )
    return CompilerAgent().compile(
        target_month="2026-04",
        candidates=[candidate],
        excluded=[],
        manual_review=[],
        user_criteria=user_criteria,
        sources=(source,),
        rubric_version="hot_science_v2_candidate",
    )


def _candidate() -> CandidateRecord:
    return CandidateRecord(
        title="Ocean warming accelerates Antarctic ice shelf retreat",
        doi="10.1234/api.2026.001",
        authors=["Ada Ice", "Sam Ocean"],
        publication=PublicationInfo(
            venue="Nature Climate Change",
            venue_type="peer_reviewed_journal",
            online_publication_date="2026-04-12",
            url="https://doi.org/10.1234/api.2026.001",
            open_access=True,
        ),
        abstract=(
            "This study reports climate-change-driven ocean warming and Antarctic "
            "ice shelf retreat with implications for sea-level rise."
        ),
        abstract_source="publisher",
        discovered_via=[
            SourceMention(
                source="Nature Climate Change",
                url="https://doi.org/10.1234/api.2026.001",
                date_seen="2026-04-12",
                source_type="peer_reviewed_journal",
            )
        ],
        target_month="2026-04",
    )


def _login(client: TestClient, username: str, password: str) -> str:
    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}
