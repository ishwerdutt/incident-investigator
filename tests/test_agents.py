"""Tests for agents and orchestrator using MockLLMProvider."""

import json
from datetime import datetime

import pytest

from incident_investigator.agents.critic import CriticAgent
from incident_investigator.agents.generator import HypothesisGeneratorAgent
from incident_investigator.agents.reporter import ReporterAgent
from incident_investigator.agents.tester import HypothesisTesterAgent
from incident_investigator.agents.triage import TriageAgent
from incident_investigator.ledger.evidence_ledger import EvidenceLedger
from incident_investigator.llm.provider import MockLLMProvider
from incident_investigator.models import (
    BucketCount,
    EvidenceItem,
    Hypothesis,
    HypothesisStatus,
    IncidentBrief,
    InvestigationConfig,
    LogEvent,
    LogLevel,
    TemplateCluster,
)
from incident_investigator.orchestrator import InvestigationOrchestrator
from incident_investigator.store.duckdb_store import LogStore


@pytest.mark.asyncio
async def test_triage_agent_produces_incident_brief():
    triage_response = json.dumps(
        {
            "incident_window_start": "2024-01-15T10:25:00",
            "incident_window_end": "2024-01-15T10:35:00",
            "affected_services": ["db-proxy", "checkout-service"],
            "primary_symptoms": ["Connection pool exhausted", "504 Gateway Timeout"],
            "anomalous_templates": [],
            "user_hint": "DB seemed slow",
        }
    )

    mock_llm = MockLLMProvider(responses=[triage_response])
    agent = TriageAgent(name="triage", llm=mock_llm)

    brief = await agent.analyze(
        template_summary="Template 1: Connection pool exhausted",
        anomaly_summary="Spike at 10:28",
        user_hint="DB seemed slow",
    )

    assert isinstance(brief, IncidentBrief)
    assert brief.affected_services == ["db-proxy", "checkout-service"]
    assert len(brief.primary_symptoms) == 2
    assert brief.incident_window_start == datetime(2024, 1, 15, 10, 25, 0)
    assert agent.token_usage["prompt"] > 0


@pytest.mark.asyncio
async def test_hypothesis_generator_agent_produces_hypotheses():
    gen_response = json.dumps(
        [
            {
                "statement": "Database connection pool exhausted",
                "predicted_evidence": ["Error logs in db-proxy", "Checkout timeouts"],
                "falsification_conditions": ["DB pool has free connections"],
            },
            {
                "statement": "Network partition between api-gateway and checkout",
                "predicted_evidence": ["DNS errors", "TCP reset"],
                "falsification_conditions": ["Successful TCP handshakes during window"],
            },
        ]
    )

    mock_llm = MockLLMProvider(responses=[gen_response])
    ledger = EvidenceLedger()
    agent = HypothesisGeneratorAgent(name="generator", llm=mock_llm)

    brief = IncidentBrief(
        incident_window_start=datetime(2024, 1, 15, 10, 25, 0),
        incident_window_end=datetime(2024, 1, 15, 10, 35, 0),
        affected_services=["db-proxy", "checkout-service"],
        primary_symptoms=["Connection timeouts"],
    )

    hypotheses = await agent.generate(brief, ledger)

    assert len(hypotheses) == 2
    assert hypotheses[0].statement == "Database connection pool exhausted"
    assert hypotheses[0].status == HypothesisStatus.OPEN
    assert len(ledger.get_all_hypotheses()) == 2


@pytest.mark.asyncio
async def test_hypothesis_tester_agent():
    # LLM concludes with supporting evidence and event IDs
    verdict_response = json.dumps(
        {
            "supports": True,
            "summary": "Found 5 pool exhaustion errors in db-proxy",
            "event_ids": ["evt_123", "evt_124"],
            "confidence": 0.85,
        }
    )

    mock_llm = MockLLMProvider(responses=[verdict_response])
    tool_executor_called = []

    def mock_executor(name, **kwargs):
        tool_executor_called.append((name, kwargs))
        return {"results": []}

    tester = HypothesisTesterAgent(
        name="tester",
        llm=mock_llm,
        tools_definitions=[],
        tool_executor=mock_executor,
    )

    ledger = EvidenceLedger()
    hyp = Hypothesis(statement="Database connection pool exhausted")
    ledger.add_hypothesis(hyp)

    updated_hyp = await tester.test(hyp, ledger)
    assert updated_hyp.confidence == 0.85
    assert len(updated_hyp.evidence) == 1
    assert updated_hyp.evidence[0].supports is True
    assert updated_hyp.evidence[0].event_ids == ["evt_123", "evt_124"]


@pytest.mark.asyncio
async def test_critic_agent_approves():
    critic_response = json.dumps(
        {
            "verdict": "approved",
            "notes": "Temporal sequence holds: pool exhaustion preceded checkout failures.",
        }
    )

    mock_llm = MockLLMProvider(responses=[critic_response])
    critic = CriticAgent(name="critic", llm=mock_llm)

    ledger = EvidenceLedger()
    hyp = Hypothesis(
        statement="Database connection pool exhausted",
        confidence=0.85,
        status=HypothesisStatus.TESTING,
    )
    ledger.add_hypothesis(hyp)
    ledger.add_evidence(
        hyp.id,
        EvidenceItem(
            hypothesis_id=hyp.id,
            event_ids=["evt_01"],
            summary="Pool exhausted",
            supports=True,
            earliest_timestamp=datetime(2024, 1, 15, 10, 26, 0),
        ),
    )

    result = await critic.evaluate(ledger, symptom_time=datetime(2024, 1, 15, 10, 28, 0))
    assert result["verdict"] == "approved"
    assert "Temporal sequence holds" in result["notes"]
    assert hyp.critic_notes == result["notes"]


@pytest.mark.asyncio
async def test_reporter_agent_writes_report():
    report_response = json.dumps(
        {
            "executive_summary": "Major outage caused by db-proxy pool exhaustion.",
            "root_cause": "Database connection pool was saturated.",
            "confidence": 0.9,
            "incident_timeline": [
                {"timestamp": "2024-01-15T10:26:00", "description": "Pool usage reached 90%"},
                {"timestamp": "2024-01-15T10:28:00", "description": "Pool exhausted"},
            ],
            "recommended_mitigations": ["Increase pool size", "Implement circuit breaker"],
            "unknowns": ["Root query that caused leak"],
        }
    )

    mock_llm = MockLLMProvider(responses=[report_response])
    reporter = ReporterAgent(name="reporter", llm=mock_llm)

    ledger = EvidenceLedger()
    hyp = Hypothesis(
        statement="Database connection pool exhausted",
        confidence=0.9,
        status=HypothesisStatus.SUPPORTED,
    )
    ledger.add_hypothesis(hyp)
    ledger.add_evidence(
        hyp.id,
        EvidenceItem(
            hypothesis_id=hyp.id,
            event_ids=["evt_01"],
            summary="Pool exhausted",
            supports=True,
        ),
    )

    brief = IncidentBrief(
        incident_window_start=datetime(2024, 1, 15, 10, 25, 0),
        incident_window_end=datetime(2024, 1, 15, 10, 35, 0),
        affected_services=["db-proxy"],
        primary_symptoms=["Connection errors"],
    )

    result = await reporter.write_report(ledger, brief)
    assert result.executive_summary == "Major outage caused by db-proxy pool exhaustion."
    assert result.root_cause == "Database connection pool was saturated."
    assert "evt_01" in result.verified_evidence_event_ids
    assert len(result.recommended_mitigations) == 2


@pytest.mark.asyncio
async def test_orchestrator_flow():
    # Sequence of mock LLM responses for end-to-end investigation:
    # 1. Triage
    triage_json = json.dumps(
        {
            "incident_window_start": "2024-01-15T10:25:00",
            "incident_window_end": "2024-01-15T10:35:00",
            "affected_services": ["db-proxy", "checkout-service"],
            "primary_symptoms": ["Connection pool exhausted", "504 Gateway Timeout"],
            "anomalous_templates": [],
            "user_hint": "DB issue",
        }
    )
    # 2. Generator
    generator_json = json.dumps(
        [
            {
                "statement": "Database connection pool exhausted",
                "predicted_evidence": ["Error logs in db-proxy"],
                "falsification_conditions": ["Free connections available"],
            }
        ]
    )
    # 3. Tester
    tester_json = json.dumps(
        {
            "supports": True,
            "summary": "Verified connection pool exhaustion in db-proxy",
            "event_ids": ["evt_100"],
            "confidence": 0.85,
        }
    )
    # 4. Critic
    critic_json = json.dumps(
        {
            "verdict": "approved",
            "notes": "Confirmed valid cause and sequence",
        }
    )
    # 5. Reporter
    reporter_json = json.dumps(
        {
            "executive_summary": "Database pool exhaustion outage.",
            "root_cause": "db-proxy ran out of database connections.",
            "confidence": 0.85,
            "incident_timeline": [{"timestamp": "2024-01-15T10:28:00", "description": "Connection pool exhausted"}],
            "recommended_mitigations": ["Scale up db connection limits"],
            "unknowns": [],
        }
    )

    mock_llm = MockLLMProvider(responses=[triage_json, generator_json, tester_json, critic_json, reporter_json])

    config = InvestigationConfig(max_rounds=2, confidence_threshold=0.7)
    orchestrator = InvestigationOrchestrator(llm=mock_llm, config=config)

    events_received = []
    orchestrator.on_event = lambda ev: events_received.append(ev)

    # Set up in-memory store and dummy data
    store = LogStore(":memory:")
    sample_event = LogEvent(
        event_id="evt_100",
        timestamp=datetime(2024, 1, 15, 10, 28, 0),
        level=LogLevel.ERROR,
        service="db-proxy",
        message="Connection pool exhausted",
        template_id="tpl_01",
    )
    sample_template = TemplateCluster(
        template_id="tpl_01",
        pattern="Connection pool exhausted",
        sample_message="Connection pool exhausted",
        total_count=10,
        is_anomaly=True,
        anomaly_score=5.0,
        services=["db-proxy"],
    )
    sample_bucket = BucketCount(
        template_id="tpl_01",
        bucket_start=datetime(2024, 1, 15, 10, 28, 0),
        count=10,
        service="db-proxy",
    )

    store.ingest_events([sample_event])
    store.ingest_templates([sample_template])
    store.ingest_buckets([sample_bucket])

    result = await orchestrator.investigate(
        events=[sample_event],
        templates=[sample_template],
        buckets=[sample_bucket],
        store=store,
        user_hint="DB issue",
    )

    assert result.root_cause == "db-proxy ran out of database connections."
    assert result.confidence == 0.85
    assert result.total_tokens_used > 0
    assert len(events_received) > 0

    # Ensure REPORT_READY was emitted
    event_types = [ev.event_type for ev in events_received]
    assert "STAGE_CHANGED" in event_types
    assert "REPORT_READY" in event_types
    store.close()
