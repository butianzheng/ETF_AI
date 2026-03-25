# ETF AI 系统开发任务清单

## Phase 1: 项目骨架与核心引擎 ✅

### T1.1 项目初始化 ✅
- [x] 创建项目目录结构
- [x] 创建 requirements.txt
- [x] 创建 pyproject.toml
- [x] 配置 .gitignore

### T1.2 配置文件 ✅
- [x] 创建 config/strategy.yaml
- [x] 创建 config/etf_pool.yaml
- [x] 创建 config/agent.yaml
- [x] 创建 config/.env.example
- [x] 实现配置验证 (Pydantic models)

### T1.3 数据层 ✅
- [x] 实现 src/data/fetcher.py
- [x] 实现 src/data/normalizer.py
- [x] 实现 src/data/calendar.py
- [x] 实现 src/data/validator.py

### T1.4 策略计算层 ✅
- [x] 实现 src/strategy/momentum.py
- [x] 实现 src/strategy/trend_filter.py
- [x] 实现 src/strategy/selector.py
- [x] 实现 src/strategy/engine.py

### T1.5 存储层 ✅
- [x] 实现 src/storage/database.py
- [x] 实现 src/storage/models.py (5张表)
- [x] 实现 src/storage/repositories.py
- [x] 创建 scripts/init_db.py

### T1.6 回测模块 ✅
- [x] 实现 src/backtest/engine.py
- [x] 实现 src/backtest/evaluator.py
- [x] 实现 src/backtest/comparator.py
- [x] 创建 scripts/run_backtest.py

### T1.7 主入口 ✅
- [x] 实现 src/main.py
- [x] 创建 scripts/daily_run.py

## Phase 2: Agent协作层 📋

### T2.1 Agent基础设施
- [x] 实现 src/agents/llm_client.py
- [x] 实现 src/agents/base.py

### T2.2 Data QA Agent
- [x] 实现 src/agents/data_qa.py
- [x] 设计输入输出结构
- [x] 编写提示词模板

### T2.3 Report Agent
- [x] 实现 src/agents/report.py
- [x] 设计输入输出结构
- [x] 编写Markdown报告生成逻辑

### T2.4 Research Agent
- [x] 实现 src/agents/research.py
- [x] 设计输入输出结构
- [x] 编写参数对比分析逻辑

### T2.5 Risk Monitor Agent
- [x] 实现 src/agents/risk_monitor.py
- [x] 设计输入输出结构
- [x] 编写风险评估逻辑

## Phase 3: 执行与风控层 📋

### T3.1 执行模块
- [x] 实现 src/execution/checker.py
- [x] 实现 src/execution/executor.py

### T3.2 风控规则
- [x] 实现白名单检查
- [x] 实现最小交易单位检查
- [x] 实现资金充足性检查

## 验证标准

### Phase 1 验证
- [x] 项目可正常导入运行
- [x] 配置文件正确加载
- [x] 可拉取ETF历史数据
- [x] 策略引擎输出正确信号
- [x] 回测结果符合预期
- [x] 数据正确存储到SQLite

### Phase 2 验证
- [x] DataQA Agent正确识别数据问题
- [x] Report Agent生成可读报告
- [x] Research Agent可对比参数
- [x] Risk Monitor Agent正确评估风险

### Phase 3 验证
- [x] 订单检查通过合法订单
- [x] 订单检查拒绝非法订单
- [x] 执行器正确记录执行结果

## 当前进度

- ✅ 已完成：Phase 1 的 T1.1-T1.7（实现层）
- ✅ 已完成：Phase 1 验证
- ✅ 已完成：Phase 2 Agent 协作层
- ✅ 已完成：Phase 3 执行与风控层

## 2026-03-24 Phase 5 治理状态门禁规划

- [x] 完成 Phase 5 设计 spec
- [x] 完成 Phase 5 implementation plan
- [x] 按计划开始实现配置与 evidence 持久化
- [x] 按计划实现 `regime gate` 判定与实时状态重算
- [x] 按计划完成治理自动化集成与聚焦回归

### 规划产物

- Spec: `docs/superpowers/specs/2026-03-24-phase-five-regime-aware-governance-gate-design.md`
- Plan: `docs/superpowers/plans/2026-03-24-phase-five-regime-aware-governance-gate-implementation.md`

### 完成结果

- Task 1 提交：`b1185a9`、`deb47d0`
- Task 2 提交：`a371acc`
- Task 3 提交：`3aee5a3`
- Task 4 提交：`3659874`、`612c1e2`、`58c1d7d`、`c6c8ac9`
- Task 4 spec compliance review：已通过
- Task 4 code quality review：已通过
- 聚焦回归：`pytest tests/test_governance_repository.py tests/test_governance_regime_gate.py tests/test_governance_automation.py tests/test_governance_runtime.py -q` 通过（`35 passed`）

## 2026-03-24 Research-To-Governance 统一编排

### 执行清单（立项）
- [ ] 统一编排服务
- [ ] blocked / fatal error 语义
- [ ] 统一编排 CLI
- [ ] 文档与验证

### 当前状态（已完成）
- [x] 统一编排服务
- [x] blocked / fatal error 语义
- [x] 统一编排 CLI
- [x] 文档与验证

### Task 1/2/3/4 完成与审查
- Task 1（统一编排服务）完成：`a5955a6`、`be381bf`、`23c485e`
- Task 2（blocked / fatal error 语义）完成：`1e7bf20`、`c85b5a9`、`f5bfc22`
- Task 3（统一编排 CLI）完成：`825fe92`、`436769f`
- Task 4（文档与任务跟踪）完成：本次提交
- 审查状态：Task 1/2/3 代码审查通过；Task 4 文档一致性与路径准确性自审通过

### 验证结果
- 聚焦回归：`pytest tests/test_research_governance_pipeline.py tests/test_governance_automation.py -q` 通过（`24 passed in 1.09s`）

## 2026-03-25 Research-To-Governance CLI Smoke

### 执行清单（立项）
- [x] happy path smoke
- [x] blocked smoke 与退出码语义
- [x] fatal smoke 与 partial pipeline summary
- [x] 聚焦回归与审查

### 规划产物

- Spec: `docs/superpowers/specs/2026-03-24-research-governance-cli-smoke-design.md`
- Plan: `docs/superpowers/plans/2026-03-24-research-governance-cli-smoke-implementation.md`

### 完成结果

- Task 1（happy path smoke）提交：`69157e4`
- Task 2（blocked smoke）提交：`f12cbfe`、`51889d6`
- Task 3（fatal smoke）提交：`567c3d0`
- 审查状态：
  - Task 1 spec compliance review：已通过
  - Task 1 code quality review：已通过
  - Task 2 spec compliance review：已通过
  - Task 2 code quality review：修复后已通过
  - Task 3 spec compliance review：已通过
  - Task 3 code quality review：已通过

### 验证结果

- Task 2 fresh 验证：`pytest tests/test_research_governance_pipeline_cli_smoke.py -q -k "smoke_blocked"` 通过（`2 passed, 1 deselected`）
- Task 3 fresh 验证：`pytest tests/test_research_governance_pipeline_cli_smoke.py -q -k "smoke_fatal"` 通过（`1 passed, 3 deselected`）
- smoke 全量：`pytest tests/test_research_governance_pipeline_cli_smoke.py -q` 通过（`4 passed`）
- 聚焦回归：`pytest tests/test_research_governance_pipeline.py tests/test_research_governance_pipeline_cli_smoke.py -q` 通过（`16 passed`）

## 2026-03-25 B 子项目：shared candidate-config helper 收尾

### 执行清单（Task 4）
- [x] 更新任务跟踪（spec/plan、Task 1/2/3 提交、审查状态、验证结果）
- [x] 将下一步行动从 B 子项目切换到后续端到端/文档工作
- [x] 完成最终聚焦回归

### 规划产物

- Spec: `docs/superpowers/specs/2026-03-25-shared-candidate-config-helper-design.md`
- Plan: `docs/superpowers/plans/2026-03-25-shared-candidate-config-helper-implementation.md`

### 完成结果

- Task 1（共享生产 helper 与解析边界测试）提交：`d9bd752`
- Task 2（CLI 切换共享 helper 与 wiring test）提交：`ac1ca79`
- Task 3（tests/support helper 收敛）提交：`f2df7f7`
- 审查状态：Task 1/2/3 已通过审查；Task 4 文档一致性与路径准确性自审通过

### 关键验证

- 最终聚焦回归：`pytest tests/test_research_pipeline.py tests/test_research_governance_pipeline.py tests/test_research_governance_pipeline_cli_smoke.py -q` 通过（`24 passed in 1.41s`）

## 2026-03-25 End-to-End Workflow Runner

### 执行清单（立项）
- [x] Task 1：编排脚本骨架、参数校验与默认 no-publish
- [x] Task 2：blocked / fatal / summary 语义与退出码优先级
- [x] Task 3：可选 daily / publish / post-publish health
- [x] Task 4：README / 任务跟踪 / 最终聚焦回归

### 规划产物

- Spec: `docs/superpowers/specs/2026-03-25-end-to-end-workflow-runner-design.md`
- Plan: `docs/superpowers/plans/2026-03-25-end-to-end-workflow-runner-implementation.md`

### 当前进度

- Task 1 初始提交：`6e58b30`
- Task 1 修复提交：`fa44bdd`
- Task 2 初始提交：`46b794b`
- Task 2 修复提交：`7a8012c`
- Task 3 提交：`5726e79`
- 审查状态：
  - Task 1 spec compliance review：已通过
  - Task 1 code quality review：修复后已通过
  - Task 2 spec compliance review：修复后已通过
  - Task 2 code quality review：修复后已通过
  - Task 3 spec compliance review：修复后已通过
  - Task 3 code quality review：修复后已通过
- fresh 验证：
  - Task 1：`pytest tests/test_end_to_end_workflow_runner.py -q` 通过（`4 passed in 0.65s`）
  - Task 2：`pytest tests/test_end_to_end_workflow_runner.py -q` 通过（`9 passed in 0.69s`）
  - Task 3：`pytest tests/test_end_to_end_workflow_runner.py -q` 通过（`12 passed in 0.63s`）
  - Task 4：`pytest tests/test_end_to_end_workflow_runner.py tests/test_research_governance_pipeline.py tests/test_research_governance_pipeline_cli_smoke.py tests/test_pipeline_e2e.py -q` 通过（`33 passed in 1.04s`）

## 后续阶段建议（已完成）

1. 将 stdout 合同与 per-run manifest 作为 CI artifact，替代依赖 legacy summary 覆盖语义
2. 进入“运营化与联调闭环”阶段，补齐 preflight/manifest/stdout 合同与聚焦回归
3. 基于 runner 的结果做可观测性与告警（按 `run_id` 定位 manifest、health report、pipeline summary）

## 2026-03-25 Workflow Runner 运营化与联调闭环

### 执行清单（立项）
- [x] 完成设计 spec
- [x] 完成 implementation plan
- [x] Task 1：preflight 辅助模块与失败语义
- [x] Task 2：run_id / per-run manifest / legacy summary 兼容
- [x] Task 3：自动化 stdout 合同与 runner smoke
- [x] Task 4：更新 README / tasks + 最终聚焦回归 + 提交收口

### 规划产物

- Spec: `docs/superpowers/specs/2026-03-25-workflow-runner-operationalization-design.md`
- Plan: `docs/superpowers/plans/2026-03-25-workflow-runner-operationalization-implementation.md`

### 审查状态

- Spec review：已通过
- Plan review：已通过

### Task 1/2/3 完成与验证（事实记录）

- Task 1 提交：`c41f7f0`、`b69b26a`
- Task 1 spec review：通过
- Task 1 code review：修复后通过
- Task 1 fresh 验证：`pytest tests/test_workflow_preflight.py tests/test_end_to_end_workflow_runner.py -q -k "preflight or blocked_stdout_status"` -> `9 passed, 12 deselected in 0.71s`

- Task 2 提交：`f39d1a5`
- Task 2 spec review：通过
- Task 2 code review：通过
- Task 2 fresh 验证：`pytest tests/test_workflow_manifest.py tests/test_end_to_end_workflow_runner.py -q -k "run_id or manifest"` -> `4 passed, 16 deselected in 0.58s`

- Task 3 提交：`a930827`
- Task 3 spec review：通过
- Task 3 code review：通过
- Task 3 fresh 验证：`pytest tests/test_end_to_end_workflow_runner.py tests/test_end_to_end_workflow_runner_cli_smoke.py -q` -> `18 passed in 0.66s`

### Task 4 目标与记录

- 目标：补齐 README（`--preflight-only` 示例、stdout 合同、per-run manifest vs legacy summary、`workflow_status` 枚举值），并同步 `tasks/todo.md` 最终状态
- 最终聚焦回归：
  - 命令：`pytest tests/test_workflow_preflight.py tests/test_workflow_manifest.py tests/test_end_to_end_workflow_runner.py tests/test_end_to_end_workflow_runner_cli_smoke.py tests/test_research_governance_pipeline.py tests/test_research_governance_pipeline_cli_smoke.py tests/test_pipeline_e2e.py -q`
  - 结果：通过（`47 passed in 1.32s`）
- Task 4 提交链：
  - 初始提交：`0c4ffcf`（`docs: add workflow runner operationalization plan`）
  - 后续修订：`01bd729`（`docs: fix workflow runner docs per review`）、`be69ac5`（`docs: update workflow runner task tracking`）、`a16baa9`（`docs: refresh workflow runner regression record`）、`b307d28`（`docs: complete workflow runner task4 commit chain`）
  - 说明：任务跟踪的“自更新提交”不在同一提交内自指记录；如有后续跟踪刷新，以 `git log` 为准。

## 2026-03-25 ETF Ops 单一总入口 CLI

### 执行清单（立项）
- [ ] Task 1：新增总入口 CLI 骨架、共享 adapter 与命令树
- [ ] Task 2：落地 `status latest` 读取、归一化与输出
- [ ] Task 3：旧脚本薄兼容层与共享 adapter 收敛
- [ ] Task 4：README / tasks 更新与最终聚焦回归

### 规划产物

- Spec: `docs/superpowers/specs/2026-03-25-etf-ops-unified-cli-design.md`
- Plan: `docs/superpowers/plans/2026-03-25-etf-ops-unified-cli-implementation.md`

### 审查状态

- Spec review：已通过
- Plan review：已通过

## 下一步行动（切到后续阶段建议）

1. 在 CI/自动化里解析 stdout 合同，按 `workflow_manifest` 收集 per-run JSON 作为 artifact（避免依赖 legacy summary 覆盖语义）
2. 将 per-run manifest 接入可观测性与问题定位链路（失败/blocked 的 run_id 可直接定位到对应 manifest 与 health report）
3. 进入下一阶段：围绕 runner 的稳定运行做工程化（定时触发、artifact 保留策略、告警与人工确认流程）

## 2026-03-25 Local Workflow Automation Wrapper

### 执行清单（立项）
- [x] 完成 design spec
- [x] 完成 implementation plan
- [x] Task 1：自动化 helper、索引写盘与 attention 合同
- [x] Task 2：wrapper 脚本、退出码语义与 contract error 处理
- [x] Task 3：真实 wrapper smoke 与 attention 保留语义
- [x] Task 4：README / 任务跟踪 / 最终聚焦回归

### 规划产物

- Spec: `docs/superpowers/specs/2026-03-25-local-workflow-automation-design.md`
- Plan: `docs/superpowers/plans/2026-03-25-local-workflow-automation-implementation.md`

### 完成结果

- Spec review：已通过
- Plan review：已通过
- Task 1 提交：`46e773a`、`20f2645`、`12f571c`、`b1d796c`
- Task 1 spec review：通过
- Task 1 code review：通过
- Task 1 fresh 验证：`pytest tests/test_workflow_automation.py -q` 通过（`14 passed in 0.49s`）
- Task 2 提交：`b5d8938`、`af2f3af`、`a46f1ad`、`0c8b18c`
- Task 2 spec review：修复后通过
- Task 2 code review：修复后通过
- Task 2 fresh 验证：`pytest tests/test_workflow_automation.py tests/test_workflow_automation_runner.py -q` 通过（`29 passed in 0.57s`）
- Task 3 提交：`8bc2777`、`d49d6d5`、`3713cbe`、`e35729c`、`2c57b3f`
- Task 3 spec review：修复后通过
- Task 3 code review：修复后通过
- Task 3 fresh 验证：`pytest tests/test_workflow_automation_runner.py tests/test_workflow_automation_cli_smoke.py tests/test_end_to_end_workflow_runner.py -q` 通过（`34 passed in 3.29s`）
- Task 4 提交链：`834dfd5`、`6aa9912`、`6bc65e1`；核心文档收口提交以此为准，后续任务跟踪自更新提交不在此行穷举，以 `git log` 为准
- 审查状态：Task 1/2/3 已完成双审查（spec + code），Task 4 文档一致性与任务跟踪自审通过
- Task 4 必跑聚焦回归：`pytest tests/test_workflow_automation.py tests/test_workflow_automation_runner.py tests/test_workflow_automation_cli_smoke.py tests/test_end_to_end_workflow_runner.py tests/test_end_to_end_workflow_runner_cli_smoke.py tests/test_workflow_preflight.py tests/test_workflow_manifest.py -q` 通过（`57 passed`）
- Task 4 扩展回归：`pytest tests/test_workflow_preflight.py tests/test_workflow_manifest.py tests/test_end_to_end_workflow_runner.py tests/test_end_to_end_workflow_runner_cli_smoke.py tests/test_workflow_automation.py tests/test_workflow_automation_runner.py tests/test_workflow_automation_cli_smoke.py tests/test_research_governance_pipeline.py tests/test_research_governance_pipeline_cli_smoke.py tests/test_pipeline_e2e.py -q` 通过（`78 passed`）

## 下一步行动

1. 将 `scripts/run_workflow_automation.py` 接入 cron（本地）与 GitHub Actions（CI）双通道定时触发
2. 在 CI 中上传 `reports/workflow/automation/` 与 runner per-run manifest 作为 artifact，替代仅依赖控制台日志
3. 制定 artifact retention 策略（按运行状态区分保留周期）并补齐 blocked/failed 告警与人工确认流程

## 2026-03-12 项目扫描

### 扫描计划
- [x] 对照 `README.md`、设计文档和任务清单确认目标范围
- [x] 扫描 `src/`、`scripts/`、`tests/` 实际落地情况
- [x] 做基础可运行性验证（语法编译、模块导入前置检查）

### 审查结论
- 核心骨架、配置层、数据层、策略层代码已落地，属于“可阅读的第一版”
- 存储层当时未闭环：`src/storage/database.py` 缺失，`scripts/init_db.py` 当前不可运行
- 回测层代码文件已存在，但依赖未完成的存储层，因此不能视为完成
- Agent 层仅完成 `llm_client`、`base`、`data_qa` 的初版，当时 `DataQAAgent` 仍有错误依赖
- 执行层和测试层基本未开始，`src/execution/` 只有空 `__init__.py`，`tests/` 只有空文件
- README 的运行说明当时超前于实际状态，提到的 `scripts/run_backtest.py`、`scripts/daily_run.py`、`src/main.py` 均不存在

### 验证结果
- `python3 -m compileall src scripts example.py` 通过，说明当前文件语法基本正常
- 直接模块导入验证未通过，当前环境缺少 `pandas`、`sqlalchemy`、`loguru`、`pydantic-settings` 等依赖
- 即使依赖补齐，存储层缺失和部分错误引用仍会阻断初始化与回测流程

## 2026-03-12 本轮开发：T1.5 存储层

### 计划
- [x] 新增 `src/storage/database.py`，补齐 engine、SessionLocal、Base、init_db
- [x] 修复 `src/storage/models.py` 的表约束定义
- [x] 修复 `src/storage/repositories.py` 的缺失导入和存储层联动问题
- [x] 验证 `scripts/init_db.py` 的调用链至少在语法层闭合

### 本轮结果
- 已补齐存储层基础设施，`init_db` 调用链已闭合
- 已补齐 `scripts/run_backtest.py`、`src/main.py`、`scripts/daily_run.py`
- 已修复 `repositories.py` 的 `asdict` 缺失、价格保存非真实 upsert、`DataQAAgent` 错误导入
- 已再次执行 `python3 -m compileall src scripts example.py`，语法校验通过

## 2026-03-12 Phase 1 验证

### 已执行
- [x] 安装项目依赖并完成导入验证
- [x] 执行 `python3 scripts/init_db.py`
- [x] 加载 `strategy.yaml`、`etf_pool.yaml`、`agent.yaml`
- [x] 使用 akshare 成功拉取 4 只 ETF 历史数据并写入 SQLite
- [x] 执行 `python3 scripts/daily_run.py --date 2026-03-11`
- [x] 执行 `python3 scripts/run_backtest.py --start-date 2025-12-01 --end-date 2026-03-11`

### 验证结果
- `market_price` 表已写入 4 只 ETF、每只 297 条历史数据
- `strategy_signal` 表已有 1 条信号记录
- `backtest_run` 表已有 3 条回测记录
- 日常流程已生成有效信号：`BUY 510500`
- 回测 smoke test 已跑通，区间 `2025-12-01` 到 `2026-03-11`
- 本轮回测输出：最终净值 `111485.6616`，年化收益 `48.71%`，最大回撤 `-7.68%`，Sharpe `1.9211`

### 验证中修复的问题
- 修复 `scripts/` 直接执行时找不到 `src` 的路径问题
- 修复 `agent.yaml` 与 `AgentConfig` 的结构不匹配问题
- 将 ETF 历史行情接口从失效的 `fund_etf_hist_sina` 切换到 `fund_etf_hist_em`
- 扩大日常流程与回测的历史窗口，避免 `MA120` 因交易日不足失效
- 修复策略信号 JSON 序列化时的 numpy 标量兼容问题
- 修复回测持仓未变化时错误把仓位覆盖为 0 的 bug
- 回测改为优先使用数据库中的真实交易日，修复非交易日导致的净值异常

## 2026-03-12 Phase 2 开发

### 计划
- [x] 统一 `BaseAgent` / `LLMClient` 行为，支持无 API key 的离线回退
- [x] 完善 `DataQAAgent` 的输入输出与回退逻辑
- [x] 实现 `ReportAgent`
- [x] 实现 `ResearchAgent`
- [x] 实现 `RiskMonitorAgent`
- [x] 增加最小验证，证明 4 个 Agent 在本地可运行

### 本轮结果
- `BaseAgent` 已统一封装提示词、LLM 调用、离线回退和 Agent 日志落库
- `LLMClient` 已兼容 OpenAI 新版 SDK，并支持无 API key 时自动进入 fallback 模式
- 已实现 `DataQAAgent`、`ReportAgent`、`ResearchAgent`、`RiskMonitorAgent`
- 已新增 `tests/test_agents.py`，本地验证 4 个 Agent 的 fallback 逻辑
- `pytest -q tests/test_agents.py` 通过，4 项测试全部成功

## 2026-03-12 Phase 3 开发

### 计划
- [x] 增加执行记录模型与仓储接口
- [x] 实现 `src/execution/checker.py`
- [x] 实现 `src/execution/executor.py`
- [x] 覆盖白名单、最小交易单位、资金充足性检查
- [x] 增加最小执行测试并更新验证状态

### 本轮结果
- 新增 `execution_record` 表，用于记录执行动作、状态、检查摘要和原因
- 新增 `ExecutionRepository`，支持执行记录落库与查询
- 实现 `OrderChecker`，覆盖交易日、人工确认、白名单、调仓约束、最小交易单位和资金检查
- 实现 `RebalanceExecutor`，支持模拟买入、卖出、换仓、空仓和持仓不变场景
- 新增 `tests/test_execution.py`
- `pytest -q tests/test_execution.py` 通过，3 项测试全部成功
- `pytest -q tests` 通过，当前 7 项测试全部成功

## 2026-03-12 端到端闭环

### 已完成
- [x] 将 `DataQAAgent`、`RiskMonitorAgent`、`ReportAgent` 接入日常主流程
- [x] 将 `OrderChecker`、`RebalanceExecutor` 接入日常主流程
- [x] 支持日报 Markdown 和 JSON 落盘到 `reports/daily/`
- [x] `scripts/daily_run.py` 支持 `--execute`、`--manual-approve`、`--available-cash`
- [x] 增加端到端测试 `tests/test_pipeline_e2e.py`

## 2026-03-24 单一 ETF 治理式策略改造（Task 6-7）

### 已完成
- [x] 新增 `RiskAdjustedMomentumStrategy`，引入 20 日波动惩罚
- [x] 新增研究侧候选策略注册表，支持 `trend_momentum` / `risk_adjusted_momentum`
- [x] `config/research.yaml` 与 `ResearchConfig` 支持 `strategy_id + overrides`
- [x] 研究回测链路按 registry 实例化候选策略，输出 `candidate_name`、`strategy_id`、`target_etf_counts`
- [x] 研究汇总页与统一门户展示 `strategy_id` / `active_strategy_id`
- [x] README 明确生产单一 ETF、研究多候选策略、月末信号次一交易日执行

### 验证结果
- [x] `pytest -q tests/test_candidate_risk_adjusted_momentum.py tests/test_research_pipeline.py`
- [x] `pytest -q tests/test_research_summary.py tests/test_report_portal.py`
- [x] `pytest -q`
- [x] `python3 -m compileall src scripts tests`

## 2026-03-24 Implementation Plan 审计

### 审计结论
- [x] `docs/superpowers/plans/2026-03-23-single-etf-governed-strategy-implementation.md` 的 Task 1-7 已全部落地
- [x] 计划文档已同步为完成态，并补充“当前目录非 Git 仓库，未执行 commit”说明
- [x] 当前无该计划内遗留未开始任务

### 当前验证
- [x] `pytest -q` 通过，当前 52 项测试全部成功
- [x] `python3 -m compileall src scripts tests` 通过
- [x] 生产侧仍保持“单一 ETF 或空仓”约束
- [x] 研究侧可同时比较 `trend_momentum` 与 `risk_adjusted_momentum`

### 下一阶段建议
- [ ] 进入第二阶段“治理层落地”，把研究赢家的准入、审批、发布与回退机制正式接到生产侧
- [ ] 为生产侧引入受控策略切换，而不是长期固定 `trend_momentum`
- [ ] 在接入 Git 根目录后补齐 commit / 里程碑归档，形成可追踪发布记录

## 2026-03-24 仓库初始化与第二阶段计划

### 计划
- [x] 初始化 Git 仓库并核对 `.gitignore`
- [x] 生成首个基线提交，固化当前 Task 1-7 完成状态
- [x] 基于既有治理设计输出第二阶段治理层落地 plan
- [x] 同步 `tasks/todo.md` 与相关文档状态

### 结果
- 已初始化 Git 仓库，主分支为 `main`
- 已生成基线提交：`6731fd0 chore: bootstrap etf ai governance foundation`
- 已新增第二阶段计划：
  `docs/superpowers/plans/2026-03-24-governance-layer-rollout-phase-two.md`

## 2026-03-12 项目测试与缺陷扫描

### 扫描计划
- [x] 盘点项目结构、现有测试与历史任务记录
- [x] 运行测试与基础质量检查，确认可复现问题
- [x] 抽查关键模块实现与测试覆盖，识别潜在缺陷
- [x] 输出修复清单，按优先级整理

### 扫描结果
- `pytest -q` 通过，当前 15 项测试全部成功
- `python3 -m compileall src scripts tests` 通过
- 发现 6 个需要进入修复队列的问题，其中 4 个已做最小复现

### 已确认问题
- P0: `RebalanceExecutor` 在手续费挤占最小交易单位时，仍会写入 `filled_shares=0` 的 `filled` 结果，并把组合状态更新为持有目标 ETF
- P0: `OrderChecker` 依赖全局 `trading_calendar`，但日常主流程未加载真实交易日历；在日历为空时仅按“非周末”判断，会放行法定节假日
- P1: `TradingCalendar.get_rebalance_dates(..., frequency="biweekly")` 在 15 号不是交易日时直接跳过，导致双周调仓点缺失
- P1: `compare_params()` 与 `SimpleBacktestEngine.run()` 都会写 `BacktestRun`，一次比较会重复落库两条记录
- P1: 风险监控输入只构造单点 `nav_series`，`current_drawdown` 基本恒为 0，风险 Agent 无法识别真实回撤

## 2026-03-24 Task 3: 抽出统一成交模拟器并让研究/生产共用

### 计划
- [x] 在 `tests/test_execution_simulator.py` 先写失败测试，覆盖整手约束、缺价格失败、卖后买失败保留现金、HOLD
- [x] 运行 `pytest -q tests/test_execution_simulator.py tests/test_execution.py`，确认当前缺少统一 simulator
- [x] 新增 `src/execution/simulator.py`，实现统一成交模拟与结果对象
- [x] 修改 `src/execution/checker.py`，仅保留闸门检查并委托 simulator 做成交预估
- [x] 修改 `src/execution/executor.py`，移除重复买卖数学，改为基于 simulator 结果落库
- [x] 修改 `src/backtest/engine.py`，用 simulator 替换分数股逻辑并保留现金余额
- [x] 修改 `src/main.py`，通过 `strategy_config.trade_policy` 初始化检查/执行链路
- [x] 运行 `pytest -q tests/test_execution.py tests/test_execution_simulator.py tests/test_regressions.py`

### 审查
- [x] 对照任务边界确认：本轮只统一成交/持仓转换语义，不引入新的 signal/execution 双阶段状态机
- [x] 对照已有回归确认：“0 股成交 rejected” 继续保持绿色

- P2: 研究报告 CSV 通过字符串拼接生成，`overrides` JSON 内含逗号时会破坏列结构

### 修复清单
- [ ] 修复执行器 0 股成交问题，并补充“资金刚好够 1 手但扣费后不够”的回归测试
- [ ] 为日常流程加载真实交易日历，节假日校验失败时阻断下单；补充节假日测试
- [ ] 重写双周调仓日算法，改为“15 日所在半月的最后一个交易日 + 月末最后一个交易日”
- [ ] 统一回测落库职责，避免 `compare_params` / `SimpleBacktestEngine` 重复写库
- [ ] 从 `portfolio_state` 历史记录构造净值序列，修正回撤与相对基准判断，并补测试
- [ ] 用 `csv` 标准库写研究 CSV，增加包含逗号/换行参数的导出测试

## 2026-03-13 缺陷修复

### 修复计划
- [x] 复核 2026-03-12 扫描结论，确认 6 个问题的落点
- [x] 增加回归测试，先让问题可验证
- [x] 修复执行、交易日历、回测、风险监控、研究导出逻辑
- [x] 执行全量测试并记录结果

### 修复结果
- 已修复执行器“0 股也记 filled”问题，检查器与执行器都改为按含手续费后的实际可成交手数判断

## 2026-03-23 单ETF治理化升级设计

### 规划
- [x] 复核当前系统架构、代码边界与关键风险
- [x] 明确目标为“研究多候选 + 生产单一ETF”
- [x] 设计候选策略、治理层、生产决策层和统一交易语义
- [x] 输出正式设计 spec

### 结果
- 已形成正式设计文档：`docs/superpowers/specs/2026-03-23-single-etf-governed-strategy-design.md`
- 已确定系统目标不是组合实盘，而是“候选策略研究治理 + 单ETF生产执行”
- 已确定第一批实施范围：先统一语义、测试隔离、抽象交易服务，再引入候选策略与治理层

### 审查
- 当前设计强调研究层复杂化、生产层简化，符合现有项目逐步演进的方向
- 下一步应在用户复核 spec 后，再进入 implementation plan，避免直接跳到重构

## 2026-03-23 Implementation Plan

### 计划
- [x] 基于已确认 spec 输出 implementation plan
- [x] 将首批实施范围拆分为可执行任务
- [x] 明确文件创建/修改边界与验证命令

### 结果
- 已新增 implementation plan：
  `docs/superpowers/plans/2026-03-23-single-etf-governed-strategy-implementation.md`
- 首批实施范围被拆成 7 个任务：
  - 测试环境与数据库隔离
  - 统一交易语义与调仓计划
  - 统一成交模拟
  - 特征快照与 proposal 抽象
  - 基线候选策略重构
  - 风险调整动量候选策略
  - 报告/门户/文档收尾
- 已在主流程基于价格数据加载交易日历，且 `OrderChecker` 增加 exact-date 行情兜底，避免节假日和脏全局日历误判
- 已修复双周调仓日期算法，月中调仓点改为“15 日及之前最后一个交易日”
- 已统一回测落库职责，`compare_params()` 不再与 `SimpleBacktestEngine.run()` 重复写 `BacktestRun`
- 已改为从 `portfolio_state` 历史构造 `nav_series`，风险监控可正确识别回撤和相对基准表现
- 已改为使用 `csv` 标准库导出研究结果，修复 JSON 参数中的逗号破坏列结构问题

### 验证结果
- `pytest -q` 通过，`21 passed`
- 新增回归测试文件 `tests/test_regressions.py`

### 验证结果
- `run_daily_pipeline` 已形成闭环：数据校验 → 策略信号 → 风险评估 → 执行检查 → 模拟执行 → 报告落盘
- `pytest -q tests/test_pipeline_e2e.py` 通过
- `pytest -q tests` 通过，当前 8 项测试全部成功

## 2026-03-12 研究线闭环

### 计划
- [x] 增加研究线主流程，串联参数对比与 `ResearchAgent`
- [x] 增加 `scripts/run_research.py`
- [x] 将研究结果落盘到 `reports/research/`
- [x] 增加最小研究线测试
- [x] 更新 README 当前能力说明

### 本轮结果
- 已新增 `src/research_pipeline.py`，形成“参数对比 → ResearchAgent → Markdown/JSON/CSV 报告落盘”的研究闭环
- 已新增 `scripts/run_research.py`，支持按时间区间执行研究流程
- 研究报告已落盘到 `reports/research/`
- 已新增 `tests/test_research_pipeline.py`

### 验证结果
- `pytest -q tests/test_research_pipeline.py` 通过
- `pytest -q tests` 通过，当前 11 项测试全部成功

## 2026-03-12 本轮推进

### 计划
- [x] 将研究候选参数从代码内置列表外置到配置文件
- [x] 为研究脚本增加候选配置入参，支持切换不同研究方案
- [x] 补齐 `tasks/todo.md` 的研究线闭环结果
- [x] 同步 README 的研究配置与运行说明
- [x] 串行执行研究线测试与全量测试

### 本轮结果
- 已新增 `config/research.yaml`，研究候选参数不再硬编码在 `src/research_pipeline.py`
- `ConfigLoader` 已支持加载研究配置，研究流程默认读取 `config/research.yaml`
- `scripts/run_research.py` 已支持 `--candidate-config`，可切换不同研究候选配置文件
- 研究报告已带出候选说明字段，便于回看每组参数意图
- README 已同步研究配置说明和命令示例

### 验证结果
- `python3 -m compileall src scripts` 通过
- `pytest -q tests/test_research_pipeline.py` 通过，当前 3 项测试全部成功
- `pytest -q tests` 通过，当前 11 项测试全部成功

## 2026-03-12 研究报告汇总

### 计划
- [x] 扫描 `reports/research/*.json` 并抽取统一字段
- [x] 实现研究报告聚合模块，生成统一 Markdown/JSON/CSV 摘要
- [x] 增加聚合脚本，支持按目录执行
- [x] 增加最小测试覆盖多份研究报告汇总
- [x] 串行验证并同步 README

### 本轮结果
- 已新增 `src/research_summary.py`，支持按报告视图和候选视图聚合历史研究结果
- 已新增 `scripts/summarize_research_reports.py`，默认扫描 `reports/research/*.json`
- 汇总结果输出到 `reports/research/summary/`，包含 `Markdown + JSON + 2 份 CSV`
- 已在真实目录生成首份聚合结果，当前输出文件已落盘
- 已新增 `tests/test_research_summary.py`

### 验证结果
- `python3 -m compileall src scripts` 通过
- `pytest -q tests/test_research_summary.py` 通过，当前 2 项测试全部成功
- `python3 scripts/summarize_research_reports.py` 通过，已生成真实汇总文件
- `pytest -q tests` 通过，当前 13 项测试全部成功

## 2026-03-12 研究历史总览页

### 计划
- [x] 基于研究汇总结果生成静态 HTML 总览页
- [x] 将总览页接入现有研究汇总输出流程
- [x] 增加最小测试验证 HTML 输出
- [x] 串行验证并同步 README

### 本轮结果
- 研究汇总流程已新增静态 HTML 渲染，输出 `reports/research/summary/index.html`
- 页面已接入报告视图和候选视图两张表，并展示最新推荐、历史领先候选等概览指标
- 聚合脚本保持不变，执行 `python3 scripts/summarize_research_reports.py` 会同步生成 HTML 页
- `tests/test_research_summary.py` 已补充 HTML 输出断言

### 验证结果
- `python3 -m compileall src scripts` 通过
- `pytest -q tests/test_research_summary.py` 通过，当前 2 项测试全部成功
- `python3 scripts/summarize_research_reports.py` 通过，已生成真实 HTML 总览页
- `pytest -q tests` 通过，当前 13 项测试全部成功

## 2026-03-12 总览页交互增强

### 计划
- [x] 为研究历史总览页增加按候选筛选
- [x] 为研究历史总览页增加按日期区间筛选
- [x] 为报告表和候选表增加列排序
- [x] 补充测试并串行验证
- [x] 同步 README / todo，并更新整体项目进度状态

### 本轮结果
- 汇总 JSON 已新增 `candidate_observations`，为总览页提供按筛选条件重算候选表现的原始明细
- `reports/research/summary/index.html` 已支持候选筛选、起止日期筛选和双表列排序
- 排序在前端本地完成，不依赖服务端或额外前端框架
- README 已同步总览页交互能力说明

### 验证结果
- `python3 -m compileall src scripts` 通过
- `pytest -q tests/test_research_summary.py` 通过，当前 2 项测试全部成功
- `python3 scripts/summarize_research_reports.py` 通过，真实总览页已更新
- `pytest -q tests` 通过，当前 13 项测试全部成功

## 2026-03-12 统一门户视图

### 计划
- [x] 聚合 `reports/daily/*.json` 和研究汇总结果
- [x] 生成统一入口页 `reports/index.html`
- [x] 增加最小测试验证门户页输出
- [x] 串行验证并同步 README / todo

### 本轮结果
- 已新增 `src/report_portal.py`，统一聚合日报摘要与研究汇总结果
- 已新增 `scripts/build_report_portal.py`，可单独构建门户页
- 已生成 `reports/index.html` 和 `reports/portal_summary.json`
- `scripts/summarize_research_reports.py` 已接入门户刷新
- 日常主流程和研究主流程在报告落盘后都会自动刷新统一门户
- 已新增 `tests/test_report_portal.py`

### 验证结果
- `python3 -m compileall src scripts` 通过
- `pytest -q tests/test_report_portal.py tests/test_research_summary.py` 通过，当前 4 项测试全部成功
- `python3 scripts/build_report_portal.py` 通过，真实统一门户已生成
- `pytest -q tests` 通过，当前 15 项测试全部成功

## 2026-03-24 第二阶段治理层落地

### 计划
- [x] 增加治理配置、领域模型与 SQLite 决策持久化
- [x] 落地治理评估器与 `run_governance_review.py`
- [x] 接入审批、发布、回退与生产运行时策略解析
- [x] 升级统一门户与 README 治理运维说明
- [x] 执行专项测试、全量测试与语法编译校验
- [x] 按单次仓库提交收敛第二阶段改动

### 本轮结果
- 已新增 `src/governance/` 域，覆盖治理配置、评估、运行时解析、发布与回退
- 已新增 `governance_decision` 表与 `GovernanceRepository`，支持 draft/approved/published/rolled_back 生命周期
- 生产主流程已优先消费“最新已发布治理策略”，治理关闭或无有效发布记录时回退到 YAML 默认策略
- 已新增 `scripts/run_governance_review.py`、`scripts/publish_governance_decision.py`、`scripts/rollback_governance_decision.py`
- 统一门户已展示 active strategy、最近治理决策与最近已发布策略，README 已补充治理运维命令

### 验证结果
- `pytest -q tests/test_governance_models.py` 通过，`2 passed`
- `pytest -q tests/test_governance_repository.py` 通过，`1 passed`
- `pytest -q tests/test_governance_evaluator.py` 通过，`3 passed`
- `pytest -q tests/test_governance_runtime.py tests/test_pipeline_e2e.py` 通过，`6 passed`
- `pytest -q tests/test_report_portal.py` 通过，`2 passed`
- `pytest -q` 通过，`62 passed in 1.63s`
- `python3 -m compileall src scripts tests` 通过

## 2026-03-24 第三阶段治理自动化增强计划

### 计划
- [x] 明确第三阶段范围为“半自动治理编排”，默认保留人工最终发布门禁
- [x] 输出第三阶段实施计划文档
- [x] 同步 `tasks/todo.md` 记录后续执行入口

### 结果
- 已新增第三阶段 plan：
  `docs/superpowers/plans/2026-03-24-governance-automation-enhancement-phase-three.md`
- 本轮计划聚焦四块：
  - 自动 review cycle 与去重
  - 发布前门禁与 blocked/ready 状态
  - 健康巡检、incident 与 rollback recommendation
  - 门户与运维手册升级

### 下一步执行建议
- [x] 完成 Task 1，补齐 `governance.automation` 配置、review 状态和 incident 持久化
- [x] 执行 Task 2，把 `run_governance_cycle.py` 接成统一自动编排入口
- [x] 执行 Task 3，落健康巡检与 rollback recommendation
- [x] 执行 Task 4，落门户展示与全量验证

### Task 1 结果
- 已新增 `GovernanceAutomationConfig`
- 已为 `GovernanceDecision` 增加 `summary_hash/source_report_date/review_status/blocked_reasons`
- 已新增 `GovernanceIncident` 与 `governance_incident` 表
- 已扩展 `GovernanceRepository` 支持 review 状态更新、summary_hash 查询与 incident 持久化
- 已新增轻量测试文件 `tests/test_governance_automation.py`、`tests/test_governance_health.py`
- 已生成 Task 1 提交：`b720d64 feat: add governance automation config and audit state`

### Task 1 验证
- `pytest -q tests/test_governance_repository.py` 通过，`4 passed`
- `pytest -q tests/test_governance_repository.py tests/test_governance_models.py tests/test_governance_automation.py tests/test_governance_health.py` 通过，`8 passed`
- `python3 -m compileall src/core/config.py src/governance/models.py src/storage/models.py src/storage/repositories.py tests/test_governance_repository.py tests/test_governance_automation.py tests/test_governance_health.py` 通过

### Task 2 结果
- 已新增 `src/governance/automation.py`，支持 summary hash 去重、freshness/cooldown/open critical incident 门禁和 `ready/blocked` review 状态回写
- 已新增 `scripts/run_governance_cycle.py`
- `scripts/run_governance_review.py` 已复用自动 cycle 的 draft 生成逻辑
- `publish_decision()` 已在自动化开启时要求 `review_status == "ready"`，自动化关闭时保持旧兼容行为
- 已生成 Task 2 提交：`5a0a1d8 feat: add governance automation review cycle`

### Task 2 验证
- `pytest -q tests/test_governance_automation.py tests/test_governance_runtime.py` 通过，`10 passed`
- `pytest -q tests/test_governance_repository.py tests/test_governance_automation.py tests/test_governance_runtime.py` 通过，`14 passed`
- `python3 -m compileall src/governance/automation.py src/governance/publisher.py scripts/run_governance_review.py scripts/run_governance_cycle.py tests/test_governance_automation.py tests/test_governance_runtime.py` 通过

### Task 3 结果
- 已新增 `src/governance/health.py`，支持 `STRATEGY_DRIFT`、`RISK_BREACH`、`EXECUTION_FAILURE`、`GOVERNANCE_STALE` 巡检
- 已新增 `scripts/check_governance_health.py`
- health check 在 critical incident 场景下可生成 fallback draft recommendation
- 已补 e2e：健康巡检推荐回退后，生产主流程可恢复消费 fallback 策略
- 已生成 Task 3 提交：`9f89e8c feat: add governance health checks and rollback recommendation`

### Task 3 验证
- `pytest -q tests/test_governance_health.py tests/test_pipeline_e2e.py` 通过，`6 passed`
- `pytest -q tests/test_governance_health.py tests/test_governance_automation.py tests/test_governance_runtime.py tests/test_pipeline_e2e.py` 通过，`16 passed`
- `python3 -m compileall src/governance/health.py scripts/check_governance_health.py tests/test_governance_health.py tests/test_pipeline_e2e.py` 通过

### Task 4 结果
- 统一门户已展示 `latest_draft.review_status`、`blocked_reasons`、open incident 统计与最新 rollback recommendation
- README 已补治理自动化推荐运行顺序和“默认不自动 publish”说明
- 第三阶段 plan 已更新为完成态

### Task 4 验证
- `pytest -q tests/test_report_portal.py` 通过，`2 passed`
- `pytest -q` 通过，`75 passed in 1.60s`
- `python3 -m compileall src scripts tests` 通过

## 2026-03-24 Phase 4 状态感知研究实施计划

### 计划
- [x] 复核 Phase 4 设计 spec，锁定“规则型 3 档 regime + ETF 池聚合 + 仅研究线”边界
- [x] 输出 Phase 4 implementation plan
- [x] 同步 `tasks/todo.md` 记录当前阶段状态
- [ ] 执行 Task 1，落地 regime 配置与规则型分类器
- [ ] 执行 Task 2，落地样本切片与候选分层分析
- [ ] 执行 Task 3，把 regime 分析接入 `src/research_pipeline.py`
- [ ] 执行 Task 4，升级 `src/research_summary.py` 并完成全量验证

### 结果
- 已新增 Phase 4 plan：
  `docs/superpowers/plans/2026-03-24-phase-four-regime-research-implementation.md`
- 本阶段继续保持“单一 ETF 实盘不接 `regime`”约束，当前只增强研究证据层
- 计划已拆成 4 个可独立验证的任务，覆盖配置、分类、分析、单次研究落盘和跨报告汇总

### 审查
- 计划边界与 `docs/superpowers/specs/2026-03-24-phase-four-regime-research-design.md` 一致，未扩到生产 runtime
- 计划默认按 TDD 执行，并明确了每个 Task 的专项测试、全量测试与最终编译校验
- 当前仅完成文档与计划，代码实现尚未开始

### Task 1 结果
- 已扩展 `ResearchConfig`，新增 `regime` 与 `sample_split` 配置模型
- 已扩展 `config/research.yaml`，补齐规则型 regime 阈值和 70/30 样本切分配置
- 已新增 `src/research/regime.py`，支持 ETF 池价格序列到逐日 `RegimeSnapshot` 列表的规则型分类
- 已新增 `tests/test_regime_classifier.py`，覆盖配置加载、`risk_on/risk_off` 判定与 coverage 不足回退
- 已补齐 `enabled=false`、warm-up 过滤和横盘市场 `neutral` 的边界修复
- 已生成 Task 1 提交：`a758d45 feat: add regime classifier for research`

### Task 1 验证
- `pytest -q tests/test_regime_classifier.py -v` 通过，`6 passed`
- `pytest -q tests/test_research_pipeline.py -v` 通过，`3 passed`
- `pytest -q tests/test_research_summary.py -v` 通过，`2 passed`
- `python3 -m compileall src/research src/core/config.py tests/test_regime_classifier.py` 通过

### Task 2 结果
- 已新增 `src/research/segmentation.py`，实现固定 70/30 交易日样本切片
- 已新增 `src/research/regime_analysis.py`，支持 `overall / by_regime / in_sample / out_of_sample / by_regime_and_sample / transition` 分层统计
- 已新增 `tests/test_regime_analysis.py`，覆盖切片比例、状态分层和 transition 聚合
- 已生成 Task 2 提交：`c7a90d3 feat: add regime segmentation analysis`

### Task 2 验证
- `pytest -q tests/test_regime_analysis.py -v` 通过，`2 passed`
- `python3 -m compileall src/research tests/test_regime_analysis.py` 通过

### Task 3 结果
- `src/research_pipeline.py` 已接入 ETF 池 regime 标签、样本切片和候选分层分析
- 单次研究 JSON 已新增 `regime_config_snapshot`、`regime_daily_labels`、`candidate_regime_metrics`、`candidate_sample_split_metrics`、`candidate_regime_transition_metrics`
- Markdown 研究报告已补 `Regime 概览` 与 `样本外观察`
- 已生成 Task 3 提交：`0097f6e feat: enrich research pipeline with regime outputs`

### Task 3 验证
- `pytest -q tests/test_research_pipeline.py -v` 通过，`4 passed`
- `python3 -m compileall src/research_pipeline.py tests/test_research_pipeline.py` 通过

### Task 4 结果
- `src/research_summary.py` 已新增 `regime_summary`、`candidate_regime_leaderboard`、`candidate_out_of_sample_leaderboard`、`candidate_regime_observations`
- 研究汇总 Markdown / HTML 已显式回答 `risk_on` 强者、`risk_off` 稳定者、单一状态依赖和样本外退化四个问题
- 研究汇总 HTML 已新增“状态观察”区块

### Task 4 验证
- `pytest -q tests/test_research_summary.py -v` 通过，`2 passed`
- `pytest -q tests/test_regime_classifier.py tests/test_regime_analysis.py tests/test_research_pipeline.py tests/test_research_summary.py -v` 通过，`11 passed`
- `pytest -q` 通过，`84 passed in 2.21s`
- `python3 -m compileall src scripts tests` 通过
