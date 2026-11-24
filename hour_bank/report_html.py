"""Self-contained HTML report (no external files), readable on desktop and mobile."""

from __future__ import annotations

from collections import Counter
from html import escape
from pathlib import Path

from .engine import ERROR, INFO, WARNING, Report
from .formatting import fmt_minutes

CSS = """
:root{--bg:#f6f7fb;--card:#fff;--text:#0f172a;--muted:#5b6478;--border:#e3e7ef;--accent:#1e3a8a;
--pos:#15803d;--neg:#b91c1c;--error-bg:#fde2e1;--error:#9f1239;--warning-bg:#fef3c7;--warning:#92400e;
--info-bg:#e0ecff;--info:#1e40af}
@media (prefers-color-scheme:dark){:root{--bg:#0b1120;--card:#131d33;--text:#e7ecf5;--muted:#9aa6bd;
--border:#23304b;--accent:#93b4ff;--pos:#4ade80;--neg:#f87171;--error-bg:#3b1219;--error:#fda4af;
--warning-bg:#3a2a0b;--warning:#fcd34d;--info-bg:#15254a;--info:#93c5fd}}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;
background:var(--bg);color:var(--text);line-height:1.5}
.wrap{max-width:1100px;margin:0 auto;padding:32px 16px 48px}
h1{margin:0 0 4px;font-size:26px}h2{font-size:18px;margin:36px 0 12px}
.sub{color:var(--muted);margin:0 0 24px}
.tiles{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}
.tile{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:16px}
.tile .label{color:var(--muted);font-size:13px}.tile .value{font-size:26px;font-weight:700;margin-top:4px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;overflow-x:auto}
table{width:100%;border-collapse:collapse;font-size:14px}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--border);white-space:nowrap}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted);font-weight:600}
tr:last-child td{border-bottom:0}td.num{text-align:right;font-variant-numeric:tabular-nums}
td.details{white-space:normal;min-width:260px}
.pos{color:var(--pos);font-weight:700}.neg{color:var(--neg);font-weight:700}
.badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:12px;font-weight:600}
.error{background:var(--error-bg);color:var(--error)}.warning{background:var(--warning-bg);color:var(--warning)}
.info{background:var(--info-bg);color:var(--info)}
footer{margin-top:32px;color:var(--muted);font-size:13px}
@media (max-width:700px){.tiles{grid-template-columns:repeat(2,1fr)}}
"""


def _balance(minutes: int) -> str:
    cls = "pos" if minutes > 0 else "neg" if minutes < 0 else ""
    return f'<td class="num {cls}">{fmt_minutes(minutes, signed=True)}</td>'


def render_html(report: Report) -> str:
    names = {s.employee.id: s.employee.name for s in report.summaries}
    anomalies = report.anomalies
    by_severity = Counter(a.severity for a in anomalies)
    total_balance = sum(s.closing_balance_minutes for s in report.summaries)

    tiles = [
        ("Employees", str(len(report.summaries))),
        ("Total closing balance", fmt_minutes(total_balance, signed=True)),
        ("Errors to fix", str(by_severity[ERROR])),
        ("Warnings", str(by_severity[WARNING])),
    ]
    tiles_html = "".join(
        f'<div class="tile"><div class="label">{label}</div><div class="value">{value}</div></div>'
        for label, value in tiles
    )

    summary_rows = "".join(
        "<tr>"
        f"<td>{escape(s.employee.name)}</td><td>{escape(s.employee.team)}</td>"
        f'<td class="num">{fmt_minutes(s.employee.opening_balance_minutes, signed=True)}</td>'
        f'<td class="num">{fmt_minutes(s.worked_minutes)}</td>'
        f'<td class="num">{fmt_minutes(s.expected_minutes)}</td>'
        f"{_balance(s.period_balance_minutes)}{_balance(s.closing_balance_minutes)}"
        f'<td class="num">{s.days_with_issues}</td>'
        "</tr>"
        for s in report.summaries
    )

    issue_rows = "".join(
        "<tr>"
        f'<td><span class="badge {a.severity}">{a.severity}</span></td>'
        f"<td>{a.day.isoformat()}</td><td>{escape(names[a.employee_id])}</td>"
        f"<td>{a.code}</td><td class=\"details\">{escape(a.message)}</td>"
        "</tr>"
        for a in anomalies
    ) or '<tr><td colspan="5">No issues found.</td></tr>'

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Hour bank report</title>
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
  <h1>Hour bank report</h1>
  <p class="sub">{report.start:%d %b %Y} to {report.end:%d %b %Y} ·
     tolerance ±{report.rules.tolerance_minutes} min/day ·
     minimum rest {report.rules.min_rest_minutes // 60}h between shifts</p>
  <div class="tiles">{tiles_html}</div>

  <h2>Balances</h2>
  <div class="card"><table>
    <thead><tr><th>Employee</th><th>Team</th><th>Opening</th><th>Worked</th><th>Expected</th>
    <th>Period</th><th>Closing</th><th>Days with issues</th></tr></thead>
    <tbody>{summary_rows}</tbody>
  </table></div>

  <h2>Issues to review ({len(anomalies)})</h2>
  <div class="card"><table>
    <thead><tr><th>Severity</th><th>Date</th><th>Employee</th><th>Issue</th><th>Details</th></tr></thead>
    <tbody>{issue_rows}</tbody>
  </table></div>

  <footer>Generated by hour-bank-checker. Days with an error are left out of the balance until the punches are fixed.</footer>
</div>
</body>
</html>
"""


def write_html(report: Report, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_html(report), encoding="utf-8")
    return path
