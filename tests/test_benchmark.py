"""Tests for synthetic chaos incident benchmark suite."""

import json

import pytest

from benchmark import (
    BenchmarkRunner,
    ScenarioGenerator,
    generate_bad_deployment,
    generate_db_pool_exhaustion,
    generate_oom_kill,
    generate_upstream_outage,
)
from incident_investigator.ingest.parsers import AutoParser
from incident_investigator.llm.provider import MockLLMProvider
from incident_investigator.models import InvestigationConfig, LogLevel


class TestScenarioGenerator:
    """Verify all 4 outage scenarios generate realistic parseable logs."""

    def test_generate_db_pool_exhaustion(self):
        lines, gt = generate_db_pool_exhaustion(num_lines=100)
        assert len(lines) == 100
        assert gt["scenario_name"] == "db_pool_exhaustion"
        assert "pool" in gt["root_cause"].lower()
        assert "db-proxy" in gt["expected_failing_services"]
        assert len(gt["incident_window"]) == 2

        # Verify AutoParser parses the lines
        parser = AutoParser(lines)
        parsed_events = [parser.parse_line(l, "benchmark", idx) for idx, l in enumerate(lines, 1)]
        valid_events = [e for e in parsed_events if e is not None]
        assert len(valid_events) == 100
        assert any("db-proxy" in e.service for e in valid_events)
        assert any(e.level in (LogLevel.WARN, LogLevel.ERROR) for e in valid_events)

    def test_generate_oom_kill(self):
        lines, gt = generate_oom_kill(num_lines=80)
        assert len(lines) == 80
        assert gt["scenario_name"] == "oom_kill"
        assert "worker-service" in gt["expected_failing_services"]
        assert any("oom" in kw.lower() for kw in gt["root_cause_keywords"])

        parser = AutoParser(lines)
        parsed_events = [parser.parse_line(l, "benchmark", idx) for idx, l in enumerate(lines, 1)]
        valid_events = [e for e in parsed_events if e is not None]
        assert len(valid_events) == 80
        assert any("Out of memory" in e.message or "exit code 137" in e.message for e in valid_events)

    def test_generate_bad_deployment(self):
        lines, gt = generate_bad_deployment(num_lines=80)
        assert len(lines) == 80
        assert gt["scenario_name"] == "bad_deployment"
        assert "checkout-service" in gt["expected_failing_services"]
        assert any("v2.4.1" in kw.lower() for kw in gt["root_cause_keywords"])

        parser = AutoParser(lines)
        parsed_events = [parser.parse_line(l, "benchmark", idx) for idx, l in enumerate(lines, 1)]
        valid_events = [e for e in parsed_events if e is not None]
        assert len(valid_events) == 80
        assert any("NullPointerException" in e.message for e in valid_events)

    def test_generate_upstream_outage(self):
        lines, gt = generate_upstream_outage(num_lines=80)
        assert len(lines) == 80
        assert gt["scenario_name"] == "upstream_outage"
        assert "payment-service" in gt["expected_failing_services"]
        assert any("pay-gateway" in kw.lower() for kw in gt["root_cause_keywords"])

        parser = AutoParser(lines)
        parsed_events = [parser.parse_line(l, "benchmark", idx) for idx, l in enumerate(lines, 1)]
        valid_events = [e for e in parsed_events if e is not None]
        assert len(valid_events) == 80
        assert any("503 Service Unavailable" in e.message for e in valid_events)

    def test_scenario_generator_generate_all(self):
        scenarios = ScenarioGenerator.generate_all()
        assert len(scenarios) == 4
        assert "db_pool_exhaustion" in scenarios
        assert "oom_kill" in scenarios
        assert "bad_deployment" in scenarios
        assert "upstream_outage" in scenarios
        for lines, gt in scenarios.values():
            assert len(lines) >= 400
            assert "root_cause" in gt
            assert "expected_failing_services" in gt


class TestBenchmarkRunner:
    """Verify BenchmarkRunner executes investigations and evaluates scorecard."""

    @pytest.mark.asyncio
    async def test_run_scenario_with_mock_llm(self):
        # Setup mock LLM responses for a complete investigation flow
        triage_json = json.dumps(
            {
                "incident_window_start": "2024-01-15T10:15:00",
                "incident_window_end": "2024-01-15T10:35:00",
                "affected_services": ["db-proxy", "checkout-service", "api-gateway"],
                "primary_symptoms": ["Connection pool exhausted", "504 Gateway Timeout"],
                "anomalous_templates": [],
                "user_hint": "Checkout failing with 504 Gateway Timeout",
            }
        )
        generator_json = json.dumps(
            [
                {
                    "statement": "Database connection pool exhaustion on db-proxy",
                    "predicted_evidence": ["Connection pool warning and timeout logs in db-proxy"],
                    "falsification_conditions": ["Active pool connections remains below 50"],
                }
            ]
        )
        tester_json = json.dumps(
            {
                "supports": True,
                "summary": "Confirmed db-proxy connection pool reached 100/100 capacity",
                "event_ids": [],
                "confidence": 0.90,
            }
        )
        critic_json = json.dumps(
            {
                "verdict": "approved",
                "notes": "Evidence strongly supports database pool exhaustion",
            }
        )
        reporter_json = json.dumps(
            {
                "executive_summary": "Major cascading outage caused by database connection pool exhaustion on db-proxy.",
                "root_cause": "Database connection pool exhaustion on db-proxy causing cascading timeouts",
                "confidence": 0.90,
                "incident_timeline": [
                    {"timestamp": "2024-01-15 10:10:00", "description": "db-proxy pool saturation began"},
                    {"timestamp": "2024-01-15 10:15:00", "description": "checkout-service connection timeouts"},
                ],
                "recommended_mitigations": ["Increase maximum database pool size to 250"],
                "unknowns": [],
            }
        )

        mock_llm = MockLLMProvider(responses=[triage_json, generator_json, tester_json, critic_json, reporter_json])

        config = InvestigationConfig(max_rounds=2, confidence_threshold=0.7)
        runner = BenchmarkRunner(llm=mock_llm, config=config)

        lines, ground_truth = generate_db_pool_exhaustion(num_lines=60)
        report = await runner.run_scenario("db_pool_exhaustion", lines, ground_truth)

        assert report["scenario"] == "db_pool_exhaustion"
        assert report["root_cause_accurate"] is True
        assert report["temporal_valid"] is True
        assert report["citation_precision"] == 1.0
        assert report["confidence"] == 0.90
        assert report["duration_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_run_suite_and_scorecard_markdown(self):
        triage_json = json.dumps(
            {
                "incident_window_start": "2024-01-15T11:15:00",
                "incident_window_end": "2024-01-15T11:35:00",
                "affected_services": ["worker-service", "api-gateway"],
                "primary_symptoms": ["Memory leak warning", "OOMKilled exit code 137"],
                "anomalous_templates": [],
                "user_hint": "Worker crashed",
            }
        )
        generator_json = json.dumps(
            [
                {
                    "statement": "Memory leak in worker-service leading to kernel OOM kill",
                    "predicted_evidence": ["Heap memory consumption rising to 95%"],
                    "falsification_conditions": ["Memory remains steady at 50%"],
                }
            ]
        )
        tester_json = json.dumps(
            {
                "supports": True,
                "summary": "Verified heap consumption at 95% followed by exit code 137",
                "event_ids": [],
                "confidence": 0.92,
            }
        )
        critic_json = json.dumps(
            {
                "verdict": "approved",
                "notes": "Temporal sequence validates memory leak preceding pod crash",
            }
        )
        reporter_json = json.dumps(
            {
                "executive_summary": "Worker pod killed due to memory leak.",
                "root_cause": "Memory leak in worker-service resulting in kernel OOM-killer (exit code 137)",
                "confidence": 0.92,
                "incident_timeline": [
                    {"timestamp": "2024-01-15 11:10:00", "description": "Memory leak began"},
                    {"timestamp": "2024-01-15 11:20:00", "description": "Kernel OOM kill"},
                ],
                "recommended_mitigations": ["Profile dataframe memory retention in worker"],
                "unknowns": [],
            }
        )

        mock_llm = MockLLMProvider(responses=[triage_json, generator_json, tester_json, critic_json, reporter_json])

        config = InvestigationConfig(max_rounds=2, confidence_threshold=0.7)
        runner = BenchmarkRunner(llm=mock_llm, config=config)

        lines, ground_truth = generate_oom_kill(num_lines=50)
        mini_suite = {"oom_kill": (lines, ground_truth)}

        scorecard = await runner.run_suite(mini_suite)

        assert scorecard["total_scenarios"] == 1
        assert scorecard["accuracy_pct"] == 100.0
        assert scorecard["citation_precision_pct"] == 100.0
        assert scorecard["temporal_validity_pct"] == 100.0

        md = runner.generate_scorecard_markdown(scorecard)
        assert "# Synthetic Chaos Incident Benchmark Scorecard" in md
        assert "`oom_kill`" in md
        assert "100%" in md
