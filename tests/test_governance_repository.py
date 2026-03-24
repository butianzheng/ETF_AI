from datetime import date

from src.governance.models import GovernanceDecision


def _build_switch_decision() -> GovernanceDecision:
    return GovernanceDecision(
        decision_date=date(2026, 3, 24),
        current_strategy_id="trend_momentum",
        selected_strategy_id="risk_adjusted_momentum",
        fallback_strategy_id="trend_momentum",
        decision_type="switch",
        reason_codes=["CHALLENGER_OUTPERFORMED"],
        evidence={"avg_sharpe": 1.42},
    )


def test_governance_repository_tracks_publish_and_rollback():
    from src.storage.repositories import GovernanceRepository

    repo = GovernanceRepository()
    try:
        draft = repo.save_draft(_build_switch_decision())
        assert draft.id is not None
        assert draft.status == "draft"

        approved = repo.approve(draft.id, approved_by="tester")
        assert approved.status == "approved"
        assert approved.approved_by == "tester"

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
