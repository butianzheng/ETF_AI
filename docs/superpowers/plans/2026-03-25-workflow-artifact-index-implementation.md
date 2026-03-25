# Workflow Artifact 索引层 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `workflow/automation` 链路增加稳定的 per-run artifact index，并在统一 CLI 中补齐 `status runs` / `status show` 诊断入口，同时保持现有 `latest_run.json` / `run_history.jsonl` / `status latest` 兼容行为。

**Architecture:** 新增 `src/workflow/automation_index.py` 作为索引写盘与查询层，负责 per-run `artifact_index.json` 组装、history 扫描、latest/runs/show 查询 API、legacy fallback 重建和路径解析；`scripts/run_workflow_automation.py` 在确定最终 `effective_workdir` 后统一写出 artifact index 与 latest/history 指针；`src/cli/status.py` 只负责命令接线与文本/JSON 输出，查询逻辑优先复用 `automation_index.py`。现有 latest/history schema 保留，只增量加 `artifact_index_path`。

**Tech Stack:** Python 3、argparse、pathlib、json、pytest、现有 automation wrapper / unified CLI / workflow artifact 目录结构

---

## 文件边界

### Create

- `src/workflow/automation_index.py`
- `tests/test_workflow_artifact_index.py`

### Modify

- `scripts/run_workflow_automation.py`
- `src/cli/etf_ops.py`
- `src/cli/status.py`
- `tests/test_workflow_automation_runner.py`
- `tests/test_workflow_automation_cli_smoke.py`
- `tests/test_etf_ops_cli.py`
- `tests/test_etf_ops_status.py`
- `README.md`
- `tasks/todo.md`

### Verify Only

- `src/workflow/automation.py`
- `src/workflow/manifest.py`
- `tests/test_workflow_automation.py`
- `tests/test_end_to_end_workflow_runner.py`
- `tests/test_end_to_end_workflow_runner_cli_smoke.py`
- `tests/test_research_governance_pipeline.py`
- `tests/test_research_governance_pipeline_cli_smoke.py`

## 实施任务

### Task 1: 新增 artifact index helper，并锁定 schema、查询 API 与 legacy fallback 语义

**Files:**
- Create: `src/workflow/automation_index.py`
- Create: `tests/test_workflow_artifact_index.py`
- Verify: `src/workflow/automation.py`

- [ ] **Step 1: 先写 failing tests，锁定 index payload、history 扫描和 legacy fallback 行为**

在 `tests/test_workflow_artifact_index.py` 中先写最小覆盖：

```python
from __future__ import annotations

import json
from pathlib import Path


def test_build_artifact_index_uses_complete_schema_and_effective_workdir_relative_paths(tmp_path):
    from src.workflow.automation_index import build_artifact_index

    effective_root = tmp_path / "effective"
    payload = build_artifact_index(
        record={
            "automation_run_id": "auto-001",
            "run_id": "wf-001",
            "workflow_status": "blocked",
            "automation_started_at": "2026-03-25T08:00:00Z",
            "automation_finished_at": "2026-03-25T08:01:00Z",
            "wrapper_exit_code": 2,
            "runner_process_exit_code": 2,
            "workflow_manifest": "reports/workflow/runs/wf-001/workflow_manifest.json",
            "runner_stdout_path": "reports/workflow/automation/runs/auto-001/runner_stdout.log",
            "runner_stderr_path": "reports/workflow/automation/runs/auto-001/runner_stderr.log",
            "health_check_report_path": None,
            "post_publish_health_check_report_path": None,
            "research_governance_pipeline_summary_path": "reports/governance/pipeline/wf-001.json",
            "blocked_reasons": ["REGIME_MISMATCH"],
            "failed_step": None,
            "publish_executed": False,
            "suggested_next_action": "inspect blocked_reasons and governance review status",
            "requested_workdir": str(tmp_path / "requested"),
            "effective_workdir": str(effective_root),
            "outputs_fallback_used": True,
        },
        effective_workdir=effective_root,
        created_at="2026-03-25T08:01:02Z",
    )

    assert payload["source"] == "artifact_index"
    assert payload["automation_run_id"] == "auto-001"
    assert payload["run_id"] == "wf-001"
    assert payload["workflow_status"] == "blocked"
    assert payload["automation_started_at"] == "2026-03-25T08:00:00Z"
    assert payload["automation_finished_at"] == "2026-03-25T08:01:00Z"
    assert payload["wrapper_exit_code"] == 2
    assert payload["runner_process_exit_code"] == 2
    assert payload["manifest_path"] == "reports/workflow/runs/wf-001/workflow_manifest.json"
    assert payload["runner_stdout_path"] == "reports/workflow/automation/runs/auto-001/runner_stdout.log"
    assert payload["runner_stderr_path"] == "reports/workflow/automation/runs/auto-001/runner_stderr.log"
    assert payload["health_check_report_path"] is None
    assert payload["post_publish_health_check_report_path"] is None
    assert payload["research_governance_pipeline_summary_path"] == "reports/governance/pipeline/wf-001.json"
    assert payload["blocked_reasons"] == ["REGIME_MISMATCH"]
    assert payload["failed_step"] is None
    assert payload["suggested_next_action"] == "inspect blocked_reasons and governance review status"
    assert payload["publish_executed"] is False
    assert payload["created_at"] == "2026-03-25T08:01:02Z"
    assert payload["requested_workdir"] == str(tmp_path / "requested")
    assert payload["effective_workdir"] == str(effective_root)
    assert payload["outputs_fallback_used"] is True


def test_iter_history_records_skips_bad_lines_and_keeps_order(tmp_path):
    from src.workflow.automation_index import iter_history_records

    history_path = tmp_path / "reports" / "workflow" / "automation" / "run_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        "\n".join(
            [
                json.dumps({"automation_run_id": "auto-001", "automation_finished_at": "2026-03-25T08:01:00Z"}),
                "{bad json",
                json.dumps({"automation_run_id": "auto-002", "automation_finished_at": "2026-03-25T08:02:00Z"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    records = list(iter_history_records(tmp_path))
    assert [record["automation_run_id"] for record in records] == ["auto-001", "auto-002"]


def test_find_run_view_prefers_automation_run_id_then_latest_workflow_run_id(tmp_path):
    from src.workflow.automation_index import find_run_view

    history_path = tmp_path / "reports" / "workflow" / "automation" / "run_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "automation_run_id": "auto-old",
                        "run_id": "wf-dup",
                        "workflow_status": "failed",
                        "automation_started_at": "2026-03-25T08:00:00Z",
                        "automation_finished_at": "2026-03-25T08:01:00Z",
                        "wrapper_exit_code": 1,
                        "runner_process_exit_code": 1,
                        "workflow_manifest": "reports/workflow/runs/wf-dup/workflow_manifest.json",
                        "runner_stdout_path": "reports/workflow/automation/runs/auto-old/runner_stdout.log",
                        "runner_stderr_path": "reports/workflow/automation/runs/auto-old/runner_stderr.log",
                        "blocked_reasons": [],
                        "publish_executed": False,
                        "requested_workdir": str(tmp_path),
                        "effective_workdir": str(tmp_path),
                    }
                ),
                json.dumps(
                    {
                        "automation_run_id": "auto-new",
                        "run_id": "wf-dup",
                        "workflow_status": "succeeded",
                        "automation_started_at": "2026-03-25T09:00:00Z",
                        "automation_finished_at": "2026-03-25T09:01:00Z",
                        "wrapper_exit_code": 0,
                        "runner_process_exit_code": 0,
                        "workflow_manifest": "reports/workflow/runs/wf-dup/workflow_manifest.json",
                        "runner_stdout_path": "reports/workflow/automation/runs/auto-new/runner_stdout.log",
                        "runner_stderr_path": "reports/workflow/automation/runs/auto-new/runner_stderr.log",
                        "blocked_reasons": [],
                        "publish_executed": False,
                        "requested_workdir": str(tmp_path),
                        "effective_workdir": str(tmp_path),
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    by_automation = find_run_view(tmp_path, run_id="auto-old")
    by_workflow = find_run_view(tmp_path, run_id="wf-dup")
    assert by_automation["automation_run_id"] == "auto-old"
    assert by_workflow["automation_run_id"] == "auto-new"


def test_rebuild_legacy_detail_view_from_latest_record(tmp_path):
    from src.workflow.automation_index import rebuild_legacy_detail_view

    payload = rebuild_legacy_detail_view(
        {
            "automation_run_id": "auto-003",
            "run_id": "wf-003",
            "workflow_status": "failed",
            "automation_started_at": "2026-03-25T09:00:00Z",
            "automation_finished_at": "2026-03-25T09:01:00Z",
            "wrapper_exit_code": 1,
            "runner_process_exit_code": 1,
            "workflow_manifest": "reports/workflow/runs/wf-003/workflow_manifest.json",
            "runner_stdout_path": "reports/workflow/automation/runs/auto-003/runner_stdout.log",
            "runner_stderr_path": "reports/workflow/automation/runs/auto-003/runner_stderr.log",
            "failed_step": "preflight",
            "blocked_reasons": [],
            "publish_executed": False,
            "requested_workdir": str(tmp_path),
            "effective_workdir": str(tmp_path),
        },
        effective_workdir=tmp_path,
        source="legacy_fallback",
    )

    assert payload["source"] == "legacy_fallback"
    assert payload["run_id"] == "wf-003"
    assert payload["status"] == "failed"
    assert payload["manifest_path"] == str(
        tmp_path / "reports" / "workflow" / "runs" / "wf-003" / "workflow_manifest.json"
    )
```

- [ ] **Step 2: 跑 Task 1 测试，确认 helper 还不存在**

Run: `pytest tests/test_workflow_artifact_index.py -q`

Expected:
- FAIL
- 推荐失败形态：`ModuleNotFoundError: No module named 'src.workflow.automation_index'`

- [ ] **Step 3: 实现索引 helper，最小闭合 payload 组装、history 扫描和 fallback 重建**

在 `src/workflow/automation_index.py` 中实现：

- `build_artifact_index(record, *, effective_workdir, created_at)`
- `artifact_index_relpath(automation_run_id)`
- `write_artifact_index(payload, *, effective_workdir)`
- `iter_history_records(root)`
- `load_latest_run_view(root)`
- `list_run_views(root, *, limit)`
- `find_run_view(root, *, run_id)`
- `rebuild_legacy_detail_view(record, *, effective_workdir, source)`

要求：

- 所有相对路径都相对 `effective_workdir`
- `iter_history_records()` 默认跳过坏行/截断尾行，不抛异常
- `build_artifact_index()` 必须锁定完整 schema：缺失字段也要显式保留 `null`
- `blocked_reasons` 必须始终归一化为 list
- `load_latest_run_view()` / `list_run_views()` / `find_run_view()` 负责实现 spec 里的 latest/runs/show 查询与 fallback 规则；CLI 层不再自行解析 history/index
- legacy fallback 视图输出统一字段：
  - `source`
  - `automation_run_id`
  - `run_id`
  - `status`
  - `started_at`
  - `finished_at`
  - `wrapper_exit_code`
  - `runner_process_exit_code`
  - `manifest_path`
  - `runner_stdout_path`
  - `runner_stderr_path`
  - `failed_step`
  - `blocked_reasons`
  - `publish_executed`
  - `requested_workdir`
  - `effective_workdir`

- [ ] **Step 4: 回跑 Task 1 测试，确认 helper 边界闭合**

Run: `pytest tests/test_workflow_artifact_index.py -q`

Expected:
- PASS

- [ ] **Step 5: 提交 Task 1**

```bash
git add src/workflow/automation_index.py tests/test_workflow_artifact_index.py
git commit -m "feat: add workflow artifact index helper"
```

### Task 2: 集成 automation wrapper 写盘路径，确保 artifact index 与 latest/history 同根输出

**Files:**
- Modify: `scripts/run_workflow_automation.py`
- Modify: `tests/test_workflow_automation_runner.py`
- Modify: `tests/test_workflow_automation_cli_smoke.py`
- Verify: `src/workflow/automation.py`

- [ ] **Step 1: 先写 failing tests，锁定 index 写盘、pointer 回填与 fallback 语义**

在 `tests/test_workflow_automation_runner.py` 中新增：

```python
def test_workflow_automation_runner_writes_artifact_index_and_backfills_pointer(tmp_path, monkeypatch):
    import json
    import scripts.run_workflow_automation as cli

    manifest_path = _write_manifest(tmp_path, status="preflight_only", exit_code=0)

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                "run_id=20260325T010203Z-abcd1234\n"
                "workflow_manifest=reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json\n"
                "workflow_status=preflight_only\n"
                "publish_executed=false\n"
            ),
            stderr="",
        ),
    )

    assert cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"]) == 0

    latest = json.loads((tmp_path / "reports/workflow/automation/latest_run.json").read_text(encoding="utf-8"))
    assert "artifact_index_path" in latest

    artifact_index = tmp_path / latest["artifact_index_path"]
    assert artifact_index.exists()
    payload = json.loads(artifact_index.read_text(encoding="utf-8"))
    assert payload["manifest_path"] == "reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json"
    assert payload["effective_workdir"] == str(tmp_path)


def test_workflow_automation_runner_rebuilds_artifact_index_after_primary_write_failure(tmp_path, monkeypatch):
    import json
    import scripts.run_workflow_automation as cli

    _write_manifest(tmp_path, status="preflight_only", exit_code=0)

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                "run_id=20260325T010203Z-abcd1234\n"
                "workflow_manifest=reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json\n"
                "workflow_status=preflight_only\n"
                "publish_executed=false\n"
            ),
            stderr="",
        ),
    )

    real_write = cli.write_artifact_index
    calls = {"count": 0}

    def _flaky_write(*args, **kwargs):
        calls["count"] += 1
        if calls["count"] == 1:
            raise OSError("primary root write failed")
        return real_write(*args, **kwargs)

    monkeypatch.setattr(cli, "write_artifact_index", _flaky_write)

    assert cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"]) == 0

    latest = json.loads((Path(cli.PROJECT_ROOT) / "reports/workflow/automation/latest_run.json").read_text(encoding="utf-8"))
    assert latest["outputs_fallback_used"] is True
    assert latest["effective_workdir"] == str(Path(cli.PROJECT_ROOT).resolve())

    artifact_index = Path(cli.PROJECT_ROOT) / latest["artifact_index_path"]
    assert artifact_index.exists()


def test_workflow_automation_runner_returns_one_when_final_artifact_index_write_fails(tmp_path, monkeypatch):
    import json
    import scripts.run_workflow_automation as cli

    _write_manifest(tmp_path, status="preflight_only", exit_code=0)

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                "run_id=20260325T010203Z-abcd1234\n"
                "workflow_manifest=reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json\n"
                "workflow_status=preflight_only\n"
                "publish_executed=false\n"
            ),
            stderr="",
        ),
    )
    monkeypatch.setattr(cli, "write_artifact_index", lambda *args, **kwargs: (_ for _ in ()).throw(OSError("index failed")))

    assert cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"]) == 1
    latest_run = json.loads((tmp_path / "reports/workflow/automation/latest_run.json").read_text(encoding="utf-8"))
    attention = json.loads((tmp_path / "reports/workflow/automation/latest_attention.json").read_text(encoding="utf-8"))
    assert latest_run["failed_step"] == "automation_contract_error"
    assert "index failed" in latest_run["suggested_next_action"]
    assert attention["attention_type"] == "automation_contract_error"
```

并在 `tests/test_workflow_automation_cli_smoke.py` 中补：

- `latest_run.json` 继续保留现有富字段
- 新增 `artifact_index_path`
- `artifact_index.json` 真正落盘

- [ ] **Step 2: 跑 Task 2 测试，确认当前 wrapper 还没写 artifact index**

Run: `pytest tests/test_workflow_automation_runner.py tests/test_workflow_automation_cli_smoke.py -q -k "artifact_index or fallback_rebuilds or latest_run_json"`

Expected:
- FAIL
- 推荐失败形态：`KeyError: 'artifact_index_path'`、`assert artifact_index.exists()`，或“最终 index 写失败仍返回 0”

- [ ] **Step 3: 重构 wrapper 写盘流程，先确定最终根目录，再基于最终根目录组装 payload**

在 `scripts/run_workflow_automation.py` 中调整为：

- 保持现有 `requested_workdir` / `effective_workdir` / `outputs_fallback_used` 语义
- 先执行 runner、拿到 contract / manifest / logs
- 再确定最终输出根目录
- 基于最终 `effective_workdir`：
  - 调 `build_artifact_index(...)`
  - 写 `artifact_index.json`
  - 把 `artifact_index_path` 回填到 record
  - 再写 `latest_run.json` / `run_history.jsonl` / `latest_attention.*`
- 若主输出根失败，可沿用 repo root fallback
- 只有最终根仍无法写出 `artifact_index.json` 时，才视为 `automation_contract_error`

实现要求：

- 不能先按旧根目录组装 payload，再在 fallback 后复用
- latest/history 继续保留 current schema，不做字段删除
- `artifact_index_path` 必须是相对 `effective_workdir` 的相对路径

- [ ] **Step 4: 回跑 Task 2 测试**

Run: `pytest tests/test_workflow_automation_runner.py tests/test_workflow_automation_cli_smoke.py -q`

Expected:
- PASS
- latest/history 仍兼容现有字段
- 新增 `artifact_index_path`

- [ ] **Step 5: 提交 Task 2**

```bash
git add scripts/run_workflow_automation.py tests/test_workflow_automation_runner.py tests/test_workflow_automation_cli_smoke.py
git commit -m "feat: persist workflow artifact index records"
```

### Task 3: 扩展统一 CLI 状态入口，补齐 `status runs` / `status show`

**Files:**
- Modify: `src/cli/etf_ops.py`
- Modify: `src/cli/status.py`
- Modify: `tests/test_etf_ops_cli.py`
- Modify: `tests/test_etf_ops_status.py`
- Verify: `src/workflow/automation_index.py`

- [ ] **Step 1: 先写 failing tests，锁定新命令树和状态查询矩阵**

在 `tests/test_etf_ops_cli.py` 中补：

```python
def test_etf_ops_status_subcommand_help_smoke():
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "etf_ops.py"

    for argv in (["status", "latest", "--help"], ["status", "runs", "--help"], ["status", "show", "--help"]):
        proc = subprocess.run(
            [sys.executable, str(script), *argv],
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0
```

在 `tests/test_etf_ops_status.py` 中补最小覆盖：

```python
def test_status_latest_prefers_artifact_index_pointer(tmp_path):
    root = tmp_path / "artifacts"
    _write_json(
        root / "reports/workflow/automation/runs/auto-010/artifact_index.json",
        {
            "source": "artifact_index",
            "automation_run_id": "auto-010",
            "run_id": "wf-010",
            "workflow_status": "blocked",
            "automation_started_at": "2026-03-25T08:00:00Z",
            "automation_finished_at": "2026-03-25T08:01:00Z",
            "wrapper_exit_code": 2,
            "runner_process_exit_code": 2,
            "manifest_path": "reports/workflow/runs/wf-010/workflow_manifest.json",
            "runner_stdout_path": "reports/workflow/automation/runs/auto-010/runner_stdout.log",
            "runner_stderr_path": "reports/workflow/automation/runs/auto-010/runner_stderr.log",
            "blocked_reasons": ["REGIME_MISMATCH"],
            "failed_step": None,
            "publish_executed": False,
            "requested_workdir": str(root),
            "effective_workdir": str(root),
            "created_at": "2026-03-25T08:01:02Z",
        },
    )
    _write_json(
        root / "reports/workflow/automation/latest_run.json",
        {
            "automation_run_id": "auto-010",
            "run_id": "wf-010",
            "workflow_status": "blocked",
            "automation_started_at": "2026-03-25T08:00:00Z",
            "automation_finished_at": "2026-03-25T08:01:00Z",
            "publish_executed": False,
            "workflow_manifest": "reports/workflow/runs/wf-010/workflow_manifest.json",
            "artifact_index_path": "reports/workflow/automation/runs/auto-010/artifact_index.json",
            "requested_workdir": str(root),
            "effective_workdir": str(root),
        },
    )

    proc = _run_entry(["status", "latest", "--workdir", str(root), "--json"])
    payload = json.loads(proc.stdout)
    assert payload["source"] == "artifact_index"
    assert payload["run_id"] == "wf-010"


def test_status_latest_returns_one_when_index_file_is_corrupt(tmp_path):
    root = tmp_path / "artifacts"
    latest_path = root / "reports/workflow/automation/latest_run.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text(
        json.dumps(
            {
                "automation_run_id": "auto-011",
                "run_id": "wf-011",
                "workflow_status": "failed",
                "automation_started_at": "2026-03-25T08:00:00Z",
                "automation_finished_at": "2026-03-25T08:01:00Z",
                "publish_executed": False,
                "workflow_manifest": "reports/workflow/runs/wf-011/workflow_manifest.json",
                "artifact_index_path": "reports/workflow/automation/runs/auto-011/artifact_index.json",
                "requested_workdir": str(root),
                "effective_workdir": str(root),
            }
        ),
        encoding="utf-8",
    )
    bad_index = root / "reports/workflow/automation/runs/auto-011/artifact_index.json"
    bad_index.parent.mkdir(parents=True, exist_ok=True)
    bad_index.write_text("{bad json", encoding="utf-8")

    proc = _run_entry(["status", "latest", "--workdir", str(root), "--json"])
    assert proc.returncode == 1
    assert proc.stdout == ""


def test_status_latest_returns_one_when_latest_run_json_is_corrupt(tmp_path):
    root = tmp_path / "artifacts"
    latest_path = root / "reports/workflow/automation/latest_run.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text("{bad json", encoding="utf-8")

    proc = _run_entry(["status", "latest", "--workdir", str(root), "--json"])
    assert proc.returncode == 1
    assert proc.stdout == ""


def test_status_latest_falls_back_to_summary_only_when_latest_missing(tmp_path):
    root = tmp_path / "artifacts"
    _write_json(
        root / "reports/workflow/end_to_end_workflow_summary.json",
        {
            "run_id": "wf-summary",
            "status": "failed",
            "started_at": "2026-03-25T07:00:00Z",
            "finished_at": "2026-03-25T07:01:00Z",
            "workflow_manifest_path": "reports/workflow/runs/wf-summary/workflow_manifest.json",
            "failed_step": "preflight",
            "publish_result": {"executed": False},
            "research_governance_result": {"blocked_reasons": []},
        },
    )

    proc = _run_entry(["status", "latest", "--workdir", str(root), "--json"])
    payload = json.loads(proc.stdout)
    assert payload["source"] == "workflow_summary_fallback"


def test_status_latest_falls_back_to_latest_when_artifact_index_pointer_missing_or_target_missing(tmp_path):
    root = tmp_path / "artifacts"
    latest_payload = {
        "automation_run_id": "auto-013",
        "run_id": "wf-013",
        "workflow_status": "failed",
        "automation_started_at": "2026-03-25T08:00:00Z",
        "automation_finished_at": "2026-03-25T08:01:00Z",
        "publish_executed": False,
        "workflow_manifest": "reports/workflow/runs/wf-013/workflow_manifest.json",
        "failed_step": "preflight",
        "blocked_reasons": [],
        "suggested_next_action": "inspect failed_step=preflight and workflow manifest",
        "requested_workdir": str(root),
        "effective_workdir": str(root),
    }

    _write_json(root / "reports/workflow/automation/latest_run.json", latest_payload)
    proc_no_pointer = _run_entry(["status", "latest", "--workdir", str(root), "--json"])
    payload_no_pointer = json.loads(proc_no_pointer.stdout)
    assert payload_no_pointer["run_id"] == "wf-013"
    assert payload_no_pointer["status"] == "failed"

    latest_payload["artifact_index_path"] = "reports/workflow/automation/runs/auto-013/artifact_index.json"
    _write_json(root / "reports/workflow/automation/latest_run.json", latest_payload)
    proc_missing_target = _run_entry(["status", "latest", "--workdir", str(root), "--json"])
    payload_missing_target = json.loads(proc_missing_target.stdout)
    assert payload_missing_target["run_id"] == "wf-013"
    assert payload_missing_target["failed_step"] == "preflight"


def test_status_latest_returns_one_when_summary_is_corrupt(tmp_path):
    root = tmp_path / "artifacts"
    summary_path = root / "reports/workflow/end_to_end_workflow_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text("{bad json", encoding="utf-8")

    proc = _run_entry(["status", "latest", "--workdir", str(root), "--json"])
    assert proc.returncode == 1


def test_status_runs_lists_history_and_skips_bad_lines(tmp_path):
    root = tmp_path / "artifacts"
    history_path = root / "reports/workflow/automation/run_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        "\n".join(
            [
                json.dumps({"automation_run_id": "auto-001", "run_id": "wf-001", "workflow_status": "failed", "automation_finished_at": "2026-03-25T08:00:00Z", "wrapper_exit_code": 1, "failed_step": "preflight", "effective_workdir": str(root)}),
                "{bad json",
                json.dumps({"automation_run_id": "auto-002", "run_id": "wf-002", "workflow_status": "succeeded", "automation_finished_at": "2026-03-25T09:00:00Z", "wrapper_exit_code": 0, "failed_step": None, "effective_workdir": str(root)}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    proc = _run_entry(["status", "runs", "--workdir", str(root), "--json"])
    payload = json.loads(proc.stdout)
    assert [item["automation_run_id"] for item in payload["runs"]] == ["auto-002", "auto-001"]


def test_status_runs_uses_limit_and_marks_missing_index_fallback(tmp_path):
    root = tmp_path / "artifacts"
    history_path = root / "reports/workflow/automation/run_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        "\n".join(
            [
                json.dumps({"automation_run_id": "auto-001", "run_id": "wf-001", "workflow_status": "failed", "automation_finished_at": "2026-03-25T08:00:00Z", "wrapper_exit_code": 1, "failed_step": "preflight", "artifact_index_path": "reports/workflow/automation/runs/auto-001/artifact_index.json", "effective_workdir": str(root)}),
                json.dumps({"automation_run_id": "auto-002", "run_id": "wf-002", "workflow_status": "blocked", "automation_finished_at": "2026-03-25T09:00:00Z", "wrapper_exit_code": 2, "failed_step": None, "effective_workdir": str(root)}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    proc = _run_entry(["status", "runs", "--workdir", str(root), "--limit", "1", "--json"])
    payload = json.loads(proc.stdout)
    assert len(payload["runs"]) == 1
    assert payload["runs"][0]["automation_run_id"] == "auto-002"

    proc_all = _run_entry(["status", "runs", "--workdir", str(root), "--json"])
    payload_all = json.loads(proc_all.stdout)
    assert payload_all["runs"][1]["source"] == "legacy_fallback"


def test_status_runs_returns_one_when_history_has_no_valid_records(tmp_path):
    root = tmp_path / "artifacts"
    history_path = root / "reports/workflow/automation/run_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text("{bad json\n", encoding="utf-8")

    proc = _run_entry(["status", "runs", "--workdir", str(root), "--json"])
    assert proc.returncode == 1


def test_status_show_matches_latest_record_for_duplicate_workflow_run_id(tmp_path):
    root = tmp_path / "artifacts"
    history_path = root / "reports/workflow/automation/run_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        "\n".join(
            [
                json.dumps({"automation_run_id": "auto-old", "run_id": "wf-dup", "workflow_status": "failed", "automation_finished_at": "2026-03-25T08:00:00Z", "wrapper_exit_code": 1, "effective_workdir": str(root)}),
                json.dumps({"automation_run_id": "auto-new", "run_id": "wf-dup", "workflow_status": "succeeded", "automation_finished_at": "2026-03-25T09:00:00Z", "wrapper_exit_code": 0, "effective_workdir": str(root)}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    proc = _run_entry(["status", "show", "--run-id", "wf-dup", "--workdir", str(root), "--json"])
    payload = json.loads(proc.stdout)
    assert payload["automation_run_id"] == "auto-new"


def test_status_show_prefers_exact_automation_run_id_match(tmp_path):
    root = tmp_path / "artifacts"
    history_path = root / "reports/workflow/automation/run_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps({"automation_run_id": "auto-011", "run_id": "auto-011", "workflow_status": "failed", "automation_finished_at": "2026-03-25T08:00:00Z", "wrapper_exit_code": 1, "effective_workdir": str(root)})
        + "\n",
        encoding="utf-8",
    )

    proc = _run_entry(["status", "show", "--run-id", "auto-011", "--workdir", str(root), "--json"])
    payload = json.loads(proc.stdout)
    assert payload["automation_run_id"] == "auto-011"


def test_status_show_returns_one_for_corrupt_index_and_not_found(tmp_path):
    root = tmp_path / "artifacts"
    history_path = root / "reports/workflow/automation/run_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps({"automation_run_id": "auto-012", "run_id": "wf-012", "workflow_status": "blocked", "automation_finished_at": "2026-03-25T08:00:00Z", "wrapper_exit_code": 2, "artifact_index_path": "reports/workflow/automation/runs/auto-012/artifact_index.json", "effective_workdir": str(root)})
        + "\n",
        encoding="utf-8",
    )
    bad_index = root / "reports/workflow/automation/runs/auto-012/artifact_index.json"
    bad_index.parent.mkdir(parents=True, exist_ok=True)
    bad_index.write_text("{bad json", encoding="utf-8")

    proc_bad = _run_entry(["status", "show", "--run-id", "wf-012", "--workdir", str(root), "--json"])
    proc_missing = _run_entry(["status", "show", "--run-id", "not-found", "--workdir", str(root), "--json"])
    assert proc_bad.returncode == 1
    assert proc_missing.returncode == 1


def test_status_show_falls_back_when_index_target_missing_and_returns_absolute_paths(tmp_path):
    root = tmp_path / "artifacts"
    history_path = root / "reports/workflow/automation/run_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(
            {
                "automation_run_id": "auto-014",
                "run_id": "wf-014",
                "workflow_status": "blocked",
                "automation_started_at": "2026-03-25T08:00:00Z",
                "automation_finished_at": "2026-03-25T08:01:00Z",
                "wrapper_exit_code": 2,
                "runner_process_exit_code": 2,
                "workflow_manifest": "reports/workflow/runs/wf-014/workflow_manifest.json",
                "runner_stdout_path": "reports/workflow/automation/runs/auto-014/runner_stdout.log",
                "runner_stderr_path": "reports/workflow/automation/runs/auto-014/runner_stderr.log",
                "artifact_index_path": "reports/workflow/automation/runs/auto-014/artifact_index.json",
                "blocked_reasons": ["REGIME_MISMATCH"],
                "publish_executed": False,
                "requested_workdir": str(root),
                "effective_workdir": str(root),
            }
        )
        + "\n",
        encoding="utf-8",
    )

    proc = _run_entry(["status", "show", "--run-id", "wf-014", "--workdir", str(root), "--json"])
    payload = json.loads(proc.stdout)
    assert payload["source"] == "legacy_fallback"
    assert payload["manifest_path"] == str(root / "reports/workflow/runs/wf-014/workflow_manifest.json")


def test_status_show_uses_later_history_row_when_finished_at_ties(tmp_path):
    root = tmp_path / "artifacts"
    history_path = root / "reports/workflow/automation/run_history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        "\n".join(
            [
                json.dumps({"automation_run_id": "auto-a", "run_id": "wf-tie", "workflow_status": "failed", "automation_finished_at": "2026-03-25T08:01:00Z", "wrapper_exit_code": 1, "effective_workdir": str(root)}),
                json.dumps({"automation_run_id": "auto-b", "run_id": "wf-tie", "workflow_status": "blocked", "automation_finished_at": "2026-03-25T08:01:00Z", "wrapper_exit_code": 2, "effective_workdir": str(root)}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    proc = _run_entry(["status", "show", "--run-id", "wf-tie", "--workdir", str(root), "--json"])
    payload = json.loads(proc.stdout)
    assert payload["automation_run_id"] == "auto-b"
```

- [ ] **Step 2: 跑 Task 3 测试，确认新 status 子命令尚未实现**

Run: `pytest tests/test_etf_ops_cli.py tests/test_etf_ops_status.py -q -k "status_subcommand_help_smoke or artifact_index_pointer or status_runs or status_show"`

Expected:
- FAIL
- 推荐失败形态：`invalid choice: 'runs'` / `invalid choice: 'show'`

- [ ] **Step 3: 实现 status 查询层与命令树扩展**

在 `src/cli/etf_ops.py` 中：

- 为 `status` 增加：
  - `runs`
  - `show --run-id <id>`
- 两者都支持 `--workdir`
- `runs` 支持 `--limit`、`--json`
- `show` 支持 `--json`

在 `src/cli/status.py` 中实现：

- `run_status_latest(...)` 只负责调用 `automation_index.py` 的 latest 查询 API 并格式化输出
- `run_status_runs(...)` 只负责调用 `automation_index.py` 的 runs 查询 API 并格式化输出
- `run_status_show(...)` 只负责调用 `automation_index.py` 的 show 查询 API 并格式化输出
- 共享文本/JSON 输出 helper
- 文本/JSON 输出 helper

实现要求：

- `latest_run.json` 缺失才允许 fallback 到 workflow summary
- `latest_run.json` 或 `artifact_index.json` 若存在但损坏/缺字段，返回 `1`
- `status runs` 坏 history 行默认跳过
- `status show` 命中重复 workflow `run_id` 时返回最近完成的一条
- `status show` 对精确 `automation_run_id` 命中优先于 workflow `run_id`
- `status runs` / `status show` 需要覆盖 missing index fallback、corrupt index 错误、not found、`--limit`、绝对路径 JSON 输出
- `--json` 模式下 stdout 不混入非 JSON 文本

- [ ] **Step 4: 回跑 Task 3 测试**

Run: `pytest tests/test_etf_ops_cli.py tests/test_etf_ops_status.py -q`

Expected:
- PASS
- `status latest/runs/show` 全部可用

- [ ] **Step 5: 提交 Task 3**

```bash
git add src/cli/etf_ops.py src/cli/status.py tests/test_etf_ops_cli.py tests/test_etf_ops_status.py
git commit -m "feat: add artifact index status commands"
```

### Task 4: 更新 README / 任务跟踪，并完成最终聚焦回归

**Files:**
- Modify: `README.md`
- Modify: `tasks/todo.md`
- Verify: `tests/test_workflow_artifact_index.py`
- Verify: `tests/test_workflow_automation.py`
- Verify: `tests/test_workflow_automation_runner.py`
- Verify: `tests/test_workflow_automation_cli_smoke.py`
- Verify: `tests/test_etf_ops_cli.py`
- Verify: `tests/test_etf_ops_status.py`
- Verify: `tests/test_end_to_end_workflow_runner.py`
- Verify: `tests/test_end_to_end_workflow_runner_cli_smoke.py`
- Verify: `tests/test_research_governance_pipeline.py`
- Verify: `tests/test_research_governance_pipeline_cli_smoke.py`

- [ ] **Step 1: 更新 README，补 artifact 诊断命令与 fallback 说明**

README 至少要更新：

- `status latest` 已优先消费 artifact index
- 增加 `status runs`
- 增加 `status show --run-id <id>`
- 明确 `artifact_index.json`、`artifact_index_path`、`effective_workdir` 的关系
- 说明当 automation 输出回退到 repo root 时，状态查询应指向最终 `effective_workdir`

- [ ] **Step 2: 更新 `tasks/todo.md`，建立本子项目跟踪块**

新增：

- 执行清单（Task 1-4）
- 规划产物（spec / plan）
- 审查状态（spec review / plan review）
- 后续填写 Task 提交、fresh 验证、双审查状态

- [ ] **Step 3: 跑聚焦回归**

Run:

```bash
pytest \
  tests/test_workflow_artifact_index.py \
  tests/test_workflow_automation.py \
  tests/test_workflow_automation_runner.py \
  tests/test_workflow_automation_cli_smoke.py \
  tests/test_etf_ops_cli.py \
  tests/test_etf_ops_status.py \
  tests/test_end_to_end_workflow_runner.py \
  tests/test_end_to_end_workflow_runner_cli_smoke.py \
  tests/test_research_governance_pipeline.py \
  tests/test_research_governance_pipeline_cli_smoke.py \
  -q
```

Expected:
- PASS
- 新索引层不破坏现有 workflow / automation / status 兼容合同

- [ ] **Step 4: 跑全量回归**

Run: `pytest -q`

Expected:
- PASS

- [ ] **Step 5: 提交 Task 4**

```bash
git add README.md tasks/todo.md
git commit -m "docs: document workflow artifact index status flow"
```

## 执行注意事项

- `latest_run.json` / `run_history.jsonl` 在 v1 只允许增量加 `artifact_index_path`，不允许删现有字段。
- 若主输出根失败并回退到 repo root，必须基于最终 `effective_workdir` 重建全部相对路径字段，不能复用旧 payload。
- `status latest` 只在 `latest_run.json` 缺失时回退到 workflow summary；任何“文件存在但损坏/缺字段”的情况都必须返回 `1`。
- `status runs` 对坏 history 行做 best-effort 跳过，但 `status show` 命中的 index 文件若存在且损坏，必须返回 `1`。
- `--json` 模式的 stdout 必须保持纯 JSON，不允许混入说明文本。
- 每个 Task 完成后都要做 fresh verification、spec compliance review、code quality review，再继续下一个 Task。
