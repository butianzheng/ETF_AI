# End-to-End Workflow Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一个安全模式的一键端到端编排脚本，把可选 daily run、research-governance、health check、可选 publish 与 post-publish health 串成统一入口，并输出结构化 workflow summary。

**Architecture:** 新增 `scripts/run_end_to_end_workflow.py` 作为纯编排层，内部直接调用现有 service / 领域入口，而不是 shell 再调 shell。脚本负责参数解析、阶段调度、summary 写盘和退出码映射；独立测试文件 `tests/test_end_to_end_workflow_runner.py` 只锁编排行为、参数转发、blocked/fatal/publish 语义，不重复测子系统内部业务逻辑。

**Tech Stack:** Python 3、pytest、monkeypatch、argparse、JSON、现有 governance/daily/research services

---

## 文件边界

### Create

- `scripts/run_end_to_end_workflow.py`
- `tests/test_end_to_end_workflow_runner.py`

### Modify

- `README.md`
- `tasks/todo.md`

### Verify Only

- `scripts/daily_run.py`
- `scripts/run_research_governance_pipeline.py`
- `scripts/publish_governance_decision.py`
- `scripts/check_governance_health.py`
- `src/main.py`
- `src/governance_pipeline.py`
- `src/governance/health.py`
- `src/governance/publisher.py`

## 实施任务

### Task 1: 建立编排脚本骨架，锁定参数校验与默认 no-publish 行为

**Files:**
- Create: `scripts/run_end_to_end_workflow.py`
- Create: `tests/test_end_to_end_workflow_runner.py`
- Verify: `scripts/run_research_governance_pipeline.py`
- Verify: `scripts/check_governance_health.py`

- [ ] **Step 1: 先写失败测试，锁定 CLI 参数校验与默认 no-publish 行为**

在 `tests/test_end_to_end_workflow_runner.py` 中新增：

```python
import json
from pathlib import Path

import pytest


def test_workflow_runner_requires_approved_by_when_publish_enabled(tmp_path, monkeypatch):
    import scripts.run_end_to_end_workflow as cli

    monkeypatch.chdir(tmp_path)

    with pytest.raises(SystemExit):
        cli.main(["--start-date", "2025-12-01", "--end-date", "2026-03-24", "--publish"])


def test_workflow_runner_happy_path_defaults_to_no_publish(tmp_path, monkeypatch, capsys):
    import scripts.run_end_to_end_workflow as cli

    calls: list[tuple[str, object]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli,
        "run_research_governance_pipeline",
        lambda **kwargs: calls.append(("research_governance", kwargs)) or {
            "research_result": {"report_paths": {"json": "reports/research/2026-03-24.json"}},
            "summary_result": {"output_paths": {"json": "reports/research/summary/research_summary.json"}},
            "cycle_result": type(
                "CycleResult",
                (),
                {
                    "decision": type(
                        "Decision",
                        (),
                        {"id": 12, "review_status": "ready", "blocked_reasons": []},
                    )()
                },
            )(),
            "pipeline_summary_path": "reports/governance/pipeline/2026-03-24.json",
            "exit_code": 0,
        },
    )
    monkeypatch.setattr(
        cli,
        "check_governance_health",
        lambda **kwargs: calls.append(("health", kwargs))
        or type("HealthResult", (), {"incidents": [], "rollback_recommendation": None})(),
    )
    monkeypatch.setattr(
        cli,
        "_write_health_report",
        lambda result: "reports/governance/health/2026-03-24.json",
    )

    exit_code = cli.main(["--start-date", "2025-12-01", "--end-date", "2026-03-24"])

    stdout = capsys.readouterr().out
    summary_path = tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json"
    assert exit_code == 0
    assert [name for name, _ in calls] == ["research_governance", "health"]
    assert "publish_executed=false" in stdout
    assert summary_path.exists()
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["publish_result"]["executed"] is False
    assert payload["exit_code"] == 0


def test_workflow_runner_forwards_create_rollback_draft_only_to_health_check(tmp_path, monkeypatch):
    import scripts.run_end_to_end_workflow as cli

    calls: list[tuple[str, object]] = []

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        cli,
        "run_research_governance_pipeline",
        lambda **kwargs: calls.append(("research_governance", kwargs)) or {
            "research_result": {"report_paths": {"json": "reports/research/2026-03-24.json"}},
            "summary_result": {"output_paths": {"json": "reports/research/summary/research_summary.json"}},
            "cycle_result": type(
                "CycleResult",
                (),
                {
                    "decision": type(
                        "Decision",
                        (),
                        {"id": 12, "review_status": "ready", "blocked_reasons": []},
                    )()
                },
            )(),
            "pipeline_summary_path": "reports/governance/pipeline/2026-03-24.json",
            "exit_code": 0,
        },
    )
    monkeypatch.setattr(
        cli,
        "check_governance_health",
        lambda **kwargs: calls.append(("health", kwargs))
        or type("HealthResult", (), {"incidents": [], "rollback_recommendation": None})(),
    )
    monkeypatch.setattr(cli, "_write_health_report", lambda result: "reports/governance/health/2026-03-24.json")

    exit_code = cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--create-rollback-draft",
        ]
    )

    assert exit_code == 0
    assert calls[0][0] == "research_governance"
    assert "create_rollback_draft" not in calls[0][1]
    assert calls[1][0] == "health"
    assert calls[1][1]["create_rollback_draft"] is True
```

- [ ] **Step 2: 跑测试，确认新脚本尚未实现**

Run: `pytest tests/test_end_to_end_workflow_runner.py -q -k "requires_approved_by or defaults_to_no_publish or create_rollback_draft"`

Expected:
- FAIL
- 推荐失败形态：`ModuleNotFoundError: No module named 'scripts.run_end_to_end_workflow'`

- [ ] **Step 3: 新增最小编排脚本，实现参数解析、summary 写盘与默认 no-publish happy path**

在 `scripts/run_end_to_end_workflow.py` 中实现最小骨架：

```python
def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ...
    if args.publish and not args.approved_by:
        parser.error("--publish requires --approved-by")
    return args


def _write_workflow_summary(payload: dict[str, Any]) -> Path:
    path = Path("reports/workflow/end_to_end_workflow_summary.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    result = run_research_governance_pipeline(...)
    health_result = check_governance_health(...)
    payload = {
        "daily_result": {"executed": False, "artifacts": {}},
        "research_governance_result": {...},
        "health_check_result": {...},
        "publish_result": {"executed": False, "decision": None},
        "exit_code": int(result.get("exit_code", 0)),
    }
    _write_workflow_summary(payload)
    print("publish_executed=false")
    return payload["exit_code"]
```

要求：
- 默认不跑 daily
- 默认不 publish
- 仅实现 happy-path no-publish 最小编排
- summary 固定写到 `reports/workflow/end_to_end_workflow_summary.json`
- `--create-rollback-draft` 只透传给 `check_governance_health(...)`

- [ ] **Step 4: 回跑 Task 1 测试，确认骨架闭合**

Run: `pytest tests/test_end_to_end_workflow_runner.py -q -k "requires_approved_by or defaults_to_no_publish or create_rollback_draft"`

Expected:
- PASS

- [ ] **Step 5: 提交编排脚本骨架**

```bash
git add scripts/run_end_to_end_workflow.py tests/test_end_to_end_workflow_runner.py
git commit -m "feat: add end to end workflow runner skeleton"
```

### Task 2: 补齐 blocked / fatal / summary 语义与退出码优先级

**Files:**
- Modify: `scripts/run_end_to_end_workflow.py`
- Modify: `tests/test_end_to_end_workflow_runner.py`
- Verify: `src/governance_pipeline.py`
- Verify: `src/governance/health.py`

- [ ] **Step 1: 先写失败测试，锁定 blocked、fatal 与 summary 语义**

在 `tests/test_end_to_end_workflow_runner.py` 中新增：

```python
def test_workflow_runner_returns_two_when_blocked_and_fail_on_blocked_enabled(...):
    ...
    monkeypatch.setattr(cli, "run_research_governance_pipeline", lambda **kwargs: {
        "research_result": {"report_paths": {"json": "reports/research/2026-03-24.json"}},
        "summary_result": {"output_paths": {"json": "reports/research/summary/research_summary.json"}},
        "cycle_result": SimpleNamespace(
            decision=SimpleNamespace(id=21, review_status="blocked", blocked_reasons=["SELECTED_STRATEGY_REGIME_MISMATCH"])
        ),
        "pipeline_summary_path": "reports/governance/pipeline/2026-03-24.json",
        "exit_code": 2,
    })
    ...
    assert exit_code == 2
    assert payload["publish_result"]["executed"] is False
    assert payload["research_governance_result"]["review_status"] == "blocked"


def test_workflow_runner_writes_failed_summary_and_returns_one_on_research_governance_fatal(...):
    ...
    monkeypatch.setattr(cli, "run_research_governance_pipeline", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("runner rg fatal")))
    ...
    assert exit_code == 1
    assert payload["status"] == "failed"
    assert payload["failed_step"] == "research_governance"
    assert payload["error"]["message"] == "runner rg fatal"


def test_workflow_runner_health_fatal_overrides_blocked_exit_code(...):
    ...
    monkeypatch.setattr(cli, "run_research_governance_pipeline", lambda **kwargs: blocked_result)
    monkeypatch.setattr(cli, "check_governance_health", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("health fatal")))
    ...
    assert exit_code == 1
    assert payload["failed_step"] == "health_check"
```

- [ ] **Step 2: 跑测试，确认当前脚本尚未覆盖这些语义**

Run: `pytest tests/test_end_to_end_workflow_runner.py -q -k "blocked or failed_summary or health_fatal"`

Expected:
- FAIL

- [ ] **Step 3: 最小补齐 blocked/fatal 逻辑、summary 失败形态与退出码优先级**

在 `scripts/run_end_to_end_workflow.py` 中增加：

- `_build_failure_summary(...)`
- `fatal(1) > blocked(2) > success(0)` 的退出码归一逻辑
- `blocked + --publish` 时禁止发布并写：

```python
"publish_result": {
    "executed": False,
    "decision": None,
    "publish_blocked_reason": "governance_review_status_blocked",
}
```

要求：
- `research-governance` fatal 或 `health check` fatal 都写失败 summary
- 除 summary 自身写盘失败外，fatal 场景尽量保留 summary artifact

- [ ] **Step 4: 回跑 Task 2 测试**

Run: `pytest tests/test_end_to_end_workflow_runner.py -q -k "blocked or failed_summary or health_fatal"`

Expected:
- PASS

- [ ] **Step 5: 提交 blocked/fatal 语义**

```bash
git add scripts/run_end_to_end_workflow.py tests/test_end_to_end_workflow_runner.py
git commit -m "feat: add workflow runner blocked and fatal handling"
```

### Task 3: 接入可选 daily、publish 与 post-publish health

**Files:**
- Modify: `scripts/run_end_to_end_workflow.py`
- Modify: `tests/test_end_to_end_workflow_runner.py`
- Verify: `src/main.py`
- Verify: `src/governance/publisher.py`
- Verify: `src/governance/health.py`

- [ ] **Step 1: 先写失败测试，锁定 daily / publish / post-publish health 行为**

在 `tests/test_end_to_end_workflow_runner.py` 中新增：

```python
def test_workflow_runner_can_run_daily_before_research_governance(...):
    ...
    monkeypatch.setattr(cli, "run_daily_pipeline", lambda **kwargs: calls.append(("daily", kwargs)) or daily_result)
    ...
    assert [name for name, _ in calls][:1] == ["daily"]
    assert payload["daily_result"]["executed"] is True


def test_workflow_runner_publish_path_runs_post_publish_health_check(...):
    ...
    monkeypatch.setattr(cli, "publish_decision", lambda **kwargs: calls.append(("publish", kwargs)) or published_decision)
    monkeypatch.setattr(cli, "check_governance_health", lambda **kwargs: calls.append(("health", kwargs)) or health_result)
    ...
    assert [name for name, _ in calls] == ["research_governance", "health", "publish", "health"]
    assert payload["publish_result"]["executed"] is True
    assert payload["publish_result"]["decision"]["id"] == 12


def test_workflow_runner_publish_is_skipped_when_review_status_is_blocked(...):
    ...
    assert payload["publish_result"]["executed"] is False
    assert payload["publish_result"]["publish_blocked_reason"] == "governance_review_status_blocked"
```

- [ ] **Step 2: 跑测试，确认当前脚本尚未完整覆盖 daily / publish path**

Run: `pytest tests/test_end_to_end_workflow_runner.py -q -k "run_daily or post_publish_health or publish_is_skipped"`

Expected:
- FAIL

- [ ] **Step 3: 最小实现 daily、publish 与 post-publish health 编排**

在 `scripts/run_end_to_end_workflow.py` 中：

- 接入：

```python
from src.main import run_daily_pipeline
from src.governance.health import check_governance_health
from src.governance.publisher import publish_decision
from src.storage.repositories import GovernanceRepository
```

- `--run-daily` 时调用：

```python
run_daily_pipeline(
    as_of_date=date.fromisoformat(args.daily_date) if args.daily_date else None,
    log_level=args.log_level,
    execute_trade=args.daily_execute,
    manual_approved=args.daily_manual_approve,
    available_cash=args.daily_available_cash,
)
```

- publish 路径：
  - 仅在 `args.publish and review_status == "ready"` 时执行
  - 调 `publish_decision(...)`
  - publish 后必须再跑一次 health check

要求：
- 不自动 rollback
- 不改变现有 publish 规则
- summary 中区分 pre-publish 与 post-publish health 结果

- [ ] **Step 4: 跑完整 runner 测试**

Run: `pytest tests/test_end_to_end_workflow_runner.py -q`

Expected:
- PASS

- [ ] **Step 5: 提交编排完整流程**

```bash
git add scripts/run_end_to_end_workflow.py tests/test_end_to_end_workflow_runner.py
git commit -m "feat: add end to end workflow runner"
```

### Task 4: 更新 README / tasks 并做最终聚焦回归

**Files:**
- Modify: `README.md`
- Modify: `tasks/todo.md`
- Verify: `docs/superpowers/specs/2026-03-25-end-to-end-workflow-runner-design.md`
- Verify: `docs/superpowers/plans/2026-03-25-end-to-end-workflow-runner-implementation.md`

- [ ] **Step 1: 更新 README，加入统一编排脚本用法**

至少补充：
- 默认安全模式示例
- `--run-daily` 示例
- `--publish --approved-by` 示例
- blocked/fatal/summary 输出说明

- [ ] **Step 2: 更新 `tasks/todo.md`，记录本子项目的 spec / plan / task 提交 / 审查 / 验证**

要求：
- 与实际提交和 fresh 验证保持一致

- [ ] **Step 3: 跑最终聚焦回归**

Run: `pytest tests/test_end_to_end_workflow_runner.py tests/test_research_governance_pipeline.py tests/test_research_governance_pipeline_cli_smoke.py tests/test_pipeline_e2e.py -q`

Expected:
- PASS

- [ ] **Step 4: 提交文档更新**

```bash
git add README.md tasks/todo.md
git commit -m "docs: document end to end workflow runner"
```

## 实施备注

- 测试应优先 monkeypatch `run_daily_pipeline`、`run_research_governance_pipeline`、`check_governance_health`、`publish_decision`，把重点放在编排与退出码，而不是各子系统内部逻辑
- 若 script 需要写 health report，可在脚本内部抽 `_write_health_report(...)` 辅助函数；它仍属于脚本内部编排逻辑，不需要新建 `src/` 模块
- `main(argv)` 固定返回 `int`，测试主断言应落在 summary artifact 和关键 stdout 行
- 完成后按 `finishing-a-development-branch` 提供 4 个收尾选项
