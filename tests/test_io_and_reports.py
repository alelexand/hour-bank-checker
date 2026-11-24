from datetime import date

import pytest
from openpyxl import load_workbook

from hour_bank.cli import main
from hour_bank.engine import ABSENCE, LONG_DAY, MISSING_PUNCH, NON_WORKDAY, SHORT_BREAK, SHORT_REST, Rules, build_report
from hour_bank.io import load_employees, load_holidays, load_punches
from hour_bank.report_excel import write_excel
from hour_bank.report_html import render_html
from hour_bank.sample import generate


@pytest.fixture
def sample(tmp_path):
    return generate(tmp_path / "data")


@pytest.fixture
def report(sample):
    rules = Rules(holidays=load_holidays(sample["holidays"]))
    return build_report(load_employees(sample["employees"]), load_punches(sample["punches"]),
                        date(2026, 10, 1), date(2026, 10, 31), rules)


def test_sample_is_deterministic(tmp_path):
    a, b = generate(tmp_path / "a"), generate(tmp_path / "b")
    assert a["punches"].read_text() == b["punches"].read_text()


def test_sample_contains_every_planted_problem(report):
    found = {(a.employee_id, a.code) for a in report.anomalies}
    assert {("E002", MISSING_PUNCH), ("E003", SHORT_BREAK), ("E004", LONG_DAY), ("E004", SHORT_REST),
            ("E005", ABSENCE), ("E006", NON_WORKDAY)} <= found


def test_part_time_employee_expects_four_hours_a_day(report):
    greta = next(d for d in report.days if d.employee_id == "E007" and d.day == date(2026, 10, 1))
    assert greta.expected_minutes == 240


def test_load_employees_accepts_hh_mm_and_semicolons(tmp_path):
    path = tmp_path / "e.csv"
    path.write_text("Employee ID;Name;Team;Weekly hours;Opening balance\nA1;Ann;Ops;37,5;-01:30\n", encoding="utf-8")
    [emp] = load_employees(path)
    assert (emp.id, emp.weekly_minutes, emp.opening_balance_minutes) == ("A1", 2250, -90)


def test_load_employees_reports_missing_columns(tmp_path):
    path = tmp_path / "e.csv"
    path.write_text("employee_id,name\nA1,Ann\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing column"):
        load_employees(path)


def test_load_punches_reports_bad_rows(tmp_path):
    path = tmp_path / "p.csv"
    path.write_text("employee_id,timestamp\nA1,2026-10-01 09:00\nA1,yesterday\n", encoding="utf-8")
    with pytest.raises(ValueError, match="row\\(s\\) 3"):
        load_punches(path)


def test_load_punches_from_excel(tmp_path, sample):
    import pandas as pd
    xlsx = tmp_path / "p.xlsx"
    pd.read_csv(sample["punches"]).to_excel(xlsx, index=False)
    assert load_punches(xlsx) == load_punches(sample["punches"])


def test_excel_report_has_three_sheets(tmp_path, report):
    wb = load_workbook(write_excel(report, tmp_path / "r.xlsx"))
    assert wb.sheetnames == ["Summary", "Issues", "Daily"]
    assert wb["Summary"].max_row == 1 + len(report.summaries)
    assert wb["Issues"].max_row == 1 + len(report.anomalies)
    assert wb["Daily"].max_row == 1 + len(report.days)


def test_html_report_escapes_names():
    from hour_bank import Employee
    risky = build_report([Employee("X", "<script>alert(1)</script>", "QA", 2400)], [], date(2026, 10, 1), date(2026, 10, 2))
    html = render_html(risky)
    assert "<script>alert" not in html and "&lt;script&gt;" in html


def test_cli_end_to_end(tmp_path, capsys):
    data, out = tmp_path / "data", tmp_path / "out"
    assert main(["sample", "--out", str(data)]) == 0
    assert main(["report", "--data", str(data), "--out", str(out)]) == 0
    assert (out / "hour_bank_2026-10.xlsx").exists() and (out / "hour_bank_2026-10.html").exists()
    assert "1 error(s) to fix" in capsys.readouterr().out
    assert main(["report", "--data", str(data), "--out", str(out), "--strict"]) == 1


def test_cli_friendly_error_for_missing_file(tmp_path, capsys):
    assert main(["report", "--employees", str(tmp_path / "nope.csv"), "--punches", str(tmp_path / "nope.csv")]) == 2
    assert "File not found" in capsys.readouterr().err
