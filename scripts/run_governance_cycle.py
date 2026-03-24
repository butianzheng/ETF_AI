"""执行治理自动 review cycle。"""
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
from src.governance.automation import run_governance_cycle
from src.storage.repositories import GovernanceRepository


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="读取研究汇总并执行治理自动 review cycle")
    parser.add_argument(
        "--summary",
        default="reports/research/summary/research_summary.json",
        help="研究汇总 JSON 路径",
    )
    parser.add_argument(
        "--current-strategy-id",
        help="当前生产策略 ID，默认读取 strategy.yaml 中的 production_strategy_id",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    summary_path = Path(args.summary)
    strategy_config = config_loader.load_strategy_config()
    current_strategy_id = args.current_strategy_id or config_loader.load_production_strategy_id()

    repo = GovernanceRepository()
    try:
        result = run_governance_cycle(
            summary_path=summary_path,
            repo=repo,
            policy=strategy_config.governance,
            current_strategy_id=current_strategy_id,
        )
    finally:
        repo.close()

    report_dir = Path("reports/governance/cycle")
    report_dir.mkdir(parents=True, exist_ok=True)
    output_path = report_dir / f"{date.today().isoformat()}.json"
    output_path.write_text(
        json.dumps(
            {
                "decision": result.decision.model_dump(mode="json"),
                "summary_hash": result.summary_hash,
                "created_new": result.created_new,
                "blocked_reasons": result.decision.blocked_reasons,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        "decision_id={decision_id} review_status={review_status} blocked_reasons={blocked_reasons}".format(
            decision_id=result.decision.id,
            review_status=result.decision.review_status,
            blocked_reasons=",".join(result.decision.blocked_reasons) or "[]",
        )
    )
    print(output_path)


if __name__ == "__main__":
    main()
