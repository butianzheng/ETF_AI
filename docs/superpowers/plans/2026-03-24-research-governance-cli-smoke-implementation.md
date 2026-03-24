# Research-To-Governance CLI Smoke Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `scripts/run_research_governance_pipeline.py` 增加一组独立 smoke，用真实 `CLI + service` 覆盖 `happy path`、`blocked`、fatal 三类运行语义，并在临时目录中真实落盘 artifact。

**Architecture:** 新增独立测试文件 `tests/test_research_governance_pipeline_cli_smoke.py`。测试直接调用 `scripts.run_research_governance_pipeline.main(argv)`，不 mock CLI 或 service；仅 monkeypatch 研究/治理内部重依赖，并让真实 `aggregate_research_reports()`、真实 `build_report_portal()` 和真实 artifact helper 负责写盘。默认不改生产代码，只有在 TDD 证明没有稳定注入点时，才对 CLI / service 做最小改动。

**Tech Stack:** Python 3、pytest、monkeypatch、tmp_path、临时 SQLite

---

## 文件边界

### Create

- `tests/test_research_governance_pipeline_cli_smoke.py`
  - 独立 smoke 文件
  - 包含最小 candidate-config YAML helper
  - 覆盖 `happy path`、`blocked`、fatal 三类 CLI smoke

### Modify (Only If TDD Proves Necessary)

- `scripts/run_research_governance_pipeline.py`
  - 仅当 smoke 证明缺少稳定注入点时，允许做最小 CLI 注入点增强
- `src/governance_pipeline.py`
  - 仅当 smoke 证明 service 缺少稳定注入点时，允许做最小 service 注入点增强

### Verify Only

- `tests/conftest.py`
- `tests/test_research_governance_pipeline.py`
- `tests/test_report_portal.py`
- `scripts/run_research.py`
- `src/research_summary.py`
- `src/report_portal.py`

## 实施任务

### Task 1: 建立 smoke 脚手架并打通 happy path

**Files:**
- Create: `tests/test_research_governance_pipeline_cli_smoke.py`
- Verify: `tests/conftest.py`
- Verify: `src/research_summary.py`
- Verify: `src/report_portal.py`

- [ ] **Step 1: 先写失败测试，锁定真实 CLI happy path smoke**

```python
import json
from datetime import date
from pathlib import Path


def _write_candidate_config(path: Path) -> Path:
    path.write_text(
        """
research:
  candidates:
    - name: baseline_trend
      strategy_id: trend_momentum
      description: baseline
      overrides: {}
""".strip(),
        encoding="utf-8",
    )
    return path


def test_research_governance_pipeline_cli_smoke_happy_path(tmp_path, monkeypatch, capsys):
    import scripts.run_research_governance_pipeline as cli
    import src.governance_pipeline as pipeline
    from src.governance.automation import GovernanceCycleResult
    from src.governance.models import GovernanceDecision

    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 24)

    class DummyGovernanceConfig:
        pass

    class DummyStrategyConfig:
        governance = DummyGovernanceConfig()

    candidate_config = _write_candidate_config(tmp_path / "research_candidates.yaml")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pipeline, "date", FakeDate)
    monkeypatch.setattr(
        pipeline,
        "run_research_pipeline",
        lambda **kwargs: {
            "report_paths": {
                "markdown": str(tmp_path / "reports" / "research" / "2026-03-24.md"),
                "json": str(tmp_path / "reports" / "research" / "2026-03-24.json"),
                "csv": str(tmp_path / "reports" / "research" / "2026-03-24.csv"),
            },
            "portal_paths": {},
        },
    )
    monkeypatch.setattr(
        pipeline,
        "run_governance_cycle",
        lambda **kwargs: GovernanceCycleResult(
            decision=GovernanceDecision(
                decision_date=FakeDate.today(),
                current_strategy_id="trend_momentum",
                selected_strategy_id="risk_adjusted_momentum",
                previous_strategy_id="trend_momentum",
                fallback_strategy_id="trend_momentum",
                decision_type="switch",
                review_status="ready",
                blocked_reasons=[],
                reason_codes=["CHALLENGER_PROMOTED"],
            ),
            summary_hash="summary-hash-smoke-happy",
            created_new=True,
        ),
    )
    monkeypatch.setattr(
        pipeline.config_loader,
        "load_strategy_config",
        lambda: DummyStrategyConfig(),
    )
    monkeypatch.setattr(
        pipeline.config_loader,
        "load_production_strategy_id",
        lambda: "trend_momentum",
    )

    exit_code = cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--candidate-config",
            str(candidate_config),
        ]
    )

    stdout = capsys.readouterr().out
    assert exit_code == 0
    assert "research_report=" in stdout
    assert "summary_json=" in stdout
    assert "decision_id=" in stdout
    assert "pipeline_summary=" in stdout
```

- [ ] **Step 2: 跑测试确认当前 smoke 还没真正打通**

Run: `pytest tests/test_research_governance_pipeline_cli_smoke.py::test_research_governance_pipeline_cli_smoke_happy_path -q`

Expected:
- FAIL
- 推荐失败形态：`aggregate_research_reports()` 报 `FileNotFoundError`
- 原因：Step 1 的 `run_research_pipeline` stub 只返回路径，还没有真实写最小 research 报告

- [ ] **Step 3: 在测试文件中补最小 research 报告 helper，并让真实 summary/portal 可消费**

```python
def _write_minimal_research_report(base_dir: Path, report_date: str = "2026-03-24") -> dict[str, str]:
    report_dir = base_dir / "reports" / "research"
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"{report_date}.json"
    md_path = report_dir / f"{report_date}.md"
    csv_path = report_dir / f"{report_date}.csv"

    json_path.write_text(
        json.dumps(
            {
                "comparison_rows": [
                    {
                        "name": "baseline_trend",
                        "candidate_name": "baseline_trend",
                        "strategy_id": "trend_momentum",
                        "description": "baseline",
                        "overrides": {},
                        "annual_return": 0.18,
                        "sharpe": 1.2,
                        "max_drawdown": -0.08,
                        "composite_score": 1.2,
                    }
                ],
                "research_output": {
                    "ranked_candidates": [
                        {
                            "name": "baseline_trend",
                            "candidate_name": "baseline_trend",
                            "strategy_id": "trend_momentum",
                            "description": "baseline",
                            "overrides": {},
                            "annual_return": 0.18,
                            "sharpe": 1.2,
                            "max_drawdown": -0.08,
                            "composite_score": 1.2,
                        }
                    ],
                    "recommendation": "继续观察 baseline_trend",
                    "overfit_risk": "low",
                    "summary": "smoke happy path",
                },
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    md_path.write_text("# Smoke Research Report", encoding="utf-8")
    csv_path.write_text("name,annual_return\nbaseline_trend,0.18\n", encoding="utf-8")
    return {"markdown": str(md_path), "json": str(json_path), "csv": str(csv_path)}


def fake_run_research_pipeline(**kwargs):
    report_paths = _write_minimal_research_report(tmp_path, report_date="2026-03-24")
    assert kwargs["candidate_specs"] == [
        {
            "name": "baseline_trend",
            "strategy_id": "trend_momentum",
            "description": "baseline",
            "overrides": {},
        }
    ]
    return {"report_paths": report_paths, "portal_paths": {}}


def fake_run_governance_cycle(**kwargs):
    draft = GovernanceDecision(
        decision_date=FakeDate.today(),
        current_strategy_id="trend_momentum",
        selected_strategy_id="risk_adjusted_momentum",
        previous_strategy_id="trend_momentum",
        fallback_strategy_id="trend_momentum",
        decision_type="switch",
        review_status="ready",
        blocked_reasons=[],
        reason_codes=["CHALLENGER_PROMOTED"],
    )
    saved = kwargs["repo"].save_draft(draft)
    return GovernanceCycleResult(
        decision=saved,
        summary_hash="summary-hash-smoke-happy",
        created_new=True,
    )
```

要求：
- `happy path` 默认走真实 `aggregate_research_reports()`
- `happy path` 默认走真实 `build_report_portal()`
- 用 `tests/conftest.py` 提供的临时 SQLite 支撑真实 portal governance summary 读取

- [ ] **Step 4: 回跑 happy path smoke，确认 CLI + service + artifact 闭合**

Run: `pytest tests/test_research_governance_pipeline_cli_smoke.py::test_research_governance_pipeline_cli_smoke_happy_path -q`

Expected:
- PASS
- 同时断言：
  - `reports/research/summary/research_summary.json` 存在
  - `reports/governance/cycle/2026-03-24.json` 存在
  - `reports/governance/2026-03-24.json` 存在
  - `reports/governance/pipeline/2026-03-24.json` 存在
  - `reports/portal_summary.json` 存在
  - `pipeline summary.final_decision.review_status == "ready"`

- [ ] **Step 5: 提交 happy path smoke 基础层**

```bash
git add tests/test_research_governance_pipeline_cli_smoke.py
git commit -m "test: add happy path governance cli smoke"
```

### Task 2: 补齐 blocked smoke 与退出码语义

**Files:**
- Modify: `tests/test_research_governance_pipeline_cli_smoke.py`
- Verify: `scripts/run_research_governance_pipeline.py`
- Verify: `src/governance_pipeline.py`

- [ ] **Step 1: 先写失败测试，锁定 blocked 的两种 CLI 语义**

```python
def test_research_governance_pipeline_cli_smoke_blocked_returns_zero_by_default(...):
    exit_code = cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--candidate-config",
            str(candidate_config),
        ]
    )

    assert exit_code == 0
    payload = json.loads(Path("reports/governance/pipeline/2026-03-24.json").read_text(encoding="utf-8"))
    assert payload["final_decision"]["review_status"] == "blocked"
    assert payload["final_decision"]["blocked_reasons"] == ["SELECTED_STRATEGY_REGIME_MISMATCH"]


def test_research_governance_pipeline_cli_smoke_blocked_returns_two_with_fail_flag(...):
    exit_code = cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--candidate-config",
            str(candidate_config),
            "--fail-on-blocked",
        ]
    )

    assert exit_code == 2
    assert Path("reports/governance/cycle/2026-03-24.json").exists()
    assert Path("reports/governance/2026-03-24.json").exists()
    assert Path("reports/governance/pipeline/2026-03-24.json").exists()
```

- [ ] **Step 2: 跑测试确认当前 smoke helper 还不支持 blocked 分支**

Run: `pytest tests/test_research_governance_pipeline_cli_smoke.py -q -k "smoke_blocked"`

Expected:
- FAIL
- 推荐失败形态：
  - `review_status` 仍然是 `"ready"`
  - 或 helper 还未支持 `blocked_reasons` / `--fail-on-blocked` 组合

- [ ] **Step 3: 把 smoke helper 参数化到 blocked 场景，但保持真实 CLI + service**

```python
def _install_governance_cycle_stub(
    monkeypatch,
    pipeline_module,
    *,
    run_date_cls,
    review_status: str,
    blocked_reasons: list[str],
    summary_hash: str,
):
    def fake_run_governance_cycle(**kwargs):
        draft = GovernanceDecision(
            decision_date=run_date_cls.today(),
            current_strategy_id="trend_momentum",
            selected_strategy_id="risk_adjusted_momentum",
            previous_strategy_id="trend_momentum",
            fallback_strategy_id="trend_momentum",
            decision_type="switch",
            review_status=review_status,
            blocked_reasons=blocked_reasons,
            reason_codes=["REGIME_GATE_BLOCKED"] if blocked_reasons else ["CHALLENGER_PROMOTED"],
        )
        saved = kwargs["repo"].save_draft(draft)
        return GovernanceCycleResult(
            decision=saved,
            summary_hash=summary_hash,
            created_new=True,
        )

    monkeypatch.setattr(pipeline_module, "run_governance_cycle", fake_run_governance_cycle)
```

要求：
- default blocked smoke 不传 `--fail-on-blocked`，退出码必须是 `0`
- fail-flag blocked smoke 传 `--fail-on-blocked`，退出码必须是 `2`
- 两个 smoke 都必须证明：
  - artifact 没有因为 `blocked` 被短路
  - `pipeline summary.final_decision.blocked_reasons` 正确

- [ ] **Step 4: 回跑 blocked smoke，确认两种退出码都闭合**

Run: `pytest tests/test_research_governance_pipeline_cli_smoke.py -q -k "smoke_blocked"`

Expected:
- PASS

- [ ] **Step 5: 提交 blocked smoke**

```bash
git add tests/test_research_governance_pipeline_cli_smoke.py
git commit -m "test: cover blocked governance cli smoke"
```

### Task 3: 补齐 fatal smoke，并做聚焦回归

**Files:**
- Modify: `tests/test_research_governance_pipeline_cli_smoke.py`
- Verify: `scripts/run_research_governance_pipeline.py`
- Verify: `src/governance_pipeline.py`
- Verify: `tests/test_research_governance_pipeline.py`

- [ ] **Step 1: 先写失败测试，锁定 fatal CLI smoke**

```python
def test_research_governance_pipeline_cli_smoke_fatal_writes_partial_summary_and_returns_one(
    tmp_path, monkeypatch, capsys
):
    import scripts.run_research_governance_pipeline as cli
    import src.governance_pipeline as pipeline

    class FakeDate(date):
        @classmethod
        def today(cls):
            return cls(2026, 3, 24)

    candidate_config = _write_candidate_config(tmp_path / "research_candidates.yaml")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(pipeline, "date", FakeDate)
    monkeypatch.setattr(pipeline, "run_research_pipeline", fake_run_research_pipeline)
    monkeypatch.setattr(
        pipeline,
        "aggregate_research_reports",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("summary smoke fatal")),
    )

    exit_code = cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--candidate-config",
            str(candidate_config),
        ]
    )

    stderr = capsys.readouterr().err
    partial_summary_path = tmp_path / "reports" / "governance" / "pipeline" / "2026-03-24.json"
    assert exit_code == 1
    assert "fatal_error=RuntimeError: summary smoke fatal" in stderr
    assert partial_summary_path.exists()
    payload = json.loads(partial_summary_path.read_text(encoding="utf-8"))
    assert payload["status"] == "failed"
    assert payload["failed_step"] == "summary"
    assert payload["error"]["type"] == "RuntimeError"
    assert payload["error"]["message"] == "summary smoke fatal"
    assert not (tmp_path / "reports" / "governance" / "cycle" / "2026-03-24.json").exists()
    assert not (tmp_path / "reports" / "governance" / "2026-03-24.json").exists()
    assert not (tmp_path / "reports" / "portal_summary.json").exists()
```

- [ ] **Step 2: 跑测试确认 fatal smoke 还未闭合**

Run: `pytest tests/test_research_governance_pipeline_cli_smoke.py -q -k "smoke_fatal"`

Expected:
- FAIL
- 推荐失败形态：
  - helper 还没有共用到真实最小 research 输入
  - 或 `stderr` / partial summary 断言与现有实现不一致

- [ ] **Step 3: 用最小改动打通 fatal smoke**

要求：
- 默认只改 `tests/test_research_governance_pipeline_cli_smoke.py`
- 继续复用 Task 1 的最小 research helper
- 如果 TDD 证明当前 CLI / service 没有稳定注入点，再最小修改生产代码
- 不得改变现有 `CLI + service` 对外语义

- [ ] **Step 4: 跑 smoke 文件与聚焦回归**

Run: `pytest tests/test_research_governance_pipeline_cli_smoke.py -q`

Expected:
- PASS

Run: `pytest tests/test_research_governance_pipeline.py tests/test_research_governance_pipeline_cli_smoke.py -q`

Expected:
- PASS

- [ ] **Step 5: 提交 fatal smoke 与聚焦回归**

```bash
git add tests/test_research_governance_pipeline_cli_smoke.py
git commit -m "test: add fatal governance cli smoke"
```

## 实施备注

- `tests/conftest.py` 已经把 ORM 切到临时 SQLite；happy / blocked smoke 可直接复用
- `happy / blocked` 默认应 stub `run_research_pipeline`，真实执行 `aggregate_research_reports()` 与 `build_report_portal()`
- `fatal` 默认让 `aggregate_research_reports()` 在 `summary` 步骤抛错，避免引入不必要变量
- 本计划默认不更新 README / `tasks/todo.md`；若后续需要记录该 smoke rollout，再单独开文档任务
