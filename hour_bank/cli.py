"""Command line: `python -m hour_bank sample` and `python -m hour_bank report ...`."""

from __future__ import annotations

import argparse
import calendar
import sys
from dataclasses import replace
from datetime import date
from pathlib import Path

from .engine import ERROR, WARNING, Rules, build_report
from .formatting import fmt_minutes
from .io import load_employees, load_holidays, load_punches
from .report_excel import write_excel
from .report_html import write_html
from .sample import generate


def _parse_date(text: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid date {text!r}, use YYYY-MM-DD") from None


def _month_bounds(punches) -> tuple[date, date]:
    first = min(ts for _, ts in punches).date()
    last_day = calendar.monthrange(first.year, first.month)[1]
    return first.replace(day=1), first.replace(day=last_day)


def cmd_sample(args: argparse.Namespace) -> int:
    paths = generate(args.out, seed=args.seed)
    for kind, path in paths.items():
        print(f"  {kind:<10} {path}")
    print(f"\nNext: python -m hour_bank report --data {args.out}")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    data = Path(args.data) if args.data else None
    employees_path = args.employees or (data / "employees.csv" if data else None)
    punches_path = args.punches or (data / "punches.csv" if data else None)
    holidays_path = args.holidays or (data / "holidays.csv" if data and (data / "holidays.csv").exists() else None)
    if not employees_path or not punches_path:
        print("error: give --data FOLDER or both --employees and --punches", file=sys.stderr)
        return 2

    employees = load_employees(employees_path)
    punches = load_punches(punches_path)
    if not punches:
        print("error: the punches file is empty", file=sys.stderr)
        return 2
    default_start, default_end = _month_bounds(punches)
    start, end = args.start or default_start, args.end or default_end

    rules = replace(Rules(), holidays=load_holidays(holidays_path), tolerance_minutes=args.tolerance)
    report = build_report(employees, punches, start, end, rules)

    out = Path(args.out)
    excel = write_excel(report, out / f"hour_bank_{start:%Y-%m}.xlsx")
    html = write_html(report, out / f"hour_bank_{start:%Y-%m}.html")

    print(f"\nHour bank {start} to {end}\n")
    print(f"  {'Employee':<18}{'Opening':>9}{'Period':>9}{'Closing':>9}  Issues")
    for s in report.summaries:
        print(f"  {s.employee.name:<18}"
              f"{fmt_minutes(s.employee.opening_balance_minutes, True):>9}"
              f"{fmt_minutes(s.period_balance_minutes, True):>9}"
              f"{fmt_minutes(s.closing_balance_minutes, True):>9}  {s.days_with_issues or ''}")
    errors = sum(1 for a in report.anomalies if a.severity == ERROR)
    warnings = sum(1 for a in report.anomalies if a.severity == WARNING)
    print(f"\n  {errors} error(s) to fix, {warnings} warning(s) to review")
    print(f"\n  Excel: {excel}\n  HTML:  {html}")
    return 1 if errors and args.strict else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="hour_bank", description="Turn time-clock punches into hour bank balances.")
    sub = parser.add_subparsers(dest="command", required=True)

    s = sub.add_parser("sample", help="generate a month of fictional data")
    s.add_argument("--out", default="sample_data")
    s.add_argument("--seed", type=int, default=42)
    s.set_defaults(func=cmd_sample)

    r = sub.add_parser("report", help="build the Excel and HTML reports")
    r.add_argument("--data", help="folder with employees.csv, punches.csv and optional holidays.csv")
    r.add_argument("--employees", type=Path, help="employees file (.csv or .xlsx)")
    r.add_argument("--punches", type=Path, help="punches file (.csv or .xlsx)")
    r.add_argument("--holidays", type=Path, help="holidays file (.csv or .xlsx)")
    r.add_argument("--start", type=_parse_date, help="first day (default: first day of the punches' month)")
    r.add_argument("--end", type=_parse_date, help="last day (default: last day of that month)")
    r.add_argument("--tolerance", type=int, default=Rules().tolerance_minutes, help="daily tolerance in minutes")
    r.add_argument("--out", default="reports")
    r.add_argument("--strict", action="store_true", help="exit with code 1 when there are errors (for automation)")
    r.set_defaults(func=cmd_report)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
