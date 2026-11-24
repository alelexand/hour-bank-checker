"""Core rules: pairs punches into work periods, computes daily balances and flags issues.

The engine is plain Python on purpose: it has no I/O and no pandas, so every rule can be
unit-tested with a handful of datetimes.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Iterable

# Severity levels, from most to least urgent.
ERROR, WARNING, INFO = "error", "warning", "info"

MISSING_PUNCH = "MISSING_PUNCH"
ABSENCE = "ABSENCE"
SHORT_BREAK = "SHORT_BREAK"
LONG_DAY = "LONG_DAY"
SHORT_REST = "SHORT_REST"
NON_WORKDAY = "NON_WORKDAY"
DUPLICATE_PUNCH = "DUPLICATE_PUNCH"

SEVERITY = {
    MISSING_PUNCH: ERROR,
    ABSENCE: WARNING,
    SHORT_BREAK: WARNING,
    LONG_DAY: WARNING,
    SHORT_REST: WARNING,
    NON_WORKDAY: INFO,
    DUPLICATE_PUNCH: INFO,
}


@dataclass(frozen=True)
class Rules:
    """Company policy. Defaults follow common European practice; adjust per country/contract."""

    tolerance_minutes: int = 10
    """Daily differences within +/- this many minutes are treated as zero."""
    break_required_after_minutes: int = 6 * 60
    """Working longer than this in a day requires a break."""
    min_break_minutes: int = 30
    max_daily_minutes: int = 10 * 60
    min_rest_minutes: int = 11 * 60
    """Minimum rest between the end of one working day and the start of the next."""
    duplicate_window_minutes: int = 2
    """Punches closer than this are treated as one accidental double punch."""
    workdays: tuple[int, ...] = (0, 1, 2, 3, 4)
    """Weekday numbers that are regular working days (Monday = 0)."""
    holidays: frozenset[date] = field(default_factory=frozenset)


@dataclass(frozen=True)
class Employee:
    id: str
    name: str
    team: str
    weekly_minutes: int
    opening_balance_minutes: int = 0


@dataclass(frozen=True)
class Anomaly:
    employee_id: str
    day: date
    code: str
    message: str

    @property
    def severity(self) -> str:
        return SEVERITY[self.code]


@dataclass
class DayResult:
    employee_id: str
    day: date
    punches: list[datetime]
    worked_minutes: int
    expected_minutes: int
    break_minutes: int
    difference_minutes: int
    counted: bool
    anomalies: list[Anomaly]


@dataclass
class EmployeeSummary:
    employee: Employee
    worked_minutes: int
    expected_minutes: int
    period_balance_minutes: int
    closing_balance_minutes: int
    days_with_issues: int
    errors: int


@dataclass
class Report:
    start: date
    end: date
    rules: Rules
    summaries: list[EmployeeSummary]
    days: list[DayResult]

    @property
    def anomalies(self) -> list[Anomaly]:
        order = {ERROR: 0, WARNING: 1, INFO: 2}
        found = [a for d in self.days for a in d.anomalies]
        return sorted(found, key=lambda a: (order[a.severity], a.day, a.employee_id))


def _minutes(delta: timedelta) -> int:
    return int(round(delta.total_seconds() / 60))


def expected_minutes_for(employee: Employee, day: date, rules: Rules) -> int:
    if day.weekday() not in rules.workdays or day in rules.holidays:
        return 0
    return round(employee.weekly_minutes / len(rules.workdays))


def dedupe_punches(punches: Iterable[datetime], window_minutes: int) -> tuple[list[datetime], int]:
    """Sort punches and drop the ones that follow the previous punch within the window."""
    kept: list[datetime] = []
    dropped = 0
    for p in sorted(punches):
        if kept and _minutes(p - kept[-1]) < window_minutes:
            dropped += 1
            continue
        kept.append(p)
    return kept, dropped


def evaluate_day(
    employee: Employee,
    day: date,
    raw_punches: list[datetime],
    rules: Rules,
    previous_last_punch: datetime | None = None,
) -> DayResult:
    punches, duplicates = dedupe_punches(raw_punches, rules.duplicate_window_minutes)
    expected = expected_minutes_for(employee, day, rules)
    anomalies: list[Anomaly] = []

    def flag(code: str, message: str) -> None:
        anomalies.append(Anomaly(employee.id, day, code, message))

    if duplicates:
        flag(DUPLICATE_PUNCH, f"{duplicates} duplicate punch(es) ignored")

    if not punches:
        if expected:
            flag(ABSENCE, "No punches on a working day")
        return DayResult(employee.id, day, [], 0, expected, 0, -expected, True, anomalies)

    if len(punches) % 2:
        times = ", ".join(p.strftime("%H:%M") for p in punches)
        flag(MISSING_PUNCH, f"Odd number of punches ({times}); day left out of the balance until fixed")
        return DayResult(employee.id, day, punches, 0, expected, 0, 0, False, anomalies)

    periods = list(zip(punches[0::2], punches[1::2]))
    worked = sum(_minutes(out - start) for start, out in periods)
    breaks = sum(_minutes(periods[i + 1][0] - periods[i][1]) for i in range(len(periods) - 1))

    if worked > rules.break_required_after_minutes and breaks < rules.min_break_minutes:
        flag(SHORT_BREAK, f"Break of {breaks} min after {worked // 60}h{worked % 60:02d} worked "
                          f"(minimum {rules.min_break_minutes} min)")
    if worked > rules.max_daily_minutes:
        flag(LONG_DAY, f"Worked {worked // 60}h{worked % 60:02d} (limit {rules.max_daily_minutes // 60}h)")
    if previous_last_punch is not None:
        rest = _minutes(punches[0] - previous_last_punch)
        if rest < rules.min_rest_minutes:
            flag(SHORT_REST, f"Only {rest // 60}h{rest % 60:02d} of rest since the previous shift "
                             f"(minimum {rules.min_rest_minutes // 60}h)")
    if not expected:
        flag(NON_WORKDAY, "Worked on a weekend or holiday; all time counts as extra")

    difference = worked - expected
    if abs(difference) <= rules.tolerance_minutes:
        difference = 0

    return DayResult(employee.id, day, punches, worked, expected, breaks, difference, True, anomalies)


def build_report(
    employees: Iterable[Employee],
    punches: Iterable[tuple[str, datetime]],
    start: date,
    end: date,
    rules: Rules | None = None,
) -> Report:
    """Evaluate every employee for every day in [start, end]."""
    if end < start:
        raise ValueError("end date is before start date")
    rules = rules or Rules()
    employees = list(employees)
    known = {e.id for e in employees}

    by_employee_day: dict[tuple[str, date], list[datetime]] = defaultdict(list)
    last_before_start: dict[str, datetime] = {}
    unknown: set[str] = set()
    for employee_id, ts in punches:
        if employee_id not in known:
            unknown.add(employee_id)
            continue
        if ts.date() < start:
            # Kept only to check rest time on the first day of the period.
            if ts.date() == start - timedelta(days=1):
                prev = last_before_start.get(employee_id)
                last_before_start[employee_id] = max(prev, ts) if prev else ts
            continue
        if ts.date() > end:
            continue
        by_employee_day[(employee_id, ts.date())].append(ts)
    if unknown:
        raise ValueError(f"Punches for unknown employee id(s): {', '.join(sorted(unknown))}")

    all_days = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    days: list[DayResult] = []
    summaries: list[EmployeeSummary] = []
    for employee in employees:
        previous_last = last_before_start.get(employee.id)
        results = []
        for day in all_days:
            result = evaluate_day(employee, day, by_employee_day.get((employee.id, day), []), rules, previous_last)
            results.append(result)
            if result.punches:
                previous_last = result.punches[-1]
            elif day.weekday() in rules.workdays:
                previous_last = None
        days.extend(results)
        counted = [r for r in results if r.counted]
        period_balance = sum(r.difference_minutes for r in counted)
        summaries.append(EmployeeSummary(
            employee=employee,
            worked_minutes=sum(r.worked_minutes for r in counted),
            expected_minutes=sum(r.expected_minutes for r in counted),
            period_balance_minutes=period_balance,
            closing_balance_minutes=employee.opening_balance_minutes + period_balance,
            days_with_issues=sum(1 for r in results if any(a.severity != INFO for a in r.anomalies)),
            errors=sum(1 for r in results for a in r.anomalies if a.severity == ERROR),
        ))
    return Report(start, end, rules, summaries, days)
