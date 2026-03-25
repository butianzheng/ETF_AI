"""端到端工作流统一编排入口（Task 1 最小骨架）。"""
from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
import json
from pathlib import Path
import secrets
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.check_governance_health import check_governance_health
from src.core.config import ConfigLoader
from src.governance.publisher import publish_decision
from src.governance_pipeline import run_research_governance_pipeline
from src.main import run_daily_pipeline
from src.research_candidate_config import load_candidate_specs
from src.storage.repositories import GovernanceRepository
from src.workflow.preflight import run_workflow_preflight


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    today = date.today()
    default_start = today - timedelta(days=365)
    parser = argparse.ArgumentParser(description="执行端到端工作流编排")
    parser.add_argument("--start-date", default=default_start.isoformat(), help="开始日期，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", default=today.isoformat(), help="结束日期，格式 YYYY-MM-DD")
    parser.add_argument("--candidate-config", help="研究候选配置文件路径，默认使用 config/research.yaml")
    parser.add_argument("--initial-capital", type=float, default=100000.0, help="初始资金")
    parser.add_argument("--fee-rate", type=float, default=0.001, help="手续费率")
    parser.add_argument("--log-level", default="INFO", help="日志级别")
    parser.add_argument("--fail-on-blocked", action="store_true", help="当治理结果为 blocked 时返回退出码 2")
    parser.add_argument("--preflight-only", action="store_true", help="仅执行预检并输出工作流摘要")
    parser.add_argument("--run-daily", action="store_true", help="是否在 research-governance 前执行 daily run")
    parser.add_argument("--daily-date", default=None, help="daily run 交易日期，格式 YYYY-MM-DD，默认今天")
    parser.add_argument("--daily-execute", action="store_true", help="daily run 通过检查后执行调仓")
    parser.add_argument("--daily-manual-approve", action="store_true", help="daily run 标记人工确认")
    parser.add_argument("--daily-available-cash", type=float, default=100000.0, help="daily run 可用现金")
    parser.add_argument("--publish", action="store_true", help="预留参数，显式授权后才允许发布")
    parser.add_argument("--approved-by", help="发布审批人")
    parser.add_argument(
        "--create-rollback-draft",
        action="store_true",
        help="透传给治理健康巡检，用于发现 critical incident 时生成 rollback draft",
    )
    args = parser.parse_args(argv)
    if args.publish and not args.approved_by:
        parser.error("--publish requires --approved-by")
    return args


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _generate_run_id(now: datetime | None = None) -> str:
    current = now or datetime.now(timezone.utc)
    return f"{current:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"


def _health_payload(result: Any) -> dict[str, Any]:
    incidents = getattr(result, "incidents", [])
    rollback = getattr(result, "rollback_recommendation", None)
    return {
        "incidents": [
            item.model_dump(mode="json") if hasattr(item, "model_dump") else item
            for item in incidents
        ],
        "rollback_recommendation": (
            rollback.model_dump(mode="json") if hasattr(rollback, "model_dump") else rollback
        ),
    }


def _write_health_report(result: Any, stage: str | None = None) -> str:
    output_dir = Path("reports/governance/health")
    output_dir.mkdir(parents=True, exist_ok=True)
    suffix = f"_{stage}" if stage else ""
    output_path = output_dir / f"{date.today().isoformat()}{suffix}.json"
    output_path.write_text(
        json.dumps(_health_payload(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(output_path)


def _write_workflow_summary(payload: dict[str, Any]) -> Path:
    summary_path = Path("reports/workflow/end_to_end_workflow_summary.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary_path


def _write_workflow_manifest(payload: dict[str, Any]) -> Path:
    run_id = str(payload["run_id"])
    manifest_path = Path("reports/workflow/runs") / run_id / "workflow_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    return manifest_path


def _write_workflow_artifacts(payload: dict[str, Any]) -> Path:
    manifest_path = _write_workflow_manifest(payload)
    payload["workflow_manifest_path"] = str(manifest_path)
    manifest_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return _write_workflow_summary(payload)


def _finalize_workflow_run(payload: dict[str, Any], *, workflow_status: str) -> None:
    _write_workflow_artifacts(payload)
    print(f"workflow_status={workflow_status}")
    publish_executed = bool(payload.get("publish_result", {}).get("executed"))
    print(f"publish_executed={'true' if publish_executed else 'false'}")


def _research_governance_payload(pipeline_result: dict[str, Any]) -> dict[str, Any]:
    cycle_result = pipeline_result.get("cycle_result")
    decision = getattr(cycle_result, "decision", None)
    research_report = (
        pipeline_result.get("research_result", {})
        .get("report_paths", {})
        .get("json")
    )
    summary_json = (
        pipeline_result.get("summary_result", {})
        .get("output_paths", {})
        .get("json")
    )
    blocked_reasons = getattr(decision, "blocked_reasons", [])
    if blocked_reasons is None:
        blocked_reasons = []
    if not isinstance(blocked_reasons, list):
        blocked_reasons = [blocked_reasons]
    return {
        "research_report": research_report,
        "summary_json": summary_json,
        "decision_id": getattr(decision, "id", None),
        "review_status": getattr(decision, "review_status", None),
        "blocked_reasons": blocked_reasons,
        "pipeline_summary": pipeline_result.get("pipeline_summary_path"),
        "exit_code": int(pipeline_result.get("exit_code", 0)),
    }


def _error_payload(error: Exception) -> dict[str, str]:
    return {
        "type": type(error).__name__,
        "message": str(error),
    }


def _daily_payload(result: Any) -> dict[str, Any]:
    payload = {
        "executed": True,
        "status": None,
        "artifacts": {},
    }
    if not isinstance(result, dict):
        return payload
    payload["status"] = result.get("status")
    payload["artifacts"] = {
        "report_paths": result.get("report_paths", {}),
        "portal_paths": result.get("portal_paths", {}),
    }
    return payload


def _decision_payload(decision: Any) -> dict[str, Any]:
    if decision is None:
        return {}
    if hasattr(decision, "model_dump"):
        return decision.model_dump(mode="json")
    if isinstance(decision, dict):
        return dict(decision)

    fields = (
        "id",
        "decision_date",
        "current_strategy_id",
        "selected_strategy_id",
        "previous_strategy_id",
        "fallback_strategy_id",
        "decision_type",
        "status",
        "approved_by",
        "source_report_date",
        "review_status",
        "blocked_reasons",
        "reason_codes",
    )
    payload: dict[str, Any] = {}
    for field in fields:
        if not hasattr(decision, field):
            continue
        value = getattr(decision, field)
        if isinstance(value, date):
            payload[field] = value.isoformat()
        else:
            payload[field] = value
    return payload


def _failed_summary_payload(
    *,
    run_id: str,
    started_at: str,
    preflight_result: dict[str, Any],
    failed_step: str,
    error: Exception,
    daily_result: dict[str, Any],
    research_governance_result: dict[str, Any],
    health_check_result: dict[str, Any],
    post_publish_health_check_result: dict[str, Any],
    publish_result: dict[str, Any],
) -> dict[str, Any]:
    return {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": _iso_utc_now(),
        "status": "failed",
        "failed_step": failed_step,
        "preflight_result": preflight_result,
        "error": _error_payload(error),
        "daily_result": daily_result,
        "research_governance_result": research_governance_result,
        "health_check_result": health_check_result,
        "post_publish_health_check_result": post_publish_health_check_result,
        "publish_result": publish_result,
        "exit_code": 1,
    }


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    run_id = _generate_run_id()
    started_at = _iso_utc_now()
    daily_result = {"executed": False, "artifacts": {}}
    research_governance_result: dict[str, Any] = {}
    health_check_result: dict[str, Any] = {"executed": False, "report_path": None}
    post_publish_health_check_result: dict[str, Any] = {"executed": False, "report_path": None}
    publish_result: dict[str, Any] = {"executed": False, "decision": None}
    preflight_result: dict[str, Any] = {"status": "not_run", "checks": [], "failed_checks": []}

    preflight_result = run_workflow_preflight(
        start_date=args.start_date,
        end_date=args.end_date,
        daily_date=args.daily_date,
        candidate_config=args.candidate_config,
        workflow_root=Path("reports/workflow"),
        health_root=Path("reports/governance/health"),
    )
    if preflight_result["status"] == "failed":
        _finalize_workflow_run(
            _failed_summary_payload(
                run_id=run_id,
                started_at=started_at,
                preflight_result=preflight_result,
                failed_step="preflight",
                error=RuntimeError("workflow preflight failed"),
                daily_result=daily_result,
                research_governance_result=research_governance_result,
                health_check_result=health_check_result,
                post_publish_health_check_result=post_publish_health_check_result,
                publish_result=publish_result,
            ),
            workflow_status="failed",
        )
        return 1

    if args.preflight_only:
        _finalize_workflow_run(
            {
                "run_id": run_id,
                "started_at": started_at,
                "finished_at": _iso_utc_now(),
                "status": "preflight_only",
                "preflight_result": preflight_result,
                "daily_result": daily_result,
                "research_governance_result": research_governance_result,
                "health_check_result": health_check_result,
                "post_publish_health_check_result": post_publish_health_check_result,
                "publish_result": publish_result,
                "exit_code": 0,
            },
            workflow_status="preflight_only",
        )
        return 0

    if args.run_daily:
        try:
            daily_pipeline_result = run_daily_pipeline(
                as_of_date=date.fromisoformat(args.daily_date) if args.daily_date else None,
                log_level=args.log_level,
                execute_trade=args.daily_execute,
                manual_approved=args.daily_manual_approve,
                available_cash=args.daily_available_cash,
            )
            daily_result = _daily_payload(daily_pipeline_result)
        except Exception as error:
            _finalize_workflow_run(
                _failed_summary_payload(
                    run_id=run_id,
                    started_at=started_at,
                    preflight_result=preflight_result,
                    failed_step="daily_run",
                    error=error,
                    daily_result=daily_result,
                    research_governance_result=research_governance_result,
                    health_check_result=health_check_result,
                    post_publish_health_check_result=post_publish_health_check_result,
                    publish_result=publish_result,
                ),
                workflow_status="failed",
            )
            return 1

    try:
        pipeline_result = run_research_governance_pipeline(
            start_date=date.fromisoformat(args.start_date),
            end_date=date.fromisoformat(args.end_date),
            candidate_specs=load_candidate_specs(args.candidate_config),
            initial_capital=args.initial_capital,
            fee_rate=args.fee_rate,
            log_level=args.log_level,
            fail_on_blocked=args.fail_on_blocked,
        )
    except Exception as error:
        _finalize_workflow_run(
            _failed_summary_payload(
                run_id=run_id,
                started_at=started_at,
                preflight_result=preflight_result,
                failed_step="research_governance",
                error=error,
                daily_result=daily_result,
                research_governance_result=research_governance_result,
                health_check_result=health_check_result,
                post_publish_health_check_result=post_publish_health_check_result,
                publish_result=publish_result,
            ),
            workflow_status="failed",
        )
        return 1

    research_governance_result = _research_governance_payload(pipeline_result)
    review_status = research_governance_result.get("review_status")
    blocked = review_status == "blocked"
    blocked_exit_code = int(pipeline_result.get("exit_code", 0))
    if args.fail_on_blocked and blocked:
        blocked_exit_code = 2

    repo = GovernanceRepository()
    policy_loader = ConfigLoader(str(PROJECT_ROOT / "config"))
    try:
        try:
            health_result = check_governance_health(
                report_dir="reports/daily",
                repo=repo,
                policy=policy_loader.load_strategy_config().governance,
                create_rollback_draft=args.create_rollback_draft,
                summary_path=(
                    pipeline_result.get("summary_result", {})
                    .get("output_paths", {})
                    .get("json", "reports/research/summary/research_summary.json")
                ),
            )
            health_check_result = {
                "executed": True,
                "report_path": None,
                **_health_payload(health_result),
            }
            health_report_path = _write_health_report(health_result)
            health_check_result["report_path"] = health_report_path
        except Exception as error:
            _finalize_workflow_run(
                _failed_summary_payload(
                    run_id=run_id,
                    started_at=started_at,
                    preflight_result=preflight_result,
                    failed_step="health_check",
                    error=error,
                    daily_result=daily_result,
                    research_governance_result=research_governance_result,
                    health_check_result=health_check_result,
                    post_publish_health_check_result=post_publish_health_check_result,
                    publish_result=publish_result,
                ),
                workflow_status="failed",
            )
            return 1
    finally:
        repo.close()

    if args.publish and blocked:
        publish_result["publish_blocked_reason"] = "governance_review_status_blocked"
    elif args.publish and review_status == "ready":
        repo = GovernanceRepository()
        policy_loader = ConfigLoader(str(PROJECT_ROOT / "config"))
        try:
            try:
                published_decision = publish_decision(
                    decision_id=research_governance_result.get("decision_id"),
                    approved_by=args.approved_by,
                    repo=repo,
                    policy=policy_loader.load_strategy_config().governance,
                )
            except Exception as error:
                _finalize_workflow_run(
                    _failed_summary_payload(
                        run_id=run_id,
                        started_at=started_at,
                        preflight_result=preflight_result,
                        failed_step="publish",
                        error=error,
                        daily_result=daily_result,
                        research_governance_result=research_governance_result,
                        health_check_result=health_check_result,
                        post_publish_health_check_result=post_publish_health_check_result,
                        publish_result=publish_result,
                    ),
                    workflow_status="failed",
                )
                return 1

            publish_result = {
                "executed": True,
                "decision": _decision_payload(published_decision),
            }

            try:
                post_health_result = check_governance_health(
                    report_dir="reports/daily",
                    repo=repo,
                    policy=policy_loader.load_strategy_config().governance,
                    create_rollback_draft=args.create_rollback_draft,
                    summary_path=(
                        pipeline_result.get("summary_result", {})
                        .get("output_paths", {})
                        .get("json", "reports/research/summary/research_summary.json")
                    ),
                )
                post_publish_health_check_result = {
                    "executed": True,
                    "report_path": None,
                    **_health_payload(post_health_result),
                }
                post_health_report_path = _write_health_report(post_health_result, stage="post_publish")
                post_publish_health_check_result["report_path"] = post_health_report_path
            except Exception as error:
                _finalize_workflow_run(
                    _failed_summary_payload(
                        run_id=run_id,
                        started_at=started_at,
                        preflight_result=preflight_result,
                        failed_step="post_publish_health_check",
                        error=error,
                        daily_result=daily_result,
                        research_governance_result=research_governance_result,
                        health_check_result=health_check_result,
                        post_publish_health_check_result=post_publish_health_check_result,
                        publish_result=publish_result,
                    ),
                    workflow_status="failed",
                )
                return 1
        finally:
            repo.close()

    summary_payload = {
        "run_id": run_id,
        "started_at": started_at,
        "finished_at": _iso_utc_now(),
        "status": "blocked" if blocked else "succeeded",
        "preflight_result": preflight_result,
        "daily_result": daily_result,
        "research_governance_result": research_governance_result,
        "health_check_result": health_check_result,
        "post_publish_health_check_result": post_publish_health_check_result,
        "publish_result": publish_result,
        "exit_code": blocked_exit_code,
    }
    _finalize_workflow_run(summary_payload, workflow_status=summary_payload["status"])
    return blocked_exit_code


if __name__ == "__main__":
    raise SystemExit(main())
