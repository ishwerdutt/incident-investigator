"""Investigation orchestrator: coordinates multi-agent investigation workflow."""

from __future__ import annotations

import asyncio
import inspect
import time
from collections.abc import Callable
from typing import Any

from incident_investigator.agents.critic import CriticAgent
from incident_investigator.agents.generator import HypothesisGeneratorAgent
from incident_investigator.agents.reporter import ReporterAgent
from incident_investigator.agents.tester import HypothesisTesterAgent
from incident_investigator.agents.triage import TriageAgent
from incident_investigator.ledger.evidence_ledger import (
    EvidenceLedger,
    LedgerIntegrityError,
)
from incident_investigator.llm.provider import LLMProvider
from incident_investigator.models import (
    BucketCount,
    HypothesisStatus,
    InvestigationConfig,
    InvestigationEvent,
    InvestigationResult,
    LogEvent,
    TemplateCluster,
)
from incident_investigator.store.duckdb_store import LogStore
from incident_investigator.tools.investigation_tools import (
    TOOL_DEFINITIONS,
    InvestigationTools,
)


class InvestigationOrchestrator:
    """Coordinates Triage, Hypothesis Generation, Testing, Critic, and
    Reporting agents into an end-to-end investigation loop."""

    def __init__(
        self,
        llm: LLMProvider,
        config: InvestigationConfig | None = None,
        on_event: Callable[[InvestigationEvent], None] | None = None,
    ) -> None:
        self.llm = llm
        self.config = config or InvestigationConfig()
        self.on_event = on_event

    def _emit(
        self,
        event_type: str,
        stage: str | None = None,
        agent: str | None = None,
        data: dict[str, Any] | None = None,
    ) -> None:
        """Fire the on_event callback if registered."""
        if self.on_event is not None:
            event = InvestigationEvent(
                event_type=event_type,
                stage=stage,
                agent=agent,
                data=data or {},
            )
            try:
                res = self.on_event(event)
                if inspect.iscoroutine(res):
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(res)
                    except RuntimeError:
                        pass
            except Exception:  # noqa: BLE001, S110
                pass

    async def investigate(
        self,
        events: list[LogEvent],
        templates: list[TemplateCluster],
        buckets: list[BucketCount],
        store: LogStore,
        user_hint: str | None = None,
    ) -> InvestigationResult:
        """Run the full multi-agent investigation pipeline."""
        start_time = time.time()
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_tool_calls = 0

        # --------------------------------------------------------------
        # 1. Build summary strings from templates and buckets
        # --------------------------------------------------------------
        self._emit("STAGE_CHANGED", stage="summarize", agent="orchestrator")

        sorted_templates = sorted(
            templates,
            key=lambda t: (t.is_anomaly, t.anomaly_score, t.total_count),
            reverse=True,
        )
        min_ts = min((e.timestamp for e in events), default=None)
        max_ts = max((e.timestamp for e in events), default=None)
        time_header = (
            f"Log time range spans from {min_ts.isoformat()} to {max_ts.isoformat()}.\n\n"
            if min_ts and max_ts
            else ""
        )

        tpl_lines = [
            f"- [{t.template_id}] count={t.total_count} anomaly={t.is_anomaly} "
            f"score={t.anomaly_score:.2f} services={','.join(t.services)}: {t.pattern}"
            for t in sorted_templates[:20]
        ]
        template_summary = time_header + ("\n".join(tpl_lines) or "No templates found.")

        anomalous = [t for t in templates if t.is_anomaly]
        anom_lines = [
            f"- [{t.template_id}] score={t.anomaly_score:.2f} count={t.total_count} sample={t.sample_message}"
            for t in sorted(anomalous, key=lambda t: t.anomaly_score, reverse=True)[:10]
        ]
        anomaly_summary = "\n".join(anom_lines) or "No anomalies detected."

        # --------------------------------------------------------------
        # 2. Triage -> IncidentBrief
        # --------------------------------------------------------------
        self._emit(
            "STAGE_CHANGED",
            stage="triage",
            agent="triage",
            data={"user_hint": user_hint},
        )
        triage_agent = TriageAgent("triage", self.llm, model=self.config.openai_model)
        brief = await triage_agent.analyze(
            template_summary=template_summary,
            anomaly_summary=anomaly_summary,
            user_hint=user_hint,
        )
        total_prompt_tokens += triage_agent.token_usage["prompt"]
        total_completion_tokens += triage_agent.token_usage["completion"]

        # Ensure anomalous templates are populated on the brief if empty
        if not brief.anomalous_templates and anomalous:
            brief.anomalous_templates = anomalous

        # --------------------------------------------------------------
        # 3. Generate Hypotheses
        # --------------------------------------------------------------
        self._emit("STAGE_CHANGED", stage="generate", agent="generator")
        ledger = EvidenceLedger()
        generator_agent = HypothesisGeneratorAgent("generator", self.llm, model=self.config.openai_model)
        hypotheses = await generator_agent.generate(brief, ledger)
        total_prompt_tokens += generator_agent.token_usage["prompt"]
        total_completion_tokens += generator_agent.token_usage["completion"]

        self._emit(
            "LEDGER_UPDATED",
            stage="generate",
            agent="generator",
            data={
                "hypotheses_count": len(hypotheses),
                "hypotheses": [h.statement for h in hypotheses],
            },
        )

        # --------------------------------------------------------------
        # 4. Testing & Critic Loop
        # --------------------------------------------------------------
        investigation_tools = InvestigationTools(store)

        def tool_executor(tool_name: str, **kwargs: Any) -> Any:
            nonlocal total_tool_calls
            total_tool_calls += 1
            self._emit(
                "TOOL_CALLED",
                stage="testing",
                agent="tester",
                data={"tool": tool_name, "args": kwargs},
            )
            fn = getattr(investigation_tools, tool_name, None)
            if fn is None:
                res = {"error": f"Tool '{tool_name}' not found"}
            else:
                try:
                    res = fn(**kwargs)
                except Exception as exc:  # noqa: BLE001
                    res = {"error": str(exc)}
            self._emit(
                "TOOL_RESULT",
                stage="testing",
                agent="tester",
                data={"tool": tool_name, "result": res},
            )
            return res

        for round_num in range(1, self.config.max_rounds + 1):
            open_hypotheses = ledger.get_open_hypotheses()
            if not open_hypotheses:
                break

            self._emit(
                "STAGE_CHANGED",
                stage="testing",
                agent="tester",
                data={"round": round_num, "hypotheses_count": len(open_hypotheses)},
            )

            # Test all open hypotheses in parallel
            testers = [
                HypothesisTesterAgent(
                    name=f"tester_{h.id}",
                    llm=self.llm,
                    tools_definitions=TOOL_DEFINITIONS,
                    tool_executor=tool_executor,
                    model=self.config.openai_model,
                )
                for h in open_hypotheses
            ]

            test_tasks = [
                tester.test(
                    h,
                    ledger,
                    max_tool_calls=self.config.max_tool_calls_per_agent,
                )
                for tester, h in zip(testers, open_hypotheses)
            ]
            await asyncio.gather(*test_tasks)

            for tester in testers:
                total_prompt_tokens += tester.token_usage["prompt"]
                total_completion_tokens += tester.token_usage["completion"]

            self._emit(
                "LEDGER_UPDATED",
                stage="testing",
                agent="tester",
                data={"summary": ledger.to_summary()},
            )

            # Critic evaluates the leading hypothesis
            self._emit(
                "STAGE_CHANGED",
                stage="critic",
                agent="critic",
                data={"round": round_num},
            )
            critic_agent = CriticAgent("critic", self.llm, model=self.config.openai_model)
            critic_result = await critic_agent.evaluate(ledger, symptom_time=brief.incident_window_start)
            total_prompt_tokens += critic_agent.token_usage["prompt"]
            total_completion_tokens += critic_agent.token_usage["completion"]

            leading = ledger.get_leading_hypothesis()
            verdict = critic_result.get("verdict")

            # Check if leading hypothesis can be marked SUPPORTED and is approved
            if leading and verdict == "approved":
                if leading.confidence >= self.config.confidence_threshold:
                    try:
                        ledger.update_status(
                            leading.id,
                            HypothesisStatus.SUPPORTED,
                            confidence=leading.confidence,
                        )
                        break
                    except LedgerIntegrityError:
                        pass
                elif leading.status == HypothesisStatus.SUPPORTED:
                    break

            # Check token budget
            if (total_prompt_tokens + total_completion_tokens) >= self.config.max_total_tokens:
                break

        # --------------------------------------------------------------
        # 5. Reporter writes final report
        # --------------------------------------------------------------
        self._emit("STAGE_CHANGED", stage="reporting", agent="reporter")
        reporter_agent = ReporterAgent("reporter", self.llm, model=self.config.openai_model)
        result = await reporter_agent.write_report(ledger, brief)
        total_prompt_tokens += reporter_agent.token_usage["prompt"]
        total_completion_tokens += reporter_agent.token_usage["completion"]

        duration = time.time() - start_time
        result.total_tokens_used = total_prompt_tokens + total_completion_tokens
        result.total_tool_calls = total_tool_calls
        result.investigation_duration_seconds = round(duration, 2)

        # Ensure supported_hypothesis and ruled_out_hypotheses are correctly linked
        if result.supported_hypothesis is None:
            result.supported_hypothesis = ledger.get_leading_hypothesis()
        if not result.ruled_out_hypotheses:
            result.ruled_out_hypotheses = [
                h for h in ledger.get_all_hypotheses() if h.status == HypothesisStatus.REFUTED
            ]

        self._emit(
            "REPORT_READY",
            stage="complete",
            agent="reporter",
            data={"incident_id": result.incident_id, "confidence": result.confidence},
        )

        return result
