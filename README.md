# ETF 动量轮动 + AI Agent 辅助系统 v0.1

基于设计文档实现的 ETF 动量轮动策略系统，集成 AI Agent 进行数据质量检查、风险监控和报告生成。

当前生产侧聚焦“单一 ETF 实盘持有”场景：每次只持有 1 只 ETF 或空仓。研究侧则可以并行比较多个候选策略，并把结果汇总进统一研究报告。

## 项目状态

当前已完成 Phase 1、Phase 2、Phase 3，并已接通日常闭环与研究线闭环。

### ✅ 已完成
- 项目骨架和配置文件
- 核心工具模块（配置加载、日志）
- 数据层（数据获取、标准化、交易日历、数据验证）
- 策略计算层（动量计算、趋势过滤、持仓选择、策略引擎）
- 存储层（SQLite 落盘、仓储接口）
- 回测模块
- Agent协作层（Data QA / Report / Research / Risk Monitor）
- 执行与风控层（订单检查、模拟执行、执行记录）
- 日常闭环（策略 -> Agent -> 检查 -> 执行 -> 报告）
- 研究线闭环（候选策略比较 -> ResearchAgent -> 研究报告）

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp config/.env.example config/.env
# 编辑 config/.env，填入你的 OPENAI_API_KEY
```

### 3. 配置策略参数

编辑以下配置文件：
- `config/strategy.yaml` - 策略参数
- `config/etf_pool.yaml` - ETF池
- `config/agent.yaml` - Agent配置
- `config/research.yaml` - 研究候选参数配置

### 4. 初始化数据库

```bash
python scripts/init_db.py
```

### 5. 运行回测

```bash
python scripts/run_backtest.py
```

### 6. 每日闭环运行

```bash
python scripts/daily_run.py --date 2026-03-11 --manual-approve --execute
```

### 7. 运行研究线

```bash
python scripts/run_research.py --start-date 2025-12-01 --end-date 2026-03-11
```

如需切换研究候选集合，可额外传入：

```bash
python scripts/run_research.py --candidate-config config/research.yaml
```

### 8. 汇总研究报告

```bash
python scripts/summarize_research_reports.py
```

默认会扫描 `reports/research/*.json`，并输出到 `reports/research/summary/`：
- `index.html`：可直接打开的研究历史总览页
- `research_summary.md`：适合人工阅读的汇总视图
- `research_summary.json`：适合后续页面或脚本消费的结构化摘要
- `research_reports.csv`：按报告维度汇总
- `research_candidates.csv`：按候选参数维度汇总

总览页当前已支持：
- 按候选筛选
- 按日期区间筛选
- 报告表 / 候选表按列排序

### 9. 统一门户入口

```bash
python scripts/build_report_portal.py
```

会生成：
- `reports/index.html`：日报与研究统一入口
- `reports/portal_summary.json`：门户结构化摘要

说明：
- 运行 `scripts/daily_run.py` 后会自动刷新统一门户
- 运行 `scripts/run_research.py` 或 `scripts/summarize_research_reports.py` 后也会自动刷新统一门户

## 项目结构

```
etf_agent_rotation/
├── config/                 # 配置文件
│   ├── strategy.yaml      # 策略配置
│   ├── etf_pool.yaml     # ETF池配置
│   ├── agent.yaml        # Agent配置
│   └── research.yaml     # 研究候选配置
├── src/                   # 源代码
│   ├── core/             # 核心工具
│   ├── data/             # 数据层
│   ├── strategy/         # 策略计算层
│   ├── agents/           # Agent协作层
│   ├── execution/        # 执行与风控层
│   ├── backtest/         # 回测模块
│   └── storage/          # 存储层
├── scripts/              # 脚本
├── tests/                # 测试
├── data/                 # 数据目录
└── reports/              # 报告输出
```

## 核心策略

### 动量评分
- 20日收益率权重：50%
- 60日收益率权重：50%
- 综合得分 = 0.5 × Return_20 + 0.5 × Return_60

### 趋势过滤
- 使用MA120作为趋势判断
- 只持有价格在MA120之上的ETF

### 持仓规则
- 生产默认只持有 1 只 ETF
- 选择得分最高且满足趋势条件的ETF
- 无合格标的时空仓

### 调仓周期
- 默认月度调仓
- 每月最后一个交易日计算信号
- 次一交易日执行

## Agent功能

### Data QA Agent
- 检查数据完整性
- 识别异常ETF
- 判断是否允许运行策略

### Report Agent
- 生成调仓报告
- 解释策略决策
- 输出Markdown格式

### Research Agent
- 对比多个候选策略及其参数组合
- 分析回测结果
- 提供优化建议

研究候选参数默认从 `config/research.yaml` 加载。每个 candidate 需显式声明 `strategy_id`，可直接增删候选组合，无需改动研究主流程代码。

### Risk Monitor Agent
- 监控实盘表现
- 计算回撤
- 识别异常状态

## 开发约束

1. 策略核心必须是显式规则引擎
2. Agent只做辅助，不掌控交易闭环
3. 生产与研究隔离
4. 先半自动，后自动
5. 先单策略，后多策略

## 下一步开发

1. 增加更完整的集成测试和样例数据
2. 增加统一门户里的跨日报/研究筛选能力
3. 增加跨日报/研究的统一指标卡与跳转
4. 完善文档

## 许可证

MIT License
