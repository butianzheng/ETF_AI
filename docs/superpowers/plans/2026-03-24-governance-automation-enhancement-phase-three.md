# 第三阶段治理自动化增强 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在保持“单一 ETF 或空仓”实盘约束和人工最终发布门禁不变的前提下，把治理流程升级为可定时执行、可自动预审、可持续巡检、可生成回退建议的半自动闭环。

**Architecture:** 在现有 `governance` 域上新增 `automation` 与 `health` 两个子能力。`automation` 负责读取最新研究汇总、生成/去重 draft、执行发布前门禁并把 draft 标记为 `ready` 或 `blocked`；`health` 负责扫描最近日报、已发布策略和组合状态，识别风险退化、策略漂移、执行失败或治理陈旧，并持久化 incident。生产主流程仍然只消费 `published` 策略，不直接接受自动 draft。

**Tech Stack:** Python 3.10+, pandas, SQLAlchemy 2.x, pydantic 2.x, pytest, YAML, SQLite

---

> 说明：
> 1. 本计划建立在已完成的第二阶段治理层落地之上。
> 2. 本轮仍只治理 `trend_momentum` / `risk_adjusted_momentum`，不新增候选策略。
> 3. 默认不做“满足条件即自动发布到实盘”；自动化只做到 draft 生成、预审、巡检、回退建议。
> 4. 所有自动化规则都以“单一 ETF 实盘”场景为前提：若发现策略漂移、风控异常或治理数据陈旧，优先阻断和告警，而不是继续自动切换。

## File Structure

### Create

- `src/governance/automation.py`
  治理自动编排服务，负责 summary 去重、draft 生成、门禁校验、review 状态流转。
- `src/governance/health.py`
  治理健康巡检服务，负责 incident 检测与 rollback recommendation 生成。
- `scripts/run_governance_cycle.py`
  一键执行“读取研究汇总 -> 生成/更新 draft -> 自动预审 -> 输出结果”。
- `scripts/check_governance_health.py`
  扫描最新实盘日报、已发布策略与组合状态，输出 incident/rollback 建议。
- `tests/test_governance_automation.py`
  验证自动 review cycle、summary 去重、cooldown、blocked reasons。
- `tests/test_governance_health.py`
  验证 incident 检测、rollback recommendation 和单一 ETF 实盘场景的保护门禁。

### Modify

- `src/core/config.py`
  增加治理自动化配置模型。
- `config/strategy.yaml`
  增加 `governance.automation` 配置段。
- `src/governance/models.py`
  为 `GovernanceDecision` 增加自动 review 元数据，并新增 `GovernanceIncident` 模型。
- `src/governance/publisher.py`
  发布前增加 `review_status == "ready"` 等自动化门禁校验。
- `src/storage/models.py`
  为治理决策表增加自动 review 字段，并新增 incident 表。
- `src/storage/repositories.py`
  增加 draft 去重、review 状态更新、incident 持久化与查询接口。
- `src/report_portal.py`
  门户展示 ready/blocked draft、open incidents、最近健康巡检结果。
- `README.md`
  增加治理自动化运行手册与推荐操作顺序。
- `tasks/todo.md`
  记录第三阶段治理自动化计划与结果。
- `tests/test_governance_repository.py`
  补充 review 状态与 incident 仓储测试。
- `tests/test_governance_runtime.py`
  补充“blocked draft 不得发布”与“自动化关闭时兼容旧行为”测试。
- `tests/test_pipeline_e2e.py`
  补充“治理 cycle -> 人工 publish -> 实盘主流程消费”的端到端测试。
- `tests/test_report_portal.py`
  验证门户展示自动化治理状态。

## Task 1: 扩展治理配置、领域模型与审计持久化

**Files:**
- Create: `tests/test_governance_automation.py`
- Create: `tests/test_governance_health.py`
- Modify: `src/core/config.py`
- Modify: `config/strategy.yaml`
- Modify: `src/governance/models.py`
- Modify: `src/storage/models.py`
- Modify: `src/storage/repositories.py`
- Modify: `tests/test_governance_repository.py`
- Test: `tests/test_governance_repository.py`

- [x] **Step 1: 写失败测试，锁定治理自动化配置、review 状态和 incident 持久化**

```python
def test_strategy_config_loads_governance_automation_policy():
    strategy_config = ConfigLoader().load_strategy_config()
    assert strategy_config.governance.automation.enabled is True
    assert strategy_config.governance.automation.max_summary_age_days == 7
    assert strategy_config.governance.automation.min_days_between_switches == 20


def test_governance_repository_tracks_review_status_and_incidents():
    repo = GovernanceRepository()
    draft = repo.save_draft(_build_switch_decision())
    updated = repo.set_review_status(
        draft.id,
        review_status="blocked",
        blocked_reasons=["SUMMARY_STALE"],
    )
    incident = repo.save_incident(_build_incident())
    assert updated.review_status == "blocked"
    assert updated.blocked_reasons == ["SUMMARY_STALE"]
    assert repo.list_open_incidents()[0].incident_type == incident.incident_type
```

- [x] **Step 2: 运行测试确认当前缺少自动化配置与 incident 仓储**

Run: `pytest -q tests/test_governance_repository.py`
Expected: FAIL，`GovernanceDecision` 缺少 `review_status/blocked_reasons` 或 repository 缺少 incident 接口

- [x] **Step 3: 增加最小自动化配置和领域对象**

```python
class GovernanceAutomationConfig(BaseModel):
    enabled: bool = True
    require_fresh_summary: bool = True
    max_summary_age_days: int = 7
    min_reports_required: int = 3
    min_days_between_switches: int = 20
    block_on_open_incident: bool = True
    risk_breach_streak: int = 2
```

```python
class GovernanceDecision(BaseModel):
    ...
    summary_hash: str | None = None
    source_report_date: str | None = None
    review_status: Literal["pending", "ready", "blocked"] = "pending"
    blocked_reasons: list[str] = Field(default_factory=list)
```

```python
class GovernanceIncident(BaseModel):
    id: int | None = None
    incident_date: date
    incident_type: Literal["SUMMARY_STALE", "PUBLISH_COOLDOWN", "RISK_BREACH", "STRATEGY_DRIFT", "EXECUTION_FAILURE", "GOVERNANCE_STALE"]
    severity: Literal["info", "warning", "critical"]
    status: Literal["open", "resolved"] = "open"
    strategy_id: str | None = None
    reason_codes: list[str] = Field(default_factory=list)
    evidence: dict[str, Any] = Field(default_factory=dict)
```

要求：
- `GovernanceConfig` 下新增 `automation`，避免再引入第三份 YAML
- review 状态与 publish 状态分离，避免把“人工批准”与“系统预审通过”混在一个字段里
- incident 必须可审计、可查询、可关闭，不靠 portal 临时计算

- [x] **Step 4: 扩展 SQLite 模型与仓储接口**

```python
class GovernanceRepository(BaseRepository):
    def find_draft_by_summary_hash(self, summary_hash: str) -> GovernanceDecision | None: ...
    def set_review_status(self, decision_id: int, review_status: str, blocked_reasons: list[str]) -> GovernanceDecision: ...
    def save_incident(self, incident: GovernanceIncident) -> GovernanceIncident: ...
    def list_open_incidents(self) -> list[GovernanceIncident]: ...
    def resolve_incident(self, incident_id: int) -> GovernanceIncident: ...
```

要求：
- `governance_decision` 表新增 `summary_hash/source_report_date/review_status/blocked_reasons_json`
- 新增 `governance_incident` 表，按 `incident_date + incident_type + status` 可查询
- repository 仍然只返回领域对象，不把 ORM 泄漏给上层

- [x] **Step 5: 运行仓储测试确认通过**

Run: `pytest -q tests/test_governance_repository.py`
Expected: PASS

- [x] **Step 6: 提交**

```bash
git add src/core/config.py config/strategy.yaml src/governance/models.py src/storage/models.py src/storage/repositories.py tests/test_governance_repository.py tests/test_governance_automation.py tests/test_governance_health.py
git commit -m "feat: add governance automation config and audit state"
```

## Task 2: 落地自动 review cycle 与发布前门禁

**Files:**
- Create: `src/governance/automation.py`
- Create: `scripts/run_governance_cycle.py`
- Modify: `src/governance/publisher.py`
- Modify: `scripts/run_governance_review.py`
- Modify: `tests/test_governance_automation.py`
- Modify: `tests/test_governance_runtime.py`
- Test: `tests/test_governance_automation.py`
- Test: `tests/test_governance_runtime.py`

- [x] **Step 1: 写失败测试，锁定 cycle 去重、summary freshness、cooldown 和 ready/blocked 状态**

```python
def test_run_governance_cycle_marks_ready_draft_for_fresh_summary(tmp_path):
    result = run_governance_cycle(summary_path=summary_path, policy=policy, repo=repo)
    assert result.decision.review_status == "ready"
    assert result.decision.blocked_reasons == []


def test_run_governance_cycle_blocks_switch_within_cooldown(tmp_path):
    result = run_governance_cycle(summary_path=summary_path, policy=policy, repo=repo)
    assert result.decision.review_status == "blocked"
    assert "PUBLISH_COOLDOWN" in result.decision.blocked_reasons


def test_publish_rejects_blocked_draft_when_automation_enabled():
    with pytest.raises(ValueError, match="review_status"):
        publish_decision(...)
```

- [x] **Step 2: 运行测试确认当前缺少自动编排与自动化门禁**

Run: `pytest -q tests/test_governance_automation.py tests/test_governance_runtime.py`
Expected: FAIL

- [x] **Step 3: 实现自动 review cycle**

```python
def run_governance_cycle(
    summary_path: str | Path,
    repo: GovernanceRepository,
    policy: GovernanceConfig,
    current_strategy_id: str | None,
) -> GovernanceCycleResult:
    ...
```

最小规则：
- 对 `research_summary.json` 计算 `summary_hash`，相同 summary 不重复创建 draft
- summary 超过 `max_summary_age_days` 时直接 blocked
- `report_count < min_reports_required` 时直接 blocked
- 若最新已发布策略距离当前不足 `min_days_between_switches` 且本次是 `switch`，则 blocked
- 若存在 open critical incident 且 `block_on_open_incident=true`，则 blocked
- 自动化仅生成/更新 draft，不自动 publish

- [x] **Step 4: 增加治理 cycle 脚本并复用 review 逻辑**

```bash
python scripts/run_governance_cycle.py --summary reports/research/summary/research_summary.json
```

要求：
- 输出 `reports/governance/cycle/<date>.json`
- 终端打印 `decision_id/review_status/blocked_reasons`
- `scripts/run_governance_review.py` 继续可用，但内部尽量复用 `automation.py` 的 draft 生成逻辑，避免双套实现

- [x] **Step 5: 更新发布逻辑，要求 draft 已通过自动预审**

```python
if policy.automation.enabled and decision.review_status != "ready":
    raise ValueError("governance decision review_status must be ready before publishing")
```

要求：
- 保持 `manual_approval_required=true` 的语义不变
- `automation.enabled=false` 时兼容第二阶段旧行为

- [x] **Step 6: 运行自动 review 与 runtime 测试**

Run: `pytest -q tests/test_governance_automation.py tests/test_governance_runtime.py`
Expected: PASS

- [x] **Step 7: 提交**

```bash
git add src/governance/automation.py src/governance/publisher.py scripts/run_governance_cycle.py scripts/run_governance_review.py tests/test_governance_automation.py tests/test_governance_runtime.py
git commit -m "feat: add governance automation review cycle"
```

## Task 3: 增加治理健康巡检与回退建议

**Files:**
- Create: `src/governance/health.py`
- Create: `scripts/check_governance_health.py`
- Modify: `src/storage/repositories.py`
- Modify: `tests/test_governance_health.py`
- Modify: `tests/test_pipeline_e2e.py`
- Test: `tests/test_governance_health.py`

- [x] **Step 1: 写失败测试，锁定 risk breach、strategy drift、execution failure 与 rollback recommendation**

```python
def test_governance_health_opens_incidents_for_strategy_drift_and_risk_breach(tmp_path):
    result = check_governance_health(report_dir=tmp_path, repo=repo, policy=policy)
    assert {item.incident_type for item in result.incidents} == {"STRATEGY_DRIFT", "RISK_BREACH"}


def test_governance_health_creates_fallback_recommendation_for_critical_incident(tmp_path):
    result = check_governance_health(report_dir=tmp_path, repo=repo, policy=policy, create_rollback_draft=True)
    assert result.rollback_recommendation is not None
    assert result.rollback_recommendation.decision_type == "fallback"
```

- [x] **Step 2: 运行测试确认当前没有治理健康巡检能力**

Run: `pytest -q tests/test_governance_health.py`
Expected: FAIL

- [x] **Step 3: 实现健康巡检服务**

```python
def check_governance_health(
    report_dir: str | Path,
    repo: GovernanceRepository,
    policy: GovernanceConfig,
    create_rollback_draft: bool = False,
) -> GovernanceHealthResult:
    ...
```

最小规则：
- 最新日报里的 `active_strategy_id` 与 `latest_published.selected_strategy_id` 不一致时，记 `STRATEGY_DRIFT`
- 最近 `risk_breach_streak` 份日报中连续 `risk_level in {"orange", "red"}` 时，记 `RISK_BREACH`
- 最新执行状态为 `rejected/failed` 且当天要求 rebalance 时，记 `EXECUTION_FAILURE`
- 最新研究汇总或最新 published 决策超过 freshness 限制时，记 `GOVERNANCE_STALE`
- 若出现 `critical` incident 且 `create_rollback_draft=true`，生成 `fallback` draft recommendation，但默认不自动 publish

- [x] **Step 4: 增加健康巡检脚本**

```bash
python scripts/check_governance_health.py --report-dir reports/daily --create-rollback-draft
```

要求：
- 输出 `reports/governance/health/<date>.json`
- 同时把 incident 写入 `governance_incident`
- 若生成 rollback recommendation，明确打印 `decision_id`

- [x] **Step 5: 运行健康巡检测试与相关 e2e**

Run: `pytest -q tests/test_governance_health.py tests/test_pipeline_e2e.py`
Expected: PASS

- [x] **Step 6: 提交**

```bash
git add src/governance/health.py scripts/check_governance_health.py src/storage/repositories.py tests/test_governance_health.py tests/test_pipeline_e2e.py
git commit -m "feat: add governance health checks and rollback recommendation"
```

## Task 4: 升级门户与治理运维手册，并做全量验证

**Files:**
- Modify: `src/report_portal.py`
- Modify: `README.md`
- Modify: `tasks/todo.md`
- Modify: `tests/test_report_portal.py`
- Test: `tests/test_report_portal.py`

- [x] **Step 1: 写失败测试，锁定门户展示 ready/blocked draft 和 open incidents**

```python
def test_report_portal_shows_governance_automation_state(tmp_path):
    result = build_report_portal(...)
    html = Path(result["output_paths"]["html"]).read_text(encoding="utf-8")
    assert "review_status" in html
    assert "blocked" in html
    assert "open incidents" in html
```

- [x] **Step 2: 运行测试确认当前门户还不展示自动化治理状态**

Run: `pytest -q tests/test_report_portal.py`
Expected: FAIL

- [x] **Step 3: 更新门户与 README**

要求：
- 门户显示：
  - 最近 draft 的 `review_status`
  - `blocked_reasons`
  - open incident 数量、最高严重级别、最近 rollback recommendation
- README 增加推荐运行顺序：
  - `python scripts/run_research.py ...`
  - `python scripts/summarize_research_reports.py`
  - `python scripts/run_governance_cycle.py --summary ...`
  - 人工确认后 `python scripts/publish_governance_decision.py ...`
  - `python scripts/check_governance_health.py --report-dir reports/daily`
- README 明确：单一 ETF 实盘默认不启用自动 publish
- `tasks/todo.md` 记录第三阶段计划与后续执行结果占位

- [x] **Step 4: 运行门户与全量验证**

Run: `pytest -q tests/test_report_portal.py`
Expected: PASS

Run: `pytest -q`
Expected: PASS

Run: `python3 -m compileall src scripts tests`
Expected: PASS

- [x] **Step 5: 提交**

```bash
git add src/report_portal.py README.md tasks/todo.md tests/test_report_portal.py
git commit -m "docs: surface governance automation status and runbook"
```

## Final Verification Checklist

- [x] `tests/test_governance_repository.py` 通过
- [x] `tests/test_governance_automation.py` 通过
- [x] `tests/test_governance_runtime.py` 通过
- [x] `tests/test_governance_health.py` 通过
- [x] `tests/test_pipeline_e2e.py` 通过
- [x] `tests/test_report_portal.py` 通过
- [x] `pytest -q` 全量通过
- [x] `python3 -m compileall src scripts tests` 通过
- [x] 相同 `research_summary.json` 不会重复生成多个 draft
- [x] stale / cooldown / open critical incident 会阻断 draft 进入 `ready`
- [x] `review_status != ready` 的 draft 不得发布
- [x] health check 能产出 incident，并在 critical 场景下生成 rollback recommendation
- [x] 统一门户可展示自动化治理状态，且不改变“生产只消费 published 策略”的主约束
