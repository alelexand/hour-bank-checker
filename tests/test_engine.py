from datetime import date, datetime

import pytest

from hour_bank import Employee, Rules, build_report, fmt_minutes
from hour_bank.engine import (
    ABSENCE, DUPLICATE_PUNCH, LONG_DAY, MISSING_PUNCH, NON_WORKDAY, SHORT_BREAK, SHORT_REST,
    evaluate_day,
)

EMP = Employee("E1", "Test Person", "QA", weekly_minutes=40 * 60)
MON = date(2026, 10, 12)  # a Monday
RULES = Rules()


def at(day: date, hhmm: str) -> datetime:
    h, m = map(int, hhmm.split(":"))
    return datetime(day.year, day.month, day.day, h, m)


def day(*times: str, d: date = MON, prev: datetime | None = None, rules: Rules = RULES):
    return evaluate_day(EMP, d, [at(d, t) for t in times], rules, prev)


def codes(result) -> set[str]:
    return {a.code for a in result.anomalies}


def test_regular_day_is_balanced():
    r = day("09:00", "13:00", "14:00", "18:00")
    assert (r.worked_minutes, r.expected_minutes, r.break_minutes, r.difference_minutes) == (480, 480, 60, 0)
    assert r.anomalies == []


def test_overtime_counts_beyond_tolerance():
    assert day("09:00", "13:00", "14:00", "18:45").difference_minutes == 45


def test_small_difference_within_tolerance_is_ignored():
    assert day("09:00", "13:00", "14:00", "18:08").difference_minutes == 0
    assert day("09:00", "13:00", "14:00", "17:52").difference_minutes == 0


def test_tolerance_is_configurable():
    strict = Rules(tolerance_minutes=0)
    assert day("09:00", "13:00", "14:00", "18:08", rules=strict).difference_minutes == 8


def test_punch_order_does_not_matter():
    assert day("18:00", "09:00", "14:00", "13:00").worked_minutes == 480


def test_missing_punch_is_an_error_and_not_counted():
    r = day("09:00", "13:00", "18:00")
    assert codes(r) == {MISSING_PUNCH}
    assert r.anomalies[0].severity == "error"
    assert not r.counted and r.difference_minutes == 0


def test_absence_on_workday_counts_negative():
    r = day()
    assert codes(r) == {ABSENCE}
    assert r.difference_minutes == -480


def test_no_punches_on_weekend_is_fine():
    r = day(d=date(2026, 10, 17))
    assert r.anomalies == [] and r.difference_minutes == 0


def test_weekend_work_is_all_extra():
    r = day("09:00", "13:00", d=date(2026, 10, 17))
    assert codes(r) == {NON_WORKDAY}
    assert r.difference_minutes == 240


def test_holiday_has_no_expected_hours():
    rules = Rules(holidays=frozenset({MON}))
    assert day(rules=rules).anomalies == []
    assert day("09:00", "12:00", rules=rules).difference_minutes == 180


def test_short_break_after_six_hours():
    assert SHORT_BREAK in codes(day("09:00", "13:00", "13:15", "17:15"))


def test_no_break_needed_for_short_day():
    assert SHORT_BREAK not in codes(day("09:00", "14:00"))


def test_long_day():
    assert LONG_DAY in codes(day("08:00", "12:00", "13:00", "20:30"))


def test_short_rest_between_shifts():
    previous = datetime(2026, 10, 11, 23, 0)
    assert SHORT_REST in codes(day("08:00", "12:00", "13:00", "17:00", prev=previous))
    assert SHORT_REST not in codes(day("10:00", "13:00", "14:00", "19:00", prev=previous))


def test_duplicate_punch_is_ignored():
    r = evaluate_day(EMP, MON, [at(MON, "09:00"), datetime(2026, 10, 12, 9, 0, 40),
                                at(MON, "13:00"), at(MON, "14:00"), at(MON, "18:00")], RULES)
    assert codes(r) == {DUPLICATE_PUNCH}
    assert r.counted and r.worked_minutes == 480


def test_report_balances_and_opening_balance():
    emp = Employee("E1", "Test Person", "QA", 40 * 60, opening_balance_minutes=-30)
    punches = [("E1", at(MON, t)) for t in ("09:00", "13:00", "14:00", "19:00")]
    report = build_report([emp], punches, MON, MON)
    s = report.summaries[0]
    assert (s.period_balance_minutes, s.closing_balance_minutes) == (60, 30)


def test_report_checks_rest_against_day_before_period():
    punches = [("E1", datetime(2026, 10, 11, 23, 30))] + [("E1", at(MON, t)) for t in ("07:00", "11:00", "12:00", "16:00")]
    report = build_report([EMP], punches, MON, MON)
    assert SHORT_REST in codes(report.days[0])


def test_report_rejects_unknown_employee():
    with pytest.raises(ValueError, match="unknown employee"):
        build_report([EMP], [("X9", at(MON, "09:00"))], MON, MON)


def test_report_rejects_inverted_period():
    with pytest.raises(ValueError):
        build_report([EMP], [], MON, date(2026, 10, 1))


@pytest.mark.parametrize("minutes, signed, expected", [
    (0, False, "00:00"), (75, False, "01:15"), (-75, False, "-01:15"), (75, True, "+01:15"), (600, True, "+10:00"),
])
def test_fmt_minutes(minutes, signed, expected):
    assert fmt_minutes(minutes, signed) == expected
