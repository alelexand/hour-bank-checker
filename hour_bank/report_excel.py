"""Excel report: Summary, Issues and Daily sheets, ready to send to HR or payroll."""

from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet

from .engine import ERROR, INFO, WARNING, Report
from .formatting import fmt_minutes

HEADER_FILL = PatternFill("solid", fgColor="1E3A8A")
HEADER_FONT = Font(bold=True, color="FFFFFF")
FILLS = {
    ERROR: PatternFill("solid", fgColor="FDE2E1"),
    WARNING: PatternFill("solid", fgColor="FEF3C7"),
    INFO: PatternFill("solid", fgColor="E0ECFF"),
}
POSITIVE = Font(color="15803D", bold=True)
NEGATIVE = Font(color="B91C1C", bold=True)
HOURS_FORMAT = "+0.00;-0.00;0.00"


def _hours(minutes: int) -> float:
    return round(minutes / 60, 2)


def _sheet(ws: Worksheet, headers: list[str], rows: list[list], widths: list[int]) -> None:
    ws.append(headers)
    for cell in ws[1]:
        cell.fill, cell.font = HEADER_FILL, HEADER_FONT
        cell.alignment = Alignment(vertical="center")
    for row in rows:
        ws.append(row)
    for i, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = width
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = ws.dimensions


def write_excel(report: Report, path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    names = {s.employee.id: s.employee.name for s in report.summaries}
    wb = Workbook()

    summary = wb.active
    summary.title = "Summary"
    _sheet(summary,
           ["Employee ID", "Name", "Team", "Opening (h)", "Worked (h)", "Expected (h)",
            "Period balance (h)", "Closing balance (h)", "Closing (hh:mm)", "Days with issues", "Errors"],
           [[s.employee.id, s.employee.name, s.employee.team,
             _hours(s.employee.opening_balance_minutes), _hours(s.worked_minutes), _hours(s.expected_minutes),
             _hours(s.period_balance_minutes), _hours(s.closing_balance_minutes),
             fmt_minutes(s.closing_balance_minutes, signed=True), s.days_with_issues, s.errors]
            for s in report.summaries],
           [12, 20, 13, 12, 12, 13, 18, 19, 15, 16, 8])
    for row in summary.iter_rows(min_row=2):
        for cell in row[3:8]:
            cell.number_format = HOURS_FORMAT
        for cell in (row[6], row[7]):
            cell.font = POSITIVE if cell.value > 0 else NEGATIVE if cell.value < 0 else Font()
        if row[10].value:
            row[10].fill = FILLS[ERROR]

    issues = wb.create_sheet("Issues")
    _sheet(issues,
           ["Severity", "Date", "Employee ID", "Name", "Issue", "Details"],
           [[a.severity.upper(), a.day, a.employee_id, names[a.employee_id], a.code, a.message]
            for a in report.anomalies],
           [10, 12, 12, 20, 18, 80])
    for row in issues.iter_rows(min_row=2):
        row[1].number_format = "yyyy-mm-dd"
        for cell in row:
            cell.fill = FILLS[row[0].value.lower()]

    daily = wb.create_sheet("Daily")
    _sheet(daily,
           ["Date", "Weekday", "Employee ID", "Name", "Punches", "Worked (h)", "Expected (h)",
            "Break (min)", "Difference (h)", "Counted", "Issues"],
           [[d.day, d.day.strftime("%a"), d.employee_id, names[d.employee_id],
             " ".join(p.strftime("%H:%M") for p in d.punches), _hours(d.worked_minutes),
             _hours(d.expected_minutes), d.break_minutes, _hours(d.difference_minutes),
             "yes" if d.counted else "NO", ", ".join(a.code for a in d.anomalies)]
            for d in report.days],
           [12, 9, 12, 20, 30, 11, 12, 11, 14, 9, 30])
    for row in daily.iter_rows(min_row=2):
        row[0].number_format = "yyyy-mm-dd"
        for cell in (row[5], row[6], row[8]):
            cell.number_format = HOURS_FORMAT
        severities = {a.severity for a in report.days[row[0].row - 2].anomalies}
        for level in (ERROR, WARNING, INFO):
            if level in severities:
                row[10].fill = FILLS[level]
                break

    wb.save(path)
    return path
