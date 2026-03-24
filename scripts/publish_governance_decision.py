"""审批并发布治理决策。"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.core.config import config_loader
from src.governance.publisher import publish_decision
from src.storage.repositories import GovernanceRepository


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="发布治理 draft 决策")
    parser.add_argument("--decision-id", type=int, required=True, help="draft 决策 ID")
    parser.add_argument("--approved-by", required=True, help="审批人")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    repo = GovernanceRepository()
    try:
        decision = repo.get_by_id(args.decision_id)
        if decision is None:
            raise ValueError(f"governance decision not found: {args.decision_id}")
        if decision.status == "draft":
            repo.approve(args.decision_id, approved_by=args.approved_by)
        published = publish_decision(
            decision_id=args.decision_id,
            approved_by=args.approved_by,
            repo=repo,
            policy=config_loader.load_strategy_config().governance,
        )
    finally:
        repo.close()
    print(published.model_dump_json())


if __name__ == "__main__":
    main()
