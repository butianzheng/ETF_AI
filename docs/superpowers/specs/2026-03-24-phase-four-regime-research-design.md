# Phase 4 状态感知研究优先设计

## 1. 背景

截至 2026-03-24，系统已经完成：

- 单 ETF 生产约束
- 多候选研究
- champion/challenger/fallback 治理闭环
- 半自动治理编排、健康巡检、rollback recommendation

当前仍缺少一层关键研究能力：

- 研究结果仍以整体区间表现为主
- 无法回答“某候选是否只在特定市场状态下有效”
- 无法做基于状态的样本内/样本外观察
- 后续 `RegimeAwareStrategy` 缺少统一、可解释的输入基础

因此，下一阶段不直接把状态感知推到生产，而是先建设研究优先的 `regime` 分析框架。

## 2. 本阶段已确认选择

本阶段按以下边界实施：

- `regime` 定义方式：规则型
- 状态颗粒度：3 档
  - `risk_on`
  - `neutral`
  - `risk_off`
- 状态锚点：ETF 池聚合，而不是单一指数
- 范围：研究优先
- 本阶段不新增生产候选策略
- 本阶段不改变 governance publish/runtime 逻辑

## 3. 目标

建设一套面向研究线的状态感知分析框架，使系统可以：

- 对研究区间中的每个交易日打上 `regime` 标签
- 对候选策略结果按 `regime` 分层统计
- 对候选策略结果按 `in_sample / out_of_sample` 分层统计
- 识别候选是否存在明显的状态依赖或样本外退化
- 为后续 `RegimeAwareStrategy` 原型提供统一输入与证据基础

## 4. 非目标

本阶段明确不做：

- 直接把 `regime` 结果接入生产策略切换
- 新增 `RegimeAwareStrategy` 生产候选
- 自动根据 `regime` 调整实盘仓位
- walk-forward、聚类分桶、在线学习
- 对现有 governance runtime 做状态驱动重写

## 5. 总体设计

本阶段只增强研究流：

1. 对 ETF 池行情生成池级状态特征
2. 用规则型 `RegimeClassifier` 生成逐日状态标签
3. 将状态标签映射到研究结果与候选回测结果
4. 在研究输出中新增：
   - `overall`
   - `by_regime`
   - `in_sample`
   - `out_of_sample`
   - `regime_transition`
5. 升级研究 JSON/Markdown/HTML 摘要

生产流保持不变，仍然只消费已发布策略。

## 6. Regime 模型

### 6.1 状态标签

统一使用：

- `risk_on`
- `neutral`
- `risk_off`

### 6.2 ETF 池聚合方法

`regime` 不依赖单一指数，而由当前启用 ETF 池的池级表现生成。

池级特征计算原则：

- ETF 集合：`config/etf_pool.yaml` 中 `enabled=true` 的标的
- 聚合方式：
  - 趋势宽度类特征用占比
  - 数值类特征优先用横截面中位数，避免单只 ETF 扰动过大
- 当某只 ETF 历史窗口不足时，当日该 ETF 不参与该特征聚合
- 若参与样本数低于最小阈值，则当日 `regime` 标为 `neutral`，并带 `INSUFFICIENT_POOL_COVERAGE`

### 6.3 池级特征

首批建议特征：

- `pool_return_20`
- `pool_return_60`
- `pool_ma_distance_120`
- `pool_breadth_above_ma120`
  ETF 池内价格高于 MA120 的占比
- `pool_volatility_20`
- `pool_drawdown_60`

### 6.4 默认判定规则

默认规则全部配置化，以下是建议初值：

#### `risk_on`

同时满足：

- `pool_breadth_above_ma120 >= 0.60`
- `pool_return_20 > 0`
- `pool_return_60 > 0`
- `pool_drawdown_60 > -0.08`

#### `risk_off`

满足任一组即可：

- `pool_breadth_above_ma120 <= 0.35`
- `pool_return_20 < 0` 且 `pool_return_60 < 0` 且 `pool_drawdown_60 <= -0.12`
- `pool_ma_distance_120 <= -0.03` 且 `pool_volatility_20 >= min_volatility_20`

#### `neutral`

其余情况全部归为 `neutral`

### 6.5 输出对象

建议新增统一输出 `RegimeSnapshot`：

- `trade_date`
- `regime_label`
- `regime_score`
- `reason_codes`
- `metrics_snapshot`

其中：

- `regime_label` 为三档标签
- `regime_score` 为区间 `[-1, 1]` 的解释性分数
  - 偏正：更接近 `risk_on`
  - 偏负：更接近 `risk_off`
- `reason_codes` 用于报告解释
- `metrics_snapshot` 保留当日池级特征快照

## 7. 样本内 / 样本外分析

### 7.1 切片策略

第一版采用固定时间切片，不上 walk-forward：

- 前 70% 交易日：`in_sample`
- 后 30% 交易日：`out_of_sample`

切片基于研究窗口内的交易日序列，而不是自然月或报告数量。

### 7.2 输出目的

该切片主要用于回答：

- 某候选是否只在样本内看起来优秀
- 某候选是否在样本外明显退化
- 状态优势是否只集中在单一时间段

## 8. Regime 分层分析框架

### 8.1 分析层级

每个候选都输出以下维度：

- `overall_metrics`
- `by_regime_metrics`
- `in_sample_metrics`
- `out_of_sample_metrics`
- `by_regime_and_sample_metrics`
- `regime_transition_metrics`

### 8.2 指标集合

首批统一指标：

- `annual_return`
- `max_drawdown`
- `sharpe`
- `turnover`
- `trade_count`
- `win_rate`
- `profit_drawdown_ratio`
- `observation_count`

### 8.3 Transition 分析

为避免阶段膨胀，第一版只做轻量 transition 统计：

- 统计状态切换点
- 观察切换前后 `N=5` 个交易日内的候选收益和回撤表现
- 不做复杂事件研究或显著性检验

## 9. 研究产物扩展

### 9.1 单次研究报告 JSON

在现有 `comparison_rows` 与 `research_output` 基础上增加：

- `regime_config_snapshot`
- `regime_daily_labels`
- `candidate_regime_metrics`
- `candidate_sample_split_metrics`
- `candidate_regime_transition_metrics`

### 9.2 研究汇总 JSON

在现有 `research_summary.json` 基础上增加：

- `regime_summary`
- `candidate_regime_leaderboard`
- `candidate_out_of_sample_leaderboard`
- `candidate_regime_observations`

### 9.3 Markdown / HTML 展示重点

必须回答四个问题：

1. 哪个候选在 `risk_on` 最强
2. 哪个候选在 `risk_off` 更稳
3. 某候选是否只在单一 `regime` 下有效
4. 某候选在样本外是否明显退化

## 10. 文件边界

### Create

- `src/research/regime.py`
  ETF 池聚合特征与 `RegimeClassifier`
- `src/research/segmentation.py`
  研究窗口切片逻辑
- `src/research/regime_analysis.py`
  按 `regime` / `sample split` 聚合候选结果
- `tests/test_regime_classifier.py`
- `tests/test_regime_analysis.py`

### Modify

- `config/research.yaml`
  增加 `regime` 阈值与 sample split 配置
- `src/core/config.py`
  增加 research regime 配置模型
- `src/research_pipeline.py`
  接入 regime 标注、sample split、analysis 输出
- `src/research_summary.py`
  接入新的研究汇总字段与 leaderboard
- `tests/test_research_pipeline.py`
- `tests/test_research_summary.py`

### 暂不修改

- `src/main.py`
- `src/governance/runtime.py`
- `src/governance/publisher.py`
- `src/report_portal.py`

如需在门户中展示 regime 研究摘要，应单独作为后续小阶段处理。

## 11. 默认配置建议

建议在 `config/research.yaml` 中新增：

```yaml
research:
  regime:
    enabled: true
    pool_min_coverage_ratio: 0.6
    sample_split_ratio: 0.7
    transition_window_days: 5
    risk_on:
      min_breadth_above_ma120: 0.60
      min_return_20: 0.0
      min_return_60: 0.0
      min_drawdown_60: -0.08
    risk_off:
      max_breadth_above_ma120: 0.35
      max_return_20: 0.0
      max_return_60: 0.0
      max_drawdown_60: -0.12
      max_ma_distance_120: -0.03
      min_volatility_20: 0.025
```

## 12. 测试策略

### 12.1 单元测试

- `RegimeClassifier`：
  - `risk_on`
  - `neutral`
  - `risk_off`
  - 样本覆盖不足降级
- `segmentation`：
  - 70/30 切片边界
- `regime_analysis`：
  - 正确按状态聚合
  - 正确输出样本内/样本外指标

### 12.2 集成测试

- `run_research_pipeline()` 输出新增 regime 字段
- `research_summary.json` 包含新的 regime 汇总结构
- Markdown/HTML 页面能展示按状态和样本分层的解释

## 13. 风险与控制

### 13.1 风险

- ETF 池较小时，池级特征可能过于敏感
- 阈值初值可能带有主观性
- `regime` 标签过多会稀释样本量
- 状态分层后，某些候选的样本数可能很少

### 13.2 控制

- 第一版只保留 3 档状态
- 阈值全部配置化
- 对低覆盖率样本强制降级为 `neutral`
- 所有分层结果必须附带 `observation_count`

## 14. 后续衔接

本阶段完成后，下一阶段才进入：

- `RegimeAwareStrategy` 研究原型
- 状态敏感候选与基线候选并行比较
- 必要时再讨论是否进入治理候选池

换句话说，本阶段交付的是“研究框架与证据层”，不是“生产状态策略层”。
