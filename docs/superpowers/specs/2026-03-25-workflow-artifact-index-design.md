# Workflow Artifact 索引层设计

## 1. 背景

截至 2026-03-25，项目已经具备：

- `scripts/run_end_to_end_workflow.py` 统一 workflow 编排入口
- `scripts/run_workflow_automation.py` 本地自动化 wrapper
- `reports/workflow/runs/<run_id>/workflow_manifest.json` per-run manifest
- `reports/workflow/end_to_end_workflow_summary.json` legacy summary
- `reports/workflow/automation/latest_run.json`
- `reports/workflow/automation/run_history.jsonl`
- `reports/workflow/automation/latest_attention.json|md`
- `python scripts/etf_ops.py status latest`

当前短板已经不再是“有没有 artifact”，而是“artifact 之间缺少统一索引层”：

- `status latest` 只能看最近一次，不能稳定按 `run_id` 追溯
- `latest_run.json` / `run_history.jsonl` 仍承担兼容记录职责，但不适合继续扩展为完整诊断视图
- per-run manifest、runner stdout/stderr、health report、research summary 已存在，但缺少稳定的一跳入口
- 后续若要做本地定时触发、告警或人工排障，会重复实现同一套路径拼接与 fallback 逻辑

因此，本轮目标不是再增加新的业务流程，而是把现有 workflow / automation artifact 收敛成一层稳定的“文件系统索引面”。

## 2. 本子项目已确认选择

本子项目按以下边界设计：

- 优先建设 artifact 索引层，再让 CLI / 告警 / 定时任务复用
- 第一版只覆盖 `workflow/automation` 这条链路
- 继续使用文件系统，不引入 SQLite
- 采用“per-run snapshot + latest/history 兼容记录”方案
- 新增只读 CLI 诊断入口，但挂在现有 `status` 子命令下
- 不做历史数据一次性回填，旧数据以 fallback 兼容

明确不做：

- 新数据库 run registry
- GitHub Actions / CI 工作流建设
- artifact 归档搬运或保留策略
- 模糊搜索、交互式 TUI、tail/open 等高阶诊断命令
- 对既有 workflow runner / automation stdout 合同做破坏性改名

## 3. 目标

本子项目需要解决 4 个问题：

1. 每次 automation 运行后，都能生成一份标准化的 per-run artifact 索引快照
2. `latest_run.json` 与 `run_history.jsonl` 可以引用该快照，而不是重复承载完整诊断语义
3. 统一 CLI 可以新增“列最近运行”和“按 run_id 查看详情”能力
4. 新旧 artifact 可以共存，历史数据在不迁移的情况下仍可 best-effort 查询

## 4. 非目标

本子项目明确不做：

- 改写 workflow 业务阶段逻辑
- 改动 publish / governance 审批门禁
- 为历史 artifact 批量补建索引
- 引入多环境、多账户、多 runner 编排
- 把所有脚本都收编到新的 artifact 索引层

## 5. 方案选择

本子项目采用：

- 每次运行写一份标准化 `artifact_index.json`
- 保留 `latest_run.json` / `run_history.jsonl` 现有富记录 schema，并新增索引指针字段
- 查询优先读取 `artifact_index.json`，找不到再做 legacy fallback

不采用：

### 方案 B：单文件总索引

例如新增 `reports/workflow/automation/run_index.json`，把所有运行历史都汇总到一个 JSON。

不选原因：

- 每次运行都要重写整份索引
- 单文件损坏会影响全部查询
- 后续扩展 run 级别诊断字段时冲突更大

### 方案 C：SQLite 本地索引库

例如新增一张 automation run 表，把 artifact 元数据全部入库。

不选原因：

- 会形成“文件 artifact + 数据库索引”双真相
- 对当前单机文件系统场景过重
- 与现有 JSON/JSONL artifact 演进路径不一致

## 6. 模块边界

### 6.1 保留现有 automation helper 职责

继续保留：

- `src/workflow/automation.py`

职责保持为：

- stdout 合同解析
- contract / manifest 校验
- `latest_run.json` / `run_history.jsonl` / `latest_attention.*` / runner logs 写盘

它不承载面向 CLI 的查询与索引读取逻辑。

### 6.2 新增 artifact 索引模块

建议新增：

- `src/workflow/automation_index.py`

职责：

- 组装标准化 per-run artifact index payload
- 写入 `artifact_index.json`
- 解析 `latest_run.json` / `run_history.jsonl` 中的 `artifact_index_path`
- 提供 `latest` / `runs` / `show` 所需的只读查询 API
- 对无 index 的历史记录生成 `legacy_fallback` 视图

它不负责：

- 子进程执行
- CLI 参数解析
- attention 判定

### 6.3 扩展统一 CLI 状态入口

继续使用：

- `src/cli/status.py`
- `src/cli/etf_ops.py`

新增但不拆新顶级命令：

- `status runs`
- `status show --run-id <id>`

`status latest` 保持原命令名不变，但内部优先使用新的 artifact 索引层。

## 7. Artifact 目录与 schema 设计

### 7.1 新增 per-run index 文件

每次 automation 运行完成后新增：

- `reports/workflow/automation/runs/<automation_run_id>/artifact_index.json`

该文件是第一版 run 诊断的核心真相文件。

保留现有 wrapper fallback 语义：

- `requested_workdir` 仍表示用户请求的工作目录
- `effective_workdir` 仍表示实际产出 artifact 的根目录
- 若 `write_automation_outputs(...)` 回退到 repo root，则 `artifact_index.json` 也必须落在同一个 `effective_workdir` 下
- 所有相对路径字段，包括 `artifact_index_path`，统一相对 `effective_workdir` 解析，而不是相对 `requested_workdir`

### 7.2 artifact_index.json 建议字段

至少包含：

- `source`
- `automation_run_id`
- `run_id`
- `workflow_status`
- `automation_started_at`
- `automation_finished_at`
- `wrapper_exit_code`
- `runner_process_exit_code`
- `manifest_path`
- `runner_stdout_path`
- `runner_stderr_path`
- `health_check_report_path`
- `post_publish_health_check_report_path`
- `research_governance_pipeline_summary_path`
- `blocked_reasons`
- `failed_step`
- `suggested_next_action`
- `publish_executed`
- `created_at`
- `requested_workdir`
- `effective_workdir`
- `outputs_fallback_used`

字段要求：

- `source` 对新运行固定为 `artifact_index`
- 路径字段统一保存“相对 effective_workdir 的相对路径”
- `blocked_reasons` 固定为 list
- 允许部分诊断字段为 `null`
- 不复制 manifest / health / summary 文件内容，只保留路径

### 7.3 latest / history 的兼容扩展

保留：

- `reports/workflow/automation/latest_run.json`
- `reports/workflow/automation/run_history.jsonl`

但新增字段：

- `artifact_index_path`

要求：

- `artifact_index_path` 也是相对 `effective_workdir` 的相对路径
- `latest_run.json` / `run_history.jsonl` 在 v1 保留 current schema，不做瘦身，只额外新增 `artifact_index_path`
- 历史记录与 latest 都必须引用已经写成功的 `artifact_index.json`
- `requested_workdir` / `effective_workdir` / `outputs_fallback_used` 继续保留为兼容字段
- 旧记录允许没有该字段

## 8. 写入时机与失败语义

### 8.1 写入顺序

每次 `automation run` 完成后按以下顺序执行：

1. 执行 runner 子进程并获得 stdout/stderr/exit code
2. 写 `runner_stdout.log` / `runner_stderr.log`
3. 解析 stdout 合同并读取 manifest
4. 确定本次 automation 输出的最终根目录；若主输出根不可写，可沿用现有逻辑回退到 repo root
5. 基于最终 `effective_workdir` 组装标准化 `artifact_index.json` 与所有带路径字段的 latest/history/attention payload
6. 将 `artifact_index.json` 写到最终 `effective_workdir`
7. 将带有 `artifact_index_path` 的 `latest_run.json`、`run_history.jsonl`、`latest_attention.*` 写到同一个 `effective_workdir`

原因：

- 避免 latest/history 先引用一个尚未存在的 index 文件
- 保证“按 latest/history 跳转到 per-run index”是一跳可用的
- 保证 `artifact_index.json` 与 latest/history/attention 不会落在不同根目录
- 若写盘过程中发生 fallback，必须基于最终 `effective_workdir` 重建全部相对路径字段后再重试写盘，不能复用第一次按旧根目录组装的 payload

### 8.2 索引写失败语义

如果主输出根写入 `artifact_index.json` 失败：

- 允许沿用现有 `write_automation_outputs(...)` 的 repo root fallback 语义
- 只有当最终 `effective_workdir` 下仍无法写出 `artifact_index.json` 时，才视为失败

如果最终 `effective_workdir` 下 `artifact_index.json` 仍写入失败：

- wrapper 退出码统一返回 `1`
- 视为 `automation_contract_error`
- 刷新 `latest_attention.*`
- `suggested_next_action` 指向索引写入失败或索引校验失败

不允许静默降级为“业务成功但不可诊断”。

## 9. 查询语义

### 9.1 status latest

读取优先级：

1. 读取 `latest_run.json`
2. 若存在 `artifact_index_path` 且目标文件存在，则读 `artifact_index.json`
3. 若 `artifact_index_path` 缺失或目标文件不存在，则 fallback 到当前 `latest_run.json` 直读归一化
4. 只有当 `latest_run.json` 整个文件缺失时，才 fallback 到 `end_to_end_workflow_summary.json`

失败矩阵必须写死：

- `latest_run.json` 缺失：允许回退到 workflow summary
- `latest_run.json` 存在但 JSON 损坏 / 缺字段：返回 `1`
- `artifact_index_path` 缺失：回退到 `latest_run.json` 直读
- `artifact_index_path` 指向文件不存在：回退到 `latest_run.json` 直读
- `artifact_index.json` 存在但 JSON 损坏 / 缺字段：返回 `1`
- workflow summary 仅在 automation latest 缺失时参与 fallback；summary 自身若损坏，同样返回 `1`

输出要求：

- `--json` 时 stdout 仅输出 JSON
- 文本模式保留当前可读摘要语义
- 有 index 时优先输出 index 视图

### 9.2 status runs

命令形态：

```bash
python scripts/etf_ops.py status runs
python scripts/etf_ops.py status runs --limit 20
python scripts/etf_ops.py status runs --json
python scripts/etf_ops.py status runs --workdir /tmp/workflow_job
```

语义：

- 默认从 `run_history.jsonl` 读取最近记录
- 每条记录优先跳到 `artifact_index.json`
- 对无 index 的旧记录生成轻量 `legacy_fallback` 视图
- 默认按最近完成时间倒序输出

历史扫描规则：

- `run_history.jsonl` 的坏行、截断尾行默认跳过，不中断整个命令
- 若某条记录引用的 `artifact_index.json` 不存在，则回退为该条记录的 `legacy_fallback` 视图
- 若某条记录引用的 `artifact_index.json` 存在但损坏，则该条记录退回 `legacy_fallback_index_error` 视图，避免整条列表不可用
- 若扫描后没有任何有效记录，命令返回 `1`

首版输出字段：

- `automation_run_id`
- `run_id`
- `status`
- `finished_at`
- `wrapper_exit_code`
- `failed_step`

### 9.3 status show

命令形态：

```bash
python scripts/etf_ops.py status show --run-id 20260325T010203Z-abcd1234
python scripts/etf_ops.py status show --run-id 20260325T010203Z-abcd1234 --json
python scripts/etf_ops.py status show --run-id 20260325T010203Z-a1b2c3d4 --workdir /tmp/workflow_job
```

语义：

- `--run-id` 同时接受 `automation_run_id` 或 workflow `run_id`
- 先精确匹配 `automation_run_id`
- 再精确匹配 workflow `run_id`
- 不做模糊匹配
- 命中 index 时输出完整诊断视图
- 老记录无 index 时，返回 `source=legacy_fallback` 的重建视图
- 历史扫描时坏行、截断尾行默认跳过
- 若 workflow `run_id` 命中多条记录，则返回 `automation_finished_at` 最近的一条；若仍并列，则取 `run_history.jsonl` 中较后的那条
- 若匹配记录的 index 文件不存在，则回退为 `legacy_fallback`
- 若匹配记录的 index 文件存在但损坏，则返回 `1`
- 未找到记录时返回 `1`

路径要求：

- JSON 输出中提供解析后的绝对路径，便于直接定位 manifest / logs / report
- 文本输出保留核心字段，不展开超长 JSON 结构

## 10. 兼容与迁移策略

第一版不做历史回填脚本。

兼容规则：

- 新运行必须产出 `artifact_index.json`
- 旧运行没有 `artifact_index_path` 时仍可查询
- fallback 查询只保证 best-effort，不保证旧记录具备完整诊断字段
- `latest_run.json` / `run_history.jsonl` 的 current schema 与兼容字段继续保留，既有消费者不需要立即修改

这意味着第一版的重点是“让未来新运行具备稳定索引面”，而不是改造全部历史数据。

## 11. 测试与验收

至少需要覆盖：

- 新运行成功写出 `artifact_index.json`
- `latest_run.json` / `run_history.jsonl` 成功回填 `artifact_index_path`
- `status latest` 在有 index 场景下优先读 index
- `status latest` 在无 index 场景下保持现有 fallback 行为
- `status runs` 可列出新旧记录混合历史
- `status show --run-id` 可分别命中 `automation_run_id` 与 workflow `run_id`
- `status latest` 对“缺失”和“损坏”采用不同失败语义，不静默掩盖损坏
- `status runs` / `status show` 对坏 history 行、缺失 index、损坏 index 有明确且可测试的行为
- `artifact_index.json` 写失败时 wrapper 返回 `1` 且刷新 attention
- `--json` 模式下 stdout 不混入非 JSON 文本

首版验收标准：

1. 新 automation 运行后一定存在 `artifact_index.json`
2. `status latest` 行为不回退
3. `status runs` 与 `status show` 可用于本地半自动排障
4. 旧数据无需迁移也可 best-effort 查询
