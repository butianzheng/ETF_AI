"""端到端工作流统一编排入口（Task 1 最小骨架）。"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
import json
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from scripts.check_governance_health import check_governance_health
from src.core.config import ConfigLoader
from src.governance_pipeline import run_research_governance_pipeline
from src.research_candidate_config import load_candidate_specs
from src.storage.repositories import GovernanceRepository


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
    parser.add_argument("--run-daily", action="store_true", help="预留参数，Task 1 不执行 daily run")
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


def _write_health_report(result: Any) -> str:
    output_dir = Path("reports/governance/health")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{date.today().isoformat()}.json"
    output_path.write_text(
        json.dumps(_health_payload(result), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return str(output_path)


def _write_workflow_summary(payload: dict[str, Any]) -> Path:
    summary_path = Path("reports/workflow/end_to_end_workflow_summary.json")
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding="utf-8",
    )
    return summary_path


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    pipeline_result = run_research_governance_pipeline(
        start_date=date.fromisoformat(args.start_date),
        end_date=date.fromisoformat(args.end_date),
        candidate_specs=load_candidate_specs(args.candidate_config),
        initial_capital=args.initial_capital,
        fee_rate=args.fee_rate,
        log_level=args.log_level,
        fail_on_blocked=args.fail_on_blocked,
    )

    repo = GovernanceRepository()
    policy_loader = ConfigLoader(str(PROJECT_ROOT / "config"))
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
    finally:
        repo.close()

    health_report_path = _write_health_report(health_result)
    exit_code = int(pipeline_result.get("exit_code", 0))
    summary_payload = {
        "daily_result": {"executed": False, "artifacts": {}},
        "research_governance_result": pipeline_result,
        "health_check_result": {
            "executed": True,
            "report_path": health_report_path,
            **_health_payload(health_result),
        },
        "publish_result": {"executed": False, "decision": None},
        "exit_code": exit_code,
    }
    _write_workflow_summary(summary_payload)
    print("publish_executed=false")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
