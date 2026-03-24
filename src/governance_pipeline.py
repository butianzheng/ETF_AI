"""Research-To-Governance 统一编排服务。"""
from __future__ import annotations

from datetime import date
import json
from pathlib import Path
from typing import Any

from src.core.config import config_loader
from src.governance.automation import run_governance_cycle
from src.report_portal import build_report_portal
from src.research_pipeline import run_research_pipeline
from src.research_summary import aggregate_research_reports
from src.storage.repositories import GovernanceRepository


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path.resolve()


def _write_governance_cycle_artifact(run_date: date, cycle_result: Any) -> Path:
    return _write_json(
        Path("reports/governance/cycle") / f"{run_date.isoformat()}.json",
        {
            "decision": cycle_result.decision.model_dump(mode="json"),
            "summary_hash": cycle_result.summary_hash,
            "created_new": cycle_result.created_new,
            "blocked_reasons": cycle_result.decision.blocked_reasons,
        },
    )


def _write_governance_review_artifact(run_date: date, decision: Any) -> Path:
    return _write_json(
        Path("reports/governance") / f"{run_date.isoformat()}.json",
        decision.model_dump(mode="json"),
    )


def _write_pipeline_summary_artifact(
    research_end_date: date,
    governance_run_date: date,
    research_result: dict[str, Any],
    summary_result: dict[str, Any],
    cycle_result: Any,
    governance_review_path: Path,
) -> Path:
    return _write_json(
        Path("reports/governance/pipeline") / f"{governance_run_date.isoformat()}.json",
        {
            "research_end_date": research_end_date.isoformat(),
            "governance_run_date": governance_run_date.isoformat(),
            "steps": {
                "research": {
                    "status": "completed",
                    "output_paths": research_result.get("report_paths", {}),
                },
                "summary": {
                    "status": "completed",
                    "output_paths": {
                        "json": summary_result.get("output_paths", {}).get("json"),
                    },
                },
                "governance_cycle": {
                    "status": "completed",
                    "review_status": cycle_result.decision.review_status,
                    "decision_id": cycle_result.decision.id,
                    "created_new": cycle_result.created_new,
                    "summary_hash": cycle_result.summary_hash,
                },
                "governance_review": {
                    "status": "completed",
                    "output_path": str(governance_review_path),
                },
            },
            "final_decision": {
                "decision_id": cycle_result.decision.id,
                "review_status": cycle_result.decision.review_status,
                "blocked_reasons": cycle_result.decision.blocked_reasons,
                "created_new": cycle_result.created_new,
                "summary_hash": cycle_result.summary_hash,
            },
        },
    )


def run_research_governance_pipeline(
    start_date: date,
    end_date: date,
    candidate_specs: list[dict[str, Any]] | None = None,
    initial_capital: float = 100000.0,
    fee_rate: float = 0.001,
    log_level: str = "INFO",
) -> dict[str, Any]:
    research_result = run_research_pipeline(
        start_date=start_date,
        end_date=end_date,
        candidate_specs=candidate_specs,
        initial_capital=initial_capital,
        fee_rate=fee_rate,
        log_level=log_level,
    )
    summary_result = aggregate_research_reports(
        report_dir=Path("reports/research"),
        output_dir=Path("reports/research/summary"),
    )
    portal_result = build_report_portal(
        daily_dir=Path("reports/daily"),
        research_dir=Path("reports/research"),
        output_dir=Path("reports"),
    )

    run_date = date.today()
    repo = GovernanceRepository()
    try:
        strategy_config = config_loader.load_strategy_config()
        cycle_result = run_governance_cycle(
            summary_path=Path(summary_result["output_paths"]["json"]),
            repo=repo,
            policy=strategy_config.governance,
            current_strategy_id=config_loader.load_production_strategy_id(),
        )
    finally:
        repo.close()

    governance_cycle_path = _write_governance_cycle_artifact(run_date, cycle_result)
    governance_review_path = _write_governance_review_artifact(run_date, cycle_result.decision)
    pipeline_summary_path = _write_pipeline_summary_artifact(
        research_end_date=end_date,
        governance_run_date=run_date,
        research_result=research_result,
        summary_result=summary_result,
        cycle_result=cycle_result,
        governance_review_path=governance_review_path,
    )
    return {
        "research_result": research_result,
        "summary_result": summary_result,
        "portal_result": portal_result,
        "cycle_result": cycle_result,
        "governance_cycle_path": str(governance_cycle_path),
        "governance_review_path": str(governance_review_path),
        "pipeline_summary_path": str(pipeline_summary_path),
        "exit_code": 0,
    }
