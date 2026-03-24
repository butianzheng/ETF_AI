"""回退最新已发布治理决策。"""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.governance.publisher import rollback_latest
from src.storage.repositories import GovernanceRepository


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="回退最新已发布治理决策")
    parser.add_argument("--approved-by", required=True, help="执行回退的人")
    parser.add_argument("--reason", required=True, help="回退原因")
    return parser.parse_args()


def main() -> None:
    args = _parse_args()
    repo = GovernanceRepository()
    try:
        decision = rollback_latest(
            approved_by=args.approved_by,
            reason=args.reason,
            repo=repo,
        )
    finally:
        repo.close()
    print(decision.model_dump_json())


if __name__ == "__main__":
    main()
