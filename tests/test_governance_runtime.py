from datetime import date

import pytest

from src.core.config import GovernanceAutomationConfig
from src.core.config import GovernanceConfig
from src.governance.models import GovernanceDecision


def _build_draft(selected_strategy_id: str = "risk_adjusted_momentum") -> GovernanceDecision:
    return GovernanceDecision(
        decision_date=date(2026, 3, 24),
        current_strategy_id="trend_momentum",
        selected_strategy_id=selected_strategy_id,
        previous_strategy_id="trend_momentum",
        fallback_strategy_id="trend_momentum",
        decision_type="switch",
    )


def test_runtime_prefers_latest_published_governance_strategy():
    from src.governance.runtime import resolve_active_strategy_id
    from src.storage.repositories import GovernanceRepository

    repo = GovernanceRepository()
    try:
        draft = repo.save_draft(_build_draft())
        repo.approve(draft.id, approved_by="tester")
        repo.publish(draft.id)

        strategy_id = resolve_active_strategy_id(
            default_strategy_id="trend_momentum",
            repo=repo,
        )

        assert strategy_id == "risk_adjusted_momentum"
    finally:
        repo.close()


def test_runtime_falls_back_when_latest_published_strategy_is_unsupported():
    from src.governance.runtime import resolve_active_strategy_id
    from src.storage.repositories import GovernanceRepository

    repo = GovernanceRepository()
    try:
        draft = repo.save_draft(_build_draft(selected_strategy_id="unsupported_strategy"))
        repo.approve(draft.id, approved_by="tester")
        repo.publish(draft.id)

        strategy_id = resolve_active_strategy_id(
            default_strategy_id="trend_momentum",
            repo=repo,
        )

        assert strategy_id == "trend_momentum"
    finally:
        repo.close()


def test_publish_decision_rejects_unapproved_draft_when_manual_approval_is_required():
    from src.governance.publisher import publish_decision
    from src.storage.repositories import GovernanceRepository

    repo = GovernanceRepository()
    try:
        draft = repo.save_draft(_build_draft())

        with pytest.raises(ValueError, match="manual approval"):
            publish_decision(
                decision_id=draft.id,
                approved_by="ops",
                repo=repo,
                policy=GovernanceConfig(manual_approval_required=True),
            )
    finally:
        repo.close()


def test_publish_decision_rejects_blocked_draft_when_automation_is_enabled():
    from src.governance.publisher import publish_decision
    from src.storage.repositories import GovernanceRepository

    repo = GovernanceRepository()
    try:
        draft = repo.save_draft(_build_draft())
        repo.set_review_status(draft.id, review_status="blocked", blocked_reasons=["SUMMARY_STALE"])
        repo.approve(draft.id, approved_by="ops")

        with pytest.raises(ValueError, match="review_status"):
            publish_decision(
                decision_id=draft.id,
                approved_by="ops",
                repo=repo,
                policy=GovernanceConfig(manual_approval_required=True),
            )
    finally:
        repo.close()


def test_publish_decision_allows_blocked_draft_when_automation_is_disabled():
    from src.governance.publisher import publish_decision
    from src.storage.repositories import GovernanceRepository

    repo = GovernanceRepository()
    try:
        draft = repo.save_draft(_build_draft())
        repo.set_review_status(draft.id, review_status="blocked", blocked_reasons=["SUMMARY_STALE"])
        repo.approve(draft.id, approved_by="ops")

        published = publish_decision(
            decision_id=draft.id,
            approved_by="ops",
            repo=repo,
            policy=GovernanceConfig(
                manual_approval_required=True,
                automation=GovernanceAutomationConfig(enabled=False),
            ),
        )

        assert published.status == "published"
    finally:
        repo.close()
