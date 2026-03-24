# Research-To-Governance 统一编排 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增一条统一入口，用一条命令跑完 `research -> summary -> governance cycle/review`，同时保留既有产物并额外输出可供自动化消费的 `pipeline summary`。

**Architecture:** 新增 `src/governance_pipeline.py` 作为统一编排服务，直接复用 `run_research_pipeline()`、`aggregate_research_reports()`、`build_report_portal()` 与 `run_governance_cycle()` 的 Python 返回值，不解析旧脚本 stdout。再新增一个薄 CLI `scripts/run_research_governance_pipeline.py`，只负责参数解析、打印摘要和退出码。旧脚本全部保留，不改变默认行为。

**Tech Stack:** Python 3、argparse、Pydantic、pytest

---

## 文件边界

### Create

- `src/governance_pipeline.py`
  - 提供统一编排服务
  - 写 cycle artifact / review artifact / pipeline summary
  - 处理 `blocked` 与 fatal error 的退出语义
- `scripts/run_research_governance_pipeline.py`
  - 统一编排 CLI
  - 解析参数、打印简要摘要、返回退出码
- `tests/test_research_governance_pipeline.py`
  - 覆盖服务 happy path / blocked / fatal error / CLI 退出码

### Modify

- `README.md`
  - 增加统一编排脚本用法
- `tasks/todo.md`
  - 增加本阶段执行记录与验证结果

### Verify Only

- `scripts/run_research.py`
- `scripts/summarize_research_reports.py`
- `scripts/run_governance_cycle.py`
- `scripts/run_governance_review.py`
- `src/research_pipeline.py`
- `src/research_summary.py`
- `src/report_portal.py`
- `src/governance/automation.py`

## 实施任务

### Task 1: 建立统一编排服务的 happy path

**Files:**
- Create: `src/governance_pipeline.py`
- Create: `tests/test_research_governance_pipeline.py`

- [ ] **Step 1: 先写失败测试，锁定 happy path 的编排输出**

```python
def test_run_research_governance_pipeline_writes_all_expected_artifacts(tmp_path, monkeypatch):
    from src.governance.automation import GovernanceCycleResult
    from src.governance.models import GovernanceDecision
    from src.governance_pipeline import run_research_governance_pipeline

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "src.governance_pipeline.run_research_pipeline",
        lambda **_: {
            "report_paths": {
                "markdown": "reports/research/2026-03-24.md",
                "json": "reports/research/2026-03-24.json",
                "csv": "reports/research/2026-03-24.csv",
            },
            "portal_paths": {
                "html": "reports/index.html",
                "json": "reports/portal_summary.json",
            },
        },
    )
    monkeypatch.setattr(
        "src.governance_pipeline.aggregate_research_reports",
        lambda **_: {
            "report_summaries": [{"report_date": "2026-03-24"}],
            "candidate_leaderboard": [],
            "candidate_observations": [],
            "candidate_regime_leaderboard": [],
            "output_paths": {"json": "reports/research/summary/research_summary.json"},
        },
    )
    monkeypatch.setattr(
        "src.governance_pipeline.build_report_portal",
        lambda **_: {"output_paths": {"html": "reports/index.html", "json": "reports/portal_summary.json"}},
    )
    monkeypatch.setattr(
        "src.governance_pipeline.run_governance_cycle",
        lambda **_: GovernanceCycleResult(
            decision=GovernanceDecision(
                id=12,
                decision_date=date(2026, 3, 24),
                current_strategy_id="trend_momentum",
                selected_strategy_id="risk_adjusted_momentum",
                previous_strategy_id="trend_momentum",
                fallback_strategy_id="trend_momentum",
                decision_type="switch",
                review_status="ready",
            ),
            summary_hash="summary-hash-001",
            created_new=True,
        ),
    )

    result = run_research_governance_pipeline(
        start_date=date(2025, 12, 1),
        end_date=date(2026, 3, 24),
    )

    assert result["exit_code"] == 0
    assert Path(result["governance_cycle_path"]).exists()
    assert Path(result["governance_review_path"]).exists()
    assert Path(result["pipeline_summary_path"]).exists()
```

- [ ] **Step 2: 跑测试确认当前缺少统一编排服务**

Run: `pytest tests/test_research_governance_pipeline.py -q`

Expected:
- FAIL，提示 `ModuleNotFoundError: src.governance_pipeline`

- [ ] **Step 3: 实现最小编排服务骨架与 artifact 写出 helper**

```python
def run_research_governance_pipeline(...):
    research_result = run_research_pipeline(...)
    summary_result = aggregate_research_reports(...)
    portal_result = build_report_portal(...)
    cycle_result = _run_cycle(...)
    cycle_path = _write_cycle_artifact(cycle_result)
    review_path = _write_review_artifact(cycle_result.decision)
    summary_path = _write_pipeline_summary(...)
    return {
        "exit_code": 0,
        "research_result": research_result,
        "summary_result": summary_result,
        "portal_result": portal_result,
        "cycle_result": cycle_result,
        "governance_cycle_path": str(cycle_path),
        "governance_review_path": str(review_path),
        "pipeline_summary_path": str(summary_path),
    }
```

要求：
- research 继续沿用 `end_date` 命名
- governance cycle / review / pipeline summary 继续沿用 `date.today()` 命名
- review artifact 直接复用本次 cycle 已得到的 `decision`
- summary 继续聚合 `reports/research/*.json` 全历史目录

- [ ] **Step 4: 回跑 happy path 测试，确认统一编排服务最小闭合**

Run: `pytest tests/test_research_governance_pipeline.py -q`

Expected:
- 至少 `happy path` 用例 PASS

- [ ] **Step 5: 提交统一编排服务基础层**

```bash
git add src/governance_pipeline.py tests/test_research_governance_pipeline.py
git commit -m "feat: add research governance pipeline service"
```

### Task 2: 补齐 blocked / fatal error 语义与 partial summary

**Files:**
- Modify: `src/governance_pipeline.py`
- Modify: `tests/test_research_governance_pipeline.py`

- [ ] **Step 1: 先写失败测试，锁定 blocked 默认成功与 fatal error 行为**

```python
def test_pipeline_returns_zero_by_default_when_governance_is_blocked(...):
    result = run_research_governance_pipeline(..., fail_on_blocked=False)

    assert result["exit_code"] == 0
    payload = json.loads(Path(result["pipeline_summary_path"]).read_text(encoding="utf-8"))
    assert payload["final_decision"]["review_status"] == "blocked"
    assert payload["final_decision"]["blocked_reasons"] == ["SELECTED_STRATEGY_REGIME_MISMATCH"]


def test_pipeline_returns_two_when_fail_on_blocked_enabled(...):
    result = run_research_governance_pipeline(..., fail_on_blocked=True)

    assert result["exit_code"] == 2


def test_pipeline_writes_partial_summary_when_summary_step_fails(...):
    with pytest.raises(RuntimeError, match="boom"):
        run_research_governance_pipeline(...)

    payload = json.loads(Path("reports/governance/pipeline/2026-03-24.json").read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["failed_step"] == "summary"
```

- [ ] **Step 2: 跑测试确认当前还没有 blocked / fatal 语义**

Run: `pytest tests/test_research_governance_pipeline.py -q`

Expected:
- FAIL，`exit_code` 或 partial `pipeline summary` 与预期不符

- [ ] **Step 3: 以最小改动补齐 blocked / fatal error 语义**

```python
try:
    ...
except Exception as exc:
    summary_path = _write_pipeline_summary(
        status="failed",
        failed_step=current_step,
        error={"type": type(exc).__name__, "message": str(exc)},
        ...
    )
    raise

exit_code = 0
if cycle_result.decision.review_status == "blocked" and fail_on_blocked:
    exit_code = 2
```

要求：
- 服务层 fatal error 时先写 partial `pipeline summary`，再继续抛出异常
- `blocked + fail_on_blocked=True` 返回 `2`
- fatal error 时仍写 partial `pipeline summary`
- `blocked` 不是流程失败，仍写 cycle artifact / review artifact / pipeline summary

- [ ] **Step 4: 回跑服务测试，确认三类状态都可测**

Run: `pytest tests/test_research_governance_pipeline.py -q`

Expected:
- PASS

- [ ] **Step 5: 提交语义补齐层**

```bash
git add src/governance_pipeline.py tests/test_research_governance_pipeline.py
git commit -m "feat: add pipeline blocked and failure semantics"
```

### Task 3: 增加统一编排 CLI 并锁定退出码

**Files:**
- Create: `scripts/run_research_governance_pipeline.py`
- Modify: `tests/test_research_governance_pipeline.py`

- [ ] **Step 1: 先写失败测试，锁定 CLI 参数透传、stdout 与退出码**

```python
def test_pipeline_cli_prints_summary_and_returns_zero(monkeypatch, capsys):
    import scripts.run_research_governance_pipeline as cli

    monkeypatch.setattr(
        cli,
        "run_research_governance_pipeline",
        lambda **_: {
            "exit_code": 0,
            "research_result": {"report_paths": {"json": "reports/research/2026-03-24.json"}},
            "summary_result": {"output_paths": {"json": "reports/research/summary/research_summary.json"}},
            "cycle_result": {"decision": {"id": 12, "review_status": "ready", "blocked_reasons": []}},
            "pipeline_summary_path": "reports/governance/pipeline/2026-03-24.json",
        },
    )

    exit_code = cli.main(["--start-date", "2025-12-01", "--end-date", "2026-03-24"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "research_report=reports/research/2026-03-24.json" in captured.out


def test_pipeline_cli_returns_two_when_blocked_and_fail_on_blocked(monkeypatch):
    import scripts.run_research_governance_pipeline as cli

    monkeypatch.setattr(
        cli,
        "run_research_governance_pipeline",
        lambda **_: {
            "exit_code": 2,
            "research_result": {"report_paths": {"json": "reports/research/2026-03-24.json"}},
            "summary_result": {"output_paths": {"json": "reports/research/summary/research_summary.json"}},
            "cycle_result": {
                "decision": {"id": 12, "review_status": "blocked", "blocked_reasons": ["SELECTED_STRATEGY_REGIME_MISMATCH"]},
            },
            "pipeline_summary_path": "reports/governance/pipeline/2026-03-24.json",
        },
    )

    assert cli.main(["--fail-on-blocked"]) == 2


def test_pipeline_cli_returns_one_when_service_raises(monkeypatch):
    import scripts.run_research_governance_pipeline as cli

    monkeypatch.setattr(
        cli,
        "run_research_governance_pipeline",
        lambda **_: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    assert cli.main(["--start-date", "2025-12-01", "--end-date", "2026-03-24"]) == 1
```

- [ ] **Step 2: 跑测试确认当前还没有统一编排 CLI**

Run: `pytest tests/test_research_governance_pipeline.py -q`

Expected:
- FAIL，`scripts.run_research_governance_pipeline` 不存在

- [ ] **Step 3: 实现薄 CLI，只负责参数解析与结果打印**

```python
def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        result = run_research_governance_pipeline(...)
    except Exception as exc:
        print(f"pipeline_error={type(exc).__name__}:{exc}")
        return 1
    print(f"research_report={result['research_result']['report_paths']['json']}")
    print(f"summary_json={result['summary_result']['output_paths']['json']}")
    print(
        "decision_id={decision_id} review_status={review_status} blocked_reasons={blocked_reasons}".format(...)
    )
    print(f"pipeline_summary={result['pipeline_summary_path']}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
```

要求：
- CLI 不解析旧脚本 stdout
- CLI 不直接实现业务逻辑
- `candidate-config` 仍沿用 `run_research.py` 的 YAML 加载语义
- CLI 将服务层 fatal exception 映射为退出码 `1`

- [ ] **Step 4: 回跑 CLI 测试，确认退出码与 stdout 契约闭合**

Run: `pytest tests/test_research_governance_pipeline.py -q`

Expected:
- PASS

- [ ] **Step 5: 提交统一编排 CLI**

```bash
git add scripts/run_research_governance_pipeline.py tests/test_research_governance_pipeline.py
git commit -m "feat: add research governance pipeline cli"
```

### Task 4: 更新文档与任务跟踪，并做聚焦验证

**Files:**
- Modify: `README.md`
- Modify: `tasks/todo.md`
- Verify: `tests/test_research_governance_pipeline.py`
- Verify: `tests/test_governance_automation.py`

- [ ] **Step 1: 更新 README，补统一编排命令说明**

```md
python scripts/run_research_governance_pipeline.py --start-date 2025-12-01 --end-date 2026-03-24
python scripts/run_research_governance_pipeline.py --start-date 2025-12-01 --end-date 2026-03-24 --fail-on-blocked
```

- [ ] **Step 2: 在 `tasks/todo.md` 增加本阶段执行清单**

```md
## 2026-03-24 Research-To-Governance 统一编排
- [ ] 统一编排服务
- [ ] blocked / fatal error 语义
- [ ] 统一编排 CLI
- [ ] 文档与验证
```

- [ ] **Step 3: 运行聚焦回归**

Run: `pytest tests/test_research_governance_pipeline.py tests/test_governance_automation.py -q`

Expected:
- PASS

- [ ] **Step 4: 检查工作区，仅保留本阶段涉及文件**

Run: `git status --short`

Expected:
- 仅出现：
  - `src/governance_pipeline.py`
  - `scripts/run_research_governance_pipeline.py`
  - `tests/test_research_governance_pipeline.py`
  - `README.md`
  - `tasks/todo.md`

- [ ] **Step 5: 提交文档与跟踪更新**

```bash
git add README.md tasks/todo.md
git commit -m "docs: track research governance pipeline rollout"
```

## 实施备注

- 本计划默认不修改旧脚本行为；新入口只做新增能力
- `run_research_pipeline()` 现有 portal 刷新副作用保留
- summary 步骤仍显式调用 `build_report_portal()`，以保持与 `scripts/summarize_research_reports.py` 一致的结果语义
- fatal error 时写 partial `pipeline summary`，但不要伪造 cycle / review artifact
