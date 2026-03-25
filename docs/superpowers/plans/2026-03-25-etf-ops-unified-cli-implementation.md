# ETF Ops 单一总入口 CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为项目增加单一总入口 `python scripts/etf_ops.py`，统一收敛高频主链命令，并在不破坏既有 workflow/automation 合同的前提下保留旧脚本兼容入口。

**Architecture:** 新增 `src/cli` 作为 CLI 适配层，分为命令分发、共享 command adapter 和 `status latest` 只读状态汇总三部分。总入口与旧脚本都调用同一组 adapter；workflow / automation 继续复用现有稳定 runner 行为与 stdout 合同，`status latest` 只读取现有 artifact 并做最小归一化，不新增数据库或新的 summary artifact。

**Tech Stack:** Python 3、argparse、pathlib、json、pytest、现有 workflow runner / automation wrapper / daily pipeline / research-governance CLI

---

## 文件边界

### Create

- `src/cli/__init__.py`
- `src/cli/commands.py`
- `src/cli/etf_ops.py`
- `src/cli/status.py`
- `scripts/etf_ops.py`
- `tests/test_etf_ops_cli.py`
- `tests/test_etf_ops_status.py`
- `tests/test_etf_ops_legacy_compat.py`

### Modify

- `scripts/run_end_to_end_workflow.py`
- `scripts/run_workflow_automation.py`
- `scripts/daily_run.py`
- `scripts/run_research_governance_pipeline.py`
- `README.md`
- `tasks/todo.md`

### Verify Only

- `src/workflow/automation.py`
- `src/workflow/manifest.py`
- `src/workflow/preflight.py`
- `tests/test_end_to_end_workflow_runner.py`
- `tests/test_end_to_end_workflow_runner_cli_smoke.py`
- `tests/test_workflow_automation.py`
- `tests/test_workflow_automation_runner.py`
- `tests/test_workflow_automation_cli_smoke.py`
- `tests/test_research_governance_pipeline.py`
- `tests/test_research_governance_pipeline_cli_smoke.py`

## 实施任务

### Task 1: 建立总入口 CLI 骨架、共享 adapter 和命令树

**Files:**
- Create: `src/cli/__init__.py`
- Create: `src/cli/commands.py`
- Create: `src/cli/etf_ops.py`
- Create: `scripts/etf_ops.py`
- Create: `tests/test_etf_ops_cli.py`
- Modify: `scripts/daily_run.py`

- [ ] **Step 1: 先写 failing test，锁定命令树、dispatch 和 `workflow preflight` alias**

在 `tests/test_etf_ops_cli.py` 中先写最小覆盖：

```python
import subprocess
import sys
from pathlib import Path


def test_etf_ops_help_lists_top_level_commands():
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "etf_ops.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "workflow" in proc.stdout
    assert "automation" in proc.stdout
    assert "daily" in proc.stdout
    assert "research-governance" in proc.stdout
    assert "status" in proc.stdout


def test_etf_ops_help_works_outside_repo_cwd(tmp_path):
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "etf_ops.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=str(tmp_path),
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "workflow" in proc.stdout


def test_etf_ops_subcommand_help_smoke():
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "etf_ops.py"

    commands = [
        ["workflow", "run", "--help"],
        ["workflow", "preflight", "--help"],
        ["automation", "run", "--help"],
        ["daily", "run", "--help"],
        ["research-governance", "run", "--help"],
    ]

    for argv in commands:
        proc = subprocess.run(
            [sys.executable, str(script), *argv],
            cwd=str(repo_root),
            text=True,
            capture_output=True,
            check=False,
        )
        assert proc.returncode == 0


def test_workflow_preflight_appends_preflight_only(monkeypatch):
    import src.cli.etf_ops as cli

    captured = {}

    def _fake_workflow(argv):
        captured["argv"] = list(argv)
        return 0

    monkeypatch.setattr(cli, "run_workflow_command", _fake_workflow)
    assert cli.main(["workflow", "preflight", "--start-date", "2025-12-01", "--end-date", "2026-03-24"]) == 0
    assert "--preflight-only" in captured["argv"]


def test_automation_run_keeps_double_dash_passthrough(monkeypatch):
    import src.cli.etf_ops as cli

    captured = {}

    def _fake_automation(argv):
        captured["argv"] = list(argv)
        return 0

    monkeypatch.setattr(cli, "run_automation_command", _fake_automation)
    assert cli.main(["automation", "run", "--workdir", "/tmp/job", "--", "--preflight-only"]) == 0
    assert captured["argv"] == ["--workdir", "/tmp/job", "--", "--preflight-only"]


def test_workflow_run_does_not_add_wrapper_stdout(monkeypatch, capsys):
    import src.cli.etf_ops as cli

    def _fake_workflow(argv):
        print("run_id=20260325T010203Z-abcd1234")
        print("workflow_manifest=reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json")
        print("workflow_status=preflight_only")
        print("publish_executed=false")
        return 0

    monkeypatch.setattr(cli, "run_workflow_command", _fake_workflow)
    assert cli.main(["workflow", "run", "--preflight-only"]) == 0
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert lines == [
        "run_id=20260325T010203Z-abcd1234",
        "workflow_manifest=reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json",
        "workflow_status=preflight_only",
        "publish_executed=false",
    ]
```

- [ ] **Step 2: 跑 Task 1 测试，确认 CLI 还不存在**

Run: `pytest tests/test_etf_ops_cli.py -q`

Expected:
- FAIL
- 推荐失败形态：`ModuleNotFoundError: No module named 'src.cli.etf_ops'` 或 `can't open file 'scripts/etf_ops.py'`

- [ ] **Step 3: 实现共享 command adapter 与总入口 parser**

在 `src/cli/commands.py` 中先实现 4 个最小 adapter，供总入口复用：

```python
def run_workflow_command(argv: list[str] | None = None) -> int:
    from scripts.run_end_to_end_workflow import main as workflow_main

    return int(workflow_main(argv))


def run_automation_command(argv: list[str] | None = None) -> int:
    from scripts.run_workflow_automation import main as automation_main

    return int(automation_main(argv))
```

同文件中补齐：

- `run_daily_command(argv)`
- `run_research_governance_command(argv)`

在 `src/cli/etf_ops.py` 中实现：

- `build_parser()`
- `main(argv: list[str] | None = None) -> int`
- `workflow run`
- `workflow preflight`
- `automation run`
- `daily run`
- `research-governance run`

要求：

- `workflow preflight` 复用 `workflow run` 参数面
- 通过 helper 保证最终参数中存在 `--preflight-only`
- `automation run` 使用 `argparse.REMAINDER` 保留 `--` 后原样透传
- 暂时先不接 `status latest`

- [ ] **Step 4: 增加脚本壳并让 `daily_run.py` 可复用**

在 `scripts/etf_ops.py` 中只保留入口壳：

```python
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.cli.etf_ops import main


if __name__ == "__main__":
    raise SystemExit(main())
```

同时把 `scripts/daily_run.py` 调整为：

- `main(argv: list[str] | None = None) -> int`
- `_parse_args(argv)` 接收显式 argv
- 成功时返回 `0`

这样总入口与后续 legacy wrapper 都能一致复用。

- [ ] **Step 5: 回跑 Task 1 测试**

Run: `pytest tests/test_etf_ops_cli.py -q`

Expected:
- PASS
- `workflow preflight` 已注入 `--preflight-only`
- `automation run` 透传保持不变

- [ ] **Step 6: 提交 Task 1**

```bash
git add src/cli/__init__.py src/cli/commands.py src/cli/etf_ops.py scripts/etf_ops.py scripts/daily_run.py tests/test_etf_ops_cli.py
git commit -m "feat: add unified etf ops cli skeleton"
```

### Task 2: 落地 `status latest` 读取、归一化和文本/JSON 输出

**Files:**
- Create: `src/cli/status.py`
- Create: `tests/test_etf_ops_status.py`
- Modify: `src/cli/etf_ops.py`

- [ ] **Step 1: 先写 failing test，锁定 `status latest` 的根目录语义和字段映射**

在 `tests/test_etf_ops_status.py` 中先写最小覆盖：

```python
import json
from pathlib import Path


def test_status_latest_prefers_automation_latest_run(tmp_path, capsys):
    import src.cli.etf_ops as cli

    root = tmp_path / "job"
    automation_dir = root / "reports" / "workflow" / "automation"
    automation_dir.mkdir(parents=True, exist_ok=True)
    (automation_dir / "latest_run.json").write_text(
        json.dumps(
            {
                "automation_run_id": "20260325T010203Z-a1b2c3d4",
                "automation_started_at": "2026-03-25T01:02:03Z",
                "automation_finished_at": "2026-03-25T01:02:05Z",
                "run_id": "20260325T010203Z-abcd1234",
                "workflow_manifest": "reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json",
                "workflow_status": "blocked",
                "publish_executed": False,
                "failed_step": None,
                "blocked_reasons": ["REGIME_MISMATCH"],
                "suggested_next_action": "inspect blocked_reasons and governance review status",
            }
        ),
        encoding="utf-8",
    )

    assert cli.main(["status", "latest", "--workdir", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "automation_latest"
    assert payload["status"] == "blocked"
    assert payload["blocked_reasons"] == ["REGIME_MISMATCH"]


def test_status_latest_falls_back_to_workflow_summary(tmp_path, capsys):
    import src.cli.etf_ops as cli

    root = tmp_path / "repo"
    summary_path = root / "reports" / "workflow" / "end_to_end_workflow_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "run_id": "20260325T010203Z-abcd1234",
                "started_at": "2026-03-25T01:02:03Z",
                "finished_at": "2026-03-25T01:02:05Z",
                "status": "failed",
                "failed_step": "preflight",
                "workflow_manifest_path": "reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json",
                "research_governance_result": {"blocked_reasons": []},
                "publish_result": {"executed": False},
            }
        ),
        encoding="utf-8",
    )

    assert cli.main(["status", "latest", "--workdir", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["source"] == "workflow_summary_fallback"
    assert payload["suggested_next_action"] == "inspect failed_step=preflight and workflow manifest"


def test_status_latest_returns_one_when_no_artifact_exists(tmp_path, capsys):
    import src.cli.etf_ops as cli

    assert cli.main(["status", "latest", "--workdir", str(tmp_path), "--json"]) == 1


def test_status_latest_text_output_contains_key_fields(tmp_path, capsys):
    import src.cli.etf_ops as cli

    root = tmp_path / "repo"
    summary_path = root / "reports" / "workflow" / "end_to_end_workflow_summary.json"
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(
        json.dumps(
            {
                "run_id": "20260325T010203Z-abcd1234",
                "started_at": "2026-03-25T01:02:03Z",
                "finished_at": "2026-03-25T01:02:05Z",
                "status": "succeeded",
                "workflow_manifest_path": "reports/workflow/runs/20260325T010203Z-abcd1234/workflow_manifest.json",
                "research_governance_result": {"blocked_reasons": []},
                "publish_result": {"executed": False},
            }
        ),
        encoding="utf-8",
    )

    assert cli.main(["status", "latest", "--workdir", str(root)]) == 0
    text = capsys.readouterr().out
    assert "run_id" in text
    assert "succeeded" in text


def test_status_latest_returns_one_for_invalid_json(tmp_path, capsys):
    import src.cli.etf_ops as cli

    root = tmp_path / "repo"
    latest_path = root / "reports" / "workflow" / "automation" / "latest_run.json"
    latest_path.parent.mkdir(parents=True, exist_ok=True)
    latest_path.write_text("{bad json", encoding="utf-8")

    assert cli.main(["status", "latest", "--workdir", str(root), "--json"]) == 1
```

- [ ] **Step 2: 跑 Task 2 测试，确认 `status latest` 仍未实现**

Run: `pytest tests/test_etf_ops_status.py -q`

Expected:
- FAIL
- 推荐失败形态：`invalid choice: 'status'` 或 `ImportError: cannot import name ...`

- [ ] **Step 3: 在 `src/cli/status.py` 实现只读 status helper**

实现最小接口：

```python
def resolve_status_root(workdir: str | None) -> Path: ...
def load_latest_status(root: Path) -> dict[str, Any]: ...
def normalize_status_payload(payload: dict[str, Any], *, source: str, root: Path) -> dict[str, Any]: ...
def render_status_text(payload: dict[str, Any]) -> str: ...
```

实现要求：

- 若传 `--workdir`，根目录使用该路径；否则使用当前 cwd
- 优先读取 `<root>/reports/workflow/automation/latest_run.json`
- automation 不存在时回退 `<root>/reports/workflow/end_to_end_workflow_summary.json`
- artifact JSON 损坏、字段缺失或来源都不存在时统一返回退出码 `1`
- workflow summary 的 `suggested_next_action` 采用 spec 中的 fallback 规则
- 相对 `manifest_path` 只做“相对根目录解析后的展示值”，不创建新 artifact

- [ ] **Step 4: 把 `status latest` 接到总入口**

在 `src/cli/etf_ops.py` 中补：

- `status latest`
- `--workdir`
- `--json`

输出要求：

- 文本模式：打印人工可读摘要
- `--json`：只打印 JSON，不插入 banner 或辅助说明
- `python scripts/etf_ops.py status latest --help` 返回 `0`

- [ ] **Step 5: 回跑 Task 2 测试**

Run: `pytest tests/test_etf_ops_status.py -q`

Expected:
- PASS
- automation 优先级、fallback 和错误退出码都被锁定

- [ ] **Step 6: 提交 Task 2**

```bash
git add src/cli/status.py src/cli/etf_ops.py tests/test_etf_ops_status.py
git commit -m "feat: add latest status command"
```

### Task 3: 把旧脚本收敛为薄兼容层，并锁定兼容帮助信息

**Files:**
- Modify: `src/cli/commands.py`
- Modify: `scripts/run_end_to_end_workflow.py`
- Modify: `scripts/run_workflow_automation.py`
- Modify: `scripts/daily_run.py`
- Modify: `scripts/run_research_governance_pipeline.py`
- Create: `tests/test_etf_ops_legacy_compat.py`

- [ ] **Step 1: 先写 failing test，锁定旧脚本仍可用且转到共享 adapter**

在 `tests/test_etf_ops_legacy_compat.py` 中先写最小覆盖：

```python
import subprocess
import sys
from pathlib import Path


def test_daily_legacy_main_forwards_to_shared_adapter(monkeypatch):
    import scripts.daily_run as legacy
    import src.cli.commands as commands

    captured = {}

    def _fake(argv=None):
        captured["argv"] = list(argv or [])
        return 0

    monkeypatch.setattr(commands, "run_daily_command", _fake)
    assert legacy.main(["--date", "2026-03-25"]) == 0
    assert captured["argv"] == ["--date", "2026-03-25"]


def test_legacy_workflow_help_mentions_unified_entrypoint():
    repo_root = Path(__file__).resolve().parents[1]
    script = repo_root / "scripts" / "run_end_to_end_workflow.py"
    proc = subprocess.run(
        [sys.executable, str(script), "--help"],
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "兼容入口" in proc.stdout
    assert "scripts/etf_ops.py" in proc.stdout
```

- [ ] **Step 2: 跑 Task 3 测试，确认旧脚本尚未转发**

Run: `pytest tests/test_etf_ops_legacy_compat.py -q`

Expected:
- FAIL
- 推荐失败形态：帮助文本不含“兼容入口”，或 `legacy.main()` 未调用共享 adapter

- [ ] **Step 3: 为 4 个旧脚本引入显式兼容入口函数和薄 `main()`**

在 4 个旧脚本中统一整理成两层：

```python
def run_daily_entrypoint(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    ...
    return 0


def main(argv: list[str] | None = None) -> int:
    from src.cli.commands import run_daily_command

    return int(run_daily_command(argv))
```

同理为 workflow / automation / research-governance 增加：

- `run_workflow_entrypoint`
- `run_workflow_automation_entrypoint`
- `run_research_governance_entrypoint`

要求：

- 旧业务逻辑留在 `run_*_entrypoint`
- `main()` 只保留一层共享 adapter 转发
- `argparse` description 增加“兼容入口，推荐改用 `python scripts/etf_ops.py ...`”

- [ ] **Step 4: 调整 `src/cli/commands.py` 避免递归，统一调用 `run_*_entrypoint`**

把 Task 1 中的 lazy import 更新为：

```python
def run_workflow_command(argv=None) -> int:
    from scripts.run_end_to_end_workflow import run_workflow_entrypoint

    return int(run_workflow_entrypoint(argv))
```

同理更新 automation / daily / research-governance。

- [ ] **Step 5: 跑 Task 3 测试与兼容回归**

Run:

```bash
pytest tests/test_etf_ops_legacy_compat.py tests/test_etf_ops_cli.py -q
pytest tests/test_end_to_end_workflow_runner.py tests/test_workflow_automation_runner.py tests/test_research_governance_pipeline.py -q
```

Expected:
- PASS
- 旧脚本仍可调用
- workflow / automation / rg 既有回归不漂移

- [ ] **Step 6: 提交 Task 3**

```bash
git add src/cli/commands.py scripts/run_end_to_end_workflow.py scripts/run_workflow_automation.py scripts/daily_run.py scripts/run_research_governance_pipeline.py tests/test_etf_ops_legacy_compat.py
git commit -m "refactor: route legacy scripts through unified cli adapters"
```

### Task 4: 更新 README / tasks 跟踪，并完成最终回归

**Files:**
- Modify: `README.md`
- Modify: `tasks/todo.md`
- Verify: `tests/test_etf_ops_cli.py`
- Verify: `tests/test_etf_ops_status.py`
- Verify: `tests/test_etf_ops_legacy_compat.py`
- Verify: `tests/test_end_to_end_workflow_runner.py`
- Verify: `tests/test_end_to_end_workflow_runner_cli_smoke.py`
- Verify: `tests/test_workflow_automation.py`
- Verify: `tests/test_workflow_automation_runner.py`
- Verify: `tests/test_workflow_automation_cli_smoke.py`
- Verify: `tests/test_research_governance_pipeline.py`
- Verify: `tests/test_research_governance_pipeline_cli_smoke.py`

- [ ] **Step 1: 更新 README，默认示例切到统一入口**

README 至少要更新：

- 快速开始中的高频命令示例改为 `python scripts/etf_ops.py ...`
- 增加 `status latest` / `status latest --json`
- 保留旧脚本兼容说明，不删除原有低频脚本文档
- 明确 `automation run --workdir` 与 `status latest --workdir` 的对应关系

- [ ] **Step 2: 更新 `tasks/todo.md`，建立本子项目跟踪块**

新增：

- 执行清单（Task 1-4）
- 规划产物（spec / plan 路径）
- 审查状态（spec review / plan review）
- 后续填写 Task 提交、fresh 验证、双审查状态

- [ ] **Step 3: 跑聚焦回归**

Run:

```bash
pytest \
  tests/test_etf_ops_cli.py \
  tests/test_etf_ops_status.py \
  tests/test_etf_ops_legacy_compat.py \
  tests/test_end_to_end_workflow_runner.py \
  tests/test_end_to_end_workflow_runner_cli_smoke.py \
  tests/test_workflow_automation.py \
  tests/test_workflow_automation_runner.py \
  tests/test_workflow_automation_cli_smoke.py \
  tests/test_research_governance_pipeline.py \
  tests/test_research_governance_pipeline_cli_smoke.py \
  -q
```

Expected:
- PASS
- 新 CLI 与旧 runner/automation 合同共同稳定

- [ ] **Step 4: 跑全量回归，确认没有隐藏漂移**

Run: `pytest -q`

Expected:
- PASS

- [ ] **Step 5: 提交 Task 4**

```bash
git add README.md tasks/todo.md
git commit -m "docs: document unified etf ops cli"
```

## 执行注意事项

- `workflow preflight` 必须走同一 workflow runner，只允许参数注入，不允许复制一套预检实现。
- `automation run`、`workflow run`、`workflow preflight` 不得在 stdout 合同前后插入新的说明文本。
- `status latest` 的错误退出码统一为 `1`；不存在 artifact、JSON 损坏、关键字段缺失都按失败处理。
- 旧脚本的 `--help` 仍应可用，但必须明确它们是兼容入口。
- 每个 Task 完成后都要做 fresh verification、spec compliance review、code quality review，再继续下一个 Task。
