"""Status helpers for unified CLI."""
from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

from src.workflow.automation_index import find_run_view, list_run_views, load_latest_run_view

def resolve_status_root(workdir: str | None) -> Path:
    if workdir:
        return Path(workdir).expanduser().resolve()
    return Path.cwd().resolve()


def _print_json(payload: Any) -> int:
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def _print_error(message: str) -> int:
    print(message, file=sys.stderr)
    return 1


def _render_value(value: Any) -> str:
    if isinstance(value, bool):
        return str(value).lower()
    return str(value)


def _render_detail_text(payload: dict[str, Any]) -> str:
    ordered_keys = [
        "automation_run_id",
        "run_id",
        "status",
        "started_at",
        "finished_at",
        "wrapper_exit_code",
        "runner_process_exit_code",
        "publish_executed",
        "manifest_path",
        "runner_stdout_path",
        "runner_stderr_path",
        "health_check_report_path",
        "post_publish_health_check_report_path",
        "research_governance_pipeline_summary_path",
        "failed_step",
        "blocked_reasons",
        "suggested_next_action",
        "created_at",
        "requested_workdir",
        "effective_workdir",
        "outputs_fallback_used",
        "source",
    ]
    lines: list[str] = []
    for key in ordered_keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if value is None:
            continue
        if isinstance(value, list) and not value:
            continue
        lines.append(f"{key}: {_render_value(value)}")
    return "\n".join(lines)


def _render_runs_text(payload: list[dict[str, Any]]) -> str:
    if not payload:
        return "no runs found"
    lines: list[str] = []
    for item in payload:
        lines.append(
            " | ".join(
                [
                    f"automation_run_id={item.get('automation_run_id')}",
                    f"run_id={item.get('run_id')}",
                    f"status={item.get('status')}",
                    f"finished_at={item.get('finished_at')}",
                    f"wrapper_exit_code={item.get('wrapper_exit_code')}",
                    f"source={item.get('source')}",
                ]
            )
        )
    return "\n".join(lines)


def run_status_latest(workdir: str | None, *, output_json: bool) -> int:
    root = resolve_status_root(workdir)
    try:
        payload = load_latest_run_view(root)
    except ValueError as exc:
        return _print_error(str(exc))
    if payload is None:
        return _print_error("no status artifacts found")
    if output_json:
        return _print_json(payload)
    print(_render_detail_text(payload))
    return 0


def run_status_runs(workdir: str | None, *, limit: int, output_json: bool) -> int:
    root = resolve_status_root(workdir)
    try:
        runs = list_run_views(root, limit=limit)
    except ValueError as exc:
        return _print_error(str(exc))
    if not runs:
        return _print_error("no runs found")
    if output_json:
        return _print_json(runs)
    print(_render_runs_text(runs))
    return 0


def run_status_show(workdir: str | None, *, run_id: str, output_json: bool) -> int:
    root = resolve_status_root(workdir)
    try:
        payload = find_run_view(root, run_id=run_id)
    except ValueError as exc:
        return _print_error(str(exc))
    if payload is None:
        return _print_error(f"run not found: {run_id}")
    if output_json:
        return _print_json(payload)
    print(_render_detail_text(payload))
    return 0
