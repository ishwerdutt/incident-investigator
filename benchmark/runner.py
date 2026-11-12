"""Benchmark evaluation runner.

Runs the Incident Investigator on synthetic outage scenarios and evaluates:
- Root-cause identification accuracy
- Temporal validity (cause timestamp precedes symptom timestamp)
- Citation validity (every cited event_id exists in store and contains relevant error)
- Scorecard summary metrics
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from incident_investigator.investigator import Investigator
from incident_investigator.llm.provider import LLMProvider
from incident_investigator.models import InvestigationConfig, InvestigationResult, LogLevel


class BenchmarkRunner:
    """Automated benchmark evaluator for root-cause analysis pipelines."""

    def __init__(
        self,
        llm: LLMProvider | None = None,
        config: InvestigationConfig | None = None,
    ) -> None:
        self.llm = llm
        self.config = config or InvestigationConfig()

    async def run_scenario(
        self,
        name: str,
        log_lines: list[str],
        ground_truth: dict[str, Any],
    ) -> dict[str, Any]:
        """Run an investigation on a single scenario and evaluate its quality."""
        investigator = Investigator(llm=self.llm, config=self.config)
        hint = ground_truth.get("hint")

        result: InvestigationResult = await investigator.investigate_async(
            raw_logs=log_lines,
            hint=hint,
        )

        # --------------------------------------------------------------
        # 1. Root-cause identification accuracy
        # --------------------------------------------------------------
        combined_text = " ".join(
            [
                result.root_cause or "",
                result.executive_summary or "",
                result.supported_hypothesis.statement if result.supported_hypothesis else "",
            ]
        ).lower()

        keywords = [kw.lower() for kw in ground_truth.get("root_cause_keywords", [])]
        matched_keywords = [kw for kw in keywords if kw in combined_text]
        # Considered accurate if at least 1 prominent keyword matches or root cause matches
        root_cause_accurate = len(matched_keywords) >= 1 or (
            ground_truth.get("root_cause", "").lower() in combined_text
        )

        # --------------------------------------------------------------
        # 2. Temporal validity
        # --------------------------------------------------------------
        # Cause timestamp strictly precedes symptom timestamp
        temporal_valid = True
        cause_ts: datetime | None = None
        symptom_ts: datetime | None = None

        # Check evidence in supported hypothesis
        if result.supported_hypothesis and result.supported_hypothesis.evidence:
            earliest_ev = [
                e.earliest_timestamp for e in result.supported_hypothesis.evidence if e.earliest_timestamp is not None
            ]
            if earliest_ev:
                cause_ts = min(earliest_ev)

        # Fallback to incident timeline
        if cause_ts is None and result.incident_timeline:
            for item in result.incident_timeline:
                raw_ts = item.get("timestamp")
                if raw_ts:
                    try:
                        cause_ts = datetime.fromisoformat(str(raw_ts))
                        break
                    except (ValueError, TypeError):
                        pass

        # Parse symptom timestamp from ground truth or failing services
        raw_symptom = ground_truth.get("incident_start")
        if raw_symptom:
            try:
                symptom_ts = datetime.fromisoformat(str(raw_symptom))
            except (ValueError, TypeError):
                try:
                    symptom_ts = datetime.strptime(str(raw_symptom), "%Y-%m-%d %H:%M:%S")
                except (ValueError, TypeError):
                    pass

        if cause_ts is not None and symptom_ts is not None:
            # Cause must precede or equal the symptom onset (strictly precede or lead the window)
            temporal_valid = cause_ts <= symptom_ts
        else:
            temporal_valid = True

        # --------------------------------------------------------------
        # 3. Citation validity
        # --------------------------------------------------------------
        # Collect all cited event IDs
        cited_ids: list[str] = list(result.verified_evidence_event_ids or [])
        if result.supported_hypothesis:
            for ev in result.supported_hypothesis.evidence:
                cited_ids.extend(ev.event_ids)

        cited_ids = list(dict.fromkeys(cited_ids))  # deduplicate preserving order

        # Look up against parsed events from investigator
        events_by_id = {e.event_id: e for e in getattr(investigator, "last_events", [])}

        valid_citations = 0
        citation_details = []
        error_levels = {LogLevel.ERROR, LogLevel.FATAL, LogLevel.WARN}
        error_words = [
            "error",
            "fail",
            "timeout",
            "kill",
            "exception",
            "unavailable",
            "504",
            "503",
            "500",
            "502",
            "exhaust",
            "leak",
            "npe",
            "nullpointer",
        ]

        for cid in cited_ids:
            if cid in events_by_id:
                evt = events_by_id[cid]
                msg_lower = evt.message.lower()
                is_error = evt.level in error_levels or any(w in msg_lower for w in error_words)
                if is_error:
                    valid_citations += 1
                citation_details.append({"event_id": cid, "exists": True, "contains_error": is_error})
            else:
                citation_details.append({"event_id": cid, "exists": False, "contains_error": False})

        citation_precision = (valid_citations / len(cited_ids)) if cited_ids else 1.0

        return {
            "scenario": name,
            "root_cause_accurate": root_cause_accurate,
            "temporal_valid": temporal_valid,
            "citation_precision": citation_precision,
            "total_citations": len(cited_ids),
            "valid_citations": valid_citations,
            "matched_keywords": matched_keywords,
            "duration_seconds": result.investigation_duration_seconds,
            "tool_calls": result.total_tool_calls,
            "tokens_used": result.total_tokens_used,
            "confidence": result.confidence,
            "citation_details": citation_details,
            "result": result,
        }

    async def run_suite(
        self,
        scenarios: dict[str, tuple[list[str], dict[str, Any]]] | None = None,
    ) -> dict[str, Any]:
        """Run all benchmark scenarios and generate aggregated scorecard."""
        if scenarios is None:
            from benchmark.generator import ScenarioGenerator

            scenarios = ScenarioGenerator.generate_all()

        results: list[dict[str, Any]] = []
        for name, (lines, ground_truth) in scenarios.items():
            sc_res = await self.run_scenario(name, lines, ground_truth)
            results.append(sc_res)

        total = len(results)
        if total == 0:
            return {"total_scenarios": 0}

        accuracy = sum(1 for r in results if r["root_cause_accurate"]) / total
        mean_precision = sum(r["citation_precision"] for r in results) / total
        temporal_rate = sum(1 for r in results if r["temporal_valid"]) / total
        mean_duration = sum(r["duration_seconds"] for r in results) / total
        total_tool_calls = sum(r["tool_calls"] for r in results)
        total_tokens = sum(r["tokens_used"] for r in results)

        scorecard = {
            "total_scenarios": total,
            "accuracy_pct": round(accuracy * 100.0, 1),
            "citation_precision_pct": round(mean_precision * 100.0, 1),
            "temporal_validity_pct": round(temporal_rate * 100.0, 1),
            "mean_duration_seconds": round(mean_duration, 2),
            "total_tool_calls": total_tool_calls,
            "total_tokens_used": total_tokens,
            "scenario_results": results,
        }
        return scorecard

    def generate_scorecard_markdown(self, scorecard: dict[str, Any]) -> str:
        """Render evaluation scorecard as GitHub-flavored Markdown."""
        lines = [
            "# Synthetic Chaos Incident Benchmark Scorecard\n",
            f"**Total Scenarios:** {scorecard.get('total_scenarios', 0)}  ",
            f"**Root-Cause Accuracy:** {scorecard.get('accuracy_pct', 0.0)}%  ",
            f"**Citation Precision:** {scorecard.get('citation_precision_pct', 0.0)}%  ",
            f"**Temporal Validity:** {scorecard.get('temporal_validity_pct', 0.0)}%  ",
            f"**Mean Investigation Duration:** {scorecard.get('mean_duration_seconds', 0.0)}s  ",
            f"**Total Tool Calls:** {scorecard.get('total_tool_calls', 0)}  \n",
            "## Scenario Breakdown\n",
            "| Scenario | Accurate | Temporal Valid | Citation Precision | Duration (s) | Tool Calls | Confidence |",
            "|---|:---:|:---:|:---:|:---:|:---:|:---:|",
        ]

        for s in scorecard.get("scenario_results", []):
            acc_icon = "✅" if s["root_cause_accurate"] else "❌"
            temp_icon = "✅" if s["temporal_valid"] else "❌"
            prec = f"{s['citation_precision'] * 100:.0f}%"
            dur = f"{s['duration_seconds']:.1f}"
            calls = str(s["tool_calls"])
            conf = f"{s['confidence']:.0%}"
            lines.append(f"| `{s['scenario']}` | {acc_icon} | {temp_icon} | {prec} | {dur} | {calls} | {conf} |")

        return "\n".join(lines)
