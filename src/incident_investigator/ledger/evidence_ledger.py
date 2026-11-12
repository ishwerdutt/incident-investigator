"""Evidence ledger: tracks hypotheses and evidence for an investigation."""

from __future__ import annotations

from datetime import datetime

from incident_investigator.models import (
    EvidenceItem,
    Hypothesis,
    HypothesisStatus,
)


class LedgerIntegrityError(Exception):
    """Raised when a ledger invariant is violated."""


class EvidenceLedger:
    """In-memory store of hypotheses and their evidence chains."""

    def __init__(self) -> None:
        self._hypotheses: list[Hypothesis] = []

    # ------------------------------------------------------------------
    # Hypotheses
    # ------------------------------------------------------------------

    def add_hypothesis(self, hypothesis: Hypothesis) -> None:
        """Register a new hypothesis."""
        self._hypotheses.append(hypothesis)

    def get_hypothesis(self, hypothesis_id: str) -> Hypothesis | None:
        """Fetch a hypothesis by its ID."""
        for h in self._hypotheses:
            if h.id == hypothesis_id:
                return h
        return None

    def get_all_hypotheses(self) -> list[Hypothesis]:
        """Return every hypothesis in the ledger."""
        return list(self._hypotheses)

    def get_open_hypotheses(self) -> list[Hypothesis]:
        """Return hypotheses with OPEN or TESTING status."""
        return [h for h in self._hypotheses if h.status in (HypothesisStatus.OPEN, HypothesisStatus.TESTING)]

    # ------------------------------------------------------------------
    # Evidence
    # ------------------------------------------------------------------

    def add_evidence(self, hypothesis_id: str, evidence: EvidenceItem) -> None:
        """Attach an evidence item to a hypothesis."""
        hyp = self.get_hypothesis(hypothesis_id)
        if hyp is None:
            raise LedgerIntegrityError(f"Hypothesis {hypothesis_id} not found")
        hyp.evidence.append(evidence)

    # ------------------------------------------------------------------
    # Status management
    # ------------------------------------------------------------------

    def update_status(
        self,
        hypothesis_id: str,
        status: HypothesisStatus,
        confidence: float | None = None,
    ) -> None:
        """Update a hypothesis status, enforcing ledger invariants.

        INVARIANT for SUPPORTED:
          1. At least one evidence item with ``supports=True``
          2. At least one evidence item with non-empty ``event_ids``
        """
        hyp = self.get_hypothesis(hypothesis_id)
        if hyp is None:
            raise LedgerIntegrityError(f"Hypothesis {hypothesis_id} not found")

        if status == HypothesisStatus.SUPPORTED:
            has_supporting = any(e.supports for e in hyp.evidence)
            has_event_ids = any(len(e.event_ids) > 0 for e in hyp.evidence)
            if not has_supporting:
                raise LedgerIntegrityError(
                    f"Cannot mark hypothesis {hypothesis_id} as SUPPORTED: no evidence with supports=True"
                )
            if not has_event_ids:
                raise LedgerIntegrityError(
                    f"Cannot mark hypothesis {hypothesis_id} as SUPPORTED: no evidence with non-empty event_ids"
                )

        hyp.status = status
        if confidence is not None:
            hyp.confidence = confidence

    def mark_refuted(self, hypothesis_id: str, reason: str) -> None:
        """Shorthand: set status to REFUTED and record the reason."""
        hyp = self.get_hypothesis(hypothesis_id)
        if hyp is None:
            raise LedgerIntegrityError(f"Hypothesis {hypothesis_id} not found")
        hyp.status = HypothesisStatus.REFUTED
        hyp.critic_notes = reason

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_leading_hypothesis(self) -> Hypothesis | None:
        """Return the highest-confidence hypothesis among OPEN/TESTING/SUPPORTED."""
        candidates = [
            h
            for h in self._hypotheses
            if h.status
            in (
                HypothesisStatus.OPEN,
                HypothesisStatus.TESTING,
                HypothesisStatus.SUPPORTED,
            )
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda h: h.confidence)

    def validate_temporal_order(self, hypothesis_id: str, symptom_time: datetime) -> bool:
        """Check whether the earliest evidence timestamp precedes *symptom_time*.

        Returns ``True`` if temporal ordering is valid (cause before symptom),
        or ``True`` if there is no evidence with timestamps to check.
        Returns ``False`` if the earliest evidence is *after* the symptom.
        """
        hyp = self.get_hypothesis(hypothesis_id)
        if hyp is None:
            return False
        timestamps = [e.earliest_timestamp for e in hyp.evidence if e.earliest_timestamp is not None]
        if not timestamps:
            return True  # no timestamps to contradict
        return min(timestamps) < symptom_time

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def to_summary(self) -> str:
        """Human-readable summary of the ledger."""
        if not self._hypotheses:
            return "Ledger is empty."
        lines: list[str] = ["=== Evidence Ledger ==="]
        for h in self._hypotheses:
            supporting = sum(1 for e in h.evidence if e.supports)
            refuting = sum(1 for e in h.evidence if not e.supports)
            lines.append(f"[{h.status.value.upper()}] (confidence={h.confidence:.2f}) {h.statement}")
            lines.append(f"   Evidence: {len(h.evidence)} total, {supporting} supporting, {refuting} refuting")
            if h.critic_notes:
                lines.append(f"   Critic: {h.critic_notes}")
        return "\n".join(lines)
