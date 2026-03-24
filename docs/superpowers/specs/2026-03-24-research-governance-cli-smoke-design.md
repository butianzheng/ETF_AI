# Research-To-Governance CLI Smoke 设计

## 1. 背景

截至 2026-03-24，`Research-To-Governance` 统一编排已经完成：

- 服务层：`src/governance_pipeline.py`
- CLI：`scripts/run_research_governance_pipeline.py`
- 语义覆盖：
  - `happy path`
  - `blocked + fail_on_blocked`
  - fatal error + partial `pipeline summary`
- 文档与任务跟踪：`README.md`、`tasks/todo.md`

当前缺口不在主功能，而在“运行级信心”：

- 现有测试以 service 单测和 CLI 契约单测为主
- 还没有一组独立 smoke，用真实 `CLI + service` 串起来验证
- 还没有一组测试同时覆盖：
  - `happy path`
  - `blocked`
  - fatal
  - 真实 artifact 落盘

因此，本子项目的目标不是新增功能，而是补一层稳定、快速、可回归的 CLI smoke。

## 2. 本子项目已确认选择

本子项目按以下边界设计：

- 本轮只做 A：
  - `Research-To-Governance CLI smoke`
- B：
  - 抽共享 `candidate-config` 加载 helper
  - 延后到本子项目完成之后
- smoke 覆盖：
  - `happy path`
  - `blocked`
  - fatal
- 测试强度：
  - `CLI + service` 走真实代码
  - 研究/治理内部重依赖用 stub
  - artifact 真实落盘
- 不走子进程
  - 直接调用 `scripts.run_research_governance_pipeline.main(argv)`

## 3. 目标

建设一组独立 smoke，使系统可以：

- 从真实 CLI 入口验证统一编排主链路
- 在临时目录中真实落盘 research / governance / pipeline / portal 产物
- 验证 `happy path`、`blocked`、fatal 三类关键运行语义
- 为后续 B 子项目和更大范围回归提供稳定基础

## 4. 非目标

本子项目明确不做：

- 重写 `src/governance_pipeline.py`
- 重写 `scripts/run_research_governance_pipeline.py`
- 新增 publish / rollback / health check smoke
- 改成真实子进程执行 CLI
- 接入真实市场数据、真实 LLM、真实生产数据库
- 顺手实现 B：共享 `candidate-config` helper 抽取

## 5. 方案选择

本子项目采用：

- 独立 smoke 文件
- 真实 `CLI + service`
- 内部依赖最小 stub

而不是：

- 把 smoke 继续塞进现有 `tests/test_research_governance_pipeline.py`
- 直接起子进程执行 `python scripts/run_research_governance_pipeline.py`
- 尽量真实接通 SQLite / repo / 全部治理依赖

原因：

- 独立文件可以保持 smoke 边界清晰，不和现有语义单测混在一起
- 直接调 `main(argv)` 能测到 CLI，又比子进程方案稳定
- 最小 stub 可以把测试重点放在编排链路和 artifact，而不是外部依赖脆弱性

## 6. 测试边界

### 6.1 入口

统一入口固定为：

- `scripts.run_research_governance_pipeline.main(argv)`

要求：

- 不 mock `main()`
- 不 mock `run_research_governance_pipeline()`
- CLI 参数解析、stdout/stderr、退出码映射都走真实代码

### 6.2 真实落盘

smoke 必须在 `tmp_path` 下真实生成：

- `reports/research/*.json`
- `reports/research/*.md`
- `reports/research/*.csv`
- `reports/research/summary/*`
- `reports/governance/cycle/*.json`
- `reports/governance/*.json`
- `reports/governance/pipeline/*.json`
- `reports/portal_summary.json`

### 6.3 允许 stub 的依赖

允许对以下重依赖做 monkeypatch：

- `run_research_pipeline`
- `aggregate_research_reports`
- `run_governance_cycle`
- `build_report_portal`

约束：

- patched 函数必须返回真实 service 期望的数据结构
- 不允许把整个 service 结果直接 mock 成最终返回值
- 不允许绕过 artifact helper 的真实写盘

## 7. 场景设计

### 7.1 Happy Path Smoke

固定验证：

- 真实调用 CLI `main(argv)`
- 传入真实：
  - `--start-date`
  - `--end-date`
  - `--candidate-config`
- service 正常跑完

必须断言：

- CLI 返回 `0`
- stdout 包含：
  - `research_report=...`
  - `summary_json=...`
  - `decision_id=... review_status=... blocked_reasons=...`
  - `pipeline_summary=...`
- cycle / review / pipeline / portal 真实落盘
- `pipeline summary.final_decision.review_status == "ready"`

### 7.2 Blocked Smoke

固定验证：

- 真实调用 CLI `main(argv)`
- `run_governance_cycle()` 返回 `review_status="blocked"`

分两种子场景：

1. 不传 `--fail-on-blocked`
   - CLI 返回 `0`
2. 传 `--fail-on-blocked`
   - CLI 返回 `2`

两种都必须断言：

- cycle / review / pipeline artifact 仍然存在
- `pipeline summary.final_decision.review_status == "blocked"`
- `pipeline summary.final_decision.blocked_reasons` 正确

### 7.3 Fatal Smoke

固定验证：

- 真实调用 CLI `main(argv)`
- 在 pre-governance 阶段制造 fatal
- 默认优先让 `summary` 步骤抛异常，保持断言稳定

必须断言：

- CLI 返回 `1`
- `stderr` 包含 `fatal_error=...`
- partial `pipeline summary` 存在
- partial payload 至少包含：
  - `status == "failed"`
  - `failed_step == "summary"`
  - `error.type`
  - `error.message`
- cycle / review artifact 不存在

## 8. 文件边界

建议新增：

- `tests/test_research_governance_pipeline_cli_smoke.py`

默认不改：

- `scripts/run_research_governance_pipeline.py`
- `src/governance_pipeline.py`

仅当 smoke 无法稳定注入时，才允许对生产代码做最小改动：

- 只增加测试友好的注入点或小型 helper
- 不改变现有 CLI / service 对外语义

## 9. 测试组织

测试文件建议包含：

- 一个 helper：
  - 真实写 `candidate-config` YAML
- 一个 helper：
  - 固定 `tmp_path` 下的 `cwd`
- 少量 helper：
  - 生成最小 research / summary / portal 输入

组织原则：

- `happy path`
- `blocked`
- fatal

每个场景独立成测试函数，不做大参数化。

原因：

- smoke 失败时应当一眼定位
- 不为了压缩代码牺牲可读性

## 10. 验收标准

本子项目完成后，至少要满足：

- `tests/test_research_governance_pipeline_cli_smoke.py` 新增完成
- `pytest tests/test_research_governance_pipeline_cli_smoke.py -q` 通过
- `pytest tests/test_research_governance_pipeline.py tests/test_research_governance_pipeline_cli_smoke.py -q` 通过
- 若引入生产代码改动：
  - 改动必须是最小注入点增强
  - 现有 `CLI + service` 语义不变

## 11. 后续衔接

本子项目完成后，再进入 B：

- 收敛 `candidate-config` YAML 加载逻辑
- 减少 `scripts/run_research.py` 与 `scripts/run_research_governance_pipeline.py` 的重复实现

本 spec 不覆盖 B 的实现细节，避免把两个相对独立子系统混进同一计划。
