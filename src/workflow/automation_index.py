"""Workflow automation artifact index helper.

This module is a pure helper layer (no CLI parsing, no subprocess orchestration).
It provides:
1) A locked schema for per-run `artifact_index.json`
2) File-system query helpers for latest/runs/show
3) Best-effort legacy fallback views when index pointers/files are missing
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator


_AUTOMATION_RELROOT = Path("reports") / "workflow" / "automation"
_WORKFLOW_SUMMARY_RELPATH = Path("reports") / "workflow" / "end_to_end_workflow_summary.json"

_ARTIFACT_INDEX_SCHEMA_KEYS: tuple[str, ...] = (
    "source",
    "automation_run_id",
    "run_id",
    "workflow_status",
    "automation_started_at",
    "automation_finished_at",
    "wrapper_exit_code",
    "runner_process_exit_code",
    "manifest_path",
    "runner_stdout_path",
    "runner_stderr_path",
    "health_check_report_path",
    "post_publish_health_check_report_path",
    "research_governance_pipeline_summary_path",
    "blocked_reasons",
    "failed_step",
    "suggested_next_action",
    "publish_executed",
    "created_at",
    "requested_workdir",
    "effective_workdir",
    "outputs_fallback_used",
)

_LATEST_REQUIRED_FIELDS: tuple[str, ...] = (
    "automation_run_id",
    "run_id",
    "workflow_status",
    "automation_started_at",
    "automation_finished_at",
    "wrapper_exit_code",
    "runner_process_exit_code",
    "publish_executed",
    "workflow_manifest",
)

_WORKFLOW_SUMMARY_REQUIRED_FIELDS: tuple[str, ...] = (
    "run_id",
    "status",
    "started_at",
    "finished_at",
    "workflow_manifest_path",
)


def _normalize_blocked_reasons(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _path_to_relpath(value: Any, *, effective_workdir: Path) -> str | None:
    if value is None:
        return None
    path = Path(str(value))
    if not path.is_absolute():
        return path.as_posix()

    root = Path(effective_workdir)
    try:
        return path.relative_to(root).as_posix()
    except Exception:
        try:
            return Path(os.path.relpath(str(path), str(root))).as_posix()
        except Exception:
            # Best-effort: keep absolute if we cannot compute a safe relpath.
            return str(path)


def _resolve_abs_path(value: Any, *, effective_workdir: Path) -> str | None:
    if value is None:
        return None
    path = Path(str(value))
    return str(path if path.is_absolute() else (Path(effective_workdir) / path))


def _load_json_file(path: Path) -> dict[str, Any]:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"failed to read {str(path)}") from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid json: {str(path)}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"invalid payload type: {str(path)}")
    return payload


def _require_fields(payload: dict[str, Any], required: tuple[str, ...], *, context: str) -> None:
    missing = [key for key in required if key not in payload or payload.get(key) is None]
    if missing:
        raise ValueError(f"missing fields in {context}: {', '.join(missing)}")


def _validate_artifact_index_payload(payload: dict[str, Any], *, context: str) -> None:
    keys = set(payload.keys())
    expected = set(_ARTIFACT_INDEX_SCHEMA_KEYS)
    if keys != expected:
        missing = sorted(expected - keys)
        extra = sorted(keys - expected)
        raise ValueError(f"artifact index schema mismatch in {context}: missing={missing} extra={extra}")
    if not isinstance(payload.get("blocked_reasons"), list):
        raise ValueError(f"artifact index schema mismatch in {context}: blocked_reasons must be list")

    def _require_non_empty_str(field: str) -> None:
        value = payload.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"artifact index semantic error in {context}: {field} must be non-empty string")

    def _require_optional_str(field: str) -> None:
        value = payload.get(field)
        if value is None:
            return
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"artifact index semantic error in {context}: {field} must be string or null")

    def _require_int(field: str) -> None:
        value = payload.get(field)
        if not isinstance(value, int):
            raise ValueError(f"artifact index semantic error in {context}: {field} must be int")

    def _require_optional_int(field: str) -> None:
        value = payload.get(field)
        if value is None:
            return
        if not isinstance(value, int):
            raise ValueError(f"artifact index semantic error in {context}: {field} must be int or null")

    def _require_bool(field: str) -> None:
        value = payload.get(field)
        if not isinstance(value, bool):
            raise ValueError(f"artifact index semantic error in {context}: {field} must be bool")

    # Required core semantics (file can have nullable fields, but core diagnosis must be present and well-typed).
    _require_non_empty_str("source")
    _require_non_empty_str("automation_run_id")
    run_id = payload.get("run_id")
    if run_id is not None and (not isinstance(run_id, str) or not run_id.strip()):
        raise ValueError(f"artifact index semantic error in {context}: run_id must be string or null")
    _require_non_empty_str("workflow_status")
    _require_non_empty_str("automation_started_at")
    _require_non_empty_str("automation_finished_at")
    _require_int("wrapper_exit_code")
    _require_optional_int("runner_process_exit_code")
    _require_non_empty_str("manifest_path")
    _require_bool("publish_executed")
    _require_non_empty_str("created_at")
    _require_non_empty_str("requested_workdir")
    _require_non_empty_str("effective_workdir")
    _require_bool("outputs_fallback_used")

    # Optional fields (nullable, but when present must be typed sanely).
    _require_optional_str("runner_stdout_path")
    _require_optional_str("runner_stderr_path")
    _require_optional_str("health_check_report_path")
    _require_optional_str("post_publish_health_check_report_path")
    _require_optional_str("research_governance_pipeline_summary_path")
    _require_optional_str("failed_step")
    _require_optional_str("suggested_next_action")


def _suggested_next_action_for_summary(*, status: str, failed_step: str | None) -> str | None:
    if status == "blocked":
        return "inspect blocked_reasons and governance review status"
    if status == "failed" and failed_step:
        return f"inspect failed_step={failed_step} and workflow manifest"
    if status == "failed":
        return "inspect workflow manifest and stage outputs"
    return None


def artifact_index_relpath(automation_run_id: str) -> str:
    return str(_AUTOMATION_RELROOT / "runs" / str(automation_run_id) / "artifact_index.json")


def build_artifact_index(
    record: dict[str, Any],
    *,
    effective_workdir: str | Path,
    created_at: str,
) -> dict[str, Any]:
    """Build a per-run artifact index payload with a locked schema.

    All path fields are stored as *relative paths* to `effective_workdir`.
    Missing fields are kept explicitly as null (None) except blocked_reasons (always list).
    """

    if not isinstance(record, dict):
        raise ValueError("record must be a dict")

    root = Path(effective_workdir)
    blocked_reasons = _normalize_blocked_reasons(record.get("blocked_reasons"))

    # Explicitly materialize the full schema (no implicit omissions).
    payload: dict[str, Any] = {
        "source": "artifact_index",
        "automation_run_id": record.get("automation_run_id"),
        "run_id": record.get("run_id"),
        "workflow_status": record.get("workflow_status"),
        "automation_started_at": record.get("automation_started_at"),
        "automation_finished_at": record.get("automation_finished_at"),
        "wrapper_exit_code": record.get("wrapper_exit_code"),
        "runner_process_exit_code": record.get("runner_process_exit_code"),
        "manifest_path": _path_to_relpath(record.get("workflow_manifest"), effective_workdir=root),
        "runner_stdout_path": _path_to_relpath(record.get("runner_stdout_path"), effective_workdir=root),
        "runner_stderr_path": _path_to_relpath(record.get("runner_stderr_path"), effective_workdir=root),
        "health_check_report_path": _path_to_relpath(record.get("health_check_report_path"), effective_workdir=root),
        "post_publish_health_check_report_path": _path_to_relpath(
            record.get("post_publish_health_check_report_path"),
            effective_workdir=root,
        ),
        "research_governance_pipeline_summary_path": _path_to_relpath(
            record.get("research_governance_pipeline_summary_path"),
            effective_workdir=root,
        ),
        "blocked_reasons": blocked_reasons,
        "failed_step": record.get("failed_step"),
        "suggested_next_action": record.get("suggested_next_action"),
        "publish_executed": record.get("publish_executed"),
        "created_at": created_at,
        "requested_workdir": record.get("requested_workdir"),
        "effective_workdir": record.get("effective_workdir", str(root)),
        "outputs_fallback_used": record.get("outputs_fallback_used"),
    }

    # Guard: schema lock.
    if set(payload.keys()) != set(_ARTIFACT_INDEX_SCHEMA_KEYS):
        missing = [key for key in _ARTIFACT_INDEX_SCHEMA_KEYS if key not in payload]
        extra = [key for key in payload.keys() if key not in _ARTIFACT_INDEX_SCHEMA_KEYS]
        raise ValueError(f"artifact index schema mismatch: missing={missing!r} extra={extra!r}")

    return payload


def write_artifact_index(payload: dict[str, Any], *, effective_workdir: str | Path) -> Path:
    if not isinstance(payload, dict):
        raise ValueError("payload must be a dict")
    automation_run_id = payload.get("automation_run_id")
    if not automation_run_id:
        raise ValueError("payload missing automation_run_id")

    root = Path(effective_workdir)
    relpath = artifact_index_relpath(str(automation_run_id))
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def iter_history_records(root: str | Path) -> Iterator[dict[str, Any]]:
    """Iterate parsed history records from run_history.jsonl.

    Default behavior is best-effort:
    - bad lines are skipped
    - truncated tail line is skipped
    - never raises due to JSON decode errors
    """

    history_path = Path(root) / _AUTOMATION_RELROOT / "run_history.jsonl"
    try:
        with open(history_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line:
                    continue
                try:
                    item = json.loads(line)
                except Exception:
                    continue
                if isinstance(item, dict):
                    yield item
    except FileNotFoundError:
        return


def _record_to_summary_view(
    record: dict[str, Any],
    *,
    effective_workdir: Path,
) -> dict[str, Any]:
    source = "legacy_fallback"

    index_path_value = record.get("artifact_index_path")
    if isinstance(index_path_value, str) and index_path_value.strip():
        index_path = Path(index_path_value)
        index_abspath = index_path if index_path.is_absolute() else (effective_workdir / index_path)
        if index_abspath.exists():
            try:
                payload = _load_json_file(index_abspath)
                _validate_artifact_index_payload(payload, context=str(index_abspath))
                source = str(payload.get("source") or "artifact_index")
                return {
                    "source": source,
                    "automation_run_id": payload.get("automation_run_id"),
                    "run_id": payload.get("run_id"),
                    "status": payload.get("workflow_status"),
                    "finished_at": payload.get("automation_finished_at"),
                    "wrapper_exit_code": payload.get("wrapper_exit_code"),
                    "failed_step": payload.get("failed_step"),
                }
            except Exception:
                source = "legacy_fallback_index_error"

    return {
        "source": source,
        "automation_run_id": record.get("automation_run_id"),
        "run_id": record.get("run_id"),
        "status": record.get("workflow_status"),
        "finished_at": record.get("automation_finished_at"),
        "wrapper_exit_code": record.get("wrapper_exit_code"),
        "failed_step": record.get("failed_step"),
    }


def list_run_views(root: str | Path, *, limit: int) -> list[dict[str, Any]]:
    effective_workdir = Path(root)
    records = list(iter_history_records(effective_workdir))

    views = [_record_to_summary_view(record, effective_workdir=effective_workdir) for record in records]
    views.sort(key=lambda item: str(item.get("finished_at") or ""), reverse=True)
    if limit <= 0:
        return []
    return views[:limit]


def _build_index_detail_view(payload: dict[str, Any], *, effective_workdir: Path) -> dict[str, Any]:
    blocked_reasons = _normalize_blocked_reasons(payload.get("blocked_reasons"))
    return {
        "source": str(payload.get("source") or "artifact_index"),
        "automation_run_id": payload.get("automation_run_id"),
        "run_id": payload.get("run_id"),
        "status": payload.get("workflow_status"),
        "started_at": payload.get("automation_started_at"),
        "finished_at": payload.get("automation_finished_at"),
        "wrapper_exit_code": payload.get("wrapper_exit_code"),
        "runner_process_exit_code": payload.get("runner_process_exit_code"),
        "manifest_path": _resolve_abs_path(payload.get("manifest_path"), effective_workdir=effective_workdir),
        "runner_stdout_path": _resolve_abs_path(payload.get("runner_stdout_path"), effective_workdir=effective_workdir),
        "runner_stderr_path": _resolve_abs_path(payload.get("runner_stderr_path"), effective_workdir=effective_workdir),
        "health_check_report_path": _resolve_abs_path(
            payload.get("health_check_report_path"),
            effective_workdir=effective_workdir,
        ),
        "post_publish_health_check_report_path": _resolve_abs_path(
            payload.get("post_publish_health_check_report_path"),
            effective_workdir=effective_workdir,
        ),
        "research_governance_pipeline_summary_path": _resolve_abs_path(
            payload.get("research_governance_pipeline_summary_path"),
            effective_workdir=effective_workdir,
        ),
        "blocked_reasons": blocked_reasons,
        "failed_step": payload.get("failed_step"),
        "suggested_next_action": payload.get("suggested_next_action"),
        "publish_executed": payload.get("publish_executed"),
        "created_at": payload.get("created_at"),
        "requested_workdir": payload.get("requested_workdir"),
        "effective_workdir": payload.get("effective_workdir"),
        "outputs_fallback_used": payload.get("outputs_fallback_used"),
    }


def rebuild_legacy_detail_view(
    record: dict[str, Any],
    *,
    effective_workdir: str | Path,
    source: str,
) -> dict[str, Any]:
    """Rebuild a detail view from legacy latest/history record (no per-run index)."""

    root = Path(effective_workdir)
    blocked_reasons = _normalize_blocked_reasons(record.get("blocked_reasons"))

    return {
        "source": source,
        "automation_run_id": record.get("automation_run_id"),
        "run_id": record.get("run_id"),
        "status": record.get("workflow_status"),
        "started_at": record.get("automation_started_at"),
        "finished_at": record.get("automation_finished_at"),
        "wrapper_exit_code": record.get("wrapper_exit_code"),
        "runner_process_exit_code": record.get("runner_process_exit_code"),
        "manifest_path": _resolve_abs_path(record.get("workflow_manifest"), effective_workdir=root),
        "runner_stdout_path": _resolve_abs_path(record.get("runner_stdout_path"), effective_workdir=root),
        "runner_stderr_path": _resolve_abs_path(record.get("runner_stderr_path"), effective_workdir=root),
        "failed_step": record.get("failed_step"),
        "blocked_reasons": blocked_reasons,
        "publish_executed": record.get("publish_executed"),
        "requested_workdir": record.get("requested_workdir"),
        "effective_workdir": record.get("effective_workdir"),
    }


def _load_detail_view_for_record(record: dict[str, Any], *, effective_workdir: Path) -> dict[str, Any]:
    index_path_value = record.get("artifact_index_path")
    if isinstance(index_path_value, str) and index_path_value.strip():
        index_path = Path(index_path_value)
        index_abspath = index_path if index_path.is_absolute() else (effective_workdir / index_path)
        if index_abspath.exists():
            payload = _load_json_file(index_abspath)
            _validate_artifact_index_payload(payload, context=str(index_abspath))
            return _build_index_detail_view(payload, effective_workdir=effective_workdir)

    return rebuild_legacy_detail_view(record, effective_workdir=effective_workdir, source="legacy_fallback")


def find_run_view(root: str | Path, *, run_id: str) -> dict[str, Any] | None:
    """Find a run view by automation_run_id or workflow run_id.

    Preference:
    1) exact match automation_run_id
    2) exact match workflow run_id, choosing the latest finished record; tie -> later history line.
    """

    effective_workdir = Path(root)
    history = list(iter_history_records(effective_workdir))

    for record in history:
        if str(record.get("automation_run_id") or "") == str(run_id):
            return _load_detail_view_for_record(record, effective_workdir=effective_workdir)

    best: dict[str, Any] | None = None
    best_finished = ""
    for record in history:
        if str(record.get("run_id") or "") != str(run_id):
            continue
        finished = str(record.get("automation_finished_at") or "")
        if best is None or finished > best_finished or finished == best_finished:
            best = record
            best_finished = finished

    if best is None:
        return None
    return _load_detail_view_for_record(best, effective_workdir=effective_workdir)


def load_latest_run_view(root: str | Path) -> dict[str, Any] | None:
    effective_workdir = Path(root)
    latest_path = effective_workdir / _AUTOMATION_RELROOT / "latest_run.json"
    if not latest_path.exists():
        summary_path = effective_workdir / _WORKFLOW_SUMMARY_RELPATH
        if not summary_path.exists():
            return None
        summary = _load_json_file(summary_path)
        _require_fields(summary, _WORKFLOW_SUMMARY_REQUIRED_FIELDS, context=str(summary_path))
        publish_result = summary.get("publish_result") or {}
        research_governance = summary.get("research_governance_result") or {}
        failed_step = summary.get("failed_step")
        status = str(summary.get("status"))
        return {
            "source": "workflow_summary_fallback",
            "automation_run_id": None,
            "run_id": summary.get("run_id"),
            "status": status,
            "started_at": summary.get("started_at"),
            "finished_at": summary.get("finished_at"),
            "publish_executed": publish_result.get("executed", False),
            "manifest_path": _resolve_abs_path(
                summary.get("workflow_manifest_path"),
                effective_workdir=effective_workdir,
            ),
            "failed_step": failed_step,
            "blocked_reasons": research_governance.get("blocked_reasons") or [],
            "suggested_next_action": _suggested_next_action_for_summary(status=status, failed_step=failed_step),
        }

    record = _load_json_file(latest_path)
    _require_fields(record, _LATEST_REQUIRED_FIELDS, context=str(latest_path))

    # If artifact_index_path exists and points to an existing file, it must be valid; otherwise error.
    index_path_value = record.get("artifact_index_path")
    if isinstance(index_path_value, str) and index_path_value.strip():
        index_path = Path(index_path_value)
        index_abspath = index_path if index_path.is_absolute() else (effective_workdir / index_path)
        if index_abspath.exists():
            payload = _load_json_file(index_abspath)
            _validate_artifact_index_payload(payload, context=str(index_abspath))
            return _build_index_detail_view(payload, effective_workdir=effective_workdir)

    return rebuild_legacy_detail_view(record, effective_workdir=effective_workdir, source="automation_latest")
