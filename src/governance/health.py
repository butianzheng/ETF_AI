"""治理健康巡检。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from pathlib import Path
from typing import Any

from src.core.config import GovernanceConfig
from src.governance.models import GovernanceDecision
from src.governance.models import GovernanceIncident
from src.storage.repositories import GovernanceRepository


@dataclass
class GovernanceHealthResult:
    incidents: list[GovernanceIncident]
    rollback_recommendation: GovernanceDecision | None


def _load_daily_reports(report_dir: str | Path) -> list[dict[str, Any]]:
    report_dir = Path(report_dir)
    reports: list[dict[str, Any]] = []
    for path in sorted(report_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        payload["_report_date"] = path.stem
        reports.append(payload)
    return reports


def _active_strategy_id(report: dict[str, Any]) -> str | None:
    report_output = report.get("report_output") or {}
    data = report_output.get("data") or {}
    return data.get("active_strategy_id")


def _risk_level(report: dict[str, Any]) -> str | None:
    return (report.get("risk_output") or {}).get("risk_level")


def _execution_status(report: dict[str, Any]) -> str | None:
    return (report.get("execution_result") or {}).get("status")


def _rebalance_requested(report: dict[str, Any]) -> bool:
    return bool((report.get("strategy_result") or {}).get("rebalance"))


def _maybe_add_incident(
    repo: GovernanceRepository,
    incidents: list[GovernanceIncident],
    incident: GovernanceIncident | None,
) -> None:
    if incident is None:
        return
    incidents.append(repo.save_incident(incident))


def check_governance_health(
    report_dir: str | Path,
    repo: GovernanceRepository,
    policy: GovernanceConfig,
    create_rollback_draft: bool = False,
    summary_path: str | Path | None = None,
) -> GovernanceHealthResult:
    reports = _load_daily_reports(report_dir)
    latest_published = repo.get_latest_published()
    incidents: list[GovernanceIncident] = []

    latest_report = reports[-1] if reports else None
    if latest_report is not None and latest_published is not None:
        latest_active_strategy_id = _active_strategy_id(latest_report)
        if latest_active_strategy_id and latest_active_strategy_id != latest_published.selected_strategy_id:
            _maybe_add_incident(
                repo,
                incidents,
                GovernanceIncident(
                    incident_date=date.today(),
                    incident_type="STRATEGY_DRIFT",
                    severity="critical",
                    strategy_id=latest_published.selected_strategy_id,
                    reason_codes=["ACTIVE_STRATEGY_MISMATCH"],
                    evidence={
                        "latest_active_strategy_id": latest_active_strategy_id,
                        "published_strategy_id": latest_published.selected_strategy_id,
                        "report_date": latest_report["_report_date"],
                    },
                ),
            )

    streak = policy.automation.risk_breach_streak
    recent_reports = reports[-streak:] if streak > 0 else []
    if len(recent_reports) >= streak and recent_reports:
        recent_levels = [_risk_level(report) for report in recent_reports]
        if all(level in {"orange", "red"} for level in recent_levels):
            _maybe_add_incident(
                repo,
                incidents,
                GovernanceIncident(
                    incident_date=date.today(),
                    incident_type="RISK_BREACH",
                    severity="critical",
                    strategy_id=latest_published.selected_strategy_id if latest_published else None,
                    reason_codes=["RISK_BREACH_STREAK"],
                    evidence={
                        "risk_levels": recent_levels,
                        "report_dates": [report["_report_date"] for report in recent_reports],
                    },
                ),
            )

    if latest_report is not None:
        latest_execution_status = _execution_status(latest_report)
        if _rebalance_requested(latest_report) and latest_execution_status in {"rejected", "failed"}:
            _maybe_add_incident(
                repo,
                incidents,
                GovernanceIncident(
                    incident_date=date.today(),
                    incident_type="EXECUTION_FAILURE",
                    severity="critical",
                    strategy_id=latest_published.selected_strategy_id if latest_published else None,
                    reason_codes=["REBALANCE_EXECUTION_FAILED"],
                    evidence={
                        "execution_status": latest_execution_status,
                        "report_date": latest_report["_report_date"],
                    },
                ),
            )

    freshness_limit = policy.automation.max_summary_age_days
    if latest_published is not None:
        if (date.today() - latest_published.decision_date).days > freshness_limit:
            _maybe_add_incident(
                repo,
                incidents,
                GovernanceIncident(
                    incident_date=date.today(),
                    incident_type="GOVERNANCE_STALE",
                    severity="warning",
                    strategy_id=latest_published.selected_strategy_id,
                    reason_codes=["PUBLISHED_DECISION_STALE"],
                    evidence={"decision_date": latest_published.decision_date.isoformat()},
                ),
            )

    summary_file = Path(summary_path) if summary_path is not None else None
    if summary_file is not None and summary_file.exists():
        summary = json.loads(summary_file.read_text(encoding="utf-8"))
        report_summaries = summary.get("report_summaries") or []
        if report_summaries:
            latest_summary_date = max(item["report_date"] for item in report_summaries if item.get("report_date"))
            if (date.today() - date.fromisoformat(latest_summary_date)).days > freshness_limit:
                _maybe_add_incident(
                    repo,
                    incidents,
                    GovernanceIncident(
                        incident_date=date.today(),
                        incident_type="GOVERNANCE_STALE",
                        severity="warning",
                        strategy_id=latest_published.selected_strategy_id if latest_published else None,
                        reason_codes=["RESEARCH_SUMMARY_STALE"],
                        evidence={"latest_summary_date": latest_summary_date},
                    ),
                )

    rollback_recommendation: GovernanceDecision | None = None
    if create_rollback_draft and latest_published is not None and any(item.severity == "critical" for item in incidents):
        rollback_recommendation = repo.save_draft(
            GovernanceDecision(
                decision_date=date.today(),
                current_strategy_id=latest_published.selected_strategy_id,
                selected_strategy_id=latest_published.previous_strategy_id or latest_published.fallback_strategy_id,
                previous_strategy_id=latest_published.selected_strategy_id,
                fallback_strategy_id=latest_published.fallback_strategy_id,
                decision_type="fallback",
                source_report_date=latest_report["_report_date"] if latest_report else None,
                review_status="ready",
                reason_codes=["HEALTH_CHECK_RECOMMENDS_ROLLBACK"],
                evidence={"incident_types": [item.incident_type for item in incidents]},
            )
        )

    return GovernanceHealthResult(
        incidents=incidents,
        rollback_recommendation=rollback_recommendation,
    )
