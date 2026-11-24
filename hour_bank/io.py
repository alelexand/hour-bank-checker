"""Loading employees, punches and holidays from CSV or Excel exports."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

from .engine import Employee

EMPLOYEE_COLUMNS = {"employee_id", "name", "team", "weekly_hours"}
PUNCH_COLUMNS = {"employee_id", "timestamp"}


def _read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    if path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path, dtype=str)
    elif path.suffix.lower() == ".csv":
        df = pd.read_csv(path, dtype=str, sep=None, engine="python")  # detects , or ;
    else:
        raise ValueError(f"Unsupported file type: {path.suffix} (use .csv or .xlsx)")
    df.columns = [str(c).strip().lower().replace(" ", "_") for c in df.columns]
    return df.dropna(how="all")


def _require(df: pd.DataFrame, columns: set[str], path: str | Path) -> None:
    missing = columns - set(df.columns)
    if missing:
        raise ValueError(f"{Path(path).name}: missing column(s) {', '.join(sorted(missing))}")


def _hours_to_minutes(value: str, *, field: str, row: int) -> int:
    text = str(value).strip().replace(",", ".")
    try:
        if ":" in text:
            sign = -1 if text.startswith("-") else 1
            hours, minutes = text.lstrip("+-").split(":")
            return sign * (int(hours) * 60 + int(minutes))
        return round(float(text) * 60)
    except ValueError:
        raise ValueError(f"Row {row}: invalid {field} {value!r} (use 40, 37.5 or 37:30)") from None


def load_employees(path: str | Path) -> list[Employee]:
    df = _read_table(path)
    _require(df, EMPLOYEE_COLUMNS, path)
    employees = []
    for i, row in enumerate(df.itertuples(index=False), start=2):
        opening = getattr(row, "opening_balance", None)
        employees.append(Employee(
            id=str(row.employee_id).strip(),
            name=str(row.name).strip(),
            team=str(row.team).strip(),
            weekly_minutes=_hours_to_minutes(row.weekly_hours, field="weekly_hours", row=i),
            opening_balance_minutes=0 if pd.isna(opening) else _hours_to_minutes(opening, field="opening_balance", row=i),
        ))
    ids = [e.id for e in employees]
    duplicated = sorted({i for i in ids if ids.count(i) > 1})
    if duplicated:
        raise ValueError(f"Duplicated employee id(s): {', '.join(duplicated)}")
    return employees


def load_punches(path: str | Path) -> list[tuple[str, datetime]]:
    df = _read_table(path)
    _require(df, PUNCH_COLUMNS, path)
    timestamps = pd.to_datetime(df["timestamp"].str.strip(), errors="coerce", format="mixed", dayfirst=False)
    bad = df.index[timestamps.isna()].tolist()
    if bad:
        rows = ", ".join(str(i + 2) for i in bad[:5])
        raise ValueError(f"{Path(path).name}: unreadable timestamp on row(s) {rows}")
    return [(str(e).strip(), ts.to_pydatetime()) for e, ts in zip(df["employee_id"], timestamps)]


def load_holidays(path: str | Path | None) -> frozenset[date]:
    if path is None:
        return frozenset()
    df = _read_table(path)
    _require(df, {"date"}, path)
    return frozenset(pd.to_datetime(df["date"].str.strip()).dt.date)
