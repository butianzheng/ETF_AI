"""统一报告门户。"""
from __future__ import annotations

from datetime import datetime
from html import escape
import json
import os
from pathlib import Path
from typing import Any, Dict, List

from src.research_summary import aggregate_research_reports


def _load_json(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _format_pct(value: Any) -> str:
    if value is None:
        return "-"
    return f"{float(value):.2%}"


def _format_float(value: Any, digits: int = 4) -> str:
    if value is None:
        return "-"
    return f"{float(value):.{digits}f}"


def _relative(path: Path, base_dir: Path) -> str:
    return os.path.relpath(path, start=base_dir).replace("\\", "/")


def collect_daily_report_summaries(report_dir: str | Path = "reports/daily") -> List[Dict[str, Any]]:
    """收集日报摘要。"""
    report_dir = Path(report_dir)
    rows: List[Dict[str, Any]] = []
    for json_path in sorted(report_dir.glob("*.json"), reverse=True):
        payload = _load_json(json_path)
        strategy_result = payload.get("strategy_result") or {}
        risk_output = payload.get("risk_output") or {}
        execution_result = payload.get("execution_result") or {}
        report_output = payload.get("report_output") or {}
        data_qa_output = payload.get("data_qa_output") or {}
        rows.append(
            {
                "report_date": json_path.stem,
                "status": payload.get("status", "unknown"),
                "current_position": strategy_result.get("current_position"),
                "target_position": strategy_result.get("target_position"),
                "rebalance": strategy_result.get("rebalance", False),
                "active_strategy_id": (
                    (report_output.get("data") or {}).get("active_strategy_id")
                    or (payload.get("strategy_proposal") or {}).get("strategy_id")
                ),
                "risk_level": risk_output.get("risk_level"),
                "data_status": data_qa_output.get("status"),
                "execution_status": execution_result.get("status")
                or report_output.get("execution_status")
                or "pending",
                "execution_action": execution_result.get("action"),
                "summary": report_output.get("summary", ""),
                "markdown_path": str(json_path.with_suffix(".md")),
                "json_path": str(json_path),
            }
        )
    return rows


def _build_portal_html(
    daily_rows: List[Dict[str, Any]],
    research_summary: Dict[str, Any],
    base_dir: Path,
) -> str:
    latest_daily = daily_rows[0] if daily_rows else None
    research_reports = research_summary.get("report_summaries", [])
    candidate_leaderboard = research_summary.get("candidate_leaderboard", [])
    latest_research = research_reports[-1] if research_reports else None
    leader = candidate_leaderboard[0] if candidate_leaderboard else None
    research_index_href = "research/summary/index.html" if research_reports else "#"
    research_json_href = "research/summary/research_summary.json" if research_reports else "#"

    daily_rows_html = []
    for row in daily_rows:
        daily_rows_html.append(
            """
            <tr>
              <td>{report_date}</td>
              <td>{active_strategy_id}</td>
              <td>{target_position}</td>
              <td>{rebalance}</td>
              <td>{risk_level}</td>
              <td>{execution_status}</td>
              <td>{summary}</td>
              <td class="actions">
                <a href="{markdown_href}">Markdown</a>
                <a href="{json_href}">JSON</a>
              </td>
            </tr>
            """.format(
                report_date=escape(row["report_date"]),
                active_strategy_id=escape(row.get("active_strategy_id") or "-"),
                target_position=escape(row["target_position"] or "空仓"),
                rebalance="是" if row["rebalance"] else "否",
                risk_level=escape(row["risk_level"] or "-"),
                execution_status=escape(row["execution_status"] or "-"),
                summary=escape(row["summary"] or "-"),
                markdown_href=escape(_relative(Path(row["markdown_path"]), base_dir)),
                json_href=escape(_relative(Path(row["json_path"]), base_dir)),
            ).strip()
        )

    research_rows_html = []
    for row in reversed(research_reports):
        research_rows_html.append(
            """
            <tr>
              <td>{report_date}</td>
              <td>{top_candidate_name}</td>
              <td>{overfit_risk}</td>
              <td class="num">{top_annual_return}</td>
              <td class="num">{top_sharpe}</td>
              <td>{summary}</td>
            </tr>
            """.format(
                report_date=escape(row["report_date"]),
                top_candidate_name=escape(row["top_candidate_name"]),
                overfit_risk=escape(row.get("overfit_risk") or "-"),
                top_annual_return=_format_pct(row.get("top_annual_return")),
                top_sharpe=_format_float(row.get("top_sharpe")),
                summary=escape(row.get("summary") or "-"),
            ).strip()
        )

    return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>报告统一门户</title>
  <style>
    :root {{
      --bg: #f5efe5;
      --panel: rgba(255,255,255,0.9);
      --text: #16212d;
      --muted: #68707d;
      --accent: #b45309;
      --accent-dark: #92400e;
      --line: rgba(22,33,45,0.12);
      --shadow: 0 26px 60px rgba(28, 36, 54, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Avenir Next", "PingFang SC", sans-serif;
      color: var(--text);
      background:
        radial-gradient(circle at top left, rgba(180,83,9,0.16), transparent 28%),
        radial-gradient(circle at top right, rgba(15,118,110,0.14), transparent 26%),
        linear-gradient(180deg, #fbf8f1 0%, var(--bg) 100%);
    }}
    .page {{ width: min(1240px, calc(100vw - 32px)); margin: 28px auto 60px; }}
    .hero {{
      padding: 30px;
      border-radius: 30px;
      background: linear-gradient(135deg, rgba(255,255,255,0.92), rgba(255,247,235,0.94));
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
    }}
    .eyebrow {{
      font-size: 12px;
      letter-spacing: 0.18em;
      text-transform: uppercase;
      color: var(--accent);
      font-weight: 700;
    }}
    h1 {{ margin: 10px 0 0; font-size: clamp(30px, 5vw, 52px); line-height: 1.02; }}
    .sub {{ margin: 14px 0 0; color: var(--muted); max-width: 780px; line-height: 1.65; }}
    .metrics {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
      margin-top: 22px;
    }}
    .metric {{
      padding: 18px;
      border-radius: 22px;
      background: rgba(255,255,255,0.8);
      border: 1px solid rgba(180,83,9,0.1);
    }}
    .metric-label {{
      font-size: 12px;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: var(--muted);
    }}
    .metric-value {{ margin-top: 8px; font-size: clamp(22px, 3vw, 34px); font-weight: 700; }}
    .metric-note {{ margin-top: 8px; font-size: 13px; color: var(--muted); }}
    .grid {{
      display: grid;
      grid-template-columns: 1.1fr 1fr;
      gap: 22px;
      margin-top: 24px;
    }}
    .panel {{
      padding: 22px;
      border-radius: 26px;
      background: var(--panel);
      border: 1px solid var(--line);
      box-shadow: var(--shadow);
    }}
    .panel h2 {{ margin: 0 0 14px; font-size: 22px; }}
    .quick-links {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .link-card {{
      display: block;
      padding: 16px;
      border-radius: 18px;
      background: linear-gradient(180deg, #fffdf8, #f6fbf9);
      border: 1px solid var(--line);
      text-decoration: none;
      color: inherit;
    }}
    .link-card strong {{ display: block; font-size: 16px; }}
    .link-card span {{ display: block; margin-top: 8px; font-size: 13px; color: var(--muted); line-height: 1.5; }}
    .table-wrap {{ overflow-x: auto; border-radius: 18px; border: 1px solid var(--line); }}
    table {{ width: 100%; border-collapse: collapse; min-width: 720px; background: white; }}
    th, td {{ padding: 14px 16px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; font-size: 14px; }}
    th {{ background: #faf7ef; font-size: 12px; text-transform: uppercase; letter-spacing: 0.08em; color: #5f4c2c; }}
    tr:last-child td {{ border-bottom: none; }}
    .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    .actions a {{ margin-right: 10px; color: var(--accent-dark); text-decoration: none; }}
    .footer {{ margin-top: 14px; color: var(--muted); font-size: 13px; }}
    @media (max-width: 960px) {{
      .metrics {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
      .grid {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 640px) {{
      .page {{ width: min(100vw - 20px, 100%); margin-top: 18px; }}
      .hero, .panel {{ padding: 18px; border-radius: 20px; }}
      .metrics, .quick-links {{ grid-template-columns: 1fr; }}
      th, td {{ padding: 12px; }}
    }}
  </style>
</head>
<body>
  <main class="page">
    <section class="hero">
      <div class="eyebrow">Unified Report Portal</div>
      <h1>日报与研究统一门户</h1>
      <p class="sub">把生产日报闭环与研究闭环放到一个入口回看，快速判断最近执行状态、研究推荐以及可继续下钻的报告文件。</p>
      <div class="metrics">
        <article class="metric">
          <div class="metric-label">日报数量</div>
          <div class="metric-value">{daily_count}</div>
          <div class="metric-note">最近日报：{latest_daily_date}</div>
        </article>
        <article class="metric">
          <div class="metric-label">最新日报目标</div>
          <div class="metric-value">{latest_target}</div>
          <div class="metric-note">生效策略 {latest_active_strategy_id}，执行状态 {latest_execution_status}</div>
        </article>
        <article class="metric">
          <div class="metric-label">研究报告数量</div>
          <div class="metric-value">{research_count}</div>
          <div class="metric-note">最近研究：{latest_research_date}</div>
        </article>
        <article class="metric">
          <div class="metric-label">当前领先候选</div>
          <div class="metric-value">{leader_name}</div>
          <div class="metric-note">平均年化 {leader_return}</div>
        </article>
      </div>
    </section>

    <section class="grid">
      <div class="panel">
        <h2>快速入口</h2>
        <div class="quick-links">
          <a class="link-card" href="{latest_daily_md_href}">
            <strong>最新日报 Markdown</strong>
            <span>{latest_daily_desc}</span>
          </a>
          <a class="link-card" href="{latest_daily_json_href}">
            <strong>最新日报 JSON</strong>
            <span>适合程序消费和排查执行细节</span>
          </a>
          <a class="link-card" href="{research_index_href}">
            <strong>研究历史总览</strong>
            <span>查看研究推荐、候选筛选、日期筛选和排序</span>
          </a>
          <a class="link-card" href="{research_json_href}">
            <strong>研究汇总 JSON</strong>
            <span>用于后续统一看板或脚本消费</span>
          </a>
        </div>
      </div>

      <div class="panel">
        <h2>统一状态</h2>
        <div class="quick-links">
          <div class="link-card">
            <strong>最新日报</strong>
            <span>{latest_daily_summary}</span>
          </div>
          <div class="link-card">
            <strong>最新研究</strong>
            <span>{latest_research_summary}</span>
          </div>
          <div class="link-card">
            <strong>生产策略</strong>
            <span>{latest_active_strategy_id}</span>
          </div>
          <div class="link-card">
            <strong>领先候选</strong>
            <span>{leader_note}</span>
          </div>
        </div>
      </div>
    </section>

    <section class="panel" style="margin-top:24px;">
      <h2>日报时间线</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>日期</th>
              <th>生效策略</th>
              <th>目标持仓</th>
              <th>调仓</th>
              <th>风险</th>
              <th>执行状态</th>
              <th>摘要</th>
              <th>文件</th>
            </tr>
          </thead>
          <tbody>
            {daily_rows}
          </tbody>
        </table>
      </div>
    </section>

    <section class="panel" style="margin-top:24px;">
      <h2>研究时间线</h2>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>日期</th>
              <th>推荐方案</th>
              <th>过拟合风险</th>
              <th class="num">最优年化</th>
              <th class="num">最优 Sharpe</th>
              <th>摘要</th>
            </tr>
          </thead>
          <tbody>
            {research_rows}
          </tbody>
        </table>
      </div>
      <div class="footer">生成时间：{generated_at}</div>
    </section>
  </main>
</body>
</html>
    """.format(
        daily_count=len(daily_rows),
        latest_daily_date=escape(latest_daily["report_date"]) if latest_daily else "暂无",
        latest_target=escape(latest_daily["target_position"] or "空仓") if latest_daily else "-",
        latest_active_strategy_id=escape(latest_daily.get("active_strategy_id") or "-") if latest_daily else "-",
        latest_execution_status=escape(latest_daily["execution_status"] or "-") if latest_daily else "-",
        research_count=len(research_reports),
        latest_research_date=escape(latest_research["report_date"]) if latest_research else "暂无",
        leader_name=escape(leader["name"]) if leader else "-",
        leader_return=_format_pct(leader.get("avg_annual_return")) if leader else "-",
        latest_daily_md_href=escape(f"daily/{Path(latest_daily['markdown_path']).name}") if latest_daily else "#",
        latest_daily_json_href=escape(f"daily/{Path(latest_daily['json_path']).name}") if latest_daily else "#",
        latest_daily_desc=escape(latest_daily["summary"] or "查看最近一日报告") if latest_daily else "暂无日报",
        latest_daily_summary=escape(latest_daily["summary"] or "暂无日报") if latest_daily else "暂无日报",
        latest_research_summary=escape(latest_research["summary"] or "暂无研究") if latest_research else "暂无研究",
        research_index_href=escape(research_index_href),
        research_json_href=escape(research_json_href),
        leader_note=(
            f"{escape(leader['name'])}，Top1 {leader['top1_count']} 次，平均 Sharpe {_format_float(leader.get('avg_sharpe'))}"
            if leader
            else "暂无候选统计"
        ),
        daily_rows="\n".join(daily_rows_html) if daily_rows_html else '<tr><td colspan="8">暂无日报</td></tr>',
        research_rows="\n".join(research_rows_html) if research_rows_html else '<tr><td colspan="6">暂无研究报告</td></tr>',
        generated_at=datetime.now().isoformat(timespec="seconds"),
    ).strip()


def build_report_portal(
    daily_dir: str | Path = "reports/daily",
    research_dir: str | Path = "reports/research",
    output_dir: str | Path = "reports",
) -> Dict[str, Any]:
    """构建统一报告门户。"""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    daily_rows = collect_daily_report_summaries(daily_dir)
    try:
        research_result = aggregate_research_reports(report_dir=research_dir, output_dir=Path(research_dir) / "summary")
    except FileNotFoundError:
        research_result = {
            "report_summaries": [],
            "candidate_leaderboard": [],
            "candidate_observations": [],
            "output_paths": {},
        }

    portal_payload = {
        "daily_summaries": daily_rows,
        "research_summary": {
            "report_count": len(research_result["report_summaries"]),
            "report_summaries": research_result["report_summaries"],
            "candidate_leaderboard": research_result["candidate_leaderboard"],
            "candidate_observations": research_result["candidate_observations"],
            "output_paths": research_result["output_paths"],
        },
    }
    json_path = output_dir / "portal_summary.json"
    html_path = output_dir / "index.html"
    json_path.write_text(json.dumps(portal_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    html_path.write_text(
        _build_portal_html(daily_rows=daily_rows, research_summary=portal_payload["research_summary"], base_dir=output_dir),
        encoding="utf-8",
    )
    return {
        "daily_summaries": daily_rows,
        "research_summary": portal_payload["research_summary"],
        "output_paths": {
            "html": str(html_path),
            "json": str(json_path),
        },
    }
