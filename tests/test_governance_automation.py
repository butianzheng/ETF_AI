import json
from datetime import date
from datetime import timedelta

from src.core.config import GovernanceConfig
from src.governance.models import GovernanceDecision
from src.governance.models import GovernanceIncident
from src.research.regime import RegimeSnapshot


def _build_snapshot(regime_label: str, reason_codes: list[str] | None = None) -> RegimeSnapshot:
    return RegimeSnapshot(
        trade_date=date(2026, 3, 24),
        regime_label=regime_label,  # type: ignore[arg-type]
        regime_score=0.0,
        reason_codes=reason_codes or [],
        metrics_snapshot={"coverage": 5},
    )


def _build_candidate_regime_leaderboard() -> list[dict]:
    return [
        {
            "strategy_id": "risk_adjusted_momentum",
            "regime_label": "risk_on",
            "appearances": 4,
            "avg_observation_count": 60.0,
            "avg_annual_return": 0.25,
            "avg_sharpe": 1.35,
        },
        {
            "strategy_id": "risk_adjusted_momentum",
            "regime_label": "neutral",
            "appearances": 3,
            "avg_observation_count": 42.0,
            "avg_annual_return": 0.03,
            "avg_sharpe": 0.25,
        },
        {
            "strategy_id": "risk_adjusted_momentum",
            "regime_label": "risk_off",
            "appearances": 3,
            "avg_observation_count": 44.0,
            "avg_annual_return": -0.12,
            "avg_sharpe": -0.35,
        },
        {
            "strategy_id": "trend_momentum",
            "regime_label": "risk_on",
            "appearances": 4,
            "avg_observation_count": 58.0,
            "avg_annual_return": 0.18,
            "avg_sharpe": 1.00,
        },
        {
            "strategy_id": "trend_momentum",
            "regime_label": "neutral",
            "appearances": 3,
            "avg_observation_count": 40.0,
            "avg_annual_return": 0.02,
            "avg_sharpe": 0.20,
        },
        {
            "strategy_id": "trend_momentum",
            "regime_label": "risk_off",
            "appearances": 3,
            "avg_observation_count": 41.0,
            "avg_annual_return": -0.09,
            "avg_sharpe": -0.30,
        },
    ]


def _write_summary(
    tmp_path,
    report_date: date,
    report_count: int = 4,
    leader_strategy_id: str = "risk_adjusted_momentum",
    filename: str = "research_summary.json",
):
    candidate_leaderboard = [
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
    ]
    if leader_strategy_id == "trend_momentum":
        candidate_leaderboard = [candidate_leaderboard[1], candidate_leaderboard[0]]

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
        "candidate_leaderboard": candidate_leaderboard,
        "candidate_regime_leaderboard": _build_candidate_regime_leaderboard(),
    }
    summary_path = tmp_path / filename
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
            current_regime_snapshot=_build_snapshot("risk_on"),
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
            current_regime_snapshot=_build_snapshot("risk_on"),
        )
        second = run_governance_cycle(
            summary_path=summary_path,
            policy=GovernanceConfig(),
            repo=repo,
            current_strategy_id="trend_momentum",
            current_regime_snapshot=_build_snapshot("risk_on"),
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
            current_regime_snapshot=_build_snapshot("risk_on"),
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
            current_regime_snapshot=_build_snapshot("risk_on"),
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
            current_regime_snapshot=_build_snapshot("risk_on"),
        )

        assert result.decision.review_status == "blocked"
        assert "OPEN_CRITICAL_INCIDENT" in result.decision.blocked_reasons
    finally:
        repo.close()


def test_run_governance_cycle_blocks_selected_strategy_on_regime_mismatch(tmp_path):
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
            current_regime_snapshot=_build_snapshot("risk_off"),
        )

        assert result.decision.decision_type == "switch"
        assert result.decision.review_status == "blocked"
        assert "SELECTED_STRATEGY_REGIME_MISMATCH" in result.decision.blocked_reasons
        assert result.decision.evidence["regime_gate"]["gate_status"] == "blocked"
        assert result.decision.evidence["regime_gate"]["selected_strategy_id"] == "risk_adjusted_momentum"
        assert result.decision.evidence["regime_gate"]["sample_thresholds"]["min_appearances"] == 2
        assert result.decision.evidence["regime_gate"]["sample_thresholds"]["min_avg_observation_count"] == 20
    finally:
        repo.close()


def test_run_governance_cycle_skipped_regime_gate_records_evidence_without_blocking(tmp_path):
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
            current_regime_snapshot=_build_snapshot(
                "risk_off",
                reason_codes=["INSUFFICIENT_POOL_COVERAGE"],
            ),
        )

        assert result.decision.review_status == "ready"
        assert "SELECTED_STRATEGY_REGIME_MISMATCH" not in result.decision.blocked_reasons
        assert result.decision.evidence["regime_gate"]["gate_status"] == "skipped"
        assert result.decision.evidence["regime_gate"]["skip_reason"] == "CURRENT_REGIME_UNCERTAIN"
        assert result.decision.evidence["regime_gate"]["selected_strategy_id"] == "risk_adjusted_momentum"
        assert result.decision.evidence["regime_gate"]["sample_thresholds"]["min_appearances"] == 2
        assert result.decision.evidence["regime_gate"]["sample_thresholds"]["min_avg_observation_count"] == 20
    finally:
        repo.close()


def test_run_governance_cycle_refreshes_regime_gate_evidence_for_same_summary(tmp_path):
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
            current_regime_snapshot=_build_snapshot("risk_on"),
        )
        second = run_governance_cycle(
            summary_path=summary_path,
            policy=GovernanceConfig(),
            repo=repo,
            current_strategy_id="trend_momentum",
            current_regime_snapshot=_build_snapshot("risk_off"),
        )

        assert first.decision.id == second.decision.id
        assert first.decision.evidence["regime_gate"]["current_regime"]["regime_label"] == "risk_on"
        assert second.decision.review_status == "blocked"
        assert "SELECTED_STRATEGY_REGIME_MISMATCH" in second.decision.blocked_reasons
        assert second.decision.evidence["regime_gate"]["current_regime"]["regime_label"] == "risk_off"
    finally:
        repo.close()


def test_run_governance_cycle_applies_gate_to_keep_and_fallback_targets(tmp_path):
    from src.governance.automation import run_governance_cycle
    from src.storage.repositories import GovernanceRepository

    repo = GovernanceRepository()
    try:
        keep_summary_path = _write_summary(
            tmp_path,
            report_date=date.today(),
            leader_strategy_id="trend_momentum",
            filename="keep_summary.json",
        )
        fallback_summary_path = _write_summary(
            tmp_path,
            report_date=date.today(),
            filename="fallback_summary.json",
        )

        keep_result = run_governance_cycle(
            summary_path=keep_summary_path,
            policy=GovernanceConfig(),
            repo=repo,
            current_strategy_id="trend_momentum",
            current_regime_snapshot=_build_snapshot("risk_off"),
        )
        fallback_result = run_governance_cycle(
            summary_path=fallback_summary_path,
            policy=GovernanceConfig(),
            repo=repo,
            current_strategy_id="retired_strategy",
            current_regime_snapshot=_build_snapshot("risk_off"),
        )

        assert keep_result.decision.decision_type == "keep"
        assert keep_result.decision.selected_strategy_id == "trend_momentum"
        assert "SELECTED_STRATEGY_REGIME_MISMATCH" in keep_result.decision.blocked_reasons
        assert fallback_result.decision.decision_type == "fallback"
        assert fallback_result.decision.selected_strategy_id == "trend_momentum"
        assert "SELECTED_STRATEGY_REGIME_MISMATCH" in fallback_result.decision.blocked_reasons
    finally:
        repo.close()


def test_run_governance_cycle_builds_uncertain_snapshot_when_current_regime_is_unavailable(
    tmp_path,
    monkeypatch,
):
    from src.governance import automation
    from src.storage.repositories import GovernanceRepository

    repo = GovernanceRepository()
    try:
        summary_path = _write_summary(tmp_path, report_date=date.today())
        monkeypatch.setattr(automation, "resolve_current_regime", lambda **_: None)

        result = automation.run_governance_cycle(
            summary_path=summary_path,
            policy=GovernanceConfig(),
            repo=repo,
            current_strategy_id="trend_momentum",
        )

        assert result.decision.review_status == "ready"
        assert "SELECTED_STRATEGY_REGIME_MISMATCH" not in result.decision.blocked_reasons
        assert result.decision.evidence["regime_gate"]["gate_status"] == "skipped"
        assert result.decision.evidence["regime_gate"]["skip_reason"] == "CURRENT_REGIME_UNCERTAIN"
        assert "INSUFFICIENT_POOL_COVERAGE" in result.decision.evidence["regime_gate"]["current_regime"]["reason_codes"]
    finally:
        repo.close()
