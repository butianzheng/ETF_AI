"""候选配置加载与解析。"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.core.config import ResearchConfig


def parse_candidate_config_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = ResearchConfig(**data["research"]).candidates
    return [candidate.model_dump() for candidate in candidates]


def load_candidate_specs(candidate_config: str | Path | None) -> list[dict[str, Any]] | None:
    if candidate_config is None:
        return None
    config_path = Path(candidate_config)
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return parse_candidate_config_data(data)
