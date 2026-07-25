from datetime import datetime

import pytest

from validators import (
    validate_calendar_date,
    validate_day,
    validate_month,
    validate_year,
)

CURRENT_YEAR = datetime.now().year


@pytest.mark.parametrize("month", [1, 6, 12])
def test_valid_months_pass(month):
    assert validate_month(month) is None


@pytest.mark.parametrize("month", [0, 13, -1, 100])
def test_invalid_months_rejected(month):
    assert validate_month(month) == "Month must be between 1 and 12."


@pytest.mark.parametrize("day", [1, 15, 31])
def test_valid_days_pass(day):
    assert validate_day(day) is None


@pytest.mark.parametrize("day", [0, 32, -5])
def test_invalid_days_rejected(day):
    assert validate_day(day) == "Day must be between 1 and 31."


@pytest.mark.parametrize("year", [CURRENT_YEAR, CURRENT_YEAR + 1])
def test_current_and_next_year_pass(year):
    assert validate_year(year) is None


@pytest.mark.parametrize("year", [CURRENT_YEAR - 1, CURRENT_YEAR + 2, 26])
def test_out_of_range_years_rejected(year):
    """A user typing "26" instead of "2026" gets a clear message, not a crash."""
    assert validate_year(year) == f"Year must be {CURRENT_YEAR} or {CURRENT_YEAR + 1}."


def test_real_date_passes():
    assert validate_calendar_date(CURRENT_YEAR, 11, 15) is None


@pytest.mark.parametrize(
    "month,day",
    [
        (2, 30),  # February never has 30 days
        (2, 31),
        (4, 31),  # 30-day months
        (6, 31),
        (9, 31),
        (11, 31),
    ],
)
def test_impossible_day_of_month_rejected(month, day):
    """validate_day allows 1-31 for every month, so these reach datetime()
    and used to raise ValueError mid-command."""
    result = validate_calendar_date(CURRENT_YEAR, month, day)
    assert result == f"{month}/{day}/{CURRENT_YEAR} is not a real date. Please check the day."


def test_leap_day_valid_in_leap_year():
    assert validate_calendar_date(2028, 2, 29) is None


def test_leap_day_invalid_in_non_leap_year():
    assert validate_calendar_date(2027, 2, 29) is not None


def test_end_of_30_day_month_valid():
    assert validate_calendar_date(CURRENT_YEAR, 4, 30) is None


def test_end_of_31_day_month_valid():
    assert validate_calendar_date(CURRENT_YEAR, 12, 31) is None
