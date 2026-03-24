# Phase 5 Regime-Aware Governance Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为治理周期增加 `regime-aware gate`，在单 ETF 实盘与人工发布流程不变的前提下，拦截当前市场状态下已被证明处于明确劣势 `regime` 的目标策略。

**Architecture:** 保持 `src/governance/evaluator.py` 只负责选出 `selected_strategy_id`，新增 `src/governance/regime_gate.py` 负责实时 `current_regime` 解析与门禁判定，再由 `src/governance/automation.py` 统一合并 `blocked_reasons` 与 `decision.evidence["regime_gate"]`。仓储层必须支持在复用同一 `summary_hash` draft 时刷新 review 结果与 evidence，否则实时 `regime` 变化会留下过期证据。

**Tech Stack:** Python 3、Pydantic、SQLAlchemy、pandas、pytest

**Status (2026-03-24):** 已完成
- Commits: `b1185a9`, `deb47d0`, `a371acc`, `3aee5a3`, `3659874`, `612c1e2`, `58c1d7d`, `c6c8ac9`
- Review: Task 4 的 spec compliance review 与 code quality review 均已通过
- Verify: `pytest tests/test_governance_repository.py tests/test_governance_regime_gate.py tests/test_governance_automation.py tests/test_governance_runtime.py -q` -> `35 passed`

---

## 文件边界

### Create

- `src/governance/regime_gate.py`
  - 定义 `RegimeGateResult`
  - 解析研究汇总里的候选 `regime` 证据
  - 实时重算 `current_regime`
  - 输出 `pass / blocked / skipped`
- `tests/test_governance_regime_gate.py`
  - 覆盖纯判定逻辑与实时 `regime` 解析注入点

### Modify

- `src/core/config.py`
  - 新增 `GovernanceRegimeGateConfig`
  - 将其挂到 `GovernanceAutomationConfig.regime_gate`
- `config/strategy.yaml`
  - 增加 `governance.automation.regime_gate` 默认配置
- `src/storage/repositories.py`
  - 扩展治理 draft review 更新接口，使其能同时刷新 `review_status`、`blocked_reasons`、`evidence`
- `tests/test_governance_repository.py`
  - 增加配置加载断言与 evidence 持久化断言
- `src/governance/automation.py`
  - 在 `evaluate_governance()` 之后接入 `regime gate`
  - 合并现有自动化阻断原因与 `regime gate` 阻断原因
  - 支持复用 draft 时刷新 `regime_gate` evidence
  - 为测试提供可注入的 `current_regime_snapshot` 或等价 seam
- `tests/test_governance_automation.py`
  - 增加 `blocked / skipped / pass` 集成场景
  - 增加 `keep / switch / fallback` 三类目标策略的门禁覆盖
  - 增加同一 `summary_hash` 二次运行刷新 evidence 的场景

### Verify Only

- `src/governance/publisher.py`
  - 预期无需修改；现有 `review_status == "ready"` 语义已足够承接 `regime gate`
- `scripts/run_governance_cycle.py`
  - 预期无需修改；当前已输出完整 `decision.model_dump()`
- `scripts/run_governance_review.py`
  - 预期无需修改；当前已输出完整 `decision.model_dump()`
- `tests/test_governance_runtime.py`
  - 预期无需改测试代码；作为发布语义回归验证

## 实施任务

### Task 1: 增加治理门禁配置与 review/evidence 持久化

**Files:**
- Modify: `src/core/config.py`
- Modify: `config/strategy.yaml`
- Modify: `src/storage/repositories.py`
- Test: `tests/test_governance_repository.py`

- [x] **Step 1: 先写失败测试，锁定配置与 evidence 刷新行为**

```python
def test_strategy_config_loads_governance_regime_gate_policy():
    strategy_config = ConfigLoader().load_strategy_config()

    assert strategy_config.governance.automation.regime_gate.enabled is True
    assert strategy_config.governance.automation.regime_gate.min_appearances == 2
    assert strategy_config.governance.automation.regime_gate.min_avg_observation_count == 20


def test_governance_repository_updates_review_status_and_evidence():
    reviewed = repo.set_review_status(
        draft.id,
        review_status="blocked",
        blocked_reasons=["SELECTED_STRATEGY_REGIME_MISMATCH"],
        evidence={"regime_gate": {"gate_status": "blocked"}},
    )

    assert reviewed.review_status == "blocked"
    assert reviewed.evidence["regime_gate"]["gate_status"] == "blocked"
```

- [x] **Step 2: 运行测试，确认当前代码缺少配置与 evidence 更新能力**

Run: `pytest tests/test_governance_repository.py -q`

Expected:
- FAIL，报错应落在 `GovernanceAutomationConfig` 缺少 `regime_gate`
- 或 `set_review_status()` 不接受 `evidence`

- [x] **Step 3: 以最小改动补齐配置模型与仓储更新接口**

```python
class GovernanceRegimeGateConfig(BaseModel):
    enabled: bool = True
    min_appearances: int = 2
    min_avg_observation_count: float = 20.0


class GovernanceAutomationConfig(BaseModel):
    enabled: bool = True
    require_fresh_summary: bool = True
    max_summary_age_days: int = 7
    min_reports_required: int = 3
    min_days_between_switches: int = 20
    block_on_open_incident: bool = True
    risk_breach_streak: int = 2
    regime_gate: GovernanceRegimeGateConfig = Field(default_factory=GovernanceRegimeGateConfig)


def set_review_status(
    self,
    decision_id: int,
    review_status: str,
    blocked_reasons: list[str],
    evidence: dict[str, Any] | None = None,
) -> GovernanceDecision:
    record = self.session.get(GovernanceDecisionRecord, decision_id)
    record.review_status = review_status
    record.blocked_reasons_json = _to_json_compatible(blocked_reasons)
    if evidence is not None:
        record.evidence_json = _to_json_compatible(evidence)
    self.session.commit()
    self.session.refresh(record)
    return _to_governance_decision(record)
```

- [x] **Step 4: 回跑仓储测试，确认配置与 evidence 可持久化**

Run: `pytest tests/test_governance_repository.py -q`

Expected:
- PASS

- [x] **Step 5: 提交这一层基础改动**

```bash
git add config/strategy.yaml src/core/config.py src/storage/repositories.py tests/test_governance_repository.py
git commit -m "feat: add governance regime gate config and review persistence"
```

### Task 2: 实现纯 `regime gate` 判定逻辑

**Files:**
- Create: `src/governance/regime_gate.py`
- Test: `tests/test_governance_regime_gate.py`

- [x] **Step 1: 先写失败测试，固定 `pass / blocked / skipped` 语义**

```python
def test_regime_gate_blocks_when_selected_strategy_is_in_proven_bad_regime():
    result = evaluate_regime_gate(
        summary=summary_with_candidate_regimes(),
        selected_strategy_id="trend_momentum",
        current_regime_snapshot=build_snapshot("risk_off"),
        gate_config=gate_config(),
    )

    assert result.gate_status == "blocked"
    assert result.blocked_reason == "SELECTED_STRATEGY_REGIME_MISMATCH"


def test_regime_gate_skips_when_current_regime_sample_is_insufficient():
    result = evaluate_regime_gate(
        summary=summary_with_single_risk_off_sample(),
        selected_strategy_id="trend_momentum",
        current_regime_snapshot=build_snapshot("risk_off"),
        gate_config=gate_config(),
    )

    assert result.gate_status == "skipped"
    assert result.skip_reason == "SELECTED_STRATEGY_REGIME_SAMPLE_INSUFFICIENT"


def test_regime_gate_passes_when_current_regime_is_not_the_worst_state():
    result = evaluate_regime_gate(
        summary=summary_with_candidate_regimes(),
        selected_strategy_id="trend_momentum",
        current_regime_snapshot=build_snapshot("risk_on"),
        gate_config=gate_config(),
    )

    assert result.gate_status == "pass"
    assert result.blocked_reason is None
```

- [x] **Step 2: 运行目标测试，确保还没有门禁实现**

Run: `pytest tests/test_governance_regime_gate.py -q`

Expected:
- FAIL，提示 `ModuleNotFoundError` 或 `evaluate_regime_gate` 未定义

- [x] **Step 3: 编写最小门禁实现，只做 summary 解析与弱/强证据判定**

```python
@dataclass
class RegimeGateResult:
    gate_status: Literal["pass", "blocked", "skipped"]
    blocked_reason: str | None
    skip_reason: str | None
    current_regime: dict[str, Any]
    current_regime_stats: dict[str, Any] | None
    worst_regime_stats: dict[str, Any] | None


def evaluate_regime_gate(summary, selected_strategy_id, current_regime_snapshot, gate_config):
    if current_regime_is_uncertain(current_regime_snapshot):
        return skipped("CURRENT_REGIME_UNCERTAIN")
    if current_stats_missing(summary, selected_strategy_id, current_regime_snapshot.regime_label):
        return skipped("SELECTED_STRATEGY_REGIME_STATS_MISSING")
    if current_stats_sample_insufficient(summary, selected_strategy_id, current_regime_snapshot.regime_label, gate_config):
        return skipped("SELECTED_STRATEGY_REGIME_SAMPLE_INSUFFICIENT")
    if comparison_rows_insufficient(summary, selected_strategy_id, gate_config):
        return skipped("SELECTED_STRATEGY_REGIME_COMPARISON_INSUFFICIENT")
    if is_proven_bad_regime(summary, selected_strategy_id, current_regime_snapshot.regime_label, gate_config):
        return blocked("SELECTED_STRATEGY_REGIME_MISMATCH")
    return passed(current_regime_snapshot)
```

- [x] **Step 4: 回跑纯门禁测试，确认三态输出闭合**

Run: `pytest tests/test_governance_regime_gate.py -q`

Expected:
- PASS

- [x] **Step 5: 提交纯判定层**

```bash
git add src/governance/regime_gate.py tests/test_governance_regime_gate.py
git commit -m "feat: add regime gate evaluation"
```

### Task 3: 为 `current_regime` 实时重算加入可测试注入点

**Files:**
- Modify: `src/governance/regime_gate.py`
- Test: `tests/test_governance_regime_gate.py`
- Reuse: `src/research/regime.py`
- Reuse: `src/data/fetcher.py`
- Reuse: `src/data/normalizer.py`
- Reuse: `src/core/config.py`

- [x] **Step 1: 先写失败测试，锁定实时 `regime` 解析与注入 seam**

```python
def test_resolve_current_regime_uses_injected_price_loader():
    snapshot = resolve_current_regime(
        as_of_date=date(2026, 3, 24),
        load_price_data=lambda *_: make_risk_off_price_data(),
        regime_config=ConfigLoader().load_research_config().regime,
        lookback_days=365,
    )

    assert snapshot.regime_label == "risk_off"


def test_evaluate_regime_gate_treats_uncertain_current_regime_as_skipped():
    result = evaluate_regime_gate(
        summary=summary_with_candidate_regimes(),
        selected_strategy_id="trend_momentum",
        current_regime_snapshot=build_snapshot(
            "neutral",
            reason_codes=["INSUFFICIENT_POOL_COVERAGE"],
        ),
        gate_config=gate_config(),
    )

    assert result.gate_status == "skipped"
    assert result.skip_reason == "CURRENT_REGIME_UNCERTAIN"
```

- [x] **Step 2: 运行目标测试，确认当前模块还不支持实时解析 seam**

Run: `pytest tests/test_governance_regime_gate.py -q`

Expected:
- FAIL，报错应落在 `resolve_current_regime` 未定义或签名不匹配

- [x] **Step 3: 实现默认实时重算路径，同时保留测试注入 seam**

```python
def resolve_current_regime(
    as_of_date: date,
    regime_config: ResearchRegimeConfig,
    load_price_data: Callable[..., dict[str, pd.DataFrame]] | None = None,
    lookback_days: int = 365,
) -> RegimeSnapshot | None:
    price_data = (load_price_data or _load_price_data_for_regime)(as_of_date, lookback_days)
    snapshots = RegimeClassifier(regime_config).classify(price_data)
    return snapshots[-1] if snapshots else None
```

实现要求：
- 默认加载路径使用 ETF 池 `enabled=true` 标的
- lookback 至少覆盖 120/60/20 日特征窗口
- 复用 `DataFetcher` + `DataNormalizer`
- 不把网络依赖带进测试；测试只能走注入 loader

- [x] **Step 4: 回跑门禁测试，确认实时解析路径可测**

Run: `pytest tests/test_governance_regime_gate.py -q`

Expected:
- PASS

- [x] **Step 5: 提交实时解析层**

```bash
git add src/governance/regime_gate.py tests/test_governance_regime_gate.py
git commit -m "feat: resolve current regime for governance gate"
```

### Task 4: 将 `regime gate` 接入治理自动化并处理 draft 复用

**Files:**
- Modify: `src/governance/automation.py`
- Modify: `tests/test_governance_automation.py`
- Verify: `tests/test_governance_runtime.py`

- [x] **Step 1: 先写失败的自动化测试，覆盖阻断、跳过、draft 复用刷新**

```python
def test_run_governance_cycle_blocks_selected_strategy_on_regime_mismatch(tmp_path):
    result = run_governance_cycle(
        summary_path=summary_path,
        policy=GovernanceConfig(),
        repo=repo,
        current_strategy_id="trend_momentum",
        current_regime_snapshot=build_snapshot("risk_off"),
    )

    assert result.decision.review_status == "blocked"
    assert "SELECTED_STRATEGY_REGIME_MISMATCH" in result.decision.blocked_reasons
    assert result.decision.evidence["regime_gate"]["gate_status"] == "blocked"


def test_run_governance_cycle_refreshes_regime_gate_evidence_for_same_summary(tmp_path):
    first = run_governance_cycle(
        summary_path=summary_path,
        policy=GovernanceConfig(),
        repo=repo,
        current_strategy_id="trend_momentum",
        current_regime_snapshot=build_snapshot("risk_on"),
    )
    second = run_governance_cycle(
        summary_path=summary_path,
        policy=GovernanceConfig(),
        repo=repo,
        current_strategy_id="trend_momentum",
        current_regime_snapshot=build_snapshot("risk_off"),
    )

    assert first.decision.id == second.decision.id
    assert second.decision.evidence["regime_gate"]["current_regime"]["regime_label"] == "risk_off"


def test_run_governance_cycle_applies_gate_to_keep_and_fallback_targets(tmp_path):
    keep_result = run_governance_cycle(
        summary_path=keep_summary_path,
        policy=GovernanceConfig(),
        repo=repo,
        current_strategy_id="trend_momentum",
        current_regime_snapshot=build_snapshot("risk_off"),
    )
    fallback_result = run_governance_cycle(
        summary_path=fallback_summary_path,
        policy=GovernanceConfig(),
        repo=repo,
        current_strategy_id="retired_strategy",
        current_regime_snapshot=build_snapshot("risk_off"),
    )

    assert keep_result.decision.selected_strategy_id == "trend_momentum"
    assert fallback_result.decision.decision_type == "fallback"
```

- [x] **Step 2: 运行自动化测试，确认当前治理流程尚未接入门禁**

Run: `pytest tests/test_governance_automation.py -q`

Expected:
- FAIL，缺少 `current_regime_snapshot` 注入点
- 或 `blocked_reasons` / `evidence["regime_gate"]` 不符合预期

- [x] **Step 3: 在自动化层接入门禁，并让复用 draft 时也刷新 evidence**

```python
def run_governance_cycle(
    summary_path,
    repo,
    policy,
    current_strategy_id,
    current_regime_snapshot: RegimeSnapshot | None = None,
):
    summary = _load_summary(summary_path)
    gate_result = evaluate_regime_gate(
        summary=summary,
        selected_strategy_id=result.decision.selected_strategy_id,
        current_regime_snapshot=current_regime_snapshot or resolve_current_regime(
            as_of_date=date.today(),
            regime_config=config_loader.load_research_config().regime,
        ),
        gate_config=policy.automation.regime_gate,
    )
    evidence = {**result.decision.evidence, "regime_gate": gate_result.to_evidence()}
    blocked_reasons = existing_reasons + gate_result.blocked_reasons()
    reviewed = repo.set_review_status(
        result.decision.id,
        review_status="blocked" if blocked_reasons else "ready",
        blocked_reasons=blocked_reasons,
        evidence=evidence,
    )
```

实现要求：
- `keep / switch / fallback` 全部走同一门禁逻辑
- 只在 `gate_status == "blocked"` 时追加 `SELECTED_STRATEGY_REGIME_MISMATCH`
- `gate_status == "skipped"` 时只写 evidence，不新增 `blocked_reasons`
- 同一 `summary_hash` 二次运行时，必须刷新最新 `regime_gate` evidence

- [x] **Step 4: 回跑自动化与发布语义回归测试**

Run: `pytest tests/test_governance_automation.py tests/test_governance_runtime.py -q`

Expected:
- PASS
- `tests/test_governance_runtime.py` 不需要改断言就通过，说明发布语义未被破坏

- [x] **Step 5: 提交自动化集成层**

```bash
git add src/governance/automation.py tests/test_governance_automation.py
git commit -m "feat: integrate regime gate into governance automation"
```

### Task 5: 做聚焦回归并更新项目任务跟踪

**Files:**
- Modify: `tasks/todo.md`
- Verify: `tests/test_governance_repository.py`
- Verify: `tests/test_governance_regime_gate.py`
- Verify: `tests/test_governance_automation.py`
- Verify: `tests/test_governance_runtime.py`

- [x] **Step 1: 在 `tasks/todo.md` 中新增 Phase 5 执行清单**

```md
## 2026-03-24 Phase 5 治理状态门禁
- [ ] 配置与仓储刷新
- [ ] 纯门禁判定
- [ ] 当前 regime 实时重算
- [ ] 自动化集成与 draft 复用刷新
- [ ] 聚焦回归验证
```

- [x] **Step 2: 运行 Phase 5 相关测试集**

Run: `pytest tests/test_governance_repository.py tests/test_governance_regime_gate.py tests/test_governance_automation.py tests/test_governance_runtime.py -q`

Expected:
- PASS

- [x] **Step 3: 将验证结果与 review 结论写回 `tasks/todo.md`**

```md
### 验证结果
- `pytest tests/test_governance_repository.py tests/test_governance_regime_gate.py tests/test_governance_automation.py tests/test_governance_runtime.py -q` 通过
- `regime gate` 在 blocked/skipped/pass 三种状态下行为符合 spec
```

- [x] **Step 4: 检查工作区，只保留本阶段应有文件**

Run: `git status --short`

Expected:
- 只出现本任务涉及文件；无意外改动

- [x] **Step 5: 提交收尾文档与跟踪更新**

```bash
git add tasks/todo.md
git commit -m "docs: track phase 5 governance gate implementation"
```

## 实施备注

- 本计划默认不修改 `src/governance/publisher.py`，因为它已经通过 `review_status` 承接硬门禁
- 本计划默认不修改 CLI 脚本输出逻辑；一旦 `decision.evidence["regime_gate"]` 正确持久化，现有 `model_dump()` 即会带出门禁证据
- 若实现时发现实时行情拉取与主流程重复逻辑过多，可在不扩大范围的前提下抽一个极小共享 helper，但不要把本阶段扩成数据层重构
