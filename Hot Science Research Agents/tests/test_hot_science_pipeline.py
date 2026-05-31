"""Tests for UC-I-1 Hot Science pipeline components."""

import csv

import agents.hot_science.clients as clients_module
import agents.hot_science.resolver as resolver_module
from scripts.run_hot_science import resolve_criteria, resolve_retrieval_query
from agents.hot_science.access import AccessAgent
from agents.hot_science.compiler import CompilerAgent
from agents.hot_science.config import (
    HotScienceConfig,
    IntentConfig,
    SourceConfig,
    WatchlistConfig,
    load_hot_science_config,
)
from agents.hot_science.evaluator import SignificanceEvaluatorAgent
from agents.hot_science.orchestrator import HotScienceOrchestrator
from agents.hot_science.prior_editions import PriorEditionCheckerAgent
from agents.hot_science.resolver import PrimarySourceResolverAgent
from agents.hot_science.schema import CandidateRecord, PublicationInfo, SourceMention
from agents.hot_science.semantic import annotate_retrieval_signals, cosine_similarity
from agents.hot_science.source_monitor import build_retrieval_queries
from agents.hot_science.storage import CandidateStore
from agents.hot_science.verification import VerificationAgent, extract_doi


def make_candidate(
    *,
    title: str = "Unprecedented global heat and ocean warming signals",
    doi: str | None = "10.1234/example.2026.001",
    date: str | None = "2026-04-15",
    venue_type: str = "peer_reviewed_journal",
) -> CandidateRecord:
    return CandidateRecord(
        title=title,
        doi=doi,
        authors=["Ada Climate", "Sam Ocean"],
        publication=PublicationInfo(
            venue="Nature Climate Change",
            venue_type=venue_type,
            online_publication_date=date,
            url=f"https://doi.org/{doi}" if doi else "https://example.org/no-doi",
            open_access=True,
        ),
        abstract=(
            "A new global dataset shows unprecedented heat, ocean warming, "
            "and cascading ecosystem risk for millions of people."
        ),
        abstract_source="publisher",
        discovered_via=[
            SourceMention(
                source="Nature Climate Change",
                url=f"https://doi.org/{doi}" if doi else "https://example.org/no-doi",
                date_seen=date,
                source_type=venue_type,
            )
        ],
        target_month="2026-04",
    )


def test_hot_science_config_loads_sources():
    config = load_hot_science_config()
    assert "climate" in config.seed_terms
    assert "extreme heat climate" in config.search_queries
    assert any(source.id == "openalex" for source in config.sources)
    assert any(source.id == "nature" for source in config.sources)


def test_hot_science_config_loads_phase1_upgrade_knobs():
    config = load_hot_science_config()
    domain_ids = {domain.id for domain in config.domains}
    assert {"flooding", "human_health", "ocean_change"}.issubset(domain_ids)

    novelty = config.rubric.dimension("novelty")
    cascading = config.rubric.dimension("cascading_impact")
    audience = config.rubric.dimension("audience_relevance")
    assert config.rubric.version == "hot_science_v2_candidate"
    assert novelty.weight > cascading.weight
    assert cascading.bonus_only is True
    assert audience.selection_signal is False
    assert audience.weight == 0.0
    assert config.watchlist.non_target_month_enabled is False
    assert config.watchlist.preprint_bucket_enabled is True
    assert config.primary_work_type_priority[0] == "peer_reviewed_journal_article"

    nature_climate_change = next(
        source for source in config.sources if source.id == "nature_climate_change"
    )
    assert "1758-6798" in nature_climate_change.issns
    semantic_scholar = next(source for source in config.sources if source.id == "semantic_scholar")
    eartharxiv = next(source for source in config.sources if source.id == "eartharxiv")
    noaa = next(source for source in config.sources if source.id == "noaa_climate")
    nsidc = next(source for source in config.sources if source.id == "nsidc_news")
    agu = next(source for source in config.sources if source.id == "agu_earths_future")
    egu = next(source for source in config.sources if source.id == "egu_the_cryosphere")
    wmo = next(source for source in config.sources if source.id == "wmo")
    assert semantic_scholar.enabled is True
    assert "unauthenticated calls are rate-limited" in (semantic_scholar.notes or "")
    assert eartharxiv.kind == "oai_pmh"
    assert eartharxiv.url == "https://eartharxiv.org/api/oai/"
    assert noaa.url == "https://www.ncei.noaa.gov/news.xml"
    assert nsidc.enabled is True
    assert "2328-4277" in agu.issns
    assert "1994-0424" in egu.issns
    assert wmo.enabled is False


def test_search_query_variants_only_apply_to_searchable_sources():
    config = load_hot_science_config()
    openalex = SourceConfig(
        id="openalex",
        name="OpenAlex Works",
        kind="scholarly_api",
        source_type="peer_reviewed_journal",
    )
    semantic_scholar = SourceConfig(
        id="semantic_scholar",
        name="Semantic Scholar Academic Graph",
        kind="scholarly_api",
        source_type="peer_reviewed_journal",
    )
    rss = SourceConfig(
        id="science_daily_climate",
        name="ScienceDaily Climate News",
        kind="rss",
        source_type="popular_press",
    )
    assert len(build_retrieval_queries(config, openalex)) > 1
    assert build_retrieval_queries(config, semantic_scholar) == ("climate change",)
    assert build_retrieval_queries(config, rss) == ("climate change",)
    assert build_retrieval_queries(config, "rss") == ("climate change",)

    journal_rss_with_issn = SourceConfig(
        id="nature_climate_change",
        name="Nature Climate Change",
        kind="rss",
        source_type="peer_reviewed_journal",
        issns=("1758-678X", "1758-6798"),
    )
    assert len(build_retrieval_queries(config, journal_rss_with_issn)) > 1


def test_user_criteria_leads_search_queries():
    config = load_hot_science_config()
    openalex = SourceConfig(
        id="openalex",
        name="OpenAlex Works",
        kind="scholarly_api",
        source_type="peer_reviewed_journal",
    )
    queries = build_retrieval_queries(
        config,
        openalex,
        user_criteria="  extreme heat and human health impacts  ",
    )
    assert queries[0] == "extreme heat and human health impacts"
    assert "climate change" in queries


def test_run_hot_science_reads_long_criteria_file(tmp_path):
    criteria_file = tmp_path / "criteria.md"
    criteria_file.write_text(
        "# Cryosphere search brief\n\n"
        "Find April 2026 peer-reviewed papers about Antarctic ice shelves, "
        "ocean warming, permafrost, glaciers, and sea-level rise.\n\n"
        "Exclude historical geology and papers without current or future climate implications.\n"
    )

    resolved = resolve_criteria(None, str(criteria_file))

    assert "Antarctic ice shelves" in resolved
    assert "Exclude historical geology" in resolved


def test_run_hot_science_extracts_short_query_from_long_criteria_file(tmp_path):
    criteria_file = tmp_path / "criteria.md"
    criteria_file.write_text(
        "# Hot Science Agent Specification\n\n"
        "Search query: climate change global warming sea level ice sheets permafrost ocean warming\n\n"
        "Include only March 2026 papers with direct climate relevance.\n"
    )

    query = resolve_retrieval_query(None, str(criteria_file), None, None)

    assert query == "climate change global warming sea level ice sheets permafrost ocean warming"


def test_run_hot_science_uses_broad_queries_when_long_file_has_no_short_query(tmp_path):
    criteria_file = tmp_path / "criteria.md"
    criteria_file.write_text(
        "# Hot Science Agent Specification\n\n"
        "A page-long brief with inclusion and exclusion rules should not be sent "
        "directly to scholarly API search endpoints.\n"
    )

    query = resolve_retrieval_query(None, str(criteria_file), None, None)

    assert query == ""


def test_retrieval_query_overrides_long_user_criteria_for_api_queries():
    config = load_hot_science_config()
    openalex = SourceConfig(
        id="openalex",
        name="OpenAlex Works",
        kind="scholarly_api",
        source_type="peer_reviewed_journal",
    )
    long_criteria = "# Hot Science Agent Specification\n\n" + "Detailed instructions. " * 30

    queries = build_retrieval_queries(
        config,
        openalex,
        user_criteria=long_criteria,
        retrieval_query="climate change global warming sea level",
    )

    assert queries[0] == "climate change global warming sea level"
    assert not queries[0].startswith("# Hot Science")


def test_run_hot_science_rejects_inline_and_file_criteria(tmp_path):
    criteria_file = tmp_path / "criteria.md"
    criteria_file.write_text("cryosphere")

    try:
        resolve_criteria("cryosphere", str(criteria_file))
    except SystemExit as exc:
        assert "either --criteria or --criteria-file" in str(exc)
    else:
        raise AssertionError("Expected mixed criteria inputs to fail")


def test_journal_issn_backfill_uses_scholarly_api_filters(monkeypatch):
    captured_urls: list[str] = []

    def fake_fetch_json(url, headers=None, timeout=30):
        captured_urls.append(url)
        if "openalex" in url:
            return {
                "results": [
                    {
                        "id": "https://openalex.org/W1",
                        "doi": "https://doi.org/10.1234/issn-openalex",
                        "title": "Ocean warming increases Antarctic ice shelf exposure",
                        "publication_date": "2026-04-15",
                        "type": "article",
                        "primary_location": {
                            "landing_page_url": "https://doi.org/10.1234/issn-openalex",
                            "source": {"display_name": "Nature Climate Change"},
                        },
                        "open_access": {"is_oa": True},
                        "authorships": [{"author": {"display_name": "Ada Ice"}}],
                    }
                ]
            }
        return {"message": {"items": []}}

    def fake_scan_rss(source, window_start, window_end, max_results):
        return []

    monkeypatch.setattr(clients_module, "fetch_json", fake_fetch_json)
    monkeypatch.setattr(clients_module, "scan_rss", fake_scan_rss)
    source = SourceConfig(
        id="nature_climate_change",
        name="Nature Climate Change",
        kind="rss",
        source_type="peer_reviewed_journal",
        url="https://example.org/rss",
        issns=("1758-678X", "1758-6798"),
    )

    records = clients_module.scan_source(
        source,
        query="ocean warming",
        seed_terms=("climate",),
        window_start=clients_module.date(2026, 4, 1),
        window_end=clients_module.date(2026, 4, 30),
        max_results=10,
    )

    assert len(records) == 1
    assert records[0].doi == "https://doi.org/10.1234/issn-openalex"
    assert any("locations.source.issn" in url for url in captured_urls)
    assert any("issn%3A1758-678X" in url or "issn:1758-678X" in url for url in captured_urls)


def test_oai_pmh_source_parses_and_filters_records(monkeypatch):
    payload = """<?xml version="1.0" encoding="UTF-8"?>
    <OAI-PMH xmlns="http://www.openarchives.org/OAI/2.0/"
      xmlns:oai_dc="http://www.openarchives.org/OAI/2.0/oai_dc/"
      xmlns:dc="http://purl.org/dc/elements/1.1/">
      <ListRecords>
        <record>
          <header>
            <identifier>oai:EA:id:1</identifier>
            <datestamp>2026-04-10T12:00:00Z</datestamp>
          </header>
          <metadata>
            <oai_dc:dc>
              <dc:title>Rapid Antarctic ice shelf thinning linked to ocean warming</dc:title>
              <dc:creator>Ada Ice</dc:creator>
              <dc:creator>Sam Ocean</dc:creator>
              <dc:description>Ocean warming increases Antarctic ice shelf melt risk.</dc:description>
              <dc:date>2026-04-10T12:00:00Z</dc:date>
              <dc:identifier>10.31223/example</dc:identifier>
              <dc:identifier>https://eartharxiv.org/repository/object/1/download/2/</dc:identifier>
            </oai_dc:dc>
          </metadata>
        </record>
        <record>
          <header>
            <identifier>oai:EA:id:2</identifier>
            <datestamp>2026-03-10T12:00:00Z</datestamp>
          </header>
          <metadata>
            <oai_dc:dc>
              <dc:title>March-only preprint</dc:title>
              <dc:date>2026-03-10T12:00:00Z</dc:date>
            </oai_dc:dc>
          </metadata>
        </record>
      </ListRecords>
    </OAI-PMH>
    """

    captured_urls: list[str] = []

    def fake_fetch_text(url, headers=None, timeout=30):
        captured_urls.append(url)
        return payload

    monkeypatch.setattr(clients_module, "fetch_text", fake_fetch_text)
    source = SourceConfig(
        id="eartharxiv",
        name="EarthArXiv",
        kind="oai_pmh",
        source_type="preprint",
        url="https://eartharxiv.org/api/oai/",
    )

    records = clients_module.scan_source(
        source,
        query="ocean warming",
        seed_terms=("climate",),
        window_start=clients_module.date(2026, 4, 1),
        window_end=clients_module.date(2026, 4, 30),
        max_results=10,
    )

    assert len(records) == 1
    assert "metadataPrefix=oai_dc" in captured_urls[0]
    assert records[0].title == "Rapid Antarctic ice shelf thinning linked to ocean warming"
    assert records[0].doi == "10.31223/example"
    assert records[0].authors == ["Ada Ice", "Sam Ocean"]
    assert records[0].publication.online_publication_date == "2026-04-10"
    assert records[0].publication.source_record_type == "oai_pmh_record"
    assert records[0].abstract_source == "oai_pmh"


def test_fetch_text_falls_back_to_requests_after_urllib_reset(monkeypatch):
    class FakeResponse:
        content = b"<rss>ok</rss>"

        def raise_for_status(self):
            return None

    def fake_urlopen(*args, **kwargs):
        raise ConnectionResetError("reset")

    def fake_get(url, headers=None, timeout=30):
        assert url == "https://example.org/feed"
        assert headers["User-Agent"].startswith("DeepGreen/")
        return FakeResponse()

    monkeypatch.setattr(clients_module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(clients_module.requests, "get", fake_get)
    monkeypatch.setattr(clients_module.time, "sleep", lambda delay: None)

    assert clients_module.fetch_text("https://example.org/feed") == "<rss>ok</rss>"


def test_fetch_text_falls_back_to_curl_after_requests_reset(monkeypatch):
    class FakeCompleted:
        stdout = b"<rss>curl ok</rss>"

    def fake_urlopen(*args, **kwargs):
        raise ConnectionResetError("reset")

    def fake_get(url, headers=None, timeout=30):
        raise clients_module.requests.exceptions.ConnectionError("reset")

    def fake_run(args, capture_output=False, check=False):
        assert args[0] == "/usr/bin/curl"
        assert "-fsSL" in args
        assert args[-1] == "https://example.org/feed"
        assert capture_output is True
        assert check is True
        return FakeCompleted()

    monkeypatch.setattr(clients_module.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(clients_module.requests, "get", fake_get)
    monkeypatch.setattr(clients_module.shutil, "which", lambda name: "/usr/bin/curl")
    monkeypatch.setattr(clients_module.subprocess, "run", fake_run)
    monkeypatch.setattr(clients_module.time, "sleep", lambda delay: None)

    assert clients_module.fetch_text("https://example.org/feed") == "<rss>curl ok</rss>"


def test_orchestrator_wires_watchlist_config_to_verifier(tmp_path):
    config = HotScienceConfig(
        intent=IntentConfig(description="climate science"),
        seed_terms=("climate",),
        search_queries=("climate change",),
        sources=(),
        watchlist=WatchlistConfig(non_target_month_enabled=True),
    )

    orchestrator = HotScienceOrchestrator(
        config=config,
        store=CandidateStore(tmp_path / "candidates.sqlite3"),
    )

    assert orchestrator.verifier.non_target_month_watchlist is True


def test_extract_doi_from_url():
    assert extract_doi("https://doi.org/10.1038/s41586-026-00001-1") == (
        "10.1038/s41586-026-00001-1"
    )


def test_verification_enforces_target_month():
    verifier = VerificationAgent()
    in_month = make_candidate(date="2026-04-15")
    out_month = make_candidate(
        title="Historic climate paper from the wrong month",
        doi="10.1234/example.2026.002",
        date="2026-03-31",
    )
    result = verifier.verify([in_month, out_month], "2026-04")
    assert len(result.verified) == 1
    assert result.verified[0].title == in_month.title
    assert any(flag.code == "outside_target_month" for flag in result.excluded[0].exclusion_flags)


def test_verification_excludes_research_artifact_before_date():
    verifier = VerificationAgent()
    artifact = make_candidate(
        title="Ocean Warming Weaken Sea Land Breeze in Coastal Megacities (Code for simulation)",
        doi="10.5281/zenodo.18932849",
        date="2026-03-10",
    )
    artifact.publication.venue = "Zenodo"
    artifact.publication.source_record_type = "dataset"

    result = verifier.verify([artifact], "2026-04")

    assert len(result.verified) == 0
    assert any(
        flag.code == "non_primary_research_object"
        for flag in result.excluded[0].exclusion_flags
    )
    assert not any(
        flag.code == "outside_target_month"
        for flag in result.excluded[0].exclusion_flags
    )


def test_verification_records_date_provenance():
    verifier = VerificationAgent()
    candidate = make_candidate(date="2026-04-15")
    candidate.publication.date_source_field = "published-online"
    candidate.publication.raw_publication_date = '{"date-parts": [[2026, 4, 15]]}'

    result = verifier.verify([candidate], "2026-04")

    assert result.verified[0].verification.date_verification_source == "published-online"
    assert any(
        event.action == "date_verified" and "published-online" in (event.detail or "")
        for event in result.verified[0].audit_trail
    )


def test_verification_routes_noncanonical_date_fields_to_manual_review():
    verifier = VerificationAgent()
    candidate = make_candidate(date="2026-04-15")
    candidate.publication.date_source_field = "received"
    candidate.publication.raw_publication_date = '{"date-parts": [[2026, 4, 15]]}'

    result = verifier.verify([candidate], "2026-04")

    assert len(result.verified) == 0
    assert len(result.manual_review) == 1
    assert result.manual_review[0].routing_reason == "date_not_verified"
    assert result.manual_review[0].date_eligibility.reason == "non_canonical_date_field"


def test_verification_excludes_journal_level_records():
    verifier = VerificationAgent()
    candidate = make_candidate(
        title="The International Journal of Climate Change: Impacts and Responses",
        doi=None,
        date="2026-04-15",
    )
    candidate.publication.source_record_type = "journal"

    result = verifier.verify([candidate], "2026-04")

    assert len(result.verified) == 0
    assert len(result.excluded) == 1
    assert result.excluded[0].routing_reason == "journal_level_record"
    assert any(flag.code == "journal_level_record" for flag in result.excluded[0].exclusion_flags)


def test_verification_can_route_wrong_month_to_watchlist():
    verifier = VerificationAgent(non_target_month_watchlist=True)
    candidate = make_candidate(date="2026-02-15")

    result = verifier.verify([candidate], "2026-04")

    assert len(result.verified) == 0
    assert len(result.excluded) == 0
    assert len(result.manual_review) == 1
    assert result.manual_review[0].watchlist_reason == "relevant_outside_target_month"
    assert result.manual_review[0].date_eligibility.eligible is False


def test_candidate_schema_phase1_fields_round_trip():
    candidate = make_candidate()
    candidate.publication.primary_work_type = "peer_reviewed_journal_article"
    candidate.fit_assessment.passed = True
    candidate.fit_assessment.relevance_claim = "This paper reports ocean warming impacts."
    candidate.fit_assessment.evidence_source = "abstract"
    candidate.fit_assessment.evidence_snippet = "ocean warming"
    candidate.fit_assessment.supported_domain_tags = ["ocean_change"]
    candidate.date_eligibility.eligible = True
    candidate.date_eligibility.target_month = "2026-04"
    candidate.date_eligibility.checked_date = "2026-04-15"
    candidate.date_eligibility.date_kind = "online_publication_date"
    candidate.routing_reason = "verified_primary_work_and_in_target_month"
    candidate.watchlist_reason = None
    candidate.rubric_version = "hot_science_v2_candidate"
    candidate.significance.rubric_version = "hot_science_v2_candidate"
    candidate.significance.novelty.evidence = "A new global dataset"
    candidate.significance.novelty.subtype = "new_finding_in_established_area"
    candidate.significance.novelty.weight = 1.3

    loaded = CandidateRecord.from_dict(candidate.to_dict())

    assert loaded.publication.primary_work_type == "peer_reviewed_journal_article"
    assert loaded.fit_assessment.passed is True
    assert loaded.fit_assessment.supported_domain_tags == ["ocean_change"]
    assert loaded.date_eligibility.eligible is True
    assert loaded.routing_reason == "verified_primary_work_and_in_target_month"
    assert loaded.rubric_version == "hot_science_v2_candidate"
    assert loaded.significance.novelty.subtype == "new_finding_in_established_area"
    assert loaded.significance.novelty.weight == 1.3


def test_candidate_from_dict_accepts_legacy_and_extra_fields():
    payload = make_candidate().to_dict()
    payload["unexpected_future_field"] = "ignored"
    payload["publication"]["unexpected_future_field"] = "ignored"
    payload["significance"]["novelty"]["unexpected_future_field"] = "ignored"
    payload.pop("fit_assessment", None)
    payload.pop("date_eligibility", None)
    payload.pop("routing_reason", None)
    payload.pop("watchlist_reason", None)
    payload.pop("rubric_version", None)

    loaded = CandidateRecord.from_dict(payload)

    assert loaded.title == payload["title"]
    assert loaded.fit_assessment.passed is None
    assert loaded.date_eligibility.eligible is None
    assert loaded.routing_reason is None


def test_verification_deduplicates_by_doi():
    verifier = VerificationAgent()
    first = make_candidate()
    duplicate = make_candidate(title="Duplicate copy of the same paper")
    result = verifier.verify([first, duplicate], "2026-04")
    assert len(result.verified) == 1
    assert len(result.excluded) == 1
    assert result.verified[0].verification.consolidated_from == [duplicate.candidate_id]


def test_primary_source_resolver_preserves_press_and_extracts_doi():
    candidate = CandidateRecord(
        title="Climate discovery gets press attention",
        publication=PublicationInfo(
            venue="ScienceDaily",
            venue_type="popular_press",
            online_publication_date="2026-04-03",
            url="https://example.org/press",
        ),
        abstract="Journal Reference: Nature Climate Change. DOI: 10.1038/s41558-026-00001-2",
        discovered_via=[
            SourceMention(
                source="ScienceDaily",
                url="https://example.org/press",
                date_seen="2026-04-03",
                source_type="popular_press",
            )
        ],
    )
    result = PrimarySourceResolverAgent().resolve([candidate])
    resolved = result.candidates[0]
    assert not result.unresolved_press
    assert resolved.doi == "10.1038/s41558-026-00001-2"
    assert resolved.publication.venue_type == "peer_reviewed_journal"
    assert resolved.publication.primary_source_url == "https://doi.org/10.1038/s41558-026-00001-2"
    assert resolved.press_coverage[0].outlet == "ScienceDaily"


def test_unresolved_press_routes_to_manual_review():
    candidate = CandidateRecord(
        title="Press item without journal metadata",
        publication=PublicationInfo(
            venue="ScienceDaily",
            venue_type="popular_press",
            online_publication_date="2026-04-03",
            url="https://example.org/press",
        ),
        discovered_via=[
            SourceMention(
                source="ScienceDaily",
                url="https://example.org/press",
                date_seen="2026-04-03",
                source_type="popular_press",
            )
        ],
    )
    resolved = PrimarySourceResolverAgent().resolve([candidate]).candidates
    result = VerificationAgent().verify(resolved, "2026-04")
    assert len(result.manual_review) == 1
    assert result.manual_review[0].source_status == "manual_review"


def test_primary_source_resolver_can_fetch_press_page_for_doi(monkeypatch):
    def fake_fetch_text(url, timeout=30, headers=None):
        return "<html><body>Journal Reference DOI: 10.1038/s41558-026-02618-9</body></html>"

    monkeypatch.setattr(resolver_module, "fetch_text", fake_fetch_text)
    candidate = CandidateRecord(
        title="Press item with DOI on the article page",
        publication=PublicationInfo(
            venue="ScienceDaily",
            venue_type="popular_press",
            online_publication_date="2026-04-03",
            url="https://example.org/press",
        ),
        discovered_via=[
            SourceMention(
                source="ScienceDaily",
                url="https://example.org/press",
                date_seen="2026-04-03",
                source_type="popular_press",
            )
        ],
    )

    resolved = PrimarySourceResolverAgent(fetch_press_pages=True).resolve([candidate]).candidates[0]

    assert resolved.doi == "10.1038/s41558-026-02618-9"
    assert resolved.publication.primary_source_url == "https://doi.org/10.1038/s41558-026-02618-9"
    assert any(event.action == "press_page_fetched" for event in resolved.audit_trail)


def test_access_agent_preserves_paywalled_abstract_candidates():
    candidate = make_candidate()
    candidate.publication.open_access = False
    result = AccessAgent().annotate([candidate])
    annotated = result.candidates[0]
    assert annotated.publication.paywall is True
    assert annotated.publication.abstract_accessible is True
    assert "paywalled" in (annotated.publication.access_note or "")


def test_evaluator_scores_and_tags_candidate():
    evaluator = SignificanceEvaluatorAgent()
    candidate = make_candidate()
    result = evaluator.evaluate([candidate])
    assert len(result.evaluated) == 1
    scored = result.evaluated[0]
    assert scored.significance.composite_score is not None
    assert scored.significance.composite_score > 0
    assert "extreme_heat" in scored.topic_tags


def test_evaluator_applies_weighted_rubric_without_audience_selection():
    evaluator = SignificanceEvaluatorAgent()
    candidate = evaluator.evaluate([make_candidate()]).evaluated[0]
    sig = candidate.significance

    expected = round(
        (sig.novelty.score or 0) * (sig.novelty.weight or 0)
        + (sig.impact_magnitude.score or 0) * (sig.impact_magnitude.weight or 0)
        + (sig.earth_system_signal.score or 0) * (sig.earth_system_signal.weight or 0)
        + (sig.cross_disciplinary.score or 0) * (sig.cross_disciplinary.weight or 0)
        + (sig.cascading_impact.score or 0) * (sig.cascading_impact.weight or 0),
        2,
    )

    assert candidate.rubric_version == "hot_science_v2_candidate"
    assert sig.rubric_version == "hot_science_v2_candidate"
    assert sig.audience_relevance.score > 0
    assert sig.audience_relevance.weight == 0.0
    assert sig.composite_score == expected


def test_evaluator_additive_secondary_signals_have_no_baseline_penalty():
    evaluator = SignificanceEvaluatorAgent()
    candidate = make_candidate(
        title="Ocean warming increases Antarctic ice shelf melt",
    )
    candidate.abstract = (
        "Ocean warming increases Antarctic ice shelf exposure and future "
        "sea-level implications."
    )

    scored = evaluator.evaluate([candidate]).evaluated[0]
    sig = scored.significance
    primary_only = round(
        (sig.novelty.score or 0) * (sig.novelty.weight or 0)
        + (sig.impact_magnitude.score or 0) * (sig.impact_magnitude.weight or 0)
        + (sig.earth_system_signal.score or 0) * (sig.earth_system_signal.weight or 0),
        2,
    )

    assert sig.cross_disciplinary.score == 0
    assert sig.cascading_impact.score == 0
    assert sig.composite_score == primary_only


def test_evaluator_records_novelty_subtype_and_impact_evidence():
    evaluator = SignificanceEvaluatorAgent()
    candidate = make_candidate(
        title="First observation of ocean warming beneath Antarctic ice shelves",
    )
    candidate.abstract = (
        "For the first time, researchers report ocean warming beneath Antarctic "
        "ice shelves that increases exposure for millions of people through "
        "future sea-level risk."
    )

    scored = evaluator.evaluate([candidate]).evaluated[0]

    assert scored.significance.novelty.subtype == "first_observation"
    assert "first time" in (scored.significance.novelty.evidence or "").casefold()
    assert "millions of people" in (
        scored.significance.impact_magnitude.evidence or ""
    ).casefold()
    assert scored.significance.impact_magnitude.subtype == "regional_or_system_scale"


def test_evaluator_enforces_run_focus_when_provided():
    evaluator = SignificanceEvaluatorAgent()
    candidate = make_candidate()
    result = evaluator.evaluate([candidate], user_criteria="cryosphere and sea-level rise")

    assert not result.evaluated
    assert result.excluded
    assert "run_focus_mismatch" in {flag.code for flag in result.excluded[0].exclusion_flags}
    assert result.excluded[0].fit_assessment.run_focus_aligned is False


def test_evaluator_excludes_focus_run_candidate_without_focus_domain_tags():
    evaluator = SignificanceEvaluatorAgent()
    candidate = make_candidate(
        title="A carbon monoxide cycle drives carbon monoxide uptake and poisoning",
        date="2026-04-15",
    )
    candidate.abstract = (
        "An understanding of the physiology of acute carbon monoxide poisoning "
        "remains incomplete. This study describes a novel approach considering "
        "a carbon monoxide cycle driven by carbon monoxide inhalation."
    )

    result = evaluator.evaluate(
        [candidate],
        user_criteria="cryosphere and sea-level rise research",
    )

    assert not result.evaluated
    assert "run_focus_mismatch" in {flag.code for flag in result.excluded[0].exclusion_flags}


def test_evaluator_does_not_match_short_domain_terms_inside_unrelated_words():
    evaluator = SignificanceEvaluatorAgent()
    candidate = make_candidate(
        title="Filament sensing tension for wearable robotics",
        date="2026-04-15",
    )
    candidate.abstract = (
        "Artificial muscles have been in development for decades and play a "
        "crucial role in the field of wearable robotics. A universal device "
        "for sensing and regulating forces is still absent."
    )

    result = evaluator.evaluate(
        [candidate],
        user_criteria="cryosphere and sea-level rise research",
    )

    assert not result.evaluated
    excluded = result.excluded[0]
    assert "cryosphere" not in excluded.topic_tags
    assert "run_focus_mismatch" in {flag.code for flag in excluded.exclusion_flags}


def test_retrieval_signal_annotation():
    config = load_hot_science_config()
    candidate = make_candidate()
    annotate_retrieval_signals(candidate, config)
    assert "warming" in candidate.seed_term_matches
    assert "retrieval_score" in candidate.missing_reasons


def test_cosine_similarity():
    assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0
    assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0


def test_evaluator_routes_preprints_to_separate_bucket():
    evaluator = SignificanceEvaluatorAgent()
    candidate = make_candidate(venue_type="preprint")
    result = evaluator.evaluate([candidate])
    assert len(result.evaluated) == 0
    assert len(result.excluded) == 0
    assert len(result.preprints) == 1
    assert result.preprints[0].routing_reason == "preprint_separate_bucket"
    assert result.preprints[0].source_status == "preprint"


def test_compiler_clusters_and_store_round_trip(tmp_path):
    evaluator = SignificanceEvaluatorAgent()
    candidate = evaluator.evaluate([make_candidate()]).evaluated[0]
    compiled = CompilerAgent().compile(
        target_month="2026-04",
        candidates=[candidate],
        excluded=[],
    )
    assert compiled.clusters

    store = CandidateStore(tmp_path / "candidates.sqlite3")
    store.upsert_candidate(candidate)
    loaded = store.list_candidates("2026-04")
    assert len(loaded) == 1
    assert loaded[0].candidate_id == candidate.candidate_id


def test_prior_edition_checker_flags_existing_candidate(tmp_path):
    store = CandidateStore(tmp_path / "candidates.sqlite3")
    previous = make_candidate(date="2026-03-15")
    previous.target_month = "2026-03"
    store.upsert_candidate(previous)

    current = make_candidate(date="2026-04-15")
    current.target_month = "2026-04"
    result = PriorEditionCheckerAgent(store).check([current])
    assert result.candidates[0].prior_editions[0].target_month == "2026-03"
    assert result.candidates[0].prior_editions[0].confidence == "high"


def test_compiler_writes_review_csv(tmp_path):
    candidate = SignificanceEvaluatorAgent().evaluate([make_candidate()]).evaluated[0]
    compiled = CompilerAgent().compile(
        target_month="2026-04",
        candidates=[candidate],
        excluded=[],
        manual_review=[],
        user_criteria="extreme heat",
    )
    output = tmp_path / "review.csv"
    CompilerAgent().write_review_csv(compiled, output)
    rows = list(csv.DictReader(output.open()))
    assert rows[0]["bucket"] == "candidate"
    assert rows[0]["user_criteria"] == "extreme heat"
    assert rows[0]["primary_url"] == "https://doi.org/10.1234/example.2026.001"
    assert rows[0]["fit_relevance_claim"]
    assert rows[0]["routing_reason"] == "evidence_fit_in_target_month"


def test_compiler_outputs_phase6_review_workflow(tmp_path):
    source = SourceConfig(
        id="nature_climate_change",
        name="Nature Climate Change",
        kind="rss",
        source_type="peer_reviewed_journal",
    )
    evaluator = SignificanceEvaluatorAgent()
    candidate = evaluator.evaluate([make_candidate()]).evaluated[0]
    preprint = evaluator.evaluate([make_candidate(venue_type="preprint")]).preprints[0]
    watchlist = make_candidate(
        title="Relevant wrong-month ocean warming item",
        date="2026-02-15",
    )
    watchlist.routing_reason = "non_target_month_watchlist"
    watchlist.watchlist_reason = "relevant_outside_target_month"
    manual_review = make_candidate(
        title="Title-only plausible climate item",
        doi="10.1234/manual",
    )
    manual_review.abstract = None
    manual_review.routing_reason = "title_only_abstract_missing"
    manual_review.fit_assessment.manual_review_reason = "Needs abstract before scoring."
    excluded = make_candidate(title="Off-scope geology item", doi="10.1234/excluded")
    excluded.add_exclusion("no_evidence_of_hot_science_fit", "No climate mechanism.")
    source_error = CandidateRecord(
        title="Source scan failed: Nature Climate Change",
        publication=PublicationInfo(venue="Nature Climate Change", venue_type="peer_reviewed_journal"),
        discovered_via=[
            SourceMention(
                source="Nature Climate Change",
                url="https://example.org/feed",
                source_type="peer_reviewed_journal",
                note="HTTP Error 500",
            )
        ],
        source_status="source_error",
    )

    compiled = CompilerAgent().compile(
        target_month="2026-04",
        candidates=[candidate],
        excluded=[excluded],
        manual_review=[watchlist, manual_review],
        preprints=[preprint],
        user_criteria="cryosphere",
        sources=(source,),
        source_errors=[source_error],
        rubric_version="hot_science_v2_candidate",
    )

    assert len(compiled.candidates) == 1
    assert len(compiled.preprints) == 1
    assert len(compiled.watchlist) == 1
    assert len(compiled.manual_review) == 1
    assert compiled.source_diagnostics["nature_climate_change"]["preprints"] == 1
    assert compiled.source_diagnostics["nature_climate_change"]["watchlist"] == 1

    payload = compiled.to_json_dict()
    assert payload["run_config"]["rubric_version"] == "hot_science_v2_candidate"
    assert payload["run_config"]["target_month_window"] == "2026-04-01 through 2026-04-30"
    assert payload["run_config"]["source_scan_window"] == "2026-02-15 through 2026-04-30"
    assert payload["retrieval_method"]["query_strategy"]
    assert payload["source_inventory"][0]["id"] == "nature_climate_change"
    assert payload["counts"]["total_paper_records_categorized"] == 5
    assert payload["counts"]["preprints"] == 1
    assert payload["counts"]["watchlist"] == 1
    assert payload["zero_count_explanations"] == [
        "Honorable mention candidates: No paper met the special high-audience-signal/lower-selection-score rule."
    ]

    markdown_path = tmp_path / "review.md"
    CompilerAgent().write_markdown(compiled, markdown_path)
    markdown = markdown_path.read_text()
    assert markdown.index("## Run Configuration") < markdown.index("## Top Candidates")
    assert "- Total paper records categorized: 5" in markdown
    assert (
        "- Category breakdown: top candidates 1; manual review 1; excluded 1; "
        "preprints 1; watchlist 1; honorable mentions 0; source errors 1"
    ) in markdown
    assert "**Why any categories are zero**" in markdown
    assert "Honorable mention candidates: No paper met the special high-audience-signal/lower-selection-score rule." in markdown
    assert "## Search Criteria and Methodology" in markdown
    assert "## Data Sources Searched or Configured" in markdown
    assert "**Enabled sources scanned**" in markdown
    assert "Nature Climate Change" in markdown
    assert "**Fit and verification evidence**" in markdown
    assert '### <span style="font-size: 1.08em;">' in markdown
    assert markdown.index("## Top Candidates") < markdown.index("## Preprints")
    assert markdown.index("## Preprints") < markdown.index("## Non-Target-Month Watchlist")
    assert markdown.index("## Non-Target-Month Watchlist") < markdown.index("## Manual Review Queue")
    assert markdown.index("## Manual Review Queue") < markdown.index("## Excluded Candidates Appendix")
    assert "## Source Diagnostics" in markdown
    assert "Why this is here" in markdown

    csv_path = tmp_path / "review.csv"
    CompilerAgent().write_review_csv(compiled, csv_path)
    rows = list(csv.DictReader(csv_path.open()))
    assert [row["bucket"] for row in rows] == [
        "candidate",
        "preprint",
        "watchlist",
        "manual_review",
        "excluded",
    ]
    assert rows[1]["routing_reason"] == "preprint_separate_bucket"
    assert rows[2]["watchlist_reason"] == "relevant_outside_target_month"


def test_compiler_writes_source_breakdown_csv(tmp_path):
    source = SourceConfig(
        id="nature_climate_change",
        name="Nature Climate Change",
        kind="rss",
        source_type="peer_reviewed_journal",
    )
    candidate = SignificanceEvaluatorAgent().evaluate([make_candidate()]).evaluated[0]
    manual_review = make_candidate(
        title="Press item without primary source",
        doi=None,
        venue_type="popular_press",
    )
    manual_review.discovered_via[0].source = "Nature Climate Change"
    excluded = make_candidate(title="Wrong month", doi="10.1234/wrong", date="2026-03-01")
    excluded.discovered_via[0].source = "Nature Climate Change"
    source_error = CandidateRecord(
        title="Source scan failed: Nature Climate Change",
        publication=PublicationInfo(venue="Nature Climate Change", venue_type="peer_reviewed_journal"),
        discovered_via=[
            SourceMention(
                source="Nature Climate Change",
                url="https://example.org/feed",
                source_type="peer_reviewed_journal",
                note="HTTP Error 404",
            )
        ],
        source_status="source_error",
    )
    compiled = CompilerAgent().compile(
        target_month="2026-04",
        candidates=[candidate],
        excluded=[excluded],
        manual_review=[manual_review],
        user_criteria="cryosphere",
    )
    output = tmp_path / "source_breakdown.csv"
    CompilerAgent().write_source_breakdown_csv(
        compiled,
        output,
        sources=(source,),
        source_errors=[source_error],
    )

    rows = list(csv.DictReader(output.open()))
    assert rows[0]["source_id"] == "nature_climate_change"
    assert rows[0]["verified"] == "1"
    assert rows[0]["manual_review"] == "1"
    assert rows[0]["excluded"] == "1"
    assert rows[0]["source_errors"] == "1"
    assert rows[0]["total"] == "3"


def test_compiler_summarizes_long_criteria_without_breaking_markdown_headings(tmp_path):
    long_criteria = (
        "Search query: climate change global warming sea level rise\n\n"
        "# Hot Science Agent Criteria\n\n"
        "## Include\n\n"
        "Include climate impacts first published in April 2026.\n"
    )
    candidate = SignificanceEvaluatorAgent().evaluate([make_candidate()]).evaluated[0]
    compiled = CompilerAgent().compile(
        target_month="2026-04",
        candidates=[candidate],
        excluded=[],
        user_criteria=long_criteria,
    )

    output = tmp_path / "report.md"
    CompilerAgent().write_markdown(compiled, output)
    markdown = output.read_text()

    assert "- Search focus: Search query: climate change global warming sea level rise" in markdown
    assert "## Data Sources Searched or Configured" not in markdown or markdown.index(
        "## Top Candidates"
    ) < markdown.index("## Full Criteria Brief")
    assert "> # Hot Science Agent Criteria" in markdown
    assert "\n# Hot Science Agent Criteria" not in markdown
