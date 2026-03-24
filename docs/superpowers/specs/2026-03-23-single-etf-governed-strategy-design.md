# 单ETF生产 + 多候选研究治理系统设计

## 1. 背景

当前系统已经具备：

- ETF 行情抓取、标准化、存储
- 单策略回测
- Agent 辅助日报、研究报告、风险监控
- 半自动执行与统一门户

当前主要短板：

- 研究、生产、执行语义不一致
- 生产侧缺少严格的调仓日/执行日约束
- 研究仍以少量参数比较为主，尚未形成候选策略治理体系
- 回测与实盘成交规则不一致，结果可信度不足
- 测试与真实库隔离不足，工程风险较高

## 2. 目标

建设一套`研究多候选策略、生产只持有单一ETF`的准行业化系统：

- 研究层允许多个候选策略并行评估
- 治理层从候选策略中选出当前激活的生产策略
- 生产层始终只允许输出：
  - 持有一只 ETF
  - 保持当前持仓
  - 空仓
- 回测、研究、生产、执行共享统一交易语义
- 保持系统可解释、可审计、可测试

## 3. 非目标

本次设计不包含：

- 多ETF组合实盘持仓
- 黑盒 AI 直接决定下单
- 在线学习或自动参数自适应
- 高频或盘中交易

## 4. 顶层架构

系统划分为七个域：

### 4.1 数据域

负责：

- ETF 行情、基准、元数据、交易日历
- 数据新鲜度检查
- 缺口、停牌、异常成交过滤

### 4.2 特征域

负责生成统一特征快照 `FeatureSnapshot`，供所有候选策略复用。

建议首批特征：

- `momentum_20`
- `momentum_60`
- `momentum_120`
- `ma_distance_120`
- `ma_slope_20`
- `volatility_20`
- `drawdown_60`
- `relative_strength_vs_benchmark`
- `avg_amount_20`

### 4.3 候选策略域

每个候选策略只输出单一 ETF 建议，不参与执行。

统一输出对象：`StrategyProposal`

字段建议：

- `strategy_id`
- `trade_date`
- `target_etf`
- `score`
- `confidence`
- `risk_flags`
- `reason_codes`
- `debug_payload`

### 4.4 治理域

负责从多个候选策略中选择`当前激活的生产策略`。

统一输出对象：`GovernanceDecision`

字段建议：

- `effective_date`
- `active_strategy_id`
- `previous_strategy_id`
- `fallback_strategy_id`
- `candidate_rankings`
- `governance_score`
- `activation_reason`
- `switch_reason`
- `review_required`

### 4.5 生产决策域

负责把激活策略的建议加工成可执行的单ETF生产决策。

统一输出对象：`ProductionDecision`

字段建议：

- `trade_date`
- `target_etf`
- `action`
- `rebalance_required`
- `risk_gate_status`
- `blocked_reasons`

### 4.6 执行审计域

负责：

- 下单前检查
- 成交模拟
- 整手约束
- 手续费和滑点
- 执行记录
- 组合状态快照

### 4.7 研究与报告域

负责：

- 批量回测候选策略
- 生成 champion/challenger/fallback 分析
- 输出研究报告、日报、门户摘要

## 5. 两条主流程

### 5.1 研究流

1. 加载历史行情、基准、交易日历、ETF 元数据
2. 进行数据校验与特征计算
3. 多个候选策略并行产生每日 `StrategyProposal`
4. 统一成交模型回放执行
5. 治理层按滚动窗口评估候选策略
6. 输出 `GovernanceDecision`
7. 写入研究报告与治理记录

### 5.2 生产流

1. 读取当日行情与交易日历
2. 做数据新鲜度和可交易性检查
3. 生成当日 `FeatureSnapshot`
4. 读取当前激活策略
5. 生成单日 `StrategyProposal`
6. 经过数据闸门、风险闸门、信号稳定闸门、执行闸门
7. 输出 `ProductionDecision`
8. 转换为 `ExecutionIntent`
9. 执行或拒绝，并落库存档

## 6. 候选策略体系

首批建议落地四类候选策略：

### 6.1 TrendMomentumStrategy

现有策略的升级版，使用：

- 20/60/120 日动量
- MA 偏离
- 均线斜率

适合趋势明显的市场阶段。

### 6.2 RiskAdjustedMomentumStrategy

在动量基础上加入惩罚项：

- 波动率惩罚
- 回撤惩罚
- 流动性惩罚

目标是降低“高收益但脆弱”的标的被选中的概率。

### 6.3 DefensiveRotationStrategy

在风险环境变弱时优先：

- 红利
- 低波
- 防御型 ETF

若无合格标的，允许空仓。

### 6.4 RegimeAwareStrategy

先识别市场状态，再切换评分逻辑：

- 风险开：偏趋势/成长
- 风险中：偏低波/红利
- 风险关：空仓或防御

## 7. 治理层设计

采用：

- `Champion`
- `Challenger`
- `Fallback`

### 7.1 治理评估维度

- 收益能力：年化收益、超额收益
- 风险控制：最大回撤、波动率、恢复时长
- 执行可行性：换手、切换次数、成交可执行率
- 稳定性：滚动窗口胜率、样本外表现、参数敏感度
- 一致性：是否与生产交易规则一致

### 7.2 切换原则

- 不允许按单期收益即时切换
- challenger 必须在多个滚动窗口内稳定胜出
- champion 连续退化才允许被替换
- 若所有策略退化，则切换到 fallback 或空仓模式

## 8. 统一交易语义

这是本系统的强约束。

### 8.1 时间语义

统一定义：

- `signal_date`
- `decision_date`
- `execution_date`

默认规则：

- 月末最后一个交易日生成信号
- 下一个交易日执行
- 非调仓日仅允许 `HOLD`

### 8.2 成交语义

研究、回测、生产共用同一规则：

- 最小交易单位 `100 股`
- 手续费
- 不允许分数股
- 目标 ETF 当日无价格则不得成交
- 扣费后不足一手则不得成交

### 8.3 持仓语义

统一状态机：

- `CASH`
- `LONG_SINGLE_ETF(symbol)`

换仓必须：

- 先卖后买
- 卖出成功、买入失败时进入 `CASH`

### 8.4 数据语义

- 信号生成只允许使用 `signal_date` 及以前数据
- 执行成交只允许使用 `execution_date` 规则
- 若关键 ETF 数据缺失，必须阻断或降级

## 9. 统一服务

建议新增三类基础服务：

### 9.1 TradePolicy

统一定义：

- 调仓频率
- 执行延迟
- lot size
- fee rate
- slippage
- 风险闸门参数
- stale data policy

### 9.2 RebalanceScheduleService

统一负责：

- 计算调仓信号日
- 计算执行日
- 判断当日是否允许换仓

### 9.3 ExecutionSimulator

统一负责：

- 资金检查
- 整手约束
- 手续费/滑点
- 模拟成交结果

回测和生产都调用该服务，避免双套逻辑。

## 10. 分阶段落地路线

### Phase 1：统一可信语义

- 抽出 `TradePolicy`
- 抽出 `RebalanceScheduleService`
- 抽出 `ExecutionSimulator`
- 修复生产/回测调仓语义不一致
- 增加数据新鲜度、停牌、缺数闸门
- 测试改用临时数据库，避免影响真实库

### Phase 2：升级为候选策略工厂

- 新增 `FeatureSnapshot`
- 新增 `StrategyProposal`
- 现有策略改造成 `TrendMomentumStrategy`
- 新增 `RiskAdjustedMomentumStrategy`
- 新增 `DefensiveRotationStrategy`

### Phase 3：引入治理层

- 新增 `GovernanceDecision`
- 落地 champion/challenger/fallback
- 用滚动窗口和稳健性评分选择激活策略

### Phase 4：引入状态感知

- 新增 `RegimeAwareStrategy`
- 增加样本内/样本外、状态分层研究
- 升级研究报告与生产报告

## 11. 第一批推荐实施范围

第一批建议只做以下内容：

- 统一交易语义与测试隔离
- 建立 `TradePolicy`
- 建立 `RebalanceScheduleService`
- 建立 `ExecutionSimulator`
- 建立 `FeatureSnapshot`
- 建立 `StrategyProposal`
- 将现有逻辑重构为 `TrendMomentumStrategy`
- 新增 `RiskAdjustedMomentumStrategy`
- 生产侧继续强约束为“单一 ETF 或空仓”

明确不建议首批实施：

- 自动在线学习
- 组合实盘
- 黑盒 AI 下单
- 复杂状态机直接上线

## 12. 验收标准

完成首批实施后，系统至少应满足：

- 回测与生产使用相同的调仓与执行语义
- 生产侧严格限制为单ETF或空仓
- 研究侧可并行比较多个候选策略
- 能输出当前激活策略及其原因
- 测试不会污染真实数据库
- 日报和研究报告能够解释：
  - 为什么选这只 ETF
  - 为什么没有选其他 ETF
  - 当前风险闸门是否触发

## 13. 风险与注意事项

- 候选策略数量一开始不宜过多，否则治理层容易过拟合
- 状态识别逻辑必须做样本外验证，不能直接靠主观划分上线
- 防御策略需要补充更合适的防御资产池，否则“防御”会名不副实
- 治理层切换必须带滞后机制，否则会造成策略层面的频繁抖动
