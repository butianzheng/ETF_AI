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
python scripts/etf_ops.py daily run --date 2026-03-11 --manual-approve --execute
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

### 10. 治理自动化、发布与回退

```bash
python scripts/etf_ops.py research-governance run --start-date 2025-12-01 --end-date 2026-03-24
python scripts/etf_ops.py research-governance run --start-date 2025-12-01 --end-date 2026-03-24 --fail-on-blocked

python scripts/run_research.py --start-date 2025-12-01 --end-date 2026-03-11
python scripts/summarize_research_reports.py
python scripts/run_governance_cycle.py --summary reports/research/summary/research_summary.json
python scripts/run_governance_review.py --summary reports/research/summary/research_summary.json
python scripts/publish_governance_decision.py --decision-id 1 --approved-by your_name
python scripts/check_governance_health.py --report-dir reports/daily
python scripts/rollback_governance_decision.py --approved-by your_name --reason "manual rollback"
```

说明：
- 推荐优先使用 `python scripts/etf_ops.py research-governance run ...` 一次串联研究、汇总、governance cycle 与门户刷新
- `--fail-on-blocked` 会在出现 blocked/fatal error 时以非零码退出，方便 CI 门禁
- 推荐顺序是：研究 -> 汇总 -> governance cycle -> 人工确认 publish -> health check
- `run_governance_cycle.py` 会复用治理评估逻辑，生成/去重 draft，并给出 `ready/blocked` review 状态
- `run_governance_review.py` 会根据研究汇总结果生成治理 draft，并写入 `reports/governance/`
- `publish_governance_decision.py` 会把指定 draft 审批并发布到生产运行时
- `check_governance_health.py` 会扫描日报与已发布策略，输出 incident 和 rollback recommendation
- `rollback_governance_decision.py` 会把生产策略回退到上一稳定策略或 fallback
- 单一 ETF 实盘场景下默认不启用自动 publish，最终切换仍保留人工门禁

### 11. 统一端到端编排入口

默认安全模式：

```bash
python scripts/etf_ops.py workflow run --start-date 2025-12-01 --end-date 2026-03-24
```

说明：
- 默认只执行 `research-governance + pre-publish health check`
- 默认不跑 daily
- 默认不 publish

仅执行预检（常用于 CI 或快速确认输入参数/目录结构是否可用）：

```bash
python scripts/etf_ops.py workflow preflight \
  --start-date 2025-12-01 \
  --end-date 2026-03-24
```

如需把 daily 纳入同一入口：

```bash
python scripts/etf_ops.py workflow run \
  --start-date 2025-12-01 \
  --end-date 2026-03-24 \
  --run-daily \
  --daily-date 2026-03-24 \
  --daily-manual-approve \
  --daily-execute \
  --daily-available-cash 100000
```

如需显式授权发布：

```bash
python scripts/etf_ops.py workflow run \
  --start-date 2025-12-01 \
  --end-date 2026-03-24 \
  --publish \
  --approved-by your_name
```

说明：
- 只有 `--publish --approved-by <name>` 才会执行 publish
- 若治理结果是 `blocked`，即使显式传了 `--publish` 也会跳过发布，并在 summary 中写入 `publish_blocked_reason`
- publish 成功后会自动再跑一次 post-publish health check

输出与退出码：
- per-run manifest（推荐自动化消费）写到：`reports/workflow/runs/<run_id>/workflow_manifest.json`
- legacy summary（兼容旧路径，永远覆盖为“最近一次运行”）写到：`reports/workflow/end_to_end_workflow_summary.json`
- `stdout` 合同（稳定字段，方便 CI 解析）：
  - `run_id=<run_id>`
  - `workflow_manifest=<manifest_path>`
  - `workflow_status=<status>`
  - `publish_executed=true|false`
- `workflow_status` 枚举值：
  - `preflight_only`：仅预检完成（未执行 daily / research-governance / health / publish）
  - `succeeded`：完整流程成功（未 blocked）
  - `blocked`：治理结果为 blocked（是否退出码为 2 取决于是否启用 `--fail-on-blocked`）
  - `failed`：预检失败或任一阶段 fatal error
- `exit_code=0`：成功，或 `blocked` 但未启用 `--fail-on-blocked`
- `exit_code=2`：`blocked` 且启用了 `--fail-on-blocked`
- `exit_code=1`：fatal，包括 `preflight`、`research-governance`、`health check`、`publish`、`post-publish health check`
- manifest / summary JSON 内会同时保留：`health_check_result`（publish 前）、`post_publish_health_check_result`（publish 后，若执行）、`publish_result`

### 12. 本地自动化包装入口（Local Workflow Automation Wrapper）

```bash
python scripts/etf_ops.py automation run -- --preflight-only
python scripts/etf_ops.py automation run --workdir /tmp/workflow_job -- --start-date 2025-12-01 --end-date 2026-03-24
```

说明：
- wrapper 通过真实子进程调用 `scripts/run_end_to_end_workflow.py`，不复制业务编排逻辑
- `--workdir` 控制 runner 进程的工作目录（cwd）；当 `workdir != repo root` 时，会自动准备 `config -> <repo>/config` 符号链接，保证配置解析路径一致
- `automation run` 未显式传 `--workdir` 时，产物默认写到 repo root 下的 `reports/workflow/**`
- `--` 后面的参数会原样透传给 runner（例如 `--preflight-only`、`--fail-on-blocked`、`--publish` 等）

### 13. 快速查看最近一次工作流状态

```bash
python scripts/etf_ops.py status latest
python scripts/etf_ops.py status latest --json
python scripts/etf_ops.py status latest --workdir /tmp/workflow_job --json
```

说明：
- `status latest` 默认读取当前工作目录下的 `reports/workflow/**` 产物
- 若在 repo 外执行了 `automation run`，建议显式传 `--workdir <dir>` 固定产物目录；后续查询状态时也传同一个 `--workdir <dir>`，否则可能读取到错误目录
- 当自动化运行使用 `python scripts/etf_ops.py automation run --workdir <dir> ...` 时，状态查询应使用同一个 `<dir>`：`python scripts/etf_ops.py status latest --workdir <dir>`
- 状态读取优先级：`reports/workflow/automation/latest_run.json`，不存在时回退到 `reports/workflow/end_to_end_workflow_summary.json`

### 14. 旧脚本兼容入口（保留）

以下脚本仍可继续使用，当前作为兼容入口保留，`--help` 会提示迁移到统一入口：
- `python scripts/daily_run.py ...`
- `python scripts/run_end_to_end_workflow.py ...`
- `python scripts/run_workflow_automation.py ...`
- `python scripts/run_research_governance_pipeline.py ...`

自动化产物目录（固定，相对 `--workdir` 解析；未显式传 `--workdir` 时等于 repo root）：
- `reports/workflow/automation/run_history.jsonl`：历史运行索引（append-only）
- `reports/workflow/automation/latest_run.json`：最近一次 wrapper 运行快照（每次运行都会更新）
- `reports/workflow/automation/latest_attention.json|md`：最近一次“需人工关注”摘要，仅在 `blocked`、`failed`、`automation_contract_error` 时刷新
- `reports/workflow/automation/runs/<automation_run_id>/runner_stdout.log|runner_stderr.log`：runner 原始日志

`latest_run.json` 与 `latest_attention.*` 区别：
- `latest_run.json` 记录“最后一次运行”事实，不区分成功或失败
- `latest_attention.*` 只记录“最后一次需人工介入”的事件；成功运行不会清空旧 attention 文件

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
