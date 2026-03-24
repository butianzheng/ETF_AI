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


def _build_pipeline_summary_base(
    research_end_date: date,
    governance_run_date: date,
) -> dict[str, Any]:
    return {
        "research_end_date": research_end_date.isoformat(),
        "governance_run_date": governance_run_date.isoformat(),
    }


def _write_pipeline_summary_artifact(
    research_end_date: date,
    governance_run_date: date,
    research_result: dict[str, Any],
    summary_result: dict[str, Any],
    cycle_result: Any,
    governance_review_path: Path,
) -> Path:
    payload = _build_pipeline_summary_base(
        research_end_date=research_end_date,
        governance_run_date=governance_run_date,
    )
    payload.update(
        {
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
    return _write_json(
        Path("reports/governance/pipeline") / f"{governance_run_date.isoformat()}.json",
        payload,
    )


def _write_partial_pipeline_summary_artifact(
    research_end_date: date,
    governance_run_date: date,
    failed_step: str,
    error: Exception,
) -> Path:
    payload = _build_pipeline_summary_base(
        research_end_date=research_end_date,
        governance_run_date=governance_run_date,
    )
    payload.update(
        {
            "status": "failed",
            "failed_step": failed_step,
            "error": {
                "type": type(error).__name__,
                "message": str(error),
            },
        }
    )
    return _write_json(
        Path("reports/governance/pipeline") / f"{governance_run_date.isoformat()}.json",
        payload,
    )


def run_research_governance_pipeline(
    start_date: date,
    end_date: date,
    candidate_specs: list[dict[str, Any]] | None = None,
    initial_capital: float = 100000.0,
    fee_rate: float = 0.001,
    log_level: str = "INFO",
    fail_on_blocked: bool = False,
) -> dict[str, Any]:
    run_date = date.today()
    current_step = "research"
    try:
        research_result = run_research_pipeline(
            start_date=start_date,
            end_date=end_date,
            candidate_specs=candidate_specs,
            initial_capital=initial_capital,
            fee_rate=fee_rate,
            log_level=log_level,
        )
        current_step = "summary"
        summary_result = aggregate_research_reports(
            report_dir=Path("reports/research"),
            output_dir=Path("reports/research/summary"),
        )
        current_step = "portal_pre_governance"
        build_report_portal(
            daily_dir=Path("reports/daily"),
            research_dir=Path("reports/research"),
            output_dir=Path("reports"),
        )

        current_step = "governance_cycle"
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

        current_step = "governance_cycle_artifact"
        governance_cycle_path = _write_governance_cycle_artifact(run_date, cycle_result)
        current_step = "governance_review_artifact"
        governance_review_path = _write_governance_review_artifact(run_date, cycle_result.decision)
        current_step = "pipeline_summary"
        pipeline_summary_path = _write_pipeline_summary_artifact(
            research_end_date=end_date,
            governance_run_date=run_date,
            research_result=research_result,
            summary_result=summary_result,
            cycle_result=cycle_result,
            governance_review_path=governance_review_path,
        )
        current_step = "portal_final_refresh"
        portal_result = build_report_portal(
            daily_dir=Path("reports/daily"),
            research_dir=Path("reports/research"),
            output_dir=Path("reports"),
        )
    except Exception as exc:
        _write_partial_pipeline_summary_artifact(
            research_end_date=end_date,
            governance_run_date=run_date,
            failed_step=current_step,
            error=exc,
        )
        raise

    exit_code = 0
    if fail_on_blocked and cycle_result.decision.review_status == "blocked":
        exit_code = 2

    return {
        "research_result": research_result,
        "summary_result": summary_result,
        "portal_result": portal_result,
        "cycle_result": cycle_result,
        "governance_cycle_path": str(governance_cycle_path),
        "governance_review_path": str(governance_review_path),
        "pipeline_summary_path": str(pipeline_summary_path),
        "exit_code": exit_code,
    }
