from __future__ import annotations

import pytest


def test_daily_legacy_main_forwards_to_shared_adapter(monkeypatch):
    import scripts.daily_run as legacy
    import src.cli.commands as shared

    captured: list[list[str]] = []

    def _fake(argv: list[str], *, entrypoint=None) -> int:
        captured.append(argv)
        return 37

    monkeypatch.setattr(shared, "run_daily_command", _fake)

    exit_code = legacy.main(["--date", "2026-03-24", "--log-level", "DEBUG"])

    assert exit_code == 37
    assert captured == [["--date", "2026-03-24", "--log-level", "DEBUG"]]


@pytest.mark.parametrize(
    ("command_func", "module_name", "entrypoint_name"),
    [
        ("run_workflow_command", "scripts.run_end_to_end_workflow", "run_workflow_entrypoint"),
        ("run_automation_command", "scripts.run_workflow_automation", "run_workflow_automation_entrypoint"),
        ("run_daily_command", "scripts.daily_run", "run_daily_entrypoint"),
        ("run_research_governance_command", "scripts.run_research_governance_pipeline", "run_research_governance_entrypoint"),
    ],
)
def test_shared_command_adapters_call_entrypoints_instead_of_legacy_main(
    monkeypatch,
    command_func: str,
    module_name: str,
    entrypoint_name: str,
):
    import importlib
    import src.cli.commands as shared

    module = importlib.import_module(module_name)
    forwarded: list[list[str]] = []

    monkeypatch.setattr(module, "main", lambda _argv=None: (_ for _ in ()).throw(AssertionError("legacy main should not be called")))
    monkeypatch.setattr(module, entrypoint_name, lambda argv: forwarded.append(argv) or 23, raising=False)

    exit_code = getattr(shared, command_func)(["--sample-arg"])

    assert exit_code == 23
    assert forwarded == [["--sample-arg"]]


@pytest.mark.parametrize(
    ("module_name", "main_func_name", "shared_func_name", "entrypoint_name", "argv_tail"),
    [
        (
            "scripts.run_end_to_end_workflow",
            "main",
            "run_workflow_command",
            "run_workflow_entrypoint",
            ["--preflight-only", "--start-date", "2026-01-01"],
        ),
        (
            "scripts.run_workflow_automation",
            "main",
            "run_automation_command",
            "run_workflow_automation_entrypoint",
            ["--workdir", "/tmp/compat", "--", "--preflight-only"],
        ),
        (
            "scripts.daily_run",
            "main",
            "run_daily_command",
            "run_daily_entrypoint",
            ["--date", "2026-03-24", "--execute"],
        ),
        (
            "scripts.run_research_governance_pipeline",
            "main",
            "run_research_governance_command",
            "run_research_governance_entrypoint",
            ["--start-date", "2026-01-01", "--end-date", "2026-03-24"],
        ),
    ],
)
def test_legacy_main_with_none_forwards_sys_argv_and_current_entrypoint(
    monkeypatch,
    module_name: str,
    main_func_name: str,
    shared_func_name: str,
    entrypoint_name: str,
    argv_tail: list[str],
):
    import importlib
    import src.cli.commands as shared

    module = importlib.import_module(module_name)
    captured: list[tuple[list[str], object]] = []

    def _fake(argv: list[str], *, entrypoint=None) -> int:
        captured.append((argv, entrypoint))
        return 19

    monkeypatch.setattr(shared, shared_func_name, _fake)
    monkeypatch.setattr(module.sys, "argv", ["legacy.py", *argv_tail])

    exit_code = getattr(module, main_func_name)()

    assert exit_code == 19
    assert captured == [(argv_tail, getattr(module, entrypoint_name))]


def test_shared_command_adapter_accepts_explicit_entrypoint_without_import(monkeypatch):
    import src.cli.commands as shared

    called: list[list[str]] = []

    def _entrypoint(argv: list[str]) -> int:
        called.append(argv)
        return 41

    exit_code = shared.run_daily_command(["--date", "2026-03-24"], entrypoint=_entrypoint)

    assert exit_code == 41
    assert called == [["--date", "2026-03-24"]]


def test_legacy_workflow_help_mentions_unified_entrypoint(capsys):
    import scripts.run_end_to_end_workflow as legacy

    with pytest.raises(SystemExit) as ex:
        legacy.run_workflow_entrypoint(["--help"])

    assert ex.value.code == 0
    out = capsys.readouterr().out
    assert "兼容入口，推荐改用 `python scripts/etf_ops.py ...`" in out


def test_legacy_workflow_automation_help_mentions_unified_entrypoint(capsys):
    import scripts.run_workflow_automation as legacy

    with pytest.raises(SystemExit) as ex:
        legacy.run_workflow_automation_entrypoint(["--help"])

    assert ex.value.code == 0
    out = capsys.readouterr().out
    assert "兼容入口，推荐改用 `python scripts/etf_ops.py ...`" in out


def test_legacy_research_governance_help_mentions_unified_entrypoint(capsys):
    import scripts.run_research_governance_pipeline as legacy

    with pytest.raises(SystemExit) as ex:
        legacy.run_research_governance_entrypoint(["--help"])

    assert ex.value.code == 0
    out = capsys.readouterr().out
    assert "兼容入口，推荐改用 `python scripts/etf_ops.py ...`" in out
