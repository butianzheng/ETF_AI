# 本地半自动使用说明

本文档面向当前阶段的实际使用方式，重点覆盖：

- 单一 ETF 实盘/半自动持有场景
- 研究与治理链路的本地执行
- `automation run` + `status latest/runs/show` 的诊断方式
- 常用产物目录、返回码和排障入口

当前建议的统一入口是：

```bash
python scripts/etf_ops.py ...
```

旧脚本仍可用，但更建议把日常操作收口到统一 CLI。

## 1. 适用范围

当前生产侧默认按“单一 ETF 持有”设计：

- 任一时点只持有 1 只 ETF，或者空仓
- 日常使用建议先走“半自动”方式
- 先看结果、再人工确认、最后决定是否执行

这意味着当前最推荐的顺序不是“直接自动跑完全部动作”，而是：

1. 先跑日常或 workflow 预检
2. 查看状态与产物
3. 人工确认
4. 再决定是否执行调仓或发布

## 2. 基础准备

### 2.1 安装依赖

```bash
pip install -r requirements.txt
```

### 2.2 配置环境变量

```bash
cp config/.env.example config/.env
```

至少补齐：

- `OPENAI_API_KEY`

### 2.3 检查核心配置

建议至少确认以下文件：

- `config/strategy.yaml`
- `config/etf_pool.yaml`
- `config/agent.yaml`
- `config/research.yaml`

### 2.4 初始化数据库

```bash
python scripts/init_db.py
```

## 3. 推荐入口总览

### 3.1 日常单 ETF 运行

```bash
python scripts/etf_ops.py daily run --date 2026-03-26
python scripts/etf_ops.py daily run --date 2026-03-26 --manual-approve
python scripts/etf_ops.py daily run --date 2026-03-26 --manual-approve --execute
python scripts/etf_ops.py daily run --date 2026-03-26 --available-cash 100000
```

说明：

- `--manual-approve` 表示人工已确认
- `--execute` 表示通过检查后执行模拟调仓
- `--available-cash` 用于指定初始或可用现金

### 3.2 研究治理链路

```bash
python scripts/etf_ops.py research-governance run --start-date 2025-12-01 --end-date 2026-03-24
python scripts/etf_ops.py research-governance run --start-date 2025-12-01 --end-date 2026-03-24 --fail-on-blocked
```

适合场景：

- 想先跑研究候选集合
- 想看治理是否放行
- 想在正式发布前先观察 blocked/failed 原因

### 3.3 端到端 workflow

```bash
python scripts/etf_ops.py workflow preflight --start-date 2025-12-01 --end-date 2026-03-24
python scripts/etf_ops.py workflow run --start-date 2025-12-01 --end-date 2026-03-24 --run-daily --daily-date 2026-03-26
python scripts/etf_ops.py workflow run --start-date 2025-12-01 --end-date 2026-03-24 --run-daily --daily-date 2026-03-26 --daily-manual-approve --daily-execute --fail-on-blocked
```

说明：

- `workflow preflight` 只做预检，不推进后续执行
- `workflow run` 可串起 daily + research governance + publish health 流程
- 如果你只是日常单 ETF 调仓，通常先用 `daily run`
- 如果你要验证整条编排链路，再用 `workflow preflight/run`

## 4. 本地 automation wrapper 用法

如果你想把一次 workflow 运行包装成稳定的“可诊断运行记录”，推荐使用：

```bash
python scripts/etf_ops.py automation run -- --preflight-only
python scripts/etf_ops.py automation run --workdir /tmp/workflow_job -- --start-date 2025-12-01 --end-date 2026-03-24
python scripts/etf_ops.py automation run --workdir /tmp/workflow_job -- --start-date 2025-12-01 --end-date 2026-03-24 --fail-on-blocked
```

规则：

- `automation run` 自己只识别 `--workdir`
- 真正透传给 workflow runner 的参数放在 `--` 后面
- 不传 `--workdir` 时，产物默认写到 repo root 下的 `reports/workflow/**`
- 传了 `--workdir` 时，wrapper 会把 runner 的工作目录切到该目录

推荐习惯：

1. 先用 `--preflight-only` 验证链路
2. 再用真实日期区间重跑
3. 运行完成后立刻用 `status latest --json` 看 `effective_workdir`

## 5. 状态查询与排障

### 5.1 看最近一次运行

```bash
python scripts/etf_ops.py status latest
python scripts/etf_ops.py status latest --json
python scripts/etf_ops.py status latest --workdir /tmp/workflow_job --json
```

读取规则：

1. 优先读取 `reports/workflow/automation/latest_run.json`
2. 若其中带有 `artifact_index_path` 且目标可用，则优先读取 `artifact_index.json`
3. 若索引缺失，则回退到 legacy latest 记录
4. 只有 `latest_run.json` 整个缺失时，才回退到 workflow summary

### 5.2 列历史运行

```bash
python scripts/etf_ops.py status runs
python scripts/etf_ops.py status runs --limit 20
python scripts/etf_ops.py status runs --json
python scripts/etf_ops.py status runs --workdir /tmp/workflow_job --json
```

适合场景：

- 想看最近几次 automation 运行结果
- 想按 `automation_run_id` 反查某次问题
- 想快速区分成功、blocked、failed、contract error

注意：

- `--limit` 必须是正整数
- history 坏行会跳过
- 如果没有任何有效记录，命令会返回非零

### 5.3 看某一次详情

```bash
python scripts/etf_ops.py status show --run-id auto-20260324-001
python scripts/etf_ops.py status show --run-id 20260324T101530Z
python scripts/etf_ops.py status show --run-id auto-20260324-001 --json
python scripts/etf_ops.py status show --run-id 20260324T101530Z --workdir /tmp/workflow_job --json
```

规则：

- `--run-id` 可以传 `automation_run_id`
- 也可以传 workflow `run_id`
- 如果两者都可能命中，优先精确命中 `automation_run_id`

### 5.4 `effective_workdir` 怎么理解

`effective_workdir` 是本次运行最终实际落盘的产物根目录。

这点很重要，因为：

- 你请求的目录不一定就是最终落盘目录
- 某些情况下 wrapper 会回退到 repo root 写产物
- `artifact_index_path`、`latest_run.json`、`run_history.jsonl` 都相对 `effective_workdir` 解析

推荐操作：

```bash
python scripts/etf_ops.py status latest --json
```

先看返回里的：

- `effective_workdir`
- `outputs_fallback_used`

如果 `outputs_fallback_used=true`，后续 `status runs/show` 就要以该 `effective_workdir` 为准。

## 6. 关键产物目录

以下路径都相对某次运行的 `effective_workdir`：

### 6.1 automation 层

- `reports/workflow/automation/latest_run.json`
- `reports/workflow/automation/run_history.jsonl`
- `reports/workflow/automation/latest_attention.json`
- `reports/workflow/automation/latest_attention.md`
- `reports/workflow/automation/runs/<automation_run_id>/artifact_index.json`
- `reports/workflow/automation/runs/<automation_run_id>/runner_stdout.log`
- `reports/workflow/automation/runs/<automation_run_id>/runner_stderr.log`

### 6.2 workflow 层

- `reports/workflow/end_to_end_workflow_summary.json`
- `reports/workflow/runs/<run_id>/workflow_manifest.json`

### 6.3 研究与治理层

- `reports/research/`
- `reports/research/summary/`
- `reports/governance/`

## 7. 返回码约定

建议至少记住这三类：

- `0`：命令按预期完成
- `1`：命令失败，或状态工件损坏/缺失到无法可靠读取
- `2`：典型用于 blocked 或参数错误这类“明确非成功但有语义区分”的情况

其中：

- `research-governance run --fail-on-blocked` 遇到 blocked 可返回 `2`
- `workflow run --fail-on-blocked` 遇到 blocked 可返回 `2`
- `status runs --limit 0` 或非整数参数会走参数错误

## 8. 单一 ETF 场景的推荐日常流程

如果你当前就是“单一 ETF 实盘/半自动持有”，建议按这个顺序：

### 8.1 盘前或开盘前先跑日常检查

```bash
python scripts/etf_ops.py daily run --date 2026-03-26
```

先看：

- 选中的 ETF 是否合理
- 是否被风控/检查拦住
- 当天报告是否完整

### 8.2 人工确认后再执行

```bash
python scripts/etf_ops.py daily run --date 2026-03-26 --manual-approve --execute
```

如果你暂时只想演练流程，不要加 `--execute`。

### 8.3 需要串 workflow 时先走 preflight

```bash
python scripts/etf_ops.py workflow preflight --start-date 2025-12-01 --end-date 2026-03-24
```

### 8.4 需要保留可诊断运行记录时用 automation wrapper

```bash
python scripts/etf_ops.py automation run --workdir /tmp/workflow_job -- --preflight-only
python scripts/etf_ops.py status latest --workdir /tmp/workflow_job --json
```

### 8.5 有异常时按这条线排查

1. 先看 `status latest --json`
2. 再看 `status runs`
3. 再用 `status show --run-id <id>`
4. 最后去看：
   - `artifact_index.json`
   - `runner_stdout.log`
   - `runner_stderr.log`
   - `workflow_manifest.json`

## 9. 常见问题

### 9.1 为什么 `status latest` 读不到我刚刚那次运行？

优先检查：

1. 你查询时传的 `--workdir` 是否和运行时一致
2. 那次运行是否发生了 fallback
3. `status latest --json` 里的 `effective_workdir` 是什么

### 9.2 为什么 `status show` 查不到？

常见原因：

- 传错了 `automation_run_id` / `run_id`
- 查询目录不对
- 历史记录文件损坏或为空

### 9.3 为什么明明有 `latest_run.json`，状态命令还是失败？

这是预期保护行为之一。当前实现不会静默掩盖损坏工件：

- `latest_run.json` 存在但缺字段/损坏：返回失败
- `artifact_index.json` 存在但损坏：`latest/show` 返回失败

这样做是为了避免把坏数据误报成“成功读取”。

## 10. 兼容入口

以下脚本仍可直接运行：

- `python scripts/daily_run.py ...`
- `python scripts/run_end_to_end_workflow.py ...`
- `python scripts/run_workflow_automation.py ...`
- `python scripts/run_research_governance_pipeline.py ...`

但建议：

- 日常使用优先走 `python scripts/etf_ops.py ...`
- 兼容脚本更多用于调试、对照和局部排查
