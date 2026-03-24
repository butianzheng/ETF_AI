"""治理自动 review cycle。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from typing import Any

from src.core.config import GovernanceConfig
from src.governance.evaluator import evaluate_governance
from src.governance.models import GovernanceDecision
from src.storage.repositories import GovernanceRepository


@dataclass
class GovernanceCycleResult:
    decision: GovernanceDecision
    summary_hash: str
    created_new: bool


def _load_summary(summary_path: str | Path) -> dict[str, Any]:
    with open(summary_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _compute_summary_hash(summary: dict[str, Any]) -> str:
    normalized = json.dumps(summary, ensure_ascii=False, sort_keys=True)
    return sha256(normalized.encode("utf-8")).hexdigest()


def _extract_source_report_date(summary: dict[str, Any]) -> str | None:
    report_summaries = summary.get("report_summaries") or []
    report_dates = [item.get("report_date") for item in report_summaries if item.get("report_date")]
    if report_dates:
        return max(report_dates)

    leaderboard = summary.get("candidate_leaderboard") or []
    last_seen = [item.get("last_seen") for item in leaderboard if item.get("last_seen")]
    if last_seen:
        return max(last_seen)
    return None


def create_or_update_governance_draft(
    summary: dict[str, Any],
    repo: GovernanceRepository,
    policy: GovernanceConfig,
    current_strategy_id: str | None,
) -> GovernanceCycleResult:
    summary_hash = _compute_summary_hash(summary)
    existing = repo.find_draft_by_summary_hash(summary_hash)
    if existing is not None:
        return GovernanceCycleResult(
            decision=existing,
            summary_hash=summary_hash,
            created_new=False,
        )

    decision = evaluate_governance(
        summary=summary,
        current_strategy_id=current_strategy_id,
        policy=policy,
    )
    decision.summary_hash = summary_hash
    decision.source_report_date = _extract_source_report_date(summary)
    saved = repo.save_draft(decision)
    return GovernanceCycleResult(
        decision=saved,
        summary_hash=summary_hash,
        created_new=True,
    )


def _collect_blocked_reasons(
    summary: dict[str, Any],
    decision: GovernanceDecision,
    repo: GovernanceRepository,
    policy: GovernanceConfig,
) -> list[str]:
    reasons: list[str] = []
    automation = policy.automation

    if automation.require_fresh_summary:
        source_report_date = decision.source_report_date
        if not source_report_date:
            reasons.append("SUMMARY_STALE")
        else:
            age_days = (date.today() - date.fromisoformat(source_report_date)).days
            if age_days > automation.max_summary_age_days:
                reasons.append("SUMMARY_STALE")

    if int(summary.get("report_count", 0) or 0) < automation.min_reports_required:
        reasons.append("INSUFFICIENT_REPORT_COUNT")

    if decision.decision_type == "switch":
        latest_published = repo.get_latest_published()
        if latest_published is not None:
            days_since_last_publish = (decision.decision_date - latest_published.decision_date).days
            if days_since_last_publish < automation.min_days_between_switches:
                reasons.append("PUBLISH_COOLDOWN")

    if automation.block_on_open_incident:
        open_incidents = repo.list_open_incidents()
        if any(item.severity == "critical" for item in open_incidents):
            reasons.append("OPEN_CRITICAL_INCIDENT")

    return reasons


def run_governance_cycle(
    summary_path: str | Path,
    repo: GovernanceRepository,
    policy: GovernanceConfig,
    current_strategy_id: str | None,
) -> GovernanceCycleResult:
    summary = _load_summary(summary_path)
    result = create_or_update_governance_draft(
        summary=summary,
        repo=repo,
        policy=policy,
        current_strategy_id=current_strategy_id,
    )

    if not policy.automation.enabled:
        return result

    blocked_reasons = _collect_blocked_reasons(
        summary=summary,
        decision=result.decision,
        repo=repo,
        policy=policy,
    )
    review_status = "blocked" if blocked_reasons else "ready"
    reviewed = repo.set_review_status(
        result.decision.id,
        review_status=review_status,
        blocked_reasons=blocked_reasons,
    )
    return GovernanceCycleResult(
        decision=reviewed,
        summary_hash=result.summary_hash,
        created_new=result.created_new,
    )
