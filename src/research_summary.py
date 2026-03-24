"""研究报告汇总模块。"""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime
import csv
from html import escape
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _safe_float(value: Any) -> Optional[float]:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _average(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return sum(values) / len(values)


def _candidate_name(candidate: Dict[str, Any], fallback: str) -> str:
    return (
        candidate.get("candidate_name")
        or candidate.get("name")
        or candidate.get("param_desc")
        or candidate.get("label")
        or fallback
    )


def _candidate_strategy_id(candidate: Dict[str, Any]) -> str:
    return candidate.get("strategy_id") or "n/a"


def _read_report(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _build_markdown(
    report_summaries: List[Dict[str, Any]],
    candidate_leaderboard: List[Dict[str, Any]],
) -> str:
    lines = [
        "# Research Summary",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 报告数量：{len(report_summaries)}",
    ]
    if report_summaries:
        lines.append(
            f"- 报告区间：{report_summaries[0]['report_date']} -> {report_summaries[-1]['report_date']}"
        )

    lines.extend(
        [
            "",
            "## 报告视图",
            "",
            "| 报告日期 | 推荐方案 | 策略ID | 过拟合风险 | 最优年化 | 最优 Sharpe | 摘要 |",
            "| --- | --- | --- | --- | ---: | ---: | --- |",
        ]
    )
    for report in report_summaries:
        lines.append(
            "| {report_date} | {top_candidate_name} | {top_candidate_strategy_id} | {overfit_risk} | {top_annual_return:.2%} | {top_sharpe:.4f} | {summary} |".format(
                report_date=report["report_date"],
                top_candidate_name=report["top_candidate_name"],
                top_candidate_strategy_id=report["top_candidate_strategy_id"],
                overfit_risk=report["overfit_risk"],
                top_annual_return=report["top_annual_return"] or 0.0,
                top_sharpe=report["top_sharpe"] or 0.0,
                summary=report["summary"],
            )
        )

    lines.extend(
        [
            "",
            "## 候选视图",
            "",
            "| 候选方案 | 策略ID | 出现次数 | Top1 次数 | 平均排名 | 平均年化 | 平均 Sharpe | 平均回撤 | 最近出现 |",
            "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
        ]
    )
    for candidate in candidate_leaderboard:
        lines.append(
            "| {name} | {strategy_id} | {appearances} | {top1_count} | {avg_rank:.2f} | {avg_annual_return:.2%} | {avg_sharpe:.4f} | {avg_max_drawdown:.2%} | {last_seen} |".format(
                name=candidate["name"],
                strategy_id=candidate["strategy_id"],
                appearances=candidate["appearances"],
                top1_count=candidate["top1_count"],
                avg_rank=candidate["avg_rank"],
                avg_annual_return=candidate["avg_annual_return"] or 0.0,
                avg_sharpe=candidate["avg_sharpe"] or 0.0,
                avg_max_drawdown=candidate["avg_max_drawdown"] or 0.0,
                last_seen=candidate["last_seen"],
            )
        )

    return "\n".join(lines)


def _format_pct(value: Optional[float]) -> str:
    return f"{value:.2%}" if value is not None else "-"


def _format_float(value: Optional[float], digits: int = 4) -> str:
    return f"{value:.{digits}f}" if value is not None else "-"


def _build_html(
    report_summaries: List[Dict[str, Any]],
    candidate_leaderboard: List[Dict[str, Any]],
    candidate_observations: List[Dict[str, Any]],
) -> str:
    latest_report = report_summaries[-1] if report_summaries else None
    leader = candidate_leaderboard[0] if candidate_leaderboard else None
    candidate_options = "".join(
        [
            '<option value="">全部候选</option>',
            *[
                f'<option value="{escape(candidate["name"])}">{escape(candidate["name"])} / {escape(candidate["strategy_id"])}</option>'
                for candidate in candidate_leaderboard
            ],
        ]
    )
    report_json = json.dumps(report_summaries, ensure_ascii=False)
    candidate_json = json.dumps(candidate_observations, ensure_ascii=False)

    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>研究历史总览</title>
  <style>
    :root {{
      --bg: #f3efe7;
      --panel: rgba(255, 252, 247, 0.88);
      --panel-strong: #fffdf9;
      --text: #1e2430;
      --muted: #6a7180;
      --accent: #0f766e;
      --accent-soft: #d8efe8;
      --border: rgba(30, 36, 48, 0.12);
      --shadow: 0 24px 60px rgba(39, 52, 79, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "PingFang SC", "Hiragino Sans GB", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(15, 118, 110, 0.18), transparent 28%),
        radial-gradient(circle at top right, rgba(198, 93, 62, 0.14), transparent 24%),
        linear-gradient(180deg, #f8f4ed 0%, var(--bg) 100%);
    }}
    .page {{
      width: min(1180px, calc(100vw - 32px));
      margin: 32px auto 56px;
    }}
    .hero {{
      padding: 28px;
      border: 1px solid var(--border);
      border-radius: 28px;
      background: linear-gradient(135deg, rgba(255,255,255,0.82), rgba(255,248,238,0.92));
      box-shadow: var(--shadow);
      overflow: hidden;
      position: relative;
    }}
    .hero::after {{
      content: "";
      position: absolute;
      right: -40px;
      top: -20px;
      width: 220px;
      height: 220px;
      border-radius: 999px;
      background: radial-gradient(circle, rgba(15,118,110,0.18), transparent 68%);
    }}
    .eyebrow {{
      font-size: 12px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--accent);
      margin-bottom: 10px;
      font-weight: 700;
    }}
    h1 {{
      margin: 0;
      font-size: clamp(30px, 5vw, 52px);
      line-height: 1.02;
    }}
    .sub {{
      margin: 14px 0 0;
      color: var(--muted);
      max-width: 760px;
      line-height: 1.65;
      font-size: 15px;
    }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
      margin-top: 22px;
    }}
    .metric {{
      padding: 18px;
      border-radius: 22px;
      background: var(--panel);
      border: 1px solid rgba(15, 118, 110, 0.08);
      backdrop-filter: blur(8px);
    }}
    .metric-label {{
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
      margin-bottom: 8px;
    }}
    .metric-value {{
      font-size: clamp(22px, 3vw, 34px);
      font-weight: 700;
      line-height: 1.1;
    }}
    .metric-note {{
      margin-top: 8px;
      font-size: 13px;
      color: var(--muted);
    }}
    .section {{
      margin-top: 24px;
      padding: 22px;
      border-radius: 26px;
      border: 1px solid var(--border);
      background: var(--panel-strong);
      box-shadow: var(--shadow);
    }}
    .section h2 {{
      margin: 0 0 14px;
      font-size: 20px;
    }}
    .toolbar {{
      display: grid;
      grid-template-columns: 1.3fr 1fr 1fr auto;
      gap: 12px;
      margin-bottom: 18px;
      align-items: end;
    }}
    .control {{
      display: flex;
      flex-direction: column;
      gap: 6px;
    }}
    .control label {{
      font-size: 12px;
      color: var(--muted);
      letter-spacing: 0.06em;
      text-transform: uppercase;
    }}
    .control select,
    .control input {{
      width: 100%;
      height: 42px;
      border-radius: 14px;
      border: 1px solid var(--border);
      background: white;
      color: var(--text);
      padding: 0 12px;
      font-size: 14px;
    }}
    .toolbar-actions {{
      display: flex;
      justify-content: flex-end;
    }}
    .ghost-btn {{
      height: 42px;
      border-radius: 14px;
      border: 1px solid rgba(15, 118, 110, 0.16);
      background: var(--accent-soft);
      color: var(--accent);
      padding: 0 16px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
    }}
    .table-wrap {{
      overflow-x: auto;
      border-radius: 18px;
      border: 1px solid var(--border);
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 760px;
      background: white;
    }}
    th, td {{
      padding: 14px 16px;
      border-bottom: 1px solid var(--border);
      vertical-align: top;
      text-align: left;
      font-size: 14px;
    }}
    th {{
      background: #f6fbf9;
      color: #24403d;
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .sort-btn {{
      border: none;
      background: transparent;
      color: inherit;
      font: inherit;
      letter-spacing: inherit;
      text-transform: inherit;
      cursor: pointer;
      padding: 0;
    }}
    .sort-btn::after {{
      content: "↕";
      margin-left: 6px;
      color: #7b8d8a;
      font-size: 11px;
    }}
    .sort-btn[data-dir="asc"]::after {{ content: "↑"; color: var(--accent); }}
    .sort-btn[data-dir="desc"]::after {{ content: "↓"; color: var(--accent); }}
    tr:last-child td {{ border-bottom: none; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .candidate-name {{ font-weight: 700; }}
    .candidate-desc {{ color: var(--muted); margin-top: 4px; font-size: 12px; }}
    .empty {{
      text-align: center;
      color: var(--muted);
      padding: 18px;
    }}
    .footer {{
      margin-top: 16px;
      color: var(--muted);
      font-size: 13px;
    }}
    @media (max-width: 900px) {{
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .toolbar {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    }}
    @media (max-width: 640px) {{
      .page {{ width: min(100vw - 20px, 100%); margin-top: 18px; }}
      .hero, .section {{ padding: 18px; border-radius: 20px; }}
      .metrics {{ grid-template-columns: 1fr; }}
      .toolbar {{ grid-template-columns: 1fr; }}
      th, td {{ padding: 12px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="eyebrow">Research Overview</div>
      <h1>研究历史总览</h1>
      <p class="sub">集中回看历史研究报告，快速判断最近推荐方案、跨报告最稳候选以及参数组合的持续性表现。</p>
      <div class="metrics">
        <article class="metric">
          <div class="metric-label">报告数量</div>
          <div class="metric-value">{report_count}</div>
          <div class="metric-note">当前已纳入汇总的研究报告数</div>
        </article>
        <article class="metric">
          <div class="metric-label">最新推荐</div>
          <div class="metric-value">{latest_candidate}</div>
          <div class="metric-note">{latest_date}</div>
        </article>
        <article class="metric">
          <div class="metric-label">历史领先候选</div>
          <div class="metric-value">{leader_name}</div>
          <div class="metric-note">Top1 次数 {leader_top1}</div>
        </article>
        <article class="metric">
          <div class="metric-label">领先候选平均年化</div>
          <div class="metric-value">{leader_return}</div>
          <div class="metric-note">平均 Sharpe {leader_sharpe}</div>
        </article>
      </div>
    </section>

    <section class="section">
      <h2>按报告回看</h2>
      <div class="toolbar">
        <div class="control">
          <label for="candidate-filter">候选筛选</label>
          <select id="candidate-filter">{candidate_options}</select>
        </div>
        <div class="control">
          <label for="start-date-filter">开始日期</label>
          <input id="start-date-filter" type="date" />
        </div>
        <div class="control">
          <label for="end-date-filter">结束日期</label>
          <input id="end-date-filter" type="date" />
        </div>
        <div class="toolbar-actions">
          <button id="reset-filters" class="ghost-btn" type="button">重置筛选</button>
        </div>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th><button class="sort-btn" data-table="reports" data-key="report_date" type="button">报告日期</button></th>
              <th><button class="sort-btn" data-table="reports" data-key="top_candidate_name" type="button">推荐方案</button></th>
              <th><button class="sort-btn" data-table="reports" data-key="top_candidate_strategy_id" type="button">策略ID</button></th>
              <th><button class="sort-btn" data-table="reports" data-key="overfit_risk" type="button">过拟合风险</button></th>
              <th class="num"><button class="sort-btn" data-table="reports" data-key="top_annual_return" type="button">最优年化</button></th>
              <th class="num"><button class="sort-btn" data-table="reports" data-key="top_sharpe" type="button">最优 Sharpe</button></th>
              <th>摘要</th>
            </tr>
          </thead>
          <tbody id="report-table-body"></tbody>
        </table>
      </div>
    </section>

    <section class="section">
      <h2>按候选横向对比</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th><button class="sort-btn" data-table="candidates" data-key="name" type="button">候选方案</button></th>
              <th><button class="sort-btn" data-table="candidates" data-key="strategy_id" type="button">策略ID</button></th>
              <th class="num"><button class="sort-btn" data-table="candidates" data-key="appearances" type="button">出现次数</button></th>
              <th class="num"><button class="sort-btn" data-table="candidates" data-key="top1_count" type="button">Top1 次数</button></th>
              <th class="num"><button class="sort-btn" data-table="candidates" data-key="avg_rank" type="button">平均排名</button></th>
              <th class="num"><button class="sort-btn" data-table="candidates" data-key="avg_annual_return" type="button">平均年化</button></th>
              <th class="num"><button class="sort-btn" data-table="candidates" data-key="avg_sharpe" type="button">平均 Sharpe</button></th>
              <th class="num"><button class="sort-btn" data-table="candidates" data-key="avg_max_drawdown" type="button">平均回撤</button></th>
              <th><button class="sort-btn" data-table="candidates" data-key="last_seen" type="button">最近出现</button></th>
            </tr>
          </thead>
          <tbody id="candidate-table-body"></tbody>
        </table>
      </div>
      <div class="footer">数据来源：`reports/research/*.json` 聚合结果</div>
    </section>
  </main>
  <script>
    const reportData = {report_json};
    const candidateObservations = {candidate_json};
    const state = {{
      candidate: "",
      startDate: "",
      endDate: "",
      reportSort: {{ key: "report_date", dir: "desc" }},
      candidateSort: {{ key: "top1_count", dir: "desc" }},
    }};

    const reportBody = document.getElementById("report-table-body");
    const candidateBody = document.getElementById("candidate-table-body");
    const candidateFilter = document.getElementById("candidate-filter");
    const startDateFilter = document.getElementById("start-date-filter");
    const endDateFilter = document.getElementById("end-date-filter");
    const resetButton = document.getElementById("reset-filters");

    function formatPct(value) {{
      return value === null || value === undefined ? "-" : `${{(value * 100).toFixed(2)}}%`;
    }}

    function formatFloat(value, digits = 4) {{
      return value === null || value === undefined ? "-" : Number(value).toFixed(digits);
    }}

    function compareValues(a, b, dir) {{
      const left = a ?? "";
      const right = b ?? "";
      if (typeof left === "number" || typeof right === "number") {{
        return dir === "asc" ? left - right : right - left;
      }}
      return dir === "asc"
        ? String(left).localeCompare(String(right), "zh-CN")
        : String(right).localeCompare(String(left), "zh-CN");
    }}

    function inDateRange(value) {{
      if (!value) return false;
      if (state.startDate && value < state.startDate) return false;
      if (state.endDate && value > state.endDate) return false;
      return true;
    }}

    function sortRows(rows, config) {{
      return [...rows].sort((a, b) => compareValues(a[config.key], b[config.key], config.dir));
    }}

    function aggregateCandidates(observations) {{
      const grouped = new Map();
      observations.forEach((item) => {{
        const key = `${{item.name}}::${{item.strategy_id || ""}}`;
        if (!grouped.has(key)) {{
          grouped.set(key, {{
            name: item.name,
            strategy_id: item.strategy_id || "n/a",
            description: item.description || "",
            appearances: 0,
            top1_count: 0,
            rank_sum: 0,
            annual_returns: [],
            sharpes: [],
            max_drawdowns: [],
            last_seen: item.report_date,
          }});
        }}
        const current = grouped.get(key);
        current.appearances += 1;
        current.top1_count += item.rank === 1 ? 1 : 0;
        current.rank_sum += item.rank;
        current.last_seen = current.last_seen > item.report_date ? current.last_seen : item.report_date;
        if (item.description) current.description = item.description;
        if (item.annual_return !== null && item.annual_return !== undefined) current.annual_returns.push(item.annual_return);
        if (item.sharpe !== null && item.sharpe !== undefined) current.sharpes.push(item.sharpe);
        if (item.max_drawdown !== null && item.max_drawdown !== undefined) current.max_drawdowns.push(item.max_drawdown);
      }});
      return [...grouped.values()].map((item) => ({{
        name: item.name,
        strategy_id: item.strategy_id,
        description: item.description,
        appearances: item.appearances,
        top1_count: item.top1_count,
        avg_rank: item.rank_sum / item.appearances,
        avg_annual_return: item.annual_returns.length ? item.annual_returns.reduce((a, b) => a + b, 0) / item.annual_returns.length : null,
        avg_sharpe: item.sharpes.length ? item.sharpes.reduce((a, b) => a + b, 0) / item.sharpes.length : null,
        avg_max_drawdown: item.max_drawdowns.length ? item.max_drawdowns.reduce((a, b) => a + b, 0) / item.max_drawdowns.length : null,
        last_seen: item.last_seen,
      }}));
    }}

    function getFilteredReports() {{
      return reportData.filter((item) => {{
        if (state.candidate && item.top_candidate_name !== state.candidate) return false;
        return inDateRange(item.report_date);
      }});
    }}

    function getFilteredCandidateRows() {{
      const filtered = candidateObservations.filter((item) => {{
        if (state.candidate && item.name !== state.candidate) return false;
        return inDateRange(item.report_date);
      }});
      return aggregateCandidates(filtered);
    }}

    function renderReports(rows) {{
      if (!rows.length) {{
        reportBody.innerHTML = '<tr><td class="empty" colspan="7">当前筛选条件下没有报告</td></tr>';
        return;
      }}
      reportBody.innerHTML = sortRows(rows, state.reportSort).map((item) => `
        <tr>
          <td>${{item.report_date}}</td>
          <td>${{item.top_candidate_name}}</td>
          <td>${{item.top_candidate_strategy_id || "-"}}</td>
          <td>${{item.overfit_risk || "-"}}</td>
          <td class="num">${{formatPct(item.top_annual_return)}}</td>
          <td class="num">${{formatFloat(item.top_sharpe)}}</td>
          <td>${{item.summary}}</td>
        </tr>
      `).join("");
    }}

    function renderCandidates(rows) {{
      if (!rows.length) {{
        candidateBody.innerHTML = '<tr><td class="empty" colspan="9">当前筛选条件下没有候选</td></tr>';
        return;
      }}
      candidateBody.innerHTML = sortRows(rows, state.candidateSort).map((item) => `
        <tr>
          <td>
            <div class="candidate-name">${{item.name}}</div>
            <div class="candidate-desc">${{item.description || "未提供说明"}}</div>
          </td>
          <td>${{item.strategy_id || "-"}}</td>
          <td class="num">${{item.appearances}}</td>
          <td class="num">${{item.top1_count}}</td>
          <td class="num">${{formatFloat(item.avg_rank, 2)}}</td>
          <td class="num">${{formatPct(item.avg_annual_return)}}</td>
          <td class="num">${{formatFloat(item.avg_sharpe)}}</td>
          <td class="num">${{formatPct(item.avg_max_drawdown)}}</td>
          <td>${{item.last_seen}}</td>
        </tr>
      `).join("");
    }}

    function updateSortButtons() {{
      document.querySelectorAll(".sort-btn").forEach((button) => {{
        const table = button.dataset.table;
        const config = table === "reports" ? state.reportSort : state.candidateSort;
        button.dataset.dir = config.key === button.dataset.key ? config.dir : "";
      }});
    }}

    function render() {{
      renderReports(getFilteredReports());
      renderCandidates(getFilteredCandidateRows());
      updateSortButtons();
    }}

    candidateFilter.addEventListener("change", (event) => {{
      state.candidate = event.target.value;
      render();
    }});
    startDateFilter.addEventListener("change", (event) => {{
      state.startDate = event.target.value;
      render();
    }});
    endDateFilter.addEventListener("change", (event) => {{
      state.endDate = event.target.value;
      render();
    }});
    resetButton.addEventListener("click", () => {{
      state.candidate = "";
      state.startDate = "";
      state.endDate = "";
      candidateFilter.value = "";
      startDateFilter.value = "";
      endDateFilter.value = "";
      render();
    }});
    document.querySelectorAll(".sort-btn").forEach((button) => {{
      button.addEventListener("click", () => {{
        const target = button.dataset.table === "reports" ? state.reportSort : state.candidateSort;
        if (target.key === button.dataset.key) {{
          target.dir = target.dir === "asc" ? "desc" : "asc";
        }} else {{
          target.key = button.dataset.key;
          target.dir = button.dataset.key.includes("date") ? "desc" : "asc";
          if (button.dataset.table === "candidates" && button.dataset.key === "top1_count") {{
            target.dir = "desc";
          }}
        }}
        render();
      }});
    }});

    render();
  </script>
</body>
</html>
    """.format(
        report_count=len(report_summaries),
        latest_candidate=escape(latest_report["top_candidate_name"]) if latest_report else "-",
        latest_date=escape(latest_report["report_date"]) if latest_report else "暂无数据",
        leader_name=escape(leader["name"]) if leader else "-",
        leader_top1=leader["top1_count"] if leader else 0,
        leader_return=_format_pct(leader["avg_annual_return"]) if leader else "-",
        leader_sharpe=_format_float(leader["avg_sharpe"]) if leader else "-",
        candidate_options=candidate_options,
        report_json=report_json,
        candidate_json=candidate_json,
    ).strip()


def _write_csv(path: Path, rows: List[Dict[str, Any]], fieldnames: List[str]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        normalized_rows = []
        for row in rows:
            normalized_rows.append(
                {
                    key: json.dumps(value, ensure_ascii=False)
                    if isinstance(value, (dict, list))
                    else value
                    for key, value in row.items()
                }
            )
        writer.writerows(normalized_rows)


def aggregate_research_reports(
    report_dir: str | Path = "reports/research",
    output_dir: str | Path | None = None,
) -> Dict[str, Any]:
    """聚合研究报告，输出统一摘要。"""
    report_dir = Path(report_dir)
    output_dir = Path(output_dir) if output_dir else report_dir / "summary"
    report_paths = sorted(report_dir.glob("*.json"))
    if not report_paths:
        raise FileNotFoundError(f"未找到研究报告: {report_dir}")

    report_summaries: List[Dict[str, Any]] = []
    candidate_observations: List[Dict[str, Any]] = []
    candidate_stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "name": "",
            "strategy_id": "n/a",
            "description": None,
            "appearances": 0,
            "top1_count": 0,
            "rank_sum": 0.0,
            "annual_returns": [],
            "sharpes": [],
            "max_drawdowns": [],
            "composite_scores": [],
            "last_seen": "",
            "latest_overrides": {},
        }
    )

    for path in report_paths:
        payload = _read_report(path)
        ranked_candidates = payload.get("research_output", {}).get("ranked_candidates", [])
        top_candidate = ranked_candidates[0] if ranked_candidates else {}
        report_summary = {
            "report_date": path.stem,
            "candidate_count": len(payload.get("comparison_rows", [])),
            "top_candidate_name": _candidate_name(top_candidate, "n/a"),
            "top_candidate_strategy_id": _candidate_strategy_id(top_candidate),
            "recommendation": payload.get("research_output", {}).get("recommendation", ""),
            "overfit_risk": payload.get("research_output", {}).get("overfit_risk", ""),
            "summary": payload.get("research_output", {}).get("summary", ""),
            "top_annual_return": _safe_float(top_candidate.get("annual_return")),
            "top_sharpe": _safe_float(top_candidate.get("sharpe")),
        }
        report_summaries.append(report_summary)

        for idx, candidate in enumerate(ranked_candidates, start=1):
            candidate_name = _candidate_name(candidate, f"candidate_{idx}")
            candidate_strategy_id = _candidate_strategy_id(candidate)
            stats = candidate_stats[f"{candidate_name}::{candidate_strategy_id}"]
            stats["name"] = candidate_name
            stats["strategy_id"] = candidate_strategy_id
            stats["description"] = candidate.get("description") or stats["description"]
            stats["appearances"] += 1
            stats["top1_count"] += 1 if idx == 1 else 0
            stats["rank_sum"] += idx
            stats["last_seen"] = path.stem
            stats["latest_overrides"] = candidate.get("overrides", stats["latest_overrides"])

            annual_return = _safe_float(candidate.get("annual_return"))
            sharpe = _safe_float(candidate.get("sharpe"))
            max_drawdown = _safe_float(candidate.get("max_drawdown"))
            composite_score = _safe_float(candidate.get("composite_score"))
            if annual_return is not None:
                stats["annual_returns"].append(annual_return)
            if sharpe is not None:
                stats["sharpes"].append(sharpe)
            if max_drawdown is not None:
                stats["max_drawdowns"].append(max_drawdown)
            if composite_score is not None:
                stats["composite_scores"].append(composite_score)
            candidate_observations.append(
                {
                    "report_date": path.stem,
                    "name": candidate_name,
                    "strategy_id": candidate_strategy_id,
                    "description": candidate.get("description"),
                    "rank": idx,
                    "annual_return": annual_return,
                    "sharpe": sharpe,
                    "max_drawdown": max_drawdown,
                    "composite_score": composite_score,
                }
            )

    report_summaries.sort(key=lambda item: item["report_date"])
    candidate_leaderboard = []
    for stats in candidate_stats.values():
        appearances = stats["appearances"]
        candidate_leaderboard.append(
            {
                "name": stats["name"],
                "strategy_id": stats["strategy_id"],
                "description": stats["description"],
                "appearances": appearances,
                "top1_count": stats["top1_count"],
                "avg_rank": stats["rank_sum"] / appearances,
                "avg_annual_return": _average(stats["annual_returns"]),
                "avg_sharpe": _average(stats["sharpes"]),
                "avg_max_drawdown": _average(stats["max_drawdowns"]),
                "avg_composite_score": _average(stats["composite_scores"]),
                "last_seen": stats["last_seen"],
                "latest_overrides": stats["latest_overrides"],
            }
        )

    candidate_leaderboard.sort(
        key=lambda item: (
            -item["top1_count"],
            item["avg_rank"],
            -(item["avg_composite_score"] or 0.0),
            -(item["avg_annual_return"] or 0.0),
        )
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    markdown_path = output_dir / "research_summary.md"
    html_path = output_dir / "index.html"
    json_path = output_dir / "research_summary.json"
    reports_csv_path = output_dir / "research_reports.csv"
    candidates_csv_path = output_dir / "research_candidates.csv"

    markdown_path.write_text(
        _build_markdown(report_summaries=report_summaries, candidate_leaderboard=candidate_leaderboard),
        encoding="utf-8",
    )
    html_path.write_text(
        _build_html(
            report_summaries=report_summaries,
            candidate_leaderboard=candidate_leaderboard,
            candidate_observations=candidate_observations,
        ),
        encoding="utf-8",
    )
    json_path.write_text(
        json.dumps(
            {
                "report_count": len(report_summaries),
                "report_summaries": report_summaries,
                "candidate_leaderboard": candidate_leaderboard,
                "candidate_observations": candidate_observations,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    _write_csv(
        reports_csv_path,
        report_summaries,
        [
            "report_date",
            "candidate_count",
            "top_candidate_name",
            "top_candidate_strategy_id",
            "recommendation",
            "overfit_risk",
            "summary",
            "top_annual_return",
            "top_sharpe",
        ],
    )
    _write_csv(
        candidates_csv_path,
        candidate_leaderboard,
        [
            "name",
            "strategy_id",
            "description",
            "appearances",
            "top1_count",
            "avg_rank",
            "avg_annual_return",
            "avg_sharpe",
            "avg_max_drawdown",
            "avg_composite_score",
            "last_seen",
            "latest_overrides",
        ],
    )

    return {
        "report_summaries": report_summaries,
        "candidate_leaderboard": candidate_leaderboard,
        "candidate_observations": candidate_observations,
        "output_paths": {
            "markdown": str(markdown_path),
            "html": str(html_path),
            "json": str(json_path),
            "reports_csv": str(reports_csv_path),
            "candidates_csv": str(candidates_csv_path),
        },
    }
