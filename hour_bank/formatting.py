def fmt_minutes(minutes: int, signed: bool = False) -> str:
    """Format a number of minutes as HH:MM, e.g. -75 -> "-01:15"."""
    sign = "-" if minutes < 0 else ("+" if signed and minutes > 0 else "")
    hours, mins = divmod(abs(int(minutes)), 60)
    return f"{sign}{hours:02d}:{mins:02d}"
