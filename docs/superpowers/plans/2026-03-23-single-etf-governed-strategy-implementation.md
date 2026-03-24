# 单ETF治理化升级 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持生产端“单一ETF或空仓”约束不变的前提下，先完成交易语义统一、测试隔离、特征/候选策略抽象和首个新增候选策略落地，使研究结果能够可信地迁移到生产流程。

**Architecture:** 第一批不实现完整治理层切换，只先搭好统一交易语义与候选策略框架。生产端先固定激活 `TrendMomentumStrategy`，研究端同时比较 `TrendMomentumStrategy` 和 `RiskAdjustedMomentumStrategy`，并用统一的 schedule / simulator / proposal 接口驱动研究与生产。

**Tech Stack:** Python 3.10+, pandas, numpy, SQLAlchemy 2.x, pydantic 2.x, pytest, YAML 配置

**Implementation Status (2026-03-24):** Task 1-7 已全部完成，当前工作区已通过 `pytest -q` 与 `python3 -m compileall src scripts tests` 验证。

---

> 说明：
> 1. 当前工作目录不是 Git 仓库根目录，以下 `git commit` 步骤仅在后续接入 Git 根目录后执行。
> 2. 本计划对应 spec：`docs/superpowers/specs/2026-03-23-single-etf-governed-strategy-design.md`

## File Structure

### Create

- `tests/test_database_isolation.py`
  验证测试数据库与默认业务库隔离。
- `tests/test_rebalance_policy.py`
  验证调仓信号日、执行日与非调仓日行为。
- `tests/test_execution_simulator.py`
  验证统一成交模型、整手约束、卖后买失败回退现金等规则。
- `tests/test_strategy_features.py`
  验证特征快照计算逻辑。
- `tests/test_candidate_trend_momentum.py`
  验证升级后的基线候选策略输出。
- `tests/test_candidate_risk_adjusted_momentum.py`
  验证风险调整动量候选策略输出。
- `tests/conftest.py`
  统一测试数据库、临时目录和环境初始化。
- `src/execution/trade_policy.py`
  统一交易语义配置对象。
- `src/execution/schedule.py`
  调仓信号日 / 执行日服务。
- `src/execution/simulator.py`
  统一成交模拟与结果对象。
- `src/strategy/features.py`
  特征快照对象与特征计算函数。
- `src/strategy/proposal.py`
  候选策略统一输出结构。
- `src/strategy/candidates/__init__.py`
  候选策略包入口。
- `src/strategy/candidates/base.py`
  候选策略基类接口。
- `src/strategy/candidates/trend_momentum.py`
  基线候选策略。
- `src/strategy/candidates/risk_adjusted_momentum.py`
  风险调整动量候选策略。
- `src/strategy/registry.py`
  候选策略注册表。

### Modify

- `src/storage/database.py`
  支持测试数据库隔离与 engine/session 重建。
- `src/core/config.py`
  增加交易语义配置、生产策略选择、研究候选策略类型定义。
- `config/strategy.yaml`
  增加 `trade_policy` 和 `production_strategy_id`。
- `config/research.yaml`
  从“参数覆盖列表”升级为“候选策略 + 覆盖参数”。
- `src/data/calendar.py`
  只保留交易日历职责，调仓计划下沉到 schedule service。
- `src/execution/checker.py`
  改为复用 `TradePolicy` 和 `ExecutionSimulator`。
- `src/execution/executor.py`
  改为复用统一成交模拟结果。
- `src/backtest/engine.py`
  复用 `TradePolicy`、`RebalanceScheduleService`、`ExecutionSimulator`。
- `src/main.py`
  复用统一调仓计划、候选策略接口和生产策略配置。
- `src/strategy/__init__.py`
  导出新对象。
- `src/agents/report.py`
  报告里展示 active strategy / proposal reason。
- `src/research_pipeline.py`
  从参数比较升级为候选策略研究。
- `scripts/run_research.py`
  加载候选策略配置。
- `src/research_summary.py`
  适配新的研究结果结构。
- `src/report_portal.py`
  展示激活策略与候选策略结果。
- `README.md`
  更新研究/生产语义与执行说明。
- `requirements.txt`
  收紧 pandas/numpy 版本约束，保证测试环境可复现。
- `pyproject.toml`
  同步依赖约束与测试配置说明。
- `tests/test_pipeline_e2e.py`
  迁移到隔离测试库并验证新生产流程输出。
- `tests/test_regressions.py`
  迁移到新服务与回归点。
- `tests/test_research_pipeline.py`
  迁移到候选策略研究流。
- `tests/test_research_summary.py`
  适配新研究输出结构。
- `tests/test_report_portal.py`
  适配 active strategy 与候选展示。

## Task 1: 稳定测试环境与数据库隔离

**Files:**
- Create: `tests/test_database_isolation.py`
- Create: `tests/conftest.py`
- Modify: `src/storage/database.py`
- Modify: `requirements.txt`
- Modify: `pyproject.toml`
- Modify: `tests/test_pipeline_e2e.py`
- Modify: `tests/test_regressions.py`
- Modify: `tests/test_research_pipeline.py`
- Test: `tests/test_database_isolation.py`

- [x] **Step 1: 写出失败测试，证明测试不会写入默认业务库**

```python
def test_sessionlocal_uses_temp_database(tmp_path, monkeypatch):
    monkeypatch.setenv("ETF_AI_TEST_DB", f"sqlite:///{tmp_path / 'test.db'}")
    db = reload_database_module()
    db.init_db()
    assert db.DATABASE_URL.endswith("test.db")
```

- [x] **Step 2: 运行测试确认当前实现不满足该约束**

Run: `pytest -q tests/test_database_isolation.py`
Expected: FAIL，当前 `src/storage/database.py` 在导入时固定了默认库地址

- [x] **Step 3: 实现数据库工厂与测试隔离入口**

```python
def get_database_url() -> str:
    return os.getenv("ETF_AI_TEST_DB") or config_loader.load_settings().database_url

def reset_engine(database_url: str | None = None) -> None:
    ...
```

要求：
- `SessionLocal` 不再只依赖导入时静态 URL
- `tests/conftest.py` 在 session 级别注入临时 SQLite
- 现有测试不再直接操作默认 `data/db/etf_rotation.db`

- [x] **Step 4: 收紧依赖版本，修复 pandas/numpy ABI 漂移**

```toml
dependencies = [
    "numpy>=1.24,<2.0",
    "pandas>=2.0,<2.3",
]
```

要求：
- `requirements.txt` 和 `pyproject.toml` 保持一致
- 只做首批必要收紧，不新增复杂锁文件

- [x] **Step 5: 重新运行隔离测试**

Run: `pytest -q tests/test_database_isolation.py tests/test_pipeline_e2e.py`
Expected: PASS，测试数据库路径为临时文件，且不依赖默认业务库

- [x] **Step 6: 提交（当前目录非 Git 仓库，按计划说明未执行 commit）**

```bash
git add tests/test_database_isolation.py tests/conftest.py src/storage/database.py requirements.txt pyproject.toml tests/test_pipeline_e2e.py tests/test_regressions.py tests/test_research_pipeline.py
git commit -m "test: isolate sqlite database for test runs"
```

## Task 2: 引入统一交易语义配置与调仓计划服务

**Files:**
- Create: `src/execution/trade_policy.py`
- Create: `src/execution/schedule.py`
- Create: `tests/test_rebalance_policy.py`
- Modify: `src/core/config.py`
- Modify: `config/strategy.yaml`
- Modify: `src/data/calendar.py`
- Test: `tests/test_rebalance_policy.py`

- [x] **Step 1: 写失败测试，锁定月末信号/次日执行语义**

```python
def test_monthly_schedule_generates_signal_and_next_execution():
    schedule = RebalanceScheduleService(calendar, policy)
    dates = schedule.build_plan(date(2026, 3, 1), date(2026, 3, 31))
    assert dates[0].signal_date == date(2026, 3, 31)
    assert dates[0].execution_date == date(2026, 4, 1)
```

- [x] **Step 2: 运行测试，确认当前代码缺少统一 schedule service**

Run: `pytest -q tests/test_rebalance_policy.py`
Expected: FAIL with `ImportError` or missing service assertions

- [x] **Step 3: 新增 `TradePolicy` 和 `RebalanceScheduleService`**

```python
class TradePolicy(BaseModel):
    rebalance_frequency: Literal["monthly", "biweekly"]
    execution_delay_trading_days: int = 1
    lot_size: int = 100
    fee_rate: float = 0.001
```

```python
class RebalanceEvent(BaseModel):
    signal_date: date
    execution_date: date
```

要求：
- `config/strategy.yaml` 新增 `trade_policy`
- `config_loader` 能加载 `production_strategy_id`
- `src/data/calendar.py` 不再承担调仓业务规则

- [x] **Step 4: 补充非调仓日只允许 HOLD 的接口**

```python
assert service.is_signal_day(date(2026, 3, 30)) is False
assert service.is_execution_day(date(2026, 4, 1)) is True
```

- [x] **Step 5: 运行测试并确认通过**

Run: `pytest -q tests/test_rebalance_policy.py tests/test_regressions.py::test_biweekly_rebalance_uses_last_trading_day_before_15th`
Expected: PASS

- [x] **Step 6: 提交（当前目录非 Git 仓库，按计划说明未执行 commit）**

```bash
git add src/execution/trade_policy.py src/execution/schedule.py tests/test_rebalance_policy.py src/core/config.py config/strategy.yaml src/data/calendar.py
git commit -m "feat: add unified trade policy and rebalance schedule"
```

## Task 3: 抽出统一成交模拟器并让研究/生产共用

**Files:**
- Create: `src/execution/simulator.py`
- Create: `tests/test_execution_simulator.py`
- Modify: `src/execution/checker.py`
- Modify: `src/execution/executor.py`
- Modify: `src/backtest/engine.py`
- Modify: `src/main.py`
- Test: `tests/test_execution.py`
- Test: `tests/test_execution_simulator.py`
- Test: `tests/test_regressions.py`

- [x] **Step 1: 写失败测试，锁定整手、费用、卖后买失败回退现金**

```python
def test_simulator_returns_cash_when_sell_succeeds_but_buy_fails():
    result = simulator.rebalance(...)
    assert result.final_state.holding_symbol is None
    assert result.final_state.cash > 0
```

- [x] **Step 2: 运行测试，确认当前回测与执行不共用语义**

Run: `pytest -q tests/test_execution_simulator.py tests/test_execution.py`
Expected: FAIL，当前没有 `ExecutionSimulator`

- [x] **Step 3: 实现统一模拟器与结果对象**

```python
class SimulatedFill(BaseModel):
    action: str
    filled_shares: int
    fill_price: float | None
    cash_after: float
    holding_symbol: str | None
```

要求：
- 下单前估算与实际成交都通过 simulator
- `OrderChecker` 只负责组装请求与解释失败原因
- `RebalanceExecutor` 不再重复实现买卖数学
- `SimpleBacktestEngine` 在调仓日调用同一 simulator

- [x] **Step 4: 用 simulator 替换回测里的分数股逻辑**

```python
fill = simulator.rebalance(current_state, target_symbol=target, trade_date=today)
cash = fill.cash_after
holdings = fill.to_holdings_dict()
```

- [x] **Step 5: 运行回归测试**

Run: `pytest -q tests/test_execution.py tests/test_execution_simulator.py tests/test_regressions.py`
Expected: PASS，且已有“0 股成交”回归测试仍为绿色

- [x] **Step 6: 提交（当前目录非 Git 仓库，按计划说明未执行 commit）**

```bash
git add src/execution/simulator.py tests/test_execution_simulator.py src/execution/checker.py src/execution/executor.py src/backtest/engine.py src/main.py tests/test_execution.py tests/test_regressions.py
git commit -m "refactor: unify execution semantics across backtest and production"
```

## Task 4: 建立特征快照与候选策略统一输出结构

**Files:**
- Create: `src/strategy/features.py`
- Create: `src/strategy/proposal.py`
- Create: `src/strategy/candidates/__init__.py`
- Create: `src/strategy/candidates/base.py`
- Create: `tests/test_strategy_features.py`
- Modify: `src/strategy/__init__.py`
- Test: `tests/test_strategy_features.py`

- [x] **Step 1: 写失败测试，锁定 `FeatureSnapshot` 结构**

```python
def test_build_feature_snapshot_returns_expected_metrics():
    snapshot = build_feature_snapshot(price_data, benchmark_data)
    assert snapshot.by_symbol["510500"].momentum_60 > 0
    assert "volatility_20" in snapshot.by_symbol["510500"].model_dump()
```

- [x] **Step 2: 运行测试，确认新对象尚不存在**

Run: `pytest -q tests/test_strategy_features.py`
Expected: FAIL with `ImportError`

- [x] **Step 3: 实现特征对象与构建函数**

```python
class SymbolFeatures(BaseModel):
    momentum_20: float | None = None
    momentum_60: float | None = None
    momentum_120: float | None = None
    ma_distance_120: float | None = None
    volatility_20: float | None = None
```

```python
class FeatureSnapshot(BaseModel):
    trade_date: date
    by_symbol: dict[str, SymbolFeatures]
```

- [x] **Step 4: 实现 `StrategyProposal` 与候选策略基类**

```python
class StrategyProposal(BaseModel):
    strategy_id: str
    trade_date: date
    target_etf: str | None
    score: float
    confidence: float
    risk_flags: list[str] = []
    reason_codes: list[str] = []
```

- [x] **Step 5: 运行测试并确认通过**

Run: `pytest -q tests/test_strategy_features.py`
Expected: PASS

- [x] **Step 6: 提交（当前目录非 Git 仓库，按计划说明未执行 commit）**

```bash
git add src/strategy/features.py src/strategy/proposal.py src/strategy/candidates/__init__.py src/strategy/candidates/base.py tests/test_strategy_features.py src/strategy/__init__.py
git commit -m "feat: add feature snapshot and proposal abstractions"
```

## Task 5: 把现有基线重构为 `TrendMomentumStrategy`

**Files:**
- Create: `src/strategy/candidates/trend_momentum.py`
- Create: `tests/test_candidate_trend_momentum.py`
- Modify: `src/main.py`
- Modify: `src/agents/report.py`
- Modify: `src/core/config.py`
- Modify: `config/strategy.yaml`
- Test: `tests/test_candidate_trend_momentum.py`
- Test: `tests/test_pipeline_e2e.py`

- [x] **Step 1: 写失败测试，锁定候选策略输出单一 ETF proposal**

```python
def test_trend_momentum_strategy_selects_highest_trending_symbol():
    proposal = strategy.generate(snapshot, current_position=None)
    assert proposal.target_etf == "510500"
    assert proposal.strategy_id == "trend_momentum"
```

- [x] **Step 2: 运行测试，确认基线策略仍耦合在旧 `StrategyEngine`**

Run: `pytest -q tests/test_candidate_trend_momentum.py`
Expected: FAIL

- [x] **Step 3: 实现 `TrendMomentumStrategy`**

```python
class TrendMomentumStrategy(BaseCandidateStrategy):
    strategy_id = "trend_momentum"

    def generate(...)-> StrategyProposal:
        ...
```

要求：
- 尽量复用现有动量/趋势逻辑
- 输出 `reason_codes`
- 生产端读取 `production_strategy_id`，先固定为 `trend_momentum`

- [x] **Step 4: 让 `src/main.py` 通过候选策略接口生成生产 proposal**

```python
active_strategy = build_candidate_strategy(config.production_strategy_id, ...)
proposal = active_strategy.generate(snapshot, current_position=current_position)
```

- [x] **Step 5: 报告中展示 active strategy 与 proposal 原因**

```python
ReportInput(
    ...,
    data={"active_strategy_id": proposal.strategy_id, "reason_codes": proposal.reason_codes},
)
```

- [x] **Step 6: 运行生产相关测试**

Run: `pytest -q tests/test_candidate_trend_momentum.py tests/test_pipeline_e2e.py`
Expected: PASS，日报内容包含 active strategy 信息

- [x] **Step 7: 提交（当前目录非 Git 仓库，按计划说明未执行 commit）**

```bash
git add src/strategy/candidates/trend_momentum.py tests/test_candidate_trend_momentum.py src/main.py src/agents/report.py src/core/config.py config/strategy.yaml
git commit -m "refactor: route production through trend momentum candidate strategy"
```

## Task 6: 新增 `RiskAdjustedMomentumStrategy` 与研究候选注册表

**Files:**
- Create: `src/strategy/candidates/risk_adjusted_momentum.py`
- Create: `src/strategy/registry.py`
- Create: `tests/test_candidate_risk_adjusted_momentum.py`
- Modify: `config/research.yaml`
- Modify: `src/core/config.py`
- Modify: `scripts/run_research.py`
- Modify: `src/research_pipeline.py`
- Modify: `tests/test_research_pipeline.py`
- Test: `tests/test_candidate_risk_adjusted_momentum.py`
- Test: `tests/test_research_pipeline.py`

- [x] **Step 1: 写失败测试，锁定风险调整策略会惩罚高波动标的**

```python
def test_risk_adjusted_strategy_penalizes_high_vol_symbol():
    proposal = strategy.generate(snapshot, current_position=None)
    assert proposal.target_etf == "515180"
```

- [x] **Step 2: 运行测试，确认新策略与 registry 尚不存在**

Run: `pytest -q tests/test_candidate_risk_adjusted_momentum.py`
Expected: FAIL

- [x] **Step 3: 实现候选注册表与风险调整策略**

```python
STRATEGY_REGISTRY = {
    "trend_momentum": TrendMomentumStrategy,
    "risk_adjusted_momentum": RiskAdjustedMomentumStrategy,
}
```

要求：
- `config/research.yaml` 的每个 candidate 明确包含 `strategy_id`
- `scripts/run_research.py` 能读取 `strategy_id + overrides`
- `run_research_pipeline()` 按 registry 实例化策略，而不是只做参数覆盖

- [x] **Step 4: 输出新的研究结果结构**

```python
comparison_rows.append(
    {
        "candidate_name": spec["name"],
        "strategy_id": spec["strategy_id"],
        "target_etf_counts": ...,
        ...
    }
)
```

- [x] **Step 5: 运行研究流测试**

Run: `pytest -q tests/test_candidate_risk_adjusted_momentum.py tests/test_research_pipeline.py`
Expected: PASS，研究报告同时包含两个候选策略结果

- [x] **Step 6: 提交（当前目录非 Git 仓库，按计划说明未执行 commit）**

```bash
git add src/strategy/candidates/risk_adjusted_momentum.py src/strategy/registry.py tests/test_candidate_risk_adjusted_momentum.py config/research.yaml src/core/config.py scripts/run_research.py src/research_pipeline.py tests/test_research_pipeline.py
git commit -m "feat: add risk adjusted momentum candidate research flow"
```

## Task 7: 升级研究摘要、门户与文档，并做全量验证

**Files:**
- Modify: `src/research_summary.py`
- Modify: `src/report_portal.py`
- Modify: `README.md`
- Modify: `tests/test_research_summary.py`
- Modify: `tests/test_report_portal.py`
- Test: `tests/test_research_summary.py`
- Test: `tests/test_report_portal.py`

- [x] **Step 1: 写失败测试，锁定门户/摘要展示 active strategy 与 strategy_id**

```python
assert result["candidate_leaderboard"][0]["strategy_id"] == "risk_adjusted_momentum"
assert "trend_momentum" in html_content
```

- [x] **Step 2: 运行测试确认现有结构不包含新字段**

Run: `pytest -q tests/test_research_summary.py tests/test_report_portal.py`
Expected: FAIL

- [x] **Step 3: 更新摘要与门户结构**

要求：
- 研究摘要显示 `candidate_name`、`strategy_id`
- 门户显示生产端 active strategy
- README 明确：
  - 生产只持有单一ETF
  - 研究端可以并行比较多个候选策略
  - 调仓采用“月末信号、次日执行”

- [x] **Step 4: 运行完整验证**

Run: `pytest -q`
Expected: PASS

Run: `python3 -m compileall src scripts tests`
Expected: PASS

- [x] **Step 5: 提交（当前目录非 Git 仓库，按计划说明未执行 commit）**

```bash
git add src/research_summary.py src/report_portal.py README.md tests/test_research_summary.py tests/test_report_portal.py
git commit -m "docs: surface candidate strategy metadata in reports and portal"
```

## Final Verification Checklist

- [x] `tests/test_database_isolation.py` 通过
- [x] `tests/test_rebalance_policy.py` 通过
- [x] `tests/test_execution_simulator.py` 通过
- [x] `tests/test_strategy_features.py` 通过
- [x] `tests/test_candidate_trend_momentum.py` 通过
- [x] `tests/test_candidate_risk_adjusted_momentum.py` 通过
- [x] `pytest -q` 全量通过
- [x] `python3 -m compileall src scripts tests` 通过
- [x] 生产端输出仍严格限制为“单一ETF或空仓”
- [x] 研究端能同时比较至少两个候选策略
