# Workflow Runner 运营化与联调闭环设计

## 1. 背景

截至 2026-03-25，项目已经完成统一端到端入口：

- `scripts/run_end_to_end_workflow.py`

它已经具备：

- 默认安全模式
- `blocked / fatal` 退出码语义
- 可选 `daily run`
- 可选 `publish`
- `post-publish health check`
- 结构化 workflow summary

当前主要短板已经不再是“功能缺失”，而是“运营可用性不足”：

- 只有一份“最新 summary”，缺少可审计的单次运行标识与 per-run artifact
- 运行前没有统一预检，自动化场景下很难在真正执行前发现配置/仓储/输出路径问题
- 现有 runner 测试已覆盖编排语义，但对“run 级 artifact 合同”和“自动化消费路径”覆盖不够
- 生产侧聚焦“单一 ETF 实盘”，当前更需要稳定运营、复盘追踪和联调闭环，而不是继续堆叠更复杂策略规则

因此，这一轮目标不是新增策略能力，而是把现有 runner 从“能跑”提升到“可运营、可追踪、可自动化接入”。

## 2. 本子项目已确认选择

本子项目按以下边界设计：

- 继续以 `scripts/run_end_to_end_workflow.py` 作为唯一统一入口
- 新增运行前预检（preflight），并支持 `preflight-only`
- 为每次运行生成唯一 `run_id` 与 per-run manifest
- 保留现有 `reports/workflow/end_to_end_workflow_summary.json` 兼容路径
- 增加面向自动化消费的稳定 stdout 合同
- 增加更接近真实 I/O 的 runner smoke 覆盖

明确不做：

- 新建调度器、后台服务或任务队列
- 自动 rollback
- 放宽当前人工 publish 门禁
- 重写 `daily / research-governance / publish / health` 子系统内部逻辑

## 3. 目标

本子项目需要解决 4 个问题：

1. 运行前就能发现明显阻塞项，并结构化记录预检结果
2. 每次端到端运行都有唯一标识、独立 manifest 和可回放 artifact 路径
3. 自动化脚本/CI 能稳定拿到 `run_id / manifest / status`，不依赖手工读 README
4. runner 自身的 artifact 合同能被 smoke 测试锁住，而不是只测 monkeypatch 顺序

## 4. 非目标

本子项目明确不做：

- 自动调度（cron UI、队列、守护进程）
- 通知系统（飞书、邮件、Webhook）
- 自动审批或自动发布
- 扩展到多账户、多产品线或多策略生产编排
- 为所有子系统增加统一数据库审计表

## 5. 方案选择

本子项目采用：

- 在现有 runner 上继续增强
- 新增少量纯辅助模块承载 preflight / manifest 逻辑
- runner 继续只做 CLI 参数解析和阶段调度

不采用：

### 方案 B：再加一层自动化 wrapper 脚本

例如新增 `scripts/run_end_to_end_automation.py` 再包一层 runner。

不选原因：

- 会产生两套入口语义
- 自动化与人工模式更容易漂移
- 当前规模下收益不足

### 方案 C：直接上服务化 orchestrator

例如后台服务、任务状态机、数据库 run table。

不选原因：

- 对当前单机/脚本形态过重
- 会把本轮从“运营化增强”拉成“新系统建设”
- 超出当前单 ETF 实盘场景需求

## 6. 模块边界

### 6.1 保留现有统一入口

继续使用：

- `scripts/run_end_to_end_workflow.py`

职责：

- 参数解析
- 调度 preflight / daily / research-governance / health / publish
- 汇总 summary / manifest
- 映射退出码

### 6.2 新增纯辅助模块

建议新增：

- `src/workflow/preflight.py`
- `src/workflow/manifest.py`

其中：

- `preflight.py` 负责纯预检逻辑与结果结构
- `manifest.py` 负责 `run_id`、per-run manifest 路径和写盘辅助

它们不直接执行业务流程，不替代现有 CLI。

### 6.3 保持现有领域层不变

继续复用：

- `src/main.py`
- `src/governance_pipeline.py`
- `src/governance/publisher.py`
- `src/governance/health.py`

本轮只消费它们现有能力，不改其核心职责。

## 7. 预检设计

### 7.1 触发时机

预检应在任何实际 workflow 阶段前执行，并写入最终 manifest / summary：

1. 解析 CLI 参数
2. 执行 preflight
3. 若失败：
   - 返回 `1`
   - 记录 `failed_step = "preflight"`
4. 若传 `--preflight-only`：
   - 只输出预检结果
   - 不再执行 daily / research / health / publish

### 7.2 预检内容

预检只检查“轻量、确定、无副作用”的项，不做业务重跑：

- 日期参数可解析
- 策略配置可加载
- 候选配置可解析
- `GovernanceRepository` 可初始化并完成最小访问
- `reports/workflow/` 与 `reports/governance/health/` 可写

预检不应过度阻塞：

- 不要求预先存在 daily report
- 不要求预先存在 research summary
- 不要求预先存在可 publish 的 decision

原因：

- 这些输入本来就是 workflow 执行过程中的产物
- 预检应发现“环境问题”，而不是抢先执行业务判断

### 7.3 预检输出

建议输出：

```json
{
  "status": "passed",
  "checks": [
    {"name": "date_args", "status": "passed", "detail": null},
    {"name": "strategy_config", "status": "passed", "detail": null},
    {"name": "candidate_config", "status": "passed", "detail": null},
    {"name": "governance_repository", "status": "passed", "detail": null},
    {"name": "workflow_output_dir", "status": "passed", "detail": null}
  ],
  "failed_checks": []
}
```

若失败：

- `status = "failed"`
- `failed_checks` 中给出检查名和错误摘要

## 8. Run ID 与 Manifest 设计

### 8.1 Run ID

每次运行生成唯一 `run_id`，建议格式：

- `YYYYMMDDTHHMMSSZ-<shortid>`

要求：

- 在同一秒内也能避免碰撞
- 适合作为目录名
- 适合 stdout 与 artifact 引用
- `Z` 明确表示 UTC

时间约定：

- `run_id` 使用 UTC 时间戳生成
- `started_at` / `finished_at` 使用 ISO 8601 UTC 字符串，例如 `2026-03-25T08:15:30Z`
- 不使用本地时区时间作为 manifest 主时间源，避免跨环境对账歧义

### 8.2 Per-run manifest

建议新增 per-run manifest 路径：

- `reports/workflow/runs/<run_id>/workflow_manifest.json`

manifest 是本次运行的权威结构化产物，包含：

- `run_id`
- `started_at`
- `finished_at`
- `status`
- `exit_code`
- `preflight_result`
- `daily_result`
- `research_governance_result`
- `health_check_result`
- `post_publish_health_check_result`
- `publish_result`

其中：

- per-run manifest 与 legacy summary 必须复用同一 payload 生成逻辑
- 二者 schema 必须一致，只是写入路径不同
- manifest 顶层 `status` 必须与 stdout 中的 `workflow_status` 使用同一枚举和值

### 8.3 兼容路径

为兼容现有使用方，仍保留：

- `reports/workflow/end_to_end_workflow_summary.json`

兼容策略：

- legacy summary 继续存在
- 内容与 per-run manifest 保持同一 schema
- 只是“最近一次运行”的覆盖副本

也就是说：

- 新系统应优先消费 per-run manifest
- 旧系统仍可继续消费 legacy summary

## 9. 自动化消费合同

本轮不新增独立自动化脚本，而是增强现有 runner 的自动化友好度。

### 9.1 CLI 新增参数

建议新增：

- `--preflight-only`

不建议本轮再加更多模式参数，避免入口膨胀。

### 9.2 稳定 stdout

runner 应稳定输出：

- `run_id=<id>`
- `workflow_manifest=<path>`
- `workflow_status=<status>`
- `publish_executed=true|false`

这样自动化脚本可以：

- 先读 stdout 拿到 `run_id / manifest`
- 再解析 manifest 获取完整细节

`workflow_status` 取值固定为：

- `preflight_only`
- `succeeded`
- `blocked`
- `failed`

映射规则：

- `--preflight-only` 且预检通过：`preflight_only`
- 完整 workflow 成功结束：`succeeded`
- 治理结果 `blocked`，无论退出码是 `0` 还是 `2`：`blocked`
- 任一 fatal（含 preflight、daily、research-governance、health、publish、post-publish health）：`failed`

manifest / legacy summary 顶层 `status` 也必须使用这同一组枚举值。

`exit_code` 约束：

- `--preflight-only` 且预检通过：必须返回 `0`
- `--preflight-only` 且预检失败：必须返回 `1`
- `workflow_status=blocked` 时，退出码仍按既有 blocked 语义返回 `0` 或 `2`
- `workflow_status=failed` 时，退出码固定为 `1`

## 10. 失败语义补充

在现有 `failed_step` 基础上，补充：

- `preflight`
- `daily_run`

原因：

- 这两个阶段现在已经是统一入口真实的一部分
- 若失败仍强行归并到其它阶段，会损失诊断准确性

fatal 场景下仍应尽力保留：

- `run_id`
- 已完成阶段结果
- manifest / summary artifact

除非失败点本身发生在 manifest / summary 写盘阶段。

其中 preflight 失败也不例外：

- 仍必须先生成 `run_id`
- 仍必须写出 per-run manifest 与 legacy summary
- 至少包含：
  - `run_id`
  - `started_at`
  - `finished_at`
  - `status = "failed"`
  - `failed_step = "preflight"`
  - `exit_code = 1`
  - `preflight_result`
  - 各阶段默认占位结果

## 11. 测试边界

本轮建议增加 3 层验证：

### 11.1 预检单测

新增：

- `tests/test_workflow_preflight.py`

覆盖：

- 全部检查通过
- 单项失败能落到 `failed_checks`
- `--preflight-only` 的 runner 语义

### 11.2 Manifest / runner 合同测试

增强：

- `tests/test_end_to_end_workflow_runner.py`

覆盖：

- `run_id` 与 manifest 路径写入
- preflight 失败 / preflight-only
- legacy summary 与 per-run manifest 共存
- stdout 稳定输出 `run_id / workflow_manifest / workflow_status`

### 11.3 Runner smoke

新增：

- `tests/test_end_to_end_workflow_runner_cli_smoke.py`

重点：

- 使用 `tmp_path`
- 让 runner 真实写出 manifest / health report / legacy summary
- 锁定 pre/post publish health 工件、per-run manifest 路径和 stdout 合同

约束：

- 仍允许 stub 上游 service 边界
- 不重复验证 daily / research / publish 子系统内部业务逻辑

## 12. 风险与控制

主要风险：

- runner 继续膨胀成“超级脚本”
- preflight 检查过重，误把业务前置条件当环境阻塞
- manifest 与 legacy summary schema 漂移

控制策略：

- 把 preflight / manifest 抽到独立辅助模块
- 预检只做轻量、无副作用检查
- per-run manifest 与 legacy summary 复用同一 payload 生成逻辑
- 用 smoke 测试锁住 artifact 合同

## 13. 完成标志

本子项目完成后，应达到：

- runner 每次运行都有唯一 `run_id`
- 有 per-run manifest，也保留 legacy summary
- 支持 `--preflight-only`
- 预检失败时能输出结构化失败结果
- 自动化可以稳定拿到 `run_id / manifest / status`
- smoke 测试能锁住这些合同
