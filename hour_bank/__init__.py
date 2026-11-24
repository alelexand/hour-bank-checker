"""Hour bank checker: turns raw time-clock punches into balances and a list of issues to fix."""

from .engine import Anomaly, DayResult, Employee, Report, Rules, build_report
from .formatting import fmt_minutes

__all__ = ["Anomaly", "DayResult", "Employee", "Report", "Rules", "build_report", "fmt_minutes"]
__version__ = "1.0.0"
