# Shared Candidate-Config Helper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `candidate-config` 建立共享生产 helper 与测试 support helper，收敛两个 CLI 以及相关 smoke/test 的重复配置加载逻辑，同时保持现有 CLI 对外语义不变。

**Architecture:** 新增一个薄的生产模块 `src/research_candidate_config.py` 负责外部 YAML 读取、`ResearchConfig` 校验和 `candidate_specs` 转换；新增 `tests/support/research_candidates.py` 统一候选配置样例、YAML 写入与期望值断言。两个 CLI 仅切换到共享 helper，不改变参数或默认行为；现有测试改为围绕共享边界做校验与复用。

**Tech Stack:** Python 3、pytest、monkeypatch、PyYAML、Pydantic

---

## 文件边界

### Create

- `src/research_candidate_config.py`
- `tests/support/__init__.py`
- `tests/support/research_candidates.py`

### Modify

- `scripts/run_research.py`
- `scripts/run_research_governance_pipeline.py`
- `tests/test_research_pipeline.py`
- `tests/test_research_governance_pipeline.py`
- `tests/test_research_governance_pipeline_cli_smoke.py`
- `tasks/todo.md`

### Verify Only

- `src/core/config.py`
- `src/research_pipeline.py`
- `src/governance_pipeline.py`

## 实施任务

### Task 1: 建立共享生产 helper，并把候选配置解析测试迁到共享边界

**Files:**
- Create: `src/research_candidate_config.py`
- Modify: `tests/test_research_pipeline.py`
- Verify: `src/core/config.py`
- Verify: `scripts/run_research.py`
- Verify: `scripts/run_research_governance_pipeline.py`

- [ ] **Step 1: 先写失败测试，锁定共享 helper 的解析语义**

在 `tests/test_research_pipeline.py` 中去掉对脚本私有 `_load_candidate_specs` 的依赖，改为直接测试新的共享模块：

```python
from src.research_candidate_config import load_candidate_specs, parse_candidate_config_data


def test_parse_candidate_config_data_returns_candidate_specs():
    data = {
        "research": {
            "candidates": [
                {
                    "name": "fast_rebalance",
                    "strategy_id": "risk_adjusted_momentum",
                    "description": "test candidate",
                    "overrides": {
                        "strategy_params": {
                            "volatility_penalty_weight": 0.8,
                        }
                    },
                }
            ]
        }
    }

    assert parse_candidate_config_data(data) == [
        {
            "name": "fast_rebalance",
            "strategy_id": "risk_adjusted_momentum",
            "description": "test candidate",
            "overrides": {
                "strategy_params": {
                    "volatility_penalty_weight": 0.8,
                }
            },
        }
    ]


def test_load_candidate_specs_returns_none_without_candidate_config():
    assert load_candidate_specs(None) is None
```

- [ ] **Step 2: 跑测试，确认共享模块尚未实现**

Run: `pytest tests/test_research_pipeline.py -q -k "candidate_specs or parse_candidate_config_data"`

Expected:
- FAIL
- 推荐失败形态：`ModuleNotFoundError: No module named 'src.research_candidate_config'`

- [ ] **Step 3: 新增共享生产 helper，最小实现 YAML 读取与数据解析**

在 `src/research_candidate_config.py` 中实现：

```python
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from src.core.config import ResearchConfig


def parse_candidate_config_data(data: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = ResearchConfig(**data["research"]).candidates
    return [candidate.model_dump() for candidate in candidates]


def load_candidate_specs(candidate_config: str | Path | None) -> list[dict[str, Any]] | None:
    if candidate_config is None:
        return None
    config_path = Path(candidate_config)
    with open(config_path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return parse_candidate_config_data(data)
```

要求：
- 保持 `candidate_config is None -> None`
- 不引入默认配置缓存逻辑
- 只负责外部 YAML 读取与 `candidate_specs` 转换

- [ ] **Step 4: 回跑解析测试，确认共享边界闭合**

Run: `pytest tests/test_research_pipeline.py -q -k "candidate_specs or parse_candidate_config_data"`

Expected:
- PASS

- [ ] **Step 5: 提交共享生产 helper**

```bash
git add src/research_candidate_config.py tests/test_research_pipeline.py
git commit -m "feat: add shared candidate config loader"
```

### Task 2: 切换两个 CLI 到共享 helper，并用 wiring test 锁定调用路径

**Files:**
- Modify: `scripts/run_research.py`
- Modify: `scripts/run_research_governance_pipeline.py`
- Modify: `tests/test_research_pipeline.py`
- Modify: `tests/test_research_governance_pipeline.py`

- [ ] **Step 1: 先写失败测试，锁定两个 CLI 都走共享 helper**

在 `tests/test_research_pipeline.py` 中新增：

```python
def test_run_research_main_uses_shared_candidate_specs_loader(tmp_path, monkeypatch):
    import argparse
    import scripts.run_research as cli

    forwarded = {}
    sentinel_specs = [{"name": "sentinel", "strategy_id": "trend_momentum", "description": "x", "overrides": {}}]
    config_path = tmp_path / "research.yaml"
    config_path.write_text("research:\n  candidates: []\n", encoding="utf-8")

    monkeypatch.setattr(
        cli,
        "_parse_args",
        lambda: argparse.Namespace(
            start_date="2025-12-01",
            end_date="2026-03-24",
            initial_capital=123456.78,
            fee_rate=0.0025,
            candidate_config=str(config_path),
            log_level="DEBUG",
        ),
    )
    monkeypatch.setattr(cli, "load_candidate_specs", lambda path: sentinel_specs, raising=False)
    monkeypatch.setattr(cli, "run_research_pipeline", lambda **kwargs: forwarded.update(kwargs))

    cli.main()

    assert forwarded["candidate_specs"] is sentinel_specs
    assert forwarded["initial_capital"] == pytest.approx(123456.78)
    assert forwarded["fee_rate"] == pytest.approx(0.0025)
    assert forwarded["log_level"] == "DEBUG"
```

在 `tests/test_research_governance_pipeline.py` 中新增：

```python
def test_research_governance_pipeline_cli_main_uses_shared_candidate_specs_loader(tmp_path, monkeypatch):
    import scripts.run_research_governance_pipeline as cli

    sentinel_specs = [{"name": "sentinel", "strategy_id": "trend_momentum", "description": "x", "overrides": {}}]
    config_path = tmp_path / "research.yaml"
    config_path.write_text("research:\n  candidates: []\n", encoding="utf-8")
    calls = {}

    monkeypatch.setattr(cli, "load_candidate_specs", lambda path: sentinel_specs, raising=False)
    monkeypatch.setattr(
        cli,
        "run_research_governance_pipeline",
        lambda **kwargs: calls.update(kwargs) or {
            "research_result": {"report_paths": {}},
            "summary_result": {"output_paths": {}},
            "cycle_result": SimpleNamespace(
                decision=SimpleNamespace(id=1, review_status="ready", blocked_reasons=[])
            ),
            "pipeline_summary_path": "reports/governance/pipeline/2026-03-24.json",
            "exit_code": 0,
        },
    )

    assert cli.main(
        [
            "--start-date",
            "2025-12-01",
            "--end-date",
            "2026-03-24",
            "--candidate-config",
            str(config_path),
        ]
    ) == 0
    assert calls["candidate_specs"] is sentinel_specs
```

- [ ] **Step 2: 跑 wiring tests，确认当前 CLI 还没有切到共享 helper**

Run: `pytest tests/test_research_pipeline.py tests/test_research_governance_pipeline.py -q -k "uses_shared_candidate_specs_loader"`

Expected:
- FAIL
- 推荐失败形态：`candidate_specs` 不是 `sentinel_specs`

- [ ] **Step 3: 修改两个 CLI，删除本地 `_load_candidate_specs()` 并改用共享 helper**

在 `scripts/run_research.py` 与 `scripts/run_research_governance_pipeline.py` 中：

- 删除：
  - `yaml` 读取逻辑
  - `ResearchConfig` 导入
  - 本地 `_load_candidate_specs()`
- 新增：

```python
from src.research_candidate_config import load_candidate_specs
```

并把调用点统一改为：

```python
candidate_specs=load_candidate_specs(args.candidate_config)
```

要求：
- 不改 CLI 参数名
- 不改默认 `None` 语义
- 不改现有 stdout/stderr/exit code 语义

- [ ] **Step 4: 回跑 CLI wiring tests 与现有参数转发测试**

Run: `pytest tests/test_research_pipeline.py tests/test_research_governance_pipeline.py -q -k "candidate_specs or uses_shared_candidate_specs_loader or loads_candidate_config"`

Expected:
- PASS

- [ ] **Step 5: 提交 CLI 共享切换**

```bash
git add scripts/run_research.py scripts/run_research_governance_pipeline.py tests/test_research_pipeline.py tests/test_research_governance_pipeline.py
git commit -m "refactor: share candidate config loading across CLIs"
```

### Task 3: 新增 tests/support helper，并收敛 smoke/test 的配置写入与断言

**Files:**
- Create: `tests/support/__init__.py`
- Create: `tests/support/research_candidates.py`
- Modify: `tests/test_research_pipeline.py`
- Modify: `tests/test_research_governance_pipeline.py`
- Modify: `tests/test_research_governance_pipeline_cli_smoke.py`

- [ ] **Step 1: 先写失败测试/导入，锁定测试 support helper 的共享边界**

将三个测试文件改为使用：

```python
from tests.support.research_candidates import (
    ADVANCED_TEST_CANDIDATES,
    DEFAULT_TEST_CANDIDATES,
    assert_candidate_specs,
    expected_candidate_specs,
    write_candidate_config,
)
```

其中：
- `tests/test_research_pipeline.py`
  - 用 `write_candidate_config(...)` 替换内联 YAML
- `tests/test_research_governance_pipeline.py`
  - 用 `write_candidate_config(..., candidates=ADVANCED_TEST_CANDIDATES)`
  - 用 `assert_candidate_specs(...)` 或 `expected_candidate_specs(...)` 替换内联列表
- `tests/test_research_governance_pipeline_cli_smoke.py`
  - 删除本地 `_write_candidate_config(...)`
  - 在 smoke helper / test 中统一调用 `write_candidate_config(...)`
  - 在 stub 中用 `assert_candidate_specs(kwargs["candidate_specs"])` 锁定默认候选

- [ ] **Step 2: 跑相关测试，确认 tests/support helper 尚未实现**

Run: `pytest tests/test_research_pipeline.py tests/test_research_governance_pipeline.py tests/test_research_governance_pipeline_cli_smoke.py -q -k "candidate_config or smoke"`

Expected:
- FAIL
- 推荐失败形态：`ModuleNotFoundError: No module named 'tests.support'`

- [ ] **Step 3: 实现 tests/support helper，保持薄封装**

在 `tests/support/research_candidates.py` 中实现：

```python
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml

DEFAULT_TEST_CANDIDATES = [
    {
        "name": "baseline_trend",
        "strategy_id": "trend_momentum",
        "description": "baseline",
        "overrides": {},
    }
]

ADVANCED_TEST_CANDIDATES = [
    {
        "name": "baseline_trend",
        "strategy_id": "trend_momentum",
        "description": "baseline",
        "overrides": {},
    },
    {
        "name": "fast_turn",
        "strategy_id": "risk_adjusted_momentum",
        "description": "fast",
        "overrides": {
            "strategy_params": {
                "rebalance_frequency": "biweekly",
                "hold_count": 2,
            }
        },
    },
]


def write_candidate_config(path: Path, candidates=DEFAULT_TEST_CANDIDATES) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump({"research": {"candidates": list(candidates)}}, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return path


def expected_candidate_specs(candidates=DEFAULT_TEST_CANDIDATES) -> list[dict[str, Any]]:
    return deepcopy(list(candidates))


def assert_candidate_specs(actual, candidates=DEFAULT_TEST_CANDIDATES) -> None:
    assert actual == expected_candidate_specs(candidates)
```

要求：
- helper 只负责候选配置写入与期望值
- 不封装 artifact 断言
- `DEFAULT_TEST_CANDIDATES` 与 smoke 当前最小样例保持一致

- [ ] **Step 4: 回跑聚焦测试，确认 smoke/test 收敛后仍通过**

Run: `pytest tests/test_research_pipeline.py tests/test_research_governance_pipeline.py tests/test_research_governance_pipeline_cli_smoke.py -q`

Expected:
- PASS

- [ ] **Step 5: 提交测试 support helper 收敛**

```bash
git add tests/support/__init__.py tests/support/research_candidates.py tests/test_research_pipeline.py tests/test_research_governance_pipeline.py tests/test_research_governance_pipeline_cli_smoke.py
git commit -m "test: share candidate config fixtures across research flows"
```

### Task 4: 更新任务跟踪并完成最终聚焦回归

**Files:**
- Modify: `tasks/todo.md`
- Verify: `docs/superpowers/specs/2026-03-25-shared-candidate-config-helper-design.md`
- Verify: `docs/superpowers/plans/2026-03-25-shared-candidate-config-helper-implementation.md`

- [ ] **Step 1: 更新 `tasks/todo.md`，记录 B 子项目完成状态**

补充：
- spec / plan 路径
- Task 1/2/3 提交
- 关键验证命令与结果
- 下一步行动从 B 切换到后续端到端/文档工作

- [ ] **Step 2: 跑最终聚焦回归，确认文档更新前后的工作区状态一致**

Run: `pytest tests/test_research_pipeline.py tests/test_research_governance_pipeline.py tests/test_research_governance_pipeline_cli_smoke.py -q`

Expected:
- PASS

- [ ] **Step 3: 提交任务跟踪更新**

```bash
git add tasks/todo.md
git commit -m "docs: update shared candidate config helper status"
```

## 实施备注

- `run_research.py` 不要求改成 `main(argv)`；本轮只需通过 monkeypatch `_parse_args()` 锁定 wiring
- `run_research_governance_pipeline.py` 已有 CLI 契约测试，新增 wiring test 只补“确实走共享 helper”这一层
- `tests/support` 只收敛 candidate-config 相关样例与断言，避免把 smoke 逻辑过度抽象
- 最终实现完成后，按 `finishing-a-development-branch` 提供 4 个收尾选项
