"""Tests for EvidenceLedger."""

from datetime import datetime, timedelta

import pytest

from incident_investigator.ledger.evidence_ledger import (
    EvidenceLedger,
    LedgerIntegrityError,
)
from incident_investigator.models import (
    EvidenceItem,
    Hypothesis,
    HypothesisStatus,
)


def test_add_and_retrieve_hypothesis():
    ledger = EvidenceLedger()
    hyp = Hypothesis(
        statement="Database connection pool exhausted",
        predicted_evidence=["error spike on db-proxy"],
        falsification_conditions=["normal latency to db"],
    )
    ledger.add_hypothesis(hyp)

    retrieved = ledger.get_hypothesis(hyp.id)
    assert retrieved is not None
    assert retrieved.statement == "Database connection pool exhausted"
    assert retrieved.status == HypothesisStatus.OPEN
    assert len(ledger.get_all_hypotheses()) == 1
    assert len(ledger.get_open_hypotheses()) == 1


def test_add_evidence():
    ledger = EvidenceLedger()
    hyp = Hypothesis(statement="Network partition between services")
    ledger.add_hypothesis(hyp)

    ev = EvidenceItem(
        hypothesis_id=hyp.id,
        event_ids=["evt_01", "evt_02"],
        summary="504 Gateway Timeout observed",
        supports=True,
    )
    ledger.add_evidence(hyp.id, ev)

    assert len(hyp.evidence) == 1
    assert hyp.evidence[0].summary == "504 Gateway Timeout observed"

    # Adding evidence to non-existent hypothesis should raise LedgerIntegrityError
    with pytest.raises(LedgerIntegrityError):
        ledger.add_evidence("non_existent_id", ev)


def test_supported_invariant_violation_no_evidence():
    ledger = EvidenceLedger()
    hyp = Hypothesis(statement="Disk full on host")
    ledger.add_hypothesis(hyp)

    # Attempting to set SUPPORTED without any evidence
    with pytest.raises(LedgerIntegrityError, match="no evidence with supports=True"):
        ledger.update_status(hyp.id, HypothesisStatus.SUPPORTED)


def test_supported_invariant_violation_no_supporting_evidence():
    ledger = EvidenceLedger()
    hyp = Hypothesis(statement="Disk full on host")
    ledger.add_hypothesis(hyp)

    # Has evidence, but supports=False
    ev = EvidenceItem(
        hypothesis_id=hyp.id,
        event_ids=["evt_01"],
        summary="Disk usage is only 30%",
        supports=False,
    )
    ledger.add_evidence(hyp.id, ev)

    with pytest.raises(LedgerIntegrityError, match="no evidence with supports=True"):
        ledger.update_status(hyp.id, HypothesisStatus.SUPPORTED)


def test_supported_invariant_violation_empty_event_ids():
    ledger = EvidenceLedger()
    hyp = Hypothesis(statement="Disk full on host")
    ledger.add_hypothesis(hyp)

    # Has supporting evidence, but event_ids is empty
    ev = EvidenceItem(
        hypothesis_id=hyp.id,
        event_ids=[],
        summary="Rumor says disk was full",
        supports=True,
    )
    ledger.add_evidence(hyp.id, ev)

    with pytest.raises(LedgerIntegrityError, match="no evidence with non-empty event_ids"):
        ledger.update_status(hyp.id, HypothesisStatus.SUPPORTED)


def test_supported_with_proper_evidence():
    ledger = EvidenceLedger()
    hyp = Hypothesis(statement="Database connection pool exhausted")
    ledger.add_hypothesis(hyp)

    ev = EvidenceItem(
        hypothesis_id=hyp.id,
        event_ids=["evt_01", "evt_02"],
        summary="Connection pool 100% full errors",
        supports=True,
    )
    ledger.add_evidence(hyp.id, ev)

    ledger.update_status(hyp.id, HypothesisStatus.SUPPORTED, confidence=0.92)
    assert hyp.status == HypothesisStatus.SUPPORTED
    assert hyp.confidence == 0.92
    assert ledger.get_leading_hypothesis() == hyp


def test_refuted_hypotheses_preserved():
    ledger = EvidenceLedger()
    hyp1 = Hypothesis(statement="Bad DNS resolution", confidence=0.2)
    hyp2 = Hypothesis(statement="OOM killed container", confidence=0.8)
    ledger.add_hypothesis(hyp1)
    ledger.add_hypothesis(hyp2)

    ledger.mark_refuted(hyp1.id, reason="DNS query latency was < 1ms")
    assert hyp1.status == HypothesisStatus.REFUTED
    assert hyp1.critic_notes == "DNS query latency was < 1ms"

    # Refuted hypothesis is still in all hypotheses, but not in open hypotheses
    assert len(ledger.get_all_hypotheses()) == 2
    assert len(ledger.get_open_hypotheses()) == 1
    assert ledger.get_open_hypotheses()[0].id == hyp2.id

    # Leading hypothesis ignores refuted hypotheses
    leading = ledger.get_leading_hypothesis()
    assert leading is not None
    assert leading.id == hyp2.id


def test_temporal_order_validation():
    ledger = EvidenceLedger()
    symptom_time = datetime(2024, 1, 15, 10, 30, 0)
    hyp = Hypothesis(statement="Slow database queries cause timeout")
    ledger.add_hypothesis(hyp)

    # No evidence timestamps -> returns True
    assert ledger.validate_temporal_order(hyp.id, symptom_time) is True

    # Cause happens BEFORE symptom -> True
    cause_time_before = symptom_time - timedelta(minutes=5)
    ev_before = EvidenceItem(
        hypothesis_id=hyp.id,
        event_ids=["evt_pre"],
        summary="DB slow queries started",
        supports=True,
        earliest_timestamp=cause_time_before,
    )
    ledger.add_evidence(hyp.id, ev_before)
    assert ledger.validate_temporal_order(hyp.id, symptom_time) is True

    # Test another hypothesis where cause only happens AFTER symptom -> False
    hyp_late = Hypothesis(statement="Recovery script caused outage")
    ledger.add_hypothesis(hyp_late)
    cause_time_after = symptom_time + timedelta(minutes=10)
    ev_after = EvidenceItem(
        hypothesis_id=hyp_late.id,
        event_ids=["evt_post"],
        summary="Recovery script executed",
        supports=True,
        earliest_timestamp=cause_time_after,
    )
    ledger.add_evidence(hyp_late.id, ev_after)
    assert ledger.validate_temporal_order(hyp_late.id, symptom_time) is False


def test_to_summary():
    ledger = EvidenceLedger()
    assert ledger.to_summary() == "Ledger is empty."

    hyp = Hypothesis(statement="DB connection exhaustion", status=HypothesisStatus.TESTING)
    ledger.add_hypothesis(hyp)
    summary = ledger.to_summary()
    assert "DB connection exhaustion" in summary
    assert "TESTING" in summary
