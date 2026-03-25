"""Shared adapters for unified etf_ops CLI commands."""
from __future__ import annotations

from collections.abc import Callable


Entrypoint = Callable[[list[str]], int]


def run_workflow_command(argv: list[str], *, entrypoint: Entrypoint | None = None) -> int:
    if entrypoint is None:
        from scripts.run_end_to_end_workflow import run_workflow_entrypoint

        entrypoint = run_workflow_entrypoint

    return int(entrypoint(argv))


def run_automation_command(argv: list[str], *, entrypoint: Entrypoint | None = None) -> int:
    if entrypoint is None:
        from scripts.run_workflow_automation import run_workflow_automation_entrypoint

        entrypoint = run_workflow_automation_entrypoint

    return int(entrypoint(argv))


def run_daily_command(argv: list[str], *, entrypoint: Entrypoint | None = None) -> int:
    if entrypoint is None:
        from scripts.daily_run import run_daily_entrypoint

        entrypoint = run_daily_entrypoint

    return int(entrypoint(argv))


def run_research_governance_command(argv: list[str], *, entrypoint: Entrypoint | None = None) -> int:
    if entrypoint is None:
        from scripts.run_research_governance_pipeline import run_research_governance_entrypoint

        entrypoint = run_research_governance_entrypoint

    return int(entrypoint(argv))
