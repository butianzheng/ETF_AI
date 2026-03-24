import json
from datetime import date
from pathlib import Path

from src.governance.models import GovernanceIncident
from src.governance.models import GovernanceDecision
from src.report_portal import build_report_portal, collect_daily_report_summaries
from src.storage.repositories import GovernanceRepository


def _write_daily_report(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "status": "ok",
                "data_qa_output": {"status": "ok"},
                "strategy_result": {
                    "current_position": None,
                    "target_position": "510500",
                    "rebalance": True,
                },
                "risk_output": {"risk_level": "yellow"},
                "execution_result": {"status": "filled", "action": "BUY"},
                "report_output": {
                    "summary": "建议调仓并已模拟执行",
                    "data": {"active_strategy_id": "trend_momentum"},
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    path.with_suffix(".md").write_text("# Daily Report", encoding="utf-8")


def _write_research_report(path: Path) -> None:
    path.write_text(
        json.dumps(
            {
                "comparison_rows": [
                    {
                        "name": "biweekly_rebalance",
                        "candidate_name": "biweekly_rebalance",
                        "strategy_id": "risk_adjusted_momentum",
                        "description": "提高调仓频率",
                        "overrides": {"rebalance_frequency": "biweekly"},
                        "annual_return": 0.28,
                        "sharpe": 1.5,
                        "max_drawdown": -0.11,
                        "composite_score": 1.5,
                    }
                ],
                "research_output": {
                    "ranked_candidates": [
                        {
                            "name": "biweekly_rebalance",
                            "candidate_name": "biweekly_rebalance",
                            "strategy_id": "risk_adjusted_momentum",
                            "description": "提高调仓频率",
                            "overrides": {"rebalance_frequency": "biweekly"},
                            "annual_return": 0.28,
                            "sharpe": 1.5,
                            "max_drawdown": -0.11,
                            "composite_score": 1.5,
                        }
                    ],
                    "recommendation": "优先复核 biweekly_rebalance",
                    "overfit_risk": "low",
                    "summary": "研究表现稳定",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_collect_daily_report_summaries(tmp_path):
    daily_dir = tmp_path / "daily"
    daily_dir.mkdir()
    _write_daily_report(daily_dir / "2026-03-11.json")

    rows = collect_daily_report_summaries(daily_dir)

    assert len(rows) == 1
    assert rows[0]["target_position"] == "510500"
    assert rows[0]["execution_status"] == "filled"
    assert rows[0]["active_strategy_id"] == "trend_momentum"


def test_build_report_portal(tmp_path):
    daily_dir = tmp_path / "daily"
    research_dir = tmp_path / "research"
    output_dir = tmp_path / "reports"
    daily_dir.mkdir()
    research_dir.mkdir()
    _write_daily_report(daily_dir / "2026-03-11.json")
    _write_research_report(research_dir / "2026-03-11.json")
    repo = GovernanceRepository()
    try:
        draft = repo.save_draft(
            GovernanceDecision(
                decision_date=date(2026, 3, 24),
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

        repo.save_draft(
            GovernanceDecision(
                decision_date=date(2026, 3, 24),
                current_strategy_id="risk_adjusted_momentum",
                selected_strategy_id="trend_momentum",
                previous_strategy_id="risk_adjusted_momentum",
                fallback_strategy_id="trend_momentum",
                decision_type="fallback",
                review_status="blocked",
                blocked_reasons=["OPEN_CRITICAL_INCIDENT"],
                reason_codes=["HEALTH_CHECK_RECOMMENDS_ROLLBACK"],
            )
        )
        repo.save_incident(
            GovernanceIncident(
                incident_date=date(2026, 3, 24),
                incident_type="RISK_BREACH",
                severity="critical",
                strategy_id="risk_adjusted_momentum",
                reason_codes=["RISK_BREACH_STREAK"],
            )
        )
    finally:
        repo.close()

    result = build_report_portal(daily_dir=daily_dir, research_dir=research_dir, output_dir=output_dir)

    assert Path(result["output_paths"]["html"]).exists()
    assert Path(result["output_paths"]["json"]).exists()
    assert result["governance_summary"]["latest_published"]["selected_strategy_id"] == "risk_adjusted_momentum"
    assert result["governance_summary"]["latest_draft"]["review_status"] == "blocked"
    assert result["governance_summary"]["open_incident_count"] == 1
    assert result["governance_summary"]["highest_open_incident_severity"] == "critical"
    assert result["governance_summary"]["latest_rollback_recommendation"]["selected_strategy_id"] == "trend_momentum"
    html = Path(result["output_paths"]["html"]).read_text(encoding="utf-8")
    assert "日报与研究统一门户" in html
    assert "研究历史总览" in html
    assert "2026-03-11" in html
    assert "trend_momentum" in html
    assert "治理决策" in html
    assert "published" in html
    assert "review_status" in html
    assert "blocked" in html
    assert "open incidents" in html
    assert "OPEN_CRITICAL_INCIDENT" in html
