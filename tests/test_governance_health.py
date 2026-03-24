import json
from datetime import date
from datetime import timedelta
from pathlib import Path

from src.core.config import GovernanceConfig
from src.governance.models import GovernanceDecision


def _write_daily_report(
    path: Path,
    active_strategy_id: str,
    risk_level: str,
    execution_status: str = "filled",
    rebalance: bool = False,
) -> None:
    path.write_text(
        json.dumps(
            {
                "status": "ok",
                "strategy_result": {
                    "current_position": None,
                    "target_position": "510500",
                    "rebalance": rebalance,
                },
                "risk_output": {"risk_level": risk_level},
                "execution_result": {"status": execution_status, "action": "BUY"},
                "report_output": {
                    "summary": "health test",
                    "data": {"active_strategy_id": active_strategy_id},
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _publish_risk_adjusted(repo) -> None:
    draft = repo.save_draft(
        GovernanceDecision(
            decision_date=date.today(),
            current_strategy_id="trend_momentum",
            selected_strategy_id="risk_adjusted_momentum",
            previous_strategy_id="trend_momentum",
            fallback_strategy_id="trend_momentum",
            decision_type="switch",
            review_status="ready",
        )
    )
    repo.approve(draft.id, approved_by="tester")
    repo.publish(draft.id)


def test_governance_health_opens_incidents_for_strategy_drift_and_risk_breach(tmp_path):
    from src.governance.health import check_governance_health
    from src.storage.repositories import GovernanceRepository

    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    _write_daily_report(
        daily_dir / f"{(date.today() - timedelta(days=1)).isoformat()}.json",
        active_strategy_id="trend_momentum",
        risk_level="orange",
    )
    _write_daily_report(
        daily_dir / f"{date.today().isoformat()}.json",
        active_strategy_id="trend_momentum",
        risk_level="red",
    )

    repo = GovernanceRepository()
    try:
        _publish_risk_adjusted(repo)

        result = check_governance_health(
            report_dir=daily_dir,
            repo=repo,
            policy=GovernanceConfig(),
        )

        assert {item.incident_type for item in result.incidents} == {"STRATEGY_DRIFT", "RISK_BREACH"}
    finally:
        repo.close()


def test_governance_health_creates_fallback_recommendation_for_critical_incident(tmp_path):
    from src.governance.health import check_governance_health
    from src.storage.repositories import GovernanceRepository

    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    _write_daily_report(
        daily_dir / f"{date.today().isoformat()}.json",
        active_strategy_id="trend_momentum",
        risk_level="red",
    )

    repo = GovernanceRepository()
    try:
        _publish_risk_adjusted(repo)

        result = check_governance_health(
            report_dir=daily_dir,
            repo=repo,
            policy=GovernanceConfig(),
            create_rollback_draft=True,
        )

        assert result.rollback_recommendation is not None
        assert result.rollback_recommendation.decision_type == "fallback"
        assert result.rollback_recommendation.selected_strategy_id == "trend_momentum"
    finally:
        repo.close()
