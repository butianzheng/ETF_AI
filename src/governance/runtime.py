"""治理运行时解析。"""
from __future__ import annotations

from src.storage.repositories import GovernanceRepository
from src.strategy.registry import STRATEGY_REGISTRY


def resolve_active_strategy_id(
    default_strategy_id: str,
    repo: GovernanceRepository | None = None,
    governance_enabled: bool = True,
) -> str:
    """优先解析最新已发布治理策略，否则回退默认策略。"""
    if not governance_enabled:
        return default_strategy_id

    owns_repo = repo is None
    repository = repo or GovernanceRepository()
    try:
        latest = repository.get_latest_published()
        if latest is None:
            return default_strategy_id
        if latest.selected_strategy_id not in STRATEGY_REGISTRY:
            return default_strategy_id
        return latest.selected_strategy_id
    finally:
        if owns_repo:
            repository.close()
