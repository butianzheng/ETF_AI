"""Local workflow automation wrapper.

This script runs the existing workflow runner as a subprocess, captures stdout/stderr,
writes automation indexes (latest/history) and attention summaries.

Key behaviors (Task 2):
- `--workdir` controls the subprocess cwd (default: repo root).
- runner args are passed after `--`.
- runner is invoked via an absolute path.
- when `workdir != repo root`, create `workdir/config -> <repo>/config` symlink.
- write runner stdout/stderr logs before parsing stdout contract.
- wrapper exit code inherits runner exit code unless wrapper/contract error => 1.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.workflow.automation import (  # noqa: E402
    WorkflowContractError,
    _build_attention_payload,
    build_automation_record,
    generate_automation_run_id,
    parse_workflow_stdout_contract,
    render_attention_markdown,
    should_update_attention,
    validate_workflow_contract,
    write_automation_outputs,
    write_runner_logs,
)

from src.workflow.automation_index import (  # noqa: E402
    artifact_index_relpath,
    build_artifact_index,
    write_artifact_index,
)


RUNNER_SCRIPT = (PROJECT_ROOT / "scripts" / "run_end_to_end_workflow.py").resolve()


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Local workflow automation wrapper（兼容入口，推荐改用 `python scripts/etf_ops.py ...`）"
    )
    parser.add_argument("--workdir", default=None, help="Runner subprocess working directory (default: repo root)")
    parser.add_argument("runner_args", nargs=argparse.REMAINDER, help="Runner args (pass after `--`)")
    return parser.parse_args(argv)


def _ensure_workdir_config_symlink(*, workdir: Path, repo_root: Path) -> None:
    config_target = (repo_root / "config").resolve()
    link_path = workdir / "config"

    if link_path.exists() or link_path.is_symlink():
        if link_path.is_symlink() and link_path.resolve() == config_target:
            return
        raise RuntimeError(f"workdir config path already exists and is not the expected symlink: {link_path}")

    link_path.symlink_to(config_target, target_is_directory=True)


def _rel_to_workdir(path: str | Path | None, *, workdir: Path) -> str | None:
    if path is None:
        return None
    p = Path(path)
    # If a helper accidentally returns a relative path, interpret it as relative to workdir
    # (not the current process CWD).
    resolved = ((workdir / p).resolve() if not p.is_absolute() else p.resolve())
    try:
        return str(resolved.relative_to(workdir))
    except Exception:
        return str(resolved)


def _resolve_manifest_path(value: str, *, workdir: Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return (workdir / path).resolve()


def _resolve_path_against_workdir(value: str | Path | None, *, workdir: Path) -> Path | None:
    if value is None:
        return None
    path = Path(str(value))
    return (path if path.is_absolute() else (workdir / path)).resolve()


def _materialize_record_for_effective_workdir(
    record: dict[str, Any],
    *,
    requested_workdir: Path,
    effective_workdir: Path,
    runner_artifacts_workdir: Path,
    outputs_fallback_used: bool,
    runner_stdout_abs: str | None,
    runner_stderr_abs: str | None,
    manifest_abs: Path | None,
) -> dict[str, Any]:
    """Rebuild record payload against the final effective_workdir.

    This prevents reusing path fields built under an earlier workdir when we fall back.
    """

    out = dict(record)
    out["requested_workdir"] = str(requested_workdir.resolve())
    out["effective_workdir"] = str(effective_workdir.resolve())
    out["outputs_fallback_used"] = bool(outputs_fallback_used)

    if runner_stdout_abs is not None:
        out["runner_stdout_path"] = _rel_to_workdir(runner_stdout_abs, workdir=effective_workdir)
    if runner_stderr_abs is not None:
        out["runner_stderr_path"] = _rel_to_workdir(runner_stderr_abs, workdir=effective_workdir)
    if manifest_abs is not None:
        out["workflow_manifest"] = _rel_to_workdir(manifest_abs, workdir=effective_workdir)

    # Runner-produced artifacts are generally relative to the runner's workdir; resolve them there first,
    # then rebase against the final effective_workdir.
    for field in (
        "health_check_report_path",
        "post_publish_health_check_report_path",
        "research_governance_pipeline_summary_path",
    ):
        resolved = _resolve_path_against_workdir(out.get(field), workdir=runner_artifacts_workdir)
        if resolved is not None:
            out[field] = _rel_to_workdir(resolved, workdir=effective_workdir)

    return out


def _write_artifact_index_for_effective_workdir(
    record: dict[str, Any],
    *,
    requested_workdir: Path,
    effective_workdir: Path,
    runner_artifacts_workdir: Path,
    outputs_fallback_used: bool,
    runner_stdout_abs: str | None,
    runner_stderr_abs: str | None,
    manifest_abs: Path | None,
) -> dict[str, Any]:
    rebuilt = _materialize_record_for_effective_workdir(
        record,
        requested_workdir=requested_workdir,
        effective_workdir=effective_workdir,
        runner_artifacts_workdir=runner_artifacts_workdir,
        outputs_fallback_used=outputs_fallback_used,
        runner_stdout_abs=runner_stdout_abs,
        runner_stderr_abs=runner_stderr_abs,
        manifest_abs=manifest_abs,
    )

    created_at = _iso_utc_now()
    index_payload = build_artifact_index(rebuilt, effective_workdir=effective_workdir, created_at=created_at)
    write_artifact_index(index_payload, effective_workdir=effective_workdir)

    rebuilt["artifact_index_path"] = artifact_index_relpath(str(rebuilt.get("automation_run_id")))
    return rebuilt


def _write_automation_outputs_for_effective_workdir(record: dict[str, Any], *, effective_workdir: Path) -> None:
    _write_automation_outputs_idempotent(record, root=Path(effective_workdir) / "reports" / "workflow" / "automation")


def _build_outputs_failure_record(
    record: dict[str, Any],
    *,
    requested_workdir: Path,
    effective_workdir: Path,
    runner_artifacts_workdir: Path,
    outputs_fallback_used: bool,
    runner_stdout_abs: str | None,
    runner_stderr_abs: str | None,
    manifest_abs: Path | None,
    error_text: str,
) -> dict[str, Any]:
    error_record = dict(record)
    error_record["wrapper_exit_code"] = 1
    error_record["attention_type"] = "automation_contract_error"
    error_record["suggested_next_action"] = error_text
    error_record["failed_step"] = "automation_contract_error"
    return _materialize_record_for_effective_workdir(
        error_record,
        requested_workdir=requested_workdir,
        effective_workdir=effective_workdir,
        runner_artifacts_workdir=runner_artifacts_workdir,
        outputs_fallback_used=outputs_fallback_used,
        runner_stdout_abs=runner_stdout_abs,
        runner_stderr_abs=runner_stderr_abs,
        manifest_abs=manifest_abs,
    )


def _write_latest_run_json(record: dict[str, Any], *, path: Path) -> None:
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")


def _upsert_history_record(record: dict[str, Any], *, path: Path) -> None:
    """Append or replace the history record for this automation_run_id.

    `write_automation_outputs()` always appends. In wrapper recovery flows we may need to retry
    within the same root; to avoid duplicated lines (same automation_run_id), we upsert by
    replacing the most recent matching line.
    """

    automation_run_id = str(record.get("automation_run_id") or "")
    if not automation_run_id:
        raise ValueError("record missing automation_run_id")

    path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(record, ensure_ascii=False) + "\n"

    if not path.exists():
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
        return

    raw_lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    for idx in range(len(raw_lines) - 1, -1, -1):
        if not raw_lines[idx].strip():
            continue
        try:
            payload = json.loads(raw_lines[idx])
        except Exception:
            continue
        if isinstance(payload, dict) and str(payload.get("automation_run_id") or "") == automation_run_id:
            raw_lines[idx] = line
            path.write_text("".join(raw_lines), encoding="utf-8")
            return

    with open(path, "a", encoding="utf-8") as f:
        f.write(line)


def _write_attention_outputs(record: dict[str, Any], *, json_path: Path, md_path: Path) -> None:
    if not should_update_attention(record):
        return
    payload = _build_attention_payload(record)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(render_attention_markdown(record), encoding="utf-8")


def _write_automation_outputs_idempotent(record: dict[str, Any], *, root: Path) -> None:
    """Write history/latest/attention, allowing safe retries without duplicating history."""

    root.mkdir(parents=True, exist_ok=True)

    run_history_path = root / "run_history.jsonl"
    latest_run_path = root / "latest_run.json"
    latest_attention_json_path = root / "latest_attention.json"
    latest_attention_md_path = root / "latest_attention.md"

    _upsert_history_record(record, path=run_history_path)
    _write_latest_run_json(record, path=latest_run_path)
    _write_attention_outputs(record, json_path=latest_attention_json_path, md_path=latest_attention_md_path)


def _sanitize_runner_args(runner_args: list[str]) -> list[str]:
    # `argparse.REMAINDER` may include a literal `--` marker; do not forward it to the runner.
    if runner_args and runner_args[0] == "--":
        return runner_args[1:]
    return runner_args


def _normalize_wrapper_exit_code(runner_exit_code: int | None) -> int:
    if runner_exit_code is None:
        return 1
    if runner_exit_code < 0:
        # subprocess uses negative returncode to indicate termination by signal.
        # Avoid passing a negative code to SystemExit.
        return 128 + abs(int(runner_exit_code))
    return int(runner_exit_code)


def _format_exception(e: Exception) -> str:
    msg = str(e).strip()
    if msg:
        return f"{type(e).__name__}: {msg}"
    return type(e).__name__


def run_workflow_automation_entrypoint(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    repo_root = PROJECT_ROOT.resolve()
    requested_workdir = Path(args.workdir).resolve() if args.workdir else repo_root

    automation_run_id = generate_automation_run_id()
    started_at = _iso_utc_now()
    runner_args = _sanitize_runner_args(list(args.runner_args or []))
    runner_command = [sys.executable, str(RUNNER_SCRIPT), *runner_args]

    # We always try to write a record (history/latest/attention) for the wrapper run.
    # If `--workdir` cannot be prepared (mkdir/config symlink), we fall back to repo_root for
    # automation outputs and skip running the runner.
    workdir = requested_workdir
    prep_error: str | None = None
    skip_runner = False

    try:
        workdir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        prep_error = f"workdir mkdir failed: {workdir}: {_format_exception(e)}"
        workdir = repo_root
        skip_runner = True

    if not skip_runner and workdir != repo_root:
        try:
            _ensure_workdir_config_symlink(workdir=workdir, repo_root=repo_root)
        except Exception as e:
            prep_error = f"config symlink preparation failed: {_format_exception(e)}"
            workdir = repo_root
            skip_runner = True

    automation_root = workdir / "reports" / "workflow" / "automation"

    runner_exit_code: int | None
    runner_stdout: str
    runner_stderr: str

    if skip_runner:
        runner_exit_code = None
        runner_stdout = ""
        runner_stderr = prep_error or "wrapper preparation failed"
    else:
        try:
            proc = subprocess.run(
                runner_command,
                cwd=str(workdir),
                text=True,
                capture_output=True,
                check=False,
            )
            runner_exit_code = proc.returncode
            runner_stdout = proc.stdout or ""
            runner_stderr = proc.stderr or ""
        except Exception as e:
            runner_exit_code = None
            runner_stdout = ""
            runner_stderr = f"wrapper subprocess failure: {_format_exception(e)}"

    # Always persist raw logs first (even if subprocess/contract parsing fails).
    runner_logs_abs: dict[str, str] = {}
    log_write_error: str | None = None
    try:
        runner_logs_abs = write_runner_logs(
            automation_run_id=automation_run_id,
            stdout=runner_stdout,
            stderr=runner_stderr,
            root=automation_root,
        )
    except Exception as e:
        log_write_error = f"write_runner_logs failed: {_format_exception(e)}"

    runner_stdout_abs = runner_logs_abs.get("runner_stdout_path")
    runner_stderr_abs = runner_logs_abs.get("runner_stderr_path")
    runner_stdout_path = _rel_to_workdir(runner_logs_abs.get("runner_stdout_path"), workdir=workdir)
    runner_stderr_path = _rel_to_workdir(runner_logs_abs.get("runner_stderr_path"), workdir=workdir)

    wrapper_exit_code = _normalize_wrapper_exit_code(runner_exit_code)
    contract: dict[str, Any] | None = None
    manifest_payload: dict[str, Any] | None = None
    resolved_manifest_path: Path | None = None
    record: dict[str, Any]

    try:
        if prep_error is not None:
            raise WorkflowContractError(prep_error)
        if log_write_error is not None:
            raise WorkflowContractError(log_write_error)
        if runner_exit_code is None:
            raise WorkflowContractError("runner subprocess failed before producing stdout contract")

        contract = parse_workflow_stdout_contract(runner_stdout)
        resolved_manifest_path = _resolve_manifest_path(str(contract["workflow_manifest"]), workdir=workdir)
        manifest_payload = json.loads(resolved_manifest_path.read_text(encoding="utf-8"))
        validate_workflow_contract(
            contract,
            manifest_payload,
            runner_process_exit_code=runner_exit_code,
            manifest_path=resolved_manifest_path,
        )

        finished_at = _iso_utc_now()
        record = build_automation_record(
            automation_run_id=automation_run_id,
            automation_started_at=started_at,
            automation_finished_at=finished_at,
            runner_command=runner_command,
            runner_process_exit_code=runner_exit_code,
            wrapper_exit_code=wrapper_exit_code,
            contract=contract,
            manifest_payload=manifest_payload,
            runner_stdout_path=runner_stdout_path,
            runner_stderr_path=runner_stderr_path,
        )
    except WorkflowContractError as e:
        wrapper_exit_code = 1
        finished_at = _iso_utc_now()
        record = build_automation_record(
            automation_run_id=automation_run_id,
            automation_started_at=started_at,
            automation_finished_at=finished_at,
            runner_command=runner_command,
            runner_process_exit_code=runner_exit_code,
            wrapper_exit_code=wrapper_exit_code,
            contract=contract or {},
            manifest_payload=manifest_payload or {},
            runner_stdout_path=runner_stdout_path,
            runner_stderr_path=runner_stderr_path,
            attention_type="automation_contract_error",
            suggested_next_action=str(e),
        )
        record["failed_step"] = "automation_contract_error"
    except Exception as e:  # pragma: no cover
        wrapper_exit_code = 1
        finished_at = _iso_utc_now()
        record = build_automation_record(
            automation_run_id=automation_run_id,
            automation_started_at=started_at,
            automation_finished_at=finished_at,
            runner_command=runner_command,
            runner_process_exit_code=runner_exit_code,
            wrapper_exit_code=wrapper_exit_code,
            contract=contract or {},
            manifest_payload=manifest_payload or {},
            runner_stdout_path=runner_stdout_path,
            runner_stderr_path=runner_stderr_path,
            attention_type="automation_contract_error",
            suggested_next_action=_format_exception(e),
        )
        record["failed_step"] = "automation_contract_error"

    record["requested_workdir"] = str(requested_workdir)
    record["effective_workdir"] = str(workdir)
    record.setdefault("outputs_fallback_used", False)

    # If runner/contract already failed, we still keep the legacy best-effort write path.
    if record.get("failed_step") == "automation_contract_error":
        try:
            write_automation_outputs(record, root=automation_root)
        except Exception as e:
            # Best-effort fallback: if workdir reports are not writable, try repo_root so the
            # wrapper run is still discoverable.
            fallback_root = repo_root / "reports" / "workflow" / "automation"
            if fallback_root.resolve() == automation_root.resolve():
                return 1
            try:
                record["effective_workdir"] = str(repo_root)
                record["outputs_fallback_used"] = True
                record["outputs_write_error"] = _format_exception(e)
                write_automation_outputs(record, root=fallback_root)
            except Exception:
                return 1
        return int(wrapper_exit_code)

    # Task 2: Persist artifact index + pointer, with fallback and full record rebuild per effective_workdir.
    # Once `artifact_index.json` has been written on some root, that root is "locked":
    # any subsequent latest/history/attention failure must not write to a different root.
    index_primary_error: str | None = None
    index_fallback_error: str | None = None

    selected_root: Path | None = None
    selected_record: dict[str, Any] | None = None
    selected_outputs_fallback_used = False

    try:
        selected_record = _write_artifact_index_for_effective_workdir(
            record,
            requested_workdir=requested_workdir,
            effective_workdir=workdir,
            runner_artifacts_workdir=workdir,
            outputs_fallback_used=False,
            runner_stdout_abs=runner_stdout_abs,
            runner_stderr_abs=runner_stderr_abs,
            manifest_abs=resolved_manifest_path,
        )
        selected_root = workdir
        selected_outputs_fallback_used = False
    except Exception as e:
        index_primary_error = _format_exception(e)

    if selected_record is None and repo_root.resolve() != workdir.resolve():
        try:
            selected_record = _write_artifact_index_for_effective_workdir(
                record,
                requested_workdir=requested_workdir,
                effective_workdir=repo_root,
                runner_artifacts_workdir=workdir,
                outputs_fallback_used=True,
                runner_stdout_abs=runner_stdout_abs,
                runner_stderr_abs=runner_stderr_abs,
                manifest_abs=resolved_manifest_path,
            )
            selected_root = repo_root
            selected_outputs_fallback_used = True
        except Exception as e:
            index_fallback_error = _format_exception(e)

    if selected_record is not None and selected_root is not None:
        try:
            _write_automation_outputs_for_effective_workdir(selected_record, effective_workdir=selected_root)
            return int(wrapper_exit_code)
        except Exception as e:
            # Index exists on selected_root; do not write errors back to any other root.
            error_text = f"automation outputs write failed: {_format_exception(e)}"
            wrapper_exit_code = 1
            try:
                error_record = _build_outputs_failure_record(
                    selected_record,
                    requested_workdir=requested_workdir,
                    effective_workdir=selected_root,
                    runner_artifacts_workdir=selected_root,
                    outputs_fallback_used=selected_outputs_fallback_used,
                    runner_stdout_abs=runner_stdout_abs,
                    runner_stderr_abs=runner_stderr_abs,
                    manifest_abs=resolved_manifest_path,
                    error_text=error_text,
                )
                # Do not retain artifact_index_path on wrapper failure, otherwise queries may
                # prefer the stale index and hide the wrapper error state.
                error_record.pop("artifact_index_path", None)
                _write_automation_outputs_for_effective_workdir(error_record, effective_workdir=selected_root)
            except Exception:
                return 1
            return 1

    # Only when the final effective root still cannot persist artifact_index.json do we treat it as
    # automation_contract_error (even if runner succeeded).
    wrapper_exit_code = 1
    error_text = f"artifact index write failed: {index_primary_error}"
    if index_fallback_error:
        error_text = f"{error_text}; fallback failed: {index_fallback_error}"

    error_record = _build_outputs_failure_record(
        record,
        requested_workdir=requested_workdir,
        effective_workdir=workdir,
        runner_artifacts_workdir=workdir,
        outputs_fallback_used=False,
        runner_stdout_abs=runner_stdout_abs,
        runner_stderr_abs=runner_stderr_abs,
        manifest_abs=resolved_manifest_path,
        error_text=error_text,
    )
    error_record.pop("artifact_index_path", None)

    try:
        write_automation_outputs(error_record, root=automation_root)
    except Exception as e:
        fallback_root = repo_root / "reports" / "workflow" / "automation"
        if fallback_root.resolve() == automation_root.resolve():
            return 1
        try:
            error_record["effective_workdir"] = str(repo_root)
            error_record["outputs_fallback_used"] = True
            error_record["outputs_write_error"] = _format_exception(e)
            write_automation_outputs(error_record, root=fallback_root)
        except Exception:
            return 1

    return 1


def main(argv: list[str] | None = None) -> int:
    from src.cli.commands import run_automation_command

    effective_argv = sys.argv[1:] if argv is None else argv
    return int(run_automation_command(effective_argv, entrypoint=run_workflow_automation_entrypoint))


if __name__ == "__main__":
    raise SystemExit(main())
