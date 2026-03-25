"""Status helpers for unified CLI."""
from __future__ import annotations

from pathlib import Path
import json
from typing import Any


AUTOMATION_LATEST_PATH = Path("reports/workflow/automation/latest_run.json")
WORKFLOW_SUMMARY_PATH = Path("reports/workflow/end_to_end_workflow_summary.json")


def resolve_status_root(workdir: str | None) -> Path:
    if workdir:
        return Path(workdir).expanduser().resolve()
    return Path.cwd().resolve()


def _load_json(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"failed to read {path}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"invalid payload type: {path}")
    return payload


def _require_fields(payload: dict[str, Any], required: set[str], *, context: str) -> None:
    missing = [key for key in required if key not in payload or payload[key] is None]
    if missing:
        raise ValueError(f"missing fields in {context}: {', '.join(missing)}")


def load_latest_status(root: Path) -> tuple[str, dict[str, Any]]:
    automation_path = root / AUTOMATION_LATEST_PATH
    summary_path = root / WORKFLOW_SUMMARY_PATH

    if automation_path.exists():
        payload = _load_json(automation_path)
        _require_fields(
            payload,
            {
                "run_id",
                "workflow_status",
                "automation_started_at",
                "automation_finished_at",
                "publish_executed",
                "workflow_manifest",
            },
            context=str(automation_path),
        )
        return "automation_latest", payload

    if summary_path.exists():
        payload = _load_json(summary_path)
        _require_fields(
            payload,
            {
                "run_id",
                "status",
                "started_at",
                "finished_at",
                "workflow_manifest_path",
            },
            context=str(summary_path),
        )
        return "workflow_summary_fallback", payload

    raise FileNotFoundError("no status artifacts found")


def _resolve_manifest_path(root: Path, manifest_path: str | None) -> str:
    if not manifest_path:
        raise ValueError("manifest_path missing")
    path = Path(manifest_path)
    if path.is_absolute():
        return str(path)
    return str(root / path)


def normalize_status_payload(
    root: Path,
    source: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    if source == "automation_latest":
        return {
            "source": "automation_latest",
            "run_id": payload["run_id"],
            "status": payload["workflow_status"],
            "started_at": payload["automation_started_at"],
            "finished_at": payload["automation_finished_at"],
            "publish_executed": payload["publish_executed"],
            "manifest_path": _resolve_manifest_path(root, payload["workflow_manifest"]),
            "failed_step": payload.get("failed_step"),
            "blocked_reasons": payload.get("blocked_reasons") or [],
            "suggested_next_action": payload.get("suggested_next_action"),
        }

    if source == "workflow_summary_fallback":
        publish_result = payload.get("publish_result") or {}
        research_governance = payload.get("research_governance_result") or {}
        failed_step = payload.get("failed_step")
        status = payload["status"]

        suggested_next_action = None
        if status == "blocked":
            suggested_next_action = "inspect blocked_reasons and governance review status"
        elif status == "failed" and failed_step:
            suggested_next_action = f"inspect failed_step={failed_step} and workflow manifest"
        elif status == "failed":
            suggested_next_action = "inspect workflow manifest and stage outputs"

        return {
            "source": "workflow_summary_fallback",
            "run_id": payload["run_id"],
            "status": status,
            "started_at": payload["started_at"],
            "finished_at": payload["finished_at"],
            "publish_executed": publish_result.get("executed", False),
            "manifest_path": _resolve_manifest_path(root, payload["workflow_manifest_path"]),
            "failed_step": failed_step,
            "blocked_reasons": research_governance.get("blocked_reasons") or [],
            "suggested_next_action": suggested_next_action,
        }

    raise ValueError(f"unsupported source {source}")


def render_status_text(payload: dict[str, Any]) -> str:
    lines = [
        f"run_id: {payload.get('run_id')}",
        f"status: {payload.get('status')}",
        f"started_at: {payload.get('started_at')}",
        f"finished_at: {payload.get('finished_at')}",
        f"publish_executed: {str(payload.get('publish_executed')).lower()}",
        f"manifest_path: {payload.get('manifest_path')}",
    ]
    if "failed_step" in payload:
        lines.append(f"failed_step: {payload.get('failed_step')}")
    if "blocked_reasons" in payload:
        lines.append(f"blocked_reasons: {payload.get('blocked_reasons')}")
    if "suggested_next_action" in payload:
        lines.append(f"suggested_next_action: {payload.get('suggested_next_action')}")
    if "source" in payload:
        lines.append(f"source: {payload.get('source')}")
    return "\n".join(lines)


def run_status_latest(workdir: str | None, *, output_json: bool) -> int:
    root = resolve_status_root(workdir)
    try:
        source, raw_payload = load_latest_status(root)
        normalized = normalize_status_payload(root, source, raw_payload)
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc))
        return 1

    if output_json:
        print(json.dumps(normalized, ensure_ascii=False, indent=2))
        return 0

    print(render_status_text(normalized))
    return 0
