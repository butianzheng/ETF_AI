from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

DEFAULT_TEST_CANDIDATES = [
    {
        "name": "baseline_trend",
        "strategy_id": "trend_momentum",
        "description": "baseline",
        "overrides": {},
    }
]

ADVANCED_TEST_CANDIDATES = [
    {
        "name": "baseline_trend",
        "strategy_id": "trend_momentum",
        "description": "baseline",
        "overrides": {},
    },
    {
        "name": "fast_turn",
        "strategy_id": "risk_adjusted_momentum",
        "description": "fast",
        "overrides": {
            "strategy_params": {
                "rebalance_frequency": "biweekly",
                "hold_count": 2,
            }
        },
    },
]


def write_candidate_config(path: Path, candidates=DEFAULT_TEST_CANDIDATES) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"research": {"candidates": list(candidates)}}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def expected_candidate_specs(candidates=DEFAULT_TEST_CANDIDATES) -> list[dict[str, Any]]:
    return deepcopy(list(candidates))


def assert_candidate_specs(actual, candidates=DEFAULT_TEST_CANDIDATES) -> None:
    assert actual == expected_candidate_specs(candidates)

