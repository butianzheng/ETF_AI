# Research-To-Governance 统一编排设计

## 1. 背景

截至 2026-03-24，系统已经具备以下独立能力：

- `scripts/run_research.py`
  - 运行候选策略研究并输出研究报告
- `scripts/summarize_research_reports.py`
  - 汇总研究报告并生成研究摘要
- `scripts/run_governance_cycle.py`
  - 基于研究摘要生成/刷新治理 draft，并写出 cycle 产物
- `scripts/run_governance_review.py`
  - 再次执行治理 cycle，并写出 review 产物

当前缺口不在单点能力，而在运维入口：

- 研究到治理仍需要人工按顺序运行多条命令
- `run_governance_cycle.py` 与 `run_governance_review.py` 存在重复边界
- 当前没有一份统一的编排级摘要，自动化很难直接消费整条链路的结果

因此，这一阶段的目标不是新增治理规则，而是补一条稳定、可测试、适合自动化调用的统一编排入口。

## 2. 本阶段已确认选择

本阶段按以下边界设计：

- 只覆盖链路：
  - `research`
  - `summary`
  - `governance cycle`
  - `governance review artifact`
- 新入口既要跑完整链路，也要输出统一摘要
- 本阶段面向“当前执行日”的统一运维入口
  - research 仍可传历史 `start_date/end_date`
  - 但 governance freshness / regime / 产物命名继续沿用当前执行日语义
- 若治理结果为 `blocked`：
  - 行为做成参数可配
  - 默认退出码仍为 `0`
  - 开启 `--fail-on-blocked` 后返回非 `0`
- 保留现有 4 个脚本，不破坏原用法
- 不扩到：
  - `publish`
  - `rollback`
  - `health check`

## 3. 目标

建设一条最小而清晰的统一编排链路，使系统可以：

- 用一条命令跑完 `research -> summary -> governance cycle/review`
- 不依赖解析 CLI stdout，而是直接复用 Python 级函数返回值
- 继续生成原有研究、摘要、治理产物
- 额外输出一份统一 `pipeline summary`
- 让自动化调用方能可靠读取：
  - 每一步是否成功
  - 核心产物路径
  - 最终治理 decision 的关键状态

## 4. 非目标

本阶段明确不做：

- 重写研究流程内部逻辑
- 重写治理评估逻辑
- 引入新的治理状态机
- 自动 publish
- 串上 `health check` 或 `rollback`
- 为旧脚本引入破坏性参数变更
- 为了复用而大范围重构现有脚本

## 5. 推荐方案

本阶段采用：

- 编排服务 + 薄 CLI

而不是：

- 纯 shell/子进程串联多个脚本
- 把编排逻辑继续塞进现有治理脚本

原因：

- 统一编排应直接消费函数返回值，而不是解析终端输出
- 新入口需要写统一摘要和控制退出码，天然更适合单独服务层
- 保留旧脚本可以降低回归风险

## 6. 总体流程

建议新增统一入口：

- `run_research_governance_pipeline(...)`

流程固定为：

1. 运行 research
2. 汇总 research reports
3. 运行 governance cycle
4. 写出 governance review artifact
5. 写出 pipeline summary
6. 根据 `fail_on_blocked` 决定 CLI 退出码

关键原则：

- `governance cycle` 只执行一次
- 不重复跑第二次治理评估
- review artifact 直接复用本次 cycle 已得到的 `decision`
- summary 步骤继续按当前 `aggregate_research_reports()` 语义工作
  - 先写入本次 research 报告
  - 再聚合 `reports/research/*.json` 的全历史集合
  - governance 输入仍是“全历史摘要”，不是“仅本次运行的临时摘要”

## 7. 模块边界

### 7.1 新增服务层

建议新增：

- `src/governance_pipeline.py`

职责：

- 编排 research、summary、governance cycle
- 汇总所有步骤输出
- 写 pipeline summary
- 返回统一结构给 CLI

它不负责：

- publish
- rollback
- health check

### 7.2 新增 CLI

建议新增：

- `scripts/run_research_governance_pipeline.py`

职责：

- 参数解析
- 调用 `src/governance_pipeline.py`
- 打印简洁摘要
- 根据 blocked 状态控制退出码

### 7.3 保留既有入口

继续保留：

- `scripts/run_research.py`
- `scripts/summarize_research_reports.py`
- `scripts/run_governance_cycle.py`
- `scripts/run_governance_review.py`

要求：

- 原有默认参数与行为不变
- 新编排入口是新增能力，不替代旧脚本

## 8. 输入参数设计

建议新 CLI 支持以下参数：

- 研究参数
  - `--start-date`
  - `--end-date`
  - `--initial-capital`
  - `--fee-rate`
  - `--candidate-config`
- 编排参数
  - `--current-strategy-id`
- 退出语义
  - `--fail-on-blocked`

默认行为：

- 不传参数也能跑完整链路
- 默认路径仍沿用现有约定
  - `reports/research`
  - `reports/research/summary`
  - `reports/governance`
  - `reports/governance/cycle`

补充约束：

- 本阶段不把 research / summary / governance 输出目录参数化
- research、summary、governance 继续沿用现有默认目录
- 避免本轮把范围扩成“所有产物目录完全可配”

## 9. 输出产物设计

### 9.1 保留既有产物

统一编排执行后，应继续生成既有产物：

- `reports/research/<date>.md`
- `reports/research/<date>.json`
- `reports/research/<date>.csv`
- `reports/research/summary/*`
- `reports/governance/cycle/<date>.json`
- `reports/governance/<date>.json`
- `reports/index.html`
- `reports/portal_summary.json`

兼容性要求：

- cycle artifact 的结构应与现有 `scripts/run_governance_cycle.py` 写出的 JSON 保持兼容
- review artifact 的结构应与现有 `scripts/run_governance_review.py` 写出的 JSON 保持兼容
- 成功跑完整链路后，portal 产物仍应刷新到最新状态

### 9.2 新增 pipeline summary

建议新增：

- `reports/governance/pipeline/<date>.json`

职责：

- 记录整条编排链路的结构化摘要
- 为自动化与后续运维入口提供稳定消费面

日期口径要求：

- research 产物继续沿用 `end_date` 命名
- governance cycle / review / pipeline summary 继续沿用 orchestration 执行日命名
  - 即与当前 governance 脚本保持一致
- pipeline summary 必须同时写出：
  - `research_end_date`
  - `governance_run_date`

## 10. Pipeline Summary 结构

建议统一写成：

```json
{
  "research_end_date": "2026-03-24",
  "governance_run_date": "2026-03-24",
  "steps": {
    "research": {
      "status": "completed",
      "output_paths": {
        "markdown": "reports/research/2026-03-24.md",
        "json": "reports/research/2026-03-24.json",
        "csv": "reports/research/2026-03-24.csv"
      }
    },
    "summary": {
      "status": "completed",
      "output_paths": {
        "json": "reports/research/summary/research_summary.json"
      }
    },
    "governance_cycle": {
      "status": "completed",
      "review_status": "ready|blocked",
      "decision_id": 12,
      "created_new": true,
      "summary_hash": "..."
    },
    "governance_review": {
      "status": "completed",
      "output_path": "reports/governance/2026-03-24.json"
    }
  },
  "final_decision": {
    "decision_id": 12,
    "review_status": "blocked",
    "blocked_reasons": ["SELECTED_STRATEGY_REGIME_MISMATCH"],
    "created_new": true,
    "summary_hash": "..."
  },
  "fail_on_blocked": false
}
```

要求：

- `blocked` 不是步骤失败，而是业务结果
- 真正异常才使用流程级 failure

## 11. CLI 输出约定

CLI stdout 只打印简洁摘要，便于人工和自动化读取，例如：

```text
research_report=reports/research/2026-03-24.json
summary_json=reports/research/summary/research_summary.json
decision_id=12 review_status=blocked blocked_reasons=SELECTED_STRATEGY_REGIME_MISMATCH
pipeline_summary=reports/governance/pipeline/2026-03-24.json
```

不要求打印冗长 JSON 到 stdout。

## 12. Exit Code 语义

默认语义：

- research / summary / governance 执行成功，即返回 `0`
- 即使最终 `review_status == blocked`，默认也返回 `0`

可选语义：

- 开启 `--fail-on-blocked`
- 若最终 `review_status == blocked`，则 CLI 返回 `2`

这样可以同时满足：

- 人工运维希望拿到完整产物
- 自动化调度希望把 `blocked` 视为失败事件

## 13. 错误处理原则

### 13.1 research 失败

- 直接终止后续步骤
- 不写伪造 summary / governance 结果
- 仍写 partial `pipeline summary`
  - 标明 failed step
  - 标明错误类型与错误信息
- CLI 返回 `1`

### 13.2 summary 失败

- 直接终止治理步骤
- 仍写 partial `pipeline summary`
- CLI 返回 `1`

### 13.3 governance cycle 失败

- 直接终止 review artifact 写出
- 仍写 partial `pipeline summary`
- CLI 返回 `1`

### 13.4 governance blocked

- 仍写出：
  - cycle artifact
  - review artifact
  - pipeline summary
- 仅由 `fail_on_blocked` 决定退出码

### 13.5 review artifact 写出失败

- 视为流程失败
- 不得吞错
- 仍写 partial `pipeline summary`
- CLI 返回 `1`

## 14. 文件边界

### Create

- `src/governance_pipeline.py`
  - 统一编排服务
- `scripts/run_research_governance_pipeline.py`
  - 统一编排 CLI
- `tests/test_research_governance_pipeline.py`
  - 统一编排测试

### Modify

- 允许最小修改以下文件，但仅在必要时：
  - `src/governance/automation.py`
  - `src/research_pipeline.py`
  - `src/research_summary.py`

原则：

- 优先新增，不轻易改旧脚本
- 若旧逻辑已可直接复用，则不为“抽象更漂亮”而重构

### Verify Only

- `scripts/run_research.py`
- `scripts/summarize_research_reports.py`
- `scripts/run_governance_cycle.py`
- `scripts/run_governance_review.py`

## 15. 测试策略

新增 `tests/test_research_governance_pipeline.py`，至少覆盖：

- happy path
  - research、summary、governance cycle/review、pipeline summary 全部产出
- blocked path
  - 默认退出语义仍成功
  - `pipeline summary` 正确记录 `blocked_reasons`
- fail-on-blocked path
  - 当治理结果为 `blocked` 时，CLI 返回 `2`
- fatal error path
  - research / summary / governance / review 任一步抛错时，CLI 返回 `1`
  - partial `pipeline summary` 正确记录 failed step 与错误信息

建议同时验证：

- 统一摘要里的关键路径存在
- `decision_id / review_status / created_new / summary_hash` 被正确透传
- 旧脚本行为未被破坏

## 16. 成功标准

完成后，系统应满足：

- 一条命令可完成 `research -> summary -> governance cycle/review`
- 不依赖解析旧脚本 stdout
- 既有研究/治理产物继续生成
- 新增 `pipeline summary` 可被自动化稳定消费
- `blocked` 退出码语义可配置，默认不把业务阻断误判成程序失败
