# Phase 4 状态感知研究优先 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在不改变单一 ETF 实盘和现有 governance runtime 的前提下，为研究链路增加基于 ETF 池聚合的 regime 标注、样本内/样本外切片和分层分析产物。

**Architecture:** 新增 `src/research/` 包承载三个小模块：`regime.py` 负责池级特征与规则型状态判定，`segmentation.py` 负责研究窗口的样本切片，`regime_analysis.py` 负责把每日标签映射到候选回测结果并输出分层指标。`src/research_pipeline.py` 负责在单次研究中串起这些模块并扩展 JSON/Markdown 报告，`src/research_summary.py` 只做跨报告聚合与展示升级，不把状态判断接回生产。

**Tech Stack:** Python 3.10+, pandas, numpy, pydantic 2.x, pytest, YAML, SQLite

---

> 约束：
> 1. 本阶段仍是研究优先，`src/main.py`、`src/governance/runtime.py`、`src/governance/publisher.py` 不改。
> 2. `regime` 锚点来自 `config/etf_pool.yaml` 中 `enabled=true` 的 ETF 池聚合，不引入单一指数特判。
> 3. 单一 ETF 实盘场景保持不变：本阶段只产出研究证据，不新增生产候选或自动切换逻辑。
> 4. 每个 Task 按 `@superpowers:test-driven-development` 先红后绿，再做最小收敛提交。

## File Structure

### Create

- `src/research/__init__.py`
  显式声明研究子包，导出 `RegimeClassifier`、`RegimeSnapshot`、`build_sample_split_labels`、`analyze_candidate_segments`。
- `src/research/regime.py`
  ETF 池级特征构建、规则型 `RegimeClassifier`、`RegimeSnapshot` 定义。
- `src/research/segmentation.py`
  研究窗口 `in_sample / out_of_sample` 切片工具。
- `src/research/regime_analysis.py`
  候选 `overall / by_regime / by_sample / transition` 聚合逻辑。
- `tests/test_regime_classifier.py`
  锁定配置加载、规则判定、coverage 不足回退。
- `tests/test_regime_analysis.py`
  锁定样本切片、分层指标、transition 统计。

### Modify

- `config/research.yaml`
  增加 `research.regime` 与 `research.sample_split` 配置段。
- `src/core/config.py`
  增加 `ResearchRegimeConfig`、`ResearchSampleSplitConfig` 及其嵌套规则模型。
- `src/research_pipeline.py`
  在单次研究里接入 regime 标签、sample split 和候选分层输出。
- `src/research_summary.py`
  聚合跨报告 `regime_summary`、`candidate_regime_leaderboard`、`candidate_out_of_sample_leaderboard`、`candidate_regime_observations`。
- `tests/test_research_pipeline.py`
  断言研究主流程会输出新字段并保持旧输出兼容。
- `tests/test_research_summary.py`
  断言研究汇总 JSON/Markdown/HTML 已展示状态感知结论。

### 不修改

- `src/main.py`
- `src/governance/runtime.py`
- `src/governance/publisher.py`
- `src/report_portal.py`

## Task 1: 落地 Regime 配置与规则型分类器

**Files:**
- Create: `src/research/__init__.py`
- Create: `src/research/regime.py`
- Create: `tests/test_regime_classifier.py`
- Modify: `config/research.yaml`
- Modify: `src/core/config.py`
- Test: `tests/test_regime_classifier.py`

- [ ] **Step 1: 先写失败测试，锁定配置加载、risk_on/risk_off 判定和 coverage 不足回退**

```python
def test_research_config_loads_regime_policy():
    research_config = ConfigLoader().load_research_config()
    assert research_config.regime.enabled is True
    assert research_config.regime.min_pool_coverage == 3
    assert research_config.sample_split.in_sample_ratio == 0.7


def test_regime_classifier_labels_risk_on_and_risk_off():
    classifier = RegimeClassifier(_build_regime_config())
    risk_on = classifier.classify(_make_pool_price_data(trend="up"))[-1]
    risk_off = classifier.classify(_make_pool_price_data(trend="down"))[-1]
    assert risk_on.regime_label == "risk_on"
    assert risk_on.regime_score > 0
    assert risk_off.regime_label == "risk_off"
    assert risk_off.regime_score < 0


def test_regime_classifier_returns_neutral_when_pool_coverage_is_insufficient():
    classifier = RegimeClassifier(_build_regime_config(min_pool_coverage=3))
    snapshot = classifier.classify(_make_pool_price_data(symbol_count=2))[-1]
    assert snapshot.regime_label == "neutral"
    assert "INSUFFICIENT_POOL_COVERAGE" in snapshot.reason_codes
```

- [ ] **Step 2: 运行测试，确认当前缺少 regime 配置模型和分类器实现**

Run: `pytest -q tests/test_regime_classifier.py -v`
Expected: FAIL，报错应指向 `src.research.regime` 不存在或 `ResearchConfig` 缺少 `regime/sample_split`

- [ ] **Step 3: 先补配置模型与 YAML，确保规则完全配置化**

```python
class ResearchRegimeRuleConfig(BaseModel):
    breadth_above_ma120_min: float | None = None
    breadth_above_ma120_max: float | None = None
    return_20_min: float | None = None
    return_60_min: float | None = None
    drawdown_60_min: float | None = None
    drawdown_60_max: float | None = None
    ma_distance_120_max: float | None = None
    volatility_20_min: float | None = None


class ResearchRegimeConfig(BaseModel):
    enabled: bool = True
    min_pool_coverage: int = 3
    min_volatility_20: float = 0.18
    risk_on: ResearchRegimeRuleConfig = Field(default_factory=ResearchRegimeRuleConfig)
    risk_off: ResearchRegimeRuleConfig = Field(default_factory=ResearchRegimeRuleConfig)


class ResearchSampleSplitConfig(BaseModel):
    in_sample_ratio: float = 0.7
```

```yaml
research:
  regime:
    enabled: true
    min_pool_coverage: 3
    min_volatility_20: 0.18
    risk_on:
      breadth_above_ma120_min: 0.60
      return_20_min: 0.0
      return_60_min: 0.0
      drawdown_60_min: -0.08
    risk_off:
      breadth_above_ma120_max: 0.35
      drawdown_60_max: -0.12
      ma_distance_120_max: -0.03
      volatility_20_min: 0.18
  sample_split:
    in_sample_ratio: 0.70
```

要求：
- `ResearchConfig` 继续保留 `candidates`，但新增 `regime` 与 `sample_split`
- 不新建第四份配置文件，仍然只扩展 `config/research.yaml`
- 阈值命名保持“含义直白、可直接落 YAML”，不要用难读的缩写

- [ ] **Step 4: 再实现池级特征与 `RegimeClassifier` 最小闭环**

```python
@dataclass
class RegimeSnapshot:
    trade_date: date
    regime_label: Literal["risk_on", "neutral", "risk_off"]
    regime_score: float
    reason_codes: list[str]
    metrics_snapshot: dict[str, float | int | None]


class RegimeClassifier:
    def __init__(self, config: ResearchRegimeConfig):
        self.config = config

    def classify(self, price_data: dict[str, pd.DataFrame]) -> list[RegimeSnapshot]:
        feature_frame = self.build_pool_feature_frame(price_data)
        return [self._classify_row(row) for _, row in feature_frame.iterrows()]
```

池级特征要求：
- `pool_return_20`、`pool_return_60`、`pool_ma_distance_120`、`pool_volatility_20`、`pool_drawdown_60` 用横截面中位数
- `pool_breadth_above_ma120` 用 ETF 占比
- 每日参与样本数不足 `min_pool_coverage` 时直接回退 `neutral`，并记 `INSUFFICIENT_POOL_COVERAGE`
- `regime_score` 只做解释性打分，范围裁剪到 `[-1, 1]`

- [ ] **Step 5: 回跑测试，确认配置与分类器闭环成立**

Run: `pytest -q tests/test_regime_classifier.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add config/research.yaml src/core/config.py src/research/__init__.py src/research/regime.py tests/test_regime_classifier.py
git commit -m "feat: add regime classifier for research"
```

## Task 2: 落地样本切片与候选分层分析

**Files:**
- Create: `src/research/segmentation.py`
- Create: `src/research/regime_analysis.py`
- Create: `tests/test_regime_analysis.py`
- Test: `tests/test_regime_analysis.py`

- [ ] **Step 1: 写失败测试，锁定 70/30 切片、按 regime 聚合和 transition 统计**

```python
def test_build_sample_split_labels_uses_trade_day_ratio():
    trade_dates = _make_trade_dates(10)
    labels = build_sample_split_labels(trade_dates, in_sample_ratio=0.7)
    assert [labels[d] for d in trade_dates[:7]] == ["in_sample"] * 7
    assert [labels[d] for d in trade_dates[7:]] == ["out_of_sample"] * 3


def test_analyze_candidate_segments_returns_regime_and_sample_metrics():
    analysis = analyze_candidate_segments(
        candidate_name="baseline_trend",
        nav_series=_make_nav_series(),
        regime_snapshots=_make_regime_snapshots(),
        sample_labels=_make_sample_labels(),
    )
    assert analysis["overall_metrics"]["observation_count"] == 10
    assert analysis["by_regime_metrics"]["risk_on"]["observation_count"] > 0
    assert analysis["out_of_sample_metrics"]["observation_count"] == 3
    assert analysis["regime_transition_metrics"][0]["transition"] == "neutral->risk_off"
```

- [ ] **Step 2: 运行测试，确认当前缺少切片与分析模块**

Run: `pytest -q tests/test_regime_analysis.py -v`
Expected: FAIL，报错应指向 `src.research.segmentation` 或 `src.research.regime_analysis` 不存在

- [ ] **Step 3: 先实现样本切片工具，统一输出交易日标签映射**

```python
def build_sample_split_labels(
    trade_dates: Sequence[date],
    in_sample_ratio: float = 0.7,
) -> dict[date, Literal["in_sample", "out_of_sample"]]:
    cutoff = max(1, min(len(trade_dates) - 1, int(len(trade_dates) * in_sample_ratio)))
    return {
        trade_date: "in_sample" if idx < cutoff else "out_of_sample"
        for idx, trade_date in enumerate(trade_dates)
    }
```

要求：
- 边界要保证“有样本内也有样本外”，不能全部落同一侧
- 标签映射的 key 统一使用 `date`，避免后续 `Timestamp/date` 混用

- [ ] **Step 4: 实现候选分层分析，复用现有回测评估函数**

```python
def analyze_candidate_segments(
    candidate_name: str,
    nav_series: pd.Series,
    regime_snapshots: Sequence[RegimeSnapshot],
    sample_labels: dict[date, str],
    transition_window: int = 5,
) -> dict[str, Any]:
    return {
        "candidate_name": candidate_name,
        "overall_metrics": _evaluate_segment(nav_series),
        "by_regime_metrics": _group_metrics_by_regime(...),
        "in_sample_metrics": _evaluate_segment(...),
        "out_of_sample_metrics": _evaluate_segment(...),
        "by_regime_and_sample_metrics": _group_metrics_by_regime_and_sample(...),
        "regime_transition_metrics": _summarize_transitions(...),
    }
```

实现要求：
- `overall/by_regime/in_sample/out_of_sample` 都输出统一指标集，并附 `observation_count`
- `transition` 第一版只做轻量统计：`from_regime`、`to_regime`、`transition`、`event_count`、`avg_forward_return_5`、`avg_forward_drawdown_5`
- 空切片或样本不足时输出 0/`None`，不要抛异常中断整份研究

- [ ] **Step 5: 回跑测试，确认切片与分析结果稳定**

Run: `pytest -q tests/test_regime_analysis.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add src/research/segmentation.py src/research/regime_analysis.py tests/test_regime_analysis.py
git commit -m "feat: add regime segmentation analysis"
```

## Task 3: 接入单次研究主流程与报告落盘

**Files:**
- Modify: `src/research_pipeline.py`
- Modify: `tests/test_research_pipeline.py`
- Test: `tests/test_research_pipeline.py`

- [ ] **Step 1: 先扩失败测试，锁定研究主流程的新返回字段与落盘 JSON**

```python
def test_research_pipeline_outputs_regime_analysis_sections():
    _seed_research_db()
    result = run_research_pipeline(
        start_date=date(2025, 12, 1),
        end_date=date(2026, 3, 11),
        log_level="INFO",
    )
    assert result["regime_daily_labels"]
    assert "baseline_trend" in result["candidate_regime_metrics"]
    assert "risk_on" in result["candidate_regime_metrics"]["baseline_trend"]["by_regime_metrics"]
    assert "out_of_sample_metrics" in result["candidate_sample_split_metrics"]["baseline_trend"]

    payload = json.loads(Path(result["report_paths"]["json"]).read_text(encoding="utf-8"))
    assert "regime_config_snapshot" in payload
    assert "candidate_regime_transition_metrics" in payload
```

- [ ] **Step 2: 运行测试，确认当前 pipeline 尚未产出新研究字段**

Run: `pytest -q tests/test_research_pipeline.py -v`
Expected: FAIL，断言缺少 `regime_daily_labels` 或 JSON 不含新字段

- [ ] **Step 3: 在 pipeline 中先接好 regime 标签和 sample split**

```python
research_config = config_loader.load_research_config()
pool_symbols = config_loader.get_enabled_etf_codes()
pool_prices = price_repo.get_multi_symbol_prices(
    pool_symbols,
    start_date - timedelta(days=365),
    end_date,
)
regime_snapshots = RegimeClassifier(research_config.regime).classify(pool_prices)
sample_labels = build_sample_split_labels(list(nav_series.index), research_config.sample_split.in_sample_ratio)
```

要求：
- ETF 池行情只拉一次，不能为每个候选重复算一遍
- `regime_daily_labels` 以交易日为准，只保留研究窗口内日期
- 当前研究的生产约束仍然是“单一 ETF 候选对比”，这里不要引入组合级候选

- [ ] **Step 4: 再把候选分析结果写回单次研究结果和报告**

```python
candidate_analysis = analyze_candidate_segments(
    candidate_name=spec["name"],
    nav_series=nav_series,
    regime_snapshots=regime_snapshots,
    sample_labels=sample_labels,
)

report_payload = {
    "comparison_rows": _to_jsonable(comparison_rows),
    "research_output": _to_jsonable(research_output.model_dump()),
    "regime_config_snapshot": _to_jsonable(research_config.regime.model_dump()),
    "regime_daily_labels": _to_jsonable([snapshot.__dict__ for snapshot in regime_snapshots]),
    "candidate_regime_metrics": {...},
    "candidate_sample_split_metrics": {...},
    "candidate_regime_transition_metrics": {...},
}
```

实现要求：
- 顶层字段命名与 spec 保持一致，不额外发明并列命名
- 返回值与落盘 JSON 同时带新字段，便于测试与后续汇总复用
- Markdown 报告最少补两个区块：`Regime 概览`、`样本外观察`

- [ ] **Step 5: 回跑专项测试，确认旧输出兼容且新字段已落盘**

Run: `pytest -q tests/test_research_pipeline.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add src/research_pipeline.py tests/test_research_pipeline.py
git commit -m "feat: enrich research pipeline with regime outputs"
```

## Task 4: 升级研究汇总 JSON/Markdown/HTML 并完成全量验证

**Files:**
- Modify: `src/research_summary.py`
- Modify: `tests/test_research_summary.py`
- Test: `tests/test_research_summary.py`

- [ ] **Step 1: 先扩失败测试，锁定汇总 JSON 字段和四个核心问题的展示**

```python
def test_aggregate_research_reports_surfaces_regime_leaderboards(tmp_path):
    _write_report_with_regime_payload(report_dir / "2026-03-10.json", ...)
    _write_report_with_regime_payload(report_dir / "2026-03-11.json", ...)

    result = aggregate_research_reports(report_dir=report_dir, output_dir=output_dir)

    assert "regime_summary" in result
    assert result["candidate_regime_leaderboard"]
    assert result["candidate_out_of_sample_leaderboard"]
    assert len(result["candidate_regime_observations"]) == 4

    html_content = Path(result["output_paths"]["html"]).read_text(encoding="utf-8")
    assert "哪个候选在 risk_on 最强" in html_content
    assert "哪个候选在 risk_off 更稳" in html_content
    assert "样本外是否明显退化" in html_content
```

- [ ] **Step 2: 运行测试，确认当前研究汇总尚未理解 regime 字段**

Run: `pytest -q tests/test_research_summary.py -v`
Expected: FAIL，断言缺少 `regime_summary`、`candidate_regime_leaderboard` 或新展示文案

- [ ] **Step 3: 先实现跨报告聚合 helpers，稳定 JSON 结构**

```python
def _build_regime_summary(report_payloads: list[dict[str, Any]]) -> dict[str, Any]: ...


def _build_candidate_regime_leaderboard(report_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]: ...


def _build_candidate_out_of_sample_leaderboard(report_payloads: list[dict[str, Any]]) -> list[dict[str, Any]]: ...


def _build_candidate_regime_observations(...) -> list[dict[str, Any]]:
    return [
        {"question": "哪个候选在 risk_on 最强", "answer": "...", "evidence": {...}},
        {"question": "哪个候选在 risk_off 更稳", "answer": "...", "evidence": {...}},
        {"question": "某候选是否只在单一 regime 下有效", "answer": "...", "evidence": {...}},
        {"question": "某候选在样本外是否明显退化", "answer": "...", "evidence": {...}},
    ]
```

要求：
- `candidate_regime_leaderboard` 至少包含 `regime_label/name/strategy_id/avg_annual_return/avg_sharpe/avg_max_drawdown/appearances`
- `candidate_out_of_sample_leaderboard` 至少包含 `name/strategy_id/avg_out_of_sample_annual_return/avg_out_of_sample_sharpe/degradation_vs_overall`
- `candidate_regime_observations` 不输出空话，必须附 evidence 字段供 Markdown/HTML 渲染

- [ ] **Step 4: 升级 Markdown/HTML，显式回答四个问题**

```python
markdown_sections.extend(
    [
        "## Regime Summary",
        f"- 最新状态分布：{regime_summary['latest_distribution']}",
        "",
        "## 核心观察",
        *[
            f"- {item['question']}：{item['answer']}"
            for item in candidate_regime_observations
        ],
    ]
)
```

实现要求：
- Markdown 和 HTML 都要能直接看出 `risk_on` 强者、`risk_off` 稳定者、单一状态依赖、样本外退化
- 保持现有研究历史总览页风格，不重写为全新前端框架
- 保持旧字段兼容，避免影响现有门户读取

- [ ] **Step 5: 跑专项验证与全量验证**

Run: `pytest -q tests/test_regime_classifier.py tests/test_regime_analysis.py tests/test_research_pipeline.py tests/test_research_summary.py -v`
Expected: PASS

Run: `pytest -q`
Expected: PASS

Run: `python3 -m compileall src scripts tests`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add src/research_summary.py tests/test_research_summary.py docs/superpowers/plans/2026-03-24-phase-four-regime-research-implementation.md tasks/todo.md
git commit -m "feat: surface regime insights in research summary"
```

## Execution Notes

- 优先顺序固定为：Task 1 -> Task 2 -> Task 3 -> Task 4；不要跳着实现，否则 `research_pipeline.py` 会缺依赖。
- 如果 Task 3 中发现 `nav_series` 与 `regime_daily_labels` 日期类型不一致，先在研究模块里统一到 `date`，不要在多个调用方零散修补。
- 如果 Task 4 中发现历史老报告不含 regime 字段，汇总逻辑应跳过缺失字段并保持旧报告仍可被聚合。
- 完成 Task 4 后，再回写本计划勾选状态与 `tasks/todo.md` 结果区。
