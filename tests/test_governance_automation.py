import json
from datetime import date
from datetime import timedelta

from src.core.config import GovernanceConfig
from src.governance.models import GovernanceDecision
from src.governance.models import GovernanceIncident


def _write_summary(tmp_path, report_date: date, report_count: int = 4):
    payload = {
        "report_count": report_count,
        "report_summaries": [
            {
                "report_date": report_date.isoformat(),
                "candidate_count": 2,
                "top_candidate_name": "risk_adjusted",
                "top_candidate_strategy_id": "risk_adjusted_momentum",
                "recommendation": "promote challenger",
                "overfit_risk": "low",
                "summary": "summary",
                "top_annual_return": 0.24,
                "top_sharpe": 1.42,
            }
        ],
        "candidate_leaderboard": [
            {
                "name": "risk_adjusted",
                "strategy_id": "risk_adjusted_momentum",
                "appearances": 4,
                "top1_count": 3,
                "avg_annual_return": 0.24,
                "avg_sharpe": 1.42,
                "avg_max_drawdown": -0.08,
                "last_seen": report_date.isoformat(),
            },
            {
                "name": "baseline",
                "strategy_id": "trend_momentum",
                "appearances": 4,
                "top1_count": 1,
                "avg_annual_return": 0.16,
                "avg_sharpe": 1.05,
                "avg_max_drawdown": -0.10,
                "last_seen": report_date.isoformat(),
            },
        ],
    }
    summary_path = tmp_path / "research_summary.json"
    summary_path.write_text(json.dumps(payload), encoding="utf-8")
    return summary_path


def _publish_recent_baseline(repo) -> None:
    draft = repo.save_draft(
        GovernanceDecision(
            decision_date=date.today() - timedelta(days=3),
            current_strategy_id="trend_momentum",
            selected_strategy_id="trend_momentum",
            previous_strategy_id="trend_momentum",
            fallback_strategy_id="trend_momentum",
            decision_type="keep",
            review_status="ready",
        )
    )
    repo.approve(draft.id, approved_by="tester")
    repo.publish(draft.id)


def test_run_governance_cycle_marks_ready_draft_for_fresh_summary(tmp_path):
    from src.governance.automation import run_governance_cycle
    from src.storage.repositories import GovernanceRepository

    repo = GovernanceRepository()
    try:
        summary_path = _write_summary(tmp_path, report_date=date.today())

        result = run_governance_cycle(
            summary_path=summary_path,
            policy=GovernanceConfig(),
            repo=repo,
            current_strategy_id="trend_momentum",
        )

        assert result.decision.review_status == "ready"
        assert result.decision.blocked_reasons == []
        assert result.decision.source_report_date == date.today().isoformat()
    finally:
        repo.close()


def test_run_governance_cycle_deduplicates_same_summary(tmp_path):
    from src.governance.automation import run_governance_cycle
    from src.storage.repositories import GovernanceRepository

    repo = GovernanceRepository()
    try:
        summary_path = _write_summary(tmp_path, report_date=date.today())

        first = run_governance_cycle(
            summary_path=summary_path,
            policy=GovernanceConfig(),
            repo=repo,
            current_strategy_id="trend_momentum",
        )
        second = run_governance_cycle(
            summary_path=summary_path,
            policy=GovernanceConfig(),
            repo=repo,
            current_strategy_id="trend_momentum",
        )

        assert first.decision.id == second.decision.id
    finally:
        repo.close()


def test_run_governance_cycle_blocks_stale_summary(tmp_path):
    from src.governance.automation import run_governance_cycle
    from src.storage.repositories import GovernanceRepository

    repo = GovernanceRepository()
    try:
        summary_path = _write_summary(tmp_path, report_date=date.today() - timedelta(days=8))

        result = run_governance_cycle(
            summary_path=summary_path,
            policy=GovernanceConfig(),
            repo=repo,
            current_strategy_id="trend_momentum",
        )

        assert result.decision.review_status == "blocked"
        assert "SUMMARY_STALE" in result.decision.blocked_reasons
    finally:
        repo.close()


def test_run_governance_cycle_blocks_switch_within_cooldown(tmp_path):
    from src.governance.automation import run_governance_cycle
    from src.storage.repositories import GovernanceRepository

    repo = GovernanceRepository()
    try:
        _publish_recent_baseline(repo)
        summary_path = _write_summary(tmp_path, report_date=date.today())

        result = run_governance_cycle(
            summary_path=summary_path,
            policy=GovernanceConfig(),
            repo=repo,
            current_strategy_id="trend_momentum",
        )

        assert result.decision.review_status == "blocked"
        assert "PUBLISH_COOLDOWN" in result.decision.blocked_reasons
    finally:
        repo.close()


def test_run_governance_cycle_blocks_when_open_critical_incident_exists(tmp_path):
    from src.governance.automation import run_governance_cycle
    from src.storage.repositories import GovernanceRepository

    repo = GovernanceRepository()
    try:
        repo.save_incident(
            GovernanceIncident(
                incident_date=date.today(),
                incident_type="RISK_BREACH",
                severity="critical",
                strategy_id="trend_momentum",
            )
        )
        summary_path = _write_summary(tmp_path, report_date=date.today())

        result = run_governance_cycle(
            summary_path=summary_path,
            policy=GovernanceConfig(),
            repo=repo,
            current_strategy_id="trend_momentum",
        )

        assert result.decision.review_status == "blocked"
        assert "OPEN_CRITICAL_INCIDENT" in result.decision.blocked_reasons
    finally:
        repo.close()
