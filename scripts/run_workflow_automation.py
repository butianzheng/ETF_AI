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
    build_automation_record,
    generate_automation_run_id,
    parse_workflow_stdout_contract,
    validate_workflow_contract,
    write_automation_outputs,
    write_runner_logs,
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

    runner_stdout_path = _rel_to_workdir(runner_logs_abs.get("runner_stdout_path"), workdir=workdir)
    runner_stderr_path = _rel_to_workdir(runner_logs_abs.get("runner_stderr_path"), workdir=workdir)

    wrapper_exit_code = _normalize_wrapper_exit_code(runner_exit_code)
    contract: dict[str, Any] | None = None
    manifest_payload: dict[str, Any] | None = None
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


def main(argv: list[str] | None = None) -> int:
    from src.cli.commands import run_automation_command

    return int(run_automation_command([] if argv is None else argv))


if __name__ == "__main__":
    raise SystemExit(main())
