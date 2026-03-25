# Workflow Runner 运营化与联调闭环 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为现有端到端 runner 增加运行前预检、per-run manifest、自动化友好 stdout 合同和更真实的 runner smoke 覆盖，使其从“能跑”提升到“可运营、可追踪、可自动化接入”。

**Architecture:** 保持 `scripts/run_end_to_end_workflow.py` 作为唯一入口，但把 preflight 与 manifest 逻辑拆到 `src/workflow/` 下的纯辅助模块。runner 仍只做参数解析、阶段调度和 payload 汇总；legacy summary 继续保留，同时新增 per-run manifest 作为权威运行工件。

**Tech Stack:** Python 3、pytest、monkeypatch、argparse、JSON、pathlib、现有 governance/daily/research services

---

## 文件边界

### Create

- `src/workflow/__init__.py`
- `src/workflow/preflight.py`
- `src/workflow/manifest.py`
- `tests/test_workflow_preflight.py`
- `tests/test_workflow_manifest.py`
- `tests/test_end_to_end_workflow_runner_cli_smoke.py`

### Modify

- `scripts/run_end_to_end_workflow.py`
- `tests/test_end_to_end_workflow_runner.py`
- `README.md`
- `tasks/todo.md`

### Verify Only

- `src/main.py`
- `src/governance_pipeline.py`
- `src/governance/health.py`
- `src/governance/publisher.py`
- `src/storage/repositories.py`
- `tests/test_research_governance_pipeline_cli_smoke.py`

## 实施任务

### Task 1: 抽出 preflight 辅助模块并锁定失败语义

**Files:**
- Create: `src/workflow/__init__.py`
- Create: `src/workflow/preflight.py`
- Create: `tests/test_workflow_preflight.py`
- Modify: `scripts/run_end_to_end_workflow.py`
- Modify: `tests/test_end_to_end_workflow_runner.py`
- Verify: `src/storage/repositories.py`

- [ ] **Step 1: 先写 preflight 单测，锁定通过与失败结构**

在 `tests/test_workflow_preflight.py` 中新增：

```python
from pathlib import Path


def test_run_workflow_preflight_returns_passed_with_all_checks(tmp_path, monkeypatch):
    from src.workflow.preflight import run_workflow_preflight

    result = run_workflow_preflight(
        start_date="2025-12-01",
        end_date="2026-03-24",
        daily_date=None,
        candidate_config=None,
        workflow_root=tmp_path / "reports" / "workflow",
        health_root=tmp_path / "reports" / "governance" / "health",
    )

    assert result["status"] == "passed"
    assert result["failed_checks"] == []
    assert {item["name"] for item in result["checks"]} >= {
        "date_args",
        "strategy_config",
        "candidate_config",
        "governance_repository",
        "workflow_output_dir",
        "health_output_dir",
    }


def test_run_workflow_preflight_collects_failed_checks(monkeypatch, tmp_path):
    import src.workflow.preflight as preflight

    monkeypatch.setattr(
        preflight,
        "_check_strategy_config",
        lambda *_args, **_kwargs: {"name": "strategy_config", "status": "failed", "detail": "boom"},
    )

    result = preflight.run_workflow_preflight(
        start_date="2025-12-01",
        end_date="2026-03-24",
        daily_date=None,
        candidate_config=None,
        workflow_root=tmp_path / "reports" / "workflow",
        health_root=tmp_path / "reports" / "governance" / "health",
    )

    assert result["status"] == "failed"
    assert result["failed_checks"] == [{"name": "strategy_config", "detail": "boom"}]
```

- [ ] **Step 2: 跑单测，确认模块尚未实现**

Run: `pytest tests/test_workflow_preflight.py -q`

Expected:
- FAIL
- 推荐失败形态：`ModuleNotFoundError: No module named 'src.workflow.preflight'`

- [ ] **Step 3: 实现最小 preflight 模块**

在 `src/workflow/preflight.py` 中实现：

```python
def run_workflow_preflight(
    *,
    start_date: str,
    end_date: str,
    daily_date: str | None,
    candidate_config: str | None,
    workflow_root: Path,
    health_root: Path,
) -> dict[str, Any]:
    checks = [...]
    failed_checks = [
        {"name": item["name"], "detail": item["detail"]}
        for item in checks
        if item["status"] == "failed"
    ]
    return {
        "status": "failed" if failed_checks else "passed",
        "checks": checks,
        "failed_checks": failed_checks,
    }
```

要求：
- 日期解析失败要落到 `date_args`
- 候选配置解析失败要落到 `candidate_config`
- `reports/workflow/` 与 `reports/governance/health/` 可写性分别落独立 check
- 只做轻量、无副作用检查
- 输出必须全是稳定 JSON 结构

- [ ] **Step 4: 先写 runner 失败测试，锁定 preflight-only 和 preflight fatal**

在 `tests/test_end_to_end_workflow_runner.py` 中新增：

```python
def test_workflow_runner_preflight_only_writes_summary_and_returns_zero(...):
    ...
    monkeypatch.setattr(cli, "run_workflow_preflight", lambda **kwargs: {
        "status": "passed",
        "checks": [{"name": "date_args", "status": "passed", "detail": None}],
        "failed_checks": [],
    })
    exit_code = cli.main(["--start-date", "2025-12-01", "--end-date", "2026-03-24", "--preflight-only"])
    stdout = capsys.readouterr().out
    assert exit_code == 0
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["preflight_result"]["status"] == "passed"
    assert payload["status"] == "preflight_only"
    assert "workflow_status=preflight_only" in stdout


def test_workflow_runner_returns_one_when_preflight_fails(...):
    ...
    monkeypatch.setattr(cli, "run_workflow_preflight", lambda **kwargs: {
        "status": "failed",
        "checks": [{"name": "strategy_config", "status": "failed", "detail": "boom"}],
        "failed_checks": [{"name": "strategy_config", "detail": "boom"}],
    })
    exit_code = cli.main(["--start-date", "2025-12-01", "--end-date", "2026-03-24"])
    stdout = capsys.readouterr().out
    assert exit_code == 1
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["run_id"]
    assert Path(payload["workflow_manifest_path"]).exists()
    assert payload["failed_step"] == "preflight"
    manifest_payload = json.loads(Path(payload["workflow_manifest_path"]).read_text(encoding="utf-8"))
    assert manifest_payload == payload
    assert "workflow_status=failed" in stdout


def test_workflow_runner_blocked_stdout_status_matches_exit_code(...):
    ...
    monkeypatch.setattr(cli, "run_workflow_preflight", lambda **kwargs: {"status": "passed", "checks": [], "failed_checks": []})
    monkeypatch.setattr(cli, "run_research_governance_pipeline", lambda **kwargs: blocked_result_with_exit_code_2)
    ...
    exit_code = cli.main(["--start-date", "2025-12-01", "--end-date", "2026-03-24", "--fail-on-blocked"])
    stdout = capsys.readouterr().out
    assert exit_code == 2
    assert "workflow_status=blocked" in stdout
```

- [ ] **Step 5: 接线 runner 到 preflight**

在 `scripts/run_end_to_end_workflow.py` 中：

- 增加 `--preflight-only`
- 在任何业务阶段前执行 `run_workflow_preflight(...)`
- preflight 失败时写失败 summary 并返回 `1`
- `--preflight-only` 时写 summary 并返回 `0`
- fatal `failed_step` 新增支持 `preflight` 和 `daily_run`
- preflight 失败时也必须先生成 `run_id`，并同时写出 per-run manifest 与 legacy summary

- [ ] **Step 6: 跑 Task 1 回归**

Run: `pytest tests/test_workflow_preflight.py tests/test_end_to_end_workflow_runner.py -q -k "preflight or blocked_stdout_status"`

Expected:
- PASS

- [ ] **Step 7: 提交 preflight 能力**

```bash
git add src/workflow/__init__.py src/workflow/preflight.py tests/test_workflow_preflight.py scripts/run_end_to_end_workflow.py tests/test_end_to_end_workflow_runner.py
git commit -m "feat: add workflow runner preflight checks"
```

### Task 2: 增加 run_id 与 per-run manifest，保留 legacy summary

**Files:**
- Create: `src/workflow/manifest.py`
- Create: `tests/test_workflow_manifest.py`
- Modify: `scripts/run_end_to_end_workflow.py`
- Modify: `tests/test_end_to_end_workflow_runner.py`

- [ ] **Step 1: 先写 manifest 单测，锁定 run_id 与路径格式**

在 `tests/test_workflow_manifest.py` 中新增：

```python
def test_generate_run_id_is_path_safe():
    import re
    from src.workflow.manifest import generate_run_id

    run_id = generate_run_id()
    assert " " not in run_id
    assert "/" not in run_id
    assert re.match(r"^\d{8}T\d{6}Z-[a-z0-9]{8}$", run_id)


def test_generate_run_id_avoids_collision_with_same_second():
    from datetime import datetime, timezone
    from src.workflow.manifest import generate_run_id

    now = datetime(2026, 3, 25, 1, 2, 3, tzinfo=timezone.utc)
    first = generate_run_id(now=now)
    second = generate_run_id(now=now)

    assert first != second
    assert first.startswith("20260325T010203Z-")
    assert second.startswith("20260325T010203Z-")


def test_write_workflow_manifest_writes_per_run_and_latest_copy(tmp_path):
    from src.workflow.manifest import write_workflow_manifest

    payload = {
        "run_id": "20260325T010203Z-abcd1234",
        "started_at": "2026-03-25T01:02:03Z",
        "finished_at": "2026-03-25T01:02:05Z",
        "status": "succeeded",
        "exit_code": 0,
        "preflight_result": {"status": "passed", "checks": [], "failed_checks": []},
    }
    paths = write_workflow_manifest(payload, root=tmp_path / "reports" / "workflow")

    assert paths["manifest_path"].endswith("runs/20260325T010203Z-abcd1234/workflow_manifest.json")
    assert (tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json").exists()
    manifest_payload = json.loads(Path(paths["manifest_path"]).read_text(encoding="utf-8"))
    latest_payload = json.loads((tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json").read_text(encoding="utf-8"))
    assert manifest_payload["started_at"] == "2026-03-25T01:02:03Z"
    assert manifest_payload["preflight_result"]["status"] == "passed"
    assert latest_payload == manifest_payload
```

- [ ] **Step 2: 跑单测，确认 manifest 模块尚未实现**

Run: `pytest tests/test_workflow_manifest.py -q`

Expected:
- FAIL

- [ ] **Step 3: 实现 manifest 辅助模块**

在 `src/workflow/manifest.py` 中实现：

```python
def generate_run_id(now: datetime | None = None) -> str:
    ...


def write_workflow_manifest(payload: dict[str, Any], root: Path) -> dict[str, str]:
    manifest_path = root / "runs" / payload["run_id"] / "workflow_manifest.json"
    latest_path = root / "end_to_end_workflow_summary.json"
    ...
    return {"manifest_path": str(manifest_path), "latest_summary_path": str(latest_path)}
```

- [ ] **Step 4: 增强 runner 测试，锁定 manifest 合同**

在 `tests/test_end_to_end_workflow_runner.py` 中新增：

```python
def test_workflow_runner_writes_run_id_and_manifest_path(...):
    ...
    exit_code = cli.main(["--start-date", "2025-12-01", "--end-date", "2026-03-24"])
    assert exit_code == 0
    payload = json.loads(summary_path.read_text(encoding="utf-8"))
    assert payload["run_id"]
    assert payload["workflow_manifest_path"].endswith("workflow_manifest.json")
    assert payload["started_at"]
    assert payload["finished_at"]
    assert payload["preflight_result"]["status"] == "passed"
    manifest_payload = json.loads(Path(payload["workflow_manifest_path"]).read_text(encoding="utf-8"))
    assert manifest_payload == payload
```

- [ ] **Step 5: 接线 runner 写 per-run manifest**

要求：
- 所有成功 / blocked / fatal / preflight-only 路径都必须带 `run_id`
- preflight 失败路径也必须带 `run_id`
- 所有 summary 都通过同一 payload 写出
- 继续保留 `reports/workflow/end_to_end_workflow_summary.json`
- payload 至少锁住：`run_id`、`started_at`、`finished_at`、`status`、`exit_code`、`preflight_result`

- [ ] **Step 6: 跑 Task 2 回归**

Run: `pytest tests/test_workflow_manifest.py tests/test_end_to_end_workflow_runner.py -q -k "run_id or manifest"`

Expected:
- PASS

- [ ] **Step 7: 提交 manifest 能力**

```bash
git add src/workflow/manifest.py tests/test_workflow_manifest.py scripts/run_end_to_end_workflow.py tests/test_end_to_end_workflow_runner.py
git commit -m "feat: add workflow runner run manifests"
```

### Task 3: 增强自动化 stdout 合同并补 runner smoke

**Files:**
- Create: `tests/test_end_to_end_workflow_runner_cli_smoke.py`
- Modify: `scripts/run_end_to_end_workflow.py`
- Modify: `tests/test_end_to_end_workflow_runner.py`
- Verify: `tests/test_research_governance_pipeline_cli_smoke.py`

- [ ] **Step 1: 先写 runner smoke，锁定真实 artifact 合同**

在 `tests/test_end_to_end_workflow_runner_cli_smoke.py` 中新增：

```python
def test_end_to_end_workflow_runner_cli_smoke_writes_manifest_and_stdout(tmp_path, monkeypatch, capsys):
    import scripts.run_end_to_end_workflow as cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cli, "run_workflow_preflight", lambda **kwargs: {"status": "passed", "checks": [], "failed_checks": []})
    monkeypatch.setattr(cli, "run_research_governance_pipeline", lambda **kwargs: {...})
    monkeypatch.setattr(cli, "check_governance_health", lambda **kwargs: SimpleNamespace(incidents=[], rollback_recommendation=None))

    exit_code = cli.main(["--start-date", "2025-12-01", "--end-date", "2026-03-24"])

    stdout = capsys.readouterr().out
    assert exit_code == 0
    assert "run_id=" in stdout
    assert "workflow_manifest=" in stdout
    assert "workflow_status=succeeded" in stdout
    assert (tmp_path / "reports" / "workflow" / "end_to_end_workflow_summary.json").exists()
```

- [ ] **Step 2: 跑 smoke，确认当前合同尚未完整落地**

Run: `pytest tests/test_end_to_end_workflow_runner_cli_smoke.py -q`

Expected:
- FAIL

- [ ] **Step 3: 在 runner 中补齐 stdout 合同**

要求：
- 成功 / blocked / preflight-only / fatal 都输出 `run_id=`
- 输出 `workflow_manifest=<path>`
- 输出 `workflow_status=<status>`，且值只能是 `preflight_only|succeeded|blocked|failed`
- 保留现有 `publish_executed=true|false`

- [ ] **Step 4: 完善 smoke 覆盖 pre/post health 工件**

在 smoke 中额外断言：
- pre-publish health report 存在
- post-publish health report 存在且路径不同
- per-run manifest 存在
- legacy summary 存在
- payload `status` 与 stdout 中的 `workflow_status` 一致
- 另在函数级 runner 测试中锁住 `preflight_only`、`blocked`、`failed` 三种非成功 stdout 状态

- [ ] **Step 5: 跑 Task 3 回归**

Run: `pytest tests/test_end_to_end_workflow_runner.py tests/test_end_to_end_workflow_runner_cli_smoke.py -q`

Expected:
- PASS

- [ ] **Step 6: 提交自动化合同与 smoke**

```bash
git add scripts/run_end_to_end_workflow.py tests/test_end_to_end_workflow_runner.py tests/test_end_to_end_workflow_runner_cli_smoke.py
git commit -m "feat: operationalize workflow runner artifacts"
```

### Task 4: 更新 README / tasks 并做最终聚焦回归

**Files:**
- Modify: `README.md`
- Modify: `tasks/todo.md`
- Verify: `docs/superpowers/specs/2026-03-25-workflow-runner-operationalization-design.md`
- Verify: `docs/superpowers/plans/2026-03-25-workflow-runner-operationalization-implementation.md`

- [ ] **Step 1: 更新 README，加入 preflight / manifest / automation 用法**

至少补充：
- `--preflight-only` 示例
- `run_id / workflow_manifest / workflow_status` stdout 说明
- per-run manifest 与 legacy summary 的区别

- [ ] **Step 2: 更新 `tasks/todo.md`，记录本子项目 spec / plan / task 提交 / 审查 / 验证**

要求：
- 与实际提交和 fresh 验证保持一致

- [ ] **Step 3: 跑最终聚焦回归**

Run: `pytest tests/test_workflow_preflight.py tests/test_workflow_manifest.py tests/test_end_to_end_workflow_runner.py tests/test_end_to_end_workflow_runner_cli_smoke.py tests/test_research_governance_pipeline.py tests/test_research_governance_pipeline_cli_smoke.py tests/test_pipeline_e2e.py -q`

Expected:
- PASS

- [ ] **Step 4: 提交文档更新**

```bash
git add README.md tasks/todo.md
git commit -m "docs: add workflow runner operationalization plan"
```

## 实施备注

- `run_id` 与 manifest 写盘必须走同一 helper，避免成功/失败路径 schema 漂移
- `workflow_status` 只能输出 `preflight_only|succeeded|blocked|failed`
- `--preflight-only` 不应触发 daily / research / health / publish 任一业务阶段
- runner smoke 重点锁 artifact 与 stdout 合同，不重复验证上游策略逻辑
- 只有在现有 `scripts/run_end_to_end_workflow.py` 继续明显膨胀时，才考虑下一轮再抽 service 层
