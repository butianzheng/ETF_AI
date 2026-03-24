# Phase 5 Regime-Aware Governance Gate 设计

## 1. 背景

截至 2026-03-24，系统已经完成：

- 单 ETF 实盘约束
- 多候选研究
- champion / challenger / fallback 治理闭环
- review / publish / rollback / health check 自动化
- Phase 4 `regime` 研究分析与研究汇总输出

当前仍存在一个明显缺口：

- 研究层已经能回答“某候选在什么 `regime` 下更强/更弱”
- 治理层仍只基于整体 leaderboard 做 `keep / switch / fallback`
- 当前治理准入没有消费已有的 `regime` 证据

因此，Phase 5 的目标不是新增自动交易逻辑，而是在现有治理流程中加入一层面向单 ETF 实盘的 `regime-aware gate`，用于拦截“当前状态下明显不适配的已选目标策略”。

## 2. 本阶段已确认选择

本阶段按以下边界设计：

- 保持单 ETF 实盘，不做多策略同时在线
- 保持人工最终发布，不做自动实盘切换
- 本阶段只做治理门禁，不重写运行时选股/调仓逻辑
- 当当前市场 `regime` 与候选优势状态明显不匹配时，采用硬门禁
- 当前 `regime` 来源为治理周期执行时的实时重算
- `regime mismatch` 采用“只在明确劣势状态才拦截”的口径
- `明确劣势` 定义为：
  - 当前 `regime` 是该候选样本充足状态中的最低 `avg_annual_return`
  - 且该状态 `avg_annual_return <= 0`
  - 且该状态 `avg_sharpe <= 0`
- 样本不足不触发硬门禁，只记证据不足
- 样本充足性采用双门槛：
  - `appearances >= 2`
  - `avg_observation_count >= 20`
- 当前状态不确定时不拦截，只记证据不足/状态不确定
- 门禁作用于所有 `selected_strategy_id`
  - `keep`
  - `switch`
  - `fallback`

## 3. 目标

建设一层最小而明确的治理门禁，使系统可以：

- 在治理周期中实时重算当前 ETF 池的 `regime`
- 将 `selected_strategy_id` 与研究汇总中的 `regime` 证据进行适配性检查
- 对证据充分且明确不适配的目标策略直接打成 `blocked`
- 对证据不足或状态不确定的情况保持克制，只留下审计证据
- 保持当前 `publish` 语义不变，即只有 `review_status == ready` 才允许发布

## 4. 非目标

本阶段明确不做：

- 自动根据 `regime` 切换实盘策略
- 多策略同时在线或按状态动态配仓
- 为 `regime gate` 引入人工强制越权发布后门
- 把 `regime gate` 扩展为第二套复杂评分系统
- 改写现有 `publisher` / `runtime` 主流程语义
- 在门户中新增复杂独立页面

## 5. 总体流程

Phase 5 保持现有治理入口不变，仍由 `run_governance_cycle()` 驱动：

1. 读取研究汇总
2. 运行现有 `evaluate_governance()`，先得到原始 `selected_strategy_id`
3. 治理周期基于最新 ETF 池行情实时重算 `current_regime`
4. 用 `regime gate` 校验 `selected_strategy_id` 在当前状态下是否适配
5. 将 `regime gate` 结果与现有自动化阻断原因合并
6. 统一写回 `review_status`、`blocked_reasons`、`evidence`

这里的核心原则是：

- `evaluator` 负责“选谁”
- `regime gate` 负责“现在能不能放行”
- `publisher` 继续只负责“只有 `ready` 才能发”

## 6. 模块边界

### 6.1 治理入口

仍复用：

- `src/governance/automation.py`

不新增第二套治理入口，也不要求用户改变脚本调用方式。

### 6.2 候选选择层

仍复用：

- `src/governance/evaluator.py`

它继续只做整体 leaderboard 的治理评估，不感知实时市场状态。

### 6.3 Regime Gate 层

建议新增独立模块：

- `src/governance/regime_gate.py`

职责只包含：

- 基于最新 ETF 池行情重算 `current_regime`
- 从研究汇总中抽取 `selected_strategy_id` 的 `regime` 统计
- 产出标准化门禁结果供 `automation` 合并

它不负责重新选策略，不负责发布，也不改动生产 runtime。

### 6.4 发布层

仍复用：

- `src/governance/publisher.py`

保持当前语义不变：

- `manual approval required`
- `review_status == ready` 才允许发布

## 7. 当前 Regime 的实时重算

治理周期执行时，系统应基于当前启用 ETF 池的最新可用行情实时重算 `current_regime`。

建议口径：

- ETF 集合：`config/etf_pool.yaml` 中 `enabled=true` 的标的
- 规则与阈值：直接复用 Phase 4 的 `ResearchRegimeConfig` 与 `RegimeClassifier`
- 输入数据：治理周期执行时获取的最新行情历史窗口
  - 至少覆盖 `RegimeClassifier` 所需的 120 日均线、60 日回撤、20 日波动率窗口
  - 建议沿用当前主流程的 lookback 口径，避免治理与主流程使用不同历史深度
- 输出结果：取最新一个 `RegimeSnapshot` 作为 `current_regime`

若无法得到可靠结果，则门禁降级为 `skipped`，而不是让治理周期失败。

## 8. 门禁判定模型

### 8.1 输出状态

`regime gate` 只输出三类结果：

- `pass`
- `blocked`
- `skipped`

### 8.2 `blocked` 条件

只有同时满足以下条件才进入 `blocked`：

- 当前 `regime` 已成功实时重算，且不是不确定状态
- 研究汇总中存在 `selected_strategy_id` 在当前 `regime` 下的统计行
- 该统计行样本充足：
  - `appearances >= 2`
  - `avg_observation_count >= 20`
- 在该策略所有“样本充足”的 `regime` 中，当前 `regime` 的 `avg_annual_return` 最差
- 且当前 `regime` 的 `avg_annual_return <= 0`
- 且当前 `regime` 的 `avg_sharpe <= 0`

### 8.3 `skipped` 条件

以下场景统一进入 `skipped`：

- 当前 `regime` 不确定
- 当前 `regime` 对应统计缺失
- 当前 `regime` 对应统计样本不足
- 该策略整体缺少足够多的可比较 `regime` 行，无法可靠判断最差状态

### 8.4 `pass` 条件

只要未命中 `blocked`，且没有触发 `skipped`，则视为 `pass`。

## 9. 不确定状态与降级策略

当前 `regime` 重算结果若带以下原因码，应视为“不确定状态”，只记证据，不触发硬门禁：

- `INSUFFICIENT_POOL_COVERAGE`
- `CONFLICTING_RULES`

建议统一映射为：

- `skip_reason = CURRENT_REGIME_UNCERTAIN`

这类情况不应让治理周期失败，也不应直接阻断单 ETF 实盘流程。

## 10. 原因码与证据结构

### 10.1 `blocked_reason`

建议新增：

- `SELECTED_STRATEGY_REGIME_MISMATCH`

仅在门禁真实拦截时写入 `blocked_reasons`。

### 10.2 `skip_reason`

建议支持以下类型：

- `CURRENT_REGIME_UNCERTAIN`
- `SELECTED_STRATEGY_REGIME_STATS_MISSING`
- `SELECTED_STRATEGY_REGIME_SAMPLE_INSUFFICIENT`
- `SELECTED_STRATEGY_REGIME_COMPARISON_INSUFFICIENT`

### 10.3 evidence 结构

建议统一写入 `decision.evidence["regime_gate"]`：

```json
{
  "gate_status": "pass|blocked|skipped",
  "selected_strategy_id": "trend_momentum",
  "current_regime": {
    "trade_date": "2026-03-24",
    "regime_label": "risk_off",
    "reason_codes": []
  },
  "sample_thresholds": {
    "min_appearances": 2,
    "min_avg_observation_count": 20
  },
  "current_regime_stats": {},
  "worst_regime_stats": {},
  "skip_reason": null,
  "blocked_reason": null
}
```

要求：

- 即使 `gate_status=skipped`，也保留 `current_regime` 与 `skip_reason`
- 即使 `gate_status=pass`，也保留用于审计的比较证据
- `blocked_reason` 只在真实拦截时出现

## 11. 配置策略

建议在 `GovernanceAutomationConfig` 下新增一组最小化的 `regime_gate` 嵌套配置，而不是把治理门禁配置塞进研究层：

- `regime_gate.enabled`
- `regime_gate.min_appearances`
- `regime_gate.min_avg_observation_count`

默认值建议：

- `regime_gate.enabled = true`
- `regime_gate.min_appearances = 2`
- `regime_gate.min_avg_observation_count = 20`

Phase 5 第一版不开放更多“明确劣势”阈值配置，保持逻辑固定，避免配置膨胀。

## 12. Review Status 合并规则

`automation` 需要把两类阻断原因统一合并：

- 现有自动化门禁
  - `SUMMARY_STALE`
  - `INSUFFICIENT_REPORT_COUNT`
  - `PUBLISH_COOLDOWN`
  - `OPEN_CRITICAL_INCIDENT`
- 新增 `regime gate` 门禁
  - `SELECTED_STRATEGY_REGIME_MISMATCH`

最终规则：

- 只要任一阻断原因存在，`review_status = blocked`
- 若无阻断原因，则 `review_status = ready`
- 不新增新的治理状态机

## 13. 单 ETF 实盘约束下的行为

在单 ETF 实盘场景下，Phase 5 的行为必须保持简单：

- 治理层仍然只产生一个 `selected_strategy_id`
- 该策略仍需经过人工审批与发布
- `regime gate` 只是一道“发布前适配性门禁”
- 它不替代候选研究，不替代治理选择，也不直接驱动运行时自动切换

因此，Phase 5 是治理约束增强，不是执行逻辑扩容。

## 14. 文件边界

### Create

- `src/governance/regime_gate.py`
  - `current_regime` 实时重算
  - `selected_strategy_id` 的 `regime fit` 评估
  - 标准化门禁结果输出
- `tests/test_governance_regime_gate.py`

### Modify

- `src/core/config.py`
  - 增加治理门禁配置
- `config/strategy.yaml`
  - 增加治理门禁默认配置
- `src/governance/automation.py`
  - 接入 `regime gate`
  - 合并 `blocked_reasons`
  - 回写 `decision.evidence["regime_gate"]`
- `scripts/run_governance_cycle.py`
  - 输出新增 `regime gate` 证据
- `scripts/run_governance_review.py`
  - 输出新增 `regime gate` 证据
- `tests/test_governance_automation.py`
  - 增补集成测试

### Reuse

- `src/research/regime.py`
  - 复用 `RegimeClassifier`
- `src/research_summary.py`
  - 复用 `candidate_regime_leaderboard`
- `src/governance/evaluator.py`
  - 保持选策略职责
- `src/governance/publisher.py`
  - 保持发布准入职责

## 15. 异常处理原则

- `regime gate` 失败不能让整个治理周期崩掉
- 当前状态不确定时，只能 `skipped`，不能直接 `blocked`
- 样本不足时，只能 `skipped`，不能直接 `blocked`
- 只有证据充分且明确劣势时才允许硬拦截

这保证治理层在证据不足时保持克制，在证据明确时保持约束。

## 16. 测试策略

### 16.1 单元测试

新增 `tests/test_governance_regime_gate.py`，覆盖：

- 当前状态命中明确劣势时返回 `blocked`
- 当前状态不是最差状态时返回 `pass`
- 当前状态对应统计样本不足时返回 `skipped`
- 当前状态不确定时返回 `skipped`
- 可比较 `regime` 整体不足时返回 `skipped`

### 16.2 自动化集成测试

扩展 `tests/test_governance_automation.py`，覆盖：

- `run_governance_cycle()` 可并入 `SELECTED_STRATEGY_REGIME_MISMATCH`
- 新旧门禁原因可同时存在
- `keep / switch / fallback` 三类 `selected_strategy_id` 都受门禁影响
- `blocked` 时 `review_status` 正确落为 `blocked`
- `skipped` 时只写 evidence，不新增 `blocked_reasons`

### 16.3 发布语义测试

保留并复用现有发布测试语义：

- `review_status != ready` 不能发布
- 不为 `regime gate` 增加特殊发布例外

## 17. 验收标准

满足以下条件即可进入实现阶段：

- 治理 draft 能写出 `regime_gate` evidence
- 当前状态明确不适配时，draft 自动进入 `blocked`
- 当前状态不确定或样本不足时，draft 保持原有准入能力，仅附带审计证据
- `publisher` 的现有行为不需要新分支即可正确拒绝被阻断的 draft
- 单 ETF 实盘仍维持“研究 -> 治理 -> 人工审批 -> 发布”的闭环

## 18. 后续阶段边界

若未来继续演进，可作为后续独立小阶段讨论：

- 将 `regime gate` 结果在报告门户中做更完整展示
- 为人工治理提供更精细的解释卡片
- 研究是否需要 `regime-aware challenger` 或更强的状态稳定性评分

这些都不属于 Phase 5 第一版。
