# ETF 动量轮动 + AI Agent 辅助系统设计文档 v0.1

## 1. 文档目标

本文档用于定义一个适合个人量化起步的交易研究与执行系统，核心策略为 **ETF 动量轮动**，AI Agent 通过 API 接入，承担数据检查、回测分析、风险监控、报告生成等辅助职责。

系统目标不是构建“自主交易 Agent”，而是构建一个：

- 策略规则清晰
- 回测与实盘一致性较高
- 可逐步演进
- 可与大模型 API 协同
- 适合 1 万级启动资金验证的最小可行系统

---

## 2. 设计原则

### 2.1 核心原则

系统必须遵循以下原则：

1. **策略核心规则化**  
   买卖信号由显式规则引擎生成，不由 Agent 自由决定。

2. **Agent 只做辅助，不掌控交易闭环**  
   Agent 负责解释、比较、监控、建议，不直接定义正式生产策略。

3. **生产与研究隔离**  
   实盘运行的生产策略必须冻结版本。参数研究与候选策略测试在独立研究线中完成。

4. **先半自动，后自动**  
   第一阶段推荐“自动算信号 + 人工确认执行”。不建议启动阶段直接全自动实盘下单。

5. **先做单策略，后做多策略**  
   v0.1 仅支持单一 ETF 动量轮动主策略，不引入多策略组合、复杂风控优化、强化学习等机制。

---

## 3. 目标用户与适用场景

### 3.1 目标用户

- 个人量化起步用户
- 小资金账户（例如 1 万级）
- 希望低频、可解释、可回测、可逐步自动化的用户

### 3.2 适用场景

- ETF 低频轮动
- 月频或双周频调仓
- 每日收盘后更新
- 次日人工确认执行或半自动执行

### 3.3 不适用场景

- 高频交易
- 涨停板情绪交易
- 盘中秒级博弈
- 复杂多资产实时套利
- Agent 自主交易决策

---

## 4. 系统范围

### 4.1 v0.1 范围内

- ETF 历史行情拉取
- ETF 池配置
- 动量打分
- 趋势过滤
- 持仓目标生成
- 回测执行
- 交易信号输出
- Agent 报告生成
- Agent 参数研究建议
- 数据质量检查
- 风险状态监控
- 版本记录

### 4.2 v0.1 范围外

- 自动实盘下单闭环
- 盘中实时监控
- 多账户统一管理
- 多策略组合引擎
- 自主参数上线
- 强化学习优化
- 全自动自我迭代

---

## 5. 整体架构

系统整体分为 5 层：

```text
数据层
→ 策略计算层
→ Agent 协作层
→ 执行与风控层
→ 存储与评估层
```

### 5.1 数据层

职责：

- 拉取 ETF 行情数据
- 拉取交易日历
- 拉取账户持仓与资金数据
- 数据标准化与清洗

### 5.2 策略计算层

职责：

- 计算动量得分
- 做趋势过滤
- 生成目标持仓
- 输出调仓信号

### 5.3 Agent 协作层

职责：

- 数据质量检查
- 参数比较与研究建议
- 风险状态分析
- 持仓与调仓报告生成

### 5.4 执行与风控层

职责：

- 订单合法性检查
- 最小交易单位处理
- 人工确认执行
- 半自动执行接口预留

### 5.5 存储与评估层

职责：

- 行情缓存
- 回测结果记录
- 策略版本管理
- Agent 输出日志
- 实盘表现跟踪

---

## 6. 核心策略定义

### 6.1 策略名称

ETF 动量轮动策略 v1

### 6.2 策略目标

在给定 ETF 池内，定期选择短中期动量更强且趋势条件满足的 ETF 持有；若无合格标的，则空仓或切入防御 ETF。

### 6.3 ETF 池

v0.1 使用配置文件管理 ETF 池，建议初始池控制在 4–6 只。

示例：

```yaml
etf_pool:
  - code: "510300"
    name: "沪深300ETF"
    category: "broad"
  - code: "510500"
    name: "中证500ETF"
    category: "broad"
  - code: "159915"
    name: "创业板ETF"
    category: "growth"
  - code: "515180"
    name: "红利ETF"
    category: "dividend"
```

可选增加：

- 纳指相关 ETF
- 债券/货币类防御 ETF

### 6.4 调仓周期

默认：**月度调仓**

说明：

- 每月最后一个交易日收盘后计算
- 下一交易日执行
- v0.1 只支持一个正式调仓周期，不做多周期并行

### 6.5 动量打分模型

默认评分公式：

```text
Score = 0.5 × Return_20 + 0.5 × Return_60
```

其中：

```text
Return_20 = Close_t / Close_t-20 - 1
Return_60 = Close_t / Close_t-60 - 1
```

设计说明：

- 20 日动量反映短期强弱
- 60 日动量反映中期趋势
- 双窗口比单窗口更稳
- v0.1 不引入波动率调整和复杂因子

### 6.6 趋势过滤

默认规则：

```text
Close_t > MA120
```

如果某 ETF 不满足趋势过滤，则不能成为目标持仓。

设计说明：趋势过滤用于避免在系统性弱势中持有“跌得最少”的风险资产。

### 6.7 持仓规则

#### 规则 1：目标持仓数

默认只持有 **1 只 ETF**。

#### 规则 2：选取逻辑

- 对 ETF 池计算 Score
- 过滤掉不满足趋势条件的 ETF
- 在剩余 ETF 中选取 Score 最高者

#### 规则 3：无合格标的

若最高得分 ETF 也不满足趋势条件，则：

- 方案 A：空仓
- 方案 B：切换防御 ETF

v0.1 推荐先支持方案 A，方案 B 作为后续可配置扩展。

### 6.8 调仓信号

若当前持仓与目标持仓不同，则生成调仓信号：

```text
SELL current_position
BUY target_position
```

若当前持仓等于目标持仓，则输出：

```text
HOLD
```

若目标为空仓，则输出：

```text
SELL current_position
MOVE_TO_CASH
```

---

## 7. Agent 协作层设计

Agent 不直接改策略规则。其职责限定为：检查、比较、解释、建议。

推荐设置 4 个 Agent。

### 7.1 Data QA Agent

#### 目标

检查数据是否可用于策略计算。

#### 输入

- 最新 ETF 行情数据
- 历史缓存数据
- 交易日历
- 数据源状态信息

#### 输出

- 数据完整性结论
- 异常 ETF 列表
- 缺失日期
- 异常跳变说明
- 是否允许进入策略计算

#### 典型输出示例

```json
{
  "status": "warning",
  "issues": [
    {
      "code": "159915",
      "issue": "missing_close_price",
      "date": "2026-03-12"
    }
  ],
  "allow_strategy_run": false
}
```

### 7.2 Research Agent

#### 目标

对候选参数组合进行研究与比较，输出建议，但不直接上线。

#### 输入

- 回测结果表
- 参数配置列表
- 研究窗口设定
- 当前生产策略版本

#### 输出

- 候选参数排名
- 与生产版的差异说明
- 收益与回撤比较
- 是否疑似过拟合
- 推荐研究方向

#### 典型职责

- 比较 20/60 vs 20/90
- 比较月频 vs 双周频
- 比较 MA120 vs MA90
- 比较空仓 vs 防御 ETF

### 7.3 Risk Monitor Agent

#### 目标

监控生产策略近期表现，识别异常状态。

#### 输入

- 实盘净值序列
- 基准净值序列
- 最近信号记录
- 账户状态
- 当前回撤信息

#### 输出

- 风险等级
- 是否触发人工复核
- 异常原因说明
- 风险提示

#### 风险等级建议

- green：正常
- yellow：轻度异常
- orange：需复核
- red：暂停执行

### 7.4 Report Agent

#### 目标

把策略结果转为可读报告，方便人工确认与复盘。

#### 输入

- 最新策略结果
- 当前持仓
- 目标持仓
- ETF 得分表
- 风险状态

#### 输出

- 本次是否调仓
- 调仓原因说明
- 当前持仓解释
- 风险状态摘要
- 简版日报 / 周报 / 月报

#### 示例输出

```text
本期建议：调仓
当前持仓：沪深300ETF
目标持仓：中证500ETF

原因：
1. 中证500ETF 的综合动量得分最高
2. 当前价格高于 MA120，满足趋势过滤
3. 沪深300ETF 得分下降至第二位

当前风险状态：正常
数据状态：正常
```

---

## 8. 生产线与研究线分离

这是系统的硬约束。

### 8.1 生产线

职责：

- 运行正式策略版本
- 生成正式交易信号
- 记录正式净值与持仓

约束：

- 参数冻结
- ETF 池冻结
- 仅人工批准可升级

### 8.2 研究线

职责：

- 跑候选参数组合
- 输出研究建议
- 识别可能的优化方向

约束：

- 不直接影响生产策略
- 不自动改实盘参数
- 研究结果只作为候选建议

---

## 9. 数据流设计

推荐数据流如下：

```text
Market API / Broker API
→ ETL 标准化
→ 本地数据库
→ 策略引擎
→ 结果表
→ Agent API 输入摘要
→ Agent 输出建议/报告
→ 人工确认
→ 执行记录
```

关键点：

1. Agent 不直接读取原始脏数据  
2. Agent 输入应为结构化摘要  
3. 下单前必须经过规则检查和人工确认  
4. 全部过程需留痕

---

## 10. 模块划分

推荐项目目录结构如下：

```text
etf_agent_rotation/
├─ config/
│  ├─ strategy.yaml
│  ├─ etf_pool.yaml
│  └─ agent.yaml
├─ data/
│  ├─ fetch_market_data.py
│  ├─ fetch_account_data.py
│  ├─ normalize_data.py
│  └─ trading_calendar.py
├─ strategy/
│  ├─ momentum_score.py
│  ├─ trend_filter.py
│  ├─ portfolio_selector.py
│  └─ signal_engine.py
├─ agents/
│  ├─ data_qa_agent.py
│  ├─ research_agent.py
│  ├─ risk_monitor_agent.py
│  └─ report_agent.py
├─ execution/
│  ├─ order_checker.py
│  ├─ broker_api.py
│  └─ rebalance_executor.py
├─ backtest/
│  ├─ run_backtest.py
│  ├─ compare_params.py
│  └─ evaluate.py
├─ storage/
│  ├─ db.py
│  ├─ models.py
│  └─ repositories.py
├─ reports/
│  └─ render_report.py
├─ main.py
└─ README.md
```

---

## 11. 核心配置文件设计

### 11.1 strategy.yaml

```yaml
strategy:
  name: "etf_momentum_v1"
  rebalance_frequency: "monthly"
  hold_count: 1
  score_formula:
    return_20_weight: 0.5
    return_60_weight: 0.5
  trend_filter:
    enabled: true
    ma_period: 120
  defensive_mode:
    enabled: false
    defensive_etf: null
  allow_cash: true
```

### 11.2 etf_pool.yaml

```yaml
etf_pool:
  - code: "510300"
    name: "沪深300ETF"
    enabled: true
  - code: "510500"
    name: "中证500ETF"
    enabled: true
  - code: "159915"
    name: "创业板ETF"
    enabled: true
  - code: "515180"
    name: "红利ETF"
    enabled: true
```

### 11.3 agent.yaml

```yaml
agents:
  data_qa:
    enabled: true
    model: "gpt"
  research:
    enabled: true
    model: "gpt"
  risk_monitor:
    enabled: true
    model: "gpt"
  report:
    enabled: true
    model: "gpt"

constraints:
  allow_agent_modify_production_strategy: false
  allow_agent_execute_order: false
```

---

## 12. 数据库表设计建议

v0.1 可使用 SQLite。

### 12.1 market_price

存储 ETF 历史行情。

字段建议：

- id
- symbol
- trade_date
- open
- high
- low
- close
- volume
- amount
- source
- created_at

### 12.2 strategy_signal

存储每次策略输出。

字段建议：

- id
- strategy_version
- trade_date
- current_position
- target_position
- rebalance_flag
- signal_type
- score_snapshot_json
- created_at

### 12.3 backtest_run

存储回测运行记录。

字段建议：

- id
- strategy_name
- parameter_snapshot_json
- start_date
- end_date
- annual_return
- max_drawdown
- sharpe
- turnover
- created_at

### 12.4 agent_log

存储 Agent 输出记录。

字段建议：

- id
- agent_name
- input_summary_json
- output_text
- status
- created_at

### 12.5 portfolio_state

存储账户持仓快照。

字段建议：

- id
- trade_date
- cash
- holding_symbol
- holding_shares
- total_asset
- nav
- created_at

---

## 13. 策略引擎接口设计

### 13.1 输入

- 最新历史行情
- ETF 池配置
- 策略配置
- 当前持仓状态

### 13.2 输出

建议统一为结构化对象：

```json
{
  "trade_date": "2026-03-12",
  "strategy_version": "etf_momentum_v1",
  "rebalance": true,
  "current_position": "510300",
  "target_position": "510500",
  "scores": [
    {"code": "510300", "score": 0.042, "above_ma": true},
    {"code": "510500", "score": 0.068, "above_ma": true},
    {"code": "159915", "score": 0.031, "above_ma": false}
  ],
  "risk_mode": "normal"
}
```

---

## 14. Agent API 输入输出约束

### 14.1 输入原则

- 不传长原始行情表
- 只传结构化摘要
- 输入字段固定化
- 限制 Agent 自由解释范围

### 14.2 输出原则

- 输出必须模板化
- 不能直接输出下单指令
- 不能修改正式参数
- 必须可记录、可审计

---

## 15. 执行层设计

v0.1 推荐采用 **半自动执行**。

执行流程：

```text
收盘后跑策略
→ Agent 生成解释
→ 人工确认
→ 执行下单
→ 记录成交结果
```

### 执行前检查项

- 当前是否调仓日
- 目标 ETF 是否在白名单中
- 买入金额是否满足最小交易单位
- 当前账户资金是否足够
- 是否触发暂停执行标记

---

## 16. 回测模块设计

回测模块职责：

- 模拟月度调仓
- 计算净值曲线
- 输出关键指标
- 支持参数对比

### 基础输出指标

- 年化收益
- 最大回撤
- 夏普比率
- 调仓次数
- 胜率
- 收益回撤比

### 回测注意事项

- 使用与生产一致的数据源口径
- 使用实际交易日历
- 模拟手续费
- 不做过度参数搜索
- 记录每次回测参数快照

---

## 17. 风险控制设计

v0.1 风控以“简单、刚性”为原则。

### 17.1 策略级风控

- 无合格标的时允许空仓
- 趋势过滤失效时禁止持仓
- 仅允许 1 个正式目标持仓

### 17.2 执行级风控

- 禁止买入非白名单 ETF
- 禁止超额下单
- 禁止非调仓日随意调仓

### 17.3 系统级风控

- 数据异常时禁止跑正式信号
- Agent 输出异常时不影响策略核心信号
- 生产与研究隔离

---

## 18. 版本管理机制

### 18.1 正式策略版本

例如：

```text
etf_momentum_v1
etf_momentum_v1_1
```

### 18.2 升级流程

1. 研究线生成候选版本  
2. 跑样本外验证  
3. 输出研究报告  
4. 人工审核  
5. 升级生产版本

### 18.3 禁止事项

- Agent 自动升级生产版
- 生产参数每日漂移
- 无审计直接改策略核心

---

## 19. 开发优先级建议

### Phase 1：最小可行版本

目标：先把规则策略跑通。

范围：

- ETF 数据拉取
- 策略配置
- 动量打分
- 趋势过滤
- 调仓信号生成
- 简单回测
- SQLite 落盘

### Phase 2：Agent 报告层

目标：提高可读性和复盘效率。

范围：

- Report Agent
- Data QA Agent
- 简单日报输出

### Phase 3：研究线

目标：建立受控迭代能力。

范围：

- Research Agent
- 参数对比
- 研究报告
- 候选版本管理

### Phase 4：风险与执行增强

目标：增强系统稳健性。

范围：

- Risk Monitor Agent
- 执行前检查
- 半自动接口预留

---

## 20. 对 Claude Code 的开发约束建议

你可以直接把下面这段作为开发约束发给 Claude Code。

### Claude Code 开发约束提示词（建议版）

请基于以下约束设计并实现系统，不要擅自引入超出范围的复杂架构：

1. 本项目是“ETF 动量轮动 + AI Agent 辅助系统”，不是自主交易 Agent。  
2. 策略核心必须是显式规则引擎，不允许由 Agent 自由决定买卖逻辑。  
3. v0.1 仅支持：  
   - 4–6 只 ETF 池  
   - 月度调仓  
   - 单持仓  
   - 20 日 + 60 日动量加权评分  
   - MA120 趋势过滤  
4. Agent 只负责：  
   - 数据质量检查  
   - 参数研究比较  
   - 风险监控  
   - 调仓报告生成  
5. 生产线和研究线必须隔离。  
6. 不允许 Agent 自动修改生产策略参数。  
7. 不允许 Agent 直接下单。  
8. 先实现最小可行版本，优先保证：  
   - 结构清晰  
   - 配置驱动  
   - SQLite 可落盘  
   - 回测与生产逻辑共用核心规则  
9. 代码目录请按模块分层，不要写成单文件脚本。  
10. 预留 API 接入能力，但 v0.1 不强依赖真实券商接口。

请先输出：

- 项目目录结构
- 核心模块职责说明
- 配置文件样例
- SQLite 表结构
- 主流程时序
- v0.1 开发任务拆分清单

---

## 21. 我对 v0.1 的建议取舍

推荐取舍：

**先不要做复杂多 Agent 编排，也不要先接券商实盘。**  
v0.1 的重点只有三件事：

- 把规则策略跑通
- 把 Agent 辅助层接起来
- 把研究与生产边界立住

这样后面扩展才不会乱。

---

## 22. 下一步最小动作

现在最适合让 Claude Code 先做这 4 件事：

1. 搭项目骨架与配置文件  
2. 实现 ETF 动量轮动规则引擎  
3. 实现 SQLite 表结构与落盘  
4. 实现 Report Agent 和 Data QA Agent 的输入输出骨架

等这四步完成，再谈 Research Agent 和 Risk Monitor Agent。

