"""治理审批、发布与回退服务。"""
from __future__ import annotations

from src.core.config import GovernanceConfig
from src.governance.models import GovernanceDecision
from src.storage.repositories import GovernanceRepository


def publish_decision(
    decision_id: int,
    approved_by: str,
    repo: GovernanceRepository,
    policy: GovernanceConfig,
) -> GovernanceDecision:
    decision = repo.get_by_id(decision_id)
    if decision is None:
        raise ValueError(f"governance decision not found: {decision_id}")

    if policy.manual_approval_required and decision.status != "approved":
        raise ValueError("manual approval is required before publishing governance decision")

    if not policy.manual_approval_required and decision.status == "draft":
        repo.approve(decision_id, approved_by=approved_by)

    return repo.publish(decision_id)


def rollback_latest(
    approved_by: str,
    reason: str,
    repo: GovernanceRepository,
) -> GovernanceDecision:
    return repo.rollback_latest(approved_by=approved_by, reason=reason)
