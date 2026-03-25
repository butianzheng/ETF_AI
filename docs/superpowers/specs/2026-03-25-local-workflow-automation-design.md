# Local Workflow Automation Wrapper 设计

## 1. 背景

截至 2026-03-25，项目已经完成：

- `scripts/run_end_to_end_workflow.py` 统一端到端入口
- `run_id / workflow_manifest / workflow_status / publish_executed` stdout 合同
- per-run manifest：`reports/workflow/runs/<run_id>/workflow_manifest.json`
- legacy summary：`reports/workflow/end_to_end_workflow_summary.json`
- runner smoke 与自动化消费合同测试

当前短板不再是“runner 本身缺少可消费输出”，而是“本地自动化层还没有形成稳定闭环”：

- 还没有一个面向本地脚本/cron 的独立自动化入口
- 还没有把 `workflow_manifest` 变成自动化层的一等 artifact
- 还没有本地 run 索引，无法快速按 `run_id` 查最近成功/失败
- 还没有稳定的失败摘要输出，人工排查仍要手工翻多个 JSON

因此，这一轮目标不是继续增强业务编排，而是增加一个“自动化消费层”，把现有 runner 的输出稳定沉淀为：

- 可脚本化调用
- 可索引追踪
- 可人工诊断

## 2. 本子项目已确认选择

本子项目按以下边界设计：

- 本地脚本优先，不先做 GitHub Actions
- 新增独立 wrapper 脚本，不污染现有人工入口
- wrapper 通过子进程真实调用 `scripts/run_end_to_end_workflow.py`
- 自动化索引放在文件系统，不引入 SQLite
- 自动化层只引用现有 artifact 路径，不复制文件
- 自动化层同时覆盖机器消费索引与人工失败摘要

明确不做：

- 定时调度器、守护进程、任务队列
- 飞书/邮件/Webhook 告警
- 新的数据库 run table
- artifact 复制/归档搬运
- 重写现有 runner 的业务阶段逻辑

## 3. 目标

本子项目需要解决 4 个问题：

1. 本地脚本能以“真实自动化方式”稳定调用现有 runner
2. 每次运行都能落一条轻量 run 索引，便于按 `run_id` 与状态追踪
3. `blocked / failed / 合同损坏` 时，人工能直接看到摘要而不是手工拼路径
4. wrapper 自身的消费合同能被 smoke 测试锁住，而不是只测 helper 单元逻辑

## 4. 非目标

本子项目明确不做：

- cron 配置管理 UI
- GitHub Actions 工作流编排
- 告警发送通道
- artifact 生命周期清理策略
- 多账户、多环境、多 runner 编排

## 5. 方案选择

本子项目采用：

- 独立 Python wrapper 脚本
- 子进程调用现有 runner
- 文件系统 JSON / JSONL 索引
- 独立 failure attention 摘要

不采用：

### 方案 B：继续扩展 `scripts/run_end_to_end_workflow.py`

例如增加 `--automation-mode`、`--write-run-index` 等参数。

不选原因：

- 会把人工入口与自动化入口职责重新耦合
- runner 容易继续膨胀成“超级脚本”
- 自动化消费层的失败语义与业务编排语义会缠在一起

### 方案 C：shell wrapper + 文本工具解析

例如 bash + grep/sed/jq 方案。

不选原因：

- 测试性差
- 结构化错误处理弱
- 后续演进到更复杂索引/摘要时可维护性差

### 方案 D：直接上完整自动化框架

例如一步到位做 run registry、保留策略、告警钩子、调度集成。

不选原因：

- 范围过大
- 会把本轮从“本地自动化消费层”拉成“新系统建设”
- 当前单机/本地脚本优先场景下收益不足

## 6. 模块边界

### 6.1 保留现有业务编排入口

继续使用：

- `scripts/run_end_to_end_workflow.py`

职责保持不变：

- 参数解析
- preflight / daily / research-governance / health / publish 调度
- workflow manifest / legacy summary 生成
- 退出码与 stdout 合同输出

### 6.2 新增自动化 wrapper 入口

建议新增：

- `scripts/run_workflow_automation.py`

职责：

- 组装 runner 子进程命令
- 执行并捕获 stdout / stderr / process exit code
- 解析 stdout 合同
- 读取并校验 manifest
- 写自动化索引与 attention 摘要
- 正常情况下继承 runner 退出码；若 wrapper 自身失败则返回 `1`

它不直接执行业务流程，不替代 runner。

### 6.3 新增纯辅助模块

建议新增：

- `src/workflow/automation.py`

职责：

- stdout 合同解析
- automation record 组装
- latest / history / attention 写盘
- attention 判定
- contract error 结构化输出

它不负责子进程执行与 CLI 参数解析。

## 7. 自动化目录设计

自动化层固定写入：

- `reports/workflow/automation/run_history.jsonl`
- `reports/workflow/automation/latest_run.json`
- `reports/workflow/automation/latest_attention.json`
- `reports/workflow/automation/latest_attention.md`
- `reports/workflow/automation/runs/<automation_run_id>/runner_stdout.log`
- `reports/workflow/automation/runs/<automation_run_id>/runner_stderr.log`

设计原则：

- `run_history.jsonl` 是追加式历史索引
- `latest_run.json` 始终代表最近一次 wrapper 执行结果
- `latest_attention.*` 只在“需要人工关注”时更新
- 自动化层只引用现有业务 artifact 路径，不复制 manifest / health / summary 等原文件
- wrapper 自己生成的 stdout / stderr 日志视为自动化层原生 artifact，可单独落盘

## 8. 索引结构设计

### 8.0 Automation Run ID

wrapper 每次执行都必须生成唯一 `automation_run_id`，作为自动化层自己的稳定主键。

建议格式：

- `YYYYMMDDTHHMMSSZ-<shortid>`

要求：

- 路径安全
- 与现有 `run_id` 风格一致
- 即使 runner 完全没有输出 `run_id`，自动化层仍可凭 `automation_run_id` 建索引与落日志

### 8.1 历史索引字段

`run_history.jsonl` 与 `latest_run.json` 使用同一 schema，至少包含：

- `automation_run_id`
- `automation_started_at`
- `automation_finished_at`
- `runner_command`
- `runner_process_exit_code`
- `wrapper_exit_code`
- `run_id`
- `workflow_manifest`
- `workflow_status`
- `publish_executed`
- `manifest_exit_code`
- `failed_step`
- `blocked_reasons`
- `health_check_report_path`
- `post_publish_health_check_report_path`
- `research_governance_pipeline_summary_path`
- `runner_stdout_path`
- `runner_stderr_path`

来源原则：

- runner 进程事实来自 stdout 与 process exit code
- 业务阶段细节来自 `workflow_manifest`
- `health_check_report_path` 派生自 `health_check_result.report_path`
- `post_publish_health_check_report_path` 派生自 `post_publish_health_check_result.report_path`
- `research_governance_pipeline_summary_path` 派生自 `research_governance_result.pipeline_summary`
- 上述派生字段允许为 `null`
- 自动化层不再生成第二份“业务 summary”

### 8.2 更新规则

每次 wrapper 运行完成后：

1. 追加一条 `run_history.jsonl`
2. 覆盖写 `latest_run.json`
3. 仅当需要人工关注时，才同时刷新 `latest_attention.json` 与 `latest_attention.md`

当 `workflow_status = succeeded` 时：

- 不覆盖现有 `latest_attention.*`

原因：

- 避免刚发生的失败/blocked 线索被后续成功运行冲掉

## 9. 失败摘要设计

attention 范围固定覆盖：

- `workflow_status = blocked`
- `workflow_status = failed`
- automation contract error

`latest_attention.json` 至少包含：

- `attention_type`
- `automation_run_id`
- `run_id`
- `workflow_status`
- `failed_step`
- `blocked_reasons`
- `workflow_manifest`
- `health_check_report_path`
- `post_publish_health_check_report_path`
- `research_governance_pipeline_summary_path`
- `runner_process_exit_code`
- `runner_stdout_path`
- `runner_stderr_path`
- `suggested_next_action`

`latest_attention.md` 采用面向人工的固定摘要结构：

- 自动化运行标识：`automation_run_id`
- 业务运行标识：`run_id`（若存在）
- 当前状态：`workflow_status`
- 失败阶段或 blocked 原因
- manifest 路径
- 关键关联 artifact 路径
- runner stdout / stderr 路径
- 建议动作，例如：
  - 先打开 manifest 核对阶段结果
  - 若是 `blocked`，判断是否需要人工审批/重新研究
  - 若是 `failed`，优先检查 `failed_step` 对应输入环境或输出目录

## 10. 执行语义

### 10.1 调用方式

wrapper 必须通过子进程真实执行。

概念上等价于：

- `python /abs/path/to/scripts/run_end_to_end_workflow.py ...`

不采用 import `main()` 直调。

原因：

- 更贴近真实本地自动化入口
- 能覆盖 stdout 合同与进程退出码
- 后续接 cron 时无需改消费逻辑

### 10.2 工作目录策略

wrapper 必须使用 runner 脚本绝对路径启动子进程，并显式设置子进程 `cwd`：

- 生产默认：repo root
- 测试 / 隔离场景：允许覆盖到指定工作目录，例如 `tmp_path`
- 当 `cwd` 不是 repo root 时，wrapper 需要先在目标工作目录下准备只读 `config -> <repo>/config` 符号链接

原因：

- 当前部分代码仍通过默认 `ConfigLoader()` 读取相对 `config/`
- runner 代码与配置仍来自 repo
- `reports/...` 等相对输出路径则写入目标工作目录
- 这样既能做真实自动化 smoke，又不会污染仓库内真实 `reports/`

### 10.3 退出码语义

wrapper 需要同时区分两类退出码：

- `runner_process_exit_code`：始终记录 runner 真实退出码
- `wrapper_exit_code`：wrapper 自己对外返回的退出码

正常情况下，`wrapper_exit_code` 直接继承 runner 退出码：

- `0`：成功，或 blocked 但 runner 返回 0
- `2`：blocked 且启用 `--fail-on-blocked`
- `1`：preflight 失败或 fatal

若 wrapper 自身失败（例如 contract error、索引写盘失败），则：

- `wrapper_exit_code = 1`
- 但 `runner_process_exit_code` 仍保留 runner 原始值

这样自动化层既能保留 runner 事实，也能在消费层自失败时给出统一非零码。

## 11. 合同校验设计

wrapper 不应盲信 stdout，应做轻量校验：

### 11.1 stdout 合同校验

以下字段缺任意一个，都视为 contract error：

- `run_id`
- `workflow_manifest`
- `workflow_status`
- `publish_executed`

若缺失导致无法获得 runner `run_id`：

- `run_id` 允许为 `null`
- 仍必须生成 `automation_run_id`
- 仍必须落 `runner_stdout_path` 与 `runner_stderr_path`

### 11.2 manifest 校验

若 `workflow_manifest` 路径不存在，视为 contract error。

### 11.3 stdout / manifest 一致性校验

至少校验：

- stdout `run_id` == manifest `run_id`
- stdout `workflow_status` == manifest `status`
- 当 wrapper 未自失败时，`runner_process_exit_code` 与 manifest `exit_code` 一致
- 当 manifest 中嵌套路径缺失时，派生字段按 `null` 处理，而不是自行补默认值

contract error 处理要求：

- 写入 `run_history.jsonl` 与 `latest_run.json`
- 刷新 `latest_attention.json` 与 `latest_attention.md`
- `attention_type = "automation_contract_error"`
- `wrapper_exit_code = 1`

## 12. 测试边界

本轮建议增加 3 层验证：

### 12.1 自动化辅助单测

新增：

- `tests/test_workflow_automation.py`

覆盖：

- stdout 合同解析
- history/latest 写盘
- attention 判定
- contract error 结构

### 12.2 wrapper 函数级测试

新增：

- `tests/test_workflow_automation_runner.py`

覆盖：

- `succeeded`
- `blocked`
- `failed`
- contract error

允许 stub 子进程结果与 manifest 文件，不重复验证业务编排内部逻辑。

### 12.3 wrapper CLI smoke

新增：

- `tests/test_workflow_automation_cli_smoke.py`

重点：

- 真实调用 `scripts/run_workflow_automation.py`
- wrapper 再真实调用现有 runner
- 用 runner 脚本绝对路径 + 隔离 `cwd=tmp_path` 的方式隔离写盘
- smoke 预先按正式语义准备工作目录输入兜底：
  - `config -> <repo>/config`
- 在 `tmp_path` 下断言：
  - `run_history.jsonl`
  - `latest_run.json`
  - `latest_attention.json`
  - `latest_attention.md`
  - 以及它们正确引用 `workflow_manifest`
- 增加一个序列语义断言：
  - 先跑一轮 `blocked` 或 `failed`
  - 再跑一轮 `succeeded`
  - 断言 `latest_attention.*` 仍保留上一次需人工关注的内容，不被成功运行覆盖

## 13. 风险与控制

主要风险：

- wrapper 与 runner 合同漂移
- 自动化索引变成第二套事实源
- attention 摘要被成功运行覆盖，导致排障线索丢失

控制策略：

- 通过真实子进程消费 stdout 合同
- 所有业务细节都回指 `workflow_manifest`
- `latest_attention.*` 只在需要人工关注时更新
- 用 wrapper smoke 测试锁住真实消费闭环

## 14. 完成标志

本子项目完成后，应达到：

- 存在独立本地自动化入口 `scripts/run_workflow_automation.py`
- 本地脚本可稳定调用 runner；正常继承 runner 退出码，wrapper 自身失败时返回 `1`
- 每次运行都会落 `run_history.jsonl` 与 `latest_run.json`
- `blocked / failed / contract error` 会刷新 `latest_attention.json` 与 `latest_attention.md`
- attention 与历史索引都能回指现有 `workflow_manifest`
- smoke 测试能锁住这条自动化消费闭环
