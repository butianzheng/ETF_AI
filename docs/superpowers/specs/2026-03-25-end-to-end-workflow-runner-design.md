# End-to-End Workflow Runner 设计

## 1. 背景

截至 2026-03-25，项目已经具备以下独立入口：

- 日常执行：
  - `scripts/daily_run.py`
- 研究治理统一编排：
  - `scripts/run_research_governance_pipeline.py`
- 治理发布：
  - `scripts/publish_governance_decision.py`
- 治理健康巡检：
  - `scripts/check_governance_health.py`
- 统一门户刷新：
  - 已由日常流和研究治理流内部覆盖

当前问题不在于“没有能力”，而在于“入口分散”：

- 想完整跑一次研究治理到发布前检查，仍需人工拼接多个脚本
- `publish` 与 `health check` 缺少统一管理入口
- 对外管理时，很难用一条命令拿到本次运行的关键状态与产物路径

因此，这一轮的目标不是新增治理规则，而是补一个面向管理执行的一键端到端编排脚本，把现有入口串成一个清晰、安全、可回归的统一入口。

## 2. 本子项目已确认选择

本子项目按以下边界设计：

- 新增一个统一管理入口：
  - `scripts/run_end_to_end_workflow.py`
- 默认采用安全模式
  - 默认不自动 publish
  - 只有显式传 `--publish --approved-by <name>` 才发布
- 同一入口纳入：
  - 研究治理流
  - health check
  - 可选 daily run
  - 可选 publish
- publish 后自动再跑一次 health check
- 默认不把 daily run 作为强制前置
- 不重写现有单脚本职责
  - 新脚本只做编排，不替代已有 CLI

## 3. 目标

建设一个端到端编排入口，使系统可以：

- 用一条命令完成研究治理主流程与后续健康检查
- 在需要时把 daily run 纳入同一入口统一调度
- 在显式授权下完成 publish，并自动执行发布后健康检查
- 输出统一、结构化的本次运行 summary，便于人工查看和后续自动化接入

## 4. 非目标

本子项目明确不做：

- 改写 `daily_run.py`、`run_research_governance_pipeline.py`、`publish_governance_decision.py`、`check_governance_health.py` 的现有职责
- 默认开启自动发布
- 把 rollback 自动执行纳入本轮
- 新增复杂的任务调度器、队列或后台服务
- 重写现有 report/governance/publish 领域逻辑

## 5. 方案选择

本子项目采用：

- 新增统一编排脚本
- 内部直接编排现有 service / script-level 入口

而不是：

- 继续靠 README 指导人工串多个命令
- 用 shell 脚本简单串行调用多个 Python 脚本
- 把所有逻辑硬塞进某个已有脚本

原因：

- 统一 Python 入口更易测试，也更适合输出结构化结果
- shell 串联虽然快，但错误处理、参数复用、测试与跨平台管理都较弱
- 现有单脚本职责已经较清晰，新增编排层更符合边界分离

## 6. 模块边界

### 6.1 新编排入口

建议新增：

- `scripts/run_end_to_end_workflow.py`

职责只包含：

- 解析统一编排参数
- 调度 daily / research-governance / health / publish
- 汇总本次运行结果
- 映射退出码

它不负责：

- 重写 daily 主流程
- 重写研究治理逻辑
- 重写 publish / health check 逻辑

### 6.2 现有脚本与领域层

保留现有入口与领域逻辑不变：

- `scripts/daily_run.py`
- `scripts/run_research_governance_pipeline.py`
- `scripts/publish_governance_decision.py`
- `scripts/check_governance_health.py`

新脚本应优先复用它们背后的领域/service 能力，必要时也可调用脚本级 `main(...)`，但不能改变其对外语义。

## 7. 默认流程设计

默认流程固定为：

1. 可选执行 `daily run`
2. 执行 `research -> summary -> governance -> portal refresh`
3. 执行一次 `health check`
4. 若显式传 `--publish --approved-by <name>`：
   - 发布本次治理决策
   - 再执行一次 `health check`

关键原则：

- 默认不 publish
- 默认 daily run 非强制
- publish 必须显式授权
- publish 后必须自动做一次 post-publish health check

## 8. CLI 设计

### 8.1 研究治理参数

建议支持：

- `--start-date`
- `--end-date`
- `--candidate-config`
- `--initial-capital`
- `--fee-rate`
- `--log-level`
- `--fail-on-blocked`

### 8.2 编排控制参数

建议支持：

- `--run-daily`
- `--daily-date`
- `--daily-execute`
- `--daily-manual-approve`
- `--daily-available-cash`
- `--publish`
- `--approved-by`
- `--create-rollback-draft`

### 8.3 参数语义

约束：

- 默认不跑 daily
- 默认跑 research-governance + health
- 默认不 publish
- 若传 `--publish`，必须同时传 `--approved-by`
- `--create-rollback-draft` 仅传递给 health check

## 9. 发布策略

本轮固定采用安全模式：

- 默认只执行到 `health check`
- 只有显式传 `--publish --approved-by <name>` 才允许发布

不采用：

- 自动只要 `ready` 就发布
- 默认 publish

原因：

- 当前生产侧仍保留人工门禁
- 单 ETF 实盘场景下，发布动作应继续显式授权

## 10. blocked / fatal 语义

### 10.1 blocked

当 research-governance 返回 `blocked` 时：

- 若启用 `--fail-on-blocked`：
  - 脚本返回 `2`
- 否则：
  - 脚本仍返回 `0`

无论哪种情况：

- 仍应输出本次运行 summary
- 默认不自动 publish

若用户显式传了 `--publish --approved-by <name>`，且本次治理结果为 `blocked`：

- 必须禁止 publish
- 必须保留并输出 `research-governance` 与 `health check` 结果
- `publish_result.executed` 必须为 `false`
- summary 中必须明确记录：
  - `publish_blocked_reason = "governance_review_status_blocked"`
- 最终退出码：
  - 启用 `--fail-on-blocked` 时返回 `2`
  - 未启用时返回 `0`

### 10.2 fatal

当 research-governance、health check 或 publish 后 health check 阶段出现 fatal：

- 脚本整体返回 `1`
- summary 中应清晰记录失败阶段与错误

退出码优先级固定为：

- `1`（fatal）高于 `2`（blocked + fail-on-blocked）
- `2` 高于 `0`

也就是说：

- 若 research-governance 已经是 `blocked` 且原本应返回 `2`，但随后 health check / publish 阶段 fatal，最终退出码仍必须提升为 `1`
- health check 自身异常视为 fatal，而不是保留 `2`

## 11. 输出设计

建议最终统一输出一份结构化 summary，至少包含：

```json
{
  "daily_result": {
    "executed": false,
    "artifacts": {}
  },
  "research_governance_result": {
    "research_report": "reports/research/2026-03-25.json",
    "summary_json": "reports/research/summary/research_summary.json",
    "decision_id": 12,
    "review_status": "ready",
    "blocked_reasons": [],
    "pipeline_summary": "reports/governance/pipeline/2026-03-25.json"
  },
  "health_check_result": {
    "report_path": "reports/governance/health/2026-03-25.json",
    "rollback_decision_id": null
  },
  "publish_result": {
    "executed": false,
    "decision": null
  },
  "exit_code": 0
}
```

要求：

- 同时保留适合终端阅读的简洁 stdout
- 若测试/自动化需要，summary 应易于断言

summary 交付形态固定为：

- 写盘到：
  - `reports/workflow/end_to_end_workflow_summary.json`
- 同时 stdout 打印关键摘要行
- `main(argv)` 返回退出码 `int`，不直接返回 summary dict

fatal 场景下仍必须尽力输出 summary 文件，至少包含：

```json
{
  "status": "failed",
  "failed_step": "research_governance|health_check|publish|post_publish_health_check",
  "error": {
    "type": "RuntimeError",
    "message": "..."
  },
  "exit_code": 1
}
```

也就是说：

- 除非失败发生在 summary 自身写盘阶段，否则 fatal 场景仍应产出可断言的 summary artifact
- 独立测试文件以该 summary JSON 为主断言目标，stdout 只做关键契约断言

## 12. 文件边界

### Create

- `scripts/run_end_to_end_workflow.py`
- `tests/test_end_to_end_workflow_runner.py`

### Modify

- `README.md`
- `tasks/todo.md`

### Verify Only

- `scripts/daily_run.py`
- `scripts/run_research_governance_pipeline.py`
- `scripts/publish_governance_decision.py`
- `scripts/check_governance_health.py`

## 13. 测试边界

建议新增独立测试文件：

- `tests/test_end_to_end_workflow_runner.py`

重点覆盖：

1. 默认不 publish
2. 传 `--publish` 但缺 `--approved-by` 时参数校验失败
3. happy path
   - 研究治理 + health
4. publish path
   - publish 后自动再跑一次 health check
5. blocked path
   - 启用 `--fail-on-blocked` 时返回 `2`
   - 即使显式传 `--publish`，也必须禁止发布
6. fatal path
   - research/governance fatal 时返回 `1`
7. health check fatal path
   - 返回 `1`
   - summary 中记录 `failed_step`

约束：

- 重点测编排与参数转发，不需要在该测试里重复覆盖各子脚本的内部业务逻辑

## 14. 风险与控制

主要风险：

- 新脚本变成“超级入口”，把过多业务逻辑吸进去
- publish 与 health 的顺序处理不清，导致状态不一致
- stdout / summary 设计过重，影响可读性

控制策略：

- 新脚本只做编排，不做业务重写
- publish 后强制再做一次 health check
- 默认安全模式，不自动发布
- 用独立测试文件锁住参数和退出码语义
