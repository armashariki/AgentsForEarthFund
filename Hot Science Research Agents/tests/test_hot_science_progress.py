"""Progress instrumentation tests for the Hot Science pipeline."""

from __future__ import annotations

import agents.hot_science.source_monitor as source_monitor_module
from agents.hot_science.config import HotScienceConfig, IntentConfig, SourceConfig
from agents.hot_science.orchestrator import HotScienceOrchestrator
from agents.hot_science.progress import ProgressEvent
from agents.hot_science.schema import CandidateRecord, PublicationInfo, SourceMention
from agents.hot_science.source_monitor import SourceMonitorAgent
from agents.hot_science.storage import CandidateStore


def test_source_monitor_emits_source_progress(monkeypatch):
    source = _source()
    config = _config(source)

    def fake_scan_source(source, **kwargs):
        return [_candidate(source)]

    monkeypatch.setattr(source_monitor_module, "scan_source", fake_scan_source)
    events: list[ProgressEvent] = []

    result = SourceMonitorAgent(config).scan(
        "2026-04",
        max_results_per_source=5,
        progress_callback=events.append,
        run_id="run-123",
    )

    assert len(result.candidates) == 1
    assert [event.event_type for event in events] == [
        "source_started",
        "source_completed",
    ]
    assert events[0].source_id == source.id
    assert events[0].stage == "scanning_sources"
    assert events[0].counts["query_count"] == 1
    assert events[1].counts["candidates"] == 1
    assert events[1].to_dict()["source_name"] == source.name


def test_source_monitor_emits_source_error_progress(monkeypatch):
    source = _source()
    config = _config(source)

    def fake_scan_source(source, **kwargs):
        return [
            CandidateRecord(
                title="Source scan failed: Nature Climate Change",
                publication=PublicationInfo(
                    venue=source.name,
                    venue_type=source.source_type,
                ),
                discovered_via=[
                    SourceMention(
                        source=source.name,
                        url="https://example.org/feed",
                        source_type=source.source_type,
                        note="HTTP Error 500",
                    )
                ],
                source_status="source_error",
            )
        ]

    monkeypatch.setattr(source_monitor_module, "scan_source", fake_scan_source)
    events: list[ProgressEvent] = []

    result = SourceMonitorAgent(config).scan(
        "2026-04",
        progress_callback=events.append,
        run_id="run-456",
    )

    assert len(result.source_errors) == 1
    assert [event.event_type for event in events] == [
        "source_started",
        "source_error",
        "source_completed",
    ]
    assert events[1].detail == "HTTP Error 500"
    assert events[2].counts["source_errors"] == 1


def test_orchestrator_progress_does_not_change_routing(monkeypatch, tmp_path):
    source = _source()
    config = _config(source)

    def fake_scan_source(source, **kwargs):
        return [_candidate(source)]

    monkeypatch.setattr(source_monitor_module, "scan_source", fake_scan_source)
    events: list[ProgressEvent] = []

    with_progress = HotScienceOrchestrator(
        config=config,
        store=CandidateStore(tmp_path / "with_progress.sqlite3"),
    ).run(
        "2026-04",
        progress_callback=events.append,
    )
    without_progress = HotScienceOrchestrator(
        config=config,
        store=CandidateStore(tmp_path / "without_progress.sqlite3"),
    ).run("2026-04")

    assert _stable_summary(with_progress) == _stable_summary(without_progress)
    assert events[0].event_type == "run_started"
    assert events[-1].event_type == "run_completed"
    assert any(
        event.stage == "scanning_sources" and event.event_type == "stage_started"
        for event in events
    )
    assert any(event.event_type == "source_completed" for event in events)
    assert any(
        event.stage == "compiling_outputs" and event.event_type == "stage_completed"
        for event in events
    )
    assert events[-1].counts["evaluated"] == with_progress.summary["evaluated"]


def test_progress_callback_errors_do_not_fail_run(monkeypatch, tmp_path):
    source = _source()
    config = _config(source)

    def fake_scan_source(source, **kwargs):
        return [_candidate(source)]

    def failing_callback(event):
        raise RuntimeError("UI callback failed")

    monkeypatch.setattr(source_monitor_module, "scan_source", fake_scan_source)

    result = HotScienceOrchestrator(
        config=config,
        store=CandidateStore(tmp_path / "callback_error.sqlite3"),
    ).run(
        "2026-04",
        progress_callback=failing_callback,
    )

    assert result.summary["evaluated"] == 1


def _source() -> SourceConfig:
    return SourceConfig(
        id="nature_climate_change",
        name="Nature Climate Change",
        kind="rss",
        source_type="peer_reviewed_journal",
    )


def _config(source: SourceConfig) -> HotScienceConfig:
    return HotScienceConfig(
        intent=IntentConfig(description="climate science"),
        seed_terms=("climate",),
        search_queries=("climate change",),
        sources=(source,),
    )


def _candidate(source: SourceConfig) -> CandidateRecord:
    return CandidateRecord(
        title="Ocean warming accelerates Antarctic ice shelf retreat",
        doi="10.1234/progress.2026.001",
        authors=["Ada Ice", "Sam Ocean"],
        publication=PublicationInfo(
            venue=source.name,
            venue_type=source.source_type,
            online_publication_date="2026-04-12",
            url="https://doi.org/10.1234/progress.2026.001",
            open_access=True,
        ),
        abstract=(
            "This peer-reviewed study reports climate-change-driven ocean warming "
            "and Antarctic ice shelf retreat with implications for sea-level rise."
        ),
        abstract_source="publisher",
        discovered_via=[
            SourceMention(
                source=source.name,
                url="https://doi.org/10.1234/progress.2026.001",
                date_seen="2026-04-12",
                source_type=source.source_type,
            )
        ],
    )


def _stable_summary(result) -> dict:
    return {
        key: value
        for key, value in result.summary.items()
        if key not in {"run_id"}
    }
