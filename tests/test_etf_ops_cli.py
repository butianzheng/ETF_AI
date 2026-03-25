from __future__ import annotations

from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
ENTRY = REPO_ROOT / "scripts" / "etf_ops.py"


def _run_entry(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(ENTRY), *args],
        cwd=str(cwd or REPO_ROOT),
        text=True,
        capture_output=True,
        check=False,
    )


def test_etf_ops_help_lists_top_level_commands():
    proc = _run_entry(["--help"])

    assert proc.returncode == 0
    assert "workflow" in proc.stdout
    assert "automation" in proc.stdout
    assert "daily" in proc.stdout
    assert "research-governance" in proc.stdout
    assert "status" in proc.stdout


def test_etf_ops_help_works_outside_repo_cwd(tmp_path):
    proc = _run_entry(["--help"], cwd=tmp_path)

    assert proc.returncode == 0
    assert "workflow" in proc.stdout


def test_etf_ops_subcommand_help_smoke():
    proc = _run_entry(["workflow", "--help"])

    assert proc.returncode == 0
    assert "run" in proc.stdout
    assert "preflight" in proc.stdout


def test_etf_ops_run_help_smoke_commands():
    checks = [
        ["workflow", "run", "--help"],
        ["workflow", "preflight", "--help"],
        ["automation", "run", "--help"],
        ["daily", "run", "--help"],
        ["research-governance", "run", "--help"],
    ]

    for args in checks:
        proc = _run_entry(args)
        assert proc.returncode == 0, f"help failed for args={args}: {proc.stderr}"
        assert "usage:" in proc.stdout.lower()


def test_automation_run_parser_uses_remainder():
    import src.cli.etf_ops as cli

    parser = cli.build_parser()
    args, unknown = parser.parse_known_args(
        ["automation", "run", "--", "--workdir", "/tmp/wd", "--", "--preflight-only"]
    )

    assert unknown == []
    assert args.runner_args == ["--", "--workdir", "/tmp/wd", "--", "--preflight-only"]


def test_workflow_preflight_appends_preflight_only(monkeypatch):
    import src.cli.etf_ops as cli

    received: list[str] = []

    def _fake(argv: list[str]) -> int:
        received[:] = argv
        return 17

    monkeypatch.setattr(cli, "run_workflow_command", _fake)

    exit_code = cli.main(["workflow", "preflight", "--start-date", "2026-01-01"])

    assert exit_code == 17
    assert received.count("--preflight-only") == 1
    assert "--start-date" in received
    assert "2026-01-01" in received


def test_automation_run_keeps_double_dash_passthrough(monkeypatch):
    import src.cli.etf_ops as cli

    received: list[str] = []

    def _fake(argv: list[str]) -> int:
        received[:] = argv
        return 0

    monkeypatch.setattr(cli, "run_automation_command", _fake)

    exit_code = cli.main(["automation", "run", "--", "--workdir", "/tmp/wd", "--", "--preflight-only"])

    assert exit_code == 0
    assert received == ["--", "--workdir", "/tmp/wd", "--", "--preflight-only"]


def test_workflow_run_does_not_add_wrapper_stdout(monkeypatch, capsys):
    import src.cli.etf_ops as cli

    def _fake(_argv: list[str]) -> int:
        print("run_id=abc")
        print("workflow_status=succeeded")
        return 0

    monkeypatch.setattr(cli, "run_workflow_command", _fake)

    exit_code = cli.main(["workflow", "run", "--start-date", "2026-01-01"])
    out = capsys.readouterr().out

    assert exit_code == 0
    assert out == "run_id=abc\nworkflow_status=succeeded\n"
