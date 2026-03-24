"""执行治理健康巡检。"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import config_loader
from src.governance.health import check_governance_health
from src.storage.repositories import GovernanceRepository


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="扫描日报并执行治理健康巡检")
    parser.add_argument(
        "--report-dir",
        default="reports/daily",
        help="日报 JSON 目录",
    )
    parser.add_argument(
        "--create-rollback-draft",
        action="store_true",
        help="发现 critical incident 时创建 fallback draft recommendation",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    repo = GovernanceRepository()
    try:
        result = check_governance_health(
            report_dir=args.report_dir,
            repo=repo,
            policy=config_loader.load_strategy_config().governance,
            create_rollback_draft=args.create_rollback_draft,
            summary_path="reports/research/summary/research_summary.json",
        )
    finally:
        repo.close()

    report_dir = Path("reports/governance/health")
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = report_dir / f"{date.today().isoformat()}.json"
    output_path.write_text(
        json.dumps(
            {
                "incidents": [item.model_dump(mode="json") for item in result.incidents],
                "rollback_recommendation": (
                    result.rollback_recommendation.model_dump(mode="json")
                    if result.rollback_recommendation
                    else None
                ),
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    if result.rollback_recommendation is not None:
        print(f"rollback_decision_id={result.rollback_recommendation.id}")
    print(output_path)


if __name__ == "__main__":
    main()
