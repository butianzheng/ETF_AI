"""执行 research-to-governance 统一编排 CLI。"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
import sys
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.governance_pipeline import run_research_governance_pipeline
from src.research_candidate_config import load_candidate_specs


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    today = date.today()
    default_start = today - timedelta(days=365)
    parser = argparse.ArgumentParser(description="执行 Research-To-Governance 统一编排")
    parser.add_argument("--start-date", default=default_start.isoformat(), help="开始日期，格式 YYYY-MM-DD")
    parser.add_argument("--end-date", default=today.isoformat(), help="结束日期，格式 YYYY-MM-DD")
    parser.add_argument("--initial-capital", type=float, default=100000.0, help="初始资金")
    parser.add_argument("--fee-rate", type=float, default=0.001, help="手续费率")
    parser.add_argument("--candidate-config", help="研究候选配置文件路径，默认使用 config/research.yaml")
    parser.add_argument("--log-level", default="INFO", help="日志级别")
    parser.add_argument(
        "--fail-on-blocked",
        action="store_true",
        help="当治理结果为 blocked 时返回退出码 2",
    )
    return parser.parse_args(argv)


def _format_blocked_reasons(blocked_reasons: Any) -> str:
    if blocked_reasons is None:
        return "[]"
    if isinstance(blocked_reasons, (list, tuple)):
        return ",".join(str(item) for item in blocked_reasons) or "[]"
    return str(blocked_reasons)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = run_research_governance_pipeline(
            start_date=date.fromisoformat(args.start_date),
            end_date=date.fromisoformat(args.end_date),
            candidate_specs=load_candidate_specs(args.candidate_config),
            initial_capital=args.initial_capital,
            fee_rate=args.fee_rate,
            log_level=args.log_level,
            fail_on_blocked=args.fail_on_blocked,
        )
    except Exception as exc:
        print(f"fatal_error={type(exc).__name__}: {exc}", file=sys.stderr)
        return 1

    research_report = (
        result.get("research_result", {})
        .get("report_paths", {})
        .get("json")
    )
    summary_json = (
        result.get("summary_result", {})
        .get("output_paths", {})
        .get("json")
    )
    cycle_result = result.get("cycle_result")
    decision = getattr(cycle_result, "decision", None)
    decision_id = getattr(decision, "id", None)
    review_status = getattr(decision, "review_status", None)
    blocked_reasons = _format_blocked_reasons(getattr(decision, "blocked_reasons", None))
    pipeline_summary = result.get("pipeline_summary_path")

    print(f"research_report={research_report}")
    print(f"summary_json={summary_json}")
    print(
        "decision_id={decision_id} review_status={review_status} blocked_reasons={blocked_reasons}".format(
            decision_id=decision_id,
            review_status=review_status,
            blocked_reasons=blocked_reasons,
        )
    )
    print(f"pipeline_summary={pipeline_summary}")
    return int(result.get("exit_code", 0))


if __name__ == "__main__":
    raise SystemExit(main())
