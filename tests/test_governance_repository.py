from datetime import date

from src.core.config import ConfigLoader
from src.governance.models import GovernanceIncident
from src.governance.models import GovernanceDecision


def _build_switch_decision() -> GovernanceDecision:
    return GovernanceDecision(
        decision_date=date(2026, 3, 24),
        current_strategy_id="trend_momentum",
        selected_strategy_id="risk_adjusted_momentum",
        fallback_strategy_id="trend_momentum",
        decision_type="switch",
        summary_hash="summary-hash-001",
        source_report_date="2026-03-24",
        reason_codes=["CHALLENGER_OUTPERFORMED"],
        evidence={"avg_sharpe": 1.42},
    )


def _build_incident() -> GovernanceIncident:
    return GovernanceIncident(
        incident_date=date(2026, 3, 24),
        incident_type="SUMMARY_STALE",
        severity="warning",
        strategy_id="trend_momentum",
        reason_codes=["SUMMARY_TOO_OLD"],
        evidence={"summary_age_days": 9},
    )


def test_strategy_config_loads_governance_regime_gate_policy():
    strategy_config = ConfigLoader().load_strategy_config()

    assert strategy_config.governance.automation.regime_gate.enabled is True
    assert strategy_config.governance.automation.regime_gate.min_appearances == 2
    assert strategy_config.governance.automation.regime_gate.min_avg_observation_count == 20


def test_governance_decision_defaults_to_pending_review_status():
    decision = _build_switch_decision()

    assert decision.review_status == "pending"
    assert decision.blocked_reasons == []


def test_governance_repository_tracks_publish_and_rollback():
    from src.storage.repositories import GovernanceRepository

    repo = GovernanceRepository()
    try:
        draft = repo.save_draft(_build_switch_decision())
        assert draft.id is not None
        assert draft.status == "draft"
        assert draft.review_status == "pending"
        assert draft.blocked_reasons == []

        located = repo.find_draft_by_summary_hash("summary-hash-001")
        assert located is not None
        assert located.id == draft.id

        reviewed = repo.set_review_status(
            draft.id,
            review_status="blocked",
            blocked_reasons=["SELECTED_STRATEGY_REGIME_MISMATCH"],
            evidence={"regime_gate": {"gate_status": "blocked"}},
        )
        assert reviewed.review_status == "blocked"
        assert reviewed.blocked_reasons == ["SELECTED_STRATEGY_REGIME_MISMATCH"]
        assert reviewed.evidence["regime_gate"]["gate_status"] == "blocked"
        assert reviewed.evidence["avg_sharpe"] == 1.42

        approved = repo.approve(draft.id, approved_by="tester")
        assert approved.status == "approved"
        assert approved.approved_by == "tester"
        assert approved.review_status == "blocked"

        published = repo.publish(draft.id)
        assert published.status == "published"
        assert published.selected_strategy_id == "risk_adjusted_momentum"

        latest = repo.get_latest_published()
        assert latest is not None
        assert latest.selected_strategy_id == "risk_adjusted_momentum"

        rollback = repo.rollback_latest(approved_by="ops", reason="manual rollback")
        assert rollback.status == "published"
        assert rollback.decision_type == "fallback"
        assert rollback.selected_strategy_id == "trend_momentum"

        latest_after_rollback = repo.get_latest_published()
        assert latest_after_rollback is not None
        assert latest_after_rollback.selected_strategy_id == "trend_momentum"
    finally:
        repo.close()


def test_governance_repository_tracks_incidents():
    from src.storage.repositories import GovernanceRepository

    repo = GovernanceRepository()
    try:
        incident = repo.save_incident(_build_incident())
        assert incident.id is not None
        assert incident.status == "open"

        incidents = repo.list_open_incidents()
        assert len(incidents) == 1
        assert incidents[0].incident_type == "SUMMARY_STALE"

        resolved = repo.resolve_incident(incident.id)
        assert resolved.status == "resolved"
        assert repo.list_open_incidents() == []
    finally:
        repo.close()
