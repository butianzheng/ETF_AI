# Local Workflow Automation Wrapper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为现有 workflow runner 增加一个本地自动化消费层：独立 wrapper、文件系统 run 索引、失败 attention 摘要，以及真实子进程 smoke 验证。

**Architecture:** 保持 `scripts/run_end_to_end_workflow.py` 作为唯一业务编排入口；新增 `scripts/run_workflow_automation.py` 作为自动化入口，内部通过子进程真实调用 runner。自动化层的结构化逻辑下沉到 `src/workflow/automation.py`，负责 stdout 合同解析、record 组装、history/latest/attention 写盘和 contract error 结构化处理。业务事实仍以 runner manifest 为准，自动化层只做引用和派生视图。

**Tech Stack:** Python 3、pytest、subprocess、json/jsonl、pathlib、argparse、现有 workflow runner / governance / config 模块

---

## 文件边界

### Create

- `src/workflow/automation.py`
- `scripts/run_workflow_automation.py`
- `tests/test_workflow_automation.py`
- `tests/test_workflow_automation_runner.py`
- `tests/test_workflow_automation_cli_smoke.py`

### Modify

- `src/workflow/__init__.py`
- `README.md`
- `tasks/todo.md`

### Verify Only

- `scripts/run_end_to_end_workflow.py`
- `src/workflow/manifest.py`
- `src/workflow/preflight.py`
- `src/governance_pipeline.py`
- `src/core/config.py`
- `tests/test_end_to_end_workflow_runner.py`
- `tests/test_end_to_end_workflow_runner_cli_smoke.py`

## 实施任务

### Task 1: 抽出自动化辅助模块并锁定索引/attention 合同

**Files:**
- Create: `src/workflow/automation.py`
- Modify: `src/workflow/__init__.py`
- Create: `tests/test_workflow_automation.py`
- Verify: `src/workflow/manifest.py`

- [ ] **Step 1: 先写自动化 helper 单测，锁定 run id、stdout 解析和写盘结构**

在 `tests/test_workflow_automation.py` 中新增最小覆盖：

```python
import json
import re
from datetime import datetime, timezone
from pathlib import Path
import pytest


def test_generate_automation_run_id_is_path_safe():
    from src.workflow.automation import generate_automation_run_id

    run_id = generate_automation_run_id()
    assert re.match(r"^\d{8}T\d{6}Z-[a-z0-9]{8}$", run_id)


def test_parse_workflow_stdout_contract_extracts_required_fields():
    from src.workflow.automation import parse_workflow_stdout_contract

    contract = parse_workflow_stdout_contract(
        "run_id=20260325T010203Z-abcd1234\n"
        "workflow_manifest=reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json\n"
        "workflow_status=blocked\n"
        "publish_executed=false\n"
    )

    assert contract["run_id"] == "20260325T010203Z-abcd1234"
    assert contract["workflow_status"] == "blocked"


def test_write_automation_outputs_writes_history_latest_and_attention(tmp_path):
    from src.workflow.automation import write_automation_outputs

    record = {
        "automation_run_id": "20260325T010203Z-a1b2c3d4",
        "automation_started_at": "2026-03-25T01:02:03Z",
        "automation_finished_at": "2026-03-25T01:02:05Z",
        "runner_command": ["python", "/abs/scripts/run_end_to_end_workflow.py", "--preflight-only"],
        "runner_process_exit_code": 1,
        "wrapper_exit_code": 1,
        "run_id": "20260325T010203Z-abcd1234",
        "workflow_manifest": "reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json",
        "workflow_status": "failed",
        "publish_executed": False,
        "manifest_exit_code": 1,
        "failed_step": "preflight",
        "blocked_reasons": [],
        "health_check_report_path": None,
        "post_publish_health_check_report_path": None,
        "research_governance_pipeline_summary_path": None,
        "runner_stdout_path": "reports/workflow/automation/runs/20260325T010203Z-a1b2c3d4/runner_stdout.log",
        "runner_stderr_path": "reports/workflow/automation/runs/20260325T010203Z-a1b2c3d4/runner_stderr.log",
    }

    paths = write_automation_outputs(record, root=tmp_path / "reports" / "workflow" / "automation")

    assert Path(paths["latest_run_path"]).exists()
    assert Path(paths["latest_attention_json_path"]).exists()
    assert Path(paths["latest_attention_md_path"]).exists()
    history_lines = (
        (tmp_path / "reports" / "workflow" / "automation" / "run_history.jsonl")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()
    )
    assert len(history_lines) == 1
    attention_payload = json.loads(Path(paths["latest_attention_json_path"]).read_text(encoding="utf-8"))
    assert {"attention_type", "automation_run_id", "suggested_next_action"} <= attention_payload.keys()
    attention_md = Path(paths["latest_attention_md_path"]).read_text(encoding="utf-8")
    assert "automation_run_id" in attention_md
    assert "workflow_status" in attention_md
    assert "runner_stdout" in attention_md
    assert "runner_stderr" in attention_md


def test_write_automation_outputs_keeps_existing_attention_on_success(tmp_path):
    from src.workflow.automation import write_automation_outputs

    root = tmp_path / "reports" / "workflow" / "automation"
    failed_record = {
        "automation_run_id": "20260325T010203Z-a1b2c3d4",
        "automation_started_at": "2026-03-25T01:02:03Z",
        "automation_finished_at": "2026-03-25T01:02:05Z",
        "runner_command": ["python", "/abs/scripts/run_end_to_end_workflow.py"],
        "runner_process_exit_code": 1,
        "wrapper_exit_code": 1,
        "run_id": None,
        "workflow_manifest": None,
        "workflow_status": "failed",
        "publish_executed": False,
        "manifest_exit_code": None,
        "failed_step": "automation_contract_error",
        "blocked_reasons": [],
        "health_check_report_path": None,
        "post_publish_health_check_report_path": None,
        "research_governance_pipeline_summary_path": None,
        "runner_stdout_path": "reports/workflow/automation/runs/20260325T010203Z-a1b2c3d4/runner_stdout.log",
        "runner_stderr_path": "reports/workflow/automation/runs/20260325T010203Z-a1b2c3d4/runner_stderr.log",
        "attention_type": "automation_contract_error",
        "suggested_next_action": "check stdout",
    }
    write_automation_outputs(failed_record, root=root)
    attention_before = (root / "latest_attention.json").read_text(encoding="utf-8")

    success_record = dict(failed_record)
    success_record.update(
        {
            "automation_run_id": "20260325T010210Z-e5f6g7h8",
            "runner_process_exit_code": 0,
            "wrapper_exit_code": 0,
            "workflow_status": "preflight_only",
            "attention_type": None,
        }
    )
    write_automation_outputs(success_record, root=root)

    assert (root / "latest_attention.json").read_text(encoding="utf-8") == attention_before


def test_write_automation_outputs_appends_history_without_overwriting(tmp_path):
    from src.workflow.automation import write_automation_outputs

    root = tmp_path / "reports" / "workflow" / "automation"
    base = {
        "automation_started_at": "2026-03-25T01:02:03Z",
        "automation_finished_at": "2026-03-25T01:02:05Z",
        "runner_command": ["python", "/abs/scripts/run_end_to_end_workflow.py"],
        "runner_process_exit_code": 0,
        "wrapper_exit_code": 0,
        "run_id": "20260325T010203Z-abcd1234",
        "workflow_manifest": "reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json",
        "workflow_status": "preflight_only",
        "publish_executed": False,
        "manifest_exit_code": 0,
        "failed_step": None,
        "blocked_reasons": [],
        "health_check_report_path": None,
        "post_publish_health_check_report_path": None,
        "research_governance_pipeline_summary_path": None,
        "runner_stdout_path": "reports/workflow/automation/runs/x/runner_stdout.log",
        "runner_stderr_path": "reports/workflow/automation/runs/x/runner_stderr.log",
    }
    write_automation_outputs({"automation_run_id": "20260325T010203Z-a1b2c3d4", **base}, root=root)
    write_automation_outputs({"automation_run_id": "20260325T010210Z-e5f6g7h8", **base}, root=root)

    history_lines = (root / "run_history.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(history_lines) == 2
    assert "20260325T010203Z-a1b2c3d4" in history_lines[0]
    assert "20260325T010210Z-e5f6g7h8" in history_lines[1]


def test_parse_workflow_contract_error_when_manifest_mismatches():
    from src.workflow.automation import validate_workflow_contract

    contract = {
        "run_id": "20260325T010203Z-abcd1234",
        "workflow_manifest": "reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json",
        "workflow_status": "failed",
        "publish_executed": False,
    }
    manifest_payload = {"run_id": "other", "status": "failed", "exit_code": 1}

    with pytest.raises(Exception):
        validate_workflow_contract(contract, manifest_payload, runner_process_exit_code=1)
```

- [ ] **Step 2: 跑单测，确认模块尚未实现**

Run: `pytest tests/test_workflow_automation.py -q`

Expected:
- FAIL
- 推荐失败形态：`ModuleNotFoundError: No module named 'src.workflow.automation'`

- [ ] **Step 3: 实现最小自动化 helper**

在 `src/workflow/automation.py` 中实现：

- `generate_automation_run_id(now: datetime | None = None) -> str`
- `parse_workflow_stdout_contract(stdout: str) -> dict[str, Any]`
- `validate_workflow_contract(contract, manifest_payload, runner_process_exit_code) -> None`
- `build_automation_record(...) -> dict[str, Any]`
- `write_automation_outputs(record, root: Path) -> dict[str, str]`
- `write_runner_logs(automation_run_id, stdout, stderr, root) -> dict[str, str]`
- `should_update_attention(record) -> bool`
- `render_attention_markdown(record) -> str`

要求：
- stdout 缺字段时抛出结构化 contract error
- `run_id` 允许为 `None`
- `automation_run_id` 必须始终存在
- `latest_attention.*` 只在 `blocked / failed / automation_contract_error` 时更新
- 成功写 `latest_run.json` 不应覆盖现有 attention 文件
- contract error 下也必须写 `run_history.jsonl`、`latest_run.json`、stdout/stderr 日志
- `latest_attention.json` 至少锁住 `attention_type`、`automation_run_id`、`suggested_next_action`
- `latest_attention.md` 至少锁住 `automation_run_id`、`workflow_status`、关键路径段落

- [ ] **Step 4: 在 `src/workflow/__init__.py` 暴露必要入口**

仅导出后续脚本/测试会直接用到的 helper，例如：

```python
from src.workflow.automation import (
    build_automation_record,
    generate_automation_run_id,
    parse_workflow_stdout_contract,
    should_update_attention,
    write_automation_outputs,
)
```

- [ ] **Step 5: 跑 Task 1 回归**

Run: `pytest tests/test_workflow_automation.py -q`

Expected:
- PASS

- [ ] **Step 6: 提交 helper 能力**

```bash
git add src/workflow/automation.py src/workflow/__init__.py tests/test_workflow_automation.py
git commit -m "feat: add workflow automation helpers"
```

### Task 2: 新增 wrapper 脚本并锁定退出码/contract error 语义

**Files:**
- Create: `scripts/run_workflow_automation.py`
- Create: `tests/test_workflow_automation_runner.py`
- Verify: `scripts/run_end_to_end_workflow.py`
- Verify: `src/core/config.py`

- [ ] **Step 1: 先写 wrapper 函数级测试，锁定子进程、workdir 和 contract error 语义**

在 `tests/test_workflow_automation_runner.py` 中新增：

```python
import json
from pathlib import Path
from subprocess import CompletedProcess


def test_workflow_automation_runner_writes_latest_run_for_success(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    manifest_path = tmp_path / "reports" / "workflow" / "runs" / "20260325T010203Z-abcd1234" / "workflow_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": "20260325T010203Z-abcd1234",
                "status": "preflight_only",
                "exit_code": 0,
                "health_check_result": {"report_path": None},
                "post_publish_health_check_result": {"report_path": None},
                "research_governance_result": {"pipeline_summary": None},
            }
        ),
        encoding="utf-8",
    )

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

    exit_code = cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"])

    assert exit_code == 0
    assert (tmp_path / "reports" / "workflow" / "automation" / "latest_run.json").exists()


def test_workflow_automation_runner_returns_one_and_writes_attention_on_contract_error(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout="workflow_status=succeeded\npublish_executed=false\n",
            stderr="boom",
        ),
    )

    exit_code = cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"])

    assert exit_code == 1
    assert (tmp_path / "reports" / "workflow" / "automation" / "latest_attention.json").exists()
    assert (tmp_path / "reports" / "workflow" / "automation" / "latest_run.json").exists()
    history_path = tmp_path / "reports" / "workflow" / "automation" / "run_history.jsonl"
    assert history_path.exists()
    assert "automation_run_id" in history_path.read_text(encoding="utf-8")
    assert list((tmp_path / "reports" / "workflow" / "automation" / "runs").glob("*/runner_stdout.log"))
    assert list((tmp_path / "reports" / "workflow" / "automation" / "runs").glob("*/runner_stderr.log"))


def test_workflow_automation_runner_inherits_blocked_exit_code(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    manifest_path = tmp_path / "reports" / "workflow" / "runs" / "20260325T010203Z-abcd1234" / "workflow_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": "20260325T010203Z-abcd1234",
                "status": "blocked",
                "exit_code": 2,
                "research_governance_result": {"pipeline_summary": "reports/governance/pipeline/2026-03-24.json"},
                "health_check_result": {"report_path": None},
                "post_publish_health_check_result": {"report_path": None},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=2,
            stdout=(
                "run_id=20260325T010203Z-abcd1234\n"
                "workflow_manifest=reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json\n"
                "workflow_status=blocked\n"
                "publish_executed=false\n"
            ),
            stderr="",
        ),
    )

    exit_code = cli.main(["--workdir", str(tmp_path), "--", "--fail-on-blocked"])

    assert exit_code == 2
    assert (tmp_path / "reports" / "workflow" / "automation" / "latest_attention.json").exists()


def test_workflow_automation_runner_keeps_blocked_exit_zero_when_runner_returns_zero(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    manifest_path = tmp_path / "reports" / "workflow" / "runs" / "20260325T010203Z-abcd1234" / "workflow_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": "20260325T010203Z-abcd1234",
                "status": "blocked",
                "exit_code": 0,
                "research_governance_result": {"pipeline_summary": "reports/governance/pipeline/2026-03-24.json"},
                "health_check_result": {"report_path": None},
                "post_publish_health_check_result": {"report_path": None},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=(
                "run_id=20260325T010203Z-abcd1234\n"
                "workflow_manifest=reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json\n"
                "workflow_status=blocked\n"
                "publish_executed=false\n"
            ),
            stderr="",
        ),
    )

    assert cli.main(["--workdir", str(tmp_path), "--"]) == 0
    assert (tmp_path / "reports" / "workflow" / "automation" / "latest_attention.json").exists()


def test_workflow_automation_runner_inherits_failed_exit_code(tmp_path, monkeypatch):
    import scripts.run_workflow_automation as cli

    manifest_path = tmp_path / "reports" / "workflow" / "runs" / "20260325T010203Z-abcd1234" / "workflow_manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "run_id": "20260325T010203Z-abcd1234",
                "status": "failed",
                "exit_code": 1,
                "failed_step": "preflight",
                "health_check_result": {"report_path": None},
                "post_publish_health_check_result": {"report_path": None},
                "research_governance_result": {"pipeline_summary": None},
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        cli.subprocess,
        "run",
        lambda *args, **kwargs: CompletedProcess(
            args=args[0],
            returncode=1,
            stdout=(
                "run_id=20260325T010203Z-abcd1234\n"
                "workflow_manifest=reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json\n"
                "workflow_status=failed\n"
                "publish_executed=false\n"
            ),
            stderr="",
        ),
    )

    assert cli.main(["--workdir", str(tmp_path), "--", "--preflight-only"]) == 1
```

- [ ] **Step 2: 跑测试，确认 wrapper 尚未实现**

Run: `pytest tests/test_workflow_automation_runner.py -q`

Expected:
- FAIL
- 推荐失败形态：`ModuleNotFoundError: No module named 'scripts.run_workflow_automation'`

- [ ] **Step 3: 实现 wrapper 最小入口**

在 `scripts/run_workflow_automation.py` 中实现：

- `--workdir` 可选参数，默认 repo root
- `--` 后 runner 参数透传
- runner 脚本绝对路径解析
- 当 `workdir != repo root` 时准备 `config -> <repo>/config` 只读符号链接
- 子进程执行 runner，捕获 stdout/stderr
- 在解析 stdout 前先把 stdout/stderr 写到 `reports/workflow/automation/runs/<automation_run_id>/`
- 解析并校验 contract
- 读取 manifest，构造 automation record
- 写 `run_history.jsonl`、`latest_run.json`
- 必要时写 `latest_attention.json|md`

要求：
- `wrapper_exit_code` 正常继承 runner 退出码
- contract error 或自动化层写盘失败时返回 `1`
- `runner_process_exit_code` 必须原样保留到 record
- `workflow_manifest` 为相对路径时，按 `workdir` 解析

- [ ] **Step 4: 补锁 attention 不覆盖和 config workdir 语义**

在同一测试文件中补两类断言：

- 先写一条 attention，再跑成功记录，确认旧 `latest_attention.*` 不被覆盖
- `--workdir` 模式下会创建 `config` 符号链接，且链接目标指向 repo `config/`
- `failed` 路径会继承 runner `1`
- `blocked` 路径会继承 runner `0/2`

- [ ] **Step 5: 跑 Task 2 回归**

Run: `pytest tests/test_workflow_automation.py tests/test_workflow_automation_runner.py -q`

Expected:
- PASS

- [ ] **Step 6: 提交 wrapper 能力**

```bash
git add scripts/run_workflow_automation.py tests/test_workflow_automation_runner.py src/workflow/automation.py
git commit -m "feat: add local workflow automation runner"
```

### Task 3: 增加真实 wrapper smoke，锁定失败后成功不覆盖 attention

**Files:**
- Create: `tests/test_workflow_automation_cli_smoke.py`
- Verify: `tests/test_end_to_end_workflow_runner_cli_smoke.py`
- Verify: `src/workflow/preflight.py`
- Verify: `src/governance_pipeline.py`

- [ ] **Step 1: 先写 wrapper CLI smoke**

在 `tests/test_workflow_automation_cli_smoke.py` 中新增一个真实序列用例：

```python
import json
from pathlib import Path
import subprocess
import sys


def test_workflow_automation_cli_smoke_failed_then_success_keeps_attention(tmp_path):
    wrapper_path = Path(__file__).resolve().parents[1] / "scripts" / "run_workflow_automation.py"

    failed = subprocess.run(
        [
            sys.executable,
            str(wrapper_path),
            "--workdir",
            str(tmp_path),
            "--",
            "--start-date",
            "2026-03-24",
            "--end-date",
            "2025-12-01",
            "--preflight-only",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert failed.returncode == 1

    attention_json_path = tmp_path / "reports" / "workflow" / "automation" / "latest_attention.json"
    failed_attention = json.loads(attention_json_path.read_text(encoding="utf-8"))
    assert failed_attention["workflow_status"] == "failed"

    success = subprocess.run(
        [
            sys.executable,
            str(wrapper_path),
            "--workdir",
            str(tmp_path),
            "--",
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--preflight-only",
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    assert success.returncode == 0

    latest_run = json.loads(
        (tmp_path / "reports" / "workflow" / "automation" / "latest_run.json").read_text(encoding="utf-8")
    )
    assert latest_run["workflow_status"] == "preflight_only"
    assert (tmp_path / latest_run["workflow_manifest"]).exists()
    history_lines = (
        (tmp_path / "reports" / "workflow" / "automation" / "run_history.jsonl")
        .read_text(encoding="utf-8")
        .strip()
        .splitlines()
    )
    assert len(history_lines) == 2

    retained_attention = json.loads(attention_json_path.read_text(encoding="utf-8"))
    assert retained_attention["automation_run_id"] == failed_attention["automation_run_id"]
    assert (tmp_path / "reports" / "workflow" / "automation" / "latest_attention.md").exists()
    assert (tmp_path / retained_attention["runner_stdout_path"]).exists()
    assert (tmp_path / retained_attention["runner_stderr_path"]).exists()
    attention_md = (tmp_path / "reports" / "workflow" / "automation" / "latest_attention.md").read_text(encoding="utf-8")
    assert failed_attention["automation_run_id"] in attention_md
```

- [ ] **Step 2: 跑 smoke，确认当前闭环尚未完整打通**

Run: `pytest tests/test_workflow_automation_cli_smoke.py -q`

Expected:
- FAIL

- [ ] **Step 3: 补齐 smoke 所需最小行为**

若 RED 暴露问题，在 wrapper / helper 中只补最小实现：

- `config -> repo/config` workdir 兜底真实可用
- runner 真实子进程调用使用绝对路径
- success / failed 序列后 attention 不被成功覆盖
- `run_history.jsonl` 每次都追加记录

- [ ] **Step 4: 跑 Task 3 回归**

Run: `pytest tests/test_workflow_automation_runner.py tests/test_workflow_automation_cli_smoke.py -q`

Expected:
- PASS

- [ ] **Step 5: 提交 smoke 闭环**

```bash
git add tests/test_workflow_automation_cli_smoke.py scripts/run_workflow_automation.py src/workflow/automation.py
git commit -m "test: add workflow automation smoke coverage"
```

### Task 4: 更新 README / tasks 并做最终聚焦回归

**Files:**
- Modify: `README.md`
- Modify: `tasks/todo.md`
- Verify: `docs/superpowers/specs/2026-03-25-local-workflow-automation-design.md`
- Verify: `docs/superpowers/plans/2026-03-25-local-workflow-automation-implementation.md`

- [ ] **Step 1: 更新 README，补本地自动化入口说明**

至少补充：

- `scripts/run_workflow_automation.py` 用法
- `--workdir` 语义
- `reports/workflow/automation/` 目录说明
- `latest_run.json` 与 `latest_attention.*` 的区别
- attention 只在 `blocked / failed / contract error` 时更新

- [ ] **Step 2: 更新 `tasks/todo.md`，记录 spec / plan / task 提交 / 审查 / 验证**

要求：
- 记录本子项目 spec / plan 路径
- 记录 Task 1/2/3 提交、fresh 验证、双审查状态
- 记录最终聚焦回归结果
- 将下一步行动切到后续 cron / GitHub Actions / artifact retention 方向

- [ ] **Step 3: 跑最终聚焦回归**

必跑：

Run: `pytest tests/test_workflow_automation.py tests/test_workflow_automation_runner.py tests/test_workflow_automation_cli_smoke.py tests/test_end_to_end_workflow_runner.py tests/test_end_to_end_workflow_runner_cli_smoke.py tests/test_workflow_preflight.py tests/test_workflow_manifest.py -q`

Expected:
- PASS

扩展回归（建议在 Task 4 收口时再跑）：

Run: `pytest tests/test_workflow_preflight.py tests/test_workflow_manifest.py tests/test_end_to_end_workflow_runner.py tests/test_end_to_end_workflow_runner_cli_smoke.py tests/test_workflow_automation.py tests/test_workflow_automation_runner.py tests/test_workflow_automation_cli_smoke.py tests/test_research_governance_pipeline.py tests/test_research_governance_pipeline_cli_smoke.py tests/test_pipeline_e2e.py -q`

Expected:
- PASS

- [ ] **Step 4: 提交文档与任务跟踪更新**

```bash
git add README.md tasks/todo.md
git commit -m "docs: add local workflow automation plan"
```

## 实施备注

- `workflow_manifest` 是唯一业务事实源；自动化索引只做派生视图，字段缺失时用 `null`
- `automation_run_id` 是自动化层主键，`run_id` 可以为空
- wrapper 必须先写 stdout/stderr 日志，再做 contract 解析，确保 contract error 仍可排查
- `latest_attention.*` 只在需人工关注时刷新；成功运行不能清空旧 attention
- smoke 优先使用真实 `--preflight-only` 路径，避免把自动化 smoke 变成业务回归全集
