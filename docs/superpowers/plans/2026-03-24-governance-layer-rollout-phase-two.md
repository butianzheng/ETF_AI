# 第二阶段治理层落地 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持生产端“单一 ETF 或空仓”约束不变的前提下，把研究赢家评估、人工审批、发布生效、回退恢复正式接入生产闭环。

**Architecture:** 新增独立 `governance` 域，不把治理规则散落在研究或生产主流程里。研究汇总结果先进入治理评估器生成 `draft decision`，审批/发布状态持久化到 SQLite，生产侧仅消费“最新已发布策略”，若无有效发布记录则回退到 `config/strategy.yaml` 的默认 `production_strategy_id`。

**Tech Stack:** Python 3.10+, pandas, SQLAlchemy 2.x, pydantic 2.x, pytest, YAML, SQLite

---

> 说明：
> 1. 本计划以上一轮设计 spec `docs/superpowers/specs/2026-03-23-single-etf-governed-strategy-design.md` 第 7 节与第 10 节为输入。
> 2. 本轮不新增更多候选策略，先只治理现有 `trend_momentum` / `risk_adjusted_momentum`。
> 3. 发布切换默认要求人工审批，不在本轮引入自动发布。

## File Structure

### Create

- `src/governance/__init__.py`
  治理域对外导出。
- `src/governance/models.py`
  定义 `GovernanceDecision`、`GovernancePolicy`、`GovernanceReviewInput` 等领域对象。
- `src/governance/evaluator.py`
  基于研究汇总结果计算治理评分并生成 draft decision。
- `src/governance/runtime.py`
  生产侧读取“最新已发布策略”的运行时解析逻辑。
- `src/governance/publisher.py`
  审批、发布、回退服务。
- `scripts/run_governance_review.py`
  从研究汇总产物生成治理 draft。
- `scripts/publish_governance_decision.py`
  将 draft 决策审批并发布到生产。
- `scripts/rollback_governance_decision.py`
  将生产策略回退到上一个已发布策略或 fallback。
- `tests/test_governance_models.py`
  验证治理配置与领域对象。
- `tests/test_governance_repository.py`
  验证治理决策落库、审批、发布、回退。
- `tests/test_governance_evaluator.py`
  验证 champion/challenger/fallback 规则。
- `tests/test_governance_runtime.py`
  验证生产侧策略解析逻辑。

### Modify

- `src/core/config.py`
  增加治理配置模型与加载逻辑。
- `config/strategy.yaml`
  增加 `governance` 配置段。
- `src/storage/models.py`
  增加治理决策表。
- `src/storage/repositories.py`
  增加 `GovernanceRepository`。
- `src/main.py`
  生产端改为优先读取“最新已发布治理策略”。
- `src/report_portal.py`
  统一门户展示 active strategy、最近治理决策、待发布 draft。
- `README.md`
  增加治理评审/发布/回退命令说明。
- `tasks/todo.md`
  记录本轮计划与结果。
- `tests/test_pipeline_e2e.py`
  端到端验证发布后生产端切换策略。
- `tests/test_report_portal.py`
  验证门户展示治理信息。

## Task 1: 建立治理配置与领域模型

**Files:**
- Create: `src/governance/__init__.py`
- Create: `src/governance/models.py`
- Create: `tests/test_governance_models.py`
- Modify: `src/core/config.py`
- Modify: `config/strategy.yaml`
- Test: `tests/test_governance_models.py`

- [ ] **Step 1: 写失败测试，锁定治理配置能从 strategy.yaml 正确加载**

```python
def test_strategy_config_loads_governance_policy():
    strategy_config = config_loader.load_strategy_config()
    assert strategy_config.governance.enabled is True
    assert strategy_config.governance.manual_approval_required is True
    assert strategy_config.governance.fallback_strategy_id == "trend_momentum"
```

- [ ] **Step 2: 运行测试确认当前尚无治理配置模型**

Run: `pytest -q tests/test_governance_models.py`
Expected: FAIL，`StrategyConfig` 缺少 `governance` 字段

- [ ] **Step 3: 实现最小治理配置与领域对象**

```python
class GovernanceConfig(BaseModel):
    enabled: bool = True
    manual_approval_required: bool = True
    champion_min_appearances: int = 3
    challenger_min_top1: int = 2
    challenger_min_score_margin: float = 0.05
    champion_max_drawdown_penalty: float = 0.12
    fallback_strategy_id: str = "trend_momentum"
```

```python
class GovernanceDecision(BaseModel):
    decision_date: date
    current_strategy_id: str | None
    selected_strategy_id: str
    fallback_strategy_id: str
    decision_type: Literal["keep", "switch", "fallback"]
    status: Literal["draft", "approved", "published", "rolled_back"]
    reason_codes: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
```

要求：
- 治理配置挂在 `StrategyConfig` 下，避免再引入第二份全局 YAML
- 默认 fallback 先指向 `trend_momentum`，不在本轮新建防御策略
- 领域对象与 ORM 解耦，先走 pydantic + repository 映射

- [ ] **Step 4: 在 `config/strategy.yaml` 增加治理配置段**

```yaml
governance:
  enabled: true
  manual_approval_required: true
  champion_min_appearances: 3
  challenger_min_top1: 2
  challenger_min_score_margin: 0.05
  champion_max_drawdown_penalty: 0.12
  fallback_strategy_id: trend_momentum
```

- [ ] **Step 5: 运行模型测试确认通过**

Run: `pytest -q tests/test_governance_models.py`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add src/governance/__init__.py src/governance/models.py tests/test_governance_models.py src/core/config.py config/strategy.yaml
git commit -m "feat: add governance domain models and config"
```

## Task 2: 增加治理决策持久化与状态流转

**Files:**
- Create: `tests/test_governance_repository.py`
- Modify: `src/storage/models.py`
- Modify: `src/storage/repositories.py`
- Test: `tests/test_governance_repository.py`

- [ ] **Step 1: 写失败测试，锁定 draft/approved/published/rolled_back 生命周期**

```python
def test_governance_repository_tracks_publish_and_rollback():
    repo = GovernanceRepository()
    decision = repo.save_draft(...)
    repo.approve(decision.id, approved_by="tester")
    repo.publish(decision.id)
    assert repo.get_latest_published().selected_strategy_id == "risk_adjusted_momentum"
```

- [ ] **Step 2: 运行测试确认当前没有治理仓储**

Run: `pytest -q tests/test_governance_repository.py`
Expected: FAIL with `ImportError` or missing repository/table

- [ ] **Step 3: 在 ORM 中新增治理决策表**

```python
class GovernanceDecisionRecord(Base):
    __tablename__ = "governance_decision"
    id = Column(Integer, primary_key=True, autoincrement=True)
    decision_date = Column(Date, index=True, nullable=False)
    decision_type = Column(String, nullable=False)
    status = Column(String, nullable=False)
    current_strategy_id = Column(String, nullable=True)
    selected_strategy_id = Column(String, nullable=False)
    previous_strategy_id = Column(String, nullable=True)
    fallback_strategy_id = Column(String, nullable=False)
    approved_by = Column(String, nullable=True)
    reason_codes_json = Column(JSON, nullable=True)
    evidence_json = Column(JSON, nullable=True)
```

- [ ] **Step 4: 在 `src/storage/repositories.py` 增加 `GovernanceRepository`**

```python
class GovernanceRepository(BaseRepository):
    def save_draft(self, decision: GovernanceDecision) -> GovernanceDecision: ...
    def approve(self, decision_id: int, approved_by: str) -> GovernanceDecision: ...
    def publish(self, decision_id: int) -> GovernanceDecision: ...
    def rollback_latest(self, approved_by: str, reason: str) -> GovernanceDecision: ...
    def get_latest_published(self) -> GovernanceDecision | None: ...
```

要求：
- 发布时保留 `previous_strategy_id`，为回退提供来源
- 回退不删除历史记录，只新增一条 `rolled_back` / `published` 事件
- repository 返回领域对象，不把 ORM 暴露给上层

- [ ] **Step 5: 运行仓储测试确认通过**

Run: `pytest -q tests/test_governance_repository.py`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add tests/test_governance_repository.py src/storage/models.py src/storage/repositories.py
git commit -m "feat: persist governance decisions and publish state"
```

## Task 3: 落地治理评估器与 review 脚本

**Files:**
- Create: `src/governance/evaluator.py`
- Create: `scripts/run_governance_review.py`
- Create: `tests/test_governance_evaluator.py`
- Modify: `src/research_summary.py`
- Test: `tests/test_governance_evaluator.py`

- [ ] **Step 1: 写失败测试，锁定 keep/switch/fallback 三种决策**

```python
def test_evaluator_switches_when_challenger_wins_consistently():
    decision = evaluate_governance(summary, current_strategy_id="trend_momentum", policy=policy)
    assert decision.decision_type == "switch"
    assert decision.selected_strategy_id == "risk_adjusted_momentum"
```

- [ ] **Step 2: 运行测试确认当前缺少治理评估器**

Run: `pytest -q tests/test_governance_evaluator.py`
Expected: FAIL

- [ ] **Step 3: 实现治理评分与决策规则**

```python
def evaluate_governance(summary: dict[str, Any], current_strategy_id: str | None, policy: GovernanceConfig) -> GovernanceDecision:
    ...
```

最小规则：
- leader 的 `appearances < champion_min_appearances` 时不得切换
- challenger `top1_count < challenger_min_top1` 时不得切换
- challenger 的 `governance_score - current_score < challenger_min_score_margin` 时保持现状
- 当前 champion 缺席、显著退化或不再受支持时切到 fallback

```python
governance_score = (
    0.45 * avg_sharpe
    + 0.35 * avg_annual_return
    - 0.20 * abs(avg_max_drawdown)
)
```

- [ ] **Step 4: 新增治理 review 脚本**

```bash
python scripts/run_governance_review.py --summary reports/research/summary/research_summary.json
```

要求：
- 输入默认读取 `reports/research/summary/research_summary.json`
- 输出 `reports/governance/<date>.json`
- 同时把 draft decision 写入 `governance_decision` 表

- [ ] **Step 5: 运行治理评估测试**

Run: `pytest -q tests/test_governance_evaluator.py`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add src/governance/evaluator.py scripts/run_governance_review.py tests/test_governance_evaluator.py src/research_summary.py
git commit -m "feat: add governance evaluator and review draft flow"
```

## Task 4: 接入审批/发布/回退，并让生产侧消费已发布策略

**Files:**
- Create: `src/governance/runtime.py`
- Create: `src/governance/publisher.py`
- Create: `scripts/publish_governance_decision.py`
- Create: `scripts/rollback_governance_decision.py`
- Create: `tests/test_governance_runtime.py`
- Modify: `src/main.py`
- Modify: `tests/test_pipeline_e2e.py`
- Test: `tests/test_governance_runtime.py`
- Test: `tests/test_pipeline_e2e.py`

- [ ] **Step 1: 写失败测试，锁定生产优先读取最新已发布治理策略**

```python
def test_runtime_prefers_latest_published_governance_strategy():
    strategy_id = resolve_active_strategy_id(default_strategy_id="trend_momentum", repo=repo)
    assert strategy_id == "risk_adjusted_momentum"
```

- [ ] **Step 2: 运行测试确认当前生产仍固定读取 YAML 默认值**

Run: `pytest -q tests/test_governance_runtime.py tests/test_pipeline_e2e.py`
Expected: FAIL，当前 `main.py` 只看 `production_strategy_id`

- [ ] **Step 3: 实现审批/发布/回退服务**

```python
def publish_decision(decision_id: int, approved_by: str, repo: GovernanceRepository) -> GovernanceDecision: ...
def rollback_latest(approved_by: str, reason: str, repo: GovernanceRepository, fallback_strategy_id: str) -> GovernanceDecision: ...
```

要求：
- `manual_approval_required=true` 时，未审批 draft 不得发布
- 发布时只能发布 `draft` / `approved` 的最新候选，不允许任意覆盖
- 回退优先回到 `previous_strategy_id`，不存在则回到 `fallback_strategy_id`

- [ ] **Step 4: 修改 `src/main.py` 的 active strategy 解析逻辑**

```python
active_strategy_id = resolve_active_strategy_id(
    default_strategy_id=config_loader.load_production_strategy_id(),
    repo=GovernanceRepository(),
)
```

要求：
- 若治理层关闭、表为空、最新发布策略不受支持，则安全回退到 YAML 默认策略
- 运行日报时把治理来源写入 `report_output.data`

- [ ] **Step 5: 运行生产链路相关测试**

Run: `pytest -q tests/test_governance_runtime.py tests/test_pipeline_e2e.py`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add src/governance/runtime.py src/governance/publisher.py scripts/publish_governance_decision.py scripts/rollback_governance_decision.py tests/test_governance_runtime.py src/main.py tests/test_pipeline_e2e.py
git commit -m "feat: publish governance decisions into production runtime"
```

## Task 5: 升级门户、README 与治理运维说明，并做全量验证

**Files:**
- Modify: `src/report_portal.py`
- Modify: `README.md`
- Modify: `tasks/todo.md`
- Modify: `tests/test_report_portal.py`
- Test: `tests/test_report_portal.py`

- [ ] **Step 1: 写失败测试，锁定门户展示治理状态**

```python
def test_report_portal_shows_active_governance_strategy(tmp_path):
    result = build_report_portal(...)
    html = Path(result["output_paths"]["html"]).read_text(encoding="utf-8")
    assert "risk_adjusted_momentum" in html
    assert "治理决策" in html
```

- [ ] **Step 2: 运行测试确认当前门户还不展示治理状态**

Run: `pytest -q tests/test_report_portal.py`
Expected: FAIL

- [ ] **Step 3: 更新门户与 README**

要求：
- 门户显示：
  - 当前 active strategy
  - 最近 draft / published / rolled_back 状态
  - 最近治理评审日期
- README 增加完整运维命令：
  - `python scripts/run_governance_review.py`
  - `python scripts/publish_governance_decision.py --decision-id <id> --approved-by <name>`
  - `python scripts/rollback_governance_decision.py --approved-by <name> --reason <text>`
- `tasks/todo.md` 记录第二阶段治理层计划与结果

- [ ] **Step 4: 运行治理展示与全量验证**

Run: `pytest -q tests/test_report_portal.py`
Expected: PASS

Run: `pytest -q`
Expected: PASS

Run: `python3 -m compileall src scripts tests`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add src/report_portal.py README.md tasks/todo.md tests/test_report_portal.py
git commit -m "docs: surface governance lifecycle in portal and runbook"
```

## Final Verification Checklist

- [ ] `tests/test_governance_models.py` 通过
- [ ] `tests/test_governance_repository.py` 通过
- [ ] `tests/test_governance_evaluator.py` 通过
- [ ] `tests/test_governance_runtime.py` 通过
- [ ] `tests/test_pipeline_e2e.py` 通过
- [ ] `tests/test_report_portal.py` 通过
- [ ] `pytest -q` 全量通过
- [ ] `python3 -m compileall src scripts tests` 通过
- [ ] 未发布 draft 不会影响生产 active strategy
- [ ] 已发布策略可被 `src/main.py` 自动消费
- [ ] rollback 后生产侧可恢复到上一个稳定策略或 fallback
