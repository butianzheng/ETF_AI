# ETF Ops 单一总入口 CLI 设计

## 1. 背景

截至 2026-03-25，项目已经具备多条可运行主链：

- `scripts/run_end_to_end_workflow.py`
- `scripts/run_workflow_automation.py`
- `scripts/daily_run.py`
- `scripts/run_research_governance_pipeline.py`

它们分别覆盖：

- 端到端 workflow 编排
- 本地自动化 wrapper
- 单日执行
- research-to-governance 闭环

当前主要短板不是“能力缺失”，而是“入口分散”：

- 高频操作分布在多个脚本，新使用者记忆成本高
- README 示例越来越多，但缺少统一导航入口
- 旧脚本各自维护 CLI 边界，后续扩展容易漂移
- 本地半自动与人工执行缺少统一查看口径

生产侧当前仍聚焦“单一 ETF 实盘持有”场景，因此本轮更需要把已有能力收敛为稳定、可发现、易执行的单一总入口，而不是继续扩展新的业务子系统。

## 2. 本子项目已确认选择

本子项目按以下边界设计：

- 新增单一总入口：`python scripts/etf_ops.py ...`
- 第一版只覆盖高频主链：`workflow / automation / daily / research-governance / status`
- 交互形态采用分层 `subcommand`
- 保留旧脚本，并让它们转发到新的统一入口
- `status latest` 首版只读取现有 artifact，不新增数据库表

明确不做：

- TUI、交互式菜单或浏览器控制台
- profile/preset 抽象
- 一次性收编所有低频脚本（如 backtest / portal / publish / rollback）
- 改写现有 workflow / automation 的退出码或 stdout 合同

## 3. 目标

本子项目需要解决 4 个问题：

1. 让操作者只需要记住一个入口，就能触达高频主链
2. 保留旧脚本兼容性，同时把 CLI 维护点集中到一处
3. 为本地半自动场景提供统一的最近运行状态查看命令
4. 在不破坏既有合同的前提下，为后续 CLI 扩展建立清晰边界

## 4. 非目标

本子项目明确不做：

- 改动底层业务流程语义
- 新增服务端调度器、任务队列或持久化运行注册表
- 调整 publish 审批门禁
- 为低频维护命令设计完整运维平台
- 重新命名既有 workflow / automation 合同字段

## 5. 方案选择

本子项目采用：

- 分层 `subcommand` 总入口
- 统一 CLI 适配层
- 旧脚本薄转发
- 基于现有 artifact 的只读状态汇总

不采用：

### 方案 B：扁平命令总入口

例如：

- `etf_ops workflow-run`
- `etf_ops daily-run`
- `etf_ops rg-run`

不选原因：

- 命令分组关系弱
- 子命令越多越难发现
- 后续加入 `status / publish / rollback` 时会快速失控

### 方案 C：配置驱动或 profile 驱动入口

例如：

- `etf_ops run daily-safe`
- `etf_ops run rg-safe`

不选原因：

- 当前阶段抽象过早
- 会掩盖底层关键参数，降低调试透明度
- 不利于保持与现有脚本参数语义对齐

## 6. 命令树设计

第一版命令树如下：

```bash
python scripts/etf_ops.py workflow run [workflow 原有参数]
python scripts/etf_ops.py workflow preflight [workflow run 同参，内部强制 --preflight-only]

python scripts/etf_ops.py automation run -- [透传给 workflow runner 的参数]

python scripts/etf_ops.py daily run [daily 原有参数]

python scripts/etf_ops.py research-governance run [rg pipeline 原有参数]

python scripts/etf_ops.py status latest
python scripts/etf_ops.py status latest --json
```

分组语义：

- `workflow`：端到端编排主入口
- `automation`：本地半自动 wrapper 主入口
- `daily`：单日执行
- `research-governance`：研究到治理闭环
- `status`：最近一次运行状态查看

该分组与现有脚本职责一致，便于未来继续收编低频命令而不污染主路径。

## 7. 参数与语义设计

### 7.1 workflow run

`workflow run` 直接复用现有 `scripts/run_end_to_end_workflow.py` 的参数语义，不重新命名参数：

- `--start-date`
- `--end-date`
- `--candidate-config`
- `--initial-capital`
- `--fee-rate`
- `--log-level`
- `--fail-on-blocked`
- `--preflight-only`
- `--run-daily`
- `--daily-date`
- `--daily-execute`
- `--daily-manual-approve`
- `--daily-available-cash`
- `--publish`
- `--approved-by`
- `--create-rollback-draft`

### 7.2 workflow preflight

`workflow preflight` 是显式别名，面向可发现性。其内部行为等价于：

```bash
python scripts/etf_ops.py workflow run --preflight-only ...
```

设计要求：

- 内部仍调用同一 workflow runner
- 不引入第二套预检实现
- 参数面保持与 `workflow run` 一致，由统一 workflow 参数解析器处理
- CLI 适配层在最终参数列表中强制附加 `--preflight-only`
- 即使用户显式传入 `--run-daily`、`--publish` 等非预检场景参数，runner 也会因为 `--preflight-only` 而在预检后直接返回，不进入后续阶段

这样设计的原因是：

- 不需要维护第二套 workflow 参数定义
- 旧 runner 参数校验逻辑可以完整复用
- implementation planning 可以明确收敛为“复用同一参数面 + 强制注入 `--preflight-only`”

### 7.3 automation run

`automation run` 复用 `scripts/run_workflow_automation.py` 的现有语义：

- 保留 `--workdir`
- 保留 `--` 后参数原样透传给 workflow runner

示例：

```bash
python scripts/etf_ops.py automation run -- --preflight-only
python scripts/etf_ops.py automation run --workdir /tmp/workflow_job -- --start-date 2025-12-01 --end-date 2026-03-24
```

首版不对透传参数做高层封装，避免与现有 automation 合同产生偏差。

### 7.4 daily run

`daily run` 直接复用 `scripts/daily_run.py` 的参数：

- `--date`
- `--log-level`
- `--execute`
- `--manual-approve`
- `--available-cash`

### 7.5 research-governance run

`research-governance run` 直接复用 `scripts/run_research_governance_pipeline.py` 的参数：

- `--start-date`
- `--end-date`
- `--initial-capital`
- `--fee-rate`
- `--candidate-config`
- `--log-level`
- `--fail-on-blocked`

### 7.6 status latest

`status latest` 为首版新增命令：

- 默认输出面向人工可读的文本摘要
- `--json` 输出结构化结果，便于脚本消费

它只读取现有 artifact，不触发任何业务流程。

## 8. 内部模块边界

建议新增：

- `scripts/etf_ops.py`
- `src/cli/etf_ops.py`
- `src/cli/status.py`

职责划分：

### 8.1 scripts/etf_ops.py

仅负责：

- 补齐 `sys.path`
- 调用统一 `main(argv)` 入口
- `raise SystemExit(main())`

### 8.2 src/cli/etf_ops.py

负责：

- 构建总命令树
- 子命令分发
- 统一帮助信息
- 调用既有 runner/daily/automation/rg 的适配函数

它不直接承载业务编排逻辑。

### 8.3 src/cli/status.py

负责：

- 读取最近运行 artifact
- 归一化字段
- 输出文本或 JSON 摘要

它不依赖数据库，不创建新 artifact。

### 8.4 旧脚本处理

以下旧脚本继续保留：

- `scripts/run_end_to_end_workflow.py`
- `scripts/run_workflow_automation.py`
- `scripts/daily_run.py`
- `scripts/run_research_governance_pipeline.py`

它们将逐步收敛为薄兼容层：

- 接收旧命令行调用
- 转发到新的统一 CLI 适配函数
- 不再各自维护独立命令树

## 9. 兼容策略与合同稳定性

### 9.1 转发方式

首版采用函数级转发，而不是子进程转发。

原因：

- 更容易保持退出码语义
- 不会额外包裹 stdout/stderr
- 更容易保持 `workflow` 与 `automation` 的稳定 stdout 合同

建议方向：

- 将现有脚本的 `main(argv) -> int` 适配为可复用函数
- 总入口和旧脚本共同调用同一适配层

### 9.2 兼容期行为

旧脚本仍可继续使用：

- 现有调用命令不报错
- 现有自动化脚本无需立刻迁移
- README 和 `--help` 明确推荐迁移到 `python scripts/etf_ops.py ...`

首版不做：

- 强制 deprecated 警告
- 删除旧脚本
- 改动旧脚本参数名

### 9.3 退出码与 stdout 合同

首版必须保持以下稳定性：

- `workflow run` 继续保持现有 `0 / 1 / 2` 语义
- `automation run` 继续保持 wrapper/runner 合同语义
- `workflow` stdout 合同字段保持不变：
  - `run_id`
  - `workflow_manifest`
  - `workflow_status`
  - `publish_executed`
- 这些字段继续以稳定的 `key=value` 单行格式输出
- 对于 `workflow run` / `workflow preflight` / `automation run`，总入口不得在 stdout 合同前后额外插入 banner、说明文本或包装层摘要；额外说明只能走 `stderr` 或 `--help`

总入口不得在这些命令之上再套一层不兼容输出。

## 10. status latest 读取与输出设计

### 10.1 读取优先级

`status latest` 新增可选参数：

- `--workdir <path>`

路径语义：

- 若显式传入 `--workdir`，则把该目录视为 artifact 根基准
- 若未传入，则使用当前进程工作目录（cwd）作为根基准
- automation artifact 与 workflow summary 都按同一根基准解析

原因：

- `automation run --workdir <path>` 已明确把 artifact 写到相对 `workdir` 的 `reports/...`
- 若 `status latest` 只盯 repo root，会读不到外部 workdir 中的最近一次自动化运行
- 以 `cwd/--workdir` 为基准，既兼容 repo 内手工运行，也兼容 `/tmp/workflow_job` 之类的本地半自动目录

`status latest` 首版按以下顺序读取：

1. `<root>/reports/workflow/automation/latest_run.json`
2. `<root>/reports/workflow/end_to_end_workflow_summary.json`

优先 automation 的原因：

- 它更贴近本地半自动实际使用场景
- 包含 wrapper 层的额外诊断字段

若两者都不存在：

- 返回非零退出码
- 输出明确错误，说明尚无可读取的运行记录

### 10.2 归一化字段

无论来源为何，`status latest` 都应归一化出以下字段：

- `source`
- `run_id`
- `status`
- `started_at`
- `finished_at`
- `publish_executed`
- `manifest_path`
- `failed_step`
- `blocked_reasons`
- `suggested_next_action`

映射规则固定如下：

| 归一化字段 | automation latest_run.json | workflow summary |
|---|---|---|
| `source` | 固定为 `automation_latest` | 固定为 `workflow_summary_fallback` |
| `run_id` | `run_id` | `run_id` |
| `status` | `workflow_status` | `status` |
| `started_at` | `automation_started_at` | `started_at` |
| `finished_at` | `automation_finished_at` | `finished_at` |
| `publish_executed` | `publish_executed` | `publish_result.executed`，缺失时按 `false` |
| `manifest_path` | `workflow_manifest` | `workflow_manifest_path` |
| `failed_step` | `failed_step` | `failed_step` |
| `blocked_reasons` | `blocked_reasons`，缺失时按 `[]` | `research_governance_result.blocked_reasons`，缺失时按 `[]` |
| `suggested_next_action` | `suggested_next_action` | 按下面的 fallback 规则派生 |

当来源是 workflow summary 且缺少 `suggested_next_action` 时，按以下规则派生：

- `status = blocked`：`inspect blocked_reasons and governance review status`
- `status = failed` 且存在 `failed_step`：`inspect failed_step=<failed_step> and workflow manifest`
- `status = failed` 且不存在 `failed_step`：`inspect workflow manifest and stage outputs`
- 其他状态：`null`

归一化后的 `manifest_path` 若为相对路径，则相对 `status latest` 的根基准目录解析；若已是绝对路径，则原样保留。

### 10.3 文本输出

默认文本输出至少包含：

- 来源
- 运行 ID
- 状态
- 开始/结束时间
- 是否执行 publish
- manifest 路径

若存在异常上下文，额外显示：

- `failed_step`
- `blocked_reasons`
- `suggested_next_action`

文本输出以“快速判读最近一次运行结果”为目标，不要求完整打印所有底层字段。

### 10.4 JSON 输出

`--json` 输出保持结构化，便于外部脚本消费。

首版不要求额外引入 JSON schema 文件，但测试必须锁定关键字段与来源优先级。

## 11. 错误处理设计

总入口的错误处理遵循“原命令原语义优先”：

- 业务命令错误由原 runner/daily/automation/rg 命令自身决定退出码
- `status latest` 只在读取失败或输入 artifact 结构明显损坏时返回非零
- CLI 分发错误交由 argparse 处理

设计重点：

- 不把多个子系统错误统一包装成新的自定义退出码
- 不引入新的“总入口级 summary artifact”
- 不覆盖原命令 stdout/stderr 行为

## 12. 测试与验收

首版至少覆盖以下测试：

### 12.1 CLI smoke

- `python scripts/etf_ops.py --help`
- `python scripts/etf_ops.py workflow run --help`
- `python scripts/etf_ops.py workflow preflight --help`
- `python scripts/etf_ops.py automation run --help`
- `python scripts/etf_ops.py daily run --help`
- `python scripts/etf_ops.py research-governance run --help`
- `python scripts/etf_ops.py status latest --help`

### 12.2 分发与兼容测试

- `workflow run` 正确调度到现有 workflow runner
- `workflow preflight` 等价于 `workflow run --preflight-only`
- `automation run -- --preflight-only` 保持 `--` 透传
- 旧脚本入口仍可调用，且转发到统一适配层

### 12.3 status latest 测试

- 有 `latest_run.json` 时优先读取 automation 输出
- automation 输出不存在时回退 workflow summary
- `succeeded / blocked / failed` 三种状态下字段归一化正确
- `--json` 输出字段完整
- 没有任何可读 artifact 时返回非零

### 12.4 回归保护

- workflow stdout 合同不变
- automation wrapper 合同不变
- README 新示例切换到总入口
- README 保留旧脚本兼容说明

## 13. 验收标准

本子项目完成后，应满足：

1. 操作者只需记住 `python scripts/etf_ops.py`
2. 高频主链均可由总入口触达
3. 旧脚本不失效
4. `workflow` / `automation` 的退出码与 stdout 合同不漂移
5. `status latest` 能给出最近一次运行的可读结论

## 14. 后续扩展边界

若首版稳定，后续可在同一命令树下逐步纳入：

- `publish`
- `rollback`
- `portal`
- `health`

但这些都不属于本轮 scope。本轮只建立统一入口骨架与高频主链收敛，不提前扩张为完整运维平台。
