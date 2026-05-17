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


def validate_hour(hour: int) -> Optional[str]:
    if not (0 <= hour <= 23):
        return "Hour must be between 0 and 23."
    return None


def validate_year(year: int) -> Optional[str]:
    current_year = datetime.now().year
    if year < current_year or year > current_year + 1:
        return f"Year must be {current_year} or {current_year + 1}."
    return None
