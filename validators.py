from datetime import datetime
from typing import Optional


def validate_month(month: int) -> Optional[str]:
    if not (1 <= month <= 12):
        return "Month must be between 1 and 12."
    return None


def validate_day(day: int) -> Optional[str]:
    if not (1 <= day <= 31):
        return "Day must be between 1 and 31."
    return None


def validate_year(year: int) -> Optional[str]:
    current_year = datetime.now().year
    if year < current_year or year > current_year + 1:
        return f"Year must be {current_year} or {current_year + 1}."
    return None


def validate_calendar_date(year: int, month: int, day: int) -> Optional[str]:
    """Catch day-of-month combinations the per-field checks let through.

    validate_day allows 1-31 for every month, so Feb 30 or Nov 31 would reach
    datetime() and raise ValueError mid-command.
    """
    try:
        datetime(year, month, day)
    except ValueError:
        return f"{month}/{day}/{year} is not a real date. Please check the day."
    return None
