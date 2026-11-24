"""Generates a month of fictional time-clock data with realistic problems mixed in.

Every name and number here is invented. The generator is seeded, so the output is
identical on every run.
"""

from __future__ import annotations

import csv
import random
from datetime import date, datetime, time, timedelta
from pathlib import Path

EMPLOYEES = [
    # id, name, team, weekly hours, opening balance (hh:mm)
    ("E001", "Ana Ribeiro", "Operations", "40", "02:30"),
    ("E002", "Bruno Costa", "Operations", "40", "00:00"),
    ("E003", "Clara Dubois", "Finance", "40", "-01:15"),
    ("E004", "Daniel Weber", "Operations", "40", "05:00"),
    ("E005", "Elena Rossi", "Support", "40", "00:45"),
    ("E006", "Filipe Santos", "Support", "40", "-00:30"),
    ("E007", "Greta Novak", "Finance", "20", "00:00"),
    ("E008", "Hugo Martins", "Operations", "40", "01:00"),
]

HOLIDAYS = [("2026-10-05", "Public holiday")]
YEAR, MONTH = 2026, 10


def _at(day: date, hh: int, mm: int, jitter: int, rng: random.Random) -> datetime:
    return datetime.combine(day, time(hh, mm)) + timedelta(minutes=rng.randint(-jitter, jitter))


def _regular_day(day: date, rng: random.Random, extra: int = 0) -> list[datetime]:
    start = _at(day, 9, 0, 8, rng)
    lunch_out = _at(day, 13, 0, 10, rng)
    lunch_in = lunch_out + timedelta(minutes=60 + rng.randint(-3, 5))
    out = start + timedelta(hours=9, minutes=rng.randint(-6, 6) + extra)
    return [start, lunch_out, lunch_in, out]


def generate(out_dir: str | Path, seed: int = 42) -> dict[str, Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    holidays = {date.fromisoformat(d) for d, _ in HOLIDAYS}

    first = date(YEAR, MONTH, 1)
    days = [first + timedelta(days=i) for i in range(31) if (first + timedelta(days=i)).month == MONTH]
    workdays = [d for d in days if d.weekday() < 5 and d not in holidays]

    punches: list[tuple[str, datetime]] = []
    for emp_id, *_ in EMPLOYEES:
        for day in workdays:
            if emp_id == "E007":  # part-time mornings, no lunch break
                start = _at(day, 8, 30, 6, rng)
                punches += [(emp_id, start), (emp_id, start + timedelta(hours=4, minutes=rng.randint(-5, 5)))]
                continue
            extra = 30 if emp_id == "E008" else 0  # Hugo stays late every day
            punches += [(emp_id, p) for p in _regular_day(day, rng, extra)]

    def replace_day(emp_id: str, day: date, new: list[datetime]) -> None:
        punches[:] = [(e, p) for e, p in punches if not (e == emp_id and p.date() == day)]
        punches.extend((emp_id, p) for p in new)

    d = lambda n: date(YEAR, MONTH, n)  # noqa: E731
    dt = lambda n, hh, mm: datetime(YEAR, MONTH, n, hh, mm)  # noqa: E731

    # Bruno forgot to punch back in after lunch.
    replace_day("E002", d(14), [dt(14, 8, 58), dt(14, 13, 2), dt(14, 18, 4)])
    # Clara took a 20-minute lunch.
    replace_day("E003", d(7), [dt(7, 9, 1), dt(7, 13, 0), dt(7, 13, 20), dt(7, 17, 45)])
    # Daniel closed the quarter: very long day, then back early next morning.
    replace_day("E004", d(20), [dt(20, 8, 0), dt(20, 12, 30), dt(20, 13, 15), dt(20, 22, 30)])
    replace_day("E004", d(21), [dt(21, 7, 30), dt(21, 12, 0), dt(21, 13, 0), dt(21, 16, 30)])
    # Elena missed a day with no punches at all.
    replace_day("E005", d(22), [])
    # Filipe covered a Saturday shift.
    punches += [("E006", dt(17, 9, 0)), ("E006", dt(17, 13, 5))]
    # Greta's badge registered twice.
    punches.append(("E007", next(p for e, p in punches if e == "E007" and p.date() == d(9)) + timedelta(seconds=40)))

    punches.sort(key=lambda x: (x[0], x[1]))

    paths = {
        "employees": out / "employees.csv",
        "punches": out / "punches.csv",
        "holidays": out / "holidays.csv",
    }
    with paths["employees"].open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["employee_id", "name", "team", "weekly_hours", "opening_balance"])
        w.writerows(EMPLOYEES)
    with paths["punches"].open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["employee_id", "timestamp"])
        w.writerows((e, p.strftime("%Y-%m-%d %H:%M:%S")) for e, p in punches)
    with paths["holidays"].open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["date", "description"])
        w.writerows(HOLIDAYS)
    return paths
