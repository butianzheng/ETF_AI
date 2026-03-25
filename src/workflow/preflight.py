"""Workflow runner 预检逻辑。"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from src.core.config import ConfigLoader
from src.research_candidate_config import load_candidate_specs
from src.storage.repositories import GovernanceRepository

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_CONFIG_ROOT = _PROJECT_ROOT / "config"


def _passed(name: str, detail: str | None = None) -> dict[str, str | None]:
    return {"name": name, "status": "passed", "detail": detail}


def _failed(name: str, error: Exception | str) -> dict[str, str]:
    detail = str(error).strip()
    return {"name": name, "status": "failed", "detail": detail or "unknown error"}


def _check_date_args(*, start_date: str, end_date: str, daily_date: str | None) -> dict[str, str | None]:
    name = "date_args"
    try:
        parsed_start = date.fromisoformat(start_date)
        parsed_end = date.fromisoformat(end_date)
        if parsed_start > parsed_end:
            return _failed(name, "start_date must be <= end_date")
        if daily_date is not None:
            date.fromisoformat(daily_date)
    except Exception as error:
        return _failed(name, error)
    return _passed(name)


def _check_strategy_config() -> dict[str, str | None]:
    name = "strategy_config"
    try:
        ConfigLoader(str(_CONFIG_ROOT)).load_strategy_config()
    except Exception as error:
        return _failed(name, error)
    return _passed(name)


def _check_candidate_config(candidate_config: str | None) -> dict[str, str | None]:
    name = "candidate_config"
    if candidate_config is None:
        return _passed(name)
    try:
        load_candidate_specs(candidate_config)
    except Exception as error:
        return _failed(name, error)
    return _passed(name)


def _check_governance_repository() -> dict[str, str | None]:
    name = "governance_repository"
    repo: GovernanceRepository | None = None
    try:
        repo = GovernanceRepository()
    except Exception as error:
        return _failed(name, error)
    finally:
        if repo is not None:
            repo.close()
    return _passed(name)


def _check_output_dir_writable(path: Path, *, name: str) -> dict[str, str | None]:
    probe_path = path / ".workflow_preflight_write_probe"
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe_path.write_text("ok", encoding="utf-8")
        probe_path.unlink(missing_ok=True)
    except Exception as error:
        return _failed(name, error)
    return _passed(name)


def run_workflow_preflight(
    *,
    start_date: str,
    end_date: str,
    daily_date: str | None,
    candidate_config: str | None,
    workflow_root: Path,
    health_root: Path,
) -> dict[str, Any]:
    checks = [
        _check_date_args(start_date=start_date, end_date=end_date, daily_date=daily_date),
        _check_strategy_config(),
        _check_candidate_config(candidate_config),
        _check_governance_repository(),
        _check_output_dir_writable(workflow_root, name="workflow_output_dir"),
        _check_output_dir_writable(health_root, name="health_output_dir"),
    ]
    failed_checks = [
        {"name": item["name"], "detail": item["detail"]}
        for item in checks
        if item["status"] == "failed"
    ]
    return {
        "status": "failed" if failed_checks else "passed",
        "checks": checks,
        "failed_checks": failed_checks,
    }
